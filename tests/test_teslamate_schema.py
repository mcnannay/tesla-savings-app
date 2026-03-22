import unittest

from app.teslamate import _charge_energy_expr, _distance_expr


class TeslaMateSchemaTests(unittest.TestCase):
    def test_distance_expr_prefers_verified_distance_column(self):
        expr = _distance_expr({'distance', 'start_km', 'end_km'})
        self.assertEqual(expr, 'COALESCE(distance, 0)')

    def test_distance_expr_falls_back_to_start_end_km(self):
        expr = _distance_expr({'start_km', 'end_km'})
        self.assertEqual(expr, 'GREATEST(COALESCE(end_km, 0) - COALESCE(start_km, 0), 0)')

    def test_charge_energy_expr_prefers_charge_energy_added(self):
        expr = _charge_energy_expr({'charge_energy_added', 'charge_energy_used'})
        self.assertEqual(expr, 'COALESCE(charge_energy_added, 0)')


if __name__ == '__main__':
    unittest.main()
