from queue import Queue
from concurrent.futures import ThreadPoolExecutor
import datetime
import time
import tempfile
import threading
import uuid
import os

from utils import extract_archive, is_archive, match_pattern, normalise_path

from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy

DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'password')
DB_HOST = os.getenv('DB_HOST', 'db')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_NAME = os.getenv('DB_NAME', 'archives')

UPLOAD_DIR = "uploads"

os.makedirs(UPLOAD_DIR, exist_ok=True)


PORT = int(os.getenv('PORT', 8080))
CONCURRENCY = int(os.getenv('CONCURRENCY', 4))

MAX_DEPTH = 5

def create_app(testing=False):
    app = Flask(__name__)
    if testing:
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    else:
        app.config[
            "SQLALCHEMY_DATABASE_URI"
        ] = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    return app

app = create_app()
db = SQLAlchemy(app)


class Job(db.Model):
    __tablename__ = 'jobs'

    job_id = db.Column(db.String, primary_key=True)
    status = db.Column(db.String)
    pattern = db.Column(db.String)
    error = db.Column(db.Text)

    created_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)


class Result(db.Model):
    __tablename__ = 'results'

    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.String, db.ForeignKey('jobs.job_id'))
    matched_path = db.Column(db.String)
    archive_path = db.Column(db.String)
    size = db.Column(db.BigInteger)

    created_at = db.Column(db.DateTime)

job_queue = Queue()

executor = ThreadPoolExecutor(max_workers=CONCURRENCY)

def initialize_database():
    with app.app_context():
        for attempt in range(10):
            try:
                db.create_all()
                break
            except Exception:
                if attempt == 9:
                    raise
                time.sleep(2)


def start_workers():
    for _ in range(CONCURRENCY):
        t = threading.Thread(target=worker, daemon=True)
        t.start()

# SAVE RESULT
def save_result(job_id, matched_path, archive_path, size):
    result = Result(
        job_id=job_id,
        matched_path=matched_path,
        archive_path=archive_path,
        size=size,
        created_at=datetime.datetime.utcnow()
    )

    db.session.add(result)
    db.session.commit()

def nested_scan_archive(job_id, archive_path, pattern, depth, archive_chain):
    with app.app_context():
        scan_archive(
            job_id=job_id,
            archive_path=archive_path,
            pattern=pattern,
            depth=depth,
            archive_chain=archive_chain
        )

# SCAN ARCHIVE
def scan_archive(job_id, archive_path, pattern, depth=0, archive_chain=None):
    if depth > MAX_DEPTH:
        return

    archive_name = normalise_path(os.path.basename(archive_path))
    if archive_chain is None:
        archive_chain = archive_name
    
    with tempfile.TemporaryDirectory() as temp_dir:
            extract_archive(archive_path, temp_dir)
            futures = []
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    full_path = os.path.join(root, file)
                    rel_path = normalise_path(os.path.relpath(full_path, temp_dir))
                    full_matched_path = f"{archive_chain}/{rel_path}"

                    if match_pattern(rel_path, pattern) or match_pattern(full_matched_path, pattern):
                        size = os.path.getsize(full_path)

                        save_result(
                            job_id=job_id,
                            matched_path=full_matched_path,
                            archive_path=archive_chain,
                            size=size
                        )
                    
                    if is_archive(full_path):
                        future = executor.submit(
                            nested_scan_archive,
                            job_id,
                            full_path,
                            pattern,
                            depth + 1
                            ,full_matched_path
                        )
                        futures.append(future)
            for future in futures:
                future.result()

                # a.zip
                    # b.txt c.zip
                            # d.txt
                        

# WORKER
def worker():
    while True:
        item = job_queue.get()

        if item is None:
            break
        
        job_id, archive_path, pattern = item
        # /tmp/abc.zip

        with app.app_context():
            try:
                job = Job.query.get(job_id)

                job.status = "running"
                db.session.commit()

                scan_archive(job_id, archive_path, pattern)

                job.status = "completed"
                job.completed_at = datetime.datetime.utcnow()
                db.session.commit()
            except Exception as e:
                job = Job.query.get(job_id)
                job.status = "failed"
                job.error = str(e)
                db.session.commit()
            finally:
                if os.path.exists(archive_path):
                    os.remove(archive_path)
                job_queue.task_done()

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy"}), 200


@app.route('/extractions', methods=['POST'])
def create_extraction():

    if("file" not in request.files):
        return jsonify({"error": "No file part in the request"}), 400
    pattern = request.form.get('pattern')

    if not pattern:
        return jsonify({"error": "Pattern is required"}), 400
    
    file = request.files["file"]

    job_id = str(uuid.uuid4())
    filename = f"{file.filename}"
    
    archive_path = os.path.join(UPLOAD_DIR, filename)
    file.save(archive_path)

    job = Job(
        job_id=job_id,
        status='pending',
        pattern=pattern,
        created_at=datetime.datetime.utcnow()
    )

    db.session.add(job)
    db.session.commit()

    job_queue.put((job_id, archive_path, pattern))

    return jsonify({"job_id": job_id}), 202


@app.route('/extractions/<job_id>', methods=['GET'])
def get_extraction(job_id):
    job = Job.query.get(job_id)

    if not job:
        return jsonify({"error": "Job not found"}), 404
    
    count = Result.query.filter_by(job_id=job_id).count()


    return jsonify({
        "job_id" : job.job_id,
        "status" : job.status,
        "pattern" : job.pattern,
        "error" : job.error
    }), 200

PAGE_SIZE = 20

@app.route('/extractions/<job_id>/results', methods=['GET'])
def get_results(job_id):
    job = Job.query.get(job_id)

    if not job:
        return jsonify({"error": "Job not found"}), 404

    page = request.args.get('page', 1, type=int)

    pagination = Result.query.filter_by(job_id=job_id).paginate(
        page=page, per_page=PAGE_SIZE, error_out=False
    )

    data = [
        {
            "matched_path": result.matched_path,
            "archive_path": result.archive_path,
            "size": result.size,
        }
        for result in pagination.items
    ]

    return jsonify({
        "data": data,
        "page": page,
        "per_page": PAGE_SIZE,
        "total": pagination.total,
        "total_pages": pagination.pages,
    }), 200

if __name__ == '__main__':
    initialize_database()
    start_workers()
    app.run(host='0.0.0.0', port=PORT)