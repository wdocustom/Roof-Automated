"use client";

import { useQuery } from "@tanstack/react-query";
import {
  FolderKanban,
  CheckCircle2,
  Bot,
  AlertTriangle,
  DollarSign,
  TrendingUp,
} from "lucide-react";
import { StatCard } from "@/components/stat-card";
import { AlertList } from "@/components/alert-list";
import { ProjectStatusChart } from "@/components/project-status-chart";
import {
  fetchInsights,
  fetchAlerts,
  fetchCostTracking,
} from "@/lib/api";

export default function DashboardPage() {
  const insights = useQuery({
    queryKey: ["dashboard-insights"],
    queryFn: fetchInsights,
  });

  const alerts = useQuery({
    queryKey: ["dashboard-alerts"],
    queryFn: fetchAlerts,
  });

  const costs = useQuery({
    queryKey: ["dashboard-costs"],
    queryFn: () => fetchCostTracking(30),
  });

  const isLoading = insights.isLoading || alerts.isLoading || costs.isLoading;

  return (
    <div className="p-6 lg:p-8 space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <p className="text-sm text-gray-500 mt-1">
          Your AI-powered operations overview
        </p>
      </div>

      {/* Stat cards */}
      {isLoading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <div
              key={i}
              className="h-32 rounded-xl border border-gray-200 bg-white animate-pulse"
            />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
          <StatCard
            title="Active Projects"
            value={insights.data?.project_summary.active ?? 0}
            icon={FolderKanban}
          />
          <StatCard
            title="Completed This Month"
            value={insights.data?.project_summary.completed_this_month ?? 0}
            icon={CheckCircle2}
            trend="up"
          />
          <StatCard
            title="AI Autonomy Rate"
            value={`${(insights.data?.agent_performance.autonomy_rate_pct ?? 0).toFixed(0)}%`}
            subtitle={`${insights.data?.agent_performance.events_processed_7d ?? 0} events processed (7d)`}
            icon={Bot}
          />
          <StatCard
            title="Est. AI Cost (30d)"
            value={`$${(costs.data?.estimated_llm_cost ?? 0).toFixed(2)}`}
            subtitle={`$${(costs.data?.cost_per_project ?? 0).toFixed(2)} per project`}
            icon={DollarSign}
          />
        </div>
      )}

      {/* Charts + Alerts row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Project pipeline chart */}
        <div className="lg:col-span-2 rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">
            Project Pipeline
          </h2>
          {insights.data ? (
            <ProjectStatusChart
              byStatus={insights.data.project_summary.by_status}
            />
          ) : (
            <div className="h-[250px] animate-pulse bg-gray-100 rounded" />
          )}
        </div>

        {/* Alerts */}
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-900">Alerts</h2>
            {alerts.data && alerts.data.high_severity > 0 && (
              <span className="inline-flex items-center gap-1 text-xs font-medium text-red-600">
                <AlertTriangle className="h-3.5 w-3.5" />
                {alerts.data.high_severity} urgent
              </span>
            )}
          </div>
          {alerts.data ? (
            <AlertList alerts={alerts.data.alerts} />
          ) : (
            <div className="space-y-3">
              {[...Array(3)].map((_, i) => (
                <div
                  key={i}
                  className="h-12 bg-gray-100 animate-pulse rounded"
                />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* AI Insights */}
      {insights.data && insights.data.insights.length > 0 && (
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <div className="flex items-center gap-2 mb-4">
            <TrendingUp className="h-5 w-5 text-orange-500" />
            <h2 className="text-lg font-semibold text-gray-900">
              AI Coach Insights
            </h2>
          </div>
          <ul className="space-y-2">
            {insights.data.insights.map((insight, i) => (
              <li
                key={i}
                className="flex items-start gap-2 text-sm text-gray-700"
              >
                <span className="text-orange-500 mt-0.5">-</span>
                {insight}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
