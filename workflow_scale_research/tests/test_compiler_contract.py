from worldscale.compiler_contract import (
    canonicalize_aliases,
    issues,
    pass_coverage_spec,
)


def test_identity_scale_does_not_override_authored_dimensions():
    source = {
        "componentTree": [
            {
                "id": "building",
                "dimensions": {"width": 2.6, "height": 1.8, "depth": 1.35},
                "transform": {"scale": [1, 1, 1], "position": [0, 0, 0]},
            }
        ]
    }
    result, changes = canonicalize_aliases(source)
    assert result["componentTree"][0]["transform"] == {"position": [0, 0, 0]}
    assert source["componentTree"][0]["transform"]["scale"] == [1, 1, 1]
    assert "identity transform.scale removed" in changes[0]


def test_intended_nonidentity_scale_is_preserved():
    source = {
        "componentTree": [
            {
                "id": "shaft",
                "dimensions": {"width": 2, "height": 3, "depth": 2},
                "transform": {"scale": [1, 0.5, 1]},
            }
        ]
    }
    result, changes = canonicalize_aliases(source)
    assert result["componentTree"][0]["transform"]["scale"] == [1, 0.5, 1]
    assert changes == []


def test_macro_coverage_excludes_later_pass_details_and_repetitions():
    source = {
        "componentTree": [
            {"id": "root", "level": "macro"},
            {"id": "window", "level": "meso", "parent": "root"},
            {"id": "mullion", "level": "micro", "parent": "window"},
        ],
        "repetitionSystems": [
            {"id": "windows", "level": "meso"},
            {"id": "mullions", "level": "micro"},
        ],
        "preSpecAssessment": {
            "detailInventory": {
                "details": [
                    {"id": "mass", "mapsTo": {"ref": "root/main"}},
                    {"id": "frame", "mapsTo": {"ref": "window/frame"}},
                ]
            }
        },
    }
    scoped = pass_coverage_spec(source, "blockout")
    assert [c["id"] for c in scoped["componentTree"]] == ["root"]
    assert scoped["repetitionSystems"] == []
    assert [d["id"] for d in scoped["preSpecAssessment"]["detailInventory"]["details"]] == ["mass"]


def test_factory_contract_catches_invalid_hollow_profile():
    source = {
        "componentTree": [
            {
                "id": "flue",
                "level": "macro",
                "primitive": "extrude",
                "dimensions": {"width": 1, "height": 1, "depth": 1},
                "geometryDescriptor": {"profile2D": {"points": [[0, 0]], "depth": 0}},
            }
        ]
    }
    errors = issues(source, "blockout")
    assert {x["error"] for x in errors} == {
        "EXTRUDE_REQUIRES_NUMERIC_PROFILE_POINTS",
        "EXTRUDE_REQUIRES_POSITIVE_PROFILE_DEPTH",
    }
