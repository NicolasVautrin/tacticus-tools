"""Run gradle compileJava and save output to a temp file, for analysis."""
import os
import subprocess
from pathlib import Path

APP = Path(r"C:\Users\nicolasv\tacticus-tools\app")
OUT = Path(r"C:\Users\nicolasv\tacticus-tools\build-errors.log")

env = os.environ.copy()
env["JAVA_HOME"] = r"C:\Program Files\Eclipse Adoptium\jdk-21.0.9.10-hotspot"

# On Windows, use gradlew.bat
cmd = [str(APP / "gradlew.bat"), "compileJava", "--console=plain", "--warning-mode=none"]
proc = subprocess.run(cmd, cwd=str(APP), env=env, capture_output=True, text=True)
out = (proc.stdout or "") + (proc.stderr or "")
OUT.write_text(out, encoding="utf-8")
print(f"exit={proc.returncode}")
print(f"saved {OUT} ({len(out.splitlines())} lines, {out.count('error:')} errors)")
