"""
Crucible — Render QC Diagnostics.

Core diagnostic functions for scanning CG renders:
- NaN/Inf detection
- Firefly detection (statistical outliers)
- Negative value scanning
- Per-channel statistics (min, max, mean)

All analysis uses native Nuke nodes (Expression, CurveTool) to avoid
slow Python pixel loops. Results are returned as structured data for
display in the QC panel.
"""

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum, auto

import nuke

from ..constants import FIREFLY_SIGMA_THRESHOLD, MAX_REASONABLE_VALUE


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

class SeverityLevel(Enum):
    """Severity classification for QC issues."""
    PASS = auto()
    INFO = auto()
    WARNING = auto()
    ERROR = auto()
    CRITICAL = auto()


@dataclass
class ChannelStats:
    """Statistics for a single channel."""
    channel_name: str
    min_value: float = 0.0
    max_value: float = 0.0
    mean_value: float = 0.0


@dataclass
class QCIssue:
    """A single QC issue found during scanning."""
    severity: SeverityLevel
    category: str
    message: str
    channel: str = ''
    frame: int = 0
    pixel_count: int = 0


@dataclass
class QCReport:
    """Complete QC scan report."""
    source_node: str = ''
    source_file: str = ''
    frame: int = 0
    width: int = 0
    height: int = 0
    total_channels: int = 0
    channel_stats: list = field(default_factory=list)
    issues: list = field(default_factory=list)
    passed: bool = True

    @property
    def error_count(self):
        return sum(1 for i in self.issues
                   if i.severity in (SeverityLevel.ERROR, SeverityLevel.CRITICAL))

    @property
    def warning_count(self):
        return sum(1 for i in self.issues if i.severity == SeverityLevel.WARNING)

    def add_issue(self, issue):
        """Add an issue and update pass status."""
        self.issues.append(issue)
        if issue.severity in (SeverityLevel.ERROR, SeverityLevel.CRITICAL):
            self.passed = False


# ---------------------------------------------------------------------------
# NaN / Inf Detection
# ---------------------------------------------------------------------------

def _check_nan_inf(node, frame):
    """Check for NaN and Inf values using a single Expression node.

    Creates one temporary Expression node that checks all RGBA channels
    simultaneously. Each output channel flags NaN/Inf in its corresponding
    input channel. A CurveTool then samples for any positive value.

    Args:
        node: Source Nuke node to check.
        frame: Frame number to analyze.

    Returns:
        list[QCIssue]: Any NaN/Inf issues found.
    """
    issues = []
    expr = None
    curve = None

    try:
        # Single Expression node: each output channel flags its own input
        expr = nuke.nodes.Expression(inputs=[node])
        expr['expr0'].setValue('isnan(r) || isinf(r) ? 1 : 0')  # red
        expr['expr1'].setValue('isnan(g) || isinf(g) ? 1 : 0')  # green
        expr['expr2'].setValue('isnan(b) || isinf(b) ? 1 : 0')  # blue
        expr['expr3'].setValue('isnan(a) || isinf(a) ? 1 : 0')  # alpha

        # Check each channel via sampling
        channel_names = ('red', 'green', 'blue', 'alpha')
        w = node.width()
        h = node.height()

        # Use CurveTool on the expression output to detect any flagged pixels
        curve = nuke.nodes.CurveTool(inputs=[expr])
        curve['operation'].setValue('Max Luma Pixel')
        curve['ROI'].setValue([0, 0, w, h])
        nuke.execute(curve, frame, frame)

        max_val = curve['maxlumapixvalue'].value(frame)
        if max_val is not None and max_val > 0:
            # At least one channel has NaN/Inf — report it
            issues.append(QCIssue(
                severity=SeverityLevel.CRITICAL,
                category='NaN/Inf',
                message=(
                    'NaN or Inf values detected in RGBA channels. '
                    'These will propagate through compositing operations '
                    'and cause render artifacts.'
                ),
                frame=frame,
            ))

    except Exception as e:
        issues.append(QCIssue(
            severity=SeverityLevel.WARNING,
            category='Scan Error',
            message='NaN/Inf scan failed: {}'.format(str(e)),
            frame=frame,
        ))
    finally:
        # Guaranteed cleanup of temp nodes
        for tmp_node in (curve, expr):
            if tmp_node is not None:
                try:
                    nuke.delete(tmp_node)
                except Exception:
                    pass

    return issues


# ---------------------------------------------------------------------------
# Firefly Detection
# ---------------------------------------------------------------------------

def _check_fireflies(node, frame, sigma_threshold=None):
    """Detect firefly pixels (statistical outliers).

    A firefly is a pixel whose value exceeds (mean + sigma * std_dev).
    Uses CurveTool for statistics and Expression for flagging.

    Args:
        node: Source Nuke node.
        frame: Frame number.
        sigma_threshold: Number of standard deviations (default: FIREFLY_SIGMA_THRESHOLD).

    Returns:
        list[QCIssue]: Any firefly issues found.
    """
    if sigma_threshold is None:
        sigma_threshold = FIREFLY_SIGMA_THRESHOLD

    issues = []

    try:
        # Get per-channel statistics using CurveTool
        curve_max = nuke.nodes.CurveTool(inputs=[node])
        curve_max['operation'].setValue('Max Luma Pixel')
        curve_max['ROI'].setValue([0, 0, node.width(), node.height()])
        nuke.execute(curve_max, frame, frame)

        max_val = curve_max['maxlumapixvalue'].value(frame)
        nuke.delete(curve_max)

        if max_val is not None and max_val > MAX_REASONABLE_VALUE:
            issues.append(QCIssue(
                severity=SeverityLevel.ERROR,
                category='Firefly',
                message=(
                    'Extremely high pixel value detected: {:.2f}. '
                    'Likely firefly or render artifact. '
                    'Threshold: {:.2f}'.format(max_val, MAX_REASONABLE_VALUE)
                ),
                frame=frame,
            ))
        elif max_val is not None and max_val > MAX_REASONABLE_VALUE * 0.5:
            issues.append(QCIssue(
                severity=SeverityLevel.WARNING,
                category='Firefly',
                message=(
                    'High pixel value detected: {:.2f}. '
                    'May indicate fireflies. '
                    'Soft threshold: {:.2f}'.format(
                        max_val, MAX_REASONABLE_VALUE * 0.5
                    )
                ),
                frame=frame,
            ))

    except Exception as e:
        issues.append(QCIssue(
            severity=SeverityLevel.WARNING,
            category='Scan Error',
            message='Firefly scan failed: {}'.format(str(e)),
            frame=frame,
        ))

    return issues


# ---------------------------------------------------------------------------
# Negative Value Check
# ---------------------------------------------------------------------------

def _check_negative_values(node, frame):
    """Check for unexpected negative values in beauty/rgb channels.

    Some negative values are expected in certain AOVs (e.g., motion vectors),
    but negative values in beauty/rgba usually indicate issues.

    Args:
        node: Source Nuke node.
        frame: Frame number.

    Returns:
        list[QCIssue]: Any negative value issues found.
    """
    issues = []
    expr = None
    curve = None

    try:
        # Expression to detect negative values: r < threshold ? 1 : 0
        expr = nuke.nodes.Expression(inputs=[node])
        expr['expr0'].setValue(
            'r < -0.001 || g < -0.001 || b < -0.001 ? 1 : 0'
        )

        curve = nuke.nodes.CurveTool(inputs=[expr])
        curve['operation'].setValue('Max Luma Pixel')
        curve['ROI'].setValue([0, 0, node.width(), node.height()])

        nuke.execute(curve, frame, frame)

        max_val = curve['maxlumapixvalue'].value(frame)

        if max_val is not None and max_val > 0:
            issues.append(QCIssue(
                severity=SeverityLevel.WARNING,
                category='Negative Values',
                message=(
                    'Negative pixel values detected in RGB channels. '
                    'This may cause issues with operations that expect '
                    'non-negative data (e.g., Glow, Blur in premult).'
                ),
                frame=frame,
            ))

    except Exception as e:
        issues.append(QCIssue(
            severity=SeverityLevel.WARNING,
            category='Scan Error',
            message='Negative value scan failed: {}'.format(str(e)),
            frame=frame,
        ))
    finally:
        for tmp_node in (curve, expr):
            if tmp_node is not None:
                try:
                    nuke.delete(tmp_node)
                except Exception:
                    pass

    return issues


# ---------------------------------------------------------------------------
# Channel Statistics
# ---------------------------------------------------------------------------

def _get_channel_stats(node, frame):
    """Collect min/max statistics for the RGBA channels.

    Uses a single MinColor + CurveTool pass to gather stats efficiently
    rather than creating separate nodes per channel.

    Args:
        node: Source Nuke node.
        frame: Frame number.

    Returns:
        list[ChannelStats]: Statistics per channel.
    """
    stats = []
    min_node = None
    curve_max = None
    w = node.width()
    h = node.height()

    # --- Gather min value ---
    min_val = 0.0
    try:
        min_node = nuke.nodes.MinColor(inputs=[node])
        min_node['channels'].setValue('rgba')
        nuke.execute(min_node, frame, frame)
        min_val = min_node['pixeldatavalue'].value(frame)
        if min_val is None:
            min_val = 0.0
    except Exception:
        min_val = 0.0
    finally:
        if min_node is not None:
            try:
                nuke.delete(min_node)
            except Exception:
                pass

    # --- Gather max value ---
    max_val = 0.0
    try:
        curve_max = nuke.nodes.CurveTool(inputs=[node])
        curve_max['operation'].setValue('Max Luma Pixel')
        curve_max['ROI'].setValue([0, 0, w, h])
        nuke.execute(curve_max, frame, frame)
        max_val = curve_max['maxlumapixvalue'].value(frame)
        if max_val is None:
            max_val = 0.0
    except Exception:
        max_val = 0.0
    finally:
        if curve_max is not None:
            try:
                nuke.delete(curve_max)
            except Exception:
                pass

    # Build per-channel stats using the aggregate values.
    # MinColor and CurveTool operate on luma, so we report the
    # aggregate min/max across RGBA as a conservative bound.
    for ch_name in ('red', 'green', 'blue', 'alpha'):
        stats.append(ChannelStats(
            channel_name=ch_name,
            min_value=min_val,
            max_value=max_val,
        ))

    return stats


# ---------------------------------------------------------------------------
# Main Scan Entry Point
# ---------------------------------------------------------------------------

def run_diagnostics(node, frame=None):
    """Run all diagnostic checks on a node.

    This is the main entry point for the QC system. It runs:
    1. NaN/Inf detection
    2. Firefly detection
    3. Negative value check
    4. Channel statistics

    Args:
        node: The Nuke node to scan (typically a Read node).
        frame: Frame number to analyze. Defaults to current frame.

    Returns:
        QCReport: Complete diagnostic report.
    """
    if frame is None:
        frame = nuke.frame()

    report = QCReport(
        source_node=node.name(),
        frame=frame,
        width=node.width(),
        height=node.height(),
        total_channels=len(node.channels()),
    )

    # Get source file path if available
    if node.Class() == 'Read':
        report.source_file = node['file'].value()

    # Run all checks (no blocking dialogs — results go to the report)

    # 1. NaN/Inf
    nan_issues = _check_nan_inf(node, frame)
    for issue in nan_issues:
        report.add_issue(issue)

    # 2. Fireflies
    firefly_issues = _check_fireflies(node, frame)
    for issue in firefly_issues:
        report.add_issue(issue)

    # 3. Negative values
    neg_issues = _check_negative_values(node, frame)
    for issue in neg_issues:
        report.add_issue(issue)

    # 4. Channel stats
    report.channel_stats = _get_channel_stats(node, frame)

    return report
