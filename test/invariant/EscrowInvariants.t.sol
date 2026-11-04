// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {Test, console2} from "forge-std/Test.sol";
import {StdInvariant} from "forge-std/StdInvariant.sol";
import {MilestoneEscrow} from "../../src/MilestoneEscrow.sol";
import {MockERC20} from "../mocks/Tokens.sol";
import {EscrowHandler} from "./EscrowHandler.sol";

contract EscrowInvariants is StdInvariant, Test {
    MilestoneEscrow internal escrow;
    MockERC20 internal token;
    EscrowHandler internal handler;

    function setUp() public {
        escrow = new MilestoneEscrow();
        token = new MockERC20("USD Coin", "USDC", 6);
        handler = new EscrowHandler(escrow, token);
        targetContract(address(handler));
        bytes4[] memory actions = new bytes4[](13);
        actions[0] = EscrowHandler.create.selector;
        actions[1] = EscrowHandler.fund.selector;
        actions[2] = EscrowHandler.submit.selector;
        actions[3] = EscrowHandler.approve.selector;
        actions[4] = EscrowHandler.reject.selector;
        actions[5] = EscrowHandler.dispute.selector;
        actions[6] = EscrowHandler.resolve.selector;
        actions[7] = EscrowHandler.timeoutRelease.selector;
        actions[8] = EscrowHandler.deadlineRefund.selector;
        actions[9] = EscrowHandler.cancel.selector;
        actions[10] = EscrowHandler.withdraw.selector;
        actions[11] = EscrowHandler.warp.selector;
        actions[12] = EscrowHandler.fund.selector; // funding twice as often keeps agreements flowing
        targetSelector(FuzzSelector({addr: address(handler), selectors: actions}));
    }

    /// 1. Every token the escrow holds is accounted for as locked or withdrawable. Nothing more, nothing less.
    function invariant_BalanceEqualsLockedPlusWithdrawable() public view {
        assertEq(
            token.balanceOf(address(escrow)),
            escrow.totalLocked(address(token)) + escrow.totalWithdrawable(address(token))
        );
    }

    /// 2. Money in minus money out equals what the escrow still holds: no value is created or lost.
    function invariant_ValueConserved() public view {
        assertEq(handler.ghostDeposited() - handler.ghostWithdrawn(), token.balanceOf(address(escrow)));
    }

    /// 3. Per agreement: settled never exceeds the total, the settled sum matches milestone states,
    ///    and an agreement is Closed exactly when everything is settled.
    function invariant_AgreementBookkeeping() public view {
        uint256 lockedSum;
        uint256 n = handler.idCount();
        for (uint256 k; k < n; ++k) {
            uint256 id = handler.ids(k);
            MilestoneEscrow.Agreement memory a = escrow.getAgreement(id);
            MilestoneEscrow.Milestone[] memory ms = escrow.getMilestones(id);
            uint256 settled;
            for (uint256 i; i < ms.length; ++i) {
                MilestoneEscrow.MilestoneState s = ms[i].state;
                if (
                    s == MilestoneEscrow.MilestoneState.Released || s == MilestoneEscrow.MilestoneState.Refunded
                        || s == MilestoneEscrow.MilestoneState.Resolved
                ) {
                    settled += ms[i].amount;
                }
            }
            assertLe(a.settled, a.total);
            assertEq(a.settled, settled);
            if (a.status == MilestoneEscrow.Status.Active) {
                assertLt(a.settled, a.total);
                lockedSum += a.total - a.settled;
            }
            if (a.status == MilestoneEscrow.Status.Closed && a.settled != 0) assertEq(a.settled, a.total);
        }
        // 4. The global locked counter equals the sum of what active agreements still hold.
        assertEq(escrow.totalLocked(address(token)), lockedSum);
    }

    /// 5. The arbiter never accrues a balance.
    function invariant_ArbiterNeverPaid() public view {
        assertEq(escrow.withdrawable(address(token), handler.arbiter()), 0);
    }

    function afterInvariant() external view {
        console2.log("create", handler.calls("create"), "fund", handler.calls("fund"));
        console2.log("submit", handler.calls("submit"), "approve", handler.calls("approve"));
        console2.log("reject", handler.calls("reject"), "dispute", handler.calls("dispute"));
        console2.log("resolve", handler.calls("resolve"), "timeoutRelease", handler.calls("timeoutRelease"));
        console2.log("deadlineRefund", handler.calls("deadlineRefund"), "cancel", handler.calls("cancel"));
        console2.log("withdraw", handler.calls("withdraw"));
    }
}
