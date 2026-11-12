import ast

import pytest
from playwright.sync_api import sync_playwright

from worldascode.adapters.rendering.browser import bundle, serve
from worldascode.cli.main import main
from worldascode.config import RESOURCE_ROOT


def test_cli_exposes_only_owned_workflows(capsys):
    with pytest.raises(SystemExit) as exit:
        main(["--help"])
    assert exit.value.code == 0
    help_text = capsys.readouterr().out
    assert "native" not in help_text
    assert "design" in help_text and "compose" in help_text


def test_package_has_no_upstream_adapter_or_imports():
    root = RESOURCE_ROOT.parent
    assert not (root / "experimental").exists()
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert "experimental.native" not in (node.module or ""), path


@pytest.mark.parametrize("mesh_root", [False, True])
def test_owned_factory_uses_plain_javascript_and_object_name_probes(
    tmp_path, mesh_root
):
    script = tmp_path / "model.mjs"
    script.write_text(
        """import * as THREE from "three";
export const createModel = (options = {}) => {
  const root = new THREE.Group();
  root.userData.received = options;
  const shape = new THREE.Shape();
  shape.moveTo(-1,-1); shape.lineTo(1,-1); shape.lineTo(1,1); shape.lineTo(-1,1);
  const hole = new THREE.Path();
  hole.moveTo(-.6,-.6); hole.lineTo(-.6,.6); hole.lineTo(.6,.6); hole.lineTo(.6,-.6);
  shape.holes.push(hole);
  const mesh = new THREE.Mesh(new THREE.ExtrudeGeometry(shape,{depth:3,bevelEnabled:false}),new THREE.MeshStandardMaterial());
  mesh.name='flue'; root.add(mesh);
  root.userData.blockFlue = () => {
    const lid=new THREE.Mesh(new THREE.BoxGeometry(2,2,.1),new THREE.MeshStandardMaterial());
    lid.position.z=2.8; mesh.add(lid);
  };
  root.userData.semanticChecks=[{component_id:'flue',requirement:'air_path',axis:[0,0,1],centre:[0,0,1.5],length:4,wall_probe:[.8,0,1.5]}];
  return root;
};""",
        encoding="utf-8",
    )
    if mesh_root:
        script.write_text(
            script.read_text(encoding="utf-8").replace(
                "return root;",
                "root.remove(mesh); mesh.userData=root.userData; return mesh;",
            ),
            encoding="utf-8",
        )
    bundle(tmp_path, factory=script)
    with serve(tmp_path) as url, sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--use-angle=swiftshader"])
        page = browser.new_page()
        page.goto(url)
        page.wait_for_function("() => window.worldscaleReady === true")
        result = page.evaluate("worldscale.manifest()")
        assert result["probes"][0]["passed"]
        blocked = page.evaluate(
            "() => {worldscale.root.userData.blockFlue(); return worldscale.manifest();}"
        )
        assert not blocked["probes"][0]["passed"]
        browser.close()

    world = {
        "seed": 17,
        "blueprints": [
            {"id": "landmark", "origin": "factory", "components": [], "materials": []}
        ],
        "instances": [
            {
                "id": "one",
                "blueprint": "landmark",
                "anchor": [12, 0, 0],
                "scale": 2,
                "seed": 9,
            }
        ],
    }
    composed = tmp_path / "composed"
    bundle(composed, world=world, factories={"landmark": script})
    with serve(composed) as url, sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=["--use-angle=swiftshader"])
        page = browser.new_page()
        page.goto(url)
        page.wait_for_function("() => window.worldscaleReady === true")
        result = page.evaluate(
            "() => {const asset=worldscale.root.userData.factoryAssets[0];return {options:asset.userData.received,anchor:asset.position.toArray(),probe:worldscale.manifest().probes[0]};}"
        )
        assert result["options"] == {"seed": 17 ^ 9, "instanceId": "one"}
        assert result["anchor"] == [12, 0, 0]
        assert result["probe"]["passed"]
        blocked = page.evaluate(
            "() => {worldscale.root.userData.factoryAssets[0].userData.blockFlue(); return worldscale.manifest();}"
        )
        assert not blocked["probes"][0]["passed"]
        browser.close()


def test_factory_blueprint_requires_exact_bindings(tmp_path):
    world = {
        "blueprints": [
            {"id": "landmark", "origin": "factory", "components": [], "materials": []}
        ],
        "instances": [{"id": "one", "blueprint": "landmark", "anchor": [0, 0, 0]}],
    }
    with pytest.raises(ValueError, match="FACTORY_MAP_MISMATCH"):
        bundle(tmp_path, world=world)
