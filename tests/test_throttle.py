import httpx

from header_emulator.config import RetryConfig, ThrottleConfig
from header_emulator.throttle import ThrottleController


def test_backoff_with_jitter_and_server_hint():
    retry = RetryConfig(max_attempts=3, backoff_factor=1.0, jitter_seconds=1.0)
    throttle = ThrottleConfig(enabled=True, max_delay_seconds=5.0, use_server_hints=True)

    controller = ThrottleController(retry, throttle, random_fn=lambda: 0.5)
    response = httpx.Response(429, headers={"Retry-After": "2"})

    delay = controller.backoff_delay(attempt=2, response=response)

    # base: 1 * 2^(2-1) = 2, jitter adds 0.5, server hint raises to 2 (already higher)
    assert 2.49 <= delay <= 2.51


def test_throttle_delay_respects_retry_after():
    retry = RetryConfig()
    throttle = ThrottleConfig(enabled=True, base_delay_seconds=0.2, max_delay_seconds=2.0, use_server_hints=True)

    controller = ThrottleController(retry, throttle)
    response = httpx.Response(200, headers={"Retry-After": "1.5"})

    delay = controller.throttle_delay(response)
    assert delay == 1.5


def test_throttle_disabled_returns_zero():
    controller = ThrottleController(
        RetryConfig(jitter_seconds=0.0),
        ThrottleConfig(enabled=False),
    )
    assert controller.throttle_delay() == 0.0
    assert controller.backoff_delay(1) == 0.5
