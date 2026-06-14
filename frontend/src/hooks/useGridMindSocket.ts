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

/** Shape of the messages pushed over /ws/telemetry. All fields optional because
 *  the frontend must tolerate partial/malformed frames without crashing. */
interface WSMessage {
  type?: string;
  nodes?: (NodeTelemetry & { node_id: string })[];
  node?: NodeTelemetry & { node_id: string };
  node_id?: string;
  strategy?: string;
  queue_size?: number;
  carbon_savings?: string;
  carbon_intensity?: number;
  carbon_gco2?: number | null;
  reason?: string;
  override?: Override;
  carbon_baseline_g?: number;
  carbon_gridmind_g?: number;
  carbon_saved_g?: number;
  carbon_tasks_counted?: number;
  carbon_forecast?: number[];
  clean_window_min?: number | null;
  task_id?: string;
  stdout?: string;
  stderr?: string;
}

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
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectDelayRef = useRef(1000); // exponential backoff, capped
  const unmountedRef = useRef(false);
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
      // NOTE: do NOT clear `error` here. While in REST-fallback mode the dispatcher,
      // carbon and task streams are frozen, so the degraded banner must persist until
      // the WebSocket actually reconnects (cleared in socket.onopen).
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  const startPolling = () => {
    if (!pollingRef.current) pollingRef.current = setInterval(fetchNodes, 3000);
  };
  const stopPolling = () => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
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
    unmountedRef.current = false;

    const scheduleReconnect = () => {
      if (unmountedRef.current || reconnectTimerRef.current) return;
      // Degraded mode: poll node telemetry over REST until the WS is back. The
      // dispatcher/carbon/task streams stay frozen, so keep the banner up.
      setError("Live connection lost — reconnecting… (node telemetry via REST; dispatcher/carbon paused)");
      startPolling();
      const delay = reconnectDelayRef.current;
      reconnectTimerRef.current = setTimeout(() => {
        reconnectTimerRef.current = null;
        reconnectDelayRef.current = Math.min(delay * 2, 15000); // backoff, cap 15s
        connect();
      }, delay);
    };

    const handleMessage = (ev: MessageEvent) => {
      let data: WSMessage;
      try {
        data = JSON.parse(ev.data);
      } catch {
        // Ignore malformed/non-JSON frames instead of throwing inside the handler.
        return;
      }
      if (!data || typeof data !== "object") return;

      if (data.type === "initial_state") {
        const arr = (data.nodes ?? [])
          .filter((n) => n && n.node_id)
          .map((n) => ({ node_id: n.node_id, telemetry: n }));
        setNodes(arr);
        setLoading(false);
      } else if (data.type === "node_update") {
        if (!data.node || !data.node.node_id) return; // ignore malformed frame
        setLoading(false);
        nodeBufferRef.current.set(data.node.node_id, data.node);
        needsNodeFlushRef.current = true;
      } else if (data.type === "node_remove") {
        if (!data.node_id) return;
        // Also drop from the throttle buffer, else the next 250ms flush would
        // resurrect the just-removed node as a ghost.
        nodeBufferRef.current.delete(data.node_id);
        setNodes((prev) => prev.filter((n) => n.node_id !== data.node_id));
      } else if (data.type === "dispatcher_update") {
        setLoading(false);
        const ci = data.carbon_intensity ?? 0.5;
        const gco2 = data.carbon_gco2 ?? null;
        const strategy = data.strategy ?? strategyRef.current;
        const queue = data.queue_size ?? 0;
        setStrategy(strategy);
        setTasksQueued(queue);
        setCarbonSavings(data.carbon_savings ?? "—");
        if (data.reason !== undefined) setReason(data.reason);
        setOverride(data.override ?? null);
        if (data.carbon_baseline_g !== undefined) {
          setCarbonBaselineG(data.carbon_baseline_g);
          setCarbonGridmindG(data.carbon_gridmind_g ?? 0);
          setCarbonSavedG(data.carbon_saved_g ?? 0);
          setCarbonTasksCounted(data.carbon_tasks_counted ?? 0);
        }
        if (Array.isArray(data.carbon_forecast)) setForecast(data.carbon_forecast);
        if (data.clean_window_min !== undefined) setForecastCleanInMin(data.clean_window_min);
        setCarbonIntensity(ci);
        if (gco2 !== null) {
          setCarbonGco2(gco2);
          pushCarbonPoint(gco2);
        }
        // Only log a real measured carbon number; never fabricate one from ci.
        pushDispatchEvent(strategy, gco2 ?? NaN, queue);
      } else if (data.type === "task_output") {
        if (!data.task_id) return;
        const tid = data.task_id;
        if (!taskOutputBufferRef.current[tid]) {
          taskOutputBufferRef.current[tid] = [];
        }
        if (data.stdout) taskOutputBufferRef.current[tid].push(data.stdout.trimEnd());
        if (data.stderr) taskOutputBufferRef.current[tid].push(`[ERR] ${data.stderr.trimEnd()}`);
        needsTaskFlushRef.current = true;
      }
    };

    function connect() {
      if (unmountedRef.current) return;
      let socket: WebSocket;
      try {
        socket = new WebSocket(WS_URL);
      } catch {
        scheduleReconnect();
        return;
      }
      socketRef.current = socket;

      socket.onopen = () => {
        // Connected: clear the degraded banner, reset backoff, and stop the REST
        // fallback poll (the server pushes initial_state + live streams now).
        setError(null);
        reconnectDelayRef.current = 1000;
        stopPolling();
      };
      socket.onmessage = handleMessage;
      // Both onerror and onclose can fire; scheduleReconnect is idempotent.
      socket.onerror = () => {
        setLoading(false);
      };
      socket.onclose = () => {
        socketRef.current = null;
        scheduleReconnect();
      };
    }

    connect();

    return () => {
      unmountedRef.current = true;
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      stopPolling();
      const s = socketRef.current;
      if (s) {
        s.onclose = null; // prevent reconnect-on-unmount
        s.close();
        socketRef.current = null;
      }
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
