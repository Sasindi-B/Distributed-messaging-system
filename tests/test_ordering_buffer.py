import time

from ds_messaging.time.ordering import MessageOrderingBuffer, TimedMessage


def _make_message(msg_id: str, corrected: float, received: float) -> TimedMessage:
    return TimedMessage(
        msg_id=msg_id,
        sender="sensor",
        recipient="client",
        payload="data",
        original_timestamp=corrected,
        corrected_timestamp=corrected,
        receive_timestamp=received,
        sequence_number=None,
        vector_clock=None,
    )


def test_out_of_order_messages_delivered_in_timestamp_order() -> None:
    buffer = MessageOrderingBuffer(buffer_timeout=0.1)
    now = time.time()

    msg_a = _make_message("a", corrected=now + 2, received=now)
    msg_b = _make_message("b", corrected=now + 1, received=now)

    assert buffer.add_message(msg_a)
    assert buffer.add_message(msg_b)

    deliverable = buffer.get_deliverable_messages(current_time=now + 1.0)
    assert [m.msg_id for m in deliverable] == ["b", "a"]


def test_duplicate_messages_are_ignored() -> None:
    buffer = MessageOrderingBuffer()
    now = time.time()
    msg = _make_message("dup", corrected=now, received=now)

    assert buffer.add_message(msg)
    deliverable = buffer.get_deliverable_messages(current_time=now + 10)
    assert [m.msg_id for m in deliverable] == ["dup"]
    # Once delivered, the buffer should treat the message as duplicate
    assert not buffer.add_message(msg)
