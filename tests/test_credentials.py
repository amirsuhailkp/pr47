from datetime import datetime, timedelta, timezone

from intelligence.llm.credentials import CredentialPool

NOW = datetime.now(timezone.utc)


def test_next_available_returns_first_key_by_default():
    pool = CredentialPool("groq", ["k1", "k2"])
    assert pool.next_available(NOW) == "k1"


def test_rate_limited_key_is_skipped_until_cooldown_expires():
    pool = CredentialPool("groq", ["k1", "k2"])
    pool.record_rate_limited("k1", NOW, retry_after_seconds=30)
    assert pool.next_available(NOW) == "k2"
    assert pool.next_available(NOW + timedelta(seconds=31)) == "k1"


def test_exponential_backoff_without_explicit_retry_after():
    pool = CredentialPool("groq", ["k1"], base_backoff_seconds=5.0, max_backoff_seconds=100.0)
    pool.record_rate_limited("k1", NOW)
    first_cooldown = pool._states["k1"].disabled_until
    assert first_cooldown == NOW + timedelta(seconds=5.0)

    pool.record_rate_limited("k1", NOW)
    second_cooldown = pool._states["k1"].disabled_until
    assert second_cooldown == NOW + timedelta(seconds=10.0)


def test_backoff_caps_at_max():
    pool = CredentialPool("groq", ["k1"], base_backoff_seconds=100.0, max_backoff_seconds=150.0)
    pool.record_rate_limited("k1", NOW)
    pool.record_rate_limited("k1", NOW)
    pool.record_rate_limited("k1", NOW)
    assert pool._states["k1"].disabled_until == NOW + timedelta(seconds=150.0)


def test_record_success_clears_cooldown_and_failure_count():
    pool = CredentialPool("groq", ["k1"])
    pool.record_rate_limited("k1", NOW, retry_after_seconds=100)
    pool.record_success("k1")
    assert pool.next_available(NOW) == "k1"
    assert pool._states["k1"].consecutive_failures == 0


def test_has_any_available_false_when_all_cooling_down():
    pool = CredentialPool("groq", ["k1", "k2"])
    pool.record_rate_limited("k1", NOW, retry_after_seconds=100)
    pool.record_rate_limited("k2", NOW, retry_after_seconds=100)
    assert pool.has_any_available(NOW) is False
    assert pool.next_available(NOW) is None
