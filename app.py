import os
import re
import sqlite3
from datetime import datetime
from collections import Counter

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
)
from werkzeug.utils import secure_filename

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None


# ==================================================
# APPLICATION CONFIGURATION
# ==================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY",
    "local-development-key-change-before-deployment"
)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
DATABASE = os.path.join(BASE_DIR, "study_buddy.db")

ALLOWED_EXTENSIONS = {"pdf"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024

os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# ==================================================
# DATABASE
# ==================================================

def get_db():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                extracted_text TEXT NOT NULL DEFAULT '',
                uploaded_at TEXT NOT NULL
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS quiz_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT NOT NULL,
                score INTEGER NOT NULL,
                total INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
        """)


def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def latest_notes():
    with get_db() as db:
        return db.execute("""
            SELECT *
            FROM notes
            ORDER BY id DESC
            LIMIT 1
        """).fetchone()


# ==================================================
# TEXT PROCESSING
# ==================================================

STOP_WORDS = {
    "the", "and", "for", "are", "was", "were", "with",
    "this", "that", "from", "have", "has", "had", "not",
    "but", "you", "your", "our", "they", "them", "their",
    "what", "when", "where", "which", "who", "why", "how",
    "can", "could", "would", "should", "will", "shall",
    "may", "might", "must", "into", "onto", "over", "under",
    "between", "among", "after", "before", "about", "also",
    "been", "being", "because", "while", "during", "there",
    "here", "then", "than", "these", "those", "such", "some",
    "more", "most", "other", "each", "every", "only", "very",
    "all", "any", "both", "few", "many", "much", "own",
    "its", "itself", "through", "within", "without", "use",
    "used", "using", "does", "did", "doing", "done", "get",
    "got", "make", "made", "like", "well", "per", "one",
    "two", "three", "four", "five", "etc", "example"
}


def clean_text(text):
    """Clean PDF text while preserving paragraphs."""

    if not text:
        return ""

    text = text.replace("\x00", " ")
    text = text.replace("\r", "\n")

    # Join words split across PDF lines.
    text = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", text)

    # Normalize spaces and excessive blank lines.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def split_sentences(text):
    """Split text into sentences."""

    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        return []

    sentences = re.split(r"(?<=[.!?])\s+", text)

    return [
        sentence.strip()
        for sentence in sentences
        if sentence.strip()
    ]


def get_keywords(text, limit=20):
    """Extract frequently occurring meaningful keywords."""

    words = re.findall(
        r"\b[A-Za-z][A-Za-z'-]{2,}\b",
        text.lower()
    )

    meaningful_words = [
        word for word in words
        if word not in STOP_WORDS
    ]

    counts = Counter(meaningful_words)

    return [
        word for word, _count in counts.most_common(limit)
    ]


# ==================================================
# FULL PDF SUMMARY
# ==================================================

def simple_summary(text, sentence_count=None):
    """
    Summarize the entire document.

    If sentence_count is None, there is no fixed sentence limit.
    All meaningful sentences are selected and arranged in their
    original document order.

    This is an extractive summary, not an AI-generated paraphrase.
    """

    text = clean_text(text)

    if not text:
        return "No readable text was found in the uploaded PDF."

    sentences = split_sentences(text)

    if not sentences:
        return text

    if sentence_count is None:
        # Keep the entire document's sentence content.
        # Remove only extremely short fragments that are likely
        # to be page numbers or broken PDF extraction artifacts.
        useful_sentences = [
            sentence
            for sentence in sentences
            if len(sentence.split()) >= 3
        ]

        if not useful_sentences:
            return text

        return "\n\n".join(useful_sentences)

    sentence_count = max(1, sentence_count)

    if len(sentences) <= sentence_count:
        return "\n\n".join(sentences)

    # Select sentences spread across the complete document.
    indexes = sorted({
        round(
            i * (len(sentences) - 1)
            / max(sentence_count - 1, 1)
        )
        for i in range(sentence_count)
    })

    return "\n\n".join(sentences[i] for i in indexes)


def create_study_notes(text):
    """Create a full-document summary and revision material."""

    text = clean_text(text)

    if not text:
        return {
            "summary": "No readable text was found in the PDF.",
            "keywords": [],
            "key_points": [],
            "total_sentences": 0,
        }

    sentences = split_sentences(text)

    # Full-document summary: no fixed sentence limit.
    summary_text = simple_summary(text)

    keywords = get_keywords(text, limit=20)

    # Keep important explanatory sentences for revision.
    key_points = []

    importance_phrases = [
        "defined as",
        "refers to",
        "consists of",
        "is called",
        "is known as",
        "important",
        "therefore",
        "as a result",
        "advantages",
        "disadvantages",
        "characteristics",
        "functions",
        "objectives",
        "methods",
        "process",
        "types of",
        "in conclusion",
        "for example",
    ]

    for sentence in sentences:
        words = sentence.split()

        if len(words) < 6:
            continue

        lower_sentence = sentence.lower()

        if (
            len(words) >= 10
            or any(
                phrase in lower_sentence
                for phrase in importance_phrases
            )
        ):
            key_points.append(sentence)

    return {
        "summary": summary_text,
        "keywords": keywords,
        "key_points": key_points,
        "total_sentences": len(sentences),
    }


# ==================================================
# HOME
# ==================================================

@app.route("/")
def home():
    return render_template("index.html")


# ==================================================
# DASHBOARD
# ==================================================

@app.route("/dashboard")
def dashboard():
    with get_db() as db:
        notes = db.execute("""
            SELECT id, filename, uploaded_at
            FROM notes
            ORDER BY id DESC
            LIMIT 10
        """).fetchall()

        scores = db.execute("""
            SELECT *
            FROM quiz_scores
            ORDER BY id DESC
            LIMIT 5
        """).fetchall()

    return render_template(
        "dashboard.html",
        notes=notes,
        scores=scores
    )


# ==================================================
# PDF UPLOAD
# ==================================================

@app.route("/upload", methods=["POST"])
def upload_pdf():
    if "pdf_file" not in request.files:
        flash("Choose a PDF file first.", "error")
        return redirect(url_for("dashboard"))

    file = request.files["pdf_file"]

    if not file.filename:
        flash("Choose a PDF file first.", "error")
        return redirect(url_for("dashboard"))

    if not allowed_file(file.filename):
        flash("Please upload a PDF file only.", "error")
        return redirect(url_for("dashboard"))

    if PdfReader is None:
        flash(
            "PDF reader is not installed. Run: "
            "python -m pip install pypdf",
            "error"
        )
        return redirect(url_for("dashboard"))

    safe_name = secure_filename(file.filename)

    if not safe_name:
        flash("The filename is invalid.", "error")
        return redirect(url_for("dashboard"))

    saved_name = (
        f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_"
        f"{safe_name}"
    )

    saved_path = os.path.join(
        app.config["UPLOAD_FOLDER"],
        saved_name
    )

    file.save(saved_path)

    try:
        reader = PdfReader(saved_path)

        if reader.is_encrypted:
            try:
                result = reader.decrypt("")
                if not result:
                    raise ValueError("Encrypted PDF")
            except Exception:
                flash(
                    "This PDF is password-protected. "
                    "Upload an unlocked PDF.",
                    "error"
                )
                return redirect(url_for("dashboard"))

        extracted = "\n\n".join(
            page.extract_text() or ""
            for page in reader.pages
        )

        extracted = clean_text(extracted)

    except Exception:
        flash(
            "Unable to read this PDF. Try another PDF file.",
            "error"
        )
        return redirect(url_for("dashboard"))

    with get_db() as db:
        db.execute("""
            INSERT INTO notes
            (filename, extracted_text, uploaded_at)
            VALUES (?, ?, ?)
        """, (
            safe_name,
            extracted,
            datetime.now().strftime("%Y-%m-%d %H:%M")
        ))

    if not extracted:
        flash(
            "No selectable text was found. Scanned PDFs need OCR.",
            "error"
        )
    else:
        flash(
            f"Uploaded {safe_name}. "
            f"Text extracted successfully.",
            "success"
        )

    return redirect(url_for("dashboard"))


# ==================================================
# SUMMARY PAGE
# ==================================================

@app.route("/summary")
def summary():
    note = latest_notes()

    if note and note["extracted_text"].strip():
        study_notes = create_study_notes(
            note["extracted_text"]
        )

        summary_text = study_notes["summary"]
        keywords = study_notes["keywords"]
        key_points = study_notes["key_points"]
        total_sentences = study_notes["total_sentences"]

    else:
        summary_text = (
            "Upload a readable PDF to generate your study notes."
        )
        keywords = []
        key_points = []
        total_sentences = 0

    return render_template(
        "summary.html",
        note=note,
        summary_text=summary_text,
        keywords=keywords,
        key_points=key_points,
        total_sentences=total_sentences
    )


# ==================================================
# QUIZ GENERATION
# ==================================================

def make_quiz_questions(text):
    sentences = split_sentences(clean_text(text))

    questions = []
    used_answers = set()

    for sentence in sentences:
        words = re.findall(
            r"\b[A-Za-z][A-Za-z'-]*\b",
            sentence
        )

        candidates = [
            word for word in words
            if len(word) >= 6
            and word.lower() not in STOP_WORDS
        ]

        if len(candidates) < 2:
            continue

        answer = max(candidates, key=len)

        if answer.lower() in used_answers:
            continue

        question_text = re.sub(
            r"\b" + re.escape(answer) + r"\b",
            "________",
            sentence,
            count=1,
            flags=re.IGNORECASE
        )

        options = [answer]

        for word in candidates:
            if word.lower() not in {
                option.lower() for option in options
            }:
                options.append(word)

            if len(options) >= 4:
                break

        fallback_options = [
            "Learning",
            "Concept",
            "Practice",
            "Knowledge",
            "Method",
            "Process",
        ]

        for fallback in fallback_options:
            if len(options) >= 4:
                break

            if fallback.lower() not in {
                option.lower() for option in options
            }:
                options.append(fallback)

        if len(options) < 4:
            continue

        questions.append({
            "question": question_text,
            "answer": answer,
            "options": options[:4]
        })

        used_answers.add(answer.lower())

        if len(questions) >= 5:
            break

    return questions


@app.route("/quiz", methods=["GET", "POST"])
def quiz():
    note = latest_notes()

    if not note or not note["extracted_text"].strip():
        flash(
            "Upload a text-based PDF first to create a quiz.",
            "error"
        )
        return redirect(url_for("dashboard"))

    questions = make_quiz_questions(
        note["extracted_text"]
    )

    if not questions:
        flash(
            "We couldn't create quiz questions from this PDF. "
            "Try a PDF with complete sentences.",
            "error"
        )
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        score = 0

        for i, question in enumerate(questions):
            selected = request.form.get(f"q{i}", "")

            if selected == question["answer"]:
                score += 1

        with get_db() as db:
            db.execute("""
                INSERT INTO quiz_scores
                (topic, score, total, created_at)
                VALUES (?, ?, ?, ?)
            """, (
                note["filename"],
                score,
                len(questions),
                datetime.now().strftime("%Y-%m-%d %H:%M")
            ))

        return render_template(
            "quiz_result.html",
            score=score,
            total=len(questions),
            filename=note["filename"]
        )

    return render_template(
        "quiz.html",
        questions=questions,
        filename=note["filename"]
    )


# ==================================================
# ASK QUESTIONS ABOUT THE PDF
# ==================================================

@app.route("/ask", methods=["POST"])
def ask():
    question = request.form.get(
        "question", ""
    ).strip()

    note = latest_notes()

    if not note or not note["extracted_text"].strip():
        answer = "Upload a readable PDF first."

    elif not question:
        answer = "Please type a question."

    else:
        text = clean_text(note["extracted_text"])

        terms = [
            word.lower()
            for word in re.findall(
                r"\b\w{3,}\b",
                question
            )
            if word.lower() not in STOP_WORDS
        ]

        sentences = split_sentences(text)

        ranked = []

        for index, sentence in enumerate(sentences):
            lower_sentence = sentence.lower()

            matches = sum(
                1 for term in terms
                if term in lower_sentence
            )

            if matches > 0:
                ranked.append(
                    (matches, index, sentence)
                )

        ranked.sort(
            key=lambda item: (-item[0], item[1])
        )

        useful = [
            sentence
            for _matches, _index, sentence in ranked[:5]
        ]

        if useful:
            answer = " ".join(useful)
        else:
            answer = (
                "I couldn't find a clear answer in the uploaded "
                "notes. Try asking with keywords from your PDF."
            )

    return render_template(
        "answer.html",
        question=question,
        answer=answer
    )


# ==================================================
# ERROR HANDLING
# ==================================================

@app.errorhandler(413)
def too_large(_error):
    flash(
        "The PDF is too large. Please upload a file under 15 MB.",
        "error"
    )
    return redirect(url_for("dashboard"))


# ==================================================
# RUN APPLICATION
# ==================================================

init_db()

if __name__ == "__main__":
    app.run(debug=True)