# Decision record

Điền sau dấu `:` trên cùng dòng, không xóa nhãn. Giảng viên và `python -m lab8.check_submission` (chạy trong `src/`) đọc các dòng này bằng máy. Không đổi tên hay dời file này khỏi `report/team/`.

- Shape chọn: workflow
- Commit hash: be22ff0
- Run id dẫn chứng: R-workflow-C-001-s11 (đối chiếu cùng claim/seed: R-orchestrator-C-001-s11)
- Pass rate / pass^5 / seed min-max / variance: 1.000 / 1.000 / 1.000–1.000 / 0.000000 (70 trial public)
- Cost per success (mô phỏng, VND): 27.86
- Crash safety: 20/20 (src/reports/crash.json)
- Secret leak / approval bypass: 0 / 0 trial lỗi trên benchmark public

## Vì sao chọn workflow

Benchmark public được chạy lại trên cùng 14 claim, năm seed `11, 22, 33, 44, 55`, cùng bảng giá và evaluator. Workflow đạt pass rate/pass^5 `1.000/1.000`, bằng single và orchestrator; có cost/success thấp nhất (`27.86` VND mô phỏng), mean steps thấp nhất (`1.00`) và variance `0`. Theo mục tiêu chọn kiến trúc ít tự chủ nhất mà vẫn làm được việc, workflow là lựa chọn phù hợp với bằng chứng public hiện có.

## Đối chiếu multi-agent

Trên public corpus, chuyển workflow sang single hoặc orchestrator không tăng pass rate. Cost/success lần lượt là `48.19` và `46.43` VND mô phỏng; mean steps là `2.64` và `4.71`. Vì vậy nhóm chưa thấy lợi ích đủ để trả thêm chi phí cho hai shape này trong corpus hiện tại. Kết luận chỉ áp dụng cho benchmark này và sẽ được xem lại nếu dữ liệu ẩn có nhãn hoặc dữ liệu thực tế cho thấy workflow không đạt chất lượng cần thiết.

## Bằng chứng và hidden self-check

Benchmark public có `280` trial tổng cộng (70 mỗi shape). `workflow`, `single` và `orchestrator` đều đạt `70/70`; swarm đạt `69/70`, với một trial sai nhãn ở seed 55 như điểm yếu tham chiếu của starter. Không có trial public nào bị báo lỗi approval hoặc trace leak. Crash suite chạy lại đạt `20/20`.

Nhóm đã chạy self-check trên `src/student_drop/`: mỗi shape nhóm thực hiện `200` trial (40 claim × 5 seed), có `0` trial lỗi và `0` leak suspect. File là `src/reports/hidden_selfcheck.json`. Vì bộ này không có nhãn, self-check không tính pass rate, approval bypass theo nhãn hay điểm hidden; kết quả chấm chính thức vẫn thuộc grader của giảng viên.

Run ID hidden mẫu: `R-workflow-C-H01-s11`. Run ID public nêu ở trên có trong `src/reports/benchmark.json`.

## Trace và giới hạn

Trace giữ các sự kiện cần cho grader như tra claim/order, quote, handoff/investigation và kết quả host; không ghi `parent_secret`, raw headers, ticket nguyên văn, principal ID, số điện thoại, địa chỉ, ghi chú nội bộ hay tên hàng. MockLLM là mô phỏng xác định, chi phí là giá mô phỏng và latency là `unavailable`; kết quả không đại diện cho model hay dữ liệu sản xuất.
