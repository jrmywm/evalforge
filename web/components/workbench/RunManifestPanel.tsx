import React from 'react';
import { RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { LaunchState } from './types';
import { trustedManifests } from './formatters';

export function RunManifestPanel({
  selectedManifest,
  launchState,
  launchError,
  onSelect,
  onLaunch,
}: {
  selectedManifest: string;
  launchState: LaunchState;
  launchError: string | null;
  onSelect: (manifest: string) => void;
  onLaunch: () => void;
}) {
  const running = launchState === 'running';
  return (
    <section className="manifest-launch" aria-busy={running}>
      <div className="section-heading">
        <div>
          <h2>Run a Trusted Evaluation</h2>
          <p>
            The local API executes the selected workspace manifest and opens its
            recorded evidence here.
          </p>
        </div>
        <span>Local only</span>
      </div>
      <fieldset disabled={running}>
        <legend className="sr-only">Choose an evaluation manifest</legend>
        <div className="manifest-options">
          {trustedManifests.map((manifest) => {
            const checked = selectedManifest === manifest.path;
            return (
              <label
                key={manifest.path}
                aria-label={`Run ${manifest.label}`}
                className={`manifest-option ${checked ? 'manifest-option-active' : ''}`}
              >
                <input
                  type="radio"
                  name="manifest"
                  value={manifest.path}
                  checked={checked}
                  onChange={() => onSelect(manifest.path)}
                />
                <span>
                  <strong>{manifest.label}</strong>
                  <small>{manifest.detail}</small>
                  <code>{manifest.path}</code>
                </span>
              </label>
            );
          })}
        </div>
      </fieldset>
      <div className="launch-status" aria-live="polite">
        <p>
          {running
            ? 'Running the selected manifest locally. The API executes synchronously; this may take a moment.'
            : launchState === 'success'
              ? 'Run complete. The release decision below is calculated from the new evidence.'
              : 'Only the listed workspace manifests can be started from this workbench.'}
        </p>
        <Button onClick={onLaunch} disabled={running} className="min-h-11">
          <RefreshCw
            aria-hidden="true"
            data-icon="inline-start"
            className={running ? 'animate-spin' : ''}
          />
          {running ? 'Running Evaluation' : 'Run Manifest'}
        </Button>
      </div>
      {launchError && (
        <p className="launch-error" role="alert">
          {launchError}
        </p>
      )}
    </section>
  );
}
