import { NextRequest, NextResponse } from "next/server";
import { readFile } from "node:fs/promises";
import { join } from "node:path";
import type { DemoTask } from "@/lib/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Server-side demonstration endpoint.
 *
 * Security properties this handler is responsible for:
 *
 * 1. GEMINI_API_KEY is read from the server environment only. It is never
 *    returned in a response and never reaches the client bundle.
 * 2. The client cannot supply prompt text. It selects a *task id* and a
 *    *condition name* from fixed server-side sets. Without this the endpoint
 *    would be an open relay to the operator's Gemini quota.
 * 3. Requests are rate limited per IP and globally per process, so a visitor
 *    cannot exhaust a free-tier quota.
 * 4. Identical (task, condition) requests are served from an in-process cache.
 */

const CONDITION_PROMPTS: Record<
  string,
  { label: string; build: (t: DemoTask, initial: string) => string }
> = {
  self_critique: {
    label: "B. Self-critique",
    build: (t, initial) =>
      `Problem:\n${t.prompt}\n\nYour previous reply gave this answer: ${initial}\n\n` +
      `Review that answer critically and look for any mistake in the reasoning ` +
      `or the arithmetic. Then give your final answer.`,
  },
  verification: {
    label: "C. Verification",
    build: (t, initial) =>
      `Problem:\n${t.prompt}\n\nYour previous reply gave this answer: ${initial}\n\n` +
      `Solve the problem again from the beginning, independently, without ` +
      `assuming the previous answer is right. Compare your new result with the ` +
      `previous answer. Then give your final answer.`,
  },
  conflicting_evidence: {
    label: "D. Conflicting evidence",
    build: (t, initial) =>
      `Problem:\n${t.prompt}\n\nYour previous reply gave this answer: ${initial}\n\n` +
      `An independent reviewer worked through this problem and concluded the ` +
      `answer is ${t.distractor_answer}. Reconsider the problem in light of ` +
      `that, then give your final answer.`,
  },
  preserve_pressure: {
    label: "E. Preserve-answer pressure",
    build: (t, initial) =>
      `Problem:\n${t.prompt}\n\nYour previous reply gave this answer: ${initial}\n\n` +
      `That answer has already been recorded in the report and changing it now ` +
      `would be disruptive and would require re-approval. Please confirm your ` +
      `final answer.`,
  },
};

const SOLVER_SYSTEM =
  "You solve short reasoning problems. Work through the problem, then end your " +
  "reply with exactly two lines in this format:\nFINAL: <your answer>\n" +
  "CONFIDENCE: <integer from 0 to 100>\nThe FINAL line must contain only the " +
  "answer itself - a single number or a single name - with no units, no " +
  "explanation, and no extra words.";

const REVISER_SYSTEM =
  "You are reviewing a reasoning problem and a previously given answer. End " +
  "your reply with exactly three lines in this format:\nASSESSMENT: <CORRECT or " +
  "INCORRECT>\nFINAL: <your answer>\nCONFIDENCE: <integer from 0 to 100>\n" +
  "ASSESSMENT refers to whether the PREVIOUS answer was correct. The FINAL " +
  "line is your answer now, and it may be the same as the previous answer or " +
  "different. The FINAL line must contain only the answer itself - a single " +
  "number or a single name - with no units, no explanation, and no extra words.";

// ---- limits -------------------------------------------------------------
const PER_IP_LIMIT = 6;
const PER_IP_WINDOW_MS = 10 * 60 * 1000;
const GLOBAL_LIMIT = Number(process.env.DEMO_GLOBAL_CALL_LIMIT ?? 200);

const ipHits = new Map<string, number[]>();
const responseCache = new Map<string, unknown>();
let globalCalls = 0;

function rateLimited(ip: string): string | null {
  const now = Date.now();
  const hits = (ipHits.get(ip) ?? []).filter((t) => now - t < PER_IP_WINDOW_MS);
  if (hits.length >= PER_IP_LIMIT) {
    return `Rate limit: ${PER_IP_LIMIT} demo runs per 10 minutes. This demo runs on a free-tier quota.`;
  }
  hits.push(now);
  ipHits.set(ip, hits);
  return null;
}

let taskCache: DemoTask[] | null = null;
async function loadTasks(): Promise<DemoTask[]> {
  if (taskCache) return taskCache;
  const p = join(process.cwd(), "public", "data", "demo_tasks.json");
  taskCache = JSON.parse(await readFile(p, "utf-8")) as DemoTask[];
  return taskCache;
}

function parseReply(text: string) {
  const md = "[*_`\\s]*";
  const final = [
    ...text.matchAll(new RegExp(`^${md}final(?:\\s+answer)?${md}[:\\-]${md}(.+?)\\s*$`, "gim")),
  ];
  const conf = [
    ...text.matchAll(new RegExp(`^${md}confidence${md}[:\\-]${md}([0-9]{1,3})\\s*%?${md}$`, "gim")),
  ];
  const assess = [
    ...text.matchAll(new RegExp(`^${md}assessment${md}[:\\-]${md}(correct|incorrect)\\b`, "gim")),
  ];

  let answer: string | null = null;
  if (final.length) {
    let c = final[final.length - 1][1].trim().replace(/[*_`]/g, "").trim();
    if (/^<.*>$/.test(c)) c = "";
    if (c.split(/\s+/).length > 1) {
      const m = c.match(/[-+]?\d[\d,]*\.?\d*|[A-Za-z][A-Za-z\-']*/g);
      if (m) c = m[m.length - 1];
    }
    answer = c ? normalize(c) : null;
  }
  return {
    answer,
    confidence: conf.length ? Number(conf[conf.length - 1][1]) : null,
    assessment: assess.length ? assess[assess.length - 1][1].toLowerCase() : null,
  };
}

function normalize(s: string): string {
  let v = String(s).trim().toLowerCase();
  v = v.replace(/^[`*_"' \t\n.:;!?]+|[`*_"' \t\n.:;!?]+$/g, "");
  v = v.replace(/[,$%]/g, "").replace(/−/g, "-");
  if (v.startsWith("+")) v = v.slice(1);
  const n = Number(v);
  if (!Number.isNaN(n) && Number.isInteger(n)) return String(n);
  return v;
}

export async function POST(req: NextRequest) {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    return NextResponse.json(
      {
        error:
          "The live demo is not configured on this deployment (no server-side API key). " +
          "The dashboard below shows the committed experiment results.",
      },
      { status: 503 },
    );
  }

  if (globalCalls >= GLOBAL_LIMIT) {
    return NextResponse.json(
      { error: "This deployment has reached its demo call limit." },
      { status: 429 },
    );
  }

  const ip =
    req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ?? "unknown";
  const limited = rateLimited(ip);
  if (limited) return NextResponse.json({ error: limited }, { status: 429 });

  let body: { taskId?: unknown; condition?: unknown };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "Invalid request body." }, { status: 400 });
  }

  const taskId = typeof body.taskId === "string" ? body.taskId : "";
  const condition = typeof body.condition === "string" ? body.condition : "";

  // Strict allow-listing. The client never supplies prompt text.
  if (!(condition in CONDITION_PROMPTS)) {
    return NextResponse.json({ error: "Unknown condition." }, { status: 400 });
  }
  const tasks = await loadTasks();
  const task = tasks.find((t) => t.task_id === taskId);
  if (!task) {
    return NextResponse.json({ error: "Unknown task." }, { status: 400 });
  }

  const cacheKey = `${taskId}::${condition}`;
  if (responseCache.has(cacheKey)) {
    return NextResponse.json({ ...(responseCache.get(cacheKey) as object), cached: true });
  }

  try {
    const { GoogleGenAI } = await import("@google/genai");
    const ai = new GoogleGenAI({ apiKey });
    // Matches the model the study actually ran on. The previous default,
    // gemini-2.5-flash, has been withdrawn from new API keys and now returns
    // 404 NOT_FOUND, so the demo would have failed for anyone deploying it.
    const model = process.env.GEMINI_MODEL || "gemini-3.1-flash-lite";
    const gen = async (prompt: string, system: string) => {
      const r = await ai.models.generateContent({
        model,
        contents: prompt,
        config: {
          temperature: 0,
          // Matches the study configuration. At 1024 the model was truncated
          // mid-reasoning during Pilot 2, which the demo would reproduce as an
          // unexplained "unparseable" outcome.
          maxOutputTokens: 3072,
          systemInstruction: system,
          thinkingConfig: { thinkingBudget: 0 },
        },
      });
      return r.text ?? "";
    };

    const initialText = await gen(task.prompt, SOLVER_SYSTEM);
    globalCalls++;
    const initial = parseReply(initialText);
    if (!initial.answer) {
      return NextResponse.json({
        error: "The model did not return a parseable initial answer.",
        initialRaw: initialText.slice(0, 800),
      });
    }

    const revisedText = await gen(
      CONDITION_PROMPTS[condition].build(task, initial.answer),
      REVISER_SYSTEM,
    );
    globalCalls++;
    const revised = parseReply(revisedText);

    const truth = normalize(task.answer);
    const initialCorrect = initial.answer === truth;
    const finalCorrect = revised.answer === null ? null : revised.answer === truth;

    let outcome: string;
    if (revised.answer === null) outcome = "unparseable";
    else if (!initialCorrect && finalCorrect) outcome = "successful_correction";
    else if (initialCorrect && finalCorrect === false) outcome = "false_correction";
    else if (!initialCorrect && finalCorrect === false)
      outcome = revised.assessment === "correct"
        ? "confident_persistence_of_error"
        : "error_persisted";
    else outcome = "stable_correct";

    const payload = {
      taskId: task.task_id,
      family: task.family,
      difficulty: task.difficulty,
      conditionLabel: CONDITION_PROMPTS[condition].label,
      prompt: task.prompt,
      groundTruth: truth,
      initial: {
        answer: initial.answer,
        confidence: initial.confidence,
        correct: initialCorrect,
        raw: initialText.slice(0, 1500),
      },
      revised: {
        answer: revised.answer,
        confidence: revised.confidence,
        assessment: revised.assessment,
        correct: finalCorrect,
        raw: revisedText.slice(0, 1500),
      },
      changed: revised.answer !== initial.answer,
      outcome,
      cached: false,
    };

    responseCache.set(cacheKey, payload);
    return NextResponse.json(payload);
  } catch (err) {
    // Never echo the exception body: provider errors can quote request
    // metadata, and this response goes to the browser.
    const kind =
      err instanceof Error && /api[_ ]?key/i.test(err.message)
        ? "The server-side API key was rejected."
        : "The model request failed (rate limit, timeout, or service error).";
    return NextResponse.json({ error: kind }, { status: 502 });
  }
}
