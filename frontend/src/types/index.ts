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

/**
 * What a company is to Extravis. Only 'partner' and 'distributor' take part
 * in the partner programme (deal registration, commissions, scorecard, tier);
 * a 'customer' is an end customer with a portal login and none of those.
 */
export type CompanyType = 'customer' | 'distributor' | 'partner';

export interface UserBasic {
  id: number;
  full_name: string;
  email: string;
  role: UserRole;
  status: string;
  company_id: number | null;
  company_name: string | null;
  /** Null for admins and sales reps, who belong to no company. */
  company_type: CompanyType | null;
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
  is_channel_manager: boolean;
  managed_company_count: number;
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
  company_type: CompanyType;
  /** Null for a customer company — partner tier does not apply. */
  tier: string | null;
  channel_manager_id: number;
  channel_manager_name: string | null;
  /**
   * Set only on a partner company that resells through a distributor. Null
   * means the company reports directly to Extravis.
   */
  parent_distributor_id: number | null;
  parent_distributor_name: string | null;
  partner_count: number;
  opportunity_count: number;
  created_at: string;
  updated_at: string;
}

export interface CompanyDetailResponse extends CompanyResponse {
  partners: PartnerAccountBrief[];
  /** The companies underneath this one. Only ever non-empty for a distributor. */
  resellers: ResellerBrief[];
}

export interface ResellerBrief {
  id: number;
  name: string;
  country: string;
  status: string;
  tier: string | null;
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
  /** Required — classification governs what the company's users can reach. */
  company_type: CompanyType;
  /** Only valid on a partner company, and only pointing at a distributor. */
  parent_distributor_id?: number | null;
}

export interface CompanyUpdateRequest {
  name?: string;
  country?: string;
  region?: string;
  city?: string;
  industry?: string;
  contact_email?: string;
  channel_manager_id?: number;
  /** Superadmin-only; the API rejects it from anyone else. */
  company_type?: CompanyType;
  /**
   * Superadmin-only too. Send null explicitly to unlink a reseller; omit the
   * field entirely to leave the current link alone.
   */
  parent_distributor_id?: number | null;
}

// ==================== Opportunity ====================
export type OpportunityStatus =
  | 'draft'
  | 'pending_review'
  | 'under_review'
  | 'approved'
  | 'rejected'
  | 'removed'
  | 'multi_partner_flagged'
  // Terminal outcomes, recorded after approval. Note `won` still counts as an
  // accepted deal everywhere a total is taken — see ACCEPTED_STATUSES.
  | 'won'
  | 'lost';

export type LossReason =
  | 'price'
  | 'competitor'
  | 'no_budget'
  | 'timing'
  | 'technical_fit'
  | 'no_decision';

export interface LossReasonOption {
  value: LossReason;
  label: string;
}

/** The product catalogue. Served by /opportunities/products so the form does
 *  not hardcode it; this type is for the values that come back. */
export type ProductName = 'MonetX' | 'SupportX' | 'GreenX' | 'PatchX' | 'AgentX';

export interface ProductOption {
  value: string;
  label: string;
}

/** One product on a deal, with the sizing the quote is built from. */
export interface ProductLine {
  product: string;
  device_count: number | null;
  node_count: number | null;
  value: number | string | null;
  notes?: string | null;
}
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
  loss_reason: LossReason | null;
  loss_reason_label: string | null;
  loss_notes: string | null;
  closed_outcome_at: string | null;
  /**
   * Set when this opportunity renews an expiring licence rather than being new
   * business. Null on nearly all of them.
   */
  renewal_of_license_id: number | null;
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
  /** Every product on the deal, with its sizing and value. */
  products: ProductLine[];
  /** Derived one-word summary — the biggest line. Never stored. */
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
  products: string[];
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
  /**
   * The products on the deal, with sizing. Omitting the field on an update
   * leaves the existing lines alone; sending an empty array clears them.
   */
  products?: ProductLine[];
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
  opps_progress_pct: number;
  /**
   * Company-wide LMS completion rate, as a percentage. Replaces a per-user
   * course *count*: a tier belongs to the company, so one person finishing
   * five courses no longer reads as the company being ready for platinum.
   */
  lms_rate_required: number;
  lms_rate_current: number;
  lms_progress_pct: number;
  /** The weaker of the two — what actually stands between here and promotion. */
  overall_progress_pct: number;
  /**
   * Set only while the company is below the requirements for the tier it
   * already holds: the date the grace period runs out and the tier drops.
   * Null is the normal case.
   */
  at_risk_until: string | null;
  at_risk_shortfall: string | null;
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
  /** Null for a customer company. */
  company_tier: string | null;
  lms_courses_enrolled: number;
  lms_courses_completed: number;
  pending_doc_requests: number;
  tier_progress: TierProgress | null;
}

export interface UpcomingRenewal {
  license_id: number;
  opportunity_id: number;
  customer_name: string;
  company_id: number;
  company_name: string | null;
  product: string | null;
  po_value: string | null;
  device_count: number | null;
  node_count: number | null;
  expires_at: string;
  days_left: number;
  /** Set once somebody has raised the renewal, so the action is not offered twice. */
  renewal_opportunity_id: number | null;
  notified_at: string | null;
}

export type TierDirection = 'up' | 'down' | 'unchanged' | 'unknown';

export interface TierHistoryEntry {
  id: number;
  previous_tier: string | null;
  new_tier: string;
  reason: string | null;
  changed_by_name: string | null;
  changed_at: string;
  direction: TierDirection;
}

export interface CompanyPerformance {
  company_id: number;
  company_name: string;
  company_type: CompanyType;
  tier: string | null;
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
  // Days until exclusivity lapses; null once the window is gone or was never
  // granted, so a number here always means live protection.
  days_left: number | null;
  expired_at: string | null;
  extension_pending: boolean;
  rejection_reason: string | null;
}

export interface ExpiringExclusivity {
  deal_id: number;
  customer_name: string;
  company_id: number;
  company_name: string | null;
  estimated_value: string;
  exclusivity_end: string;
  days_left: number;
  extension_pending: boolean;
}

export type ExtensionStatus = 'pending' | 'approved' | 'refused';

export interface ExtensionRequest {
  id: number;
  deal_id: number;
  customer_name: string | null;
  company_name: string | null;
  requested_by: number;
  requested_by_name: string | null;
  requested_days: number;
  granted_days: number | null;
  reason: string | null;
  status: ExtensionStatus;
  decided_by_name: string | null;
  decided_at: string | null;
  decision_note: string | null;
  exclusivity_end: string | null;
  created_at: string;
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
  company_type: CompanyType;
  /** Null for a customer company — it can rank on pipeline but has no tier. */
  tier: string | null;
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
  // Empty until deals start being closed as lost.
  loss_reasons: LossReasonBreakdown[];
  recent_activity: RecentActivityItem[];
}

export interface LossReasonBreakdown {
  reason: LossReason;
  label: string;
  count: number;
  total_worth: string;
}

// ==================== Review ageing ====================
export interface StaleReview {
  id: number;
  name: string;
  customer_name: string;
  company_name: string | null;
  reviewer_id: number | null;
  reviewer_name: string | null;
  claimed_at: string;
  days_claimed: number;
  escalated: boolean;
}

// ==================== Email delivery ====================
export type EmailStatus = 'sent' | 'failed' | 'skipped';

export interface EmailDeliveryItem {
  id: number;
  status: EmailStatus;
  recipients: string;
  subject: string;
  template: string | null;
  error: string | null;
  created_at: string;
}

export interface EmailLogResponse {
  items: EmailDeliveryItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  totals_by_status: Record<string, number>;
  email_configured: boolean;
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

  /**
   * Who on the POC team is responsible for this stage. All null when nobody
   * has been named — and all null for a partner viewer, who sees the roster
   * but not the internal division of labour.
   */
  owner_user_id: number | null;
  owner_name: string | null;
  owner_role: PocTeamRoleKey | null;
  owner_role_label: string | null;
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

  /**
   * Everyone from Extravis currently working this POC, over and above the
   * opportunity's single named sales rep. Empty until someone is staffed on
   * it, which is the normal state for a new POC.
   */
  team: PocTeamMember[];

  created_at: string;
  updated_at: string;
}

/**
 * What someone does on a POC. Distinct from their portal role: the same
 * engineer can be the deployment engineer on one POC and the solution
 * architect on another.
 */
export type PocTeamRoleKey =
  | 'presales_lead'
  | 'solution_architect'
  | 'deployment_engineer'
  | 'project_manager'
  | 'qa'
  | 'support';

export interface PocTeamMember {
  id: number;
  poc_id: number;
  user_id: number;
  user_name: string | null;
  user_email: string | null;
  /** Their role in the portal — 'admin' or 'sales_rep'. */
  user_role: string | null;
  job_title: string | null;
  role: PocTeamRoleKey;
  /** Server-rendered label; "QA", not "Qa". Never title-case `role` locally. */
  role_label: string;
  assigned_by: number | null;
  assigned_by_name: string | null;
  /**
   * Null for a partner viewer, who gets a redacted roster — name and POC role
   * only. Never render this without a null check.
   */
  assigned_at: string | null;
  /** Only set on rows from a history read; the current roster is all nulls. */
  removed_at: string | null;
}

export interface PocTeamRoleOption {
  value: PocTeamRoleKey;
  label: string;
}

export interface PocAssignableUser {
  id: number;
  full_name: string;
  email: string;
  role: string;
  job_title: string | null;
}

/** One person's total on a POC. Zero counts are meaningful: assigned, nothing logged. */
export interface PocActivityPerson {
  user_id: number;
  user_name: string | null;
  poc_role: PocTeamRoleKey | null;
  poc_role_label: string | null;
  on_team: boolean;
  activity_count: number;
  total_duration_minutes: number;
}

export interface PocActivityEntry {
  id: number;
  user_id: number;
  user_name: string | null;
  activity_date: string;
  activity_type: string;
  activity_type_label: string;
  customer_name: string | null;
  opportunity_id: number | null;
  opportunity_name: string | null;
  poc_id: number | null;
  duration_minutes: number | null;
  notes: string | null;
  /** 'poc' when logged as POC work, 'opportunity' when logged against the deal. */
  linked_via: 'poc' | 'opportunity';
  created_at: string;
  updated_at: string;
}

export interface PocActivityFeed {
  poc_id: number;
  items: PocActivityEntry[];
  by_person: PocActivityPerson[];
  total_activities: number;
  total_duration_minutes: number;
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
  company_type: CompanyType;
  tier: string | null;
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

// ==================== Sales activity log ====================
export type ActivityType =
  | 'call'
  | 'meeting'
  | 'demo'
  | 'email'
  | 'site_visit'
  | 'follow_up'
  | 'training'
  | 'other';

export interface ActivityCreateRequest {
  activity_date: string; // YYYY-MM-DD
  activity_type: ActivityType;
  customer_name?: string | null;
  opportunity_id?: number | null;
  /** The POC this was work on. Only accepted for a POC the logger can work on. */
  poc_id?: number | null;
  duration_minutes?: number | null;
  notes?: string | null;
}

export interface ActivityResponse {
  id: number;
  user_id: number;
  user_name: string | null;
  activity_date: string;
  activity_type: ActivityType;
  activity_type_label: string;
  customer_name: string | null;
  opportunity_id: number | null;
  opportunity_name: string | null;
  poc_id: number | null;
  duration_minutes: number | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface ActivityTypeTotal {
  activity_type: ActivityType;
  label: string;
  count: number;
}

export interface ActivityDay {
  date: string;
  weekday: number; // 0 = Monday … 6 = Sunday
  items: ActivityResponse[];
}

export interface ActivityMonthResponse {
  user_id: number;
  user_name: string | null;
  month: string; // YYYY-MM
  days: ActivityDay[];
  totals_by_type: ActivityTypeTotal[];
  total_activities: number;
  total_duration_minutes: number;
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
