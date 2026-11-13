"""Fit calibrated building bundles before regional detailing, with identity guards."""

import math

import numpy as np

from worldascode.contracts.region import Entity, Region
from worldascode.evidence import georeference as georef
from worldascode.geometry import massing
from worldascode.storage.artifacts import file_hash
from worldascode.workflows.massing import MASSING_MEAN_IOU, MASSING_MIN_IOU


def fit_region_massing(region, evidence_map):
    unknown = set(evidence_map) - set(region.index())
    if unknown:
        raise ValueError("MASSING_UNKNOWN_ENTITIES: " + ",".join(sorted(unknown)))
    region_frame = georef.Frame(
        region.origin.longitude, region.origin.latitude, region.origin.ground_height_m
    )
    inverse = np.linalg.inv(region_frame.local_to_ecef())
    entities, reports = [], {}
    for entity in region.entities:
        if entity.id not in evidence_map:
            entities.append(entity)
            continue
        evidence = georef.load_evidence(evidence_map[entity.id])
        if entity.kind != "building" or evidence.get("object_id") != entity.id:
            raise ValueError("MASSING_EVIDENCE_IDENTITY_MISMATCH: " + entity.id)
        frame = evidence["frame"]
        source_frame = georef.Frame(
            frame["origin"]["longitude"],
            frame["origin"]["latitude"],
            frame["ground_height_m"],
        )
        if frame.get("axes") != source_frame.describe()["axes"]:
            raise ValueError("MASSING_EVIDENCE_FRAME_AXES_MISMATCH")
        transform = inverse @ np.asarray(source_frame.local_to_ecef())
        c, s = math.cos(entity.yaw), math.sin(entity.yaw)

        def local(point):
            world = transform @ np.array([point[0], 0, point[1], 1])
            x, y, z = world[:3] - np.asarray(entity.anchor)
            return [c * x - s * z, y, s * x + c * z]

        outline = [[p[0], p[2]] for p in map(local, evidence["footprint"])]

        # Matching IDs alone do not establish matching geometry/frame. Require the
        # original footprints to agree within 1 m before allowing a fitted change.
        def distance(point, ring):
            distances = []
            for a, b in zip(ring, ring[1:] + ring[:1]):
                dx, dz = b[0] - a[0], b[1] - a[1]
                length = dx * dx + dz * dz
                t = (
                    max(
                        0,
                        min(
                            1,
                            ((point[0] - a[0]) * dx + (point[1] - a[1]) * dz) / length,
                        ),
                    )
                    if length
                    else 0
                )
                distances.append(
                    math.hypot(point[0] - a[0] - t * dx, point[1] - a[1] - t * dz)
                )
            return min(distances)

        if (
            max(
                [distance(p, entity.footprint) for p in outline]
                + [distance(p, outline) for p in entity.footprint]
            )
            > 1
        ):
            raise ValueError("MASSING_EVIDENCE_FOOTPRINT_FRAME_MISMATCH: " + entity.id)
        program, fit = massing.fit(evidence)
        values = list(fit["per_view_iou"].values())
        accepted = bool(
            values
            and min(values) >= MASSING_MIN_IOU
            and sum(values) / len(values) >= MASSING_MEAN_IOU
        )
        reports[entity.id] = {
            "applied": accepted,
            "fit": fit,
            "program": program.model_dump(mode="json"),
            "evidence": str(evidence["path"]),
            "manifest_sha256": file_hash(evidence["path"]),
            "image_hashes": {v["id"]: file_hash(v["image"]) for v in evidence["views"]},
            "thresholds": {"mean_iou": MASSING_MEAN_IOU, "min_iou": MASSING_MIN_IOU},
            "note": "Massing fit only; not facade quality, semantic identity or surveyed accuracy.",
        }
        if not accepted:
            entities.append(entity)
            continue
        fitted_plan = massing.registered_plan(
            evidence["footprint"], program.registration
        )
        outline = [[p[0], p[2]] for p in map(local, massing.from_plan(fitted_plan))]
        ground = float((transform @ np.array([0, 0, 0, 1]))[1])
        stored = program.model_copy(update={"registration": massing.Registration()})
        entities.append(
            Entity.model_validate(
                {
                    **entity.model_dump(mode="json"),
                    "footprint": outline,
                    "anchor": (entity.anchor[0], ground, entity.anchor[2]),
                    "eave_m": program.eave_height,
                    "ridge_m": program.eave_height + program.roof.rise,
                    "facts": {
                        **entity.facts,
                        "massing_program": stored.model_dump(mode="json"),
                        "roof": {"form": program.roof.form, "pitch_deg": None},
                        "sources": {
                            **entity.facts.get("sources", {}),
                            "height": "calibrated multi-view silhouette fit; not surveyed",
                            "footprint": "OSM outline registered by calibrated multi-view silhouette fit",
                        },
                    },
                }
            )
        )
    return Region.model_validate(
        {
            **region.model_dump(mode="json"),
            "entities": [e.model_dump(mode="json") for e in entities],
        }
    ), reports
