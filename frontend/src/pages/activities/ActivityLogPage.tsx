/**
 * Sales activity log.
 *
 * A Monday–Friday month grid of a rep's daily activities (calls, meetings,
 * demos, …). Sales reps log/edit/delete their own entries by clicking a day;
 * admins pick any rep and review the same grid read-only, with monthly
 * totals by activity type.
 */
import React, { useMemo, useState } from 'react';
import {
  Card, Row, Col, Select, Button, Modal, Form, DatePicker, Input, InputNumber,
  Tag, Tooltip, Typography, Space, Statistic, Empty, Popconfirm, message, Skeleton,
} from 'antd';
import {
  PlusOutlined, LeftOutlined, RightOutlined, PhoneOutlined,
  TeamOutlined, DeleteOutlined,
} from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import dayjs, { Dayjs } from 'dayjs';
import { activitiesApi, opportunitiesApi, pocsApi, usersApi } from '@/api/endpoints';
import { useAuth } from '@/contexts/AuthContext';
import PageHeader from '@/components/common/PageHeader';
import type { ActivityResponse, ActivityType } from '@/types';

const { Text } = Typography;

const TYPE_OPTIONS: Array<{ value: ActivityType; label: string }> = [
  { value: 'call', label: 'Call' },
  { value: 'meeting', label: 'Meeting' },
  { value: 'demo', label: 'Demo' },
  { value: 'email', label: 'Email' },
  { value: 'site_visit', label: 'Site Visit' },
  { value: 'follow_up', label: 'Follow-up' },
  { value: 'training', label: 'Training' },
  { value: 'other', label: 'Other' },
];

// Proper plural headings for the monthly totals row ('Training' and 'Other'
// don't take a naive +'s').
const TYPE_PLURALS: Record<ActivityType, string> = {
  call: 'Calls',
  meeting: 'Meetings',
  demo: 'Demos',
  email: 'Emails',
  site_visit: 'Site Visits',
  follow_up: 'Follow-ups',
  training: 'Training',
  other: 'Other',
};

const TYPE_COLORS: Record<ActivityType, string> = {
  call: 'blue',
  meeting: 'purple',
  demo: 'geekblue',
  email: 'cyan',
  site_visit: 'orange',
  follow_up: 'gold',
  training: 'green',
  other: 'default',
};

const WEEKDAY_HEADERS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'];

/** All Mon–Fri dates of the month, grouped into calendar weeks. Cells outside
 * the month are null so week rows stay aligned. */
function buildWeeks(month: Dayjs): Array<Array<Dayjs | null>> {
  const first = month.startOf('month');
  const last = month.endOf('month');
  // dayjs: .day() is 0=Sunday..6=Saturday; shift to Monday-based.
  const mondayOffset = (first.day() + 6) % 7;
  let cursor = first.subtract(mondayOffset, 'day'); // the Monday of week 1
  const weeks: Array<Array<Dayjs | null>> = [];
  while (cursor.isBefore(last) || cursor.isSame(last, 'day')) {
    const week: Array<Dayjs | null> = [];
    for (let i = 0; i < 5; i++) {
      const d = cursor.add(i, 'day');
      week.push(d.isSame(month, 'month') ? d : null);
    }
    if (week.some(Boolean)) weeks.push(week);
    cursor = cursor.add(7, 'day');
  }
  return weeks;
}

const ActivityLogPage: React.FC = () => {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const isRep = user?.role === 'sales_rep';
  const isAdmin = user?.role === 'admin';

  const [month, setMonth] = useState<Dayjs>(dayjs());
  const [repId, setRepId] = useState<number | undefined>();
  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<ActivityResponse | null>(null);
  const [form] = Form.useForm();

  const monthStr = month.format('YYYY-MM');
  // Reps always view themselves; admins view the selected rep.
  const targetUserId = isRep ? undefined : repId;

  const { data: reps } = useQuery({
    queryKey: ['sales-reps'],
    queryFn: async () =>
      (await usersApi.list({ role: 'sales_rep', page: 1, page_size: 100 })).data,
    enabled: isAdmin,
  });

  // Reps can optionally link an activity to one of their opportunities.
  const { data: myOpps } = useQuery({
    queryKey: ['my-opportunities-for-activities'],
    queryFn: async () =>
      (await opportunitiesApi.list({ page: 1, page_size: 100 })).data,
    enabled: isRep,
  });

  // POCs this person can work on — their own plus any they are on the team
  // of. The API applies that scope; nothing is filtered client-side.
  const { data: myPocs } = useQuery({
    queryKey: ['my-pocs-for-activities'],
    queryFn: async () => (await pocsApi.list({ page: 1, page_size: 100 })).data,
  });

  const { data: log, isLoading } = useQuery({
    queryKey: ['activity-month', monthStr, targetUserId],
    queryFn: async () => (await activitiesApi.getMonth(monthStr, targetUserId)).data,
    enabled: isRep || (isAdmin && !!repId),
  });

  const byDate = useMemo(() => {
    const map: Record<string, ActivityResponse[]> = {};
    log?.days.forEach((d) => { map[d.date] = d.items; });
    return map;
  }, [log]);

  const weeks = useMemo(() => buildWeeks(month), [month]);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['activity-month'] });
  const fail = (e: unknown, fallback: string) => {
    const msg = (e as { response?: { data?: { message?: string } } })?.response?.data?.message;
    message.error(msg ?? fallback);
  };

  const createMut = useMutation({
    mutationFn: (values: Parameters<typeof activitiesApi.create>[0]) => activitiesApi.create(values),
    onSuccess: () => { message.success('Activity logged'); closeEditor(); invalidate(); },
    onError: (e) => fail(e, 'Could not log the activity'),
  });
  const updateMut = useMutation({
    mutationFn: ({ id, values }: { id: number; values: Partial<Parameters<typeof activitiesApi.create>[0]> }) =>
      activitiesApi.update(id, values),
    onSuccess: () => { message.success('Activity updated'); closeEditor(); invalidate(); },
    onError: (e) => fail(e, 'Could not update the activity'),
  });
  const deleteMut = useMutation({
    mutationFn: (id: number) => activitiesApi.remove(id),
    onSuccess: () => { message.success('Activity deleted'); invalidate(); },
    onError: (e) => fail(e, 'Could not delete the activity'),
  });

  const openCreate = (day: Dayjs) => {
    setEditing(null);
    form.setFieldsValue({
      activity_date: day,
      activity_type: 'call',
      customer_name: undefined,
      opportunity_id: undefined,
      poc_id: undefined,
      duration_minutes: undefined,
      notes: undefined,
    });
    setEditorOpen(true);
  };

  const openEdit = (a: ActivityResponse) => {
    setEditing(a);
    form.setFieldsValue({
      activity_date: dayjs(a.activity_date),
      activity_type: a.activity_type,
      customer_name: a.customer_name ?? undefined,
      opportunity_id: a.opportunity_id ?? undefined,
      poc_id: a.poc_id ?? undefined,
      duration_minutes: a.duration_minutes ?? undefined,
      notes: a.notes ?? undefined,
    });
    setEditorOpen(true);
  };

  const closeEditor = () => { setEditorOpen(false); setEditing(null); form.resetFields(); };

  const submit = (v: {
    activity_date: Dayjs; activity_type: ActivityType;
    customer_name?: string; opportunity_id?: number; poc_id?: number;
    duration_minutes?: number; notes?: string;
  }) => {
    const payload = {
      activity_date: v.activity_date.format('YYYY-MM-DD'),
      activity_type: v.activity_type,
      customer_name: v.customer_name || null,
      opportunity_id: v.opportunity_id ?? null,
      poc_id: v.poc_id ?? null,
      duration_minutes: v.duration_minutes ?? null,
      notes: v.notes || null,
    };
    if (editing) updateMut.mutate({ id: editing.id, values: payload });
    else createMut.mutate(payload);
  };

  const today = dayjs();

  return (
    <div>
      <PageHeader
        title="Activity Log"
        subtitle={
          isRep
            ? 'Log your daily calls, meetings, and demos'
            : 'Review each sales rep’s daily activities'
        }
      />

      <Card variant="borderless" style={{ borderRadius: 12, marginBottom: 16 }}>
        <Space wrap size="middle" style={{ width: '100%', justifyContent: 'space-between', display: 'flex' }}>
          <Space wrap>
            <Button icon={<LeftOutlined />} onClick={() => setMonth((m) => m.subtract(1, 'month'))} />
            <DatePicker
              picker="month"
              value={month}
              allowClear={false}
              onChange={(m) => m && setMonth(m)}
              format="MMMM YYYY"
            />
            <Button
              icon={<RightOutlined />}
              onClick={() => setMonth((m) => m.add(1, 'month'))}
              disabled={month.isSame(today, 'month')}
            />
            {isAdmin && (
              <Select
                showSearch
                optionFilterProp="label"
                placeholder="Select a sales rep"
                style={{ minWidth: 220 }}
                value={repId}
                onChange={setRepId}
                options={(reps?.items ?? []).map((r) => ({ value: r.id, label: r.full_name }))}
              />
            )}
          </Space>
          {log && log.total_activities > 0 && (
            <Space size="large" wrap>
              {log.totals_by_type.map((t) => (
                <Statistic
                  key={t.activity_type}
                  title={TYPE_PLURALS[t.activity_type] ?? t.label}
                  value={t.count}
                  valueStyle={{ fontSize: 18 }}
                />
              ))}
              <Statistic title="Total" value={log.total_activities} valueStyle={{ fontSize: 18 }} />
              {log.total_duration_minutes > 0 && (
                <Statistic
                  title="Time Logged"
                  value={`${Math.floor(log.total_duration_minutes / 60)}h ${log.total_duration_minutes % 60}m`}
                  valueStyle={{ fontSize: 18 }}
                />
              )}
            </Space>
          )}
        </Space>
      </Card>

      {isAdmin && !repId ? (
        <Card variant="borderless" style={{ borderRadius: 12 }}>
          <Empty description="Select a sales rep to view their activity log" />
        </Card>
      ) : isLoading ? (
        <Card variant="borderless" style={{ borderRadius: 12 }}><Skeleton active /></Card>
      ) : (
        <>
          <Row gutter={[8, 8]}>
            {WEEKDAY_HEADERS.map((h) => (
              <Col key={h} flex="20%">
                <div style={{ textAlign: 'center', fontWeight: 600, padding: '4px 0' }}>
                  <Text type="secondary">{h}</Text>
                </div>
              </Col>
            ))}
          </Row>
          {weeks.map((week, wi) => (
            <Row gutter={[8, 8]} key={wi} style={{ marginBottom: 8 }}>
              {week.map((day, di) => {
                if (!day) {
                  return <Col key={di} flex="20%"><div /></Col>;
                }
                const key = day.format('YYYY-MM-DD');
                const items = byDate[key] ?? [];
                const isToday = day.isSame(today, 'day');
                const isFuture = day.isAfter(today, 'day');
                return (
                  <Col key={di} flex="20%">
                    <Card
                      size="small"
                      variant="borderless"
                      style={{
                        borderRadius: 10,
                        minHeight: 120,
                        background: isToday ? 'var(--ant-color-primary-bg, #eef1ff)' : undefined,
                        opacity: isFuture ? 0.55 : 1,
                      }}
                      styles={{ body: { padding: 8 } }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                        <Text strong={isToday}>{day.date()}</Text>
                        {isRep && !isFuture && (
                          <Button
                            type="text"
                            size="small"
                            icon={<PlusOutlined />}
                            onClick={() => openCreate(day)}
                          />
                        )}
                      </div>
                      <Space direction="vertical" size={4} style={{ width: '100%' }}>
                        {items.map((a) => (
                          <div
                            key={a.id}
                            style={{ display: 'flex', alignItems: 'center', gap: 4 }}
                          >
                            <Tooltip
                              title={[
                                a.customer_name && `Customer: ${a.customer_name}`,
                                a.opportunity_name && `Opportunity: ${a.opportunity_name}`,
                                a.duration_minutes && `Duration: ${a.duration_minutes} min`,
                                a.notes,
                              ].filter(Boolean).join('\n') || undefined}
                              styles={{ root: { whiteSpace: 'pre-line' } }}
                            >
                              <Tag
                                color={TYPE_COLORS[a.activity_type]}
                                style={{
                                  flex: 1, margin: 0, cursor: isRep ? 'pointer' : 'default',
                                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                                }}
                                onClick={isRep ? () => openEdit(a) : undefined}
                              >
                                {a.activity_type_label}
                                {a.customer_name ? ` · ${a.customer_name}` : a.opportunity_name ? ` · ${a.opportunity_name}` : ''}
                              </Tag>
                            </Tooltip>
                            {isRep && (
                              <Popconfirm
                                title="Delete this activity?"
                                onConfirm={() => deleteMut.mutate(a.id)}
                              >
                                <Button type="text" size="small" danger icon={<DeleteOutlined />} />
                              </Popconfirm>
                            )}
                          </div>
                        ))}
                      </Space>
                    </Card>
                  </Col>
                );
              })}
            </Row>
          ))}
          {log && log.total_activities === 0 && (
            <Card variant="borderless" style={{ borderRadius: 12, marginTop: 8 }}>
              <Empty
                description={
                  isRep
                    ? 'No activities logged this month yet — click + on a day to add one'
                    : `No activities logged by ${log.user_name ?? 'this rep'} in ${month.format('MMMM YYYY')}`
                }
              />
            </Card>
          )}
        </>
      )}

      <Modal
        title={editing ? 'Edit Activity' : 'Log Activity'}
        open={editorOpen}
        onCancel={closeEditor}
        onOk={() => form.submit()}
        confirmLoading={createMut.isPending || updateMut.isPending}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" onFinish={submit}>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="activity_date" label="Date" rules={[{ required: true }]}>
                <DatePicker
                  style={{ width: '100%' }}
                  disabledDate={(d) => d.isAfter(dayjs(), 'day') || [0, 6].includes(d.day())}
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="activity_type" label="Type" rules={[{ required: true }]}>
                <Select options={TYPE_OPTIONS} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={12}>
            <Col span={14}>
              <Form.Item name="customer_name" label="Customer / Contact">
                <Input prefix={<TeamOutlined />} placeholder="e.g. HUGO BANK" maxLength={255} />
              </Form.Item>
            </Col>
            <Col span={10}>
              <Form.Item name="duration_minutes" label="Duration (min)">
                <InputNumber min={1} max={1440} style={{ width: '100%' }} prefix={<PhoneOutlined />} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="opportunity_id" label="Related Opportunity (optional)">
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              placeholder="Link to one of your opportunities"
              options={(myOpps?.items ?? []).map((o) => ({ value: o.id, label: o.name }))}
            />
          </Form.Item>
          <Form.Item
            name="poc_id"
            label="Related POC (optional)"
            extra="Set this when the work was part of a POC — it is what makes the activity show up on that POC's log."
          >
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              placeholder="Link to a POC you're working on"
              options={(myPocs?.items ?? []).map((p) => ({
                value: p.id,
                label: `${p.customer_name ?? 'POC'}${
                  p.current_stage_label ? ` — ${p.current_stage_label}` : ''
                }`,
              }))}
            />
          </Form.Item>
          <Form.Item name="notes" label="Notes">
            <Input.TextArea rows={3} placeholder="What was discussed, outcomes, next steps…" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default ActivityLogPage;
