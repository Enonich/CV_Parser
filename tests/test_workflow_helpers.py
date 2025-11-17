import datetime

from backend.api.workflow import serialize_datetime, percentile_bounds, percentile_calibrate

def test_serialize_datetime_basic():
    now = datetime.datetime(2025, 11, 12, 10, 30, 0)
    data = {"ts": now, "list": [now, {"inner": now}], "plain": "value"}
    ser = serialize_datetime(data)
    assert ser["ts"] == now.isoformat()
    assert ser["list"][0] == now.isoformat()
    assert ser["list"][1]["inner"] == now.isoformat()
    assert ser["plain"] == "value"


def test_percentile_bounds_empty():
    p5, p95, spread = percentile_bounds([])
    assert p5 == 0.0 and p95 == 1.0 and spread == 1.0


def test_percentile_bounds_typical():
    values = [0.0, 0.1, 0.2, 0.5, 1.0]
    p5, p95, spread = percentile_bounds(values)
    # With 5 items: p5 index = int(0.05*4)=0; p95 index = int(0.95*4)=3
    assert p5 == 0.0
    assert p95 == 0.5
    assert spread == 0.5


def test_percentile_calibrate():
    p5, p95, spread = 0.0, 0.5, 0.5
    assert percentile_calibrate(-0.1, p5, spread) == 0.0  # below floor
    assert percentile_calibrate(0.0, p5, spread) == 0.0
    mid = percentile_calibrate(0.25, p5, spread)
    assert 0.45 < mid < 0.55  # approx halfway
    top = percentile_calibrate(0.5, p5, spread)
    assert top == 1.0
    above = percentile_calibrate(0.6, p5, spread)
    assert above == 1.0


def test_percentile_calibrate_zero_spread():
    assert percentile_calibrate(1.0, 1.0, 0.0) == 0.0
