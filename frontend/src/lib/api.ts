// Central place for the backend base URL + WebSocket URL.
// Uses the page's own hostname so teammates hitting http://<master-ip>:3005
// automatically talk to the backend on the same host.

export const API =
  typeof window !== "undefined"
    ? `http://${window.location.hostname}:8000`
    : "http://localhost:8000";

export const WS_URL =
  typeof window !== "undefined"
    ? `ws://${window.location.hostname}:8000/ws/telemetry`
    : "ws://localhost:8000/ws/telemetry";

/** Map a 1–10 priority slider value to the backend's three tiers. */
export function priorityTier(prio: number): "best_effort" | "deferrable" | "urgent" {
  if (prio <= 3) return "best_effort";
  if (prio <= 6) return "deferrable";
  return "urgent";
}
