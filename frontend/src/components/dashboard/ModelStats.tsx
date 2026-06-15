"use client";

import React, { useEffect, useState } from "react";
import { Gauge, Layers, Target } from "lucide-react";
import { API } from "@/lib/api";

interface ClassMetrics {
  precision: number;
  recall: number;
  "f1-score": number;
  support: number;
}

interface ObserverMeta {
  model_name?: string;
  accuracy: number;
  test_samples?: number;
  classification_report?: Record<string, ClassMetrics | number>;
  feature_columns?: string[];
  hyperparameters?: { rf_n_estimators?: number; rf_max_depth?: number | null };
}

const SHORT: Record<string, string> = {
  idle: "Idle",
  active_user: "Active User",
  busy_hardware: "Busy Hardware",
  "macro avg": "Macro Avg",
  "weighted avg": "Weighted Avg",
};

const COLOR: Record<string, string> = {
  idle: "var(--accent-2)",
  active_user: "var(--carbon-mixed)",
  busy_hardware: "var(--carbon-dirty)",
};

// A compact metric bar (0–1 → 0–100%).
function Metric({ value, color }: { value: number; color: string }) {
  const pct = Math.round((Number(value) || 0) * 100);
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 rounded-full bg-white/10 overflow-hidden min-w-[40px]">
        <div className="h-full rounded-full" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="font-mono text-xs text-foreground w-9 text-right">{pct}%</span>
    </div>
  );
}

export function ModelStats() {
  const [meta, setMeta] = useState<ObserverMeta | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    fetch(`${API}/api/v1/observer/metadata`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(setMeta)
      .catch(() => setFailed(true));
  }, []);

  const report = meta?.classification_report;
  // Per-class rows (skip the aggregate scalar 'accuracy' entry).
  const classRows = report
    ? Object.entries(report).filter(
        ([k, v]) => typeof v === "object" && k !== "macro avg" && k !== "weighted avg"
      )
    : [];
  const macro = report?.["macro avg"];

  return (
    <div className="card card-hover p-6">
      <div className="flex items-center gap-2 mb-1">
        <Target className="w-4 h-4 text-accent" />
        <h2 className="section-label">Observer AI — Performance Metrics</h2>
      </div>
      <p className="text-[11px] text-faint mb-5">
        Per-class precision / recall / F1 on the held-out test set
        {meta?.test_samples ? ` (${meta.test_samples} samples)` : ""}.
      </p>

      {failed || !report || classRows.length === 0 ? (
        <p className="text-sm text-muted py-6 text-center">
          {failed ? "Observer metadata unavailable — is the backend running?" : "Loading metrics…"}
        </p>
      ) : (
        <>
          {/* Headline accuracy chips */}
          <div className="flex flex-wrap gap-2 mb-5">
            <span className="chip font-mono text-accent-2">
              <Gauge className="w-3.5 h-3.5" /> {(meta!.accuracy * 100).toFixed(1)}% accuracy
            </span>
            {typeof macro === "object" && (
              <span className="chip font-mono text-foreground">
                F1 {((macro as ClassMetrics)["f1-score"] * 100).toFixed(1)}% (macro)
              </span>
            )}
            {meta?.feature_columns && (
              <span className="chip font-mono text-muted">
                <Layers className="w-3.5 h-3.5" /> {meta.feature_columns.length} features
              </span>
            )}
            {meta?.hyperparameters?.rf_n_estimators && (
              <span className="chip font-mono text-muted">
                RandomForest · {meta.hyperparameters.rf_n_estimators} trees
              </span>
            )}
          </div>

          {/* Per-class metric grid */}
          <div className="space-y-4">
            <div className="grid grid-cols-[120px_1fr_1fr_1fr] gap-3 text-[10px] uppercase tracking-wider text-faint font-semibold">
              <span>Class</span>
              <span>Precision</span>
              <span>Recall</span>
              <span>F1</span>
            </div>
            {classRows.map(([cls, m]) => {
              const cm = m as ClassMetrics;
              const color = COLOR[cls] ?? "var(--accent)";
              return (
                <div key={cls} className="grid grid-cols-[120px_1fr_1fr_1fr] gap-3 items-center">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="w-2 h-2 rounded-full shrink-0" style={{ background: color }} />
                    <span className="text-sm text-foreground truncate">{SHORT[cls] ?? cls}</span>
                  </div>
                  <Metric value={cm.precision} color={color} />
                  <Metric value={cm.recall} color={color} />
                  <Metric value={cm["f1-score"]} color={color} />
                </div>
              );
            })}
          </div>

          <p className="text-[10px] text-faint mt-5 leading-relaxed">
            <span className="text-accent-2">Precision</span> = of the laptops it called this state, how
            many were right. <span className="text-accent-2">Recall</span> = of the laptops actually in
            this state, how many it caught. High recall on <em>active user</em> is what protects people
            from interruption.
          </p>
        </>
      )}
    </div>
  );
}
