import pytest
from backend.app.analytics import forecast, scenario
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
