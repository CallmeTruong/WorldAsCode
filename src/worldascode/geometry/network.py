"""Shared stationing and tile ownership; geometry fragments never own topology."""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class NetworkEdge:
    id: str
    points: tuple[tuple[float, float, float], ...]
    width: float
    kind: str = "road"
    gauge: float | None = None

    def __post_init__(self):
        if (
            not math.isfinite(self.width)
            or self.width <= 0
            or len(self.points) < 2
            or any(not math.isfinite(v) for p in self.points for v in p)
        ):
            raise ValueError("Invalid edge geometry")
        if any(math.dist(a, b) < 1e-8 for a, b in zip(self.points, self.points[1:])):
            raise ValueError("Zero-length segment")
        if self.kind == "rail" and (
            self.gauge is None or not math.isfinite(self.gauge) or self.gauge <= 0
        ):
            raise ValueError("Rail gauge required")

    def sample(self, station):
        if not math.isfinite(station) or station < 0:
            raise ValueError("Invalid station")
        total = 0
        for a, b in zip(self.points, self.points[1:]):
            length = math.dist(a, b)
            if station <= total + length:
                t = max(0, (station - total) / length)
                return {
                    "position": [a[i] + (b[i] - a[i]) * t for i in range(3)],
                    "tangent": [(b[i] - a[i]) / length for i in range(3)],
                    "phase": station,
                    "edge_id": self.id,
                    "width": self.width,
                    "gauge": self.gauge,
                }
            total += length
        raise ValueError("Station beyond edge")


def compatible_ports(a, b, tolerance=1e-5):
    return (
        a["edge_id"] == b["edge_id"]
        and math.dist(a["position"], b["position"]) <= tolerance
        and math.dist(a["tangent"], b["tangent"]) <= tolerance
        and abs(a["phase"] - b["phase"]) <= tolerance
        and a["width"] == b["width"]
        and a.get("gauge") == b.get("gauge")
    )


def tile_owner(anchor, tile_size=100):
    if tile_size <= 0:
        raise ValueError("Positive tile size required")
    return (math.floor(anchor[0] / tile_size), math.floor(anchor[2] / tile_size))


def tile_fragments(edge, tile_size=100):
    """Split centreline at tile planes; preserve global station and shared boundary ports."""
    if not math.isfinite(tile_size) or tile_size <= 0:
        raise ValueError("Positive finite tile size required")
    pieces = []
    station = 0.0
    for a, b in zip(edge.points, edge.points[1:]):
        length = math.dist(a, b)
        cuts = {0.0, 1.0}
        for axis in (0, 2):
            if abs(b[axis] - a[axis]) < 1e-12:
                continue
            lo, hi = sorted((a[axis], b[axis]))
            for boundary in range(
                math.floor(lo / tile_size) + 1, math.ceil(hi / tile_size)
            ):
                t = (boundary * tile_size - a[axis]) / (b[axis] - a[axis])
                if 1e-10 < t < 1 - 1e-10:
                    cuts.add(t)
        ordered = sorted(cuts)
        for t0, t1 in zip(ordered, ordered[1:]):
            s0 = station + t0 * length
            s1 = station + t1 * length
            p0 = edge.sample(s0)
            p1 = edge.sample(s1)
            midpoint = [(p0["position"][i] + p1["position"][i]) / 2 for i in range(3)]
            owner = tile_owner(midpoint, tile_size)
            radius = edge.width / 2
            x0, x1 = sorted([p0["position"][0], p1["position"][0]])
            z0, z1 = sorted([p0["position"][2], p1["position"][2]])
            references = [
                (x, z)
                for x in range(
                    math.floor((x0 - radius) / tile_size),
                    math.floor((x1 + radius) / tile_size) + 1,
                )
                for z in range(
                    math.floor((z0 - radius) / tile_size),
                    math.floor((z1 + radius) / tile_size) + 1,
                )
                if (x, z) != owner
            ]
            pieces.append(
                {
                    "edge_id": edge.id,
                    "owner": owner,
                    "references": references,
                    "start": p0,
                    "end": p1,
                    "uv_station": [s0, s1],
                    "kind": edge.kind,
                }
            )
        station += length
    return pieces
