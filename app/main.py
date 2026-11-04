"""IntelliLead AI — FastAPI application entry point.

Phase 3 — adds PostgreSQL persistence layer alongside the in-memory job store.
The in-memory JOBS dict is kept as the primary job store until the full
dual-write / read switchover is validated in Phase 4.  The DB engine is
initialised at startup and shut down cleanly at shutdown via the lifespan hook.
"""
from __future__ import annotations

import asyncio
import io
import logging
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator

import pandas as pd
from fastapi import FastAPI, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import get_settings
from .export import to_csv_bytes, to_excel_bytes
from .ingestion import load_companies
from .pipeline import run_pipeline

log = logging.getLogger(__name__)

# ── Settings ─────────────────────────────────────────────────────────────────

settings = get_settings()

# ── Database (optional — graceful if not configured) ─────────────────────────

_db_engine = None
_db_session_factory = None
_db_ok = False


def _init_db():
    """Try to initialise the async SQLAlchemy engine.  Does NOT raise."""
    global _db_engine, _db_session_factory, _db_ok
    try:
        from .database.config import DatabaseSettings
        from .database.session import build_engine, build_session_factory

        db_settings = DatabaseSettings.from_env()
        _db_engine = build_engine(db_settings)
        _db_session_factory = build_session_factory(_db_engine)
        _db_ok = True
        log.info("Database engine initialised: %s", db_settings.database_url.split("@")[-1])
    except Exception as exc:  # pragma: no cover
        log.warning("Database unavailable — running in memory-only mode: %s", exc)
        _db_ok = False


async def _dispose_db():
    """Dispose the async engine if it was created."""
    global _db_engine, _db_ok
    if _db_engine is not None:
        await _db_engine.dispose()
        _db_engine = None
    _db_ok = False


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown hook wired to FastAPI lifespan."""
    _init_db()
    log.info("IntelliLead AI %s starting (db_ok=%s)", __version__, _db_ok)
    yield
    await _dispose_db()
    log.info("IntelliLead AI shutdown complete")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="IntelliLead AI",
    version=__version__,
    description="Company intelligence engine: crawl → detect → enrich → export.",
    lifespan=lifespan,
)

_STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=_STATIC), name="static")


# ── In-memory job store (MVP — replaced by PostgreSQL in Phase 4) ─────────────

@dataclass
class Job:
    id: str
    status: str = "queued"          # queued | running | done | failed
    total: int = 0
    done: int = 0
    stats: dict = field(default_factory=dict)
    error: str | None = None
    created_at: str = ""
    results: pd.DataFrame | None = None
    rejected: pd.DataFrame | None = None


JOBS: dict[str, Job] = {}
_TASKS: set[asyncio.Task] = set()


async def _run(job: Job, companies: pd.DataFrame) -> None:
    job.status = "running"
    try:
        def tick():
            job.done += 1

        job.results = await run_pipeline(companies, settings, on_progress=tick)
        job.status = "done"
    except Exception as exc:                   # noqa: BLE001
        job.status = "failed"
        job.error = type(exc).__name__
        log.exception("Job %s failed", job.id)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
def root() -> FileResponse:
    return FileResponse(_STATIC / "index.html")


@app.get("/health", tags=["system"])
async def health():
    """Liveness + readiness probe. Returns DB connectivity status."""
    db_connected = False
    if _db_engine is not None:
        try:
            async with asyncio.timeout(1.0):
                async with _db_engine.connect() as conn:
                    from sqlalchemy import text
                    await conn.execute(text("SELECT 1"))
                    db_connected = True
        except Exception:
            db_connected = False
    return {
        "status": "ok",
        "version": __version__,
        "db_ok": _db_ok,
        "db_connected": db_connected,
        "jobs_in_memory": len(JOBS),
    }


@app.get("/v1/samples/companies.csv", tags=["system"])
def download_sample_csv():
    """Provide sample CSV containing real company domains for quick testing."""
    sample_path = Path(__file__).parent.parent / "data" / "sample_companies.csv"
    if not sample_path.exists():
        raise HTTPException(404, "Sample CSV not found")
    return FileResponse(
        sample_path,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="sample_companies.csv"'},
    )


@app.post("/v1/jobs", status_code=202, tags=["jobs"])
async def create_job(file: UploadFile):
    """Accept a CSV upload, validate it, and enqueue a crawl job."""
    raw = await file.read()
    if len(raw) > settings.max_upload_bytes:
        raise HTTPException(413, f"File larger than {settings.max_upload_bytes} bytes")

    try:
        ing = load_companies(io.BytesIO(raw), max_rows=settings.max_rows)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    if ing.valid.empty:
        raise HTTPException(422, "No valid domains found in the file")

    job = Job(
        id=uuid.uuid4().hex,
        total=len(ing.valid),
        stats=ing.stats,
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        rejected=ing.rejected,
    )
    JOBS[job.id] = job
    task = asyncio.create_task(_run(job, ing.valid))
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)

    return {
        "job_id": job.id,
        "accepted": len(ing.valid),
        "rejected": len(ing.rejected),
        "stats": ing.stats,
    }


def _get_job(job_id: str) -> Job:
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, "Unknown job")
    return job


@app.get("/v1/jobs/{job_id}", tags=["jobs"])
def job_status(job_id: str):
    """Return current status and progress for a job."""
    j = _get_job(job_id)
    return {
        "job_id": j.id,
        "status": j.status,
        "progress": f"{j.done}/{j.total}",
        "stats": j.stats,
        "error": j.error,
        "created_at": j.created_at,
    }


@app.get("/v1/jobs/{job_id}/results", tags=["jobs"])
def job_results(
    job_id: str,
    limit: int = Query(100, ge=1, le=1000),
):
    """Stream enriched results as JSON.  Job must be in ``done`` status."""
    j = _get_job(job_id)
    if j.status != "done":
        raise HTTPException(409, f"Job is {j.status}")
    return j.results.head(limit).to_dict("records")


@app.get("/v1/jobs/{job_id}/download", tags=["jobs"])
def job_download(
    job_id: str,
    format: str = Query("csv", pattern="^(csv|xlsx)$"),
):
    """Download enriched results as CSV or Excel (with rejected-rows sheet)."""
    j = _get_job(job_id)
    if j.status != "done":
        raise HTTPException(409, f"Job is {j.status}")

    stem = f"intellilead_{j.id[:8]}"
    if format == "csv":
        return Response(
            to_csv_bytes(j.results),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{stem}.csv"'},
        )
    return Response(
        to_excel_bytes(j.results, j.rejected),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{stem}.xlsx"'},
    )
