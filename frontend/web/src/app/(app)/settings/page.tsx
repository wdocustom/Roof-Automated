"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, useEffect } from "react";
import { Settings, Save, Building2, Phone, Bot, Bell } from "lucide-react";
import { clsx } from "clsx";
import { fetchCompanySettings, updateCompanySettings, type CompanySettings } from "@/lib/api";

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<"company" | "ai" | "notifications">("company");

  const { data: settings, isLoading } = useQuery({
    queryKey: ["company-settings"],
    queryFn: fetchCompanySettings,
  });

  const [form, setForm] = useState<Partial<CompanySettings>>({});

  useEffect(() => {
    if (settings) {
      setForm(settings);
    }
  }, [settings]);

  const mutation = useMutation({
    mutationFn: updateCompanySettings,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["company-settings"] });
    },
  });

  function handleChange(field: keyof CompanySettings, value: string | number) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  function handleSave() {
    mutation.mutate(form);
  }

  const tabs = [
    { id: "company" as const, label: "Company", icon: Building2 },
    { id: "ai" as const, label: "AI Configuration", icon: Bot },
    { id: "notifications" as const, label: "Notifications", icon: Bell },
  ];

  const inputClass =
    "w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-orange-500 focus:ring-1 focus:ring-orange-500 outline-none";

  return (
    <div className="p-6 lg:p-8 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Settings</h1>
          <p className="text-sm text-gray-500 mt-1">
            Manage your company and platform configuration
          </p>
        </div>
        <button
          onClick={handleSave}
          disabled={mutation.isPending}
          className={clsx(
            "inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium text-white transition-colors",
            mutation.isPending
              ? "bg-gray-400 cursor-not-allowed"
              : "bg-orange-600 hover:bg-orange-700"
          )}
        >
          <Save className="h-4 w-4" />
          {mutation.isPending ? "Saving..." : "Save Changes"}
        </button>
      </div>

      {mutation.isSuccess && (
        <div className="rounded-lg bg-green-50 border border-green-200 px-4 py-3 text-sm text-green-700">
          Settings saved successfully.
        </div>
      )}

      {/* Tab bar */}
      <div className="border-b border-gray-200">
        <nav className="flex gap-6">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={clsx(
                  "flex items-center gap-2 pb-3 text-sm font-medium border-b-2 transition-colors",
                  activeTab === tab.id
                    ? "border-orange-600 text-orange-600"
                    : "border-transparent text-gray-500 hover:text-gray-700"
                )}
              >
                <Icon className="h-4 w-4" />
                {tab.label}
              </button>
            );
          })}
        </nav>
      </div>

      {isLoading ? (
        <div className="space-y-4">
          {[...Array(4)].map((_, i) => (
            <div
              key={i}
              className="h-16 bg-gray-100 animate-pulse rounded-lg"
            />
          ))}
        </div>
      ) : (
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm space-y-6">
          {activeTab === "company" && (
            <>
              <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
                <Building2 className="h-5 w-5 text-gray-400" />
                Company Information
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Company Name
                  </label>
                  <input
                    type="text"
                    value={form.name ?? ""}
                    onChange={(e) => handleChange("name", e.target.value)}
                    className={inputClass}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Email
                  </label>
                  <input
                    type="email"
                    value={form.email ?? ""}
                    onChange={(e) => handleChange("email", e.target.value)}
                    className={inputClass}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Phone
                  </label>
                  <input
                    type="tel"
                    value={form.phone ?? ""}
                    onChange={(e) => handleChange("phone", e.target.value)}
                    className={inputClass}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Twilio Phone Number
                  </label>
                  <input
                    type="tel"
                    value={form.twilio_phone_number ?? ""}
                    onChange={(e) => handleChange("twilio_phone_number", e.target.value)}
                    className={inputClass}
                    placeholder="+1..."
                  />
                </div>
                <div className="md:col-span-2">
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Address
                  </label>
                  <input
                    type="text"
                    value={form.address ?? ""}
                    onChange={(e) => handleChange("address", e.target.value)}
                    className={inputClass}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    City
                  </label>
                  <input
                    type="text"
                    value={form.city ?? ""}
                    onChange={(e) => handleChange("city", e.target.value)}
                    className={inputClass}
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      State
                    </label>
                    <input
                      type="text"
                      maxLength={2}
                      value={form.state ?? ""}
                      onChange={(e) => handleChange("state", e.target.value.toUpperCase())}
                      className={inputClass}
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      ZIP
                    </label>
                    <input
                      type="text"
                      maxLength={10}
                      value={form.zip_code ?? ""}
                      onChange={(e) => handleChange("zip_code", e.target.value)}
                      className={inputClass}
                    />
                  </div>
                </div>
              </div>
            </>
          )}

          {activeTab === "ai" && (
            <>
              <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
                <Bot className="h-5 w-5 text-gray-400" />
                AI Configuration
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Human Review Threshold ($)
                  </label>
                  <input
                    type="number"
                    value={form.human_review_threshold_dollars ?? 5000}
                    onChange={(e) =>
                      handleChange("human_review_threshold_dollars", Number(e.target.value))
                    }
                    className={inputClass}
                  />
                  <p className="text-xs text-gray-500 mt-1">
                    Estimates above this amount require human approval before
                    sending to the customer
                  </p>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Agent Confidence Threshold
                  </label>
                  <input
                    type="number"
                    step="0.05"
                    min="0"
                    max="1"
                    value={form.agent_confidence_threshold ?? 0.7}
                    onChange={(e) =>
                      handleChange("agent_confidence_threshold", Number(e.target.value))
                    }
                    className={inputClass}
                  />
                  <p className="text-xs text-gray-500 mt-1">
                    Agent responses below this confidence level will be escalated
                    for human review (0.0 - 1.0)
                  </p>
                </div>
              </div>
            </>
          )}

          {activeTab === "notifications" && (
            <>
              <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
                <Bell className="h-5 w-5 text-gray-400" />
                Notification Preferences
              </h2>
              <div className="space-y-4">
                <p className="text-sm text-gray-500">
                  Notification settings will be available in a future update.
                  Currently, all alerts are shown on the dashboard.
                </p>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
