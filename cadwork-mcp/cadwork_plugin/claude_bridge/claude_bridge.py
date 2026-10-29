"""Claude bridge plugin for cadwork 3D.

Runs inside cadwork's embedded Python. When started from the cadwork plugin
bar it opens a TCP socket on 127.0.0.1 and executes JSON commands sent by the
cadwork MCP server (server/cadwork_mcp_server.py), which in turn is driven by
Claude.

Protocol: one JSON object per line.
    request:  {"id": 1, "command": "create_beam", "params": {...}}
    response: {"id": 1, "ok": true, "result": ...}
              {"id": 1, "ok": false, "error": "...", "traceback": "..."}

The cadwork API is not thread-safe, so commands are executed on cadwork's own
(main) thread. That means the cadwork UI is busy while the bridge is running.
Stop it with the `stop_bridge` tool, or let it time out after IDLE_TIMEOUT_S
seconds without any request.

All lengths are in millimetres, angles passed to the bridge in degrees.
"""

import contextlib
import io
import json
import math
import os
import socket
import time
import traceback

HOST = "127.0.0.1"
PORT = int(os.environ.get("CADWORK_MCP_PORT", "53002"))
# Stop the bridge (and give the UI back) after this many seconds with no request.
IDLE_TIMEOUT_S = float(os.environ.get("CADWORK_MCP_IDLE_TIMEOUT", "1800"))
# Set to "0" to refuse the execute_python command.
ALLOW_EXECUTE_PYTHON = os.environ.get("CADWORK_MCP_ALLOW_PYTHON", "1") != "0"
MAX_LIST = 5000

import cadwork  # noqa: E402
import element_controller as ec  # noqa: E402
import geometry_controller as gc  # noqa: E402
import attribute_controller as ac  # noqa: E402
import visualization_controller as vc  # noqa: E402
import utility_controller as uc  # noqa: E402

try:
    import file_controller as fc  # noqa: E402
except ImportError:  # older cadwork versions
    fc = None


# ---------------------------------------------------------------- helpers

def _pt(v):
    """[x, y, z] -> cadwork.point_3d"""
    if v is None:
        return None
    x, y, z = (float(c) for c in v)
    return cadwork.point_3d(x, y, z)


def _xyz(p):
    """cadwork.point_3d -> [x, y, z]"""
    if p is None:
        return None
    return [round(p.x, 4), round(p.y, 4), round(p.z, 4)]


def _ids(v):
    if isinstance(v, int):
        return [v]
    return [int(i) for i in v]


def _try(fn, *args):
    try:
        return fn(*args)
    except Exception:
        return None


def _first_available(module, names, *args):
    """Call the first function from `names` that exists on `module`."""
    for name in names:
        fn = getattr(module, name, None)
        if fn is not None:
            return _try(fn, *args)
    return None


def _default_p3(p1, p2):
    """Point that sets the height (zl) direction of a member.

    Horizontal-ish members get their height along global Z; vertical members
    along global Y.
    """
    d = [p2[i] - p1[i] for i in range(3)]
    length = math.sqrt(sum(c * c for c in d)) or 1.0
    if abs(d[2]) / length > 0.99:
        return [p1[0], p1[1] + 1.0, p1[2]]
    return [p1[0], p1[1], p1[2] + 1.0]


def _refresh():
    _try(vc.refresh)


def _apply_common(ids, params):
    """Optional attributes shared by all create_* commands."""
    if params.get("name") is not None:
        ac.set_name(ids, str(params["name"]))
    if params.get("group") is not None:
        ac.set_group(ids, str(params["group"]))
    if params.get("subgroup") is not None:
        ac.set_subgroup(ids, str(params["subgroup"]))
    if params.get("comment") is not None:
        ac.set_comment(ids, str(params["comment"]))
    if params.get("material") is not None:
        ac.set_material(ids, str(params["material"]))
    if params.get("color") is not None:
        vc.set_color(ids, int(params["color"]))


def _element_info(eid):
    info = {
        "id": eid,
        "type": _first_available(ac, ["get_element_type_description"], eid),
        "name": _try(ac.get_name, eid),
        "group": _try(ac.get_group, eid),
        "subgroup": _try(ac.get_subgroup, eid),
        "comment": _try(ac.get_comment, eid),
        "material": _first_available(ac, ["get_element_material_name", "get_material"], eid),
        "color": _try(vc.get_color, eid),
        "length": _try(gc.get_length, eid),
        "width": _try(gc.get_width, eid),
        "height": _try(gc.get_height, eid),
        "volume": _try(gc.get_volume, eid),
        "p1": _xyz(_try(gc.get_p1, eid)),
        "p2": _xyz(_try(gc.get_p2, eid)),
        "p3": _xyz(_try(gc.get_p3, eid)),
    }
    if info["type"] is not None and not isinstance(info["type"], (str, int, float)):
        info["type"] = str(info["type"])
    return info


# --------------------------------------------------------------- commands

def cmd_ping(params):
    return {
        "status": "ok",
        "cadwork_version": _first_available(uc, ["get_cadwork_version", "get_3d_version"]),
        "file": _first_available(uc, ["get_3d_file_path"]),
        "element_count": len(ec.get_all_identifiable_element_ids()),
        "python_execution_allowed": ALLOW_EXECUTE_PYTHON,
    }


def cmd_list_elements(params):
    scope = params.get("scope", "all")
    if scope == "active":
        ids = ec.get_active_identifiable_element_ids()
    elif scope == "visible":
        ids = ec.get_visible_identifiable_element_ids()
    else:
        ids = ec.get_all_identifiable_element_ids()
    ids = list(ids)
    limit = min(int(params.get("limit", 200)), MAX_LIST)
    detailed = bool(params.get("detailed", False))
    shown = ids[:limit]
    if detailed:
        items = [_element_info(i) for i in shown]
    else:
        items = [
            {"id": i, "name": _try(ac.get_name, i), "group": _try(ac.get_group, i),
             "subgroup": _try(ac.get_subgroup, i)}
            for i in shown
        ]
    return {"total": len(ids), "returned": len(items), "elements": items}


def cmd_get_element_info(params):
    return [_element_info(i) for i in _ids(params["ids"])]


def cmd_create_beam(params):
    p1, p2 = params["p1"], params["p2"]
    p3 = params.get("p3") or _default_p3(p1, p2)
    eid = ec.create_rectangular_beam_points(
        float(params["width"]), float(params["height"]), _pt(p1), _pt(p2), _pt(p3))
    _apply_common([eid], params)
    _refresh()
    return {"id": eid}


def cmd_create_circular_beam(params):
    p1, p2 = params["p1"], params["p2"]
    p3 = params.get("p3") or _default_p3(p1, p2)
    eid = ec.create_circular_beam_points(
        float(params["diameter"]), _pt(p1), _pt(p2), _pt(p3))
    _apply_common([eid], params)
    _refresh()
    return {"id": eid}


def cmd_create_panel(params):
    p1, p2 = params["p1"], params["p2"]
    p3 = params.get("p3") or _default_p3(p1, p2)
    eid = ec.create_rectangular_panel_points(
        float(params["width"]), float(params["thickness"]), _pt(p1), _pt(p2), _pt(p3))
    _apply_common([eid], params)
    _refresh()
    return {"id": eid}


def cmd_create_line(params):
    eid = ec.create_line_points(_pt(params["p1"]), _pt(params["p2"]))
    _apply_common([eid], params)
    _refresh()
    return {"id": eid}


def cmd_create_node(params):
    eid = ec.create_node(_pt(params["point"]))
    _apply_common([eid], params)
    _refresh()
    return {"id": eid}


def cmd_delete_elements(params):
    ids = _ids(params["ids"])
    ec.delete_elements(ids)
    _refresh()
    return {"deleted": len(ids)}


def cmd_move_elements(params):
    ids = _ids(params["ids"])
    ec.move_element(ids, _pt(params["vector"]))
    _refresh()
    return {"moved": len(ids)}


def cmd_copy_elements(params):
    ids = _ids(params["ids"])
    new_ids = ec.copy_elements(ids, _pt(params["vector"]))
    _refresh()
    return {"new_ids": list(new_ids) if new_ids is not None else None}


def cmd_rotate_elements(params):
    ids = _ids(params["ids"])
    angle = math.radians(float(params["angle_deg"]))
    ec.rotate_elements(ids, _pt(params["origin"]), _pt(params.get("axis", [0, 0, 1])), angle)
    _refresh()
    return {"rotated": len(ids)}


def cmd_set_attributes(params):
    ids = _ids(params["ids"])
    _apply_common(ids, params)
    _refresh()
    return {"updated": len(ids)}


def cmd_set_visibility(params):
    ids = _ids(params["ids"])
    if params.get("visible", True):
        vc.set_visible(ids)
    else:
        vc.set_invisible(ids)
    _refresh()
    return {"updated": len(ids)}


def cmd_list_api_functions(params):
    modules = {
        "cadwork": cadwork, "element_controller": ec, "geometry_controller": gc,
        "attribute_controller": ac, "visualization_controller": vc,
        "utility_controller": uc, "file_controller": fc,
    }
    name = params.get("module", "element_controller")
    if name in modules and modules[name] is not None:
        mod = modules[name]
    else:
        mod = __import__(name)
    filt = (params.get("filter") or "").lower()
    out = []
    for attr in sorted(dir(mod)):
        if attr.startswith("_") or (filt and filt not in attr.lower()):
            continue
        doc = (getattr(getattr(mod, attr), "__doc__", None) or "").strip()
        out.append({"name": attr, "doc": doc[:400]})
    return out


def cmd_execute_python(params):
    """Run arbitrary Python inside cadwork. Assign to `result` to return a value."""
    if not ALLOW_EXECUTE_PYTHON:
        raise PermissionError("execute_python is disabled (CADWORK_MCP_ALLOW_PYTHON=0)")
    ns = {
        "cadwork": cadwork, "ec": ec, "gc": gc, "ac": ac, "vc": vc, "uc": uc, "fc": fc,
        "element_controller": ec, "geometry_controller": gc, "attribute_controller": ac,
        "visualization_controller": vc, "utility_controller": uc, "file_controller": fc,
        "pt": _pt, "xyz": _xyz, "math": math, "result": None,
    }
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        exec(params["code"], ns)
    _refresh()
    res = ns.get("result")
    try:
        json.dumps(res)
    except (TypeError, ValueError):
        res = repr(res)
    return {"result": res, "stdout": buf.getvalue()[-20000:]}


COMMANDS = {
    name[len("cmd_"):]: fn for name, fn in globals().items() if name.startswith("cmd_")
}


# ----------------------------------------------------------------- server

class Bridge:
    def __init__(self, host=HOST, port=PORT, idle_timeout=IDLE_TIMEOUT_S):
        self.host = host
        self.port = port
        self.idle_timeout = idle_timeout
        self.running = False

    def handle(self, request):
        rid = request.get("id")
        command = request.get("command")
        if command == "stop":
            self.running = False
            return {"id": rid, "ok": True, "result": "bridge stopping"}
        fn = COMMANDS.get(command)
        if fn is None:
            return {"id": rid, "ok": False, "error": "unknown command: %s" % command}
        try:
            return {"id": rid, "ok": True, "result": fn(request.get("params") or {})}
        except Exception as exc:
            return {"id": rid, "ok": False, "error": "%s: %s" % (type(exc).__name__, exc),
                    "traceback": traceback.format_exc()[-4000:]}

    def _serve_connection(self, conn):
        conn.settimeout(0.5)
        buf = b""
        last = time.time()
        while self.running:
            try:
                chunk = conn.recv(65536)
            except socket.timeout:
                if time.time() - last > 60:  # client went quiet; free the slot
                    return
                continue
            if not chunk:
                return
            last = time.time()
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if not line.strip():
                    continue
                try:
                    request = json.loads(line.decode("utf-8"))
                    response = self.handle(request)
                except ValueError as exc:
                    response = {"id": None, "ok": False, "error": "bad JSON: %s" % exc}
                conn.sendall((json.dumps(response) + "\n").encode("utf-8"))
                self.last_activity = time.time()

    def serve(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((self.host, self.port))
        srv.listen(1)
        srv.settimeout(0.5)
        self.running = True
        self.last_activity = time.time()
        _message("Claude bridge listening on %s:%d" % (self.host, self.port))
        try:
            while self.running:
                if self.idle_timeout and time.time() - self.last_activity > self.idle_timeout:
                    _message("Claude bridge idle timeout")
                    break
                try:
                    conn, _ = srv.accept()
                except socket.timeout:
                    continue
                with conn:
                    self._serve_connection(conn)
        finally:
            srv.close()
            self.running = False
            _message("Claude bridge stopped")


def _message(text):
    print(text)
    _try(uc.print_message, text, 1, 1)


def main():
    Bridge().serve()


if os.environ.get("CADWORK_BRIDGE_NO_AUTOSTART") != "1":
    main()
