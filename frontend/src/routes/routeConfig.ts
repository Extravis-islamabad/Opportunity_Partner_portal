/**
 * Single source of truth for route metadata.
 *
 * Consumed by:
 *  - RouteBreadcrumb (to render crumb labels for the current path)
 *  - CommandPalette (to populate global search targets)
 *
 * Add a route here the same time you add one to App.tsx.
 */

export type UserRole = 'admin' | 'partner' | 'sales_rep';
export type CompanyType = 'customer' | 'distributor' | 'partner';

/**
 * Access keys a route can require. Mirrors ProtectedRoute: everything past the
 * three roles is derived, not a role of its own — a channel-manager admin has
 * 'admin' but NOT 'superadmin', and a partner at a customer company has
 * 'partner' but NOT 'channel_member'.
 */
export type RouteCapability =
  | UserRole
  | 'superadmin'
  | 'channel_member'
  | 'own_scorecard';

export interface RouteDescriptor {
  path: string;
  label: string;
  section?: string;
  icon?: string; // ant design icon name, for palette only
  roles?: RouteCapability[]; // if unset → available to all authenticated users
  keywords?: string[]; // extra search terms for the palette
}

/**
 * The capability set for a user: their role, plus 'superadmin' when flagged,
 * plus the partner-programme capabilities when they apply. Use this (not raw
 * role equality) when filtering routes, so superadmin-only pages never surface
 * for channel-manager admins and partner-programme pages never surface for a
 * customer company's users.
 *
 * Kept in step with ProtectedRoute.effectiveAccess — that one gates the route,
 * this one gates what the command palette offers.
 */
export function capabilitiesFor(
  role: UserRole,
  isSuperadmin: boolean,
  companyType?: CompanyType | null,
): RouteCapability[] {
  const caps: RouteCapability[] = [role];
  if (isSuperadmin) caps.push('superadmin');
  if (role === 'admin') {
    caps.push('channel_member');
  } else if (role === 'partner' && (companyType === 'partner' || companyType === 'distributor')) {
    caps.push('channel_member', 'own_scorecard');
  }
  return caps;
}

export const ROUTES: RouteDescriptor[] = [
  {
    path: '/dashboard',
    label: 'Dashboard',
    section: 'Overview',
    keywords: ['home', 'kpis', 'stats'],
  },
  {
    path: '/opportunities',
    label: 'Opportunities',
    section: 'Pipeline',
    keywords: ['pipeline', 'deals', 'leads'],
  },
  {
    path: '/poc',
    label: 'POC Tracking',
    section: 'Pipeline',
    keywords: ['poc', 'proof of concept', 'vm', 'provisioning', 'onboarding', 'fine tuning', 'trial'],
  },
  {
    path: '/deployment',
    label: 'Deployment',
    section: 'Pipeline',
    roles: ['admin', 'sales_rep'],
    keywords: ['deployment', 'devices', 'nodes', 'licence', 'license', 'rollout', 'activation', 'expiry'],
  },
  {
    path: '/activities',
    label: 'Activity Log',
    section: 'Pipeline',
    roles: ['admin', 'sales_rep'],
    keywords: ['activity', 'daily', 'calls', 'meetings', 'demos', 'log', 'calendar'],
  },
  {
    path: '/audit-logs',
    label: 'Audit Logs',
    section: 'Administration',
    roles: ['superadmin'],
    keywords: ['audit', 'history', 'activity', 'log', 'trail'],
  },
  {
    path: '/admin/currencies',
    label: 'Currency Rates',
    section: 'Administration',
    roles: ['superadmin'],
    keywords: ['currency', 'rate', 'exchange', 'usd', 'sar', 'aed', 'pkr', 'fx'],
  },
  {
    path: '/admin/email-log',
    label: 'Email Log',
    section: 'Administration',
    roles: ['superadmin'],
    keywords: ['email', 'smtp', 'mail', 'delivery', 'failed', 'skipped', 'notification'],
  },
  {
    path: '/admin/bulk-import',
    label: 'Bulk Import',
    section: 'Administration',
    roles: ['superadmin'],
    keywords: ['import', 'bulk', 'upload', 'xlsx', 'excel', 'template'],
  },
  {
    path: '/opportunities/create',
    label: 'New Opportunity',
    section: 'Pipeline',
    roles: ['partner'],
    keywords: ['create', 'add', 'new'],
  },
  {
    path: '/opportunities/duplicates',
    label: 'Duplicate Review',
    section: 'Pipeline',
    roles: ['admin'],
    keywords: ['duplicate', 'dedupe', 'merge', 'review', 'conflict'],
  },
  {
    path: '/deals/exclusivity',
    label: 'Exclusivity',
    section: 'Pipeline',
    roles: ['channel_member'],
    keywords: ['exclusivity', 'expiry', 'expiring', 'extension', 'protection', 'deal'],
  },
  {
    path: '/renewals',
    label: 'Renewals',
    section: 'Pipeline',
    roles: ['channel_member'],
    keywords: ['renewal', 'licence', 'license', 'expiry', 'expiring', 'renew'],
  },
  {
    path: '/opportunities/stale-reviews',
    label: 'Stuck Reviews',
    section: 'Pipeline',
    roles: ['admin'],
    keywords: ['stuck', 'stale', 'sla', 'review', 'claimed', 'release', 'overdue'],
  },
  {
    path: '/companies/create',
    label: 'New Company',
    section: 'Administration',
    roles: ['superadmin'],
    keywords: ['create', 'add', 'company', 'partner company'],
  },
  {
    // Deal registration is a partner-programme workflow. Sales reps and
    // customer companies are both denied by the backend, so keep it out of
    // their command palette too.
    path: '/deals',
    label: 'Deal Registration',
    section: 'Pipeline',
    roles: ['channel_member'],
    keywords: ['deal', 'exclusivity', 'register'],
  },
  {
    path: '/commissions',
    label: 'Commissions',
    section: 'Earnings',
    roles: ['channel_member'],
    keywords: ['payout', 'money', 'earnings'],
  },
  {
    path: '/scorecard',
    label: 'My Scorecard',
    section: 'Earnings',
    roles: ['own_scorecard'],
    keywords: ['tier', 'progress', 'badges'],
  },
  {
    path: '/leaderboard',
    label: 'Leaderboard',
    section: 'Earnings',
    roles: ['channel_member'],
    keywords: ['rankings', 'top partners', 'trophy'],
  },
  {
    path: '/knowledge-base',
    label: 'Knowledge Base',
    section: 'Resources',
    keywords: ['kb', 'docs', 'documents'],
  },
  {
    path: '/lms',
    label: 'Training',
    section: 'Resources',
    keywords: ['lms', 'courses', 'learning'],
  },
  {
    path: '/doc-requests',
    label: 'Document Requests',
    section: 'Resources',
    roles: ['admin', 'partner'],
    keywords: ['request', 'docs'],
  },
  {
    path: '/companies',
    label: 'Companies',
    section: 'Administration',
    roles: ['admin'],
    keywords: ['partners', 'tenants'],
  },
  {
    path: '/users',
    label: 'Users',
    section: 'Administration',
    roles: ['superadmin'],
    keywords: ['team', 'accounts'],
  },
  {
    path: '/notifications',
    label: 'Notifications',
    section: 'Account',
    keywords: ['alerts', 'inbox'],
  },
  {
    path: '/profile',
    label: 'My Profile',
    section: 'Account',
    keywords: ['settings', 'account'],
  },
];

/**
 * Look up a static route descriptor by exact path.
 * Returns the descriptor or undefined for dynamic segments like /opportunities/:id.
 */
export function findRoute(path: string): RouteDescriptor | undefined {
  return ROUTES.find((r) => r.path === path);
}

/**
 * Returns a human-readable label for a dynamic path by walking each segment.
 * For a path like "/opportunities/42" returns "Opportunities > #42".
 */
export function buildCrumbs(pathname: string): Array<{ label: string; path: string | null }> {
  const segments = pathname.split('/').filter(Boolean);
  if (segments.length === 0) return [];

  const crumbs: Array<{ label: string; path: string | null }> = [];
  let accumulated = '';
  for (let i = 0; i < segments.length; i++) {
    accumulated += '/' + segments[i];
    const route = findRoute(accumulated);
    if (route) {
      crumbs.push({ label: route.label, path: i === segments.length - 1 ? null : accumulated });
    } else {
      // Dynamic segment (an id, slug, etc) — show as-is, no link
      crumbs.push({ label: `#${segments[i]}`, path: null });
    }
  }
  return crumbs;
}
