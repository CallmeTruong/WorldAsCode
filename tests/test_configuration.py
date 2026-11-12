import json

import httpx
import pytest


def test_toml_models_endpoints_and_relative_paths_are_portable(tmp_path, monkeypatch):
    from worldascode.config import Settings, paths

    config = tmp_path / "config" / "worldascode.toml"
    config.parent.mkdir()
    config.write_text(
        """[paths]
data_dir = "state"
node_modules = "../toolchain"
[llm]
default_provider = "primary"
timeout_seconds = 17
[llm.providers.primary]
base_url = "https://primary.test/v1"
api_key_env = "TEST_PRIMARY_KEY"
[llm.providers.review]
base_url = "https://review.test/v1"
api_key_env = "TEST_REVIEW_KEY"
[models]
default = "coding-model"
critic = "review-model"
[model_providers]
critic = "review"
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("WORLDASCODE_CONFIG", str(config))
    monkeypatch.setenv("TEST_PRIMARY_KEY", "primary-secret")
    monkeypatch.setenv("TEST_REVIEW_KEY", "review-secret")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("WORLDASCODE_DATA_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    settings = Settings.load()
    assert settings.for_node("author-0").model == "coding-model"
    critic = settings.for_node("kit-candidate-critic-0")
    assert (
        critic.model == "review-model" and critic.base_url == "https://review.test/v1"
    )
    assert critic.api_key == "review-secret" and critic.timeout_seconds == 17
    assert paths().data_dir == config.parent / "state"
    assert paths().node_modules == tmp_path / "toolchain"


def test_role_routing_reaches_transport_without_persisting_credentials(
    tmp_path, monkeypatch
):
    from worldascode.adapters.llm.transport import Provider
    from worldascode.config import Settings

    monkeypatch.setenv("WORLDASCODE_DATA_DIR", str(tmp_path))
    settings = Settings(
        "https://base.test/v1",
        "base-key",
        role_models={"critic": "review-model"},
        providers={
            "review": {
                "base_url": "https://review.test/v1",
                "api_key_env": "TEST_REVIEW_KEY",
            }
        },
        role_providers={"critic": "review"},
    )
    monkeypatch.setenv("TEST_REVIEW_KEY", "never-log-this")
    original = httpx.Client
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": '{"ok":true}'}, "finish_reason": "stop"}
                ],
                "usage": {"prompt_tokens": 5, "completion_tokens": 4},
            },
        )

    monkeypatch.setattr(
        "worldascode.adapters.llm.transport.httpx.Client",
        lambda **kw: original(transport=httpx.MockTransport(respond), **kw),
    )
    provider = Provider(settings, tmp_path / "run")
    assert provider.call("critic-0", "review") == {"ok": True}
    assert str(requests[0].url) == "https://review.test/v1/chat/completions"
    assert json.loads(requests[0].content)["model"] == "review-model"
    assert requests[0].headers["authorization"] == "Bearer never-log-this"
    for path in (tmp_path / "run").rglob("*.json"):
        assert "never-log-this" not in path.read_text()


def test_unknown_configuration_key_is_reported(tmp_path, monkeypatch):
    from worldascode.config import Settings

    config = tmp_path / "bad.toml"
    config.write_text('[models]\ndefualt="typo"')
    monkeypatch.setenv("WORLDASCODE_CONFIG", str(config))
    with pytest.raises(ValueError, match="CONFIG"):
        Settings.load()


@pytest.mark.parametrize(
    "content",
    [
        '[llm]\ndefault_provider="missing"',
        '[llm]\nproviders="wrong-type"',
        "[models]\nauthor=17",
        "[budgets]\nmax_revisions=-1",
        "[capture]\nwidth=0",
    ],
)
def test_invalid_configuration_fails_before_running_jobs(
    content, tmp_path, monkeypatch
):
    from worldascode.config import configuration

    config = tmp_path / "invalid.toml"
    config.write_text(content, encoding="utf-8")
    monkeypatch.setenv("WORLDASCODE_CONFIG", str(config))
    with pytest.raises(ValueError, match="CONFIG"):
        configuration()
