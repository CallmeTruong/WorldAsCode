# Agent design on a measured site

Date: 2026-11-12. One pilot on the Mitsubishi Ichigokan Museum (`way/306116935`) with the user's aerial style reference. One building is a pilot, not a benchmark.

## Division of work

| Layer | Who | Artifact | Model calls |
|---|---|---|---|
| Facts | deterministic code | `site.json`: outline, edges with facing and wing ends, eave/ridge/top heights, roof pitch, measured dormer/chimney/tower positions, sampled colours | 0 |
| Style | agent, once per style image set | `style.json`: form, detail, colour and material treatment, light, exaggeration limits | 1 (cached by image content) |
| Design | agent | `attempt-N/design.mjs`: a script in the building kit (`runtime/kit.mjs`, reference in `runtime/kit-api.md`) | 1 per attempt |
| Checks | deterministic code | `metrics.json`: outline agreement through the evidence cameras, height ratio, triangle budget | 0 |
| Review | vision critic | `review.json`: likeness, style, detail, feature checklist, kit-level fixes | 1 per attempt |

The agent chooses materials, window treatment, roof form, ornament, repetition and extra masses, and can add free geometry. It cannot change the wall outline: `b.walls` and every edge frame come from the site. Design scripts run only in the sandboxed browser page; a lint rejects imports, network, timers and browser globals before bundling.

The metric limits are tolerant by design (mean oblique silhouette IoU 0.70, plan IoU 0.75, height within 0.8–1.3 of measured). They exist to reject a wrong building, not to force a trace. The earlier 0.85 single-view silhouette gate is not used on this route.

## Pilot result

`runs/design-ichigokan-v1`, one revision allowed.

| Attempt | Built first time | Mean oblique IoU | Likeness | Style | Detail | Critic accepted |
|---|---|---|---|---|---|---|
| 0 | yes | 0.853 | 0.68 | 0.64 | 0.43 | no |
| 1 | yes | 0.855 | 0.65 | 0.72 | 0.53 | no |

Thresholds are 0.70 / 0.65 / 0.65. `accepted` is false. Attempt 1 is kept as the best.

Cost: 5 model calls, 31,430 input and 7,065 output tokens, no unknown reserve. Wall time 404 s, of which 182 s was model latency; the rest was fitting facts (now cached per evidence bundle) and two browser captures. For comparison, `native-museum-v2` used 153,904 metered tokens plus a 194,037-token unknown reserve and did not pass its first pass.

Direct inspection of `attempt-1/render-sheet.jpg`: red-brick three-storey L plan, slate mansard, corner towers with pointed caps, dormers, chimneys, stone bands and window surrounds, an arched entrance, style-sheet lighting and ground. The script is 106 lines. The agent turned off the kit's window tile and built its own stone-framed windows from boxes, which the kit allows.

What the critic and inspection agree is still wrong:

- The roofline is flatter and more uniform than the real one. Tall feature gables are weak; dormers are small and repetitive.
- Facade ornament is thin compared with the reference.
- Some dormer and tower bases meet the roof as plain boxes.
- Two attempts did not converge to acceptance. Whether more revisions, a richer kit, or both are needed is not established.

The critic is the same model family as the author and has not been compared with human judgement. Its scores rank attempts; they are not a measured quality level.

## Why this route instead of the earlier two

- The native route asked the agent for coordinates and judged it on pixels. It was expensive and never left blockout.
- The compiled-massing route (docs/08) is accurate and cheap but leaves the agent nothing to design, and a roof fitted to noisy heights looks stepped.
- Here measurement supplies anchors and limits, and the agent spends its tokens on design decisions in a vocabulary that cannot break the plan.

## Scaling plan (not yet built)

1. **Family scripts.** A design script already reads everything from `site`. Running one script on other sites of the same building type needs no model call. Not yet tried on a second site.
2. **Tiering.** Tag-derived massing for background buildings (`district`, docs/08), a family script for ordinary ones, a bespoke script for landmarks.
3. **Kit growth from critic feedback.** Recurring "fixes" that the kit cannot express become new parts. From this pilot: tall wall gables integrated with the roof, dormer variants, a window-surround part.
4. **District composition** of designed buildings into one frame, with roads and ground.

## Command

```powershell
.venv/Scripts/python -m worldscale.cli design `
  --evidence inputs/evidence/<id> --styles inputs/style-references/<folder> `
  --run runs/<name> --max-revisions 1
```

Uses `heights.json` beside the evidence when present (see docs/08 for sampling). Model calls are capped at `2 + 2 × (revisions + 1)`.
