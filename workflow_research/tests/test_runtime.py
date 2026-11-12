from pathlib import Path
import json
import pytest
from PIL import Image, ImageStat
from building_workflow.runtime import render
from building_workflow.skills import geometry_gate

SOURCE = """import * as THREE from 'three';
export function build(params = {}) {
 const g=new THREE.Group();
 const b=new THREE.Mesh(new THREE.BoxGeometry(4,6,3),new THREE.MeshStandardMaterial({color:0xbc8250}));
 b.position.y=3;b.name='main-mass';g.add(b);return g;
}
"""


def test_actual_three_geometry_and_five_different_views(tmp_path):
    # Put source under project root so tsc resolves the pinned Three.js types.
    from building_workflow.config import ROOT
    import tempfile
    with tempfile.TemporaryDirectory(dir=ROOT/".cache") as folder:
        source=Path(folder)/"generator.ts";source.write_text(SOURCE)
        result=render(source,tmp_path)
    assert result["geometry_passed"] and result["triangles"]==12
    assert result["network_requests_denied"]==[]
    for name in ["front","back","left","right","isometric"]:
        im=Image.open(tmp_path/(name+".png"))
        assert im.size==(800,800)
        assert max(ImageStat.Stat(im).stddev)>10
    assert (tmp_path/"front.png").read_bytes()!=(tmp_path/"isometric.png").read_bytes()


def test_open_mesh_fails_real_upstream_gate():
    result=geometry_gate({"meshes":[{"id":"open","vertices":[[0,0,0],[1,0,0],[0,1,0]],"indices":[0,1,2],"normals":[[0,0,1]]*3}]})
    assert not result["passed"]
    assert any("openEdges" in message for message in result["failures"])


def test_architectural_blade_wall_keeps_topology_checks_without_weapon_gate():
    from building_workflow.config import ROOT
    import tempfile
    with tempfile.TemporaryDirectory(dir=ROOT/".cache") as folder:
        path=Path(folder);source=path/"generator.ts"
        source.write_text(SOURCE.replace("main-mass","white blade wall"))
        result=render(source,path)
        assert result["geometry_passed"]
        report=json.loads((path/"geometry.json").read_text())
        assert report["meshes"][0]["source_part_name"]=="white blade wall"
        assert report["meshes"][0]["boundaryEdges"]==0


def test_runaway_generated_worker_is_terminated(tmp_path):
    from building_workflow.config import ROOT
    import tempfile
    with tempfile.TemporaryDirectory(dir=ROOT/".cache") as folder:
        source=Path(folder)/"generator.ts"
        source.write_text("export function build(params = {}) { while(true) {} return null; }")
        with pytest.raises(RuntimeError):render(source,tmp_path,timeout=12)


def test_network_is_denied_even_if_static_scan_is_obfuscated():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,chromium_sandbox=True)
        ctx=browser.new_context(service_workers="block")
        ctx.route("**/*",lambda route:route.abort())
        page=ctx.new_page()
        page.set_content('<meta http-equiv="Content-Security-Policy" content="connect-src \'none\'; script-src \'unsafe-inline\' blob:; worker-src blob:">')
        outcome=page.evaluate("""async ()=>{try{await globalThis['fet'+'ch']('https://example.invalid');return 'allowed'}catch(e){return 'denied'}}""")
        assert outcome=="denied"
        browser.close()
