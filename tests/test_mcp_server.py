import asyncio

import pytest

mcp_server = pytest.importorskip("goodnotes_ocr.mcp_server")


def _run(calls, monkeypatch, limit=3):
    """Run each call through _guarded and return (results, exit codes requested)."""
    exits = []
    monkeypatch.setattr(mcp_server, "BROWSER_STALL_RESTART", limit)
    monkeypatch.setattr(mcp_server, "_stalls", 0)
    monkeypatch.setattr(mcp_server.os, "_exit", exits.append)

    async def go():
        results = [await mcp_server._guarded(call) for call in calls]
        await asyncio.sleep(1.1)
        return results

    return asyncio.run(go()), exits


async def _timeout():
    raise mcp_server.PlaywrightTimeoutError("Page.screenshot: Timeout 90000ms exceeded.")


async def _ok():
    return {"status": "ok"}


def test_restarts_after_limit_timeouts_in_a_row(monkeypatch):
    results, exits = _run([_timeout, _timeout, _timeout], monkeypatch)
    assert exits == [75]
    assert all("error" in r for r in results)
    assert "restarting" in results[-1]["error"]
    assert "restarting" not in results[1]["error"]


def test_success_resets_the_count(monkeypatch):
    results, exits = _run([_timeout, _timeout, _ok, _timeout, _timeout], monkeypatch)
    assert exits == []
    assert results[2] == {"status": "ok"}


def test_zero_turns_restart_off(monkeypatch):
    _, exits = _run([_timeout] * 5, monkeypatch, limit=0)
    assert exits == []


def test_value_errors_still_become_error_results(monkeypatch):
    def bad():
        raise ValueError("`page` must be a single page number or 'last'.")

    results, exits = _run([bad], monkeypatch)
    assert results == [{"error": "`page` must be a single page number or 'last'."}]
    assert exits == []


def test_extract_scale_is_separate_from_drawing_scale(monkeypatch):
    monkeypatch.delenv("DEVICE_SCALE_FACTOR", raising=False)
    monkeypatch.delenv("EXTRACT_DEVICE_SCALE_FACTOR", raising=False)
    assert mcp_server._browser_options().device_scale_factor == 2.0
    assert mcp_server._browser_options(extract=True).device_scale_factor == 2.0

    monkeypatch.setenv("EXTRACT_DEVICE_SCALE_FACTOR", "1.0")
    assert mcp_server._browser_options(extract=True).device_scale_factor == 1.0
    assert mcp_server._browser_options().device_scale_factor == 2.0
