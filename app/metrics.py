from __future__ import annotations

from datetime import date

from app.config import Config
from app.pricing import get_effective_gas_price, get_latest_local_price, list_fuel_prices
from app.teslamate import get_charge_summary, get_daily_drive_rows


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
        'current_gas_price_source': None,
        'current_gas_price_effective_date': None,
        'current_gas_price_fetched_at': None,
        'last_local_gas_price': None,
        'last_local_gas_price_date': None,
        'last_local_gas_price_fetched_at': None,
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


def _summarize_drives(daily_drive_rows) -> dict:
    total_miles = sum(row.miles for row in daily_drive_rows)
    total_energy_used = sum(row.energy_used_kwh for row in daily_drive_rows)
    drive_energy_available = total_energy_used > 0
    drive_energy_note = None if drive_energy_available else 'TeslaMate does not expose direct drive energy in this schema.'

    return {
        'miles_driven': round(total_miles, 2),
        'drive_energy_used_kwh': round(total_energy_used, 2) if drive_energy_available else None,
        'drive_energy_available': drive_energy_available,
        'drive_energy_source': 'drives.consumption_kwh' if drive_energy_available else None,
        'drive_energy_note': drive_energy_note,
    }


def _estimate_gas_cost(daily_drive_rows, fuel_prices: list[dict]) -> tuple[float, list[str]]:
    if not fuel_prices:
        return 0.0, []

    estimated_gas_cost = 0.0
    gas_price_dates: list[str] = []
    fuel_index = 0
    current_price = None

    for row in daily_drive_rows:
        drive_date = row.drive_date.isoformat()
        while fuel_index < len(fuel_prices) and fuel_prices[fuel_index]['price_date'] <= drive_date:
            current_price = fuel_prices[fuel_index]
            fuel_index += 1

        if current_price is None:
            continue

        estimated_gas_cost += gas_cost_for_miles(
            row.miles,
            current_price['price_per_gallon'],
            Config.GAS_VEHICLE_MPG,
        )
        gas_price_dates.append(current_price['price_date'])

    return estimated_gas_cost, gas_price_dates


def build_metrics(teslamate_conn, app_db_conn, days: int | None = None) -> dict:
    daily_drive_rows = get_daily_drive_rows(teslamate_conn, days=days)
    drive_summary = _summarize_drives(daily_drive_rows)
    charge_summary = get_charge_summary(teslamate_conn, days=days)
    fuel_prices = list_fuel_prices(app_db_conn)

    estimated_gas_cost, gas_price_dates = _estimate_gas_cost(daily_drive_rows, fuel_prices)

    current_gas_price_meta = get_effective_gas_price(app_db_conn, date.today())
    current_gas_price = current_gas_price_meta['price_per_gallon'] if current_gas_price_meta else 0.0
    latest_local_price = get_latest_local_price(app_db_conn)

    efficiency = 0.0
    if drive_summary['miles_driven'] > 0 and charge_summary['energy_added_kwh'] > 0:
        efficiency = drive_summary['miles_driven'] / charge_summary['energy_added_kwh']

    savings = estimated_gas_cost - charge_summary['ev_cost']

    cost_per_mile = 0.0
    if drive_summary['miles_driven'] > 0:
        cost_per_mile = charge_summary['ev_cost'] / drive_summary['miles_driven']

    return {
        'miles_driven': drive_summary['miles_driven'],
        'drive_energy_used_kwh': drive_summary['drive_energy_used_kwh'],
        'drive_energy_available': drive_summary['drive_energy_available'],
        'drive_energy_source': drive_summary['drive_energy_source'],
        'drive_energy_note': drive_summary['drive_energy_note'],
        'energy_added_kwh': round(charge_summary['energy_added_kwh'], 2),
        'ev_cost': round(charge_summary['ev_cost'], 2),
        'estimated_gas_cost': round(estimated_gas_cost, 2),
        'savings': round(savings, 2),
        'gas_vehicle_mpg': Config.GAS_VEHICLE_MPG,
        'current_gas_price': round(current_gas_price, 3),
        'current_gas_price_source': current_gas_price_meta['source'] if current_gas_price_meta else None,
        'current_gas_price_effective_date': current_gas_price_meta['price_date'] if current_gas_price_meta else None,
        'current_gas_price_fetched_at': current_gas_price_meta['created_at'] if current_gas_price_meta else None,
        'last_local_gas_price': round(latest_local_price['price_per_gallon'], 3) if latest_local_price else None,
        'last_local_gas_price_date': latest_local_price['price_date'] if latest_local_price else None,
        'last_local_gas_price_fetched_at': latest_local_price['created_at'] if latest_local_price else None,
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
