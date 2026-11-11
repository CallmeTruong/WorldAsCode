import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import time
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver
from .config import ROOT, PROMPT_VERSION, SKILL_COMMIT
from .models import BuildingSpec, Review, prefer
from .provider import Provider, BudgetExceeded, write_json
from . import skills
from .runtime import render, validate_source
from .report import comparison, multiview, run_report

FACTORY_CONTRACT = """
Return JSON {"source":"complete TypeScript source", "camera":{"azimuth":number,"elevation":number}, "notes":[strings]}.
Source imports ONLY `import * as THREE from 'three';` and exports `export function build(params = {}) { ... return root; }`.
Y is up, ground y=0, front is +Z, right is +X. The returned Group contains ONLY generated geometry, no lights/camera/ground/landscaping or surrounding buildings. Name every mesh/part. Use helper functions and loops for repeated features; no hardcoded mesh vertex dumps.
Write free procedural code specific to the building in the photo, with macro massing, true roof shape, floor rhythm, recesses, balconies, columns, mullions and landmark details where observed. Do not use a generic house template. Respect observed proportions first.
Use MeshStandardMaterial with physically meaningful colors; glass should remain visible (opaque dark tinted proxy acceptable). No textures or external assets, no browser/Node APIs, no fetch, no file IO, no dynamic imports, no timers, no eval/Function. build must be synchronous and deterministic.
All meshes must be closed watertight solids with consistent normals: BoxGeometry, ExtrudeGeometry closed Shape, CylinderGeometry with caps/nonzero radii, or explicitly closed custom geometry. Avoid PlaneGeometry, open tubes, degenerate triangles and coincident overlapping coplanar faces. Geometry gate checks every mesh, including self-intersections.
Budgets: <=50000 triangles, <=1200 meshes, source <100000 chars. Ordinary Mesh only (no InstancedMesh in this measurable baseline). Reuse geometries/materials. Do not implement rendering. Visible facade is +Z. Camera azimuth 0 is looking at front; +35 sees front and right; -35 sees front and left. Elevation degrees above ground; fit the actual photograph's perspective. Hidden sides are inferred; never pretend measured dimensions exist.
"""


class State(TypedDict, total=False):
    sample: dict
    strategy: str
    max_refinements: int
    iteration: int
    spec: dict
    camera: dict
    candidates: list[dict]
    best: dict | None
    current: dict
    stop_reason: str


def apply_edits(source, edits):
    if not isinstance(edits,list) or not edits or len(edits)>12:
        raise ValueError("INVALID_PATCH_LIST")
    for edit in edits:
        old,new=edit.get("old"),edit.get("new")
        if not isinstance(old,str) or not old or source.count(old)!=1 or not isinstance(new,str):
            raise ValueError("PATCH_ANCHOR_NOT_UNIQUE")
        source=source.replace(old,new,1)
    validate_source(source)
    return source


def run_job(settings,sample,strategy,max_refinements=1,run_id=None,max_calls=12,max_tokens=100000,max_seconds=900,refinement_scope="targeted"):
    if not 0<=max_refinements<=6:
        raise ValueError("max refinements must be 0..6")
    if run_id is None:
        run_id=f'{time.strftime("%Y%m%d-%H%M%S")}-{sample["id"]}-{strategy}'
    import re
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,100}",run_id):
        raise ValueError("invalid run id")
    run=ROOT/"runs"/run_id;run.mkdir(parents=True,exist_ok=True)
    config={"sample":sample,"strategy":strategy,"max_refinements":max_refinements,"max_calls":max_calls,"max_tokens":max_tokens,
            "max_seconds":max_seconds,"settings":settings.public(),"prompt_version":PROMPT_VERSION,"skill_commit":SKILL_COMMIT,"workflow_version":"0.1.0"}
    if refinement_scope!="targeted":
        config["refinement_scope"]=refinement_scope
    if (run/"config.json").exists():
        previous=json.loads((run/"config.json").read_text(encoding="utf-8"))
        def effective_config(value):
            # Attribution corrections do not change immutable image input.
            return {**value,"sample":{k:value["sample"].get(k) for k in ["id","title","image","sha256","split"]}}
        if effective_config(previous)!=effective_config(config):
            raise ValueError("RUN_ID_CONFIG_MISMATCH")
        if (run/"result.json").exists():
            return run
    else:
        write_json(run/"config.json",config)
    reference=run/"reference.jpg"
    if not reference.exists():
        shutil.copyfile(ROOT/sample["image"],reference)
    if hashlib.sha256(reference.read_bytes()).hexdigest()!=sample["sha256"]:
        raise ValueError("REFERENCE_CHECKSUM_MISMATCH")
    api=Provider(settings,run,max_calls,max_tokens,max_seconds)
    started=time.monotonic()

    def timed(stage,fn):
        def node(state):
            t=time.monotonic();api.trace("stage_start",stage=stage,iteration=state.get("iteration",0))
            if stage!="finalize" and api.elapsed()>=max_seconds:
                raise BudgetExceeded("TIME_BUDGET")
            result=fn(state)
            api.save_usage()
            api.trace("stage_complete",stage=stage,seconds=time.monotonic()-t)
            print(json.dumps({"run":run.name,"stage":stage,"iteration":result.get("iteration",state.get("iteration",0)),"seconds":round(time.monotonic()-t,2)},ensure_ascii=True),flush=True)
            return result
        return node

    def intake(state):
        skills.intake(reference,run)
        return {"iteration":0,"candidates":[],"best":None,"camera":{"azimuth":35,"elevation":12}}

    def analyze(state):
        if strategy=="direct":
            return {"spec":{"mode":"direct-image-to-code","uncertainty":["Unobserved sides and dimensions unknown."]}}
        prompt="""Analyze the target building, before writing any geometry code. Return a structured building research specification (not native ObjectSculptSpec) with EXACT keys:
name, suitability ('usable' or 'insufficient_evidence'), observed_floors (integer or null), components (3..80 objects: id, description, evidence observed/inferred/unknown, confidence 0..1, source region such as 'reference upper left', parent id or null), repetitions (array of count/spacing/placement rules), materials (array of id,color,roughness,observed_region), proportions (height/width/depth ratios with confidence, no false measured units), camera (azimuth, elevation degrees), uncertainty (nonempty array), quality_contract (>=3 concrete identity-defining features that must be present).
Separate observation from inference. Decompose macro mass -> facade modules -> details; count floors/windows where visible. No trees, cars or adjacent structures as building parts. Identify the named target, not everything in the image.
Target: """+sample["title"]+"\n"+skills.context("analysis")
        raw=api.call("analysis",prompt,[reference],settings.vision_model,4500)
        spec=BuildingSpec.model_validate(raw).model_dump()
        write_json(run/"spec.json",spec)
        if spec["suitability"]!="usable":
            return {"spec":spec,"stop_reason":"insufficient_evidence"}
        return {"spec":spec,"camera":spec["camera"]}

    def generate(state):
        prompt=f'Reconstruct {sample["title"]} from the attached real photograph.\n'+FACTORY_CONTRACT
        if strategy=="spec":
            prompt+='\nAuthoritative observations and uncertainties:\n'+json.dumps(state["spec"],ensure_ascii=False)
        prompt+='\nGeometry guidance (selected upstream excerpt):\n'+skills.context("code")
        raw=api.call("generate",prompt,[reference],settings.code_model,9000)
        source=raw["source"]
        validate_source(source)
        folder=run/"iteration-00";folder.mkdir(exist_ok=True)
        (folder/"generator.ts").write_text(source,encoding="utf-8")
        write_json(folder/"generation.json",{k:v for k,v in raw.items() if k!="source"})
        camera=raw.get("camera",state["camera"])
        return {"camera":camera,"current":{"iteration":0,"source_sha256":hashlib.sha256(source.encode()).hexdigest()}}

    def execute(state):
        folder=run/f'iteration-{state["iteration"]:02d}'
        candidate=dict(state["current"])
        try:
            output=render(folder/"generator.ts",folder,state["camera"],timeout=min(90,max(1,max_seconds-api.elapsed())))
            candidate.update(output)
            comparison(reference,folder/"reference-view.png",folder/"comparison.jpg")
            multiview(folder)
        except Exception as exc:
            candidate.update({"geometry_passed":False,"error":{"code":str(exc)[:500],"stage":"execute","evidence":str(folder.relative_to(run)),
                "recovery":"Inspect compile/runtime/geometry evidence; patch source within correction budget."}})
        write_json(folder/"candidate.json",candidate)
        return {"current":candidate}

    def evaluate(state):
        candidate=dict(state["current"])
        folder=run/f'iteration-{state["iteration"]:02d}'
        if candidate.get("geometry_passed"):
            prompt="""Compare the actual reference photo with the procedural render and standard multi-view sheet. First attachment: reference/render comparison, second: front/back/left/right/isometric. Judge ONLY the target building, not background, landscape or photograph lighting. Hidden sides are plausibility only. Camera mismatch is a camera defect, never a reason to distort geometry.
Return JSON with EXACT keys:
scores: object of six numbers 0..1 named mass,facade,roof,details,materials,proportions;
critical_defects: array of severe identity/structure errors (empty only if no severe defects);
defects: array of objects {component,severity ('critical','major','minor'),cause ('geometry','camera','material','spec'),fix} with actionable local fixes;
matched_features: array; inferred_regions: array; confidence: 0..1.
Do not award high scores because the model looks attractive. Missing floors, roof shape, distinctive cantilevers or facade rhythms must depress the corresponding scores. This is an uncalibrated research review, not certification. Do not fabricate IoU, SSIM or real dimensions.
Target: """+sample["title"]+"\nSpecification: "+json.dumps(state["spec"],ensure_ascii=False)
            raw=api.call("evaluate",prompt,[folder/"comparison.jpg",folder/"multiview.jpg"],settings.review_model,3500)
            review=Review.model_validate(raw)
            candidate.update({"review":review.model_dump(),"quality":review.quality})
            write_json(folder/"review.json",review.model_dump())
        else:
            # Deterministic errors are sufficient repair evidence; avoid a vision call.
            detail=[]
            for file in ["compile.log","geometry.json","runtime-result.json"]:
                if (folder/file).exists():
                    detail.append((folder/file).read_text(encoding="utf-8")[:3500])
            candidate["repair_evidence"]="\n".join(detail)
        best=state.get("best")
        if prefer(candidate,best):
            best=candidate
            candidate["selection"]="retained"
        else:
            candidate["selection"]="rejected_or_invalid"
        candidates=state.get("candidates",[])+[candidate]
        write_json(folder/"candidate.json",candidate)
        write_json(run/"progress.json",{"candidates":candidates,"best_iteration":best["iteration"] if best else None})
        return {"current":candidate,"best":best,"candidates":candidates}

    def refine(state):
        prior=run/f'iteration-{state["iteration"]:02d}'
        source=(prior/"generator.ts").read_text(encoding="utf-8")
        candidate=state["current"]
        feedback=candidate.get("review",candidate.get("repair_evidence",candidate.get("error")))
        if refinement_scope=="camera" and candidate.get("geometry_passed"):
            prompt="""Fit only the comparison camera to the target building photograph. Keep geometry, materials and source EXACTLY unchanged. The comparison currently uses a camera hypothesis, not calibrated alignment. Return JSON {"camera":{"azimuth":degrees,"elevation":degrees},"reason":"visible evidence for change"}. Azimuth 0 sees the +Z front, +35 sees front/right, -35 sees front/left. Elevation 0 is eye level at building center, positive values look down. Diagnose the photo and current render's visible sides, roof visibility and vertical convergence. Do not compensate for wrong geometry by an extreme angle. Use azimuth -80..80 and elevation -15..30.
Current camera: """+json.dumps(state["camera"])+"\nTarget: "+sample["title"]+"\nReview: "+json.dumps(feedback,ensure_ascii=False)
            raw=api.call("refine-camera",prompt,[reference,prior/"comparison.jpg"],settings.code_model,1500)
            cam=raw.get("camera",{})
            if not isinstance(cam.get("azimuth"),(int,float)) or not isinstance(cam.get("elevation"),(int,float)) or not -80<=cam["azimuth"]<=80 or not -15<=cam["elevation"]<=30:
                raise ValueError("INVALID_CAMERA_CORRECTION")
            iteration=state["iteration"]+1
            folder=run/f'iteration-{iteration:02d}';folder.mkdir(exist_ok=True)
            (folder/"generator.ts").write_text(source,encoding="utf-8")
            write_json(folder/"patch.json",{**raw,"edits":[],"scope":"camera-only; geometry unchanged"})
            return {"iteration":iteration,"camera":cam,"current":{"iteration":iteration,"source_sha256":hashlib.sha256(source.encode()).hexdigest(),"patch_reason":raw.get("reason","")}}
        prompt="""Correct the existing procedural building generator using a few precise local edits. Preserve already correct parts. Fix the largest structural error first. No full regeneration. Return JSON {"edits":[{"old":"exact unique source substring","new":"replacement"}],"reason":"why","camera":{"azimuth":number,"elevation":number}}. Use at most 8 edits; old substrings must match exactly once. Camera-only defects should change camera values, not geometry; if only camera change use edits=[] and camera. You must keep the factory contract and closed watertight meshes. Never introduce open PlaneGeometry.
"""+FACTORY_CONTRACT+"\nTarget: "+sample["title"]+"\nFeedback:\n"+json.dumps(feedback,ensure_ascii=False)+"\nCurrent source:\n"+source
        images=[reference]
        if (prior/"comparison.jpg").exists(): images.append(prior/"comparison.jpg")
        raw=api.call("refine",prompt,images,settings.code_model,6500)
        if not raw.get("edits") and isinstance(raw.get("camera"),dict):
            corrected=source
        else:
            corrected=apply_edits(source,raw.get("edits"))
        iteration=state["iteration"]+1
        folder=run/f'iteration-{iteration:02d}';folder.mkdir(exist_ok=True)
        (folder/"generator.ts").write_text(corrected,encoding="utf-8")
        write_json(folder/"patch.json",raw)
        return {"iteration":iteration,"camera":raw.get("camera",state["camera"]),
                "current":{"iteration":iteration,"source_sha256":hashlib.sha256(corrected.encode()).hexdigest(),"patch_reason":raw.get("reason","")}}

    def next_step(state):
        if state["iteration"]>=max_refinements:
            return "finalize"
        if len(state.get("candidates",[]))>=2:
            a,b=state["candidates"][-2:]
            if a.get("source_sha256")==b.get("source_sha256") and a.get("error")==b.get("error"):
                return "finalize"
        try:
            api.check(16000)
        except BudgetExceeded:
            return "finalize"
        return "refine"

    def finalize(state):
        write_result(state,state.get("stop_reason","refinement_budget_or_plateau"))
        return {"stop_reason":state.get("stop_reason","refinement_budget_or_plateau")}

    def write_result(state,reason):
        best=state.get("best")
        progress=run/"progress.json"
        if not state.get("candidates") and progress.exists():
            persisted=json.loads(progress.read_text(encoding="utf-8"))
            state={**state,**persisted}
            best=next((c for c in state["candidates"] if c["iteration"]==persisted.get("best_iteration")),None)
        result={"status":"partial" if best else ("insufficient_evidence" if reason=="insufficient_evidence" else "failed"),
            "stop_reason":reason,"best_iteration":best["iteration"] if best else None,"candidates":state.get("candidates",[]),
            "seconds":api.elapsed(),"limitations":["Single photo does not constrain hidden geometry or true dimensions.",
            "Feature scores are uncalibrated VLM judgments; no fidelity certification.","Native eight-pass img2threejs baseline incomplete.",
            "Silhouette IoU/SSIM unavailable without verified segmentation and camera alignment."]}
        write_json(run/"result.json",result)
        api.save_usage()
        run_report(run)

    builder=StateGraph(State)
    for name,fn in [("intake",intake),("analyze",analyze),("generate",generate),("execute",execute),("evaluate",evaluate),("refine",refine),("finalize",finalize)]:
        builder.add_node(name,timed(name,fn))
    builder.add_edge(START,"intake");builder.add_edge("intake","analyze")
    builder.add_conditional_edges("analyze",lambda s:"finalize" if s.get("stop_reason") else "generate")
    builder.add_edge("generate","execute");builder.add_edge("execute","evaluate")
    builder.add_conditional_edges("evaluate",next_step)
    builder.add_edge("refine","execute");builder.add_edge("finalize",END)
    with sqlite3.connect(run/"checkpoint.sqlite",check_same_thread=False) as conn:
        saver=SqliteSaver(conn);graph=builder.compile(checkpointer=saver)
        graph_config={"configurable":{"thread_id":run_id},"recursion_limit":50}
        checkpoint=graph.get_state(graph_config)
        initial=None if checkpoint.values else {"sample":sample,"strategy":strategy,"max_refinements":max_refinements}
        try:
            graph.invoke(initial,graph_config)
        except Exception as exc:
            state=dict(graph.get_state(graph_config).values)
            reason=f'{type(exc).__name__}: {str(exc)[:350]}'
            api.trace("run_error",reason=reason,recovery="Inspect traces; failed terminal result retained. Use a new run id for a changed configuration.")
            write_result(state,reason)
    return run
