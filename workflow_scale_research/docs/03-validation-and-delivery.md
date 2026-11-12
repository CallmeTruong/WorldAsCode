# Kiểm chứng và bàn giao

1. Pin checkout upstream và toàn bộ contract context; không sửa vendor. Native commands/state/logs là bằng chứng tương thích.
2. Negative tests: không mở pass sau khi pass trước chưa review, không generate shallow strict spec, không publish source/render khác hash, không accept feature định danh hoặc semantic opening sai.
3. Geometry tests: hollow shaft có khoang thực và thành đúng độ dày; roof/facade slots và attachments; không chấp nhận hộp đặc chỉ vì screenshot giống từ xa.
4. Runtime tests: ngày/đêm/mưa đổi light/emissive/wetness, không đổi geometry IDs/anchors/hash; cùng seed/channel/version lặp lại đúng, thay một channel không kéo theo các channel khác.
5. Graph/cache tests: tile seam/owner, stationing/UV liên tục, thay texture không rebuild geometry, thay topology invalidates dependencies thật sự; stage interruption/resume không lặp request đã cache hoặc dùng render cũ cho source mới.
6. Browser capture/critic: multi-view images readable, scope/camera/hash verified, actual style images supplied; spec/refine routing và feedback đều nằm trong workflow nodes. Human audit không thay câu trả lời của critic bằng điểm tự đặt.
7. Report phân biệt technical valid, native strict valid, native passes complete, semantic valid và visual accepted. Chi phí ghi tokens/calls/actual configured rates; không đoán USD hoặc city-scale speed từ một asset.

Thư mục mới chứa code và docs riêng, không import `building_workflow`. Checkout skill có thể là canonical shared dependency đã pin; input Tokyo là fixture liên kết/copy có provenance, không hardcode thành generator theo thành phố. Bản cũ giữ lại để đối chiếu.
