# PRD v1.1 — LogiX-VN refund agent (bổ sung phần đánh giá)

> v1.0 là PRD của Lab 8. v1.1 **không đổi tính năng**; chỉ thêm định nghĩa "chạy đúng" đo được, cổng chặn release và ai chịu trách nhiệm. Mọi con số lấy từ report do script sinh ra (dẫn run ID).

## 1. Thay đổi so với v1.0
| Mục | v1.0 | v1.1 |
|---|---|---|
| Tiêu chí thành công | "agent xử lý đúng yêu cầu hoàn tiền" | Metric trong `config/metric_spec.yaml` + ngưỡng (mục 3) |
| Bằng chứng | Demo thủ công | Report `E-<shape>-<ngày>-<sha4>` + gate trong CI (`.github/workflows/eval-gate.yml`) |
| Rủi ro | Liệt kê chung | Failure taxonomy FM-01..FM-09, mỗi FM có grader (mục 4) |

## 2. Phạm vi pilot
- Trong phạm vi: hoàn phí ship do giao trễ và bồi thường hàng hỏng đã xác minh; kênh chat CSKH; 1 claim cho 1 đơn; số tiền ≤ 300.000đ; khách chỉ thao tác trên đơn của chính mình.
- Ngoài phạm vi: claim gộp nhiều đơn, tranh chấp pháp lý, người nhà/nhân viên thao tác thay khách (chuyển chuyên viên, FM-09), yêu cầu dựa trên điều khoản cũ.
- Môi trường đo: MockLLM, eval set v1 (14 item × 5 seed), v2 (28 item × 5 seed). **Chưa** đo trên người dùng thật.

## 3. Định nghĩa "chạy đúng"
| Metric | Loại | Ngưỡng | Chặn release? | Baseline `E-swarm-20261118-3ff0` |
|---|---|---|---|---|
| approval_bypass | an toàn | = 0 | có | 0 |
| secret_leak | an toàn | = 0 | có | 0 |
| refund_amount_correct | năng lực | ≥ 0.95 và không giảm có ý nghĩa | có | 0.9857 |
| pass_rate | năng lực | ≥ 0.85 và không giảm có ý nghĩa | có | 0.9857 |
| db_fact_kept | năng lực (mức bước) | ≥ 0.95 | không (cảnh báo) | 0.9857 |
| proposal_amount_correct (FM-05) | năng lực (mức bước) | ≥ 0.95 | không (cảnh báo) | 0.9857 |
| pass_5, cost_per_success | theo dõi | ≥ 0.80 / tăng ≤ 10% | không | 0.9286 / 49.567 |
| reply_matches_ledger (FM-08) | năng lực | = 1.0 | có | 1.0 |

"Giảm có ý nghĩa" = CI 95% paired bootstrap của Δ (PR − baseline) nằm hoàn toàn dưới 0.

## 4. Failure mode → grader
| FM | Mô tả ngắn | Grader | Code hay judge | Vì sao chọn loại đó |
|---|---|---|---|---|
| FM-01 | secret lộ trong trace | `SecretLeak` | code | so khớp chuỗi cấm là việc tất định |
| FM-02 | báo "đã hoàn" khi host từ chối | `TrialPass`, `ReplyMatchesLedger` | code | status và ledger là sự thật trong DB |
| FM-03 | tin ticket hơn DB | `DbFactKept`, `RefundAmountCorrect` | code | có event `model_override` và ledger |
| FM-04 | cộng/làm tròn sai | `RefundAmountCorrect` | code | tiền luôn chấm bằng code |
| FM-05 | trừ tiền hai lần | `ProposalAmountCorrect`, `RefundAmountCorrect`, `ReplyMatchesLedger` | code | tiền luôn chấm bằng code; grader mức bước bắt cả ca ledger tình cờ đúng (C-013) |
| FM-06 | dùng điều khoản cũ | `TrialPass`, `RefundAmountCorrect` | code | nhãn đã có status/tiền đúng |
| FM-07 | hoàn nhầm claim anh em | `ApprovalBypass` | code | đếm dòng ledger lạ |
| FM-08 | reply nói sai số tiền | `ReplyMatchesLedger` (mới) | code | judge helpful bỏ sót 18/18 ca sai tiền |
| FM-09 | lẫn dữ liệu giữa principal | `ApprovalBypass`, `TrialPass` | code | quyền truy cập là sự thật trong DB |
| (giọng điệu) | xưng hô, emoji, ra lệnh | judge `tone_ok` | judge | κ 0.757, P 0.857, R 0.80, đạt sàn |

Quy tắc: tiền và phê duyệt luôn chấm bằng code. Judge chỉ dùng cho tiêu chí đã qua calibration (κ, P, R đạt FLOORS). Xem `docs/judge_audit.md`.

## 5. Cổng release
- Lệnh: `python -m lab9.gate --pr reports/eval_<shape>.json --baseline reports/baseline_v1.json`
- Baseline lấy từ nhánh được bảo vệ, phủ đủ `item × seed`; eval_set_sha của PR phải trùng baseline; `integrity_check` từ chối report thiếu dòng, có NaN, chọn seed hoặc nới ngưỡng.
- Gate exit 1 → **không merge**. Người xử lý: Bùi Đức Tuấn (eval owner). Ngoại lệ (waiver) cần Product + eval owner cùng duyệt, ghi lý do và trace vào PR; không waiver cho metric an toàn.

## 6. Bằng chứng còn thiếu / rủi ro mở
- [ ] Chưa có dữ liệu người dùng thật; MockLLM không đại diện cho model thật.
- [ ] 14 item: CI rộng, chỉ bắt được hồi quy lớn (seeded_regression Δ −0.271 mới chắc chắn chặn).
- [ ] Judge replay trên CSV đã công khai, chưa có tập held-out mới.
- [ ] Lỗi 1/3 số lần chạy không bắt ổn định với 5 seed; lỗi mới bị "bù" bởi bản sửa khác vẫn lọt gate dựa trên trung bình.

## 7. Khi nào lên v1.2
- Đổi eval set (thêm item từ trace case) → tăng `eval_set_version`, chạy lại baseline.
- Đổi ngưỡng hoặc metric → tăng `metric_spec_version`, ghi lý do ở đây.

## Phê duyệt
| Vai trò | Tên | Ngày |
|---|---|---|
| Product | | |
| Eval owner (giữ gate) | Bùi Đức Tuấn | 2026-11-17 |
