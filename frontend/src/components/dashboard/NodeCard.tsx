"use client";

import React from "react";
import { motion } from "framer-motion";
import { Battery, BatteryCharging, Clock, Monitor, Thermometer } from "lucide-react";
import type { Node, NodeState } from "@/lib/types";

const STATE_DOT: Record<NodeState, string> = {
  idle: "bg-accent-2",
  active_user: "bg-carbon-mixed",
  busy_hardware: "bg-carbon-dirty",
  unknown: "bg-faint",
};

// A user is present (active) — highlight the card so the "veto" moment pops on stage.
const STATE_RING: Record<NodeState, string> = {
  idle: "",
  active_user: "ring-1 ring-carbon-mixed/40",
  busy_hardware: "ring-1 ring-carbon-dirty/30",
  unknown: "",
};

export const NodeCard = React.memo(function NodeCard({ node }: { node: Node }) {
  const { state, battery_percent, on_battery, cpu_temp_c } = node.telemetry;
  const hasBattery = battery_percent !== undefined;
  const hasTemp = cpu_temp_c !== undefined && cpu_temp_c > 0;
  const lowBattery = hasBattery && (battery_percent as number) < 20;
  const hot = hasTemp && (cpu_temp_c as number) > 85;
  // "Protected" = the dispatcher will NOT send work here (battery/thermal guard).
  const protectedNode = !!on_battery || lowBattery || hot;
  const ring = protectedNode ? "ring-1 ring-carbon-mixed/50" : STATE_RING[state];
  return (
    <motion.div
      layout
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95 }}
      whileHover={{ y: -5 }}
      className={`card card-hover p-6 ${ring}`}
    >
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-4">
          <div className="p-2.5 bg-accent/10 rounded-xl">
            <Monitor className="text-accent h-6 w-6" />
          </div>
          <div>
            <h3 className="font-bold text-base text-foreground">{node.node_id}</h3>
            <p className="text-xs text-muted">Live Telemetry</p>
          </div>
        </div>
        <div className="flex items-center gap-2.5">
          <span className={`w-2.5 h-2.5 rounded-full ${STATE_DOT[state]} animate-pulse`} />
          <span className="text-xs uppercase font-mono tracking-wider text-muted">{state}</span>
        </div>
      </div>
      <div className="space-y-4">
        {[
          { label: "CPU", value: node.telemetry.cpu_usage_pct, color: "bg-accent" },
          { label: "RAM", value: node.telemetry.ram_usage_pct, color: "bg-accent-2" },
        ].map(({ label, value, color }) => (
          <div key={label}>
            <div className="flex justify-between text-xs mb-1.5">
              <span className="text-muted">{label} Usage</span>
              <span className="font-mono text-foreground">{value.toFixed(1)}%</span>
            </div>
            <div className="w-full bg-white/10 h-2 rounded-full overflow-hidden">
              <div
                className={`${color} h-full rounded-full transition-all duration-500`}
                style={{ width: `${value}%` }}
              />
            </div>
          </div>
        ))}
      </div>
      {/* Power / thermal state — the dispatcher protects laptops that are on
          battery, low, or hot (shown by the ⛔ Protected pill). */}
      {(hasBattery || hasTemp) && (
        <div className="mt-4 flex items-center gap-2 flex-wrap text-xs font-mono">
          {hasBattery && (
            <span
              className={`chip flex items-center gap-1 ${
                on_battery ? "text-carbon-mixed" : "text-accent-2"
              }`}
            >
              {on_battery ? <Battery className="w-3.5 h-3.5" /> : <BatteryCharging className="w-3.5 h-3.5" />}
              {Math.round(battery_percent as number)}% {on_battery ? "battery" : "plugged"}
            </span>
          )}
          {hasTemp && (
            <span
              className={`chip flex items-center gap-1 ${
                hot ? "text-carbon-dirty" : "text-muted"
              }`}
            >
              <Thermometer className="w-3.5 h-3.5" />
              {Math.round(cpu_temp_c as number)}°C
            </span>
          )}
          {protectedNode && (
            <span className="chip ml-auto text-[10px] font-bold uppercase tracking-wider text-carbon-mixed">
              ⛔ Protected
            </span>
          )}
        </div>
      )}
      <div className="mt-5 pt-4 border-t border-white/10 flex items-center justify-between text-xs text-muted font-mono">
        <div className="flex items-center gap-1.5">
          <Clock className="w-3.5 h-3.5" />
          <span>Last Seen</span>
        </div>
        <span>{new Date(node.telemetry.last_seen).toLocaleTimeString()}</span>
      </div>
    </motion.div>
  );
});
