import React from 'react';
import { Select } from 'antd';
import { useQuery } from '@tanstack/react-query';
import { usersApi } from '@/api/endpoints';

interface Props {
  /** Provided by Form.Item — do not pass by hand. */
  value?: number[];
  onChange?: (value: number[]) => void;
  disabled?: boolean;
}

/**
 * Picks every admin who looks after a company. The first one chosen is the
 * primary channel manager — the name shown where only one fits — and every
 * one of them gets the company in their scope and its notifications.
 */
const ChannelManagersSelect: React.FC<Props> = ({ value, onChange, disabled }) => {
  const { data: admins, isLoading } = useQuery({
    queryKey: ['admins-list'],
    queryFn: async () => (await usersApi.getAdmins()).data,
  });

  return (
    <Select
      mode="multiple"
      value={value}
      onChange={onChange}
      disabled={disabled}
      loading={isLoading}
      placeholder="Select one or more channel managers"
      showSearch
      optionFilterProp="label"
      maxTagCount="responsive"
      options={(admins ?? []).map((a) => ({
        value: a.id,
        label: `${a.full_name} (${a.email})`,
      }))}
    />
  );
};

export default ChannelManagersSelect;
