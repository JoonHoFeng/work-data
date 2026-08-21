import csv
import io
import os
import tempfile
import unittest
from pathlib import Path

import db
from templates import TEMPLATE_DEV, TEMPLATE_QA, template_categories


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "worklog.db"
        db.init_db(self.path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_people_and_templates(self):
        people = db.list_people(self.path)
        self.assertEqual([person["name"] for person in people], ["默认"])
        qa_id = db.add_person("测试同事", TEMPLATE_QA, self.path)
        self.assertEqual(db.get_categories(qa_id, self.path), template_categories(TEMPLATE_QA))
        with self.assertRaises(ValueError):
            db.add_person("测试同事", TEMPLATE_DEV, self.path)

    def test_entry_is_scoped_to_person(self):
        first_id = db.list_people(self.path)[0]["id"]
        second_id = db.add_person("李四", db_path=self.path)
        entry_id = db.add_entry(
            first_id,
            "2026-08-21",
            "完成接口",
            2,
            "开发实现类",
            db_path=self.path,
        )
        self.assertFalse(
            db.update_entry(
                entry_id,
                second_id,
                description="错误修改",
                hours=1,
                category="开发实现类",
                db_path=self.path,
            )
        )
        self.assertFalse(db.delete_entry(entry_id, second_id, self.path))
        self.assertEqual(
            db.get_entries(
                "2026-08-21", "2026-08-21", person_id=first_id, db_path=self.path
            )[0]["description"],
            "完成接口",
        )

    def test_replace_import_rolls_back_on_invalid_row(self):
        person_id = db.list_people(self.path)[0]["id"]
        db.add_entry(
            person_id,
            "2026-08-20",
            "原记录",
            1,
            "开发实现类",
            db_path=self.path,
        )
        invalid = [
            {
                "日期": "bad-date",
                "任务名称": "无效",
                "时长(h)": "2",
                "分类": "开发实现类",
            }
        ]
        with self.assertRaises(ValueError):
            db.import_rows(person_id, invalid, replace=True, db_path=self.path)
        entries = db.get_entries(
            "2026-01-01", "2026-12-31", person_id=person_id, db_path=self.path
        )
        self.assertEqual([entry["description"] for entry in entries], ["原记录"])

    def test_csv_and_consistent_backup(self):
        person_id = db.list_people(self.path)[0]["id"]
        db.add_entry(
            person_id,
            "2026-08-21",
            "CSV记录",
            3.5,
            "方案设计类",
            "说明",
            self.path,
        )
        text = db.export_csv("2026-08-01", "2026-08-31", person_id, self.path).decode(
            "utf-8-sig"
        )
        rows = list(csv.DictReader(io.StringIO(text)))
        self.assertEqual(rows[0]["任务名称"], "CSV记录")

        backup_dir = Path(self.temp_dir.name) / "backups"
        backup = db.backup_database(backup_dir, db_path=self.path)
        self.assertTrue(backup.is_file())
        self.assertEqual(
            db.get_entries(
                "2026-08-01", "2026-08-31", person_id=person_id, db_path=backup
            )[0]["notes"],
            "说明",
        )


class WebTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_path = db.DB_PATH
        db.DB_PATH = Path(self.temp_dir.name) / "web.db"
        db.init_db()
        os.environ.pop("WORKLOG_PASSWORD", None)
        from app import app

        app.config.update(TESTING=True, SECRET_KEY="test-secret")
        self.client = app.test_client()

    def tearDown(self):
        os.environ.pop("WORKLOG_PASSWORD", None)
        db.DB_PATH = self.old_path
        self.temp_dir.cleanup()

    def _csrf(self):
        with self.client.session_transaction() as session:
            session["_csrf"] = "test-token"
        return "test-token"

    def test_dashboard_health_and_entry(self):
        self.assertEqual(self.client.get("/healthz").status_code, 200)
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("每日填报".encode(), response.data)

        response = self.client.post(
            "/entries",
            data={
                "_csrf": self._csrf(),
                "work_date": "2026-08-21",
                "description": "Web记录",
                "hours": "2",
                "category": "开发实现类",
                "notes": "",
            },
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Web记录".encode(), response.data)

    def test_post_requires_csrf(self):
        response = self.client.post("/entries", data={})
        self.assertEqual(response.status_code, 400)

    def test_password_gate(self):
        os.environ["WORKLOG_PASSWORD"] = "secret"
        self.assertEqual(self.client.get("/").status_code, 302)
        self.client.get("/login")
        response = self.client.post(
            "/login",
            data={"_csrf": self._csrf(), "password": "secret"},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("每日填报".encode(), response.data)


if __name__ == "__main__":
    unittest.main()
