#!/usr/bin/env python3
"""
Regression tests reproducing the failure recorded in error.log.

error.log shows the JSON customer export failing with
    ERROR - Error exporting data: 'dict' object has no attribute 'keys'
immediately followed by
    ERROR - Data processing completed successfully

Two defects combine to produce that log:
  1. export_customer_data() swallows the exception and logs only str(e),
     so the traceback (and the failing line) is lost.
  2. main() ignores the False return value and reports success anyway.

These tests inject the exact exception from the log into the JSON export
path (the second export_customer_data call in main) and assert the behaviour
we want after the fix. Against the current code they are expected to FAIL.
"""

import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

import process_data
from process_data import DataProcessor

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_ERROR_MESSAGE = "'dict' object has no attribute 'keys'"
SUCCESS_MESSAGE = "Data processing completed successfully"

_real_json_dump = json.dump


def _json_dump_failing_on_customer_export(obj, fp, *args, **kwargs):
    """Behave like json.dump, except for the JSON customer export, which
    raises the same AttributeError recorded in error.log."""
    if os.path.basename(getattr(fp, "name", "")) == "customers_export.json":
        raise AttributeError(LOG_ERROR_MESSAGE)
    return _real_json_dump(obj, fp, *args, **kwargs)


class ExportFailureTestBase(unittest.TestCase):
    """Runs each test in a temp dir holding copies of the sample CSVs, since
    main() uses hard-coded relative paths and writes its outputs to the cwd."""

    def setUp(self):
        self.orig_cwd = os.getcwd()
        self.tmp_dir = tempfile.mkdtemp()
        for name in ("customers.csv", "transactions.csv"):
            shutil.copy(os.path.join(REPO_DIR, name), self.tmp_dir)
        os.chdir(self.tmp_dir)

    def tearDown(self):
        os.chdir(self.orig_cwd)
        shutil.rmtree(self.tmp_dir)

    def make_processor(self):
        processor = DataProcessor("customers.csv")
        self.assertTrue(processor.load_data())
        self.assertTrue(processor.process_transactions("transactions.csv"))
        return processor


class TestMainReportsExportFailure(ExportFailureTestBase):
    """Reproduces the misleading 'completed successfully' line in error.log."""

    def run_main_with_failing_json_export(self):
        with mock.patch.object(
            process_data.json, "dump", side_effect=_json_dump_failing_on_customer_export
        ), self.assertLogs(process_data.logger, level="INFO") as logs:
            try:
                process_data.main()
                exit_code = 0
            except SystemExit as exc:
                exit_code = exc.code
        return logs, exit_code

    def test_error_from_log_is_raised_and_reported(self):
        logs, _ = self.run_main_with_failing_json_export()
        # Sanity check: we reproduced the same error line as error.log.
        self.assertIn(
            f"ERROR:{process_data.logger.name}:Error exporting data: {LOG_ERROR_MESSAGE}",
            logs.output,
        )

    def test_main_does_not_claim_success_after_export_failure(self):
        logs, _ = self.run_main_with_failing_json_export()
        success_lines = [line for line in logs.output if SUCCESS_MESSAGE in line]
        self.assertEqual(
            success_lines,
            [],
            "main() reported success even though the JSON export failed "
            "(the same contradiction seen at the end of error.log)",
        )

    def test_main_exits_non_zero_after_export_failure(self):
        _, exit_code = self.run_main_with_failing_json_export()
        self.assertNotIn(
            exit_code,
            (0, None),
            "main() must exit with a non-zero status when a step fails",
        )


class TestExportCustomerDataFailure(ExportFailureTestBase):
    """Reproduces the traceback-less error line in error.log."""

    def test_json_export_failure_returns_false(self):
        processor = self.make_processor()
        with mock.patch.object(
            process_data.json, "dump", side_effect=_json_dump_failing_on_customer_export
        ), self.assertLogs(process_data.logger, level="ERROR"):
            self.assertFalse(
                processor.export_customer_data("customers_export.json", "json")
            )

    def test_json_export_failure_logs_traceback(self):
        processor = self.make_processor()
        with mock.patch.object(
            process_data.json, "dump", side_effect=_json_dump_failing_on_customer_export
        ), self.assertLogs(process_data.logger, level="ERROR") as logs:
            processor.export_customer_data("customers_export.json", "json")

        record = logs.records[-1]
        self.assertIsNotNone(
            record.exc_info,
            "export errors are logged without a traceback, so the failing line "
            "in error.log cannot be identified",
        )
        self.assertIsInstance(record.exc_info[1], AttributeError)


class TestExportCustomerDataHappyPath(unittest.TestCase):
    """Control test: with healthy data the JSON export must keep working."""

    def test_json_export_round_trips(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            processor = DataProcessor(os.path.join(REPO_DIR, "customers.csv"))
            processor.load_data()
            processor.process_transactions(os.path.join(REPO_DIR, "transactions.csv"))

            out = os.path.join(tmp_dir, "customers_export.json")
            self.assertTrue(processor.export_customer_data(out, "json"))
            with open(out) as fh:
                self.assertEqual(json.load(fh), processor.customers)


if __name__ == "__main__":
    unittest.main(verbosity=2)
