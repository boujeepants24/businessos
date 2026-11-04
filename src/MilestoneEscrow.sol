// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/// @title MilestoneEscrow
/// @notice Milestone-based escrow for client/provider work agreements, with a neutral arbiter for disputes.
///
///         Lifecycle of one agreement:
///           create (client) → fund (client) → per milestone: submit (provider) → approve (client)
///                                                                    ↘ reject → resubmit
///                                                                    ↘ review period passes → provider claims
///                                                                    ↘ dispute (either) → arbiter splits
///           missed deadline on an unsubmitted milestone → client refund
///           both parties agree to cancel → everything not yet settled or disputed is refunded
///
///         Funds are never pushed: settlements credit `withdrawable`, and each party pulls with `withdraw`.
///         A recipient that cannot receive (e.g. a blacklisted address) therefore cannot block anyone else.
///
/// @dev    Accounting invariant, per token: token.balanceOf(this) == totalLocked[token] + totalWithdrawable[token].
///         Only plain ERC-20s are supported; fee-on-transfer and rebasing tokens are rejected at funding time.
///         NOT AUDITED. Do not use with real funds.
contract MilestoneEscrow is ReentrancyGuard {
    using SafeERC20 for IERC20;

    enum Status {
        None,
        Created,
        Active,
        Closed
    }
    enum MilestoneState {
        Pending,
        Submitted,
        Released,
        Refunded,
        Disputed,
        Resolved
    }

    struct Agreement {
        address client;
        address provider;
        address arbiter;
        IERC20 token;
        uint64 reviewPeriod; // seconds the client has to respond to a submission
        uint64 deadline; // after this, unsubmitted milestones can be refunded to the client
        Status status;
        bool clientWantsCancel;
        bool providerWantsCancel;
        uint8 milestoneCount;
        uint128 total; // sum of milestone amounts
        uint128 settled; // sum of milestone amounts that are released, refunded or resolved
        bytes32 termsHash; // hash of the off-chain statement of work
    }

    struct Milestone {
        uint128 amount;
        MilestoneState state;
        uint64 submittedAt;
        bytes32 deliverableHash;
    }

    uint256 public constant MAX_MILESTONES = 20;
    uint64 public constant MIN_REVIEW_PERIOD = 1 days;
    uint64 public constant MAX_REVIEW_PERIOD = 30 days;
    uint16 public constant BPS = 10_000;

    uint256 public agreementCount;
    mapping(uint256 id => Agreement) private _agreements;
    mapping(uint256 id => mapping(uint256 index => Milestone)) private _milestones;
    mapping(address token => mapping(address account => uint256)) public withdrawable;
    mapping(address token => uint256) public totalLocked;
    mapping(address token => uint256) public totalWithdrawable;

    event AgreementCreated(
        uint256 indexed id,
        address indexed client,
        address indexed provider,
        address arbiter,
        address token,
        uint256 total,
        uint64 deadline,
        bytes32 termsHash
    );
    event AgreementFunded(uint256 indexed id, uint256 amount);
    event AgreementCancelled(uint256 indexed id);
    event CancelRequested(uint256 indexed id, address indexed by);
    event AgreementClosed(uint256 indexed id);
    event MilestoneSubmitted(uint256 indexed id, uint256 indexed index, bytes32 deliverableHash);
    event MilestoneRejected(uint256 indexed id, uint256 indexed index, bytes32 reasonHash);
    event MilestoneReleased(uint256 indexed id, uint256 indexed index, uint256 amount, bool byTimeout);
    event MilestoneRefunded(uint256 indexed id, uint256 indexed index, uint256 amount);
    event DisputeRaised(uint256 indexed id, uint256 indexed index, address indexed by);
    event DisputeResolved(uint256 indexed id, uint256 indexed index, uint256 toProvider, uint256 toClient);
    event Withdrawn(address indexed token, address indexed account, uint256 amount);

    error InvalidParams();
    error NotAuthorized();
    error WrongStatus();
    error WrongMilestoneState();
    error InvalidMilestone();
    error ReviewPeriodNotOver();
    error DeadlineNotPassed();
    error UnsupportedToken();
    error NothingToWithdraw();

    // ------------------------------------------------------------------ setup

    /// @notice Client creates an agreement. Nothing moves until `fund`.
    function createAgreement(
        address provider,
        address arbiter,
        IERC20 token,
        uint128[] calldata amounts,
        uint64 reviewPeriod,
        uint64 deadline,
        bytes32 termsHash
    ) external returns (uint256 id) {
        uint256 n = amounts.length;
        if (
            provider == address(0) || arbiter == address(0) || address(token) == address(0) || provider == msg.sender
                || arbiter == msg.sender || arbiter == provider || n == 0 || n > MAX_MILESTONES
                || reviewPeriod < MIN_REVIEW_PERIOD || reviewPeriod > MAX_REVIEW_PERIOD || deadline <= block.timestamp
        ) revert InvalidParams();

        id = ++agreementCount;
        uint256 total;
        for (uint256 i; i < n; ++i) {
            if (amounts[i] == 0) revert InvalidParams();
            total += amounts[i];
            _milestones[id][i].amount = amounts[i];
        }
        if (total > type(uint128).max) revert InvalidParams();

        _agreements[id] = Agreement({
            client: msg.sender,
            provider: provider,
            arbiter: arbiter,
            token: token,
            reviewPeriod: reviewPeriod,
            deadline: deadline,
            status: Status.Created,
            clientWantsCancel: false,
            providerWantsCancel: false,
            // forge-lint: disable-next-line(unsafe-typecast)
            milestoneCount: uint8(n), // n <= MAX_MILESTONES (20), checked above
            // forge-lint: disable-next-line(unsafe-typecast)
            total: uint128(total), // checked against type(uint128).max above
            settled: 0,
            termsHash: termsHash
        });
        emit AgreementCreated(id, msg.sender, provider, arbiter, address(token), total, deadline, termsHash);
    }

    /// @notice Client deposits the full agreement amount. Requires prior ERC-20 approval.
    function fund(uint256 id) external nonReentrant {
        Agreement storage a = _agreements[id];
        if (msg.sender != a.client) revert NotAuthorized();
        if (a.status != Status.Created) revert WrongStatus();

        a.status = Status.Active;
        totalLocked[address(a.token)] += a.total;

        uint256 before = a.token.balanceOf(address(this));
        a.token.safeTransferFrom(msg.sender, address(this), a.total);
        if (a.token.balanceOf(address(this)) - before != a.total) revert UnsupportedToken();
        emit AgreementFunded(id, a.total);
    }

    /// @notice Client abandons an agreement that was never funded.
    function cancelUnfunded(uint256 id) external {
        Agreement storage a = _agreements[id];
        if (msg.sender != a.client) revert NotAuthorized();
        if (a.status != Status.Created) revert WrongStatus();
        a.status = Status.Closed;
        emit AgreementCancelled(id);
    }

    // ------------------------------------------------------------------ milestone flow

    function submitMilestone(uint256 id, uint256 index, bytes32 deliverableHash) external {
        (Agreement storage a, Milestone storage m) = _active(id, index);
        if (msg.sender != a.provider) revert NotAuthorized();
        if (m.state != MilestoneState.Pending) revert WrongMilestoneState();
        m.state = MilestoneState.Submitted;
        // forge-lint: disable-next-line(unsafe-typecast)
        m.submittedAt = uint64(block.timestamp); // fits until year 2^64 seconds
        m.deliverableHash = deliverableHash;
        emit MilestoneSubmitted(id, index, deliverableHash);
    }

    function approveMilestone(uint256 id, uint256 index) external {
        (Agreement storage a, Milestone storage m) = _active(id, index);
        if (msg.sender != a.client) revert NotAuthorized();
        if (m.state != MilestoneState.Submitted) revert WrongMilestoneState();
        _settle(id, a, m, MilestoneState.Released, m.amount);
        emit MilestoneReleased(id, index, m.amount, false);
    }

    /// @notice Client sends a submission back for more work. The provider can resubmit or dispute.
    function rejectMilestone(uint256 id, uint256 index, bytes32 reasonHash) external {
        (Agreement storage a, Milestone storage m) = _active(id, index);
        if (msg.sender != a.client) revert NotAuthorized();
        if (m.state != MilestoneState.Submitted) revert WrongMilestoneState();
        m.state = MilestoneState.Pending;
        m.submittedAt = 0;
        emit MilestoneRejected(id, index, reasonHash);
    }

    /// @notice Provider is paid if the client ignores a submission for the whole review period.
    function releaseAfterReview(uint256 id, uint256 index) external {
        (Agreement storage a, Milestone storage m) = _active(id, index);
        if (msg.sender != a.provider) revert NotAuthorized();
        if (m.state != MilestoneState.Submitted) revert WrongMilestoneState();
        if (block.timestamp < uint256(m.submittedAt) + a.reviewPeriod) revert ReviewPeriodNotOver();
        _settle(id, a, m, MilestoneState.Released, m.amount);
        emit MilestoneReleased(id, index, m.amount, true);
    }

    /// @notice Client is refunded for a milestone the provider never submitted before the deadline.
    function refundAfterDeadline(uint256 id, uint256 index) external {
        (Agreement storage a, Milestone storage m) = _active(id, index);
        if (msg.sender != a.client) revert NotAuthorized();
        if (m.state != MilestoneState.Pending) revert WrongMilestoneState();
        if (block.timestamp <= a.deadline) revert DeadlineNotPassed();
        _settle(id, a, m, MilestoneState.Refunded, 0);
        emit MilestoneRefunded(id, index, m.amount);
    }

    // ------------------------------------------------------------------ disputes

    function raiseDispute(uint256 id, uint256 index) external {
        (Agreement storage a, Milestone storage m) = _active(id, index);
        if (msg.sender != a.client && msg.sender != a.provider) revert NotAuthorized();
        if (m.state != MilestoneState.Pending && m.state != MilestoneState.Submitted) revert WrongMilestoneState();
        m.state = MilestoneState.Disputed;
        emit DisputeRaised(id, index, msg.sender);
    }

    /// @notice Arbiter splits a disputed milestone. The arbiter can never receive funds.
    function resolveDispute(uint256 id, uint256 index, uint16 providerBps) external {
        Agreement storage a = _agreements[id];
        if (a.status != Status.Active) revert WrongStatus();
        if (index >= a.milestoneCount) revert InvalidMilestone();
        Milestone storage m = _milestones[id][index];
        if (msg.sender != a.arbiter) revert NotAuthorized();
        if (m.state != MilestoneState.Disputed) revert WrongMilestoneState();
        if (providerBps > BPS) revert InvalidParams();

        uint256 toProvider = (uint256(m.amount) * providerBps) / BPS;
        _settle(id, a, m, MilestoneState.Resolved, toProvider);
        emit DisputeResolved(id, index, toProvider, m.amount - toProvider);
    }

    // ------------------------------------------------------------------ mutual cancellation

    /// @notice Both parties must call this. Once both have, every milestone that is still Pending or
    ///         Submitted is refunded to the client. Disputed milestones stay with the arbiter.
    function requestCancel(uint256 id) external {
        Agreement storage a = _agreements[id];
        if (a.status != Status.Active) revert WrongStatus();
        if (msg.sender == a.client) a.clientWantsCancel = true;
        else if (msg.sender == a.provider) a.providerWantsCancel = true;
        else revert NotAuthorized();
        emit CancelRequested(id, msg.sender);
        if (!(a.clientWantsCancel && a.providerWantsCancel)) return;

        emit AgreementCancelled(id);
        uint256 n = a.milestoneCount;
        for (uint256 i; i < n; ++i) {
            Milestone storage m = _milestones[id][i];
            if (m.state == MilestoneState.Pending || m.state == MilestoneState.Submitted) {
                _settle(id, a, m, MilestoneState.Refunded, 0);
                emit MilestoneRefunded(id, i, m.amount);
                if (a.status == Status.Closed) break;
            }
        }
    }

    // ------------------------------------------------------------------ withdrawals

    function withdraw(IERC20 token) external nonReentrant {
        uint256 amount = withdrawable[address(token)][msg.sender];
        if (amount == 0) revert NothingToWithdraw();
        withdrawable[address(token)][msg.sender] = 0;
        totalWithdrawable[address(token)] -= amount;
        token.safeTransfer(msg.sender, amount);
        emit Withdrawn(address(token), msg.sender, amount);
    }

    // ------------------------------------------------------------------ views

    function getAgreement(uint256 id) external view returns (Agreement memory) {
        return _agreements[id];
    }

    function getMilestone(uint256 id, uint256 index) external view returns (Milestone memory) {
        return _milestones[id][index];
    }

    function getMilestones(uint256 id) external view returns (Milestone[] memory list) {
        uint256 n = _agreements[id].milestoneCount;
        list = new Milestone[](n);
        for (uint256 i; i < n; ++i) {
            list[i] = _milestones[id][i];
        }
    }

    // ------------------------------------------------------------------ internals

    function _active(uint256 id, uint256 index) private view returns (Agreement storage a, Milestone storage m) {
        a = _agreements[id];
        if (a.status != Status.Active) revert WrongStatus();
        if (index >= a.milestoneCount) revert InvalidMilestone();
        m = _milestones[id][index];
    }

    /// @dev Moves one milestone's amount out of escrow: `toProvider` to the provider, the rest to the client.
    ///      Pure bookkeeping (no external calls), so it is safe to call from any function.
    function _settle(uint256 id, Agreement storage a, Milestone storage m, MilestoneState newState, uint256 toProvider)
        private
    {
        uint256 amount = m.amount;
        uint256 toClient = amount - toProvider;
        address token = address(a.token);

        m.state = newState;
        // forge-lint: disable-next-line(unsafe-typecast)
        a.settled += uint128(amount); // amount was read from a uint128 field
        totalLocked[token] -= amount;
        totalWithdrawable[token] += amount;
        if (toProvider > 0) withdrawable[token][a.provider] += toProvider;
        if (toClient > 0) withdrawable[token][a.client] += toClient;

        if (a.settled == a.total) {
            a.status = Status.Closed;
            emit AgreementClosed(id);
        }
    }
}
