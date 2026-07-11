import nuke
from . import unified_panel
nuke.menu("Pane").addCommand("Crucible", unified_panel.LightMixerWidget)
