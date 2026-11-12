Current scene-mode commands and measured limitations: [implementation results](../../reports/urban/scene-implementation-results.md#inspect-and-reproduce).

> Active implementation revision: [scene reconstruction](scene-revision.md). Earlier scope/status statements below are historical where they conflict with this revision.

# Run the District 1 urban style pilot

> Current selected result: `district1-quality-v10` (220 m AOI, 3 photo-backed targets and 8 context proxies). Descriptive style preserves native materials; fidelity remains partial. See [quality correction results](../../reports/urban/quality-correction-results.md). Earlier v4/palette/36-building statements below are historical and superseded.

Current quality revision: [descriptive style and per-object evidence](quality-revision.md). Use a fresh run ID with the new implementation; old runs remain comparison evidence. The earlier 400 m prototype instructions below are historical context.

```powershell
.venv/Scripts/python -m building_workflow.cli urban --style-dir inputs/style-references/user-isometric --object-refs inputs/object-references/cluster-manifest.json --run-id my-quality-cluster --size 220 --longitude 106.7032 --latitude 10.7763 --grid 2 --max-calls 18 --max-tokens 240000 --max-seconds 2400 --max-visual-refinements 1
```

Style output is descriptive prose. Lighting experiment values are saved separately. Original material colors/slots/PBR maps survive presentation switches. Each observed object has its own part plan, source, front/overhead render and quality review. Unknown neighbors are explicitly proxies. Overhead renders and footprint diagrams are not factual aerial photos. A review with major defects cannot mark the object visually accepted.

Input, image bytes and implementation hashes are frozen per run. Changing them requires a new run ID. `--size`, `--longitude`, `--latitude`, `--grid` configure the AOI; the saved OSM snapshot still constrains actual source coverage. Arbitrary global-area data ingestion/terrain and lane/intersection reconstruction remain future work.

For an implementation-only bug fix, `--resume-code-update` archives the previous implementation hash and permits resuming unchanged inputs/config/budgets. Changed photographs, AOI or budgets still require a fresh run ID. This option does not replenish used attempts or tokens. View the selected existing result at <http://127.0.0.1:8765/district1-quality-v10/viewer.html>; serving it makes no model calls. The final run includes reuse of already observed/generated modules, so its API usage is not cold-start cost.

Status, 2026-11-12: implemented research prototype; visual fidelity remains **partial**. Selected evidence: `district1-final-v4`. The later `district1-roof-v5` is retained as an unsuccessful roof refinement.

From `D:\WorldAsCode\workflow_research`, after installing dependencies from the project README:

```powershell
.venv/Scripts/python -m building_workflow.cli urban --help
.venv/Scripts/python -m building_workflow.cli urban --style-dir inputs/style-references/user-isometric --object-refs inputs/object-references/manifest.json --run-id district1-new --max-calls 12 --max-tokens 180000 --max-seconds 2400
```

The original user attachment is `inputs/style-references/user-isometric/reference.png`. Supply another folder of 1–20 PNG/JPEG/WebP images to change references. The vision model extracts a profile; the implementation does not fix the user's palette. Style guidance is separate from factual object photographs and OSM geometry. It does not automatically recover photo textures or detailed geometry from a style image.

The AOI is currently fixed in the adapter: 400 × 400 m near 10.775 N, 106.702 E, four 200 m cells. OSM snapshot: `../docs/research/`. General AOI/continuous ingestion is future work. Object references map stable OSM-derived IDs to photos in a manifest.

Credentials are read from `../.env`. Each run saves bounded usage, SQLite checkpoint, prompts/responses/source, checks, images and review. An unchanged completed run ID returns saved results. Use a new ID for changed configuration. `--reuse-run-id <id>` reuses parameterized source, without fresh per-object inference. `--rerender` re-enters stages and can call review; it is not a zero-cost render-only command.

View existing results without model calls:

```powershell
.venv/Scripts/python -m http.server 8765 --bind 127.0.0.1 --directory runs/urban
```

Open <http://127.0.0.1:8765/district1-final-v4/viewer.html>. Orbit, zoom, switch style, toggle layers, or select Object detail. Static report: `runs/urban/district1-final-v4/index.html`.

```powershell
.venv/Scripts/python -m pytest -q
.venv/Scripts/python .specify/scripts/python/check_prerequisites.py --json --require-spec --require-tasks
```

Read [findings](../../reports/urban/findings.md), [validation](../../reports/urban/validation.md) and [tasks](tasks.md). Current limits: 32/36 heights inferred; only 1/36 buildings has factual photo analysis; streetscape includes inferred placements; flat ground; no runtime cell streaming/LOD. Cesium readiness was probed separately; this viewer does not stream Cesium or Google tiles.
