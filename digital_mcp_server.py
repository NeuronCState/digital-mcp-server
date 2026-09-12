#!/usr/bin/env python3
"""MCP server for building, validating and running Digital circuits.

The server deliberately uses only the Python standard library.  An MCP host
provides the natural-language/image understanding; this server turns the
host's structured circuit design into Digital's XML format and uses Digital's
headless CLI for validation and tests.
"""

from __future__ import annotations

import html
import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


ROOT = Path(os.environ.get("DIGITAL_PROJECT_ROOT", Path(__file__).resolve().parents[1])).expanduser().resolve()
SERVER_ROOT = Path(__file__).resolve().parent
GENERATED = Path(os.environ.get("DIGITAL_MCP_OUTPUT_DIR", SERVER_ROOT / "generated")).expanduser().resolve()
SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")


class ToolError(Exception):
    """An expected, user-facing MCP tool error."""


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _number(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ToolError(f"{name} must be a number")
    return int(value)


def _safe_output(name: str | None) -> Path:
    filename = name or f"circuit-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}.dig"
    if not SAFE_NAME.fullmatch(filename) or not filename.endswith(".dig"):
        raise ToolError("file_name must be a simple .dig filename")
    GENERATED.mkdir(parents=True, exist_ok=True)
    return GENERATED / filename


def _input_path(value: Any, suffix: str | None = None) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ToolError("path must be a non-empty string")
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise ToolError(f"file does not exist: {path}")
    if suffix and path.suffix.lower() != suffix.lower():
        raise ToolError(f"expected a {suffix} file: {path}")
    return path


def _element_attributes(parent: ET.Element, attrs: dict[str, Any]) -> None:
    entries = ET.SubElement(parent, "elementAttributes")
    for key, value in attrs.items():
        entry = ET.SubElement(entries, "entry")
        ET.SubElement(entry, "string").text = str(key)
        if key == "Testdata":
            data = ET.SubElement(entry, "testData")
            ET.SubElement(data, "dataString").text = str(value)
        elif isinstance(value, bool):
            ET.SubElement(entry, "boolean").text = str(value).lower()
        elif isinstance(value, int) and not isinstance(value, bool):
            ET.SubElement(entry, "int").text = str(value)
        elif isinstance(value, float):
            ET.SubElement(entry, "double").text = str(value)
        else:
            ET.SubElement(entry, "string").text = str(value)


def _pin(element: dict[str, Any], pin: Any, output: bool) -> tuple[int, int]:
    """Resolve the common Digital pin positions used by generated circuits."""
    x = _number(element.get("x", element.get("pos", {}).get("x", 0)), "element.x")
    y = _number(element.get("y", element.get("pos", {}).get("y", 0)), "element.y")
    kind = str(element.get("type", ""))
    if output:
        if kind in {"In", "Const", "Clock", "VDD", "Ground", "PullUp", "PullDown"}:
            return x, y
        if kind in {"Not", "Buffer"}:
            return x + 40, y
        return x + 60, y + 20
    index = int(pin or 0)
    if kind in {"Out", "Probe"}:
        return x, y
    if kind in {"Not", "Buffer"}:
        return x, y
    return x, y + index * 40


def _wire_point(design: dict[str, Any], endpoint: Any, output: bool) -> tuple[int, int]:
    if isinstance(endpoint, dict) and "x" in endpoint and "y" in endpoint:
        return _number(endpoint["x"], "wire point.x"), _number(endpoint["y"], "wire point.y")
    if not isinstance(endpoint, str):
        raise ToolError("wire endpoint must be an element id or {x,y}")
    element = next((e for e in design["elements"] if e.get("id") == endpoint), None)
    if element is None:
        raise ToolError(f"wire references unknown element: {endpoint}")
    return _pin(element, 0, output)


def _test_data(tests: list[dict[str, Any]]) -> str:
    if not tests:
        return ""
    input_names = list(tests[0].get("inputs", {}).keys())
    output_names = list(tests[0].get("outputs", {}).keys())
    names = input_names + output_names
    rows = [" ".join(names)]
    for case in tests:
        inputs = case.get("inputs", {})
        outputs = case.get("outputs", {})
        missing = [n for n in names if n not in inputs and n not in outputs]
        if missing:
            raise ToolError(f"test case is missing values for: {', '.join(missing)}")
        rows.append(" ".join(str(inputs.get(n, outputs.get(n))) for n in names))
    return "\n".join(rows)


def build_circuit(design: dict[str, Any], output: Path) -> dict[str, Any]:
    if not isinstance(design, dict):
        raise ToolError("design must be an object")
    elements = design.get("elements", [])
    wires = design.get("wires", [])
    if not isinstance(elements, list) or not isinstance(wires, list):
        raise ToolError("design.elements and design.wires must be arrays")
    ids: set[str] = set()
    root = ET.Element("circuit")
    ET.SubElement(root, "version").text = "1"
    ET.SubElement(root, "attributes")
    visual = ET.SubElement(root, "visualElements")
    for element in elements:
        element_id = element.get("id")
        kind = element.get("type")
        if not isinstance(element_id, str) or not element_id or element_id in ids:
            raise ToolError("each element needs a unique non-empty id")
        if not isinstance(kind, str) or not SAFE_NAME.fullmatch(kind):
            raise ToolError(f"invalid element type: {kind!r}")
        ids.add(element_id)
        ve = ET.SubElement(visual, "visualElement")
        ET.SubElement(ve, "elementName").text = kind
        attrs = dict(element.get("attributes", {}))
        if "label" in element:
            attrs["Label"] = element["label"]
        if "bits" in element:
            attrs["Bits"] = _number(element["bits"], "element.bits")
        if "inputs" in element:
            attrs["Inputs"] = _number(element["inputs"], "element.inputs")
        if kind == "Testcase" and "tests" in design:
            attrs["Testdata"] = _test_data(design["tests"])
        _element_attributes(ve, attrs)
        pos = ET.SubElement(ve, "pos")
        pos.set("x", str(_number(element.get("x", element.get("pos", {}).get("x", 0)), "element.x")))
        pos.set("y", str(_number(element.get("y", element.get("pos", {}).get("y", 0)), "element.y")))
    wires_node = ET.SubElement(root, "wires")
    for wire in wires:
        if not isinstance(wire, dict):
            raise ToolError("each wire must be an object")
        if "p1" in wire and "p2" in wire:
            p1, p2 = _wire_point(design, wire["p1"], True), _wire_point(design, wire["p2"], False)
        elif "from" in wire and "to" in wire:
            p1 = _wire_point(design, wire["from"], True)
            p2 = _wire_point(design, wire["to"], False)
            if isinstance(wire["to"], str):
                target = next(e for e in elements if e.get("id") == wire["to"])
                p2 = _pin(target, wire.get("input", 0), False)
        else:
            raise ToolError("each wire needs from/to or p1/p2")
        node = ET.SubElement(wires_node, "wire")
        for tag, point in (("p1", p1), ("p2", p2)):
            child = ET.SubElement(node, tag)
            child.set("x", str(point[0]))
            child.set("y", str(point[1]))
    if design.get("tests"):
        # A testcase element is optional for callers that only want a circuit,
        # but adding one makes the generated file directly runnable by Digital.
        if not any(e.get("type") == "Testcase" for e in elements):
            ve = ET.SubElement(visual, "visualElement")
            ET.SubElement(ve, "elementName").text = "Testcase"
            _element_attributes(ve, {"Testdata": _test_data(design["tests"])})
            ET.SubElement(ve, "pos", x="0", y="0")
    ET.SubElement(root, "measurementOrdering")
    ET.indent(root, space="  ")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text('<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(root, encoding="unicode"), encoding="utf-8")
    return inspect_circuit(output)


def inspect_circuit(path: Path) -> dict[str, Any]:
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise ToolError(f"invalid Digital XML: {exc}") from exc
    elements = []
    for ve in root.findall("./visualElements/visualElement"):
        attrs: dict[str, Any] = {}
        entries = ve.find("elementAttributes")
        if entries is not None:
            for entry in entries.findall("entry"):
                key = entry.findtext("string")
                strings = entry.findall("string")
                if len(strings) > 1:
                    value = strings[1].text
                elif entry.find("testData") is not None:
                    value = entry.findtext("testData/dataString")
                else:
                    value = next((child.text for child in list(entry) if child.tag != "string"), None)
                if key:
                    attrs[key] = value
        pos = ve.find("pos")
        elements.append({"type": ve.findtext("elementName"), "x": int(pos.get("x", 0)), "y": int(pos.get("y", 0)), "attributes": attrs})
    wires = []
    for wire in root.findall("./wires/wire"):
        wires.append({tag: {"x": int(wire.find(tag).get("x")), "y": int(wire.find(tag).get("y"))} for tag in ("p1", "p2")})
    return {"path": str(path), "elements": elements, "element_count": len(elements), "wire_count": len(wires), "wires": wires}


def _jar() -> Path:
    candidates = []
    if os.environ.get("DIGITAL_JAR"):
        candidates.append(Path(os.environ["DIGITAL_JAR"]).expanduser())
    candidates += [
        ROOT / "source/target/Digital.jar",
        ROOT / "modern/dist/Digital.jar",
        ROOT / "target/Digital.jar",
        SERVER_ROOT / "Digital.jar",
    ]
    for path in candidates:
        if path.is_file():
            return path
    raise ToolError("Digital.jar not found; run Maven build or set DIGITAL_JAR")


def _java() -> str:
    configured = os.environ.get("DIGITAL_JAVA")
    candidates = [
        Path(configured).expanduser() if configured else None,
        ROOT / ".runtime/desktop-runtime/bin/java",
        ROOT / ".runtime/jdk-21.0.12.1+1/Contents/Home/bin/java",
    ]
    for path in candidates:
        if path and path.is_file():
            return str(path)
    return "java"


def run_tests(path: Path, timeout: int, verbose: bool) -> dict[str, Any]:
    command = [_java(), "-Djava.awt.headless=true", "-cp", str(_jar()), "CLI", "test", "-circ", str(path)]
    if verbose:
        command += ["-verbose"]
    try:
        completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise ToolError(f"Digital test timed out after {timeout}s") from exc
    output = (completed.stdout + completed.stderr).strip()
    return {"passed": completed.returncode == 0, "exit_code": completed.returncode, "output": output, "command": command}


def render_svg(path: Path, timeout: int) -> dict[str, Any]:
    svg = path.with_suffix(path.suffix + ".svg")
    command = [_java(), "-Djava.awt.headless=true", "-cp", str(_jar()), "CLI", "svg", "-dig", str(path), "-svg", str(svg)]
    try:
        completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise ToolError(f"Digital SVG export timed out after {timeout}s") from exc
    if completed.returncode != 0:
        raise ToolError((completed.stdout + completed.stderr).strip() or "Digital SVG export failed")
    return {"svg_path": str(svg), "command": command}


def open_circuit(path: Path, app_path: str | None) -> dict[str, Any]:
    if sys.platform != "darwin":
        raise ToolError("digital_open_circuit currently requires macOS")
    configured_app = os.environ.get("DIGITAL_APP")
    app = Path(app_path or configured_app).expanduser() if (app_path or configured_app) else ROOT / "modern/dist/Digital.app"
    if not app.exists():
        raise ToolError(f"Digital.app not found: {app}")
    subprocess.Popen(["open", "-a", str(app), str(path)], cwd=ROOT)
    return {"opened": True, "app": str(app), "path": str(path)}


TOOLS = [
    {"name": "digital_build_circuit", "description": "Build a Digital .dig file from a structured circuit design, optionally test, render and open it. The host AI should translate text or an attached image into this design object.", "inputSchema": {"type": "object", "required": ["design"], "properties": {"design": {"type": "object", "description": "Object with elements, wires, and optional tests; see digital_design_schema."}, "file_name": {"type": "string", "description": "Optional simple .dig filename."}, "run_tests": {"type": "boolean", "description": "Run embedded test cases after building."}, "render_svg": {"type": "boolean", "description": "Export an SVG preview after building."}, "open": {"type": "boolean", "description": "Open the generated circuit in Digital.app on macOS."}, "timeout_seconds": {"type": "integer", "default": 30}}}},
    {"name": "digital_inspect_circuit", "description": "Read a Digital .dig file and return its elements, positions, attributes and wires.", "inputSchema": {"type": "object", "required": ["path"], "properties": {"path": {"type": "string"}}}},
    {"name": "digital_run_tests", "description": "Run the test cases embedded in a Digital .dig file through Digital's headless CLI.", "inputSchema": {"type": "object", "required": ["path"], "properties": {"path": {"type": "string"}, "timeout_seconds": {"type": "integer", "default": 30}, "verbose": {"type": "boolean", "default": True}}}},
    {"name": "digital_render_circuit", "description": "Render a Digital .dig file to SVG using Digital's CLI.", "inputSchema": {"type": "object", "required": ["path"], "properties": {"path": {"type": "string"}, "timeout_seconds": {"type": "integer", "default": 30}}}},
    {"name": "digital_open_circuit", "description": "Open a .dig file in the modern Digital.app on macOS.", "inputSchema": {"type": "object", "required": ["path"], "properties": {"path": {"type": "string"}, "app_path": {"type": "string"}}}},
    {"name": "digital_design_schema", "description": "Return the structured design schema and supported common gate pin conventions.", "inputSchema": {"type": "object", "properties": {}}},
]


SCHEMA = {"elements": [{"id": "a", "type": "In", "label": "A", "x": 200, "y": 100}, {"id": "b", "type": "In", "label": "B", "x": 200, "y": 140}, {"id": "and1", "type": "And", "x": 240, "y": 100}, {"id": "y", "type": "Out", "label": "Y", "x": 340, "y": 120}], "wires": [{"from": "a", "to": "and1", "input": 0}, {"from": "b", "to": "and1", "input": 1}, {"from": "and1", "to": "y"}], "tests": [{"inputs": {"A": 0, "B": 0}, "outputs": {"Y": 0}}, {"inputs": {"A": 1, "B": 1}, "outputs": {"Y": 1}}], "supported_types": ["In", "Out", "And", "Or", "XOr", "XNOr", "NAnd", "NOr", "Not", "Clock", "Const", "Ground", "VDD", "Testcase"], "wire_note": "For uncommon elements, use explicit p1/p2 coordinates. Common gate inputs are spaced 40 units vertically."}


def call_tool(name: str, args: dict[str, Any]) -> Any:
    if name == "digital_design_schema":
        return SCHEMA
    if name == "digital_build_circuit":
        output = _safe_output(args.get("file_name"))
        result = build_circuit(args.get("design"), output)
        timeout = max(1, int(args.get("timeout_seconds", 30)))
        if args.get("run_tests"):
            result["tests"] = run_tests(output, timeout, True)
        if args.get("render_svg"):
            result["render"] = render_svg(output, timeout)
        if args.get("open"):
            result["open"] = open_circuit(output, args.get("app_path"))
        return result
    path = _input_path(args.get("path"), ".dig")
    if name == "digital_inspect_circuit":
        return inspect_circuit(path)
    if name == "digital_run_tests":
        return run_tests(path, max(1, int(args.get("timeout_seconds", 30))), bool(args.get("verbose", True)))
    if name == "digital_render_circuit":
        return render_svg(path, max(1, int(args.get("timeout_seconds", 30))))
    if name == "digital_open_circuit":
        return open_circuit(path, args.get("app_path"))
    raise ToolError(f"unknown tool: {name}")


def response(request_id: Any, result: Any = None, error: dict[str, Any] | None = None) -> None:
    message: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id}
    if error is not None:
        message["error"] = error
    else:
        message["result"] = result
    sys.stdout.write(_json(message) + "\n")
    sys.stdout.flush()


def main() -> None:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
            method = request.get("method")
            request_id = request.get("id")
            if method == "initialize":
                response(request_id, {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "digital-mcp", "version": "0.1.0"}})
            elif method == "notifications/initialized":
                continue
            elif method == "ping":
                response(request_id, {})
            elif method == "tools/list":
                response(request_id, {"tools": TOOLS})
            elif method == "tools/call":
                params = request.get("params", {})
                try:
                    result = call_tool(params.get("name"), params.get("arguments", {}))
                    response(request_id, {"content": [{"type": "text", "text": _json(result)}], "structuredContent": result, "isError": False})
                except (ToolError, ValueError, OSError) as exc:
                    response(request_id, {"content": [{"type": "text", "text": str(exc)}], "isError": True})
            else:
                response(request_id, error={"code": -32601, "message": f"method not found: {method}"})
        except json.JSONDecodeError as exc:
            response(None, error={"code": -32700, "message": str(exc)})
        except Exception as exc:  # keep the stdio server alive for the next request
            response(request.get("id") if isinstance(request, dict) else None, error={"code": -32603, "message": str(exc)})


if __name__ == "__main__":
    main()
