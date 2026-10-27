import pytest

from openingroutes.clips import plan_clip


def test_ticks_map_to_recording_time_with_context_before_and_after():
    p = plan_clip(
        recording_start_tick=1664, tick_rate=64, release_tick=3024, effect_tick=3116, setup_tick=3008
    )
    assert p.aim_at == 21.25 and p.stance_at == 21.0
    assert p.clip_start == 13.25 and p.clip_end == round((3116 - 1664) / 64 + 4, 3)
    assert p.release_in_clip == 8.0


def test_clip_is_clamped_to_the_recording_and_rejects_impossible_ranges():
    p = plan_clip(
        recording_start_tick=0, tick_rate=64, release_tick=64, effect_tick=None, recording_seconds=3
    )
    assert p.clip_start == 0 and p.clip_end == 3 and p.stance_at == 0
    with pytest.raises(ValueError):
        plan_clip(recording_start_tick=100, tick_rate=64, release_tick=50, effect_tick=None)
    with pytest.raises(ValueError):
        plan_clip(
            recording_start_tick=0, tick_rate=64, release_tick=6400, effect_tick=None, recording_seconds=10
        )
    with pytest.raises(ValueError):
        plan_clip(recording_start_tick=0, tick_rate=0, release_tick=1, effect_tick=None)
