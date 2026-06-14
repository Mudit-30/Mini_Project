"use client";

import React from "react";
import { Wind } from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { CarbonPoint } from "@/lib/types";

interface TooltipProps {
  active?: boolean;
  payload?: { value: number }[];
  label?: string;
}

function CarbonTooltip({ active, payload, label }: TooltipProps) {
  if (!active || !payload?.length) return null;
  const v = payload[0].value;
  const color = v < 200 ? "#2ee07a" : v < 350 ? "#f7b733" : "#ff5a5f";
  return (
    <div className="card px-3 py-2 text-xs">
      <p className="text-muted mb-1">{label}</p>
      <p className="font-mono font-bold" style={{ color }}>
        {Math.round(v)} g CO₂/kWh
      </p>
    </div>
  );
}

export const CarbonChart = React.memo(function CarbonChart({
  history,
  gco2,
  intensity,
}: {
  history: CarbonPoint[];
  gco2: number | null;
  intensity: number;
}) {
  const gradColor =
    gco2 !== null
      ? gco2 < 200
        ? "#2ee07a"
        : gco2 < 350
        ? "#f7b733"
        : "#ff5a5f"
      : intensity < 0.4
      ? "#2ee07a"
      : intensity < 0.75
      ? "#f7b733"
      : "#ff5a5f";

  return (
    <div className="card card-hover p-6 lg:col-span-3">
      <div className="flex items-center gap-2 mb-5">
        <Wind className="w-4 h-4 text-accent" />
        <h2 className="section-label" title="WattTime Marginal Operating Emissions Rate">
          Live Marginal Carbon (MOER) — Rolling Window
        </h2>
      </div>
      {history.length < 2 ? (
        <div className="h-[180px] flex items-center justify-center text-faint text-sm">
          Waiting for dispatcher data…
        </div>
      ) : (
        <div className="h-[180px]">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={history} margin={{ top: 4, right: 4, left: -10, bottom: 0 }}>
              <defs>
                <linearGradient id="carbonGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={gradColor} stopOpacity={0.4} />
                  <stop offset="95%" stopColor={gradColor} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#ffffff0d" vertical={false} />
              <XAxis dataKey="t" stroke="#5b6475" fontSize={9} interval="preserveStartEnd" />
              <YAxis stroke="#5b6475" fontSize={9} domain={["auto", "auto"]} tickFormatter={(v) => `${Math.round(v)}`} />
              <Tooltip content={<CarbonTooltip />} />
              <Area
                type="monotone"
                dataKey="gco2"
                stroke={gradColor}
                strokeWidth={2}
                fillOpacity={1}
                fill="url(#carbonGrad)"
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
});
