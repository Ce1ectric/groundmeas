"""Asset-management statistics over all evaluated towers (the ``stats`` step).

Aggregates every per-tower JSON written by the ``calc`` step and renders a four-page
HTML/PDF report: distributions of earth potential rise (U_E) and touch voltage
(U_T), limit-value exceedances per line, correlations and a list of all towers
above the permissible touch voltage.

!!! note
    The report texts are currently German only.
"""

from __future__ import annotations

import glob
import json
import logging
import os
from typing import Any

import matplotlib as mpl
import numpy as np
import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape
from matplotlib.figure import Figure

from .config import read_config
from .pdf import TEMPLATE_DIR, generate_pdf

__all__ = ["build_context", "generate_asset_report", "load_dataframe", "make_plots"]

logger = logging.getLogger(__name__)

_ACCENT = "#1f4e79"
_RED = "#c0392b"
_GREY = "#7f7f7f"
_STYLE: dict[Any, Any] = {"font.size": 12}

DEFAULT_FAULT_CURRENT_KA = 12.0
"""Fault current in kA that marks towers evaluated with the conservative default.

The default of a low-impedance earthed network is used when no short-circuit
data are available. The JSON results do not record the source of the fault
current, so the marker is a fixed value.
"""


def _num(value: Any) -> float:
    return (
        float(value)
        if isinstance(value, (int, float)) and not isinstance(value, bool)
        else np.nan
    )


def load_dataframe(
    json_dir: str, default_fault_current_kA: float = DEFAULT_FAULT_CURRENT_KA
) -> pd.DataFrame:
    """Load every per-tower JSON in ``json_dir`` into a tidy data frame.

    Parameters
    ----------
    json_dir : str
        Folder with the results of the ``calc`` step.
    default_fault_current_kA : float, optional
        Fault current used for towers without short-circuit data; such towers
        are flagged in the column ``default_ik``.

    Returns
    -------
    pandas.DataFrame
        Columns ``Leitung``, ``Mast``, ``ZE``, ``RA``, ``UT``, ``Ik``, ``r``,
        ``UD``, ``UE_kV``, ``UT_zu_hoch`` and ``default_ik``.
    """
    rows = []
    for path in sorted(glob.glob(os.path.join(json_dir, "*.json"))):
        try:
            with open(path, encoding="utf-8-sig") as file:
                data = json.load(file)
        except (ValueError, OSError):
            continue
        if not isinstance(data, dict) or "Leitung" not in data:
            continue
        ze, ra, ut = (
            _num(data.get("ZE_62_Ohm")),
            _num(data.get("RA_62_Ohm")),
            _num(data.get("UT_max_Messung_V")),
        )
        ik, red, ud = (
            _num(data.get("Ik_kA")),
            _num(data.get("r_pu")),
            _num(data.get("UD_V")),
        )
        ue = ik * red * ze if not np.isnan(ze * ik * red) else np.nan
        rows.append(
            {
                "Leitung": str(data.get("Leitung", "")),
                "Mast": str(data.get("Mast", "")),
                "ZE": ze,
                "RA": ra,
                "UT": ut,
                "Ik": ik,
                "r": red,
                "UD": ud,
                "UE_kV": ue,
                "UT_zu_hoch": (
                    bool(ut > ud) if not (np.isnan(ut) or np.isnan(ud)) else False
                ),
                "default_ik": bool(
                    not np.isnan(ik) and abs(ik - default_fault_current_kA) < 1e-6
                ),
            }
        )
    return pd.DataFrame(rows)


def _fmt(series: pd.Series) -> dict[str, str]:
    s = series.dropna()
    if s.empty:
        return dict.fromkeys(("min", "median", "mean", "p95", "max"), "-")
    return {
        "min": f"{s.min():.1f}",
        "median": f"{s.median():.1f}",
        "mean": f"{s.mean():.1f}",
        "p95": f"{s.quantile(0.95):.1f}",
        "max": f"{s.max():.1f}",
    }


def _save(fig: Figure, path: str) -> str:
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    return os.path.basename(path)


def make_plots(df: pd.DataFrame, plots_dir: str) -> dict[str, str]:
    """Draw the diagrams of the report.

    Parameters
    ----------
    df : pandas.DataFrame
        Output of `load_dataframe`.
    plots_dir : str
        Folder for the PNG files (also the folder of the HTML report).

    Returns
    -------
    dict
        File names of the diagrams by key (``hist_ut``, ``hist_ue``, ``exceed``,
        ``corr``, ``scatter``).
    """
    os.makedirs(plots_dir, exist_ok=True)
    p: dict[str, str] = {}
    with mpl.rc_context(_STYLE):
        # U_T histogram with permissible-voltage marker
        fig = Figure(figsize=(8, 3.6))
        ax = fig.subplots()
        ut = df["UT"].dropna()
        ax.hist(ut, bins=20, color=_ACCENT, alpha=0.85, edgecolor="white")
        ud_typ = df["UD"].dropna().median() if not df["UD"].dropna().empty else None
        if ud_typ:
            ax.axvline(
                ud_typ,
                color=_RED,
                linestyle="--",
                linewidth=1.6,
                label=f"zul. U_T (UD = {ud_typ:.0f} V)",
            )
            ax.legend(fontsize=10)
        ax.set_xlabel("Berührungsspannung U_T in V")
        ax.set_ylabel("Anzahl Masten")
        p["hist_ut"] = _save(fig, os.path.join(plots_dir, "hist_ut.png"))

        # U_E histogram
        fig = Figure(figsize=(8, 3.6))
        ax = fig.subplots()
        ue = df["UE_kV"].dropna()
        clip = float(ue.quantile(0.97)) if not ue.empty else 1.0
        ax.hist(
            ue.clip(upper=clip), bins=20, color=_GREY, alpha=0.85, edgecolor="white"
        )
        ax.set_xlabel(
            "Erdungsspannung U_E in kV  (oberhalb des 97-%-Werts zusammengefasst)"
        )
        ax.set_ylabel("Anzahl Masten")
        p["hist_ue"] = _save(fig, os.path.join(plots_dir, "hist_ue.png"))

        # exceedance rate per line
        g = df.groupby("Leitung").agg(n=("UT", "size"), hi=("UT_zu_hoch", "sum"))
        g["rate"] = 100 * g["hi"] / g["n"]
        g = g.sort_values("rate", ascending=True)
        fig = Figure(figsize=(8, 4.2))
        ax = fig.subplots()
        colors = [_RED if r >= 40 else (_ACCENT if r > 0 else _GREY) for r in g["rate"]]
        ax.barh(g.index, g["rate"], color=colors)
        for y, (rate, n, hi) in enumerate(zip(g["rate"], g["n"], g["hi"], strict=True)):
            ax.text(rate + 1, y, f"{hi}/{n}", va="center", fontsize=9)
        ax.set_xlabel("Anteil Masten mit U_T > zulässig in %")
        ax.set_xlim(0, max(100, g["rate"].max() * 1.15))
        p["exceed"] = _save(fig, os.path.join(plots_dir, "exceed_by_line.png"))

        # correlation heatmap
        cols = ["UT", "UE_kV", "ZE", "RA", "Ik"]
        labels = ["U_T", "U_E", "Z_E", "R_A", "I_k"]
        corr = df[cols].corr()
        fig = Figure(figsize=(4.6, 4.2))
        ax = fig.subplots()
        im = ax.imshow(corr, vmin=-1, vmax=1, cmap="RdBu_r")
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels)
        ax.set_yticks(range(len(labels)))
        ax.set_yticklabels(labels)
        values = corr.to_numpy(dtype=float)
        for i in range(len(labels)):
            for j in range(len(labels)):
                ax.text(
                    j,
                    i,
                    f"{values[i, j]:.2f}",
                    ha="center",
                    va="center",
                    color="white" if abs(values[i, j]) > 0.5 else "black",
                    fontsize=10,
                )
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        p["corr"] = _save(fig, os.path.join(plots_dir, "corr.png"))

        # scatter U_T vs Z_E and U_T vs I_k
        fig = Figure(figsize=(8, 3.4))
        axes = fig.subplots(1, 2)
        axes[0].scatter(df["ZE"], df["UT"], s=18, color=_ACCENT, alpha=0.7)
        axes[0].set_xlabel("Z_E in Ohm")
        axes[0].set_ylabel("U_T in V")
        axes[0].set_title("U_T vs. Z_E", fontsize=11)
        axes[1].scatter(df["Ik"], df["UT"], s=18, color=_ACCENT, alpha=0.7)
        axes[1].set_xlabel("I_k in kA")
        axes[1].set_ylabel("U_T in V")
        axes[1].set_title("U_T vs. I_k", fontsize=11)
        for a in axes:
            a.grid(True, alpha=0.3)
        p["scatter"] = _save(fig, os.path.join(plots_dir, "scatter.png"))
    return p


def build_context(
    df: pd.DataFrame,
    plots: dict[str, str],
    default_fault_current_kA: float = DEFAULT_FAULT_CURRENT_KA,
) -> dict[str, Any]:
    """Compute key figures, tables and text blocks of the report.

    Parameters
    ----------
    df : pandas.DataFrame
        Output of `load_dataframe`.
    plots : dict
        Output of `make_plots`.
    default_fault_current_kA : float, optional
        Fault current used for towers without short-circuit data.

    Returns
    -------
    dict
        Template context for ``templates/stats.html``.
    """
    total = len(df)
    hi = int(df["UT_zu_hoch"].sum())
    g = (
        df.groupby("Leitung")
        .agg(
            n=("UT", "size"),
            hi=("UT_zu_hoch", "sum"),
            ut_med=("UT", "median"),
            ut_max=("UT", "max"),
            ue_med=("UE_kV", "median"),
            ze_med=("ZE", "median"),
            default=("default_ik", "sum"),
        )
        .reset_index()
    )
    g["rate"] = (100 * g["hi"] / g["n"]).round(0).astype(int)
    g = g.sort_values("rate", ascending=False)
    line_rows = [
        {
            "line": r["Leitung"],
            "n": int(r["n"]),
            "hi": int(r["hi"]),
            "rate": int(r["rate"]),
            "ut_med": f"{r['ut_med']:.0f}",
            "ut_max": f"{r['ut_max']:.0f}",
            "ue_med": f"{r['ue_med']:.1f}",
            "ze_med": f"{r['ze_med']:.2f}",
            "default": int(r["default"]),
        }
        for _, r in g.iterrows()
    ]

    def _f(value: float, digits: int) -> str:
        return f"{value:.{digits}f}" if not np.isnan(value) else "-"

    top = df.dropna(subset=["UT"]).sort_values("UT", ascending=False).head(12)
    top_rows = [
        {
            "line": r["Leitung"],
            "mast": r["Mast"],
            "ut": f"{r['UT']:.0f}",
            "ud": _f(r["UD"], 0),
            "ue": _f(r["UE_kV"], 1),
            "ze": _f(r["ZE"], 2),
            "default": "ja" if r["default_ik"] else "",
        }
        for _, r in top.iterrows()
    ]

    # complete list of towers above the permissible touch voltage, by U_T
    fails = (
        df[df["UT_zu_hoch"]].dropna(subset=["UT"]).sort_values("UT", ascending=False)
    )
    fail_rows = [
        {
            "line": r["Leitung"],
            "mast": r["Mast"],
            "ut": f"{r['UT']:.0f}",
            "ud": _f(r["UD"], 0),
            "ratio": (
                f"{r['UT'] / r['UD']:.1f}"
                if (not np.isnan(r["UD"]) and r["UD"])
                else "-"
            ),
            "ue": _f(r["UE_kV"], 1),
            "ze": _f(r["ZE"], 2),
            "ik": _f(r["Ik"], 1),
            "default": "ja" if r["default_ik"] else "",
        }
        for _, r in fails.iterrows()
    ]

    corr_ut_ze = df[["UT", "ZE"]].corr().iloc[0, 1]
    corr_ut_ik = df[["UT", "Ik"]].corr().iloc[0, 1]
    corr_ze_ra = df[["ZE", "RA"]].corr().iloc[0, 1]
    n_default = int(df["default_ik"].sum())
    default_lines = sorted(df.loc[df["default_ik"], "Leitung"].unique())
    worst = g.iloc[0] if not g.empty else None
    default_text = f"{default_fault_current_kA:g}".replace(".", ",")

    insights = [
        f"Von {total} ausgewerteten Masten überschreiten {hi} ({100 * hi // total} %) die zulässige "
        f"Berührungsspannung U_T. Der Median liegt bei {df['UT'].median():.0f} V, der 95-%-Wert bei "
        f"{df['UT'].quantile(0.95):.0f} V, das Maximum bei {df['UT'].max():.0f} V.",
    ]
    if worst is not None:
        insights.append(
            f"Auffälligste Leitung ist {worst['Leitung']} mit {int(worst['rate'])} % Überschreitungen "
            f"({int(worst['hi'])}/{int(worst['n'])}); unauffällige Leitungen weisen 0 Überschreitungen "
            "auf. Das Risiko ist also stark leitungs- bzw. standortabhängig."
        )
    insights += [
        f"Die Berührungsspannung korreliert praktisch nicht mit der Erdungsimpedanz (r = {corr_ut_ze:.2f}) "
        f"oder der Erdungsspannung — eine niedrige Z_E garantiert keine niedrige U_T. Es besteht nur ein "
        f"schwacher Zusammenhang mit dem Fehlerstrom (r = {corr_ut_ik:.2f}); Z_E und R_A hängen mäßig "
        f"zusammen (r = {corr_ze_ra:.2f}).",
        f"Einschränkung: {n_default} Masten (v. a. Leitungen {', '.join(default_lines[:4])}) wurden mangels "
        f"Kurzschlussdaten mit dem {default_text}-kA-Default gerechnet. Ihre U_T-Werte sind konservativ "
        "überschätzt; die dortigen Überschreitungsquoten sind erst nach Ergänzung der Kurzschlussdaten "
        "belastbar.",
    ]
    default_focus = list(
        df.loc[df["default_ik"]]
        .groupby("Leitung")
        .size()
        .sort_values(ascending=False)
        .index[:3]
    )
    focus_lines = [
        r["line"]
        for r in sorted(line_rows, key=lambda x: x["hi"], reverse=True)
        if r["hi"] > 0
    ][:3]
    recommendations = [
        "Kurzschlussdaten für die Leitungen mit Default-Fehlerstrom"
        + (f" (insb. {', '.join(default_focus)})" if default_focus else "")
        + " ergänzen, damit deren Bewertung belastbar wird.",
        "Masten mit den höchsten Berührungsspannungen priorisiert prüfen (Top-Liste auf der letzten Seite); "
        + (
            f"die meisten Grenzwertüberschreitungen entfallen auf {', '.join(focus_lines)}."
            if focus_lines
            else ""
        ),
        "Da U_T nicht aus Z_E folgt, bei kritischen Standorten weiterhin die direkte "
        "Berührungsspannungsmessung als maßgeblichen Nachweis heranziehen (nicht allein Z_E).",
    ]

    summary = {
        "total": total,
        "lines": df["Leitung"].nunique(),
        "hi": hi,
        "hi_pct": 100 * hi // total if total else 0,
        "ut": _fmt(df["UT"]),
        "ue": _fmt(df["UE_kV"]),
        "ze": _fmt(df["ZE"]),
        "ra": _fmt(df["RA"]),
        "n_default": n_default,
    }
    return {
        "default_kA_text": default_text,
        "summary": summary,
        "line_rows": line_rows,
        "top_rows": top_rows,
        "fail_rows": fail_rows,
        "insights": insights,
        "recommendations": recommendations,
        "plots": plots,
    }


def generate_asset_report(
    config_path: str | os.PathLike[str] | None = None,
    output_dir: str | None = None,
    print_pdf: bool = True,
) -> tuple[str, str]:
    """Create the statistics report of a campaign.

    Parameters
    ----------
    config_path : str, os.PathLike or None, optional
        Configuration file.
    output_dir : str or None, optional
        Output folder; default ``<json_export_path>/Statistik``.
    print_pdf : bool, optional
        Also create the PDF.

    Returns
    -------
    tuple of (str, str)
        Paths of the HTML and of the (possibly not created) PDF file.

    Raises
    ------
    ValueError
        If no evaluated towers are found.
    """
    config = read_config(config_path)
    json_dir = config["json_export_path"]
    out = output_dir or os.path.join(json_dir, "Statistik")
    os.makedirs(out, exist_ok=True)

    df = load_dataframe(json_dir)
    if df.empty:
        raise ValueError(
            f"No JSON files found in {json_dir}. Run the calc step first "
            "(gm-cli towers run --calc)."
        )

    plots = make_plots(df, out)
    context = build_context(df, plots)
    context["company"] = config.get("evaluation_company", "")

    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR), autoescape=select_autoescape(["html"])
    )
    env.globals["comma"] = lambda x: str(x).replace(".", ",")
    html = env.get_template("stats.html").render(**context)

    html_path = os.path.join(out, "Asset_Auswertung.html")
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(html)

    pdf_path = os.path.join(out, "Asset_Auswertung.pdf")
    if print_pdf:
        generate_pdf(html_path, pdf_path, language="de")
    logger.info("Statistics report written: %s", html_path)
    return html_path, pdf_path
