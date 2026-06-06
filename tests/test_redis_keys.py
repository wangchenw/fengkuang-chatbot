from shared import redis_keys


def test_match_scoped_redis_keys_are_stable() -> None:
    match_id = "123"

    assert redis_keys.state_key(match_id) == "live:123:state"
    assert redis_keys.bots_key(match_id) == "live:123:bots"
    assert redis_keys.messages_key(match_id) == "live:123:messages"
    assert redis_keys.context_key(match_id) == "live:123:context"
    assert redis_keys.dedup_key(match_id) == "live:123:dedup"
    assert redis_keys.stop_key(match_id) == "live:123:stop"
    assert redis_keys.stats_key(match_id) == "live:123:stats"
