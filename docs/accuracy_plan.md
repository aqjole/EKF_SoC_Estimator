# Draft plan: improve the ECM and existing EKF

Status: revised proposal, 2026-11-07, following review. Keep this as an untracked
working draft; existing decisions remain in force. The intended stage workflow
is to add S10 at the next spec revision (3.7) and decisions 1.44 onward before
execution. S10 implementation and result files are now present in the workspace;
this draft revision does not establish that any decision preceded those results.
Reconcile the actual chronology when formalizing the stage, without backdating.
Do not maintain a second authoritative plan. The existing v1.5 tag belongs to
S9; choose a new release tag when the S10 scope is fixed.

## Objective and scope

Improve cold-temperature SoC accuracy and aggressive-cycle robustness while
retaining an explainable equivalent-circuit model, the existing EKF, and a small
C99 implementation. Develop the identification code in this repository using
NumPy, SciPy and existing utilities. PyBOP may inform the design, but is not a
dependency or a replacement for our implementation.

Included: offline parameter identification, evidence-supported ECM changes,
measurement of omitted Jacobian terms, conditional EKF variants, offline noise
calibration and C deployment.
Excluded: SPKF/UKF, online parameter or sensor-bias estimation, neural networks,
electrochemical PDE models and a general-purpose fitting framework.

## Starting point

- The adopted Python model is 2RC-I. The C library still implements v1.0 2RC.
- S6 rejected two 3RC fits. S8 rejected three current-dependent R1 variants.
- S9 improved average results with 3RC-D but failed the worst-run guard.
  Its outcome remains closed; this work must not silently revise that fit.
- Current EKF Jacobians omit the SoC dependence of RC parameters and R0.
  The stored OCV slope also differs from the derivative of the lookup itself.
  Retain that central-difference slope table: exact interpolation derivatives
  have jumps at cell boundaries and are not automatically better for estimation.
- Existing noise settings were fitted at one temperature. Changing them is a
  separate experiment, not an explanation for accepting a failed model fit.

Evidence: README.md; decisions.md 1.12, 1.15, 1.26, 1.28, 1.40–1.43;
model.md equations 4–8; results/model_compare_3rcd.md.

## Phase 0 — freeze the comparison protocol

Reuse decisions 1.5, 1.15 and 1.40 and the existing run selection/split functions.
Generate run membership and provenance in the report from those functions;
do not create a separately maintained manifest. If provenance is included,
record deterministic content hashes of the input parameter/configuration files.
Rely on git history for code provenance; do not embed the current HEAD revision,
timestamps or other changing metadata in reproducible generated reports.

Freeze 2RC-I as the adoption comparator for all S10 candidates, regardless of
the model used as their fitting base. In particular, guard 5 compares the
maximum experiment-1 RMSE over all 23 standard runs with 2RC-I's maximum
(approximately 6.2547 pp, US06 at -10 degC); it is not a check on that run alone.
Use the stored full-precision evidence under the existing rounding rule, not
this rounded number. Do not change comparator after observing candidate results.
Report v1.0 2RC and the rejected 3RC-D alongside, without changing their verdicts.
The v1.0 US06 result is context, not the predicted error of a refitted candidate.

Keep the current SoC reference, Q_ref, exclusions, current sign and integration
rules. Do not renormalize cold runs to end at zero SoC. Any independent discovery
of a reference/data defect requires a separate documented correction.

For comparability, propose retaining S9's 40 Mix / 23 standard run reporting.
The standard runs are a previously inspected regression suite, not an untouched
test set. For the first candidate retain S9's fit settings and leave-one-Mix-run-out
diagnostic, with the shared-segment limitation disclosed. Do not introduce a new
split to select this candidate. New cells/profiles are needed for independent
final validation, but are not required to run this investigation.

Deliverable: a new decision entry specifying the one changed modelling choice,
fixed comparator, reused fit protocol, output paths and adoption rules.

## Phase 1 — reproduce the residual diagnosis

Build one diagnostic script reusing the loader, model and experiment runner.
Separate open-loop voltage residuals at reference SoC from EKF innovations and
SoC errors. Keep full-run and evaluation-window summaries distinct.

Inspect residuals by temperature, SoC, current magnitude/sign, time after current
steps, rest duration and accumulated history. Report sample/run support in each
bin. Examine mean bias, transient shape, slow drift and innovation correlation.
Include US06 and low-SoC tails, but label their use as exploratory analysis.

Reproduce the relevant earlier findings instead of treating scratch diagnostics
as established explanations. Check current/voltage timing conventions before
interpreting a transient residual as a missing physical state.

The leading question is whether the current-dependent R1 partly compensates
for dynamics that the drive-fitted middle branch also represents. Decision 1.28
confounds pulse magnitude with position/history, and 1.34 identifies regen R1
as an important contributor to the US06 regression. These support testing an
interaction; they do not establish that current dependence is physically absent.

In the same diagnostic script, measure -I*dR0/dSoC relative to the stored OCV
slope, and measure omitted RC-process derivatives and their effect on predicted
covariance. Existing saved traces omit the branch states and full covariance.
Rerun the unchanged incumbent EKF for experiment 1 over the 63 runs, capturing
the state and covariance at the precise pre-predict and pre-update points needed
by each calculation. Accumulate diagnostic summaries in that pass; retain any
additional diagnostic arrays separately from historical trace files. Compare
its SoC and predicted voltage with the ordinary runner to verify observation
has not changed the filter. Other experiments require separately specified
reruns; one pass does not cover every initialization/offset case. Report absolute
values where OCV slope is near zero instead of unstable ratios. This measures
terms on the original trajectory, not the accuracy of a changed filter.

Deliverable: a compact report identifying the leading testable error mechanism,
its supporting plots, and what the available data cannot distinguish.
This report is not a gate for phase 2: the prescribed 3RC-D0 fit and evaluation
are the test of the R1/middle-branch interaction, and proceed under their own
decision entry. Do not alter their frozen protocol in response to residual bins.
Diagnosis gates the deferred phase 3 Jacobian work and phase 4 candidates only.

## Phase 2 — first candidate: drive-fitted 3RC with v1.0 R1

Hypothesis: the middle branch can supply the missing drive-cycle polarization
without retaining the current-dependent R1 that contributes to US06 regressions.
Working candidate name: 3RC-D0. This is a new experiment; S9 stays closed.

1. Use the v1.0 2RC tables as the base, including R1(T, SoC) for both current
   signs. Do not load the current-axis R1 table. OCV, dOCV/dSoC, R0, tau1 and
   tau2 remain unchanged.
2. Refit R3 and the R2 scale using exactly S9's model form and fitting protocol:
   tau3 = 45 s, the same nodes, bounds, support threshold, low-SoC taper,
   weighting, cost rows, BVLS solver and 40 Mix calibration runs. Reuse the
   existing fit helpers with an explicit base-model argument, and reuse the
   comparison helpers with a model list. Keep separate output paths and the
   historical S9 defaults; avoid copying a pipeline or overwriting S9.
3. Run one prescribed full calibration fit plus S9's prescribed diagnostic
   cross-validation fits. No search over branch time constants, grids, weights
   or regularization after seeing standard-cycle results.
4. Verify the linear prediction against full-rate simulation; report support,
   rank/conditioning and bound hits. Serialize and reload the candidate tables.
5. Apply the S1 voltage gate, then experiments 1–4 with frozen S2 noise and
   existing Jacobians. Compute all six adoption guards against 2RC-I.
6. Report 2RC, 2RC-I, 3RC-D and 3RC-D0 together. Also report one diagnostic
   substitution: v1.0 R1 with the original S9 R2/R3 coefficients, without
   refitting. Keep it outside the adoption decision. This distinguishes the
   immediate R1 substitution from the effect of refitting slow dynamics.

Deliverable: separate candidate tables, fit/evaluation reports and an explicit
verdict. Improvement would support the interaction hypothesis, not prove a
single physical cause for S8 and S9. Failure closes this specified candidate;
another attempt requires a new hypothesis and decision before it runs.

Expected tradeoff: removing current-dependent R1 also removes the correction
associated with S7's cold-temperature gains, including improvements on non-US06
cycles (1.31). The fitted middle branch and R2 rescaling must recover enough of
those gains to pass guard 2 against 2RC-I, while also passing the other guards.
US06 may recover while other cold cycles deteriorate enough to reject 3RC-D0.
S9's average improvements motivate the test but do not guarantee recovery with
the changed base. Report this failure mode alongside the interaction hypothesis.

Development complexity: low to medium because the fitter and simulator exist.
Hardware complexity: low to medium; four states instead of three and a larger
covariance, but this candidate has no current-axis R1 table. Measure the net
footprint rather than assuming it is smaller or faster.

## Phase 3 — separate EKF improvements

Use the accepted model from phase 2, or retain 2RC-I if phase 2 fails.

Retain the stored central-difference OCV slope. Its smoothing is a reasonable
engineering choice; the repository documents common Python/C lookup behaviour,
but does not establish that either slope choice has superior accuracy.

Only implement omitted Jacobian terms if phase 1 shows material contributions
to measurement sensitivity or covariance propagation. Record a quantitative
criterion before running a filter variant. Include the SoC derivatives of R_i
and tau_i and the -I*dR0/dSoC measurement term as separate ablations if warranted.
Specify behaviour at knots and clamped axes. Keep the nonlinear state propagation
separate from the covariance Jacobian; adding Jacobian terms must not change
the process equation itself.

Verify derivatives against finite differences away from knots, and explicitly
test knots, clamping and zero-dt behaviour. Evaluate with frozen noise first.
Mathematical consistency does not guarantee better estimation with noisy tables.
Use a named variant with separate traces/configuration/reports, leaving the
legacy path byte-identical. Its C port needs a new equation/operation-order
contract matching that variant, while the old contract remains valid.

Then, as a distinct experiment, compare shared noise settings with a small,
smooth temperature-dependent schedule fitted offline. Proposed tuning set: the
40 Mix runs only. Proposed objective: at each temperature average, over its Mix
runs, the mean of experiment-2 and experiment-4 SoC RMSE; then average the six
temperature scores equally. This extends the S2 objective without letting a
temperature with more runs dominate. Experiments 1 and 3 remain reported checks.
Fix schedule parameterization, search budget and tie rules in a separate decision
before tuning, giving global and scheduled variants comparable search budgets.
Keep process-noise dt scaling and measurement-noise units explicit. No per-run
settings or changes to the historical S2 configuration/results.

Deliverable: an ablation table separating model, Jacobian and noise effects.
Adopt only changes that pass the declared guards, including their combination.

Development complexity: medium. Hardware complexity: low to medium; derivative
lookups and non-diagonal covariance propagation add work without a new observer.

## Phase 4 — deferred calibration and model extensions

Proceed only if the simpler candidates leave a diagnosed, repeatable mechanism.
Choose one extension and write a fresh experiment decision before fitting:

- Continuous-state HPPC calibration if diagnostics identify slow-state bias.
  Decision 1.35's <=1.1% R1 change applies to starting one charge-pulse correction
  at the previous move; it is not a bound on all R2/tau2 refitting gains. However,
  S6–S9 give stronger support to a drive-fitted middle branch, which is why this
  is deferred. Moving tau2 into a middle timescale alone can sacrifice the slow
  relaxation mode; it does not supply both modes simultaneously.
- A single hysteresis state if direction/history-dependent residuals persist
  after accounting for polarization. The 610 s rests after charge pulses provide
  useful charge-side relaxation evidence alongside discharge-side rests. Check
  SoC alignment and remaining polarization; these are not automatically matched
  equilibrium OCV pairs. Do not use the ambiguous C/20 gap alone.
- A revision to the current dependence of an existing parameter if transient
  evidence supports it. S8's failed sign/low-current variants must inform the
  hypothesis; do not simply repeat them with different tuning.

Choose at most one follow-on experiment at a time. Do not add further branches
automatically or fit a free OCV offset to hide dynamic errors. If the available
measurements cannot identify a change, document the characterization required.

For any HPPC continuity fit, specify both the state-propagation rows and the
objective rows before fitting. Carry state through excluded cost intervals,
including charge and moves. Preserve actual timestamps; inspect logging steps
by segment (about 0.1 s in discharge windows, 10 s in long rests, with coarser
intervals elsewhere). Bound transition-time uncertainty from the actual adjacent
samples and counter/step evidence where available. Do not assume an edge is
misplaced by the maximum logging interval or infer unlogged transitions exactly.
Check sensitivity before fitting dynamics comparable to those time intervals.

Deliverable: one small candidate or a documented decision that data are
insufficient. Development complexity: medium to high; a hysteresis state adds
covariance and initialization work as well as the state update itself.

## Proposed adoption gates

Retain the S9 numerical guards on the same 23 standard runs against 2RC-I:

| Metric | Required outcome |
|---|---|
| Full-run US06 voltage RMSE at 25 degC | At most 30 mV |
| Experiment-1 mean SoC RMSE by temperature | Lower at >=4 of 6; increase <=0.10 pp at each |
| Experiment-1 individual-run regression | Increase <=0.50 pp |
| Experiment-1 standard-cycle mean regression | Increase <=0.25 pp |
| Worst experiment-1 run | No increase in the maximum RMSE |
| Experiment-4 mean by temperature | Increase <=0.10 pp |
| Experiments 2 and 3 | No reduction in reached counts at any temperature |

Use the existing near-threshold full-precision comparison convention. Report
cold-temperature results and US06 explicitly. Add peak absolute SoC error,
convergence time and capacity/sample-rate sensitivity as diagnostic metrics;
declare any new pass/fail thresholds before running candidates.

Repeated use of these gates is regression protection, not independent evidence
of generalization. Do not relax a threshold because a candidate nearly passes.

## Phase 5 — port the accepted estimator and close the stage

Port the accepted Python model to C. Add current-axis R1 support only if the
selected model uses it; 3RC-D0 instead requires the third branch and its tables.
Keep the v1.0 reproduction path.
Use caller-owned state, fixed storage, const tables and float32 by default.
Implement only adopted changes; avoid a general model-selection framework.

Run meaningful synthetic tests for state continuity, parameter recovery where
identifiable, derivative behaviour and any new state. Run the existing Python
and C regression checks plus full candidate Python/C comparisons across
experiments 1–4, including restart and boundary conditions. Proposed equivalence
limits remain 0.1 pp for float and 0.001 pp for double.

Measure flash, per-cell persistent state and stack usage where the tooling
supports it. Cross-compilation cannot establish execution time: measure
worst-case update time on an available target, or explicitly leave timing
unverified. Set target RAM/flash/deadline budgets before final deployment once
the actual board and number of cells are known. Preserve the existing Octave
baseline; extending Octave to the new model is a separate deliverable.

Deliverable: reproducible accepted parameters, Python/C equivalence, footprint
report, updated model equations and a concise record of positive and negative
results. If no candidate passes, retain the incumbent and report what was learned.

## First implementation milestone

The intended first milestone is the S10 decision for the 3RC-D0 experiment,
reusing the existing protocol and run selectors, followed by its prescribed fit
and evaluation. The diagnostic report is separate work, not a prerequisite for
that fit. Respect the actual decision/result chronology noted above when
formalizing work already present. Jacobian/noise changes, HPPC continuity and hysteresis are deferred
experiments, not required additions to S10 or ways to rescue its first verdict.
