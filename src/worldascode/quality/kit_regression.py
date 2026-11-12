"""Independent browser regressions for isolated kit candidates."""

import json
import math
from pathlib import Path

from playwright.sync_api import sync_playwright

from worldascode.adapters.rendering.browser import bundle, serve
from worldascode.storage.artifacts import write_json

SCRIPT = """export function design(site,b,style) {
  const T=b.THREE;
  b.material('brick',{color:'#986856',seed:42,surface:{type:'brick',scale:2.4}});
  b.material('glass',{color:'#304956'});
  b.walls({material:'brick',windows:false});b.roof({material:'brick',form:site.roof.form});
  const frame=b.edge('e0').at(.5);
  b.window(frame,{y:1,width:1.3,height:2.2,trimMaterial:'brick',glass:'glass',pediment:'triangular'});
  b.gable(b.edge('e0').at(.3),{width:3,height:2.5,depth:3,material:'brick',roofMaterial:'brick',trimMaterial:'brick'});
  b.dormer(b.edge('e0').at(.7),{width:1.5,height:1.8,depth:2,material:'brick',roofMaterial:'brick',glass:'glass'});
  const chimney=b.chimney(b.at(0,0),{width:1,depth:1,height:2,material:'brick'});
  const marker=new T.Object3D();
  marker.userData.runProbe=()=>{
    chimney.object.updateWorldMatrix(true,true);
    const ray=new T.Raycaster(new T.Vector3(0,site.eave_m+20,0),new T.Vector3(0,-1,0));
    const centre=ray.intersectObject(chimney.object,true).length;
    ray.ray.origin.x=.45;const wall=ray.intersectObject(chimney.object,true).length;
    return {centre,wall};
  };b.add(marker,b.at(0,0));
}"""


def fixture_options(value, plan, case):
    """Declarative fixture bindings; no model-supplied JavaScript is evaluated.

    Roof APIs may legitimately need explicit wing polygons. Vary their inputs
    with the fixture rather than testing one building's absolute coordinates.
    """
    if value == {"$fixture": "wing-corners"}:
        wings = [plan]
        if case == 1:
            wings = [
                [[-15, 5], [15, 5], [15, -4], [-15, -4]],
                [[6, -4], [15, -4], [15, -15], [6, -15]],
            ]
        return [{"corners": wing} for wing in wings]
    if isinstance(value, dict):
        return {key: fixture_options(item, plan, case) for key, item in value.items()}
    if isinstance(value, list):
        return [fixture_options(item, plan, case) for item in value]
    return value


def run_regressions(kit, out, exercise=None):
    out = Path(out)
    plans = [
        [[-12, 5], [12, 5], [12, -5], [-12, -5]],
        [[-15, 5], [15, 5], [15, -15], [6, -15], [6, -4], [-15, -4]],
        [[-8, 4], [8, 4], [8, -4], [-8, -4]],
    ]
    plans[2] = [
        [x * math.cos(0.5) + z * math.sin(0.5), -x * math.sin(0.5) + z * math.cos(0.5)]
        for x, z in plans[2]
    ]
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--use-angle=swiftshader"])
        for i, plan in enumerate(plans):
            folder = out / f"case-{i}"
            folder.mkdir(parents=True)
            code = folder / "design.mjs"
            script = SCRIPT
            if exercise:
                method = exercise["method"]
                options = {
                    "material": "brick",
                    **fixture_options(exercise.get("options", {}), plan, i),
                }
                args = json.dumps(options, allow_nan=False)
                if exercise.get("signature") == "frame-options":
                    args = "b.edge('e0').at(.45)," + args
                elif exercise.get("signature") == "material":
                    args = "'exercise-material'," + args
                invocation = "b[" + json.dumps(method) + "](" + args + ");"
                if exercise.get("phase", "roof") == "roof":
                    script = script.replace(
                        "b.roof({material:'brick',form:site.roof.form});", invocation
                    )
                else:
                    script = script.replace(
                        "const frame=b.edge('e0').at(.5);",
                        invocation + "const frame=b.edge('e0').at(.5);",
                    )
            code.write_text(script, encoding="utf-8")
            site = {
                "object_id": f"regression-{i}",
                "footprint": plan,
                "eave_m": 9 + i * 2,
                "ridge_m": 12 + i * 2,
                "storeys": 3 + i,
                "roof": {"form": ["gable", "hip", "mansard"][i]},
                "edges": [{"id": f"e{k}", "end": k % 2 == 1} for k in range(len(plan))],
            }
            write_json(folder / "render-config.json", {"width": 480, "height": 360})
            try:
                bundle(folder, design=code, site=site, style={}, kit_path=kit)
                with serve(folder) as url:
                    page = browser.new_page(viewport={"width": 480, "height": 420})
                    errors, denied = [], []
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    page.route(
                        "**/*",
                        lambda route: (
                            route.continue_()
                            if route.request.url.startswith(url + "/")
                            else (denied.append(route.request.url), route.abort())[-1]
                        ),
                    )
                    page.goto(url, timeout=30000)
                    page.wait_for_function(
                        "() => window.worldscaleReady === true", timeout=20000
                    )
                    page.evaluate("worldscale.renderer.setAnimationLoop(null)")
                    manifest = page.evaluate("worldscale.manifest()")
                    probe = page.evaluate(
                        """() => {let report;worldscale.root.traverse(o=>{if(o.userData.runProbe)report=o.userData.runProbe();});return report;}"""
                    )
                    page.locator("canvas").screenshot(path=str(folder / "front.png"))
                    roof_audit = page.evaluate(
                        """plan=>{
                      const inside=(x,z)=>{let yes=false;for(let i=0,j=plan.length-1;i<plan.length;j=i++){const a=plan[i],b=plan[j];if((a[1]>z)!==(b[1]>z)&&x<(b[0]-a[0])*(z-a[1])/(b[1]-a[1])+a[0])yes=!yes;}return yes;};
                      const distance=(x,z)=>Math.min(...plan.map((a,i)=>{const b=plan[(i+1)%plan.length],dx=b[0]-a[0],dz=b[1]-a[1],t=Math.max(0,Math.min(1,((x-a[0])*dx+(z-a[1])*dz)/(dx*dx+dz*dz)));return Math.hypot(x-a[0]-t*dx,z-a[1]-t*dz);}));
                      let count=0,outside=0,uv=true,uMin=Infinity,uMax=-Infinity,vMin=Infinity,vMax=-Infinity;for(const p of worldscale.root.userData.components.filter(p=>p.component.kind==='roof'))p.node.traverse(m=>{if(!m.isMesh)return;const a=m.geometry.attributes.position,tex=m.geometry.attributes.uv;uv=uv&&!!tex;for(let i=0;i<a.count;i++){const x=a.getX(i),z=a.getZ(i);count++;if(!inside(x,z)&&distance(x,z)>.7)outside++;if(tex){uMin=Math.min(uMin,tex.getX(i));uMax=Math.max(uMax,tex.getX(i));vMin=Math.min(vMin,tex.getY(i));vMax=Math.max(vMax,tex.getY(i));}}});
                      return {count,outside,fraction:outside/Math.max(1,count),uv,uvSpan:Math.max(uMax-uMin,vMax-vMin)};
                    }""",
                        plan,
                    )
                    height = manifest["bounds"]["max"][1]
                    result = {
                        "case": i,
                        "passed": not errors
                        and not denied
                        and probe["centre"] == 0
                        and probe["wall"] > 0
                        and 0 < manifest["triangles"] < 200000
                        and site["eave_m"] <= height <= site["eave_m"] + 12
                        and roof_audit["count"] > 0
                        and roof_audit["fraction"] < 0.02
                        and roof_audit["uv"]
                        and roof_audit["uvSpan"] > 0.1,
                        "triangles": manifest["triangles"],
                        "height": height,
                        "flue": probe,
                        "errors": errors,
                        "denied_requests": denied,
                    }
                    result["roof_audit"] = roof_audit
                    result["exercise"] = exercise
                    page.close()
            except Exception as exc:
                result = {
                    "case": i,
                    "passed": False,
                    "error": str(exc)[:1800],
                    "errors": errors if "errors" in locals() else [],
                    "exercise": exercise,
                }
            write_json(folder / "result.json", result)
            results.append(result)
        browser.close()
    write_json(
        out / "result.json",
        {
            "passed": all(r["passed"] for r in results),
            "cases": results,
            "scope": "three synthetic geometry/runtime fixtures; no factual fidelity claim",
        },
    )
    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--kit", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--exercise", type=Path)
    args = parser.parse_args()
    exercise = (
        json.loads(args.exercise.read_text(encoding="utf-8")) if args.exercise else None
    )
    results = run_regressions(args.kit, args.out, exercise)
    print(json.dumps(results))
    raise SystemExit(0 if all(r["passed"] for r in results) else 2)
