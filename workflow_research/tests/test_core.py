import json
import pytest
from building_workflow.models import Review, BuildingSpec, prefer, SCORE_KEYS
from building_workflow.provider import Provider, BudgetExceeded
from building_workflow.config import Settings
from building_workflow.runtime import validate_source
from building_workflow.workflow import apply_edits


def candidate(value=.7,critical=(),valid=True):
    return {"geometry_passed":valid,"review":{"scores":dict.fromkeys(SCORE_KEYS,value),"critical_defects":list(critical),
        "defects":[],"matched_features":[],"inferred_regions":["back"],"confidence":.7}}


def test_critical_regression_cannot_win_average_score():
    assert not prefer(candidate(.95,["missing roof"]),candidate(.6))
    assert not prefer(candidate(.95,valid=False),candidate(.6))
    assert prefer(candidate(.65),candidate(.6))


def test_regressed_feature_is_not_hidden_by_mean():
    newer=candidate(.9);newer["review"]["scores"]["facade"]=.4
    assert not prefer(newer,candidate(.7))


def test_review_rejects_nan_or_missing_dimension():
    bad=candidate()["review"];bad["scores"]["roof"]=float("nan")
    with pytest.raises(ValueError): Review.model_validate(bad)
    bad["scores"].pop("roof")
    with pytest.raises(ValueError): Review.model_validate(bad)


def test_exact_patch_rejects_ambiguous_anchor():
    with pytest.raises(ValueError,match="PATCH_ANCHOR"):
        apply_edits("abc abc",[{"old":"abc","new":"def"}])


@pytest.mark.parametrize("danger",["fetch('https://x')","import('node:fs')","process.env","new Function('x')"])
def test_unsafe_source_is_rejected(danger):
    with pytest.raises(ValueError):validate_source("export function build(params = {}) { "+danger+"; return {};} // extra")


def test_call_budget_survives_recreation(tmp_path):
    settings=Settings("https://example.invalid","SECRET","test","test","test","test")
    provider=Provider(settings,tmp_path,max_calls=1)
    provider.usage["calls"]=1;provider.save_usage()
    restored=Provider(settings,tmp_path,max_calls=1)
    with pytest.raises(BudgetExceeded):restored.check()
    assert restored.usage["cost_usd"] is None
    assert "SECRET" not in (tmp_path/"usage.json").read_text()


def test_observation_alias_preserves_provenance():
    from building_workflow.models import Feature
    feature=Feature.model_validate({"id":"facade","description":"three bays","evidence":"observed",
        "confidence":.8,"source region":"reference center"})
    assert feature.source=="reference center"
