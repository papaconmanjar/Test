# cadwork MCP connector

Lets Claude (Claude Desktop, Claude Code, or any other MCP client) read and draw in a
**cadwork 3D** model. It works the same way as the AutoCAD MCP connectors.

```
Claude ──MCP (stdio)──► server/cadwork_mcp_server.py ──TCP 127.0.0.1:53002──► claude_bridge plugin (inside cadwork 3D)
```

cadwork has no external automation interface. Its Python API only runs **inside**
cadwork, as a plugin. So the connector has two parts:

| Part | Runs in | What it does |
|---|---|---|
| `cadwork_plugin/claude_bridge/` | cadwork's own Python | Listens on localhost and runs commands through the cadwork API |
| `server/cadwork_mcp_server.py` | your normal Python | The MCP server Claude talks to. It forwards each tool call to the bridge |

## Installation (Windows, on the machine where cadwork runs)

### 1. Install the bridge plugin in cadwork

Copy the `claude_bridge` folder into cadwork's plugin folder. The folder name and the `.py`
file name must stay the same:

```
C:\Users\Public\Documents\cadwork\userprofile_<version>\3d\API.x64\claude_bridge\claude_bridge.py
```

(The plugin folder is the one where your other cadwork Python plugins live. In cadwork 3D,
look for it in the plugin bar settings, or under *Help → Info → userprofile*.) Restart
cadwork. **claude_bridge** then shows up in the plugin bar.

### 2. Install the MCP server

Use Python 3.10 or newer, separate from cadwork's Python:

```powershell
cd cadwork-mcp\server
pip install -r requirements.txt
```

### 3. Register it with Claude

**Claude Desktop**: edit `%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "cadwork": {
      "command": "python",
      "args": ["C:\\path\\to\\cadwork-mcp\\server\\cadwork_mcp_server.py"]
    }
  }
}
```

**Claude Code**:

```powershell
claude mcp add cadwork -- python C:\path\to\cadwork-mcp\server\cadwork_mcp_server.py
```

## Usage

1. Open your model in cadwork 3D.
2. Click **claude_bridge** in the plugin bar. The message line shows
   `Claude bridge listening on 127.0.0.1:53002`.
3. Ask Claude something like:
   - *"List the beams in the model with their sizes"*
   - *"Draw a 6 × 4 m floor frame: 120×240 C24 joists at 625 mm spacing, group House, subgroup Ground floor"*
   - *"Copy the selected rafters 2 m along X"*
4. When you are done, ask Claude to **stop the bridge**. That gives you back the cadwork UI.

> **Important:** the cadwork API is not thread-safe, so the bridge runs on cadwork's main
> thread. **cadwork's UI is busy while the bridge is running.** Stop it from Claude
> (`stop_bridge`) to work in cadwork yourself, then start it again from the plugin bar. It
> also stops by itself after 30 minutes without requests.

### Tools

| Tool | Purpose |
|---|---|
| `cadwork_status` | Connection check: version, file, element count |
| `list_elements` | IDs in the model (`all`, `active` = the current selection, `visible`), optionally with details |
| `get_element_info` | Name, group, subgroup, material, colour, dimensions, volume, p1/p2/p3 |
| `create_beam`, `create_circular_beam`, `create_panel`, `create_line`, `create_node` | Create geometry, optionally with attributes |
| `move_elements`, `copy_elements`, `rotate_elements`, `delete_elements` | Edit geometry |
| `set_attributes`, `set_visibility` | Name, group, subgroup, material, comment, colour; show or hide |
| `list_api_functions` | Shows the cadwork Python API **of your installed version**, so Claude can find any function |
| `execute_python` | Runs arbitrary Python inside cadwork, for anything else (processing, exports, lists…) |
| `stop_bridge` | Gives the cadwork UI back |

Units are millimetres and points are `[x, y, z]`. A beam runs from `p1` to `p2`. The
optional `p3` sets the height direction. By default it is global Z for horizontal members
and global Y for vertical ones.

## Configuration

Set these as environment variables. On the bridge side they must be set before cadwork starts.

| Variable | Default | Side |
|---|---|---|
| `CADWORK_MCP_PORT` | `53002` | both |
| `CADWORK_MCP_HOST` | `127.0.0.1` | server |
| `CADWORK_MCP_TIMEOUT` | `120` s per command | server |
| `CADWORK_MCP_IDLE_TIMEOUT` | `1800` s | bridge |
| `CADWORK_MCP_ALLOW_PYTHON` | `1`. Set to `0` to disable `execute_python` | bridge |

## Security

The bridge only listens on `127.0.0.1`. `execute_python` can run any code inside cadwork
with your user's rights. Set `CADWORK_MCP_ALLOW_PYTHON=0` if you don't want that.

## Compatibility notes

The bridge uses the standard cadwork Python controllers (`element_controller`,
`geometry_controller`, `attribute_controller`, `visualization_controller`,
`utility_controller`). Function names have changed a little between cadwork versions. If a
dedicated tool fails on your version, Claude can call `list_api_functions` to find the right
name and do the job with `execute_python`. Please report the mismatch so the bridge can be
fixed.

## Development

```bash
pip install -r server/requirements.txt pytest
python -m pytest tests/
```

The tests replace the cadwork modules with in-memory stubs. They run the real MCP server
functions against the real bridge over TCP, so they run without cadwork.
