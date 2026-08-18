import pandas as pd
import pytest

from backend.app.dataset_analysis import run_analysis


def test_distribution_analysis_returns_stable_chart_and_metrics():
    result = run_analysis(pd.DataFrame({'sales': [10, 20, 30]}), {}, 'distribution', 'sales')

    assert result['kind'] == 'distribution'
    assert result['metrics']['mean'] == 20
    assert sum(point['value'] for point in result['chart']) == 3


def test_trend_analysis_requires_a_profiled_date_field():
    with pytest.raises(ValueError, match='date field'):
        run_analysis(pd.DataFrame({'sales': [10]}), {}, 'trend', 'sales')
