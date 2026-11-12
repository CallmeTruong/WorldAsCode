"""Native skill orchestration: observation precedes admission; reviewers are model nodes."""

import copy
import json
import shutil
import threading
import time
from pathlib import Path

from PIL import Image, ImageDraw

from worldascode.adapters.llm.transport import Provider
from worldascode.adapters.rendering.browser import bundle, capture, comparison
from worldascode.contracts.world import NativeSemanticCheck
from worldascode.evidence.georeference import load_evidence
from worldascode.execution.jobs import JobQueue
from worldascode.experimental.native.bridge import NativeBlocked, NativeBridge
from worldascode.experimental.native.compiler_contract import (
    canonicalize_aliases,
    pass_coverage_spec,
)
from worldascode.experimental.native.compiler_contract import issues as compiler_issues
from worldascode.geometry.registration import bind_wing_poses
from worldascode.kits.patches import PROTECTED_SPEC_FIELDS, json_edits, text_edits
from worldascode.quality.evidence import metric_footprint_report
from worldascode.storage.artifacts import digest, file_hash, run_lock, write_json

PASSES = [
    "blockout",
    "structural-pass",
    "form-refinement",
    "material-pass",
    "surface-pass",
    "lighting-pass",
    "interaction-pass",
    "optimization-pass",
]


def read(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def dump(v):
    return json.dumps(v, ensure_ascii=False)


def apply_documented_approximation_mode(spec):
    """Allow synthesized materials while keeping structural validation and render gates."""
    result = copy.deepcopy(spec)
    result["workflowPolicy"] = {
        "validationMode": "documented-source-derived-approximation",
        "materialPolicy": "Use observed source images as identity and broad color cues; synthesize detailed style-aware maps when clean source pixels are unavailable. Never label synthetic maps as extracted PBR.",
        "unknownGeometryPolicy": "Keep unresolved features and their confidence in the assessment and risks. Build bounded estimates only where required to produce the reviewable pilot; judge them through silhouette and multi-view render gates.",
    }
    targets = result.setdefault("lookDevTargets", {})
    if isinstance(targets, dict):
        targets["qualityPriority"] = "documented-source-derived-approximation"
        material_pass = targets.setdefault("materialPass", {})
        if isinstance(material_pass, dict):
            extraction = material_pass.setdefault("referencePbrExtraction", {})
            if isinstance(extraction, dict):
                extraction["requiredWhenSourceImagePresent"] = False
                extraction["stopOnLowConfidence"] = False
                extraction["acceptedLimitation"] = (
                    "Low-resolution or occluded source pixels provide material cues only; final detailed appearance may be synthesized and remains subject to visual review."
                )
    return result


def material_patch_status(size, minimum=64):
    width, height = size
    return (
        "resolution_eligible_for_review"
        if min(width, height) >= minimum
        else "resolution_inadequate"
    )


def enforce_material_review_policy(review, requires_synthesis):
    if not requires_synthesis:
        return review
    if review.get("action") in ("stop", "request-input"):
        return review
    score = review.get("material_score")
    if not isinstance(score, (int, float)) or not 0 <= score <= 1:
        raise NativeBlocked("CRITIC_MATERIAL_SCORE_MISSING_OR_INVALID")
    if score >= 0.75:
        return review
    return {
        **review,
        "model_action": review["action"],
        "action": "refine-code",
        "summary": review["summary"]
        + "; workflow policy: undersampled source requires an improved style-synthesized texture",
    }


def material_contact_sheet(run, materials):
    """Pair source pixels with generated proposals so reviewers see upscaling limits."""
    run = Path(run)
    tile_w, tile_h, label_h, gap = 260, 200, 28, 12
    rows = max(1, len(materials))
    sheet = Image.new(
        "RGB", (2 * tile_w + 3 * gap, rows * (tile_h + label_h + gap)), "#20242a"
    )
    draw = ImageDraw.Draw(sheet)
    for row, material in enumerate(materials):
        folder = run / "assets" / material
        source_path = folder / "source.png"
        extraction_path = folder / "extraction.json"
        if not source_path.exists():
            continue
        source = Image.open(source_path).convert("RGB")
        generated_path = None
        if extraction_path.exists():
            extraction = read(extraction_path)
            generated_path = Path(
                extraction.get("maps", {}).get("albedo", {}).get("path", "")
            )
        generated = (
            Image.open(generated_path).convert("RGB")
            if generated_path and generated_path.exists()
            else Image.new("RGB", (64, 64), "#555555")
        )
        y = row * (tile_h + label_h + gap)
        draw.text((gap, y), f"{material}: source pixels, nearest", fill="white")
        draw.text(
            (2 * gap + tile_w, y),
            f"{material}: generated albedo proposal",
            fill="white",
        )
        for x, image, resample in (
            (gap, source, Image.Resampling.NEAREST),
            (2 * gap + tile_w, generated, Image.Resampling.BILINEAR),
        ):
            image.thumbnail((tile_w, tile_h), resample=resample)
            px = x + (tile_w - image.width) // 2
            py = y + label_h + (tile_h - image.height) // 2
            sheet.paste(image, (px, py))
    output = run / "material-source-vs-albedo.jpg"
    sheet.save(output, quality=92)
    return output


def audit_material_assets(run, materials, source_image=None):
    run = Path(run)
    patches = []
    for material in materials:
        folder = run / "assets" / material
        crop = folder / "source.png"
        report_path = folder / "extraction.json"
        if not crop.is_file():
            continue
        size = Image.open(crop).size
        extraction = read(report_path) if report_path.is_file() else {}
        patches.append(
            {
                "material": material,
                "source_size_px": list(size),
                "source_sha256": file_hash(crop),
                "native_extractor_verdict": extraction.get("verdict"),
                "native_extractor_confidence": extraction.get("confidence"),
                "status": material_patch_status(size),
            }
        )
    adequate = bool(patches) and all(
        patch["status"] == "resolution_eligible_for_review" for patch in patches
    )
    return {
        "source_image": str(Path(source_image).resolve()) if source_image else None,
        "source_sha256": file_hash(source_image) if source_image else None,
        "minimum_source_patch_px": [64, 64],
        "recommended_source_patch_px": [128, 128],
        "maps_claimed_as_source_pbr": False,
        "resolution_gate_passed": adequate,
        "requires_style_synthesis": not adequate,
        "patches": patches,
        "reason": "Source crops are cues for material family/color/pattern only. Enlarged maps do not recover unobserved surface detail or constitute clean PBR.",
    }


def review_diagnostics(folder):
    folder = Path(folder)
    gates_path = folder / "gates.json"
    gates = read(gates_path) if gates_path.is_file() else {}
    out = {"failed_gates": [key for key, value in gates.items() if value is False]}
    for name in (
        "divine-eye",
        "geometry-gate",
        "part-coverage",
        "render-manifest",
        "camera-fit",
        "metric-footprint",
    ):
        path = folder / (name + ".json")
        if not path.is_file():
            continue
        payload = read(path)
        if name == "divine-eye":
            try:
                data = json.loads(payload.get("stdout", "{}"))
                out[name] = {
                    key: data.get(key)
                    for key in ("fidelity", "hardGateFailures", "verdict", "features")
                    if key in data
                }
            except json.JSONDecodeError:
                out[name] = {"error": payload.get("stderr", "")[-1200:]}
        elif name == "geometry-gate":
            out[name] = {
                key: payload.get(key)
                for key in (
                    "passed",
                    "failures",
                    "issues",
                    "triangleCount",
                    "triangleBudget",
                )
                if key in payload
            }
        elif name == "part-coverage":
            out[name] = {
                key: payload.get(key)
                for key in ("passed", "missing", "unexpected", "issues", "coverage")
                if key in payload
            }
        elif name == "render-manifest":
            manifest = payload.get("manifest", {})
            out[name] = {
                "probes": manifest.get("probes"),
                "triangles": manifest.get("triangles"),
            }
        elif name == "metric-footprint":
            out[name] = payload
        else:
            out[name] = {
                key: payload.get(key)
                for key in ("score", "azimuth", "elevation", "method")
                if key in payload
            }
    return out


def asset_fingerprint(spec):
    return digest(
        {
            k: spec.get(k)
            for k in [
                "sourceImage",
                "referenceCamera",
                "componentTree",
                "materials",
                "repetitionSystems",
                "coordinateFrame",
                "lightingFromPhoto",
                "proceduralStrategy",
            ]
        }
    )


def verify_render_evidence(folder, spec, target):
    folder = Path(folder)
    binding = read(folder / "evidence-binding.json")
    render = read(folder / "render-manifest.json")
    if binding["asset_fingerprint"] != asset_fingerprint(spec) or binding[
        "target_sha256"
    ] != file_hash(target):
        raise NativeBlocked("STALE_ASSET_OR_REFERENCE_EVIDENCE")
    if render["bundle_sha256"] != file_hash(folder / "bundle.js") or binding[
        "factory_sha256"
    ] != file_hash(folder / "createObjectModel.ts"):
        raise NativeBlocked("STALE_FACTORY_OR_RENDER_BUNDLE")
    if any(file_hash(folder / p) != h for p, h in render["captures"].items()):
        raise NativeBlocked("CAPTURE_HASH_MISMATCH")


def apply_sections(spec, sections):
    if not isinstance(sections, dict) or not sections:
        raise ValueError("EMPTY_SPEC_PATCH")
    if any(k in PROTECTED_SPEC_FIELDS or k not in spec for k in sections):
        raise ValueError("PROTECTED_OR_UNKNOWN_SPEC_SECTION")
    return json_edits(
        spec,
        [{"op": "replace", "path": "/" + k, "value": v} for k, v in sections.items()],
    )


def repair_view(spec):
    result = copy.deepcopy(spec)
    for k in list(result):
        if k in PROTECTED_SPEC_FIELDS:
            del result[k]
    component_keys = {
        "id",
        "name",
        "level",
        "parent",
        "primitive",
        "dimensions",
        "material",
        "colorMaterialRecipe",
        "topologyClass",
    }
    result["componentTree"] = [
        {k: v for k, v in c.items() if k in component_keys}
        | {
            "localFeatureIds": [
                f["id"] for f in c.get("localFeatures", []) if isinstance(f, dict)
            ]
        }
        for c in spec.get("componentTree", [])
    ]
    result["materials"] = [
        {
            "id": m["id"],
            "name": m.get("name"),
            "baseColor": m.get("baseColor"),
            "albedo": {
                k: m.get("albedo", {}).get(k) for k in ("dominant", "secondary")
            },
            "textureProjection": m.get("textureProjection"),
            "referencePbr": {
                k: m.get("referencePbr", {}).get(k)
                for k in ("usable", "confidence", "verdict")
            },
        }
        for m in spec.get("materials", [])
    ]
    result["viewEvidence"] = [
        {"id": v["id"], "sourceImage": v.get("sourceImage")}
        for v in spec.get("viewEvidence", [])
    ]
    inv = result.get("preSpecAssessment", {}).get("detailInventory", {})
    if inv:
        inv["details"] = [
            {k: d.get(k) for k in ("id", "kind", "mapsTo")}
            for d in inv.get("details", [])
        ]
    return result


def register_evidence(spec):
    """Normalize representation only: actual source files become named native view evidence."""
    spec = copy.deepcopy(spec)
    views = spec.setdefault("viewEvidence", [])
    ids = {v["id"] for v in views}
    refs = set()

    def visit(v):
        if isinstance(v, dict):
            for k, x in v.items():
                if k == "evidenceRefs" and isinstance(x, list):
                    refs.update(r for r in x if isinstance(r, str))
                else:
                    visit(x)
        elif isinstance(v, list):
            for x in v:
                visit(x)

    visit(spec)
    for ref in sorted(refs):
        if ref not in ids and Path(ref).is_file():
            views.append(
                {
                    "id": ref,
                    "view": "primary",
                    "sourceImage": str(Path(ref).resolve()),
                    "imageRegion": {
                        "x": 0,
                        "y": 0,
                        "width": 1,
                        "height": 1,
                        "units": "normalized",
                    },
                    "observations": [
                        "Verified source crop; same camera as primary, not an independent view."
                    ],
                    "confidence": 0.5,
                }
            )
            ids.add(ref)
    links = {
        c["id"] + "/" + f["id"]
        for c in spec.get("componentTree", [])
        for f in c.get("localFeatures", [])
        if isinstance(f, dict) and "id" in f
    }
    links |= {
        m["id"] + "/" + o["id"]
        for m in spec.get("materials", [])
        for o in m.get("localOverrides", [])
        if isinstance(o, dict) and "id" in o
    }
    for d in (
        spec.get("preSpecAssessment", {}).get("detailInventory", {}).get("details", [])
    ):
        maps = d.get("mapsTo", {})
        ref = maps.get("ref", "")
        candidate = ref.replace(".localFeatures.", "/").replace(".localOverrides.", "/")
        if candidate in links:
            maps["ref"] = candidate
    return spec


class Workflow:
    def __init__(self, run, settings, max_calls=10, max_tokens=240000):
        self.run = Path(run).resolve()
        self.run.mkdir(parents=True, exist_ok=True)
        self.bridge = NativeBridge(self.run)
        self.provider = Provider(settings, self.run, max_calls, max_tokens)
        self.settings = settings
        self.started = time.monotonic()
        self.ledger = self.bridge.ledger
        self.jobs = JobQueue(self.run / "jobs.sqlite")

    def node(self, name, prompt, images=(), max_output=7000):
        self.bridge.next()
        self.ledger.event(name, "started")
        key = self.jobs.enqueue(
            {
                "node": name,
                "prompt_sha256": digest(prompt),
                "images": [file_hash(p) for p in images],
                "model": self.settings.model,
                "transport": "stream-v1",
                "max_output": max_output,
                "upstream": self.bridge.lock["commit"],
            }
        )
        job = self.jobs.get(key)
        if job["status"] == "complete":
            value = read(job["artifact"])
            write_json(self.run / (name + ".json"), value)
            return value
        if job["status"] == "blocked" and (job.get("error") or "").startswith(
            "BudgetExceeded: MODEL_BUDGET_EXHAUSTED"
        ):
            # Provider budget validation happens before incrementing call usage or
            # opening HTTP. This one precise failure is safe to resume; 5xx,
            # timeouts and expired leases remain blocked/uncertain for reconciliation.
            self.jobs.requeue_preflight_budget(key)
            job = self.jobs.get(key)
        if job["status"] != "pending":
            raise NativeBlocked("JOB_RECONCILIATION_REQUIRED: " + key)
        lease = self.jobs.claim(seconds=300)
        if lease is None or lease["key"] != key:
            raise NativeBlocked("JOB_DEPENDENCY_OR_LEASE_BLOCKED")
        stopped = threading.Event()
        heartbeat_errors = []

        def heartbeat():
            while not stopped.wait(30):
                try:
                    self.jobs.heartbeat(key, lease["lease"])
                except Exception as exc:
                    heartbeat_errors.append(type(exc).__name__)
                    return

        thread = threading.Thread(target=heartbeat, daemon=True)
        thread.start()
        try:
            value = self.provider.call(name, prompt, images, max_output)
            if heartbeat_errors:
                raise NativeBlocked("NODE_LEASE_LOST_DURING_REQUEST")
        except Exception as exc:
            self.jobs.fail(
                key, lease["lease"], type(exc).__name__ + ": " + str(exc)[:200]
            )
            raise
        finally:
            stopped.set()
            thread.join(timeout=1)
        output = self.run / "nodes" / (key + ".json")
        write_json(output, value, exclusive=True)
        self.jobs.finish(key, lease["lease"], output)
        write_json(self.run / (name + ".json"), value)
        self.ledger.event(
            name, "finished", output_sha256=file_hash(self.run / (name + ".json"))
        )
        return value

    def prepare(self, reference, styles=(), context_images=(), evidence_path=None):
        reference = Path(reference).resolve()
        styles = [Path(p).resolve() for p in styles]
        context_images = [Path(p).resolve() for p in context_images]
        self.georeferenced_evidence = (
            load_evidence(evidence_path) if evidence_path else None
        )
        evidence_file = (
            (Path(evidence_path) / "evidence.json").resolve()
            if evidence_path and Path(evidence_path).is_dir()
            else Path(evidence_path).resolve()
            if evidence_path
            else None
        )
        if self.georeferenced_evidence:
            evidence_views = [
                Path(v["image"]).resolve()
                for v in self.georeferenced_evidence["views"]
                if file_hash(v["image"]) != file_hash(reference)
            ]
            context_images = list(dict.fromkeys([*context_images, *evidence_views]))
            self.georeference_facts = {
                "object_id": self.georeferenced_evidence["object_id"],
                "label": self.georeferenced_evidence.get("label"),
                "coordinate_frame": self.georeferenced_evidence["frame"],
                "footprint_m": self.georeferenced_evidence["footprint"],
                "footprint_source": self.georeferenced_evidence["footprint_source"],
                "wings": self.georeferenced_evidence["wings"],
                "height_m": self.georeferenced_evidence["height_m"],
                "height_source": self.georeferenced_evidence["height_source"],
                "tags": self.georeferenced_evidence.get("tags", {}),
                "uncertainty": self.georeferenced_evidence.get("uncertainty"),
                "views": [
                    {
                        "id": v["id"],
                        "image": Path(v["image"]).name,
                        "sha256": v.get("source_sha256"),
                        "camera": v["camera"],
                        "calibration": v["calibration"],
                    }
                    for v in self.georeferenced_evidence["views"]
                ],
            }
        else:
            self.georeference_facts = None
        self.context_images = context_images
        manifest = {
            "reference": {"path": str(reference), "sha256": file_hash(reference)},
            "styles": [{"path": str(p), "sha256": file_hash(p)} for p in styles],
            "context": [
                {"path": str(p), "sha256": file_hash(p)} for p in context_images
            ],
            "model": self.settings.model,
            "upstream": self.bridge.lock["commit"],
            "evidence": (
                {
                    "path": str(evidence_file),
                    "sha256": file_hash(evidence_file),
                    "object_id": self.georeferenced_evidence["object_id"],
                    "view_ids": [v["id"] for v in self.georeferenced_evidence["views"]],
                }
                if self.georeferenced_evidence
                else None
            ),
        }
        if (self.run / "inputs.json").exists() and read(
            self.run / "inputs.json"
        ) != manifest:
            raise ValueError("INPUTS_CHANGED_USE_NEW_RUN")
        write_json(self.run / "inputs.json", manifest)
        self.bridge.init(reference)
        if not (self.run / "observation.json").exists():
            observation = self.node(
                "observation",
                self.bridge.context("observe")
                + """\nTASK: Observe the first image using all eight analysis layers before any assessment. Additional context images follow it; last images are styles. Do NOT confuse style architecture/location with target. Return {"layers": [8 detailed layers], "suitability":"pass|conditional|reject", "reason":..., "target_bbox":[x,y,width,height] normalized tightly enclosing only the main building, "semantic_requirements":[{"part":...,"requirement":...,"observed_or_inferred":...}], "unknowns":[], "style":{"form_language":[],"detail_treatment":[],"lighting":[],"avoid":[]}}. Style is descriptive; do not create a fixed palette or override observed material colours. Cropping may remove unrelated fragments, never invent hidden walls.\nIMAGE ORDER: reference, """
                + str(len(context_images))
                + " context views, "
                + str(len(styles))
                + " style images."
                + (
                    "\nGEOREFERENCED FACTS (view IDs follow the factual context-image order; approximate OSM footprint and mesh-height evidence; do not treat OSM as a roof outline): "
                    + dump(self.georeference_facts)
                    if self.georeference_facts
                    else ""
                ),
                [reference, *context_images, *styles],
                6500,
            )
            self.bridge.mark("image-analysis", [self.run / "observation.json"])
            self.bridge.mark("reference-suitability", [self.run / "observation.json"])
        observation = read(self.run / "observation.json")
        for step in ["image-analysis", "reference-suitability"]:
            self.bridge.mark(step, [self.run / "observation.json"])
        if observation["suitability"] == "reject":
            raise NativeBlocked("REFERENCE_REJECTED: " + observation["reason"])
        target = self.run / "target.png"
        if not target.exists():
            image = Image.open(reference)
            w, h = image.size
            x, y, bw, bh = observation["target_bbox"]
            if not (
                0 <= x < 1
                and 0 <= y < 1
                and bw > 0
                and bh > 0
                and x + bw <= 1.001
                and y + bh <= 1.001
            ):
                raise ValueError("INVALID_OBSERVER_CROP")
            image.crop(
                (int(x * w), int(y * h), int((x + bw) * w), int((y + bh) * h))
            ).save(target)
            write_json(
                self.run / "crop-provenance.json",
                {
                    "original": manifest["reference"],
                    "bbox": observation["target_bbox"],
                    "crop_sha256": file_hash(target),
                    "note": "Original source retained; crop is not a new independent observation.",
                },
            )
        for image, label in [
            (reference, "reference"),
            (target, "target"),
            *[(p, f"context-{i}") for i, p in enumerate(context_images)],
            *[(p, f"style-{i}") for i, p in enumerate(styles)],
        ]:
            out = self.run / (label + "-admission.json")
            if not out.exists():
                gate = self.bridge.command(
                    "forge/stage1_intake/check_reference_admission.py",
                    [
                        image,
                        "--viewpoint",
                        label,
                        "--out",
                        out,
                        "--probe-out",
                        self.run / (label + "-probe.json"),
                    ],
                    check=False,
                )
                if gate["exit_code"]:
                    raise NativeBlocked("REFERENCE_ADMISSION_FAILED: " + label)
            elif not read(out)["admitted"]:
                raise NativeBlocked("REFERENCE_ADMISSION_FAILED: " + label)
        self.bridge.mark(
            "reference-admission",
            [self.run / "reference-admission.json", self.run / "target-admission.json"],
        )
        assessment = self.run / "assessment-starter.json"
        inventory = self.run / "inventory-starter.json"
        starter = self.run / "spec-starter.json"
        if not assessment.exists():
            self.bridge.command(
                "forge/stage2_spec/new_pre_spec_assessment.py",
                [
                    "Observed building",
                    "--image",
                    target,
                    "--domain",
                    "generic",
                    "--complexity",
                    "complex",
                    "--out",
                    assessment,
                ],
            )
        self.bridge.mark("local-spec-search", [assessment])
        if not inventory.exists():
            self.bridge.command(
                "forge/stage1_intake/build_detail_inventory.py",
                [
                    target,
                    "--complexity",
                    "complex",
                    "--out-dir",
                    self.run / "zones",
                    "--out",
                    inventory,
                ],
            )
        if not (self.run / "assessment.json").exists():
            crops = sorted((self.run / "zones").glob("*.png"))
            result = self.node(
                "assessment",
                self.bridge.context("observe")
                + "\nOBSERVATION: "
                + dump(observation)
                + "\nASSESSMENT SKELETON: "
                + assessment.read_text(encoding="utf-8")
                + "\nINVENTORY SKELETON: "
                + inventory.read_text(encoding="utf-8")
                + """\nReturn a complete assessment object matching assessment skeleton (preserve localSpecSearch and qualityContract unchanged). Fill preSpecAssessment from actual images and all 9 crop zones. Add >=10 concrete details mapped to IDs you will use in componentTree.localFeatures or materials.localOverrides, mark uncertainty. Do not count empty background zones as details. No unassessed/stub values. Images are cropped target then its 9 zone crops.""",
                [target, *crops],
                9500,
            )
            write_json(self.run / "assessment.json", result)
        if (
            read(self.run / "assessment.json")["qualityContract"]
            != read(assessment)["qualityContract"]
        ):
            raise ValueError("ASSESSMENT_CHANGED_NATIVE_QUALITY_CONTRACT")
        self.bridge.mark("pre-spec-assessment", [self.run / "assessment.json"])
        self.bridge.mark("detail-inventory", [self.run / "assessment.json"])
        if not starter.exists():
            self.bridge.command(
                "forge/stage2_spec/new_sculpt_spec.py",
                [
                    "Observed building",
                    "--image",
                    target,
                    "--assessment",
                    self.run / "assessment.json",
                    "--domain",
                    "generic",
                    "--out",
                    starter,
                ],
            )
        write_json(
            self.run / "material-applicability.json",
            {
                "projection": "not requested",
                "reason": "Approximate procedural materials accepted by user; shaded photogrammetry is not reliable albedo. No projected texture or PBR extraction is claimed. Native strict spec still applies.",
            },
        )
        self.bridge.mark(
            "projection-route",
            [self.run / "material-applicability.json"],
            status="skipped",
            reason="Procedural approximation explicitly allowed; no projected texture is claimed.",
        )
        if not (self.run / "object-sculpt-spec.json").exists():
            instructions = (
                self.bridge.context("spec")
                + "\nOBSERVATION: "
                + dump(observation)
                + "\nASSESSMENT: "
                + (self.run / "assessment.json").read_text(encoding="utf-8")
                + "\nNATIVE STARTER: "
                + starter.read_text(encoding="utf-8")
                + (
                    "\nGEOREFERENCED FACTS (approximate ground footprint; camera calibration per view is stated, do not present OSM tags or photogrammetry height estimates as survey truth): "
                    + dump(self.georeference_facts)
                    if self.georeference_facts
                    else ""
                )
                + """\nAuthor native ObjectSculptSpec sections grounded in reference. Never change protected sections: """
                + dump(sorted(PROTECTED_SPEC_FIELDS))
                + """. Macro dimensions normalized around width 1-3 units. Topology rationale before primitive; true holes use extrude geometryDescriptor.profile2D.holes or ovalHoles, not solid cylinders. Use only generator-readable schema fields. Don't claim solved camera or extracted PBR without evidence. Treat photogrammetry damage as unknown. No unassessed/stubs. Keep output concise; repeated details should use native repetition descriptors. Every detail must map to actual implemented fields."""
            )
            geometry_file = self.run / "geometry-author.json"
            geometry = (
                read(geometry_file)
                if geometry_file.exists()
                else self.node(
                    "geometry-author",
                    instructions
                    + """\nFIRST TRANSACTION: Return {"sections":{"componentTree":[complete native components]},"material_slots":[IDs your components use]}. Only componentTree goes in sections. Include all native minimum macro/meso/micro levels, actual localFeatures covering detail IDs, parent joints and geometry descriptors. Do not return materials or copy the whole starter. Images: target, contextual source views, then style images. Context informs spatial relationships; style does not define architecture.""",
                    [target, *context_images, *styles],
                    7500,
                )
            )
            intermediate = apply_sections(read(starter), geometry["sections"])
            write_json(self.run / "geometry-spec.json", intermediate)
            material_file = self.run / "material-author.json"
            materials = (
                read(material_file)
                if material_file.exists()
                else self.node(
                    "material-author",
                    instructions
                    + "\nAUTHORED COMPONENTS: "
                    + dump(geometry)
                    + """\nSECOND TRANSACTION: Return {"sections":{...}} with materials, preSpecAssessment (including its detailInventory), suitability, scores, featureReviewTargets, repetitionSystems, silhouette, proceduralStrategy and other needed EXISTING top-level sections only. Never return componentTree or protected sections. There is NO top-level detailInventory or geometryPlan: inventory belongs inside preSpecAssessment. Create every material slot used by geometry; wire >=10 inventoried details to actual localFeatures/material.localOverrides paths. Preserve qualityContract unchanged and avoid forcing a style palette. Procedural PBR approximation is accepted, not factual source texture extraction. Keep concise.""",
                    [target, *styles],
                    7500,
                )
            )
            if "componentTree" in materials["sections"]:
                raise ValueError("MATERIAL_NODE_CANNOT_REWRITE_GEOMETRY")
            spec = apply_sections(intermediate, materials["sections"])
            write_json(self.run / "object-sculpt-spec.json", spec)
        self.bridge.mark("spec-authoring", [self.run / "object-sculpt-spec.json"])
        spec = read(self.run / "object-sculpt-spec.json")
        normalized = register_evidence(spec)
        if normalized != spec:
            write_json(self.run / "object-sculpt-spec.json", normalized)
            write_json(
                self.run / "evidence-normalization.json",
                {
                    "before_sha256": digest(spec),
                    "after_sha256": digest(normalized),
                    "note": "Registered real crop files and normalized owner/feature pointer syntax; no geometric or material observations changed.",
                },
            )
        spec = apply_documented_approximation_mode(spec)
        write_json(self.run / "object-sculpt-spec.json", spec)
        if (
            self.georeferenced_evidence
            and not (self.run / "metric-frame.json").exists()
        ):
            macro = [
                c
                for c in spec["componentTree"]
                if c.get("level") == "macro" and c.get("parent")
            ]
            if not macro:
                raise NativeBlocked("METRIC_FRAME_MISSING_MACRO_WALLS")
            length_units = max(
                max(c["dimensions"]["width"], c["dimensions"]["depth"]) for c in macro
            )
            length_m = max(
                max(w["length_m"], w["width_m"])
                for w in self.georeferenced_evidence["wings"]
            )
            write_json(
                self.run / "metric-frame.json",
                {
                    "metres_per_unit": length_m / length_units,
                    "wall_names": [c["name"] for c in macro],
                    "method": "Fixed from initial longest macro wall vs evidence wing; subsequent camera/code edits cannot recalibrate it.",
                },
            )
        self.material_evidence(target)
        return target, styles

    def material_evidence(self, target):
        marker = self.run / "material-wiring.json"
        if marker.exists():
            quality_file = self.run / "material-quality.json"
            if not quality_file.exists():
                materials = [
                    m["id"]
                    for m in read(self.run / "object-sculpt-spec.json")["materials"]
                ]
                write_json(
                    quality_file, audit_material_assets(self.run, materials, target)
                )
            material_contact_sheet(
                self.run,
                [
                    m["id"]
                    for m in read(self.run / "object-sculpt-spec.json")["materials"]
                ],
            )
            self.bridge.mark("material-evidence", [self.run / "material-regions.json"])
            self.bridge.mark("material-spec-wiring", [marker])
            return
        state = read(self.run / ".img2threejs/state.json")
        if any(
            e["id"] == "material-evidence" and e["status"] == "skipped"
            for e in state["checklist"]
        ):
            self.bridge.command(
                "forge/state.py",
                [
                    "mark",
                    "material-evidence",
                    "material-spec-wiring",
                    "--state",
                    self.run / ".img2threejs/state.json",
                    "--status",
                    "pending",
                    "--reason",
                    "Strict gate requires real PBR evidence; invalidate previously skipped material route.",
                ],
            )
        spec = read(self.run / "object-sculpt-spec.json")
        regions_file = self.run / "material-regions.json"
        material_sources = [("target", Path(target).resolve())] + [
            (f"context-{i}", Path(p).resolve())
            for i, p in enumerate(getattr(self, "context_images", []))
        ]
        source_dimensions = {
            source_id: list(Image.open(path).size)
            for source_id, path in material_sources
        }
        if not regions_file.exists():
            regions = self.node(
                "material-regions-v2",
                'Inspect the target and context images as alternate evidence views. Native strict quality requires actual source-pixel evidence, not a fixed texture catalog. Identify one representative material patch per material ID. Return {"regions":[{"material_id":...,"source_view_id":"target|context-N","bbox":[x,y,width,height] normalized to that image,"observation":...,"confidence":0..1}],"missing":[]}. Every ID must be covered or explicitly missing. Image order and IDs: '
                + dump(
                    [
                        {"id": view_id, "size_px": size}
                        for view_id, size in source_dimensions.items()
                    ]
                )
                + ". A usable source patch must contain at least 64x64 original pixels of one reasonably uniform visible surface; prefer 128x128 or larger. Choose a larger genuinely homogeneous patch, not a tiny detail enlarged by the crop. If no such patch exists, mark that material missing and explain the required closer or higher-resolution view. Select the cleanest visible material patch without mixing roof, sky, windows or deep shadow; never substitute a style-image patch. Do not claim accurate physical PBR. IDs and authored descriptions: "
                + dump(
                    [
                        {k: m.get(k) for k in ("id", "name", "baseColor", "notes")}
                        for m in spec["materials"]
                    ]
                ),
                [p for _, p in material_sources],
                2200,
            )
            write_json(regions_file, regions)
        regions = read(regions_file)
        ids = {m["id"] for m in spec["materials"]}
        region_ids = [r["material_id"] for r in regions.get("regions", [])]
        missing_by_id = {
            item["material_id"]: item.get("reason", "No clean source patch is visible.")
            for item in regions.get("missing", [])
            if item.get("material_id")
        }
        if len(region_ids) != len(set(region_ids)) or not set(region_ids) <= ids:
            raise NativeBlocked("MATERIAL_REGION_COVERAGE_INVALID")
        if set(region_ids) | set(missing_by_id) != ids:
            raise NativeBlocked("MATERIAL_REGION_COVERAGE_INCOMPLETE")
        regions_by_id = {r["material_id"]: r for r in regions.get("regions", [])}
        materials_by_id = {m["id"]: m for m in spec["materials"]}
        reports = []
        quality_report = {
            "source_image": str(Path(target).resolve()),
            "source_sha256": file_hash(target),
            "minimum_source_patch_px": [64, 64],
            "recommended_source_patch_px": [128, 128],
            "maps_claimed_as_source_pbr": False,
            "resolution_gate_passed": False,
            "patches": [],
        }
        for mid in sorted(ids):
            if not mid or any(
                c
                not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
                for c in mid
            ):
                raise ValueError("UNSAFE_MATERIAL_ID")
            region = regions_by_id.get(mid)
            folder = self.run / "assets" / mid
            folder.mkdir(parents=True, exist_ok=True)
            if region is None:
                reason = missing_by_id[mid]
                material = materials_by_id[mid]
                write_json(
                    folder / "synthesis-cue.json",
                    {
                        "material_id": mid,
                        "source_patch_available": False,
                        "source_limitation": reason,
                        "material_family": material.get("name"),
                        "observed_base_color_cue": material.get("baseColor"),
                        "material_notes": material.get("notes"),
                        "instruction": "Author a plausible detailed procedural material from this observed material-family cue and the requested style reference. Do not claim it is an extracted source texture or accurate PBR. Preserve semantic material identity; style may transform finish and fine surface detail without imposing a fixed palette.",
                    },
                )
                patch = {
                    "material": mid,
                    "source_size_px": None,
                    "source_sha256": None,
                    "status": "no_usable_source_patch_synthesize",
                    "observation": reason,
                }
                quality_report["patches"].append(patch)
                reports.append(
                    {
                        "material": mid,
                        "source_patch_status": patch["status"],
                        "native_extraction_is_final_texture": False,
                        "style_synthesis_required": True,
                    }
                )
                continue
            source_id = region.get("source_view_id", "target")
            source_map = dict(material_sources)
            if source_id not in source_map:
                raise NativeBlocked(
                    "MATERIAL_REGION_UNKNOWN_SOURCE_VIEW: " + str(source_id)
                )
            source_image = source_map[source_id]
            source = Image.open(source_image)
            source_w, source_h = source.size
            x, y, bw, bh = region["bbox"]
            if not (
                0 <= x < 1
                and 0 <= y < 1
                and bw > 0
                and bh > 0
                and x + bw <= 1.001
                and y + bh <= 1.001
            ):
                raise ValueError("INVALID_MATERIAL_CROP")
            crop = folder / "source.png"
            if not crop.exists():
                source.crop(
                    (
                        round(x * source_w),
                        round(y * source_h),
                        round((x + bw) * source_w),
                        round((y + bh) * source_h),
                    )
                ).save(crop)
            crop_size = Image.open(crop).size
            patch = {
                "material": mid,
                "source_view_id": source_id,
                "source_image_sha256": file_hash(source_image),
                "bbox_normalized": region["bbox"],
                "source_size_px": list(crop_size),
                "source_sha256": file_hash(crop),
                "reported_confidence": region.get("confidence"),
                "observation": region.get("observation"),
                "status": material_patch_status(crop_size),
            }
            quality_report["patches"].append(patch)
            if patch["status"] != "resolution_eligible_for_review":
                material = materials_by_id[mid]
                write_json(
                    folder / "synthesis-cue.json",
                    {
                        "material_id": mid,
                        "source_patch_available": True,
                        "source_size_px": list(crop_size),
                        "source_sha256": file_hash(crop),
                        "source_limitation": "Original pixels are too few for texture extraction; retain only broad material-family, color-placement and directional cues.",
                        "material_family": material.get("name"),
                        "observed_base_color_cue": material.get("baseColor"),
                        "material_notes": material.get("notes"),
                        "instruction": "Author a plausible detailed procedural material from the observed cues and requested style reference. Do not enlarge the crop as if it contained recovered detail; do not claim extracted source texture or accurate PBR.",
                    },
                )
                reports.append(
                    {
                        "material": mid,
                        "source_patch_status": patch["status"],
                        "native_extraction_is_final_texture": False,
                        "style_synthesis_required": True,
                    }
                )
                continue
            report = folder / "extraction.json"
            if not report.exists():
                self.bridge.command(
                    "forge/stage1_intake/extract_pbr_evidence.py",
                    [
                        crop,
                        "--out-dir",
                        folder,
                        "--material-id",
                        mid,
                        "--size",
                        "1024",
                        "--url-prefix",
                        "./assets/" + mid,
                        "--spec",
                        self.run / "object-sculpt-spec.json",
                        "--in-place",
                        "--report",
                        report,
                    ],
                    check=False,
                    timeout=180,
                )
            if not report.exists() or not read(report).get("ok"):
                raise NativeBlocked("NATIVE_PBR_CONFIDENCE_FAILED: " + mid)
            reports.append(
                {
                    "material": mid,
                    "report_sha256": file_hash(report),
                    "confidence": read(report)["confidence"],
                    "source_patch_status": patch["status"],
                    "native_extraction_is_final_texture": False,
                }
            )
        self.bridge.mark("material-evidence", [regions_file])
        quality_report["resolution_gate_passed"] = all(
            item["status"] == "resolution_eligible_for_review"
            for item in quality_report["patches"]
        )
        quality_report["requires_style_synthesis"] = not quality_report[
            "resolution_gate_passed"
        ]
        quality_report["maps_claimed_as_source_pbr"] = False
        quality_report["reason"] = (
            "Source crops are retained as material identity/color cues only. They do not establish clean albedo or physical PBR. "
            + (
                "Some materials lack a clean source patch or fall below the pixel-resolution floor; these materials require an explicitly stylized procedural texture."
                if quality_report["requires_style_synthesis"]
                else "Crops clear the size floor but still need review for baked lighting, projection distortion and occlusion."
            )
        )
        write_json(self.run / "material-quality.json", quality_report)
        contact = material_contact_sheet(self.run, [m["id"] for m in spec["materials"]])
        write_json(
            marker,
            {
                "reports": reports,
                "source_sha256": file_hash(target),
                "contact_sheet": str(contact),
                "note": "Native extractor output is an initial compatibility proposal, not accepted final material. Source crop is not claimed as clean PBR. Style synthesis and visual review decide final surface appearance.",
            },
        )
        self.bridge.mark("material-spec-wiring", [marker])

    def strict_repair(self, target, styles, max_repairs=2):
        for attempt in range(max_repairs + 1):
            gate = self.bridge.strict()
            write_json(self.run / "strict-result.json", gate)
            if gate["exit_code"] == 0:
                self.bridge.mark("strict-validation", [self.run / "strict-result.json"])
                return
            strict_report = json.loads(gate["stdout"] or "{}")
            strict_errors = strict_report.get("errors", [])
            if strict_errors and all(
                error.startswith("strict quality failure:") for error in strict_errors
            ):
                structural = self.bridge.strict(strict_quality=False)
                try:
                    structural_report = json.loads(structural["stdout"] or "{}")
                except json.JSONDecodeError:
                    structural_report = {"ok": False, "errors": [structural["stdout"]]}
                if structural["exit_code"] == 0 and structural_report.get("ok") is True:
                    accepted = {
                        "mode": "documented-source-derived-approximation",
                        "structural_validation": structural_report,
                        "quality_warnings": strict_report.get("warnings", []),
                        "policy": "Unknown surfaces may use procedural style synthesis. This records a bounded approximation; it does not assert extracted PBR, surveyed dimensions, or resolved hidden geometry. Visual render gates remain mandatory.",
                    }
                    write_json(self.run / "quality-exceptions.json", accepted)
                    write_json(self.run / "spec-validation.json", structural_report)
                    self.bridge.mark(
                        "strict-validation",
                        [
                            self.run / "spec-validation.json",
                            self.run / "quality-exceptions.json",
                        ],
                        reason="Structural schema passes; quality warnings are explicitly carried as approximation risks to visual gates.",
                    )
                    return
            if attempt == max_repairs:
                raise NativeBlocked("STRICT_SPEC_FAILED_AFTER_BOUNDED_REPAIRS")
            spec = read(self.run / "object-sculpt-spec.json")
            validator = (
                self.bridge.upstream / "forge/stage2_spec/validate_sculpt_spec.py"
            ).read_text(encoding="utf-8")
            relevant = "\n".join(
                line
                for line in validator.splitlines()
                if any(
                    s in line
                    for s in (
                        "VALID_MATERIAL_CLASSES",
                        '"metal"',
                        '"wood"',
                        '"stone"',
                        '"glass"',
                        '"paint"',
                    )
                )
            )
            errors = strict_errors or [
                line
                for line in gate["stdout"].splitlines()
                if line.startswith("error:")
            ]
            targeted = bool(errors) and all(
                "unresolved unknowns" in e or "lighting-pass" in e for e in errors
            )
            if targeted:
                view = {
                    "preSpecAssessment": {
                        "unknownsToResolveBeforeImplementation": spec[
                            "preSpecAssessment"
                        ]["unknownsToResolveBeforeImplementation"]
                    },
                    "assumptions": spec["assumptions"],
                    "lightingFromPhoto": spec["lightingFromPhoto"],
                }
                fragment = validator[
                    validator.index(
                        '    lighting = spec.get("lightingFromPhoto"'
                    ) : validator.index("\ndef _detail_link_keys")
                ]
                fix = self.node(
                    "targeted-contract-repair-" + digest(errors)[:8],
                    'Fix only the two native contract categories shown. Return {"action":"patch|request-input","summary":...,"edits":[{"op":"add|replace","path":...,"value":...}]}. The user explicitly accepts approximate textures and inferred hidden surrounding surfaces. For EACH unknown, decide whether implementation really cannot proceed, or whether a documented bounded inference is adequate. Keep genuine blockers; move accepted inferences to assumptions with low-confidence status, never call them observed or delete their provenance. Original observation and source remain unchanged. Set a concrete proposed exposure/tone mapping intent inside lightingFromPhoto, as required by actual validator, not only in lookDevTargets. Renderer review profile currently uses ACESFilmic at exposure 1, separate from inferred source lighting. Do not change geometry, materials, scores or native thresholds.\nACTUAL NATIVE VALIDATOR:\n'
                    + fragment
                    + "\nCURRENT RELEVANT FIELDS: "
                    + dump(view)
                    + "\nERRORS: "
                    + dump(errors),
                    [target],
                    3000,
                )
                if fix.get("action") == "request-input":
                    raise NativeBlocked("UNRESOLVED_REFERENCE_INPUT: " + fix["summary"])
                write_json(
                    self.run / "object-sculpt-spec.json", json_edits(spec, fix["edits"])
                )
                continue
            repairs = self.node(
                "spec-repair-patches-" + str(attempt),
                'Repair this native spec using small JSON Pointer edits. Return {"edits":[{"op":"add|replace","path":"/componentTree/0/colorMaterialRecipe","value":...}]} only. No full-spec rewrite. Preserve every native quality floor and machine-generated referencePbr. No fabricated evidence. Keep uncertainty in assumptions/observation; before-implementation unknowns may be resolved only by an explicit approximation decision accepted by user. mapsTo.ref native syntax is ownerId/featureId, not owner.localFeatures.featureId. Every evidenceRefs string must match an existing viewEvidence.id; add a view record only for a real listed image. colorMaterialRecipe requires dominantAlbedo and secondaryAlbedo rgba strings, valid materialClass, materialClassConfidence 0..1. material textureProjection needs mode plus texel-density/repeat intent.\nNATIVE ENUM EXCERPT: '
                + relevant
                + "\nPROTECTED: "
                + dump(sorted(PROTECTED_SPEC_FIELDS))
                + "\nSPEC (machine PBR internals omitted; do not replace them): "
                + dump(repair_view(spec))
                + "\nERRORS: "
                + gate["stdout"]
                + gate["stderr"],
                [target],
                6000,
            )
            write_json(
                self.run / "object-sculpt-spec.json", json_edits(spec, repairs["edits"])
            )

    def render_gates(self, pass_id, target):
        spec = read(self.run / "object-sculpt-spec.json")
        canonical, aliases = canonicalize_aliases(spec)
        if aliases:
            write_json(
                self.run / "compiler-normalization.json",
                {
                    "changes": aliases,
                    "before_sha256": digest(spec),
                    "after_sha256": digest(canonical),
                    "note": "Field-name conversion only; original authored numeric vertices/depth preserved.",
                },
            )
            overlay_file = self.run / "semantic-overlay.json"
            if overlay_file.exists():
                overlay = read(overlay_file)
                if overlay.get("geometry_sha256") == digest(spec["componentTree"]):
                    overlay["geometry_sha256"] = digest(canonical["componentTree"])
                    overlay["schema_normalization"] = aliases
                    write_json(overlay_file, overlay)
            spec = canonical
            write_json(self.run / "object-sculpt-spec.json", spec)
        for correction in range(2):
            problems = compiler_issues(spec, pass_id)
            write_json(
                self.run / "compiler-preflight.json",
                {"pass_id": pass_id, "issues": problems, "passed": not problems},
            )
            if not problems:
                break
            if correction:
                raise NativeBlocked("COMPILER_CONTRACT_FAILED_AFTER_REPAIR")
            result = self.node(
                "compiler-contract-repair-" + pass_id + "-" + digest(problems)[:8],
                'Native factory cannot execute prose or schema aliases. Return {"edits":[small JSON Pointer add/replace operations]} using the actual top-level native sections `componentTree` and `repetitionSystems` (never `/components` or `/repetitions`). Fix only executable descriptor/placement fields. Author concrete numeric estimated counts and positions with inferred confidence; an uncertain count still needs a buildable estimate, not a string. Native extrude: geometryDescriptor.profile2D={points:[[x,y]],depth:positive,holes:[loops]}; dimensions then scale its vertices. Native repetitions need parent, primitive, integer count, placement object {mode:"linear|radial",origin:[x,y,z],axis:[x,y,z],step:[x,y,z],radius:number}, instanceScale:[x,y,z], material and level. No fixed style palette. Do not change protected native contracts/history or machine PBR evidence.\nERRORS: '
                + dump(problems)
                + "\nCOMPONENTS: "
                + dump(
                    [
                        {
                            k: c.get(k)
                            for k in (
                                "id",
                                "level",
                                "parent",
                                "primitive",
                                "dimensions",
                                "transform",
                                "geometryDescriptor",
                            )
                        }
                        for c in spec["componentTree"]
                    ]
                )
                + "\nREPETITIONS: "
                + dump(spec.get("repetitionSystems", [])),
                [target],
                4000,
            )
            spec = json_edits(spec, result["edits"])
            write_json(self.run / "object-sculpt-spec.json", spec)
        iteration = sum(
            r.get("passId") == pass_id for r in spec.get("reviewHistory", [])
        )
        folder = self.run / pass_id / f"attempt-{iteration}"
        folder.mkdir(parents=True, exist_ok=True)
        material_sheet = self.run / "material-source-vs-albedo.jpg"
        if material_sheet.exists():
            shutil.copy2(material_sheet, folder / material_sheet.name)
        factory = folder / "createObjectModel.ts"
        pending = self.run / "pending-code-edit.json"
        if pending.exists():
            job = read(pending)
            if job["pass_id"] != pass_id:
                raise NativeBlocked("CODE_REFINEMENT_PASS_MISMATCH")
            source = Path(job["source"]).read_text(encoding="utf-8")
            code = self.node(
                "code-author-" + pass_id + "-" + str(iteration),
                self.bridge.context("spec")
                + "\nSPEC: "
                + dump(repair_view(spec))
                + "\nFEEDBACK: "
                + dump(job["review"])
                + "\nDETERMINISTIC DIAGNOSTICS: "
                + dump(job.get("diagnostics", {}))
                + "\nGEOREFERENCED FACTS (retain this common frame and wing ratios): "
                + dump(getattr(self, "georeference_facts", None))
                + "\nMATERIAL SOURCE QUALITY: "
                + dump(
                    read(self.run / "material-quality.json")
                    if (self.run / "material-quality.json").exists()
                    else {}
                )
                + "\nEDITABLE FACTORY BODY:\n"
                + source[source.index("export function ") :]
                + """\nReturn {"edits":[{"find":exact unique existing source substring,"replace":new TypeScript}],"summary":...,"components":[IDs]}. This is native refine-code: fix implementation of an otherwise sound spec, do not regenerate or alter the native gate history. Keep every required named part, pivot, socket and sculptRuntime entry; do not spoof part manifests or tests. Use real geometry for voids, bevels, roof planes and frames. For texture defects, author a deterministic tileable procedural Three.js treatment from source material cues and the requested style. Preserve the observed material family and meaningful pattern direction, while adapting meso/micro detail and finish. Never enlarge a few source pixels and call them recovered detail; do not copy a fixed palette from style images. Keep edits small and reusable. No external network/assets/imports; Three.js only. Repeated structural decisions will be persisted as a versioned code overlay referenced in the spec, reapplied to future native generations only if anchors remain exact. Images: target, last render, material source-vs-generated contact sheet, then styles."""
                + "\nAdditional constraints: treat deterministic diagnostics as hard requirements and fix each demonstrated failure; preserve measured silhouette, dimensions, roof profile, openings and feature placement. Do not add unsupported decorative objects or untracked parts. For material edits, use coherent multiscale, material-specific procedural detail; avoid obvious periodic speckles/noise and preserve source material identity without copying a fixed style palette. After the style images, additional source context images show the same object from other directions. These constrain its geometry, not its style.",
                [
                    target,
                    (
                        Path(job["source"]).parent / "front.png"
                        if (Path(job["source"]).parent / "front.png").is_file()
                        else target
                    ),
                    *(
                        [self.run / "material-source-vs-albedo.jpg"]
                        if (self.run / "material-source-vs-albedo.jpg").exists()
                        else []
                    ),
                    *[
                        Path(x["path"])
                        for x in read(self.run / "inputs.json")["styles"]
                    ],
                    *getattr(self, "context_images", []),
                ],
                6500,
            )
            updated = text_edits(source, code["edits"], job["source_digest"])
            factory.write_text(updated, encoding="utf-8")
            overlay = {
                "pass_id": pass_id,
                "edits": code["edits"],
                "summary": code["summary"],
                "components": code["components"],
            }
            key = digest(overlay)
            write_json(
                self.run / "code-overlays" / (key + ".json"), overlay, exclusive=True
            )
            marker = "worldscale-code-overlay:" + key
            if marker not in spec["proceduralStrategy"]:
                spec["proceduralStrategy"].append(marker)
            write_json(self.run / "object-sculpt-spec.json", spec)
            pending.unlink()
        else:
            binding_file = folder / "evidence-binding.json"
            existing = read(binding_file) if binding_file.exists() else {}
            reusable = (
                factory.exists()
                and existing.get("asset_fingerprint") == asset_fingerprint(spec)
                and existing.get("factory_sha256") == file_hash(factory)
            )
            if not reusable:
                self.bridge.generate(pass_id, factory)
            source = factory.read_text(encoding="utf-8")
            for marker in [] if reusable else spec.get("proceduralStrategy", []):
                if isinstance(marker, str) and marker.startswith(
                    "worldscale-code-overlay:"
                ):
                    key = marker.split(":", 1)[1]
                    overlay = read(self.run / "code-overlays" / (key + ".json"))
                    if digest(overlay) != key:
                        raise NativeBlocked("CODE_OVERLAY_HASH_MISMATCH")
                    source = text_edits(source, overlay["edits"], digest(source))
            factory.write_text(source, encoding="utf-8")
        if getattr(self, "georeferenced_evidence", None):
            frame = read(self.run / "metric-frame.json")
            grounded, changes = bind_wing_poses(
                factory.read_text(encoding="utf-8"),
                spec,
                self.georeferenced_evidence,
                frame["metres_per_unit"],
            )
            factory.write_text(grounded, encoding="utf-8")
            write_json(
                folder / "frame-binding.json",
                {"changes": changes, "metres_per_unit": frame["metres_per_unit"]},
            )
        self.bridge.mark("build-current-pass", [factory])
        write_json(
            folder / "evidence-binding.json",
            {
                "asset_fingerprint": asset_fingerprint(spec),
                "target_sha256": file_hash(target),
                "factory_sha256": file_hash(factory),
            },
        )
        semantic_file = self.run / "semantic-overlay.json"
        if not semantic_file.exists() or read(semantic_file).get(
            "geometry_sha256"
        ) != digest(spec["componentTree"]):
            result = self.node(
                "semantic-author-" + pass_id + "-" + str(iteration),
                "NATIVE COMPONENT TREE: "
                + dump(
                    [
                        {
                            k: c[k]
                            for k in (
                                "id",
                                "parent",
                                "primitive",
                                "dimensions",
                                "geometryDescriptor",
                                "transform",
                            )
                            if k in c
                        }
                        for c in spec["componentTree"]
                    ]
                )
                + "\nOBSERVATIONS: "
                + dump(read(self.run / "observation.json")["semantic_requirements"])
                + """\nMap physical meaning to geometric probes. Return {"checks":[{"component_id":native ID,"requirement":"air_path|opening","axis":[x,y,z],"centre":[x,y,z],"length":positive,"wall_probe":[x,y,z],"confidence":"observed|inferred"}],"coverage":[{"requirement":observation requirement,"components":[IDs],"test":"geometric|vision|needs-input","reason":...}],"unresolved_critical":[]}. Probe coordinates are relative to the native pivot in model units, not normalized size coordinates; length crosses the full object wall. At least one wall_probe must hit actual material while the centre ray goes through the void. A chimney/flue requires an actual channel or a declared unresolved physical function; a painted hole/solid cylinder cannot satisfy it. Don't fabricate voids where geometryDescriptor has none. Include visible passage/window openings only where actually open, not glazing. Pure shape/material observations can route to vision. If no probes apply, explain coverage and uncertainty explicitly. Do not change geometry. Actual target image follows.""",
                [target],
                4500,
            )
            valid = [
                NativeSemanticCheck.model_validate(c).model_dump()
                for c in result["checks"]
            ]
            ids = {c["id"] for c in spec["componentTree"]}
            if any(c["component_id"] not in ids for c in valid):
                raise NativeBlocked("SEMANTIC_CHECK_UNKNOWN_COMPONENT")
            result["checks"] = valid
            result["geometry_sha256"] = digest(spec["componentTree"])
            write_json(semantic_file, result)
        overlay = read(semantic_file)
        write_json(folder / "semantic-overlay.json", overlay)
        w, h = Image.open(target).size
        scale = min(1100 / w, 850 / h)
        write_json(
            folder / "render-config.json",
            {"width": round(w * scale), "height": round(h * scale)},
        )
        if (self.run / "assets").exists():
            shutil.copytree(self.run / "assets", folder / "assets", dirs_exist_ok=True)
        bundle(folder, native=factory)
        report = capture(folder, reference=target)
        if report.get("runtime_error"):
            error_file = folder / "browser-bootstrap-failure.json"
            write_json(error_file, report)
            gates = {
                "browser": False,
                "browser_runtime_error": report["runtime_error"],
                "full_native_gates": False,
            }
            write_json(folder / "gates.json", gates)
            return folder, gates
        self.bridge.mark("render-capture", [folder / "render-manifest.json"])
        (folder / "review-contract.txt").write_text(
            self.bridge.context("review"), encoding="utf-8"
        )
        self.bridge.mark("review-contract-read", [folder / "review-contract.txt"])
        gates = {}
        commands = [
            (
                "tier1",
                "forge/stage4_review/diagnose_render.py",
                [
                    "--reference",
                    target,
                    "--render",
                    folder / "front.png",
                    *(
                        ["--map-stripped-render", folder / "clay.png"]
                        if pass_id == "blockout"
                        else []
                    ),
                    "--spec",
                    self.run / "object-sculpt-spec.json",
                    "--pass-id",
                    pass_id,
                    "--in-place",
                    "--json",
                ],
            ),
            (
                "divine-eye",
                "forge/stage4_review/divine_eye.py",
                ["--reference", target, "--render", folder / "front.png", "--json"],
            ),
            (
                "interior",
                "forge/stage4_review/interior_difference.py",
                [target, folder / "front.png", "--json"],
            ),
            (
                "orbit",
                "forge/stage4_review/diagnose_render_multi_angle.py",
                [
                    "--reference",
                    folder / "front.png",
                    "--orbit",
                    folder / "rear.png",
                    "--orbit",
                    folder / "side.png",
                    "--json",
                ],
            ),
            (
                "parts",
                "forge/stage4_review/check_part_coverage.py",
                [
                    "--spec",
                    folder / "pass-coverage-spec.json",
                    "--manifest",
                    folder / "parts.json",
                    "--json",
                    folder / "part-coverage.json",
                ],
            ),
            (
                "attachment",
                "forge/stage4_review/attachment_anchor.py",
                [
                    self.run / "object-sculpt-spec.json",
                    "--measured",
                    folder / "measured.json",
                    "--json",
                ],
            ),
        ]
        # Meso and micro components are deliberately authored in later native
        # passes. Gate only the current pass's promised parts; the final delivery
        # still validates the full spec after optimization-pass.
        write_json(
            folder / "pass-coverage-spec.json", pass_coverage_spec(spec, pass_id)
        )
        for name, script, args in commands:
            result = self.bridge.command(script, args, check=False)
            write_json(folder / (name + ".json"), result)
            gates[name] = result["exit_code"] == 0
        self.bridge.mark("tier1-diagnostics", [folder / "tier1.json"])
        self.bridge.mark("multi-angle-review", [folder / "orbit.json"])
        gate = self.bridge.check_pass(pass_id)
        write_json(folder / "pass-check.json", gate)
        gates["pass_check"] = gate["exit_code"] == 0
        self.bridge.mark("pass-gate-check", [folder / "pass-check.json"])
        structural = self.bridge.function_gate(
            "geometry", folder / "geometry.json", folder / "geometry-gate.json"
        )
        gates["geometry"] = structural["exit_code"] == 0
        if getattr(self, "georeferenced_evidence", None):
            frame = read(self.run / "metric-frame.json")
            metric = metric_footprint_report(
                read(folder / "geometry.json"),
                self.georeferenced_evidence,
                frame["wall_names"],
                frame["metres_per_unit"],
            )
            write_json(folder / "metric-footprint.json", metric)
            gates["metric_footprint"] = metric["passed"]
        attachment = read(folder / "attachment.json")
        try:
            attachment_report = json.loads(attachment["stdout"])
            gates["attachment"] = gates["attachment"] and not attachment_report.get(
                "unmeasuredAttachments"
            )
        except (ValueError, TypeError):
            gates["attachment"] = False
        interior = read(folder / "interior.json")
        try:
            gates["interior"] = (
                gates["interior"]
                and json.loads(interior["stdout"]).get("status") == "measured"
            )
        except (ValueError, TypeError):
            gates["interior"] = False
        comparison(target, folder / "front.png", folder / "comparison.png")
        camera = read(folder / "camera-fit.json")
        gates["reference_camera_matched"] = camera["score"] >= 0.8 and gates["tier1"]
        required = {
            r["requirement"]
            for r in read(self.run / "observation.json")["semantic_requirements"]
        }
        covered = {r.get("requirement") for r in overlay.get("coverage", [])}
        gates["browser"] = report["passed"]
        gates["action_ready"] = report["manifest"]["sculptRuntime"]
        gates["semantic_coverage"] = (
            not overlay.get("unresolved_critical") and required <= covered
        )
        # Before the review is appended, the native pass checker is expected to
        # report "locked pending review". It is recorded as evidence, but it is
        # not a render-quality failure and must not suppress the critic forever.
        gates["full_native_gates"] = all(
            gates.get(k)
            for k in [
                "tier1",
                "divine-eye",
                "interior",
                "orbit",
                "parts",
                "attachment",
                "geometry",
                "reference_camera_matched",
                "browser",
                "action_ready",
                "semantic_coverage",
            ]
        )
        if "metric_footprint" in gates:
            gates["full_native_gates"] = (
                gates["full_native_gates"] and gates["metric_footprint"]
            )
        write_json(folder / "gates.json", gates)
        return folder, gates

    def critic(self, pass_id, folder, target, styles):
        """Executable native critic route; unreachable until ALL gate evidence is clean."""
        folder = Path(folder)
        gates = read(folder / "gates.json")
        if not gates.get("full_native_gates"):
            raise NativeBlocked("CRITIC_DENIED_DETERMINISTIC_GATES")
        spec = read(self.run / "object-sculpt-spec.json")
        verify_render_evidence(folder, spec, target)
        review = self.node(
            "critic-" + pass_id,
            self.bridge.context("review")
            + "\nSPEC: "
            + dump(spec)
            + "\nGATES: "
            + dump(gates)
            + "\nMATERIAL SOURCE QUALITY: "
            + dump(
                read(self.run / "material-quality.json")
                if (self.run / "material-quality.json").exists()
                else {}
            )
            + """\nReturn {"score":0..1,"style_score":0..1,"style_evidence":...,"material_score":0..1,"material_evidence":...,"action":"continue|refine-spec|refine-code|request-input|stop","summary":...,"features":[{"id":actual feature target id,"score":0..1,"summary":...}],"layers":{all required native layer names:0..1},"defects":[{"component":...,"evidence":...,"fix":...}]}. Evaluate reference vs front only; orbit images test self-consistency, not unobserved ground truth. The image after the orbit renders is the material source-vs-generated audit; final images are style references. Treat undersampled source crops only as cues for material family, broad color placement and directional structure. Do not accept their enlarged maps as detailed final texture. Score material clarity, plausible surface frequency, coherence with the observed material family, and fidelity to the requested style. If output texture is blurry, tiled conspicuously, noisy, or conflicts with the observed material identity and requested style, choose refine-code and name a specific procedural-map fix. Style may creatively transform surface detail and finish; do not impose a fixed palette from the style reference.""",
            [
                target,
                folder / "front.png",
                folder / "rear.png",
                folder / "side.png",
                *(
                    [folder / "material-source-vs-albedo.jpg"]
                    if (folder / "material-source-vs-albedo.jpg").exists()
                    else []
                ),
                *styles,
            ],
            6500,
        )
        if styles and (
            not isinstance(review.get("style_score"), (int, float))
            or not 0 <= review["style_score"] <= 1
        ):
            raise NativeBlocked("CRITIC_STYLE_SCORE_MISSING_OR_INVALID")
        if styles and review["action"] == "continue" and review["style_score"] < 0.75:
            review = {
                **review,
                "model_action": review["action"],
                "action": "refine-spec",
                "summary": review["summary"]
                + "; workflow policy: style score below 0.75",
            }
        material_quality = (
            read(self.run / "material-quality.json")
            if (self.run / "material-quality.json").exists()
            else {}
        )
        review = enforce_material_review_policy(
            review, material_quality.get("requires_style_synthesis", False)
        )
        write_json(folder / "features.json", review["features"])
        write_json(folder / "layers.json", review["layers"])
        result = self.bridge.append_review(
            pass_id,
            review,
            folder / "front.png",
            folder / "comparison.png",
            folder / "features.json",
            folder / "layers.json",
        )
        write_json(folder / "append-review.json", result)
        if result["exit_code"]:
            raise NativeBlocked("NATIVE_REVIEW_REJECTED: " + result["stderr"][-1800:])
        self.bridge.mark(
            "ai-review-recorded", [self.run / ("critic-" + pass_id + ".json")]
        )
        return review

    def sync(self, folder, review=None):
        if review is not None:
            pass_id = folder.parent.name
            result = self.bridge.check_pass(pass_id)
            write_json(folder / "pass-unlock-check.json", result)
            unlocked = result["exit_code"] == 0
            if review["action"] == "continue" and not unlocked:
                raise NativeBlocked(
                    "NATIVE_CONTINUE_DID_NOT_UNLOCK_PASS: "
                    + result["stdout"]
                    + result["stderr"]
                )
            if review["action"] != "continue" and unlocked:
                raise NativeBlocked("NATIVE_PASS_UNLOCKED_WITHOUT_CONTINUE_REVIEW")
        record = self.bridge.command(
            "forge/stage3_build/orchestrate_passes.py",
            ["sync", self.run / "object-sculpt-spec.json", "--in-place", "--json"],
        )
        write_json(folder / "pipeline-sync.json", record)
        self.bridge.mark("pipeline-sync", [folder / "pipeline-sync.json"])
        self.bridge.next()

    def deterministic_feedback(self, pass_id, folder, gates):
        eye = read(folder / "divine-eye.json")
        try:
            eye_result = json.loads(eye["stdout"])
            fidelity = float(eye_result["fidelity"])
        except (ValueError, TypeError, KeyError):
            eye_result = {}
            fidelity = 0
        hard_failures = eye_result.get("hardGateFailures", [])
        write_json(
            folder / "correction-loop-input.json",
            [
                {
                    "fidelity": fidelity,
                    "defectTags": [str(item) for item in hard_failures],
                    "reverted": False,
                    "hardGateFailures": hard_failures,
                    "divineEye": {
                        "fidelity": fidelity,
                        "hardGateFailures": hard_failures,
                        "action": eye_result.get("action"),
                        "verdict": eye_result.get("verdict"),
                    },
                }
            ],
        )
        loop = self.bridge.function_gate(
            "loop",
            folder / "correction-loop-input.json",
            folder / "correction-loop.json",
        )
        if loop["exit_code"] not in (0, 1):
            raise NativeBlocked("NATIVE_CORRECTION_LOOP_FAILED: " + loop["stderr"])
        decision = read(folder / "correction-loop.json")
        action = decision.get("action")
        if action not in ("refine-code", "refine-spec", "request-input", "continue"):
            raise NativeBlocked("UNKNOWN_NATIVE_CORRECTION_ACTION")
        summary = (
            "Deterministic failure; AI critic not invoked. Failed: "
            + ",".join(k for k, v in gates.items() if v is False)
            + ". Native correction loop: "
            + str(decision.get("reason", ""))
        )
        diagnosis = self.visual_diagnosis(folder)
        summary += "; visual diagnosis: " + diagnosis.get("summary", "")
        args = [
            self.run / "object-sculpt-spec.json",
            "--pass-id",
            pass_id,
            "--fidelity",
            str(fidelity),
            "--action",
            action,
            "--summary",
            summary,
            "--render-screenshot",
            folder / "front.png",
            "--comparison-image",
            folder / "comparison.png",
            "--in-place",
        ]
        r = self.bridge.command("forge/stage4_review/append_review.py", args)
        write_json(folder / "deterministic-feedback.json", r)
        self.bridge.mark(
            "ai-review-recorded",
            [folder / "deterministic-feedback.json"],
            status="skipped",
            reason="Hard deterministic failure: native contract forbids spending AI vision to grant acceptance.",
        )
        self.sync(folder)
        return {
            "action": action,
            "summary": summary,
            "score": fidelity,
            "visual_diagnosis": diagnosis,
        }

    def visual_diagnosis(self, folder):
        """Give failed renders visual feedback without granting gate acceptance."""
        folder = Path(folder)
        inputs = read(self.run / "inputs.json")
        evidence = (
            load_evidence(inputs["evidence"]["path"])
            if inputs.get("evidence")
            else None
        )
        facts = (
            {
                k: evidence[k]
                for k in (
                    "footprint",
                    "height_m",
                    "frame",
                    "height_source",
                    "footprint_source",
                )
            }
            if evidence
            else {}
        )
        contexts = [Path(v["path"]) for v in inputs.get("context", [])]
        result = self.node(
            "visual-diagnosis-" + folder.parent.name + "-" + folder.name,
            'Diagnose this failed reconstruction to guide its coding node. You cannot accept it or change gate thresholds. Return {"summary":...,"defects":[{"component":...,"observation":...,"cause":...,"code_fix":...,"priority":1..3}],"geometry_constraints":[],"uncertainties":[]}. Compare target, front, top, rear, side, then source context views, then styles. Prioritize connected footprint, wing length/width ratios, axes/handedness, wall height, roof ridges/valleys and facade rhythm. Identify scan gaps as uncertain evidence; do not convert damaged scan walls into giant openings. Explain z-fighting, overly smooth roof normals, duplicate coplanar faces and missing storeys concretely. Style describes finish/detail/light; do not transplant its architecture or force its palette. Preserve OSM metric geometry across views; do not move wings merely to match a camera.\nGEO FACTS: '
            + dump(facts)
            + "\nDIAGNOSTICS: "
            + dump(review_diagnostics(folder)),
            [
                self.run / "target.png",
                *[folder / (v + ".png") for v in ("front", "top", "rear", "side")],
                *contexts,
                *[Path(v["path"]) for v in inputs.get("styles", [])],
            ],
            3000,
        )
        write_json(folder / "visual-diagnosis.json", result)
        return result

    def correct(self, pass_id, folder, review, target, styles):
        spec = read(self.run / "object-sculpt-spec.json")
        if review["action"] == "refine-code":
            source = folder / "createObjectModel.ts"
            write_json(
                self.run / "pending-code-edit.json",
                {
                    "pass_id": pass_id,
                    "source": str(source),
                    "source_digest": digest(source.read_text(encoding="utf-8")),
                    "review": review,
                    "diagnostics": review_diagnostics(folder),
                },
            )
            return
        reports = {
            p.stem: read(p)
            for p in folder.glob("*.json")
            if p.name
            in (
                "tier1.json",
                "gates.json",
                "part-coverage.json",
                "attachment.json",
                "camera-fit.json",
                "geometry-gate.json",
            )
        }
        # Geometry reports can be large: transmit failures/issues, never drop the authoritative file.
        if "geometry-gate" in reports:
            reports["geometry-gate"] = {
                k: v
                for k, v in reports["geometry-gate"].items()
                if k
                in ("passed", "failures", "issues", "triangleCount", "triangleBudget")
            }
        result = self.node(
            "correction-" + pass_id + "-" + folder.name,
            self.bridge.context("spec")
            + "\nSPEC: "
            + dump(spec)
            + "\nFEEDBACK: "
            + dump(review)
            + "\nGATES: "
            + dump(reports)
            + "\nMATERIAL SOURCE QUALITY: "
            + dump(
                read(self.run / "material-quality.json")
                if (self.run / "material-quality.json").exists()
                else {}
            )
            + """\nReturn {"sections":{complete replacements of only affected existing native sections}}. Correct geometry/spec defects; do not change protected review history/thresholds/contracts or erase details. If camera fitting is poor, don't distort geometry to one image; preserve multi-angle consistency and report uncertainty. Code is rebuilt by native factory from your generator-readable geometryDescriptor, localFeatures and materials. Images are target, current front, rear, side, material source-vs-generated contact sheet, then style references. Inspect actual difference. Where raw material regions are undersampled, author a style-aware procedural recipe for the final surface while preserving material identity. Protected keys: """
            + dump(sorted(PROTECTED_SPEC_FIELDS)),
            [
                target,
                folder / "front.png",
                folder / "rear.png",
                folder / "side.png",
                *(
                    [self.run / "material-source-vs-albedo.jpg"]
                    if (self.run / "material-source-vs-albedo.jpg").exists()
                    else []
                ),
                *styles,
            ],
            7500,
        )
        write_json(
            self.run / "object-sculpt-spec.json",
            apply_sections(spec, result["sections"]),
        )
        self.strict_repair(target, styles, max_repairs=1)

    def _execute_native(
        self, reference, styles=(), context_images=(), evidence_path=None
    ):
        try:
            target, styles = self.prepare(
                reference, styles, context_images, evidence_path
            )
            self.strict_repair(target, styles)
            while True:
                self.bridge.next()
                status = self.bridge.status()
                write_json(self.run / "native-status.json", status)
                state = json.loads(status["stdout"])
                pass_id = state["currentPass"]
                if pass_id == "complete":
                    candidates = list(
                        (self.run / "optimization-pass").glob("attempt-*")
                    )
                    if not candidates:
                        raise NativeBlocked("COMPLETE_SPEC_MISSING_RENDER_EVIDENCE")
                    folder = max(candidates, key=lambda p: int(p.name.split("-")[-1]))
                    verify_render_evidence(
                        folder, read(self.run / "object-sculpt-spec.json"), target
                    )
                    break
                if pass_id not in PASSES:
                    raise NativeBlocked("UNKNOWN_NATIVE_PASS")
                folder, gates = self.render_gates(pass_id, target)
                if gates.get("browser_runtime_error"):
                    repair_file = self.run / "browser-runtime-repairs.json"
                    repairs = (
                        read(repair_file)
                        if repair_file.exists()
                        else {"count": 0, "attempts": []}
                    )
                    repairs["count"] += 1
                    repairs["attempts"].append(
                        {
                            "pass_id": pass_id,
                            "folder": folder.name,
                            "error": gates["browser_runtime_error"],
                        }
                    )
                    write_json(repair_file, repairs)
                    if repairs["count"] > 2:
                        raise NativeBlocked(
                            "BROWSER_RUNTIME_REPAIR_LIMIT: "
                            + gates["browser_runtime_error"]
                        )
                    self.correct(
                        pass_id,
                        folder,
                        {
                            "action": "refine-code",
                            "summary": "Browser runtime failed before review: "
                            + gates["browser_runtime_error"],
                        },
                        target,
                        styles,
                    )
                    continue
                if gates.get("full_native_gates") is True:
                    review = self.critic(pass_id, folder, target, styles)
                    self.sync(folder, review)
                else:
                    review = self.deterministic_feedback(pass_id, folder, gates)
                if review["action"] in ("stop", "request-input"):
                    raise NativeBlocked(
                        "CRITIC_" + review["action"].upper() + ": " + review["summary"]
                    )
                if review["action"] != "continue":
                    self.correct(pass_id, folder, review, target, styles)
            self.bridge.mark("part-coverage", [folder / "part-coverage.json"])
            self.bridge.mark("action-ready", [folder / "render-manifest.json"])
            self.bridge.command(
                "forge/stage3_build/emit_target.py",
                [
                    "--spec",
                    self.run / "object-sculpt-spec.json",
                    "--workspace",
                    self.run,
                    "--target",
                    "threejs-ts",
                ],
            )
            plugins = self.bridge.command(
                "forge/stage3_build/run_gates.py", ["--workspace", self.run]
            )
            write_json(self.run / "plugin-gates.json", plugins)
            self.bridge.mark("plugin-gates", [self.run / "plugin-gates.json"])
            self.bridge.next()
            result = {
                "accepted": True,
                "status": "complete",
                "model": self.settings.model,
                "seconds": round(time.monotonic() - self.started, 2),
                "usage": self.provider.usage,
            }
            write_json(self.run / "result.json", result)
            return result
        except Exception as exc:
            result = {
                "accepted": False,
                "status": "blocked",
                "reason": str(exc),
                "model": self.settings.model,
                "seconds": round(time.monotonic() - self.started, 2),
                "usage": self.provider.usage,
            }
            write_json(self.run / "result.json", result)
            self.ledger.event("workflow", "blocked", reason=str(exc))
            return result
        return {"accepted": False, "status": "pending"}

    def run_native(self, reference, styles=(), context_images=(), evidence_path=None):
        with run_lock(self.run):
            return self._execute_native(
                reference, styles, context_images, evidence_path
            )
