# Import and export

This tutorial covers JSON, CSV, and XML export, JSON import, and OCR-based import from measurement images.

## Physical background

Not applicable. This tutorial focuses on data transfer and ingestion.

## Function overview
- `export_measurements_to_json`, `export_measurements_to_csv`, `export_measurements_to_xml` export measurement data.
- `import_items_from_images` runs OCR and creates items from images.
- CLI commands `import-json`, `export-json`, and `import-from-images` provide the same capabilities.

## Inputs and outputs
| Function | Input | Output | Description |
| --- | --- | --- | --- |
| `export_measurements_to_json` | `path`, filters | none | Write measurements to JSON. |
| `export_measurements_to_csv` | `path`, filters | none | Write measurements to CSV. |
| `export_measurements_to_xml` | `path`, filters | none | Write measurements to XML. |
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

### Scenario A: export and share
```python
from groundmeas.db import connect_db
from groundmeas.export import export_measurements_to_json, export_measurements_to_csv

connect_db("groundmeas.db")

export_measurements_to_json("export/site_a.json", id__in=[1])
export_measurements_to_csv("export/site_a.csv", id__in=[1])
```

### Scenario B: OCR import
```python
from groundmeas.db import connect_db
from groundmeas.vision_import import import_items_from_images

connect_db("groundmeas.db")

summary = import_items_from_images(
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
