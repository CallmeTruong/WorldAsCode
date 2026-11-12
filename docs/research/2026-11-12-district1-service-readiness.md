# Khảo sát dịch vụ và dữ liệu Quận 1 — 12/11/2026

**Scope:** Read-only probes có giới hạn; không inference, không dựng viewer/pipeline đô thị, không upload asset và không trích mesh/texture Google.  
**Khu vực:** Bbox WGS84 south=10.773, west=106.700, north=10.777, east=106.704; khoảng 437×445 m quanh Nguyễn Huệ–UBND TP.HCM. Đây không phải boundary hành chính.

Bằng chứng máy đọc: [service-probe.json](2026-11-12-district1-service-probe.json). Snapshot OSM nhỏ: [district1-osm.osm](2026-11-12-district1-osm.osm). Nghiên cứu/thiết kế: [urban_grid_research.md](../urban_grid_research.md).

## Kết quả truy cập đã quan sát

| Dịch vụ/phép thử | Kết quả | Kết luận được phép |
|---|---|---|
| Cesium asset list | HTTP 200; Terrain, OSM Buildings, Google Photorealistic 3D Tiles có trạng thái COMPLETE | Token đọc được danh sách asset này |
| Terrain asset 1 endpoint + root metadata | HTTP 200 + HTTP 200, bounds metadata toàn cầu | Truy cập metadata thành công; chưa kiểm tra độ phân giải/độ chính xác cao độ trong AOI |
| OSM Buildings asset 96188 endpoint + root metadata | HTTP 200 + HTTP 200 | Truy cập tileset root thành công; chưa xem building tiles tại AOI |
| Google asset 2275207 endpoint | HTTP 200, external 3DTILES metadata | Truy cập metadata dịch vụ được; chưa tải root/child Google tiles hoặc xác nhận coverage địa phương |
| Gateway LLM model discovery | HTTP 200, model đã cấu hình có trong danh sách | API discovery được; đợt này không gọi inference |
| Poly Haven texture catalog | HTTP 200, 869 catalog entries, có asphalt/concrete IDs | Đọc catalog được; chưa tải texture payload hoặc render vật liệu |
| Overpass chính | HTTP 502 | Request thất bại, không suy ra khu vực không có dữ liệu |
| Overpass Kumi fallback | ReadTimeout | Chưa dùng được trong lần thử này |
| Overpass private.coffee count fallback | ReadTimeout | Chưa dùng được trong lần thử này |
| OSM small map bbox fallback | HTTP 200, 851.594 bytes | Đã đọc dữ liệu vector cụ thể cho bbox nhỏ |

Lần fallback map API chỉ là phép đọc nhỏ, có snapshot để tránh truy vấn lại. Không dùng map API công khai làm backend bulk download cho cả thành phố; production/batch nên đánh giá regional extracts, cache dữ liệu OSM hợp lệ hoặc Overpass tự host/provider khi cần.

## Dữ liệu OSM thực nhận

| Trường | Số lượng |
|---|---:|
| Nodes | 1.997 |
| Ways | 309 |
| Relations | 55 |
| Phần tử có tag building | 55 |
| Có tag height | 5 |
| Có tag building:levels | 6 |
| Highway ways | 198 |
| Highway ways có width | 0 |
| Highway ways có lanes | 37 |
| Tree nodes | 16 |
| Street lamp nodes | 6 |

Chỉ **9/55 phần tử building có ít nhất height hoặc building:levels** (khoảng 16,4%; hai trường có thể cùng tồn tại). Highway ways gồm 99 footway, 17 pedestrian, 23 service, 17 residential, 9 secondary, 29 tertiary và 4 steps. Cần chuẩn hóa graph/ngữ nghĩa trước khi đếm tuyến phố hoặc suy ra cross-section.

**Đây là counts phần tử trả về**, chưa deduplicate thành công trình vật lý và chưa đo độ đầy đủ. Map bbox có crossing ways và referenced elements nằm ngoài khung; relations có thể chưa đủ members. `highway ways` bao gồm đường đi bộ và các loại khác, không phải 198 tuyến đường ô tô độc lập.

Tên đường trong dữ liệu gồm Nguyễn Huệ, Lê Lợi, Lê Thánh Tôn, Đồng Khởi, Pasteur và các đường tham chiếu khác. Có dữ liệu đủ để tiếp tục audit topology, nhưng chưa đủ để cam kết tái tạo đầy đủ nhà/đèn/cây hoặc chiều rộng đường.

## Hệ quả cho workflow cần nghiên cứu

1. **Chiều cao còn thiếu:** đa số phần tử building không có height/floor tags trong snapshot. Cần ảnh/metadata hợp lệ hoặc rule-based estimate có confidence. Không tự biến mặc định số mét/tầng thành đo đạc thực tế.
2. **Đường cần phân loại:** audit footway/pedestrian/service/primary/... và layer/bridge/tunnel, không tạo mỗi way thành một road corridor riêng. Width không có phải là inferred hoặc bổ sung từ nguồn hợp lệ.
3. **Cây/đèn chỉ là phần được mapping:** giữ các node quan sát từ OSM; bố trí bổ sung theo quy tắc phải có nhãn procedural/inferred.
4. **Fallback source adapter cần thiết:** endpoint health, retry/backoff hữu hạn, partial-response checks, snapshot hashes và data audit trước generation.
5. **Google là optional visualization:** metadata sẵn có chưa chứng minh AOI có photorealistic coverage và không cho phép suy ra quyền tái tạo/export. Nhánh procedural dùng dữ liệu được phép tạo derivatives.
6. **Style reference chưa được cung cấp:** folder/profile pipeline là yêu cầu thiết kế mới. Chưa trích style, chưa có paired renders, không khẳng định user-style đã đạt.
7. **Chưa có ngân sách batch mới:** không gọi LLM hay chạy streaming/render batch trong đợt này. Probe metadata có thể tiêu thụ provider quota; chưa có billing ledger để kết luận phí bằng 0.

## Kết luận readiness

**Có thể tiếp tục nghiên cứu thiết kế và chuẩn bị pilot. Chưa đủ bằng chứng để gọi đô thị sẵn sàng dựng chính xác.** Những phần cần xác minh tiếp là local visual coverage, rights cho factual images/terrain export, data normalization/dedup, chiều cao/bề rộng còn thiếu, thư mục style thực tế, budget và baseline compatibility.

Không có secret/token/signed URL được lưu trong báo cáo. `temporary_credential_returned` trong evidence chỉ là boolean.

## Nguồn chính thức

- [Cesium token scopes](https://cesium.com/learn/ion/cesium-ion-access-tokens/)
- [Cesium content usage](https://cesium.com/learn/ion/content-usage-and-attribution-guide/)
- [Cesium Google tiles](https://cesium.com/learn/cesiumjs-learn/cesiumjs-photorealistic-3d-tiles/)
- [Google Map Tiles policies](https://developers.google.com/maps/documentation/tile/policies)
- [OSM API map call](https://wiki.openstreetmap.org/wiki/API_v0.6#Retrieving_map_data_by_bounding_box:_GET_/api/0.6/map)
- [OSM/Overpass](https://wiki.openstreetmap.org/wiki/Overpass_API)
- [OSM copyright/license](https://www.openstreetmap.org/copyright)
- [Poly Haven license](https://polyhaven.com/license)
