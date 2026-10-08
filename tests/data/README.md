# Test fixtures

All files in this folder are **synthetic**. They contain no real measurement
values and no identifiers of real installations or instruments.

| File | Content |
|---|---|
| `compano_fall_of_potential.xml` | Structure of an OMICRON COMPANO 100 XML export (firmware 2.40) with all measured values replaced by a hemispherical-electrode model: true earthing resistance R = 0.40 Ω, electrode radius a = 3 m, current electrode at D = 100 m, probe distances 1, 5, 10, 20, 30, 40, 60 m from the electrode surface, injected current 54/55 mA at 30/70 Hz, footing current share 0.5, step/touch measuring currents 53/54 mA. Serial number, hash and time stamps are blanked. |
| `hgt1_step_touch_report.txt` | OMICRON HGT1 *StepTouch* report in the instrument's format (tab separated, CRLF line endings): two measuring points (MAST, ZAUN), each read with termination `1k` and `2x1k` at 30 Hz and 70 Hz. |

Further test data (complete tower campaigns, Excel workbooks, defective
files) are generated at test time with `groundmeas.towers.demo` and helpers in
the test modules.

The files must stay byte-exact (see `.gitattributes`): the HGT1 report keeps
its Windows line endings on every platform. `*.xml` is ignored by
`.gitignore` except in this folder.
