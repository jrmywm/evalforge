import { Configuration, ReplayState, WorkflowStep } from './types';

export const API =
  process.env.NEXT_PUBLIC_EVALFORGE_API_URL ?? 'http://127.0.0.1:8765';

export const trustedManifests = [
  {
    path: 'examples/invoice/portfolio.yaml',
    label: 'Aggregate improvement, critical regressions',
    detail: 'Higher average accuracy with two new failures that block release.',
  },
  {
    path: 'examples/invoice/portfolio-fixed.yaml',
    label: 'Corrected candidate',
    detail:
      'The follow-up candidate resolves the critical regressions and passes.',
  },
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

export const steps: { id: WorkflowStep; label: string; detail: string }[] = [
  { id: 'define', label: 'Define', detail: 'Review the change and policy' },
  { id: 'run', label: 'Run', detail: 'Confirm execution and provenance' },
  {
    id: 'investigate',
    label: 'Investigate',
    detail: 'Trace failures to evidence',
  },
  { id: 'decide', label: 'Decide', detail: 'Approve or block the release' },
];

export const percentFormat = new Intl.NumberFormat('en-SG', {
  style: 'percent',
  maximumFractionDigits: 1,
});

export const numberFormat = new Intl.NumberFormat('en-SG', {
  maximumFractionDigits: 1,
});

export const dateFormat = new Intl.DateTimeFormat('en-SG', {
  dateStyle: 'medium',
  timeStyle: 'short',
});

export function percent(value: number) {
  return percentFormat.format(value);
}

export function milliseconds(value: number | null) {
  return value === null ? 'Unavailable' : `${numberFormat.format(value)} ms`;
}

export function metricValue(metric: string, value: number | null) {
  if (value === null) return 'Unavailable';
  if (metric.includes('latency')) return `${numberFormat.format(value)} ms`;
  if (metric.endsWith('_count')) return numberFormat.format(value);
  return percent(value);
}

export function sentence(value: string) {
  return value.replaceAll('_', ' ');
}

export function json(value: unknown) {
  return JSON.stringify(value, null, 2);
}

export function configuration(
  values: Configuration[],
  name: 'baseline' | 'candidate',
) {
  return values.find((value) => value.name === name);
}

export function replayMessage(state: ReplayState) {
  if (state === 'working') return 'Verifying immutable snapshots…';
  if (state === 'verified-pass')
    return 'Offline replay reproduced a PASS decision; no provider call was made.';
  if (state === 'verified-block')
    return 'Offline replay reproduced a BLOCK decision; no provider call was made.';
  if (state === 'error')
    return 'Evidence verification could not complete. Check the API and artifact integrity.';
  return 'Not yet verified in this session. Replay stored snapshots without calling the model provider.';
}
