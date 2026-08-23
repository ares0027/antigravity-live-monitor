import sys
import json
import os

USER_HOME = os.path.expanduser("~")
HUD_CONFIG_FILE = os.path.join(
    USER_HOME, "AppData", "Local", "agy", "bin", "hud_config.json"
)

is_yolo_enabled = True
if os.path.exists(HUD_CONFIG_FILE):
    try:
        with open(HUD_CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            if isinstance(cfg, dict):
                is_yolo_enabled = cfg.get("global_yolo", True)
    except Exception:
        pass

if sys.stdout:
    if is_yolo_enabled:
        print(json.dumps({"decision": "allow"}))
    else:
        print(json.dumps({}))
