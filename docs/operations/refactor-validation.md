# Vận hành và kiểm chứng refactor

Ngày kiểm chứng: 2026-11-13. Runtime chính: `src/worldascode`; CLI: `worldascode`.

## Cấu hình và triển khai

Chỉnh `worldascode.toml` thay vì sửa Python. Cấu trúc thường dùng:

```toml
[paths]
data_dir = "state"
node_modules = "../toolchain/node_modules"

[llm]
default_provider = "primary"
timeout_seconds = 240

[llm.providers.primary]
base_url = "https://your-provider.example/v1"
api_key_env = "OPENAI_API_KEY"

[llm.providers.review]
base_url = "https://your-review-provider.example/v1"
api_key_env = "REVIEW_API_KEY"
# input_rate = 1.0  # Ví dụ minh họa, không phải giá của model.
# output_rate = 2.0

[models]
default = "gpt-6-sol"
critic = "your-review-model"

[model_providers]
critic = "review"

[budgets]
max_tokens = 220000
max_revisions = 1
max_kit_cycles = 1
```

Đây là ví dụ cấu trúc, cần thay endpoint/model bằng thông tin provider thực. Role để trống kế thừa model mặc định; không route provider thì dùng provider mặc định. Mỗi provider có thể khai báo giá token; không có giá thì báo chi phí chưa biết. API gọi theo giao thức OpenAI-compatible chat/completions.

`--config /path/worldascode.toml` chọn cấu hình. Đường dẫn TOML tính từ vị trí file; các biến `WORLDASCODE_DATA_DIR` và `WORLDASCODE_NODE_MODULES` ghi đè bằng đường dẫn tính từ cwd. `OPENAI_BASE_URL` ghi đè endpoint mặc định; `WORLDASCODE_MODEL` ghi đè model mặc định. Model theo role vẫn ưu tiên nếu đã khai báo. Secrets đọc từ environment trước, dotenv không ghi đè giá trị đã có. Dotenv mặc định nằm cùng TOML, hoặc chọn `WORLDASCODE_ENV_FILE`.

Sau khi cài wheel vẫn cần Node.js, npm dependencies theo lock và Chromium của Playwright. Dùng `doctor` để kiểm tra Node/modules/resources; lệnh này chưa kiểm tra coverage provider hoặc quyền API và chưa xác minh Chromium khởi động được. Demo/browser fixture thực sự khởi động Chromium.

## Dữ liệu và kho kit

- `state/runs`: artifact từng workflow; input evidence/style được truyền explicit.
- `state/cache`: cache có dependency fingerprint.
- `state/kit-library`: catalog, immutable releases, grants và host workflow profile.
- Package resources chỉ đọc; không ghi run/grant vào nơi cài Python.
- Không tự chuyển kho cũ, grant cũ hay nâng channel stable. Thao tác kho cũ có thể chỉ định `--library`; migration đầy đủ cần bước kiểm chứng riêng.

Publication vẫn đi qua quyền host, validation và promotion. Candidate kit bị cô lập theo run; API cards và dependency slice chỉ tải phần liên quan. Những file card ngắn được giữ có chủ đích vì là đơn vị retrieval; các file Python chỉ forwarding đã được bỏ.

## Kiểm chứng

Các kiểm tra được chạy trên Windows, Python 3.12.16:

- Suite root: **117 passed** trong 56,57 giây khi bật upstream explicit. Bao gồm workflow/recovery, transport giả lập, footprint, permissions/publication, AST, cấu hình và portability.
- Kiểm thử native upstream chỉ bật khi truyền `WORLDASCODE_TEST_UPSTREAM`; không phải dependency mặc định.
- Ruff check: passed; format: 72 file đúng định dạng; Node syntax check: passed.
- Build wheel mới; cài không editable trong venv riêng; chạy Python `-I` từ thư mục tạm ngoài checkout với file config riêng. Module được import từ `site-packages`.
- Installed demo: 18.336 triangles; probe tâm ống khói không va mặt, probe thành ống có va mặt; đổi trạng thái giữ nguyên hình học.
- Installed kit fixtures: ba hình học tổng hợp qua kiểm tra mái/UV/lỗ ống khói, không có lỗi browser hoặc request bị chặn.
- Subprocess regression worker cũng chạy thành công từ cwd ngoài repo, tự tìm TOML tại cwd và đọc toolchain theo đường dẫn cấu hình; không đổi cwd sang resources.
- Đã xem trực tiếp ảnh demo. Đây là fixture kỹ thuật đơn giản, không phải công trình được tái tạo từ ảnh thật.

Lệnh fixture nhận `--kit /path/to/kit.mjs`, không phải thư mục runtime. Lần smoke đầu truyền nhầm thư mục đã báo lỗi; chạy lại với file đúng vượt qua cả ba case.

Không gọi LLM trả phí trong đợt refactor. Model routing được kiểm tra bằng HTTP giả lập, không phải xác nhận quyền truy cập model trên provider thật. Chưa chạy Linux/macOS, benchmark đô thị lớn hoặc chứng minh nâng chất lượng thị giác. Các kết quả research chưa accepted vẫn giữ nguyên trạng thái.
