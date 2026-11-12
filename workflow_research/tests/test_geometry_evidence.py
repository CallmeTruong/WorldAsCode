import hashlib,json
from building_workflow.urban.geometry_evidence import load_geometry_evidence


def test_numeric_roof_evidence_does_not_confuse_absolute_altitude_with_roof_level(tmp_path):
    (tmp_path/'ground-evidence.json').write_text(json.dumps({'median_height_m':40}))
    (tmp_path/'measurements').mkdir()
    identifier='way/1/0';points=[[x,z] for x in [3,5,7] for z in [3,5,7]]
    data={'id':identifier,'points':points+[[.2,.2]],'heights':[210]*len(points)+[70]}
    (tmp_path/'measurements'/(hashlib.sha256(identifier.encode()).hexdigest()[:12]+'.json')).write_text(json.dumps(data))
    result=load_geometry_evidence({'buildings':[{'id':identifier,'outer':[[0,0],[10,0],[10,10],[0,10]],'holes':[]}]},tmp_path)
    assert result['available']
    roof=result['objects'][0];assert roof['height_p10_p50_p90_m']==[170,170,170]
    assert roof['interior_samples']==9 and all(p[1]==170 for p in roof['spatial_anchors_xyz_m'])


def test_absent_measurements_are_optional(tmp_path):
    assert not load_geometry_evidence({'buildings':[]},tmp_path)['available']
