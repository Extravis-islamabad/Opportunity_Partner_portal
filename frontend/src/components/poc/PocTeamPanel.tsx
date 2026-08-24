/**
 * The POC team roster.
 *
 * An opportunity has one named sales rep. A POC needs a presales lead, a
 * solution architect, a deployment engineer and whoever else — this is where
 * an admin puts them there.
 *
 * Membership grants access, so the controls are admin-only. A sales rep sees
 * the roster read-only; the API refuses their writes either way, and offering
 * a button that always 403s is worse than not offering it.
 *
 * A partner sees a roster the *server* has already redacted to names and POC
 * roles — no emails, job titles or assignment metadata. This component does
 * not re-implement that rule; it just renders nothing where the server sent
 * nothing, so there is one place the redaction lives.
 */
import React, { useState } from 'react';
import {
  Card, Table, Button, Select, Modal, Form, Tag, Space, Popconfirm, Empty,
  message, Typography, Avatar,
} from 'antd';
import { UserAddOutlined, DeleteOutlined, TeamOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AxiosError } from 'axios';
import { pocTeamApi } from '@/api/endpoints';
import { useAuth } from '@/contexts/AuthContext';
import type {
  ErrorResponse, PocTeamMember, PocTeamRoleKey,
} from '@/types';
import type { ColumnsType } from 'antd/es/table';

const { Text } = Typography;

/** Distinct colours so a roster reads at a glance rather than as a wall of grey. */
const ROLE_COLOR: Record<PocTeamRoleKey, string> = {
  presales_lead: 'blue',
  solution_architect: 'geekblue',
  deployment_engineer: 'cyan',
  project_manager: 'purple',
  qa: 'gold',
  support: 'green',
};

interface Props {
  /** Null before the POC has been started — there is nothing to staff yet. */
  pocId: number | null;
  team: PocTeamMember[];
  /** Called after any change, so the parent can refetch the POC. */
  onChanged: () => void;
}

const PocTeamPanel: React.FC<Props> = ({ pocId, team, onChanged }) => {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  // Staffing a POC is a management decision and it hands out access, so it is
  // not self-service. Mirrors get_current_admin on the mutating routes.
  const canManage = user?.role === 'admin';

  const [addOpen, setAddOpen] = useState(false);
  const [form] = Form.useForm();

  const { data: roles } = useQuery({
    queryKey: ['poc-team-roles'],
    queryFn: async () => (await pocTeamApi.roles()).data,
    // The list is a fixed enum; no point refetching it per POC.
    staleTime: Infinity,
    // Only managers get a role picker, and the endpoint is staff-only — a
    // partner viewing their POC would just collect a 403 per render.
    enabled: canManage,
  });

  const { data: assignable } = useQuery({
    queryKey: ['poc-assignable-users'],
    queryFn: async () => (await pocTeamApi.assignableUsers()).data,
    // Admin-only endpoint — asking as a sales rep would just 403.
    enabled: canManage && addOpen,
  });

  const onError = (err: AxiosError<ErrorResponse>) => {
    void message.error(err.response?.data?.message ?? 'Something went wrong');
  };

  const settled = () => {
    void queryClient.invalidateQueries({ queryKey: ['poc-team-roles'] });
    onChanged();
  };

  const addMutation = useMutation({
    mutationFn: ({ userId, role }: { userId: number; role: PocTeamRoleKey }) =>
      pocTeamApi.add(pocId!, userId, role),
    onSuccess: () => {
      void message.success('Added to the POC team');
      setAddOpen(false);
      form.resetFields();
      settled();
    },
    onError,
  });

  const roleMutation = useMutation({
    mutationFn: ({ userId, role }: { userId: number; role: PocTeamRoleKey }) =>
      pocTeamApi.changeRole(pocId!, userId, role),
    onSuccess: () => {
      void message.success('Role updated');
      settled();
    },
    onError,
  });

  const removeMutation = useMutation({
    mutationFn: (userId: number) => pocTeamApi.remove(pocId!, userId),
    onSuccess: () => {
      void message.success('Removed from the POC team');
      settled();
    },
    onError,
  });

  // People already on the team can't be added again — the API returns 409, so
  // don't offer them.
  const onTeam = new Set(team.map((m) => m.user_id));
  const options = (assignable ?? [])
    .filter((u) => !onTeam.has(u.id))
    .map((u) => ({
      value: u.id,
      label: `${u.full_name}${u.job_title ? ` — ${u.job_title}` : ''} (${u.email})`,
    }));

  const columns: ColumnsType<PocTeamMember> = [
    {
      title: 'Person',
      dataIndex: 'user_name',
      key: 'user_name',
      render: (name: string | null, record) => (
        <Space>
          <Avatar size="small" style={{ backgroundColor: '#3750ed' }}>
            {(name ?? '?').charAt(0).toUpperCase()}
          </Avatar>
          <span>
            <div style={{ fontWeight: 600 }}>{name ?? '—'}</div>
            {/* Null for a partner viewer — the server redacts job title and
                email out of the roster, so the second line simply vanishes
                rather than needing its own role check here. */}
            {(record.job_title ?? record.user_email) && (
              <Text type="secondary" style={{ fontSize: 12 }}>
                {record.job_title ?? record.user_email}
              </Text>
            )}
          </span>
        </Space>
      ),
    },
    {
      title: 'POC Role',
      dataIndex: 'role',
      key: 'role',
      render: (role: PocTeamRoleKey, record) =>
        canManage ? (
          <Select
            size="small"
            style={{ minWidth: 180 }}
            value={role}
            loading={roleMutation.isPending}
            options={(roles ?? []).map((r) => ({ value: r.value, label: r.label }))}
            onChange={(next) =>
              roleMutation.mutate({ userId: record.user_id, role: next })
            }
          />
        ) : (
          // role_label comes from the server so "QA" doesn't render as "Qa".
          <Tag color={ROLE_COLOR[role]}>{record.role_label}</Tag>
        ),
    },
    // Assignment metadata is internal: the server sends it as null to a
    // partner, so the column is dropped for them rather than rendering a row
    // of dashes.
    ...(team.some((m) => m.assigned_at)
      ? [{
          title: 'Assigned',
          dataIndex: 'assigned_at',
          key: 'assigned_at',
          render: (at: string | null, record: PocTeamMember) =>
            at ? (
              <Text type="secondary" style={{ fontSize: 12 }}>
                {new Date(at).toLocaleDateString()}
                {record.assigned_by_name ? ` by ${record.assigned_by_name}` : ''}
              </Text>
            ) : null,
        }]
      : []),
    ...(canManage
      ? [{
          title: '',
          key: 'actions',
          width: 100,
          render: (_: unknown, record: PocTeamMember) => (
            <Popconfirm
              title={`Remove ${record.user_name ?? 'this person'} from the POC?`}
              description="They lose access immediately, and any stage they own becomes unowned."
              okText="Remove"
              cancelText="Cancel"
              onConfirm={() => removeMutation.mutate(record.user_id)}
            >
              <Button type="link" danger size="small" icon={<DeleteOutlined />}>
                Remove
              </Button>
            </Popconfirm>
          ),
        }]
      : []),
  ];

  return (
    <Card
      title={
        <Space>
          <TeamOutlined />
          <span>POC Team{team.length > 0 ? ` (${team.length})` : ''}</span>
        </Space>
      }
      style={{ marginTop: 16 }}
      extra={
        canManage && pocId ? (
          <Button
            type="primary"
            size="small"
            icon={<UserAddOutlined />}
            onClick={() => setAddOpen(true)}
          >
            Add Person
          </Button>
        ) : null
      }
    >
      {pocId === null ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="Start the POC before staffing it"
        />
      ) : team.length === 0 ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={
            canManage
              ? 'Nobody assigned yet. Anyone you add can work on this POC.'
              : 'Nobody assigned to this POC yet'
          }
        />
      ) : (
        <Table
          rowKey="id"
          size="small"
          columns={columns}
          dataSource={team}
          pagination={false}
        />
      )}

      <Modal
        title="Add someone to the POC team"
        open={addOpen}
        onCancel={() => setAddOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={addMutation.isPending}
        okText="Add"
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={(values: { user_id: number; role: PocTeamRoleKey }) =>
            addMutation.mutate({ userId: values.user_id, role: values.role })
          }
        >
          <Form.Item
            name="user_id"
            label="Person"
            rules={[{ required: true, message: 'Choose someone to add' }]}
            extra="Extravis admins and sales reps. They will be notified, and can work on this POC straight away."
          >
            <Select
              placeholder="Search by name or email"
              showSearch
              optionFilterProp="label"
              options={options}
              notFoundContent="Everyone eligible is already on the team"
            />
          </Form.Item>
          <Form.Item
            name="role"
            label="POC Role"
            rules={[{ required: true, message: 'Choose what they do on this POC' }]}
          >
            <Select
              placeholder="Select a role"
              options={(roles ?? []).map((r) => ({ value: r.value, label: r.label }))}
            />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
};

export default PocTeamPanel;
