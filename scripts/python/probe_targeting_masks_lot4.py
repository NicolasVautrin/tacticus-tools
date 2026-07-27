"""Probe -- confronte les `TARGETING_OPTIONS` posees sur necrons/orks/votann/genestealer
au verdict NATIF, cible par cible.

ORACLE = le RPC `abilityReason` (`IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason`
+ `$$GetInvalidCasterReason` via `AttackQuery`), qui rend le `TargetingRule` rompu en HEX et en NOMS.
CONFRONTE = `engine.runner.abilities.targeting.get_invalid_target_reason` /
`get_invalid_caster_reason` sur l'etat charge du MEME runner.

CRITERE (le seul qui compte) :
  * FAUX REFUS = le port refuse une cible que le natif ACCEPTE  -> FATAL (un gate faux casse des
    casts legitimes, en silence). C'est le risque introduit par un masque errone.
  * BIT DIFFERENT quand les DEUX refusent -> ANOMALIE a expliquer (le port doit rendre la MEME
    regle que le natif, pas seulement « un » refus).
  * Le natif refuse / le port accepte -> PERMISSIF : attendu pour toute regle NON PORTEE
    (inventaire en tete de `targeting.py`). Compte, pas fatal.

Un lot dont AUCUNE ligne n'est en REFUS des deux cotes n'aurait rien prouve : le probe compte donc
aussi les REFUS CONCORDANTS et sort en erreur s'il n'y en a aucun.

Usage :
    python probe_targeting_masks_lot4.py [--board MC1_67] [--seed 777] [--groups pool,inject,mow]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import rl_collect_batch as R

PYDIR = Path(__file__).resolve().parent

# (visualId du PORTEUR, ActiveAbilityType, nom) -- les 13 abilities du lot, par groupe de runner.
# `pool`   : porteurs presents dans `rl_duel build --list-pool` (rank 17).
# `inject` : porteurs HORS seed BC -> `catalog_inject.py` (cf. runner.md 1bis).
# `mow`    : Machine of War (entite hors plateau, casterId = machineId).
GROUPS = {
    "pool": {
        "p_units": ["necroOverlord", "necroDestroyer", "genesPrimus", "genesKelermorph",
                    "custoKyrus"],
        "a_units": ["eldarRanger", "astraBullgryn", "darkaCompanion"],
        "inject": [],
        "mow": None,
        "cases": [("necroOverlord", 1009, "ResurrectionOrb"),
                  ("necroDestroyer", 1006, "MultiThreatEliminator"),
                  ("genesPrimus", 1179, "CultDemagogue"),
                  ("genesKelermorph", 1180, "HeroicFusillade"),
                  ("custoKyrus", 1202, "VigilanceEternal")],
    },
    # ⚠ `necroPlasmancer` (porteur de HarbingerOfDestruction 1008) est dans
    # `rl_collect_batch.UNSPAWNABLE_FALLBACK` -- il throw au spawn, donc AUCUN runner ne peut le
    # porter. Et le proxy « caster arbitraire + abilityType=1008 » est REFUTE par
    # `probe_targeting_reason_by_type.py` : `AttackQuery$$GetInvalidTargetReason` resout l'ability
    # sur les ACTIVES DE L'ATTAQUANT, pas par un registre global -- un caster qui ne la porte pas
    # rend `ValidRequest` (0x1) sans consulter le moindre `TargetingOptions`. 1008 est donc
    # NON CONFRONTABLE LIVE (masque LU au decompile, gate porte, mesure impossible).
    "inject": {
        "p_units": ["necroChronomancer", "votanBeserk", "votanIronmaster", "votanUthar"],
        "a_units": ["eldarRanger", "astraBullgryn", "darkaCompanion"],
        "inject": ["necroChronomancer", "votanBeserk", "votanIronmaster", "votanUthar"],
        "mow": None,
        "cases": [("necroChronomancer", 1226, "Chronometron"),
                  ("votanBeserk", 1221, "AugmentedAssault"),
                  ("votanIronmaster", 1206, "GravitonRifle"),
                  ("votanUthar", 1207, "AncestralFortune")],
    },
    "steeljack": {
        "p_units": ["votanMemnyr", "necroOverlord"],
        "a_units": ["eldarRanger", "astraBullgryn"],
        "inject": ["votanMemnyr"],
        "mow": None,
        "cases": [("votanMemnyr", 1219, "IronkinSteeljack")],
    },
    # Roster ALIGNE sur `tests/engine/runner/test_mow_targeting_predicate_live.py` (le seul setup
    # ou 1200 est castable) : des ORKS allies, indispensables au predicat dynamique
    # `SquigLaunchasAbility$$GetDynamicInvalidTargetReason` (>= 1 Ork allie OU >= 2 allies adjacents
    # a la cible).
    "mow": {
        "p_units": ["orksNob", "orksBigMek", "necroDestroyer"],
        "a_units": ["ultraTitus", "astraBullgryn"],
        "inject": [],
        "mow": "orksRukkatrukk",
        # ORACLE DIFFERENT POUR LES MoW. `abilityReason` -> `AttackQuery$$GetInvalidTargetReason`
        # resout l'ability par `ActiveAbilityComponent.GetOrNull(<ActiveAbilitiesComponent>, type)`
        # et rend `ValidRequest` (0x1) si elle n'y est pas. Or les abilities d'une MACHINE OF WAR
        # sont des abilities-MACHINE (Primary/Secondary, lues par `mowAbilityTypes` cote hooks), PAS
        # des entrees d'`ActiveAbilitiesComponent` : 1200 rend `ValidRequest` sur toutes les cibles
        # et a tous les tours (MESURE : 12 tours d'attente, roster Ork aligne sur
        # `test_mow_targeting_predicate_live.py` -- inchange). L'instrument ne s'applique donc pas a
        # ce porteur. On bascule sur l'oracle `abilityTargets`, qui LUI passe par `mowAbilityTypes`
        # et rend les cibles LEGALES natives : le critere devient « le port refuse-t-il une cible que
        # le natif OFFRE ? » -- exactement le risque de FAUX REFUS.
        "oracle": "targets",
        "escort_in": True,
        "cases": [("orksRukkatrukk", 1200, "SquigLaunchas"),
                  ("orksRukkatrukk", 1201, "SquigMine")],
    },
    # MESURE DU BIT 57 `CasterOrEnemyTargeting` -- porte dans `targeting.py` pour
    # HarbingerOfDestruction (1008), dont le porteur `necroPlasmancer` NE SPAWNE PAS. On confronte
    # donc la REGLE (pas l'ability) via **Doombolt (1102, `thousAhriman`, dans le pool)** : son
    # `DoomboltAbility$$.ctor` copie EXACTEMENT LE MEME preset statique `TargetingOptions` `+0x3c0`
    # (puis overload PRESET+flags avec flags 0) -> masque IDENTIQUE `0x200000000000004`. Doombolt
    # n'etant pas dans `ABILITY_CLASSES`, le cote PORT est evalue sur un STUB portant ce masque :
    # c'est bien la branche `RULE_BIT57_CASTER_OR_ENEMY` de `get_invalid_target_reason` qui est
    # confrontee au natif, cible par cible.
    "bit57": {
        "p_units": ["thousAhriman", "necroOverlord"],
        "a_units": ["eldarRanger", "astraBullgryn"],
        "inject": [],
        "mow": None,
        # RAPPROCHEMENT OBLIGATOIRE : la PORTEE (`TargetIsInRange`, NON PORTEE) est evaluee AVANT le
        # bit 57 dans la cascade native -- aux distances de spawn elle domine TOUT et la regle testee
        # n'est jamais atteinte (mesure : natif = TargetIsInRange sur les 4 cibles). On AMENE donc
        # les allies au contact du caster (doctrine « deplace les unites », jamais « bloque par la
        # geometrie de spawn »).
        "close_in": True,
        "cases": [("thousAhriman", 1102, "Doombolt(stub bit57)", 0x200000000000004)],
    },
}

# Regles que le port n'implemente PAS (inventaire en tete de `targeting.py`). Quand le natif refuse
# par l'une d'elles ET que le port refuse par une autre, ce n'est PAS une divergence de verdict : le
# natif s'arrete a la PREMIERE regle rompue de SA cascade, et celle-ci precede la regle portee.
UNPORTED_RULES = (
    0x8000000,          # TargetIsInRange (portee : depend de `TargetingQuery$$GetRange`)
    0x2,                # TargetMatchesDynamicRule quand l'ability ne surcharge pas le predicat
    0x200000000,        # bit 33 : HasTrait(0xd) interdit
    0x800000,           # TargetIsAllowedForCaster (forced targets / Taunt)
    0x800,              # AddCasterIfAtLeastOneTarget (via GetCasterNotAddedReason)
    0x40000000000000,   # AlreadyUsedThisTurn (AttackQuery, en amont du filtre)
)


class _StubAbility:
    """Porteur de masque SANS behaviour -- sert a confronter une REGLE de `targeting.py` quand
    l'ability qui la porte n'est pas dans `ABILITY_CLASSES` (cf. le groupe `bit57`)."""
    __slots__ = ("TARGETING_OPTIONS",)

    def __init__(self, rules, self_cast=False):
        from engine.runner.abilities.targeting import TargetingOptions
        self.TARGETING_OPTIONS = TargetingOptions(rules=int(rules), self_cast=bool(self_cast))

    def get_dynamic_invalid_target_reason(self, state, caster_id, target_id) -> int:
        return 0


def _unwrap(r):
    return r.get("result") if isinstance(r, dict) and "result" in r else r


def _hex_to_int(h):
    if not h:
        return 0
    try:
        return int(str(h), 16)
    except ValueError:
        return 0


def _inject_bc(units, tmpdir):
    """`catalog_inject.py --units ...` -> chemin ABSOLU d'un seed BC augmente (le partage intact)."""
    out = Path(tmpdir) / "bc_lot4.json"
    p = subprocess.run([sys.executable, "catalog_inject.py", "--units", ",".join(units),
                        "--out", str(out)],
                       cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not out.exists():
        print("  [inject] KO:", (p.stderr or p.stdout or "")[-300:])
        return None
    return str(out)


def _close_in(rpc, rid, caster_vis, ability_id, max_turns=14):
    """MARCHE le caster (et ses allies) jusqu'a ce que l'ability ait des CIBLES.

    Sans ca la regle testee n'est jamais ATTEINTE. Mesure d'etage a l'appui
    (`probe_bit57_diag.py`) : aux distances de spawn, c'est le volet CASTER de
    `IdunBattle.Core.Services.AttackQuery$$GetInvalidCasterReason` qui rend `TargetIsInRange`
    (0x8000000) -- « aucune cible atteignable d'ici » -- et l'overload 5 arguments de
    `TargetingQuery$$GetInvalidTargetReason` COURT-CIRCUITE alors sur cette raison caster
    (`if (casterReason.IsInvalid()) return casterReason;`). Tous les `targetReason` valent donc
    0x8000000 et AUCUNE regle de cible n'est evaluee. Rapprocher les seuls ALLIES ne suffit pas :
    il faut un ENNEMI a portee pour que le volet caster passe.

    Patron repris de `probe_115_ability_reason.py` : tant que `abilityTargets` ne rend rien, on
    avance le caster vers l'ennemi le plus proche, on ramene les allies au contact, puis `endturn`.
    Le caster PEUT bouger ici : aucun des masques mesures par ce groupe ne pose `CasterHasNotMoved`
    (0x10) -- a re-verifier si on ajoute un groupe dont le masque le pose."""
    import hexgeo

    def _pos(u):
        q = (u or {}).get("pos") or {}
        return (q.get("col"), q.get("row"))

    for _ in range(max_turns):
        dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        units = [u for u in (dec.get("units") or []) if u.get("alive")]
        caster = next((u for u in units if u.get("visualId") == caster_vis), None)
        if caster is None:
            return
        if dec.get("currentPlayer") != caster.get("owner"):
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        at = rpc("abilityTargets", {"runnerId": rid, "unitId": caster["id"],
                                    "abilityType": int(ability_id)}, 90)
        # `fromHere` (cast SANS bouger, depuis la tuile courante) et NON `targets` (superset « ce
        # tour, MOVE inclus ») : `abilityReason` evalue depuis `getUnitMainTile(caster)`, donc seul
        # `fromHere` garantit que le volet CASTER passera.
        n = sum(int(ab.get("fromHereCount") or 0)
                for u in (at.get("units") or []) for ab in (u.get("abilities") or []))
        if n > 0:
            print("    [close-in] cibles castables SANS bouger: %d" % n)
            # DERNIERE PASSE : coller les ALLIES au caster SANS bouger le caster (sa tuile fixe
            # `fromHere`). Sans elle, l'allie reste hors portee et le natif s'arrete sur
            # `TargetIsInRange` : le cas de REFUS du bit 57 (« un allie n'est ni le caster ni un
            # ennemi attaquable ») ne serait jamais confronte a son vrai code.
            mov = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
            for m in (mov.get("units") or []):
                uid = m.get("unitId")
                if uid == caster["id"]:
                    continue
                tiles = [(t["col"], t["row"]) for t in (m.get("tiles") or [])
                         if t.get("col") is not None]
                if not tiles:
                    continue
                best = min(tiles, key=lambda t: (hexgeo.distance(t, _pos(caster)), t))
                rpc("applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": uid, "to": {"col": best[0], "row": best[1]}}}, 60)
                print("    [close-in] allie u%s -> %s (dist %d du caster)"
                      % (uid, best, hexgeo.distance(best, _pos(caster))))
            return
        foes = [u for u in units if u.get("owner") != caster.get("owner")]
        if not foes:
            return
        goal = min(foes, key=lambda e: hexgeo.distance(_pos(caster), _pos(e)))
        mov = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        for m in (mov.get("units") or []):
            uid = m.get("unitId")
            tiles = [(t["col"], t["row"]) for t in (m.get("tiles") or [])
                     if t.get("col") is not None]
            if not tiles:
                continue
            # le caster marche vers l'ennemi ; les allies se collent au caster
            anchor = _pos(goal) if uid == caster["id"] else _pos(caster)
            best = min(tiles, key=lambda t: (hexgeo.distance(t, anchor), t))
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": uid, "to": {"col": best[0], "row": best[1]}}}, 60)
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)


def _allies_to_enemy(rpc, rid, caster_vis, ability_id, max_turns=10):
    """Amene les ALLIES au CONTACT d'un ennemi jusqu'a ce que l'ability offre des cibles.

    Necessaire pour SquigLaunchas (1200) : son
    `IdunBattleLogic.Entities.Abilities.Active.Loki.SquigLaunchasAbility$$GetDynamicInvalidTargetReason`
    n'autorise une cible que si >= 1 Ork allie (ou >= 2 allies) lui est ADJACENT -- d'ou « 0 cible au
    spawn », deja constate par `test_mow_targeting_predicate_live.py`. Le caster est une MoW
    HORS-PLATEAU : c'est donc l'ESCORTE qu'on deplace, pas lui."""
    import hexgeo

    def _pos(u):
        q = (u or {}).get("pos") or {}
        return (q.get("col"), q.get("row"))

    for _ in range(max_turns):
        dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        units = [u for u in (dec.get("units") or []) if u.get("alive")]
        mrow = next((m for m in (dec.get("mows") or []) if m.get("visualId") == caster_vis), None)
        if mrow is None:
            return
        cid = int(mrow.get("casterId") if mrow.get("casterId") is not None else mrow.get("id"))
        at = rpc("abilityTargets", {"runnerId": rid, "unitId": cid,
                                    "abilityType": int(ability_id)}, 90)
        n = sum(1 for u in (at.get("units") or []) for ab in (u.get("abilities") or [])
                for t in (list(ab.get("fromHere") or []) + list(ab.get("targets") or []))
                if t.get("kind") == "unit")
        if n > 0:
            print("    [allies-to-enemy] %d cible(s)-unite offerte(s) -- stop" % n)
            return
        if dec.get("currentPlayer") != mrow.get("owner"):
            rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
            continue
        foes = [u for u in units if u.get("team") != mrow.get("team")]
        if not foes:
            return
        mov = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
        for m in (mov.get("units") or []):
            tiles = [(t["col"], t["row"]) for t in (m.get("tiles") or [])
                     if t.get("col") is not None]
            if not tiles:
                continue
            goal = min(foes, key=lambda e: hexgeo.distance(tiles[0], _pos(e)))
            best = min(tiles, key=lambda t: (hexgeo.distance(t, _pos(goal)), t))
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": m.get("unitId"),
                "to": {"col": best[0], "row": best[1]}}}, 60)
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    print("    [allies-to-enemy] aucune cible offerte apres %d tours" % max_turns)


def _wait_castable(rpc, rid, caster_vis, ability_id, max_turns=12):
    """Fait AVANCER les tours jusqu'a ce que l'ability soit reellement castable par son porteur.

    Motif : `IdunBattle.Core.Services.AttackQuery$$GetInvalidTargetReason` sort AVANT le filtre de
    ciblage (`comp == null || !CanCurrentlyBeUsed || comp+0x44 == 0`) et rend `ValidRequest` (0x1).
    Tant que ce court-circuit s'applique -- typiquement une MACHINE OF WAR au tour 1, dont l'ability
    n'est pas encore chargee -- AUCUNE regle de cible n'est evaluee et la mesure ne prouve rien.
    On ne conclut donc pas « pas de gate » : on attend que l'ability murisse."""
    for _ in range(max_turns):
        dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        rows = list(dec.get("mows") or []) + [u for u in (dec.get("units") or [])]
        src = next((r for r in rows if r.get("visualId") == caster_vis), None)
        if src is None:
            return
        cid = int(src.get("casterId") if src.get("casterId") is not None else src.get("id"))
        probe_tgt = next((u for u in (dec.get("units") or [])
                          if u.get("alive") and int(u["id"]) != cid), None)
        if probe_tgt is None:
            return
        nat = rpc("abilityReason", {"runnerId": rid, "casterId": cid,
                                    "abilityType": int(ability_id),
                                    "targetId": int(probe_tgt["id"])}, 60)
        hexv = _hex_to_int(((nat or {}).get("targetReason") or {}).get("hex"))
        if hexv != 0x1:
            print("    [wait-castable] %s / %d castable (targetReason=0x%x)"
                  % (caster_vis, int(ability_id), hexv))
            return
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    print("    [wait-castable] %s / %d TOUJOURS ValidRequest apres %d tours"
          % (caster_vis, int(ability_id), max_turns))


def run_group(sid, name, cfg, board, seed, tmpdir):
    """Construit UN runner, confronte natif vs port pour chaque cas du groupe.
    Rend (n_ok, n_false_refusal, n_bit_mismatch, n_concordant_refusal, n_permissive)."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.abilities.handler import ABILITY_CLASSES
    from engine.runner.abilities.targeting import (get_invalid_caster_reason,
                                                   get_invalid_target_reason)
    from engine.runner.snapshot import load_state

    state_file = Path(tmpdir) / ("state_%s.json" % name)
    state_file.unlink(missing_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board,
            "--p-units", ",".join(cfg["p_units"]), "--a-units", ",".join(cfg["a_units"]),
            "--no-ai", "--state-file", str(state_file)]
    if cfg["inject"]:
        bc = _inject_bc(cfg["inject"], tmpdir)
        if bc is None:
            return (0, 0, 0, 0, 0, 0)
        argv += ["--seed-bc", bc]
    if cfg["mow"]:
        argv += ["--p-mow", cfg["mow"]]
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state_file.exists():
        print("  [build] KO:", (p.stderr or p.stdout or "")[-400:])
        return (0, 0, 0, 0, 0, 0)
    rid = json.loads(state_file.read_text())["runnerId"]

    def rpc(m, b, t=90):
        return _unwrap(R._rpc(sid, m, [b], timeout=t))

    n_ok = n_false = n_bit = n_both = n_perm = n_skip = 0
    try:
        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        board_obj = Board(bg["tiles"], adjacency="evenq")
        if cfg.get("close_in"):
            _close_in(rpc, rid, cfg["cases"][0][0], cfg["cases"][0][1])
        if cfg.get("wait_ready"):
            _wait_castable(rpc, rid, cfg["cases"][0][0], cfg["cases"][0][1])
        if cfg.get("escort_in"):
            _allies_to_enemy(rpc, rid, cfg["cases"][0][0], cfg["cases"][0][1])
        dec = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
        ob = rpc("observeBattle", {"runnerId": rid}, 40)
        snap = rpc("combatSnapshot", {"runnerId": rid}, 60)
        st = load_state(dec, ob, snap, board=board_obj)
        units = [u for u in (dec.get("units") or []) if u.get("alive")]
        by_vis = {}
        for u in units:
            by_vis.setdefault(u.get("visualId"), u)
        mows = {m.get("visualId"): m for m in (dec.get("mows") or [])}

        for case in cfg["cases"]:
            vis, ab_id, ab_name = case[0], case[1], case[2]
            stub_rules = case[3] if len(case) > 3 else None
            if stub_rules is not None:
                ability = _StubAbility(stub_rules)
            else:
                klass = ABILITY_CLASSES.get(ab_id)
                if klass is None:
                    print("  [%s %d] PAS dans ABILITY_CLASSES -- skip" % (ab_name, ab_id))
                    continue
                ability = klass()
            opts = getattr(ability, "TARGETING_OPTIONS", None)
            src = by_vis.get(vis) or mows.get(vis)
            if src is None:
                print("  [%s %d] porteur %s ABSENT du runner -- skip" % (ab_name, ab_id, vis))
                continue
            # ⚠ PIEGE MoW : une entree `decisionView.mows[]` porte DEUX ids DIFFERENTS -- `id`
            # (mesure : 75) et `casterId` (81). C'est `casterId` qui designe l'entite Machine
            # portant les abilities, et c'est sous CET id que `snapshot._load_machines` materialise
            # la MoW offline. Prendre `id` donne un caster INEXISTANT cote port -> `is_actor` False
            # -> `UnitsCanAttackEachOther` rend False pour TOUT LE MONDE -> `TargetIsEnemy` refuse
            # meme les ennemis (faux refus de MESURE, pas de port -- diagnostique par
            # `probe_mow_caster_resolution.py`). Cote natif le meme mauvais id designe une autre
            # entite et rend « valide » partout : les deux cotes etaient faux, dans des sens
            # opposes. On prend donc `casterId` EN PRIORITE.
            cid = int(src.get("casterId") if src.get("casterId") is not None else src.get("id"))
            print("  [%s %d] caster=%s u%d rules=%s"
                  % (ab_name, ab_id, vis, cid,
                     ("0x%x" % opts.rules) if opts is not None else "None"))

            if cfg.get("oracle") == "targets":
                # ORACLE `abilityTargets` : toute cible-UNITE que le natif OFFRE doit etre ACCEPTEE
                # par le port (port != 0 => faux refus). L'inverse n'est pas exigible : une cible
                # non offerte peut l'etre pour une regle NON PORTEE.
                at = rpc("abilityTargets", {"runnerId": rid, "unitId": cid,
                                            "abilityType": ab_id}, 90)
                offered = []
                for un in (at.get("units") or []):
                    for ab in (un.get("abilities") or []):
                        for t in list(ab.get("fromHere") or []) + list(ab.get("targets") or []):
                            if t.get("kind") == "unit" and t.get("targetId") is not None:
                                offered.append(int(t["targetId"]))
                offered = sorted(set(offered))
                print("    cibles-unite OFFERTES par le natif: %s" % (offered or "aucune"))
                if not offered:
                    print("    -> aucune cible offerte : rien a confronter pour cette ability")
                    n_skip += 1
                for uid in offered:
                    pt = int(get_invalid_target_reason(st, cid, uid, ability) or 0)
                    if pt:
                        print("    u%-4d OFFERTE par le natif mais port=0x%x  FAUX-REFUS"
                              % (uid, pt))
                        n_false += 1
                    else:
                        print("    u%-4d OFFERTE et acceptee par le port          OK" % uid)
                        n_ok += 1
                        n_both += 1
                continue

            for u in units:
                uid = int(u["id"])
                nat = rpc("abilityReason", {"runnerId": rid, "casterId": cid,
                                            "abilityType": ab_id, "targetId": uid}, 60)
                if not (isinstance(nat, dict) and nat.get("ok")):
                    print("    u%-4d natif INDISPO: %s" % (uid, str(nat)[:120]))
                    continue
                nt = _hex_to_int(((nat.get("targetReason") or {}).get("hex")))
                nc = _hex_to_int(((nat.get("casterReason") or {}).get("hex")))
                names = ",".join((nat.get("targetReason") or {}).get("reasons") or []) or "-"
                pt = int(get_invalid_target_reason(st, cid, uid, ability) or 0)
                pc = int(get_invalid_caster_reason(st, cid, ability) or 0)
                # `ValidRequest` (0x1) = `AttackQuery$$GetInvalidTargetReason` a REFUSE EN AMONT du
                # filtre (`comp == null || !CanCurrentlyBeUsed || comp+0x44 == 0`) : l'ability n'est
                # pas castable par ce caster a cet instant. AUCUNE regle de ciblage n'a ete evaluee
                # -> la ligne n'est PAS exploitable, ni comme accord ni comme desaccord. La compter
                # « valide » fabriquerait de faux FAUX-REFUS (mesure MoW : 2 lignes).
                if nt == 0x1:
                    n_skip += 1
                    print("    u%-4d %-16s ally=%-5s natif=ValidRequest (ability non castable ICI)"
                          " -- ligne non exploitable"
                          % (uid, str(u.get("visualId"))[:16],
                             str(u.get("owner") == src.get("owner"))))
                    continue
                nat_t = nt
                verdict = "OK"
                if pt and not nat_t:
                    # Le port refuse, le natif ACCEPTE : la seule categorie FATALE.
                    verdict = "FAUX-REFUS"; n_false += 1
                elif pt and nat_t and pt != nat_t:
                    # Les DEUX refusent, raisons differentes. Acceptable SI la raison native est une
                    # regle NON PORTEE : le natif s'arrete a la premiere regle rompue de SA cascade,
                    # qui precede celle que le port sait evaluer. Sinon = vraie anomalie.
                    if nat_t in UNPORTED_RULES:
                        verdict = "refus/ordre-cascade"; n_both += 1; n_ok += 1
                    else:
                        verdict = "BIT-DIFF"; n_bit += 1
                elif pt and nat_t:
                    verdict = "REFUS-CONCORDANT"; n_both += 1; n_ok += 1
                elif nat_t and not pt:
                    verdict = "permissif"; n_perm += 1; n_ok += 1
                else:
                    n_ok += 1
                same_team = (u.get("owner") == (src.get("owner")))
                print("    u%-4d %-16s ally=%-5s natif=0x%-12x port=0x%-12x %-18s [%s]"
                      % (uid, str(u.get("visualId"))[:16], str(same_team), nat_t, pt,
                         verdict, names))
                if pc and not nc:
                    print("      CASTER FAUX-REFUS port=0x%x natif=0x%x" % (pc, nc))
                    n_false += 1
    finally:
        try:
            R._rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=20)
        except Exception:
            pass
        state_file.unlink(missing_ok=True)
    return (n_ok, n_false, n_bit, n_both, n_perm, n_skip)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--seed", default="777")
    ap.add_argument("--groups", default="pool,inject,steeljack,mow")
    args = ap.parse_args()

    sid = R._resolve_session()
    tot = [0, 0, 0, 0, 0, 0]
    with tempfile.TemporaryDirectory(prefix="tgtmask_") as tmpdir:
        for name in args.groups.split(","):
            name = name.strip()
            cfg = GROUPS.get(name)
            if cfg is None:
                print("groupe inconnu:", name)
                continue
            print("== groupe %s (board=%s seed=%s) ==" % (name, args.board, args.seed))
            res = run_group(sid, name, cfg, args.board, args.seed, tmpdir)
            tot = [a + b for a, b in zip(tot, res)]
    print("\n== TOTAL == lignes_ok=%d FAUX_REFUS=%d BIT_DIFF=%d refus_concordants=%d "
          "permissifs=%d non_exploitables=%d" % tuple(tot))
    if tot[1] or tot[2]:
        print("ECHEC : le port refuse ce que le natif accepte, ou pas la meme regle.")
        return 1
    if tot[3] == 0:
        print("ECHEC : AUCUN refus concordant -- le lot n'a rien prouve (annotation, pas gate).")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
