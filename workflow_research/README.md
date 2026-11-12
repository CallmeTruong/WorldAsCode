Current implementation experiment: `tokyo-scene-v2` ? shared scene evidence, five component buildings, mesh-height checks, bound PBR materials and observed crossing extent. Technical checks pass; factual/style acceptance remains false. [results](reports/urban/scene-implementation-results.md).

> Active test: Tokyo Marunouchi, 220 m AOI, Google 3D Tiles multi-view evidence, one individually observed museum and 13 context proxies. See [Tokyo findings](reports/urban/tokyo-findings.md). Earlier HCMC selected-run statements below are historical.

# Procedural Building Workflow

> Current selected result: `district1-quality-v10` (220 m AOI, 3 photo-backed targets and 8 context proxies). Descriptive style preserves native materials; fidelity remains partial. See [quality correction results](reports/urban/quality-correction-results.md). Earlier v4/palette/36-building statements below are historical and superseded.


## Urban/style pilot — đã triển khai 12/11/2026

Ảnh user được giữ nguyên ở [style folder](inputs/style-references/user-isometric/reference.png). Folder bất kỳ được vision API phân tích thành StyleProfile; palette không hardcode theo ảnh này. [Báo cáo đô thị](reports/urban/index.html), [findings](reports/urban/findings.md), [Spec Kit 002 tasks](specs/002-urban-grid-style/tasks.md).

```powershell
.venv/Scripts/python -m building_workflow.cli urban --style-dir inputs/style-references/user-isometric --run-id my-urban-run --object-refs inputs/object-references/manifest.json
```

Muốn thử thư mục style khác, thay `--style-dir` và dùng run ID mới. Không có flag này thì neutral profile. `--reuse-run-id EXISTING_ID` tái dùng source procedural đã được API tạo; `--object-refs` cung cấp ảnh factual theo object ID. Các chế độ này khác nhau: ảnh style chỉ chỉ dẫn hình thức; ảnh object mới dùng tái tạo kiến trúc riêng. Lệnh mặc định có giới hạn calls/tokens/time; đọc contracts/urban-cli.md.

Pilot 400×400m có 4 cells, 36 buildings. Chỉ Nhà hát Thành phố có ảnh riêng được LLM quan sát/sinh module, các mặt tiền khác là procedural inferred. Hiện xem assembled scene toàn khu vực; cell manifests/cache và seam evidence có, cell-level streaming/LOD city chưa được triển khai. Native eight-pass baseline vẫn chưa hoàn tất.

Mở viewer khi server local chạy:

```powershell
.venv/Scripts/python -m http.server 8765 --bind 127.0.0.1 --directory runs/urban
```

Sau đó vào URL của run, ví dụ `http://127.0.0.1:8765/district1-final-v4/viewer.html`. Bật/tắt neutral/style, grid, cây, đèn và các góc camera. Static report `runs/urban/<run-id>/index.html` có thể mở trực tiếp bằng file. Không có Cesium/LLM keys trong viewer assets. Viewer đô thị hiện không stream Google/Cesium tiles và không export dữ liệu nhà cung cấp vào scene.

Dependencies mới: Shapely/PyProj, đã ghi trong pyproject.toml và requirements.lock.txt. Texture resolver tải hữu hạn PBR CC0 và xác minh checksums; worker code không có quyền tải mạng. Nguồn ảnh Nhà hát và giấy phép CC BY 2.0 lưu ở inputs/object-references/manifest.json.

**Nghiên cứu tiếp theo, 12/11/2026:** [Đô thị theo grid quanh Quận 1 và thư mục ảnh tham chiếu style](../docs/urban_grid_research.md), [Spec Kit feature 002](specs/002-urban-grid-style/spec.md), [khảo sát dịch vụ/dữ liệu thực](../docs/research/2026-11-12-district1-service-readiness.md). Đợt này mới docs và read-only probes; chưa có city runner, style-folder CLI hoặc viewer đô thị. Phần dưới mô tả prototype công trình đã chạy của feature 001.

Đợt nghiên cứu đầu tiên đã có workflow chạy bằng **LangGraph → API → procedural TypeScript → kiểm tra mesh → Three.js → review → sửa có giới hạn**. Không dùng Codex/Claude CLI trong runtime. Chưa tích hợp input liên tục.

- [Mở báo cáo và ảnh so sánh](reports/index.html)
- [Kết luận và giới hạn](reports/findings.md)
- [Số liệu tất cả thí nghiệm, gồm lần thất bại](reports/comparison-table.md)
- [Spec Kit: spec](specs/001-building-workflow/spec.md), [plan](specs/001-building-workflow/plan.md), [tasks](specs/001-building-workflow/tasks.md), [nghiên cứu upstream](specs/001-building-workflow/research.md)
- [Kiểm tra và tái lập](reports/validation.md)

## Chạy

PowerShell tại thư mục này:

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.lock.txt
npm ci
.venv/Scripts/python -m playwright install chromium
git clone https://github.com/img2threejs/img2threejs.git vendor/img2threejs
git -C vendor/img2threejs checkout 0c0c49bc168e648dbaf9c8c080474de0b3a941b6
.venv/Scripts/python -m building_workflow.cli doctor
.venv/Scripts/python -m building_workflow.cli samples
.venv/Scripts/python -m building_workflow.cli run --sample rietveld --strategy spec --max-refinements 1
.venv/Scripts/python -m building_workflow.cli report
```

Nếu các dependencies/vendor đã có trên máy hiện tại, bắt đầu từ `doctor`. Đọc credentials từ `../.env`; không cần sao chép key. ID model có tiền tố `openai/` trong biến CASEPILOT được chuẩn hóa sang ID gateway công bố. Có thể đặt `WORKFLOW_VISION_MODEL`, `WORKFLOW_CODE_MODEL`, `WORKFLOW_REVIEW_MODEL` để đổi từng bước.

Thử nghiệm camera độc lập, giữ nguyên geometry:

```powershell
.venv/Scripts/python -m building_workflow.cli run --sample rietveld --strategy spec --refinement-scope camera --max-refinements 1
```

Render lại procedural source đã lưu, không gọi model:

```powershell
.venv/Scripts/python -m building_workflow.cli render runs/smoke-rietveld-camera/iteration-01/generator.ts runs/rerender-rietveld
.venv/Scripts/python -m pytest -q
```

Giới hạn mặc định mỗi job: 12 API attempts, 100k tokens với dự phòng token trước mỗi call, 900 giây; tối đa 50k triangles, 1200 meshes, 2 GB RSS tổng process tree và deadline renderer. Chỉnh bằng `--max-calls`, `--max-tokens`, `--max-seconds`, `--max-refinements`. Exit code: 0 cho `partial` có artifact, 2 cho failed, 3 cho insufficient_evidence. `partial` không đồng nghĩa đã đạt fidelity.

Graph lưu SQLite sau mỗi node; dùng cùng `--run-id` và cùng cấu hình để tiếp tục checkpoint chưa hoàn tất. Run đã có `result.json` là terminal và được giữ nguyên; sửa cấu hình hoặc chạy lại thất bại bằng ID mới. Cache theo endpoint/model/prompt/ảnh; tính phí thực tế và lượng token tương đương khi không cache được tách riêng trong báo cáo. `scripts/summarize.py` dựng lại bảng so sánh từ trace; script này không gọi API.

## Kết quả và phạm vi

Đã thử Rietveld, Bauhaus và Fallingwater bằng direct và spec; thêm một thử nghiệm chỉ sửa camera. Tất cả 6 cấu hình chính có ít nhất một candidate hợp lệ và đủ ảnh; còn lỗi cấu trúc nên kết quả là **partial**. Ba lượt lỗi tích hợp ban đầu được giữ trong báo cáo, không xóa khỏi thống kê.

Nhánh spec và sửa có mục tiêu giúp một số mẫu, nhưng chưa có bằng chứng thắng trên mọi kiến trúc. Fallingwater vẫn còn sai đáng kể. Điểm VLM chưa hiệu chỉnh; không có IoU/SSIM hợp lệ khi chưa có mask và camera được kiểm chứng. Giá API chưa được cung cấp nên chi phí USD để `null`; có số calls/tokens thật. Đặt hai biến `WORKFLOW_INPUT_USD_PER_MILLION` và `WORKFLOW_OUTPUT_USD_PER_MILLION` khi có bảng giá được xác nhận.

Adapter dùng source img2threejs đã pin, đọc router, nạp hướng dẫn theo giai đoạn, chạy probe/state và gate hình học thật. **Chưa hoàn tất baseline native đủ tám pass / ObjectSculptSpec strict-quality**; trạng thái upstream không bị tự đánh dấu hoàn tất. Held-out benchmark, segmentation/camera fitting định lượng, city assembly và ingestion liên tục nằm ở đợt sau.

Generated code chỉ chạy trong Chromium OS sandbox và dedicated worker, CSP cùng request blocking chặn mạng. Host giữ credentials; code sinh ra không chạy trong Node/Python. Watchdog theo dõi thời gian và RSS; đây là prototype cục bộ, chưa phải sandbox dịch vụ đa người dùng với quota OS cứng. Docker daemon trên máy chưa chạy nhưng không cần cho thử nghiệm hiện tại.