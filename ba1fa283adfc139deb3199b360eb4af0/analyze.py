"""
Comprehensive NetCDF Dataset Analyzer for ERA5 Atmospheric & Wave Streams
Target Datasets:
1. data_stream-oper_stepType-instant.nc (Atmospheric Oper Stream)
2. data_stream-wave_stepType-instant.nc (Ocean Wave Model Stream)
"""

import os
import sys
import json
import traceback

def analyze_dataset(file_path):
    print(f"\n{'='*70}\nAnalyzing: {os.path.basename(file_path)}\n{'='*70}")
    
    # Try xarray first, then netCDF4
    ds = None
    engine_used = None
    try:
        import xarray as xr
        import numpy as np
        ds = xr.open_dataset(file_path)
        engine_used = "xarray"
    except Exception as e_xr:
        print(f"xarray open failed ({e_xr}), trying netCDF4...")
        try:
            from netCDF4 import Dataset
            import numpy as np
            nc = Dataset(file_path, 'r')
            engine_used = "netCDF4"
        except Exception as e_nc:
            print(f"netCDF4 open failed ({e_nc})")
            return None

    report = {
        "file_name": os.path.basename(file_path),
        "file_size_bytes": os.path.getsize(file_path),
        "file_size_mb": round(os.path.getsize(file_path) / (1024 * 1024), 2),
        "engine": engine_used,
        "dimensions": {},
        "coordinates": {},
        "variables": {},
        "global_attributes": {}
    }

    if engine_used == "xarray":
        report["dimensions"] = {k: int(v) for k, v in ds.dims.items()}
        report["global_attributes"] = {k: str(v) for k, v in ds.attrs.items()}

        # Coordinates
        for cname, coord in ds.coords.items():
            vals = coord.values
            c_info = {
                "dims": list(coord.dims),
                "shape": list(coord.shape),
                "dtype": str(coord.dtype),
                "attrs": {k: str(v) for k, v in coord.attrs.items()}
            }
            if np.issubdtype(coord.dtype, np.datetime64):
                c_info["min"] = str(vals.min())
                c_info["max"] = str(vals.max())
                c_info["count"] = int(len(vals))
                c_info["first_5_timestamps"] = [str(t) for t in vals[:5]]
                c_info["last_5_timestamps"] = [str(t) for t in vals[-5:]]
                if len(vals) > 1:
                    dt_diff = vals[1] - vals[0]
                    c_info["time_step"] = str(dt_diff)
            else:
                c_info["min"] = float(np.nanmin(vals))
                c_info["max"] = float(np.nanmax(vals))
                c_info["count"] = int(len(vals))
                if len(vals) > 1:
                    c_info["resolution"] = float(vals[1] - vals[0])
                c_info["first_5_values"] = [float(x) for x in vals[:5]]
                c_info["last_5_values"] = [float(x) for x in vals[-5:]]
            report["coordinates"][cname] = c_info

        # Variables
        for vname, var in ds.data_vars.items():
            vals = var.values
            valid_vals = vals[~np.isnan(vals)]
            v_info = {
                "dims": list(var.dims),
                "shape": list(var.shape),
                "dtype": str(var.dtype),
                "units": var.attrs.get("units", "N/A"),
                "long_name": var.attrs.get("long_name", var.attrs.get("standard_name", "N/A")),
                "attributes": {k: str(v) for k, v in var.attrs.items()},
                "total_elements": int(vals.size),
                "valid_elements": int(len(valid_vals)),
                "nan_elements": int(np.isnan(vals).sum()),
                "min": float(np.nanmin(valid_vals)) if len(valid_vals) > 0 else None,
                "max": float(np.nanmax(valid_vals)) if len(valid_vals) > 0 else None,
                "mean": float(np.nanmean(valid_vals)) if len(valid_vals) > 0 else None,
                "std": float(np.nanstd(valid_vals)) if len(valid_vals) > 0 else None,
                "sample_values_flat_first_10": [float(x) for x in valid_vals[:10]] if len(valid_vals) > 0 else []
            }
            report["variables"][vname] = v_info

    return report

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    files = [
        "data_stream-oper_stepType-instant.nc",
        "data_stream-wave_stepType-instant.nc"
    ]
    
    all_reports = {}
    for f in files:
        fpath = os.path.join(base_dir, f)
        if os.path.exists(fpath):
            res = analyze_dataset(fpath)
            if res:
                all_reports[f] = res
        else:
            print(f"File not found: {fpath}")

    # Output paths
    json_path = os.path.join(base_dir, "netcdf_analysis_summary.json")
    with open(json_path, "w", encoding="utf-8") as jf:
        json.dump(all_reports, jf, indent=2)
    print(f"\nAnalysis written to {json_path}")

    # Generate Markdown Report
    md_path = os.path.join(base_dir, "netcdf_analysis_report.md")
    with open(md_path, "w", encoding="utf-8") as mf:
        mf.write("# NetCDF Dataset Schema & Scientific Analysis Report\n\n")
        for fname, data in all_reports.items():
            mf.write(f"## Dataset: `{fname}`\n")
            mf.write(f"- **File Size**: {data['file_size_mb']} MB ({data['file_size_bytes']:,} bytes)\n")
            mf.write(f"- **Dimensions**: `{data['dimensions']}`\n\n")
            
            mf.write("### Coordinates\n\n")
            mf.write("| Coordinate | Dimensions | Count | Range (Min → Max) | Resolution / Step | Units |\n")
            mf.write("|---|---|---|---|---|---|\n")
            for cname, cinfo in data["coordinates"].items():
                units = cinfo.get("attrs", {}).get("units", "N/A")
                res = cinfo.get("resolution", cinfo.get("time_step", "N/A"))
                mf.write(f"| `{cname}` | `{cinfo['dims']}` | {cinfo['count']} | `{cinfo['min']}` → `{cinfo['max']}` | `{res}` | {units} |\n")
            
            mf.write("\n### Data Variables\n\n")
            mf.write("| Variable | Long Name | Units | Dimensions / Shape | Range (Min / Max) | Mean ± Std |\n")
            mf.write("|---|---|---|---|---|---|\n")
            for vname, vinfo in data["variables"].items():
                rng = f"[{vinfo['min']:.3f}, {vinfo['max']:.3f}]" if vinfo['min'] is not None else "N/A"
                stats = f"{vinfo['mean']:.3f} ± {vinfo['std']:.3f}" if vinfo['mean'] is not None else "N/A"
                mf.write(f"| `{vname}` | {vinfo['long_name']} | `{vinfo['units']}` | `{vinfo['shape']}` | {rng} | {stats} |\n")
            
            mf.write("\n---\n\n")
    print(f"Markdown report written to {md_path}")

if __name__ == "__main__":
    main()
