> Active implementation revision: [scene reconstruction](scene-revision.md). Earlier scope/status statements below are historical where they conflict with this revision.

# Thiết kế nghiên cứu — Urban grid + reference style

> Current selected result: `district1-quality-v10` (220 m AOI, 3 photo-backed targets and 8 context proxies). Descriptive style preserves native materials; fidelity remains partial. See [quality correction results](../../reports/urban/quality-correction-results.md). Earlier v4/palette/36-building statements below are historical and superseded.


**Status:** Proposed, không phải implementation đã tồn tại. **Date:** 2026-11-12.

Tài liệu bài toán đầy đủ: [docs/urban_grid_research.md](../../../docs/urban_grid_research.md). Spec: [spec.md](spec.md).

## ADR-01 — Global semantics, local generation

**Decision:** CitySpec giữ hệ tọa độ mét, road graph, elevations, object registry và versions. CellSpec giữ quyền xử lý, context buffer và boundary constraints. Generated code tạo source đặc thù trong phạm vi được cấp; deterministic tools quản lý clipping/build/assembly.

**Rationale:** Grid là đơn vị thực thi/streaming, không phải ranh giới tự nhiên của nhà, đường hay giao lộ. Dùng stable IDs và owner bảo toàn đối tượng qua cell.

**Alternatives:** Cho từng agent dựng toàn bộ ô độc lập dễ làm lệch biên; một monolithic source cho cả vùng khó sửa và tăng context; fixed-template toàn bộ công trình vi phạm mục tiêu reconstruction by code.

## ADR-02 — Có hai nhánh dữ liệu với quyền sử dụng riêng

**Decision:** Source viewer có thể stream các asset được cấp quyền; nhánh procedural export chỉ dùng dữ liệu được phép tạo derivatives/export. Tách IDs, provenance, credits và cache policies.

**Rationale:** Cesium asset endpoint thành công không xác nhận đầy đủ quyền của các nhà cung cấp bên trong. Google policies hạn chế tạo mô hình từ Google Maps Content; raw OSM có điều kiện ODbL riêng.

**Alternatives:** Trích mesh/texture/screenshot Google làm nguyên liệu độc lập không được chọn khi chưa có quyền riêng. Xuất source viewer thành "AI-generated city" gây sai nguồn và không kiểm chứng thuật toán.

## ADR-03 — Style được biên dịch thành profile dùng chung

**Decision:** `style_reference_dir` → local checks/statistics + bounded vision extraction → StyleProfile → material/lighting/optional bounded-form parameters. Hashes và dependencies giúp tái dùng geometry khi đổi style.

**Rationale:** Hồ sơ có cấu trúc cho phép kiểm tra, version, xung đột và tái lập. Giữ factual reference tách style reference; ảnh style không được biến thành bằng chứng số tầng/đường.

**Alternatives:** Đưa toàn bộ ảnh vào mọi call tăng tokens; prompt "cartoon" tự do khó tái lập; fine-tuning/LoRA chưa có bằng chứng cần thiết; copy ảnh mẫu thành texture không phải mặc định hợp lệ.

## ADR-04 — Texture do host resolve, generated code dùng ID

**Decision:** Material registry lưu map URLs/local IDs, checksums, license, color-space, texel scale và slots. Trusted resolver tải có chọn lọc, chuẩn hóa và gắn texture sau geometry validation. Worker tiếp tục bị chặn network/credentials.

**Rationale:** Prototype đang cấm texture; mở khả năng tải URL cho arbitrary generated code làm hỏng ranh giới hiện tại. PBR maps đúng semantic/color-space và tỷ lệ vật lý phải được kiểm tra riêng.

**Alternatives:** Bỏ CSP hoặc cho worker tải tùy ý không được chọn. Một texture atlas khổng lồ toàn thành phố gây rebuild/phân phối quá rộng. Atlas được nghiên cứu theo nhóm vật liệu và spatial chunk.

## ADR-05 — Domain-aware validation

**Decision:** Mỗi geometry role có gates phù hợp: closed building solids; road/sidewalk surfaces; decals; foliage cards; instanced base geometry và transforms. Không tắt mọi topology gate vì vài loại hợp lệ là mặt hở.

**Rationale:** Prototype đóng băng Mesh-only và watertight cho mọi mesh chưa phù hợp đô thị. Giữ phần kiểm tra số học, budget, bounds và provenance cho mọi vai trò.

## ADR-06 — Consistent roads and style at cell boundaries

**Decision:** Dùng road spline/cross-section/cao độ chung, canonical samples tại biên, cumulative road-distance UV, stable scatter IDs và vùng chuyển tiếp khai báo. Không reset texture phase hoặc nhịp cột đèn theo cell.

**Rationale:** World-coordinate consistency cần được bảo toàn trước texturing và LOD; chỉ ghép ảnh đẹp không sửa được đường đứt hoặc UV lệch.

## ADR-07 — Build-time agents, runtime streaming

**Decision:** LangGraph điều phối jobs nghiên cứu/build với persistent state. Viewer tải artifacts đã build theo camera và LOD; không bắt người xem chờ LLM sinh cell trước mặt. Bounded 2/4 workers chỉ thử sau baseline và quota audit.

**Rationale:** API latency là phần lớn thời gian ở prototype. Chưa có bằng chứng nhiều agents chuyên biệt cải thiện chất lượng; bắt đầu bằng vai trò có prompt riêng và chia jobs độc lập.

## ADR-08 — Renderer và georeferencing

**Decision:** Đánh giá CesiumJS cho source viewer/geospatial context và Three.js hiện tại cho sandbox/neutral-style comparisons; chọn có tiếp tục hai viewer hay thống nhất sau thử nghiệm. Chưa thay stack runtime trong lượt docs.

Một origin ENU theo AOI, mét và convention Three.js Y-up phải có transform rõ ràng sang Earth-fixed coordinates. Terrain có datum/source; thiếu cao độ không tự coi bằng 0 là thực tế.

## Các thay đổi dự kiến, chưa triển khai

```text
src/building_workflow/
  urban/        # AOI, source audit, global/cell/object schemas, boundary contracts
  style/        # reference ingest, extraction, profile validation/application
  assets/       # trusted material registry/resolution
  scheduling/   # quota-aware jobs, dependencies, checkpoints
runtime/
  ...           # instance/role-aware payload validation, texture bindings
```

Không có files/modules này được tạo làm runtime trong lượt hiện tại. Chưa có CLI `--style-dir`, city runner, viewer đô thị hay extractor style chạy thật.

## Đo và chốt thiết kế

So same inputs/versions/cameras, lưu mọi candidate, không có blanket quality certification từ VLM. Native img2threejs compatibility còn là công việc bắt buộc; style adoption không được dùng để che baseline incomplete. Các ngưỡng nghiệm thu phải gắn vào phép đo cụ thể và được điều chỉnh có ghi nhận sau pilot.