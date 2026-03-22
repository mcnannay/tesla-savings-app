from __future__ import annotations

from datetime import date

from app.config import Config
from app.pricing import get_effective_gas_price
from app.teslamate import get_charge_summary, get_daily_drive_rows, get_drive_summary


def gas_cost_for_miles(miles: float, gas_price: float, mpg: float) -> float:
    if mpg <= 0:
        return 0.0
    return (miles / mpg) * gas_price


def build_empty_metrics(days: int | None = None, error_message: str | None = None) -> dict:
    return {
        'miles_driven': 0.0,
        'drive_energy_used_kwh': None,
        'drive_energy_available': False,
        'drive_energy_source': None,
        'drive_energy_note': 'TeslaMate does not expose direct drive energy in this schema.',
        'energy_added_kwh': 0.0,
        'ev_cost': 0.0,
        'estimated_gas_cost': 0.0,
        'savings': 0.0,
        'gas_vehicle_mpg': Config.GAS_VEHICLE_MPG,
        'current_gas_price': 0.0,
        'cost_per_mile': 0.0,
        'mi_per_kwh': 0.0,
        'efficiency_source': 'charging_processes.charge_energy_added',
        'price_coverage_start': None,
        'price_coverage_end': None,
        'distance_unit': Config.DISTANCE_UNIT,
        'currency_symbol': Config.CURRENCY_SYMBOL,
        'status': 'error' if error_message else 'ok',
        'error': error_message,
        'window_days': days,
    }


def build_metrics(teslamate_conn, app_db_conn, days: int | None = None) -> dict:
    drive_summary = get_drive_summary(teslamate_conn, days=days)
    charge_summary = get_charge_summary(teslamate_conn, days=days)
    daily_drive_rows = get_daily_drive_rows(teslamate_conn, days=days)

    estimated_gas_cost = 0.0
    gas_price_dates = []
    for row in daily_drive_rows:
        price_meta = get_effective_gas_price(app_db_conn, row.drive_date)
        if not price_meta:
            continue
        estimated_gas_cost += gas_cost_for_miles(
            row.miles,
            price_meta['price_per_gallon'],
            Config.GAS_VEHICLE_MPG,
        )
        gas_price_dates.append(price_meta['price_date'])

    current_gas_price_meta = get_effective_gas_price(app_db_conn, date.today())
    current_gas_price = current_gas_price_meta['price_per_gallon'] if current_gas_price_meta else 0.0

    efficiency = 0.0
    if drive_summary['miles_driven'] > 0 and charge_summary['energy_added_kwh'] > 0:
        efficiency = drive_summary['miles_driven'] / charge_summary['energy_added_kwh']

    savings = estimated_gas_cost - charge_summary['ev_cost']

    cost_per_mile = 0.0
    if drive_summary['miles_driven'] > 0:
        cost_per_mile = charge_summary['ev_cost'] / drive_summary['miles_driven']

    drive_energy_note = None
    if not drive_summary['drive_energy_available']:
        drive_energy_note = 'TeslaMate does not expose direct drive energy in this schema.'

    return {
        'miles_driven': round(drive_summary['miles_driven'], 2),
        'drive_energy_used_kwh': drive_summary['drive_energy_used_kwh'],
        'drive_energy_available': drive_summary['drive_energy_available'],
        'drive_energy_source': drive_summary['drive_energy_source'],
        'drive_energy_note': drive_energy_note,
        'energy_added_kwh': round(charge_summary['energy_added_kwh'], 2),
        'ev_cost': round(charge_summary['ev_cost'], 2),
        'estimated_gas_cost': round(estimated_gas_cost, 2),
        'savings': round(savings, 2),
        'gas_vehicle_mpg': Config.GAS_VEHICLE_MPG,
        'current_gas_price': round(current_gas_price, 3),
        'cost_per_mile': round(cost_per_mile, 3),
        'mi_per_kwh': round(efficiency, 2),
        'efficiency_source': 'charging_processes.charge_energy_added',
        'price_coverage_start': min(gas_price_dates) if gas_price_dates else None,
        'price_coverage_end': max(gas_price_dates) if gas_price_dates else None,
        'distance_unit': Config.DISTANCE_UNIT,
        'currency_symbol': Config.CURRENCY_SYMBOL,
        'status': 'ok',
        'error': None,
        'window_days': days,
    }
