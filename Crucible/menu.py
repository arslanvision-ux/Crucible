import nuke
import os
import sys

parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from Crucible import unified_panel
try:
    unified_panel.register_unified_panel()
except Exception as e:
    nuke.tprint("[Crucible] Failed to register panel: " + str(e))

import nukescripts
toolbar = nuke.menu("Nodes")
crucible_nodes = toolbar.addMenu("Crucible", icon="Render.png")
crucible_nodes.addCommand("Open Crucible Panel", "nukescripts.panels.restorePanel('com.crucible.unified')")

main_menu = nuke.menu("Nuke")
crucible_main = main_menu.addMenu("Crucible")
crucible_main.addCommand("Open Crucible Panel", "nukescripts.panels.restorePanel('com.crucible.unified')")
