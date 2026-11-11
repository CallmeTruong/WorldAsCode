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
    p=sub.add_parser("run")
    p.add_argument("--sample",required=True);p.add_argument("--strategy",choices=["direct","spec"],default="spec")
    p.add_argument("--max-refinements",type=int,default=1);p.add_argument("--run-id")
    p.add_argument("--refinement-scope",choices=["targeted","camera"],default="targeted")
    p.add_argument("--max-calls",type=int,default=12);p.add_argument("--max-tokens",type=int,default=100000)
    p.add_argument("--max-seconds",type=int,default=900)
    p=sub.add_parser("render");p.add_argument("source",type=Path);p.add_argument("output",type=Path);p.add_argument("--camera",type=Path)
    args=parser.parse_args()
    if args.command=="doctor":
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
