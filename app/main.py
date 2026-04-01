from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, jsonify, render_template

from app.config import Config
from app.db import get_app_db
from app.homeassistant import build_price_snapshot
from app.mqtt_publish import publish_metric_config, publish_metric_state
from app.pricing import seed_historical_prices, upsert_daily_local_price
from app.service import collect_health_payload, collect_metrics_payload

app = Flask(__name__)
app.config['SECRET_KEY'] = Config.APP_SECRET_KEY
LOGGER = logging.getLogger(__name__)

METRIC_DEFINITIONS = (
    {'name': 'all_time_savings', 'section': 'all_time', 'key': 'savings', 'unit': Config.CURRENCY_SYMBOL, 'state_class': 'total'},
    {'name': 'last_30_days_savings', 'section': 'last_30_days', 'key': 'savings', 'unit': Config.CURRENCY_SYMBOL, 'state_class': None},
    {'name': 'all_time_miles', 'section': 'all_time', 'key': 'miles_driven', 'unit': Config.DISTANCE_UNIT, 'state_class': 'total'},
    {'name': 'last_30_days_miles', 'section': 'last_30_days', 'key': 'miles_driven', 'unit': Config.DISTANCE_UNIT, 'state_class': None},
    {'name': 'all_time_ev_cost', 'section': 'all_time', 'key': 'ev_cost', 'unit': Config.CURRENCY_SYMBOL, 'state_class': 'total'},
    {'name': 'last_30_days_ev_cost', 'section': 'last_30_days', 'key': 'ev_cost', 'unit': Config.CURRENCY_SYMBOL, 'state_class': None},
    {'name': 'current_gas_price', 'section': 'all_time', 'key': 'current_gas_price', 'unit': '$/gal', 'state_class': 'measurement'},
    {'name': 'current_gas_price_source', 'section': 'all_time', 'key': 'current_gas_price_source', 'state_class': None},
    {'name': 'current_gas_price_effective_date', 'section': 'all_time', 'key': 'current_gas_price_effective_date', 'state_class': None},
    {
        'name': 'current_gas_price_fetched_at',
        'section': 'all_time',
        'key': 'current_gas_price_fetched_at',
        'state_class': None,
        'device_class': 'timestamp',
    },
    {'name': 'last_local_gas_price', 'section': 'all_time', 'key': 'last_local_gas_price', 'unit': '$/gal', 'state_class': 'measurement'},
    {'name': 'last_local_gas_price_date', 'section': 'all_time', 'key': 'last_local_gas_price_date', 'state_class': None},
    {
        'name': 'last_local_gas_price_fetched_at',
        'section': 'all_time',
        'key': 'last_local_gas_price_fetched_at',
        'state_class': None,
        'device_class': 'timestamp',
    },
    {
        'name': 'all_time_estimated_gas_cost',
        'section': 'all_time',
        'key': 'estimated_gas_cost',
        'unit': Config.CURRENCY_SYMBOL,
        'state_class': 'total',
    },
    {
        'name': 'last_30_days_estimated_gas_cost',
        'section': 'last_30_days',
        'key': 'estimated_gas_cost',
        'unit': Config.CURRENCY_SYMBOL,
        'state_class': None,
    },
    {'name': 'all_time_efficiency', 'section': 'all_time', 'key': 'mi_per_kwh', 'unit': 'mi/kWh', 'state_class': None},
    {'name': 'last_30_days_efficiency', 'section': 'last_30_days', 'key': 'mi_per_kwh', 'unit': 'mi/kWh', 'state_class': None},
)


def update_daily_gas_price() -> None:
    app_db = get_app_db()
    try:
        seed_historical_prices(app_db)
        snapshot = build_price_snapshot()
        if snapshot:
            price_date, price = snapshot
            upsert_daily_local_price(app_db, price_date, price)
    except Exception:
        LOGGER.exception("Failed to update the daily gas price snapshot.")
    finally:
        app_db.close()


def publish_metric_configs() -> None:
    for metric in METRIC_DEFINITIONS:
        publish_metric_config(
            metric['name'],
            unit=metric.get('unit', ''),
            state_class=metric.get('state_class'),
            device_class=metric.get('device_class'),
        )


def publish_metrics_payload(payload: dict) -> None:
    if payload['status'] != 'ok':
        LOGGER.warning(
            "Skipping MQTT state publish because the metrics payload is '%s'.",
            payload['status'],
        )
        return

    for metric in METRIC_DEFINITIONS:
        publish_metric_state(
            metric['name'],
            payload[metric['section']][metric['key']],
        )


def refresh_and_publish_metrics() -> None:
    publish_metric_configs()
    update_daily_gas_price()
    publish_metrics_payload(collect_metrics_payload())


@app.route('/')
def index():
    payload = collect_metrics_payload()
    return render_template(
        'index.html',
        app_title=Config.APP_TITLE,
        all_time=payload['all_time'],
        last_30=payload['last_30_days'],
        app_status=payload['status'],
        source_status=payload['sources'],
        currency_symbol=Config.CURRENCY_SYMBOL,
        distance_unit=Config.DISTANCE_UNIT,
    )


@app.route('/api/health')
def health():
    payload, status_code = collect_health_payload()
    return jsonify(payload), status_code


@app.route('/api/metrics')
def api_metrics():
    payload = collect_metrics_payload()
    return jsonify(payload)

publish_metric_configs()
update_daily_gas_price()
startup_payload = collect_metrics_payload()
publish_metrics_payload(startup_payload)

scheduler = BackgroundScheduler(timezone=Config.TZ)
scheduler.add_job(
    update_daily_gas_price,
    trigger='cron',
    hour=Config.PRICE_FETCH_HOUR,
    minute=Config.PRICE_FETCH_MINUTE,
    id='update_daily_gas_price',
    replace_existing=True,
)
scheduler.add_job(
    refresh_and_publish_metrics,
    trigger='interval',
    hours=6,
    id='refresh_and_publish_metrics',
    replace_existing=True,
)
scheduler.start()
