/**
 * POC / deployment / city-funnel widgets.
 *
 * Same approach as BrandWidgets: plain divs + SVG rather than
 * @ant-design/plots, so these stay stable across chart-library versions and
 * match the existing dashboard visually.
 */
import React from 'react';
import { Typography, Tag, Tooltip, Empty } from 'antd';
import { CheckCircleFilled, ClockCircleOutlined } from '@ant-design/icons';
import { formatChartUsd } from './BrandWidgets';
import type {
  PocStageProgress,
  PocStageState,
  CityFunnelResponse,
  PocStatus,
} from '@/types';

const { Text } = Typography;

const BRAND = {
  royal500: '#3750ed',
  royal400: '#4961f1',
  royal300: '#6b7bfe',
  royal200: '#8c93f1',
  royal50: '#e7e7f1',
  navy: '#1c1c3a',
  violet500: '#a064f3',
  violet600: '#7a2280',
  green: '#10b981',
  amber: '#f59e0b',
  red: '#ef4444',
  grey: '#94a3b8',
};

// The five stages in flow order, each with its own hue so a stage keeps the
// same colour everywhere it appears.
export const STAGE_COLORS: string[] = [
  BRAND.royal500,
  BRAND.royal300,
  BRAND.violet500,
  BRAND.violet600,
  BRAND.green,
];

export const POC_STATUS_COLORS: Record<PocStatus, string> = {
  not_started: BRAND.grey,
  running: BRAND.royal500,
  successful: BRAND.green,
  unsuccessful: BRAND.red,
};

export const pocStatusColor = (s: PocStatus): string => POC_STATUS_COLORS[s] ?? BRAND.grey;

// ---------------------------------------------------------------------------
// PocStageTracker — the 5-stage checklist for a single POC
// ---------------------------------------------------------------------------
interface PocStageTrackerProps {
  stages: PocStageState[];
  // Fires when a stage dot is clicked. Omit to render read-only (partners).
  onToggle?: (stage: PocStageState) => void;
  disabled?: boolean;
}

export const PocStageTracker: React.FC<PocStageTrackerProps> = ({ stages, onToggle, disabled }) => (
  <div style={{ display: 'flex', alignItems: 'flex-start', width: '100%' }}>
    {stages.map((s, idx) => {
      const color = STAGE_COLORS[idx] ?? BRAND.royal500;
      const isLast = idx === stages.length - 1;
      const clickable = !!onToggle && !disabled;
      return (
        <div key={s.key} style={{ flex: 1, minWidth: 0, position: 'relative' }}>
          {/* Connector to the next stage, drawn behind the dot */}
          {!isLast && (
            <div
              style={{
                position: 'absolute',
                top: 15,
                left: '50%',
                right: '-50%',
                height: 3,
                background: s.completed ? color : BRAND.royal50,
                zIndex: 0,
              }}
            />
          )}
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', position: 'relative', zIndex: 1 }}>
            <Tooltip
              title={
                s.completed
                  ? `${s.label} — completed ${s.completed_at}${clickable ? ' (click to undo)' : ''}`
                  : clickable
                    ? `Mark ${s.label} complete`
                    : `${s.label} — not started`
              }
            >
              <div
                onClick={clickable ? () => onToggle(s) : undefined}
                style={{
                  width: 32,
                  height: 32,
                  borderRadius: '50%',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  background: s.completed ? color : '#fff',
                  border: `3px solid ${s.completed ? color : BRAND.royal50}`,
                  color: '#fff',
                  cursor: clickable ? 'pointer' : 'default',
                  transition: 'all 0.2s',
                  fontSize: 14,
                }}
              >
                {s.completed ? <CheckCircleFilled /> : <span style={{ color: BRAND.grey, fontSize: 12 }}>{idx + 1}</span>}
              </div>
            </Tooltip>
            <Text
              style={{
                fontSize: 11,
                marginTop: 8,
                textAlign: 'center',
                lineHeight: 1.3,
                color: s.completed ? BRAND.navy : BRAND.grey,
                fontWeight: s.completed ? 600 : 400,
              }}
            >
              {s.label}
            </Text>
            {s.completed_at && (
              <Text type="secondary" style={{ fontSize: 10, marginTop: 2 }}>
                {s.completed_at}
              </Text>
            )}
          </div>
        </div>
      );
    })}
  </div>
);

// ---------------------------------------------------------------------------
// PocStageFunnel — how many running POCs have cleared each stage
// ---------------------------------------------------------------------------
interface PocStageFunnelProps {
  data: PocStageProgress[];
}

export const PocStageFunnel: React.FC<PocStageFunnelProps> = ({ data }) => {
  // Scale bars against the widest stage, not the total, so the first stage
  // always fills the row and the drop-off stays legible.
  const max = Math.max(...data.map((d) => d.completed_count), 1);

  if (!data.some((d) => d.completed_count > 0)) {
    return <Empty description="No running POCs" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }

  return (
    <div>
      {data.map((d, idx) => {
        const color = STAGE_COLORS[idx] ?? BRAND.royal500;
        const pct = (d.completed_count / max) * 100;
        return (
          <div key={d.stage} style={{ marginBottom: 14 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
              <Text style={{ fontSize: 12, fontWeight: 600, color: BRAND.navy }}>{d.label}</Text>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                {d.avg_days_to_complete !== null && (
                  <Tooltip title="Average days from POC start to this stage completing">
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      <ClockCircleOutlined /> {d.avg_days_to_complete.toFixed(0)}d
                    </Text>
                  </Tooltip>
                )}
                <Text style={{ fontSize: 12, fontWeight: 700, color }}>{d.completed_count}</Text>
              </div>
            </div>
            <div style={{ height: 10, background: BRAND.royal50, borderRadius: 5, overflow: 'hidden' }}>
              <div
                style={{
                  width: `${pct}%`,
                  height: '100%',
                  background: `linear-gradient(90deg, ${color} 0%, ${color}cc 100%)`,
                  borderRadius: 5,
                  transition: 'width 0.4s',
                }}
              />
            </div>
            {d.pending_count > 0 && (
              <Text type="secondary" style={{ fontSize: 10 }}>
                {d.pending_count} running POC{d.pending_count === 1 ? '' : 's'} yet to clear this stage
              </Text>
            )}
          </div>
        );
      })}
    </div>
  );
};

// ---------------------------------------------------------------------------
// CityFunnelChart — funnel value per city, stacked by stage, filtered by quarter
// ---------------------------------------------------------------------------
interface CityFunnelChartProps {
  data: CityFunnelResponse;
  // 'all' sums every quarter; otherwise show just the selected one.
  quarter: string;
  maxCities?: number;
}

export const CityFunnelChart: React.FC<CityFunnelChartProps> = ({ data, quarter, maxCities = 12 }) => {
  const cells = quarter === 'all' ? data.cells : data.cells.filter((c) => c.quarter === quarter);

  // Pivot to city → stage → value.
  const byCity = new Map<string, Map<string, number>>();
  for (const c of cells) {
    if (!byCity.has(c.city)) byCity.set(c.city, new Map());
    const row = byCity.get(c.city)!;
    row.set(c.stage, (row.get(c.stage) ?? 0) + Number(c.total_worth));
  }

  const cityTotals = [...byCity.entries()]
    .map(([city, row]) => ({ city, total: [...row.values()].reduce((a, b) => a + b, 0), row }))
    .sort((a, b) => b.total - a.total)
    .slice(0, maxCities);

  if (cityTotals.length === 0) {
    return <Empty description={`No pipeline for ${quarter === 'all' ? 'any quarter' : quarter}`} image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }

  const max = Math.max(...cityTotals.map((c) => c.total), 1);
  const stageColor = (stage: string, idx: number): string => {
    const i = data.stages.indexOf(stage);
    return STAGE_COLORS[(i >= 0 ? i : idx) % STAGE_COLORS.length] ?? BRAND.royal500;
  };

  return (
    <div>
      {/* Legend */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, marginBottom: 16 }}>
        {data.stages.map((s, idx) => (
          <div key={s} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
            <span style={{ width: 10, height: 10, borderRadius: 2, background: stageColor(s, idx), display: 'inline-block' }} />
            <Text style={{ fontSize: 11 }}>{data.stage_labels[s] ?? s}</Text>
          </div>
        ))}
      </div>

      {cityTotals.map(({ city, total, row }) => (
        <div key={city} style={{ marginBottom: 12 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
            <Text style={{ fontSize: 12, fontWeight: 600, color: BRAND.navy }}>{city}</Text>
            <Text style={{ fontSize: 12, fontWeight: 700, color: BRAND.royal500 }}>{formatChartUsd(total)}</Text>
          </div>
          <div style={{ display: 'flex', height: 18, borderRadius: 4, overflow: 'hidden', background: BRAND.royal50 }}>
            {data.stages.map((s, idx) => {
              const v = row.get(s) ?? 0;
              if (v <= 0) return null;
              // Width is relative to the largest city, so bars are comparable
              // across rows rather than each filling 100%.
              const pct = (v / max) * 100;
              return (
                <Tooltip key={s} title={`${data.stage_labels[s] ?? s}: ${formatChartUsd(v)}`}>
                  <div style={{ width: `${pct}%`, background: stageColor(s, idx), transition: 'width 0.4s' }} />
                </Tooltip>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
};

// ---------------------------------------------------------------------------
// PocStatusTag
// ---------------------------------------------------------------------------
const STATUS_LABELS: Record<PocStatus, string> = {
  not_started: 'Not Started',
  running: 'Running',
  successful: 'Successful',
  unsuccessful: 'Unsuccessful',
};

export const PocStatusTag: React.FC<{ status: PocStatus }> = ({ status }) => (
  <Tag color={pocStatusColor(status)} style={{ borderRadius: 4, fontWeight: 600, border: 'none' }}>
    {STATUS_LABELS[status] ?? status}
  </Tag>
);
