# Model: conventions and equations

The 2RC equivalent-circuit model and the EKF, as used by every stage: loader, OCV and 2RC fit, EKF, metrics and the C port. The conventions below were fixed in S0 and checked against the raw data. The equations for S1 (2RC model, SoC update, table lookup, OCV slope) follow them; the EKF equations of S2 (Eq. 6 to 11) come after those. Decisions that affect results are recorded in `docs/decisions.md`.

Data: LG 18650HG2 Li-ion Battery Data, Kollmeyer et al., McMaster University, Mendeley Data v2, DOI 10.17632/b5mj79w5w9.2, CC BY 4.0. There are 206 `.mat` files in `data/raw/` [inv].

Sources: every measured number below comes from a results file that a script in this repo writes. `[inv]` = `results/data_inventory.md` and `[cap]` = `results/capacity.md` (both from `python/inventory.py`, `make inventory`). `[chk N]` = section N of `results/data_checks.md` (from `python/data_checks.py`, `make checks`). File names are shortened to `<folder>/<test>_<descriptor>`. Current and Ah values quoted from the files are in the cycler's sign (C2, C3). Row numbers count from 0 in the file as stored, before any row is dropped. A number that is a sum or ratio of printed values says so. The evaluation set is the 62 runs listed in `docs/decisions.md`: 25 degC 10, 40 degC 7, 10 degC 11, 0 degC 11, -10 degC 11, -20 degC 12 [chk legend]. The other eight drive files are `25degC/551_HWFET` (no current), `25degC/551_Mixed1` (tuning cycle), `40degC/562_Mixed4` to `Mixed8` (partial runs) and `n10degC/602_Mixed4` (corrupt, C12).

## Files and loader rules

What each test type is used for (file counts from [chk 2]):

| test type | files | used for |
|---|---|---|
| drive cycles: UDDS, HWFET, LA92, US06, Mixed1 to 8 | 70 | the EKF runs: evaluation (62 runs), tuning (`25degC/551_Mixed1`) and the S1 open-loop check (US06 at each temperature) |
| HPPC | 6 | the 2RC fit (R0, R1, tau1, R2, tau2); the 1 h rest voltages correct the OCV table (decisions 1.1) |
| C20DisCh | 6 | OCV (the C/20 discharge half, corrected onto the HPPC rest voltages) and Q_ref (the 25 degC file); the charge half is shown for comparison only |
| Cap_1C, Dis_0p5C, Dis_2C | 10, 6, 6 | the capacity tables in [cap] only; nothing is fitted on them |
| Charge | 96 | nothing is fitted; they show what a full charge looks like (C13) |
| PausCycl | 6 | not used: the readme does not list them as drive cycles and they are not in the evaluation set [inv: summary, *readme tests missing*] |

The loader applies these rules in this order. This is the only place the order is stated; C8 to C12 give the reasons and the evidence.

1. Drop every row with Voltage <= 0 and every row with NaN in Time, Voltage, Current, Ah or Battery_Temp_degC (C10).
2. Apply the per-file cuts: `10degC/571_Mixed6` starts at row 391, and `10degC/582_LA92` keeps only the rows dated 26/11/2018 (C12). Steps 1 and 2 keep the same rows in either order, because the only NaN rows are in the 582 file and lie inside the rows its cut removes, and the only 0 V rows are in Charge files, which have no cut [chk 4b, 5].
3. Of consecutive rows that share one Time value, keep the last (C9).
4. Compute dt(k) = Time(k) - Time(k-1) in float64 from the rows that are left (C8). Every dt is then above 0: the only backward Time steps are in the 582 file, and its cut removes them [inv: flags; chk 1, 4b]. Steps longer than 1 s are recorded per run and used as they are (C11).

## Conventions

Each convention gives the rule in bold, then the reason, then the evidence.

### C1. Units
**SI units: current in A, voltage in V, time in s and temperature in degC. Charge and capacity are in Ah. Inside the code SoC is a fraction from 0 to 1; reports give it in percentage points (pp).**
- Reason: the cycler already writes these units, so the loader changes only signs. The factor 3600 s/h appears only where A·s meets Ah.
- Evidence: over all 206 files, Voltage runs from 2.786 to 4.240 V, leaving out three 0 V sentinel rows (C10). Drive-cycle Current runs from -18.098 to +6.005 A, and 1C is 3.0 A (Cap_1C at -3.001 A) [inv: *V*, *I* columns]. The coulomb-counting baseline (the logged current held over each step, C13) agrees with the Ah counter: in 68 of the 69 drive files that carry current, its SoC at the end of the run differs from the counter-based reference by -0.299 pp to +0.049 pp [chk 7]. That agreement confirms A, s and Ah together. The exception is `n10degC/602_Mixed4`, 10.389 pp (C12).

### C2. Current sign
**I > 0 is discharge and I < 0 is charge (regen). The cycler writes discharge as negative, so the loader sets I = -Current.**
- Reason: with this sign, SoC falls during a discharge and the voltage drops across R0, R1 and R2 are positive, which is how the model equations are written (S2). In S1 a loader unit test checks the sign on a known discharge segment of the committed fixture.
- Evidence: all 10 Cap_1C files have Current from -3.001 to 0.000 A, and no Charge file (96) goes below 0.000 A [inv: *I min / max*]. In `25degC/551_Cap_1C_25degC_LGHG2`, the discharge step at Time 60.005 s takes Current from 0 to -3.0011 A and Voltage from 4.1927 to 4.0928 V. In `25degC/551_Charge2`, the charge step at 3600.005 s takes Current from 0 to +2.9985 A and Voltage from 3.1220 to 3.4144 V [chk 19].

### C3. Ah sign and counter semantics
**The loader's Ah column is Ah_removed(k) = -(Ah(k) - Ah_start): the Ah removed since the counting start, positive on discharge, formed only inside a stretch of rows with no counter reset. Ah_start is the counter's zero at the step start for C20DisCh and Dis_2C files, and Ah at the first row used (k0) for every other file.**
- Refinement of the spec's convention ("Ah discharged since the start of the file"), labelled as such. C20DisCh and Dis_2C files open one 60 s log interval after the cycler reset the counter at the step start, so Ah(k0) is not 0 there. Counting from the step-start zero (Ah_removed = -Ah) matches Q_ref = 2.7807 Ah (C4) and ends the 25 degC OCV axis at SoC 0. Counting from Ah(k0) would give 2.7782 Ah and shift that axis by 0.091 % of Q_ref [chk 12].
- Reason: the cycler's counter has the same sign as its current, so it falls while discharging. It is also reset at some step starts, so the meaning of Ah(k0) depends on the file type:

| file type (files) | Ah at the first row (Ah) | resets to 0 inside the file | what the first row is |
|---|---|---|---|
| drive cycle (70), PausCycl (6) | -0.00005 to 0 | none | the counter is at 0 (within 0.00005 Ah) |
| Cap_1C (10) | 0 | none | counter at 0 at the test start |
| HPPC (6) | 0 | 5 of 6 files, two each: during the final 3660 s rest that follows the last move, and on the last row | counter at 0 at the test start |
| Charge (96) | 0 | 28 files: 25 on the last row, 3 on the second-to-last row; 3 further resets on other rows (the only file with several charges is `25degC/549_Charge`, four [chk 9]) | counter at 0 at the test start |
| C20DisCh (6) | -0.00254 to -0.00245 | none | file opens one 60 s interval into the C/20 discharge, after a reset at the step start |
| Dis_2C (6) | -0.09999 to -0.09666 | 5 of 6 | as C20DisCh, one 60 s interval at 2C |
| Dis_0p5C (6) | -0.06718 to +0.16524 | 5 of 6 | not reset: continues the folder's C20DisCh counter |

- Evidence: first-row values and reset counts are [chk 16]; a counter that only passes through 0 under regen is not a reset. The first HPPC reset comes during the final 3660 s rest that follows the last move, 1 h before the in-file recharge starts, and Ah_removed is valid up to it [chk 10]. Stepped back one interval at the first row's current, the C20DisCh and Dis_2C counters are 0 to within 0.00004 Ah, and the Dis_0p5C counters equal the C20DisCh file's last Ah to within 0.00007 Ah [cap: Method; chk 13]. [cap] counts a 0.5C capacity from that carried value (2.7507 Ah at 25 degC), while the loader column, counted from Ah(k0), gives 2.7257 Ah there [chk 13]. The 0.5C files feed the capacity tables only, so the difference reaches no fit.

### C4. SoC definition and Q_ref
**SoC(t) = SoC0 - ∫ I dt / (3600 · Q_ref), with Q_ref = 2.7807 Ah at every temperature. For the reference SoC the integral is the cycler's Ah counter (C13). Q_ref is the C/20 discharge capacity at 25 degC: -Ah at the last discharge row of `25degC/10-26-18_09.29 549_C20DisCh_25degC_LGHG2.mat`, 2.78074 Ah, counted from the step-start zero (C3).**
- Reason: the reference SoC, the SoC axis of the OCV tables and the EKF process model all use this one Q_ref, so the filter has no capacity bias built in (the spec). The reference follows the cycler's counter and the filter integrates the logged current, so the two can still differ by up to 0.30 pp at the end of a run (C13). 2.7807 Ah is the charge removed from the full-charge state, where SoC = 1. The alternative that uses logged samples only, -(Ah(k) - Ah(0)) = 2.7782 Ah, leaves out the first unlogged interval (0.0025 Ah, 0.091 %). Drive-cycle counters start at 0 at the full-charge state (C3, C13), so Q_ref and the reference SoC count from the same point.
- Cold runs end at a higher reference SoC because less capacity is usable in the cold (C14). This is expected and is not folded into Q_ref. The usable 1C capacity per temperature is in [cap: "C/20 and 1C capacities per folder"].
- Evidence: [cap: row 1 and "25 degC C/20 discharge capacity"] gives 2.7807 Ah at a mean 0.152 A, ending at 2.800 V with the cell at 23.6 / 24.3 degC. [chk 12]: the last discharge row is row 1096, at Time 65,733.85 s (18.26 h) and 2.79993 V; Ah(0) = -0.00254 Ah.

### C5. Coulombic efficiency
**η (eta) = 1 for charge and discharge.**
- Reason: the reference SoC is built from the cycler's counter (C13). That counter is a signed integral of the current: it weights charge and discharge equally, and the filter's process model has to match it. The data gives no basis for another value: the C/20 charge puts back between 0.983 and 1.068 times the Ah the discharge removed, the ratios fall on both sides of 1, and none is explained.
- Evidence: the counter matches the baseline's integral of Current in drive files that include regen (C1). The C/20 ratios are 1.068 / 1.066 / 1.018 / 1.034 / 1.015 / 0.983 at 25 / 40 / 10 / 0 / -10 / -20 degC [cap: Anomalies].

### C6. Temperature input
**T is the measured cell temperature, field Battery_Temp_degC. The files contain no chamber temperature.**
- Reason: the cell heats itself under load, and its parameters follow its own temperature, not the chamber's (the spec).
- Evidence: all 206 files hold exactly Time, TimeStamp, Voltage, Current, Ah, Wh, Power and Battery_Temp_degC [inv: *fields* = "8 expected", and the legend]. Drive-cycle cell temperature, min / max per folder: 23.6 / 26.8 degC at 25degC, -10.3 / -4.7 at n10degC and -20.2 / -14.6 at n20degC [inv: summary per folder].

### C7. Filter rate
**The filter runs at the native logging rate of the drive cycles, nominally 0.1 s. Nothing is decimated.**
- Reason: tau1 is fitted in [0.5, 30] s, so 1 s steps would not resolve the fast RC branch.
- Evidence: drive-cycle dt per folder, as median (1st to 99th percentile): 0.100 (0.096 to 0.104) s at 25degC and 40degC, 0.100 (0.095 to 0.105) s at 10degC and 0degC, and 0.101 (0.094 to 0.106) s at n10degC and n20degC. Of the 4,498,539 steps in the 70 drive files, 99.893 % lie between 0.09 and 0.11 s [chk 1]. The per-file median is 0.099 to 0.101 s [inv: *median dt*]. The other tests log slower: Cap_1C at 10 s; C20DisCh, Dis_0p5C, Dis_2C and Charge at 60 s [inv: *median dt*]; they are not filter inputs (see Files). HPPC logs at 0.1 s in the pulses and their 40 s rests, and at 10 s through the 1 h rests [chk 10].

### C8. dt comes from Time, never from TimeStamp
**dt(k) = Time(k) - Time(k-1), computed in float64 in step 4 of the loader rules. TimeStamp is used only to put files in order and to find hidden pauses.**
- Reason: Time is a float64 clock in seconds. TimeStamp shows whole seconds in 25degC, and in the other folders its whole second sometimes lags the millisecond digits by up to 1 s. Its usable resolution is therefore 1 s, ten times the sample step. The C tool reads dt from a column that Python writes and never subtracts timestamps (the spec).
- Evidence: [inv: legend, *TimeStamp format*] notes that "Time, not TimeStamp, is the sample clock".

### C9. Duplicate Time values: keep the last row
**When consecutive rows share one Time value, the loader keeps the last of them and drops the rest, so every step it keeps has dt > 0.**
- Reason: both rows are the same instant, and a step with dt = 0 cannot be used. The choice moves no kept sample by more than the difference inside the pair: of the 5,754 duplicate rows, 68 pairs differ in Current or Voltage, by at most 2.56 mA and 0.170 mV. 63 of the 67 differing HPPC pairs (sum of the table) are the last sample of a current step [chk 2]. Keep-last takes the later logged value.
- Evidence: 5,754 duplicate rows in 177 of 206 files. Each HPPC file has 193 to 247, of which 9 to 13 differ. 47 of the 70 drive files end on a duplicated row, and in all 47 both rows have Current = 0 A. `n10degC/602_Mixed4` alone holds 4,160 of the 4,212 duplicate rows in drive files, 4,159 of them in its frozen block (C12) [chk 2].

### C10. Dropped rows
**Step 1 of the loader rules drops every row with Voltage <= 0 and every row with NaN in Time, Voltage, Current, Ah or Battery_Temp_degC.**
- Reason: 0 V is the cycler's end-of-test sentinel, not a measurement, and a NaN row holds no sample. Wh and Power are not used, so a NaN in them alone does not drop a row.
- Evidence: 0 V appears only on the last row of `25degC/552_Charge16` (row 127), `40degC/557_Charge10` (row 32) and `0degC/590_Charge16` (row 152) [chk 5; inv: *Voltage <= 0* flag]. NaN appears only in `10degC/582_LA92_10degC_LGHG2` [inv: "4 rows with NaN"]. Rows 1491, 1492 and 1944 are NaN in Voltage, Current, Ah, Wh, Power and Battery_Temp_degC (Time is not NaN), and row 1943 is NaN in Wh only [chk 5]. All four lie in the rows that the 582 cut removes (C12).

### C11. Gaps
**Steps longer than 1 s are recorded per run (how many and how long) and used as they are. The filter takes the actual dt at every step with the spec's exact zero-order hold: the predict step integrates the previous kept sample's current over the whole dt. A long step therefore moves the SoC mean by I·dt/(3600·Q_ref) as well as widening the prior (process noise scales with dt, S2). There is no special gap code.**
- Reason: a hold over dt is what the exact process model defines for any dt. Interpolating the current across a step would be no better founded, and a separate rule for long steps would need its own code and threshold. The coulomb-counting baseline uses the same dt and hold (C13).
- Evidence: 10 of the 70 drive files have steps longer than 1 s [chk 3]. Nine are evaluation runs: `25degC/551_UDDS` and `551_LA92`, `40degC/556_UDDS` and `556_LA92`, `10degC/576_UDDS` and `582_LA92`, `0degC/589_LA92`, `n10degC/596_LA92`, `n20degC/610_LA92`. Together they have 32 cycle-boundary steps of 1.147 to 2.143 s; the 32 include the 5 steps (1.641 to 2.056 s) that 582_LA92 keeps after the C12 cut. The tenth is `n10degC/602_Mixed4`, which is excluded (C12).
- Size of the error at a boundary step: the longest step, 2.143 s, held at 6.00 A (the largest regen current in the evaluation runs) is 0.129 pp of Q_ref, and at 18.10 A (the largest discharge current) it would be 0.387 pp, the theoretical worst case. Measured, the held current against the counter's change over the 32 steps differs by at most 0.0024 pp, because the current at these steps is at most 117.5 mA [chk 3].

### C12. Hidden pauses, the false start and the frozen block
**Three drive files are damaged. `10degC/571_Mixed6` and `10degC/582_LA92` get a cut (loader step 2). `n10degC/602_Mixed4` is excluded from the evaluation set.**
- `10degC/571_Mixed6_10degC_LGHG2`: between rows 390 and 391, Time advances 0.003 s while TimeStamp jumps 37,526.003 s (10.42 h). Row 390 is at 4.2399 V and +2.86316 A of regen, above the 4.2 V charge limit, which suggests an over-voltage stop (an inference; the file does not say so). Row 391 is at 4.1657 V, 0 A, Ah = -0.01008 Ah. **The run starts at row 391**, and SoC0 = 0.99638 comes from the counter (C13) [chk 4a].
- `10degC/582_LA92_10degC_LGHG2`: rows 0 to 1030 are a false start dated 25/11 (Time 0 to 102.935 s). Its counter reaches -0.01453 Ah at row 1009 and ends at -0.01436 Ah at row 1030, which is at 4.2345 V and +2.9858 A, the same over-voltage signature as 571 row 390. Then TimeStamp jumps 47,423.002 s (13.17 h) while Time advances 0.002 s, and the real run starts at row 1031 (26/11, 10:11:10 to 12:40:49) at 4.15933 V, 0 A, Ah = -0.01436 Ah. **Only the 89,702 rows dated 26/11 are used** (1,038 of the file's 90,740 rows are dated 25/11). Seven rows dated 25/11 sit inside the real run, at rows 1488 to 1492 and 1943 to 1944. They hold the NaN rows (C10), and three of the four backward Time steps involve them: rows 1487 to 1488 (-147.204 s), 1490 to 1491 (-1.402 s) and 1942 to 1943 (-154.998 s). The fourth, rows 228 to 229 (-22.297 s), lies inside the false start. The 582 run opens at SoC0 = 0.99484 from the counter. After keep-last it has 89,701 rows, Time 102.937 to 9082.415 s, and 5 steps above 1 s (C11) [chk 3, 4b].
- `n10degC/602_Mixed4_n10degC_LGHG2`: rows 3867 to 8026 are 4,160 identical copies of one sample at Time 386.704 s (4.19995 V, +1.50948 A; a logger stall). The next step is 415.993 s, unlogged in both Time and TimeStamp, and the counter moved from -0.14564 to -0.26146 Ah in it: 0.11582 Ah, 4.165 pp of Q_ref, which the logged current never shows. A zero-order hold over that step with the current of the row before (+1.50948 A) moves SoC by +6.27 pp, with the row after (-1.49159 A) by -6.20 pp, and the counter moves the reference by -4.17 pp. No hold rule reproduces the counter, and over the run the baseline ends 10.39 pp from the reference. **The run is excluded** from the evaluation set. The loader still reads it, and keep-last reduces the frozen block to one row [chk 4c, 7].
- Reason: Time does not show the 571 and 582 breaks. The general rules alone would treat a 10 h rest as a 3 ms step, and would mix the false start into the real run.
- Evidence: [inv: *flags*] gives "TimeStamp span is 10.42 h longer than Time span", "4 backward Time steps; TimeStamp span is 13.17 h longer than Time span" and "4160 consecutive rows share one Time value (logger stall)". The row numbers and values above are [chk 4].

### C13. Reference SoC and the full-charge start
**SoC_ref(k) = SoC0 - Ah_removed(k) / Q_ref: coulomb counting on the cycler's Ah counter (C3) from the full charge at the start of each test, with SoC0 = 1 and η = 1.**
- Exceptions: `10degC/571_Mixed6` and `10degC/582_LA92` start after some charge has already been removed (C12). Their SoC0 is 1 minus the charge the counter removed before the first row used, divided by Q_ref: 0.99638 (0.01008 Ah) and 0.99484 (0.01436 Ah) [chk 4a, 4b]. `0degC/590_Mixed4` opens under load with no logged rest right before it (below). It keeps SoC0 = 1 and is listed among the drive cycles whose full-charge start is not confirmed [inv: legend]. `40degC/562_Mixed4` has the same problem but is a partial run, so it is not in the evaluation set.
- Reason: the reference uses the same Q_ref and η as the filter (C4, C5). It counts on the cycler's counter because the spec defines the reference as coulomb counting from the full charge, and the counter is the cycler's own count.
- Baseline versus reference: the plain coulomb-counting baseline does not use the counter. It integrates the logged current with the same dt and hold rule as the filter (C11), as a BMS would. The two are therefore not equal by construction. They differ by at most 0.299 pp (0.30 pp) over a run, in `0degC/589_US06`, and the end-of-run difference over the 62 evaluation runs lies between -0.299 and +0.049 pp [chk 7]. Experiment 1 reports "coulomb counting vs reference" as a column, and the spec's sentence that the two are equal by construction is amended. In `n10degC/602_Mixed4` they differ by 10.389 pp (C12).
- What a full charge looks like in the files [chk 9]. Of the 96 Charge files, 95 carry current (all but `40degC/557_Charge10`); these 95 are the files counted here. Each rests 3600.0 s, charges, holds about 4.1998 V (highest sample 4.2000 V) until the current falls to 0.0485 A, which is the last charge current in all 95, then rests 3660.0 to 3661.0 s. 78 of the 95 have a constant-current phase above 2.9 A (median 2.9985 A, largest sample 3.0011 A): 77 single-charge files plus `25degC/549_Charge`, which holds four charges. The other 17 have none: ten short top-ups (0.0046 to 0.0169 Ah charged, peaks 0.102 to 0.268 A), `40degC/562_Charge11` to `562_Charge15` (peaks 2.401 to 2.541 A), `40degC/562_Charge16` (peak 0.518 A) and `n10degC/604_Charge17` (peak 0.756 A). The cell is at 22.92 to 24.61 degC at the first charging row, and at 22.92 to 25.45 degC over all charging rows (549_Charge included).
- Five drive files follow one of those 17 instead of a CC-CV charge: `25degC/551_LA92` (after `551_Charge4`, peak 0.238 A) and `40degC/562_Mixed5` to `Mixed8` (after `562_Charge11` to `14`). 551_LA92 stays in the evaluation set because it opens at a full-charge rest voltage (4.1916 V). The 562 runs are partial runs and are excluded [chk 8, 9].
- The drive file opens at the full-charge rest voltage: 57 of the 69 drive files with current open at rest, at 4.1814 to 4.1916 V and -0.0511 to -0.0077 A, so the rest voltage is below 4.2 V. The other 12 (Mixed4 and Mixed8 runs) open under load, at 4.0550 to 4.1781 V and -1.7215 to -1.1034 A. 10 of them start at most 300 s after a Charge file whose last row is a rest above 4.15 V. The other two are `40degC/562_Mixed4` (after the empty `557_Charge10`) and `0degC/590_Mixed4` (4.1494 V, 15,859 s after `589_Charge8`) [chk 8].
- Three drive files do not follow their Charge file closely [chk 8]: `10degC/567_US06` is the first file of its folder, `n10degC/601_US06` starts 556,663 s (about 6.4 days) after `596_Charge5` ended, and the `10degC/582_LA92` false start begins 451,617 s (about 5.2 days) after `576_Charge4` ended. Their first rows used are at rest above 4.15 V (4.1840 V, 4.1858 V and 4.1593 V). They are taken as full.
- Evidence: [inv] has the *full charge at start* column per file and the list of starts not confirmed. The charge, start and chronology numbers above are [chk 8, 9].

### C14. Evaluation window
**Every metric is computed from the filter start to the last sample where SoC_ref >= 0.10.**
- Reason: the end of a run near empty is where the model is worst (the spec).
- Which runs it cuts: the lowest end-of-run SoC_ref in the evaluation set is 9.17 % at 40 degC, 6.85 % at 25, 10.83 % at 10, 15.49 % at 0, 22.67 % at -10 and 42.90 % at -20 degC (the highest at -20 degC is 44.75 %) [chk 7]. The cut therefore applies only at 40 degC (the six test-556 runs; `557_Mixed3` ends at 14.57 %) and at 25 degC (all 10 evaluation runs, which end at 6.85 to 8.00 %). At 10 degC and below, the window is the whole run.
- Evidence: end SoC_ref = 1 - (Ah removed)/Q_ref, with *Ah removed* from [cap: "Drive-cycle stop rule"]. For example, the 40degC test-556 runs remove 2.5255 to 2.5256 Ah, and 1 - 2.5256/2.7807 = 9.17 %. The end value and window of every run are in [chk 7]. The 40degC 562 partial runs (0.19 Ah each, ending at 93.17 to 93.18 %) and 551_HWFET (no current) are not counted.

### C15. Grids
**SoC grid: 0 to 1 in steps of 0.01 (101 points). Temperature grid: the six folder temperatures, 40, 25, 10, 0, -10 and -20 degC. Every parameter table uses these two axes.**
- Reason: these are the set points at which HPPC and C/20 tests exist, and sharing one grid between Python and C keeps their lookups identical (the spec). A temperature between grid points is interpolated, and one outside the grid is clamped to the edge (S1).
- Evidence: the cell runs near the set points but not at them. The median Battery_Temp_degC over each folder's evaluation runs is 38.70, 24.08, 9.57, 0.00, -9.04 and -18.40 degC at 40, 25, 10, 0, -10 and -20 degC [chk 6]. The min / max per folder is in [inv: summary per folder].

## Symbols

| symbol | meaning | unit | sign / range |
|---|---|---|---|
| SoC | state of charge | 1 (fraction; reports in pp) | 0 to 1; falls when I > 0 |
| SoC0 | SoC at the first row used (C13) | 1 | 1, except 0.99638 for `10degC/571_Mixed6` and 0.99484 for `10degC/582_LA92` |
| η | coulombic efficiency (C5) | 1 | 1 |
| Ah_removed | charge removed since the counting start (C3) | Ah | positive on discharge, negative under regen |
| V1, V2 | voltages across the fast (1) and slow (2) RC branches | V | follow the recent current: > 0 after discharge, < 0 after regen, 0 after a long rest |
| I | cell current (I = -Current) | A | > 0 discharge, < 0 charge |
| V | measured terminal voltage | V | > 0 (2.786 to 4.240 V in the data, C1) |
| T | measured cell temperature, Battery_Temp_degC | degC | either sign (40 to -20 degC grid) |
| dt | step between kept rows, from Time | s | > 0 (C8, C9) |
| Q_ref | reference capacity | Ah | > 0; 2.7807 Ah (C4) |
| R0 | series (ohmic) resistance | Ohm | > 0 |
| R1, R2 | RC branch resistances | Ohm | > 0 |
| tau1, tau2 | RC branch time constants, tau_i = R_i · C_i | s | > 0; tau1 in [0.5, 30] s, tau2 in [30, 3600] s (3600 s = the HPPC 1 h rest after each move, 3600.105 to 3600.131 s [chk 10]) |
| OCV | open-circuit voltage OCV(SoC, T) | V | > 0; checked monotone in SoC (S1) |
| dOCV/dSoC | slope of OCV over SoC, a table by central differences (S1) | V (per unit SoC) | >= 0 |
| Q | process noise covariance diag(q_soc, q_v, q_v) · dt; q_soc in 1/s, q_v in V²/s | 1, V², V² on the diagonal | >= 0 (positive semi-definite) |
| R | measurement noise variance | V² | > 0 |
| P0 | initial state covariance diag(0.2², 0.05², 0.05²) | 1, V², V² on the diagonal | > 0 (positive definite) |

## Equations

The equations of S1, numbered for citation in the Python and C code (a comment reads "docs/model.md Eq. 1"). Symbols are those of the table above. Index k counts the rows a run keeps after the loader rules, `dt(k) = t(k) - t(k-1)` (C8, C9), and I is the loader-sign current, positive on discharge (C2). R0, R1, R2, tau1, tau2 and OCV are not constants: each is a table over (T, SoC) read with Eq. 4. Python (`python/ekfsoc/model.py`) and the C port repeat these equations with the same operation order.

### Eq. 1. The two RC branches, exact zero-order hold

```
a_i(k)  = exp(-dt(k) / tau_i)                                        i = 1, 2
V_i(k)  = a_i(k) · V_i(k-1) + R_i · (1 - a_i(k)) · I(k-1)
```

- R_i and tau_i are read with Eq. 4 at the start of the step, at (T(k-1), SoC(k-1)). The current held over the step is the previous kept sample's current, I(k-1) (C11).
- Where it comes from: branch i is a resistor R_i in parallel with a capacitor C_i = tau_i / R_i, so dV_i/dt = -V_i / tau_i + R_i · I / tau_i. With I constant over the step, the solution over dt is Eq. 1 exactly. It is not an Euler step, so it holds for any dt, from the 0.1 s logging step to the 1.147 to 2.143 s steps at cycle boundaries (C11).
- Limits: dt = 0 gives a_i = 1 and leaves V_i unchanged. A long step gives a_i -> 0 and V_i -> R_i · I(k-1), the steady value of a constant current.
- Start: V1(0) = V2(0) = 0. The open-loop check starts the branches relaxed; C13 lists the runs that open under load.
- Sign: V_i > 0 after a discharge, V_i < 0 after regen (Symbols).

### Eq. 2. Terminal voltage

```
V_model(k) = OCV(SoC(k), T(k)) - V1(k) - V2(k) - R0(SoC(k), T(k)) · I(k)
```

- OCV and R0 are read with Eq. 4 at the sample itself, (T(k), SoC(k)). The sample's own current drops across R0 at once, while it enters V1 and V2 only from the next row on (Eq. 1).
- V_model is compared with the measured terminal voltage V.
- In S1's open-loop check SoC(k) is the reference SoC of C13, so only the voltage model is under test. In S2 the filter's SoC state takes its place.

### Eq. 3. Coulomb counting

```
SoC(k) = SoC(k-1) - η · I(k-1) · dt(k) / (3600 · Q_ref)             η = 1 (C5)
```

- The factor 3600 converts A·s to Ah (C1). The previous kept sample's current is held over dt(k) (C11), as in Eq. 1.
- This is the SoC process model of the filter (S2) and of the plain coulomb-counting baseline. The reference SoC is the same sum taken on the cycler's Ah counter, `SoC_ref(k) = SoC0 - Ah_removed(k) / Q_ref` (C3, C4, C13); the two can differ by up to 0.30 pp over a run (C13).

### Eq. 4. Table lookup: bilinear interpolation with clamping

Every parameter table F has one row per temperature node T_j (j = 0 to n_T - 1, stored in the order 40, 25, 10, 0, -10, -20 degC, so descending) and one column per SoC node S_m (m = 0 to n_S - 1, ascending, C15). The value at (T, S) is computed in this order:

```
1. clamp:    T_c = min(max(T, T_lo), T_hi)         T_lo, T_hi = smaller, larger of the two end nodes
             S_c = min(max(S, S_lo), S_hi)         (a query beyond an axis end takes the end value)
2. cell:     j = the largest index in 0 .. n_T - 2 with  d_T · (T_c - T_j) >= 0
             m = the largest index in 0 .. n_S - 2 with  d_S · (S_c - S_m) >= 0
             d = +1 for an ascending axis, -1 for a descending one
3. weights:  w_T = (T_c - T_j) / (T_{j+1} - T_j)
             w_S = (S_c - S_m) / (S_{m+1} - S_m)                      both in [0, 1]
4. along S:  F_a = (1 - w_S) · F[j][m]   + w_S · F[j][m+1]
             F_b = (1 - w_S) · F[j+1][m] + w_S · F[j+1][m+1]
5. along T:  F(T, S) = (1 - w_T) · F_a + w_T · F_b
```

- The weights are written (1 - w) · x + w · y and not x + w · (y - x), so a query exactly on a node returns that node's value with no rounding. At the last node of an axis the cell is the last one (index n - 2) and w = 1.
- The same rule serves all seven tables: OCV, dOCV/dSoC, R0, R1, tau1, R2, tau2. No table is extrapolated.
- Clamping matters in use: the measured cell temperature can lie beyond the 40 and -20 degC nodes [inv: summary per folder, drive-cycle cell T min / max] and an estimated SoC can leave 0 to 1.

### Eq. 5. dOCV/dSoC by central differences

On the SoC grid S_0 .. S_{n-1}, for each temperature node:

```
dOCV/dSoC(S_m) = (OCV(S_{m+1}) - OCV(S_{m-1})) / (S_{m+1} - S_{m-1})        0 < m < n - 1
dOCV/dSoC(S_0) = (OCV(S_1) - OCV(S_0)) / (S_1 - S_0)                         one-sided at the low end
dOCV/dSoC(S_{n-1}) = (OCV(S_{n-1}) - OCV(S_{n-2})) / (S_{n-1} - S_{n-2})     one-sided at the high end
```

- Computed once in Python from the OCV table and stored as its own table. Python and C both read it with Eq. 4 and never differentiate at runtime, so the Jacobians of the two are identical.
- Below the lowest SoC the C/20 discharge reached, the OCV table is held constant (decisions 1.1), so the differences are 0 over that held region. At the two nodes next to its edge they mix held and measured values. The valid SoC range per temperature is in `results/params.md`.
- Unit: V per unit SoC (Symbols). It is not negative where OCV is monotone in SoC.

## EKF equations (S2)

The filter of S2, numbered after Eq. 5 and cited the same way in the Python (`python/ekfsoc/ekf.py`) and C code, which repeat these equations with the same operation order. State x = [SoC, V1, V2]^T with covariance P (3 x 3), input I, measurement V. One step handles one kept row k and has two parts, `predict` (Eq. 6, Eq. 7) and `update` (Eq. 8 to Eq. 11):

- x(k-1) and P(k-1) are the posterior of the previous row. x- and P- are the prior after predict (SoC-, V1-, V2- are the entries of x-). x and P without a mark are the posterior after update.
- dt = dt(k) and T = T(k), the measured cell temperature of the row being processed. The held current is I(k-1), the previous kept sample's current (C11). The update uses the row's own V(k) and I(k).
- Q is the process noise covariance, R the measurement noise variance, P0 the initial covariance (Symbols). The same q_soc, q_v, R and P0 are used for every experiment and temperature, and the filter is never told that an initial SoC is wrong.
- Start of a run, or of a restart in mid-run: x = [SoC0, 0, 0], P = P0, and the first processed row has its dt taken as 0. Then F is the identity and B and Q are zero, so predict changes nothing and that row gets an update only. V1 = V2 = 0 holds also where a run opens under load or the filter starts mid-test (C13).

### Eq. 6. Process model

```
a_i  = exp(-dt / tau_i)                                              i = 1, 2
F    = diag(1, a1, a2)
B    = [ -dt / (3600 · Q_ref),   R1 · (1 - a1),   R2 · (1 - a2) ]^T
x-   = F · x(k-1) + B · I(k-1)
```

- Row by row: `SoC- = SoC(k-1) - I(k-1) · dt / (3600 · Q_ref)` is Eq. 3 with η = 1, and `Vi- = a_i · Vi(k-1) + R_i · (1 - a_i) · I(k-1)` is Eq. 1.
- R1, tau1, R2 and tau2 are read with Eq. 4 at the previous posterior SoC, SoC(k-1), and at T(k). Eq. 1 reads T(k-1); the filter takes one temperature per sample, so predict and update of a step use the same one.
- The current is held over the whole step, including the cycle-boundary steps of up to 2.143 s, with no special gap code (C11).
- SoC is not limited in predict. The limit is applied in update (Eq. 10), and a prior outside 0 to 1 is clamped by the lookups of Eq. 4.

### Eq. 7. Covariance prediction

```
Q    = diag(q_soc, q_v, q_v) · dt                                    q_soc in 1/s, q_v in V²/s
P-   = F · P(k-1) · F^T + Q
```

- Process noise grows in proportion to the elapsed time, so a longer step widens the prior by more (C11).
- F is diagonal, so `P-[i][j] = f_i · f_j · P(k-1)[i][j]` plus `Q[i][i]` on the diagonal, with f = (1, a1, a2). The code writes it as two 3 x 3 products, `F · P` and then `(F · P) · F^T`.
- F is the Jacobian of Eq. 6 with respect to x in which the dependence of a_i and R_i on SoC is left out, as dR0/dSoC is left out of H in Eq. 8. Both are approximations.

### Eq. 8. Predicted voltage and measurement Jacobian

```
y_hat = OCV(SoC-, T) - V1- - V2- - R0(SoC-, T) · I(k)
H     = [ dOCV/dSoC(SoC-, T),   -1,   -1 ]
```

- OCV, dOCV/dSoC and R0 are read with Eq. 4 at the prior SoC, SoC-, and at T(k). I(k) is the row's own current (Eq. 2). y_hat is Eq. 2 with the prior state in place of the true one, and is what the voltage diagnostic compares with V(k).
- H is the gradient of y_hat with respect to x. The slope is the table of Eq. 5 read with Eq. 4, not the derivative of the interpolated OCV. dR0/dSoC is left out of H: the term `-I(k) · dR0/dSoC` is missing from its first entry. This approximation is noted in the spec.

### Eq. 9. Innovation variance and gain

```
S    = H · P- · H^T + R                                              scalar, V²
K    = P- · H^T / S                                                  3 x 1
```

- S > 0 because P- is positive semi-definite and R > 0.

### Eq. 10. State update and SoC limit

```
x      = x- + K · (V(k) - y_hat)
b      = min(max(SoC, 0), 1)                                         SoC of the x above
x      = x - P[:, 0] · (SoC - b) / P[0][0]                           P from Eq. 11, SoC and x as above
```

- The third line acts only when the updated SoC is outside [0, 1] (otherwise SoC = b and it changes nothing, and the code skips it). The whole state then moves onto the nearer bound b along the first column of the posterior P, so V1 and V2 move with SoC by their correlation with it and SoC equals b afterwards.
- P is the posterior of Eq. 11, which the code forms before this step, and the projection leaves it unchanged.
- Reason: truncating SoC alone keeps the V2 part of an innovation that pushed SoC past a bound, which grew the next innovation and ran V2 away to thousands of volts (docs/decisions.md 1.16).

### Eq. 11. Covariance update, Joseph form

```
P    = (I - K · H) · P- · (I - K · H)^T + K · R · K^T
```

- In exact arithmetic this P is symmetric and positive semi-definite for any K, while the short form `(I - K · H) · P-` equals it only for the optimal gain of Eq. 9. The Joseph form keeps P valid when K is rounded, in particular in the float build of the C port.
- The code forms `(I - K · H)` once, then `(I - K · H) · P-`, then multiplies by `(I - K · H)^T` and adds `R · K · K^T`.
