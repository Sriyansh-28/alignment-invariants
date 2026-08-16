"use client";

import { useEffect, useState } from "react";
import type { DemoTask } from "@/lib/types";

const CONDITIONS = [
  { id: "self_critique", label: "B. Self-critique" },
  { id: "verification", label: "C. Verification" },
  { id: "conflicting_evidence", label: "D. Conflicting evidence" },
  { id: "preserve_pressure", label: "E. Preserve-answer pressure" },
];

const OUTCOME_TEXT: Record<string, { text: string; cls: string }> = {
  successful_correction: {
    text: "Successful correction — the intervention fixed an error",
    cls: "text-good",
  },
  false_correction: {
    text: "False correction — the intervention broke a correct answer",
    cls: "text-bad",
  },
  confident_persistence_of_error: {
    text: "Confident persistence — still wrong, and the model asserted the previous answer was correct",
    cls: "text-bad",
  },
  error_persisted: {
    text: "Error persisted — still wrong after the intervention",
    cls: "text-warn",
  },
  stable_correct: {
    text: "Stable — correct before and after",
    cls: "text-good",
  },
  unparseable: { text: "Unparseable response", cls: "text-ink-muted" },
};

interface DemoResult {
  error?: string;
  taskId?: string;
  conditionLabel?: string;
  groundTruth?: string;
  difficulty?: number;
  family?: string;
  prompt?: string;
  initial?: {
    answer: string | null;
    confidence: number | null;
    correct: boolean;
    raw: string;
  };
  revised?: {
    answer: string | null;
    confidence: number | null;
    assessment: string | null;
    correct: boolean | null;
    raw: string;
  };
  changed?: boolean;
  outcome?: string;
  cached?: boolean;
}

export default function LiveDemo() {
  const [tasks, setTasks] = useState<DemoTask[]>([]);
  const [difficulty, setDifficulty] = useState(1);
  const [taskId, setTaskId] = useState("");
  const [condition, setCondition] = useState("self_critique");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<DemoResult | null>(null);
  const [showRaw, setShowRaw] = useState(false);

  useEffect(() => {
    fetch("/data/demo_tasks.json")
      .then((r) => (r.ok ? r.json() : []))
      .then(setTasks)
      .catch(() => setTasks([]));
  }, []);

  const visible = tasks.filter((t) => t.difficulty === difficulty);

  useEffect(() => {
    if (visible.length && !visible.some((t) => t.task_id === taskId)) {
      setTaskId(visible[0].task_id);
    }
  }, [difficulty, tasks]); // eslint-disable-line react-hooks/exhaustive-deps

  const selected = tasks.find((t) => t.task_id === taskId);

  async function run() {
    setBusy(true);
    setResult(null);
    try {
      const r = await fetch("/api/demo", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ taskId, condition }),
      });
      setResult(await r.json());
    } catch {
      setResult({ error: "Request failed." });
    } finally {
      setBusy(false);
    }
  }

  if (!tasks.length) {
    return (
      <div className="border border-rule bg-white p-4 text-sm text-ink-muted">
        Demo tasks are not available in this build.
      </div>
    );
  }

  return (
    <div className="border border-rule bg-white p-4">
      <p className="mb-4 text-xs text-ink-muted">
        Runs two live model calls on one pre-defined research task: an initial
        answer, then the selected intervention. This is a single illustrative
        trial, not a reproduction of the experiment — one trial tells you
        nothing statistically. Rate limited, and the API key stays server-side.
      </p>

      <div className="grid gap-3 sm:grid-cols-3">
        <label className="text-xs">
          <span className="mb-1 block text-ink-muted">Difficulty</span>
          <select
            className="w-full border border-rule bg-paper px-2 py-1.5 text-sm"
            value={difficulty}
            onChange={(e) => setDifficulty(Number(e.target.value))}
          >
            <option value={1}>Level 1 — easy</option>
            <option value={2}>Level 2 — moderate</option>
            <option value={3}>Level 3 — difficult</option>
          </select>
        </label>

        <label className="text-xs">
          <span className="mb-1 block text-ink-muted">Task</span>
          <select
            className="w-full border border-rule bg-paper px-2 py-1.5 text-sm"
            value={taskId}
            onChange={(e) => setTaskId(e.target.value)}
          >
            {visible.map((t) => (
              <option key={t.task_id} value={t.task_id}>
                {t.family} · {t.task_id.split("-").pop()}
              </option>
            ))}
          </select>
        </label>

        <label className="text-xs">
          <span className="mb-1 block text-ink-muted">Condition</span>
          <select
            className="w-full border border-rule bg-paper px-2 py-1.5 text-sm"
            value={condition}
            onChange={(e) => setCondition(e.target.value)}
          >
            {CONDITIONS.map((c) => (
              <option key={c.id} value={c.id}>
                {c.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {selected && (
        <pre className="mt-3 max-h-40 overflow-auto whitespace-pre-wrap border border-rule bg-paper p-3 font-mono text-[11px] leading-relaxed">
          {selected.prompt}
        </pre>
      )}

      <button
        onClick={run}
        disabled={busy || !taskId}
        className="mt-3 border border-accent bg-accent px-4 py-1.5 text-sm text-white disabled:opacity-40"
      >
        {busy ? "Running two model calls…" : "Run trial"}
      </button>

      {result?.error && (
        <p className="mt-3 border-l-2 border-warn bg-paper px-3 py-2 text-sm text-warn">
          {result.error}
        </p>
      )}

      {result && !result.error && (
        <div className="mt-4 border-t border-rule pt-4">
          <div className="grid gap-3 sm:grid-cols-3 text-sm">
            <div className="border border-rule p-3">
              <div className="text-xs text-ink-faint">Initial answer</div>
              <div className="font-mono text-base">{result.initial?.answer}</div>
              <div
                className={
                  result.initial?.correct ? "text-xs text-good" : "text-xs text-bad"
                }
              >
                {result.initial?.correct ? "correct" : "incorrect"}
                {result.initial?.confidence !== null &&
                  ` · stated confidence ${result.initial?.confidence}`}
              </div>
            </div>

            <div className="border border-rule p-3">
              <div className="text-xs text-ink-faint">
                After {result.conditionLabel}
              </div>
              <div className="font-mono text-base">
                {result.revised?.answer ?? "—"}
              </div>
              <div
                className={
                  result.revised?.correct ? "text-xs text-good" : "text-xs text-bad"
                }
              >
                {result.revised?.correct === null
                  ? "unparseable"
                  : result.revised?.correct
                    ? "correct"
                    : "incorrect"}
                {result.revised?.confidence !== null &&
                  ` · stated confidence ${result.revised?.confidence}`}
              </div>
              {result.revised?.assessment && (
                <div className="mt-1 text-xs text-ink-muted">
                  model called the previous answer{" "}
                  <span className="font-mono">{result.revised.assessment}</span>
                </div>
              )}
            </div>

            <div className="border border-rule p-3">
              <div className="text-xs text-ink-faint">Ground truth</div>
              <div className="font-mono text-base">{result.groundTruth}</div>
              <div className="text-xs text-ink-muted">
                computed by the generator
              </div>
            </div>
          </div>

          <p
            className={`mt-3 text-sm font-semibold ${
              OUTCOME_TEXT[result.outcome ?? ""]?.cls ?? ""
            }`}
          >
            {OUTCOME_TEXT[result.outcome ?? ""]?.text ?? result.outcome}
            {result.changed ? " · answer changed" : " · answer unchanged"}
            {result.cached && (
              <span className="ml-2 text-xs font-normal text-ink-faint">
                (served from cache — no new API call)
              </span>
            )}
          </p>

          <button
            onClick={() => setShowRaw((v) => !v)}
            className="mt-3 text-xs text-accent underline"
          >
            {showRaw ? "Hide" : "Show"} raw model output
          </button>
          {showRaw && (
            <div className="mt-2 space-y-2">
              <pre className="max-h-52 overflow-auto whitespace-pre-wrap border border-rule bg-paper p-2 font-mono text-[10px]">
                {result.initial?.raw}
              </pre>
              <pre className="max-h-52 overflow-auto whitespace-pre-wrap border border-rule bg-paper p-2 font-mono text-[10px]">
                {result.revised?.raw}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
