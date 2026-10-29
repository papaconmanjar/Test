# cadwork MCP connector

Lets Claude read and draw in your **cadwork 3D** model. You ask in plain language, for
example *"draw a 6 × 4 m floor with 120×240 joists every 625 mm"*, and Claude builds it
in cadwork.

It has two parts, and both run on **your own computer**:

| Part | What it is |
|---|---|
| **claude_bridge** | A cadwork plugin. It runs inside cadwork and carries out Claude's commands. |
| **cadwork_mcp_server.py** | The connector Claude Desktop starts. It passes Claude's requests to the plugin. |

```
Claude Desktop ──► cadwork_mcp_server.py ──► claude_bridge plugin (inside cadwork 3D)
```

Each person installs their own copy. The connector only talks to the cadwork on the same
computer.

**You need:** Windows, cadwork 3D with a license, and Claude Desktop (or Claude Code).
Setup takes about 15 minutes.

---

## Setup

### Step 1: Download the files

1. Download the ZIP:
   https://github.com/papaconmanjar/Test/archive/refs/heads/claude/cadwork-connector-zsm1ks.zip
   (or use the copy a teammate sent you).
2. Unzip it to a permanent place. Don't leave it in Downloads. This guide uses
   `C:\cadwork-mcp\`, so the files end up in `C:\cadwork-mcp\cadwork-mcp\`.

Inside you'll find the folders `cadwork_plugin`, `server` and `tests`.

### Step 2: Install the plugin in cadwork

1. Find cadwork's plugin folder. It is usually:
   ```
   C:\Users\Public\Documents\cadwork\userprofile_XX\3d\API.x64\
   ```
   `XX` is your cadwork version, e.g. `userprofile_30`. If you can't find it, open
   `C:\Users\Public\Documents\cadwork` in File Explorer and search for `API.x64`.
2. Copy the **whole `claude_bridge` folder** from `C:\cadwork-mcp\cadwork-mcp\cadwork_plugin\`
   into `API.x64`. You should end up with:
   ```
   ...\API.x64\claude_bridge\claude_bridge.py
   ```
   The folder and the file must both be called `claude_bridge`.
3. Restart cadwork 3D. **claude_bridge** now appears under **Window → User Plugins**.

### Step 3: Install Python

The connector needs its own Python, separate from the one inside cadwork.

1. Go to https://www.python.org/downloads/ and click the big yellow **Download Python 3.x**
   button. Any version from 3.10 up works.
2. Run the file you downloaded:
   - **Classic installer:** tick **"Add python.exe to PATH"** on the first screen, then
     click **Install Now**.
   - **Python install manager:** just accept the defaults.
3. Open a **new** PowerShell window and check:
   ```powershell
   python --version
   ```
   You should see something like `Python 3.15.2`. If the Microsoft Store opens instead,
   Python isn't on PATH yet. Close PowerShell, reopen it, and try again.

### Step 4: Install the connector

In PowerShell, run:

```powershell
cd C:\cadwork-mcp\cadwork-mcp\server
python -m pip install -r requirements.txt
```

It should end with a line like `Successfully installed ... mcp-...`.

> If you see a red error mentioning **Rust**, **cargo** or **"Failed building wheel"**, your
> Python is too new for one of the packages. Install Python 3.14 next to it
> (`py install 3.14`), then run `py -3.14 -m pip install -r requirements.txt` instead. Use
> the 3.14 path in step 5.

### Step 5: Connect it to Claude Desktop

1. Get the full path to your Python. You'll need it in a moment:
   ```powershell
   (Get-Command python).Source
   ```
   It prints something like `C:\Users\YOURNAME\AppData\Local\Programs\Python\Python315\python.exe`.

2. In Claude Desktop, go to **Settings → Developer → Edit Config** ("Editar configuración"
   in Spanish). This opens a **folder**, not the file. That's normal.

3. **Quit Claude Desktop completely:** right-click its icon in the tray near the clock →
   **Quit**. Claude Desktop saves its own settings into the config file and would
   overwrite your edit if it stayed open.

4. In that folder, right-click `claude_desktop_config.json` → **Open with → Notepad**.

5. The file probably already has content, starting with `{` and a line like
   `"coworkUserFilesPath": ...`. **Don't replace it.** Put your cursor at the end of the
   very first line (`{`), press **Enter**, and paste this block. Use your own Python path
   from step 1, and write every `\` as `\\`:
   ```json
     "mcpServers": {
       "cadwork": {
         "command": "C:\\Users\\YOURNAME\\AppData\\Local\\Programs\\Python\\Python315\\python.exe",
         "args": ["C:\\cadwork-mcp\\cadwork-mcp\\server\\cadwork_mcp_server.py"]
       }
     },
   ```
   Keep the comma after the last `}`. The top of the file should now look like this:
   ```json
   {
     "mcpServers": {
       "cadwork": {
         "command": "C:\\Users\\YOURNAME\\...\\python.exe",
         "args": ["C:\\cadwork-mcp\\cadwork-mcp\\server\\cadwork_mcp_server.py"]
       }
     },
     "coworkUserFilesPath": "...",
     ...everything else unchanged...
   ```
   - If the file already has an `"mcpServers"` section, for example for AutoCAD, add only
     the `"cadwork": { ... }` entry inside it, with a comma after the entry before it.
   - If the file doesn't exist, create it in Notepad with this content, then **Save As** with
     **Save as type: All files (\*.\*)** and the exact name `claude_desktop_config.json`:
     ```json
     {
       "mcpServers": {
         "cadwork": {
           "command": "C:\\Users\\YOURNAME\\...\\python.exe",
           "args": ["C:\\cadwork-mcp\\cadwork-mcp\\server\\cadwork_mcp_server.py"]
         }
       }
     }
     ```

6. Save (**Ctrl+S**) and open Claude Desktop again.

7. Check it worked: in **Settings → Developer**, **cadwork** should be listed as
   **Running** ("En ejecución").

<details>
<summary>Using Claude Code instead of Claude Desktop</summary>

```powershell
claude mcp add cadwork -- "C:\Users\YOURNAME\...\python.exe" "C:\cadwork-mcp\cadwork-mcp\server\cadwork_mcp_server.py"
claude mcp list
```

</details>

### Step 6: First test

1. Open cadwork 3D with a **new, empty test model**. Don't use a real project for the first
   test.
2. Go to **Window → User Plugins** and click **claude_bridge**. **cadwork will look frozen. That's expected**
   (see below).
3. In Claude Desktop, start a new chat and send:
   > Check the cadwork status, then draw one 100×200 mm beam, 3 m long, from the origin along X. Then stop the bridge.
4. Allow the cadwork tools when Claude asks for permission.
5. cadwork unfreezes and the beam is in the model.

---

## Daily use

1. Open your model in cadwork.
2. Go to **Window → User Plugins** and click **claude_bridge**.
3. Ask Claude what you need, for example:
   - *"List the beams in the model with their sizes."*
   - *"Draw a 6 × 4 m floor frame: 120×240 C24 joists at 625 mm spacing, group House, subgroup Ground floor."*
   - *"Copy the selected rafters 2 m along X."*
   - *"Set the material of all elements in subgroup Roof to C24."*
4. When you want to work in cadwork yourself, ask Claude to **"stop the bridge"**.

### Why cadwork freezes

cadwork only allows its Python to run one thing at a time, on its own thread. While the
plugin is waiting for Claude, cadwork's screen is busy and you can't click in it. That's
normal. To get control back:

- ask Claude to **stop the bridge**, or
- wait: the plugin stops by itself after **30 minutes** without requests.

Click **claude_bridge** again (Window → User Plugins) to reconnect.

Tips:
- Everything is in **millimetres**. Points are `[x, y, z]`.
- **"Selected"** means the elements you had selected in cadwork when you started the
  plugin.
- Save your model before asking for big changes.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Claude says *"Cannot reach the cadwork bridge"* | The plugin isn't running. Click **claude_bridge** in cadwork, then ask again. |
| **claude_bridge** isn't under Window → User Plugins | Check that the path is exactly `...\API.x64\claude_bridge\claude_bridge.py`, then restart cadwork. |
| **cadwork** isn't listed in Claude's Settings → Developer | The config file has a typo. Check the commas and that every `\` is written `\\`. Quit Claude Desktop fully and reopen it. |
| cadwork is listed but shows as **failed** | Click **View logs** ("Ver registros") and check the Python path. Running `(Get-Command python).Source` again shows the right one. |
| My edit to the config file disappeared | Claude Desktop was still open and overwrote it. Quit it from the tray icon, edit, save, then reopen it. |
| A tool fails with an error about a missing cadwork function | Function names differ a little between cadwork versions. Claude can usually work around it by itself (it can look up your version's functions). Please report the error so the plugin can be fixed. |
| cadwork stays frozen | Ask Claude to *stop the bridge*. If Claude is closed, wait up to 30 minutes, or close cadwork from Task Manager. **Save often.** |

---

## What Claude can do

| Tool | Purpose |
|---|---|
| `cadwork_status` | Connection check: cadwork version, open file, element count |
| `list_elements` | Elements in the model: all, the current selection, or visible ones |
| `get_element_info` | Name, group, subgroup, material, colour, dimensions, volume, points |
| `create_beam`, `create_circular_beam`, `create_panel`, `create_line`, `create_node` | Create geometry, optionally with name, group, subgroup, material and colour |
| `move_elements`, `copy_elements`, `rotate_elements`, `delete_elements` | Edit geometry |
| `set_attributes`, `set_visibility` | Change name, group, subgroup, material, comment, colour; show or hide |
| `list_api_functions` | Looks up the cadwork Python functions in **your** installed version |
| `execute_python` | Runs Python inside cadwork, for anything else (processing, exports, lists...) |
| `stop_bridge` | Stops the plugin and unfreezes cadwork |

A beam runs from `p1` to `p2`. The optional `p3` sets which way its height points. By
default that's up (global Z) for horizontal members and global Y for vertical ones.

## Settings (optional)

Set these as Windows environment variables. For the plugin, set them before starting cadwork.

| Variable | Default | Used by | Meaning |
|---|---|---|---|
| `CADWORK_MCP_PORT` | `53002` | both | Port the plugin listens on |
| `CADWORK_MCP_IDLE_TIMEOUT` | `1800` | plugin | Seconds without requests before the plugin stops |
| `CADWORK_MCP_ALLOW_PYTHON` | `1` | plugin | Set to `0` to turn off `execute_python` |
| `CADWORK_MCP_HOST` | `127.0.0.1` | connector | Where the plugin is |
| `CADWORK_MCP_TIMEOUT` | `120` | connector | Seconds to wait for each command |

## Security

The plugin only accepts connections from your own computer (`127.0.0.1`). `execute_python`
can run any code inside cadwork with your Windows user's rights. Set
`CADWORK_MCP_ALLOW_PYTHON=0` if you don't want that.

## Updating

Download the new ZIP and unzip it over `C:\cadwork-mcp\`. Copy the new `claude_bridge`
folder into `API.x64` again, then restart cadwork and Claude Desktop.

## For developers

```bash
pip install -r server/requirements.txt pytest
python -m pytest tests/
```

The tests replace cadwork's modules with in-memory stand-ins. They run the real connector
against the real plugin over a local connection, so they work without cadwork.
