// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {BaseTest} from "./Base.t.sol";
import {MilestoneEscrow} from "../src/MilestoneEscrow.sol";

/// Every guard that rejects an invalid call, exercised once. These are the checks an attacker probes first.
contract GuardsTest is BaseTest {
    function test_TotalAboveUint128Reverts() public {
        uint128[] memory a = new uint128[](2);
        a[0] = type(uint128).max;
        a[1] = 1;
        vm.prank(client);
        vm.expectRevert(MilestoneEscrow.InvalidParams.selector);
        escrow.createAgreement(
            provider, arbiter, IERC20(address(usdc)), a, REVIEW, uint64(block.timestamp + 1 days), TERMS
        );
    }

    function test_CancelUnfundedGuards() public {
        uint256 id = _create(_amounts3());
        vm.prank(provider);
        vm.expectRevert(MilestoneEscrow.NotAuthorized.selector);
        escrow.cancelUnfunded(id);
        vm.prank(client);
        escrow.fund(id);
        vm.prank(client);
        vm.expectRevert(MilestoneEscrow.WrongStatus.selector);
        escrow.cancelUnfunded(id); // funded agreements need mutual cancel instead
    }

    function test_ActionsOnUnfundedAgreementRevert() public {
        uint256 id = _create(_amounts3());
        vm.prank(provider);
        vm.expectRevert(MilestoneEscrow.WrongStatus.selector);
        escrow.submitMilestone(id, 0, bytes32(0));
        vm.prank(client);
        vm.expectRevert(MilestoneEscrow.WrongStatus.selector);
        escrow.requestCancel(id);
        vm.prank(arbiter);
        vm.expectRevert(MilestoneEscrow.WrongStatus.selector);
        escrow.resolveDispute(id, 0, 0);
    }

    function test_SubmitTwiceReverts() public {
        uint256 id = _createFunded();
        _submit(id, 0);
        vm.prank(provider);
        vm.expectRevert(MilestoneEscrow.WrongMilestoneState.selector);
        escrow.submitMilestone(id, 0, bytes32(0));
    }

    function test_RejectOrTimeoutBeforeSubmissionReverts() public {
        uint256 id = _createFunded();
        vm.prank(client);
        vm.expectRevert(MilestoneEscrow.WrongMilestoneState.selector);
        escrow.rejectMilestone(id, 0, bytes32(0));
        vm.prank(provider);
        vm.expectRevert(MilestoneEscrow.WrongMilestoneState.selector);
        escrow.releaseAfterReview(id, 0);
    }

    function test_OnlyClientCanClaimDeadlineRefund() public {
        uint256 id = _createFunded();
        vm.warp(block.timestamp + 61 days);
        vm.prank(provider);
        vm.expectRevert(MilestoneEscrow.NotAuthorized.selector);
        escrow.refundAfterDeadline(id, 0);
    }

    function test_ResolveOutOfRangeAndAfterClose() public {
        uint128[] memory a = new uint128[](1);
        a[0] = 100e6;
        uint256 id = _create(a);
        vm.prank(client);
        escrow.fund(id);
        vm.prank(arbiter);
        vm.expectRevert(MilestoneEscrow.InvalidMilestone.selector);
        escrow.resolveDispute(id, 1, 0);

        vm.prank(provider);
        escrow.raiseDispute(id, 0);
        vm.prank(arbiter);
        escrow.resolveDispute(id, 0, 10_000); // closes the agreement
        vm.prank(arbiter);
        vm.expectRevert(MilestoneEscrow.WrongStatus.selector);
        escrow.resolveDispute(id, 0, 0);
    }
}
