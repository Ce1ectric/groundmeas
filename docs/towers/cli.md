# Command line

All tower commands are sub-commands of `gm-cli towers`:

| Command | Purpose |
| --- | --- |
| `gm-cli towers run` | evaluate a campaign: steps `--calc`, `--print`, `--zip`, `--stats` |
| `gm-cli towers demo DIR` | write the synthetic demo campaign |
| `gm-cli towers example-config [PATH]` | write an annotated example configuration |
| `gm-cli towers flatten SRC DEST` | copy a delivery with one folder per tower into the flat layout ([details](campaign.md#delivery-with-one-folder-per-tower)) |
| `gm-cli towers import-db` | copy the instrument data of a campaign into the groundmeas database ([details](database.md)) |
| `gm-cli towers install-browser` | download Playwright's Chromium for the PDF protocols |

The commands work on files and do not open the groundmeas database – except
`import-db`, which uses the database chosen with `gm-cli --db PATH towers
import-db …` (or `GROUNDMEAS_DB`, or the default database).

## `gm-cli towers run`

```text
gm-cli towers run [--calc] [--print] [--zip] [--stats]
                  [--config PATH] [--worker N] [--no-pdf] [-v | -q]
```

### Steps

| Option | Step | Reads | Writes |
| --- | --- | --- | --- |
| `--calc` | evaluate all measurements | measurement folder, workbooks, configuration | JSON per tower, `summary.xlsx`, updated grid-data workbook |
| `--print` | diagrams and protocol per tower | JSON files | `html_files/*.png`, `*.html`, `*.pdf` |
| `--zip` | collect the PDF protocols | `html_files/*.pdf` | `protocols.zip` (`export_path_pdf`) |
| `--stats` | statistics over all towers | JSON files | `Statistik/Asset_Auswertung.html` / `.pdf` |

- Without a step option, `--calc --print --zip` is run.
- Several options can be combined; the steps always run in the order
  `calc → print → zip → stats`, independent of the order on the command line.
- `--print`, `--zip` and `--stats` work on existing JSON files, so a protocol
  layout or language change does not require a new `--calc`.

### Options

| Option | Meaning |
| --- | --- |
| `--config PATH`, `-c PATH` | campaign configuration; default `$GROUNDMEAS_TOWER_CONFIG` or `./config.json` |
| `--worker N` | number of parallel processes for `--print` (default 1); 4–8 speed up large campaigns |
| `--no-pdf` | write HTML protocols and statistics only, no browser needed; without explicit steps, `--zip` is skipped |
| `-v`, `--verbose` | show debug messages |
| `-q`, `--quiet` | show warnings and errors only |

### Exit codes

| Code | Meaning |
| --- | --- |
| `0` | success |
| `1` | processing error (file locked by Excel, no browser for the PDF export, no results for `--stats`, …) |
| `2` | invalid command line or configuration (missing file, wrong value) |

Warnings about single towers (unreadable file, missing HGT1 report, no row in
the measurement description) do not change the exit code; the tower is
skipped and the message names it. Run with `-q` to see only these messages.

## Other commands

| Command and options | Meaning |
| --- | --- |
| `demo DIR [--language en\|de] [--overwrite]` | write the demo campaign into `DIR` (must be empty or new unless `--overwrite`) |
| `example-config [PATH] [--overwrite]` | write the example configuration (default `config.json`) |
| `flatten SRC DEST [--apply] [--report CSV] [--only FOLDER]… [--line-pattern RE] [--tower-pattern RE] [--map-strip PREFIX]` | dry run unless `--apply`; exit code 1 on name conflicts |
| `import-db [--config PATH] [--per-frequency/--no-per-frequency] [--voltage-level-kv KV] [--timezone TZ] [--dry-run] [--reimport] [-v\|-q]` | exit code 1 if a file could not be imported |
| `install-browser` | runs `python -m playwright install chromium`; needs the `pdf` extra |

## Environment variables

| Variable | Meaning |
| --- | --- |
| `GROUNDMEAS_TOWER_CONFIG` | configuration file used when `--config` is not given (formerly `TOWER_GROUNDING_CONFIG`, still read) |
| `GROUNDMEAS_BROWSER` | browser for the PDF export: a Playwright channel (`chrome`, `msedge`, …) or the path of a Chromium-based executable (formerly `TOWER_GROUNDING_BROWSER`, still read) |
| `GROUNDMEAS_DB` | database of `import-db` when `--db` is not given |

## Examples

```console
# complete run
$ gm-cli towers run --config campaign/config.json

# evaluate only, check the warnings
$ gm-cli towers run --config campaign/config.json --calc -q

# re-print the protocols in parallel after a template change
$ gm-cli towers run --config campaign/config.json --print --zip --worker 6

# HTML only (e.g. on a server without browser)
$ gm-cli towers run --config campaign/config.json --no-pdf

# statistics report
$ gm-cli towers run --config campaign/config.json --stats

# copy the campaign into a database
$ gm-cli --db towers.db towers import-db --config campaign/config.json --timezone Europe/Berlin
```

=== "Windows (PowerShell)"

    ```powershell
    PS> $env:GROUNDMEAS_TOWER_CONFIG = "D:\Campaigns\2026\config.json"
    PS> gm-cli towers run --print --worker 4
    ```

=== "macOS / Linux"

    ```console
    $ export GROUNDMEAS_TOWER_CONFIG=~/campaigns/2026/config.json
    $ gm-cli towers run --print --worker 4
    ```
