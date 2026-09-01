"""Milestone 4 pure end-to-end aggregation, comparison, and gate orchestration."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from evalforge.aggregation import (
    ConfigurationSummary,
    aggregate_experiment,
)
from evalforge.artifacts import read_manifest_snapshot
from evalforge.config import ExperimentConfig, LoadedManifest
from evalforge.dataset import DatasetSnapshot
from evalforge.evaluators.base import EvaluationResult
from evalforge.gates import QualityGateResult, evaluate_quality_gates
from evalforge.models import GenerationRecord
from evalforge.regression import RegressionResult, compare_summaries


class ExperimentAnalysis(BaseModel):
    """Deterministic stored-data decision without report or CLI concerns."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    baseline: ConfigurationSummary
    candidate: ConfigurationSummary
    regression: RegressionResult
    gates: QualityGateResult


def analyze_experiment(
    manifest: LoadedManifest | ExperimentConfig | Path,
    dataset: DatasetSnapshot | Path,
    generations: Iterable[GenerationRecord] | Path,
    evaluations: Iterable[EvaluationResult] | Path,
) -> ExperimentAnalysis:
    """Aggregate stored artifacts, compare configurations, then apply gates."""
    baseline, candidate = aggregate_experiment(manifest, dataset, generations, evaluations)
    regression = compare_summaries(baseline, candidate)
    gates = evaluate_quality_gates(
        manifest if not isinstance(manifest, Path) else read_manifest_snapshot(manifest),
        regression,
    )
    return ExperimentAnalysis(
        baseline=baseline,
        candidate=candidate,
        regression=regression,
        gates=gates,
    )
