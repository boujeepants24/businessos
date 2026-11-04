# Security

**Status: not audited.** Everything below describes what has been considered and tested. None of it is a guarantee. Do not deploy with real funds without an independent review.

## Assets and trust assumptions

- **Assets:** ERC-20 tokens locked in agreements, and balances waiting to be withdrawn.
- **Client and provider** are mutually untrusted and may act maliciously or simply go silent.
- **Arbiter** is trusted by both parties *only* to split disputed milestones fairly. A malicious arbiter can give a disputed milestone entirely to one side, and that's the extent of their power. They can't touch undisputed milestones, other agreements, or receive funds themselves.
- **Token** is chosen by the client and is untrusted code. A malicious token can only affect agreements that use it.
- There is **no owner, admin, upgrade path or pause.** Nobody can change the rules or move funds outside them.

## Threats and how they are handled

| Threat | Mitigation | Test |
|---|---|---|
| Re-entrancy through a token callback | `nonReentrant` on `fund` and `withdraw`; checks-effects-interactions everywhere; settlement is pure bookkeeping with no external calls | `test_ReentrantWithdrawIsBlocked`, `test_ReentrantFundIsBlocked` |
| Fee-on-transfer or rebasing token leaves the escrow short | Balance-delta check on funding; reverts with `UnsupportedToken` | `test_RejectsFeeOnTransferToken` |
| Recipient can't receive (blacklist) and blocks others | Pull payments: each party withdraws separately | `test_BlacklistedProviderCannotTrapClientFunds` |
| Malicious token drains other tokens | Per-token accounting (`totalLocked`, `totalWithdrawable`, `withdrawable` keyed by token) | `test_BadTokenCannotDrainOtherTokens` |
| Paying a milestone twice | Explicit state machine; every settling transition requires a specific prior state | `test_NoDoubleReleaseAcrossPaths`, `test_CannotApproveTwiceOrOutOfRange`, invariant 3 |
| Client stalls forever after delivery | Review-period timeout lets the provider claim | `test_ProviderPaidIfClientGoesSilent`, `testFuzz_ReviewTimeoutBoundary` |
| Provider never delivers | Deadline refund for unsubmitted milestones | `test_ClientRefundedIfProviderMissesDeadline` |
| Client claws back delivered work by waiting out the deadline | Deadline refund only applies to `Pending` milestones | `test_ClientRefundedIfProviderMissesDeadline`, `test_DisputedMilestoneCannotBeRefundedByTimeout` |
| Unauthorised caller | Role check on every state-changing function | `test_RoleChecksOnEveryAction`, `testFuzz_StrangersAreLockedOut` |
| Arithmetic errors in splits | Basis-point split with the remainder going to the client; the sum always equals the milestone | `testFuzz_DisputeSplitConservesValue`, invariants 1–2 |
| Accounting drift over many interactions | On-chain invariant `balance == locked + withdrawable` | Invariant suite (random sequences of every action) |

## Known limitations

- **Arbiter is a single address.** There's no appeal and no arbiter fee. In practice this should be a multisig or a dispute protocol.
- **No on-chain acceptance by the provider.** The provider shows acceptance by submitting work; terms live off-chain, referenced by `termsHash`.
- **`block.timestamp` is used for timeouts.** Validators can shift it by seconds; the timeouts are measured in days, so this is acceptable.
- **Rejection loops.** A client can reject submissions repeatedly. The provider's remedy is to raise a dispute.
- **No native ETH.** Use WETH.
- **Static analysis** (Slither and similar) has not been run yet.

## Reporting

Please open a GitHub issue for anything non-sensitive, or email aranthebotguy@gmail.com.
