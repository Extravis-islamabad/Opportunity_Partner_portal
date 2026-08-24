import React, { useState } from 'react';
import { Descriptions, Card, Tag, Skeleton, Alert, Empty, Button, Space, Row, Col, Modal, Input, Select, Checkbox, Upload, List, message, Typography, Popconfirm } from 'antd';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { opportunitiesApi, aiApi } from '@/api/endpoints';
import { useAuth } from '@/contexts/AuthContext';
import PageHeader from '@/components/common/PageHeader';
import AIScoreBadge from '@/components/ai/AIScoreBadge';
import OpportunityPocPanel from '@/components/poc/OpportunityPocPanel';
import { StarFilled, WarningOutlined, UploadOutlined, FileOutlined, ThunderboltOutlined, ReloadOutlined, DeleteOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';

const statusColors: Record<string, string> = {
  draft: 'default', pending_review: 'orange', under_review: 'processing',
  approved: 'green', rejected: 'red', removed: 'default',
  won: 'success', lost: 'volcano',
};

const OpportunityDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const oppId = Number(id);
  const isAdmin = user?.role === 'admin';

  const [rejectModal, setRejectModal] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [approveModal, setApproveModal] = useState(false);
  const [preferredPartner, setPreferredPartner] = useState(false);
  const [noteModal, setNoteModal] = useState(false);
  const [noteText, setNoteText] = useState('');
  const [closeModal, setCloseModal] = useState<'won' | 'lost' | null>(null);
  const [lossReason, setLossReason] = useState<string | undefined>();
  const [lossNotes, setLossNotes] = useState('');
  const [releaseModal, setReleaseModal] = useState(false);
  const [releaseReason, setReleaseReason] = useState('');

  const { data: opp, isLoading, error } = useQuery({
    queryKey: ['opportunity', oppId],
    queryFn: async () => { const res = await opportunitiesApi.get(oppId); return res.data; },
  });

  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ['opportunity', oppId] });

  const submitMut = useMutation({ mutationFn: () => opportunitiesApi.submit(oppId), onSuccess: () => { invalidate(); void message.success('Submitted'); } });
  const approveMut = useMutation({
    mutationFn: () => opportunitiesApi.approve(oppId, preferredPartner),
    onSuccess: () => { setApproveModal(false); invalidate(); void message.success('Approved'); },
  });
  const rejectMut = useMutation({
    mutationFn: () => opportunitiesApi.reject(oppId, rejectReason),
    onSuccess: () => { setRejectModal(false); invalidate(); void message.success('Rejected'); },
  });
  const reviewMut = useMutation({ mutationFn: () => opportunitiesApi.markUnderReview(oppId), onSuccess: invalidate });
  const removeMut = useMutation({
    mutationFn: () => opportunitiesApi.remove(oppId),
    onSuccess: () => { void message.success('Removed'); navigate('/opportunities'); },
  });
  const noteMut = useMutation({
    mutationFn: () => opportunitiesApi.addNote(oppId, noteText),
    onSuccess: () => { setNoteModal(false); invalidate(); void message.success('Note added'); },
  });
  // Only fetched for the admin who can actually close something, and only
  // while the close dialog is open — the list is static, so once is enough.
  const { data: lossReasonOptions } = useQuery({
    queryKey: ['loss-reasons'],
    queryFn: async () => (await opportunitiesApi.lossReasons()).data,
    enabled: closeModal === 'lost',
    staleTime: Infinity,
  });

  const closeMut = useMutation({
    mutationFn: () => opportunitiesApi.close(oppId, {
      won: closeModal === 'won',
      ...(closeModal === 'lost'
        ? { loss_reason: lossReason, loss_notes: lossNotes.trim() || undefined }
        : {}),
    }),
    onSuccess: () => {
      const outcome = closeModal;
      setCloseModal(null);
      setLossReason(undefined);
      setLossNotes('');
      invalidate();
      void message.success(outcome === 'won' ? 'Recorded as won' : 'Recorded as lost');
    },
    onError: () => { void message.error('Could not record the outcome'); },
  });

  const releaseMut = useMutation({
    mutationFn: () => opportunitiesApi.releaseReview(oppId, releaseReason.trim() || undefined),
    onSuccess: () => {
      setReleaseModal(false);
      setReleaseReason('');
      invalidate();
      void message.success('Review released — back in the queue');
    },
    onError: () => { void message.error('Could not release the review'); },
  });

  const deleteDocMut = useMutation({
    mutationFn: (docId: number) => opportunitiesApi.deleteDocument(oppId, docId),
    onSuccess: () => { invalidate(); void message.success('Document deleted'); },
    onError: () => { void message.error('Could not delete the document'); },
  });

  const [summary, setSummary] = useState<string | null>(null);
  const summarizeMut = useMutation({
    mutationFn: () => aiApi.summarizeOpportunity(oppId),
    onSuccess: (res) => {
      setSummary(res.data.summary);
      void message.success(res.data.cached ? 'Summary loaded from cache' : 'Summary generated');
    },
    onError: () => { void message.error('Summarization unavailable'); },
  });
  const rescoreMut = useMutation({
    mutationFn: () => aiApi.rescoreOpportunity(oppId),
    onSuccess: () => { invalidate(); void message.success('AI score updated'); },
    onError: () => { void message.error('Rescoring unavailable'); },
  });

  if (error) return <Alert type="error" message="Failed to load opportunity" showIcon />;
  if (isLoading) return <Skeleton active paragraph={{ rows: 10 }} />;
  if (!opp) return <Empty description="Opportunity not found" />;

  const canEdit = !isAdmin && (opp.status === 'draft' || opp.status === 'rejected');
  const canSubmit = !isAdmin && (opp.status === 'draft' || opp.status === 'rejected');
  const canReview = isAdmin && opp.status === 'pending_review';
  const canApproveReject = isAdmin && (opp.status === 'pending_review' || opp.status === 'under_review');
  // Only an approved deal has an outcome to record; won and lost are terminal.
  const canClose = isAdmin && opp.status === 'approved';
  const canRelease = isAdmin && opp.status === 'under_review';
  const isClosed = opp.status === 'won' || opp.status === 'lost';

  return (
    <>
      <PageHeader
        title={opp.name}
        breadcrumbs={[{ label: 'Opportunities', path: '/opportunities' }, { label: opp.name }]}
        extra={
          <Space>
            {canEdit && <Button onClick={() => navigate(`/opportunities/${oppId}/edit`)}>Edit</Button>}
            {canSubmit && <Button type="primary" loading={submitMut.isPending} onClick={() => submitMut.mutate()}>Submit for Review</Button>}
            {canReview && <Button type="primary" loading={reviewMut.isPending} onClick={() => reviewMut.mutate()}>Mark Under Review</Button>}
            {canApproveReject && <Button type="primary" style={{ background: '#52c41a' }} onClick={() => setApproveModal(true)}>Approve</Button>}
            {canApproveReject && <Button danger onClick={() => setRejectModal(true)}>Reject</Button>}
            {canRelease && <Button onClick={() => setReleaseModal(true)}>Release Review</Button>}
            {canClose && <Button type="primary" onClick={() => setCloseModal('won')}>Mark Won</Button>}
            {canClose && <Button onClick={() => setCloseModal('lost')}>Mark Lost</Button>}
            {isAdmin && !isClosed && <Button danger onClick={() => { Modal.confirm({ title: 'Remove this opportunity?', onOk: () => removeMut.mutate() }); }}>Remove</Button>}
            {isAdmin && <Button onClick={() => setNoteModal(true)}>Add Note</Button>}
          </Space>
        }
      />

      {opp.multi_partner_alert && (
        <Alert type="warning" icon={<WarningOutlined />} message="Multi-Partner Alert"
          description="Another partner has already submitted an opportunity for this customer. Admins have been notified — this opportunity is in the duplicate review queue."
          showIcon style={{ marginBottom: 16 }}
          action={isAdmin && (
            <Button size="small" onClick={() => navigate('/opportunities/duplicates')}>Review Queue</Button>
          )}
        />
      )}

      {opp.ai_duplicate_of_id && (
        <Alert
          type="info"
          message="AI flagged a possible duplicate"
          description={
            <span>
              The AI scoring service believes this opportunity may be a duplicate of{' '}
              <a onClick={() => navigate(`/opportunities/${opp.ai_duplicate_of_id}`)}>opportunity #{opp.ai_duplicate_of_id}</a>.
              Review both side-by-side before making an approval decision.
            </span>
          }
          showIcon
          style={{ marginBottom: 16 }}
          action={isAdmin && (
            <Button size="small" onClick={() => navigate(`/opportunities/${opp.ai_duplicate_of_id}`)}>
              View match
            </Button>
          )}
        />
      )}

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={16}>
          <Card>
            <Descriptions bordered column={{ xs: 1, sm: 2 }} size="small">
              <Descriptions.Item label="Status">
                <Space><Tag color={statusColors[opp.status] ?? 'default'}>{opp.status.replace(/_/g, ' ').toUpperCase()}</Tag>
                  {opp.preferred_partner && <Tag color="gold" icon={<StarFilled />}>Preferred Partner</Tag>}
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label="Worth">${Number(opp.worth).toLocaleString()}</Descriptions.Item>
              <Descriptions.Item label="Customer">{opp.customer_name}</Descriptions.Item>
              <Descriptions.Item label="Company">{opp.company_name}</Descriptions.Item>
              <Descriptions.Item label="Region">{opp.region}</Descriptions.Item>
              <Descriptions.Item label="Country">{opp.country}</Descriptions.Item>
              <Descriptions.Item label="City">{opp.city}</Descriptions.Item>
              <Descriptions.Item label="Closing Date">{dayjs(opp.closing_date).format('MMM D, YYYY')}</Descriptions.Item>
              {opp.renewal_of_license_id && (
                <Descriptions.Item label="Type">
                  <Tag color="cyan" icon={<ReloadOutlined />}>Renewal</Tag>
                </Descriptions.Item>
              )}
              {opp.product && <Descriptions.Item label="Product"><Tag color="geekblue">{opp.product}</Tag></Descriptions.Item>}
              {opp.industry && <Descriptions.Item label="Industry">{opp.industry}</Descriptions.Item>}
              {opp.stage_probability && (
                <Descriptions.Item label="Stage">
                  <Tag color="purple">{Math.round(Number(opp.stage_probability) * 100)}%</Tag>
                </Descriptions.Item>
              )}
              {opp.time_frame && <Descriptions.Item label="Time Frame">{opp.time_frame}</Descriptions.Item>}
              {opp.sales_rep_name && <Descriptions.Item label="Sales Rep">{opp.sales_rep_name}</Descriptions.Item>}
              <Descriptions.Item label="Submitted By">{opp.submitted_by_name}</Descriptions.Item>
              {opp.submitted_at && <Descriptions.Item label="Submitted At">{dayjs(opp.submitted_at).format('MMM D, YYYY HH:mm')}</Descriptions.Item>}
              {opp.reviewer_name && <Descriptions.Item label="Reviewed By">{opp.reviewer_name}</Descriptions.Item>}
              {opp.reviewed_at && <Descriptions.Item label="Reviewed At">{dayjs(opp.reviewed_at).format('MMM D, YYYY HH:mm')}</Descriptions.Item>}
            </Descriptions>
          </Card>

          {isClosed && (
            <Card title="Outcome" style={{ marginTop: 16 }}>
              <Alert
                type={opp.status === 'won' ? 'success' : 'warning'}
                showIcon
                message={
                  opp.status === 'won'
                    ? 'Closed as won'
                    : `Closed as lost — ${opp.loss_reason_label ?? 'reason not recorded'}`
                }
                description={
                  <Space direction="vertical" size={4}>
                    {opp.closed_outcome_at && (
                      <span>Recorded {dayjs(opp.closed_outcome_at).format('MMM D, YYYY HH:mm')}</span>
                    )}
                    {opp.loss_notes && (
                      <Typography.Text style={{ whiteSpace: 'pre-wrap' }}>{opp.loss_notes}</Typography.Text>
                    )}
                  </Space>
                }
              />
            </Card>
          )}

          <Card title="Requirements" style={{ marginTop: 16 }}>
            <Typography.Paragraph style={{ whiteSpace: 'pre-wrap' }}>{opp.requirements}</Typography.Paragraph>
          </Card>

          <OpportunityPocPanel opportunityId={opp.id} />

          {opp.rejection_reason && (
            <Card title="Rejection Reason" style={{ marginTop: 16 }}>
              <Alert type="error" message={opp.rejection_reason} />
            </Card>
          )}

          {isAdmin && opp.internal_notes && (
            <Card title="Internal Notes (Admin Only)" style={{ marginTop: 16 }}>
              <Typography.Paragraph style={{ whiteSpace: 'pre-wrap' }}>{opp.internal_notes}</Typography.Paragraph>
            </Card>
          )}

          <Card
            title={
              <Space>
                <ThunderboltOutlined style={{ color: '#faad14' }} />
                AI Insights
              </Space>
            }
            style={{ marginTop: 16 }}
            extra={
              isAdmin && (
                <Space>
                  <Button
                    size="small"
                    icon={<ReloadOutlined />}
                    loading={rescoreMut.isPending}
                    onClick={() => rescoreMut.mutate()}
                  >
                    Re-score
                  </Button>
                  <Button
                    size="small"
                    type="primary"
                    icon={<ThunderboltOutlined />}
                    loading={summarizeMut.isPending}
                    onClick={() => summarizeMut.mutate()}
                  >
                    Summarize
                  </Button>
                </Space>
              )
            }
          >
            <Space direction="vertical" style={{ width: '100%' }}>
              <Space align="center">
                <AIScoreBadge score={opp.ai_score} />
                {opp.ai_scored_at && (
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    scored {dayjs(opp.ai_scored_at).format('MMM D, YYYY')}
                  </Typography.Text>
                )}
              </Space>
              {opp.ai_reasoning && (
                <Typography.Paragraph type="secondary" style={{ marginBottom: 0, fontSize: 13 }}>
                  {opp.ai_reasoning}
                </Typography.Paragraph>
              )}
              {opp.ai_duplicate_of_id && (
                <Alert
                  type="warning"
                  showIcon
                  message="Possible duplicate detected"
                  description={
                    <span>
                      This opportunity may be a duplicate of{' '}
                      <a onClick={() => navigate(`/opportunities/${opp.ai_duplicate_of_id}`)}>
                        opportunity #{opp.ai_duplicate_of_id}
                      </a>.
                    </span>
                  }
                />
              )}
              {summary && (
                <Alert
                  type="info"
                  showIcon
                  message="AI Summary"
                  description={<div style={{ whiteSpace: 'pre-wrap' }}>{summary}</div>}
                />
              )}
              {!opp.ai_score && !opp.ai_reasoning && (
                <Typography.Text type="secondary">
                  AI scoring runs automatically when an opportunity is submitted for review.
                </Typography.Text>
              )}
            </Space>
          </Card>
        </Col>

        <Col xs={24} lg={8}>
          <Card title="Documents">
            {opp.documents.length > 0 ? (
              <List dataSource={opp.documents} renderItem={(doc) => (
                <List.Item
                  actions={
                    (canEdit || opp.status === 'draft')
                      ? [
                          <Popconfirm
                            key="del"
                            title="Delete this document?"
                            okText="Delete"
                            okButtonProps={{ danger: true }}
                            onConfirm={() => deleteDocMut.mutate(doc.id)}
                          >
                            <Button type="text" danger size="small" icon={<DeleteOutlined />} loading={deleteDocMut.isPending} />
                          </Popconfirm>,
                        ]
                      : undefined
                  }
                >
                  {doc.file_url ? (
                    <a href={doc.file_url} target="_blank" rel="noopener noreferrer">
                      <FileOutlined style={{ marginRight: 8 }} />{doc.file_name}
                    </a>
                  ) : (
                    <span><FileOutlined style={{ marginRight: 8 }} />{doc.file_name}</span>
                  )}
                </List.Item>
              )} />
            ) : <Empty description="No documents" image={Empty.PRESENTED_IMAGE_SIMPLE} />}
            {(canEdit || opp.status === 'draft') && (
              <Upload
                customRequest={async ({ file, onSuccess, onError }) => {
                  try {
                    await opportunitiesApi.uploadDocument(oppId, file as File);
                    invalidate();
                    onSuccess?.(null);
                    void message.success('Document uploaded');
                  } catch (e) { onError?.(e as Error); }
                }}
                showUploadList={false}
              >
                <Button icon={<UploadOutlined />} style={{ marginTop: 8 }}>Upload Document</Button>
              </Upload>
            )}
          </Card>
        </Col>
      </Row>

      <Modal title="Approve Opportunity" open={approveModal} onCancel={() => setApproveModal(false)}
        onOk={() => approveMut.mutate()} confirmLoading={approveMut.isPending}>
        <Checkbox checked={preferredPartner} onChange={(e) => setPreferredPartner(e.target.checked)}>
          Tag as Preferred Partner
        </Checkbox>
      </Modal>

      <Modal title="Reject Opportunity" open={rejectModal} onCancel={() => setRejectModal(false)}
        onOk={() => rejectMut.mutate()} confirmLoading={rejectMut.isPending}
        okButtonProps={{ disabled: !rejectReason.trim() }}>
        <Input.TextArea rows={4} placeholder="Rejection reason (required)" value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} maxLength={1000} showCount />
      </Modal>

      <Modal
        title={closeModal === 'won' ? 'Mark as Won' : 'Mark as Lost'}
        open={closeModal !== null}
        onCancel={() => setCloseModal(null)}
        onOk={() => closeMut.mutate()}
        confirmLoading={closeMut.isPending}
        okText={closeModal === 'won' ? 'Mark Won' : 'Mark Lost'}
        okButtonProps={{ disabled: closeModal === 'lost' && !lossReason }}
      >
        {closeModal === 'won' ? (
          <Typography.Paragraph>
            This is final: a closed deal cannot be reopened or closed again. It stays
            in the partner&apos;s approved total and counts towards their tier.
          </Typography.Paragraph>
        ) : (
          <Space direction="vertical" style={{ width: '100%' }}>
            <Typography.Paragraph style={{ marginBottom: 0 }}>
              This is final, and it removes the deal from the partner&apos;s approved
              total. A reason is required so losses can be counted.
            </Typography.Paragraph>
            <Select
              placeholder="Reason (required)"
              style={{ width: '100%' }}
              value={lossReason}
              onChange={setLossReason}
              options={(lossReasonOptions ?? []).map((o) => ({ value: o.value, label: o.label }))}
            />
            <Input.TextArea
              rows={3}
              placeholder="Notes (optional)"
              value={lossNotes}
              onChange={(e) => setLossNotes(e.target.value)}
              maxLength={2000}
              showCount
            />
          </Space>
        )}
      </Modal>

      <Modal title="Release Review" open={releaseModal} onCancel={() => setReleaseModal(false)}
        onOk={() => releaseMut.mutate()} confirmLoading={releaseMut.isPending} okText="Release">
        <Space direction="vertical" style={{ width: '100%' }}>
          <Typography.Paragraph style={{ marginBottom: 0 }}>
            The opportunity goes back to pending review, loses its reviewer, and the
            partner can edit it again. Use this when a claimed review has stalled.
          </Typography.Paragraph>
          <Input.TextArea rows={3} placeholder="Reason (optional — shown to the previous reviewer)"
            value={releaseReason} onChange={(e) => setReleaseReason(e.target.value)} maxLength={500} />
        </Space>
      </Modal>

      <Modal title="Add Internal Note" open={noteModal} onCancel={() => setNoteModal(false)}
        onOk={() => noteMut.mutate()} confirmLoading={noteMut.isPending}
        okButtonProps={{ disabled: !noteText.trim() }}>
        <Input.TextArea rows={4} placeholder="Internal note..." value={noteText} onChange={(e) => setNoteText(e.target.value)} />
      </Modal>
    </>
  );
};

export default OpportunityDetailPage;
