"""Offline replay helpers. Altered sequences and responses are HYPOTHETICAL test scenarios."""
from io import BytesIO
from email.message import Message
import json
from pathlib import Path
from predarb.validation import load_json

FIXTURES = Path(__file__).parent / 'fixtures'


def fixture(name):
    return json.loads((FIXTURES / (name + '.json')).read_text())


def payload(name):
    return load_json(fixture(name)['body'])


class Response(BytesIO):
    def __init__(self, body, code=200, headers=None):
        super().__init__(body)
        self.code = code
        self.headers = Message()
        for key, value in (headers or {'Content-Type': 'application/json'}).items():
            self.headers[key] = value


class Replay:
    """HYPOTHETICAL response sequence; never opens a socket."""
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        if not self.responses:
            raise AssertionError('unexpected network request: ' + request.full_url)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def real_response(name):
    entry = fixture(name)
    return Response(entry['body'].encode(), entry['status'], entry['headers'])


def drop_m4_tables(con):
    """Reconstruct a pre-M4 database for migration fixtures only."""
    for table in ('research_details', 'research_evaluations', 'research_cycles', 'research_sessions',
                  'research_audit', 'research_replays', 'fee_profiles', 'fee_documents', 'fee_imports'):
        con.execute('DROP TABLE ' + table)
