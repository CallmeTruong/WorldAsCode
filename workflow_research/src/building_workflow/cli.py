import argparse
import json
import subprocess
from pathlib import Path
from .config import ROOT, Settings
from .provider import Provider
from .samples import download_samples
from .workflow import run_job
from .report import aggregate
from .runtime import render
from .skills import verify_pin


def main():
    parser=argparse.ArgumentParser(description="Bounded real-image procedural building experiments")
    sub=parser.add_subparsers(dest="command",required=True)
    sub.add_parser("doctor");sub.add_parser("samples");sub.add_parser("report")
    coverage=sub.add_parser('imagery',help='Bounded official-provider catalog discovery; no paid orders')
    coverage.add_argument('--bbox',nargs=4,type=float,required=True,metavar=('WEST','SOUTH','EAST','NORTH'))
    coverage.add_argument('--output',type=Path,default=ROOT/'reports/urban/provider-coverage.json')
    u=sub.add_parser('urban',help='Bounded four-cell OSM and reference-style pilot')
    u.add_argument('--style-dir',type=Path);u.add_argument('--run-id',default='district1-pilot')
    u.add_argument('--max-calls',type=int,default=12);u.add_argument('--max-tokens',type=int,default=180000)
    u.add_argument('--max-seconds',type=int,default=2400);u.add_argument('--rerender',action='store_true')
    u.add_argument('--reuse-run-id',help='Reuse a previously API-generated building source in a new experiment')
    u.add_argument('--object-refs',type=Path,help='Manifest of factual reference images mapped to object IDs')
    u.add_argument('--size',type=float,default=400);u.add_argument('--longitude',type=float,default=106.702);u.add_argument('--latitude',type=float,default=10.775)
    u.add_argument('--grid',type=int,default=2);u.add_argument('--max-visual-refinements',type=int,choices=[0,1,2],default=1)
    u.add_argument('--resume-code-update',action='store_true',help='Archive a changed implementation hash while resuming unchanged inputs and budget')
    u.add_argument('--reference-url',help='Local Cesium evidence service; measure mesh heights and observe shared street features before generation')
    u.add_argument('--scene-refs',type=Path,help='Shared factual scene views, held-out view and optional target details')
    u.add_argument('--osm-snapshot',type=Path,help='OSM XML snapshot covering the selected AOI')
    u.add_argument('--tree-observations',type=Path,help='Georeferenced approximate crown observations; shapes remain seeded')
    strict=sub.add_parser('urban-refine',help='Strict GPT Sol target refinement on a prepared isolated run')
    strict.add_argument('--run',type=Path,required=True);strict.add_argument('--evidence',type=Path,required=True)
    strict.add_argument('--object-id',required=True);strict.add_argument('--repairs',type=int,choices=range(5),default=2)
    strict.add_argument('--max-calls',type=int,default=12);strict.add_argument('--max-tokens',type=int,default=250000)
    strict.add_argument('--max-seconds',type=int,default=1800)
    joint=sub.add_parser('urban-scene',help='Joint whole-AOI generation with optional approximate materials')
    joint.add_argument('--run-id',required=True);joint.add_argument('--parent-run',required=True);joint.add_argument('--evidence-run',required=True)
    joint.add_argument('--repairs',type=int,choices=range(4),default=2)
    joint.add_argument('--seed-scene',action='store_true');joint.add_argument('--expanded-context',action='store_true')
    coordinated=sub.add_parser('urban-workflow',help='Coordinated observer/critic/coding nodes with real render feedback')
    coordinated.add_argument('--run-id',required=True);coordinated.add_argument('--parent-run',required=True);coordinated.add_argument('--evidence-run',required=True)
    coordinated.add_argument('--repairs',type=int,choices=range(5),default=3);coordinated.add_argument('--resume',action='store_true')
    p=sub.add_parser("run")
    p.add_argument("--sample",required=True);p.add_argument("--strategy",choices=["direct","spec"],default="spec")
    p.add_argument("--max-refinements",type=int,default=1);p.add_argument("--run-id")
    p.add_argument("--refinement-scope",choices=["targeted","camera"],default="targeted")
    p.add_argument("--max-calls",type=int,default=12);p.add_argument("--max-tokens",type=int,default=100000)
    p.add_argument("--max-seconds",type=int,default=900)
    p=sub.add_parser("render");p.add_argument("source",type=Path);p.add_argument("output",type=Path);p.add_argument("--camera",type=Path)
    args=parser.parse_args()
    if args.command=='imagery':
        from .urban.imagery import discover_imagery
        result=discover_imagery(args.bbox,args.output)
        print(json.dumps({'output':str(args.output),'providers':[{'provider':p['provider'],'status':p['status'],'candidates':len(p['assets'])} for p in result['providers']]}))
    elif args.command=='urban-workflow':
        import re
        from .urban.coordinated import run_coordinated
        for name in (args.run_id,args.parent_run,args.evidence_run):
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,80}',name):parser.error('invalid run name')
        result=run_coordinated(ROOT/'runs/urban'/args.parent_run,ROOT/'runs/urban'/args.evidence_run,ROOT/'runs/urban'/args.run_id,args.repairs,args.resume)
        print(json.dumps({'report':str(ROOT/'runs/urban'/args.run_id/'index.html'),'accepted':result['accepted'],'status':result['status']}))
    elif args.command=='urban-scene':
        import re
        from .urban.scene_first import run_scene_first
        for name in (args.run_id,args.parent_run,args.evidence_run):
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,80}',name):parser.error('invalid run name')
        result=run_scene_first(ROOT/'runs/urban'/args.parent_run,ROOT/'runs/urban'/args.evidence_run,ROOT/'runs/urban'/args.run_id,args.repairs,args.seed_scene,args.expanded_context)
        print(json.dumps({'report':str(ROOT/'runs/urban'/args.run_id/'index.html'),'accepted':result['accepted'],'status':result['status']}))
    elif args.command=='urban-refine':
        from .urban.strict_loop import run_target,write_strict_report
        from .urban.report import viewer_files
        settings=Settings.load();settings.model=settings.vision_model=settings.code_model=settings.review_model='gpt-6-sol'
        run=args.run.resolve();api=Provider(settings,run,args.max_calls,args.max_tokens,args.max_seconds,max_attempts=1)
        try:
            result=run_target(run,args.evidence.resolve(),args.object_id,api,args.repairs)
            viewer_files(run);write_strict_report(run)
            print(json.dumps({'report':str(run/'index.html'),'accepted':result['accepted'],'status':result['status']}))
        finally:api.save_usage();api.client.close()
    elif args.command=='urban':
        from .urban.runner import run_urban
        run=run_urban(args.style_dir,args.run_id,args.max_calls,args.max_tokens,args.max_seconds,args.rerender,args.reuse_run_id,args.object_refs,args.size,args.longitude,args.latitude,args.grid,args.max_visual_refinements,args.resume_code_update,args.osm_snapshot,args.tree_observations,args.scene_refs,args.reference_url)
        print(str(run/'index.html'))
    elif args.command=="doctor":
        import httpx
        from playwright.sync_api import sync_playwright
        settings=Settings.load()
        response=httpx.get(settings.base_url+"/models",headers={"Authorization":"Bearer "+settings.api_key,"User-Agent":"Mozilla/5.0"},timeout=30)
        response.raise_for_status()
        models=[m["id"] for m in response.json().get("data",[])]
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True,chromium_sandbox=True)
            version=browser.version;browser.close()
        print(json.dumps({"configuration":settings.public(),"models":models,"selected_available":settings.model in models,
            "upstream_commit":verify_pin(),"chromium":version},indent=2))
    elif args.command=="samples":
        print(json.dumps(download_samples(),indent=2,ensure_ascii=True))
    elif args.command=="run":
        manifest=json.loads((ROOT/"data/samples.json").read_text(encoding="utf-8"))
        sample=next((s for s in manifest if s["id"]==args.sample),None)
        if sample is None:
            parser.error("unknown sample id")
        run=run_job(Settings.load(),sample,args.strategy,args.max_refinements,args.run_id,args.max_calls,args.max_tokens,args.max_seconds,args.refinement_scope)
        aggregate()
        print(str(run/"index.html"))
        status=json.loads((run/"result.json").read_text(encoding="utf-8"))["status"]
        if status=="failed":
            raise SystemExit(2)
        if status=="insufficient_evidence":
            raise SystemExit(3)
    elif args.command=="render":
        camera_path=args.camera or args.source.parent/"camera.json"
        camera=json.loads(camera_path.read_text()) if camera_path.exists() else None
        print(json.dumps(render(args.source,args.output,camera),indent=2))
    else:
        print(json.dumps(aggregate(),indent=2))


if __name__=="__main__":
    main()
