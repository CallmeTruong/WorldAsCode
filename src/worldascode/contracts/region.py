"""Shared metric addressing for source tools, regional critics and local authors."""

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Bounds(Strict):
    min: tuple[float, float, float]
    max: tuple[float, float, float]

    @model_validator(mode="after")
    def ordered(self):
        if any(a >= b for a, b in zip(self.min, self.max)):
            raise ValueError("ROI_REQUIRES_POSITIVE_EXTENT")
        return self

    def intersects(self, other, tolerance=0):
        return all(
            a <= d + tolerance and c <= b + tolerance
            for a, b, c, d in zip(self.min, self.max, other.min, other.max)
        )


class Origin(Strict):
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(gt=-89, lt=89)
    ground_height_m: float = 0


class Entity(Strict):
    id: str = Field(min_length=1, max_length=120)
    kind: str = Field(min_length=1, max_length=60)
    anchor: tuple[float, float, float]
    yaw: float = 0
    description: str = ""
    footprint: list[tuple[float, float]] = Field(default_factory=list)
    eave_m: float = Field(default=1, gt=0)
    ridge_m: float = Field(default=1, gt=0)
    storeys: int = Field(default=1, ge=1, le=200)
    bounds: Bounds | None = None
    facts: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def geometry(self):
        if "::" in self.id or any(ord(c) < 32 for c in self.id):
            raise ValueError("ENTITY_ID_RESERVED_SEPARATOR")
        if self.kind == "building" and len(self.footprint) < 3:
            raise ValueError("BUILDING_REQUIRES_MEASURED_FOOTPRINT")
        if self.kind != "building" and self.bounds is None:
            raise ValueError("ENTITY_LOCAL_BOUNDS_REQUIRED")
        return self

    def site(self):
        # Facts supplement observations, but never replace protected identity/geometry.
        from worldascode.evidence.site_context import edges
        from worldascode.geometry.massing import to_plan

        defaults = {
            "edges": edges(to_plan(self.footprint)) if self.footprint else [],
            "roof": {
                "form": "flat" if self.ridge_m <= self.eave_m + 0.3 else "hip",
                "pitch_deg": None,
            },
            "features": {},
            "tags": {},
        }
        if self.bounds:
            defaults["bounds"] = self.bounds.model_dump(mode="json")
            defaults["envelope"] = {
                key: self.bounds.max[i] - self.bounds.min[i]
                for key, i in [("length_m", 0), ("height_m", 1), ("width_m", 2)]
            }
        return {
            **defaults,
            **self.facts,
            "object_id": self.id,
            "kind": self.kind,
            "footprint": self.footprint,
            "eave_m": self.eave_m,
            "ridge_m": self.ridge_m,
            "top_m": max(self.ridge_m, self.eave_m),
            "storeys": self.storeys,
            "description": self.description,
        }

    def world_bounds(self):
        local = self.bounds or Bounds(
            min=(
                min(p[0] for p in self.footprint),
                0,
                min(p[1] for p in self.footprint),
            ),
            max=(
                max(p[0] for p in self.footprint),
                max(self.eave_m, self.ridge_m),
                max(p[1] for p in self.footprint),
            ),
        )
        c, s = math.cos(self.yaw), math.sin(self.yaw)
        points = [
            (
                self.anchor[0] + c * x + s * z,
                self.anchor[1] + y,
                self.anchor[2] - s * x + c * z,
            )
            for x in [local.min[0], local.max[0]]
            for y in [local.min[1], local.max[1]]
            for z in [local.min[2], local.max[2]]
        ]
        return Bounds(
            min=tuple(min(p[i] for p in points) for i in range(3)),
            max=tuple(max(p[i] for p in points) for i in range(3)),
        )

    def owns(self, point, tolerance=1):
        """Does a sampled source surface fall in this entity's prior volume?"""
        x, y, z = (point[i] - self.anchor[i] for i in range(3))
        c, s = math.cos(self.yaw), math.sin(self.yaw)
        x, z = c * x - s * z, s * x + c * z
        if self.kind != "building":
            return all(
                a - tolerance <= v <= b + tolerance
                for a, v, b in zip(self.bounds.min, (x, y, z), self.bounds.max)
            )
        if not -tolerance <= y <= max(self.eave_m, self.ridge_m) * 1.35 + tolerance:
            return False
        inside = False
        for a, b in zip(self.footprint, self.footprint[1:] + self.footprint[:1]):
            dx, dz = b[0] - a[0], b[1] - a[1]
            if dx * dx + dz * dz:
                t = max(
                    0, min(1, ((x - a[0]) * dx + (z - a[1]) * dz) / (dx * dx + dz * dz))
                )
                if math.hypot(x - a[0] - t * dx, z - a[1] - t * dz) <= tolerance:
                    return True
            if (a[1] > z) != (b[1] > z) and x < (b[0] - a[0]) * (z - a[1]) / (
                b[1] - a[1]
            ) + a[0]:
                inside = not inside
        return inside


class Region(Strict):
    schema_version: Literal["worldascode-region-1"] = "worldascode-region-1"
    id: str = Field(min_length=1, max_length=120)
    origin: Origin
    seed: int = 1
    entities: list[Entity] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def unique(self):
        if len({e.id for e in self.entities}) != len(self.entities):
            raise ValueError("DUPLICATE_ENTITY_ID")
        return self

    def index(self):
        return {e.id: e for e in self.entities}


class EvidenceRequest(Strict):
    entity_ids: list[str] = Field(min_length=1, max_length=64)
    purpose: str = Field(min_length=3, max_length=600)
    roi: Bounds
    component_id: str | None = None
    revision: str | None = None
    heading: float = Field(default=35, ge=-360, le=360)
    pitch: float = Field(default=-35, ge=-89.8, le=-5)
    range_m: float | None = Field(default=None, ge=8, le=3000)
    mode: Literal["context", "detail"] = "context"


class Defect(Strict):
    id: str = Field(min_length=1, max_length=120)
    entity_ids: list[str] = Field(min_length=1, max_length=16)
    component_id: str | None = None
    roi: Bounds
    category: Literal[
        "evidence", "geometry", "material", "style", "detail", "capability", "code"
    ]
    description: str = Field(min_length=3, max_length=1500)
    correction: str = Field(min_length=3, max_length=2000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=16)
    confidence: float = Field(ge=0, le=1)
    view_request: EvidenceRequest | None = None


def _address(region, item, components):
    index = region.index()
    if len(set(item.entity_ids)) != len(item.entity_ids) or any(
        i not in index for i in item.entity_ids
    ):
        raise ValueError("UNKNOWN_OR_DUPLICATE_ENTITY_ID")
    if (
        item.component_id
        and "::" not in item.component_id
        and len(item.entity_ids) == 1
    ):
        canonical = item.entity_ids[0] + "::" + item.component_id
        if canonical in components:
            item = item.model_copy(update={"component_id": canonical})
    component = components.get(item.component_id) if item.component_id else None
    if not all(
        item.roi.intersects(index[i].world_bounds(), tolerance=1)
        or bool(
            component
            and component.get("entity_id") == i
            and component.get("bounds")
            and item.roi.intersects(
                Bounds.model_validate(component["bounds"]), tolerance=1
            )
        )
        for i in item.entity_ids
    ):
        raise ValueError("ROI_DOES_NOT_OVERLAP_ADDRESSED_ENTITY")
    if item.component_id:
        component = components.get(item.component_id)
        if not component or component["entity_id"] not in item.entity_ids:
            raise ValueError(
                "UNKNOWN_OR_WRONG_OWNER_COMPONENT: "
                + str(item.component_id)
                + "; use a full entity_id::local_component_id from the registry. For multiple entities, use separate defects or omit component_id rather than guessing its owner."
            )
        if component.get("bounds") and not item.roi.intersects(
            Bounds.model_validate(component["bounds"]), tolerance=1
        ):
            raise ValueError("ROI_DOES_NOT_OVERLAP_COMPONENT")
    return item


def validate_request(region, request, components=None):
    return _address(region, EvidenceRequest.model_validate(request), components or {})


def validate_feedback(region, review, revision, components, evidence_ids):
    if review.get("revision") != revision:
        raise ValueError("STALE_REVIEW_REVISION")
    defects = [
        _address(region, Defect.model_validate(d), components)
        for d in review.get("defects", [])
    ]
    if len(defects) > 32 or len({d.id for d in defects}) != len(defects):
        raise ValueError("INVALID_DEFECT_COUNT_OR_DUPLICATE_ID")
    for defect in defects:
        if not set(defect.evidence_ids) <= set(evidence_ids):
            raise ValueError("UNKNOWN_EVIDENCE_ID")
        if defect.view_request:
            request = defect.view_request
            if defect.category != "evidence" or not set(request.entity_ids) <= set(
                defect.entity_ids
            ):
                raise ValueError("CRITIC_CAPTURE_OUTSIDE_DEFECT_SCOPE")
            _address(region, request, components)
            if request.component_id and request.revision != revision:
                raise ValueError("STALE_COMPONENT_EVIDENCE_REQUEST")
    return defects
