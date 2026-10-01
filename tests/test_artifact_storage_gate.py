import importlib.util
import io
import json
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / '.github/scripts/artifact_storage_gate.py'
spec = importlib.util.spec_from_file_location('artifact_storage_gate', SCRIPT)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class ArtifactStorageGateTests(unittest.TestCase):
    def test_inventory_paginates_and_sums_all_bytes(self):
        pages = [
            {'total_count': 101, 'artifacts': [{'size_in_bytes': 2}] * 100},
            {'total_count': 101, 'artifacts': [{'size_in_bytes': 3}]},
        ]
        calls = []
        def opener(request, timeout):
            calls.append((request.full_url, timeout))
            return io.BytesIO(json.dumps(pages.pop(0)).encode())
        self.assertEqual(gate.repository_bytes('owner/repo', 'test-token', opener), 203)
        self.assertEqual(len(calls), 2)
        self.assertIn('page=2', calls[1][0])

    def test_incomplete_or_changed_inventory_fails_closed(self):
        for second in ({'total_count': 101, 'artifacts': []},
                       {'total_count': 102, 'artifacts': [{'size_in_bytes': 1}]}):
            pages = [{'total_count': 101, 'artifacts': [{'size_in_bytes': 1}] * 100}, second]
            def opener(request, timeout):
                return io.BytesIO(json.dumps(pages.pop(0)).encode())
            with self.assertRaises(ValueError):
                gate.repository_bytes('owner/repo', 'test-token', opener)

    def test_cap_candidate_size_and_safety_margin(self):
        self.assertTrue(gate.may_upload(300_000_000, 25_000_000))
        self.assertFalse(gate.may_upload(349_000_000, 1))
        self.assertFalse(gate.may_upload(300_000_000, 25_000_001))
        self.assertFalse(gate.may_upload(-1, 1))
        self.assertFalse(gate.may_upload(0, 0))


if __name__ == '__main__':
    unittest.main()
