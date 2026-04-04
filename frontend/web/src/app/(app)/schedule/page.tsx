"use client";

import { useQuery } from "@tanstack/react-query";
import { useState, useMemo } from "react";
import { ChevronLeft, ChevronRight, MapPin, HardHat, Clock } from "lucide-react";
import { clsx } from "clsx";
import Link from "next/link";

const API_BASE = "/api/proxy";

interface ScheduledJob {
  project_id: string;
  property_address: string;
  property_city: string;
  project_type: string;
  status: string;
  scheduled_start: string | null;
  scheduled_end: string | null;
}

async function fetchCalendar(daysAhead: number): Promise<{ schedule: ScheduledJob[] }> {
  const res = await fetch(`${API_BASE}/schedule/calendar?days_ahead=${daysAhead}`, {
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) return { schedule: [] };
  return res.json();
}

const statusColors: Record<string, string> = {
  scheduled: "bg-amber-500",
  in_progress: "bg-orange-500",
};

function getDaysInMonth(year: number, month: number) {
  return new Date(year, month + 1, 0).getDate();
}

function getFirstDayOfMonth(year: number, month: number) {
  return new Date(year, month, 1).getDay();
}

export default function SchedulePage() {
  const today = new Date();
  const [viewMonth, setViewMonth] = useState(today.getMonth());
  const [viewYear, setViewYear] = useState(today.getFullYear());

  const { data } = useQuery({
    queryKey: ["calendar"],
    queryFn: () => fetchCalendar(60),
  });

  const schedule = data?.schedule || [];

  // Group jobs by date
  const jobsByDate = useMemo(() => {
    const map: Record<string, ScheduledJob[]> = {};
    for (const job of schedule) {
      if (!job.scheduled_start) continue;
      const dateKey = job.scheduled_start.slice(0, 10);
      if (!map[dateKey]) map[dateKey] = [];
      map[dateKey].push(job);
    }
    return map;
  }, [schedule]);

  const daysInMonth = getDaysInMonth(viewYear, viewMonth);
  const firstDay = getFirstDayOfMonth(viewYear, viewMonth);
  const monthName = new Date(viewYear, viewMonth).toLocaleString("default", {
    month: "long",
    year: "numeric",
  });

  function prevMonth() {
    if (viewMonth === 0) {
      setViewMonth(11);
      setViewYear(viewYear - 1);
    } else {
      setViewMonth(viewMonth - 1);
    }
  }

  function nextMonth() {
    if (viewMonth === 11) {
      setViewMonth(0);
      setViewYear(viewYear + 1);
    } else {
      setViewMonth(viewMonth + 1);
    }
  }

  const todayStr = today.toISOString().slice(0, 10);

  // Build calendar grid
  const cells: (number | null)[] = [];
  for (let i = 0; i < firstDay; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(d);
  while (cells.length % 7 !== 0) cells.push(null);

  // Upcoming jobs list (next 14 days)
  const upcoming = schedule
    .filter((j) => {
      if (!j.scheduled_start) return false;
      const d = new Date(j.scheduled_start);
      return d >= today && d <= new Date(today.getTime() + 14 * 86400000);
    })
    .sort((a, b) => (a.scheduled_start || "").localeCompare(b.scheduled_start || ""));

  return (
    <div className="p-6 lg:p-8 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Schedule</h1>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Calendar */}
        <div className="lg:col-span-2 bg-white rounded-xl border border-gray-200 shadow-sm">
          {/* Month header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
            <button
              onClick={prevMonth}
              className="p-1.5 rounded-lg hover:bg-gray-100 transition-colors"
            >
              <ChevronLeft className="h-5 w-5 text-gray-600" />
            </button>
            <h2 className="text-lg font-semibold text-gray-900">{monthName}</h2>
            <button
              onClick={nextMonth}
              className="p-1.5 rounded-lg hover:bg-gray-100 transition-colors"
            >
              <ChevronRight className="h-5 w-5 text-gray-600" />
            </button>
          </div>

          {/* Day headers */}
          <div className="grid grid-cols-7 border-b border-gray-100">
            {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((d) => (
              <div
                key={d}
                className="py-2 text-center text-xs font-medium text-gray-400 uppercase"
              >
                {d}
              </div>
            ))}
          </div>

          {/* Calendar grid */}
          <div className="grid grid-cols-7">
            {cells.map((day, i) => {
              if (day === null) {
                return <div key={`empty-${i}`} className="h-24 border-b border-r border-gray-50" />;
              }

              const dateStr = `${viewYear}-${String(viewMonth + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
              const jobs = jobsByDate[dateStr] || [];
              const isToday = dateStr === todayStr;
              const isPast = dateStr < todayStr;

              return (
                <div
                  key={dateStr}
                  className={clsx(
                    "h-24 border-b border-r border-gray-50 p-1 transition-colors",
                    isToday && "bg-orange-50",
                    isPast && "opacity-50"
                  )}
                >
                  <div className="flex items-center justify-between mb-0.5">
                    <span
                      className={clsx(
                        "text-xs font-medium w-6 h-6 flex items-center justify-center rounded-full",
                        isToday
                          ? "bg-orange-600 text-white"
                          : "text-gray-700"
                      )}
                    >
                      {day}
                    </span>
                  </div>
                  <div className="space-y-0.5 overflow-hidden">
                    {jobs.slice(0, 2).map((job) => (
                      <Link
                        key={job.project_id}
                        href={`/projects/${job.project_id}`}
                        className={clsx(
                          "block text-[10px] leading-tight px-1 py-0.5 rounded truncate text-white font-medium hover:opacity-80",
                          statusColors[job.status] || "bg-gray-500"
                        )}
                        title={`${job.project_type} — ${job.property_address}`}
                      >
                        {job.project_type}
                      </Link>
                    ))}
                    {jobs.length > 2 && (
                      <span className="text-[10px] text-gray-400 px-1">
                        +{jobs.length - 2} more
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Upcoming sidebar */}
        <div className="space-y-4">
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
            <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-2 mb-4">
              <Clock className="h-4 w-4 text-gray-400" /> Upcoming (14 days)
            </h3>
            {upcoming.length === 0 ? (
              <p className="text-sm text-gray-500">No jobs scheduled.</p>
            ) : (
              <div className="space-y-3">
                {upcoming.map((job) => {
                  const dt = new Date(job.scheduled_start!);
                  const dayStr = dt.toLocaleDateString("en-US", {
                    weekday: "short",
                    month: "short",
                    day: "numeric",
                  });
                  return (
                    <Link
                      key={job.project_id}
                      href={`/projects/${job.project_id}`}
                      className="block p-3 rounded-lg border border-gray-100 hover:border-orange-200 hover:bg-orange-50 transition-colors"
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs font-medium text-orange-600">{dayStr}</span>
                        <span
                          className={clsx(
                            "text-[10px] font-medium px-1.5 py-0.5 rounded-full text-white",
                            statusColors[job.status] || "bg-gray-500"
                          )}
                        >
                          {job.status.replace("_", " ")}
                        </span>
                      </div>
                      <div className="flex items-center gap-1.5 text-sm font-medium text-gray-900">
                        <HardHat className="h-3.5 w-3.5 text-gray-400 shrink-0" />
                        {job.project_type}
                      </div>
                      <div className="flex items-center gap-1.5 text-xs text-gray-500 mt-0.5">
                        <MapPin className="h-3 w-3 text-gray-300 shrink-0" />
                        {job.property_address}, {job.property_city}
                      </div>
                    </Link>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
