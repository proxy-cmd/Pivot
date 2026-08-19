import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";


export function AnalystVisualization({ visualization }) {
  if (!visualization || visualization.type === "table") {
    return null;
  }

  if (visualization.type === "line") {
    return <LineVisualization visualization={visualization} />;
  }

  return <BarVisualization visualization={visualization} />;
}


function LineVisualization({ visualization }) {
  const points = visualization.data || [];
  if (!points.length) {
    return null;
  }

  return (
    <div className="analyst-visual" style={{ margin: "15px 0" }}>
      <VisualizationTitle>{visualization.title}</VisualizationTitle>
      <MiniChart points={points} />
    </div>
  );
}


function BarVisualization({ visualization }) {
  const data = chartData(visualization.data);
  if (!data.length) {
    return null;
  }

  return (
    <div className="analyst-visual" style={{ margin: "15px 0" }}>
      <VisualizationTitle>{visualization.title}</VisualizationTitle>
      <div style={{ height: "220px", width: "100%" }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 10, right: 10, left: 10, bottom: 20 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#eef2ee" />
            <XAxis
              dataKey="name"
              tick={{ fill: "#7f958b", fontSize: 10 }}
              axisLine={{ stroke: "#cbd9cf" }}
              tickLine={{ stroke: "#cbd9cf" }}
              interval={0}
              tickFormatter={shortLabel}
            />
            <YAxis
              tickFormatter={compactNumber}
              tick={{ fill: "#7f958b", fontSize: 10 }}
              axisLine={{ stroke: "#cbd9cf" }}
              tickLine={{ stroke: "#cbd9cf" }}
            />
            <Tooltip contentStyle={tooltipStyle} formatter={formatTooltip} />
            <Bar dataKey="value" fill="#138463" radius={[4, 4, 0, 0]} barSize={32}>
              {data.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={index === 0 ? "#10634c" : "#138463"} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}


function VisualizationTitle({ children }) {
  return (
    <div
      className="visual-title"
      style={{ fontWeight: "600", fontSize: "13px", color: "#153f36", marginBottom: "10px" }}
    >
      {children}
    </div>
  );
}


function MiniChart({ points }) {
  const values = points.map((point) => Number(point.value) || 0);
  const maximum = Math.max(...values, 1);
  const minimum = Math.min(...values, 0);
  const width = 760;
  const height = 190;
  const linePoints = points.map((point, index) => chartPoint(point, index, points.length, minimum, maximum, width, height)).join(" ");

  return (
    <div className="analysis-chart">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Analysis chart">
        <polyline points={linePoints} fill="none" stroke="#138463" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
        {points.map((point, index) => {
          const [x, y] = chartPoint(point, index, points.length, minimum, maximum, width, height).split(",");
          return <circle key={index} cx={x} cy={y} r="4" fill="#fff" stroke="#138463" strokeWidth="3" />;
        })}
      </svg>
      <div className="analysis-chart-labels">
        <span>{points[0]?.label || ""}</span>
        <span>{points[Math.floor(points.length / 2)]?.label || ""}</span>
        <span>{points[points.length - 1]?.label || ""}</span>
      </div>
    </div>
  );
}


function chartData(points = []) {
  return points.slice(0, 10).map((point) => ({ name: point.label, value: Number(point.value) || 0 }));
}


function chartPoint(point, index, count, minimum, maximum, width, height) {
  const x = (index / Math.max(count - 1, 1)) * width;
  const y = height - ((Number(point.value) - minimum) / Math.max(maximum - minimum, 1)) * 145 - 12;
  return `${x},${y}`;
}


function shortLabel(label) {
  return label.length > 12 ? `${label.substring(0, 10)}...` : label;
}


function compactNumber(value) {
  if (value >= 1e6) {
    return `${(value / 1e6).toFixed(1)}M`;
  }
  if (value >= 1e3) {
    return `${(value / 1e3).toFixed(1)}K`;
  }
  return value;
}


function formatTooltip(value) {
  return [`${value.toLocaleString()}`, "Value"];
}


const tooltipStyle = {
  background: "#073a31",
  border: "none",
  borderRadius: "6px",
  color: "white",
  fontSize: "11px",
  fontFamily: "inherit",
};
