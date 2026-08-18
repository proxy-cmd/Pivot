from backend.app.gemini import parse_json_object


def test_parse_json_object_accepts_raw_and_fenced_responses():
    assert parse_json_object('{"intent": "general_chat"}') == {'intent': 'general_chat'}
    assert parse_json_object('```json\n{"intent": "sql"}\n```') == {'intent': 'sql'}


def test_parse_json_object_rejects_non_json_responses():
    assert parse_json_object('I cannot answer that.') is None
