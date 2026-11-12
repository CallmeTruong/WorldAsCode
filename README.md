# WorldAsCode

Workflow tái tạo cảnh Three.js từ bằng chứng địa lý, ảnh nhiều góc nhìn và thư mục ảnh tham chiếu phong cách. Hệ thống chính nằm trong `src/worldascode`; các thư mục `workflow_*research` giữ lịch sử thử nghiệm.

## Cài đặt

Cần Python 3.12+, uv, Node.js 22+ và npm. Chạy từ root checkout:

```sh
uv sync --extra test
npm ci --ignore-scripts
uv run playwright install chromium
uv run worldascode doctor
```

## Cấu hình

Chỉnh [worldascode.toml](worldascode.toml) để thay endpoint, model theo vai trò, ngân sách token, capture và đường dẫn dữ liệu. API key đặt trong `.env` theo [.env.example](.env.example), không ghi vào TOML.

```sh
uv run worldascode --config worldascode.toml config show
uv run worldascode demo
uv run worldascode serve --run .worldascode/runs/semantic-demo
```

`config show` không xuất giá trị API key. Endpoint LLM cần hỗ trợ giao thức OpenAI-compatible `chat/completions`. Model mặc định là `gpt-6-sol`; ID phải được provider của bạn cung cấp. Có thể đặt model và provider riêng cho observer, style, author, critic, planner, kit developer.

Đường dẫn trong TOML tính từ thư mục chứa TOML. `WORLDASCODE_CONFIG`, `WORLDASCODE_DATA_DIR`, `WORLDASCODE_NODE_MODULES`, `WORLDASCODE_ENV_FILE` cho phép triển khai ngoài checkout. Khi không chọn config, hệ thống chỉ tìm `worldascode.toml` ở cwd; không quét các thư mục cha.

## Chạy workflow

```sh
uv run worldascode design --evidence /path/to/evidence --styles /path/to/styles --run /path/to/new-run --adaptive-kit --require-quality
uv run worldascode serve --run /path/to/new-run
uv run worldascode kit-library status
uv run worldascode kit-library search --query roof
```

Observer đọc bằng chứng và kích thước; author viết JavaScript sử dụng kit; trình duyệt dựng ảnh; critic trong workflow đánh giá và gửi phản hồi cho vòng sửa. Kit developer tạo candidate riêng khi thiếu capability. Đưa vào kho chung cần grant từ host, kiểm thử và promotion; workflow không tự cấp quyền. Context kit được chọn theo API liên quan thay vì nạp toàn kho.

`design --help`, `capture-site --help`, `reference-serve --help` mô tả đầu vào cụ thể. Capture Google/Cesium cần `CESIUM_ION_TOKEN` có quyền dataset tương ứng. Runtime không cần img2threejs, checkout upstream, skill hoặc upstream lock.

Đối tượng viết Three.js riêng có thể export `createModel(options)` và trả về `THREE.Object3D`. Khi ghép scene, dùng blueprint `origin: "factory"` và `compose --factories factories.json` với ánh xạ ID blueprint → đường dẫn module JS/TS. Factory nhận `seed` và `instanceId`; hệ thống đặt anchor/rotation/scale. Không cần signature hoặc metadata từ generator bên ngoài. Xem [hợp đồng factory và chuyển đổi](docs/architecture/independent-runtime.md).

Chạy xong và đạt chất lượng là hai trạng thái riêng. `--require-quality` trả exit code 2 nếu chưa được chấp nhận; workflow vẫn lưu ảnh, phản hồi và usage. Các pilot cũ chưa được coi là đạt chất lượng chỉ vì refactor thành công.

## Cấu trúc và kiểm thử

- [Thiết kế hệ thống](docs/architecture/system-refactor.md): ranh giới module, cấu hình, kit và dữ liệu.
- [Vận hành và kết quả kiểm chứng](docs/operations/refactor-validation.md).
- [SpecKit hệ thống](specs/001-workflow-system/spec.md).
- [Runtime độc lập và kết quả bỏ adapter](docs/architecture/independent-runtime.md).
- [Phương pháp và hạn chế trước refactor](workflow_scale_research/docs/00-phuong-phap-hien-tai.md).

```sh
uv run pytest -q
uv run ruff check src tests
uv run ruff format --check src tests
uv build --wheel
```

Wheel chứa Python và tài nguyên JS; môi trường chạy vẫn cần Node dependencies từ `package-lock.json` và Chromium của Playwright. Dữ liệu thay đổi được lưu ở `.worldascode/` theo mặc định, tách khỏi package cài đặt.
