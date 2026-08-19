import { CheckCircle2, WandSparkles } from "lucide-react";

import { Badge, Button, PageHeader } from "./ui";

const formatNumber = (value) =>
  typeof value === "number"
    ? value.toLocaleString(undefined, { maximumFractionDigits: 2 })
    : String(value ?? "—");

export function Quality({ data, go }) {
  const issues = data.profile?.issues || [];
  const metrics = data.profile?.metrics || {};

  return (
    <div className="workspace-page">
      <PageHeader
        eyebrow="DATASET / QUALITY"
        title={`Quality score: ${formatNumber(data.quality_score)}/100`}
        copy="These are findings, not automatic changes."
        action={
          <Button variant="outline" onClick={go}>
            <WandSparkles size={15} /> Review cleaning
          </Button>
        }
      />
      <section className="quality-hero">
        <div>
          <Badge tone="green">PROFILE COMPLETE</Badge>
          <h2>
            {issues.length
              ? "A few things deserve attention."
              : "Your source looks healthy."}
          </h2>
          <p>
            Pivot found {issues.length} issue categories across{" "}
            {formatNumber(data.rows)} rows.
          </p>
        </div>
        <div className="quality-metrics">
          <QualityMetric value={metrics.completeness} label="completeness" />
          <QualityMetric value={metrics.consistency} label="consistency" />
          <QualityMetric value={metrics.uniqueness} label="uniqueness" />
        </div>
      </section>
      <div className="issue-grid">
        {issues.length ? (
          issues.map((issue) => <IssueCard key={issue.type} issue={issue} />)
        ) : (
          <NoIssues />
        )}
      </div>
    </div>
  );
}

function QualityMetric({ value, label }) {
  return (
    <span>
      <b>{value ?? 0}%</b>
      {label}
    </span>
  );
}

function IssueCard({ issue }) {
  return (
    <article className="issue-card">
      <Badge tone="orange">{issue.type.replaceAll("_", " ")}</Badge>
      <h3>{formatNumber(issue.count)} affected</h3>
      <p>{issue.impact}</p>
      <small>Suggested: {issue.fix}</small>
    </article>
  );
}

function NoIssues() {
  return (
    <div className="lineage-empty">
      <CheckCircle2 size={20} />
      <b>No obvious quality issues detected.</b>
      <span>
        Pivot checked missing values, duplicates, dates, negatives, and
        outliers.
      </span>
    </div>
  );
}
