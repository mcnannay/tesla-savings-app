from __future__ import annotations

import json

import paho.mqtt.publish as publish

from app.config import Config


def _auth():
    if not Config.MQTT_USERNAME:
        return None
    return {
        "username": Config.MQTT_USERNAME,
        "password": Config.MQTT_PASSWORD,
    }


def publish_metric(name: str, value, unit: str = "", icon: str = "", state_class: str = "measurement") -> None:
    if not Config.MQTT_HOST:
        return

    base = Config.MQTT_BASE_TOPIC
    state_topic = f"{base}/{name}/state"
    discovery_topic = f"homeassistant/sensor/{base}/{name}/config"

    discovery_payload = {
        "name": f"Tesla Savings {name.replace('_', ' ').title()}",
        "state_topic": state_topic,
        "unique_id": f"tesla_savings_{name}",
        "default_entity_id": f"sensor.tesla_savings_{name}",
        "unit_of_measurement": unit,
        "icon": icon,
        "state_class": state_class,
    }

    publish.single(
        discovery_topic,
        payload=json.dumps(discovery_payload),
        hostname=Config.MQTT_HOST,
        port=Config.MQTT_PORT,
        auth=_auth(),
        retain=True,
    )

    publish.single(
        state_topic,
        payload=str(value),
        hostname=Config.MQTT_HOST,
        port=Config.MQTT_PORT,
        auth=_auth(),
        retain=True,
    )
