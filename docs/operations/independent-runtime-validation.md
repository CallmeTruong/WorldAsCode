# Kiểm chứng runtime độc lập

Ngày: 2026-11-13. Thiết kế: [independent-runtime.md](../architecture/independent-runtime.md).

## Kết quả

- **105 tests passed**, không skip, trong 49,21 giây. Bộ test trước có 117: bỏ 17 test chỉ dành cho nhánh adapter/schema đã xóa, thêm 5 case hợp đồng độc lập. Kiểm thử workflow chính, hồi phục, kit developer/publication, footprint, hình học và browser vẫn chạy.
- Ruff check passed; Ruff format xác nhận 65 file; kiểm tra cú pháp JavaScript passed.
- Wheel được build từ build directory mới; kiểm tra archive không có `experimental/`, adapter diagnostic hoặc schema patching đã bỏ.
- Cài wheel vào venv mới không editable; chạy Python `-I` từ thư mục tạm ngoài checkout, dùng TOML ở cwd và đường dẫn toolchain explicit. Không cấu hình upstream hoặc dùng research input.
- CLI help không còn `native`, `native-pin` và `status` riêng của adapter. `kit-library status` và các lệnh workflow chính vẫn tồn tại.
- Installed `doctor` passed. Installed demo passed: 18.336 triangles; tâm lỗ ống khói thông, probe thành có va chạm; đổi trạng thái không tạo lại hình học.
- Installed subprocess kit regression: cả ba fixture passed, bao gồm mái/UV và ống khói rỗng.
- Installed `compose`: ghép hai instance từ module JavaScript export `createModel`, kiểm tra kỹ thuật passed. Kết quả vẫn là draft, `accepted: false`, đúng hợp đồng scene-level review.
- Đã xem trực tiếp ảnh demo; đây là fixture kỹ thuật giữ nguyên hình học cơ bản, không phải benchmark tái tạo công trình mới.

## Các lỗi phát hiện và xử lý

1. Probe dùng độ dài local sau khi công trình được scale: thêm test scene scale 2, quan sát fail, đổi chiều dài ray sang world-space, test passed.
2. Review độc lập phát hiện compose ghi đè tên Mesh gốc: thêm test trả Mesh thay vì Group, quan sát fail; giữ tên root, lưu danh tính instance ở `userData.instanceId`. Test standalone/composed, seed/anchor và bịt lỗ đều passed. Reviewer kiểm tra lại và không còn blocker.

## Phạm vi bảo toàn

Không sửa kho kit/release lịch sử, grants, ảnh hoặc mã research. Kit nền vẫn ở `src/worldascode/resources/runtime`; logic author/critic/refinement và quyền host giữ nguyên. Không gọi LLM trả phí. API model routing không thay đổi trong đợt này.

Job native cũ không resume; cần port factory và kiểm chứng lại theo hợp đồng mới. Runtime không đọc upstream lock, skill, grimoire hoặc gọi script img2threejs. Các thư mục lịch sử vẫn được giữ ngoài package. Linux/macOS và chất lượng tái tạo đô thị lớn chưa được kiểm chứng trong đợt này.
