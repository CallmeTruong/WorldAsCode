# Data model

WorldIR: schema_version, world_seed, coordinate_frame, blueprints, instances, network, styles, provenance.
Blueprint: id, version, semantic_components, material_slots, generator_ref, allowed_variation, runtime_capabilities.
Component: id, kind, topology_class, geometry_params, parent/attachment, evidence_refs, confidence, semantic_requirements.
Instance: stable_id, blueprint_id/version, transform/anchor, seed_channels, locked_attributes, overrides.
RuntimeState: time_of_day, wetness, wind, lighting/occupancy, actor state; excluded from geometry cache key.
NetworkEdge: stable_id, points_xyz, width/gauge, stationing, level, lane/track identity. TilePort: edge_id, position, tangent, phase, owner.
NativeState: actual upstream state/spec paths, commit, next-command output, correction counters; never synthesized as success.
PassReview: pass, source/render hashes, capture scope/camera, deterministic gate artifacts, semantic gate, critic scores/features/action and native append/check output.
ArtifactManifest: content hashes, dependencies, origin (native/semantic/custom), validity and acceptance. Job ledger records requests and checkpoints for resume.
