# WorldScale research

Workflow nghiên cứu tạo mô hình đô thị bằng code Three.js: code đo sự thật (footprint, cao độ, đặc điểm mái), agent viết thiết kế bằng một bộ kit kiến trúc theo style mong muốn, và kết quả được kiểm tra bằng dung sai chứ không bằng pixel.

**Đọc trước:** [Phương pháp hiện tại và hướng triển khai](docs/00-phuong-phap-hien-tai.md).

**Trạng thái:** hướng hiện tại đã chạy trọn vòng trên một tòa nhà (38,5k token, build được ngay), critic tự động chưa chấp nhận kết quả. Việc dùng lại script cho nhiều tòa cùng kiểu chưa được thử. Nhánh native img2threejs (lệnh `native`, docs 01–07) là hướng cũ, chỉ còn là tùy chọn.

## Tài liệu và SpecKit

- [Phương pháp hiện tại và hướng triển khai](docs/00-phuong-phap-hien-tai.md) — tài liệu định hướng chính
- Lịch sử hướng cũ (native img2threejs): docs 01–07
- [Audit skill gốc](docs/01-upstream-audit.md)
- [Thiết kế workflow](docs/02-implementation-design.md)
- [Kế hoạch kiểm chứng](docs/03-validation-and-delivery.md)
- [Chi tiết implementation và node contracts](docs/04-implementation-reference.md)
- [Chiến lược scale và phạm vi chưa triển khai](docs/05-scale-strategy.md)
- [Dựng khối từ bằng chứng: footprint, camera thật, trường cao độ, kết quả đo](docs/08-evidence-compiled-massing.md)
- [Agent thiết kế trên site đã đo: kit, style sheet, critic, kết quả pilot](docs/09-agent-design-on-measured-site.md)
- [SpecKit đang dùng](specs/001-native-semantic-world/spec.md), [tasks](specs/001-native-semantic-world/tasks.md)

## Chạy trên Windows

```powershell
cd D:\WorldAsCode\workflow_scale_research
python -m venv .venv
.venv/Scripts/python -m pip install -e '.[test]'
npm ci --ignore-scripts
python scripts/restore_upstream.py
.venv/Scripts/python -m playwright install chromium
.venv/Scripts/python -m pytest -q
.venv/Scripts/python -m worldscale.cli demo
.venv/Scripts/python -m worldscale.cli serve --run runs --port 8770
```

Mở `http://127.0.0.1:8770/semantic-demo/index.html`. Viewer có orbit, chọn part, explode, giờ trong ngày, độ ướt và gió. Đây là fixture kỹ thuật có chủ ý đơn giản để kiểm tra các invariant, không phải showcase đạt fidelity.

Thiết kế một tòa nhà theo hướng hiện tại (chi tiết từng bước trong docs/00):

```powershell
.venv/Scripts/python -m worldscale.cli design `
  --evidence inputs/evidence/tokyo-ichigokan-validated `
  --styles inputs/style-references/user-reference `
  --run runs/new-design --max-revisions 1
```

Nhánh native cũ (không còn là đường mặc định):

```powershell
.venv/Scripts/python -m worldscale.cli native `
  --reference inputs/reference/tokyo/museum-photogrammetry.jpg `
  --styles inputs/style-references/user-reference `
  --run runs/new-museum-pilot `
  --max-calls 10 --max-tokens 240000
```

Có thể truyền thêm `--context path/front.jpg path/rear.jpg`. Style folder nhận ảnh PNG/JPG bất kỳ; ảnh người dùng đã được copy vào `inputs/style-references/user-reference/reference.png`. Không có palette phong cách cố định. Ảnh reference và style tách vai trò trong prompt và provenance.

Đọc `OPENAI_BASE_URL`, `OPENAI_API_KEY` từ `.env` ở workspace. Mặc định `gpt-6-sol`; có thể đặt `WORLD_SCALE_MODEL`. Không dùng Anthropic/Fable. Chỉ tính USD khi có giá hợp đồng gateway qua `WORKFLOW_INPUT_USD_PER_MILLION` và `WORKFLOW_OUTPUT_USD_PER_MILLION`, đồng thời mọi request có usage. Giới hạn token là ngân sách ước lượng và đối soát usage, không phải cam kết trần hóa đơn của gateway.

`native` trả exit code 2 khi blocked hoặc chưa được chấp nhận. `runs/<run>/result.json`, `usage.json`, native logs và SQLite ledger giữ nguyên nguyên nhân. Không đổi `accepted:false` chỉ để có ảnh kết quả. Resume dùng cùng input; thay ảnh hoặc style cần run mới. Request bị timeout/lease chưa rõ trạng thái cần đối soát, không tự retry vô hạn.

Checkout img2threejs được pin ở `../workflow_research/vendor/img2threejs`; đây là dependency source. Application mới không import package `building_workflow`. Các ảnh thử nghiệm là snapshot, chưa có bộ thu input liên tục.

## Ghép asset

Nhánh workflow tự phát triển kit đã có: `design --adaptive-kit --max-kit-cycles 1`, hoặc chạy độc lập `adapt-kit --source-run runs/<design-run> --run runs/<new-run> --max-cycles 2`. Node viết kit chỉ sửa bản sao được cấp quyền, phải qua kiểm thử API cũ + khả năng mới và render/critic trước khi kích hoạt cục bộ. Xem [thiết kế, phân quyền và kết quả thực nghiệm](docs/12-adaptive-agent-kit-evolution.md). Chưa tự phát hành kit dùng chung và chưa chứng minh chất lượng đô thị.

`compose --world world.json --factories factories.json --run runs/composition` dựng một World IR gồm các kit procedural và factory native. `factories.json` ánh xạ blueprint ID sang file factory TS. Instance có anchor, rotation, uniform scale và seed; native landmark không bị random lại kiến trúc. Kết quả composition luôn là draft cho tới khi có scene-level review; chất lượng asset riêng không tự chứng minh chất lượng cả khu phố.
