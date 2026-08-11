#!/usr/bin/env python3
"""轻量核心测试（标准库 unittest）。"""

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ical_client import parse_ics_events, normalize_ics_url  # noqa: E402
from templates import (  # noqa: E402
    TEMPLATE_DEV,
    TEMPLATE_QA,
    template_categories,
    format_help_markdown,
    get_template,
)
from ui_helpers import short_cal_event_name, LEGACY_CATEGORY_MAP  # noqa: E402
from db import (  # noqa: E402
    DEFAULT_CATEGORIES,
    LEGACY_CATEGORY_MAP as DB_LEGACY_MAP,
)


class TestIcal(unittest.TestCase):
    def test_normalize_webcal(self):
        self.assertTrue(normalize_ics_url("webcal://example.com/a.ics").startswith("https://"))

    def test_parse_basic(self):
        sample = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:t1
DTSTART:20260806T140000
DTEND:20260806T150000
SUMMARY:项目例会
LOCATION:3F
END:VEVENT
BEGIN:VEVENT
UID:t2
DTSTART;VALUE=DATE:20260810
DTEND;VALUE=DATE:20260811
SUMMARY:休假
END:VEVENT
END:VCALENDAR
"""
        ev = parse_ics_events(
            sample,
            range_start=date(2026, 8, 1),
            range_end=date(2026, 8, 31),
        )
        self.assertEqual(len(ev), 2)
        self.assertEqual(ev[0]["summary"], "项目例会")
        self.assertEqual(ev[1]["event_date"], "2026-08-10")


class TestTemplates(unittest.TestCase):
    def test_dev_seven(self):
        cats = template_categories(TEMPLATE_DEV)
        self.assertEqual(len(cats), 7)
        self.assertEqual(cats, DEFAULT_CATEGORIES)

    def test_qa_seven(self):
        cats = template_categories(TEMPLATE_QA)
        self.assertIn("用例设计", cats)
        self.assertEqual(len(cats), 7)

    def test_help_markdown(self):
        md = format_help_markdown(TEMPLATE_QA)
        self.assertIn("干什么用的", md)
        self.assertIn("用例执行", md)

    def test_get_template(self):
        self.assertEqual(get_template("nope")["id"], TEMPLATE_DEV)


class TestHelpers(unittest.TestCase):
    def test_short_name(self):
        self.assertEqual(short_cal_event_name("端午节 假期 第1天/共3天"), "端午节")
        self.assertIn("班", short_cal_event_name("国庆节 补班 第1天/共2天"))

    def test_legacy_map_consistent(self):
        self.assertEqual(LEGACY_CATEGORY_MAP, DB_LEGACY_MAP)


if __name__ == "__main__":
    unittest.main()
