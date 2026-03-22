from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from app.config import Config

KM_TO_MI = 0.621371


class TeslaMateError(RuntimeError):
    pass


class TeslaMateSchemaError(TeslaMateError):
    pass


@dataclass
class DriveDay:
    drive_date: date
    miles: float
    energy_used_kwh: float


@dataclass(frozen=True)
class DriveSchema:
    date_column: str
    distance_expr: str
    energy_expr: str
    energy_available: bool
    energy_source: str | None


@dataclass(frozen=True)
class ChargingSchema:
    date_column: str
    energy_expr: str
    cost_expr: str


def _columns_for_table(conn, table_name: str) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(
            '''
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ''',
            (table_name,),
        )
        columns = {row[0] for row in cur.fetchall()}

    if not columns:
        raise TeslaMateSchemaError(
            f"TeslaMate table '{table_name}' was not found or has no readable columns."
        )

    return columns


def _days_filter_sql(days: int | None, column: str) -> tuple[str, list[Any]]:
    if days is None:
        return "", []
    return f"WHERE {column} >= NOW() - (%s || ' days')::interval", [str(days)]


def _first_present(columns: set[str], candidates: tuple[str, ...], label: str, table_name: str) -> str:
    for candidate in candidates:
        if candidate in columns:
            return candidate

    raise TeslaMateSchemaError(
        f"Could not find a {label} column in TeslaMate table '{table_name}'. "
        f"Checked: {', '.join(candidates)}."
    )


def _distance_expr(columns: set[str]) -> str:
    if 'distance' in columns:
        return 'COALESCE(distance, 0)'
    if 'end_km' in columns and 'start_km' in columns:
        return 'GREATEST(COALESCE(end_km, 0) - COALESCE(start_km, 0), 0)'
    if 'distance_km' in columns:
        return 'COALESCE(distance_km, 0)'
    if 'odometer' in columns and 'start_odometer' in columns:
        return 'GREATEST(COALESCE(odometer, 0) - COALESCE(start_odometer, 0), 0)'
    raise TeslaMateSchemaError(
        'Could not find a usable distance column in TeslaMate drives table. '
        'Checked: distance, end_km/start_km, distance_km, odometer/start_odometer.'
    )


def _energy_config(columns: set[str]) -> tuple[str, bool, str | None]:
    if 'consumption_kwh' in columns:
        return 'COALESCE(consumption_kwh, 0)', True, 'drives.consumption_kwh'
    return '0', False, None


def _charge_energy_expr(columns: set[str]) -> str:
    for name in ('charge_energy_added', 'charge_energy_used', 'charge_energy'):
        if name in columns:
            return f'COALESCE({name}, 0)'
    raise TeslaMateSchemaError(
        'Could not find a charge energy column in TeslaMate charging_processes table. '
        'Checked: charge_energy_added, charge_energy_used, charge_energy.'
    )


def _charge_cost_expr(columns: set[str]) -> str:
    if 'cost' in columns:
        return 'COALESCE(cost, 0)'
    return '0'


def _convert_distance_to_miles(distance_value: float) -> float:
    if Config.TESLAMATE_DISTANCE_IN_KM:
        return distance_value * KM_TO_MI
    return distance_value


def _drive_schema(conn) -> DriveSchema:
    columns = _columns_for_table(conn, 'drives')
    energy_expr, energy_available, energy_source = _energy_config(columns)
    return DriveSchema(
        date_column=_first_present(
            columns,
            ('start_date', 'end_date', 'date', 'inserted_at'),
            'drive date',
            'drives',
        ),
        distance_expr=_distance_expr(columns),
        energy_expr=energy_expr,
        energy_available=energy_available,
        energy_source=energy_source,
    )


def _charging_schema(conn) -> ChargingSchema:
    columns = _columns_for_table(conn, 'charging_processes')
    return ChargingSchema(
        date_column=_first_present(
            columns,
            ('start_date', 'end_date', 'date', 'inserted_at'),
            'charging date',
            'charging_processes',
        ),
        energy_expr=_charge_energy_expr(columns),
        cost_expr=_charge_cost_expr(columns),
    )


def get_daily_drive_rows(conn, days: int | None = None) -> list[DriveDay]:
    schema = _drive_schema(conn)
    where_sql, params = _days_filter_sql(days, schema.date_column)

    query = f'''
        SELECT
            DATE({schema.date_column}) AS drive_date,
            SUM({schema.distance_expr}) AS distance_total,
            SUM({schema.energy_expr}) AS energy_total
        FROM drives
        {where_sql}
        GROUP BY DATE({schema.date_column})
        ORDER BY DATE({schema.date_column})
    '''

    with conn.cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()

    result = []
    for row in rows:
        raw_distance = float(row[1] or 0)
        miles = _convert_distance_to_miles(raw_distance)
        result.append(
            DriveDay(
                drive_date=row[0],
                miles=round(miles, 4),
                energy_used_kwh=float(row[2] or 0),
            )
        )
    return result


def get_charge_summary(conn, days: int | None = None) -> dict[str, float]:
    schema = _charging_schema(conn)
    where_sql, params = _days_filter_sql(days, schema.date_column)

    query = f'''
        SELECT
            SUM({schema.energy_expr}) AS energy_added,
            SUM({schema.cost_expr}) AS total_cost
        FROM charging_processes
        {where_sql}
    '''

    with conn.cursor() as cur:
        cur.execute(query, params)
        row = cur.fetchone()

    return {
        'energy_added_kwh': float(row[0] or 0),
        'ev_cost': float(row[1] or 0),
    }


def get_drive_summary(conn, days: int | None = None) -> dict[str, float | bool | str | None]:
    schema = _drive_schema(conn)
    daily_rows = get_daily_drive_rows(conn, days=days)
    total_miles = sum(item.miles for item in daily_rows)
    total_energy_used = sum(item.energy_used_kwh for item in daily_rows)

    mi_per_kwh = None
    if schema.energy_available and total_energy_used > 0:
        mi_per_kwh = total_miles / total_energy_used

    return {
        'miles_driven': round(total_miles, 2),
        'drive_energy_used_kwh': round(total_energy_used, 2) if schema.energy_available else None,
        'drive_energy_available': schema.energy_available,
        'drive_energy_source': schema.energy_source,
        'mi_per_kwh_from_drives': round(mi_per_kwh, 2) if mi_per_kwh is not None else None,
    }
