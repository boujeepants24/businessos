// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {Test} from "forge-std/Test.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {MilestoneEscrow} from "../src/MilestoneEscrow.sol";
import {MockERC20} from "./mocks/Tokens.sol";

abstract contract BaseTest is Test {
    MilestoneEscrow internal escrow;
    MockERC20 internal usdc;

    address internal client = makeAddr("client");
    address internal provider = makeAddr("provider");
    address internal arbiter = makeAddr("arbiter");
    address internal stranger = makeAddr("stranger");

    uint64 internal constant REVIEW = 7 days;
    bytes32 internal constant TERMS = keccak256("Website rebuild, 3 milestones");

    function setUp() public virtual {
        escrow = new MilestoneEscrow();
        usdc = new MockERC20("USD Coin", "USDC", 6);
        usdc.mint(client, 1_000_000e6);
        vm.prank(client);
        usdc.approve(address(escrow), type(uint256).max);
    }

    function _amounts3() internal pure returns (uint128[] memory a) {
        a = new uint128[](3);
        a[0] = 1_000e6;
        a[1] = 2_000e6;
        a[2] = 3_000e6;
    }

    function _create(uint128[] memory amounts) internal returns (uint256 id) {
        vm.prank(client);
        id = escrow.createAgreement(
            provider, arbiter, IERC20(address(usdc)), amounts, REVIEW, uint64(block.timestamp + 60 days), TERMS
        );
    }

    function _createFunded() internal returns (uint256 id) {
        id = _create(_amounts3());
        vm.prank(client);
        escrow.fund(id);
    }

    function _submit(uint256 id, uint256 i) internal {
        vm.prank(provider);
        escrow.submitMilestone(id, i, keccak256(abi.encode("deliverable", i)));
    }

    function _state(uint256 id, uint256 i) internal view returns (MilestoneEscrow.MilestoneState) {
        return escrow.getMilestone(id, i).state;
    }

    /// The accounting invariant, checked after every scenario.
    function _assertAccounting(address token) internal view {
        assertEq(
            IERC20(token).balanceOf(address(escrow)),
            escrow.totalLocked(token) + escrow.totalWithdrawable(token),
            "balance != locked + withdrawable"
        );
    }
}
