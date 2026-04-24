import re

def repair_args(args_inner):
    keys = list(re.finditer(r'"(\w+)"\s*:', args_inner))
    if not keys:
        # Fallback to single string or empty
        return {}
    args = {}
    for i in range(len(keys)):
        key = keys[i].group(1)
        val_start = keys[i].end()
        if i + 1 < len(keys):
            val_end = keys[i+1].start()
            val_str = args_inner[val_start:val_end].strip()
            # remove trailing comma
            if val_str.endswith(','):
                val_str = val_str[:-1].strip()
        else:
            val_str = args_inner[val_start:].strip()
            
        # Strip surrounding quotes from val_str
        if val_str.startswith('"') and val_str.endswith('"'):
            val_str = val_str[1:-1]
        args[key] = val_str
    return args

test_str1 = '''
"tool_name": "media_tools.generate_tts",
"description": "Generates a TTS",
"code": "@mcp_tool(name="tools", desc="hello")\\ndef hello():\\n  pass"
'''

print(repair_args(test_str1.strip()))
