import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Alignment Invariants",
  description:
    "Experimental study of whether alignment-relevant LLM behaviors remain stable under increasing task difficulty and behavioral pressure.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="font-serif">
        <div className="mx-auto max-w-5xl px-5 py-8">
          <header className="border-b border-rule pb-4">
            <h1 className="text-2xl font-semibold tracking-tight">
              Alignment Invariants
            </h1>
            <p className="mt-1 text-sm text-ink-muted">
              Do alignment-relevant behavioral properties stay stable as task
              difficulty and behavioral pressure increase?
            </p>
            <p className="mt-3 border-l-2 border-warn bg-white px-3 py-2 text-xs text-warn">
              Research demonstration — not a production safety evaluation.
              Results describe one model on one small synthetic task set.
            </p>
          </header>
          <main className="py-6">{children}</main>
          <footer className="mt-10 border-t border-rule pt-4 text-xs text-ink-faint">
            <a
              className="underline hover:text-accent"
              href="https://github.com/Sriyansh-28/alignment-invariants"
            >
              Source, data, and full report on GitHub
            </a>
            <span className="mx-2">·</span>
            <span>
              Every number shown is read from committed experiment output.
            </span>
          </footer>
        </div>
      </body>
    </html>
  );
}
