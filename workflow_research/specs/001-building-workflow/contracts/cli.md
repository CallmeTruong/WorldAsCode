# CLI Contract

Run from workflow_research using `.venv/Scripts/python -m building_workflow.cli`.

- `doctor`: verify safe configuration, provider model list, pinned upstream and browser. Never print credentials.
- `samples`: download finite public references and write `data/samples.json` with attribution/checksums. Existing verified samples are retained.
- `run --sample ID --strategy direct|spec --max-refinements 1 [--run-id ID]`: execute bounded graph. Defaults 12 calls, 100000 tokens, 900 seconds. Existing run id resumes only pending checkpoint, never silently replaces unrelated config.
- `run ... --refinement-scope camera`: isolate camera corrections from geometry as a controlled experiment; default remains targeted code correction.
- `render SOURCE OUTPUT [--camera FILE]`: execute saved factory and render without model calls. Reuses adjacent camera.json by default.
- `report`: rebuild aggregate local report from saved runs.

Generated factory contract: `import * as THREE from 'three'; export function build(params = {}) { return rootGroup; }`. Y up, front +Z, ground y=0. Use named parts and reusable functions/loops. External imports, dynamic imports, globals with host effects, texture/network loading and environment access forbidden. Source is compiled as TypeScript, transformed/bundled then executed ONLY inside a network-denied sandboxed browser worker. Trusted host validates emitted scene and topology before rendering.

Refinement contract: JSON `{edits:[{old:string,new:string}],reason:string}`; old must occur exactly once, source size bounded, every changed source rerendered. Full regeneration is a separate research strategy, not an implicit fallback.

Review contract: six bounded feature scores, critical_defects list, defects (component, severity, cause, fix), matched_features, inferred_regions, confidence. Single-image output is always partial regardless of scores.

Artifacts: `config.json`, `reference.jpg`, `spec.json`, `trace.jsonl`, `usage.json`, `checkpoint.sqlite`, `iteration-NN/{generator.ts,scene.json,geometry.json,front.png,back.png,left.png,right.png,isometric.png,reference-view.png,comparison.jpg,review.json}`, `result.json`, `index.html`, upstream state and gate evidence. Errors include code, stage, evidence and recovery.
