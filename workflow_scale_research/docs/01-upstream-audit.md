# Audit img2threejs và mục tiêu tích hợp

Ngày: 2026-11-12. Nguồn khảo sát là checkout local `../workflow_research/vendor/img2threejs`, không dùng demo gallery làm bằng chứng cho kết quả của workflow mới. Commit và hash các contract sẽ được pin trong lock manifest.

Skill gốc là quy trình agent chứ không chỉ là một hàm image-to-mesh. Nó dùng local state, `forge/next.py` ở đầu và trước correction, image admission/analysis, local spec retrieval, pre-spec assessment và quality contract, detail inventory ánh xạ tới component/material, topology classification, `ObjectSculptSpec`, schema + strict-quality validation, rồi tám pass khóa thứ tự: blockout, structural, form refinement, material, surface, lighting, interaction, optimization. Review gồm deterministic gates, ảnh cùng reference camera, orbit self-consistency, kiểm tra feature/assembly/attachment, agent vision và lịch sử quyết định. `continue` cần bằng chứng, không được mở khóa bằng điểm do compiler tự điền.

Các script được gọi trực tiếp từ checkout đã pin. Không sửa validator gốc, không tạo log giả rằng native pass đã hoàn tất. Bất kỳ bước nào chưa có bridge thực thi phải hiện pending/blocked. Native strict spec failure phải được đưa lại node spec author, không thay bằng template chung. Correction budgets của upstream phải được giữ và hard-stop phải được tôn trọng.

Khác biệt của adapter cũ: chủ yếu sinh TS tự do và tái sử dụng geometry gate; thiếu native strict-spec/pass lifecycle, giữ nhiều đặc tả dưới dạng prose, semantic object checks yếu, tốn token sửa cả file lớn. Vision từng nhầm roof level; source clip và render visibility từng không khớp. Workflow mới dùng bằng chứng có hash, scope camera rõ ràng và phần semantic/compiler tách biệt.

Mức tương thích được báo cáo theo từng capability: native commands đã chạy, native strict spec đã qua, pass nào đã generate/render/review/check, bước nào chỉ có implementation/test. Một native factory được sinh thành công chưa chứng minh đủ tám pass hoặc chất lượng ngang gallery. Chất lượng phải được so sánh cùng source/style và nhiều góc nhìn.

User chấp nhận vật liệu gần đúng và không bắt buộc texture catalog. Vì vậy material/projection applicability được ghi rõ từng vùng. Không nhận procedural albedo là ảnh gốc; không bake shadow vào màu để giả fidelity. Style là input ảnh độc lập và phải được node critic xem trực tiếp, không phải palette cố định.
