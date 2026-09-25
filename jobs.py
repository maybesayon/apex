"""
Background jobs.

WHY NOT REDIS + RQ (yet)
------------------------
The migration plan called for Redis + RQ. This ships a thread-pool
executor instead, for two reasons:

  1. Cost. Redis is a paid add-on almost everywhere. The only work that
     currently needs a job is the broad scan — a single user action taking
     ~46 seconds, run occasionally. Paying for a message broker to move
     one task an hour is the wrong trade at this stage.

  2. Nothing is lost by waiting. Job *state* lives in the database, which
     is where it belongs regardless of executor: progress is readable from
     any process, survives a restart, and leaves a history. RQ's own
     result store would not give that. Swapping the executor later means
     implementing `submit()` against RQ and changing one setting — the
     API, the schema and the frontend do not move.

WHAT YOU GIVE UP
----------------
  * Jobs run inside the API process, so a deploy or crash kills a running
    scan. `db.reap_orphaned_jobs()` marks those failed on startup rather
    than leaving them spinning forever in the UI.
  * No retries, no scheduled jobs, no scaling workers independently.
  * Concurrency is bounded by MAX_WORKERS in this one process.

Those are acceptable for one ~46s task. They stop being acceptable when
jobs become frequent, must survive deploys, or need retrying — at which
point implement RQExecutor below and set APEX_JOB_BACKEND=rq.
"""

import os
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor

import db

MAX_WORKERS = int(os.environ.get("APEX_JOB_WORKERS", "2"))
JOB_BACKEND = os.environ.get("APEX_JOB_BACKEND", "thread").strip().lower()

_executor: ThreadPoolExecutor | None = None
_lock = threading.Lock()


def _pool() -> ThreadPoolExecutor:
    global _executor
    with _lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(
                max_workers=MAX_WORKERS, thread_name_prefix="apex-job")
        return _executor


def startup() -> int:
    """
    Called when the API starts. Any job still marked running belongs to a
    process that no longer exists.
    """
    return db.reap_orphaned_jobs()


def shutdown() -> None:
    global _executor
    with _lock:
        if _executor is not None:
            _executor.shutdown(wait=False, cancel_futures=True)
            _executor = None


# ── Job bodies ────────────────────────────────────────────────────────────────

def _run_scan(job_id: str, scope: str, min_score: int) -> None:
    """Executed on a worker thread. Never raises into the pool."""
    from api.serialization import to_jsonable
    from scanner import ScanCancelled, run_broad_scan, run_full_scan

    def on_progress(done, total, label):
        db.update_job_progress(job_id, done, total, str(label))

    def should_cancel():
        return db.is_cancel_requested(job_id)

    try:
        db.start_job(job_id)
        if scope == "broad":
            results = run_broad_scan(min_score=min_score, on_progress=on_progress,
                                     should_cancel=should_cancel)
        else:
            results = run_full_scan(min_score=min_score, on_progress=on_progress,
                                    should_cancel=should_cancel)
        db.finish_job(job_id, {"scope": scope, "count": len(results),
                               "results": to_jsonable(results)})
    except ScanCancelled:
        db.mark_job_cancelled(job_id)
    except Exception as exc:
        # A traceback in the log, a readable sentence for the client.
        traceback.print_exc()
        db.fail_job(job_id, f"{type(exc).__name__}: {exc}")


JOB_KINDS = {"scan": _run_scan}


# ── Public API ────────────────────────────────────────────────────────────────

def submit(user_id: int, kind: str, **params) -> dict:
    """
    Queue a job and return its record immediately.

    The caller gets a job id straight away; the work happens elsewhere.
    That is the whole point — a 46-second scan must never block an HTTP
    request.
    """
    if kind not in JOB_KINDS:
        raise ValueError(f"Unknown job kind {kind!r}")

    job_id = uuid.uuid4().hex
    record = db.create_job(job_id, user_id, kind, params)

    if JOB_BACKEND == "rq":  # pragma: no cover - not implemented yet
        raise NotImplementedError(
            "APEX_JOB_BACKEND=rq is not implemented. Implement RQ submission "
            "here and run a worker against the same database; the job schema "
            "and API do not change."
        )

    _pool().submit(JOB_KINDS[kind], job_id, **params)
    return record


def get(job_id: str, user_id: int) -> dict | None:
    return db.get_job(job_id, user_id)


def listing(user_id: int, limit: int = 20) -> list[dict]:
    return db.list_jobs(user_id, limit)


def cancel(job_id: str, user_id: int) -> bool:
    """
    Request cancellation. A queued job stops immediately; a running one
    stops at the next symbol boundary, because the work in between is a
    blocking network call that cannot be interrupted safely.
    """
    return db.request_cancel(job_id, user_id)
