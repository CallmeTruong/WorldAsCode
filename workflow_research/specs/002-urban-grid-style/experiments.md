> Active implementation revision: [scene reconstruction](scene-revision.md). Earlier scope/status statements below are historical where they conflict with this revision.

# Kế hoạch nghiên cứu và thử nghiệm có kết quả trực quan

> Current selected result: `district1-quality-v10` (220 m AOI, 3 photo-backed targets and 8 context proxies). Descriptive style preserves native materials; fidelity remains partial. See [quality correction results](../../reports/urban/quality-correction-results.md). Earlier v4/palette/36-building statements below are historical and superseded.


**Status:** Planned, chưa triển khai các experiments. **Date:** 2026-11-12.

## Câu hỏi phải trả lời

1. Dữ liệu nào trong phạm vi nhỏ quanh Quận 1 đủ cho reconstruction, dữ liệu nào chỉ phù hợp streaming, phần nào còn suy luận?
2. Native img2threejs và nhánh code-generation adapter khác nhau thế nào về fidelity, chi phí, thời gian và khả năng sửa?
3. Chia cell thế nào để đường/vật liệu/đối tượng giữ liên tục và sinh lại độc lập?
4. Tái sử dụng generators có giảm việc lặp mà không ép công trình vào template không phù hợp?
5. Style trích từ folder có thể áp dụng nhất quán toàn scene và giữ cấu trúc đã khóa không?
6. Nút thắt scale thực tế nằm ở API, geometry, texture, draw calls, memory hay data preparation?

## Protocol

- Freeze bbox con, refs có quyền dùng, OSM snapshot, registry, source/skill/model/prompt/profile versions.
- Chọn 2×2 ô đủ trường hợp biên; ghi rõ cặp ô dùng để phát triển và ô hold-out nếu có thể.
- Bắt đầu từ neutral geometry; camera alignment được lưu riêng trước style.
- Thay một biến mỗi comparison, lưu mọi lần lỗi và candidate bị loại.
- Mỗi job và toàn đợt có finite time/token/USD limits. Discovery này không cấp ngân sách suy diễn cho future batch.
- Trước ghi chi phí phải xác nhận nhóm giá/quota/cache và thời điểm biểu giá; phiếu billing chưa có thì không coi ước tính là tiền đã trừ.

## Ma trận thử nghiệm tối thiểu

| ID | Baseline | Thay đổi | Đo và artifact |
|---|---|---|---|
| R0 | Kết nối dịch vụ | Truy cập dữ liệu AOI và audit quyền | Evidence JSON, raw OSM snapshot nếu đọc được, missing-field table, coverage chưa đo |
| R1 | Native staged baseline | Research adapter có domain gates | Input giống nhau, pass/gate status, geometry, camera, code, renders, failure và usage |
| R2 | Một cell | 2×2 cells với global contracts | Seam errors, duplicates, graph connectivity, ownership và thời gian assemble |
| R3 | Source mới cho phần lặp | Reuse generators + source đặc thù | Chất lượng từng feature, tokens, số patch, regressions |
| R4 | Neutral/color-only | PBR texture bindings | UV scale, material slots/color-space, cận cảnh và view cùng camera |
| R5 | Style prompt tự do | Extracted StyleProfile từ cùng ảnh | Contact sheet/profile/conflicts; fidelity/style review tách riêng; ý kiến người dùng |
| R6 | Neutral scene | Material-only style A và style B nếu có | Geometry/transform hashes giữ nguyên; ảnh cùng camera, không gán effect camera cho style |
| R7 | Full rebuild | Một cell/style/dependency thay đổi | Rebuild set, cache, ngoài phạm vi không đổi, seam checks trước/sau |
| R8 | Tuần tự | 2 rồi 4 workers nếu quota đủ | Cold/warm wall time, RPM/TPM, retries, shared budgets, local resources |
| R9 | Scene chưa tối ưu | Instances/LOD/spatial streaming | Same camera path, draw calls, frame time distribution, texture memory khả dụng, load/unload correctness |

Style A/B không tự chọn thay cho user: nếu chỉ một reference set thì dùng neutral/A và ghi phạm vi còn thiếu. Nếu không có style folder, R5/R6 chờ input và không được đánh dấu đạt.

## Gói kết quả phải giao và trực tiếp xem

Đề xuất output tương lai tại `runs/urban/<experiment-id>/`; chưa tạo trong lượt docs:

- `input-manifest`, source/rights audit, CitySpec/CellSpecs, object registry và boundary contracts.
- Ảnh factual references; style contact sheet/profile tách riêng.
- Procedural source, generator versions/params, materials/assets/provenance và scene/export artifacts.
- Overview, bốn ô với ID, street-level views, seam close-ups, material close-ups, neutral/styled same-camera comparisons.
- Layer tô màu observed/inferred/unknown; phần streaming không được tính thành procedural output.
- Viewer/gói ảnh có thể mở tại máy; không chỉ console/logs.
- Raw metrics, errors, patch history, rollback, resource/usage và bảng so sánh.
- Research findings/ADR: phương án đã thử, giữ/bỏ vì sao, chất lượng chưa đạt, cách khắc phục và bottleneck tiếp theo.

Người thực hiện phải mở artifact đã lưu trong trình duyệt hoặc image viewer, kiểm tra blank/stale/clipped, biên, style và sai cấu trúc; lưu review trực tiếp. Chưa có visual pilot thì trạng thái là pending, không gọi HTTP metadata test là thử nghiệm đô thị hoàn chỉnh.

## Nghiệm thu từng lớp

1. **Input readiness:** nguồn và quyền đủ dùng, dữ liệu thiếu được liệt kê, không có credentials trong manifests.
2. **Geometry/factual fidelity:** identity features, footprint/height constraints, ground alignment, topology đúng role; VLM không là bằng chứng duy nhất.
3. **Boundary consistency:** road samples/UV phase, duplicate IDs, shared revisions, geometry kỹ thuật ghép kín; ngưỡng 1 cm/1° là mục tiêu đề xuất, không là survey accuracy.
4. **Style adherence:** cùng camera, thuộc tính profile thực sự áp dụng, confidence/conflicts, ý kiến người dùng; geometry invariants không đổi trong material-only mode.
5. **Operational quality:** quota/budget compliance, reproducible inputs, partial recovery, artifacts và measured viewer/generation performance.

## Roadmap và trạng thái

- [x] S0 Đọc yêu cầu, kiểm tra token/asset endpoints/catalog/model discovery và ghi docs/spec.
- [ ] S1 Hoàn tất AOI data/rights audit, kiểm tra visual coverage, nguồn ảnh và budget cho thực nghiệm.
- [ ] S2 Hoàn tất native compatibility baseline và prototype input texture/style.
- [ ] S3 Dựng 2×2 pilot, boundary validation và paired neutral/styled output.
- [ ] S4 Chạy comparisons/hold-out/scale có giới hạn và trực tiếp kiểm tra artifacts.
- [ ] S5 Chốt workflow bằng findings, kết quả xem được và các trade-offs.

Checkboxes trên thể hiện trạng thái roadmap nghiên cứu, không phải đánh giá chất lượng requirements. S0 không đồng nghĩa scene đô thị đã được triển khai.

## Evidence hi?n c?

R0 ?? probe; R2 topology/owner/canonical surfaces c? b?ng ch?ng nh?ng ch?a ??c l?p streaming; R3 c? reuse source v? m?t object ri?ng; R4 c? PBR; R5/R6 c? neutral/A c?ng geometry/camera, ch?a c? style B ho?c nghi?m thu c?a user; R7 ch? test input/material invalidation; R1 native eight-pass, R8 concurrency, R9 LOD/streaming c?n pending. Kh?ng c? held-out evaluation. C?c l??t v1?v5 kh?ng ph?i th? nghi?m m?t bi?n ???c ki?m so?t to?n b?; ch? paired neutral/style gi? geometry/camera c? ??nh. Xem findings thay v? suy ra ch?t l??ng t? checkbox.