import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { Spin } from 'antd';
import { useAuth } from '@/contexts/AuthContext';

// The concrete access keys a route can require. Everything past the three
// roles is a derived capability, not a literal user.role value.
type AccessKey =
  | 'admin'
  | 'partner'
  | 'sales_rep'
  | 'superadmin'
  | 'poc_editor'
  // Partner-programme member: may reach deal registration, commissions and
  // the leaderboard. Admins qualify (they run the programme); a partner
  // qualifies only when their company is a partner or distributor.
  | 'channel_member'
  // A partner user with their own company scorecard — channel_member minus
  // admins, who have no company of their own to score.
  | 'own_scorecard';

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
  company_type?: string | null;
}

/**
 * The capabilities a user effectively holds. A superadmin is an admin with the
 * is_superadmin flag, so they hold both 'admin' and 'superadmin'. Admins and
 * sales reps additionally hold 'poc_editor' (the two roles that drive POC /
 * deployment data), matching the backend's get_poc_editor dependency.
 *
 * A partner's company type decides whether they hold the partner-programme
 * capabilities: a customer company's users get neither 'channel_member' nor
 * 'own_scorecard', which is what keeps deal registration, commissions,
 * scorecard and leaderboard out of their sidebar, routes and palette. This
 * mirrors deps.deny_customer_company on the server — the server is the
 * enforcement, this is the UI telling the same truth.
 */
export function effectiveAccess(user: UserLike | null | undefined): Set<AccessKey> {
  const keys = new Set<AccessKey>();
  if (!user?.role) return keys;
  if (user.role === 'admin') {
    keys.add('admin');
    keys.add('poc_editor');
    // Admins run the partner programme, so they always see its pages, but
    // they have no company of their own and therefore no scorecard.
    keys.add('channel_member');
    if (user.is_superadmin) keys.add('superadmin');
  } else if (user.role === 'partner') {
    keys.add('partner');
    if (user.company_type === 'partner' || user.company_type === 'distributor') {
      keys.add('channel_member');
      keys.add('own_scorecard');
    }
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
