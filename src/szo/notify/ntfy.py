"""Push notifications through an ntfy server.
"""

from typing import Literal, TypeAlias

import requests

Priority: TypeAlias = Literal["min", "low", "default", "high", "urgent"]

EmojiTag: TypeAlias = Literal[
    "👍",  # +1
    "🥳",  # partying_face
    "🎉",  # tada
    "✔️",  # heavy_check_mark
    "📢",  # loudspeaker
    "👎",  # -1
    "⚠️",  # warning
    "🚨",  # rotating_light
    "🚩",  # triangular_flag_on_post
    "💀",  # skull
    "🤦",  # facepalm
    "⛔",  # no_entry
    "🚫",  # no_entry_sign
    "💿",  # cd
    "💻",  # computer
]

TAG_BY_EMOJI: dict[str, str] = {
    "👍": "+1",
    "🥳": "partying_face",
    "🎉": "tada",
    "✔️": "heavy_check_mark",
    "📢": "loudspeaker",
    "👎": "-1",
    "⚠️": "warning",
    "🚨": "rotating_light",
    "🚩": "triangular_flag_on_post",
    "💀": "skull",
    "🤦": "facepalm",
    "⛔": "no_entry",
    "🚫": "no_entry_sign",
    "💿": "cd",
    "💻": "computer",
}


REQUEST_TIMEOUT_SEC = 10


class Ntfy:
    """Publishes notifications to one ntfy topic."""

    def __init__(self, topic: str, server: str = "https://ntfy.sh") -> None:
        if not topic:
            raise ValueError("An ntfy topic must be a non-empty string.")
        self.url = server.rstrip('/') + "/" + topic

    def send(
        self,
        title: str,
        body: str,
        priority: Priority = "default",
        tags: list[str | EmojiTag] | None = None,
    ) -> Exception | None:
        # Bodies are always markdown. Rendered by the ntfy web app; other clients
        # show the raw text, which reads fine either way.
        headers = {"X-Title": title, "X-Priority": priority, "X-Markdown": "yes"}
        if tags:
            headers["X-Tags"] = ",".join(TAG_BY_EMOJI.get(tag, tag) for tag in tags)

        try:
            response = requests.post(
                self.url,
                data=body.encode("utf-8"),
                headers=headers,
                timeout=REQUEST_TIMEOUT_SEC,
            )
            response.raise_for_status()
            return None
        except Exception as error:
            return error
