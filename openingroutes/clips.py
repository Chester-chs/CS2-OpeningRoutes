"""Cut a professional demonstration from a POV recording of the original demo.

The recording must start at a known demo tick (POVForge plans record from
``start_tick`` without an intro). Times are derived only from ticks; nothing is
estimated from the picture.
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ClipPlan:
    clip_start: float
    clip_end: float
    stance_at: float
    aim_at: float
    release_in_clip: float


def plan_clip(
    *,
    recording_start_tick: int,
    tick_rate: float,
    release_tick: int,
    effect_tick: int | None,
    setup_tick: int | None = None,
    before: float = 8.0,
    after: float = 4.0,
    recording_seconds: float | None = None,
) -> ClipPlan:
    if tick_rate <= 0:
        raise ValueError("Tick rate must be positive")
    if release_tick < recording_start_tick:
        raise ValueError("The recording starts after the throw")

    def at(tick):
        return (tick - recording_start_tick) / tick_rate

    release = at(release_tick)
    end_tick = effect_tick if effect_tick and effect_tick > release_tick else release_tick
    start = max(0.0, release - before)
    end = at(end_tick) + after
    if recording_seconds is not None:
        if release > recording_seconds:
            raise ValueError("The recording ends before the throw")
        end = min(end, recording_seconds)
    stance = at(setup_tick) if setup_tick is not None and setup_tick <= release_tick else release - 1.0
    return ClipPlan(
        clip_start=round(start, 3),
        clip_end=round(end, 3),
        stance_at=round(max(start, stance), 3),
        aim_at=round(release, 3),
        release_in_clip=round(release - start, 3),
    )


def render(source: Path, out_dir: Path, plan: ClipPlan, stem: str, ffmpeg: str = "ffmpeg") -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    clip = out_dir / f"{stem}-pro.mp4"
    stance = out_dir / f"{stem}-stance.jpg"
    aim = out_dir / f"{stem}-aim.jpg"
    base = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]
    subprocess.run(
        [
            *base,
            "-ss",
            f"{plan.clip_start}",
            "-to",
            f"{plan.clip_end}",
            "-i",
            str(source),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(clip),
        ],
        check=True,
    )
    for at, target in ((plan.stance_at, stance), (plan.aim_at, aim)):
        subprocess.run(
            [*base, "-ss", f"{at}", "-i", str(source), "-frames:v", "1", "-q:v", "3", str(target)],
            check=True,
        )
    return {"pro_video": clip, "stance_image": stance, "aim_image": aim}
