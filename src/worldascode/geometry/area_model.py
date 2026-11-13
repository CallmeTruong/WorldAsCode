"""Area model: every mapped thing in a radius, in one metric frame.

Input is plain OpenStreetMap data (available worldwide), optionally joined with
an area height grid. Output is a registry of buildings, roads, rails, surface
areas and point objects with a stated source for every height. Nothing here
calls a model: the same input always yields the same area.

Frame: X east, Y up, Z south, metres, origin at the requested centre on the
ground datum.
"""

import math
import re
import time
import xml.etree.ElementTree as ElementTree
from pathlib import Path

import worldascode.geometry.massing as massing
from worldascode.evidence import georeference as georef
from worldascode.evidence.georeference import Frame

USER_AGENT = "worldascode-area/0.1"


def validate_extent(latitude, longitude, radius, margin=0):
    if not all(math.isfinite(v) for v in (latitude, longitude, radius)) or not (
        -85 < latitude < 85
        and -180 <= longitude <= 180
        and 20 <= radius <= 1500 + margin
    ):
        raise ValueError(
            "AREA_EXTENT_INVALID: latitude (-85,85), longitude [-180,180], radius [20,1500] metres"
        )


def clip_polyline(points, half):
    """Clip to a common metric square; interpolate exact shared boundary points."""
    pieces, current = [], []
    for a, b in zip(points, points[1:]):
        dx, dz = b[0] - a[0], b[1] - a[1]
        low, high = 0.0, 1.0
        for p, q in (
            (-dx, a[0] + half),
            (dx, half - a[0]),
            (-dz, a[1] + half),
            (dz, half - a[1]),
        ):
            if p == 0:
                if q < 0:
                    low, high = 1, 0
                    break
            elif p < 0:
                low = max(low, q / p)
            else:
                high = min(high, q / p)
        if low > high:
            if len(current) > 1:
                pieces.append(current)
            current = []
            continue
        start, end = (
            [a[0] + dx * low, a[1] + dz * low],
            [a[0] + dx * high, a[1] + dz * high],
        )
        if math.dist(start, end) < 1e-6:
            continue
        if current and math.dist(current[-1], start) > 1e-6:
            pieces.append(current)
            current = []
        if not current:
            current = [start]
        current.append(end)
    if len(current) > 1:
        pieces.append(current)
    return pieces


def clip_polygon(polygon, half):
    ring = [list(p) for p in polygon]
    for axis, sign in ((0, 1), (0, -1), (1, 1), (1, -1)):
        output = []
        for a, b in zip(ring, ring[1:] + ring[:1]):
            ina, inb = sign * a[axis] <= half, sign * b[axis] <= half
            if ina:
                output.append(a)
            if ina != inb:
                t = (sign * half - a[axis]) / (b[axis] - a[axis])
                output.append([a[i] + t * (b[i] - a[i]) for i in range(2)])
        ring = output
        if not ring:
            break
    return clean_ring(ring) if ring else None


LANE_M = 3.25
ROAD_CLASSES = {
    # class: (default lanes, sidewalk width each side, centre marking)
    "motorway": (4, 0.0, True),
    "trunk": (4, 3.5, True),
    "primary": (4, 3.5, True),
    "secondary": (3, 3.5, True),
    "tertiary": (2, 3.0, True),
    "unclassified": (2, 2.0, False),
    "residential": (2, 1.8, False),
    "living_street": (1, 0.0, False),
    "service": (1, 0.0, False),
}
PATH_CLASSES = {
    "footway": 2.5,
    "pedestrian": 6.0,
    "path": 2.0,
    "cycleway": 2.0,
    "steps": 2.5,
}
RAIL_CLASSES = {"rail", "light_rail", "tram", "narrow_gauge", "monorail"}
GREEN = {
    ("leisure", "park"),
    ("leisure", "garden"),
    ("landuse", "grass"),
    ("landuse", "forest"),
    ("landuse", "village_green"),
    ("natural", "wood"),
    ("natural", "grassland"),
    ("natural", "scrub"),
    ("landuse", "meadow"),
    ("leisure", "pitch"),
}
WATER = {
    ("natural", "water"),
    ("waterway", "riverbank"),
    ("landuse", "basin"),
    ("leisure", "swimming_pool"),
}
POINT_KINDS = {
    ("natural", "tree"): "tree",
    ("highway", "street_lamp"): "lamp",
    ("highway", "traffic_signals"): "traffic_light",
    ("highway", "crossing"): "crossing",
    ("highway", "bus_stop"): "bus_stop",
    ("amenity", "bench"): "bench",
    ("amenity", "waste_basket"): "bin",
    ("amenity", "vending_machine"): "vending",
    ("amenity", "post_box"): "post_box",
    ("amenity", "telephone"): "phone",
    ("barrier", "bollard"): "bollard",
    ("emergency", "fire_hydrant"): "hydrant",
}


def fetch_osm(latitude, longitude, radius, out, attempts=4):
    """Download everything mapped in the bounding box; returns the cached path."""
    import httpx

    validate_extent(latitude, longitude, radius, margin=30)
    out = Path(out)
    if out.is_file() and out.stat().st_size > 1000:
        return out
    dlat = radius / 111_320
    dlon = radius / (111_320 * math.cos(math.radians(latitude)))
    south, west, north, east = (
        latitude - dlat,
        longitude - dlon,
        latitude + dlat,
        longitude + dlon,
    )
    overpass = f"[out:xml][timeout:90];nwr({south:.6f},{west:.6f},{north:.6f},{east:.6f});(._;>>;);out meta;"
    sources = [
        (
            "GET",
            "https://api.openstreetmap.org/api/0.6/map",
            {"bbox": f"{west:.6f},{south:.6f},{east:.6f},{north:.6f}"},
        ),
        ("POST", "https://overpass-api.de/api/interpreter", overpass),
        ("POST", "https://overpass.private.coffee/api/interpreter", overpass),
    ]
    errors = []
    for attempt in range(attempts):
        for method, url, payload in sources:
            try:
                if method == "GET":
                    reply = httpx.get(
                        url,
                        params=payload,
                        timeout=120,
                        follow_redirects=True,
                        headers={"User-Agent": USER_AGENT},
                    )
                else:
                    reply = httpx.post(
                        url,
                        data={"data": payload},
                        timeout=150,
                        headers={"User-Agent": USER_AGENT},
                    )
                if reply.status_code == 200 and len(reply.content) > 1000:
                    if ElementTree.fromstring(reply.content).tag != "osm":
                        raise ValueError("MAP_RESPONSE_IS_NOT_OSM")
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_bytes(reply.content)
                    return out
                errors.append(f"{url}: HTTP {reply.status_code}")
            except (httpx.HTTPError, ElementTree.ParseError, ValueError) as exc:
                errors.append(f"{url}: {type(exc).__name__}")
        time.sleep(2 + 3 * attempt)
    raise RuntimeError("MAP_DATA_UNAVAILABLE: " + "; ".join(errors[-6:]))


def number(text):
    match = re.fullmatch(
        r"\s*([+-]?\d+(?:[.,]\d+)?)\s*(m|ft|feet|')?\s*", str(text).lower()
    )
    if not match:
        return None
    value = float(match[1].replace(",", "."))
    return value * (0.3048 if match[2] in ("ft", "feet", "'") else 1)


def clean_ring(points, tolerance=0.25):
    """Drop repeated and near-collinear vertices; ``None`` if nothing usable is left."""
    ring = []
    for p in points:
        if not ring or math.dist(p, ring[-1]) > tolerance:
            ring.append(p)
    if len(ring) > 1 and math.dist(ring[0], ring[-1]) <= tolerance:
        ring.pop()
    changed = True
    while changed and len(ring) > 3:
        changed = False
        for i in range(len(ring)):
            a, b, c = ring[i - 1], ring[i], ring[(i + 1) % len(ring)]
            cross = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
            if abs(cross) < tolerance * max(math.dist(a, c), 1e-6):
                del ring[i]
                changed = True
                break
    return ring if len(ring) >= 3 and abs(georef.area(ring)) > 4.0 else None


def stitch(ways):
    """Join way node lists into closed rings by shared end nodes."""
    rings, pending = [], [list(w) for w in ways if len(w) >= 2]
    while pending:
        ring = pending.pop(0)
        while ring[0] != ring[-1]:
            for i, other in enumerate(pending):
                if other[0] == ring[-1]:
                    ring += other[1:]
                elif other[-1] == ring[-1]:
                    ring += other[-2::-1]
                elif other[-1] == ring[0]:
                    ring = other[:-1] + ring
                elif other[0] == ring[0]:
                    ring = other[:0:-1] + ring
                else:
                    continue
                del pending[i]
                break
            else:
                break
        if ring[0] == ring[-1] and len(ring) >= 4:
            rings.append(ring)
    return rings


def inside(polygon, point):
    x, y = point
    result = False
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        if (a[1] > y) != (b[1] > y) and x < (b[0] - a[0]) * (y - a[1]) / (
            b[1] - a[1]
        ) + a[0]:
            result = not result
    return result


def underground(tags):
    layer = number(tags.get("layer")) or 0
    level = number(str(tags.get("level", "0")).split(";")[0]) or 0
    return (
        layer < 0
        or level < 0
        or tags.get("location") == "underground"
        or tags.get("tunnel") == "yes"
        or tags.get("indoor") in ("yes", "corridor", "room", "area")
    )


def parse(osm_path, latitude, longitude, radius):
    validate_extent(latitude, longitude, radius)
    root = ElementTree.parse(osm_path).getroot()
    if root.tag != "osm":
        raise ValueError("MAP_RESPONSE_IS_NOT_OSM")
    frame = Frame(longitude, latitude)
    nodes, node_tags, ways, relations = {}, {}, {}, []
    for el in root:
        tags = {t.get("k"): t.get("v") for t in el.findall("tag")}
        if el.tag == "node":
            east, _, south = frame.model(float(el.get("lon")), float(el.get("lat")))
            nodes[el.get("id")] = [east, south]
            if tags:
                node_tags[el.get("id")] = tags
        elif el.tag == "way":
            ways[el.get("id")] = ([n.get("ref") for n in el.findall("nd")], tags)
        elif el.tag == "relation":
            members = [
                (m.get("type"), m.get("ref"), m.get("role"))
                for m in el.findall("member")
            ]
            relations.append((el.get("id"), members, tags))

    def points(refs):
        return [nodes[r] for r in refs] if all(r in nodes for r in refs) else []

    def within(pts, margin=0.0):
        return bool(clip_polyline(pts, radius + margin)) or any(
            math.hypot(*p) <= radius + margin for p in pts
        )

    area = {
        "buildings": [],
        "roads": [],
        "paths": [],
        "rails": [],
        "surfaces": [],
        "points": [],
        "skipped": {"underground_ways": 0, "open_rings": 0},
    }
    shapes = []  # (id, ring, tags, holes) for every polygonal feature
    for way_id, (refs, tags) in ways.items():
        if len(refs) >= 4 and refs[0] == refs[-1]:
            shapes.append(("way/" + way_id, points(refs[:-1]), tags, []))
    consumed = set()
    for rel_id, members, tags in relations:
        if tags.get("type") != "multipolygon":
            continue
        outer = [
            ways[ref][0]
            for kind, ref, role in members
            if kind == "way" and role in ("outer", "") and ref in ways
        ]
        rings = stitch(outer)
        if not rings:
            area["skipped"]["open_rings"] += 1
        inners = stitch(
            [
                ways[ref][0]
                for kind, ref, role in members
                if kind == "way" and role == "inner" and ref in ways
            ]
        )
        for index, ring in enumerate(rings):
            outer_points = points(ring[:-1])
            if not outer_points:
                area["skipped"]["open_rings"] += 1
                continue
            holes = [
                p
                for r in inners
                if (p := clean_ring(points(r[:-1]))) and inside(outer_points, p[0])
            ]
            shapes.append((f"relation/{rel_id}/{index}", outer_points, tags, holes))
            if any(
                k in tags
                for k in (
                    "building",
                    "building:part",
                    "landuse",
                    "natural",
                    "leisure",
                    "amenity",
                )
            ):
                consumed.update(
                    "way/" + ref
                    for kind, ref, role in members
                    if kind == "way"
                    and not ways.get(ref, ([], {}))[1].get("building:part")
                )

    outlines, parts = [], []
    for shape_id, ring, tags, holes in shapes:
        if shape_id in consumed:
            continue
        is_part = tags.get("building:part") not in (None, "no")
        is_building = tags.get("building") not in (None, "no")
        if is_part or is_building:
            if underground(tags):
                continue
            ring = clean_ring(ring)
            if not ring:
                continue
            centre = georef.centroid(ring)
            item = {
                "id": shape_id,
                "polygon": [[round(x, 2), round(z, 2)] for x, z in ring],
                "holes": [
                    [[round(x, 2), round(z, 2)] for x, z in hole] for hole in holes
                ],
                "centroid": [round(centre[0], 2), round(centre[1], 2)],
                "area_m2": round(
                    abs(georef.area(ring)) - sum(abs(georef.area(h)) for h in holes), 1
                ),
                "is_part": is_part,
                "name": tags.get("name:en") or tags.get("name"),
                "use": tags.get("building")
                if is_building
                else tags.get("building:part"),
                "height_tag": number(tags.get("height"))
                or number(tags.get("building:height")),
                "levels_tag": number(tags.get("building:levels")),
                "min_height": number(tags.get("min_height")) or 0.0,
                "roof_shape_tag": tags.get("roof:shape"),
                "roof_height_tag": number(tags.get("roof:height")),
                "colour_tag": tags.get("building:colour"),
                "roof_colour_tag": tags.get("roof:colour"),
                "material_tag": tags.get("building:material"),
                "tags": {
                    k: tags[k]
                    for k in (
                        "building",
                        "building:part",
                        "amenity",
                        "shop",
                        "office",
                        "tourism",
                        "historic",
                        "start_date",
                        "building:architecture",
                        "railway",
                        "public_transport",
                    )
                    if k in tags
                },
            }
            (parts if item["is_part"] else outlines).append(item)
            continue
        key = next(
            (
                (k, tags[k])
                for k in ("leisure", "landuse", "natural", "waterway")
                if k in tags
            ),
            None,
        )
        kind = "green" if key in GREEN else "water" if key in WATER else None
        if (
            tags.get("highway") in ("pedestrian", "footway")
            and tags.get("area") == "yes"
            and not underground(tags)
        ):
            kind = "plaza"
        if tags.get("amenity") == "parking" and not underground(tags):
            kind = "paved"
        if kind and (within(ring, 20) or (ring and inside(ring, (0, 0)))):
            ring = clean_ring(ring)
            if ring:
                area["surfaces"].append(
                    {
                        "id": shape_id,
                        "kind": kind,
                        "polygon": [[round(x, 2), round(z, 2)] for x, z in ring],
                        "holes": holes,
                    }
                )

    # Simple 3D Buildings: where parts describe an outline, the parts are the building.
    for part in parts:
        owners = [
            o
            for o in outlines
            if inside(o["polygon"], part["centroid"])
            and not any(inside(h, part["centroid"]) for h in o["holes"])
        ]
        if owners:
            part["parent"] = min(owners, key=lambda o: o["area_m2"])["id"]
    for outline in outlines:
        children = [p for p in parts if p.get("parent") == outline["id"]]
        for child in children:
            child["parent"] = outline["id"]
            for key in ("name", "use", "colour_tag", "material_tag", "roof_colour_tag"):
                child[key] = child[key] or outline[key]
            child["tags"] = {**outline["tags"], **child["tags"]}
        grounded = sum(p["area_m2"] for p in children if p["min_height"] < 1)
        outline["replaced_by_parts"] = (
            bool(children) and grounded >= 0.6 * outline["area_m2"]
        )
    area["buildings"] = [o for o in outlines if not o["replaced_by_parts"]] + parts
    area["buildings"] = [
        b
        for b in area["buildings"]
        if within(b["polygon"])
        or (
            inside(b["polygon"], (0, 0))
            and not any(inside(h, (0, 0)) for h in b["holes"])
        )
    ]
    # Incomplete parts retain their owner outline; never silently drop a tower.
    for item in area["buildings"]:
        item.pop("replaced_by_parts", None)

    for way_id, (refs, tags) in ways.items():
        if refs and refs[0] == refs[-1] and tags.get("area") == "yes":
            continue
        line = points(refs)
        if len(line) < 2 or not within(line, 10):
            continue
        highway, railway = tags.get("highway"), tags.get("railway")
        if not (highway or railway):
            continue
        if underground(tags):
            area["skipped"]["underground_ways"] += 1
            continue
        layer = int(
            number(tags.get("layer"))
            or (1 if tags.get("bridge") in ("yes", "viaduct") else 0)
        )
        line = [[round(x, 2), round(z, 2)] for x, z in line]
        if (
            highway in ROAD_CLASSES
            or (highway or "").replace("_link", "") in ROAD_CLASSES
        ):
            lanes_default, sidewalk, marking = ROAD_CLASSES[
                highway.replace("_link", "")
            ]
            lanes = int(
                number(tags.get("lanes"))
                or (
                    max(1, lanes_default // 2)
                    if tags.get("oneway") == "yes"
                    else lanes_default
                )
            )
            width = number(tags.get("width")) or lanes * LANE_M + (
                0.6 if lanes > 1 else 0.8
            )
            if tags.get("sidewalk") in ("no", "none", "separate"):
                sidewalk = 0.0
            area["roads"].append(
                {
                    "id": "way/" + way_id,
                    "class": highway,
                    "name": tags.get("name:en") or tags.get("name"),
                    "lanes": lanes,
                    "width_m": round(width, 2),
                    "sidewalk_m": sidewalk,
                    "oneway": tags.get("oneway") == "yes",
                    "marking": marking and lanes >= 2,
                    "layer": layer,
                    "points": line,
                    "node_ids": refs,
                }
            )
        elif highway in PATH_CLASSES and layer == 0:
            area["paths"].append(
                {
                    "id": "way/" + way_id,
                    "class": highway,
                    "width_m": number(tags.get("width")) or PATH_CLASSES[highway],
                    "points": line,
                }
            )
        elif railway in RAIL_CLASSES:
            area["rails"].append(
                {
                    "id": "way/" + way_id,
                    "class": railway,
                    "layer": layer,
                    "gauge_m": (number(tags.get("gauge")) or 1067) / 1000,
                    "points": line,
                }
            )

    road_nodes = {}
    for road in area["roads"]:
        for index, node_id in enumerate(road.pop("node_ids")):
            road_nodes.setdefault(node_id, (road, index))
    for node_id, tags in node_tags.items():
        if underground(tags) or math.hypot(*nodes[node_id]) > radius:
            continue
        kind = next(
            (POINT_KINDS[(k, v)] for k, v in tags.items() if (k, v) in POINT_KINDS),
            None,
        )
        if not kind:
            continue
        item = {
            "id": "node/" + node_id,
            "kind": kind,
            "x": round(nodes[node_id][0], 2),
            "z": round(nodes[node_id][1], 2),
        }
        if node_id in road_nodes:
            road, index = road_nodes[node_id]
            a = road["points"][max(index - 1, 0)]
            b = road["points"][min(index + 1, len(road["points"]) - 1)]
            item["heading_rad"] = round(math.atan2(-(b[1] - a[1]), b[0] - a[0]), 4)
            item["road_width_m"] = road["width_m"]
            item["road_id"] = road["id"]
        elif kind in ("crossing", "traffic_light"):
            continue  # a crossing that is not on a mapped surface road has nowhere to go
        area["points"].append(item)
    return {
        "schema": "worldascode-area-1",
        "origin": {"latitude": latitude, "longitude": longitude},
        "radius_m": radius,
        "frame": "X east, Y up, Z south; metres; origin at the requested centre on the ground datum",
        "source": {"map": "OpenStreetMap contributors (ODbL)", "file": str(osm_path)},
        **area,
    }


def edges_of(polygon):
    """Edge table for the building kit; outlines too intricate to inset simply have no wing ends."""
    plan = massing.to_plan(polygon)
    try:
        ends = massing.end_edges(plan)
    except (ValueError, ZeroDivisionError):
        ends = [False] * len(plan)
    compass = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
    table = []
    for i, (a, b) in enumerate(zip(plan, plan[1:] + plan[:1])):
        dx, dn = b[0] - a[0], b[1] - a[1]
        bearing = math.degrees(math.atan2(dn, -dx)) % 360
        table.append(
            {
                "id": f"e{i}",
                "length_m": round(math.hypot(dx, dn), 1),
                "facing": compass[int((bearing + 22.5) // 45) % 8],
                "end": bool(ends[i]),
            }
        )
    return table
