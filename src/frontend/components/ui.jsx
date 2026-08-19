import { useMemo, useState } from "react";

import { CheckCircle2, Search, Table2 } from "lucide-react";


export function Logo({ light = false }) {
  return (
    <div className={`logo ${light ? "logo-light" : ""}`}>
      <span className="logo-mark">
        <i />
        <i />
      </span>
      <b>PIVOT</b>
    </div>
  );
}


export function Button({
  children,
  variant = "primary",
  onClick,
  disabled = false,
  type = "button",
}) {
  return (
    <button
      type={type}
      className={`btn btn-${variant}`}
      onClick={onClick}
      disabled={disabled}
    >
      {children}
    </button>
  );
}


export function Badge({ children, tone = "gray" }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}


export function PageHeader({ eyebrow, title, copy, action }) {
  return (
    <div className="page-head">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        {copy && <p className="page-copy">{copy}</p>}
      </div>
      {action}
    </div>
  );
}


export function DataGrid({ columns = [], rows = [] }) {
  return (
    <div className="grid-scroll">
      <table>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index}>
              {columns.map((column) => (
                <td key={column}>{displayValue(row[column])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}


export function SchemaExplorer({ data }) {
  const fields = data.profile?.schema?.column_stats || [];
  const [query, setQuery] = useState("");
  const [selectedColumn, setSelectedColumn] = useState(fields[0]?.column);

  const visibleFields = useMemo(() => {
    const searchText = query.trim().toLowerCase();
    if (!searchText) {
      return fields;
    }

    return fields.filter((field) =>
      String(field.column).toLowerCase().includes(searchText),
    );
  }, [fields, query]);

  const selectedField = fields.find((field) => field.column === selectedColumn);

  return (
    <div className="schema-explorer panel">
      <div className="schema-toolbar">
        <div>
          <span className="panel-kicker">DATA DICTIONARY</span>
          <h2>Every field, explained.</h2>
        </div>
        <label className="field-search">
          <Search size={14} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search fields"
          />
          <span>{fields.length} fields</span>
        </label>
      </div>
      <div className="schema-layout">
        <section className="schema-table">
          <div className="schema-row schema-labels">
            <span>Field</span>
            <span>Type</span>
            <span>Role</span>
            <span>Unique</span>
            <span>Missing</span>
            <span>Example</span>
          </div>
          {visibleFields.map((field) => (
            <button
              className={`schema-row ${selectedField?.column === field.column ? "selected" : ""}`}
              onClick={() => setSelectedColumn(field.column)}
              key={field.column}
            >
              <b>{field.column}</b>
              <span>{field.dtype}</span>
              <span>
                <Badge tone="purple">
                  {field.role?.replaceAll("_", " ") || "field"}
                </Badge>
              </span>
              <span>{formatNumber(field.unique_count)}</span>
              <span>{field.null_pct || 0}%</span>
              <span>{field.examples?.[0] ?? "—"}</span>
            </button>
          ))}
        </section>
        <FieldInspector field={selectedField} />
      </div>
    </div>
  );
}


function FieldInspector({ field }) {
  if (!field) {
    return (
      <div className="lineage-empty">
        <Table2 size={20} />
        <b>No fields were profiled.</b>
      </div>
    );
  }

  return (
    <aside className="field-inspector">
      <span className="panel-kicker">FIELD INSPECTOR</span>
      <h2>{field.column}</h2>
      <Badge tone="purple">{field.role?.replaceAll("_", " ") || "field"}</Badge>
      <div className="field-facts">
        <span>
          <small>Data type</small>
          <b>{field.dtype}</b>
        </span>
        <span>
          <small>Unique values</small>
          <b>{formatNumber(field.unique_count)}</b>
        </span>
        <span>
          <small>Missing</small>
          <b>{field.null_pct || 0}%</b>
        </span>
      </div>
      <div className="mini-distribution">
        <span>Distribution preview</span>
        <i />
        <i />
        <i />
        <i />
        <i />
        <i />
        <i />
      </div>
      <div className="field-examples">
        <small>EXAMPLES</small>
        {(field.examples || []).slice(0, 4).map((example) => (
          <code key={String(example)}>{String(example)}</code>
        ))}
      </div>
    </aside>
  );
}


export function AppToast({ children }) {
  return (
    <div className="app-toast">
      <CheckCircle2 size={15} />
      {children}
    </div>
  );
}


function displayValue(value) {
  if (value && typeof value === "object") {
    return JSON.stringify(value);
  }

  return String(value ?? "");
}


function formatNumber(value) {
  if (typeof value === "number") {
    return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }

  return String(value ?? "—");
}
