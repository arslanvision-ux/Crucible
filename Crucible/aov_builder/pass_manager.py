"""
Crucible — Universal AOV Pass Manager.

Normalises multi-pass EXR channel naming across all supported DCCs
(Arnold, Karma, Cycles, Redshift) to a single Crucible-
standard schema.  Provides pass-validation, missing-pass detection,
beauty-reconstruction verification, and a visual pass-routing map.

Key concepts
------------
* ``PassRecord``  — one normalised pass entry with DCC-original name +
                    Crucible-standard name + AOVType + status flags.
* ``PassManifest`` — the full parsed result for one EXR / Read node.
* ``PassManager``  — stateless helper that builds manifests, validates
                     them against JSON schemas, and builds Nuke node
                     graphs for any channel set.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from ..constants import (
    AOVType,
    AOVCategory,
    Renderer,
    ADDITIVE_REBUILD_ORDER,
    UTILITY_AOV_TYPES,
)
from .channel_parser import parse_channels, ParsedChannels, ChannelLayer
from .presets import RENDERER_PRESETS, get_preset


# ---------------------------------------------------------------------------
# Crucible-Standard AOV Name Table
#
# This is the canonical naming for all passes inside Crucible regardless
# of source DCC.  All display labels, validation schemas, and JSON export
# use these strings.
# ---------------------------------------------------------------------------

CRUCIBLE_STANDARD_NAMES: Dict[AOVType, str] = {
    AOVType.BEAUTY:                "beauty",
    AOVType.DIFFUSE:               "diffuse",
    AOVType.DIFFUSE_DIRECT:        "diffuse_direct",
    AOVType.DIFFUSE_INDIRECT:      "diffuse_indirect",
    AOVType.DIFFUSE_FILTER:        "diffuse_albedo",
    AOVType.SPECULAR:              "specular",
    AOVType.SPECULAR_DIRECT:       "specular_direct",
    AOVType.SPECULAR_INDIRECT:     "specular_indirect",
    AOVType.SSS:                   "sss",
    AOVType.SSS_DIRECT:            "sss_direct",
    AOVType.SSS_INDIRECT:          "sss_indirect",
    AOVType.COAT:                  "coat",
    AOVType.COAT_DIRECT:           "coat_direct",
    AOVType.COAT_INDIRECT:         "coat_indirect",
    AOVType.SHEEN:                 "sheen",
    AOVType.SHEEN_DIRECT:          "sheen_direct",
    AOVType.SHEEN_INDIRECT:        "sheen_indirect",
    AOVType.EMISSION:              "emission",
    AOVType.TRANSMISSION:          "transmission",
    AOVType.TRANSMISSION_DIRECT:   "transmission_direct",
    AOVType.TRANSMISSION_INDIRECT: "transmission_indirect",
    AOVType.VOLUME:                "volume",
    AOVType.VOLUME_DIRECT:         "volume_direct",
    AOVType.VOLUME_INDIRECT:       "volume_indirect",
    AOVType.REFLECTION:            "reflection",
    AOVType.REFRACTION:            "refraction",
    AOVType.GI:                    "gi",
    AOVType.LIGHTING:              "lighting",
    AOVType.SELF_ILLUMINATION:     "self_illumination",
    AOVType.CAUSTICS:              "caustics",
    AOVType.ATMOSPHERE:            "atmosphere",
    AOVType.BACKGROUND:            "background",
    AOVType.DEPTH:                 "depth",
    AOVType.NORMAL:                "normal",
    AOVType.POSITION:              "position",
    AOVType.UV:                    "uv",
    AOVType.MOTION:                "motion",
    AOVType.OBJECT_ID:             "object_id",
    AOVType.MATERIAL_ID:           "material_id",
    AOVType.CRYPTOMATTE:           "cryptomatte",
    AOVType.AMBIENT_OCCLUSION:     "ambient_occlusion",
    AOVType.SHADOW:                "shadow",
    AOVType.FRESNEL:               "fresnel",
    AOVType.LIGHT_GROUP:           "light_group",
    AOVType.CUSTOM:                "custom",
    AOVType.UNKNOWN:               "unknown",
}

# Reverse lookup: crucible-standard name → AOVType
_REVERSE_STANDARD: Dict[str, AOVType] = {v: k for k, v in CRUCIBLE_STANDARD_NAMES.items()}


# ---------------------------------------------------------------------------
# Pass Status Enum
# ---------------------------------------------------------------------------

class PassStatus:
    """String constants for per-pass status flags."""
    OK      = "ok"
    MISSING = "missing"
    EXTRA   = "extra"
    WARNING = "warning"


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class PassRecord:
    """One normalised pass entry inside a PassManifest.

    Attributes
    ----------
    original_name   : Layer name as found in the EXR.
    standard_name   : Crucible-normalised name (from CRUCIBLE_STANDARD_NAMES).
    aov_type        : Classified AOVType enum value.
    category        : High-level AOVCategory.
    suffixes        : Channel suffixes present (e.g. ['red','green','blue']).
    light_group     : Light group identifier (or None if not a light group).
    status          : PassStatus flag — set by the validator.
    renderer        : Source renderer that produced this pass.
    """
    original_name: str
    standard_name: str
    aov_type: AOVType
    category: AOVCategory
    suffixes: List[str] = field(default_factory=list)
    light_group: Optional[str] = None
    status: str = PassStatus.OK
    renderer: Renderer = Renderer.GENERIC

    @property
    def display_name(self) -> str:
        """Human-readable display label."""
        if self.light_group:
            return f"LG: {self.light_group}"
        return self.standard_name.replace("_", " ").title()

    @property
    def full_channel_names(self) -> List[str]:
        return [f"{self.original_name}.{s}" for s in self.suffixes]

    @property
    def is_rgb(self) -> bool:
        return all(s in self.suffixes for s in ("red", "green", "blue"))

    @property
    def has_alpha(self) -> bool:
        return "alpha" in self.suffixes


@dataclass
class PassManifest:
    """Complete normalised pass manifest for one EXR source.

    Attributes
    ----------
    renderer        : Auto-detected source renderer.
    all_passes      : All normalised PassRecord objects.
    missing_passes  : Crucible standard names that were expected but absent.
    extra_passes    : Passes found that have no recognised standard mapping.
    light_groups    : Detected light group names (ordered).
    beauty_verified : Whether additive rebuild sum ≈ beauty (if verifiable).
    source_node_name: Name of the Nuke Read node this manifest was built from.
    """
    renderer: Renderer = Renderer.GENERIC
    all_passes: List[PassRecord] = field(default_factory=list)
    missing_passes: List[str] = field(default_factory=list)
    extra_passes: List[str] = field(default_factory=list)
    light_groups: List[str] = field(default_factory=list)
    beauty_verified: Optional[bool] = None
    source_node_name: str = ""

    # ------------------------------------------------------------------ #
    # Convenience accessors
    # ------------------------------------------------------------------ #

    @property
    def shading_passes(self) -> List[PassRecord]:
        return [p for p in self.all_passes if p.category == AOVCategory.SHADING]

    @property
    def utility_passes(self) -> List[PassRecord]:
        return [p for p in self.all_passes if p.category == AOVCategory.UTILITY]

    @property
    def beauty_pass(self) -> Optional[PassRecord]:
        for p in self.all_passes:
            if p.category == AOVCategory.BEAUTY:
                return p
        return None

    @property
    def light_group_passes(self) -> List[PassRecord]:
        return [p for p in self.all_passes if p.category == AOVCategory.LIGHT_GROUP]

    @property
    def matte_passes(self) -> List[PassRecord]:
        return [p for p in self.all_passes if p.category == AOVCategory.MATTE]

    @property
    def ok_count(self) -> int:
        return sum(1 for p in self.all_passes if p.status == PassStatus.OK)

    @property
    def missing_count(self) -> int:
        return len(self.missing_passes)

    @property
    def has_issues(self) -> bool:
        return bool(self.missing_passes or self.extra_passes)

    def to_dict(self) -> dict:
        """Serialise the manifest to a plain dict (JSON-safe)."""
        return {
            "renderer": self.renderer.value,
            "source_node": self.source_node_name,
            "passes": [
                {
                    "original_name": p.original_name,
                    "standard_name": p.standard_name,
                    "aov_type": p.aov_type.name,
                    "category": p.category.name,
                    "light_group": p.light_group,
                    "status": p.status,
                    "channels": p.full_channel_names,
                }
                for p in self.all_passes
            ],
            "missing": self.missing_passes,
            "extra": self.extra_passes,
            "light_groups": self.light_groups,
            "beauty_verified": self.beauty_verified,
        }


# ---------------------------------------------------------------------------
# Built-in Validation Schemas
#
# Studios can extend these or supply custom JSON schemas.
# ---------------------------------------------------------------------------

#: Minimum set of shading passes for a "simple" CG render.
SCHEMA_SIMPLE = {
    "name": "Simple CG",
    "required": ["beauty", "diffuse", "specular"],
    "recommended": ["shadow", "ambient_occlusion", "depth"],
}

#: Expected passes for an Arnold split-component render.
SCHEMA_ARNOLD_FULL = {
    "name": "Arnold Full",
    "required": [
        "beauty",
        "diffuse_direct", "diffuse_indirect",
        "specular_direct", "specular_indirect",
        "sss", "emission", "coat", "sheen",
        "transmission",
        "depth", "normal",
    ],
    "recommended": [
        "diffuse_albedo", "motion", "object_id",
        "cryptomatte", "ambient_occlusion",
    ],
}

#: Expected passes for a Karma / Houdini render with LPEs.
SCHEMA_KARMA_LPE = {
    "name": "Karma LPE",
    "required": [
        "beauty",
        "diffuse_direct", "diffuse_indirect",
        "specular_direct", "specular_indirect",
        "emission", "sss",
        "depth",
    ],
    "recommended": [
        "normal", "motion", "cryptomatte",
    ],
}

#: Blender Cycles expected passes.
SCHEMA_CYCLES_FULL = {
    "name": "Cycles Full",
    "required": [
        "beauty",
        "diffuse_direct", "diffuse_indirect",
        "specular_direct", "specular_indirect",
        "emission",
        "shadow", "depth", "normal",
    ],
    "recommended": [
        "ambient_occlusion", "uv", "motion",
    ],
}

#: V-Ray component-based render.
SCHEMA_VRAY = {
    "name": "V-Ray",
    "required": [
        "beauty",
        "lighting", "gi", "reflection", "refraction",
        "specular", "sss", "self_illumination",
        "depth",
    ],
    "recommended": [
        "shadow", "caustics", "atmosphere", "object_id",
    ],
}

BUILT_IN_SCHEMAS = {
    "Simple CG":      SCHEMA_SIMPLE,
    "Arnold Full":    SCHEMA_ARNOLD_FULL,
    "Karma LPE":      SCHEMA_KARMA_LPE,
    "Cycles Full":    SCHEMA_CYCLES_FULL,
}

# Auto-select schema per renderer
_RENDERER_DEFAULT_SCHEMA: Dict[Renderer, str] = {
    Renderer.ARNOLD:   "Arnold Full",
    Renderer.KARMA:    "Karma LPE",
    Renderer.REDSHIFT: "Simple CG",
    Renderer.CYCLES:   "Cycles Full",
    Renderer.GENERIC:  "Simple CG",
}


# ---------------------------------------------------------------------------
# Pass Manager  (Main Entry Point)
# ---------------------------------------------------------------------------

class PassManager:
    """Stateless helper that builds and validates PassManifests.

    Usage
    -----
    ::

        import nuke
        from crucible.aov_builder.pass_manager import PassManager

        node = nuke.selectedNode()
        pm   = PassManager()
        manifest = pm.build_manifest(node)
        report   = pm.validate(manifest, schema_name="Arnold Full")
        pm.auto_route(manifest, node)     # creates Shuffle nodes in DAG
    """

    # ------------------------------------------------------------------ #
    # Build
    # ------------------------------------------------------------------ #

    def build_manifest(
        self,
        node,
        prefix_override: Optional[str] = None,
    ) -> PassManifest:
        """Parse a Nuke node and return a normalised PassManifest.

        Args:
            node:             A Nuke Read (or any) node.
            prefix_override:  Force a specific light-group prefix string.

        Returns:
            PassManifest fully populated with normalised PassRecord objects.
        """
        parsed: ParsedChannels = parse_channels(node, prefix_override=prefix_override)
        manifest = PassManifest(
            renderer=parsed.renderer,
            source_node_name=node.name(),
        )

        for layer in parsed.all_layers:
            std_name = CRUCIBLE_STANDARD_NAMES.get(layer.aov_type, layer.name.lower())
            record = PassRecord(
                original_name=layer.name,
                standard_name=std_name,
                aov_type=layer.aov_type,
                category=layer.category,
                suffixes=layer.suffixes,
                light_group=layer.light_group,
                renderer=parsed.renderer,
            )
            manifest.all_passes.append(record)
            if layer.light_group and layer.light_group not in manifest.light_groups:
                manifest.light_groups.append(layer.light_group)

        return manifest

    # ------------------------------------------------------------------ #
    # Validate
    # ------------------------------------------------------------------ #

    def validate(
        self,
        manifest: PassManifest,
        schema_name: Optional[str] = None,
        custom_schema: Optional[dict] = None,
    ) -> dict:
        """Validate a PassManifest against a named or custom schema.

        Marks each PassRecord with a status flag and populates
        ``manifest.missing_passes`` and ``manifest.extra_passes``.

        Args:
            manifest:       The manifest to validate.
            schema_name:    Name of a built-in schema.  If None, auto-selects
                            based on ``manifest.renderer``.
            custom_schema:  A raw schema dict with ``required`` / ``recommended``
                            lists.  Overrides ``schema_name`` if supplied.

        Returns:
            dict with keys:
                - ``schema``: Name of the schema used.
                - ``required_missing``: list of missing required pass names.
                - ``recommended_missing``: list of missing recommended pass names.
                - ``unknown_passes``: list of passes with UNKNOWN aov_type.
                - ``summary``: human-readable string.
        """
        # Resolve schema
        if custom_schema:
            schema = custom_schema
        else:
            if schema_name is None:
                schema_name = _RENDERER_DEFAULT_SCHEMA.get(manifest.renderer, "Simple CG")
            schema = BUILT_IN_SCHEMAS.get(schema_name, SCHEMA_SIMPLE)

        required:    List[str] = schema.get("required", [])
        recommended: List[str] = schema.get("recommended", [])

        # Build lookup: standard_name → PassRecord
        found_standards: Set[str] = {p.standard_name for p in manifest.all_passes}

        required_missing    = [r for r in required    if r not in found_standards]
        recommended_missing = [r for r in recommended if r not in found_standards]
        unknown_passes      = [
            p.original_name for p in manifest.all_passes
            if p.aov_type in (AOVType.UNKNOWN, AOVType.CUSTOM)
        ]

        # Tag records
        found_set = set(required + recommended)
        for p in manifest.all_passes:
            if p.standard_name in required_missing:
                p.status = PassStatus.MISSING
            elif p.aov_type == AOVType.UNKNOWN:
                p.status = PassStatus.WARNING
            elif p.standard_name not in found_set:
                p.status = PassStatus.EXTRA
            else:
                p.status = PassStatus.OK

        manifest.missing_passes = required_missing
        manifest.extra_passes   = unknown_passes

        # Build summary
        if not required_missing and not recommended_missing:
            summary = f"✅  All required passes present ({len(manifest.all_passes)} total)."
        else:
            parts = []
            if required_missing:
                parts.append(f"❌ {len(required_missing)} required missing")
            if recommended_missing:
                parts.append(f"⚠️  {len(recommended_missing)} recommended missing")
            summary = "  |  ".join(parts)

        return {
            "schema":               schema.get("name", schema_name),
            "required_missing":     required_missing,
            "recommended_missing":  recommended_missing,
            "unknown_passes":       unknown_passes,
            "summary":              summary,
        }

    # ------------------------------------------------------------------ #
    # Diff Manifests
    # ------------------------------------------------------------------ #

    def diff(self, manifest_a: PassManifest, manifest_b: PassManifest) -> dict:
        """Compare two manifests (e.g. different shots or render versions).

        Args:
            manifest_a: Reference manifest (e.g. Shot A).
            manifest_b: Comparison manifest (e.g. Shot B).

        Returns:
            dict with keys:
                - ``only_in_a``: pass names present in A but not B.
                - ``only_in_b``: pass names present in B but not A.
                - ``shared``:    pass names present in both.
                - ``renderer_match``: bool.
        """
        names_a = {p.standard_name for p in manifest_a.all_passes}
        names_b = {p.standard_name for p in manifest_b.all_passes}
        return {
            "only_in_a":       sorted(names_a - names_b),
            "only_in_b":       sorted(names_b - names_a),
            "shared":          sorted(names_a & names_b),
            "renderer_match":  manifest_a.renderer == manifest_b.renderer,
            "renderer_a":      manifest_a.renderer.value,
            "renderer_b":      manifest_b.renderer.value,
        }

    # ------------------------------------------------------------------ #
    # Auto-Route  (creates Nuke nodes)
    # ------------------------------------------------------------------ #

    def auto_route(self, manifest: PassManifest, source_node) -> dict:
        """Create Shuffle2 nodes routing each pass to its own output.

        Organises passes into labelled Backdrop regions:
        * SHADING PASSES
        * UTILITY PASSES
        * LIGHT GROUPS

        Args:
            manifest:     PassManifest built from source_node.
            source_node:  The Nuke Read node to shuffle from.

        Returns:
            dict mapping standard_name → created Shuffle2 node.
        """
        try:
            import nuke
            from ..nuke_utils import create_shuffle, set_node_position, create_backdrop, create_dot
        except ImportError:
            raise RuntimeError("auto_route() must be called from inside Nuke.")

        created: Dict[str, object] = {}
        COL = 200
        ROW = 110
        base_x = source_node.xpos()
        base_y = source_node.ypos() + 220

        with nuke.Undo("Crucible: Auto-Route Passes"):
            dot = create_dot(source_node)
            set_node_position(dot, base_x + 34, base_y)

            # ---- Shading ----
            shading = [p for p in manifest.shading_passes]
            shading_nodes = []
            for i, rec in enumerate(shading):
                shuf = create_shuffle(dot, rec.original_name,
                                      label=rec.display_name,
                                      layer_suffixes=rec.suffixes)
                set_node_position(shuf, base_x + (i + 1) * COL, base_y + ROW)
                created[rec.standard_name] = shuf
                shading_nodes.append(shuf)

            if shading_nodes:
                create_backdrop([dot] + shading_nodes, "SHADING PASSES", "#1a3a2a")

            # ---- Utility ----
            util_y = base_y + ROW * 3
            util_nodes = []
            for i, rec in enumerate(manifest.utility_passes):
                shuf = create_shuffle(dot, rec.original_name,
                                      label=rec.display_name,
                                      layer_suffixes=rec.suffixes)
                set_node_position(shuf, base_x + (i + 1) * COL, util_y)
                created[rec.standard_name] = shuf
                util_nodes.append(shuf)

            if util_nodes:
                create_backdrop(util_nodes, "UTILITY PASSES", "#2a2a3a")

            # ---- Light Groups ----
            lg_x = base_x + (len(shading) + 2) * COL
            lg_dot = create_dot(source_node)
            set_node_position(lg_dot, lg_x + 34, base_y)
            lg_nodes = [lg_dot]
            for i, rec in enumerate(manifest.light_group_passes):
                shuf = create_shuffle(lg_dot, rec.original_name,
                                      label=rec.display_name,
                                      layer_suffixes=rec.suffixes)
                set_node_position(shuf, lg_x + i * COL, base_y + ROW)
                created[f"lg_{rec.light_group}"] = shuf
                lg_nodes.append(shuf)

            if lg_nodes:
                create_backdrop(lg_nodes, "LIGHT GROUPS", "#3a2a1a")

        return created

    # ------------------------------------------------------------------ #
    # Export / Import Manifest JSON
    # ------------------------------------------------------------------ #

    def export_manifest(self, manifest: PassManifest, file_path: str) -> None:
        """Write the manifest to a JSON file.

        Args:
            manifest:  PassManifest to export.
            file_path: Full path to write (will overwrite).

        Raises:
            OSError: If the file cannot be written.
        """
        data = manifest.to_dict()
        data["crucible_schema_version"] = "1.0"
        with open(file_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=4)

    def load_manifest_from_json(self, file_path: str) -> dict:
        """Read a previously exported manifest JSON.

        Returns the raw dict (use ``to_dict()`` on a live manifest to compare).

        Args:
            file_path: Path to the JSON file.

        Returns:
            Parsed dict from the JSON file.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError:        If the file is not valid JSON.
        """
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"Manifest file not found: {file_path}")
        with open(file_path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    # ------------------------------------------------------------------ #
    # Normalise a raw layer name → Crucible standard name
    # ------------------------------------------------------------------ #

    @staticmethod
    def normalise_name(raw_name: str, renderer: Renderer = Renderer.GENERIC) -> str:
        """Convert a DCC-specific layer name to a Crucible standard name.

        Performs:
        1. Renderer-preset lookup.
        2. Generic-preset fallback.
        3. Returns the raw name lowercased if no match found.

        Args:
            raw_name:  Original layer name (any casing).
            renderer:  Source renderer for preset priority.

        Returns:
            Crucible-standard pass name string.
        """
        preset   = get_preset(renderer)
        aov_map  = preset["aov_map"]
        lower    = raw_name.lower()

        aov_type = aov_map.get(lower)
        if aov_type is None and renderer != Renderer.GENERIC:
            generic_map = RENDERER_PRESETS[Renderer.GENERIC]["aov_map"]
            aov_type    = generic_map.get(lower)

        if aov_type is not None:
            return CRUCIBLE_STANDARD_NAMES.get(aov_type, lower)
        return lower

    # ------------------------------------------------------------------ #
    # Utility: get default schema for a renderer
    # ------------------------------------------------------------------ #

    @staticmethod
    def default_schema_for(renderer: Renderer) -> str:
        """Return the built-in schema name best matching a renderer."""
        return _RENDERER_DEFAULT_SCHEMA.get(renderer, "Simple CG")

    @staticmethod
    def list_schemas() -> List[str]:
        """Return all available built-in schema names."""
        return list(BUILT_IN_SCHEMAS.keys())
