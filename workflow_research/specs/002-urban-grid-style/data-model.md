> Active implementation revision: [scene reconstruction](scene-revision.md). Earlier scope/status statements below are historical where they conflict with this revision.

# Data contracts đề xuất

> Current selected result: `district1-quality-v10` (220 m AOI, 3 photo-backed targets and 8 context proxies). Descriptive style preserves native materials; fidelity remains partial. See [quality correction results](../../reports/urban/quality-correction-results.md). Earlier v4/palette/36-building statements below are historical and superseded.

> Active quality correction: [quality revision](quality-revision.md) supersedes earlier palette/material-only contracts. Descriptive style, native materials, individual object evidence and explicit visual acceptance are now required.


**Status:** Design only; chưa có runtime schema/parser tương ứng. **Date:** 2026-11-12.

## Các thực thể

| Entity | Trường chính | Ràng buộc |
|---|---|---|
| AreaSpec | id, WGS84 polygon/bbox, local origin, CRS/units, data revision | Nêu rõ bbox ordering; đơn vị mét sau chuẩn hóa; không coi bbox là ranh hành chính |
| SourceRecord | provider, dataset/asset ID, retrieved_at, checksum, license, allowed_uses, attribution, coverage_status | Credentials và signed URLs không được lưu trong artifact; unknown permission không đồng nghĩa allowed |
| CitySpec | AreaSpec, road graph, object index, terrain source, shared profile/registry versions | Nguồn sự thật dùng chung, cập nhật có revision |
| CellSpec | id, bounds, context buffer, owned/referenced IDs, boundary contracts, evidence, limits | Không sinh duplicate object; context buffer không cấp quyền ghi sang ô khác |
| ObjectRecord | stable id, semantic role, owner, transform, source/parameters, dependencies, evidence | OSM ID bao gồm element type; một owner, nhiều references; confidence 0..1 |
| RoadRecord | graph endpoints, spline, cross-section, elevations, chainage origin, material sections | Phân biệt layer/bridge/tunnel; UV/marking phase ổn định toàn tuyến |
| BoundaryContract | affected IDs, shared samples, position/tangent/elevation/width, continuity tolerances | Các cell dùng cùng canonical data và revision |
| GeneratorRecord | id, semantic version, source hash, schema, supported roles, regression evidence | Cell không tự sửa shared version; promotion và invalidation có kiểm tra |
| MaterialAsset | id, map slots, content hashes, license, physical scale, color-space, resolver revision | UV phải tồn tại khi cần; maps không nhận arbitrary external URI từ model |
| StyleReferenceSet | id, explicit local dir, selected file hashes, per-image roles/weights/provenance | Không scan ngoài thư mục được chọn; reject invalid/decompression-bomb images |
| StyleProfile | id/version, evidence hashes, attributes, confidence/conflicts, locked invariants, overrides | Không ghi geometry facts từ ảnh style; profile được validate trước áp dụng |
| Experiment | hypothesis, input/versions, variable under test, budget, candidates, measurements | Phân biệt measured/projected và cache loại nào |
| Candidate | object/cell revision, artifacts, scores by dimension, critical issues, retain/reject reason | Source và failed evidence giữ nguyên; rollback không xóa lịch sử |

## StyleProfile dự kiến

```json
{
  "id": "user-style-a",
  "version": "draft-1",
  "reference_set_hash": "computed-at-ingest",
  "mode": "material-only",
  "attributes": {
    "palette": [],
    "contrast": {"value": null, "confidence": 0},
    "saturation": {"value": null, "confidence": 0},
    "material_rules": [],
    "shading": {"value": null, "confidence": 0},
    "outlines": {"value": null, "confidence": 0},
    "foliage_treatment": {"value": null, "confidence": 0},
    "detail_level": {"value": null, "confidence": 0}
  },
  "locked_invariants": [
    "world_transforms", "footprints", "floor_counts",
    "road_connectivity", "boundary_contracts", "object_ids"
  ],
  "conflicts": [],
  "regional_overrides": [],
  "evidence": [],
  "status": "awaiting_reference_images"
}
```

Ví dụ là shape thiết kế; không phải kết quả trích xuất style. `null` là unknown, không suy ra một default bằng 0. Mỗi attribute có evidence refs và confidence; palette cần định nghĩa color-space ở schema triển khai. Profile không mang API key hay raw filesystem capabilities.

## Cấu hình workflow dự kiến

```json
{
  "area_id": "hcmc-central-d1-pilot",
  "source_audit": "docs/research/2026-11-12-district1-service-probe.json",
  "pilot_grid": {"rows": 2, "columns": 2, "cell_size_m": 100},
  "style_reference_dir": null,
  "style_mode": "material-only",
  "research_budget_usd": null,
  "execution_status": "design_only"
}
```

Đường dẫn trong ví dụ là từ workspace root. Kích thước grid/vùng đệm là giả thuyết pilot, không mô tả một grid đã được dựng. Không có budget thì chỉ discovery/docs hiện tại được thực hiện, không tự chạy inference/streaming batch mới.

## State transitions dự kiến

`source_discovery -> rights_and_coverage_audit -> freeze_inputs -> city_spec -> cell_plan -> generate_or_reuse -> geometry_and_boundary_gates -> material_style_bindings -> render -> fidelity_and_style_review -> retain_or_refine -> export_and_report`.

Style branch: `explicit_folder -> safe_ingest -> contact_sheet/statistics -> bounded_extraction -> validate_conflicts/invariants -> version_profile -> bind -> paired_review`.

Một revision shared generator/style được chấp nhận sẽ invalidates đúng phụ thuộc. Style-only material-mode không invalidates geometry; structural changes invalidates geometry, bounds, boundary evidence và các render/exports liên quan. Failed candidate không thay incumbent.