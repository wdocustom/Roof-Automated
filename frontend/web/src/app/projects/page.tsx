"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { clsx } from "clsx";
import { formatDistanceToNow } from "date-fns";
import { FolderKanban, MapPin, Plus } from "lucide-react";
import { fetchProjects } from "@/lib/api";

const statusColors: Record<string, string> = {
  lead: "bg-gray-100 text-gray-700",
  onboarded: "bg-blue-100 text-blue-700",
  estimated: "bg-indigo-100 text-indigo-700",
  contract_sent: "bg-purple-100 text-purple-700",
  contract_signed: "bg-violet-100 text-violet-700",
  scheduled: "bg-amber-100 text-amber-700",
  in_progress: "bg-orange-100 text-orange-700",
  qc_review: "bg-red-100 text-red-700",
  completed: "bg-green-100 text-green-700",
  invoiced: "bg-teal-100 text-teal-700",
  paid: "bg-emerald-100 text-emerald-700",
  cancelled: "bg-gray-100 text-gray-500",
};

function formatStatus(status: string) {
  return status.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatCurrency(value: number | null) {
  if (value == null) return "-";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}

export default function ProjectsPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["projects"],
    queryFn: () => fetchProjects(),
  });

  return (
    <div className="p-6 lg:p-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Projects</h1>
          <p className="text-sm text-gray-500 mt-1">
            {data ? `${data.total} total projects` : "Loading..."}
          </p>
        </div>
        <button className="inline-flex items-center gap-2 rounded-lg bg-orange-600 px-4 py-2 text-sm font-medium text-white hover:bg-orange-700 transition-colors">
          <Plus className="h-4 w-4" />
          New Project
        </button>
      </div>

      {/* Table */}
      <div className="rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Property
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Type
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Status
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Estimate
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Created
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {isLoading ? (
              [...Array(5)].map((_, i) => (
                <tr key={i}>
                  {[...Array(5)].map((_, j) => (
                    <td key={j} className="px-6 py-4">
                      <div className="h-4 bg-gray-100 animate-pulse rounded w-24" />
                    </td>
                  ))}
                </tr>
              ))
            ) : data?.items.length === 0 ? (
              <tr>
                <td
                  colSpan={5}
                  className="px-6 py-12 text-center text-gray-500"
                >
                  <FolderKanban className="h-8 w-8 mx-auto text-gray-300 mb-2" />
                  No projects yet. Incoming SMS leads will appear here.
                </td>
              </tr>
            ) : (
              data?.items.map((project) => (
                <tr
                  key={project.id}
                  className="hover:bg-gray-50 transition-colors"
                >
                  <td className="px-6 py-4">
                    <Link
                      href={`/projects/${project.id}`}
                      className="text-sm font-medium text-gray-900 hover:text-orange-600"
                    >
                      {project.property_address}
                    </Link>
                    <div className="flex items-center gap-1 text-xs text-gray-500 mt-0.5">
                      <MapPin className="h-3 w-3" />
                      {project.property_city}, {project.property_state}
                    </div>
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-700">
                    {formatStatus(project.project_type)}
                  </td>
                  <td className="px-6 py-4">
                    <span
                      className={clsx(
                        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
                        statusColors[project.status] || statusColors.lead
                      )}
                    >
                      {formatStatus(project.status)}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-700">
                    {project.estimate_low && project.estimate_high
                      ? `${formatCurrency(project.estimate_low)} - ${formatCurrency(project.estimate_high)}`
                      : formatCurrency(project.contract_amount)}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-500">
                    {formatDistanceToNow(new Date(project.created_at), {
                      addSuffix: true,
                    })}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
