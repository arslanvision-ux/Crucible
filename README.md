# Crucible Live Bridge & VFX Toolkit

![Crucible VFX Toolkit - Light Mixer](Crucible/screenshots/Screenshot1.png)

Professional Nuke VFX Toolkit for feature-film and episodic VFX compositing pipelines.

**📚 [Click Here to View the Walkthrough Tutorial PDF](Crucible/Crucible_Walkthrough_Tutorial.pdf)**

## Overview
Crucible is a unified PySide-based interface for Nuke that integrates advanced AOV compositing, real-time lighting sync with 3D DCCs, and rigorous Render Quality Control (QC). 

### Supported DCCs & Renderers
- **Host Application:** Foundry Nuke 14+
- **Supported 3D DCCs:** Autodesk Maya, SideFX Houdini, Blender
- **Supported Renderers:** Arnold, Redshift, Karma (Solaris), Cycles

## Core Features

- **Real-Time Light Mixer & AOV Builder:** Automatically detect light groups and generate a non-destructive Shuffle-Grade-Merge tree. Sculpt your lighting directly in Nuke with Intensity, Temperature, Tint, and Saturation controls.
- **Bidirectional DCC Live Bridge:** Adjust light sliders in Nuke and watch them update live in your Maya, Houdini, or Blender viewport via robust socket communication. Keyframe lighting changes instantly.
- **Live 3D Camera Pull:** Pull live 3D camera animations and scene geometry directly from your DCC into Nuke without relying on baked JSON files—instantly building a 3D projection rig.
- **Render QC & Diagnostics:** Validate your multi-channel EXRs before publishing. Run diagnostics for negative pixels, NaNs, metadata missing, bounding box errors, and perform Pre-Flight Farm Checks. Generate FML Review Slates and Contact Sheets instantly.
- **Advanced CG Utilities:** One-click operations to extract Cryptomattes, build Crypto-Grade networks, set up Optical Z-Defocus from depth passes, and organize massive EXR layers with the Smart AOV Wrangler.
- **Lens & FX Integration:** Generate production-standard matching networks such as Physical Z-Depth Fog, Unified LensMatch, Exponential Glow, Smart Light Wrap, Procedural Heat Distortion, and Camera Shake.
- **Pipeline Workflow Tools:** Integrated OCIO Color Space Auditor to prevent mismatch errors, one-click slap-comp generation, versioning tools, and CDL exporting for color round-tripping.
- **Universal Pass Manager:** Automatically analyze and standardize utility passes (Normals, Position, Cryptomatte) from Arnold, Karma, Cycles, or Redshift.

---

## Installation

### Nuke
1. Copy the `Crucible` folder into your `.nuke` directory.
   - *Windows:* `%USERPROFILE%\.nuke`
   - *Linux / macOS:* `~/.nuke`
2. In your `.nuke/init.py`, add the following line:
   ```python
   nuke.pluginAddPath('./Crucible')
   ```
3. Restart Nuke. The "Crucible" panel will be available in the pane menu.

*(Note: Windows users can simply run `install_nuke_windows.bat`, and macOS/Linux users can run `install_nuke_unix.sh` located in the root of this repository for an automated installation).*

### Houdini, Maya, Blender
Please see the [Crucible/install/README.md](Crucible/install/README.md) file inside the Crucible folder for instructions on installing the Live Bridge for your specific DCC.
