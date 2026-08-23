import os
import sys
import subprocess

hud_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hud.pyw")
if not os.path.exists(hud_script):
    hud_script = r"C:\Users\baran\AppData\Local\agy\bin\hud.pyw"

python_dir = os.path.dirname(sys.executable)
pythonw = os.path.join(python_dir, "pythonw.exe")
if not os.path.exists(pythonw):
    pythonw = r"C:\Users\baran\AppData\Local\Programs\Python\Python311\pythonw.exe"

if os.path.exists(hud_script):
    CREATE_NO_WINDOW = 0x08000000
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = subprocess.SW_HIDE
    try:
        subprocess.Popen(
            [pythonw, hud_script], startupinfo=si, creationflags=CREATE_NO_WINDOW
        )
    except Exception:
        pass

# Output empty JSON for hook contract
if sys.stdout:
    print("{}")
