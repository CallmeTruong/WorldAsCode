import json

from playwright.sync_api import sync_playwright

from worldscale.browser import bundle, serve
from worldscale.config import ROOT


def test_static_batch_preserves_geometry_bounds_raycast_ownership_and_materials(tmp_path):
    script=tmp_path/'factory.ts'
    script.write_text('import * as THREE from "three";\n'
        +f'import {{batchStaticAssets,resolveBatchHit}} from {json.dumps((ROOT/"runtime/batching.mjs").as_posix())};\n'
        +'''export function createProbe(options: ProceduralModelOptions={}) {
          const p=new THREE.Group(),material=new THREE.MeshStandardMaterial();
          for(let i=0;i<2;i++){const mesh=new THREE.Mesh(new THREE.BoxGeometry(2,4,2),material);mesh.position.set(i*3,2,0);mesh.name='part-'+i;p.add(mesh);}
          const placements=[{id:'first',position:[0,0,0]},{id:'second',position:[10,0,0]}];
          const root=batchStaticAssets(p,placements);
          const marker=new THREE.Object3D();marker.userData.check=()=>{
            root.updateMatrixWorld(true);
            const ray=new THREE.Raycaster(new THREE.Vector3(10,10,0),new THREE.Vector3(0,-1,0));
            return {groups:root.children.filter(o=>o.isInstancedMesh).length,
              count:root.children.find(o=>o.isInstancedMesh).count,
              owner:resolveBatchHit(ray.intersectObject(root,true)[0]),
              bounds:new THREE.Box3().setFromObject(root).getSize(new THREE.Vector3()).toArray()};
          };root.add(marker);return root;
        }''',encoding='utf-8')
    bundle(tmp_path,native=script)
    with serve(tmp_path) as url,sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True,args=['--use-angle=swiftshader'])
        page=browser.new_page()
        page.goto(url)
        page.wait_for_function('() => window.worldscaleReady === true')
        result=page.evaluate('() => {let r;worldscale.root.traverse(o=>{if(o.userData.check)r=o.userData.check();});return r;}')
        manifest=page.evaluate('worldscale.manifest()')
        browser.close()
    assert result=={'groups':1,'count':4,'owner':{'asset':'second','component':'part-0'},'bounds':[15,4,2]}
    assert manifest['triangles']==48
