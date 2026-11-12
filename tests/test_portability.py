import json
import threading

import httpx


def test_regression_worker_inherits_config_discovery_directory(tmp_path, monkeypatch):
    from worldascode.execution.regression_worker import regressions

    calls = []

    class Process:
        returncode = 2

        def __init__(self, command, **options):
            calls.append(options)

        def communicate(self, **options):
            return "", "expected fixture failure"

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "worldascode.execution.regression_worker.subprocess.Popen", Process
    )
    assert regressions(tmp_path / "kit.mjs", tmp_path / "report")[0]["passed"] is False
    assert calls[0].get("cwd") is None


def test_ast_method_boundaries_preserve_unicode_and_layout():
    from worldascode.kits.code import method_blocks

    source = "// 🏙️ Unicode before the class\nclass Builder {\n roof (o={}) { return o; }\n finish(){return true;}\n}\n"
    blocks = method_blocks(source)
    assert blocks["roof"].strip() == "roof (o={}) { return o; }"
    assert "finish(){return true;}" in blocks["finish"]


def test_packaged_reference_service_without_legacy_server_or_real_credentials():
    from worldascode.adapters.geospatial.reference_server import create_server

    with create_server(1, 2, "test-token", port=0) as server:
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}"
            assert httpx.get(url + "/").status_code == 200
            assert httpx.get(url + "/config").json()["ionToken"] == "test-token"
            assert (
                "configureEvidenceCapture"
                in httpx.get(url + "/google-reference.js").text
            )
            assert (
                httpx.get(
                    url + "/config", headers={"Host": "attacker.example"}
                ).status_code
                == 403
            )
            assert httpx.get(url + "/cesium/../../config.py").status_code == 404
        finally:
            server.shutdown()
            worker.join()


def test_cli_quality_exit_and_status_axes_are_consistent(tmp_path, monkeypatch, capsys):
    from worldascode.cli.main import main
    from worldascode.config import Settings

    image = tmp_path / "style.png"
    image.touch()
    monkeypatch.setattr(
        Settings, "load", lambda: Settings("https://test.invalid/v1", "test")
    )
    monkeypatch.setattr(
        "worldascode.workflows.reconstruction.run_design",
        lambda *a, **kw: {"status": "designed", "accepted": False},
    )
    command = [
        "design",
        "--evidence",
        str(tmp_path),
        "--styles",
        str(tmp_path),
        "--run",
        str(tmp_path / "run"),
    ]
    assert main(command) == 0
    result = json.loads(capsys.readouterr().out)
    assert (
        result["execution_status"] == "completed"
        and result["quality_status"] == "rejected"
    )
    assert main(command + ["--require-quality"]) == 2
