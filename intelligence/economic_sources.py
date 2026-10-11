"""Disabled-by-default, bounded MOEX adapter. Public access is not a license."""
from __future__ import annotations
import hashlib
import json
import math
import os
from datetime import date, datetime, timezone
from pathlib import Path
import httpx

TERMS = 'https://www.moex.com/a2193'
INDEXES = frozenset(('IMOEX', 'RTSI', 'MOEXOG', 'MOEXFN', 'MOEXTL', 'MOEXMM', 'MOEXEU', 'MOEXCN', 'MOEXCH', 'MOEXTN'))
MAX_BYTES = 1_500_000


def authorization():
    path = os.getenv('MOEX_RIGHTS_MANIFEST_FILE')
    if not path:
        return None
    try:
        with Path(path).open('rb') as file:
            raw = file.read(16385)
        if len(raw) > 16384:
            return None
        value = json.loads(raw)
        allowed = value['permitted_indexes']
        if value.get('provider') != 'MOEX ISS' or value.get('approved_by_operator') is not True or value.get('third_party_product_use') is not True:
            return None
        if not isinstance(value.get('contract_reference'), str) or not 1 <= len(value['contract_reference']) <= 200:
            return None
        if not isinstance(allowed, list) or not allowed or not set(allowed) <= INDEXES:
            return None
        if not date.fromisoformat(value['valid_from']) <= datetime.now(timezone.utc).date() <= date.fromisoformat(value['valid_until']):
            return None
        return {'indexes': allowed, 'manifest_sha256': hashlib.sha256(raw).hexdigest()}
    except (OSError, ValueError, TypeError, KeyError):
        return None


def status(_payload=None):
    rights = authorization()
    return {'status': 'authorized_not_fetched' if rights else 'licensing_required',
            'source_url': TERMS, 'ranking_effect': 0, 'forecast_effect': 0,
            'rights_manifest_present': bool(rights), 'available_indexes': sorted(INDEXES),
            'connection_mode': 'fixed HTTPS origin; no redirects; no proxy inheritance',
            'activation_requires': ['valid operator rights manifest', 'fresh source snapshot',
                                    'independent temporal ablation', 'approved model publication']}


def parse_history(data, index, observed_at):
    section = data.get('history') if isinstance(data, dict) else None
    if not isinstance(section, dict) or not isinstance(section.get('columns'), list) or not isinstance(section.get('data'), list):
        raise ValueError('ISS_schema')
    columns, values = section['columns'], section['data']
    required = ('SECID', 'TRADEDATE', 'CLOSE')
    if len(set(columns)) != len(columns) or not all(c in columns for c in required) or len(values) > 100:
        raise ValueError('ISS_columns')
    positions = [columns.index(c) for c in required]; result = []; seen = set()
    for row in values:
        if not isinstance(row, list) or len(row) != len(columns):
            raise ValueError('ISS_row')
        identity, day, close = (row[i] for i in positions)
        if identity != index or day in seen or date.fromisoformat(day) > date.fromisoformat(observed_at[:10]):
            raise ValueError('ISS_identity_date')
        seen.add(day)
        if close is None:
            continue  # Non-trading/missing prices are not zero.
        if isinstance(close, bool) or not isinstance(close, (float, int)) or not math.isfinite(close) or close <= 0:
            raise ValueError('ISS_price')
        result.append({'date': day, 'close': close})
    return sorted(result, key=lambda row: row['date'])


async def fetch(payload):
    rights = authorization()
    if not rights:
        return status()
    index = payload.get('index', 'IMOEX')
    if index not in rights['indexes']:
        raise ValueError('index_not_authorized')
    start, end = date.fromisoformat(payload['from']), date.fromisoformat(payload['till'])
    if start > end or (end-start).days > 90 or end > datetime.now(timezone.utc).date():
        raise ValueError('history_window')
    # Main session only; one bounded page. Never imply a complete multi-page history.
    url = f'https://iss.moex.com/iss/history/engines/stock/markets/index/sessions/1/securities/{index}.json'
    params = {'from': start.isoformat(), 'till': end.isoformat(), 'iss.meta': 'off',
              'iss.only': 'history', 'history.columns': 'SECID,TRADEDATE,CLOSE', 'limit': 100}
    async with httpx.AsyncClient(timeout=10, follow_redirects=False, trust_env=False) as client:
        async with client.stream('GET', url, params=params) as response:
            response.raise_for_status()
            if response.status_code != 200:
                raise ValueError('ISS_status')
            raw = bytearray()
            async for chunk in response.aiter_bytes():
                if len(raw)+len(chunk) > MAX_BYTES:
                    raise ValueError('ISS_body_limit')
                raw.extend(chunk)
    now = datetime.now(timezone.utc).isoformat()
    observations = parse_history(json.loads(raw), index, now)
    if any(not start.isoformat() <= row['date'] <= end.isoformat() for row in observations):
        raise ValueError('ISS_window_mismatch')
    stale = not observations or (datetime.now(timezone.utc).date()-date.fromisoformat(observations[-1]['date'])).days > 7
    return {**status(), 'status': 'stale' if stale else 'source_snapshot', 'index': index,
            'observed_at': now, 'source_url': url, 'terms_url': TERMS, 'session': 'main',
            'observations': observations, 'body_sha256': hashlib.sha256(raw).hexdigest(),
            'rights_manifest_sha256': rights['manifest_sha256'],
            'limited_to_one_page': True, 'max_rows': 100, 'is_financial_advice': False}
