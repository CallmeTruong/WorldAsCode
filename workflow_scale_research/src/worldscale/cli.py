import argparse
import json
from pathlib import Path

from .artifacts import write_json
from .config import ROOT, Settings


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Native img2threejs + semantic world research workflow"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("demo")
    p.add_argument("--run", type=Path, default=ROOT / "runs/semantic-demo")
    p = sub.add_parser("native")
    p.add_argument("--reference", type=Path, required=True)
    p.add_argument("--styles", type=Path)
    p.add_argument("--context", type=Path, nargs="*", default=[])
    p.add_argument("--evidence", type=Path, help="Validated georeferenced evidence bundle")
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--max-calls", type=int, default=10)
    p.add_argument("--max-tokens", type=int, default=240000)
    p = sub.add_parser(
        "evidence",
        help="Build a georeferenced evidence bundle from an OSM outline and a capture folder",
    )
    p.add_argument("--osm", type=Path, required=True)
    p.add_argument("--way", required=True, help="OSM way id of the building outline")
    p.add_argument("--captures", type=Path, required=True,
                   help="Folder with capture-manifest.json and one PNG per view")
    p.add_argument("--ground-height", type=float, required=True,
                   help="Ground height in the capture's vertical datum, metres")
    p.add_argument("--height", type=float, required=True,
                   help="Rough building height above ground, metres (a prior; it is refitted)")
    p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser(
        "massing", help="Fit and compile one building from a georeferenced evidence bundle"
    )
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--program", type=Path, help="JSON overrides for detail fields only")
    p.add_argument(
        "--vision-details",
        action="store_true",
        help="Spend one bounded model call on storeys/bays/dormers/chimneys",
    )
    p = sub.add_parser(
        "design",
        help="Agent writes a kit design script for one measured site in a given style",
    )
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--styles", type=Path, required=True)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--max-revisions", type=int, default=1)
    p.add_argument("--max-tokens", type=int, default=220000)
    p.add_argument("--adaptive-kit", action="store_true", help="Develop isolated kit candidates after an unaccepted design")
    p.add_argument("--max-kit-cycles", type=int, default=1)
    p.add_argument("--kit-version", type=Path, help="Verified active-kit.json to pin for this run")
    p.add_argument('--publish-kit',action=argparse.BooleanOptionalAction,default=None)
    p.add_argument('--kit-grant')
    p = sub.add_parser('recover-design',help='Recover completed artifacts without model retries')
    p.add_argument('--run',type=Path,required=True)
    p = sub.add_parser("adapt-kit", help="Develop and evaluate isolated kit versions from an existing design run")
    p.add_argument("--source-run", type=Path, required=True)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--max-cycles", type=int, default=1)
    p.add_argument("--max-tokens", type=int, default=220000)
    p.add_argument('--publish-kit',action=argparse.BooleanOptionalAction,default=None)
    p.add_argument('--kit-grant')
    p=sub.add_parser('kit-library',help='Shared kit registry, host-held permissions and release lifecycle')
    p.add_argument('action',choices=['init','grant','revoke','submit','validate','promote','rollback','search','status'])
    p.add_argument('--library',type=Path,default=ROOT/'kit_library')
    p.add_argument('--package',default='buildings')
    p.add_argument('--subject',default='workflow')
    p.add_argument('--actions',nargs='+',default=[])
    p.add_argument('--hours',type=int,default=720)
    p.add_argument('--token')
    p.add_argument('--manifest',type=Path)
    p.add_argument('--submission')
    p.add_argument('--channel',choices=['incubating','stable'],default='incubating')
    p.add_argument('--version')
    p.add_argument('--heldout-runs',type=Path,nargs='*',default=[])
    p.add_argument('--set-default',action='store_true')
    p.add_argument('--configure-workflow',action='store_true')
    p.add_argument('--query',default='')
    p = sub.add_parser(
        "heights",
        help="Sample a dense height grid for an evidence bundle from a running reference viewer",
    )
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--url", default="http://127.0.0.1:8767/")
    p.add_argument("--step", type=float, default=0.6)
    p = sub.add_parser(
        "district", help="Compile every OSM building outline into one shared-frame draft"
    )
    p.add_argument("--osm", type=Path, required=True)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--fitted", type=Path, nargs="*", default=[])
    p = sub.add_parser("status")
    p.add_argument("--run", type=Path, required=True)
    p = sub.add_parser("compose")
    p.add_argument("--world", type=Path, required=True)
    p.add_argument("--factories", type=Path)
    p.add_argument("--run", type=Path, required=True)
    p = sub.add_parser("serve")
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--port", type=int, default=8770)
    args = parser.parse_args(argv)
    if args.command=='kit-library':
        from .kit_library import Library

        library=Library(args.library)
        registry=library.initialize()
        action=args.action
        if action in ('init','status'):
            value=registry
        elif action=='grant':
            value={'grant':library.grant(args.subject,[args.package],args.actions,args.hours)}
            if args.configure_workflow:
                if args.subject!='workflow' or not {'submit','promote-incubating','set-default'}<=set(args.actions):
                    parser.error('Workflow profile requires subject workflow and submit/promote-incubating/set-default')
                write_json(args.library/'workflow-profile.json',{'auto_publish':True,'grant':value['grant']})
        elif action=='revoke':
            library.revoke(args.token)
            value={'revoked':True}
        elif action=='submit':
            value=library.submit(args.manifest,args.package,args.token,args.subject)
        elif action=='validate':
            value=library.validate(args.submission,args.heldout_runs)
        elif action=='promote':
            value=library.promote(args.submission,args.channel,args.token,args.subject,args.set_default)
        elif action=='rollback':
            value=library.rollback(args.package,args.channel,args.version,args.token,args.subject)
        else:
            value=library.search(args.query)
        print(json.dumps(value,ensure_ascii=False))
        return 0
    if args.command=='recover-design':
        from .design import recover_design

        print(json.dumps(recover_design(args.run)))
        return 2
    if args.command == "adapt-kit":
        from .adaptive import evolve_design

        profile_path=ROOT/'kit_library/workflow-profile.json'
        profile=json.loads(profile_path.read_text(encoding='utf-8')) if profile_path.exists() else {}
        result = evolve_design(args.source_run, args.run, Settings.load(), args.max_cycles, args.max_tokens,
            publish_kit=profile.get('auto_publish',False) if args.publish_kit is None else args.publish_kit,
            kit_grant=args.kit_grant or profile.get('grant'))
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("accepted") else 2
    if args.command == "demo":
        from .browser import bundle, capture
        from .demo import demo_world

        folder = bundle(args.run, world=demo_world())
        r = capture(folder)
        print(
            json.dumps(
                {
                    "path": str(folder),
                    "passed": r["passed"],
                    "triangles": r["manifest"]["triangles"],
                    "semantic_probes": r["manifest"]["probes"],
                    "state_preserves_geometry": r["state_preserves_geometry"],
                },
                ensure_ascii=False,
            )
        )
        return 0 if r["passed"] else 2
    if args.command == "evidence":
        from . import georef

        ring, tags = georef.osm_way(args.osm, args.way)
        manifest = json.loads((args.captures / "capture-manifest.json").read_text(encoding="utf-8"))
        kept = {k: tags[k] for k in ("building:levels", "roof:shape", "building:architecture",
                                     "height", "building") if k in tags}
        evidence = georef.build_evidence(
            args.out, ring, manifest, args.captures, args.ground_height, args.height,
            "way/" + str(args.way), tags.get("name:en", tags.get("name", "")), kept,
            height_source="caller-supplied prior; refitted from silhouettes or the height field",
        )
        print(json.dumps({"path": str(args.out / "evidence.json"),
                          "views": [v["id"] for v in evidence["views"]],
                          "footprint_vertices": len(evidence["footprint"])}))
        return 0
    if args.command == "massing":
        from .pipeline import run_massing

        settings = None
        if args.vision_details:
            settings = Settings.load()
            if not settings.api_key or not settings.base_url:
                parser.error("--vision-details needs OPENAI_BASE_URL and OPENAI_API_KEY")
        result = run_massing(args.evidence, args.run, args.program, settings)
        print(json.dumps({k: v for k, v in result.items() if k != "massing"} | {
            "mean_iou": result["massing"]["mean_iou"],
            "min_iou": result["massing"]["min_iou"],
            "massing_passed": result["massing"]["passed"],
        }, ensure_ascii=False))
        return 0 if result["browser_passed"] else 2
    if args.command == "design":
        from .design import run_design

        settings = Settings.load()
        if not settings.api_key or not settings.base_url:
            parser.error("OPENAI_BASE_URL and OPENAI_API_KEY required in workspace .env")
        styles = sorted(
            p for p in args.styles.glob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png")
        )
        if not 1 <= len(styles) <= 3:
            parser.error("Provide one to three style images")
        result = run_design(
            args.evidence, styles, args.run, settings, args.max_revisions, args.max_tokens,
            adaptive_kit=args.adaptive_kit, max_kit_cycles=args.max_kit_cycles,
            kit_version=args.kit_version,
            publish_kit=(json.loads((ROOT/'kit_library/workflow-profile.json').read_text(encoding='utf-8')).get('auto_publish',False)
                         if args.publish_kit is None and (ROOT/'kit_library/workflow-profile.json').exists() else bool(args.publish_kit)),
            kit_grant=args.kit_grant or (json.loads((ROOT/'kit_library/workflow-profile.json').read_text(encoding='utf-8')).get('grant')
                                         if (ROOT/'kit_library/workflow-profile.json').exists() else None),
        )
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["status"] == "designed" else 2
    if args.command == "heights":
        from . import dsm, georef

        evidence = georef.load_evidence(args.evidence)
        out = Path(evidence["path"]).parent / "heights.json"
        record = dsm.capture(evidence, out, args.url, args.step)
        missing = sum(h is None for h in record["heights_above_ground"])
        print(json.dumps({"path": str(out), "samples": len(record["heights_above_ground"]),
                          "missing": missing, "source": record["source"]}))
        return 0
    if args.command == "district":
        from .pipeline import run_district

        result = run_district(args.osm, args.run, args.fitted)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["browser_passed"] else 2
    if args.command == "native":
        from .workflow import Workflow

        settings = Settings.load()
        if not settings.api_key or not settings.base_url:
            parser.error(
                "OPENAI_BASE_URL and OPENAI_API_KEY required in workspace .env"
            )
        styles = (
            sorted(
                p
                for p in args.styles.glob("*")
                if p.suffix.lower() in (".jpg", ".jpeg", ".png")
            )
            if args.styles
            else []
        )
        if len(styles) > 6:
            parser.error(
                "At most 6 style images per pilot; curate the style folder to control cost"
            )
        result = Workflow(
            args.run, settings, args.max_calls, args.max_tokens
        ).run_native(args.reference, styles, args.context, args.evidence)
        print(
            json.dumps(
                {k: v for k, v in result.items() if k != "usage"}, ensure_ascii=False
            )
        )
        return 0 if result.get("accepted") else 2
    if args.command == "compose":
        from .browser import bundle, capture

        world = json.loads(args.world.read_text(encoding="utf-8"))
        factories = (
            json.loads(args.factories.read_text(encoding="utf-8"))
            if args.factories
            else {}
        )
        folder = bundle(args.run, world=world, native_factories=factories)
        report = capture(folder)
        result = {
            "accepted": False,
            "status": "draft-composition",
            "technical_checks_passed": report["passed"],
            "note": "Composition requires independent scene-level visual review; accepted asset quality is not inherited by a whole world.",
        }
        write_json(folder / "result.json", result)
        print(json.dumps(result))
        return 0 if report["passed"] else 2
    if args.command == "status":
        from .native import NativeBridge

        bridge = NativeBridge(args.run)
        bridge.init(
            json.loads((args.run / "inputs.json").read_text())["reference"]["path"]
        )
        print(bridge.next()["stdout"])
        return 0
    if args.command == "serve":
        import http.server
        from functools import partial

        server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", args.port),
            partial(
                http.server.SimpleHTTPRequestHandler, directory=str(args.run.resolve())
            ),
        )
        print(f"Preview: http://127.0.0.1:{args.port}/index.html", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
