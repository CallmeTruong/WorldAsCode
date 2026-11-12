# Data Model

- Sample: safe slug id, title, source page and image URL, local image path, SHA256, license, author, development split, crop/metadata. Image is immutable after download.
- BuildingSpec: name, suitability, uncertainty, components (id, parent, shape, observed/inferred/unknown, confidence 0..1, source), repetitions, materials, dimensions and camera hypotheses. This is a research schema, NOT native ObjectSculptSpec 2.1.
- RunConfig: strategy direct/spec, model per stage, max calls/tokens/seconds/corrections, per-call completion cap, optional input/output USD rates.
- Candidate: iteration, source checksum, compile status, emitted scene and geometry report, five renders plus reference camera, structured review, eligibility and failure record.
- Review: six scores 0..1 (mass, facade, roof, details, materials, proportions), critical defects, observations, inferred regions, suggested region edits and confidence. Scores are model judgments requiring calibration.
- Usage: all attempts, input/output tokens, elapsed seconds, cache hits, monetary cost nullable, provider-reported billing if supplied.

State transitions: intake -> analysis -> generate -> execute/geometry -> render -> evaluate -> (refine -> execute/geometry -> render -> evaluate)* -> finalize. Failed execution routes to bounded code repair; exhausted budget finalizes as partial/failed. Completed graph nodes checkpoint durably. Source and all attempted artifacts survive retries. Incumbent selection requires geometry pass, valid review, no critical defect and no material score regression; otherwise preserve prior best.
