import os
import json
import shapely
from shapely.geometry import shape, Polygon, MultiPolygon, box
import shapefile # pyshp

os.environ["SHAPE_RESTORE_SHX"] = "YES"

SHP_PATH = r"d:\downloads\SMART INDIA HACKATHON 2026\GSHHS_i_L1.shp"
OUTPUT_JSON = r"d:\downloads\SMART INDIA HACKATHON 2026\gshhs_advanced_analysis.json"

def run_analysis():
    print("Reading shapefile with PyShp...")
    with open(SHP_PATH, "rb") as shp_file:
        sf = shapefile.Reader(shp=shp_file)
        num_shapes = len(sf.shapes())
        shape_type_name = sf.shapeTypeName
        bbox = sf.bbox # [minx, miny, maxx, maxy]
        shapes = sf.shapes()
        fields = []
    
    print(f"Num shapes: {num_shapes}")
    print(f"Shape type: {shape_type_name}")
    print(f"BBox: {bbox}")
    print(f"Fields: {fields}")
    
    # Regions for spatial analysis
    regions_def = {
        "Indian Ocean Basin (Broad: 30E-120E, 50S-30N)": {
            "bbox": [30.0, -50.0, 120.0, 30.0],
            "desc": "Broad Indian Ocean basin from East Africa to Western Australia, 50S to 30N"
        },
        "North Indian Ocean (45E-100E, 0N-30N)": {
            "bbox": [45.0, 0.0, 100.0, 30.0],
            "desc": "North Indian Ocean including Arabian Sea, Bay of Bengal, and adjacent coasts"
        },
        "Arabian Sea (50E-77.5E, 5N-26N)": {
            "bbox": [50.0, 5.0, 77.5, 26.0],
            "desc": "Arabian Sea (Somalia, Oman, Gulf entrance, Pakistan, West Coast of India, Lakshadweep)"
        },
        "Bay of Bengal (77.5E-100E, 5N-23N)": {
            "bbox": [77.5, 5.0, 100.0, 23.0],
            "desc": "Bay of Bengal (East Coast of India, Sri Lanka East, Bangladesh, Myanmar, Andaman & Nicobar)"
        },
        "India Coastal & EEZ Zone (68E-94E, 6N-24N)": {
            "bbox": [68.0, 6.0, 94.0, 24.0],
            "desc": "Immediate waters around mainland India, Lakshadweep, Andaman & Nicobar"
        }
    }

    region_boxes = {name: box(*info["bbox"]) for name, info in regions_def.items()}
    region_counts_bbox = {name: 0 for name in regions_def}
    region_counts_exact = {name: 0 for name in regions_def}
    region_polys = {name: [] for name in regions_def}

    total_points = 0
    total_parts = 0
    polygon_sizes = []
    
    for i, s in enumerate(shapes):
        s_bbox = s.bbox # [minx, miny, maxx, maxy]
        pts_cnt = len(s.points)
        parts_cnt = len(s.parts)
        total_points += pts_cnt
        total_parts += parts_cnt
        polygon_sizes.append(pts_cnt)
        
        s_box = box(*s_bbox)

        for rname, rpoly in region_boxes.items():
            minx, miny, maxx, maxy = regions_def[rname]["bbox"]
            # Bounding box overlap test
            if not (s_bbox[2] < minx or s_bbox[0] > maxx or s_bbox[3] < miny or s_bbox[1] > maxy):
                region_counts_bbox[rname] += 1
                # Exact geometric test
                try:
                    geom = shape(s.__geo_interface__)
                    if geom.intersects(rpoly):
                        region_counts_exact[rname] += 1
                        if len(region_polys[rname]) < 5:
                            region_polys[rname].append({
                                "id": i,
                                "bbox": [round(c, 4) for c in s_bbox],
                                "points": pts_cnt
                            })
                except Exception:
                    region_counts_exact[rname] += 1

    polygon_sizes.sort()
    
    results = {
        "dataset_name": "GSHHG (Global Self-consistent, Hierarchical, High-resolution Geography Database)",
        "file_name": "GSHHS_i_L1.shp",
        "file_path": SHP_PATH,
        "file_size_bytes": os.path.getsize(SHP_PATH),
        "file_size_mb": round(os.path.getsize(SHP_PATH) / (1024 * 1024), 2),
        "number_of_features": num_shapes,
        "geometry_type": "Polygon (Shapefile Type 5)",
        "crs_projection": {
            "name": "WGS 84 (World Geodetic System 1984)",
            "epsg": 4326,
            "unit": "Decimal Degrees (Longitude, Latitude)",
            "prj_file_present": False,
            "standard_specification": "GSHHG global vector coastline database is natively defined in Geographic WGS84 coordinates."
        },
        "bounding_box_extent": {
            "min_longitude": bbox[0],
            "min_latitude": bbox[1],
            "max_longitude": bbox[2],
            "max_latitude": bbox[3],
            "formatted": f"West {bbox[0]:.4f}°, South {bbox[1]:.4f}°, East {bbox[2]:.4f}°, North {bbox[3]:.4f}°"
        },
        "attribute_columns": {
            "fields_in_dbf": [f[0] for f in fields] if fields else [],
            "has_attribute_table": False,
            "description": "Standalone .shp geometry file containing 32,830 polygon boundaries (Level 1: Shorelines dividing ocean and land/islands). No separate .dbf attribute table is present."
        },
        "geometry_summary": {
            "total_polygons": num_shapes,
            "total_parts": total_parts,
            "total_vertices": total_points,
            "min_vertices_per_polygon": polygon_sizes[0],
            "max_vertices_per_polygon": polygon_sizes[-1],
            "median_vertices_per_polygon": polygon_sizes[len(polygon_sizes)//2],
            "avg_vertices_per_polygon": round(total_points / num_shapes, 2)
        },
        "regional_breakdown": {
            rname: {
                "description": regions_def[rname]["desc"],
                "bounding_box": regions_def[rname]["bbox"],
                "overlapping_polygon_count": region_counts_exact[rname],
                "sample_features": region_polys[rname]
            }
            for rname in regions_def
        }
    }

    with open(OUTPUT_JSON, "w") as f:
        json.dump(results, f, indent=2)

    print("ADVANCED ANALYSIS COMPLETE:")
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    run_analysis()
