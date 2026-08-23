import os
import sys
import json
import glob
import re
import subprocess
import datetime
import urllib.parse
import sqlite3
import msvcrt

# Windows ANSI color setup
os.system("")

# Config & Storage Locations
USER_HOME = os.path.expanduser("~")
SETTINGS_FILE = os.path.join(USER_HOME, ".gemini", "antigravity-cli", "settings.json")
PROJECTS_STORE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "projects.json")
CLI_BRAIN = os.path.join(USER_HOME, ".gemini", "antigravity-cli", "brain")
DESKTOP_BRAIN = os.path.join(USER_HOME, ".gemini", "antigravity", "brain")
APPDATA_ROAMING = os.environ.get("APPDATA", os.path.join(USER_HOME, "AppData", "Roaming"))
VSCDB_PATHS = [
    os.path.join(APPDATA_ROAMING, "Antigravity", "User", "globalStorage", "state.vscdb"),
    os.path.join(APPDATA_ROAMING, "Antigravity IDE", "User", "globalStorage", "state.vscdb")
]

# ANSI Styles
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
BLUE = "\033[38;2;49;134;255m"
CYAN = "\033[38;2;0;210;255m"
GREEN = "\033[38;2;16;185;129m"
YELLOW = "\033[38;2;245;158;11m"
ORANGE = "\033[38;2;249;115;22m"
MAGENTA = "\033[38;2;168;85;247m"
RED = "\033[38;2;239;68;68m"
GRAY = "\033[38;2;100;116;139m"

def clear_screen():
    print("\033[2J\033[H", end="")

def get_git_info(path):
    if not os.path.exists(os.path.join(path, ".git")):
        return None
    try:
        branch = subprocess.check_output(
            ["git", "branch", "--show-current"],
            cwd=path, stderr=subprocess.DEVNULL, text=True, timeout=1.2
        ).strip()
        commit = subprocess.check_output(
            ["git", "log", "-1", "--pretty=format:%s"],
            cwd=path, stderr=subprocess.DEVNULL, text=True, timeout=1.2
        ).strip()
        return {"branch": branch or "main", "commit": commit or "No commits"}
    except Exception:
        return {"branch": "git", "commit": "Git repository"}

def get_vscdb_recent_workspaces():
    paths = []
    for db in VSCDB_PATHS:
        if not os.path.exists(db): continue
        try:
            conn = sqlite3.connect(db)
            cur = conn.cursor()
            rows = cur.execute("SELECT value FROM ItemTable WHERE key = 'history.recentlyOpenedPathsList'").fetchall()
            for r in rows:
                raw = r[0].decode("utf-8", errors="ignore") if isinstance(r[0], bytes) else str(r[0])
                d = json.loads(raw)
                for entry in d.get("entries", []):
                    uri = entry.get("folderUri") or entry.get("fileUri")
                    if uri:
                        p = urllib.parse.unquote(uri)
                        if p.startswith("file:///"):
                            p = p[8:].replace("/", "\\")
                            if os.path.exists(p) and os.path.isdir(p):
                                paths.append(os.path.normpath(p))
            conn.close()
        except Exception:
            pass
    return paths

def load_all_workspaces():
    saved = []
    if os.path.exists(PROJECTS_STORE):
        try:
            with open(PROJECTS_STORE, "r", encoding="utf-8") as f:
                saved = json.load(f)
        except Exception:
            saved = []

    vscdb_paths = get_vscdb_recent_workspaces()

    trusted = []
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
                trusted = d.get("trustedWorkspaces", [])
        except Exception:
            pass

    scan_roots = [
        USER_HOME,
        os.path.join(USER_HOME, "Projects"),
        os.path.join(USER_HOME, "Documents")
    ]

    discovered = []
    for root in scan_roots:
        if not os.path.exists(root): continue
        try:
            for item in os.listdir(root):
                full = os.path.join(root, item)
                if os.path.isdir(full):
                    markers = [".git", ".agents", ".gemini", "package.json", "pyproject.toml", "Cargo.toml", "requirements.txt", "project.godot"]
                    if any(os.path.exists(os.path.join(full, m)) for m in markers):
                        discovered.append(os.path.normpath(full))
        except Exception:
            pass

    all_paths = list(dict.fromkeys(saved + vscdb_paths + trusted + discovered))
    
    ignored_patterns = [
        "appdata", ".venv", "node_modules", "build\\tmp", "agy\\bin", 
        "documents", "pictures", "videos", "music", "saved games", "searches", "downloads", "calibre library"
    ]

    valid_workspaces = []
    for p in all_paths:
        p_norm = os.path.normpath(p)
        p_lower = p_norm.lower()
        if not os.path.isdir(p_norm):
            continue
        if p_lower == USER_HOME.lower():
            continue
        if any(p_lower.endswith("\\" + ig) or p_lower.endswith(ig) for ig in ignored_patterns):
            continue
        valid_workspaces.append(p_norm)

    valid_workspaces = list(dict.fromkeys(valid_workspaces))

    workspace_sessions = {p: [] for p in valid_workspaces}

    for brain_root in [DESKTOP_BRAIN, CLI_BRAIN]:
        if not os.path.exists(brain_root): continue
        for log_file in glob.glob(os.path.join(brain_root, "*", ".system_generated", "logs", "transcript.jsonl")):
            cid = os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(log_file))))
            mtime = os.path.getmtime(log_file)
            first_prompt = ""
            matched_ws = None
            turns = 0

            try:
                with open(log_file, "r", encoding="utf-8", errors="ignore") as fp:
                    for line in fp:
                        if not line.strip(): continue
                        try:
                            data = json.loads(line)
                        except:
                            continue

                        if data.get("type") == "USER_INPUT" and not first_prompt:
                            c = data.get("content", "")
                            clean_p = re.sub(r"<[^>]+>", "", c).strip()
                            first_prompt = clean_p.split("\n")[0][:100]
                            turns += 1

                        if not matched_ws and data.get("tool_calls"):
                            for tc in data["tool_calls"]:
                                args = tc.get("args") or tc.get("arguments") or {}
                                for k, v in args.items():
                                    if isinstance(v, str):
                                        v_norm = os.path.normpath(v.strip('"\'')).lower()
                                        for ws in valid_workspaces:
                                            if v_norm.startswith(os.path.normpath(ws).lower()):
                                                matched_ws = ws
                                                break
                                        if matched_ws: break
                                if matched_ws: break
            except Exception:
                pass

            dt_str = datetime.datetime.fromtimestamp(mtime).strftime("%b %d, %H:%M")
            session_obj = {
                "id": cid,
                "mtime": mtime,
                "date": dt_str,
                "turns": turns,
                "prompt": first_prompt or "Conversation Session"
            }

            if matched_ws and matched_ws in workspace_sessions:
                workspace_sessions[matched_ws].append(session_obj)

    projects = []
    for p in valid_workspaces:
        name = os.path.basename(p) or p
        git_info = get_git_info(p)
        sessions = sorted(workspace_sessions.get(p, []), key=lambda x: x["mtime"], reverse=True)
        last_active = sessions[0]["date"] if sessions else (
            datetime.datetime.fromtimestamp(os.path.getmtime(p)).strftime("%b %d, %Y")
        )
        projects.append({
            "name": name,
            "path": p,
            "git": git_info,
            "lastActive": last_active,
            "sessionCount": len(sessions),
            "sessions": sessions
        })

    projects.sort(key=lambda x: (len(x["sessions"]) > 0, x["sessions"][0]["mtime"] if x["sessions"] else os.path.getmtime(x["path"])), reverse=True)
    return projects

def save_custom_project(path):
    path = os.path.normpath(path.strip())
    if not os.path.isdir(path):
        return False
    saved = []
    if os.path.exists(PROJECTS_STORE):
        try:
            with open(PROJECTS_STORE, "r", encoding="utf-8") as f:
                saved = json.load(f)
        except Exception:
            saved = []
    if path not in saved:
        saved.append(path)
        with open(PROJECTS_STORE, "w", encoding="utf-8") as f:
            json.dump(saved, f, indent=2)
    return True

def launch_session(path, mode="default", session_id=None):
    clear_screen()
    print(f"\n{BLUE}{BOLD}🚀 Launching Antigravity CLI...{RESET}")
    print(f"{GRAY}Workspace: {RESET}{BOLD}{path}{RESET}")
    
    cmd_parts = ["agy"]
    if mode == "yolo":
        cmd_parts.append("--dangerously-skip-permissions")
        print(f"{YELLOW}{BOLD}Mode: 🔥 Full Auto (YOLO){RESET}")
    elif mode == "accept-edits":
        cmd_parts.append("--accept-edits")
        print(f"{CYAN}{BOLD}Mode: ⚡ Accept Edits{RESET}")
    elif mode == "plan":
        cmd_parts.append("--plan")
        print(f"{MAGENTA}{BOLD}Mode: 📋 Plan Mode{RESET}")
    else:
        print(f"{GREEN}{BOLD}Mode: 🛡️ Default Interactive{RESET}")

    if session_id:
        cmd_parts.extend(["--resume", session_id])
        print(f"{BLUE}Resuming Session: {session_id}{RESET}")

    print("\n" + "─" * 60 + "\n")
    
    os.chdir(path)
    try:
        subprocess.run(cmd_parts, shell=True)
    except KeyboardInterrupt:
        pass
    sys.exit(0)

def show_session_browser(project):
    sessions = project["sessions"]
    if not sessions:
        clear_screen()
        print(f"\n{YELLOW}No recorded sessions found for {project['name']}.{RESET}")
        print(f"\nPress any key to return...")
        msvcrt.getch()
        return

    sel_idx = 0
    while True:
        clear_screen()
        print(f"{BLUE}{BOLD}💬 Conversation History: {RESET}{BOLD}{project['name']}{RESET}")
        print(f"{GRAY}{project['path']}{RESET}\n")
        print(f"{DIM}Use [▲/▼] to select session • [Enter/Y/A] to resume • [Esc] to go back{RESET}\n")
        print("─" * 74)

        for idx, s in enumerate(sessions[:15]):
            is_sel = (idx == sel_idx)
            prefix = f"{BLUE} ▶ {RESET}" if is_sel else "   "
            num = f"#{len(sessions) - idx}".ljust(4)
            date = f"[{s['date']}]".ljust(16)
            prompt = s["prompt"]
            if len(prompt) > 46:
                prompt = prompt[:43] + "..."

            if is_sel:
                print(f"{prefix}{BOLD}{YELLOW}{num}{RESET} {CYAN}{date}{RESET} {BOLD}{prompt}{RESET}")
                print(f"      {GRAY}ID: {s['id']}  •  Turns: {s['turns']}{RESET}")
            else:
                print(f"{prefix}{DIM}{num}{RESET} {GRAY}{date}{RESET} {prompt}")

        print("─" * 74)
        print(f"{GRAY}[Enter] Resume Default  •  [Y] Resume in YOLO  •  [A] Resume in Accept-Edits  •  [Esc] Back{RESET}")

        key = msvcrt.getwch()
        if key == "\x00" or key == "\xe0":
            arrow = msvcrt.getwch()
            if arrow == "H":
                sel_idx = (sel_idx - 1) % min(len(sessions), 15)
            elif arrow == "P":
                sel_idx = (sel_idx + 1) % min(len(sessions), 15)
        elif key == "\r":
            launch_session(project["path"], mode="default", session_id=sessions[sel_idx]["id"])
        elif key.lower() == "y":
            launch_session(project["path"], mode="yolo", session_id=sessions[sel_idx]["id"])
        elif key.lower() == "a":
            launch_session(project["path"], mode="accept-edits", session_id=sessions[sel_idx]["id"])
        elif key in ["\x1b", "q", "Q"]:
            break

def main():
    selected_idx = 0
    projects = load_all_workspaces()
    page_offset = 0
    PAGE_SIZE = 10

    while True:
        clear_screen()
        print(f"{BLUE}{BOLD}╭────────────────────────────────────────────────────────────────────────╮{RESET}")
        print(f"{BLUE}{BOLD}│  🚀 ANTIGRAVITY WORKSPACE HUB                            (agy v1.1.18) │{RESET}")
        print(f"{BLUE}{BOLD}╰────────────────────────────────────────────────────────────────────────╯{RESET}")
        print(f"{GRAY}Found {len(projects)} projects (Desktop + CLI) • [▲/▼] Navigate • [Q] Quit{RESET}\n")

        if not projects:
            print(f"{YELLOW}No workspaces found. Press [+] to add a project folder.{RESET}")
        else:
            start_idx = page_offset
            end_idx = min(start_idx + PAGE_SIZE, len(projects))

            for idx in range(start_idx, end_idx):
                p = projects[idx]
                is_selected = (idx == selected_idx)
                cursor = f"{BLUE} ▶ {RESET}" if is_selected else "   "
                num_tag = f"[{idx + 1}]".ljust(4)

                git_str = ""
                if p["git"]:
                    git_str = f" {GRAY}git:{RESET}{CYAN}{p['git']['branch']}{RESET} {DIM}• {p['git']['commit'][:30]}{RESET}"

                sess_count = p["sessionCount"]
                sess_str = f"{GREEN}{sess_count} sessions{RESET}" if sess_count > 0 else f"{GRAY}0 sessions{RESET}"
                last_time = f"{GRAY}({p['lastActive']}){RESET}"

                if is_selected:
                    print(f"{cursor}{BOLD}{BLUE}{num_tag}{RESET} {BOLD}{p['name']}{RESET}  {sess_str} {last_time}")
                    print(f"      {GRAY}📂 {p['path']}{RESET}{git_str}")
                else:
                    print(f"{cursor}{DIM}{num_tag}{RESET} {p['name']}  {sess_str} {last_time}")
                    print(f"      {DIM}📂 {p['path']}{RESET}")

            if len(projects) > PAGE_SIZE:
                print(f"\n{GRAY}  Page {page_offset // PAGE_SIZE + 1} of {(len(projects) + PAGE_SIZE - 1) // PAGE_SIZE}  (Showing {start_idx+1}-{end_idx} of {len(projects)}){RESET}")

        print("\n" + "─" * 74)
        print(f"{BOLD}Quick Actions for Highlighted Workspace:{RESET}")
        print(f"  {YELLOW}{BOLD}[Y]{RESET} {YELLOW}🔥 YOLO Mode{RESET}          {CYAN}{BOLD}[A]{RESET} {CYAN}⚡ Accept-Edits{RESET}      {GREEN}{BOLD}[Enter]{RESET} {GREEN}🛡️ Default Mode{RESET}")
        print(f"  {MAGENTA}{BOLD}[P]{RESET} {MAGENTA}📋 Plan Mode{RESET}          {BLUE}{BOLD}[R]{RESET} {BLUE}💬 History ({projects[selected_idx]['sessionCount'] if projects else 0}){RESET}    {GRAY}{BOLD}[+]{RESET} {GRAY}📁 Add Path{RESET}   {RED}[Q]{RESET} Exit")
        print("─" * 74)

        key = msvcrt.getwch()

        if key == "\x00" or key == "\xe0":
            arrow = msvcrt.getwch()
            if arrow == "H":
                if projects:
                    selected_idx = (selected_idx - 1) % len(projects)
                    if selected_idx < page_offset:
                        page_offset = (selected_idx // PAGE_SIZE) * PAGE_SIZE
                    elif selected_idx == len(projects) - 1:
                        page_offset = (selected_idx // PAGE_SIZE) * PAGE_SIZE
            elif arrow == "P":
                if projects:
                    selected_idx = (selected_idx + 1) % len(projects)
                    if selected_idx >= page_offset + PAGE_SIZE:
                        page_offset = (selected_idx // PAGE_SIZE) * PAGE_SIZE
                    elif selected_idx == 0:
                        page_offset = 0
        elif key.isdigit():
            num = int(key) - 1
            if 0 <= num < len(projects):
                selected_idx = num
        elif key == "\r":
            if projects:
                launch_session(projects[selected_idx]["path"], mode="default")
        elif key.lower() == "y":
            if projects:
                launch_session(projects[selected_idx]["path"], mode="yolo")
        elif key.lower() == "a":
            if projects:
                launch_session(projects[selected_idx]["path"], mode="accept-edits")
        elif key.lower() == "p":
            if projects:
                launch_session(projects[selected_idx]["path"], mode="plan")
        elif key.lower() == "r":
            if projects:
                show_session_browser(projects[selected_idx])
        elif key == "+":
            clear_screen()
            print(f"\n{BLUE}{BOLD}📁 Add New Project Workspace{RESET}")
            print(f"{GRAY}Enter full directory path:{RESET}\n")
            try:
                new_path = input("Path: ").strip()
                if new_path and save_custom_project(new_path):
                    projects = load_all_workspaces()
                    print(f"\n{GREEN}✓ Project added successfully!{RESET}")
                else:
                    print(f"\n{RED}✗ Invalid directory path.{RESET}")
                print(f"{GRAY}Press any key to continue...{RESET}")
                msvcrt.getch()
            except KeyboardInterrupt:
                pass
        elif key in ["\x1b", "q", "Q"]:
            clear_screen()
            print(f"{GRAY}Exited Antigravity Hub.{RESET}\n")
            sys.exit(0)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        clear_screen()
        sys.exit(0)
