"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";

const STATUS_COLORS: Record<string, string> = {
  lead: "#94a3b8",
  onboarded: "#60a5fa",
  estimated: "#818cf8",
  contract_sent: "#a78bfa",
  contract_signed: "#c084fc",
  scheduled: "#f59e0b",
  in_progress: "#f97316",
  qc_review: "#ef4444",
  completed: "#22c55e",
  invoiced: "#14b8a6",
  paid: "#10b981",
  cancelled: "#6b7280",
};

function formatLabel(status: string) {
  return status
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function ProjectStatusChart({
  byStatus,
}: {
  byStatus: Record<string, number>;
}) {
  const data = Object.entries(byStatus).map(([status, count]) => ({
    status: formatLabel(status),
    count,
    key: status,
  }));

  if (data.length === 0) {
    return (
      <p className="text-sm text-gray-500 py-8 text-center">
        No projects yet.
      </p>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={250}>
      <BarChart data={data} margin={{ top: 5, right: 5, bottom: 5, left: 0 }}>
        <XAxis
          dataKey="status"
          tick={{ fontSize: 11 }}
          angle={-35}
          textAnchor="end"
          height={70}
        />
        <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
        <Tooltip />
        <Bar dataKey="count" radius={[4, 4, 0, 0]}>
          {data.map((entry) => (
            <Cell
              key={entry.key}
              fill={STATUS_COLORS[entry.key] || "#94a3b8"}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
