"""Small, data-driven helpers for the Auto Pilot workflow."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from .analytics import _numeric_series, forecast
from .pipeline import apply


SAFE_OPS = {'sum', 'mean', 'median', 'min', 'max', 'count', 'nunique'}
MAX_FIELDS = 8


def plan_prompt(profile: dict[str, Any], facts: dict[str, Any]) -> str:
    """Ask the model for a plan, never for calculated answers."""
    schema = profile.get('schema', {})
    fields = schema.get('column_stats', [])[:60]
    context = {
        'rows': profile.get('rows'),
        'columns': fields,
        'date_fields': schema.get('date_columns', []),
        'numeric_fields': schema.get('numeric_columns', []),
        'identifier_fields': schema.get('candidate_ids', []),
        'calculated_facts': facts,
    }
    return f'''You are planning an analysis for an unknown dataset.
Use only this schema and field profile. Do not rely on business keyword lists.

{json.dumps(context, default=str)}

Return JSON only:
{{
  "dataset_type": "short neutral description of what this dataset appears to describe",
  "reason": "short explanation based on the available fields",
  "metric": "one exact numeric field name or null",
  "dimension": "one exact grouping field name or null",
  "date": "one exact date field name or null",
  "kpis": [
    {{"label": "short business-friendly label", "column": "exact field name", "operation": "sum|mean|median|min|max|count|nunique"}}
  ],
  "next_checks": ["up to three concise, evidence-safe next checks"]
}}

Choose fields only from the supplied profile. KPI labels must describe a calculation,
not assume a business definition that the data does not prove. Never invent a fact.'''


def explore(frame: pd.DataFrame, profile: dict[str, Any]) -> dict[str, Any]:
    """Calculate a compact fact pack for the AI planner and the UI."""
    schema = profile.get('schema', {})
    numbers = schema.get('numeric_columns', [])[:MAX_FIELDS]
    dates = schema.get('date_columns', [])[:2]
    ids = set(schema.get('candidate_ids', []))
    groups = [field for field in frame.columns if field not in numbers and field not in dates and field not in ids]
    groups = [field for field in groups if 2 <= frame[field].nunique(dropna=True) <= 50][:MAX_FIELDS]
    return {
        'numeric': numeric_facts(frame, numbers),
        'groups': group_facts(frame, groups),
        'time_series': time_facts(frame, dates, numbers),
        'relationships': relationships(frame, numbers),
        'quality_issues': profile.get('issues', []),
    }


def numeric_facts(frame: pd.DataFrame, fields: list[str]) -> list[dict[str, Any]]:
    facts = []
    for field in fields:
        values = _numeric_series(frame, field).dropna()
        if values.empty:
            continue
        facts.append({
            'field': field,
            'count': int(len(values)),
            'sum': round(float(values.sum()), 2),
            'mean': round(float(values.mean()), 2),
            'median': round(float(values.median()), 2),
            'min': round(float(values.min()), 2),
            'max': round(float(values.max()), 2),
        })
    return facts


def group_facts(frame: pd.DataFrame, fields: list[str]) -> list[dict[str, Any]]:
    facts = []
    for field in fields:
        values = frame[field].fillna('(blank)').astype(str).value_counts().head(3)
        facts.append({
            'field': field,
            'unique': int(frame[field].nunique(dropna=True)),
            'top_values': [{'label': str(label), 'count': int(count)} for label, count in values.items()],
        })
    return facts


def time_facts(frame: pd.DataFrame, dates: list[str], numbers: list[str]) -> list[dict[str, Any]]:
    facts = []
    for date in dates:
        for metric in numbers:
            trend = monthly_trend(frame, date, metric)
            if len(trend) < 2:
                continue
            previous, latest = trend[-2]['value'], trend[-1]['value']
            change = round((latest - previous) / abs(previous) * 100, 2) if previous else None
            facts.append({'date': date, 'metric': metric, 'periods': len(trend), 'latest': latest, 'change_pct': change})
    return facts[:MAX_FIELDS * 2]


def relationships(frame: pd.DataFrame, fields: list[str]) -> list[dict[str, Any]]:
    if len(fields) < 2:
        return []
    values = pd.DataFrame({field: _numeric_series(frame, field) for field in fields}).corr()
    pairs = []
    for index, left in enumerate(fields):
        for right in fields[index + 1:]:
            score = values.loc[left, right]
            if pd.notna(score):
                pairs.append({'left': left, 'right': right, 'correlation': round(float(score), 3)})
    return sorted(pairs, key=lambda item: abs(item['correlation']), reverse=True)[:5]


def clean_frame(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Apply only low-risk cleanup steps and keep an audit trail."""
    cleaned = frame.copy()
    steps = []
    actions = [
        ('standardize_format', 'Standardized text, dates, and numeric formats'),
        ('remove_duplicates', 'Removed exact duplicate rows'),
        ('normalize_columns', 'Normalized column names for analysis'),
    ]
    for action, label in actions:
        before = len(cleaned)
        cleaned, metrics = apply(cleaned, action)
        steps.append({
            'operation': action,
            'label': label,
            'rows_before': before,
            'rows_after': len(cleaned),
            'metrics': metrics,
        })
    return cleaned, steps


def build_report(frame: pd.DataFrame, profile: dict[str, Any], steps: list[dict[str, Any]], plan: dict[str, Any] | None = None, facts: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate the AI plan, then calculate the report from the dataframe."""
    plan = clean_plan(plan, profile)
    metric = plan['metric']
    charts = build_charts(frame, plan)
    facts = facts or explore(frame, profile)
    insights = build_insights(frame, profile, metric, charts, plan)
    return {
        'domain': {
            'name': plan['dataset_type'],
            'confidence': 'AI planned' if plan['from_ai'] else 'Profile planned',
            'evidence': plan['reason'],
        },
        'cleaning': steps,
        'kpis': build_kpis(frame, profile, plan),
        'charts': charts,
        'insights': insights,
        'recommendations': plan['next_checks'] or default_checks(profile, metric),
        'coverage': {
            'numeric_fields': len(facts['numeric']),
            'group_fields': len(facts['groups']),
            'time_series': len(facts['time_series']),
            'relationships': len(facts['relationships']),
        },
        'headline': insights[0]['text'] if insights else '',
    }


def clean_plan(raw: dict[str, Any] | None, profile: dict[str, Any]) -> dict[str, Any]:
    """Keep only model choices that match fields found in this dataset."""
    raw = raw if isinstance(raw, dict) else {}
    schema = profile.get('schema', {})
    fields = set(item.get('column') for item in schema.get('column_stats', []))
    numbers = [field for field in schema.get('numeric_columns', []) if field in fields]
    dates = [field for field in schema.get('date_columns', []) if field in fields]
    ids = set(schema.get('candidate_ids', []))
    groups = [field for field in fields if field not in numbers and field not in dates and field not in ids]
    metric = pick(raw.get('metric'), numbers)
    dimension = pick(raw.get('dimension'), groups)
    date = pick(raw.get('date'), dates)
    kpis = valid_kpis(raw.get('kpis'), fields)
    checks = [str(item).strip() for item in raw.get('next_checks', []) if str(item).strip()][:3]
    title = str(raw.get('dataset_type') or 'Dataset analysis').strip()[:80]
    reason = str(raw.get('reason') or 'Fields were selected from the detected schema and value profile.').strip()[:240]
    return {
        'from_ai': bool(raw),
        'dataset_type': title,
        'reason': reason,
        'metric': metric,
        'dimension': dimension,
        'date': date,
        'kpis': kpis,
        'next_checks': checks,
    }


def pick(value: Any, options: list[str]) -> str | None:
    return value if isinstance(value, str) and value in options else (options[0] if options else None)


def valid_kpis(items: Any, fields: set[str]) -> list[dict[str, str]]:
    result = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        column = item.get('column')
        operation = item.get('operation')
        label = str(item.get('label') or '').strip()
        if column in fields and operation in SAFE_OPS and label:
            result.append({'label': label[:60], 'column': column, 'operation': operation})
    return result[:3]


def build_kpis(frame: pd.DataFrame, profile: dict[str, Any], plan: dict[str, Any]) -> list[dict[str, Any]]:
    cards = [
        {'label': 'Clean rows', 'value': int(len(frame)), 'kind': 'count'},
        {'label': 'Quality score', 'value': int(profile.get('quality_score', 0)), 'kind': 'score', 'suffix': '/100'},
    ]
    items = plan['kpis'] or fallback_kpis(plan['metric'])
    for item in items:
        value = calculate(frame, item['column'], item['operation'])
        if value is not None:
            cards.append({'label': item['label'], 'value': value, 'kind': 'metric'})
    return cards[:5]


def fallback_kpis(metric: str | None) -> list[dict[str, str]]:
    if not metric:
        return []
    return [
        {'label': f'Total {pretty(metric)}', 'column': metric, 'operation': 'sum'},
        {'label': f'Average {pretty(metric)}', 'column': metric, 'operation': 'mean'},
    ]


def calculate(frame: pd.DataFrame, column: str, operation: str) -> float | int | None:
    values = _numeric_series(frame, column).dropna()
    if operation == 'count':
        return int(frame[column].notna().sum())
    if operation == 'nunique':
        return int(frame[column].nunique(dropna=True))
    if values.empty:
        return None
    value = getattr(values, operation)()
    return round(float(value), 2)


def build_charts(frame: pd.DataFrame, plan: dict[str, Any]) -> list[dict[str, Any]]:
    charts = []
    if plan['date'] and plan['metric']:
        trend = monthly_trend(frame, plan['date'], plan['metric'])
        if trend:
            charts.append({'type': 'line', 'title': f"{pretty(plan['metric']).title()} over time", 'data': trend})
    if plan['dimension'] and plan['metric']:
        bars = grouped_values(frame, plan['dimension'], plan['metric'])
        if bars:
            charts.append({'type': 'bar', 'title': f"{pretty(plan['metric']).title()} by {pretty(plan['dimension'])}", 'data': bars})
    if plan['metric']:
        histogram = distribution(frame, plan['metric'])
        if histogram:
            charts.append({'type': 'bar', 'title': f"Distribution of {pretty(plan['metric'])}", 'data': histogram})
    return charts


def distribution(frame: pd.DataFrame, metric: str) -> list[dict[str, Any]]:
    values = _numeric_series(frame, metric).dropna()
    if values.nunique() < 2:
        return []
    bins = min(12, max(4, int(len(values) ** 0.5)))
    counts = pd.cut(values, bins=bins, duplicates='drop').value_counts().sort_index()
    return [{'label': str(interval), 'value': int(count)} for interval, count in counts.items()]


def monthly_trend(frame: pd.DataFrame, date: str, metric: str) -> list[dict[str, Any]]:
    parsed = pd.to_datetime(frame[date], format='mixed', errors='coerce')
    values = _numeric_series(frame, metric)
    data = pd.DataFrame({'period': parsed.dt.to_period('M').astype('string'), 'value': values}).dropna()
    if data.empty:
        return []
    grouped = data.groupby('period', as_index=False)['value'].sum().tail(18)
    return chart_rows(grouped)


def grouped_values(frame: pd.DataFrame, dimension: str, metric: str) -> list[dict[str, Any]]:
    values = _numeric_series(frame, metric)
    data = pd.DataFrame({'label': frame[dimension].fillna('(blank)').astype(str), 'value': values}).dropna()
    if data.empty:
        return []
    grouped = data.groupby('label', as_index=False)['value'].sum().sort_values('value', ascending=False).head(8)
    return chart_rows(grouped)


def chart_rows(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return [{'label': str(row.iloc[0]), 'value': round(float(row.iloc[1]), 2)} for _, row in frame.iterrows()]


def build_insights(frame: pd.DataFrame, profile: dict[str, Any], metric: str | None, charts: list[dict[str, Any]], plan: dict[str, Any]) -> list[dict[str, str]]:
    # The model selects fields and calculations, but every displayed statement is
    # generated from locally calculated values. This keeps the briefing auditable.
    insights = []
    issues = profile.get('issues', [])
    if issues:
        issue = max(issues, key=lambda item: item.get('count', 0))
        insights.append({'type': 'quality', 'text': f"{pretty(issue['type']).title()} affects {issue['count']:,} records. {issue['impact']}"})
    if metric:
        value = calculate(frame, metric, 'sum')
        if value is not None:
            insights.append({'type': 'metric', 'text': f"{pretty(metric).title()} totals {value:,.2f} across usable records."})
    trend = next((chart['data'] for chart in charts if chart['type'] == 'line'), [])
    if len(trend) >= 2:
        add_trend_insight(insights, trend, metric)
    bars = next((chart['data'] for chart in charts if chart['type'] == 'bar'), [])
    if bars:
        top = bars[0]
        insights.append({'type': 'segment', 'text': f"{top['label']} has the largest measured value in the generated comparison: {top['value']:,.2f}."})
    if not insights:
        insights.append({'type': 'ready', 'text': 'The dataset is ready for a focused question or drill-down.'})
    return insights[:5]


def add_trend_insight(insights: list[dict[str, str]], trend: list[dict[str, Any]], metric: str | None) -> None:
    previous, latest = trend[-2]['value'], trend[-1]['value']
    if previous:
        change = (latest - previous) / abs(previous) * 100
        direction = 'increased' if change >= 0 else 'decreased'
        insights.append({'type': 'trend', 'text': f"{pretty(metric).title()} {direction} {abs(change):.1f}% in the latest period."})
    outlook = forecast([item['value'] for item in trend])
    if outlook.get('available'):
        insights.append({'type': 'forecast', 'text': f"A simple trend projection estimates the next period at {outlook['forecast'][0]:,.2f} ({outlook['confidence']} confidence)."})


def default_checks(profile: dict[str, Any], metric: str | None) -> list[str]:
    checks = ['Confirm what one row represents before making decisions from totals or averages.']
    if profile.get('issues'):
        checks.append('Review the remaining data-quality findings before using this version for a model or forecast.')
    if metric:
        checks.append(f"Use {pretty(metric)} as the starting point for a focused follow-up analysis.")
    return checks


def pretty(value: str | None) -> str:
    return str(value or 'value').replace('_', ' ')


def briefing_markdown(name: str, report: dict[str, Any], profile: dict[str, Any]) -> str:
    lines = [
        '# Pivot Auto Pilot briefing',
        '',
        f'**Dataset:** {name}',
        f"**Analysis focus:** {report['domain']['name']}",
        f"**Rows / columns:** {profile.get('rows', 0):,} / {profile.get('columns', 0):,}",
        f"**Quality score:** {profile.get('quality_score', 0)}/100",
        '',
        '## Executive summary',
        '',
    ]
    lines.extend(f"- {item['text']}" for item in report['insights'])
    lines.extend(['', '## Safe cleanup applied', ''])
    lines.extend(f"- {step['label']}: {step['rows_before']:,} to {step['rows_after']:,} rows." for step in report['cleaning'])
    lines.extend(['', '## Recommended next checks', ''])
    lines.extend(f'- {item}' for item in report['recommendations'])
    return '\n'.join(lines) + '\n'
