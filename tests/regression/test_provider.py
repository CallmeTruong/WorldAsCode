import json

import httpx
import pytest

import worldascode.adapters.llm.transport as transport
from worldascode.adapters.llm.transport import BudgetExceeded, Provider
from worldascode.config import Settings


def mock_client(monkeypatch, handler):
    original = httpx.Client
    monkeypatch.setattr(
        transport.httpx,
        "Client",
        lambda **kw: original(transport=httpx.MockTransport(handler), **kw),
    )


def test_streamed_json_usage_and_content_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("WORLDASCODE_DATA_DIR", str(tmp_path))
    calls = []

    def handler(request):
        calls.append(request)
        body = json.loads(request.content)
        assert body["stream"] is True
        packets = [
            {"choices": [{"delta": {"content": '{"ok":'}, "finish_reason": None}]},
            {"choices": [{"delta": {"content": "true}"}, "finish_reason": "stop"}]},
            {"choices": [], "usage": {"prompt_tokens": 12, "completion_tokens": 6}},
        ]
        text = (
            "".join("data: " + json.dumps(p) + "\n\n" for p in packets)
            + "data: [DONE]\n\n"
        )
        return httpx.Response(
            200, text=text, headers={"content-type": "text/event-stream"}
        )

    mock_client(monkeypatch, handler)
    p = Provider(
        Settings("https://example.test/v1", "do-not-persist-this"), tmp_path / "run"
    )
    assert p.call("node", "prompt") == {"ok": True}
    assert p.call("node", "prompt") == {"ok": True}
    assert (
        len(calls) == 1 and p.usage["input_tokens"] == 12 and p.usage["cache_hits"] == 1
    )
    assert p.usage["unknown_token_reserve"] == 0 and p.usage["cost_usd"] is None
    for file in (tmp_path / "run").rglob("*.json"):
        assert "do-not-persist-this" not in file.read_text()


def test_proxy_timeout_is_reserved_not_blindly_retried(monkeypatch, tmp_path):
    monkeypatch.setenv("WORLDASCODE_DATA_DIR", str(tmp_path))
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(524, text="proxy timeout")

    mock_client(monkeypatch, handler)
    p = Provider(
        Settings("https://example.test/v1", "secret"), tmp_path / "run", max_calls=1
    )
    with pytest.raises(RuntimeError, match="HTTP_524"):
        p.call("node", "prompt")
    assert (
        len(calls) == 1
        and p.usage["unknown_token_reserve"] > 0
        and p.usage["cost_usd"] is None
    )
    with pytest.raises(BudgetExceeded):
        p.call("node", "different prompt")
    assert len(calls) == 1


def test_missing_stream_termination_is_not_success(monkeypatch, tmp_path):
    monkeypatch.setenv("WORLDASCODE_DATA_DIR", str(tmp_path))
    mock_client(
        monkeypatch,
        lambda _: httpx.Response(
            200,
            text='data: {"choices":[{"delta":{"content":"{}"}}]}\n\ndata: [DONE]\n\n',
            headers={"content-type": "text/event-stream"},
        ),
    )
    p = Provider(Settings("https://example.test/v1", "secret"), tmp_path / "run")
    with pytest.raises(RuntimeError, match="INCOMPLETE"):
        p.call("node", "prompt")
    assert p.usage["unknown_token_reserve"] > 0
