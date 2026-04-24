from mcp.mcp_registry import mcp_tool

import csv
import os
from mcp import mcp_tool

@mcp_tool
def export_structure_to_csv(path: str, output_path: str):
    """Generates a CSV of the directory structure for easy import to Google Sheets."""
    try:
        items = os.listdir(path)
        with open(output_path, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['Type', 'Name', 'Size (Bytes)'])
            for item in items:
                full_path = os.path.join(path, item)
                is_dir = os.path.isdir(full_path)
                size = os.path.getsize(full_path) if not is_dir else 0
                writer.writerow(['DIR' if is_dir else 'FILE', item, size])
        return f'Successfully exported structure to {output_path}'
    except Exception as e:
        return str(e)