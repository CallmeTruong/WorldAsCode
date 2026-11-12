# Implementation plan: scene-informed Tokyo block

Date: 2026-11-12. User authorized documentation, research, Spec Kit updates and implementation. See [scene revision](scene-revision.md) and [research protocol](../../reports/urban/scene-research-protocol.md).

1. Record root causes, competing approaches, executable contracts and separate visual acceptance criteria.
2. Add a scene-reference manifest, common scene observation and cached per-object local code modules. Keep old urban mode reproducible.
3. Enforce host-owned placement, complete object IDs and surface bindings. Capture full camera metadata for new references.
4. Preserve factual surface identities; implement material/detail guidance and style review using actual reference images. Ground textures remain evidence-labeled substitutes where no exact source exists.
5. Run a bounded 120 m Tokyo experiment with all buildings included, inspect images and apply bounded evidence-driven fixes.
6. Run regressions, record failures/usage/remaining uncertainty, update quickstart and selected artifacts.

Python/LangGraph orchestrates trusted provider and artifact operations. Generated Three.js remains synchronous, deterministic, network-denied and resource-bounded. Shared roads use canonical area geometry and tree anchors remain fixed under reseeding. Existing dependencies suffice. Native img2threejs full staged equivalence, photo baking and city streaming remain separate unfinished capabilities.
