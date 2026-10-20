# Exercises speed_limiter.py against Klipper's real Move/LookAheadQueue.
# Needs a Klipper checkout: KLIPPER_DIR=~/klipper python3 tests/test_integration.py
import os, sys, types, math
kdir = os.path.expanduser(os.environ.get('KLIPPER_DIR', '~/klipper'))
if not os.path.isdir(os.path.join(kdir, 'klippy')):
    print("SKIP: no Klipper at %s" % kdir); sys.exit(0)
here = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(kdir, 'klippy'), os.path.join(here, '..', 'klipper')]
for name in ('serial', 'mcu', 'chelper', 'kinematics.extruder'):
    if name not in sys.modules:
        sys.modules[name] = types.ModuleType(name)
sys.modules['kinematics'] = types.ModuleType('kinematics')
sys.modules['kinematics'].extruder = sys.modules['kinematics.extruder']
import toolhead as th
import speed_limiter as sl
import speed_limiter_core as core

class Reactor:
    NOW = 0.
    def register_timer(self, *a): return 1
    def update_timer(self, *a): pass
class Printer:
    def get_reactor(self): return Reactor()
    def register_event_handler(self, *a): pass
class Cfg:
    def get_printer(self): return Printer()
    def getfloat(self, name, default=None, **kw): return {'max_volumetric_flow': 20.}.get(name, default)
class Extruder: filament_area = math.pi * 1.75 ** 2 / 4
class GM: speed_factor = 1. / 60.
class FakeToolHead:
    max_velocity = 300.; max_accel = 3000.; junction_deviation = 0.01
    mcr_pseudo_accel = 1500.; print_stall = 0
    def __init__(self):
        self.lookahead = th.LookAheadQueue(); self.pos = [0., 0., 0., 0.]
        self.extra_axes = []
    def get_extruder(self): return Extruder()
    def move(self, newpos, speed):
        m = th.Move(self, self.pos, newpos, speed)
        # mimic a 40 mm/s Z cap and a 25 mm/s extruder-only cap
        if m.is_kinematic_move and m.axes_d[2]:
            m.limit_speed(40. * m.move_d / abs(m.axes_d[2]), 1e9)
        if not m.is_kinematic_move:
            m.limit_speed(25. / max(abs(m.axes_r[3]), 1e-9) * abs(m.axes_r[3]), 1e9)
        self.pos = list(m.end_pos)
        self.lookahead.add_move(m)

def run(moves):
    t = FakeToolHead(); s = sl.SpeedLimiter(Cfg())
    s.toolhead, s.gcode_move = t, GM()
    s.orig_move = t.move; t.move = s._move_wrapper
    for newpos, speed in moves: t.move(newpos, speed)
    queued = list(t.lookahead.queue)
    for m in t.lookahead.flush(): [cb(1.) for cb in m.timing_callbacks]
    return [(core.classify(r[2], max_volumetric_flow=20.), r[2]) for r in s.records]

def last(moves): return run(moves)[-1][0].reason

# long straight move at 100 mm/s F, modest extrusion -> slicer speed
assert last([([200, 0, 0, 1], 100.)]) == core.SLICER, last([([200, 0, 0, 1], 100.)])
# above max_velocity
assert last([([200, 0, 0, 1], 900.)]) == core.MAX_VELOCITY
# heavy extrusion: 100 mm/s * (e/d=0.1) * 2.405 = 24 mm3/s > 95% of 20
assert last([([200, 0, 0, 20], 100.)]) == core.VOLUMETRIC
# Z move capped
assert last([([0, 0, 20, 0], 100.)]) == core.KIN_Z
# short segments at high speed -> acceleration
moves = [([i * 0.5, 0, 0, 0.01 * i], 200.) for i in range(1, 40)]
assert last(moves) in (core.ACCEL, core.JUNCTION), last(moves)
# 90-degree corners
moves = [([10, 0, 0, 0], 200.), ([10, 10, 0, 0], 200.), ([0, 10, 0, 0], 200.), ([0, 0, 0, 0], 200.)]
assert last(moves) in (core.ACCEL, core.JUNCTION), last(moves)
# polling fallback must not report a bogus speed override
t = FakeToolHead(); s = sl.SpeedLimiter(Cfg())
s.toolhead, s.hooked = t, False
class GM2:
    def get_status(self, *a): return {'speed': 6000., 'speed_factor': 1.0}
s.gcode_move = GM2()
rec = s._polled_record()
assert core.classify_window([(rec[0], 1., rec[2])], rec[0]).reason == core.SLICER
print("integration OK")
