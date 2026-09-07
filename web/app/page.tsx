'use client';

import { useCallback, useEffect, useState } from 'react';
import { RefreshCw, Scale } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  API,
  FailedCase,
  LaunchState,
  LoadState,
  ReleaseReview,
  ReplayState,
  RunDetail,
  RunManifestPanel,
  RunSidebar,
  RunSummary,
  StatePanel,
  steps,
  trustedManifests,
  WorkflowStep,
} from '@/components/workbench';

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
        <RunSidebar
          runs={runs}
          selectedRun={selectedRun}
          onSelectRun={selectRun}
        />

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
