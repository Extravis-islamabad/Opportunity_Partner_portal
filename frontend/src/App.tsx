import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '@/contexts/AuthContext';
import { ThemeProvider } from '@/contexts/ThemeContext';
import ProtectedRoute from '@/components/common/ProtectedRoute';
import AppLayout from '@/components/layout/AppLayout';

import LoginPage from '@/pages/auth/LoginPage';
import ForgotPasswordPage from '@/pages/auth/ForgotPasswordPage';
import ResetPasswordPage from '@/pages/auth/ResetPasswordPage';
import ActivateAccountPage from '@/pages/auth/ActivateAccountPage';
import DashboardPage from '@/pages/dashboard/DashboardPage';
import CompanyListPage from '@/pages/companies/CompanyListPage';
import CompanyCreatePage from '@/pages/companies/CompanyCreatePage';
import CompanyDetailPage from '@/pages/companies/CompanyDetailPage';
import CompanyEditPage from '@/pages/companies/CompanyEditPage';
import UserListPage from '@/pages/users/UserListPage';
import OpportunityListPage from '@/pages/opportunities/OpportunityListPage';
import OpportunityCreatePage from '@/pages/opportunities/OpportunityCreatePage';
import OpportunityDetailPage from '@/pages/opportunities/OpportunityDetailPage';
import DuplicateReviewPage from '@/pages/opportunities/DuplicateReviewPage';
import StaleReviewsPage from '@/pages/opportunities/StaleReviewsPage';
import KnowledgeBasePage from '@/pages/knowledge-base/KnowledgeBasePage';
import LmsPage from '@/pages/lms/LmsPage';
import CourseDetailPage from '@/pages/lms/CourseDetailPage';
import DocRequestPage from '@/pages/documents/DocRequestPage';
import NotificationsPage from '@/pages/notifications/NotificationsPage';
import ProfilePage from '@/pages/profile/ProfilePage';
import DealsPage from '@/pages/deals/DealsPage';
import ExclusivityPage from '@/pages/deals/ExclusivityPage';
import RenewalsPage from '@/pages/renewals/RenewalsPage';
import CommissionsListPage from '@/pages/commissions/CommissionsListPage';
import ScorecardPage from '@/pages/scorecard/ScorecardPage';
import LeaderboardPage from '@/pages/scorecard/LeaderboardPage';
import PocListPage from '@/pages/poc/PocListPage';
import DeploymentPage from '@/pages/deployment/DeploymentPage';
import ActivityLogPage from '@/pages/activities/ActivityLogPage';
import OpportunityEditPage from '@/pages/opportunities/OpportunityEditPage';
import AuditLogsPage from '@/pages/audit/AuditLogsPage';
import BulkImportPage from '@/pages/admin/BulkImportPage';
import EmailLogPage from '@/pages/admin/EmailLogPage';
import CurrencyRatesPage from '@/pages/admin/CurrencyRatesPage';
import LegalDocumentsPage from '@/pages/admin/LegalDocumentsPage';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 30000,
    },
  },
});

const App: React.FC = () => {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <AuthProvider>
            <Routes>
              {/* Public routes */}
              <Route path="/login" element={<LoginPage />} />
              <Route path="/forgot-password" element={<ForgotPasswordPage />} />
              <Route path="/reset-password" element={<ResetPasswordPage />} />
              <Route path="/activate" element={<ActivateAccountPage />} />

              {/* Protected routes */}
              <Route
                element={
                  <ProtectedRoute>
                    <AppLayout />
                  </ProtectedRoute>
                }
              >
                <Route path="/dashboard" element={<DashboardPage />} />

                {/* Admin only */}
                <Route path="/companies" element={<ProtectedRoute requiredRole="admin"><CompanyListPage /></ProtectedRoute>} />
                {/* Only superadmins can create new companies (assigning channel managers etc.) */}
                <Route path="/companies/create" element={<ProtectedRoute requiredRole="superadmin"><CompanyCreatePage /></ProtectedRoute>} />
                <Route path="/companies/:id/edit" element={<ProtectedRoute requiredRole="admin"><CompanyEditPage /></ProtectedRoute>} />
                <Route path="/companies/:id" element={<ProtectedRoute requiredRole="admin"><CompanyDetailPage /></ProtectedRoute>} />
                {/* User management is superadmin-only */}
                <Route path="/users" element={<ProtectedRoute requiredRole="superadmin"><UserListPage /></ProtectedRoute>} />
                {/* Audit log + bulk import are superadmin-only tools */}
                <Route path="/audit-logs" element={<ProtectedRoute requiredRole="superadmin"><AuditLogsPage /></ProtectedRoute>} />
                <Route path="/admin/bulk-import" element={<ProtectedRoute requiredRole="superadmin"><BulkImportPage /></ProtectedRoute>} />
                <Route path="/admin/email-log" element={<ProtectedRoute requiredRole="superadmin"><EmailLogPage /></ProtectedRoute>} />
                <Route path="/admin/currencies" element={<ProtectedRoute requiredRole="superadmin"><CurrencyRatesPage /></ProtectedRoute>} />
                <Route path="/admin/legal" element={<ProtectedRoute requiredRole="superadmin"><LegalDocumentsPage /></ProtectedRoute>} />

                {/* Pipeline — visible to all authenticated roles, each
                    scoped by the backend (partners own, sales reps assigned,
                    channel managers their companies). */}
                <Route path="/opportunities" element={<OpportunityListPage />} />
                <Route path="/opportunities/create" element={<ProtectedRoute allow={['partner', 'sales_rep']}><OpportunityCreatePage /></ProtectedRoute>} />
                {/* Static paths declared BEFORE :id so they don't get caught by the param route */}
                <Route path="/opportunities/duplicates" element={<ProtectedRoute requiredRole="admin"><DuplicateReviewPage /></ProtectedRoute>} />
                {/* Declared above /opportunities/:id so the static path wins. */}
                <Route path="/opportunities/stale-reviews" element={<ProtectedRoute requiredRole="admin"><StaleReviewsPage /></ProtectedRoute>} />
                <Route path="/opportunities/:id/edit" element={<ProtectedRoute allow={['partner', 'sales_rep']}><OpportunityEditPage /></ProtectedRoute>} />
                <Route path="/opportunities/:id" element={<OpportunityDetailPage />} />
                {/* POC visible to all (partners read-only); Deployment is
                    internal — admins and sales reps only. */}
                <Route path="/poc" element={<PocListPage />} />
                <Route path="/deployment" element={<ProtectedRoute requiredRole="poc_editor"><DeploymentPage /></ProtectedRoute>} />
                {/* Daily activity log — reps write their own, admins review. */}
                <Route path="/activities" element={<ProtectedRoute allow={['admin', 'sales_rep']}><ActivityLogPage /></ProtectedRoute>} />
                {/* Learning + KB open to all authenticated roles. */}
                <Route path="/knowledge-base" element={<KnowledgeBasePage />} />
                <Route path="/lms" element={<LmsPage />} />
                <Route path="/lms/courses/:id" element={<CourseDetailPage />} />
                {/* Partner/admin workflows — sales reps are denied by the
                    backend, so gate the routes to match. */}
                <Route path="/doc-requests" element={<ProtectedRoute allow={['admin', 'partner']}><DocRequestPage /></ProtectedRoute>} />
                {/* Partner-programme pages. 'channel_member' is admin OR a
                    partner whose company is a partner/distributor — a customer
                    company's users are excluded here and by the backend. */}
                <Route path="/deals" element={<ProtectedRoute requiredRole="channel_member"><DealsPage /></ProtectedRoute>} />
                <Route path="/deals/exclusivity" element={<ProtectedRoute requiredRole="channel_member"><ExclusivityPage /></ProtectedRoute>} />
                <Route path="/renewals" element={<ProtectedRoute requiredRole="channel_member"><RenewalsPage /></ProtectedRoute>} />
                <Route path="/commissions" element={<ProtectedRoute requiredRole="channel_member"><CommissionsListPage /></ProtectedRoute>} />
                <Route path="/scorecard" element={<ProtectedRoute requiredRole="own_scorecard"><ScorecardPage /></ProtectedRoute>} />
                <Route path="/leaderboard" element={<ProtectedRoute requiredRole="channel_member"><LeaderboardPage /></ProtectedRoute>} />
                {/* Personal — every authenticated user. */}
                <Route path="/notifications" element={<NotificationsPage />} />
                <Route path="/profile" element={<ProfilePage />} />
              </Route>

              {/* Default redirect */}
              <Route path="/" element={<Navigate to="/dashboard" replace />} />
              <Route path="*" element={<Navigate to="/dashboard" replace />} />
            </Routes>
          </AuthProvider>
        </BrowserRouter>
      </ThemeProvider>
    </QueryClientProvider>
  );
};

export default App;
