# Comprehensive reference ranges for common lab parameters
PARAMETERS = {
    # CBC
    "hemoglobin":           {"min": 12.0,   "max": 17.5,   "unit": "g/dL"},
    "hgb":                  {"min": 12.0,   "max": 17.5,   "unit": "g/dL"},
    "wbc":                  {"min": 4000,   "max": 11000,  "unit": "cells/µL"},
    "white blood cells":    {"min": 4000,   "max": 11000,  "unit": "cells/µL"},
    "platelets":            {"min": 150000, "max": 450000, "unit": "cells/µL"},
    "platelet count":       {"min": 150000, "max": 450000, "unit": "cells/µL"},
    "rbc":                  {"min": 4.0,    "max": 6.0,    "unit": "million/µL"},
    "red blood cells":      {"min": 4.0,    "max": 6.0,    "unit": "million/µL"},
    "hematocrit":           {"min": 36.0,   "max": 52.0,   "unit": "%"},
    "hct":                  {"min": 36.0,   "max": 52.0,   "unit": "%"},
    "mcv":                  {"min": 80.0,   "max": 100.0,  "unit": "fL"},
    "mch":                  {"min": 27.0,   "max": 33.0,   "unit": "pg"},
    "mchc":                 {"min": 32.0,   "max": 36.0,   "unit": "g/dL"},
    "rdw":                  {"min": 11.5,   "max": 14.5,   "unit": "%"},
    "neutrophils":          {"min": 40.0,   "max": 75.0,   "unit": "%"},
    "lymphocytes":          {"min": 20.0,   "max": 45.0,   "unit": "%"},
    "monocytes":            {"min": 2.0,    "max": 10.0,   "unit": "%"},
    "eosinophils":          {"min": 1.0,    "max": 6.0,    "unit": "%"},
    "basophils":            {"min": 0.0,    "max": 1.0,    "unit": "%"},

    # Blood glucose
    "glucose":              {"min": 70,     "max": 100,    "unit": "mg/dL"},
    "fasting glucose":      {"min": 70,     "max": 100,    "unit": "mg/dL"},
    "blood sugar":          {"min": 70,     "max": 100,    "unit": "mg/dL"},
    "fasting blood sugar":  {"min": 70,     "max": 100,    "unit": "mg/dL"},
    "fbs":                  {"min": 70,     "max": 100,    "unit": "mg/dL"},
    "random blood sugar":   {"min": 70,     "max": 140,    "unit": "mg/dL"},
    "rbs":                  {"min": 70,     "max": 140,    "unit": "mg/dL"},
    "postprandial glucose": {"min": 70,     "max": 140,    "unit": "mg/dL"},
    "hba1c":                {"min": 4.0,    "max": 5.7,    "unit": "%"},
    "glycated hemoglobin":  {"min": 4.0,    "max": 5.7,    "unit": "%"},

    # Lipid profile
    "total cholesterol":    {"min": 0,      "max": 200,    "unit": "mg/dL"},
    "cholesterol":          {"min": 0,      "max": 200,    "unit": "mg/dL"},
    "ldl":                  {"min": 0,      "max": 100,    "unit": "mg/dL"},
    "ldl cholesterol":      {"min": 0,      "max": 100,    "unit": "mg/dL"},
    "hdl":                  {"min": 40,     "max": 9999,   "unit": "mg/dL"},
    "hdl cholesterol":      {"min": 40,     "max": 9999,   "unit": "mg/dL"},
    "triglycerides":        {"min": 0,      "max": 150,    "unit": "mg/dL"},
    "vldl":                 {"min": 2,      "max": 30,     "unit": "mg/dL"},

    # Blood pressure
    "systolic":             {"min": 90,     "max": 120,    "unit": "mmHg"},
    "systolic bp":          {"min": 90,     "max": 120,    "unit": "mmHg"},
    "diastolic":            {"min": 60,     "max": 80,     "unit": "mmHg"},
    "diastolic bp":         {"min": 60,     "max": 80,     "unit": "mmHg"},
    "blood pressure systolic": {"min": 90,  "max": 120,    "unit": "mmHg"},
    "blood pressure diastolic": {"min": 60, "max": 80,     "unit": "mmHg"},

    # Kidney function
    "creatinine":           {"min": 0.6,    "max": 1.2,    "unit": "mg/dL"},
    "serum creatinine":     {"min": 0.6,    "max": 1.2,    "unit": "mg/dL"},
    "bun":                  {"min": 7,      "max": 20,     "unit": "mg/dL"},
    "blood urea nitrogen":  {"min": 7,      "max": 20,     "unit": "mg/dL"},
    "urea":                 {"min": 15,     "max": 45,     "unit": "mg/dL"},
    "uric acid":            {"min": 3.5,    "max": 7.2,    "unit": "mg/dL"},
    "egfr":                 {"min": 60,     "max": 9999,   "unit": "mL/min"},

    # Liver function
    "alt":                  {"min": 7,      "max": 56,     "unit": "U/L"},
    "sgpt":                 {"min": 7,      "max": 56,     "unit": "U/L"},
    "ast":                  {"min": 10,     "max": 40,     "unit": "U/L"},
    "sgot":                 {"min": 10,     "max": 40,     "unit": "U/L"},
    "alkaline phosphatase": {"min": 44,     "max": 147,    "unit": "U/L"},
    "alp":                  {"min": 44,     "max": 147,    "unit": "U/L"},
    "bilirubin":            {"min": 0.1,    "max": 1.2,    "unit": "mg/dL"},
    "total bilirubin":      {"min": 0.1,    "max": 1.2,    "unit": "mg/dL"},
    "direct bilirubin":     {"min": 0.0,    "max": 0.3,    "unit": "mg/dL"},
    "albumin":              {"min": 3.5,    "max": 5.0,    "unit": "g/dL"},
    "total protein":        {"min": 6.0,    "max": 8.3,    "unit": "g/dL"},
    "ggt":                  {"min": 9,      "max": 48,     "unit": "U/L"},

    # Thyroid
    "tsh":                  {"min": 0.4,    "max": 4.0,    "unit": "mIU/L"},
    "t3":                   {"min": 80,     "max": 200,    "unit": "ng/dL"},
    "t4":                   {"min": 5.0,    "max": 12.0,   "unit": "µg/dL"},
    "free t3":              {"min": 2.3,    "max": 4.2,    "unit": "pg/mL"},
    "free t4":              {"min": 0.8,    "max": 1.8,    "unit": "ng/dL"},

    # Electrolytes
    "sodium":               {"min": 136,    "max": 145,    "unit": "mEq/L"},
    "potassium":            {"min": 3.5,    "max": 5.0,    "unit": "mEq/L"},
    "chloride":             {"min": 98,     "max": 107,    "unit": "mEq/L"},
    "calcium":              {"min": 8.5,    "max": 10.5,   "unit": "mg/dL"},
    "magnesium":            {"min": 1.7,    "max": 2.2,    "unit": "mg/dL"},
    "phosphorus":           {"min": 2.5,    "max": 4.5,    "unit": "mg/dL"},
    "bicarbonate":          {"min": 22,     "max": 29,     "unit": "mEq/L"},

    # Iron studies
    "iron":                 {"min": 60,     "max": 170,    "unit": "µg/dL"},
    "serum iron":           {"min": 60,     "max": 170,    "unit": "µg/dL"},
    "ferritin":             {"min": 12,     "max": 300,    "unit": "ng/mL"},
    "tibc":                 {"min": 250,    "max": 370,    "unit": "µg/dL"},
    "transferrin saturation": {"min": 20,   "max": 50,     "unit": "%"},

    # Vitamins
    "vitamin d":            {"min": 30,     "max": 100,    "unit": "ng/mL"},
    "vitamin b12":          {"min": 200,    "max": 900,    "unit": "pg/mL"},
    "folate":               {"min": 2.7,    "max": 17.0,   "unit": "ng/mL"},

    # Cardiac
    "troponin":             {"min": 0,      "max": 0.04,   "unit": "ng/mL"},
    "creatine kinase":      {"min": 22,     "max": 198,    "unit": "U/L"},
    "ck":                   {"min": 22,     "max": 198,    "unit": "U/L"},
    "ck-mb":                {"min": 0,      "max": 25,     "unit": "U/L"},
    "bnp":                  {"min": 0,      "max": 100,    "unit": "pg/mL"},

    # Inflammation
    "crp":                  {"min": 0,      "max": 1.0,    "unit": "mg/dL"},
    "c-reactive protein":   {"min": 0,      "max": 1.0,    "unit": "mg/dL"},
    "esr":                  {"min": 0,      "max": 20,     "unit": "mm/hr"},

    # Coagulation
    "pt":                   {"min": 11,     "max": 13.5,   "unit": "seconds"},
    "inr":                  {"min": 0.8,    "max": 1.1,    "unit": ""},
    "aptt":                 {"min": 25,     "max": 35,     "unit": "seconds"},
    "ptt":                  {"min": 25,     "max": 35,     "unit": "seconds"},
}


def analyze_report(data: dict) -> dict:
    result = {}

    for raw_key, value in data.items():
        # normalise key: lowercase + strip
        key = raw_key.strip().lower()

        # try exact match first, then partial match
        ref = PARAMETERS.get(key)
        if ref is None:
            for pkey in PARAMETERS:
                if pkey in key or key in pkey:
                    ref = PARAMETERS[pkey]
                    break

        if ref is None:
            # unknown parameter — still include it, flag as "unrecognized"
            result[raw_key] = {"value": value, "status": "unrecognized", "unit": ""}
            continue

        try:
            numeric = float(value)
        except (TypeError, ValueError):
            result[raw_key] = {"value": value, "status": "unrecognized", "unit": ref.get("unit", "")}
            continue

        if numeric < ref["min"]:
            status = "low"
        elif numeric > ref["max"]:
            status = "high"
        else:
            status = "normal"

        result[raw_key] = {
            "value": numeric,
            "status": status,
            "unit": ref.get("unit", ""),
            "reference_range": f"{ref['min']} – {ref['max']}"
        }

    return result
