# Understand Your Event Registration API

Use this guide to learn the project, not as a script to memorize. Open `app.py` alongside this document and trace one request at a time.

## The request lifecycle

For a successful registration, the flow is:

1. A client sends `POST /register` with a JSON body.
2. Flask routes the request to the `register()` function.
3. `request.get_json()` reads the submitted JSON.
4. `validate_registration()` checks the types, required fields and length limits, then normalizes the values.
5. The route opens a database transaction.
6. It checks for a duplicate email and checks the current number of registrations.
7. If a seat exists, a parameterized `INSERT` saves the participant.
8. The transaction commits, and the API returns `201 Created` with the saved record.

If validation fails, the request returns `400`. If the email already exists or the event is full, it returns `409`. The database is not modified for those rejected requests.

## Key concepts in plain English

### Flask route

A decorator such as `@app.post("/register")` tells Flask which Python function should handle a `POST` request to that URL.

### JSON

JSON is a text format for structured data. The client sends fields such as `name` and `email`; the API responds with JSON so a browser or another program can read it.

### HTTP status codes

- `200 OK`: a read or other request succeeded.
- `201 Created`: a new registration was created.
- `400 Bad Request`: submitted information is invalid.
- `401 Unauthorized`: an organizer key is missing or incorrect.
- `404 Not Found`: the requested record or route does not exist.
- `409 Conflict`: the email already exists or capacity has been reached.
- `503 Service Unavailable`: organizer endpoints are disabled because no key is configured, or the database is temporarily busy.

### SQLite and SQL

SQLite stores data in a local database file. SQL is used to create tables, insert rows, count records and retrieve them. The `registrations` table has an automatically generated ID, required name/email/timestamp fields and an optional college field.

### Parameterized queries

Prefer:

```python
db.execute("SELECT * FROM registrations WHERE email = ?", (email,))
```

The email is supplied as a value rather than pasted into SQL text. This helps prevent SQL injection.

### Unique email constraint

The database declares email as `UNIQUE COLLATE NOCASE`, so emails differing only by letter case cannot create separate registrations. The app also converts submitted emails to lowercase to keep stored data consistent.

### Why use a transaction for capacity?

Imagine there is one seat left and two requests arrive together. If each request counts registrations before either inserts, both might see one seat and both attempt to claim it. `BEGIN IMMEDIATE` reserves SQLite's write transaction before the count is checked. One writer proceeds at a time, so the second request sees the updated count after the first commits.

### What does the organizer API key do?

Organizer routes check the `X-API-Key` request header against `ADMIN_API_KEY` from the server environment. The key is not embedded in the source code. If the server has no key configured, organizer routes are disabled rather than accidentally left public. Registration remains public so students can sign up.

## Learn the code in this order

1. `EVENT` and the configuration in `create_app()`.
2. `init_db()` and the `registrations` table.
3. `validate_registration()` and its returned `problems` dictionary.
4. `GET /` to understand a simple read route.
5. `POST /register`, first the validation and then the transaction.
6. `admin_required()` and the organizer routes.
7. `register_errors()` for consistent error responses.
8. `test_app.py`: read each test and predict the result before running it.

## Practice exercises

Do these yourself, one at a time:

- Change the event capacity in a test-only configuration and test the full-event case.
- Add a test for a college/department value that is too long.
- Add a `GET /health` endpoint that returns `{"status":"ok"}` without exposing private data.
- Change a test input from `asha@college.edu` to `ASHA@COLLEGE.EDU` and explain why it is a duplicate.
- Temporarily remove the `BEGIN IMMEDIATE` transaction in a separate experiment and explain the race condition. Restore it afterward.
- Deliberately send an invalid organizer key and explain the `401` response.

## Interview practice

**Why Flask?** It is lightweight, readable and sufficient for a small REST API.

**Why SQLite?** The project needs persistent relational data, and SQLite avoids the setup of a separate database server.

**Why not store registrations in a Python list?** A list is lost when the process restarts and does not provide database constraints or safe concurrent writes.

**Why check duplicates in both Python and SQL?** The Python check gives a friendly response; the database constraint remains a final safeguard against duplicate data.

**Why not trust the browser to enforce capacity?** Clients can bypass browser checks or send requests directly. The server and database must enforce the rule.

**What is the biggest limitation?** This is a single-event learning service with a shared API key for organizers. A real multi-event system would need event records, stronger identity and access management, rate limiting, monitoring and deployment hardening.

## Important

Do not claim that you wrote every line from memory if you used AI or tutorials. You can honestly say you used them as learning tools, then explain what you verified, what you changed and what you understand now. Being able to trace, test and modify the project is the goal.
