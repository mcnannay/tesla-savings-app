import sqlite3
import unittest
from datetime import date
from unittest.mock import patch

from app.metrics import _estimate_gas_cost, build_empty_metrics, build_metrics, gas_cost_for_miles
from app.pricing import get_effective_gas_price, get_latest_local_price, upsert_daily_local_price
from app.service import collect_health_payload
from app.teslamate import DriveDay


class PricingTests(unittest.TestCase):
    def test_gas_cost_for_miles_uses_mpg(self):
        self.assertAlmostEqual(gas_cost_for_miles(240, 4.0, 24), 40.0)

    def test_gas_cost_for_zero_mpg_returns_zero(self):
        self.assertEqual(gas_cost_for_miles(100, 4.0, 0), 0.0)

    def test_upsert_daily_price_becomes_effective_price(self):
        conn = sqlite3.connect(':memory:')
        conn.row_factory = sqlite3.Row

        upsert_daily_local_price(conn, date(2026, 3, 22), 4.99)
        price = get_effective_gas_price(conn, date(2026, 3, 22))

        self.assertIsNotNone(price)
        self.assertEqual(price['price_per_gallon'], 4.99)
        self.assertEqual(price['source'], 'home_assistant_gasbuddy')

    def test_get_latest_local_price_returns_metadata(self):
        conn = sqlite3.connect(':memory:')
        conn.row_factory = sqlite3.Row

        upsert_daily_local_price(conn, date(2026, 3, 21), 4.11)
        upsert_daily_local_price(conn, date(2026, 3, 22), 4.22)
        price = get_latest_local_price(conn)

        self.assertIsNotNone(price)
        self.assertEqual(price['price_date'], '2026-03-22')
        self.assertEqual(price['price_per_gallon'], 4.22)
        self.assertIsNotNone(price['created_at'])

    def test_estimate_gas_cost_uses_latest_effective_price(self):
        rows = [
            DriveDay(date(2026, 3, 20), 24.0, 0.0),
            DriveDay(date(2026, 3, 21), 48.0, 0.0),
        ]
        prices = [
            {'price_date': '2026-03-19', 'price_per_gallon': 4.0, 'source': 'historical_seed', 'region': 'WA', 'created_at': '2026-03-19 00:00:00'},
            {'price_date': '2026-03-21', 'price_per_gallon': 5.0, 'source': 'home_assistant_gasbuddy', 'region': 'local', 'created_at': '2026-03-21 05:15:00'},
        ]

        estimated_gas_cost, coverage = _estimate_gas_cost(rows, prices)

        self.assertEqual(round(estimated_gas_cost, 2), 14.0)
        self.assertEqual(coverage, ['2026-03-19', '2026-03-21'])


class EmptyMetricsTests(unittest.TestCase):
    def test_build_empty_metrics_includes_drive_energy_metadata(self):
        payload = build_empty_metrics(days=30, error_message='schema mismatch')

        self.assertEqual(payload['status'], 'error')
        self.assertEqual(payload['error'], 'schema mismatch')
        self.assertEqual(payload['window_days'], 30)
        self.assertFalse(payload['drive_energy_available'])
        self.assertIsNone(payload['drive_energy_used_kwh'])
        self.assertIsNone(payload['last_local_gas_price_fetched_at'])


class BuiltMetricsTests(unittest.TestCase):
    @patch('app.metrics.get_daily_drive_rows')
    @patch('app.metrics.get_charge_summary')
    def test_build_metrics_includes_gas_fetch_metadata(
        self,
        mock_get_charge_summary,
        mock_get_daily_drive_rows,
    ):
        conn = sqlite3.connect(':memory:')
        conn.row_factory = sqlite3.Row
        upsert_daily_local_price(conn, date.today(), 4.5)

        mock_get_charge_summary.return_value = {
            'energy_added_kwh': 40.0,
            'ev_cost': 12.0,
        }
        mock_get_daily_drive_rows.return_value = [DriveDay(date.today(), 120.0, 0.0)]

        payload = build_metrics(object(), conn)

        self.assertFalse(payload['drive_energy_available'])
        self.assertIsNone(payload['drive_energy_used_kwh'])
        self.assertEqual(payload['efficiency_source'], 'charging_processes.charge_energy_added')
        self.assertEqual(payload['mi_per_kwh'], 3.0)
        self.assertEqual(payload['current_gas_price_source'], 'home_assistant_gasbuddy')
        self.assertEqual(payload['last_local_gas_price'], 4.5)
        self.assertIsNotNone(payload['last_local_gas_price_fetched_at'])


class HealthPayloadTests(unittest.TestCase):
    @patch('app.service.collect_metrics_payload')
    def test_collect_health_payload_returns_degraded_status_code(self, mock_collect_metrics_payload):
        mock_collect_metrics_payload.return_value = {
            'status': 'degraded',
            'sources': {
                'teslamate': {'ok': False, 'error': 'schema mismatch'},
                'pricing': {'ok': True, 'error': None},
            },
            'all_time': build_empty_metrics(error_message='schema mismatch'),
            'last_30_days': build_empty_metrics(days=30, error_message='schema mismatch'),
        }

        payload, status_code = collect_health_payload()

        self.assertEqual(status_code, 503)
        self.assertEqual(payload['status'], 'degraded')
        self.assertFalse(payload['sources']['teslamate']['ok'])


if __name__ == '__main__':
    unittest.main()
