// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {BaseTest} from "./Base.t.sol";
import {MilestoneEscrow} from "../src/MilestoneEscrow.sol";

contract MilestoneEscrowTest is BaseTest {
    // ---------------------------------------------------------------- creation & funding

    function test_CreateStoresTermsAndMilestones() public {
        uint256 id = _create(_amounts3());
        MilestoneEscrow.Agreement memory a = escrow.getAgreement(id);
        assertEq(a.client, client);
        assertEq(a.provider, provider);
        assertEq(a.arbiter, arbiter);
        assertEq(a.total, 6_000e6);
        assertEq(a.milestoneCount, 3);
        assertEq(uint8(a.status), uint8(MilestoneEscrow.Status.Created));
        assertEq(escrow.getMilestones(id).length, 3);
        assertEq(usdc.balanceOf(address(escrow)), 0, "nothing moves before funding");
    }

    function test_CreateRejectsBadParams() public {
        uint128[] memory ok = _amounts3();
        uint128[] memory empty = new uint128[](0);
        uint128[] memory zero = new uint128[](1);
        uint128[] memory tooMany = new uint128[](21);
        for (uint256 i; i < 21; ++i) {
            tooMany[i] = 1;
        }
        IERC20 t = IERC20(address(usdc));
        uint64 dl = uint64(block.timestamp + 30 days);

        vm.startPrank(client);
        vm.expectRevert(MilestoneEscrow.InvalidParams.selector);
        escrow.createAgreement(provider, arbiter, t, empty, REVIEW, dl, TERMS);
        vm.expectRevert(MilestoneEscrow.InvalidParams.selector);
        escrow.createAgreement(provider, arbiter, t, zero, REVIEW, dl, TERMS);
        vm.expectRevert(MilestoneEscrow.InvalidParams.selector);
        escrow.createAgreement(provider, arbiter, t, tooMany, REVIEW, dl, TERMS);
        vm.expectRevert(MilestoneEscrow.InvalidParams.selector);
        escrow.createAgreement(client, arbiter, t, ok, REVIEW, dl, TERMS); // client is provider
        vm.expectRevert(MilestoneEscrow.InvalidParams.selector);
        escrow.createAgreement(provider, provider, t, ok, REVIEW, dl, TERMS); // arbiter is provider
        vm.expectRevert(MilestoneEscrow.InvalidParams.selector);
        escrow.createAgreement(provider, arbiter, t, ok, 1 hours, dl, TERMS); // review too short
        vm.expectRevert(MilestoneEscrow.InvalidParams.selector);
        escrow.createAgreement(provider, arbiter, t, ok, REVIEW, uint64(block.timestamp), TERMS); // deadline now
        vm.stopPrank();
    }

    function test_FundMovesExactTotal() public {
        uint256 id = _create(_amounts3());
        vm.prank(client);
        escrow.fund(id);
        assertEq(usdc.balanceOf(address(escrow)), 6_000e6);
        assertEq(escrow.totalLocked(address(usdc)), 6_000e6);
        assertEq(uint8(escrow.getAgreement(id).status), uint8(MilestoneEscrow.Status.Active));
        _assertAccounting(address(usdc));
    }

    function test_OnlyClientFundsOnce() public {
        uint256 id = _create(_amounts3());
        vm.prank(stranger);
        vm.expectRevert(MilestoneEscrow.NotAuthorized.selector);
        escrow.fund(id);
        vm.startPrank(client);
        escrow.fund(id);
        vm.expectRevert(MilestoneEscrow.WrongStatus.selector);
        escrow.fund(id);
        vm.stopPrank();
    }

    function test_CancelUnfunded() public {
        uint256 id = _create(_amounts3());
        vm.prank(client);
        escrow.cancelUnfunded(id);
        assertEq(uint8(escrow.getAgreement(id).status), uint8(MilestoneEscrow.Status.Closed));
        vm.prank(client);
        vm.expectRevert(MilestoneEscrow.WrongStatus.selector);
        escrow.fund(id);
    }

    // ---------------------------------------------------------------- happy path

    function test_FullHappyPath() public {
        uint256 id = _createFunded();
        for (uint256 i; i < 3; ++i) {
            _submit(id, i);
            vm.prank(client);
            escrow.approveMilestone(id, i);
            assertEq(uint8(_state(id, i)), uint8(MilestoneEscrow.MilestoneState.Released));
        }
        assertEq(uint8(escrow.getAgreement(id).status), uint8(MilestoneEscrow.Status.Closed));
        assertEq(escrow.withdrawable(address(usdc), provider), 6_000e6);

        vm.prank(provider);
        escrow.withdraw(IERC20(address(usdc)));
        assertEq(usdc.balanceOf(provider), 6_000e6);
        assertEq(usdc.balanceOf(address(escrow)), 0);
        _assertAccounting(address(usdc));
    }

    function test_RejectThenResubmit() public {
        uint256 id = _createFunded();
        _submit(id, 0);
        vm.prank(client);
        escrow.rejectMilestone(id, 0, keccak256("needs mobile layout"));
        assertEq(uint8(_state(id, 0)), uint8(MilestoneEscrow.MilestoneState.Pending));
        _submit(id, 0);
        vm.prank(client);
        escrow.approveMilestone(id, 0);
        assertEq(escrow.withdrawable(address(usdc), provider), 1_000e6);
    }

    // ---------------------------------------------------------------- timeouts

    function test_ProviderPaidIfClientGoesSilent() public {
        uint256 id = _createFunded();
        _submit(id, 1);
        vm.warp(block.timestamp + REVIEW - 1);
        vm.prank(provider);
        vm.expectRevert(MilestoneEscrow.ReviewPeriodNotOver.selector);
        escrow.releaseAfterReview(id, 1);
        vm.warp(block.timestamp + 1);
        vm.prank(provider);
        escrow.releaseAfterReview(id, 1);
        assertEq(escrow.withdrawable(address(usdc), provider), 2_000e6);
    }

    function test_ClientRefundedIfProviderMissesDeadline() public {
        uint256 id = _createFunded();
        _submit(id, 0); // delivered milestone 0 only
        vm.prank(client);
        vm.expectRevert(MilestoneEscrow.DeadlineNotPassed.selector);
        escrow.refundAfterDeadline(id, 1);

        vm.warp(block.timestamp + 61 days);
        vm.startPrank(client);
        escrow.refundAfterDeadline(id, 1);
        escrow.refundAfterDeadline(id, 2);
        vm.expectRevert(MilestoneEscrow.WrongMilestoneState.selector);
        escrow.refundAfterDeadline(id, 0); // submitted work can't be clawed back by timeout
        vm.stopPrank();
        assertEq(escrow.withdrawable(address(usdc), client), 5_000e6);
        _assertAccounting(address(usdc));
    }

    // ---------------------------------------------------------------- disputes

    function test_DisputeSplitByArbiter() public {
        uint256 id = _createFunded();
        _submit(id, 2);
        vm.prank(client);
        escrow.raiseDispute(id, 2);

        vm.prank(client);
        vm.expectRevert(MilestoneEscrow.WrongMilestoneState.selector);
        escrow.approveMilestone(id, 2); // frozen while disputed

        vm.prank(provider);
        vm.expectRevert(MilestoneEscrow.NotAuthorized.selector);
        escrow.resolveDispute(id, 2, 10_000);

        vm.prank(arbiter);
        escrow.resolveDispute(id, 2, 7_000); // 70% to provider
        assertEq(escrow.withdrawable(address(usdc), provider), 2_100e6);
        assertEq(escrow.withdrawable(address(usdc), client), 900e6);
        assertEq(escrow.withdrawable(address(usdc), arbiter), 0, "arbiter never receives funds");
        _assertAccounting(address(usdc));
    }

    function test_ArbiterCannotTouchUndisputedMilestones() public {
        uint256 id = _createFunded();
        _submit(id, 0);
        vm.prank(arbiter);
        vm.expectRevert(MilestoneEscrow.WrongMilestoneState.selector);
        escrow.resolveDispute(id, 0, 10_000);
    }

    function test_ResolveRejectsBpsAbove100Percent() public {
        uint256 id = _createFunded();
        vm.prank(provider);
        escrow.raiseDispute(id, 0);
        vm.prank(arbiter);
        vm.expectRevert(MilestoneEscrow.InvalidParams.selector);
        escrow.resolveDispute(id, 0, 10_001);
    }

    // ---------------------------------------------------------------- cancellation

    function test_MutualCancelRefundsUnsettledButLeavesDisputes() public {
        uint256 id = _createFunded();
        _submit(id, 0);
        vm.prank(client);
        escrow.approveMilestone(id, 0); // 1,000 released
        _submit(id, 1);
        vm.prank(provider);
        escrow.raiseDispute(id, 1); // 2,000 disputed

        vm.prank(client);
        escrow.requestCancel(id);
        assertEq(escrow.withdrawable(address(usdc), client), 0, "one-sided request does nothing");
        vm.prank(provider);
        escrow.requestCancel(id);

        assertEq(escrow.withdrawable(address(usdc), client), 3_000e6, "milestone 2 refunded");
        assertEq(uint8(_state(id, 1)), uint8(MilestoneEscrow.MilestoneState.Disputed));
        assertEq(uint8(escrow.getAgreement(id).status), uint8(MilestoneEscrow.Status.Active));

        vm.prank(arbiter);
        escrow.resolveDispute(id, 1, 5_000);
        assertEq(uint8(escrow.getAgreement(id).status), uint8(MilestoneEscrow.Status.Closed));
        _assertAccounting(address(usdc));
    }

    function test_StrangerCannotRequestCancel() public {
        uint256 id = _createFunded();
        vm.prank(stranger);
        vm.expectRevert(MilestoneEscrow.NotAuthorized.selector);
        escrow.requestCancel(id);
    }

    // ---------------------------------------------------------------- access control sweep

    function test_RoleChecksOnEveryAction() public {
        uint256 id = _createFunded();
        vm.startPrank(stranger);
        vm.expectRevert(MilestoneEscrow.NotAuthorized.selector);
        escrow.submitMilestone(id, 0, bytes32(0));
        vm.stopPrank();

        _submit(id, 0);
        address[3] memory notClient = [provider, arbiter, stranger];
        for (uint256 k; k < 3; ++k) {
            vm.startPrank(notClient[k]);
            vm.expectRevert(MilestoneEscrow.NotAuthorized.selector);
            escrow.approveMilestone(id, 0);
            vm.expectRevert(MilestoneEscrow.NotAuthorized.selector);
            escrow.rejectMilestone(id, 0, bytes32(0));
            vm.stopPrank();
        }
        vm.prank(client);
        vm.expectRevert(MilestoneEscrow.NotAuthorized.selector);
        escrow.submitMilestone(id, 1, bytes32(0));
        vm.prank(arbiter);
        vm.expectRevert(MilestoneEscrow.NotAuthorized.selector);
        escrow.raiseDispute(id, 1);
    }

    function test_CannotApproveTwiceOrOutOfRange() public {
        uint256 id = _createFunded();
        _submit(id, 0);
        vm.startPrank(client);
        escrow.approveMilestone(id, 0);
        vm.expectRevert(MilestoneEscrow.WrongMilestoneState.selector);
        escrow.approveMilestone(id, 0);
        vm.expectRevert(MilestoneEscrow.InvalidMilestone.selector);
        escrow.approveMilestone(id, 3);
        vm.stopPrank();
    }

    function test_WithdrawNothingReverts() public {
        vm.prank(stranger);
        vm.expectRevert(MilestoneEscrow.NothingToWithdraw.selector);
        escrow.withdraw(IERC20(address(usdc)));
    }
}
