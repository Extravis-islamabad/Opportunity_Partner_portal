import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { Spin } from 'antd';
import { useAuth } from '@/contexts/AuthContext';

// The concrete access keys a route can require. 'superadmin' and 'poc_editor'
// are derived capabilities, not literal user.role values.
type AccessKey = 'admin' | 'partner' | 'sales_rep' | 'superadmin' | 'poc_editor';

interface ProtectedRouteProps {
  children: React.ReactNode;
  // Single required capability (kept for existing call sites).
  requiredRole?: AccessKey;
  // OR a set of capabilities — the user needs to match at least ONE. Use this
  // for "admin or partner, but not sales_rep" style gates.
  allow?: AccessKey[];
}

interface UserLike {
  role?: string;
  is_superadmin?: boolean;
}

/**
 * The capabilities a user effectively holds. A superadmin is an admin with the
 * is_superadmin flag, so they hold both 'admin' and 'superadmin'. Admins and
 * sales reps additionally hold 'poc_editor' (the two roles that drive POC /
 * deployment data), matching the backend's get_poc_editor dependency.
 */
function effectiveAccess(user: UserLike | null | undefined): Set<AccessKey> {
  const keys = new Set<AccessKey>();
  if (!user?.role) return keys;
  if (user.role === 'admin') {
    keys.add('admin');
    keys.add('poc_editor');
    if (user.is_superadmin) keys.add('superadmin');
  } else if (user.role === 'partner') {
    keys.add('partner');
  } else if (user.role === 'sales_rep') {
    keys.add('sales_rep');
    keys.add('poc_editor');
  }
  return keys;
}

const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ children, requiredRole, allow }) => {
  const { isAuthenticated, isLoading, user } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <Spin size="large" tip="Loading..." />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  const required: AccessKey[] = allow ?? (requiredRole ? [requiredRole] : []);
  if (required.length > 0) {
    const held = effectiveAccess(user as UserLike);
    const permitted = required.some((r) => held.has(r));
    if (!permitted) {
      // Not authorised for this route — send them somewhere they can see.
      return <Navigate to="/dashboard" replace />;
    }
  }

  return <>{children}</>;
};

export default ProtectedRoute;
