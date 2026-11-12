import json
import subprocess

import pytest
from pydantic import ValidationError

from worldscale.config import ROOT
from worldscale.demo import demo_world
from worldscale.ir import (
    Component,
    RuntimeState,
    World,
    appearance_key,
    geometry_key,
    seed_channel,
)


def node(script):
    r = subprocess.run(
        ["node", "--input-type=module"],
        input=script,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return json.loads(r.stdout)


def test_solid_cannot_claim_air_path():
    with pytest.raises(ValidationError):
        Component(
            id="bad",
            kind="box",
            size=(1, 2, 1),
            material="m",
            semantic_requirements=["air_path"],
        )


@pytest.mark.parametrize("thickness", [0, -1, 0.5, 1])
def test_wall_thickness_leaves_real_opening(thickness):
    with pytest.raises(ValidationError):
        Component(
            id="bad",
            kind="hollow_shaft",
            size=(1, 2, 1),
            material="m",
            wall_thickness=thickness,
        )


def test_unknown_material_parent_cycle_nan():
    w = demo_world()
    w["blueprints"][0]["components"][0]["material"] = "missing"
    with pytest.raises(ValidationError):
        World.model_validate(w)
    w = demo_world()
    w["blueprints"][0]["components"][0]["parent"] = "hall"
    with pytest.raises(ValidationError):
        World.model_validate(w)
    with pytest.raises(ValidationError):
        RuntimeState(hour=float("nan"))


def test_material_changes_dont_rebuild_geometry():
    b = World.model_validate(demo_world()).blueprints[0]
    c = b.model_copy(deep=True)
    c.materials[0].color = "#123456"
    assert geometry_key(b) == geometry_key(c)
    assert appearance_key(b) != appearance_key(c)
    c.components[0].size = (19, 7, 10)
    assert geometry_key(b) != geometry_key(c)


def test_seed_channel_matches_browser_including_unicode():
    result = node(
        "import {seedChannel} from './runtime/semantic.mjs';console.log(JSON.stringify(seedChannel(42,'cây/01','1.0','shape')))"
    )
    assert result == seed_channel(42, "cây/01", "1.0", "shape")
    assert result != seed_channel(42, "cây/01", "1.0", "appearance")


def test_geometric_probe_detects_filled_hole_and_missing_shell():
    w = {
        "blueprints": [
            {
                "id": "b",
                "components": [
                    {
                        "id": "pipe",
                        "kind": "hollow_shaft",
                        "size": [2, 4, 2],
                        "wall_thickness": 0.2,
                        "material": "m",
                        "semantic_requirements": ["air_path"],
                    }
                ],
                "materials": [{"id": "m"}],
            }
        ],
        "instances": [{"id": "i", "blueprint": "b", "anchor": [0, 0, 0]}],
    }
    w = World.model_validate(w).model_dump()
    result = node(
        "import * as T from 'three';import {buildWorld,semanticProbes} from './runtime/semantic.mjs';const w="
        + json.dumps(w)
        + ";const root=buildWorld(w);const clean=semanticProbes(root);const lid=new T.Mesh(new T.BoxGeometry(2,.1,2),new T.MeshBasicMaterial());root.add(lid);const filled=semanticProbes(root);root.remove(lid);root.userData.components[0].node.visible=false;root.userData.components[0].node.geometry=new T.BufferGeometry();const empty=semanticProbes(root);console.log(JSON.stringify({clean,filled,empty}));"
    )
    assert result["clean"][0]["passed"]
    assert not result["filled"][0]["passed"]
    assert not result["empty"][0]["passed"]


def test_seed_varies_canopy_without_moving_anchors_and_runtime_doesnt_rebuild():
    w = demo_world()
    result = node(
        "import {buildWorld,applyState} from './runtime/semantic.mjs';const w="
        + json.dumps(w)
        + ";const a=buildWorld(w),b=buildWorld(w);w.seed++;const c=buildWorld(w);const leaves=r=>r.userData.components.filter(v=>v.component.kind==='tree').flatMap(v=>v.node.children.map(n=>n.position.toArray()));const ids=[];a.traverse(o=>{if(o.isMesh)ids.push(o.geometry.uuid)});applyState(a,{hour:22,wetness:.9,wind:1});const after=[];a.traverse(o=>{if(o.isMesh)after.push(o.geometry.uuid)});console.log(JSON.stringify({same:JSON.stringify(leaves(a))===JSON.stringify(leaves(b)),varied:JSON.stringify(leaves(a))!==JSON.stringify(leaves(c)),anchor:a.children[0].position.equals(c.children[0].position),fixed:JSON.stringify(ids)===JSON.stringify(after)}));"
    )
    assert all(result.values())
