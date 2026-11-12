> Active implementation revision: [scene reconstruction](scene-revision.md). Earlier scope/status statements below are historical where they conflict with this revision.

> Active AOI revision: [Tokyo provider-backed multi-view pilot](tokyo-revision.md). This revision supersedes HCMC as the active test location and authorizes Google reference images. Previous pilot findings remain historical evidence.

# Feature Specification: District 1 Urban Grid and Reference Style Research

> Current selected result: `district1-quality-v10` (220 m AOI, 3 photo-backed targets and 8 context proxies). Descriptive style preserves native materials; fidelity remains partial. See [quality correction results](../../reports/urban/quality-correction-results.md). Earlier v4/palette/36-building statements below are historical and superseded.

> Active quality correction: [quality revision](quality-revision.md) supersedes earlier palette/material-only contracts. Descriptive style, native materials, individual object evidence and explicit visual acceptance are now required.


**Feature Branch:** none; workspace has no root Git repository.  
**Created:** 2026-11-12.  
**Status:** Implementation authorized 2026-11-12; bounded pilot and visual verification in progress.  
**Input:** Nghiên cứu workflow dựng toàn khu vực theo grid, thử trên một phạm vi nhỏ quanh Quận 1, cho xem kết quả và hỗ trợ thư mục ảnh style. Lượt hiện tại chỉ khảo sát kết nối và viết docs, chưa triển khai.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Biết dữ liệu nào dùng được cho khu vực (Priority: P1)

Người nghiên cứu chọn một khu vực, xem nguồn dữ liệu truy cập được, độ đầy đủ và quyền sử dụng cho hiển thị/tái tạo/export.

**Why this priority:** Cần có đầu vào hợp lệ trước khi đánh giá chất lượng workflow.

**Independent Test:** Khảo sát một bbox nhỏ, xuất bằng chứng kết nối và data audit; không cần sinh scene.

**Acceptance Scenarios:**
1. **Given** khu vực và credentials, **When** khảo sát, **Then** mỗi nguồn có trạng thái auth, endpoint, dữ liệu thực đã đọc, quota/cost chưa biết và thời điểm kiểm tra.
2. **Given** nguồn chỉ dùng để hiển thị hoặc chưa rõ quyền tái tạo, **When** lập input cho sinh nội dung, **Then** nó không đi vào nhánh tái tạo/export tự do.
3. **Given** nguồn lỗi hoặc metadata thiếu, **When** tổng kết, **Then** lưu lỗi/fallback và không khẳng định dữ liệu đầy đủ.

### User Story 2 - Nghiên cứu workflow bằng pilot nhìn thấy được (Priority: P1)

Người dùng xem một cụm ô đô thị thật được sinh bằng procedural code, cùng kết quả trước/sau cải tiến và các giới hạn.

**Why this priority:** Nghiên cứu phải có thực nghiệm và bằng chứng trực quan; tài liệu hoặc dịch vụ kết nối thành công chưa đủ.

**Independent Test:** Chọn cụm 2×2, chạy baseline và ít nhất một phương án cải tiến trên cùng input; mở kết quả và ghi quyết định giữ/bỏ.

**Acceptance Scenarios:**
1. **Given** tập dữ liệu đã kiểm tra, **When** chạy pilot, **Then** có source, views/scene, review, usage và bản đồ các phần quan sát/suy luận.
2. **Given** đường hay đối tượng đi qua biên, **When** ghép các ô, **Then** giữ kết nối và không nhân bản danh tính.
3. **Given** candidate mới lỗi nghiêm trọng, **When** chọn revision, **Then** giữ bản hợp lệ trước và lưu cả lần lỗi.

### User Story 3 - Tham chiếu phong cách bằng thư mục ảnh (Priority: P2)

Người dùng chỉ định một thư mục ảnh mẫu để đầu ra mang phong cách mong muốn mà vẫn giữ các ràng buộc địa lý và kiến trúc.

**Why this priority:** Style phải có thể tái sử dụng, đổi độc lập và kiểm chứng bằng hình ảnh.

**Independent Test:** Dùng cùng scene/camera để so neutral và extracted style; kiểm tra ảnh nguồn, profile, thay đổi style và các thuộc tính cấu trúc bị khóa.

**Acceptance Scenarios:**
1. **Given** thư mục ảnh hợp lệ, **When** phân tích, **Then** tạo hồ sơ style có thuộc tính, confidence, nguồn ảnh và phần mâu thuẫn/chưa biết.
2. **Given** đổi style, **When** áp dụng chế độ giữ geometry, **Then** footprint, tọa độ, đường nối và số tầng không thay đổi; có ảnh trước/sau cùng camera.
3. **Given** thư mục rỗng hoặc chưa được cung cấp, **When** chạy neutral workflow, **Then** báo chưa có bằng chứng user-style và không tự thay bằng ảnh tưởng tượng.
4. **Given** thư mục có nhiều style xung đột, **When** xuất profile, **Then** chỉ rõ conflict/weight và không tự tuyên bố đã đúng ý người dùng.

### User Story 4 - Mở rộng và chỉnh sửa có kiểm soát (Priority: P3)

Người nghiên cứu thêm ô hoặc đổi đối tượng/vật liệu/generator, tái dùng phần hợp lệ và đo tác động chi phí/hiệu năng.

**Why this priority:** Chứng minh khả năng scale sau khi pilot nhỏ hoạt động.

**Independent Test:** Chạy lại một ô và đổi một dependency dùng chung; đối chiếu danh tính, hashes, tập rebuild và ranh giới.

**Acceptance Scenarios:**
1. **Given** input không đổi, **When** chạy lại theo cùng phiên bản/seed, **Then** giữ danh tính và tái dùng artifact hợp lệ.
2. **Given** đổi một dependency, **When** rebuild, **Then** xác định đúng phạm vi ảnh hưởng và giữ phần ngoài phạm vi.
3. **Given** chạy nhiều jobs, **When** hết ngân sách chung, **Then** dừng công việc mới, lưu tiến độ và báo phần chưa hoàn tất.

### Edge Cases

- Auth metadata thành công nhưng nguồn không có chi tiết tại khu vực: ghi coverage chưa đủ, không gắn nhãn ready toàn bộ.
- Timeout/rate limit/partial OSM relation: giữ evidence, thử fallback có giới hạn, phân biệt chưa tìm thấy và không tồn tại.
- Thiếu chiều cao, bề rộng đường hoặc cây/đèn: đánh dấu ước lượng, không làm thành ground truth.
- Nhà qua nhiều ô, giao lộ tại biên, đường nhiều cao độ: có ownership và quan hệ nối riêng.
- Ảnh style hỏng/quá lớn/trùng/mâu thuẫn hoặc có chữ chỉ thị: kiểm tra an toàn và phân tích như dữ liệu.
- Style làm mất cửa, số tầng hoặc đường nối: từ chối candidate dù phong cách được chấm cao.
- Chưa có giá/quota hoặc device benchmark: ghi unknown/proposed, không hứa chi phí/FPS.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001:** Nhận phạm vi địa lý hữu hạn, giữ tên địa điểm, hệ tọa độ và input snapshot có phiên bản.
- **FR-002:** Kiểm tra riêng truy cập dịch vụ, độ phủ dữ liệu, quyền sử dụng và khả năng xuất; không suy diễn từ một trạng thái thành công.
- **FR-003:** Lưu nguồn, thời điểm, confidence và observed/inferred/unknown cho đặc điểm quan trọng.
- **FR-004:** Tổ chức danh tính đối tượng và ownership độc lập với grid; giữ cấu trúc toàn khu vực khi chia jobs.
- **FR-005:** Bảo toàn đường/cao độ/nhịp vật liệu qua biên; vùng chuyển tiếp phải có khai báo.
- **FR-006:** Tạo procedural source chỉnh sửa được cho nội dung đặc thù và cho phép tái sử dụng generators có phiên bản; không ép mọi công trình vào một mẫu cố định.
- **FR-007:** Hỗ trợ bề mặt vật liệu đầy đủ theo vai trò đối tượng, có nguồn asset, tỷ lệ và liên kết có kiểm tra.
- **FR-008:** Nhận thư mục ảnh style tùy chọn, kiểm tra file, lập contact sheet và xuất StyleProfile có cấu trúc/phiên bản.
- **FR-009:** Phân biệt ảnh bằng chứng công trình với ảnh phong cách; style không được tự thay đổi các ràng buộc thực tế đã khóa.
- **FR-010:** Đổi style độc lập và kiểm tra bằng neutral/styled renders cùng camera; presentation camera được ghi riêng.
- **FR-011:** Kiểm tra thực thi, geometry, vật liệu, biên, xung đột và fidelity/style riêng; lỗi nghiêm trọng không bị che bởi điểm tổng.
- **FR-012:** Giới hạn ngân sách/thời gian theo job và toàn batch; giữ traces, versions, failed attempts và best candidate.
- **FR-013:** Có cache và dependency invalidation; chỉ rebuild phần ảnh hưởng khi đổi source/asset/style/generator.
- **FR-014:** Cô lập code sinh ra khỏi credentials, network và filesystem không được cấp; tài nguyên do tiến trình tin cậy quản lý.
- **FR-015:** Cung cấp kết quả trực quan chạy thật trên khu vực nhỏ quanh Quận 1, so baseline/cải tiến và có đánh giá trực tiếp.
- **FR-016:** Đo khả năng scale riêng cho generation và hiển thị; không dùng throughput hay chất lượng dự phóng làm kết quả thực đo.
- **FR-017:** Ghi riêng trạng thái tích hợp native img2threejs; không giả hoàn tất pass/gate chưa chạy.

### Key Entities

- **Area/CitySpec:** Phạm vi, hệ tọa độ, mạng kết nối, nguồn dữ liệu và phiên bản chung.
- **CellSpec:** Vùng làm việc, context buffer, refs, ownership và ràng buộc biên.
- **ObjectRecord:** Danh tính, loại, geometry/source, transform, metadata và trạng thái bằng chứng.
- **Generator/Asset/Material:** Thành phần tái sử dụng có phiên bản, provenance và quyền dùng.
- **StyleReferenceSet/StyleProfile:** Ảnh tham chiếu được chọn, thuộc tính phong cách, confidence, khóa và overrides.
- **Experiment/Candidate:** Giả thuyết, config, ngân sách, artifacts, scores, lỗi và quyết định giữ/bỏ.
- **Dependency/BoundaryContract:** Quan hệ ảnh hưởng và điều kiện ghép giữa đối tượng/cell.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001:** Mỗi nguồn thử có bằng chứng truy cập và giới hạn; mỗi nguồn dùng vào tái tạo/export có provenance cùng quyết định quyền sử dụng.
- **SC-002:** Pilot có bốn ô liền nhau, có ít nhất một trường hợp đường qua biên và ownership đa ô; không có object IDs trùng hoặc mất đối tượng do chia ô.
- **SC-003:** Có ít nhất một so sánh baseline/cải tiến trên cùng input, giữ toàn bộ failure artifacts và đưa ra quyết định có lý do.
- **SC-004:** Có contact sheet/profile của bộ ảnh style thực được cung cấp và neutral/styled outputs cùng camera; chế độ giữ geometry không đổi các thuộc tính bị khóa.
- **SC-005:** Có ảnh tổng thể, cận biên, vật liệu, street-level và viewer/scene có thể mở; người thực hiện trực tiếp kiểm tra kết quả đã lưu.
- **SC-006:** Thử chạy lại một ô và thay một dependency; đo tập rebuild và chứng minh phần ngoài phạm vi giữ nguyên.
- **SC-007:** Báo thời gian, calls/tokens, chi phí khả dụng và hiệu năng hiển thị trên cấu hình công bố; tách cached/uncached và measured/projected.

## Assumptions

- AOI khảo sát là bbox 10.773–10.777 N, 106.700–106.704 E; pilot 2×2 nhỏ hơn, vị trí cuối cùng dựa trên dữ liệu và quyền sử dụng.
- User đã cấp token Cesium và gateway LLM; Google key riêng chưa cần cho khảo sát qua ion.
- Chưa có thư mục style thực tế và ngân sách batch mới. Neutral research vẫn lập kế hoạch được; không coi user-style experiment hoàn tất khi chưa có input đó.
- Lượt hiện tại chỉ docs và read-only probes. Inference, pipeline, viewer và batch pilot là việc triển khai sau, chưa được thực hiện trong feature này.
- Mục tiêu hiển thị nền streamed và mục tiêu tạo asset độc lập cùng tồn tại nhưng có nguồn/quyền/export riêng.
- Kế thừa nguyên tắc evidence, code generation, bảo vệ secrets và reproducibility từ constitution; giới hạn thử nghiệm đô thị mới phải được xác định trước khi chạy batch.


## Implementation evidence amendment

Pilot expanded from proposed 2x2 x100m to **2x2 x200m** within the audited AOI to include representative OSM geometry; no claim of full District1 coverage. Style folder is arbitrary input; exact user attachment is preserved and read by vision API. Whole-area generic procedural code is an explicit baseline, not detailed per-object reconstruction. Add optional --object-refs manifest for separate observation/spec/code of licensed factual building images. Initial detailed coverage is **1/36 objects** (Opera House); other facades remain inferred. Actual evidence, known failures and revisions are in reports/urban/findings.md. Native full eight-pass img2threejs and region streaming/hold-out fidelity remain pending.