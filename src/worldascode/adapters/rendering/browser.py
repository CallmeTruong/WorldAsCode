"""Independent browser runtime with network denial and content-hashed captures."""

import base64
import contextlib
import http.server
import io
import json
import subprocess
import threading
import time
from functools import partial
from hashlib import sha256
from pathlib import Path

import numpy as np
from PIL import Image, ImageStat
from playwright.sync_api import sync_playwright

from worldascode.config import ROOT, paths
from worldascode.contracts.world import GeometryProbe, World
from worldascode.evidence.images import (
    detail_sheet,
    evidence_capture,
    render_camera,
    sheet,
)
from worldascode.kits.code import lint
from worldascode.quality.evaluation import measure
from worldascode.storage.artifacts import file_hash, write_json


@contextlib.contextmanager
def serve(directory):
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def end_headers(self):
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; img-src 'self' data: blob:; connect-src 'none'; style-src 'self' 'unsafe-inline'",
            )
            super().end_headers()

    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(Quiet, directory=str(directory))
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def bundle(
    run,
    world=None,
    factory=None,
    factories=None,
    design=None,
    site=None,
    style=None,
    kit_path=None,
    packs=None,
):
    """Bundle a World recipe, owned createModel factory, or kit design script.

    ``packs`` are part packs (see ``kits.packs``) made available to the design.

    Factories export createModel(options) and return a THREE.Object3D. They have
    no dependency on an upstream generator, schema, signature or state machine.
    """
    run = Path(run).resolve()
    run.mkdir(parents=True, exist_ok=True)
    if sum(v is not None for v in (world, factory, design)) != 1:
        raise ValueError("Exactly one reconstruction route required")
    if factories and world is None:
        raise ValueError("FACTORIES_REQUIRE_WORLD")
    runtime = (ROOT / "runtime/viewer.mjs").as_posix()
    if design is not None:
        source = Path(design).resolve()
        from worldascode.kits import packs as pack_library
        from worldascode.kits.context import runtime_slice

        packs = [
            pack_library.pin(pack, run / "selected-packs" / pack["id"])
            for pack in (packs or [])
        ]
        selected = runtime_slice(
            Path(kit_path or ROOT / "runtime/kit.mjs").resolve(),
            source.read_text(encoding="utf-8"),
            run / "selected-runtime",
            pack_parts=pack_library.part_names(packs),
            host_services=pack_library.HOST_SERVICES,
        )
        write_json(run / "site.json", site)
        write_json(
            run / "packs.json",
            [
                {"id": p["id"], "version": p["version"], "sha256": p["sha256"]}
                for p in packs
            ],
        )
        entry = (
            f"import {{design}} from {json.dumps(source.as_posix())};\n"
            f"import {{buildDesign}} from {json.dumps(selected.as_posix())};\n"
            + "".join(
                f"import * as pack{i} from {json.dumps(Path(p['module']).as_posix())};\n"
                for i, p in enumerate(packs)
            )
            + "".join(
                f"for(const name of {json.dumps(p['parts'])})if(typeof pack{i}.parts?.[name]!=='function')throw Error('PACK_PART_MISSING:'+name);\n"
                for i, p in enumerate(packs)
            )
            + f"const root=buildDesign(design,{json.dumps(site)},{json.dumps(style or {})},[{','.join('pack' + str(i) for i in range(len(packs)))}]);\n"
        )
    elif world is not None:
        validated = World.model_validate(world)
        world = validated.model_dump()
        write_json(run / "world.json", world)
        imports = []
        bindings = {}
        for i, (key, path) in enumerate((factories or {}).items()):
            model_path = Path(path).resolve()
            alias = "modelFactory" + str(i)
            imports.append(
                f"import {{createModel as {alias}}} from {json.dumps(model_path.as_posix())};"
            )
            bindings[key] = alias
        factory_ids = {b.id for b in validated.blueprints if b.origin == "factory"}
        if factory_ids != set(bindings):
            raise ValueError("FACTORY_MAP_MISMATCH")
        mapping = (
            "{" + ",".join(json.dumps(k) + ":" + v for k, v in bindings.items()) + "}"
        )
        entry = (
            "\n".join(imports)
            + f"\nimport {{buildWorld}} from {json.dumps((ROOT / 'runtime/semantic.mjs').as_posix())};\nconst root=buildWorld({json.dumps(world)},{mapping});\n"
        )
        source = run / "world.json"
    else:
        source = Path(factory).resolve()
        entry = f"import {{createModel}} from {json.dumps(source.as_posix())};\nconst root=createModel({{}});\nif(!root?.isObject3D)throw Error('FACTORY_MUST_RETURN_OBJECT3D');\n"
        if (run / "semantic-overlay.json").exists():
            overlay = json.loads(
                (run / "semantic-overlay.json").read_text(encoding="utf-8")
            )
            checks = [
                GeometryProbe.model_validate(check).model_dump()
                for check in overlay["checks"]
            ]
            entry += "root.userData.semanticChecks=" + json.dumps(checks) + ";\n"
    config = (
        json.loads((run / "render-config.json").read_text())
        if (run / "render-config.json").exists()
        else {}
    )
    config.setdefault("isolated_stage", factory is not None)
    entry = (
        f"import {{monitorAssets}} from {json.dumps(runtime)};\nmonitorAssets();\n"
        + entry
    )
    entry += f"import {{mount}} from {json.dumps(runtime)};\nmount(root,{json.dumps(config)});\n"
    (run / "entry.mjs").write_text(entry, encoding="utf-8")
    # Invoke the JS API rather than the platform-specific npm wrapper or esbuild binary.
    script = "require(process.argv[3]+'/esbuild').buildSync({entryPoints:[process.argv[1]],outfile:process.argv[2],nodePaths:[process.argv[3]],bundle:true,format:'esm',platform:'browser',sourcemap:true,logLevel:'warning'});"
    result = subprocess.run(
        [
            "node",
            "-e",
            script,
            str(run / "entry.mjs"),
            str(run / "bundle.js"),
            str(paths().node_modules),
        ],
        cwd=run,
        capture_output=True,
        text=True,
    )
    write_json(
        run / "build.json",
        {
            "exit_code": result.returncode,
            "stderr": result.stderr,
            "source_sha256": file_hash(source),
        },
    )
    if result.returncode:
        raise RuntimeError("BROWSER_BUILD_FAILED: " + result.stderr[-2000:])
    (run / "index.html").write_text(
        """<!doctype html><meta charset="utf-8"><title>WorldAsCode viewer</title><style>body{margin:0;background:#161c24;color:#eee;font:15px system-ui}header{padding:10px}canvas{display:block}input{vertical-align:middle}</style><header>Asset preview · Hour <input id="hour" type="range" min="0" max="23.9" value="13" step=".1"> Wetness <input id="wetness" type="range" min="0" max="1" step=".05" value="0"> Wind <input id="wind" type="range" min="0" max="2" step=".1" value="0"> Explode <input id="explode" type="range" min="0" max="1" step=".05" value="0"> <span id="selection">Click a part</span></header><div id="viewport"></div><script type="module" src="./bundle.js"></script>""",
        encoding="utf-8",
    )
    return run


def fit_camera(page, reference, run):
    # This fits an estimated camera to the source silhouette; it does not solve survey geometry.
    # Compare in the actual render aspect ratio. Stretching the reference into a
    # square makes a wrong camera appear to match a distorted building.
    canvas_size = page.locator("canvas").evaluate("c=>[c.width,c.height]")
    fit_size = (160, round(160 * canvas_size[1] / canvas_size[0]))
    source = Image.open(reference).convert("RGB")
    source.thumbnail(fit_size)
    im = Image.new("RGB", fit_size, "black")
    im.paste(
        source, ((fit_size[0] - source.width) // 2, (fit_size[1] - source.height) // 2)
    )
    a = np.asarray(im)
    mask = a.max(axis=2) > 40
    candidates = []
    for azimuth in [0, 35, 70, 110, 145, 180, 215, 250, 290, 325]:
        for elevation in [18, 32, 46]:
            page.evaluate("v=>worldscale.view(...v)", [azimuth, elevation])
            data = page.evaluate("worldscale.silhouette()").split(",", 1)[1]
            shot = (
                Image.open(io.BytesIO(base64.b64decode(data)))
                .convert("L")
                .resize(fit_size)
            )
            m = np.asarray(shot) > 100
            intersection = np.logical_and(mask, m).sum()
            union = np.logical_or(mask, m).sum()
            score = float(intersection / max(union, 1))
            candidates.append(
                {"azimuth": azimuth, "elevation": elevation, "score": score}
            )
    best = max(candidates, key=lambda c: c["score"])
    # Refine view direction and framing together; this never changes geometry.
    coarse = dict(best)
    for azimuth in [coarse["azimuth"] + d for d in (-12, 0, 12)]:
        for elevation in [max(8, coarse["elevation"] + d) for d in (-8, 0, 8)]:
            for scale in (1.0, 1.1, 1.25):
                page.evaluate("v=>worldscale.view(...v)", [azimuth, elevation, scale])
                data = page.evaluate("worldscale.silhouette()").split(",", 1)[1]
                shot = (
                    Image.open(io.BytesIO(base64.b64decode(data)))
                    .convert("L")
                    .resize(fit_size)
                )
                m = np.asarray(shot) > 100
                score = float(
                    np.logical_and(mask, m).sum() / max(np.logical_or(mask, m).sum(), 1)
                )
                candidates.append(
                    {
                        "azimuth": azimuth,
                        "elevation": elevation,
                        "scale": scale,
                        "score": score,
                    }
                )
    best = max(candidates, key=lambda c: c["score"])
    best["method"] = "bounded silhouette fit; estimated camera, not metric pose"
    best["candidates"] = len(candidates)
    write_json(Path(run) / "camera-fit.json", best)
    return best


def capture(
    run,
    reference=None,
    camera_override=None,
    extra=None,
    review_only=False,
    export_geometry=True,
    prepare=None,
):
    """``extra(page, shots)`` may take further captures without changing geometry.

    ``prepare(page)`` may rebuild styles before the geometry-invariance baseline;
    it returns any screenshot names to include in the capture receipt.
    """
    run = Path(run).resolve()
    errors = []
    denied = []
    with serve(run) as url, sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True, args=["--use-angle=swiftshader", "--enable-webgl"]
        )
        page = browser.new_page(
            viewport={"width": 1100, "height": 900}, device_scale_factor=1
        )
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route(
            "**/*",
            lambda route: (
                route.continue_()
                if route.request.url.startswith(url + "/")
                else (denied.append(route.request.url), route.abort())[-1]
            ),
        )
        page.goto(url + "/index.html")
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if errors:
                break
            try:
                ready = page.evaluate(
                    "() => window.worldscaleReady === true && window.worldscaleLoading?.pending === 0"
                )
            except Exception as exc:
                errors.append(type(exc).__name__ + ": " + str(exc))
                break
            if ready:
                break
            page.wait_for_timeout(100)
        ready = not errors and time.monotonic() < deadline
        if not ready:
            failure = {
                "passed": False,
                "runtime_error": errors[0] if errors else "WORLD_SCALE_BOOT_TIMEOUT",
                "runtime_errors": errors,
                "loading": page.evaluate("window.worldscaleLoading || null"),
            }
            write_json(run / "browser-bootstrap-failure.json", failure)
            browser.close()
            return failure
        errors.extend(page.evaluate("worldscaleLoading.failed").copy())
        # Automated captures call draw() explicitly through view/pose/state.
        # Do not compete with a continuous animation loop on software WebGL.
        page.evaluate("worldscale.renderer.setAnimationLoop(null)")
        # A preview may exercise explicit scene/style rebuilds before the state-invariance
        # baseline. The subsequent night/weather check still requires identical geometry.
        prepared_shots = prepare(page) if prepare else []
        try:
            initial = page.evaluate("worldscale.manifest()")
        except Exception as exc:
            failure = {
                "passed": False,
                "runtime_error": type(exc).__name__ + ": " + str(exc),
                "runtime_errors": errors,
                "loading": page.evaluate("window.worldscaleLoading || null"),
            }
            write_json(run / "browser-bootstrap-failure.json", failure)
            browser.close()
            return failure
        shots = list(prepared_shots or [])
        camera = camera_override or (
            fit_camera(page, reference, run)
            if reference
            else {"azimuth": 35, "elevation": 28}
        )
        if camera_override:
            write_json(run / "camera-fit.json", camera_override)
        az, el = camera["azimuth"], camera["elevation"]
        free_views = [
            ("front", az, el),
            ("rear", az + 180, el),
            ("side", az + 90, el),
            ("orbit45", az + 45, el),
            ("orbit135", az + 135, el),
            ("orbit225", az + 225, el),
            ("orbit270", az + 270, el),
            ("orbit315", az + 315, el),
            ("top", az, 75),
        ]
        # Design reviews already capture every calibrated evidence camera.
        # Extra orbit screenshots duplicate those views and are not consumed.
        for name, a, e in free_views[:1] if review_only else free_views:
            page.evaluate("v=>worldscale.view(...v)", [a, e, camera.get("scale", 1.0)])
            page.locator("canvas").screenshot(path=str(run / (name + ".png")))
            shots.append(name + ".png")
        if extra:
            extra(page, shots)
        page.evaluate("v=>worldscale.view(...v)", [az, el, camera.get("scale", 1.0)])
        page.evaluate("worldscale.clay(true)")
        page.locator("canvas").screenshot(path=str(run / "clay.png"))
        page.evaluate("worldscale.clay(false)")
        shots.append("clay.png")
        page.evaluate("worldscale.lookdev('grazing')")
        page.locator("canvas").screenshot(path=str(run / "grazing.png"))
        shots.append("grazing.png")
        page.evaluate("worldscale.lookdev('neutral')")
        page.evaluate("worldscale.state({hour:22,wetness:.8,wind:0})")
        after = page.evaluate("worldscale.manifest()")
        page.locator("canvas").screenshot(path=str(run / "night.png"))
        shots.append("night.png")
        if export_geometry:
            geometry = page.evaluate("worldscale.geometry()")
            write_json(run / "geometry.json", {"meshes": geometry["meshes"]})
            write_json(run / "parts.json", geometry["parts"])
            write_json(run / "measured.json", geometry["measured"])
        browser.close()
    image = Image.open(run / "front.png").convert("RGB")
    spread = max(ImageStat.Stat(image).stddev)
    metadata = {
        "errors": errors,
        "denied_requests": denied,
        "manifest": initial,
        "state_preserves_geometry": initial["parts"] == after["parts"],
        "visible_variance": spread,
        "captures": {name: file_hash(run / name) for name in shots},
        "bundle_sha256": file_hash(run / "bundle.js"),
    }
    metadata["passed"] = (
        not errors
        and not denied
        and spread > 5
        and initial["triangles"] > 0
        and metadata["state_preserves_geometry"]
        and all(x["passed"] for x in initial["probes"])
    )
    write_json(run / "render-manifest.json", metadata)
    return metadata


def render_attempt(
    folder, code, site, style, evidence, kit_path=None, heights=None, packs=None
):
    """Bundle and capture one script. Returns (metrics, error text or None).

    ``heights`` is the optional ``(grid, layout)`` height field; with it the
    model's roof is compared to the measured one.
    """
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "design.mjs").write_text(code, encoding="utf-8")
    problems = lint(code)
    if problems:
        return None, "LINT: " + " ".join(problems)
    first = render_camera(evidence["views"][0])
    write_json(
        folder / "render-config.json",
        {"width": first["render_width"], "height": first["render_height"]},
    )
    try:
        bundle(
            folder,
            design=folder / "design.mjs",
            site=site,
            style=style,
            kit_path=kit_path,
            packs=packs,
        )
        record_runtime_snapshot(folder)
    except (RuntimeError, ValueError) as exc:
        return None, str(exc)[-1500:]
    browser, inspection = {}, {}
    views = evidence_capture(evidence, folder, browser)

    def extra(page, shots):
        views(page, shots)
        inspection["structure"] = page.evaluate("worldscale.structure()")
        if heights is not None:
            from worldascode.quality import roof_shape

            inspection["model_heights"] = roof_shape.capture(page, heights[1])

    report = capture(
        folder,
        camera_override={"azimuth": 215, "elevation": 32, "method": "free review view"},
        extra=extra,
        review_only=True,
    )
    if report.get("runtime_error"):
        return None, "RUNTIME: " + str(report["runtime_error"])[:1500]
    if "model_heights" in inspection:
        import worldascode.geometry.massing as massing
        from worldascode.quality import roof_shape

        plan = massing.to_plan(site["footprint"])
        inspection["roof_shape"] = roof_shape.compare(
            inspection.pop("model_heights"),
            heights[0],
            heights[1],
            plan,
            evidence["height_m"],
            out_image=folder / "roof-error.png",
        )
    metrics = measure(folder, evidence, site, report, browser, inspection)
    write_json(folder / "metrics.json", metrics)
    sheet(
        [folder / ("view-" + v["id"] + ".png") for v in evidence["views"]]
        + [folder / "front.png"],
        folder / "render-sheet.jpg",
    )
    detail_sheet(evidence, folder, folder / "detail-sheet.jpg", rendered=True)
    return metrics, None


def record_runtime_snapshot(folder):
    """Hash the exact runtime content bundled, including between-attempt edits."""
    folder = Path(folder)
    mapping = json.loads((folder / "bundle.js.map").read_text(encoding="utf-8"))
    names = {
        "kit.mjs",
        "surfaces.mjs",
        "roof-openings.mjs",
        "viewer.mjs",
        "semantic.mjs",
        "parts.mjs",
        "region.mjs",
        "area.mjs",
        "buildings.mjs",
    }
    versions = {
        source.replace("\\", "/"): sha256(content.encode("utf-8")).hexdigest()
        for source, content in zip(
            mapping["sources"], mapping["sourcesContent"], strict=True
        )
        if Path(source).name in names and content is not None
    }
    write_json(
        folder / "runtime-versions.json",
        {
            "bundle_sha256": file_hash(folder / "bundle.js"),
            "modules": versions,
            "provenance": "Exact source content embedded by esbuild, not the current runtime files after rendering.",
        },
    )


def render_object(folder, code, site, style=None, packs=None, kit_path=None):
    """Bundle and capture a free-standing object (no evidence cameras).

    Returns (metrics, error). Checks are the ones that need no reference: it
    builds, nothing floats, and it fits the size the site asked for.
    """
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "design.mjs").write_text(code, encoding="utf-8")
    problems = lint(code)
    if problems:
        return None, "LINT: " + " ".join(problems)
    try:
        bundle(
            folder,
            design=folder / "design.mjs",
            site=site,
            style=style,
            kit_path=kit_path,
            packs=packs,
        )
        record_runtime_snapshot(folder)
    except (RuntimeError, ValueError) as exc:
        return None, str(exc)[-1500:]
    inspection = {}

    def extra(page, shots):
        inspection["structure"] = page.evaluate("worldscale.structure()")
        inspection["part_calls"] = page.evaluate(
            "worldscale.root.userData.packCalls??{}"
        )
        for name, azimuth in [("rear", 35), ("side", 305)]:
            page.evaluate("v=>worldscale.view(...v)", [azimuth, 28])
            page.locator("canvas").screenshot(path=str(folder / (name + ".png")))
            shots.append(name + ".png")

    report = capture(
        folder,
        camera_override={"azimuth": 215, "elevation": 28, "method": "free review view"},
        extra=extra,
        review_only=True,
        export_geometry=False,
    )
    if report.get("runtime_error"):
        return None, "RUNTIME: " + str(report["runtime_error"])[:1500]
    bounds = report["manifest"]["bounds"]
    size = [round(bounds["max"][i] - bounds["min"][i], 2) for i in range(3)]
    envelope = site.get("envelope")
    fits = True
    if envelope:
        wanted = [
            envelope.get("length_m"),
            envelope.get("height_m"),
            envelope.get("width_m"),
        ]
        horizontal = sorted([size[0], size[2]], reverse=True)
        target = sorted([v for v in (wanted[0], wanted[2]) if v], reverse=True)
        fits = all(0.6 <= a / b <= 1.6 for a, b in zip(horizontal, target)) and (
            not wanted[1] or 0.6 <= size[1] / wanted[1] <= 1.6
        )
    triangles = report["manifest"]["triangles"]
    checks = {
        "browser": bool(report.get("passed")),
        "structure": not inspection["structure"]["issues"],
        "envelope": fits,
        "triangles": 0 < triangles <= 60_000,
        "ground": -0.25 <= bounds["min"][1] <= 0.25,
        "required_probes": all(
            any(
                probe.get("requirement") == requirement and probe.get("passed")
                for probe in report["manifest"]["probes"]
            )
            for requirement in site.get("required_checks", [])
        ),
    }
    metrics = {
        "passed": all(checks.values()),
        "checks": checks,
        "size_m": {"x": size[0], "y": size[1], "z": size[2]},
        "bounds_m": bounds,
        "triangles": triangles,
        "structure": inspection["structure"],
        "part_calls": inspection["part_calls"],
        "probes": report["manifest"]["probes"],
        "performance": report["manifest"].get("performance"),
    }
    write_json(folder / "metrics.json", metrics)
    return metrics, None


def render_region(folder, scripts, region, style, evidence, selected_packs):
    """Compose guarded local recipes and capture the source's exact regional cameras."""
    import shutil

    from PIL import ImageDraw

    from worldascode.kits import packs as pack_library
    from worldascode.storage.artifacts import digest

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    if set(scripts) != set(region.index()):
        return None, "REGION_ENTITY_DESIGNS_MISMATCH"
    runtime = folder / "selected-runtime"
    runtime.mkdir(exist_ok=True)
    for p in (ROOT / "runtime").glob("*.mjs"):
        shutil.copy2(p, runtime / p.name)
    imports = []
    bindings = []
    for index, (entity_id, code) in enumerate(scripts.items()):
        problems = lint(code)
        if problems:
            return None, f"ENTITY {entity_id}: " + "; ".join(problems)
        try:
            from worldascode.kits.code import analyze_source

            analyze_source(code)
        except ValueError as error:
            return None, f"ENTITY {entity_id}: {error}"
        path = folder / ("entity-" + digest(entity_id)[:16] + ".mjs")
        path.write_text(code, encoding="utf-8")
        imports.append(
            f"import {{design as design{index}}} from {json.dumps(path.resolve().as_posix())};"
        )
        bindings.append(json.dumps(entity_id) + f":design{index}")
    pinned = [
        pack_library.pin(p, folder / "selected-packs" / p["id"]) for p in selected_packs
    ]
    for index, p in enumerate(pinned):
        imports.append(
            f"import * as pack{index} from {json.dumps(Path(p['module']).as_posix())};"
        )
    registry = {
        **region.model_dump(mode="json"),
        "entities": [
            {**e.model_dump(mode="json"), "site": e.site()} for e in region.entities
        ],
    }
    imports.append(
        f"import {{buildRegionDesign}} from {json.dumps((runtime / 'region.mjs').resolve().as_posix())};"
    )
    code = (
        "\n".join(imports)
        + f"\nexport function createModel(){{return buildRegionDesign({{{','.join(bindings)}}},{json.dumps(registry)},{json.dumps(style)},[{','.join('pack' + str(i) for i in range(len(pinned)))}]);}}"
    )
    factory = folder / "region-factory.mjs"
    factory.write_text(code, encoding="utf-8")
    write_json(folder / "render-config.json", {"isolated_stage": False})
    write_json(folder / "scripts.json", scripts)
    try:
        bundle(folder, factory=factory)
        record_runtime_snapshot(folder)
    except (ValueError, RuntimeError) as error:
        return None, str(error)[-1600:]
    inspection = {}
    aligned = []

    def extra(page, shots):
        inspection.update(
            page.evaluate(
                "({structure:worldscale.structure(),...worldscale.addresses(),part_calls:worldscale.root.userData.packCalls??{}})"
            )
        )
        for name, az, el in [("overview", 125, 48), ("overview-top", 35, 75)]:
            page.evaluate("v=>worldscale.view(...v)", [az, el])
            page.locator("canvas").screenshot(path=str(folder / (name + ".png")))
            shots.append(name + ".png")
        for record in evidence:
            if not record.get("camera"):
                continue
            page.evaluate("c=>worldscale.pose(c)", record["camera"])
            name = record["id"] + ".png"
            page.locator("canvas").screenshot(path=str(folder / name))
            shots.append(name)
            addresses = page.evaluate("worldscale.addresses()")
            write_json(folder / (record["id"] + "-addresses.json"), addresses)
            aligned.append(
                {
                    "evidence_id": record["id"],
                    "entity_ids": record["request"]["entity_ids"],
                    "source": record["image"],
                    "output": str((folder / name).resolve()),
                    "camera": record["camera"],
                    "addresses": addresses["entities"],
                    "reference_addresses": record.get(
                        "projected_entities", addresses["entities"]
                    ),
                }
            )

    report = capture(folder, extra=extra, review_only=True, export_geometry=False)
    if report.get("runtime_error"):
        return None, "RUNTIME: " + str(report["runtime_error"])[:1800]
    expected = region.index()
    entities = inspection.get("entities", {})
    checks = {
        "browser": bool(report.get("passed")),
        "entities": set(entities) == set(expected),
        "structure": not inspection.get("structure", {}).get("issues", []),
        "triangles": 0 < report["manifest"]["triangles"] <= 200000 * len(expected),
    }
    envelope = {}
    for key, entity in expected.items():
        actual = entities.get(key, {}).get("bounds")
        wanted = entity.world_bounds()
        envelope[key] = bool(
            actual
            and all(
                actual["min"][i]
                >= wanted.min[i] - max(1, (wanted.max[i] - wanted.min[i]) * 0.15)
                and actual["max"][i]
                <= wanted.max[i] + max(1, (wanted.max[i] - wanted.min[i]) * 0.3)
                for i in range(3)
            )
        )
    checks["entity_envelopes"] = all(envelope.values())
    metrics = {
        "passed": all(checks.values()),
        "checks": checks,
        "entity_envelopes": envelope,
        "entities": entities,
        "components": inspection.get("components", {}),
        "structure": inspection.get("structure"),
        "part_calls": inspection.get("part_calls", {}),
        "triangles": report["manifest"]["triangles"],
        "performance": report["manifest"].get("performance"),
    }
    write_json(folder / "metrics.json", metrics)
    # Identical projected labels on source and output disambiguate neighboring objects.
    for pair in aligned:
        for key in ["source", "output"]:
            img = Image.open(pair[key]).convert("RGB")
            draw = ImageDraw.Draw(img)
            for entity_id, record in pair["reference_addresses"].items():
                rect = record.get("screen")
                if not rect:
                    continue
                x0, y0 = [
                    max(0, min(img.size[i] - 1, v)) for i, v in enumerate(rect["min"])
                ]
                x1, y1 = [
                    max(0, min(img.size[i] - 1, v)) for i, v in enumerate(rect["max"])
                ]
                if x1 <= x0 or y1 <= y0:
                    continue
                draw.rectangle((x0, y0, x1, y1), outline="#ffbf00", width=2)
                draw.text(
                    (x0 + 3, y0 + 3),
                    entity_id,
                    fill="#ffbf00",
                    stroke_width=1,
                    stroke_fill="black",
                )
            path = folder / (pair["evidence_id"] + "-" + key + "-labeled.jpg")
            img.save(path, quality=92)
            pair[key + "_labeled"] = str(path.resolve())
    write_json(folder / "aligned-evidence.json", aligned)
    return metrics, None
