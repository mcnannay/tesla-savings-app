# Tesla Savings App

A GitHub-first, containerized TeslaMate companion app that estimates EV savings versus a **24 MPG gas vehicle**.

This project is designed to be:

- deployed as a **container image** from **GitHub Container Registry**
- launched from **Portainer** using a simple stack
- connected to your existing **TeslaMate PostgreSQL database**
- integrated with **Home Assistant** through both **MQTT discovery** and an optional Home Assistant REST lookup
- seeded with built-in historical Washington gas prices, then updated daily from your **GasBuddy HACS sensor**

## What it does

The app reads your TeslaMate data and calculates:

- all-time miles driven
- last 30 days miles driven
- all-time EV charging cost
- last 30 days EV charging cost
- all-time estimated gas cost using a 24 MPG comparison vehicle
- last 30 days estimated gas cost using a 24 MPG comparison vehicle
- all-time savings
- last 30 days savings
- current gas price used by the app
- efficiency in mi/kWh
- cost per mile

It exposes those numbers in three ways:

1. a small built-in web dashboard
2. a JSON API at `/api/metrics`
3. MQTT-discovered Home Assistant sensors

## How the savings math works

The comparison formula is:

`estimated gas cost = miles driven / 24 * gas price`

`estimated savings = estimated gas cost - actual EV charging cost`

### Fuel prices

The app uses **two sources** for fuel prices:

1. **Built-in historical backfill**
   - The app seeds the weekly Washington gas prices included in the repo.
   - Each listed price becomes effective on its date and stays active until the next effective date.

2. **Daily local updates from Home Assistant**
   - The app can read a Home Assistant entity such as a GasBuddy HACS sensor.
   - Once per day, it stores that price in its local SQLite database.
   - Those daily prices override the historical backfill for matching dates.

## Architecture

The container contains:

- Flask web app
- APScheduler background jobs
- read-only connection to TeslaMate PostgreSQL
- a small local SQLite database used only for gas prices and app-owned data
- MQTT publishing for Home Assistant sensors

### Why SQLite is included

TeslaMate stays the source of truth for driving and charging data.

The app keeps its own SQLite database so it can safely store:

- the built-in historical gas price series
- your daily local gas price snapshots from Home Assistant
- future app-owned data without changing TeslaMate itself

## Project structure

```text
tesla-savings-app/
├── app/
├── docs/
│   └── lovelace-dashboard.yaml
├── tests/
├── .github/
├── Dockerfile
├── README.md
├── requirements.txt
└── stack.yml
```

## TeslaMate schema notes

This app has been checked against a live TeslaMate schema with these confirmed columns:

- `drives.start_date`
- `drives.distance`
- `charging_processes.start_date`
- `charging_processes.charge_energy_added`
- `charging_processes.cost`

One important limitation is that this TeslaMate schema does **not** expose direct drive energy in `drives`, so:

- savings still work normally
- cost per mile still works normally
- efficiency is currently calculated from miles divided by `charging_processes.charge_energy_added`
- the dashboard labels this clearly as **Charging-Based** efficiency

## Environment variables

### App

- `APP_HOST` - default `0.0.0.0`
- `APP_PORT` - default `5000`
- `APP_SECRET_KEY` - set this to a long random string
- `TZ` - default `America/Los_Angeles`

### TeslaMate

- `TESLAMATE_DB_HOST`
- `TESLAMATE_DB_PORT`
- `TESLAMATE_DB_NAME`
- `TESLAMATE_DB_USER`
- `TESLAMATE_DB_PASSWORD`
- `TESLAMATE_DISTANCE_IN_KM` - `true` or `false`

### Savings behavior

- `GAS_VEHICLE_MPG` - default `24`
- `CURRENCY_SYMBOL` - default `$`
- `DISTANCE_UNIT` - default `mi`

### Home Assistant

- `HA_URL`
- `HA_TOKEN`
- `HA_GAS_PRICE_ENTITY`

### MQTT / Home Assistant discovery

- `MQTT_HOST`
- `MQTT_PORT`
- `MQTT_USERNAME`
- `MQTT_PASSWORD`
- `MQTT_BASE_TOPIC`

### Scheduler

- `PRICE_FETCH_HOUR`
- `PRICE_FETCH_MINUTE`

## GitHub workflow

The included GitHub Actions workflow:

- builds the Docker image
- pushes it to GitHub Container Registry
- tags it as `latest`, commit SHA, and Git tag when applicable

After you push this project to GitHub, the published image will look like:

`ghcr.io/<your-github-username>/tesla-savings-app:latest`

## Portainer deployment

### Current environment assumptions

This repo is already shaped around your environment:

- TeslaMate stack/project name: `teslamate`
- TeslaMate DB service name on the Docker network: `database`
- Home Assistant URL: `http://192.168.11.10:8123`
- MQTT broker: `192.168.11.7:1883`
- app HTTP port mapping: `5080:5000`

### Before deploying

Update [stack.yml](./stack.yml) and replace:

- `YOUR_GITHUB_USERNAME`
- `APP_SECRET_KEY`
- `TESLAMATE_DB_PASSWORD`
- `HA_TOKEN`
- `MQTT_PASSWORD`

For a cleaner setup, copy values from `.env.example` into your own private notes or secret store and paste them into Portainer during deployment. Do not commit real secrets to the repo.

### Network requirement

This app must join the same Docker network as your TeslaMate database.

The stack uses:

```yaml
networks:
  teslamate_default:
    external: true
```

That should be correct for a Portainer stack named `teslamate`. If your real Docker network name differs, update it.

### Deploy steps

1. Push this repo to GitHub.
2. Let GitHub Actions publish the image to GHCR.
3. In Portainer, create a new stack or update your existing app stack using [stack.yml](./stack.yml).
4. Replace the remaining placeholders.
5. Deploy the stack.
6. Open the app at `http://<your-docker-host>:5080/`.
7. Check `http://<your-docker-host>:5080/api/health`.
8. Wait for MQTT discovery entities to appear in Home Assistant.

## Web UI and API

After deploy, the app serves:

- `/` - HTML dashboard
- `/api/health` - health endpoint
- `/api/metrics` - JSON metrics

## Home Assistant integration

The app publishes MQTT discovery topics for sensors such as:

- `sensor.tesla_savings_all_time_savings`
- `sensor.tesla_savings_last_30_days_savings`
- `sensor.tesla_savings_all_time_miles`
- `sensor.tesla_savings_last_30_days_miles`
- `sensor.tesla_savings_all_time_ev_cost`
- `sensor.tesla_savings_last_30_days_ev_cost`
- `sensor.tesla_savings_current_gas_price`
- `sensor.tesla_savings_all_time_estimated_gas_cost`
- `sensor.tesla_savings_last_30_days_estimated_gas_cost`
- `sensor.tesla_savings_all_time_efficiency`
- `sensor.tesla_savings_last_30_days_efficiency`

The code uses `default_entity_id`, not deprecated `object_id`.

### Recommended dashboard choice

For this project, Home Assistant is the best first dashboard.

Use:

- the app web UI for a dedicated app page
- Home Assistant Lovelace for your everyday dashboard
- Grafana only if you later want more advanced historical charting

A ready-to-paste Lovelace example is included at [docs/lovelace-dashboard.yaml](./docs/lovelace-dashboard.yaml).

## Historical fuel prices included

The following weekly Washington values are built directly into the app and seeded on startup:

- 2025-08-04 → 4.273
- 2025-08-11 → 4.314
- 2025-08-18 → 4.313
- 2025-08-25 → 4.291
- 2025-09-01 → 4.294
- 2025-09-08 → 4.365
- 2025-09-15 → 4.536
- 2025-09-22 → 4.515
- 2025-09-29 → 4.449
- 2025-10-06 → 4.409
- 2025-10-13 → 4.357
- 2025-10-20 → 4.305
- 2025-10-27 → 4.253
- 2025-11-03 → 4.173
- 2025-11-10 → 4.117
- 2025-11-17 → 4.052
- 2025-11-24 → 4.039
- 2025-12-01 → 4.027
- 2025-12-08 → 3.980
- 2025-12-15 → 3.870
- 2025-12-22 → 3.817
- 2025-12-29 → 3.774
- 2026-01-05 → 3.710
- 2026-01-12 → 3.645
- 2026-01-19 → 3.657
- 2026-01-26 → 3.685
- 2026-02-02 → 3.763
- 2026-02-09 → 3.863
- 2026-02-16 → 4.009
- 2026-02-23 → 4.143
- 2026-03-02 → 4.202
- 2026-03-09 → 4.522
- 2026-03-16 → 4.788

## Local development

Create a Python environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Then run:

```bash
export FLASK_APP=app.main:app
flask run --host=0.0.0.0 --port=5000
```

## Build locally

```bash
docker build -t tesla-savings-app:local .
```

## Next recommended improvements

1. switch the stack to env substitution for secrets
2. add chart views for monthly savings and gas price history
3. add CSV export
4. add a settings page stored in the app DB
5. add tests for TeslaMate query logic against fixture schemas
6. add a richer Lovelace dashboard variant with graphs

## Summary

This repo is now a solid starting point for your actual setup:

- GitHub-hosted
- containerized
- Portainer deployable
- TeslaMate-aware
- Home Assistant-aware
- seeded with historical fuel prices
- aligned with your real TeslaMate schema
