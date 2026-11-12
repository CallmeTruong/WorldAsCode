"""Georeferenced evidence: metric footprint, calibrated capture cameras, scoped silhouettes.

Model frame for every asset built from an evidence bundle: X = east, Y = up,
Z = south (so north is -Z), units are metres, origin is the footprint centroid at
local ground. The same frame is used by the browser camera, so a reference view
and its render share one projection instead of a searched approximation.
"""

import math
import xml.etree.ElementTree as ElementTree
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .artifacts import digest, file_hash, write_json

WGS84_A = 6378137.0
WGS84_E2 = 6.69437999014e-3
# Cesium's PerspectiveFrustum default: 60 degrees applied to the larger image side.
CESIUM_DEFAULT_FOV_DEG = 60.0


class Frame:
    """Local tangent plane; adequate for a single asset or a few city blocks."""

    def __init__(self, longitude, latitude, ground_height=0.0):
        self.longitude, self.latitude, self.ground = longitude, latitude, ground_height
        s = math.sin(math.radians(latitude))
        w = math.sqrt(1 - WGS84_E2 * s * s)
        self.north_radius = WGS84_A * (1 - WGS84_E2) / w**3
        self.east_radius = WGS84_A / w * math.cos(math.radians(latitude))

    def model(self, longitude, latitude, height=None):
        east = math.radians(longitude - self.longitude) * self.east_radius
        north = math.radians(latitude - self.latitude) * self.north_radius
        y = 0.0 if height is None else height - self.ground
        return [east, y, -north]

    def local_to_ecef(self):
        """Row-major transform from this frame (east, up, south metres) to ECEF."""
        lon, lat = math.radians(self.longitude), math.radians(self.latitude)
        sin_lon, cos_lon = math.sin(lon), math.cos(lon)
        sin_lat, cos_lat = math.sin(lat), math.cos(lat)
        n = WGS84_A / math.sqrt(1 - WGS84_E2 * sin_lat**2)
        origin = [
            (n + self.ground) * cos_lat * cos_lon,
            (n + self.ground) * cos_lat * sin_lon,
            (n * (1 - WGS84_E2) + self.ground) * sin_lat,
        ]
        east = [-sin_lon, cos_lon, 0]
        up = [cos_lat * cos_lon, cos_lat * sin_lon, sin_lat]
        south = [sin_lat * cos_lon, sin_lat * sin_lon, -cos_lat]
        return [
            [east[0], up[0], south[0], origin[0]],
            [east[1], up[1], south[1], origin[1]],
            [east[2], up[2], south[2], origin[2]],
            [0, 0, 0, 1],
        ]

    def to_ecef(self, east, up, south):
        point = np.asarray(self.local_to_ecef()) @ np.array([east, up, south, 1.0])
        return point[:3].tolist()

    def describe(self):
        return {
            "origin": {"longitude": self.longitude, "latitude": self.latitude},
            "ground_height_m": self.ground,
            "axes": "X east, Y up, Z south; metres",
        }


def osm_way(osm_path, way_id):
    root = ElementTree.parse(osm_path).getroot()
    nodes = {
        n.get("id"): (float(n.get("lon")), float(n.get("lat"))) for n in root.iter("node")
    }
    for way in root.iter("way"):
        if way.get("id") == str(way_id):
            ring = [nodes[n.get("ref")] for n in way.iter("nd")]
            if len(ring) > 1 and ring[0] == ring[-1]:
                ring = ring[:-1]
            return ring, {t.get("k"): t.get("v") for t in way.iter("tag")}
    raise KeyError("OSM_WAY_NOT_FOUND: " + str(way_id))


def osm_buildings(osm_path):
    """Every closed building way of a snapshot (multipolygon relations are not expanded)."""
    root = ElementTree.parse(osm_path).getroot()
    nodes = {
        n.get("id"): (float(n.get("lon")), float(n.get("lat"))) for n in root.iter("node")
    }
    result = []
    for way in root.iter("way"):
        tags = {t.get("k"): t.get("v") for t in way.iter("tag")}
        refs = [n.get("ref") for n in way.iter("nd")]
        if "building" not in tags or len(refs) < 4 or refs[0] != refs[-1]:
            continue
        result.append(
            {"id": "way/" + way.get("id"), "ring": [nodes[r] for r in refs[:-1]], "tags": tags}
        )
    return result


def area(polygon):
    return 0.5 * sum(
        a[0] * b[1] - b[0] * a[1] for a, b in zip(polygon, polygon[1:] + polygon[:1])
    )


def centroid(polygon):
    a = area(polygon)
    cx = cy = 0.0
    for p, q in zip(polygon, polygon[1:] + polygon[:1]):
        cross = p[0] * q[1] - q[0] * p[1]
        cx += (p[0] + q[0]) * cross
        cy += (p[1] + q[1]) * cross
    return [cx / (6 * a), cy / (6 * a)]


def principal_angle(polygon):
    """Direction (radians, in the polygon plane) of the length-weighted dominant edge."""
    sx = sy = 0.0
    for p, q in zip(polygon, polygon[1:] + polygon[:1]):
        dx, dy = q[0] - p[0], q[1] - p[1]
        length = math.hypot(dx, dy)
        if not length:
            continue
        # Edges at 90 degree multiples vote for the same axis: quadruple the angle.
        angle = 4 * math.atan2(dy, dx)
        sx += length * math.cos(angle)
        sy += length * math.sin(angle)
    return math.atan2(sy, sx) / 4


def wings(polygon, tolerance=0.75):
    """Decompose a near-rectilinear footprint into axis-aligned rectangles.

    Returned rectangles are in the polygon's own plane: centre, size along the
    principal axis (``length``) and across it (``width``), and the axis angle.
    They are a layout aid for roof authoring, not a replacement for the polygon.
    """
    angle = principal_angle(polygon)
    c, s = math.cos(-angle), math.sin(-angle)
    local = [[p[0] * c - p[1] * s, p[0] * s + p[1] * c] for p in polygon]
    levels = []
    for v in sorted(p[1] for p in local):
        if not levels or v - levels[-1] > tolerance:
            levels.append(v)
    slabs = []
    for low, high in zip(levels, levels[1:]):
        mid = (low + high) / 2
        crossings = []
        for p, q in zip(local, local[1:] + local[:1]):
            if (p[1] - mid) * (q[1] - mid) < 0:
                crossings.append(p[0] + (mid - p[1]) / (q[1] - p[1]) * (q[0] - p[0]))
        crossings.sort()
        for left, right in zip(crossings[::2], crossings[1::2]):
            previous = next(
                (
                    r
                    for r in slabs
                    if abs(r[3] - low) < 1e-6
                    and abs(r[0] - left) < tolerance
                    and abs(r[1] - right) < tolerance
                ),
                None,
            )
            if previous:
                previous[3] = high
            else:
                slabs.append([left, right, low, high])
    c, s = math.cos(angle), math.sin(angle)
    result = []
    for left, right, low, high in slabs:
        u, v = (left + right) / 2, (low + high) / 2
        result.append(
            {
                "centre": [u * c - v * s, u * s + v * c],
                "length": right - left,
                "width": high - low,
                "axis_angle_rad": angle,
            }
        )
    return result


def camera_basis(camera):
    position = np.array(camera["position"], float)
    forward = np.array(camera["target"], float) - position
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, [0.0, 1.0, 0.0])
    right_norm = np.linalg.norm(right)
    if right_norm < 1e-6:
        heading = math.radians(camera.get("heading_deg", 0.0))
        right = np.array([math.cos(heading), 0.0, math.sin(heading)])
    else:
        right /= right_norm
    return position, forward, right, np.cross(right, forward)


def vertical_fov(camera):
    """Vertical field of view in degrees for the capture's image aspect."""
    aspect = camera["width"] / camera["height"]
    half = math.radians(camera["fov_deg"]) / 2
    if aspect >= 1:  # the declared angle is on the larger (horizontal) side
        return math.degrees(2 * math.atan(math.tan(half) / aspect))
    return camera["fov_deg"]


def project(camera, points):
    """Project model-frame points to pixel coordinates; depth <= 0 is behind the camera."""
    if all(
        key in camera
        for key in ("local_to_ecef", "view_matrix", "projection_matrix")
    ):
        local = np.column_stack([np.asarray(points, float), np.ones(len(points))])
        transform = np.asarray(camera["local_to_ecef"], float).reshape(4, 4)
        # Cesium Matrix4.toArray serializes column-major matrices; the local
        # frame transform stored by this module is explicitly row-major.
        view = np.asarray(camera["view_matrix"], float).reshape(4, 4, order="F")
        projection = np.asarray(camera["projection_matrix"], float).reshape(
            4, 4, order="F"
        )
        clip = local @ transform.T @ view.T @ projection.T
        w = clip[:, 3]
        safe = np.where(w > 1e-9, w, np.nan)
        x, y = clip[:, 0] / safe, clip[:, 1] / safe
        pixels = np.stack(
            [(x + 1) * camera["width"] / 2, (1 - y) * camera["height"] / 2],
            axis=1,
        )
        return pixels, w
    position, forward, right, up = camera_basis(camera)
    relative = np.asarray(points, float) - position
    depth = relative @ forward
    tan_v = math.tan(math.radians(vertical_fov(camera)) / 2)
    tan_h = tan_v * camera["width"] / camera["height"]
    safe = np.where(depth > 1e-6, depth, np.nan)
    x = (relative @ right) / safe / tan_h
    y = (relative @ up) / safe / tan_v
    pixels = np.stack(
        [(x + 1) / 2 * camera["width"], (1 - y) / 2 * camera["height"]], axis=1
    )
    return pixels, depth


def prism_mask(camera, footprint, low, high, size=None, grow_px=0):
    """Image region that the footprint prism between two heights can occupy."""
    width, height = size or (camera["width"], camera["height"])
    sx, sy = width / camera["width"], height / camera["height"]
    image = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(image)
    rings = []
    for y in (low, high):
        pixels, depth = project(camera, [[x, y, z] for x, z in footprint])
        if np.any(depth <= 1e-6):
            raise ValueError("FOOTPRINT_BEHIND_EVIDENCE_CAMERA")
        rings.append([(float(px) * sx, float(py) * sy) for px, py in pixels])
    for ring in rings:
        draw.polygon(ring, fill=255)
    count = len(footprint)
    for i in range(count):
        j = (i + 1) % count
        draw.polygon([rings[0][i], rings[0][j], rings[1][j], rings[1][i]], fill=255)
    if grow_px:
        # Dilate at quarter resolution; the margin is a tolerance, not a boundary.
        small = image.resize((max(1, width // 4), max(1, height // 4)), Image.BOX)
        small = small.point(lambda v: 255 if v else 0).filter(
            ImageFilter.MaxFilter(2 * max(1, round(grow_px / 4)) + 1)
        )
        image = small.resize((width, height), Image.NEAREST)
    return np.asarray(image) > 0


_SCOPED = {}  # scoped reference masks for this process, keyed by view and scope content


def foreground(image, threshold=28):
    """Captured photogrammetry sits on a near-black sky with faint stars."""
    source = Image.open(image).convert("RGB")
    # Stars are one or two pixels wide: a median at half resolution removes them
    # at a quarter of the cost of filtering the full frame.
    small = source.resize((source.width // 2, source.height // 2), Image.BOX)
    bright = np.asarray(small.filter(ImageFilter.MedianFilter(3))).max(axis=2) > threshold
    return np.asarray(Image.fromarray(bright).resize(source.size, Image.NEAREST))


def scoped_reference(view, evidence, out_image=None, out_mask=None):
    """Reference silhouette restricted to where this object can project.

    Neighbour fragments, watermark text and star noise fall outside the scope
    prism and are removed; the dark shadowed facade inside it is kept.
    """
    camera = view["camera"]
    margin = evidence["scope"]
    key = digest(
        [view["image"], view.get("source_sha256"), camera, evidence["footprint"],
         evidence["height_m"], margin]
    )
    if key not in _SCOPED:
        scope = prism_mask(
            camera,
            evidence["footprint"],
            -margin["below_m"],
            evidence["height_m"] + margin["above_m"],
            grow_px=margin["grow_px"],
        )
        _SCOPED[key] = foreground(view["image"]) & scope
    mask = _SCOPED[key]
    if out_mask:
        Image.fromarray((mask * 255).astype(np.uint8)).save(out_mask)
    if out_image:
        rgb = np.asarray(Image.open(view["image"]).convert("RGB")).copy()
        rgb[~mask] = 0
        Image.fromarray(rgb).save(out_image)
    return mask


def outline(mask):
    """Fill enclosed holes so only the outer silhouette is compared.

    Deeply shadowed photogrammetry is as dark as the sky and would otherwise
    read as a see-through gap inside the building.

    A pixel is filled when foreground lies on all four sides along its row and
    column. Concave notches stay open; the test is vectorised so that fitting
    thousands of candidates stays cheap.
    """
    m = np.asarray(mask, bool)
    left = np.logical_or.accumulate(m, axis=1)
    right = np.logical_or.accumulate(m[:, ::-1], axis=1)[:, ::-1]
    above = np.logical_or.accumulate(m, axis=0)
    below = np.logical_or.accumulate(m[::-1], axis=0)[::-1]
    return m | (left & right & above & below)


def iou(a, b):
    union = np.logical_or(a, b).sum()
    return float(np.logical_and(a, b).sum() / union) if union else 0.0


def difference_image(reference_mask, render_mask, out):
    """Green = agreement, red = reference only (missing mass), blue = render only (excess)."""
    image = np.zeros((*reference_mask.shape, 3), np.uint8)
    image[reference_mask & render_mask] = (70, 170, 90)
    image[reference_mask & ~render_mask] = (220, 60, 50)
    image[~reference_mask & render_mask] = (60, 110, 230)
    Image.fromarray(image).save(out)


def region_report(reference_mask, render_mask, grid=3):
    """Where the silhouettes disagree, as fractions of each image cell."""
    h, w = reference_mask.shape
    cells = []
    for r in range(grid):
        for c in range(grid):
            window = (
                slice(r * h // grid, (r + 1) * h // grid),
                slice(c * w // grid, (c + 1) * w // grid),
            )
            ref, ren = reference_mask[window], render_mask[window]
            missing = float((ref & ~ren).mean())
            excess = float((~ref & ren).mean())
            if missing > 0.01 or excess > 0.01:
                cells.append(
                    {
                        "cell": f"row{r}col{c}",
                        "missing_fraction": round(missing, 3),
                        "excess_fraction": round(excess, 3),
                    }
                )
    return cells


def build_evidence(
    out,
    footprint_lonlat,
    capture_manifest,
    capture_folder,
    ground_height,
    height,
    object_id,
    label="",
    tags=None,
    primary=None,
    height_source="",
):
    """Write a self-contained evidence bundle next to hash-pinned copies of the views."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    lon0 = sum(p[0] for p in footprint_lonlat) / len(footprint_lonlat)
    lat0 = sum(p[1] for p in footprint_lonlat) / len(footprint_lonlat)
    rough = Frame(lon0, lat0)
    cx, cz = centroid([rough.model(*p)[::2] for p in footprint_lonlat])
    frame = Frame(
        lon0 + math.degrees(cx / rough.east_radius),
        lat0 - math.degrees(cz / rough.north_radius),
        ground_height,
    )
    footprint = [frame.model(*p)[::2] for p in footprint_lonlat]
    if area([[x, -z] for x, z in footprint]) < 0:
        footprint.reverse()
    target = capture_manifest["target"]
    look = frame.model(target["longitude"], target["latitude"], target["height"])
    views = []
    for v in capture_manifest["views"]:
        source = Path(capture_folder) / (v["view"] + ".png")
        with Image.open(source) as im:
            width, height_px = im.size
            destination = out / (v["view"] + ".png")
            im.save(destination)
        camera = v["stats"]["camera"]
        projection = camera.get("projection_matrix")
        view_matrix = camera.get("view_matrix")
        exact_matrices = (
            isinstance(projection, list)
            and len(projection) == 16
            and isinstance(view_matrix, list)
            and len(view_matrix) == 16
        )
        views.append(
            {
                "id": v["view"],
                "image": destination.name,
                "source_sha256": file_hash(destination),
                "camera": {
                    "position": frame.model(
                        camera["longitude"], camera["latitude"], camera["height"]
                    ),
                    "target": look,
                    "fov_deg": camera.get("fov_deg", CESIUM_DEFAULT_FOV_DEG),
                    "width": width,
                    "height": height_px,
                    "heading_deg": v.get("heading_deg", 0.0),
                    **(
                        {
                            "local_to_ecef": frame.local_to_ecef(),
                            "view_matrix": view_matrix,
                            "projection_matrix": projection,
                            "projection_source": "captured Cesium view/projection matrices",
                        }
                        if exact_matrices
                        else {
                            "projection_source": "reconstructed pose; FOV is an assumed Cesium default because capture matrices were not recorded"
                        }
                    ),
                },
                "calibration": (
                    "Exact capture view/projection matrices transformed into the local metric frame."
                    if exact_matrices
                    else "Approximate: recorded cartographic camera position and target, plus the assumed default frustum; verify against visible footprint edges."
                ),
            }
        )
    plan = [[x, -z] for x, z in footprint]
    evidence = {
        "schema": "worldscale-evidence-1",
        "object_id": object_id,
        "label": label,
        "source": capture_manifest.get("source"),
        "frame": frame.describe(),
        "footprint": footprint,
        "footprint_source": "OpenStreetMap way outline (ODbL); approximate",
        "wings": [
            {
                "centre_xz": [w["centre"][0], -w["centre"][1]],
                "length_m": w["length"],
                "width_m": w["width"],
                # Rotation about +Y that turns local +X onto the wing's long axis.
                "rotation_y_rad": w["axis_angle_rad"],
            }
            for w in wings(plan)
        ],
        "height_m": height,
        "height_source": height_source,
        "tags": tags or {},
        "scope": {"below_m": 1.0, "above_m": max(4.0, 0.35 * height), "grow_px": 14},
        "views": views,
        "primary_view": primary or views[0]["id"],
        "uncertainty": capture_manifest.get("uncertainty"),
    }
    write_json(out / "evidence.json", evidence)
    return evidence


def load_evidence(path):
    """Read a bundle and resolve view images to absolute paths."""
    import json

    path = Path(path)
    if path.is_dir():
        path = path / "evidence.json"
    evidence = json.loads(path.read_text(encoding="utf-8"))
    if evidence.get("schema") != "worldscale-evidence-1":
        raise ValueError("UNSUPPORTED_EVIDENCE_SCHEMA")
    if (
        not isinstance(evidence.get("footprint"), list)
        or len(evidence["footprint"]) < 3
        or not isinstance(evidence.get("views"), list)
        or not evidence["views"]
        or not isinstance(evidence.get("height_m"), (int, float))
        or evidence["height_m"] <= 0
    ):
        raise ValueError("INVALID_GEOREFERENCED_EVIDENCE")
    view_ids = set()
    for view in evidence["views"]:
        if view.get("id") in view_ids:
            raise ValueError("DUPLICATE_GEOREFERENCED_VIEW_ID")
        view_ids.add(view.get("id"))
        image = (path.parent / view["image"]).resolve()
        if not image.is_file():
            raise ValueError("GEOREFERENCED_VIEW_IMAGE_MISSING: " + str(image))
        if view.get("source_sha256") and file_hash(image) != view["source_sha256"]:
            raise ValueError("GEOREFERENCED_VIEW_HASH_MISMATCH: " + view.get("id", ""))
        view["image"] = str(image)
    if evidence.get("primary_view") not in view_ids:
        raise ValueError("GEOREFERENCED_PRIMARY_VIEW_MISSING")
    evidence["path"] = str(path.resolve())
    return evidence


def overlay(view, evidence, out):
    """Draw the footprint at ground and roof height over a view to audit calibration."""
    image = Image.open(view["image"]).convert("RGB")
    draw = ImageDraw.Draw(image)
    for y, colour in ((0.0, (0, 255, 120)), (evidence["height_m"], (255, 210, 0))):
        pixels, _ = project(view["camera"], [[x, y, z] for x, z in evidence["footprint"]])
        ring = [tuple(map(float, p)) for p in pixels]
        draw.line(ring + ring[:1], fill=colour, width=3)
    image.save(out)
