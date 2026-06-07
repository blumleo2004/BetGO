import pytest
import random
from stealth import jitter_stake, mug_bet_due


def test_jitter_stake_within_range():
    random.seed(42)
    for _ in range(100):
        raw = 50.0
        result = jitter_stake(raw, pct=0.06)
        assert 47.0 <= result <= 53.0, f"Expected 47-53, got {result}"


def test_jitter_stake_default_pct():
    random.seed(0)
    result = jitter_stake(100.0)
    assert 94.0 <= result <= 106.0


def test_jitter_stake_zero():
    assert jitter_stake(0.0) == 0.0


def test_mug_bet_due_threshold():
    assert mug_bet_due(5) is True
    assert mug_bet_due(4) is False
    assert mug_bet_due(10) is True
    assert mug_bet_due(0) is False


def test_mug_bet_due_custom_threshold():
    assert mug_bet_due(3, threshold=3) is True
    assert mug_bet_due(2, threshold=3) is False
