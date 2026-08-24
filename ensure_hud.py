import os
import sys
import subprocess
import ctypes

kernel32 = ctypes.windll.kernel32

# If HUD mutex already exists, an instance is already running; exit immediately.
h_mutex = kernel32.OpenMutexW(
    0x00100000, False, "Global\\AntigravityHUD_SingleInstance_Mutex"
)
if h_mutex:
    kernel32.CloseHandle(h_mutex)
    if sys.stdout:
        print("{}")
    sys.exit(0)

hud_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hud.pyw")
if not os.path.exists(hud_script):
    hud_script = r"C:\Users\baran\AppData\Local\agy\bin\hud.pyw"

python_dir = os.path.dirname(sys.executable)
pythonw = os.path.join(python_dir, "pythonw.exe")
if not os.path.exists(pythonw):
    pythonw = r"C:\Users\baran\AppData\Local\Programs\Python\Python311\pythonw.exe"

if os.path.exists(hud_script) and os.path.exists(pythonw):
    CREATE_NO_WINDOW = 0x08000000
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = subprocess.SW_HIDE
    try:
        subprocess.Popen(
            [pythonw, hud_script],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            startupinfo=si,
            creationflags=CREATE_NO_WINDOW,
        )
    except Exception:
        pass

if sys.stdout:
    print("{}")
