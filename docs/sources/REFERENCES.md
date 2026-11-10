# References and source status

Every value or relation in the repo carries one of these source states (the same convention
as `captension.params`):
- **[read]**: I opened the source and the cited value comes from it.
- **[abstract]**: only an abstract, a product listing or a search snippet was available.
- **[std]**: a standard textbook or standard result quoted from memory; the section is named, the page was not re-checked.
- **[derived]**: computed in this repository from tagged values.
- **[assumed]**: a modelling choice of this repository; listed with a sensitivity range in DOSSIER section 8.2.

All web sources were accessed on 10 Nov 2026.

## Systems engineering

- **[W]** C. S. Wasson, *System Engineering Analysis, Design, and Development: Concepts, Principles,
  and Practices*, 2nd ed., Wiley, 2016. **[read]**, ch. 4-7, 13, 19-22, 26-28, 31-34. Reading notes
  with printed and PDF page numbers: `wasson_extract_ch04-22.md`, `wasson_extract_ch26-34.md`.

## Cord

- **[M1]** Dipped cord-fabric product table (nylon 6.6 constructions), en.texxcore.com/products/dipped-cord-fabrics. **[read]**
  - 1400 dtex x1x2: breaking strength >= 206 N, elongation at break 22 +- 2 %, elongation at 20 N
    3.5 +- 1.5 %, at 39 N 6.5 +- 1.5 %, thickness 0.63 +- 0.03 mm.
  - 940 dtex x1x2: >= 129-132 N; 1880 dtex x1x2: >= 250 N (not used).
- **[M2]** Cord-fabric data sheet of a second producer (1440 x1x2: minimum breaking strength about 206-211 N,
  thickness 0.62-0.66 mm). **[abstract]**, used only as a cross-check of [M1].
- **[T1]** Polyamide 6.6 fibre density 1.14 g/cm3. **[std]** (any polymer handbook).
- **[T2]** ASTM D885, *Standard Test Methods for Tire Cords, Tire Cord Fabrics, and Industrial Filament
  Yarns Made from Manufactured Organic-Base Fibers*. **[std]** Test method behind [M1]; the gauge length
  of 250 mm used for the Weibull reference length is an order of magnitude, not a quoted clause.
- **[L1]** D. Tasche, "Risk contributions and performance measurement", 1999 (Euler allocation of a
  homogeneous risk measure). **[std]** Used for the cause attribution in `breaks.py`.

## Path friction

- **[T3]** Capstan (Euler-Eytelwein) equation T_out = T_in exp(mu theta). **[std]**
- **[F1]** "Friction characteristics of polypropylene fibers" (Istanbul Technical University research
  portal): polypropylene monofilament on a ceramic guide, mu = 0.32-0.42. **[abstract]**
- **[F2]** Fibre-on-fibre friction table, nylon on nylon 0.47 static / 0.40 kinetic (textile-study web
  page on frictional properties). **[abstract]**
- **[F3]** Study of the dynamic friction of nylon yarn on guides: mu_K approximately a power of the initial
  tension (Kanazawa institutional repository, 1981). **[abstract]** Reason the guide mu is given a spread
  and a range instead of one value.
- **[F4]** ASTM D3412, *Coefficient of Friction, Yarn to Solid Material* (capstan method). **[abstract]**
  Route to measure the plant's guides (TBD-4).

## Tension dynamics and winding

- **[K1]** H. Koc, D. Knittel, M. de Mathelin, G. Abba, "Modeling and robust control of winding systems for
  elastic webs", *IEEE Trans. Control Systems Technology* 10(2) (2002) 197-208, doi:10.1109/87.987065.
  **[abstract]**
- **[K2]** M. Vedrines, D. Knittel, "An improved friction sliding model for web handling systems",
  IFAC World Congress 2005. **[read]**, section 2, p.2: Hooke's law (eq. 1), the span equation
  L dT_k/dt = ES (V_k+1 - V_k) + T_k-1 V_k - T_k V_k+1 (eq. 2) and the roll equation
  d(J_k V_k / R_k)/dt = R_k (T_k - T_k-1) + K_k U_k - C_f (eq. 3), "both inertia J_k and radius R_k of
  unwinder and winder are time dependent"; section 3: tension gain inversely proportional to the radius
  (eq. 5) and gain scheduling by the radius; section 4: exponential (capstan-type) tension over a wrapped
  roll (eq. 12). `sim.span_rate` reduces to eq. 2 to first order in the strain
  (`tests/test_physics.py::test_span_rate_reduces_to_koc_equation_for_one_segment`).
- **[H1]** Z. Hakiel, "Nonlinear model for wound roll stresses", *Tappi Journal* 70 (1987) 113-117.
  **[abstract]** Not implemented: it needs the radial modulus of the wound green strip (TBD-9).
- **[E1]** EN 60204-1, *Safety of machinery - Electrical equipment of machines*, stop categories 0, 1, 2.
  **[std]**

## Rubberising template

- **[R1]** Y.-S. Ha, J.-R. Cho, T.-H. Kim, J.-H. Kim, "Finite element analysis of rubber extrusion forming
  process", KSME conference, 2007, Table 1. **[read]** (via the author's extruder-pressure-fill-estimator
  project): compound w6043, k = 0.9881e6, n = 0.2226, temperature coefficient 0.8917e-2, reference 363 K;
  units assumed SI.
- **[R2]** Brzoskowski et al., *International Polymer Processing* 2 (1987), doi:10.1515/ipp-1987-0004, and
  J. L. White, *Rubber Processing*, Hanser, 1995: filled rubber compounds slip at the wall. **[abstract]**/**[std]**
  Basis for the slip factor, whose value is assumed.
- **[R3]** Z. Tadmor, C. G. Gogos, *Principles of Polymer Processing*, 2nd ed., Wiley, 2006, wire-coating
  analysis (drag of a moving wire through a die land). **[std]**

## Brakes and drives

- **[B1]** Static friction of brake linings exceeds kinetic friction (breakaway). **[std]** Ratio assumed.
- **[B2]** Magnetic-particle brake product pages of a US brake maker (B5Z ... B35): B35 torque range
  0.07-3.95 N m, max 1800 rpm, slip heat 30 W; torque proportional to coil current, "brakes exhibit
  hysteresis" (FAQ). **[read]** B15 data-sheet snippet "unforced 25, forced 14" response (units ms
  inferred). **[abstract]**
- **[B3]** Hysteresis brake HB-140 table: nominal 140 oz-in, drag torque de-energised 0.70 (units inferred
  oz-in, i.e. 0.5 %). **[abstract]** Basis of the drag order of magnitude.
- **[B4]** Distributor listing of a 24 V magnetic-particle brake MPB15-3-24: USD 600 each. **[read]**

## Tension measurement

- **[S1]** Online 3-roller tension sensor TS2H brochure (Electromatic / Check-Line): "ideal for wires, cables,
  tirecord", ranges 0-1000 g ... 0-50 kg, accuracy +-1 % FS, damping 30 Hz, temperature drift < +-0.1 % FS/degC,
  measuring-roller deflection 0.5 mm max, outer roller spacing 100 mm up to 10 kg, 0-1 V / 0-10 V / 4-20 mA.
  **[read]** No price published (quote only), so the sensor price is assumed.
- **[S2]** Same vendor's 3-roller sensor overview: model TE-24 "tire cord ... high-impact loading",
  hardened-steel rollers. **[read]**

## PLC

- **[P1]** Siemens data sheet 6AG1513-1AL02-2AB0 (based on 6ES7513-1AL02-0AB0), CPU processing times:
  48 ns per word operation, 64 ns per fixed-point operation, 256 ns per floating-point operation.
  **[read]** (via the author's extruder-pressure-fill-estimator project).
- **[P2]** Siemens TIA Portal V18, STEP 7 Professional; compile results through TIA Openness on this PC.
