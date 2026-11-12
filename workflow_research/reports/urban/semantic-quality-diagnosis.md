# Chất lượng hình học/ngữ nghĩa và khác biệt với img2threejs

Ngày kiểm tra: 2026-11-12. Kết quả `tokyo-coordinated-v1` vẫn `accepted:false`; chưa đạt yêu cầu hình dáng, vật liệu và style.

## Định dạng thực tế

- `building-generator.ts`: chương trình TypeScript dùng Three.js, export `build(params)` nhận `{city,tools}`.
- `urban-worker.js`: code build đã bundle, chạy trong worker bị chặn mạng.
- `buildings-scene.json`: Three.js Object3D/BufferGeometry/material serialization. Đây không phải glTF.
- `city.json`: dữ liệu không gian, thuộc tính/recipe, IDs và trạng thái cấu hình.
- `presentation.json`, `urban-viewer.js`: dữ liệu/renderer phục vụ trình duyệt, bao gồm hạ tầng và vật liệu thủ tục do host gắn.

Chưa có export GLB hoặc tileset 3D Tiles thành phẩm trong nhánh này. Google 3D Tiles là nguồn đầu vào.

## Bằng chứng code và ảnh

Đã đối chiếu ảnh style thật, source `adaptive-1`, render cận cảnh cuối ở `iterations/04/adaptive-1/` và source TS thực tế.

Trong nhánh nhà cổ, thân các chi tiết ống khói được dựng bằng `box(...,.98,2.25,.85,brick)` và nắp bằng `box(...,1.26,.17,1.13,pale)`. Không có inner profile, wall thickness, flue path hay opening. Đây là khối đặc có hình dáng gần giống từ xa, không phải cấu trúc ống rỗng.

Các cửa cũng chủ yếu là box kính đặt trên biên tường và một thanh header; chưa có hệ opening/recess/jamb đầy đủ. Mái đã được bổ sung dormer và chimney nhưng các khối còn đơn giản, lặp đều; không giải quyết được chỉ bằng đổi texture.

Mesh kín/manifold không cấm lỗ chức năng. Thành ống có mặt ngoài, mặt trong và vành nối vẫn có thể là mesh kín của thể tích vật liệu, trong khi lòng ống để trống. Cần kiểm tra ngữ nghĩa/geometry của cavity, không nới topology gate để chấp nhận mặt hở tùy tiện. Ống khói có nắp che vẫn cần cấu trúc thoát khí hợp lý; vật trang trí giống ống khói phải được phân loại khác hoặc ghi nhận chưa rõ.

## Nguyên nhân chính

1. Representation hiện tại vẫn là mã hình học tự do. Observer ghi “chimney-like projections”, coder chọn box cho dễ; chưa có component specification phân biệt flue, rain cap, wall shell và opening.
2. Compile/manifold/placement gates chỉ kiểm tra tính hợp lệ kỹ thuật. Box đặc vượt các gate đó. Visual critic chủ yếu nhìn bề ngoài nên không kiểm tra chức năng ở phần khuất.
3. Một số capture cận cảnh trước đây không đồng nhất visibility với source. Đã sửa capture isolation/manifest và publication audit, nhưng so sánh lịch sử trước sửa không phải benchmark fidelity đáng tin cậy.
4. Một observer từng nhầm roof level; numeric source anchors đã sửa được lỗi này. Vision feedback vẫn cần kiểm tra bằng bằng chứng, không được coi output của node trước là chân lý.
5. Mặt đứng, bề mặt và chi tiết bị giản lược; style reference có mức articulation, phân cấp mặt đứng và tự nhiên cao hơn. Tăng số box hoặc thêm nhiễu albedo không tự tạo ra style tương ứng.
6. Vòng lặp sửa cả source lớn gây lỗi scope/biến và lặp lại nhiều context. Case này dùng 13 request, 378943 input tokens + 44275 output tokens ghi nhận, nhưng vẫn không đạt. Chưa có đơn giá gateway để kết luận USD. Cách này chưa phù hợp để nhân rộng nguyên trạng.

## img2threejs

Checkout `vendor/img2threejs` mô tả model thủ tục Three.js có `ObjectSculptSpec`, staged generation và quality gates. Pass order local: blockout, structural, form-refinement, material, surface, lighting, interaction, optimization. Nhánh đang chạy là adapter có node riêng và tái sử dụng một số gate; native eight-pass baseline chưa hoàn thành (được ghi trong `building_workflow/skills.py`). Vì vậy chưa thể gọi đây là chạy trọn workflow img2threejs gốc hoặc lấy demo của repo làm bảo đảm chất lượng.

Cùng ngôn ngữ xuất không có nghĩa cùng quy trình. Repo gốc cũng không thay thế yêu cầu object-specific spec/kiểm chứng cấu trúc. Cần baseline cùng input, model và ngân sách trước khi kết luận.

## Hướng sửa đề xuất

Chuyển điểm điều khiển từ “sửa vài chuỗi code để giống ảnh” sang semantic Scene IR và part contracts: type, geometric construction, openings/cavities, wall thickness, attachment, material slots và runtime capabilities. LLM quan sát/đề xuất các thuộc tính, compiler và generator có kiểm thử hiện thực, semantic validator kiểm tra những thuộc tính đó trên geometry/representation thực. Custom TS dành cho kiến trúc chưa được library hỗ trợ, vẫn phải qua các contract tương ứng.

Giữ code generator, spec/params và compiled assets riêng. Landmark có ngân sách/asset riêng; các cấu kiện chuẩn và kit được dùng lại. Ngày/đêm, thời tiết, ánh sáng, seed hình thái và hành vi thuộc những lớp khác nhau. Chi tiết chiến lược: `specs/002-urban-grid-style/scalable-world-architecture.md`.

Chưa triển khai đầy đủ semantic IR hoặc sửa mọi ống khói trong output; không dùng một chỉnh sửa tay cho riêng case này để trình bày thành thành công của workflow.
