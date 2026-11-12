from pathlib import Path

import pytest


def test_paths_are_explicit_and_never_depend_on_research_checkout(
    tmp_path, monkeypatch
):
    from worldascode.config import WorkspacePaths

    monkeypatch.chdir(tmp_path)
    paths = WorkspacePaths.from_environment(
        {
            "WORLDASCODE_DATA_DIR": str(tmp_path / "state"),
            "WORLDASCODE_NODE_MODULES": str(tmp_path / "toolchain"),
        }
    )
    assert paths.data_dir == tmp_path / "state"
    assert paths.cache_dir.is_relative_to(paths.data_dir)
    assert paths.node_modules == tmp_path / "toolchain"
    assert paths.runtime_dir.is_dir()
    assert "workflow_scale_research" not in str(paths.runtime_dir)


@pytest.mark.parametrize(
    "record,execution,quality",
    [
        ({"status": "designed", "accepted": False}, "completed", "rejected"),
        ({"status": "designed", "accepted": True}, "completed", "accepted"),
        (
            {"status": "incomplete-run-retained", "accepted": False},
            "interrupted",
            "unreviewed",
        ),
        ({"status": "no-buildable-design", "accepted": False}, "failed", "unreviewed"),
    ],
)
def test_execution_completion_is_distinct_from_visual_acceptance(
    record, execution, quality
):
    from worldascode.contracts.execution import RunOutcome

    outcome = RunOutcome.from_legacy(record)
    assert outcome.execution_status == execution and outcome.quality_status == quality
    assert outcome.exit_code(require_quality=True) == (
        0 if quality == "accepted" and execution == "completed" else 2
    )
    assert outcome.exit_code() == (0 if execution == "completed" else 2)


def test_unavailable_stable_channel_is_not_reported_as_stable(tmp_path):
    from worldascode.kits.registry import KitRegistry

    registry = KitRegistry(tmp_path / "library")
    registry.initialize()
    with pytest.raises(ValueError, match="CHANNEL_UNAVAILABLE"):
        registry.resolve(channel="stable")


def test_javascript_analysis_handles_method_formatting_and_reports_dynamic_access():
    from worldascode.kits.code import analyze_source

    source = "class Builder {\n roof ( options = {} )\n { return this.helper(options); }\n helper(x){return x;}\n}\n"
    report = analyze_source(source)
    assert set(report["methods"]) == {"roof", "helper"}
    assert report["methods"]["roof"]["dependencies"] == ["helper"]
    assert "roof" in report["public_methods"]
    assert analyze_source("export function design(site,b){b[site.method]();}")[
        "dynamic_api_access"
    ]


def test_no_research_application_imports_in_system_source():
    source = Path(__file__).resolve().parents[1] / "src/worldascode"
    if not source.exists():
        pytest.fail("System package is not implemented")
    files = list(source.rglob("*.py"))
    assert files
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert "from building_workflow" not in text and "from worldscale" not in text, (
            path
        )
