# Chất lượng, công trình mới và khả năng scale — 2026-11-13

## Kết luận từ thực nghiệm

Đã dựng và đánh giá ba công trình thật trong cùng khu Marunouchi, dùng OSM + Google Photorealistic 3D Tiles qua Cesium ion và cùng ảnh style của người dùng. Cùng phiên bản kit v6 dựng được cả mái phức tạp, văn phòng thấp và khối cao tầng. Cả ba bản đã đánh giá đều qua metric hình học, nhưng **chưa bản nào đạt ngưỡng visual acceptance**. Không coi điều này là benchmark đa thành phố hoặc hệ thống đô thị hoàn thiện.

Có cải thiện cụ thể: nhánh `fix-design` nay thực sự sửa và đánh giá code trong workflow; chi tiết văn phòng tăng từ 0,43 lên 0,52. Batching giảm draw call cho chín bản sao từ 9.018 xuống 118. Ngược lại, chuyển nguyên recipe văn phòng thấp sang tòa cao tầng chỉ đạt likeness 0,39 dù hình học vẫn qua: tái sử dụng kit không đồng nghĩa dùng chung mọi recipe.

## Dữ liệu và kiểm tra input

| Công trình | OSM | Input | Phạm vi |
|---|---|---|---|
| Mitsubishi Ichigokan Museum | way/306116935 | Bundle calibrated + height field có sẵn | Cảnh phát triển ban đầu |
| Marunouchi 2-chome building | way/145394389 | Năm góc chụp mới + outline, height 35 m/9 tầng từ OSM làm prior | Công trình mới, mái bằng và khối kỹ thuật trên mái |
| Khối văn phòng height 115 m | way/145394367 | Năm góc chụp mới + outline/height OSM làm prior | Công trình mới, mặt đứng nhiều lá đứng |

Các prior được fit lại theo ảnh; chiều cao cuối cùng không phải cứ lấy nguyên tag. Chẳng hạn main roof văn phòng thấp khoảng 31,7 m, phần cao nhất khoảng 42,2 m theo fit; đây là ước lượng photogrammetry, không phải khảo sát.

`worldscale.capture_site` nhận OSM way bất kỳ, ước lượng ground từ các mẫu bề mặt xung quanh, clip footprint và ghi camera/projection thực của từng góc. Token chỉ dùng trong SDK viewer, không lưu vào bundle hoặc prompt. SDK viewer hiện chạy bằng dịch vụ reference có sẵn trong package cũ; module mới không import application code cũ. Chưa đóng gói viewer/provider server thành một dịch vụ độc lập mới.

Đã mở trực tiếp ảnh input: lần chụp đầu có nền sao và sắc xanh. Chụp lại với clock cố định gần giữa trưa địa phương và nền đen đã loại bỏ nền sao, nhưng sắc xanh vẫn còn đáng kể: không thể quy mọi sai màu cho giờ chụp. Baked texture, bóng, thiếu mặt dưới và clipping theo outline gần đúng vẫn ảnh hưởng input. Observer phải tách material identity khỏi màu bị ám và không tái tạo các lỗ mất mesh thành kiến trúc thật.

Lần chụp khối 115 m đầu tiên không đạt điều kiện tiles-ready trong 60 giây khi đang chạy nhiều browser. Một lượt capture mới với giới hạn 120 giây đã hoàn tất; giữ riêng thư mục thất bại, không gán nó thành capture thành công. Chưa chứng minh throughput thu thập nhiều AOI đồng thời.

## Thay đổi workflow đã triển khai

1. **Architecture observer trước coding.** Quan sát full views và crop chi tiết, mô tả hierarchy mái, nhịp tầng/bay, chiều sâu mặt đứng, material và uncertainty. Kết quả lưu `observations.json`, đi vào site brief; không thay footprint đo.
2. **Prompt theo kiến trúc thực tế.** Không buộc mọi công trình có gable, turret, dormer, pediment hay gạch. Tác giả phải dùng tham số site cho vòng lặp tầng/bay, giữ chi tiết nhận diện thay vì ép số dòng code.
3. **Critic theo bộ phận.** Trả thêm nhận xét roof/facade/materials/attachments và độ tin cậy. Phân biệt dùng chưa đúng API với thiếu công cụ; cửa sổ và local roof opening đã tồn tại, không yêu cầu xây lại kit vô căn cứ.
4. **Hoàn tất route `fix-design`.** Triage chọn route này thì coding node nhận review và ảnh, sửa code bằng kit hiện có, render/critic lại rồi chỉ giữ nếu vượt điều kiện bảo toàn hình học/likeness và xếp hạng tốt hơn. Không còn chỉ ghi bàn giao rồi dừng. `need-evidence` vẫn dừng với yêu cầu dữ liệu, chưa tự tìm provider mới.
5. **Ngữ cảnh phiên bản kit.** Triage nhận descriptor của bản kit đã pin và source helper liên quan, tránh coi mục “missing” của catalog gốc là đúng cho một extension đã có trong v6.
6. **Đo hiệu năng thật.** Manifest có mesh, geometry/material count, CPU attribute bytes và draw call. Đếm tam giác của InstancedMesh nhân đúng số instance; export có matrix/ownership của từng instance.
7. **Giảm capture thừa.** Luồng design giữ toàn bộ camera evidence, một free view và các kiểm tra clay/grazing/night; bỏ tám orbit image không được critic sử dụng. Probe hiệu năng có thể bỏ export vertex JSON để không trộn chi phí serialize hàng trăm MB vào phép đo render.
8. **Giữ kết quả khi provider lỗi.** `run_design` ghi kết quả chưa hoàn tất từ artifact có sẵn; ảnh thiếu review không được chọn thay bản đã review. `recover-design` không gọi model lại, giữ usage và khoản billing chưa rõ.

## Kết quả chất lượng

Điểm theo thứ tự **likeness / style / detail**, do node critic đánh giá; không phải chấp nhận của người dùng.

| Lượt | Mean oblique IoU | Điểm | Trạng thái |
|---|---:|---|---|
| Museum v7, tốt nhất trong 3 attempts | 0,8811 | 0,55 / 0,67 / 0,44 | Metric qua, visual chưa đạt |
| Văn phòng thấp, attempt 0 | — | 0,48 / 0,65 / 0,38 | Chưa đạt |
| Văn phòng thấp, attempt 1 | 0,9092 | 0,64 / 0,62 / 0,43 | Metric qua, visual chưa đạt |
| Văn phòng thấp, workflow `fix-design` | 0,9093 | **0,62 / 0,72 / 0,52** | Được giữ theo chính sách cải thiện, visual chưa đạt |
| Khối 115 m, attempt 0 đã review | 0,9397 | 0,52 / 0,63 / 0,35 | Metric qua, visual chưa đạt |
| Khối 115 m, attempt 1 | 0,9428 | **Chưa có review hợp lệ** | Render/metric qua; critic bị lỗi stream |

Đã trực tiếp xem input và output. Museum vẫn còn đầu hồi giống các tấm mỏng, hình khối mái lớn đơn giản và mặt đứng lặp lại. Observer giúp tách kiến trúc nhưng chưa tự giải quyết topology hoặc detail. Không có bằng chứng chất lượng museum tăng đáng kể so với v6; prompt critic cũng đã thay đổi nên không dùng điểm lịch sử để kết luận A/B.

Văn phòng thấp sau route `fix-design` có cửa và vật liệu được phân tách tốt hơn, nhưng hai khối trên mái và thiết bị còn đơn giản. Likeness giảm 0,02 trong khi style/detail tăng; workflow giữ theo dung sai hiện tại, không tuyên bố mọi chiều chất lượng đều tăng. Khối cao tầng nhận đúng hệ lá đứng ở bản viết riêng, song vật liệu, mái và mặt đứng vẫn thiếu chi tiết.

Ảnh: [museum](results/heldout-quality/museum.jpg), [văn phòng trước sửa](results/heldout-quality/office-low-before.jpg), [văn phòng sau sửa](results/heldout-quality/office-low-refined.jpg), [cao tầng đã review](results/heldout-quality/office-high-reviewed.jpg), [cao tầng chưa review](results/heldout-quality/office-high-unreviewed.jpg). Reference: [văn phòng thấp](results/heldout-quality/office-low-reference.jpg), [cao tầng](results/heldout-quality/office-high-reference.jpg).

## Thử giữ nguyên recipe

Lấy nguyên `design.mjs` từ văn phòng thấp, không sửa byte nào, chạy với site của tòa 115 m và cùng kit. Hai hash code bằng nhau, `author_calls:0`. Có một call critic mới cho phép thử này, không gọi lại request critic lỗi trước.

- Render và metric qua: IoU 0,9303; height 115,34 m; 188.034 tam giác.
- Điểm 0,39 / 0,67 / 0,34; `accepted:false`.
- Sai nhận diện: recipe giữ dải cửa ngang và cấu trúc rooftop của nhà thấp, trong khi target cần lá đứng, hai bank cửa và phần mái khác.
- Recipe còn làm tăng số tam giác hơn mười lần so với bản viết riêng cho target (15.184 tam giác ở bản đã review).

[Ảnh bị từ chối](results/heldout-quality/recipe-transfer-rejected.jpg), [báo cáo hash và review](results/heldout-quality/recipe-transfer.json).

Kết luận hẹp: kit dùng lại được để viết các thiết kế khác nhau; một script nhận footprint/height không tự trở thành family recipe tổng quát. Cần phân họ bằng cấu trúc mái, hệ mặt đứng, bay/opening rhythm và tổ chức khối trước khi tái sử dụng. Chưa promote recipe này thành family ổn định, chưa có selector tự động đã được benchmark.

## Thử scale renderer

`runtime/batching.mjs` gom geometry giống nhau bằng nội dung buffer và cùng material; kiểm lại buffer để không dựa riêng vào hash 32-bit. Giữ UV, matrix, shadow/render-order/layer và owner `{asset, component}` cho raycast. Đây là đường **static asset**, chưa hỗ trợ skinned/morph/dynamic part, explode từng chi tiết hoặc sửa vật liệu riêng một instance. Utility được dùng bởi probe; chưa bật tự động cho toàn bộ workflow thành phố.

Thử chín bản sao của cùng museum v7, cùng placement và look, chạy lần lượt:

| Đại lượng | Không batch | Batch |
|---|---:|---:|
| Mesh/draw group | 9.018 | 118 |
| Draw call frame đo | 9.018 | 118 |
| Tam giác | 286.317 | 286.317 |
| Unique geometry | 1.002 | 118 |
| CPU geometry attribute bytes | 2.629.328 | 271.280 |
| Bundle + capture, bỏ export geometry | 17,52 giây | 23,83 giây |
| Trung bình 8 lời gọi frame sau warm-up | 174,83 ms | 0,85 ms |

Draw call giảm khoảng 98,7%. Bounds lệch dưới 0,00001 m; mean absolute image difference khoảng 0,08 trên thang 0–255 mỗi kênh. Cả hai qua kiểm trạng thái không đổi vị trí, GL context không bị mất và không có GL error. Kiểm thử raycast xác minh owner đúng sau batching.

Không diễn giải số ms trên thành FPS thiết bị người dùng: đo JS/WebGL đã warm-up với `gl.finish()` trên software WebGL, chỉ tám mẫu, không đo toàn bộ đường trình bày của browser. Thời gian toàn lượt không nhanh hơn trong phép thử này; khởi tạo, hashing, shader và các tác vụ chạy cùng máy còn ảnh hưởng. Instancing chứng minh giảm draw/geometry overhead, chưa chứng minh pipeline đầu-cuối nhanh hơn hoặc khả năng stream đô thị.

Lượt probe ban đầu có export geometry JSON: unbatched mất 122,46 giây và xuất khoảng 160 MB; batched mất 19,03 giây. Không dùng so sánh đó làm tốc độ render vì serialization khác nhau. Bảng chính đã bỏ export ở cả hai phía và giữ cùng lighting.

[Ảnh chín instance](results/heldout-quality/nine-instances.png), [frame batch](results/heldout-quality/batched-frame-times.json), [frame không batch](results/heldout-quality/unbatched-frame-times.json), [report chính](results/heldout-quality/report.json).

## Độ ổn định và chi phí

- Ba site có bản dựng và review hợp lệ; cả ba bản được giữ qua metric. Hai luồng design hoàn tất bình thường, luồng cao tầng giữ lại attempt 0 sau lỗi critic ở attempt 1. **Không báo hoàn tất 3/3 hoặc visual đạt 3/3.**
- Một lượt kit-triage museum khác cũng bị `STREAM_PROVIDER_ERROR`, trước khi có đề xuất kit hợp lệ. Không có kit mới được kích hoạt từ nhánh lỗi đó và không tự gửi lại request.
- Đã bổ sung và kiểm thử recovery sau lỗi; các lỗi đã gặp trước bản sửa được phục hồi từ file thật, không ghi lại như thể chúng đã chạy bản sửa từ đầu. Main run v7 cũng có các thay đổi runtime trong quá trình giám sát; source map/hash từng attempt là nguồn truy nguyên, không coi toàn bộ lượt là thí nghiệm giữ nguyên một biến.
- Tổng phần usage đã biết của ba design, một refine và một transfer: **265.413 input + 37.450 output token**. Hai request stream lỗi có tổng reserve **93.563 token chưa đối soát**; reserve không phải số token thực tế hoặc hóa đơn. Chưa có USD hợp đồng gateway nên không tính giá USD giả định.
- Các lượt design chính ghi khoảng 542 giây (museum), 386 giây (văn phòng thấp) và 277 giây tới lỗi (cao tầng); không bao gồm capture provider. Máy có các tác vụ đồng thời, không dùng các số này như throughput chuẩn hoặc trung bình của một đô thị.
- 84 test phần mềm qua, Ruff và Node syntax check qua. Test phần mềm không thay thế nghiệm thu ngoại hình.

## Hướng ưu tiên từ bằng chứng mới

1. Hoàn thiện topology mái, đầu hồi và attachment của landmark trước khi thêm nhiều ornament; kiểm mặt cắt, ray sampling và tiếp giáp thực.
2. Thêm facade observation theo từng mặt: ánh xạ camera → cạnh nhìn thấy, opening/bay rhythm, chiều sâu và vật liệu; tách mảng chính khỏi chi tiết lặp. Dữ liệu hiện có vẫn mờ ở một số mặt, cần giữ uncertainty.
3. Chỉ dùng recipe khi architectural discriminators tương thích. Lưu kit/domain code, family recipe và landmark code riêng; đa dạng seed không được thay thế bằng việc áp một recipe lên kiến trúc khác.
4. Đưa static batching vào bước scene composition sau asset validation; giữ source code/semantic ownership riêng để sửa asset rồi build lại batch. Thêm LOD, spatial chunks, visibility/streaming và budget unique material/geometry. Biến thể độc đáo sẽ làm giảm hiệu quả batching.
5. Hoàn thiện node lấy thêm evidence và cơ chế giải quyết request billing chưa rõ trước khi chạy job dài; không dùng retry vô hạn để che lỗi provider.
6. Mở rộng held-out set sang kiến trúc và thành phố khác sau khi có ít nhất một loại công trình đạt visual acceptance. Hiện mới chứng minh pipeline đi qua dữ liệu mới trong một khu Tokyo, chưa đủ kết luận tổng quát toàn cầu.

## Lệnh tái sử dụng

```powershell
.venv/Scripts/python -m worldscale.capture_site --osm ../workflow_research/inputs/geography/tokyo-marunouchi/snapshot.osm --way 145394389 --height 35 --out inputs/evidence/new-site
.venv/Scripts/python -m worldscale.cli design --evidence inputs/evidence/new-site --styles inputs/style-references/user-reference --run runs/new-design --max-revisions 1 --kit-version runs/kit-evolution-ichigokan-v6/active-kit.json
.venv/Scripts/python -m worldscale.cli adapt-kit --source-run runs/new-design --run runs/new-refine --max-cycles 1
.venv/Scripts/python -m worldscale.cli recover-design --run runs/interrupted-design
.venv/Scripts/python -m worldscale.scale_probe --source-run runs/quality-holdout-museum-v7 --out runs/new-scale-probe --count 9
.venv/Scripts/python -m worldscale.benchmark --runs runs/quality-holdout-museum-v7 runs/quality-holdout-office-low-v1 runs/quality-holdout-office-high-v1 --out runs/new-report.json
```

Dùng tên thư mục run mới. Recovery chỉ đọc artifact, không gửi model request. Mặc định capture cần SDK reference viewer đang chạy; không có input liên tục hoặc tự mua dịch vụ mới.
