"""Evidence-derived building massing: geometry is compiled, parameters are fitted.

A building is described by a small typed ``BuildingProgram``. The wall plan is
the evidence footprint itself; roof form and heights are chosen by rendering
candidate massings through the calibrated evidence cameras and comparing
silhouettes. A language model may propose programme *parameters* (storeys,
bays, dormers, colours) but never writes coordinates, so a correction cannot
move a wing or mirror a plan.

Every part is a ``loft``: horizontal rings ``{y, points[[x, z]]}`` joined by
flat faces. The same rings feed the Python silhouette rasteriser used for
fitting and the Three.js generator used for rendering, so both agree by
construction. Frame: X east, Y up, Z south, metres.
"""

import math
from typing import Literal

import numpy as np
from PIL import Image, ImageDraw
from pydantic import BaseModel, ConfigDict, Field

from . import georef

ROOF_FORMS = ("flat", "hip", "gable", "mansard")
_IMAGES = {}  # decoded evidence views at fitting resolution, keyed by (path, size)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Registration(Strict):
    """Rigid correction of an approximate footprint against imagery."""

    dx: float = 0.0
    dz: float = 0.0
    grow: float = 0.0


class Roof(Strict):
    form: Literal["flat", "hip", "gable", "mansard"] = "flat"
    rise: float = Field(default=0.0, ge=0)
    # Mansard only: share of the rise in the steep lower slope, and its run/rise.
    lower_fraction: float = Field(default=0.6, gt=0, lt=1)
    lower_run: float = Field(default=0.35, ge=0, le=2)
    overhang: float = Field(default=0.0, ge=0, le=2)


class Dormers(Strict):
    spacing_m: float = Field(gt=1)
    width_m: float = Field(default=1.6, gt=0.3)
    height_m: float = Field(default=1.8, gt=0.3)
    min_edge_m: float = Field(default=8.0, gt=0)


class Chimneys(Strict):
    spacing_m: float = Field(gt=2)
    width_m: float = Field(default=1.0, gt=0.2)
    above_ridge_m: float = Field(default=1.2, ge=0)


class Appearance(Strict):
    wall: str = "#9a8f84"
    roof: str = "#5c6470"
    trim: str = "#d8d2c4"
    glass: str = "#2f3d48"
    source: str = "default; no image evidence sampled"


class BuildingProgram(Strict):
    schema_version: Literal["worldscale-program-1"] = "worldscale-program-1"
    registration: Registration = Registration()
    eave_height: float = Field(gt=0)
    roof: Roof = Roof()
    storeys: int = Field(default=1, ge=1, le=120)
    bay_m: float = Field(default=3.2, gt=0.8, le=12)
    window_width: float = Field(default=0.42, gt=0.05, lt=0.95)
    window_height: float = Field(default=0.55, gt=0.05, lt=0.95)
    cornice: bool = True
    dormers: Dormers | None = None
    chimneys: Chimneys | None = None
    appearance: Appearance = Appearance()
    provenance: dict[str, str] = {}


# --- plan geometry -------------------------------------------------------


def to_plan(footprint):
    """[x, z] (z south) -> counter-clockwise [x, north]."""
    plan = [[float(x), -float(z)] for x, z in footprint]
    return plan if georef.area(plan) > 0 else plan[::-1]


def from_plan(plan):
    return [[x, -n] for x, n in plan]


def edge_lengths(plan):
    return [math.dist(a, b) for a, b in zip(plan, plan[1:] + plan[:1])]


def offset(plan, distances):
    """Mitered inward offset with one distance per edge; None when it degenerates."""
    count = len(plan)
    if isinstance(distances, (int, float)):
        distances = [distances] * count
    lines = []
    for i in range(count):
        a, b = plan[i], plan[(i + 1) % count]
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        if length < 1e-9:
            return None
        dx, dy = dx / length, dy / length
        d = distances[i]
        lines.append(((a[0] - dy * d, a[1] + dx * d), (dx, dy)))
    result = []
    for i in range(count):
        (p, r), (q, s) = lines[i - 1], lines[i]
        cross = r[0] * s[1] - r[1] * s[0]
        if abs(cross) < 1e-9:
            result.append([q[0], q[1]])
            continue
        t = ((q[0] - p[0]) * s[1] - (q[1] - p[1]) * s[0]) / cross
        result.append([p[0] + r[0] * t, p[1] + r[1] * t])
    for i in range(count):
        a, b = result[i], result[(i + 1) % count]
        direction = lines[i][1]
        if (b[0] - a[0]) * direction[0] + (b[1] - a[1]) * direction[1] <= 1e-6:
            return None
    return result if georef.area(result) > 1e-6 else None


def inset_limit(plan, weights=None):
    """Largest uniform inset (scaled per edge by ``weights``) keeping the plan simple."""
    weights = weights or [1.0] * len(plan)
    low, high = 0.0, max(edge_lengths(plan))
    for _ in range(40):
        mid = (low + high) / 2
        if offset(plan, [mid * w for w in weights]) is None:
            high = mid
        else:
            low = mid
    return low


def end_edges(plan):
    """Edges about as short as the body is wide: the ends of a wing."""
    limit = inset_limit(plan)
    return [length <= 2.4 * limit for length in edge_lengths(plan)]


def registered_plan(footprint, registration):
    plan = to_plan(footprint)
    if registration.grow:
        grown = offset(plan, -registration.grow)
        plan = grown or plan
    return [[x + registration.dx, n - registration.dz] for x, n in plan]


# --- compilation to lofts ------------------------------------------------


def loft(part_id, material, rings, **extra):
    return {
        "id": part_id,
        "material": material,
        "rings": [{"y": float(y), "points": from_plan(plan)} for y, plan in rings],
        **extra,
    }


def rectangle(centre, along, half_length, half_depth):
    """Counter-clockwise rectangle in plan around ``centre``; ``along`` is a unit vector."""
    ax, ay = along
    nx, ny = -ay, ax
    cx, cy = centre
    return [
        [cx - ax * half_length - nx * half_depth, cy - ay * half_length - ny * half_depth],
        [cx + ax * half_length - nx * half_depth, cy + ay * half_length - ny * half_depth],
        [cx + ax * half_length + nx * half_depth, cy + ay * half_length + ny * half_depth],
        [cx - ax * half_length + nx * half_depth, cy - ay * half_length + ny * half_depth],
    ]


def roof_rings(plan, program):
    """Rings of the main roof above the eave, and the plan-inset reached at each."""
    roof, eave = program.roof, program.eave_height
    base = offset(plan, -roof.overhang) if roof.overhang else plan
    base = base or plan
    if roof.form == "flat" or roof.rise <= 0:
        return [(eave, base), (eave + max(roof.rise, 0.3), base)], [0.0, 0.0]
    weights = (
        [0.0 if end else 1.0 for end in end_edges(plan)]
        if roof.form == "gable"
        else [1.0] * len(plan)
    )
    if not any(weights):
        weights = [1.0] * len(plan)
    limit = inset_limit(plan, weights) * 0.96
    rings, insets = [(eave, base)], [0.0]
    if roof.form == "mansard":
        lower = roof.rise * roof.lower_fraction
        inset = min(lower * roof.lower_run, limit * 0.6)
        rings.append((eave + lower, offset(plan, [inset * w for w in weights])))
        insets.append(inset)
    rings.append((eave + roof.rise, offset(plan, [limit * w for w in weights])))
    insets.append(limit)
    return rings, insets


def roof_height_at(inset, rings, insets):
    """Height of the roof surface at a given plan inset from the eave line."""
    for (y0, _), (y1, _), d0, d1 in zip(rings, rings[1:], insets, insets[1:]):
        if d1 > d0 and inset <= d1:
            return y0 + (y1 - y0) * (inset - d0) / (d1 - d0)
    return rings[-1][0]


def compile_parts(footprint, program, measured_roof=None):
    """Deterministic parts for one building in its local metric frame.

    With ``measured_roof`` (a plane recipe fitted to a height field) the roof,
    towers, dormers and stacks come from measurement; the parametric roof and
    its repeated details are the fallback when no height field exists.
    """
    plan = registered_plan(footprint, program.registration)
    eave = program.eave_height
    if measured_roof:
        storey = eave / program.storeys
        parts = [
            loft(
                "walls",
                "wall",
                [(0.0, plan), (eave, plan)],
                facade={"bay_m": program.bay_m, "storey_m": storey},
            )
        ]
        if program.cornice and eave > 4 and offset(plan, -0.25):
            band = offset(plan, -0.25)
            parts.append(loft("cornice", "trim", [(eave - 0.45, band), (eave, band)]))
            plinth = offset(plan, -0.12)
            parts.append(loft("plinth", "trim", [(0.0, plinth), (min(0.9, 0.2 * storey), plinth)]))
        parts.append(
            {
                "id": "roof",
                "kind": "roof_planes",
                "material": "roof",
                # Faces above the eave are roof cladding unless imagery says otherwise;
                # classifying them per face from the views is not implemented yet.
                "side_material": "roof-side",
                "frame_angle_rad": measured_roof["frame_angle_rad"],
                "base_y": measured_roof["base_y"],
                "planes": measured_roof["planes"],
            }
        )
        return parts
    storey = eave / program.storeys
    parts = [
        loft(
            "walls",
            "wall",
            [(0.0, plan), (eave, plan)],
            facade={"bay_m": program.bay_m, "storey_m": storey},
        )
    ]
    if program.cornice and eave > 4:
        band = offset(plan, -0.25)
        if band:
            parts.append(loft("cornice", "trim", [(eave - 0.45, band), (eave, band)]))
            plinth = offset(plan, -0.12)
            parts.append(loft("plinth", "trim", [(0.0, plinth), (min(0.9, 0.2 * storey), plinth)]))
    rings, insets = roof_rings(plan, program)
    parts.append(loft("roof", "roof", rings))
    sloped = program.roof.form != "flat" and program.roof.rise > 0
    lengths, ends = edge_lengths(plan), end_edges(plan)
    if program.dormers and sloped:
        d = program.dormers
        depth = min(d.width_m * 1.4, insets[-1] * 0.8)
        for i, (a, b) in enumerate(zip(plan, plan[1:] + plan[:1])):
            if lengths[i] < d.min_edge_m or (program.roof.form == "gable" and ends[i]):
                continue
            along = ((b[0] - a[0]) / lengths[i], (b[1] - a[1]) / lengths[i])
            normal = (-along[1], along[0])
            count = max(1, round(lengths[i] / d.spacing_m))
            for k in range(count):
                s = lengths[i] * (k + 0.5) / count
                centre = (
                    a[0] + along[0] * s + normal[0] * (depth / 2 + 0.05),
                    a[1] + along[1] * s + normal[1] * (depth / 2 + 0.05),
                )
                sill = roof_height_at(0.05, rings, insets)
                body = rectangle(centre, along, d.width_m / 2, depth / 2)
                ridge = rectangle(centre, along, 0.04, depth / 2)
                parts.append(
                    loft(
                        f"dormer-{i}-{k}",
                        "roof",
                        [
                            (sill, body),
                            (sill + d.height_m * 0.65, body),
                            (sill + d.height_m, ridge),
                        ],
                    )
                )
                face_centre = (
                    a[0] + along[0] * s + normal[0] * 0.03,
                    a[1] + along[1] * s + normal[1] * 0.03,
                )
                glass = rectangle(face_centre, along, d.width_m * 0.3, 0.04)
                parts.append(
                    loft(
                        f"dormer-window-{i}-{k}",
                        "glass",
                        [(sill + d.height_m * 0.12, glass), (sill + d.height_m * 0.58, glass)],
                    )
                )
    if program.chimneys and sloped:
        c = program.chimneys
        inset = insets[-1] * 0.72
        top = rings[-1][0] + c.above_ridge_m
        line = offset(plan, inset)
        if line:
            for i, (a, b) in enumerate(zip(line, line[1:] + line[:1])):
                length = math.dist(a, b)
                if lengths[i] < 2 * c.spacing_m or length < c.spacing_m:
                    continue
                along = ((b[0] - a[0]) / length, (b[1] - a[1]) / length)
                count = max(1, round(length / c.spacing_m))
                for k in range(count):
                    s = length * (k + 0.5) / count
                    centre = (a[0] + along[0] * s, a[1] + along[1] * s)
                    stack = rectangle(centre, along, c.width_m / 2, c.width_m * 0.3)
                    parts.append(
                        loft(
                            f"chimney-{i}-{k}",
                            "trim",
                            [(roof_height_at(inset, rings, insets) - 0.3, stack), (top, stack)],
                        )
                    )
    return parts


def part_faces(part):
    """Planar faces (lists of xyz) of a loft: side quads and the top cap."""
    rings = part["rings"]
    faces = []
    for low, high in zip(rings, rings[1:]):
        a, b = low["points"], high["points"]
        count = len(a)
        for i in range(count):
            j = (i + 1) % count
            faces.append(
                [
                    [a[i][0], low["y"], a[i][1]],
                    [a[j][0], low["y"], a[j][1]],
                    [b[j][0], high["y"], b[j][1]],
                    [b[i][0], high["y"], b[i][1]],
                ]
            )
    top = rings[-1]
    faces.append([[x, top["y"], z] for x, z in top["points"]])
    return faces


def silhouette(camera, parts, size):
    """Rasterised union of projected faces; matches the browser's loft mesh."""
    width, height = size
    sx, sy = width / camera["width"], height / camera["height"]
    image = Image.new("L", size, 0)
    draw = ImageDraw.Draw(image)
    for part in parts:
        for face in part_faces(part):
            pixels, depth = georef.project(camera, face)
            if np.any(depth <= 1e-6) or np.any(~np.isfinite(pixels)):
                continue
            draw.polygon([(float(x) * sx, float(y) * sy) for x, y in pixels], fill=255)
    return np.asarray(image) > 0


# --- fitting -------------------------------------------------------------


def reference_masks(evidence, size_width=360):
    masks = {}
    for view in evidence["views"]:
        camera = view["camera"]
        size = (size_width, round(size_width * camera["height"] / camera["width"]))
        mask = georef.scoped_reference(view, evidence)
        masks[view["id"]] = (
            georef.outline(np.asarray(Image.fromarray(mask).resize(size, Image.NEAREST))),
            size,
        )
    return masks


def colour_separation(evidence, program, views, width=300):
    """Fisher separation of wall-region and roof-region chromaticity.

    The eave is where the facade material gives way to the roof material. A
    silhouette cannot place that line; the colour change can, when one exists.
    """
    parts = {p["id"]: p for p in compile_parts(evidence["footprint"], program)}
    total = 0.0
    for view in evidence["views"]:
        if view["id"] not in views:
            continue
        camera = view["camera"]
        size = (width, round(width * camera["height"] / camera["width"]))
        key = (view["image"], size)
        if key not in _IMAGES:
            _IMAGES[key] = np.asarray(
                Image.open(view["image"]).convert("RGB").resize(size), float
            )
        rgb = _IMAGES[key]
        lit = rgb.sum(axis=2) > 150
        chroma = rgb / np.maximum(rgb.sum(axis=2, keepdims=True), 1)
        roof = silhouette(camera, [parts["roof"]], size)
        walls = silhouette(camera, [parts["walls"]], size) & ~roof
        a, b = chroma[walls & lit], chroma[roof & lit]
        if len(a) < 150 or len(b) < 150:
            continue
        spread = a.var(axis=0).sum() + b.var(axis=0).sum() + 1e-6
        total += float(((a.mean(axis=0) - b.mean(axis=0)) ** 2).sum() / spread)
    return total


def score(evidence, masks, program, views=None):
    parts = [
        p
        for p in compile_parts(evidence["footprint"], program)
        if p["id"] in ("walls", "roof")
    ]
    result = {}
    for view in evidence["views"]:
        if views and view["id"] not in views:
            continue
        mask, size = masks[view["id"]]
        result[view["id"]] = georef.iou(
            mask, georef.outline(silhouette(view["camera"], parts, size))
        )
    return result


def is_plan_view(view):
    position, forward, _, _ = georef.camera_basis(view["camera"])
    return forward[1] < -0.95


def fit(evidence, program=None):
    """Choose registration, eave height, roof form and rise from silhouettes alone."""
    masks = reference_masks(evidence)
    height = float(evidence["height_m"])
    program = program or BuildingProgram(eave_height=height)
    oblique = [v["id"] for v in evidence["views"] if not is_plan_view(v)] or None
    trace = []

    def mean(candidate, views=None):
        values = score(evidence, masks, candidate, views)
        return sum(values.values()) / len(values)

    def update(candidate, **changes):
        return candidate.model_copy(update=changes)

    def register(start, steps):
        """Rigid registration of the approximate footprint, using every view."""
        best, best_score = start, mean(start)
        for step in steps:
            improved = True
            while improved:
                improved = False
                r = best.registration
                for name, delta in (
                    ("dx", step),
                    ("dx", -step),
                    ("dz", step),
                    ("dz", -step),
                    ("grow", step / 2),
                    ("grow", -step / 2),
                ):
                    value = getattr(r, name) + delta
                    if abs(value) > (3.0 if name == "grow" else 6.0):
                        continue
                    candidate = update(best, registration=r.model_copy(update={name: value}))
                    s = mean(candidate)
                    if s > best_score + 1e-4:
                        best, best_score, improved = candidate, s, True
                        r = best.registration
        return best, best_score

    # 1. First registration against a plain prism at the prior height.
    best, best_score = register(program, (2.0, 1.0, 0.5))
    trace.append({"stage": "registration", "score": best_score, **best.registration.model_dump()})

    # 2. Roof form and heights from oblique views; a simpler form wins ties.
    totals = [height * f for f in (0.8, 0.9, 1.0, 1.1, 1.2, 1.3)]
    options = []
    for form in ROOF_FORMS:
        for total in totals:
            for share in (0.0,) if form == "flat" else (0.15, 0.25, 0.35, 0.45, 0.55):
                rise = total * share
                candidate = update(
                    best,
                    eave_height=total - rise,
                    roof=best.roof.model_copy(update={"form": form, "rise": rise}),
                )
                options.append((mean(candidate, oblique), -ROOF_FORMS.index(form), candidate))
    top = max(o[0] for o in options)
    chosen = max((o for o in options if o[0] >= top - 0.004), key=lambda o: (o[1], o[0]))
    best, best_score = chosen[2], chosen[0]
    by_form = {
        form: round(max(o[0] for o in options if o[2].roof.form == form), 4)
        for form in ROOF_FORMS
    }
    trace.append({"stage": "roof", "score": best_score, "best_by_form": by_form})

    # 3. Local refinement of the continuous heights.
    for step in (1.0, 0.5, 0.25):
        improved = True
        while improved:
            improved = False
            for field, delta in (("eave", step), ("eave", -step), ("rise", step), ("rise", -step)):
                eave = best.eave_height + (delta if field == "eave" else 0)
                rise = best.roof.rise + (delta if field == "rise" else 0)
                if eave < 2 or rise < 0 or (best.roof.form != "flat" and rise < 0.5):
                    continue
                candidate = update(
                    best, eave_height=eave, roof=best.roof.model_copy(update={"rise": rise})
                )
                s = mean(candidate, oblique)
                if s > best_score + 1e-4:
                    best, best_score, improved = candidate, s, True
    trace.append(
        {
            "stage": "refine",
            "score": best_score,
            "eave_height": best.eave_height,
            "rise": best.roof.rise,
            "form": best.roof.form,
        }
    )
    # 4. Eave line from the wall/roof colour change; the silhouette fixes the total.
    eave_source = "fitted to scoped multi-view silhouettes"
    fit_views = oblique or [v["id"] for v in evidence["views"]]
    total = best.eave_height + best.roof.rise
    shares = [0.45 + 0.05 * i for i in range(11)]
    forms = [best.roof.form] if best.roof.form != "flat" else ["hip"]
    curve = []
    for share in shares:
        candidate = update(
            best,
            eave_height=total * share,
            roof=best.roof.model_copy(update={"form": forms[0], "rise": total * (1 - share)}),
        )
        curve.append((colour_separation(evidence, candidate, fit_views), share))
    peak, share = max(curve)
    floor = min(c[0] for c in curve)
    if peak > 0.6 and peak > 1.25 * max(floor, 1e-6):
        alternatives = []
        for form in ("hip", "gable", "mansard"):
            candidate = update(
                best,
                eave_height=total * share,
                roof=best.roof.model_copy(update={"form": form, "rise": total * (1 - share)}),
            )
            alternatives.append((mean(candidate, oblique), -ROOF_FORMS.index(form), candidate))
        top = max(a[0] for a in alternatives)
        chosen = max((a for a in alternatives if a[0] >= top - 0.004), key=lambda a: (a[1], a[0]))
        best, best_score = chosen[2], chosen[0]
        eave_source = "wall/roof colour boundary in evidence views; total height from silhouettes"
    trace.append(
        {
            "stage": "eave-colour",
            "applied": eave_source.startswith("wall/roof"),
            "separation_by_eave_share": [[round(s, 2), round(v, 3)] for v, s in curve],
            "score": best_score,
            "eave_height": best.eave_height,
            "rise": best.roof.rise,
            "form": best.roof.form,
        }
    )
    # 5. A wrong prior height biases the first registration (a plan that is too
    # low gets grown to compensate); settle it again with the fitted roof.
    best = update(best, registration=Registration(dx=best.registration.dx, dz=best.registration.dz))
    best, all_view_score = register(best, (0.5, 0.25))
    trace.append(
        {"stage": "registration-final", "score": all_view_score, **best.registration.model_dump()}
    )
    per_view = score(evidence, masks, best)
    best = update(
        best,
        provenance={
            **best.provenance,
            "registration": "fitted to scoped multi-view silhouettes",
            "eave_height": eave_source,
            "roof": "form and rise selected by multi-view silhouette IoU",
        },
    )
    return best, {"per_view_iou": per_view, "trace": trace, "fit_views": oblique}


# --- appearance and defaults ---------------------------------------------


def hex_colour(rgb):
    return "#%02x%02x%02x" % tuple(int(max(0, min(255, round(v)))) for v in rgb)


def shade(colour, factor):
    return hex_colour([int(colour[i : i + 2], 16) * factor for i in (1, 3, 5)])


def sample_appearance(evidence, program, keys=("wall", "roof")):
    """Median lit colour of wall and roof regions seen through the evidence cameras.

    Photogrammetry bakes shadows in; the brighter half of each region is used as
    an albedo estimate. It is a material cue, not a measured reflectance.
    """
    parts = {p["id"]: p for p in compile_parts(evidence["footprint"], program)}
    samples = {"walls": [], "roof": []}
    for view in evidence["views"]:
        camera = view["camera"]
        size = (camera["width"], camera["height"])
        rgb = np.asarray(Image.open(view["image"]).convert("RGB"))
        reference = georef.scoped_reference(view, evidence)
        roof = silhouette(camera, [parts["roof"]], size)
        walls = silhouette(camera, [parts["walls"]], size) & ~roof
        for name, region in (("walls", walls), ("roof", roof)):
            if name == "walls" and is_plan_view(view):
                continue
            pixels = rgb[region & reference]
            if len(pixels) < 500:
                continue
            pixels = pixels.astype(float)
            luma = pixels @ np.array([0.299, 0.587, 0.114])
            lit = pixels[luma >= np.percentile(luma, 60)]
            # Shadow, haze and blown highlights are all less saturated than the
            # surface they fall on, so the more saturated half is closer to albedo.
            saturation = (lit.max(axis=1) - lit.min(axis=1)) / np.maximum(lit.max(axis=1), 1)
            samples[name].append(lit[saturation >= np.median(saturation)])
    appearance = program.appearance.model_dump()
    sampled = False
    for name, key in (("walls", "wall"), ("roof", "roof")):
        if samples[name] and key in keys:
            appearance[key] = hex_colour(np.median(np.concatenate(samples[name]), axis=0))
            sampled = True
    if sampled and len(keys) < 2:
        appearance["source"] += "; " + "/".join(keys) + " re-sampled from sunlit pixels"
    elif sampled:
        appearance["source"] = (
            "median of bright, more-saturated pixels in projected wall/roof regions; an albedo cue from baked photogrammetry, not a measurement"
        )
    return program.model_copy(update={"appearance": Appearance(**appearance)})


def default_program(height, tags=None):
    """Programme for a building with no imagery: tags and typical proportions only."""
    tags = tags or {}
    levels = None
    try:
        levels = int(float(tags.get("building:levels", "")))
    except ValueError:
        pass
    storeys = levels or max(1, round(height / 3.4))
    shape = {"gabled": "gable", "hipped": "hip", "mansard": "mansard"}.get(
        tags.get("roof:shape", ""), "flat"
    )
    rise = 0.0 if shape == "flat" else min(0.3 * height, 6.0)
    return BuildingProgram(
        eave_height=height - rise,
        roof=Roof(form=shape, rise=rise),
        storeys=storeys,
        cornice=False,
        provenance={"all": "OSM tags and typical proportions; no image evidence"},
    )


def tag_height(tags, default_storey=3.4):
    """Height in metres from OSM tags, with the tag that supplied it."""
    for key in ("height", "building:height"):
        try:
            return float(str(tags.get(key, "")).replace("m", "").strip()), key
        except ValueError:
            continue
    try:
        return float(tags["building:levels"]) * default_storey, "building:levels"
    except (KeyError, ValueError):
        return 3 * default_storey, "assumed three storeys"


# --- World IR ------------------------------------------------------------


def blueprint(blueprint_id, parts, program, tier="family", version="1.0.0"):
    a = program.appearance
    return {
        "id": blueprint_id,
        "version": version,
        "tier": tier,
        "origin": "semantic",
        "components": [
            {**p, "size": [1, 1, 1], "confidence": "observed"}
            if p.get("kind") == "roof_planes"
            else {
                "id": p["id"],
                "kind": "loft",
                "size": bounding_size(p),
                "material": p["material"],
                "rings": p["rings"],
                **({"facade": p["facade"]} if "facade" in p else {}),
                "confidence": "observed" if p["id"] in ("walls", "roof") else "inferred",
            }
            for p in parts
        ],
        "materials": [
            {
                "id": "wall",
                "color": a.wall,
                "roughness": 0.85,
                "emission": "#ffcf82",
                "emissive_at_night": True,
                "pattern": {
                    "kind": "facade",
                    "window_width": program.window_width,
                    "window_height": program.window_height,
                    "glass": a.glass,
                    "trim": a.trim,
                },
            },
            {"id": "roof", "color": a.roof, "roughness": 0.7},
            {"id": "roof-side", "color": shade(a.roof, 0.82), "roughness": 0.75},
            {"id": "trim", "color": a.trim, "roughness": 0.8},
            {"id": "glass", "color": a.glass, "roughness": 0.25},
        ],
    }


def bounding_size(part):
    points = [p for ring in part["rings"] for p in ring["points"]]
    ys = [ring["y"] for ring in part["rings"]]
    xs, zs = [p[0] for p in points], [p[1] for p in points]
    return [
        max(max(xs) - min(xs), 1e-3),
        max(max(ys) - min(ys), 1e-3),
        max(max(zs) - min(zs), 1e-3),
    ]
