# EvalForge Product Vision

## Summary

EvalForge is a local-first developer tool for testing changes to LLM application
configurations. It compares a candidate with a known baseline and makes an
evidence-backed release decision across quality, reliability, latency, security,
and cost.

Its initial wedge is structured extraction. The architecture should permit RAG
and agent evaluation later, but those use cases must not complicate the first
release.

## Problem

LLM application changes are difficult to review safely. A new prompt, model, or
inference setting may improve average accuracy while making a subset of cases
worse, increasing latency, breaking structured output, or raising cost.

Teams often test these changes informally and cannot answer:

- Which cases regressed?
- Is the change statistically or operationally meaningful?
- Does it violate an explicit release policy?
- Can the result be reproduced from stored inputs and outputs?
- Was additional model inference actually necessary?

## Target user

The primary initial user is an AI or backend engineer who maintains a structured
LLM workflow and wants a local or CI-friendly regression check before release.

The first release optimizes for a single developer operating from the command
line. Multi-user collaboration, hosted operation, and enterprise administration
are not initial requirements.

## Product promise

Given:

- a versioned dataset;
- a baseline model configuration;
- a candidate model configuration;
- one or more evaluators; and
- release thresholds;

EvalForge returns:

- normalized results for every test case and configuration;
- aggregate quality, latency, token, and cost metrics;
- candidate-versus-baseline changes;
- failed-case details; and
- an explicit pass or fail decision.

## Design principles

### Evidence before infrastructure

Every significant capability must produce a result that can be demonstrated,
tested, or measured. Infrastructure is added only when a demonstrated workflow
requires it.

### Deterministic evaluation first

Use programmatic evaluators for schema validity, exact values, numeric tolerance,
sets, tool calls, latency, and cost. Use LLM judges only for behavior that cannot
be measured adequately without semantic judgment.

### Reproducibility by construction

An experiment must capture immutable snapshots or identifiers for its dataset,
prompt, provider configuration, inference parameters, evaluator versions, output
schema, and source revision when available.

### Stored generations are first-class artifacts

Inference and evaluation are separate operations. Saved generations can be
reevaluated without invoking a model again. Fresh sampling, cache reuse, and
explicit replay must remain distinguishable in the result.

### Local-first, not hardware-blind

The core workflow must run without paid API credentials. Deterministic mock
providers are the universal development baseline. Local model support is added
through an OpenAI-compatible endpoint and may require appropriate user hardware.

### Honest metrics

Reports must distinguish model errors, invalid outputs, provider failures,
timeouts, evaluator failures, and infrastructure failures. Unmeasured claims and
invented percentages do not belong in portfolio material.

## Portfolio positioning

EvalForge should demonstrate the ability to turn nondeterministic AI behavior into
a controlled engineering process. The strongest portfolio artifact is not the
number of integrated tools; it is a reproducible case where EvalForge identifies
a consequential tradeoff or blocks a real regression.

## Success signal

A reviewer should be able to clone the repository, run one command without an API
key, inspect a failed release decision, identify the responsible test cases, and
understand how a real model provider could be substituted.
