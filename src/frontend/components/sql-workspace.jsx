import { useMemo, useState } from "react";

import {
  Code2,
  Download,
  LockKeyhole,
  Play,
  RefreshCw,
  Search,
  ShieldCheck,
} from "lucide-react";

import { Badge, Button, DataGrid, PageHeader } from "./ui";


export function SqlWorkspace({ dataset, query, setQuery, result, runQuery, busy }) {
  const [filter, setFilter] = useState("");
  const visibleRows = useMemo(() => filterRows(result?.rows || [], filter), [result?.rows, filter]);

  return (
    <div className="workspace-page">
      <PageHeader
        eyebrow="SQL / SAFE WORKSPACE"
        title="Query your data."
        copy="Use read-only SQL against the normalized dataset table."
        action={
          <Badge tone="green">
            <LockKeyhole size={12} /> Read-only mode
          </Badge>
        }
      />
      <div className="sql-layout">
        <QueryEditor query={query} setQuery={setQuery} runQuery={runQuery} busy={busy} />
        <SchemaHelp columns={dataset.profile?.columns_list || []} />
      </div>
      {result && <QueryResults result={result} visibleRows={visibleRows} filter={filter} setFilter={setFilter} />}
    </div>
  );
}


function QueryEditor({ query, setQuery, runQuery, busy }) {
  return (
    <div className="sql-editor panel">
      <div className="editor-bar">
        <span>
          <Code2 size={15} /> query-01.sql
        </span>
        <span>SQLite · dataset</span>
      </div>
      <div className="editor-body">
        <textarea value={query} onChange={(event) => setQuery(event.target.value)} spellCheck="false" />
      </div>
      <div className="editor-footer">
        <span>
          <ShieldCheck size={13} /> Query guard active
        </span>
        <Button variant="small" onClick={runQuery} disabled={busy}>
          {busy ? <RefreshCw size={13} className="spin" /> : <Play size={13} fill="currentColor" />}
          Run query
        </Button>
      </div>
    </div>
  );
}


function SchemaHelp({ columns }) {
  return (
    <div className="sql-help panel">
      <span className="panel-kicker">DETECTED COLUMNS</span>
      <h3>Use the profile</h3>
      <p>{columns.join(", ") || "No columns detected"}</p>
      <div className="sql-tip">
        <LockKeyhole size={14} />
        <span>Only SELECT and WITH statements can run.</span>
      </div>
    </div>
  );
}


function QueryResults({ result, visibleRows, filter, setFilter }) {
  return (
    <div className="panel sql-result">
      <div className="panel-heading">
        <div>
          <h3>{formatNumber(result.count)} rows returned</h3>
          <small className="result-context">
            Showing {formatNumber(visibleRows.length)} returned rows · search exact results below
          </small>
        </div>
        <Button variant="outline" onClick={() => downloadQueryResults(result)}>
          <Download size={14} /> Export CSV
        </Button>
      </div>
      <label className="result-search">
        <Search size={14} />
        <input value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="Search returned rows..." />
      </label>
      <DataGrid columns={result.columns} rows={visibleRows} />
    </div>
  );
}


function filterRows(rows, filter) {
  const searchText = filter.trim().toLowerCase();
  if (!searchText) {
    return rows;
  }
  return rows.filter((row) => Object.values(row).some((value) => displayValue(value).toLowerCase().includes(searchText)));
}


function downloadQueryResults(result) {
  const csv = [result.columns.join(","), ...result.rows.map((row) => csvRow(result.columns, row))].join("\n");
  const objectUrl = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = "pivot-query-result.csv";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(objectUrl);
}


function csvRow(columns, row) {
  return columns.map((column) => JSON.stringify(row[column] ?? "")).join(",");
}


function displayValue(value) {
  return value && typeof value === "object" ? JSON.stringify(value) : String(value ?? "");
}


function formatNumber(value) {
  return typeof value === "number" ? value.toLocaleString(undefined, { maximumFractionDigits: 2 }) : String(value ?? "—");
}
