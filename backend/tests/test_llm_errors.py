from app.llm_errors import invoke_with_retry, rate_limited


def test_rate_limited_detects_429():
    assert rate_limited(Exception("HTTP 429 Too Many Requests"))


def test_rate_limited_ignores_unrelated_errors():
    assert not rate_limited(Exception("connection timeout"))
    assert not rate_limited(ValueError("invalid SQL syntax"))


def test_invoke_with_retry_succeeds_after_rate_limit():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        if calls["n"] < 2:
            raise Exception("429 Resource Exhausted")
        return "ok"

    assert invoke_with_retry(fn, max_attempts=3, base_delay_seconds=0.01) == "ok"
    assert calls["n"] == 2
