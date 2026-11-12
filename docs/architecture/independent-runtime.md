# Runtime độc lập

Ngày: 2026-11-13. Thay thế thiết kế adapter optional ở commit `c6cbce2` theo yêu cầu bỏ hoàn toàn phụ thuộc img2threejs.

## Quyết định

Workflow chính vẫn là evidence địa lý/ảnh/style → measured site → author → Three.js → kiểm tra hình học → critic → sửa design hoặc candidate kit. Nhà phát triển workflow cải tiến vòng lặp; node critic gửi phản hồi trực tiếp cho node author/kit developer. Không có workflow upstream chạy song song.

Đã bỏ `experimental/native`, diagnostic chỉ dùng nhánh đó, CLI `native`, `native-pin`, `status` cũ, schema patching/compiler contract/state machine riêng của upstream. Các kiểm thử chỉ kiểm chứng giao thức upstream cũng được bỏ cùng tính năng. Không chuyển chúng thành module core không có nơi sử dụng.

Giữ các khả năng độc lập đang dùng: footprint/height/roof fitting, metric checks, AST và protected kit patches, seed, batching, trạng thái ngày đêm/thời tiết, review/refinement, publication có quyền host. Primitive text patch được hợp nhất vào `kits/code.py`. Kiểm tra lỗ rỗng không còn tra cứu metadata `sculptRuntime`; dùng tên Object3D, tâm lỗ phải thông và probe thành phải chạm hình học thật. Chiều dài probe biến đổi theo scale của đối tượng.

## Hợp đồng factory nội bộ

Một module `.mjs`, `.js` hoặc `.ts` export:

```js
import * as THREE from 'three';

export function createModel({ seed = 0, instanceId = 'asset' } = {}) {
  const root = new THREE.Group();
  // Tạo hình học bằng kit hoặc Three.js; dùng seed khi cần biến thể.
  const mesh = new THREE.Mesh(
    new THREE.BoxGeometry(2, 4, 2),
    new THREE.MeshStandardMaterial({ color: '#a99988' })
  );
  mesh.name = 'shell';
  root.add(mesh);
  return root;
}
```

Hàm trả `THREE.Object3D`; esbuild xác nhận export khi bundle, runtime từ chối giá trị trả sai. Không parse chữ ký bằng regex hoặc yêu cầu kiểu `ProceduralModelOptions`. Có thể dùng named function hoặc exported arrow function.

- Python: `bundle(out, factory=module)` để render một đối tượng.
- Scene: blueprint `origin: "factory"`; `bundle(out, world=recipe, factories={blueprint_id: module})`.
- CLI: `compose --world world.json --factories factories.json --run new-run`. `factories.json` là object ID blueprint → đường dẫn module; đường dẫn module tương đối tính từ cwd.
- Mapping factory phải khớp đúng tập blueprint factory; thiếu hoặc thừa bị từ chối.
- Khi compose, factory nhận seed `world.seed XOR instance.seed` và `instanceId`; placement/rotation/scale do World quản lý.
- `root.userData.semanticChecks` có thể khai báo probe với `component_id`, `axis`, `centre`, `length`, `wall_probe`, `requirement`; component phải có tên Object3D tương ứng, duy nhất trong factory. `GeometryProbe` xác thực file `semantic-overlay.json` tùy chọn khi render factory riêng; file này còn yêu cầu `confidence: "observed" | "inferred"`.

Đây là hợp đồng dựng đối tượng, không phải adapter dịch vụ. Factory là code có quyền dựng cảnh; network vẫn bị chặn trong browser review. Không coi lint hoặc probe là sandbox chống code độc hại. Factory không tự thừa hưởng điều khiển thời tiết cho mọi material; muốn phản ứng riêng cần triển khai theo runtime state contract hiện có.

## Kit và dữ liệu

Kit nền ở `src/worldascode/resources/runtime`; kho mutable mặc định ở `<paths.data_dir>/kit-library`. Kho nghiên cứu `workflow_scale_research/kit_library` giữ nguyên, chưa tự nhập hoặc cấp lại quyền. Không sửa byte/hash các release lịch sử.

Kho kit lưu code + manifest + API cards + validation. Author truy xuất phần API liên quan; kit developer tạo candidate riêng; đưa vào kho chung vẫn cần validation và grant host.

## Chuyển đổi và giới hạn

Các job native cũ không resume trong hệ thống mới. Muốn dùng lại factory cũ, chủ động port code sang export `createModel`, thay metadata bằng Object3D names/probe, khai báo `origin: "factory"`, rồi render/kiểm chứng lại. Không chỉ đổi nhãn rồi coi kết quả cũ đã accepted.

Các thư mục research và vendor cũ trên máy không bị xóa vì là lịch sử nghiên cứu. Chúng không được import hoặc đóng gói trong runtime mới. Không cần copy lại upstream hay nạp SKILL.md/grimoire khi chạy.

Kiểm chứng độc lập được ghi trong [báo cáo](../operations/independent-runtime-validation.md). Đợt này không tuyên bố nâng fidelity kiến trúc hoặc hoàn thiện benchmark đô thị.
