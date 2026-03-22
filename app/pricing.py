from __future__ import annotations

from datetime import date

from app.historical_prices import HISTORICAL_WA_GAS_PRICES


def _normalize_timestamp(value: str | None) -> str | None:
    if value is None:
        return None
    return value.replace(' ', 'T') + 'Z'


def ensure_pricing_schema(conn) -> None:
    conn.execute(
        '''
        CREATE TABLE IF NOT EXISTS fuel_prices (
            price_date TEXT PRIMARY KEY,
            price_per_gallon REAL NOT NULL,
            source TEXT NOT NULL,
            region TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        '''
    )
    conn.commit()


def seed_historical_prices(conn) -> None:
    ensure_pricing_schema(conn)

    for price_date, price in HISTORICAL_WA_GAS_PRICES:
        conn.execute(
            '''
            INSERT OR IGNORE INTO fuel_prices (
                price_date,
                price_per_gallon,
                source,
                region
            ) VALUES (?, ?, ?, ?)
            ''',
            (price_date.isoformat(), float(price), 'historical_seed', 'WA'),
        )
    conn.commit()


def upsert_daily_local_price(conn, price_date: date, price_per_gallon: float) -> None:
    ensure_pricing_schema(conn)
    conn.execute(
        '''
        INSERT INTO fuel_prices (
            price_date,
            price_per_gallon,
            source,
            region
        ) VALUES (?, ?, ?, ?)
        ON CONFLICT(price_date) DO UPDATE SET
            price_per_gallon = excluded.price_per_gallon,
            source = excluded.source,
            region = excluded.region,
            created_at = CURRENT_TIMESTAMP
        ''',
        (price_date.isoformat(), float(price_per_gallon), 'home_assistant_gasbuddy', 'local'),
    )
    conn.commit()


def list_fuel_prices(conn) -> list[dict]:
    ensure_pricing_schema(conn)
    rows = conn.execute(
        '''
        SELECT price_date, price_per_gallon, source, region, created_at
        FROM fuel_prices
        ORDER BY price_date ASC
        '''
    ).fetchall()

    return [
        {
            'price_date': row['price_date'],
            'price_per_gallon': float(row['price_per_gallon']),
            'source': row['source'],
            'region': row['region'],
            'created_at': _normalize_timestamp(row['created_at']),
        }
        for row in rows
    ]


def get_effective_gas_price(conn, target_date: date) -> dict | None:
    ensure_pricing_schema(conn)
    row = conn.execute(
        '''
        SELECT price_date, price_per_gallon, source, region, created_at
        FROM fuel_prices
        WHERE price_date <= ?
        ORDER BY price_date DESC
        LIMIT 1
        ''',
        (target_date.isoformat(),),
    ).fetchone()

    if row is None:
        return None

    return {
        'price_date': row['price_date'],
        'price_per_gallon': float(row['price_per_gallon']),
        'source': row['source'],
        'region': row['region'],
        'created_at': _normalize_timestamp(row['created_at']),
    }


def get_latest_local_price(conn) -> dict | None:
    ensure_pricing_schema(conn)
    row = conn.execute(
        '''
        SELECT price_date, price_per_gallon, source, region, created_at
        FROM fuel_prices
        WHERE source = 'home_assistant_gasbuddy'
        ORDER BY price_date DESC
        LIMIT 1
        '''
    ).fetchone()

    if row is None:
        return None

    return {
        'price_date': row['price_date'],
        'price_per_gallon': float(row['price_per_gallon']),
        'source': row['source'],
        'region': row['region'],
        'created_at': _normalize_timestamp(row['created_at']),
    }
