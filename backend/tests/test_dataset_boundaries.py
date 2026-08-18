import pandas as pd

from backend.app.dataset_io import available_analyses, profile_payload
from backend.app.dataset_sql import deterministic_query, execute_query


def test_dataset_profile_response_keeps_recommendations_with_the_profile():
    frame = pd.DataFrame({'sales': [10, None], 'region': ['North', 'South']})

    result = profile_payload(frame, 'sales.csv', 'dataset-1')

    assert result['dataset_id'] == 'dataset-1'
    assert result['columns_list'] == ['sales', 'region']
    assert any(item['operation'] == 'fill_missing' for item in result['recommendations'])
    assert available_analyses(frame, result)


def test_readonly_dataset_sql_executes_against_the_dataframe():
    frame = pd.DataFrame({'sales': [10, 20], 'region': ['North', 'South']})
    item = {'profile': {'columns_list': ['sales', 'region'], 'schema': {'numeric_columns': ['sales'], 'date_columns': []}}}

    query = deterministic_query('What is total sales?', item)

    assert query == 'SELECT SUM("sales") AS value FROM dataset'
    assert execute_query(frame, query)['rows'] == [{'value': 30}]
