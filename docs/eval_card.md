# Eval card — LogiX-VN refund agent

Card này đi kèm mỗi báo cáo và được dùng lại ở Day 10.

- **Run ID / Eval set SHA:** sinh lại bằng `python -m lab9.eval --shape swarm --out reports/baseline_v1.json`
- **Phiên bản:** code (commit sau overlay) · eval set v1 · metric_spec 1.0 · seeds 11/22/33/44/55
- **Eval set:** v1, 14 item × 5 seed, nguồn lab8_public; nhãn: labels_v1.json
- **Metric & ngưỡng:** safety max 0; pass_rate min 0.85; refund_amount_correct min 0.95.
- **Kết quả baseline vs PR:** dùng `lab9.gate`; capability có paired bootstrap CI trên từng item.
- **Judge:** tone_ok κ=0.757, P=0.857, R=0.800; helpful bị loại vì không đạt floor.
- **Trace case:** link `docs/trace_case.md`, bước sai đầu tiên, regression test
- **Gate owner:** người mở PR xử lý metric bị block và bổ sung regression test.
- **Phạm vi pilot:** MockLLM, public claims và 5 seed cố định.
- **Giới hạn / bằng chứng còn thiếu:** MockLLM, 14 item, judge replay; không đo trên người dùng thật
- **Khi nào tăng eval-set version:** khi thêm adversarial pack hoặc thay đổi nhãn/provenance; không sửa report thủ công.
