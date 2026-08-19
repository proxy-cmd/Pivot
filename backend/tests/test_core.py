import pytest
import pandas as pd
from backend.app.analytics import forecast, prepare_frame, profile_frame, scenario
from backend.app.autopilot import briefing_markdown, build_report, clean_frame
from backend.app.assistant import answer_question
from backend.app.rag import chunks, extract, retrieve
from backend.app.core.security import validate_readonly_sql
from backend.app.dataset_sql import deterministic_query
from backend.app.pipeline import apply


def test_forecast_has_intervals():
    result = forecast([10, 12, 14, 16])
    assert result['available'] and len(result['forecast']) == 3 and result['lower'][0] < result['upper'][0]


def test_scenario_moves_with_price():
    assert scenario(10, 0, 0, 1000)['revenue'] > 1000


def test_rag_retrieves_matching_source():
    result = retrieve('what is revenue', [{'source': 'sales.csv', 'content': 'Revenue was 120000 dollars in June.'}])
    assert result[0]['source'] == 'sales.csv'


def test_rag_extracts_business_glossary_text():
    result = extract('business-glossary.md', b'# Terms\nActive customer means an order in the last 45 days.')
    assert result and 'Active customer' in result[0]


def test_sql_blocks_writes():
    assert validate_readonly_sql('SELECT * FROM sales') == 'SELECT * FROM sales'
    with pytest.raises(ValueError): validate_readonly_sql('DELETE FROM sales')


def test_deterministic_sql_uses_the_dataset_schema():
    dataset = {
        'profile': {
            'columns_list': ['order_date', 'region', 'sales'],
            'schema': {
                'numeric_columns': ['sales'],
                'date_columns': ['order_date'],
            },
        },
    }

    query = deterministic_query('Show sales trend by month', dataset)

    assert query
    assert 'strftime' in query
    assert '"order_date"' in query
    assert '"sales"' in query


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


def test_assistant_can_forecast_and_flag_anomalies():
    frame = prepare_frame(pd.DataFrame({
        'order_date': pd.date_range('2025-01-01', periods=8, freq='MS'),
        'sales': [100, 110, 120, 130, 140, 150, 160, 1000],
    }))
    profile = profile_frame(frame, 'sales.csv')
    forecast_result = answer_question('Forecast the next months of sales', frame, profile)
    anomaly_result = answer_question('Show unusual sales outliers', frame, profile)
    assert forecast_result['intent'] == 'forecast'
    assert len(forecast_result['rows']) == 11
    assert anomaly_result['intent'] == 'anomaly'
    assert anomaly_result['rows']


def test_standardize_format_normalizes_dates_text_and_numbers():
    frame = pd.DataFrame({'order_date': ['2025/01/01', 'not-a-date'], 'product': [' A ', 'B'], 'sales': ['$1,200', '800']})
    cleaned, metrics = apply(frame, 'standardize_format')
    assert cleaned.loc[0, 'order_date'] == '2025-01-01'
    assert pd.isna(cleaned.loc[1, 'order_date'])
    assert cleaned.loc[0, 'product'] == 'A'
    assert cleaned.loc[0, 'sales'] == 1200
    assert metrics['invalid_dates_normalized'] == 1


def test_transformations_do_not_mutate_the_source_frame():
    source = pd.DataFrame({'product': [' A ', 'B '], 'sales': [100, 200]})

    cleaned, _ = apply(source, 'trim_text')

    assert source['product'].tolist() == [' A ', 'B ']
    assert cleaned['product'].tolist() == ['A', 'B']


def test_autopilot_creates_a_safe_retail_briefing_without_mutating_source():
    source = pd.DataFrame({
        'Order Date': ['2025/01/01', '2025/02/01', '2025/03/01', '2025/03/01'],
        'Order ID': ['A-1', 'A-2', 'A-3', 'A-3'],
        'Region': [' North ', 'South', 'South', 'South'],
        'Sales': ['$100', '$150', '$200', '$200'],
        'Profit': [20, 30, 40, 40],
    })
    cleaned, steps = clean_frame(prepare_frame(source))
    profile = profile_frame(cleaned, 'retail.csv')
    report = build_report(cleaned, profile, steps)

    assert len(source) == 4
    assert len(cleaned) == 3
    assert report['domain']['name'] == 'Dataset analysis'
    assert report['kpis']
    assert report['insights']
    assert 'Pivot Auto Pilot briefing' in briefing_markdown('retail.csv', report, profile)


def test_autopilot_never_displays_model_written_findings():
    frame = prepare_frame(pd.DataFrame({
        'order_date': ['2025-01-01', '2025-02-01'],
        'region': ['North', 'South'],
        'sales': [100, 200],
    }))
    profile = profile_frame(frame, 'sales.csv')
    report = build_report(frame, profile, [], {
        'metric': 'sales',
        'dimension': 'region',
        'date': 'order_date',
        'findings': ['Unverified claim that must never reach a customer.'],
        'headline': 'Unverified headline that must never reach a customer.',
    })

    text = ' '.join(item['text'] for item in report['insights']) + report['headline']
    assert 'Unverified' not in text
