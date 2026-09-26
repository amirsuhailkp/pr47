from datetime import datetime, timedelta, timezone

from alerts.telegram.delivery_queue import DeliveryQueue

NOW = datetime.now(timezone.utc)


def test_enqueue_and_due_immediately():
    q = DeliveryQueue()
    q.enqueue(1, {"text": "hi"})
    due = q.due(NOW)
    assert len(due) == 1
    assert due[0].alert_row_id == 1


def test_record_success_removes_from_queue():
    q = DeliveryQueue()
    q.enqueue(1, {"text": "hi"})
    q.record_success(1)
    assert q.pending_count() == 0
    assert q.due(NOW) == []


def test_record_failure_schedules_backoff_retry():
    q = DeliveryQueue(base_backoff_seconds=10.0, max_backoff_seconds=1000.0, max_attempts=5)
    q.enqueue(1, {"text": "hi"})
    still_pending = q.record_failure(1, NOW)
    assert still_pending is True
    assert q.due(NOW) == []  # not due yet
    later = NOW + timedelta(seconds=11)
    assert len(q.due(later)) == 1


def test_record_failure_gives_up_after_max_attempts():
    q = DeliveryQueue(base_backoff_seconds=1.0, max_attempts=2)
    q.enqueue(1, {"text": "hi"})
    assert q.record_failure(1, NOW) is True
    assert q.record_failure(1, NOW) is False
    assert q.pending_count() == 0


def test_record_failure_on_unknown_id_is_noop():
    q = DeliveryQueue()
    assert q.record_failure(999, NOW) is False
