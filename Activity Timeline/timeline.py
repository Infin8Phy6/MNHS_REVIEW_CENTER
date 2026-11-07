import os
import json
from flask import Flask, render_template_string, request, redirect, url_for, flash
from werkzeug.utils import secure_filename
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

app = Flask(__name__)
app.secret_key = "secret_key_for_flask_timeline"

UPLOAD_FOLDER = os.path.join(os.getcwd(), 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

TOKEN_FILE = 'token.json'

# In-memory storage for timeline
timeline_data = {
    "title": "Timeline of events in the Development of the atomic theory",
    "events": []
}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Atomic Theory Timeline Generator</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 30px; background-color: #f4f6f9; color: #333; }
        .container { max-width: 900px; margin: 0 auto; background: white; padding: 25px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
        h1, h2 { color: #1a365d; }
        .form-group { margin-bottom: 15px; }
        label { display: block; font-weight: bold; margin-bottom: 5px; }
        input[type="text"], textarea { width: 100%; padding: 10px; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; }
        textarea { height: 100px; }
        .btn { padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; font-weight: bold; }
        .btn-primary { background-color: #3182ce; color: white; }
        .btn-success { background-color: #38a169; color: white; }
        .btn-danger { background-color: #e53e3e; color: white; }
        .alert { padding: 12px; margin-bottom: 20px; border-radius: 4px; }
        .alert-success { background-color: #c6f6d5; color: #22543d; }
        .alert-error { background-color: #fed7d7; color: #742a2a; }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        th, td { border: 1px solid #e2e8f0; padding: 12px; text-align: left; vertical-align: middle; }
        th { background-color: #edf2f7; }
        img.thumb { width: 60px; height: 60px; object-fit: cover; border-radius: 4px; }
        .actions { margin-top: 20px; display: flex; gap: 10px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Timeline Builder</h1>

        {% with messages = get_flashed_messages(with_categories=true) %}
          {% if messages %}
            {% for category, message in messages %}
              <div class="alert alert-{{ category }}">{{ message }}</div>
            {% endfor %}
          {% endif %}
        {% endwith %}

        <!-- Timeline Title Form -->
        <form action="{{ url_for('update_title') }}" method="POST" class="form-group">
            <label for="title">Timeline Title:</label>
            <div style="display: flex; gap: 10px;">
                <input type="text" id="title" name="title" value="{{ timeline.title }}" required>
                <button type="submit" class="btn btn-primary">Update Title</button>
            </div>
        </form>

        <hr style="margin: 25px 0;">

        <h2>Add Timeline Event</h2>
        <form action="{{ url_for('add_event') }}" method="POST" enctype="multipart/form-data">
            <div class="form-group">
                <label for="year">Year:</label>
                <input type="text" id="year" name="year" placeholder="e.g., 1803 or 400 BC" required>
            </div>
            <div class="form-group">
                <label for="person_name">Name of Person:</label>
                <input type="text" id="person_name" name="person_name" placeholder="e.g., John Dalton" required>
            </div>
            <div class="form-group">
                <label for="image">Image of Person:</label>
                <input type="file" id="image" name="image" accept="image/*" required>
            </div>
            <div class="form-group">
                <label for="contribution">Contribution:</label>
                <textarea id="contribution" name="contribution" placeholder="Describe their contribution to the atomic theory..." required></textarea>
            </div>
            <button type="submit" class="btn btn-primary">Save Event</button>
        </form>

        <hr style="margin: 25px 0;">

        <h2>Saved Events ({{ timeline.events|length }})</h2>
        {% if timeline.events %}
        <table>
            <thead>
                <tr>
                    <th>Year</th>
                    <th>Image</th>
                    <th>Person</th>
                    <th>Contribution</th>
                    <th>Action</th>
                </tr>
            </thead>
            <tbody>
                {% for event in timeline.events %}
                <tr>
                    <td><strong>{{ event.year }}</strong></td>
                    <td><img src="{{ url_for('static', filename='uploads/' + event.image_filename) }}" class="thumb"></td>
                    <td>{{ event.person_name }}</td>
                    <td>{{ event.contribution }}</td>
                    <td>
                        <a href="{{ url_for('delete_event', index=loop.index0) }}" class="btn btn-danger" style="text-decoration:none; padding: 5px 10px;">Delete</a>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>

        <div class="actions">
            <a href="{{ url_for('export_timeline') }}" class="btn btn-success" style="text-decoration:none;">Export Timeline & Save to Google Drive</a>
        </div>
        {% else %}
        <p>No events added yet. Fill out the form above and click "Save Event".</p>
        {% endif %}
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, timeline=timeline_data)

@app.route('/update_title', methods=['POST'])
def update_title():
    timeline_data['title'] = request.form.get('title', 'Atomic Theory Timeline')
    flash('Timeline title updated!', 'success')
    return redirect(url_for('index'))

@app.route('/add_event', methods=['POST'])
def add_event():
    year = request.form.get('year')
    person_name = request.form.get('person_name')
    contribution = request.form.get('contribution')
    image_file = request.files.get('image')

    if not (year and person_name and contribution and image_file):
        flash('All fields are required!', 'error')
        return redirect(url_for('index'))

    filename = secure_filename(image_file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    image_file.save(filepath)

    timeline_data['events'].append({
        'year': year,
        'person_name': person_name,
        'contribution': contribution,
        'image_filename': filename,
        'image_path': filepath
    })

    flash(f'Event for {person_name} ({year}) added successfully!', 'success')
    return redirect(url_for('index'))

@app.route('/delete_event/<int:index>')
def delete_event(index):
    if 0 <= index < len(timeline_data['events']):
        removed = timeline_data['events'].pop(index)
        flash(f'Removed {removed["person_name"]}.', 'success')
    return redirect(url_for('index'))

def create_pdf(output_path, timeline):
    """Generates an A4 PDF based on exact percentage viewport heights."""
    c = canvas.Canvas(output_path, pagesize=A4)
    page_width, page_height = A4  # A4 size in points

    margin = 36  # 0.5 inch horizontal margin
    content_width = page_width - (2 * margin)

    styles = getSampleStyleSheet()

    for idx, event in enumerate(timeline['events']):
        # Section Vertical Height allocations (vh)
        year_h = page_height * 0.10          # 10% vh for Year (Upper Right)
        image_h = page_height * 0.60         # 60% vh for Picture
        name_h = page_height * 0.05          # 5% vh for Name

        # 1. UPPER RIGHT CORNER: YEAR (10% vh slot)
        year_font_size = int(year_h * 0.5)
        c.setFont("Helvetica-Bold", year_font_size)
        c.setFillColor(HexColor("#1A365D"))
        c.drawRightString(page_width - margin, page_height - year_h + (year_h * 0.2), str(event['year']))

        # 2. PICTURE OF THE PERSON (60% vh slot)
        img_top = page_height - year_h
        img_y = img_top - image_h
        img_path = event['image_path']
        if os.path.exists(img_path):
            c.drawImage(img_path, margin, img_y, width=content_width, height=image_h, preserveAspectRatio=True, anchor='c')

        # 3. BELOW PICTURE: NAME OF PERSON (5% vh slot)
        name_y_top = img_y
        name_font_size = int(name_h * 0.5)
        c.setFont("Helvetica-Bold", name_font_size)
        c.setFillColor(HexColor("#2B6CB0"))
        c.drawString(margin, name_y_top - name_h + (name_h * 0.25), event['person_name'])

        # 4. CONTRIBUTION (Remaining space down to bottom margin)
        contrib_y_top = name_y_top - name_h - 10
        contrib_height = contrib_y_top - margin

        contrib_style = ParagraphStyle(
            'ContributionStyle',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=12,
            leading=16,
            textColor=HexColor('#2D3748')
        )
        
        p = Paragraph(event['contribution'], contrib_style)
        w, h = p.wrap(content_width, contrib_height)
        p.drawOn(c, margin, contrib_y_top - h)

        if idx < len(timeline['events']) - 1:
            c.showPage()

    c.save()

def upload_to_google_drive(file_path, folder_name, file_name):
    """Loads credentials from external token.json and uploads generated PDF."""
    if not os.path.exists(TOKEN_FILE):
        raise FileNotFoundError(f"External token file '{TOKEN_FILE}' not found.")

    with open(TOKEN_FILE, 'r') as f:
        token_info = json.load(f)

    creds = Credentials.from_authorized_user_info(token_info)
    service = build('drive', 'v3', credentials=creds)

    # 1. Check if folder already exists or create it
    query = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    response = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
    folders = response.get('files', [])

    if folders:
        folder_id = folders[0]['id']
    else:
        folder_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        folder = service.files().create(body=folder_metadata, fields='id').execute()
        folder_id = folder.get('id')

    # 2. Upload file into the designated folder
    file_metadata = {
        'name': file_name,
        'parents': [folder_id]
    }
    media = MediaFileUpload(file_path, mimetype='application/pdf', resumable=True)
    uploaded_file = service.files().create(body=file_metadata, media_body=media, fields='id, name').execute()

    return uploaded_file.get('id')

@app.route('/export_timeline')
def export_timeline():
    if not timeline_data['events']:
        flash('Cannot export empty timeline!', 'error')
        return redirect(url_for('index'))

    folder_name = timeline_data['title'].strip()
    pdf_filename = f"{folder_name}.pdf"
    pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], pdf_filename)

    # Generate PDF locally
    create_pdf(pdf_path, timeline_data)

    # Upload to Google Drive using token.json
    try:
        drive_file_id = upload_to_google_drive(pdf_path, folder_name, pdf_filename)
        flash(f'Timeline exported and successfully uploaded to Google Drive in folder "{folder_name}"! (File ID: {drive_file_id})', 'success')
    except Exception as e:
        flash(f'PDF generated locally, but Google Drive upload failed: {str(e)}', 'error')

    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)