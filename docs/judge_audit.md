# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5`

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | Đạt | dùng |
| helpful | 100 | < 0.6 | < 0.8 | < 0.7 | Không đạt | loại |

## ≥5 case audit thủ công
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú |
|---|---|---|---|---|---|
| 1 | tone_ok / FAIL | FAIL | FAIL | cả hai | Nhãn nhất quán |
| 2 | tone_ok / FAIL | PASS | FAIL | người | Judge bỏ sót lỗi |
| 3 | tone_ok / PASS | FAIL | PASS | người | Judge báo nhầm |
| 4 | tone_ok / FAIL | FAIL | FAIL | cả hai | Có bằng chứng lỗi |
| 5 | tone_ok / PASS | PASS | PASS | cả hai | Câu trả lời đạt |

## Kết luận
- `helpful` bị loại vì không đạt đồng thời κ, precision và recall trên replay.
- Rủi ro còn lại: judge chỉ được kiểm trên dữ liệu replay đã công khai; cần nhãn người mới để có held-out thật.
