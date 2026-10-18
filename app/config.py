"""Settings, read from environment variables prefixed `MATCHER_` (or a `.env` file)."""

from typing import Annotated, Any

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.domain.models import Platform


class Settings(BaseSettings):
    # An empty variable counts as unset, so a blank MATCHER_PROXY_URL can't hide the one under its old name.
    model_config = SettingsConfigDict(
        env_prefix="MATCHER_", env_file=".env", extra="ignore", populate_by_name=True, env_ignore_empty=True
    )

    demo: bool = False  # serve the bundled sample results instead of searching the shops
    fetch_timeout_s: float = 15.0  # one HTTP request
    platform_timeout_s: float = 45.0  # everything done for one shop: searches and product pages
    croma_pincode: str = Field(default="400001", pattern=r"^[1-9]\d{5}$")  # Croma's stock is per pincode
    croma_inventory_key: str | None = None  # Croma's stock-check key; read from Croma's own script if unset
    product_cache_ttl_s: float = 24 * 60 * 60  # an Amazon product's details rarely change within a day
    result_cache_ttl_s: float = 30 * 60  # a shop's answer, including stock, is reused for half an hour
    cache_max_entries: int = 1000
    # Some shops refuse servers outside India, or serve them empty pages (Flipkart, Myntra). With a proxy set
    # (e.g. ZenRows or Bright Data, targeted to India), those shops' requests, and only theirs, go through it.
    # MATCHER_FLIPKART_PROXY_URL is the setting's first name, still read so existing deployments keep working.
    proxy_url: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("MATCHER_PROXY_URL", "MATCHER_FLIPKART_PROXY_URL")
    )
    proxy_ca_path: str | None = Field(  # the proxy's CA certificate; unset, the proxy isn't verified
        default=None, validation_alias=AliasChoices("MATCHER_PROXY_CA_PATH", "MATCHER_FLIPKART_PROXY_CA_PATH")
    )
    proxy_timeout_s: float = 30.0  # such proxies retry for us, so one request can take longer
    # A shop behind the proxy needs a search and up to a dozen product pages, each several seconds slower.
    proxied_platform_timeout_s: float = 90.0
    proxy_max_per_host: int = Field(default=4, ge=1)  # a shop's batch of product pages, fetched at once
    proxied_shops: Annotated[tuple[Platform, ...], NoDecode] = (Platform.FLIPKART, Platform.MYNTRA)

    @field_validator("proxied_shops", mode="before")
    @classmethod
    def _comma_separated(cls, value: Any) -> Any:
        if isinstance(value, str):  # from the environment: "flipkart,myntra"
            return tuple(name.strip().lower() for name in value.split(",") if name.strip())
        return value
