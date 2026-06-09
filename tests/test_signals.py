import pytest

from bot.services.signals import detect_price_spike, detect_volume_spike, pct_change


def test_pct_change():
    assert pct_change(120, 100) == pytest.approx(0.20)
    assert pct_change(80, 100) == pytest.approx(-0.20)
    assert pct_change(10, 0) == 0.0


def test_price_spike_triggers():
    s = detect_price_spike(130, [100, 100, 100], 0.15)
    assert s.triggered is True
    assert s.magnitude == pytest.approx(0.30)


def test_price_spike_below_threshold():
    s = detect_price_spike(110, [100, 100, 100], 0.15)
    assert s.triggered is False


def test_price_spike_empty_history():
    s = detect_price_spike(100, [], 0.15)
    assert s.triggered is False


def test_volume_spike_triggers():
    s = detect_volume_spike(10, [3, 4, 3], 2.0)
    # moyenne ~3.33, 10/3.33 ~3 >= 2
    assert s.triggered is True


def test_volume_spike_below_threshold():
    s = detect_volume_spike(4, [3, 4, 3], 2.0)
    assert s.triggered is False
