# Rà soát chất lượng urban pilot và hướng thay đổi

Ngày 12/11/2026. Theo phản hồi người dùng: style phải mô tả phong cách rõ ràng, linh hoạt; không áp bảng màu hay quy tắc hình thức cứng lên objects. Đợt này chỉ đọc code, input/artifact và kiểm tra ảnh; **chưa sửa pipeline hoặc sinh scene mới**.

## Kết luận

Kết quả hiện tại không đáp ứng mục tiêu tái tạo đô thị có chi tiết theo ảnh. Vấn đề nằm ở hợp đồng style, material binding, thiếu bằng chứng theo object, generator quá tổng quát và quality gate chưa đánh giá đúng sản phẩm. Việc 24 tests qua chỉ chứng minh một số hợp đồng kỹ thuật, không chứng minh chất lượng hình ảnh. Task list cũ là phạm vi pilot kỹ thuật, không nên dùng làm bằng chứng đã đạt mục tiêu thị giác.

Đã xem lại `renders/styled-street.png`, ảnh factual Nhà hát và source thực tế của run `district1-final-v4`, đồng thời đối chiếu các ảnh overview/landmark đã kiểm tra trong lượt trước. Không quy lỗi cho model hoặc thiếu token khi chưa tách các nguyên nhân này.

## Các phát hiện có bằng chứng

| Mức | Vấn đề | Bằng chứng và tác động |
|---|---|---|
| P0 | Style bị định nghĩa thành palette/material override | `urban/style.py:12,29,77` bắt buộc 13 màu RGB, gọi style là material-only. `urban-viewer.mjs:106,122` thay material mọi mesh theo role. Mái đỏ, chân đế nâu và vật liệu riêng không có đường giữ identity độc lập với palette. Prompt còn có câu “Observe bright architecture”, tạo thiên hướng không phù hợp mọi style. |
| P0 | Texture có tải nhưng bị làm mất thông tin | `urban-viewer.mjs:33–34` chuyển màu texture sang luminance rồi nhân tint. `:26` normal intensity bằng texture_strength × 0.25. `assets.py:14` cố định asphalt cho road, concrete_floor cho cả pavement/building. Roof/glass/metal/accent không có texture tương ứng trong registry này. |
| P0 | Không có quy trình tạo texture theo bề mặt thực | Chưa có face segmentation, rectification, atlas/baking cho facade/roof, de-lighting hay kiểm tra seams. Bật PBR maps không tự tạo cửa thật, mái ngói, chân đế và phù điêu. Màu texture bị bỏ càng làm mất nhận dạng. |
| P0 | 35 công trình chưa được quan sát bằng ảnh | `generate.py` gọi codegen với danh sách tên/type/height/floors/area/số góc, không đính ảnh và không gửi tọa độ footprint đầy đủ ở thời điểm suy luận; footprint đầy đủ chỉ có khi generator chạy. Chỉ 1/36 có nhánh factual photo. 27/36 có `building=yes`, quá ít thông tin để chọn kiến trúc. |
| P0 | Generic generator không tái tạo từng công trình | Source thực `building-generator.ts:89–154` extrude một footprint lên toàn bộ chiều cao rồi lặp cửa theo bay/floor, chia ít nhóm loại nhà. Mặt trên khối cũng dùng material building. Không có phân tích hình khối mái, setback, khối đế, podium, balcony hoặc facade grammar riêng từ ảnh. |
| P0 | Nhánh Nhà hát vẫn suy đoán hình học nhiều | `objects/.../generator.ts:69–76` dùng rotation và kích thước khối số cố định; không fit ảnh/camera/landmarks. Chỉ có một ảnh chính diện; chưa có ảnh mái/top-down. Các khối/roof và chi tiết bước thang/tượng không được đối chiếu theo view đã căn camera. Số cố định trong một asset không tự nó là lỗi; ở đây chúng thiếu nguồn đo/fit và hợp đồng tái sử dụng. |
| P1 | Chia grid chưa chia nhiệm vụ quan sát | `data.py:90–91` tạo bốn cell, nhưng codegen/render vẫn xử lý toàn bộ AOI; chưa có workflow quan sát theo cell hoặc từng object. Giảm kích thước grid mà giữ nguyên prompt/input sẽ không giải quyết thiếu chi tiết. |
| P1 | Streetscape nhiều giá trị giả định | Cây cùng ba tán sphere low-poly, đèn cùng hình và hướng tay đèn; đặt cây theo khoảng cách 14 m. Trong output: 16 cây có node OSM, 334 cây suy diễn; 6 đèn có node OSM, 105 đèn suy diễn. Cắt danh sách 350 cây/120 đèn có thể tạo phân bố không đồng đều theo thứ tự input. |
| P1 | Đường chỉ đúng phép hợp bề mặt, chưa đúng hình thái nút giao | Mặc định bề rộng đường/vỉa hè, buffer centerline và trừ occupied. Vạch đứt đặt theo từng way, phase lấy seed theo ID; không phải một lane graph liên tục qua giao lộ. Union/clipping không có khe hở không chứng minh lane, curb, crossing, elevation và traffic topology đúng. |
| P1 | Review chưa là quality gate | Graph đi review → finalize, không có nhánh sửa hình ảnh/đánh giá lại theo issue. Chỉ compile/geometry được retry tự động. Khi có nhiều object refs, reviewer/report vẫn chọn object đầu tiên. Geometry gate và height tolerance không kiểm chứng facade landmarks, silhouette, UV, footprint containment hay giao cắt toàn scene. |
| P1 | Cache chưa theo đầy đủ dependency | Có file source/observation thì skip; run config hash manifest ảnh nhưng không hash nội dung ảnh factual được tham chiếu. Cell hash chưa có cây/đèn/parks, referenced object content, source generator và asset versions. Thay input có thể không invalidation đúng nếu tiếp tục cùng artifact. Chưa có runtime mesh cache/streaming thực. |
| P2 | AOI/render bị gắn với pilot | Tâm AOI, 2×2 grid, đất 410 m, biên vạch đường ±200 m, camera/grid và hướng nắng cố định. Source hiện có nhánh tìm tên địa điểm với chuỗi ký tự không sạch. Những giá trị này cần thành config hoặc suy từ bounds trước khi chạy khu khác. |

Các giới hạn resource, kiểm tra path/hash, chặn mạng worker và geometry validity nên giữ. Không đánh đồng hardcode an toàn với giả định thẩm mỹ/địa lý. Vẫn cần tọa độ/ownership và identity có nguồn làm ràng buộc reconstruction; phản hồi này loại bỏ ràng buộc style không hợp lý.

## Style cần thay thế như thế nào

Thay bảng màu theo role bằng bản mô tả ý đồ nghệ thuật dựa trên ảnh, có evidence, uncertainty và conflicting references. Không có danh sách phong cách đóng, RGB bắt buộc hoặc mặc định ép vật liệu về cùng màu.

Ví dụ mô tả phù hợp ảnh người dùng: “Diorama kiến trúc nhìn xiên, cảm giác mô hình thu nhỏ; hình khối và các chi tiết nhận dạng vẫn đọc rõ; bề mặt có chất liệu, phân lớp cây xanh tự nhiên, bóng đổ giúp tách khối; giảm nhiễu vi chi tiết khi nhìn toàn cảnh.” Đây là diễn giải đề xuất để kiểm chứng, không là preset cứng. Vật liệu/màu riêng như mái ngói, sơn, đá, kính đến từ bằng chứng object. Style hỗ trợ mức trừu tượng hóa, cách thể hiện bề mặt, ánh sáng và bố cục; không ghi đè factual appearance. Các tham số renderer vẫn cần tồn tại nhưng là quyết định có thể thử nghiệm, không là giới hạn bắt người dùng tuân theo.

Material identity cần nhiều slot/asset riêng cho từng bề mặt: facade paint/plaster, roof tile, stone plinth, glazing, frame, relief, signage… Slot mở rộng được; không đồng nhất toàn bộ building thành một material chung. Tách bản reconstruction gốc và bản được diễn giải style để truy nguyên sai khác.

## Pipeline đề xuất để thử tiếp

1. Chọn một cụm nhỏ gồm một landmark và 2–3 công trình lân cận có dữ liệu ảnh đủ dùng; kích thước AOI là kết quả của số object/coverage, không đặt một kích thước cố định cho mọi nơi. Giữ vùng context rộng hơn cho đường và địa lý.
2. Tạo gói evidence riêng mỗi object: footprint/height có nguồn, ảnh top-down thật, mặt đứng và ảnh xiên nếu có, crop riêng, nguồn/quyền dùng, thời gian, hướng nhìn và confidence. Ảnh style độc lập. Không dùng ảnh sinh làm bằng chứng địa lý. Top-down giúp mái/khối/bố trí, không thay được ảnh mặt đứng bị che khuất.
3. Phân tích context một lượt để gắn object với địa lý; sau đó quan sát từng object, rồi từng facade/roof khi cần. Lưu part graph, landmark points, phân vùng material và sự bất đồng dữ liệu. Thiếu input thì ghi unknown hoặc yêu cầu bổ sung; không lặng lẽ đẩy generic detail thành reconstruction.
4. Sinh và kiểm tra theo thứ tự: mass/roof/silhouette → facade opening/proportion → chi tiết nhận dạng → texture/material → style presentation. Mỗi bước render cận cảnh, camera đối chiếu căn gần đúng có lưu thông số; sửa issue cụ thể rồi so sánh trước/sau. Không chờ tới cuối scene mới nhìn ảnh nhỏ toàn cảnh.
5. Vật liệu dùng PBR phù hợp từng bề mặt; UV theo mét hoặc atlas/triplanar phù hợp mesh. Với ảnh có quyền dùng và đủ coverage mới thử rectification/baking, xử lý ánh sáng đã có trong ảnh và seams. Giữ albedo và điều khiển texture độc lập khỏi style. Normal map không thay được silhouette hoặc cửa mở sâu.
6. Giữ road/lane/intersection graph toàn cục; cell chỉ sở hữu fragment, object refs và UV phase. Object asset và source module có version/dependency riêng. Chỉ reuse phần cấu tạo phù hợp như cửa/cột/curb và asset đã kiểm chứng; không reuse cùng facade cho mọi tòa nhà.
7. Quality report theo từng object/view/surface: observed coverage, silhouette/landmarks, proportions, material/UV, detail visibility, collisions, continuity, performance. Tách trạng thái technical-valid khỏi visual-accepted; issue nghiêm trọng không được kết thúc như đã đạt mục tiêu. Ngưỡng đo và camera cần kiểm chứng trước khi gọi metric là độ chính xác.

## Thử nghiệm kiểm chứng nguyên nhân

- Cùng camera/geometry: tắt global material override và shader grayscale; so material native để tách lỗi texture khỏi lỗi model.
- Cùng một object: so các bước mass → facade → texture; chưa áp style cho tới khi identity đọc được.
- So input một ảnh với gói top-down + facade + oblique của cùng object. Không thay đồng thời renderer/model để giữ khả năng quy nguyên nhân.
- Chỉ sau khi landmark và vài neighbor đạt hình ảnh mới mở rộng sang nhiều cell, đo cold/warm cache và kiểm tra biên.

Các thử nghiệm này là đề xuất, chưa chạy trong lượt audit. Không hứa chỉ chia nhỏ cell hoặc thay model sẽ tự khắc phục thiếu dữ liệu.

Tham khảo kỹ thuật đã đối chiếu: [Three.js Texture](https://threejs.org/docs/pages/Texture.html) (UV/repeat/color space), [MeshStandardMaterial](https://threejs.org/docs/pages/MeshStandardMaterial.html) (PBR maps và environment lighting). Renderer hiện chỉ có hemisphere/directional light, chưa có environment map, góp phần làm kính/kim loại kém thuyết phục; nguyên nhân chính vẫn là input/geometry/material contract.
