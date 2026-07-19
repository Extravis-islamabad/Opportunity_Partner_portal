import React from 'react';
import { useAuth } from '@/contexts/AuthContext';
import AdminDashboard from './AdminDashboard';
import PartnerDashboard from './PartnerDashboard';
import SalesRepDashboard from './SalesRepDashboard';

const DashboardPage: React.FC = () => {
  const { user } = useAuth();
  if (user?.role === 'admin') return <AdminDashboard />;
  // Sales reps get their own scoped view — PartnerDashboard calls
  // partner-only endpoints that a rep is denied.
  if (user?.role === 'sales_rep') return <SalesRepDashboard />;
  return <PartnerDashboard />;
};

export default DashboardPage;
