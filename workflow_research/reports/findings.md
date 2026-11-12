# Kết quả nghiên cứu workflow công trình 3D

Ngày thực hiện: **11/11/2026, Asia/Saigon**. Phạm vi: ảnh công khai cố định, nghiên cứu khả thi và tối ưu vòng đầu. Không triển khai input liên tục.

## Kết quả chính

Workflow đã gọi API thật, sinh mã procedural tự do, kiểm tra TypeScript và mesh, render Three.js từ năm góc chuẩn, so sánh với ảnh gốc và thử sửa. **Sáu cấu hình chính trên ba công trình đều có candidate hợp lệ**, nhưng chưa đạt mức fidelity có thể chứng nhận. Có thêm thử nghiệm camera và ba run lỗi tích hợp được giữ nguyên.

| Công trình | Direct: điểm candidate giữ lại | Spec: điểm candidate giữ lại | Quan sát trực tiếp |
|---|---:|---:|---|
| Rietveld | 0,517 | 0,648 | Spec giữ được phân lớp trắng/xám và mái tốt hơn; chiều sâu và cánh trái còn sai. |
| Bauhaus | 0,595 | 0,750 | Nhận diện được tường kính, tháp chữ và cửa đỏ; bố cục, tỷ lệ chiều dài và khối phía sau vẫn xấp xỉ. |
| Fallingwater | 0,460 | 0,450 | Nhận được bản sàn đua và trụ đá nhưng khối tích, hỗ trợ kết cấu và tổ chức kính còn sai; cả hai chưa đạt. |

Các số trên là trung bình sáu tiêu chí VLM, **không phải phần trăm chính xác**, không đủ kết luận spec thắng phổ quát. Tập mẫu đều là kiến trúc hiện đại nổi tiếng, chưa đại diện nhà phố/chung cư/mái phức tạp; prior kiến thức model có thể ảnh hưởng. Không có held-out và chưa chạy lặp nhiều seed.

## Những thay đổi đã thử và quyết định giữ/bỏ

1. **Direct → phân tích spec trước khi sinh code.** Cùng ảnh, cùng model `gpt-6-sol`, cùng renderer và rubric. Rietveld/Bauhaus tốt hơn theo rubric; Fallingwater không tốt hơn và có một lỗi TypeScript ban đầu. Giữ như phương án có triển vọng để tiếp tục nghiên cứu, chưa coi là mặc định tối ưu cho mọi mẫu.
2. **Sửa theo vùng code sau review.** Bauhaus spec tăng từ **0,598 → 0,750**, bản sửa được giữ. Direct Rietveld **0,517 → 0,437**, direct Bauhaus **0,595 → 0,570**, direct Fallingwater **0,460 → 0,423**, spec Rietveld **0,648 → 0,632**: giữ bản trước. Các ảnh và patch bị loại vẫn còn nguyên. Đây là bằng chứng cần rollback, không phải mọi vòng refinement đều giúp.
3. **Tách sửa camera khỏi geometry.** Sau khi review Rietveld xác định camera sai, giữ **chính xác cùng checksum source**, chỉ đổi `(35°,12°)` thành `(-30°,2°)`. Điểm **0,648 → 0,702**; ảnh trực tiếp cho thấy góc nhìn gần ảnh chụp hơn. Giữ chế độ `--refinement-scope camera` để xử lý lỗi camera trước. Đây vẫn là giả thuyết góc chụp, chưa phải hiệu chỉnh camera định lượng.
4. **Sửa lỗi compile bằng deterministic feedback.** Fallingwater spec ban đầu TS2488 do suy luận union type, chưa render và không gọi VLM để chấm ảnh không tồn tại. Patch cục bộ sửa type, sau đó geometry gate và renderer mới chạy. Candidate có hình nhưng vẫn còn critical defect; trạng thái partial.

## Kiểm tra evaluator

Model chính `gpt-6-sol` chấm Bauhaus trước/sau 0,598/0,750. Một call độc lập dùng model có thật trên gateway `gpt-6-luna`, trình bày thứ tự ảnh đảo ngược, chấm **0,748/0,775** và cũng ưu tiên bản sửa. [Review độc lập và lý do](reliability/smoke-bauhaus-spec-v2/pair-review.json).

Cả hai đồng ý chiều cải thiện, nhưng chênh lệch điểm tuyệt đối và biên cải thiện lớn. Kiểm tra trực tiếp cho thấy đây là thay đổi tỷ lệ/chi tiết vừa phải; không diễn giải mức tăng 0,152 của model chính thành cải thiện vật lý tương ứng. Một cặp/một model phụ chưa đo được độ ổn định, độ đồng thuận với người thật hay calibration. Không dùng VLM làm tiêu chí duy nhất: TypeScript, topology/normals/self-intersection, ngân sách, ảnh thật và kiểm tra trực tiếp vẫn độc lập.

## Chi phí, thời gian và cache

Tổng cả run lỗi và review độc lập: **30 API attempts, 202.891 tokens được gateway báo cáo**. Chưa có bảng giá đáng tin của gateway, nên **USD chưa xác định**, không ghi bằng 0. [Bảng đầy đủ](comparison-table.md), [số liệu máy đọc](experiment-summary.json), [usage từng run](index.html).

Các run direct không cache mất khoảng **187–231 giây**. Nhiều run spec dùng lại analysis/code từ các lượt sửa adapter; vì vậy **không so thẳng wall time 62/111/272 giây với direct để kết luận nhanh hơn**. Script tổng hợp đã cộng lại lượng token/API time tương đương của những response cache được dùng:

| Cấu hình | Tokens tương đương không cache | Tổng thời gian API tương đương |
|---|---:|---:|
| Rietveld direct | 23.439 | 173,3 giây |
| Rietveld spec + targeted | 37.510 | 237,2 giây |
| Rietveld spec + camera | 32.901 | 204,9 giây |
| Bauhaus direct | 26.369 | 208,2 giây |
| Bauhaus spec | 41.874 | 302,6 giây |
| Fallingwater direct | 25.968 | 206,5 giây |
| Fallingwater spec | 26.051 | 175,5 giây |

Đây là cộng response đã quan sát, **không phải đo cold end-to-end mới**, không tính phí lần hai và không chứa toàn bộ compile/render. Structured/camera tăng chất lượng một số mẫu nhưng không miễn phí; chưa xác định Pareto frontier ổn định vì thiếu repeated trials, calibrated quality và giá USD. Báo cáo HTML có đồ thị quality–tokens/time và tách rõ cache.

## Các lỗi tìm được bằng kiểm tra thật

- Gateway quảng bá ID `gpt-6-sol`; cấu hình CASEPILOT có `openai/gpt-6-sol` làm request thử bị `model_not_found`. Adapter chuẩn hóa ID; không sửa `.env`.
- Hai run analysis đầu trả provenance dưới tên `source_region` / `source region`; schema từ chối trước khi sinh code. Đã thêm alias rõ ràng giữ nguyên giá trị quan sát. Hai run thất bại vẫn được thống kê.
- Gate upstream đo độ thuôn lưỡi dao bằng substring `blade` trong tên mesh, nhầm các vách kiến trúc. Adapter dùng role architectural và mapping ID tường minh để không chạy weapon-specific gate; **không thay vertices, normals, topology hay ngưỡng kiểm tra**. Cả hai candidate lỗi của run `smoke-rietveld-spec-v2` được giữ.
- Ảnh Commons tên Villa Savoye thực ra chụp ghế nội thất. Đã mở ảnh, loại khỏi benchmark trước gọi reconstruction và thay bằng Fallingwater ngoại thất. Có [rejected-sources.json](../data/rejected-sources.json).
- Snapshot nguồn được render trong Chromium thật, không xuất ảnh giả. Đã mở ảnh so sánh trước/sau và các multi-view sheets; mặt sau của mô hình còn sơ lược do không có bằng chứng.

## Workflow đề xuất cho đợt tiếp theo

Giữ cấu trúc **intake → observations/spec → procedural source → deterministic gates → multiview → structured review → sửa camera hoặc component → chọn incumbent → export artifacts**. Dùng camera-only khi review phát hiện camera sai; với lỗi geometry, chỉ sửa một nguyên nhân lớn trong mỗi lượt để giảm regression. Giới hạn calls/tokens/time, giữ best candidate và dừng khi hết budget; không lặp cùng lỗi vô hạn.

Đây là khuyến nghị thực dụng cho nghiên cứu tiếp, chưa phải cấu hình được chứng minh tối ưu. Trong đợt này chưa đủ bằng chứng giữ mọi thay đổi theo yêu cầu ổn định ở tài liệu dài hạn. Cần kiểm chứng camera-first trên nhiều mẫu trước khi đổi default targeted hiện tại.

## Chưa hoàn thành và hướng nghiên cứu

1. **Native img2threejs baseline đủ tám pass vẫn incomplete**. Đã nghiên cứu source, pin commit, dùng probe/state/next, nạp skill theo giai đoạn và gate geometry thật. BuildingSpec nghiên cứu **không được gọi là ObjectSculptSpec 2.1**; strict-quality và các pass native chưa được giả đánh dấu xong. Cần hoàn tất baseline này trước khi kết luận về mức tối ưu so với upstream.
2. Cần foreground mask, camera fitting có kiểm chứng và landmark/facade annotations để có metric xác định. **IoU/SSIM/3D error hiện unavailable**; ảnh background tự nhiên và một camera giả thuyết không đủ điều kiện dùng metric ảnh.
3. Cần 8–12 development buildings đa dạng, held-out chưa dùng, repeated runs và review từ người. Chưa có dữ liệu đủ cho chứng minh tổng quát, độ ổn định hay chọn model tốt nhất.
4. Chưa có texture/projection, phong cách cartoon độc lập, GLB export, tọa độ mét/GIS, ghép city hay input liên tục. Có `scene.json` và source rerunnable; đó chưa phải city pilot.
5. Sandbox Chromium có CSP/network denial, credential separation và process watchdog; chưa phải hard OS quota/multi-tenant isolation. Docker daemon hiện không hoạt động; không cần thêm dịch vụ để chạy lại phạm vi local hiện tại.

Nguồn chính: [img2threejs đã nghiên cứu](https://github.com/img2threejs/img2threejs/tree/0c0c49bc168e648dbaf9c8c080474de0b3a941b6), [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence), nguồn ảnh/giấy phép ở [manifest](../data/samples.json). Tất cả key giữ trong `.env`, không đưa vào source sinh ra hay report.
