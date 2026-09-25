"""
Background jobs: lifecycle, progress, cancellation, isolation.

Jobs run on real threads here rather than being mocked, so these exercise
the concurrency path the API actually uses.
"""

import time

import pytest
from fastapi.testclient import TestClient

import db
import jobs


@pytest.fixture
def client(temp_db, offline):
    """
    A signed-in client whose background jobs are drained on teardown.

    Draining matters: a job runs on a thread that outlives the test, so
    without this, monkeypatched functions revert while the thread is still
    running and it calls the real network-backed scanner. That leaks work
    between tests and makes them non-deterministic.
    """
    from api.main import app

    with TestClient(app) as c:
        r = c.post("/auth/register",
                   json={"username": "jobuser", "password": "job-pass-1234"})
        assert r.status_code == 201, r.text
        from api import security
        c.headers[security.CSRF_HEADER] = r.json()["csrf_token"]
        user_id = r.json()["user_id"]
        try:
            yield c
        finally:
            _drain(user_id)
    jobs.shutdown()


def _drain(user_id: int, timeout: float = 15.0) -> None:
    """Cancel anything still in flight and wait for the threads to notice."""
    for job in jobs.listing(user_id, limit=100):
        if job["status"] in ("queued", "running"):
            jobs.cancel(job["id"], user_id)

    deadline = time.time() + timeout
    while time.time() < deadline:
        pending = [j for j in jobs.listing(user_id, limit=100)
                   if j["status"] in ("queued", "running")]
        if not pending:
            return
        time.sleep(0.1)


def wait_for(client, job_id, statuses=("finished", "failed", "cancelled"), timeout=60):
    """Poll until the job settles, as a frontend would."""
    deadline = time.time() + timeout
    body = None
    while time.time() < deadline:
        body = client.get(f"/jobs/{job_id}").json()
        if body["status"] in statuses:
            return body
        time.sleep(0.1)
    raise AssertionError(f"job did not settle within {timeout}s: {body}")


# ── Lifecycle ─────────────────────────────────────────────────────────────────

def test_scan_returns_immediately_with_a_job_id(client, monkeypatch):
    """The request must not block for the length of the scan."""
    import scanner

    monkeypatch.setattr(scanner, "run_full_scan",
                        lambda **kw: (time.sleep(2), [])[1])

    started = time.time()
    r = client.post("/jobs/scan", json={"scope": "universe", "min_score": 55})
    elapsed = time.time() - started

    assert r.status_code == 202
    assert elapsed < 1.0, f"request blocked for {elapsed:.1f}s"
    body = r.json()
    assert body["status"] in ("queued", "running")
    assert body["id"]


def test_job_reaches_finished_with_results(client):
    job_id = client.post("/jobs/scan",
                         json={"scope": "universe", "min_score": 0}).json()["id"]
    body = wait_for(client, job_id)
    assert body["status"] == "finished", body.get("error")
    assert body["result"]["scope"] == "universe"
    assert isinstance(body["result"]["results"], list)
    assert body["finished_at"] is not None


def test_progress_is_reported_while_running(client, monkeypatch):
    """A client must be able to show something other than a spinner."""
    import scanner

    seen = []
    real = scanner.run_full_scan

    def slow(symbols=None, min_score=50, on_progress=None, should_cancel=None):
        for i, sym in enumerate(["AAPL", "NVDA", "MSFT"], start=1):
            time.sleep(0.4)
            if on_progress:
                on_progress(i, 3, sym)
        return []

    monkeypatch.setattr(scanner, "run_full_scan", slow)
    job_id = client.post("/jobs/scan", json={"scope": "universe"}).json()["id"]

    deadline = time.time() + 20
    while time.time() < deadline:
        body = client.get(f"/jobs/{job_id}").json()
        seen.append((body["progress"]["done"], body["progress"]["total"]))
        if body["status"] in ("finished", "failed"):
            break
        time.sleep(0.15)

    assert any(done > 0 and total == 3 for done, total in seen), seen
    assert max(d for d, _ in seen) == 3


def test_failure_surfaces_as_a_readable_error(client, monkeypatch):
    import scanner

    def boom(**kwargs):
        raise RuntimeError("upstream data provider is down")

    monkeypatch.setattr(scanner, "run_full_scan", boom)
    job_id = client.post("/jobs/scan", json={"scope": "universe"}).json()["id"]
    body = wait_for(client, job_id)

    assert body["status"] == "failed"
    assert "upstream data provider is down" in body["error"]
    assert body["result"] is None


def test_cancellation_stops_a_running_scan(client, monkeypatch):
    import scanner

    def slow(symbols=None, min_score=50, on_progress=None, should_cancel=None):
        for i in range(60):
            if should_cancel and should_cancel():
                raise scanner.ScanCancelled("stopped")
            time.sleep(0.15)
            if on_progress:
                on_progress(i + 1, 60, f"SYM{i}")
        return []

    monkeypatch.setattr(scanner, "run_full_scan", slow)
    job_id = client.post("/jobs/scan", json={"scope": "universe"}).json()["id"]

    time.sleep(0.6)
    assert client.delete(f"/jobs/{job_id}").status_code == 200
    body = wait_for(client, job_id, timeout=20)
    assert body["status"] == "cancelled"


def test_cancelling_a_finished_job_is_409(client):
    job_id = client.post("/jobs/scan",
                         json={"scope": "universe", "min_score": 0}).json()["id"]
    wait_for(client, job_id)
    r = client.delete(f"/jobs/{job_id}")
    assert r.status_code == 409


def test_listing_shows_recent_jobs(client):
    ids = {client.post("/jobs/scan", json={"scope": "universe", "min_score": 0}).json()["id"]
           for _ in range(2)}
    for job_id in ids:
        wait_for(client, job_id)
    listed = {j["id"] for j in client.get("/jobs").json()}
    assert ids <= listed


# ── Access control ────────────────────────────────────────────────────────────

def test_jobs_require_auth(temp_db, offline):
    from api.main import app

    with TestClient(app) as anon:
        assert anon.post("/jobs/scan", json={"scope": "universe"}).status_code == 401
        assert anon.get("/jobs").status_code == 401


def test_one_account_cannot_read_anothers_job(client, temp_db, offline):
    """404, not 403 — the endpoint must not confirm the job exists."""
    from api.main import app
    from api import security

    job_id = client.post("/jobs/scan",
                         json={"scope": "universe", "min_score": 0}).json()["id"]

    with TestClient(app) as other:
        r = other.post("/auth/register",
                       json={"username": "intruder", "password": "intruder-pass-1"})
        other.headers[security.CSRF_HEADER] = r.json()["csrf_token"]
        assert other.get(f"/jobs/{job_id}").status_code == 404
        assert other.delete(f"/jobs/{job_id}").status_code == 404

    wait_for(client, job_id)


def test_unknown_job_is_404(client):
    assert client.get("/jobs/does-not-exist").status_code == 404


# ── Restart handling ──────────────────────────────────────────────────────────

def test_stale_jobs_are_failed_on_startup(temp_db):
    """
    A job left 'running' by a dead process would otherwise spin forever in
    the UI, because nothing remains to update it.
    """
    import auth

    uid = auth.register("orphan", "o@x.co", "orphan-pass-1")
    db.create_job("stale-job-id", uid, "scan", {"scope": "universe"})
    db.start_job("stale-job-id")
    assert db.get_job("stale-job-id", uid)["status"] == "running"

    # stale_seconds=0 makes every running job look abandoned
    assert db.reap_orphaned_jobs(stale_seconds=0) >= 1
    after = db.get_job("stale-job-id", uid)
    assert after["status"] == "failed"
    assert "restart" in after["error"].lower()


def test_healthy_jobs_are_not_reaped(temp_db):
    """
    Regression: reaping every 'running' job meant a second worker booting
    would kill jobs the first worker was still running happily.
    """
    import auth

    uid = auth.register("healthy", "h@x.co", "healthy-pass-1")
    db.create_job("live-job-id", uid, "scan", {"scope": "universe"})
    db.start_job("live-job-id")
    db.update_job_progress("live-job-id", 3, 10, "AAPL")   # fresh heartbeat

    assert db.reap_orphaned_jobs() == 0, "a live job was reaped"
    assert db.get_job("live-job-id", uid)["status"] == "running"


# ── Scanner callbacks ─────────────────────────────────────────────────────────

def test_scanner_reports_progress_per_symbol(offline):
    from scanner import run_full_scan

    seen = []
    run_full_scan(["AAPL", "NVDA"], min_score=0,
                  on_progress=lambda d, t, s: seen.append((d, t, s)))
    assert seen == [(1, 2, "AAPL"), (2, 2, "NVDA")]


def test_scanner_honours_cancellation(offline):
    from scanner import ScanCancelled, run_full_scan

    with pytest.raises(ScanCancelled):
        run_full_scan(["AAPL", "NVDA", "MSFT"], min_score=0,
                      should_cancel=lambda: True)


def test_scan_without_callbacks_still_works(offline):
    """The Streamlit app calls this with no callbacks at all."""
    from scanner import run_full_scan

    assert isinstance(run_full_scan(["AAPL"], min_score=0), list)


def test_sync_scan_endpoint_is_marked_deprecated():
    """It must stay discouraged so no client builds against it."""
    from api.main import app

    assert app.openapi()["paths"]["/scan"]["post"].get("deprecated") is True
