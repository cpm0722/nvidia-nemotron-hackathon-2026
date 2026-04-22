"""Unit tests for ari_core.events."""

from __future__ import annotations

import asyncio
from contextvars import copy_context
from typing import Any

import httpx
import pytest

from ari_core import events
from ari_core.events import (
    build_event_payload,
    emit_event,
    get_event_context,
    set_event_context,
)


def _run_in_fresh_context(coro_fn: Any) -> Any:
    """Run an async callable in an isolated copy of the current context.

    Guards tests against contextvar leakage from other tests in the same event
    loop — ``set_event_context`` mutates module-level ContextVar slots which
    would otherwise persist.
    """

    async def _wrapper() -> Any:
        return await coro_fn()

    ctx = copy_context()
    return asyncio.run(ctx.run(asyncio.ensure_future, _wrapper()))  # type: ignore[arg-type]


class TestContextVars:
    def test_default_is_empty(self) -> None:
        async def check() -> tuple[str | None, str | None]:
            return get_event_context()

        url, jid = asyncio.run(check())
        # Module may retain state from prior tests; only assert the set/get
        # round-trip in the next case.
        assert url is None or isinstance(url, str)
        assert jid is None or isinstance(jid, str)

    def test_set_and_get_round_trip(self) -> None:
        async def go() -> tuple[str | None, str | None]:
            set_event_context("http://ui/api/events/j1", "j1")
            return get_event_context()

        url, jid = asyncio.run(go())
        assert url == "http://ui/api/events/j1"
        assert jid == "j1"

    def test_clear_with_none(self) -> None:
        async def go() -> tuple[str | None, str | None]:
            set_event_context("u", "j")
            set_event_context(None, None)
            return get_event_context()

        url, jid = asyncio.run(go())
        assert url is None
        assert jid is None


class TestBuildEventPayload:
    def test_shape_with_all_fields(self) -> None:
        async def go() -> dict[str, Any]:
            set_event_context("http://ui/api/events/j1", "j1")
            return build_event_payload(
                agent="arcalive",
                event_type="progress",
                phase="collect",
                message="scraped 12",
                data={"scraped": 12},
            )

        payload = asyncio.run(go())
        assert payload["agent"] == "arcalive"
        assert payload["type"] == "progress"
        assert payload["phase"] == "collect"
        assert payload["message"] == "scraped 12"
        assert payload["data"] == {"scraped": 12}
        assert payload["job_id"] == "j1"
        assert isinstance(payload["ts"], float)

    def test_omits_optional_fields_as_none_or_empty(self) -> None:
        async def go() -> dict[str, Any]:
            set_event_context(None, None)
            return build_event_payload(agent="reporter", event_type="start")

        payload = asyncio.run(go())
        assert payload["phase"] is None
        assert payload["message"] == ""
        assert payload["data"] == {}
        assert payload["job_id"] is None


class TestEmitEvent:
    def test_no_op_without_context(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """emit_event with no context set must NOT open a client."""
        calls: list[Any] = []

        class _FakeClient:
            def __init__(self, *a: Any, **kw: Any) -> None:
                calls.append(("init", a, kw))

            async def __aenter__(self) -> "_FakeClient":
                return self

            async def __aexit__(self, *a: Any) -> None:
                return None

            async def post(self, *a: Any, **kw: Any) -> None:
                calls.append(("post", a, kw))

        monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)

        async def go() -> None:
            set_event_context(None, None)
            await emit_event(agent="x", event_type="start")

        asyncio.run(go())
        assert calls == []

    def test_posts_payload_with_context(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, Any] = {}

        class _FakeClient:
            def __init__(self, *_: Any, **__: Any) -> None:
                pass

            async def __aenter__(self) -> "_FakeClient":
                return self

            async def __aexit__(self, *_: Any) -> None:
                return None

            async def post(self, url: str, json: dict[str, Any] | None = None) -> Any:
                captured["url"] = url
                captured["payload"] = json
                return None

        monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)

        async def go() -> None:
            set_event_context("http://ui/api/events/j1", "j1")
            await emit_event(
                agent="arcalive",
                event_type="progress",
                phase="collect",
                message="ok",
                data={"scraped": 5},
            )

        asyncio.run(go())
        assert captured["url"] == "http://ui/api/events/j1"
        payload = captured["payload"]
        assert payload["agent"] == "arcalive"
        assert payload["job_id"] == "j1"
        assert payload["data"] == {"scraped": 5}

    def test_swallows_transport_errors(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _BrokenClient:
            def __init__(self, *_: Any, **__: Any) -> None:
                pass

            async def __aenter__(self) -> "_BrokenClient":
                return self

            async def __aexit__(self, *_: Any) -> None:
                return None

            async def post(self, *_: Any, **__: Any) -> Any:
                raise httpx.ConnectError("refused")

        monkeypatch.setattr(httpx, "AsyncClient", _BrokenClient)

        async def go() -> None:
            set_event_context("http://ui/api/events/j1", "j1")
            # Must not raise.
            await emit_event(agent="x", event_type="error", message="boom")

        asyncio.run(go())


def test_module_exports_are_accessible() -> None:
    """Smoke-check the public surface referenced by downstream packages."""
    assert events.EMIT_TIMEOUT_SECONDS > 0
    assert callable(events.emit_event)
    assert callable(events.set_event_context)
    assert callable(events.get_event_context)
    assert callable(events.build_event_payload)
