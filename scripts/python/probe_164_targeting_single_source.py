"""#164 -- GENERALISATION de la convergence `RULE_*` -> enum GENERE `TargetingRule`.

CE QUE CA REPOND
----------------
La convergence est un changement de SOURCE de constantes, pas de comportement : le diff doit etre
NUL a l'execution. C'est deja prouve formellement (substitution de chaque symbole par sa valeur ->
diff vide sur toute ligne de logique), mais une preuve formelle ne dit rien du re-mapping lui-meme :
si `RULE_BIT39_TARGET_IS_CASTER` avait ete remappe sur le MAUVAIS membre de l'enum, la substitution
resterait « coherente » et le port changerait de verdict en silence.

Ce probe confronte donc le port au NATIF sur les trois bits dont le NOM a change, en montant une
bataille ou ils sont EFFECTIVEMENT poses :

    TargetIsCaster          (ex-`RULE_BIT39_TARGET_IS_CASTER`)     -> ResurrectionOrb (1009)
    AllowUntargetableTarget (ex-`RULE_BIT41_ALLOW_NON_TARGETABLE`) -> RadBombardment (1116)
    TargetIsCasterOrEnemy   (ex-`RULE_BIT57_CASTER_OR_ENEMY`)      -> HarbingerOfDestruction (1008)

PORTEURS (gate de confrontabilite) : `necroOverlord` (1009) et `admecDominus` (1116) sont dans
`rl_duel.py build --list-pool` -> confrontables. Le 3e, `necroPlasmancer` (1008), est `lineup` mais
ABSENT du pool au rank courant, et ses cinq autres porteurs sont npc : `TargetIsCasterOrEnemy` n'est
donc PAS confrontable live -- c'est dit ici plutot que masque par un vert.

CONTRAT (le meme que `test_targeting_masks_live.py`) :

    natif == 0   =>  port == 0        STRICT (le port n'invente JAMAIS un refus)
    natif != 0   =>  port == natif    (regle PORTEE)
                 ou  port == 0        (regle NON PORTEE -> permissif)
    jamais       :   port != 0 et port != natif

DISCRIMINANCE : le probe ECHOUE aussi si `TargetIsCaster` n'a mordu sur AUCUNE paire -- un vert
obtenu sans que le bit renomme ait ete exerce ne prouverait rien.

Usage :
    python probe_164_targeting_single_source.py [--board MC1_67] [--seed 777]

Sortie ASCII only (console Windows cp1252).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import rl_collect_batch as R

from engine.runner.abilities.targeting_rule import TargetingRule as TR

PYDIR = Path(__file__).resolve().parent

P_UNITS = ["necroOverlord", "admecDominus", "necroDestroyer"]
A_UNITS = ["darkaCompanion", "astraBullgryn", "eldarRanger"]

# (abilityType, visualId du porteur) -- table FIXE plutot que la lecture des abilities de
# `decisionView`, comme `test_targeting_masks_live.py` : un porteur absent doit ECHOUER, pas
# reduire silencieusement le scenario a rien.
CAS = [
    (1009, "necroOverlord"),      # ResurrectionOrb  -- pose TargetIsCaster (+ self_cast)
    (1116, "admecDominus"),       # RadBombardment   -- pose AllowUntargetableTarget
    (1006, "necroDestroyer"),     # MultiThreatEliminator -- volet PORTEE (temoin non renomme)
]

# Raisons rendues EN AMONT du filtre de cible par `AttackQuery$$GetInvalidTargetReason`
# (cooldown / munitions / deja utilisee ce tour) : hors du perimetre de `is_invalid_target`.
HORS_CONTRAT = {int(TR.ValidRequest), int(TR.AlreadyUseThisTurn)}

# Le bit dont le re-mapping serait le plus destructeur ET qui est exerçable ici : sans lui, le
# scenario n'a rien discrimine.
BIT_DISCRIMINANT = TR.TargetIsCaster


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _hexv(h):
    try:
        return int(str(h), 16)
    except (TypeError, ValueError):
        return 0


def _noms(masque: int) -> str:
    if not masque:
        return "-"
    out = [m.name for m in TR if int(m) and not (int(m) & (int(m) - 1)) and (masque & int(m))]
    return "|".join(out) or hex(masque)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", default="777")
    args = ap.parse_args()

    from engine.entities.pathfinding.board import Board
    from engine.runner.abilities import ABILITY_CLASSES
    from engine.runner.abilities.targeting import is_invalid_target
    from engine.runner.snapshot import load_state

    sid = R._resolve_session()
    echecs, exerces, opposes = [], {}, {}
    paires = 0

    with tempfile.TemporaryDirectory(prefix="p164_") as tmpdir:
        state_file = Path(tmpdir) / "state_164.json"
        argv = [sys.executable, "rl_duel.py", "build", "--seed", str(args.seed),
                "--board", args.board, "--p-units", ",".join(P_UNITS),
                "--a-units", ",".join(A_UNITS), "--no-ai", "--state-file", str(state_file)]
        p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if not state_file.exists():
            print("[build] KO:", (p.stderr or p.stdout or "")[-400:])
            return 1
        rid = json.loads(state_file.read_text())["runnerId"]

        def rpc(m, b, t=90):
            return _unwrap(R._rpc(sid, m, [b], timeout=t))

        try:
            bg = rpc("boardGraph", {"runnerId": rid}, 60)
            board = Board(bg["tiles"], adjacency="evenq")
            # Purge les `initialCooldownTurns` : tant qu'ils tiennent, le natif rend `ValidRequest`
            # pour TOUTE cible et le filtre de cible n'est jamais atteint.
            for _ in range(6):
                rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)

            dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
            ob = rpc("observeBattle", {"runnerId": rid}, 40)
            snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
            vivants = [u for u in (dec.get("units") or []) if u.get("alive")]
            print("runner %d  board=%s  %d unites vivantes" % (rid, args.board, len(vivants)))

            par_visuel = {}
            for u in vivants:
                par_visuel.setdefault(u.get("visualId"), int(u["id"]))

            for at, vis in CAS:
                cid = par_visuel.get(vis)
                if cid is None:
                    print("PORTEUR ABSENT : %s (ability %d) -- le harnais n'a pas monte la "
                          "bataille voulue (visualIds vus : %s)"
                          % (vis, at, sorted(v for v in par_visuel if v)))
                    return 1
                klass = ABILITY_CLASSES[at]
                assert getattr(klass, "TARGETING_OPTIONS", None) is not None
                print("  ability %-5d caster u%-3d %-16s masque=%s"
                      % (at, cid, vis, _noms(int(klass.TARGETING_OPTIONS.rules))))
                for tgt in vivants:
                    tid = int(tgt["id"])
                    r = rpc("abilityReason", {"runnerId": rid, "casterId": cid,
                                              "abilityType": at, "targetId": tid}, 60) or {}
                    natif = _hexv((r.get("targetReason") or {}).get("hex"))
                    if natif in HORS_CONTRAT:
                        continue
                    state = load_state(dec, ob, snap, board=board)
                    port = int(is_invalid_target(state, cid, tid, klass()) or 0)
                    paires += 1
                    if natif:
                        exerces[_noms(natif)] = exerces.get(_noms(natif), 0) + 1
                    if port:
                        opposes[_noms(port)] = opposes.get(_noms(port), 0) + 1
                    if port and port != natif:
                        echecs.append("ability %d caster u%d cible u%d : port=%s natif=%s"
                                      % (at, cid, tid, _noms(port), _noms(natif)))
        finally:
            rpc("disposeRunner", {"runnerId": rid}, 60)

    print()
    print("%d paires (caster, ability, cible) confrontees au natif" % paires)
    print("raisons NATIVES rencontrees :")
    for nom, n in sorted(exerces.items(), key=lambda kv: (-kv[1], kv[0])):
        print("  %-40s %d" % (nom, n))
    print("raisons OPPOSEES PAR LE PORT :")
    for nom, n in sorted(opposes.items(), key=lambda kv: (-kv[1], kv[0])):
        print("  %-40s %d" % (nom, n))

    if echecs:
        print()
        print("DIVERGENCES port != natif (et port != 0) :")
        for e in echecs:
            print("  " + e)
        return 1

    manquants = [c for c in (exerces, opposes)
                 if not any(BIT_DISCRIMINANT.name in nom for nom in c)]
    if manquants:
        print()
        print("NON DISCRIMINANT : %s n'a pas mordu DES DEUX COTES -- un vert obtenu sans exercer "
              "ce bit ne prouve rien sur son re-mapping." % BIT_DISCRIMINANT.name)
        return 1

    print()
    print("OK: contrat de fidelite tenu sur les %d paires, et %s a mordu cote NATIF et cote PORT "
          "(bit renomme EXERCE, verdicts concordants)" % (paires, BIT_DISCRIMINANT.name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
