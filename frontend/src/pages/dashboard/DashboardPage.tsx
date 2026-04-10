import React from 'react';
import { useAuth } from '@/contexts/AuthContext';
import AdminDashboard from './AdminDashboard';
import PartnerDashboard from './PartnerDashboard';

const DashboardPage: React.FC = () => {
  const { user } = useAuth();
  return user?.role === 'admin' ? <AdminDashboard /> : <PartnerDashboard />;
};

export default DashboardPage;
