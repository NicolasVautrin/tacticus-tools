"""Contre-epreuve #888 : chaque assertion du test live MORD-elle ?

Pour chaque mutant : on ecrit la mutation, on joue le test CIBLE, on restaure, et on exige
`rc != 0` sous mutation. Un mutant qui laisse le test VERT designe une assertion inerte.
Sortie ASCII.
"""
import os
import subprocess
import sys

W = r"C:\Users\nicolasv\tacticus-tools\.claude\worktrees\agent-ae91510c47091f8b9"
PY = os.path.join(W, "scripts", "python")
DG = os.path.join(PY, "engine", "runner", "abilities", "deathguard.py")
SNAP = os.path.join(PY, "engine", "runner", "snapshot.py")
TEST = "tests/engine/runner/test_888_mortarion_boss_abilities_live.py"

MUTANTS = [
    # (libelle, fichier, avant, apres, selection pytest)
    ("1095 reference=Target -> collapse caster (defaut du noeud)", DG,
     "return Union(t, AdjacentFriends(t, reference=t, selection_type=SELECTION))",
     "return Union(t, AdjacentFriends(t, selection_type=SELECTION))",
     "test_1095_live_equals_offline and voisins"),
    ("1093 gate Summon : le x2 retire", DG,
     "                        Multiply(avg, Const(2)),             # <DSLFormulas+0x28> = Direct(2)",
     "                        avg,                                 # MUTANT : x2 retire",
     "test_1093_summon_gate_doubles_offline"),
    ("1093 seeding : le comblement AbilityState per-ability desactive", SNAP,
     "            _ability_state_with_rows(_ability_state_from_config(su.get(\"unitConfig\")), su),",
     "            _ability_state_from_config(su.get(\"unitConfig\")),",
     "test_1093_three_waves_live_equals_offline"),
]


def jouer(sel):
    env = dict(os.environ, TACTICUS_ALLOW_ROSTER_DEFICIT="1")
    p = subprocess.run([sys.executable, "-m", "pytest", TEST, "-q", "-k", sel],
                       cwd=PY, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env)
    tail = [l for l in (p.stdout or "").splitlines() if l.strip()][-1:]
    return p.returncode, (tail[0] if tail else "")


def muter(path, avant, apres):
    s = open(path, encoding="utf-8").read()
    if s.count(avant) != 1:
        raise SystemExit("ANCRE non unique (%d) dans %s" % (s.count(avant), path))
    open(path, "w", encoding="utf-8", newline="").write(s.replace(avant, apres))


ok = True
for libelle, path, avant, apres, sel in MUTANTS:
    orig = open(path, encoding="utf-8").read()
    try:
        muter(path, avant, apres)
        rc, tail = jouer(sel)
    finally:
        open(path, "w", encoding="utf-8", newline="").write(orig)
    verdict = "MORD" if rc != 0 else "*** INERTE ***"
    ok = ok and rc != 0
    print("[mutant] %-60s rc=%d  %s   | %s" % (libelle, rc, verdict, tail))

rc0, tail0 = jouer("test_1093 or test_1095")
print("[temoin] restauration                                        rc=%d          | %s" % (rc0, tail0))
ok = ok and rc0 == 0
print("VERDICT :", "OK -- les 3 mutants mordent et la restauration est verte" if ok else "ROUGE")
raise SystemExit(0 if ok else 1)
