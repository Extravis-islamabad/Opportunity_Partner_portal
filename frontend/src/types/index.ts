// ==================== Common ====================
export interface ErrorResponse {
  code: string;
  message: string;
  details: Record<string, unknown>;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface MessageResponse {
  message: string;
}

// ==================== Auth ====================
export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: UserBasic;
}

export interface RefreshResponse {
  access_token: string;
  token_type: string;
}

export type UserRole = 'admin' | 'partner' | 'sales_rep';

export interface UserBasic {
  id: number;
  full_name: string;
  email: string;
  role: UserRole;
  status: string;
  company_id: number | null;
  company_name: string | null;
  is_superadmin: boolean;
  is_channel_manager?: boolean;
  managed_company_count?: number;
  has_completed_onboarding?: boolean;
}

// ==================== User ====================
export interface UserResponse {
  id: number;
  full_name: string;
  email: string;
  role: string;
  status: string;
  job_title: string | null;
  phone: string | null;
  company_id: number | null;
  company_name: string | null;
  is_superadmin: boolean;
  last_login_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface UserCreateRequest {
  full_name: string;
  email: string;
  role: string;
  job_title?: string;
  phone?: string;
  company_id?: number;
}

export interface UserUpdateRequest {
  full_name?: string;
  job_title?: string;
  phone?: string;
  status?: string;
}

// ==================== Company ====================
export interface CompanyResponse {
  id: number;
  name: string;
  country: string;
  region: string;
  city: string;
  industry: string;
  contact_email: string;
  status: string;
  tier: string;
  channel_manager_id: number;
  channel_manager_name: string | null;
  partner_count: number;
  opportunity_count: number;
  created_at: string;
  updated_at: string;
}

export interface CompanyDetailResponse extends CompanyResponse {
  partners: PartnerAccountBrief[];
}

export interface PartnerAccountBrief {
  id: number;
  full_name: string;
  email: string;
  status: string;
  job_title: string | null;
  created_at: string;
}

export interface CompanyCreateRequest {
  name: string;
  country: string;
  region: string;
  city: string;
  industry: string;
  contact_email: string;
  channel_manager_id: number;
}

export interface CompanyUpdateRequest {
  name?: string;
  country?: string;
  region?: string;
  city?: string;
  industry?: string;
  contact_email?: string;
  channel_manager_id?: number;
}

// ==================== Opportunity ====================
export type OpportunityStatus =
  | 'draft'
  | 'pending_review'
  | 'under_review'
  | 'approved'
  | 'rejected'
  | 'removed'
  | 'multi_partner_flagged';

export type ProductName = 'MonetX' | 'PatchX' | 'SupportX';
export type StageProbability = 0.1 | 0.3 | 0.6 | 0.7 | 0.9 | 1.0;

export interface OpportunityResponse {
  id: number;
  name: string;
  customer_name: string;
  region: string;
  country: string;
  city: string;
  worth: string;
  closing_date: string;
  requirements: string;
  status: OpportunityStatus;
  preferred_partner: boolean;
  multi_partner_alert: boolean;
  rejection_reason: string | null;
  internal_notes: string | null;
  submitted_by: number;
  submitted_by_name: string | null;
  company_id: number;
  company_name: string | null;
  reviewed_by: number | null;
  reviewer_name: string | null;
  sales_rep_id: number | null;
  sales_rep_name: string | null;
  industry: string | null;
  product: string | null;
  stage_probability: string | null;
  time_frame: string | null;
  submitted_at: string | null;
  reviewed_at: string | null;
  documents: OppDocumentResponse[];
  ai_score: number | null;
  ai_reasoning: string | null;
  ai_scored_at: string | null;
  ai_duplicate_of_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface OpportunityListItem {
  id: number;
  name: string;
  customer_name: string;
  country: string;
  worth: string;
  closing_date: string;
  status: OpportunityStatus;
  preferred_partner: boolean;
  multi_partner_alert: boolean;
  submitted_by_name: string | null;
  company_name: string | null;
  company_id: number;
  industry: string | null;
  product: string | null;
  stage_probability: string | null;
  time_frame: string | null;
  sales_rep_id: number | null;
  sales_rep_name: string | null;
  submitted_at: string | null;
  ai_score: number | null;
  ai_reasoning: string | null;
  ai_duplicate_of_id?: number | null;
  created_at: string;
}

export interface OppDocumentResponse {
  id: number;
  file_name: string;
  file_url: string;
  file_size: number | null;
  content_type: string | null;
  uploaded_at: string;
}

export interface OpportunityCreateRequest {
  name: string;
  customer_name: string;
  region: string;
  country: string;
  city: string;
  worth: number;
  closing_date: string;
  requirements: string;
  status?: string;
  industry?: string;
  product?: string;
  stage_probability?: number;
  time_frame?: string;
  sales_rep_id?: number;
}

// 2027 Target Plan analytics (admin dashboard)
export interface ProductBreakdown {
  product: string;
  opportunity_count: number;
  total_worth: string;
  weighted_pipeline: string;
}
export interface OppIndustryBreakdown {
  industry: string;
  opportunity_count: number;
  total_worth: string;
}
export interface StageBreakdown {
  probability: number;
  stage_label: string;
  opportunity_count: number;
  total_worth: string;
}
export interface QuarterBreakdown {
  time_frame: string;
  opportunity_count: number;
  total_worth: string;
  weighted_pipeline: string;
}
export interface SalesRepBreakdown {
  sales_rep_id: number;
  sales_rep_name: string;
  opportunity_count: number;
  total_worth: string;
  weighted_pipeline: string;
}
export interface TargetPlanAnalytics {
  total_opportunities: number;
  total_worth: string;
  weighted_pipeline: string;
  by_product: ProductBreakdown[];
  by_industry: OppIndustryBreakdown[];
  by_stage: StageBreakdown[];
  by_quarter: QuarterBreakdown[];
  by_sales_rep: SalesRepBreakdown[];
}

// ==================== Knowledge Base ====================
export interface KBDocumentResponse {
  id: number;
  title: string;
  category: string;
  description: string | null;
  file_name: string;
  file_url: string;
  file_size: number | null;
  content_type: string | null;
  version: number;
  uploaded_by: number;
  uploader_name: string | null;
  download_count: number;
  published_at: string;
  created_at: string;
  updated_at: string;
}

export interface KBCategoryResponse {
  name: string;
  document_count: number;
}

// ==================== LMS ====================
export interface CourseResponse {
  id: number;
  title: string;
  description: string | null;
  status: string;
  modules_json: CourseModule[];
  duration_hours: number | null;
  thumbnail_url: string | null;
  enrollment_count: number;
  completion_count: number;
  created_at: string;
  updated_at: string;
}

export type CourseModuleType = 'video' | 'pdf' | 'text' | 'quiz';

export interface CourseModule {
  id: string;
  title: string;
  type: CourseModuleType;
  content_url?: string | null;
  description?: string | null;
  duration_minutes?: number | null;
  order: number;
}

export interface QuizQuestion {
  id: number;
  question: string;
  options: string[];
  correct?: number;
  correct_answer?: number;
  points?: number;
}

export interface EnrollmentResponse {
  id: number;
  user_id: number;
  user_name: string | null;
  course_id: number;
  course_title: string | null;
  status: string;
  progress_json: Record<string, boolean> | null;
  completed_at: string | null;
  score?: number | null;
  attempt_count?: number;
  certificate_requested: boolean;
  certificate_requested_at: string | null;
  certificate_url: string | null;
  certificate_issued_at: string | null;
  enrolled_at: string;
}

// ==================== Document Request ====================
export interface DocRequestResponse {
  id: number;
  company_id: number;
  company_name: string | null;
  requested_by: number;
  requester_name: string | null;
  requester_email: string | null;
  description: string;
  reason: string | null;
  urgency: string;
  status: string;
  fulfilled_by: number | null;
  fulfiller_name: string | null;
  fulfilled_at: string | null;
  fulfilled_file_url: string | null;
  fulfilled_file_name: string | null;
  decline_reason: string | null;
  created_at: string;
  updated_at: string;
}

// ==================== Notification ====================
export interface NotificationResponse {
  id: number;
  user_id: number;
  type: string;
  title: string;
  message: string;
  read: boolean;
  entity_type: string | null;
  entity_id: number | null;
  created_at: string;
}

// ==================== Dashboard ====================
export interface OverdueOpportunityItem {
  id: number;
  name: string;
  company_name: string;
  closing_date: string;
  worth: string;
  status: string;
}

export interface TierProgress {
  next_tier: string | null;
  opps_required: number;
  opps_current: number;
  courses_required: number;
  courses_current: number;
  opps_progress_pct: number;
  courses_progress_pct: number;
}

export interface DashboardStats {
  total_companies: number;
  total_partners: number;
  total_opportunities: number;
  total_approved: number;
  total_rejected: number;
  total_pending: number;
  total_worth: string;
  approved_worth: string;
  overdue_count: number;
  overdue_opportunities: OverdueOpportunityItem[];
  pending_doc_requests: number;
}

export interface PartnerDashboard {
  my_opportunities: number;
  my_approved: number;
  my_rejected: number;
  my_pending: number;
  my_drafts: number;
  my_total_worth: string;
  my_approved_worth: string;
  company_tier: string;
  lms_courses_enrolled: number;
  lms_courses_completed: number;
  pending_doc_requests: number;
  tier_progress: TierProgress | null;
}

export interface CompanyPerformance {
  company_id: number;
  company_name: string;
  tier: string;
  opportunities_submitted: number;
  opportunities_won: number;
  opportunities_lost: number;
  total_worth: string;
  approved_worth: string;
  lms_completion_rate: number;
}

export interface DealRegistrationResponse {
  id: number;
  company_id: number;
  company_name: string | null;
  registered_by: number;
  registered_by_name: string | null;
  customer_name: string;
  deal_description: string;
  estimated_value: string;
  expected_close_date: string;
  status: string;
  exclusivity_start: string | null;
  exclusivity_end: string | null;
  rejection_reason: string | null;
}

export interface OpportunityStatusBreakdown {
  status: string;
  count: number;
}

export interface MonthlyOpportunityData {
  month: string;
  submitted: number;
  approved: number;
  rejected: number;
}

// ==================== Admin Analytics ====================
export interface RegionBreakdown {
  region: string;
  company_count: number;
  opportunity_count: number;
  total_worth: string;
  approved_worth: string;
}

export interface TierDistribution {
  tier: string;
  company_count: number;
  total_worth: string;
}

export interface IndustryBreakdown {
  industry: string;
  company_count: number;
  opportunity_count: number;
}

export interface TopCompany {
  company_id: number;
  company_name: string;
  tier: string;
  region: string;
  opportunities_won: number;
  approved_worth: string;
}

export interface FunnelStage {
  stage: string;
  count: number;
}

export interface RecentActivityItem {
  id: number;
  actor_name: string;
  action: string;
  entity_type: string;
  entity_id: number;
  timestamp: string;
}

export interface AdminAnalyticsResponse {
  regions: RegionBreakdown[];
  tiers: TierDistribution[];
  industries: IndustryBreakdown[];
  top_companies: TopCompany[];
  funnel: FunnelStage[];
  recent_activity: RecentActivityItem[];
}

// ==================== Commissions & Scorecard ====================
export type CommissionStatus = 'pending' | 'approved' | 'paid' | 'void';

export interface CommissionRead {
  id: number;
  deal_id: number;
  company_id: number;
  company_name: string | null;
  user_id: number | null;
  user_name: string | null;
  tier_at_calculation: string;
  rate_percentage: string;
  deal_value: string;
  amount: string;
  currency: string;
  status: CommissionStatus;
  notes: string | null;
  calculated_at: string;
  approved_at: string | null;
  paid_at: string | null;
  deal_customer_name: string | null;
  deal_expected_close_date: string | null;
}

export interface Badge {
  key: string;
  label: string;
  description: string;
  earned_at: string | null;
}

export interface MonthlyCommissionPoint {
  month: string;
  amount: string;
}

export interface ScorecardRead {
  company_id: number;
  company_name: string;
  tier: string;
  next_tier: string | null;
  total_approved_deals: number;
  total_closed_value: string;
  ytd_commission: string;
  lifetime_commission: string;
  tier_progress_pct: number;
  rank: number | null;
  badges: Badge[];
  monthly_commission: MonthlyCommissionPoint[];
}

export interface LeaderboardEntry {
  rank: number;
  company_id: number;
  company_name: string;
  tier: string;
  total_amount: string;
  deal_count: number;
}

export interface LeaderboardResponse {
  period: string;
  entries: LeaderboardEntry[];
}

export interface StatementPeriodSummary {
  period_start: string;
  period_end: string;
  company_id: number;
  company_name: string | null;
  total_amount: string;
  commission_count: number;
  currency: string;
}

// ==================== POC ====================

export type PocStatus = 'not_started' | 'running' | 'successful' | 'unsuccessful';
export type PocStageKey =
  | 'vm_provisioning'
  | 'deployment'
  | 'device_onboarding'
  | 'dashboarding'
  | 'fine_tuning';

export interface PocStageState {
  key: PocStageKey;
  label: string;
  completed: boolean;
  completed_at: string | null;
}

export interface PocResponse {
  id: number;
  opportunity_id: number;
  status: PocStatus;

  start_date: string | null;
  target_end_date: string | null;
  end_date: string | null;

  vm_provisioning_completed_at: string | null;
  deployment_completed_at: string | null;
  device_onboarding_completed_at: string | null;
  dashboarding_completed_at: string | null;
  fine_tuning_completed_at: string | null;

  closed_at: string | null;
  outcome_notes: string | null;
  failure_reason: string | null;
  notes: string | null;

  stages: PocStageState[];
  completed_stage_count: number;
  total_stage_count: number;
  current_stage: PocStageKey | null;
  current_stage_label: string | null;
  days_running: number | null;
  is_overdue: boolean;

  opportunity_name: string | null;
  customer_name: string | null;
  company_name: string | null;
  partner_name: string | null;
  country: string | null;
  city: string | null;
  region: string | null;
  product: string | null;
  worth: string | null;
  sales_rep_name: string | null;
  closed_by_name: string | null;

  created_at: string;
  updated_at: string;
}

export interface PocStartRequest {
  start_date: string;
  target_end_date?: string | null;
  notes?: string | null;
}

export interface PocCloseRequest {
  successful: boolean;
  end_date?: string | null;
  outcome_notes?: string | null;
  failure_reason?: string | null;
}

// ==================== Customer licence (post-PO) ====================

export type LicenseStatus = 'pending_activation' | 'active' | 'expiring_soon' | 'expired';

export interface LicenseResponse {
  id: number;
  opportunity_id: number;
  po_number: string | null;
  po_received_date: string | null;
  po_value: string | null;
  device_count: number | null;
  node_count: number | null;
  license_activated_at: string | null;
  license_expires_at: string | null;
  license_key: string | null;
  status: LicenseStatus;
  notes: string | null;
  days_until_expiry: number | null;
  opportunity_name: string | null;
  customer_name: string | null;
  company_name: string | null;
  country: string | null;
  product: string | null;
  created_at: string;
  updated_at: string;
}

export interface LicenseUpsertRequest {
  po_number?: string | null;
  po_received_date?: string | null;
  po_value?: string | null;
  device_count?: number | null;
  node_count?: number | null;
  license_activated_at?: string | null;
  license_expires_at?: string | null;
  license_key?: string | null;
  notes?: string | null;
}

// ==================== POC / deployment analytics ====================

export interface PocStatusCount {
  status: PocStatus;
  label: string;
  count: number;
  total_worth: string;
}

export interface PocStageProgress {
  stage: PocStageKey;
  label: string;
  completed_count: number;
  pending_count: number;
  avg_days_to_complete: number | null;
}

export interface PocCountryBreakdown {
  country: string;
  running: number;
  successful: number;
  unsuccessful: number;
  total_worth: string;
}

export interface PocSummary {
  total_pocs: number;
  not_started: number;
  running: number;
  successful: number;
  unsuccessful: number;
  overdue: number;
  success_rate: number | null;
  avg_duration_days: number | null;
  running_worth: string;
  won_worth: string;
  by_status: PocStatusCount[];
  by_stage: PocStageProgress[];
  by_country: PocCountryBreakdown[];
}

// Mirrors backend ChannelManagerCompanyBreakdown / ChannelManagerDashboardResponse
// (schemas/dashboard.py) — the per-company rollup for a channel manager's book.
export interface ChannelManagerCompanyBreakdown {
  company_id: number;
  company_name: string;
  tier: string;
  partner_count: number;
  pending_opportunities: number;
  approved_opportunities: number;
  pending_doc_requests: number;
}

export interface ChannelManagerDashboard {
  total_companies: number;
  total_partners: number;
  total_pending_opportunities: number;
  total_approved_opportunities: number;
  total_pending_doc_requests: number;
  companies: ChannelManagerCompanyBreakdown[];
}

export interface DeploymentMonthPoint {
  month: string;
  started: number;
  completed: number;
}

export interface LicenseStatusCount {
  status: LicenseStatus;
  label: string;
  count: number;
  device_count: number;
  node_count: number;
}

export interface ExpiringLicenseItem {
  opportunity_id: number;
  customer_name: string;
  company_name: string | null;
  country: string | null;
  license_expires_at: string;
  days_until_expiry: number;
  device_count: number | null;
  node_count: number | null;
}

export interface DeploymentAnalytics {
  active_pocs: number;
  stage_funnel: PocStageProgress[];
  monthly_activity: DeploymentMonthPoint[];
  total_devices: number;
  total_nodes: number;
  active_licenses: number;
  licenses_by_status: LicenseStatusCount[];
  expiring_soon: ExpiringLicenseItem[];
}

// ==================== City funnel ====================

export interface CityFunnelCell {
  city: string;
  country: string | null;
  quarter: string;
  stage: string;
  stage_label: string;
  opportunity_count: number;
  total_worth: string;
  weighted_pipeline: string;
}

export interface CityFunnelResponse {
  cities: string[];
  quarters: string[];
  stages: string[];
  stage_labels: Record<string, string>;
  cells: CityFunnelCell[];
  total_worth: string;
  weighted_pipeline: string;
}

// ==================== Audit Logs ====================
export interface AuditLogItem {
  id: number;
  user_id: number;
  user_full_name: string;
  action: string;
  entity_type: string;
  entity_id: number;
  metadata_json: Record<string, unknown> | null;
  timestamp: string;
}

export interface AuditLogListResponse {
  items: AuditLogItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

// ==================== Bulk Import ====================
export interface BulkImportResult {
  processed: number;
  succeeded: number;
  failed: Array<{ row: number; error: string }>;
  // Only returned by the opportunities importer (bulk_import_opportunities.py)
  companies_touched?: number;
  admins_touched?: number;
}

// ==================== Onboarding ====================
export interface OnboardingChecklistItem {
  key: string;
  label: string;
  completed: boolean;
}
export interface OnboardingChecklist {
  has_completed_onboarding: boolean;
  items: OnboardingChecklistItem[];
}
