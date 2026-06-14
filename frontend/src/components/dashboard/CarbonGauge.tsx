"use client";

import React from "react";
import { motion } from "framer-motion";
import { Wind } from "lucide-react";
import { NumberTicker } from "@/components/magicui/number-ticker";

export const CarbonGauge = React.memo(function CarbonGauge({
  value,
  gco2,
  color,
  label,
}: {
  value: number;
  gco2: number | null;
  color: string;
  label: string;
}) {
  // Colour + label are computed once by the page (relative to the grid's range)
  // and shared with the header chip + aurora, so the gauge never disagrees.
  const pct = Math.round(value * 100);

  return (
    <motion.div whileHover={{ y: -3 }} className="card card-hero card-hover p-6 flex flex-col items-center justify-center gap-2">
      <div className="flex items-center gap-1.5 section-label">
        <Wind className="w-3.5 h-3.5" /> Marginal Carbon
      </div>
      <div className="relative w-44 h-[94px] overflow-hidden mt-1">
        <svg viewBox="0 0 120 60" className="w-full h-full">
          <path d="M10,60 A50,50 0 0,1 110,60" fill="none" stroke="rgba(255,255,255,0.07)" strokeWidth="11" strokeLinecap="round" />
          <path
            d="M10,60 A50,50 0 0,1 110,60"
            fill="none"
            stroke={color}
            strokeWidth="11"
            strokeLinecap="round"
            strokeDasharray={`${pct * 1.57} 157`}
            style={{ transition: "stroke-dasharray 0.9s ease, stroke 0.9s ease", filter: `drop-shadow(0 0 6px ${color})` }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-end pb-0.5">
          {gco2 !== null ? (
            <span className="flex items-baseline gap-1">
              <span className="stat-num text-3xl font-bold text-foreground">
                <NumberTicker value={Math.round(gco2)} />
              </span>
              <span className="text-[10px] text-muted font-mono">g/kWh</span>
            </span>
          ) : (
            <span className="stat-num text-3xl font-bold text-foreground">
              <NumberTicker value={pct} />%
            </span>
          )}
        </div>
      </div>
      <span
        className="chip mt-1 font-mono font-bold"
        style={{ color, borderColor: `color-mix(in srgb, ${color} 45%, transparent)`, background: `color-mix(in srgb, ${color} 10%, transparent)` }}
      >
        {label}
      </span>
    </motion.div>
  );
});
