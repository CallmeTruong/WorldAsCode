"""Area-wide measurements from the reference viewer: a height grid and reference views.

One pass over a whole area replaces per-building capture. The height grid gives
ground level, building heights, roof relief and tree canopy in a single frame;
the views are the picture the reconstruction is compared against. Both are
optional: without a viewer the area is built from map data alone.
"""

import math
import time
from pathlib import Path

import numpy as np

from worldascode.adapters.geospatial.inspection import camera_in_region
from worldascode.evidence.georeference import Frame
from worldascode.storage.artifacts import file_hash, write_json

VIEWS = (
    ("north", 0, -40),
    ("east", 90, -40),
    ("south", 180, -40),
    ("west", 270, -40),
    ("top", 0, -89.8),
)


def open_viewer(
    playwright,
    url,
    width=1440,
    height=1080,
    timeout_s=120,
    noon_date="2026-06-21",
    sse=4,
    cache_mb=128,
):
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": width, "height": height})
    page.goto(
        url + ("&" if "?" in url else "?") + f"sse={sse}&cache={cache_mb}",
        wait_until="load",
    )
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if page.evaluate("()=>window.__GOOGLE_REFERENCE_READY__===true"):
            break
        if page.evaluate("()=>!!window.__GOOGLE_REFERENCE_FAILURE__"):
            raise RuntimeError("REFERENCE_VIEWER_CONNECTION_FAILED")
        page.wait_for_timeout(300)
    else:
        raise RuntimeError("REFERENCE_VIEWER_START_TIMEOUT")
    page.set_default_timeout(600000)
    page.evaluate("o=>window.configureEvidenceCapture(o)", {"solarNoonDate": noon_date})
    page.locator("header").evaluate("el=>el.style.display='none'")
    return browser, page


def settle(page, timeout_s=90, stable_polls=4):
    """Wait until the streamed tiles for the current view have stopped arriving."""
    deadline, stable = time.monotonic() + timeout_s, 0
    page.wait_for_timeout(1500)
    while time.monotonic() < deadline and stable < stable_polls:
        page.wait_for_timeout(600)
        stats = page.evaluate("window.googleEvidenceStats()")
        stable = (
            stable + 1 if stats["tilesLoaded"] and stats["selectedTiles"] > 0 else 0
        )
    return stable >= stable_polls


def stable_surface(page, repetitions=3):
    """Independent geometry readiness; does not certify texture completeness."""
    probe = """()=>{const p=[];const w=innerWidth,h=innerHeight;for(let r=0;r<7;r++)for(let c=0;c<7;c++)p.push(window.inspectEvidencePoint(w*(.15+.7*c/6),h*(.15+.7*r/6)));return p;}"""
    previous = page.evaluate(probe)
    if sum(p is not None for p in previous) < 40:
        return False
    for _ in range(repetitions):
        page.wait_for_timeout(650)
        current = page.evaluate(probe)
        good = 0
        for a, b in zip(previous, current):
            if a and b:
                delta = max(
                    abs(a["height"] - b["height"]),
                    abs(a["latitude"] - b["latitude"]) * 111320,
                    abs(a["longitude"] - b["longitude"])
                    * 111320
                    * math.cos(math.radians(a["latitude"])),
                )
                good += delta <= 0.25
        if good < 47:
            return False
    return True


def settle_geometry(page, timeout_s):
    complete = settle(page, min(timeout_s, 12))
    stable = complete or stable_surface(page)
    if not stable and timeout_s > 12:
        complete = settle(page, timeout_s - 12)
        stable = complete or stable_surface(page)
    return complete, stable


def height_grid(
    page,
    latitude,
    longitude,
    half_m,
    step,
    out,
    tile_m=170.0,
    range_m=420.0,
    progress=None,
    settle_s=60,
):
    """Surface heights on a north-aligned grid, from depth picks of straight-down views.

    The area is covered by overlapping nadir tiles; only the centre of each frame
    is read, so walls hide little ground. Each pick is a true 3D surface point,
    and a cell keeps its highest one (the roof rather than the facade below it).
    """
    frame = Frame(longitude, latitude)
    n = int(round(2 * half_m / step)) + 1
    grid = np.full((n, n), -np.inf)
    size = page.viewport_size
    # Metres per pixel on the ground for the viewer's 60 degree horizontal field of view.
    metres_per_pixel = 2 * range_m * math.tan(math.radians(30)) / size["width"]
    window_px = min(size["height"] - 40, int((tile_m * 1.25) / metres_per_pixel))
    x0, y0 = (size["width"] - window_px) // 2, (size["height"] - window_px) // 2
    centres = (
        np.linspace(
            -half_m + tile_m / 2, half_m - tile_m / 2, math.ceil(2 * half_m / tile_m)
        )
        if 2 * half_m > tile_m
        else np.array([0.0])
    )
    partial, stable_partial, done = [], [], 0

    def checkpoint():
        heights = np.where(np.isfinite(grid), grid, np.nan)
        record = {
            "schema": "worldascode-area-heights-1",
            "source": page.evaluate("()=>window.googleEvidenceStats().source"),
            "method": "highest depth-buffer pick per cell from overlapping straight-down views",
            "not_surveyed": True,
            "origin": {"latitude": latitude, "longitude": longitude},
            # Rows run south to north, columns west to east; heights are ellipsoidal metres.
            "layout": {
                "u0": -half_m,
                "v0": -half_m,
                "step": step,
                "nu": n,
                "nv": n,
                "angle_rad": 0.0,
            },
            "tiles_not_settled": partial,
            "partial_tiles_with_stable_geometry": stable_partial,
            "quality_note": "Partial tiles contribute heights only after 47/49 spatial probes stay within 0.25 m over three repeats. Texture completeness and surveyed accuracy are not certified.",
            "coverage": round(float(np.isfinite(heights).mean()), 4),
            "heights": [
                None if not np.isfinite(h) else round(float(h), 2)
                for h in heights.ravel()
            ],
        }
        record["completed_tiles"] = done
        record["complete"] = done == len(centres) ** 2
        write_json(Path(out), record)
        return record

    for north in centres:
        for east in centres:
            lon = longitude + math.degrees(east / frame.east_radius)
            lat = latitude + math.degrees(north / frame.north_radius)
            page.evaluate("p=>window.setEvidenceTarget(...p)", [lon, lat, 0])
            page.evaluate("p=>window.setEvidenceView(...p)", [0, -89.9, range_m + 40])
            complete, stable = settle_geometry(page, settle_s)
            if not complete:
                partial.append([round(float(east), 1), round(float(north), 1)])
            if stable and not complete:
                stable_partial.append([round(float(east), 1), round(float(north), 1)])
            if not stable:
                done += 1
                checkpoint()
                if progress:
                    progress(done, len(centres) ** 2)
                continue
            flat = page.evaluate(
                "a=>window.pickEvidenceGrid(...a)",
                [
                    max(2, int(step / metres_per_pixel / 2)),
                    x0,
                    y0,
                    x0 + window_px,
                    y0 + window_px,
                ],
            )
            picks = np.array(flat, float).reshape(-1, 3)
            if len(picks):
                e = np.radians(picks[:, 0] - longitude) * frame.east_radius
                nn = np.radians(picks[:, 1] - latitude) * frame.north_radius
                col = np.rint((e + half_m) / step).astype(int)
                row = np.rint((nn + half_m) / step).astype(int)
                ok = (col >= 0) & (col < n) & (row >= 0) & (row < n)
                np.maximum.at(grid, (row[ok], col[ok]), picks[ok, 2])
            done += 1
            checkpoint()
            if progress:
                progress(done, len(centres) ** 2)
    return checkpoint()


def reference_views(
    page, latitude, longitude, target_height, range_m, folder, settle_s=60
):
    """Screenshots from fixed headings with the exact camera of each, in the area frame."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    frame = Frame(longitude, latitude)
    page.evaluate(
        "p=>window.setEvidenceTarget(...p)", [longitude, latitude, target_height]
    )
    views = []
    for name, heading, pitch in VIEWS:
        page.evaluate("p=>window.setEvidenceView(...p)", [heading, pitch, range_m])
        settled, stable = settle_geometry(page, settle_s)
        path = folder / f"reference-{name}.png"
        page.screenshot(path=str(path))
        stats = page.evaluate("window.googleEvidenceStats()")
        camera = stats["camera"]
        east, _, south = frame.model(camera["longitude"], camera["latitude"])
        views.append(
            {
                "id": name,
                "image": path.name,
                "sha256": file_hash(path),
                "heading_deg": heading,
                "pitch_deg": pitch,
                "tiles_loaded": bool(settled),
                "surface_stable": bool(stable),
                "pose": camera_in_region(camera, frame, range_m),
                "actual_camera": camera,
                "origin": {"latitude": latitude, "longitude": longitude},
                "camera": {
                    # Heights stay ellipsoidal here; the area model subtracts its ground datum.
                    "east_m": east,
                    "south_m": south,
                    "height_ellipsoid_m": camera["height"],
                    "target_height_ellipsoid_m": target_height,
                    "fov_vertical_deg": camera.get("fov_vertical_deg")
                    or math.degrees(
                        2 * math.atan(math.tan(math.radians(30)) * 1080 / 1440)
                    ),
                    "width": camera["viewport"][0],
                    "height": camera["viewport"][1],
                },
            }
        )
        write_json(
            folder / "reference-views.json",
            {
                "views": views,
                "source": stats["source"],
                "origin": {"latitude": latitude, "longitude": longitude},
                "complete": False,
            },
        )
        write_json(
            folder / "progress.json",
            {"stage": "reference-views", "done": len(views), "total": len(VIEWS)},
        )
    write_json(
        folder / "reference-views.json",
        {
            "views": views,
            "source": stats["source"],
            "origin": {"latitude": latitude, "longitude": longitude},
            "complete": True,
        },
    )
    return views


def capture_area(latitude, longitude, radius, out, step=3, url=None, profile=None):
    from playwright.sync_api import sync_playwright

    from worldascode.config import CaptureProfile
    from worldascode.geometry.area_model import validate_extent

    validate_extent(latitude, longitude, radius)
    if not math.isfinite(step) or not 1 <= step <= 10 or 2 * radius / step > 1500:
        raise ValueError("AREA_GRID_STEP_INVALID")
    profile = profile or CaptureProfile.load()
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    try:
        with sync_playwright() as playwright:
            browser, page = open_viewer(
                playwright,
                url or profile.viewer_url,
                profile.width,
                profile.height,
                profile.ready_timeout_s,
                profile.solar_noon_date,
                profile.inspection_sse,
                profile.inspection_cache_mb,
            )
            try:
                grid = height_grid(
                    page,
                    latitude,
                    longitude,
                    radius,
                    step,
                    out / "heights.json",
                    progress=lambda done, total: write_json(
                        out / "progress.json",
                        {"stage": "height-grid", "done": done, "total": total},
                    ),
                    settle_s=min(profile.ready_timeout_s, 60),
                )
                values = [h for h in grid["heights"] if h is not None]
                target = float(np.percentile(values, 5)) if values else 20
                views = reference_views(
                    page,
                    latitude,
                    longitude,
                    target,
                    max(250, radius * 3),
                    out,
                    settle_s=min(profile.ready_timeout_s, 60),
                )
            finally:
                browser.close()
        result = {
            "execution_status": "completed" if values else "failed",
            "grid_coverage": grid["coverage"],
            "usable_views": [v["id"] for v in views if v["tiles_loaded"]],
            "measurements": str(out),
            "source": "streamed photogrammetry; not surveyed",
        }
    except Exception as error:
        result = {
            "execution_status": "failed",
            "error": str(error),
            "measurements": str(out),
        }
    write_json(out / "capture-result.json", result)
    return result
