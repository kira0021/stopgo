> **MOCKED**: no real payment, publication or delivery happened.
> **DEMO FIXTURE**: founder-reported numbers in this run come from a demo brief, not from real interviews or sign-ups.

# Payment and delivery test log

**MOCKED.** No payment provider (real or sandbox) is called. Events are simulated in-process.
Price under test: $9.00. Fee model (ASSUMPTION): 2.9% + $0.30 per charge.

## Events

| # | Step | Result |
|---|---|---|
| 1 | payment.succeeded for ord_1 (evt_mock_c3dd9038) | access_granted |
| 2 | payment.succeeded for ord_2 (evt_mock_a7474b80) | access_granted |
| 3 | payment.succeeded for ord_3 (evt_mock_e085faa9) | access_granted |
| 4 | same payment webhook for ord_1 delivered again (provider retry) | duplicate_ignored |
| 5 | refund ord_2 without founder approval | blocked (ApprovalRequired) |
| 6 | refund ord_2 with founder approval apr_c37a8401f7 (MOCKED) | access_revoked |
| 7 | same refund webhook delivered again | duplicate_ignored |

## Reconciliation

| Order | Amount | Paid | Fee | Refunded | Access |
|---|---|---|---|---|---|
| ord_1 | 9.00 | True | 0.56 | False | True |
| ord_2 | 9.00 | True | 0.56 | True | False |
| ord_3 | 9.00 | True | 0.56 | False | True |

Gross 27.00 - fees 1.68 - refunds 9.00 = expected payout 16.32; mocked payout 16.32.
Problems: none

## Checks

- PASS: payment_grants_access
- PASS: duplicate_webhook_no_double_delivery
- PASS: refund_blocked_without_approval
- PASS: refund_revokes_access
- PASS: reconciliation_balanced
