import os
import yaml

base_dir = "d:/downloads/SMART INDIA HACKATHON 2026/qml_route_search"

init_files = [
    "src/__init__.py",
    "src/hard_filters/__init__.py",
    "src/search/__init__.py",
    "src/safety/__init__.py",
    "src/rerouting/__init__.py",
    "src/output/__init__.py",
    "api/__init__.py"
]

for f in init_files:
    p = os.path.join(base_dir, f)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as file:
        file.write(f'"""{f} module."""\n')

yaml_dir = os.path.join(base_dir, "config/vessels")
os.makedirs(yaml_dir, exist_ok=True)

vessels = {
    "sci_chennai.yaml": {
        "name": "SCI Chennai", "imo": "9418298", "type": "Container Panamax",
        "loa_m": 262.0, "beam_m": 32.2, "draft_design_m": 11.5, "draft_max_m": 13.2,
        "dwt_mt": 57813, "depth_m": 19.3, "service_speed_kn": 23.5, "eco_speed_kn": 16.5,
        "engine": {"model": "Sulzer 8RTA82C", "type": "Main", "mcr_kw": 36160, "ncr_kw": 30736, "rpm_mcr": 102},
        "sfoc_curve": {25: 196, 50: 175, 75: 167, 85: 166, 100: 171},
        "roll": {"gm_loaded_m": 1.45, "gm_ballast_m": 2.40, "t_roll_loaded_s": 24.2, "t_roll_ballast_s": 18.8, "k_xx_factor": 0.39}
    },
    "ssl_bharat.yaml": {
        "name": "SSL Bharat", "imo": "9141314", "type": "Container Feeder",
        "loa_m": 195.73, "beam_m": 32.25, "draft_design_m": 11.51, "draft_max_m": 11.51,
        "dwt_mt": 34670, "depth_m": 16.4, "service_speed_kn": 16.0, "eco_speed_kn": 14.0,
        "engine": {"model": "MAN B&W 8S70MC", "type": "Main", "mcr_kw": 22480, "ncr_kw": 19108, "rpm_mcr": 91},
        "sfoc_curve": {25: 186, 50: 173, 75: 165, 85: 163, 100: 168},
        "roll": {"gm_loaded_m": 1.80, "gm_ballast_m": 2.80, "t_roll_loaded_s": 20.5, "t_roll_ballast_s": 16.5, "k_xx_factor": 0.38}
    },
    "desh_shobha.yaml": {
        "name": "Desh Shobha", "imo": "9459046", "type": "Suezmax Tanker",
        "loa_m": 274.33, "beam_m": 48.0, "draft_design_m": 16.0, "draft_max_m": 17.2,
        "dwt_mt": 158034, "depth_m": 23.2, "service_speed_kn": 15.0, "eco_speed_kn": 13.0,
        "engine": {"model": "MAN B&W 6S70MC-C", "type": "Main", "mcr_kw": 18660, "ncr_kw": 15861, "rpm_mcr": 91},
        "sfoc_curve": {25: 191, 50: 172, 75: 164, 85: 162, 100: 167},
        "roll": {"gm_loaded_m": 5.20, "gm_ballast_m": 7.80, "t_roll_loaded_s": 14.8, "t_roll_ballast_s": 12.1, "k_xx_factor": 0.40}
    },
    "desh_viraat.yaml": {
        "name": "Desh Viraat", "imo": "9371593", "type": "VLCC",
        "loa_m": 333.0, "beam_m": 60.0, "draft_design_m": 22.5, "draft_max_m": 22.5,
        "dwt_mt": 316635, "depth_m": 30.5, "service_speed_kn": 15.2, "eco_speed_kn": 13.5,
        "engine": {"model": "Sulzer 7RTA84TD", "type": "Main", "mcr_kw": 27180, "ncr_kw": 23103, "rpm_mcr": 76},
        "sfoc_curve": {25: 188, 50: 173, 75: 164, 85: 163, 100: 168},
        "roll": {"gm_loaded_m": 5.80, "gm_ballast_m": 8.50, "t_roll_loaded_s": 17.2, "t_roll_ballast_s": 14.2, "k_xx_factor": 0.41}
    },
    "swarna_pushp.yaml": {
        "name": "Swarna Pushp", "imo": "9432672", "type": "MR2 Product Tanker",
        "loa_m": 184.95, "beam_m": 32.23, "draft_design_m": 12.32, "draft_max_m": 12.32,
        "dwt_mt": 47795, "depth_m": 18.2, "service_speed_kn": 14.5, "eco_speed_kn": 12.5,
        "engine": {"model": "MAN B&W 6S50MC-C", "type": "Main", "mcr_kw": 9480, "ncr_kw": 8058, "rpm_mcr": 127},
        "sfoc_curve": {25: 192, 50: 174, 75: 166, 85: 165, 100: 170},
        "roll": {"gm_loaded_m": 3.20, "gm_ballast_m": 5.50, "t_roll_loaded_s": 13.1, "t_roll_ballast_s": 10.0, "k_xx_factor": 0.38}
    },
    "vishva_chetna.yaml": {
        "name": "Vishva Chetna", "imo": "9603893", "type": "Kamsarmax Bulk",
        "loa_m": 229.0, "beam_m": 32.26, "draft_design_m": 12.2, "draft_max_m": 14.45,
        "dwt_mt": 81733, "depth_m": 20.25, "service_speed_kn": 14.2, "eco_speed_kn": 12.0,
        "engine": {"model": "MAN B&W 5S60MC-C", "type": "Main", "mcr_kw": 9929, "ncr_kw": 8440, "rpm_mcr": 105},
        "sfoc_curve": {25: 193, 50: 173, 75: 164, 85: 163, 100: 168},
        "roll": {"gm_loaded_m": 2.80, "gm_ballast_m": 4.60, "t_roll_loaded_s": 14.6, "t_roll_ballast_s": 11.4, "k_xx_factor": 0.39}
    },
    "vishva_vijeta.yaml": {
        "name": "Vishva Vijeta", "imo": "9621699", "type": "Supramax Bulk",
        "loa_m": 190.0, "beam_m": 32.26, "draft_design_m": 12.8, "draft_max_m": 12.8,
        "dwt_mt": 56800, "depth_m": 18.0, "service_speed_kn": 14.0, "eco_speed_kn": 12.0,
        "engine": {"model": "Wartsila 6RT-flex50", "type": "Main", "mcr_kw": 9480, "ncr_kw": 8058, "rpm_mcr": 124},
        "sfoc_curve": {25: 185, 50: 168, 75: 164, 85: 164, 100: 169},
        "roll": {"gm_loaded_m": 2.50, "gm_ballast_m": 4.20, "t_roll_loaded_s": 15.3, "t_roll_ballast_s": 11.8, "k_xx_factor": 0.38}
    },
    "jsw_pratapgad.yaml": {
        "name": "JSW Pratapgad", "imo": "9797321", "type": "Coastal Mini-Bulker",
        "loa_m": 122.25, "beam_m": 20.0, "draft_design_m": 4.8, "draft_max_m": 4.8,
        "dwt_mt": 8000, "depth_m": 7.2, "service_speed_kn": 11.0, "eco_speed_kn": 9.5,
        "engine": {"model": "Yanmar 6EY22AW", "type": "Main", "mcr_kw": 1400, "ncr_kw": 1190, "rpm_mcr": 900},
        "sfoc_curve": {25: 224, 50: 199, 75: 191, 85: 189, 100: 193},
        "roll": {"gm_loaded_m": 1.85, "gm_ballast_m": 2.50, "t_roll_loaded_s": 10.5, "t_roll_ballast_s": 9.0, "k_xx_factor": 0.37}
    },
    "sci_panna.yaml": {
        "name": "SCI Panna", "imo": "9524889", "type": "AHTS/OSV",
        "loa_m": 64.8, "beam_m": 15.7, "draft_design_m": 5.81, "draft_max_m": 5.81,
        "dwt_mt": 1997, "depth_m": 7.0, "service_speed_kn": 12.5, "eco_speed_kn": 11.0,
        "engine": {"model": "2x MaK 8M25", "type": "Main", "mcr_kw": 4800, "ncr_kw": 4080, "rpm_mcr": 750},
        "sfoc_curve": {25: 216, 50: 194, 75: 185, 85: 183, 100: 187},
        "roll": {"gm_loaded_m": 1.25, "gm_ballast_m": 2.10, "t_roll_loaded_s": 9.8, "t_roll_ballast_s": 7.6, "k_xx_factor": 0.36}
    },
    "ins_deepak.yaml": {
        "name": "INS Deepak", "imo": "A50", "type": "Naval Fleet Replenishment",
        "loa_m": 175.0, "beam_m": 25.0, "draft_design_m": 9.1, "draft_max_m": 9.1,
        "dwt_mt": 27550, "depth_m": 14.0, "service_speed_kn": 20.0, "eco_speed_kn": 16.0,
        "engine": {"model": "2x MAN 14V32/44CR", "type": "Main", "mcr_kw": 19200, "ncr_kw": 16320, "rpm_mcr": None},
        "sfoc_curve": {25: 195, 50: 178, 75: 174, 85: 172, 100: 177},
        "roll": {"gm_loaded_m": 1.80, "gm_ballast_m": 3.20, "t_roll_loaded_s": 13.25, "t_roll_ballast_s": 10.0, "k_xx_factor": 0.38}
    }
}

for fname, data in vessels.items():
    p = os.path.join(yaml_dir, fname)
    with open(p, "w") as file:
        yaml.dump(data, file, sort_keys=False)
