import logging

import gevent
import pytest
import rlp
from eth.vm.forks.spurious_dragon.transactions import SpuriousDragonTransaction
from eth_utils import decode_hex, keccak, to_checksum_address
from gevent.queue import Queue
from hexbytes import HexBytes
from web3.datastructures import AttributeDict

from bridge.confirmation_sender import ConfirmationSender, make_sanity_check_transfer
from bridge.constants import HOME_CHAIN_STEP_DURATION
from bridge.utils import compute_transfer_hash


#
# Fixtures related to the confirmation sender
#
@pytest.fixture
def transfer_queue():
    """Transfer event queue used by the confirmation sender."""
    return Queue()


@pytest.fixture
def validator_key(validator_account_and_key):
    """Private key of the validator running the confirmation sender."""
    _, key = validator_account_and_key
    return key


@pytest.fixture
def max_reorg_depth():
    """Max reorg depth of the home chain used by the confirmation sender."""
    return 5


@pytest.fixture
def gas_price():
    """Gas price used by the confirmation sender for transactions on the home bridge."""
    return 1


@pytest.fixture
def confirmation_sender(
    transfer_queue,
    home_bridge_contract,
    validator_key,
    max_reorg_depth,
    gas_price,
    foreign_bridge_contract,
):
    """A confirmation sender."""
    return ConfirmationSender(
        transfer_event_queue=transfer_queue,
        home_bridge_contract=home_bridge_contract,
        private_key=validator_key.to_bytes(),
        gas_price=gas_price,
        max_reorg_depth=max_reorg_depth,
        sanity_check_transfer=make_sanity_check_transfer(
            to_checksum_address(foreign_bridge_contract.address)
        ),
    )


@pytest.fixture
def confirmation_sender_with_non_validator_account(
    transfer_queue,
    home_bridge_contract,
    non_validator_key,
    max_reorg_depth,
    gas_price,
    foreign_bridge_contract,
):
    """A confirmation sender."""
    return ConfirmationSender(
        transfer_event_queue=transfer_queue,
        home_bridge_contract=home_bridge_contract,
        private_key=non_validator_key.to_bytes(),
        gas_price=gas_price,
        max_reorg_depth=max_reorg_depth,
        sanity_check_transfer=make_sanity_check_transfer(
            to_checksum_address(foreign_bridge_contract.address)
        ),
    )


@pytest.fixture
def transfer_event():
    """An exemplary transfer event."""
    return AttributeDict(
        {
            "args": AttributeDict(
                {
                    "from": "0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf",
                    "to": "0x2946259E0334f33A064106302415aD3391BeD384",
                    "value": 1,
                }
            ),
            "event": "Transfer",
            "logIndex": 5,
            "transactionIndex": 10,
            "transactionHash": HexBytes(
                "0x66ba278660204ddd43f350e9110a8339fd32a227354429744456aac63ff9ef6f"
            ),
            "address": "0xF2E246BB76DF876Cef8b38ae84130F4F55De395b",
            "blockHash": HexBytes(
                "0x0e9226f0b8eb7b1c0b1652b8c8ce81b1790927bdaa692223ec2fb746e21063f8"
            ),
            "blockNumber": 3,
        }
    )


#
# Tests
#
def test_transfer_hash_computation(confirmation_sender, transfer_event):
    transfer_hash = compute_transfer_hash(transfer_event)
    assert transfer_event.logIndex == 5
    assert transfer_hash == keccak(transfer_event.transactionHash + b"\x05")


def test_transaction_preparation(
    confirmation_sender,
    validator_address,
    gas_price,
    home_bridge_contract,
    transfer_event,
):
    signed_transaction = confirmation_sender.sender.prepare_confirmation_transaction(
        transfer_event, nonce=1234
    )
    transaction = rlp.decode(
        bytes(signed_transaction.rawTransaction), SpuriousDragonTransaction
    )
    assert transaction.sender == decode_hex(validator_address)
    assert transaction.to == decode_hex(home_bridge_contract.address)
    assert transaction.gas_price == gas_price
    assert transaction.value == 0
    assert transaction.nonce == 1234


def test_transaction_sending(
    confirmation_sender,
    w3_home,
    tester_home,
    home_bridge_contract,
    transfer_event,
    validator_address,
):
    transaction = confirmation_sender.sender.prepare_confirmation_transaction(
        transfer_event, nonce=confirmation_sender.sender.get_next_nonce()
    )
    confirmation_sender.sender.send_confirmation_transaction(transaction)
    assert transaction == confirmation_sender.pending_transaction_queue.peek()
    tester_home.mine_block()
    receipt = w3_home.eth.getTransactionReceipt(transaction.hash)
    assert receipt is not None
    events = home_bridge_contract.events.Confirmation.getLogs(
        fromBlock=receipt.blockNumber, toBlock=receipt.blockNumber
    )
    assert len(events) == 1
    event_args = events[0].args
    assert event_args.transferHash == compute_transfer_hash(transfer_event)
    assert event_args.transactionHash == transfer_event.transactionHash
    assert event_args.amount == transfer_event.args.value
    assert event_args.recipient == transfer_event.args["from"]
    assert event_args.validator == validator_address


def test_transfers_are_handled(
    confirmation_sender,
    w3_home,
    tester_home,
    transfer_queue,
    transfer_event,
    home_bridge_contract,
    spawn,
):
    spawn(confirmation_sender.run)
    latest_block_number = w3_home.eth.blockNumber
    transfer_queue.put(transfer_event)

    gevent.sleep(0.01)

    events = home_bridge_contract.events.Confirmation.createFilter(
        fromBlock=latest_block_number
    ).get_all_entries()
    print("EVENTS", events)
    assert len(events) == 1


def test_pending_transfers_are_cleared(
    confirmation_sender,
    tester_home,
    transfer_queue,
    transfer_event,
    max_reorg_depth,
    caplog,
    spawn,
):
    caplog.set_level(logging.INFO)

    def confirmed():
        for rec in caplog.records:
            if rec.message.startswith("Transaction confirmed:"):
                return True
        return False

    spawn(confirmation_sender.run)
    transfer_queue.put(transfer_event)
    gevent.sleep(0.01)

    tester_home.mine_block()
    gevent.sleep(
        1.5 * HOME_CHAIN_STEP_DURATION
    )  # wait until they have a chance to check

    assert not confirmed()

    tester_home.mine_blocks(max_reorg_depth - 1)
    gevent.sleep(1.5 * HOME_CHAIN_STEP_DURATION)

    assert confirmed()
