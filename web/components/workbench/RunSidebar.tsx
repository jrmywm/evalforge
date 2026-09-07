import React from 'react';
import { RunSummary } from './types';
import { dateFormat } from './formatters';

export function RunSidebar({
  runs,
  selectedRun,
  onSelectRun,
}: {
  runs: RunSummary[];
  selectedRun: string | null;
  onSelectRun: (runId: string) => void;
}) {
  return (
    <aside className="border-b border-border bg-sidebar lg:min-h-[calc(100vh-65px)] lg:border-r lg:border-b-0">
      <div className="px-4 py-5 sm:px-6">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-xs font-semibold">Indexed Runs</h2>
          <span className="font-mono text-[11px] text-muted-foreground">
            {runs.length}
          </span>
        </div>
        <nav
          aria-label="Experiment runs"
          className="grid gap-1 sm:grid-cols-2 lg:grid-cols-1"
        >
          {runs.map((run) => (
            <button
              key={run.run_id}
              onClick={() => onSelectRun(run.run_id)}
              className={`run-item text-left ${selectedRun === run.run_id ? 'run-item-active' : ''}`}
              aria-current={selectedRun === run.run_id ? 'true' : undefined}
            >
              <span className="mb-1 flex items-center justify-between gap-2">
                <span
                  className={`status-text ${run.decision === 'passed' ? 'status-pass' : 'status-block'}`}
                >
                  {run.decision === 'passed' ? 'Pass' : 'Block'}
                </span>
                <span className="text-[10px] text-muted-foreground">
                  {dateFormat.format(new Date(run.indexed_at))}
                </span>
              </span>
              <span className="block truncate text-sm font-medium">
                {run.experiment}
              </span>
              <span
                translate="no"
                className="mt-1 block truncate font-mono text-[10px] text-muted-foreground"
              >
                {run.run_id}
              </span>
            </button>
          ))}
        </nav>
      </div>
    </aside>
  );
}
