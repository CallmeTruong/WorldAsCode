import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import psutil
from .config import ROOT
from .provider import write_json


def validate_source(source):
    if not isinstance(source, str) or not 50 < len(source) < 100000:
        raise ValueError("INVALID_SOURCE_SIZE")
    # Defense in depth; isolation and outbound request denial are the boundary.
    banned = r"\b(?:eval|Function|fetch|XMLHttpRequest|WebSocket|importScripts|SharedWorker|Worker|indexedDB|localStorage|sessionStorage|process|require|Deno|Bun)\b|\bimport\s*\(|https?://|file://"
    if re.search(banned, source):
        raise ValueError("UNSAFE_SOURCE_CAPABILITY")
    if not re.search(r"export\s+function\s+build\s*\(", source):
        raise ValueError("MISSING_BUILD_FACTORY")


def kill_tree(process):
    try:
        parent = psutil.Process(process.pid)
        for child in parent.children(recursive=True):
            try:
                child.kill()
            except psutil.Error:
                pass
        parent.kill()
    except psutil.Error:
        pass


def render(source: Path, output: Path, camera=None, timeout=65, memory_mb=2000):
    source, output = source.resolve(), output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    validate_source(source.read_text(encoding="utf-8"))
    write_json(output / "camera.json", camera or {"azimuth": 35, "elevation": 12})
    # Child never receives API credentials. Browser worker cannot access this process.
    env = {k: v for k, v in os.environ.items() if k.upper() in {
        "PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "PLAYWRIGHT_BROWSERS_PATH", "COMSPEC"}}
    env["PYTHONPATH"] = str(ROOT / "src")
    with (output / "runtime.log").open("w", encoding="utf-8") as log:
        child = subprocess.Popen([sys.executable, "-m", "building_workflow.runtime", "--child", str(source), str(output)],
                                 cwd=ROOT, env=env, stdout=log, stderr=log)
        started = time.monotonic()
        peak = 0
        try:
            while child.poll() is None:
                if time.monotonic() - started > timeout:
                    raise RuntimeError("RENDER_TIMEOUT")
                try:
                    processes = [psutil.Process(child.pid)]
                    processes += processes[0].children(recursive=True)
                    memory = sum(p.memory_info().rss for p in processes if p.is_running())
                    peak = max(peak, memory)
                    if memory > memory_mb * 1024 * 1024:
                        raise RuntimeError("RENDER_MEMORY_BUDGET")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
                time.sleep(0.1)
        finally:
            if child.poll() is None:
                kill_tree(child)
            child.wait()
        write_json(output / "runtime-resources.json", {"seconds": time.monotonic() - started, "peak_process_tree_rss_mb": peak / 1024**2,
            "memory_ceiling_mb": memory_mb, "timeout_seconds": timeout, "isolation": "Chromium OS sandbox + dedicated worker + CSP + request denial"})
    result_path = output / "runtime-result.json"
    if child.returncode != 0 or not result_path.exists():
        raise RuntimeError("RUNTIME_FAILED: see runtime.log")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if not result.get("ok"):
        raise RuntimeError(result.get("error", "RUNTIME_FAILED"))
    return result


def child_main(source, output):
    from playwright.sync_api import sync_playwright
    from .skills import geometry_gate
    source, output = Path(source), Path(output)
    try:
        compiler = ROOT / "node_modules/typescript/bin/tsc"
        check = subprocess.run(["node", str(compiler), "--noEmit", "--skipLibCheck", "--moduleResolution", "bundler",
            "--module", "esnext", "--target", "es2022", str(source)], cwd=ROOT, capture_output=True, text=True, timeout=20)
        (output / "compile.log").write_text(check.stdout + check.stderr, encoding="utf-8")
        if check.returncode:
            raise RuntimeError("TYPESCRIPT_VALIDATION_FAILED")
        for mode in ["worker", "viewer"]:
            cmd = ["node", str(ROOT / "runtime/bundle.mjs"), str(source), str(output / (mode + ".js")), mode]
            check = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=15)
            if check.returncode:
                (output / "bundle.log").write_text(check.stdout + check.stderr, encoding="utf-8")
                raise RuntimeError("BUNDLE_VALIDATION_FAILED")
        with sync_playwright() as p:
            # Chromium's OS sandbox is explicitly on. No --no-sandbox flags.
            browser = p.chromium.launch(headless=True, chromium_sandbox=True)
            context = browser.new_context(viewport={"width":800,"height":800}, service_workers="block", accept_downloads=False)
            denied = []
            def deny(route):
                denied.append(route.request.url.split(":", 1)[0])
                route.abort()
            context.route("**/*", deny)
            page = context.new_page()
            csp = "default-src 'none'; script-src 'unsafe-inline' blob:; worker-src blob:; connect-src 'none'; img-src data:; style-src 'unsafe-inline'"
            page.set_content(f'<meta http-equiv="Content-Security-Policy" content="{csp}"><body></body>')
            worker = (output / "worker.js").read_text(encoding="utf-8")
            result = page.evaluate("""code => new Promise((resolve,reject)=>{
                const w=new Worker(URL.createObjectURL(new Blob([code],{type:'text/javascript'})));
                const timer=setTimeout(()=>{w.terminate();reject(Error('WORKER_TIMEOUT'))},20000);
                w.onmessage=e=>{clearTimeout(timer);w.terminate();resolve(e.data)};
                w.onerror=e=>{clearTimeout(timer);w.terminate();reject(Error(e.message))};
                w.postMessage({});
            })""", worker)
            if not result.get("ok"):
                raise RuntimeError(result.get("error", "GENERATOR_FAILED"))
            # Validate worker output again on the trusted host before ObjectLoader.
            if len(result.get("geometry", {}).get("meshes", [])) > 1200 or len(json.dumps(result)) > 40_000_000:
                raise RuntimeError("SCENE_PAYLOAD_BUDGET")
            scene = result["scene"]
            if scene.get("textures") or scene.get("images"):
                raise RuntimeError("EXTERNAL_TEXTURE_FORBIDDEN")
            write_json(output / "scene.json", scene)
            write_json(output / "mesh-payload.json", result["geometry"])
            gate = geometry_gate(result["geometry"])
            write_json(output / "geometry.json", gate)
            if not gate["passed"]:
                raise RuntimeError("GEOMETRY_GATE_FAILED")
            page.add_script_tag(content=(output / "viewer.js").read_text(encoding="utf-8"))
            page.evaluate("data=>window.loadModel(data)", scene)
            cameras = {"front": {"azimuth":0,"elevation":0}, "back": {"azimuth":180,"elevation":0},
                "left":{"azimuth":-90,"elevation":0}, "right":{"azimuth":90,"elevation":0},
                "isometric":{"azimuth":35,"elevation":25}, "reference-view":json.loads((output/"camera.json").read_text())}
            for name, camera in cameras.items():
                page.evaluate("camera=>window.captureView(camera)", camera)
                page.locator("canvas").screenshot(path=str(output / (name + ".png")))
            # These checks catch blank/stale/clipped capture failures only.
            # They do not measure agreement with a photograph.
            from PIL import Image
            import numpy as np
            capture_checks={}
            background=np.array([232,237,242])
            for name in cameras:
                pixels=np.array(Image.open(output/(name+".png")).convert("RGB"))
                mask=np.max(np.abs(pixels.astype(int)-background),axis=2)>18
                ys,xs=np.where(mask)
                if not len(xs) or mask.mean()<0.005:
                    raise RuntimeError("BLANK_CAPTURE")
                clipped=bool(xs.min()==0 or ys.min()==0 or xs.max()==799 or ys.max()==799)
                if clipped:
                    raise RuntimeError("CLIPPED_CAPTURE")
                capture_checks[name]={"foreground_fraction":float(mask.mean()),"bounds_px":[int(xs.min()),int(ys.min()),int(xs.max()),int(ys.max())],"clipped":clipped}
            write_json(output/"capture-checks.json",capture_checks)
            result = {"ok":True, "triangles": result["triangles"], "mesh_count": len(result["geometry"]["meshes"]),
                "bounds":result["bounds"], "geometry_passed": True, "network_requests_denied":denied}
            browser.close()
        write_json(output / "runtime-result.json", result)
    except Exception as exc:
        write_json(output / "runtime-result.json", {"ok":False, "error":str(exc)[:1000]})


if __name__ == "__main__":
    child_main(sys.argv[2], sys.argv[3])
