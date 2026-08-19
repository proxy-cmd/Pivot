import { BarChart3, ChevronRight, RefreshCw } from "lucide-react";

import { Button, DataGrid, PageHeader } from "./ui";

export function AnalysisWorkspace({
  analyses,
  busy,
  selected,
  run,
  number,
  text,
  chart,
}) {
  const result = selected?.result;
  const points = result?.chart || [];
  const table = resultTable(result, points);

  return (
    <div className="workspace-page">
      <PageHeader
        eyebrow="ANALYSIS / GENERATED"
        title="Analyses your data supports."
        copy="These options come from detected fields, so Pivot does not assume a business domain."
      />
      <div className="analysis-grid">
        {analyses.map((analysis) => (
          <AnalysisCard
            key={analysis.id}
            analysis={analysis}
            isRunning={busy && selected?.id === analysis.id}
            onRun={() => run(analysis)}
          />
        ))}
      </div>
      {result && (
        <AnalysisResult
          result={result}
          points={points}
          table={table}
          number={number}
          text={text}
          chart={chart}
        />
      )}
    </div>
  );
}

function AnalysisCard({ analysis, isRunning, onRun }) {
  return (
    <article className={`analysis-card ${analysis.enabled ? "" : "disabled"}`}>
      <span className="analysis-icon">
        <BarChart3 size={17} />
      </span>
      <h3>{analysis.title}</h3>
      <p>{analysis.description}</p>
      <Button
        variant="outline"
        disabled={!analysis.enabled || isRunning}
        onClick={onRun}
      >
        {isRunning ? <RefreshCw size={14} className="spin" /> : "Run analysis"}{" "}
        <ChevronRight size={14} />
      </Button>
    </article>
  );
}

function AnalysisResult({ result, points, table, number, text, chart: Chart }) {
  return (
    <section className="panel analysis-detail">
      <div className="panel-heading">
        <div>
          <span className="panel-kicker">ANALYSIS RESULT</span>
          <h3>{result.title}</h3>
          <p className="result-context">
            Field: <b>{result.field || "dataset"}</b> · Calculation:{" "}
            <b>{result.aggregation || "profile review"}</b>
          </p>
        </div>
      </div>
      {result.metrics && (
        <Metrics values={result.metrics} number={number} text={text} />
      )}
      {points.length > 1 && <Chart points={points} />}
      <DataGrid columns={table.columns} rows={table.rows} />
    </section>
  );
}

function Metrics({ values, number, text }) {
  return (
    <div className="result-metrics">
      {Object.entries(values)
        .filter(([, value]) => value !== null && typeof value !== "object")
        .map(([key, value]) => (
          <div key={key}>
            <span>{key.replaceAll("_", " ")}</span>
            <b>{typeof value === "number" ? number(value) : text(value)}</b>
          </div>
        ))}
    </div>
  );
}

function resultTable(result, points) {
  if (result?.kind === "trend") {
    return {
      columns: ["period", result.field || "value"],
      rows: points.map((point) => ({
        period: point.label,
        [result.field || "value"]: point.value,
      })),
    };
  }
  if (result?.kind === "breakdown") {
    return {
      columns: [result.field || "group", "count"],
      rows: points.map((point) => ({
        [result.field || "group"]: point.label,
        count: point.value,
      })),
    };
  }
  return {
    columns: ["range", "count"],
    rows: points.map((point) => ({ range: point.label, count: point.value })),
  };
}
