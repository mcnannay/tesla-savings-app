from __future__ import annotations

import sqlite3

try:
    import psycopg2
except ModuleNotFoundError:
    psycopg2 = None

from app.db import get_app_db, get_teslamate_conn
from app.metrics import build_empty_metrics, build_metrics
from app.pricing import seed_historical_prices
from app.teslamate import TeslaMateError


def initialize_price_store() -> None:
    app_db = get_app_db()
    try:
        seed_historical_prices(app_db)
    finally:
        app_db.close()


def _default_source_status() -> dict:
    return {
        'teslamate': {'ok': True, 'error': None},
        'pricing': {'ok': True, 'error': None},
    }


def _mark_error(status: dict, source: str, exc: Exception) -> None:
    status[source]['ok'] = False
    status[source]['error'] = str(exc)


def _is_teslamate_error(exc: Exception) -> bool:
    if isinstance(exc, TeslaMateError):
        return True
    if psycopg2 is not None and isinstance(exc, psycopg2.Error):
        return True
    return isinstance(exc, ModuleNotFoundError) and exc.name == 'psycopg2'


def collect_metrics_payload() -> dict:
    status = _default_source_status()
    all_time = build_empty_metrics()
    last_30_days = build_empty_metrics(days=30)

    try:
        initialize_price_store()
    except sqlite3.Error as exc:
        _mark_error(status, 'pricing', exc)
        return {
            'status': 'degraded',
            'sources': status,
            'all_time': all_time,
            'last_30_days': last_30_days,
        }

    teslamate_conn = None
    app_db = None
    try:
        teslamate_conn = get_teslamate_conn()
        app_db = get_app_db()
        all_time = build_metrics(teslamate_conn, app_db, days=None)
        last_30_days = build_metrics(teslamate_conn, app_db, days=30)
    except Exception as exc:
        if _is_teslamate_error(exc):
            _mark_error(status, 'teslamate', exc)
        elif isinstance(exc, sqlite3.Error):
            _mark_error(status, 'pricing', exc)
        else:
            raise
        all_time = build_empty_metrics(error_message=str(exc))
        last_30_days = build_empty_metrics(days=30, error_message=str(exc))
    finally:
        if teslamate_conn is not None:
            teslamate_conn.close()
        if app_db is not None:
            app_db.close()

    overall_status = 'ok' if all(source['ok'] for source in status.values()) else 'degraded'
    return {
        'status': overall_status,
        'sources': status,
        'all_time': all_time,
        'last_30_days': last_30_days,
    }


def collect_health_payload() -> tuple[dict, int]:
    payload = collect_metrics_payload()
    status_code = 200 if payload['status'] == 'ok' else 503
    return {
        'status': payload['status'],
        'sources': payload['sources'],
    }, status_code
