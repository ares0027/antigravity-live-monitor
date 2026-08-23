# Auto-formatting hook for Antigravity (PostToolUse)
import sys
import json
import subprocess
from pathlib import Path

RUFF_PATH = r"C:\Users\baran\AppData\Local\Programs\Python\Python312\Scripts\ruff.exe"


def format_file(file_path: str):
    p = Path(file_path)
    if p.exists() and p.suffix.lower() == ".py" and Path(RUFF_PATH).exists():
        try:
            CREATE_NO_WINDOW = 0x08000000
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            subprocess.run(
                [RUFF_PATH, "format", str(p)],
                capture_output=True,
                timeout=5,
                startupinfo=si,
                creationflags=CREATE_NO_WINDOW,
            )
        except Exception:
            pass


def main():
    try:
        if sys.stdin and not sys.stdin.isatty():
            raw = sys.stdin.read()
            if raw.strip():
                data = json.loads(raw)
                tool_call = data.get("toolCall", {})
                args = tool_call.get("args", {})
                target = (
                    args.get("TargetFile")
                    or args.get("target_file")
                    or args.get("file_path")
                )
                if target:
                    format_file(target)
    except Exception:
        pass
    if sys.stdout:
        print("{}")


if __name__ == "__main__":
    main()
