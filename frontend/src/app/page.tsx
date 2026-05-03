"use client";

import React, { useEffect, useRef, useState } from "react";
import {
  Activity,
  Cpu,
  Database,
  LayoutDashboard,
  Monitor,
  Zap,
  AlertCircle,
  Clock,
  Shield,
  Wind,
  ListChecks,
  PlusCircle,
  CheckCircle2,
  XCircle,
  Loader2,
} from "lucide-react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

// ── Types ──────────────────────────────────────────────────────────────────────

interface NodeTelemetry {
  cpu_usage_pct: number;
  ram_usage_pct: number;
  state: "idle" | "active_user" | "busy_hardware" | "unknown";
  last_seen: string;
}

interface Node {
  node_id: string;
  telemetry: NodeTelemetry;
}

interface CarbonPoint {
  t: string;      // "HH:MM:SS"
  v: number;      // 0–1 carbon intensity
  pct: number;    // 0–100 for display
}

interface DispatchEvent {
  id: number;
  time: string;
  strategy: string;
  carbon: number;
  queue: number;
}

interface Task {
  id: number;
  name: string;
  command: string | null;
  priority: number;
  status: string;
  assigned_node: string | null;
  submitted_at: string | null;
  dispatched_at: string | null;
}

const API = "http://localhost:8000";

// ── Task Panel ────────────────────────────────────────────────────────────────
function TaskPanel() {
  const [name, setName]         = useState("");
  const [cmd,  setCmd]          = useState("");
  const [prio, setPrio]         = useState("5");
  const [tasks, setTasks]       = useState<Task[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [flash, setFlash]       = useState<string | null>(null);

  const loadTasks = async () => {
    try {
      const res = await fetch(`${API}/api/v1/tasks?limit=10`);
      if (!res.ok) return;
      const data = await res.json();
      setTasks(data.tasks ?? []);
    } catch { /* backend offline */ }
  };

  useEffect(() => { loadTasks(); const t = setInterval(loadTasks, 4000); return () => clearInterval(t); }, []);

  const submit = async () => {
    if (!name.trim()) { setFlash("Task name is required."); return; }
    setSubmitting(true);
    try {
      const res = await fetch(`${API}/api/v1/tasks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim(), command: cmd.trim() || null, priority: Number(prio) }),
      });
      if (!res.ok) throw new Error(await res.text());
      setName(""); setCmd(""); setPrio("5");
      setFlash("✓ Task queued — Dispatcher AI will pick it up shortly.");
      loadTasks();
    } catch (e: any) {
      setFlash(`✗ ${e.message}`);
    } finally {
      setSubmitting(false);
      setTimeout(() => setFlash(null), 4000);
    }
  };

  const cancel = async (id: number) => {
    try {
      await fetch(`${API}/api/v1/tasks/${id}`, { method: "DELETE" });
      loadTasks();
    } catch { /* ignore */ }
  };

  const statusColor: Record<string, string> = {
    pending:    "text-yellow-400",
    dispatched: "text-blue-400",
    completed:  "text-emerald-400",
    failed:     "text-red-400",
  };
  const statusDot: Record<string, string> = {
    pending:    "bg-yellow-400",
    dispatched: "bg-blue-400 animate-pulse",
    completed:  "bg-emerald-400",
    failed:     "bg-red-400",
  };

  return (
    <div className="glass p-6 flex flex-col gap-5">
      <div className="flex items-center gap-2 text-gray-300">
        <PlusCircle className="w-5 h-5" />
        <h2 className="text-xs md:text-sm font-bold uppercase tracking-wider">Submit Compute Task</h2>
      </div>

      {/* Form */}
      <div className="space-y-3">
        <input
          id="task-name"
          className="w-full bg-white/10 border border-white/20 rounded-lg px-4 py-3 text-base text-white placeholder-gray-400 focus:outline-none focus:border-blue-400 transition-colors"
          placeholder="Task name (e.g. Train ResNet Epoch 5)"
          value={name}
          onChange={e => setName(e.target.value)}
        />
        <input
          id="task-cmd"
          className="w-full bg-white/10 border border-white/20 rounded-lg px-4 py-3 text-sm font-mono text-white placeholder-gray-400 focus:outline-none focus:border-blue-400 transition-colors"
          placeholder="Command (optional, e.g. python train.py)"
          value={cmd}
          onChange={e => setCmd(e.target.value)}
        />
        <div className="flex items-center gap-3">
          <label className="text-xs text-gray-400 font-semibold uppercase tracking-wider shrink-0">Priority</label>
          <input
            id="task-priority"
            type="range" min="1" max="10" step="1"
            value={prio}
            onChange={e => setPrio(e.target.value)}
            className="flex-1 accent-blue-500"
          />
          <span className="text-sm font-mono font-bold text-gray-200 w-6 text-right">{prio}</span>
        </div>
        <button
          id="task-submit-btn"
          onClick={submit}
          disabled={submitting}
          className="w-full flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-500 disabled:bg-blue-900 disabled:text-blue-600 rounded-lg py-3 text-base font-bold transition-colors"
        >
          {submitting ? <Loader2 className="w-5 h-5 animate-spin" /> : <PlusCircle className="w-5 h-5" />}
          {submitting ? "Queueing…" : "Queue Task"}
        </button>
        {flash && (
          <p className={`text-sm font-mono font-semibold ${flash.startsWith("✓") ? "text-emerald-400" : "text-red-400"}`}>{flash}</p>
        )}
      </div>

      {/* Task list */}
      <div className="border-t border-white/10 pt-4">
        <p className="text-xs text-gray-400 font-semibold uppercase tracking-wider mb-3">Recent Tasks</p>
        {tasks.length === 0 ? (
          <p className="text-gray-400 text-sm text-center py-5">No tasks yet — submit one above.</p>
        ) : (
          <div className="space-y-2 max-h-[250px] overflow-y-auto pr-1 scrollbar-thin">
            {tasks.map(t => (
              <div key={t.id} className="flex items-center gap-3 p-3 rounded-lg bg-white/[0.03] border border-white/10 hover:bg-white/[0.06] transition-colors">
                <div className={`w-2 h-2 rounded-full shrink-0 ${statusDot[t.status] ?? "bg-gray-500"}`} />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-bold text-white truncate">{t.name}</p>
                  <p className={`text-xs font-mono font-medium ${statusColor[t.status] ?? "text-gray-300"} mt-0.5`}>
                    {t.status.toUpperCase()}{t.assigned_node ? ` → ${t.assigned_node}` : ""} · P{t.priority}
                  </p>
                </div>
                {t.status === "pending" && (
                  <button onClick={() => cancel(t.id)} title="Cancel" className="text-gray-500 hover:text-red-400 transition-colors shrink-0">
                    <XCircle className="w-5 h-5" />
                  </button>
                )}
                {t.status === "completed" && <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Sub-components ─────────────────────────────────────────────────────────────

const StatCard = ({ title, value, icon: Icon, color, pulse }: any) => (
  <div className="glass p-6 glass-hover transition-all">
    <div className="flex items-center justify-between mb-4">
      <span className="text-gray-300 text-xs font-bold uppercase tracking-wider">{title}</span>
      <Icon className={`w-5 h-5 ${color}`} />
    </div>
    <div className={`text-3xl font-black ${pulse ? "animate-pulse text-yellow-400" : "text-white"}`}>{value}</div>
  </div>
);

const CarbonGauge = ({ value }: { value: number }) => {
  const pct = Math.round(value * 100);
  const isClean = value < 0.4;
  const isMid   = value < 0.65;
  const color   = isClean ? "#10b981" : isMid ? "#f59e0b" : "#ef4444";
  const label   = isClean ? "CLEAN ✦" : isMid ? "MIXED" : "DIRTY ⚠";

  return (
    <div className="glass p-6 flex flex-col items-center justify-center gap-3">
      <span className="text-xs font-bold text-gray-300 uppercase tracking-wider flex items-center gap-1.5 mb-2">
        <Wind className="w-4 h-4" /> Grid Carbon
      </span>
      <div className="relative w-36 h-18 overflow-hidden">
        {/* semi-circle track */}
        <svg viewBox="0 0 120 60" className="w-full h-full">
          <path d="M10,60 A50,50 0 0,1 110,60" fill="none" stroke="#ffffff10" strokeWidth="12" strokeLinecap="round" />
          <path
            d="M10,60 A50,50 0 0,1 110,60"
            fill="none"
            stroke={color}
            strokeWidth="12"
            strokeLinecap="round"
            strokeDasharray={`${pct * 1.57} 157`}
            style={{ transition: "stroke-dasharray 0.8s ease, stroke 0.8s ease" }}
          />
          <text x="60" y="55" textAnchor="middle" fill="white" fontSize="18" fontWeight="900">{pct}%</text>
        </svg>
      </div>
      <span className="text-sm font-bold mt-1" style={{ color }}>{label}</span>
    </div>
  );
};

const NodeCard = ({ node }: { node: Node }) => {
  const colors: Record<string, string> = {
    idle: "bg-emerald-500",
    active_user: "bg-yellow-500",
    busy_hardware: "bg-red-500",
    unknown: "bg-gray-500",
  };
  return (
    <div className="glass p-6 glass-hover">
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-4">
          <div className="p-2.5 bg-blue-500/10 rounded-xl">
            <Monitor className="text-blue-400 h-6 w-6" />
          </div>
          <div>
            <h3 className="font-bold text-base text-white">{node.node_id}</h3>
            <p className="text-xs text-gray-400">Live Telemetry</p>
          </div>
        </div>
        <div className="flex items-center gap-2.5">
          <span className={`w-2.5 h-2.5 rounded-full ${colors[node.telemetry.state]} animate-pulse`} />
          <span className="text-xs uppercase font-mono tracking-wider text-gray-300">
            {node.telemetry.state}
          </span>
        </div>
      </div>
      <div className="space-y-4">
        {[
          { label: "CPU", value: node.telemetry.cpu_usage_pct, color: "bg-blue-500" },
          { label: "RAM", value: node.telemetry.ram_usage_pct, color: "bg-purple-500" },
        ].map(({ label, value, color }) => (
          <div key={label}>
            <div className="flex justify-between text-xs mb-1.5">
              <span className="text-gray-400">{label} Usage</span>
              <span className="font-mono text-gray-200">{value.toFixed(1)}%</span>
            </div>
            <div className="w-full bg-white/10 h-2 rounded-full overflow-hidden">
              <div className={`${color} h-full rounded-full transition-all duration-500`} style={{ width: `${value}%` }} />
            </div>
          </div>
        ))}
      </div>
      <div className="mt-5 pt-4 border-t border-white/10 flex items-center justify-between text-xs text-gray-400 font-mono">
        <div className="flex items-center gap-1.5"><Clock className="w-3.5 h-3.5" /><span>Last Seen</span></div>
        <span>{new Date(node.telemetry.last_seen).toLocaleTimeString()}</span>
      </div>
    </div>
  );
};

// ── Custom Tooltip for Carbon Chart ───────────────────────────────────────────

const CarbonTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  const v = payload[0].value;
  const color = v < 40 ? "#10b981" : v < 65 ? "#f59e0b" : "#ef4444";
  return (
    <div className="bg-black/90 border border-white/10 rounded-lg px-3 py-2 text-xs">
      <p className="text-gray-400 mb-1">{label}</p>
      <p className="font-bold" style={{ color }}>{v}% intensity</p>
    </div>
  );
};

// ── Main Page ──────────────────────────────────────────────────────────────────

const MAX_HISTORY = 40;

export default function DashboardPage() {
  const [nodes, setNodes]               = useState<Node[]>([]);
  const [loading, setLoading]           = useState(true);
  const [error, setError]               = useState<string | null>(null);
  const [strategy, setStrategy]         = useState("IDLE — Awaiting Data");
  const [tasksQueued, setTasksQueued]   = useState(0);
  const [carbonSavings, setCarbonSavings] = useState("0%");
  const [carbonIntensity, setCarbonIntensity] = useState(0.5);
  const [carbonHistory, setCarbonHistory] = useState<CarbonPoint[]>([]);
  const [dispatchLog, setDispatchLog]   = useState<DispatchEvent[]>([]);
  const eventId = useRef(0);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchNodes = async () => {
    try {
      const res = await fetch("http://localhost:8000/api/v1/nodes");
      if (!res.ok) throw new Error("Failed to fetch nodes");
      const data = await res.json();
      const arr = Object.entries(data.nodes || {}).map(([id, t]: any) => ({ node_id: id, telemetry: t }));
      setNodes(arr);
      setError(null);
    } catch (e: any) { setError(e.message); }
    finally { setLoading(false); }
  };

  const pushCarbonPoint = (v: number) => {
    const now = new Date().toLocaleTimeString("en-GB");
    setCarbonHistory(prev => {
      const next = [...prev, { t: now, v, pct: Math.round(v * 100) }];
      return next.length > MAX_HISTORY ? next.slice(-MAX_HISTORY) : next;
    });
  };

  const pushDispatchEvent = (strat: string, carbon: number, queue: number) => {
    if (strat === strategy) return; // skip duplicates
    const now = new Date().toLocaleTimeString("en-GB");
    setDispatchLog(prev => {
      const entry: DispatchEvent = { id: ++eventId.current, time: now, strategy: strat, carbon, queue };
      return [entry, ...prev].slice(0, 20);
    });
  };

  useEffect(() => {
    const socket = new WebSocket("ws://localhost:8000/ws/telemetry");

    socket.onopen  = () => { setError(null); fetchNodes(); };
    socket.onerror = () => {
      setError("WebSocket failed — polling REST API…");
      setLoading(false);
      pollingRef.current = setInterval(fetchNodes, 3000);
    };
    socket.onclose = () => console.log("WS closed");

    socket.onmessage = (ev) => {
      const data = JSON.parse(ev.data);

      if (data.type === "initial_state") {
        const arr = (data.nodes ?? []).map((n: any) => ({ node_id: n.node_id, telemetry: n }));
        setNodes(arr);
        setLoading(false);
      } else if (data.type === "node_update") {
        setLoading(false);
        setNodes(prev => {
          const idx = prev.findIndex(n => n.node_id === data.node.node_id);
          const updated = { node_id: data.node.node_id, telemetry: data.node };
          if (idx !== -1) { const a = [...prev]; a[idx] = updated; return a; }
          return [...prev, updated];
        });
      } else if (data.type === "node_remove") {
        setNodes(prev => prev.filter(n => n.node_id !== data.node_id));
      } else if (data.type === "dispatcher_update") {
        setLoading(false);
        const ci = data.carbon_intensity ?? 0.5;
        setStrategy(data.strategy);
        setTasksQueued(data.queue_size);
        setCarbonSavings(data.carbon_savings);
        setCarbonIntensity(ci);
        pushCarbonPoint(ci);
        pushDispatchEvent(data.strategy, ci, data.queue_size);
      }
    };

    return () => {
      socket.close();
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const idleCount  = nodes.filter(n => n.telemetry.state === "idle").length;
  const isDispatch = strategy.includes("DISPATCH");

  if (loading && nodes.length === 0) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="flex flex-col items-center gap-4">
          <Activity className="w-8 h-8 text-blue-500 animate-spin" />
          <p className="text-gray-400 font-medium">Connecting to GridMind Server…</p>
        </div>
      </div>
    );
  }

  // Carbon chart gradient stop colour
  const gradColor = carbonIntensity < 0.4 ? "#10b981" : carbonIntensity < 0.65 ? "#f59e0b" : "#ef4444";

  return (
    <main className="p-8 max-w-7xl mx-auto">

      {/* ── Header ── */}
      <header className="flex flex-col md:flex-row md:items-center justify-between gap-5 mb-10">
        <div>
          <div className="flex items-center gap-2 mb-2 text-blue-400">
            <Zap className="w-5 h-5 fill-current" />
            <span className="text-sm font-bold uppercase tracking-widest">Master Node</span>
          </div>
          <h1 className="text-5xl lg:text-6xl font-black tracking-tight text-white drop-shadow-md">GridMind Central</h1>
          <p className="text-sm text-gray-400 font-mono mt-3">Carbon-Aware Distributed Scheduler — Phase 4 Live Validation</p>
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <div className="glass px-5 py-3 rounded-xl flex items-center gap-3">
            <div className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
            <span className="text-xs font-mono font-semibold text-gray-300">SERVER ONLINE</span>
            <div className="w-px h-5 bg-white/20" />
            <span className="text-sm font-mono text-emerald-400 font-bold">{nodes.length}</span>
            <span className="text-xs font-mono font-semibold text-gray-300">NODES</span>
          </div>
          <div className="glass px-5 py-3 rounded-xl flex items-center gap-2">
            <Zap className="w-4 h-4 text-emerald-400" />
            <span className="text-xs font-mono font-bold text-white tracking-wide">AUTOPILOT: ACTIVE</span>
          </div>
        </div>
      </header>

      {/* ── Error Banner ── */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-4 flex items-center gap-3 mb-8">
          <AlertCircle className="text-red-500 h-5 w-5 shrink-0" />
          <p className="text-red-200 text-sm">{error} — Check if FastAPI server is running.</p>
        </div>
      )}

      {/* ── Summary Stats ── */}
      <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-5 gap-4 mb-8">
        <StatCard title="Active Nodes"     value={nodes.length}  icon={Monitor}    color="text-blue-400" />
        <StatCard title="Idle Capacity"    value={idleCount}     icon={Cpu}        color="text-emerald-400" />
        <StatCard title="Tasks Queued"     value={tasksQueued}   icon={Database}   color="text-purple-400" />
        <StatCard title="Carbon Saved"     value={carbonSavings} icon={Zap}        color="text-yellow-400" />
        <StatCard
          title="AI Strategy"
          value={isDispatch ? strategy : strategy.split("—")[0].trim()}
          icon={Shield}
          color="text-blue-400"
          pulse={isDispatch}
        />
      </div>

      {/* ── Carbon Gauge + Intensity Chart ── */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 mb-8">
        {/* Gauge */}
        <CarbonGauge value={carbonIntensity} />

        {/* Rolling Carbon Chart */}
        <div className="glass p-6 lg:col-span-3">
          <div className="flex items-center gap-2 mb-5">
            <Wind className="w-5 h-5 text-emerald-400" />
            <h2 className="text-xs font-bold uppercase tracking-wider text-gray-300">
              Live Grid Carbon Intensity — Rolling {MAX_HISTORY}s Window
            </h2>
          </div>
          {carbonHistory.length < 2 ? (
            <div className="h-[180px] flex items-center justify-center text-gray-600 text-sm">
              Waiting for dispatcher data…
            </div>
          ) : (
            <div className="h-[180px]">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={carbonHistory} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="carbonGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%"  stopColor={gradColor} stopOpacity={0.4} />
                      <stop offset="95%" stopColor={gradColor} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#ffffff08" vertical={false} />
                  <XAxis dataKey="t" stroke="#555" fontSize={9} interval="preserveStartEnd" />
                  <YAxis stroke="#555" fontSize={9} domain={[0, 100]} tickFormatter={(v) => `${v}%`} />
                  <Tooltip content={<CarbonTooltip />} />
                  <Area
                    type="monotone"
                    dataKey="pct"
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
      </div>

      {/* ── Node Grid + Dispatch Log ── */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6 mb-8">

        {/* Worker Nodes */}
        <div className="xl:col-span-2">
          <div className="flex items-center gap-2 mb-5 text-gray-300">
            <LayoutDashboard className="w-5 h-5" />
            <h2 className="text-xs font-bold uppercase tracking-wider">Worker Node Cluster</h2>
          </div>
          {nodes.length === 0 ? (
            <div className="glass p-12 text-center">
              <Monitor className="w-16 h-16 text-gray-600 mx-auto mb-4" />
              <p className="text-gray-400 text-base">No nodes connected yet.</p>
              <p className="text-gray-500 text-sm mt-2">Run <code className="bg-white/10 px-1.5 py-0.5 rounded text-gray-300">gridmind_node/agent.py</code> on worker laptops.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              {nodes.map(n => <NodeCard key={n.node_id} node={n} />)}
            </div>
          )}
        </div>

        {/* Dispatcher Action Log */}
        <div className="glass p-6 flex flex-col">
          <div className="flex items-center gap-2 mb-5 text-gray-300">
            <ListChecks className="w-5 h-5" />
            <h2 className="text-xs font-bold uppercase tracking-wider">Dispatcher Action Log</h2>
          </div>
          {dispatchLog.length === 0 ? (
            <div className="flex-1 flex items-center justify-center text-gray-500 text-sm">
              Awaiting first dispatch event…
            </div>
          ) : (
            <div className="space-y-2.5 overflow-y-auto max-h-[420px] pr-2 scrollbar-thin">
              {dispatchLog.map(ev => {
                const isD = ev.strategy.includes("DISPATCH");
                const isDef = ev.strategy.includes("DEFER");
                const dot = isD ? "bg-yellow-400" : isDef ? "bg-orange-400" : "bg-gray-500";
                return (
                  <div key={ev.id} className="flex items-start gap-3 p-3 rounded-lg bg-white/[0.03] border border-white/10 hover:bg-white/[0.06] transition-colors">
                    <div className={`w-2 h-2 rounded-full mt-1.5 shrink-0 ${dot}`} />
                    <div className="min-w-0">
                      <p className="text-sm font-bold text-white truncate">{ev.strategy}</p>
                      <p className="text-xs text-gray-400 font-mono mt-1 font-medium">
                        {ev.time} · Carbon {Math.round(ev.carbon * 100)}% · Q={ev.queue}
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* ── Task Queue Submission ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        <TaskPanel />
        <div className="glass p-6 flex flex-col justify-center items-center gap-4 text-center">
          <Zap className="w-12 h-12 text-blue-500/50" />
          <div>
            <p className="text-white font-bold text-lg mb-1">How the Task Loop Works</p>
            <p className="text-gray-400 text-sm mt-2 leading-relaxed max-w-sm">
              Submit a task above. Every 2 seconds the <span className="text-blue-400 font-semibold">Dispatcher AI</span> checks
              carbon intensity and node availability. When conditions are green, it picks the
              highest-priority pending task and assigns it to a safe idle node automatically.
            </p>
          </div>
          <div className="grid grid-cols-3 gap-4 w-full mt-4">
            {[
              { label: "Submit", icon: PlusCircle, color: "text-blue-400" },
              { label: "AI Decides", icon: Shield, color: "text-purple-400" },
              { label: "Dispatched", icon: CheckCircle2, color: "text-emerald-400" },
            ].map(({ label, icon: Icon, color }) => (
              <div key={label} className="bg-white/[0.03] border border-white/10 rounded-xl p-4 flex flex-col items-center gap-2 hover:bg-white/[0.05] transition-colors">
                <Icon className={`w-6 h-6 ${color}`} />
                <span className="text-xs text-gray-300 font-semibold uppercase tracking-wider">{label}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── System Load Trends ── */}
      <section>
        <div className="flex items-center gap-2 mb-5 text-gray-300">
          <Activity className="w-5 h-5" />
          <h2 className="text-xs font-bold uppercase tracking-wider">System Load Trends</h2>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {[
            { key: "cpu_usage_pct",  label: "Aggregate CPU Usage (%)",    id: "colorCpu", stroke: "#3b82f6" },
            { key: "ram_usage_pct",  label: "Aggregate Memory Load (%)",  id: "colorMem", stroke: "#8b5cf6" },
          ].map(({ key, label, id, stroke }) => (
            <div className="glass p-6" key={key}>
              <h3 className="text-gray-300 text-xs font-bold uppercase tracking-wider mb-5">{label}</h3>
              <div className="h-[240px]">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={nodes.map(n => ({ name: n.node_id, val: (n.telemetry as any)[key] }))} margin={{ left: -20 }}>
                    <defs>
                      <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%"  stopColor={stroke} stopOpacity={0.3} />
                        <stop offset="95%" stopColor={stroke} stopOpacity={0}   />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#ffffff08" vertical={false} />
                    <XAxis dataKey="name" stroke="#555" fontSize={9} />
                    <YAxis stroke="#555" fontSize={9} domain={[0, 100]} />
                    <Tooltip contentStyle={{ backgroundColor: "#000", border: "1px solid #333", borderRadius: "8px" }} itemStyle={{ color: stroke }} />
                    <Area type="monotone" dataKey="val" stroke={stroke} strokeWidth={2} fillOpacity={1} fill={`url(#${id})`} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
