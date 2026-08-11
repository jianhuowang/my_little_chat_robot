import hashlib
from typing import Literal


REQUEST_TEXT = "来只千早爱音"


def matches_request(
    message_type: Literal["private", "group"],
    text: str,
    *,
    is_self: bool,
) -> bool:
    if is_self:
        return False
    normalized = text.strip()
    if message_type == "private":
        if normalized.startswith("/"):
            normalized = normalized[1:]
        return normalized == REQUEST_TEXT
    if message_type == "group":
        return REQUEST_TEXT in normalized
    return False


def hash_session(unified_msg_origin: str) -> str:
    return hashlib.sha256(unified_msg_origin.encode("utf-8")).hexdigest()
