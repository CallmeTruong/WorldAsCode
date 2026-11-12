# WorldAsCode: từ research package đến workflow hệ thống

> Quyết định cuối sau yêu cầu làm gọn: CLI/package chính chỉ còn `worldascode`, không tạo shim import/CLI `worldscale`. Research giữ nguyên để đối chiếu. Các mô tả compatibility trong thiết kế ban đầu bên dưới chỉ áp dụng việc đọc artifact/release cũ, không phải lớp chuyển tiếp runtime.

## Tổ chức cuối cùng và cấu hình

Các module cùng trách nhiệm được hợp nhất: cấu hình vào `config.py`, trạng thái/lỗi vào `contracts/execution.py`, AST/lint vào `kits/code.py`, catalog/quyền/releases vào `kits/registry.py`, ảnh/camera vào `evidence/images.py`, renderer vào `adapters/rendering/browser.py`. Giữ file riêng khi có ranh giới thực như subprocess worker, CLI entrypoint, provider transport, node AI, workflow điều phối.

`worldascode.toml` chứa endpoint, model từng vai trò, routing provider, ngân sách, capture và đường dẫn. Secrets ở `.env`/environment. Đường dẫn tương đối tính từ config; `.env` mặc định ở cùng thư mục config, hoặc cwd khi không chọn config. `WORLDASCODE_ENV_FILE` thay vị trí secrets. Không tự leo lên repo cha. Giá provider khai báo bằng `input_rate`/`output_rate` (USD/million tokens); giá chưa biết để null. Provider phải dùng giao thức OpenAI-compatible chat/completions. Chưa có adapter native Anthropic protocol.

Kiểm tra cấu hình từ chối khóa sai, provider không tồn tại, kiểu dữ liệu sai và ngân sách âm. Ngưỡng chất lượng được version hóa trong `QualityPolicy`; chưa có override chất lượng theo job trong TOML.

Kit builtin có manifest, dependency AST và API card riêng. Các card ngắn là đơn vị truy xuất context; giữ riêng để tránh nạp toàn bộ tài liệu mỗi node. Tài nguyên Git giữ nguyên byte để checksum nhất quán giữa hệ điều hành. Kho mutable và quyền host nằm ngoài package.

Cài trên máy khác cần đồng bộ Python dependencies, npm lock và Chromium, rồi chọn config và nơi lưu dữ liệu. Không cần đường dẫn máy tác giả hay thư mục research. Native upstream phải pin explicit. Windows ngoài checkout đã có kiểm chứng; Linux/macOS chưa chạy trong phiên này.

Không tự nhập kho/grant cũ: có thể chỉ định `--library` khi thao tác kho lịch sử; cần kế hoạch migration riêng trước khi chuyển quyền và dữ liệu. Đợt này không đổi hash release cũ và không tự nâng channel stable.

Ngày: 2026-11-13. Thiết kế triển khai theo yêu cầu ghi tài liệu rồi thực hiện; không thay đổi mục tiêu chất lượng hoặc tự coi các pilot đã được chấp nhận.

## Mục tiêu và nguyên tắc

Hệ thống chính nằm trong `src/worldascode`, cài được từ root, chạy được ngoài checkout research. Python orchestration, JavaScript runtime và dữ liệu có ranh giới rõ. Không phục hồi file `src/worldascode/__init__.py` mà người dùng đã xóa: dùng namespace package và entrypoint `worldascode.cli.main:main`.

Không thay thuật toán massing hoặc ngoại hình mặc định trong một bước chuyển code. Heuristic capture/feature được đặt tên và version hóa; sự cải thiện thuật toán cần benchmark riêng. Release kit cũ giữ nguyên byte/hash. Grant cũ không tự di chuyển hoặc cấp rộng hơn.

## Kiến trúc đích

```text
src/worldascode/
  config.py          # TOML, Settings, WorkspacePaths, policy profiles
  contracts/         # Run status, artifact references, World IR
  workflows/         # reconstruction, refinement, massing, district
  nodes/             # observation, style, authoring, review
  geometry/          # coordinates, massing, surface height, registration
  evidence/          # bundles, camera preparation, scope checks
  quality/           # visual/metric selection and execution checks
  kits/              # registry, publication, retrieval, code analysis
  execution/         # jobs, worker processes, model budgets
  storage/           # atomic JSON, asset store, manifest lookup
  adapters/          # LLM transport, browser bundle/capture, Cesium viewer
  experimental/      # optional native img2threejs bridge and legacy passes
  cli/               # command registration / dependency composition
  resources/         # packaged JS runtime, builtin kit, schemas/templates
```

Các package có logic thật; không tạo hàng loạt class rỗng. Dependency IO được truyền qua hàm/provider; không xây framework DAG phân tán trong đợt refactor này. Code kiểm thử chuyển sang import hệ thống mới; không có package forwarding `worldscale`.

## Đường dẫn và đóng gói

- Resource readonly được định vị từ package; không suy ra repo cha hoặc quét repo tìm dữ liệu.
- `WORLDASCODE_DATA_DIR` quyết định nơi ghi run/cache/database/registry/grants. Mặc định là `.worldascode` trong working directory; CLI và config ghi rõ vị trí thực tế.
- `.env` đọc từ thư mục config hoặc `WORLDASCODE_ENV_FILE`, không tự leo lên repo cha. Khi không chọn config, dùng cwd. Credentials chỉ tới provider tương ứng.
- Node toolchain được pin bằng root `package.json`/lock; `WORLDASCODE_NODE_MODULES` cho phép worker dùng toolchain đã cài ngoài cwd.
- Capture SDK server đóng gói trong adapter mới. Native img2threejs là adapter optional với upstream path/lock explicit; thiếu dependency báo lỗi có loại, không tìm `workflow_research` ngầm.

## Hợp đồng thực thi

Tách `execution_status` (completed/failed/interrupted), `quality_status` (accepted/rejected/unreviewed), `selection_status` và release channel. Trường legacy được giữ khi cần để đọc artifact cũ nhưng không quyết định exit code ngầm. CLI thành công nghĩa job chạy xong; `--require-quality` yêu cầu quality accepted. Exception transport, input, validation và programming error có mã/traceback riêng. Không retry request billing chưa rõ.

Evidence và run dùng ID/hash + relative artifact references. Manifest resolver đọc artifact của run thay vì glob toàn kho. Cache key gồm evidence/dependency/policy version thực sự được dùng. Recovery chỉ giữ review đã hoàn tất, không promote ảnh chưa review.

## Kit

Giữ checksum master và guard. Catalog, permissions, regression runner và publication policy không import workflow điều phối. `KitRegistry.resolve` báo thiếu channel explicit thay vì trả builtin gắn nhãn stable. Fallback chỉ khi policy yêu cầu và phải ghi requested/resolved channel.

Thay việc parse class bằng khoảng trắng thành JavaScript AST analyzer. Manifest chuẩn ghi exports/dependencies/API cards/validation suite; docs là tài liệu trình bày, không phải nguồn duy nhất cho capability. Reader legacy tiếp tục hỗ trợ release cũ; không sửa lịch sử. Source/runtime slice/developer candidate vẫn là ba artifact khác nhau.

## Chuyển đổi

1. Ghi baseline, schema/config và test ranh giới mới.
2. Chuyển package, tài nguyên và CLI; giữ research nguyên trạng, không tạo shim.
3. Tách node/quality/worker để loại dependency ngược; chuẩn hóa status/path/error.
4. Đóng gói capture service, policy và upstream optional.
5. Chuẩn hóa phân tích code/manifest kit và strict resolution.
6. Chạy suite, render fixture, kiểm wheel trong thư mục sạch, cập nhật docs/SpecKit.

## Bảo toàn và rủi ro

User workspace có file bị xóa và ảnh untracked; không xóa hoặc đưa chúng vào commit. Thực thi tại checkout hiện tại theo phạm vi người dùng đã yêu cầu. Các thư mục research và run cũ giữ nguyên như bằng chứng. Một lần chuyển đổi không đồng nghĩa chứng minh city scale hay nâng chất lượng kiến trúc.

Kết quả thực thi, thay đổi phạm vi và giới hạn được ghi trong `docs/operations/refactor-validation.md` sau kiểm chứng.
