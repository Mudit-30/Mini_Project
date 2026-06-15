"use client";

import { motion, AnimatePresence } from "framer-motion";
import {
  Activity,
  AlertCircle,
  Cpu,
  Database,
  LayoutDashboard,
  Monitor,
  Shield,
  Zap,
} from "lucide-react";
import { useGridMindSocket } from "@/hooks/useGridMindSocket";
import { StatCard } from "@/components/dashboard/StatCard";
import { CarbonGauge } from "@/components/dashboard/CarbonGauge";
import { CarbonChart } from "@/components/dashboard/CarbonChart";
import { CarbonProof } from "@/components/dashboard/CarbonProof";
import { CarbonForecastStrip } from "@/components/dashboard/CarbonForecastStrip";
import { AIDecisionStrip } from "@/components/dashboard/AIDecisionStrip";
import { NodeCard } from "@/components/dashboard/NodeCard";
import { DispatchLog } from "@/components/dashboard/DispatchLog";
import { TaskPanel } from "@/components/dashboard/TaskPanel";
import { JobPanel } from "@/components/dashboard/JobPanel";
import { ConfusionMatrix } from "@/components/dashboard/ConfusionMatrix";
import { ModelStats } from "@/components/dashboard/ModelStats";
import { SystemLoadTrends } from "@/components/dashboard/SystemLoadTrends";
import { LiveClock } from "@/components/dashboard/LiveClock";

const containerVariants = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.1 } },
};

const itemVariants = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0, transition: { type: "spring" as const, stiffness: 300, damping: 24 } },
};

// Map normalised grid intensity (0 = cleanest the grid gets, 1 = dirtiest) to a
// CONTINUOUS colour: green → amber → red. Using the relative position (not an
// absolute g/kWh threshold) is what makes the UI sweep through all colours as the
// grid cycles — the real CAISO data never drops below ~270 g/kWh, so absolute
// thresholds would pin everything to red.
function carbonColorFor(t: number): string {
  const c = Math.min(1, Math.max(0, t));
  const green = [46, 224, 122];
  const amber = [247, 183, 51];
  const red = [255, 90, 95];
  const [a, b, f] = c < 0.5 ? [green, amber, c / 0.5] : [amber, red, (c - 0.5) / 0.5];
  const ch = (i: number) => Math.round(a[i] + (b[i] - a[i]) * f);
  return `rgb(${ch(0)}, ${ch(1)}, ${ch(2)})`;
}

export default function DashboardPage() {
  const s = useGridMindSocket();

  const idleCount = s.nodes.filter((n) => n.telemetry?.state === "idle").length;
  const isDispatch = (s.strategy ?? "").includes("DISPATCH");

  if (s.loading && s.nodes.length === 0) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="aurora" />
        <div className="flex flex-col items-center gap-4 relative z-10">
          <Activity className="w-8 h-8 text-accent animate-spin" />
          <p className="text-muted font-display font-medium">Connecting to GridMind…</p>
        </div>
      </div>
    );
  }

  // Colour the whole UI by where the grid sits *within its recent range* (the last
  // ~rolling window of readings), not an absolute g/kWh threshold. The real CAISO
  // data never drops below ~270 g/kWh, so absolute thresholds pin it to red forever;
  // a relative scale makes the UI sweep green→amber→red as the grid actually moves.
  let t = s.carbonIntensity;
  if (s.carbonHistory.length >= 4 && s.carbonGco2 != null) {
    const vals = s.carbonHistory.map((p) => p.gco2);
    const lo = Math.min(...vals);
    const hi = Math.max(...vals);
    if (hi - lo > 1) t = Math.min(1, Math.max(0, (s.carbonGco2 - lo) / (hi - lo)));
  }
  const carbonColor = carbonColorFor(t);
  const carbonLabel = t < 0.4 ? "CLEAN" : t < 0.7 ? "MIXED" : "DIRTY";

  return (
    <div
      className="relative min-h-screen w-full overflow-hidden"
      style={{ ["--carbon-glow" as string]: carbonColor } as React.CSSProperties}
    >
      <div className="topbar" />
      <div className="grid-mesh" />
      <div className="aurora" />
      <motion.main
        initial="hidden"
        animate="show"
        variants={containerVariants}
        className="p-5 md:p-8 max-w-[1440px] mx-auto relative z-10"
      >
        {/* ── Header ── */}
        <motion.header
          variants={itemVariants}
          className="flex flex-col lg:flex-row lg:items-center justify-between gap-5 mb-8"
        >
          <div className="flex items-center gap-4">
            <div className="grid place-items-center w-12 h-12 rounded-2xl border border-accent/30 glow-accent" style={{ background: "color-mix(in srgb, var(--accent) 14%, transparent)" }}>
              <Zap className="w-6 h-6 text-accent" fill="currentColor" />
            </div>
            <div>
              <h1 className="font-display text-4xl lg:text-5xl font-bold tracking-tight text-foreground leading-none">
                Grid<span className="text-accent">Mind</span>
              </h1>
              <p className="text-xs text-muted font-mono mt-1.5 tracking-wide">Carbon-Aware Distributed Scheduler</p>
            </div>
          </div>
          <div className="flex items-center gap-2.5 flex-wrap">
            <span
              className="chip font-mono"
              style={{ color: "var(--carbon-glow)", borderColor: "color-mix(in srgb, var(--carbon-glow) 45%, transparent)" }}
            >
              <span className="w-2 h-2 rounded-full" style={{ background: "var(--carbon-glow)", boxShadow: "0 0 10px var(--carbon-glow)" }} />
              GRID {carbonLabel}{s.carbonGco2 != null ? ` · ${Math.round(s.carbonGco2)}g` : ""}
            </span>
            <LiveClock />
            <span className="chip font-mono text-foreground">
              <span className="stat-num text-accent text-sm">{s.nodes.length}</span>&nbsp;NODES
            </span>
            <span className="chip font-mono text-foreground">
              <Zap className="w-3.5 h-3.5 text-accent" /> AUTOPILOT
            </span>
          </div>
        </motion.header>

        {/* ── Error Banner ── */}
        {s.error && (
          <div className="card p-4 flex items-center gap-3 mb-8" style={{ borderColor: "color-mix(in srgb, var(--carbon-dirty) 40%, transparent)" }}>
            <AlertCircle className="text-carbon-dirty h-5 w-5 shrink-0" />
            <p className="text-sm text-muted">{s.error} — Check if the FastAPI server is running.</p>
          </div>
        )}

        {/* ── Summary Stats ── */}
        <motion.div variants={itemVariants} className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-5 gap-4 mb-8">
          <StatCard title="Active Nodes" value={s.nodes.length} icon={Monitor} color="text-accent" />
          <StatCard title="Idle Capacity" value={idleCount} icon={Cpu} color="text-accent-2" />
          <StatCard title="Tasks Queued" value={s.tasksQueued} icon={Database} color="text-muted" />
          <StatCard title="CO₂ Saved vs Naive" value={s.carbonSavings} icon={Zap} color="text-accent-2" />
          <StatCard
            title="AI Strategy"
            value={isDispatch ? s.strategy : s.strategy.split("—")[0].trim()}
            icon={Shield}
            color="text-accent"
            pulse={isDispatch}
          />
        </motion.div>

        {/* ── Explainable-AI decision strip (with guardrail transparency) ── */}
        <AIDecisionStrip reason={s.reason} override={s.override} />

        {/* ── 2-hour carbon forecast ── */}
        <CarbonForecastStrip forecast={s.forecast} cleanInMin={s.forecastCleanInMin} />

        {/* ── Carbon Gauge + Intensity Chart ── */}
        <motion.div variants={itemVariants} className="grid grid-cols-1 lg:grid-cols-4 gap-6 mb-8">
          <CarbonGauge value={s.carbonIntensity} gco2={s.carbonGco2} color={carbonColor} label={carbonLabel} />
          <CarbonChart history={s.carbonHistory} gco2={s.carbonGco2} intensity={s.carbonIntensity} />
        </motion.div>

        {/* ── Carbon Proof (the thesis, measured) ── */}
        <CarbonProof
          baselineG={s.carbonBaselineG}
          gridmindG={s.carbonGridmindG}
          savedG={s.carbonSavedG}
          tasksCounted={s.carbonTasksCounted}
        />

        {/* ── Node Grid + Dispatch Log ── */}
        <motion.div variants={itemVariants} className="grid grid-cols-1 xl:grid-cols-3 gap-6 mb-8">
          <div className="xl:col-span-2">
            <div className="flex items-center gap-2 mb-5 text-muted">
              <LayoutDashboard className="w-4 h-4 text-accent" />
              <h2 className="section-label">Worker Node Cluster</h2>
            </div>
            {s.nodes.length === 0 ? (
              <div className="card p-12 text-center">
                <Monitor className="w-16 h-16 text-faint mx-auto mb-4" />
                <p className="text-foreground text-base">No nodes connected yet.</p>
                <p className="text-muted text-sm mt-2">
                  Run <code className="bg-white/10 px-1.5 py-0.5 rounded text-foreground font-mono text-xs">gridmind_node/agent.py</code> on worker laptops.
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                <AnimatePresence>
                  {s.nodes.map((n) => (
                    <NodeCard key={n.node_id} node={n} />
                  ))}
                </AnimatePresence>
              </div>
            )}
          </div>

          <DispatchLog events={s.dispatchLog} />
        </motion.div>

        {/* ── Task submission + honest-ML panel ── */}
        <motion.div variants={itemVariants} className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
          <TaskPanel taskOutput={s.taskOutput} />
          <ConfusionMatrix />
        </motion.div>

        {/* ── Observer AI performance stats (precision/recall/F1 per class) ── */}
        <motion.div variants={itemVariants} className="mb-8">
          <ModelStats />
        </motion.div>

        {/* ── Parallel compute (data-parallel job splitting) ── */}
        <motion.div variants={itemVariants} className="mb-8">
          <JobPanel />
        </motion.div>

        {/* ── System Load Trends ── */}
        <motion.div variants={itemVariants}>
          <SystemLoadTrends nodes={s.nodes} />
        </motion.div>
      </motion.main>
    </div>
  );
}
