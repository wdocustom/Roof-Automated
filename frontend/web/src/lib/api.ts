/**
 * API client for the Roof-Automated backend.
 */

// In production, API calls go through the Next.js proxy (/api/proxy/...)
// which handles auth server-side. In dev, can hit the backend directly.
const API_BASE = "/api/proxy";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });

  if (!res.ok) {
    throw new Error(`API ${res.status}: ${res.statusText}`);
  }

  return res.json() as Promise<T>;
}

// ── Dashboard ────────────────────────────────────────────────

export interface ProjectSummary {
  active: number;
  completed_this_month: number;
  by_status: Record<string, number>;
}

export interface AgentPerformance {
  events_processed_7d: number;
  escalations_7d: number;
  escalation_rate_pct: number;
  autonomy_rate_pct: number;
}

export interface DashboardInsights {
  project_summary: ProjectSummary;
  agent_performance: AgentPerformance;
  insights: string[];
}

export interface AgentMetrics {
  period_days: number;
  by_agent: Record<string, number>;
  by_type: Record<string, number>;
  total_events: number;
}

export interface Alert {
  id: string;
  type: string;
  severity: "high" | "medium";
  project_id: string;
  description: string;
  data: Record<string, unknown>;
  created_at: string;
}

export interface AlertsResponse {
  alerts: Alert[];
  total: number;
  high_severity: number;
}

export interface CostTracking {
  period_days: number;
  total_agent_invocations: number;
  projects_touched: number;
  estimated_llm_cost: number;
  cost_per_project: number;
}

export function fetchInsights() {
  return apiFetch<DashboardInsights>("/dashboard/insights");
}

export function fetchAgentMetrics(days = 7) {
  return apiFetch<AgentMetrics>(`/dashboard/agent-metrics?days=${days}`);
}

export function fetchAlerts() {
  return apiFetch<AlertsResponse>("/dashboard/alerts");
}

export function fetchCostTracking(days = 30) {
  return apiFetch<CostTracking>(`/dashboard/cost-tracking?days=${days}`);
}

// ── Projects ─────────────────────────────────────────────────

export interface CustomerInfo {
  id: string;
  first_name: string | null;
  last_name: string | null;
  phone: string | null;
  email: string | null;
}

export interface Project {
  id: string;
  company_id: string;
  customer_id: string;
  property_address: string;
  property_city: string;
  property_state: string;
  property_zip: string;
  project_type: string;
  status: string;
  description: string | null;
  estimated_sqft: number | null;
  estimate_low: number | null;
  estimate_high: number | null;
  contract_amount: number | null;
  scheduled_start: string | null;
  scheduled_end: string | null;
  lead_source: string | null;
  created_at: string;
  updated_at: string;
  customer: CustomerInfo | null;
}

export interface ProjectListResponse {
  items: Project[];
  total: number;
}

export function fetchProjects(status?: string, skip = 0, limit = 50) {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  params.set("skip", String(skip));
  params.set("limit", String(limit));
  return apiFetch<ProjectListResponse>(`/projects?${params}`);
}

export function fetchProject(id: string) {
  return apiFetch<Project>(`/projects/${id}`);
}

export function updateProject(id: string, data: Record<string, unknown>) {
  return apiFetch<Project>(`/projects/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

// ── Messages ─────────────────────────────────────────────────

export interface MessageResponse {
  id: string;
  project_id: string | null;
  from_phone: string;
  to_phone: string;
  direction: "inbound" | "outbound";
  sender_type: string;
  body: string | null;
  channel: string;
  twilio_message_sid: string | null;
  twilio_status: string | null;
  agent_name: string | null;
  agent_confidence: number | null;
  created_at: string;
}

export interface Conversation {
  phone_number: string;
  message_count: number;
  last_message: string | null;
  last_message_at: string | null;
}

export interface ConversationThread {
  phone_number: string;
  messages: MessageResponse[];
  total: number;
}

export function fetchConversations() {
  return apiFetch<Conversation[]>("/messages");
}

export function fetchThread(phoneNumber: string) {
  return apiFetch<ConversationThread>(
    `/messages/${encodeURIComponent(phoneNumber)}`
  );
}

export interface SendMessageRequest {
  to_phone: string;
  body: string;
}

export interface SendMessageResult {
  message_id: string;
  twilio_sid: string;
  status: string;
}

export function sendMessage(data: SendMessageRequest) {
  return apiFetch<SendMessageResult>("/messages/send", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

// ── Projects (create) ───────────────────────────────────────

export interface ProjectCreateRequest {
  customer_name?: string;
  customer_phone?: string;
  customer_email?: string;
  property_address: string;
  property_city: string;
  property_state: string;
  property_zip: string;
  project_type: string;
  description?: string;
  lead_source?: string;
}

export interface SendInvoiceResponse {
  status: string;
  payment_url: string;
  amount: number;
  twilio_sid: string;
  customer_phone: string;
}

export function sendInvoice(projectId: string) {
  return apiFetch<SendInvoiceResponse>(`/projects/${projectId}/send-invoice`, {
    method: "POST",
  });
}

// ── Contracts ──────────────────────────────────────────────

export interface ContractSummary {
  contract_id: string;
  token: string;
  status: string;
  contract_amount: number;
  signer_name: string | null;
  signed_at: string | null;
  created_at: string;
}

export interface GenerateContractResponse {
  contract_id: string;
  token: string;
  status: string;
  contract_amount: number;
}

export function generateContract(projectId: string, contractAmount?: number) {
  return apiFetch<GenerateContractResponse>(
    `/projects/${projectId}/generate-contract`,
    {
      method: "POST",
      body: JSON.stringify({
        project_id: projectId,
        ...(contractAmount ? { contract_amount: contractAmount } : {}),
      }),
    }
  );
}

export function sendContract(contractId: string) {
  return apiFetch<{ status: string; twilio_sid: string }>(
    `/contracts/${contractId}/send`,
    { method: "POST" }
  );
}

export function listProjectContracts(projectId: string) {
  return apiFetch<ContractSummary[]>(`/projects/${projectId}/contracts`);
}

export function createProject(data: ProjectCreateRequest) {
  return apiFetch<Project>("/projects", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

// ── Onboarding ──────────────────────────────────────────────

export interface OnboardingStatus {
  has_company: boolean;
  company_name: string | null;
  company_id: string | null;
}

export interface OnboardingRequest {
  company_name: string;
  phone?: string;
  email?: string;
  address?: string;
  city?: string;
  state?: string;
  zip_code?: string;
  contractor_license_number?: string;
  contractor_license_state?: string;
  preferred_area_code?: string;
  skip_twilio?: boolean;
}

export interface OnboardingResponse {
  company_id: string;
  company_name: string;
  twilio_phone_number: string | null;
  messaging_service_sid: string | null;
  status: string;
}

export function fetchOnboardingStatus() {
  return apiFetch<OnboardingStatus>("/onboarding/status");
}

export function completeOnboarding(data: OnboardingRequest) {
  return apiFetch<OnboardingResponse>("/onboarding/complete", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

// ── Settings ─────────────────────────────────────────────────

export interface CompanySettings {
  name: string;
  phone: string | null;
  email: string | null;
  address: string | null;
  city: string | null;
  state: string | null;
  zip_code: string | null;
  twilio_phone_number: string | null;
  human_review_threshold_dollars: number;
  agent_confidence_threshold: number;
}

export function fetchCompanySettings() {
  return apiFetch<CompanySettings>("/settings/company");
}

export function updateCompanySettings(data: Partial<CompanySettings>) {
  return apiFetch<CompanySettings>("/settings/company", {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}
