> Active implementation revision: [scene reconstruction](scene-revision.md). Earlier scope/status statements below are historical where they conflict with this revision.

# Research evidence and unresolved questions

> Current selected result: `district1-quality-v10` (220 m AOI, 3 photo-backed targets and 8 context proxies). Descriptive style preserves native materials; fidelity remains partial. See [quality correction results](../../reports/urban/quality-correction-results.md). Earlier v4/palette/36-building statements below are historical and superseded.


**Date:** 2026-11-12. **Status:** Source/API discovery done within bounded scope; experiments pending.

## Đã kiểm chứng

- Cesium token đọc asset list và metadata endpoints Terrain/OSM Buildings/Google tiles; Terrain và OSM Buildings đọc được root metadata.
- Small OSM bbox map call trả dữ liệu thật cho AOI; 55 building-tagged elements, 9 có ít nhất height hoặc levels, 198 highway ways gồm phần lớn footway/pedestrian/service; đây là counts thô, không là số physical objects độc lập.
- Overpass chính trả 502, hai fallback timeout; giữ evidence và dùng small-map snapshot cho audit.
- Gateway model discovery thành công, không gọi inference mới.
- Poly Haven catalog có texture asphalt/concrete và license CC0 theo trang chính thức; chưa tải material maps.

Evidence: [readable audit](../../../docs/research/2026-11-12-district1-service-readiness.md), [JSON](../../../docs/research/2026-11-12-district1-service-probe.json), [OSM snapshot](../../../docs/research/2026-11-12-district1-osm.osm).

## Các lựa chọn có rationale/alternatives

1. **Global semantics + cell jobs:** giữ stable IDs, road graph và contracts. Thay thế cell độc lập vì lỗi nối biên; không dùng source monolithic toàn khu vực.
2. **Source rights tách riêng:** Google/ion visualization giữ terms theo nguồn; nhánh export dùng dữ liệu được phép tạo derivatives. Thay thế cách screenshot/mesh extraction không kiểm tra quyền.
3. **Structured StyleProfile:** extract một lần, version và tái dùng. Thay thế việc nhét cả folder vào mọi prompt hoặc fine-tune trước khi có baseline.
4. **Trusted material resolution:** model chỉ tham chiếu asset IDs/parameters. Thay thế mở network tùy ý trong generated worker.
5. **Role-aware validation:** solids/surfaces/foliage/instances có checks phù hợp. Thay thế tắt toàn bộ geometry gates.
6. **Measured rollout:** native baseline -> four-cell visual pilot -> controlled scale. Thay thế ước tính benchmark ba buildings thành cam kết throughput/fidelity đô thị.

Các quyết định đầy đủ ở [design.md](design.md).

## Chưa được kiểm chứng

Độ phủ/độ phân giải visual tại AOI; geometric accuracy và quyền source ảnh/DEM cho export; street widths/heights thật; native eight-pass end-to-end; material UV pipeline; style extraction từ folder thực; bốn cell nối đúng; world placement; actual GLB city export; viewport performance; batch cost/quota và tính tổng quát ngoài AOI.

Không có style refs/user-style results ở thời điểm viết. Tiêu chí tiếp theo và gói kết quả cần xem nằm ở [experiments.md](experiments.md).

## Primary sources

- [Cesium tokens](https://cesium.com/learn/ion/cesium-ion-access-tokens/)
- [Cesium data usage](https://cesium.com/learn/ion/content-usage-and-attribution-guide/)
- [Cesium Google tiles](https://cesium.com/learn/cesiumjs-learn/cesiumjs-photorealistic-3d-tiles/)
- [Google policies](https://developers.google.com/maps/documentation/tile/policies)
- [OSM/Overpass](https://wiki.openstreetmap.org/wiki/Overpass_API)
- [OSM license](https://www.openstreetmap.org/copyright)
- [Poly Haven license](https://polyhaven.com/license)
- [Three.js InstancedMesh](https://threejs.org/docs/pages/InstancedMesh.html)
- [Three.js KTX2Loader](https://threejs.org/docs/pages/KTX2Loader.html)