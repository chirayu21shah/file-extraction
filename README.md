# Archive File Extractor

An HTTP service that accepts archive files and a glob pattern, recursively searches for matching files (including inside nested archives), and stores the results in a PostgreSQL database.

---

## Quick Start

### Prerequisites
- [Docker](https://www.docker.com/) and Docker Compose

### Build and Run

```bash
# Clone the repository and enter the directory
git clone <repo-url>
cd File_Extraction

# Start the service and database
docker-compose up --build
```

The service will be available at `http://localhost:8080`.

---

## API Reference

### `GET /health`
Liveness check.

**Response**
```json
{"status": "healthy"}
```

---

### `POST /extractions`
Submit a new extraction job. Returns immediately with a `job_id`; extraction runs in the background.

**Request** — `multipart/form-data`

| Field     | Type | Required | Description                        |
|-----------|------|----------|------------------------------------|
| `file`    | File | Yes      | The archive file (`.zip`, `.tar`, `.tar.gz`, `.tgz`) |
| `pattern` | Text | Yes      | Glob pattern to match (e.g. `*.txt`, `**/*.json`) |

**Response** `202 Accepted`
```json
{"job_id": "1d7b6395-4619-46a4-b94b-10ef9a379b98"}
```

---

### `GET /extractions/{job_id}`
Get job status and summary.

**Response** `200 OK`
```json
{
  "job_id": "1d7b6395-...",
  "status": "completed",
  "pattern": "*.txt",
  "error": null
}
```

`status` values: `pending` → `running` → `completed` | `failed`

---

### `GET /extractions/{job_id}/results?page=1`
List matched files for a job, paginated (20 results per page).

**Query Parameters**

| Param  | Default | Description   |
|--------|---------|---------------|
| `page` | `1`     | Page number   |

**Response** `200 OK`
```json
{
  "data": [
    {
      "matched_path": "data/notes.txt",
      "archive_path": "uploads/1d7b6395_sample.zip",
      "size": 16
    }
  ],
  "page": 1,
  "per_page": 20,
  "total": 4,
  "total_pages": 1
}
```

---

## Example Usage

A sample nested archive is included in the repository (`sample_nested.zip`).

Its structure is:
```
sample_nested.zip
├── top_level.txt
├── config.json
├── data/
│   └── notes.txt
└── inner.zip
    ├── deep.txt
    └── deeper.tar.gz
        └── bottom.txt
```

### Submit a job

```bash
curl -X POST http://localhost:8080/extractions \
  -F "file=@sample_nested.zip" \
  -F "pattern=*.txt"
# → {"job_id": "<job_id>"}
```

### Check status

```bash
curl http://localhost:8080/extractions/<job_id>
# → {"job_id": "...", "status": "completed", "pattern": "*.txt", "error": null}
```

### Get results

```bash
curl "http://localhost:8080/extractions/<job_id>/results?page=1"
```

Expected: 4 matches — `top_level.txt`, `data/notes.txt`, `deep.txt`, `bottom.txt`.

---

## Running Tests

### Unit tests (no running service required)

```bash
pip install pytest requests
pytest tests/test_unit.py -v
```

### Integration tests (requires running stack)

```bash
# Start the stack first
docker-compose up --build -d

# Run integration tests
pytest tests/test_integration.py -v

# Or override the service URL
SERVICE_URL=http://localhost:8080 pytest tests/test_integration.py -v
```

---

## Configuration

All configuration is via environment variables:

| Variable      | Default      | Description                        |
|---------------|--------------|------------------------------------|
| `DB_HOST`     | `db`         | PostgreSQL host                    |
| `DB_PORT`     | `5432`       | PostgreSQL port                    |
| `DB_NAME`     | `archives`   | Database name                      |
| `DB_USER`     | `postgres`   | Database user                      |
| `DB_PASSWORD` | `password`   | Database password                  |
| `PORT`        | `8080`       | HTTP port                          |
| `CONCURRENCY` | `4`          | Number of parallel worker threads  |

---

## Design Decisions and Assumptions

### File upload vs URL/path reference
Archives are accepted as **multipart/form-data uploads**. This makes the API self-contained (no shared filesystem or URL accessibility required) and works naturally with `curl` and API clients.

### Asynchronous processing
Jobs are placed on an in-process `queue.Queue` and consumed by a fixed pool of worker threads (controlled by `CONCURRENCY`). This keeps the implementation simple while providing genuine concurrency and bounded resource usage. A production system would use a dedicated task queue (e.g. Celery + Redis) for durability and horizontal scaling.

### Nested archive handling
The service recursively extracts archives up to `MAX_DEPTH = 5` levels deep. Nested archives found at each level are submitted to a `ThreadPoolExecutor` for parallel processing.

### Database schema
Tables are created automatically at startup via `db.create_all()`. The service retries the connection up to 10 times (2 s apart) to handle the race where the app starts before PostgreSQL is ready.

### What I would do differently with more time
- Add structured JSON logging with job IDs on every log line
- Use Alembic for proper database migrations instead of `create_all()`
- Stream large archives rather than extracting to disk entirely
- Implement graceful shutdown (drain the queue before exiting)
- Add file size / archive count limits to prevent resource exhaustion
- Replace the in-process queue with Celery + Redis for multi-replica deployments
- Store the full nesting chain path (e.g. `outer.zip/inner.tar.gz/file.txt`) in `matched_path`
