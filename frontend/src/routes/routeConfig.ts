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

export interface RouteDescriptor {
  path: string;
  label: string;
  section?: string;
  icon?: string; // ant design icon name, for palette only
  roles?: UserRole[]; // if unset → available to all authenticated users
  keywords?: string[]; // extra search terms for the palette
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
    path: '/audit-logs',
    label: 'Audit Logs',
    section: 'Administration',
    roles: ['admin'],
    keywords: ['audit', 'history', 'activity', 'log', 'trail'],
  },
  {
    path: '/admin/bulk-import',
    label: 'Bulk Import',
    section: 'Administration',
    roles: ['admin'],
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
    // Deal registration is a partner/admin workflow; sales reps are denied
    // by the backend, so keep it out of their command palette too.
    path: '/deals',
    label: 'Deal Registration',
    section: 'Pipeline',
    roles: ['admin', 'partner'],
    keywords: ['deal', 'exclusivity', 'register'],
  },
  {
    path: '/commissions',
    label: 'Commissions',
    section: 'Earnings',
    roles: ['admin', 'partner'],
    keywords: ['payout', 'money', 'earnings'],
  },
  {
    path: '/scorecard',
    label: 'My Scorecard',
    section: 'Earnings',
    roles: ['partner'],
    keywords: ['tier', 'progress', 'badges'],
  },
  {
    path: '/leaderboard',
    label: 'Leaderboard',
    section: 'Earnings',
    roles: ['admin', 'partner'],
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
    roles: ['admin'],
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
