def ai_extract_parameters(report_text, client):
    prompt = f"""
You are a medical data extractor.

Extract ALL lab parameters and their numeric values from the report below.

IMPORTANT RULES:
- For blood pressure, extract as TWO separate keys: "systolic" and "diastolic"
  e.g. BP 140/90 → {{"systolic": 140, "diastolic": 90}}
- For cholesterol, extract: "total cholesterol", "ldl", "hdl", "triglycerides" separately
- Use lowercase keys with spaces (not underscores)
- Extract EVERY parameter you can find — do not skip any
- Values must be numeric only (no units in the value)
- Return ONLY valid JSON, no explanation

Example output:
{{
  "hemoglobin": 10.5,
  "total cholesterol": 240,
  "ldl": 160,
  "hdl": 38,
  "triglycerides": 200,
  "systolic": 145,
  "diastolic": 95,
  "fasting glucose": 110,
  "creatinine": 1.4
}}

Report:
{report_text}
"""

    response = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )

    return response.choices[0].message.content
