"""Versioned semantic asset recipes, placements and runtime state are separate."""

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from worldascode.config import ROOT
from worldascode.storage.artifacts import digest, file_hash


def seed_channel(world_seed, object_id, version, channel):
    payload = json.dumps(
        [world_seed, object_id, version, channel],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    value = 2166136261
    for byte in payload:
        value = ((value ^ byte) * 16777619) & 0xFFFFFFFF
    return value


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


def _hex(v):
    if (
        len(v) != 7
        or v[0] != "#"
        or any(c not in "0123456789abcdefABCDEF" for c in v[1:])
    ):
        raise ValueError("RGB hex colour required")
    return v


class FacadePattern(StrictModel):
    """Procedural bay/storey tile; an appearance choice, never geometry."""

    kind: Literal["facade"]
    window_width: float = Field(gt=0, lt=1)
    window_height: float = Field(gt=0, lt=1)
    glass: str
    trim: str

    _colours = field_validator("glass", "trim")(_hex)


class Ring(StrictModel):
    y: float
    points: list[tuple[float, float]] = Field(min_length=3)


class FacadeGrid(StrictModel):
    bay_m: float = Field(gt=0)
    storey_m: float = Field(gt=0)


class RoofPlane(StrictModel):
    """y = a*u + b*v + c over rectangles (u0, v0, u1, v1) in the component's plan frame."""

    a: float
    b: float
    c: float
    material: str
    rects: list[tuple[float, float, float, float]] = Field(min_length=1)


class Material(StrictModel):
    id: str
    color: str = "#8b8b85"
    roughness: float = Field(default=0.75, ge=0, le=1)
    metalness: float = Field(default=0, ge=0, le=1)
    emission: str = "#000000"
    emissive_at_night: bool = False
    weather_response: bool = True
    pattern: FacadePattern | None = None

    @field_validator("color", "emission")
    @classmethod
    def hex_color(cls, v):
        if (
            len(v) != 7
            or v[0] != "#"
            or any(c not in "0123456789abcdefABCDEF" for c in v[1:])
        ):
            raise ValueError("RGB hex colour required")
        return v


class Component(StrictModel):
    id: str
    kind: Literal[
        "box",
        "hollow_shaft",
        "gable_roof",
        "window_frame",
        "tree",
        "lamp",
        "rail_track",
        "road_strip",
        "vehicle",
        "animal",
        "loft",
        "roof_planes",
    ]
    rings: list[Ring] | None = None
    facade: FacadeGrid | None = None
    planes: list[RoofPlane] | None = None
    frame_angle_rad: float = 0
    base_y: float = 0
    side_material: str | None = None
    topology_class: Literal[
        "assembled-solid",
        "conforming-shell",
        "fiber-strand",
        "surface-relief",
        "continuous-sculpt",
        "material-only",
    ] = "assembled-solid"
    size: tuple[float, float, float]
    position: tuple[float, float, float] = (0, 0, 0)
    rotation_y: float = 0
    material: str
    wall_thickness: float | None = None
    semantic_requirements: list[
        Literal["air_path", "opening", "attached", "track_gauge"]
    ] = []
    parent: str | None = None
    allow_shape_variation: bool = False
    evidence_refs: list[str] = []
    confidence: Literal["observed", "inferred"] = "inferred"

    @model_validator(mode="after")
    def geometry(self):
        if min(self.size) <= 0:
            raise ValueError("Positive dimensions required")
        if (self.kind == "loft") != (self.rings is not None):
            raise ValueError("Rings belong to loft components, and a loft needs them")
        if self.rings is not None:
            if len(self.rings) < 2 or len({len(r.points) for r in self.rings}) != 1:
                raise ValueError("A loft needs two or more rings of equal vertex count")
            if any(b.y < a.y for a, b in zip(self.rings, self.rings[1:])):
                raise ValueError("Loft rings must not descend")
        if (self.kind == "roof_planes") != (self.planes is not None):
            raise ValueError("Planes belong to roof_planes components, which need them")
        if self.kind == "roof_planes":
            if not self.planes or self.side_material is None:
                raise ValueError("Measured roof needs planes and a side material")
            if any(r[2] <= r[0] or r[3] <= r[1] for p in self.planes for r in p.rects):
                raise ValueError("Roof rectangles need positive extent")
        if self.facade is not None and self.kind != "loft":
            raise ValueError("Facade grid applies to loft walls only")
        if "air_path" in self.semantic_requirements and self.kind != "hollow_shaft":
            raise ValueError("Solid primitive cannot satisfy air_path")
        if "opening" in self.semantic_requirements and self.kind not in (
            "hollow_shaft",
            "window_frame",
        ):
            raise ValueError("Primitive does not implement opening")
        if self.kind in ("hollow_shaft", "window_frame"):
            if (
                self.wall_thickness is None
                or not 0
                < self.wall_thickness
                < min(
                    self.size[0],
                    self.size[2] if self.kind == "hollow_shaft" else self.size[1],
                )
                / 2
            ):
                raise ValueError("Wall/frame thickness must leave a nonzero opening")
        return self


class Blueprint(StrictModel):
    id: str
    version: str = "1.0.0"
    tier: Literal["kit", "family", "landmark"] = "family"
    origin: Literal["semantic", "factory"] = "semantic"
    components: list[Component]
    materials: list[Material]

    @model_validator(mode="after")
    def references(self):
        ids = [c.id for c in self.components]
        materials = [m.id for m in self.materials]
        if len(ids) != len(set(ids)) or len(materials) != len(set(materials)):
            raise ValueError("Duplicate part/material IDs")
        parents = {c.id: c.parent for c in self.components}
        for c in self.components:
            used = {c.material, *([c.side_material] if c.side_material else [])}
            used |= {p.material for p in c.planes or []}
            if not used <= set(materials):
                raise ValueError("Unknown material slot")
            chain = set()
            current = c.id
            while current is not None:
                if current not in parents or current in chain:
                    raise ValueError("Unknown/cyclic parent")
                chain.add(current)
                current = parents[current]
        return self


class Instance(StrictModel):
    id: str
    blueprint: str
    anchor: tuple[float, float, float]
    seed: int = 0
    evidence_locked_anchor: bool = True
    rotation_y: float = 0
    scale: float = Field(default=1, gt=0)


class GeoOrigin(StrictModel):
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)
    altitude: float = 0


class RuntimeState(StrictModel):
    hour: float = Field(default=13, ge=0, lt=24)
    wetness: float = Field(default=0, ge=0, le=1)
    wind: float = Field(default=0, ge=0, le=2)


class GeometryProbe(StrictModel):
    component_id: str
    requirement: Literal["air_path", "opening"]
    axis: tuple[float, float, float]
    centre: tuple[float, float, float] = (0, 0, 0)
    length: float = Field(gt=0)
    wall_probe: tuple[float, float, float]
    confidence: Literal["observed", "inferred"]

    @model_validator(mode="after")
    def direction(self):
        if sum(v * v for v in self.axis) < 1e-10:
            raise ValueError("Probe direction cannot be zero")
        return self


class World(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    seed: int = 17
    coordinate_system: Literal["local-ENU-metres"] = "local-ENU-metres"
    origin: GeoOrigin | None = None
    blueprints: list[Blueprint]
    instances: list[Instance]

    @model_validator(mode="after")
    def refs(self):
        ids = [b.id for b in self.blueprints]
        if len(set(ids)) != len(ids) or len({i.id for i in self.instances}) != len(
            self.instances
        ):
            raise ValueError("Duplicate IDs")
        if any(i.blueprint not in ids for i in self.instances):
            raise ValueError("Unknown blueprint")
        return self


def geometry_key(blueprint, seed=0):
    return digest(
        {
            "compiler_sha256": file_hash(ROOT / "runtime/semantic.mjs"),
            "version": blueprint.version,
            "components": [
                {
                    k: v
                    for k, v in c.model_dump().items()
                    if k not in ("material", "evidence_refs", "confidence")
                }
                for c in blueprint.components
            ],
            "shape_seed": seed
            if any(c.allow_shape_variation for c in blueprint.components)
            else None,
        }
    )


def appearance_key(blueprint):
    return digest([m.model_dump() for m in blueprint.materials])
