"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { formatDistanceToNow } from "date-fns";
import {
  ArrowLeft,
  MapPin,
  Calendar,
  DollarSign,
  Save,
  Pencil,
  X,
} from "lucide-react";
import { clsx } from "clsx";
import Link from "next/link";
import { fetchProject, updateProject } from "@/lib/api";

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

const allStatuses = [
  "lead",
  "onboarded",
  "estimated",
  "contract_sent",
  "contract_signed",
  "scheduled",
  "in_progress",
  "qc_review",
  "completed",
  "invoiced",
  "paid",
  "cancelled",
];

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

export default function ProjectDetailPage() {
  const params = useParams();
  const router = useRouter();
  const queryClient = useQueryClient();
  const id = params.id as string;

  const [editing, setEditing] = useState(false);
  const [editData, setEditData] = useState<Record<string, unknown>>({});

  const { data: project, isLoading } = useQuery({
    queryKey: ["project", id],
    queryFn: () => fetchProject(id),
  });

  const mutation = useMutation({
    mutationFn: (data: Record<string, unknown>) => updateProject(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["project", id] });
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      setEditing(false);
      setEditData({});
    },
  });

  function startEditing() {
    if (!project) return;
    setEditData({
      status: project.status,
      description: project.description ?? "",
      estimated_sqft: project.estimated_sqft ?? "",
      estimate_low: project.estimate_low ?? "",
      estimate_high: project.estimate_high ?? "",
      contract_amount: project.contract_amount ?? "",
    });
    setEditing(true);
  }

  function handleSave() {
    const cleaned: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(editData)) {
      if (value === "" || value === null) continue;
      if (typeof value === "string" && !isNaN(Number(value)) && key !== "status" && key !== "description") {
        cleaned[key] = Number(value);
      } else {
        cleaned[key] = value;
      }
    }
    mutation.mutate(cleaned);
  }

  const inputClass =
    "w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-orange-500 focus:ring-1 focus:ring-orange-500 outline-none";

  if (isLoading) {
    return (
      <div className="p-6 lg:p-8 space-y-6">
        <div className="h-8 w-48 bg-gray-200 animate-pulse rounded" />
        <div className="h-64 bg-gray-100 animate-pulse rounded-xl" />
      </div>
    );
  }

  if (!project) {
    return (
      <div className="p-6 lg:p-8">
        <p className="text-gray-500">Project not found.</p>
        <Link
          href="/projects"
          className="text-orange-600 hover:text-orange-700 text-sm mt-2 inline-flex items-center gap-1"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to projects
        </Link>
      </div>
    );
  }

  return (
    <div className="p-6 lg:p-8 space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <Link
            href="/projects"
            className="text-sm text-gray-500 hover:text-gray-700 inline-flex items-center gap-1 mb-2"
          >
            <ArrowLeft className="h-4 w-4" />
            Projects
          </Link>
          <h1 className="text-2xl font-bold text-gray-900">
            {project.property_address}
          </h1>
          <div className="flex items-center gap-3 mt-2">
            <div className="flex items-center gap-1 text-sm text-gray-500">
              <MapPin className="h-4 w-4" />
              {project.property_city}, {project.property_state}{" "}
              {project.property_zip}
            </div>
            <span
              className={clsx(
                "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
                statusColors[project.status] || statusColors.lead
              )}
            >
              {formatStatus(project.status)}
            </span>
          </div>
        </div>
        <div>
          {!editing ? (
            <button
              onClick={startEditing}
              className="inline-flex items-center gap-2 rounded-lg bg-orange-600 px-4 py-2 text-sm font-medium text-white hover:bg-orange-700 transition-colors"
            >
              <Pencil className="h-4 w-4" />
              Edit
            </button>
          ) : (
            <div className="flex items-center gap-2">
              <button
                onClick={handleSave}
                disabled={mutation.isPending}
                className="inline-flex items-center gap-2 rounded-lg bg-orange-600 px-4 py-2 text-sm font-medium text-white hover:bg-orange-700 transition-colors"
              >
                <Save className="h-4 w-4" />
                {mutation.isPending ? "Saving..." : "Save"}
              </button>
              <button
                onClick={() => {
                  setEditing(false);
                  setEditData({});
                }}
                className="inline-flex items-center gap-2 rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
              >
                <X className="h-4 w-4" />
                Cancel
              </button>
            </div>
          )}
        </div>
      </div>

      {mutation.isError && (
        <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
          Failed to save changes. Please try again.
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main details */}
        <div className="lg:col-span-2 space-y-6">
          {/* Status & Description */}
          <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm space-y-4">
            <h2 className="text-lg font-semibold text-gray-900">Details</h2>

            {editing ? (
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Status
                  </label>
                  <select
                    value={(editData.status as string) ?? project.status}
                    onChange={(e) =>
                      setEditData((prev) => ({ ...prev, status: e.target.value }))
                    }
                    className={inputClass}
                  >
                    {allStatuses.map((s) => (
                      <option key={s} value={s}>
                        {formatStatus(s)}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Description
                  </label>
                  <textarea
                    rows={3}
                    value={(editData.description as string) ?? ""}
                    onChange={(e) =>
                      setEditData((prev) => ({
                        ...prev,
                        description: e.target.value,
                      }))
                    }
                    className={inputClass}
                  />
                </div>
              </div>
            ) : (
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-gray-500">Type</span>
                    <p className="font-medium text-gray-900 mt-0.5">
                      {formatStatus(project.project_type)}
                    </p>
                  </div>
                  <div>
                    <span className="text-gray-500">Status</span>
                    <p className="mt-0.5">
                      <span
                        className={clsx(
                          "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
                          statusColors[project.status] || statusColors.lead
                        )}
                      >
                        {formatStatus(project.status)}
                      </span>
                    </p>
                  </div>
                  <div>
                    <span className="text-gray-500">Lead Source</span>
                    <p className="font-medium text-gray-900 mt-0.5">
                      {project.lead_source || "-"}
                    </p>
                  </div>
                  <div>
                    <span className="text-gray-500">Created</span>
                    <p className="font-medium text-gray-900 mt-0.5">
                      {formatDistanceToNow(new Date(project.created_at), {
                        addSuffix: true,
                      })}
                    </p>
                  </div>
                </div>
                {project.description && (
                  <div>
                    <span className="text-sm text-gray-500">Description</span>
                    <p className="text-sm text-gray-900 mt-0.5">
                      {project.description}
                    </p>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Estimates & Pricing */}
          <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm space-y-4">
            <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
              <DollarSign className="h-5 w-5 text-gray-400" />
              Estimates & Pricing
            </h2>

            {editing ? (
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Estimated Sq Ft
                  </label>
                  <input
                    type="number"
                    value={(editData.estimated_sqft as string) ?? ""}
                    onChange={(e) =>
                      setEditData((prev) => ({
                        ...prev,
                        estimated_sqft: e.target.value,
                      }))
                    }
                    className={inputClass}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Contract Amount
                  </label>
                  <input
                    type="number"
                    value={(editData.contract_amount as string) ?? ""}
                    onChange={(e) =>
                      setEditData((prev) => ({
                        ...prev,
                        contract_amount: e.target.value,
                      }))
                    }
                    className={inputClass}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Estimate Low
                  </label>
                  <input
                    type="number"
                    value={(editData.estimate_low as string) ?? ""}
                    onChange={(e) =>
                      setEditData((prev) => ({
                        ...prev,
                        estimate_low: e.target.value,
                      }))
                    }
                    className={inputClass}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Estimate High
                  </label>
                  <input
                    type="number"
                    value={(editData.estimate_high as string) ?? ""}
                    onChange={(e) =>
                      setEditData((prev) => ({
                        ...prev,
                        estimate_high: e.target.value,
                      }))
                    }
                    className={inputClass}
                  />
                </div>
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-gray-500">Estimated Sq Ft</span>
                  <p className="font-medium text-gray-900 mt-0.5">
                    {project.estimated_sqft
                      ? `${project.estimated_sqft.toLocaleString()} sq ft`
                      : "-"}
                  </p>
                </div>
                <div>
                  <span className="text-gray-500">Contract Amount</span>
                  <p className="font-medium text-gray-900 mt-0.5">
                    {formatCurrency(project.contract_amount)}
                  </p>
                </div>
                <div>
                  <span className="text-gray-500">Estimate Range</span>
                  <p className="font-medium text-gray-900 mt-0.5">
                    {project.estimate_low && project.estimate_high
                      ? `${formatCurrency(project.estimate_low)} - ${formatCurrency(project.estimate_high)}`
                      : "-"}
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Sidebar info */}
        <div className="space-y-6">
          {/* Schedule */}
          <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
            <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-2 mb-3">
              <Calendar className="h-4 w-4 text-gray-400" />
              Schedule
            </h3>
            <div className="space-y-3 text-sm">
              <div>
                <span className="text-gray-500">Scheduled Start</span>
                <p className="font-medium text-gray-900 mt-0.5">
                  {project.scheduled_start
                    ? new Date(project.scheduled_start).toLocaleDateString()
                    : "Not scheduled"}
                </p>
              </div>
              <div>
                <span className="text-gray-500">Scheduled End</span>
                <p className="font-medium text-gray-900 mt-0.5">
                  {project.scheduled_end
                    ? new Date(project.scheduled_end).toLocaleDateString()
                    : "Not scheduled"}
                </p>
              </div>
            </div>
          </div>

          {/* Timeline */}
          <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
            <h3 className="text-sm font-semibold text-gray-900 mb-3">
              Timeline
            </h3>
            <div className="space-y-3 text-sm">
              <div>
                <span className="text-gray-500">Created</span>
                <p className="font-medium text-gray-900 mt-0.5">
                  {new Date(project.created_at).toLocaleDateString()}
                </p>
              </div>
              <div>
                <span className="text-gray-500">Last Updated</span>
                <p className="font-medium text-gray-900 mt-0.5">
                  {formatDistanceToNow(new Date(project.updated_at), {
                    addSuffix: true,
                  })}
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
