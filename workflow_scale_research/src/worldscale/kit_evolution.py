"""Isolated, bounded kit development. Models propose; measured gates activate."""

import json
import re
import shutil
import subprocess
from pathlib import Path

from .artifacts import digest, file_hash, write_json
from .config import ROOT
from .kit_context import METHOD, context, methods
from .patches import text_edits

PATCHABLE = {"roof", "roofY", "gable", "dormer", "window", "turret", "chimney", "material"}
FORBIDDEN = re.compile(r"\b(?:import|require|fetch|XMLHttpRequest|WebSocket|eval|Function|globalThis|navigator|localStorage|setTimeout|setInterval)\b|(?<![\w.])window\s*[.\[]")
PROTECTED_ACCESS = re.compile(r"\b(?:wallGuard|__proto__|prototype|constructor)\b|this\.(?:walls|finish|counts)\b")


def editable_methods(source):
    """Allow a released extension's implementation to evolve with its API.

    Core helpers remain protected; only new helpers reachable from an allowed
    domain method can be granted by triage, never arbitrary Builder methods.
    """
    blocks=methods(source)
    core={'_add','_material','_world','_box','_prism','_loft','_edgeFrame','_facadeMaterial'}
    permitted=set(PATCHABLE)
    while True:
        called=set(re.findall(r'this\.(_\w+)\(', '\n'.join(blocks.get(k,'') for k in permitted)))
        called=(called&blocks.keys())-core
        if called<=permitted:
            return permitted
        permitted.update(called)


def protected_projection(source, editable, additions=()):
    blocks = methods(source)
    for name in editable:
        if name in blocks:
            source = source.replace(blocks[name], f"  @editable:{name}@\n", 1)
    for name in additions:
        if name in blocks:
            source = source.replace(blocks[name], '', 1)
    return '\n'.join(line.rstrip() for line in source.splitlines() if line.strip())


def apply_proposal(source, proposal, editable):
    editable = set(editable)
    if not editable or not editable <= editable_methods(source):
        raise ValueError("KIT_PERMISSION_DENIED")
    edits = proposal.get('edits', [])
    additions = proposal.get('new_methods', [])
    if not isinstance(edits, list) or not isinstance(additions, list) or len(additions) > 3:
        raise ValueError("INVALID_KIT_PROPOSAL")
    original = methods(source)
    for edit in edits:
        if not any(edit.get('find', '') and edit['find'] in original.get(name, '') for name in editable):
            raise ValueError("KIT_PATCH_OUTSIDE_GRANTED_METHODS")
        if FORBIDDEN.search(edit.get('replace', '')) or PROTECTED_ACCESS.search(edit.get('replace', '')):
            raise ValueError("KIT_FORBIDDEN_CAPABILITY")
    updated = text_edits(source, edits, digest(source))
    names = []
    for item in additions:
        name, code = item['name'], item['code']
        if not re.fullmatch(r'[A-Za-z_]\w*', name) or name in original or name in names:
            raise ValueError("KIT_INVALID_NEW_METHOD")
        if FORBIDDEN.search(code) or PROTECTED_ACCESS.search(code) or not code.startswith('  ' + name + '('):
            raise ValueError("KIT_FORBIDDEN_NEW_METHOD")
        # Only one new method per declared capability; no class/global edits.
        parsed = list(METHOD.finditer(code))
        if len(parsed) != 1 or parsed[0].group(1) != name:
            raise ValueError("KIT_NEW_METHOD_DECLARATION_MISMATCH")
        updated = updated.replace('  finish() {', code.rstrip() + '\n  finish() {', 1)
        names.append(name)
    if protected_projection(source, editable) != protected_projection(updated, editable, names):
        raise ValueError("KIT_PROTECTED_CODE_CHANGED")
    if len(updated) > 85000:
        raise ValueError("KIT_CANDIDATE_TOO_LARGE")
    return updated, names


def snapshot(folder, source_folder=None):
    """Restore actual bundled runtime when available; otherwise snapshot current source."""
    folder = Path(folder)
    if source_folder is None and (ROOT/'kit_library/registry.json').exists():
        from .kit_library import Library

        return Library().pin(folder)
    folder.mkdir(parents=True, exist_ok=False)
    for path in (ROOT / 'runtime').glob('*.mjs'):
        shutil.copy2(path, folder / path.name)
    mapping = Path(source_folder) / 'bundle.js.map' if source_folder else None
    if mapping and mapping.is_file():
        payload = json.loads(mapping.read_text(encoding='utf-8'))
        for path, content in zip(payload['sources'], payload['sourcesContent'], strict=True):
            name = Path(path).name
            if name in {'kit.mjs', 'surfaces.mjs', 'roof-openings.mjs'} and content is not None:
                (folder / name).write_text(content, encoding='utf-8')
    shutil.copy2(ROOT / 'runtime/kit-api.md', folder / 'kit-api.md')
    shutil.copy2(ROOT / 'runtime/capabilities.json', folder / 'capabilities.json')
    write_json(folder / 'version.json', {'state': 'pinned', 'modules': {p.name: file_hash(p) for p in folder.glob('*.mjs')}})
    return folder / 'kit.mjs'


def propose(provider, folder, base_kit, history, images, site):
    folder, base_kit = Path(folder), Path(base_kit)
    folder.mkdir(parents=True, exist_ok=False)
    source = base_kit.read_text(encoding='utf-8')
    permitted=editable_methods(source)
    words=json.dumps(history).lower()
    relevant=[name for name in ('roof','gable','dormer','window','turret','chimney','material') if re.search(r'\b'+name+r's?\b',words)][:3]
    implementation={name:methods(source)[name] for name in relevant}
    if 'roof' in relevant:
        implementation['roofY']=methods(source)['roofY']
    known_helpers={'_add','_material','_loft','_box','_prism','_world','_facadeMaterial','_edgeFrame'}
    referenced=set(re.findall(r'this\.(_\w+)\(', '\n'.join(implementation.values())))-known_helpers
    implementation.update({name:methods(source)[name] for name in referenced if name in methods(source)})
    version_path=base_kit.parent/'version.json'
    version=json.loads(version_path.read_text(encoding='utf-8')) if version_path.exists() else {}
    plan = provider.call('kit-gap-' + folder.name,
        'Triage rejected 3D designs. Return {"action":"develop-kit|fix-design|need-evidence", "reason":..., "capability":..., "methods":[up to 3 existing method names], "tests":[concrete geometry/visual requirements]}. Only request kit development when the API/implementation cannot express the observed architecture or repeated output defects prove a library bug. Existing permitted methods: '
        + json.dumps(sorted(permitted)) + '. The wall footprint, measured heights, camera, style and quality thresholds are protected. Never develop a Tokyo-specific primitive. Distinguish a real missing geometric capability from incorrect usage or uncertain scan data.\nHISTORY: '
        + json.dumps(history) + '\nSITE: ' + json.dumps(site)
        + '\nDECLARED CAPABILITIES (missing means not implemented, not a parameter issue): ' + (base_kit.parent/'capabilities.json').read_text(encoding='utf-8')
        + '\nRELEVANT ACTUAL IMPLEMENTATION: ' + json.dumps(implementation)
        + '\nPINNED VERSION EXTENSIONS: '+json.dumps(version)
        + '\nThe capability catalog can describe an older base version: its missing status must not override actual methods and extensions present in this pinned version. Do not repeatedly rebuild an operation already implemented by a versioned helper.'
        + '\nRepeated failures across designs can justify a reusable kit capability even though arbitrary custom geometry is technically possible. Do not ask to implement an operation already present; identify what its current implementation cannot express. Historical versions may differ from this pinned source.'
        + '\nRELEVANT API: ' + context(base_kit.parent/'kit-api.md',site,feedback=history,method_names=relevant)['text'], images, 1800)
    write_json(folder / 'triage.json', plan)
    if plan.get('action') != 'develop-kit':
        write_json(folder / 'decision.json', {'activated': False, 'status': plan.get('action'), 'reason': plan.get('reason')})
        return None
    granted = set(plan.get('methods', []))
    if not granted or len(granted) > 3 or not granted <= permitted:
        raise ValueError('INVALID_KIT_PERMISSION_GRANT')
    selected = {name: methods(source)[name] for name in granted}
    # Progressive disclosure: only granted source methods, API docs and the
    # request are disclosed. The model never receives secrets or release tools.
    proposal = provider.call('kit-developer-' + folder.name,
        'Develop a reusable architecture-kit improvement. Return {"summary":..., "edits":[{"find":exact unique substring, "replace":JavaScript}], "new_methods":[{"name":newMethodName,"code":"  newMethodName(frame,o={}) { ... }"}], "exercise":{"method":newOrChangedPublicMethod,"options":{parameters enabling the new capability}}, "api_notes": short Markdown usage, "test_notes":...}. The exercise is a declarative options-only roof construction call run after measured walls on a rectangle, L plan and rotated rectangle. It MUST activate the new feature, not just test the old default. All roof geometry needs metric UVs and must stay within the measured footprint plus declared overhang. this.plan is [east,NORTH]; emitted mesh vertices are [east,UP,SOUTH], so negate NORTH to get Z. You may edit ONLY the supplied existing methods. You may add at most 3 reusable methods to Builder. No imports, network, browser globals, timers, eval or changes to measured walls/frames/guards/API wrapper. Only Three.js and Builder helpers. Units metres, X east/Y up/Z south. Never name a place or object id in implementation. Avoid style palettes or hardcoded architectural layouts. Build true volume/roof continuity, not camera-dependent silhouettes. New public methods are automatically exposed by the existing API. All edits must preserve old signatures and defaults. Available helpers: this._material(id), this._add(object,type,frame), this._world(frame,x,z), this._box(w,h,d,x,y,z,mat), this._prism(profile,depth,mat), this._loft(rings,mat), this.roofY(x,z), this.plan, this.edges, this.roofMesh, this.roofProfile, this.wallTop, this.site; imports already available: THREE, metricUVs, cutRoofOpening, mergeGeometries. Do not call private helpers that are not listed.\nREQUEST: '
        + json.dumps(plan) + '\nGRANTED SOURCE METHODS: ' + json.dumps(selected)
        + '\nLATEST REJECTED PROPOSAL AND EXECUTED TEST DIAGNOSTICS: '
        + json.dumps(next((item for item in reversed(history) if item.get('kit_failure')), None))
        + '\nCorrect that proposal using the diagnostics when available; edits still apply against the GRANTED SOURCE METHODS above, not against the rejected candidate. Never repeat fixed scene coordinates or an unexercised path.'
        + '\nExercise contract: fixtures declare materials brick and glass; use material="brick", never a placeholder id. Fixture dimensions vary: do not use fixed coordinates tuned to one footprint. If your API needs explicit wing polygons, use wings: {"$fixture":"wing-corners"} in exercise.options. The harness replaces that declarative marker with an array of {corners:[[east,south],...]} rectangular wings covering each footprint, with correct rotation. Implement your API to accept that documented corners schema; this marker is ONLY harness input, not part of the kit. Otherwise derive geometry from this.plan. Optional signature is options (default), frame-options, or material; optional phase is roof (replaces host roof) or part (adds after host roof).'
        + '\nInclude requires_design_update:true if using the improvement needs new options or a new call. Use false only for a backwards-compatible internal fix already exercised by the unchanged original design.'
        + '\nFormatting contract: method declarations start with exactly two spaces; method bodies use at least four spaces. Prefer replacing a complete supplied method when short snippets would not be globally unique. Keep braces inside each method balanced.'
        + '\nRELEVANT API: ' + context(base_kit.parent/'kit-api.md',method_names=granted)['text'], images, 9000)
    write_json(folder / 'proposal.json', proposal)
    try:
        changed, additions = apply_proposal(source, proposal, granted)
        exercise=proposal.get('exercise')
        if not isinstance(exercise,dict) or exercise.get('method') not in (granted|set(additions)) or not isinstance(exercise.get('options',{}),dict):
            raise ValueError('KIT_NEW_CAPABILITY_EXERCISE_REQUIRED')
        if exercise.get('signature','options') not in ('options','frame-options','material') or exercise.get('phase','roof') not in ('roof','part'):
            raise ValueError('KIT_INVALID_EXERCISE_SIGNATURE')
        json.dumps(exercise,allow_nan=False)
        write_json(folder/'exercise.json',exercise)
        candidate = folder / 'runtime'
        shutil.copytree(base_kit.parent, candidate)
        (candidate / 'kit.mjs').write_text(changed, encoding='utf-8')
        write_json(candidate / 'version.json', {'state':'candidate','base_sha256':file_hash(base_kit),
                   'kit_sha256':file_hash(candidate/'kit.mjs'),'capability':plan.get('capability'),
                   'modules':{p.name:file_hash(p) for p in candidate.glob('*.mjs')}})
        with (candidate / 'kit-api.md').open('a', encoding='utf-8') as stream:
            stream.write('\n\n## Candidate capability\n' + str(proposal.get('api_notes', '')) + '\n')
        check = subprocess.run(['node', '--check', str(candidate / 'kit.mjs')], capture_output=True, text=True, timeout=30)
        write_json(folder / 'syntax.json', {'passed': check.returncode == 0, 'stderr': check.stderr})
        if check.returncode:
            raise ValueError('KIT_SYNTAX_FAILED')
        write_json(folder / 'permissions.json', {'granted_methods': sorted(granted), 'added_methods': additions,
            'consumer_required':bool(additions) or proposal.get('requires_design_update',True) is not False,
            'base_sha256': file_hash(base_kit), 'candidate_sha256': file_hash(candidate / 'kit.mjs'),
            'protected_projection_unchanged': True, 'shared_runtime_written': False})
        return candidate / 'kit.mjs'
    except (ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        write_json(folder / 'decision.json', {'activated': False, 'status': 'proposal-rejected', 'reason': str(exc)})
        return None


def activation_decision(before_metrics, after_metrics, before_scores, after_scores, regressions):
    regression_ok = bool(regressions) and all(r.get('passed') is True for r in regressions)
    likeness_ok = after_scores['likeness'] >= before_scores['likeness'] - .02
    metric_ok = after_metrics['passed'] and after_metrics['mean_oblique_iou'] >= before_metrics['mean_oblique_iou'] - .025
    weakest_gain = min(after_scores.values()) - min(before_scores.values())
    checks = {'regressions': regression_ok, 'metrics': metric_ok, 'likeness': likeness_ok,
              'balanced_visual_gain': weakest_gain >= .03,
              'other_quality_preserved':all(after_scores[k]>=before_scores[k]-.03 for k in ('style','detail'))}
    return {'activated': all(checks.values()), 'checks': checks, 'weakest_score_gain': round(weakest_gain, 4),
            'scope': 'this run only; not a global kit release', 'human_review': False}


def copy_active_version(manifest, destination):
    record=json.loads(Path(manifest).read_text(encoding='utf-8'))
    kit=Path(record['path'])
    if record.get('scope')!='run-local' or file_hash(kit)!=record['sha256'] or not record.get('modules'):
        raise ValueError('KIT_VERSION_NOT_VERIFIED')
    validation=Path(record.get('validation_path',kit.parent.parent/'decision.json'))
    if not validation.is_file() or file_hash(validation)!=record.get('validation_sha256'):
        raise ValueError('KIT_VERSION_VALIDATION_MISMATCH')
    decision=json.loads(validation.read_text(encoding='utf-8'))
    if decision.get('activated') is not True or decision.get('candidate_sha256')!=record['sha256']:
        raise ValueError('KIT_VERSION_NOT_ACTIVATED')
    if set(record['modules'])!={p.name for p in kit.parent.glob('*.mjs')}:
        raise ValueError('KIT_VERSION_MODULE_MISMATCH')
    for name,expected in record['modules'].items():
        if Path(name).name!=name or file_hash(kit.parent/name)!=expected:
            raise ValueError('KIT_VERSION_MODULE_MISMATCH')
    shutil.copytree(kit.parent,destination)
    return Path(destination)/'kit.mjs'
