"""Host-owned regional shells; authors supply bounded appearance and details."""

import json
from typing import Literal

from pydantic import Field

from worldascode.contracts.region import Strict
from worldascode.geometry.massing import Appearance, BuildingProgram, Roof
from worldascode.kits.code import lint


class BuildingDetails(Strict):
    roof_form: Literal["flat", "hip", "gable", "mansard"] | None = None
    bay_m: float = Field(default=3.2, gt=0.8, le=12)
    windows: bool = False
    window_width: float = Field(default=0.42, gt=0.05, lt=0.95)
    window_height: float = Field(default=0.55, gt=0.05, lt=0.95)
    wall: str = Field(default="#9a8f84", pattern=r"^#[0-9a-fA-F]{6}$")
    roof: str = Field(default="#5c6470", pattern=r"^#[0-9a-fA-F]{6}$")
    trim: str = Field(default="#d8d2c4", pattern=r"^#[0-9a-fA-F]{6}$")
    glass: str = Field(default="#2f3d48", pattern=r"^#[0-9a-fA-F]{6}$")
    evidence_ids: list[str] = Field(default_factory=list, max_length=16)
    uncertainty: list[str] = Field(default_factory=list, max_length=20)


def building_program(entity, details):
    """Reuse the massing programme contract while keeping spatial facts host-owned."""
    fitted = entity.facts.get("massing_program")
    form = details.roof_form or entity.site()["roof"]["form"]
    if fitted:
        measured = BuildingProgram.model_validate(fitted)
        if details.roof_form and details.roof_form != measured.roof.form:
            raise ValueError("FITTED_ROOF_FORM_IS_HOST_OWNED")
        form = measured.roof.form
    rise = max(0, entity.ridge_m - entity.eave_m)
    if form != "flat" and rise <= 0:
        raise ValueError("SLOPED_ROOF_REQUIRES_HOST_RIDGE_ABOVE_EAVE")
    return BuildingProgram(
        eave_height=entity.eave_m,
        roof=Roof(form=form, rise=rise),
        storeys=entity.storeys,
        bay_m=details.bay_m,
        window_width=details.window_width,
        window_height=details.window_height,
        cornice=False,
        appearance=Appearance(
            wall=details.wall,
            roof=details.roof,
            trim=details.trim,
            glass=details.glass,
            source="author estimate; see evidence_ids and uncertainty in building-details.json",
        ),
        provenance={
            "footprint": str(
                entity.facts.get("sources", {}).get("footprint", "registry")
            ),
            "height": str(
                entity.facts.get("sources", {}).get(
                    "height", "registry; accuracy unverified"
                )
            ),
        },
    )


def compile_building(entity, details=None, detail_code=None):
    details = BuildingDetails.model_validate(details or {})
    if not details.evidence_ids and not details.uncertainty:
        details = details.model_copy(
            update={
                "uncertainty": [
                    "Appearance is an estimate without cited source evidence."
                ]
            }
        )
    program = building_program(entity, details)
    spec = details.model_dump(mode="json")
    # Detail code receives no shell handles or shell constructors. The compiled
    # script remains a normal design module, so saved runs stay self-contained.
    extension = ""
    if detail_code:
        errors = lint(detail_code)
        if errors:
            raise ValueError("INVALID_BUILDING_DETAIL_CODE: " + "; ".join(errors))
        extension = detail_code.replace(
            "export function design(", "function detail(", 1
        )
        extension += "\ndetail(site,Object.freeze(Object.fromEntries(Object.entries(b).filter(([k])=>!['walls','roof','roofPlanes'].includes(k)))),style);"
    source = (
        "export function design(site,b,style){\n"
        f"const spec={json.dumps(spec)};\n"
        "b.material('__shell_wall',{color:spec.wall});\n"
        "b.material('__shell_roof',{color:spec.roof});\n"
        "b.material('__shell_trim',{color:spec.trim});\n"
        "b.material('__shell_glass',{color:spec.glass});\n"
        "b.walls({height:site.eave_m,storeys:site.storeys,material:'__shell_wall',"
        "windows:spec.windows,bay:spec.bay_m,window:{w:spec.window_width,h:spec.window_height,"
        "glass:'__shell_glass',frame:'__shell_trim'}});\n"
        f"b.roof({{material:'__shell_roof',form:{json.dumps(program.roof.form)},"
        "rise:Math.max(0,site.ridge_m-site.eave_m),overhang:0,parapet:Math.max(0.02,site.ridge_m-site.eave_m)});\n"
        + extension
        + "\n}\n"
    )
    return source, {
        "details": spec,
        "program": program.model_dump(mode="json"),
        "detail_code": detail_code,
    }


def baseline_scripts(region):
    scripts, plans = {}, {}
    for entity in region.entities:
        if entity.kind == "building":
            scripts[entity.id], plans[entity.id] = compile_building(
                entity,
                {
                    "uncertainty": [
                        "Registry shell only; appearance has not been observed."
                    ]
                },
            )
        else:
            bounds = entity.bounds
            centre = [(a + b) / 2 for a, b in zip(bounds.min, bounds.max)]
            size = [b - a for a, b in zip(bounds.min, bounds.max)]
            scripts[entity.id] = (
                "export function design(site,b){b.material('__prior',{color:'#999999'});"
                f"b.box(b.at({centre[0]},{centre[2]}),"
                + json.dumps(
                    dict(
                        w=size[0],
                        h=size[1],
                        d=size[2],
                        y=bounds.min[1],
                        material="__prior",
                    )
                )
                + ");}"
            )
    return scripts, plans


def compile_changes(region, changes, plans, evidence_ids):
    """Validate building parameters before compiling; non-buildings keep their kit API."""
    if not isinstance(changes, list):
        raise ValueError("ENTITY_CHANGES_REQUIRED")
    compiled, updated = [], dict(plans)
    for change in changes:
        entity = region.index().get(change.get("entity_id"))
        if entity is None:
            raise ValueError("UNKNOWN_ENTITY_CHANGE")
        if entity.kind != "building":
            compiled.append(change)
            continue
        if "building" not in change:
            raise ValueError(
                "BUILDING_PARAMETERS_REQUIRED: use building plus optional detail_code; host builds walls/roof"
            )
        previous = plans.get(entity.id, {})
        if not isinstance(change["building"], dict):
            raise ValueError("BUILDING_PARAMETERS_REQUIRE_OBJECT")
        details = BuildingDetails.model_validate(
            {**previous.get("details", {}), **change["building"]}
        )
        if not set(details.evidence_ids) <= set(evidence_ids):
            raise ValueError("BUILDING_DETAIL_UNKNOWN_EVIDENCE")
        code, plan = compile_building(
            entity,
            details.model_dump(),
            change.get("detail_code", previous.get("detail_code")),
        )
        updated[entity.id] = plan
        compiled.append({"entity_id": entity.id, "code": code})
    return compiled, updated


def run_baseline(region, run, massing_evidence=None):
    """Render a complete registry without a model, source viewer or quality claim."""
    from pathlib import Path

    from worldascode.adapters.rendering.browser import render_region
    from worldascode.contracts.region import Region
    from worldascode.storage.artifacts import write_json

    region = Region.model_validate(region) if isinstance(region, dict) else region
    from worldascode.evidence.region_massing import fit_region_massing

    region, fit = fit_region_massing(region, massing_evidence or {})
    run = Path(run).resolve()
    run.mkdir(parents=True, exist_ok=False)
    scripts, plans = baseline_scripts(region)
    write_json(run / "region.json", region.model_dump(mode="json"))
    write_json(run / "massing-fit.json", fit)
    write_json(run / "building-details.json", plans)
    write_json(
        run / "priors.json",
        {
            e.id: {
                "sources": e.facts.get("sources", {}),
                "appearance": "unobserved",
                "representation": "registry shell"
                if e.kind == "building"
                else "bounds proxy",
            }
            for e in region.entities
        },
    )
    metrics, error = render_region(run / "baseline", scripts, region, {}, [], [])
    result = {
        "status": "region-baseline",
        "execution_status": "failed" if error else "completed",
        "accepted": False,
        "quality_status": "unreviewed",
        "selection_status": "retained" if metrics else "none",
        "selected_render": str(run / "baseline") if metrics else None,
        "metrics": metrics,
        "error": error,
    }
    write_json(run / "result.json", result)
    return result
