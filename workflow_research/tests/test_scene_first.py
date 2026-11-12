import copy
import pytest
from building_workflow.urban.scene_first import acceptable,improved,apply_adjustments,DIMENSIONS


def review(score=4):return {'scores':dict.fromkeys(DIMENSIONS,score),'issues':[]}


def test_usable_quality_allows_approximation_but_blocks_major_faults():
    r=review();r['scores']['materials']=3;assert acceptable(r)
    r['issues']=[{'severity':'minor','part':'approximate roof material'}];assert acceptable(r)
    r['issues']=[{'severity':'major'}];assert not acceptable(r)
    r=review(3);assert not acceptable(r)
    r['scores']['roofs']=float('nan')
    with pytest.raises(ValueError):acceptable(r)


def test_agent_controls_shared_appearance_without_texture_registry():
    city={'material_recipes':{},'tree_cluster_detail':1}
    result=apply_adjustments(city,{'material_recipes':{'road':{'color':'#55616b','roughness':.92,'pattern':'asphalt','tile_m':3},'pavement':{'color':'#beb9ab','pattern':'none'}},'tree_cluster_detail':2})
    assert result['material_recipes']['road']['color']=='#55616b'
    assert 'required_texture_roles' not in result
    assert result['tree_cluster_detail']==2
    with pytest.raises(ValueError):apply_adjustments({}, {'material_recipes':{'road':{'color':'javascript:bad'}}})
    with pytest.raises(ValueError):apply_adjustments({}, {'material_recipes':{'road':{'pattern':'asphalt','tile_m':0}}})


def test_scene_improvement_cannot_hide_critical_regression():
    old=review(3);new=review(4);assert improved(old,new)
    new['issues']=[{'severity':'critical'}];assert not improved(old,new)
    new=review(4);new['scores']['identity']=1;assert not improved(old,new)


def test_conflicting_measurements_allow_bounded_part_interpretation():
    from building_workflow.urban.runtime import height_within_evidence
    b={'height':12}
    assert not height_within_evidence(b,34.7)
    b['height_envelope_m']=[12,34.7]
    assert height_within_evidence(b,34.7) and height_within_evidence(b,12)
    assert not height_within_evidence(b,80)
    b['height_envelope_m']=[35,12]
    with pytest.raises(ValueError):height_within_evidence(b,20)
