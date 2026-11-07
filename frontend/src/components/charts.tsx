import { useState, type ReactNode } from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card } from "./ui";

const AXIS = { fontSize: 11, fill: "#7c8aa0" };
const GRID = "#1e2c45";
const tooltipStyle = {
  contentStyle: { background: "#162136", border: "1px solid #2a3a57", borderRadius: 6, fontSize: 12, color: "#e8edf4" },
  labelStyle: { color: "#a9b5c6", marginBottom: 2 },
  itemStyle: { color: "#e8edf4", padding: 0 },
  cursor: { fill: "rgba(127,220,236,0.06)", stroke: "#2a3a57" },
};

export function ChartCard({ title, note, table, children, height = 220 }: { title: string; note?: string; table: { head: string[]; rows: (string | number)[][] }; children: ReactNode; height?: number }) {
  const [showTable, setShowTable] = useState(false);
  return (
    <Card title={title} actions={
      <button type="button" className="text-xs text-text-3 hover:text-text-1" aria-pressed={showTable} onClick={() => setShowTable(!showTable)}>
        {showTable ? "View chart" : "View table"}
      </button>
    }>
      {showTable ? (
        <div className="overflow-auto" style={{ maxHeight: height }}>
          <table className="w-full text-xs">
            <thead><tr className="text-left text-text-3">{table.head.map((h) => <th key={h} className="pb-1 pr-3 font-medium">{h}</th>)}</tr></thead>
            <tbody>{table.rows.map((row, i) => <tr key={i} className="border-t border-ink-700">{row.map((c, j) => <td key={j} className="data py-1 pr-3 text-text-2">{c}</td>)}</tr>)}</tbody>
          </table>
        </div>
      ) : <div style={{ height }}>{children}</div>}
      {note && <p className="mt-2 text-xs text-text-3">{note}</p>}
    </Card>
  );
}

export function TrendChart({ data, xKey, tickFormatter }: { data: Record<string, string | number>[]; xKey: string; tickFormatter: (value: string) => string }) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={data} margin={{ top: 8, right: 8, left: -22, bottom: 0 }}>
        <defs><linearGradient id="trend" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--chart-1)" stopOpacity={0.3} /><stop offset="100%" stopColor="var(--chart-1)" stopOpacity={0} /></linearGradient></defs>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey={xKey} tick={AXIS} tickLine={false} axisLine={{ stroke: GRID }} tickFormatter={tickFormatter} minTickGap={32} />
        <YAxis allowDecimals={false} tick={AXIS} tickLine={false} axisLine={false} />
        <Tooltip {...tooltipStyle} labelFormatter={(value) => tickFormatter(String(value))} />
        <Area type="monotone" dataKey="count" name="Inspections" stroke="var(--chart-1)" strokeWidth={2} fill="url(#trend)" activeDot={{ r: 4, stroke: "#111a2b", strokeWidth: 2 }} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function RankedBars({ data, labelKey, name, formatLabel }: { data: Record<string, string | number>[]; labelKey: string; name: string; formatLabel?: (value: string) => string }) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} layout="vertical" margin={{ top: 0, right: 24, left: 8, bottom: 0 }} barCategoryGap={8}>
        <CartesianGrid stroke={GRID} horizontal={false} />
        <XAxis type="number" allowDecimals={false} tick={AXIS} tickLine={false} axisLine={false} />
        <YAxis type="category" dataKey={labelKey} width={120} tick={AXIS} tickLine={false} axisLine={false} tickFormatter={(v) => (formatLabel ? formatLabel(String(v)) : String(v))} />
        <Tooltip {...tooltipStyle} labelFormatter={(v) => (formatLabel ? formatLabel(String(v)) : String(v))} />
        <Bar dataKey="count" name={name} fill="var(--chart-1)" radius={[0, 4, 4, 0]} maxBarSize={16} label={{ position: "right", fontSize: 11, fill: "#a9b5c6" }} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function StackedReview({ data, formatLabel }: { data: { category: string; confirmed: number; false_positive: number; unconfirmed: number }[]; formatLabel: (value: string) => string }) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} layout="vertical" margin={{ top: 0, right: 8, left: 8, bottom: 0 }} barCategoryGap={8}>
        <CartesianGrid stroke={GRID} horizontal={false} />
        <XAxis type="number" allowDecimals={false} tick={AXIS} tickLine={false} axisLine={false} />
        <YAxis type="category" dataKey="category" width={120} tick={AXIS} tickLine={false} axisLine={false} tickFormatter={formatLabel} />
        <Tooltip {...tooltipStyle} labelFormatter={(v) => formatLabel(String(v))} />
        <Legend iconType="square" iconSize={9} wrapperStyle={{ fontSize: 11, color: "#a9b5c6" }} />
        <Bar dataKey="confirmed" name="Confirmed or resolved" stackId="a" fill="var(--chart-1)" stroke="#111a2b" strokeWidth={2} maxBarSize={16} />
        <Bar dataKey="false_positive" name="False positive" stackId="a" fill="var(--chart-2)" stroke="#111a2b" strokeWidth={2} maxBarSize={16} />
        <Bar dataKey="unconfirmed" name="No decision yet" stackId="a" fill="#4b5a73" stroke="#111a2b" strokeWidth={2} maxBarSize={16} />
      </BarChart>
    </ResponsiveContainer>
  );
}
