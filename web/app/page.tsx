import Dashboard from "@/components/Dashboard";
import LiveDemo from "@/components/LiveDemo";

export default function Page() {
  return (
    <div>
      <section>
        <h2 className="border-b border-rule pb-1 text-lg font-semibold">
          What this study measures
        </h2>
        <p className="mt-3 text-sm leading-relaxed">
          Four candidate behavioral properties — self-correction, instruction
          consistency, robustness to misleading information, and
          confidence/correctness correspondence — are measured on the same
          procedurally generated tasks under six conditions and three levels of
          structurally defined difficulty. All interventions act on the{" "}
          <em>same</em> initial answer, so every comparison is exactly paired.
        </p>
        <p className="mt-2 text-sm leading-relaxed">
          These properties are <strong>not</strong> a definition of alignment.
          The question is narrower and answerable: do they stay stable when
          conditions get harder?
        </p>
        <p className="mt-2 text-sm leading-relaxed text-ink-muted">
          The design includes a neutral <strong>reprompt control</strong>: a
          second turn that asks for the answer again without asking for a
          critique. Without it, any difference between one-turn and
          critique-and-revise is confounded with simply getting another turn.
        </p>
      </section>

      <section className="mt-8">
        <h2 className="border-b border-rule pb-1 text-lg font-semibold">
          Live demonstration
        </h2>
        <div className="mt-3">
          <LiveDemo />
        </div>
      </section>

      <section className="mt-10">
        <h2 className="border-b border-rule pb-1 text-lg font-semibold">
          Experiment results
        </h2>
        <div className="mt-3">
          <Dashboard />
        </div>
      </section>
    </div>
  );
}
