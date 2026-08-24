/**
 * POC + post-PO licence panel for the opportunity detail page.
 *
 * This is where the modules join up: an opportunity's POC starts on VM
 * allocation, runs the five stages, closes successful/unsuccessful, and —
 * once the PO lands — becomes a tracked customer licence with device/node
 * counts and an expiry.
 *
 * Admins and sales reps edit; partners see the same thing read-only.
 *
 * The POC team roster sits in the middle: an admin staffs the POC there, and
 * anyone staffed on it can reach this page and drive the POC even though the
 * opportunity names a different sales rep.
 */
import React, { useState } from 'react';
import {
  Card, Button, Empty, Descriptions, Space, Modal, Form, DatePicker, Input,
  InputNumber, message, Typography, Tag, Alert, Radio, Select,
} from 'antd';
import { RocketOutlined, SafetyCertificateOutlined, WarningOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import dayjs from 'dayjs';
import { pocsApi, licensesApi } from '@/api/endpoints';
import { useAuth } from '@/contexts/AuthContext';
import { PocStageTracker, PocStatusTag } from '@/components/dashboard/PocWidgets';
import PocTeamPanel from '@/components/poc/PocTeamPanel';
import PocActivityPanel from '@/components/poc/PocActivityPanel';
import type { PocResponse, PocStageState, LicenseStatus } from '@/types';

const { Text } = Typography;

const LICENSE_TAG: Record<LicenseStatus, { color: string; label: string }> = {
  pending_activation: { color: '#94a3b8', label: 'Pending Activation' },
  active: { color: '#10b981', label: 'Active' },
  expiring_soon: { color: '#f59e0b', label: 'Expiring Soon' },
  expired: { color: '#ef4444', label: 'Expired' },
};

interface Props {
  opportunityId: number;
}

const OpportunityPocPanel: React.FC<Props> = ({ opportunityId }) => {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const canEdit = user?.role === 'admin' || user?.role === 'sales_rep';

  // The stage whose owner is being picked, or null when the modal is closed.
  const [ownerStage, setOwnerStage] = useState<PocStageState | null>(null);
  const [startOpen, setStartOpen] = useState(false);
  const [closeOpen, setCloseOpen] = useState(false);
  const [licOpen, setLicOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [startForm] = Form.useForm();
  const [closeForm] = Form.useForm();
  const [licForm] = Form.useForm();
  const [editForm] = Form.useForm();

  const { data: poc, isLoading } = useQuery({
    queryKey: ['poc', opportunityId],
    queryFn: async () => (await pocsApi.getByOpportunity(opportunityId)).data,
  });

  const { data: license } = useQuery({
    queryKey: ['license', opportunityId],
    queryFn: async () => (await licensesApi.getByOpportunity(opportunityId)).data,
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['poc', opportunityId] });
    queryClient.invalidateQueries({ queryKey: ['license', opportunityId] });
    queryClient.invalidateQueries({ queryKey: ['poc-summary'] });
    queryClient.invalidateQueries({ queryKey: ['pocs'] });
    queryClient.invalidateQueries({ queryKey: ['poc-activities'] });
  };

  const fail = (e: { response?: { data?: { message?: string } } }, fallback: string) =>
    message.error(e.response?.data?.message ?? fallback);

  const startMut = useMutation({
    mutationFn: (values: Record<string, unknown>) => pocsApi.start(opportunityId, values as never),
    onSuccess: () => {
      message.success('POC started — VM allocated');
      setStartOpen(false);
      startForm.resetFields();
      invalidate();
    },
    onError: (e: never) => fail(e, 'Could not start the POC'),
  });

  const stageMut = useMutation({
    mutationFn: ({ p, s }: { p: PocResponse; s: PocStageState }) =>
      pocsApi.setStage(p.id, s.key, s.completed ? null : dayjs().format('YYYY-MM-DD')),
    onSuccess: (_r, v) => {
      message.success(`${v.s.label} ${v.s.completed ? 'cleared' : 'complete'}`);
      invalidate();
    },
    onError: (e: never) => fail(e, 'Could not update the stage'),
  });

  const ownerMut = useMutation({
    mutationFn: ({ stage, userId }: { stage: PocStageState; userId: number | null }) =>
      pocsApi.setStageOwner(poc!.id, stage.key, userId),
    onSuccess: () => {
      message.success('Stage owner updated');
      setOwnerStage(null);
      invalidate();
    },
    onError: (e: never) => fail(e, 'Could not set the stage owner'),
  });

  const editMut = useMutation({
    mutationFn: (values: Record<string, unknown>) => pocsApi.update(poc!.id, values),
    onSuccess: () => {
      message.success('POC updated');
      setEditOpen(false);
      invalidate();
    },
    onError: (e: never) => fail(e, 'Could not update the POC'),
  });

  const openEdit = () => {
    if (!poc) return;
    editForm.setFieldsValue({
      start_date: poc.start_date ? dayjs(poc.start_date) : null,
      target_end_date: poc.target_end_date ? dayjs(poc.target_end_date) : null,
      notes: poc.notes ?? undefined,
    });
    setEditOpen(true);
  };

  const closeMut = useMutation({
    mutationFn: (values: Record<string, unknown>) => pocsApi.close(poc!.id, values as never),
    onSuccess: () => {
      message.success('POC closed');
      setCloseOpen(false);
      closeForm.resetFields();
      invalidate();
    },
    onError: (e: never) => fail(e, 'Could not close the POC'),
  });

  const reopenMut = useMutation({
    mutationFn: () => pocsApi.reopen(poc!.id),
    onSuccess: () => { message.success('POC reopened'); invalidate(); },
    onError: (e: never) => fail(e, 'Could not reopen the POC'),
  });

  const licMut = useMutation({
    mutationFn: (values: Record<string, unknown>) => licensesApi.upsert(opportunityId, values as never),
    onSuccess: () => {
      message.success('Customer tracking saved');
      setLicOpen(false);
      invalidate();
    },
    onError: (e: never) => fail(e, 'Could not save the licence'),
  });

  return (
    <>
      {/* ---------------- POC ---------------- */}
      <Card
        title={<span><RocketOutlined style={{ color: '#3750ed', marginRight: 8 }} />Proof of Concept</span>}
        variant="borderless"
        style={{ borderRadius: 12, marginTop: 16 }}
        loading={isLoading}
        extra={
          canEdit && (
            poc && poc.status === 'running' ? (
              <Space>
                <Button size="small" onClick={openEdit}>Edit</Button>
                <Button size="small" onClick={() => setCloseOpen(true)}>Close POC</Button>
              </Space>
            ) : poc?.closed_at ? (
              <Button size="small" type="link" onClick={() => reopenMut.mutate()} loading={reopenMut.isPending}>
                Reopen
              </Button>
            ) : !poc || poc.status === 'not_started' ? (
              <Button size="small" type="primary" onClick={() => setStartOpen(true)}>
                Start POC (allocate VM)
              </Button>
            ) : null
          )
        }
      >
        {!poc || poc.status === 'not_started' ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              canEdit
                ? 'No POC yet. The POC starts when the VM is allocated.'
                : 'No POC has been started for this opportunity yet.'
            }
          />
        ) : (
          <>
            {poc.is_overdue && (
              <Alert
                type="warning"
                showIcon
                icon={<WarningOutlined />}
                message={`This POC passed its target end date (${poc.target_end_date})`}
                style={{ marginBottom: 16, borderRadius: 8 }}
              />
            )}

            <Space style={{ marginBottom: 20 }} wrap>
              <PocStatusTag status={poc.status} />
              <Text type="secondary" style={{ fontSize: 12 }}>
                Started {poc.start_date}
                {poc.days_running !== null && ` · ${poc.days_running} days`}
                {poc.current_stage_label && ` · now: ${poc.current_stage_label}`}
              </Text>
            </Space>

            <PocStageTracker
              stages={poc.stages}
              disabled={stageMut.isPending || !!poc.closed_at}
              onToggle={canEdit && !poc.closed_at ? (s) => stageMut.mutate({ p: poc, s }) : undefined}
              // Owners come back null for a partner, so the row is absent for
              // them regardless; this only decides who can change one.
              onAssignOwner={canEdit ? (s) => setOwnerStage(s) : undefined}
            />

            {poc.closed_at && (
              <div style={{ marginTop: 20, paddingTop: 16, borderTop: '1px solid #f0f0f0' }}>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  Closed {dayjs(poc.closed_at).format('YYYY-MM-DD')}
                  {poc.closed_by_name ? ` by ${poc.closed_by_name}` : ''}
                  {poc.failure_reason ? ` — ${poc.failure_reason}` : ''}
                </Text>
                {poc.outcome_notes && <div><Text style={{ fontSize: 12 }}>{poc.outcome_notes}</Text></div>}
              </div>
            )}
          </>
        )}
      </Card>

      {/* Stage owner picker. Options come from the POC's own roster: only
          someone on the team can own a stage, which the API enforces too. */}
      <Modal
        title={ownerStage ? `Who owns ${ownerStage.label}?` : 'Stage owner'}
        open={ownerStage !== null}
        onCancel={() => setOwnerStage(null)}
        footer={null}
      >
        {poc && poc.team.length === 0 ? (
          <Alert
            type="info"
            showIcon
            message="Nobody is on this POC team yet"
            description="Add people to the team below, then come back to divide up the stages."
          />
        ) : (
          <>
            <Select
              style={{ width: '100%' }}
              placeholder="Select someone from the POC team"
              value={ownerStage?.owner_user_id ?? undefined}
              loading={ownerMut.isPending}
              options={(poc?.team ?? []).map((m) => ({
                value: m.user_id,
                label: `${m.user_name ?? 'Unknown'} — ${m.role_label}`,
              }))}
              onChange={(userId: number) =>
                ownerStage && ownerMut.mutate({ stage: ownerStage, userId })
              }
            />
            {ownerStage?.owner_user_id != null && (
              <Button
                type="link"
                danger
                style={{ paddingLeft: 0, marginTop: 12 }}
                loading={ownerMut.isPending}
                onClick={() =>
                  ownerStage && ownerMut.mutate({ stage: ownerStage, userId: null })
                }
              >
                Leave this stage unowned
              </Button>
            )}
          </>
        )}
      </Modal>

      {/* The roster sits between the POC and its post-PO tracking because
          that is the span of work these people cover. */}
      <PocTeamPanel
        pocId={poc?.id ?? null}
        team={poc?.team ?? []}
        onChanged={invalidate}
      />

      {/* Who actually did what. Internal only — the API refuses partners, and
          rendering it for them would just show a permanent error card. */}
      {canEdit && poc && <PocActivityPanel pocId={poc.id} />}

      {/* ---------------- Post-PO customer tracking ---------------- */}
      <Card
        title={<span><SafetyCertificateOutlined style={{ color: '#10b981', marginRight: 8 }} />Customer Tracking (post-PO)</span>}
        variant="borderless"
        style={{ borderRadius: 12, marginTop: 16 }}
        extra={
          canEdit && (
            <Button
              size="small"
              type={license ? 'default' : 'primary'}
              onClick={() => {
                // Prefill from the existing record so the form is an edit,
                // not a blank re-entry.
                licForm.setFieldsValue({
                  po_number: license?.po_number,
                  po_received_date: license?.po_received_date ? dayjs(license.po_received_date) : null,
                  po_value: license?.po_value ? Number(license.po_value) : null,
                  device_count: license?.device_count,
                  node_count: license?.node_count,
                  license_activated_at: license?.license_activated_at ? dayjs(license.license_activated_at) : null,
                  license_expires_at: license?.license_expires_at ? dayjs(license.license_expires_at) : null,
                  license_key: license?.license_key,
                  notes: license?.notes,
                });
                setLicOpen(true);
              }}
            >
              {license ? 'Edit' : 'Record PO'}
            </Button>
          )
        }
      >
        {!license ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={canEdit ? 'No PO recorded yet.' : 'No PO recorded yet.'}
          />
        ) : (
          <>
            {license.status === 'expiring_soon' && license.days_until_expiry !== null && (
              <Alert
                type="warning"
                showIcon
                message={`Licence expires in ${license.days_until_expiry} days`}
                style={{ marginBottom: 16, borderRadius: 8 }}
              />
            )}
            {license.status === 'expired' && (
              <Alert type="error" showIcon message="This licence has expired" style={{ marginBottom: 16, borderRadius: 8 }} />
            )}
            <Descriptions bordered column={{ xs: 1, sm: 2 }} size="small">
              <Descriptions.Item label="Status">
                <Tag color={LICENSE_TAG[license.status].color} style={{ border: 'none', fontWeight: 600 }}>
                  {LICENSE_TAG[license.status].label}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="PO Number">{license.po_number ?? '—'}</Descriptions.Item>
              <Descriptions.Item label="PO Received">{license.po_received_date ?? '—'}</Descriptions.Item>
              <Descriptions.Item label="PO Value">
                {license.po_value ? `$${Number(license.po_value).toLocaleString()}` : '—'}
              </Descriptions.Item>
              <Descriptions.Item label="Devices">{license.device_count ?? '—'}</Descriptions.Item>
              <Descriptions.Item label="Nodes">{license.node_count ?? '—'}</Descriptions.Item>
              <Descriptions.Item label="Licence Activated">{license.license_activated_at ?? '—'}</Descriptions.Item>
              <Descriptions.Item label="Licence Expires">
                {license.license_expires_at ?? '—'}
                {license.days_until_expiry !== null && license.license_expires_at && (
                  <Text type="secondary" style={{ fontSize: 11, marginLeft: 6 }}>
                    ({license.days_until_expiry}d)
                  </Text>
                )}
              </Descriptions.Item>
              {license.notes && (
                <Descriptions.Item label="Notes" span={{ xs: 1, sm: 2 }}>{license.notes}</Descriptions.Item>
              )}
            </Descriptions>
          </>
        )}
      </Card>

      {/* ---------------- Modals ---------------- */}
      <Modal
        title="Edit POC"
        open={editOpen}
        onCancel={() => setEditOpen(false)}
        onOk={() => editForm.submit()}
        confirmLoading={editMut.isPending}
        okText="Save"
      >
        <Form
          form={editForm}
          layout="vertical"
          onFinish={(v) =>
            editMut.mutate({
              // start_date drives vm_provisioning_completed_at on the backend
              // (they're kept in lockstep), so send it via that field.
              vm_provisioning_completed_at: v.start_date ? v.start_date.format('YYYY-MM-DD') : undefined,
              target_end_date: v.target_end_date ? v.target_end_date.format('YYYY-MM-DD') : null,
              notes: v.notes ?? null,
            })
          }
        >
          <Form.Item name="start_date" label="VM allocation / start date">
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="target_end_date" label="Target end date">
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="notes" label="Notes">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="Start POC — allocate VM"
        open={startOpen}
        onCancel={() => setStartOpen(false)}
        onOk={() => startForm.submit()}
        confirmLoading={startMut.isPending}
        okText="Start POC"
      >
        <Alert
          type="info"
          showIcon
          message="Starting the POC records VM Provisioning as complete — they're the same event."
          style={{ marginBottom: 16, borderRadius: 8 }}
        />
        <Form
          form={startForm}
          layout="vertical"
          initialValues={{ start_date: dayjs() }}
          onFinish={(v) =>
            startMut.mutate({
              start_date: v.start_date.format('YYYY-MM-DD'),
              target_end_date: v.target_end_date ? v.target_end_date.format('YYYY-MM-DD') : null,
              notes: v.notes ?? null,
            })
          }
        >
          <Form.Item name="start_date" label="VM allocation date" rules={[{ required: true }]}>
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="target_end_date" label="Target end date">
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="notes" label="Notes">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="Close POC"
        open={closeOpen}
        onCancel={() => setCloseOpen(false)}
        onOk={() => closeForm.submit()}
        confirmLoading={closeMut.isPending}
        okText="Close POC"
      >
        <Form
          form={closeForm}
          layout="vertical"
          initialValues={{ successful: true, end_date: dayjs() }}
          onFinish={(v) =>
            closeMut.mutate({
              successful: v.successful,
              end_date: v.end_date ? v.end_date.format('YYYY-MM-DD') : null,
              outcome_notes: v.outcome_notes ?? null,
              failure_reason: v.successful ? null : (v.failure_reason ?? null),
            })
          }
        >
          <Form.Item name="successful" label="Outcome" rules={[{ required: true }]}>
            <Radio.Group>
              <Radio.Button value={true}>Successful</Radio.Button>
              <Radio.Button value={false}>Unsuccessful</Radio.Button>
            </Radio.Group>
          </Form.Item>
          <Form.Item name="end_date" label="End date" rules={[{ required: true }]}>
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item noStyle shouldUpdate={(p, c) => p.successful !== c.successful}>
            {({ getFieldValue }) =>
              getFieldValue('successful') === false ? (
                <Form.Item name="failure_reason" label="Reason">
                  <Input maxLength={255} placeholder="e.g. lost on latency benchmarks" />
                </Form.Item>
              ) : null
            }
          </Form.Item>
          <Form.Item name="outcome_notes" label="Notes">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="Customer tracking"
        open={licOpen}
        onCancel={() => setLicOpen(false)}
        onOk={() => licForm.submit()}
        confirmLoading={licMut.isPending}
        okText="Save"
        width={620}
      >
        <Form
          form={licForm}
          layout="vertical"
          onFinish={(v) =>
            licMut.mutate({
              po_number: v.po_number ?? null,
              po_received_date: v.po_received_date ? v.po_received_date.format('YYYY-MM-DD') : null,
              po_value: v.po_value ?? null,
              device_count: v.device_count ?? null,
              node_count: v.node_count ?? null,
              license_activated_at: v.license_activated_at ? v.license_activated_at.format('YYYY-MM-DD') : null,
              license_expires_at: v.license_expires_at ? v.license_expires_at.format('YYYY-MM-DD') : null,
              license_key: v.license_key ?? null,
              notes: v.notes ?? null,
            })
          }
        >
          <Space style={{ display: 'flex' }} align="start">
            <Form.Item name="po_number" label="PO number" style={{ flex: 1 }}>
              <Input placeholder="PO-2027-0142" />
            </Form.Item>
            <Form.Item name="po_received_date" label="PO received" style={{ flex: 1 }}>
              <DatePicker style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="po_value" label="PO value" style={{ flex: 1 }}>
              <InputNumber style={{ width: '100%' }} min={0} prefix="$" />
            </Form.Item>
          </Space>
          <Space style={{ display: 'flex' }} align="start">
            <Form.Item name="device_count" label="Devices" style={{ flex: 1 }}>
              <InputNumber style={{ width: '100%' }} min={0} />
            </Form.Item>
            <Form.Item name="node_count" label="Nodes" style={{ flex: 1 }}>
              <InputNumber style={{ width: '100%' }} min={0} />
            </Form.Item>
          </Space>
          <Space style={{ display: 'flex' }} align="start">
            <Form.Item name="license_activated_at" label="Licence activated" style={{ flex: 1 }}>
              <DatePicker style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="license_expires_at" label="Licence expires" style={{ flex: 1 }}>
              <DatePicker style={{ width: '100%' }} />
            </Form.Item>
          </Space>
          <Form.Item name="license_key" label="Licence key">
            <Input />
          </Form.Item>
          <Form.Item name="notes" label="Notes">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
};

export default OpportunityPocPanel;
