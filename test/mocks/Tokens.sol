// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";

contract MockERC20 is ERC20 {
    uint8 private immutable _dec;

    constructor(string memory n, string memory s, uint8 d) ERC20(n, s) {
        _dec = d;
    }

    function decimals() public view override returns (uint8) {
        return _dec;
    }

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }
}

/// @dev Takes a 1% fee on transfers. The escrow must refuse to be funded with it.
contract FeeOnTransferToken is MockERC20 {
    constructor() MockERC20("Fee", "FEE", 18) {}

    function _update(address from, address to, uint256 value) internal override {
        if (from != address(0) && to != address(0)) {
            uint256 fee = value / 100;
            super._update(from, address(0), fee);
            value -= fee;
        }
        super._update(from, to, value);
    }
}

/// @dev Reverts any transfer to a blacklisted address, like USDC/USDT can.
contract BlacklistToken is MockERC20 {
    mapping(address => bool) public blacklisted;
    constructor() MockERC20("Blacklist USD", "BUSD", 6) {}

    function setBlacklisted(address a, bool b) external {
        blacklisted[a] = b;
    }

    function _update(address from, address to, uint256 value) internal override {
        require(!blacklisted[to] && !blacklisted[from], "blacklisted");
        super._update(from, to, value);
    }
}

/// @dev Calls back into a target during every transfer, to probe for reentrancy.
contract ReentrantToken is MockERC20 {
    address public target;
    bytes public payload;
    bool public attackSucceeded;
    bool private _inAttack;
    constructor() MockERC20("Reentrant", "RNT", 18) {}

    function arm(address target_, bytes calldata payload_) external {
        target = target_;
        payload = payload_;
    }

    function _update(address from, address to, uint256 value) internal override {
        super._update(from, to, value);
        if (target != address(0) && !_inAttack && from != address(0)) {
            _inAttack = true;
            (bool ok,) = target.call(payload);
            if (ok) attackSucceeded = true;
            _inAttack = false;
        }
    }
}
