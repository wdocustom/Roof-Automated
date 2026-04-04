"use client";

import { useState, useEffect } from "react";
import {
  CheckCircle,
  Star,
  Share2,
  CreditCard,
  Shield,
  Phone,
  MapPin,
  Calendar,
  Camera,
  HardHat,
  FileText,
  Loader2,
  AlertCircle,
  Heart,
  Clock,
  ClipboardCheck,
  PenTool,
  Hammer,
  CircleDot,
} from "lucide-react";
import { clsx } from "clsx";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

interface Stage {
  stage: string;
  label: string;
  completed: boolean;
  current: boolean;
}

interface MilestoneData {
  name: string;
  status: string;
  sort_order: number;
  has_photo: boolean;
}

interface ProjectPage {
  token: string;
  project_id: string;
  status: string;
  status_message: string;
  status_badge: { text: string; color: string };
  stages: Stage[];

  // Flags
  is_paid: boolean;
  is_completed: boolean;
  is_in_progress: boolean;
  is_pre_construction: boolean;
  has_contract: boolean;
  show_payment: boolean;
  show_review: boolean;
  show_referral: boolean;
  show_milestones: boolean;
  show_schedule: boolean;
  show_estimate: boolean;
  show_contract: boolean;

  company_name: string;
  company_phone: string;
  company_license: string;
  customer_name: string;
  property_address: string;
  property_city: string;
  property_state: string;
  property_zip: string;
  project_type: string;
  description: string;
  created_at: string;
  completed_at: string | null;
  contract_amount: number;
  deposit_amount: number;
  balance_due: number;

  estimate: {
    estimate_low: number | null;
    estimate_high: number | null;
    contract_amount: number;
    sqft: number | null;
  } | null;

  contract: {
    id: string;
    status: string;
    signed_at: string | null;
    sign_url: string | null;
  } | null;

  schedule: {
    start_date: string | null;
    end_date: string | null;
  } | null;

  milestones: MilestoneData[];
  milestone_progress: {
    total: number;
    completed: number;
    percentage: number;
  };
  photos: { milestone: string; url: string; sort_order: number }[];
  review: {
    rating: number;
    review_text: string;
    reviewer_name: string;
    quality_rating: number | null;
    communication_rating: number | null;
    timeliness_rating: number | null;
    cleanup_rating: number | null;
  } | null;
  referral_text: string;
  referral_phone: string;
}

function StarRating({
  value,
  onChange,
  size = "md",
}: {
  value: number;
  onChange?: (v: number) => void;
  size?: "sm" | "md" | "lg";
}) {
  const sizeClass = size === "lg" ? "h-8 w-8" : size === "sm" ? "h-4 w-4" : "h-5 w-5";
  return (
    <div className="flex gap-0.5">
      {[1, 2, 3, 4, 5].map((i) => (
        <button
          key={i}
          type="button"
          onClick={() => onChange?.(i)}
          disabled={!onChange}
          className={clsx(!onChange && "cursor-default")}
        >
          <Star
            className={clsx(
              sizeClass,
              i <= value ? "text-yellow-400 fill-yellow-400" : "text-gray-300"
            )}
          />
        </button>
      ))}
    </div>
  );
}

function formatCurrency(n: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(n);
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

const BADGE_COLORS: Record<string, string> = {
  blue: "bg-blue-500/20 text-blue-400",
  indigo: "bg-indigo-500/20 text-indigo-400",
  green: "bg-green-500/20 text-green-400",
  purple: "bg-purple-500/20 text-purple-400",
  orange: "bg-orange-500/20 text-orange-400",
  yellow: "bg-yellow-500/20 text-yellow-400",
  gray: "bg-gray-500/20 text-gray-400",
};

const MILESTONE_STATUS_COLORS: Record<string, string> = {
  approved: "bg-green-500",
  awaiting_qc: "bg-yellow-500",
  in_progress: "bg-blue-500",
  pending: "bg-gray-300",
  rejected: "bg-red-500",
};

export default function CustomerProjectPage({ params }: { params: { token: string } }) {
  const { token } = params;
  const [project, setProject] = useState<ProjectPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Review form
  const [showReviewForm, setShowReviewForm] = useState(false);
  const [rating, setRating] = useState(0);
  const [reviewText, setReviewText] = useState("");
  const [qualityRating, setQualityRating] = useState(0);
  const [communicationRating, setCommunicationRating] = useState(0);
  const [timelinessRating, setTimelinessRating] = useState(0);
  const [cleanupRating, setCleanupRating] = useState(0);
  const [submittingReview, setSubmittingReview] = useState(false);
  const [reviewSubmitted, setReviewSubmitted] = useState(false);

  // Payment
  const [loadingPayment, setLoadingPayment] = useState(false);

  // Share
  const [shared, setShared] = useState(false);

  useEffect(() => {
    fetch(`${API_BASE}/api/v1/public/project/${token}`)
      .then((r) => {
        if (!r.ok) throw new Error("Not found");
        return r.json();
      })
      .then(setProject)
      .catch(() => setError("Project not found."))
      .finally(() => setLoading(false));
  }, [token]);

  async function handlePay() {
    setLoadingPayment(true);
    try {
      const res = await fetch(`${API_BASE}/api/v1/public/project/${token}/pay`, {
        method: "POST",
      });
      if (!res.ok) throw new Error("Payment failed");
      const data = await res.json();
      window.location.href = data.payment_url;
    } catch {
      setError("Failed to create payment link.");
      setTimeout(() => setError(""), 3000);
    } finally {
      setLoadingPayment(false);
    }
  }

  async function handleReviewSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (rating === 0) return;
    setSubmittingReview(true);
    try {
      const res = await fetch(`${API_BASE}/api/v1/public/project/${token}/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          rating,
          review_text: reviewText,
          quality_rating: qualityRating || null,
          communication_rating: communicationRating || null,
          timeliness_rating: timelinessRating || null,
          cleanup_rating: cleanupRating || null,
        }),
      });
      if (!res.ok) throw new Error("Failed");
      setReviewSubmitted(true);
      setShowReviewForm(false);
    } catch {
      setError("Failed to submit review.");
      setTimeout(() => setError(""), 3000);
    } finally {
      setSubmittingReview(false);
    }
  }

  function handleShare() {
    if (!project) return;
    const text = project.referral_text;
    if (navigator.share) {
      navigator.share({ text }).catch(() => {});
    } else {
      navigator.clipboard.writeText(text);
      setShared(true);
      setTimeout(() => setShared(false), 3000);
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <HardHat className="h-12 w-12 text-orange-500 animate-pulse" />
      </div>
    );
  }

  if (error && !project) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
        <div className="text-center">
          <AlertCircle className="h-12 w-12 text-red-400 mx-auto mb-3" />
          <p className="text-gray-600">{error}</p>
        </div>
      </div>
    );
  }

  if (!project) return null;

  const fullAddress = `${project.property_address}, ${project.property_city}, ${project.property_state} ${project.property_zip}`;
  const hasReview = project.review || reviewSubmitted;
  const badgeColor = BADGE_COLORS[project.status_badge.color] || BADGE_COLORS.gray;

  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-900 via-gray-900 to-gray-50">
      {/* Hero */}
      <div className="bg-gray-900 text-white pb-12 pt-8">
        <div className="max-w-2xl mx-auto px-4 text-center">
          <div className="flex items-center justify-center gap-2 mb-6">
            <HardHat className="h-8 w-8 text-orange-500" />
            <span className="text-xl font-bold tracking-tight">
              {project.company_name}
            </span>
          </div>

          <div className={clsx(
            "inline-flex items-center gap-2 px-4 py-1.5 rounded-full text-sm font-medium mb-4",
            badgeColor
          )}>
            {project.is_completed || project.is_paid ? (
              <CheckCircle className="h-4 w-4" />
            ) : project.is_in_progress ? (
              <Hammer className="h-4 w-4" />
            ) : (
              <CircleDot className="h-4 w-4" />
            )}
            {project.status_badge.text}
          </div>

          <h1 className="text-2xl sm:text-3xl font-bold mb-2">
            {project.project_type}
          </h1>

          <p className="text-gray-300 text-sm mb-3">
            {project.status_message}
          </p>

          <div className="flex items-center justify-center gap-2 text-gray-400 text-sm">
            <MapPin className="h-4 w-4" />
            {fullAddress}
          </div>

          {project.customer_name && (
            <p className="text-gray-400 text-sm mt-2">
              Prepared for <span className="text-white font-medium">{project.customer_name}</span>
            </p>
          )}
        </div>
      </div>

      <div className="max-w-2xl mx-auto px-4 -mt-6 space-y-4 pb-12">
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-sm text-red-700">
            {error}
          </div>
        )}

        {/* Stage progress tracker */}
        <div className="bg-white rounded-2xl shadow-lg p-6">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-500 mb-4 flex items-center gap-2">
            <ClipboardCheck className="h-4 w-4" /> Project Progress
          </h2>
          <div className="flex items-center justify-between">
            {project.stages.map((stage, i) => (
              <div key={stage.stage} className="flex items-center flex-1 last:flex-initial">
                <div className="flex flex-col items-center">
                  <div
                    className={clsx(
                      "w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold transition-colors",
                      stage.completed
                        ? "bg-green-500 text-white"
                        : stage.current
                        ? "bg-orange-500 text-white ring-4 ring-orange-100"
                        : "bg-gray-200 text-gray-400"
                    )}
                  >
                    {stage.completed ? (
                      <CheckCircle className="h-4 w-4" />
                    ) : (
                      i + 1
                    )}
                  </div>
                  <span
                    className={clsx(
                      "text-[10px] mt-1 text-center leading-tight max-w-[60px]",
                      stage.current ? "font-bold text-orange-600" : "text-gray-400"
                    )}
                  >
                    {stage.label}
                  </span>
                </div>
                {i < project.stages.length - 1 && (
                  <div
                    className={clsx(
                      "h-0.5 flex-1 mx-1 mt-[-16px]",
                      stage.completed ? "bg-green-500" : "bg-gray-200"
                    )}
                  />
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Estimate card — pre-construction only */}
        {project.show_estimate && project.estimate && (
          <div className="bg-blue-50 rounded-2xl shadow-sm border border-blue-200 p-6">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-blue-600 mb-4 flex items-center gap-2">
              <FileText className="h-4 w-4" /> Your Estimate
            </h2>
            <div className="space-y-3">
              {project.estimate.sqft && (
                <div className="flex justify-between text-sm">
                  <span className="text-blue-600/70">Roof Area</span>
                  <span className="font-semibold text-blue-900">
                    {project.estimate.sqft.toLocaleString()} sq ft
                  </span>
                </div>
              )}
              {project.estimate.estimate_low && project.estimate.estimate_high && (
                <div className="flex justify-between text-sm">
                  <span className="text-blue-600/70">Estimated Range</span>
                  <span className="font-semibold text-blue-900">
                    {formatCurrency(project.estimate.estimate_low)} – {formatCurrency(project.estimate.estimate_high)}
                  </span>
                </div>
              )}
              {project.estimate.contract_amount > 0 && (
                <div className="border-t border-blue-200 pt-3 flex justify-between">
                  <span className="font-semibold text-blue-900">Project Total</span>
                  <span className="text-lg font-bold text-blue-900">
                    {formatCurrency(project.estimate.contract_amount)}
                  </span>
                </div>
              )}
            </div>
            {project.description && (
              <div className="mt-4 pt-4 border-t border-blue-200">
                <p className="text-xs font-semibold text-blue-600/70 uppercase mb-1">Scope of Work</p>
                <p className="text-sm text-blue-900 whitespace-pre-line">{project.description}</p>
              </div>
            )}
          </div>
        )}

        {/* Contract card — when contract exists */}
        {project.show_contract && project.contract && (
          <div className={clsx(
            "rounded-2xl shadow-sm border p-6",
            project.contract.status === "signed"
              ? "bg-green-50 border-green-200"
              : "bg-indigo-50 border-indigo-200"
          )}>
            <h2 className={clsx(
              "text-sm font-semibold uppercase tracking-wider mb-4 flex items-center gap-2",
              project.contract.status === "signed" ? "text-green-600" : "text-indigo-600"
            )}>
              <PenTool className="h-4 w-4" />
              {project.contract.status === "signed" ? "Contract Signed" : "Contract Ready"}
            </h2>
            {project.contract.status === "signed" ? (
              <div className="flex items-center gap-2 text-sm text-green-700">
                <CheckCircle className="h-4 w-4" />
                Signed on {formatDate(project.contract.signed_at!)}
              </div>
            ) : (
              <div className="space-y-3">
                <p className="text-sm text-indigo-700">
                  Your contract is ready. Review the terms and sign electronically.
                </p>
                {project.contract.sign_url && (
                  <a
                    href={project.contract.sign_url}
                    className="block w-full bg-indigo-600 text-white py-3.5 rounded-xl text-base font-semibold
                      hover:bg-indigo-700 transition-colors text-center"
                  >
                    Review & Sign Contract
                  </a>
                )}
              </div>
            )}
          </div>
        )}

        {/* Schedule card */}
        {project.show_schedule && project.schedule && (
          <div className="bg-purple-50 rounded-2xl shadow-sm border border-purple-200 p-6">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-purple-600 mb-4 flex items-center gap-2">
              <Calendar className="h-4 w-4" /> Scheduled Date
            </h2>
            <div className="flex items-center gap-3">
              <div className="bg-purple-100 rounded-lg p-3">
                <Calendar className="h-6 w-6 text-purple-600" />
              </div>
              <div>
                <p className="font-semibold text-purple-900">
                  {project.schedule.start_date
                    ? formatDate(project.schedule.start_date)
                    : "Date TBD"}
                </p>
                {project.schedule.end_date && project.schedule.start_date !== project.schedule.end_date && (
                  <p className="text-sm text-purple-600/70">
                    through {formatDate(project.schedule.end_date)}
                  </p>
                )}
              </div>
            </div>
            <div className="mt-4 pt-4 border-t border-purple-200">
              <p className="text-xs font-semibold text-purple-600/70 uppercase mb-2">Before We Arrive</p>
              <ul className="space-y-1 text-sm text-purple-800">
                <li>Move vehicles from the driveway</li>
                <li>Secure pets inside or away from work area</li>
                <li>Close windows and blinds near the roof</li>
                <li>Expect noise during work hours (7 AM – 6 PM)</li>
              </ul>
            </div>
          </div>
        )}

        {/* Milestone progress — during/after work */}
        {project.show_milestones && project.milestones.length > 0 && (
          <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-6">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-500 mb-4 flex items-center gap-2">
              <Hammer className="h-4 w-4" /> Work Progress
            </h2>

            {/* Progress bar */}
            <div className="mb-4">
              <div className="flex justify-between text-xs text-gray-500 mb-1">
                <span>{project.milestone_progress.completed} of {project.milestone_progress.total} steps complete</span>
                <span className="font-semibold">{project.milestone_progress.percentage}%</span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2.5">
                <div
                  className="bg-green-500 rounded-full h-2.5 transition-all duration-500"
                  style={{ width: `${project.milestone_progress.percentage}%` }}
                />
              </div>
            </div>

            {/* Milestone list */}
            <div className="space-y-2">
              {project.milestones.map((m) => (
                <div
                  key={m.name}
                  className="flex items-center gap-3 py-2 border-b border-gray-100 last:border-0"
                >
                  <div
                    className={clsx(
                      "w-3 h-3 rounded-full flex-shrink-0",
                      MILESTONE_STATUS_COLORS[m.status] || "bg-gray-300"
                    )}
                  />
                  <span className={clsx(
                    "text-sm flex-1",
                    m.status === "approved"
                      ? "text-green-700 font-medium"
                      : m.status === "pending"
                      ? "text-gray-400"
                      : "text-gray-700"
                  )}>
                    {m.name}
                  </span>
                  {m.status === "approved" && (
                    <CheckCircle className="h-4 w-4 text-green-500 flex-shrink-0" />
                  )}
                  {m.status === "awaiting_qc" && (
                    <Clock className="h-4 w-4 text-yellow-500 flex-shrink-0" />
                  )}
                  {m.has_photo && (
                    <Camera className="h-4 w-4 text-gray-400 flex-shrink-0" />
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Payment card — always show if contract exists */}
        {project.has_contract && project.contract_amount > 0 && (
          <div className={clsx(
            "rounded-2xl shadow-lg p-6",
            project.is_paid
              ? "bg-green-50 border border-green-200"
              : "bg-white border border-gray-200"
          )}>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-500">
                Payment
              </h2>
              {project.is_paid && (
                <span className="inline-flex items-center gap-1 bg-green-100 text-green-700 px-3 py-1 rounded-full text-xs font-semibold">
                  <CheckCircle className="h-3 w-3" /> Paid in Full
                </span>
              )}
            </div>

            <div className="space-y-2 mb-4">
              <div className="flex justify-between text-sm">
                <span className="text-gray-500">Contract Total</span>
                <span className="font-semibold text-gray-900">{formatCurrency(project.contract_amount)}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-gray-500">Deposit (50%)</span>
                <span className="text-gray-700">{formatCurrency(project.deposit_amount)}</span>
              </div>
              <div className="border-t border-gray-200 pt-2 flex justify-between">
                <span className="font-semibold text-gray-900">
                  {project.is_paid ? "Balance" : "Balance Due"}
                </span>
                <span className={clsx(
                  "text-lg font-bold",
                  project.is_paid ? "text-green-600" : "text-gray-900"
                )}>
                  {project.is_paid ? "$0" : formatCurrency(project.balance_due)}
                </span>
              </div>
            </div>

            {project.show_payment && project.balance_due > 0 && (
              <button
                onClick={handlePay}
                disabled={loadingPayment}
                className="w-full bg-orange-600 text-white py-3.5 rounded-xl text-base font-semibold
                  hover:bg-orange-700 disabled:opacity-50 transition-colors
                  flex items-center justify-center gap-2"
              >
                {loadingPayment ? (
                  <Loader2 className="h-5 w-5 animate-spin" />
                ) : (
                  <CreditCard className="h-5 w-5" />
                )}
                Pay {formatCurrency(project.balance_due)}
              </button>
            )}
          </div>
        )}

        {/* Project details */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-6">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-500 mb-4 flex items-center gap-2">
            <FileText className="h-4 w-4" /> Project Details
          </h2>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="text-gray-500">Type</span>
              <p className="font-medium text-gray-900">{project.project_type}</p>
            </div>
            <div>
              <span className="text-gray-500">Status</span>
              <p className="font-medium text-gray-900 capitalize">
                {project.status.replace("_", " ")}
              </p>
            </div>
            <div>
              <span className="text-gray-500">Started</span>
              <p className="font-medium text-gray-900">
                {new Date(project.created_at).toLocaleDateString()}
              </p>
            </div>
            {project.completed_at && (
              <div>
                <span className="text-gray-500">Completed</span>
                <p className="font-medium text-gray-900">
                  {new Date(project.completed_at).toLocaleDateString()}
                </p>
              </div>
            )}
          </div>
          {project.description && !project.show_estimate && (
            <p className="text-sm text-gray-600 mt-4 border-t border-gray-100 pt-4">
              {project.description}
            </p>
          )}
        </div>

        {/* Photos */}
        {project.photos.length > 0 && (
          <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-6">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-500 mb-4 flex items-center gap-2">
              <Camera className="h-4 w-4" /> Project Photos
            </h2>
            <div className="space-y-4">
              {project.photos.map((photo, i) => (
                <div key={i} className="space-y-1">
                  <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
                    {photo.milestone}
                  </p>
                  <div className="bg-gray-100 rounded-xl h-48 flex items-center justify-center text-gray-400 text-sm overflow-hidden">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={photo.url}
                      alt={photo.milestone}
                      className="w-full h-full object-cover"
                      onError={(e) => {
                        (e.target as HTMLImageElement).style.display = "none";
                        (e.target as HTMLImageElement).parentElement!.innerHTML =
                          '<div class="flex items-center justify-center h-full"><svg class="h-8 w-8 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" /><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" /></svg></div>';
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Review — only show for completed/paid projects */}
        {project.show_review && (
          <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-6">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-500 mb-4 flex items-center gap-2">
              <Star className="h-4 w-4" /> Your Review
            </h2>

            {hasReview ? (
              <div className="space-y-3">
                <StarRating value={project.review?.rating || rating} size="lg" />
                {(project.review?.review_text || reviewText) && (
                  <p className="text-sm text-gray-700 italic">
                    &ldquo;{project.review?.review_text || reviewText}&rdquo;
                  </p>
                )}
                <p className="text-xs text-green-600 font-medium">
                  Thank you for your review!
                </p>
              </div>
            ) : showReviewForm ? (
              <form onSubmit={handleReviewSubmit} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Overall Rating
                  </label>
                  <StarRating value={rating} onChange={setRating} size="lg" />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  {[
                    { label: "Quality", value: qualityRating, set: setQualityRating },
                    { label: "Communication", value: communicationRating, set: setCommunicationRating },
                    { label: "Timeliness", value: timelinessRating, set: setTimelinessRating },
                    { label: "Cleanup", value: cleanupRating, set: setCleanupRating },
                  ].map((cat) => (
                    <div key={cat.label}>
                      <label className="block text-xs text-gray-500 mb-1">{cat.label}</label>
                      <StarRating value={cat.value} onChange={cat.set} size="sm" />
                    </div>
                  ))}
                </div>

                <textarea
                  value={reviewText}
                  onChange={(e) => setReviewText(e.target.value)}
                  placeholder="Tell us about your experience..."
                  rows={3}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm
                    focus:border-orange-500 focus:ring-1 focus:ring-orange-500 outline-none resize-none"
                />

                <button
                  type="submit"
                  disabled={rating === 0 || submittingReview}
                  className="w-full bg-orange-600 text-white py-3 rounded-xl text-sm font-semibold
                    hover:bg-orange-700 disabled:opacity-50 transition-colors"
                >
                  {submittingReview ? "Submitting..." : "Submit Review"}
                </button>
              </form>
            ) : (
              <button
                onClick={() => setShowReviewForm(true)}
                className="w-full border-2 border-dashed border-gray-300 rounded-xl py-4
                  text-sm text-gray-500 hover:border-orange-300 hover:text-orange-600
                  transition-colors flex items-center justify-center gap-2"
              >
                <Star className="h-4 w-4" /> Rate your experience
              </button>
            )}
          </div>
        )}

        {/* Referral — only show for completed/paid */}
        {project.show_referral && (
          <div className="bg-gradient-to-r from-orange-500 to-orange-600 rounded-2xl shadow-lg p-6 text-white">
            <div className="flex items-center gap-2 mb-2">
              <Heart className="h-5 w-5" />
              <h2 className="font-semibold">Love your new roof?</h2>
            </div>
            <p className="text-orange-100 text-sm mb-4">
              Refer a friend or neighbor and help them get the same great service!
            </p>
            <button
              onClick={handleShare}
              className="w-full bg-white text-orange-600 py-3 rounded-xl text-sm font-semibold
                hover:bg-orange-50 transition-colors flex items-center justify-center gap-2"
            >
              <Share2 className="h-4 w-4" />
              {shared ? "Copied to clipboard!" : "Share with Friends & Family"}
            </button>
            {project.referral_phone && (
              <p className="text-xs text-orange-200 text-center mt-3">
                Or have them text <span className="font-mono font-bold text-white">{project.referral_phone}</span> for a free estimate
              </p>
            )}
          </div>
        )}

        {/* Contractor info — always visible */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-6">
          <div className="flex items-center gap-3">
            <div className="bg-gray-900 rounded-full p-2.5">
              <HardHat className="h-5 w-5 text-orange-500" />
            </div>
            <div>
              <p className="font-semibold text-gray-900">{project.company_name}</p>
              {project.company_license && (
                <p className="text-xs text-gray-500">License: {project.company_license}</p>
              )}
            </div>
          </div>
          {project.company_phone && (
            <a
              href={`tel:${project.company_phone}`}
              className="mt-4 w-full inline-flex items-center justify-center gap-2
                border border-gray-200 rounded-xl py-2.5 text-sm font-medium
                text-gray-700 hover:bg-gray-50 transition-colors"
            >
              <Phone className="h-4 w-4" /> {project.company_phone}
            </a>
          )}
        </div>

        {/* Footer */}
        <div className="text-center pt-2 pb-4">
          <div className="flex items-center justify-center gap-1 text-xs text-gray-400">
            <Shield className="h-3 w-3" /> Powered by Roof Automated
          </div>
        </div>
      </div>
    </div>
  );
}
