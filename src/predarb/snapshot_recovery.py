"""Opt-in M5P market-data snapshot requests; no order/account commands.

Commands are archived before send. Acknowledgments advance only protocol
frontiers, never book freshness. Production book inspection rejects this
experimental control-message path; the isolated quality replay supports it.
"""
from .kalshi_auth import WS_URL
from .store import archive_response, validate_observation
from .validation import dumps, load_json
import hashlib

COMMAND_SCHEMA = 'kalshi-snapshot-command/m5p-v1'
POLICIES = ('reconnect', 'inband-snapshot')


def command(source, sid, command_id):
    return dict(id=command_id, cmd='update_subscription', params=dict(
        sid=sid, market_tickers=[source], action='get_snapshot'))


def archive_command(con, connection, source, sid, command_id, at):
    body = dumps(dict(connection_id=connection, command=command(source,sid,command_id))).encode()
    oid = archive_response(con,'kalshi',WS_URL,body,0,{},at,COMMAND_SCHEMA)
    validate_observation(con,oid,'VALID',None)
    return oid


def load_command(con, oid, connection, source, sid, before):
    row = con.execute('SELECT raw_body,body_sha256,ts_utc,schema_version,validation_status FROM raw_observations WHERE id=?',(oid,)).fetchone()
    if not row or hashlib.sha256(row[0]).hexdigest()!=row[1] or row[3:]!=(COMMAND_SCHEMA,'VALID'):
        raise ValueError('invalid snapshot command provenance')
    from .validation import utc_time
    if utc_time(row[2])>utc_time(before): raise ValueError('command after response')
    data=load_json(row[0]);request=data['command']
    if (data['connection_id']!=connection or type(request.get('id')) is not int or request['id']<2
            or request!=command(source,sid,request['id'])):
        raise ValueError('snapshot command identity mismatch')
    return request


def acknowledge(stream, frame, request):
    """Require a matching command; optional control sequence must be contiguous."""
    if frame.get('type')!='ok' or frame.get('id')!=request['id']:
        raise ValueError('unmatched snapshot acknowledgment')
    if 'sid' in frame and frame['sid']!=request['params']['sid']:
        raise ValueError('snapshot acknowledgment subscription mismatch')
    msg=frame.get('msg',{})
    if set(msg)-{'market_tickers'} or ('market_tickers' in msg and msg['market_tickers']!=[stream.source_id]):
        raise ValueError('snapshot acknowledgment market mismatch')
    if 'seq' in frame:
        seq=frame['seq']
        if type(seq) is not int or stream.seq is None or seq!=stream.seq+1:
            raise ValueError('snapshot acknowledgment sequence gap')
        stream.seq=stream.high_seq=seq
    if 'sending_ts_ms' in frame:
        sent=frame['sending_ts_ms']
        if type(sent) is not int or not 0<=sent<=253402300799999 or (stream.last_send_ms is not None and sent<stream.last_send_ms):
            raise ValueError('snapshot acknowledgment timestamp regression')
        stream.last_send_ms=sent


class Recovery:
    """One pending request, >=5s request spacing, 5s response deadline."""
    def __init__(self, started):
        self.last_book=self.last_snapshot=self.last_request=started
        self.pending=None
        self.next_id=2
        self.requests={}
        self.acknowledged=set()

    def due(self, at, sid):
        return (sid is not None and self.pending is None and at-self.last_request>=5
                and (at-self.last_book>=5 or at-self.last_snapshot>=25))

    def timed_out(self, at):
        return self.pending is not None and at-self.last_request>=5

    def sent(self, at, observation):
        self.pending=self.next_id;self.requests[self.next_id]=observation
        self.next_id+=1;self.last_request=at

    def book(self, at, snapshot):
        self.last_book=at
        if snapshot:
            self.last_snapshot=at;self.pending=None
