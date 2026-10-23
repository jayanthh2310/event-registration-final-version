#!/usr/bin/env bash
# Start the server first and set ADMIN_API_KEY in that server's environment.
# Usage: ADMIN_API_KEY='local-demo-key-change-this' bash demo.sh
set -eu
B=${1:-http://127.0.0.1:5000}
KEY=${ADMIN_API_KEY:-local-demo-key-change-this}
JSON='Content-Type: application/json'
ADMIN="X-API-Key: $KEY"
echo '--- event info'; curl -s "$B/"
echo; echo '--- register (201)'; curl -s -X POST "$B/register" -H "$JSON" -d '{"name":"Asha","email":"asha@college.edu","college":"ECE"}'
echo; echo '--- duplicate (409)'; curl -s -X POST "$B/register" -H "$JSON" -d '{"name":"Asha","email":"ASHA@college.edu"}'
echo; echo '--- invalid (400)'; curl -s -X POST "$B/register" -H "$JSON" -d '{"name":"","email":"nope"}'
echo; echo '--- list (organizer key)'; curl -s "$B/registrations" -H "$ADMIN"
echo; echo '--- one by id (organizer key)'; curl -s "$B/registrations/1" -H "$ADMIN"
echo; echo '--- one by email (organizer key; URL-encode special characters if present)'; curl -s "$B/registrations/email/asha@college.edu" -H "$ADMIN"
echo; echo '--- not found (404)'; curl -s "$B/registrations/999" -H "$ADMIN"
echo
