// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {Test} from "forge-std/Test.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {MilestoneEscrow} from "../../src/MilestoneEscrow.sol";
import {MockERC20} from "../mocks/Tokens.sol";

/// @dev Drives the escrow with random but well-formed actions from three clients, three providers and
///      one arbiter. The fuzzer calls these functions in random order with random inputs; invariants
///      are checked after every call.
contract EscrowHandler is Test {
    MilestoneEscrow public escrow;
    MockERC20 public token;

    address[3] public clients;
    address[3] public providers;
    address public arbiter;

    uint256[] public ids;
    mapping(bytes32 => uint256) public calls;

    // Ghost accounting: what the outside world has put in and taken out.
    uint256 public ghostDeposited;
    uint256 public ghostWithdrawn;

    constructor(MilestoneEscrow escrow_, MockERC20 token_) {
        escrow = escrow_;
        token = token_;
        arbiter = makeAddr("arbiter");
        for (uint256 i; i < 3; ++i) {
            clients[i] = makeAddr(string.concat("client", vm.toString(i)));
            providers[i] = makeAddr(string.concat("provider", vm.toString(i)));
            vm.prank(clients[i]);
            token.approve(address(escrow), type(uint256).max);
        }
    }

    function idCount() external view returns (uint256) {
        return ids.length;
    }

    function _pick(uint256 seed) internal view returns (uint256 id, MilestoneEscrow.Agreement memory a) {
        id = ids[seed % ids.length];
        a = escrow.getAgreement(id);
    }

    /// Finds an Active agreement with a milestone in `want`, starting the scan at a random point,
    /// so that actions hit valid targets instead of silently skipping.
    function _find(uint256 seed, MilestoneEscrow.MilestoneState want)
        internal
        view
        returns (bool found, uint256 id, uint256 i, MilestoneEscrow.Agreement memory a)
    {
        uint256 n = ids.length;
        for (uint256 k; k < n; ++k) {
            id = ids[(seed % n + k) % n];
            a = escrow.getAgreement(id);
            if (a.status != MilestoneEscrow.Status.Active) continue;
            for (uint256 j; j < a.milestoneCount; ++j) {
                i = (seed % a.milestoneCount + j) % a.milestoneCount;
                if (escrow.getMilestone(id, i).state == want) return (true, id, i, a);
            }
        }
    }

    // ---------------------------------------------------------------- actions

    function create(uint256 who, uint256 prov, uint8 count, uint256 amountSeed) external {
        address c = clients[who % 3];
        address p = providers[prov % 3];
        uint256 n = bound(count, 1, 5);
        uint128[] memory amounts = new uint128[](n);
        for (uint256 i; i < n; ++i) {
            amounts[i] = uint128(bound(uint256(keccak256(abi.encode(amountSeed, i))), 1, 1e24));
        }
        vm.prank(c);
        ids.push(
            escrow.createAgreement(
                p, arbiter, IERC20(address(token)), amounts, 3 days, uint64(block.timestamp + 20 days), bytes32(0)
            )
        );
        calls["create"]++;
    }

    function fund(uint256 seed) external {
        if (ids.length == 0) return;
        (uint256 id, MilestoneEscrow.Agreement memory a) = _pick(seed);
        if (a.status != MilestoneEscrow.Status.Created) return;
        token.mint(a.client, a.total);
        vm.prank(a.client);
        escrow.fund(id);
        ghostDeposited += a.total;
        calls["fund"]++;
    }

    function submit(uint256 seed, uint256 idx) external {
        (bool ok, uint256 id, uint256 i, MilestoneEscrow.Agreement memory a) =
            _find(seed, MilestoneEscrow.MilestoneState.Pending);
        if (!ok) return;
        vm.prank(a.provider);
        escrow.submitMilestone(id, i, bytes32(seed));
        calls["submit"]++;
    }

    function approve(uint256 seed, uint256 idx) external {
        (bool ok, uint256 id, uint256 i, MilestoneEscrow.Agreement memory a) =
            _find(seed, MilestoneEscrow.MilestoneState.Submitted);
        if (!ok) return;
        vm.prank(a.client);
        escrow.approveMilestone(id, i);
        calls["approve"]++;
    }

    function reject(uint256 seed, uint256 idx) external {
        (bool ok, uint256 id, uint256 i, MilestoneEscrow.Agreement memory a) =
            _find(seed, MilestoneEscrow.MilestoneState.Submitted);
        if (!ok) return;
        vm.prank(a.client);
        escrow.rejectMilestone(id, i, bytes32(0));
        calls["reject"]++;
    }

    function dispute(uint256 seed, uint256 idx, bool byClient) external {
        (bool ok, uint256 id, uint256 i, MilestoneEscrow.Agreement memory a) =
            _find(seed, byClient ? MilestoneEscrow.MilestoneState.Pending : MilestoneEscrow.MilestoneState.Submitted);
        if (!ok) return;
        vm.prank(byClient ? a.client : a.provider);
        escrow.raiseDispute(id, i);
        calls["dispute"]++;
    }

    function resolve(uint256 seed, uint256 idx, uint16 bps) external {
        (bool ok, uint256 id, uint256 i, MilestoneEscrow.Agreement memory a) =
            _find(seed, MilestoneEscrow.MilestoneState.Disputed);
        if (!ok) return;
        vm.prank(arbiter);
        escrow.resolveDispute(id, i, uint16(bound(bps, 0, 10_000)));
        calls["resolve"]++;
    }

    function timeoutRelease(uint256 seed, uint256 idx) external {
        (bool ok, uint256 id, uint256 i, MilestoneEscrow.Agreement memory a) =
            _find(seed, MilestoneEscrow.MilestoneState.Submitted);
        if (!ok) return;
        MilestoneEscrow.Milestone memory m = escrow.getMilestone(id, i);
        if (block.timestamp < uint256(m.submittedAt) + a.reviewPeriod) {
            vm.warp(uint256(m.submittedAt) + a.reviewPeriod);
        }
        vm.prank(a.provider);
        escrow.releaseAfterReview(id, i);
        calls["timeoutRelease"]++;
    }

    function deadlineRefund(uint256 seed, uint256 idx) external {
        (bool ok, uint256 id, uint256 i, MilestoneEscrow.Agreement memory a) =
            _find(seed, MilestoneEscrow.MilestoneState.Pending);
        if (!ok) return;
        if (block.timestamp <= a.deadline) vm.warp(uint256(a.deadline) + 1);
        vm.prank(a.client);
        escrow.refundAfterDeadline(id, i);
        calls["deadlineRefund"]++;
    }

    function cancel(uint256 seed, bool clientFirst) external {
        if (ids.length == 0) return;
        (uint256 id, MilestoneEscrow.Agreement memory a) = _pick(seed);
        if (a.status != MilestoneEscrow.Status.Active) return;
        vm.prank(clientFirst ? a.client : a.provider);
        escrow.requestCancel(id);
        a = escrow.getAgreement(id);
        if (a.status == MilestoneEscrow.Status.Active && !(a.clientWantsCancel && a.providerWantsCancel)) {
            vm.prank(clientFirst ? a.provider : a.client);
            escrow.requestCancel(id);
        }
        calls["cancel"]++;
    }

    function withdraw(uint256 who) external {
        address[7] memory everyone =
            [clients[0], clients[1], clients[2], providers[0], providers[1], providers[2], arbiter];
        address w = everyone[who % 7];
        uint256 owed = escrow.withdrawable(address(token), w);
        if (owed == 0) return;
        vm.prank(w);
        escrow.withdraw(IERC20(address(token)));
        ghostWithdrawn += owed;
        calls["withdraw"]++;
    }

    function warp(uint32 secs) external {
        vm.warp(block.timestamp + bound(secs, 0, 10 days));
    }
}
