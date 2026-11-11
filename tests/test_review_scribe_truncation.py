"""AI Scribe says when the model stopped at its length limit."""
import json

import ai.assistant as assistant


class _FakeLlm:
    def __init__(self, reason):
        self.reason = reason

    def create_chat_completion(self, **kwargs):
        yield {"choices": [{"delta": {"content": "Partial "}, "finish_reason": None}]}
        yield {"choices": [{"delta": {"content": "text"}, "finish_reason": None}]}
        yield {"choices": [{"delta": {}, "finish_reason": self.reason}]}


def _stream(client, monkeypatch, reason):
    monkeypatch.setattr(assistant, '_llm', _FakeLlm(reason))
    monkeypatch.setattr(assistant, '_model_loaded', True)
    resp = client.post('/api/ai/process',
                       json={'action': 'proofread', 'text': 'some notes'})
    events = [json.loads(line[6:]) for line in resp.get_data(as_text=True).splitlines()
              if line.startswith('data: ')]
    return events


def test_stream_flags_a_result_cut_off_at_the_token_limit(client, app_db, monkeypatch):
    events = _stream(client, monkeypatch, 'length')
    assert ''.join(e.get('token', '') for e in events) == 'Partial text'
    assert events[-1] == {'done': True, 'truncated': True}


def test_stream_does_not_flag_a_result_that_finished(client, app_db, monkeypatch):
    assert _stream(client, monkeypatch, 'stop')[-1] == {'done': True, 'truncated': False}
