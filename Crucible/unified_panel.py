"""
Crucible — Unified Professional Panel.

Provides a unified, PySide-based interface for all Crucible tools
(AOV Builder, Light Mixer, Render QC) in a single dockable panel with tabs.
"""

import os
import sys
import nuke
import nukescripts

# Attempt to import PySide6 or PySide2 depending on Nuke version
try:
    if nuke.NUKE_VERSION_MAJOR >= 15:
        from PySide6 import QtWidgets, QtCore, QtGui
    else:
        from PySide2 import QtWidgets, QtCore, QtGui
except Exception:
    # Fallback to the other if the primary fails (e.g. NumPy version mismatch)
    try:
        if nuke.NUKE_VERSION_MAJOR >= 15:
            from PySide2 import QtWidgets, QtCore, QtGui
        else:
            from PySide6 import QtWidgets, QtCore, QtGui
    except Exception:
        pass

from .constants import UI_COLORS, LIGHT_MIXER_MIN, LIGHT_MIXER_MAX, LIGHT_MIXER_DEFAULT
from .aov_builder.channel_parser import parse_channels
from .aov_builder.tree_builder import build_aov_tree
from .render_qc.diagnostics import run_diagnostics, SeverityLevel
from .render_qc.contact_sheet_builder import generate_aov_contact_sheet, generate_fml_review_slate
from .render_qc.preflight_checker import run_preflight_check
from .cg_tools import extract_cryptomattes, setup_zdefocus, rebuild_beauty, create_crypto_grade, smart_aov_wrangler
from .nuke_utils import get_selected_source_node
from . import integration_tools
from . import fx_lighting_tools
from .pipeline_tools import check_color_spaces, change_version, build_slap_comp, export_cdl_from_node, launch_scopes
from .deep_tools import create_deep_matte, create_deep_holdout, create_deep_edge_fix, create_2d_to_deep_rig, create_deep_slap_comp, create_deep_memory_inspector
from .bridge_tools import export_lightmix_json, generate_bridge_scripts
from .live_bridge import (
    NukeLiveSender, NukeLiveListener,
    LIVE_BRIDGE_DEFAULT_PORT, LIVE_BRIDGE_LISTEN_PORT,
)
from .live_bridge_protocol import (
    LIVE_BRIDGE_PORTS,
    MSG_CAMERA_FRAME, MSG_CAMERA_SEQUENCE, MSG_SCENE_INFO, MSG_PONG, MSG_ERROR,
)
from .aov_builder.pass_manager import PassManager, BUILT_IN_SCHEMAS, PassStatus
from .dcc_bridges.camera_exchange import import_camera_from_json, import_scene_from_json, diff_render_settings


# ---------------------------------------------------------------------------
# UI Helpers & Styling
# ---------------------------------------------------------------------------

CRUCIBLE_STYLESHEET = """
    QWidget {
        background-color: #1e1e1e;
        color: #e0e0e0;
        font-family: "Segoe UI", "Inter", "Open Sans", sans-serif;
        font-size: 10pt;
    }
    QTabWidget::pane {
        border: 1px solid #333333;
        background-color: #252526;
        border-radius: 6px;
        margin-top: -1px;
    }
    QTabBar::tab {
        background-color: #2d2d30;
        color: #999999;
        padding: 8px 20px;
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
        border: 1px solid #333333;
        border-bottom: none;
        margin-right: 2px;
        font-weight: 500;
    }
    QTabBar::tab:selected {
        background-color: #252526;
        color: #ffffff;
        border-top: 2px solid #f2a822;
    }
    QTabBar::tab:hover:!selected {
        background-color: #3e3e42;
        color: #dfdfdf;
    }
    QPushButton {
        background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3e3e42, stop:1 #2d2d30);
        color: #ffffff;
        border: 1px solid #4a4a4c;
        padding: 6px 10px;
        border-radius: 4px;
        font-weight: 500;
    }
    QPushButton[square="true"] {
        padding: 2px 4px;
        font-weight: bold;
        font-size: 11pt;
    }
    QPushButton[solo="true"]:checked {
        background-color: #f1c40f;
        color: black;
    }
    QPushButton[mute="true"]:checked {
        background-color: #e74c3c;
        color: white;
    }
    QPushButton:hover {
        background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #4e4e52, stop:1 #3d3d40);
        border: 1px solid #5a5a5c;
    }
    QPushButton:pressed {
        background-color: #1e1e1e;
        border: 1px solid #f2a822;
    }
    QPushButton[primary="true"] {
        background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #f2a822, stop:1 #d89115);
        border: 1px solid #ffb732;
        font-weight: bold;
    }
    QPushButton[primary="true"]:hover {
        background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffb732, stop:1 #efa120);
    }
    QPushButton[primary="true"]:pressed {
        background-color: #bd7f11;
    }
    QSlider::groove:horizontal {
        border: 1px solid #1a1a1a;
        height: 6px;
        background: #111111;
        border-radius: 3px;
    }
    QSlider::sub-page:horizontal {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #b37400, stop:1 #f2a822);
        border-radius: 3px;
    }
    QSlider::handle:horizontal {
        background: #ffffff;
        border: 1px solid #555555;
        width: 14px;
        margin-top: -5px;
        margin-bottom: -5px;
        border-radius: 7px;
    }
    QSlider::handle:horizontal:hover {
        background: #f2a822;
        border: 1px solid #ffb732;
    }
    QGroupBox {
        border: 1px solid #3a3a3a;
        border-radius: 6px;
        margin-top: 14px;
        background-color: #2a2a2b;
        font-weight: bold;
        color: #b0b0b0;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 14px;
        padding: 0 4px;
        color: #f2a822;
    }
    QScrollArea {
        border: 1px solid #333333;
        border-radius: 6px;
        background-color: #1e1e1e;
    }
    QScrollBar:vertical {
        border: none;
        background: #1e1e1e;
        width: 12px;
        margin: 2px;
    }
    QScrollBar::handle:vertical {
        background: #4a4a4c;
        min-height: 20px;
        border-radius: 4px;
    }
    QScrollBar::handle:vertical:hover {
        background: #5a5a5c;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
    }
    QLabel[header="true"] {
        font-size: 15pt;
        font-weight: 600;
        color: #ffffff;
        letter-spacing: 1px;
    }
    QTableWidget {
        background-color: #252526;
        alternate-background-color: #2a2a2b;
        color: #dcdcdc;
        gridline-color: #3a3a3a;
        border: none;
        border-radius: 4px;
        selection-background-color: #f2a822;
    }
    QHeaderView::section {
        background-color: #1e1e1e;
        color: #a0a0a0;
        padding: 6px;
        border: 1px solid #333333;
        font-weight: bold;
        border-top: none;
    }
    QTableCornerButton::section {
        background-color: #1e1e1e;
        border: 1px solid #333333;
    }
"""


# ---------------------------------------------------------------------------
# Light Mixer Tab
# ---------------------------------------------------------------------------

class LightMixerWidget(QtWidgets.QWidget):
    """The Light Mixer UI component."""

    def __init__(self, parent=None):
        super(LightMixerWidget, self).__init__(parent)
        self._grade_nodes = {}
        self._sliders = {}
        self._intensity_spins = {}
        self._temp_sliders = {}
        self._tint_sliders = {}
        self._sat_sliders = {}
        self._color_btns = {}
        self._solo_btns = {}
        self._mute_btns = {}
        self._active_solo = None
        # Snapshot system
        self._snapshots = {}
        # Live Bridge
        self._live_sender = NukeLiveSender()
        self._live_timer = QtCore.QTimer(self)
        self._live_timer.setSingleShot(True)
        self._live_timer.setInterval(80)   # 80 ms debounce
        self._live_timer.timeout.connect(self._broadcast_live_state)
        # Heartbeat
        self._heartbeat_timer = QtCore.QTimer(self)
        self._heartbeat_timer.setInterval(3000)
        self._heartbeat_timer.timeout.connect(self._check_live_health)
        self._heartbeat_timer.start()

        self._setup_ui()
        nuke.addUpdateUI(self._sync_ui_to_nodes)

    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Header
        header = QtWidgets.QLabel("AOV Builder & Light Mixer")
        header.setProperty("header", True)
        layout.addWidget(header)

        info_lbl = QtWidgets.QLabel("Select a node with multi-pass CG render data and click Build.")
        info_lbl.setWordWrap(True)
        layout.addWidget(info_lbl)

        # Main Controls
        control_layout = QtWidgets.QHBoxLayout()
        
        self.prefix_combo = QtWidgets.QComboBox()
        self.prefix_combo.setToolTip("Override auto-detection and force a specific light group prefix.")
        self.prefix_combo.addItems([
            "Auto-Detect Prefix",
            "Arnold (rgba_)",
            "Redshift (lightgroup)",
            "Karma (lpe_)",
            "Cycles (combined_)",
            "Custom (C_)",
            "Generic (light_)"
        ])
        control_layout.addWidget(self.prefix_combo)
        
        self.custom_prefix_input = QtWidgets.QLineEdit()
        self.custom_prefix_input.setPlaceholderText("Enter custom prefix...")
        self.custom_prefix_input.setVisible(False)
        control_layout.addWidget(self.custom_prefix_input)
        
        self.prefix_combo.currentIndexChanged.connect(
            lambda idx: self.custom_prefix_input.setVisible(idx == 5)
        )

        self.build_btn = QtWidgets.QPushButton("⚒ Build AOV Tree\u00A0\u00A0\u00A0\u00A0")
        self.build_btn.setProperty("primary", True)
        self.build_btn.setToolTip("Auto-detect AOVs and generate the Shuffle-Grade-Merge rebuild tree.")
        self.build_btn.clicked.connect(self._build_tree)
        control_layout.addWidget(self.build_btn)
        
        self.rebuild_btn = QtWidgets.QPushButton("⟳ Rebuild\u00A0\u00A0\u00A0\u00A0")
        self.rebuild_btn.setToolTip("Regenerate the tree from the selected node.")
        self.rebuild_btn.clicked.connect(self._build_tree)
        control_layout.addWidget(self.rebuild_btn)

        self.load_selected_btn = QtWidgets.QPushButton("📥 Load Selected\u00A0\u00A0\u00A0\u00A0")
        self.load_selected_btn.setToolTip("Load an existing AOV setup from the selected node.")
        self.load_selected_btn.clicked.connect(self._load_from_selection)
        control_layout.addWidget(self.load_selected_btn)
        
        control_layout.addStretch()
        layout.addLayout(control_layout)

        # Status
        self.status_lbl = QtWidgets.QLabel("")
        self.status_lbl.setStyleSheet("color: #aaa; font-style: italic;")
        layout.addWidget(self.status_lbl)

        # Master Controls
        self.master_group = QtWidgets.QGroupBox("Master Controls")
        master_layout = QtWidgets.QVBoxLayout(self.master_group)
        
        master_row = QtWidgets.QHBoxLayout()
        master_row.addWidget(QtWidgets.QLabel("Master Intensity:"))
        
        self.master_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.master_slider.setRange(int(LIGHT_MIXER_MIN * 100), int(LIGHT_MIXER_MAX * 100))
        self.master_slider.setValue(int(LIGHT_MIXER_DEFAULT * 100))
        self.master_slider.valueChanged.connect(self._apply_all_intensities)
        master_row.addWidget(self.master_slider)
        
        self.master_val_lbl = QtWidgets.QLabel(str(LIGHT_MIXER_DEFAULT))
        self.master_val_lbl.setMinimumWidth(40)
        master_row.addWidget(self.master_val_lbl)
        master_layout.addLayout(master_row)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(6)
        self.reset_btn = QtWidgets.QPushButton("↶ Reset All\u00A0\u00A0\u00A0\u00A0")
        self.reset_btn.setToolTip("Reset all light groups to default intensity.")
        self.reset_btn.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.reset_btn.clicked.connect(self._reset_all)
        btn_row.addWidget(self.reset_btn)
        
        self.unsolo_btn = QtWidgets.QPushButton("👁 Clear Solo\u00A0\u00A0\u00A0\u00A0")
        self.unsolo_btn.setToolTip("Un-solo all light groups.")
        self.unsolo_btn.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.unsolo_btn.clicked.connect(self._unsolo_all)
        btn_row.addWidget(self.unsolo_btn)
        
        self.save_preset_btn = QtWidgets.QPushButton("💾 Save Preset\u00A0\u00A0\u00A0\u00A0")
        self.save_preset_btn.setToolTip("Save the current light mix to a JSON file.")
        self.save_preset_btn.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.save_preset_btn.clicked.connect(self._save_preset)
        btn_row.addWidget(self.save_preset_btn)

        self.load_preset_btn = QtWidgets.QPushButton("📂 Load Preset\u00A0\u00A0\u00A0\u00A0")
        self.load_preset_btn.setToolTip("Load a light mix preset from a JSON file.")
        self.load_preset_btn.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.load_preset_btn.clicked.connect(self._load_preset)
        btn_row.addWidget(self.load_preset_btn)
        master_layout.addLayout(btn_row)

        # --- Snapshot System ---
        snap_group = QtWidgets.QGroupBox("📸 Version Snapshots")
        snap_group.setStyleSheet("QGroupBox { border: 1px solid #3a3a3a; border-radius:4px; margin-top:6px; color:#ccc; font-weight:bold; } QGroupBox::title { subcontrol-origin: margin; left: 8px; }")
        snap_layout = QtWidgets.QVBoxLayout(snap_group)
        snap_layout.setSpacing(4)

        snap_row1 = QtWidgets.QHBoxLayout()
        self._snap_name_edit = QtWidgets.QLineEdit()
        self._snap_name_edit.setPlaceholderText("Snapshot name (e.g. v001_morning)...")
        snap_row1.addWidget(self._snap_name_edit)
        save_snap_btn = QtWidgets.QPushButton("📸 Save Snapshot\u00A0\u00A0\u00A0\u00A0")
        save_snap_btn.setToolTip("Save a named snapshot of the current mix state.")
        save_snap_btn.setFixedWidth(120)
        save_snap_btn.clicked.connect(self._save_snapshot)
        snap_row1.addWidget(save_snap_btn)
        snap_layout.addLayout(snap_row1)

        snap_row2 = QtWidgets.QHBoxLayout()
        self._snap_combo_a = QtWidgets.QComboBox()
        self._snap_combo_a.setToolTip("Snapshot A (source)")
        snap_row2.addWidget(self._snap_combo_a)
        recall_btn = QtWidgets.QPushButton("↩ Recall\u00A0\u00A0\u00A0\u00A0")
        recall_btn.setFixedWidth(85)
        recall_btn.setToolTip("Recall this snapshot.")
        recall_btn.clicked.connect(lambda: self._recall_snapshot(self._snap_combo_a.currentText()))
        snap_row2.addWidget(recall_btn)
        del_btn = QtWidgets.QPushButton("🗑\u00A0\u00A0\u00A0\u00A0")
        del_btn.setFixedWidth(32)
        del_btn.setToolTip("Delete this snapshot.")
        del_btn.clicked.connect(lambda: self._delete_snapshot(self._snap_combo_a.currentText()))
        snap_row2.addWidget(del_btn)
        snap_layout.addLayout(snap_row2)

        snap_row3 = QtWidgets.QHBoxLayout()
        snap_row3.addWidget(QtWidgets.QLabel("Blend A↔B:", styleSheet="color:#999; font-size:8pt;"))
        self._snap_combo_b = QtWidgets.QComboBox()
        self._snap_combo_b.setToolTip("Snapshot B (target for blend)")
        snap_row3.addWidget(self._snap_combo_b)
        self._blend_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self._blend_slider.setRange(0, 100)
        self._blend_slider.setValue(0)
        self._blend_slider.setToolTip("Crossfade between Snapshot A (0%) and Snapshot B (100%)")
        self._blend_slider.valueChanged.connect(self._blend_snapshots)
        snap_row3.addWidget(self._blend_slider)
        self._blend_lbl = QtWidgets.QLabel("0%")
        self._blend_lbl.setFixedWidth(32)
        snap_row3.addWidget(self._blend_lbl)
        snap_layout.addLayout(snap_row3)

        master_layout.addWidget(snap_group)

        # Bridge Section
        self.bridge_group = QtWidgets.QGroupBox("3D Lighting Bridge")
        bridge_layout = QtWidgets.QVBoxLayout(self.bridge_group)
        
        bridge_row = QtWidgets.QHBoxLayout()
        bridge_row.setSpacing(6)
        self.software_combo = QtWidgets.QComboBox()
        self.software_combo.addItems(["Houdini", "Maya", "Blender"])
        self.software_combo.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        bridge_row.addWidget(self.software_combo)
        # Auto-update port when DCC target changes
        self.software_combo.currentTextChanged.connect(
            lambda sw: self._live_port_spin.setValue(LIVE_BRIDGE_PORTS.get(sw, LIVE_BRIDGE_DEFAULT_PORT))
            if hasattr(self, '_live_port_spin') else None
        )
        
        self.engine_combo = QtWidgets.QComboBox()
        self.engine_combo.addItems(["Karma", "Arnold", "Redshift", "Cycles"])
        self.engine_combo.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        bridge_row.addWidget(self.engine_combo)
        
        self.export_3d_btn = QtWidgets.QPushButton("📤 Export JSON Bridge\u00A0\u00A0\u00A0\u00A0")
        self.export_3d_btn.setToolTip("Export final float multipliers to JSON for your Lighting TD.")
        self.export_3d_btn.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.export_3d_btn.clicked.connect(self._export_3d)
        bridge_row.addWidget(self.export_3d_btn)
        bridge_layout.addLayout(bridge_row)
        
        self.toggle_offline_btn = QtWidgets.QPushButton("⏷ Show Offline Pipeline Tools\u00A0\u00A0\u00A0\u00A0")
        self.toggle_offline_btn.setStyleSheet("background: transparent; color: #888; text-align: left;")
        self.toggle_offline_btn.setCheckable(True)
        bridge_layout.addWidget(self.toggle_offline_btn)

        self.gen_scripts_btn = QtWidgets.QPushButton("🛠️ Generate 3D Importer Scripts\u00A0\u00A0\u00A0\u00A0")
        self.gen_scripts_btn.setStyleSheet("background-color: #2b4f2b; color: white;")
        self.gen_scripts_btn.clicked.connect(generate_bridge_scripts)
        bridge_layout.addWidget(self.gen_scripts_btn)

        self.import_houdini_btn = QtWidgets.QPushButton("📥 Import from Houdini\u00A0\u00A0\u00A0\u00A0")
        self.import_houdini_btn.setToolTip("Read a Houdini-exported light JSON back into the Nuke mixer.")
        self.import_houdini_btn.setStyleSheet("background-color: #2b3f5f; color: white;")
        self.import_houdini_btn.clicked.connect(self._import_from_houdini)
        bridge_layout.addWidget(self.import_houdini_btn)

        self.batch_export_btn = QtWidgets.QPushButton("📦 Batch Sequence Export\u00A0\u00A0\u00A0\u00A0")
        self.batch_export_btn.setToolTip("Export one JSON per shot for a whole sequence folder.")
        self.batch_export_btn.setStyleSheet("background-color: #4a2b5f; color: white;")
        self.batch_export_btn.clicked.connect(self._open_batch_export_dialog)
        bridge_layout.addWidget(self.batch_export_btn)
        
        self.gen_scripts_btn.setVisible(False)
        self.import_houdini_btn.setVisible(False)
        self.batch_export_btn.setVisible(False)
        
        def _toggle_offline(checked):
            self.gen_scripts_btn.setVisible(checked)
            self.import_houdini_btn.setVisible(checked)
            self.batch_export_btn.setVisible(checked)
            self.toggle_offline_btn.setText("⏶ Hide Offline Pipeline Tools" if checked else "⏷ Show Offline Pipeline Tools")
            
        self.toggle_offline_btn.clicked.connect(_toggle_offline)

        # ── Live Link row ──
        # ── Live Link row ──
        live_row = QtWidgets.QHBoxLayout()
        live_row.setSpacing(6)
        self._live_btn = QtWidgets.QPushButton("🔴 Live Link: OFF\u00A0\u00A0\u00A0\u00A0")
        self._live_btn.setCheckable(True)
        self._live_btn.setMinimumWidth(140)
        self._live_btn.setStyleSheet("background-color: #3a2020; color: #ff6b6b; font-weight: bold; padding: 6px 10px;")
        self._live_btn.setToolTip("Toggle real-time Nuke→DCC sync via socket.")
        self._live_btn.clicked.connect(self._toggle_live_link)
        live_row.addWidget(self._live_btn)
        
        self._mixer_dcc_combo = QtWidgets.QComboBox()
        self._mixer_dcc_combo.addItems(["Houdini", "Maya", "Blender"])
        self._mixer_dcc_combo.setToolTip("Select the DCC to send light data to.")
        self._mixer_dcc_combo.currentIndexChanged.connect(self._on_mixer_dcc_changed)
        live_row.addWidget(self._mixer_dcc_combo)

        live_row.addWidget(QtWidgets.QLabel("Host:", styleSheet="color:#999; font-size:8pt;"))
        self._live_host_edit = QtWidgets.QLineEdit("localhost")
        self._live_host_edit.setMinimumWidth(80)
        live_row.addWidget(self._live_host_edit)
        live_row.addWidget(QtWidgets.QLabel("Port:", styleSheet="color:#999; font-size:8pt;"))
        self._live_port_spin = QtWidgets.QSpinBox()
        self._live_port_spin.setRange(1024, 65535)
        self._live_port_spin.setValue(LIVE_BRIDGE_DEFAULT_PORT)
        self._live_port_spin.setFixedWidth(70)
        live_row.addWidget(self._live_port_spin)
        bridge_layout.addLayout(live_row)
        
        master_layout.addWidget(self.bridge_group)
        
        self.master_group.setVisible(False)
        layout.addWidget(self.master_group)

        # Light Groups Scroll Area
        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_widget = QtWidgets.QWidget()
        self.scroll_layout = QtWidgets.QVBoxLayout(self.scroll_widget)
        self.scroll_layout.setContentsMargins(4, 4, 4, 4)
        self.scroll_layout.setSpacing(12)
        self.scroll_layout.addStretch()
        self.scroll_area.setWidget(self.scroll_widget)
        
        layout.addWidget(self.scroll_area)

    def _sync_ui_to_nodes(self):
        try:
            f = nuke.frame()
            if hasattr(self, '_last_sync_frame') and self._last_sync_frame == f:
                return
            self._last_sync_frame = f
            was_updated = False
            for group_name, grade in self._grade_nodes.items():
                if not nuke.exists(grade.name()):
                    continue
                    
                if grade['lg_intensity'].isAnimated():
                    was_updated = True
                    new_val = grade['lg_intensity'].value()
                    
                    if group_name in self._sliders:
                        s = self._sliders[group_name]
                        s.blockSignals(True)
                        s.setValue(int(new_val * 100))
                        s.blockSignals(False)
                        
                    if hasattr(self, '_intensity_spins') and group_name in self._intensity_spins:
                        sp = self._intensity_spins[group_name]
                        sp.blockSignals(True)
                        sp.setValue(new_val)
                        sp.blockSignals(False)
                        
                if grade['lg_color'].isAnimated():
                    was_updated = True
                    c_val = grade['lg_color'].value()
                    if not isinstance(c_val, (list, tuple)): c_val = [c_val, c_val, c_val]
                    r_c, g_c, b_c = int(c_val[0]*255), int(c_val[1]*255), int(c_val[2]*255)
                    if group_name in self._color_btns:
                        self._color_btns[group_name].setStyleSheet(f"background-color: rgb({r_c}, {g_c}, {b_c}); border: 1px solid #555; border-radius: 3px;")
            
            if was_updated and hasattr(self, '_live_sender') and getattr(self._live_sender, 'is_connected', lambda: False)():
                self._broadcast_live_state()
        except Exception:
            pass

    def _build_tree(self):
        source = get_selected_source_node()
        if source is None:
            return

        prefix_idx = self.prefix_combo.currentIndex()
        prefix_override = None
        if prefix_idx == 1: prefix_override = "rgba_"
        elif prefix_idx == 2: prefix_override = "lightgroup"
        elif prefix_idx == 3: prefix_override = "lpe_"
        elif prefix_idx == 4: prefix_override = "combined_"
        elif prefix_idx == 5: prefix_override = self.custom_prefix_input.text().strip() or "c_"
        elif prefix_idx == 6: prefix_override = "light_"

        # Auto-detect renderer first so we can force the correct prefix
        from .aov_builder.channel_parser import detect_renderer
        from .constants import Renderer
        from .nuke_utils import get_channels_from_node, get_layers_from_channels
        try:
            channels = get_channels_from_node(source)
            layer_names = set(get_layers_from_channels(channels).keys())
            detected = detect_renderer(layer_names)
            if prefix_override is None and detected == Renderer.REDSHIFT:
                prefix_override = "lightgroup"
                # Also sync the combo so the user sees what was selected
                self.prefix_combo.setCurrentIndex(2)  # 'Redshift (lightgroup)'
            elif prefix_override is None and detected == Renderer.CYCLES:
                prefix_override = "combined_"
                self.prefix_combo.setCurrentIndex(4)  # 'Cycles (combined_)'
        except Exception:
            pass

        parsed = parse_channels(source, prefix_override=prefix_override)

        # For Redshift (and any renderer where light groups are the goal),
        # only require light_group_layers — shading AOVs are a bonus, not a blocker.
        if not parsed.light_group_layers:
            if parsed.renderer == Renderer.REDSHIFT:
                nuke.message(
                    "Crucible: No Redshift Light Group AOVs found.\n\n"
                    "Make sure you have enabled 'Light Group' AOVs in Redshift's\n"
                    "AOV Manager and your EXR contains layers starting with 'lightgroup'.\n\n"
                    f"Layers found: {', '.join(sorted(layer_names)[:12]) if 'layer_names' in dir() else '(could not read)'}"
                )
            elif not parsed.shading_layers:
                nuke.message("Crucible: No AOVs or light groups detected.")
            else:
                # Shading AOVs found but no light groups — still build for shading passes
                pass
            if not parsed.light_group_layers and not parsed.shading_layers:
                return

        result = build_aov_tree(parsed, source)
        self._grade_nodes = result.get('grade_nodes', {})

        self._clear_lg_controls()
        self._populate_lg_controls()

        renderer_name = parsed.renderer.value.title()
        n_lg = len(parsed.light_group_layers)
        self.status_lbl.setText(
            f"Built {renderer_name} tree.  "
            f"{n_lg} light group{'s' if n_lg != 1 else ''} • "
            f"{len(self._grade_nodes)} mixer channels."
        )
        self.master_group.setVisible(len(self._grade_nodes) > 0)

    def _load_from_selection(self):
        try:
            selected_node = nuke.selectedNode()
        except ValueError:
            nuke.message("Crucible: Please select a node in your AOV setup.")
            return

        # Trace up to find the central 'Dot' node connecting the light group shuffles
        def get_lg_dot(node, visited=None):
            if visited is None: visited = set()
            if node in visited: return None
            visited.add(node)
            
            def find_grade(n, v2=None):
                if v2 is None: v2 = set()
                if n in v2: return False
                v2.add(n)
                for child in n.dependent(nuke.INPUTS):
                    if child.Class() == 'Grade' and child.name().startswith('crucible_lg_'):
                        return True
                    elif child.Class() == 'Merge2':
                        if find_grade(child, v2):
                            return True
                return False

            if node.Class() == 'Dot':
                for dep in node.dependent(nuke.INPUTS):
                    if dep.Class() in ('Shuffle', 'Shuffle2'):
                        if find_grade(dep):
                            return node
            
            for i in range(node.inputs()):
                inp = node.input(i)
                if inp:
                    res = get_lg_dot(inp, visited)
                    if res: return res
            return None

        lg_dot = get_lg_dot(selected_node)
        
        # If not found upstream, try downstream (e.g. they selected the Read node)
        if not lg_dot:
            def get_lg_dot_down(node, visited=None):
                if visited is None: visited = set()
                if node in visited: return None
                visited.add(node)
                
                def find_grade_down(n, v2=None):
                    if v2 is None: v2 = set()
                    if n in v2: return False
                    v2.add(n)
                    for child in n.dependent(nuke.INPUTS):
                        if child.Class() == 'Grade' and child.name().startswith('crucible_lg_'):
                            return True
                        elif child.Class() == 'Merge2':
                            if find_grade_down(child, v2):
                                return True
                    return False

                if node.Class() == 'Dot':
                    for dep in node.dependent(nuke.INPUTS):
                        if dep.Class() in ('Shuffle', 'Shuffle2'):
                            if find_grade_down(dep):
                                return node
                                    
                for dep in node.dependent(nuke.INPUTS):
                    res = get_lg_dot_down(dep, visited)
                    if res: return res
                return None
                
            lg_dot = get_lg_dot_down(selected_node)

        if not lg_dot:
            # No Crucible tree found — try to auto-build from the selected node directly
            candidate = selected_node
            # Walk upstream to find a Read node
            visited_scan = set()
            def _find_read(n, vis):
                if n in vis: return None
                vis.add(n)
                if n.Class() == 'Read': return n
                for i in range(n.inputs()):
                    inp = n.input(i)
                    if inp:
                        r = _find_read(inp, vis)
                        if r: return r
                return None
            read_node = _find_read(candidate, visited_scan)
            if read_node is None and selected_node.Class() == 'Read':
                read_node = selected_node
            if read_node is not None:
                # Auto-select in the source combo and build the tree
                try:
                    nuke.selectAll()
                    nuke.invertSelection()
                    read_node.setSelected(True)
                except Exception:
                    pass
                self._build_tree()
                self.status_lbl.setText(
                    f"Auto-built Redshift Light Mixer from '{read_node.name()}'. "
                    f"{len(self._grade_nodes)} channel(s) loaded."
                )
                return
            nuke.message(
                "Crucible: Could not identify a Light Mixer setup from the selection.\n\n"
                "Try selecting your Read node and clicking Build Tree first,\n"
                "then use Load from Selection to reload an existing tree."
            )
            return

        grade_nodes = {}
        for dep in lg_dot.dependent(nuke.INPUTS):
            if dep.Class() in ('Shuffle', 'Shuffle2'):
                def collect_grades(n, v2=None):
                    if v2 is None: v2 = set()
                    if n in v2: return
                    v2.add(n)
                    for child in n.dependent(nuke.INPUTS):
                        if child.Class() == 'Grade' and child.name().startswith('crucible_lg_'):
                            label = child['label'].value()
                            group_name = label.split('\n')[0] if label else child.name().replace('crucible_lg_', '')
                            grade_nodes[group_name] = child
                        elif child.Class() == 'Merge2':
                            collect_grades(child, v2)
                collect_grades(dep)

        if not grade_nodes:
            nuke.message("Crucible: Found setup, but no light groups exist.")
            return

        self._grade_nodes = grade_nodes
        self._clear_lg_controls()
        self._populate_lg_controls()
        
        self.status_lbl.setText(f"Loaded existing setup. Found {len(self._grade_nodes)} light groups.")
        self.master_group.setVisible(True)

    def _clear_lg_controls(self):
        while self.scroll_layout.count() > 1: # Keep the stretch
            item = self.scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._sliders.clear()
        self._temp_sliders.clear()
        self._tint_sliders.clear()
        self._sat_sliders.clear()
        self._color_btns.clear()
        self._solo_btns.clear()
        self._mute_btns.clear()
        self._active_solo = None
        self._focused_group = None
        self._group_order = []

    def _populate_lg_controls(self):
        self._group_order = sorted(self._grade_nodes.keys())
        self._focused_group = None
        self._row_widgets = {}
        for group_name, grade_node in [(g, self._grade_nodes[g]) for g in self._group_order]:
            row_widget = QtWidgets.QWidget()
            row_widget.setStyleSheet("QWidget { background-color: #2a2a2b; border-radius: 4px; }")
            main_layout = QtWidgets.QVBoxLayout(row_widget)
            main_layout.setContentsMargins(6, 6, 6, 6)
            main_layout.setSpacing(4)
            
            # If the node is missing the new knobs, add them
            if 'lg_intensity' not in grade_node.knobs():
                k_int = nuke.Double_Knob('lg_intensity', 'Intensity')
                k_int.setValue(grade_node['multiply'].value()[0] if isinstance(grade_node['multiply'].value(), (list, tuple)) else grade_node['multiply'].value())
                k_col = nuke.Color_Knob('lg_color', 'Color')
                k_col.clearFlag(nuke.SINGLE_VALUE)
                k_col.setValue([1.0, 1.0, 1.0])
                k_temp = nuke.Double_Knob('lg_temp', 'Temperature')
                k_temp.setRange(1000, 10000)
                k_temp.setValue(6500)
                k_tint = nuke.Double_Knob('lg_tint', 'Tint')
                k_tint.setRange(-1, 1)
                k_tint.setValue(0.0)
                k_sat = nuke.Double_Knob('lg_sat', 'Saturation')
                k_sat.setRange(0, 2)
                k_sat.setValue(1.0)
                for k in [k_int, k_col, k_temp, k_tint, k_sat]:
                    grade_node.addKnob(k)

            # ROW 1: Intensity, Color Picker, S, M
            r1 = QtWidgets.QHBoxLayout()
            lbl = QtWidgets.QLabel(group_name)
            lbl.setMinimumWidth(80)
            lbl.setStyleSheet("font-weight: bold; color: #ddd;")
            r1.addWidget(lbl)
            
            intensity_val = grade_node['lg_intensity'].value()
            slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
            slider.setRange(int(LIGHT_MIXER_MIN * 100), int(LIGHT_MIXER_MAX * 100))
            slider.setValue(int(intensity_val * 100))
            self._sliders[group_name] = slider
            r1.addWidget(slider)
            
            val_spin = QtWidgets.QDoubleSpinBox()
            val_spin.setRange(LIGHT_MIXER_MIN, LIGHT_MIXER_MAX)
            val_spin.setValue(intensity_val)
            val_spin.setSingleStep(0.1)
            val_spin.setDecimals(3)
            val_spin.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
            val_spin.setMinimumWidth(40)
            val_spin.setStyleSheet("background-color: #222; color: #fff; border: 1px solid #444;")
            self._intensity_spins[group_name] = val_spin
            r1.addWidget(val_spin)
            
            col_btn = QtWidgets.QPushButton("")
            col_btn.setFixedSize(22, 22)
            col_btn.setToolTip("Select Base Color")
            c_val = grade_node['lg_color'].value()
            if not isinstance(c_val, (list, tuple)): c_val = [c_val, c_val, c_val]
            r_c, g_c, b_c = int(c_val[0]*255), int(c_val[1]*255), int(c_val[2]*255)
            col_btn.setStyleSheet(f"background-color: rgb({r_c}, {g_c}, {b_c}); border: 1px solid #555; border-radius: 3px;")
            self._color_btns[group_name] = col_btn
            r1.addWidget(col_btn)
            
            def make_color_cb(g_name, btn): return lambda: self._pick_color(g_name, btn)
            col_btn.clicked.connect(make_color_cb(group_name, col_btn))
            
            def make_solo_callback(g_name): return lambda *args: self._toggle_solo(g_name)
            def make_mute_callback(g_name): return lambda *args: self._toggle_mute(g_name)

            solo_btn = QtWidgets.QPushButton("S")
            solo_btn.setCheckable(True)
            solo_btn.setProperty("square", True)
            solo_btn.setProperty("solo", True)
            solo_btn.setFixedWidth(24)
            solo_btn.clicked.connect(make_solo_callback(group_name))
            self._solo_btns[group_name] = solo_btn
            r1.addWidget(solo_btn)

            mute_btn = QtWidgets.QPushButton("M")
            mute_btn.setCheckable(True)
            mute_btn.setProperty("square", True)
            mute_btn.setProperty("mute", True)
            mute_btn.setFixedWidth(24)
            mute_btn.clicked.connect(make_mute_callback(group_name))
            self._mute_btns[group_name] = mute_btn
            r1.addWidget(mute_btn)
            
            def make_reset_callback(g_name): return lambda *args: self._reset_group(g_name)
            reset_btn = QtWidgets.QPushButton("↶")
            reset_btn.setToolTip("Reset this light group")
            reset_btn.setProperty("square", True)
            reset_btn.setFixedWidth(24)
            reset_btn.setStyleSheet("color: #aaa;")
            reset_btn.clicked.connect(make_reset_callback(group_name))
            r1.addWidget(reset_btn)
            
            def make_key_callback(g_name): return lambda *args: self._set_keyframe(g_name)
            key_btn = QtWidgets.QPushButton("K")
            key_btn.setToolTip("Set Keyframe on current frame")
            key_btn.setProperty("square", True)
            key_btn.setFixedWidth(24)
            key_btn.setStyleSheet("color: #ffa500; font-weight: bold;")
            key_btn.clicked.connect(make_key_callback(group_name))
            r1.addWidget(key_btn)
            
            def make_del_key_callback(g_name): return lambda *args: self._clear_keyframes(g_name)
            del_btn = QtWidgets.QPushButton("X")
            del_btn.setToolTip("Clear all animation keyframes")
            del_btn.setProperty("square", True)
            del_btn.setFixedWidth(24)
            del_btn.setStyleSheet("color: #ff5555; font-weight: bold;")
            del_btn.clicked.connect(make_del_key_callback(group_name))
            r1.addWidget(del_btn)
            
            main_layout.addLayout(r1)

            # ROW 2: Temp, Tint, Desat
            r2 = QtWidgets.QHBoxLayout()
            r2.setContentsMargins(10, 0, 0, 0)
            
            r2.addWidget(QtWidgets.QLabel("Temp", styleSheet="color: #999; font-size: 8pt;"))
            temp_val = grade_node['lg_temp'].value()
            t_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
            t_slider.setRange(1000, 10000)
            t_slider.setValue(int(temp_val))
            self._temp_sliders[group_name] = t_slider
            r2.addWidget(t_slider)
            
            r2.addWidget(QtWidgets.QLabel("Tint", styleSheet="color: #999; font-size: 8pt;"))
            tint_val = grade_node['lg_tint'].value()
            tint_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
            tint_slider.setRange(-100, 100)
            tint_slider.setValue(int(tint_val * 100))
            self._tint_sliders[group_name] = tint_slider
            r2.addWidget(tint_slider)
            
            r2.addWidget(QtWidgets.QLabel("Sat", styleSheet="color: #999; font-size: 8pt;"))
            sat_val = grade_node['lg_sat'].value()
            sat_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
            sat_slider.setRange(0, 200)
            sat_slider.setValue(int(sat_val * 100))
            self._sat_sliders[group_name] = sat_slider
            r2.addWidget(sat_slider)
            
            main_layout.addLayout(r2)
            
            # Connect signals
            def make_slider_cb(g_name, s, vs):
                def cb(val):
                    self._on_intensity_changed(g_name, val, vs)
                return cb
            
            def make_spin_cb(g_name, s):
                def cb(val):
                    s.blockSignals(True)
                    s.setValue(int(val * 100))
                    s.blockSignals(False)
                    self._on_intensity_changed(g_name, int(val * 100), None)
                return cb

            slider.valueChanged.connect(make_slider_cb(group_name, slider, val_spin))
            val_spin.valueChanged.connect(make_spin_cb(group_name, slider))
            
            t_slider.valueChanged.connect(lambda val, g=group_name: self._on_temp_changed(g, val))
            tint_slider.valueChanged.connect(lambda val, g=group_name: self._on_tint_changed(g, val))
            sat_slider.valueChanged.connect(lambda val, g=group_name: self._on_sat_changed(g, val))

            # --- Hotkey support ---
            row_widget.setFocusPolicy(QtCore.Qt.ClickFocus)
            def make_key_handler(g_name):
                def key_press(event):
                    key = event.key()
                    if key == QtCore.Qt.Key_S:
                        self._solo_btns[g_name].toggle()
                        self._toggle_solo(g_name)
                    elif key == QtCore.Qt.Key_M:
                        self._mute_btns[g_name].toggle()
                        self._toggle_mute(g_name)
                    elif key == QtCore.Qt.Key_R:
                        self._reset_group(g_name)
                    elif key in (QtCore.Qt.Key_Up, QtCore.Qt.Key_Down):
                        self._navigate_groups(g_name, -1 if key == QtCore.Qt.Key_Up else 1)
                    else:
                        QtWidgets.QWidget.keyPressEvent(row_widget, event)
                return key_press
            row_widget.keyPressEvent = make_key_handler(group_name)
            self._row_widgets[group_name] = row_widget
            
            self.scroll_layout.insertWidget(self.scroll_layout.count() - 1, row_widget)

    def _navigate_groups(self, current, delta):
        """Move keyboard focus to the next/previous light group row."""
        if current not in self._group_order:
            return
        idx = self._group_order.index(current)
        new_idx = max(0, min(len(self._group_order) - 1, idx + delta))
        new_group = self._group_order[new_idx]
        widget = self._row_widgets.get(new_group)
        if widget:
            widget.setFocus()
            # Highlight the focused row
            for g, w in self._row_widgets.items():
                w.setStyleSheet("QWidget { background-color: %s; border-radius: 4px; }" % (
                    "#1e3a4a" if g == new_group else "#2a2a2b"
                ))

    def _pick_color(self, group_name, btn):
        grade = self._grade_nodes.get(group_name)
        if not grade: return
        curr = grade['lg_color'].value()
        if not isinstance(curr, (list, tuple)): curr = [curr, curr, curr]
        curr_c = QtGui.QColor(int(curr[0]*255), int(curr[1]*255), int(curr[2]*255))
        c = QtWidgets.QColorDialog.getColor(curr_c, self, f"Pick Base Color for {group_name}")
        if c.isValid():
            r, g, b = c.redF(), c.greenF(), c.blueF()
            if grade['lg_color'].isAnimated():
                grade['lg_color'].setValueAt(r, nuke.frame(), 0)
                grade['lg_color'].setValueAt(g, nuke.frame(), 1)
                grade['lg_color'].setValueAt(b, nuke.frame(), 2)
            else:
                grade['lg_color'].setValue(r, 0)
                grade['lg_color'].setValue(g, 1)
                grade['lg_color'].setValue(b, 2)
                
            btn.setStyleSheet(f"background-color: rgb({c.red()}, {c.green()}, {c.blue()}); border: 1px solid #555; border-radius: 3px;")
            self._apply_intensity(group_name)

    def _on_intensity_changed(self, group_name, val, val_spin):
        intensity = val / 100.0
        grade = self._grade_nodes.get(group_name)
        if grade:
            if grade['lg_intensity'].isAnimated():
                grade['lg_intensity'].setValueAt(intensity, nuke.frame())
            else:
                grade['lg_intensity'].setValue(intensity)
            
        if val_spin is not None:
            val_spin.blockSignals(True)
            val_spin.setValue(intensity)
            val_spin.blockSignals(False)
            
        self._apply_intensity(group_name)
        
    def _on_temp_changed(self, group_name, val):
        grade = self._grade_nodes.get(group_name)
        if grade:
            grade['lg_temp'].setValue(val)
        self._apply_intensity(group_name)
        
    def _on_tint_changed(self, group_name, val):
        grade = self._grade_nodes.get(group_name)
        if grade:
            grade['lg_tint'].setValue(val / 100.0)
        self._apply_intensity(group_name)
        
    def _on_sat_changed(self, group_name, val):
        grade = self._grade_nodes.get(group_name)
        if grade:
            grade['lg_sat'].setValue(val / 100.0)
        self._apply_intensity(group_name)

    def _apply_intensity(self, group_name):
        grade = self._grade_nodes.get(group_name)
        if not grade or not nuke.exists(grade.name()):
            return

        intensity = grade['lg_intensity'].value()
        color = [grade['lg_color'].value(0), grade['lg_color'].value(1), grade['lg_color'].value(2)]
        temp = grade['lg_temp'].value()
        tint = grade['lg_tint'].value()
        sat = grade['lg_sat'].value()
        master = self.master_slider.value() / 100.0

        if self._mute_btns[group_name].isChecked() or (self._active_solo and self._active_solo != group_name):
            final_mult = 0.0
        else:
            final_mult = intensity * master

        temp = max(1000.0, min(temp, 20000.0))
        
        # --- Physically accurate Kelvin → ACEScg ---
        # Step 1: Kelvin → CIE xy chromaticity (Kang et al. 2002)
        K = temp
        if K <= 4000:
            xc = (-0.2661239e9/K**3) + (-0.2343580e6/K**2) + (0.8776956e3/K) + 0.179910
        else:
            xc = (-3.0258469e9/K**3) + (2.1070379e6/K**2) + (0.2226347e3/K) + 0.240390

        if K <= 2222:
            yc = (-1.1063814*xc**3) + (-1.34811020*xc**2) + (2.18555832*xc) - 0.20219683
        elif K <= 4000:
            yc = (-0.9549476*xc**3) + (-1.37418593*xc**2) + (2.09137015*xc) - 0.16748867
        else:
            yc = (3.0817580*xc**3) + (-5.87338670*xc**2) + (3.75112997*xc) - 0.37001483

        # Step 2: CIE xy + Y=1 → XYZ
        Yc = 1.0
        Xc = (Yc / yc) * xc
        Zc = (Yc / yc) * (1.0 - xc - yc)

        # Step 3: XYZ → linear sRGB (D65 adapted)
        r_lin =  3.2404542*Xc - 1.5371385*Yc - 0.4985314*Zc
        g_lin = -0.9692660*Xc + 1.8760108*Yc + 0.0415560*Zc
        b_lin =  0.0556434*Xc - 0.2040259*Yc + 1.0572252*Zc
        r_lin = max(0.0, r_lin)
        g_lin = max(0.0, g_lin)
        b_lin = max(0.0, b_lin)

        # Step 4: linear sRGB → ACEScg (AP1) via Bradford-adapted matrix
        r = max(0.0,  0.6131*r_lin + 0.3395*g_lin + 0.0474*b_lin)
        g = max(0.0,  0.0701*r_lin + 0.9164*g_lin + 0.0135*b_lin)
        b = max(0.0,  0.0206*r_lin + 0.1096*g_lin + 0.8698*b_lin)

        # Normalize so the brightest channel stays at 1.0 (luminance-preserving)
        peak = max(r, g, b, 1e-6)
        r, g, b = r / peak, g / peak, b / peak

        # Apply Tint (green–magenta axis, scene-linear)
        if tint > 0:
            g = min(g * (1.0 + tint), 1.0)
        elif tint < 0:
            r = min(r * (1.0 + tint), 1.0)
            b = min(b * (1.0 + tint), 1.0)

        # Base color multiplier
        r *= color[0]
        g *= color[1]
        b *= color[2]

        # Apply Saturation (using ACEScg luminance weights)
        luma = r * 0.2722287 + g * 0.6740818 + b * 0.0536895
        r = max(0.0, luma + sat * (r - luma))
        g = max(0.0, luma + sat * (g - luma))
        b = max(0.0, luma + sat * (b - luma))

        final_r = r * final_mult
        final_g = g * final_mult
        final_b = b * final_mult

        if grade['multiply'].isAnimated():
            grade['multiply'].setValueAt(final_r, nuke.frame(), 0)
            grade['multiply'].setValueAt(final_g, nuke.frame(), 1)
            grade['multiply'].setValueAt(final_b, nuke.frame(), 2)
            grade['multiply'].setValueAt(final_mult, nuke.frame(), 3)
        else:
            grade['multiply'].setValue(final_r, 0)
            grade['multiply'].setValue(final_g, 1)
            grade['multiply'].setValue(final_b, 2)
            grade['multiply'].setValue(final_mult, 3)

        # Kick the debounced live broadcast so every individual slider move
        # (intensity, temp, tint, sat, color) sends an update automatically.
        if self._live_sender.is_connected():
            self._live_timer.start()

    def _apply_all_intensities(self, *args):
        # Update master label
        master_val = self.master_slider.value() / 100.0
        self.master_val_lbl.setText(f"{master_val:.2f}")
        
        for group_name in self._grade_nodes:
            self._apply_intensity(group_name)

        # Kick the debounced live broadcast (no-op if not connected)
        if self._live_sender.is_connected():
            self._live_timer.start()

    # ------------------------------------------------------------------
    # Live Bridge
    # ------------------------------------------------------------------

    def _on_mixer_dcc_changed(self, index: int):
        dcc = self._mixer_dcc_combo.currentText()
        port = LIVE_BRIDGE_PORTS.get(dcc, LIVE_BRIDGE_DEFAULT_PORT)
        self._live_port_spin.setValue(port)

    def _toggle_live_link(self):
        """Connect or disconnect the real-time Nuke→DCC link."""
        host = self._live_host_edit.text().strip() or "localhost"
        port = self._live_port_spin.value()
        self._live_sender.host = host
        self._live_sender.port = port

        if self._live_btn.isChecked():
            ok = self._live_sender.connect()
            if ok:
                self._live_btn.setText("🟢 Live Link: ON")
                self._live_btn.setStyleSheet(
                    "background-color: #1a3a1a; color: #6bff6b; font-weight: bold;"
                )
                self.status_lbl.setText(f"Live Link active → {host}:{port}")
                # Send current state immediately
                self._broadcast_live_state()
            else:
                self._live_btn.setChecked(False)
                self._live_btn.setText("🔴 Live Link: OFF")
                nuke.message(
                    f"Could not connect to DCC at {host}:{port}.\n\n"
                    f"Make sure the Crucible LiveBridge server is running in your DCC first."
                )
        else:
            self._live_sender.disconnect()
            self._live_btn.setText("🔴 Live Link: OFF")
            self._live_btn.setStyleSheet(
                "background-color: #3a2020; color: #ff6b6b; font-weight: bold; padding: 6px 10px;"
            )
            self.status_lbl.setText("Live Link disconnected.")

    def _check_live_health(self):
        """Heartbeat: if the sender lost the connection, reset the UI button.

        NukeLiveSender._send_with_retry() sets _connected=False when all retry
        attempts are exhausted. This timer polls every 3 s and reflects that in
        the UI so the user sees the link dropped without needing to move a slider.
        """
        if not self._live_sender.is_connected() and self._live_btn.isChecked():
            self._live_btn.setChecked(False)
            self._live_btn.setText("🔴 Live Link: OFF")
            self._live_btn.setStyleSheet(
                "background-color: #3a2020; color: #ff6b6b; font-weight: bold; padding: 6px 10px;"
            )
            self.status_lbl.setText(
                "⚠️ Live Link dropped — check DCC receiver and re-enable."
            )


    def _broadcast_live_state(self):
        """Serialize current mixer state and send to Houdini over socket."""
        if not self._live_sender.is_connected() or not self._sliders:
            return

        master = self.master_slider.value() / 100.0
        payload = {}

        for g, slider in self._sliders.items():
            intensity = slider.value() / 100.0
            is_muted  = self._mute_btns[g].isChecked()
            is_culled = self._active_solo and self._active_solo != g
            final_mult = 0.0 if (is_muted or is_culled) else intensity * master

            color_rgb = [1.0, 1.0, 1.0]
            is_anim = False
            grade = self._grade_nodes.get(g)
            if grade:
                is_anim = grade['multiply'].isAnimated() or grade['lg_intensity'].isAnimated() or grade['lg_color'].isAnimated()
                if final_mult != 0.0:
                    denom = abs(final_mult) if final_mult != 0 else 1.0
                    mv_r = grade['multiply'].value(0)
                    mv_g = grade['multiply'].value(1)
                    mv_b = grade['multiply'].value(2)
                    color_rgb = [round(mv_r / denom, 4), round(mv_g / denom, 4), round(mv_b / denom, 4)]

            clean = g
            for pfx in ('C_', 'c_', 'rgba_', 'lightgroup_'):
                if clean.startswith(pfx):
                    clean = clean[len(pfx):]
                    break

            payload[clean] = {"multiplier": round(final_mult, 4), "color": color_rgb, "is_animated": is_anim}

        print(f"Crucible Live Link sending to port {self._live_sender.port}: {list(payload.keys())}")
        self._live_sender.send({
            "metadata": {
                "software": self.software_combo.currentText(),
                "target_engine": self.engine_combo.currentText(),
                "frame": int(nuke.frame()),
            },
            "lighting_multipliers": payload,
        })

    def _toggle_solo(self, group_name):
        btn = self._solo_btns.get(group_name)
        if not btn:
            return
            
        if btn.isChecked():
            self._active_solo = group_name
            # Uncheck others
            for g, other_btn in self._solo_btns.items():
                if g != group_name:
                    other_btn.blockSignals(True)
                    other_btn.setChecked(False)
                    other_btn.blockSignals(False)
        else:
            if self._active_solo == group_name:
                self._active_solo = None
            
        self._apply_all_intensities()

    def _toggle_mute(self, group_name):
        self._apply_intensity(group_name)

    def _reset_all(self):
        self.master_slider.setValue(int(LIGHT_MIXER_DEFAULT * 100))
        self._active_solo = None
        for g, slider in self._sliders.items():
            slider.setValue(int(LIGHT_MIXER_DEFAULT * 100))
            if g in self._temp_sliders: self._temp_sliders[g].setValue(6500)
            if g in self._tint_sliders: self._tint_sliders[g].setValue(0)
            if g in self._sat_sliders: self._sat_sliders[g].setValue(100)
            
            grade = self._grade_nodes.get(g)
            if grade:
                grade['lg_color'].setValue([1.0, 1.0, 1.0])
                if g in self._color_btns: self._color_btns[g].setStyleSheet("background-color: rgb(255, 255, 255); border: 1px solid #555; border-radius: 3px;")
                
            self._solo_btns[g].setChecked(False)
            self._mute_btns[g].setChecked(False)
        self._apply_all_intensities()

    def _unsolo_all(self):
        self._active_solo = None
        for btn in self._solo_btns.values():
            btn.setChecked(False)
        self._apply_all_intensities()

    def _reset_group(self, group_name):
        if group_name in self._sliders: self._sliders[group_name].setValue(int(LIGHT_MIXER_DEFAULT * 100))
        if group_name in self._temp_sliders: self._temp_sliders[group_name].setValue(6500)
        if group_name in self._tint_sliders: self._tint_sliders[group_name].setValue(0)
        if group_name in self._sat_sliders: self._sat_sliders[group_name].setValue(100)
        
        grade = self._grade_nodes.get(group_name)
        if grade:
            grade['lg_color'].setValue([1.0, 1.0, 1.0])
            if group_name in self._color_btns:
                self._color_btns[group_name].setStyleSheet("background-color: rgb(255, 255, 255); border: 1px solid #555; border-radius: 3px;")
                
        if group_name in self._solo_btns: self._solo_btns[group_name].setChecked(False)
        if group_name in self._mute_btns: self._mute_btns[group_name].setChecked(False)
            
        if self._active_solo == group_name:
            self._active_solo = None
        self._apply_all_intensities()

    def _set_keyframe(self, group_name):
        grade = self._grade_nodes.get(group_name)
        if grade:
            f = nuke.frame()
            
            # MUST CACHE VALUES FIRST! Calling setAnimated() can reset knob evaluations to 0
            i_val = grade['lg_intensity'].value()
            
            c_val = grade['lg_color'].value()
            if not isinstance(c_val, (list, tuple)): c_val = [c_val, c_val, c_val]
            elif len(c_val) < 3: c_val = list(c_val) + [c_val[-1]] * (3 - len(c_val))
            
            m_val = grade['multiply'].value()
            if not isinstance(m_val, (list, tuple)): m_val = [m_val, m_val, m_val, m_val]
            elif len(m_val) < 4: m_val = list(m_val) + [m_val[-1]] * (4 - len(m_val))
            
            # NOW apply animations and restore the cached values
            grade['lg_intensity'].setAnimated()
            grade['lg_intensity'].setValueAt(i_val, f)
            
            for i in range(3):
                grade['lg_color'].setAnimated(i)
                grade['lg_color'].setValueAt(c_val[i], f, i)
                
            for i in range(4):
                grade['multiply'].setAnimated(i)
                grade['multiply'].setValueAt(m_val[i], f, i)
                
            # Force the Nuke timeline to show the keyframes by opening the node's properties
            grade.showControlPanel()
            self.status_lbl.setText(f"Keyframe set for '{group_name}' at frame {f}")
            self._apply_intensity(group_name)

    def _clear_keyframes(self, group_name):
        grade = self._grade_nodes.get(group_name)
        if grade:
            grade['lg_intensity'].clearAnimated()
            grade['lg_color'].clearAnimated()
            grade['multiply'].clearAnimated()
            grade.hideControlPanel()
            
            # Reset color to white
            grade['lg_color'].setValue([1.0, 1.0, 1.0])
            if group_name in self._color_btns:
                self._color_btns[group_name].setStyleSheet("background-color: rgb(255, 255, 255); border: 1px solid #555; border-radius: 3px;")
                
            self._apply_intensity(group_name)
            
            # Send clear message to DCC if connected
            if self._live_sender.is_connected():
                clean = group_name
                for pfx in ('C_', 'c_', 'rgba_', 'lightgroup_'):
                    if clean.startswith(pfx):
                        clean = clean[len(pfx):]
                        break
                self._live_sender.send({
                    "type": "clear_keyframes",
                    "light": clean
                })
                
            self.status_lbl.setText(f"Cleared all keyframes and reset color for '{group_name}'")

    # ------------------------------------------------------------------
    # Snapshot helpers
    # ------------------------------------------------------------------

    def _capture_state(self):
        """Capture the full current mixer state as a plain dict."""
        state = {
            "master": self.master_slider.value(),
            "groups": {g: s.value() for g, s in self._sliders.items()},
            "temps":  {g: s.value() for g, s in self._temp_sliders.items()},
            "tints":  {g: s.value() for g, s in self._tint_sliders.items()},
            "sats":   {g: s.value() for g, s in self._sat_sliders.items()},
            "mutes":  {g: m.isChecked() for g, m in self._mute_btns.items()},
            "colors": {},
        }
        for g in self._sliders:
            grade = self._grade_nodes.get(g)
            if grade:
                v = grade['lg_color'].value()
                if not isinstance(v, (list, tuple)): v = [v, v, v]
                state["colors"][g] = list(v)
        return state

    def _apply_state(self, state):
        """Restore the mixer to a previously captured state dict."""
        if "master" in state:
            self.master_slider.setValue(state["master"])
        for g, val in state.get("groups", {}).items():
            if g in self._sliders: self._sliders[g].setValue(val)
        for g, val in state.get("temps", {}).items():
            if g in self._temp_sliders: self._temp_sliders[g].setValue(val)
        for g, val in state.get("tints", {}).items():
            if g in self._tint_sliders: self._tint_sliders[g].setValue(val)
        for g, val in state.get("sats", {}).items():
            if g in self._sat_sliders: self._sat_sliders[g].setValue(val)
        for g, val in state.get("colors", {}).items():
            grade = self._grade_nodes.get(g)
            if grade:
                grade['lg_color'].setValue(val)
                r_c, g_c, b_c = int(val[0]*255), int(val[1]*255), int(val[2]*255)
                if g in self._color_btns:
                    self._color_btns[g].setStyleSheet(f"background-color: rgb({r_c}, {g_c}, {b_c}); border: 1px solid #555; border-radius: 3px;")
        for g, val in state.get("mutes", {}).items():
            if g in self._mute_btns: self._mute_btns[g].setChecked(val)
        self._apply_all_intensities()

    def _save_snapshot(self):
        name = self._snap_name_edit.text().strip()
        if not name:
            nuke.message("Please enter a snapshot name.")
            return
        self._snapshots[name] = self._capture_state()
        # Refresh both combos
        for combo in (self._snap_combo_a, self._snap_combo_b):
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(list(self._snapshots.keys()))
            combo.blockSignals(False)
        self._snap_name_edit.clear()
        self.status_lbl.setText(f"Snapshot '{name}' saved ({len(self._snapshots)} total).")

    def _recall_snapshot(self, name):
        if name not in self._snapshots:
            return
        self._blend_slider.blockSignals(True)
        self._blend_slider.setValue(0)
        self._blend_slider.blockSignals(False)
        self._blend_lbl.setText("0%")
        self._apply_state(self._snapshots[name])
        self.status_lbl.setText(f"Recalled snapshot '{name}'.")

    def _delete_snapshot(self, name):
        if name not in self._snapshots:
            return
        del self._snapshots[name]
        for combo in (self._snap_combo_a, self._snap_combo_b):
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(list(self._snapshots.keys()))
            combo.blockSignals(False)
        self.status_lbl.setText(f"Deleted snapshot '{name}'.")

    def _blend_snapshots(self, blend_val):
        """Crossfade linearly between snapshot A and snapshot B."""
        self._blend_lbl.setText(f"{blend_val}%")
        name_a = self._snap_combo_a.currentText()
        name_b = self._snap_combo_b.currentText()
        if name_a not in self._snapshots or name_b not in self._snapshots or name_a == name_b:
            return
        t = blend_val / 100.0
        a, b = self._snapshots[name_a], self._snapshots[name_b]

        # Build blended state
        blended = {
            "master": int(a["master"] * (1-t) + b["master"] * t),
            "groups": {g: int(a["groups"].get(g, 100) * (1-t) + b["groups"].get(g, 100) * t) for g in self._sliders},
            "temps":  {g: int(a["temps"].get(g, 6500) * (1-t) + b["temps"].get(g, 6500) * t) for g in self._temp_sliders},
            "tints":  {g: int(a["tints"].get(g, 0) * (1-t) + b["tints"].get(g, 0) * t) for g in self._tint_sliders},
            "sats":   {g: int(a["sats"].get(g, 100) * (1-t) + b["sats"].get(g, 100) * t) for g in self._sat_sliders},
            "mutes":  {g: a["mutes"].get(g, False) if t < 0.5 else b["mutes"].get(g, False) for g in self._mute_btns},
            "colors": {},
        }
        for g in self._sliders:
            ca = a["colors"].get(g, [1.0, 1.0, 1.0])
            cb = b["colors"].get(g, [1.0, 1.0, 1.0])
            blended["colors"][g] = [ca[i]*(1-t) + cb[i]*t for i in range(3)]

        self._apply_state(blended)

    def _save_preset(self):
        import json
        if not self._sliders:
            return
        
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save Light Mix Preset", "", "JSON Files (*.json)")
        if not file_path:
            return
            
        data = {
            "master": self.master_slider.value(),
            "groups": {g: s.value() for g, s in self._sliders.items()},
            "temps": {g: s.value() for g, s in self._temp_sliders.items()},
            "tints": {g: s.value() for g, s in self._tint_sliders.items()},
            "sats": {g: s.value() for g, s in self._sat_sliders.items()},
            "colors": {g: list(self._grade_nodes[g]['lg_color'].value() if isinstance(self._grade_nodes[g]['lg_color'].value(), (list, tuple)) else [self._grade_nodes[g]['lg_color'].value()]*3) for g in self._sliders.keys()},
            "mutes": {g: m.isChecked() for g, m in self._mute_btns.items()}
        }
        
        try:
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=4)
            nuke.message("Preset saved successfully.")
        except Exception as e:
            nuke.message("Failed to save preset:\n{}".format(e))

    def _load_preset(self):
        import json
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Load Light Mix Preset", "", "JSON Files (*.json)")
        if not file_path:
            return
            
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
                
            if "master" in data:
                self.master_slider.setValue(data["master"])
                
            groups = data.get("groups", {})
            mutes = data.get("mutes", {})
            temps = data.get("temps", {})
            tints = data.get("tints", {})
            sats = data.get("sats", {})
            colors = data.get("colors", {})
            
            for g, val in groups.items():
                if g in self._sliders: self._sliders[g].setValue(val)
            for g, val in temps.items():
                if g in self._temp_sliders: self._temp_sliders[g].setValue(val)
            for g, val in tints.items():
                if g in self._tint_sliders: self._tint_sliders[g].setValue(val)
            for g, val in sats.items():
                if g in self._sat_sliders: self._sat_sliders[g].setValue(val)
            for g, val in colors.items():
                grade = self._grade_nodes.get(g)
                if grade:
                    grade['lg_color'].setValue(val)
                    r_c, g_c, b_c = int(val[0]*255), int(val[1]*255), int(val[2]*255)
                    if g in self._color_btns: self._color_btns[g].setStyleSheet(f"background-color: rgb({r_c}, {g_c}, {b_c}); border: 1px solid #555; border-radius: 3px;")
                    
            for g, val in mutes.items():
                if g in self._mute_btns:
                    self._mute_btns[g].setChecked(val)
                    
            self._apply_all_intensities()
        except Exception as e:
            nuke.message("Failed to load preset:\n{}".format(e))
            
    def _export_3d(self):
        import json
        if not self._sliders:
            return
            
        msg = QtWidgets.QMessageBox()
        msg.setWindowTitle("Export 3D Lighting")
        msg.setText("Do you want to export the current frame or the full animated sequence?")
        btn_single = msg.addButton("Current Frame", QtWidgets.QMessageBox.AcceptRole)
        btn_anim = msg.addButton("Animated Sequence", QtWidgets.QMessageBox.AcceptRole)
        msg.addButton("Cancel", QtWidgets.QMessageBox.RejectRole)
        msg.exec_()
        
        if msg.clickedButton() not in (btn_single, btn_anim):
            return
            
        export_anim = (msg.clickedButton() == btn_anim)
            
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export 3D Lighting Data", "", "JSON Files (*.json)")
        if not file_path:
            return
            
        export_data = {}
        
        frames_to_export = []
        if export_anim:
            f_start = int(nuke.root().firstFrame())
            f_end = int(nuke.root().lastFrame())
            frames_to_export = list(range(f_start, f_end + 1))
        else:
            frames_to_export = [int(nuke.frame())]
            
        for g in self._sliders.keys():
            # Clean up the AOV name to match the 3D Light name
            clean_name = g
            for prefix in ['C_', 'c_', 'rgba_', 'lightgroup_']:
                if clean_name.startswith(prefix):
                    clean_name = clean_name[len(prefix):]
                    break
            
            is_muted = self._mute_btns[g].isChecked()
            is_solo_culled = self._active_solo and self._active_solo != g
            
            grade = self._grade_nodes.get(g)
            
            if export_anim:
                multipliers = []
                colors = []
                for f in frames_to_export:
                    if is_muted or is_solo_culled or not grade:
                        multipliers.append(0.0)
                        colors.append([1.0, 1.0, 1.0])
                    else:
                        mult_val = grade['lg_intensity'].getValueAt(f)
                        master_val = self.master_slider.value() / 100.0 # PySide has no keyframes, use static
                        final_mult = mult_val * master_val
                        
                        col_val = grade['multiply'].getValueAt(f)
                        if isinstance(col_val, (list, tuple)) and len(col_val) >= 3 and final_mult > 0:
                            cr = round(col_val[0] / final_mult, 4)
                            cg = round(col_val[1] / final_mult, 4)
                            cb = round(col_val[2] / final_mult, 4)
                            colors.append([cr, cg, cb])
                        else:
                            colors.append([1.0, 1.0, 1.0])
                        multipliers.append(round(final_mult, 4))
                        
                export_data[clean_name] = {
                    "animated": True,
                    "frames": frames_to_export,
                    "multipliers": multipliers,
                    "colors": colors
                }
            else:
                f = frames_to_export[0]
                if is_muted or is_solo_culled or not grade:
                    final_mult = 0.0
                    color_rgb = [1.0, 1.0, 1.0]
                else:
                    mult_val = grade['lg_intensity'].getValueAt(f)
                    master_val = self.master_slider.value() / 100.0
                    final_mult = mult_val * master_val
                    
                    col_val = grade['multiply'].getValueAt(f)
                    if isinstance(col_val, (list, tuple)) and len(col_val) >= 3 and final_mult > 0:
                        color_rgb = [
                            round(col_val[0] / final_mult, 4),
                            round(col_val[1] / final_mult, 4),
                            round(col_val[2] / final_mult, 4)
                        ]
                    else:
                        color_rgb = [1.0, 1.0, 1.0]
                
                export_data[clean_name] = {
                    "multiplier": round(final_mult, 4),
                    "color": color_rgb
                }
            
        software = self.software_combo.currentText()
        engine = self.engine_combo.currentText()
        
        export_lightmix_json(file_path, export_data, software, engine)

    def _import_from_houdini(self):
        """Read a Houdini-exported LightMix JSON back into Nuke.
        
        Houdini stores exposure in stops. We convert back to a linear
        multiplier using 2^exposure so the Nuke sliders reflect the
        actual light strength that is live in the Houdini scene.
        """
        import json, math
        if not self._sliders:
            nuke.message("Please build the AOV tree first before importing.")
            return

        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Import Houdini LightMix JSON", "", "JSON Files (*.json)"
        )
        if not file_path:
            return

        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
        except Exception as e:
            nuke.message(f"Failed to read JSON:\n{e}")
            return

        # Houdini JSON may use 'lighting_multipliers' key (bridge format)
        # or raw dict if exported directly from Houdini read-back tool.
        lights = data.get("lighting_multipliers", data)

        matched = 0
        for aov_key in list(self._sliders.keys()):
            # Strip prefix to get the bare light name
            clean = aov_key
            for prefix in ['C_', 'c_', 'rgba_', 'lightgroup_']:
                if clean.startswith(prefix):
                    clean = clean[len(prefix):]
                    break

            if clean not in lights:
                continue

            entry = lights[clean]
            if isinstance(entry, dict):
                exp_val  = entry.get("exposure", None)
                mult_val = entry.get("multiplier", None)
                color    = entry.get("color", [1.0, 1.0, 1.0])
            else:
                exp_val  = None
                mult_val = float(entry)
                color    = [1.0, 1.0, 1.0]

            # Prefer exposure→linear conversion; fall back to multiplier
            if exp_val is not None:
                linear_mult = pow(2.0, exp_val)
            elif mult_val is not None:
                linear_mult = float(mult_val)
            else:
                continue

            # Update intensity slider (clamped to mixer range)
            slider_val = int(max(LIGHT_MIXER_MIN, min(LIGHT_MIXER_MAX, linear_mult)) * 100)
            self._sliders[aov_key].setValue(slider_val)

            # Update color
            grade = self._grade_nodes.get(aov_key)
            if grade and color:
                grade['lg_color'].setValue(color)
                r_c = int(min(color[0], 1.0) * 255)
                g_c = int(min(color[1], 1.0) * 255)
                b_c = int(min(color[2], 1.0) * 255)
                if aov_key in self._color_btns:
                    self._color_btns[aov_key].setStyleSheet(
                        f"background-color: rgb({r_c}, {g_c}, {b_c}); border: 1px solid #555; border-radius: 3px;"
                    )
            matched += 1

        self._apply_all_intensities()
        self.status_lbl.setText(f"Imported from Houdini: {matched} lights synced.")
        if matched == 0:
            nuke.message("No matching lights found. Make sure light names in Houdini match your AOV names.")

    def _on_live_lights(self, lights_list: list):
        """Live Light Mixer Sync from DCC scene snapshot."""
        if not self._sliders:
            print("[Crucible Nuke] _on_live_lights aborted: No sliders built yet.")
            return
            
        print(f"[Crucible Nuke] _on_live_lights received {len(lights_list)} lights.")
        matched = 0
        for aov_key, slider in self._sliders.items():
            clean_aov = aov_key.lower()
            for prefix in ('c_', 'rgba_', 'lightgroup_', 'combined_'):
                if clean_aov.startswith(prefix):
                    clean_aov = clean_aov[len(prefix):]
                    break

            for live_light in lights_list:
                clean_live = live_light.get("name", "").lower()
                if clean_live == clean_aov:
                    intensity = float(live_light.get("intensity", 1.0))
                    color = live_light.get("color", [1.0, 1.0, 1.0])
                    
                    slider_val = int(max(LIGHT_MIXER_MIN, min(LIGHT_MIXER_MAX, intensity)) * 100)
                    slider.blockSignals(True)
                    slider.setValue(slider_val)
                    slider.blockSignals(False)
                    
                    if aov_key in self._intensity_spins:
                        self._intensity_spins[aov_key].blockSignals(True)
                        self._intensity_spins[aov_key].setValue(intensity)
                        self._intensity_spins[aov_key].blockSignals(False)
                        
                    grade = self._grade_nodes.get(aov_key)
                    if grade:
                        if grade['lg_intensity'].isAnimated():
                            grade['lg_intensity'].setValueAt(intensity, nuke.frame())
                        else:
                            grade['lg_intensity'].setValue(intensity)
                        if color:
                            grade['lg_color'].setValue(color)
                            r_c = int(min(color[0], 1.0) * 255)
                            g_c = int(min(color[1], 1.0) * 255)
                            b_c = int(min(color[2], 1.0) * 255)
                            if aov_key in self._color_btns:
                                self._color_btns[aov_key].setStyleSheet(
                                    f"background-color: rgb({r_c}, {g_c}, {b_c}); border: 1px solid #555; border-radius: 3px;"
                                )
                    matched += 1
                    break
            
            if matched == 0:
                # Debug logging if a particular AOV failed to match anything
                incoming_names = [l.get("name", "") for l in lights_list]
                print(f"[Crucible Nuke] AOV '{aov_key}' (cleaned: '{clean_aov}') did NOT match any incoming lights: {incoming_names}")
        
        print(f"[Crucible Nuke] Matched {matched} out of {len(self._sliders)} AOVs.")
        if matched > 0:
            self._apply_all_intensities()
            self.status_lbl.setText(f"Live Sync: {matched} lights updated from DCC.")
        else:
            self.status_lbl.setText("Live Sync: Nuke received packet, but 0 names matched AOVs.")

    def _open_batch_export_dialog(self):
        """Open the Batch Sequence Export dialog."""
        if not self._sliders:
            nuke.message("Please build the AOV tree first before batch exporting.")
            return
        dlg = CrucibleBatchExportDialog(self, self)
        dlg.exec_()


# ---------------------------------------------------------------------------
# Batch Export Dialog (Feature 5)
# ---------------------------------------------------------------------------

class CrucibleBatchExportDialog(QtWidgets.QDialog):
    """Export one Crucible LightMix JSON per EXR in a sequence folder."""

    def __init__(self, mixer_widget, parent=None):
        super(CrucibleBatchExportDialog, self).__init__(parent)
        self._mixer = mixer_widget
        self.setWindowTitle("Crucible — Batch Sequence Export")
        self.setMinimumWidth(560)
        self._setup_ui()

    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(8)

        # --- Sequence folder ---
        row1 = QtWidgets.QHBoxLayout()
        row1.addWidget(QtWidgets.QLabel("Sequence Folder:"))
        self._seq_edit = QtWidgets.QLineEdit()
        self._seq_edit.setPlaceholderText("/path/to/renders/")
        row1.addWidget(self._seq_edit)
        seq_btn = QtWidgets.QPushButton("Browse\u00A0\u00A0\u00A0\u00A0")
        seq_btn.setFixedWidth(72)
        seq_btn.clicked.connect(self._browse_seq)
        row1.addWidget(seq_btn)
        layout.addLayout(row1)

        # --- Output folder ---
        row2 = QtWidgets.QHBoxLayout()
        row2.addWidget(QtWidgets.QLabel("Output JSON Folder:"))
        self._out_edit = QtWidgets.QLineEdit()
        self._out_edit.setPlaceholderText("/path/to/json_output/")
        row2.addWidget(self._out_edit)
        out_btn = QtWidgets.QPushButton("Browse\u00A0\u00A0\u00A0\u00A0")
        out_btn.setFixedWidth(72)
        out_btn.clicked.connect(self._browse_out)
        row2.addWidget(out_btn)
        layout.addLayout(row2)

        # --- Extension filter ---
        row3 = QtWidgets.QHBoxLayout()
        row3.addWidget(QtWidgets.QLabel("File Extension:"))
        self._ext_combo = QtWidgets.QComboBox()
        self._ext_combo.addItems([".exr", ".dpx", ".tif", ".tiff", ".png"])
        row3.addWidget(self._ext_combo)
        row3.addStretch()
        layout.addLayout(row3)

        # --- Log output ---
        layout.addWidget(QtWidgets.QLabel("Export Log:"))
        self._log = QtWidgets.QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(150)
        self._log.setStyleSheet("background:#111; color:#8f8; font-family: monospace; font-size:8pt;")
        layout.addWidget(self._log)

        # --- Progress bar ---
        self._progress = QtWidgets.QProgressBar()
        self._progress.setValue(0)
        layout.addWidget(self._progress)

        # --- Buttons ---
        btn_row = QtWidgets.QHBoxLayout()
        run_btn = QtWidgets.QPushButton("▶ Run Batch Export\u00A0\u00A0\u00A0\u00A0")
        run_btn.setStyleSheet("background-color: #2b4f2b; color: white; font-weight: bold; padding: 6px 20px;")
        run_btn.clicked.connect(self._run)
        btn_row.addWidget(run_btn)
        close_btn = QtWidgets.QPushButton("Close\u00A0\u00A0\u00A0\u00A0")
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _browse_seq(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Sequence Folder")
        if folder:
            self._seq_edit.setText(folder)

    def _browse_out(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if folder:
            self._out_edit.setText(folder)

    def _run(self):
        import json, os, math

        seq_folder = self._seq_edit.text().strip()
        out_folder  = self._out_edit.text().strip()
        ext         = self._ext_combo.currentText()

        if not seq_folder or not os.path.isdir(seq_folder):
            nuke.message("Please select a valid sequence folder.")
            return
        if not out_folder or not os.path.isdir(out_folder):
            nuke.message("Please select a valid output folder.")
            return

        # Gather all matching files
        files = sorted([f for f in os.listdir(seq_folder) if f.lower().endswith(ext)])
        if not files:
            nuke.message(f"No {ext} files found in the sequence folder.")
            return

        self._log.clear()
        self._progress.setMaximum(len(files))
        self._progress.setValue(0)

        # Capture current mixer state as the grade template
        master = self._mixer.master_slider.value() / 100.0
        export_template = {}
        for g, slider in self._mixer._sliders.items():
            intensity  = slider.value() / 100.0
            is_muted   = self._mixer._mute_btns[g].isChecked()
            is_culled  = self._mixer._active_solo and self._mixer._active_solo != g
            final_mult = 0.0 if (is_muted or is_culled) else intensity * master

            color_rgb = [1.0, 1.0, 1.0]
            grade = self._mixer._grade_nodes.get(g)
            if grade and final_mult > 0:
                mv = grade['multiply'].value()
                if isinstance(mv, (list, tuple)) and len(mv) >= 3:
                    color_rgb = [round(mv[i] / final_mult, 4) for i in range(3)]

            clean = g
            for prefix in ['C_', 'c_', 'rgba_', 'lightgroup_']:
                if clean.startswith(prefix):
                    clean = clean[len(prefix):]
                    break

            export_template[clean] = {
                "multiplier": round(final_mult, 4),
                "color": color_rgb
            }

        software = self._mixer.software_combo.currentText()
        engine   = self._mixer.engine_combo.currentText()

        written = 0
        for i, fname in enumerate(files):
            shot_name = os.path.splitext(fname)[0]
            out_path  = os.path.join(out_folder, f"{shot_name}_lightmix.json")
            payload = {
                "metadata": {
                    "shot": shot_name,
                    "source_frame": os.path.join(seq_folder, fname),
                    "software": software,
                    "target_engine": engine,
                    "tool": "Crucible LightMixer v1.0"
                },
                "lighting_multipliers": export_template
            }
            try:
                with open(out_path, 'w') as f:
                    json.dump(payload, f, indent=4)
                self._log.appendPlainText(f"✔ {shot_name} → {out_path}")
                written += 1
            except Exception as e:
                self._log.appendPlainText(f"✘ {shot_name} FAILED: {e}")

            self._progress.setValue(i + 1)
            QtWidgets.QApplication.processEvents()

        self._log.appendPlainText(f"\n🎉 Done! {written}/{len(files)} JSON files exported.")



class RenderQCWidget(QtWidgets.QWidget):
    """The Render QC UI component."""

    def __init__(self, parent=None):
        super(RenderQCWidget, self).__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Header
        header = QtWidgets.QLabel("Render Quality Control")
        header.setProperty("header", True)
        layout.addWidget(header)

        # Controls Row 1
        control_layout1 = QtWidgets.QHBoxLayout()
        self.scan_btn = QtWidgets.QPushButton("🎯 Scan Current Frame\u00A0\u00A0\u00A0\u00A0")
        self.scan_btn.setProperty("primary", True)
        self.scan_btn.setToolTip("Run a quick QC diagnostic on the current frame.")
        self.scan_btn.clicked.connect(lambda: self._run_scan(False))
        control_layout1.addWidget(self.scan_btn)

        self.scan_range_btn = QtWidgets.QPushButton("📊 Scan Frame Range\u00A0\u00A0\u00A0\u00A0")
        self.scan_range_btn.setToolTip("Run QC diagnostics across the entire frame range.")
        self.scan_range_btn.clicked.connect(lambda: self._run_scan(True))
        control_layout1.addWidget(self.scan_range_btn)

        self.export_qc_btn = QtWidgets.QPushButton("📤 Export Report\u00A0\u00A0\u00A0\u00A0")
        self.export_qc_btn.setToolTip("Export the current QC report to HTML or JSON.")
        self.export_qc_btn.clicked.connect(self._export_qc)
        self.export_qc_btn.setEnabled(False)
        control_layout1.addWidget(self.export_qc_btn)
        
        control_layout1.addStretch()
        layout.addLayout(control_layout1)

        # Controls Row 2
        control_layout2 = QtWidgets.QHBoxLayout()
        self.contact_sheet_btn = QtWidgets.QPushButton("🖼 Generate AOV Contact Sheet\u00A0\u00A0\u00A0\u00A0")
        self.contact_sheet_btn.setToolTip("Builds a labeled contact sheet showing every pass inside the selected EXR.")
        self.contact_sheet_btn.clicked.connect(lambda: generate_aov_contact_sheet(nuke.selectedNode() if nuke.selectedNodes() else None))
        control_layout2.addWidget(self.contact_sheet_btn)
        
        self.fml_slate_btn = QtWidgets.QPushButton("🎞 Generate FML Review Slate\u00A0\u00A0\u00A0\u00A0")
        self.fml_slate_btn.setToolTip("Builds a 5-frame Review Sequence: First, Middle, Last, Contact Sheet, and EXR Metadata.")
        self.fml_slate_btn.clicked.connect(lambda: generate_fml_review_slate(nuke.selectedNode() if nuke.selectedNodes() else None))
        control_layout2.addWidget(self.fml_slate_btn)
        
        self.preflight_btn = QtWidgets.QPushButton("🚀 Run Pre-Flight Farm Check\u00A0\u00A0\u00A0\u00A0")
        self.preflight_btn.setToolTip("Scans the entire Nuke script for missing files and extreme bounding boxes before farm submission.")
        self.preflight_btn.clicked.connect(run_preflight_check)
        self.preflight_btn.setStyleSheet("background-color: #8e44ad; border: 1px solid #9b59b6;")
        control_layout2.addWidget(self.preflight_btn)
        
        control_layout2.addStretch()
        layout.addLayout(control_layout2)

        # Results Area
        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.results_widget = QtWidgets.QWidget()
        self.results_layout = QtWidgets.QVBoxLayout(self.results_widget)
        self.results_layout.setContentsMargins(10, 10, 10, 10)
        self.scroll_area.setWidget(self.results_widget)
        layout.addWidget(self.scroll_area)
        
        # Initial state
        self._clear_results()
        self.results_layout.addWidget(QtWidgets.QLabel("No scan results. Select a node and click Scan."))
        self.results_layout.addStretch()

    def _clear_results(self):
        while self.results_layout.count():
            item = self.results_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _run_scan(self, is_range):
        node = get_selected_source_node()
        if not node:
            return

        self._current_report = None
        self._clear_results()
        lbl = QtWidgets.QLabel("Scanning... Please wait.")
        self.results_layout.addWidget(lbl)
        self.results_layout.addStretch()
        QtWidgets.QApplication.processEvents()

        try:
            if is_range and node.Class() == 'Read':
                first = int(node['first'].value())
                last = int(node['last'].value())
                step = max(1, (last - first) // 20)
                
                all_issues = []
                seq_stats = {} # channel_name -> ChannelStat
                
                import copy
                
                for f in range(first, last + 1, step):
                    report = run_diagnostics(node, frame=f)
                    all_issues.extend(report.issues)
                    
                    # Accumulate sequence-level stats
                    for stat in report.channel_stats:
                        if stat.channel_name not in seq_stats:
                            seq_stats[stat.channel_name] = copy.copy(stat)
                        else:
                            seq_stats[stat.channel_name].min_value = min(seq_stats[stat.channel_name].min_value, stat.min_value)
                            seq_stats[stat.channel_name].max_value = max(seq_stats[stat.channel_name].max_value, stat.max_value)
                
                final_report = run_diagnostics(node, frame=first) # Get base report metadata
                final_report.frame = f"{first}-{last}"
                final_report.issues = all_issues
                final_report.channel_stats = list(seq_stats.values())
                final_report.passed = not any(i.severity in (SeverityLevel.ERROR, SeverityLevel.CRITICAL) for i in all_issues)
                
            else:
                final_report = run_diagnostics(node)
                
            self._current_report = final_report
            self._display_report(final_report)
        except Exception as e:
            self._clear_results()
            self.results_layout.addWidget(QtWidgets.QLabel(f"Scan failed: {e}"))
            self.results_layout.addStretch()

    def _display_report(self, report):
        self._clear_results()

        # Overall Status
        status_lbl = QtWidgets.QLabel()
        status_lbl.setProperty("header", True)
        if report.passed:
            status_lbl.setText("✅ PASS")
            status_lbl.setStyleSheet("color: #2ecc71; font-size: 16pt; font-weight: bold;")
        else:
            status_lbl.setText(f"❌ FAIL ({report.error_count} errors, {report.warning_count} warnings)")
            status_lbl.setStyleSheet("color: #e74c3c; font-size: 16pt; font-weight: bold;")
        self.results_layout.addWidget(status_lbl)

        # Details
        details_txt = f"Node: {report.source_node} | Frame: {report.frame} | Res: {report.width}x{report.height}"
        self.results_layout.addWidget(QtWidgets.QLabel(details_txt))

        # Issues
        if report.issues:
            issues_group = QtWidgets.QGroupBox("Issues Found")
            issues_layout = QtWidgets.QVBoxLayout(issues_group)
            
            for issue in report.issues:
                color = {
                    SeverityLevel.CRITICAL: "#c0392b",
                    SeverityLevel.ERROR: "#e74c3c",
                    SeverityLevel.WARNING: "#f39c12",
                    SeverityLevel.INFO: "#3498db"
                }.get(issue.severity, "#ffffff")
                
                issue_lbl = QtWidgets.QLabel(f"<b>[{issue.category}]</b> {issue.message}")
                issue_lbl.setStyleSheet(f"color: {color};")
                issue_lbl.setWordWrap(True)
                issues_layout.addWidget(issue_lbl)
                
            self.results_layout.addWidget(issues_group)

        # Channel Stats Table
        if report.channel_stats:
            stats_group = QtWidgets.QGroupBox("Channel Statistics")
            stats_layout = QtWidgets.QVBoxLayout(stats_group)
            
            table = QtWidgets.QTableWidget(len(report.channel_stats), 3)
            table.setHorizontalHeaderLabels(["Channel", "Min", "Max"])
            table.horizontalHeader().setStretchLastSection(True)
            table.verticalHeader().setVisible(False)
            table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            table.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
            
            for row, stat in enumerate(report.channel_stats):
                table.setItem(row, 0, QtWidgets.QTableWidgetItem(stat.channel_name))
                table.setItem(row, 1, QtWidgets.QTableWidgetItem(f"{stat.min_value:.6f}"))
                table.setItem(row, 2, QtWidgets.QTableWidgetItem(f"{stat.max_value:.6f}"))
                
            stats_layout.addWidget(table)
            self.results_layout.addWidget(stats_group)

        self.results_layout.addStretch()
        self.export_qc_btn.setEnabled(True)

    def _export_qc(self):
        if not self._current_report:
            return
            
        file_path, filter_used = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export QC Report", "Crucible_QC_Report.html", 
            "HTML Report (*.html);;JSON Data (*.json)"
        )
        if not file_path:
            return
            
        import json
        report = self._current_report
        
        data = {
            "source": report.source_node,
            "frame": report.frame,
            "resolution": f"{report.width}x{report.height}",
            "passed": report.passed,
            "error_count": report.error_count,
            "warning_count": report.warning_count,
            "issues": [{"severity": i.severity.name, "category": i.category, "message": i.message} for i in report.issues],
            "stats": {s.channel_name: {"min": s.min_value, "max": s.max_value} for s in report.channel_stats}
        }
        
        try:
            if file_path.endswith('.json'):
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
            else:
                import base64
                import tempfile
                import os
                import json
                
                # Get script metadata
                try:
                    script_path = nuke.root().name()
                except ValueError:
                    script_path = 'Untitled Script'
                
                # Gather all Read nodes in the scene for comprehensive asset tracking
                asset_rows = []
                for read_node in nuke.allNodes('Read'):
                    node_name = read_node.name()
                    asset_path = read_node['file'].evaluate() if 'file' in read_node.knobs() else "Unknown"
                    
                    r_time = "N/A"
                    c_info = []
                    all_meta = []
                    
                    try:
                        meta = read_node.metadata()
                        if meta:
                            for key, val in sorted(meta.items()):
                                lower_key = key.lower()
                                
                                # Extract specific highlights
                                if 'rendertime' in lower_key or 'render_time' in lower_key:
                                    r_time = str(val)
                                elif 'camera' in lower_key and ('focal' in lower_key or 'aperture' in lower_key or 'fov' in lower_key):
                                    clean_key = key.split('/')[-1]
                                    c_info.append(f"{clean_key}: {val}")
                                
                                # Gather all safe metadata for the raw dump
                                if 'manifest' not in lower_key and 'hash' not in lower_key and len(str(val)) < 200:
                                    all_meta.append(f"<b>{key}</b>: {val}")
                    except:
                        pass
                        
                    cam_str = ", ".join(c_info) if c_info else "N/A"
                    meta_dump = "<br>".join(all_meta) if all_meta else "No metadata available."
                    
                    # Determine type for styling (Plate vs CG)
                    is_plate = 'plate' in node_name.lower() or 'bg' in node_name.lower()
                    badge_color = "#3498db" if is_plate else "#9b59b6"
                    badge_text = "PLATE" if is_plate else "CG ELEMENT"
                    
                    # Create a collapsible details tag for the raw metadata
                    details_html = f"<details style='margin-top: 5px; cursor: pointer;'><summary style='color: #3498db; font-size: 11px;'>View Raw Metadata</summary><div style='padding: 10px; background: #1e1e1e; font-size: 10px; margin-top: 5px; border-radius: 4px; max-height: 150px; overflow-y: auto;'>{meta_dump}</div></details>"
                    
                    asset_rows.append(f"<tr><td><span style='background:{badge_color}; color:#fff; padding:2px 6px; border-radius:3px; font-size:11px; font-weight:bold;'>{badge_text}</span> {node_name}</td><td>{asset_path}{details_html}</td><td>{r_time}</td><td>{cam_str}</td></tr>")
                
                # Attempt to render the frame
                b64_img = ""
                src_node = nuke.toNode(report.source_node)
                w = None
                if src_node:
                    try:
                        temp_dir = tempfile.gettempdir()
                        temp_img = os.path.join(temp_dir, f"crucible_qc_{src_node.name()}.jpg").replace('\\', '/')
                        w = nuke.nodes.Write(inputs=[src_node], file=temp_img, file_type="jpeg", _jpeg_quality=0.85)
                        curr_frame = nuke.frame()
                        nuke.execute(w, curr_frame, curr_frame)
                        
                        with open(temp_img, "rb") as img_file:
                            b64_img = base64.b64encode(img_file.read()).decode('utf-8')
                            
                        try:
                            os.remove(temp_img)
                        except:
                            pass
                    except Exception as e:
                        print("Crucible: Failed to render QC image:", e)
                    finally:
                        if w is not None:
                            try:
                                nuke.delete(w)
                            except:
                                pass

                html = "<html><head><meta charset='utf-8'><style>body {font-family: 'Segoe UI', sans-serif; background: #1e1e1e; color: #e0e0e0; padding: 30px; max-width: 1200px; margin: auto;} "
                html += "table {border-collapse: collapse; width: 100%; margin-top: 15px; margin-bottom: 30px;} th, td {border: 1px solid #333; padding: 10px; text-align: left; word-break: break-all;} "
                html += "th {background-color: #2d2d30; color: #fff; width: 25%;} tr:nth-child(even) {background-color: #252526;} "
                html += ".error {color: #e74c3c; font-weight: bold;} .warning {color: #f39c12; font-weight: bold;} "
                html += "img.preview {width: 100%; border: 2px solid #333; border-radius: 6px; margin-bottom: 20px;} "
                html += "h1 {color: #f2a822; border-bottom: 2px solid #333; padding-bottom: 10px;}</style></head><body>"
                
                html += f"<h1>Crucible Render QC Report</h1>"
                
                if b64_img:
                    html += f"<img class='preview' src='data:image/jpeg;base64,{b64_img}'/>"
                
                status_html = "<span style='color:#2ecc71'>✅ PASSED</span>" if report.passed else "<span style='color:#e74c3c'>❌ FAILED</span>"
                
                html += "<h2>General Info</h2>"
                html += "<table>"
                html += f"<tr><th>Target Node</th><td>{report.source_node}</td></tr>"
                html += f"<tr><th>Status</th><td>{status_html}</td></tr>"
                html += f"<tr><th>Evaluated Frame(s)</th><td>{report.frame}</td></tr>"
                html += f"<tr><th>Resolution</th><td>{report.width}x{report.height}</td></tr>"
                html += f"<tr><th>Nuke Script</th><td>{script_path}</td></tr>"
                html += "</table>"
                
                html += "<h2>Scene Assets</h2>"
                html += "<table><tr><th style='width: 15%;'>Asset Node</th><th style='width: 45%;'>File Path</th><th style='width: 15%;'>Render Time</th><th style='width: 25%;'>Camera Info</th></tr>"
                if asset_rows:
                    html += "".join(asset_rows)
                else:
                    html += "<tr><td colspan='4' style='text-align:center;'>No Read nodes found in script.</td></tr>"
                html += "</table>"
                
                if report.issues:
                    html += "<h2>Diagnostic Issues</h2><ul>"
                    for i in report.issues:
                        css = "error" if "ERROR" in i.severity.name or "CRITICAL" in i.severity.name else "warning"
                        html += f"<li class='{css}'>[{i.category}] {i.message}</li>"
                    html += "</ul>"
                else:
                    html += "<h2>Diagnostic Issues</h2><p style='color:#2ecc71'>No critical issues found. Render is clean.</p>"
                    
                html += "<h2>Channel Analytics</h2><table><tr><th>Channel</th><th>Min Value</th><th>Max Value</th></tr>"
                for s in report.channel_stats:
                    html += f"<tr><td>{s.channel_name}</td><td>{s.min_value:.6f}</td><td>{s.max_value:.6f}</td></tr>"
                html += "</table></body></html>"
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(html)
                    
            nuke.message("QC Report exported successfully!")
        except Exception as e:
            nuke.message(f"Export failed:\n{e}")


# ---------------------------------------------------------------------------
# Lens & Integration Tab
# ---------------------------------------------------------------------------

class LensIntegrationWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(LensIntegrationWidget, self).__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        
        info = QtWidgets.QLabel(
            "<b>Lens, Lighting & FX Tools</b><br>"
            "Select the bottom of your CG tree (or your plate) and click to generate "
            "production-standard matching networks."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #b0b0b0; padding-bottom: 10px;")
        layout.addWidget(info)
        
        btn_layout = QtWidgets.QVBoxLayout()
        

        # Group: Integration & Lens
        lbl_lens = QtWidgets.QLabel("<b><br>Integration & Lens</b>")
        lbl_lens.setStyleSheet("color: #f2a822;")
        btn_layout.addWidget(lbl_lens)
        
        self.fog_btn = QtWidgets.QPushButton("🌫️ Physical Z-Depth Fog\u00A0\u00A0\u00A0\u00A0")
        self.fog_btn.setToolTip("Generates physically accurate exponential depth fog.")
        self.fog_btn.clicked.connect(lambda: fx_lighting_tools.create_physical_depth_fog(nuke.selectedNode() if nuke.selectedNodes() else None))
        btn_layout.addWidget(self.fog_btn)
        
        # LensMatch Engine
        self.lens_match_btn = QtWidgets.QPushButton("🎥 Unified LensMatch Engine\u00A0\u00A0\u00A0\u00A0")
        self.lens_match_btn.setToolTip("Builds a monolithic node for matching Optical Defocus, Chroma, Halation, Vignette, and Grain.")
        self.lens_match_btn.setStyleSheet("background-color: #2b4f2b; font-weight: bold;")
        self.lens_match_btn.clicked.connect(lambda: integration_tools.create_lens_match_engine())
        btn_layout.addWidget(self.lens_match_btn)
        

        
        # Auto Light Match
        self.light_match_btn = QtWidgets.QPushButton("💡 Auto Light Match\u00A0\u00A0\u00A0\u00A0")
        self.light_match_btn.setToolTip("Procedurally extracts ambient color from the Plate to tint the CG, preserving original exposure.")
        self.light_match_btn.clicked.connect(integration_tools.create_auto_light_match)
        btn_layout.addWidget(self.light_match_btn)
        

        

        
        # Edge Extend
        self.edge_btn = QtWidgets.QPushButton("🔪 Edge Extend\u00A0\u00A0\u00A0\u00A0")
        self.edge_btn.setToolTip("Fixes harsh CG edges using premult/unpremult bleed.")
        self.edge_btn.clicked.connect(lambda: fx_lighting_tools.create_edge_extend(nuke.selectedNode() if nuke.selectedNodes() else None))
        btn_layout.addWidget(self.edge_btn)
        

        
        # Exponential Glow
        self.glow_btn = QtWidgets.QPushButton("✨ Exponential Glow\u00A0\u00A0\u00A0\u00A0")
        self.glow_btn.setToolTip("Builds a physically accurate optical glow using stacked blurs.")
        self.glow_btn.clicked.connect(lambda: integration_tools.create_exponential_glow(nuke.selectedNode() if nuke.selectedNodes() else None))
        btn_layout.addWidget(self.glow_btn)
        
        # Smart Wrap
        self.wrap_btn = QtWidgets.QPushButton("🌗 Smart Light Wrap\u00A0\u00A0\u00A0\u00A0")
        self.wrap_btn.setToolTip("Builds a physically plausible optical edge bloom/wrap using exponential blurs.")
        self.wrap_btn.clicked.connect(lambda: integration_tools.create_light_wrap(nuke.selectedNode() if nuke.selectedNodes() else None))
        btn_layout.addWidget(self.wrap_btn)
        
        # Vignette
        self.vignette_btn = QtWidgets.QPushButton("🌑 Lens Vignette\u00A0\u00A0\u00A0\u00A0")
        self.vignette_btn.setToolTip("Creates a responsive radial vignette driven by format resolution.")
        self.vignette_btn.clicked.connect(lambda: integration_tools.create_vignette(nuke.selectedNode() if nuke.selectedNodes() else None))
        btn_layout.addWidget(self.vignette_btn)
        
        
        # Heat Distortion
        self.heat_btn = QtWidgets.QPushButton("〰️ Procedural Heat Distortion\u00A0\u00A0\u00A0\u00A0")
        self.heat_btn.setToolTip("Creates procedural heat distortion with Noise and IDistort.")
        self.heat_btn.clicked.connect(lambda: fx_lighting_tools.create_heat_distortion(nuke.selectedNode() if nuke.selectedNodes() else None))
        btn_layout.addWidget(self.heat_btn)

        
        # Camera Shake
        self.shake_btn = QtWidgets.QPushButton("📳 Procedural Camera Shake\u00A0\u00A0\u00A0\u00A0")
        self.shake_btn.setToolTip("Procedural handheld camera shake with accurate optical motion blur.")
        self.shake_btn.clicked.connect(lambda: integration_tools.create_camera_shake(nuke.selectedNode() if nuke.selectedNodes() else None))
        btn_layout.addWidget(self.shake_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)


# ---------------------------------------------------------------------------
# CG Utilities Tab
# ---------------------------------------------------------------------------

class CGUtilitiesWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(CGUtilitiesWidget, self).__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        
        info = QtWidgets.QLabel(
            "<b>CG Render Utilities</b><br>"
            "Select your raw CG render node and run these utilities to instantly "
            "extract heavy data streams."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #b0b0b0; padding-bottom: 10px;")
        layout.addWidget(info)
        
        btn_layout = QtWidgets.QVBoxLayout()
        
        # Cryptomatte
        self.crypto_btn = QtWidgets.QPushButton("🧩 Extract Cryptomattes\u00A0\u00A0\u00A0\u00A0")
        self.crypto_btn.setToolTip("Auto-detects and wires Cryptomatte nodes for all available ID manifests.")
        self.crypto_btn.clicked.connect(lambda: extract_cryptomattes(nuke.selectedNode() if nuke.selectedNodes() else None))
        btn_layout.addWidget(self.crypto_btn)
        
        # Crypto-Grade Generator
        self.crypto_grade_btn = QtWidgets.QPushButton("🎨 Crypto-Grade Generator\u00A0\u00A0\u00A0\u00A0")
        self.crypto_grade_btn.setToolTip("Generates a Grade node pre-masked by a Cryptomatte isolation based on search string.")
        self.crypto_grade_btn.clicked.connect(lambda: create_crypto_grade(nuke.selectedNode() if nuke.selectedNodes() else None))
        btn_layout.addWidget(self.crypto_grade_btn)
        
        # Z-Depth Focus
        self.zdefocus_btn = QtWidgets.QPushButton("🎯 Optical Z-Defocus\u00A0\u00A0\u00A0\u00A0")
        self.zdefocus_btn.setToolTip("Creates an artifact-free ZDefocus setup with edge-extension and unpremult/premult.")
        self.zdefocus_btn.clicked.connect(lambda: setup_zdefocus(nuke.selectedNode() if nuke.selectedNodes() else None))
        btn_layout.addWidget(self.zdefocus_btn)
        
        # Beauty Pass Builder
        self.beauty_btn = QtWidgets.QPushButton("✨ Rebuild Beauty Pass\u00A0\u00A0\u00A0\u00A0")
        self.beauty_btn.setToolTip("Extracts standard shader AOVs (Diffuse, Specular, Coat, SSS, etc.) and reconstructs the Beauty mix.")
        self.beauty_btn.clicked.connect(lambda: rebuild_beauty(nuke.selectedNode() if nuke.selectedNodes() else None))
        btn_layout.addWidget(self.beauty_btn)
        
        # Smart AOV Wrangler
        self.wrangler_btn = QtWidgets.QPushButton("🐙 Smart AOV Wrangler\u00A0\u00A0\u00A0\u00A0")
        self.wrangler_btn.setToolTip("Automatically extracts and organizes all AOVs from a multi-channel EXR into a color-coded node tree.")
        self.wrangler_btn.clicked.connect(lambda: smart_aov_wrangler(nuke.selectedNode() if nuke.selectedNodes() else None))
        btn_layout.addWidget(self.wrangler_btn)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)


# ---------------------------------------------------------------------------
# Pipeline Tools Tab
# ---------------------------------------------------------------------------

class PipelineToolsWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(PipelineToolsWidget, self).__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        
        info = QtWidgets.QLabel(
            "<b>Pipeline & Workflow Tools</b><br>"
            "Manage versions, validate color spaces, and automate slap comps."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #b0b0b0; padding-bottom: 10px;")
        layout.addWidget(info)
        
        btn_layout = QtWidgets.QVBoxLayout()
        
        self.color_btn = QtWidgets.QPushButton("🎨 OCIO Color Space Auditor\u00A0\u00A0\u00A0\u00A0")
        self.color_btn.setToolTip("Scans the script for illegal color spaces and OCIO violations.")
        self.color_btn.clicked.connect(check_color_spaces)
        btn_layout.addWidget(self.color_btn)
        
        self.vup_btn = QtWidgets.QPushButton("⬆️ Version Up\u00A0\u00A0\u00A0\u00A0")
        self.vup_btn.setToolTip("Increments the version number of the selected Read/Write node.")
        self.vup_btn.clicked.connect(lambda: change_version(nuke.selectedNode() if nuke.selectedNodes() else None, 'up'))
        btn_layout.addWidget(self.vup_btn)
        
        self.vdown_btn = QtWidgets.QPushButton("⬇️ Version Down\u00A0\u00A0\u00A0\u00A0")
        self.vdown_btn.setToolTip("Decrements the version number of the selected Read/Write node.")
        self.vdown_btn.clicked.connect(lambda: change_version(nuke.selectedNode() if nuke.selectedNodes() else None, 'down'))
        btn_layout.addWidget(self.vdown_btn)
        
        self.vlatest_btn = QtWidgets.QPushButton("🔝 Get Latest Version\u00A0\u00A0\u00A0\u00A0")
        self.vlatest_btn.setToolTip("Scans the directory and updates to the highest available version.")
        self.vlatest_btn.clicked.connect(lambda: change_version(nuke.selectedNode() if nuke.selectedNodes() else None, 'latest'))
        btn_layout.addWidget(self.vlatest_btn)
        
        self.slap_btn = QtWidgets.QPushButton("⚡ Build One-Click Slap-Comp\u00A0\u00A0\u00A0\u00A0")
        self.slap_btn.setToolTip("Select 1 CG Read and 1 Plate Read. Automatically builds a merged tree with Smart Wrap and Grain.")
        self.slap_btn.clicked.connect(build_slap_comp)
        btn_layout.addWidget(self.slap_btn)
        
        self.cdl_btn = QtWidgets.QPushButton("💾 Export CDL\u00A0\u00A0\u00A0\u00A0")
        self.cdl_btn.setToolTip("Export a .cdl file from the selected OCIOCDLTransform or Grade node.")
        self.cdl_btn.clicked.connect(export_cdl_from_node)
        btn_layout.addWidget(self.cdl_btn)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)


# ---------------------------------------------------------------------------
# Deep Tools Tab
# ---------------------------------------------------------------------------

class DeepToolsWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(DeepToolsWidget, self).__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        
        info = QtWidgets.QLabel(
            "<b>Deep Compositing Utilities</b><br>"
            "Select a Deep node to generate matte extractors and holdouts."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #b0b0b0; padding-bottom: 10px;")
        layout.addWidget(info)
        
        btn_layout = QtWidgets.QVBoxLayout()
        
        self.dmatte_btn = QtWidgets.QPushButton("🔪 Extract Deep 2D Matte\u00A0\u00A0\u00A0\u00A0")
        self.dmatte_btn.setToolTip("Slices Deep data at a specific Z-depth to create a flat 2D matte.")
        self.dmatte_btn.clicked.connect(lambda: create_deep_matte(nuke.selectedNode() if nuke.selectedNodes() else None))
        btn_layout.addWidget(self.dmatte_btn)
        
        self.dholdout_btn = QtWidgets.QPushButton("🛡️ Create Deep Holdout\u00A0\u00A0\u00A0\u00A0")
        self.dholdout_btn.setToolTip("Builds a Deep Holdout tree combining Deep and 2D elements.")
        self.dholdout_btn.clicked.connect(lambda: create_deep_holdout(nuke.selectedNode() if nuke.selectedNodes() else None))
        btn_layout.addWidget(self.dholdout_btn)
        
        self.dedge_btn = QtWidgets.QPushButton("🩹 Fix Deep Edges\u00A0\u00A0\u00A0\u00A0")
        self.dedge_btn.setToolTip("Builds a DeepExpression cluster to fix deep fringing/AA issues.")
        self.dedge_btn.clicked.connect(lambda: create_deep_edge_fix(nuke.selectedNode() if nuke.selectedNodes() else None))
        btn_layout.addWidget(self.dedge_btn)
        
        self.d2d_btn = QtWidgets.QPushButton("🧊 2D-to-Deep Conversion Rig\u00A0\u00A0\u00A0\u00A0")
        self.d2d_btn.setToolTip("Builds a rig to inject Z-depth into a flat 2D element and convert it into a Deep volume.")
        self.d2d_btn.clicked.connect(lambda: create_2d_to_deep_rig(nuke.selectedNode() if nuke.selectedNodes() else None))
        btn_layout.addWidget(self.d2d_btn)
        
        self.dslap_btn = QtWidgets.QPushButton("⚡ Deep Slap-Comp Assembler\u00A0\u00A0\u00A0\u00A0")
        self.dslap_btn.setToolTip("Select multiple Deep nodes to auto-merge, flatten to 2D, and build a standard unpremult/grade/premult block.")
        self.dslap_btn.clicked.connect(lambda: create_deep_slap_comp(nuke.selectedNodes() if nuke.selectedNodes() else None))
        btn_layout.addWidget(self.dslap_btn)
        
        self.dopt_btn = QtWidgets.QPushButton("📉 Deep Memory Inspector\u00A0\u00A0\u00A0\u00A0")
        self.dopt_btn.setToolTip("Scans a Deep node and provides frustum/bbox culling and micro-density cleanup to slash memory usage.")
        self.dopt_btn.clicked.connect(lambda: create_deep_memory_inspector(nuke.selectedNode() if nuke.selectedNodes() else None))
        btn_layout.addWidget(self.dopt_btn)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)


# ---------------------------------------------------------------------------
# Pass Manager Tab
# ---------------------------------------------------------------------------

class PassManagerWidget(QtWidgets.QWidget):
    """Universal AOV Pass Manager — normalises, validates, and routes
    multi-pass EXR channels from any DCC renderer."""

    # Status-colour mapping
    _STATUS_COLORS = {
        PassStatus.OK:      "#2ecc71",
        PassStatus.MISSING: "#e74c3c",
        PassStatus.EXTRA:   "#3498db",
        PassStatus.WARNING: "#f39c12",
    }

    def __init__(self, parent=None):
        super(PassManagerWidget, self).__init__(parent)
        self._manager  = PassManager()
        self._manifest = None
        self._setup_ui()

        # Polling timer for Nuke listener (forces queue drain without UI redraw)
        self._listener_timer = QtCore.QTimer(self)
        self._listener_timer.setInterval(100)
        self._listener_timer.timeout.connect(self._pump_listener_queue)
        self._listener_timer.start()

    def _pump_listener_queue(self):
        """Force the NukeLiveListener to dispatch its queue independently of Nuke's updateUI."""
        if self._live_listener and self._live_listener._running:
            self._live_listener._dispatch_queue()

    # ------------------------------------------------------------------ #
    # UI Build
    # ------------------------------------------------------------------ #

    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        hdr = QtWidgets.QLabel("Universal Pass Manager")
        hdr.setProperty("header", True)
        layout.addWidget(hdr)

        info = QtWidgets.QLabel(
            "Analyse, normalise, and validate EXR passes from Arnold, "
            "Karma, Cycles, or Redshift. (To import camera/scene data, "
            "use the Pipeline Tools tab)."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color:#999; font-size:9pt; padding-bottom:4px;")
        layout.addWidget(info)

        # ── SPLITTER ───────────────────────────────────────────────────
        self._splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        layout.addWidget(self._splitter)

        top_widget = QtWidgets.QWidget()
        top_layout = QtWidgets.QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        
        bottom_widget = QtWidgets.QWidget()
        bottom_layout = QtWidgets.QVBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 10, 0, 0)

        self._splitter.addWidget(top_widget)
        self._splitter.addWidget(bottom_widget)
        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 0)

        # ── TOP ROW: scan + schema ──────────────────────────────────────
        top_row = QtWidgets.QHBoxLayout()

        self._scan_btn = QtWidgets.QPushButton("🔍 Scan Selected Node\u00A0\u00A0\u00A0\u00A0")
        self._scan_btn.setProperty("primary", True)
        self._scan_btn.setToolTip(
            "Select a Read node and click to parse all EXR passes."
        )
        self._scan_btn.clicked.connect(self._scan_node)
        top_row.addWidget(self._scan_btn)

        top_row.addWidget(QtWidgets.QLabel("Schema:", styleSheet="color:#aaa;"))
        self._schema_combo = QtWidgets.QComboBox()
        self._schema_combo.addItems(["Auto"] + list(BUILT_IN_SCHEMAS.keys()))
        self._schema_combo.setToolTip(
            "Validation schema.  'Auto' picks the best match for the detected renderer."
        )
        top_row.addWidget(self._schema_combo)

        self._validate_btn = QtWidgets.QPushButton("✅ Validate\u00A0\u00A0\u00A0\u00A0")
        self._validate_btn.setToolTip("Validate passes against selected schema.")
        self._validate_btn.clicked.connect(self._validate)
        top_row.addWidget(self._validate_btn)

        top_layout.addLayout(top_row)

        # ── STATUS BAR ─────────────────────────────────────────────────
        self._status_lbl = QtWidgets.QLabel("No passes loaded. Select a node and click Scan.")
        self._status_lbl.setStyleSheet("color:#888; font-style:italic; font-size:9pt;")
        top_layout.addWidget(self._status_lbl)

        # ── PASS TABLE ─────────────────────────────────────────────────
        self._table = QtWidgets.QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            ["DCC Layer Name", "Crucible Standard", "Category", "Channels", "Status"]
        )
        self._table.horizontalHeader().setStretchLastSection(False)
        self._table.horizontalHeader().setSectionResizeMode(
            0, QtWidgets.QHeaderView.Stretch
        )
        self._table.horizontalHeader().setSectionResizeMode(
            1, QtWidgets.QHeaderView.Stretch
        )
        self._table.horizontalHeader().setSectionResizeMode(
            2, QtWidgets.QHeaderView.ResizeToContents
        )
        self._table.horizontalHeader().setSectionResizeMode(
            3, QtWidgets.QHeaderView.ResizeToContents
        )
        self._table.horizontalHeader().setSectionResizeMode(
            4, QtWidgets.QHeaderView.ResizeToContents
        )
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.setMinimumHeight(200)
        top_layout.addWidget(self._table)

        # ── ACTION ROW ─────────────────────────────────────────────────
        act_row = QtWidgets.QHBoxLayout()

        self._route_btn = QtWidgets.QPushButton("🔀 Auto-Route Passes\u00A0\u00A0\u00A0\u00A0")
        self._route_btn.setToolTip(
            "Create Shuffle2 nodes for every pass, organised into backdrops."
        )
        self._route_btn.clicked.connect(self._auto_route)
        act_row.addWidget(self._route_btn)

        self._export_manifest_btn = QtWidgets.QPushButton("💾 Export Manifest\u00A0\u00A0\u00A0\u00A0")
        self._export_manifest_btn.setToolTip(
            "Save the pass manifest as a Crucible JSON for archive or diffing."
        )
        self._export_manifest_btn.clicked.connect(self._export_manifest)
        act_row.addWidget(self._export_manifest_btn)

        self._diff_btn = QtWidgets.QPushButton("⚖ Diff Manifests\u00A0\u00A0\u00A0\u00A0")
        self._diff_btn.setToolTip(
            "Compare two Crucible manifest JSONs to see which passes differ."
        )
        self._diff_btn.clicked.connect(self._diff_manifests)
        act_row.addWidget(self._diff_btn)

        bottom_layout.addLayout(act_row)


        # ── LIVE PULL GROUP (ALL DCCs) ──────────────────────────────────
        live_grp = QtWidgets.QGroupBox("📡 Live Pull — Bidirectional DCC Bridge   ")
        live_layout = QtWidgets.QVBoxLayout(live_grp)
        live_layout.setSpacing(5)

        live_info = QtWidgets.QLabel(
            "Pull camera animation and scene data in real-time from a running "
            "Houdini, Maya, or Blender session — no JSON files required."
        )
        live_info.setWordWrap(True)
        live_info.setStyleSheet("color:#999; font-size:9pt;")
        live_layout.addWidget(live_info)

        # DCC selector row
        dcc_sel_row = QtWidgets.QHBoxLayout()
        dcc_sel_row.addWidget(QtWidgets.QLabel("DCC:", styleSheet="color:#aaa; font-size:9pt;"))
        self._live_dcc_combo = QtWidgets.QComboBox()
        self._live_dcc_combo.addItems(["Houdini", "Maya", "Blender"])
        self._live_dcc_combo.setFixedWidth(90)
        self._live_dcc_combo.setToolTip("Select the DCC you want to pull data from.")
        self._live_dcc_combo.currentIndexChanged.connect(self._on_dcc_changed)
        dcc_sel_row.addWidget(self._live_dcc_combo)

        dcc_sel_row.addSpacing(10)
        dcc_sel_row.addWidget(QtWidgets.QLabel("Host:", styleSheet="color:#aaa; font-size:9pt;"))
        self._live_host_edit = QtWidgets.QLineEdit("localhost")
        self._live_host_edit.setMaximumWidth(110)
        dcc_sel_row.addWidget(self._live_host_edit)

        dcc_sel_row.addWidget(QtWidgets.QLabel("Out Port:", styleSheet="color:#aaa; font-size:9pt;"))
        self._live_out_port = QtWidgets.QSpinBox()
        self._live_out_port.setRange(1024, 65535)
        self._live_out_port.setValue(LIVE_BRIDGE_DEFAULT_PORT)
        self._live_out_port.setFixedWidth(65)
        self._live_out_port.setToolTip("Port the DCC server is listening on.")
        dcc_sel_row.addWidget(self._live_out_port)

        dcc_sel_row.addWidget(QtWidgets.QLabel("In Port:", styleSheet="color:#aaa; font-size:9pt;"))
        self._live_in_port = QtWidgets.QSpinBox()
        self._live_in_port.setRange(1024, 65535)
        self._live_in_port.setValue(LIVE_BRIDGE_LISTEN_PORT)
        self._live_in_port.setFixedWidth(65)
        self._live_in_port.setToolTip("Port Nuke listens on for incoming DCC data (all DCCs share this).")
        dcc_sel_row.addWidget(self._live_in_port)
        dcc_sel_row.addStretch()
        live_layout.addLayout(dcc_sel_row)

        # Listener toggle + status
        listener_row = QtWidgets.QHBoxLayout()
        self._listener_btn = QtWidgets.QPushButton("🔴 Listener: OFF\u00A0\u00A0\u00A0\u00A0")
        self._listener_btn.setMinimumWidth(150)
        self._listener_btn.setFixedHeight(28)
        self._listener_btn.setCheckable(True)
        self._listener_btn.setStyleSheet(
            "background-color:#3a1a1a; color:#ff6b6b; font-size:9pt; font-weight:bold; padding:4px;"
        )
        self._listener_btn.setToolTip(
            "Start Nuke's inbound listener so any DCC can push data back."
        )
        self._listener_btn.clicked.connect(self._toggle_listener)
        listener_row.addWidget(self._listener_btn)

        self._listener_status = QtWidgets.QLabel("Listener not running.")
        self._listener_status.setStyleSheet("color:#666; font-size:8pt; font-style:italic;")
        self._listener_status.setWordWrap(True)
        self._listener_status.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        listener_row.addWidget(self._listener_status)
        listener_row.addStretch()
        live_layout.addLayout(listener_row)

        # Pull action buttons
        pull_row = QtWidgets.QHBoxLayout()
        self._pull_cam_btn = QtWidgets.QPushButton("🎥 Pull Camera (frame)\u00A0\u00A0\u00A0\u00A0")
        self._pull_cam_btn.setMinimumWidth(170)
        self._pull_cam_btn.setFixedHeight(28)
        self._pull_cam_btn.setStyleSheet("background-color:#1a2a4a; color:#aaddff; font-size:9pt; font-weight:bold; padding:4px;")
        self._pull_cam_btn.setToolTip("Ask the DCC to send the active camera at the current frame.")
        self._pull_cam_btn.clicked.connect(self._pull_camera_live)

        # ── ONE-CLICK MASTER BUILD BUTTON ──────────────────────────────
        oneclk_row = QtWidgets.QHBoxLayout()
        self._build_live_scene_btn = QtWidgets.QPushButton(
            "⚡  Build Live 3D Scene  —  Pull Camera + Rig + Projection in one click   "
        )
        self._build_live_scene_btn.setMinimumHeight(36)
        self._build_live_scene_btn.setStyleSheet(
            "background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            " stop:0 #1a1a4a, stop:0.5 #2a1a3a, stop:1 #1a2a4a);"
            " color:#ffffff; font-size:10pt; font-weight:bold;"
            " border:1px solid #5555aa; border-radius:4px;"
        )
        self._build_live_scene_btn.setToolTip(
            "ONE CLICK: Requests the full animated camera from the active DCC, then\n"
            "automatically builds:\n"
            "  • Background plate (from selected Read) or CheckerBoard\n"
            "  • Scene + ScanlineRender 3D rig\n"
            "  • Frozen Projection Camera (for paint-outs)\n"
            "  • Project3D + RotoPaint + Card2\n"
            "  • Backdrop organiser\n\n"
            "Select a Read node first if you have a background plate."
        )
        self._build_live_scene_btn.clicked.connect(self._one_click_build_3d_scene)
        oneclk_row.addWidget(self._build_live_scene_btn)
        live_layout.addLayout(oneclk_row)
        pull_row.addWidget(self._pull_cam_btn)

        self._pull_cam_seq_btn = QtWidgets.QPushButton("🎥 Pull Camera Sequence\u00A0\u00A0\u00A0\u00A0")
        self._pull_cam_seq_btn.setMinimumWidth(200)
        self._pull_cam_seq_btn.setFixedHeight(28)
        self._pull_cam_seq_btn.setStyleSheet("background-color:#1a2a4a; color:#aaddff; font-size:9pt; font-weight:bold; padding:4px;")
        self._pull_cam_seq_btn.setToolTip("Ask the DCC to send the full camera animation for the frame range.")
        self._pull_cam_seq_btn.clicked.connect(self._pull_camera_sequence_live)
        pull_row.addWidget(self._pull_cam_seq_btn)

        self._pull_scene_btn = QtWidgets.QPushButton("🌍 Pull Scene Info\u00A0\u00A0\u00A0\u00A0")
        self._pull_scene_btn.setMinimumWidth(150)
        self._pull_scene_btn.setFixedHeight(28)
        self._pull_scene_btn.setStyleSheet("background-color:#1a3a2a; color:#aaffcc; font-size:9pt; font-weight:bold; padding:4px;")
        self._pull_scene_btn.setToolTip("Ask the DCC to send a full scene snapshot (lights, render settings).")
        self._pull_scene_btn.clicked.connect(self._pull_scene_live)
        pull_row.addWidget(self._pull_scene_btn)
        live_layout.addLayout(pull_row)

        # Diagnostic row
        diag_row = QtWidgets.QHBoxLayout()
        self._ping_btn = QtWidgets.QPushButton("📡 Ping DCC\u00A0\u00A0\u00A0\u00A0")
        self._ping_btn.setMinimumWidth(100)
        self._ping_btn.setFixedHeight(26)
        self._ping_btn.setStyleSheet("background-color:#2a2a2a; color:#ffdd88; font-size:9pt;")
        self._ping_btn.setToolTip("Send a ping and wait for pong — tests the full round-trip TCP path.")
        self._ping_btn.clicked.connect(self._ping_dcc)
        diag_row.addWidget(self._ping_btn)

        self._selftest_btn = QtWidgets.QPushButton("🔍 Test Listener Port\u00A0\u00A0\u00A0\u00A0")
        self._selftest_btn.setMinimumWidth(160)
        self._selftest_btn.setFixedHeight(26)
        self._selftest_btn.setStyleSheet("background-color:#2a2a2a; color:#ffdd88; font-size:9pt;")
        self._selftest_btn.setToolTip(
            "Verify Nuke's listener port is reachable from localhost.\n"
            "If this fails, a firewall or port conflict is blocking the reply leg."
        )
        self._selftest_btn.clicked.connect(self._selftest_listener)
        diag_row.addWidget(self._selftest_btn)
        
        diag_row.addSpacing(20)
        self._build_proj_btn = QtWidgets.QPushButton("📽️ Build Projection Rig\u00A0\u00A0\u00A0\u00A0")
        self._build_proj_btn.setMinimumWidth(200)
        self._build_proj_btn.setFixedHeight(28)
        self._build_proj_btn.setStyleSheet("background-color:#4a2a4a; color:#ffaadd; font-size:9pt; font-weight:bold;")
        self._build_proj_btn.setToolTip("Generates a Project3D + Card rig using a frozen frame of the Live Camera for 2D paint-outs.")
        self._build_proj_btn.clicked.connect(self._build_projection_rig)
        self._build_proj_btn.hide()
        # diag_row.addWidget(self._build_proj_btn)
        
        diag_row.addStretch()
        live_layout.addLayout(diag_row)

        # Frame range + save server script row
        bot_row = QtWidgets.QHBoxLayout()
        bot_row.addWidget(QtWidgets.QLabel("Seq Range:", styleSheet="color:#aaa; font-size:9pt;"))
        self._live_frame_start = QtWidgets.QSpinBox()
        self._live_frame_start.setRange(0, 999999)
        self._live_frame_start.setValue(1001)
        self._live_frame_start.setFixedWidth(70)
        bot_row.addWidget(self._live_frame_start)
        bot_row.addWidget(QtWidgets.QLabel("–", styleSheet="color:#aaa;"))
        self._live_frame_end = QtWidgets.QSpinBox()
        self._live_frame_end.setRange(0, 999999)
        self._live_frame_end.setValue(1100)
        self._live_frame_end.setFixedWidth(70)
        bot_row.addWidget(self._live_frame_end)

        bot_row.addStretch()
        bot_row.addWidget(QtWidgets.QLabel("Server script:", styleSheet="color:#888; font-size:8pt;"))
        self._save_server_btn = QtWidgets.QPushButton("💾 Save Houdini Server Script\u00A0\u00A0\u00A0\u00A0")
        self._save_server_btn.setMinimumWidth(220)
        self._save_server_btn.setFixedHeight(28)
        self._save_server_btn.setStyleSheet("font-size:9pt; font-weight:bold;")
        self._save_server_btn.setToolTip("Save the live server script for the selected DCC to disk.")
        self._save_server_btn.clicked.connect(self._save_dcc_server_script)
        bot_row.addWidget(self._save_server_btn)
        live_layout.addLayout(bot_row)

        bottom_layout.addWidget(live_grp)

        # Internal live bridge state
        self._live_sender      = None
        self._live_listener    = None
        self._live_camera_node = None
        self._pending_full_rig = False   # set True by the one-click builder

        # Apply initial DCC-specific port
        self._on_dcc_changed(0)


    # ------------------------------------------------------------------ #
    # Live Pull Methods
    # ------------------------------------------------------------------ #

    # DCC port map: out-port auto-fill when selector changes
    _DCC_OUT_PORTS = {"Houdini": 7890, "Maya": 7891, "Blender": 7892}
    _DCC_COLORS    = {
        "Houdini": ("background-color:#1a2a3a; color:#ffa040;", "\U0001f7e0 Houdini"),
        "Maya":    ("background-color:#2a1a2a; color:#ff8fcc;", "\U0001f7e3 Maya"),
        "Blender": ("background-color:#1a1a2a; color:#a0a0ff;", "\U0001f535 Blender"),
    }

    def _on_dcc_changed(self, index: int):
        """Update out-port and button label when DCC selector changes."""
        dcc  = self._live_dcc_combo.currentText()
        port = self._DCC_OUT_PORTS.get(dcc, 7890)
        self._live_out_port.setValue(port)
        style, label = self._DCC_COLORS.get(dcc, ("", dcc))
        self._live_dcc_combo.setStyleSheet(style)
        self._save_server_btn.setText(f"\U0001f4be Save {dcc} Server Script")

    def _save_dcc_server_script(self):
        """Save the live server script for the selected DCC to disk."""
        import os, shutil
        dcc = self._live_dcc_combo.currentText()
        script_names = {
            "Houdini": "houdini_live_server.py",
            "Maya":    "maya_live_server.py",
            "Blender": "blender_live_server.py",
        }
        script_name = script_names.get(dcc)
        if not script_name:
            return
        src = os.path.join(os.path.dirname(os.path.abspath(__file__)), script_name)
        if not os.path.isfile(src):
            nuke.message(f"Server script not found:\n{src}")
            return
        dest = QtWidgets.QFileDialog.getSaveFileName(
            self,
            f"Save {dcc} Live Server Script",
            f"Crucible_{dcc}_LiveServer.py",
            "Python Files (*.py)",
        )[0]
        if not dest:
            return
        shutil.copy2(src, dest)
        nuke.message(f"{dcc} live server script saved to:\n{dest}")

    def _toggle_listener(self, checked: bool):
        """Start or stop Nuke's inbound listener."""
        if checked:
            port = self._live_in_port.value()
            self._live_listener = NukeLiveListener(port=port)
            self._live_listener.register(MSG_CAMERA_FRAME,    self._on_camera_frame)
            self._live_listener.register(MSG_CAMERA_SEQUENCE, self._on_camera_sequence)
            self._live_listener.register(MSG_SCENE_INFO,      self._on_scene_info)
            self._live_listener.register(MSG_PONG,            self._on_pong)
            self._live_listener.register("error",             self._on_error_message)
            ok = self._live_listener.start()
            if ok:
                self._listener_btn.setText("\U0001f7e2 Listener: ON")
                self._listener_btn.setStyleSheet(
                    "background-color:#1a3a1a; color:#6eff6e; font-weight:bold;"
                )
                self._listener_status.setText(
                    f"Listening on port {port}. Ready to receive from {self._live_dcc_combo.currentText()}."
                )
                self._listener_status.setStyleSheet("color:#6eff6e; font-size:8pt;")
            else:
                self._listener_btn.setChecked(False)
                self._listener_btn.setText("\U0001f534 Listener: OFF")
                self._listener_btn.setStyleSheet(
                    "background-color:#3a1a1a; color:#ff6b6b; font-weight:bold;"
                )
                self._listener_status.setText(f"Failed to bind port {port}.")
                self._listener_status.setStyleSheet("color:#ff6b6b; font-size:8pt;")
        else:
            if self._live_listener:
                self._live_listener.stop()
                self._live_listener = None
            self._listener_btn.setText("\U0001f534 Listener: OFF")
            self._listener_btn.setStyleSheet(
                "background-color:#3a1a1a; color:#ff6b6b; font-weight:bold;"
            )
            self._listener_status.setText("Listener stopped.")
            self._listener_status.setStyleSheet("color:#666; font-size:8pt; font-style:italic;")

    def _get_sender(self):
        """Return a connected NukeLiveSender for the configured host/port."""
        dcc  = self._live_dcc_combo.currentText()
        host = self._live_host_edit.text().strip() or "localhost"
        port = self._live_out_port.value()
        if (self._live_sender is None
                or self._live_sender.host != host
                or self._live_sender.port != port):
            self._live_sender = NukeLiveSender(host=host, port=port)
        if not self._live_sender.is_connected():
            ok = self._live_sender.connect()
            if not ok:
                self._listener_status.setText(
                    f"\u274c Cannot reach {dcc} at {host}:{port}. Is the LiveBridge server running?"
                )
                self._listener_status.setStyleSheet("color:#ff6b6b; font-size:8pt;")
                return None
        return self._live_sender

    def _ping_dcc(self):
        """Send a ping to the DCC and expect a pong back — tests the full round-trip."""
        if not self._ensure_listener_running():
            return
        sender = self._get_sender()
        if sender is None:
            return
        dcc = self._live_dcc_combo.currentText()
        sender.ping()
        self._listener_status.setText(f"Ping sent to {dcc}. Waiting for pong\u2026")
        self._listener_status.setStyleSheet("color:#f2a822; font-size:8pt;")
        print(f"[Crucible] PING sent to {dcc} on port {self._live_out_port.value()}")
        print(f"[Crucible] Nuke is listening for PONG on port {self._live_in_port.value()}")

    def _selftest_listener(self):
        """Connect to Nuke's own listener port from localhost to verify it's reachable."""
        import socket as _socket
        port = self._live_in_port.value()
        try:
            with _socket.create_connection(("127.0.0.1", port), timeout=2.0) as s:
                # Send a valid minimal framed message so the listener doesn't error
                import json
                payload = json.dumps({"type": "ping", "selftest": True}).encode("utf-8")
                s.sendall(len(payload).to_bytes(4, "big") + payload)
            self._listener_status.setText(
                f"\u2705 Port {port} reachable locally \u2014 listener is working correctly."
            )
            self._listener_status.setStyleSheet("color:#6eff6e; font-size:8pt;")
            print(f"[Crucible] Self-test: Nuke listener on port {port} is reachable.")
        except OSError as e:
            self._listener_status.setText(
                f"\u274c Port {port} NOT reachable: {e}\n"
                f"A firewall may be blocking loopback connections."
            )
            self._listener_status.setStyleSheet("color:#ff6b6b; font-size:8pt;")
            print(f"[Crucible] Self-test FAILED for port {port}: {e}")
            nuke.message(
                f"Crucible Listener Self-Test FAILED\n\n"
                f"Port {port} is not reachable even from localhost.\n"
                f"Error: {e}\n\n"
                f"Steps to fix:\n"
                f"1. Check Windows Firewall is not blocking TCP port {port}\n"
                f"2. Make sure no other application is using port {port}\n"
                f"3. Try changing the In Port to a different number (e.g. 7894)\n"
                f"4. Restart Nuke and re-enable the listener"
            )

    def _ensure_listener_running(self) -> bool:
        """Auto-start the listener if not already running."""
        if self._live_listener and self._live_listener.is_running:
            return True
        self._listener_btn.setChecked(True)
        self._toggle_listener(True)
        return self._live_listener is not None and self._live_listener.is_running

    def _pull_camera_live(self):
        """Request current-frame camera data from the active DCC via live link."""
        if not self._ensure_listener_running():
            return
        sender = self._get_sender()
        if sender is None:
            return
        dcc = self._live_dcc_combo.currentText()
        sender.request_camera()
        self._listener_status.setText(f"Camera request sent \u2014 waiting for {dcc}\u2026")
        self._listener_status.setStyleSheet("color:#f2a822; font-size:8pt;")

    def _pull_camera_sequence_live(self):
        """Request full camera sequence from the active DCC via live link."""
        if not self._ensure_listener_running():
            return
        sender = self._get_sender()
        if sender is None:
            return
        dcc = self._live_dcc_combo.currentText()
        frame_range = (self._live_frame_start.value(), self._live_frame_end.value())
        sender.request_camera(frame_range=frame_range)
        self._listener_status.setText(
            f"Camera sequence request sent ({frame_range[0]}\u2013{frame_range[1]}) from {dcc} \u2014 waiting\u2026"
        )
        self._listener_status.setStyleSheet("color:#f2a822; font-size:8pt;")

    def _pull_scene_live(self):
        """Request scene info from the active DCC via live link."""
        if not self._ensure_listener_running():
            return
        sender = self._get_sender()
        if sender is None:
            return
        dcc = self._live_dcc_combo.currentText()
        sender.request_scene()
        self._listener_status.setText(f"Scene info request sent \u2014 waiting for {dcc}\u2026")
        self._listener_status.setStyleSheet("color:#f2a822; font-size:8pt;")

    # ------------------------------------------------------------------ #
    # One-Click 3D Scene Builder
    # ------------------------------------------------------------------ #

    def _one_click_build_3d_scene(self):
        """One-click: Pull full camera sequence then auto-build the complete 3D rig."""
        if not self._ensure_listener_running():
            return
        sender = self._get_sender()
        if sender is None:
            return
        dcc = self._live_dcc_combo.currentText()
        frame_range = (self._live_frame_start.value(), self._live_frame_end.value())
        # Set the flag BEFORE the request so the callback knows what to do
        self._pending_full_rig = True
        sender.request_camera(frame_range=frame_range)
        self._listener_status.setText(
            f"⏳ Building Live 3D Scene — pulling {dcc} camera "
            f"({frame_range[0]}–{frame_range[1]}) …"
        )
        self._listener_status.setStyleSheet("color:#f2a822; font-size:9pt; font-weight:bold;")

    def _build_nuke_3d_scene(self, cam_node):
        """Lightweight 3D setup used by the basic Pull Camera buttons (not the one-click builder)."""
        import nuke
        # Only build if the camera isn't already connected to anything
        if len(cam_node.dependent()) > 0:
            return
        cx = cam_node.xpos()
        cy = cam_node.ypos()
        scene   = nuke.nodes.Scene(xpos=cx - 150, ypos=cy)
        bg      = nuke.nodes.CheckerBoard2(xpos=cx + 150, ypos=cy - 100)
        scanline = nuke.nodes.ScanlineRender(xpos=cx, ypos=cy + 150)
        scanline.setInput(0, bg)
        scanline.setInput(1, scene)
        scanline.setInput(2, cam_node)

    def _build_full_3d_scene(self, cam_node):
        """Build the complete professional 3D compositing rig around cam_node.

        Layout (top → bottom, left → right):

          [BG Plate / CheckerBoard]        [proj_cam]  (frozen camera)
                   |                            |
          [RotoPaint / Paint Layer]  → [Project3D]
                                           |
          [Scene] ←────────────────── [Card2]
             ↑
          [ScanlineRender]  ←  [cam_node]  (animated live camera)
        """
        import nuke

        dcc  = self._live_dcc_combo.currentText()
        f    = nuke.frame()
        cx   = cam_node.xpos()
        cy   = cam_node.ypos()

        with nuke.Undo("Crucible: Build Full 3D Scene"):

            # ── 1. Background plate or CheckerBoard ────────────────────
            bg_node = None
            try:
                sel = nuke.selectedNode()
                if sel.Class() == "Read":
                    bg_node = sel
            except ValueError:
                pass

            if bg_node is None:
                bg_node = nuke.nodes.CheckerBoard2(
                    name="crucible_bg",
                    xpos=cx - 400,
                    ypos=cy - 200,
                )
                bg_node["label"].setValue("Background\n(replace with Read)")
                bg_node["tile_color"].setValue(0x222233FF)
            else:
                # Clone so the original Read isn't moved
                clone = nuke.nodes.Read(
                    name="crucible_bg_plate",
                    xpos=cx - 400,
                    ypos=cy - 200,
                )
                clone["file"].setValue(bg_node["file"].value())
                clone["first"].setValue(bg_node["first"].value())
                clone["last"].setValue(bg_node["last"].value())
                clone["label"].setValue("BG Plate (Live Bridge)")
                bg_node = clone

            # ── 2. RotoPaint for paint-outs ────────────────────────────
            roto = nuke.nodes.RotoPaint(
                name="crucible_paintout",
                xpos=cx - 150,
                ypos=cy - 200,
            )
            roto.setInput(0, bg_node)
            roto["label"].setValue("🎨 Paint / Clean Plate\nDraw over area to remove")
            roto["tile_color"].setValue(0x664422FF)

            # ── 3. Frozen projection camera ────────────────────────────
            proj_cam = nuke.nodes.Camera2(
                name=f"crucible_proj_cam_f{int(f)}",
                xpos=cx + 250,
                ypos=cy - 200,
            )
            proj_cam["label"].setValue(f"📷 Frozen @ frame {int(f)}\n(Projection Cam)")
            proj_cam["tile_color"].setValue(0x224422FF)
            for kn in ("translate", "rotate", "focal", "haperture",
                       "vaperture", "focaldist", "fstop", "win_translate"):
                src_k = cam_node.knob(kn)
                dst_k = proj_cam.knob(kn)
                if src_k and dst_k:
                    try:
                        dst_k.setValue(src_k.getValueAt(f))
                    except Exception:
                        pass

            # ── 4. Project3D ───────────────────────────────────────────
            proj3d = nuke.nodes.Project3D(
                name="crucible_project3d",
                xpos=cx + 100,
                ypos=cy - 100,
            )
            proj3d["label"].setValue("Project3D\n(Paints onto Card)")
            proj3d["tile_color"].setValue(0x334455FF)
            proj3d.setInput(0, roto)
            proj3d.setInput(1, proj_cam)

            # ── 5. Card2 in 3D space ───────────────────────────────────
            card = nuke.nodes.Card2(
                name="crucible_card",
                xpos=cx + 100,
                ypos=cy,
            )
            card["label"].setValue("🃏 Move me in Z to place\npaint in world space")
            card["tile_color"].setValue(0x443344FF)
            card.setInput(0, proj3d)

            # ── 6. Scene node (collect 3D objects) ─────────────────────
            scene = nuke.nodes.Scene(
                name="crucible_scene",
                xpos=cx - 150,
                ypos=cy + 50,
            )
            scene["label"].setValue("3D Scene")
            scene["tile_color"].setValue(0x334433FF)
            scene.setInput(0, card)   # card projects onto itself; add more objects via extra inputs

            # ── 7. ScanlineRender (final composite) ────────────────────
            slr = nuke.nodes.ScanlineRender(
                name="crucible_scanline",
                xpos=cx - 150,
                ypos=cy + 200,
            )
            slr["label"].setValue("ScanlineRender\n[Crucible 3D]")
            slr["tile_color"].setValue(0x222244FF)
            slr.setInput(0, bg_node)   # background plate
            slr.setInput(1, scene)     # 3D objects
            slr.setInput(2, cam_node)  # animated live camera

            # ── 8. Backdrop for organisation ───────────────────────────
            all_nodes = [bg_node, roto, proj_cam, proj3d, card, scene, slr, cam_node]
            xs = [n.xpos() for n in all_nodes]
            ys = [n.ypos() for n in all_nodes]
            pad = 80
            bd = nuke.nodes.BackdropNode(
                xpos=min(xs) - pad,
                ypos=min(ys) - pad - 60,
                bdwidth=max(xs) - min(xs) + 180 + pad * 2,
                bdheight=max(ys) - min(ys) + 120 + pad * 2,
                label=(
                    f"<b><font color='#aaddff' size=5>⚡ Crucible Live 3D Scene</font></b>\n"
                    f"<font color='#888888' size=3>Camera: {cam_node.name()} | "
                    f"DCC: {dcc} | Built frame {int(f)}</font>"
                ),
                note_font_size=14,
            )
            bd["tile_color"].setValue(0x1a1a2aFF)
            bd["z_order"].setValue(0)

        nuke.message(
            f"[Crucible] ⚡ Live 3D Scene Built!\n\n"
            f"Camera  : {cam_node.name()}  (from {dcc})\n"
            f"Frames  : {self._live_frame_start.value()} – {self._live_frame_end.value()}\n"
            f"Bg Plate: {bg_node.name()}\n\n"
            f"Next steps:\n"
            f"  1. Select the RotoPaint node and paint over the area you want to remove.\n"
            f"  2. Select the Card (crucible_card) and move it in Z-space so it sits\n"
            f"     at the depth of your object (use the 3D viewer).\n"
            f"  3. View the ScanlineRender to see the final result.\n\n"
            f"The paint projection is locked to frame {int(f)} of the camera."
        )

    def _build_projection_rig(self):
        """Builds a Project3D projection rig from the Live Camera for paint cleanup."""
        import nuke
        
        cam = self._live_camera_node
        
        # Fallback 1: Try the currently selected node
        if not cam:
            try:
                sel = nuke.selectedNode()
                if sel.Class() in ("Camera", "Camera2", "Camera3", "Camera4"):
                    cam = sel
            except ValueError:
                pass
                
        # Fallback 2: Search the node graph for any node starting with 'crucible_live_'
        if not cam:
            for node in nuke.allNodes():
                if node.Class() in ("Camera", "Camera2", "Camera3", "Camera4") and node.name().startswith("crucible_live_"):
                    cam = node
                    break
        
        if not cam:
            nuke.message("[Crucible] No Live Camera found.\n\nPlease select your camera node or pull one from Houdini first!")
            return
            
        cx = cam.xpos()
        cy = cam.ypos()
        
        with nuke.Undo("Crucible: Build Projection Rig"):
            f = nuke.frame()
            
            # Build frozen projection camera
            freeze_cam = nuke.nodes.Camera2(name=f"proj_cam_{int(f)}", xpos=cx + 250, ypos=cy - 50)
            freeze_cam["label"].setValue(f"Frozen at frame {f}\n(Projection)")
            
            # Copy values at current frame
            for kn in ("translate", "rotate", "focal", "haperture", "vaperture", "focaldist", "fstop"):
                if cam.knob(kn) and freeze_cam.knob(kn):
                    freeze_cam[kn].setValue(cam[kn].getValueAt(f))
            
            # Project3D
            proj = nuke.nodes.Project3D(xpos=cx + 250, ypos=cy + 50)
            proj.setInput(1, freeze_cam)
            
            # RotoPaint
            roto = nuke.nodes.RotoPaint(xpos=cx + 250, ypos=cy - 120)
            roto["label"].setValue("Paint / Clean Plate")
            proj.setInput(0, roto)
            
            # Card
            card = nuke.nodes.Card2(xpos=cx + 250, ypos=cy + 150)
            card.setInput(0, proj)
            card["label"].setValue("Move this Card\nin Z-Space")
            
            nuke.message(
                f"[Crucible] Projection Rig built for Frame {int(f)}!\n\n"
                "1. Connect the RotoPaint node to your background plate.\n"
                "2. Move the Card in Z-space to where the object lives.\n"
                "3. Connect the Card into your Scene node.\n\n"
                "Because the Scene is filmed by the Live Camera, your paint will stick perfectly!"
            )

    # ---- Incoming message handlers (fired on Nuke main thread via updateUI) ---

    def _on_camera_frame(self, msg: dict):
        """DCC pushed a single camera frame \u2014 apply/create Camera2 node."""
        try:
            from .dcc_bridges.camera_exchange import _set_key
            source_dcc = msg.get("source_dcc", self._live_dcc_combo.currentText()).title()
            cam_name = msg.get("name", "dcc_cam")
            node_name = f"crucible_live_{cam_name}"
            existing = nuke.toNode(node_name)
            if existing is None:
                with nuke.Undo("Crucible: Live Camera"):
                    existing = nuke.nodes.Camera2(name=node_name)
                    existing["label"].setValue(f"[Crucible] Live {source_dcc} Camera")
            self._live_camera_node = existing
            self._build_nuke_3d_scene(existing)
            frame = float(msg.get("frame", nuke.frame()))
            _set_key(existing, "translate", frame, msg.get("translate", [0, 0, 0]))
            _set_key(existing, "rotate",    frame, msg.get("rotate",    [0, 0, 0]))
            if msg.get("focal_length_mm"):
                _set_key(existing, "focal",     frame, msg["focal_length_mm"])
            if msg.get("haperture_mm"):
                _set_key(existing, "haperture", frame, msg["haperture_mm"])
            if msg.get("vaperture_mm"):
                _set_key(existing, "vaperture", frame, msg["vaperture_mm"])
            if msg.get("focus_distance"):
                _set_key(existing, "focaldist", frame, msg["focus_distance"])
            self._listener_status.setText(
                f"\u2705 Camera frame {int(frame)} received from {source_dcc}."
            )
            self._listener_status.setStyleSheet("color:#2ecc71; font-size:8pt;")
        except Exception as exc:
            self._listener_status.setText(f"\u274c Camera frame error: {exc}")
            self._listener_status.setStyleSheet("color:#e74c3c; font-size:8pt;")

    def _on_camera_sequence(self, msg: dict):
        """DCC pushed a full camera sequence \u2014 build animated Camera2 node."""
        try:
            from .dcc_bridges.camera_exchange import _set_key
            source_dcc = msg.get("source_dcc", self._live_dcc_combo.currentText()).title()
            cam_name = msg.get("name", "dcc_cam")
            frames   = msg.get("frames", [])
            if not frames:
                self._listener_status.setText("\u26a0 Camera sequence: no frames received.")
                return
            node_name = f"crucible_live_{cam_name}"
            existing  = nuke.toNode(node_name)
            with nuke.Undo("Crucible: Live Camera Sequence"):
                if existing is None:
                    existing = nuke.nodes.Camera2(name=node_name)
                    existing["label"].setValue(
                        f"[Crucible] Live {source_dcc}  |  {len(frames)} frames"
                    )
                self._live_camera_node = existing
                _should_build_full_rig = self._pending_full_rig
                if self._pending_full_rig:
                    self._pending_full_rig = False
                    # Full rig build happens AFTER all keyframes are set (at end of this method)
                cam = existing
                for kn in ("translate", "rotate", "focal", "haperture",
                           "vaperture", "focaldist", "fstop"):
                    k = cam.knob(kn)
                    if k:
                        try:
                            k.setAnimated()
                        except Exception:
                            pass
                for frec in frames:
                    f = float(frec.get("frame", 0))
                    _set_key(cam, "translate", f, frec.get("translate", [0, 0, 0]))
                    _set_key(cam, "rotate",    f, frec.get("rotate",    [0, 0, 0]))
                    if frec.get("focal_length_mm"):
                        _set_key(cam, "focal",     f, frec["focal_length_mm"])
                    if frec.get("haperture_mm"):
                        _set_key(cam, "haperture", f, frec["haperture_mm"])
                    if frec.get("vaperture_mm"):
                        _set_key(cam, "vaperture", f, frec["vaperture_mm"])
                    if frec.get("focus_distance"):
                        _set_key(cam, "focaldist", f, frec["focus_distance"])
            shot = msg.get("shot", {})
            if _should_build_full_rig:
                self._build_full_3d_scene(existing)
                self._listener_status.setText(
                    f"\u26a1 Live 3D Scene built! Camera '{cam_name}' from {source_dcc}: {len(frames)} frames "
                    f"({shot.get('frame_start','?')}\u2013{shot.get('frame_end','?')})."
                )
                self._listener_status.setStyleSheet("color:#a0ddff; font-size:9pt; font-weight:bold;")
            else:
                self._build_nuke_3d_scene(existing)
                self._listener_status.setText(
                    f"\u2705 {source_dcc} camera '{cam_name}': {len(frames)} frames "
                    f"({shot.get('frame_start','?')}\u2013{shot.get('frame_end','?')}) received."
                )
                self._listener_status.setStyleSheet("color:#2ecc71; font-size:8pt;")
        except Exception as exc:
            self._listener_status.setText(f"❌ Camera sequence error: {exc}")
            self._listener_status.setStyleSheet("color:#e74c3c; font-size:8pt;")
            import traceback; traceback.print_exc()

    def _on_scene_info(self, msg: dict):
        """Houdini pushed a scene snapshot \u2014 display summary and sync settings."""
        try:
            n_lights = len(msg.get("lights", []))
            shot     = msg.get("shot", {})
            f_start  = shot.get('frame_start')
            f_end    = shot.get('frame_end')
            fps      = shot.get('fps')

            # Synchronize the UI and Nuke root settings if we got valid frame ranges
            if f_start is not None and f_end is not None:
                self._live_frame_start.setValue(int(f_start))
                self._live_frame_end.setValue(int(f_end))
                
                try:
                    import nuke
                    nuke.root()["first_frame"].setValue(int(f_start))
                    nuke.root()["last_frame"].setValue(int(f_end))
                    if fps:
                        nuke.root()["fps"].setValue(float(fps))
                except Exception:
                    pass

            # Update the Light Mixer if we have live lights
            lights_data = msg.get("lights", [])
            if lights_data:
                found = False
                p = self.parent()
                while p:
                    if hasattr(p, "mixer_tab") and hasattr(p.mixer_tab, "_on_live_lights"):
                        p.mixer_tab._on_live_lights(lights_data)
                        found = True
                        break
                    p = p.parent()
                
                if not found:
                    for w in QtWidgets.QApplication.allWidgets():
                        if type(w).__name__ == "LightMixerWidget" and hasattr(w, "_on_live_lights"):
                            w._on_live_lights(lights_data)
                            break

            self._listener_status.setText(
                f"\u2705 Scene: {n_lights} lights  |  "
                f"{f_start or '?'}\u2013{f_end or '?'} "
                f"@ {fps or '?'}fps. (Nuke settings synced!)"
            )
            self._listener_status.setStyleSheet("color:#2ecc71; font-size:8pt;")
        except Exception as exc:
            self._listener_status.setText(f"\u274c Scene info error: {exc}")
            self._listener_status.setStyleSheet("color:#e74c3c; font-size:8pt;")

    def _on_pong(self, msg: dict):
        """Received heartbeat pong from DCC."""
        source_dcc = msg.get("source_dcc", self._live_dcc_combo.currentText()).title()
        self._listener_status.setText(f"\U0001f493 {source_dcc} heartbeat OK.")
        self._listener_status.setStyleSheet("color:#2ecc71; font-size:8pt;")

    def _on_error_message(self, msg: dict):
        """Houdini encountered an error and reported it back to Nuke."""
        error_text = msg.get("message", "Unknown error")
        self._listener_status.setText(f"\u274c DCC Error: {error_text}")
        self._listener_status.setStyleSheet("color:#ff6b6b; font-weight:bold; font-size:8pt;")
        nuke.message(f"Crucible LiveBridge Error:\n\n{error_text}")

    # ------------------------------------------------------------------ #
    # Pass Manager Actions
    # ------------------------------------------------------------------ #

    def _scan_node(self):
        """Parse the selected node and populate the pass table."""
        try:
            node = nuke.selectedNode()
        except ValueError:
            nuke.message("Crucible Pass Manager: Please select a node.")
            return

        try:
            self._manifest = self._manager.build_manifest(node)
        except Exception as exc:
            nuke.message(f"Crucible Pass Manager: Failed to parse node.\n{exc}")
            return

        self._populate_table()

        renderer = self._manifest.renderer.value.title()
        n_passes = len(self._manifest.all_passes)
        n_lgs    = len(self._manifest.light_groups)
        self._status_lbl.setText(
            f"Renderer: {renderer}  |  "
            f"{n_passes} passes  |  "
            f"{n_lgs} light groups  |  "
            f"Node: {node.name()}"
        )
        self._status_lbl.setStyleSheet("color:#2ecc71; font-size:9pt;")

    def _validate(self):
        """Validate the current manifest and colour the table rows."""
        if self._manifest is None:
            nuke.message("Crucible Pass Manager: Scan a node first.")
            return

        schema_idx  = self._schema_combo.currentIndex()
        schema_name = None if schema_idx == 0 else self._schema_combo.currentText()

        result = self._manager.validate(self._manifest, schema_name=schema_name)
        self._populate_table()  # refresh with updated status flags

        summary = result["summary"]
        req_miss = result["required_missing"]
        rec_miss = result["recommended_missing"]

        detail = summary
        if req_miss:
            detail += f"\n\nMissing required passes:\n" + "\n".join(f"  • {p}" for p in req_miss)
        if rec_miss:
            detail += f"\n\nMissing recommended passes:\n" + "\n".join(f"  • {p}" for p in rec_miss)

        color = "#2ecc71" if not req_miss else "#e74c3c"
        self._status_lbl.setText(summary)
        self._status_lbl.setStyleSheet(f"color:{color}; font-size:9pt;")

        if req_miss or rec_miss:
            nuke.message(f"Crucible Pass Validation ({result['schema']})\n\n{detail}")

    def _auto_route(self):
        """Auto-route all passes as Shuffle2 nodes in the DAG."""
        if self._manifest is None:
            nuke.message("Crucible Pass Manager: Scan a node first.")
            return
        try:
            node = nuke.toNode(self._manifest.source_node_name)
            if node is None:
                raise RuntimeError(f"Source node '{self._manifest.source_node_name}' no longer exists.")
            created = self._manager.auto_route(self._manifest, node)
            nuke.message(
                f"Crucible Pass Manager: Created {len(created)} Shuffle nodes.\n"
                f"Passes are organised into labelled backdrops."
            )
        except Exception as exc:
            nuke.message(f"Crucible Pass Manager: Auto-Route failed.\n{exc}")

    def _export_manifest(self):
        """Export the current manifest as a JSON file."""
        if self._manifest is None:
            nuke.message("Crucible Pass Manager: Nothing to export. Scan a node first.")
            return
        path = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save Pass Manifest", "", "JSON Files (*.json)"
        )[0]
        if not path:
            return
        try:
            self._manager.export_manifest(self._manifest, path)
            nuke.message(f"Pass manifest saved to:\n{path}")
        except Exception as exc:
            nuke.message(f"Failed to save manifest:\n{exc}")

    def _diff_manifests(self):
        """Load two manifest JSONs and show a diff report."""
        path_a = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select Manifest A", "", "JSON Files (*.json)"
        )[0]
        if not path_a:
            return
        path_b = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select Manifest B", "", "JSON Files (*.json)"
        )[0]
        if not path_b:
            return
        try:
            data_a = self._manager.load_manifest_from_json(path_a)
            data_b = self._manager.load_manifest_from_json(path_b)
        except Exception as exc:
            nuke.message(f"Failed to load manifests:\n{exc}")
            return

        passes_a = {p["standard_name"] for p in data_a.get("passes", [])}
        passes_b = {p["standard_name"] for p in data_b.get("passes", [])}
        only_a   = sorted(passes_a - passes_b)
        only_b   = sorted(passes_b - passes_a)
        shared   = sorted(passes_a & passes_b)

        rend_a = data_a.get("renderer", "?")
        rend_b = data_b.get("renderer", "?")

        lines = [
            f"Renderer A: {rend_a}   |   Renderer B: {rend_b}",
            f"Shared passes: {len(shared)}",
        ]
        if only_a:
            lines.append("\nOnly in A:\n" + "\n".join(f"  • {p}" for p in only_a))
        if only_b:
            lines.append("\nOnly in B:\n" + "\n".join(f"  • {p}" for p in only_b))
        if not only_a and not only_b:
            lines.append("\n✅  Manifests are identical.")

        nuke.message("Pass Manifest Diff\n\n" + "\n".join(lines))

    def _import_camera(self):
        """Import a Crucible Universal Camera JSON into Nuke."""
        path = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open Crucible Camera JSON", "", "JSON Files (*.json)"
        )[0]
        if not path:
            return
        try:
            import_camera_from_json(path)
        except Exception as exc:
            nuke.message(f"Camera import failed:\n{exc}")

    def _import_scene(self):
        """Import a Crucible Universal Scene JSON and display a summary."""
        path = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open Crucible Scene JSON", "", "JSON Files (*.json)"
        )[0]
        if not path:
            return
        try:
            data = import_scene_from_json(path)
        except Exception as exc:
            nuke.message(f"Scene import failed:\n{exc}")
            return

        dcc      = data.get("source_dcc", "unknown").title()
        renderer = data.get("source_renderer", "unknown").title()
        n_lights = len(data.get("lights", []))
        n_passes = len(data.get("passes", []))
        shot     = data.get("shot", {})
        rs       = data.get("render_settings", {})

        lines = [
            f"Source DCC: {dcc}   Renderer: {renderer}",
            f"Frame Range: {shot.get('frame_start', '?')} – {shot.get('frame_end', '?')}",
            f"FPS: {shot.get('fps', '?')}",
            f"Resolution: {rs.get('resolution_x', '?')} × {rs.get('resolution_y', '?')}",
            f"Color Space: {rs.get('color_space', '?')}",
            f"Lights found: {n_lights}",
            f"Passes declared: {n_passes}",
        ]
        nuke.message("Crucible Scene Import\n\n" + "\n".join(lines))

    def _diff_render_settings(self):
        """Compare render settings between two scene JSON files."""
        path_a = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select Scene JSON A", "", "JSON Files (*.json)"
        )[0]
        if not path_a:
            return
        path_b = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select Scene JSON B", "", "JSON Files (*.json)"
        )[0]
        if not path_b:
            return
        try:
            mismatches = diff_render_settings(path_a, path_b)
        except Exception as exc:
            nuke.message(f"Diff failed:\n{exc}")
            return

        if not mismatches:
            nuke.message("✅  Render settings are identical between both scenes.")
        else:
            msg = "Render Settings Mismatches:\n\n" + "\n".join(f"• {m}" for m in mismatches)
            nuke.message(msg)

    def _make_save_companion(self, dcc: str):
        """Return a closure that saves the companion exporter script for a DCC."""
        def _save():
            import os
            src_dir = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "dcc_bridges"
            )
            src_file = os.path.join(src_dir, f"{dcc}_exporter.py")
            if not os.path.isfile(src_file):
                nuke.message(f"Companion script not found:\n{src_file}")
                return
            dest = QtWidgets.QFileDialog.getSaveFileName(
                self,
                f"Save {dcc.title()} Companion Script",
                f"Crucible_{dcc.title()}_Exporter.py",
                "Python Files (*.py)",
            )[0]
            if not dest:
                return
            import shutil
            shutil.copy2(src_file, dest)
            nuke.message(f"{dcc.title()} companion script saved to:\n{dest}")
        return _save

    # ------------------------------------------------------------------ #
    # Table Population
    # ------------------------------------------------------------------ #

    def _populate_table(self):
        """Fill the pass table from the current manifest."""
        if self._manifest is None:
            return

        passes = self._manifest.all_passes
        self._table.setRowCount(0)
        self._table.setRowCount(len(passes))

        for row, rec in enumerate(passes):
            # DCC layer name
            item0 = QtWidgets.QTableWidgetItem(rec.original_name)
            item0.setToolTip("\n".join(rec.full_channel_names))
            self._table.setItem(row, 0, item0)

            # Crucible standard name
            item1 = QtWidgets.QTableWidgetItem(rec.standard_name)
            self._table.setItem(row, 1, item1)

            # Category
            cat_label = rec.category.name.replace("_", " ").title()
            if rec.light_group:
                cat_label = f"LG: {rec.light_group}"
            item2 = QtWidgets.QTableWidgetItem(cat_label)
            item2.setTextAlignment(QtCore.Qt.AlignCenter)
            self._table.setItem(row, 2, item2)

            # Channel count
            item3 = QtWidgets.QTableWidgetItem(str(len(rec.suffixes)))
            item3.setTextAlignment(QtCore.Qt.AlignCenter)
            self._table.setItem(row, 3, item3)

            # Status badge
            status_text = rec.status.upper()
            item4 = QtWidgets.QTableWidgetItem(status_text)
            item4.setTextAlignment(QtCore.Qt.AlignCenter)
            color = self._STATUS_COLORS.get(rec.status, "#aaaaaa")
            item4.setForeground(QtGui.QColor(color))
            self._table.setItem(row, 4, item4)

            # Row background for missing passes
            if rec.status == PassStatus.MISSING:
                for col in range(5):
                    it = self._table.item(row, col)
                    if it:
                        it.setBackground(QtGui.QColor("#2a1010"))
            elif rec.status == PassStatus.WARNING:
                for col in range(5):
                    it = self._table.item(row, col)
                    if it:
                        it.setBackground(QtGui.QColor("#2a2010"))

        self._table.resizeRowsToContents()


# ---------------------------------------------------------------------------
# Main Unified Panel
# ---------------------------------------------------------------------------

class CrucibleUnifiedPanel(QtWidgets.QWidget):
    """The main unified Crucible panel containing all tools."""

    def __init__(self, parent=None):
        super(CrucibleUnifiedPanel, self).__init__(parent)
        self.setObjectName("CrucibleUnifiedPanel")
        self.setStyleSheet(CRUCIBLE_STYLESHEET)
        
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        self.tabs = QtWidgets.QTabWidget()
        
        self.mixer_tab = LightMixerWidget()
        self.tabs.addTab(self.mixer_tab, "🎛 AOV & Light Mixer\u00A0\u00A0\u00A0\u00A0")
        
        self.util_tab = CGUtilitiesWidget()
        self.tabs.addTab(self.util_tab, "🛠 CG Utilities\u00A0\u00A0\u00A0\u00A0")
        
        self.qc_tab = RenderQCWidget()
        self.tabs.addTab(self.qc_tab, "🔬 Render QC\u00A0\u00A0\u00A0\u00A0")
        
        self.lens_tab = LensIntegrationWidget()
        self.tabs.addTab(self.lens_tab, "🎥 Lens & Integration\u00A0\u00A0\u00A0\u00A0")
        
        self.pipeline_tab = PipelineToolsWidget()
        self.tabs.addTab(self.pipeline_tab, "🚀 Pipeline Tools\u00A0\u00A0\u00A0\u00A0")
        
        self.deep_tab = DeepToolsWidget()
        self.tabs.addTab(self.deep_tab, "🌌 Deep Tools\u00A0\u00A0\u00A0\u00A0")

        self.pass_manager_tab = PassManagerWidget()
        self.tabs.addTab(self.pass_manager_tab, "📊 Pass Manager\u00A0\u00A0\u00A0\u00A0")


        layout.addWidget(self.tabs)
        
        # ── Cross-Tab Sync & Persistence ──
        settings = QtCore.QSettings("Crucible", "CrucibleLiveLink")
        
        def _sync_dcc_combo(index, source_combo, target_combo):
            if target_combo.currentIndex() != index:
                target_combo.blockSignals(True)
                target_combo.setCurrentIndex(index)
                target_combo.blockSignals(False)
                
                # Ensure the port updates explicitly via the tab's methods
                if target_combo == self.pass_manager_tab._live_dcc_combo:
                    self.pass_manager_tab._on_dcc_changed(index)
                elif target_combo == self.mixer_tab._mixer_dcc_combo:
                    self.mixer_tab._on_mixer_dcc_changed(index)
                    
            settings.setValue("last_dcc", source_combo.currentText())
            
        self.mixer_tab._mixer_dcc_combo.currentIndexChanged.connect(
            lambda idx: _sync_dcc_combo(idx, self.mixer_tab._mixer_dcc_combo, self.pass_manager_tab._live_dcc_combo)
        )
        self.pass_manager_tab._live_dcc_combo.currentIndexChanged.connect(
            lambda idx: _sync_dcc_combo(idx, self.pass_manager_tab._live_dcc_combo, self.mixer_tab._mixer_dcc_combo)
        )
        
        last_dcc = settings.value("last_dcc", "Houdini")
        idx = self.mixer_tab._mixer_dcc_combo.findText(last_dcc)
        if idx >= 0:
            self.mixer_tab._mixer_dcc_combo.setCurrentIndex(idx)
            
        # Sync Live Link state
        def _sync_mixer_to_pass_manager():
            if self.mixer_tab._live_btn.isChecked() != self.pass_manager_tab._listener_btn.isChecked():
                self.pass_manager_tab._listener_btn.setChecked(self.mixer_tab._live_btn.isChecked())
                self.pass_manager_tab._toggle_listener(self.mixer_tab._live_btn.isChecked())
                
        def _sync_pass_manager_to_mixer():
            if self.pass_manager_tab._listener_btn.isChecked() != self.mixer_tab._live_btn.isChecked():
                self.mixer_tab._live_btn.setChecked(self.pass_manager_tab._listener_btn.isChecked())
                self.mixer_tab._toggle_live_link()
                
        self.mixer_tab._live_btn.clicked.connect(_sync_mixer_to_pass_manager)
        self.pass_manager_tab._listener_btn.clicked.connect(_sync_pass_manager_to_mixer)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def show_unified_panel():
    """Show the panel as a floating window (useful for testing)."""
    global crucible_panel
    crucible_panel = CrucibleUnifiedPanel()
    crucible_panel.show()


class CruciblePanelWrapper(nukescripts.PythonPanel):
    """Wrapper to make the PySide widget dockable in Nuke."""
    def __init__(self):
        super(CruciblePanelWrapper, self).__init__('Crucible', 'com.crucible.unified')
        self.custom_knob = nuke.PyCustom_Knob("CrucibleUI", "", "CrucibleUnifiedPanel()")
        self.addKnob(self.custom_knob)

def register_unified_panel():
    """Register the unified PySide panel as a dockable Nuke panel."""
    # Register the widget class so Nuke can instantiate it
    sys.modules['__main__'].CrucibleUnifiedPanel = CrucibleUnifiedPanel
    nukescripts.registerWidgetAsPanel(
        'CrucibleUnifiedPanel',
        'Crucible',
        'com.crucible.unified'
    )
