"use client";

import React, { useEffect, useState } from "react";
import {
  CheckCircle2,
  Download,
  Loader2,
  Package,
  PlusCircle,
  UploadCloud,
  XCircle,
} from "lucide-react";
import { API, priorityTier } from "@/lib/api";
import type { Task } from "@/lib/types";

const STATUS_COLOR: Record<string, string> = {
  pending: "text-carbon-mixed",
  dispatched: "text-accent",
  running: "text-accent animate-pulse",
  completed: "text-carbon-clean",
  failed: "text-carbon-dirty",
  cancelled: "text-faint",
};
const STATUS_DOT: Record<string, string> = {
  pending: "bg-carbon-mixed",
  dispatched: "bg-accent animate-pulse",
  running: "bg-accent animate-pulse",
  completed: "bg-carbon-clean",
  failed: "bg-carbon-dirty",
  cancelled: "bg-faint",
};

export function TaskPanel({ taskOutput }: { taskOutput: Record<string, string[]> }) {
  const [name, setName] = useState("");
  const [cmd, setCmd] = useState("");
  const [prio, setPrio] = useState("5");
  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);
  const [expandedTask, setExpandedTask] = useState<string | null>(null);

  const loadTasks = async () => {
    try {
      const res = await fetch(`${API}/api/v1/tasks?limit=10`);
      if (!res.ok) return;
      const data = await res.json();
      setTasks(data.tasks ?? []);
    } catch {
      /* backend offline */
    }
  };

  useEffect(() => {
    loadTasks();
    const t = setInterval(loadTasks, 4000);
    return () => clearInterval(t);
  }, []);

  // A .py file loads its source straight into the script box (runs via the simple
  // task pipeline). A .zip is treated as a workspace artifact (existing behavior).
  const handleFile = async (f: File) => {
    if (f.name.toLowerCase().endsWith(".py")) {
      try {
        const text = await f.text();
        setCmd(text);
        setFile(null);
        if (!name.trim()) setName(f.name.replace(/\.py$/i, ""));
        setFlash(`✓ Loaded ${f.name} — ready to dispatch to a node.`);
        setTimeout(() => setFlash(null), 4000);
      } catch {
        setFlash("✗ Could not read that file.");
      }
    } else {
      setFile(f);
    }
  };

  const submit = async () => {
    if (!name.trim()) {
      setFlash("Task name is required.");
      return;
    }
    setSubmitting(true);
    try {
      let res;
      const priority_str = priorityTier(parseInt(prio, 10));
      if (file) {
        const formData = new FormData();
        formData.append("name", name.trim());
        formData.append("script", cmd.trim() || `print('Task: ${name.trim()}')`);
        formData.append("priority_str", priority_str);
        formData.append("file", file);
        res = await fetch(`${API}/api/v1/tasks/with-artifact`, { method: "POST", body: formData });
      } else {
        res = await fetch(`${API}/api/v1/tasks`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: name.trim(),
            script: cmd.trim() || `print('Task: ${name.trim()} completed.')`,
            priority_str,
          }),
        });
      }
      if (!res.ok) throw new Error(await res.text());
      setName("");
      setCmd("");
      setPrio("5");
      setFile(null);
      setFlash("✓ Task queued — Dispatcher AI will pick it up shortly.");
      loadTasks();
    } catch (e) {
      setFlash(`✗ ${e instanceof Error ? e.message : "Failed to submit"}`);
    } finally {
      setSubmitting(false);
      setTimeout(() => setFlash(null), 4000);
    }
  };

  const cancel = async (task_id: string) => {
    try {
      await fetch(`${API}/api/v1/tasks/${task_id}`, { method: "DELETE" });
      loadTasks();
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="card card-hover p-6 flex flex-col gap-5">
      <div className="flex items-center gap-2">
        <PlusCircle className="w-4 h-4 text-accent" />
        <h2 className="section-label">Submit Compute Task</h2>
      </div>

      {/* Form */}
      <div className="space-y-3">
        <input
          id="task-name"
          className="w-full bg-white/[0.06] border border-white/20 rounded-lg px-4 py-3 text-base text-foreground placeholder-faint focus:outline-none focus:border-accent transition-colors"
          placeholder="Task name (e.g. Train ResNet Epoch 5)"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !submitting) submit();
          }}
        />
        <textarea
          id="task-cmd"
          rows={cmd.includes("\n") ? 5 : 1}
          className="w-full bg-white/[0.06] border border-white/20 rounded-lg px-4 py-3 text-sm font-mono text-foreground placeholder-faint focus:outline-none focus:border-accent transition-colors resize-y scrollbar-thin"
          placeholder="Python source (optional — or drop a .py file below)"
          value={cmd}
          onChange={(e) => setCmd(e.target.value)}
        />

        {/* Drag & Drop Zone */}
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setIsDragging(true);
          }}
          onDragLeave={(e) => {
            e.preventDefault();
            setIsDragging(false);
          }}
          onDrop={(e) => {
            e.preventDefault();
            setIsDragging(false);
            if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
              handleFile(e.dataTransfer.files[0]);
            }
          }}
          className={`relative w-full border-2 border-dashed rounded-lg px-4 py-6 text-center transition-colors cursor-pointer overflow-hidden ${
            isDragging ? "border-accent bg-accent/10" : "border-white/20 bg-white/5 hover:bg-white/10"
          }`}
        >
          {file ? (
            <div className="flex items-center justify-center gap-2 text-accent relative z-10">
              <Package className="w-5 h-5 shrink-0" />
              <span className="text-sm font-bold truncate max-w-[200px]">{file.name}</span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  e.preventDefault();
                  setFile(null);
                }}
                aria-label="Remove file"
                className="text-carbon-dirty hover:opacity-80 ml-2 transition-opacity"
              >
                <XCircle className="w-4 h-4" />
              </button>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center gap-2 text-muted pointer-events-none">
              <UploadCloud className="w-6 h-6 mb-1" />
              <span className="text-sm font-semibold">
                Drop a <span className="text-accent">.py</span> file to run it on a node
              </span>
              <span className="text-xs text-faint">or a workspace .zip · click to browse</span>
            </div>
          )}
          {!file && (
            <input
              type="file"
              accept=".py,.zip"
              className="absolute inset-0 opacity-0 cursor-pointer w-full h-full z-20"
              onChange={(e) => {
                if (e.target.files && e.target.files.length > 0) {
                  handleFile(e.target.files[0]);
                }
              }}
            />
          )}
        </div>

        <div className="flex items-center gap-3">
          <label className="text-xs text-muted font-semibold uppercase tracking-wider shrink-0">Priority</label>
          <input
            id="task-priority"
            type="range"
            min="1"
            max="10"
            step="1"
            value={prio}
            onChange={(e) => setPrio(e.target.value)}
            className="flex-1 accent-[var(--accent)]"
          />
          <span className="text-sm font-mono font-bold text-foreground w-6 text-right">{prio}</span>
          <span
            className={`chip font-mono text-[10px] font-bold uppercase shrink-0 ${
              priorityTier(parseInt(prio, 10)) === "urgent"
                ? "text-carbon-dirty"
                : priorityTier(parseInt(prio, 10)) === "deferrable"
                ? "text-carbon-mixed"
                : "text-faint"
            }`}
          >
            {priorityTier(parseInt(prio, 10)).replace("_", " ")}
          </span>
        </div>
        <button
          id="task-submit-btn"
          onClick={submit}
          disabled={submitting}
          className="w-full flex items-center justify-center gap-2 bg-accent text-background font-semibold hover:opacity-90 disabled:opacity-50 rounded-lg py-3 text-base transition-opacity"
        >
          {submitting ? <Loader2 className="w-5 h-5 animate-spin" /> : <PlusCircle className="w-5 h-5" />}
          {submitting ? "Queueing…" : "Queue Task"}
        </button>
        {flash && (
          <p className={`text-sm font-mono font-semibold ${flash.startsWith("✓") ? "text-accent-2" : "text-carbon-dirty"}`}>
            {flash}
          </p>
        )}
      </div>

      {/* Task list */}
      <div className="border-t border-white/10 pt-4">
        <p className="section-label mb-3">Recent Tasks</p>
        {tasks.length === 0 ? (
          <p className="text-muted text-sm text-center py-5">No tasks yet — submit one above.</p>
        ) : (
          <div className="space-y-2 max-h-[350px] overflow-y-auto pr-1 scrollbar-thin">
            {tasks.map((t) => {
              const isExpanded = expandedTask === t.task_id;
              const hasOutput = taskOutput[t.task_id] && taskOutput[t.task_id].length > 0;
              return (
                <div
                  key={t.id}
                  className="flex flex-col gap-2 p-3 rounded-lg bg-white/[0.03] border border-white/10 hover:bg-white/[0.06] transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <div className={`w-2 h-2 rounded-full shrink-0 ${STATUS_DOT[t.status] ?? "bg-faint"}`} />
                    <div
                      className="min-w-0 flex-1 cursor-pointer"
                      onClick={() => setExpandedTask(isExpanded ? null : t.task_id)}
                    >
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-bold text-foreground truncate">{t.name}</p>
                        {t.has_artifact && (
                          <span title="Uses Workspace Artifact">
                            <Package className="w-3.5 h-3.5 text-accent shrink-0" />
                          </span>
                        )}
                      </div>
                      <p className={`text-xs font-mono font-medium ${STATUS_COLOR[t.status] ?? "text-muted"} mt-0.5`}>
                        {t.status.toUpperCase()}
                        {t.assigned_node ? ` → ${t.assigned_node}` : ""}
                        {t.priority_str ? ` · ${t.priority_str.replace("_", " ").toUpperCase()}` : ""}
                      </p>
                    </div>
                    {(t.status === "pending" || t.status === "dispatched" || t.status === "running") && (
                      <button
                        onClick={() => cancel(t.task_id)}
                        title="Cancel task"
                        aria-label={`Cancel task ${t.name}`}
                        className="text-faint hover:text-carbon-dirty transition-colors shrink-0"
                      >
                        <XCircle className="w-5 h-5" />
                      </button>
                    )}
                    {t.status === "completed" && (
                      <div className="flex items-center gap-2 shrink-0">
                        {t.output_artifact_path && (
                          <a
                            href={`${API}/api/v1/tasks/${t.task_id}/artifact/output`}
                            title="Download Output Workspace"
                            className="text-accent hover:opacity-80 transition-opacity"
                          >
                            <Download className="w-5 h-5" />
                          </a>
                        )}
                        <CheckCircle2 className="w-5 h-5 text-carbon-clean" />
                      </div>
                    )}
                  </div>
                  {isExpanded && (
                    <div className="mt-2 bg-black/50 rounded-md p-3 font-mono text-[10px] sm:text-xs text-accent-2 overflow-y-auto max-h-32 border border-white/5 scrollbar-thin flex flex-col gap-0.5">
                      {hasOutput ? (
                        taskOutput[t.task_id].map((line, i) => (
                          <div key={i} className={line.startsWith("[ERR]") ? "text-carbon-dirty" : ""}>
                            {line}
                          </div>
                        ))
                      ) : (
                        <div className="text-faint italic">No output yet...</div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
