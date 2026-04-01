"use client";

import { useQuery } from "@tanstack/react-query";
import { formatDistanceToNow } from "date-fns";
import {
  DollarSign,
  CreditCard,
  TrendingUp,
  ArrowUpRight,
  CheckCircle2,
  Clock,
  AlertTriangle,
} from "lucide-react";
import { clsx } from "clsx";
import { StatCard } from "@/components/stat-card";
import { fetchProjects } from "@/lib/api";

const paymentStatusConfig: Record<
  string,
  { label: string; color: string; icon: typeof CheckCircle2 }
> = {
  paid: {
    label: "Paid",
    color: "bg-green-100 text-green-700",
    icon: CheckCircle2,
  },
  invoiced: {
    label: "Invoiced",
    color: "bg-amber-100 text-amber-700",
    icon: Clock,
  },
  completed: {
    label: "Awaiting Invoice",
    color: "bg-blue-100 text-blue-700",
    icon: ArrowUpRight,
  },
};

function formatCurrency(value: number | null) {
  if (value == null) return "$0";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}

export default function PaymentsPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["projects-for-payments"],
    queryFn: () => fetchProjects(),
  });

  const projects = data?.items ?? [];

  const paidProjects = projects.filter((p) => p.status === "paid");
  const invoicedProjects = projects.filter((p) => p.status === "invoiced");
  const awaitingInvoice = projects.filter((p) => p.status === "completed");

  const totalRevenue = paidProjects.reduce(
    (sum, p) => sum + (p.contract_amount ?? 0),
    0
  );
  const outstanding = invoicedProjects.reduce(
    (sum, p) => sum + (p.contract_amount ?? 0),
    0
  );
  const pipeline = awaitingInvoice.reduce(
    (sum, p) => sum + (p.contract_amount ?? 0),
    0
  );

  const paymentProjects = [...paidProjects, ...invoicedProjects, ...awaitingInvoice];

  return (
    <div className="p-6 lg:p-8 space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Payments</h1>
        <p className="text-sm text-gray-500 mt-1">
          Track revenue, invoices, and payment status
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
            title="Total Revenue"
            value={formatCurrency(totalRevenue)}
            subtitle={`${paidProjects.length} paid projects`}
            icon={DollarSign}
            trend="up"
          />
          <StatCard
            title="Outstanding"
            value={formatCurrency(outstanding)}
            subtitle={`${invoicedProjects.length} invoiced`}
            icon={CreditCard}
          />
          <StatCard
            title="Pipeline"
            value={formatCurrency(pipeline)}
            subtitle={`${awaitingInvoice.length} awaiting invoice`}
            icon={TrendingUp}
          />
        </div>
      )}

      {/* Payments table */}
      <div className="rounded-xl border border-gray-200 bg-white shadow-sm overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Project
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Amount
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Status
              </th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Updated
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {isLoading ? (
              [...Array(5)].map((_, i) => (
                <tr key={i}>
                  {[...Array(4)].map((_, j) => (
                    <td key={j} className="px-6 py-4">
                      <div className="h-4 bg-gray-100 animate-pulse rounded w-24" />
                    </td>
                  ))}
                </tr>
              ))
            ) : paymentProjects.length === 0 ? (
              <tr>
                <td
                  colSpan={4}
                  className="px-6 py-12 text-center text-gray-500"
                >
                  <DollarSign className="h-8 w-8 mx-auto text-gray-300 mb-2" />
                  No payment activity yet. Completed projects will appear here.
                </td>
              </tr>
            ) : (
              paymentProjects.map((project) => {
                const config = paymentStatusConfig[project.status] ?? {
                  label: project.status,
                  color: "bg-gray-100 text-gray-700",
                  icon: AlertTriangle,
                };
                const Icon = config.icon;
                return (
                  <tr
                    key={project.id}
                    className="hover:bg-gray-50 transition-colors"
                  >
                    <td className="px-6 py-4">
                      <p className="text-sm font-medium text-gray-900">
                        {project.property_address}
                      </p>
                      <p className="text-xs text-gray-500">
                        {project.property_city}, {project.property_state}
                      </p>
                    </td>
                    <td className="px-6 py-4 text-sm font-medium text-gray-900">
                      {formatCurrency(project.contract_amount)}
                    </td>
                    <td className="px-6 py-4">
                      <span
                        className={clsx(
                          "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium",
                          config.color
                        )}
                      >
                        <Icon className="h-3 w-3" />
                        {config.label}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-500">
                      {formatDistanceToNow(new Date(project.updated_at), {
                        addSuffix: true,
                      })}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
