import argparse
import json
from pathlib import Path

import yaml
import pandas as pd
from jsonschema import validate, ValidationError

# Example schema — adjust to YOUR YAML structure
SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "value": {"type": "number"},
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["name", "value"],
    "additionalProperties": True,
}

def load_yaml_file(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Input folder with YAML files")
    parser.add_argument("--output", required=True, help="Output folder for reports")
    args = parser.parse_args()

    input_dir = Path(args.input)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    errors = []

    for p in sorted(list(input_dir.rglob("*.yml")) + list(input_dir.rglob("*.yaml"))):
        try:
            data = load_yaml_file(p)

            # Validate (optional)
            validate(instance=data, schema=SCHEMA)

            rows.append({
                "file": str(p),
                "name": data.get("name"),
                "value": data.get("value"),
                "tags": ",".join(data.get("tags", [])) if isinstance(data.get("tags"), list) else None,
            })

        except ValidationError as e:
            errors.append({"file": str(p), "error": f"Schema validation failed: {e.message}"})
        except Exception as e:
            errors.append({"file": str(p), "error": str(e)})

    df = pd.DataFrame(rows)

    summary = {
        "files_ok": len(rows),
        "files_failed": len(errors),
        "value_count": int(df["value"].count()) if not df.empty else 0,
        "value_mean": float(df["value"].mean()) if not df.empty else None,
        "value_min": float(df["value"].min()) if not df.empty else None,
        "value_max": float(df["value"].max()) if not df.empty else None,
        "errors": errors,
    }

    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    df.to_csv(out_dir / "summary.csv", index=False)

    # Fail the CI run if any YAML file is invalid
    if errors:
        raise SystemExit(f"Validation/parse errors in {len(errors)} file(s). See reports/summary.json")

if __name__ == "__main__":
    main()

