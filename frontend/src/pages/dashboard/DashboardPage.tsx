import React from 'react';
import { Result } from 'antd';
import { useAuth } from '@/contexts/AuthContext';
import AdminDashboard from './AdminDashboard';
import PartnerDashboard from './PartnerDashboard';
import SalesRepDashboard from './SalesRepDashboard';

const DashboardPage: React.FC = () => {
  const { user } = useAuth();
  // Exhaustive on role — an unknown role must NOT silently fall through to
  // PartnerDashboard (whose partner-only API calls would all 403).
  switch (user?.role) {
    case 'admin':
      return <AdminDashboard />;
    // Sales reps get their own scoped view — PartnerDashboard calls
    // partner-only endpoints that a rep is denied.
    case 'sales_rep':
      return <SalesRepDashboard />;
    case 'partner':
      return <PartnerDashboard />;
    default:
      return (
        <Result
          status="warning"
          title="No dashboard for this account type"
          subTitle="Your account role is not recognised by this version of the portal. Please contact an administrator."
        />
      );
  }
};

export default DashboardPage;
