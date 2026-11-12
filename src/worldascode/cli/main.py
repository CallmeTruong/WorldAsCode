import argparse
import json
from pathlib import Path

from worldascode.config import CaptureProfile, PublicationProfile, Settings, paths
from worldascode.contracts.execution import RunOutcome, normalize_result
from worldascode.storage.artifacts import write_json


def main(argv=None):
    import os

    preliminary = argparse.ArgumentParser(add_help=False)
    preliminary.add_argument("--config", type=Path)
    selected, _ = preliminary.parse_known_args(argv)
    if selected.config:
        os.environ["WORLDASCODE_CONFIG"] = str(selected.config.resolve())
    from worldascode.config import configuration

    defaults = configuration()[0].get("budgets", {})
    parser = argparse.ArgumentParser(
        description="WorldAsCode evidence-driven reconstruction and kit workflows"
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="TOML configuration file; paths are relative to this file",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("demo")
    p.add_argument("--run", type=Path, default=paths().runs_dir / "semantic-demo")
    p = sub.add_parser(
        "object",
        help="Author, render, review and refine a non-building object or small scene",
    )
    p.add_argument("--brief", type=Path, required=True)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument(
        "--initial-pack",
        type=Path,
        help="Let the developer repair a previous candidate using fresh fixture diagnostics",
    )
    p.add_argument("--references", type=Path, nargs="*", default=[])
    p.add_argument("--styles", type=Path)
    p.add_argument("--pack", type=Path, action="append", default=[])
    p.add_argument(
        "--initial-design",
        type=Path,
        help="Review and refine an existing script without paying to regenerate it",
    )
    p.add_argument(
        "--max-revisions", type=int, default=defaults.get("max_revisions", 1)
    )
    p.add_argument("--max-tokens", type=int, default=defaults.get("max_tokens", 100000))
    p.add_argument(
        "--max-pack-cycles", type=int, default=defaults.get("max_kit_cycles", 1)
    )
    p.add_argument("--require-quality", action="store_true")
    p = sub.add_parser(
        "object-scale",
        help="Measure static replication of a pinned object, preserving nested foliage instances",
    )
    p.add_argument("--source-run", type=Path, required=True)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--count", type=int, default=16)
    p = sub.add_parser(
        "packs", help="Discover, validate and explicitly publish additive part packs"
    )
    p.add_argument("action", choices=["list", "validate", "publish", "publish-run"])
    p.add_argument("--path", type=Path)
    p.add_argument("--out", type=Path)
    p.add_argument("--token")
    p.add_argument("--subject", default="workflow")
    p.add_argument("--channel", choices=["incubating", "stable"], default="incubating")
    p.add_argument("--heldout-runs", type=Path, nargs="*", default=[])
    p = sub.add_parser(
        "evidence",
        help="Build a georeferenced evidence bundle from an OSM outline and a capture folder",
    )
    p.add_argument("--osm", type=Path, required=True)
    p.add_argument("--way", required=True, help="OSM way id of the building outline")
    p.add_argument(
        "--captures",
        type=Path,
        required=True,
        help="Folder with capture-manifest.json and one PNG per view",
    )
    p.add_argument(
        "--ground-height",
        type=float,
        required=True,
        help="Ground height in the capture's vertical datum, metres",
    )
    p.add_argument(
        "--height",
        type=float,
        required=True,
        help="Rough building height above ground, metres (a prior; it is refitted)",
    )
    p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser(
        "massing",
        help="Fit and compile one building from a georeferenced evidence bundle",
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
    p.add_argument(
        "--max-revisions", type=int, default=defaults.get("max_revisions", 1)
    )
    p.add_argument("--max-tokens", type=int, default=defaults.get("max_tokens", 220000))
    p.add_argument(
        "--adaptive-kit",
        action="store_true",
        help="Develop isolated kit candidates after an unaccepted design",
    )
    p.add_argument(
        "--max-kit-cycles", type=int, default=defaults.get("max_kit_cycles", 1)
    )
    p.add_argument(
        "--kit-version", type=Path, help="Verified active-kit.json to pin for this run"
    )
    p.add_argument("--require-quality", action="store_true")
    p.add_argument("--publish-kit", action=argparse.BooleanOptionalAction, default=None)
    p.add_argument("--kit-grant")
    p = sub.add_parser(
        "recover-design", help="Recover completed artifacts without model retries"
    )
    p.add_argument("--run", type=Path, required=True)
    p = sub.add_parser(
        "adapt-kit",
        help="Develop and evaluate isolated kit versions from an existing design run",
    )
    p.add_argument("--source-run", type=Path, required=True)
    p.add_argument("--require-quality", action="store_true")
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--max-cycles", type=int, default=1)
    p.add_argument("--max-tokens", type=int, default=defaults.get("max_tokens", 220000))
    p.add_argument("--publish-kit", action=argparse.BooleanOptionalAction, default=None)
    p.add_argument("--kit-grant")
    p = sub.add_parser(
        "kit-library",
        help="Shared kit registry, host-held permissions and release lifecycle",
    )
    p.add_argument(
        "action",
        choices=[
            "init",
            "grant",
            "revoke",
            "submit",
            "validate",
            "promote",
            "rollback",
            "search",
            "status",
        ],
    )
    p.add_argument("--library", type=Path, default=paths().library_dir)
    p.add_argument("--package", default="buildings")
    p.add_argument("--subject", default="workflow")
    p.add_argument("--actions", nargs="+", default=[])
    p.add_argument("--hours", type=int, default=720)
    p.add_argument("--token")
    p.add_argument("--manifest", type=Path)
    p.add_argument("--submission")
    p.add_argument("--channel", choices=["incubating", "stable"], default="incubating")
    p.add_argument("--version")
    p.add_argument("--heldout-runs", type=Path, nargs="*", default=[])
    p.add_argument("--set-default", action="store_true")
    p.add_argument("--configure-workflow", action="store_true")
    p.add_argument("--query", default="")
    p = sub.add_parser(
        "heights",
        help="Sample a dense height grid for an evidence bundle from a running reference viewer",
    )
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--url", default=CaptureProfile.load().viewer_url)
    p.add_argument("--step", type=float, default=0.6)
    p = sub.add_parser(
        "district",
        help="Compile every OSM building outline into one shared-frame draft",
    )
    p.add_argument("--osm", type=Path, required=True)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--fitted", type=Path, nargs="*", default=[])
    p = sub.add_parser("compose")
    p.add_argument("--world", type=Path, required=True)
    p.add_argument("--factories", type=Path)
    p.add_argument("--run", type=Path, required=True)
    p = sub.add_parser("serve")
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--port", type=int, default=8770)
    p = sub.add_parser(
        "reference-serve", help="Start the packaged Google/Cesium SDK reference viewer"
    )
    p.add_argument("--longitude", type=float, required=True)
    p.add_argument("--latitude", type=float, required=True)
    p.add_argument("--port", type=int, default=8767)
    p = sub.add_parser(
        "capture-site",
        help="Capture calibrated multi-view evidence for an OSM building",
    )
    p.add_argument("--osm", type=Path, required=True)
    p.add_argument("--way", required=True)
    p.add_argument("--height", type=float, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--url", default=None)
    p = sub.add_parser("config", help="Inspect effective configuration without secrets")
    p.add_argument("action", choices=["show"])
    sub.add_parser(
        "doctor", help="Check installed runtime dependencies without provider requests"
    )
    args = parser.parse_args(argv)
    if args.command == "object-scale":
        from worldascode.workflows.scale_probe import probe_object

        result = probe_object(args.source_run, args.run, args.count)
        print(json.dumps(result))
        return 0 if result["passed"] else 2
    if args.command == "packs":
        from worldascode.kits import packs

        if args.action == "list":
            print(
                json.dumps(
                    packs.discover(channel=args.channel), ensure_ascii=False, indent=2
                )
            )
            return 0
        if args.path is None:
            parser.error("--path required")
        if args.action == "publish-run":
            from worldascode.workflows.objects import publish_candidates

            print(
                json.dumps(
                    publish_candidates(
                        args.path,
                        args.token,
                        args.subject,
                        args.channel,
                        args.heldout_runs,
                    )
                )
            )
            return 0
        if args.action == "validate":
            if args.out is None:
                parser.error("--out required for fresh validation artifacts")
            result = packs.validate(args.path, args.out)
            print(json.dumps(result))
            return 0 if result["passed"] else 2
        result = packs.promote(
            args.path, args.token, args.subject, args.channel, args.heldout_runs
        )
        print(
            json.dumps({k: v for k, v in result.items() if k not in {"api", "fixture"}})
        )
        return 0
    if args.command == "object":
        from worldascode.workflows.objects import run_object

        styles = (
            sorted(
                p
                for p in args.styles.iterdir()
                if p.suffix.lower() in {".png", ".jpg", ".jpeg"}
            )
            if args.styles
            else []
        )
        if len(styles) > 6:
            parser.error("At most six style references per object run")
        result = run_object(
            json.loads(args.brief.read_text(encoding="utf-8")),
            args.run,
            Settings.load(),
            args.references,
            styles,
            args.pack,
            args.max_revisions,
            args.max_tokens,
            args.max_pack_cycles,
            args.initial_design,
            args.initial_pack,
        )
        print(json.dumps(result, ensure_ascii=False))
        return RunOutcome.model_validate(result).exit_code(args.require_quality)
    if args.command == "config":
        document, _ = configuration()
        settings = Settings.load()
        print(
            json.dumps(
                {
                    "paths": {
                        "data_dir": str(paths().data_dir),
                        "node_modules": str(paths().node_modules),
                    },
                    "models": {"default": settings.model, **settings.role_models},
                    "providers": {
                        name: {
                            "base_url": entry.get("base_url"),
                            "api_key_env": entry.get("api_key_env"),
                        }
                        for name, entry in settings.providers.items()
                    },
                    "default_endpoint": settings.base_url,
                    "credential_configured": bool(settings.api_key),
                    "budgets": document.get("budgets", {}),
                    "capture": document.get("capture", {}),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.command == "doctor":
        import shutil

        report = {
            "python": True,
            "node": bool(shutil.which("node")),
            "runtime": paths().runtime_dir.is_dir(),
            "modules": {
                name: (paths().node_modules / name / "package.json").is_file()
                for name in ("three", "esbuild", "acorn", "cesium")
            },
        }
        print(json.dumps(report, indent=2))
        return (
            0
            if report["node"] and report["runtime"] and all(report["modules"].values())
            else 2
        )
    if args.command == "reference-serve":
        from worldascode.adapters.geospatial.reference_server import serve_reference

        serve_reference(args.longitude, args.latitude, args.port)
        return 0
    if args.command == "capture-site":
        from worldascode.adapters.geospatial.capture import capture_site

        result = capture_site(args.osm, args.way, args.out, args.height, args.url)
        print(json.dumps({"object_id": result["object_id"], "path": str(args.out)}))
        return 0
    if args.command == "kit-library":
        from worldascode.kits.registry import Library

        library = Library(args.library)
        registry = library.initialize()
        action = args.action
        if action in ("init", "status"):
            value = registry
        elif action == "grant":
            value = {
                "grant": library.grant(
                    args.subject, [args.package], args.actions, args.hours
                )
            }
            if args.configure_workflow:
                if args.subject != "workflow" or not {
                    "submit",
                    "promote-incubating",
                    "set-default",
                } <= set(args.actions):
                    parser.error(
                        "Workflow profile requires subject workflow and submit/promote-incubating/set-default"
                    )
                write_json(
                    args.library / "workflow-profile.json",
                    {"auto_publish": True, "grant": value["grant"]},
                )
        elif action == "revoke":
            library.revoke(args.token)
            value = {"revoked": True}
        elif action == "submit":
            value = library.submit(
                args.manifest, args.package, args.token, args.subject
            )
        elif action == "validate":
            value = library.validate(args.submission, args.heldout_runs)
        elif action == "promote":
            value = library.promote(
                args.submission,
                args.channel,
                args.token,
                args.subject,
                args.set_default,
            )
        elif action == "rollback":
            value = library.rollback(
                args.package, args.channel, args.version, args.token, args.subject
            )
        else:
            value = library.search(args.query)
        print(json.dumps(value, ensure_ascii=False))
        return 0
    if args.command == "recover-design":
        from worldascode.workflows.reconstruction import recover_design

        print(json.dumps(recover_design(args.run)))
        return 2
    if args.command == "adapt-kit":
        from worldascode.workflows.refinement import evolve_design

        profile = PublicationProfile.load()
        result = evolve_design(
            args.source_run,
            args.run,
            Settings.load(),
            args.max_cycles,
            args.max_tokens,
            **profile.options(args.publish_kit, args.kit_grant),
        )
        result = normalize_result(result)
        print(json.dumps(result, ensure_ascii=False))
        return RunOutcome.from_legacy(result).exit_code(args.require_quality)
    if args.command == "demo":
        from worldascode.adapters.rendering.browser import bundle, capture
        from worldascode.examples.semantic_demo import demo_world

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
        import worldascode.evidence.georeference as georef

        ring, tags = georef.osm_way(args.osm, args.way)
        manifest = json.loads(
            (args.captures / "capture-manifest.json").read_text(encoding="utf-8")
        )
        kept = {
            k: tags[k]
            for k in (
                "building:levels",
                "roof:shape",
                "building:architecture",
                "height",
                "building",
            )
            if k in tags
        }
        evidence = georef.build_evidence(
            args.out,
            ring,
            manifest,
            args.captures,
            args.ground_height,
            args.height,
            "way/" + str(args.way),
            tags.get("name:en", tags.get("name", "")),
            kept,
            height_source="caller-supplied prior; refitted from silhouettes or the height field",
        )
        print(
            json.dumps(
                {
                    "path": str(args.out / "evidence.json"),
                    "views": [v["id"] for v in evidence["views"]],
                    "footprint_vertices": len(evidence["footprint"]),
                }
            )
        )
        return 0
    if args.command == "massing":
        from worldascode.workflows.massing import run_massing

        settings = None
        if args.vision_details:
            settings = Settings.load()
            if not settings.api_key or not settings.base_url:
                parser.error(
                    "--vision-details needs OPENAI_BASE_URL and OPENAI_API_KEY"
                )
        result = run_massing(args.evidence, args.run, args.program, settings)
        print(
            json.dumps(
                {k: v for k, v in result.items() if k != "massing"}
                | {
                    "mean_iou": result["massing"]["mean_iou"],
                    "min_iou": result["massing"]["min_iou"],
                    "massing_passed": result["massing"]["passed"],
                },
                ensure_ascii=False,
            )
        )
        return 0 if result["browser_passed"] else 2
    if args.command == "design":
        from worldascode.workflows.reconstruction import run_design

        settings = Settings.load()
        if not settings.api_key or not settings.base_url:
            parser.error(
                "OPENAI_BASE_URL and OPENAI_API_KEY required in workspace .env"
            )
        styles = sorted(
            p
            for p in args.styles.glob("*")
            if p.suffix.lower() in (".jpg", ".jpeg", ".png")
        )
        if not 1 <= len(styles) <= 3:
            parser.error("Provide one to three style images")
        result = run_design(
            args.evidence,
            styles,
            args.run,
            settings,
            args.max_revisions,
            args.max_tokens,
            adaptive_kit=args.adaptive_kit,
            max_kit_cycles=args.max_kit_cycles,
            kit_version=args.kit_version,
            **PublicationProfile.load().options(args.publish_kit, args.kit_grant),
        )
        result = normalize_result(result)
        print(json.dumps(result, ensure_ascii=False))
        return RunOutcome.from_legacy(result).exit_code(args.require_quality)
    if args.command == "heights":
        import worldascode.evidence.georeference as georef
        import worldascode.geometry.surface_height as dsm

        evidence = georef.load_evidence(args.evidence)
        out = Path(evidence["path"]).parent / "heights.json"
        record = dsm.capture(evidence, out, args.url, args.step)
        missing = sum(h is None for h in record["heights_above_ground"])
        print(
            json.dumps(
                {
                    "path": str(out),
                    "samples": len(record["heights_above_ground"]),
                    "missing": missing,
                    "source": record["source"],
                }
            )
        )
        return 0
    if args.command == "district":
        from worldascode.workflows.massing import run_district

        result = run_district(args.osm, args.run, args.fitted)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["browser_passed"] else 2
    if args.command == "compose":
        from worldascode.adapters.rendering.browser import bundle, capture

        world = json.loads(args.world.read_text(encoding="utf-8"))
        factories = (
            json.loads(args.factories.read_text(encoding="utf-8"))
            if args.factories
            else {}
        )
        folder = bundle(args.run, world=world, factories=factories)
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
