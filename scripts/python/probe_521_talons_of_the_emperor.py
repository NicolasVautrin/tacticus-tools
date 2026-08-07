#!/usr/bin/env python
"""probe_521_talons_of_the_emperor -- CONFRONTATION LIVE du port COMBAT de `1195 TalonsOfTheEmperor`
(`custoAtlacoya` << Atlacoya >>, Adeptus Custodes / Sisters of Silence).

QUESTION BINAIRE. Le port rend-il, COUP PAR COUP, PROFIL PAR PROFIL et TIRAGE PAR TIRAGE, ce que
rend le natif -- dans les DEUX branches du `If` et dans au moins DEUX regimes du compteur ? Sans les
deux, aucune des deux ne prouve rien : a compteur 0 un port qui IGNORERAIT `GetExtraDamage` serait
bit-exact, et sur une seule branche un port qui figerait le profil le serait aussi.

MECANIQUE (decompile = verite, build `rnca9r7q6c`).

    IdunBattleLogic.Entities.Abilities.Active.Loki.TalonsOfTheEmperorAbility$$ExecuteBehaviour
        dmg  = Sum( MinMaxDamage(this, abilityState, 0), GetExtraDamage(this, abilityState) )
        atk1 = AttackWithAttackDamage( Caster@0x48, Target@0x60, dmg,
                                       Direct(GetDamageProfile())  = Power,
                                       Direct(GetHits()) = nrOfHits, AbilityOrEffect(this) )
        atk2 = <idem, Direct(GetDamageProfile2()) = DirectDamage>
        Execute( If(MeetSecondDamageProfileRequirement(), atk2, atk1) )

    ...TalonsOfTheEmperorAbility$$MeetSecondDamageProfileRequirement
        HasTrait(Target@0x60, 0x3ea = Psyker)
        | HasFaction( NonSteppableOrObjectUnits(AdjacentFriends(Caster@0x48, CasterTile@0x50, 1), 3),
                      0x12 = Custodes, 3 )

    ...TalonsOfTheEmperorAbility$$GetExtraDamage
        Multiply( ConfigVar(8 = extraDmg),
                  If( HasEffect(Caster@0x48, 0x58c = 1420, activeOnly = 0, sourceFlags = 6),
                      EffectLevel(EffectFromOwner(Caster@0x48, 0x58c)),
                      DSLFormulas@+0x18 = Direct(0) ) )

CE QUE MESURE LE MONTAGE, par cast :

  * `compteur`  -- le niveau LIVE de l'effet 1420 sur le caster (`decisionView.units[].effects`),
                   la verite du natif, jamais un derive ;
  * E1 SEQUENCE coup par coup, NATIF (`UnitDamaged` filtre sur `Active_Ability_Type = 1195`) contre
       PORT (`per_hit_health` de la feuille) -- un total juste ne prouve rien ;
  * E2 PROFIL DE DEGAT natif (`DamageProfileType` du meme evenement : 14 = Power, 15 = DirectDamage)
       contre la branche prise par le port -- c'est l'etage `If` lui-meme ;
  * E3 TIRAGES `genrand_int32` (`dumpRng` avant/apres contre l'etat MT du port) -- l'etage qui separe
       une faute d'ARITHMETIQUE d'une faute de STRUCTURE ;
  * E4 les CONTRE-EPREUVES hors-ligne, chacune ne retirant QU'UNE lecture du mirror.

UN CAST PAR RUNNER, ET C'EST UNE MESURE, PAS UN CHOIX. Le kit 1195 ne porte AUCUN `cooldownTurns`
(contraste `MartialInspiration`, qui porte `cooldownTurns = 2`) : mesure du 2026-08-07 sur le
runner, apres le premier cast le champ `CanUse` de l'`ActiveAbility` reste **false** pour toute la
bataille (`usable: false`, `unresetedLastTurnUsed: 0`, `cooldown: null`), a travers 10 cycles de
tour complets. 1195 est donc UNE FOIS PAR BATAILLE, et le compteur ne peut pas se balayer en
rejouant l'ability : chaque point de mesure est un BUILD.

LES SIX REGIMES, et pourquoi chacun existe (armure NON nulle PARTOUT : `Power` perce 40 %,
`DirectDamage` 100 % -- a armure 0 les deux branches rendraient le MEME degat et l'etage `If` ne
serait pas mesure) :

  * `power`     -- cible non-Psyker, AUCUN ami adjacent au caster  -> branche `else`, profil Power,
                   compteur 1420 = 0.
  * `power_n1`  -- MEME geometrie, mais un allie LOIN (`custoTrajann`) caste d'abord son self-cast
                   `1184 MomentShackle` : la triggered 1330 fait alors passer le compteur a 1. C'est
                   le SECOND regime de compteur, sans lequel `sans_extra` ne peut rien discriminer.
  * `psyker`    -- cible `astraPrimarisPsy` (trait Psyker)          -> branche `then` par HasTrait.
  * `custodes`  -- cible non-Psyker, UN ami `custoKyrus` (Custodes) adjacent au caster et a LUI SEUL
                   -> branche `then` par HasFaction.
  * `mixte`     -- DEUX amis adjacents : `darkaCompanion` (DarkAngels) sur (5,7) et `custoKyrus`
                   (Custodes) sur (4,8). L'ordre d'adjacence STOCKE de la tuile (5,8) est
                   [(6,8), (6,7), (5,7), (4,7), (4,8)] -> le PREMIER ami rendu est le NON-Custodes.
  * `mixte_inv` -- le MEME couple, positions ECHANGEES -> le premier ami rendu est le Custodes.

`mixte` + `mixte_inv` TRANCHENT la semantique du selecteur d'`HasFaction` (#521-r2), et les trois
hypotheses sont separees par construction :
    any (le noeud porte)      -> Direct  dans les DEUX
    SelectSingle = premier    -> Power   dans `mixte`, Direct dans `mixte_inv`
    SelectSingle = 0-ou-1     -> Power   dans les DEUX

Aucune valeur attendue codee en dur : l'oracle est le natif qui tourne.

Usage (depuis scripts/python, session Frida chaude) :
    python probe_521_talons_of_the_emperor.py [--seed 52101] [--board MC1_67]
                                              [--regimes power,psyker,custodes,mixte,mixte_inv]

ASCII only (cp1252). Dispose SES runners (jamais ceux des autres).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

PYDIR = str(Path(__file__).resolve().parent)
sys.path.insert(0, PYDIR)

HOST = os.environ.get("TACTICUS_HOST", "http://127.0.0.1:8765")

TALONS = 1195
TALONS_USED_ABILITIES = 1420          # EffectType.TalonsOfTheEmperor_UsedAbilities (0x58c)
CASTER = "custoAtlacoya"              # Atlacoya -- SEUL porteur de 1195, LINEUP, dans le pool rank 17
FOE = "necroWarden"                   # cible NON-Psyker
FOE_PSYKER = "astraPrimarisPsy"       # cible Psyker (traits ['Hero', 'Psyker'])
FOE_FILLER = "necroOverlord"          # 2e a-unit : la bataille ne finit pas si la cible tombe
ALLY_CUSTODES = "custoKyrus"          # ami de FACTION Custodes (traits Hero/MartialKatah/Resilient)
ALLY_OTHER = "darkaCompanion"         # ami NON-Custodes (DarkAngels ; passifs self-only)
ALLY_CASTER = "custoTrajann"          # Character allie qui INCREMENTE le compteur 1420 (cf. `pre`)
P_FILLER = "astraDreir"               # FIGURANT du camp joueur, place LOIN (cf. ci-dessous)
#: `1184 MomentShackle` -- SELF-CAST (`TargetingOptions.isSelfCasting = 1`), donc castable sans
#: geometrie ni cible ennemie, et son observable (heal + 2 stat-mods + marqueur) reste SUR Trajann,
#: place LOIN du caster. C'est ce qui en fait le levier propre du compteur.
MOMENT_SHACKLE = 1184
BOARD = "MC1_67"
RANK = 17

#: GEOMETRIE, LUE dans `boardGraph` du board MC1_67 (toutes ces tuiles sont a ELEVATION 1 -> aucun
#: bonus d'elevation ne pollue la mesure) :
#:   (5,8) voisins STOCKES = [(6,8), (6,7), (5,7), (4,7), (4,8)]      <- l'ordre d'`AdjacentTiles`
#:   (6,8) voisins STOCKES = [(6,7), (5,8)]                            <- la cible n'a que 2 voisins
PLACE_CASTER = "5,8"
PLACE_ALLY_A = "5,7"      # adjacent au CASTER, PAS a la cible ; 3e dans l'ordre d'adjacence
PLACE_ALLY_B = "4,8"      # adjacent au CASTER, PAS a la cible ; 5e dans l'ordre d'adjacence
PLACE_FILLER = "1,7"      # LOIN du caster : jamais dans `AdjacentFriends`
PLACE_FILLER_2 = "0,7"    # 2e figurant LOIN (regime `power_n1`, ou le 1er a deja agi)
A_PLACE_FOE = "6,8"       # adjacent au caster
A_PLACE_FILLER = "6,7"    # ENNEMI adjacent au caster -> `Friends` l'ecarte (temoin du filtre equipe)

HP_FOE = 300000           # la cible ne meurt jamais : la fenetre de mesure reste ouverte
ARMURE = 2000             # armure NON nulle PARTOUT : c'est ce qui rend `Power` != `DirectDamage`

#: `IdunBattle.Entities.Enum.DamageProfileType` (table de symboles du build) -- les DEUX profils du
#: kit 1195. Ecrits par leur NOM d'enum au site, jamais l'ordinal nu.
DP_POWER = 14
DP_DIRECT_DAMAGE = 15

#: `UnitDamaged` natif : la SEQUENCE coup par coup (cible, montant, profil), pas un total.
RE_DMG = re.compile(
    r"UnitDamaged e=(\d+).*?Attacker_Id=(\d+) Target_Id=(\d+) Amount=(-?\d+) "
    r"DamageProfileType=(\d+) Active_Ability_Type=(\d+)")
#: TOUS les coups portes pendant l'appel `act` -- sert a ATTRIBUER les tirages.
RE_HIT = re.compile(r"UnitDamaged e=(\d+)\s+UnitStats_RemainingHealth=(-?\d+)")
#: Tirages `genrand_int32` par coup de la famille ATTACK a `critChance = 0`.
TIRAGES_PAR_COUP = 2

#: Chaque regime : `p` = unites joueur (visualId, tuile), `a` = unites adverses, `pre` = les casts
#: d'ALLIE joues AVANT celui d'Atlacoya (visualId, abilityId) -- le levier du compteur 1420.
#: L'ORDRE des `--p-units` ne compte pas ; les TUILES, si (cf. `mixte` / `mixte_inv`).
REGIMES = {
    "power":     {"p": [(CASTER, PLACE_CASTER), (P_FILLER, PLACE_FILLER)],
                  "a": [(FOE, A_PLACE_FOE), (FOE_FILLER, A_PLACE_FILLER)], "pre": []},
    "power_n1":  {"p": [(CASTER, PLACE_CASTER), (ALLY_CASTER, PLACE_FILLER),
                        (P_FILLER, PLACE_FILLER_2)],
                  "a": [(FOE, A_PLACE_FOE), (FOE_FILLER, A_PLACE_FILLER)],
                  "pre": [(ALLY_CASTER, MOMENT_SHACKLE)]},
    "psyker":    {"p": [(CASTER, PLACE_CASTER), (P_FILLER, PLACE_FILLER)],
                  "a": [(FOE_PSYKER, A_PLACE_FOE), (FOE_FILLER, A_PLACE_FILLER)], "pre": []},
    "custodes":  {"p": [(CASTER, PLACE_CASTER), (ALLY_CUSTODES, PLACE_ALLY_B),
                        (P_FILLER, PLACE_FILLER)],
                  "a": [(FOE, A_PLACE_FOE), (FOE_FILLER, A_PLACE_FILLER)], "pre": []},
    "mixte":     {"p": [(CASTER, PLACE_CASTER), (ALLY_OTHER, PLACE_ALLY_A),
                        (ALLY_CUSTODES, PLACE_ALLY_B), (P_FILLER, PLACE_FILLER)],
                  "a": [(FOE, A_PLACE_FOE), (FOE_FILLER, A_PLACE_FILLER)], "pre": []},
    "mixte_inv": {"p": [(CASTER, PLACE_CASTER), (ALLY_CUSTODES, PLACE_ALLY_A),
                        (ALLY_OTHER, PLACE_ALLY_B), (P_FILLER, PLACE_FILLER)],
                  "a": [(FOE, A_PLACE_FOE), (FOE_FILLER, A_PLACE_FILLER)], "pre": []},
}
#: Profil ATTENDU par la LECTURE du decompile, regime par regime -- ce n'est PAS l'oracle (l'oracle
#: est le natif) : c'est ce que le rapport confronte pour dire QUEL etage a bouge.
PROFIL_LU = {"power": DP_POWER, "power_n1": DP_POWER, "psyker": DP_DIRECT_DAMAGE,
             "custodes": DP_DIRECT_DAMAGE,
             "mixte": None, "mixte_inv": None}      # None = c'est justement ce qu'on MESURE (#521-r2)
#: Compteur 1420 ATTENDU au moment du cast, regime par regime (`None` = non prescrit).
COMPTEUR_LU = {"power": 0, "power_n1": 1, "psyker": 0, "custodes": 0, "mixte": 0, "mixte_inv": 0}


# ------------------------------------------------------------------ transport

def _sid():
    with urllib.request.urlopen(HOST + "/api/admin/status", timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))["session"]["id"]


def _rpc(sid, method, body=None, timeout=180):
    payload = json.dumps({"method": method,
                          "args": [body] if body is not None else []}).encode("utf-8")
    req = urllib.request.Request("%s/api/scripts/%s/rpc" % (HOST, sid), data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read().decode("utf-8"))
    return out.get("result") if isinstance(out, dict) and "result" in out else out


def _duel(args, timeout=400):
    return subprocess.run([sys.executable, "rl_duel.py"] + args, cwd=PYDIR,
                          capture_output=True, text=True, timeout=timeout,
                          encoding="utf-8", errors="replace")


# ------------------------------------------------------------------ montage

def build(state_file: str, seed: int, board: str, regime: str):
    spec = REGIMES[regime]
    argv = ["build", "--seed", str(seed), "--board", board, "--rank", str(RANK),
            "--p-units", ",".join(v for v, _t in spec["p"]),
            "--a-units", ",".join(v for v, _t in spec["a"]),
            "--crit", "0,0", "--block-target", "0,0",
            "--armor-target", str(ARMURE),
            "--state-file", state_file]
    for vid, tile in spec["p"]:
        argv += ["--place", "%s:%s" % (vid, tile)]
    for vid, tile in spec["a"]:
        argv += ["--a-place", "%s:%s" % (vid, tile)]
        # ⚠ PAS `--hp-target` : il met AUSSI Armor/FixedArmor a 0, ce qui rendrait les deux branches
        # du `If` NUMERIQUEMENT identiques -- le regime ne mesurerait alors plus rien.
        argv += ["--unit-stat", "%s:Health=%d,RemainingHealth=%d" % (vid, HP_FOE, HP_FOE)]
    p = _duel(argv)
    if p.returncode != 0 or not os.path.exists(state_file):
        print("[build %s] rc=%s\n%s\n%s" % (regime, p.returncode, (p.stdout or "")[-2000:],
                                            (p.stderr or "")[-800:]))
        return None
    with open(state_file, "r", encoding="utf-8") as f:
        return int(json.load(f)["runnerId"])


def unites(sid, rid):
    dv = _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 180)
    out = {}
    for u in (dv.get("units") or []):
        p = u.get("pos") or {}
        out[u.get("visualId")] = {"id": u.get("id"), "pos": (p.get("col"), p.get("row")),
                                  "hp": u.get("hp"), "owner": u.get("owner"),
                                  "abilities": u.get("abilities") or [],
                                  "effects": u.get("effects") or []}
    return out, dv


def assert_montage(u, regime):
    """Un montage DEGENERE rendrait l'accord trivial : on echoue AVANT de mesurer, jamais apres."""
    spec = REGIMES[regime]
    voulu = {v: t for v, t in (spec["p"] + spec["a"])}
    manquants = [v for v in voulu if v not in u]
    if manquants:
        raise SystemExit("montage %s invalide : unites absentes %r" % (regime, manquants))
    mauvais = [(v, u[v]["pos"], voulu[v]) for v in voulu
               if u[v]["pos"] != tuple(int(x) for x in voulu[v].split(","))]
    if mauvais:
        raise SystemExit("placement REFUSE -- montage %s invalide, pas de mesure : %r"
                         % (regime, mauvais))
    cible = spec["a"][0][0]
    if int(u[cible]["hp"] or 0) < 1000:
        raise SystemExit("cible trop fragile (%s PV) : elle mourrait avant la 2e mesure"
                         % u[cible]["hp"])


def _ability_entry(u, aid):
    return next((a for a in u["abilities"] if a.get("id") == aid), None)


def _normal_id(u):
    """Id CONCRET de l'attaque normale (`kind == "normal"`), per-unite -- jamais le 17 generique."""
    return next((a.get("id") for a in u["abilities"] if a.get("kind") == "normal"), None)


def _compteur_live(u, visual_id=CASTER):
    """Niveau LIVE de l'effet 1420 sur le caster, lu dans `decisionView.units[].effects` -- le MEME
    canal que celui dont `snapshot.load_state` seede `EffectsState`. Effet absent -> 0 (le natif,
    lui, prend la branche `Direct(0)` du `If`). None si le canal n'a rien rendu du tout."""
    effs = (u.get(visual_id) or {}).get("effects")
    if effs is None:
        return None
    total = 0
    for e in effs:
        et = e.get("effectType", e.get("effect_type"))
        if et is not None and int(et) == TALONS_USED_ABILITIES:
            total += int(e.get("level") or 0)
    return total


def capture(sid, rid):
    """L'etat COMPLET juste avant le cast natif -- le substrat du rejeu porte."""
    return {
        "dv": _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 180),
        "ob": _rpc(sid, "observeBattle", {"runnerId": rid}, 90),
        "snap": _rpc(sid, "combatSnapshot", {"runnerId": rid}, 120),
        "tm": _rpc(sid, "tileMeta", {"runnerId": rid}, 120),
        "tiles": _rpc(sid, "boardGraph", {"runnerId": rid}, 90)["tiles"],
        "stats": _rpc(sid, "actorStats", {"runnerId": rid}, 60),
        "rng": _rpc(sid, "dumpRng", {"runnerId": rid}, 60),
    }


# ------------------------------------------------------------------ rejeu hors-ligne

def etat_porte(cap):
    """`State` charge depuis la capture, PRNG cale sur `dumpRng`.

    Sans le calage MT, `execute_ability_attack` SKIPPE le degat par repli defensif : on lirait un
    faux `0`."""
    from engine.entities.pathfinding.board import Board
    from engine.runner.prng import IntBasedMersenneTwister
    from engine.runner.snapshot import load_state
    board = Board(cap["tiles"], adjacency="native_sym")
    st = load_state(cap["dv"], cap["ob"], cap["snap"], board=board, tiles=cap["tm"],
                    actor_stats=cap["stats"])
    d = cap["rng"]
    if not (isinstance(d, dict) and d.get("mt")):
        raise SystemExit("dumpRng VIDE -- MT non calable, aucune mesure de degat n'a de sens")
    rng = IntBasedMersenneTwister()
    rng.mt, rng.mti = list(d["mt"]), d["mti"]
    st.rng = rng
    return st


def rejeu_porte(cap, caster_id, target_id):
    """Rejoue le cast par le CHEMIN COMPLET du moteur (`Runner.apply(ActiveAbilityMessage)`), pas
    par un appel direct a `execute_behaviour` : c'est ce qui exerce le registre `ABILITY_CLASSES` et
    rend `ability_handler.last['ported']` -- l'observable qui distingue le port du NO-OP."""
    from engine.runner.messages import ActiveAbilityMessage
    from engine.runner.runner import Runner
    st = etat_porte(cap)
    runner = Runner(st).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=int(caster_id), target_id=int(target_id),
                                      ability_type=TALONS))
    last = getattr(runner.ability_handler, "last", None) or {}
    seq = [(int(a.get("target")), int(m)) for a in (last.get("attacks") or [])
           for m in ((a.get("attack") or {}).get("per_hit_health") or [])]
    return {
        "ported": last.get("ported"),
        "second_profile": last.get("second_profile"),
        "profil": (DP_DIRECT_DAMAGE if last.get("second_profile") else DP_POWER),
        "compteur": last.get("used_abilities_level"),
        "extra": last.get("extra_damage"),
        "seq": seq,
        "total": sum(m for _t, m in seq),
        "mt": (list(st.rng.mt), st.rng.mti),
    }


def _rejeu_arbre(cap, caster_id, target_id, arbre_fn):
    """Rejoue le MEME cast avec un arbre SUBSTITUE, sur la MEME capture (donc le meme MT)."""
    from engine.dsl.effects import ExecutionContext
    from engine.runner.abilities.behaviours.context import entities_from_state
    st = etat_porte(cap)
    ectx = ExecutionContext(state=st, rng=st.rng)
    entities = entities_from_state(st, int(caster_id), int(target_id))
    arbre_fn(st, entities).execute(entities, ectx)
    seq = [(int(p.get("target")), int(m))
           for n, p in ectx.emitted if n == "AttackWithAttackDamage"
           for m in ((p.get("attack") or {}).get("per_hit_health") or [])]
    return {"seq": seq, "total": sum(m for _t, m in seq),
            "tirages": tirages(cap["rng"], list(st.rng.mt), st.rng.mti)}


def contre_epreuves(cap, caster_id, target_id):
    """Chaque variante ne change QU'UNE lecture du mirror. Si l'une rendait le MEME resultat que la
    REFERENCE, la lecture correspondante ne serait PAS mesuree par ce montage -- et l'accord du port
    avec le natif serait un accord de hasard.

      * `sans_extra`        -- retire `Sum(MinMaxDamage, GetExtraDamage)` : doit diverger des que le
                               compteur 1420 est > 0 (et SEULEMENT alors) ;
      * `profil_fixe_power` -- fige la branche `else` : doit diverger quand le natif rend Direct ;
      * `profil_fixe_direct`-- fige la branche `then` : doit diverger quand le natif rend Power ;
      * `psyker_seul`       -- ampute le `op_BitwiseOr` de son volet FACTION ;
      * `faction_seule`     -- ampute le `op_BitwiseOr` de son volet TRAIT.
    """
    from engine.entities.behaviours import If
    from engine.entities.formulas import Get, If as AmountIf, Multiply
    from engine.entities.selectors.accessors import Target
    from engine.entities.selectors.tiles import Caster
    from engine.entities.triggers import HasEffect, HasFaction, HasTrait
    from engine.runner.abilities.behaviours.combat import AttackWithAttackDamage
    from engine.entities.active_ability_type import ActiveAbilityType
    from engine.entities.selectors.units import non_steppable_or_object_units
    from engine.entities.effects.magnitude import ability_var
    from engine.runner.components import StatsComponent
    import engine.runner.abilities.custodes as CU
    import gameconfig as GC

    consts = (GC.ability(CU.TALONS_OF_THE_EMPEROR_ID) or {}).get("constants") or {}
    prof, prof2 = consts.get("damageProfile"), consts.get("damageProfile_2")

    def _override(st, entities):
        e = st.get_entity(int(caster_id))
        sc = e.get_component(StatsComponent) if e is not None else None
        cctx = sc.ctx if sc is not None else None
        lvl = getattr(cctx, "active_ability_level", None)
        mult = int(getattr(cctx, "ability_variables_multiplier", 100) or 100)
        per = int(ability_var(CU.TALONS_OF_THE_EMPEROR_ID, "extraDmg", lvl,
                              multiplier_pct=mult) or 0)
        used = CU.talons_used_abilities_level(st, int(caster_id))
        node = Multiply(Get(per),
                        AmountIf(HasEffect(Caster(), CU.TOTE_USED_ABILITIES, active_only=False),
                                 Get(used), Get(0)))

        def _f(_st, _c, _t, bmin, bmax):
            flat = int(node.evaluate(entities))
            return bmin + flat, bmax + flat
        return _f

    def _atk(prof_name, ov):
        return AttackWithAttackDamage(
            Target(), CU.TALONS_OF_THE_EMPEROR_ID, prof_name, is_melee=True,
            damage_override=ov, native_factory="attack",
            ability_type=int(ActiveAbilityType.TalonsOfTheEmperor))

    variantes = {
        "ref": lambda st, en: CU.talons_of_the_emperor_tree(prof, prof2, _override(st, en)),
        "sans_extra": lambda st, en: CU.talons_of_the_emperor_tree(prof, prof2, None),
        "profil_fixe_power": lambda st, en: _atk(prof, _override(st, en)),
        "profil_fixe_direct": lambda st, en: _atk(prof2, _override(st, en)),
        "psyker_seul": lambda st, en: If(
            HasTrait(Target(), CU.TOTE_PSYKER_TRAIT),
            _atk(prof2, _override(st, en)), _atk(prof, _override(st, en))),
        "faction_seule": lambda st, en: If(
            HasFaction(non_steppable_or_object_units(CU.talons_adjacent_friends()),
                       CU.TOTE_CUSTODES_FACTION),
            _atk(prof2, _override(st, en)), _atk(prof, _override(st, en))),
    }
    return {k: _rejeu_arbre(cap, caster_id, target_id, v) for k, v in variantes.items()}


def tirages(rng_initial, mt_cible, mti_cible, cap=600):
    """Nombre de `genrand_int32` consommes pour aller de l'etat INITIAL a l'etat CIBLE. Deux moteurs
    qui rendent des montants differents mais consomment le MEME nombre de tirages ont un bug
    d'ARITHMETIQUE ; sinon c'est la STRUCTURE. Rend None si non atteint."""
    from engine.runner.prng import IntBasedMersenneTwister
    r = IntBasedMersenneTwister()
    r.mt, r.mti = list(rng_initial["mt"]), rng_initial["mti"]
    for n in range(cap + 1):
        if r.mti == mti_cible and r.mt == mt_cible:
            return n
        r.genrand_int32()
    return None


# ------------------------------------------------------------------ pilotage

def _endturn(sid, rid):
    return _rpc(sid, "applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 90)


def _rendre_la_main(sid, rid, me, max_steps=8):
    """Rend la main a MON camp sans faire jouer l'IA (`endturn` seulement : geometrie figee)."""
    for _ in range(max_steps):
        _endturn(sid, rid)
        dv = _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 180)
        if dv.get("currentPlayer") == me:
            return dv
    return _rpc(sid, "decisionView", {"runnerId": rid, "allAbilities": True}, 180)


def _cast(state_file, rid, cid, tid, aid):
    return _duel(["act", "ability", "--caster", str(cid), "--ability", str(aid),
                  "--target", str(tid), "--state-file", state_file, "--runner", str(rid)])


def mesure(sid, state_file, seed, board, regime, garder=False):
    """UN build, les casts `pre` de la sequence, puis LE cast de 1195 (once-per-battle, cf. l'en-tete).

    Le montage ECHOUE s'il n'obtient pas son regime -- il ne rend pas un vert de regime degenere."""
    rid = build(state_file, seed, board, regime)
    if rid is None:
        return None
    spec = REGIMES[regime]
    try:
        u, dv = unites(sid, rid)
        assert_montage(u, regime)
        cid, tid = u[CASTER]["id"], u[spec["a"][0][0]]["id"]
        me = u[CASTER]["owner"]
        if dv.get("currentPlayer") != me:
            _rendre_la_main(sid, rid, me)
            u, dv = unites(sid, rid)
        pre = []
        for vid, aid in spec.get("pre") or []:
            # SELF-CAST : `--target` = le caster lui-meme (`isSelfCasting = 1`).
            r = _cast(state_file, rid, u[vid]["id"], u[vid]["id"], aid)
            u, dv = unites(sid, rid)
            pre.append({"unit": vid, "ability": aid, "rc": r.returncode,
                        "compteur_apres": _compteur_live(u),
                        "out": (r.stdout or "")[-600:] + (r.stderr or "")[-300:]})
            if r.returncode != 0:
                raise SystemExit("cast PREALABLE %s/%s en echec (rc=%s) -- regime %s non atteint"
                                 % (vid, aid, r.returncode, regime))
        ent = _ability_entry(u[CASTER], TALONS)
        if not (ent and ent.get("usable") and not ent.get("disabled") and not ent.get("cooldown")):
            raise SystemExit("1195 NON castable sur %s au moment voulu : %r -- montage %s sterile"
                             % (CASTER, ent, regime))
        cnt = _compteur_live(u)
        cap = capture(sid, rid)
        port = rejeu_porte(cap, cid, tid)
        ab = contre_epreuves(cap, cid, tid)
        p = _cast(state_file, rid, cid, tid, TALONS)
        seq_n = [(int(t), int(a), int(pr))
                 for _e, at, t, a, pr, ab_id in RE_DMG.findall(p.stdout or "")
                 if int(ab_id) == TALONS and int(at) == int(cid)]
        coups_tous = RE_HIT.findall(p.stdout or "")
        rng_apres = _rpc(sid, "dumpRng", {"runnerId": rid}, 60)
        u2, _dv2 = unites(sid, rid)
        cast = {
            "compteur_live": cnt,
            "compteur_live_apres": _compteur_live(u2),
            "port": port, "ab": ab,
            "natif": {"seq": [(t, a) for t, a, _pr in seq_n],
                      "profils": sorted({pr for _t, _a, pr in seq_n}),
                      "total": sum(a for _t, a, _pr in seq_n),
                      "coups_tous": len(coups_tous),
                      "cibles_tous": sorted({int(e) for e, _hp in coups_tous}),
                      "rc": p.returncode,
                      "out": (p.stdout or "")[-1500:] + (p.stderr or "")[-500:]},
            "tirages_natif": (tirages(cap["rng"], rng_apres.get("mt"), rng_apres.get("mti"))
                              if isinstance(rng_apres, dict) and rng_apres.get("mt") else None),
            "tirages_port": tirages(cap["rng"], port["mt"][0], port["mt"][1]),
        }
        return {"regime": regime, "rid": rid, "caster": cid, "cible": tid, "pre": pre,
                "casts": [cast], "hp_cible": u[spec["a"][0][0]]["hp"]}
    finally:
        if not garder:
            _duel(["dispose", "--state-file", state_file, "--runner", str(rid)], timeout=120)


# ------------------------------------------------------------------ rapport

#: Quelles contre-epreuves DOIVENT diverger, selon ce que le natif a rendu. Une contre-epreuve non
#: discriminante = une lecture du mirror que CE regime ne mesure pas -> l'accord y serait fortuit.
def _attendues_divergentes(profil_natif, compteur):
    out = []
    if compteur:
        out.append("sans_extra")
    if profil_natif == DP_DIRECT_DAMAGE:
        out.append("profil_fixe_power")
    elif profil_natif == DP_POWER:
        out.append("profil_fixe_direct")
    return out


def rapport(m) -> bool:
    print("[521:%s] runner=%s caster=u%s cible=u%s (PV %s)"
          % (m["regime"], m["rid"], m["caster"], m["cible"], m["hp_cible"]))
    for pc in (m.get("pre") or []):
        print("  pre-cast %s / ability %s : rc=%s -> compteur 1420 = %s"
              % (pc["unit"], pc["ability"], pc["rc"], pc["compteur_apres"]))
    if not m["casts"]:
        print("  AUCUN cast mesure -- montage sterile, verdict IMPOSSIBLE")
        return False
    ok = True
    for c in m["casts"]:
        n = c["compteur_live"]
        sp, sn = c["port"]["seq"], c["natif"]["seq"]
        pn = c["natif"]["profils"][0] if len(c["natif"]["profils"]) == 1 else None
        print("  -- cast avec EffectLevel(1420) = %s (apres = %s) --"
              % (n, c["compteur_live_apres"]))
        print("     E1 SEQUENCE  PORT (%d coups) = %s" % (len(sp), [a for _t, a in sp]))
        print("                  NATIF(%d coups) = %s" % (len(sn), [a for _t, a in sn]))
        print("     E2 PROFIL    PORT = %s (second_profile=%s)   NATIF = %s"
              % (c["port"]["profil"], c["port"]["second_profile"], c["natif"]["profils"]))
        print("     E1 total     PORT=%s  NATIF=%s   (ported=%s, compteur port=%s, extra=%s, rc=%s)"
              % (c["port"]["total"], c["natif"]["total"], c["port"]["ported"],
                 c["port"]["compteur"], c["port"]["extra"], c["natif"]["rc"]))
        att = TIRAGES_PAR_COUP * c["natif"]["coups_tous"]
        print("     E3 TIRAGES genrand_int32 : PORT=%s (= 2 x %d coups 1195)  NATIF=%s "
              "(2 x %d coups TOUS = %d attendu, cibles %s)"
              % (c["tirages_port"], len(sp), c["tirages_natif"], c["natif"]["coups_tous"], att,
                 c["natif"]["cibles_tous"]))
        print("     -- contre-epreuves (hors-ligne, MEME capture, MEME MT) --")
        ref = (c.get("ab") or {}).get("ref")
        for nom, r in (c.get("ab") or {}).items():
            marque = "== REF" if nom != "ref" and ref and r["seq"] == ref["seq"] else ""
            print("        %-20s total=%-8s tirages=%-4s %s" % (nom, r["total"], r["tirages"],
                                                                marque))
        if not sn:
            print("     !! aucun `UnitDamaged` natif attribue a 1195")
            ok = False
        if sp != sn:
            print("     !! SEQUENCE divergente")
            ok = False
        if pn is None:
            print("     !! le natif rend %d profils distincts -- non interpretable"
                  % len(c["natif"]["profils"]))
            ok = False
        elif pn != c["port"]["profil"]:
            print("     !! PROFIL divergent : port=%s natif=%s" % (c["port"]["profil"], pn))
            ok = False
        if n is not None and c["port"]["compteur"] != n:
            print("     !! le compteur SEEDE du port (%s) differe du LIVE (%s)"
                  % (c["port"]["compteur"], n))
            ok = False
        if c["tirages_port"] != TIRAGES_PAR_COUP * len(sp):
            print("     !! le port ne consomme pas 2 tirages par coup")
            ok = False
        if c["tirages_natif"] != att:
            print("     !! l'attribution des tirages natifs ne boucle pas (%s != %s)"
                  % (c["tirages_natif"], att))
            ok = False
        if ref and ref["seq"] != sn:
            print("     !! l'arbre du module ne rend pas la sequence native")
            ok = False
        for nom in _attendues_divergentes(pn, n):
            r = (c.get("ab") or {}).get(nom)
            if r and r["seq"] == sn:
                print("     !! contre-epreuve %s NON discriminante (== natif)" % nom)
                ok = False
    profils = sorted({p for c in m["casts"] for p in c["natif"]["profils"]})
    compteurs = sorted({c["compteur_live"] for c in m["casts"]})
    lu = PROFIL_LU.get(m["regime"])
    cl = COMPTEUR_LU.get(m["regime"])
    print("  PROFILS NATIFS ATTEINTS : %s%s   COMPTEURS : %s"
          % (profils, ("" if lu is None else "   (lecture du decompile : %s)" % lu), compteurs))
    if lu is not None and profils != [lu]:
        print("  !! le regime %s devait rendre le profil %s et rend %s -- la LECTURE du decompile "
              "est contredite, ou le montage n'est pas celui qu'on croit" % (m["regime"], lu, profils))
        ok = False
    if cl is not None and compteurs != [cl]:
        print("  !! le regime %s devait mesurer au compteur %s et mesure %s -- le montage n'a pas "
              "atteint son regime" % (m["regime"], cl, compteurs))
        ok = False
    return ok


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Confrontation live du port COMBAT de 1195")
    ap.add_argument("--seed", type=int, default=52101)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--regimes", default="power,power_n1,psyker,custodes,mixte,mixte_inv")
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--garder", action="store_true")
    a = ap.parse_args(argv)

    import gameconfig as GC
    from engine.entities.effects.magnitude import ability_var
    consts = (GC.ability("TalonsOfTheEmperor") or {}).get("constants") or {}
    print("config TalonsOfTheEmperor : nrOfHits=%s damageProfile=%s damageProfile_2=%s "
          "extraDmg[lvl 50]=%s"
          % (consts.get("nrOfHits"), consts.get("damageProfile"), consts.get("damageProfile_2"),
             int(ability_var("TalonsOfTheEmperor", "extraDmg", 50) or 0)))

    sid = _sid()
    base_sf = a.state_file or str(Path(PYDIR).parents[1] / "logs"
                                  / ("probe521_%d.json" % os.getpid()))
    tout_ok = True
    resultats = {}
    for regime in [r.strip() for r in a.regimes.split(",") if r.strip()]:
        sf = base_sf.replace(".json", "_%s.json" % regime)
        m = mesure(sid, sf, a.seed, a.board, regime, garder=a.garder)
        if m is None:
            print("[521:%s] BUILD KO" % regime)
            tout_ok = False
            continue
        resultats[regime] = m
        tout_ok = rapport(m) and tout_ok
    verdict_mixte(resultats)
    print("[521] VERDICT : %s" % ("OK" if tout_ok else "DIVERGENCE"))
    return 0 if tout_ok else 1


def semantique_hasfaction(m_mixte, m_inv):
    """Verdict du residu `#521-r2` a partir des DEUX arrangements. Rend `None` si l'un des deux
    manque ou n'a rien mesure (une mesure incomplete ne rend JAMAIS de verdict)."""
    def _p(m):
        if not m or not m["casts"]:
            return None
        prof = sorted({p for c in m["casts"] for p in c["natif"]["profils"]})
        return prof[0] if len(prof) == 1 else None
    a, b = _p(m_mixte), _p(m_inv)
    if a is None or b is None:
        return None, (a, b)
    if a == DP_DIRECT_DAMAGE and b == DP_DIRECT_DAMAGE:
        return "any", (a, b)
    if a == DP_POWER and b == DP_DIRECT_DAMAGE:
        return "premier", (a, b)
    if a == DP_POWER and b == DP_POWER:
        return "zero_ou_un", (a, b)
    return "incoherent", (a, b)


def verdict_mixte(resultats):
    v, (a, b) = semantique_hasfaction(resultats.get("mixte"), resultats.get("mixte_inv"))
    if v is None:
        print("[521:#521-r2] NON TRANCHE -- profils mixte=%s mixte_inv=%s (mesure incomplete)"
              % (a, b))
        return
    libelle = {
        "any": "any(...) sur TOUT l'ensemble",
        "premier": "SelectSingle = PREMIER element de l'ensemble (mirror `TargetsSelector$$SelectFirst`)",
        "zero_ou_un": "SelectSingle = 0-ou-1 (plus d'un -> null -> FAUX)",
        "incoherent": "arrangements INCOHERENTS -- ni any, ni premier, ni 0-ou-1",
    }[v]
    print("[521:#521-r2] SEMANTIQUE NATIVE de HasFaction sur un ENSEMBLE : %s  "
          "(mixte=%s, mixte_inv=%s ; 14=Power 15=DirectDamage). Le noeud porte "
          "(`entities/triggers.py::HasFaction`) doit rendre LA MEME CHOSE -- c'est ce que "
          "verifient les deux `PROFIL` ci-dessus, pas cette ligne." % (libelle, a, b))


if __name__ == "__main__":
    raise SystemExit(main())
