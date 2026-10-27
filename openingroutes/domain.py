"""Pure rules shared by extraction, review, and publication."""
from pathlib import PurePosixPath
from urllib.parse import urlsplit

TEACHING_FIELDS = (
    "title", "area", "purpose", "prerequisites", "stance", "aim", "operation", "timing",
    "effect", "coordination", "failures", "counterplay", "stance_image", "aim_image",
    "pro_video", "verified_by", "verified_on", "map_version",
)


def safe_url(value: str) -> bool:
    if not isinstance(value, str) or "\\" in value or any(ord(c) < 32 for c in value):
        return False
    if value.startswith("media/"):
        return ".." not in PurePosixPath(value).parts and "%" not in value and ":" not in value
    parsed = urlsplit(value)
    return parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username and not parsed.password


def teaching_gaps(teaching: dict, *, source_verified: bool) -> list[str]:
    gaps = [key for key in TEACHING_FIELDS if not str(teaching.get(key) or "").strip()]
    if not source_verified:
        gaps.insert(0, "source")
    for key in ("stance_image", "aim_image", "pro_video"):
        if key not in gaps and not safe_url(teaching[key]):
            gaps.append(key)
    if teaching.get("reproduction") != "verified":
        gaps.append("reproduction")
    return gaps


def side(number) -> str | None:
    return {2: "T", 3: "CT", "T": "T", "CT": "CT"}.get(number)


def build_rounds(match_id: str, freezes: list[dict], ends: list[dict],
                 regulation_half: int | None = 12) -> list[dict]:
    """Pair by time: round_end's rounds-played field is already incremented in real demos."""
    valid = sorted((x for x in freezes if x.get("is_warmup_period") is False), key=lambda x: x["tick"])
    by_number: dict[int, list[dict]] = {}
    for index, freeze in enumerate(valid):
        played = freeze.get("total_rounds_played")
        if played is None:
            continue
        next_tick = valid[index + 1]["tick"] if index + 1 < len(valid) else float("inf")
        end = next((e for e in sorted(ends, key=lambda x: x["tick"])
                    if freeze["tick"] < e["tick"] < next_tick and side(e.get("winner"))), None)
        number = int(played) + 1
        row = {
            "id": f"{match_id}-r{number}", "match_id": match_id, "number": number,
            "start_tick": freeze["tick"], "freeze_end_tick": freeze["tick"],
            "end_tick": end["tick"] if end else None, "complete": end is not None,
            "winner": side(end.get("winner")) if end else None,
            "reason": end.get("reason") if end else None,
            "is_pistol": bool(end and regulation_half and played in (0, regulation_half)),
            "pistol_basis": f"regulation half={regulation_half}; official freeze + completed round",
            "review_required": regulation_half is None,
        }
        by_number.setdefault(number, []).append(row)
    result = []
    for attempts in by_number.values():
        completed = [x for x in attempts if x["complete"]]
        kept = (completed or attempts)[-1]
        kept["review_required"] |= len(attempts) > 1
        result.append(kept)
    return sorted(result, key=lambda x: x["number"])
