# Import and export

This tutorial covers JSON, CSV, and XML export, JSON import, and OCR-based import from measurement images.
Exports of OMICRON COMPANO 100 and HGT1 instruments are imported directly, see
[Import from OMICRON instruments](17_instrument_import.md).

## Physical background

Not applicable. This tutorial focuses on data transfer and ingestion.

## Function overview
- `export_measurements_to_json`, `export_measurements_to_csv`, `export_measurements_to_xml` export measurement data.
- `import_measurements_from_json` / `import_measurements` read JSON written by `export_measurements_to_json` (round trip; time stamps are parsed, database keys are dropped).
- `import_items_from_images` runs OCR and creates items from images.
- CLI commands `import-json`, `export-json`, and `import-from-images` provide the same capabilities.

## Inputs and outputs
| Function | Input | Output | Description |
| --- | --- | --- | --- |
| `export_measurements_to_json` | `path`, filters | none | Write measurements to JSON. |
| `export_measurements_to_csv` | `path`, filters | none | Write measurements to CSV. |
| `export_measurements_to_xml` | `path`, filters | none | Write measurements to XML. |
| `import_measurements_from_json` | file or folder path | list of (measurement id, item count) | Import JSON exports (single file, folder or `X_measurement.json` + `X_items.json`). |
| `import_items_from_images` | images dir, measurement id | summary dict | OCR import of items from images. |

## General workflow

### Scenario A: share measurements
1. Export measurements to JSON or CSV.
2. Send the file to collaborators.
3. Import the JSON into another database.

### Scenario B: OCR import
1. Collect images of measurement tables.
2. Run OCR import for a target measurement.
3. Validate the imported items.

## Python API examples

These examples use the canonical top-level package
(`import groundmeas as gm`). The legacy `from groundmeas.export import ...`
and `from groundmeas.vision_import import ...` forms still work but emit
a `DeprecationWarning` — see the compatibility-shim list in
`docs/21_ref_api.md`.

### Scenario A: export and share
```python
import groundmeas as gm

gm.connect_db("groundmeas.db")

gm.export_measurements_to_json("export/site_a.json", id__in=[1])
gm.export_measurements_to_csv("export/site_a.csv", id__in=[1])

# in another database
gm.connect_db("other.db", force=True)
imported = gm.import_measurements_from_json("export/site_a.json")  # [(id, n_items), ...]
```

### Scenario B: OCR import
```python
import groundmeas as gm

gm.connect_db("groundmeas.db")

summary = gm.import_items_from_images(
    images_dir="images/site_a",
    measurement_id=1,
    measurement_type="earthing_impedance",
    frequency_hz="dir",
    distance_to_current_injection_m=200.0,
    ocr_provider="tesseract",
)
print(summary)
```

## CLI examples

### Scenario A: export and import
```bash
gm-cli export-json export/site_a.json --measurement-id 1

gm-cli import-json export/site_a.json
```

### Scenario B: OCR import
```bash
gm-cli import-from-images 1 images/site_a \
  --type earthing_impedance \
  --frequency dir \
  --ocr tesseract \
  --injection-distance 200
```

## Additional notes
- CSV export stores items as a JSON string and is not round-trip safe.
- OCR can misread decimal separators; validate imports before analysis.
- Use `--json-out` in CLI commands to capture structured output for automation.
