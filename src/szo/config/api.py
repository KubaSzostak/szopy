from typing import Annotated
from szo.config.base_config import BaseConfig
from szo.config.annotations import Secret


class OAuthClientConfig(BaseConfig):
    client_id: Annotated[str, "OAuth client id"]
    client_secret: Annotated[Secret[str], "OAuth client secret"]


class AzureConfig(OAuthClientConfig):
    subscription_id: Annotated[str, "Azure subscription id"]
    tenant_id: Annotated[str, "Azure tenant (directory) id"]
