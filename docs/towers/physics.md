# Physical background

This page explains the physics behind the evaluation: why the earthing of an
overhead-line tower is measured, how the instruments measure, and how the
tool turns the readings into the quantities that are assessed. The decision
rules themselves are summarised in [Assessment procedure](assessment.md).

## Why tower earthing matters

During a single-phase earth fault on an overhead line (for example a
flashover across an insulator), the fault current flows from the phase
conductor into the tower. Part of it returns through the **earth wires**
(shield wires) to the neighbouring towers and substations, the rest – the
**earth current** $I_E$ – flows through the tower earthing into the soil:

$$
I_E = r \cdot I_k
$$

$I_k$ is the single-phase short-circuit current at the fault location and $r$
the **reduction factor** of the earth wire ($r = 1$ without earth wire; the
better the earth wire conducts and couples to the phase conductor, the
smaller $r$).

The earth current raises the potential of the tower and of the soil around it
relative to remote earth. This **earth potential rise** is

$$
U_E = I_E \cdot Z_E
$$

with the **earthing impedance** $Z_E$ of the tower. A person touching the tower
while standing on the soil a metre away bridges a part of $U_E$, the **touch
voltage** $U_T$; a person walking near the tower bridges the **step voltage**
$U_S$ between the feet. Because the soil potential drops with the distance to
the tower, $U_T$ is always a fraction of $U_E$.

The permissible touch voltage depends on how long the current flows through
the body, i.e. on the **fault clearing time** $t_F$ of the protection (see
[below](#permissible-touch-voltage)).

## Measuring the earthing impedance

### The fall-of-potential method

The OMICRON COMPANO 100 injects a test current $I$ between the tower earthing
and an auxiliary **current electrode** placed at a distance $D$ (typically
100 m or more). A **potential probe** is moved step by step from the tower
towards the current electrode; at every distance $x$ the instrument records the
voltage $U(x)$ between tower and probe. The ratio

$$
Z(x) = \left| \frac{U(x)}{I} \right|
$$

is the *fall-of-potential profile*. To suppress interference from the
power-frequency stray currents in the soil, the measurement is made at
frequencies next to the power frequency (for example 30 Hz and 70 Hz).

Close to the tower $Z(x)$ rises steeply, far from both electrodes it flattens
(the probe is "at remote earth" with respect to the tower), and near the
current electrode it rises again. The earthing impedance is the value of the
flat part – which, for a finite distance $D$, has to be identified carefully.

### The 62 % method

For a hemispherical electrode of radius $a$ in homogeneous soil of resistivity
$\rho$ the potential at a distance $p$ from its centre is
$\varphi(p) = \rho I / (2 \pi p)$. With the return current $-I$ at the current
electrode (distance $D$ from the centre) the probe at distance $p$ measures

$$
Z(p) = \frac{\rho}{2 \pi} \left( \frac{1}{a} - \frac{1}{D}
       - \frac{1}{p} + \frac{1}{D - p} \right)
     = R \, a \left( \frac{1}{a} - \frac{1}{D}
       - \frac{1}{p} + \frac{1}{D - p} \right)
$$

where $R = \rho / (2 \pi a)$ is the true earthing resistance. $Z(p)$ equals $R$
when the two "error terms" cancel:

$$
\frac{1}{D - p} = \frac{1}{D} + \frac{1}{p}
\quad\Longleftrightarrow\quad
p^2 + D\,p - D^2 = 0
\quad\Longleftrightarrow\quad
p = \frac{\sqrt{5} - 1}{2}\,D \approx 0.618\,D .
$$

This is the classical **62 % rule** (Curdts 1958, Tagg 1964): the true
resistance is read with the potential probe at 61.8 % of the distance to the
current electrode, measured from the electrical centre of the earthing
system.

The tool evaluates every profile as follows
(`GroundingSystemAnalysis.get_62_percentage_value`):

1. $d_{62} = 0.62 \cdot D$, with $D$ the distance tower – current electrode
   from the measurement description (`Entfernung_Hilfserder_m`).
2. $Z(d_{62})$ is interpolated linearly between the three measuring points
   closest to $d_{62}$ (extrapolated if $d_{62}$ lies outside the measured
   range).
3. Two conservative corrections handle profiles that do not look like the
   textbook curve:
    - the profile ends before $d_{62}$ and its maximum is higher → the
      maximum is used;
    - a point closer to the tower than $d_{62}$ shows a higher impedance →
      that higher value is used.
4. The result is $Z_{E,62}$, the earthing impedance used for the assessment.

The same procedure is available as the pure function
`groundmeas.value_at_62_percent(distances, values, D, conservative=True)` and
for profiles stored in the database as
`distance_profile_value(..., algorithm="62_percent", conservative=True)`.
Without `conservative=True` groundmeas interpolates between the three nearest
points without extrapolation (the end value is kept) and without the
corrections of step 3.

!!! example "Check with the analytical model"

    The synthetic demo profiles are generated from the formula above, with
    the probe distances measured from the electrode surface (radius 1.5 m to
    2.5 m). The 62 % evaluation reproduces the true values with a small
    deviation to the safe side, because 62 % of $D$ from the surface lies
    slightly beyond the exact 61.8 % point from the centre:

    | Tower | true $R$ | $Z_{E,62}$ | deviation |
    | --- | --- | --- | --- |
    | 3 | 0.550 Ω | 0.552 Ω | +0.5 % |
    | 8 | 0.120 Ω | 0.121 Ω | +0.7 % |
    | 21 | 0.600 Ω | 0.602 Ω | +0.3 % |
    | 37 | 0.350 Ω | 0.352 Ω | +0.5 % |

    The test suite compares the method in addition with a least-squares fit
    of the hemisphere model and with the exact 61.8 % point.

### Earthing impedance and footing resistance

With the earth wires connected, the injected current divides: part of it
flows into the soil at the tower, the rest flows through the earth wires to
the neighbouring towers. The COMPANO export therefore contains two currents:

- the **raw output current** – the total injected current. $Z = U / I_{raw}$
  is the **earthing impedance** $Z_E$ of the tower *including* the earth-wire
  chain, i.e. the impedance that determines the earth potential rise during a
  fault;
- the **corrected output current** – the share that flows into the tower
  footing. $R_A = U / I_{corr}$ is the **footing resistance** of the tower
  alone, an indicator of the condition of the tower's own earthing.

The footing resistance at the 62 % point is obtained by scaling the maximum
footing resistance with the ratio of the impedances,
$R_{A,62} = R_{A,max} \cdot Z_{E,62} / Z_{E,max}$.

The footing resistance can also be measured with a **high-frequency earth
tester**, whose high test frequency decouples the neighbouring towers through
the inductance of the earth wire. If such a single value is given in the
measurement description and deviates by more than 20 % from the
fall-of-potential value (or if there is no profile), the protocol shows the
high-frequency value and says so. The footing resistance is reported, not
assessed.

## Touch voltage

### Measurement

While the COMPANO injects its test current $I_{meas}$ into the tower, the
OMICRON HGT1 measures the voltage between the tower (or another touchable
object: fence, gate, street light) and a test electrode placed 1 m away on
the soil. The HGT1 measures frequency-selectively at the two test frequencies
$f_1$ and $f_2$ and loads the measurement with a defined resistance
(termination):

- `1k` – 1 kΩ, representing the body impedance,
- `2x1k` – 1 kΩ plus an additional 1 kΩ in series, representing footwear and
  standing surface.

The value at the nominal frequency $f_n$ (50 Hz or 60 Hz) is interpolated
linearly:

$$
U_{f_n} = U_1 + (f_n - f_1)\,\frac{U_2 - U_1}{f_2 - f_1}
$$

### Scaling to the earth-fault current

The earthing system is linear: voltages scale with the injected current.
The touch voltage expected during an earth fault is therefore

$$
U_T = U_{T,meas} \cdot \frac{I_E}{I_{meas}}
$$

with $I_{meas}$ the mean measuring current of the step/touch test from the
COMPANO export. The tool rounds the result **up** to whole volts.

The same scaling is applied to voltages measured at a **neighbouring tower**
(`UT_<line>_<tower>-<neighbour>.txt`): they show how much of the earth
potential rise is transferred along the earth wire.

### Permissible touch voltage

The permissible touch voltage $U_{TP}$ is derived from the current that the
human body tolerates for a given duration without ventricular fibrillation
(IEC/TS 60479-1) and the body impedance. It decreases steeply with the
duration of the current flow, which equals the fault clearing time $t_F$. The
standards for high-voltage installations (EN 50522) and overhead lines
(EN 50341-1) give it as a curve over $t_F$; the tool reads the curve as a table
from the [configuration](configuration.md#touch_voltages-permissible-touch-voltage)
and interpolates linearly between its points.

## Step voltage

The step voltage over one metre is approximated from the slope of the
fall-of-potential profile, scaled to the earth current:

$$
U_S(x_i) = I_E \left| \frac{Z(x_{i+1}) - Z(x_i)}{x_{i+1} - x_i} \right|
$$

with $x_0 = 0$ and $Z(0) = 0$ at the tower; the value at the last point is
extrapolated linearly from the two preceding slopes. The step voltage is shown
for information. It is not assessed, because the permissible step voltages
are considerably higher than the touch voltages (the current path from foot
to foot does not cross the heart).

## Short-circuit current along the line

The single-phase short-circuit current depends on the fault location. For a
line fed from both ends it is modelled as the sum of the contributions of
both sources:

$$
I_k(x) = \frac{a}{b\,l\,x + c} + \frac{a}{b\,(N - x)\,l + d}
$$

| Symbol | Meaning |
| --- | --- |
| $x$ | tower index from the line start (0 … N−1) |
| $N$ | number of towers |
| $l$ | mean span length (line length / (N − 1)) |
| $a$ | driving voltage (fit parameter) |
| $b$ | line impedance per unit length (fit parameter) |
| $c$, $d$ | source impedances at both line ends (fit parameters) |

The four parameters are fitted with `scipy.optimize.curve_fit` to short-circuit
currents calculated with a network-calculation program for a few fault
locations (sheet per line in the short-circuit workbook). If the fit does not
converge, a straight line is used (one-sided infeed) and a warning is logged.
The model is a smooth interpolation between calculated values; it is only as
good as the network calculation behind it.

## Fault clearing time along the line

Earth faults on lines in solidly or low-impedance earthed networks are
cleared by distance protection at both line ends. Zone 1 of each relay covers
about 80–85 % of the line and trips without intentional delay; faults beyond
it are cleared by the delayed zone 2. A fault in the middle section is
therefore cleared quickly from both ends, a fault near one end only after the
remote relay's zone-2 delay. The tool assigns

| Position on the line | Clearing time |
| --- | --- |
| < 16 % | end-zone time `t_Endbereich_s` (e.g. 0.4 s) |
| 16 % … 84 % | instantaneous time `t_Schnellzeit_s` (e.g. 0.1 s) |
| > 84 % | end-zone time |

with configurable limits per line. The position follows from the tower
number, assuming uniform spans. Positions between the integer limits are
assigned to the end zone (the longer time is the conservative choice).

## Soil resistivity

Some towers are measured with a **Schlumberger** array: four electrodes on a
line, current injected through the outer pair, voltage measured with the
inner pair, for increasing electrode spacings. The COMPANO reports the
apparent soil resistivity $\rho_a$ for every spacing directly; the tool copies
the values and the electrode distances into the JSON file. Increasing
$\rho_a$ with increasing spacing indicates that deeper layers have a higher
resistivity.

## Assumptions and limitations

- **Linearity.** Scaling the measured values to the fault current assumes a
  linear earthing system (no soil ionisation, no saturation).
- **62 % rule.** The rule is exact for a compact electrode in homogeneous
  soil with the potential probe on the straight line towards the current
  electrode. The angle between probe and current electrode is recorded
  (`Winkel_Sonde_Hilfserder_grad`) but not used in the calculation. In
  layered soil, for extended earthing systems or with too short distances the
  profile may have no plateau; the conservative corrections and the profile
  diagram in the protocol help to recognise such cases – check them.
- **Measuring current.** The touch voltages are scaled with the mean
  measuring current of both test frequencies.
- **Interpolation to 50/60 Hz** is linear between the two test frequencies.
- **Short-circuit currents, reduction factors and clearing times** are input
  data. The results are only as good as these values.
- **Permissible touch voltage.** The curve comes from the configuration; the
  tool does not check it against a particular edition of a standard.

## References

- EN 50522:2010, *Earthing of power installations exceeding 1 kV a.c.*
- EN 50341-1:2012, *Overhead electrical lines exceeding AC 1 kV – Part 1:
  General requirements – Common specifications*, and its national normative
  aspects (EN 50341-2-x).
- IEC/TS 60479-1, *Effects of current on human beings and livestock – Part 1:
  General aspects*.
- IEEE Std 81-2012, *IEEE Guide for Measuring Earth Resistivity, Ground
  Impedance, and Earth Surface Potentials of a Grounding System*.
- E. B. Curdts, "Some of the fundamental aspects of ground resistance
  measurements", *AIEE Transactions, Part I*, vol. 77, 1958.
- G. F. Tagg, *Earth Resistances*, George Newnes, London, 1964.
- OMICRON electronics, user manuals of the COMPANO 100 and the HGT1.
