
import os
import json
import pandas as pd
from flask import Flask, request, jsonify, render_template, send_file
from flask_cors import CORS
from dotenv import load_dotenv
import openai
from werkzeug.utils import secure_filename
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sentence_transformers import SentenceTransformer
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from PyPDF2 import PdfReader

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# OpenAI API key
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

# File upload configuration
UPLOAD_FOLDER = 'uploads'
STATIC_FOLDER = 'static'
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'csv', 'xlsx', 'json'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024  # 32 MB limit

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(STATIC_FOLDER, exist_ok=True)

# RAG System class
class RAGSystem:
    def __init__(self):
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')

    def generate_response(self, prompt, context):
        combined_context = ' '.join(context)
        response = f"Generated response for prompt: '{prompt}' with context: {combined_context}"
        return response

    def extract_text_from_pdf(self, file_path):
        text = ""
        try:
            reader = PdfReader(file_path)
            for page in reader.pages:
                text += page.extract_text()
        except Exception as e:
            text = f"Error extracting text from PDF: {str(e)}"
        return text

rag_system = RAGSystem()

# Utility function to check allowed file types
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# PDF generation function
def generate_pdf(prompt, file_content, response, df):
    pdf_path = os.path.join(STATIC_FOLDER, "output_report.pdf")
    doc = SimpleDocTemplate(pdf_path, pagesize=letter)
    styles = getSampleStyleSheet()
    content = []

    content.append(Paragraph("AI Generated Report", styles["Title"]))
    content.append(Spacer(1, 12))
    content.append(Paragraph(f"<b>Prompt:</b> {prompt}", styles["BodyText"]))
    content.append(Spacer(1, 12))
    content.append(Paragraph("<b>File Content:</b>", styles["BodyText"]))
    content.append(Paragraph(file_content[:2000] + "..." if len(file_content) > 2000 else file_content, styles["BodyText"]))
    content.append(Spacer(1, 12))
    content.append(Paragraph(f"<b>Response:</b> {response}", styles["BodyText"]))

    if not df.empty:
        plt.figure(figsize=(4, 4))
        df.select_dtypes(include=[np.number]).iloc[:, :2].plot(kind="bar", legend=False)
        plt.tight_layout()
        plt.savefig(os.path.join(STATIC_FOLDER, "plot.png"))
        plt.close()
        content.append(Image(os.path.join(STATIC_FOLDER, "plot.png"), width=400, height=300))

    doc.build(content)
    return pdf_path

# Preview endpoint
@app.route('/preview', methods=['POST'])
def preview_report():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files['file']
    prompt = request.form.get('prompt', '')

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        file_extension = filename.rsplit(".", 1)[1].lower()
        try:
            if file_extension == "csv":
                df = pd.read_csv(file_path)
            elif file_extension == "xlsx":
                df = pd.read_excel(file_path)
            elif file_extension == "json":
                df = pd.read_json(file_path)
            elif file_extension == "pdf":
                text = rag_system.extract_text_from_pdf(file_path)
                df = pd.DataFrame({"Content": [text]})
            elif file_extension == "txt":
                with open(file_path, "r", encoding="utf-8") as f:
                    text = f.read()
                df = pd.DataFrame({"Content": [text]})
            else:
                return jsonify({"error": "Unsupported file type"}), 400
        except Exception as e:
            return jsonify({"error": f"Error reading file: {str(e)}"}), 400

        file_content = df.to_string(index=False) if not df.empty else ""
        response = rag_system.generate_response(prompt, [file_content])

        pdf_path = generate_pdf(prompt, file_content, response, df)
        return jsonify({"preview_url": f"/static/{os.path.basename(pdf_path)}"})
    else:
        return jsonify({"error": "Invalid file type"}), 400

# Serve static files
@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_file(os.path.join(STATIC_FOLDER, filename))

@app.route("/")
def index():
    return render_template("upload.html")

if __name__ == "__main__":
    app.run(debug=True)
