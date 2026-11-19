"""Tests for the journal helpers, queued-label dialog and indicator."""

import threading
import time
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QMessageBox

from shippy_gui.core import label_journal
from shippy_gui.core.models import RecipientAddress
from shippy_gui.widgets.label_queue import (
    PendingLabelsDialog,
    PendingLabelsIndicator,
    build_label_queued_box,
)

from journal_fakes import install_fake_journal, make_record


def wait_until(predicate, timeout_s=5.0):
    """Process Qt events until ``predicate()`` holds."""
    app = QApplication.instance()
    deadline = time.monotonic() + timeout_s
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("timed out waiting for the indicator")
        app.processEvents()
        time.sleep(0.01)


class LabelJournalHelperTests(unittest.TestCase):
    """Journal identity and timestamp helpers used by the widgets."""

    def test_identity_joins_both_street_lines(self):
        journal = install_fake_journal(self)
        identity = label_journal.identity_for(
            RecipientAddress(
                name="John Roe #123",
                street1="1 Unit Rd",
                street2="Bldg 4",
                city="Gatesville",
                state="TX",
                zipcode="76528",
            )
        )
        self.assertEqual(
            identity.recipient_key,
            journal.recipient_key(
                "John Roe #123", "1 Unit Rd Bldg 4", "Gatesville", "TX", "76528"
            ),
        )
        self.assertEqual(
            identity.recipient_label, "John Roe #123, 1 Unit Rd, Gatesville, TX"
        )

    def test_format_time_today_is_local_time(self):
        printed = datetime.now().replace(hour=14, minute=5).timestamp()
        self.assertEqual(label_journal.format_time(printed), "14:05")

    def test_format_time_older_shows_the_date(self):
        printed = (datetime.now() - timedelta(days=1)).replace(hour=8, minute=7)
        self.assertEqual(
            label_journal.format_time(printed.timestamp()),
            f"{printed.strftime('%b %d')} 08:07",
        )


class LabelQueuedDialogTests(unittest.TestCase):
    """The dialog shown when a label was saved to print later."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_text_is_calm_and_says_it_prints_later(self):
        box = build_label_queued_box(
            None, "Jane Doe, 123 Prison Rd, Huntsville, TX", "9400NEW"
        )

        self.assertEqual(box.windowTitle(), "Label Will Print Later")
        self.assertIs(box.icon(), QMessageBox.Icon.Information)
        text = box.text()
        self.assertIn("The label didn't print", text)
        self.assertIn("Recipient: Jane Doe, 123 Prison Rd, Huntsville, TX", text)
        self.assertIn("Tracking: 9400NEW", text)
        self.assertIn(
            "It was saved and will print automatically when the printer is " "working.",
            text,
        )
        self.assertNotIn("font-size", text)
        self.assertNotIn("color", text)
        self.assertNotIn("again", text)
        self.assertEqual(box.informativeText(), "")

    def test_recipient_is_html_escaped(self):
        box = build_label_queued_box(None, "A <b> & Co", "T1")
        self.assertIn("A &lt;b&gt; &amp; Co", box.text())


class PendingLabelsIndicatorTests(unittest.TestCase):
    """The "Waiting to print: N" status-bar indicator."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_hidden_when_nothing_waits(self):
        indicator = PendingLabelsIndicator(fetch=list)
        indicator.refresh()
        wait_until(lambda: not indicator.busy)
        self.assertEqual(indicator.count, 0)
        self.assertTrue(indicator.isHidden())

    def test_shows_count_and_updates(self):
        pending = [make_record(), make_record(tracking_code="9400TWO")]
        indicator = PendingLabelsIndicator(fetch=lambda: list(pending))

        indicator.refresh()
        wait_until(lambda: not indicator.busy)
        self.assertEqual(indicator.text(), "Waiting to print: 2")
        self.assertFalse(indicator.isHidden())

        pending.clear()
        indicator.refresh()
        wait_until(lambda: not indicator.busy)
        self.assertEqual(indicator.count, 0)
        self.assertTrue(indicator.isHidden())

    def test_failed_read_keeps_last_count(self):
        calls = {"n": 0}

        def flaky():
            calls["n"] += 1
            if calls["n"] > 1:
                raise OSError("journal locked")
            return [make_record()]

        indicator = PendingLabelsIndicator(fetch=flaky)
        indicator.refresh()
        wait_until(lambda: not indicator.busy)
        with self.assertLogs("shippy_gui.widgets.label_queue", "ERROR"):
            indicator.refresh()
            wait_until(lambda: not indicator.busy)
        self.assertEqual(indicator.text(), "Waiting to print: 1")

    def test_slow_read_does_not_block_or_pile_up(self):
        release = threading.Event()
        self.addCleanup(release.set)
        calls = {"n": 0}

        def slow():
            calls["n"] += 1
            release.wait(5)
            return [make_record()]

        indicator = PendingLabelsIndicator(fetch=slow)
        started = time.monotonic()
        indicator.refresh()
        indicator.refresh()  # skipped: a read is already running
        self.assertLess(time.monotonic() - started, 0.5)
        self.assertTrue(indicator.busy)

        release.set()
        wait_until(lambda: not indicator.busy)
        self.assertEqual(calls["n"], 1)
        self.assertEqual(indicator.count, 1)

    def test_timer_refreshes_periodically(self):
        calls = {"n": 0}

        def fetch():
            calls["n"] += 1
            return []

        indicator = PendingLabelsIndicator(fetch=fetch, interval_ms=20)
        indicator.start()
        try:
            wait_until(lambda: calls["n"] >= 3)
        finally:
            indicator._timer.stop()  # pylint: disable=protected-access

    def test_default_fetch_reads_the_journal(self):
        journal = install_fake_journal(self)
        journal.pending = [make_record()]
        indicator = PendingLabelsIndicator()
        indicator.refresh()
        wait_until(lambda: not indicator.busy)
        self.assertEqual(indicator.count, 1)

    def test_click_opens_details(self):
        indicator = PendingLabelsIndicator(fetch=lambda: [make_record()])
        indicator.refresh()
        wait_until(lambda: not indicator.busy)
        with patch(
            "shippy_gui.widgets.label_queue.PendingLabelsDialog.exec"
        ) as mock_exec:
            indicator.click()
        mock_exec.assert_called_once_with()

    def test_details_dialog_lists_labels(self):
        queued_at = datetime.now().replace(hour=9, minute=41).timestamp()
        dialog = PendingLabelsDialog(
            [
                make_record(updated=queued_at, file="/tmp/x.png"),
                make_record(tracking_code="9400TWO", status="check_printer"),
            ]
        )
        table = dialog.table
        self.assertEqual(table.rowCount(), 2)
        self.assertEqual(
            [table.horizontalHeaderItem(i).text() for i in range(4)],
            ["Recipient", "Tracking", "Status", "Queued at"],
        )
        self.assertEqual(
            table.item(0, 0).text(), "Jane Doe, 123 Prison Rd, Huntsville, TX"
        )
        self.assertEqual(table.item(0, 1).text(), "9400OLD")
        self.assertEqual(table.item(0, 2).text(), "Queued - prints automatically")
        self.assertEqual(table.item(0, 3).text(), "09:41")
        self.assertEqual(table.item(1, 2).text(), "Check the printer")


if __name__ == "__main__":
    unittest.main()
