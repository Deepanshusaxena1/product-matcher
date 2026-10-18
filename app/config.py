"""Settings, read from environment variables prefixed `MATCHER_` (or a `.env` file)."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MATCHER_", env_file=".env", extra="ignore")

    demo: bool = False  # serve the bundled sample results instead of searching the shops
    fetch_timeout_s: float = 15.0  # one HTTP request
    platform_timeout_s: float = 45.0  # everything done for one shop: searches and product pages
    croma_pincode: str = Field(default="400001", pattern=r"^[1-9]\d{5}$")  # Croma's stock is per pincode
    croma_inventory_key: str | None = None  # Croma's stock-check key; read from Croma's own script if unset
    product_cache_ttl_s: float = 24 * 60 * 60  # an Amazon product's details rarely change within a day
    result_cache_ttl_s: float = 30 * 60  # a shop's answer, including stock, is reused for half an hour
    cache_max_entries: int = 1000
