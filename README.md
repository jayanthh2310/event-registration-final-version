# Celestius Event Registration API

A small, documented REST API for the Celestius Backend Team recruitment task. It manages registrations for the **Backend Development Workshop** (task scenario date: **20 October 2026**, capacity: **50 participants**).

**Stack:** Python 3.10+ · Flask · SQLite · `unittest`

The backend is the main deliverable. A lightweight browser dashboard is included as an optional demo at `/ui`; it is not required for the backend task.

## Quick start (2 minutes)

> **Important:** set `ADMIN_API_KEY` *before* starting the server. Without it, the organizer routes (`GET /registrations`, etc.) deliberately return `503`. This is a safety feature, not a bug. Registering (`POST /register`) works either way.

```bash
python3 -m venv .venv && source .venv/bin/activate     # Windows: py -m venv .venv ; .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
export ADMIN_API_KEY='local-demo-key-change-this'       # Windows: $env:ADMIN_API_KEY = "local-demo-key-change-this"
python app.py                                           # then, in a second terminal: bash demo.sh
python -m unittest -v                                   # run the 16 automated tests
```

## Features

- Register participants with name, email, optional college/department and a server-generated UTC timestamp.
- List registrations and retrieve a registration by ID or email.
- Enforce a hard capacity of 50 and prevent duplicate emails (case-insensitive).
- Validate input and return consistent JSON errors and meaningful HTTP status codes.
- Use parameterized SQL queries and a transaction to prevent overbooking during concurrent requests.
- Protect organizer endpoints with an API key; if no key is configured, organizer endpoints fail closed with `503` rather than silently becoming public.
- Automated tests for core behavior, validation, authentication and concurrency.

## 1. Run locally

### Windows PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:ADMIN_API_KEY = "local-demo-key-change-this"
python app.py
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export ADMIN_API_KEY='local-demo-key-change-this'
python app.py
```

API base URL: `http://127.0.0.1:5000`  
Optional dashboard: `http://127.0.0.1:5000/ui`

### Optional Docker run

```bash
docker build -t celestius-event-api .
docker run --rm -p 8000:8000 -e ADMIN_API_KEY="replace-with-a-strong-key" -v celestius-data:/data celestius-event-api
```

The container API is available at `http://127.0.0.1:8000`. The dashboard is included in the image too.

Keep the server terminal open while testing. The local SQLite database is created automatically at `registrations.db` (or at the path specified by `DB_PATH`). Do not commit real API keys or a database containing personal information.

## 2. Try the API

### Event status

```bash
curl http://127.0.0.1:5000/
```

### Register a student

```bash
curl -i -X POST http://127.0.0.1:5000/register \
  -H 'Content-Type: application/json' \
  -d '{"name":"Asha Kumar","email":"asha@college.edu","college":"ECE"}'
```

Registration is public by design; organizers do not need to share their API key with participants.

### List registrations (organizer key required)

```bash
curl http://127.0.0.1:5000/registrations \
  -H 'X-API-Key: local-demo-key-change-this'
```

### Get one registration

```bash
curl http://127.0.0.1:5000/registrations/1 \
  -H 'X-API-Key: local-demo-key-change-this'
```

### Cancel a registration (bonus endpoint)

```bash
curl -X DELETE http://127.0.0.1:5000/registrations/1 \
  -H 'X-API-Key: local-demo-key-change-this'
```

You can also run `bash demo.sh` on macOS/Linux after setting the key and starting the server.

## 3. API reference

| Method | Route | Access | Purpose |
|---|---|---|---|
| `GET` | `/` | Public | Event details, registered count, seats remaining, full status |
| `POST` | `/register` | Public | Create a registration |
| `GET` | `/registrations` | Organizer | List registrations; supports `?limit=10&offset=0` |
| `GET` | `/registrations/<id>` | Organizer | Retrieve one registration by ID |
| `GET` | `/registrations/email/<email>` | Organizer | Retrieve one registration by email |
| `DELETE` | `/registrations/<id>` | Organizer | Cancel a registration; frees a seat |
| `GET` | `/ui` | Public | Optional demo dashboard |

### Expected responses

| Scenario | Status | Meaning |
|---|---:|---|
| Registration created | `201` | Resource created; response includes `Location` header |
| Invalid/missing input | `400` | Request needs correction; field details are returned |
| Missing/incorrect organizer key | `401` | Organizer authentication failed |
| Organizer key not configured | `503` | Organizer endpoints are disabled until configured |
| Duplicate email or event full | `409` | Request conflicts with current registration state |
| Registration/route not found | `404` | Requested resource or route does not exist |
| Unsupported HTTP method | `405` | Route does not support that method |

### Example request body

```json
{
  "name": "Asha Kumar",
  "email": "asha@college.edu",
  "college": "ECE"
}
```

`name` and `email` are required. `college` is optional. Registration time is generated by the server in UTC; clients cannot set it.

## 4. Run the tests

With the virtual environment active:

```bash
python -m unittest -v
```

The tests use temporary SQLite databases, so they do not alter your real `registrations.db`. They cover valid and invalid requests, duplicate emails, capacity, cancellation, retrieval, pagination, organizer authentication and concurrent registration attempts.

## 5. Important design decisions

1. **Flask:** small and approachable for a learning project; routes map HTTP requests to Python functions.
2. **SQLite:** persistent relational storage without a separate database server; suitable for this small event.
3. **Database constraints:** `NOT NULL` and `UNIQUE ... COLLATE NOCASE` protect data even if application checks are missed.
4. **Atomic capacity check:** `BEGIN IMMEDIATE` obtains the SQLite write reservation before checking the count and inserting. This prevents two writers from both claiming the last seat.
5. **Parameterized SQL:** values are passed separately from SQL text, reducing SQL injection risk.
6. **Server-generated timestamp:** consistent UTC timestamps cannot be supplied or forged by the client.
7. **Fail-closed organizer access:** organizer endpoints return `503` if `ADMIN_API_KEY` is missing and `401` for an incorrect key. Use a strong secret in deployment; this simple API-key approach is a learning-project safeguard, not a full user-account system.
8. **App factory:** `create_app()` lets tests use isolated temporary databases and configuration.

## 6. Known limitations and sensible next steps

- This is a single-event learning project. Event details and capacity are constants, not editable records.
- A single shared organizer API key is not a substitute for individual accounts, roles, key rotation and audit logs.
- Public registration would need rate limiting, monitoring and deployment-level protections before real-world use.
- SQLite is appropriate here; a multi-instance production service would typically use a managed database such as PostgreSQL.
- The email validation is intentionally lightweight and does not prove that an address exists.

## Project structure

```text
app.py           Flask routes, validation, database access and error handlers
static/ui.html   Optional browser dashboard
test_app.py      Automated tests
UNDERSTANDING.md Beginner-friendly walkthrough and interview practice
LEARNING_LOG.md  How I approached the task and what I learned (my own notes)
demo.sh          Example API requests
requirements.txt Python dependency list
Dockerfile       Optional container setup
```
