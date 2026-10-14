/**
 * Sales activity log.
 *
 * A Monday–Sunday month grid of a rep's daily activities (calls, meetings,
 * demos, …). Sales reps log/edit/delete their own entries by clicking a day,
 * and can attach a follow-up reminder that arrives as a notification; admins
 * pick any rep and review the same grid read-only, with monthly totals by
 * activity type.
 */
import React, { useMemo, useState } from 'react';
import {
  Card, Row, Col, Select, Button, Modal, Form, DatePicker, Input,
  Tag, Tooltip, Typography, Space, Statistic, Empty, Popconfirm, message, Skeleton,
  List, theme,
} from 'antd';
import {
  PlusOutlined, LeftOutlined, RightOutlined, BellOutlined,
  TeamOutlined, DeleteOutlined, ShopOutlined,
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
  { value: 'deployment', label: 'Deployment' },
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
  deployment: 'Deployments',
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
  deployment: 'magenta',
  other: 'default',
};

const WEEKDAY_HEADERS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

// Seven equal columns. Below ~840px the grid scrolls sideways inside its own
// container rather than squeezing a day to an unreadable sliver.
const GRID_STYLE: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(7, minmax(0, 1fr))',
  gap: 8,
  minWidth: 840,
};

/** Every date of the month, grouped into Monday-first calendar weeks. Cells
 * outside the month are null so week rows stay aligned. */
function buildWeeks(month: Dayjs): Array<Array<Dayjs | null>> {
  const first = month.startOf('month');
  const last = month.endOf('month');
  // dayjs: .day() is 0=Sunday..6=Saturday; shift to Monday-based.
  const mondayOffset = (first.day() + 6) % 7;
  let cursor = first.subtract(mondayOffset, 'day'); // the Monday of week 1
  const weeks: Array<Array<Dayjs | null>> = [];
  while (cursor.isBefore(last) || cursor.isSame(last, 'day')) {
    const week: Array<Dayjs | null> = [];
    for (let i = 0; i < 7; i++) {
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
  const { token } = theme.useToken();
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

  const { data: reminders } = useQuery({
    queryKey: ['activity-reminders'],
    queryFn: async () => (await activitiesApi.reminders()).data,
    enabled: isRep,
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

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['activity-month'] });
    void queryClient.invalidateQueries({ queryKey: ['activity-reminders'] });
  };
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
      partner_name: undefined,
      opportunity_id: undefined,
      poc_id: undefined,
      notes: undefined,
      reminder_at: undefined,
      reminder_note: undefined,
    });
    setEditorOpen(true);
  };

  const openEdit = (a: ActivityResponse) => {
    setEditing(a);
    form.setFieldsValue({
      activity_date: dayjs(a.activity_date),
      activity_type: a.activity_type,
      customer_name: a.customer_name ?? undefined,
      partner_name: a.partner_name ?? undefined,
      opportunity_id: a.opportunity_id ?? undefined,
      poc_id: a.poc_id ?? undefined,
      notes: a.notes ?? undefined,
      reminder_at: a.reminder_at ? dayjs(a.reminder_at) : undefined,
      reminder_note: a.reminder_note ?? undefined,
    });
    setEditorOpen(true);
  };

  const closeEditor = () => { setEditorOpen(false); setEditing(null); form.resetFields(); };

  const submit = (v: {
    activity_date: Dayjs; activity_type: ActivityType;
    customer_name?: string; partner_name?: string; opportunity_id?: number; poc_id?: number;
    notes?: string; reminder_at?: Dayjs | null; reminder_note?: string;
  }) => {
    const payload = {
      activity_date: v.activity_date.format('YYYY-MM-DD'),
      activity_type: v.activity_type,
      customer_name: v.customer_name || null,
      partner_name: v.partner_name || null,
      opportunity_id: v.opportunity_id ?? null,
      poc_id: v.poc_id ?? null,
      notes: v.notes || null,
      // Sent as an absolute instant, so the server fires it at the moment the
      // rep picked in their own timezone.
      reminder_at: v.reminder_at ? v.reminder_at.toISOString() : null,
      reminder_note: v.reminder_at ? v.reminder_note || null : null,
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
          <div style={{ overflowX: 'auto', paddingBottom: 4 }}>
            <div style={GRID_STYLE}>
              {WEEKDAY_HEADERS.map((h, i) => (
                <div key={h} style={{ textAlign: 'center', fontWeight: 600, padding: '4px 0' }}>
                  <Text type={i >= 5 ? undefined : 'secondary'} style={i >= 5 ? { color: token.colorTextTertiary } : undefined}>
                    {h}
                  </Text>
                </div>
              ))}
              {weeks.flat().map((day, idx) => {
                if (!day) {
                  return <div key={`blank-${idx}`} />;
                }
                const key = day.format('YYYY-MM-DD');
                const items = byDate[key] ?? [];
                const isToday = day.isSame(today, 'day');
                const isFuture = day.isAfter(today, 'day');
                const isWeekend = day.day() === 0 || day.day() === 6;
                return (
                  <Card
                    key={key}
                    size="small"
                    variant="borderless"
                    style={{
                      borderRadius: 10,
                      minHeight: 120,
                      // A border on every day: in dark mode the card and the
                      // page are the same colour, so without one the grid
                      // had no visible cells.
                      border: `1px solid ${isToday ? token.colorPrimaryBorder : token.colorBorderSecondary}`,
                      background: isToday
                        ? token.colorPrimaryBg
                        : isWeekend
                          ? token.colorFillTertiary
                          : token.colorBgContainer,
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
                          aria-label={`Log activity on ${day.format('D MMMM')}`}
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
                              a.customer_name && `Client / Contact: ${a.customer_name}`,
                              a.partner_name && `Partner: ${a.partner_name}`,
                              a.opportunity_name && `Opportunity: ${a.opportunity_name}`,
                              a.duration_minutes && `Duration: ${a.duration_minutes} min`,
                              a.reminder_at && `Reminder: ${dayjs(a.reminder_at).format('D MMM YYYY, h:mm A')}${a.reminder_sent_at ? ' (sent)' : ''}`,
                              a.notes,
                            ].filter(Boolean).join('\n') || undefined}
                            styles={{ root: { whiteSpace: 'pre-line' } }}
                          >
                            <Tag
                              color={TYPE_COLORS[a.activity_type]}
                              icon={a.reminder_at && !a.reminder_sent_at ? <BellOutlined /> : undefined}
                              style={{
                                flex: 1, minWidth: 0, margin: 0, cursor: isRep ? 'pointer' : 'default',
                                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                              }}
                              onClick={isRep ? () => openEdit(a) : undefined}
                            >
                              {a.activity_type_label}
                              {a.customer_name ? ` · ${a.customer_name}` : a.partner_name ? ` · ${a.partner_name}` : a.opportunity_name ? ` · ${a.opportunity_name}` : ''}
                            </Tag>
                          </Tooltip>
                          {isRep && (
                            <Popconfirm
                              title="Delete this activity?"
                              onConfirm={() => deleteMut.mutate(a.id)}
                            >
                              <Button type="text" size="small" danger icon={<DeleteOutlined />} aria-label="Delete activity" />
                            </Popconfirm>
                          )}
                        </div>
                      ))}
                    </Space>
                  </Card>
                );
              })}
            </div>
          </div>
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
          {isRep && reminders && reminders.length > 0 && (
            <Card
              variant="borderless"
              style={{ borderRadius: 12, marginTop: 16 }}
              title={<Space><BellOutlined />Upcoming reminders</Space>}
            >
              <List
                size="small"
                dataSource={reminders}
                renderItem={(r) => (
                  <List.Item
                    actions={[
                      <Button key="open" type="link" size="small" onClick={() => openEdit(r)}>Edit</Button>,
                    ]}
                  >
                    <List.Item.Meta
                      title={
                        <Space wrap size={6}>
                          <Text strong>{dayjs(r.reminder_at).format('ddd D MMM YYYY, h:mm A')}</Text>
                          <Tag color={TYPE_COLORS[r.activity_type]}>{r.activity_type_label}</Tag>
                          {r.customer_name && <Text type="secondary">{r.customer_name}</Text>}
                          {r.partner_name && <Text type="secondary">· {r.partner_name}</Text>}
                        </Space>
                      }
                      description={r.reminder_note || `Follow up on the ${dayjs(r.activity_date).format('D MMM')} ${r.activity_type_label.toLowerCase()}`}
                    />
                  </List.Item>
                )}
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
                  disabledDate={(d) => d.isAfter(dayjs(), 'day')}
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
            <Col xs={24} sm={12}>
              <Form.Item name="partner_name" label="Partner Name">
                <Input prefix={<ShopOutlined />} placeholder="e.g. NetSoft" maxLength={255} />
              </Form.Item>
            </Col>
            <Col xs={24} sm={12}>
              <Form.Item name="customer_name" label="Client Name / Contact Name">
                <Input prefix={<TeamOutlined />} placeholder="e.g. HUGO BANK / Ali Khan" maxLength={255} />
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
          <Form.Item
            name="reminder_at"
            label="Set Reminder (date & time)"
            extra="Optional. You'll get a notification and an email at this time."
            rules={[
              {
                validator: (_, v?: Dayjs | null) =>
                  !v || v.isAfter(dayjs())
                    ? Promise.resolve()
                    : Promise.reject(new Error('Pick a time in the future')),
              },
            ]}
          >
            <DatePicker
              showTime={{ format: 'h:mm A', use12Hours: true, minuteStep: 5 }}
              format="D MMM YYYY, h:mm A"
              style={{ width: '100%' }}
              disabledDate={(d) => d.isBefore(dayjs(), 'day')}
              placeholder="No reminder"
            />
          </Form.Item>
          <Form.Item noStyle shouldUpdate={(prev, cur) => prev.reminder_at !== cur.reminder_at}>
            {({ getFieldValue }) =>
              getFieldValue('reminder_at') ? (
                <Form.Item name="reminder_note" label="Reminder">
                  <Input.TextArea rows={2} maxLength={2000} placeholder="What to follow up on, e.g. send revised quote" />
                </Form.Item>
              ) : null
            }
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default ActivityLogPage;
