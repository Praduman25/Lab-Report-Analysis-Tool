# 🩺 MediScan AI — Lab Report Analyzer  

<p align="center">
  <b>AI-powered health report analysis with instant insights, structured advice, and smart chatbot assistance.</b>
</p>

<p align="center">
  📄 Text • 🖼 Image • 📑 PDF → 📊 Insights • 🧠 AI Advice • 💬 Chatbot  
</p>

---

## 🚀 Badges  

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10-blue?style=for-the-badge" />
  <img src="https://img.shields.io/badge/Streamlit-App-red?style=for-the-badge" />
  <img src="https://img.shields.io/badge/AI-Groq_API-purple?style=for-the-badge" />
  <img src="https://img.shields.io/badge/Status-Active-success?style=for-the-badge" />
</p>





---

## 🚀 Overview  

MediScan AI is an intelligent healthcare application that analyzes lab reports from text, images, and PDFs. It extracts medical parameters, evaluates them, and generates structured explanations along with personalized health recommendations and a context-aware AI chatbot.

---

## ✨ Features  

- 📄 **Multi-Input Support** — Text, Image, and PDF uploads  
- 🤖 **AI Parameter Extraction** — Automatically detects medical values  
- 📊 **Smart Analysis Engine** — Classifies values (High / Low / Normal)  
- 🧠 **AI Summary & Advice**
  - Explanation  
  - Diet suggestions  
  - Lifestyle improvements  
  - Precautions  
- 💬 **AI Chatbot** — Context-aware responses based on report  
- 🎨 **Modern UI** — Clean Streamlit interface  
- 🛡 **Safety Guardrails** — Prevents unsafe outputs  

---

## 🛠 Tech Stack  

### Frontend
- Streamlit  
- HTML / CSS (custom styling)  

### Backend
- Python  

### AI / ML
- Groq API (`openai/gpt-oss-120b`)  

### Processing
- OCR (image & PDF extraction)  
- JSON parsing & analysis logic  

---

## 📂 Project Structure  

  lab-report-analysis-tool/
   - │
   - ├── frontend/
   - │ └── streamlit_app.py
   - │
   - ├── utils/
   - │ ├── extractor.py
   - │ ├── ai_extractor.py
   - │ └── parser.py
   - │
   - ├── chatbot/
   - │ └── memory.py
   - │
   - ├── prompts.py
   - ├── .env
   - ├── requirements.txt
   - └── README.md


---

## ⚙️ Installation  

```bash
git clone <your-repo-link>
cd lab-report-analysis-tool
pip install -r requirements.txt
```
---
🔑 Environment Setup

Create a .env file:GROQ_API_KEY=your_api_key_here

⚠️ Do not expose your API key

---
▶️ Run the App
- streamlit run frontend/streamlit_app.py

---

📌 Usage

  1️⃣ Analyze Report
    
     Select input type

     Upload or paste report

     Click Analyze Report

 2️⃣ View Results
 
     Parameter breakdown

     AI summary

 3️⃣ Chat with AI
 
     Ask health-related questions based on report


---

🛡 Guardrails

❌ No diagnosis

❌ No medicines

❌ No hallucinated data

✅ Only uses report data

✅ Rejects non-medical inputs

---

⚠️ Disclaimer

This tool is for informational purposes only and does not replace professional medical advice.

---
🔮 Future Enhancements

🔐 Login / Signup

📊 Report history

📈 Health charts

🌐 Full-stack deployment

📱 Mobile optimization

---

👨‍💻 Author

Akshat Acharya , Praduman Dadhich and Krish Lenjhara 

---

⭐ Support

If you like this project:
⭐ Star it • 🍴 Fork it • 🚀 Contribute

---


