from __future__ import annotations

"""Dataset-aware question answering used by the Pivot Analyst.

The analyst deliberately calculates answers from the active dataframe. SQL is
still returned as a transparent, read-only trace, but the user-facing answer
is a structured result rather than a query-generation demo.
"""

import re
from typing import Any

import pandas as pd

from .analytics import _numeric_series


MONEY_WORDS = ("revenue", "sales", "amount", "price", "cost", "profit", "margin", "total", "value")
TIME_WORDS = ("month", "monthly", "date", "time", "trend", "year", "quarter", "week", "period", "season")
GROUP_WORDS = ("product", "category", "region", "country", "customer", "segment", "channel", "department", "store", "city", "state", "brand", "sku", "name")


def quote(identifier: str) -> str:
    return '"' + str(identifier).replace('"', '""') + '"'


def _normal(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()


def _schema(profile: dict[str, Any], frame: pd.DataFrame) -> tuple[list[str], list[str]]:
    detected = profile.get("schema", {})
    dates = [column for column in detected.get("date_columns", []) if column in frame.columns]
    numeric = [column for column in detected.get("numeric_columns", []) if column in frame.columns and column not in dates]
    return dates, numeric


def _date_column(frame: pd.DataFrame, profile: dict[str, Any]) -> str | None:
    dates, _ = _schema(profile, frame)
    if dates:
        return dates[0]
    # A date can be present in a generically named field, so use a conservative
    # value-based fallback when the profiler did not identify it.
    for column in frame.columns:
        parsed = pd.to_datetime(frame[column], format="mixed", errors="coerce")
        if parsed.notna().mean() >= 0.8 and parsed.nunique(dropna=True) >= 3:
            return str(column)
    return None


def _metric(frame: pd.DataFrame, profile: dict[str, Any], question: str) -> str | None:
    _, numeric = _schema(profile, frame)
    if not numeric:
        return None
    words = set(_normal(question).split())
    explicit = [column for column in numeric if _normal(column) in _normal(question)]
    if explicit:
        return explicit[0]
    scored = []
    for column in numeric:
        name = _normal(column)
        score = sum(3 for word in MONEY_WORDS if word in name and word in words)
        score += sum(1 for word in MONEY_WORDS if word in name)
        if any(term in words for term in ("count", "number", "how many", "orders")) and "quantity" in name:
            score += 2
        scored.append((score, column))
    return max(scored, key=lambda item: item[0])[1]


def _dimension(frame: pd.DataFrame, profile: dict[str, Any], question: str) -> str | None:
    dates, numeric = _schema(profile, frame)
    candidates = [str(column) for column in frame.columns if column not in dates and column not in numeric]
    if not candidates:
        return None
    question_text = _normal(question)
    explicit = [column for column in candidates if _normal(column) in question_text]
    if explicit:
        return explicit[0]
    scored = []
    for column in candidates:
        name = _normal(column)
        score = sum(3 for word in GROUP_WORDS if word in name and word in question_text)
        score += sum(1 for word in GROUP_WORDS if word in name)
        # High-cardinality identifiers are rarely useful as a first grouping.
        unique_ratio = frame[column].nunique(dropna=True) / max(len(frame), 1)
        if unique_ratio > 0.9:
            score -= 2
        scored.append((score, -unique_ratio, column))
    return max(scored, key=lambda item: (item[0], item[1]))[2]


def _period_values(frame: pd.DataFrame, date_column: str, metric: str, question: str) -> tuple[pd.DataFrame, str]:
    parsed = pd.to_datetime(frame[date_column], format="mixed", errors="coerce")
    values = _numeric_series(frame, metric)
    period = "M"
    normalized = _normal(question)
    if "year" in normalized or "annual" in normalized:
        period = "Y"
    elif "quarter" in normalized:
        period = "Q"
    elif "week" in normalized:
        period = "W"
    grouped = pd.DataFrame({"date": parsed, "value": values}).dropna()
    grouped["period"] = grouped["date"].dt.to_period(period).astype(str)
    result = grouped.groupby("period", as_index=False)["value"].sum()
    result["value"] = result["value"].round(2)
    return result, {"M": "monthly", "Q": "quarterly", "W": "weekly", "Y": "yearly"}[period]


def _chart(chart_type: str, title: str, data: list[dict[str, Any]], x: str = "label", y: str = "value") -> dict[str, Any]:
    return {"type": chart_type, "title": title, "data": data, "x": x, "y": y}


def _base(profile: dict[str, Any], frame: pd.DataFrame) -> dict[str, Any]:
    return {
        "dataset_rows": int(len(frame)),
        "dataset_columns": int(len(frame.columns)),
        "quality_score": profile.get("quality_score"),
    }


def answer_question(question: str, frame: pd.DataFrame, profile: dict[str, Any]) -> dict[str, Any]:
    question = question.strip()
    normalized = _normal(question)
    lower = normalized.split()
    dates, numeric = _schema(profile, frame)
    date_column = _date_column(frame, profile)
    metric = _metric(frame, profile, question)
    dimension = _dimension(frame, profile, question)
    base = _base(profile, frame)

    if normalized in {"hi", "hello", "hey", "hiya", "good morning", "good afternoon", "good evening"}:
        return {"answer": f"Hi! I’m Pivot Analyst. I’ve loaded {len(frame):,} rows across {len(frame.columns)} columns. Ask me about trends, products, regions, quality, or any numeric field.", "insights": [], "visualization": None, "rows": [], "sql": None, "intent": "conversation", "evidence": base}
    if any(phrase in normalized for phrase in ("who are you", "what can you do", "what are you")):
        return {"answer": "I’m Pivot Analyst. I inspect the active dataset, calculate answers from its actual values, show the supporting records or chart, and explain what the evidence does—and does not—show.", "insights": [], "visualization": None, "rows": [], "sql": None, "intent": "conversation", "evidence": base}

    if any(word in normalized for word in ("quality", "missing", "duplicate", "duplicates", "clean", "messy", "null")):
        issues = profile.get("issues", [])
        if not issues:
            answer = "The dataset has no detected quality findings in the current profile. That does not prove every value is correct, but completeness, exact duplicates, date parsing, and the configured outlier checks are clear."
        else:
            details = "; ".join(f"{issue['type'].replace('_', ' ')} ({issue['count']:,})" for issue in issues)
            answer = f"I found {len(issues)} quality finding(s): {details}. Review these before using the data for final reporting."
        return {"answer": answer, "insights": [issue["impact"] for issue in issues[:4]], "visualization": None, "rows": issues, "sql": "SELECT * FROM dataset LIMIT 1", "intent": "quality", "evidence": base | {"issues": issues}}

    if any(word in normalized for word in ("correlation", "correlate", "relationship", "related")) and len(numeric) >= 2:
        correlations = frame[numeric].apply(lambda values: _numeric_series(frame, values.name)).corr().fillna(0)
        pairs = []
        for index, first in enumerate(numeric):
            for second in numeric[index + 1:]:
                pairs.append({"field_1": first, "field_2": second, "correlation": round(float(correlations.loc[first, second]), 3)})
        pairs.sort(key=lambda row: abs(row["correlation"]), reverse=True)
        strongest = pairs[0] if pairs else None
        answer = f"The strongest observed relationship is between {strongest['field_1']} and {strongest['field_2']} (correlation {strongest['correlation']:.3f}). Correlation is association, not proof that one field causes the other." if strongest else "There are not enough complete numeric fields to calculate a relationship."
        return {"answer": answer, "insights": [], "visualization": None, "rows": pairs[:20], "sql": "SELECT * FROM dataset LIMIT 200", "intent": "correlation", "evidence": base}

    if any(word in normalized for word in ("how many rows", "row count", "number of rows", "how many records", "records are")):
        count = len(frame)
        return {"answer": f"The active dataset contains {count:,} rows and {len(frame.columns):,} columns.", "insights": [], "visualization": None, "rows": [{"rows": count, "columns": len(frame.columns)}], "sql": "SELECT COUNT(*) AS rows FROM dataset", "intent": "profile", "evidence": base}

    drop_question = any(word in normalized for word in ("drop", "dropped", "decline", "declined", "fell", "fall", "decrease", "decreased", "worst month", "lowest month"))
    if drop_question and date_column and metric:
        periods, cadence = _period_values(frame, date_column, metric, question)
        periods["previous"] = periods["value"].shift(1).round(2)
        periods["change"] = (periods["value"] - periods["previous"]).round(2)
        periods["change_pct"] = (periods["change"] / periods["previous"].replace(0, pd.NA) * 100).round(2)
        changes = periods.dropna(subset=["previous"]).sort_values("change")
        if changes.empty:
            return {"answer": "There are not enough consecutive time periods to measure a drop.", "insights": [], "visualization": None, "rows": [], "sql": None, "intent": "change", "evidence": base}
        worst = changes.iloc[0].to_dict()
        answer = f"{worst['period']} had the largest {cadence} drop in {metric}: {worst['change']:,.2f} ({worst['change_pct']:.2f}% versus {worst['previous']:,.2f} in the prior period)."
        insights = [f"The period moved from {worst['previous']:,.2f} to {worst['value']:,.2f}."]
        driver_rows: list[dict[str, Any]] = []
        previous_period = changes.iloc[0]["period"]
        ordered_periods = periods["period"].tolist()
        position = ordered_periods.index(worst["period"])
        if position > 0 and dimension:
            previous_label = ordered_periods[position - 1]
            parsed = pd.to_datetime(frame[date_column], format="mixed", errors="coerce")
            frame_copy = frame.copy()
            frame_copy["__period"] = parsed.dt.to_period({"monthly": "M", "quarterly": "Q", "weekly": "W", "yearly": "Y"}[cadence]).astype(str)
            frame_copy["__metric"] = _numeric_series(frame_copy, metric)
            current = frame_copy[frame_copy["__period"] == worst["period"]].groupby(dimension)["__metric"].sum()
            previous = frame_copy[frame_copy["__period"] == previous_label].groupby(dimension)["__metric"].sum()
            driver = pd.concat({"current": current, "previous": previous}, axis=1).fillna(0)
            driver["change"] = (driver["current"] - driver["previous"]).round(2)
            driver = driver.sort_values("change").head(8)
            driver_rows = [{"group": str(index), "current": round(float(row["current"]), 2), "previous": round(float(row["previous"]), 2), "change": round(float(row["change"]), 2)} for index, row in driver.iterrows()]
            if driver_rows:
                insights.append(f"The largest observed associated driver was {driver_rows[0]['group']} ({driver_rows[0]['change']:,.2f} versus the prior period). This is an association in the data, not proof of causation.")
        rows = [{"period": str(row["period"]), "value": float(row["value"]), "previous": float(row["previous"]), "change": float(row["change"]), "change_pct": float(row["change_pct"]) if pd.notna(row["change_pct"]) else None} for _, row in changes.head(12).iterrows()]
        chart_data = [{"label": str(row["period"]), "value": float(row["value"])} for _, row in periods.iterrows()]
        sql = f"SELECT strftime('%Y-%m', {quote(date_column)}) AS period, SUM({quote(metric)}) AS value FROM dataset GROUP BY period ORDER BY period"
        return {"answer": answer, "insights": insights, "visualization": _chart("line", f"{cadence.title()} {metric}", chart_data), "rows": rows, "driver_rows": driver_rows, "sql": sql, "intent": "change", "evidence": base | {"date_column": date_column, "metric": metric}}

    if date_column and metric and any(word in normalized for word in TIME_WORDS):
        periods, cadence = _period_values(frame, date_column, metric, question)
        peak = periods.loc[periods["value"].idxmax()]
        low = periods.loc[periods["value"].idxmin()]
        answer = f"Across {len(periods)} {cadence} periods, {metric} totaled {periods['value'].sum():,.2f}. The highest was {peak['period']} at {peak['value']:,.2f}; the lowest was {low['period']} at {low['value']:,.2f}."
        rows = [{"period": str(row["period"]), "value": float(row["value"])} for _, row in periods.iterrows()]
        sql = f"SELECT strftime('%Y-%m', {quote(date_column)}) AS period, SUM({quote(metric)}) AS value FROM dataset GROUP BY period ORDER BY period"
        return {"answer": answer, "insights": [f"The highest period is {peak['period']}.", f"The lowest period is {low['period']}.", f"Average per period: {periods['value'].mean():,.2f}."] , "visualization": _chart("line", f"{cadence.title()} {metric}", [{"label": str(row["period"]), "value": float(row["value"])} for _, row in periods.iterrows()]), "rows": rows, "sql": sql, "intent": "trend", "evidence": base | {"date_column": date_column, "metric": metric}}

    grouped_question = any(word in normalized for word in ("by", "per", "each", "which", "top", "highest", "most", "best", "lowest", "bottom", "compare"))
    if grouped_question and metric and dimension:
        values = frame.copy()
        values["__metric"] = _numeric_series(values, metric)
        grouped = values.groupby(dimension, dropna=False)["__metric"].agg(["sum", "count"]).reset_index().rename(columns={"sum": "value"})
        grouped[dimension] = grouped[dimension].fillna("(blank)").astype(str)
        descending = not any(word in normalized for word in ("lowest", "bottom", "least", "smallest"))
        grouped = grouped.sort_values("value", ascending=not descending).head(20)
        top = grouped.iloc[0]
        direction = "highest" if descending else "lowest"
        answer = f"{top[dimension]} has the {direction} {metric}: {top['value']:,.2f} across {int(top['count']):,} rows."
        rows = [{"group": str(row[dimension]), "value": round(float(row["value"]), 2), "rows": int(row["count"])} for _, row in grouped.iterrows()]
        sql = f"SELECT {quote(dimension)} AS group_name, SUM({quote(metric)}) AS value, COUNT(*) AS rows FROM dataset GROUP BY {quote(dimension)} ORDER BY value {'DESC' if descending else 'ASC'} LIMIT 20"
        return {"answer": answer, "insights": [f"The top group represents {top['value'] / grouped['value'].sum() * 100:.1f}% of the displayed group total."], "visualization": _chart("bar", f"{metric} by {dimension}", [{"label": row["group"], "value": row["value"]} for row in rows]), "rows": rows, "sql": sql, "intent": "breakdown", "evidence": base | {"dimension": dimension, "metric": metric}}

    if metric and any(word in normalized for word in ("sum", "total", "revenue", "sales", "amount", "average", "mean", "median", "maximum", "minimum", "max", "min")):
        values = _numeric_series(frame, metric).dropna()
        if len(values):
            if any(word in normalized for word in ("average", "mean")):
                operation, value = "average", float(values.mean())
                sql_operation = "AVG"
            elif "median" in normalized:
                operation, value = "median", float(values.median())
                sql_operation = None
            elif any(word in normalized for word in ("minimum", "min")):
                operation, value = "minimum", float(values.min())
                sql_operation = "MIN"
            elif any(word in normalized for word in ("maximum", "max")):
                operation, value = "maximum", float(values.max())
                sql_operation = "MAX"
            else:
                operation, value = "total", float(values.sum())
                sql_operation = "SUM"
            sql = f"SELECT {sql_operation}({quote(metric)}) AS value FROM dataset" if sql_operation else f"SELECT * FROM dataset LIMIT 200"
            return {"answer": f"The {operation} {metric} is {value:,.2f}, calculated from {len(values):,} usable values.", "insights": [f"Usable values: {len(values):,}; missing or non-numeric values excluded: {len(frame) - len(values):,}."], "visualization": None, "rows": [{"metric": metric, "operation": operation, "value": round(value, 2)}], "sql": sql, "intent": "aggregate", "evidence": base | {"metric": metric}}

    sample = frame.head(20).fillna("")
    rows = sample.to_dict(orient="records")
    fields = ", ".join(str(column) for column in frame.columns[:8])
    return {"answer": f"I can investigate this dataset, but I couldn’t map that request to a reliable calculation yet. Available fields include {fields}. Try asking for a trend, total, average, top product/category, largest drop, quality issues, or correlation.", "insights": [], "visualization": _chart("table", "Dataset preview", [{"label": str(index + 1), "value": 1} for index in range(min(len(rows), 20))]), "rows": rows, "sql": "SELECT * FROM dataset LIMIT 20", "intent": "clarification", "evidence": base}
