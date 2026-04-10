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

export interface UserBasic {
  id: number;
  full_name: string;
  email: string;
  role: 'admin' | 'partner';
  status: string;
  company_id: number | null;
  company_name: string | null;
  is_superadmin: boolean;
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
  submitted_at: string | null;
  reviewed_at: string | null;
  documents: OppDocumentResponse[];
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
  submitted_at: string | null;
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

export interface CourseModule {
  id: string;
  title: string;
  type: string;
  content_url: string | null;
  description: string | null;
  order: number;
}

export interface EnrollmentResponse {
  id: number;
  user_id: number;
  user_name: string | null;
  course_id: number;
  course_title: string | null;
  status: string;
  progress_json: string | null;
  completed_at: string | null;
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
