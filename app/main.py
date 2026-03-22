from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, jsonify, render_template

from app.config import Config
from app.db import get_app_db
from app.homeassistant import build_price_snapshot
from app.mqtt_publish import publish_metric
from app.pricing import seed_historical_prices, upsert_daily_local_price
from app.service import collect_health_payload, collect_metrics_payload, initialize_price_store

app = Flask(__name__)
app.config['SECRET_KEY'] = Config.APP_SECRET_KEY


def update_daily_gas_price() -> None:
    app_db = get_app_db()
    try:
        seed_historical_prices(app_db)
        snapshot = build_price_snapshot()
        if snapshot:
            price_date, price = snapshot
            upsert_daily_local_price(app_db, price_date, price)
    finally:
        app_db.close()


def publish_metrics_payload(payload: dict) -> None:
    if payload['status'] != 'ok':
        return

    all_time = payload['all_time']
    last_30 = payload['last_30_days']

    publish_metric('all_time_savings', all_time['savings'], unit=Config.CURRENCY_SYMBOL)
    publish_metric('last_30_days_savings', last_30['savings'], unit=Config.CURRENCY_SYMBOL)
    publish_metric('all_time_miles', all_time['miles_driven'], unit=Config.DISTANCE_UNIT)
    publish_metric('last_30_days_miles', last_30['miles_driven'], unit=Config.DISTANCE_UNIT)
    publish_metric('all_time_ev_cost', all_time['ev_cost'], unit=Config.CURRENCY_SYMBOL)
    publish_metric('last_30_days_ev_cost', last_30['ev_cost'], unit=Config.CURRENCY_SYMBOL)
    publish_metric('current_gas_price', all_time['current_gas_price'], unit='$/gal')
    publish_metric('current_gas_price_source', all_time['current_gas_price_source'], state_class=None)
    publish_metric('current_gas_price_effective_date', all_time['current_gas_price_effective_date'], state_class=None)
    publish_metric(
        'current_gas_price_fetched_at',
        all_time['current_gas_price_fetched_at'],
        state_class=None,
        device_class='timestamp',
    )
    publish_metric('last_local_gas_price', all_time['last_local_gas_price'], unit='$/gal')
    publish_metric('last_local_gas_price_date', all_time['last_local_gas_price_date'], state_class=None)
    publish_metric(
        'last_local_gas_price_fetched_at',
        all_time['last_local_gas_price_fetched_at'],
        state_class=None,
        device_class='timestamp',
    )
    publish_metric('all_time_estimated_gas_cost', all_time['estimated_gas_cost'], unit=Config.CURRENCY_SYMBOL)
    publish_metric('last_30_days_estimated_gas_cost', last_30['estimated_gas_cost'], unit=Config.CURRENCY_SYMBOL)
    publish_metric('all_time_efficiency', all_time['mi_per_kwh'], unit='mi/kWh')
    publish_metric('last_30_days_efficiency', last_30['mi_per_kwh'], unit='mi/kWh')


def refresh_and_publish_metrics() -> None:
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


initialize_price_store()
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
