from typing import Annotated

from szo.config.annotations import Secret
from szo.config.base_config import BaseConfig


class NtfyConfig(BaseConfig):
    topic: Annotated[str, "ntfy topic to publish to; blank disables notifications"] = ""
    server: Annotated[str, "ntfy server base URL"] = "https://ntfy.sh"
