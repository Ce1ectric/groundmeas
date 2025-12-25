# Import and export

Scenario continuation: archive the staged fault test, share data, and ingest additional measurements from JSON and images.

## CLI
| Task | Command | Notes |
| --- | --- | --- |
| Import JSON | `gm-cli import-json PATH` | File, folder, or split pairs `_measurement.json` + `_items.json`. |
| Export JSON | `gm-cli export-json OUT.json --measurement-id MEAS_ID ...` | Export selected measurements with items. |
| OCR import from images | `gm-cli import-from-images MEAS_ID IMAGES_DIR --type earthing_impedance --frequency 50 --ocr tesseract --injection-distance 200` | Use `--frequency dir` to read freq from subfolders; switch OCR provider with `--ocr openai:<model>` or `--ocr ollama:<model>`. |

Example (pull new site data):
```bash
gm-cli import-json data/new_site/
gm-cli export-json export/sub_west.json --measurement-id 1
gm-cli import-from-images 1 ./images/sub_west --type earthing_impedance --frequency dir --ocr tesseract
```

## Python API
```python
from groundmeas.db import connect_db
from groundmeas.export import export_measurements_to_json, export_measurements_to_csv, export_measurements_to_xml
from groundmeas.vision_import import import_items_from_images

connect_db("groundmeas.db")

# Export selected measurements
export_measurements_to_json("export/sub_west.json", id__in=[1])
export_measurements_to_csv("export/sub_west.csv", id__in=[1])
export_measurements_to_xml("export/sub_west.xml", id__in=[1])

# OCR import for another measurement
summary = import_items_from_images(
    images_dir="images/sub_west",
    measurement_id=1,
    measurement_type="earthing_impedance",
    frequency_hz="dir",
    distance_to_current_injection_m=200.0,
    ocr_provider="tesseract",
)
print(summary)
```

### OCR notes
- For OpenAI models, set `OPENAI_API_KEY` or pass `api_key_env`.
- `ocr_max_dim` can downscale images for cloud OCR efficiency.
- The importer deduplicates impedance by distance, median-filters currents when stable, and estimates prospective touch voltage near 1 m.

### File format tips
- JSON export is lossless and includes nested items and location.
- CSV export stores items as a JSON string column—best for spreadsheets, not round-trips.
- XML export nests items under each measurement. 
