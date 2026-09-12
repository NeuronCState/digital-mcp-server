import json
import tempfile
import unittest
from pathlib import Path

import digital_mcp_server as server


class DigitalMcpServerTest(unittest.TestCase):
    def test_build_inspect_and_testdata(self):
        design = {
            "elements": [
                {"id": "a", "type": "In", "label": "A", "x": 200, "y": 100},
                {"id": "b", "type": "In", "label": "B", "x": 200, "y": 140},
                {"id": "g", "type": "And", "x": 240, "y": 100},
                {"id": "y", "type": "Out", "label": "Y", "x": 340, "y": 120},
            ],
            "wires": [
                {"from": "a", "to": "g", "input": 0},
                {"from": "b", "to": "g", "input": 1},
                {"from": "g", "to": "y"},
            ],
            "tests": [
                {"inputs": {"A": 0, "B": 0}, "outputs": {"Y": 0}},
                {"inputs": {"A": 1, "B": 1}, "outputs": {"Y": 1}},
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "and.dig"
            result = server.build_circuit(design, path)
            self.assertEqual(result["element_count"], 5)  # includes the generated Testcase
            self.assertEqual(result["wire_count"], 3)
            xml = path.read_text(encoding="utf-8")
            self.assertIn("A B Y", xml)
            self.assertIn("1 1 1", xml)
            self.assertEqual(server.inspect_circuit(path)["wire_count"], 3)

    def test_protocol_initialize_and_tools_list(self):
        self.assertEqual(server.SCHEMA["elements"][2]["type"], "And")
        names = {tool["name"] for tool in server.TOOLS}
        self.assertIn("digital_build_circuit", names)
        self.assertIn("digital_run_tests", names)


if __name__ == "__main__":
    unittest.main()
