"use client";

import { AlertTriangle, AlertCircle } from "lucide-react";
import { clsx } from "clsx";
import { formatDistanceToNow } from "date-fns";
import type { Alert } from "@/lib/api";

const typeLabels: Record<string, string> = {
  human_escalation: "Escalation",
  payment_overdue: "Payment Overdue",
  milestone_qc_failed: "QC Failed",
  weather_alert: "Weather",
  price_update_flagged: "Price Change",
};

export function AlertList({ alerts }: { alerts: Alert[] }) {
  if (alerts.length === 0) {
    return (
      <p className="text-sm text-gray-500 py-8 text-center">
        No active alerts. All clear!
      </p>
    );
  }

  return (
    <ul className="divide-y divide-gray-100">
      {alerts.map((alert) => (
        <li key={alert.id} className="flex items-start gap-3 py-3">
          {alert.severity === "high" ? (
            <AlertTriangle className="h-5 w-5 text-red-500 mt-0.5 shrink-0" />
          ) : (
            <AlertCircle className="h-5 w-5 text-amber-500 mt-0.5 shrink-0" />
          )}
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span
                className={clsx(
                  "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
                  alert.severity === "high"
                    ? "bg-red-100 text-red-700"
                    : "bg-amber-100 text-amber-700"
                )}
              >
                {typeLabels[alert.type] || alert.type}
              </span>
              <span className="text-xs text-gray-400">
                {formatDistanceToNow(new Date(alert.created_at), {
                  addSuffix: true,
                })}
              </span>
            </div>
            <p className="mt-1 text-sm text-gray-700">{alert.description}</p>
          </div>
        </li>
      ))}
    </ul>
  );
}
