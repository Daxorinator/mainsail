import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'klipper'))
import speed_limiter_core as c

AREA = 2.405  # 1.75mm filament

def mv(**kw):
    d = dict(requested=100., allowed=100., cruise_v=100., move_d=50.,
             accel=3000., is_kinematic=True, cap_kind=None, speed_factor=1.0,
             e_ratio=0.02, filament_area=AREA, max_velocity=300.)
    d.update(kw)
    return c.MoveInfo(**d)

def reason(m, **kw):
    return c.classify(m, **kw).reason

def test_idle_and_paused():
    assert reason(None) == c.IDLE
    assert reason(mv(), state="paused") == c.PAUSED

def test_stall():
    assert reason(mv(), stall_delta=2) == c.STALLED

def test_slicer_default():
    assert reason(mv()) == c.SLICER

def test_max_velocity():
    m = mv(requested=500., allowed=300., cruise_v=300., max_velocity=300.)
    assert reason(m) == c.MAX_VELOCITY

def test_override():
    assert reason(mv(speed_factor=0.8)) == c.SPEED_OVERRIDE

def test_z_cap():
    m = mv(requested=100., allowed=20., cruise_v=20., cap_kind='z')
    assert reason(m) == c.KIN_Z

def test_extruder_cap():
    m = mv(requested=100., allowed=40., cruise_v=40., cap_kind='extruder')
    assert reason(m) == c.KIN_EXTRUDER

def test_accel_short_segment():
    m = mv(move_d=2., cruise_v=40.)
    assert reason(m) == c.ACCEL

def test_junction():
    m = mv(move_d=50., cruise_v=40.)
    assert reason(m) == c.JUNCTION

def test_volumetric():
    # 100 mm/s * 0.1 * 2.405 = 24 mm3/s
    m = mv(e_ratio=0.1)
    r = c.classify(m, max_volumetric_flow=25.)
    assert r.reason == c.VOLUMETRIC and r.likely
    assert reason(m, max_volumetric_flow=40.) == c.SLICER
    assert reason(m, max_volumetric_flow=0.) == c.SLICER

def test_min_layer_time():
    m = mv()
    assert reason(m, min_layer_time=10., last_layer_time=10.4) == c.MIN_LAYER_TIME
    assert reason(m, min_layer_time=10., last_layer_time=25.) == c.SLICER
    assert reason(m, min_layer_time=10., last_layer_time=None) == c.SLICER

def test_priority_accel_over_volumetric():
    m = mv(e_ratio=0.1, cruise_v=50., move_d=50.)
    assert reason(m, max_volumetric_flow=10.) == c.JUNCTION

def test_parse_min_layer_time():
    assert c.parse_min_layer_time("; slowdown_below_layer_time = 5\n") == 5.
    assert c.parse_min_layer_time("; slow_down_layer_time = 4\n") == 4.
    assert c.parse_min_layer_time("; cool_min_layer_time = 10\n") == 10.
    assert c.parse_min_layer_time("G1 X1\n") is None

def test_parse_cura():
    txt = ';SETTING_3 {"global_quality": "\\ncool_min_layer_time = 7\\nfoo = 1"}'
    assert c.parse_min_layer_time(txt) == 7.

def test_window_dominant_reason():
    # 1.2s of long straights at slicer speed, 0.3s burst of short segments
    recs = [(1.2, 1.2, mv()), (1.5, 0.3, mv(move_d=2., cruise_v=40.))]
    r = c.classify_window(recs, 1.5, 1.5)
    assert r.reason == c.SLICER and '20%' not in r.detail
    recs = [(0.3, 0.3, mv()), (1.5, 1.2, mv(move_d=2., cruise_v=40.))]
    r = c.classify_window(recs, 1.5, 1.5)
    assert r.reason == c.ACCEL and '80%' in r.detail, r.detail

def test_window_empty_and_stall():
    assert c.classify_window([], 1.0).reason == c.IDLE
    assert c.classify_window([], 1.0, stall_delta=1).reason == c.STALLED

def test_window_ignores_old_records():
    recs = [(1.0, 1.0, mv(speed_factor=0.5))]
    assert c.classify_window(recs, 10., 1.5).reason == c.IDLE

def test_parse_max_volumetric_flow():
    p = c.parse_max_volumetric_flow
    assert p("; filament_max_volumetric_speed = 16\n") == 16.
    assert p("; filament_max_volumetric_speed = 15,12\n") == 15.
    assert p("; filament_max_volumetric_speed = 21;18\n") == 21.
    assert p("; filament_max_volumetric_speed = 0\n") is None
    assert p("G1 X1\n") is None
    # key mentioned in a list of changed settings must not match
    assert p("; different_settings = a;filament_max_volumetric_speed;b\n") is None

def test_flow_tracker_finds_plateau():
    t = c.FlowTracker()
    # flow = v * e_ratio * area: three feedrates all at ~16 mm3/s
    for v in (80., 100., 120.):
        t.observe(mv(requested=v, allowed=v, cruise_v=v,
                     e_ratio=16. / (v * AREA)), 2.0)
    cap = t.ceiling()
    assert cap is not None and 16. <= cap <= 16.8, cap

def test_flow_tracker_ignores_single_feedrate_and_blips():
    t = c.FlowTracker()
    # one feature at one speed (no evidence of a cap)
    for _ in range(10):
        t.observe(mv(requested=100., allowed=100., cruise_v=100.,
                     e_ratio=0.1), 2.0)
    assert t.ceiling() is None
    # short blips of higher flow do not count
    t.observe(mv(requested=100., allowed=100., cruise_v=100.,
                 e_ratio=0.3), 0.2)
    assert t.ceiling() is None

def test_flow_tracker_ignores_unreached_speed_and_travel():
    t = c.FlowTracker()
    for v in (80., 100., 120.):
        t.observe(mv(requested=v, allowed=v, cruise_v=v * 0.5,
                     e_ratio=16. / (v * AREA)), 5.0)
        t.observe(mv(requested=v, allowed=v, cruise_v=v, e_ratio=0.), 5.0)
    assert t.ceiling() is None

if __name__ == '__main__':
    # Runs without pytest
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith('test_'):
            fn()
            n += 1
    print("%d tests passed" % n)
