AI STUDY BUDDY — FULL STARTER PROJECT
Created for Ruksar Banu

WHAT'S INCLUDED
- Flask website with homepage and dashboard
- PDF upload and selectable-text extraction
- SQLite database for notes and quiz scores
- Basic summary from uploaded text
- Simple practice quiz
- Basic question search through the uploaded notes
- Responsive styling
- ROADMAP.txt with all 8 project steps

RUN ON WINDOWS
1. Extract this ZIP.
2. Open the extracted AI-Study-Buddy-Full folder in VS Code.
3. Open Terminal > New Terminal.
4. Run: python -m pip install -r requirements.txt
5. Run: python app.py
6. Open: http://127.0.0.1:5000

If Python uses the Windows launcher instead, try:
py -m pip install -r requirements.txt
py app.py

IMPORTANT NOTES
- PDF upload supports PDFs with selectable text. Scanned image PDFs need OCR, not included.
- Summaries, quizzes, and answers use simple local logic; no external AI API is connected.
- A local SQLite database file is created automatically when the app runs.
- Replace the development secret key before deployment.
- Use non-sensitive practice documents while testing.
