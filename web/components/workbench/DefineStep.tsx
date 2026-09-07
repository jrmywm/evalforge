import React from 'react';
import { Configuration, RunDetail } from './types';
import { ConfigurationPanel, Fact, StepFooter, StepHeading } from './Primitives';
import { metricValue, sentence } from './formatters';

export function DefineStep({
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
