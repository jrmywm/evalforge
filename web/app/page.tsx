'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  ChevronRight,
  CircleAlert,
  Copy,
  FileCheck2,
  RefreshCw,
  RotateCcw,
  Scale,
  X,
} from 'lucide-react';
import { Button } from '@/components/ui/button';

const API =
  process.env.NEXT_PUBLIC_EVALFORGE_API_URL ?? 'http://127.0.0.1:8765';

type WorkflowStep = 'define' | 'run' | 'investigate' | 'decide';
type LoadState = 'loading' | 'ready' | 'empty' | 'error';
type ReplayState =
  | 'idle'
  | 'working'
  | 'verified-pass'
  | 'verified-block'
  | 'error';
type LaunchState = 'idle' | 'running' | 'success' | 'error';
type RunSummary = {
  run_id: string;
  experiment: string;
  decision: 'passed' | 'failed';
  indexed_at: string;
  artifact_digests: Record<string, string>;
};
type Metric = {
  score: number;
  evaluator_error_count?: number;
  missing_count?: number;
};
type Summary = {
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
type GateRule = {
  metric: string;
  rule: string;
  observed: number | null;
  threshold: number;
  passed: boolean;
  reason: string;
};
type EvaluationEvidence = {
  evaluator: string;
  evaluator_version: string;
  status: string;
  reason: string;
  score: number | null;
  details: { mismatches?: unknown[]; schema_errors?: unknown[] };
  error: unknown;
};
type FailedCase = {
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
type Configuration = {
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
type RunDetail = RunSummary & {
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

const trustedManifests = [
  {
    path: 'examples/invoice/pass.yaml',
    label: 'Passing policy',
    detail: 'Deterministic invoice extraction with a passing release decision.',
  },
  {
    path: 'examples/invoice/regression.yaml',
    label: 'Regression demo',
    detail: 'A deliberate candidate regression that should block release.',
  },
  {
    path: 'examples/invoice/local-openai.yaml',
    label: 'Local OpenAI-compatible model',
    detail: 'Runs against your configured local model endpoint.',
  },
] as const;

const steps: { id: WorkflowStep; label: string; detail: string }[] = [
  { id: 'define', label: 'Define', detail: 'Review the change and policy' },
  { id: 'run', label: 'Run', detail: 'Confirm execution and provenance' },
  {
    id: 'investigate',
    label: 'Investigate',
    detail: 'Trace failures to evidence',
  },
  { id: 'decide', label: 'Decide', detail: 'Approve or block the release' },
];
const percentFormat = new Intl.NumberFormat('en-SG', {
  style: 'percent',
  maximumFractionDigits: 1,
});
const numberFormat = new Intl.NumberFormat('en-SG', {
  maximumFractionDigits: 1,
});
const dateFormat = new Intl.DateTimeFormat('en-SG', {
  dateStyle: 'medium',
  timeStyle: 'short',
});

function percent(value: number) {
  return percentFormat.format(value);
}
function milliseconds(value: number | null) {
  return value === null ? 'Unavailable' : `${numberFormat.format(value)} ms`;
}
function metricValue(metric: string, value: number | null) {
  if (value === null) return 'Unavailable';
  return metric.includes('latency')
    ? `${numberFormat.format(value)} ms`
    : percent(value);
}
function sentence(value: string) {
  return value.replaceAll('_', ' ');
}
function json(value: unknown) {
  return JSON.stringify(value, null, 2);
}
function configuration(
  values: Configuration[],
  name: 'baseline' | 'candidate',
) {
  return values.find((value) => value.name === name);
}

export default function Home() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [selectedRun, setSelectedRun] = useState<string | null>(null);
  const [selectedFailure, setSelectedFailure] = useState<FailedCase | null>(
    null,
  );
  const [step, setStep] = useState<WorkflowStep>('decide');
  const [state, setState] = useState<LoadState>('loading');
  const [replayState, setReplayState] = useState<ReplayState>('idle');
  const [selectedManifest, setSelectedManifest] = useState<string>(
    trustedManifests[0].path,
  );
  const [launchState, setLaunchState] = useState<LaunchState>('idle');
  const [launchError, setLaunchError] = useState<string | null>(null);

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
      const params = new URLSearchParams(window.location.search);
      const requestedRun = params.get('run');
      const nextId =
        values.find((run) => run.run_id === requestedRun)?.run_id ??
        values[0].run_id;
      const requestedStep = params.get('step');
      if (steps.some((item) => item.id === requestedStep)) {
        setStep(requestedStep as WorkflowStep);
      }
      const detailResponse = await fetch(
        `${API}/api/runs/${encodeURIComponent(nextId)}`,
        { cache: 'no-store' },
      );
      if (!detailResponse.ok) throw new Error('run unavailable');
      const nextDetail = (await detailResponse.json()) as RunDetail;
      const requestedCase = params.get('case');
      const requestedConfiguration = params.get('configuration');
      setSelectedRun(nextId);
      setDetail(nextDetail);
      setSelectedFailure(
        nextDetail.report.failed_cases.find(
          (failure) =>
            failure.case_id === requestedCase &&
            (!requestedConfiguration ||
              failure.configuration === requestedConfiguration),
        ) ?? null,
      );
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
        setState('ready');
      })
      .catch(() => setState('error'));
  }, [selectedRun, detail?.run_id]);

  useEffect(() => {
    function restoreLocation() {
      const params = new URLSearchParams(window.location.search);
      const nextStep = params.get('step');
      if (steps.some((item) => item.id === nextStep)) {
        setStep(nextStep as WorkflowStep);
      }
      const nextRun = params.get('run');
      if (nextRun && runs.some((run) => run.run_id === nextRun)) {
        setSelectedRun(nextRun);
      }
      const nextCase = params.get('case');
      const nextConfiguration = params.get('configuration');
      if (nextCase && detail?.run_id === nextRun) {
        setSelectedFailure(
          detail.report.failed_cases.find(
            (failure) =>
              failure.case_id === nextCase &&
              (!nextConfiguration ||
                failure.configuration === nextConfiguration),
          ) ?? null,
        );
      } else {
        setSelectedFailure(null);
      }
    }
    window.addEventListener('popstate', restoreLocation);
    return () => window.removeEventListener('popstate', restoreLocation);
  }, [runs, detail]);

  function updateLocation(nextStep: WorkflowStep, runId = selectedRun) {
    const params = new URLSearchParams(window.location.search);
    params.set('step', nextStep);
    if (runId) params.set('run', runId);
    if (nextStep !== 'investigate') {
      params.delete('case');
      params.delete('configuration');
    }
    window.history.replaceState(null, '', `?${params.toString()}`);
  }
  function selectStep(nextStep: WorkflowStep) {
    setStep(nextStep);
    if (nextStep !== 'investigate') setSelectedFailure(null);
    updateLocation(nextStep);
  }
  function selectRun(runId: string) {
    setSelectedRun(runId);
    setStep('decide');
    setSelectedFailure(null);
    updateLocation('decide', runId);
  }
  function selectFailure(failure: FailedCase) {
    setSelectedFailure(failure);
    setStep('investigate');
    const params = new URLSearchParams(window.location.search);
    params.set('step', 'investigate');
    if (selectedRun) params.set('run', selectedRun);
    params.set('case', failure.case_id);
    params.set('configuration', failure.configuration);
    window.history.replaceState(null, '', `?${params.toString()}`);
  }
  function closeFailure() {
    setSelectedFailure(null);
    const params = new URLSearchParams(window.location.search);
    params.delete('case');
    params.delete('configuration');
    window.history.replaceState(null, '', `?${params.toString()}`);
  }
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
      setReplayState(
        value.gates.decision === 'passed' ? 'verified-pass' : 'verified-block',
      );
    } catch {
      setReplayState('error');
    }
  }
  async function launchRun() {
    setLaunchState('running');
    setLaunchError(null);
    try {
      const response = await fetch(`${API}/api/runs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ manifest: selectedManifest }),
      });
      const payload = (await response.json().catch(() => null)) as
        | RunDetail
        | { detail?: { message?: string } | string }
        | null;
      if (!response.ok || !payload || !('run_id' in payload)) {
        const detail =
          payload && 'detail' in payload ? payload.detail : undefined;
        throw new Error(
          typeof detail === 'object' && detail?.message
            ? detail.message
            : typeof detail === 'string'
              ? detail
              : 'The selected manifest could not complete. Check the local API and configuration.',
        );
      }
      const run = payload as RunDetail;
      setRuns((current) => [
        run,
        ...current.filter((item) => item.run_id !== run.run_id),
      ]);
      setDetail(run);
      setSelectedRun(run.run_id);
      setSelectedFailure(null);
      setReplayState('idle');
      setStep('decide');
      setState('ready');
      setLaunchState('success');
      updateLocation('decide', run.run_id);
    } catch (error) {
      setLaunchError(
        error instanceof Error
          ? error.message
          : 'The selected manifest could not complete.',
      );
      setLaunchState('error');
    }
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      <a href="#main-content" className="skip-link">
        Skip to Content
      </a>
      <header className="sticky top-0 z-20 border-b border-border bg-card">
        <div className="mx-auto flex min-h-16 max-w-[1500px] items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
          <div className="flex min-w-0 items-center gap-3">
            <div className="forge-mark">
              <Scale aria-hidden="true" className="size-4" />
            </div>
            <div className="min-w-0">
              <p className="font-heading text-sm font-semibold tracking-tight">
                EvalForge
              </p>
              <p className="truncate text-xs text-muted-foreground">
                AI release assurance
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span
              aria-live="polite"
              className="hidden items-center gap-2 text-xs text-muted-foreground sm:flex"
            >
              <span
                aria-hidden="true"
                className={`size-2 rounded-full ${state === 'error' || launchState === 'error' ? 'bg-red-700' : launchState === 'running' ? 'bg-amber-600' : 'bg-emerald-700'}`}
              />
              {launchState === 'running'
                ? 'Evaluation running locally'
                : launchState === 'error'
                  ? 'Last launch needs attention'
                  : state === 'error'
                    ? 'API unavailable'
                    : 'Local evidence connected'}
            </span>
            <Button
              variant="outline"
              className="min-h-11 border-border bg-card text-xs"
              onClick={() => void loadRuns()}
              disabled={state === 'loading'}
            >
              <RefreshCw
                aria-hidden="true"
                data-icon="inline-start"
                className={state === 'loading' ? 'animate-spin' : ''}
              />
              Refresh Runs
            </Button>
          </div>
        </div>
      </header>

      <div className="mx-auto grid max-w-[1500px] lg:grid-cols-[280px_minmax(0,1fr)]">
        <aside className="border-b border-border bg-sidebar lg:min-h-[calc(100vh-65px)] lg:border-r lg:border-b-0">
          <div className="px-4 py-5 sm:px-6">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-xs font-semibold">Indexed Runs</h2>
              <span className="font-mono text-[11px] text-muted-foreground">
                {runs.length}
              </span>
            </div>
            <nav
              aria-label="Experiment runs"
              className="grid gap-1 sm:grid-cols-2 lg:grid-cols-1"
            >
              {runs.map((run) => (
                <button
                  key={run.run_id}
                  onClick={() => selectRun(run.run_id)}
                  className={`run-item text-left ${selectedRun === run.run_id ? 'run-item-active' : ''}`}
                  aria-current={selectedRun === run.run_id ? 'true' : undefined}
                >
                  <span className="mb-1 flex items-center justify-between gap-2">
                    <span
                      className={`status-text ${run.decision === 'passed' ? 'status-pass' : 'status-block'}`}
                    >
                      {run.decision === 'passed' ? 'Pass' : 'Block'}
                    </span>
                    <span className="text-[10px] text-muted-foreground">
                      {dateFormat.format(new Date(run.indexed_at))}
                    </span>
                  </span>
                  <span className="block truncate text-sm font-medium">
                    {run.experiment}
                  </span>
                  <span
                    translate="no"
                    className="mt-1 block truncate font-mono text-[10px] text-muted-foreground"
                  >
                    {run.run_id}
                  </span>
                </button>
              ))}
            </nav>
          </div>
        </aside>

        <main id="main-content" className="min-w-0 px-4 py-6 sm:px-6 lg:px-8">
          <RunManifestPanel
            selectedManifest={selectedManifest}
            launchState={launchState}
            launchError={launchError}
            onSelect={setSelectedManifest}
            onLaunch={() => void launchRun()}
          />
          {state === 'loading' && (
            <StatePanel
              title="Loading Experiment History…"
              detail="Reading the local evidence index."
            />
          )}
          {state === 'empty' && (
            <StatePanel
              title="No Indexed Runs"
              detail="Choose a trusted manifest above to create the first evidence-backed run."
            />
          )}
          {state === 'error' && (
            <StatePanel
              error
              title="Local API Unavailable"
              detail="Start evalforge serve --artifact-root artifacts, then refresh the runs."
            />
          )}
          {state === 'ready' && detail && (
            <ReleaseReview
              detail={detail}
              step={step}
              selectedFailure={selectedFailure}
              replayState={replayState}
              onStep={selectStep}
              onFailure={selectFailure}
              onCloseFailure={closeFailure}
              onReplay={() => void replay()}
            />
          )}
        </main>
      </div>
    </div>
  );
}

function RunManifestPanel({
  selectedManifest,
  launchState,
  launchError,
  onSelect,
  onLaunch,
}: {
  selectedManifest: string;
  launchState: LaunchState;
  launchError: string | null;
  onSelect: (manifest: string) => void;
  onLaunch: () => void;
}) {
  const running = launchState === 'running';
  return (
    <section className="manifest-launch" aria-busy={running}>
      <div className="section-heading">
        <div>
          <h2>Run a Trusted Evaluation</h2>
          <p>
            The local API executes the selected workspace manifest and opens its
            recorded evidence here.
          </p>
        </div>
        <span>Local only</span>
      </div>
      <fieldset disabled={running}>
        <legend className="sr-only">Choose an evaluation manifest</legend>
        <div className="manifest-options">
          {trustedManifests.map((manifest) => {
            const checked = selectedManifest === manifest.path;
            return (
              <label
                key={manifest.path}
                aria-label={`Run ${manifest.label}`}
                className={`manifest-option ${checked ? 'manifest-option-active' : ''}`}
              >
                <input
                  type="radio"
                  name="manifest"
                  value={manifest.path}
                  checked={checked}
                  onChange={() => onSelect(manifest.path)}
                />
                <span>
                  <strong>{manifest.label}</strong>
                  <small>{manifest.detail}</small>
                  <code>{manifest.path}</code>
                </span>
              </label>
            );
          })}
        </div>
      </fieldset>
      <div className="launch-status" aria-live="polite">
        <p>
          {running
            ? 'Running the selected manifest locally. The API executes synchronously; this may take a moment.'
            : launchState === 'success'
              ? 'Run complete. The release decision below is calculated from the new evidence.'
              : 'Only the listed workspace manifests can be started from this workbench.'}
        </p>
        <Button onClick={onLaunch} disabled={running} className="min-h-11">
          <RefreshCw
            aria-hidden="true"
            data-icon="inline-start"
            className={running ? 'animate-spin' : ''}
          />
          {running ? 'Running Evaluation' : 'Run Manifest'}
        </Button>
      </div>
      {launchError && (
        <p className="launch-error" role="alert">
          {launchError}
        </p>
      )}
    </section>
  );
}

function StatePanel({
  title,
  detail,
  error = false,
}: {
  title: string;
  detail: string;
  error?: boolean;
}) {
  return (
    <section className="state-panel" aria-live="polite">
      <CircleAlert
        aria-hidden="true"
        className={error ? 'text-red-700' : 'text-muted-foreground'}
      />
      <div>
        <h1 className="text-lg font-semibold">{title}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{detail}</p>
      </div>
    </section>
  );
}

function ReleaseReview({
  detail,
  step,
  selectedFailure,
  replayState,
  onStep,
  onFailure,
  onCloseFailure,
  onReplay,
}: {
  detail: RunDetail;
  step: WorkflowStep;
  selectedFailure: FailedCase | null;
  replayState: ReplayState;
  onStep: (step: WorkflowStep) => void;
  onFailure: (failure: FailedCase) => void;
  onCloseFailure: () => void;
  onReplay: () => void;
}) {
  const report = detail.report;
  const baselineConfig = configuration(report.configurations, 'baseline');
  const candidateConfig = configuration(report.configurations, 'candidate');
  const failures = report.failed_cases;
  return (
    <>
      <header className="review-header">
        <div className="min-w-0">
          <p className="context-line">
            <span>{report.experiment}</span>
            <span translate="no">{report.run_id}</span>
          </p>
          <h1 className="text-balance text-2xl font-semibold tracking-tight sm:text-3xl">
            Release Review
          </h1>
          <p className="mt-2 max-w-[65ch] text-pretty text-sm leading-6 text-muted-foreground">
            Compare the current production configuration with the proposed
            candidate, trace every policy result to evidence, and make a
            defensible release decision.
          </p>
        </div>
        <output
          aria-live="polite"
          aria-atomic="true"
          className={`decision-mark ${report.gates.decision === 'passed' ? 'decision-pass' : 'decision-block'}`}
          aria-label={`Release decision: ${report.gates.decision === 'passed' ? 'pass' : 'block'}`}
        >
          <span>Decision</span>
          <strong>
            {report.gates.decision === 'passed' ? 'PASS' : 'BLOCK'}
          </strong>
        </output>
      </header>
      <nav aria-label="Release review workflow" className="workflow-rail">
        {steps.map((item, index) => (
          <button
            key={item.id}
            onClick={() => onStep(item.id)}
            className={`workflow-tab ${step === item.id ? 'workflow-tab-active' : ''}`}
            aria-current={step === item.id ? 'step' : undefined}
          >
            <span className="workflow-number">{index + 1}</span>
            <span className="min-w-0 text-left">
              <strong>{item.label}</strong>
              <small>{item.detail}</small>
            </span>
          </button>
        ))}
      </nav>
      {step === 'define' && (
        <DefineStep
          detail={detail}
          baseline={baselineConfig}
          candidate={candidateConfig}
          onNext={() => onStep('run')}
        />
      )}
      {step === 'run' && (
        <RunStep
          detail={detail}
          baseline={baselineConfig}
          candidate={candidateConfig}
          onNext={() => onStep('investigate')}
        />
      )}
      {step === 'investigate' && (
        <InvestigateStep
          detail={detail}
          failures={failures}
          selectedFailure={selectedFailure}
          replayState={replayState}
          onFailure={onFailure}
          onCloseFailure={onCloseFailure}
          onReplay={onReplay}
          onNext={() => onStep('decide')}
        />
      )}
      {step === 'decide' && (
        <DecideStep
          detail={detail}
          failures={failures}
          replayState={replayState}
          onInvestigate={() => onStep('investigate')}
          onReplay={onReplay}
        />
      )}
    </>
  );
}

function StepHeading({
  kicker,
  title,
  detail,
}: {
  kicker: string;
  title: string;
  detail: string;
}) {
  return (
    <div className="step-heading">
      <p>{kicker}</p>
      <h2>{title}</h2>
      <span>{detail}</span>
    </div>
  );
}

function DefineStep({
  detail,
  baseline,
  candidate,
  onNext,
}: {
  detail: RunDetail;
  baseline?: Configuration;
  candidate?: Configuration;
  onNext: () => void;
}) {
  const decisionRules = detail.report.gates.rules;
  return (
    <section id="define" className="workflow-panel">
      <StepHeading
        kicker="Step 1 of 4"
        title="Define the Release Contract"
        detail="Confirm the evidence set, configurations, and policy that decide the release."
      />
      <dl className="definition-strip">
        <Fact label="Dataset Version" value={detail.dataset_version} />
        <Fact
          label="Cases"
          value={String(detail.report.candidate_summary.attempted_generations)}
        />
        <Fact
          label="Manifest Digest"
          value={detail.manifest_digest.slice(0, 12)}
          mono
        />
        <Fact
          label="Dataset Digest"
          value={detail.dataset_digest.slice(0, 12)}
          mono
        />
      </dl>
      <div className="config-comparison">
        <ConfigurationPanel label="Current Baseline" value={baseline} />
        <ConfigurationPanel
          label="Proposed Candidate"
          value={candidate}
          candidate
        />
      </div>
      <section className="evidence-section">
        <div className="section-heading">
          <div>
            <h3>Decision Contract</h3>
            <p>
              Integrity checks and configured policy rules determine the
              decision.
            </p>
          </div>
          <span>{decisionRules.length} rules</span>
        </div>
        <section className="table-scroll" aria-label="Decision contract table">
          <table className="evidence-table">
            <thead>
              <tr>
                <th>Metric</th>
                <th>Rule</th>
                <th className="number-cell">Threshold</th>
                <th>Rationale</th>
              </tr>
            </thead>
            <tbody>
              {decisionRules.map((gate, index) => (
                <tr key={`${gate.metric}-${gate.rule}-${index}`}>
                  <td>{sentence(gate.metric)}</td>
                  <td>{sentence(gate.rule)}</td>
                  <td className="number-cell">
                    {metricValue(gate.metric, gate.threshold)}
                  </td>
                  <td>{gate.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </section>
      <StepFooter
        note="Definition reconstructed from the immutable manifest snapshot."
        label="Review Execution"
        onClick={onNext}
      />
    </section>
  );
}

function ConfigurationPanel({
  label,
  value,
  candidate = false,
}: {
  label: string;
  value?: Configuration;
  candidate?: boolean;
}) {
  if (!value) return null;
  return (
    <article
      className={candidate ? 'config-panel config-candidate' : 'config-panel'}
    >
      <div className="config-title">
        <p>{label}</p>
        <span>{value.provider}</span>
      </div>
      <h3 translate="no">{value.model}</h3>
      <p className="prompt-copy">{value.prompt}</p>
      <dl className="inline-facts">
        {Object.entries(value.inference_parameters).map(([key, item]) => (
          <div key={key}>
            <dt>{sentence(key)}</dt>
            <dd>{String(item)}</dd>
          </div>
        ))}
      </dl>
    </article>
  );
}

function RunStep({
  detail,
  baseline,
  candidate,
  onNext,
}: {
  detail: RunDetail;
  baseline?: Configuration;
  candidate?: Configuration;
  onNext: () => void;
}) {
  const report = detail.report;
  return (
    <section id="run" className="workflow-panel">
      <StepHeading
        kicker="Step 2 of 4"
        title="Confirm the Execution Record"
        detail="Review what executed and which evidence was captured before interpreting the result."
      />
      <div className="run-status-line">
        <span className="status-text status-pass">Recorded Run / Complete</span>
        <p>
          {dateFormat.format(new Date(report.started_at))} to{' '}
          {dateFormat.format(new Date(report.ended_at))}
        </p>
        <strong>{milliseconds(report.duration_ms)}</strong>
      </div>
      <section className="table-scroll" aria-label="Execution comparison table">
        <table className="evidence-table">
          <thead>
            <tr>
              <th>Configuration</th>
              <th>Provider / Model</th>
              <th className="number-cell">Requests</th>
              <th className="number-cell">Provider Errors</th>
              <th className="number-cell">P95 Latency</th>
              <th className="number-cell">Tokens</th>
            </tr>
          </thead>
          <tbody>
            <ExecutionRow
              label="Current Baseline"
              config={baseline}
              summary={report.baseline_summary}
            />
            <ExecutionRow
              label="Proposed Candidate"
              config={candidate}
              summary={report.candidate_summary}
            />
          </tbody>
        </table>
      </section>
      <section className="evidence-section">
        <div className="section-heading">
          <div>
            <h3>Evidence Package</h3>
            <p>
              Replay uses these stored artifacts and never calls the provider.
            </p>
          </div>
          <span>{Object.keys(detail.artifact_digests).length} artifacts</span>
        </div>
        <ul className="digest-list">
          {Object.entries(detail.artifact_digests).map(([name, digest]) => (
            <li key={name}>
              <span>{name}</span>
              <code translate="no">{digest}</code>
            </li>
          ))}
        </ul>
      </section>
      <StepFooter
        note="The browser displays indexed evidence; it does not simulate execution progress."
        label="Investigate Results"
        onClick={onNext}
      />
    </section>
  );
}

function ExecutionRow({
  label,
  config,
  summary,
}: {
  label: string;
  config?: Configuration;
  summary: Summary;
}) {
  return (
    <tr>
      <td className="font-medium">{label}</td>
      <td>
        <span className="block">{config?.provider ?? 'Unavailable'}</span>
        <small translate="no">{config?.model ?? 'Unavailable'}</small>
      </td>
      <td className="number-cell">{summary.attempted_generations}</td>
      <td className="number-cell">{summary.provider_error_count}</td>
      <td className="number-cell">{milliseconds(summary.latency.p95_ms)}</td>
      <td className="number-cell">
        {summary.usage.total_tokens_total === null
          ? 'Unavailable'
          : numberFormat.format(summary.usage.total_tokens_total)}
      </td>
    </tr>
  );
}

function InvestigateStep({
  detail,
  failures,
  selectedFailure,
  replayState,
  onFailure,
  onCloseFailure,
  onReplay,
  onNext,
}: {
  detail: RunDetail;
  failures: FailedCase[];
  selectedFailure: FailedCase | null;
  replayState: ReplayState;
  onFailure: (failure: FailedCase) => void;
  onCloseFailure: () => void;
  onReplay: () => void;
  onNext: () => void;
}) {
  const report = detail.report;
  const baseline = report.baseline_summary;
  const candidate = report.candidate_summary;
  const metrics = [
    {
      label: 'Field Accuracy',
      baseline: baseline.evaluator_metrics.field_accuracy.score,
      candidate: candidate.evaluator_metrics.field_accuracy.score,
      unit: 'percent',
    },
    {
      label: 'Schema Validity',
      baseline: baseline.evaluator_metrics.schema_validity.score,
      candidate: candidate.evaluator_metrics.schema_validity.score,
      unit: 'percent',
    },
    {
      label: 'P95 Latency',
      baseline: baseline.latency.p95_ms,
      candidate: candidate.latency.p95_ms,
      unit: 'ms',
    },
  ];
  return (
    <section id="investigate" className="workflow-panel">
      <StepHeading
        kicker="Step 3 of 4"
        title="Trace the Result to Evidence"
        detail="Compare outcomes, inspect every gate, and open the cases responsible for risk."
      />
      <section className="table-scroll" aria-label="Metric comparison table">
        <table className="evidence-table">
          <thead>
            <tr>
              <th>Metric</th>
              <th className="number-cell">Current Baseline</th>
              <th className="number-cell">Proposed Candidate</th>
              <th className="number-cell">Delta</th>
            </tr>
          </thead>
          <tbody>
            {metrics.map((metric) => {
              const delta =
                metric.baseline === null || metric.candidate === null
                  ? null
                  : metric.candidate - metric.baseline;
              return (
                <tr key={metric.label}>
                  <td className="font-medium">{metric.label}</td>
                  <td className="number-cell">
                    {metric.unit === 'ms'
                      ? milliseconds(metric.baseline)
                      : percent(metric.baseline ?? 0)}
                  </td>
                  <td className="number-cell">
                    {metric.unit === 'ms'
                      ? milliseconds(metric.candidate)
                      : percent(metric.candidate ?? 0)}
                  </td>
                  <td className="number-cell">
                    {delta === null
                      ? 'Unavailable'
                      : metric.unit === 'ms'
                        ? `${delta > 0 ? '+' : ''}${numberFormat.format(delta)} ms`
                        : `${delta > 0 ? '+' : ''}${percent(delta)}`}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>
      <section className="evidence-section">
        <div className="section-heading">
          <div>
            <h3>Gate Evidence</h3>
            <p>Integrity and configured policy rules are both shown.</p>
          </div>
          <span>
            {report.gates.rules.filter((gate) => gate.passed).length}/
            {report.gates.rules.length} passed
          </span>
        </div>
        <section className="table-scroll" aria-label="Gate evidence table">
          <table className="evidence-table compact-table">
            <thead>
              <tr>
                <th>Result</th>
                <th>Metric / Rule</th>
                <th className="number-cell">Observed</th>
                <th className="number-cell">Threshold</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {report.gates.rules.map((gate, index) => (
                <tr key={`${gate.metric}-${gate.rule}-${index}`}>
                  <td>
                    <span
                      className={`status-text ${gate.passed ? 'status-pass' : 'status-block'}`}
                    >
                      {gate.passed ? 'Pass' : 'Fail'}
                    </span>
                  </td>
                  <td>
                    {sentence(gate.metric)} / {sentence(gate.rule)}
                  </td>
                  <td className="number-cell">
                    {metricValue(gate.metric, gate.observed)}
                  </td>
                  <td className="number-cell">
                    {metricValue(gate.metric, gate.threshold)}
                  </td>
                  <td>{gate.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </section>
      <section className="evidence-section">
        <div className="section-heading">
          <div>
            <h3>Failed Cases</h3>
            <p>Select a case to inspect the expected and actual output.</p>
          </div>
          <span>{failures.length} failed results</span>
        </div>
        {failures.length ? (
          <div className="failure-layout">
            <div className="failure-list">
              {failures.map((failure) => (
                <button
                  key={`${failure.configuration}:${failure.case_id}`}
                  onClick={() => onFailure(failure)}
                  className={`failure-row ${selectedFailure?.case_id === failure.case_id && selectedFailure.configuration === failure.configuration ? 'failure-row-active' : ''}`}
                  aria-pressed={
                    selectedFailure?.case_id === failure.case_id &&
                    selectedFailure.configuration === failure.configuration
                  }
                >
                  <span className="min-w-0">
                    <strong translate="no">{failure.case_id}</strong>
                    <small>
                      {sentence(failure.configuration)} configuration -{' '}
                      {failure.description}
                    </small>
                  </span>
                  <ChevronRight aria-hidden="true" className="size-4" />
                </button>
              ))}
            </div>
            <CaseEvidence
              failure={selectedFailure ?? failures[0]}
              onClose={selectedFailure ? onCloseFailure : undefined}
            />
          </div>
        ) : (
          <p className="empty-evidence">
            No failed cases are recorded for this run.
          </p>
        )}
      </section>
      <div className="replay-line" aria-live="polite">
        <div>
          <strong>Offline Evidence Replay</strong>
          <p>{replayMessage(replayState)}</p>
        </div>
        <Button
          variant="outline"
          onClick={onReplay}
          disabled={replayState === 'working'}
          className="min-h-11"
        >
          <RotateCcw
            aria-hidden="true"
            data-icon="inline-start"
            className={replayState === 'working' ? 'animate-spin' : ''}
          />
          Verify Stored Evidence
        </Button>
      </div>
      <StepFooter
        note={`${report.regression.newly_failing.length} newly failing and ${report.regression.newly_passing.length} newly passing cases.`}
        label="Review Decision"
        onClick={onNext}
      />
    </section>
  );
}

function CaseEvidence({
  failure,
  onClose,
}: {
  failure: FailedCase;
  onClose?: () => void;
}) {
  const fieldEvidence = failure.evaluations.find(
    (evaluation) => evaluation.evaluator === 'field_accuracy',
  );
  return (
    <article
      className="case-evidence"
      aria-label={`Evidence for ${failure.case_id}`}
    >
      <header>
        <div>
          <p>Case Evidence</p>
          <h4 translate="no">{failure.case_id}</h4>
          <span className="configuration-label">
            {sentence(failure.configuration)} configuration
          </span>
        </div>
        {onClose && (
          <button
            type="button"
            className="icon-button"
            onClick={onClose}
            aria-label="Close selected case"
          >
            <X aria-hidden="true" className="size-4" />
          </button>
        )}
      </header>
      <p className="case-description">{failure.description}</p>
      <div className="json-pair">
        <div>
          <p>Expected</p>
          <pre>{json(failure.expected)}</pre>
        </div>
        <div>
          <p>Recorded Output</p>
          <pre>{json(failure.actual)}</pre>
        </div>
      </div>
      <dl className="case-reason">
        <div>
          <dt>Evaluator</dt>
          <dd>{fieldEvidence?.evaluator ?? 'Unavailable'}</dd>
        </div>
        <div>
          <dt>Reason</dt>
          <dd>{fieldEvidence?.reason ?? 'No evaluator reason recorded.'}</dd>
        </div>
        <div>
          <dt>Field Mismatches</dt>
          <dd>
            {fieldEvidence?.details.mismatches?.length
              ? json(fieldEvidence.details.mismatches)
              : 'None recorded'}
          </dd>
        </div>
        <div>
          <dt>Provider Error</dt>
          <dd>
            {failure.provider_error === null
              ? 'None recorded'
              : json(failure.provider_error)}
          </dd>
        </div>
        <div>
          <dt>Raw Response</dt>
          <dd>
            {failure.raw_response === null
              ? 'None recorded'
              : json(failure.raw_response)}
          </dd>
        </div>
      </dl>
    </article>
  );
}

function DecideStep({
  detail,
  failures,
  replayState,
  onInvestigate,
  onReplay,
}: {
  detail: RunDetail;
  failures: FailedCase[];
  replayState: ReplayState;
  onInvestigate: () => void;
  onReplay: () => void;
}) {
  const report = detail.report;
  const passed = report.gates.decision === 'passed';
  const failedRules = report.gates.rules.filter((gate) => !gate.passed);
  const candidate = report.candidate_summary;
  const baseline = report.baseline_summary;
  const [copied, setCopied] = useState<'summary' | 'command' | null>(null);
  const command =
    'uv run evalforge run <path-to-manifest> --artifact-root artifacts --run-id <new-run-id>';
  const summary = passed
    ? `PASS: ${report.experiment} candidate is eligible for release under the configured policy. Field accuracy ${percent(candidate.evaluator_metrics.field_accuracy.score)}, schema validity ${percent(candidate.evaluator_metrics.schema_validity.score)}, ${report.regression.newly_failing.length} newly failing cases. Run ${report.run_id}.`
    : `BLOCK: ${report.experiment} candidate failed ${failedRules.length} decision rule${failedRules.length === 1 ? '' : 's'} with ${report.regression.newly_failing.length} newly failing case${report.regression.newly_failing.length === 1 ? '' : 's'}. Run ${report.run_id}.`;
  async function copy(value: string, kind: 'summary' | 'command') {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(kind);
      window.setTimeout(() => setCopied(null), 1800);
    } catch {
      setCopied(null);
    }
  }
  const reasons = failedRules.length
    ? failedRules.map((gate) => gate.reason)
    : [
        `All ${report.gates.rules.length} integrity and policy checks passed.`,
        `${report.regression.newly_failing.length} newly failing cases were recorded.`,
        `${candidate.case_fail_count} candidate cases contain case-level evaluation failures even though the final decision passed.`,
      ];
  return (
    <section id="decide" className="workflow-panel">
      <StepHeading
        kicker="Step 4 of 4"
        title="Make the Release Decision"
        detail="This decision comes from the stored gate result. The interface does not recompute or override it."
      />
      <section
        className={`decision-brief ${passed ? 'decision-brief-pass' : 'decision-brief-block'}`}
      >
        <p>{passed ? 'Eligible Under Policy' : 'Release Blocked'}</p>
        <h3>
          {passed
            ? 'Candidate passed every integrity and policy rule.'
            : `Candidate failed ${failedRules.length} decision rule${failedRules.length === 1 ? '' : 's'}.`}
        </h3>
        <p className="decision-copy">
          {passed
            ? `Recommendation: eligible for release under this evaluation policy. Review the ${candidate.case_fail_count} case-level evaluation failures before deployment; passing the decision rules does not mean every case succeeded.`
            : 'Recommendation: do not release this candidate. Resolve the blocking evidence, update the configuration, and rerun the same policy.'}
        </p>
      </section>
      <div className="decision-grid">
        <section className="decision-reasons">
          <div className="section-heading">
            <div>
              <h3>{passed ? 'Why It Passed' : 'Why It Is Blocked'}</h3>
              <p>Ordered from canonical gate and regression evidence.</p>
            </div>
          </div>
          <ol>
            {reasons.map((reason, index) => (
              <li key={`${reason}-${index}`}>
                <span>{index + 1}</span>
                <p>{reason}</p>
              </li>
            ))}
          </ol>
        </section>
        <dl className="decision-facts">
          <Fact
            label="Field Accuracy"
            value={`${percent(baseline.evaluator_metrics.field_accuracy.score)} to ${percent(candidate.evaluator_metrics.field_accuracy.score)}`}
          />
          <Fact
            label="Schema Validity"
            value={`${percent(baseline.evaluator_metrics.schema_validity.score)} to ${percent(candidate.evaluator_metrics.schema_validity.score)}`}
          />
          <Fact
            label="Displayed Failed Cases"
            value={String(failures.length)}
          />
          <Fact
            label="New Regressions"
            value={String(report.regression.newly_failing.length)}
          />
          <Fact
            label="Evidence Artifacts"
            value={`${Object.keys(detail.artifact_digests).length} verified`}
          />
          <Fact label="Run ID" value={report.run_id} mono />
        </dl>
      </div>
      <section className="release-actions" aria-live="polite">
        <ReleaseAction
          title="Inspect Blocking Evidence"
          detail="Open the comparison, gate results, and affected cases."
        >
          <Button
            variant="outline"
            className="min-h-11"
            onClick={onInvestigate}
          >
            Investigate Evidence
          </Button>
        </ReleaseAction>
        <ReleaseAction
          title="Verify the Decision Offline"
          detail={replayMessage(replayState)}
        >
          <Button
            variant="outline"
            className="min-h-11"
            onClick={onReplay}
            disabled={replayState === 'working'}
          >
            <FileCheck2 aria-hidden="true" data-icon="inline-start" />
            Verify Evidence
          </Button>
        </ReleaseAction>
        <ReleaseAction
          title="Share the Review Summary"
          detail="Copy an evidence-backed result for a pull request or handoff."
        >
          <Button
            variant="outline"
            className="min-h-11"
            onClick={() => void copy(summary, 'summary')}
          >
            <Copy aria-hidden="true" data-icon="inline-start" />
            {copied === 'summary' ? 'Summary Copied' : 'Copy Review Summary'}
          </Button>
        </ReleaseAction>
        <div className="release-action">
          <div className="min-w-0">
            <h3>Edit the Candidate and Rerun</h3>
            <p>
              The current API is evidence-only. Update the manifest and run
              locally.
            </p>
            <code className="command-line" translate="no">
              {command}
            </code>
          </div>
          <Button
            variant="outline"
            className="min-h-11 shrink-0"
            onClick={() => void copy(command, 'command')}
          >
            <Copy aria-hidden="true" data-icon="inline-start" />
            {copied === 'command' ? 'Command Copied' : 'Copy Rerun Command'}
          </Button>
        </div>
      </section>
    </section>
  );
}

function ReleaseAction({
  title,
  detail,
  children,
}: {
  title: string;
  detail: string;
  children: React.ReactNode;
}) {
  return (
    <div className="release-action">
      <div>
        <h3>{title}</h3>
        <p>{detail}</p>
      </div>
      {children}
    </div>
  );
}

function Fact({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div>
      <dt>{label}</dt>
      <dd
        translate={mono ? 'no' : undefined}
        className={mono ? 'font-mono' : ''}
      >
        {value}
      </dd>
    </div>
  );
}

function StepFooter({
  note,
  label,
  onClick,
}: {
  note: string;
  label: string;
  onClick: () => void;
}) {
  return (
    <footer className="step-footer">
      <p>{note}</p>
      <Button onClick={onClick} className="min-h-11">
        {label}
        <ChevronRight aria-hidden="true" data-icon="inline-end" />
      </Button>
    </footer>
  );
}

function replayMessage(state: ReplayState) {
  if (state === 'working') return 'Verifying immutable snapshots…';
  if (state === 'verified-pass')
    return 'Offline replay reproduced a PASS decision; no provider call was made.';
  if (state === 'verified-block')
    return 'Offline replay reproduced a BLOCK decision; no provider call was made.';
  if (state === 'error')
    return 'Evidence verification could not complete. Check the API and artifact integrity.';
  return 'Not yet verified in this session. Replay stored snapshots without calling the model provider.';
}
