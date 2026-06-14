"use client";

import React from "react";
import { motion } from "framer-motion";
import type { LucideIcon } from "lucide-react";
import { NumberTicker } from "@/components/magicui/number-ticker";

interface StatCardProps {
  title: string;
  value: number | string;
  icon: LucideIcon;
  color?: string;
  pulse?: boolean;
}

export const StatCard = React.memo(function StatCard({
  title,
  value,
  icon: Icon,
  color = "text-accent",
  pulse,
}: StatCardProps) {
  let displayValue: number | string = value;
  let suffix = "";
  if (typeof value === "string" && value.endsWith("%")) {
    const num = parseFloat(value);
    if (!isNaN(num)) {
      displayValue = num;
      suffix = "%";
    }
  }
  const isNum = typeof displayValue === "number";

  return (
    <motion.div whileHover={{ y: -3 }} className="card card-hover p-5 relative overflow-hidden group">
      {/* shine sweep on hover */}
      <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/[0.06] to-transparent -translate-x-[120%] group-hover:translate-x-[120%] transition-transform duration-1000 pointer-events-none" />
      <div className="flex items-center justify-between mb-3 relative z-10">
        <span className="section-label">{title}</span>
        <Icon className={`w-4 h-4 ${color}`} />
      </div>
      {isNum ? (
        <div className={`stat-num text-4xl font-bold relative z-10 flex items-baseline ${pulse ? "text-accent" : "text-foreground"}`}>
          <NumberTicker value={displayValue as number} />
          <span className="text-2xl ml-0.5 text-muted">{suffix}</span>
        </div>
      ) : (
        <div className={`font-display text-lg font-semibold relative z-10 truncate ${pulse ? "text-accent" : "text-foreground"}`}>
          {displayValue}
        </div>
      )}
    </motion.div>
  );
});
