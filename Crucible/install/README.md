# Crucible Live Bridge — DCC Installation Guide

Each subfolder contains two scripts for that DCC:

| File | Purpose |
|------|---------|
| `crucible_live_server.py` | **Real-time Live Link** — socket server, keeps running, updates lights as you move sliders in Nuke |
| `crucible_json_importer.py` | **One-shot JSON import** — reads an exported `.json` and applies values once |

---

## Ports

| DCC | Live Link Port |
|-----|---------------|
| Houdini | **7890** |
| Maya | **7891** |
| Blender | **7892** |

Set the matching port in the Crucible panel (Live Link row) before connecting.

---

## Houdini (`install/houdini/`)

### Live Link (real-time)
1. Open Houdini with your Solaris/LOP scene.
2. **Shelf** → right-click any shelf → **New Tool**.
3. Name it `Crucible Live Link`.
4. In the **Script** tab, paste the entire contents of `crucible_live_server.py`.
5. Click **Accept**.
6. **Click the shelf button** → dialog confirms *"Crucible LiveBridge RUNNING on port 7890"*.
7. In Nuke → Crucible panel → Host: `localhost`, Port: `7890` → enable **Live Link: ON**.
8. Click the shelf button again to **stop**.

> Light matching is by node name — strip `c_`, `rgba_`, `lightgroup_` prefixes.  
> Fallback: checks `primpattern` leaf name (e.g. `/lights/sun_key` → matches `sun_key`).

### JSON Importer (one-shot)
1. In Nuke → Crucible panel → **Export JSON Bridge** → save your `.json`.
2. Create a shelf tool with `crucible_json_importer.py` and click it.
3. A file browser opens → select the `.json` → choose **Multiply** or **Overwrite** mode.

---

## Maya (`install/maya/`)

### Live Link (real-time)
1. Open Maya with your scene and render engine active (Arnold/V-Ray/Redshift).
2. Open **Script Editor** → Python tab.
3. Paste the entire contents of `crucible_live_server.py`.
4. Press **Ctrl+Enter** (or click Execute All).
5. An in-viewport message confirms *"Crucible Maya LiveBridge RUNNING on port 7891"*.
6. In Nuke → Crucible panel → Host: `localhost`, Port: `7891`, Engine: your renderer → **Live Link: ON**.
7. Run the script again to **stop**.

> **Shelf button (recommended):** highlight all code → **MMB-drag** to your shelf.  
> It toggles on/off every click.

Supported engine attribute mapping:

| Engine | Intensity attr | Color attr |
|--------|---------------|------------|
| Arnold | `aiExposure` (stops) | `color` |
| V-Ray | `intensityMult` | `lightColor` |
| Redshift | `multiplier` | `color` |
| Standard | `intensity` | `color` |

### JSON Importer (one-shot)
1. Export `.json` from Nuke → Crucible → **Export JSON Bridge**.
2. In Maya Script Editor → paste `crucible_json_importer.py` → execute.

---

## Blender (`install/blender/`)

### Live Link (real-time)
1. Open Blender with your scene (Cycles or Eevee).
2. Switch to the **Scripting** workspace.
3. Click **New** → paste the entire contents of `crucible_live_server.py`.
4. Click **▶ Run Script**.
5. Console confirms *"Crucible Blender LiveBridge RUNNING on port 7892"*.
6. In Nuke → Crucible panel → Host: `localhost`, Port: `7892`, Engine: Cycles/Eevee → **Live Link: ON**.
7. Run the script again to **stop**.

> Blender polls the socket queue every **50ms** via `bpy.app.timers` — safe for the main thread.

Supported engine mapping:

| Engine | Target |
|--------|--------|
| Cycles | Emission shader node → `Strength` + `Color` |
| Eevee | `light.energy` + `light.color` |

### JSON Importer (one-shot)
1. Export `.json` from Nuke → Crucible → **Export JSON Bridge**.
2. Scripting workspace → open `crucible_json_importer.py` → **▶ Run Script** → file browser opens.

---

## Light Name Matching

All servers use the same matching logic:

```
AOV layer name  →  strip prefix (c_, rgba_, lightgroup_)  →  compare against DCC light name (lowercase)
```

**Example:** AOV channel `c_sun_key` → stripped to `sun_key` → matches Houdini node named `sun_key` or Maya light shape `sun_keyShape`.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Live Link not connecting | Check firewall — port must be open. Confirm DCC server is running first, then enable Live Link in Nuke. |
| No lights updated | Light names don't match AOV names. Check DCC console for `[Crucible] Updated X lights` output. |
| Port already in use | Another process owns the port. Change the port in the script's `_PORT` variable and match it in Nuke's panel. |
| Houdini Karma lights not found | Ensure Solaris light nodes have a `primpattern` or that node names match AOV names. |
