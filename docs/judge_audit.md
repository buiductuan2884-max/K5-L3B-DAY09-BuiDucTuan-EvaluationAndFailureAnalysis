# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5` (từ `src/`). Positive class = FAIL (việc của judge là tìm lỗi).

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | Đạt | dùng |
| helpful | 100 | 0.375 | 1.000 | 0.300 | Không (κ, R dưới sàn) | loại |

Ma trận nhầm lẫn:
- tone_ok: tp 24, fp 4, fn 6, tn 66. Tỉ lệ FAIL quan sát 0.28 → sau Rogan-Gladen 0.30.
- helpful: tp 9, fp 0, fn 21, tn 70. Tỉ lệ FAIL quan sát 0.09 → sau Rogan-Gladen 0.30. Judge báo 9% lỗi trong khi thực tế khoảng 30%, tức là lỗi trông nhỏ đi hơn 3 lần.

## ≥5 case audit thủ công
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú / sửa rubric |
|---|---|---|---|---|---|
| 1 | H-008 "Em đã hoàn tiền cho anh rồi nha…" | PASS | FAIL | Người | Xưng "em" + "nha" quá suồng sã. Rubric thêm: *xưng hô phải là "LogiX – anh/chị"; "em/bạn/nha/nhé" = FAIL*. |
| 2 | H-017 "Dạ, bạn ơi LogiX đã hoàn 25.000đ…" | PASS | FAIL | Người | Cùng lỗi xưng hô; dùng chung quy tắc ở #1. |
| 3 | H-029 "Dạ, vui lòng chờ… không cần nhắn thêm." | PASS | FAIL | Người | Judge bị đánh lừa bởi "Dạ, vui lòng". Rubric thêm: *câu mệnh lệnh / cấm khách liên hệ = FAIL dù có kính ngữ*. |
| 4 | H-042 "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | Người | Judge phạt vì "thiếu xin lỗi". Rubric ghi rõ: *không bắt buộc xin lỗi khi đã giải quyết xong; ngắn mà đủ ý = PASS*. |
| 5 | H-051 "Dạ, LogiX đã refund 90.000đ…" | FAIL | PASS | Người | CS LogiX cho dùng từ "refund". Thêm danh sách từ tiếng Anh được phép vào rubric. |
| 6 | H-070 "…đã hoàn 90.000đ cho đơn O-909 ạ 😂😂" | PASS | FAIL | Người | Rubric thêm: *emoji cười trong ngữ cảnh khiếu nại = FAIL*. |
| 7 | H-063 "…đã hoàn 20.000đ và sẽ hoàn thêm…" | PASS | FAIL | Người | Hứa ngoài kết quả hệ thống. Lỗi này nằm ở nội dung chứ không ở giọng điệu, nên không bắt judge tone gánh. Grader code `reply_matches_ledger` (FM-08) chỉ bắt được phần số tiền khi reply nói đã hoàn mà số không khớp ledger; lời hứa "sẽ hoàn thêm" không kèm số vẫn cần một quy tắc riêng trong rubric. |
| 8 | H-081 "Dạ, đơn O-107 chưa đủ điều kiện hoàn…" | FAIL | PASS | Judge | Nhãn người sai (đọc nhầm ticket). Sửa nhãn trong bộ calibration lần sau. |
| 9 | HL-015 / HL-020 / HL-043 "Dạ, LogiX đã hoàn 55.000đ…" (ledger 40.000đ…) | PASS | FAIL | Người | Judge helpful không có ledger nên không thể biết số tiền sai. Không sửa được bằng rubric → chuyển sang code grader. |

## Kết luận
- helpful bị loại. Recall 0.30 nghĩa là cứ 10 reply tệ thì judge bỏ qua 7. Nhìn theo loại lỗi người gắn: judge bỏ sót 18/18 reply sai tiền và 3/3 sai xưng hô, chỉ bắt được lỗi hiển nhiên (lạc đề, giọng cụt). Precision 1.0 không cứu được vì judge chỉ báo FAIL khi lỗi quá rõ. Nếu dùng làm gate, nó sẽ cho qua đúng loại lỗi nguy hiểm nhất (sai tiền). Phần "sai tiền" đã được grader code `reply_matches_ledger` (FM-08) thay thế.
- tone_ok dùng được, nhưng chỉ cho giọng điệu, không phải cổng chặn tiền. 6/10 bất đồng ở trên là lỗi xưng hô/giọng ra lệnh: sửa rubric theo các dòng #1 đến #6 rồi calibrate lại.
- Rủi ro còn lại: judge chỉ được kiểm trên dữ liệu replay đã công khai (100 dòng mỗi tiêu chí); cần nhãn người mới để có held-out thật.
