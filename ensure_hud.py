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

pythonw = r"C:\Users\baran\AppData\Local\Programs\Python\Python311\pythonw.exe"
if not os.path.exists(pythonw):
    python_dir = os.path.dirname(sys.executable)
    pythonw = os.path.join(python_dir, "pythonw.exe")

if os.path.exists(hud_script) and os.path.exists(pythonw):
    CREATE_NO_WINDOW = 0x08000000
    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    try:
        # Spawn via Windows Task Scheduler service so the process is 100% outside any parent Job Object
        task_name = "AntigravityHUD_Launch"
        tr_cmd = f'"{pythonw}" "{hud_script}"'
        subprocess.run(
            ["schtasks", "/Create", "/TN", task_name, "/TR", tr_cmd, "/SC", "ONCE", "/ST", "00:00", "/F"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
            timeout=5,
        )
        subprocess.run(
            ["schtasks", "/Run", "/TN", task_name],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
            timeout=5,
        )
    except Exception:
        try:
            subprocess.Popen(
                [pythonw, hud_script],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
            )
        except Exception:
            pass

if sys.stdout:
    print("{}")
