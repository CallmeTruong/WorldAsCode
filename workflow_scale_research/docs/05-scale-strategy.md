# Chiến lược scale sau pilot

## Đơn vị tái sử dụng

Không tạo một file agent khổng lồ cho mỗi tile. Chia dữ liệu thành scene evidence, asset blueprint, asset instance, global network và runtime state. Quan sát toàn cảnh để nắm quan hệ; dành ảnh gần và quy trình native nhiều pass cho landmark hoặc family chưa có recipe phù hợp. Các ảnh góc nhìn toàn cảnh hỗ trợ layout, không đảm bảo chi tiết vật lý mà ảnh không phân giải được.

| Nhóm | Lưu và tái sử dụng | Thay đổi khi nào |
|---|---|---|
| Đường, vỉa hè, ray | Graph global, mặt cắt, lane/marking rules, material slots, stationing | Graph/thông số mặt cắt hoặc style vùng đổi; không reset ở biên tile |
| Cây, đèn, biển, phụ kiện | Generator version, tham số, seed channels, material variants | Seed hình thái trong giới hạn; vị trí từ evidence giữ cố định |
| Nhà phổ biến | Family blueprint, footprint/height constraints, roof/facade modules | Chọn family khác hoặc variant có evidence; không random landmark thành nhà chung |
| Landmark | Factory TS riêng + native spec/evidence/reviews + code overlays | Cập nhật version có review và regression nhiều góc |
| Xe, tàu, người, động vật | Asset/rig riêng và controller/path/behavior state | Pose/occupancy/behavior chạy ở runtime; không để tile code sở hữu toàn bộ actor |
| Ngày/đêm/thời tiết | Bindings material/light/shader, không nhân bản mesh | State update; có appearance key riêng nếu thay material package |

Geometry key chứa recipe, compiler hash, version và shape seed khi shape được phép thay. Appearance key chứa material definition. Màu hoặc thời gian không làm đổi geometry key. Content-addressed asset store giữ dependencies; code quyết định quan trọng phải có recipe/overlay, không chỉ giữ ảnh đẹp cuối cùng.

## Đường và biên vùng

`NetworkEdge` có ID global, points XYZ, width/gauge và station. `tile_fragments` chia centreline tại mặt phẳng grid, xuất owner/references và ports dùng cùng position/tangent/elevation/width/gauge/phase. Texture repeat lấy từ station global. Có test đường đi qua nhiều tile và đổi hướng; phase không quay về 0 ở biên. Điều này chưa phải implementation giao lộ, lane changes hoặc bridge/rail clearance hoàn chỉnh.

Renderer dùng local coordinates; World IR có origin địa lý và đơn vị ENU mét. Dữ liệu height mâu thuẫn cần confidence và prior thay vì lấy giá trị cuối cùng. Landmark native dùng đơn vị riêng cần scale theo kích thước đã kiểm chứng; không nonuniform stretch để che lỗi silhouette.

## Scheduler và QA

DAG mong muốn: source snapshot → scene analysis → asset classification/cache lookup → landmark/family jobs → per-asset gates → tile assembly → seam/network checks → held-out scene review → atomic publication. Jobs theo asset ID và evidence version, không theo mỗi góc chụp. Budget phân bổ theo projected pixel size, độ nổi bật, mức thiếu thông tin và độ mới của family.

Pilot đã có content cache, SQLite leases, run lock, request usage ledger và bounded native corrections. Chưa có distributed worker service hoặc throughput thành phố. Khi scale thật, dùng coordinator có transactional claims, object storage cho artifact, GPU render workers có pool, admission kiểm tra trùng reference và queue riêng cho expensive landmarks. Chỉ retry compute xác định; paid request không rõ trạng thái phải đối soát.

## Dữ liệu diện rộng

Giữ provider boundaries: Google Photorealistic 3D Tiles qua Cesium ion cho evidence tổng thể/multi-view; OSM cho footprint, đường và tags; DEM/terrain provider cho cao độ khi cần. Không phụ thuộc PLATEAU hay tên riêng Tokyo. Dataset thử nghiệm hiện là snapshot ảnh Cesium/Google đã có trong workspace, không phải service ingestion mới đang chạy.

API đang có không bảo đảm ảnh mặt đứng hay coverage độ phân giải cho mọi công trình. Provider adapter cần capability/coverage probe theo AOI và nguồn bổ sung khi thiếu, không đoán hình học cực chi tiết từ vài pixel. Không cần thêm key chỉ để chạy fixture hiện tại. Bộ fetch/lập lịch input liên tục và đối soát catalog đa provider là phần triển khai sau pilot, đúng phạm vi người dùng chưa cần input liên tục.

## Các mốc phải chứng minh trước production

1. Một landmark đạt đủ native passes, semantic checks và held-out visual review.
2. Một cụm nhỏ nhiều loại asset đạt identity/style và không có nhà trắng placeholder.
3. Hai tile liền nhau không đứt đường/ray hoặc lặp phase; native landmark không bị cắt đôi.
4. Đo p50/p95 model latency, GPU memory/draw calls, cache hit rate, token cost và correction rate bằng run thực.
5. Thêm LOD/instancing/tile streaming, rồi benchmark vùng lớn hơn. Không nhân tuyến tính thời gian một landmark thành chi phí cả thành phố và gọi đó là benchmark.
6. Actor/traffic/rail/animal simulation phải có test và execution riêng, không coi schema đã đủ.
