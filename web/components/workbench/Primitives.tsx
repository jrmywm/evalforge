import React from 'react';
import { ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Configuration } from './types';
import { sentence } from './formatters';

export function StepHeading({
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

export function Fact({
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

export function StepFooter({
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

export function ConfigurationPanel({
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
