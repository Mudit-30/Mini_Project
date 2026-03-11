"use client";

import React, { useEffect, useState } from "react";
import {
  Activity,
  Cpu,
  Database,
  LayoutDashboard,
  Monitor,
  Power,
  Zap,
  AlertCircle,
  Clock,
  Shield
} from "lucide-react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  AreaChart,
  Area
} from "recharts";

// --- Types ---

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

// --- Components ---

const StatCard = ({ title, value, icon: Icon, color }: any) => (
  <div className="glass p-6 glass-hover transition-all">
    <div className="flex items-center justify-between mb-4">
      <span className="text-gray-400 text-sm font-medium">{title}</span>
      <Icon className={`w-5 h-5 ${color}`} />
    </div>
    <div className="text-3xl font-bold">{value}</div>
  </div>
);

const NodeCard = ({ node }: { node: Node }) => {
  const getStatusColor = (state: string) => {
    switch (state) {
      case "idle": return "bg-green-500";
      case "active_user": return "bg-yellow-500";
      case "busy_hardware": return "bg-red-500";
      default: return "bg-gray-500";
    }
  };

  return (
    <div className="glass p-5 glass-hover">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-blue-500/10 rounded-lg">
            <Monitor className="text-blue-500 h-5 w-5" />
          </div>
          <div>
            <h3 className="font-bold">{node.node_id}</h3>
            <p className="text-xs text-gray-500">Live Telemetry</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${getStatusColor(node.telemetry.state)} animate-pulse`} />
          <span className="text-xs uppercase font-mono tracking-wider text-gray-400">
            {node.telemetry.state}
          </span>
        </div>
      </div>

      <div className="space-y-4">
        <div>
          <div className="flex justify-between text-xs mb-1">
            <span className="text-gray-400">CPU Usage</span>
            <span className="font-mono">{node.telemetry.cpu_usage_pct.toFixed(1)}%</span>
          </div>
          <div className="w-full bg-white/5 h-1.5 rounded-full overflow-hidden">
            <div
              className="bg-blue-500 h-full transition-all duration-500"
              style={{ width: `${node.telemetry.cpu_usage_pct}%` }}
            />
          </div>
        </div>

        <div>
          <div className="flex justify-between text-xs mb-1">
            <span className="text-gray-400">Memory Usage</span>
            <span className="font-mono">{node.telemetry.ram_usage_pct.toFixed(1)}%</span>
          </div>
          <div className="w-full bg-white/5 h-1.5 rounded-full overflow-hidden">
            <div
              className="bg-purple-500 h-full transition-all duration-500"
              style={{ width: `${node.telemetry.ram_usage_pct}%` }}
            />
          </div>
        </div>
      </div>

      <div className="mt-4 pt-4 border-t border-white/5 flex items-center justify-between text-[10px] text-gray-500 font-mono">
        <div className="flex items-center gap-1">
          <Clock className="w-3 h-3" />
          <span>Last Seen:</span>
        </div>
        <span>{new Date(node.telemetry.last_seen).toLocaleTimeString()}</span>
      </div>
    </div>
  );
};

export default function DashboardPage() {
  const [nodes, setNodes] = useState<Node[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchNodes = async () => {
    try {
      const response = await fetch("http://localhost:8000/api/v1/nodes");
      if (!response.ok) throw new Error("Failed to fetch nodes");
      const data = await response.json();

      // Transform object to array if needed
      const nodeArray = Object.entries(data.nodes || {}).map(([id, telemetry]: any) => ({
        node_id: id,
        telemetry: telemetry
      }));

      setNodes(nodeArray);
      setError(null);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const socket = new WebSocket("ws://localhost:8000/ws/telemetry");

    socket.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.type === "initial_state") {
        const nodeArray = data.nodes.map((node: any) => ({
          node_id: node.node_id,
          telemetry: node
        }));
        setNodes(nodeArray);
        setLoading(false);
      } else if (data.type === "node_update") {
        setNodes(prev => {
          const index = prev.findIndex(n => n.node_id === data.node.node_id);
          const newNode = { node_id: data.node.node_id, telemetry: data.node };
          if (index !== -1) {
            const updated = [...prev];
            updated[index] = newNode;
            return updated;
          }
          return [...prev, newNode];
        });
      } else if (data.type === "node_remove") {
        setNodes(prev => prev.filter(n => n.node_id !== data.node_id));
      }
    };

    socket.onopen = () => {
      console.log("Connected to GridMind WebSocket");
      setError(null);
    };

    socket.onerror = (err) => {
      console.error("WebSocket error", err);
      setError("WebSocket connection failed. Falling back to polling...");
      // Fallback to polling if WS fails
      const interval = setInterval(fetchNodes, 3000);
      return () => clearInterval(interval);
    };

    socket.onclose = () => {
      console.log("Disconnected from GridMind WebSocket");
    };

    return () => socket.close();
  }, []);

  if (loading && nodes.length === 0) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="flex flex-col items-center gap-4">
          <Activity className="w-8 h-8 text-blue-500 animate-spin" />
          <p className="text-gray-400 font-medium">Connecting to GridMind Server...</p>
        </div>
      </div>
    );
  }

  return (
    <main className="p-8 max-w-7xl mx-auto">
      {/* Header */}
      <header className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-12">
        <div>
          <div className="flex items-center gap-2 mb-2 text-blue-500">
            <Zap className="w-5 h-5 fill-current" />
            <span className="text-xs font-bold uppercase tracking-widest">Master Node</span>
          </div>
          <h1 className="text-5xl font-black tracking-tight">GridMind Central</h1>
          <p className="text-xs text-gray-500 font-mono mt-2">Master Node: 10.189.186.208</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="glass px-4 py-2 rounded-xl flex items-center gap-4">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              <span className="text-[10px] font-mono text-gray-400">SERVER ONLINE</span>
            </div>
            <div className="w-px h-4 bg-white/10" />
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-mono text-emerald-500 font-bold">{nodes.length}</span>
              <span className="text-[10px] font-mono text-gray-400">ACTIVE NODES</span>
            </div>
          </div>
          <div className="glass px-4 py-2 rounded-xl flex items-center gap-2 border-emerald-500/20">
            <Zap className="w-3 h-3 text-emerald-400" />
            <span className="text-[10px] font-mono text-white">AUTOPILOT: ACTIVE</span>
          </div>
        </div>
      </header>

      {/* --- Dashboard Summary Grid --- */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
        <div className="glass p-4 rounded-2xl border-white/5 bg-emerald-500/5">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[10px] font-bold text-emerald-400 uppercase tracking-widest">Global Health</span>
            <Zap className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-2xl font-black text-white">99.8%</div>
          <div className="text-[10px] text-gray-500 mt-1">AI CONFIDENCE INDEX</div>
        </div>

        <div className="glass p-4 rounded-2xl border-white/5">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">Active Teammates</span>
            <Monitor className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-2xl font-black text-white">{nodes.length}</div>
          <div className="text-[10px] text-gray-500 mt-1">CONNECTED AGENTS</div>
        </div>

        <div className="glass p-4 rounded-2xl border-white/5">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">Inference Rate</span>
            <Cpu className="w-4 h-4 text-blue-400" />
          </div>
          <div className="text-2xl font-black text-white">4.2ms</div>
          <div className="text-[10px] text-gray-500 mt-1">LATENCY / NODE</div>
        </div>

        <div className="glass p-4 rounded-2xl border-white/5 bg-blue-500/5">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[10px] font-bold text-blue-400 uppercase tracking-widest">Observer AI</span>
            <Shield className="w-4 h-4 text-blue-400" />
          </div>
          <div className="text-2xl font-black text-white">IDLE</div>
          <div className="text-[10px] text-gray-500 mt-1">CURRENT STRATEGY</div>
        </div>
      </div>

      {/* Stats Overview */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-12">
        <StatCard
          title="Active Nodes"
          value={nodes.length}
          icon={Monitor}
          color="text-blue-500"
        />
        <StatCard
          title="Idle Capacity"
          value={nodes.filter(n => n.telemetry.state === 'idle').length}
          icon={Cpu}
          color="text-green-500"
        />
        <StatCard
          title="Avg. Carbon Savings"
          value="24%"
          icon={Zap}
          color="text-yellow-500"
        />
        <StatCard
          title="Tasks Queued"
          value="0"
          icon={Database}
          color="text-purple-500"
        />
      </div>

      {/* Error State */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-4 flex items-center gap-3 mb-8">
          <AlertCircle className="text-red-500 h-5 w-5" />
          <p className="text-red-200 text-sm">Connection error: {error}. Check if FastAPI server is running.</p>
        </div>
      )}

      {/* Node Grid */}
      <section className="mb-12">
        <div className="flex items-center gap-2 mb-6 text-gray-400">
          <LayoutDashboard className="w-4 h-4" />
          <h2 className="text-sm font-bold uppercase tracking-widest">Worker Node Cluster</h2>
        </div>

        {nodes.length === 0 ? (
          <div className="glass p-12 text-center">
            <Monitor className="w-12 h-12 text-gray-600 mx-auto mb-4" />
            <p className="text-gray-400">No nodes connected yet.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {nodes.map(node => (
              <NodeCard key={node.node_id} node={node} />
            ))}
          </div>
        )}
      </section>

      {/* Data Trends Section */}
      <section>
        <div className="flex items-center gap-2 mb-6 text-gray-400">
          <Activity className="w-4 h-4" />
          <h2 className="text-sm font-bold uppercase tracking-widest">System Load Trends</h2>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="glass p-6">
            <h3 className="text-gray-400 text-xs font-bold uppercase mb-6 tracking-wider">Aggregate CPU Usage (%)</h3>
            <div className="h-[250px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={nodes.map(n => ({ name: n.node_id, val: n.telemetry.cpu_usage_pct }))}>
                  <defs>
                    <linearGradient id="colorCpu" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#ffffff10" vertical={false} />
                  <XAxis dataKey="name" stroke="#666" fontSize={10} hide />
                  <YAxis stroke="#666" fontSize={10} domain={[0, 100]} />
                  <Tooltip
                    contentStyle={{ backgroundColor: '#000', border: '1px solid #333', borderRadius: '8px' }}
                    itemStyle={{ color: '#3b82f6' }}
                  />
                  <Area type="monotone" dataKey="val" stroke="#3b82f6" fillOpacity={1} fill="url(#colorCpu)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="glass p-6">
            <h3 className="text-gray-400 text-xs font-bold uppercase mb-6 tracking-wider">Aggregate Memory Load (%)</h3>
            <div className="h-[250px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={nodes.map(n => ({ name: n.node_id, val: n.telemetry.ram_usage_pct }))}>
                  <defs>
                    <linearGradient id="colorMem" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#ffffff10" vertical={false} />
                  <XAxis dataKey="name" stroke="#666" fontSize={10} hide />
                  <YAxis stroke="#666" fontSize={10} domain={[0, 100]} />
                  <Tooltip
                    contentStyle={{ backgroundColor: '#000', border: '1px solid #333', borderRadius: '8px' }}
                    itemStyle={{ color: '#8b5cf6' }}
                  />
                  <Area type="monotone" dataKey="val" stroke="#8b5cf6" fillOpacity={1} fill="url(#colorMem)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}
