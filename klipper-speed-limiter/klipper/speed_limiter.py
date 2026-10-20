# Report what is currently limiting the print speed
#
# Copyright (C) 2026
# This file may be distributed under the terms of the GNU GPLv3 license.
import logging, math, collections, os
try:
    import speed_limiter_core as core
except ImportError:
    from . import speed_limiter_core as core

UPDATE_INTERVAL = 0.25
STALL_WINDOW = 5.0
WINDOW = 1.5

class SpeedLimiter:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        # None: read it from the gcode file, else infer it. 0 disables.
        self.cfg_flow = config.getfloat('max_volumetric_flow', None,
                                        minval=0.)
        self.file_flow = None
        self.tracker = core.FlowTracker()
        self.settings_loaded = False
        self.min_layer_time = config.getfloat('min_layer_time', None,
                                              minval=0.)
        self.auto_min_layer_time = self.min_layer_time is None
        if self.auto_min_layer_time:
            self.min_layer_time = 0.
        self.records = collections.deque(maxlen=50000)  # (end, dur, MoveInfo)
        self.toolhead = self.gcode_move = self.print_stats = None
        self.hooked = False
        self.last_stalls = 0
        self.stall_events = collections.deque()
        self.layer_times = {}
        self.cur_layer = None
        self.cur_layer_start = None
        self.last_layer_time = None
        self.status = self._make_status(core.Result(core.IDLE), None)
        self.printer.register_event_handler("klippy:connect",
                                            self._handle_connect)
        self.printer.register_event_handler("virtual_sdcard:reset_file",
                                            self._reset_job)
        self.timer = self.reactor.register_timer(self._update)
    def _handle_connect(self):
        self.toolhead = self.printer.lookup_object('toolhead')
        self.gcode_move = self.printer.lookup_object('gcode_move')
        self.print_stats = self.printer.lookup_object('print_stats', None)
        self.vsd = self.printer.lookup_object('virtual_sdcard', None)
        try:
            self.orig_move = self.toolhead.move
            self.toolhead.move = self._move_wrapper
            self.hooked = True
        except Exception:
            logging.exception("speed_limiter: unable to hook toolhead.move; "
                              "falling back to polling")
        self.reactor.update_timer(self.timer, self.reactor.NOW)
    def _reset_job(self, *args):
        self.layer_times.clear()
        self.cur_layer = self.cur_layer_start = self.last_layer_time = None
        self.settings_loaded = False
        self.file_flow = None
        self.tracker = core.FlowTracker()
        if self.auto_min_layer_time:
            self.min_layer_time = 0.
    # Tag moves as they are queued
    def _move_wrapper(self, newpos, speed):
        self.orig_move(newpos, speed)
        try:
            self._tag_last_move(speed)
        except Exception:
            logging.exception("speed_limiter: failed to tag move")
    def _tag_last_move(self, speed):
        th = self.toolhead
        # Older (Creality) forks call it move_queue instead of lookahead
        queue = getattr(th, 'lookahead', None) or th.move_queue
        move = queue.get_last()
        if move is None or getattr(move, '_sl_tagged', False):
            return
        move._sl_tagged = True
        if move.is_kinematic_move:
            allowed_nocap = min(speed, th.max_velocity)
        else:
            allowed_nocap = speed
        cap = math.sqrt(move.max_cruise_v2)
        cap_kind = None
        if cap < allowed_nocap * core.CRUISE_SLACK:
            if not move.is_kinematic_move or move.axes_r[3] < 0.:
                cap_kind = 'extruder'  # extrude-only or retraction
            elif move.axes_d[2]:
                cap_kind = 'z'
            else:
                cap_kind = 'kinematic'
        ex = th.get_extruder()
        area = getattr(ex, 'filament_area', 0.)
        e_ratio = max(move.axes_r[3], 0.) if len(move.axes_r) > 3 else 0.
        info = {
            'requested': speed, 'allowed': cap, 'move_d': move.move_d,
            'accel': move.accel, 'is_kinematic': move.is_kinematic_move,
            'cap_kind': cap_kind,
            'speed_factor': self.gcode_move.speed_factor * 60.,
            'e_ratio': e_ratio, 'filament_area': area,
            'max_velocity': th.max_velocity,
        }
        move._sl_info = info
        move._sl_z = move.end_pos[2]
        def done(end_time, move=move):
            dur =move.accel_t + move.cruise_t + move.decel_t
            mi = core.MoveInfo(
                info['requested'], info['allowed'], move.cruise_v,
                info['move_d'], info['accel'], info['is_kinematic'],
                info['cap_kind'], info['speed_factor'],
                info['e_ratio'], info['filament_area'], info['max_velocity'])
            self.tracker.observe(mi, dur)
            self.records.append((end_time, dur, mi, move._sl_z,
                                 info['e_ratio'] > 0.))
        move.timing_callbacks.append(done)
    # Periodic classification
    def _printing_state(self, eventtime):
        if self.print_stats is None:
            return "printing"
        return self.print_stats.get_status(eventtime).get('state', 'standby')
    def _current_records(self, eventtime):
        est = self.toolhead.mcu.estimated_print_time(eventtime)
        recs = self.records
        while recs and recs[0][0] < est - WINDOW:
            recs.popleft()
        cur = None
        window = []
        for rec in recs:
            if rec[0] - rec[1] > est:
                break
            window.append((rec[0], rec[1], rec[2]))
            if rec[0] >= est:
                cur = rec
        return est, window, cur
    def _track_layers(self, rec, eventtime):
        if rec is None or not rec[4]:
            return
        layer_z = round(rec[3], 3)
        if layer_z != self.cur_layer:
            if self.cur_layer_start is not None:
                self.last_layer_time = eventtime - self.cur_layer_start
            self.cur_layer = layer_z
            self.cur_layer_start = eventtime
    def _load_slicer_settings(self):
        # Once per job: per-filament flow cap and min layer time that the
        # slicer embedded in the gcode file (usually at the end).
        self.settings_loaded = True
        if self.vsd is None:
            return
        try:
            path = self.vsd.file_path()
            if not path:
                self.settings_loaded = False  # file not open yet
                return
            with open(path, 'rb') as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                f.seek(max(0, size - 262144))
                text = f.read().decode('utf-8', 'ignore')
                if (core.parse_max_volumetric_flow(text) is None
                        and core.parse_min_layer_time(text) is None):
                    f.seek(0)  # some slicers put the settings at the start
                    text = f.read(65536).decode('utf-8', 'ignore')
            self.file_flow = core.parse_max_volumetric_flow(text)
            if self.auto_min_layer_time:
                self.min_layer_time = core.parse_min_layer_time(text) or 0.
        except Exception:
            logging.exception("speed_limiter: unable to read slicer settings")
    def _flow_cap(self):
        # (mm^3/s, source) of the flow limit in force, cap 0 = unknown
        if self.cfg_flow is not None:
            return self.cfg_flow, "config"
        if self.file_flow:
            return self.file_flow, "slicer file"
        inferred = self.tracker.ceiling()
        if inferred:
            return inferred, "inferred"
        return 0., None
    def _update(self, eventtime):
        try:
            self._do_update(eventtime)
        except Exception:
            logging.exception("speed_limiter: update failed")
        return eventtime + UPDATE_INTERVAL
    def _do_update(self, eventtime):
        state = self._printing_state(eventtime)
        stalls = self.toolhead.print_stall
        if stalls > self.last_stalls:
            self.stall_events.append(eventtime)
        self.last_stalls = stalls
        while self.stall_events and self.stall_events[0] < eventtime - STALL_WINDOW:
            self.stall_events.popleft()
        if state not in ("printing", "paused"):
            self.status = self._make_status(core.Result(core.IDLE), None)
            return
        if not self.settings_loaded:
            self._load_slicer_settings()
        est, window, rec = self._current_records(eventtime)
        if not window and not self.hooked:
            rec = self._polled_record()
            window = [(est, 1., rec[2])]
        self._track_layers(rec, eventtime)
        mlt = max(self.min_layer_time, 0.)
        cap, source = self._flow_cap()
        kw = dict(state=state, stall_delta=len(self.stall_events),
                  max_volumetric_flow=cap,
                  min_layer_time=mlt, last_layer_time=self.last_layer_time)
        res = core.classify_window(window, est, WINDOW, **kw)
        if res.reason == core.VOLUMETRIC and source:
            res.detail += ", %s" % (source,)
        self.status = self._make_status(res, rec[2] if rec else None)
    def _polled_record(self):
        # Coarse fallback: no per-move data, so only the requested speed,
        # max_velocity and speed override can be judged.
        gm = self.gcode_move.get_status()
        req = gm['speed'] / 60. * gm['speed_factor']
        th = self.toolhead
        mi = core.MoveInfo(req, min(req, th.max_velocity),
                           min(req, th.max_velocity), 0., 0.,
                           speed_factor=gm['speed_factor'],
                           max_velocity=th.max_velocity)
        return (0., 0., mi, 0., False)
    def _make_status(self, res, mi):
        cap, source = self._flow_cap()
        return {
            'active': res.reason not in (core.IDLE,),
            'reason': res.reason,
            'label': res.label,
            'detail': res.detail,
            'likely': res.likely,
            'limit': res.limit,
            'requested_speed': mi.requested if mi else 0.,
            'cruise_speed': mi.cruise_v if mi else 0.,
            'flow': mi.flow() if mi else 0.,
            'max_volumetric_flow': cap,
            'max_volumetric_flow_source': source,
            'hooked': self.hooked,
        }
    def get_status(self, eventtime):
        return dict(self.status)

def load_config(config):
    return SpeedLimiter(config)
