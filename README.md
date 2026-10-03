# 📍 Place History Explorer

Place History Explorer is an AI-powered travel companion that helps
users discover the history and story behind places they visit.

Users can upload a photo of a landmark, monument, historical building,
or notable place. Gemini Vision analyzes the image and provides useful
information about the place, including its location, history,
architecture, cultural significance, and interesting facts.

Users can also ask follow-up questions, save visited places, and email
their saved travel history.

## ✨ Features

- 📸 Upload a photo of a place
- 📍 Add an optional location name
- 🤖 Analyze places using Gemini Vision
- 📜 Learn the history of a place
- 💬 Ask follow-up questions
- 🗺️ Save visited places
- 📅 Store the visit date
- 📧 Verify user email with a 6-digit code
- 📩 Send saved travel history by email

## 🛠️ Technologies Used

- Python
- Streamlit
- Google Gemini
- SQLite
- Gmail SMTP

## 📁 Project Structure

```text
place-history-explorer/
├── app.py
├── prompts.py
├── database.py
├── requirements.txt
├── README.md
├── .gitignore
└── .streamlit/
    └── secrets.toml.example