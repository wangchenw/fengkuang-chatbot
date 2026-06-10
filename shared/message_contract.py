from pydantic import BaseModel


class ChatMessage(BaseModel):
    match_id: str
    bot_id: str
    bot_name: str
    content: str
    match_time: str
    event: str
    ts: int

    def to_redis_fields(self) -> dict[str, str]:
        return {
            "match_id": self.match_id,
            "bot_id": self.bot_id,
            "bot_name": self.bot_name,
            "content": self.content,
            "match_time": self.match_time,
            "event": self.event,
            "ts": str(self.ts),
        }

    def to_json_bytes(self) -> bytes:
        return self.model_dump_json().encode("utf-8")