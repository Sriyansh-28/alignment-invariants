"use client";

import { useEffect, useState } from "react";
import type { Summary, RateBlock, IntervalBlock } from "@/lib/types";

const pct = (v: number | null | undefined) =>
  v === null || v === undefined ? "—" : `${(v * 100).toFixed(1)}%`;

const rate = (r: RateBlock | undefined) => {
  if (!r) return "—";
  if (r.value === null) return <span className="text-ink-faint">undefined</span>;
  return (
    <span>
      {pct(r.value)}{" "}
      <span className="text-xs text-ink-faint">
        ({r.numerator}/{r.denominator})
      </span>
    </span>
  );
};

const ci = (c: IntervalBlock | undefined) =>
  !c || c.low === null || c.high === null
    ? "—"
    : `[${(c.low * 100).toFixed(1)}, ${(c.high * 100).toFixed(1)}]`;

function Section({
  title,
  children,
  note,
}: {
  title: string;
  children: React.ReactNode;
  note?: string;
}) {
  return (
    <section className="mt-8">
      <h2 className="border-b border-rule pb-1 text-lg font-semibold">
        {title}
      </h2>
      {note && <p className="mt-2 text-xs text-ink-muted">{note}</p>}
      <div className="mt-3">{children}</div>
    </section>
  );
}

/** Horizontal bar with an error bar drawn from the confidence interval. */
function BarWithCI({ point, low, high }: IntervalBlock) {
  if (point === null) return <span className="text-ink-faint">—</span>;
  const p = point * 100;
  const lo = (low ?? point) * 100;
  const hi = (high ?? point) * 100;
  return (
    <div className="relative h-4 w-full min-w-[120px] bg-white">
      <div
        className="absolute top-1 h-2 bg-accent/25"
        style={{ left: `${lo}%`, width: `${Math.max(hi - lo, 0.5)}%` }}
        title={`95% CI: ${lo.toFixed(1)}–${hi.toFixed(1)}%`}
      />
      <div
        className="absolute top-0 h-4 w-[2px] bg-accent"
        style={{ left: `${p}%` }}
        title={`${p.toFixed(1)}%`}
      />
    </div>
  );
}

export default function Dashboard() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "pending">("loading");

  useEffect(() => {
    fetch("/data/summary.json")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("no results"))))
      .then((d: Summary) => {
        setSummary(d);
        setState("ready");
      })
      .catch(() => setState("pending"));
  }, []);

  if (state === "loading") {
    return <p className="text-sm text-ink-muted">Loading results…</p>;
  }

  if (state === "pending" || !summary) {
    return (
      <div className="border border-rule bg-white p-5">
        <h2 className="text-base font-semibold">Experiments pending</h2>
        <p className="mt-2 text-sm text-ink-muted">
          No experiment output has been committed yet, so there is nothing to
          display. This panel intentionally shows nothing rather than
          placeholder numbers.
        </p>
        <p className="mt-2 text-sm text-ink-muted">
          Run{" "}
          <code className="bg-paper px-1 font-mono text-xs">
            python -m src.run_experiment --config configs/experiment.yaml
          </code>{" "}
          followed by{" "}
          <code className="bg-paper px-1 font-mono text-xs">
            python -m analysis.analyze_results
          </code>
          , then rebuild.
        </p>
      </div>
    );
  }

  const isReal = summary.meta?.is_real_model_output !== false;
  const conds = Object.entries(summary.conditions);
  const pairwise = Object.entries(summary.tests?.primary_pairwise ?? {});
  const omnibus = summary.tests?.omnibus_cochran_q;

  return (
    <div>
      {!isReal && (
        <div className="mb-5 border-l-2 border-bad bg-white px-3 py-2 text-sm text-bad">
          <strong>Mock output.</strong> This results file was produced by the
          deterministic test provider, not by a language model. It exists to
          verify the pipeline and must not be read as experimental evidence.
        </div>
      )}

      <div className="border border-rule bg-white p-4 text-sm">
        <div className="grid grid-cols-2 gap-x-6 gap-y-1 sm:grid-cols-4">
          <div>
            <div className="text-xs text-ink-faint">Model</div>
            <div className="font-mono text-xs">{summary.meta?.model ?? "—"}</div>
          </div>
          <div>
            <div className="text-xs text-ink-faint">Trials</div>
            <div>{summary.n_trials}</div>
          </div>
          <div>
            <div className="text-xs text-ink-faint">Live API calls</div>
            <div>{summary.meta?.budget?.live_calls ?? "—"}</div>
          </div>
          <div>
            <div className="text-xs text-ink-faint">Unparseable</div>
            <div>{summary.data_quality?.unparseable_final ?? 0}</div>
          </div>
        </div>
      </div>

      {summary.power?.interpretation && (
        <p className="mt-3 border-l-2 border-rule pl-3 text-xs italic text-ink-muted">
          {summary.power.interpretation}
        </p>
      )}

      <Section
        title="Behavior by condition"
        note="Every rate carries its numerator and denominator. 'undefined' means the denominator was zero — for example, error detection is not defined for conditions that never request a self-assessment."
      >
        <div className="table-scroll">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-rule text-left text-xs text-ink-muted">
                <th className="py-2 pr-3">Condition</th>
                <th className="py-2 pr-3">Final accuracy</th>
                <th className="py-2 pr-3 w-32">95% CI</th>
                <th className="py-2 pr-3">Corrected</th>
                <th className="py-2 pr-3">False correction</th>
                <th className="py-2 pr-3">Changed answer</th>
                <th className="py-2 pr-3">Format OK</th>
                <th className="py-2 pr-3 text-right">Net</th>
              </tr>
            </thead>
            <tbody>
              {conds.map(([key, c]) => (
                <tr key={key} className="border-b border-rule/50 align-middle">
                  <td className="py-2 pr-3 whitespace-nowrap">{c.label}</td>
                  <td className="py-2 pr-3">{rate(c.metrics.final_accuracy)}</td>
                  <td className="py-2 pr-3">
                    <BarWithCI {...c.final_accuracy_ci} />
                    <div className="mt-0.5 text-[10px] text-ink-faint">
                      {ci(c.final_accuracy_ci)}
                    </div>
                  </td>
                  <td className="py-2 pr-3">
                    {rate(c.metrics.successful_correction_rate)}
                  </td>
                  <td className="py-2 pr-3">
                    {rate(c.metrics.false_correction_rate)}
                  </td>
                  <td className="py-2 pr-3">
                    {rate(c.metrics.answer_change_rate)}
                  </td>
                  <td className="py-2 pr-3">
                    {rate(c.metrics.instruction_consistency)}
                  </td>
                  <td
                    className={`py-2 pr-3 text-right font-mono ${
                      c.net_change.net > 0
                        ? "text-good"
                        : c.net_change.net < 0
                          ? "text-bad"
                          : ""
                    }`}
                  >
                    {c.net_change.net > 0 ? "+" : ""}
                    {c.net_change.net}
                    <span className="ml-1 text-[10px] text-ink-faint">
                      (+{c.net_change.gained}/−{c.net_change.lost})
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-xs text-ink-muted">
          <strong>Net</strong> = errors fixed minus correct answers broken. An
          intervention can have a positive correction rate and still be a net
          harm.
        </p>
      </Section>

      <Section
        title="Accuracy across the difficulty ladder"
        note="Difficulty is defined by generator parameters (operation count, chain depth, predicate count), not by human labels."
      >
        <div className="table-scroll">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-rule text-left text-xs text-ink-muted">
                <th className="py-2 pr-3">Condition</th>
                <th className="py-2 pr-3">L1 easy</th>
                <th className="py-2 pr-3">L2 moderate</th>
                <th className="py-2 pr-3">L3 difficult</th>
                <th className="py-2 pr-3">Trend p</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(summary.by_difficulty)
                .filter(([k]) => !k.startsWith("_"))
                .map(([key, blk]) => (
                  <tr key={key} className="border-b border-rule/50">
                    <td className="py-2 pr-3 whitespace-nowrap">{blk.label}</td>
                    {["1", "2", "3"].map((d) => (
                      <td key={d} className="py-2 pr-3">
                        {rate(blk.levels?.[d]?.metrics?.final_accuracy)}
                      </td>
                    ))}
                    <td className="py-2 pr-3 font-mono text-xs">
                      {blk.trend_test?.p_value === null ||
                      blk.trend_test?.p_value === undefined
                        ? "—"
                        : blk.trend_test.p_value.toFixed(3)}
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section
        title="Statistical comparisons"
        note="Paired comparisons on the same tasks, exact McNemar test, Holm–Bonferroni corrected across the pre-registered family."
      >
        {omnibus && (
          <p className="mb-3 text-sm">
            Omnibus (Cochran&apos;s Q across all conditions):{" "}
            <span className="font-mono text-xs">
              Q = {omnibus.statistic?.toFixed(3) ?? "—"}, p ={" "}
              {omnibus.p_value?.toFixed(4) ?? "—"}
            </span>
          </p>
        )}
        <div className="table-scroll">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-rule text-left text-xs text-ink-muted">
                <th className="py-2 pr-3">Comparison</th>
                <th className="py-2 pr-3">n</th>
                <th className="py-2 pr-3">Discordant</th>
                <th className="py-2 pr-3">Risk diff</th>
                <th className="py-2 pr-3">95% CI</th>
                <th className="py-2 pr-3">p (raw)</th>
                <th className="py-2 pr-3">p (Holm)</th>
              </tr>
            </thead>
            <tbody>
              {pairwise.map(([key, t]) => (
                <tr key={key} className="border-b border-rule/50">
                  <td className="py-2 pr-3 text-xs">{t.comparison}</td>
                  <td className="py-2 pr-3">{t.n_pairs}</td>
                  <td className="py-2 pr-3 font-mono text-xs">
                    {t.test.effect.b01}↓ / {t.test.effect.b10}↑
                  </td>
                  <td className="py-2 pr-3 font-mono text-xs">
                    {t.test.effect.risk_difference >= 0 ? "+" : ""}
                    {(t.test.effect.risk_difference * 100).toFixed(1)}pp
                  </td>
                  <td className="py-2 pr-3 font-mono text-[11px]">
                    {t.paired_difference_ci.low === null
                      ? "—"
                      : `[${(t.paired_difference_ci.low * 100).toFixed(1)}, ${(
                          t.paired_difference_ci.high! * 100
                        ).toFixed(1)}]`}
                  </td>
                  <td className="py-2 pr-3 font-mono text-xs">
                    {t.test.p_value?.toFixed(4) ?? "—"}
                  </td>
                  <td
                    className={`py-2 pr-3 font-mono text-xs ${
                      t.holm?.reject_at_alpha ? "font-bold text-accent" : ""
                    }`}
                  >
                    {t.holm?.p_adjusted?.toFixed(4) ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-xs text-ink-muted">
          Discordant cells: <span className="font-mono">↓</span> = right under
          the first condition and wrong under the second;{" "}
          <span className="font-mono">↑</span> = the reverse. These are the only
          items carrying information in a paired test.
        </p>
      </Section>

      <Section
        title="Stated confidence"
        note="Stated confidence is a verbal report, not a probability elicited under a proper scoring rule. Calibration metrics are computed only when the model emitted at least three distinct confidence values."
      >
        <div className="table-scroll">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-rule text-left text-xs text-ink-muted">
                <th className="py-2 pr-3">Condition</th>
                <th className="py-2 pr-3">Mean confidence</th>
                <th className="py-2 pr-3">Accuracy</th>
                <th className="py-2 pr-3">Gap</th>
                <th className="py-2 pr-3">Distinct values</th>
                <th className="py-2 pr-3">ECE</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(summary.confidence).map(([key, c]) => (
                <tr key={key} className="border-b border-rule/50">
                  <td className="py-2 pr-3 text-xs">
                    {summary.conditions[key]?.label ?? key}
                  </td>
                  <td className="py-2 pr-3">{pct(c.mean_confidence)}</td>
                  <td className="py-2 pr-3">{pct(c.accuracy)}</td>
                  <td
                    className={`py-2 pr-3 ${
                      (c.overconfidence_gap ?? 0) > 0.1 ? "text-warn" : ""
                    }`}
                  >
                    {c.overconfidence_gap === undefined
                      ? "—"
                      : `${c.overconfidence_gap >= 0 ? "+" : ""}${(
                          c.overconfidence_gap * 100
                        ).toFixed(1)}pp`}
                  </td>
                  <td className="py-2 pr-3 font-mono text-xs">
                    {c.n_distinct ?? "—"}
                  </td>
                  <td className="py-2 pr-3 font-mono text-xs">
                    {c.calibration_measurable
                      ? (c.ece?.toFixed(3) ?? "—")
                      : "not measurable"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      {(summary.probes?.response_consistency ||
        summary.probes?.prompt_ablation) && (
        <Section title="Probes and ablations">
          <ul className="space-y-2 text-sm">
            {summary.probes.response_consistency && (
              <li>
                <strong>Response consistency:</strong>{" "}
                {rate(summary.probes.response_consistency)}
                <div className="text-xs text-ink-muted">
                  {summary.probes.response_consistency.note}
                </div>
              </li>
            )}
            {summary.probes.prompt_ablation && (
              <li>
                <strong>Prompt-wording ablation</strong> (
                <span className="font-mono text-xs">
                  {summary.probes.prompt_ablation.name}
                </span>
                ): {summary.probes.prompt_ablation.final_correct}/
                {summary.probes.prompt_ablation.n} correct after the alternative
                self-critique wording, {summary.probes.prompt_ablation.changed}{" "}
                answers changed.
              </li>
            )}
          </ul>
        </Section>
      )}
    </div>
  );
}
