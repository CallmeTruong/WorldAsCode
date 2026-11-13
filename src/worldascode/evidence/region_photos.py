"""Explicitly bound roof/facade photos; uncalibrated images never form camera pairs."""

import json
from pathlib import Path
from typing import Literal

from PIL import Image, ImageStat
from pydantic import Field

from worldascode.contracts.region import Strict
from worldascode.evidence.georeference import Frame
from worldascode.storage.artifacts import digest, file_hash


class Photo(Strict):
    entity_id: str
    surface_id: str
    image: str
    source_kind: Literal["orthophoto", "facade_photo", "street_photo"]
    captured_at: str | None = None
    note: str = Field(default="", max_length=1000)


def load_region_photos(manifest, region):
    manifest = Path(manifest)
    entries = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(entries, list):
        raise ValueError("REGION_PHOTOS_REQUIRE_LIST")
    frame = Frame(
        region.origin.longitude, region.origin.latitude, region.origin.ground_height_m
    ).describe()
    records = []
    for entry in entries:
        photo = Photo.model_validate(entry)
        entity = region.index().get(photo.entity_id)
        if entity is None:
            raise ValueError("PHOTO_UNKNOWN_ENTITY")
        surfaces = (
            {"roof", *(e["id"] for e in entity.site()["edges"])}
            if entity.kind == "building"
            else {"object"}
        )
        if photo.surface_id not in surfaces:
            raise ValueError("PHOTO_UNKNOWN_SURFACE")
        if photo.source_kind == "orthophoto" and photo.surface_id != "roof":
            raise ValueError("ORTHOPHOTO_CANNOT_CONFIRM_FACADE_OR_STREET_OBJECT")
        path = (manifest.parent / photo.image).resolve()
        with Image.open(path) as image:
            width, height = image.size
            contrast = ImageStat.Stat(image.convert("L")).stddev[0]
        sha = file_hash(path)
        records.append(
            {
                "id": "photo-" + digest([photo.model_dump(), sha, frame])[:20],
                "image": str(path),
                "image_sha256": sha,
                "frame": frame,
                "source_kind": photo.source_kind,
                "surface_id": photo.surface_id,
                "captured_at": photo.captured_at,
                "source": "user-supplied photo binding",
                "camera": None,
                "request": {
                    "entity_ids": [entity.id],
                    "purpose": photo.note or "User-bound reference photo",
                    "roi": entity.world_bounds().model_dump(mode="json"),
                    "heading": 0,
                    "pitch": -85 if photo.surface_id == "roof" else -35,
                    "mode": "detail",
                },
                "quality": {
                    "usable": min(width, height) >= 64 and contrast > 5,
                    "identity_binding": "user",
                    "contrast_std": round(contrast, 2),
                },
                "uncertainty": "Entity/surface binding supplied by user; camera uncalibrated. Do not measure geometry or compare pixels with a rendered camera pair. "
                + (photo.note or "Capture date may differ from other sources."),
            }
        )
    return records
