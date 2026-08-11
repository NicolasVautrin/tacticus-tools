#!/usr/bin/env python
"""probe_890_hive_tyrant -- CONFRONTATION LIVE des deux actives du Hive Tyrant Leviathan.

    python probe_890_hive_tyrant.py --case catalyst
    python probe_890_hive_tyrant.py --case cannon
    python probe_890_hive_tyrant.py --case feet

`1032 Catalyst` et `1056 StranglethornCannon`, portees par `tyranBossHiveTyrantLeviathan` (SEUL
porteur des deux). Le boss n'est PAS dans `rl_duel build --list-pool` : il entre par
`--explicit-stats <id>:<palier>` (injection catalogue), et le jeu le republie sous l'id d'entite
REMAPPE `GuildBoss2Boss1TyranHiveTyrantLeviathan` -- d'ou la resolution par visualId dans
`_boss_id`. (Le garde de roster butait sur ce remappage ; **#895 l'a repare**, donc plus aucune
echappatoire n'est posee ici -- cf. `build`.)

Board : **`CE2_boss`** -- la carte que le gameconfig declare pour CE boss
(`battles/campaigns/*/battles[]`, `BoardId`), 7x10, `IsBossBoard`, et la SEULE des deux a porter une
`BossPlatform` (3 tuiles). `MC1_67` en porte **0** : c'est mesure ici (`--case feet`), pas suppose.

Ce que chaque cas EXERCE -- et c'est le point, pas l'accord :

* `catalyst` : le roster porte QUATRE non-cibles, chacune pour une raison DIFFERENTE --
  le CASTER lui-meme (`op_Subtraction`), un allie NON-Tyranide (`UnitsFromFaction`), un second allie
  non-Tyranide, et un Tyranide **ENNEMI** (`Friends`). Un selecteur a qui il manquerait n'importe
  lequel des trois filtres buffe quelqu'un de plus. Les montants discriminent aussi : `extraArmor` et
  `blockDmg` sont scales par `AbilityVariablesMultiplierPercentage` (200 % au palier 4) et
  `blockChance` NON (c'est une constante) -- trois nombres, trois regimes.

* `cannon` : placements EXPLICITES (`--place` / `--a-place`) pour que le ring-1 de la cible
  contienne A LA FOIS deux ennemis et **un allie du caster**, un autre allie restant a distance 3.
  Le volet splash natif passe `AdjacentUnits` **BRUT** (aucun wrapper `Enemies`) : l'allie adjacent
  DOIT prendre un coup. C'est la seule configuration ou un port qui aurait recopie le patron
  PlasmaGrenade/HarvesterOfSouls (ring-1 filtre aux ennemis) rend un resultat different.

ASCII only (cp1252). Dispose SES runners (jamais ceux des autres).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile

import hexgeo
import probe_112_darkangels as PR
import rl_collect_batch as R

from engine.entities.pathfinding.board import Board
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.snapshot import (bind_live_rpc, clear_ability_states_cache, load_state,
                                    runner_label)
from engine.services.battle_query import attack_range_type

CATALYST = 1032
STRANGLETHORN = 1056
BOSS = "tyranBossHiveTyrantLeviathan"
BOSS_TIER = "%s:4" % BOSS            # palier haut : 34277 PV, niveau 55, multiplicateur 200 %
BOSS_BOARD = "CE2_boss"              # la carte declaree par le gameconfig pour CE boss
SEED = 777

PYDIR = os.path.dirname(os.path.abspath(__file__))


# --------------------------------------------------------------------------- build

def build(p_units, a_units, places=(), a_places=(), board=BOSS_BOARD, seed=SEED):
    """Monte un runner par `rl_duel.py build` (le SEUL chemin qui sache injecter un boss hors pool).

    Rend `(sid, rid)`. Le runner est enregistre dans `PR._rids` pour que `PR.dispose` le retrouve.

    ⚠ **AUCUNE echappatoire de roster n'est posee, et c'est DELIBERE.** Ce probe a d'abord tourne
    sous `TACTICUS_ALLOW_ROSTER_DEFICIT=1` : le garde comparait `tyranBossHiveTyrantLeviathan` a l'id
    d'entite REMAPPE (`GuildBoss2Boss1TyranHiveTyrantLeviathan`) et rendait
    `demande x1 mais MONTE x0` -- un refus DUR sur un boss pourtant EN BATAILLE. #895 a repare le
    garde (il resout desormais le remappage), donc le build passe `rc=0` sans rien neutraliser --
    VERIFIE. Garder la variable ferait taire un VRAI deficit de roster, ce qui est exactement le
    genre de vert qui ne prouve rien."""
    fd, path = tempfile.mkstemp(prefix="probe889_", suffix=".json")
    os.close(fd)
    argv = [sys.executable, os.path.join(PYDIR, "rl_duel.py"), "build",
            "--board", board, "--seed", str(seed), "--state-file", path,
            "--explicit-stats", BOSS_TIER,
            "--p-units", ",".join(p_units), "--a-units", ",".join(a_units)]
    for p in places:
        argv += ["--place", p]
    for p in a_places:
        argv += ["--a-place", p]
    # `TACTICUS_ALLOW_ROSTER_DEFICIT` est RETIRE de l'environnement s'il traine : un probe qui
    # herite d'une echappatoire posee par son appelant ne mesure plus le meme montage (cf. docstring).
    env = {k: v for k, v in os.environ.items() if k != "TACTICUS_ALLOW_ROSTER_DEFICIT"}
    proc = subprocess.run(argv, capture_output=True, text=True, env=env, cwd=PYDIR)
    st = None
    try:
        with open(path, "r") as fh:
            st = json.load(fh)
    except Exception:
        pass
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
    if not st or st.get("runnerId") is None:
        raise RuntimeError("build KO (rc=%s) :\n%s\n%s"
                           % (proc.returncode, proc.stdout[-2000:], proc.stderr[-2000:]))
    rid = int(st["runnerId"])
    PR._rids.append(rid)
    return int(R._resolve_session()), rid


# --------------------------------------------------------------------------- helpers

def tags(e):
    tg = e.get("tags")
    if isinstance(tg, str):
        try:
            return json.loads(tg)
        except Exception:
            return {}
    return tg or {}


def capture(sid, rid):
    dec = PR.rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 300)
    ob = PR.rpc(sid, "observeBattle", {"runnerId": rid}, 60)
    snap = PR.rpc(sid, "combatSnapshot", {"runnerId": rid}, 120)
    bg = PR.rpc(sid, "boardGraph", {"runnerId": rid}, 60)
    rng = PR.rpc(sid, "dumpRng", {"runnerId": rid}, 30)
    return dec, ob, snap, bg, rng


def offline_state(sid, dec, ob, snap, bg, rngdump):
    """Etat Python charge depuis le MEME instant que le cast live, PRNG compris (sans quoi les
    montants ne seraient pas comparables).

    ⚠ `bind_live_rpc` est OBLIGATOIRE ICI, et son absence est SILENCIEUSE : sans transport lie,
    `load_state` rend `ability_states_seed.source == "no-transport"` et le canal `unitAbilityStates`
    n'est PAS tire -- or c'est le SEUL qui porte le niveau d'ability du boss (son
    `combatSnapshot.unitConfig` est `{"error": "config null"}`). Mesure du regime non lie :
    `extraArmor` 10 au lieu de 1190. On ASSERTIONNE donc la source, plutot que d'esperer."""
    prev = bind_live_rpc(lambda method, body=None, timeout=90: PR.rpc(sid, method, body or {},
                                                                     timeout))
    try:
        st = load_state(dec, ob, snap, board=Board(bg["tiles"], adjacency="native_sym"))
    finally:
        bind_live_rpc(prev)
    src = (getattr(st, "ability_states_seed", None) or {}).get("source")
    if src in (None, "no-transport"):
        raise RuntimeError("canal unitAbilityStates NON tire (source=%s) -- la mesure serait faite "
                           "au niveau 1 sans le dire" % src)
    r = IntBasedMersenneTwister()
    r.mt = list(rngdump["mt"])
    r.mti = rngdump["mti"]
    st.rng = r
    return st


def _boss_id(dec):
    """L'entite du boss dans la vue. On la cherche par son visualId REMAPPE (le seul que la vue
    publie) ET par la presence des trois actives du kit -- deux voies, pour ne pas dependre du nom."""
    for u in dec.get("units") or []:
        vid = str(u.get("visualId") or "")
        if "TyranHiveTyrant" in vid:
            return u["id"]
    for u in dec.get("units") or []:
        ids = {a.get("abilityId") or a.get("id") for a in (u.get("abilities") or [])}
        if CATALYST in ids and STRANGLETHORN in ids:
            return u["id"]
    return None


def _by_visual(dec):
    return {str(u.get("visualId")): u["id"] for u in (dec.get("units") or [])}


def stat_deltas(sid, rid, before):
    snap = PR.rpc(sid, "combatSnapshot", {"runnerId": rid}, 120)
    out = {}
    for u in snap.get("units") or []:
        s = u["stats"]
        b = before[u["entityId"]]
        out[u["entityId"]] = (s["fixedArmor"] - b[0], s["blockChance"] - b[1],
                              s["blockDamage"] - b[2])
    return out


def stat_base(sid, rid):
    snap = PR.rpc(sid, "combatSnapshot", {"runnerId": rid}, 120)
    return {u["entityId"]: (u["stats"]["fixedArmor"], u["stats"]["blockChance"],
                            u["stats"]["blockDamage"]) for u in snap.get("units") or []}


def live_hits(events, ability):
    """`[(targetId, montant), ...]` des coups de CETTE ability, dans l'ORDRE d'emission."""
    out = []
    for e in events or []:
        tg = tags(e)
        if tg.get("Active_Ability_Type") != ability or "Amount" not in tg:
            continue
        out.append((tg.get("Target_Id"), int(tg.get("Amount"))))
    return out


def _port_hits(port):
    """La MEME forme que `live_hits` a partir du retour de `execute_behaviour` : main d'abord (ses
    coups dans l'ordre), puis le splash dans l'ordre du `multi=True` (tri par id)."""
    out = []
    m = (port or {}).get("main_attack") or {}
    tgt = (port or {}).get("target")
    for amt in (m.get("per_hit") or []):
        out.append((tgt, int(amt)))
    for s in ((port or {}).get("splash") or []):
        for amt in ((s.get("attack") or {}).get("per_hit") or []):
            out.append((s.get("target"), int(amt)))
    return out


# --------------------------------------------------------------------------- cas FEET

def case_feet():
    """L'EMPREINTE du boss : combien de tuiles occupe-t-il ? (`decisionView.units[].feet`.)

    ⚠ **LA QUESTION GENERALE EST TRANCHEE, ET PAS PAR CE CANAL** (#895/#896) : un boss monte par
    `rl_duel` est **MONO-HEX**, et c'est le JEU qui le dit -- `1193 NovaCharge` porte
    `TargetingRule.CasterHas7Tiles` (famille `CasterHas1/3/7Tiles` = `GetFeetCount(caster) != N` ->
    refus), et sur le meme caster au meme instant `abilityTargets(1194)` rend 66 cibles quand
    `abilityTargets(1193)` en rend 0. `feet`, lui, rend `1` pour TOUT LE MONDE et ne prouve donc
    rien -- c'est la raison pour laquelle ce cas ne conclut PAS a partir de lui.

    Ce que ce cas mesure quand meme, et qui reste utile : (a) le chiffre du canal sur les DEUX bords
    (boss et voisins) pour le meme build ; (b) la `BossPlatform` que le DUMP DE BOARD declare, qui,
    elle, DISCRIMINE entre les deux cartes -- `CE2_boss` en porte une de 3 tuiles, `MC1_67` zero.
    L'ecart entre (a) et (b) est exactement le residu `#890-r4` : la plateforme existe dans la
    donnee et n'est pas consommee par notre voie de montage.

    Les DEUX masques du Hive Tyrant ont ete relus sur cet axe : `0x8004` et `0x100004002` ne portent
    AUCUN bit `CasterHas{1,3,7}Tiles` -- ce boss-ci n'offre donc pas la porte native qui a tranche
    pour `tauBossRiptide`."""
    out = {"boards": {}}
    for bid in (BOSS_BOARD, "MC1_67"):
        d = R._load_board_dump(bid)
        b = d["board"]
        out["boards"][bid] = {
            "w": b.get("Width"), "h": b.get("Height"), "isBossBoard": bool(b.get("IsBossBoard")),
            "bossPlatforms": [{"size": p.get("Size"),
                               "tiles": [(t["Column"], t["Row"]) for t in (p.get("Tiles") or [])],
                               "initialSpawn": bool(p.get("InitialSpawnPosition"))}
                              for p in (b.get("BossPlatforms") or [])],
        }
    sid, rid = build([BOSS_TIER, "tyranTyrantGuard"], ["ultraCalgar"])
    try:
        dec = PR.rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 300)
        boss = _boss_id(dec)
        out["boss_entity"] = boss
        out["feet"] = {u["id"]: len(u.get("feet") or []) for u in (dec.get("units") or [])}
        out["boss_feet"] = out["feet"].get(boss)
        out["pos"] = {u["id"]: (u["pos"]["col"], u["pos"]["row"]) for u in (dec.get("units") or [])}
    finally:
        # Le cache `unitAbilityStates` est cle par LABEL DE RUNNER, et un id de runner peut etre
        # RECYCLE par un build ulterieur -> on purge en meme temps qu'on dispose.
        clear_ability_states_cache(runner_label({"runner": "build#%s" % rid}))
        clear_ability_states_cache()
        PR.dispose(sid, rid)
    return out


# --------------------------------------------------------------------------- cas CATALYST

#: Le roster de `--case catalyst`. Les DEUX Tyranides allies sont les seules cibles attendues ;
#: les quatre autres unites sont chacune une NON-cible pour une raison differente.
CATALYST_P = [BOSS_TIER, "tyranTyrantGuard", "tyranNeurothrope", "ultraTitus", "templChampion"]
CATALYST_A = ["tyranDeathleaper", "ultraCalgar", "worldKharn"]


def case_catalyst():
    from engine.runner.abilities.tyranids import CatalystAbility

    sid, rid = build(CATALYST_P, CATALYST_A)
    try:
        dec, ob, snap, bg, rngd = capture(sid, rid)
        boss = _boss_id(dec)
        bv = _by_visual(dec)
        roles = {
            "caster": boss,
            "ally_tyranid_1": bv.get("tyranTyrantGuard"),
            "ally_tyranid_2": bv.get("tyranNeurothrope"),
            "ally_other_1": bv.get("ultraTitus"),
            "ally_other_2": bv.get("templChampion"),
            "enemy_tyranid": bv.get("tyranDeathleaper"),
            "enemy_other_1": bv.get("ultraCalgar"),
            "enemy_other_2": bv.get("worldKharn"),
        }
        st = offline_state(sid, dec, ob, snap, bg, rngd)
        port = CatalystAbility().execute_behaviour(st, boss, boss) or {}
        base = stat_base(sid, rid)
        res = PR.cast(sid, rid, boss, boss, CATALYST)
        deltas = stat_deltas(sid, rid, base)
        # Ground truth = les ChangeStats du cast (le stream), et non le decisionView d'apres-coup.
        native = {}
        turns = set()
        order = []
        for e in res.get("events") or []:
            tg = tags(e)
            for key, stat in (("UnitStats_FixedArmor_Modification_Change", "armor"),
                              ("UnitStats_BlockChance_Modification_Change", "chance"),
                              ("UnitStats_BlockDamage_Modification_Change", "damage")):
                if key in tg:
                    native.setdefault(e.get("entity"), {})[stat] = int(tg[key])
                    order.append((stat, e.get("entity")))
            if "Effect_RemainingTurns" in tg:
                turns.add(int(tg["Effect_RemainingTurns"]))
        return {"roles": roles, "native": native, "native_order": order,
                "native_turns": sorted(turns), "deltas": deltas,
                "port": port, "ok_apply": res.get("ok"), "mutated": res.get("mutated")}
    finally:
        # Le cache `unitAbilityStates` est cle par LABEL DE RUNNER, et un id de runner peut etre
        # RECYCLE par un build ulterieur -> on purge en meme temps qu'on dispose.
        clear_ability_states_cache(runner_label({"runner": "build#%s" % rid}))
        clear_ability_states_cache()
        PR.dispose(sid, rid)


# --------------------------------------------------------------------------- cas CANNON

#: Geometrie EXPLICITE (le boss est `moveNone` : sans placement force, rien ne garantit qu'un allie
#: soit dans le ring-1 de la cible). Distances hex mesurees : cible a 2 du caster (donc
#: `TargetIsNotAdjacent` satisfait ET dans `range`=3) ; `ultraTitus` ALLIE a 1 de la cible ;
#: `templChampion` ALLIE a 3 de la cible (temoin negatif) ; deux ennemis a 1 de la cible.
CANNON_P = [BOSS_TIER, "ultraTitus", "templChampion"]
CANNON_A = ["ultraCalgar", "worldKharn", "tyranTyrantGuard"]
CANNON_PLACES = ["%s:0,0" % BOSS_TIER, "ultraTitus:1,1", "templChampion:0,2"]
CANNON_A_PLACES = ["ultraCalgar:2,0", "worldKharn:3,0", "tyranTyrantGuard:2,1"]


def case_cannon():
    from engine.runner.abilities.tyranids import StranglethornCannonAbility

    sid, rid = build(CANNON_P, CANNON_A, places=CANNON_PLACES, a_places=CANNON_A_PLACES)
    try:
        dec, ob, snap, bg, rngd = capture(sid, rid)
        boss = _boss_id(dec)
        bv = _by_visual(dec)
        target = bv.get("ultraCalgar")
        pos = {u["id"]: (u["pos"]["col"], u["pos"]["row"]) for u in (dec.get("units") or [])}
        dist = {uid: hexgeo.distance(pos[target], p) for uid, p in pos.items()}
        roles = {"caster": boss, "target": target,
                 "ally_in_ring": bv.get("ultraTitus"), "ally_out_of_ring": bv.get("templChampion"),
                 "enemy_in_ring_1": bv.get("worldKharn"),
                 "enemy_in_ring_2": bv.get("tyranTyrantGuard")}
        st = offline_state(sid, dec, ob, snap, bg, rngd)
        port = StranglethornCannonAbility().execute_behaviour(st, boss, target) or {}
        # VUE ROUGE -- le port dont la NATURE du coup est declaree `Ranged` (`is_melee=False`) au lieu
        # d'ABSENTE (`None`). C'est l'erreur que ce port a REELLEMENT commise, et elle etait invisible
        # hors de ce montage : elle arme le gate `IsRangedAttack` de `BigTarget_AdjacentEffect`
        # (`CreateEffectHitsBonusForAttack` = `Direct(-1)` cappe a `Direct(1)`, sous
        # `get_OwnerIsTarget & IsRangedAttack`), donc -1 coup sur la cible adjacente a un `BigTarget`
        # allie. Sans ce bras, l'accord du bras vert ne dirait pas que c'est CE terme qui le produit.
        import engine.runner.abilities.tyranids as TY
        _true = TY.STRANGLETHORN_IS_MELEE
        st_red = offline_state(sid, dec, ob, snap, bg, rngd)
        try:
            TY.STRANGLETHORN_IS_MELEE = False
            port_ranged = StranglethornCannonAbility().execute_behaviour(st_red, boss, target) or {}
        finally:
            TY.STRANGLETHORN_IS_MELEE = _true
        res = PR.cast(sid, rid, boss, target, STRANGLETHORN)
        hits = live_hits(res.get("events"), STRANGLETHORN)
        # Le noeud `InformWeapon` : le natif emet un event `Info` porteur du profil et du regime
        # d'arme AVANT le premier coup. Le port ne le materialise pas -- residu #890-r1.
        inform = [tags(e) for e in (res.get("events") or [])
                  if "Attack_Weapon_DamageProfile" in tags(e)]
        return {"roles": roles, "pos": pos, "dist_to_target": dist, "hits": hits,
                "inform": inform, "port": _port_hits(port), "port_ranged": _port_hits(port_ranged),
                "attack_range_type": attack_range_type("StranglethornCannon"),
                "ok_apply": res.get("ok"), "mutated": res.get("mutated")}
    finally:
        # Le cache `unitAbilityStates` est cle par LABEL DE RUNNER, et un id de runner peut etre
        # RECYCLE par un build ulterieur -> on purge en meme temps qu'on dispose.
        clear_ability_states_cache(runner_label({"runner": "build#%s" % rid}))
        clear_ability_states_cache()
        PR.dispose(sid, rid)


# --------------------------------------------------------------------------- main

CASES = {"feet": case_feet, "catalyst": case_catalyst, "cannon": case_cannon}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", choices=sorted(CASES), required=True)
    a = ap.parse_args()
    out = CASES[a.case]()
    print(json.dumps(out, indent=1, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
