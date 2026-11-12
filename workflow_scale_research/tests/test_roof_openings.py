import json
import subprocess

from worldscale.config import ROOT


def test_roof_subtraction_preserves_area_and_uvs_with_a_real_opening():
    script = """
      import * as THREE from 'three';
      import {cutRoofOpening} from './runtime/roof-openings.mjs';
      const geo=new THREE.PlaneGeometry(16,8);geo.rotateX(-Math.PI/2);
      const mesh=new THREE.Mesh(geo,new THREE.MeshBasicMaterial({side:THREE.DoubleSide}));
      // A rotated opening must still be four square metres, independent of yaw.
      cutRoofOpening(mesh,{x:0,z:0,yaw:.3},2,1,-1);
      const p=mesh.geometry.attributes.position;let area=0;
      for(let i=0;i<p.count;i+=3){const a=new THREE.Vector3().fromBufferAttribute(p,i),b=new THREE.Vector3().fromBufferAttribute(p,i+1),c=new THREE.Vector3().fromBufferAttribute(p,i+2);area+=b.sub(a).cross(c.sub(a)).length()/2;}
      const ray=new THREE.Raycaster(new THREE.Vector3(0,10,0),new THREE.Vector3(0,-1,0));
      const centre=ray.intersectObject(mesh).length;
      ray.ray.origin.x=4;const wall=ray.intersectObject(mesh).length;
      console.log(JSON.stringify({area,centre,wall,uvCount:mesh.geometry.attributes.uv.count,positions:p.count}));
    """
    result = subprocess.run(['node', '--input-type=module', '-e', script], cwd=ROOT,
                            capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    assert abs(data['area'] - 124) < 1e-4
    assert data['centre'] == 0 and data['wall'] > 0
    assert data['uvCount'] == data['positions']
