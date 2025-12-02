"""
OCR-driven import helpers for measurement data embedded in images.

Implements an offline pipeline using Tesseract (via pytesseract) and OpenCV for
basic preprocessing. The goal is to turn images containing distance/current/
voltage/impedance readings into MeasurementItem records.
"""

from __future__ import annotations

import logging
import math
import re
import os
import base64
import requests
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import cv2
import numpy as np
import pytesseract

from .db import create_item

logger = logging.getLogger(__name__)


@dataclass
class ParsedRow:
    distance_m: Optional[float] = None
    current_a: Optional[float] = None
    current_angle_deg: Optional[float] = None
    voltage_v: Optional[float] = None
    voltage_angle_deg: Optional[float] = None
    impedance_ohm: Optional[float] = None
    impedance_angle_deg: Optional[float] = None


def _normalize_number(raw: str) -> float:
    return float(raw.replace(",", "."))


def _parse_value_angle_unit(chunk: str) -> tuple[Optional[float], Optional[float], Optional[str]]:
    """
    Parse a token like '114.0 mA 0.00°' or '118.1 mΩ -136.56°'.
    Returns (value_in_si, angle_deg, unit_string) with SI scaling applied.
    """
    if not chunk:
        return None, None, None
    # split into parts: value, unit, angle
    # Accept unit immediately after number (e.g., 118.1mΩ) or separated by space
    val_unit_match = re.search(
        r"(-?\d+(?:[.,]\d+)?)(?:\s*)?([mk]?)(A|V|Ω|ohm|ohms|0|o)?",
        chunk,
        re.IGNORECASE,
    )
    angle_match = re.search(r"(-?\d+(?:[.,]\d+)?)\s*°", chunk)
    if not val_unit_match:
        return None, None, None
    raw_val = _normalize_number(val_unit_match.group(1))
    prefix = (val_unit_match.group(2) or "").lower()
    unit_base = val_unit_match.group(3) or ""
    scale = 1.0
    if prefix == "m":
        scale = 1e-3
    if prefix == "k":
        scale = 1e3
    if unit_base in {"0", "o"}:
        unit_base = "Ω"
    value = raw_val * scale
    angle = _normalize_number(angle_match.group(1)) if angle_match else None
    unit = f"{prefix}{unit_base}".strip() or None
    return value, angle, unit


def preprocess_image(path: Path) -> np.ndarray:
    """Load and lightly denoise/threshold an image for OCR."""
    img = cv2.imread(str(path))
    if img is None:
        raise FileNotFoundError(f"Image not found: {path}")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.medianBlur(gray, 3)
    th = cv2.adaptiveThreshold(
        blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 10
    )
    return th


def _read_api_key(env_name: str) -> str:
    key = os.environ.get(env_name, "").strip()
    if not key:
        raise RuntimeError(f"API key not found in env var {env_name}")
    return key


def _image_to_base64(path: Path, max_dim: int | None = 1400) -> str:
    """
    Read image and encode to base64 (JPEG). Optionally downscale if longer side > max_dim.
    """
    img = cv2.imread(str(path))
    if img is None:
        raise FileNotFoundError(f"Image not found: {path}")
    if max_dim:
        h, w = img.shape[:2]
        if max(h, w) > max_dim:
            scale = max_dim / float(max(h, w))
            img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    _, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    return base64.b64encode(buf).decode("ascii")


def ocr_image(
    path: Path,
    lang: str = "eng",
    provider_model: str = "tesseract",
    api_key_env: str = "OPENAI_API_KEY",
    timeout: float = 120.0,
    max_dim: int | None = 1400,
) -> str:
    """
    Run OCR on an image path.

    provider_model:
      - "tesseract" (default)
      - "openai:gpt-4o" (or any OpenAI vision-capable model; uses env key)
      - "ollama:deepseek-ocr" (or other local Ollama vision model)
    """
    if ":" in provider_model:
        provider, model = provider_model.split(":", 1)
    else:
        provider, model = provider_model, None
    provider = provider.lower()

    if provider == "tesseract":
        pre = preprocess_image(path)
        return pytesseract.image_to_string(pre, lang=lang, config="--psm 6 --oem 3")

    if provider == "openai":
        api_key = _read_api_key(api_key_env)
        b64 = _image_to_base64(path, max_dim=max_dim)
        model_name = model or "gpt-4o-mini"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Extract all visible text. Respond with plain text only."},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}" }},
                    ],
                }
            ],
            "max_tokens": 512,
        }
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            json=payload,
            headers=headers,
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    if provider == "ollama":
        model_name = model or "deepseek-ocr"
        b64 = _image_to_base64(path, max_dim=max_dim)
        payload = {
            "model": model_name,
            "prompt": "Extract all text visible in the image. Return plain text only.",
            "images": [b64],
            "stream": False,
        }
        resp = requests.post("http://localhost:11434/api/generate", json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        return data.get("response", "")

    raise ValueError(f"Unsupported OCR provider '{provider_model}'")


def parse_measurement_rows(text: str) -> List[ParsedRow]:
    """
    Parse OCR text into structured rows (distance/current/voltage/impedance).
    Supports table-like lines with columns:
      Entf. | V OUT (Korr.) | IN 1 | Z (Korr)
      1.0m | 114.0 mA 0.00° | 13.46mV -136.56°| 118.1 mΩ -136.56°
    Falls back to distance-led free text otherwise.
    """
    rows: List[ParsedRow] = []
    seen_keys: set[tuple[float, Optional[float], Optional[float], Optional[float]]] = set()
    compact_pattern = re.compile(
        r"(?P<dist>-?\d+(?:[.,]\d+)?)\s*m"
        r".*?(?P<cur>-?\d+(?:[.,]\d+)?)\s*mA\s*(?P<ang1>-?\d+(?:[.,]\d+)?)?\s*[°º]?"
        r".*?(?P<volt>-?\d+(?:[.,]\d+)?)\s*mV\s*(?P<ang2>-?\d+(?:[.,]\d+)?)?\s*[°º]?"
        r".*?(?P<imp>-?\d+(?:[.,]\d+)?)\s*m[Ω0oOQqAa]\s*(?P<ang3>-?\d+(?:[.,]\d+)?)?\s*[°º]?",
        re.IGNORECASE,
    )
    full_pattern = re.compile(
        r"(?P<dist>-?\d+(?:[.,]\d+)?)\s*m"
        r".*?(?P<cur>-?\d+(?:[.,]\d+)?)\s*mA\s*(?P<ang1>-?\d+(?:[.,]\d+)?)?\s*[°º]?"
        r".*?(?P<volt>-?\d+(?:[.,]\d+)?)\s*mV\s*(?P<ang2>-?\d+(?:[.,]\d+)?)?\s*[°º]?"
        r".*?(?P<imp>-?\d+(?:[.,]\d+)?)\s*m[Ω0oOQqAa]\s*(?P<ang3>-?\d+(?:[.,]\d+)?)?\s*[°º]?",
        re.IGNORECASE | re.DOTALL,
    )
    distance_pattern = re.compile(
        r"(?:dist|distance|d)\s*[:=]?\s*(-?\d+(?:[.,]\d+)?)\s*(?:m\b|meter|metre|mtr)?",
        re.IGNORECASE,
    )
    # Also catch bare numbers followed by m
    distance_unit_pattern = re.compile(r"(-?\d+(?:[.,]\d+)?)\s*m\b", re.IGNORECASE)

    current_pattern = re.compile(
        r"(?:earth)?\s*current|i", re.IGNORECASE
    )
    current_value_pattern = re.compile(
        r"(-?\d+(?:[.,]\d+)?)\s*(?:a\b|amp)", re.IGNORECASE
    )

    voltage_pattern = re.compile(r"(?:volt|vtp|vt)\b", re.IGNORECASE)
    voltage_value_pattern = re.compile(r"(-?\d+(?:[.,]\d+)?)\s*v\b", re.IGNORECASE)

    impedance_label_pattern = re.compile(
        r"(?:impedance|resistance|z|r)\s*[:=]?\s*(-?\d+(?:[.,]\d+)?)",
        re.IGNORECASE,
    )
    impedance_unit_pattern = re.compile(
        r"(-?\d+(?:[.,]\d+)?)\s*(?:ohm|Ω|ohms)\b", re.IGNORECASE
    )

    angle_pattern = re.compile(r"(?:angle|phi|∠)\s*[:=]?\s*(-?\d+(?:[.,]\d+)?)")
    degree_pattern = re.compile(r"(-?\d+(?:[.,]\d+)?)\s*[°º]")

    # Pass 1: extract any compact sequences across the whole text (multi-line)
    full_clean = (
        text.replace("—", "-")
        .replace("|", " | ")
        .replace("0.", "0.0")
        .replace("rn", "m")
    )
    for m_full in full_pattern.finditer(full_clean):
        cur_val = _normalize_number(m_full.group("cur")) * 1e-3  # mA -> A
        volt_val = _normalize_number(m_full.group("volt")) * 1e-3  # mV -> V
        row = ParsedRow(
            distance_m=_normalize_number(m_full.group("dist")),
            current_a=cur_val,
            current_angle_deg=_normalize_number(m_full.group("ang1")) if m_full.group("ang1") else None,
            voltage_v=volt_val,
            voltage_angle_deg=_normalize_number(m_full.group("ang2")) if m_full.group("ang2") else None,
            impedance_ohm=_normalize_number(m_full.group("imp")) * 1e-3,  # mΩ → Ω
            impedance_angle_deg=_normalize_number(m_full.group("ang3")) if m_full.group("ang3") else None,
        )
        key = (
            row.distance_m or math.inf,
            row.current_a,
            row.voltage_v,
            row.impedance_ohm,
        )
        if key not in seen_keys:
            seen_keys.add(key)
            rows.append(row)

    for m_compact in compact_pattern.finditer(full_clean):
        cur_val = _normalize_number(m_compact.group("cur")) * 1e-3  # mA -> A
        volt_val = _normalize_number(m_compact.group("volt")) * 1e-3  # mV -> V
        row = ParsedRow(
            distance_m=_normalize_number(m_compact.group("dist")),
            current_a=cur_val,
            current_angle_deg=_normalize_number(m_compact.group("ang1")) if m_compact.group("ang1") else None,
            voltage_v=volt_val,
            voltage_angle_deg=_normalize_number(m_compact.group("ang2")) if m_compact.group("ang2") else None,
            impedance_ohm=_normalize_number(m_compact.group("imp")) * 1e-3,  # mΩ → Ω
            impedance_angle_deg=_normalize_number(m_compact.group("ang3")) if m_compact.group("ang3") else None,
        )
        if row.impedance_ohm is None and row.voltage_v is not None and row.current_a not in (None, 0):
            row.impedance_ohm = abs(row.voltage_v / row.current_a)
            if row.voltage_angle_deg is not None and row.current_angle_deg is not None:
                row.impedance_angle_deg = row.voltage_angle_deg - row.current_angle_deg
        key = (
            row.distance_m or math.inf,
            row.current_a,
            row.voltage_v,
            row.impedance_ohm,
        )
        if key not in seen_keys:
            seen_keys.add(key)
            rows.append(row)

    # Pass 2: per-line parsing for leftovers
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        cleaned = (
            line.replace("—", "-")
            .replace("|", " | ")
            .replace("0.", "0.0")  # stabilize missing zero before dot
            .replace("rn", "m")
        )
        m_compact_line = compact_pattern.search(cleaned)
        if m_compact_line:
            cur_val = _normalize_number(m_compact_line.group("cur")) * 1e-3  # mA -> A
            volt_val = _normalize_number(m_compact_line.group("volt")) * 1e-3  # mV -> V
            row = ParsedRow(
                distance_m=_normalize_number(m_compact_line.group("dist")),
                current_a=cur_val,
                current_angle_deg=_normalize_number(m_compact_line.group("ang1")) if m_compact_line.group("ang1") else None,
                voltage_v=volt_val,
                voltage_angle_deg=_normalize_number(m_compact_line.group("ang2")) if m_compact_line.group("ang2") else None,
                impedance_ohm=_normalize_number(m_compact_line.group("imp")) * 1e-3,  # mΩ → Ω
                impedance_angle_deg=_normalize_number(m_compact_line.group("ang2")) if m_compact_line.group("ang2") else None,
            )
            key = (
                row.distance_m or math.inf,
                row.current_a,
                row.voltage_v,
                row.impedance_ohm,
            )
            if key not in seen_keys:
                seen_keys.add(key)
                rows.append(row)
            continue

        # Sequential token extraction: dist, current (mA), voltage (mV), impedance (mΩ/Ω)
        dist_match_seq = distance_pattern.search(line) or distance_unit_pattern.search(line)
        cur_match_seq = re.search(r"(-?\d+(?:[.,]\d+)?)\s*mA", line, re.IGNORECASE)
        volt_match_seq = re.search(r"(-?\d+(?:[.,]\d+)?)\s*mV", line, re.IGNORECASE)
        imp_match_m = re.search(r"(-?\d+(?:[.,]\d+)?)\s*m[Ω0oOQqAa]", line, re.IGNORECASE)
        imp_match_O = re.search(r"(-?\d+(?:[.,]\d+)?)\s*Ω", line, re.IGNORECASE)
        degs = list(degree_pattern.finditer(line))

        if dist_match_seq and (cur_match_seq or volt_match_seq or imp_match_m or imp_match_O):
            row = ParsedRow(distance_m=_normalize_number(dist_match_seq.group(1)))
            if cur_match_seq:
                row.current_a = _normalize_number(cur_match_seq.group(1)) * 1e-3
            if volt_match_seq:
                row.voltage_v = _normalize_number(volt_match_seq.group(1)) * 1e-3
            if imp_match_m:
                row.impedance_ohm = _normalize_number(imp_match_m.group(1)) * 1e-3
            elif imp_match_O:
                row.impedance_ohm = _normalize_number(imp_match_O.group(1))
            # If we have V and I but no Z, compute Z = V/I
            if row.impedance_ohm is None and row.voltage_v is not None and row.current_a not in (None, 0):
                row.impedance_ohm = abs(row.voltage_v / row.current_a)
                if row.voltage_angle_deg is not None and row.current_angle_deg is not None:
                    row.impedance_angle_deg = row.voltage_angle_deg - row.current_angle_deg

            if degs:
                if len(degs) >= 1 and row.current_a is not None:
                    row.current_angle_deg = _normalize_number(degs[0].group(1))
                if len(degs) >= 2 and row.voltage_v is not None:
                    row.voltage_angle_deg = _normalize_number(degs[1].group(1))
                if len(degs) >= 3 and row.impedance_ohm is not None:
                    row.impedance_angle_deg = _normalize_number(degs[2].group(1))
                elif len(degs) >= 2 and row.impedance_ohm is not None:
                    row.impedance_angle_deg = _normalize_number(degs[1].group(1))

            key = (
                row.distance_m or math.inf,
                row.current_a,
                row.voltage_v,
                row.impedance_ohm,
            )
            if key not in seen_keys:
                seen_keys.add(key)
                rows.append(row)
            continue

        # Table-like lines separated by pipes
        if "|" in line:
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) >= 4:
                dist_match = re.search(r"(-?\d+(?:[.,]\d+)?)\s*m", parts[0], re.IGNORECASE)
                if dist_match:
                    row = ParsedRow(distance_m=_normalize_number(dist_match.group(1)))
                    cur_val, cur_ang, _ = _parse_value_angle_unit(parts[1])
                    row.current_a = cur_val
                    row.current_angle_deg = cur_ang
                    volt_val, volt_ang, _ = _parse_value_angle_unit(parts[2])
                    row.voltage_v = volt_val
                    row.voltage_angle_deg = volt_ang
                    imp_val, imp_ang, _ = _parse_value_angle_unit(parts[3])
                    row.impedance_ohm = imp_val
                    row.impedance_angle_deg = imp_ang
                    key = (
                        row.distance_m or math.inf,
                        row.current_a,
                        row.voltage_v,
                        row.impedance_ohm,
                    )
                    if key not in seen_keys:
                        seen_keys.add(key)
                        rows.append(row)
                    continue

        dist_match = distance_pattern.search(line) or distance_unit_pattern.search(line)
        if not dist_match:
            # skip lines without distance anchors to avoid misalignment
            continue

        row = ParsedRow(distance_m=_normalize_number(dist_match.group(1)))

        # Current
        if current_pattern.search(line):
            cur_match = current_value_pattern.search(line)
            if cur_match:
                row.current_a = _normalize_number(cur_match.group(1))
        else:
            cur_match = current_value_pattern.search(line)
            if cur_match:
                row.current_a = _normalize_number(cur_match.group(1))

        ang_match = angle_pattern.search(line)
        if ang_match and row.current_a is not None:
            row.current_angle_deg = _normalize_number(ang_match.group(1))

        # Voltage
        if voltage_pattern.search(line):
            volt_match = voltage_value_pattern.search(line)
            if volt_match:
                row.voltage_v = _normalize_number(volt_match.group(1))
        else:
            volt_match = voltage_value_pattern.search(line)
            if volt_match:
                row.voltage_v = _normalize_number(volt_match.group(1))
        if ang_match and row.voltage_v is not None and row.current_angle_deg is None:
            row.voltage_angle_deg = _normalize_number(ang_match.group(1))

        # Impedance / resistance
        imp_match = impedance_label_pattern.search(line) or impedance_unit_pattern.search(line)
        if imp_match:
            row.impedance_ohm = _normalize_number(imp_match.group(1))
        else:
            mo_matches = re.findall(r"(-?\d+(?:[.,]\d+)?)\s*m[Ω0o]", line, re.IGNORECASE)
            if mo_matches:
                row.impedance_ohm = _normalize_number(mo_matches[-1]) * 1e-3
            else:
                o_matches = re.findall(r"(-?\d+(?:[.,]\d+)?)\s*Ω", line, re.IGNORECASE)
                if o_matches:
                    row.impedance_ohm = _normalize_number(o_matches[-1])

        if ang_match and row.impedance_ohm is not None and row.current_angle_deg is None:
            row.impedance_angle_deg = _normalize_number(ang_match.group(1))

        key = (
            row.distance_m or math.inf,
            row.current_a,
            row.voltage_v,
            row.impedance_ohm,
        )
        if key in seen_keys:
            continue
        seen_keys.add(key)
        rows.append(row)

    rows.sort(key=lambda r: r.distance_m if r.distance_m is not None else math.inf)

    # Fill missing or obviously wrong currents with median of reasonable currents
    cur_candidates = [r.current_a for r in rows if r.current_a is not None and 0.01 < abs(r.current_a) < 0.3]
    median_cur = float(np.median(cur_candidates)) if cur_candidates else None
    if median_cur is not None:
        for r in rows:
            if r.current_a is None or abs(r.current_a) > 0.3:
                r.current_a = median_cur
                if r.current_angle_deg is None:
                    r.current_angle_deg = 0.0
            if r.current_a is not None and r.current_a < 0:
                r.current_a = abs(r.current_a)
        # Recompute impedance from V/I when missing or clearly off
        for r in rows:
            if r.voltage_v is not None and r.current_a not in (None, 0):
                z_calc = abs(r.voltage_v / r.current_a)
                if r.impedance_ohm is None or r.impedance_ohm <= 0 or abs(r.impedance_ohm - z_calc) / z_calc > 0.2:
                    r.impedance_ohm = z_calc
                    if r.voltage_angle_deg is not None and r.current_angle_deg is not None:
                        r.impedance_angle_deg = r.voltage_angle_deg - r.current_angle_deg

    return rows


def _relative_spread(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    med = float(np.median(values))
    if med == 0:
        return float("inf")
    return (max(values) - min(values)) / med


def _interpolate_at_distance(rows: List[ParsedRow], target: float) -> Optional[float]:
    """Linear interpolate voltage at a target distance (used for 1 m prospective)."""
    with_dist = [r for r in rows if r.distance_m is not None and r.voltage_v is not None]
    if not with_dist:
        return None
    closest = min(with_dist, key=lambda r: abs(r.distance_m - target))
    if abs(closest.distance_m - target) < 1e-6:
        return closest.voltage_v
    # find second nearest on opposite side if possible
    candidates = sorted(with_dist, key=lambda r: r.distance_m)
    lower = [r for r in candidates if r.distance_m <= target]
    upper = [r for r in candidates if r.distance_m >= target]
    if lower and upper:
        r1 = lower[-1]
        r2 = upper[0]
        if r1.distance_m == r2.distance_m:
            return r1.voltage_v
        x1, y1 = r1.distance_m, r1.voltage_v
        x2, y2 = r2.distance_m, r2.voltage_v
        return y1 + (target - x1) * (y2 - y1) / (x2 - x1)
    return closest.voltage_v


def build_items_from_rows(
    measurement_id: int,
    rows: List[ParsedRow],
    measurement_type: str,
    frequency_hz: float,
    distance_to_current_injection_m: Optional[float] = None,
) -> Dict[str, List[Dict[str, object]]]:
    """
    Convert parsed rows into MeasurementItem payloads.

    Returns dict with keys: impedance_items, current_items, voltage_items.
    """
    rows_with_dist = [r for r in rows if r.distance_m is not None]
    impedance_items: List[Dict[str, object]] = []
    current_values: List[float] = []
    current_angles: List[float] = []
    voltage_rows: List[ParsedRow] = []

    # Deduplicate impedance rows (exact-ish match)
    seen_imp: dict[float, Dict[str, object]] = {}
    for row in rows_with_dist:
        if row.impedance_ohm is not None and row.impedance_ohm > 0:
            dist_key = round(row.distance_m, 3)
            candidate = {
                "measurement_type": measurement_type,
                "frequency_hz": frequency_hz,
                "value": row.impedance_ohm,
                "value_angle_deg": row.impedance_angle_deg,
                "unit": "Ω",
                "measurement_distance_m": row.distance_m,
                "distance_to_current_injection_m": distance_to_current_injection_m,
            }
            prev = seen_imp.get(dist_key)
            # Prefer item with angle, otherwise larger magnitude
            def _score(it: Dict[str, object]) -> tuple[int, float]:
                has_ang = 1 if it.get("value_angle_deg") is not None else 0
                return (has_ang, float(it.get("value", 0.0)))
            if prev is None or _score(candidate) > _score(prev):
                seen_imp[dist_key] = candidate
    impedance_items.extend(seen_imp.values())

    for row in rows_with_dist:
        if row.current_a is not None:
            current_values.append(row.current_a)
            if row.current_angle_deg is not None:
                current_angles.append(row.current_angle_deg)
        if row.voltage_v is not None and row.distance_m is not None and 0.5 <= row.distance_m <= 1.5:
            voltage_rows.append(row)

    # Merge currents: median if spread <= ±20%; else emit distinct values
    earthing_currents: List[Dict[str, object]] = []
    valid_currents = [c for c in current_values if 0.05 <= abs(c) <= 0.2]
    chosen_currents = valid_currents if valid_currents else current_values
    if chosen_currents:
        spread = _relative_spread(chosen_currents)
        if spread <= 0.4:
            median_val = float(np.median(chosen_currents))
            median_angle = float(np.median(current_angles)) if current_angles else None
            earthing_currents.append(
                {
                    "measurement_type": "earthing_current",
                    "frequency_hz": frequency_hz,
                    "value": median_val,
                    "value_angle_deg": median_angle,
                    "unit": "A",
                }
            )
        else:
            seen_currents: set[tuple[float, Optional[float]]] = set()
            for val, ang in zip(chosen_currents, current_angles or [None] * len(chosen_currents)):
                key = (round(val, 6), None if ang is None else round(ang, 3))
                if key in seen_currents:
                    continue
                seen_currents.add(key)
                earthing_currents.append(
                    {
                        "measurement_type": "earthing_current",
                        "frequency_hz": frequency_hz,
                        "value": val,
                        "value_angle_deg": ang,
                        "unit": "A",
                    }
                )

    # Prospective touch voltage at 1 m (from rows only, nearest to 1m with tolerance dedup)
    prospective_items: List[Dict[str, object]] = []
    seen_ptv: List[ParsedRow] = []
    if voltage_rows:
        min_delta = min(abs(r.distance_m - 1.0) for r in voltage_rows)
        candidates = [r for r in voltage_rows if abs(r.distance_m - 1.0) <= min_delta + 0.02 * max(1.0, r.distance_m)]
        for r in candidates:
            dup = False
            for existing in seen_ptv:
                dist_tol = 0.02 * max(existing.distance_m, r.distance_m, 1e-6)
                val_tol = 0.02 * max(existing.voltage_v, r.voltage_v, 1e-6)
                ang_ok = True
                if existing.voltage_angle_deg is not None and r.voltage_angle_deg is not None:
                    ang_tol = 0.02 * max(abs(existing.voltage_angle_deg), abs(r.voltage_angle_deg), 1.0)
                    ang_ok = abs(existing.voltage_angle_deg - r.voltage_angle_deg) <= ang_tol
                if abs(existing.distance_m - r.distance_m) <= dist_tol and abs(existing.voltage_v - r.voltage_v) <= val_tol and ang_ok:
                    dup = True
                    break
            if dup:
                continue
            seen_ptv.append(r)
            prospective_items.append(
                {
                    "measurement_type": "prospective_touch_voltage",
                    "frequency_hz": frequency_hz,
                    "value": r.voltage_v,
                    "value_angle_deg": r.voltage_angle_deg,
                    "unit": "V",
                    "measurement_distance_m": r.distance_m,
                }
            )

    return {
        "impedance_items": impedance_items,
        "earthing_current_items": earthing_currents,
        "voltage_items": [],
        "prospective_items": prospective_items,
    }


def import_items_from_images(
    images_dir: Path,
    measurement_id: int,
    measurement_type: str = "earthing_impedance",
    frequency_hz: Union[float, str] = 50.0,
    distance_to_current_injection_m: Optional[float] = None,
    ocr_provider: str = "tesseract",
    api_key_env: str = "OPENAI_API_KEY",
    ocr_timeout: float = 120.0,
    ocr_max_dim: int | None = 1400,
) -> Dict[str, object]:
    """
    Run OCR over all images in a directory and create MeasurementItems.

    Returns summary with counts and any skipped files.
    """
    img_dir = Path(images_dir)
    img_freq_pairs: List[tuple[Path, float]] = []
    dir_mode = isinstance(frequency_hz, str) and frequency_hz.strip().lower() == "dir"

    if dir_mode:
        for sub in sorted(img_dir.iterdir()):
            if not sub.is_dir():
                continue
            try:
                freq_val = float(str(sub.name).replace(",", "."))
            except Exception:
                continue
            for p in sorted(sub.iterdir()):
                if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}:
                    img_freq_pairs.append((p, freq_val))
    else:
        try:
            freq_val = float(frequency_hz)
        except Exception:
            freq_val = 50.0
        img_freq_pairs = [
            (p, freq_val)
            for p in sorted(img_dir.iterdir())
            if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}
        ]

    if not img_freq_pairs:
        raise FileNotFoundError(f"No image files found in {images_dir}")

    created_ids: List[int] = []
    skipped: List[str] = []
    parsed_rows: List[ParsedRow] = []

    for img, freq in img_freq_pairs:
        try:
            text = ocr_image(
                img,
                provider_model=ocr_provider,
                api_key_env=api_key_env,
                timeout=ocr_timeout,
                max_dim=ocr_max_dim,
            )
            rows = parse_measurement_rows(text)
            parsed_rows.extend(rows)
            # build and create items per image (frequency-specific)
            items = build_items_from_rows(
                measurement_id=measurement_id,
                rows=rows,
                measurement_type=measurement_type,
                frequency_hz=freq,
                distance_to_current_injection_m=distance_to_current_injection_m,
            )
            for payload in (
                items["impedance_items"]
                + items["earthing_current_items"]
                + items["prospective_items"]
            ):
                iid = create_item(payload, measurement_id=measurement_id)
                created_ids.append(iid)
        except Exception as exc:
            logger.warning("Skipping %s due to error: %s", img, exc)
            skipped.append(f"{img.name}: {exc}")

    return {
        "created_item_ids": created_ids,
        "skipped": skipped,
        "parsed_row_count": len(parsed_rows),
    }
