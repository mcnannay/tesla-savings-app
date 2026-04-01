from __future__ import annotations

import logging
from datetime import date

import requests

from app.config import Config

LOGGER = logging.getLogger(__name__)


def get_home_assistant_entity_state(entity_id: str) -> str | None:
    if not Config.HA_URL or not Config.HA_TOKEN or not entity_id:
        return None

    headers = {
        "Authorization": f"Bearer {Config.HA_TOKEN}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.get(
            f"{Config.HA_URL}/api/states/{entity_id}",
            headers=headers,
            timeout=15,
        )
        if response.status_code == 404:
            LOGGER.warning("Home Assistant entity '%s' was not found.", entity_id)
            return None
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        LOGGER.warning("Failed to read Home Assistant entity '%s': %s", entity_id, exc)
        return None
    except ValueError as exc:
        LOGGER.warning("Home Assistant returned invalid JSON for '%s': %s", entity_id, exc)
        return None

    return payload.get("state")


def get_current_gas_price_from_ha() -> float | None:
    state = get_home_assistant_entity_state(Config.HA_GAS_PRICE_ENTITY)
    if state in (None, "", "unknown", "unavailable"):
        return None

    try:
        return float(state)
    except (TypeError, ValueError):
        return None


def build_price_snapshot() -> tuple[date, float] | None:
    price = get_current_gas_price_from_ha()
    if price is None:
        return None
    return (date.today(), price)
