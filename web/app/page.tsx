'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Activity,
  ArrowDownRight,
  Check,
  ChevronRight,
  CircleDot,
  Clock3,
  Database,
  GitCompareArrows,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';

const API =
  process.env.NEXT_PUBLIC_EVALFORGE_API_URL ?? 'http://127.0.0.1:8765';

type RunSummary = {
  run_id: string;
  experiment: string;
  decision: 'passed' | 'failed';
  indexed_at: string;
  artifact_digests: Record<string, string>;
};
type Metric = { score: number };
type Summary = {
  attempted_generations: number;
  case_pass_count: number;
  evaluator_metrics: { field_accuracy: Metric; schema_validity: Metric };
  latency: { p95_ms: number | null };
  usage: { total_tokens_total: number | null };
};
type GateRule = {
  metric: string;
  rule: string;
  observed: number | null;
  threshold: number;
  passed: boolean;
  reason: string;
};
type FailedCase = {
  configuration: string;
  case_id: string;
  description: string;
  expected: unknown;
  actual: unknown;
  tags: string[];
  evaluations: { evaluator: string; reason: string; score: number | null }[];
};
type RunDetail = RunSummary & {
  report: {
    run_id: string;
    experiment: string;
    baseline_summary: Summary;
    candidate_summary: Summary;
    gates: {
      decision: 'passed' | 'failed';
      rules: GateRule[];
      failures: GateRule[];
    };
    failed_cases: FailedCase[];
    regression: { newly_failing: string[]; newly_passing: string[] };
    configurations: {
      name: string;
      model: string;
      prompt: string;
      provider: string;
    }[];
  };
};

function percent(value: number) {
  return `${Math.round(value * 100)}%`;
}
function latency(value: number | null) {
  return value === null ? '--' : `${(value / 1000).toFixed(2)}s`;
}
function json(value: unknown) {
  return JSON.stringify(value, null, 2);
}

export default function Home() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [selectedRun, setSelectedRun] = useState<string | null>(null);
  const [selectedFailure, setSelectedFailure] = useState<FailedCase | null>(
    null,
  );
  const [state, setState] = useState<'loading' | 'ready' | 'empty' | 'error'>(
    'loading',
  );
  const [replayState, setReplayState] = useState<
    'idle' | 'working' | 'passed' | 'failed'
  >('idle');

  const loadRuns = useCallback(async () => {
    setState('loading');
    try {
      const response = await fetch(`${API}/api/runs`, { cache: 'no-store' });
      if (!response.ok) throw new Error('history unavailable');
      const values = (await response.json()) as RunSummary[];
      setRuns(values);
      if (!values.length) {
        setDetail(null);
        setState('empty');
        return;
      }
      const nextId =
        values.find(
          (run) => run.experiment === 'invoice-extraction-local-openai',
        )?.run_id ?? values[0].run_id;
      const detailResponse = await fetch(
        `${API}/api/runs/${encodeURIComponent(nextId)}`,
        { cache: 'no-store' },
      );
      if (!detailResponse.ok) throw new Error('run unavailable');
      setSelectedRun(nextId);
      setDetail((await detailResponse.json()) as RunDetail);
      setSelectedFailure(null);
      setReplayState('idle');
      setState('ready');
    } catch {
      setState('error');
    }
  }, []);

  useEffect(() => {
    void Promise.resolve().then(loadRuns);
  }, [loadRuns]);
  useEffect(() => {
    if (!selectedRun || detail?.run_id === selectedRun) return;
    void fetch(`${API}/api/runs/${encodeURIComponent(selectedRun)}`, {
      cache: 'no-store',
    })
      .then(async (response) => {
        if (!response.ok) throw new Error();
        return (await response.json()) as RunDetail;
      })
      .then((value) => {
        setDetail(value);
        setSelectedFailure(null);
        setReplayState('idle');
      })
      .catch(() => setState('error'));
  }, [selectedRun, detail?.run_id]);

  const configuredGates = useMemo(
    () =>
      detail?.report.gates.rules.filter(
        (gate) => gate.rule !== 'data_integrity',
      ) ?? [],
    [detail],
  );
  const uniqueFailures = useMemo(() => {
    const byCase = new Map<string, FailedCase>();
    for (const failure of detail?.report.failed_cases ?? [])
      if (!byCase.has(failure.case_id) || failure.configuration === 'candidate')
        byCase.set(failure.case_id, failure);
    return [...byCase.values()];
  }, [detail]);

  async function replay() {
    if (!selectedRun) return;
    setReplayState('working');
    try {
      const response = await fetch(
        `${API}/api/runs/${encodeURIComponent(selectedRun)}/replay`,
        { method: 'POST' },
      );
      if (!response.ok) throw new Error();
      const value = (await response.json()) as { gates: { decision: string } };
      setReplayState(value.gates.decision === 'passed' ? 'passed' : 'failed');
    } catch {
      setReplayState('failed');
    }
  }

  return (
    <main className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-20 border-b border-border/70 bg-background/90 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-[1520px] items-center justify-between px-5 lg:px-8">
          <div className="flex items-center gap-3">
            <div className="forge-mark">
              <Sparkles className="size-4" />
            </div>
            <div>
              <p className="font-heading text-[15px] font-semibold tracking-tight">
                EvalForge
              </p>
              <p className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
                Evaluation control room
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className="hidden items-center gap-2 text-xs text-muted-foreground sm:flex">
              <span
                className={`size-1.5 rounded-full ${state === 'error' ? 'bg-rose-400' : 'bg-emerald-400 shadow-[0_0_12px_var(--color-emerald-400)]'}`}
              />
              {state === 'error'
                ? 'Local API unavailable'
                : 'Local history connected'}
            </span>
            <Button
              variant="outline"
              className="border-border/80 bg-card/60 text-xs"
              onClick={() => void loadRuns()}
              disabled={state === 'loading'}
            >
              <RefreshCw
                data-icon="inline-start"
                className={state === 'loading' ? 'animate-spin' : ''}
              />{' '}
              Refresh
            </Button>
          </div>
        </div>
      </header>
      <div className="mx-auto grid max-w-[1520px] grid-cols-1 lg:grid-cols-[250px_minmax(0,1fr)]">
        <aside className="border-b border-border/60 px-5 py-6 lg:min-h-[calc(100vh-64px)] lg:border-r lg:border-b-0 lg:px-6">
          <div className="mb-7 flex items-center justify-between">
            <p className="eyebrow">Experiment history</p>
            <Database className="size-3.5 text-muted-foreground" />
          </div>
          <nav
            aria-label="Experiment runs"
            className="grid gap-2 sm:grid-cols-2 lg:grid-cols-1"
          >
            {runs.map((run) => (
              <button
                key={run.run_id}
                onClick={() => setSelectedRun(run.run_id)}
                className={`run-item text-left ${selectedRun === run.run_id ? 'run-item-active' : ''}`}
              >
                <span className="mb-2 flex items-center justify-between">
                  <Badge
                    className={
                      run.decision === 'passed'
                        ? 'border-emerald-400/20 bg-emerald-400/10 text-emerald-300'
                        : 'border-rose-400/20 bg-rose-400/10 text-rose-300'
                    }
                  >
                    {run.decision}
                  </Badge>
                  <span className="text-[10px] text-muted-foreground">
                    {new Date(run.indexed_at).toLocaleDateString()}
                  </span>
                </span>
                <span className="block truncate text-sm font-medium">
                  {run.experiment}
                </span>
                <span className="mt-1 block truncate font-mono text-[10px] text-muted-foreground">
                  {run.run_id}
                </span>
              </button>
            ))}
          </nav>
          {detail && (
            <div className="mt-7 rounded-xl border border-border/60 bg-card/30 p-4">
              <div className="mb-2 flex items-center gap-2 text-xs font-medium">
                <ShieldCheck className="size-4 text-cyan-300" /> Immutable
                evidence
              </div>
              <p className="text-[11px] leading-5 text-muted-foreground">
                {Object.keys(detail.artifact_digests).length} artifacts verified
                by SHA-256 and ready for offline replay.
              </p>
              <Button
                size="sm"
                variant="ghost"
                className="mt-3 w-full justify-start text-[11px]"
                onClick={() => void replay()}
                disabled={replayState === 'working'}
              >
                <RotateCcw
                  data-icon="inline-start"
                  className={replayState === 'working' ? 'animate-spin' : ''}
                />
                {replayState === 'idle'
                  ? 'Verify offline replay'
                  : replayState === 'working'
                    ? 'Replaying...'
                    : replayState === 'passed'
                      ? 'Replay passed'
                      : 'Replay failed'}
              </Button>
            </div>
          )}
        </aside>
        <section className="min-w-0 px-5 py-7 lg:px-8 lg:py-9">
          {state === 'loading' && (
            <StateCard
              title="Loading experiment history"
              detail="Reading the local evidence index..."
            />
          )}
          {state === 'empty' && (
            <StateCard
              title="No indexed runs yet"
              detail="Run an EvalForge experiment to populate this control room."
            />
          )}
          {state === 'error' && (
            <StateCard
              error
              title="The local API is unavailable"
              detail="Start `evalforge serve --artifact-root artifacts`, then refresh."
            />
          )}
          {state === 'ready' && detail && (
            <Dashboard
              detail={detail}
              gates={configuredGates}
              failures={uniqueFailures}
              selectedFailure={selectedFailure}
              onFailure={setSelectedFailure}
            />
          )}
        </section>
      </div>
    </main>
  );
}

function StateCard({
  title,
  detail,
  error = false,
}: {
  title: string;
  detail: string;
  error?: boolean;
}) {
  return (
    <div className="mx-auto mt-20 max-w-xl rounded-2xl border border-border/60 bg-card/70 p-8 text-center">
      <div
        className={`mx-auto mb-4 flex size-10 items-center justify-center rounded-xl ${error ? 'bg-rose-400/10 text-rose-300' : 'bg-cyan-300/10 text-cyan-200'}`}
      >
        {error ? <TriangleAlert /> : <Database />}
      </div>
      <h1 className="text-xl font-semibold">{title}</h1>
      <p className="mt-2 text-sm text-muted-foreground">{detail}</p>
    </div>
  );
}

function Dashboard({
  detail,
  gates,
  failures,
  selectedFailure,
  onFailure,
}: {
  detail: RunDetail;
  gates: GateRule[];
  failures: FailedCase[];
  selectedFailure: FailedCase | null;
  onFailure: (value: FailedCase | null) => void;
}) {
  const report = detail.report;
  const baseline = report.baseline_summary;
  const candidate = report.candidate_summary;
  const passed = report.gates.decision === 'passed';
  const metrics = [
    {
      label: 'Schema validity',
      baseline: percent(baseline.evaluator_metrics.schema_validity.score),
      candidate: percent(candidate.evaluator_metrics.schema_validity.score),
      delta: 'No change',
    },
    {
      label: 'Field accuracy',
      baseline: percent(baseline.evaluator_metrics.field_accuracy.score),
      candidate: percent(candidate.evaluator_metrics.field_accuracy.score),
      delta:
        candidate.evaluator_metrics.field_accuracy.score >=
        baseline.evaluator_metrics.field_accuracy.score
          ? 'No regression'
          : 'Regressed',
    },
    {
      label: 'P95 latency',
      baseline: latency(baseline.latency.p95_ms),
      candidate: latency(candidate.latency.p95_ms),
      delta:
        baseline.latency.p95_ms && candidate.latency.p95_ms
          ? `${Math.round(candidate.latency.p95_ms - baseline.latency.p95_ms)}ms`
          : '—',
    },
  ];
  return (
    <>
      <div className="mb-8 flex flex-col justify-between gap-5 xl:flex-row xl:items-end">
        <div>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <Badge
              variant="outline"
              className="border-cyan-300/20 bg-cyan-300/5 text-cyan-200"
            >
              Indexed local run
            </Badge>
            <span className="font-mono text-[10px] text-muted-foreground">
              {report.run_id} · {candidate.attempted_generations * 2}{' '}
              generations
            </span>
          </div>
          <h1 className="max-w-3xl font-heading text-3xl font-semibold tracking-[-0.04em] sm:text-4xl">
            {passed
              ? 'Candidate cleared every release gate.'
              : 'Candidate blocked by release gates.'}
          </h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-muted-foreground">
            {report.experiment}. Inspect the comparison, gate evidence, and
            case-level failures below.
          </p>
        </div>
        <div
          className={`decision-seal ${passed ? '' : 'decision-seal-failed'}`}
          aria-label={`Release decision ${report.gates.decision}`}
        >
          <Check className="size-5" />
          <div>
            <span>Decision</span>
            <strong>{passed ? 'PASS' : 'FAIL'}</strong>
          </div>
        </div>
      </div>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.55fr)_minmax(280px,.75fr)]">
        <Card className="panel-card">
          <CardHeader className="border-b border-border/60 pb-4">
            <CardTitle className="flex items-center gap-2">
              <GitCompareArrows className="size-4 text-cyan-300" /> Baseline vs
              candidate
            </CardTitle>
            <CardAction>
              <span className="text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
                {baseline.case_pass_count}/{baseline.attempted_generations} vs{' '}
                {candidate.case_pass_count}/{candidate.attempted_generations}{' '}
                cases
              </span>
            </CardAction>
          </CardHeader>
          <CardContent className="pt-2">
            <div className="metric-grid metric-grid-header">
              <span>Metric</span>
              <span>Baseline</span>
              <span>Candidate</span>
              <span>Delta</span>
            </div>
            {metrics.map((metric) => (
              <div className="metric-grid" key={metric.label}>
                <span className="font-medium">{metric.label}</span>
                <span className="font-mono text-muted-foreground">
                  {metric.baseline}
                </span>
                <span className="font-mono text-foreground">
                  {metric.candidate}
                </span>
                <span
                  className={
                    metric.label === 'P95 latency' &&
                    metric.delta.startsWith('-')
                      ? 'text-emerald-300'
                      : 'text-muted-foreground'
                  }
                >
                  {metric.label === 'P95 latency' &&
                    metric.delta.startsWith('-') && (
                      <ArrowDownRight className="mr-1 inline size-3" />
                    )}
                  {metric.delta}
                </span>
              </div>
            ))}
            <div className="mt-5 grid gap-3 sm:grid-cols-2">
              {report.configurations.slice(0, 2).map((config) => (
                <div
                  className={`config-block ${config.name === 'candidate' ? 'config-block-candidate' : ''}`}
                  key={config.name}
                >
                  <span>
                    {config.name} · {config.model}
                  </span>
                  <p>{config.prompt}</p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
        <Card className="panel-card">
          <CardHeader className="border-b border-border/60 pb-4">
            <CardTitle className="flex items-center gap-2">
              <CircleDot
                className={
                  passed ? 'size-4 text-emerald-300' : 'size-4 text-rose-300'
                }
              />{' '}
              Gate evidence
            </CardTitle>
            <CardAction>
              <Badge
                className={
                  passed
                    ? 'bg-emerald-400 text-emerald-950'
                    : 'bg-rose-400 text-rose-950'
                }
              >
                {gates.filter((gate) => gate.passed).length} / {gates.length}
              </Badge>
            </CardAction>
          </CardHeader>
          <CardContent className="space-y-3 pt-2">
            {gates.map((gate) => (
              <div
                className="gate-row"
                key={`${gate.metric}-${gate.rule}`}
                title={gate.reason}
              >
                <span
                  className={
                    gate.passed ? 'gate-check' : 'gate-check gate-check-failed'
                  }
                >
                  {gate.passed ? (
                    <Check className="size-3" />
                  ) : (
                    <TriangleAlert className="size-3" />
                  )}
                </span>
                <span>
                  {gate.metric.replaceAll('_', ' ')} ·{' '}
                  {gate.rule.replaceAll('_', ' ')}
                </span>
                <span className={gate.passed ? '' : '!text-rose-300'}>
                  {gate.passed ? 'Pass' : 'Fail'}
                </span>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
      <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(320px,.85fr)]">
        <Card className="panel-card">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Activity className="size-4 text-amber-300" /> Failure explorer
            </CardTitle>
            <CardAction>
              <span className="text-xs text-muted-foreground">
                {failures.length} unique failed cases
              </span>
            </CardAction>
          </CardHeader>
          <CardContent className="grid gap-2 sm:grid-cols-2">
            {failures.length ? (
              failures.map((failure, index) => (
                <button
                  className={`failure-row text-left ${selectedFailure?.case_id === failure.case_id ? 'border-amber-300/30 bg-amber-300/5' : ''}`}
                  key={failure.case_id}
                  onClick={() => onFailure(failure)}
                >
                  <span className="failure-index">
                    {String(index + 1).padStart(2, '0')}
                  </span>
                  <span>
                    <strong>{failure.case_id}</strong>
                    <small>{failure.description}</small>
                  </span>
                  <ChevronRight className="ml-auto size-4 text-muted-foreground" />
                </button>
              ))
            ) : (
              <p className="col-span-2 rounded-xl border border-emerald-400/15 bg-emerald-400/5 p-5 text-sm text-emerald-200">
                No failed cases in this run.
              </p>
            )}
          </CardContent>
        </Card>
        {selectedFailure ? (
          <Card className="panel-card evidence-card">
            <CardHeader>
              <CardTitle className="font-mono text-sm">
                {selectedFailure.case_id}
              </CardTitle>
              <CardAction>
                <button
                  className="text-xs text-muted-foreground hover:text-foreground"
                  onClick={() => onFailure(null)}
                >
                  Close
                </button>
              </CardAction>
            </CardHeader>
            <CardContent className="space-y-3">
              <div>
                <p className="eyebrow mb-1">Expected</p>
                <pre className="evidence-json">
                  {json(selectedFailure.expected)}
                </pre>
              </div>
              <div>
                <p className="eyebrow mb-1">Candidate output</p>
                <pre className="evidence-json">
                  {json(selectedFailure.actual)}
                </pre>
              </div>
              <p className="text-[11px] leading-5 text-muted-foreground">
                {
                  selectedFailure.evaluations.find(
                    (evaluation) => evaluation.evaluator === 'field_accuracy',
                  )?.reason
                }
              </p>
            </CardContent>
          </Card>
        ) : (
          <Card className="panel-card evidence-card">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Clock3 className="size-4 text-violet-300" /> Run provenance
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="provenance-row">
                <span>Provider</span>
                <strong>{report.configurations[0]?.provider}</strong>
              </div>
              <div className="provenance-row">
                <span>Tokens</span>
                <strong>
                  {(baseline.usage.total_tokens_total ?? 0) +
                    (candidate.usage.total_tokens_total ?? 0)}
                </strong>
              </div>
              <div className="provenance-row">
                <span>Transitions</span>
                <strong>
                  {report.regression.newly_failing.length} regressed
                </strong>
              </div>
              <div className="provenance-row">
                <span>Artifacts</span>
                <strong>
                  {Object.keys(detail.artifact_digests).length} / 6 verified
                </strong>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </>
  );
}
