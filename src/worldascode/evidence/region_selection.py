"""Select useful, diverse source images instead of the last N captures."""

import math


def usable(record):
    quality = record.get("quality", {})
    return (
        quality.get("usable") is True
        and quality.get("tiles_complete") is not False
        and not quality.get("likely_occluded", False)
    )


def spatially_covered(record, entity_id):
    return bool(
        usable(record)
        and (
            record.get("quality", {})
            .get("entity_visibility", {})
            .get(entity_id, {})
            .get("matched", 0)
            > 0
        )
    )


def identity_supported(record, entity_id):
    return spatially_covered(record, entity_id) or bool(
        usable(record)
        and record.get("quality", {}).get("identity_binding") == "user"
        and entity_id in record["request"]["entity_ids"]
    )


def select_evidence(records, entity_ids, limit=6):
    targets = set(entity_ids)
    candidates = []
    for record in records:
        if not usable(record):
            continue
        ids = targets & set(record["request"]["entity_ids"])
        visibility = record.get("quality", {}).get("entity_visibility", {})
        ids = {
            i for i in ids if i not in visibility or visibility[i].get("matched", 0) > 0
        }
        if ids:
            candidates.append((record, ids))
    selected, covered, poses, surfaces = [], set(), set(), set()
    while candidates and len(selected) < limit:

        def score(item):
            record, ids = item
            request = record["request"]
            pose = (
                round(request.get("heading", 0) / 45) % 8,
                round(request.get("pitch", -35) / 25),
            )
            screens = record.get("projected_entities", {})
            pixels = sum(
                math.prod(max(0, b - a) for a, b in zip(rect["min"], rect["max"]))
                for i in ids
                if (rect := screens.get(i, {}).get("screen"))
            )
            return (
                len(ids - covered),
                bool(
                    record.get("surface_id")
                    and (record["request"]["entity_ids"][0], record["surface_id"])
                    not in surfaces
                ),
                pose not in poses,
                len(ids),
                pixels,
                record["id"],
            )

        item = max(candidates, key=score)
        record, ids = item
        candidates.remove(item)
        selected.append(record)
        covered.update(ids)
        if record.get("surface_id"):
            surfaces.add((record["request"]["entity_ids"][0], record["surface_id"]))
        request = record["request"]
        poses.add(
            (
                round(request.get("heading", 0) / 45) % 8,
                round(request.get("pitch", -35) / 25),
            )
        )
    return selected


def evidence_ledger(region, records, selected):
    """Depth coverage is only a spatial check; surface semantics remain unknown."""
    return {
        "selected_ids": [e["id"] for e in selected],
        "excluded_ids": [e["id"] for e in records if not usable(e)],
        "entities": {
            e.id: {
                "spatial_evidence_ids": [
                    r["id"]
                    for r in records
                    if usable(r)
                    and r.get("quality", {})
                    .get("entity_visibility", {})
                    .get(e.id, {})
                    .get("matched", 0)
                    > 0
                ],
                "surfaces": {
                    surface: {
                        "status": "user_reference"
                        if any(
                            usable(r)
                            and e.id in r["request"]["entity_ids"]
                            and r.get("surface_id") == surface
                            for r in records
                        )
                        else "unverified",
                        "preferred_sources": sources,
                        "reference_ids": [
                            r["id"]
                            for r in records
                            if usable(r)
                            and e.id in r["request"]["entity_ids"]
                            and r.get("surface_id") == surface
                        ],
                    }
                    for surface, sources in (
                        [("roof", ["orthophoto", "high_oblique"])]
                        + [
                            (edge["id"], ["facade_photo", "street_photo"])
                            for edge in e.site()["edges"]
                        ]
                        if e.kind == "building"
                        else [("object", ["street_photo", "close_photo"])]
                    )
                },
            }
            for e in region.entities
        },
        "note": "Surface visibility is not proven by a depth hit. More renders of one mesh do not supply independent source detail.",
    }
