from __future__ import annotations

"""Dataset-aware question answering used by the Pivot Analyst.

The analyst calculates answers from the active dataframe. It supports
conversation memory so follow-up questions ("why?", "tell me more") can
reference prior answers. The Gemini LLM is used as an intelligent
fallback for free-form reasoning.
"""

import re
import json
from typing import Any

import pandas as pd

from .analytics import _numeric_series, forecast


MONEY_WORDS = ("revenue", "sales", "amount", "price", "cost", "profit", "margin", "total", "value")
TIME_WORDS = ("month", "monthly", "date", "time", "trend", "year", "quarter", "week", "period", "season")
GROUP_WORDS = ("product", "category", "region", "country", "customer", "segment", "channel", "department", "store", "city", "state", "brand", "sku", "name")
WHY_WORDS = ("why", "reason", "cause", "explain", "how come", "what happened", "tell me more", "elaborate", "can you tell", "what changed", "what caused")
CONVERSATIONAL = ("hi", "hello", "hey", "hiya", "good morning", "good afternoon", "good evening", "thanks", "thank you", "ok", "okay", "got it", "cool", "nice")


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


def json_safe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return json.loads(json.dumps(rows, default=str))


def _base(profile: dict[str, Any], frame: pd.DataFrame) -> dict[str, Any]:
    return {
        "dataset_rows": int(len(frame)),
        "dataset_columns": int(len(frame.columns)),
        "quality_score": profile.get("quality_score"),
    }


def _is_why_question(question: str) -> bool:
    """Check if the question is asking for an explanation of a previous result."""
    normalized = _normal(question)
    return any(phrase in normalized for phrase in WHY_WORDS)


def _is_followup(question: str) -> bool:
    """Check if this is a short follow-up that references prior context."""
    normalized = _normal(question)
    words = normalized.split()
    if len(words) <= 6:
        return True
    followup_signals = ("it", "that", "this", "those", "the result", "above",
                        "previous", "last answer", "you said", "you mentioned",
                        "more detail", "more about", "dig deeper")
    return any(signal in normalized for signal in followup_signals)


def _build_why_analysis(frame: pd.DataFrame, profile: dict[str, Any],
                         question: str, history: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Try to build a data-driven 'why' explanation from the prior answer context."""
    base = _base(profile, frame)
    date_column = _date_column(frame, profile)
    metric = _metric(frame, profile, question)
    dimension = _dimension(frame, profile, question)

    # Look for the most recent assistant message with actual data
    prior_answer = None
    prior_data = None
    for entry in reversed(history or []):
        if entry.get("role") == "assistant" and entry.get("text"):
            prior_answer = entry["text"]
            prior_data = entry.get("data", {})
            break

    if not prior_answer:
        return None

    # Try to build a breakdown analysis to explain "why"
    if date_column and metric and dimension:
        try:
            parsed = pd.to_datetime(frame[date_column], format="mixed", errors="coerce")
            values = _numeric_series(frame, metric)
            frame_copy = frame.copy()
            frame_copy["__date"] = parsed
            frame_copy["__metric"] = values
            frame_copy["__year"] = parsed.dt.year

            # Group by dimension and time to find what drove changes
            yearly = frame_copy.groupby(["__year", dimension])["__metric"].sum().reset_index()
            yearly.columns = ["year", "group", "value"]
            yearly = yearly.dropna()

            if len(yearly) >= 2:
                # Find biggest movers
                pivot = yearly.pivot_table(index="group", columns="year", values="value", aggfunc="sum").fillna(0)
                if pivot.shape[1] >= 2:
                    years = sorted(pivot.columns)
                    pivot["change"] = pivot[years[-1]] - pivot[years[-2]]
                    pivot["change_pct"] = ((pivot["change"] / pivot[years[-2]].replace(0, pd.NA)) * 100).round(1)
                    top_drivers = pivot.sort_values("change", ascending=False).head(5)
                    bottom_drivers = pivot.sort_values("change").head(5)

                    driver_rows = []
                    for group_name, row in top_drivers.iterrows():
                        driver_rows.append({
                            "group": str(group_name),
                            f"{years[-2]}": round(float(row[years[-2]]), 2),
                            f"{years[-1]}": round(float(row[years[-1]]), 2),
                            "change": round(float(row["change"]), 2),
                            "change_%": f"{row['change_pct']:.1f}%" if pd.notna(row["change_pct"]) else "N/A"
                        })

                    decline_rows = []
                    for group_name, row in bottom_drivers.iterrows():
                        if row["change"] < 0:
                            decline_rows.append({
                                "group": str(group_name),
                                f"{years[-2]}": round(float(row[years[-2]]), 2),
                                f"{years[-1]}": round(float(row[years[-1]]), 2),
                                "change": round(float(row["change"]), 2),
                                "change_%": f"{row['change_pct']:.1f}%" if pd.notna(row["change_pct"]) else "N/A"
                            })

                    # Build explanation
                    top_grower = driver_rows[0] if driver_rows else None
                    top_decliner = decline_rows[0] if decline_rows else None

                    explanation_parts = [
                        f"Looking at {metric} broken down by {dimension} between {years[-2]} and {years[-1]}:"
                    ]
                    if top_grower:
                        explanation_parts.append(
                            f"• The biggest growth came from **{top_grower['group']}** "
                            f"(+{top_grower['change']:,.2f}, {top_grower['change_%']})."
                        )
                    if top_decliner:
                        explanation_parts.append(
                            f"• The largest decline was in **{top_decliner['group']}** "
                            f"({top_decliner['change']:,.2f}, {top_decliner['change_%']})."
                        )

                    if len(driver_rows) > 1:
                        other_growers = [r["group"] for r in driver_rows[1:3] if r["change"] > 0]
                        if other_growers:
                            explanation_parts.append(
                                f"• Other notable growth areas: {', '.join(other_growers)}."
                            )

                    explanation_parts.append(
                        "\nNote: This analysis shows correlation in the data. "
                        "The actual business reasons (promotions, market changes, etc.) "
                        "would need domain knowledge to confirm."
                    )

                    answer = "\n".join(explanation_parts)

                    chart_data = []
                    for group_name, row in top_drivers.head(8).iterrows():
                        chart_data.append({"label": str(group_name), "value": round(float(row["change"]), 2)})

                    return {
                        "answer": answer,
                        "insights": [
                            f"Analyzed {metric} by {dimension} across {len(years)} periods.",
                            f"Top driver: {top_grower['group']} with {top_grower['change']:+,.2f} change." if top_grower else "No clear top driver found.",
                        ],
                        "visualization": _chart("bar", f"Change in {metric} by {dimension} ({years[-2]}→{years[-1]})", chart_data) if chart_data else None,
                        "rows": driver_rows[:10],
                        "driver_rows": decline_rows[:8] if decline_rows else [],
                        "sql": f"SELECT {quote(dimension)}, SUM(CASE WHEN strftime('%Y',{quote(date_column)})='{years[-2]}' THEN {quote(metric)} END) AS prev, SUM(CASE WHEN strftime('%Y',{quote(date_column)})='{years[-1]}' THEN {quote(metric)} END) AS curr FROM dataset GROUP BY {quote(dimension)} ORDER BY (curr-prev) DESC LIMIT 20",
                        "intent": "why_analysis",
                        "evidence": base | {"metric": metric, "dimension": dimension, "date_column": date_column},
                    }
        except Exception:
            pass

    return None


def answer_question(question: str, frame: pd.DataFrame, profile: dict[str, Any],
                     history: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Answer a data question. Accepts conversation history for follow-up context."""
    question = question.strip()
    normalized = _normal(question)
    lower = normalized.split()
    dates, numeric = _schema(profile, frame)
    date_column = _date_column(frame, profile)
    metric = _metric(frame, profile, question)
    dimension = _dimension(frame, profile, question)
    base = _base(profile, frame)
    history = history or []

    # --- "Why" / Explanation questions (uses conversation history) ---
    if _is_why_question(question) and history:
        why_result = _build_why_analysis(frame, profile, question, history)
        if why_result:
            return why_result
        # If we can't build a deterministic why-analysis, signal to use Gemini
        # Gather prior context for the LLM
        prior_texts = []
        for entry in history[-6:]:
            role = entry.get("role", "")
            text = entry.get("text", "")
            if text:
                prior_texts.append(f"{role}: {text}")
        context_summary = "\n".join(prior_texts)
        return {
            "answer": "",
            "insights": [],
            "visualization": None,
            "rows": [],
            "sql": None,
            "intent": "needs_gemini",
            "evidence": base,
            "conversation_context": context_summary,
        }

    # --- Dataset orientation ---
    if any(phrase in normalized for phrase in ("what is this data", "what this data", "what is this dataset", "describe this data", "describe this dataset", "data about", "data is all about", "dataset about", "tell me about this data")):
        dimensions = [str(column) for column in frame.columns if column not in dates and column not in numeric]
        field_summary = []
        if dates:
            field_summary.append(f"{len(dates)} date field{'s' if len(dates) != 1 else ''} ({', '.join(dates[:3])})")
        if numeric:
            field_summary.append(f"{len(numeric)} numeric measure{'s' if len(numeric) != 1 else ''} ({', '.join(numeric[:4])})")
        if dimensions:
            field_summary.append(f"{len(dimensions)} descriptive field{'s' if len(dimensions) != 1 else ''} ({', '.join(dimensions[:4])})")
        issues = profile.get("issues", [])
        quality_note = f" It currently has {len(issues)} detected quality finding(s) to review." if issues else " No profile-level quality findings are currently detected."
        answer = f"This dataset has {len(frame):,} rows and {len(frame.columns):,} fields. It contains " + ("; ".join(field_summary) if field_summary else "fields that Pivot could not confidently classify") + "." + quality_note
        return {"answer": answer, "insights": ["Ask a specific question about a field, a group, a time period, or data quality to investigate further."], "visualization": None, "rows": [], "sql": None, "intent": "dataset_orientation", "evidence": base | {"dates": dates, "numeric": numeric, "dimensions": dimensions[:20]}}

    # --- Quality questions ---
    if any(word in normalized for word in ("quality", "missing", "duplicate", "duplicates", "clean", "messy", "null")):
        issues = profile.get("issues", [])
        if not issues:
            answer = "The dataset has no detected quality findings in the current profile. That does not prove every value is correct, but completeness, exact duplicates, date parsing, and the configured outlier checks are clear."
        else:
            details = "; ".join(f"{issue['type'].replace('_', ' ')} ({issue['count']:,})" for issue in issues)
            answer = f"I found {len(issues)} quality finding(s): {details}. Review these before using the data for final reporting."
        return {"answer": answer, "insights": [issue["impact"] for issue in issues[:4]], "visualization": None, "rows": issues, "sql": "SELECT * FROM dataset LIMIT 1", "intent": "quality", "evidence": base | {"issues": issues}}

    # --- Correlation ---
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

    # --- Forecast ---
    if any(word in normalized for word in ("forecast", "predict", "projection", "future")) and date_column and metric:
        periods, cadence = _period_values(frame, date_column, metric, question)
        projection = forecast(periods["value"].tolist())
        if not projection.get("available"):
            return {"answer": projection.get("reason", "There are not enough clean time periods for a forecast."), "insights": [], "visualization": None, "rows": [], "sql": None, "intent": "forecast", "evidence": base}
        last_period = pd.Period(periods.iloc[-1]["period"], freq={"monthly": "M", "quarterly": "Q", "weekly": "W", "yearly": "Y"}[cadence])
        future_labels = [str(last_period + index) for index in range(1, len(projection["forecast"]) + 1)]
        rows = [{"period": str(period), "value": float(value), "kind": "historical"} for period, value in zip(periods["period"], periods["value"])]
        rows.extend({"period": period, "value": value, "kind": "forecast", "lower": projection["lower"][index], "upper": projection["upper"][index]} for index, (period, value) in enumerate(zip(future_labels, projection["forecast"])))
        answer = f"The {cadence} projection for {metric} is {', '.join(f'{label}: {value:,.2f}' for label, value in zip(future_labels, projection['forecast']))}. This is a {projection['confidence']} confidence linear trend projection, not a causal prediction."
        return {"answer": answer, "insights": [projection.get("assumption", "")], "visualization": _chart("line", f"{metric} forecast", [{"label": row["period"], "value": row["value"]} for row in rows]), "rows": rows, "sql": "SELECT * FROM dataset LIMIT 200", "intent": "forecast", "evidence": base | {"metric": metric, "date_column": date_column}}

    # --- Outlier / Anomaly detection ---
    if any(word in normalized for word in ("outlier", "outliers", "unusual", "anomaly", "anomalies")) and metric:
        values = _numeric_series(frame, metric)
        clean = values.dropna()
        if len(clean) < 4:
            return {"answer": f"There are not enough usable {metric} values to identify unusual records.", "insights": [], "visualization": None, "rows": [], "sql": None, "intent": "anomaly", "evidence": base}
        q1, q3 = clean.quantile([0.25, 0.75]); iqr = q3 - q1
        flagged = frame.loc[(values < q1 - 1.5 * iqr) | (values > q3 + 1.5 * iqr)].copy()
        flagged["value"] = values.loc[flagged.index].round(2)
        rows = json_safe_rows(flagged.head(50).to_dict(orient="records"))
        return {"answer": f"I found {len(flagged):,} unusual {metric} records using the 1.5× IQR rule. These are candidates for review, not automatic errors.", "insights": [f"Typical range: {q1:,.2f} to {q3:,.2f}; flagged values are outside the IQR fence."], "visualization": None, "rows": rows, "sql": f"SELECT * FROM dataset WHERE {quote(metric)} < {float(q1 - 1.5 * iqr)} OR {quote(metric)} > {float(q3 + 1.5 * iqr)} LIMIT 200", "intent": "anomaly", "evidence": base | {"metric": metric}}

    # --- Row count ---
    if any(word in normalized for word in ("how many rows", "row count", "number of rows", "how many records", "records are")):
        count = len(frame)
        return {"answer": f"The active dataset contains {count:,} rows and {len(frame.columns):,} columns.", "insights": [], "visualization": None, "rows": [{"rows": count, "columns": len(frame.columns)}], "sql": "SELECT COUNT(*) AS rows FROM dataset", "intent": "profile", "evidence": base}

    # --- Drop / Decline analysis ---
    drop_question = any(word in normalized for word in ("drop", "dropped", "decline", "declined", "fell", "fall", "decrease", "decreased", "worst month", "lowest month", "went down", "go down", "goes down"))
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

    # --- Time-based trend ---
    if date_column and metric and any(word in normalized for word in TIME_WORDS):
        periods, cadence = _period_values(frame, date_column, metric, question)
        peak = periods.loc[periods["value"].idxmax()]
        low = periods.loc[periods["value"].idxmin()]
        answer = f"Across {len(periods)} {cadence} periods, {metric} totaled {periods['value'].sum():,.2f}. The highest was {peak['period']} at {peak['value']:,.2f}; the lowest was {low['period']} at {low['value']:,.2f}."
        rows = [{"period": str(row["period"]), "value": float(row["value"])} for _, row in periods.iterrows()]
        sql = f"SELECT strftime('%Y-%m', {quote(date_column)}) AS period, SUM({quote(metric)}) AS value FROM dataset GROUP BY period ORDER BY period"
        return {"answer": answer, "insights": [f"The highest period is {peak['period']}.", f"The lowest period is {low['period']}.", f"Average per period: {periods['value'].mean():,.2f}."] , "visualization": _chart("line", f"{cadence.title()} {metric}", [{"label": str(row["period"]), "value": float(row["value"])} for _, row in periods.iterrows()]), "rows": rows, "sql": sql, "intent": "trend", "evidence": base | {"date_column": date_column, "metric": metric}}

    # --- Grouped / comparison questions ---
    grouped_question = any(word in normalized for word in ("by", "per", "each", "which", "top", "highest", "most", "best", "lowest", "bottom", "compare", "biggest", "largest", "smallest"))
    if grouped_question and metric and dimension:
        values = frame.copy()
        values["__metric"] = _numeric_series(values, metric)
        aggregation, sql_aggregation = "total", "SUM"
        if any(word in normalized for word in ("average", "mean")):
            aggregation, sql_aggregation = "average", "AVG"
        elif "median" in normalized:
            aggregation, sql_aggregation = "median", None
        elif any(word in normalized for word in ("count", "how many", "number of", "records", "orders")):
            aggregation, sql_aggregation = "count", "COUNT"
        grouped_values = values.groupby(dimension, dropna=False)["__metric"]
        if aggregation == "average":
            grouped = grouped_values.agg(value="mean", count="count").reset_index()
        elif aggregation == "median":
            grouped = grouped_values.agg(value="median", count="count").reset_index()
        elif aggregation == "count":
            grouped = grouped_values.agg(value="count", count="count").reset_index()
        else:
            grouped = grouped_values.agg(value="sum", count="count").reset_index()
        grouped[dimension] = grouped[dimension].fillna("(blank)").astype(str)
        descending = not any(word in normalized for word in ("lowest", "bottom", "least", "smallest", "losing", "loss", "negative", "worst", "underperforming"))
        grouped = grouped.sort_values("value", ascending=not descending).head(20)
        top = grouped.iloc[0]
        direction = "highest" if descending else "lowest"
        answer = f"{top[dimension]} has the {direction} {aggregation} {metric}: {top['value']:,.2f} across {int(top['count']):,} rows."
        rows = [{"group": str(row[dimension]), "value": round(float(row["value"]), 2), "rows": int(row["count"])} for _, row in grouped.iterrows()]
        sql_value = f"{sql_aggregation}({quote(metric)})" if sql_aggregation else f"MEDIAN({quote(metric)})"
        sql = f"SELECT {quote(dimension)} AS group_name, {sql_value} AS value, COUNT(*) AS rows FROM dataset GROUP BY {quote(dimension)} ORDER BY value {'DESC' if descending else 'ASC'} LIMIT 20"
        insight = f"The top group represents {top['value'] / grouped['value'].sum() * 100:.1f}% of the displayed group total." if aggregation == "total" and grouped['value'].sum() else f"This comparison uses the {aggregation} for each group."
        return {"answer": answer, "insights": [insight], "visualization": _chart("bar", f"{aggregation.title()} {metric} by {dimension}", [{"label": row["group"], "value": row["value"]} for row in rows]), "rows": rows, "sql": sql, "intent": "breakdown", "evidence": base | {"dimension": dimension, "metric": metric, "aggregation": aggregation}}

    # --- Simple aggregates ---
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

    # --- Fallback: route to Gemini for free-form questions ---
    # Instead of dumping frame.head(20), signal that Gemini should handle this
    fields = ", ".join(str(column) for column in frame.columns[:8])

    # Build a data summary for the LLM instead of raw rows
    data_summary = {
        "columns": [str(c) for c in frame.columns],
        "rows": int(len(frame)),
        "numeric_fields": numeric,
        "date_fields": dates,
        "sample_values": {}
    }
    for col in frame.columns[:10]:
        sample = frame[col].dropna().head(3).tolist()
        data_summary["sample_values"][str(col)] = [str(v) for v in sample]

    # Gather conversation context
    prior_texts = []
    for entry in (history or [])[-6:]:
        role = entry.get("role", "")
        txt = entry.get("text", "")
        if txt:
            prior_texts.append(f"{role}: {txt}")

    return {
        "answer": "",
        "insights": [],
        "visualization": None,
        "rows": [],
        "sql": None,
        "intent": "needs_gemini",
        "evidence": base | {"data_summary": data_summary},
        "conversation_context": "\n".join(prior_texts),
        "available_fields": fields,
    }
