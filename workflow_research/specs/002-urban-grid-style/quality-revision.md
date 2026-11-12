# Quality revision: descriptive style and evidence-backed objects

Authorized by the user's request to fix the quality audit, 2026-11-12. This revision supersedes the earlier palette/material-only style contracts.

## Required behavior

- Style extraction outputs flexible prose: artistic intent, form/detail, surface expression, lighting/composition, evidence and uncertainty. No required RGB palette or closed catalog of artistic styles. The description can guide object modeling without overriding its factual identity.
- Numeric lighting experiments live separately in `presentation-settings.json`; they cannot prescribe object colors, textures or material identities. Native material names/slots are extensible. Neutral/reference presentation must preserve actual geometry and material fingerprints.
- Texture bindings belong to individual material surfaces, not whole-building style roles. Trusted PBR assets retain color, normal and roughness maps; physical-scale mapping must account for mesh/instance transforms. Map color space remains explicit.
- AOI center, size and grid are configurable. A smaller cluster is the quality experiment, rather than a claim of high-fidelity reconstruction over 36 unobserved buildings. Unknown context remains clearly labeled proxies.
- Every photo-backed object gets a factual part plan, source module, dedicated front/top renders, factual comparison and issue list. Footprint diagrams are explicitly map-derived, not aerial photos. Roof/height evidence conflicts and unknown backs are disclosed.
- At least one bounded visual repair cycle may act on specific geometry/material defects and re-render/re-review. Runtime-valid and visually accepted are distinct states. Major unresolved identity issues block visual acceptance.
- Factual image content, source and relevant object/asset dependencies participate in cache invalidation. No silent arbitrary streetscape truncation or invented lane markings are required for a scene to appear complete.

## Experiment

Use the exact saved style attachment and a 220 m AOI centered at 106.7032, 10.7763. Target Opera House, Continental and Caravelle from licensed photographs; the Opera also receives an oblique context photo. The context image's background tower must not be mistaken for the Opera. No factual top-down imagery has yet been added; map diagrams and generated overhead views do not replace it.

Bounded attempt: 18 API attempts, 240k tokens, 2400 active seconds, one visual refinement cycle. These are finite research limits, not a billing estimate or future batch authorization. Existing earlier runs remain immutable comparison evidence.

Acceptance evidence: actual source/runtime/geometry checks, equal geometry and material fingerprints across presentation changes, per-object review of all targets, inspected before/after images, regression checks and an honest remaining-defect report. A style score or test pass alone cannot establish reconstruction fidelity.
