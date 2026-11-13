"""Bounded source-camera tools. Models request a metric ROI; the host holds credentials."""

import json
import math
import time
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageStat

from worldascode.config import RESOURCE_ROOT, CaptureProfile
from worldascode.contracts.region import Bounds, validate_request
from worldascode.evidence.georeference import Frame
from worldascode.evidence.region_focus import fit_range
from worldascode.storage.artifacts import digest, file_hash, write_json


def camera_in_region(actual, frame, distance):
    transform = np.asarray(frame.local_to_ecef())
    position = (np.linalg.inv(transform) @ np.array([*actual["position_ecef"], 1]))[:3]
    direction = transform[:3, :3].T @ np.array(actual["direction_ecef"])
    up = transform[:3, :3].T @ np.array(actual["up_ecef"])
    return {
        "position": position.tolist(),
        "target": (position + distance * direction).tolist(),
        "up": up.tolist(),
        "render_width": actual["viewport"][0],
        "render_height": actual["viewport"][1],
        "fov_vertical_deg": actual["fov_vertical_deg"],
    }


def project_bounds(camera, bounds):
    """Expected footprint/height projection, independent of generated geometry."""
    position = np.array(camera["position"], float)
    forward = np.array(camera["target"], float) - position
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, np.array(camera.get("up", [0, 1, 0]), float))
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    points = (
        np.array(
            [
                (x, y, z)
                for x in [bounds.min[0], bounds.max[0]]
                for y in [bounds.min[1], bounds.max[1]]
                for z in [bounds.min[2], bounds.max[2]]
            ]
        )
        - position
    )
    depth = points @ forward
    if np.any(depth <= 0.1):
        return None
    scale = math.tan(math.radians(camera["fov_vertical_deg"]) / 2)
    x = (
        (
            (points @ right)
            / (depth * scale * camera["render_width"] / camera["render_height"])
            + 1
        )
        * camera["render_width"]
        / 2
    )
    y = (1 - (points @ up) / (depth * scale)) * camera["render_height"] / 2
    if (
        x.max() < 0
        or x.min() > camera["render_width"]
        or y.max() < 0
        or y.min() > camera["render_height"]
    ):
        return None
    return {
        "min": [float(max(0, x.min())), float(max(0, y.min()))],
        "max": [
            float(min(camera["render_width"] - 1, x.max())),
            float(min(camera["render_height"] - 1, y.max())),
        ],
    }


def label_evidence(record, region, folder):
    if not record.get("camera"):
        return record
    projected = {
        e.id: {
            "bounds": e.world_bounds().model_dump(mode="json"),
            "screen": project_bounds(record["camera"], e.world_bounds()),
        }
        for e in region.entities
    }
    image = Image.open(record["image"]).convert("RGB")
    draw = ImageDraw.Draw(image)
    for entity_id, value in projected.items():
        rect = value["screen"]
        if not rect:
            continue
        x, y = rect["min"]
        draw.rectangle((*rect["min"], *rect["max"]), outline="#ffbf00", width=2)
        draw.text(
            (x + 3, y + 3),
            entity_id,
            fill="#ffbf00",
            stroke_width=1,
            stroke_fill="black",
        )
    path = Path(folder) / "source-labeled.jpg"
    image.save(path, quality=94)
    return {
        **record,
        "labeled_image": str(path.resolve()),
        "labeled_sha256": file_hash(path),
        "projected_entities": projected,
        "label_basis": "Expected registry footprint/height projection, not generated geometry or a guarantee of visibility through occlusion.",
    }


class EvidenceTools:
    def __init__(self, region, cache, max_captures=12, profile=None, url=None):
        self.region = region
        self.cache = Path(cache)
        self.profile = profile or CaptureProfile.load()
        self.url = url or self.profile.viewer_url
        self.max_captures = max_captures
        self.calls = 0
        self.page = None
        self._pw = None
        self._browser = None
        self.frame = Frame(
            region.origin.longitude,
            region.origin.latitude,
            region.origin.ground_height_m,
        )

    def close(self):
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()
        self.page = None
        self._browser = None
        self._pw = None

    def capture(self, request, components=None):
        query = validate_request(self.region, request, components)
        key = digest(
            {
                "region": self.region.model_dump(mode="json"),
                "request": query.model_dump(mode="json"),
                "profile": self.profile.manifest(),
                "adapter_sha": file_hash(Path(__file__)),
                "viewer_sha": file_hash(
                    RESOURCE_ROOT / "geospatial/google-reference.js"
                ),
                "source": "packaged-google-reference"
                if urlparse(self.url).hostname in {"127.0.0.1", "localhost"}
                else self.url,
            }
        )
        folder = self.cache / key
        manifest = folder / "evidence.json"
        if manifest.exists():
            record = json.loads(manifest.read_text(encoding="utf-8"))
            if file_hash(folder / "source.png") != record["image_sha256"]:
                raise ValueError("EVIDENCE_CACHE_HASH_MISMATCH")
            return {
                **record,
                "image": str((folder / "source.png").resolve()),
                "cache_hit": True,
            }
        if self.calls >= self.max_captures:
            raise ValueError("EVIDENCE_CAPTURE_BUDGET_EXHAUSTED")
        self.calls += 1
        folder.mkdir(parents=True, exist_ok=True)
        captured = self._capture(query, folder)
        record = {
            **captured,
            "id": "evidence-" + key[:20],
            "request": query.model_dump(mode="json"),
            "image_sha256": file_hash(folder / "source.png"),
            "frame": self.frame.describe(),
            "uncertainty": "Streamed photogrammetry, not surveyed geometry or intrinsic albedo; hidden details remain unknown.",
        }
        write_json(manifest, record)
        return {
            **record,
            "image": str((folder / "source.png").resolve()),
            "cache_hit": False,
        }

    def _open(self):
        if self.page:
            return
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=True)
        self.page = self._browser.new_page(
            viewport={"width": self.profile.width, "height": self.profile.height}
        )
        self.page.goto(
            self.url
            + f"?sse={self.profile.inspection_sse}&cache={self.profile.inspection_cache_mb}",
            wait_until="load",
            timeout=60000,
        )
        self.page.wait_for_function(
            "()=>window.__GOOGLE_REFERENCE_READY__||window.__GOOGLE_REFERENCE_FAILURE__",
            timeout=60000,
        )
        if self.page.evaluate("!!window.__GOOGLE_REFERENCE_FAILURE__"):
            raise RuntimeError("PROVIDER_CONNECTION_FAILED")
        self.page.evaluate(
            "o=>window.configureEvidenceCapture(o)",
            {"solarNoonDate": self.profile.solar_noon_date},
        )
        self.page.locator("header").evaluate('el=>el.style.display="none"')
        self.page.evaluate("window.clipEvidenceFootprint(null)")

    def _capture(self, q, folder):
        self._open()
        page = self.page
        centre = [(a + b) / 2 for a, b in zip(q.roi.min, q.roi.max)]
        fitted = fit_range(
            q.roi,
            q.heading,
            q.pitch,
            self.profile.width,
            self.profile.height,
            padding=1.06 if q.mode == "detail" else 1.12,
        )
        # Explicit ranges cannot crop requested geometry or pull the camera far away.
        distance = max(fitted, min(q.range_m or fitted, fitted * 1.3))
        target = [
            self.frame.longitude + math.degrees(centre[0] / self.frame.east_radius),
            self.frame.latitude - math.degrees(centre[2] / self.frame.north_radius),
            self.frame.ground + centre[1],
        ]
        page.evaluate("p=>window.setEvidenceTarget(...p)", target)
        page.evaluate("p=>window.setEvidenceView(...p)", [q.heading, q.pitch, distance])
        deadline = time.monotonic() + self.profile.ready_timeout_s
        stable = 0
        while time.monotonic() < deadline:
            page.wait_for_timeout(self.profile.poll_interval_ms)
            stats = page.evaluate("window.googleEvidenceStats()")
            stable = (
                stable + 1 if stats["tilesLoaded"] and stats["selectedTiles"] > 0 else 0
            )
            if stable >= self.profile.stable_samples:
                break
        complete = stable >= self.profile.stable_samples
        if not complete and stats["selectedTiles"] <= 0:
            raise RuntimeError("CAPTURE_TILES_NOT_READY")
        if stats["renderErrors"]:
            raise RuntimeError("CAPTURE_RENDER_ERRORS")
        page.screenshot(path=str(folder / "source.png"))
        gray = Image.open(folder / "source.png").convert("L")
        contrast = ImageStat.Stat(gray).stddev[0]
        edge = ImageStat.Stat(gray.filter(ImageFilter.FIND_EDGES)).mean[0]
        depth = page.evaluate("window.inspectEvidenceFrame()")
        surface = depth.get("median_surface_distance_m")
        occluded = surface is not None and surface < distance * 0.60
        camera = camera_in_region(stats["camera"], self.frame, distance)
        visibility = {}
        for entity_id in q.entity_ids:
            entity = self.region.index()[entity_id]
            box = entity.world_bounds()
            xs = [
                (box.min[0] + box.max[0]) / 2,
                box.min[0] + 0.25 * (box.max[0] - box.min[0]),
                box.max[0] - 0.25 * (box.max[0] - box.min[0]),
            ]
            zs = [
                (box.min[2] + box.max[2]) / 2,
                box.min[2] + 0.25 * (box.max[2] - box.min[2]),
                box.max[2] - 0.25 * (box.max[2] - box.min[2]),
            ]
            pixels = []
            for x, z in zip(
                [xs[0], xs[1], xs[1], xs[2], xs[2]], [zs[0], zs[1], zs[2], zs[1], zs[2]]
            ):
                rect = project_bounds(
                    camera,
                    Bounds(
                        min=(x - 0.01, box.max[1] - 0.02, z - 0.01),
                        max=(x + 0.01, box.max[1], z + 0.01),
                    ),
                )
                if rect:
                    pixels.append(
                        [(a + b) / 2 for a, b in zip(rect["min"], rect["max"])]
                    )
            hits = page.evaluate(
                "points=>points.map(p=>window.inspectEvidencePoint(...p))", pixels
            )
            samples = []
            for pixel, hit in zip(pixels, hits):
                point = (
                    self.frame.model(hit["longitude"], hit["latitude"], hit["height"])
                    if hit
                    else None
                )
                matched = bool(
                    point
                    and entity.owns(point)
                    and (
                        entity.kind != "building"
                        or point[1] > entity.anchor[1] + entity.eave_m * 0.15
                    )
                )
                samples.append(
                    {
                        "pixel": pixel,
                        "surface_world": point,
                        "matches_prior_volume": matched,
                    }
                )
            visibility[entity_id] = {
                "sampled": len(samples),
                "matched": sum(s["matches_prior_volume"] for s in samples),
                "samples": samples,
                "note": "Depth/footprint consistency check, not semantic segmentation; sampled roofs or canopies can differ from surveyed object boundaries.",
            }
        return {
            "source": "Google Photorealistic 3D Tiles via Cesium ion",
            "camera": camera,
            "actual_camera": stats["camera"],
            "stats": {k: v for k, v in stats.items() if k != "camera"},
            "quality": {
                "usable": complete and contrast > 5 and edge > 0.3 and not occluded,
                "tiles_complete": complete,
                "warning": None
                if complete
                else "Partial source frame retained for diagnosis; do not assume full detail or count it as accepted evidence coverage.",
                "contrast_std": round(contrast, 2),
                "edge_mean": round(edge, 2),
                "likely_occluded": occluded,
                "depth": depth,
                "entity_visibility": visibility,
                "note": "Image/depth heuristics only; critic must verify ROI visibility and detail. No semantic resolution guarantee.",
            },
        }
