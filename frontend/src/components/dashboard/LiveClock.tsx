"use client";

import { useEffect, useState } from "react";

// Live wall-clock with a breathing "synced" dot — signals the dashboard is live.
// Isolated so its 1s tick doesn't re-render the whole page.
export function LiveClock() {
  const [time, setTime] = useState<string>("");

  useEffect(() => {
    const tick = () => setTime(new Date().toLocaleTimeString("en-GB"));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <span className="chip font-mono text-muted" suppressHydrationWarning>
      <span className="w-2 h-2 rounded-full bg-accent-2 live-dot" />
      {time || "--:--:--"}
    </span>
  );
}
