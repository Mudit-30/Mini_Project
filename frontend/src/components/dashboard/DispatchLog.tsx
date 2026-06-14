"use client";

import React from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ListChecks } from "lucide-react";
import type { DispatchEvent } from "@/lib/types";

export const DispatchLog = React.memo(function DispatchLog({ events }: { events: DispatchEvent[] }) {
  return (
    <div className="card card-hover p-6 flex flex-col">
      <div className="flex items-center gap-2 mb-5">
        <ListChecks className="w-4 h-4 text-accent" />
        <h2 className="section-label">Dispatcher Action Log</h2>
      </div>
      {events.length === 0 ? (
        <div className="flex-1 flex items-center justify-center text-faint text-sm">
          Awaiting first dispatch event…
        </div>
      ) : (
        // `events` is newest-first; render in order so the newest sits on top
        // (the previous AnimatedList reversed it and revealed one item per second).
        <div className="overflow-y-auto max-h-[420px] pr-2 scrollbar-thin flex flex-col gap-2">
          <AnimatePresence initial={false}>
            {events.map((ev) => {
              const isD = ev.strategy.includes("DISPATCH");
              const isDef = ev.strategy.includes("DEFER");
              const dot = isD ? "bg-accent" : isDef ? "bg-carbon-mixed" : "bg-faint";
              return (
                <motion.div
                  key={ev.id}
                  layout
                  initial={{ opacity: 0, y: -8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  transition={{ type: "spring", stiffness: 350, damping: 30 }}
                  className="flex items-start gap-3 p-3 rounded-lg bg-white/[0.03] border border-white/10 hover:bg-white/[0.06] transition-colors w-full"
                >
                  <div className={`w-2 h-2 rounded-full mt-1.5 shrink-0 ${dot}`} />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-bold text-foreground truncate">{ev.strategy}</p>
                    <p className="text-xs text-muted font-mono mt-1 font-medium">
                      {ev.time} · {Math.round(ev.gco2)} g/kWh · Q={ev.queue}
                    </p>
                  </div>
                </motion.div>
              );
            })}
          </AnimatePresence>
        </div>
      )}
    </div>
  );
});
