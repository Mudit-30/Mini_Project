"use client";

import { useEffect, useRef, useState } from "react";
import { API, WS_URL } from "@/lib/api";
import type {
  CarbonPoint,
  DispatchEvent,
  Node,
  NodeTelemetry,
  Override,
} from "@/lib/types";

const MAX_HISTORY = 40;

/**
 * Owns all live dashboard state: opens the telemetry WebSocket (falling back to
 * REST polling), throttles the high-frequency node/task streams to a 250 ms
 * flush, and exposes everything the dashboard renders.
 */
export function useGridMindSocket() {
  const [nodes, setNodes] = useState<Node[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [strategy, setStrategy] = useState("IDLE — Awaiting Data");
  const [tasksQueued, setTasksQueued] = useState(0);
  const [carbonSavings, setCarbonSavings] = useState("—");
  const [carbonIntensity, setCarbonIntensity] = useState(0.5); // normalised 0-1 for gauge
  const [carbonGco2, setCarbonGco2] = useState<number | null>(null); // real g/kWh
  const [carbonHistory, setCarbonHistory] = useState<CarbonPoint[]>([]);
  // Real carbon-savings ledger (baseline vs GridMind, measured per completed task).
  const [carbonBaselineG, setCarbonBaselineG] = useState(0);
  const [carbonGridmindG, setCarbonGridmindG] = useState(0);
  const [carbonSavedG, setCarbonSavedG] = useState(0);
  const [carbonTasksCounted, setCarbonTasksCounted] = useState(0);
  const [dispatchLog, setDispatchLog] = useState<DispatchEvent[]>([]);
  const [reason, setReason] = useState(""); // explainable-AI text
  const [override, setOverride] = useState<Override>(null); // guardrail over the DQN
  const [taskOutput, setTaskOutput] = useState<Record<string, string[]>>({});
  // 2-hour ARIMA carbon forecast (g/kWh) + minutes until the next clean window.
  const [forecast, setForecast] = useState<number[] | null>(null);
  const [forecastCleanInMin, setForecastCleanInMin] = useState<number | null>(null);

  const eventId = useRef(0);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const strategyRef = useRef(strategy);
  strategyRef.current = strategy;

  // Throttling buffers
  const nodeBufferRef = useRef<Map<string, NodeTelemetry>>(new Map());
  const needsNodeFlushRef = useRef(false);
  const taskOutputBufferRef = useRef<Record<string, string[]>>({});
  const needsTaskFlushRef = useRef(false);

  // Periodic flush for throttled data (every 250 ms) — prevents render thrash.
  useEffect(() => {
    const flushInterval = setInterval(() => {
      if (needsNodeFlushRef.current) {
        setNodes((prev) => {
          let changed = false;
          const next = [...prev];
          nodeBufferRef.current.forEach((telemetry, node_id) => {
            const idx = next.findIndex((n) => n.node_id === node_id);
            if (idx !== -1) next[idx] = { node_id, telemetry };
            else next.push({ node_id, telemetry });
            changed = true;
          });
          nodeBufferRef.current.clear();
          needsNodeFlushRef.current = false;
          return changed ? next : prev;
        });
      }

      if (needsTaskFlushRef.current) {
        setTaskOutput((prev) => {
          const next = { ...prev };
          let changed = false;
          for (const [task_id, newLines] of Object.entries(taskOutputBufferRef.current)) {
            if (newLines.length > 0) {
              const existing = next[task_id] || [];
              next[task_id] = [...existing, ...newLines].slice(-200);
              changed = true;
            }
          }
          taskOutputBufferRef.current = {};
          needsTaskFlushRef.current = false;
          return changed ? next : prev;
        });
      }
    }, 250);
    return () => clearInterval(flushInterval);
  }, []);

  const fetchNodes = async () => {
    try {
      const res = await fetch(`${API}/api/v1/nodes`);
      if (!res.ok) throw new Error("Failed to fetch nodes");
      const data = await res.json();
      const arr = (data.nodes || []).map((n: NodeTelemetry & { node_id: string }) => ({
        node_id: n.node_id,
        telemetry: n,
      }));
      setNodes(arr);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  const pushCarbonPoint = (gco2: number) => {
    const now = new Date().toLocaleTimeString("en-GB");
    setCarbonHistory((prev) => {
      const next = [...prev, { t: now, gco2 }];
      return next.length > MAX_HISTORY ? next.slice(-MAX_HISTORY) : next;
    });
  };

  const pushDispatchEvent = (strat: string, gco2: number, queue: number) => {
    if (strat === strategyRef.current) return; // skip duplicates
    const now = new Date().toLocaleTimeString("en-GB");
    setDispatchLog((prev) => {
      const entry: DispatchEvent = { id: ++eventId.current, time: now, strategy: strat, gco2, queue };
      return [entry, ...prev].slice(0, 20);
    });
  };

  useEffect(() => {
    const socket = new WebSocket(WS_URL);

    socket.onopen = () => {
      // The server pushes an "initial_state" message on connect, so we don't need
      // a redundant REST fetch here — it would just be overwritten immediately.
      setError(null);
    };
    socket.onerror = () => {
      setError("WebSocket failed — polling node telemetry via REST (dispatcher/carbon streams paused)…");
      setLoading(false);
      // Guard against stacking intervals if onerror + onclose both fire.
      if (!pollingRef.current) pollingRef.current = setInterval(fetchNodes, 3000);
    };
    socket.onclose = () => console.log("WS closed");

    socket.onmessage = (ev) => {
      const data = JSON.parse(ev.data);

      if (data.type === "initial_state") {
        const arr = (data.nodes ?? []).map((n: NodeTelemetry & { node_id: string }) => ({
          node_id: n.node_id,
          telemetry: n,
        }));
        setNodes(arr);
        setLoading(false);
      } else if (data.type === "node_update") {
        setLoading(false);
        nodeBufferRef.current.set(data.node.node_id, data.node);
        needsNodeFlushRef.current = true;
      } else if (data.type === "node_remove") {
        // Also drop from the throttle buffer, else the next 250ms flush would
        // resurrect the just-removed node as a ghost.
        nodeBufferRef.current.delete(data.node_id);
        setNodes((prev) => prev.filter((n) => n.node_id !== data.node_id));
      } else if (data.type === "dispatcher_update") {
        setLoading(false);
        const ci = data.carbon_intensity ?? 0.5;
        const gco2 = data.carbon_gco2 ?? null;
        setStrategy(data.strategy);
        setTasksQueued(data.queue_size);
        setCarbonSavings(data.carbon_savings);
        if (data.reason !== undefined) setReason(data.reason);
        setOverride(data.override ?? null);
        if (data.carbon_baseline_g !== undefined) {
          setCarbonBaselineG(data.carbon_baseline_g);
          setCarbonGridmindG(data.carbon_gridmind_g);
          setCarbonSavedG(data.carbon_saved_g);
          setCarbonTasksCounted(data.carbon_tasks_counted);
        }
        if (Array.isArray(data.carbon_forecast)) setForecast(data.carbon_forecast);
        if (data.clean_window_min !== undefined) setForecastCleanInMin(data.clean_window_min);
        setCarbonIntensity(ci);
        if (gco2 !== null) {
          setCarbonGco2(gco2);
          pushCarbonPoint(gco2);
        }
        pushDispatchEvent(data.strategy, gco2 ?? ci * 500, data.queue_size);
      } else if (data.type === "task_output") {
        if (!taskOutputBufferRef.current[data.task_id]) {
          taskOutputBufferRef.current[data.task_id] = [];
        }
        if (data.stdout) taskOutputBufferRef.current[data.task_id].push(data.stdout.trimEnd());
        if (data.stderr) taskOutputBufferRef.current[data.task_id].push(`[ERR] ${data.stderr.trimEnd()}`);
        needsTaskFlushRef.current = true;
      }
    };

    return () => {
      socket.close();
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return {
    nodes,
    loading,
    error,
    strategy,
    tasksQueued,
    carbonSavings,
    carbonIntensity,
    carbonGco2,
    carbonHistory,
    carbonBaselineG,
    carbonGridmindG,
    carbonSavedG,
    carbonTasksCounted,
    dispatchLog,
    reason,
    override,
    taskOutput,
    forecast,
    forecastCleanInMin,
  };
}
