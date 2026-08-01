"""#426 -- CONTRE-EPREUVE de `tests/engine/test_411_transfer_hit_wiring_offline.py`.

Un garde qu'on n'a pas vu ROUGIR n'est pas un garde. Ce probe casse le cablage de
`DSLBehaviors$$TransferHit` maillon par maillon, rejoue le fichier de test, et exige un ECHEC a
chaque fois. Il restaure toujours (bloc `finally` + verification d'empreinte en sortie).

POURQUOI CE PROBE EXISTE -- le defaut qu'il interdit de reintroduire

  Le garde d'origine detectait le port par une empreinte de REGISTRE (`TRIGGERED_ABILITY_ID` valant
  1109/1511 dans `ABILITY_TRIGGERS` / `CUSTOM_TRIGGERED_ABILITIES`) que le port n'utilise PAS :
  `DrawFire` se declenche PAR COUP, via l'intercepteur d'`ExecuteHit`. Il skippait donc EN VERT sur
  un port vivant -- et aurait skippe A L'IDENTIQUE si le port avait disparu. Aucun des sept mutants
  ci-dessous ne l'aurait fait rougir. C'est la mesure qui a motive #426.

⚠ VERT EST LE RESULTAT SUSPECT ici. Une mutation qui ne s'applique pas rend un test vert et se lit
comme « le garde ne mord pas », alors que rien n'a ete mute. Chaque mutant est donc verifie EN DEUX
TEMPS : le motif recherche doit apparaitre le nombre EXACT de fois attendu AVANT ecriture, et le
texte de remplacement doit etre relu sur disque APRES. Un mutant qui echoue a l'une des deux
verifications est rapporte `MUTATION-NON-APPLIQUEE`, jamais confondu avec `garde muet`.

Purement OFFLINE : aucun runner, aucun RPC, aucune session Frida. ASCII only.

    python probe_426_transfer_hit_wiring_mutants.py            # les 7 mutants
    python probe_426_transfer_hit_wiring_mutants.py --only M3  # un seul
"""
from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
TEST = "tests/engine/test_411_transfer_hit_wiring_offline.py"

_HP = PYDIR / "engine/runner/operations/triggers/loki/harlequins_panoply.py"
_DF = PYDIR / "engine/runner/operations/triggers/loki/draw_fire.py"
_DH = PYDIR / "engine/runner/operations/damage_hits.py"
_DC = PYDIR / "engine/services/damage_combat.py"


# Chaque mutant coupe UN maillon de la chaine, du plus aval (la route elle-meme) au plus amont
# (les gates du trigger). `count` = nombre d'occurrences EXIGE avant ecriture.
MUTANTS = [
    {"id": "M1", "file": _HP, "count": 1,
     "maillon": "l'accroche `should_transfer` delegue au DrawFireTransfer",
     "old": "        return self._transfer.transfer(hit_index)\n",
     "new": "        return False   # MUTANT #426 M1\n"},
    {"id": "M2", "file": _HP, "count": 1,
     "maillon": "l'intercepteur MONTE son DrawFireTransfer sur l'etat courant",
     "old": "        self._transfer = DrawFireTransfer(state, attacker_id, defender_id)\n",
     "new": "        self._transfer = DrawFireTransfer(None, None, None)   # MUTANT #426 M2\n"},
    {"id": "M3", "file": _DH, "count": 1,
     "maillon": "`_transferred` consulte l'intercepteur dans la boucle de coups",
     "old": "                return hit_interceptor is not None and hit_interceptor.should_transfer(idx)\n",
     "new": "                return False   # MUTANT #426 M3\n"},
    {"id": "M4", "file": _DH, "count": 2,
     "maillon": "la branche transfert route vers `guaranteed_block`",
     "old": "_one_hit_tail(idx, crit, roll, guaranteed_block=True)",
     "new": "_one_hit_tail(idx, crit, roll)   # MUTANT #426 M4"},
    {"id": "M5", "file": _DC, "count": 1,
     "maillon": "`calculate_damage_operation` prend le slot 4 sans tirage",
     "old": "    if guaranteed_block:\n",
     "new": "    if False:   # MUTANT #426 M5\n"},
    {"id": "M6", "file": _DF, "count": 1,
     "maillon": "gate `IsAdjacent(Owner, Target)` de CreateTrigger (sur-transfert)",
     "old": "        if not _is_adjacent_units(state, int(eid), int(defender_id)):   # IsAdjacent(Owner, Target)\n            continue\n",
     "new": "        pass   # MUTANT #426 M6 : gate IsAdjacent retire\n"},
    {"id": "M7", "file": _DF, "count": 1,
     "maillon": "gate `AmountIsOdd(CurrentHitIndex)` (transfert de TOUS les coups)",
     "old": "        if int(hit_index) % 2 == 0:                 # AmountIsOdd(CurrentHitIndex), 0-based\n            return False\n",
     "new": "        if False:   # MUTANT #426 M7 : gate AmountIsOdd retire\n            return False\n"},
]


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _pytest() -> tuple:
    """Rejoue le fichier de test. Rend `(rc, resume)`. rc != 0 = ROUGE = le garde a mordu."""
    r = subprocess.run([sys.executable, "-m", "pytest", TEST, "-q", "--no-header", "-x"],
                       cwd=str(PYDIR), capture_output=True, text=True, errors="replace")
    tail = [ln for ln in (r.stdout or "").splitlines() if ln.strip()]
    return r.returncode, (tail[-1] if tail else "(pas de sortie)")


def _first_failure() -> str:
    """Le NOM du premier test tombe -- ce qui dit QUEL invariant a mordu, pas seulement qu'il a
    mordu."""
    r = subprocess.run([sys.executable, "-m", "pytest", TEST, "-q", "--no-header", "-x",
                        "--tb=no", "-rf"],
                       cwd=str(PYDIR), capture_output=True, text=True, errors="replace")
    for ln in (r.stdout or "").splitlines():
        if ln.startswith("FAILED "):
            return ln.split("::", 1)[-1].split(" ")[0]
    return "(aucun)"


def run_mutant(m: dict) -> dict:
    path, before = m["file"], m["file"].read_text(encoding="utf-8")
    sha0 = _sha(path)
    seen = before.count(m["old"])
    if seen != m["count"]:
        return {"id": m["id"], "verdict": "MUTATION-NON-APPLIQUEE",
                "detail": "motif vu %d fois, attendu %d -- le code a bouge, ce probe doit etre "
                          "remis a jour AVANT de conclure quoi que ce soit" % (seen, m["count"])}
    try:
        path.write_text(before.replace(m["old"], m["new"]), encoding="utf-8")
        after = path.read_text(encoding="utf-8")
        if after.count(m["new"]) != m["count"] or _sha(path) == sha0:
            return {"id": m["id"], "verdict": "MUTATION-NON-APPLIQUEE",
                    "detail": "relecture disque : le remplacement n'est pas la"}
        rc, resume = _pytest()
        verdict = "GARDE-MORD" if rc != 0 else "GARDE-MUET"
        out = {"id": m["id"], "verdict": verdict, "detail": resume}
        if rc != 0:
            out["premier_rouge"] = _first_failure()
        return out
    finally:
        path.write_text(before, encoding="utf-8")
        assert _sha(path) == sha0, "RESTAURATION RATEE sur %s -- verifier git diff" % path.name


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="n'executer qu'un mutant (M1..M7)")
    a = ap.parse_args()
    mutants = [m for m in MUTANTS if not a.only or m["id"] == a.only]
    if not mutants:
        print("aucun mutant nomme %r" % a.only)
        return 2

    rc, resume = _pytest()
    print("[etape 0] arbre INTACT -> %s" % resume)
    if rc != 0:
        print("ROUGE SUR L'ARBRE INTACT : la contre-epreuve n'a aucun sens tant que ce n'est pas "
              "vert. Rien n'a ete mute.")
        return 1

    rows = []
    for m in mutants:
        r = run_mutant(m)
        rows.append(r)
        print("[%s] %-22s %s" % (r["id"], r["verdict"], m["maillon"]))
        if r.get("premier_rouge"):
            print("      premier rouge : %s" % r["premier_rouge"])
        if r["verdict"] != "GARDE-MORD":
            print("      %s" % r["detail"])

    rc2, resume2 = _pytest()
    print("[etape N] arbre RESTAURE -> %s" % resume2)
    muets = [r["id"] for r in rows if r["verdict"] == "GARDE-MUET"]
    rates = [r["id"] for r in rows if r["verdict"] == "MUTATION-NON-APPLIQUEE"]
    print("\nRESUME : %d/%d mutants font ROUGIR le garde" % (
        sum(1 for r in rows if r["verdict"] == "GARDE-MORD"), len(rows)))
    if rates:
        print("  MUTATIONS NON APPLIQUEES (ne conclut RIEN) : %s" % ", ".join(rates))
    if muets:
        print("  MAILLONS NON GARDES : %s" % ", ".join(muets))
    return 0 if (not muets and not rates and rc2 == 0) else 1


if __name__ == "__main__":
    sys.exit(main())
