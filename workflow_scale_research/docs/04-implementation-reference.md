# Chi tiết implementation

## Artifact thực sự được xuất

Đầu ra dựng asset là `createObjectModel.ts`: code TypeScript dùng Three.js, không phải mesh Google được đổi nhãn thành sản phẩm do agent sinh. Native `ObjectSculptSpec` là đầu vào có cấu trúc cho code; World IR là recipe và placement cho composition. Bundle JS và ảnh browser là artifact kiểm chứng. Không dùng GLB làm đầu ra mặc định.

## Native protocol và quyền quyết định

`native.py` chạy chính script trong checkout đã pin, lưu command, stdout, stderr, exit code, duration, commit và hash. Kiểm tra commit, contract hash và tracked modifications trước khi làm việc. `forge/next.py` quyết định trạng thái; hard stop được giữ nguyên. Không sửa validator hay tự điền pass đã hoàn thành.

| Bước | Node/công cụ | Output và điều kiện |
|---|---|---|
| Quan sát | GPT Sol, đủ image-analysis protocol | Tám lớp quan sát, phân biệt inference, target bbox, suitability, unknowns, style descriptive |
| Admission | Native admission cho source, crop, context và style | File probe/verdict thật; source gốc giữ nguyên |
| Retrieval và assessment | Native local BM25 search + assessment skeleton; node xem target và 9 crops | Native quality contract không được tự thay đổi; detail inventory phải nối tới component/material |
| Spec author | Node hình học, node vật liệu/chi tiết | Chỉ sửa các section được cho phép; contracts, floors, review history và diagnostic evidence được bảo vệ |
| Material evidence | Node chọn ROI; native pixel extraction | Confidence do native tool đo, không do LLM tự khai là extraction pass; maps nguồn và báo cáo giữ lại |
| Strict gate | Native strict validator | Fail được gửi node sửa bằng JSON Pointer patches nhỏ; không sinh template để thay asset lỗi |
| Build | Native factory cho pass đang mở | Tám pass giữ thứ tự native, không generate trước pass chưa được duyệt |
| Code correction | Node `refine-code` sửa TS bằng exact anchored edits | Giữ hierarchy/runtime metadata; không regenerate khi hành động yêu cầu sửa code hiện tại |
| Capture | Browser Three.js riêng | Camera fit có giới hạn, front/rear/side/top, night, export mesh/part/positions và hash |
| Deterministic gates | Native Tier 1, Divine Eye, interior, orbit, coverage, attachment, geometry + semantic probes | Hard failure không được critic dùng điểm trung bình để cứu |
| Critic | Node GPT Sol nhận reference, render, orbit, style và full review contracts | Global/layer/critical-feature score, style score, defects, action; native append/check/sync là authority |

Native strict validation vẫn có thể từ chối toàn bộ một run. Có code cho một nhánh không đồng nghĩa đã kiểm chứng nhánh đó bằng một model thật. Xem báo cáo thực nghiệm để phân biệt rõ.

## Spec sửa khác code sửa

Sai hoặc thiếu decomposition, topology, material intent và evidence thì `refine-spec`. Spec đủ đúng nhưng implementation không biểu diễn được thì `refine-code`. Code node chỉ trả exact `find/replace`, kiểm tra hash và độ duy nhất của anchor. Quyết định sửa được lưu thành versioned overlay và liên kết trong `proceduralStrategy`; generation sau chỉ áp dụng lại khi anchor còn đúng. Overlay lỗi thời phải dừng/rebase, không âm thầm bỏ thay đổi tốt.

Geometry gate đo mesh thật export từ browser. Semantic probe của shaft/window thực hiện center ray và wall ray: center phải trống, thành phải có geometry. Thử thêm vật liệu che kín hoặc xóa shell phải fail. Probe còn xét vật cản từ asset khác nên không thể đặt ống rỗng lên mái kín rồi tuyên bố có đường thoát. Kiểm tra tia hiện tại chỉ là kiểm tra theo trục, chưa phải mô phỏng dòng khí hoặc kiểm chứng mọi kiểu flue uốn cong.

## Style và vật liệu

Style được node đọc trực tiếp từ ảnh: xử lý hình khối, mật độ chi tiết, cạnh, tính minh họa, ánh sáng. Không suy vị trí hoặc hình dáng Tokyo từ ảnh Singapore; không ép mọi đối tượng theo vài màu style. Màu source thuộc material evidence, style thuộc treatment. Critic có ngưỡng style riêng 0.75 khi nhận style input.

Không có danh mục texture bắt buộc. Native pixel extraction là nguồn evidence cho spec, không phải yêu cầu mọi bề mặt khớp texture 100%. Single-image PBR là ước lượng, kể cả khi native confidence cao. Không tăng confidence bằng cách khai giả multi-view; không dùng `allow-low-confidence` để nhận native completion. Nếu native strict contract và chế độ approximation của đô thị không tương thích, phải báo khác biệt hoặc mở profile có tên riêng với quality policy rõ ràng, không gọi đó là native parity.

## Resume, provenance và ngân sách

Input manifest khóa hash source/style/context/model/upstream. Target crop lưu bbox và hash nguồn, không coi crop là ảnh quan sát độc lập. Native IDs có thể đăng ký các crop file thật; chuẩn hóa `owner.localFeatures.feature` thành `owner/feature` chỉ khi feature tồn tại. Đây là sửa biểu diễn, không sáng tạo hình học.

Render evidence gắn fingerprint spec, factory, bundle và capture hashes. Thay source/code/render làm evidence cũ mất hiệu lực. JSON patch không sửa native review history, quality targets hoặc máy đo PBR. Browser chặn network ngoài artifact root, CSP chặn kết nối; code model chỉ chạy trong browser, không chạy Python/shell do model trả về.

Provider hỗ trợ streaming JSON qua custom gateway. SSE thiếu finish reason không được nhận là thành công. Streaming tránh phụ thuộc thời gian giữ HTTP response không streaming của gateway, nhưng không làm inference nhanh hơn. Giữ usage thật, unknown reserve và raw response đã nhận; không biến failed request thành zero cost. Tiến độ stream là telemetry tùy chọn, lỗi đọc/ghi Windows không được hủy request trả phí. Atomic write dùng temp riêng và retry file sharing ngắn, không retry API.

Job có content identity, output checksum và lease; heartbeat duy trì lease khi model chạy lâu. Lease hết hạn chuyển `uncertain`, không tự phát lại paid request. Run lock chặn hai CLI cùng ghi một run. SQLite là backend pilot trên một máy; distributed scheduler chưa được benchmark.

## Runtime và compiler

Semantic kit gồm box, hollow shaft, gable roof, window frame, tree, lamp, road strip và rail track. Vehicle/animal có schema placeholder nhưng compiler từ chối rõ; chưa có simulation engine. Geometry đơn giản trùng nhau và materials của cùng blueprint được chia sẻ trong browser; chưa phải hệ thống instancing/streaming toàn thành phố.

Giờ tác động ánh sáng/emissive; wetness tác động roughness; gió tác động shader foliage. Không rebuild geometry hoặc đổi anchor. Foliage seed dùng cùng FNV-1a UTF-8 channel ở Python/JS; thay seed không thay vị trí đã khóa bằng evidence. Native factories có thể ghép vào world bằng anchor/rotation/uniform scale; không giả định mọi native material đã có runtime weather/emissive binding.


## Native generator consumer contract regression from the Tokyo pilot

The pinned factory is the final consumer of `ObjectSculptSpec`; native strict validation alone does not prove that each field changes emitted geometry. The generator's `scale_vector()` checks for `transform.scale` before reading `dimensions`. The model emitted `scale: [1,1,1]` as a default on 19 components that also had non-unit dimensions, so the factory baked unit-sized shapes. `compiler_contract.canonicalize_aliases()` removes that exact identity default only when positive dimensions exist, preserves non-identity scales, and records before/after hashes and the changed component IDs. It does not modify the pinned validator or generator.

The same preflight checks the factory's extrusion schema (`geometryDescriptor.profile2D.points`, positive `depth`, optional numeric hole loops) and repetition schema (integer count, executable placement object, level). It converts only known authoring aliases (`outer` to `points`; descriptor `extrudeDepth` to profile `depth`) while preserving numeric data. Any remaining contract issue stops before factory generation; no silent box substitution or semantic opening claim is permitted.

Part coverage uses a temporary spec view matching the pinned generator's level and explicit build-pass references. It keeps parent components and filters detail inventory to parts emitted in the current pass. This prevents `blockout` from failing because micro detail is intentionally deferred. The terminal coverage gate still checks the full spec.

After a deterministic hard rejection, the pinned `correction_loop.decide()` owns routing. A Divine Eye hard gate selects `refine-code`; the workflow records the failed render/comparison, syncs native state, then permits only hash-anchored TypeScript edits that retain parts, pivots, sockets and runtime metadata. The native per-pass and total correction ceilings remain in force. Image critic calls stay behind deterministic gates. Tests confirm hard-gate routing, but the Tokyo experiment exhausted the model-call budget before its coder node ran, so the repair is not yet validated end to end on that asset.

See [the measured experiment report](06-experiment-results.md) for images, gates, token usage, billing limits and remaining failures.
