"""MCP server that lets Claude drive cadwork 3D.

Claude <--stdio/MCP--> this server <--TCP JSON lines--> claude_bridge plugin (inside cadwork)

Run:  python cadwork_mcp_server.py
Env:  CADWORK_MCP_HOST (default 127.0.0.1), CADWORK_MCP_PORT (default 53002),
      CADWORK_MCP_TIMEOUT seconds per command (default 120)
"""

import itertools
import json
import os
import socket
from typing import Any, Literal, Optional

try:  # mcp >= 2
    from mcp.server.mcpserver import MCPServer as _Server
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server
    from mcp.server.fastmcp.exceptions import ToolError

HOST = os.environ.get("CADWORK_MCP_HOST", "127.0.0.1")
PORT = int(os.environ.get("CADWORK_MCP_PORT", "53002"))
TIMEOUT_S = float(os.environ.get("CADWORK_MCP_TIMEOUT", "120"))

Point = list[float]

INSTRUCTIONS = """\
Tools for drawing and editing a cadwork 3D model through a bridge plugin running inside cadwork.
- All coordinates and dimensions are in millimetres; points are [x, y, z].
- Beams/panels go from p1 to p2 (length axis). Optional p3 sets the height direction
  (default: global Z for horizontal members, global Y for vertical ones).
- Call `cadwork_status` first. If the bridge is not reachable, ask the user to start the
  `claude_bridge` plugin from cadwork's plugin bar.
- For anything without a dedicated tool, use `list_api_functions` to discover the cadwork
  Python API of the user's version and `execute_python` to call it.
"""

mcp = _Server("cadwork", instructions=INSTRUCTIONS)
_ids = itertools.count(1)


class BridgeError(ToolError):
    """Raised for bridge/cadwork failures; its message is shown to Claude as-is."""


def send_command(command: str, params: Optional[dict] = None) -> Any:
    """Send one command to the cadwork bridge and return its result."""
    request = {"id": next(_ids), "command": command, "params": params or {}}
    try:
        with socket.create_connection((HOST, PORT), timeout=5) as sock:
            sock.settimeout(TIMEOUT_S)
            sock.sendall((json.dumps(request) + "\n").encode("utf-8"))
            buf = b""
            while b"\n" not in buf:
                chunk = sock.recv(65536)
                if not chunk:
                    raise BridgeError("cadwork bridge closed the connection")
                buf += chunk
    except OSError as exc:
        raise BridgeError(
            f"Cannot reach the cadwork bridge at {HOST}:{PORT} ({exc}). "
            "Start the 'claude_bridge' plugin in cadwork 3D and try again."
        ) from exc
    response = json.loads(buf.split(b"\n", 1)[0].decode("utf-8"))
    if not response.get("ok"):
        detail = response.get("traceback") or ""
        raise BridgeError(f"cadwork error: {response.get('error')}\n{detail}".strip())
    return response.get("result")


def _clean(**kwargs) -> dict:
    return {k: v for k, v in kwargs.items() if v is not None}


# ------------------------------------------------------------------ tools

@mcp.tool()
def cadwork_status() -> dict:
    """Check the connection to cadwork; returns version, open file and element count."""
    return send_command("ping")


@mcp.tool()
def list_elements(
    scope: Literal["all", "active", "visible"] = "all",
    limit: int = 200,
    detailed: bool = False,
) -> dict:
    """List element IDs in the model. scope='active' means the user's current selection.
    detailed=True also returns dimensions, points, material and colour."""
    return send_command("list_elements", _clean(scope=scope, limit=limit, detailed=detailed))


@mcp.tool()
def get_element_info(ids: list[int]) -> list:
    """Get name, group, subgroup, material, colour, dimensions (mm), volume and p1/p2/p3 of elements."""
    return send_command("get_element_info", {"ids": ids})


@mcp.tool()
def create_beam(
    width: float,
    height: float,
    p1: Point,
    p2: Point,
    p3: Optional[Point] = None,
    name: Optional[str] = None,
    group: Optional[str] = None,
    subgroup: Optional[str] = None,
    material: Optional[str] = None,
    comment: Optional[str] = None,
    color: Optional[int] = None,
) -> dict:
    """Create a rectangular beam (width x height mm) from p1 to p2. Returns the new element id."""
    return send_command("create_beam", _clean(
        width=width, height=height, p1=p1, p2=p2, p3=p3, name=name, group=group,
        subgroup=subgroup, material=material, comment=comment, color=color))


@mcp.tool()
def create_circular_beam(
    diameter: float,
    p1: Point,
    p2: Point,
    p3: Optional[Point] = None,
    name: Optional[str] = None,
    group: Optional[str] = None,
    subgroup: Optional[str] = None,
    material: Optional[str] = None,
    comment: Optional[str] = None,
    color: Optional[int] = None,
) -> dict:
    """Create a round beam/post with the given diameter (mm) from p1 to p2."""
    return send_command("create_circular_beam", _clean(
        diameter=diameter, p1=p1, p2=p2, p3=p3, name=name, group=group,
        subgroup=subgroup, material=material, comment=comment, color=color))


@mcp.tool()
def create_panel(
    width: float,
    thickness: float,
    p1: Point,
    p2: Point,
    p3: Optional[Point] = None,
    name: Optional[str] = None,
    group: Optional[str] = None,
    subgroup: Optional[str] = None,
    material: Optional[str] = None,
    comment: Optional[str] = None,
    color: Optional[int] = None,
) -> dict:
    """Create a rectangular panel (e.g. CLT, OSB sheathing): length p1->p2, given width and thickness (mm)."""
    return send_command("create_panel", _clean(
        width=width, thickness=thickness, p1=p1, p2=p2, p3=p3, name=name, group=group,
        subgroup=subgroup, material=material, comment=comment, color=color))


@mcp.tool()
def create_line(p1: Point, p2: Point, name: Optional[str] = None, color: Optional[int] = None) -> dict:
    """Create a 3D line from p1 to p2 (useful as axis/reference geometry)."""
    return send_command("create_line", _clean(p1=p1, p2=p2, name=name, color=color))


@mcp.tool()
def create_node(point: Point, name: Optional[str] = None) -> dict:
    """Create a node (reference point) at the given location."""
    return send_command("create_node", _clean(point=point, name=name))


@mcp.tool()
def delete_elements(ids: list[int]) -> dict:
    """Delete elements by id. Confirm with the user before deleting anything they did not create in this session."""
    return send_command("delete_elements", {"ids": ids})


@mcp.tool()
def move_elements(ids: list[int], vector: Point) -> dict:
    """Translate elements by vector [dx, dy, dz] (mm)."""
    return send_command("move_elements", {"ids": ids, "vector": vector})


@mcp.tool()
def copy_elements(ids: list[int], vector: Point) -> dict:
    """Copy elements, offsetting the copies by vector [dx, dy, dz] (mm). Returns new ids."""
    return send_command("copy_elements", {"ids": ids, "vector": vector})


@mcp.tool()
def rotate_elements(ids: list[int], origin: Point, angle_deg: float, axis: Point = [0, 0, 1]) -> dict:
    """Rotate elements about an axis through origin. axis is a direction vector, angle in degrees."""
    return send_command("rotate_elements", {"ids": ids, "origin": origin, "axis": axis, "angle_deg": angle_deg})


@mcp.tool()
def set_attributes(
    ids: list[int],
    name: Optional[str] = None,
    group: Optional[str] = None,
    subgroup: Optional[str] = None,
    material: Optional[str] = None,
    comment: Optional[str] = None,
    color: Optional[int] = None,
) -> dict:
    """Set name, group (building), subgroup (floor), material, comment and/or colour (cadwork colour number 1-255)."""
    return send_command("set_attributes", _clean(
        ids=ids, name=name, group=group, subgroup=subgroup, material=material,
        comment=comment, color=color))


@mcp.tool()
def set_visibility(ids: list[int], visible: bool = True) -> dict:
    """Show or hide elements."""
    return send_command("set_visibility", {"ids": ids, "visible": visible})


@mcp.tool()
def list_api_functions(module: str = "element_controller", filter: Optional[str] = None) -> list:
    """List functions (with docstrings) of a cadwork Python API module in the user's installed version,
    e.g. element_controller, geometry_controller, attribute_controller, visualization_controller,
    utility_controller, file_controller, cadwork. Use `filter` to search by substring."""
    return send_command("list_api_functions", _clean(module=module, filter=filter))


@mcp.tool()
def execute_python(code: str) -> dict:
    """Execute Python code inside cadwork for anything the other tools don't cover
    (joints/processing, exports, lists, layers...). Preloaded names: cadwork, ec (element_controller),
    gc (geometry_controller), ac (attribute_controller), vc (visualization_controller),
    uc (utility_controller), fc (file_controller), pt([x,y,z]) -> point_3d, xyz(point_3d) -> list, math.
    Assign to `result` to return a JSON-serialisable value; print() output is returned too.
    Tell the user what the code will do before running anything destructive."""
    return send_command("execute_python", {"code": code})


@mcp.tool()
def stop_bridge() -> str:
    """Stop the bridge plugin so the user gets the cadwork UI back. They can restart it from the plugin bar."""
    return send_command("stop")


def main():
    mcp.run()


if __name__ == "__main__":
    main()
