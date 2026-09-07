import React from 'react';
import { X } from 'lucide-react';
import { FailedCase } from './types';
import { json, sentence } from './formatters';

export function CaseEvidence({
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
