"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { clsx } from "clsx";
import { formatDistanceToNow } from "date-fns";
import { FolderKanban, MapPin, Plus, X, Sparkles } from "lucide-react";
import { fetchProjects, createProject, seedProject } from "@/lib/api";
import { useState } from "react";

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

// Service options as clickable pills — multi-select for combo
const SERVICE_OPTIONS = [
  { value: "roof_replacement", label: "Roof Replacement", icon: "🏠" },
  { value: "roof_repair", label: "Roof Repair", icon: "🔧" },
  { value: "siding_install", label: "Siding Install", icon: "🧱" },
  { value: "siding_repair", label: "Siding Repair", icon: "🪛" },
  { value: "gutters", label: "Gutters", icon: "🌧️" },
  { value: "other", label: "Other", icon: "📋" },
];

const US_STATES = [
  "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA",
  "KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ",
  "NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT",
  "VA","WA","WV","WI","WY",
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

export default function ProjectsPage() {
  const queryClient = useQueryClient();
  const [showModal, setShowModal] = useState(false);
  const [error, setError] = useState("");

  // Form state
  const [customerName, setCustomerName] = useState("");
  const [customerPhone, setCustomerPhone] = useState("");
  const [customerEmail, setCustomerEmail] = useState("");
  const [address, setAddress] = useState("");
  const [city, setCity] = useState("");
  const [state, setState] = useState("");
  const [zip, setZip] = useState("");
  const [selectedServices, setSelectedServices] = useState<string[]>([]);
  const [description, setDescription] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["projects"],
    queryFn: () => fetchProjects(),
  });

  const mutation = useMutation({
    mutationFn: createProject,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      setShowModal(false);
      resetForm();
    },
    onError: () => {
      setError("Failed to create project. Please try again.");
    },
  });

  const seedMutation = useMutation({
    mutationFn: seedProject,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
    onError: () => {
      setError("Failed to seed project.");
      setTimeout(() => setError(""), 3000);
    },
  });

  function resetForm() {
    setCustomerName("");
    setCustomerPhone("");
    setCustomerEmail("");
    setAddress("");
    setCity("");
    setState("");
    setZip("");
    setSelectedServices([]);
    setDescription("");
    setError("");
  }

  function toggleService(value: string) {
    setSelectedServices((prev) =>
      prev.includes(value)
        ? prev.filter((s) => s !== value)
        : [...prev, value]
    );
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");

    if (selectedServices.length === 0) {
      setError("Select at least one service.");
      return;
    }

    // Determine project_type from selection
    let projectType = selectedServices[0];
    if (selectedServices.length > 1) {
      projectType = "combo";
    }

    mutation.mutate({
      customer_name: customerName,
      customer_phone: customerPhone || undefined,
      customer_email: customerEmail || undefined,
      property_address: address,
      property_city: city,
      property_state: state,
      property_zip: zip,
      project_type: projectType,
      combo_details: selectedServices,
      description: description || undefined,
      lead_source: "manual",
    });
  }

  return (
    <div className="p-6 lg:p-8 space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Projects</h1>
          <p className="text-sm text-gray-500 mt-1">
            {data ? `${data.total} total projects` : "Loading..."}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => seedMutation.mutate()}
            disabled={seedMutation.isPending}
            className="inline-flex items-center gap-1.5 rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors disabled:opacity-50"
          >
            <Sparkles className="h-4 w-4" />
            {seedMutation.isPending ? "Seeding..." : "Seed Demo"}
          </button>
          <button
            onClick={() => setShowModal(true)}
            className="inline-flex items-center gap-2 rounded-lg bg-orange-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-orange-700 transition-colors"
          >
            <Plus className="h-4 w-4" />
            New Project
          </button>
        </div>
      </div>

      {error && !showModal && (
        <div className="bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Table */}
      <div className="rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Property
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Customer
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
                  {[...Array(6)].map((_, j) => (
                    <td key={j} className="px-6 py-4">
                      <div className="h-4 bg-gray-100 animate-pulse rounded w-24" />
                    </td>
                  ))}
                </tr>
              ))
            ) : data?.items.length === 0 ? (
              <tr>
                <td
                  colSpan={6}
                  className="px-6 py-12 text-center text-gray-500"
                >
                  <FolderKanban className="h-8 w-8 mx-auto text-gray-300 mb-2" />
                  <p>No projects yet.</p>
                  <div className="flex items-center justify-center gap-3 mt-3">
                    <button
                      onClick={() => setShowModal(true)}
                      className="text-sm text-orange-600 hover:text-orange-700 font-medium"
                    >
                      Create your first project
                    </button>
                    <span className="text-gray-300">or</span>
                    <button
                      onClick={() => seedMutation.mutate()}
                      disabled={seedMutation.isPending}
                      className="text-sm text-indigo-600 hover:text-indigo-700 font-medium"
                    >
                      Seed a demo project
                    </button>
                  </div>
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
                  <td className="px-6 py-4">
                    <p className="text-sm font-medium text-gray-900">
                      {project.customer
                        ? `${project.customer.first_name || ""} ${project.customer.last_name || ""}`.trim() || "—"
                        : "—"}
                    </p>
                    {project.customer?.phone && (
                      <p className="text-xs text-gray-500">{project.customer.phone}</p>
                    )}
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

      {/* New Project Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-lg max-h-[90vh] flex flex-col">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
              <h2 className="text-lg font-semibold text-gray-900">
                New Project
              </h2>
              <button
                onClick={() => { setShowModal(false); resetForm(); }}
                className="text-gray-400 hover:text-gray-600"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <form id="new-project-form" onSubmit={handleSubmit} className="flex-1 min-h-0 overflow-y-auto px-6 py-5 space-y-5">
              {error && (
                <p className="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">
                  {error}
                </p>
              )}

              {/* Customer Info */}
              <div className="space-y-3">
                <h3 className="text-sm font-medium text-gray-700">Customer</h3>
                <input
                  type="text"
                  required
                  value={customerName}
                  onChange={(e) => setCustomerName(e.target.value)}
                  placeholder="Customer name *"
                  className="block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-orange-500 focus:outline-none focus:ring-1 focus:ring-orange-500"
                />
                <div className="grid grid-cols-2 gap-3">
                  <input
                    type="tel"
                    value={customerPhone}
                    onChange={(e) => setCustomerPhone(e.target.value)}
                    placeholder="Phone (optional)"
                    className="block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-orange-500 focus:outline-none focus:ring-1 focus:ring-orange-500"
                  />
                  <input
                    type="email"
                    value={customerEmail}
                    onChange={(e) => setCustomerEmail(e.target.value)}
                    placeholder="Email (optional)"
                    className="block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-orange-500 focus:outline-none focus:ring-1 focus:ring-orange-500"
                  />
                </div>
              </div>

              {/* Property */}
              <div className="space-y-3">
                <h3 className="text-sm font-medium text-gray-700">Property</h3>
                <input
                  type="text"
                  required
                  value={address}
                  onChange={(e) => setAddress(e.target.value)}
                  placeholder="Property address *"
                  className="block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-orange-500 focus:outline-none focus:ring-1 focus:ring-orange-500"
                />
                <div className="grid grid-cols-6 gap-3">
                  <input
                    type="text"
                    required
                    value={city}
                    onChange={(e) => setCity(e.target.value)}
                    placeholder="City *"
                    className="col-span-3 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-orange-500 focus:outline-none focus:ring-1 focus:ring-orange-500"
                  />
                  <select
                    required
                    value={state}
                    onChange={(e) => setState(e.target.value)}
                    className="col-span-1 block w-full rounded-lg border border-gray-300 px-2 py-2 text-sm focus:border-orange-500 focus:outline-none focus:ring-1 focus:ring-orange-500 bg-white"
                  >
                    <option value="">ST</option>
                    {US_STATES.map((s) => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                  <input
                    type="text"
                    required
                    value={zip}
                    onChange={(e) => setZip(e.target.value)}
                    placeholder="ZIP *"
                    className="col-span-2 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-orange-500 focus:outline-none focus:ring-1 focus:ring-orange-500"
                  />
                </div>
              </div>

              {/* Services — clickable pills */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-medium text-gray-700">Services</h3>
                  {selectedServices.length > 1 && (
                    <span className="text-xs bg-orange-100 text-orange-700 px-2 py-0.5 rounded-full font-medium">
                      Combo Project
                    </span>
                  )}
                </div>
                <p className="text-xs text-gray-500">
                  Select one or more services — multiple selections create a combo project
                </p>
                <div className="grid grid-cols-2 gap-2">
                  {SERVICE_OPTIONS.map((svc) => {
                    const selected = selectedServices.includes(svc.value);
                    return (
                      <button
                        key={svc.value}
                        type="button"
                        onClick={() => toggleService(svc.value)}
                        className={clsx(
                          "flex items-center gap-2 px-3 py-2.5 rounded-lg border-2 text-sm font-medium transition-all text-left",
                          selected
                            ? "border-orange-500 bg-orange-50 text-orange-700 ring-1 ring-orange-500/20"
                            : "border-gray-200 bg-white text-gray-700 hover:border-gray-300 hover:bg-gray-50"
                        )}
                      >
                        <span className="text-base">{svc.icon}</span>
                        <span className="flex-1">{svc.label}</span>
                        {selected && (
                          <span className="text-orange-500 text-xs font-bold">+</span>
                        )}
                      </button>
                    );
                  })}
                </div>
                {selectedServices.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {selectedServices.map((s) => {
                      const svc = SERVICE_OPTIONS.find((o) => o.value === s);
                      return (
                        <span
                          key={s}
                          className="inline-flex items-center gap-1 bg-orange-100 text-orange-700 px-2.5 py-1 rounded-full text-xs font-medium"
                        >
                          {svc?.icon} {svc?.label}
                          <button
                            type="button"
                            onClick={() => toggleService(s)}
                            className="ml-0.5 hover:text-orange-900"
                          >
                            <X className="h-3 w-3" />
                          </button>
                        </span>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Notes */}
              <div className="space-y-3">
                <h3 className="text-sm font-medium text-gray-700">Notes</h3>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Additional details (optional)"
                  rows={3}
                  className="block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-orange-500 focus:outline-none focus:ring-1 focus:ring-orange-500 resize-none"
                />
              </div>

            </form>

            {/* Actions — pinned footer, never scrolls */}
            <div className="flex-shrink-0 flex justify-end gap-3 border-t border-gray-200 px-6 py-4">
              <button
                type="button"
                onClick={() => { setShowModal(false); resetForm(); }}
                className="px-4 py-2 text-sm font-medium text-gray-700 hover:text-gray-900"
              >
                Cancel
              </button>
              <button
                type="submit"
                form="new-project-form"
                disabled={mutation.isPending || selectedServices.length === 0}
                className="px-4 py-2 rounded-lg bg-orange-600 text-sm font-medium text-white hover:bg-orange-700 disabled:opacity-50 transition-colors"
              >
                {mutation.isPending ? "Creating..." : "Create Project"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
