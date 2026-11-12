# Thiết kế triển khai mới

## Hai mặt phẳng phối hợp

**Asset reconstruction** gần skill gốc: reference admission → observation/spec search → assessment/quality contract → native ObjectSculptSpec → strict validation → từng native pass → compile/render → deterministic + semantic gates → critic → continue/refine-spec/refine-code/request-input/stop. Native state là thẩm quyền cho thứ tự pass. Agent trong workflow đánh giá và phản hồi, người phát triển chỉ audit input/output và sửa workflow.

**World composition** phục vụ scale: World IR có ID ổn định, nguồn/độ tin cậy, tọa độ, blueprint version, instance seed và material slots. Asset recipe được compile xác định; landmarks dùng custom/native sculpt riêng. Thay màu vật liệu đặc biệt không fork cả generator. Đường/ray là graph chung trước khi chia tile. Xe/tàu/động vật là actor/rig + runtime/controller contracts; chưa coi schema là mô phỏng đã hoàn thành.

## Phân chia trạng thái

Blueprint lưu code/schema/semantics/LOD. Instance lưu vị trí, footprint, tham số, seed channel và overrides. Runtime state lưu thời gian, wetness, wind, emissive và actor pose. Evidence-locked attributes không được thay bởi seed hoặc thời tiết. Seed hình thái, surface, occupancy và behavior tách kênh. Runtime đổi ngày/đêm/mưa không rebuild geometry; hash geometry phải giữ nguyên.

Ống khói/vent có shell, wall thickness và đường thoát; cửa/portal có opening phù hợp; mái có topology và attachment. Một mesh kín vẫn có thể là thành ống rỗng. Semantic compiler có generator hollow shaft, roof và facade parts; tests phải đo opening thực, không tin cờ `hollow:true`. Custom geometry cần geometric probes/contract riêng. Đây là lớp bổ sung đô thị, không được tự gắn nhãn native pass.

## Scale và tính nhất quán

Graph có global IDs/stationing, tile có owner + references + halo. Biên đường/ray phải khớp position/elevation/tangent/width và UV phase. World origin dùng tọa độ chuẩn, renderer dùng local coordinates. Asset cache key tách geometry/appearance/instance/runtime; giữ code, recipe và compiled artifact. Chỉ publish atomic manifest khi hash nguồn, render và review đồng nhất. Unload tile không xóa actor simulation state hoặc asset đang được tile khác dùng.

## Các node và công cụ

Provider dùng GPT Sol và base URL trong `.env` gốc; không log secrets. Native bridge gọi đúng executable upstream bằng subprocess, lưu stdout/stderr/hash/exit code. Renderer dùng Three.js trong browser sandbox, capture front/oblique/rear và matched reference views; semantic and camera scope gates chạy trước critic. Critic trả action và per-feature evidence, không tự sửa code. Scheduler giới hạn correction/calls/tokens/time, cache artifacts theo dependencies và không retry request chưa rõ đã tính phí.

## Vertical slices và giới hạn

Triển khai trước: package độc lập, native bridge/state/gates, semantic IR/compiler, hollow geometry và state bindings, graph seams, immutable cache/job ledger, browser evidence, staged node driver và kiểm thử. Dùng một asset bounded từ ảnh Tokyo để chạy bridge và tìm lỗi thực; scene demo riêng minh họa reusable assets + ngày/đêm/mưa/seed. Demo semantic không được coi là tái tạo thật Tokyo. Các native pass chưa đạt phải giữ trạng thái pending; quality ngang skill gốc chỉ được kết luận sau native pass evidence và visual audit, không hứa từ đầu.

Simulation giao thông/đường sắt/động vật hoàn chỉnh, terrain toàn thành phố và throughput lớn là phase sau. Có interfaces rõ nhưng không gắn cờ implemented nếu chưa có execution evidence.
