import os
import sys
import struct
import json

SHP_PATH = r"d:\downloads\SMART INDIA HACKATHON 2026\GSHHS_i_L1.shp"
OUTPUT_JSON = r"d:\downloads\SMART INDIA HACKATHON 2026\gshhs_analysis.json"
OUTPUT_TXT = r"d:\downloads\SMART INDIA HACKATHON 2026\gshhs_analysis.txt"

def analyze_shp():
    if not os.path.exists(SHP_PATH):
        print(f"File not found: {SHP_PATH}")
        return

    file_size = os.path.getsize(SHP_PATH)
    
    # Check associated files (.dbf, .shx, .prj, .cpg)
    base_no_ext = os.path.splitext(SHP_PATH)[0]
    associated_files = {}
    for ext in ['.dbf', '.shx', '.prj', '.cpg', '.sbn', '.sbx', '.shp.xml']:
        target_path = base_no_ext + ext
        associated_files[ext] = {
            "exists": os.path.exists(target_path),
            "size": os.path.getsize(target_path) if os.path.exists(target_path) else 0
        }

    with open(SHP_PATH, 'rb') as f:
        # Read 100-byte header
        header = f.read(100)
        if len(header) < 100:
            print("File too short for shapefile header")
            return

        file_code, = struct.unpack('>i', header[0:4])
        # unused 5 ints (bytes 4-24)
        file_length_words, = struct.unpack('>i', header[24:28])
        file_length_bytes = file_length_words * 2
        version, shape_type = struct.unpack('<ii', header[28:36])
        
        # Bounding box
        xmin, ymin, xmax, ymax = struct.unpack('<4d', header[36:68])
        zmin, zmax, mmin, mmax = struct.unpack('<4d', header[68:100])

        shape_type_names = {
            0: "Null Shape",
            1: "Point",
            3: "PolyLine",
            5: "Polygon",
            8: "MultiPoint",
            11: "PointZ",
            13: "PolyLineZ",
            15: "PolygonZ",
            18: "MultiPointZ",
            21: "PointM",
            23: "PolyLineM",
            25: "PolygonM",
            28: "MultiPointM",
            31: "MultiPatch"
        }
        shape_type_name = shape_type_names.get(shape_type, f"Unknown ({shape_type})")

        # Parse records
        records = []
        total_parts_all = 0
        total_points_all = 0
        
        # Regional bounding boxes for estimation:
        # Arabian Sea: Lon [50, 77.5], Lat [5, 26]
        # Bay of Bengal: Lon [77.5, 100], Lat [5, 23]
        # Indian Ocean broader region: Lon [30, 120], Lat [-50, 30]
        # North Indian Ocean: Lon [45, 100], Lat [0, 30]
        
        regions = {
            "Indian Ocean Basin (30E-120E, 50S-30N)": {"min_lon": 30.0, "max_lon": 120.0, "min_lat": -50.0, "max_lat": 30.0, "polygons": []},
            "Arabian Sea region (50E-77.5E, 5N-26N)": {"min_lon": 50.0, "max_lon": 77.5, "min_lat": 5.0, "max_lat": 26.0, "polygons": []},
            "Bay of Bengal region (77.5E-100E, 5N-23N)": {"min_lon": 77.5, "max_lon": 100.0, "min_lat": 5.0, "max_lat": 23.0, "polygons": []},
            "India & Surrounding Subcontinent (65E-95E, 5N-38N)": {"min_lon": 65.0, "max_lon": 95.0, "min_lat": 5.0, "max_lat": 38.0, "polygons": []}
        }

        # Parse all polygon records
        while f.tell() < file_size:
            rec_header = f.read(8)
            if len(rec_header) < 8:
                break
            rec_num, content_len_words = struct.unpack('>2i', rec_header)
            content_len_bytes = content_len_words * 2
            rec_data = f.read(content_len_bytes)
            if len(rec_data) < content_len_bytes:
                break

            if content_len_bytes < 4:
                continue

            rec_shape_type, = struct.unpack('<i', rec_data[0:4])
            if rec_shape_type == 0:
                # Null shape
                records.append({
                    "rec_num": rec_num,
                    "shape_type": 0,
                    "is_null": True
                })
                continue
            
            if rec_shape_type == 5 or shape_type == 5: # Polygon
                rec_xmin, rec_ymin, rec_xmax, rec_ymax = struct.unpack('<4d', rec_data[4:36])
                num_parts, num_points = struct.unpack('<2i', rec_data[36:44])
                total_parts_all += num_parts
                total_points_all += num_points

                rec_info = {
                    "rec_num": rec_num,
                    "shape_type": rec_shape_type,
                    "bbox": [rec_xmin, rec_ymin, rec_xmax, rec_ymax],
                    "num_parts": num_parts,
                    "num_points": num_points
                }
                records.append(rec_info)

                # Check regional intersections/containment
                for reg_name, reg in regions.items():
                    # Check bounding box overlap
                    if not (rec_xmax < reg["min_lon"] or rec_xmin > reg["max_lon"] or rec_ymax < reg["min_lat"] or rec_ymin > reg["max_lat"]):
                        reg["polygons"].append(rec_num)

        # Attribute information from .dbf if available
        dbf_info = {}
        if associated_files['.dbf']['exists']:
            try:
                with open(base_no_ext + '.dbf', 'rb') as dbf_f:
                    dbf_header = dbf_f.read(32)
                    num_records, header_bytes, record_bytes = struct.unpack('<IHH', dbf_header[4:12])
                    dbf_info["num_records"] = num_records
                    dbf_info["header_bytes"] = header_bytes
                    dbf_info["record_bytes"] = record_bytes
                    
                    fields = []
                    while True:
                        field_data = dbf_f.read(32)
                        if len(field_data) == 0 or field_data[0] == 0x0D:
                            break
                        field_name = field_data[0:11].rstrip(b'\x00').decode('ascii', errors='ignore')
                        field_type = chr(field_data[11])
                        field_len = field_data[16]
                        field_dec = field_data[17]
                        fields.append({
                            "name": field_name,
                            "type": field_type,
                            "length": field_len,
                            "decimal_count": field_dec
                        })
                    dbf_info["fields"] = fields
            except Exception as e:
                dbf_info["error"] = str(e)
        else:
            dbf_info["note"] = "No .dbf file present in directory alongside .shp (standalone .shp geometry file)"

        # Check PRJ projection info
        prj_info = ""
        if associated_files['.prj']['exists']:
            try:
                with open(base_no_ext + '.prj', 'r') as prj_f:
                    prj_info = prj_f.read()
            except Exception as e:
                prj_info = f"Error reading .prj: {e}"
        else:
            prj_info = "No .prj file present. GSHHG (Global Self-consistent, Hierarchical, High-resolution Geography Database) standard CRS is Geographic WGS84 (EPSG:4326), with coordinates in decimal degrees (Longitude/Latitude)."

        # Polygon size distribution
        point_counts = [r["num_points"] for r in records if "num_points" in r]
        part_counts = [r["num_parts"] for r in records if "num_parts" in r]

        # Top 10 largest features by point count
        top_features = sorted(records, key=lambda x: x.get("num_points", 0), reverse=True)[:10]

        summary = {
            "file_path": SHP_PATH,
            "file_size_bytes": file_size,
            "file_size_mb": round(file_size / (1024 * 1024), 3),
            "file_code": file_code,
            "file_code_valid": file_code == 9994,
            "header_file_length_bytes": file_length_bytes,
            "version": version,
            "geometry_type": shape_type_name,
            "geometry_type_id": shape_type,
            "crs_projection": {
                "declared_in_prj": associated_files['.prj']['exists'],
                "prj_content": prj_info,
                "standard_crs": "WGS 84 (EPSG:4326)",
                "coordinate_units": "Decimal Degrees (Longitude, Latitude)"
            },
            "bounding_box": {
                "xmin_west_lon": xmin,
                "ymin_south_lat": ymin,
                "xmax_east_lon": xmax,
                "ymax_north_lat": ymax
            },
            "z_range": [zmin, zmax],
            "m_range": [mmin, mmax],
            "feature_counts": {
                "total_features": len(records),
                "total_parts": total_parts_all,
                "total_vertices": total_points_all,
                "min_points_per_feature": min(point_counts) if point_counts else 0,
                "max_points_per_feature": max(point_counts) if point_counts else 0,
                "avg_points_per_feature": round(sum(point_counts) / len(point_counts), 2) if point_counts else 0,
                "min_parts_per_feature": min(part_counts) if part_counts else 0,
                "max_parts_per_feature": max(part_counts) if part_counts else 0
            },
            "associated_files": associated_files,
            "attribute_schema": dbf_info,
            "regional_polygon_counts": {
                k: {
                    "bounding_box": [v["min_lon"], v["min_lat"], v["max_lon"], v["max_lat"]],
                    "overlapping_polygons_count": len(v["polygons"]),
                    "sample_record_ids": v["polygons"][:10]
                }
                for k, v in regions.items()
            },
            "top_10_largest_polygons_by_vertices": top_features
        }

        # Write JSON output
        with open(OUTPUT_JSON, 'w') as jf:
            json.dump(summary, jf, indent=2)

        # Print formatted report
        report_lines = [
            "=" * 70,
            "GSHHG SHORELINE SHAPEFILE ANALYSIS REPORT",
            "=" * 70,
            f"File: {SHP_PATH}",
            f"File Size: {file_size:,} bytes ({file_size / (1024*1024):.2f} MB)",
            f"Shapefile Format Valid: {'YES (Code 9994)' if file_code == 9994 else 'NO'}",
            f"Geometry Type: {shape_type_name} (Type ID: {shape_type})",
            f"Total Number of Features / Polygons: {len(records):,}",
            f"Total Parts: {total_parts_all:,}",
            f"Total Vertices / Points: {total_points_all:,}",
            "",
            "--- COORDINATE REFERENCE SYSTEM (CRS) & EXTENT ---",
            f"Standard Projection: WGS 84 (EPSG:4326) - Geographic Lat/Lon",
            f".prj file present: {'Yes' if associated_files['.prj']['exists'] else 'No (Standard GSHHG EPSG:4326 assumed)'}",
            f"Global Bounding Box Extent:",
            f"  Longitude (X): [{xmin:.6f}°, {xmax:.6f}°] (West to East)",
            f"  Latitude  (Y): [{ymin:.6f}°, {ymax:.6f}°] (South to North)",
            "",
            "--- ATTRIBUTE COLUMNS / DBF SCHEMA ---",
            f".dbf file present: {'Yes' if associated_files['.dbf']['exists'] else 'No (.shp standalone)'}",
        ]
        
        if associated_files['.dbf']['exists'] and "fields" in dbf_info:
            report_lines.append("Attributes:")
            for fld in dbf_info["fields"]:
                report_lines.append(f"  - {fld['name']} (Type: {fld['type']}, Len: {fld['length']})")
        else:
            report_lines.append("  Note: GSHHG Level 1 shapefile contains purely shoreline vector geometry.")
            report_lines.append("  Standard GSHHG attributes in full distributions include ID, Level (1=land/ocean), Source, Area (km²).")

        report_lines.extend([
            "",
            "--- REGIONAL ANALYSIS (INDIAN OCEAN / ARABIAN SEA / BAY OF BENGAL) ---",
        ])

        for k, v in regions.items():
            report_lines.append(f"• {k}:")
            report_lines.append(f"    Bounding Box: Lon [{v['min_lon']}° to {v['max_lon']}°], Lat [{v['min_lat']}° to {v['max_lat']}°]")
            report_lines.append(f"    Overlapping Shoreline Polygons / Landmass Features: {len(v['polygons']):,}")

        report_lines.extend([
            "",
            "--- GSHHS HIERARCHY CONTEXT ---",
            "GSHHS Level 1 (L1) = Continental landmasses and ocean islands (shorelines separating ocean from land).",
            "Intermediate resolution ('i') = ~1 km shoreline accuracy, optimal for regional ocean routing & bathymetry masking.",
            "=" * 70
        ])

        report_text = "\n".join(report_lines)
        print(report_text)

        with open(OUTPUT_TXT, 'w') as tf:
            tf.write(report_text)

if __name__ == "__main__":
    analyze_shp()
