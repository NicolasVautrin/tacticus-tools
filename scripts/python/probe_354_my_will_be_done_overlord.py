"""Probe #354-r1 -- MESURE de la face COMBAT de `MyWillBeDoneOverlord` (passif `necroOverlord`,
`TriggeredAbilityType` 0x614 = 1556). Montage NOMME et REUTILISABLE (roster, board, seed, positions
DRIVEES, patchs de stats) -- rien d'inline.

LA QUESTION BINAIRE : quand `necroOverlord` CLOT son activation (`On(0x29 =
UnitFinishedTurnNormally)`), le port fait-il attaquer le MEME allie, sur la MEME cible, avec le MEME
plafond d'attaque que le natif ?

CE QUE LE PROBE MESURE, sans rien supposer :

  M1 -- PREFERENCE DE GROUPE (le discriminant central). Deux allies adjacents ELIGIBLES :
       `necroWarden` (Necron + Hero -> groupe A) et `admecDominus` (Mechanical + Hero, faction
       AdeptusMechanicus -> groupe B). L'Attaque du groupe B est patchee TRES AU-DESSUS de celle du
       groupe A. Les deux hypotheses divergent :
         H1 (l'arbre porte : `A.Otherwise(B)...` PUIS tri par Attaque DANS le groupe elu)
            -> c'est le WARDEN qui attaque, malgre son Attaque plus faible ;
         H2 (un tri global par Attaque, sans chaine de groupes)
            -> c'est le DOMINUS.
       Le montage tranche par l'IDENTITE DE LA VICTIME : chaque allie a SA propre cible adjacente,
       hors de portee de l'autre (portees verifiees, montage REFUSE sinon).

  M2 -- AGREEMENT live-vs-port : meme delta de PV PAR UNITE apres le `finish` de l'Overlord.
       C'est ce qui verifie « meme cible » ET « meme plafond d'attaque » (le montant est
       `min(maxDmg[lvl], round(Attaque x dmgPct%))` -- un cap ou un pourcentage faux donnerait un
       autre degat).

  M3 -- PURGE de la liste persistante. Au tour SUIVANT du porteur, le MEME allie re-attaque. Sans le
       volet `On(0x12) -> ClearAllPersistentData`, il serait definitivement memorise et ne pourrait
       plus jamais etre elu -- c'est la confrontation LIVE de la purge (elle n'est pas observable
       autrement : entre deux activations du porteur il y a toujours >= 1 turn-start).

  M4 -- BRANCHE ELSE. Aucun allie eligible (l'Overlord est seul) -> pas d'attaque, et l'effet
       `MyWillBeDoneOverlord_ExtraDamage` (1581) apparait SUR LUI dans `decisionView`.

Usage :
    python probe_354_my_will_be_done_overlord.py            # les quatre mesures
    python probe_354_my_will_be_done_overlord.py --only m1
ASCII only (console cp1252). Sorties dans `logs/` -- jamais dans `data/`.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PYDIR))

from rl_collect_batch import _resolve_session, _rpc                        # noqa: E402
from engine.entities.pathfinding.board import Board                        # noqa: E402
from engine.runner.snapshot import load_state                              # noqa: E402
from engine.runner.components import HealthComponent                       # noqa: E402

ROOT = PYDIR.parents[1]
STATE = ROOT / "logs" / "runners" / "_354_mwbd_overlord.json"
STATE_SOLO = ROOT / "logs" / "runners" / "_354_mwbd_overlord_solo.json"
STATE_CF = ROOT / "logs" / "runners" / "_354_mwbd_overlord_cf.json"
STATE_NOMECH = ROOT / "logs" / "runners" / "_354_mwbd_overlord_nomech.json"

CARRIER = "necroOverlord"        # le porteur : passif MyWillBeDoneOverlord (+ LivingMetal, Hero)
ALLY_A = "necroWarden"           # groupe A : faction Necrons + trait Hero + Mechanical
ALLY_B = "admecDominus"          # groupe B : Hero + Mechanical, faction AdeptusMechanicus
ENEMY_A = "blackTerminator"      # L'UNIQUE ennemi -- adjacent aux DEUX allies (cf. setup_positions)
# Roles des montages de CONTREFACTUELS (M5/M6). Traits ET portees re-derives du gameconfig le
# 2026-07-31 : les QUATRE Necrons du pool portent `Mechanical` + `Hero`, donc TOUS dans le groupe A
# -- c'est pourquoi `nomechanical` exige un montage SANS Necron allie (M6).
CF_WEAK = "necroDestroyer"       # groupe A, AVEC cible, Attaque la PLUS FAIBLE
CF_ELECT = "necroWarden"         # groupe A, AVEC cible, Attaque moyenne -> l'elu du tri DESCENDANT
# ⚠ `necroSpyder` est le SEUL Necron du pool dont `weapons` ne porte AUCUNE entree `Range` (melee
# PURE). Les trois autres tirent a 2 ou 3 hexes : sur un hub, TOUT voisin du porteur reste a portee
# de l'ennemi, donc eux ne peuvent JAMAIS jouer le role « sans cible ». Mesure du 2026-07-31 -- le
# premier montage donnait ce role a `necroDestroyer` (Range 2), qui gardait sa cible et rendait le
# contrefactuel `notargets` INERTE.
CF_NOTGT = "necroSpyder"         # groupe A, Attaque MAXIMALE, melee pure placee hors de portee
ALLY_NM = "astraCreed"           # `Hero` NU -- PAS `Mechanical` (gate HasTrait 0x05)

EXTRA_DAMAGE_EFFECT = 1581       # `EffectType.MyWillBeDoneOverlord_ExtraDamage`
MY_WILL_BE_DONE_OVERLORD = 1556  # `TriggeredAbilityType.MyWillBeDoneOverlord`
MARTIAL_APOTHEOSIS = 1045        # `TriggeredAbilityType.MartialApotheosis` (l'ANCIEN passif)

# ------------------------------------------------------------------------------------------------
# LE MONTAGE OBLIGATOIRE, et pourquoi (MESURE du 2026-07-31, `unitAbilityStates` du runner) :
#
#   `necroOverlord` monte depuis `data/seed-bc.json` porte `triggered = [1045 MartialApotheosis,
#   1010 LivingMetal]` -- PAS 1556. Le natif lit le kit de passifs dans **`BC.Units[].
#   PassiveAbilities`** (des IDs numeriques), et cette entree du seed est ANTERIEURE a la MAJ qui a
#   remplace `MartialApotheosis` par `MyWillBeDoneOverlord`. Le PORT, lui, lit
#   `gameconfig.unit(visualId).passiveAbilities` (le fichier VIVANT) -> il instancie 1556.
#
#   Sans ce patch, la confrontation ne mesure donc PAS le port de 1556 : elle mesure l'ecart entre
#   deux SOURCES de kit. C'est la forme #254 (« une config d'ability presente mais PERIMEE »), et
#   `_load_seed_bc` ne re-synthetise que `BC.Abilities`, jamais `BC.Units[].PassiveAbilities`.
#
#   Le patch est donc le MONTAGE, exactement comme poser un `TertiaryAbility` pour confronter une
#   relique non equipee au seed. `--unit-stat` ne tolere pas de virgule DANS une valeur -> la liste
#   ne porte que 1556 ; `LivingMetal` (1010) reste accorde par le TRAIT et, de toute facon, fire sur
#   `On(0x13 = TurnStart_Other)`, jamais sur le `finish` que la mesure encadre.
CARRIER_PASSIVES_PATCH = "%s:PassiveAbilities=[%d]" % (CARRIER, MY_WILL_BE_DONE_OVERLORD)

P_UNITS = [CARRIER, ALLY_A, ALLY_B]
A_UNITS = [ENEMY_A]
# L'Attaque du groupe B est patchee TRES AU-DESSUS de celle du groupe A : si le port triait
# globalement par Attaque (H2) il eluerait le Dominus. Les deux valeurs restent sous le `maxDmg` du
# porteur (verifie en sortie : le cap ne doit pas ecraser la difference).
ALLY_A_DAMAGE = 400
ALLY_B_DAMAGE = 3000
# M5/M6 (contrefactuels) : deux paliers d'Attaque de plus, pour departager DANS un meme groupe.
ALLY_C_DAMAGE = 3000            # l'elu du tri DESCENDANT dans M5 (groupe A, avec cible)
ALLY_D_DAMAGE = 9000            # Attaque MAXIMALE mais SANS cible -> ecarte par le gate
# PV des ennemis remontes : le montage doit SURVIVRE a plusieurs tours (M3), et une victime tuee au
# premier coup ferait disparaitre le cas discriminant du tour suivant.
ENEMY_HP = 40000
# ARMURE de la victime ANNULEE. Mesure faite AVANT ce patch : l'armure native de `blackTerminator`
# ecrasait les DEUX regimes d'Attaque sur le meme degat PLANCHER (-2 / -3), c'est-a-dire que le
# montage ne discriminait PLUS les deux hypotheses. Sans armure, `Damage = 400` et `Damage = 3000`
# donnent deux regimes de degat sans recouvrement -> le chiffre DESIGNE l'attaquant.
ENEMY_ARMOR_SPECS = ("%s:Armor=0" % ENEMY_A, "%s:FixedArmor=0" % ENEMY_A)


def _r(sid, m, b, t=90):
    return (_rpc(sid, m, [b], timeout=t).get("result") or {})


def build(seed, board, p_units, a_units, state_file, stats=()):
    """`rl_duel build` (voie unique, runner.md §1). `--state-file` ABSOLU sous `logs/`."""
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.unlink(missing_ok=True)
    cmd = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
           "--state-file", str(state_file), "--board", board,
           "--p-units", ",".join(p_units)]
    if a_units:
        cmd += ["--a-units", ",".join(a_units)]
    for spec in stats:
        cmd += ["--unit-stat", spec]
    proc = subprocess.run(cmd, cwd=str(PYDIR), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if not state_file.exists():
        print("[354] build KO:", (proc.stderr or proc.stdout or "")[-900:], file=sys.stderr)
        return None
    return json.loads(state_file.read_text())["runnerId"]


def dispose(sid, rid):
    try:
        _r(sid, "disposeRunner", {"runnerId": rid}, 60)
    except Exception as exc:                                   # pragma: no cover (nettoyage)
        print("[354] dispose KO:", exc, file=sys.stderr)


def dv(sid, rid, all_ab=False):
    b = {"runnerId": rid, "maxRank": 1}
    if all_ab:
        b["allAbilities"] = True
    return _r(sid, "decisionView", b, 150 if all_ab else 60)


def move(sid, rid, uid, col, row):
    _r(sid, "applyAction",
       {"runnerId": rid,
        "actions": [{"kind": "move", "unitId": uid, "to": {"col": col, "row": row}}]}, 60)


def finish(sid, rid, uid):
    """`act finish` -> `FinishUnitTurnMessage` -> `FinishUnitTurnOperation$$Execute(unit, false)`,
    c'est-a-dire EXACTEMENT l'emetteur natif de `On(0x29 = UnitFinishedTurnNormally)`."""
    return _r(sid, "applyAction",
              {"runnerId": rid, "actions": [{"kind": "finish", "unitId": uid}]}, 90)


def endturn(sid, rid):
    _r(sid, "applyAction", {"runnerId": rid, "actions": [{"kind": "endturn"}]}, 120)


def hp_live(view) -> dict:
    return {int(u["id"]): int(u.get("hp") or 0) for u in (view.get("units") or []) if u.get("alive")}


def hp_offline(state) -> dict:
    out = {}
    for eid, e in state.entities.items():
        hc = e.get_component(HealthComponent)
        if hc is not None and hc.hp is not None:
            out[int(eid)] = int(hc.hp)
    return out


def effects_live(view, effect_type: int) -> dict:
    """{id d'unite: `remaining`} des porteurs ACTIFS de `effect_type` dans `decisionView`."""
    out = {}
    for u in (view.get("units") or []):
        for e in (u.get("effects") or []):
            if e.get("active") is False:
                continue
            if int(e.get("effectType") or -1) == effect_type:
                out[int(u["id"])] = e.get("remaining")
    return out


def _hub_tile(bg):
    """Une tuile jouable a SIX voisins jouables (runner.md : une mecanique d'adjacence ne doit pas
    etre sous-exercee par un spawn en coin)."""
    by_id = {t["id"]: t for t in bg["tiles"]}
    cands = []
    for t in bg["tiles"]:
        if not t.get("walkable") or t.get("isWall"):
            continue
        good = [n for n in (t.get("neighbours") or [])
                if n in by_id and by_id[n].get("walkable") and not by_id[n].get("isWall")]
        if len(good) >= 6:
            cands.append(t)
    return cands[len(cands) // 2] if cands else None


def _free_neighbours(bg, tile_id, ids_ok=()):
    by_id = {t["id"]: t for t in bg["tiles"]}
    t = by_id.get(tile_id)
    if t is None:
        return []
    return [by_id[n] for n in (t.get("neighbours") or [])
            if n in by_id and by_id[n].get("walkable") and not by_id[n].get("isWall")
            and by_id[n].get("occupantUnitId") in (None,) + tuple(ids_ok)]


def setup_positions(sid, rid, ids, a=None, b=None, enemy=None, far=None):
    """DRIVE la geometrie du montage M1/M2/M3 (`applyAction move` TELEPORTE -> elle est CHOISIE) :

        Overlord sur un hub H a 6 voisins ; ALLY_A et ALLY_B sur DEUX voisins de H **adjacents entre
        eux** ; ENEMY_A sur leur SECOND voisin commun E (celui qui n'est pas H), donc a distance 2 de
        l'Overlord et a distance 1 des DEUX allies.

    Pourquoi CETTE geometrie, et pas « une cible par allie » : le choix de CIBLE de l'attaque libre
    est un etage PARTAGE (le moteur d'utilite de `PerformAIAbilityUnitBehaviour`, residu #348/#338-r1)
    -- avec deux ennemis, un desaccord sur cet etage-la masquerait l'etage que ce cas doit mesurer
    (QUEL ALLIE est elu). Avec un ennemi UNIQUE a portee des deux, la cible est forcee et c'est le
    DEGAT qui designe l'attaquant : les Attaques des deux allies sont patchees a `%d` et `%d`, donc
    deux regimes de degat sans recouvrement possible.

    `a` / `b` / `enemy` PARAMETRENT les trois roles (defaut = ALLY_A / ALLY_B / ENEMY_A) ; `far`, s'il
    est fourni, est un QUATRIEME occupant pose sur un voisin du hub choisi A DISTANCE >= 2 DE
    L'ENNEMI -- c'est le role « adjacent au porteur mais SANS cible d'attaque normale », qui exerce le
    gate `AmountIsGreaterThanZero(ValidNormalAttackTargets(...))` (montage M5).

    Rend `None` (montage REFUSE) plutot qu'une geometrie degradee.""" % (ALLY_A_DAMAGE,
                                                                        ALLY_B_DAMAGE)
    import hexgeo
    a, b, enemy = a or ALLY_A, b or ALLY_B, enemy or ENEMY_A
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
    hub = _hub_tile(bg)
    if hub is None:
        return None
    move(sid, rid, ids[CARRIER], hub["col"], hub["row"])
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
    by_id = {t["id"]: t for t in bg["tiles"]}
    ring = _free_neighbours(bg, hub["id"], tuple(ids.values()))
    # deux voisins du hub ADJACENTS entre eux, dont le SECOND voisin commun (hors hub) est libre.
    pick = None
    for i in range(len(ring)):
        for j in range(len(ring)):
            if i == j:
                continue
            ta, tb = ring[i], ring[j]
            if hexgeo.distance((ta["col"], ta["row"]), (tb["col"], tb["row"])) != 1:
                continue
            common = [by_id[n] for n in (ta.get("neighbours") or [])
                      if n in by_id and n != hub["id"]
                      and n in set(tb.get("neighbours") or [])
                      and by_id[n].get("walkable") and not by_id[n].get("isWall")
                      and by_id[n].get("occupantUnitId") in (None, ids[enemy])]
            if common:
                pick = (ta, tb, common[0])
                break
        if pick:
            break
    if pick is None:
        return None
    move(sid, rid, ids[a], pick[0]["col"], pick[0]["row"])
    move(sid, rid, ids[b], pick[1]["col"], pick[1]["row"])
    move(sid, rid, ids[enemy], pick[2]["col"], pick[2]["row"])
    if far is not None:
        # role « SANS cible » : un voisin LIBRE du hub, a distance >= 2 de l'ennemi (donc hors de
        # portee d'une attaque normale de melee) -- sinon le montage n'exerce pas le gate.
        epos = (pick[2]["col"], pick[2]["row"])
        used = {(pick[0]["col"], pick[0]["row"]), (pick[1]["col"], pick[1]["row"]), epos,
                (hub["col"], hub["row"])}
        spot = None
        for t in _free_neighbours(bg, hub["id"], tuple(ids.values())):
            p = (t["col"], t["row"])
            if p in used or t.get("occupantUnitId") not in (None, ids[far]):
                continue
            if hexgeo.distance(p, epos) >= 2:
                spot = t
                break
        if spot is None:
            return None
        move(sid, rid, ids[far], spot["col"], spot["row"])
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
    pos = {t.get("occupantUnitId"): (t["col"], t["row"])
           for t in bg["tiles"] if t.get("occupantUnitId") is not None}
    for vis in (a, b):                                 # controle de sortie : geometrie ATTEINTE
        if hexgeo.distance(pos[ids[vis]], pos[ids[CARRIER]]) != 1:
            return None
        if hexgeo.distance(pos[ids[vis]], pos[ids[enemy]]) != 1:
            return None
    if far is not None:                                # ... et le role SANS cible l'est aussi
        if hexgeo.distance(pos[ids[far]], pos[ids[CARRIER]]) != 1:
            return None
        if hexgeo.distance(pos[ids[far]], pos[ids[enemy]]) < 2:
            return None
    return bg


def capture(sid, rid, board):
    """Capture PRE-action, `dumpRng` INCLUS : la branche THEN passe par une ATTAQUE NORMALE
    (`PerformAIAttackFromCurrentPosition`), donc le rejeu offline doit repartir du MEME etat
    Mersenne-Twister que le natif -- sans quoi le degat compare ne serait pas confrontable."""
    return {"dec": dv(sid, rid, all_ab=True),
            "ob": _r(sid, "observeBattle", {"runnerId": rid}, 60),
            "snap": _r(sid, "combatSnapshot", {"runnerId": rid}, 120),
            "rng": _r(sid, "dumpRng", {"runnerId": rid}, 30),
            "board": board}


def offline_finish(cap, unit_id, patch=None):
    """Rejoue le `finish` de `unit_id` cote PORT depuis la capture, par le MEME chemin que le runner
    (`FinishUnitTurnOperation.execute(..., forced=False)` -> vecteur `On(0x29)`).

    `patch` = un CONTREFACTUEL : remplacant de `my_will_be_done_target_friend` (cf. `_patched_tree`).
    Rend `(state, resultats_du_vecteur)`."""
    import engine.runner.operations.triggers.loki.my_will_be_done_overlord as M
    from engine.runner.operations.turnflow import FinishUnitTurnOperation
    from engine.runner.prng import IntBasedMersenneTwister
    state = load_state(cap["dec"], cap["ob"], cap["snap"], board=cap["board"])
    s0 = cap.get("rng")
    if isinstance(s0, dict) and s0.get("mt"):
        rng = IntBasedMersenneTwister()
        rng.mt = list(s0["mt"])
        rng.mti = s0["mti"]
        state.rng = rng
    saved = M.my_will_be_done_target_friend
    if patch is not None:
        M.my_will_be_done_target_friend = patch
    try:
        out = FinishUnitTurnOperation.execute(state, int(unit_id), forced=False)
    finally:
        M.my_will_be_done_target_friend = saved
    return state, (out.get("finished_normally_triggers") or [])


def _patched_tree(mutate):
    """Contrefactuels ADVERSARIAUX sur MON PROPRE mecanisme -- chacun neutralise UN etage lu au
    decompile. S'ils ne faisaient pas diverger le port du live, le montage ne testerait pas cet
    etage.

      `nogroups`   : supprime la chaine `A.Otherwise(B).Otherwise(C).Otherwise(D)` -> tri GLOBAL par
                     Attaque (l'hypothese H2 de M1) ;
      `ascending`  : inverse le sens du tri (`ascending=True`) ;
      `notargets`  : retire le gate `AmountIsGreaterThanZero(ValidNormalAttackTargets(it))` ;
      `nomechanical`: retire le gate `HasTrait(it, 0x05 = Mechanical)`."""
    import engine.runner.operations.triggers.loki.my_will_be_done_overlord as M
    from engine.entities.formulas import Count, EntityId, StatAmount
    from engine.entities.selectors import (AdjacentFriends, Filter, First, Otherwise, SortByFormula,
                                           Subject, Tiles, ValidNormalAttackTargets)
    from engine.entities.selectors.tiles import Caster
    from engine.entities.stats import StatPart, StatType
    from engine.entities.triggers import (AmountIsGreaterThanZero, HasFaction, HasTrait,
                                          IsInPersistentDataList, Not, TriggerAnd)

    def patched():
        it = Subject()
        terms = []
        if mutate != "nomechanical":
            terms.append(HasTrait(it, M.MECHANICAL))
        if mutate != "notargets":
            terms.append(AmountIsGreaterThanZero(Count(ValidNormalAttackTargets(it, Tiles(it)))))
        terms.append(Not(IsInPersistentDataList(M.MY_WILL_BE_DONE_OVERLORD, Caster(),
                                                M.ABILITY_ID, EntityId(it))))
        base = terms[0]
        for t in terms[1:]:
            base = TriggerAnd(base, t)
        pool = Filter(AdjacentFriends(Caster()), base)
        if mutate == "nogroups":
            chain = pool
        else:
            necron, hero = HasFaction(it, M.NECRONS), HasTrait(it, M.HERO)
            chain = Otherwise(Otherwise(Otherwise(
                Filter(pool, TriggerAnd(necron, hero)),
                Filter(pool, TriggerAnd(Not(necron), hero))),
                Filter(pool, TriggerAnd(necron, Not(hero)))),
                Filter(pool, TriggerAnd(Not(necron), Not(hero))))
        return First(SortByFormula(chain, StatAmount(it, int(StatType.ATTACK),
                                                     int(StatPart.CURRENT)),
                                   ascending=(mutate == "ascending")))
    return patched


def measure(sid, seed="777", board_id="MC1_67", turns=2, verbose=True):
    """M1/M2/M3 -- monte le montage, joue `turns` activations du porteur et rend la mesure BRUTE.
    `None` si le montage n'a pas pu etre etabli (JAMAIS un resultat degrade)."""
    import hexgeo
    stats = [CARRIER_PASSIVES_PATCH,
             "%s:Damage=%d" % (ALLY_A, ALLY_A_DAMAGE),
             "%s:Damage=%d" % (ALLY_B, ALLY_B_DAMAGE)]
    for e in A_UNITS:
        stats += ["%s:Health=%d" % (e, ENEMY_HP), "%s:RemainingHealth=%d" % (e, ENEMY_HP)]
    stats += list(ENEMY_ARMOR_SPECS)
    rid = build(seed, board_id, P_UNITS, A_UNITS, STATE, stats)
    if rid is None:
        return None
    if verbose:
        print("[354] runner=%s seed=%s board=%s" % (rid, seed, board_id))
    try:
        view = dv(sid, rid)
        ids, teams = {}, {}
        for u in (view.get("units") or []):
            if u.get("alive"):
                ids[u.get("visualId")] = int(u["id"])
                teams[int(u["id"])] = u.get("team")
        missing = [v for v in (P_UNITS + A_UNITS) if v not in ids]
        if missing:
            print("[354] ABORT unites absentes du build: %s" % missing)
            return None
        vis_by_id = {v: k for k, v in ids.items()}
        p_team = view.get("currentPlayer")
        if setup_positions(sid, rid, ids) is None:
            print("[354] ABORT placement impossible (geometrie non atteinte)")
            return None
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
        board = Board(bg["tiles"], adjacency="evenq")
        pos = {t.get("occupantUnitId"): (t["col"], t["row"])
               for t in bg["tiles"] if t.get("occupantUnitId") is not None}
        if verbose:
            for vis in P_UNITS + A_UNITS:
                print("  place %-18s pos=%s dist(carrier)=%d team=%s"
                      % (vis, pos[ids[vis]], hexgeo.distance(pos[ids[vis]], pos[ids[CARRIER]]),
                         teams[ids[vis]]))

        rows = []
        for k in range(turns):
            if dv(sid, rid).get("currentPlayer") != p_team:
                endturn(sid, rid)                       # se replacer sur MON tour
            cap = capture(sid, rid, board)
            hp_before = hp_live(cap["dec"])
            # --- PORT : rejoue le meme `finish`, sur la capture PRE-action -------------------
            st, port_out = offline_finish(cap, ids[CARRIER])
            hp_off = hp_offline(st)
            # --- LIVE : le natif ------------------------------------------------------------
            finish(sid, rid, ids[CARRIER])
            after = dv(sid, rid, all_ab=True)
            hp_after = hp_live(after)
            d_live = {i: hp_after.get(i, hp_before[i]) - hp_before[i] for i in hp_before}
            d_port = {i: hp_off.get(i, hp_before[i]) - hp_before[i] for i in hp_before}
            rows.append({"k": k + 1, "cap": cap, "d_live": d_live, "d_port": d_port,
                         "port_out": port_out, "hp_before": hp_before,
                         "extra_live": effects_live(after, EXTRA_DAMAGE_EFFECT)})
            if verbose:
                hurt_live = sorted(i for i in d_live if d_live[i] < 0)
                hurt_port = sorted(i for i in d_port if d_port[i] < 0)
                print("[354] activation #%d  victimes live=%s port=%s  %s"
                      % (k + 1, [vis_by_id[i] for i in hurt_live],
                         [vis_by_id[i] for i in hurt_port],
                         "OK" if hurt_live == hurt_port else "DESACCORD-CIBLE"))
                for i in sorted(d_live):
                    if d_live[i] or d_port[i]:
                        print("    %-18s d_live=%-7d d_port=%-7d %s"
                              % (vis_by_id[i], d_live[i], d_port[i],
                                 "OK" if d_live[i] == d_port[i] else "<-- ECART"))
                if port_out:
                    print("    port: allie elu=%s cible=%s cap=%s pct=%s"
                          % (vis_by_id.get(port_out[0].get("friend")),
                             vis_by_id.get(port_out[0].get("target")),
                             port_out[0].get("cap"), port_out[0].get("pct")))
            endturn(sid, rid)                            # laisser le tour tourner (purge On(0x12))
        return {"rid": rid, "ids": ids, "vis_by_id": vis_by_id, "teams": teams,
                "p_team": p_team, "rows": rows, "board": board}
    finally:
        dispose(sid, rid)


def measure_counterfactual(sid, seed="777", board_id="MC1_67", verbose=True):
    """M5 -- montage des contrefactuels `ascending` et `notargets`, que M1 N'EXERCE PAS.

    MESURE du 2026-07-31 : sur M1 les mutations `ascending` / `notargets` / `nomechanical` ne
    changeaient AUCUNE election, et les tests (H) correspondants ECHOUAIENT -- a juste titre. M1
    n'oppose qu'UNE unite par groupe (donc le sens du tri est inerte) et ses DEUX allies sont
    Mechanical ET pourvus d'une cible (donc les deux gates sont inertes). Un montage qui n'exerce pas
    un etage ne prouve rien de cet etage.

    M5 met TROIS Necrons (tous `Mechanical` + `Hero` -> le MEME groupe A, cf. recon) :
      * CF_WEAK  `necroDestroyer` ATK %d   -- adjacent au porteur ET a l'ennemi
      * CF_ELECT `necroWarden`    ATK %d  -- idem, ATTAQUE PLUS GROSSE -> l'elu du tri DESCENDANT
      * CF_NOTGT `necroSpyder`    ATK %d  -- adjacent au porteur mais A DISTANCE >= 2 de l'ennemi
        et MELEE PURE (aucune arme a `Range`), donc AUCUNE cible d'attaque normale -> ecarte par le
        gate alors qu'il a l'Attaque MAXIMALE.

    -> `ascending` elit `necroDestroyer` au lieu de `necroWarden` ; `notargets` elit `necroSpyder`.
    `nomechanical` reste inerte ici (aucun Necron non-Mechanical n'existe : le groupe A domine
    toujours) -- c'est le role de M6 (`measure_nomech`).""" % (ALLY_A_DAMAGE, ALLY_C_DAMAGE,
                                                              ALLY_D_DAMAGE)
    rid = build(seed, board_id, [CARRIER, CF_WEAK, CF_ELECT, CF_NOTGT], [ENEMY_A], STATE_CF,
                [CARRIER_PASSIVES_PATCH,
                 "%s:Damage=%d" % (CF_WEAK, ALLY_A_DAMAGE),
                 "%s:Damage=%d" % (CF_ELECT, ALLY_C_DAMAGE),
                 "%s:Damage=%d" % (CF_NOTGT, ALLY_D_DAMAGE),
                 "%s:Health=%d" % (ENEMY_A, ENEMY_HP),
                 "%s:RemainingHealth=%d" % (ENEMY_A, ENEMY_HP)] + list(ENEMY_ARMOR_SPECS))
    if rid is None:
        return None
    try:
        view = dv(sid, rid)
        ids = {u.get("visualId"): int(u["id"]) for u in (view.get("units") or []) if u.get("alive")}
        for vis in (CARRIER, CF_WEAK, CF_ELECT, CF_NOTGT, ENEMY_A):
            if vis not in ids:
                print("[354] ABORT M5 : %s absent" % vis)
                return None
        bg = setup_positions(sid, rid, ids, a=CF_WEAK, b=CF_ELECT, enemy=ENEMY_A, far=CF_NOTGT)
        if bg is None:
            print("[354] ABORT M5 : geometrie non atteinte")
            return None
        cap = capture(sid, rid, Board(bg["tiles"], adjacency="evenq"))
        _st, port_out = offline_finish(cap, ids[CARRIER])
        vis_by_id = {v: k for k, v in ids.items()}
        if verbose:
            print("[354] M5  elu=%s"
                  % vis_by_id.get(port_out[0]["friend"] if port_out else None))
        return {"rid": rid, "ids": ids, "vis_by_id": vis_by_id, "cap": cap, "port_out": port_out}
    finally:
        dispose(rid=rid, sid=sid)


def measure_nomech(sid, seed="777", board_id="MC1_67", verbose=True):
    """M6 -- montage du contrefactuel `nomechanical`, qu'AUCUN montage Necron ne peut exercer.

    Tous les Necrons du pool portent `Mechanical` (recon 2026-07-31 : Overlord / Warden / Destroyer /
    Spyder), donc des qu'un Necron est eligible le groupe A gagne et retirer le gate `Mechanical` ne
    deplace rien. M6 supprime donc TOUT allie Necron :
      * ALLY_B   `admecDominus` -- `Mechanical` + `Hero`, faction AdeptusMechanicus (groupe B), ATK %d
      * ALLY_NM  `astraCreed`   -- `Hero` NU (aucun autre trait), donc PAS `Mechanical`, ATK %d

    Groupe A vide -> l'elu normal est `admecDominus` (le seul a passer le gate). Sans le gate, les
    deux sont dans le groupe B et le tri DESCENDANT elit `astraCreed`. -> `nomechanical` DIVERGE.
    """ % (ALLY_A_DAMAGE, ALLY_C_DAMAGE)
    rid = build(seed, board_id, [CARRIER, ALLY_B, ALLY_NM], [ENEMY_A], STATE_NOMECH,
                [CARRIER_PASSIVES_PATCH,
                 "%s:Damage=%d" % (ALLY_B, ALLY_A_DAMAGE),
                 "%s:Damage=%d" % (ALLY_NM, ALLY_C_DAMAGE),
                 "%s:Health=%d" % (ENEMY_A, ENEMY_HP),
                 "%s:RemainingHealth=%d" % (ENEMY_A, ENEMY_HP)] + list(ENEMY_ARMOR_SPECS))
    if rid is None:
        return None
    try:
        view = dv(sid, rid)
        ids = {u.get("visualId"): int(u["id"]) for u in (view.get("units") or []) if u.get("alive")}
        for vis in (CARRIER, ALLY_B, ALLY_NM, ENEMY_A):
            if vis not in ids:
                print("[354] ABORT M6 : %s absent" % vis)
                return None
        bg = setup_positions(sid, rid, ids, a=ALLY_B, b=ALLY_NM, enemy=ENEMY_A)
        if bg is None:
            print("[354] ABORT M6 : geometrie non atteinte")
            return None
        cap = capture(sid, rid, Board(bg["tiles"], adjacency="evenq"))
        _st, port_out = offline_finish(cap, ids[CARRIER])
        vis_by_id = {v: k for k, v in ids.items()}
        if verbose:
            print("[354] M6  elu=%s"
                  % vis_by_id.get(port_out[0]["friend"] if port_out else None))
        return {"rid": rid, "ids": ids, "vis_by_id": vis_by_id, "cap": cap, "port_out": port_out}
    finally:
        dispose(rid=rid, sid=sid)


def setup_solo_positions(sid, rid, ids):
    """DRIVE la geometrie du montage M4 : porteur sur un hub, ALLY_A et ENEMY_A EXILES a distance
    >= 3 -- donc AUCUN allie dans `AdjacentFriends(Caster())` et la branche ELSE est prise.

    ⚠ POURQUOI un allie PRESENT alors que la branche ELSE demande « aucun allie eligible » : il ne
    doit pas etre ELIGIBLE, il doit exister pour que le camp ait ENCORE une unite a activer apres le
    `finish` du porteur. Avec le porteur SEUL, son `finish` fait BASCULER le tour (mesure du
    2026-07-31 : `turn` 3 -> 4, `toActivate` [79] -> [77]), un TICK de duree s'applique, et le
    `remaining` de l'effet 1581 est observe a **2** alors que la formule en pose **3**. La mesure
    comparait alors deux INSTANTS differents (live APRES tick, port juste apres la pose) et faisait
    passer un ecart de protocole pour un ecart de port. Avec l'allie exile : `turn` reste 3,
    `toActivate` [79, 81] -> [81], et le live rend bien `remaining = 3`.

    Rend `None` (montage REFUSE) plutot qu'une geometrie degradee."""
    import hexgeo
    bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
    hub = _hub_tile(bg)
    if hub is None:
        return None
    move(sid, rid, ids[CARRIER], hub["col"], hub["row"])

    def positions():
        g = _r(sid, "boardGraph", {"runnerId": rid}, 90)
        return g, {t.get("occupantUnitId"): (t["col"], t["row"])
                   for t in g["tiles"] if t.get("occupantUnitId") is not None}

    bg, pos = positions()
    cpos = pos[ids[CARRIER]]
    for vis in (ALLY_A, ENEMY_A):
        if vis not in ids:
            continue
        dest = None
        for t in bg["tiles"]:
            if not t.get("walkable") or t.get("isWall"):
                continue
            if t.get("occupantUnitId") not in (None, ids[vis]):
                continue
            if hexgeo.distance((t["col"], t["row"]), cpos) >= 3:
                dest = t
                break
        if dest is not None:
            move(sid, rid, ids[vis], dest["col"], dest["row"])
        bg, pos = positions()
    # controle de SORTIE : la geometrie voulue est ATTEINTE (sinon on refuse le montage).
    if hexgeo.distance(pos[ids[ALLY_A]], pos[ids[CARRIER]]) < 2:
        return None
    return bg


def measure_solo(sid, seed="777", board_id="MC1_67", verbose=True):
    """M4 -- BRANCHE ELSE : aucun allie ADJACENT eligible -> l'Overlord n'attaque personne et l'effet
    1581 `MyWillBeDoneOverlord_ExtraDamage` apparait SUR LUI, avec sa DUREE (`remaining`).

    Le camp du porteur compte un seul AUTRE allie, EXILE a distance >= 3 (cf. `setup_solo_positions`)
    : il ne peut pas etre elu, mais il empeche la bascule de tour qui fausserait la duree observee."""
    rid = build(seed, board_id, [CARRIER, ALLY_A], [ENEMY_A], STATE_SOLO,
                [CARRIER_PASSIVES_PATCH,
                 "%s:Health=%d" % (ENEMY_A, ENEMY_HP),
                 "%s:RemainingHealth=%d" % (ENEMY_A, ENEMY_HP)])
    if rid is None:
        return None
    try:
        view = dv(sid, rid)
        ids = {u.get("visualId"): int(u["id"]) for u in (view.get("units") or []) if u.get("alive")}
        if CARRIER not in ids or ALLY_A not in ids:
            print("[354] ABORT solo : porteur ou allie-tampon absent")
            return None
        if setup_solo_positions(sid, rid, ids) is None:
            print("[354] ABORT solo : geometrie d'exil non atteinte")
            return None
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
        board = Board(bg["tiles"], adjacency="evenq")
        cap = capture(sid, rid, board)
        turn_before = (cap["dec"] or {}).get("turn")
        hp_before = hp_live(cap["dec"])
        st, port_out = offline_finish(cap, ids[CARRIER])
        finish(sid, rid, ids[CARRIER])
        after = dv(sid, rid, all_ab=True)
        d_live = {i: hp_live(after).get(i, hp_before[i]) - hp_before[i] for i in hp_before}
        live_eff = effects_live(after, EXTRA_DAMAGE_EFFECT)
        port_eff = {}
        eff = getattr(st, "effects", None)
        if eff is not None:
            port_eff = {int(uid): e.remaining_turns for uid, lst in eff.by_unit.items()
                        for e in lst if (not e.consumed) and int(e.effect_type) == EXTRA_DAMAGE_EFFECT}
        turn_after = (after or {}).get("turn")
        if verbose:
            print("[354] SOLO  1581 live=%s port=%s  degats live=%s  turn %s -> %s"
                  % (live_eff, port_eff, {i: d for i, d in d_live.items() if d},
                     turn_before, turn_after))
            if port_out:
                print("    port: self_buff=%s attaques=%s"
                      % (port_out[0].get("self_buff"), port_out[0].get("attacks")))
        return {"rid": rid, "ids": ids, "live_eff": live_eff, "port_eff": port_eff,
                "d_live": d_live, "port_out": port_out, "cap": cap,
                "turn_before": turn_before, "turn_after": turn_after}
    finally:
        dispose(rid=rid, sid=sid)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["m1", "m4"], default=None)
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--turns", type=int, default=2)
    a = ap.parse_args()
    sid = _resolve_session()
    print("[354] session=%s" % sid)
    rc = 0
    if a.only in (None, "m1"):
        out = measure(sid, a.seed, a.board, a.turns)
        if out is None:
            print("[354] M1/M2/M3 : montage NON MONTABLE")
            rc = 1
    if a.only in (None, "m4"):
        out = measure_solo(sid, a.seed, a.board)
        if out is None:
            print("[354] M4 : montage NON MONTABLE")
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
