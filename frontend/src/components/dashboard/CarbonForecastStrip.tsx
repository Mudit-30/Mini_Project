"use client";

import React from "react";
import { Area, AreaChart, ResponsiveContainer, YAxis } from "recharts";
import { Leaf, Minus, TrendingDown, TrendingUp, Wind } from "lucide-react";

/**
 * Stylish 2-hour grid outlook: a clean lime sparkline of the upcoming marginal
 * carbon (from the real replayed CAISO series) + the minutes until the grid next
 * drops into a clean window. Shows the scheduler's foresight, not just reaction.
 */
const ACCENT = "#b6ff2e"; // electric lime

export const CarbonForecastStrip = React.memo(function CarbonForecastStrip({
  forecast,
  cleanInMin,
}: {
  forecast: number[] | null;
  cleanInMin: number | null;
}) {
  if (!forecast || forecast.length === 0) return null;

  const data = forecast.map((v, i) => ({ i, gco2: v }));
  const min = Math.min(...forecast);
  const max = Math.max(...forecast);
  const now = forecast[0];
  const last = forecast[forecast.length - 1];
  const delta = last - now;
  const EPS = 1.0;
  const trend: "down" | "up" | "steady" =
    forecast.length < 2 || Math.abs(delta) < EPS ? "steady" : delta < 0 ? "down" : "up";

  const TrendIcon = trend === "down" ? TrendingDown : trend === "up" ? TrendingUp : Minus;
  const trendColor = trend === "down" ? "text-carbon-clean" : trend === "up" ? "text-carbon-dirty" : "text-faint";
  const trendLabel = trend === "down" ? "getting cleaner" : trend === "up" ? "getting dirtier" : "steady";

  // Glowing "you are here" dot at the current point.
  const renderNowDot = (p: { cx?: number; cy?: number; index?: number }) => {
    if (p.index !== 0 || p.cx == null || p.cy == null) return <g key={`d${p.index}`} />;
    return (
      <g key="now">
        <circle cx={p.cx} cy={p.cy} r={7} fill={ACCENT} opacity={0.2} />
        <circle cx={p.cx} cy={p.cy} r={3.5} fill={ACCENT} stroke="#0a0b0f" strokeWidth={1.5} />
      </g>
    );
  };

  return (
    <div className="card card-hover p-5 mb-8 flex flex-col lg:flex-row lg:items-center gap-5">
      {/* Label */}
      <div className="flex items-center gap-3 shrink-0">
        <div className="grid place-items-center w-9 h-9 rounded-xl border border-white/10" style={{ background: "color-mix(in srgb, var(--accent) 10%, transparent)" }}>
          <Wind className="w-4 h-4 text-accent" />
        </div>
        <div>
          <h2 className="section-label">Grid Outlook — Next 2 h</h2>
          <p className="text-[10px] text-faint font-mono mt-0.5">marginal gCO₂/kWh · replayed CAISO</p>
        </div>
      </div>

      {/* Lime sparkline */}
      <div className="h-[58px] flex-1 w-full min-w-[180px]">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 8, right: 6, left: 0, bottom: 2 }}>
            <defs>
              <linearGradient id="fcFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={ACCENT} stopOpacity={0.32} />
                <stop offset="100%" stopColor={ACCENT} stopOpacity={0} />
              </linearGradient>
            </defs>
            <YAxis hide domain={["dataMin - 8", "dataMax + 8"]} />
            <Area
              type="monotone"
              dataKey="gco2"
              stroke={ACCENT}
              strokeWidth={2.5}
              strokeLinecap="round"
              fill="url(#fcFill)"
              fillOpacity={1}
              dot={renderNowDot}
              isAnimationActive={false}
              style={{ filter: `drop-shadow(0 0 6px color-mix(in srgb, ${ACCENT} 45%, transparent))` }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Stats */}
      <div className="flex items-stretch gap-3 shrink-0">
        <div className="text-center px-3">
          <div className="text-faint text-[9px] uppercase tracking-wider">Now</div>
          <div className="stat-num text-xl font-bold font-mono text-foreground">{Math.round(now)}</div>
        </div>
        <div className="w-px bg-white/10" />
        <div className="text-center px-3">
          <div className="text-faint text-[9px] uppercase tracking-wider">2h Range</div>
          <div className="text-foreground font-mono text-sm mt-1">{Math.round(min)}–{Math.round(max)}</div>
        </div>
        <div className="w-px bg-white/10" />
        <div className="text-center px-3">
          <div className="text-faint text-[9px] uppercase tracking-wider">Clean Window</div>
          <div className="flex items-center justify-center gap-1 mt-1">
            {cleanInMin !== null && <Leaf className="w-3 h-3 text-carbon-clean" />}
            <span className={`font-mono text-sm font-bold ${cleanInMin === null ? "text-muted" : "text-carbon-clean"}`}>
              {cleanInMin === null ? "none in 2h" : cleanInMin === 0 ? "now" : `~${cleanInMin}m`}
            </span>
          </div>
        </div>
        <span className={`chip self-center text-[10px] font-bold uppercase ${trendColor}`}>
          <TrendIcon className="w-3 h-3" />
          {trendLabel}
        </span>
      </div>
    </div>
  );
});
