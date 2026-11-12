Current approach: measured geographic evidence supplies the building frame; an agent writes a short Three.js design using an architectural kit and a flexible style reference. Start with [the current method](workflow_scale_research/docs/00-phuong-phap-hien-tai.md) and [setup instructions](workflow_scale_research/README.md). The latest single-building pilot remains unaccepted by the visual critic. Earlier experiments below are retained as research history.

Active research AOI: Tokyo Marunouchi (220 m). Google/Cesium multi-view coverage is verified for this AOI. See [Tokyo findings](workflow_research/reports/urban/tokyo-findings.md) and [Spec Kit tasks](workflow_research/specs/002-urban-grid-style/tasks.md). Earlier District 1 results below are retained for comparison.

# WorldAsCode

Research workflow for procedural urban scenes from geographic data, optional per-object photographs and a flexible style-reference folder.

The District 1 workflow now uses descriptive style guidance and preserves each object's own materials. Start with the [workflow README](workflow_research/README.md), [quality correction results](workflow_research/reports/urban/quality-correction-results.md), [visual report](workflow_research/runs/urban/district1-quality-v10/index.html) and [Spec Kit 002](workflow_research/specs/002-urban-grid-style/spec.md).

The selected 220 m scene has three buildings with individual photographic part analysis and eight explicit context proxies. It includes per-object render/review and bounded refinement, but visual fidelity remains partial. The local viewer supports presentation comparison, orbit/zoom and object selection. Runtime cell streaming, large-area benchmarks and the complete native eight-pass img2threejs baseline remain pending.

See [quickstart](workflow_research/specs/002-urban-grid-style/quickstart.md) for execution and local viewing. Credentials stay in `.env`, outside viewer assets.
