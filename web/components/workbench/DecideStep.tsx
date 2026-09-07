import React, { useState } from 'react';
import { Copy, FileCheck2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { FailedCase, ReplayState, RunDetail } from './types';
import { Fact, StepHeading } from './Primitives';
import { percent, replayMessage } from './formatters';

export function DecideStep({
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
