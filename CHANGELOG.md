# Changelog

## 0.1.0 (10 Nov 2026)

- **Model** (`src/captension/`):
  - bobbin geometry and inertia over the package (r^2 from the consumed length, J(r));
  - three-segment cord path bobbin -> guides -> template -> capstan from conservation of cord,
    reducing to the web-span equation of Koc et al. (2002) to first order; Kelvin-Voigt cord damping;
    slack and snatch;
  - capstan friction of the guides, power-law drag of the rubberising template with wall slip and a
    restart overshoot;
  - five unwind concepts: constant-torque friction brake, dancer-compensated band brake,
    magnetic-particle brake open loop, the same with a tension sensor and PI, servo unwind;
  - emergency stop in category 0 and 1;
  - strip span and winder with taper; capstan no-slip limit.
- **Breaks** (`breaks.py`): weak-spot model, material tracking through the path with a sparse-table
  range maximum, Euler attribution to unwind / guides / template, counterfactual levers.
- **PLC** (`plc/`): FB_ThreadBrake, FB_WinderTension, FB_LineSupervisor, FB_DataCollect, generated
  OB30 (10 ms) and DBs. TIA Portal V18 compile: 0 errors, 0 warnings, OB30 as a cyclic interrupt at
  10 ms.
- **Defects found on the way and fixed** (DOSSIER section 13):
  - float32: the per-cycle radius prediction drifted to +10 % at the end of a bobbin; now applied
    once per metre;
  - TIA: a temporary `tI` clashed with the input `Ti` (SCL names are case-insensitive); the
    translator now rejects such clashes;
  - TIA: outputs used as state ("might not be initialized", 44 warnings) moved to statics;
  - the speed-damping term gated on the radius check switched itself off during oscillations and
    destabilised the loop; now gated on a persistent mismatch (0.3 s) only;
  - the first span model let the cord leave the package already stretched; corrected to a relaxed
    package (wound-in strain zero), which the Koc equation test now guards.
- **Study, trade study, dossier** (Markdown and PDF), traceability, CI.
