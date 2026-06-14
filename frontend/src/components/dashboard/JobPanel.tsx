"use client";

import React, { useEffect, useRef, useState } from "react";
import { Boxes, Gauge, Loader2, Rocket } from "lucide-react";
import { API } from "@/lib/api";
import type { JobDetail, JobSummary } from "@/lib/types";

// One-click data-parallel demo: count primes in [2, 1e6), split across chunks.
const DEFAULT_SCRIPT = `import os, time

i = int(os.environ.get("GRIDMIND_CHUNK_INDEX", "0"))
n = int(os.environ.get("GRIDMIND_CHUNK_COUNT", "1"))

def is_prime(x):
    if x < 2: return False
    d = 2
    while d * d <= x:
        if x % d == 0: return False
        d += 1
    return True

MAX = 1_000_000
block = MAX // n
lo, hi = max(2, i * block), (MAX if i == n - 1 else (i + 1) * block)
t = time.time()
print(f"chunk {i+1}/{n}: scanning [{lo}, {hi})", flush=True)
c = sum(1 for x in range(lo, hi) if is_prime(x))
print(f"chunk {i+1}/{n}: {c} primes in {time.time()-t:.1f}s", flush=True)
`;

const CHUNK_DOT: Record<string, string> = {
  pending: "bg-carbon-mixed",
  dispatched: "bg-accent animate-pulse",
  running: "bg-accent animate-pulse",
  completed: "bg-carbon-clean",
  failed: "bg-carbon-dirty",
  aborted: "bg-carbon-dirty",
  cancelled: "bg-faint",
};

export function JobPanel() {
  const [name, setName] = useState("Prime Count (1M)");
  const [chunks, setChunks] = useState(4);
  const [script, setScript] = useState(DEFAULT_SCRIPT);
  const [submitting, setSubmitting] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [detail, setDetail] = useState<JobDetail | null>(null);
  const [recent, setRecent] = useState<JobSummary[]>([]);
  const activeRef = useRef<string | null>(null);
  activeRef.current = activeJobId;

  useEffect(() => {
    const poll = async () => {
      try {
        const list = await (await fetch(`${API}/api/v1/jobs`)).json();
        setRecent(list.jobs ?? []);
      } catch {
        /* backend offline */
      }
      const id = activeRef.current;
      if (id) {
        try {
          const d = await (await fetch(`${API}/api/v1/jobs/${id}`)).json();
          if (!d.detail && d.job_id) setDetail(d);
        } catch {
          /* ignore */
        }
      }
    };
    poll();
    const t = setInterval(poll, 1500);
    return () => clearInterval(t);
  }, []);

  const submit = async () => {
    if (!name.trim()) {
      setFlash("Job name is required.");
      return;
    }
    setSubmitting(true);
    try {
      const res = await fetch(`${API}/api/v1/jobs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim(), script, chunks, priority_str: "urgent" }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setActiveJobId(data.job_id);
      setDetail(null);
      setFlash(`✓ Split into ${data.chunk_count} chunks — fanning out across the cluster.`);
    } catch (e) {
      setFlash(`✗ ${e instanceof Error ? e.message : "Failed"}`);
    } finally {
      setSubmitting(false);
      setTimeout(() => setFlash(null), 4000);
    }
  };

  return (
    <div className="card p-6">
      <div className="flex items-center gap-2 mb-1">
        <Boxes className="w-4 h-4 text-accent" />
        <h2 className="section-label">Parallel Compute — split one job across the cluster</h2>
      </div>
      <p className="text-[11px] text-faint mb-5">
        One script, fanned out into N chunks (one per free idle node) via <code className="text-muted">GRIDMIND_CHUNK_INDEX</code>.
        Measured wall-clock vs serial = real speedup.
      </p>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Submit form */}
        <div className="space-y-3">
          <input
            className="w-full bg-white/10 border border-white/20 rounded-lg px-4 py-3 text-base text-foreground placeholder-muted focus:outline-none focus:border-accent"
            placeholder="Job name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <div className="flex items-center gap-3">
            <label className="section-label shrink-0">Chunks</label>
            <input
              type="range" min="2" max="8" step="1"
              value={chunks}
              onChange={(e) => setChunks(parseInt(e.target.value, 10))}
              className="flex-1 accent-accent"
            />
            <span className="text-sm font-mono font-bold text-foreground w-6 text-right">{chunks}</span>
          </div>
          <textarea
            rows={6}
            className="w-full bg-black/40 border border-white/15 rounded-lg px-3 py-2 text-[11px] font-mono text-accent-2 focus:outline-none focus:border-accent resize-y scrollbar-thin"
            value={script}
            onChange={(e) => setScript(e.target.value)}
            spellCheck={false}
          />
          <button
            onClick={submit}
            disabled={submitting}
            className="w-full flex items-center justify-center gap-2 bg-accent text-background font-semibold hover:opacity-90 disabled:opacity-50 rounded-lg py-3 text-base transition-opacity"
          >
            {submitting ? <Loader2 className="w-5 h-5 animate-spin" /> : <Rocket className="w-5 h-5" />}
            {submitting ? "Splitting…" : `Run across ${chunks} chunks`}
          </button>
          {flash && (
            <p className={`text-sm font-mono font-semibold ${flash.startsWith("✓") ? "text-accent-2" : "text-carbon-dirty"}`}>{flash}</p>
          )}
        </div>

        {/* Active job + speedup */}
        <div className="flex flex-col">
          {!detail ? (
            <div className="flex-1 flex items-center justify-center text-faint text-sm border border-dashed border-white/10 rounded-lg py-10">
              Submit a job to watch it fan out across the cluster.
            </div>
          ) : (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <p className="text-sm font-bold text-foreground truncate">{detail.name}</p>
                <span className="text-xs font-mono text-muted">{detail.completed}/{detail.total} done</span>
              </div>

              {/* Chunk grid */}
              <div className="flex flex-wrap gap-2">
                {detail.chunks.map((c) => (
                  <div
                    key={c.chunk_index}
                    title={`chunk ${c.chunk_index + 1}: ${c.status}${c.assigned_node ? " @ " + c.assigned_node : ""}${c.duration_secs ? ` (${c.duration_secs}s)` : ""}`}
                    className="chip font-mono text-[11px] text-muted"
                  >
                    <span className={`w-2 h-2 rounded-full ${CHUNK_DOT[c.status] ?? "bg-faint"}`} />
                    #{c.chunk_index + 1}
                    {c.duration_secs ? <span className="text-faint">{c.duration_secs}s</span> : null}
                  </div>
                ))}
              </div>

              {/* Speedup headline */}
              {detail.all_done && detail.speedup ? (
                <div className="card card-hero p-4 text-center">
                  <div className="flex items-center justify-center gap-1.5 section-label mb-1">
                    <Gauge className="w-4 h-4 text-accent" /> Measured Speedup
                  </div>
                  <div className="stat-num font-display text-4xl font-bold text-accent">{detail.speedup}×</div>
                  <div className="text-faint text-[11px] mt-1 font-mono">
                    {detail.wall_secs}s wall vs {detail.serial_secs}s serial · {detail.nodes_used.length} nodes
                  </div>
                </div>
              ) : detail.all_done ? (
                <div className="card p-4 text-center">
                  <div className="text-sm font-bold text-accent-2">
                    Completed on {detail.nodes_used.length} node{detail.nodes_used.length === 1 ? "" : "s"} · {detail.serial_secs}s compute
                  </div>
                  <div className="text-carbon-mixed text-[11px] mt-1">
                    Ran sequentially — connect ≥2 nodes to see real parallel speedup.
                  </div>
                </div>
              ) : (
                <div className="flex items-center gap-2 text-accent text-sm">
                  <Loader2 className="w-4 h-4 animate-spin" /> Running {detail.completed}/{detail.total} chunks across the cluster…
                </div>
              )}
            </div>
          )}

          {recent.length > 0 && (
            <div className="mt-4 pt-4 border-t border-white/10">
              <p className="section-label mb-2">Recent jobs</p>
              <div className="space-y-1.5 max-h-28 overflow-y-auto scrollbar-thin">
                {recent.map((j) => (
                  <button
                    key={j.job_id}
                    onClick={() => { setActiveJobId(j.job_id); setDetail(null); }}
                    className="w-full flex items-center justify-between text-left text-xs px-2 py-1.5 rounded bg-white/[0.03] hover:bg-white/[0.07] transition-colors"
                  >
                    <span className="text-muted truncate">{j.name}</span>
                    <span className="font-mono text-faint shrink-0 ml-2">{j.completed}/{j.total}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
