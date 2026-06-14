// Shared types for the GridMind dashboard.

export type NodeState = "idle" | "active_user" | "busy_hardware" | "unknown";

export interface NodeTelemetry {
  cpu_usage_pct: number;
  ram_usage_pct: number;
  state: NodeState;
  last_seen: string;
  battery_percent?: number;
  on_battery?: boolean;
  cpu_temp_c?: number;
}

export interface Node {
  node_id: string;
  telemetry: NodeTelemetry;
}

export interface CarbonPoint {
  t: string; // "HH:MM:SS"
  gco2: number; // real g CO₂/kWh
}

export interface DispatchEvent {
  id: number;
  time: string;
  strategy: string;
  gco2: number; // real g CO₂/kWh
  queue: number;
}

export interface Task {
  id: number;
  task_id: string;
  name: string;
  script: string;
  priority_str: "urgent" | "deferrable" | "best_effort";
  status: string;
  assigned_node: string | null;
  submitted_at: string | null;
  dispatched_at: string | null;
  has_artifact?: boolean;
  output_artifact_path?: string | null;
}

/** The guardrail (if any) that overrode the learned DQN policy. */
export type Override = "urgent" | "clean-grid" | null;

export interface JobChunk {
  chunk_index: number;
  status: string;
  assigned_node: string | null;
  duration_secs: number | null;
}

export interface JobDetail {
  job_id: string;
  name: string;
  chunk_count: number;
  completed: number;
  total: number;
  all_done: boolean;
  serial_secs: number | null;
  wall_secs: number | null;
  speedup: number | null;
  nodes_used: string[];
  chunks: JobChunk[];
}

export interface JobSummary {
  job_id: string;
  name: string;
  chunk_count: number;
  completed: number;
  failed: number;
  total: number;
  submitted_at: string | null;
}
