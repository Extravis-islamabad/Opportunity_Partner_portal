import React, { useEffect, useMemo, useState } from 'react';
import {
  Layout,
  Card,
  Button,
  Typography,
  Tag,
  Empty,
  Skeleton,
  Alert,
  Progress,
  Space,
  message,
  Modal,
  Form,
  Input,
  Select,
  InputNumber,
  Radio,
  Result,
} from 'antd';
import {
  PlayCircleOutlined,
  FilePdfOutlined,
  FileTextOutlined,
  QuestionCircleOutlined,
  CheckCircleFilled,
  CheckCircleOutlined,
  ArrowLeftOutlined,
  ArrowRightOutlined,
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  TrophyOutlined,
  DownloadOutlined,
} from '@ant-design/icons';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { lmsApi } from '@/api/endpoints';
import { useAuth } from '@/contexts/AuthContext';
import PageHeader from '@/components/common/PageHeader';
import type { CourseModule, CourseModuleType, EnrollmentResponse, QuizQuestion } from '@/types';

const BRAND = {
  royal500: '#3750ed',
  royal400: '#4961f1',
  royal100: '#b4b6f7',
  royal50: '#e7e7f1',
  navy: '#1c1c3a',
  violet500: '#a064f3',
  violet600: '#7a2280',
  violet100: '#f0e6ff',
};

const moduleIcon = (type: CourseModuleType): React.ReactNode => {
  switch (type) {
    case 'video': return <PlayCircleOutlined />;
    case 'pdf':   return <FilePdfOutlined />;
    case 'quiz':  return <QuestionCircleOutlined />;
    default:      return <FileTextOutlined />;
  }
};

// ---------------------------------------------------------------------------
// Video player — supports YouTube, Vimeo, and direct .mp4 URLs
// ---------------------------------------------------------------------------
const VideoPlayer: React.FC<{ url: string }> = ({ url }) => {
  const youtubeId = useMemo(() => {
    const m = url.match(/(?:youtube\.com\/(?:watch\?v=|embed\/)|youtu\.be\/)([\w-]{11})/);
    return m ? m[1] : null;
  }, [url]);

  const vimeoId = useMemo(() => {
    const m = url.match(/vimeo\.com\/(?:video\/)?(\d+)/);
    return m ? m[1] : null;
  }, [url]);

  if (youtubeId) {
    return (
      <div style={{ position: 'relative', paddingBottom: '56.25%', height: 0, borderRadius: 12, overflow: 'hidden', background: '#000' }}>
        <iframe
          src={`https://www.youtube.com/embed/${youtubeId}?rel=0&modestbranding=1`}
          title="Video lesson"
          frameBorder={0}
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
          allowFullScreen
          style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%' }}
        />
      </div>
    );
  }

  if (vimeoId) {
    return (
      <div style={{ position: 'relative', paddingBottom: '56.25%', height: 0, borderRadius: 12, overflow: 'hidden', background: '#000' }}>
        <iframe
          src={`https://player.vimeo.com/video/${vimeoId}`}
          title="Video lesson"
          frameBorder={0}
          allow="autoplay; fullscreen; picture-in-picture"
          allowFullScreen
          style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%' }}
        />
      </div>
    );
  }

  // Direct video file
  return (
    <video
      controls
      style={{ width: '100%', borderRadius: 12, background: '#000', maxHeight: 480 }}
    >
      <source src={url} />
      Your browser does not support the video tag.
    </video>
  );
};

// ---------------------------------------------------------------------------
// Quiz taker
// ---------------------------------------------------------------------------
interface QuizTakerProps {
  questions: QuizQuestion[];
  enrollmentId: number;
  onPass: () => void;
}

const QuizTaker: React.FC<QuizTakerProps> = ({ questions, enrollmentId, onPass }) => {
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [result, setResult] = useState<{ score: number; passed: boolean; passing_score: number } | null>(null);
  const queryClient = useQueryClient();

  const submitMut = useMutation({
    mutationFn: () => lmsApi.submitAssessment(enrollmentId, answers),
    onSuccess: (res) => {
      setResult(res.data);
      void queryClient.invalidateQueries({ queryKey: ['my-enrollments'] });
      if (res.data.passed) {
        void message.success(`Passed with ${res.data.score}%! Certificate issued.`);
        setTimeout(() => onPass(), 1500);
      } else {
        void message.warning(`Scored ${res.data.score}% — passing score is ${res.data.passing_score}%`);
      }
    },
    onError: () => void message.error('Failed to submit quiz'),
  });

  const allAnswered = questions.every((q) => answers[String(q.id)] !== undefined);

  if (result) {
    return (
      <Result
        status={result.passed ? 'success' : 'warning'}
        icon={result.passed ? <CheckCircleFilled style={{ color: '#10b981' }} /> : undefined}
        title={result.passed ? `Passed with ${result.score}%` : `Scored ${result.score}%`}
        subTitle={result.passed
          ? 'Your certificate has been issued. Refreshing course state…'
          : `You need ${result.passing_score}% to pass. Try again whenever you are ready.`}
        extra={
          !result.passed && (
            <Button
              type="primary"
              onClick={() => {
                setResult(null);
                setAnswers({});
              }}
            >
              Retake quiz
            </Button>
          )
        }
      />
    );
  }

  return (
    <div>
      {questions.map((q, idx) => (
        <Card
          key={q.id}
          style={{ marginBottom: 14, borderRadius: 10 }}
          styles={{ body: { padding: 18 } }}
        >
          <Typography.Text strong style={{ display: 'block', marginBottom: 12, color: BRAND.navy }}>
            {idx + 1}. {q.question}
          </Typography.Text>
          <Radio.Group
            value={answers[String(q.id)]}
            onChange={(e) => setAnswers((prev) => ({ ...prev, [String(q.id)]: e.target.value }))}
          >
            <Space direction="vertical">
              {q.options.map((opt, i) => (
                <Radio key={i} value={i}>{opt}</Radio>
              ))}
            </Space>
          </Radio.Group>
        </Card>
      ))}
      <div style={{ textAlign: 'right', marginTop: 8 }}>
        <Button
          type="primary"
          size="large"
          disabled={!allAnswered}
          loading={submitMut.isPending}
          onClick={() => submitMut.mutate()}
          icon={<CheckCircleOutlined />}
        >
          Submit Quiz
        </Button>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Module editor modal (admin only)
// ---------------------------------------------------------------------------
interface ModuleEditorProps {
  open: boolean;
  initial?: CourseModule;
  onCancel: () => void;
  onSave: (m: CourseModule) => void;
}

const ModuleEditorModal: React.FC<ModuleEditorProps> = ({ open, initial, onCancel, onSave }) => {
  const [form] = Form.useForm();
  useEffect(() => {
    if (open) {
      form.setFieldsValue(initial ?? { type: 'video', order: 0 });
    }
  }, [open, initial, form]);

  return (
    <Modal
      title={initial?.id ? 'Edit lesson' : 'Add lesson'}
      open={open}
      onCancel={onCancel}
      onOk={() => form.submit()}
      destroyOnClose
    >
      <Form
        form={form}
        layout="vertical"
        onFinish={(values) => {
          onSave({
            id: initial?.id || `m_${Date.now().toString(36)}`,
            order: values.order ?? 0,
            title: values.title,
            type: values.type,
            content_url: values.content_url ?? null,
            description: values.description ?? null,
            duration_minutes: values.duration_minutes ?? null,
          });
        }}
      >
        <Form.Item name="title" label="Lesson title" rules={[{ required: true }]}>
          <Input placeholder="e.g. Introduction to the platform" />
        </Form.Item>
        <Form.Item name="type" label="Lesson type" rules={[{ required: true }]}>
          <Select
            options={[
              { value: 'video', label: 'Video (YouTube / Vimeo / .mp4)' },
              { value: 'pdf',   label: 'PDF / Slides' },
              { value: 'text',  label: 'Text / Reading' },
              { value: 'quiz',  label: 'Quiz (uses course assessment)' },
            ]}
          />
        </Form.Item>
        <Form.Item
          noStyle
          shouldUpdate={(prev, curr) => prev.type !== curr.type}
        >
          {({ getFieldValue }) => {
            const type = getFieldValue('type');
            if (type === 'quiz') return null;
            return (
              <Form.Item
                name="content_url"
                label={type === 'video' ? 'Video URL' : type === 'pdf' ? 'PDF URL' : 'Reference URL (optional)'}
              >
                <Input placeholder={
                  type === 'video' ? 'https://www.youtube.com/watch?v=…'
                  : type === 'pdf' ? 'https://example.com/slides.pdf'
                  : 'optional'
                } />
              </Form.Item>
            );
          }}
        </Form.Item>
        <Form.Item name="description" label="Description / notes">
          <Input.TextArea rows={3} placeholder="Optional summary or text content shown alongside the lesson" />
        </Form.Item>
        <Space>
          <Form.Item name="duration_minutes" label="Duration (min)">
            <InputNumber min={1} />
          </Form.Item>
          <Form.Item name="order" label="Order">
            <InputNumber min={0} />
          </Form.Item>
        </Space>
      </Form>
    </Modal>
  );
};

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
const CourseDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const courseId = Number(id);
  const navigate = useNavigate();
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const queryClient = useQueryClient();

  const { data: course, isLoading } = useQuery({
    queryKey: ['lms-course', courseId],
    queryFn: async () => (await lmsApi.getCourse(courseId)).data,
    enabled: !!courseId,
  });

  const { data: myEnrollments } = useQuery({
    queryKey: ['my-enrollments'],
    queryFn: async () => (await lmsApi.getMyEnrollments()).data,
    enabled: !isAdmin,
  });

  const enrollment: EnrollmentResponse | undefined = useMemo(
    () => myEnrollments?.find((e) => e.course_id === courseId),
    [myEnrollments, courseId],
  );

  // Local state for selected lesson + module editor
  const [activeIndex, setActiveIndex] = useState(0);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editing, setEditing] = useState<CourseModule | undefined>();

  const sortedModules: CourseModule[] = useMemo(() => {
    if (!course?.modules_json) return [];
    return [...(course.modules_json as CourseModule[])].sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
  }, [course]);

  const activeModule = sortedModules[activeIndex];

  const completedSet = useMemo(() => {
    const map = enrollment?.progress_json ?? {};
    return new Set(Object.keys(map).filter((k) => map[k]));
  }, [enrollment]);

  // Quiz questions live on course.assessment_json. Hoisted above early returns
  // so the hook order stays stable across renders (React Rules of Hooks).
  const quizQuestions: QuizQuestion[] = useMemo(() => {
    const raw = (course as unknown as { assessment_json?: QuizQuestion[] })?.assessment_json ?? [];
    return raw.map((q) => ({
      ...q,
      correct_answer: q.correct_answer ?? q.correct,
    }));
  }, [course]);

  const completionPct = sortedModules.length > 0
    ? Math.round((completedSet.size / sortedModules.length) * 100)
    : 0;

  const enrollMut = useMutation({
    mutationFn: () => lmsApi.enroll(courseId),
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['my-enrollments'] }); void message.success('Enrolled'); },
    onError: () => void message.error('Failed to enroll'),
  });

  const markDoneMut = useMutation({
    mutationFn: (moduleId: string) => lmsApi.markModuleProgress(enrollment!.id, moduleId),
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['my-enrollments'] }); },
  });

  // Admin: persist module list back to the course
  const saveCourseMut = useMutation({
    mutationFn: (modules: CourseModule[]) =>
      lmsApi.updateCourse(courseId, { modules_json: modules }),
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ['lms-course', courseId] }); void message.success('Course updated'); },
    onError: () => void message.error('Failed to save course'),
  });

  const handleSaveModule = (m: CourseModule) => {
    const exists = sortedModules.find((x) => x.id === m.id);
    const next = exists
      ? sortedModules.map((x) => (x.id === m.id ? m : x))
      : [...sortedModules, m];
    next.forEach((x, i) => { x.order = i; });
    saveCourseMut.mutate(next);
    setEditorOpen(false);
    setEditing(undefined);
  };

  const handleDeleteModule = (mid: string) => {
    Modal.confirm({
      title: 'Delete this lesson?',
      content: 'This cannot be undone.',
      okType: 'danger',
      onOk: () => {
        const next = sortedModules.filter((x) => x.id !== mid);
        next.forEach((x, i) => { x.order = i; });
        saveCourseMut.mutate(next);
      },
    });
  };

  const goPrev = () => setActiveIndex((i) => Math.max(0, i - 1));
  const goNext = () => setActiveIndex((i) => Math.min(sortedModules.length - 1, i + 1));

  const handleMarkComplete = () => {
    if (!enrollment || !activeModule) return;
    markDoneMut.mutate(activeModule.id, {
      onSuccess: () => {
        void message.success('Lesson marked complete');
        if (activeIndex < sortedModules.length - 1) {
          setActiveIndex((i) => i + 1);
        }
      },
    });
  };

  if (isLoading) {
    return (
      <>
        <PageHeader title="Loading…" />
        <Skeleton active paragraph={{ rows: 12 }} />
      </>
    );
  }
  if (!course) return <Empty description="Course not found" />;

  return (
    <>
      <PageHeader
        title={course.title}
        breadcrumbs={[
          { label: 'Training', path: '/lms' },
          { label: course.title },
        ]}
        extra={
          <Space>
            {isAdmin && (
              <Button
                icon={<PlusOutlined />}
                onClick={() => { setEditing(undefined); setEditorOpen(true); }}
              >
                Add lesson
              </Button>
            )}
            {!isAdmin && !enrollment && (
              <Button type="primary" icon={<PlayCircleOutlined />} loading={enrollMut.isPending} onClick={() => enrollMut.mutate()}>
                Enroll
              </Button>
            )}
            {!isAdmin && enrollment?.certificate_url && (
              <Button
                type="primary"
                icon={<DownloadOutlined />}
                href={enrollment.certificate_url}
                target="_blank"
                style={{ background: BRAND.violet500, borderColor: BRAND.violet500 }}
              >
                Download Certificate
              </Button>
            )}
          </Space>
        }
      />

      {course.description && (
        <Alert
          type="info"
          showIcon={false}
          message={course.description}
          style={{ marginBottom: 16, borderRadius: 10, background: BRAND.royal50, border: `1px solid ${BRAND.royal100}` }}
        />
      )}

      {!isAdmin && enrollment && (
        <Card style={{ marginBottom: 16, borderRadius: 10 }} styles={{ body: { padding: 16 } }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <Typography.Text strong>Course Progress</Typography.Text>
            <Typography.Text type="secondary">
              {completedSet.size} / {sortedModules.length} lessons
              {enrollment.status === 'completed' && (
                <Tag color="green" style={{ marginLeft: 8 }}><TrophyOutlined /> Completed</Tag>
              )}
            </Typography.Text>
          </div>
          <Progress
            percent={completionPct}
            strokeColor={{ '0%': BRAND.royal400, '100%': BRAND.violet500 }}
            showInfo={false}
            strokeWidth={10}
          />
        </Card>
      )}

      <Layout style={{ background: 'transparent', gap: 16 }}>
        {/* Sidebar — lesson list */}
        <Layout.Sider
          width={300}
          style={{
            background: '#ffffff',
            borderRadius: 12,
            padding: 12,
            border: `1px solid ${BRAND.royal50}`,
            marginRight: 16,
          }}
          breakpoint="lg"
          collapsedWidth={0}
        >
          <Typography.Text strong style={{ display: 'block', marginBottom: 12, color: BRAND.navy, fontSize: 13, textTransform: 'uppercase', letterSpacing: 0.5 }}>
            Lessons ({sortedModules.length})
          </Typography.Text>
          {sortedModules.length === 0 ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No lessons yet" />
          ) : (
            sortedModules.map((m, idx) => {
              const isActive = idx === activeIndex;
              const isDone = completedSet.has(m.id);
              return (
                <div
                  key={m.id}
                  onClick={() => setActiveIndex(idx)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 10,
                    padding: '10px 12px',
                    borderRadius: 8,
                    cursor: 'pointer',
                    marginBottom: 4,
                    background: isActive ? BRAND.royal50 : 'transparent',
                    borderLeft: isActive ? `3px solid ${BRAND.royal500}` : '3px solid transparent',
                    transition: 'background 0.15s',
                  }}
                  onMouseEnter={(e) => { if (!isActive) e.currentTarget.style.background = '#fafafa'; }}
                  onMouseLeave={(e) => { if (!isActive) e.currentTarget.style.background = 'transparent'; }}
                >
                  <span style={{ fontSize: 18, color: isDone ? '#10b981' : isActive ? BRAND.royal500 : '#9ca3af', flexShrink: 0 }}>
                    {isDone ? <CheckCircleFilled /> : moduleIcon(m.type)}
                  </span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: isActive ? 600 : 500, color: BRAND.navy, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {idx + 1}. {m.title}
                    </div>
                    <div style={{ fontSize: 11, color: '#6b7280' }}>
                      {m.type}{m.duration_minutes ? ` • ${m.duration_minutes} min` : ''}
                    </div>
                  </div>
                  {isAdmin && (
                    <Space size={4}>
                      <Button
                        size="small"
                        type="text"
                        icon={<EditOutlined />}
                        onClick={(e) => { e.stopPropagation(); setEditing(m); setEditorOpen(true); }}
                      />
                      <Button
                        size="small"
                        type="text"
                        danger
                        icon={<DeleteOutlined />}
                        onClick={(e) => { e.stopPropagation(); handleDeleteModule(m.id); }}
                      />
                    </Space>
                  )}
                </div>
              );
            })
          )}
        </Layout.Sider>

        {/* Content viewer */}
        <Layout.Content style={{ background: '#ffffff', borderRadius: 12, padding: 24, border: `1px solid ${BRAND.royal50}` }}>
          {!activeModule ? (
            <Empty description="Select a lesson from the sidebar" />
          ) : (
            <>
              <div style={{ marginBottom: 16 }}>
                <Tag color="purple" style={{ background: BRAND.violet100, color: BRAND.violet600, border: 'none' }}>
                  Lesson {activeIndex + 1} of {sortedModules.length}
                </Tag>
                <Typography.Title level={3} style={{ margin: '8px 0 4px', color: BRAND.navy }}>
                  {activeModule.title}
                </Typography.Title>
                {activeModule.duration_minutes && (
                  <Typography.Text type="secondary">{activeModule.duration_minutes} minutes</Typography.Text>
                )}
              </div>

              <div style={{ marginBottom: 24 }}>
                {activeModule.type === 'video' && activeModule.content_url ? (
                  <VideoPlayer url={activeModule.content_url} />
                ) : activeModule.type === 'pdf' && activeModule.content_url ? (
                  <iframe
                    src={activeModule.content_url}
                    title={activeModule.title}
                    style={{ width: '100%', height: 600, border: 'none', borderRadius: 12 }}
                  />
                ) : activeModule.type === 'quiz' ? (
                  enrollment ? (
                    quizQuestions.length > 0 ? (
                      <QuizTaker
                        questions={quizQuestions}
                        enrollmentId={enrollment.id}
                        onPass={() => queryClient.invalidateQueries({ queryKey: ['my-enrollments'] })}
                      />
                    ) : (
                      <Empty description="No quiz questions configured for this course yet" />
                    )
                  ) : (
                    <Alert
                      type="info"
                      showIcon
                      message="Enroll to take the quiz"
                      action={
                        <Button type="primary" onClick={() => enrollMut.mutate()}>Enroll</Button>
                      }
                    />
                  )
                ) : null}

                {activeModule.description && activeModule.type !== 'quiz' && (
                  <div style={{
                    marginTop: 16,
                    padding: '14px 18px',
                    background: BRAND.royal50,
                    borderRadius: 10,
                    borderLeft: `4px solid ${BRAND.royal500}`,
                    whiteSpace: 'pre-wrap',
                    color: '#374151',
                    fontSize: 14,
                    lineHeight: 1.6,
                  }}>
                    {activeModule.description}
                  </div>
                )}
              </div>

              {/* Navigation footer */}
              <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                paddingTop: 18,
                borderTop: `1px solid ${BRAND.royal50}`,
              }}>
                <Button
                  icon={<ArrowLeftOutlined />}
                  disabled={activeIndex === 0}
                  onClick={goPrev}
                >
                  Previous
                </Button>
                <Space>
                  {!isAdmin && enrollment && activeModule.type !== 'quiz' && (
                    <Button
                      type="primary"
                      icon={<CheckCircleOutlined />}
                      loading={markDoneMut.isPending}
                      onClick={handleMarkComplete}
                      disabled={completedSet.has(activeModule.id)}
                    >
                      {completedSet.has(activeModule.id) ? 'Completed' : 'Mark as Complete'}
                    </Button>
                  )}
                </Space>
                <Button
                  icon={<ArrowRightOutlined />}
                  iconPosition="end"
                  disabled={activeIndex >= sortedModules.length - 1}
                  onClick={goNext}
                >
                  Next
                </Button>
              </div>
            </>
          )}
        </Layout.Content>
      </Layout>

      <ModuleEditorModal
        open={editorOpen}
        initial={editing}
        onCancel={() => { setEditorOpen(false); setEditing(undefined); }}
        onSave={handleSaveModule}
      />
    </>
  );
};

export default CourseDetailPage;
