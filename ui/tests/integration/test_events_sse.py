"""Integration tests for the /api/events and /api/chat/{job_id}/stream endpoints."""

from __future__ import annotations

import json
import os

import pytest

os.environ.setdefault("NAT_UI_STUB", "1")

from fastapi.testclient import TestClient  # noqa: E402  (import after env setup)

from nat_ui import server  # noqa: E402


@pytest.fixture()
def client() -> TestClient:
    """Fresh TestClient per test + wipe the in-memory JOBS dict."""
    server.JOBS.clear()
    return TestClient(server.app)


def _parse_sse_frames(body: str) -> list[dict]:
    """Extract JSON payloads from SSE ``data:`` frames, ignoring keep-alives."""
    frames: list[dict] = []
    for line in body.splitlines():
        if line.startswith("data:"):
            payload = line[len("data:"):].strip()
            if not payload:
                continue
            frames.append(json.loads(payload))
    return frames


def _make_job(client: TestClient) -> str:
    """Create a job directly in the JOBS dict so tests don't race the stub runner."""
    job = server.Job(id="test-job-1", query="opus 4.7 review")
    server.JOBS[job.id] = job
    return job.id


class TestPostEvent:
    def test_rejects_unknown_job(self, client: TestClient) -> None:
        resp = client.post("/api/events/does-not-exist", json={"type": "start"})
        assert resp.status_code == 404

    def test_rejects_non_json_body(self, client: TestClient) -> None:
        job_id = _make_job(client)
        resp = client.post(
            f"/api/events/{job_id}",
            content="not json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code in (400, 422)

    def test_rejects_non_object_payload(self, client: TestClient) -> None:
        job_id = _make_job(client)
        resp = client.post(f"/api/events/{job_id}", json=["list", "not", "object"])
        assert resp.status_code == 400

    def test_accepts_event_and_appends_to_buffer(self, client: TestClient) -> None:
        job_id = _make_job(client)
        event = {
            "ts": 1.0,
            "agent": "arcalive",
            "type": "progress",
            "phase": "collect",
            "message": "scraped 12",
            "data": {"scraped": 12},
        }
        resp = client.post(f"/api/events/{job_id}", json=event)
        assert resp.status_code == 202
        job = server.JOBS[job_id]
        assert job.events == [event]
        # progress event surfaces the pill as working until complete/error.
        assert job.agents["arcalive"] == "working"

    def test_complete_event_flips_pill_to_done(self, client: TestClient) -> None:
        job_id = _make_job(client)
        client.post(
            f"/api/events/{job_id}",
            json={"agent": "reporter", "type": "complete", "message": "done"},
        )
        assert server.JOBS[job_id].agents["reporter"] == "done"

    def test_error_event_flips_pill_to_error(self, client: TestClient) -> None:
        job_id = _make_job(client)
        client.post(
            f"/api/events/{job_id}",
            json={"agent": "arxiv", "type": "error", "message": "timeout"},
        )
        assert server.JOBS[job_id].agents["arxiv"] == "error"

    def test_unknown_agent_ignored_but_event_stored(self, client: TestClient) -> None:
        job_id = _make_job(client)
        resp = client.post(
            f"/api/events/{job_id}",
            json={"agent": "mystery-agent", "type": "start"},
        )
        assert resp.status_code == 202
        # Still logged on the event buffer even if agent isn't a known pill.
        assert len(server.JOBS[job_id].events) == 1


class TestSseStream:
    def test_replays_buffered_events_on_connect(self, client: TestClient) -> None:
        job_id = _make_job(client)
        client.post(
            f"/api/events/{job_id}",
            json={"agent": "arcalive", "type": "start", "message": "scraping"},
        )
        client.post(
            f"/api/events/{job_id}",
            json={"agent": "arcalive", "type": "complete", "message": "12 items"},
        )
        # Add a terminal job-end event so the stream closes deterministically.
        server._publish_event(
            server.JOBS[job_id],
            {"agent": None, "type": "complete", "message": "pipeline done"},
        )

        with client.stream("GET", f"/api/chat/{job_id}/stream") as resp:
            assert resp.status_code == 200
            body = "".join(resp.iter_text())
        frames = _parse_sse_frames(body)
        # 2 agent events + 1 pipeline-terminal event.
        assert len(frames) == 3
        assert frames[0]["agent"] == "arcalive"
        assert frames[0]["type"] == "start"
        assert frames[-1]["agent"] is None
        assert frames[-1]["type"] == "complete"

    def test_unknown_job_returns_404(self, client: TestClient) -> None:
        resp = client.get("/api/chat/nope/stream")
        assert resp.status_code == 404

    def test_status_endpoint_returns_events_array(self, client: TestClient) -> None:
        job_id = _make_job(client)
        client.post(
            f"/api/events/{job_id}",
            json={"agent": "reddit", "type": "start", "message": "go"},
        )
        resp = client.get(f"/api/chat/{job_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["events"]) == 1
        assert body["events"][0]["agent"] == "reddit"
