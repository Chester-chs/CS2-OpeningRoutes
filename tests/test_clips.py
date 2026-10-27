import json
import shutil
import subprocess

import pytest

from openingroutes.clips import plan_clip, render


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


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_render_cuts_only_the_planned_range(tmp_path):
    source = tmp_path / "pov.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=320x180:rate=30",
            "-f",
            "lavfi",
            "-i",
            "sine",
            "-t",
            "12",
            "-pix_fmt",
            "yuv420p",
            "-shortest",
            str(source),
        ],
        check=True,
    )
    plan = plan_clip(
        recording_start_tick=0,
        tick_rate=64,
        release_tick=64 * 6,
        effect_tick=64 * 7,
        before=2,
        after=1,
        recording_seconds=12,
    )
    out = render(source, tmp_path / "out", plan, "case")
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(out["pro_video"])],
        capture_output=True,
        text=True,
        check=True,
    )
    assert abs(float(json.loads(probe.stdout)["format"]["duration"]) - 4.0) < 0.3
    assert out["stance_image"].stat().st_size > 0 and out["aim_image"].stat().st_size > 0
