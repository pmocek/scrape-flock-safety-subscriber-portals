#!/usr/bin/env python3
"""Tests to ensure commit message generation is decoupled from global summaries."""

import importlib.util
import os
import sys
import unittest
from pathlib import Path
import yaml

REPO_ROOT = Path(__file__).parent.parent.resolve()
SCRIPTS_DIR = REPO_ROOT / "scripts"
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "scrape.yml"

# Dynamically import describe-diff.py
spec = importlib.util.spec_from_file_location("describe_diff", SCRIPTS_DIR / "describe-diff.py")
describe_diff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(describe_diff)


class TestWorkflowConfiguration(unittest.TestCase):
    def setUp(self):
        self.assertTrue(WORKFLOW_PATH.exists(), f"{WORKFLOW_PATH} does not exist")
        with open(WORKFLOW_PATH) as f:
            self.workflow = yaml.safe_load(f)

    def test_no_audit_or_ncic_commit_steps(self):
        """Scrape workflow should not capture global audit/NCIC output for commit body."""
        scrape_job = self.workflow.get("jobs", {}).get("scrape", {})
        steps = scrape_job.get("steps", [])
        step_names = [s.get("name") for s in steps if "name" in s]
        step_ids = [s.get("id") for s in steps if "id" in s]

        self.assertNotIn("audit", step_ids, "step 'audit' should not be present in scrape.yml")
        self.assertNotIn("ncic", step_ids, "step 'ncic' should not be present in scrape.yml")
        self.assertNotIn("Analyze audit CSVs", step_names)
        self.assertNotIn("Detect NCIC contradictions", step_names)

    def test_retained_matrix_and_health_steps(self):
        """Scrape workflow must still refresh conflict matrix and export health data."""
        scrape_job = self.workflow.get("jobs", {}).get("scrape", {})
        steps = scrape_job.get("steps", [])
        step_names = [s.get("name") for s in steps if "name" in s]

        self.assertIn("Refresh NCIC conflict matrix", step_names)
        self.assertIn("Export health dashboard data", step_names)

    def test_commit_step_structure(self):
        """Commit step should only use describe-diff.py output."""
        scrape_job = self.workflow.get("jobs", {}).get("scrape", {})
        steps = scrape_job.get("steps", [])
        commit_steps = [s for s in steps if s.get("name") == "Commit and push"]
        self.assertEqual(len(commit_steps), 1)

        run_script = commit_steps[0].get("run", "")
        self.assertNotIn("steps.audit.outputs.commit_body", run_script)
        self.assertNotIn("steps.ncic.outputs.commit_body", run_script)
        self.assertNotIn("Audit findings:", run_script)
        self.assertNotIn("NCIC findings:", run_script)
        self.assertIn('git commit -m "$MSG"', run_script)


class TestDescribeDiffLogic(unittest.TestCase):
    def test_describe_change_single_agency(self):
        prev = {
            "vehicles_30d": 1000,
            "total_cameras": 5,
            "hotlist_hits_30d": 10,
        }
        curr = {
            "vehicles_30d": 1050,
            "total_cameras": 5,
            "hotlist_hits_30d": 8,
        }
        desc = describe_diff.describe_change(prev, curr)
        self.assertIn("vehicles ▲50", desc)
        self.assertIn("hotlist_hits ▼2", desc)
        self.assertNotIn("COMMIT_BODY:", desc)

    def test_last_jsonl_line_parser(self):
        content = '{"slug": "test-1", "total_cameras": 2}\n{"slug": "test-1", "total_cameras": 3}\n'
        last = describe_diff.last_jsonl_line(content)
        self.assertIsNotNone(last)
        self.assertEqual(last["total_cameras"], 3)


if __name__ == "__main__":
    unittest.main()
