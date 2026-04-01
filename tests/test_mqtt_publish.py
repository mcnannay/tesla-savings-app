import importlib
import json
import sys
import types
import unittest
from unittest.mock import patch

import requests

from app.config import Config
from app.homeassistant import get_home_assistant_entity_state

try:
    from app.mqtt_publish import publish_metric
except ModuleNotFoundError as exc:
    if exc.name != 'paho':
        raise

    fake_publish_module = types.ModuleType('paho.mqtt.publish')
    fake_publish_module.single = lambda *args, **kwargs: None

    fake_mqtt_module = types.ModuleType('paho.mqtt')
    fake_mqtt_module.publish = fake_publish_module

    fake_paho_module = types.ModuleType('paho')
    fake_paho_module.mqtt = fake_mqtt_module

    sys.modules['paho'] = fake_paho_module
    sys.modules['paho.mqtt'] = fake_mqtt_module
    sys.modules['paho.mqtt.publish'] = fake_publish_module

    publish_metric = importlib.import_module('app.mqtt_publish').publish_metric


class MqttPublishTests(unittest.TestCase):
    @patch('app.mqtt_publish.publish.single')
    def test_publish_metric_uses_sanitized_discovery_topic(self, mock_single):
        with (
            patch.object(Config, 'MQTT_HOST', 'mqtt.local'),
            patch.object(Config, 'MQTT_PORT', 1883),
            patch.object(Config, 'MQTT_USERNAME', ''),
            patch.object(Config, 'MQTT_PASSWORD', ''),
            patch.object(Config, 'MQTT_BASE_TOPIC', 'tesla/savings'),
            patch.object(Config, 'MQTT_DISCOVERY_PREFIX', 'ha'),
            patch.object(Config, 'APP_TITLE', 'Tesla Savings App'),
        ):
            publish_metric('all_time_savings', 12.34, unit='$')

        self.assertEqual(mock_single.call_count, 2)

        discovery_call = mock_single.call_args_list[0]
        self.assertEqual(discovery_call.args[0], 'ha/sensor/tesla_savings_all_time_savings/config')
        discovery_payload = json.loads(discovery_call.kwargs['payload'])
        self.assertEqual(discovery_payload['state_topic'], 'tesla/savings/all_time_savings/state')
        self.assertEqual(discovery_payload['unique_id'], 'tesla_savings_all_time_savings')
        self.assertEqual(discovery_payload['default_entity_id'], 'sensor.tesla_savings_all_time_savings')
        self.assertEqual(discovery_payload['device']['identifiers'], ['tesla_savings'])
        self.assertEqual(discovery_call.kwargs['qos'], 1)
        self.assertTrue(discovery_call.kwargs['retain'])

        state_call = mock_single.call_args_list[1]
        self.assertEqual(state_call.args[0], 'tesla/savings/all_time_savings/state')
        self.assertEqual(state_call.kwargs['payload'], '12.34')
        self.assertEqual(state_call.kwargs['qos'], 1)
        self.assertTrue(state_call.kwargs['retain'])

    @patch('app.mqtt_publish.publish.single')
    def test_publish_metric_skips_when_host_missing(self, mock_single):
        with patch.object(Config, 'MQTT_HOST', ''):
            publish_metric('all_time_savings', 12.34, unit='$')

        mock_single.assert_not_called()


class HomeAssistantTests(unittest.TestCase):
    @patch('app.homeassistant.requests.get')
    def test_get_home_assistant_entity_state_returns_none_on_request_error(self, mock_get):
        mock_get.side_effect = requests.RequestException('boom')

        with (
            patch.object(Config, 'HA_URL', 'http://homeassistant.local:8123'),
            patch.object(Config, 'HA_TOKEN', 'token'),
        ):
            state = get_home_assistant_entity_state('sensor.gasbuddy_regular')

        self.assertIsNone(state)


if __name__ == '__main__':
    unittest.main()
