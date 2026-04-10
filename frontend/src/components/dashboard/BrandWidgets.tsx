/**
 * Custom brand-themed widgets for the dashboards.
 *
 * Built as plain divs/SVG so they're 100% reliable across @ant-design/plots
 * version differences. Use these for Funnel, Donut, Heatmap, RadialBars,
 * RingProgress, etc — visualizations where the upstream chart library API
 * changes too often to depend on.
 */
import React from 'react';
import { Typography, Tag, Tooltip } from 'antd';

const BRAND = {
  royal500: '#3750ed',
  royal400: '#4961f1',
  royal300: '#6b7bfe',
  royal200: '#8c93f1',
  royal100: '#b4b6f7',
  royal50: '#e7e7f1',
  navy: '#1c1c3a',
  violet500: '#a064f3',
  violet400: '#b370fc',
  violet600: '#7a2280',
  violet700: '#5b1965',
  violet100: '#f0e6ff',
};

const formatNum = (n: number): string => {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toFixed(0);
};

// ---------------------------------------------------------------------------
// BrandFunnel — pure-CSS funnel using clip-path trapezoids
// ---------------------------------------------------------------------------
interface FunnelDatum {
  stage: string;
  count: number;
}

interface BrandFunnelProps {
  data: FunnelDatum[];
  height?: number;
}

export const BrandFunnel: React.FC<BrandFunnelProps> = ({ data, height = 280 }) => {
  if (!data || data.length === 0) {
    return <Typography.Text type="secondary">No funnel data</Typography.Text>;
  }
  const max = Math.max(...data.map((d) => d.count), 1);
  const colors = [BRAND.royal500, BRAND.royal400, BRAND.violet500, BRAND.violet600, '#10b981'];
  const rowHeight = Math.max(38, (height - data.length * 8) / data.length);

  return (
    <div style={{ padding: '8px 0', height, display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
      {data.map((d, idx) => {
        const widthPct = Math.max(20, (d.count / max) * 100);
        const prev = idx > 0 ? data[idx - 1] : undefined;
        const conversion =
          idx === 0
            ? 100
            : prev && prev.count > 0
              ? Math.round((d.count / prev.count) * 100)
              : 0;
        return (
          <div
            key={d.stage}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              marginBottom: 8,
              minHeight: rowHeight,
            }}
          >
            <div style={{ width: 92, fontSize: 12, color: '#6b7280', textAlign: 'right' }}>
              {d.stage}
            </div>
            <div style={{ flex: 1, position: 'relative', height: rowHeight }}>
              <div
                style={{
                  width: `${widthPct}%`,
                  height: '100%',
                  background: `linear-gradient(90deg, ${colors[idx % colors.length]} 0%, ${colors[(idx + 1) % colors.length]} 100%)`,
                  borderRadius: 8,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '0 14px',
                  color: '#fff',
                  fontWeight: 600,
                  boxShadow: '0 4px 12px rgba(28, 28, 58, 0.1)',
                  transition: 'width 0.6s ease',
                  margin: '0 auto',
                }}
              >
                <span style={{ fontSize: 13 }}>{d.count}</span>
                {idx > 0 && (
                  <span style={{ fontSize: 11, opacity: 0.85 }}>{conversion}% →</span>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
};

// ---------------------------------------------------------------------------
// BrandDonut — SVG donut chart with center label, totally reliable
// ---------------------------------------------------------------------------
interface DonutSlice {
  label: string;
  value: number;
  color: string;
}

interface BrandDonutProps {
  data: DonutSlice[];
  size?: number;
  thickness?: number;
  centerLabel?: string;
  centerValue?: string | number;
  showLegend?: boolean;
}

export const BrandDonut: React.FC<BrandDonutProps> = ({
  data,
  size = 200,
  thickness = 28,
  centerLabel,
  centerValue,
  showLegend = true,
}) => {
  const total = data.reduce((sum, d) => sum + d.value, 0);
  if (total === 0) {
    return <Typography.Text type="secondary">No data</Typography.Text>;
  }

  const radius = size / 2 - thickness / 2;
  const circumference = 2 * Math.PI * radius;
  let cumulative = 0;
  const segments = data.map((d) => {
    const fraction = d.value / total;
    const dasharray = `${fraction * circumference} ${circumference}`;
    const offset = -cumulative * circumference;
    cumulative += fraction;
    return { ...d, dasharray, offset, percent: Math.round(fraction * 100) };
  });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16 }}>
      <div style={{ position: 'relative', width: size, height: size }}>
        <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke={BRAND.royal50}
            strokeWidth={thickness}
          />
          {segments.map((s, idx) => (
            <circle
              key={idx}
              cx={size / 2}
              cy={size / 2}
              r={radius}
              fill="none"
              stroke={s.color}
              strokeWidth={thickness}
              strokeDasharray={s.dasharray}
              strokeDashoffset={s.offset}
              strokeLinecap="butt"
              style={{ transition: 'stroke-dasharray 0.7s ease' }}
            />
          ))}
        </svg>
        <div
          style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'center',
            alignItems: 'center',
          }}
        >
          {centerValue !== undefined && (
            <div style={{ fontSize: 26, fontWeight: 700, color: BRAND.navy, lineHeight: 1 }}>
              {centerValue}
            </div>
          )}
          {centerLabel && (
            <div style={{ fontSize: 11, color: '#6b7280', marginTop: 4, textTransform: 'uppercase', letterSpacing: 0.5 }}>
              {centerLabel}
            </div>
          )}
        </div>
      </div>

      {showLegend && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, justifyContent: 'center' }}>
          {segments.map((s) => (
            <div key={s.label} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span
                style={{
                  width: 10,
                  height: 10,
                  borderRadius: 3,
                  background: s.color,
                  display: 'inline-block',
                }}
              />
              <Typography.Text style={{ fontSize: 12, color: '#374151' }}>
                {s.label}
              </Typography.Text>
              <Typography.Text strong style={{ fontSize: 12, color: BRAND.navy }}>
                {s.value} ({s.percent}%)
              </Typography.Text>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// ---------------------------------------------------------------------------
// BrandRadialBars — vertical list of bar rows with brand gradients
// ---------------------------------------------------------------------------
interface RadialBarDatum {
  label: string;
  value: number;
  rightLabel?: string;
  color?: string;
}

interface BrandRadialBarsProps {
  data: RadialBarDatum[];
  formatValue?: (v: number) => string;
}

export const BrandRadialBars: React.FC<BrandRadialBarsProps> = ({ data, formatValue }) => {
  if (!data || data.length === 0) {
    return <Typography.Text type="secondary">No data</Typography.Text>;
  }
  const max = Math.max(...data.map((d) => d.value), 1);
  const palette = [BRAND.royal500, BRAND.royal400, BRAND.violet500, BRAND.violet600, BRAND.royal300, BRAND.royal200];

  return (
    <div>
      {data.map((d, idx) => {
        const pct = (d.value / max) * 100;
        const color = d.color ?? palette[idx % palette.length] ?? BRAND.royal500;
        return (
          <div key={d.label} style={{ marginBottom: 14 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
              <Typography.Text strong style={{ fontSize: 13, color: BRAND.navy }}>
                {d.label}
              </Typography.Text>
              <Typography.Text strong style={{ fontSize: 13, color: BRAND.navy }}>
                {d.rightLabel ?? (formatValue ? formatValue(d.value) : d.value)}
              </Typography.Text>
            </div>
            <div
              style={{
                height: 10,
                background: BRAND.royal50,
                borderRadius: 5,
                overflow: 'hidden',
              }}
            >
              <div
                style={{
                  width: `${pct}%`,
                  height: '100%',
                  background: `linear-gradient(90deg, ${color} 0%, ${BRAND.violet500} 100%)`,
                  borderRadius: 5,
                  transition: 'width 0.6s ease',
                }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
};

// ---------------------------------------------------------------------------
// BrandHeatCells — n×m grid of activity cells (calendar-style)
// ---------------------------------------------------------------------------
interface HeatCell {
  label: string;
  value: number;
}

interface BrandHeatCellsProps {
  data: HeatCell[];
  columns?: number;
}

export const BrandHeatCells: React.FC<BrandHeatCellsProps> = ({ data, columns = 12 }) => {
  if (!data || data.length === 0) return <Typography.Text type="secondary">No data</Typography.Text>;
  const max = Math.max(...data.map((d) => d.value), 1);
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: `repeat(${columns}, 1fr)`,
        gap: 6,
      }}
    >
      {data.map((c) => {
        const intensity = c.value / max;
        const opacity = 0.15 + intensity * 0.85;
        return (
          <Tooltip key={c.label} title={`${c.label}: ${c.value}`}>
            <div
              style={{
                aspectRatio: '1 / 1',
                background: BRAND.royal500,
                opacity,
                borderRadius: 4,
                transition: 'transform 0.2s',
                cursor: 'default',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.transform = 'scale(1.15)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.transform = 'scale(1)';
              }}
            />
          </Tooltip>
        );
      })}
    </div>
  );
};

// ---------------------------------------------------------------------------
// BrandGauge — semicircle SVG gauge
// ---------------------------------------------------------------------------
interface BrandGaugeProps {
  percent: number; // 0-100
  label?: string;
  size?: number;
}

export const BrandGauge: React.FC<BrandGaugeProps> = ({ percent, label, size = 200 }) => {
  const safePercent = Math.max(0, Math.min(100, percent));
  const radius = size / 2 - 18;
  const circumference = Math.PI * radius;
  const dashoffset = circumference * (1 - safePercent / 100);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}>
      <div style={{ position: 'relative', width: size, height: size / 2 + 12 }}>
        <svg width={size} height={size / 2 + 12}>
          <defs>
            <linearGradient id="gauge-grad" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor={BRAND.royal400} />
              <stop offset="100%" stopColor={BRAND.violet500} />
            </linearGradient>
          </defs>
          <path
            d={`M 18 ${size / 2} A ${radius} ${radius} 0 0 1 ${size - 18} ${size / 2}`}
            fill="none"
            stroke={BRAND.royal50}
            strokeWidth={16}
            strokeLinecap="round"
          />
          <path
            d={`M 18 ${size / 2} A ${radius} ${radius} 0 0 1 ${size - 18} ${size / 2}`}
            fill="none"
            stroke="url(#gauge-grad)"
            strokeWidth={16}
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={dashoffset}
            style={{ transition: 'stroke-dashoffset 0.8s ease' }}
          />
        </svg>
        <div
          style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'flex-end',
            alignItems: 'center',
            paddingBottom: 4,
          }}
        >
          <div style={{ fontSize: 32, fontWeight: 700, color: BRAND.navy, lineHeight: 1 }}>
            {safePercent}%
          </div>
          {label && (
            <div style={{ fontSize: 12, color: '#6b7280', marginTop: 4 }}>{label}</div>
          )}
        </div>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// BrandLiquid — vertical CSS water-fill gauge
// ---------------------------------------------------------------------------
interface BrandLiquidProps {
  percent: number; // 0-100
  label?: string;
  centerText?: string;
  size?: number;
}

export const BrandLiquid: React.FC<BrandLiquidProps> = ({ percent, label, centerText, size = 180 }) => {
  const safePercent = Math.max(0, Math.min(100, percent));
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}>
      <div
        style={{
          position: 'relative',
          width: size,
          height: size,
          borderRadius: '50%',
          border: `4px solid ${BRAND.royal100}`,
          overflow: 'hidden',
          background: BRAND.royal50,
        }}
      >
        <div
          style={{
            position: 'absolute',
            left: 0,
            right: 0,
            bottom: 0,
            height: `${safePercent}%`,
            background: `linear-gradient(180deg, ${BRAND.royal400} 0%, ${BRAND.violet500} 100%)`,
            transition: 'height 1s ease',
          }}
        >
          {/* wave effect */}
          <svg
            viewBox="0 0 200 20"
            preserveAspectRatio="none"
            style={{
              position: 'absolute',
              top: -10,
              left: 0,
              width: '100%',
              height: 20,
            }}
          >
            <path
              d="M0,10 Q50,0 100,10 T200,10 L200,20 L0,20 Z"
              fill={BRAND.royal400}
              opacity="0.7"
            />
          </svg>
        </div>
        <div
          style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'center',
            alignItems: 'center',
            zIndex: 2,
            mixBlendMode: 'difference',
            color: '#ffffff',
          }}
        >
          <div style={{ fontSize: 22, fontWeight: 700, lineHeight: 1 }}>
            {centerText ?? `${safePercent}%`}
          </div>
          {label && (
            <div style={{ fontSize: 11, marginTop: 4, textTransform: 'uppercase', letterSpacing: 0.5 }}>
              {label}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// BrandStatPill — small inline metric chip
// ---------------------------------------------------------------------------
interface BrandStatPillProps {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  color?: string;
}

export const BrandStatPill: React.FC<BrandStatPillProps> = ({ icon, label, value, color = BRAND.royal500 }) => (
  <div
    style={{
      display: 'flex',
      alignItems: 'center',
      gap: 10,
      padding: '10px 14px',
      borderRadius: 10,
      background: BRAND.royal50,
      border: `1px solid ${BRAND.royal100}`,
    }}
  >
    <div
      style={{
        width: 36,
        height: 36,
        borderRadius: 8,
        background: color,
        color: '#fff',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: 16,
        flexShrink: 0,
      }}
    >
      {icon}
    </div>
    <div style={{ minWidth: 0 }}>
      <Typography.Text style={{ fontSize: 11, color: '#6b7280', display: 'block', textTransform: 'uppercase', letterSpacing: 0.4 }}>
        {label}
      </Typography.Text>
      <Typography.Text strong style={{ fontSize: 16, color: BRAND.navy }}>
        {value}
      </Typography.Text>
    </div>
  </div>
);

// ---------------------------------------------------------------------------
// AchievementBadge — small badge for the partner dashboard
// ---------------------------------------------------------------------------
interface AchievementBadgeProps {
  icon: React.ReactNode;
  title: string;
  description: string;
  unlocked: boolean;
}

export const AchievementBadge: React.FC<AchievementBadgeProps> = ({ icon, title, description, unlocked }) => (
  <div
    style={{
      padding: 14,
      borderRadius: 12,
      background: unlocked
        ? `linear-gradient(135deg, ${BRAND.royal50} 0%, ${BRAND.violet100} 100%)`
        : '#f5f5f5',
      border: `1px solid ${unlocked ? BRAND.royal100 : '#e5e7eb'}`,
      opacity: unlocked ? 1 : 0.6,
      textAlign: 'center',
      transition: 'transform 0.2s',
    }}
  >
    <div
      style={{
        width: 44,
        height: 44,
        borderRadius: '50%',
        background: unlocked
          ? `linear-gradient(135deg, ${BRAND.royal500} 0%, ${BRAND.violet500} 100%)`
          : '#9ca3af',
        color: '#fff',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: 18,
        margin: '0 auto 10px',
      }}
    >
      {icon}
    </div>
    <div style={{ fontSize: 12, fontWeight: 700, color: BRAND.navy, marginBottom: 2 }}>{title}</div>
    <div style={{ fontSize: 11, color: '#6b7280', lineHeight: 1.4 }}>{description}</div>
    {unlocked && (
      <Tag color="purple" style={{ marginTop: 8, fontSize: 9, padding: '0 6px', background: BRAND.violet100, color: BRAND.violet700, border: 'none' }}>
        UNLOCKED
      </Tag>
    )}
  </div>
);

export const formatChartUsd = (v: number | string): string => {
  const n = Number(v);
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `$${(n / 1_000).toFixed(1)}K`;
  return `$${n.toFixed(0)}`;
};

export const formatChartNum = formatNum;

// ---------------------------------------------------------------------------
// BrandStackedBars — modern monthly trend with stacked vertical bars
// Replaces "Monthly Pipeline Trend" with a custom interactive chart that
// stacks Submitted/Approved/Rejected per month, shows totals on hover, and
// has smooth grow-in animation.
// ---------------------------------------------------------------------------
interface StackedBarPoint {
  label: string;
  values: { name: string; value: number; color: string }[];
}

interface BrandStackedBarsProps {
  data: StackedBarPoint[];
  height?: number;
  showLegend?: boolean;
}

export const BrandStackedBars: React.FC<BrandStackedBarsProps> = ({
  data,
  height = 280,
  showLegend = true,
}) => {
  if (!data || data.length === 0) {
    return <Typography.Text type="secondary">No data</Typography.Text>;
  }

  const maxTotal = Math.max(
    ...data.map((d) => d.values.reduce((s, v) => s + v.value, 0)),
    1,
  );
  const seriesNames = data[0]?.values.map((v) => ({ name: v.name, color: v.color })) ?? [];
  const chartHeight = height - (showLegend ? 50 : 20);

  return (
    <div style={{ width: '100%' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'flex-end',
          justifyContent: 'space-between',
          gap: 8,
          height: chartHeight,
          padding: '12px 4px 24px',
          borderBottom: `1px solid ${BRAND.royal50}`,
        }}
      >
        {data.map((d, idx) => {
          const total = d.values.reduce((s, v) => s + v.value, 0);
          const totalHeightPct = (total / maxTotal) * 100;
          return (
            <Tooltip
              key={`${d.label}-${idx}`}
              title={
                <div>
                  <div style={{ fontWeight: 600, marginBottom: 4 }}>{d.label}</div>
                  {d.values.map((v) => (
                    <div key={v.name} style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                      <span>
                        <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: 2, background: v.color, marginRight: 6 }} />
                        {v.name}
                      </span>
                      <strong>{v.value}</strong>
                    </div>
                  ))}
                  <div style={{ marginTop: 4, paddingTop: 4, borderTop: '1px solid rgba(255,255,255,0.2)' }}>
                    Total: <strong>{total}</strong>
                  </div>
                </div>
              }
            >
              <div
                style={{
                  flex: 1,
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  cursor: 'pointer',
                  position: 'relative',
                  height: '100%',
                  justifyContent: 'flex-end',
                }}
              >
                <div
                  style={{
                    width: '100%',
                    maxWidth: 36,
                    height: `${totalHeightPct}%`,
                    display: 'flex',
                    flexDirection: 'column-reverse',
                    borderRadius: '6px 6px 0 0',
                    overflow: 'hidden',
                    transition: 'height 0.7s ease',
                    boxShadow: '0 -2px 8px rgba(28, 28, 58, 0.06)',
                  }}
                >
                  {d.values.map((v) => (
                    <div
                      key={v.name}
                      style={{
                        width: '100%',
                        flexBasis: total > 0 ? `${(v.value / total) * 100}%` : 0,
                        background: v.color,
                        transition: 'flex-basis 0.7s ease',
                      }}
                    />
                  ))}
                </div>
                <div
                  style={{
                    position: 'absolute',
                    bottom: -22,
                    fontSize: 10,
                    color: '#6b7280',
                    fontWeight: 500,
                    whiteSpace: 'nowrap',
                  }}
                >
                  {d.label.slice(-2) /* show MM only */}
                </div>
              </div>
            </Tooltip>
          );
        })}
      </div>

      {showLegend && (
        <div style={{ display: 'flex', justifyContent: 'center', gap: 18, marginTop: 14 }}>
          {seriesNames.map((s) => (
            <div key={s.name} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ width: 12, height: 12, borderRadius: 3, background: s.color, display: 'inline-block' }} />
              <Typography.Text style={{ fontSize: 12, color: '#374151' }}>{s.name}</Typography.Text>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// ---------------------------------------------------------------------------
// BrandTimelineMetric — month boxes with delta arrows (modern timeline)
// Replaces "Monthly Approvals Trend" with horizontal cards per month showing
// the metric value and the delta vs the previous month.
// ---------------------------------------------------------------------------
interface TimelineMetricPoint {
  label: string;
  value: number;
}

interface BrandTimelineMetricProps {
  data: TimelineMetricPoint[];
  title?: string;
}

export const BrandTimelineMetric: React.FC<BrandTimelineMetricProps> = ({ data }) => {
  if (!data || data.length === 0) {
    return <Typography.Text type="secondary">No data</Typography.Text>;
  }
  const max = Math.max(...data.map((d) => d.value), 1);
  // Show last 6 entries to keep it clean
  const visible = data.slice(-6);

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: `repeat(${visible.length}, 1fr)`,
        gap: 10,
      }}
    >
      {visible.map((d, idx) => {
        const prevPoint = idx > 0 ? visible[idx - 1] : undefined;
        const prev = prevPoint?.value ?? null;
        const delta = prev !== null ? d.value - prev : null;
        const deltaPct = prev !== null && prev > 0 && delta !== null ? Math.round((delta / prev) * 100) : null;
        const fillPct = (d.value / max) * 100;
        return (
          <div
            key={d.label}
            style={{
              position: 'relative',
              padding: '14px 12px 12px',
              borderRadius: 10,
              background: BRAND.royal50,
              border: `1px solid ${BRAND.royal100}`,
              overflow: 'hidden',
              transition: 'transform 0.2s',
            }}
            onMouseEnter={(e) => (e.currentTarget.style.transform = 'translateY(-2px)')}
            onMouseLeave={(e) => (e.currentTarget.style.transform = 'translateY(0)')}
          >
            {/* Background fill bar */}
            <div
              style={{
                position: 'absolute',
                bottom: 0,
                left: 0,
                right: 0,
                height: `${fillPct}%`,
                background: `linear-gradient(180deg, transparent 0%, ${BRAND.violet100} 100%)`,
                transition: 'height 0.6s ease',
                pointerEvents: 'none',
              }}
            />
            <div style={{ position: 'relative' }}>
              <Typography.Text style={{ fontSize: 10, color: '#6b7280', textTransform: 'uppercase', letterSpacing: 0.5, display: 'block' }}>
                {d.label}
              </Typography.Text>
              <Typography.Text strong style={{ fontSize: 22, color: BRAND.navy, lineHeight: 1.2 }}>
                {d.value}
              </Typography.Text>
              {delta !== null && (
                <div
                  style={{
                    marginTop: 4,
                    display: 'flex',
                    alignItems: 'center',
                    gap: 4,
                    fontSize: 11,
                    fontWeight: 600,
                    color: delta > 0 ? '#10b981' : delta < 0 ? '#ef4444' : '#6b7280',
                  }}
                >
                  <span>{delta > 0 ? '↑' : delta < 0 ? '↓' : '·'}</span>
                  {deltaPct !== null && <span>{Math.abs(deltaPct)}%</span>}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
};

// ---------------------------------------------------------------------------
// BrandSparkCards — row of small cards with label, value, mini sparkline
// ---------------------------------------------------------------------------
interface SparkCard {
  label: string;
  value: string | number;
  series: number[];
  color?: string;
}

interface BrandSparkCardsProps {
  data: SparkCard[];
}

const Sparkline: React.FC<{ data: number[]; color: string; height?: number }> = ({ data, color, height = 32 }) => {
  if (!data || data.length === 0) return null;
  const max = Math.max(...data, 1);
  const min = Math.min(...data, 0);
  const range = max - min || 1;
  const width = 100;
  const points = data
    .map((v, i) => {
      const x = (i / Math.max(1, data.length - 1)) * width;
      const y = height - ((v - min) / range) * (height - 4) - 2;
      return `${x},${y}`;
    })
    .join(' ');

  // Build area polygon (close down to baseline)
  const areaPoints = `0,${height} ${points} ${width},${height}`;

  return (
    <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
      <defs>
        <linearGradient id={`spark-grad-${color.replace('#', '')}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.4" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polyline points={areaPoints} fill={`url(#spark-grad-${color.replace('#', '')})`} stroke="none" />
      <polyline points={points} fill="none" stroke={color} strokeWidth="1.8" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
};

export const BrandSparkCards: React.FC<BrandSparkCardsProps> = ({ data }) => {
  const palette = [BRAND.royal500, BRAND.violet500, '#10b981', '#f59e0b'];
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
        gap: 12,
      }}
    >
      {data.map((card, idx) => {
        const color = card.color ?? palette[idx % palette.length] ?? BRAND.royal500;
        return (
          <div
            key={card.label}
            style={{
              padding: 14,
              borderRadius: 10,
              background: '#ffffff',
              border: `1px solid ${BRAND.royal50}`,
              boxShadow: '0 2px 8px rgba(28, 28, 58, 0.04)',
            }}
          >
            <div style={{ fontSize: 11, color: '#6b7280', textTransform: 'uppercase', letterSpacing: 0.4, marginBottom: 4 }}>
              {card.label}
            </div>
            <div style={{ fontSize: 22, fontWeight: 700, color: BRAND.navy, lineHeight: 1.1, marginBottom: 6 }}>
              {card.value}
            </div>
            <Sparkline data={card.series} color={color} height={28} />
          </div>
        );
      })}
    </div>
  );
};

// ---------------------------------------------------------------------------
// BrandRingGrid — multiple SVG ring progress meters in a grid
// ---------------------------------------------------------------------------
interface RingDatum {
  label: string;
  percent: number;
  color?: string;
  value?: string;
}

interface BrandRingGridProps {
  data: RingDatum[];
  size?: number;
}

export const BrandRingGrid: React.FC<BrandRingGridProps> = ({ data, size = 96 }) => {
  const palette = [BRAND.royal500, BRAND.violet500, '#10b981', '#f59e0b', BRAND.violet600, BRAND.royal400];
  const radius = size / 2 - 8;
  const circumference = 2 * Math.PI * radius;

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))',
        gap: 12,
      }}
    >
      {data.map((d, idx) => {
        const safe = Math.max(0, Math.min(100, d.percent));
        const color = d.color ?? palette[idx % palette.length] ?? BRAND.royal500;
        const dashoffset = circumference * (1 - safe / 100);
        return (
          <div key={d.label} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
            <div style={{ position: 'relative', width: size, height: size }}>
              <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
                <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke={BRAND.royal50} strokeWidth={8} />
                <circle
                  cx={size / 2}
                  cy={size / 2}
                  r={radius}
                  fill="none"
                  stroke={color}
                  strokeWidth={8}
                  strokeLinecap="round"
                  strokeDasharray={circumference}
                  strokeDashoffset={dashoffset}
                  style={{ transition: 'stroke-dashoffset 0.7s ease' }}
                />
              </svg>
              <div
                style={{
                  position: 'absolute',
                  inset: 0,
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'center',
                  alignItems: 'center',
                }}
              >
                <Typography.Text strong style={{ fontSize: 16, color: BRAND.navy, lineHeight: 1 }}>
                  {d.value ?? `${safe}%`}
                </Typography.Text>
              </div>
            </div>
            <Typography.Text style={{ fontSize: 12, color: '#374151', fontWeight: 500 }}>
              {d.label}
            </Typography.Text>
          </div>
        );
      })}
    </div>
  );
};

// ---------------------------------------------------------------------------
// BrandBubbleMatrix — grid of bubbles whose size encodes value
// ---------------------------------------------------------------------------
interface BubbleDatum {
  label: string;
  value: number;
  subtitle?: string;
}

interface BrandBubbleMatrixProps {
  data: BubbleDatum[];
}

export const BrandBubbleMatrix: React.FC<BrandBubbleMatrixProps> = ({ data }) => {
  if (!data || data.length === 0) {
    return <Typography.Text type="secondary">No data</Typography.Text>;
  }
  const max = Math.max(...data.map((d) => d.value), 1);
  const palette = [BRAND.royal500, BRAND.royal400, BRAND.violet500, BRAND.violet600, BRAND.royal300, BRAND.violet700];

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
        gap: 16,
        padding: '8px 0',
      }}
    >
      {data.map((d, idx) => {
        const ratio = d.value / max;
        const bubbleSize = Math.max(48, 48 + ratio * 56);
        const color = palette[idx % palette.length] ?? BRAND.royal500;
        return (
          <div
            key={d.label}
            style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}
          >
            <Tooltip title={`${d.label}: ${d.value}${d.subtitle ? ` • ${d.subtitle}` : ''}`}>
              <div
                style={{
                  width: bubbleSize,
                  height: bubbleSize,
                  borderRadius: '50%',
                  background: `radial-gradient(circle at 30% 30%, ${color}ff 0%, ${color}66 100%)`,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#ffffff',
                  fontWeight: 700,
                  fontSize: bubbleSize > 80 ? 18 : 14,
                  boxShadow: `0 8px 20px ${color}40`,
                  transition: 'transform 0.2s',
                  cursor: 'pointer',
                }}
                onMouseEnter={(e) => (e.currentTarget.style.transform = 'scale(1.06)')}
                onMouseLeave={(e) => (e.currentTarget.style.transform = 'scale(1)')}
              >
                {d.value}
              </div>
            </Tooltip>
            <div style={{ textAlign: 'center', maxWidth: 140 }}>
              <Typography.Text strong style={{ fontSize: 12, color: BRAND.navy, display: 'block', lineHeight: 1.2 }}>
                {d.label}
              </Typography.Text>
              {d.subtitle && (
                <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                  {d.subtitle}
                </Typography.Text>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
};

// ---------------------------------------------------------------------------
// BrandDeltaCard — large metric with delta arrow + supporting series
// ---------------------------------------------------------------------------
interface BrandDeltaCardProps {
  label: string;
  value: string | number;
  previousValue?: number;
  currentValue?: number;
  series: number[];
  color?: string;
}

export const BrandDeltaCard: React.FC<BrandDeltaCardProps> = ({
  label,
  value,
  previousValue,
  currentValue,
  series,
  color = BRAND.royal500,
}) => {
  const delta = currentValue !== undefined && previousValue !== undefined && previousValue > 0
    ? Math.round(((currentValue - previousValue) / previousValue) * 100)
    : null;
  const positive = delta !== null && delta >= 0;

  return (
    <div
      style={{
        padding: 18,
        borderRadius: 12,
        background: '#ffffff',
        border: `1px solid ${BRAND.royal50}`,
        boxShadow: '0 4px 12px rgba(28, 28, 58, 0.04)',
      }}
    >
      <Typography.Text style={{ fontSize: 12, color: '#6b7280', textTransform: 'uppercase', letterSpacing: 0.5 }}>
        {label}
      </Typography.Text>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginTop: 4, marginBottom: 8 }}>
        <Typography.Text strong style={{ fontSize: 28, color: BRAND.navy, lineHeight: 1.1 }}>
          {value}
        </Typography.Text>
        {delta !== null && (
          <Typography.Text
            style={{
              fontSize: 13,
              fontWeight: 600,
              color: positive ? '#10b981' : '#ef4444',
            }}
          >
            {positive ? '↑' : '↓'} {Math.abs(delta)}%
          </Typography.Text>
        )}
      </div>
      <Sparkline data={series} color={color} height={36} />
    </div>
  );
};

