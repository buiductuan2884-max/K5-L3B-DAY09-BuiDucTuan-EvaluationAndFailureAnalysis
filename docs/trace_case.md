# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-014 --seed 11
python -m lab9.trace_case --shape fixed --claim C-014 --seed 11   # đối chứng
```

## Case: khách bị trừ tiền hai lần (C-014@11)

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-014@11`, report `reports/eval_seeded_regression.json` (run `E-seeded_regression-20261118-3ff0`) |
| Triệu chứng | `refund_amount_correct`, `reply_matches_ledger` và `proposal_amount_correct` FAIL (đề xuất 120.000, nhãn 150.000). Reply nói "Dạ, LogiX đã hoàn 120.000đ cho đơn O-515" nhưng ledger chỉ ghi 90.000đ (nhãn 120.000đ). Grader Lab 8: `proposal_mismatch`. |
| Bước sai đầu tiên | Event 5 `proposal` `{"amount_vnd": 120000}`: agent tự lấy quote 150.000 trừ 30.000 đã hoàn rồi mới gửi host. |
| Vì sao là bước *đầu tiên* | Event 1 `handoff` và 2 `investigator` đọc đúng đơn O-515. Event 3 `quote` = 150.000 (SHIP-LATE-03 + DMG-04, lấy mức lớn nhất), khớp quy tắc. Event 4 `refund_history` = 30.000, đúng dữ liệu. Tới event 5 agent mới làm điều sai: tự trừ, trong khi `business_rules.md` nói host đã tự trừ phần đã hoàn. Host trừ thêm 30.000 → 90.000. |
| Failure mode | FM-05 pre_deducted (kéo theo FM-08: reply nói 120.000 nhưng ledger 90.000) |
| Đối chứng | `fixed C-014@11`: không có event `refund_history` và `proposal`; agent gửi nguyên quote 150.000, host trừ 30.000 → ledger 120.000 = nhãn; reply "120.000đ" khớp ledger. |
| Regression test | `src/tests/test_lab9_team.py::test_trace_case_c014_pre_deducted`: `RefundAmountCorrect` và `ReplyMatchesLedger` FAIL trên `seeded_regression`, PASS trên `fixed`, và event `proposal` chỉ xuất hiện ở bản lỗi. Đã chạy: 2/2 pass. |
| Chưa chắc chắn | Trace không cho biết *vì sao* agent tự trừ (prompt hay logic); chỉ thấy hành vi. MockLLM tất định nên chưa biết với LLM thật lỗi này xuất hiện bao nhiêu % lần. |

## Case phụ: lỗi có sẵn trong baseline (C-002@55)
`python -m lab9.trace_case --shape swarm --claim C-002 --seed 55`: event 3 `model_override {"delay_days": 5}`. Ticket khai trễ 5 ngày, DB ghi 2 ngày; agent tin ticket nên hoàn 20.000đ cho đơn không đủ điều kiện (FM-03). Lỗi chỉ xảy ra ở seed 55 (`seed % 5 == 0`), nên baseline pass_rate = 0.9857 và pass^5 = 0.9286. Bản `fixed` sửa đúng lỗi này.

## Quy tắc
- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được.
