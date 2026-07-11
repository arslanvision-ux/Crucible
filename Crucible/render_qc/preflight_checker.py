import nuke
import os

def run_preflight_check():
    """Scans the Nuke script for common farm-crashing errors."""
    issues = []
    warnings = []
    
    nodes = nuke.allNodes(recurseGroups=True)
    
    if not nodes:
        nuke.message("Script is empty.")
        return
        
    for node in nodes:
        # 1. Error State
        if node.hasError():
            issues.append(f"❌ <b>[{node.name()}]</b> is in an error state.")
            
        # 2. File Path Checks
        if node.Class() in ['Read', 'ReadGeo2', 'Camera2', 'DeepRead', 'Write']:
            file_knob = node.knob('file')
            if file_knob:
                file_path = file_knob.evaluate()
                if not file_path:
                    issues.append(f"❌ <b>[{node.name()}]</b> has an empty file path.")
                else:
                    dir_path = os.path.dirname(file_path)
                    # Use a lightweight check just for the directory since frame padding (%04d) makes exact file checks tricky
                    if not os.path.exists(dir_path):
                        issues.append(f"❌ <b>[{node.name()}]</b> directory does not exist: {dir_path}")
                        
        # 3. Bounding Box Checks (Massive Bboxes crash render farms)
        try:
            bbox = node.bbox()
            fmt = nuke.root().format()
            # If a bbox is more than 3x the format size, flag it
            if bbox.w() > fmt.width() * 3 or bbox.h() > fmt.height() * 3:
                warnings.append(f"⚠️ <b>[{node.name()}]</b> has a massive Bounding Box ({bbox.w()}x{bbox.h()}). Consider adding a Crop node.")
        except Exception:
            pass
            
    # Compile the final report
    if not issues and not warnings:
        nuke.message("<b>✅ Pre-Flight Check PASSED</b><br><br>Script is clean and ready to submit to the render farm.")
    else:
        html = "<b>Farm Submission Pre-Flight Report</b><br><br>"
        if issues:
            html += "<b>CRITICAL ISSUES (Will crash farm):</b><br>"
            html += "<br>".join(issues) + "<br><br>"
        if warnings:
            html += "<b>WARNINGS (Memory/Performance risks):</b><br>"
            html += "<br>".join(warnings)
            
        nuke.message(html)
