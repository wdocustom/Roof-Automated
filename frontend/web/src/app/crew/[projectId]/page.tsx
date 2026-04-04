"use client";

import { useState, useEffect } from "react";
import {
  Camera,
  CheckCircle,
  Circle,
  ChevronDown,
  ChevronUp,
  HardHat,
  MapPin,
  AlertCircle,
  Loader2,
} from "lucide-react";
import { clsx } from "clsx";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

interface Milestone {
  id: string;
  name: string;
  description: string;
  sort_order: number;
  status: string;
  has_photo: boolean;
  photo_urls: string[];
}

interface ProjectData {
  project_id: string;
  property_address: string;
  project_type: string;
  milestones: Milestone[];
}

export default function CrewPhotoPage({ params }: { params: { projectId: string } }) {
  const { projectId } = params;
  const [project, setProject] = useState<ProjectData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [uploading, setUploading] = useState<string | null>(null);

  async function loadMilestones() {
    try {
      const res = await fetch(`${API_BASE}/api/v1/public/crew/${projectId}/milestones`);
      if (!res.ok) throw new Error("Project not found");
      const data = await res.json();
      setProject(data);

      // Auto-expand first incomplete milestone
      const first = data.milestones.find((m: Milestone) => !m.has_photo);
      if (first) setExpandedId(first.id);
    } catch {
      setError("Project not found or link is invalid.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadMilestones();
  }, [projectId]);

  async function handlePhotoCapture(milestoneId: string) {
    // For now, simulate with a placeholder URL
    // In production: camera capture → upload to S3 → get URL
    setUploading(milestoneId);

    try {
      // Create a file input to capture photo
      const input = document.createElement("input");
      input.type = "file";
      input.accept = "image/*";
      input.capture = "environment"; // Rear camera

      input.onchange = async (e) => {
        const file = (e.target as HTMLInputElement).files?.[0];
        if (!file) {
          setUploading(null);
          return;
        }

        // For MVP: convert to data URL and store
        // In production: upload to S3 presigned URL
        const reader = new FileReader();
        reader.onload = async () => {
          const photoUrl = `photo_${milestoneId}_${Date.now()}`;

          try {
            const res = await fetch(
              `${API_BASE}/api/v1/public/crew/${projectId}/complete-milestone`,
              {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                  milestone_id: milestoneId,
                  photo_url: photoUrl,
                }),
              }
            );

            if (!res.ok) throw new Error("Upload failed");

            // Refresh milestones
            await loadMilestones();

            // Auto-expand next incomplete milestone
            if (project) {
              const currentIdx = project.milestones.findIndex(
                (m) => m.id === milestoneId
              );
              const next = project.milestones.find(
                (m, i) => i > currentIdx && !m.has_photo
              );
              if (next) setExpandedId(next.id);
            }
          } catch {
            setError("Failed to upload photo. Try again.");
            setTimeout(() => setError(""), 3000);
          }
        };
        reader.readAsDataURL(file);
        setUploading(null);
      };

      input.click();
    } catch {
      setUploading(null);
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
        <div className="text-center">
          <HardHat className="h-12 w-12 text-orange-500 mx-auto mb-3 animate-pulse" />
          <p className="text-gray-400">Loading project...</p>
        </div>
      </div>
    );
  }

  if (error && !project) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
        <div className="text-center max-w-sm">
          <AlertCircle className="h-12 w-12 text-red-400 mx-auto mb-3" />
          <p className="text-gray-600">{error}</p>
        </div>
      </div>
    );
  }

  if (!project) return null;

  const completedCount = project.milestones.filter((m) => m.has_photo).length;
  const totalCount = project.milestones.length;
  const allDone = completedCount === totalCount;
  const progressPct = totalCount > 0 ? (completedCount / totalCount) * 100 : 0;

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-gray-900 text-white sticky top-0 z-10">
        <div className="max-w-lg mx-auto px-4 py-3">
          <div className="flex items-center gap-2 mb-1">
            <HardHat className="h-5 w-5 text-orange-500" />
            <span className="text-sm font-semibold">Roof Automated — Crew Photos</span>
          </div>
          <div className="flex items-center gap-2 text-xs text-gray-300">
            <MapPin className="h-3 w-3" />
            {project.property_address}
          </div>
          {/* Progress bar */}
          <div className="mt-2">
            <div className="flex items-center justify-between text-xs mb-1">
              <span className="text-gray-400">
                {completedCount} of {totalCount} photos
              </span>
              <span className="text-orange-400 font-medium">
                {Math.round(progressPct)}%
              </span>
            </div>
            <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden">
              <div
                className="h-full bg-orange-500 rounded-full transition-all duration-500"
                style={{ width: `${progressPct}%` }}
              />
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-lg mx-auto px-4 py-4 space-y-2">
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-sm text-red-700">
            {error}
          </div>
        )}

        {allDone && (
          <div className="bg-green-50 border border-green-200 rounded-xl p-4 text-center mb-4">
            <CheckCircle className="h-10 w-10 text-green-500 mx-auto mb-2" />
            <p className="font-semibold text-green-800">All photos captured!</p>
            <p className="text-sm text-green-600 mt-1">
              QC review will be completed shortly. Great work!
            </p>
          </div>
        )}

        {/* Milestone list */}
        {project.milestones.map((milestone, idx) => {
          const isExpanded = expandedId === milestone.id;
          const isDone = milestone.has_photo;
          const isCurrent = !isDone && expandedId === milestone.id;
          const isNext =
            !isDone &&
            idx ===
              project.milestones.findIndex((m) => !m.has_photo);

          return (
            <div
              key={milestone.id}
              className={clsx(
                "rounded-xl border transition-all overflow-hidden",
                isDone
                  ? "border-green-200 bg-green-50"
                  : isCurrent
                  ? "border-orange-300 bg-white shadow-md"
                  : "border-gray-200 bg-white"
              )}
            >
              {/* Milestone header */}
              <button
                onClick={() =>
                  setExpandedId(isExpanded ? null : milestone.id)
                }
                className="w-full flex items-center gap-3 px-4 py-3 text-left"
              >
                {isDone ? (
                  <CheckCircle className="h-6 w-6 text-green-500 shrink-0" />
                ) : (
                  <Circle
                    className={clsx(
                      "h-6 w-6 shrink-0",
                      isNext ? "text-orange-400" : "text-gray-300"
                    )}
                  />
                )}
                <div className="flex-1 min-w-0">
                  <p
                    className={clsx(
                      "text-sm font-medium",
                      isDone ? "text-green-800" : "text-gray-900"
                    )}
                  >
                    {milestone.sort_order}. {milestone.name}
                  </p>
                </div>
                {isExpanded ? (
                  <ChevronUp className="h-4 w-4 text-gray-400 shrink-0" />
                ) : (
                  <ChevronDown className="h-4 w-4 text-gray-400 shrink-0" />
                )}
              </button>

              {/* Expanded content */}
              {isExpanded && (
                <div className="px-4 pb-4 pt-0">
                  <p className="text-sm text-gray-600 mb-3 ml-9">
                    {milestone.description}
                  </p>

                  {isDone ? (
                    <div className="ml-9">
                      <p className="text-xs text-green-600 font-medium">
                        Photo captured
                      </p>
                    </div>
                  ) : (
                    <button
                      onClick={() => handlePhotoCapture(milestone.id)}
                      disabled={uploading === milestone.id}
                      className="ml-9 w-[calc(100%-2.25rem)] bg-orange-600 text-white py-3 rounded-xl
                        text-sm font-semibold flex items-center justify-center gap-2
                        hover:bg-orange-700 active:scale-[0.98] disabled:opacity-50
                        transition-all"
                    >
                      {uploading === milestone.id ? (
                        <Loader2 className="h-5 w-5 animate-spin" />
                      ) : (
                        <Camera className="h-5 w-5" />
                      )}
                      {uploading === milestone.id
                        ? "Uploading..."
                        : "Take Photo"}
                    </button>
                  )}
                </div>
              )}
            </div>
          );
        })}

        {/* Footer */}
        <div className="text-center pt-4 pb-8">
          <p className="text-xs text-gray-400">
            Photos are reviewed automatically. Questions? Text your dispatcher.
          </p>
        </div>
      </div>
    </div>
  );
}
