# Pure classification logic for the speed_limiter Klipper extra.
#
# No Klipper imports here so that it can be unit tested standalone.
import math, re

# Reason codes
IDLE = "idle"
PAUSED = "paused"
STALLED = "stalled"
KIN_GENERIC = "kinematic_velocity"
KIN_Z = "z_velocity"
KIN_EXTRUDER = "extruder_velocity"
ACCEL = "acceleration"
JUNCTION = "cornering"
MAX_VELOCITY = "max_velocity"
SPEED_OVERRIDE = "speed_override"
VOLUMETRIC = "volumetric_flow"
MIN_LAYER_TIME = "min_layer_time"
SLICER = "slicer_speed"

LABELS = {
    IDLE: "Not printing",
    PAUSED: "Paused",
    STALLED: "G-code throughput (printer starving for moves)",
    KIN_GENERIC: "Kinematic velocity limit",
    KIN_Z: "Max Z velocity",
    KIN_EXTRUDER: "Extruder velocity limit",
    ACCEL: "Acceleration (short segments)",
    JUNCTION: "Cornering / junction speed",
    MAX_VELOCITY: "Max configured velocity",
    SPEED_OVERRIDE: "Speed override (M220)",
    VOLUMETRIC: "Max volumetric flow",
    MIN_LAYER_TIME: "Minimum layer time",
    SLICER: "Slicer feature speed",
}

# Within this fraction of a limit counts as "at" the limit
CLOSE = 0.95
CRUISE_SLACK = 0.97


class MoveInfo(object):
    """What we know about one move, captured when it was queued/finalized."""
    def __init__(self, requested, allowed, cruise_v, move_d, accel,
                 is_kinematic=True, cap_kind=None, speed_factor=1.0,
                 e_ratio=0.0, filament_area=0.0, max_velocity=0.0):
        self.requested = requested        # mm/s, after M220 factor
        self.allowed = allowed            # mm/s, after max_velocity & kin caps
        self.cruise_v = cruise_v          # mm/s, after lookahead planning
        self.move_d = move_d
        self.accel = accel
        self.is_kinematic = is_kinematic
        self.cap_kind = cap_kind          # None, 'z' or 'extruder'
        self.speed_factor = speed_factor  # 1.0 == 100%
        self.e_ratio = e_ratio            # mm filament per mm of move
        self.filament_area = filament_area
        self.max_velocity = max_velocity

    def flow(self):
        return max(0., self.cruise_v * self.e_ratio * self.filament_area)


class Result(object):
    def __init__(self, reason, detail="", limit=None, likely=False):
        self.reason = reason
        self.label = LABELS[reason]
        self.detail = detail
        self.limit = limit
        self.likely = likely

    def __repr__(self):
        return "Result(%s, %r)" % (self.reason, self.detail)


def classify(move, state="printing", stall_delta=0, max_volumetric_flow=0.,
             min_layer_time=0., last_layer_time=None):
    """Return a Result describing what is limiting the speed of `move`."""
    if state == "paused":
        return Result(PAUSED)
    if stall_delta > 0:
        return Result(STALLED,
                      "%d buffer underruns recently" % (stall_delta,))
    if move is None:
        return Result(IDLE)
    allowed = move.allowed
    # Planner could not reach the allowed speed
    if move.cruise_v < allowed * CRUISE_SLACK:
        if move.cap_kind == 'z' and move.allowed < move.requested * CRUISE_SLACK:
            return Result(KIN_Z, "capped at %.0f mm/s" % (move.allowed,),
                          move.allowed)
        if (move.cap_kind in ('extruder', 'kinematic')
                and move.allowed < move.requested * CRUISE_SLACK):
            return Result(KIN_EXTRUDER if move.cap_kind == 'extruder'
                          else KIN_GENERIC,
                          "capped at %.0f mm/s" % (move.allowed,),
                          move.allowed)
        detail = "reaching %.0f of %.0f mm/s" % (move.cruise_v, allowed)
        if move.accel > 0 and move.move_d * move.accel < allowed ** 2:
            return Result(ACCEL, detail, move.cruise_v)
        return Result(JUNCTION, detail, move.cruise_v)
    if move.cap_kind and move.allowed < move.requested * CRUISE_SLACK:
        kind = {'z': KIN_Z, 'extruder': KIN_EXTRUDER}.get(
            move.cap_kind, KIN_GENERIC)
        return Result(kind, "capped at %.0f mm/s" % (move.allowed,),
                      move.allowed)
    if (move.max_velocity > 0
            and move.requested >= move.max_velocity * 0.999):
        return Result(MAX_VELOCITY, "%.0f mm/s" % (move.max_velocity,),
                      move.max_velocity)
    if move.speed_factor < 0.995:
        return Result(SPEED_OVERRIDE, "%.0f%%" % (move.speed_factor * 100.,),
                      move.speed_factor * 100.)
    flow = move.flow()
    if max_volumetric_flow > 0 and flow >= max_volumetric_flow * CLOSE:
        return Result(VOLUMETRIC,
                      "%.1f of %.1f mm³/s" % (flow, max_volumetric_flow),
                      max_volumetric_flow, likely=True)
    if (min_layer_time > 0 and last_layer_time is not None
            and min_layer_time <= last_layer_time <= min_layer_time * 1.08):
        return Result(MIN_LAYER_TIME,
                      "layer took %.1fs (min %.1fs)"
                      % (last_layer_time, min_layer_time),
                      min_layer_time, likely=True)
    return Result(SLICER, "%.0f mm/s" % (move.requested,), move.requested)


# Slicer settings that carry the minimum layer time, as embedded in gcode
_MIN_LAYER_RE = re.compile(
    r"^;\s*(?:slowdown_below_layer_time|slow_down_layer_time|"
    r"cool_min_layer_time)\s*=\s*([0-9.]+)", re.M)
_CURA_RE = re.compile(r"\\ncool_min_layer_time\s*=\s*([0-9.]+)")


def parse_min_layer_time(text):
    """Find a minimum layer time in slicer config text, or None."""
    m = _MIN_LAYER_RE.findall(text) + _CURA_RE.findall(text)
    if not m:
        return None
    try:
        return max(float(v) for v in m)
    except ValueError:
        return None


def classify_window(records, now, window=1.5, **kw):
    """Classify a sliding window of (end_time, duration, MoveInfo) records.

    Individual moves change every few ms, so sampling one would flicker.
    Instead each move in [now - window, now] votes for its reason, weighted
    by the time it overlaps the window. Returns the dominant Result with its
    share of the window appended to the detail.
    """
    lo = now - window
    weights = {}
    best = {}
    total = 0.
    for end, dur, mi in records:
        overlap = min(end, now) - max(end - dur, lo)
        if overlap <= 0.:
            continue
        res = classify(mi, **kw)
        weights[res.reason] = weights.get(res.reason, 0.) + overlap
        if res.reason not in best or overlap > best[res.reason][0]:
            best[res.reason] = (overlap, res)
        total += overlap
    if not weights:
        return classify(None, **kw)
    reason = max(weights, key=weights.get)
    res = best[reason][1]
    share = weights[reason] / total
    if share < 0.995:
        res.detail = ("%s, %.0f%% of recent moves" % (res.detail, share * 100.)
                      if res.detail else "%.0f%% of recent moves"
                      % (share * 100.))
    return res


_FLOW_RE = re.compile(
    r"^;\s*filament_max_volumetric_speed\s*=\s*([0-9.;,\s]+)", re.M)


def parse_max_volumetric_flow(text):
    """Per-filament max volumetric speed (mm^3/s) from slicer settings.

    PrusaSlicer, OrcaSlicer and Creality Print embed it; for several
    filaments the first (T0) value is used. 0 means unlimited -> None.
    """
    for m in _FLOW_RE.findall(text):
        nums = re.findall(r"[0-9]+(?:\.[0-9]+)?", m)
        if nums:
            val = float(nums[0])
            return val if val > 0. else None
    return None


class FlowTracker(object):
    """Infer a volumetric flow ceiling from the print itself.

    A slicer flow limit scales the feedrate of wide/tall lines down so they
    all land on the same flow. So if a good amount of extrusion time sits at
    the same (highest) flow, spread over at least two clearly different
    feedrates, that flow is probably a cap and not just one feature's speed.
    """
    BIN = 0.02          # relative width of a flow bin
    MIN_TIME = 3.0      # seconds of extrusion at the plateau
    MIN_SPREAD = 1.03   # fastest/slowest feedrate seen at the plateau

    def __init__(self):
        self.bins = {}

    def observe(self, move, duration):
        if (move.e_ratio <= 0. or duration <= 0.
                or move.cruise_v < move.allowed * CRUISE_SLACK):
            return
        flow = move.flow()
        if flow <= 0.:
            return
        idx = int(math.floor(math.log(flow) / math.log(1. + self.BIN)))
        entry = self.bins.setdefault(idx, [0., set()])
        entry[0] += duration
        entry[1].add(int(round(move.requested)))

    def ceiling(self):
        """Estimated cap in mm^3/s, or None if no plateau is evident."""
        for idx in sorted(self.bins, reverse=True):
            time_t, speeds = self.bins[idx]
            lower = self.bins.get(idx - 1)
            if lower is not None:
                time_t += lower[0]
                speeds = speeds | lower[1]
            if (time_t >= self.MIN_TIME and speeds
                    and max(speeds) >= min(speeds) * self.MIN_SPREAD):
                return (1. + self.BIN) ** (idx + 1)
        return None
