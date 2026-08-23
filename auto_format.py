# Auto-formatting hook for Antigravity (PostToolUse)
import sys
import json
import subprocess
from pathlib import Path

RUFF_PATH = r'C:\Users\baran\AppData\Local\Programs\Python\Python312\Scripts\ruff.exe'

def format_file(file_path: str):
    p = Path(file_path)
    if p.exists() and p.suffix.lower() == '.py' and Path(RUFF_PATH).exists():
        try:
            subprocess.run([RUFF_PATH, 'format', str(p)], capture_output=True, timeout=5)
        except Exception:
            pass

def main():
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            print('{}')
            return
        data = json.loads(raw)
        tool_call = data.get('toolCall', {})
        args = tool_call.get('args', {})
        target = args.get('TargetFile') or args.get('target_file') or args.get('file_path')
        if target:
            format_file(target)
    except Exception:
        pass
    print('{}')

if __name__ == '__main__':
    main()
