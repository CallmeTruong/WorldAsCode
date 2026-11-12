# Kết quả sửa workflow sau audit chất lượng

12/11/2026. Bản xem mới: [district1-quality-v10](../../runs/urban/district1-quality-v10/index.html), [viewer localhost](http://127.0.0.1:8765/district1-quality-v10/viewer.html). Đây là bản sửa pipeline có kiểm tra bằng ảnh thật; độ giống kiến trúc vẫn **partial**, không coi scene đã đạt photorealism.

## Những thay đổi đã triển khai

- Bỏ schema 13 màu và toàn bộ global palette/material override. Style là mô tả ý đồ nghệ thuật, form/detail, surface expression và lighting/composition; không trích RGB hoặc áp preset cứng. Intent tham gia bước lập kế hoạch/sinh từng object. Thử nghiệm ánh sáng nằm trong file riêng, không được đổi màu/vật liệu/texture object.
- Renderer giữ material native theo từng bộ phận, hỗ trợ tên/slot mở rộng. Bỏ shader chuyển texture thành grayscale. Ngói/đá/đường giữ albedo maps; bề mặt sơn lấy màu từ object và dùng normal/roughness, tránh nhân màu sơn với vết bẩn của scan khác. Đây là chính sách vật liệu bề mặt, không phải màu của style.
- AOI/grid cấu hình được. Pilot thu nhỏ 220 × 220 m quanh Nhà hát, Continental, Caravelle: 3 object có ảnh riêng và 8 proxy bối cảnh. Không giả lập mặt đứng cho 8 proxy. Không tự rải cây/đèn thiếu bằng chứng hoặc bịa vạch làn; snapshot AOI này không có node cây/đèn tương ứng.
- Từng object có ảnh factual, part plan, source module, render trước mặt và từ trên, review riêng. Nhà hát có thêm ảnh xiên để quan sát mái; chưa có ảnh top-down factual. Footprint diagram ghi rõ không phải ảnh aerial. Height conflicts được lưu với giá trị nguồn và mức suy diễn; không coi đếm tầng từ ảnh là đo đạc.
- Thêm vòng sửa thị giác có giới hạn, giữ issue và trước/sau. `technical_valid` tách khỏi `visual_accepted`; lỗi critical/major chặn trạng thái đạt hình ảnh. Cả ba vẫn còn lỗi sau đợt này.
- Factual image bytes tham gia signature; cell dependencies có cây/đèn/parks, referenced building content, source và asset registry. Có tùy chọn resume cập nhật code được ghi lịch sử, chỉ cho đổi implementation hash, không đổi input hoặc ngân sách.
- Geometry giống nhau được chia sẻ trước serialize/gate; mesh lặp được instancing theo geometry/material, giữ transform từng object. Module cache đồng bộ từ source đã kiểm tra cuối, giữ bản cũ để truy vết.

## Sửa và kiểm tra trực tiếp

Đã sửa các lỗi source đóng khối/tham số, hole chạm outer ring của cửa vòm và TubeGeometry hở đầu. Geometry gate thật vẫn được giữ. Một bản vá LLM thêm LOD sai mục tiêu bị loại; nguyên nhân là phần evidence bị cắt trước danh sách lỗi thật. Prompt sửa kỹ thuật nay lấy trực tiếp `ACTUAL_GATE_FAILURES` và không coi metadata LOD là lỗi mặc định.

Hai lỗi điều phối khác đã sửa và có regression test: patch function không được kiểm như module bắt buộc export factory, và giới hạn 12 edits không được loại cả bản vá Caravelle có 18 điểm sửa hợp lệ. Giữ giới hạn hữu hạn 64 edits và unique anchors, validate module sau khi ghép.

Đã raycast scene để xác nhận khối backing ở trước kính Caravelle khoảng 0.065 m. Đẩy backing về sau kính, giữ vị trí/màu pane; không dùng đổi style để che lỗi hình học.

Nguồn ảnh/giấy phép của ba công trình lưu trong `inputs/object-references/cluster-manifest.json` và report. Ảnh xiên Caravelle được dùng làm context cho Nhà hát nhưng phải ghi đúng tác giả/giấy phép của ảnh đó, không gộp vào credit ảnh chính diện.

## Số liệu có bằng chứng

- Trước chia sẻ: 3,371 geometry trùng lặp, scene JSON khoảng 65.2 MB, geometry payload khoảng 50.6 MB; gate vượt watchdog 240 giây.
- Sau exact-content sharing: khoảng 244 geometry độc lập ở candidate trước sửa thị giác; scene JSON khoảng 8.6 MB và geometry payload 4.3 MB. Số geometry có thể tăng sau khi thêm chi tiết.
- Trước instancing: 3,404 draw calls; sau instancing ở candidate v9: 340 draw calls. Hai candidate có một số thay đổi detail/camera nên không coi đây là benchmark hình ảnh hoàn toàn kiểm soát; cấu trúc renderer đã loại phần draw lặp.
- Full regression chạy riêng tài nguyên: **34 passed in 44.70s**. Lượt chạy đồng thời với urban render có hai timeout ở renderer cũ; sau khi không tranh tài nguyên đã qua lại, không nới timeout để che lỗi.
- Test gồm style không palette, lighting không override appearance, factual image hashing, dependencies, unique patches, patch 18 edits, evidence không mất lỗi gate, code-resume không đổi budget/input, đồng bộ module và worker geometry dedup/bake rotation.

Số liệu cuối của bản đang chọn đọc tại [runtime](../../runs/urban/district1-quality-v10/urban-runtime-result.json), [usage](../../runs/urban/district1-quality-v10/usage.json), [review](../../runs/urban/district1-quality-v10/quality-review.json). Timing CPU submission không phải FPS. Chi phí USD chưa có đơn giá gateway xác nhận.

Kiểm tra cuối đã hoàn tất: [browser checks](../../runs/urban/district1-quality-v10/viewer-checks.json), [viewer screenshot](../../runs/urban/district1-quality-v10/viewer-preview.png). Không có page errors; cả ba object được chọn riêng; geometry/material fingerprints giữ nguyên khi đổi presentation. Đã xác nhận mái ngói còn albedo map, sơn giữ màu intrinsic cùng normal/roughness maps. Bản cuối có 341 draw calls, 133,619 visible triangles ở overview, 353 renderer geometries và 18 textures; styled CPU submission median 6.4 ms, p95 8.9 ms. Renderer cuối mất 189.4 giây và peak process-tree RSS khoảng 1,167 MB trên máy thử.

Tổng đợt sửa v6–v10: **24 API attempts, 180,709 input tokens + 47,290 output tokens = 227,999 tokens**. Xem [metrics tổng hợp](quality-experiment-metrics.json). Đây là tổng nghiên cứu gồm cả lần lỗi, source repair và các lượt review, không phải chi phí cold-start trung bình của một khu vực. USD vẫn chưa xác nhận. Không cộng `active_seconds` thành tổng thời gian nghiên cứu: có các lần render lỗi không checkpoint thời gian và có thời gian kỹ sư sửa/kiểm tra riêng.

Các chỉnh sửa đã được kiểm tra thành phần nhưng đợt nghiên cứu vẫn cần can thiệp kỹ thuật vào source và bước điều phối. Không coi đây là bằng chứng workflow tự động đạt chất lượng với mọi input mới. Các lỗi đã gặp được chuyển thành regression checks và evidence đầy đủ để tránh lặp lại.

Các run v6–v10 giữ cả lỗi compile, timeout, bản vá bị loại và lượt sửa. Token/calls của v10 chỉ là lượt kiểm tra cuối có cache, không phải tổng chi phí tạo ba công trình từ đầu. Báo cáo đo tổng hợp riêng đi kèm.

## Phần chưa đạt

Các tượng/phù điêu, tỷ lệ vòm/mái, balcony/canopy, khối đế và mặt đứng bên/hậu vẫn chưa khớp hoàn toàn ảnh. Chưa có camera calibration, texture atlas/baking từ ảnh factual, mái có ground truth top-down, terrain hay lane/intersection graph. Vật liệu PBR tái sử dụng không được gọi là texture thực của từng tòa nhà.

Phong cách linh hoạt đã vào contract và prompt, nhưng renderer hiện chỉ thực thi lựa chọn ánh sáng ở nhánh presentation; không tuyên bố hỗ trợ mọi hiệu ứng nghệ thuật. Streaming/LOD đô thị lớn và benchmark nhiều AOI còn pending. Cần thêm ảnh nhiều góc và kiểm tra phần kiến trúc cụ thể trước khi mở rộng diện tích.
