/** Shapes mirroring results/tables/summary.json, written by
 *  analysis/analyze_results.py. The dashboard renders only these fields, so a
 *  number can never appear in the UI unless the analysis produced it. */

export interface RateBlock {
  numerator: number;
  denominator: number;
  value: number | null;
}

export interface IntervalBlock {
  point: number | null;
  low: number | null;
  high: number | null;
  method: string;
}

export interface ConditionMetrics {
  initial_accuracy: RateBlock;
  final_accuracy: RateBlock;
  error_detection_rate: RateBlock;
  false_detection_rate: RateBlock;
  successful_correction_rate: RateBlock;
  false_correction_rate: RateBlock;
  error_persistence_rate: RateBlock;
  answer_change_rate: RateBlock;
  instruction_consistency: RateBlock;
}

export interface ConditionBlock {
  label: string;
  n: number;
  metrics: ConditionMetrics;
  final_accuracy_ci: IntervalBlock;
  successful_correction_ci: IntervalBlock;
  false_correction_ci: IntervalBlock;
  net_change: { gained: number; lost: number; net: number };
}

export interface DifficultyLevel {
  metrics: ConditionMetrics;
  accuracy_ci: IntervalBlock;
  n: number;
}

export interface DifficultyBlock {
  label: string;
  levels: Record<string, DifficultyLevel>;
  trend_test: {
    name: string;
    statistic: number | null;
    p_value: number | null;
    effect: Record<string, unknown>;
    n: number;
    note: string;
  };
}

export interface PairwiseTest {
  comparison: string;
  n_pairs: number;
  test: {
    p_value: number | null;
    effect: {
      b01: number;
      b10: number;
      n_discordant: number;
      risk_difference: number;
      acc_a?: number;
      acc_b?: number;
    };
    note: string;
  };
  paired_difference_ci: IntervalBlock;
  holm?: {
    p_raw: number;
    p_adjusted: number;
    reject_at_alpha: boolean;
    family_size: number;
  };
}

export interface Summary {
  meta: {
    model?: string;
    phase?: string;
    provider?: string;
    is_real_model_output?: boolean;
    finished_utc?: string;
    budget?: {
      live_calls: number;
      successful_calls: number;
      failed_calls: number;
      cache_hits: number;
      total_tokens: number;
      calls_per_condition: Record<string, number>;
    };
  };
  n_trials: number;
  conditions: Record<string, ConditionBlock>;
  by_difficulty: Record<string, DifficultyBlock>;
  by_family: Record<string, Record<string, ConditionMetrics>>;
  tests: {
    omnibus_cochran_q?: {
      statistic: number | null;
      p_value: number | null;
      note: string;
    };
    omnibus_n_common_tasks?: number;
    primary_pairwise?: Record<string, PairwiseTest>;
    multiplicity?: { method: string; family_size: number };
  };
  confidence: Record<
    string,
    {
      n: number;
      mean_confidence?: number;
      accuracy?: number;
      overconfidence_gap?: number;
      distinct_values?: number[];
      n_distinct?: number;
      calibration_measurable: boolean;
      reason?: string;
      ece?: number | null;
    }
  >;
  probes: {
    response_consistency?: RateBlock & { note: string };
    prompt_ablation?: {
      name: string;
      n: number;
      initial_correct: number;
      final_correct: number;
      changed: number;
    };
  };
  data_quality: {
    total_trials: number;
    unparseable_final: number;
    unparseable_by_condition: Record<string, number>;
    note: string;
  };
  power: {
    n_pairs: number;
    mde_risk_difference: number | null;
    interpretation?: string;
  };
}

export interface DemoTask {
  task_id: string;
  family: string;
  difficulty: number;
  prompt: string;
  answer: string;
  distractor_answer: string;
}
