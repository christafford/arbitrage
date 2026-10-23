"""Operator-declared fee applicability, immutable byte evidence and bounded validity."""
from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlsplit

from .fees import model_from_profile
from .fee_capture import KALSHI_SCHEDULE, validate_profile_capture
from .validation import dumps, field, identifier, load_json, text_field, utc_time


def import_profile(con, raw, *, base, now, attested=False):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= 2000000:
        raise ValueError('fee import must contain 1..2000000 bytes')
    imported = con.execute("INSERT INTO fee_imports(imported_at,raw_bytes,sha256,status) VALUES(?,?,?,'PENDING')",
                           (now.isoformat(), raw, sha256(raw).hexdigest())).lastrowid
    con.commit()  # Original configuration is archived before parsing or validation.
    try:
        data = load_json(raw)
        # A failed refresh with a known identity supersedes older applicability too.
        venue, source_id, side = (text_field(data, key) for key in ('venue', 'source_id', 'side'))
        identifier(source_id)
        if venue not in {'kalshi', 'polymarket_us'} or side not in {'YES', 'NO'}:
            raise ValueError('invalid fee identity')
        con.execute('UPDATE fee_imports SET venue=?,source_id=?,side=? WHERE id=?', (venue, source_id, side, imported))
        con.commit()
        model = model_from_profile(data)
        hypothetical = field(data, 'hypothetical', bool)
        if not attested or field(data, 'applicability_reviewed', bool) is not True:
            raise ValueError('explicit fee applicability attestation required')
        operator = text_field(data, 'operator')
        if hypothetical != model.source_id.startswith('HYPOTHETICAL-'):
            raise ValueError('fee hypothetical identity mismatch')
        instrument = con.execute('''SELECT v.hypothetical FROM registry_instruments i JOIN rule_versions v ON v.id=i.version_id
                                    WHERE i.venue=? AND i.source_id=?''', (model.venue, model.source_id)).fetchone()
        if not instrument or bool(instrument[0]) != hypothetical:
            raise ValueError('matching registry instrument required for fee applicability')
        expires = utc_time(text_field(data, 'expires_at'))
        if not now < expires <= now + timedelta(hours=24):
            raise ValueError('fee expiry must be future and at most 24 hours')
        documents = field(data, 'documents', list)
        if hypothetical:
            if not 1 <= len(documents) <= 10:
                raise ValueError('1..10 fee source documents required')
        else:
            validate_profile_capture(con, data, now=now)
            if len(documents) > 10:
                raise ValueError('at most 10 supplemental fee documents allowed')
            if model.venue == 'kalshi' and not any(text_field(doc, 'url') == KALSHI_SCHEDULE for doc in documents):
                raise ValueError('current official Kalshi fee schedule PDF required')
            # Copy the reviewed capture bytes, never accept caller replacements.
            con.execute('''INSERT INTO fee_documents(import_id,source_url,retrieved_at,raw_bytes,sha256)
                SELECT ?,source_url,retrieved_at,raw_bytes,sha256 FROM fee_documents WHERE import_id=?''',
                        (imported, data['capture_id']))
            con.commit()
        for doc in documents:
            url, retrieved = text_field(doc, 'url'), utc_time(text_field(doc, 'retrieved_at'))
            host = urlsplit(url)
            allowed = {'example.invalid'} if hypothetical else (
                {'kalshi.com', 'docs.kalshi.com', 'external-api.kalshi.com'} if model.venue == 'kalshi'
                else {'docs.polymarket.us', 'polymarket.us', 'gateway.polymarket.us'})
            if host.scheme != 'https' or host.hostname not in allowed or host.username or host.password or host.port not in (None, 443) or host.fragment:
                raise ValueError('unsupported fee evidence URL')
            body = (Path(base) / text_field(doc, 'path')).read_bytes()
            if not 0 < len(body) <= 2000000:
                raise ValueError('fee source document must contain 1..2000000 bytes')
            # Source import is explicitly declared; no network fetch or authentication claimed.
            con.execute('INSERT INTO fee_documents(import_id,source_url,retrieved_at,raw_bytes,sha256) VALUES(?,?,?,?,?)',
                        (imported, url, retrieved.isoformat(), body, sha256(body).hexdigest()))
            con.commit()
            if not hypothetical and url == KALSHI_SCHEDULE and not body.startswith(b'%PDF-'):
                raise ValueError('Kalshi schedule must be the downloaded PDF, not an error page')
            if retrieved > now + timedelta(seconds=5) or expires > retrieved + timedelta(hours=24):
                raise ValueError('stale or future fee source; expiry must respect every source clock')
        if not hypothetical:
            # Applicability can differ by series, category, account and scheduled changes.
            for key in ('instrument_scope', 'scheduled_changes_checked', 'account_fee_extras_checked'):
                text_field(data, key)
            if data['account_fee_extras_checked'] != 'NONE_CONFIRMED':
                raise ValueError('additional account/FCM charges are unsupported')
        profile_json = dumps(data)
        profile_id = con.execute('''INSERT INTO fee_profiles(import_id,venue,source_id,side,reviewed_at,expires_at,
                    hypothetical,operator,profile_json,sha256) VALUES(?,?,?,?,?,?,?,?,?,?)''',
                    (imported, model.venue, model.source_id, model.side, now.isoformat(), expires.isoformat(),
                     int(hypothetical), operator, profile_json, sha256(profile_json.encode()).hexdigest())).lastrowid
        con.execute("UPDATE fee_imports SET status='VALID' WHERE id=?", (imported,))
        con.commit()
        return profile_id
    except (ValueError, OSError, TypeError) as exc:
        con.execute("UPDATE fee_imports SET status='REJECTED',error=? WHERE id=?", (str(exc), imported))
        con.commit()
        raise


def current_profile(con, venue, source_id, side, *, now, hypothetical):
    # A newer profile supersedes an earlier one, even if it is expired/not yet effective.
    row = con.execute('''SELECT id,profile_json,sha256,reviewed_at,expires_at,hypothetical,import_id FROM fee_profiles
        WHERE venue=? AND source_id=? AND side=? ORDER BY id DESC LIMIT 1''', (venue, source_id, side)).fetchone()
    if row is None:
        raise ValueError('MISSING_FEE_PROFILE: ' + venue)
    profile_id, text, digest, reviewed, expires, flag, imported = row
    latest = con.execute('SELECT id FROM fee_imports WHERE venue=? AND source_id=? AND side=? ORDER BY id DESC LIMIT 1',
                         (venue, source_id, side)).fetchone()
    if latest is None or latest[0] != imported:
        raise ValueError('FEE_PROFILE_SUPERSEDED_BY_REFRESH')
    if bool(flag) != hypothetical or not utc_time(reviewed) <= now < utc_time(expires):
        raise ValueError('STALE_OR_INAPPLICABLE_FEE_PROFILE: ' + venue)
    if sha256(text.encode()).hexdigest() != digest:
        raise ValueError('fee profile hash mismatch')
    original = con.execute('SELECT raw_bytes,sha256,status FROM fee_imports WHERE id=?', (imported,)).fetchone()
    if not original or original[2] != 'VALID' or sha256(original[0]).hexdigest() != original[1]:
        raise ValueError('fee import provenance mismatch')
    docs = con.execute('SELECT raw_bytes,sha256 FROM fee_documents WHERE import_id=?', (imported,)).fetchall()
    if not docs or any(sha256(body).hexdigest() != expected for body, expected in docs):
        raise ValueError('fee source hash mismatch')
    data = load_json(text)
    if not hypothetical:
        validate_profile_capture(con, data, now=now)
    model = model_from_profile(data)
    model.check(venue=venue, source_id=source_id, side=side, now=now)
    return model, {'id': profile_id, 'sha256': digest, 'profile': load_json(text),
                   'source_hashes': [expected for _, expected in docs], 'provenance': 'OPERATOR_DECLARED_APPLICABILITY'}
