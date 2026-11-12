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
):
    """Bundle a World recipe, owned createModel factory, or kit design script.

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
        from worldascode.kits.context import runtime_slice

        selected = runtime_slice(
            Path(kit_path or ROOT / "runtime/kit.mjs").resolve(),
            source.read_text(encoding="utf-8"),
            run / "selected-runtime",
        )
        write_json(run / "site.json", site)
        entry = (
            f"import {{design}} from {json.dumps(source.as_posix())};\n"
            f"import {{buildDesign}} from {json.dumps(selected.as_posix())};\n"
            f"const root=buildDesign(design,{json.dumps(site)},{json.dumps(style or {})});\n"
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
    config["isolated_stage"] = factory is not None
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
):
    """``extra(page, shots)`` may take further captures and append their file names."""
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
        shots = []
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


def render_attempt(folder, code, site, style, evidence, kit_path=None):
    """Bundle and capture one script. Returns (metrics, error text or None)."""
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
        )
        record_runtime_snapshot(folder)
    except (RuntimeError, ValueError) as exc:
        return None, str(exc)[-1500:]
    browser = {}
    report = capture(
        folder,
        camera_override={"azimuth": 215, "elevation": 32, "method": "free review view"},
        extra=evidence_capture(evidence, folder, browser),
        review_only=True,
    )
    if report.get("runtime_error"):
        return None, "RUNTIME: " + str(report["runtime_error"])[:1500]
    metrics = measure(folder, evidence, site, report, browser)
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
