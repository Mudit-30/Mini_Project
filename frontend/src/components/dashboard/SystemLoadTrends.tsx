"use client";

import React from "react";
import { Activity } from "lucide-react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Node } from "@/lib/types";

const SERIES = [
  { key: "cpu_usage_pct", label: "Aggregate CPU Usage (%)", id: "colorCpu", stroke: "#b6ff2e" },
  { key: "ram_usage_pct", label: "Aggregate Memory Load (%)", id: "colorMem", stroke: "#34d399" },
] as const;

export const SystemLoadTrends = React.memo(function SystemLoadTrends({ nodes }: { nodes: Node[] }) {
  return (
    <section>
      <div className="flex items-center gap-2 mb-5">
        <Activity className="w-4 h-4 text-accent" />
        <h2 className="section-label">System Load Trends</h2>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {SERIES.map(({ key, label, id, stroke }) => (
          <div className="card card-hover p-6" key={key}>
            <h3 className="section-label mb-5">{label}</h3>
            <div className="h-[240px]">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart
                  data={nodes.map((n) => ({ name: n.node_id, val: n.telemetry[key] }))}
                  margin={{ left: -20 }}
                >
                  <defs>
                    <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={stroke} stopOpacity={0.3} />
                      <stop offset="95%" stopColor={stroke} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#ffffff0d" vertical={false} />
                  <XAxis dataKey="name" stroke="#5b6475" fontSize={9} />
                  <YAxis stroke="#5b6475" fontSize={9} domain={[0, 100]} />
                  <Tooltip
                    contentStyle={{ backgroundColor: "#0e1016", border: "1px solid var(--border)", borderRadius: "8px" }}
                    itemStyle={{ color: stroke }}
                  />
                  <Area type="monotone" dataKey="val" stroke={stroke} strokeWidth={2} fillOpacity={1} fill={`url(#${id})`} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
});
