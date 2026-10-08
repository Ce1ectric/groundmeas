# Troubleshooting

Run with `-v` for debug messages and with `-q` to see only warnings and
errors. Every warning names the file or the tower it refers to.

## Installation and PDF export

??? question "`PDF export needs Playwright …`"

    Playwright is an optional dependency of groundmeas. Install the extra
    with `pip install "groundmeas[pdf]"` (or `pipx inject groundmeas
    playwright` for a pipx installation), then run
    `gm-cli towers install-browser`. `--no-pdf` creates HTML protocols
    without Playwright.

??? question "`No Chromium-based browser found for the PDF export`"

    Install Playwright's Chromium with `gm-cli towers install-browser`. If
    the download is blocked, install Google Chrome or Microsoft Edge (used
    automatically) or point `GROUNDMEAS_BROWSER` to a Chromium-based
    browser. `--no-pdf` creates HTML protocols without any browser.

??? question "Playwright's Chromium does not start on Linux"

    The browser needs system libraries:
    `python -m playwright install --with-deps chromium` (Debian/Ubuntu, as
    root).

??? question "`gm-cli: command not found`"

    The scripts folder of your Python installation is not on the `PATH`.
    Use `python -m groundmeas.ui.cli …` or install with `pipx`, which takes
    care of the `PATH`.

## Configuration

??? question "`… is not valid JSON`"

    Typical causes are a trailing comma after the last entry and single
    backslashes in Windows paths (`"C:\Data"` must be written `"C:\\Data"` or
    `"C:/Data"`). Relative paths avoid the problem.

??? question "`directory.… does not exist`"

    Relative paths are resolved against the folder of the configuration
    file, not against the current working directory.

## Measurement files

??? question "`Skipping file with unrecognised name: …`"

    The XML file name does not follow the configured
    `grounding_impedance_structure`. Most often the line identifier contains
    an underscore (`LX_01` instead of `LX-01`) or the file has a suffix
    (`ZE_LX-01_8 (2).xml`).

??? question "`No HGT1 report for …` / `Skipping …: no touch-voltage (HGT1) data`"

    The touch-voltage report must be named `UT_<line>_<tower>.txt` and lie in
    the same folder. Leading zeros and letter case are ignored.

??? question "`… the measuring points of the description … differ from the HGT1 report`"

    The HGT1 recorded location names that do not match `Messpunkte_UT` of the
    measurement description. The HGT1 names are used; correct the
    description if they are wrong.

??? question "`… measuring points in the description for … readings; the list is repeated cyclically`"

    `Messpunkte_UT` needs one entry per reading, or one entry per measuring
    point when every point was measured with and without additional
    resistor. Check the labels in the protocol.

??? question "`Skipping …: no row in the measurement description`"

    Line and tower of the file name were not found in the measurement
    description. Compare the spelling of the line identifier.

??? question "`Footing-resistance profile of … not usable …`"

    The profile of corrected currents is missing or has a different number
    of points than the impedance profile. The tower is evaluated without it;
    a high-frequency single value is shown if available.

## Results

??? question "`Cannot write …. The file is probably open in Excel`"

    Close the summary or the grid-data workbook and run again.

??? question "`Clearing time … is outside the touch-voltage table`"

    The clearing time is shorter or longer than the table in
    `touch_voltages`. The value at the table end is used; extend the table
    (for example with `10 s → 80 V` for compensated networks).

??? question "The protocol shows the wrong map"

    The map is searched as `Map_<line>_<tower>.<ext>` next to the JSON files
    first and then in the measurement folder. Remove outdated map images from
    the result folder.

??? question "`No JSON files found … Run the calc step first.` for `--stats`"

    The statistics are created from the JSON results; run `--calc` before
    `--stats`.

??? question "`import-db`: `no current-electrode distance … 62 % method not available`"

    The measurement description has no `Entfernung_Hilfserder_m` for the
    tower. The profile is imported without the distance of the current
    electrode; `distance_profile_value(..., algorithm="62_percent")` then
    cannot evaluate it. Fill in the distance and import the file again
    (`--reimport`, after deleting the old measurement).

## Reporting a problem

Please open an issue on
[GitHub](https://github.com/Ce1ectric/groundmeas/issues) with the command,
the full output with `-v`, your operating system and the version
(`python -c "import groundmeas; print(groundmeas.__version__)"`). Do not attach real
measurement data; the demo campaign or a reduced, anonymised example is
usually enough to reproduce a problem.
