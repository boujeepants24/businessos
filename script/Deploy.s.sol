// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {Script, console2} from "forge-std/Script.sol";
import {MilestoneEscrow} from "../src/MilestoneEscrow.sol";
import {MockERC20} from "../test/mocks/Tokens.sol";

/// Testnet deployment: the escrow plus a mintable test stablecoin for demos.
///   forge script script/Deploy.s.sol --rpc-url $SEPOLIA_RPC_URL --account deployer --broadcast --verify
/// Refuses to run on Ethereum mainnet. This contract is not audited.
contract Deploy is Script {
    function run() external returns (MilestoneEscrow escrow, MockERC20 testUsd) {
        require(block.chainid != 1, "Not audited: refusing to deploy to mainnet");
        vm.startBroadcast();
        escrow = new MilestoneEscrow();
        testUsd = new MockERC20("Test USD", "tUSD", 6);
        vm.stopBroadcast();
        console2.log("MilestoneEscrow:", address(escrow));
        console2.log("Test USD:", address(testUsd));
    }
}
