import pytest
import pandas as pd
from backend.app.analytics import forecast, prepare_frame, profile_frame, scenario
from backend.app.assistant import answer_question
from backend.app.rag import chunks, retrieve
from backend.app.security import validate_readonly_sql


def test_forecast_has_intervals():
    result = forecast([10, 12, 14, 16])
    assert result['available'] and len(result['forecast']) == 3 and result['lower'][0] < result['upper'][0]


def test_scenario_moves_with_price():
    assert scenario(10, 0, 0, 1000)['revenue'] > 1000


def test_rag_retrieves_matching_source():
    result = retrieve('what is revenue', [{'source': 'sales.csv', 'content': 'Revenue was 120000 dollars in June.'}])
    assert result[0]['source'] == 'sales.csv'


def test_sql_blocks_writes():
    assert validate_readonly_sql('SELECT * FROM sales') == 'SELECT * FROM sales'
    with pytest.raises(ValueError): validate_readonly_sql('DELETE FROM sales')


def test_assistant_returns_visual_breakdown_for_natural_language():
    frame = prepare_frame(pd.DataFrame({
        'order_date': ['2025-01-01', '2025-01-02', '2025-01-03', '2025-01-04'],
        'product': ['A', 'A', 'B', 'B'],
        'sales': [100, 150, 80, 90],
    }))
    profile = profile_frame(frame, 'sales.csv')
    result = answer_question('Which product sales are highest?', frame, profile)
    assert result['intent'] == 'breakdown'
    assert result['rows'][0]['group'] == 'A'
    assert result['visualization']['type'] == 'bar'


def test_assistant_explains_largest_time_drop_and_driver():
    frame = prepare_frame(pd.DataFrame({
        'order_date': ['2025-01-01', '2025-01-02', '2025-02-01', '2025-02-02', '2025-03-01'],
        'product': ['A', 'B', 'A', 'B', 'A'],
        'sales': [100, 100, 90, 80, 30],
    }))
    profile = profile_frame(frame, 'sales.csv')
    result = answer_question('When did sales drop the most, and what changed?', frame, profile)
    assert result['intent'] == 'change'
    assert result['rows'][0]['period'] == '2025-03'
    assert result['driver_rows']
    assert result['visualization']['type'] == 'line'
