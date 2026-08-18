"""#889-r10 -- LE MONTAGE QUI TRANCHE : un ALLIE du caster POSE SUR une tuile de ligne de
`1215 InstrumentsOfVengeance`. Le natif le frappe-t-il ?

CE QUE LA RE DIT (decompile = verite, build `t6dpr4k06g`), et que ce probe va CONFRONTER :
`IdunBattle.Entities.Triggers.AreFriendsAbilityTrigger$$ShouldTrigger` resout chacun de ses deux
operandes par le slot **8** d'`ITargetsSelector` = `IdunBattle.DSL.TargetsSelector$$SelectActor`,
dont la surcharge ENTITE de `$$SelectUnit` commence par

    if (EntityExtensions.IsUnitFoot(entity) || EntityExtensions.IsTile(entity))
        entity = UnitExtensions.GetUnit(entity, this.<+0x10 = State>);

=> une TUILE resout en son OCCUPANT, et le camp compare est celui de cet OCCUPANT. Corrobore par un
SECOND etage independant : `IdunBattle.Entities.EntityExtensions$$GetCurrentPlayer` porte lui-meme
une branche `<TileEntity> -> UnitExtensions.GetUnit -> RECURSION`.

PREDICTION FALSIFIABLE : un ALLIE debout sur une tuile de ligne n'est **PAS** frappe (`AreEnemies`
FAUX sur son camp). L'hypothese CONCURRENTE -- « le natif compare l'equipe de la TUILE, qui n'en a
pas, donc `AreEnemies` est VRAI pour tout occupant » -- predit l'INVERSE : l'allie encaisse.

MONTAGE, en DEUX passes (« DEPLACE les unites pour forcer la configuration », doctrine) :
  * passe RECO -- l'allie est pose LOIN ; on caste la phase 1 cote PORT et on relit les tuiles qui
    portent la marque `1518 InstrumentsOfVengeance_LocationTarget` ;
  * passe MESURE -- on REBATIT avec l'allie pose SUR l'une de ces tuiles, on caste (natif ET port),
    on passe le tour, et on lit le delta de PV de l'ALLIE des deux cotes.

NON-VACUITE, assertee et non supposee :
  * l'allie DOIT porter la marque `1518` a l'issue du cast de la passe 2 -- sinon le montage ne
    mesure rien et le probe le DIT (rc 2, « SCENARIO NON MONTE ») ;
  * un ENNEMI doit avoir ete frappe par le meme coup differe -- sinon « l'allie n'a rien pris »
    n'exprimerait que « le coup differe n'est pas parti ».

ASCII only. Runner DISPOSE en sortie (les MIENS, jamais ceux des autres).
"""
from __future__ import annotations

#: Ce qui doit changer pour que ce probe puisse changer d'avis (#486-r12).
DECLENCHEUR = {
    "chemins": ("scripts/python/engine/entities/triggers.py",
                "scripts/python/engine/runner/abilities/behaviours/combat.py",
                "scripts/python/engine/runner/operations/triggers/loki/"
                "instruments_of_vengeance_attack.py",
                "scripts/python/engine/runner/abilities/loki/instruments_of_vengeance.py",
                "data/seed-bc.json", "data/boards/**"),
    "build": True,
    "toujours": False,
    "raison": "Il confronte au NATIF la resolution TUILE -> OCCUPANT du camp lu par `AreEnemies` "
              "sur les tuiles de ligne de la phase 2 de 1215 (residu #889-r10).",
}

import argparse
import json
import os
import sys

PYDIR = os.path.dirname(os.path.abspath(__file__))
if PYDIR not in sys.path:
    sys.path.insert(0, PYDIR)

import probe_889r7_instruments_phase2 as P7          # noqa: E402  (helpers RPC/build partages)

BOSS = "darkaBossLion:4"
BOSS_ID = "darkaBossLion"
BOARD = "CE6_boss"
IOV = 1215
MARQUE = 1518                                        # EffectType.InstrumentsOfVengeance_LocationTarget
#: Un ALLIE du Lion, pris dans le pool du rank courant (`rl_duel build --list-pool`).
ALLIE = "ultraTitus"
#: Position de PARKING de la passe RECO -- volontairement a l'ecart du Lion (3,3).
PARKING = (0, 0)


def _marques_1518(state) -> set:
    """Les POSITIONS `(col,row)` des TUILES qui portent la marque `1518` dans l'etat PORTE.

    Source unique : `probe_889r7_instruments_phase2.marques_off`, qui lit `state.effects.by_unit`
    (le sac est indexe par id d'ENTITE, tuiles COMPRISES -- c'est ainsi que la passe #889-r7 a
    compte ses 13 marques). On ne garde que les cles qui sont des ids de TUILE du board."""
    board = state.board
    if board is None:
        return set()
    out = set()
    for cle, ids in (P7.marques_off(state) or {}).items():
        tid = int(cle)
        if MARQUE in [int(x) for x in ids] and tid in board.by_id:
            c = board.coord(tid)
            out.add((int(c[0]), int(c[1])))
    return out


def _construire(sid, tag, seed, hp_target, allie_pos):
    from pathlib import Path
    state_path = Path(P7.LOGS) / ("probe_889r10_%s.json" % tag)
    args = ["--seed", seed, "--board", BOARD,
            "--explicit-stats", BOSS,
            # ⚠ le SUFFIXE DE PALIER est load-bearing dans `--p-units` : `darkaBossLion` NU est
            # « hors pool » (mesure : `[error] --p-units: hors pool / non spawnables au rank 17`).
            "--p-units", "%s,%s" % (BOSS, ALLIE),
            # ⚠ ROSTER ADVERSE COURT, et c'est LOAD-BEARING : a cinq unites adverses, le second
            # `--p-units` (l'ALLIE) n'entre PAS en bataille -- mesure : `decisionView` ne rend que
            # le Lion en team 1, sans erreur au build. Le no-op serait SILENCIEUX, exactement le
            # vice que ce residu-ci corrige ailleurs.
            "--a-units", "orksNob,tauCrisis",
            # ⚠ `--place` s'apparie sur le TOKEN de `--p-units`, suffixe de palier COMPRIS (mesure :
            # `[error] --place: 'darkaBossLion' n'est pas dans --p-units ['darkaBossLion:4', ...]`).
            "--place", "%s:3,3" % BOSS,
            "--place", "%s:%d,%d" % (ALLIE, allie_pos[0], allie_pos[1]),
            "--a-place", "orksNob:3,4",
            "--a-place", "tauCrisis:2,2"]
    if hp_target:
        args += ["--hp-target", str(hp_target)]
    rid = P7.build(state_path, args)
    return rid


def _caster_et_allie(sid, rid):
    """`(caster_id, allie_id)` lus dans `decisionView` -- par VISUAL ID, jamais par rang."""
    dec = P7.rpc(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    caster = allie = None
    for u in (dec.get("units") or []):
        vid = str(u.get("visualId") or u.get("unitId") or "")
        if "DarkaLion" in vid:
            caster = int(u["id"])
        elif ALLIE.lower() in vid.lower():
            allie = int(u["id"])
    return caster, allie, dec


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--hp-target", default="400000")
    ap.add_argument("--tag", default=str(os.getpid()))
    a = ap.parse_args(argv)

    sid = P7._session()
    P7.bind(sid)

    # ---------------- PASSE 1 : RECO des tuiles de ligne -------------------------------------
    rid1 = _construire(sid, a.tag + "_reco", a.seed, a.hp_target, PARKING)
    try:
        from engine.runner.abilities.handler import ABILITY_CLASSES
        state, _dec = P7.load(sid, rid1)
        caster, allie, _d = _caster_et_allie(sid, rid1)
        if caster is None or allie is None:
            print("[889r10] SCENARIO NON MONTE (reco) : caster=%r allie=%r" % (caster, allie))
            return 2
        P7.seed_offline_rng(state, P7.rpc(sid, "dumpRng", {"runnerId": rid1}, 40) or {})
        ABILITY_CLASSES[IOV]().execute_behaviour(state, caster, caster)
        lignes = sorted(_marques_1518(state))
        print("[889r10] RECO : %d tuiles de ligne -> %r" % (len(lignes), lignes[:20]))
    finally:
        P7.rpc(sid, "disposeRunner", {"runnerId": rid1}, 30)

    if not lignes:
        print("[889r10] SCENARIO NON MONTE : la reco n'a rendu AUCUNE tuile de ligne.")
        return 2

    # On evite la tuile du Lion et celles des ennemis deja poses. Les AUTRES sont essayees UNE PAR
    # UNE : une tuile de ligne peut etre `ForceUnplayable` cote board (mesure : `(0,2)` sur
    # `CE6_boss` -> « tuile INJOUABLE »), et un `build` refuse alors le placement. Ce n'est PAS une
    # geometrie qui bloque le scenario -- c'est une tuile a ecarter.
    interdites = {(3, 3), (3, 4), (2, 2)}
    candidates = [tuple(p) for p in lignes if tuple(p) not in interdites]
    if not candidates:
        print("[889r10] SCENARIO NON MONTE : aucune tuile de ligne LIBRE.")
        return 2

    rid2 = cible = None
    for c in candidates:
        try:
            rid2 = _construire(sid, "%s_mesure_%d_%d" % (a.tag, c[0], c[1]),
                               a.seed, a.hp_target, c)
            cible = c
            break
        except SystemExit:
            print("[889r10] tuile %r REFUSEE au placement -- on essaie la suivante." % (c,))
    if rid2 is None:
        print("[889r10] SCENARIO NON MONTE : aucune des %d tuiles de ligne n'accepte un "
              "placement." % (len(candidates),))
        return 2
    print("[889r10] l'ALLIE %s est pose en %r" % (ALLIE, cible))

    # ---------------- PASSE 2 : MESURE ---------------------------------------------------------
    try:
        from engine.runner.abilities.handler import ABILITY_CLASSES
        state, _dec = P7.load(sid, rid2)
        caster, allie, _d = _caster_et_allie(sid, rid2)
        if caster is None or allie is None:
            # Un `None` ne dit pas SI l'unite manque ou si l'appariement par NOM a rate : on
            # imprime la VENTILATION, jamais le seul zero.
            print("[889r10] SCENARIO NON MONTE (mesure) : caster=%r allie=%r ; unites = %r"
                  % (caster, allie,
                     [(u.get("id"), u.get("visualId") or u.get("unitId"), u.get("team"))
                      for u in (_d.get("units") or [])]))
            return 2
        P7.seed_offline_rng(state, P7.rpc(sid, "dumpRng", {"runnerId": rid2}, 40) or {})
        ABILITY_CLASSES[IOV]().execute_behaviour(state, caster, caster)
        lignes2 = set(tuple(p) for p in _marques_1518(state))
        if tuple(cible) not in lignes2:
            print("[889r10] SCENARIO NON MONTE : l'allie n'est PAS sur une tuile marquee 1518 "
                  "(cible=%r, lignes=%r)" % (tuple(cible), sorted(lignes2)[:20]))
            return 2
        print("[889r10] NON-VACUITE OK : l'allie est sur une tuile marquee 1518.")

        # NON-VACUITE (2) : l'allie doit VRAIMENT etre un ALLIE. Sans ce cran, « il n'a rien pris »
        # pourrait n'exprimer que « c'est un ennemi hors ligne ».
        equipes = {int(u["id"]): u.get("team") for u in (_d.get("units") or [])}
        if equipes.get(allie) != equipes.get(caster) or equipes.get(caster) is None:
            print("[889r10] SCENARIO NON MONTE : l'unite posee n'est PAS de l'equipe du caster "
                  "(caster team=%r, posee team=%r)" % (equipes.get(caster), equipes.get(allie)))
            return 2
        print("[889r10] NON-VACUITE OK : allie u%d et caster u%d sont de la MEME equipe (%r)."
              % (allie, caster, equipes.get(caster)))

        # cast NATIF
        act1 = P7.rpc(sid, "applyAction", {"runnerId": rid2, "captureEvents": True, "action": {
            "kind": "ability", "casterId": caster, "abilityType": IOV, "targetId": caster}}, 120)
        avant = P7.hp_live(sid, rid2)
        # ⚠ LE PAS SE LIT SUR `currentPlayer`, JAMAIS SUR SON NOM (#889-r4/#889-r9) : le cast
        # TERMINE le tour du Lion, donc l'`endturn` qui suit ferme le tour de l'ADVERSAIRE et ROUVRE
        # celui du Lion -- c'est LA que part le coup differe.
        j_apres_cast = (act1 or {}).get("currentPlayer")
        act2 = P7.rpc(sid, "applyAction", {"runnerId": rid2, "captureEvents": True,
                                           "action": {"kind": "endturn"}}, 120)
        j_apres_endturn = (act2 or {}).get("currentPlayer")
        apres = P7.hp_live(sid, rid2)
        dhp = {u: (avant[u], apres[u]) for u in apres if u in avant and avant[u] != apres[u]}
        print("[889r10] currentPlayer : apres_cast=%r apres_endturn=%r" % (j_apres_cast,
                                                                          j_apres_endturn))
        print("[889r10] HP avant = %s" % json.dumps({str(k): v for k, v in sorted(avant.items())}))
        print("[889r10] HP apres = %s" % json.dumps({str(k): v for k, v in sorted(apres.items())}))
        print("[889r10] NATIF dhp = %s" % json.dumps({str(k): list(v) for k, v in dhp.items()}))
        if not dhp:
            # NON-VACUITE (3) : l'allie doit ETRE ENCORE sur sa tuile de ligne au moment ou le coup
            # differe part. Une unite qui a bouge entre-temps « n'a rien pris » pour une tout autre
            # raison -- et ce releve-la se prend LIVE, pas sur l'etat porte.
            # ⚠ LA FORME DU CANAL SE LIT, ELLE NE SE SUPPOSE PAS : `observeBattle` rend la position
            # A PLAT (`col`/`row`) et non sous une cle `pos` -- une lecture `u["pos"]` rendait
            # `(None, None)` et faisait crier « l'allie a QUITTE sa tuile » sur une unite immobile.
            # On accepte les DEUX formes, et on retombe sur `decisionView` si aucune ne repond.
            def _xy(u):
                p = u.get("pos") if isinstance(u.get("pos"), dict) else u
                return (p.get("col"), p.get("row"))
            ob = P7.rpc(sid, "observeBattle", {"runnerId": rid2}, 40) or {}
            pos = {int(u["squadId"]): _xy(u) for u in (ob.get("units") or [])}
            if pos.get(allie, (None, None)) == (None, None):
                dv = P7.rpc(sid, "decisionView",
                            {"runnerId": rid2, "maxRank": 1, "allAbilities": True}, 90) or {}
                pos = {int(u["id"]): _xy(u) for u in (dv.get("units") or [])}
            if pos.get(allie) != tuple(cible):
                print("[889r10] SCENARIO NON MONTE : l'allie a QUITTE sa tuile de ligne "
                      "(attendu %r, lu %r)" % (tuple(cible), pos.get(allie)))
                return 2
            print("[889r10] NON-VACUITE OK : l'allie est ENCORE en %r au coup differe."
                  % (tuple(cible),))
            # Le coup differe part au tour SUIVANT du Lion : si l'`endturn` n'a pas rendu la main,
            # on en pousse un SECOND et on le DIT (jamais un zero silencieux).
            act3 = P7.rpc(sid, "applyAction", {"runnerId": rid2, "captureEvents": True,
                                               "action": {"kind": "endturn"}}, 120)
            apres = P7.hp_live(sid, rid2)
            dhp = {u: (avant[u], apres[u]) for u in apres if u in avant and avant[u] != apres[u]}
            print("[889r10] 2e endturn (currentPlayer=%r) -> dhp = %s"
                  % ((act3 or {}).get("currentPlayer"),
                     json.dumps({str(k): list(v) for k, v in dhp.items()})))

        touche_allie = allie in dhp
        touche_ennemi = any(u != allie for u in dhp)
        print("[889r10] allie (u%d) frappe ? %s" % (allie, touche_allie))
        print("[889r10] au moins un ENNEMI frappe ? %s" % touche_ennemi)
        if not touche_ennemi:
            print("[889r10] SCENARIO DEGENERE : le coup differe n'a frappe PERSONNE -- "
                  "« l'allie n'a rien pris » n'exprime alors RIEN.")
            return 2
        if touche_allie:
            print("[889r10] VERDICT : le natif FRAPPE l'allie -> la RE (`SelectActor` resout la "
                  "TUILE en son OCCUPANT, donc `AreEnemies` FAUX sur un allie) est REFUTEE.")
            return 1
        print("[889r10] VERDICT : OK -- le natif NE FRAPPE PAS l'allie, ce que la RE predit "
              "(`TargetsSelector$$SelectUnit` : `IsTile(e) -> UnitExtensions.GetUnit(e, state)`).")
        return 0
    finally:
        P7.rpc(sid, "disposeRunner", {"runnerId": rid2}, 30)


if __name__ == "__main__":
    raise SystemExit(main())
