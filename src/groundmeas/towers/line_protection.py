"""Position-dependent fault clearing time per tower (line protection).

Earth faults on overhead lines in solidly or low-impedance earthed networks
are cleared by distance protection at both line ends. Zone 1 of each relay
reaches about 85 % of the line, so only faults in the middle section are
tripped instantaneously from *both* sides. Near either end the remote relay
trips in its delayed zone 2, which determines the effective clearing time:

```text
   0 % ... < 16 %  ->  t_Endbereich_s   (e.g. 0.4 s, remote end in zone 2)
  16 % ...   84 %  ->  t_Schnellzeit_s  (e.g. 0.1 s, both ends in zone 1)
> 84 % ...  100 %  ->  t_Endbereich_s   (e.g. 0.4 s)
```

The bands are read per line from the sheet ``Leitungsschutz`` of the
short-circuit workbook (configuration key ``sc_current_data_path``). Positions
between the integer bands (e.g. 15.5 % or 84.5 %) are deliberately assigned to
the end zone: the longer clearing time gives the lower permissible touch
voltage, i.e. the conservative result.

The position of a tower is derived from its number, exactly as in the
short-circuit line model (uniform span length):

```text
position = (tower - Mast_Anfang) / (Mast_Ende - Mast_Anfang) * 100 %
```

The same sheet can also hold flat values for lines without network data, e.g.
a compensated network with 200 A residual earth-fault current and a clearing
time above 10 s (``t_Schnellzeit_s = t_Endbereich_s = 10``).

Sheet columns (German names, as used in existing workbooks):

| Column | Meaning |
| --- | --- |
| ``Leitung`` | line identifier (required) |
| ``Netzform`` | network earthing, free text (e.g. "niederohmig") |
| ``Schutzkonzept`` | protection concept, free text |
| ``Mast_Anfang``, ``Mast_Ende`` | first / last tower number (0 % / 100 %) |
| ``Schnellzeit_von_Prozent`` | start of the instantaneous zone (default 16) |
| ``Schnellzeit_bis_Prozent`` | end of the instantaneous zone (default 84) |
| ``t_Schnellzeit_s`` | clearing time in the middle section (required) |
| ``t_Endbereich_s`` | clearing time near the line ends (required) |
| ``Fehlerstrom_pauschal_kA`` | optional flat fault current |
| ``Reduktionsfaktor_pauschal`` | optional flat reduction factor |
| ``Bemerkung`` | remark, free text |
"""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass
from typing import Any

import pandas as pd

from .i18n import format_number, translate
from .naming import tower_number

__all__ = [
    "COLUMNS",
    "REQUIRED",
    "SHEET_NAME_DEFAULT",
    "LineProtectionTable",
    "ProtectionResult",
    "tower_number",
]

logger = logging.getLogger(__name__)

SHEET_NAME_DEFAULT = "Leitungsschutz"

COLUMNS = [
    "Leitung",
    "Netzform",
    "Schutzkonzept",
    "Mast_Anfang",
    "Mast_Ende",
    "Schnellzeit_von_Prozent",
    "Schnellzeit_bis_Prozent",
    "t_Schnellzeit_s",
    "t_Endbereich_s",
    "Fehlerstrom_pauschal_kA",
    "Reduktionsfaktor_pauschal",
    "Bemerkung",
]
REQUIRED = ["Leitung", "t_Schnellzeit_s", "t_Endbereich_s"]

# Zone names stored in ``ProtectionResult.zone`` (German, also written to the
# grid-data workbook).
ZONE_FAST = "Schnellzeit"
"""Tower in the middle section, cleared in zone 1 from both ends."""
ZONE_END = "Endbereich"
"""Tower near a line end (or outside ``Mast_Anfang``..``Mast_Ende``); the remote end
clears in its delayed zone 2."""
ZONE_FLAT = "pauschal"
"""Both clearing times are equal, one flat clearing time applies to the whole line."""
ZONE_UNKNOWN = "unbekannt"
"""Position on the line unknown, the longer (conservative) clearing time is used."""


def _text(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return str(value).strip()


def _num(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number


@dataclass
class ProtectionResult:
    """Clearing time and optional flat grid values for one tower.

    Attributes
    ----------
    tripping_time_s : float
        Fault clearing time in s.
    position_percent : float or None
        Position of the tower on the line in percent (``None`` if unknown).
    zone : str
        ``"Schnellzeit"`` (instantaneous from both ends), ``"Endbereich"`` (end
        zone), ``"pauschal"`` (flat value for the whole line) or
        ``"unbekannt"`` (position unknown).
    network : str
        Network earthing from the sheet (free text).
    fault_current_A : float or None
        Flat fault current in A, if given.
    reduction_factor : float or None
        Flat reduction factor, if given.
    note : str
        Remark from the sheet.
    """

    tripping_time_s: float
    position_percent: float | None
    zone: str
    network: str = ""
    fault_current_A: float | None = None
    reduction_factor: float | None = None
    note: str = ""

    def hint(self, language: str = "en") -> str:
        """Short explanation of the clearing time for protocols and summaries.

        Parameters
        ----------
        language : str, optional
            ``"en"`` (default) or ``"de"``.

        Returns
        -------
        str
            E.g. ``"Position 19.7 % of the line length: instantaneous tripping
            from both line ends (distance protection)"``.
        """
        position = (
            format_number(f"{self.position_percent:.1f}", language)
            if self.position_percent is not None
            else ""
        )
        if self.zone == ZONE_FAST:
            return translate("hint_fast", language, position=position)
        if self.zone == ZONE_END:
            return translate("hint_end", language, position=position)
        if self.zone == ZONE_FLAT:
            return translate("hint_flat", language)
        return translate("hint_unknown", language)


class LineProtectionTable:
    """Per-line protection settings read from the ``Leitungsschutz`` sheet.

    Parameters
    ----------
    table : pandas.DataFrame or None, optional
        Sheet content with the columns `COLUMNS`; ``None`` creates an
        empty table (no line listed).
    """

    def __init__(self, table: pd.DataFrame | None = None):
        self.table = table if table is not None else pd.DataFrame(columns=COLUMNS)
        self._rows: dict[str, pd.Series] = {}
        for _, row in self.table.iterrows():
            line = str(row["Leitung"]).strip()
            if line and line.lower() != "nan":
                self._rows[line] = row

    @classmethod
    def from_excel(
        cls, path: str | None, sheet_name: str = SHEET_NAME_DEFAULT
    ) -> LineProtectionTable:
        """Read the sheet from a workbook.

        Parameters
        ----------
        path : str or None
            Workbook path. A missing file or sheet gives an empty table.
        sheet_name : str, optional
            Sheet name, by default ``"Leitungsschutz"``.

        Returns
        -------
        LineProtectionTable
            The table (possibly empty).

        Raises
        ------
        ValueError
            If the sheet lacks one of the `REQUIRED` columns.
        """
        if not path or not os.path.exists(path):
            return cls()
        try:
            with pd.ExcelFile(path, engine="openpyxl") as workbook:
                sheets = workbook.sheet_names
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Line protection: cannot open %s: %s", path, exc)
            return cls()
        if sheet_name not in sheets:
            return cls()
        df = pd.read_excel(path, sheet_name=sheet_name, engine="openpyxl")
        missing = [c for c in REQUIRED if c not in df.columns]
        if missing:
            raise ValueError(
                f"Sheet '{sheet_name}' in {path} misses the columns {missing}"
            )
        for col in COLUMNS:
            if col not in df.columns:
                df[col] = None
        df = df[df["Leitung"].notna()]
        return cls(df)

    def __contains__(self, line_number: object) -> bool:
        return str(line_number).strip() in self._rows

    def lines(self) -> list[str]:
        """Return the listed line identifiers.

        Returns
        -------
        list of str
            Line identifiers in sheet order.
        """
        return list(self._rows)

    def position_percent(self, line_number: object, tower: object) -> float | None:
        """Position of a tower on its line.

        Parameters
        ----------
        line_number : object
            Line identifier.
        tower : object
            Tower identifier (numeric part is used).

        Returns
        -------
        float or None
            Position in percent, or ``None`` if the line or its tower range is
            unknown.
        """
        row = self._rows.get(str(line_number).strip())
        if row is None:
            return None
        first, last = _num(row.get("Mast_Anfang")), _num(row.get("Mast_Ende"))
        number = tower_number(tower)
        if first is None or last is None or number is None or last == first:
            return None
        return (number - first) / (last - first) * 100.0

    def lookup(self, line_number: object, tower: object) -> ProtectionResult | None:
        """Return the clearing time for a tower.

        Parameters
        ----------
        line_number : object
            Line identifier.
        tower : object
            Tower identifier.

        Returns
        -------
        ProtectionResult or None
            ``None`` if the line is not listed.

        Raises
        ------
        ValueError
            If ``t_Schnellzeit_s`` or ``t_Endbereich_s`` is missing for the line.
        """
        row = self._rows.get(str(line_number).strip())
        if row is None:
            return None

        t_fast = _num(row.get("t_Schnellzeit_s"))
        t_end = _num(row.get("t_Endbereich_s"))
        if t_fast is None or t_end is None:
            raise ValueError(
                f"Leitungsschutz: t_Schnellzeit_s / t_Endbereich_s missing for line {line_number}"
            )

        ik = _num(row.get("Fehlerstrom_pauschal_kA"))
        red = _num(row.get("Reduktionsfaktor_pauschal"))
        common: dict[str, Any] = {
            "network": _text(row.get("Netzform")),
            "fault_current_A": ik * 1e3 if ik is not None else None,
            "reduction_factor": red,
            "note": _text(row.get("Bemerkung")),
        }

        position = self.position_percent(line_number, tower)
        if math.isclose(t_fast, t_end):
            return ProtectionResult(t_end, position, ZONE_FLAT, **common)
        if position is None:
            # position unknown -> longer (conservative) clearing time
            return ProtectionResult(max(t_fast, t_end), None, ZONE_UNKNOWN, **common)

        lower = _num(row.get("Schnellzeit_von_Prozent"))
        upper = _num(row.get("Schnellzeit_bis_Prozent"))
        lower = 16.0 if lower is None else lower
        upper = 84.0 if upper is None else upper

        if position < 0.0 or position > 100.0:
            logger.warning(
                "Leitungsschutz: tower %s of line %s lies outside Mast_Anfang..Mast_Ende "
                "(%.1f %%); end zone assumed.",
                tower,
                line_number,
                position,
            )
            return ProtectionResult(t_end, position, ZONE_END, **common)
        if lower - 1e-9 <= position <= upper + 1e-9:
            return ProtectionResult(t_fast, position, ZONE_FAST, **common)
        return ProtectionResult(t_end, position, ZONE_END, **common)
