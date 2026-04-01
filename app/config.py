import os
from pathlib import Path


def _as_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


class Config:
    APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
    APP_PORT = int(os.getenv("APP_PORT", "5000"))
    APP_SECRET_KEY = os.getenv("APP_SECRET_KEY", "change_me")
    TZ = os.getenv("TZ", "America/Los_Angeles")

    TESLAMATE_DB_HOST = os.getenv("TESLAMATE_DB_HOST", "database")
    TESLAMATE_DB_PORT = int(os.getenv("TESLAMATE_DB_PORT", "5432"))
    TESLAMATE_DB_NAME = os.getenv("TESLAMATE_DB_NAME", "teslamate")
    TESLAMATE_DB_USER = os.getenv("TESLAMATE_DB_USER", "teslamate")
    TESLAMATE_DB_PASSWORD = os.getenv("TESLAMATE_DB_PASSWORD", "")
    TESLAMATE_DISTANCE_IN_KM = _as_bool(os.getenv("TESLAMATE_DISTANCE_IN_KM", "true"), True)

    GAS_VEHICLE_MPG = float(os.getenv("GAS_VEHICLE_MPG", "24"))
    CURRENCY_SYMBOL = os.getenv("CURRENCY_SYMBOL", "$")
    DISTANCE_UNIT = os.getenv("DISTANCE_UNIT", "mi")

    HA_URL = os.getenv("HA_URL", "").rstrip("/")
    HA_TOKEN = os.getenv("HA_TOKEN", "")
    HA_GAS_PRICE_ENTITY = os.getenv("HA_GAS_PRICE_ENTITY", "")

    MQTT_HOST = os.getenv("MQTT_HOST", "")
    MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
    MQTT_USERNAME = os.getenv("MQTT_USERNAME", "")
    MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")
    MQTT_BASE_TOPIC = os.getenv("MQTT_BASE_TOPIC", "tesla_savings")
    MQTT_DISCOVERY_PREFIX = os.getenv("MQTT_DISCOVERY_PREFIX", "homeassistant")

    DATA_DIR = Path(os.getenv("APP_DATA_DIR", "/app/data"))
    SQLITE_PATH = DATA_DIR / "tesla_savings.sqlite3"

    PRICE_FETCH_HOUR = int(os.getenv("PRICE_FETCH_HOUR", "5"))
    PRICE_FETCH_MINUTE = int(os.getenv("PRICE_FETCH_MINUTE", "15"))

    APP_TITLE = os.getenv("APP_TITLE", "Tesla Savings App")
