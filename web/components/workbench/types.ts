export type WorkflowStep = 'define' | 'run' | 'investigate' | 'decide';
export type LoadState = 'loading' | 'ready' | 'empty' | 'error';
export type ReplayState =
  | 'idle'
  | 'working'
  | 'verified-pass'
  | 'verified-block'
  | 'error';
export type LaunchState = 'idle' | 'running' | 'success' | 'error';

export type RunSummary = {
  run_id: string;
  experiment: string;
  decision: 'passed' | 'failed';
  indexed_at: string;
  artifact_digests: Record<string, string>;
};

export type Metric = {
  score: number;
  evaluator_error_count?: number;
  missing_count?: number;
};

export type Summary = {
  attempted_generations: number;
  provider_success_count: number;
  provider_error_count: number;
  case_pass_count: number;
  case_fail_count: number;
  evaluator_metrics: {
    field_accuracy: Metric;
    schema_validity: Metric;
  };
  latency: { median_ms: number | null; p95_ms: number | null };
  usage: { total_tokens_total: number | null };
};

export type GateRule = {
  metric: string;
  rule: string;
  observed: number | null;
  threshold: number;
  passed: boolean;
  reason: string;
};

export type EvaluationEvidence = {
  evaluator: string;
  evaluator_version: string;
  status: string;
  reason: string;
  score: number | null;
  details: { mismatches?: unknown[]; schema_errors?: unknown[] };
  error: unknown;
};

export type FailedCase = {
  configuration: string;
  case_id: string;
  description: string;
  expected: unknown;
  actual: unknown;
  raw_response: unknown;
  provider_error: unknown;
  tags: string[];
  evaluations: EvaluationEvidence[];
};

export type Configuration = {
  name: string;
  provider: string;
  model: string;
  prompt: string;
  inference_parameters: Record<string, unknown>;
  provider_options: Record<string, unknown>;
  generation_count: number;
  status_counts: Record<string, number>;
  origin_counts: Record<string, number>;
};

export type RunDetail = RunSummary & {
  manifest_digest: string;
  dataset_version: string;
  dataset_digest: string;
  artifact_digests: Record<string, string>;
  report: {
    run_id: string;
    experiment: string;
    started_at: string;
    ended_at: string;
    duration_ms: number;
    configurations: Configuration[];
    baseline_summary: Summary;
    candidate_summary: Summary;
    gates: {
      decision: 'passed' | 'failed';
      rules: GateRule[];
      failures: GateRule[];
    };
    failed_cases: FailedCase[];
    regression: { newly_failing: string[]; newly_passing: string[] };
  };
};
