import sys, os; sys.path.insert(0, os.getcwd()) if os.getcwd() not in sys.path else None;
from mcp_custom.mcp_registry import mcp_custom_tool

import csv
import os
import sys, os; sys.path.insert(0, os.getcwd()) if os.getcwd() not in sys.path else None;
# from mcp_custom import mcp_custom_tool

@mcp_custom_tool
def export_structure_to_csv(path: str, output_csv_path: str):
    """Scans a directory and exports its structure to a CSV file for Google Sheets integration."""
    try:
        items = os.listdir(path)
        with open(output_csv_path, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['Type', 'Name', 'Size (Bytes)', 'Last Modified'])
            for item in items:
                full_path = os.path.join(path, item)
                is_dir = os.path.isdir(full_path)
                stats = os.stat(full_path)
                size = stats.st_size if not is_dir else 0
                writer.writerow(['DIR' if is_dir else 'FILE', item, size, stats.st_mtime])
        return f'Successfully exported structure to {output_csv_path}'
    except Exception as e:
        return f'Error: {str(e)}'