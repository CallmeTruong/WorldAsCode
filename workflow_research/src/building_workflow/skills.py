"""Pinned upstream integration. Incomplete canonical gates remain incomplete."""
import importlib.util
import subprocess
import sys
from pathlib import Path
from .config import ROOT, SKILL_COMMIT
from .provider import write_json

UPSTREAM = ROOT / "vendor" / "img2threejs"


def verify_pin():
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=UPSTREAM, capture_output=True, text=True, check=True)
    if result.stdout.strip() != SKILL_COMMIT:
        raise RuntimeError("UPSTREAM_VERSION_MISMATCH")
    return result.stdout.strip()


def context(stage):
    files = {"analysis": ["grimoire/intake/image_analysis.md", "grimoire/intake/quality_contract.md"],
             "code": ["grimoire/build/geometry_patterns.md"],
             "review": ["grimoire/review/self_correction.md"]}.get(stage, [])
    # Bounded progressive disclosure; complete files remain locally available.
    return "\n".join(f"SOURCE {f}\n" + (UPSTREAM / f).read_text(encoding="utf-8")[:6000] for f in files)


def intake(reference: Path, run: Path):
    verify_pin()
    import hashlib
    router=(UPSTREAM/"SKILL.md").read_bytes()
    write_json(run/"skill-loading.json",{"router":"SKILL.md","router_sha256":hashlib.sha256(router).hexdigest(),
        "commit":SKILL_COMMIT,"loading":"Router read locally; selected bounded stage guidance disclosed to API prompts.",
        "stage_contexts":{"analysis":["grimoire/intake/image_analysis.md","grimoire/intake/quality_contract.md"],
            "code":["grimoire/build/geometry_patterns.md"],"review":["grimoire/review/self_correction.md"]}})
    for name, args in [
        ("probe", ["forge/stage1_intake/probe_image.py", str(reference)]),
        ("state-init", ["forge/state.py", "init", "--state", str(run / "upstream-state.json"),
                        "--reference", str(reference), "--profile", "generic", "--spec", str(run / "native-object-sculpt-spec.json")]),
        ("next", ["forge/next.py", "--state", str(run / "upstream-state.json")]),
    ]:
        if name == "state-init" and (run / "upstream-state.json").exists():
            continue
        result = subprocess.run([sys.executable, *args], cwd=UPSTREAM, capture_output=True, text=True, encoding="utf-8", timeout=30)
        write_json(run / ("upstream-" + name + ".json"), {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
        if name == "probe" and result.returncode != 0:
            raise RuntimeError("REFERENCE_PROBE_FAILED")
    write_json(run / "upstream-compatibility.json", {
        "commit": SKILL_COMMIT, "profile": "generic", "mode": "research-adapter",
        "native_eight_pass_baseline": "incomplete", "strict_quality": "not_run_building_schema_is_not_native_ObjectSculptSpec",
        "canonical_passes_completed": [], "reused_gates": ["probe_image", "geometry_integrity"],
        "reason": "Free LLM-generated code branch with structured building schema; no upstream pass marked complete. Native staged compatibility baseline remains required future research."})


def geometry_gate(payload):
    if not payload.get("meshes"):
        return {"passed": False, "failures": ["empty scene"]}
    folder = UPSTREAM / "forge" / "stage4_review"
    sys.path.insert(0, str(folder))
    spec = importlib.util.spec_from_file_location("upstream_geometry_integrity", folder / "geometry_integrity.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Upstream selects the weapon thickness gate by an English substring in id,
    # including architectural "blade walls". Route by explicit domain instead.
    # No geometry or topology is altered; every architectural mesh still passes
    # manifold, normal, self-intersection and triangle-budget checks.
    mapping={}
    meshes=[]
    for i,mesh in enumerate(payload["meshes"]):
        copied=dict(mesh)
        if copied.get("role")=="architectural":
            stable=f"architectural-part-{i:04d}"
            mapping[stable]=copied["id"]
            copied["id"]=stable
        meshes.append(copied)
    report=module.measure_geometry_integrity({**payload,"meshes":meshes})
    report["architectural_id_mapping"]=mapping
    report["domain_applicability"]={"weapon_blade_thickness":"not applicable to explicit architectural parts",
        "topology_normals_self_intersection":"required for all meshes"}
    for row in report.get("meshes",[]):
        row["source_part_name"]=mapping.get(row["id"],row["id"])
    return report
