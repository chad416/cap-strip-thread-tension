# Traceability: requirement -> implementation -> verification -> evidence

Requirements are defined in [DOSSIER.md section 4](DOSSIER.md); verification methods I / A / D / T
after [W] p.270-272. This is the RVTM of DOSSIER section 11.1 extended with code and test locations.
Status for alternative D (the recommendation), 11 Nov 2026; "A" evidence is simulation.

| Req. | Need | Implemented in | Verified by | Evidence | Status |
|---|---|---|---|---|---|
| SPS-201 Breaks <= baseline | N1 | whole system | T: VAL-1 | - | open (plant) |
| SPS-202 Spool defects <= baseline | N3 | FB_WinderTension | T: VAL-1 | - | open (plant) |
| SPS-203 Closed loop >= 99 % available | MOS-1 | FB_ThreadBrake fallback | A: DOSSIER 9.3 | Ai 0.99994 (estimate) | A met; T open |
| SPS-301 +-10 % over >= 99 % of the bobbin | N1, N2 | FB_ThreadBrake (radius, FF, PI, damping) | A: `run_study.stage_steady_dynamic` | results/study.md section 3 | A met (100 %, p99 2.5 %) |
| SPS-302 Pre-strain spread <= 1.0 % | N2 | sensor after the last guide | A: same | results/study.md section 3 | A met (0.50 %) |
| SPS-303 Start/stop 0.8-1.25 x | N1 | FB_ThreadBrake FF + damping | A: `stage_transients` | results/study.md section 4 | A met (0.85-1.20) |
| SPS-304 E-stop: slack <= 10 mm, peak <= 1.5 x | N1 | FB_ThreadBrake mode 4, category-1 supply | A: `stage_transients` | results/study.md 4.3, docs/img/estop.png | A met in cat. 1 (0 mm, 1.50); not met in cat. 0 |
| SPS-305 Bobbin change w/o NewBobbin | N1, N5 | FB_ThreadBrake re-seed + damping gate | A: `stage_bobbin_change` | results/study.md section 7 | A met (0.1 s, 4.6 s) |
| SPS-311 Measurement 2 % (1 sigma), >= 10 Hz | N2, N4 | 3-roller sensor + calibration | A: `sensor.chain_budget` | results/study.md section 12 | A met after calibration (1.3 %) |
| SPS-312 Virtual tension reported | N4, N5 | FB_ThreadBrake region Observer | I | `Tvirtual`, `TvirtualOk` | met |
| SPS-321 Break detected <= 100 ms | N4 | FB_LineSupervisor | T: `test_supervisor_break_detection_triggers_stop` | pytest | met in the translator |
| SPS-322 Capture, classify, count | N4 | FB_DataCollect | T: `test_datacollect_capture_and_classification` | pytest | met in the translator |
| SPS-323 Sensor fault: step <= 5 % | N5 | FB_ThreadBrake integral handling | T: `test_thread_brake_sensor_fault_fallback_is_bumpless` | pytest | met in the translator |
| SPS-331 Winder +-10 % through start/stop | N3 | FB_WinderTension | A: `stage_winder` | results/study.md section 9 | A met at the limit (0.94-1.10) |
| SPS-332 Recipe above capstan slip | N3 | recipe (HMI) | A: `winder.capstan_min_tension` | results/study.md section 9 | met (21.8 N vs 40 N) |
| SPS-361 <= 3 ms incl. margin at 10 ms | constraint | all FBs, OB30 | A: `stage_budget`; T: VT-07 | results/study.md section 11 | A met (1.73 ms) |
| SPS-362 TIA V18, 0 errors / 0 warnings | constraint | plc/ | T: TIA Openness | results/tia_compile*.txt, docs/img/tia_FB_ThreadBrake.png | met |
| SPS-363 New hardware IF-01...IF-03 only | constraint | plc/tia/LineIO_OB_DB.scl | I | DOSSIER section 6 | met |

## Code-to-requirement index

| File | Requirements |
|---|---|
| `plc/FB_ThreadBrake.scl` | SPS-301...305, SPS-312, SPS-323 |
| `plc/FB_WinderTension.scl` | SPS-331 |
| `plc/FB_LineSupervisor.scl` | SPS-304, SPS-321 |
| `plc/FB_DataCollect.scl` | SPS-322 |
| `plc/tia/*` | SPS-361...363 |
| `src/captension/sensor.py` | SPS-311 |
| `src/captension/winder.py` | SPS-331, SPS-332 |
| `src/captension/breaks.py` | SPS-201 (prediction), MOE-1 |
