import React from 'react';
import { ChevronRight, RotateCcw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { FailedCase, ReplayState, RunDetail } from './types';
import { StepFooter, StepHeading } from './Primitives';
import { CaseEvidence } from './CaseEvidence';
import {
  metricValue,
  milliseconds,
  numberFormat,
  percent,
  replayMessage,
  sentence,
} from './formatters';

export function InvestigateStep({
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
