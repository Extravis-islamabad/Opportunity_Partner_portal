import React from 'react';
import { Select } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { companiesApi } from '@/api/endpoints';

interface Props {
  /** Provided by Form.Item — do not pass by hand. */
  value?: number | null;
  onChange?: (value: number | null) => void;
  disabled?: boolean;
  /** Kept out of the list so a company cannot be offered itself as a parent. */
  excludeCompanyId?: number;
  /**
   * Name of the currently linked distributor. Used to render the selection
   * when the picker is disabled, since a channel manager's company list only
   * covers the companies they manage and may not contain the parent at all.
   */
  currentLabel?: string | null;
}

/**
 * Picks the distributor a partner company resells through.
 *
 * Only distributors are offered, because only a distributor may be a parent
 * (company_service.assert_valid_parent_distributor). Clearing the select sends
 * an explicit null, which is what unlinks a reseller — so `allowClear` is
 * load-bearing, not decoration.
 */
const ParentDistributorSelect: React.FC<Props> = ({
  value,
  onChange,
  disabled,
  excludeCompanyId,
  currentLabel,
}) => {
  const { data, isLoading } = useQuery({
    queryKey: ['distributors'],
    queryFn: async () => {
      const res = await companiesApi.list({
        company_type: 'distributor',
        page_size: 100,
        status: 'active',
      });
      return res.data.items;
    },
    // Nothing is selectable when disabled, and a channel manager's list would
    // be scoped to their own companies anyway — so don't ask for it.
    enabled: !disabled,
  });

  const options = disabled
    ? value != null
      ? [{ value, label: currentLabel ?? `Company #${value}` }]
      : []
    : (data ?? [])
        .filter((c) => c.id !== excludeCompanyId)
        .map((c) => ({ value: c.id, label: `${c.name} (${c.country})` }));

  return (
    <Select
      value={value ?? undefined}
      // antd hands back `undefined` when cleared; the API needs an explicit
      // null to mean "unlink", since an absent field means "leave alone".
      onChange={(v?: number) => onChange?.(v ?? null)}
      options={options}
      loading={isLoading}
      disabled={disabled}
      allowClear
      showSearch
      optionFilterProp="label"
      placeholder={
        !disabled && options.length === 0 && !isLoading
          ? 'No distributors exist yet'
          : 'Reports directly to Extravis'
      }
    />
  );
};

export default ParentDistributorSelect;
