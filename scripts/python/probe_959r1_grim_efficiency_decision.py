"""`#959-r1` -- CONFRONTATION de la face DECISION de `GrimEfficiency` (1490).

## Le critere binaire, enonce AVANT la mesure

`#959` a livre la face COMBAT des deux passifs d'AURA Votann (0 ecart sur 33 lignes). La face
DECISION n'avait ete ni portee ni confrontee, et le residu la disait bloquee par un CAPTEUR :
son oracle est `triggeredMoveTrace` (feuille `TriggeredAbilitiesUtility`), dont l'armement est
NOMINATIF mais qui « exige que le capteur soit charge dans la session ».

⚠ **Cette premisse se RE-MESURE avant tout** : `triggeredMoveTraceStatus` repond, dans la session
courante, `installDone: true` avec ses deux state machines resolues. Le capteur EST charge. Ce
probe le verifie a l'etage 0 et sort en rc 2 s'il ne l'est pas -- jamais un verdict.

Le port ajoute par cette tranche
(`engine/playbook/friends_in_range.py::GrimEfficiencyPlaybook`) mirror
`IdunBattle.AI.Playbook.Loki.GrimEfficiencyPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext` :

    range = AbilityConfiguration.GetNumberConstant(config, 0x16)
    units = IBattleQuery.<slot 121 GetSurroundingFriends>(case.unit, case.position, range, 0)
    units.Remove(case.unit)
    yield Fix64(getUtilityVal("GrimEfficiency_FriendsInRange") * units.Count)

La question est donc : **le total NATIF de la feuille `TriggeredAbilitiesUtility`, par (unite,
tuile), egale-t-il celui du port ?**

## Et la CONTRE-EPREUVE, qui est le vrai cran

Un accord ne prouve rien s'il est DEGENERE -- si le terme de `GrimEfficiency` vaut zero partout,
le port avec et le port sans rendent la meme chose, et « 0 ecart » ne mesure que le vide. Le probe
joue donc les MEMES lignes une seconde fois, le playbook RETIRE du registre, et exige que le
verdict CHANGE. Trois issues, toutes nommees :

  * accord AVEC, desaccord SANS  -> le port est confronte ET discriminant : VERDICT OK ;
  * accord AVEC **et** SANS      -> regime DEGENERE : le montage ne mesure pas ce terme (rc 2,
                                    ce n'est PAS une validation) ;
  * desaccord AVEC               -> le port DIVERGE du natif (rc 1).

Le montage n'est pas retranscrit : il est IMPORTE de `probe_959_grim_efficiency_predictive_guidance`
(porteurs HORS POOL amenes par `catalog_inject`, board `MC1_67`, placements calcules), donc les
deux probes ne peuvent pas diverger sur la geometrie.

## Discipline

`triggeredMoveTrace` s'arme NOMINATIVEMENT (`{runnerId}`) : il ne touche pas les mesures des
autres agents. Desarmement dans un `finally`. Le runner est dispose en sortie.

ASCII only (console cp1252).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))


class MontageError(RuntimeError):
    """Un capteur muet, ou un montage degenere, n'est PAS un verdict."""


def _dispose(state_file: Path) -> None:
    if not state_file.exists():
        return
    try:
        subprocess.run([sys.executable, str(HERE / "rl_duel.py"), "dispose",
                        "--state-file", str(state_file)],
                       capture_output=True, text=True, timeout=90)
    except Exception:                                              # noqa: BLE001
        pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", default=None,
                    help="chemin ABSOLU, hors data/ ; defaut = logs/st959r1_<pid>.json")
    a = ap.parse_args()

    import probe_959_grim_efficiency_predictive_guidance as P959
    import probe_443r1a_triggered_move_anchor as P443
    import rl_duel as L

    logs = HERE.parent.parent / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    state = Path(a.state_file) if a.state_file else (logs / ("st959r1_%d.json" % os.getpid()))
    seedbc = logs / ("seed_bc_959r1_%d.json" % os.getpid())
    # Le montage d'origine ecrit dans des chemins FIXES : on les redirige vers les notres pour ne
    # pas se marcher dessus avec un `probe_959` qui tournerait en meme temps.
    P959.STATE, P959.SEED_BC = state, seedbc

    sid = L._resolve_session()

    def rpc(m, body=None, timeout=90, tolerate=False):
        try:
            r = L._rpc(sid, m, [body] if body is not None else [], timeout=timeout)
            return r["result"] if isinstance(r, dict) and "result" in r else r
        except Exception as exc:                                    # noqa: BLE001
            if tolerate:
                return None
            raise MontageError("RPC %s KO : %s" % (m, exc))

    print("== #959-r1 -- face DECISION de `GrimEfficiency` (1490)")

    print("")
    print("=== etape 0 -- le capteur est-il CHARGE ? (la premisse du residu) ===")
    st = rpc("triggeredMoveTraceStatus", {}, 30, tolerate=True)
    pres = P443.check_presence(st)
    print("  [%s] %s" % (pres["status"], pres["message"]))
    if pres["status"] != "present":
        raise MontageError("capteur `triggeredMoveTrace` NON CHARGE -- fenetre de reinject "
                           "requise. Rien n'est conclu.")

    print("")
    print("=== etape 1 -- MONTAGE (importe de probe_959 : porteurs hors pool + placements) ===")
    rid = P959.build()
    print("  runnerId=%d  state=%s" % (rid, state))

    try:
        dec = rpc("decisionView", {"runnerId": rid}, 120)
        by_vis = P959.ids_by_visual(dec)
        print("  unites : %s" % {k: v for k, v in by_vis.items()})

        print("")
        print("=== etape 2 -- ARMEMENT NOMINATIF + tour d'IA a blanc ===")
        rpc("triggeredMoveTraceClear", {"runnerId": rid}, 30, tolerate=True)
        on = rpc("triggeredMoveTraceOn", {"runnerId": rid}, 60, tolerate=True)
        print("  on -> %s" % json.dumps(on, sort_keys=True)[:220])
        try:
            rpc("aiDryRunAllUnits", {"runnerId": rid}, 300, tolerate=True)
            dump = rpc("triggeredMoveTraceDump", {"runnerId": rid, "max": 4000}, 90, tolerate=True)
        finally:
            rpc("triggeredMoveTraceOff", {"runnerId": rid}, 30, tolerate=True)
        entries = (dump or {}).get("entries") or []
        owner = [e for e in entries if e.get("utility") == "TriggeredAbilitiesUtility"]
        print("  %d event(s) captes, dont %d sur la feuille OWNER" % (len(entries), len(owner)))
        if not owner:
            raise MontageError(
                "0 event sur la feuille OWNER alors que le capteur est charge et arme -- le "
                "montage n'a PAS traverse `TriggeredAbilitiesUtility`. Ce n'est pas un verdict.")

        print("")
        print("=== etape 3 -- CONFRONTATION (port AVEC le playbook) ===")
        rows_avec = P443._port_rows(sid, rid, entries, bind=True)
        v_avec = P443.check_value(rows_avec)
        print("  [%s] %s" % (v_avec["status"], v_avec["message"]))

        print("")
        print("=== etape 4 -- CONTRE-EPREUVE (port SANS le playbook) ===")
        from engine.entities.triggered_ability_type import TriggeredAbilityType
        from engine.playbook import adjacent_unit_preference as AUP
        cle = int(TriggeredAbilityType.GrimEfficiency)
        retire = AUP.TRIGGERED_MOVE_PLAYBOOKS.pop(cle, None)
        if retire is None:
            raise MontageError("le playbook 1490 n'est PAS au registre -- la contre-epreuve ne "
                               "mesurerait rien (et l'etape 3 non plus).")
        try:
            # Le cache de `load_playbook` doit voir le registre AMPUTE : on le vide s'il existe.
            for nom in ("_PB_CACHE", "_CACHE"):
                c = getattr(AUP, nom, None)
                if isinstance(c, dict):
                    c.clear()
            rows_sans = P443._port_rows(sid, rid, entries, bind=True)
            v_sans = P443.check_value(rows_sans)
        finally:
            AUP.TRIGGERED_MOVE_PLAYBOOKS[cle] = retire
        print("  [%s] %s" % (v_sans["status"], v_sans["message"]))

        # Le DELTA ligne a ligne : c'est lui qui montre que le terme est NON NUL quelque part.
        #
        # ⚠ L'appariement est POSITIONNEL, pas par cle -- et ce n'est pas un raccourci.
        # DEUX cles ont ete essayees et ont ECHOUE, chacune en perdant des lignes : `(unitId,
        # tile)` reduisait 38 lignes a 10 (les deux feuilles d'une meme tuile s'ecrasent), et
        # `(unitId, utility, tile)` a 20 -- parce qu'un meme triplet reapparait a plusieurs
        # `parentId` du sweep de mouvement, que `_port_rows` ne republie pas. Le delta rendait
        # alors 0 partout : un faux << regime degenere >>, alors que `check_value` voyait, lui,
        # 13 lignes basculer. **Un agregat qui perd des lignes ne peut pas montrer celles qu'il a
        # perdues** -- d'ou l'assertion ci-dessous, qui refuse de conclure si l'alignement casse.
        #
        # Les deux appels iterent les MEMES `entries` dans le MEME ordre : la i-eme ligne de l'un
        # est la i-eme de l'autre. On le VERIFIE au lieu de le supposer.
        if len(rows_avec) != len(rows_sans):
            raise MontageError(
                "les deux passes rendent %d et %d lignes -- l'appariement positionnel serait FAUX"
                % (len(rows_avec), len(rows_sans)))
        for i, (ra, rs) in enumerate(zip(rows_avec, rows_sans)):
            if (ra["unitId"], ra["utility"], ra["tile"]) != (rs["unitId"], rs["utility"], rs["tile"]):
                raise MontageError("desalignement a la ligne %d : %r vs %r" % (i, ra, rs))
        diffs = [(i, ra, rs) for i, (ra, rs) in enumerate(zip(rows_avec, rows_sans))
                 if abs(ra["port"] - rs["port"]) > 1e-9]
        print("  lignes ou le terme `GrimEfficiency` est NON NUL : %d / %d"
              % (len(diffs), len(rows_avec)))
        vus = set()
        for i, ra, rs in diffs:
            k = (ra["unitId"], ra["utility"], ra["tile"])
            if k in vus:
                continue
            vus.add(k)
            if len(vus) > 16:
                break
            print("     u%-4s %-32s tuile=%-9s sans=%-6s avec=%-6s natif=%-6s (delta=%s)"
                  % (ra["unitId"], ra["utility"], ra["tile"], rs["port"], ra["port"],
                     ra["nat"], round(ra["port"] - rs["port"], 6)))

        print("")
        print("=== VERDICT ===")
        ok_avec = v_avec["status"] == "ok"
        ok_sans = v_sans["status"] == "ok"
        if not diffs:
            print("REGIME DEGENERE : le terme `GrimEfficiency` vaut ZERO sur TOUTES les lignes")
            print("  captees. L'accord de l'etape 3 ne mesure donc pas ce port -- il mesure le")
            print("  reste de la feuille. Ce n'est PAS une validation.")
            return 2
        if ok_avec and not ok_sans:
            print("OK : le port est CONFRONTE et DISCRIMINANT.")
            print("  AVEC le playbook : accord avec le natif ; SANS : desaccord.")
            print("  %d ligne(s) portent un terme `GrimEfficiency` non nul." % len(diffs))
            return 0
        if ok_avec and ok_sans:
            print("REGIME DEGENERE : le port tombe juste AVEC **et** SANS le playbook, alors que")
            print("  le terme est non nul sur %d ligne(s). La feuille compense ailleurs, ou la" % len(diffs))
            print("  tolerance de `check_value` absorbe l'ecart. Ce n'est PAS une validation.")
            return 2
        print("DIVERGENCE : le port ne reproduit PAS le natif avec le playbook actif.")
        print("  C'est le resultat qui compte -- le port est a corriger, pas le test.")
        return 1
    finally:
        _dispose(state)
        print("")
        print("[dispose] runner libere (%s)" % state.name)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except MontageError as e:
        print("MONTAGE : %s" % e)
        sys.exit(2)
