import type { CompanyType } from '@/types';

/**
 * Presentation for the company classification, in one place so the list,
 * detail, forms and dashboards all label and colour a type identically.
 *
 * The `channel` flag is the UI mirror of the backend's CHANNEL_COMPANY_TYPES:
 * it says whether this company takes part in the partner programme (deal
 * registration, commissions, scorecard, tier). Read it rather than testing
 * `=== 'customer'`, so a future fourth type is one edit here.
 */
export interface CompanyTypeMeta {
  value: CompanyType;
  label: string;
  color: string;
  channel: boolean;
  description: string;
}

export const COMPANY_TYPES: readonly CompanyTypeMeta[] = [
  {
    value: 'partner',
    label: 'Partner',
    color: 'blue',
    channel: true,
    description: 'Direct channel partner — registers deals and earns commission.',
  },
  {
    value: 'distributor',
    label: 'Distributor',
    color: 'geekblue',
    channel: true,
    description: 'Resells through sub-partners — full partner programme access.',
  },
  {
    value: 'customer',
    label: 'Customer',
    color: 'purple',
    channel: false,
    description:
      'End customer with a portal login. No deal registration, commissions, scorecard or tier.',
  },
] as const;

const BY_VALUE = new Map<string, CompanyTypeMeta>(COMPANY_TYPES.map((t) => [t.value, t]));

export function companyTypeMeta(type: CompanyType | null | undefined): CompanyTypeMeta | undefined {
  return type ? BY_VALUE.get(type) : undefined;
}

export function companyTypeLabel(type: CompanyType | null | undefined): string {
  return companyTypeMeta(type)?.label ?? '—';
}

/** Whether this company takes part in the partner programme. */
export function isChannelCompanyType(type: CompanyType | null | undefined): boolean {
  return companyTypeMeta(type)?.channel ?? false;
}

/** Options for an antd Select. */
export const COMPANY_TYPE_OPTIONS = COMPANY_TYPES.map((t) => ({
  value: t.value,
  label: t.label,
}));
