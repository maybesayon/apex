"""
Job endpoints.

The client flow the migration plan asked for:

    POST /jobs/scan   -> 202 {id, status: "queued"}
    GET  /jobs/{id}   -> progress while running, result when finished
    DELETE /jobs/{id} -> request cancellation
"""

from fastapi import APIRouter, HTTPException, Query, status

import jobs
from api.deps import CurrentUser
from api.schemas import JobResponse, ScanRequest

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("/scan", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
def start_scan(body: ScanRequest, user: CurrentUser):
    """
    Start a market scan and return immediately.

    Measured: ~21s for the personal universe, ~46s broad. Both are past
    what an HTTP request should hold open, so this never runs inline.
    Poll GET /jobs/{id} for progress.
    """
    record = jobs.submit(user["user_id"], "scan",
                         scope=body.scope, min_score=body.min_score)
    return JobResponse(**record)


@router.get("", response_model=list[JobResponse])
def list_jobs(user: CurrentUser, limit: int = Query(20, ge=1, le=100)):
    return [JobResponse(**j) for j in jobs.listing(user["user_id"], limit)]


@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: str, user: CurrentUser):
    """
    Poll a job. 404 covers both 'no such job' and 'not yours', so the
    endpoint cannot be used to discover that another account's job exists.
    """
    record = jobs.get(job_id, user["user_id"])
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such job")
    return JobResponse(**record)


@router.delete("/{job_id}", response_model=JobResponse)
def cancel_job(job_id: str, user: CurrentUser):
    """
    Request cancellation. A running scan stops at the next symbol
    boundary — the work in between is a blocking network call.
    """
    if not jobs.cancel(job_id, user["user_id"]):
        existing = jobs.get(job_id, user["user_id"])
        if existing is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such job")
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Job is already {existing['status']} and cannot be cancelled",
        )
    return JobResponse(**jobs.get(job_id, user["user_id"]))
