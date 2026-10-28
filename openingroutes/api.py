import hashlib
import json
import re
import secrets
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .domain import safe_url, teaching_gaps
from .models import Source, Teaching
from .places import valid_place
from .publish import export_bundle
from .store import Store, now

ID = r"^[A-Za-z0-9_-]{1,150}$"
MAX_DEMO = 2 * 1024**3


class RoundReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approved: bool = False
    pro_video: str = Field(default="", max_length=1000)
    description: str = Field(default="", max_length=4000)
    reviewer: str = Field(default="", max_length=100)
    resolution: Literal["", "confirmed", "excluded"] = ""
    resolution_note: str = Field(default="", max_length=2000)
    pistol_override: bool | None = None


class VariantIds(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[str] = Field(min_length=2, max_length=50)


class VariantSplit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    throw_ids: list[str] = Field(min_length=1, max_length=500)


class VariantMeta(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(default="", max_length=200)
    purpose: str = Field(default="", max_length=2000)
    reviewed: bool = False
    reviewer: str = Field(default="", max_length=100)


class PlaceLabel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    label: str | None = Field(default=None, min_length=1, max_length=60)
    area: Literal["A", "B", "Mid", "CT", "other"] | None = None


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid")
    throw_id: str = Field(pattern=ID)
    role: str = Field(min_length=1, max_length=100)
    time: float = Field(ge=-120, le=3600)
    followup: str = Field(default="", max_length=2000)


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=ID)
    title: str = Field(min_length=1, max_length=200)
    area: str = Field(min_length=1, max_length=100)
    side: str = Field(pattern=r"^(T|CT)$")
    purpose: str = Field(min_length=1, max_length=2000)
    conditions: str = Field(min_length=1, max_length=2000)
    steps: list[Step] = Field(min_length=1, max_length=50)
    counter_ids: list[str] = Field(default_factory=list, max_length=30)
    counter_explanation: str = Field(default="", max_length=2000)
    status: str = Field(default="draft", pattern=r"^(draft|published|withdrawn)$")


def create_app(root: Path, *, testing=False, web_root: Path | None = None):
    root = Path(root).resolve()
    store = Store(root)
    token = secrets.token_urlsafe(32)
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="demo-worker")
    processes = {}
    cancelled = set()

    @asynccontextmanager
    async def lifespan(_app):
        yield
        for key, process in list(processes.items()):
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            job = store.all("jobs")[key]
            if job["status"] in ("queued", "parsing"):
                store.put(
                    "jobs", key, {**job, "status": "interrupted", "error": "Application closed during import"}
                )
        executor.shutdown(wait=False, cancel_futures=True)

    app = FastAPI(title="OpeningRoutes", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.store = store
    for job in store.all("jobs").values():
        if job["status"] in ("queued", "parsing"):
            store.put(
                "jobs",
                job["id"],
                {**job, "status": "interrupted", "error": "Restart interrupted this import. Retry."},
            )

    @app.middleware("http")
    async def local_boundary(request: Request, call_next):
        host = urlsplit("//" + request.headers.get("host", "")).hostname
        if host not in (
            {"127.0.0.1", "localhost", "[::1]", "::1", "testserver"}
            if testing
            else {"127.0.0.1", "localhost", "::1"}
        ):
            return JSONResponse({"detail": "Invalid local host"}, status_code=400)
        origin = request.headers.get("origin")
        if origin and origin != f"{request.url.scheme}://{request.headers.get('host')}":
            return JSONResponse({"detail": "Cross-origin access denied"}, status_code=403)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            supplied = request.headers.get("x-session-token", "")
            if not secrets.compare_digest(supplied, token):
                return JSONResponse({"detail": "Local session token required"}, status_code=403)
            size = request.headers.get("content-length", "0")
            if not size.isdigit() or int(size) > MAX_DEMO + 1024 * 1024:
                return JSONResponse({"detail": "Upload too large"}, status_code=413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' https: data:; "
            "media-src 'self' https:; connect-src 'self'; frame-src https://www.youtube-nocookie.com; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        )
        return response

    def find(collection, item_id):
        return next((x for x in store.catalog()[collection] if x["id"] == item_id), None)

    @app.get("/api/session")
    def session():
        return {"token": token, "mode": "desktop", "version": "0.2.0"}

    @app.get("/api/catalog")
    def catalog():
        return store.catalog()

    @app.get("/api/timelines/{round_id}")
    def timeline(round_id: str):
        if not re.fullmatch(ID, round_id):
            raise HTTPException(400, "Invalid round")
        data = store.timeline(round_id)
        if data is None:
            raise HTTPException(404, "Timeline unavailable")
        return data

    @app.get("/api/jobs")
    def jobs():
        return sorted(store.all("jobs").values(), key=lambda x: x["created_at"], reverse=True)

    def run_import(job_id):
        if job_id in cancelled:
            return
        command = (
            [sys.executable, "--worker"]
            if getattr(sys, "frozen", False)
            else [sys.executable, "-m", "openingroutes.worker"]
        )
        try:
            with (root / "logs" / f"{job_id}.log").open("w", encoding="utf-8") as log:
                process = subprocess.Popen(
                    [*command, str(root), job_id],
                    stdout=log,
                    stderr=log,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                processes[job_id] = process
                if job_id in cancelled and process.poll() is None:
                    process.terminate()
                returncode = process.wait(timeout=600)
            if job_id in cancelled:
                job = store.all("jobs")[job_id]
                store.put("jobs", job_id, {**job, "status": "cancelled", "stage": "cancelled"})
            elif returncode:
                job = store.all("jobs")[job_id]
                store.put(
                    "jobs",
                    job_id,
                    {**job, "status": "failed", "error": "Demo parsing failed. Check the local task log."},
                )
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
            job = store.all("jobs")[job_id]
            store.put(
                "jobs",
                job_id,
                {
                    **job,
                    "status": "failed",
                    "error": "Parsing exceeded the 10 minute limit. Retry or use a smaller demo.",
                },
            )
        except OSError:
            job = store.all("jobs")[job_id]
            store.put(
                "jobs", job_id, {**job, "status": "failed", "error": "Could not start the parser process"}
            )
        finally:
            processes.pop(job_id, None)

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_job(job_id: str):
        job = store.all("jobs").get(job_id)
        if not job:
            raise HTTPException(404, "Import task not found")
        if job["status"] not in ("queued", "parsing"):
            raise HTTPException(409, "This task is no longer running")
        cancelled.add(job_id)
        process = processes.get(job_id)
        if process and process.poll() is None:
            process.terminate()
        job.update(status="cancelled", stage="cancelled", error=None)
        store.put("jobs", job_id, job)
        return job

    @app.post("/api/import", status_code=202)
    async def import_demo(demo: Annotated[UploadFile, File()], source: Annotated[str, Form()]):
        try:
            validated = Source.model_validate_json(source)
        except ValidationError as e:
            raise HTTPException(422, "Complete the match source fields") from e
        if validated.verified and not validated.reviewer:
            raise HTTPException(422, "Reviewer required for source verification")
        if not demo.filename or not demo.filename.lower().endswith(".dem"):
            raise HTTPException(422, "Select a .dem file")
        if sum(j["status"] in ("queued", "parsing") for j in store.all("jobs").values()) >= 3:
            raise HTTPException(429, "Import queue is full")
        job_id = uuid4().hex
        destination = root / "uploads" / f"{job_id}.dem"
        total = 0
        try:
            with destination.open("wb") as f:
                first = await demo.read(1024 * 1024)
                if not first.startswith(b"PBDEMS2\x00"):
                    raise HTTPException(422, "Not a CS2 demo (PBDEMS2 header missing)")
                total += len(first)
                f.write(first)
                while block := await demo.read(1024 * 1024):
                    total += len(block)
                    if total > MAX_DEMO:
                        raise HTTPException(413, "Demo exceeds 2 GiB")
                    f.write(block)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        job = {
            "id": job_id,
            "status": "queued",
            "stage": "queued",
            "created_at": now(),
            "source": validated.model_dump(),
            "size": total,
        }
        store.put("jobs", job_id, job)
        executor.submit(run_import, job_id)
        return job

    @app.put("/api/teachings/{throw_id}")
    def save_teaching(throw_id: str, teaching: Teaching):
        row = find("throws", throw_id)
        if row is None:
            raise HTTPException(404, "Throw not found")
        match = find("matches", row["match_id"])
        data = teaching.model_dump()
        confirmed = data.pop("verification_confirmed")
        previous = store.all("teachings").get(throw_id, {})
        action_fields = (
            "stance",
            "aim",
            "operation",
            "timing",
            "prerequisites",
            "effect",
            "coordination",
            "stance_image",
            "aim_image",
            "map_version",
        )
        if (
            previous.get("reproduction") == "verified"
            and not confirmed
            and any(data.get(key) != previous.get(key) for key in action_fields)
        ):
            data["reproduction"] = "pending"
        gaps = teaching_gaps(data, source_verified=match["source"]["verified"])
        for key in ("stance_image", "aim_image", "pro_video", "recreation_video"):
            asset = data.get(key, "")
            if asset.startswith("media/") and not (root / asset).is_file():
                gaps.append(key)
        if data["status"] == "published" and gaps:
            raise HTTPException(422, {"message": "Teaching is incomplete", "gaps": sorted(set(gaps))})
        store.save_teaching(throw_id, data)
        return {"teaching": data, "gaps": gaps}

    @app.put("/api/sources/{match_id}")
    def save_source(match_id: str, source: Source):
        match = store.all("matches").get(match_id)
        if not match:
            raise HTTPException(404, "Match not found")
        if source.verified and not source.reviewer:
            raise HTTPException(422, "Reviewer required for source verification")
        match["source"] = source.model_dump()
        store.save_match(match)
        return match["source"]

    @app.put("/api/rounds/{round_id}/review")
    def review_round(round_id: str, review: RoundReview):
        raw = next(
            (r for m in store.all("matches").values() for r in m["rounds"] if r["id"] == round_id), None
        )
        if not raw:
            raise HTTPException(404, "Round not found")
        if review.pro_video and not safe_url(review.pro_video):
            raise HTTPException(422, "Invalid video URL")
        if review.resolution and (not review.resolution_note.strip() or not review.reviewer):
            raise HTTPException(422, "A resolution needs a written basis and a reviewer")
        if review.pistol_override is not None and review.resolution != "confirmed":
            raise HTTPException(422, "Pistol corrections require a confirmed resolution")
        unresolved = raw.get("review_required") and not review.resolution
        if review.approved and (
            not review.reviewer
            or not review.description
            or not review.pro_video
            or not raw.get("complete")
            or unresolved
            or review.resolution == "excluded"
        ):
            raise HTTPException(422, "Round requires completed evidence and no unresolved round warnings")
        store.put("round_reviews", round_id, review.model_dump())
        return review

    def variant_index():
        data = store.catalog()
        return data, {v["id"]: v for v in data["variants"]}

    def stored_meta(variant):
        return {k: variant.get(k) for k in ("title", "purpose", "reviewed", "reviewer")}

    @app.post("/api/variants/merge")
    def merge_variants(body: VariantIds):
        _, variants = variant_index()
        if any(i not in variants for i in body.ids) or len(set(body.ids)) != len(body.ids):
            raise HTTPException(404, "Variant not found")
        chosen = [variants[i] for i in body.ids]
        if len({(v["map"], v["kind"], v["side"]) for v in chosen}) != 1:
            raise HTTPException(409, "Only the same map, grenade type and side can be merged")
        base = next((v for v in chosen if v.get("title")), chosen[0])
        members = [m for v in chosen for m in v["members"]]
        new_id = "v-" + uuid4().hex[:12]
        for v in chosen:
            store.delete("variants", v["id"])
        record = {"id": new_id, "source": "manual", "members": members, **stored_meta(base)}
        record["reviewed"] = False
        store.put("variants", new_id, record)
        return record

    @app.post("/api/variants/{variant_id}/split")
    def split_variant(variant_id: str, body: VariantSplit):
        _, variants = variant_index()
        variant = variants.get(variant_id)
        if not variant:
            raise HTTPException(404, "Variant not found")
        moving = list(dict.fromkeys(body.throw_ids))
        if any(t not in variant["members"] for t in moving) or len(moving) >= len(variant["members"]):
            raise HTTPException(422, "Choose some, but not all, throws from this variant")
        remaining = [m for m in variant["members"] if m not in moving]
        meta = stored_meta(variant)
        store.put(
            "variants",
            variant_id,
            {"id": variant_id, "source": "manual", "members": remaining, **meta, "reviewed": False},
        )
        new_id = "v-" + uuid4().hex[:12]
        record = {
            "id": new_id,
            "source": "manual",
            "members": moving,
            "title": "",
            "purpose": "",
            "reviewed": False,
            "reviewer": "",
        }
        store.put("variants", new_id, record)
        return record

    @app.put("/api/variants/{variant_id}")
    def label_variant(variant_id: str, body: VariantMeta):
        _, variants = variant_index()
        variant = variants.get(variant_id)
        if not variant:
            raise HTTPException(404, "Variant not found")
        if body.reviewed and not body.reviewer:
            raise HTTPException(422, "Reviewer required")
        record = {"id": variant_id, "source": variant["source"], **body.model_dump()}
        if variant["source"] == "manual":
            record["members"] = variant["members"]
        store.put("variants", variant_id, record)
        return {**variant, **body.model_dump()}

    @app.put("/api/places/{map_name}/{place}")
    def label_place(map_name: str, place: str, body: PlaceLabel):
        if not valid_place(map_name, place):
            raise HTTPException(422, "Invalid map or place name")
        if body.label is None and body.area is None:
            raise HTTPException(422, "Provide a label or an area")
        key = f"{map_name}:{place}"
        value = dict(store.all("places").get(key) or {})
        if body.label is not None:
            value["label"] = body.label
        if body.area is not None:
            value["area"] = body.area
        store.put("places", key, value)
        return {"map": map_name, "place": place, **value}

    @app.put("/api/plans/{plan_id}")
    def save_plan(plan_id: str, plan: Plan):
        if plan_id != plan.id:
            raise HTTPException(422, "Plan ID mismatch")
        available = {t["id"]: t for t in store.catalog()["throws"]}
        if any(s.throw_id not in available for s in plan.steps):
            raise HTTPException(422, "Plan references a missing throw")
        if plan.status == "published" and any(available[s.throw_id]["gaps"] for s in plan.steps):
            raise HTTPException(422, "All plan steps need complete verified teaching")
        if any(not re.fullmatch(ID, key) for key in plan.counter_ids):
            raise HTTPException(422, "Invalid counter plan ID")
        store.put("plans", plan.id, plan.model_dump())
        return plan

    @app.post("/api/media")
    async def upload_media(asset: Annotated[UploadFile, File()]):
        suffix = Path(asset.filename or "").suffix.lower()
        if suffix not in (".png", ".jpg", ".jpeg", ".webp", ".mp4", ".webm"):
            raise HTTPException(422, "Use PNG, JPEG, WebP, MP4 or WebM")
        content = await asset.read(250 * 1024**2 + 1)
        if len(content) > 250 * 1024**2:
            raise HTTPException(413, "Media exceeds 250 MiB")
        valid = (
            suffix == ".png"
            and content.startswith(b"\x89PNG\r\n\x1a\n")
            or suffix in (".jpg", ".jpeg")
            and content.startswith(b"\xff\xd8\xff")
            or suffix == ".webp"
            and content.startswith(b"RIFF")
            and content[8:12] == b"WEBP"
            or suffix == ".mp4"
            and content[4:8] == b"ftyp"
            or suffix == ".webm"
            and content.startswith(b"\x1aE\xdf\xa3")
        )
        if not valid:
            raise HTTPException(422, "File content does not match the media type")
        name = hashlib.sha256(content).hexdigest() + suffix
        (root / "media" / name).write_bytes(content)
        return {"url": f"media/{name}"}

    @app.post("/api/export")
    def export():
        try:
            path = export_bundle(store, root / "exports")
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        shutil.make_archive(str(path), "zip", path)
        return {
            "version": path.name,
            "download": f"/api/exports/{path.name}",
            "manifest": json.loads((path / "manifest.json").read_text(encoding="utf-8")),
        }

    @app.get("/api/exports/{version}")
    def download_export(version: str):
        if not re.fullmatch(r"[a-f0-9]{12}", version):
            raise HTTPException(404, "Export not found")
        path = root / "exports" / f"{version}.zip"
        if not path.exists():
            raise HTTPException(404, "Export not found")
        return FileResponse(path, filename=f"openingroutes-{version}.zip")

    app.mount("/media", StaticFiles(directory=root / "media"), name="media")
    if web_root and web_root.is_dir():
        app.mount("/", StaticFiles(directory=web_root, html=True), name="web")
    return app
