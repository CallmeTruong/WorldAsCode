# SPEC: Agentic Procedural 3D Reconstruction — Research & Optimization

**Project:** Image-to-Procedural-3D Reconstruction System  
**Architecture:** LangGraph + Multimodal LLM APIs + Self-hosted img2threejs Runtime  
**Primary Target:** High-fidelity reconstruction of real-world buildings, scalable to city-level 3D generation  
**Development Approach:** Experimental Research, Benchmark-Driven Optimization, Iterative Engineering

---

## 1. Project Vision

Xây dựng một hệ thống AI có khả năng quan sát ảnh tham chiếu của các công trình thực tế, suy luận cấu trúc hình học, tự động viết procedural generation code để tái tạo vật thể trong không gian 3D, sau đó render, đánh giá và liên tục cải thiện kết quả.

Hệ thống phải tập trung vào **reconstruction by code** — dùng LLM để tạo mã nguồn mô tả hình học có thể tái sử dụng, chỉnh sửa và thực thi — thay vì phụ thuộc vào các mô hình image-to-mesh hoặc image-to-3D black-box.

Định hướng dài hạn là tái tạo một thành phố thực tế, trong đó mỗi tòa nhà được biểu diễn bằng procedural 3D model có hình học và đặc điểm kiến trúc gần với dữ liệu ngoài đời.

Hệ thống cũng phải hỗ trợ thay đổi phong cách hiển thị, đặc biệt là **cartoon / stylized 3D**, mà vẫn giữ được cấu trúc và các đặc điểm nhận dạng của công trình gốc.

### Primary Research Question

> Làm thế nào để xây dựng một workflow tự động sử dụng LangGraph, LLM API và img2threejs nhằm tạo procedural 3D code từ ảnh thực tế với chất lượng cao nhất có thể, đồng thời tối ưu chi phí inference, thời gian xử lý, tài nguyên máy tính và khả năng mở rộng?

Không giả định workflow ban đầu là tối ưu. Mọi quyết định quan trọng phải được kiểm chứng bằng thực nghiệm.

---

## 2. Core Objectives

Hệ thống cần giải quyết đồng thời năm mục tiêu.

### O1 — Geometric Fidelity

Tạo mô hình 3D giữ được cấu trúc chính xác nhất có thể so với ảnh tham chiếu.

Đặc biệt chú trọng:

- Tổng thể silhouette, chiều cao, chiều rộng, tỷ lệ.
- Các khối chính và quan hệ hình học giữa chúng.
- Số tầng và cách tổ chức mặt tiền.
- Vị trí, kích thước, số lượng cửa sổ.
- Ban công, hành lang, phần nhô ra/thụt vào.
- Mái, tầng trệt và những chi tiết kiến trúc đặc trưng.
- Tính nhất quán hình học khi quan sát từ nhiều góc.

Phân biệt rõ hình học quan sát được, hình học suy luận và hình học không đủ thông tin để xác định.

### O2 — Visual Fidelity

Mô hình phải tương đồng về mặt thị giác với công trình ngoài đời.

Bao gồm hình dáng, vật liệu, màu sắc, bố cục, texture và những đặc điểm nhận dạng quan trọng.

Ưu tiên tính chính xác trước khi stylize.

Không được làm mô hình đẹp hơn bằng cách tự ý thay đổi cấu trúc thực tế.

### O3 — Procedural Code Quality

Kết quả phải là procedural generator thực sự, không phải mesh cố định được viết dưới dạng dữ liệu.

Code cần:

- Có khả năng thực thi độc lập.
- Sinh ra Three.js geometry đúng cấu trúc.
- Có tổ chức rõ ràng, dễ chỉnh sửa.
- Hỗ trợ tham số hóa khi phù hợp.
- Tránh geometry trùng lặp, lỗi topology và các chi tiết vô nghĩa.
- Hỗ trợ thay đổi material/style mà không phải xây dựng lại toàn bộ logic.

### O4 — Resource Efficiency

Tối ưu tổng chi phí tạo ra một mô hình đạt chất lượng yêu cầu, không chỉ chi phí cho một lần gọi model.

Cần đo lường và tối ưu:

- Input/output tokens.
- API inference cost.
- Số lần gọi model.
- Số vòng refinement.
- Thời gian phân tích ảnh.
- Thời gian sinh và sửa code.
- Thời gian compile/render.
- CPU/GPU/RAM/VRAM.
- Tổng thời gian và chi phí trên mỗi công trình.

### O5 — Scalability

Workflow phải có khả năng xử lý độc lập nhiều tòa nhà, tái sử dụng kết quả đã tạo và mở rộng thành hệ thống xây dựng một khu vực đô thị.

Ở giai đoạn nghiên cứu ban đầu, ưu tiên chứng minh chất lượng trên từng tòa nhà trước khi mở rộng quy mô.

---

## 3. Architectural Requirements

### Required Architecture

**LangGraph → LLM APIs → Self-hosted img2threejs Runtime → Three.js Renderer → Evaluator → Refinement**

LangGraph giữ vai trò điều phối workflow, quản lý state và quyết định những bước tiếp theo.

Các LLM được gọi trực tiếp qua API, không cần sử dụng Codex CLI, Claude Code CLI hoặc các phiên coding agent bên ngoài trong runtime.

Self-hosted runtime chịu trách nhiệm đọc skill, quản lý script, tạo và sửa file, thực thi code, render và thu thập kết quả.

### Architectural Constraints

1. Không sử dụng Codex CLI hoặc Claude Code CLI như một thành phần runtime để sinh tòa nhà.
2. Không bắt buộc sử dụng độc quyền một model provider.
3. Cho phép chọn model khác nhau cho từng nhiệm vụ.
4. Cho phép thay đổi prompt, model, công cụ và chiến lược điều phối mà không cần viết lại toàn bộ workflow.
5. Không đưa toàn bộ mã nguồn, tài liệu skill hoặc lịch sử hội thoại vào mọi API call nếu không cần thiết.
6. Không sử dụng LLM cho những công việc đã có giải pháp xác định bằng code.
7. Phải có state persistence, caching, retry, tracing và giới hạn ngân sách.
8. Mỗi reconstruction job có workspace độc lập.
9. Thực thi code LLM sinh ra trong sandbox giới hạn quyền, tài nguyên và thời gian.
10. Không cho phép mã được sinh ra truy cập credentials hoặc sửa đổi code dùng chung của hệ thống.

**Quan trọng:** Không được thay thế mục tiêu chính bằng một parametric template engine cố định. Bài toán nghiên cứu là khả năng AI tự tạo hoặc cải thiện procedural code từ ảnh.

Có thể thử generator reuse, code templates và parameter-only adaptation như các chiến lược tối ưu, nhưng phải chứng minh chúng không làm giảm chất lượng so với phương án sinh code riêng khi cần thiết.

---

## 4. Research and Integrate img2threejs

Repository chính:

https://github.com/img2threejs/img2threejs

### R1 — Repository Investigation

Trước khi xây dựng workflow, phải nghiên cứu source code và tài liệu thực tế của img2threejs.

Tập trung phân tích:

- `SKILL.md`
- `docs/ARCHITECTURE.md`
- `grimoire/`
- `forge/`
- State management.
- ObjectSculptSpec.
- Các geometry validation gates.
- Các staged generation passes.
- Các render/evaluation requirements.
- Cơ chế refinement.
- Plugin/domain capability và những hạn chế hiện tại.

Xác định rõ chức năng nào:

1. Có thể sử dụng trực tiếp.
2. Có thể tái sử dụng sau khi viết adapter.
3. Phụ thuộc vào công cụ của agent host.
4. Chưa được triển khai và cần phát triển mới.
5. Không phù hợp với bài toán kiến trúc.

Không giả định các lệnh, script hoặc chức năng có tồn tại nếu chưa kiểm tra source code.

### R2 — Skill Integration

Triển khai cơ chế tương đương Agent Skills trong LangGraph.

Yêu cầu:

- Đọc và hiểu `SKILL.md`.
- Nạp hướng dẫn bổ sung theo từng giai đoạn khi cần.
- Tái sử dụng các script kiểm tra có sẵn.
- Bảo toàn các validation requirements quan trọng.
- Cung cấp các tool cần thiết cho LLM.
- Hỗ trợ version pinning.
- Đảm bảo state giữa LangGraph và img2threejs nhất quán.

Ưu tiên progressive disclosure để hạn chế token context.

Không chỉ sao chép toàn bộ SKILL.md vào system prompt rồi coi như đã tích hợp hoàn chỉnh.

### R3 — Baseline Compatibility

Thiết lập một workflow thử nghiệm bám sát các bước gốc của img2threejs.

Sử dụng kết quả này làm baseline trước khi tối ưu.

Nếu có thành phần không thể chạy độc lập ngoài Codex/Claude Code, phải xác định nguyên nhân và xây giải pháp thay thế tương đương.

Không được bỏ qua quality gates chỉ để pipeline chạy thành công.

---

## 5. Input Data Requirements

### Primary Inputs

Một reconstruction job có thể nhận:

- Một hoặc nhiều ảnh tham chiếu của tòa nhà.
- Thông tin góc chụp nếu có.
- Mặt bằng footprint.
- Chiều cao, chiều rộng, chiều sâu.
- Số tầng nếu biết.
- Thông tin vật liệu.
- Target style.
- Chất lượng đầu ra mong muốn.
- Resource budget.

Các thông tin không bắt buộc phải đầy đủ.

Workflow phải hỗ trợ:

**Scenario A — Single Image**

Chỉ có một ảnh mặt tiền hoặc ảnh phối cảnh.

**Scenario B — Multi-View Images**

Có ảnh từ nhiều phía.

**Scenario C — Image + Structural Metadata**

Có ảnh kèm footprint, kích thước hoặc dữ liệu GIS.

**Scenario D — Partial/Noisy References**

Ảnh bị che khuất, thiếu góc nhìn, độ phân giải thấp hoặc chứa các tòa nhà khác.

Cần đánh giá riêng hiệu quả của workflow theo từng scenario.

### Input Priority

Nếu project có ảnh tham chiếu thực tế đã được cung cấp, phải ưu tiên sử dụng chúng.

Không được thay bằng hình ảnh ngẫu nhiên, synthetic building hoặc mô hình tưởng tượng rồi tuyên bố đã giải quyết được bài toán thực tế.

Synthetic references chỉ được sử dụng cho những thí nghiệm có mục đích rõ ràng, đặc biệt là khi cần ground-truth 3D.

---

## 6. Proposed Agentic Workflow

Cần nghiên cứu và thử nghiệm workflow gồm các thành phần sau.

Đây là kiến trúc khởi đầu, không phải thiết kế bất biến.

### Stage 1 — Reference Understanding

Vision model phân tích ảnh gốc.

Nhiệm vụ:

- Nhận diện cấu trúc tổng thể.
- Phân rã các thành phần hình học.
- Xác định quan hệ không gian.
- Phân tích các quy luật lặp.
- Ước lượng tỷ lệ, bố cục.
- Nhận diện chi tiết quan trọng.
- Xác định các vùng bất định.
- Phân biệt dữ liệu quan sát và suy luận.

Output là structured representation phù hợp cho code generation.

Không được chỉ tạo mô tả ngôn ngữ tự do nếu dữ liệu có thể được biểu diễn bằng cấu trúc rõ ràng hơn.

### Stage 2 — Structural Specification

Chuyển phân tích thành ObjectSculptSpec hoặc một schema mở rộng tương thích.

Yêu cầu biểu diễn:

- Component hierarchy.
- Geometric constraints.
- Spatial relationships.
- Repetition systems.
- Materials.
- Camera/reference alignment information.
- Confidence/uncertainty.
- Provenance của từng đặc điểm quan trọng.

Phải thử nghiệm độ chi tiết của specification.

Một spec quá đơn giản có thể làm mất thông tin; spec quá phức tạp có thể tăng token và dẫn đến code generation kém ổn định.

### Stage 3 — Procedural Code Generation

Coding/reasoning model nhận specification và ảnh tham chiếu cần thiết.

Sinh mã nguồn Three.js/TypeScript để tái tạo công trình.

Yêu cầu thử nghiệm các chiến lược:

- One-shot full code generation.
- Staged geometry generation.
- Hierarchical component generation.
- Module-based generation.
- Incremental code refinement.
- Parameter correction.
- Targeted component regeneration.

Phải đánh giá chiến lược nào đạt chất lượng tốt nhất với tổng chi phí thấp nhất.

Ưu tiên sửa đúng module thay vì sinh lại toàn bộ code khi chỉ có một thành phần sai.

### Stage 4 — Execution and Rendering

Runtime thực thi generator trong sandbox.

Yêu cầu:

- TypeScript validation/compilation.
- Kiểm tra geometry.
- Kiểm tra scene graph.
- Phát hiện lỗi thực thi.
- Render từ các camera chuẩn hóa.
- Xuất screenshot.
- Ghi nhận thời gian và tài nguyên.

Cần tạo ảnh render của các góc:

- Front.
- Back.
- Left.
- Right.
- Three-quarter/isometric.

Với góc có ảnh tham chiếu, cần cố gắng camera matching để đối chiếu công bằng.

Với góc không có ảnh tham chiếu, chỉ đánh giá tính hợp lý và nhất quán, không được coi đó là bằng chứng mô hình khớp với thực tế.

### Stage 5 — Automatic Evaluation

Kết hợp deterministic evaluation, computer vision và multimodal model.

Evaluator phải xác định:

- Kết quả có chạy được không?
- Hình học có hợp lệ không?
- Công trình có giống ảnh tham chiếu không?
- Những phần nào đang sai?
- Mức độ nghiêm trọng?
- Sai do code, spec, camera hay material?
- Cách sửa nào có khả năng cải thiện kết quả tốt nhất?

Output cần là actionable feedback, không chỉ là một số điểm tổng quát.

### Stage 6 — Targeted Refinement

Refinement agent nhận:

- Specification hiện tại.
- Relevant source code.
- Ảnh gốc.
- Ảnh render.
- Evaluation feedback.
- Lịch sử sửa đổi liên quan.

Agent phải chọn sửa đúng thành phần gây lỗi.

Ví dụ:

Sai số tầng → sửa floor structure.

Sai ban công → sửa balcony module.

Sai camera → sửa camera alignment, không sửa geometry để khớp một góc nhìn sai.

Sai material → sửa material/shader.

Sai khối hình học → sửa geometry.

Không được tạo lại toàn bộ công trình một cách không cần thiết.

### Stage 7 — Final Validation and Export

Chỉ chấp nhận model khi vượt qua các kiểm tra đã định nghĩa.

Output phải có procedural code, specification, renders, evaluation report và model export nếu được hỗ trợ.

---

## 7. Visual Evaluation and Metrics

Không đánh giá chất lượng chỉ bằng cảm nhận chủ quan của Vision LLM.

Cần xây dựng bộ đánh giá đa chiều.

### 7.1 Geometry Metrics

Nghiên cứu sử dụng:

- Silhouette IoU sau khi căn chỉnh camera.
- Shape/bounding-box ratio error.
- Building proportion error.
- Floor count accuracy.
- Window count accuracy.
- Window layout alignment.
- Balcony geometry accuracy.
- Landmark/keypoint alignment.
- Mesh validity.
- Geometric consistency giữa các góc nhìn.

Với dữ liệu synthetic có ground-truth 3D, cân nhắc thêm Chamfer Distance, voxel IoU hoặc các metric 3D phù hợp.

Không áp dụng các metric cần ground truth 3D cho dữ liệu thực tế không có ground truth.

### 7.2 Appearance Metrics

Thử nghiệm các metric phù hợp như:

- LPIPS.
- SSIM.
- Feature similarity.
- Color/material similarity.
- Region-level comparison.
- Multimodal semantic evaluation.

Chỉ dùng image-level metrics khi camera, crop và các yếu tố ảnh đã được căn chỉnh phù hợp.

Không sử dụng CLIP similarity hoặc một điểm VLM tổng quát làm tiêu chí duy nhất.

### 7.3 Structural Quality

Đánh giá bằng rubric có cấu trúc:

- Main mass fidelity.
- Facade layout.
- Repeated architectural elements.
- Roof structure.
- Distinctive details.
- Material consistency.

Các đặc điểm quan trọng phải được đánh giá riêng.

Không cho phép điểm tổng cao che giấu một lỗi cấu trúc nghiêm trọng.

### 7.4 Code Quality

Đo:

- Compilation success rate.
- Runtime success rate.
- Geometry validation pass rate.
- Code complexity.
- Khả năng chỉnh sửa.
- Tính ổn định qua các lần chạy.
- Khả năng tái sử dụng.
- Render performance.

### 7.5 Resource Metrics

Ghi lại:

- Total tokens.
- API calls.
- Cost per run.
- Cost per successful model.
- Runtime per stage.
- Total reconstruction time.
- Correction iterations.
- Peak memory.
- Rendering time.

Phân biệt chi phí thử nghiệm thất bại và chi phí tạo ra sản phẩm đạt yêu cầu.

### 7.6 Evaluation Reliability

Phải kiểm tra độ tin cậy của evaluator.

Nếu cùng một model vừa sinh code vừa tự chấm, có thể xuất hiện thiên lệch.

Thử nghiệm đánh giá bằng model độc lập và đối chiếu với human review trên một tập mẫu.

Hiệu chỉnh ngưỡng chất lượng dựa trên dữ liệu thực nghiệm.

Không tự đặt một điểm số tùy ý rồi tuyên bố đã đạt chất lượng.

---

## 8. Benchmark Dataset and Experimental Protocol

### Dataset Design

Bắt đầu với một tập nhỏ nhưng đa dạng.

Đề xuất:

**Phase A — Smoke Tests**

1–3 công trình để kiểm tra pipeline thực sự chạy đầu-cuối.

**Phase B — Development Benchmark**

Khoảng 8–12 công trình gồm:

- Nhà phố đơn giản.
- Nhà phố nhiều tầng có ban công.
- Chung cư phổ thông.
- Chung cư có nhiều khối nhô ra.
- Văn phòng nhiều kính.
- Công trình có mái phức tạp.
- Tòa nhà bất đối xứng.
- Công trình có nhiều chi tiết đặc trưng.

**Phase C — Held-Out Evaluation**

Một tập công trình chưa sử dụng để tối ưu prompt hoặc cấu hình.

**Phase D — City-Block Pilot**

Một khu vực nhỏ có nhiều công trình khác nhau để đo khả năng mở rộng.

Đây là quy mô thử nghiệm đề xuất, có thể điều chỉnh theo dữ liệu và ngân sách thực tế.

### Experimental Rules

1. Mỗi experiment phải có ID và cấu hình cụ thể.
2. Dùng cùng tập dữ liệu khi so sánh các workflow.
3. Giữ nguyên các biến không thuộc thí nghiệm.
4. Lưu kết quả và nguồn dữ liệu.
5. Không chọn ảnh tốt nhất rồi bỏ qua các trường hợp thất bại.
6. Khi có thể, chạy lặp để đánh giá độ ổn định.
7. Phân biệt development benchmark và held-out benchmark.
8. Không dùng kết quả held-out để tiếp tục tối ưu không kiểm soát.

Mọi kết luận về hiệu quả phải dựa trên dữ liệu đo được.

---

## 9. Required Experiments

Codex cần chủ động nghiên cứu và thiết kế thí nghiệm để trả lời các câu hỏi sau.

### E1 — Skill Integration Strategy

So sánh:

- Tích hợp các hướng dẫn từ img2threejs vào LangGraph.
- Tái sử dụng trực tiếp các forge scripts.
- Xây adapter có state management riêng nhưng giữ quality gates.
- Các phương án hybrid phù hợp khác.

Mục tiêu: xác định cách tận dụng repo tối đa mà không phụ thuộc vào Codex CLI.

### E2 — Agent Architecture

Thử:

- Một multimodal agent thực hiện nhiều nhiệm vụ.
- Tách Vision và Code Agent.
- Tách thêm Evaluator Agent.
- Chỉ gọi agent chuyên biệt theo nhu cầu.

Đánh giá lợi ích thực tế của việc chia agent, thay vì mặc định nhiều agent là tốt hơn.

### E3 — Model Selection

So sánh những model API có khả năng multimodal/reasoning/coding phù hợp và thực sự truy cập được.

Đánh giá:

- Vision accuracy.
- Structural reasoning.
- Procedural coding quality.
- Correction effectiveness.
- Latency.
- Token usage.
- Price.

Không mặc định model đắt nhất là tốt nhất.

Nghiên cứu việc dùng model nhẹ ở những bước đơn giản và chỉ sử dụng model mạnh khi thật sự cần thiết.

### E4 — Generation Strategy

So sánh:

- Direct image-to-code.
- Image-to-spec-to-code.
- Staged code generation.
- Component-level generation.
- Template-assisted generation.

Đảm bảo kết quả cuối vẫn là procedural code có khả năng thể hiện kiến trúc công trình.

### E5 — Refinement Strategy

So sánh:

- Full regeneration.
- Full-file correction.
- Diff-based correction.
- Component-level correction.
- Spec refinement.
- Geometry parameter refinement.

Đo chất lượng cải thiện trên mỗi lần gọi LLM và trên mỗi đơn vị chi phí.

### E6 — Visual Feedback Strategy

Thử nghiệm:

- Reference/render comparison sheet.
- Cropped region feedback.
- Landmark-based feedback.
- Geometry-aware feedback.
- Multi-view evaluation.
- Combined deterministic + VLM evaluation.

Đánh giá khả năng chỉ ra đúng nguyên nhân lỗi, không chỉ khả năng mô tả lỗi.

### E7 — Geometry and Representation

Nghiên cứu các cách tạo geometry có thể biểu diễn tốt kiến trúc:

- Three.js primitives.
- Extruded geometry.
- Custom BufferGeometry.
- Curves and parametric surfaces.
- Modular procedural components.
- Architectural grammar / facade rules.

Chỉ tích hợp phương pháp mới nếu mang lại cải thiện được kiểm chứng.

### E8 — Context and Token Optimization

Thử:

- Progressive skill loading.
- Compressed structured feedback.
- Component-scoped context.
- Prompt caching.
- Reusing unchanged artifacts.
- Summarized reconstruction history.
- Selective image crops.
- Conditional use of expensive models.

Đo số token tiết kiệm được và tác động lên chất lượng.

### E9 — Resource Optimization

Thử các chiến lược:

- Concurrent independent jobs.
- Browser/render worker pooling.
- Image resizing và crop theo nhiệm vụ.
- Local deterministic preprocessing.
- Conditional rendering.
- Caching.
- Early termination.
- Reuse of successful code/components.

Tối ưu theo tổng chi phí tạo ra công trình đạt chất lượng, không chỉ giảm thời gian của một bước riêng lẻ.

---

## 10. Continuous Workflow Optimization

Đây là phần quan trọng nhất của dự án.

Không dừng ở việc xây một workflow chạy được.

Sau khi có baseline, Codex phải thực hiện chu trình nghiên cứu thực nghiệm:

**Baseline → Evaluate → Diagnose → Hypothesize → Modify → Experiment → Compare → Retain/Revert → Repeat**

### Step 1 — Establish Baseline

Triển khai workflow cơ bản hoạt động từ đầu đến cuối.

Chạy trên dữ liệu thật.

Lưu toàn bộ metrics và artifacts.

### Step 2 — Identify Bottlenecks

Phân loại nguyên nhân làm giảm hiệu quả:

- Vision hiểu sai.
- Specification không đủ chi tiết.
- Code generation thất bại.
- Geometry sai.
- Camera không khớp.
- Material không khớp.
- Evaluation thiếu chính xác.
- Refinement không cải thiện kết quả.
- Token context quá lớn.
- Render quá chậm.
- API cost quá cao.

Xác định bottleneck quan trọng nhất dựa trên tác động đo được.

### Step 3 — Form a Hypothesis

Ví dụ:

> Chia code generation theo component có thể tăng structural accuracy và giảm chi phí refinement so với việc sinh một file lớn.

Mỗi thay đổi phải có giả thuyết và mục tiêu đo lường.

### Step 4 — Execute Controlled Experiment

Chỉ thay đổi những thành phần cần thiết để kiểm tra giả thuyết.

Chạy trên benchmark phù hợp.

### Step 5 — Compare

So sánh với baseline và phiên bản tốt nhất hiện tại.

Phải đánh giá đồng thời quality, cost, latency và reliability.

### Step 6 — Accept or Reject

Chỉ giữ thay đổi nếu nó:

- Cải thiện rõ ràng một hoặc nhiều mục tiêu.
- Không gây suy giảm không chấp nhận được ở các chỉ tiêu quan trọng.
- Có kết quả ổn định.
- Không phá vỡ các regression tests.

Nếu phương án mới thất bại, quay lại phiên bản trước đó.

### Step 7 — Repeat

Tiếp tục nghiên cứu bottleneck tiếp theo.

Không giới hạn số thí nghiệm bằng một con số tùy ý cho toàn dự án, nhưng mỗi reconstruction run và mỗi đợt nghiên cứu phải có resource/time budget hữu hạn.

Khi có dấu hiệu plateau, cần đánh giá liệu một hướng nghiên cứu khác có triển vọng hơn hay không.

Không lặp vô hạn với cùng prompt và cùng lỗi.

---

## 11. Optimization Objective and Selection

Không tối ưu bằng một tiêu chí duy nhất.

### Hard Constraints

Các phương án phải thỏa mãn:

- Model compile và chạy được.
- Geometry hợp lệ.
- Không có lỗi cấu trúc nghiêm trọng chưa được xử lý.
- Không vi phạm giới hạn tài nguyên.
- Không phát sinh hành vi thực thi không an toàn.

### Primary Optimization Target

**Tối đa hóa fidelity của công trình với nguồn dữ liệu quan sát được.**

Trong số các phương án đạt chất lượng tương đương, ưu tiên:

1. Chi phí thấp hơn.
2. Thời gian xử lý ngắn hơn.
3. Tỷ lệ thành công cao hơn.
4. Tính ổn định và khả năng mở rộng tốt hơn.

Theo dõi Pareto frontier giữa quality, cost và latency.

Không loại bỏ một workflow có chất lượng vượt trội chỉ vì nó đắt hơn đôi chút; ngược lại, cũng không chọn workflow rẻ nhất nếu chất lượng không đáp ứng mục tiêu.

Ngưỡng chấp nhận cuối cùng phải được thiết lập dựa trên benchmark và yêu cầu người dùng, không tự tuyên bố một cấu hình là tối ưu khi chưa có bằng chứng.

---

## 12. Architecture for City-Level Scaling

Sau khi chứng minh được chất lượng với một tòa nhà, mở rộng thành nhiều building jobs độc lập.

### Requirements

- Mỗi công trình có ID riêng.
- Lưu ảnh, metadata và trạng thái.
- Workflow có thể chạy song song.
- Có resource-aware scheduling.
- Có caching và resume.
- Có retry theo loại lỗi.
- Có khả năng ngừng job khi vượt ngân sách.
- Có thống kê theo công trình và toàn batch.
- Có thể tiếp tục job thất bại mà không phải chạy lại từ đầu.

### City Assembly

Xây bước ghép các mô hình vào thành phố:

- Chuyển footprint/tọa độ GIS sang hệ tọa độ dựng hình phù hợp.
- Bảo toàn tỷ lệ mét.
- Định vị và định hướng model.
- Kiểm tra ground alignment.
- Tránh chồng lấn sai giữa các công trình.
- Xuất định dạng phù hợp với 3D city viewer.
- Nghiên cứu LOD và streaming.

Ưu tiên tương thích với Three.js/CesiumJS và các định dạng như GLB/3D Tiles khi phù hợp.

Không cần xây đầy đủ hệ thống city streaming trong giai đoạn đầu.

Mục tiêu ban đầu là chứng minh rằng các output từ reconstruction workflow có thể được ghép vào cùng một hệ tọa độ.

---

## 13. Failure Handling and Robustness

Workflow phải phân loại và xử lý tối thiểu các trường hợp:

- Ảnh không đủ rõ.
- Không xác định được cấu trúc.
- Spec không hợp lệ.
- API timeout/rate limit.
- LLM trả output không đúng schema.
- Code không compile.
- Code chạy nhưng không render được.
- Geometry bị sai hoặc mất thành phần.
- Evaluator không thể đánh giá.
- Refinement lặp lại cùng một lỗi.
- Chất lượng suy giảm sau khi sửa.
- Chi phí vượt budget.

Mỗi lỗi phải có failure code, log, evidence và recovery strategy.

Không được tự đánh dấu thành công chỉ vì code chạy được.

Nếu thiếu thông tin để tái tạo chính xác, phải trả về trạng thái `partial` hoặc `insufficient_evidence` cùng giải thích rõ ràng.

---

## 14. Experiment Tracking and Reproducibility

Mỗi experiment phải lưu:

- Experiment ID.
- Building ID.
- Source image references.
- Model/provider/version.
- Prompt version.
- Skill repository commit/version.
- LangGraph workflow version.
- Runtime configuration.
- Generated specification.
- Generated source code.
- All render artifacts.
- Evaluation results.
- API usage.
- Total cost.
- Latency.
- Error reports.
- Refinement history.

Kết quả phải có khả năng tái tạo trong giới hạn tính không xác định của LLM API.

Cần có một experiment dashboard/report để so sánh trực tiếp các phương án.

Tối thiểu phải có:

- Bảng kết quả theo từng tòa nhà.
- Bảng so sánh các workflow.
- Biểu đồ quality vs cost.
- Biểu đồ quality vs runtime.
- Tỷ lệ thành công.
- Phân tích lỗi.
- Hình ảnh trước và sau refinement.

---

## 15. Visual Deliverables

Đây là yêu cầu bắt buộc, không chỉ cung cấp code hoặc logs.

Với mỗi công trình cần xuất:

**A. Reference**

Ảnh gốc đã sử dụng.

**B. Final Render**

- Front view.
- Back view.
- Left view.
- Right view.
- Isometric view.

**C. Comparison**

Ảnh reference và render được đặt cạnh nhau.

Khi có camera matching, lưu thêm overlay và difference visualization.

**D. Iterative Improvements**

Lưu kết quả của baseline và những iteration quan trọng để thấy sự thay đổi.

**E. Evaluation Report**

Nêu rõ:

- Những phần khớp.
- Những phần chưa khớp.
- Những phần chỉ được suy luận.
- Điểm chất lượng.
- Chi phí.
- Thời gian.
- Lý do dừng refinement.

**F. Procedural Source**

Cung cấp code generator có thể chạy lại và chỉnh sửa.

Không được chỉ cung cấp screenshot hoặc mesh mà thiếu code.

---

## 16. Required Implementation Phases

### Phase 1 — Research & Feasibility

- Nghiên cứu img2threejs.
- Kiểm tra các giới hạn kỹ thuật.
- Nghiên cứu phương án LangGraph + LLM APIs.
- Xác định thành phần có thể tái sử dụng.
- Viết báo cáo lựa chọn kiến trúc.

**Exit condition:** Có thiết kế khả thi, chỉ rõ phần dùng lại và phần phải triển khai.

### Phase 2 — Working Baseline

- Tích hợp skill runtime.
- Xây workflow end-to-end.
- Chạy được với ít nhất một ảnh thực tế.
- Sinh procedural code.
- Render và kiểm tra được kết quả.

**Exit condition:** Có ít nhất một reconstruction run hoàn chỉnh với đầy đủ artifacts, không chỉ mock.

### Phase 3 — Evaluation System

- Xây metrics.
- Xây structured visual feedback.
- Kiểm tra evaluation reliability.
- Tạo benchmark.

**Exit condition:** Có thể xác định và đo được các sai lệch quan trọng.

### Phase 4 — Iterative Optimization

- Thử nghiệm các kiến trúc agent.
- Thử nghiệm các model.
- Thử nghiệm prompt và specification.
- Thử nghiệm code generation strategies.
- Thử nghiệm refinement.
- Tối ưu context và resource usage.

**Exit condition:** Có bằng chứng phương án được chọn vượt baseline theo các tiêu chí đã thống nhất.

### Phase 5 — Validation

- Kiểm tra trên held-out buildings.
- Chạy regression tests.
- Kiểm tra độ ổn định.
- Đánh giá chi phí và thời gian.
- Phân tích các trường hợp thất bại.

**Exit condition:** Chất lượng được chứng minh trên nhiều loại công trình, không chỉ một demo đẹp.

### Phase 6 — City Pilot

- Chạy batch nhiều công trình.
- Kiểm tra georeferencing.
- Ghép các model vào một scene.
- Đánh giá scalability.
- Xác định bottleneck tiếp theo.

**Exit condition:** Có một khu vực 3D thử nghiệm sử dụng các model do workflow sinh ra.

---

## 17. Research Deliverables

Khi kết thúc một đợt nghiên cứu, phải cung cấp:

1. **Research Findings** — Các phương pháp đã tìm hiểu, điểm mạnh, điểm yếu và bằng chứng.
2. **Architecture Decision Record** — Lý do chọn workflow hiện tại.
3. **Working Implementation** — Source code có thể chạy.
4. **Benchmark Dataset** — Các trường hợp kiểm thử có nguồn gốc rõ ràng.
5. **Experiment Results** — Kết quả đo từ những thử nghiệm thực sự.
6. **Visual Comparisons** — Ảnh gốc, ảnh render, kết quả qua các vòng cải tiến.
7. **Optimization Report** — Tác động của từng thay đổi lên chất lượng, chi phí và tốc độ.
8. **Known Limitations** — Những vấn đề chưa giải quyết được.
9. **Final Recommended Workflow** — Phương án tốt nhất tìm được, kèm cấu hình và bằng chứng.
10. **Next Research Opportunities** — Những hướng có tiềm năng nhưng chưa đủ nguồn lực xác minh.

Không được tuyên bố một phương pháp là tốt nhất chỉ dựa trên lý thuyết hoặc ví dụ từ tài liệu.

---

## 18. Instructions for the Implementing Codex Agent

Bạn đóng vai trò **AI Research Engineer + Computer Graphics Engineer + Agentic Systems Architect**.

Nhiệm vụ không phải là viết một bản demo càng nhanh càng tốt.

Nhiệm vụ là nghiên cứu, triển khai, kiểm tra và tối ưu một hệ thống thực tế để tái tạo hình học 3D từ ảnh bằng procedural code.

### Working Principles

**Research before implementation**

Nghiên cứu trực tiếp mã nguồn img2threejs và các giải pháp hiện có trước khi lựa chọn kỹ thuật.

**Evidence over assumptions**

Không giả định một model, framework hoặc workflow vượt trội nếu chưa có benchmark.

**Build and test continuously**

Sau mỗi thay đổi quan trọng, chạy kiểm tra và quan sát kết quả thực tế.

**Preserve quality**

Không đánh đổi hình học chính xác để tạo ra ảnh trông đẹp mắt hơn.

**Optimize the complete system**

Không tối ưu một node riêng lẻ nhưng làm tăng tổng chi phí hoặc giảm chất lượng toàn pipeline.

**Avoid unnecessary complexity**

Không tạo quá nhiều agent, tool hay abstraction nếu không có lợi ích được chứng minh.

**Use real inputs**

Ưu tiên ảnh thực tế có sẵn. Với ảnh chưa đủ thông tin, phải mô tả giới hạn tái tạo.

**Keep experiments reproducible**

Lưu source code, tham số, hình ảnh và kết quả cho từng experiment.

**Make progress independently**

Chủ động tìm phương án, chạy thử, phát hiện vấn đề và cải tiến dựa trên bằng chứng. Không cần hỏi xác nhận cho mọi quyết định kỹ thuật nhỏ.

### Final Engineering Goal

Tìm ra một workflow có khả năng:

**Reference Images → Structural Understanding → Procedural Code → Rendering → Evaluation → Self-Correction → High-Fidelity 3D**

Workflow phải có thể được triển khai hoàn toàn bằng LangGraph, LLM APIs và self-hosted tools.

Không phụ thuộc vào Codex CLI trong runtime.

Việc chọn model, agent architecture, rendering strategy, evaluation method và refinement strategy phải xuất phát từ kết quả thực nghiệm.

### Definition of Success

Dự án chỉ được xem là có kết quả nghiên cứu đáng tin cậy khi:

- Workflow thực sự chạy end-to-end.
- Sinh được procedural code hợp lệ.
- Render được mô hình 3D thực tế.
- Có so sánh trực tiếp với ảnh reference.
- Có cơ chế refinement hoạt động.
- Có metrics và experiment history.
- Có bằng chứng cải tiến so với baseline.
- Có đánh giá chi phí và thời gian.
- Có phân tích thất bại và giới hạn.
- Có thể áp dụng cho nhiều công trình khác nhau.

Nếu chưa đạt được chất lượng mong muốn, phải chỉ rõ bottleneck, thử phương án thay thế trong ngân sách nghiên cứu và ghi nhận kết quả.

Không tuyên bố thành công khi chỉ mới hoàn thiện kiến trúc hoặc source code.

**Research outcome phải là một workflow được chứng minh bằng thực nghiệm, không chỉ là một workflow được đề xuất trên giấy.**