import React, { useState } from 'react';
import {
  Modal, Select, Input, Alert, Space, Typography, List, Tag, Skeleton, message, Empty,
} from 'antd';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { usersApi } from '@/api/endpoints';
import type { UserResponse, WorkloadCounts } from '@/types';
import dayjs from 'dayjs';

/**
 * Handing a leaver's open work to somebody else.
 *
 * Deactivating an account no longer just sets a flag — the API refuses while
 * the person still holds live work, because that work would otherwise stay
 * assigned to a login nobody can use. Invisible, not gone, which is worse.
 * This is where an admin sees exactly what is outstanding and moves it.
 */
const LABELS: Record<keyof WorkloadCounts, string> = {
  opportunities_submitted: 'opportunities they submitted',
  opportunities_as_sales_rep: 'opportunities they are the sales rep on',
  companies_managed: 'companies they channel-manage',
  deal_registrations_pending: 'deal registrations awaiting a decision',
  poc_team_seats: 'POC team seats',
  poc_stages_owned: 'POC stages they own',
};

interface Props {
  user: UserResponse | null;
  candidates: UserResponse[];
  onClose: () => void;
}

const HandoverModal: React.FC<Props> = ({ user, candidates, onClose }) => {
  const queryClient = useQueryClient();
  const [successor, setSuccessor] = useState<number | undefined>();
  const [notes, setNotes] = useState('');

  const { data, isLoading } = useQuery({
    queryKey: ['workload', user?.id],
    queryFn: async () => (await usersApi.workload(user!.id)).data,
    enabled: user !== null,
  });

  const handOverMut = useMutation({
    mutationFn: () => usersApi.handOver(user!.id, successor!, notes.trim() || undefined),
    onSuccess: () => {
      setSuccessor(undefined);
      setNotes('');
      void queryClient.invalidateQueries({ queryKey: ['workload', user?.id] });
      void queryClient.invalidateQueries({ queryKey: ['users'] });
      void message.success('Work handed over — the account can now be deactivated');
      onClose();
    },
    onError: (e: unknown) => {
      const detail = (e as { response?: { data?: { message?: string } } })?.response?.data?.message;
      void message.error(detail ?? 'Could not hand the work over');
    },
  });

  const outstanding = Object.entries(data?.counts ?? {}).filter(([, n]) => n > 0) as
    [keyof WorkloadCounts, number][];

  return (
    <Modal
      title={`Hand over ${user?.full_name ?? ''}'s work`}
      open={user !== null}
      onCancel={onClose}
      onOk={() => handOverMut.mutate()}
      confirmLoading={handOverMut.isPending}
      okText="Hand over"
      okButtonProps={{ disabled: !successor || outstanding.length === 0 }}
      width={640}
    >
      {isLoading ? (
        <Skeleton active paragraph={{ rows: 4 }} />
      ) : (
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          {outstanding.length === 0 ? (
            <Alert
              type="success"
              showIcon
              message="Nothing outstanding"
              description="This account holds no live work, so it can be deactivated as it is."
            />
          ) : (
            <Alert
              type="warning"
              showIcon
              message="This account still holds live work"
              description={
                <List
                  size="small"
                  dataSource={outstanding}
                  renderItem={([key, count]) => (
                    <List.Item style={{ padding: '4px 0', border: 'none' }}>
                      <Tag>{count}</Tag> {LABELS[key]}
                    </List.Item>
                  )}
                />
              }
            />
          )}

          {outstanding.length > 0 && (
            <>
              <div>
                <Typography.Text type="secondary">
                  Who takes it over. A partner&apos;s pipeline can only move to
                  another partner at the same company — it belongs to the company,
                  not the person.
                </Typography.Text>
                <Select
                  style={{ width: '100%', marginTop: 4 }}
                  showSearch
                  optionFilterProp="label"
                  placeholder="Select somebody"
                  value={successor}
                  onChange={setSuccessor}
                  options={candidates
                    .filter((c) => c.id !== user?.id && c.status === 'active')
                    .map((c) => ({
                      value: c.id,
                      label: `${c.full_name} — ${c.role}${c.company_name ? ` (${c.company_name})` : ''}`,
                    }))}
                />
              </div>
              <Input.TextArea
                rows={2}
                placeholder="Why (optional) — e.g. left the company in August"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                maxLength={2000}
              />
            </>
          )}

          {(data?.history?.length ?? 0) > 0 && (
            <div>
              <Typography.Text strong>Previous handovers</Typography.Text>
              <List
                size="small"
                dataSource={data!.history}
                locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} /> }}
                renderItem={(h) => (
                  <List.Item>
                    <Space direction="vertical" size={0}>
                      <span>
                        {h.from_user_name} → {h.to_user_name}{' '}
                        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                          {dayjs(h.created_at).format('MMM D, YYYY')}
                        </Typography.Text>
                      </span>
                      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                        {Object.entries(h.moved)
                          .filter(([, n]) => (n ?? 0) > 0)
                          .map(([k, n]) => `${n} ${LABELS[k as keyof WorkloadCounts] ?? k}`)
                          .join(', ')}
                        {h.notes ? ` — ${h.notes}` : ''}
                      </Typography.Text>
                    </Space>
                  </List.Item>
                )}
              />
            </div>
          )}
        </Space>
      )}
    </Modal>
  );
};

export default HandoverModal;
