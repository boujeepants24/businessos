// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {BaseTest} from "./Base.t.sol";
import {MilestoneEscrow} from "../src/MilestoneEscrow.sol";
import {FeeOnTransferToken, BlacklistToken, ReentrantToken, MockERC20} from "./mocks/Tokens.sol";

contract AdversarialTest is BaseTest {
    function _one(uint128 amount) internal pure returns (uint128[] memory a) {
        a = new uint128[](1);
        a[0] = amount;
    }

    /// A token that skims on transfer would leave the escrow short. Funding must fail.
    function test_RejectsFeeOnTransferToken() public {
        FeeOnTransferToken fot = new FeeOnTransferToken();
        fot.mint(client, 1_000e18);
        vm.startPrank(client);
        fot.approve(address(escrow), type(uint256).max);
        uint256 id = escrow.createAgreement(
            provider, arbiter, IERC20(address(fot)), _one(100e18), REVIEW, uint64(block.timestamp + 30 days), TERMS
        );
        vm.expectRevert(MilestoneEscrow.UnsupportedToken.selector);
        escrow.fund(id);
        vm.stopPrank();
    }

    /// A blacklisted provider can't receive USDC. With push payments that would trap the client's
    /// refund too; with pull payments the client still gets their money out.
    function test_BlacklistedProviderCannotTrapClientFunds() public {
        BlacklistToken bl = new BlacklistToken();
        bl.mint(client, 10_000e6);
        uint128[] memory a = new uint128[](2);
        a[0] = 1_000e6;
        a[1] = 2_000e6;
        vm.startPrank(client);
        bl.approve(address(escrow), type(uint256).max);
        uint256 id = escrow.createAgreement(
            provider, arbiter, IERC20(address(bl)), a, REVIEW, uint64(block.timestamp + 30 days), TERMS
        );
        escrow.fund(id);
        vm.stopPrank();

        vm.prank(provider);
        escrow.submitMilestone(id, 0, bytes32("d"));
        vm.prank(client);
        escrow.approveMilestone(id, 0); // credit only, no transfer, so this succeeds
        bl.setBlacklisted(provider, true);

        vm.prank(provider);
        vm.expectRevert(bytes("blacklisted"));
        escrow.withdraw(IERC20(address(bl)));

        vm.warp(block.timestamp + 31 days);
        vm.prank(client);
        escrow.refundAfterDeadline(id, 1);
        vm.prank(client);
        escrow.withdraw(IERC20(address(bl)));
        assertEq(bl.balanceOf(client), 10_000e6 - 1_000e6, "client recovered the undelivered milestone");
        _assertAccounting(address(bl));
    }

    /// A malicious token re-enters `withdraw` during the payout transfer. The guard stops the double-dip.
    function test_ReentrantWithdrawIsBlocked() public {
        ReentrantToken rt = new ReentrantToken();
        rt.mint(client, 1_000e18);
        vm.startPrank(client);
        rt.approve(address(escrow), type(uint256).max);
        uint256 id = escrow.createAgreement(
            provider, arbiter, IERC20(address(rt)), _one(100e18), REVIEW, uint64(block.timestamp + 30 days), TERMS
        );
        escrow.fund(id);
        vm.stopPrank();
        vm.prank(provider);
        escrow.raiseDispute(id, 0);
        vm.prank(arbiter);
        escrow.resolveDispute(id, 0, 5_000);

        rt.arm(address(escrow), abi.encodeCall(MilestoneEscrow.withdraw, (IERC20(address(rt)))));
        vm.prank(client);
        escrow.withdraw(IERC20(address(rt)));
        assertFalse(rt.attackSucceeded(), "re-entry must fail");
        assertEq(rt.balanceOf(client), 1_000e18 - 50e18);
        assertEq(escrow.withdrawable(address(rt), provider), 50e18, "provider's share untouched");
        _assertAccounting(address(rt));
    }

    /// Re-entering `fund` from inside the funding transfer can't double-lock or skip the payment.
    function test_ReentrantFundIsBlocked() public {
        ReentrantToken rt = new ReentrantToken();
        rt.mint(client, 1_000e18);
        vm.startPrank(client);
        rt.approve(address(escrow), type(uint256).max);
        uint256 id = escrow.createAgreement(
            provider, arbiter, IERC20(address(rt)), _one(100e18), REVIEW, uint64(block.timestamp + 30 days), TERMS
        );
        vm.stopPrank();
        rt.arm(address(escrow), abi.encodeCall(MilestoneEscrow.fund, (id)));
        vm.prank(client);
        escrow.fund(id);
        assertFalse(rt.attackSucceeded());
        assertEq(escrow.totalLocked(address(rt)), 100e18);
        _assertAccounting(address(rt));
    }

    /// A malicious token can only affect agreements that use it: accounting is per token.
    function test_BadTokenCannotDrainOtherTokens() public {
        uint256 good = _createFunded(); // 6,000 USDC locked
        ReentrantToken rt = new ReentrantToken();
        rt.mint(client, 1_000e18);
        vm.startPrank(client);
        rt.approve(address(escrow), type(uint256).max);
        uint256 bad = escrow.createAgreement(
            provider, arbiter, IERC20(address(rt)), _one(1e18), REVIEW, uint64(block.timestamp + 30 days), TERMS
        );
        vm.stopPrank();
        // During its own funding transfer, the token tries to withdraw USDC on the escrow's behalf.
        rt.arm(address(escrow), abi.encodeCall(MilestoneEscrow.withdraw, (IERC20(address(usdc)))));
        vm.prank(client);
        escrow.fund(bad);
        assertEq(usdc.balanceOf(address(escrow)), 6_000e6, "USDC untouched");
        assertEq(escrow.getAgreement(good).settled, 0);
        _assertAccounting(address(usdc));
    }

    /// The provider can't be paid twice by mixing the timeout path and the approval path.
    function test_NoDoubleReleaseAcrossPaths() public {
        uint256 id = _createFunded();
        _submit(id, 0);
        vm.warp(block.timestamp + REVIEW);
        vm.prank(provider);
        escrow.releaseAfterReview(id, 0);
        vm.prank(client);
        vm.expectRevert(MilestoneEscrow.WrongMilestoneState.selector);
        escrow.approveMilestone(id, 0);
        vm.prank(provider);
        vm.expectRevert(MilestoneEscrow.WrongMilestoneState.selector);
        escrow.raiseDispute(id, 0);
        assertEq(escrow.withdrawable(address(usdc), provider), 1_000e6);
    }

    /// The client can't use a dispute to escape paying for delivered work once it's released,
    /// and can't refund a milestone that's under dispute by waiting out the deadline.
    function test_DisputedMilestoneCannotBeRefundedByTimeout() public {
        uint256 id = _createFunded();
        vm.prank(provider);
        escrow.raiseDispute(id, 0);
        vm.warp(block.timestamp + 61 days);
        vm.prank(client);
        vm.expectRevert(MilestoneEscrow.WrongMilestoneState.selector);
        escrow.refundAfterDeadline(id, 0);
    }

    /// Operations on one agreement can never touch another agreement's milestones.
    function test_AgreementsAreIsolated() public {
        uint256 a = _createFunded();
        uint256 b = _createFunded();
        _submit(a, 0);
        vm.prank(client);
        escrow.approveMilestone(a, 0);
        assertEq(uint8(_state(b, 0)), uint8(MilestoneEscrow.MilestoneState.Pending));
        assertEq(escrow.getAgreement(b).settled, 0);
    }
}
