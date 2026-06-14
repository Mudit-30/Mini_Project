"use client";

import React from "react";
import { motion } from "framer-motion";
import { ArrowRight, Leaf } from "lucide-react";
import { NumberTicker } from "@/components/magicui/number-ticker";

// Emissions are small per laptop task — show mg below 1 g so numbers read cleanly.
function fmtCO2(grams: number): string {
  return grams < 1 ? `${(grams * 1000).toFixed(grams < 0.1 ? 1 : 0)} mg` : `${grams.toFixed(2)} g`;
}

// Tangible equivalents (EPA-style factors): ~251 g CO₂/km for an avg passenger
// car, ~8.2 g CO₂ per smartphone charge. Meters (not km) keep the number readable.
function tangible(savedG: number): string {
  const meters = savedG / 0.251;
  const charges = savedG / 8.2;
  return `≈ ${charges.toFixed(charges < 10 ? 1 : 0)} phone charges · ${meters.toFixed(0)} m not driven`;
}

export const CarbonProof = React.memo(function CarbonProof({
  baselineG,
  gridmindG,
  savedG,
  tasksCounted,
}: {
  baselineG: number;
  gridmindG: number;
  savedG: number;
  tasksCounted: number;
}) {
  const savedPct = baselineG > 0 ? (savedG / baselineG) * 100 : 0;

  return (
    <motion.div variants={{ hidden: { opacity: 0, y: 20 }, show: { opacity: 1, y: 0 } }} className="card card-hero card-hover p-6 mb-8 relative overflow-hidden">
      {/* subtle green wash to signal "the green win" */}
      <div className="absolute inset-0 bg-gradient-to-br from-accent-2/5 via-transparent to-transparent pointer-events-none" />
      <div className="flex items-center gap-2 mb-1 relative z-10">
        <Leaf className="w-4 h-4 text-accent" />
        <h2 className="section-label">
          Carbon Proof — Measured vs a Naive &ldquo;Run-Now&rdquo; Scheduler
        </h2>
      </div>
      <p className="text-[11px] text-faint mb-5 relative z-10">
        Scored on <span className="text-muted">marginal emissions (WattTime MOER)</span> — the CO₂ of the
        <span className="text-muted"> next</span> MWh, which is what actually changes when you shift load.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-[1fr_auto_1.4fr_auto_1fr] gap-4 md:gap-2 items-center relative z-10">
        {/* Naive baseline */}
        <div className="text-center">
          <div className="section-label mb-1">Naive Scheduler</div>
          <div className="stat-num font-display text-2xl font-bold text-carbon-dirty font-mono">{fmtCO2(baselineG)}</div>
          <div className="text-faint text-[10px] mt-1">runs every task immediately</div>
        </div>

        <ArrowRight className="hidden md:block w-5 h-5 text-faint mx-auto" />

        {/* Saved % — the headline */}
        <div className="text-center py-2 md:py-0 border-y md:border-y-0 md:border-x border-white/10">
          <div className="section-label mb-1">CO₂ Avoided</div>
          <div className="stat-num font-display text-5xl font-bold text-accent-2 flex items-baseline justify-center" style={{ filter: "drop-shadow(0 0 12px rgba(52,211,153,0.35))" }}>
            <NumberTicker value={savedPct} decimalPlaces={1} />
            <span className="text-2xl ml-0.5">%</span>
          </div>
          <div className="text-faint text-[10px] mt-1">
            {fmtCO2(savedG)} saved · {tasksCounted} task{tasksCounted === 1 ? "" : "s"}
          </div>
          {savedG > 0 && (
            <div className="text-accent-2/70 text-[10px] mt-0.5">{tangible(savedG)}</div>
          )}
        </div>

        <ArrowRight className="hidden md:block w-5 h-5 text-accent-2 mx-auto" />

        {/* GridMind */}
        <div className="text-center">
          <div className="section-label mb-1">GridMind</div>
          <div className="stat-num font-display text-2xl font-bold text-accent-2 font-mono">{fmtCO2(gridmindG)}</div>
          <div className="text-faint text-[10px] mt-1">defers to clean-grid windows</div>
        </div>
      </div>

      {tasksCounted === 0 && (
        <p className="text-center text-faint text-xs mt-5 relative z-10">
          Submit and complete a task to start measuring real avoided emissions.
        </p>
      )}
    </motion.div>
  );
});
