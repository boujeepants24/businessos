// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {BaseTest} from "./Base.t.sol";
import {MilestoneEscrow} from "../src/MilestoneEscrow.sol";

contract MilestoneEscrowFuzzTest is BaseTest {
    /// Any set of milestone amounts: funding locks exactly their sum.
    function testFuzz_FundLocksExactSum(uint128[20] memory raw, uint8 count) public {
        uint256 n = bound(count, 1, 20);
        uint128[] memory amounts = new uint128[](n);
        uint256 sum;
        for (uint256 i; i < n; ++i) {
            amounts[i] = uint128(bound(raw[i], 1, 1e30));
            sum += amounts[i];
        }
        usdc.mint(client, sum);
        uint256 id = _create(amounts);
        vm.prank(client);
        escrow.fund(id);
        assertEq(escrow.totalLocked(address(usdc)), sum);
        assertEq(escrow.getAgreement(id).total, sum);
        _assertAccounting(address(usdc));
    }

    /// Any arbiter split pays out exactly the milestone amount, never more, never to the arbiter.
    function testFuzz_DisputeSplitConservesValue(uint128 amount, uint16 bps) public {
        amount = uint128(bound(amount, 1, 1e30));
        bps = uint16(bound(bps, 0, 10_000));
        usdc.mint(client, amount);
        uint128[] memory a = new uint128[](1);
        a[0] = amount;
        uint256 id = _create(a);
        vm.prank(client);
        escrow.fund(id);
        vm.prank(provider);
        escrow.raiseDispute(id, 0);
        vm.prank(arbiter);
        escrow.resolveDispute(id, 0, bps);

        uint256 p = escrow.withdrawable(address(usdc), provider);
        uint256 c = escrow.withdrawable(address(usdc), client);
        assertEq(p + c, amount, "split must sum to the milestone");
        assertEq(p, uint256(amount) * bps / 10_000);
        assertEq(escrow.withdrawable(address(usdc), arbiter), 0);
        assertEq(uint8(escrow.getAgreement(id).status), uint8(MilestoneEscrow.Status.Closed));
        _assertAccounting(address(usdc));
    }

    /// The review-period timeout opens at exactly submittedAt + reviewPeriod, not a second earlier.
    function testFuzz_ReviewTimeoutBoundary(uint64 review, uint64 wait) public {
        review = uint64(bound(review, 1 days, 30 days));
        wait = uint64(bound(wait, 0, 60 days));
        uint128[] memory a = new uint128[](1);
        a[0] = 500e6;
        vm.prank(client);
        uint256 id = escrow.createAgreement(
            provider, arbiter, IERC20(address(usdc)), a, review, uint64(block.timestamp + 365 days), TERMS
        );
        vm.prank(client);
        escrow.fund(id);
        _submit(id, 0);
        vm.warp(block.timestamp + wait);
        vm.prank(provider);
        if (wait < review) {
            vm.expectRevert(MilestoneEscrow.ReviewPeriodNotOver.selector);
            escrow.releaseAfterReview(id, 0);
        } else {
            escrow.releaseAfterReview(id, 0);
            assertEq(escrow.withdrawable(address(usdc), provider), 500e6);
        }
    }

    /// Nobody other than the right party can move a milestone, for any caller address.
    function testFuzz_StrangersAreLockedOut(address who) public {
        vm.assume(who != client && who != provider && who != arbiter);
        uint256 id = _createFunded();
        _submit(id, 0);
        vm.startPrank(who);
        vm.expectRevert(MilestoneEscrow.NotAuthorized.selector);
        escrow.approveMilestone(id, 0);
        vm.expectRevert(MilestoneEscrow.NotAuthorized.selector);
        escrow.releaseAfterReview(id, 0);
        vm.expectRevert(MilestoneEscrow.NotAuthorized.selector);
        escrow.raiseDispute(id, 1);
        vm.expectRevert(MilestoneEscrow.NotAuthorized.selector);
        escrow.requestCancel(id);
        vm.stopPrank();
    }
}
