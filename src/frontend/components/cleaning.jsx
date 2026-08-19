import { Check, ChevronRight, WandSparkles } from "lucide-react";

import { Badge, Button, DataGrid, PageHeader } from "./ui";

const operations = [
  ["standardize_format", "Standardize messy formats"],
  ["trim_text", "Trim text fields"],
  ["remove_duplicates", "Remove exact duplicates"],
  ["normalize_columns", "Normalize column names"],
  ["parse_dates", "Parse date fields"],
  ["fill_missing", "Fill missing values"],
  ["remove_outliers", "Review numeric outliers"],
];

const formatNumber = (value) =>
  typeof value === "number"
    ? value.toLocaleString(undefined, { maximumFractionDigits: 2 })
    : String(value ?? "—");

export function Cleaning({ data, busy, preview, previewOp, approve, reject }) {
  const columns = previewColumns(preview);

  return (
    <div className="workspace-page">
      <PageHeader
        eyebrow="CLEANING / VERSIONED"
        title="Review before changing."
        copy="Every action creates a temporary preview. The source is untouched until approval. You can also ask the AI Analyst to prepare an updated CSV."
      />
      <div className="cleaning-grid">
        {operations.map(([operation, title]) => (
          <CleaningAction
            key={operation}
            operation={operation}
            title={title}
            busy={busy}
            previewOp={previewOp}
          />
        ))}
      </div>
      {preview && (
        <PreviewReview
          preview={preview}
          columns={columns}
          approve={approve}
          reject={reject}
        />
      )}
    </div>
  );
}

function CleaningAction({ operation, title, busy, previewOp }) {
  const copy =
    operation === "standardize_format"
      ? "Normalize text, dates, and numeric formats in one safe pass."
      : "Create a safe, reversible candidate version.";
  return (
    <article className="clean-action">
      <span className="clean-icon">
        <WandSparkles size={17} />
      </span>
      <div>
        <h3>{title}</h3>
        <p>{copy}</p>
      </div>
      <Button
        variant="outline"
        disabled={busy}
        onClick={() => previewOp(operation)}
      >
        Preview change <ChevronRight size={14} />
      </Button>
    </article>
  );
}

function PreviewReview({ preview, columns, approve, reject }) {
  return (
    <section className="panel preview-review">
      <div className="panel-heading">
        <div>
          <span className="panel-kicker">TEMPORARY PREVIEW</span>
          <h3>{preview.operation.replaceAll("_", " ")}</h3>
        </div>
        <Badge tone="orange">Awaiting approval</Badge>
      </div>
      <div className="analysis-detail-grid">
        <PreviewMetric
          label="Rows before"
          value={preview.rows_before ?? preview.before?.rows}
        />
        <PreviewMetric
          label="Rows after"
          value={preview.rows_after ?? preview.after?.rows}
        />
        <PreviewMetric
          label="Rows affected"
          value={preview.metrics?.affected_rows}
        />
      </div>
      <DataGrid
        columns={columns}
        rows={preview.after?.preview || preview.after_preview || []}
      />
      <div className="preview-actions">
        <Button onClick={approve}>
          <Check size={15} /> Accept and create version
        </Button>
        <Button variant="outline" onClick={reject}>
          Reject preview
        </Button>
      </div>
    </section>
  );
}

function PreviewMetric({ label, value }) {
  return (
    <div className="mini-metric">
      <span>{label}</span>
      <b>{formatNumber(value)}</b>
    </div>
  );
}

function previewColumns(preview) {
  return (
    preview?.after?.columns ||
    (preview?.after_preview?.[0] ? Object.keys(preview.after_preview[0]) : [])
  );
}
