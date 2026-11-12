import numpy as np
import pytest

from worldscale import brief, design, dsm, massing

RECTANGLE = [[-15, 6], [15, 6], [15, -6], [-15, -6]]  # 30 m east-west, 12 m north-south


def test_wing_brief_preserves_pose_and_exact_rectangles_after_registration():
    evidence={'wings':[{'centre_xz':[2,3],'length_m':5,'width_m':20,'rotation_y_rad':.27}]}
    registration=massing.Registration(dx=1,dz=-2,grow=.5)
    wing=brief.registered_wings(evidence,registration)[0]
    assert wing['centre_xz']==[3,1]
    assert wing['length_m']==21 and wing['width_m']==6
    corners=np.array(wing['corners'])
    u,v=corners[1]-corners[0],corners[3]-corners[0]
    assert abs(np.dot(u,v))<1e-10
    assert np.linalg.norm(u)==pytest.approx(21)
    assert np.linalg.norm(v)==pytest.approx(6)
    assert corners.mean(axis=0)==pytest.approx([3,1])

SCRIPT = """export function design(site, b, style) {
  b.material('brick', {color: site.colours.wall});
  // window: is a kit option, not the browser global
  b.walls({material: 'brick', window: {w: 0.4, h: 0.6}});
}"""


def test_lint_accepts_kit_options_and_rejects_escape_hatches():
    assert design.lint(SCRIPT) == []
    assert design.lint("function design(){}")  # not exported
    for bad in (
        "import x from 'y';\n" + SCRIPT,
        SCRIPT.replace("b.walls", "fetch('http://x'); b.walls"),
        SCRIPT.replace("b.walls", "window.location = 'x'; b.walls"),
        SCRIPT.replace("b.walls", "document.cookie; b.walls"),
        SCRIPT.replace("b.walls", "new Function('x')(); b.walls"),
    ):
        assert design.lint(bad), bad


def test_lint_ignores_forbidden_words_inside_comments():
    assert design.lint(SCRIPT.replace("// window:", "// fetch and import are mentioned; window:")) == []


def test_edges_report_length_facing_and_wing_ends():
    edges = brief.edges(massing.to_plan(RECTANGLE))
    assert sorted(e["length_m"] for e in edges) == [12.0, 12.0, 30.0, 30.0]
    assert {e["facing"] for e in edges} == {"N", "E", "S", "W"}
    for e in edges:
        assert e["end"] == (e["length_m"] == 12.0)
        assert e["facing"] in (("E", "W") if e["end"] else ("N", "S"))


def gable_with_features(step=0.5):
    layout = dsm.grid_layout({"footprint": RECTANGLE}, step)
    points = dsm.grid_plan_points(layout)
    x, n = points[..., 0], points[..., 1]
    inside = (np.abs(x) <= 15) & (np.abs(n) <= 6)
    grid = np.where(inside, 9.0 + 0.5 * (6 - np.abs(n)), 0.0)
    chimney = (np.abs(x - 6) < 0.6) & (np.abs(n - 1) < 0.6)
    dormer = (np.abs(x + 5) < 1.2) & (n < -3.0) & (n > -5.6)
    grid = np.where(chimney, 14.5, grid)
    grid = np.where(dormer, 11.6, grid)
    return grid, layout


def test_brief_finds_a_chimney_and_a_dormer_but_not_roof_noise():
    grid, layout = gable_with_features()
    plan = massing.to_plan(RECTANGLE)
    features, measured = brief.roof_features(grid, layout, plan, 12.0)
    assert len(features["chimneys"]) == 1
    assert abs(features["chimneys"][0]["x"] - 6) < 0.6
    assert len(features["dormers"]) == 1
    edge = brief.edges(plan)[int(features["dormers"][0]["edge"][1:])]
    assert edge["facing"] == "S" and not edge["end"]
    assert features["towers"] == []
    assert abs(measured["eave"] - 9.0) < 0.6 and abs(measured["ridge"] - 12.0) < 0.5

    plain, _ = brief.roof_features(*gable_plain(), plan, 12.0)
    assert plain == {"dormers": [], "chimneys": [], "towers": []}


def gable_plain(step=0.5):
    layout = dsm.grid_layout({"footprint": RECTANGLE}, step)
    points = dsm.grid_plan_points(layout)
    inside = (np.abs(points[..., 0]) <= 15) & (np.abs(points[..., 1]) <= 6)
    return np.where(inside, 9.0 + 0.5 * (6 - np.abs(points[..., 1])), 0.0), layout


def test_metric_checks_are_tolerant_of_style_but_not_of_a_wrong_building():
    evidence = {
        "views": [
            {"id": "north", "camera": {"position": [0, 40, 80], "target": [0, 3, 0]}},
            {"id": "overhead", "camera": {"position": [0, 100, 0.3], "target": [0, 3, 0]}},
        ]
    }
    site = {"top_m": 20.0}

    def run(oblique, plan, height):
        report = {"passed": True, "manifest": {"bounds": {"max": [0, height, 0]}, "triangles": 5000}}
        browser = {"north": {"iou": oblique}, "overhead": {"iou": plan}}
        return design.measure(".", evidence, site, report, browser)

    assert run(0.74, 0.8, 23.0)["passed"]  # stylised, taller ornament: fine
    assert not run(0.5, 0.8, 20.0)["checks"]["outline_oblique"]
    assert not run(0.8, 0.5, 20.0)["checks"]["outline_plan"]
    assert not run(0.8, 0.8, 40.0)["checks"]["height"]


def test_candidate_selection_protects_acceptance_and_weakest_quality_dimension():
    def candidate(likeness, style, detail, accepted=False):
        return {"accepted": accepted, "metrics_passed": True,
                "scores": {"likeness": likeness, "style": style, "detail": detail}}
    balanced = candidate(.73, .72, .68, True)
    flashy_wrong = candidate(.4, .99, .99)
    assert design.candidate_rank(balanced) > design.candidate_rank(flashy_wrong)
    assert design.candidate_rank(candidate(.7, .7, .6)) > design.candidate_rank(candidate(.95, .95, .35))
    for value in (float('nan'), float('inf'), True, -1, '0.9'):
        with pytest.raises(ValueError, match='INVALID_CRITIC_SCORE'):
            design.validated_scores({"likeness": value, "style": .7, "detail": .7})
