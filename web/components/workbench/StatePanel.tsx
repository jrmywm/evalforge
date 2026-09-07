import React from 'react';
import { CircleAlert } from 'lucide-react';

export function StatePanel({
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
