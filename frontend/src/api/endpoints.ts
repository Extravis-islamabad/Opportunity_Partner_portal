import apiClient from './client';
import type {
  LoginRequest,
  LoginResponse,
  RefreshResponse,
  UserBasic,
  UserResponse,
  UserCreateRequest,
  UserUpdateRequest,
  CompanyResponse,
  CompanyDetailResponse,
  CompanyCreateRequest,
  CompanyUpdateRequest,
  OpportunityResponse,
  OpportunityListItem,
  OpportunityCreateRequest,
  KBDocumentResponse,
  KBCategoryResponse,
  CourseResponse,
  EnrollmentResponse,
  DocRequestResponse,
  NotificationResponse,
  DashboardStats,
  PartnerDashboard,
  CompanyPerformance,
  DealRegistrationResponse,
  OpportunityStatusBreakdown,
  MonthlyOpportunityData,
  PaginatedResponse,
  MessageResponse,
  CommissionRead,
  ScorecardRead,
  LeaderboardResponse,
  StatementPeriodSummary,
} from '@/types';

// ==================== Auth ====================
export const authApi = {
  login: (data: LoginRequest) =>
    apiClient.post<LoginResponse>('/auth/login', data),
  refresh: () =>
    apiClient.post<RefreshResponse>('/auth/refresh'),
  logout: () =>
    apiClient.post<MessageResponse>('/auth/logout'),
  forgotPassword: (email: string) =>
    apiClient.post<MessageResponse>('/auth/forgot-password', { email }),
  resetPassword: (token: string, new_password: string) =>
    apiClient.post<MessageResponse>('/auth/reset-password', { token, new_password }),
  activate: (token: string, password: string) =>
    apiClient.post<MessageResponse>('/auth/activate', { token, password }),
  changePassword: (current_password: string, new_password: string) =>
    apiClient.post<MessageResponse>('/auth/change-password', { current_password, new_password }),
  getMe: () =>
    apiClient.get<UserBasic>('/auth/me'),
};

// ==================== Users ====================
export const usersApi = {
  create: (data: UserCreateRequest) =>
    apiClient.post<UserResponse>('/users', data),
  list: (params: Record<string, string | number | undefined>) =>
    apiClient.get<PaginatedResponse<UserResponse>>('/users', { params }),
  getAdmins: () =>
    apiClient.get<Array<{ id: number; full_name: string; email: string }>>('/users/admins'),
  get: (id: number) =>
    apiClient.get<UserResponse>(`/users/${id}`),
  update: (id: number, data: UserUpdateRequest) =>
    apiClient.put<UserResponse>(`/users/${id}`, data),
  updateProfile: (data: UserUpdateRequest) =>
    apiClient.put<UserResponse>('/users/me/profile', data),
  deactivate: (id: number) =>
    apiClient.post<MessageResponse>(`/users/${id}/deactivate`),
  reactivate: (id: number) =>
    apiClient.post<MessageResponse>(`/users/${id}/reactivate`),
};

// ==================== Companies ====================
export const companiesApi = {
  create: (data: CompanyCreateRequest) =>
    apiClient.post<CompanyResponse>('/companies', data),
  list: (params: Record<string, string | number | undefined>) =>
    apiClient.get<PaginatedResponse<CompanyResponse>>('/companies', { params }),
  get: (id: number) =>
    apiClient.get<CompanyDetailResponse>(`/companies/${id}`),
  update: (id: number, data: CompanyUpdateRequest) =>
    apiClient.put<CompanyResponse>(`/companies/${id}`, data),
  deactivate: (id: number) =>
    apiClient.delete<MessageResponse>(`/companies/${id}`),
};

// ==================== Opportunities ====================
export const opportunitiesApi = {
  create: (data: OpportunityCreateRequest) =>
    apiClient.post<OpportunityResponse>('/opportunities', data),
  list: (params: Record<string, string | number | undefined>) =>
    apiClient.get<PaginatedResponse<OpportunityListItem>>('/opportunities', { params }),
  get: (id: number) =>
    apiClient.get<OpportunityResponse>(`/opportunities/${id}`),
  update: (id: number, data: Partial<OpportunityCreateRequest>) =>
    apiClient.put<OpportunityResponse>(`/opportunities/${id}`, data),
  submit: (id: number) =>
    apiClient.post<OpportunityResponse>(`/opportunities/${id}/submit`),
  approve: (id: number, preferred_partner: boolean) =>
    apiClient.post<OpportunityResponse>(`/opportunities/${id}/approve`, { preferred_partner }),
  reject: (id: number, rejection_reason: string) =>
    apiClient.post<OpportunityResponse>(`/opportunities/${id}/reject`, { rejection_reason }),
  markUnderReview: (id: number) =>
    apiClient.post<OpportunityResponse>(`/opportunities/${id}/review`),
  remove: (id: number) =>
    apiClient.delete<MessageResponse>(`/opportunities/${id}`),
  addNote: (id: number, internal_notes: string) =>
    apiClient.post<OpportunityResponse>(`/opportunities/${id}/notes`, { internal_notes }),
  uploadDocument: (id: number, file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return apiClient.post(`/opportunities/${id}/documents`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
};

// ==================== Knowledge Base ====================
export const knowledgeBaseApi = {
  uploadDocument: (data: FormData) =>
    apiClient.post<KBDocumentResponse>('/knowledge-base/documents', data, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
  list: (params: Record<string, string | number | undefined>) =>
    apiClient.get<PaginatedResponse<KBDocumentResponse>>('/knowledge-base/documents', { params }),
  getCategories: () =>
    apiClient.get<KBCategoryResponse[]>('/knowledge-base/categories'),
  get: (id: number) =>
    apiClient.get<KBDocumentResponse>(`/knowledge-base/documents/${id}`),
  update: (id: number, data: FormData) =>
    apiClient.put<KBDocumentResponse>(`/knowledge-base/documents/${id}`, data, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }),
  delete: (id: number) =>
    apiClient.delete<MessageResponse>(`/knowledge-base/documents/${id}`),
  download: (id: number) =>
    apiClient.post<{ file_url: string; file_name: string }>(`/knowledge-base/documents/${id}/download`),
};

// ==================== LMS ====================
export const lmsApi = {
  createCourse: (data: Record<string, unknown>) =>
    apiClient.post<CourseResponse>('/lms/courses', data),
  listCourses: (params: Record<string, string | number | undefined>) =>
    apiClient.get<PaginatedResponse<CourseResponse>>('/lms/courses', { params }),
  getCourse: (id: number) =>
    apiClient.get<CourseResponse>(`/lms/courses/${id}`),
  updateCourse: (id: number, data: Record<string, unknown>) =>
    apiClient.put<CourseResponse>(`/lms/courses/${id}`, data),
  deleteCourse: (id: number) =>
    apiClient.delete<MessageResponse>(`/lms/courses/${id}`),
  enroll: (courseId: number) =>
    apiClient.post<EnrollmentResponse>(`/lms/courses/${courseId}/enroll`),
  getMyEnrollments: () =>
    apiClient.get<EnrollmentResponse[]>('/lms/enrollments/me'),
  updateEnrollment: (id: number, data: Record<string, unknown>) =>
    apiClient.put<EnrollmentResponse>(`/lms/enrollments/${id}`, data),
  requestCertificate: (enrollmentId: number) =>
    apiClient.post<EnrollmentResponse>(`/lms/enrollments/${enrollmentId}/request-certificate`),
  listCertificateRequests: (params: Record<string, string | number | undefined>) =>
    apiClient.get<PaginatedResponse<EnrollmentResponse>>('/lms/certificate-requests', { params }),
  issueCertificate: (enrollmentId: number, file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return apiClient.post<EnrollmentResponse>(`/lms/enrollments/${enrollmentId}/issue-certificate`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
};

// ==================== Document Requests ====================
export const docRequestsApi = {
  create: (data: { description: string; reason?: string; urgency: string }) =>
    apiClient.post<DocRequestResponse>('/doc-requests', data),
  list: (params: Record<string, string | number | undefined>) =>
    apiClient.get<PaginatedResponse<DocRequestResponse>>('/doc-requests', { params }),
  get: (id: number) =>
    apiClient.get<DocRequestResponse>(`/doc-requests/${id}`),
  fulfill: (id: number, file: File, addToKb: boolean, kbTitle?: string, kbCategory?: string) => {
    const formData = new FormData();
    formData.append('file', file);
    const params: Record<string, string> = { add_to_kb: String(addToKb) };
    if (kbTitle) params['kb_title'] = kbTitle;
    if (kbCategory) params['kb_category'] = kbCategory;
    return apiClient.post<DocRequestResponse>(`/doc-requests/${id}/fulfill`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      params,
    });
  },
  decline: (id: number, decline_reason: string) =>
    apiClient.post<DocRequestResponse>(`/doc-requests/${id}/decline`, { decline_reason }),
};

// ==================== Notifications ====================
export const notificationsApi = {
  list: (params: Record<string, string | number | boolean | undefined>) =>
    apiClient.get<PaginatedResponse<NotificationResponse>>('/notifications', { params }),
  getCount: () =>
    apiClient.get<{ unread_count: number; total_count: number }>('/notifications/count'),
  markRead: (notification_ids: number[]) =>
    apiClient.post<MessageResponse>('/notifications/mark-read', { notification_ids }),
  markAllRead: () =>
    apiClient.post<MessageResponse>('/notifications/mark-all-read'),
};

// ==================== Exports ====================
type ExportParams = Record<string, string | number | undefined>;

const blobGet = (url: string, params?: ExportParams) =>
  apiClient.get<Blob>(url, { params, responseType: 'blob' });

export const exportsApi = {
  opportunitiesPdf: (params?: ExportParams) => blobGet('/exports/opportunities.pdf', params),
  opportunitiesXlsx: (params?: ExportParams) => blobGet('/exports/opportunities.xlsx', params),
  dealsPdf: (params?: ExportParams) => blobGet('/exports/deals.pdf', params),
  dealsXlsx: (params?: ExportParams) => blobGet('/exports/deals.xlsx', params),
  companiesPdf: (params?: ExportParams) => blobGet('/exports/companies.pdf', params),
  companiesXlsx: (params?: ExportParams) => blobGet('/exports/companies.xlsx', params),
};

// ==================== Commissions & Scorecard ====================
export const commissionsApi = {
  list: (params: Record<string, string | number | undefined>) =>
    apiClient.get<PaginatedResponse<CommissionRead>>('/commissions', { params }),
  get: (id: number) =>
    apiClient.get<CommissionRead>(`/commissions/${id}`),
  updateStatus: (id: number, status: string, notes?: string) =>
    apiClient.patch<CommissionRead>(`/commissions/${id}/status`, { status, notes }),
  listStatements: (params?: { company_id?: number }) =>
    apiClient.get<StatementPeriodSummary[]>('/commissions/statements/list', { params }),
  statementPdf: (companyId: number, period: string) =>
    apiClient.get<Blob>(`/commissions/statements/${companyId}/${period}.pdf`, {
      responseType: 'blob',
    }),
};

export const scorecardApi = {
  me: () => apiClient.get<ScorecardRead>('/scorecard/me'),
  company: (companyId: number) =>
    apiClient.get<ScorecardRead>(`/scorecard/${companyId}`),
  leaderboard: (params?: { period?: string; limit?: number }) =>
    apiClient.get<LeaderboardResponse>('/scorecard/leaderboard/top', { params }),
};

// ==================== AI ====================
export interface AIConfigResponse {
  enabled: boolean;
  model_default: string;
  model_fast: string;
}

export interface KbCitation {
  id: number;
  title: string;
  category: string;
}

export interface KbAskResponse {
  answer: string;
  citations: KbCitation[];
}

export interface OpportunitySummaryResponse {
  opportunity_id: number;
  summary: string;
  cached: boolean;
}

export interface RescoreResponse {
  opportunity_id: number;
  score: number | null;
  reasoning: string | null;
}

export const aiApi = {
  config: () => apiClient.get<AIConfigResponse>('/ai/config'),
  kbAsk: (question: string) =>
    apiClient.post<KbAskResponse>('/ai/kb-ask', { question }),
  summarizeOpportunity: (id: number) =>
    apiClient.post<OpportunitySummaryResponse>(`/ai/opportunities/${id}/summarize`),
  rescoreOpportunity: (id: number) =>
    apiClient.post<RescoreResponse>(`/ai/opportunities/${id}/rescore`),
};

// ==================== Dashboard ====================
export const dashboardApi = {
  getAdminStats: () =>
    apiClient.get<DashboardStats>('/dashboard/admin/stats'),
  getOpportunityBreakdown: () =>
    apiClient.get<OpportunityStatusBreakdown[]>('/dashboard/admin/opportunity-breakdown'),
  getMonthlyData: (months?: number) =>
    apiClient.get<MonthlyOpportunityData[]>('/dashboard/admin/monthly-data', { params: { months } }),
  getCompanyPerformance: (companyId: number) =>
    apiClient.get<CompanyPerformance>(`/dashboard/company/${companyId}/performance`),
  getPartnerStats: () =>
    apiClient.get<PartnerDashboard>('/dashboard/partner/stats'),
  createDeal: (data: Record<string, unknown>) =>
    apiClient.post<DealRegistrationResponse>('/dashboard/deals', data),
  listDeals: (params: Record<string, string | number | undefined>) =>
    apiClient.get<PaginatedResponse<DealRegistrationResponse>>('/dashboard/deals', { params }),
  approveDeal: (id: number, exclusivity_days: number) =>
    apiClient.post<DealRegistrationResponse>(`/dashboard/deals/${id}/approve`, { exclusivity_days }),
  rejectDeal: (id: number, rejection_reason: string) =>
    apiClient.post<DealRegistrationResponse>(`/dashboard/deals/${id}/reject`, { rejection_reason }),
};
