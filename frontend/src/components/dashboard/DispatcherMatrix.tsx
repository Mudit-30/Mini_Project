"use client";

import React, { useEffect, useState } from "react";
import { Cpu } from "lucide-react";
import { API } from "@/lib/api";

interface DispatcherMeta {
  model_type?: string;
  evaluation?: string;
  using_model?: boolean;
  labels: string[];
  matrix: number[][]; // rows = reward-optimal action, cols = policy action
  samples?: number;
  agreement?: number;
  error?: string;
}

const SHORT: Record<string, string> = { defer: "Defer", dispatch: "Dispatch" };

export function DispatcherMatrix() {
  const [meta, setMeta] = useState<DispatcherMeta | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    fetch(`${API}/api/v1/dispatcher/metadata`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d) => (d?.error ? setFailed(true) : setMeta(d)))
      .catch(() => setFailed(true));
  }, []);

  if (failed || !meta?.matrix) {
    return (
      <div className="card card-hover p-6">
        <div className="flex items-center gap-2 mb-3">
          <Cpu className="w-4 h-4 text-accent" />
          <h2 className="section-label">Dispatcher DQN — Decision Matrix</h2>
        </div>
        <p className="text-sm text-muted py-6 text-center">
          {failed ? "Dispatcher evaluation unavailable — is the backend running?" : "Evaluating policy…"}
        </p>
      </div>
    );
  }

  const labels = meta.labels;
  const m = meta.matrix;
  const rowTotals = m.map((row) => row.reduce((a, b) => a + b, 0));

  return (
    <div className="card card-hover p-6">
      <div className="flex items-center gap-2 mb-1">
        <Cpu className="w-4 h-4 text-accent" />
        <h2 className="section-label">Dispatcher DQN — Decision Matrix</h2>
      </div>
      <p className="text-[11px] text-faint mb-5">
        RL has no labelled ground truth — this compares the policy against the{" "}
        <span className="text-foreground">reward-optimal</span> action over{" "}
        {meta.samples ?? "—"} held-out states.
      </p>

      <div className="flex flex-wrap items-baseline gap-3 mb-5">
        <div>
          <span className="stat-num font-display text-3xl font-bold text-accent-2">
            {((meta.agreement ?? 0) * 100).toFixed(1)}%
          </span>
          <span className="text-xs text-muted ml-1">policy ↔ optimal agreement</span>
        </div>
        <span className={`chip font-mono text-[10px] ${meta.using_model ? "text-accent-2" : "text-carbon-mixed"}`}>
          {meta.using_model ? "DQN weights" : "heuristic fallback"}
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="text-xs font-mono border-collapse">
          <thead>
            <tr>
              <th className="p-1.5 text-faint font-medium text-right">optimal ↓ / policy →</th>
              {labels.map((l) => (
                <th key={l} className="p-1.5 text-muted font-semibold text-center">
                  {SHORT[l] ?? l}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {m.map((row, i) => (
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
                      style={{ backgroundColor: bg, minWidth: "56px" }}
                      title={`${cell} states where optimal=${labels[i]}, policy chose ${labels[j]}`}
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
        Diagonal = the learned policy matched the reward-optimal choice. Optimal here =
        dispatch only when a task is queued <em>and</em> an idle node exists (per the
        training reward); the guardrails then layer carbon-aware deferral on top at runtime.
      </p>
    </div>
  );
}
