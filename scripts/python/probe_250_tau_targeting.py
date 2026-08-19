#!/usr/bin/env python
"""probe_250_tau_targeting -- ARMEMENT des gates de cible des CINQ abilities du module `tau`.

CE QUE CE PROBE MESURE
----------------------
Les cinq entraient dans `ABILITY_CLASSES` SANS `TARGETING_OPTIONS` ->
`get_invalid_target_reason` / `get_invalid_caster_reason` commencent par
`options = getattr(ability, "TARGETING_OPTIONS", None)` et rendent 0 immediatement : AUCUN gate.
Degradation PERMISSIVE -- ni erreur ni crash, donc invisible en self-play.

LES MASQUES, LUS UN PAR UN AU DECOMPILE (jamais generalises depuis la voisine)

  id    ability                   forme de ctor            rules                 TargetingRange
  ----  ------------------------  -----------------------  --------------------  ----------------
  1077  EarlyWarningOverride      3 PRESET STATIQUE COPIE  0x8004                statics+0x60 SELF
  1081  FightingRetreat           1 FLAGS DIRECTS          0x802                 statics+0x30 ADJ
  1082  InspiredToGreatness       1 FLAGS DIRECTS          0x402                 statics+0x30 ADJ
  1160  HeavyRailRifle            1 FLAGS DIRECTS          0x10400040004000      statics+0x48 BOARD
  1161  TwinSmartMissileSystem    1 FLAGS DIRECTS          0x40004000            statics+0x48 BOARD

1077 n'appelle AUCUN `IdunBattle.Core.Services.TargetingOptions$$.ctor` : il recopie les 0x40 octets
du champ statique `TargetingOptions statics+0x280`, et le masque effectif est la constante ecrite
par `IdunBattle.Core.Services.TargetingOptions$$.cctor` a `<preset>+0x28` = `*(statics+0x2a8)`.
1160 et 1161 sont portees par la MEME MoW (`tauBroadside`), sortent de la MEME forme de ctor, ont le
MEME `TargetingRange` -- et DEUX masques distincts : 1160 porte en plus `TargetIsActor` (bit 46) et
`CasterHas2TurnsLeft` (bit 52). Contre-exemple intra-porteur : generaliser aurait produit un masque
FAUX.

CE QUI EST PORTE, ET CE QUI NE L'EST PAS (le probe le MESURE, il ne le suppose pas)
----------------------------------------------------------------------------------
PORTE : `TargetIsEnemy` (1160/1161), `TargetIsFriendly` (1082), et le VOLET PORTEE
(`RANGE_ADJACENT` -> branche `AreEntitiesAdjacent` pour 1081/1082 ; `RANGE_WHOLE_BOARD` -> aucun
test pour 1160/1161 ; `RANGE_SELF` pour 1077).
NON PORTE, donc PERMISSIF : le bit `TargetMatchesDynamicRule` (1081/1082) -- la classe d'ability ne
fournit pas encore de `get_dynamic_invalid_target_reason`, alors que le natif invoque
`...FightingRetreatAbility$$GetDynamicInvalidTargetReason` (rend 2) et
`...InspiredToGreatnessAbility$$GetDynamicInvalidTargetReason` (rend 1). Le probe SEPARE donc les
lignes « tranchees par un bit PORTE » des lignes « tranchees par la regle DYNAMIQUE », et exige
l'accord parfait sur les premieres.
Egalement non portes et mesures inertes ici : `CasterMatchesDynamicRule` (1077),
`AllowNullCasterTile` (1160/1161), `TargetIsActor` (1160), `CasterHas2TurnsLeft` (1160).

ORACLE = le LIVE : `abilityReason(casterId, abilityType, targetId)` (qui appelle
`IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason` natif). Le probe rejoue le gate
OFFLINE sur le MEME etat fige, en plusieurs versions :
  * APRES     = l'ability du registre (masque pose par cette tranche) ;
  * AVANT     = la MEME classe avec `TARGETING_OPTIONS = None` (l'etat de `master`) ;
  * sansRules = masque a 0, `TargetingRange` conserve  -> isole le volet REGLES ;
  * sansRange = memes regles, `range = None`           -> isole le volet PORTEE ;
  * melee1    = `force_melee_target = RangedBool.True` -> montre si le champ est seulement LU.

Usage (depuis scripts/python, session Frida chaude) :
    python probe_250_tau_targeting.py
    python probe_250_tau_targeting.py --seed 31337 --board C4_09

ASCII only (cp1252). Dispose SES runners (jamais ceux des autres).
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import subprocess
import sys
import time
from dataclasses import replace as _replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo                                                        # noqa: E402
from rl_collect_batch import _resolve_session, _rpc                  # noqa: E402

from engine.entities.pathfinding.board import Board                  # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES          # noqa: E402
from engine.runner.abilities.targeting import (RANGED_BOOL_TRUE,     # noqa: E402
                                               get_invalid_caster_reason,
                                               get_invalid_target_reason)
from engine.runner.abilities.targeting_rule import TargetingRule as TR   # noqa: E402
from engine.runner.snapshot import load_state                        # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

# (ability_type, visualId du porteur, nom court, {code natif: nom de la regle NON PORTEE})
# Les « residus » sont les refus que le NATIF prononce par une regle que le port ne modelise PAS :
# le port rend alors 0 (degradation PERMISSIVE, convention de tout `abilities/targeting.py`). Ils
# sont NOMMES ici pour que le probe les distingue d'un vrai desaccord -- une ligne residu doit avoir
# `port == 0`, sinon c'est un MISMATCH.
#
# #247 -- LES DEUX RESIDUS DYNAMIQUES SONT FERMES, les dicts sont donc VIDES :
#   - 1081 `FightingRetreatAbility$$GetDynamicInvalidTargetReason` (rendait 2, port muet) et
#   - 1082 `InspiredToGreatnessAbility$$GetDynamicInvalidTargetReason` (rendait 1 sur 2 lignes / 8)
# sont PORTES. Laisser leurs codes ici les re-classerait « residu tolere » et le probe ne verrait
# plus une regression de ces deux regles -- c'est precisement ce que la fermeture doit interdire.
#
# 1081 garde en revanche UN residu, et il n'est PAS dynamique : `AddCasterIfAtLeastOneTarget`
# (bit 11 de son masque `0x802`), lu par `IdunBattle.Core.Services.TargetingQuery$$
# GetCasterNotAddedReason` et NON PORTE (`get_caster_not_added_reason` rend 0). `case-250` §4 le
# classait « natif = 0 sur la ligne self des deux couples » -- c'etait vrai de LEUR geometrie, pas
# de la regle. MESURE du 2026-07-29 (`C3_26`/31337, geometrie ou Darkstrider n'a AUCUN ennemi
# adjacent) : toutes ses cibles etant refusees par sa regle dynamique, il ne reste « au moins une
# cible » nulle part et le natif rend `0x800` sur SA PROPRE ligne. Le port rend 0 : degradation
# PERMISSIVE, la convention de tout `abilities/targeting.py`. On le NOMME donc ici, ce qui le
# distingue d'un vrai desaccord sans masquer quoi que ce soit d'autre -- la ligne reste comptee
# `RESIDU` et jamais `agree`.
CASES = [
    (1077, "tauCrisis", "EarlyWarningOverride", {}),
    (1081, "tauDarkstrider", "FightingRetreat",
     {int(TR.AddCasterIfAtLeastOneTarget): "AddCasterIfAtLeastOneTarget"}),
    (1082, "tauAunShi", "InspiredToGreatness", {}),
    (1160, "tauBroadside", "HeavyRailRifle", {}),
    (1161, "tauBroadside", "TwinSmartMissileSystem", {}),
]

P_UNITS = "tauCrisis,tauDarkstrider,tauAunShi"
P_MOW = "tauBroadside"
A_MOW = "ultraDreadnought"          # une MoW ENNEMIE : la seule cible qui separe 1160 de 1161
A_UNITS = "necroWarden,necroWarden,necroWarden"
BOARD = "C4_09"                     # MoW-capable (MachineOfWarPosition pose pour les DEUX camps)
SEED = "777"
TOURS_DE_CHAUFFE = 6               # purge les `initialCooldownTurns` (sinon `ValidRequest` partout)
HUB_VIS = "tauAunShi"             # l'ancre de la geometrie : c'est SON masque qui exige l'adjacence
NEAR_ALLY_VIS = "tauDarkstrider"  # l'allie AU CONTACT du hub (ligne « allie adjacent »)
FAR_ALLY_VIS = "tauCrisis"        # l'allie HORS contact -- et la seule ligne qui exerce la PORTEE
                                  # de 1082 ; il doit etre BLESSE, cf. `measure_all`.
_seq = itertools.count()


# --------------------------------------------------------------------------- plomberie RPC

def _r(sid, method, body, timeout=90):
    out = _rpc(sid, method, [body], timeout=timeout)
    return out.get("result") if isinstance(out, dict) and "result" in out else out


def _seed_bc_with_ammo(ammo: int = 9) -> Path:
    """Seed BC augmente, ecrit HORS `data/` (qui est VERSIONNE) : `Player.Players[*]
    .MachineOfWarAmmo = ammo`.

    POURQUOI C'EST OBLIGATOIRE POUR 1160. Le stock de munitions vit dans
    `IdunBattle.Entities.Components.PlayerComponent+0x6c`, pose UNE fois par
    `IdunBattle.Operations.AddPlayerOperation$$Execute` depuis `BC.Player.Players[].MachineOfWarAmmo`
    (= **0** dans le seed partage), et AUCUNE operation native ne l'incremente. Il gate
    `IdunBattle.Entities.Abilities.AActiveAbility$$get_CanCurrentlyBeUsed` -- or l'oracle
    `abilityReason` passe par `IdunBattle.Core.Services.AttackQuery$$GetInvalidTargetReason`
    (surcharge 4 arguments), dont la PREMIERE ligne est
    `if (ability == null || !ability.CanCurrentlyBeUsed || ability.<+0x44> == 0) return
    GenericBrokenTargetingRule(1);`. MESURE (#250, C4_09/777, seed partage) : 1160 (`ammoCost = 1`,
    `hasAmmo = false`) rend **0x1 sur TOUTES les lignes, casterReason compris** -- la cascade n'est
    JAMAIS evaluee, donc AUCUNE mesure de masque n'est possible. 1161 (`ammoCost = null`) n'est pas
    concernee et mesure normalement. Avec `MachineOfWarAmmo = 9` la cascade s'evalue."""
    import rl_collect_batch as R
    src = json.loads((R.ROOT / "data" / "seed-bc.json").read_text(encoding="utf-8"))
    for p in ((src.get("Player") or {}).get("Players") or {}).values():
        p["MachineOfWarAmmo"] = int(ammo)
    out = ROOT / "logs" / ("_probe250-seedbc-%d.json" % os.getpid())
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(src), encoding="utf-8")
    return out


def _build(sid, seed: str, board: str, seed_bc: Path):
    """`rl_duel build` avec state-file PROPRE sous `logs/` (jamais `data/`, qui est versionne).
    ATTEND qu'un slot se libere si MAX_RUNNERS est sature (le cap est PARTAGE entre agents)."""
    state = ROOT / "logs" / ("_probe250-%d-%d.json" % (os.getpid(), next(_seq)))
    state.parent.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, "rl_duel.py", "build", "--seed", str(seed),
            "--state-file", str(state), "--board", board, "--no-ai", "--seed-bc", str(seed_bc),
            "--p-units", P_UNITS, "--p-mow", P_MOW, "--a-mow", A_MOW, "--a-units", A_UNITS]
    deadline = time.time() + 300
    while True:
        state.unlink(missing_ok=True)
        p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if state.exists():
            return int(json.loads(state.read_text())["runnerId"]), state
        out = (p.stderr or p.stdout or "")
        if "runner cap reached" not in out or time.time() >= deadline:
            raise RuntimeError("build KO : " + out[-500:])
        time.sleep(10)


def _dv(sid, rid):
    return _r(sid, "decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)


def _act(sid, rid, action, timeout=90):
    return _r(sid, "applyAction", {"runnerId": rid, "action": action}, timeout)


def _pos(u):
    q = (u or {}).get("pos") or {}
    return (q.get("col"), q.get("row"))


def _actors(dec):
    """TOUTES les entites-ACTEUR du plateau, unites ET machines of war, sous une forme commune.

    Une MoW n'est PAS dans `decisionView.units` : elle vit dans `decisionView.mows`, dont la cle ECS
    est `casterId` (== `machineId`, l'entite **Machine**) -- c'est l'id qu'attendent
    `applyAction{kind:"ability", casterId}` et `abilityReason`. Le champ `id` de la ligne est la
    PLATEFORME, pas l'acteur. Elle n'a NI position NI PV (hors-plateau, cf.
    `engine/runner/snapshot.py` `_load_machines`), d'ou `pos = (None, None)`."""
    out = []
    for u in (dec.get("units") or []):
        if u.get("alive"):
            out.append({"id": int(u["id"]), "visualId": u.get("visualId"), "owner": u.get("owner"),
                        "pos": _pos(u), "machine": False})
    for m in (dec.get("mows") or []):
        if m.get("alive") and m.get("casterId") is not None:
            out.append({"id": int(m["casterId"]), "visualId": m.get("visualId"),
                        "owner": m.get("owner"), "pos": (None, None), "machine": True})
    return out


def _by_vis(dec, vis):
    for a in _actors(dec):
        if a["visualId"] == vis:
            return a
    return None


def _dist(a, b):
    """Distance hex, ou None des qu'un des deux acteurs est HORS-PLATEAU (MoW)."""
    if None in a["pos"] or None in b["pos"]:
        return None
    return hexgeo.distance(a["pos"], b["pos"])


def _movable(sid, rid, uid):
    mov = _r(sid, "aiMovableTiles", {"runnerId": rid}, 90)
    for m in (mov.get("units") or []):
        if m.get("unitId") == uid:
            return [(t["col"], t["row"]) for t in (m.get("tiles") or [])
                    if t.get("col") is not None]
    return []


def _wait_movable(sid, rid, unit_id, maxit=4):
    """Tuiles de deplacement de `unit_id`, en enchainant les `endturn` jusqu'a ce que son camp AIT la
    main. On ne COMPTE pas les `endturn` : quand toutes les unites d'un camp ont agi le moteur
    bascule DEJA de lui-meme, et un `endturn` de plus decalerait la parite."""
    for _ in range(maxit):
        t = _movable(sid, rid, unit_id)
        if t:
            return t
        _act(sid, rid, {"kind": "endturn"}, 60)
    return []


def _step_toward(sid, rid, unit_id, goal_pos, want: int) -> bool:
    """Rapproche (ou eloigne) `unit_id` jusqu'a une distance `want` de `goal_pos`, dans la limite de
    SON deplacement du tour."""
    tiles = _wait_movable(sid, rid, unit_id)
    if not tiles:
        return False
    best = min(tiles, key=lambda t: (abs(hexgeo.distance(t, goal_pos) - want), t))
    _act(sid, rid, {"kind": "move", "unitId": unit_id,
                    "to": {"col": best[0], "row": best[1]}}, 90)
    return True


def _hand_to(sid, rid, vis, maxit=8):
    """Rend la main au camp de l'unite `vis` (chaine de `endturn`, runner `--no-ai`).
    On NOMME le camp voulu : tester `currentPlayer == <une unite ctrl>.owner` serait une tautologie
    (`ctrl` DESIGNE le joueur courant), et ce probe pilote les DEUX camps."""
    for _ in range(maxit):
        d = _dv(sid, rid)
        me = _by_vis(d, vis)
        if me is not None and d.get("currentPlayer") == me["owner"]:
            return d
        _act(sid, rid, {"kind": "endturn"}, 60)
    return _dv(sid, rid)


def _hand_to_owner(sid, rid, owner, maxit=8):
    """Variante par OWNER : `_hand_to` designe son camp par un `visualId`, ce qui ne suffit plus des
    que le camp compte PLUSIEURS exemplaires du meme visuel (les trois `necroWarden`) -- `_by_vis`
    rend alors le premier, pas celui qu'on pilote."""
    for _ in range(maxit):
        d = _dv(sid, rid)
        if d.get("currentPlayer") == owner:
            return d
        _act(sid, rid, {"kind": "endturn"}, 60)
    return _dv(sid, rid)


# --------------------------------------------------------------------------- regime BLESSE
#
# POURQUOI CE BLOC EXISTE (mesure du 2026-07-29). Le montage `--bites` de #247 croyait faire frapper
# un ennemi avec `applyAction{"kind": "attack", ...}`. CETTE ACTION N'EXISTE PAS :
# `applyOneAction` (`frida/hooks/features/ai-step/internals.ts`) ne connait que
# `move | ability | finish | endturn` et rend `ok:false, error:"unknown kind: attack", mutated:false`
# -- un NO-OP que RIEN ne signale quand l'appelant ignore le retour. D'ou le `7530 -> 7530` du
# rapport de #254, lu a tort comme « l'attaque ne fait pas de degats ». MESURE de la correction :
# meme montage, cast de l'attaque normale -> `hpDelta = -118`.
#
# L'attaque normale est une ABILITY, et son `ActiveAbilityType` est CONCRET et PER-UNITE
# (`ActiveAbilityComponent.NormalAttackType`, ex. 69 `Loki_NormalAttack`) -- surtout pas le 17
# synthetique qu'`engine/ai/state_bridge.py` emploie OFFLINE : `ActiveAbilityMessage` exige l'id que
# porte l'unite, et 17 n'en resout aucun.

def _normal_attack_type(dv, uid):
    """L'id CONCRET de l'attaque normale de `uid`, lu dans `decisionView.units[].abilities`
    (`kind == "normal"`). None = l'unite n'expose pas d'attaque normale (rien a caster)."""
    for u in (dv.get("units") or []):
        if int(u.get("id", -1)) == int(uid):
            for a in (u.get("abilities") or []):
                if a.get("kind") == "normal" and a.get("id") is not None:
                    return int(a["id"])
    return None


def _unit_hp(dv, uid):
    """PV COURANTS de `uid` (`decisionView.units[].hp`), ou None si l'unite n'est plus listee."""
    for u in (dv.get("units") or []):
        if int(u.get("id", -1)) == int(uid):
            return u.get("hp")
    return None


def _wound(sid, rid, victim_id, rounds=14):
    """AMENE `victim_id` au regime BLESSE (`hp < hp_max`) et le VERIFIE -- jamais « j'ai envoye une
    action, donc c'est fait ».

    Un ennemi de la victime caste son attaque NORMALE depuis une tuile d'ou le jeu la declare
    frappable -- PAS forcement au contact : les `necroWarden` sont RANGED et tirent a d=3. Le
    CONTACT est un regime distinct, pose par `_bring_to_contact`. Rend `(hp_avant, hp_apres)` ;
    `hp_apres == hp_avant` signifie que le regime n'a PAS ete atteint, et c'est a l'appelant
    d'echouer dessus (aucun `skip` : un montage qui n'atteint pas son regime doit ROUGIR, cf. la
    lecon de #254 sur le test eteint).

    Le disjunct que ce regime arme cote gate : `IsDamagedUnit` d'`AttackQuery$$EntityCanBeHealed`
    (slot 0x11 d'`IAttackQuery`), donc la regle dynamique
    `InspiredToGreatnessAbility$$GetDynamicInvalidTargetReason` de 1082.

    C'EST LE JEU QUI DIT D'OU L'ON PEUT FRAPPER, PAS LA DISTANCE HEX. La 1re version conduisait
    l'attaquant a `hexgeo.distance == 1` puis castait. MESURE (`C3_26`/31337) : le `necroWarden`
    atteint bien d=1, `hasAction=True`, son camp a la main -- et le cast rend `ok=true, error=null,
    mutated=FALSE`, SEPT fois de suite. La distance a vol d'oiseau n'est PAS l'adjacence du jeu :
    `MovementUtil$$AreTilesAdjacent` porte une porte d'ELEVATION, et deux tuiles voisines separees
    par une marche ne sont pas au contact. Le canal qui repond EXACTEMENT a la question est
    `castFromTiles` (`GetInvalidTargetReason` evalue PAR TUILE) : `currentValid` = frappable d'ici,
    `moveTiles` = les tuiles d'ou ce le serait apres deplacement. On l'INTERROGE donc au lieu de
    deduire ; `_step_toward` ne sert plus qu'a se rapprocher quand AUCUN candidat n'a de tuile de
    tir ce tour."""
    dv0 = _dv(sid, rid)
    hp0 = _unit_hp(dv0, victim_id)
    for it in range(rounds):
        dv = _dv(sid, rid)
        hp = _unit_hp(dv, victim_id)
        if hp is not None and hp0 is not None and hp < hp0:
            return hp0, hp
        me = next((a for a in _actors(dv) if a["id"] == int(victim_id)), None)
        if me is None or None in me["pos"]:
            break
        cands = sorted((a for a in _actors(dv)
                        if a["owner"] != me["owner"] and None not in a["pos"] and not a["machine"]),
                       key=lambda a: (_dist(me, a), a["id"]))
        if not cands:
            break
        fired = False
        for atk in cands:
            na = _normal_attack_type(dv, atk["id"])
            if na is None:                       # pas d'attaque normale -> ce porteur ne sert a rien
                continue
            _hand_to_owner(sid, rid, atk["owner"])
            cf = _r(sid, "castFromTiles", {"runnerId": rid, "casterId": atk["id"],
                                           "targetId": int(victim_id), "abilityType": na}, 60) or {}
            tiles = [t for t in (cf.get("moveTiles") or []) if t.get("col") is not None]
            if not cf.get("currentValid") and not tiles:
                continue
            if not cf.get("currentValid"):
                _act(sid, rid, {"kind": "move", "unitId": atk["id"],
                                "to": {"col": tiles[0]["col"], "row": tiles[0]["row"]}}, 90)
            res = _act(sid, rid, {"kind": "ability", "casterId": atk["id"],
                                  "targetId": int(victim_id), "abilityType": na}, 120)
            a0 = ((res or {}).get("actions") or [{}])[0]
            print("  [wound %d] u%s -> u%s (na=%s currentValid=%s moveTiles=%d) ok=%s err=%s "
                  "mutated=%s" % (it, atk["id"], victim_id, na, cf.get("currentValid"), len(tiles),
                                  a0.get("ok"), a0.get("error"), a0.get("mutated")))
            if a0.get("mutated"):
                fired = True
                break
        if fired:
            continue
        # Aucun candidat n'a de tuile de tir CE TOUR -> on rapproche le plus proche, et on cloture
        # le tour : un cast refuse laisse l'attaquant DEJA active, il lui faut une activation neuve.
        print("  [wound %d] aucune tuile de cast -- on rapproche u%s" % (it, cands[0]["id"]))
        _step_toward(sid, rid, cands[0]["id"], me["pos"], 1)
        _act(sid, rid, {"kind": "endturn"}, 60)
    return hp0, _unit_hp(_dv(sid, rid), victim_id)


# --------------------------------------------------------------------------- montage geometrique

def _drive_cluster(sid, rid, rounds=10):
    """Monte la geometrie DISCRIMINANTE, en DEPLACANT les unites (jamais en subissant les spawns) :

      * `tauDarkstrider` (ALLIE) AU CONTACT de `tauAunShi`  -> ligne « allie adjacent »   (1082 : 0)
      * un ennemi AU CONTACT de `tauAunShi`                 -> ligne « ennemi adjacent »  (1082 : 0x400)
      * `tauCrisis` (ALLIE) HORS contact de `tauAunShi`     -> ligne « allie loin »       (1082 : portee)
      * un ennemi HORS contact                              -> ligne « ennemi loin »

    `applyAction` ne verifie pas la propriete du `unitId` (runner.md §4) mais `aiMovableTiles` est
    calcule pour le JOUEUR COURANT -> on pilote MES unites pendant mon tour et les ENNEMIES pendant
    le leur (runner `--no-ai` : rien ne bouge tout seul)."""
    def _snap():
        d = _dv(sid, rid)
        hub = _by_vis(d, HUB_VIS)
        if hub is None:
            raise RuntimeError("montage impossible : %s absent du plateau" % HUB_VIS)
        board_foes = sorted((a for a in _actors(d)
                             if a["owner"] != hub["owner"] and None not in a["pos"]),
                            key=lambda a: (_dist(hub, a), a["id"]))
        return d, hub, board_foes

    for it in range(rounds):
        d, hub, foes = _snap()
        ally = _by_vis(d, NEAR_ALLY_VIS)
        far_ally = _by_vis(d, FAR_ALLY_VIS)
        if ally is None:
            raise RuntimeError("montage impossible : %s absent" % NEAR_ALLY_VIS)
        if len(foes) < 2:
            raise RuntimeError("il faut >= 2 ennemis SUR LE PLATEAU pour separer contact/hors-contact")
        d_ally = _dist(hub, ally)
        d_near = _dist(hub, foes[0])
        d_far = _dist(hub, foes[-1])
        d_falone = _dist(hub, far_ally) if far_ally is not None else 9
        print("  [drive %d] hub=%s d(allie)=%s d(ennemi_proche)=%s d(ennemi_loin)=%s d(allie_loin)=%s"
              % (it, hub["pos"], d_ally, d_near, d_far, d_falone))
        if d_ally == 1 and d_near == 1 and d_far >= 2 and d_falone >= 2:
            return True
        if d_ally != 1:
            _step_toward(sid, rid, ally["id"], hub["pos"], 1)
        if d_falone < 2 and far_ally is not None:
            _step_toward(sid, rid, far_ally["id"], hub["pos"], 3)
        d, hub, foes = _snap()
        if _dist(hub, foes[0]) != 1:
            # Le pas « vers le hub » ne SUFFIT PAS quand le hub est dans un cul-de-sac : sur
            # `C3_26`/31337 il tombe en (0,4), colonne de BORD, et l'ennemi le plus proche oscille
            # 2<->3 pendant les 10 rounds. Le montage ne mesure alors PAS ce qu'il annonce -- 1081
            # perd toute cible valide et le natif se met a rendre `0x800
            # AddCasterIfAtLeastOneTarget` sur sa ligne self (residu NON PORTE, donc MISMATCH).
            # On demande d'abord au jeu s'il existe une tuile VOISINE atteignable ; sinon on SORT le
            # couple (hub, allie proche) du coin, exactement comme en T2 de `--bites`.
            if not _bring_to_contact(sid, rid, hub["id"], rounds=2):
                _unstick_pair(sid, rid, HUB_VIS, NEAR_ALLY_VIS)
        d, hub, foes = _snap()
        if _dist(hub, foes[-1]) < 2:
            _step_toward(sid, rid, foes[-1]["id"], hub["pos"], 4)
    print("  [drive] geometrie cible non atteinte -- on mesure la geometrie OBTENUE "
          "(les distances reelles sont imprimees dans chaque table)")
    return False


# --------------------------------------------------------------------------- variantes du port

def _ability(aid: int, variant: str):
    klass = ABILITY_CLASSES[aid]
    base = klass.TARGETING_OPTIONS
    if variant == "apres":
        return klass()
    if variant == "sansDyn":
        # CONTREFACTUEL DE LA REGLE DYNAMIQUE (#247) : masque INCHANGE (le bit
        # `TargetMatchesDynamicRule` reste pose, donc la cascade consulte bien le delegue), mais le
        # delegue est DESARME -- il retombe sur le defaut permissif d'`ActiveAbility`. C'est
        # exactement l'etat d'avant #247. Si desarmer la regle ne change AUCUNE ligne, le port ne
        # garde rien : c'est ce que le test de garde asserte.
        class _D(klass):
            __slots__ = ()

            def get_dynamic_invalid_target_reason(self, state, caster_id, target_id) -> int:
                return 0
        return _D()
    over = {"avant": None,
            "sansRules": _replace(base, rules=0),
            "sansRange": _replace(base, range=None),
            "melee1": _replace(base, force_melee_target=RANGED_BOOL_TRUE)}[variant]

    class _V(klass):
        __slots__ = ()
        TARGETING_OPTIONS = over
    return _V()


VARIANTS = ("apres", "avant", "sansRules", "sansRange", "melee1", "sansDyn")


def _nat(sid, rid, cid, aid, tid=None):
    body = {"runnerId": rid, "casterId": cid, "abilityType": aid}
    if tid is not None:
        body["targetId"] = tid
    out = _r(sid, "abilityReason", body, 60) or {}
    tr = out.get("targetReason") or {}
    cr = out.get("casterReason") or {}

    def _v(blk):
        h = blk.get("hex")
        if isinstance(h, str):
            return int(h, 16)
        return 0 if blk.get("ruleClass") == "NoBrokenTargetingRule" else None
    return _v(tr), (tr.get("reasons") or []), tr.get("ruleClass"), _v(cr), out


def _measure(sid, rid, st, dv, aid, caster_vis, residuals):
    """Une table par ability : chaque unite VIVANTE du plateau comme cible."""
    caster = _by_vis(dv, caster_vis)
    if caster is None:
        print("[%d] porteur %s ABSENT du plateau -- ability non mesuree" % (aid, caster_vis))
        return None
    cid = caster["id"]
    _, _, _, _, raw0 = _nat(sid, rid, cid, aid)
    usable = bool(((raw0 or {}).get("abilityState") or {}).get("usable"))
    mask = int(ABILITY_CLASSES[aid].TARGETING_OPTIONS.rules)
    rows = []
    for u in _actors(dv):
        tid = u["id"]
        dist = _dist(caster, u)
        side = "CASTER" if tid == cid else (
            "ALLIE" if u["owner"] == caster["owner"] else "ENNEMI")
        if u["machine"] and tid != cid:
            side += "/MoW"
        nv, reasons, rclass, cv, _ = _nat(sid, rid, cid, aid, tid)
        # PV de la CIBLE : c'est le REGIME que la ligne exerce, pas un ornement. `hp < hp_max` arme
        # le disjunct `IsDamagedUnit` d'`AttackQuery$$EntityCanBeHealed`, donc la regle dynamique de
        # 1082 -- et le test de garde en a besoin pour verifier que la mesure exerce bien le volet
        # PORTEE plutot que de le laisser masquer par un refus dynamique (cf. `measure_all`).
        hp, hp_max = _hp(st, tid)
        row = {"label": "%s %s" % (side, u["visualId"]), "targetId": tid, "dist": dist,
               "nat": nv, "nat_reasons": reasons, "nat_class": rclass, "nat_caster": cv,
               "hp": hp, "hp_max": hp_max}
        for v in VARIANTS:
            row[v] = int(get_invalid_target_reason(st, cid, tid, _ability(aid, v)))
        rows.append(row)

    print("\n[%d %s] caster=u%d(%s) pos=%s usable=%s masque=0x%x range=%s melee=%s"
          % (aid, caster_vis, cid, caster["visualId"], caster["pos"], usable, mask,
             ABILITY_CLASSES[aid].TARGETING_OPTIONS.range,
             ABILITY_CLASSES[aid].TARGETING_OPTIONS.force_melee_target))
    print("  %-22s %-5s %-3s %-13s %-24s %-13s %-9s %-11s %-11s %-9s %-9s %s"
          % ("cible", "id", "d", "natif", "regle", "APRES", "AVANT", "sansRules",
             "sansRange", "melee1", "sansDyn", "verdict"))
    stats = {"agree": 0, "dyn": 0, "gain": 0, "cf_rules": 0, "cf_range": 0, "cf_melee": 0,
             "cf_dyn": 0, "n": len(rows), "accept": 0, "refuse": 0, "residus": {},
             "residus_codes": dict(residuals)}
    for r in rows:
        dyn_line = (r["nat"] in residuals and r["apres"] == 0)
        agree = (r["nat"] == r["apres"])
        if agree:
            stats["agree"] += 1
        elif dyn_line:
            stats["dyn"] += 1
            k = residuals[r["nat"]]
            stats["residus"][k] = stats["residus"].get(k, 0) + 1
        if r["nat"] == 0:
            stats["accept"] += 1
        elif r["nat"] is not None:
            stats["refuse"] += 1
        gain = agree and r["nat"] not in (None, 0) and r["avant"] == 0
        if gain:
            stats["gain"] += 1
            stats["cf_rules"] += 1 if r["sansRules"] == 0 else 0
            stats["cf_range"] += 1 if r["sansRange"] == 0 else 0
        if r["melee1"] != r["apres"]:
            stats["cf_melee"] += 1
        if r["sansDyn"] != r["apres"]:
            stats["cf_dyn"] += 1        # #247 : lignes que la REGLE DYNAMIQUE tranche, et elle seule
        verdict = "OK" if agree else ("RESIDU" if dyn_line else "MISMATCH")
        print("  %-22s %-5d %-3s %-13s %-24s %-13s %-9s %-11s %-11s %-9s %-9s %s%s"
              % (r["label"], r["targetId"], "-" if r["dist"] is None else r["dist"],
                 "-" if r["nat"] is None else hex(r["nat"]),
                 ",".join(r["nat_reasons"]) or r["nat_class"] or "-",
                 hex(r["apres"]), hex(r["avant"]), hex(r["sansRules"]), hex(r["sansRange"]),
                 hex(r["melee1"]), hex(r["sansDyn"]), verdict, "  <-GAIN" if gain else ""))
    port_caster = int(get_invalid_caster_reason(st, cid, _ability(aid, "apres")))
    nat_caster = sorted(set(x for x in (r["nat_caster"] for r in rows) if x is not None))
    print("  [volet CASTER] natif=%s port=%s" % (nat_caster, hex(port_caster)))
    print("  [bilan] accord %d/%d ; lignes tranchees par une regle NON PORTEE (residus %s) : %d ; "
          "casts illegaux que master acceptait : %d"
          % (stats["agree"], stats["n"], stats["residus"] or "-", stats["dyn"], stats["gain"]))
    print("  [contrefactuels sur les %d lignes GAIN] sansRules faux-accepte %d ; sansRange "
          "faux-accepte %d ; force_melee_target flippe change %d ligne(s) ; regle DYNAMIQUE "
          "desarmee change %d ligne(s)"
          % (stats["gain"], stats["cf_rules"], stats["cf_range"], stats["cf_melee"],
             stats["cf_dyn"]))
    stats.update({"aid": aid, "caster": cid, "usable": usable, "port_caster": port_caster,
                  "nat_caster": nat_caster, "rows": rows})
    return stats


def measure_all(sid, seed=SEED, board=BOARD):
    """Monte le runner, BLESSE l'allie lointain, DRIVE la geometrie, fige l'etat, mesure les CINQ.

    POURQUOI L'ALLIE LOINTAIN EST BLESSE (et ce n'est pas un detail de confort). Le contrefactuel
    `sansRange` de 1082 doit exhiber une ligne que le volet PORTEE est SEUL a refuser. Depuis que
    #247 porte `InspiredToGreatnessAbility$$GetDynamicInvalidTargetReason`, un allie hors contact a
    PLEINS PV est refuse DEUX FOIS : par `RANGE_ADJACENT` (qui precede dans la cascade, d'ou le
    `TargetIsInRange` natif) ET par la regle dynamique (`0x1`, aucun des trois disjuncts vrai).
    Neutraliser la portee ne fait alors RIEN apparaitre -- `cf_range` tombe a 0 et le volet portee
    n'est plus valide par la mesure. MESURE du 2026-07-29, ligne `ALLIE tauCrisis` de 1082 :
    `natif 0x8000000 | APRES 0x8000000 | sansRange 0x1`. Ce n'etait donc PAS « aucune cible alliee
    hors contact » (elle etait bien la, a d=2) mais un contrefactuel devenu muet.

    BLESSER la cible arme le disjunct `IsDamagedUnit` d'`EntityCanBeHealed` : la regle dynamique
    ACCEPTE, et `sansRange` redevient `0` -- le faux-accept que le volet portee empeche. Le regime
    est VERIFIE (PV relus), jamais suppose ; l'echec est une RuntimeError, pas un skip.

    Rend `({ability_type: stats}, dispose)` -- `dispose()` est a appeler par l'appelant (le probe le
    fait dans son `finally`, le test de garde dans le teardown de sa fixture). MEME implementation
    pour le probe (qui MESURE) et le test (qui GARDE) : aucune divergence possible entre les deux."""
    seed_bc = _seed_bc_with_ammo()
    rid, state_file = _build(sid, seed, board, seed_bc)
    print("[build] runner=%d board=%s seed=%s seed-bc=%s (MachineOfWarAmmo patche)"
          % (rid, board, seed, seed_bc.name))

    def _dispose():
        try:
            _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=30)
            print("[cleanup] runner %d dispose" % rid)
        except Exception as e:                                       # noqa: BLE001
            print("[cleanup] dispose KO: %s" % e)
        finally:
            state_file.unlink(missing_ok=True)
            seed_bc.unlink(missing_ok=True)

    try:
        for _ in range(TOURS_DE_CHAUFFE):
            _act(sid, rid, {"kind": "endturn"}, 60)
        far = _by_vis(_dv(sid, rid), FAR_ALLY_VIS)
        if far is None:
            raise RuntimeError("montage impossible : %s absent du plateau" % FAR_ALLY_VIS)
        hp0, hp1 = _wound(sid, rid, far["id"])
        print("[wound] %s u%d : hp %s -> %s" % (FAR_ALLY_VIS, far["id"], hp0, hp1))
        if not (hp0 is not None and hp1 is not None and hp1 < hp0):
            raise RuntimeError(
                "regime BLESSE non atteint sur %s (hp %s -> %s) : le contrefactuel `sansRange` de "
                "1082 ne peut PAS exposer de faux-accept, la regle dynamique refusant deja la ligne"
                % (FAR_ALLY_VIS, hp0, hp1))
        _drive_cluster(sid, rid)
        _hand_to(sid, rid, HUB_VIS)

        dv = _dv(sid, rid)
        ob = _r(sid, "observeBattle", {"runnerId": rid}, 60)
        snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 60)
        bg = _r(sid, "boardGraph", {"runnerId": rid}, 90)
        if not (isinstance(bg, dict) and bg.get("tiles")):
            raise RuntimeError("boardGraph indisponible")
        st = load_state(dv, ob, snap, board=Board(bg["tiles"], adjacency="native_sym"))
        out = {}
        for aid, vis, _name, res in CASES:
            s = _measure(sid, rid, st, dv, aid, vis, res)
            if s is not None:
                out[aid] = s
        return out, _dispose
    except BaseException:
        _dispose()
        raise


# --------------------------------------------------------------------------- #247 : les DEUX regles
# dynamiques, dans le montage ou elles MORDENT (et son contrefactuel LIVE)

def _bring_to_contact(sid, rid, victim_id, rounds=8):
    """Amene un ennemi de `victim_id` A DISTANCE 1, et rend le booleen correspondant.

    C'est un regime DISTINCT de celui de `_wound`, et il a fallu la mesure pour le voir : les
    `necroWarden` sont RANGED. Sur `C3_26`/31337 `castFromTiles` leur trouve une tuile de tir a
    **d=3** -- la victime est bien blessee (donc 1082 bascule), mais `GetAdjacentEnemies(caster)`
    reste VIDE et 1081 continue de rendre `0x2`. Blesser et mettre au contact sont deux gestes
    separes ; ce helper ne fait que le second.

    On demande au jeu les tuiles LEGALES (`aiMovableTiles`, qui respecte relief et occupation) et on
    garde celles a distance 1 de la victime -- jamais un pas « vers » elle qui pourrait tourner en
    rond dans un cul-de-sac."""
    for it in range(rounds):
        dv = _dv(sid, rid)
        me = next((a for a in _actors(dv) if a["id"] == int(victim_id)), None)
        if me is None or None in me["pos"]:
            return False
        foes = sorted((a for a in _actors(dv)
                       if a["owner"] != me["owner"] and None not in a["pos"] and not a["machine"]),
                      key=lambda a: (_dist(me, a), a["id"]))
        if not foes:
            return False
        if _dist(me, foes[0]) == 1:
            return True
        moved = False
        for f in foes:
            _hand_to_owner(sid, rid, f["owner"])
            want = [t for t in _movable(sid, rid, f["id"])
                    if hexgeo.distance(t, me["pos"]) == 1]
            if not want:
                continue
            _act(sid, rid, {"kind": "move", "unitId": f["id"],
                            "to": {"col": want[0][0], "row": want[0][1]}}, 90)
            print("  [contact %d] u%s -> %s (voisin de u%s)" % (it, f["id"], want[0], victim_id))
            moved = True
            break
        if not moved:
            print("  [contact %d] aucune tuile voisine atteignable -- on rapproche u%s"
                  % (it, foes[0]["id"]))
            _step_toward(sid, rid, foes[0]["id"], me["pos"], 1)
            _act(sid, rid, {"kind": "endturn"}, 60)
    dv = _dv(sid, rid)
    me = next((a for a in _actors(dv) if a["id"] == int(victim_id)), None)
    foes = [a for a in _actors(dv)
            if me is not None and a["owner"] != me["owner"] and None not in a["pos"]]
    return bool(me is not None and foes and min(_dist(me, f) for f in foes) == 1)


def _unstick_pair(sid, rid, hub_vis, ally_vis):
    """SORT le couple (hub, allie) d'un cul-de-sac, en gardant l'allie AU CONTACT.

    Le hub avance de deux pas vers l'assaillant le plus proche (donc vers du terrain ouvert : c'est
    de LA que l'ennemi vient), puis l'allie recolle a d=1. Sert de deblocage a `_wound` quand aucun
    ennemi n'arrive au contact -- cf. le commentaire de `measure_dynamic_bites`."""
    d = _dv(sid, rid)
    hub = _by_vis(d, hub_vis)
    if hub is None or None in hub["pos"]:
        return
    foes = sorted((a for a in _actors(d)
                   if a["owner"] != hub["owner"] and None not in a["pos"] and not a["machine"]),
                  key=lambda a: (_dist(hub, a), a["id"]))
    if not foes:
        return
    _step_toward(sid, rid, hub["id"], foes[0]["pos"], 2)
    d = _dv(sid, rid)
    hub, ally = _by_vis(d, hub_vis), _by_vis(d, ally_vis)
    if hub is not None and ally is not None and _dist(hub, ally) != 1:
        _step_toward(sid, rid, ally["id"], hub["pos"], 1)


def _drive_isolated(sid, rid, hub_vis, ally_vis, foe_min=3, rounds=12):
    """Monte la geometrie qui fait MORDRE `FightingRetreatAbility$$GetDynamicInvalidTargetReason` :

      * `ally_vis` (ALLIE, SANS le trait `RangedSpecialist`) AU CONTACT de `hub_vis`
        -> une cible qui PASSE le volet portee `RANGE_ADJACENT`, donc qui ATTEINT la regle ;
      * TOUS les ennemis a distance >= `foe_min` de `hub_vis`
        -> `GetAdjacentEnemies(hub)` VIDE, donc le 1er `Any` ne court-circuite plus.

    C'est exactement la configuration que le montage de #250 n'avait pas (Darkstrider y avait un
    ennemi au contact, d'ou la regle mesuree INERTE). Le 2e disjunct reste faux : un
    `RangedSpecialist` ne se DESACTIVE qu'au turn-start d'un porteur adjacent a un ennemi, et ici
    plus personne ne l'est -- `ally_vis` est de toute facon choisi SANS ce trait."""
    def _snap():
        d = _dv(sid, rid)
        hub = _by_vis(d, hub_vis)
        ally = _by_vis(d, ally_vis)
        if hub is None or ally is None:
            raise RuntimeError("montage impossible : %s / %s absent" % (hub_vis, ally_vis))
        foes = sorted((a for a in _actors(d)
                       if a["owner"] != hub["owner"] and None not in a["pos"]),
                      key=lambda a: (_dist(hub, a), a["id"]))
        return d, hub, ally, foes

    for it in range(rounds):
        d, hub, ally, foes = _snap()
        d_ally = _dist(hub, ally)
        d_near = _dist(hub, foes[0]) if foes else 99
        print("  [isole %d] hub=%s d(allie)=%s d(ennemi_le_plus_proche)=%s"
              % (it, hub["pos"], d_ally, d_near))
        if d_ally == 1 and d_near >= foe_min:
            return True
        if d_ally != 1:
            _step_toward(sid, rid, ally["id"], hub["pos"], 1)
        d, hub, ally, foes = _snap()
        for f in foes:
            if _dist(hub, f) < foe_min:
                _step_toward(sid, rid, f["id"], hub["pos"], foe_min + 2)
    print("  [isole] geometrie cible NON atteinte -- les distances reelles sont imprimees")
    return False


def _line(sid, rid, st, cid, aid, tid):
    """Une ligne (caster, ability, cible) : (natif, port APRES, port avec la regle DYNAMIQUE
    desarmee). C'est le triplet qui fait le contrefactuel de #247."""
    nat, _reasons, _cls, _cr, _raw = _nat(sid, rid, cid, aid, tid)
    return (nat,
            int(get_invalid_target_reason(st, cid, tid, _ability(aid, "apres"))),
            int(get_invalid_target_reason(st, cid, tid, _ability(aid, "sansDyn"))))


def _load(sid, rid, board_graph=None):
    dv = _dv(sid, rid)
    ob = _r(sid, "observeBattle", {"runnerId": rid}, 60)
    snap = _r(sid, "combatSnapshot", {"runnerId": rid}, 60)
    bg = board_graph or _r(sid, "boardGraph", {"runnerId": rid}, 90)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        raise RuntimeError("boardGraph indisponible")
    return dv, load_state(dv, ob, snap, board=Board(bg["tiles"], adjacency="native_sym")), bg


def _hp(st, uid):
    from engine.runner.components import HealthComponent
    e = st.get_entity(int(uid))
    hc = e.get_component(HealthComponent) if e is not None else None
    return (None, None) if hc is None else (hc.hp, hc.hp_max)


def measure_dynamic_bites(sid, seed=SEED, board=BOARD):
    """LES DEUX REGLES DYNAMIQUES, mesurees dans l'etat ou elles MORDENT -- puis dans son
    BASCULEMENT, sur le MEME runner.

    T1 -- Darkstrider ISOLE (aucun ennemi au contact), Aun'Shi a son contact :
        1081 (caster Darkstrider, cible Aun'Shi) : le natif rend `0x2 TargetMatchesDynamicRule`
             (la regle mord : ni ennemi adjacent, ni allie a RangedSpecialist desactive) ;
        1082 (caster Aun'Shi, cible Darkstrider)  : le natif rend `0x1 ValidRequest`
             (Darkstrider est a PLEINS PV, non-mecanique, actif NON consomme -> les trois
             disjuncts sont faux).
    T2 -- un ennemi est amene AU CONTACT de Darkstrider et l'ATTAQUE :
        1081 : `GetAdjacentEnemies` n'est plus vide            -> 0
        1082 : Darkstrider est BLESSE, donc `EntityCanBeHealed` -> 0
    Les deux verdicts basculent ENSEMBLE, par deux disjuncts DIFFERENTS. C'est ce qui prouve que
    les regles portees ne sont pas des refus constants -- un port qui refuserait toujours passerait
    T1 et echouerait T2, et reciproquement.

    Rend `(resultats, dispose)`."""
    seed_bc = _seed_bc_with_ammo()
    rid, state_file = _build(sid, seed, board, seed_bc)
    print("[build bites] runner=%d board=%s seed=%s" % (rid, board, seed))

    def _dispose():
        try:
            _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=30)
            print("[cleanup] runner %d dispose" % rid)
        except Exception as e:                                       # noqa: BLE001
            print("[cleanup] dispose KO: %s" % e)
        finally:
            state_file.unlink(missing_ok=True)
            seed_bc.unlink(missing_ok=True)

    try:
        for _ in range(TOURS_DE_CHAUFFE):
            _act(sid, rid, {"kind": "endturn"}, 60)
        geom = _drive_isolated(sid, rid, "tauDarkstrider", "tauAunShi")
        _hand_to(sid, rid, "tauDarkstrider")
        dv, st, bg = _load(sid, rid)
        ds = _by_vis(dv, "tauDarkstrider")
        aun = _by_vis(dv, "tauAunShi")
        if ds is None or aun is None:
            raise RuntimeError("porteurs absents du plateau")
        foes = sorted((a for a in _actors(dv)
                       if a["owner"] != ds["owner"] and None not in a["pos"]),
                      key=lambda a: (_dist(ds, a), a["id"]))
        out = {"geometry_ok": geom, "d_ally": _dist(ds, aun),
               "d_foe": _dist(ds, foes[0]) if foes else None,
               "hp_before": _hp(st, ds["id"])}
        out["t1_1081"] = _line(sid, rid, st, ds["id"], 1081, aun["id"])
        out["t1_1082"] = _line(sid, rid, st, aun["id"], 1082, ds["id"])
        print("\n[T1 Darkstrider ISOLE]  d(allie)=%s d(ennemi)=%s hp=%s"
              % (out["d_ally"], out["d_foe"], out["hp_before"]))
        print("  1081 caster=Darkstrider cible=AunShi   natif/APRES/sansDyn = %s"
              % (tuple(hex(v) if v is not None else "-" for v in out["t1_1081"]),))
        print("  1082 caster=AunShi cible=Darkstrider   natif/APRES/sansDyn = %s"
              % (tuple(hex(v) if v is not None else "-" for v in out["t1_1082"]),))

        # --- T2 : un ennemi AU CONTACT de Darkstrider, qui l'ATTAQUE (donc le BLESSE).
        # Les DEUX moities du basculement passent par ce meme geste, mais par des chemins
        # DIFFERENTS : 1081 lit la seule PRESENCE de l'ennemi adjacent (`Any(GetAdjacentEnemies)`),
        # 1082 lit les PV de la cible (`IsDamagedUnit` d'`EntityCanBeHealed`). Un ennemi amene au
        # contact SANS frapper ne bascule donc que 1081 -- c'est exactement l'etat que mesurait le
        # montage de #247, dont le `{"kind": "attack"}` etait un NO-OP silencieux (cf. `_wound`).
        #
        # DEBLOCAGE : `_drive_isolated` subit la tuile de SPAWN du hub. MESURE (`C3_26`/31337) : elle
        # tombe en (0,5), colonne de BORD -- des voisins hors plateau, un pris par Aun'Shi, et les
        # trois `necroWarden` stagnent a d=2 pendant 14 rounds. Un cul-de-sac ne se CONSTATE pas, il
        # se DEFAIT : on sort Darkstrider du coin (2 pas vers l'assaillant) et Aun'Shi RECOLLE, ce
        # qui restaure les deux invariants de T2 (`d_foe == 1` pour 1081, `d_ally == 1` pour la
        # portee `RANGE_ADJACENT` de 1082). Les deux verdicts de T1 sont deja mesures : ce
        # deplacement ne peut rien leur reprendre.
        hp0 = hp1 = None
        for attempt in range(3):
            hp0, hp1 = _wound(sid, rid, ds["id"], rounds=8)
            if hp0 is not None and hp1 is not None and hp1 < hp0:
                break
            print("  [debloc %d] aucune tuile de tir sur la victime -- on la SORT du cul-de-sac, "
                  "l'allie recolle" % attempt)
            _unstick_pair(sid, rid, "tauDarkstrider", "tauAunShi")
        print("\n[wound] tauDarkstrider u%d : hp %s -> %s" % (ds["id"], hp0, hp1))
        # Le CONTACT est un SECOND regime, a poser APRES la blessure (le cast de `_wound` peut
        # deplacer son tireur). Sans lui, 1081 ne bascule pas : sa regle lit `GetAdjacentEnemies`,
        # pas les PV.
        for attempt in range(3):
            if _bring_to_contact(sid, rid, ds["id"]):
                break
            print("  [debloc contact %d] aucun voisin atteignable -- on SORT la victime du "
                  "cul-de-sac, l'allie recolle" % attempt)
            _unstick_pair(sid, rid, "tauDarkstrider", "tauAunShi")
        _hand_to(sid, rid, "tauDarkstrider")
        dv, st, _bg = _load(sid, rid, bg)
        ds = _by_vis(dv, "tauDarkstrider")
        aun = _by_vis(dv, "tauAunShi")
        foes = sorted((a for a in _actors(dv)
                       if a["owner"] != ds["owner"] and None not in a["pos"]),
                      key=lambda a: (_dist(ds, a), a["id"]))
        out["d_ally_t2"] = _dist(ds, aun) if aun is not None else None
        out["d_foe_t2"] = _dist(ds, foes[0]) if foes else None
        out["hp_after"] = _hp(st, ds["id"])
        out["t2_1081"] = _line(sid, rid, st, ds["id"], 1081, aun["id"])
        out["t2_1082"] = _line(sid, rid, st, aun["id"], 1082, ds["id"])
        print("\n[T2 ennemi AU CONTACT + attaque]  d(allie)=%s d(ennemi)=%s hp=%s"
              % (out["d_ally_t2"], out["d_foe_t2"], out["hp_after"]))
        print("  1081 caster=Darkstrider cible=AunShi   natif/APRES/sansDyn = %s"
              % (tuple(hex(v) if v is not None else "-" for v in out["t2_1081"]),))
        print("  1082 caster=AunShi cible=Darkstrider   natif/APRES/sansDyn = %s"
              % (tuple(hex(v) if v is not None else "-" for v in out["t2_1082"]),))
        return out, _dispose
    except BaseException:
        _dispose()
        raise


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--bites", action="store_true",
                    help="#247 : montage ou les DEUX regles dynamiques MORDENT + son basculement")
    a = ap.parse_args(argv)

    sid = _resolve_session()
    if a.bites:
        res, dispose = measure_dynamic_bites(sid, a.seed, a.board)
        try:
            ok = (res["t1_1081"][0] == res["t1_1081"][1] and res["t1_1082"][0] == res["t1_1082"][1]
                  and res["t2_1081"][0] == res["t2_1081"][1]
                  and res["t2_1082"][0] == res["t2_1082"][1]
                  and res["t1_1081"][0] != 0 and res["t1_1082"][0] != 0
                  and res["t2_1081"][0] == 0 and res["t2_1082"][0] == 0
                  and res["t1_1081"][2] == 0 and res["t1_1082"][2] == 0)
            print("\n[VERDICT bites] %s" % ("PASS" if ok else "FAIL"))
            print("[RAW] " + json.dumps(res))
            return 0 if ok else 1
        finally:
            dispose()

    stats, dispose = measure_all(sid, a.seed, a.board)
    try:
        print("\n================ SYNTHESE (board=%s seed=%s) ================" % (a.board, a.seed))
        ok = len(stats) == len(CASES)
        for s in stats.values():
            reste = s["n"] - s["agree"] - s["dyn"]
            print("  %d : accord %d/%d, residus %d %s, mismatch %d, gains %d, accept/refus natif "
                  "%d/%d, usable=%s" % (s["aid"], s["agree"], s["n"], s["dyn"], s["residus"] or "",
                                        reste, s["gain"], s["accept"], s["refuse"], s["usable"]))
            if reste:
                ok = False
        print("[VERDICT] %s" % ("PASS" if ok else "FAIL"))
        print("[RAW] " + json.dumps(list(stats.values())))
        return 0 if ok else 1
    finally:
        dispose()


if __name__ == "__main__":
    sys.exit(main())
