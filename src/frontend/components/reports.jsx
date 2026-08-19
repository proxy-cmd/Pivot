import { useState } from "react";
import { ChevronRight, Download, FileBarChart2 } from "lucide-react";

import { request } from "../../api";
import { Badge, Button, PageHeader } from "./ui";

export function Reports({ data, refresh, download, notify }) {
  const [title, setTitle] = useState("Dataset report");
  const [format, setFormat] = useState("md");
  const [isGenerating, setIsGenerating] = useState(false);

  async function generate() {
    setIsGenerating(true);
    try {
      const report = await request(`/api/datasets/${data.dataset_id}/reports`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, format }),
      });
      await refresh(data.dataset_id);
      await download(report.download_url);
      notify("Report generated from live dataset evidence.");
    } catch (error) {
      notify(error.message);
    } finally {
      setIsGenerating(false);
    }
  }

  return (
    <div className="workspace-page">
      <PageHeader
        eyebrow="REPORTS / EXPORT"
        title="Tell the story."
        copy="Generate a live report from the current profile, quality findings, and version history."
      />
      <ReportGenerator
        data={data}
        title={title}
        format={format}
        isGenerating={isGenerating}
        onTitleChange={setTitle}
        onFormatChange={setFormat}
        onGenerate={generate}
      />
      <ReportHistory data={data} download={download} />
    </div>
  );
}

function ReportGenerator({
  data,
  title,
  format,
  isGenerating,
  onTitleChange,
  onFormatChange,
  onGenerate,
}) {
  return (
    <section className="report-feature report-feature-polished">
      <div className="report-preview">
        <Badge tone="green">LIVE DATASET</Badge>
        <h2>Evidence, shaped into a story.</h2>
        <p>Profile, quality, analysis, and lineage in one export.</p>
        <div className="report-preview-line" />
      </div>
      <div className="report-copy">
        <h2>Generate a traceable report</h2>
        <p>
          No template numbers are used. This report is generated from{" "}
          <b>{data.file_name}</b> at export time.
        </p>
        <div className="report-form-grid">
          <label>
            Report title
            <input
              value={title}
              onChange={(event) => onTitleChange(event.target.value)}
            />
          </label>
          <label>
            Format
            <select
              value={format}
              onChange={(event) => onFormatChange(event.target.value)}
            >
              <option value="md">Markdown</option>
              <option value="csv">CSV</option>
              <option value="pdf">PDF</option>
            </select>
          </label>
        </div>
        <Button onClick={onGenerate} disabled={isGenerating}>
          <Download size={15} />{" "}
          {isGenerating ? "Generating…" : "Generate report"}
        </Button>
      </div>
    </section>
  );
}

function ReportHistory({ data, download }) {
  const reports = data.reports || [];
  return (
    <section className="report-history panel">
      <div className="panel-heading">
        <div>
          <span className="panel-kicker">REPORT HISTORY</span>
          <h3>{reports.length ? "Generated reports" : "No reports yet"}</h3>
        </div>
      </div>
      {reports.map((report) => (
        <ReportHistoryItem
          key={report.id}
          report={report}
          datasetId={data.dataset_id}
          download={download}
        />
      ))}
    </section>
  );
}

function ReportHistoryItem({ report, datasetId, download }) {
  return (
    <article>
      <span className="report-file-icon">
        <FileBarChart2 size={17} />
      </span>
      <div>
        <b>{report.title}</b>
        <small>
          {report.format.toUpperCase()} ·{" "}
          {new Date(report.created_at).toLocaleString()}
        </small>
      </div>
      <button
        className="text-button"
        onClick={() =>
          download(`/api/datasets/${datasetId}/reports/${report.id}/download`)
        }
      >
        Download <ChevronRight size={13} />
      </button>
    </article>
  );
}
