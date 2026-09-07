import React from 'react';
import { Configuration, RunDetail, Summary } from './types';
import { StepFooter, StepHeading } from './Primitives';
import { dateFormat, milliseconds, numberFormat } from './formatters';

export function RunStep({
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
