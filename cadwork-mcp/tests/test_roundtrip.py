"""End-to-end test: MCP server tools -> TCP -> bridge plugin, with cadwork's
Python modules replaced by in-memory stubs. Run: python -m pytest tests/
"""

import importlib.util
import os
import socket
import sys
import threading
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


class Point3d:
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.x, self.y, self.z = x, y, z


def _install_stubs():
    model = {"elements": {}, "next": 1}

    def new(kind, **geo):
        eid = model["next"]
        model["next"] += 1
        model["elements"][eid] = {"kind": kind, "attrs": {}, "color": 1, **geo}
        return eid

    cadwork = types.ModuleType("cadwork")
    cadwork.point_3d = Point3d

    ec = types.ModuleType("element_controller")
    ec.create_rectangular_beam_points = lambda w, h, p1, p2, p3: new("beam", width=w, height=h, p1=p1, p2=p2, p3=p3)
    ec.create_circular_beam_points = lambda d, p1, p2, p3: new("round", width=d, height=d, p1=p1, p2=p2, p3=p3)
    ec.create_rectangular_panel_points = lambda w, t, p1, p2, p3: new("panel", width=w, height=t, p1=p1, p2=p2, p3=p3)
    ec.create_line_points = lambda p1, p2: new("line", p1=p1, p2=p2)
    ec.create_node = lambda p: new("node", p1=p)
    ec.get_all_identifiable_element_ids = lambda: list(model["elements"])
    ec.get_active_identifiable_element_ids = lambda: []
    ec.get_visible_identifiable_element_ids = lambda: list(model["elements"])

    def delete(ids):
        for i in ids:
            model["elements"].pop(i)
    ec.delete_elements = delete

    def move(ids, v):
        for i in ids:
            e = model["elements"][i]
            for k in ("p1", "p2"):
                if k in e:
                    e[k] = Point3d(e[k].x + v.x, e[k].y + v.y, e[k].z + v.z)
    ec.move_element = move

    def copy(ids, v):
        out = []
        for i in ids:
            e = dict(model["elements"][i])
            nid = new(e.pop("kind"), **{k: e[k] for k in ("p1", "p2") if k in e})
            move([nid], v)
            out.append(nid)
        return out
    ec.copy_elements = copy
    ec.rotate_elements = lambda ids, o, a, ang: None

    gc = types.ModuleType("geometry_controller")
    gc.get_p1 = lambda i: model["elements"][i]["p1"]
    gc.get_p2 = lambda i: model["elements"][i]["p2"]
    gc.get_p3 = lambda i: model["elements"][i]["p3"]
    gc.get_width = lambda i: model["elements"][i]["width"]
    gc.get_height = lambda i: model["elements"][i]["height"]

    def length(i):
        e = model["elements"][i]
        return ((e["p2"].x - e["p1"].x) ** 2 + (e["p2"].y - e["p1"].y) ** 2 + (e["p2"].z - e["p1"].z) ** 2) ** 0.5
    gc.get_length = length
    gc.get_volume = lambda i: length(i) * gc.get_width(i) * gc.get_height(i)

    ac = types.ModuleType("attribute_controller")
    for attr in ("name", "group", "subgroup", "comment", "material"):
        def setter(ids, value, attr=attr):
            for i in ids:
                model["elements"][i]["attrs"][attr] = value
        setattr(ac, "set_" + attr, setter)
    for attr in ("name", "group", "subgroup", "comment"):
        setattr(ac, "get_" + attr, lambda i, attr=attr: model["elements"][i]["attrs"].get(attr, ""))
    ac.get_element_material_name = lambda i: model["elements"][i]["attrs"].get("material", "")

    vc = types.ModuleType("visualization_controller")
    vc.refresh = lambda: None
    vc.get_color = lambda i: model["elements"][i]["color"]

    def set_color(ids, c):
        for i in ids:
            model["elements"][i]["color"] = c
    vc.set_color = set_color
    vc.set_visible = vc.set_invisible = lambda ids: None

    uc = types.ModuleType("utility_controller")
    uc.get_3d_file_path = lambda: "C:/projects/test.3d"
    uc.print_message = lambda *a: None

    for mod in (cadwork, ec, gc, ac, vc, uc):
        sys.modules[mod.__name__] = mod
    return model


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def env(monkeypatch):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    monkeypatch.setenv("CADWORK_MCP_PORT", str(port))
    monkeypatch.setenv("CADWORK_BRIDGE_NO_AUTOSTART", "1")
    model = _install_stubs()
    bridge_mod = _load("claude_bridge", ROOT / "cadwork_plugin/claude_bridge/claude_bridge.py")
    server = _load("cadwork_mcp_server", ROOT / "server/cadwork_mcp_server.py")

    bridge = bridge_mod.Bridge(port=port)
    thread = threading.Thread(target=bridge.serve, daemon=True)
    thread.start()
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.1).close()
            break
        except OSError:
            threading.Event().wait(0.02)
    yield server, model
    if bridge.running:
        server.stop_bridge()
    thread.join(timeout=3)


def test_status(env):
    server, _ = env
    status = server.cadwork_status()
    assert status["status"] == "ok"
    assert status["file"] == "C:/projects/test.3d"


def test_create_and_query_beam(env):
    server, model = env
    beam = server.create_beam(100, 200, [0, 0, 0], [3000, 0, 0], name="Rafter", group="House", material="C24", color=5)
    info = server.get_element_info([beam["id"]])[0]
    assert info["name"] == "Rafter"
    assert info["material"] == "C24"
    assert info["color"] == 5
    assert info["length"] == 3000
    assert info["p3"] == [0, 0, 1]  # default height direction for a horizontal beam
    post = server.create_beam(160, 160, [0, 0, 0], [0, 0, 2500])
    assert server.get_element_info([post["id"]])[0]["p3"] == [0, 1, 0]


def test_edit_operations(env):
    server, model = env
    a = server.create_panel(1250, 18, [0, 0, 0], [2500, 0, 0])["id"]
    copies = server.copy_elements([a], [0, 0, 100])["new_ids"]
    assert server.get_element_info(copies)[0]["p1"] == [0, 0, 100]
    server.move_elements([a], [10, 0, 0])
    assert server.get_element_info([a])[0]["p1"] == [10, 0, 0]
    server.set_attributes([a], subgroup="Roof")
    assert server.list_elements()["total"] == 2
    server.delete_elements(copies)
    assert server.list_elements(detailed=True)["elements"][0]["subgroup"] == "Roof"


def test_execute_python_and_api_listing(env):
    server, _ = env
    out = server.execute_python("ids = [ec.create_node(pt([i*100, 0, 0])) for i in range(3)]\nprint('made', len(ids))\nresult = ids")
    assert out["result"] == [1, 2, 3]
    assert out["stdout"].strip() == "made 3"
    names = [f["name"] for f in server.list_api_functions("element_controller", filter="beam")]
    assert "create_rectangular_beam_points" in names


def test_errors_are_reported(env):
    server, _ = env
    with pytest.raises(server.BridgeError, match="ZeroDivisionError"):
        server.execute_python("result = 1 / 0")
