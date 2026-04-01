from __future__ import annotations

import json
import logging
import re

import paho.mqtt.publish as publish

from app.config import Config

LOGGER = logging.getLogger(__name__)
_INVALID_DISCOVERY_ID = re.compile(r'[^a-zA-Z0-9_-]+')


def _auth():
    if not Config.MQTT_USERNAME:
        return None
    return {
        'username': Config.MQTT_USERNAME,
        'password': Config.MQTT_PASSWORD,
    }


def _publish_single(topic: str, payload: str, retain: bool = True) -> bool:
    if not Config.MQTT_HOST:
        return False

    try:
        publish.single(
            topic,
            payload=payload,
            hostname=Config.MQTT_HOST,
            port=Config.MQTT_PORT,
            auth=_auth(),
            qos=1,
            retain=retain,
        )
    except Exception as exc:
        LOGGER.warning("Failed to publish MQTT topic '%s': %s", topic, exc)
        return False

    return True


def _sanitize_discovery_id(value: str, fallback: str) -> str:
    cleaned = _INVALID_DISCOVERY_ID.sub('_', value).strip('_')
    return cleaned or fallback


def _metric_unique_id(name: str) -> str:
    return f'tesla_savings_{_sanitize_discovery_id(name, "metric")}'


def _device_identifier() -> str:
    base_topic = Config.MQTT_BASE_TOPIC.strip('/')
    return _sanitize_discovery_id(base_topic or 'tesla_savings', 'tesla_savings')


def _state_topic(name: str) -> str:
    base_topic = Config.MQTT_BASE_TOPIC.strip('/') or 'tesla_savings'
    return f'{base_topic}/{name}/state'


def _discovery_topic(name: str) -> str:
    discovery_prefix = Config.MQTT_DISCOVERY_PREFIX.strip('/') or 'homeassistant'
    return f'{discovery_prefix}/sensor/{_metric_unique_id(name)}/config'


def publish_metric_config(
    name: str,
    unit: str = '',
    icon: str = '',
    state_class: str | None = 'measurement',
    device_class: str | None = None,
) -> None:
    discovery_payload = {
        'name': f"Tesla Savings {name.replace('_', ' ').title()}",
        'state_topic': _state_topic(name),
        'unique_id': _metric_unique_id(name),
        'default_entity_id': f'sensor.{_metric_unique_id(name)}',
        'device': {
            'identifiers': [_device_identifier()],
            'name': Config.APP_TITLE,
            'model': 'Tesla Savings App',
        },
    }

    if icon:
        discovery_payload['icon'] = icon
    if unit:
        discovery_payload['unit_of_measurement'] = unit
    if state_class:
        discovery_payload['state_class'] = state_class
    if device_class:
        discovery_payload['device_class'] = device_class

    _publish_single(_discovery_topic(name), json.dumps(discovery_payload), retain=True)


def publish_metric_state(name: str, value) -> None:
    _publish_single(
        _state_topic(name),
        '' if value is None else str(value),
        retain=True,
    )


def publish_metric(
    name: str,
    value,
    unit: str = '',
    icon: str = '',
    state_class: str | None = 'measurement',
    device_class: str | None = None,
) -> None:
    publish_metric_config(
        name,
        unit=unit,
        icon=icon,
        state_class=state_class,
        device_class=device_class,
    )
    publish_metric_state(name, value)
