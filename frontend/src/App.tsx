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
import KnowledgeBasePage from '@/pages/knowledge-base/KnowledgeBasePage';
import LmsPage from '@/pages/lms/LmsPage';
import CourseDetailPage from '@/pages/lms/CourseDetailPage';
import DocRequestPage from '@/pages/documents/DocRequestPage';
import NotificationsPage from '@/pages/notifications/NotificationsPage';
import ProfilePage from '@/pages/profile/ProfilePage';
import DealsPage from '@/pages/deals/DealsPage';
import CommissionsListPage from '@/pages/commissions/CommissionsListPage';
import ScorecardPage from '@/pages/scorecard/ScorecardPage';
import LeaderboardPage from '@/pages/scorecard/LeaderboardPage';

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
        <BrowserRouter>
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

                {/* All authenticated users */}
                <Route path="/opportunities" element={<OpportunityListPage />} />
                <Route path="/opportunities/create" element={<ProtectedRoute requiredRole="partner"><OpportunityCreatePage /></ProtectedRoute>} />
                <Route path="/opportunities/:id" element={<OpportunityDetailPage />} />
                <Route path="/knowledge-base" element={<KnowledgeBasePage />} />
                <Route path="/lms" element={<LmsPage />} />
                <Route path="/lms/courses/:id" element={<CourseDetailPage />} />
                <Route path="/doc-requests" element={<DocRequestPage />} />
                <Route path="/deals" element={<DealsPage />} />
                <Route path="/commissions" element={<CommissionsListPage />} />
                <Route path="/scorecard" element={<ScorecardPage />} />
                <Route path="/leaderboard" element={<LeaderboardPage />} />
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
