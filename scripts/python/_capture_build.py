"""Run gradle compileJava and save output to a temp file, for analysis.

Chemins RELATIFS au checkout (#314) : en absolu, ce script buildait l'`app/` de
l'arbre principal et y ecrasait `build-errors.log` depuis n'importe quel
worktree d'agent.
"""
import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
APP = REPO / "app"
OUT = REPO / "logs" / "build-errors.log"

env = os.environ.copy()
env["JAVA_HOME"] = r"C:\Program Files\Eclipse Adoptium\jdk-21.0.9.10-hotspot"

# On Windows, use gradlew.bat
cmd = [str(APP / "gradlew.bat"), "compileJava", "--console=plain", "--warning-mode=none"]
proc = subprocess.run(cmd, cwd=str(APP), env=env, capture_output=True, text=True)
out = (proc.stdout or "") + (proc.stderr or "")
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(out, encoding="utf-8")
print(f"exit={proc.returncode}")
print(f"saved {OUT} ({len(out.splitlines())} lines, {out.count('error:')} errors)")
