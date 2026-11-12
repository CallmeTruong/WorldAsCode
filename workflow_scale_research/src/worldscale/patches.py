"""Small, hash-guarded edits; model nodes cannot overwrite gates or forge review history."""

import copy

from .artifacts import digest
from .workflow_constants import PROTECTED


def json_edits(spec, edits):
    result = copy.deepcopy(spec)
    for edit in edits:
        if (
            edit["path"] == "/preSpecAssessment/assumptions"
            and "assumptions" not in result.get("preSpecAssessment", {})
            and "assumptions" in result
        ):
            edit = {**edit, "path": "/assumptions"}
        if edit.get("op") not in ("add", "replace"):
            raise ValueError("UNSUPPORTED_PATCH_OPERATION")
        parts = [
            p.replace("~1", "/").replace("~0", "~") for p in edit["path"].split("/")[1:]
        ]
        if not parts or parts[0] in PROTECTED:
            raise ValueError("PROTECTED_SPEC_PATH")
        if "referencePbr" in parts:
            raise ValueError("MACHINE_PBR_EVIDENCE_IS_IMMUTABLE")
        if parts[0] not in result:
            raise ValueError("UNKNOWN_SPEC_SECTION")
        obj = result
        for p in parts[:-1]:
            if isinstance(obj, list):
                if p.isdigit():
                    obj = obj[int(p)]
                else:
                    match = next(
                        (
                            item
                            for item in obj
                            if isinstance(item, dict) and item.get("id") == p
                        ),
                        None,
                    )
                    if match is None:
                        raise ValueError("PATCH_ENTITY_ID_NOT_FOUND: " + p)
                    obj = match
            else:
                obj = obj[p]
        key = parts[-1]
        if isinstance(obj, list):
            if key == "-" and edit["op"] == "add":
                obj.append(edit["value"])
            else:
                index = int(key)
                if index < 0 or index >= len(obj):
                    raise ValueError("PATCH_INDEX_OUT_OF_RANGE")
                obj[index] = edit["value"]
        else:
            if edit["op"] == "replace" and key not in obj:
                if key not in {
                    "sourceImage",
                    "textureProjection",
                    "colorMaterialRecipe",
                    "transform",
                    "geometryDescriptor",
                    "attachment",
                    "dimensions",
                    "topologyClass",
                    "placement",
                    "instanceScale",
                    "parent",
                    "primitive",
                    "material",
                    "level",
                    "confidence",
                    "count",
                    "holes",
                    "points",
                    "depth",
                }:
                    raise ValueError("PATCH_TARGET_MISSING")
                # Native optional fields are set/upsert operations at the adapter boundary.
                # Parent paths must still exist; protected paths and evidence stay immutable.
            obj[key] = edit["value"]
    # A replacement of the whole materials array must not erase real extraction evidence.
    original = {
        m["id"]: m.get("referencePbr")
        for m in spec.get("materials", [])
        if m.get("referencePbr")
    }
    updated = {m["id"]: m.get("referencePbr") for m in result.get("materials", [])}
    if any(updated.get(k) != v for k, v in original.items()):
        raise ValueError("MACHINE_PBR_EVIDENCE_IS_IMMUTABLE")
    return result


def text_edits(source, edits, expected_hash):
    if digest(source) != expected_hash:
        raise ValueError("STALE_CODE_PATCH")
    result = source
    for edit in edits:
        find = edit["find"]
        if not find or result.count(find) != 1:
            raise ValueError("CODE_PATCH_ANCHOR_NOT_UNIQUE")
        result = result.replace(find, edit["replace"], 1)
    return result
