import React from 'react';
import { FailedCase, ReplayState, RunDetail, WorkflowStep } from './types';
import { configuration, steps } from './formatters';
import { DefineStep } from './DefineStep';
import { RunStep } from './RunStep';
import { InvestigateStep } from './InvestigateStep';
import { DecideStep } from './DecideStep';

export function ReleaseReview({
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
