# Phương pháp hiện tại và hướng triển khai

Cập nhật: 2026-11-12. Đây là tài liệu định hướng chính của `workflow_scale_research`. Đọc file này trước; các file `01`–`07` là lịch sử của hướng cũ, `08` và `09` là số liệu chi tiết của hướng hiện tại.

Cải tiến chất lượng đang triển khai: [kit và vòng đánh giá](10-quality-first-kit.md). Phân biệt kit, công thức thiết kế và bố trí cảnh; cấu trúc SDK đích: [World kit](11-world-kit-structure.md). Cấu trúc SDK này chưa được triển khai đầy đủ; `runtime/kit.mjs` hiện mới là nhóm công cụ cho tòa nhà.

## 1. Bài toán

Workflow đã có nhánh [tự phát triển kit theo quyền hạn và phiên bản riêng](12-adaptive-agent-kit-evolution.md): triage → developer → kiểm thử API cũ/mới → consumer → render/critic → kích hoạt hoặc giữ bản trước. Chất lượng pilot vẫn chưa đạt nghiệm thu; xem số liệu trong docs/10 và docs/12.

Tạo mô hình 3D đô thị bằng code Three.js sao cho:

- **gần khớp thực tế**: đúng vị trí, hình mặt bằng, chiều cao, kiểu mái, các đặc điểm nhận diện — không cần khớp từng pixel;
- **theo style mong muốn**: lấy từ ảnh style do người dùng đưa, áp được cho mọi tòa nhà;
- **giữ được sự sáng tạo của agent**: agent quyết định vật liệu, nhịp cửa, trang trí, khối phụ;
- **rẻ, nhanh, nhân rộng được** tới cả khu phố và thành phố.

## 2. Nguyên tắc cốt lõi

**Đo sự thật bằng code, để agent thiết kế bằng một bộ từ vựng kiến trúc, và kiểm tra bằng dung sai chứ không bằng pixel.**

Ba tầng tách rời:

| Tầng | Ai làm | Sản phẩm | Lần gọi model |
|---|---|---|---|
| Sự thật | Code tất định | `site.json` (site brief) | 0 |
| Style | Agent, một lần cho mỗi bộ ảnh style | `style.json` (style sheet) | 1, có cache |
| Thiết kế | Agent | `design.mjs` viết bằng bộ kit | 1 mỗi bản |

Agent **không bao giờ viết tọa độ tường**. Đường bao tường và mọi "khung đặt" (frame) trên cạnh nhà đều lấy từ site đã đo. Nhờ vậy agent tự do sáng tạo mà không thể dời cánh nhà, lật mặt bằng hay đổi kích thước công trình.

## 3. Ba hướng đã thử

| Hướng | Cách làm | Kết quả trên bảo tàng Ichigokan | Kết luận |
|---|---|---|---|
| Native img2threejs (docs 01–07) | Agent viết toàn bộ spec và code từ ảnh; cổng chấm là silhouette IoU ≥ 0,85 trên một góc nhìn, camera dò đoán | IoU 0,31–0,49; hơn 150k token mỗi lần; 6 lần sửa không qua pass đầu | Không dùng làm xương sống. Chỉ còn là tùy chọn cho công trình "hero" |
| Dựng khối từ bằng chứng (docs 08) | Code khớp tham số và mặt phẳng mái từ dữ liệu đo, agent chỉ điền vài tham số | IoU 0,92 qua 4 camera thật; 0–10k token | Chính xác, rẻ, nhưng cứng nhắc và mái bị bậc thang. Giữ lại làm **nguồn sự thật** và làm khối nền cho nhà phụ |
| **Agent thiết kế trên site đã đo (docs 09)** | Ba tầng ở mục 2 | IoU 0,855; 38,5k token; build được ngay cả hai lần; critic chưa chấp nhận | **Hướng hiện tại** |

## 4. Luồng xử lý

```
OSM outline + ảnh chụp đa góc có pose camera
        │
        ▼
[1] Gói bằng chứng        evidence.json   (footprint theo mét, camera từng ảnh)
        │
        ├─► [2] Trường cao độ (tùy chọn)   heights.json  (lưới cao độ 0,6 m)
        ▼
[3] Site brief            site.json       (cạnh, cao độ, kiểu mái, dormer/ống khói/tháp, màu)
        │
[4] Style sheet ──────────┤               style.json    (một lần cho mỗi bộ ảnh style)
        ▼
[5] Agent viết thiết kế   design.mjs      (50–150 dòng, viết bằng kit)
        ▼
[6] Render qua camera thật + kiểm tra đo có dung sai     metrics.json
        ▼
[7] Critic vision         review.json     (giống / style / chi tiết + danh sách sửa)
        │
        └─► chưa đạt: quay lại [5] kèm nhận xét, tối đa N vòng; giữ bản tốt nhất
```

### Bước 1 — Gói bằng chứng

- **Đầu vào**: file OSM, id của way, thư mục ảnh chụp có `capture-manifest.json` (vị trí camera, điểm nhìn), cao độ mặt đất, chiều cao ước lượng.
- **Đầu ra**: `evidence.json` và bản sao ảnh. Footprint ở hệ tọa độ mét: X hướng đông, Y lên trên, Z hướng nam, gốc tại tâm footprint ở mặt đất.
- **Mã**: `georef.build_evidence`. Lệnh `worldscale evidence`.
- **Lưu ý**: camera được dựng lại từ vị trí ghi trong manifest và góc nhìn mặc định 60° của Cesium. Phải kiểm tra bằng `georef.overlay` (vẽ footprint đè lên ảnh) khi dùng nguồn ảnh mới.

### Bước 2 — Trường cao độ (tùy chọn nhưng nên có)

- Lấy mẫu cao độ bề mặt photogrammetry trên lưới xoay theo trục chính của footprint. Bảo tàng: 10.848 mẫu, 94 giây.
- Cần chạy viewer tham chiếu (Cesium, dùng `CESIUM_ION_TOKEN` trong `.env`). Lệnh `worldscale heights`; file `heights.json` nằm cạnh `evidence.json` và được tự động dùng.
- **Mã**: `dsm.capture`, `dsm.fit_roof`.
- Không có trường cao độ thì site brief vẫn tạo được, nhưng không có vị trí dormer/ống khói/tháp và cao độ chỉ đến từ silhouette.

### Bước 3 — Site brief

- **Mã**: `massing.fit` (khớp vị trí footprint, tổng chiều cao, kiểu mái, đường mái hiên bằng silhouette đa góc), `brief.site_brief`, `brief.roof_features`.
- **Nội dung `site.json`**: footprint; danh sách cạnh `e0…eN` kèm độ dài, hướng nhìn (N/E/S/W…) và cờ `end` cho đầu hồi của cánh nhà; `eave_m`, `ridge_m`, `top_m`; số tầng; kiểu và độ dốc mái; vị trí đo được của dormer, ống khói, tháp; màu tường/mái lấy mẫu; tag OSM.
- Kết quả khớp được cache theo hash của gói bằng chứng trong `.cache/facts/`.
- Site brief **cố ý nhỏ**: chỉ đưa mốc neo và giới hạn, không đưa lưới để sao chép.

### Bước 4 — Style sheet

- **Mã**: `design.style_sheet`. Agent mô tả style để áp cho tòa nhà bất kỳ: xử lý hình khối, mật độ chi tiết, cách dịch màu, bề mặt, ánh sáng, mức phóng đại, điều cần tránh.
- Không chứa kiến trúc hay địa điểm của ảnh style.

### Bước 5 — Agent viết thiết kế

- **Mã**: `design.author`. Prompt gồm tài liệu kit (`runtime/kit-api.md`), `site.json`, `style.json`, một tấm ghép các ảnh tham chiếu và ảnh style.
- **Đầu ra**: module `export function design(site, b, style) { … }`.
- **Bộ kit** (`runtime/kit.mjs`): `walls`, `band`, `roof` (hip/gable/mansard/flat), `dormer`, `gable`, `chimney`, `turret`, `bay`, `portal`, `pilasters`, `quoins`, `ground`, `look`; hình học tự do `box`, `cylinder`, `cone`, `prism`, `loft`, `add` với `b.THREE`. Đặt vật bằng `b.edge(id).at(t)`, `b.along(...)`, `b.at(x, z)`; hỏi cao độ mái bằng `b.roofY(x, z)`.
- **An toàn**: script chỉ chạy trong trang trình duyệt đã chặn mạng. `design.lint` từ chối `import`, mạng, timer và biến toàn cục của trình duyệt trước khi bundle.

### Bước 6 — Render và kiểm tra đo

- **Mã**: `design.render_attempt`, `pipeline.evidence_capture`, `design.measure`.
- Render đúng pose của từng ảnh tham chiếu (`worldscale.pose` trong viewer), không dò camera.
- Ngưỡng dung sai, nhằm loại "nhầm tòa nhà" chứ không ép sao chép:
  - silhouette trung bình các góc xiên ≥ 0,70;
  - silhouette góc nhìn từ trên ≥ 0,75;
  - chiều cao dựng trong khoảng 0,8–1,3 lần `top_m`;
  - không quá 200.000 tam giác.
- Script lỗi build hoặc lỗi runtime: thông báo lỗi được gửi lại cho agent ở vòng sau.

### Bước 7 — Critic và vòng sửa

- **Mã**: `design.critic`, vòng lặp trong `design.run_design`.
- Critic nhận tấm ảnh tham chiếu, tấm render cùng camera, ảnh style; trả điểm `likeness`, `style`, `detail` (0–1), checklist đặc điểm, lỗi, và danh sách sửa viết theo ngôn ngữ của kit.
- Ngưỡng chấp nhận: 0,70 / 0,65 / 0,65 và phải qua kiểm tra đo.
- Số lần gọi model bị chặn ở `2 + 2 × (số vòng sửa + 1)`. Bản tốt nhất được giữ, không phải bản cuối.
- `accepted` trong `result.json` chỉ có nghĩa "qua kiểm tra đo và critic tự động"; chưa có người duyệt.

## 5. Lệnh chạy từ đầu đến cuối

```powershell
cd D:\WorldAsCode\workflow_scale_research

# 1. Gói bằng chứng
.venv/Scripts/python -m worldscale.cli evidence --osm <snapshot.osm> --way <id> `
  --captures <thư mục ảnh> --ground-height <m> --height <m> --out inputs/evidence/<tên>

# 2. Trường cao độ (mở viewer tham chiếu ở cửa sổ khác, rồi lấy mẫu một lần)
..\workflow_research\.venv\Scripts\python -m building_workflow.urban.reference_server `
  --port 8767 --longitude <lon> --latitude <lat>
.venv/Scripts/python -m worldscale.cli heights --evidence inputs/evidence/<tên>

# 3–7. Site brief, style, thiết kế, kiểm tra, critic
.venv/Scripts/python -m worldscale.cli design --evidence inputs/evidence/<tên> `
  --styles inputs/style-references/<thư mục> --run runs/<tên run> --max-revisions 1

# Phụ: khối nền không cần agent, và bản nháp cả khu
.venv/Scripts/python -m worldscale.cli massing  --evidence inputs/evidence/<tên> --run runs/<tên>
.venv/Scripts/python -m worldscale.cli district --osm <snapshot.osm> --run runs/<tên> --fitted runs/<massing run>
```

Model và khóa đọc từ `.env` ở thư mục gốc (`OPENAI_BASE_URL`, `OPENAI_API_KEY`, tùy chọn `WORLD_SCALE_MODEL`).

## 6. Thư mục kết quả của một lần `design`

| File | Nội dung |
|---|---|
| `site.json`, `style.json`, `fit.json` | Sự thật đã đo, style sheet, nhật ký khớp tham số |
| `reference-sheet.jpg` | Tấm ghép ảnh tham chiếu đã lọc phạm vi |
| `attempt-N/design.mjs` | Script agent viết |
| `attempt-N/render-sheet.jpg` | Render qua các camera thật và một góc tự do — **xem file này để đánh giá bằng mắt** |
| `attempt-N/diff-<view>.png` | Xanh lá: trùng; đỏ: thiếu khối; xanh dương: thừa khối |
| `attempt-N/metrics.json`, `review.json` | Kiểm tra đo và nhận xét của critic |
| `result.json`, `usage.json` | Tổng kết, bản tốt nhất, token và thời gian |

## 7. Bản đồ mã nguồn

| File | Vai trò |
|---|---|
| `src/worldscale/georef.py` | Hệ tọa độ, đọc OSM, camera, mặt nạ phạm vi, IoU silhouette |
| `src/worldscale/massing.py` | Khớp tham số bằng silhouette, hình học mặt bằng (offset), khối nền |
| `src/worldscale/dsm.py` | Lấy mẫu cao độ, khớp mặt phẳng mái |
| `src/worldscale/brief.py` | Site brief và phát hiện dormer/ống khói/tháp |
| `src/worldscale/design.py` | Style sheet, tác giả, lint, render, kiểm tra đo, critic, vòng lặp |
| `src/worldscale/pipeline.py` | Render qua camera bằng chứng, lệnh `massing` và `district` |
| `runtime/kit.mjs`, `runtime/kit-api.md` | Bộ kit và tài liệu kit đưa vào prompt |
| `runtime/viewer.mjs`, `runtime/semantic.mjs` | Viewer và bộ dựng World IR (khối nền, demo) |
| `src/worldscale/workflow.py`, `native.py` | Nhánh native cũ — không phát triển tiếp |
| `tests/test_massing.py`, `test_dsm.py`, `test_design.py` | Kiểm thử cho hướng hiện tại |

## 8. Trạng thái đã đo (một tòa nhà, chưa phải benchmark)

Run `runs/design-ichigokan-v1`:

| Bản | IoU góc xiên | Giống | Style | Chi tiết | Critic chấp nhận |
|---|---|---|---|---|---|
| 0 | 0,853 | 0,68 | 0,64 | 0,43 | không |
| 1 | 0,855 | 0,65 | 0,72 | 0,53 | không |

- 5 lần gọi model, 31.430 token vào và 7.065 token ra, 404 giây (182 giây chờ model).
- Cả hai script build được ngay, 106 dòng.
- 62 kiểm thử qua.

Điểm yếu đã thấy: đường mái phẳng và đều hơn thật; đầu hồi cao và trang trí mặt đứng còn yếu; chân dormer và tháp gặp mái như hộp; hai vòng chưa hội tụ.

## 9. Điều chưa được chứng minh

- Dùng lại một script cho tòa nhà thứ hai cùng kiểu. Đây là giả thuyết then chốt để nhân rộng và **chưa thử**.
- Critic có khớp với đánh giá của người không. Critic cùng họ model với tác giả.
- Ngưỡng dung sai ở bước 6 và ngưỡng critic mới đặt theo một tòa nhà.
- Thêm vòng sửa có giúp hội tụ không.
- Ghép nhiều tòa đã thiết kế vào một khu, kèm đường và mặt đất.

## 10. Quy tắc cho các lần triển khai sau

1. **Không cho agent viết tọa độ tường hay camera.** Mọi thứ thuộc về "ở đâu, to bao nhiêu" đi qua site brief.
2. **Thiếu khả năng biểu đạt thì mở rộng kit**, không quay lại cho agent viết lưới tự do cho cả công trình. Khi critic lặp lại cùng một "fix" mà kit không làm được, thêm cấu kiện đó vào `kit.mjs` và mô tả trong `kit-api.md`.
3. **Giữ `kit-api.md` ngắn.** Nó nằm trong mọi prompt tác giả.
4. **Kiểm tra đo là để loại sai lầm lớn.** Đừng siết ngưỡng silhouette để ép giống pixel; style cần chỗ để phóng đại.
5. **Luôn mở ảnh `render-sheet.jpg`** trước khi kết luận. Điểm số không thay cho việc nhìn.
6. **Báo cáo trung thực**: `accepted` chỉ đổi theo đúng cơ sở ghi trong `acceptance_basis`; ghi rõ token, thời gian, số tòa đã thử.
7. **Phân tầng ngân sách**: nhà nền dùng `district` (0 token), nhà thường dùng script theo họ, chỉ landmark mới có script riêng.
8. **Không sửa checkout img2threejs** và không coi nhánh native là đường mặc định.

## 11. Việc tiếp theo, theo thứ tự

1. Thêm vào kit ba cấu kiện critic đã yêu cầu: đầu hồi cao liền với mái, biến thể dormer, viền cửa sổ.
2. Chạy lại bảo tàng và so với bản hiện tại bằng mắt và bằng critic.
3. Chạy cùng script trên một tòa thứ hai cùng kiểu để thử giả thuyết "script theo họ".
4. Lấy bằng chứng cho vài tòa khác kiểu (tháp kính, nhà thấp) để hiệu chỉnh ngưỡng.
5. Ghép các tòa đã thiết kế vào bản nháp khu phố.
