"use client";

import React, { useEffect, useState } from "react";
import { Brain } from "lucide-react";
import { API } from "@/lib/api";

interface ObserverMeta {
  accuracy: number;
  train_accuracy?: number;
  test_samples?: number;
  confusion_matrix: number[][];
  confusion_matrix_labels: string[];
}

const SHORT: Record<string, string> = {
  idle: "idle",
  active_user: "active",
  busy_hardware: "busy",
};

export function ConfusionMatrix() {
  const [meta, setMeta] = useState<ObserverMeta | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    fetch(`${API}/api/v1/observer/metadata`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(setMeta)
      .catch(() => setFailed(true));
  }, []);

  if (failed || !meta?.confusion_matrix) {
    return (
      <div className="card card-hover p-6">
        <div className="flex items-center gap-2 mb-3">
          <Brain className="w-4 h-4 text-accent" />
          <h2 className="section-label">Observer AI — Honest Evaluation</h2>
        </div>
        <p className="text-sm text-muted py-6 text-center">
          {failed ? "Observer metadata unavailable — is the backend running?" : "Loading evaluation…"}
        </p>
      </div>
    );
  }

  const labels = meta.confusion_matrix_labels;
  const cm = meta.confusion_matrix;
  const rowTotals = cm.map((row) => row.reduce((a, b) => a + b, 0));

  return (
    <div className="card card-hover p-6">
      <div className="flex items-center gap-2 mb-1">
        <Brain className="w-4 h-4 text-accent" />
        <h2 className="section-label">Observer AI — Honest Evaluation</h2>
      </div>
      <p className="text-[11px] text-faint mb-5">
        Held-out test set ({meta.test_samples ?? "—"} samples it never trained on) — not training data.
      </p>

      <div className="flex items-baseline gap-4 mb-5">
        <div>
          <span className="stat-num font-display text-3xl font-bold text-accent-2">{(meta.accuracy * 100).toFixed(1)}%</span>
          <span className="text-xs text-muted ml-1">held-out accuracy</span>
        </div>
        {meta.train_accuracy !== undefined && (
          <div className="text-xs text-faint font-mono">train {(meta.train_accuracy * 100).toFixed(1)}%</div>
        )}
      </div>

      {/* Confusion matrix grid */}
      <div className="overflow-x-auto">
        <table className="text-xs font-mono border-collapse">
          <thead>
            <tr>
              <th className="p-1.5 text-faint font-medium text-right">actual ↓ / pred →</th>
              {labels.map((l) => (
                <th key={l} className="p-1.5 text-muted font-semibold text-center">
                  {SHORT[l] ?? l}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {cm.map((row, i) => (
              <tr key={i}>
                <td className="p-1.5 text-muted font-semibold text-right">{SHORT[labels[i]] ?? labels[i]}</td>
                {row.map((cell, j) => {
                  const frac = rowTotals[i] ? cell / rowTotals[i] : 0;
                  const isDiag = i === j;
                  const bg = isDiag
                    ? `rgba(46,224,122,${0.15 + frac * 0.55})`
                    : cell > 0
                    ? `rgba(255,90,95,${0.2 + frac * 0.6})`
                    : "rgba(255,255,255,0.02)";
                  return (
                    <td
                      key={j}
                      className={`p-1.5 text-center rounded ${isDiag ? "text-carbon-clean" : cell > 0 ? "text-carbon-dirty" : "text-faint"}`}
                      style={{ backgroundColor: bg, minWidth: "44px" }}
                      title={`${cell} ${labels[i]} → predicted ${labels[j]}`}
                    >
                      {cell}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-[10px] text-faint mt-4 leading-relaxed">
        Diagonal = correct. The costly error (a present-but-reading user mislabelled
        &ldquo;idle&rdquo;) is the <span className="text-carbon-dirty">active→idle</span> cell — kept small and further
        smoothed further by the temporal majority-vote filter in production.
      </p>
    </div>
  );
}
