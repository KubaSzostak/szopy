# Demo: application config loaded from CLI arguments, environment variables, and .env.
# Uses szo only — no third-party dependencies, no argparse.
#
# Every setting can be provided three ways (argv > env > .env > default):
#
#     python config_demo.py --help
#
#     python config_demo.py --region admin --custom-nested-prefix-password s3cret \
#         --api-client-id my-client --api-client-secret api-s3cret \
#         --api-subscription-id 0000-1111
#
#     export CUSTOM_NESTED_PREFIX_PASSWORD=s3cret
#     export API_CLIENT_ID=my-client
#
#     echo "REGION=admin" >> .env

from typing import Annotated, Literal

from szo import BaseConfig, Secret


class DbConfig(BaseConfig):
    host: Annotated[str, "PostgreSQL server host"] = "localhost"
    port: Annotated[int, "PostgreSQL server port"] = 5432
    dbname: Annotated[str, "database name"] = "postgres"
    user: Annotated[str, "database user"] = "postgres"
    password: Annotated[Secret[str], "database password"]
    connection_timeout_in_milliseconds: int = 30000

    def connection_string(self) -> str:
        return (
            f"host={self.host} port={self.port} dbname={self.dbname} "
            f"user={self.user} password={self.password}"
        )


class ApiConfig(BaseConfig):
    client_id: Annotated[str, "API client id"]
    client_secret: Annotated[Secret[str], "API client secret"]
    subscription_id: Annotated[str, "API subscription id"]


class AppConfig(BaseConfig):
    """Demo application config: PostgreSQL connection plus external API credentials."""

    verbose: bool = False
    region: Literal["admin", "postcode", "cresta", "nuts"]

    db: DbConfig = DbConfig(env_prefix="CUSTOM_NESTED_PREFIX", arg_prefix="--custom-nested-prefix")
    api: ApiConfig


def main() -> None:
    # Construction overlays argv > env > .env > defaults; nothing prints or
    # exits yet — the application decides what to do with problems.
    config = AppConfig(dotenv=".env")

    print("---- print_help ----")
    config.print_help()

    print("\n---- print_config ----")
    config.print_config()

    print("\n---- print_errors ----")
    config.print_errors()

    # The everyday pattern: --help exits 0, config errors exit 2, otherwise continue.
    print("\n---- validate_or_exit ----")
    config.validate_or_exit()

    if config.verbose:
        # repr() masks Secret settings — the whole config is safe to print or log.
        print(f"config: {config!r}")
    print(f"connecting: {config.db.connection_string().replace(config.db.password, '***')}")


if __name__ == "__main__":
    main()
