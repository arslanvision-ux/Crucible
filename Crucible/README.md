# Crucible Live Bridge & VFX Toolkit

Professional Nuke VFX Toolkit for feature-film and episodic VFX compositing pipelines.

## Installation

### Nuke
1. Copy the `Crucible` folder into your `.nuke` directory.
2. In your `.nuke/init.py`, add the following line:
   ```python
   import os
   nuke.pluginAddPath(os.path.join(os.path.expanduser('~'), '.nuke', 'Crucible').replace('\', '/'))
   ```
3. Restart Nuke. The "Crucible" panel will be available in the pane menu and the top Nuke shelf menu.

### Houdini, Maya, Blender
Please see the `install/README.md` file for instructions on installing the Live Bridge for your specific DCC.
