"""Run with:  python -m unittest -v"""
import os
import tempfile
import threading
import unittest

from app import create_app
from flask.testing import FlaskClient


class AuthorizedTestClient(FlaskClient):
    """Test client that supplies the configured test organizer key by default."""
    def open(self, *args, **kwargs):
        headers = dict(kwargs.pop("headers", {}) or {})
        headers.setdefault("X-API-Key", "test-secret")
        kwargs["headers"] = headers
        return super().open(*args, **kwargs)


class Base(unittest.TestCase):
    ADMIN_KEY = None

    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.app = create_app(self.path, admin_api_key="test-secret")
        self.app.test_client_class = AuthorizedTestClient
        self.client = self.app.test_client()

    def tearDown(self):
        for ext in ("", "-wal", "-shm"):
            if os.path.exists(self.path + ext):
                os.remove(self.path + ext)

    def reg(self, n, **kw):
        return self.client.post("/register", json={"name": f"Student {n}", "email": f"s{n}@college.edu", **kw})


class RegistrationTests(Base):
    def test_successful_registration(self):
        r = self.reg(1, college="CSE")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json["registration"]["college"], "CSE")
        self.assertEqual(r.json["seats_left"], 49)
        self.assertEqual(r.headers["Location"], "/registrations/1")
        self.assertIn("registered_at", r.json["registration"])

    def test_college_optional(self):
        r = self.reg(1)
        self.assertEqual(r.status_code, 201)
        self.assertIsNone(r.json["registration"]["college"])

    def test_input_is_normalised(self):
        r = self.client.post("/register", json={"name": "  Asha   K ", "email": "  ASHA@College.EDU "})
        self.assertEqual(r.json["registration"]["name"], "Asha K")
        self.assertEqual(r.json["registration"]["email"], "asha@college.edu")

    def test_validation_errors(self):
        post = self.client.post
        self.assertEqual(post("/register", json={}).status_code, 400)
        self.assertEqual(post("/register", json={"name": "A"}).status_code, 400)
        self.assertEqual(post("/register", json={"name": "A", "email": "nope"}).status_code, 400)
        self.assertEqual(post("/register", json={"name": "   ", "email": "a@b.co"}).status_code, 400)
        self.assertEqual(post("/register", json={"name": 5, "email": "a@b.co"}).status_code, 400)
        self.assertEqual(post("/register", json={"name": "A", "email": "a@b.co", "college": 7}).status_code, 400)
        self.assertEqual(post("/register", json={"name": "x" * 101, "email": "a@b.co"}).status_code, 400)
        self.assertEqual(post("/register", json=[1, 2]).status_code, 400)
        self.assertEqual(post("/register", data="not json", content_type="text/plain").status_code, 400)
        self.assertEqual(post("/register", data="{broken", content_type="application/json").status_code, 400)
        r = post("/register", json={"email": "bad"})
        self.assertIn("name", r.json["details"])
        self.assertIn("email", r.json["details"])
        self.assertEqual(self.client.get("/registrations").json["total"], 0)

    def test_duplicate_email_case_insensitive(self):
        self.assertEqual(self.reg(1).status_code, 201)
        r = self.client.post("/register", json={"name": "X", "email": "S1@COLLEGE.EDU"})
        self.assertEqual(r.status_code, 409)
        self.assertIn("already registered", r.json["error"])

    def test_capacity_limit(self):
        for i in range(50):
            self.assertEqual(self.reg(i).status_code, 201)
        r = self.reg(99)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json["error"], "Event is full.")
        self.assertEqual(self.client.get("/registrations").json["total"], 50)
        self.assertTrue(self.client.get("/").json["is_full"])

    def test_cancel_frees_a_seat(self):
        for i in range(50):
            self.reg(i)
        self.assertEqual(self.client.delete("/registrations/1").status_code, 200)
        self.assertEqual(self.reg(99).status_code, 201)
        self.assertEqual(self.client.delete("/registrations/12345").status_code, 404)


class ReadTests(Base):
    def test_list_and_get(self):
        self.reg(1)
        self.reg(2)
        self.assertEqual(self.client.get("/registrations").json["total"], 2)
        self.assertEqual(self.client.get("/registrations/1").json["email"], "s1@college.edu")
        self.assertEqual(self.client.get("/registrations/email/S2@college.edu").json["name"], "Student 2")

    def test_pagination(self):
        for i in range(5):
            self.reg(i)
        r = self.client.get("/registrations?limit=2&offset=2").json
        self.assertEqual([x["id"] for x in r["registrations"]], [3, 4])
        self.assertEqual(r["total"], 5)
        self.assertEqual(self.client.get("/registrations?limit=abc").status_code, 400)
        self.assertEqual(self.client.get("/registrations?limit=0").status_code, 400)

    def test_not_found(self):
        self.assertEqual(self.client.get("/registrations/999").status_code, 404)
        self.assertEqual(self.client.get("/registrations/email/no@one.com").status_code, 404)
        self.assertEqual(self.client.get("/nope").json["error"], "Route not found.")
        self.assertEqual(self.client.put("/register").status_code, 405)

    def test_ui_page_served(self):
        r = self.client.get("/ui")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Celestius | Event Registration", r.data)
        r.close()

    def test_event_info(self):
        self.reg(1)
        r = self.client.get("/").json
        self.assertEqual((r["capacity"], r["registered"], r["seats_left"]), (50, 1, 49))


class AdminAuthTests(Base):
    ADMIN_KEY = "secret123"

    def test_organizer_routes_need_key_but_registering_does_not(self):
        self.assertEqual(self.reg(1).status_code, 201)
        raw = FlaskClient(self.app)
        self.assertEqual(raw.get("/registrations").status_code, 401)
        self.assertEqual(raw.get("/registrations", headers={"X-API-Key": "wrong"}).status_code, 401)
        self.assertEqual(raw.get("/registrations", headers={"X-API-Key": "test-secret"}).status_code, 200)
        self.assertEqual(raw.delete("/registrations/1").status_code, 401)

    def test_missing_key_disables_organizer_routes(self):
        app = create_app(self.path, admin_api_key="")
        client = app.test_client()
        response = client.get("/registrations")
        self.assertEqual(response.status_code, 503)


class ConcurrencyTests(Base):
    def test_race_for_last_seats_never_overbooks(self):
        """80 simultaneous requests for 50 seats -> exactly 50 succeed."""
        results = []

        def worker(n):
            c = self.app.test_client()
            results.append(c.post("/register", json={"name": f"S{n}", "email": f"c{n}@x.edu"}).status_code)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(80)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(results.count(201), 50)
        self.assertEqual(results.count(409), 30)
        self.assertEqual(self.client.get("/registrations").json["total"], 50)

    def test_same_email_race_only_one_wins(self):
        results = []

        def worker():
            c = self.app.test_client()
            results.append(c.post("/register", json={"name": "Same", "email": "same@x.edu"}).status_code)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(results.count(201), 1)
        self.assertEqual(results.count(409), 19)


if __name__ == "__main__":
    unittest.main()
