# Quận 1: workflow đã chạy và giới hạn

> Current selected result: `district1-quality-v10` (220 m AOI, 3 photo-backed targets and 8 context proxies). Descriptive style preserves native materials; fidelity remains partial. See [quality correction results](quality-correction-results.md). Earlier v4/palette/36-building statements below are historical and superseded.

Cập nhật 12/11/2026. **Pipeline đã chạy end-to-end, có viewer; độ giống kiến trúc thực tế còn partial.** Bản xem chính là `district1-final-v4`. Lượt `district1-roof-v5` chạy hợp lệ nhưng sửa mái chưa tốt hơn, được giữ làm bằng chứng. Điểm VLM chưa hiệu chuẩn, không phải độ chính xác đo đạc.

- [Báo cáo ảnh và dữ liệu](../../runs/urban/district1-final-v4/index.html)
- [Viewer trên localhost](http://127.0.0.1:8765/district1-final-v4/viewer.html)
- [Neutral/style](../../runs/urban/district1-final-v4/comparison-overview.jpg)
- [Công trình có quan sát riêng](../../runs/urban/district1-final-v4/renders/styled-landmark.png)
- [Review thiếu sót](../../runs/urban/district1-final-v4/visual-review.json)
- [Chạy lại](../../specs/002-urban-grid-style/quickstart.md)

## Input và hoạt động thực tế

1. **Địa lý:** snapshot OSM quanh Nhà hát Thành phố, gần 10.775 N, 106.702 E. Đổi sang UTM48 theo mét; AOI 400 × 400 m, bốn ô 200 m. Input có footprint, đường, vùng đi bộ, cây/đèn có tag, một số chiều cao. Ghép ring/multipolygon, giữ courtyard; truy vấn bổ sung relation thiếu có giới hạn. Chiều cao/bề rộng đường suy diễn được ghi evidence.
2. **Style:** ảnh người dùng được lưu nguyên bản ở `inputs/style-references/user-isometric/reference.png`, kèm manifest. Nhận thư mục tùy chọn 1–20 ảnh, kiểm tra hash/kích thước, tạo contact sheet, gọi vision model theo batch tối đa bốn ảnh. Trích palette theo vai trò, roughness, ánh sáng, camera, cây và mức chi tiết. Không dùng ảnh Singapore làm bằng chứng địa lý Quận 1. Khuyến nghị outline được ghi nhưng chưa có postprocessing thực thi.
3. **Ảnh factual từng object:** manifest độc lập ánh xạ ID sang ảnh/nguồn/giấy phép. Đã thử Nhà hát Thành phố, `way/801710792/0`, ảnh Wikimedia Commons của Jorge Láscar, CC BY 2.0. Vision phân tích identity, mặt đứng, mái/cửa/cột; codegen riêng tạo object đó. Chỉ **1/36** công trình có bước này. Một ảnh chính diện không xác nhận mặt sau, toàn bộ mái hoặc kích thước chính xác.
4. **Sinh scene:** LLM sinh TypeScript tham số hóa từ metadata OSM cho công trình thông thường; nhánh có ảnh thay riêng object tương ứng. Đường/vỉa hè/công viên dùng phép toán hình học toàn AOI; cây/đèn/vạch đường dùng procedural assets và instancing. Các mặt đứng không có ảnh vẫn là suy diễn, không coi mọi object là đã được quan sát riêng.
5. **Texture:** PBR CC0 từ Poly Haven, kiểm tra host/checksum/dung lượng/pixel. Đường dùng `asphalt_02`; bê tông/vỉa hè dùng `concrete_floor_02`, có color/normal/roughness. Material điều biến theo palette và tỷ lệ mét toàn cục. Cây/kính/nhiều chi tiết dùng procedural material. Đây là vật liệu tái sử dụng, chưa phải ảnh texture thật từng mặt đứng; không lấy texture Google Tiles để tái tạo/export.
6. **Kiểm tra:** compile TypeScript → worker Chromium chặn mạng → geometry gate img2threejs thật → kiểm tra coverage/chiều cao → trusted renderer. Bảy góc mỗi style, neutral/styled giữ geometry/camera. Review dùng ảnh render thật và ảnh style, đối chiếu identity riêng khi có ảnh object. Compile/geometry tối đa ba lần thử; sửa thẩm mỹ chưa thành vòng lặp tự động tổng quát. SQLite giữ checkpoint, usage giữ calls/tokens/thời gian, source history giữ bản sửa.

Model thực dùng vision/code/review: `gpt-6-sol`, qua gateway trong `.env`. Không chạy Codex/Claude CLI trong runtime. Adapter img2threejs dùng source pin và geometry gate thật; baseline native đủ tám pass vẫn chưa hoàn tất.

## Kết quả và giới hạn

V4 có 36 công trình, 350 cây, 111 đèn, bốn cell; 32 chiều cao suy diễn. Cây/đèn gồm node OSM và vị trí procedural, không phải 461 object đã được ảnh xác nhận. Scene có đường, vỉa hè/vùng đi bộ, cỏ, cửa sổ, mái và texture; cây còn đơn giản, mặt đứng lặp, nút giao/vạch đường cần sửa. Nhà hát có vòm chính/cửa vòm/cột, nhưng mái, bậc thềm và tượng chưa đạt ảnh thật.

Đã trực tiếp xem overview/street/seam/landmark, thao tác viewer bằng Playwright; style switch giữ hash geometry, lượt kiểm tra không có page error. Đã sửa lỗi serialize geometry làm mất biến đổi khi dựng lại Three.js bằng cách bake BufferGeometry; ảnh lỗi giữ trong experiment. V5 sửa mái ban đầu lỗi normals, sau sửa vượt gate nhưng vẫn có khối mái/phía sau lớn không hợp lý. Vượt gate không chứng minh giống thị giác.

Canonical road surface liên tục trước khi cắt ô; sai khác diện tích union so với hợp fragment khoảng 10⁻¹² m², object có một owner. **Đây là kiểm chứng topology/input và scene toàn AOI, chưa phải streaming các ô độc lập.** Cell cache lưu hash input geometry/material và fragment; test đổi style không đổi geometry input. Chưa có cache mesh/dependency hoàn chỉnh cho mọi asset.

## Usage và thời gian

| Lượt | API attempts | Input tokens | Output tokens | Active seconds | Ý nghĩa |
|---|---:|---:|---:|---:|---|
| district1-pilot | 4 | 12,419 | 6,605 | 233.0 | Style + code + sửa compile + review |
| district1-pilot-v2 | 1 | 4,065 | 745 | 95.1 | Tái dùng source/style, sửa data/camera |
| district1-object-v3 | 3 | 9,223 | 6,474 | 300.1 | Quan sát/code riêng Nhà hát |
| district1-final-v4 | 2 | 9,867 | 1,711 | 140.5 | Tái dùng object/source, trích style lại + review |
| district1-roof-v5 | 3 | 24,395 | 3,409 | 195.6 | Sửa mái + normals + review; chưa cải thiện |

Tổng 13 attempts, 78,913 tokens tính theo usage, khoảng 964 giây active tích lũy. Đây là chuỗi nghiên cứu có cache/tái sử dụng, không phải năm mẫu độc lập để suy ra trung bình cold start. Active time không gồm toàn bộ thời gian kỹ sư phân tích/chỉnh sửa. Các lượt mất khoảng 1.6–5 phút thời gian máy, nhưng chưa đạt chất lượng hoàn chỉnh.

USD để `null` vì chưa có giá gateway được xác nhận. Không suy ra hóa đơn từ giá model có tên tương tự. Khi có giá: input_tokens/1e6 × input_rate + output_tokens/1e6 × output_rate, cộng dữ liệu/hosting nếu dùng. Token replay từ cache tách khỏi token gọi thật trong `usage.json`.

Riêng v4: renderer 92.8 giây, peak RSS khoảng 1,051 MB; overview 361 draw calls, 287,148 visible triangles, 266 geometries, 12 textures. CPU submission median 3.5 ms, p95 5.3 ms cho styled; **không phải FPS hay thời gian GPU hoàn tất**. Chưa benchmark điện thoại/đô thị lớn.

## Hướng mở rộng phù hợp

Giữ mạng đường/cao độ/UV toàn cục; cell sở hữu fragment và tham chiếu. Tách dữ liệu địa lý, object identity, code geometry, asset registry và style/material. Ưu tiên ảnh riêng cho landmark/object gần camera; công trình phổ thông dùng family template tham số hóa, giữ cờ inferred.

Tiếp theo cần: lane/intersection graph, cây đa dạng có LOD, facade family/atlas, nhiều ảnh factual có camera tốt, terrain, cache mesh theo source+object+asset dependencies, streaming/LOD theo camera, benchmark nhiều AOI và ngân sách đo thật. Batch job qua hàng đợi, khóa source chung/schema, giới hạn parallel inference, sửa có mục tiêu. Mỗi ô không tự viết lại hệ đường riêng.

1 km² tương đương khoảng 25 ô 200 m so với bốn ô của pilot 0.16 km². Đây chỉ là số ô; chưa thể nhân tuyến tính chi phí/thời gian khi chưa đo mật độ và số object cần ảnh riêng. Prototype này dùng kiểm chứng hợp đồng, chưa là dịch vụ tái dựng đô thị chi tiết production.

Không cần thêm key để xem/chạy pilot. Đầu vào hữu ích nhất để tăng độ giống là ảnh nhiều góc có quyền sử dụng và cao độ/chiều cao đáng tin cậy. Cesium token đã probe readiness riêng; bản này chưa dùng Cesium/Google tiles trong renderer, chưa ingestion liên tục.