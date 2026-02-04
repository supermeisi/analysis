import argparse
import json
from pathlib import Path
from datetime import date, datetime

import yaml
import pandas as pd
import matplotlib.pyplot as plt
from jsonschema import validate, ValidationError

# Adjust this schema to match your YAML format
SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "value": {"type": "number"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "metadata": {
            "type": "object",
            "properties": {
                "date": {
                    "anyOf": [
                        {"type": "string"},  # "2026-01-15"
                        {"type": "object"}   # PyYAML may parse into datetime.date
                    ]
                },
            },
            "additionalProperties": True,
        },
    },
    "required": ["name", "value"],
    "additionalProperties": True,
}

def normalize_dates(obj):
    # Convert YAML-parsed date/datetime objects into ISO strings
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: normalize_dates(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [normalize_dates(v) for v in obj]
    return obj

def load_yaml_file(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def safe_parse_date(date_str: str):
    """Parse YYYY-MM-DD into datetime.date; return None if invalid."""
    if not date_str or not isinstance(date_str, str):
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        return None


def make_plots(df: pd.DataFrame, out_plots: Path):
    out_plots.mkdir(parents=True, exist_ok=True)

    # 1) Histogram of values
    if "value" in df.columns and df["value"].notna().any():
        plt.figure()
        plt.hist(df["value"].dropna(), bins=20)
        plt.title("Distribution of value")
        plt.xlabel("value")
        plt.ylabel("count")
        plt.tight_layout()
        plt.savefig(out_plots / "value_hist.png", dpi=150)
        plt.close()

    # 2) Mean value by name (bar)
    if "name" in df.columns and df["name"].notna().any():
        grp = df.dropna(subset=["name", "value"]).groupby("name", as_index=True)["value"].mean().sort_values()
        if len(grp) > 0:
            plt.figure()
            plt.bar(grp.index.astype(str), grp.values)
            plt.title("Mean value by name")
            plt.xlabel("name")
            plt.ylabel("mean(value)")
            plt.xticks(rotation=30, ha="right")
            plt.tight_layout()
            plt.savefig(out_plots / "value_by_name.png", dpi=150)
            plt.close()

    # 3) Value vs date (line), if metadata.date exists
    if "date" in df.columns and df["date"].notna().any():
        df_date = df.dropna(subset=["date", "value"]).copy()
        df_date["date_parsed"] = df_date["date"].apply(safe_parse_date)
        df_date = df_date.dropna(subset=["date_parsed"]).sort_values("date_parsed")

        if not df_date.empty:
            plt.figure()
            plt.plot(df_date["date_parsed"], df_date["value"])
            plt.title("Value over time")
            plt.xlabel("date")
            plt.ylabel("value")
            plt.xticks(rotation=30, ha="right")
            plt.tight_layout()
            plt.savefig(out_plots / "value_by_date.png", dpi=150)
            plt.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Input folder with YAML files")
    parser.add_argument("--output", required=True, help="Output folder for reports")
    args = parser.parse_args()

    input_dir = Path(args.input)
    out_dir = Path(args.output)
    plots_dir = out_dir / "plots"
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    errors = []

    yaml_files = sorted(list(input_dir.rglob("*.yml")) + list(input_dir.rglob("*.yaml")))
    if not yaml_files:
        raise SystemExit(f"No YAML files found in: {input_dir}")

    for p in yaml_files:
        try:
            data = load_yaml_file(p)
            data = normalize_dates(data)

            # Validate YAML structure
            validate(instance=data, schema=SCHEMA)

            metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}

            rows.append({
                "file": str(p),
                "name": data.get("name"),
                "value": data.get("value"),
                "tags": ",".join(data.get("tags", [])) if isinstance(data.get("tags"), list) else None,
                "date": metadata.get("date"),
            })

        except ValidationError as e:
            errors.append({"file": str(p), "error": f"Schema validation failed: {e.message}"})
        except Exception as e:
            errors.append({"file": str(p), "error": str(e)})

    df = pd.DataFrame(rows)

    # Save tabular outputs
    df.to_csv(out_dir / "summary.csv", index=False)

    summary = {
        "files_ok": len(rows),
        "files_failed": len(errors),
        "value_count": int(df["value"].count()) if not df.empty else 0,
        "value_mean": float(df["value"].mean()) if not df.empty else None,
        "value_min": float(df["value"].min()) if not df.empty else None,
        "value_max": float(df["value"].max()) if not df.empty else None,
        "plots": [
            "plots/value_hist.png",
            "plots/value_by_name.png",
            "plots/value_by_date.png",
        ],
        "errors": errors,
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    # Generate plots (even if some files failed, you still get plots for the valid rows)
    if not df.empty:
        make_plots(df, plots_dir)

    # Fail CI if there were invalid files
    if errors:
        raise SystemExit(f"Validation/parse errors in {len(errors)} file(s). See {out_dir / 'summary.json'}")


if __name__ == "__main__":
    main()

