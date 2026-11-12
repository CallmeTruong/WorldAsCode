"""Focused service extracted from the reconstruction workflow."""

import base64
import io
from pathlib import Path

import numpy as np
from PIL import Image

import worldascode.evidence.georeference as georef


def sheet(paths, out, cell=(640, 480), columns=3):
    """Tile images into one JPEG so a review costs one image, not five."""
    rows = -(-len(paths) // columns)
    canvas = Image.new("RGB", (cell[0] * columns, cell[1] * rows), "#111111")
    for i, path in enumerate(paths):
        image = Image.open(path).convert("RGB")
        image.thumbnail(cell)
        canvas.paste(
            image,
            (
                i % columns * cell[0] + (cell[0] - image.width) // 2,
                i // columns * cell[1] + (cell[1] - image.height) // 2,
            ),
        )
    canvas.save(out, quality=88)
    return Path(out)


def reference_sheet(evidence, out):
    folder = Path(out).parent
    crops = []
    for view in evidence["views"]:
        path = folder / ("reference-" + view["id"] + ".png")
        georef.scoped_reference(view, evidence, out_image=path)
        crops.append(path)
    return sheet(crops, out)


def detail_sheet(evidence, folder, out, rendered=False):
    """Same source-derived image rectangles for source and candidate close-ups."""
    folder, out = Path(folder), Path(out)
    crops = []
    for view in evidence["views"]:
        mask = georef.scoped_reference(view, evidence)
        yy, xx = np.nonzero(mask)
        if not len(xx):
            continue
        source_w, source_h = mask.shape[1], mask.shape[0]
        image = Image.open(
            folder / ("view-" + view["id"] + ".png") if rendered else view["image"]
        ).convert("RGB")
        sx, sy = image.width / source_w, image.height / source_h
        x0, x1 = max(0, int(xx.min()) - 5), min(source_w, int(xx.max()) + 6)
        y0, y1 = max(0, int(yy.min()) - 5), min(source_h, int(yy.max()) + 6)
        mid = y0 + int((y1 - y0) * 0.52)
        for label, a, b in (("upper", y0, mid + 12), ("lower", mid - 12, y1)):
            path = out.parent / ("detail-" + view["id"] + "-" + label + ".jpg")
            image.crop(
                (round(x0 * sx), round(a * sy), round(x1 * sx), round(b * sy))
            ).save(path, quality=93)
            crops.append(path)
    return sheet(crops, out, cell=(720, 340), columns=2)


def render_camera(view, width=1100):
    camera = view["camera"]
    return {
        "position": camera["position"],
        "target": camera["target"],
        "fov_vertical_deg": georef.vertical_fov(camera),
        "render_width": width,
        "render_height": round(width * camera["height"] / camera["width"]),
    }


def evidence_capture(evidence, run, report):
    """Browser renders through each evidence camera, scored against the scoped reference."""
    run = Path(run)

    def extra(page, shots):
        for view in evidence["views"]:
            pose = render_camera(view)
            size = (pose["render_width"], pose["render_height"])
            page.evaluate("c=>worldscale.pose(c)", pose)
            name = "view-" + view["id"] + ".png"
            page.locator("canvas").screenshot(path=str(run / name))
            shots.append(name)
            data = page.evaluate("worldscale.silhouette()").split(",", 1)[1]
            shot = (
                Image.open(io.BytesIO(base64.b64decode(data))).convert("L").resize(size)
            )
            rendered = georef.outline(np.asarray(shot) > 100)
            scoped = run / ("reference-" + view["id"] + ".png")
            mask = georef.scoped_reference(view, evidence, out_image=scoped)
            reference = georef.outline(
                np.asarray(Image.fromarray(mask).resize(size, Image.NEAREST))
            )
            georef.difference_image(
                reference, rendered, run / ("diff-" + view["id"] + ".png")
            )
            report[view["id"]] = {
                "iou": round(georef.iou(reference, rendered), 4),
                "disagreement": georef.region_report(reference, rendered),
                "calibration": view.get("calibration"),
            }

    return extra
