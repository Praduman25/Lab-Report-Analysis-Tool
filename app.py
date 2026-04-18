import os
from dotenv import load_dotenv
from groq import Groq
from prompts import explain_report_prompt
from utils.extractor import extract_text_from_pdf, extract_text_from_image
from utils.ai_extractor import ai_extract_parameters
from chatbot.memory import trim_history, summarize_memory
import json

# STEP 1: Load .env file
load_dotenv(dotenv_path=".env")

# STEP 2: Get API key
api_key = os.getenv("GROQ_API_KEY")

# STEP 3: Safety check
if not api_key:
    raise ValueError("❌ API key not found. Check your .env file")

# STEP 4: Create client
client = Groq(api_key=api_key)

# ✅ STEP 5: RESPONSE FUNCTION
def get_response(prompt):
    try:
        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {
                    "role": "system",
                    "content": """
You are an AI medical assistant.

You MUST follow this format strictly:

🧠 Explanation:
(4-5 sentences)

💡 Key Advice:

Diet:
- Give 3-4 specific food suggestions

Lifestyle:
- Give 2-3 daily routine tips

Precautions:
- Give 2-3 warnings

STRICT RULES:
- NEVER mention doctors
- NEVER write everything in one paragraph
- ALWAYS follow headings exactly
- ALWAYS give specific advice
"""
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.2
        )

        return response.choices[0].message.content

    except Exception as e:
        return f"❌ Error: {str(e)}"


# STEP 6: MAIN EXECUTION
if __name__ == "__main__":

    print("\n🩺 Lab Report Analyzer AI")
    print("Type 'exit' to quit\n")

    while True:
        choice = input("Choose input type (1 = Text, 2 = Image, 3 = PDF): ")

        if choice.lower() in ["exit", "quit"]:
            print("👋 Exiting... Stay healthy!")
            break

        try:
            # 🔹 INPUT
            if choice == "1":
                report_text = input("📄 Enter lab report details: ")

            elif choice == "2":
                file_path = input("🖼️ Enter image path: ")
                report_text = extract_text_from_image(file_path)

            elif choice == "3":
                file_path = input("📄 Enter PDF path: ")
                report_text = extract_text_from_pdf(file_path)

            else:
                print("⚠️ Invalid choice\n")
                continue

            if not report_text.strip():
                print("⚠️ No text extracted.\n")
                continue

            print("\n📄 Extracted Text:\n", report_text[:300])

            # 🔥 STEP A: AI EXTRACTION
            ai_data = ai_extract_parameters(report_text, client)
            ai_data = ai_data.strip().replace("```json", "").replace("```", "")

            try:
                parsed_data = json.loads(ai_data)
            except:
                print("❌ JSON parsing failed")
                parsed_data = {}

            # 🔥 STEP B: ANALYSIS
            from utils.parser import analyze_report
            final_data = analyze_report(parsed_data)

            print("\n📊 Final Analyzed Data:\n", final_data)

            # 🔥 STEP C: SUMMARY
            prompt = explain_report_prompt(str(final_data))
            response = get_response(prompt)

            print("\n🧠 Summary & Key Advice:\n", response)
            print("\n💡 For detailed diet & routine, use the chatbot below!")
            print("\n" + "-"*60 + "\n")

            # ✅ STEP C2: CONDITIONS
            conditions = []

            for param, details in final_data.items():
                status = details.get("status", "").lower()

                if status == "low":
                    conditions.append(f"{param} is low")
                elif status == "high":
                    conditions.append(f"{param} is high")

            if not conditions:
                conditions.append("All parameters are normal")

            # 🔥 STEP D: CHATBOT
            system_prompt = f"""
You are a smart AI medical assistant.

Patient Report:
{final_data}

Detected Conditions:
{conditions}

Your job:
- Answer ONLY based on this patient’s data
- Give personalized diet, lifestyle, precautions
- Explain reasons clearly

STRICT RULES:
- DO NOT give generic answers
- ALWAYS refer to patient condition
- Be specific (mention exact foods, habits)
- Keep answers structured

Always end with:
"This is not a medical diagnosis."
"""

            chat_history = [
                {"role": "system", "content": system_prompt}
            ]

            memory_summary = ""
            MAX_HISTORY = 8

            print("\n💬 Chat with AI Assistant (type 'exit' to stop)\n")

            while True:
                user_q = input("You: ")

                if user_q.lower() in ["exit", "quit"]:
                    print("👋 Exiting chatbot...\n")
                    break

                # ✅ MEMORY VIEW COMMAND
                if user_q.lower() == "memory":
                    print("\n🧠 Memory:\n", memory_summary)
                    continue

                # ✅ CONTEXT REMINDER
                user_q = f"""
Patient condition: {conditions}

User question: {user_q}
"""

                chat_history.append({
                    "role": "user",
                    "content": user_q
                })

                # ✅ Inject memory summary
                if memory_summary:
                    chat_history.insert(1, {
                        "role": "system",
                        "content": f"Previous context: {memory_summary}"
                    })

                response = client.chat.completions.create(
                    model="openai/gpt-oss-120b",
                    messages=chat_history,
                    temperature=0.3
                )

                reply = response.choices[0].message.content

                print("\n🤖:", reply, "\n")

                chat_history.append({
                    "role": "assistant",
                    "content": reply
                })

                # ✅ TRIM HISTORY
                chat_history = trim_history(chat_history, MAX_HISTORY)

                # ✅ SUMMARIZE MEMORY
                if len(chat_history) >= MAX_HISTORY:
                    memory_summary = summarize_memory(chat_history, client)

                    chat_history = [
                        {"role": "system", "content": system_prompt},
                        {"role": "system", "content": f"Previous context: {memory_summary}"}
                    ]

        except Exception as e:
            print(f"❌ Error: {str(e)}")