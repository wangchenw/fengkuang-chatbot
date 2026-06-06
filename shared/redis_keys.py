def state_key(match_id: str) -> str:
    return f"live:{match_id}:state"


def bots_key(match_id: str) -> str:
    return f"live:{match_id}:bots"


def messages_key(match_id: str) -> str:
    return f"live:{match_id}:messages"


def context_key(match_id: str) -> str:
    return f"live:{match_id}:context"


def dedup_key(match_id: str) -> str:
    return f"live:{match_id}:dedup"


def stop_key(match_id: str) -> str:
    return f"live:{match_id}:stop"


def stats_key(match_id: str) -> str:
    return f"live:{match_id}:stats"
