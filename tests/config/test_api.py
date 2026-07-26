from szo import AzureConfig, BaseConfig, OAuthClientConfig

OAUTH_ARGS = {"--client-id": "cid", "--client-secret": "cs"}
AZURE_ARGS = {**OAUTH_ARGS, "--tenant-id": "tid", "--subscription-id": "sid"}


class TestOAuthClientConfig:
    def test_both_settings_required(self):
        assert OAuthClientConfig(args={}, environ={}, dotenv={}).is_valid() is False

    def test_loads_values(self):
        config = OAuthClientConfig(args=OAUTH_ARGS, environ={}, dotenv={})
        assert config.is_valid()
        assert config.client_id == "cid"
        assert config.client_secret == "cs"

    def test_client_secret_is_secret(self):
        config = OAuthClientConfig(args=OAUTH_ARGS, environ={}, dotenv={})
        assert config._settings["client_id"].annotation.is_secret is False
        assert config._settings["client_secret"].annotation.is_secret is True


class TestAzureConfig:
    def test_inherits_oauth_settings_and_adds_azure_ones(self):
        config = AzureConfig(args=AZURE_ARGS, environ={}, dotenv={})
        assert config.is_valid()
        assert config.client_id == "cid"
        assert config.client_secret == "cs"
        assert config.tenant_id == "tid"
        assert config.subscription_id == "sid"

    def test_setting_order_base_first(self):
        config = AzureConfig(args=AZURE_ARGS, environ={}, dotenv={})
        assert list(config._settings) == ["client_id", "client_secret", "subscription_id", "tenant_id"]

    def test_nested_env_names_match_azure_sdk_convention(self):
        class AppConfig(BaseConfig):
            azure: AzureConfig

        environ = {
            "AZURE_CLIENT_ID": "cid",
            "AZURE_CLIENT_SECRET": "cs",
            "AZURE_SUBSCRIPTION_ID": "sid",
            "AZURE_TENANT_ID": "tid",
        }
        app = AppConfig(args={}, environ=environ, dotenv={})
        assert app.is_valid()
        assert app.azure.tenant_id == "tid"
        env_names = [setting.binding.env_name for setting in app.get_settings()]
        assert env_names == list(environ)
