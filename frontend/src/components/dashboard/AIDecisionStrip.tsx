"use client";

import React from "react";
import { motion } from "framer-motion";
import { Brain } from "lucide-react";
import type { Override } from "@/lib/types";

export const AIDecisionStrip = React.memo(function AIDecisionStrip({
  reason,
  override,
}: {
  reason: string;
  override: Override;
}) {
  if (!reason) return null;
  return (
    <motion.div
      variants={{ hidden: { opacity: 0, y: 20 }, show: { opacity: 1, y: 0 } }}
      className="card px-5 py-3 mb-8 flex items-center gap-3 flex-wrap"
    >
      <Brain className="w-4 h-4 text-accent shrink-0" />
      <h2 className="section-label shrink-0">AI Decision</h2>
      <span className="text-sm text-foreground flex-1 min-w-[200px]">{reason}</span>
      {override && (
        <span
          title="A safety guardrail overrode the learned DQN policy"
          className={`chip font-mono shrink-0 ${
            override === "urgent" ? "text-carbon-dirty" : "text-carbon-clean"
          }`}
        >
          ⚠ Guardrail: {override === "urgent" ? "urgent override" : "clean-grid override"}
        </span>
      )}
    </motion.div>
  );
});
