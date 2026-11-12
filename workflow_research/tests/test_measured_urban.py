import numpy as np
from shapely.geometry import Polygon
from building_workflow.urban.measured import LocalFrame,RoofField,sample_plan,compile_surfaces,project_points,bake_assignments


def test_roof_compiler_preserves_holes_area_and_ground_relative_heights():
    building={'id':'one','name':'one','outer':[[0,0],[10,0],[10,10],[0,10]],'holes':[[[2,2],[4,2],[4,4],[2,4]]],'area':96,'height':15}
    city={'buildings':[building]};plan=sample_plan(city,2)[0]
    parts,audit=compile_surfaces(city,[{**plan,'heights':[115]*len(plan['points'])}],100)
    faces=np.asarray(parts[0]['faces']);roof=faces[np.array(parts[0]['kinds'])=='roof']
    normals=np.cross(roof[:,1]-roof[:,0],roof[:,2]-roof[:,0]);area=sum(np.linalg.norm(normals,axis=1)/2)
    assert abs(area-96)<1e-6 and np.all(normals[:,1]>0)
    assert np.allclose(roof[:,:,1],15) and np.isfinite(faces).all()
    assert min(faces[:,:,1].ravel())==0 and audit[0]['valid_samples']==len(plan['points'])
    hole=Polygon(building['holes'][0])
    assert all(Polygon(t[:,[0,2]]).intersection(hole).area<1e-8 for t in roof)


def test_local_plane_fit_reduces_noise_without_averaging_different_roof_levels():
    points=np.array([[x,z] for x in range(6) for z in range(6)],float)
    true=10+points[:,0]*.2+points[:,1]*.1;noisy=true+np.random.default_rng(42).normal(0,.15,len(true))
    field=RoofField(points,noisy,10);fit=field.values(points,True)
    assert np.mean((fit-true)**2)<np.mean((noisy-true)**2)
    stepped=RoofField([[0,0],[0,1],[1,0],[2,0],[2,1],[3,0]],[10,10,10,100,100,100],10)
    assert stepped.values([[.2,.2]],True)[0]<12
    assert stepped.values([[2.7,.1]],True)[0]>98


def test_projection_rejects_points_behind_camera_and_outside_frame():
    matrix=np.zeros((4,4));matrix[0,0]=matrix[1,1]=1;matrix[2,2]=-1.002;matrix[2,3]=-.2;matrix[3,2]=-1
    camera={'view_matrix':np.eye(4).reshape(-1,order='F').tolist(),'projection_matrix':matrix.reshape(-1,order='F').tolist()}
    uv,valid=project_points(np.array([[0,0,-10],[0,0,10],[100,0,-10]]),camera)
    assert np.allclose(uv[0],[.5,.5]) and valid.tolist()==[True,False,False]


def test_texture_assignment_requires_depth_and_never_uses_held_out_image():
    class Frame:
        def ecef(self,p):return np.asarray(p,float)
        def local_camera(self,p):return {'position':[0,0,10]}
    view=np.eye(4);view[2,3]=-10
    projection=np.zeros((4,4));projection[0,0]=projection[1,1]=1;projection[2,2]=-1.002;projection[2,3]=-.2;projection[3,2]=-1
    camera={'view_matrix':view.reshape(-1,order='F').tolist(),'projection_matrix':projection.reshape(-1,order='F').tolist()}
    parts=[{'id':'one','faces':[[[0,0,0],[1,0,0],[0,1,0]]]}];center=[[1/3,1/3,0]]
    good=[{'camera':camera,'held_out':False}]
    groups,audit=bake_assignments(parts,Frame(),good,[center]);assert groups[0]['source_view']==0 and audit[0]['projected_area_coverage']==1
    groups,audit=bake_assignments(parts,Frame(),good,[[[1/3,1/3,100]]]);assert groups[0]['source_view']==-1 and audit[0]['projected_area_coverage']==0
    groups,_=bake_assignments(parts,Frame(),[{'camera':camera,'held_out':True}],[center]);assert groups[0]['source_view']==-1


def test_local_frame_camera_basis_and_ground_datum():
    origin={'longitude':139.7631,'latitude':35.67845,'projection':'EPSG:32654'};frame=LocalFrame(origin,38)
    camera={'longitude':origin['longitude'],'latitude':origin['latitude'],'height':138,'direction_ecef':(-frame.basis[:,1]).tolist(),'up_ecef':(-frame.basis[:,2]).tolist(),'projection_matrix':[1,0,0,0,0,2,0,0,0,0,0,0,0,0,0,1],'viewport':[1920,1440]}
    local=frame.local_camera(camera)
    assert np.allclose(local['position'],[0,100,0],atol=1e-6)
    assert np.allclose(local['direction'],[0,-1,0]) and np.linalg.det(frame.basis)>.999
