# Digital MCP Server

This is a stdio MCP server for the Digital logic simulator. It lets an AI
turn a circuit design into a `.dig` file, inspect it, run Digital's built-in
test cases, render SVG, and open the result in the modern macOS app.

The server intentionally does not call an external vision model. The MCP host
can see an attached image and should translate it into the `design` object
accepted by `digital_build_circuit`. This keeps credentials and image data in
the AI host while making circuit construction deterministic and testable.

## Run directly

From the repository root:

```bash
python3 mcp/digital_mcp_server.py
```

Example MCP client configuration:

```json
{
  "mcpServers": {
    "digital": {
      "command": "python3",
      "args": ["/absolute/path/to/Digital/mcp/digital_mcp_server.py"],
      "env": {
        "DIGITAL_JAR": "/absolute/path/to/Digital/source/target/Digital.jar"
      }
    }
  }
}
```

Generated files are written to `mcp/generated/`. The server uses Digital's
headless CLI for tests and SVG export, so it can validate circuits before
opening them in the GUI.

For a complete build loop, call `digital_build_circuit` with `run_tests: true`,
`render_svg: true`, and (on macOS) `open: true`. If the user supplies an image,
the MCP host's vision-capable AI should identify the gates, labels and wires,
then pass that result as `design`; the server performs the deterministic file
generation and Digital validation.

## Design object

```json
{
  "elements": [
    {"id": "a", "type": "In", "label": "A", "x": 200, "y": 100},
    {"id": "g", "type": "And", "x": 240, "y": 100},
    {"id": "y", "type": "Out", "label": "Y", "x": 340, "y": 120}
  ],
  "wires": [
    {"from": "a", "to": "g", "input": 0},
    {"from": "g", "to": "y"}
  ],
  "tests": [
    {"inputs": {"A": 0}, "outputs": {"Y": 0}},
    {"inputs": {"A": 1}, "outputs": {"Y": 1}}
  ]
}
```

For less common components, wires may use explicit coordinates with `p1` and
`p2`. The AI should call `digital_design_schema` when it needs the complete
schema and pin conventions.
