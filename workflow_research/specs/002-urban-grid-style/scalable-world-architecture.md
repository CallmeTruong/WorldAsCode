# Kiến trúc đề xuất để scale đô thị có trạng thái

Đây là phân tích/thiết kế đề xuất, không phải danh sách tính năng đã triển khai. Bản thử Tokyo hiện chưa đạt chất lượng hình học, vật liệu và style để nhân rộng. Không nên scale cách mỗi ô đều yêu cầu LLM viết lại toàn bộ chương trình Three.js rồi chấm nhiều vòng.

## 1. Kết luận từ input–output thực tế

Đã xem ảnh style gốc, ảnh nguồn toàn khu vực, ảnh cận cảnh Google 3D Tiles và ảnh render của workflow. Các vấn đề quan sát được:

- Bố cục/footprint có thể nhận diện, nhưng mái, nhịp mặt đứng, cửa và chi tiết đặc trưng vẫn bị giản lược thành các primitive lặp lại. Mái của nhà cổ chưa có đúng hệ gable/dormer; mặt đứng thiếu chiều sâu và phân cấp viền cửa.
- Vật liệu phẳng, glazing đồng đều và chi tiết cửa thiếu articulation tạo cảm giác mô hình đồ chơi/CAD. Bỏ texture bắt buộc đã gỡ một ràng buộc sai, nhưng không tự tạo ra hình học và vật liệu tốt.
- Khối đế/mái trên cao từng bị observer hiểu nhầm. Các mốc cao độ từ source mesh đã giúp observer xác định lại mái của tháp gần 170 m. Ảnh đa góc vẫn cần bằng chứng không gian và độ tin cậy, không thể coi mọi nhận xét vision là đúng.
- Ảnh cận cảnh nguồn đã clip theo đối tượng trong khi render giữ cả hàng xóm; công trình tiền cảnh có thể che mất phần đang chấm. Đã bổ sung capture cùng camera/cùng scope hiển thị và manifest visibility/hash. Các đánh giá trước sửa lỗi này không phải phép so sánh cận cảnh đáng tin cậy.
- Khi rollback checkpoint cũ, manifest capture mới có thể còn sót lại. Đã bổ sung lưu/khôi phục manifest và gate kiểm tra source hash, camera, visibility và PNG hash trước khi chấm/công bố.
- Node hiện thiên về dấu hiệu nhìn thấy, chưa có hợp đồng ngữ nghĩa vật thể. Ví dụ code ống khói dùng thân `box` và nắp `box`, không mô tả thành ống, đường thoát khí hoặc khoang rỗng. Mesh hợp lệ không chứng minh vật thể đúng cấu trúc.

Định dạng hiện tại: `building-generator.ts` là TypeScript dùng Three.js; `urban-worker.js` là chương trình build đã bundle; `buildings-scene.json` là serialization Object3D/geometry/material của Three.js; `city.json` lưu dữ liệu cảnh và thuộc tính; `presentation.json` cấp dữ liệu cho viewer. Chưa có nhánh xuất GLB/3D Tiles thành phẩm trong workflow này. Google 3D Tiles là nguồn bằng chứng đầu vào.

Nhánh hiện tại là research adapter, không phải toàn bộ pipeline img2threejs nguyên bản. Trong checkout local, img2threejs có `ObjectSculptSpec`, các pass blockout/structural/form/material/surface/lighting/interaction/optimization và gate theo feature/domain. Adapter đã tái sử dụng một số gate và thêm node riêng, nhưng native eight-pass baseline chưa hoàn thành. Cùng xuất Three.js không bảo đảm cùng quy trình hoặc chất lượng.

## 2. Tách blueprint, instance và runtime state

Không phân loại nguyên đối tượng thành chỉ “tĩnh” hoặc “động”. Phải phân loại thuộc tính:

| Đối tượng | Dữ liệu giữ ổn định theo bằng chứng | Biến thể/bộ sinh có seed | Trạng thái runtime |
|---|---|---|---|
| Nhà/công trình | Vị trí, footprint, phần cao–thấp, hình mái, hệ mặt đứng, landmark | Chi tiết thứ cấp chưa quan sát, mức LOD, một số trang trí phù hợp | Đèn cửa sổ, emissive, độ ướt, tuyết/bẩn, biển điện tử |
| Đường/vỉa hè | Tim tuyến, cao độ, nút giao, làn/biên đã biết, cầu/hầm | Biến thiên bề mặt, vết nứt phụ, kit vỉa hè | Ướt, tuyết, vũng nước theo mask, trạng thái giao thông |
| Đường sắt | Tuyến ray, gauge, cao độ, ghi, sân ga, liên kết | Kit tà vẹt/cột/chi tiết tuyến | Tín hiệu, ghi hoạt động, lịch tàu, trạng thái block |
| Cây | Anchor và loài/kích thước nếu có bằng chứng | Hình tán, nhánh, lá với seed riêng | Gió, mùa lá, ẩm/tuyết; không đổi anchor theo gió |
| Đèn đường | Cột, vị trí fixture, hướng chiếu, liên kết mạng điện/khu vực | Biến thể kit nếu chưa có dữ liệu | Bật/tắt, cường độ, nhiệt độ màu, lịch và sự cố |
| Xe/tàu/người/động vật | Asset/rig, kích thước, các ràng buộc hình học | Ngoại hình, phân bố/spawn, biến thiên hành vi | Pose, vận tốc, tuyến, hoạt ảnh, đèn và hành vi |

Ba bản ghi riêng:

1. **Blueprint/generator:** code tái sử dụng có version, schema tham số, material slots, LOD và kiểm thử.
2. **Instance:** ID ổn định, vị trí, tham số thực tế, seed theo kênh, override vật liệu và provenance/confidence.
3. **Runtime state:** clock, weather, light state, animation, route progress và simulation ownership. Không viết lại generator khi những trạng thái này thay đổi.

Thuộc tính nên có chính sách `evidence_locked`, `inferred`, `procedural`, `runtime` và `user_override`. Ví dụ không cho seed mới đổi footprint đã xác nhận; đổi seed cây chỉ đổi hình dáng ở cùng anchor. Nguồn mới sửa một công trình tạo revision mới, không ghi đè âm thầm mọi bản đã duyệt.

## 3. Scene IR/World IR là nguồn dữ liệu trung tâm

LLM nên tạo/cập nhật scene specification có cấu trúc thay vì sửa một file TS khổng lồ cho toàn đô thị. IR lưu:

- Stable object/part IDs, loại đối tượng, tọa độ toàn cục và local origin theo vùng.
- Geometry/part recipe, số tầng hoặc khoảng chiều cao có bằng chứng, roof/facade systems và các quan hệ gắn kết.
- Generator reference/version, parameter overrides, geometry/material asset references, LOD/collision/navigation references.
- Material slots như `roof`, `facade.main`, `window.glass`, `window.emissive`, `lamp.fixture`, `road.surface`.
- Runtime capabilities/bindings, seed channels, provenance, confidence và các xung đột dữ liệu chưa giải quyết.

Compiler có tính xác định xây mesh/asset từ IR bằng thư viện geometry đã kiểm thử. LLM được dùng cho quan sát, giải nghĩa, thiết kế recipe và phần custom khó; không tham gia mỗi frame. Custom TS vẫn có chỗ cho landmark, nhưng phải sau một API hình học/semantic contract ổn định và sandbox.

## 4. Hợp đồng ngữ nghĩa cho chi tiết

Lỗi ống khói không được giải quyết bằng cách bắt tất cả vật thể thành cylinder. Cần component type và các thuộc tính vật lý tối thiểu. Ví dụ chimney/vent có shell, wall thickness, flue hoặc exhaust path, opening/rain cap, roof attachment. Ống khói có thể có nắp che hoặc cửa thoát bên; không được suy ra mọi ống đều hở đỉnh. Nhưng một hộp đặc với nắp đặc không tự trở thành hệ thoát khí.

Ống rỗng có thể là mesh manifold kín của **thành vật liệu**, với mặt ngoài, mặt trong và vành nối; khoảng không ở giữa vẫn rỗng. Watertight không đồng nghĩa phải bịt kín lỗ chức năng. `extrudeFootprint` có lỗ là một công cụ có thể dùng để tạo thành ống chữ nhật; cần generator và semantic gate, không chỉ thêm prompt.

Các contract tương tự: portal thực sự có opening; cầu thang có bậc/liên kết cao độ; ban công có sàn/lan can; bánh xe có pivot/tiếp xúc phù hợp nếu phải chuyển động; ray có cặp ray/gauge/tuyến liên tục. Với LOD xa có thể dùng surrogate đơn giản, nhưng asset gần và metadata phải đúng. Không cần dựng mọi nội thất hoặc mô phỏng chất lưu bên trong ống.

LLM observer/spec node khai báo yêu cầu; compiler hiện thực bằng generator đã kiểm thử; semantic validator dùng tham số có kiểm soát và các probe/kiểm tra hình học thích hợp. Coder không được tự chứng nhận “đã có lỗ” bằng một trường JSON không liên kết với mesh thực.

## 5. Ba tầng tái sử dụng asset

**Kit lặp:** cây, cột đèn, biển báo, xe, thiết bị mái, hàng rào, cửa sổ. Lưu generator/rig/mesh dùng chung và instance params/seed. Render bằng instancing khi phù hợp.

**Họ kiến trúc tham số:** nhà phố, khối văn phòng, nhà công nghiệp, mái nhiều cánh, mặt đứng module. Các instance dùng footprint và dữ liệu riêng, không chỉ đổi màu một khối hộp. Seed chỉ áp dụng chi tiết phụ chưa có bằng chứng, không random hóa đặc trưng thực tế đã biết.

**Landmark/custom:** silhouette, roof system hoặc mặt đứng mang tính nhận diện mà generator chung không thể biểu diễn tốt. Dành ngân sách riêng cho quan sát/detail/kiểm chứng; giữ code custom, spec, feature anchors và compiled assets theo version. Vẫn tái sử dụng các phần con như cửa, ống, kính, đèn và cây.

Texture đặc biệt, biển hiệu hoặc một loại gạch thường là material/decal override của slot ổn định, không phải lý do fork toàn bộ generator. Chỉ tách kiến trúc riêng khi hình học hoặc cấu trúc nhận diện khác. Style là profile độc lập; không dùng palette cố định để đồng nhất vật liệu của mọi đối tượng.

## 6. Ngày/đêm, thời tiết và chuyển động

World environment quản lý clock/timezone, mặt trời/bầu trời, mây, sương, mưa/gió và mùa. Object systems nhận trạng thái qua capabilities:

- Nhà giữ mesh; cửa sổ/biển hiệu thay emissive theo lịch/occupancy có seed ổn định. Không random trạng thái cửa sổ ở mỗi frame.
- Đèn đường giữ cột/fixture; light controller đổi cường độ và nhiệt độ màu, có chuyển tiếp chạng vạng/hysteresis.
- Bề mặt đường/roof/facade giữ albedo cơ sở; weather shader điều chỉnh wetness/roughness, phản xạ và mask tuyết/bẩn. Vũng nước dựa trên vùng/mask hợp lý, không rải ngẫu nhiên mới mỗi frame.
- Cây giữ anchor; vertex/rig animation đổi theo trường gió và phase có seed. Mùa thay lá/material hoặc variant đã chuẩn bị. Wind và shadow-depth pass phải nhất quán nếu cần bóng chuyển động gần camera.
- Xe/tàu/động vật dùng rig, controller và navigation riêng. Đầu vào ảnh xe là snapshot, không tạo ra giao thông thời gian thực nếu chưa có nguồn live.

Phân biệt `style profile`, `material profile`, `environment state` và `simulation state`. Không viết rải rác các nhánh `if night`/`if rain` trong generator nhà/đường. Runtime state thay đổi qua binding, không gọi LLM hoặc rebuild thành phố.

Ảnh photogrammetry có baked lighting/shadows không phải intrinsic albedo. Muốn chuyển ngày/đêm và thời tiết thuyết phục thì reconstructed PBR layer phải tách khỏi evidence layer; giảm exposure của tiles ban ngày không tạo ra relighting đúng. Có thể dùng baked tiles làm nền xa với thỏa hiệp được ghi rõ.

## 7. Đường, ray và grid

Road/lane graph, rail graph và pedestrian navigation là dữ liệu chung. Mesh chỉ là sản phẩm của graph. Lưu node/edge IDs, stationing dọc tuyến, hướng, cao độ, lane order/width, bridge/tunnel/layer; đường và ray cắt nhau trên bản đồ chưa chắc nối ở cùng cao độ.

Grid phục vụ build/streaming/scheduling, không sở hữu độc lập các nửa đối tượng. Một tòa nhà cắt biên có một owner và nhiều cell references. Nút giao/ghi có chủ sở hữu xác định. Dùng halo/context buffer cho đường, rồi clip bản dựng ra cell; kiểm tra cổng biên gồm vị trí, cao độ, tangent, bề rộng, làn và phase UV. Không reset texture hay vạch đường từ đầu ở mỗi ô.

Road UV/marking phase dùng arc length của tuyến chuẩn, không phụ thuộc tile. Ray cần thêm gauge, độ dốc/cant và tính liên tục qua ghi. Xe và tàu theo graph/route, không tự di chuyển theo mesh nhìn thấy. Actor vượt cell giữ ID, pose, tốc độ, route progress và seed; unload render tile không làm mất trạng thái simulation.

## 8. Seed, cache và lưu trữ

Seed theo kênh: `H(worldSeed, objectID, generatorVersion, channel)`. Tách `shape`, `surface_variation`, `window_occupancy`, `spawn`, `behavior`, `wind_phase`. Không dùng một luồng random tuần tự cho cả khu vực: thêm một cây sẽ làm đổi mọi đối tượng sinh sau nó. Reproduce còn cần phiên bản generator, dữ liệu, thư viện và simulation timestep/config.

Lưu cả code/spec và compiled assets:

- `geometry key`: geometry recipe + generator version + LOD; không chứa giờ hoặc thời tiết.
- `appearance key`: material slots + style variant + texture/decal asset versions.
- `instance key`: stable ID + placement + seed channel references.
- `tile manifest`: các object/asset references, network dependencies, boundary contracts và revision.
- `simulation snapshot/event log`: trạng thái có thời gian, riêng với static assets.

Đổi texture một mái chỉ invalidates appearance liên quan; đổi thời tiết không rebuild geometry; nguồn mới đổi footprint thì chỉ rebuild đối tượng và các phụ thuộc thật sự. Chỉ công bố manifest atomic sau các gate, không để viewer đọc bản source/checkpoint và ảnh render của các revision khác nhau.

Có thể bắt đầu bằng modular monolith, file/object storage và job DB; chuẩn hóa interfaces trước khi tách dịch vụ. Khi nhiều worker, PostgreSQL/PostGIS phù hợp với canonical spatial data, object storage cho media/GLB, queue cho job và GPU render worker riêng. Không cần triển khai toàn bộ hạ tầng phân tán ngay trong bản thử.

## 9. Định dạng/tiêu chuẩn đề xuất

- Scene IR/metadata DB lưu ý nghĩa, source và quan hệ; Three.js là runtime/backend hiện tại, không phải schema thế giới.
- glTF/GLB có thể là compiled render asset. Material variants phù hợp lựa chọn hữu hạn; trạng thái wetness/thời gian liên tục vẫn do runtime bindings điều khiển. [KHR_materials_variants](https://github.com/KhronosGroup/glTF/blob/main/extensions/2.0/Khronos/KHR_materials_variants/README.md).
- Dữ liệu fixture/light có thể dùng [KHR_lights_punctual](https://github.com/KhronosGroup/glTF/blob/main/extensions/2.0/Khronos/KHR_lights_punctual/README.md); chính sách điều khiển, ngân sách đèn/bóng vẫn thuộc ứng dụng.
- Các kit lặp có thể dùng [EXT_mesh_gpu_instancing](https://github.com/KhronosGroup/glTF/blob/main/extensions/2.0/Vendor/EXT_mesh_gpu_instancing/README.md). Asset lifecycle cần reference counting để unload một tile không dispose mesh/texture của tile khác.
- [OGC 3D Tiles](https://www.ogc.org/standards/3dtiles/) phù hợp streaming geospatial content theo hierarchy/LOD; không thay thế semantic database hoặc simulation engine.
- Nếu cần tương tác hệ sinh thái lái xe/simulation, xem [ASAM OpenDRIVE](https://www.asam.net/standards/detail/opendrive/) cho static road network và OpenSCENARIO cho dynamic scenarios. Chưa cần buộc IR nội bộ dùng trực tiếp XML này.
- Khi cần traffic logic, có thể kết nối [SUMO/TraCI](https://eclipse.dev/sumo/docs/TraCI/index.html). Với mục tiêu cảnh động trang trí, lane-following có seed đơn giản có thể đủ cho giai đoạn đầu; không nên tự viết mô phỏng giao thông đầy đủ nếu không cần. [SUMO reproducibility](https://eclipse.dev/sumo/docs/Simulation/Randomness.html) cũng nêu seed không loại bỏ mọi khác biệt do phiên bản/platform.

## 10. Lộ trình và gate trước khi scale

**Bước 1 — correctness một vùng:** chuẩn hóa IR/component contracts, sửa visibility/camera pairing, numerical evidence, staged feature/style review, compiler/semantic checks và publication consistency. Hoàn thiện vài mái/mặt đứng/landmark thật sự bằng nodes, không nới điểm để qua gate.

**Bước 2 — vertical slice 2×2 cell:** một landmark, vài building families, shared street intersection, cây có seed, đèn có lịch, ngày/đêm và khô/mưa. Test vị trí/ID/geometry ổn định khi đổi runtime state, chỉ kênh seed được phép thay đổi mới đổi. Đưa ray/động vật vào fixture riêng khi có dữ liệu tương ứng; chưa có bằng chứng pipeline hiện tại xử lý được chúng.

**Bước 3 — streaming và reuse:** test 3×3 rồi 5×5 cell, seam/ownership, actor transfer, LOD, memory disposal, cold/warm cache, thời gian và chi phí trên mỗi vùng **đạt** chứ không chỉ mỗi lượt chạy. Render worker trên máy thử hiện có hạn chế tài nguyên; chưa có throughput đô thị được đo.

**Bước 4 — simulation:** thêm xe/tàu/pedestrian/animal controllers theo nhu cầu. Dùng fixed timestep và snapshot/replay phù hợp, tách simulation LOD khỏi visual LOD. Giới hạn đèn thật/bóng quanh camera; xa dùng emissive/approximation. Cache bóng hiện tại chỉ kiểm chứng cảnh tĩnh, không phải giải pháp đầy đủ cho mặt trời liên tục, xe chạy và cây rung.

Hệ thống cần các gate riêng: data/units/provenance, geometry/topology, semantic affordances, graph/seam, visual identity/style, runtime-state invariants và performance. Node chấm hỗ trợ phát hiện lỗi, không thay thế kiểm tra kỹ thuật và audit định kỳ của người cải thiện workflow.
