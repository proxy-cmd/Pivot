import { useState } from "react";

import { Cleaning } from "./cleaning";
import { Quality } from "./quality";
import { SchemaExplorer } from "./ui";

const tabs = ["Schema", "Quality", "Clean"];

export function DataWorkspace({
  data,
  busy,
  preview,
  previewOp,
  approve,
  reject,
}) {
  const [activeTab, setActiveTab] = useState("Schema");

  return (
    <>
      <div className="data-tabs">
        <span>DATA</span>
        {tabs.map((tab) => (
          <button
            key={tab}
            className={activeTab === tab ? "active" : ""}
            onClick={() => setActiveTab(tab)}
          >
            {tab}
          </button>
        ))}
      </div>
      <WorkspacePanel
        tab={activeTab}
        data={data}
        busy={busy}
        preview={preview}
        previewOp={previewOp}
        approve={approve}
        reject={reject}
        showCleaning={() => setActiveTab("Clean")}
      />
    </>
  );
}

function WorkspacePanel({
  tab,
  data,
  busy,
  preview,
  previewOp,
  approve,
  reject,
  showCleaning,
}) {
  if (tab === "Schema") {
    return <SchemaExplorer data={data} />;
  }

  if (tab === "Quality") {
    return <Quality data={data} go={showCleaning} />;
  }

  return (
    <Cleaning
      data={data}
      busy={busy}
      preview={preview}
      previewOp={previewOp}
      approve={approve}
      reject={reject}
    />
  );
}
