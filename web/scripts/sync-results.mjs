/**
 * Copies experiment output into web/public/data so the dashboard renders from
 * committed experiment results rather than from anything typed by hand.
 *
 * If no results exist yet the dashboard renders an "experiments pending" state.
 * A results file produced by the mock provider is copied but keeps its
 * `is_real_model_output: false` flag, which the UI surfaces as a loud banner.
 */
import { mkdirSync, copyFileSync, existsSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(here, "..", "..");
const outDir = join(here, "..", "public", "data");

mkdirSync(outDir, { recursive: true });

const sources = [
  ["results/tables/summary.json", "summary.json"],
  ["results/tables/failure_analysis.json", "failure_analysis.json"],
  ["web/demo_tasks.json", "demo_tasks.json"],
];

let copied = 0;
for (const [src, dest] of sources) {
  const from = join(repoRoot, src);
  if (existsSync(from)) {
    copyFileSync(from, join(outDir, dest));
    console.log(`[sync] ${src} -> public/data/${dest}`);
    copied++;
  } else {
    console.log(`[sync] missing (ok): ${src}`);
  }
}

const statusPath = join(outDir, "status.json");
writeFileSync(
  statusPath,
  JSON.stringify(
    {
      hasResults: existsSync(join(repoRoot, "results/tables/summary.json")),
      syncedAt: new Date().toISOString(),
      filesCopied: copied,
    },
    null,
    2,
  ),
);
console.log(`[sync] wrote status.json (${copied} file(s) copied)`);
