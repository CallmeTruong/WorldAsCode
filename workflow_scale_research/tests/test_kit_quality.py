import pytest
from playwright.sync_api import sync_playwright

from worldscale.browser import bundle, serve


def test_kit_hollow_flue_material_channels_and_seed_in_browser(tmp_path):
    site = {"object_id": "test", "footprint": [[-8, 4], [8, 4], [8, -4], [-8, -4]],
            "edges": [{"id": f"e{i}", "end": i % 2 == 1} for i in range(4)],
            "eave_m": 9, "ridge_m": 12, "storeys": 3}
    code = """export function design(site,b,style) {
      b.material('brick',{color:'#986856',surface:{type:'brick',scale:2.4},seed:42});
      b.material('same',{color:'#986856',surface:{type:'brick',scale:2.4},seed:42});
      b.material('different',{color:'#986856',surface:{type:'brick',scale:2.4},seed:7});
      b.material('glass',{color:'#304956'});
      b.walls({material:'brick',windows:false});
      b.roof({material:'brick',form:'gable'});
      b.chimney(b.at(0,0),{material:'brick',width:1,depth:1,height:2});
      b.window(b.edge('e0').at(.5),{trimMaterial:'brick',glass:'glass',pediment:'triangular'});
      for(const [i,name] of ['same','different'].entries()) b.box(b.at(i,0),{w:1,h:1,d:1,material:name});
    }"""
    script = tmp_path / 'design.mjs'
    script.write_text(code)
    bundle(tmp_path, design=script, site=site, style={})
    with serve(tmp_path) as url, sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--use-angle=swiftshader'])
        page = browser.new_page()
        page.goto(url)
        page.wait_for_function('window.worldscaleReady === true')
        result = page.evaluate("""() => {
          const root=worldscale.root, parts=root.userData.components;
          const chimney=parts.find(p=>p.component.kind==='chimney').node;
          const materials=[];root.traverse(o=>{if(o.isMesh&&!materials.includes(o.material))materials.push(o.material);});
          const brick=materials.find(m=>m.bumpMap), same=parts.filter(p=>p.component.kind==='box')[0].node.material,
            different=parts.filter(p=>p.component.kind==='box')[1].node.material;
          const shaft=chimney.children[0].geometry;
          return {channels:brick.map!==brick.bumpMap&&brick.bumpMap!==brick.roughnessMap,
            same:brick.map.image.toDataURL()===same.map.image.toDataURL(),
            different:brick.map.image.toDataURL()!==different.map.image.toDataURL(),
            // The cap and shaft are both extrusions of shapes with one real hole.
            holes:chimney.children.slice(0,2).map(m=>m.geometry.parameters.shapes.holes.length),
            windowMeshes:parts.find(p=>p.component.kind==='window').node.children.length,
            walls:root.userData.kitCounts.walls};
        }""")
        browser.close()
    assert result == {"channels": True, "same": True, "different": True, "holes": [1, 1], "windowMeshes": 2, "walls": 1}


@pytest.mark.parametrize('mutation', [
    'site.footprint[0][0]=100;',
    'wall.pivot.position.x=10;',
    "b.walls({material:'brick'});",
])
def test_kit_rejects_macro_geometry_mutations(tmp_path, mutation):
    site = {"object_id": "test", "footprint": [[-8, 4], [8, 4], [8, -4], [-8, -4]],
            "edges": [{"id": f"e{i}", "end": False} for i in range(4)],
            "eave_m": 9, "ridge_m": 12, "storeys": 3}
    script = tmp_path / 'design.mjs'
    script.write_text("export function design(site,b,style){b.material('brick',{color:'#986856'});const wall=b.walls({material:'brick'});" + mutation + '}')
    bundle(tmp_path, design=script, site=site, style={})
    with serve(tmp_path) as url, sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--use-angle=swiftshader'])
        page = browser.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(url)
        page.wait_for_timeout(300)
        assert errors
        assert page.evaluate('window.worldscaleReady !== true')
        browser.close()
