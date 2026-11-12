"""Additive part packs: metadata discovery, pinned code, fixtures and publication.

The catalog contains metadata only. Selected packs expose host functions and API
docs. They cannot replace host methods. Lint is a cooperative code contract,
not a security sandbox. Publication requires host permission and a fresh render.
"""

import json
import math
import re
import shutil
from pathlib import Path

from worldascode.config import RESOURCE_ROOT, paths
from worldascode.kits.code import analyze_source
from worldascode.storage.artifacts import digest, file_hash, run_lock, write_json

SCHEMA = "worldascode-pack-1"
HOST_SERVICES = (
    "_box",
    "_prism",
    "_material",
    "_surface",
    "_add",
    "_world",
    "at",
    "roofY",
)
SLUG = re.compile(r"^[a-z][a-z0-9-]{0,60}$")
PART_NAME = re.compile(r"^[a-z][A-Za-z0-9]{1,31}$")
FILES = ("pack.json", "parts.mjs", "api.md")
FORBIDDEN = re.compile(
    r"\b(?:require|fetch|XMLHttpRequest|WebSocket|eval|Function|localStorage|Worker|setTimeout|setInterval)\s*\(|\b(?:document|window|globalThis|navigator)\s*[.\[]"
)


def builtin_dir():
    return RESOURCE_ROOT / "kits"


def library_dir():
    return paths().data_dir / "kit-packs"


def metadata(folder):
    folder = Path(folder).resolve()
    record = json.loads((folder / "pack.json").read_text(encoding="utf-8"))
    if record.get("schema") != SCHEMA or not SLUG.fullmatch(record.get("id", "")):
        raise ValueError("PACK_INVALID_MANIFEST")
    names = record.get("parts")
    kinds = record.get("kinds")
    if (
        not isinstance(names, list)
        or not names
        or len(names) > 32
        or any(not isinstance(n, str) or not PART_NAME.fullmatch(n) for n in names)
        or len(names) != len(set(names))
        or not isinstance(kinds, list)
        or not kinds
        or any(
            not isinstance(k, str) or not SLUG.fullmatch(k.replace("_", "-"))
            for k in kinds
        )
        or not isinstance(record.get("version"), str)
        or not isinstance(record.get("fixture"), (str, dict))
        or not record["fixture"]
    ):
        raise ValueError("PACK_INVALID_MANIFEST_FIELDS")
    return {**record, "folder": str(folder)}


def lint(source, declared):
    try:
        parsed = analyze_source(source)
    except ValueError as error:
        return [str(error)]
    problems = []
    if set(parsed["pack_parts"]) != set(declared):
        problems.append("PACK_EXPORTS_MUST_MATCH_DECLARED_PARTS")
    if set(parsed["imports"]) - {"three"} or parsed["dynamic_import"]:
        problems.append("PACK_ONLY_THREE_IMPORT_ALLOWED")
    if set(parsed["host_members"]) - set(HOST_SERVICES) - {"site", "THREE"}:
        problems.append("PACK_HOST_ACCESS_NOT_ALLOWED")
    stripped = re.sub(r"//[^\n]*|/\*.*?\*/", "", source, flags=re.S)
    if FORBIDDEN.search(stripped) or len(source) > 60_000:
        problems.append("PACK_FORBIDDEN_CODE_OR_SIZE")
    if any(not PART_NAME.fullmatch(name) for name in declared):
        problems.append("PACK_INVALID_PART_NAME")
    return problems


def load(folder):
    record = metadata(folder)
    folder = Path(record["folder"])
    hashes = {name: file_hash(folder / name) for name in FILES}
    lock = folder / "pack-lock.json"
    if lock.is_file() and json.loads(lock.read_text(encoding="utf-8")) != hashes:
        raise ValueError("PACK_FILE_HASH_MISMATCH")
    source = (folder / "parts.mjs").read_text(encoding="utf-8")
    problems = lint(source, record["parts"])
    if problems:
        raise ValueError("PACK_REJECTED: " + "; ".join(problems))
    host = analyze_source((paths().runtime_dir / "kit.mjs").read_text(encoding="utf-8"))
    if set(record["parts"]) & (
        set(host["public_methods"]) | {"THREE", "finish", "constructor"}
    ):
        raise ValueError("PACK_HOST_PART_COLLISION")
    return {
        **record,
        "module": str(folder / "parts.mjs"),
        "api": (folder / "api.md").read_text(encoding="utf-8"),
        "sha256": digest(hashes),
        "files": hashes,
    }


def discover(extra=(), channel="stable"):
    """Read small manifests, never all source or API docs."""
    roots = [builtin_dir()]
    folders = [
        p.parent
        for root in roots
        if root.is_dir()
        for p in sorted(root.glob("*/pack.json"))
    ]
    if channel not in {"stable", "incubating"}:
        raise ValueError("PACK_CHANNEL_INVALID")
    index = library_dir() / (
        "catalog.json" if channel == "stable" else "incubating.json"
    )
    if index.is_file():
        for pack_id, version in json.loads(index.read_text(encoding="utf-8")).items():
            if not SLUG.fullmatch(pack_id) or not re.fullmatch("[a-f0-9]{64}", version):
                raise ValueError("PACK_INVALID_CATALOG")
            folders.append(library_dir() / "releases" / pack_id / version)
    folders += [Path(folder) for folder in extra]
    result = {}
    for folder in folders:
        pack = metadata(folder)
        if pack["id"] in result:
            raise ValueError("DUPLICATE_PACK_ID: " + pack["id"])
        result[pack["id"]] = pack
    return list(result.values())


def for_kind(kind, extra=()):
    return [p for p in discover(extra) if kind in p["kinds"] or "scene" == kind]


def select(catalog, methods):
    chosen = [load(p["folder"]) for p in catalog if set(methods) & set(p["parts"])]
    names = part_names(chosen)
    if len(names) != len(set(names)):
        raise ValueError("PACK_PART_COLLISION")
    return chosen


def part_names(selected):
    return [name for pack in selected for name in pack["parts"]]


def api_text(selected):
    documents=[]
    for item in selected:
        pack=load(item['folder'])
        options=analyze_source(Path(pack['module']).read_text(encoding='utf-8'))['option_names']
        contract='\n'.join(f'b.{name}(b.at(x,z,yaw),options)' for name in pack['parts'])
        notes=pack['api']
        # Module-facing implementation notes must never override the public
        # binding convention; this exact mismatch was observed in real runs.
        if re.search(r'\bparts\.|\bhost\b|frame[^\n]*\[',notes):
            notes='Implementation-facing notes omitted; use the signatures above.'
        documents.append(f"PACK {pack['id']} PUBLIC API:\n{contract}\nFrame is the object returned by b.at, never an array. There is no b.parts namespace and no host argument in design code. Option names observed in this module: {', '.join(options)}\n{notes}")
    return '\n'.join(documents)


def pin(pack, folder):
    current = load(pack["folder"])
    if pack.get("sha256") and pack["sha256"] != current["sha256"]:
        raise ValueError("PACK_SELECTED_SOURCE_CHANGED")
    pack = current
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    for name in FILES:
        shutil.copy2(Path(pack["folder"]) / name, folder / name)
    write_json(folder / "pack-lock.json", pack["files"])
    return load(folder)


def create(
    folder,
    pack_id,
    kinds,
    parts_source,
    api,
    part_list,
    fixture,
    provenance=None,
    required_checks=(),
):
    problems = lint(parts_source, part_list)
    if problems:
        raise ValueError("PACK_REJECTED: " + "; ".join(problems))
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    (folder / "parts.mjs").write_text(parts_source, encoding="utf-8", newline="\n")
    (folder / "api.md").write_text(api.strip() + "\n", encoding="utf-8", newline="\n")
    write_json(
        folder / "pack.json",
        {
            "schema": SCHEMA,
            "id": pack_id,
            "version": "0.1.0",
            "summary": (provenance or {}).get("summary", ""),
            "kinds": list(kinds),
            "parts": list(part_list),
            "fixture": fixture,
            "provenance": provenance or {},
            "required_checks": list(required_checks),
        },
    )
    return load(folder)


def fixture_script(pack):
    fixture = pack["fixture"]
    if isinstance(fixture, dict):
        if (
            set(fixture) - {"materials", "calls"}
            or not isinstance(fixture.get("materials"), dict)
            or len(fixture["materials"]) > 32
            or not isinstance(fixture.get("calls"), list)
            or not 0 < len(fixture["calls"]) <= 64
        ):
            raise ValueError("PACK_FIXTURE_DECLARATION_INVALID")
        lines = [
            f"b.material({json.dumps(name)},{json.dumps(spec, allow_nan=False)});"
            for name, spec in fixture["materials"].items()
        ]
        for call in fixture["calls"]:
            frame = call.get("frame", [0, 0, 0])
            if (
                call.get("part") not in pack["parts"]
                or not isinstance(frame, list)
                or len(frame) != 3
                or any(
                    type(v) not in (int, float) or not math.isfinite(v) for v in frame
                )
                or not isinstance(call.get("options", {}), dict)
            ):
                raise ValueError("PACK_FIXTURE_CALL_INVALID")
            lines.append(
                f"b[{json.dumps(call['part'])}](b.at(...{json.dumps(frame)}),{json.dumps(call.get('options', {}), allow_nan=False)});"
            )
        fixture = "\n".join(lines)
    code = "export function design(site,b,style) {\n" + fixture + "\n}\n"
    if not set(pack["parts"]) <= set(analyze_source(code)["api_methods"]):
        raise ValueError("PACK_FIXTURE_MUST_CALL_DECLARED_PARTS_ON_B")
    return code


def validate(folder, out):
    from worldascode.adapters.rendering.browser import render_object

    pack = pin(load(folder), Path(out) / "pinned")
    results = []
    for seed in (1, 19):
        metrics, error = render_object(
            Path(out) / f"seed-{seed}",
            fixture_script(pack),
            {"kind": "scene", "seed": seed, "object_id": pack["id"]},
            packs=[pack],
        )
        exercised = (
            set(metrics.get("part_calls", {})) >= set(pack["parts"])
            if metrics
            else False
        )
        physical = all(
            any(
                probe.get("requirement") == check and probe.get("passed")
                for probe in (metrics or {}).get("probes", [])
            )
            for check in pack.get("required_checks", [])
        )
        results.append(
            {
                "seed": seed,
                "passed": bool(
                    metrics and metrics["passed"] and exercised and physical
                ),
                "metrics": metrics,
                "error": error,
            }
        )
    report = {
        "passed": all(r["passed"] for r in results),
        "sha256": pack["sha256"],
        "cases": results,
        "scope": "execution, structure, bounds and seed fixtures; no visual quality acceptance",
    }
    write_json(Path(out) / "validation.json", report)
    return report


def promote(folder, token, subject="workflow", channel="incubating", heldout_runs=()):
    """Host-granted immutable publication with fresh validation, never agent self-grant."""
    from worldascode.kits.registry import PermissionService

    pack = load(folder)
    PermissionService(paths().library_dir).authorize(
        token, subject, "pack-" + pack["id"], "promote-" + channel
    )
    if channel not in {"stable", "incubating"}:
        raise ValueError("PACK_CHANNEL_INVALID")
    if channel == "stable":
        heldout = False
        for run in map(Path, heldout_runs):
            result = json.loads((run / "result.json").read_text(encoding="utf-8"))
            if result.get("execution_status") != "completed" or not result.get(
                "accepted"
            ):
                continue
            attempt = run / f"attempt-{result['best_attempt']}"
            chosen = attempt / "selected-packs" / pack["id"]
            if chosen.is_dir() and load(chosen)["sha256"] == pack["sha256"]:
                calls = json.loads((attempt / "metrics.json").read_text())["part_calls"]
                heldout = bool(set(calls) & set(pack["parts"]))
                if heldout:
                    break
        if not heldout:
            raise ValueError("PACK_STABLE_REQUIRES_ACCEPTED_HELDOUT")
    root = library_dir()
    root.mkdir(parents=True, exist_ok=True)
    with run_lock(root):
        existing = discover() + [
            p
            for p in discover(channel="incubating")
            if not Path(p["folder"]).is_relative_to(builtin_dir())
        ]
        if any(
            p["id"] == pack["id"] and Path(p["folder"]).is_relative_to(builtin_dir())
            for p in existing
        ):
            raise ValueError("PACK_CANNOT_REPLACE_BUILTIN")
        taken = set(part_names([p for p in existing if p["id"] != pack["id"]]))
        if taken & set(pack["parts"]):
            raise ValueError("PACK_PART_COLLISION")
        import uuid

        stage = root / "validation" / uuid.uuid4().hex
        report = validate(folder, stage)
        if (
            not report["passed"]
            or report["sha256"] != pack["sha256"]
            or load(folder)["sha256"] != pack["sha256"]
        ):
            raise ValueError("PACK_PUBLICATION_VALIDATION_FAILED")
        target = root / "releases" / pack["id"] / pack["sha256"]
        if target.exists():
            if load(target)["sha256"] != pack["sha256"]:
                raise ValueError("PACK_RELEASE_HASH_MISMATCH")
        else:
            pin(load(stage / "pinned"), target)
        index = root / ("catalog.json" if channel == "stable" else "incubating.json")
        entries = (
            json.loads(index.read_text(encoding="utf-8")) if index.exists() else {}
        )
        entries[pack["id"]] = pack["sha256"]
        write_json(index, entries)
    return load(target)
