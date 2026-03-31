"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Bot,
  MessageSquare,
  Calculator,
  Camera,
  ShieldCheck,
  Zap,
  Activity,
} from "lucide-react";
import { clsx } from "clsx";
import { StatCard } from "@/components/stat-card";
import { fetchAgentMetrics, fetchCostTracking } from "@/lib/api";

const agentConfig: Record<
  string,
  { label: string; description: string; icon: typeof Bot; color: string }
> = {
  intake_agent: {
    label: "Intake Agent",
    description:
      "Handles initial customer contact, qualifies leads, and collects property info via SMS",
    icon: MessageSquare,
    color: "bg-blue-500",
  },
  estimator_agent: {
    label: "Estimator Agent",
    description:
      "Generates material takeoffs and pricing estimates using rate cards and measurement data",
    icon: Calculator,
    color: "bg-green-500",
  },
  qc_agent: {
    label: "QC Agent",
    description:
      "Reviews project photos for quality compliance and flags issues for crew leads",
    icon: Camera,
    color: "bg-purple-500",
  },
  compliance_agent: {
    label: "Compliance Agent",
    description:
      "Ensures TCPA consent, permit requirements, and regulatory compliance",
    icon: ShieldCheck,
    color: "bg-red-500",
  },
  scheduler_agent: {
    label: "Scheduler Agent",
    description:
      "Coordinates crew scheduling, weather checks, and customer appointment confirmations",
    icon: Zap,
    color: "bg-amber-500",
  },
};

export default function AgentsPage() {
  const metrics = useQuery({
    queryKey: ["agent-metrics-30d"],
    queryFn: () => fetchAgentMetrics(30),
  });

  const costs = useQuery({
    queryKey: ["agent-costs-30d"],
    queryFn: () => fetchCostTracking(30),
  });

  const isLoading = metrics.isLoading || costs.isLoading;

  const byAgent = metrics.data?.by_agent ?? {};
  const totalEvents = metrics.data?.total_events ?? 0;

  return (
    <div className="p-6 lg:p-8 space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">AI Agents</h1>
        <p className="text-sm text-gray-500 mt-1">
          Monitor and configure your AI workforce
        </p>
      </div>

      {/* Stats */}
      {isLoading ? (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {[...Array(3)].map((_, i) => (
            <div
              key={i}
              className="h-32 rounded-xl border border-gray-200 bg-white animate-pulse"
            />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <StatCard
            title="Total Events (30d)"
            value={totalEvents}
            icon={Activity}
          />
          <StatCard
            title="Est. LLM Cost (30d)"
            value={`$${(costs.data?.estimated_llm_cost ?? 0).toFixed(2)}`}
            subtitle={`$${(costs.data?.cost_per_project ?? 0).toFixed(2)} per project`}
            icon={Bot}
          />
          <StatCard
            title="Projects Touched"
            value={costs.data?.projects_touched ?? 0}
            icon={Zap}
          />
        </div>
      )}

      {/* Agent cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
        {Object.entries(agentConfig).map(([key, agent]) => {
          const eventCount = byAgent[key] ?? 0;
          const Icon = agent.icon;
          return (
            <div
              key={key}
              className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm"
            >
              <div className="flex items-start gap-4">
                <div
                  className={clsx(
                    "h-10 w-10 rounded-lg flex items-center justify-center",
                    agent.color
                  )}
                >
                  <Icon className="h-5 w-5 text-white" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-semibold text-gray-900">
                      {agent.label}
                    </h3>
                    <span
                      className={clsx(
                        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
                        eventCount > 0
                          ? "bg-green-100 text-green-700"
                          : "bg-gray-100 text-gray-500"
                      )}
                    >
                      <span
                        className={clsx(
                          "h-1.5 w-1.5 rounded-full",
                          eventCount > 0 ? "bg-green-500" : "bg-gray-400"
                        )}
                      />
                      {eventCount > 0 ? "Active" : "Idle"}
                    </span>
                  </div>
                  <p className="text-xs text-gray-500 mt-1">
                    {agent.description}
                  </p>
                  <div className="mt-3 pt-3 border-t border-gray-100">
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-gray-500">Events (30d)</span>
                      <span className="font-medium text-gray-900">
                        {eventCount}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Event breakdown */}
      {metrics.data && Object.keys(metrics.data.by_type).length > 0 && (
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">
            Event Types (30d)
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {Object.entries(metrics.data.by_type).map(([type, count]) => (
              <div
                key={type}
                className="rounded-lg bg-gray-50 p-3 text-center"
              >
                <p className="text-lg font-bold text-gray-900">{count}</p>
                <p className="text-xs text-gray-500 mt-1">
                  {type.replace(/_/g, " ")}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
