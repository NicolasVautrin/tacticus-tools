#!/usr/bin/env python
"""probe_566_vexilla_magnifica -- CONFRONTATION LIVE du port COMBAT de `1183 VexillaMagnifica`
(`custoVexilusPraetor` << Aesoth >>, Adeptus Custodes).

QUESTION BINAIRE. Le port rend-il, COUP PAR COUP, TIRAGE PAR TIRAGE et EFFET PAR EFFET, ce que rend
le natif -- et **CHOISIT-IL LA MEME SECONDE CIBLE** quand le classement d'utilite bascule ?

Sans le second regime, le premier ne prouve rien : un port qui prendrait le PREMIER ennemi adjacent
de l'ordre source (au lieu de l'argmax d'utilite de degat) tomberait juste par hasard des que
l'argmax coincide avec la tete de l'enumeration.

MECANIQUE (decompile = verite, build `rnca9r7q6c`).

    IdunBattleLogic.Entities.Abilities.Active.Loki.VexillaMagnificaAbility$$ExecuteBehaviour
        dmg = AActiveAbility.MinMaxDamage(this, abilityState, isPrediction = 0)
            = DSLFormulas.RandomAmount(GetVariableForLevel(0xc = minDmg), (0xd = maxDmg))
        sec = Cache( First( SortUnitsByDamageUtility(
                                NormalUnits(AdjacentEnemies(Caster@0x48, 1, 3), 3)
                                op_Subtraction Target@0x60,
                                dmg, 3, null ), 1 ), 1 )
        b1  = AttackWithAttackDamage(Caster@0x48, Target@0x60, dmg, GetDamageProfile(), GetHits())
        b2  = AttackWithAttackDamage(Caster@0x48, sec,         dmg, GetDamageProfile(), GetHits())
        b3  = AddEffect(0x48a = 1162 Stunned, stateRef, Caster@0x48,
                        op_Addition(Target@0x60, sec), <options ZEROEES>)
        b4  = AddEffect(0x567 = 1383 VexillaMagnifica_DmgReduction, stateRef, Caster@0x48,
                        Caster@0x48, TurnsFromRounds(GetNumberConstant(0x45 = nrOfRounds)))
        ExecuteAtomic( ((b1 & b2) & b3) & b4, 0x2a = GroupType.Ability_AtomicGroup )

CE QUE MESURE LE MONTAGE, par regime :

  * E1  SEQUENCE coup par coup, NATIF (`UnitDamaged` filtre sur `Active_Ability_Type=1183`) contre
        PORT (`per_hit_health` des DEUX feuilles) -- un COMPTE de coups juste ne prouve rien ;
  * E2  TIRAGES `genrand_int32` consommes (`dumpRng` avant/apres contre l'etat MT du port). C'est
        ICI que le tirage du SELECTEUR DE TRI devient visible : la famille ATTACK consomme
        2 tirages par coup a `critChance = 0`, donc l'identite attendue est
        `tirages == 2 x <coups> + 1`, le `+1` etant le `RandomAmount.Calculate` que
        `SortUnitsByDamageUtilitySelector$$Select` appelle AVANT sa boucle par cible ;
  * E3  la SECONDE CIBLE (l'argmax) natif contre port, dans DEUX regimes ou elle DIFFERE ;
  * E4  les EFFETS poses : `Stunned` sur les DEUX cibles + `VexillaMagnifica_DmgReduction` sur le
        CASTER, avec leurs `RemainingTurns` (le Stun n'a AUCUN override de duree cote natif --
        surcharge OPTIONS a struct zeroee -- alors que le buff self porte un `TurnsFromRounds`).

CONTRE-EPREUVES (hors-ligne, MEME capture, MEME MT). Chacune retire UNE lecture du mirror ; si
l'une rendait le MEME resultat que la reference, cette lecture ne serait PAS mesuree par ce montage.

  * `sans_2e_attaque`      -- l'arbre sans `b2` (le patron « 1 seule cible »)
  * `pool_sans_soustraction` -- le pool SANS `op_Subtraction Target` : la 2e cible peut redevenir la
                            cible du message (double coup sur la meme unite)
  * `tri_par_ordre_source` -- `First` du pool SANS tri : prend la tete de l'enumeration d'adjacence
                            au lieu de l'argmax d'utilite
  * `stun_sur_cible_seule` -- `AddEffect(Stunned, Target)` au lieu de `Union(Target, sec)`

TROIS REGIMES, et aucun n'est decoratif :
  * `nominal` -- crit et block NEUTRALISES (`--crit 0,0`, `--block-target 0,0`) : la consommation
                 PRNG devient une identite LISIBLE (2 tirages par coup + 1 pour le tri), donc E2
                 MESURE le tirage du selecteur au lieu de le supposer ;
  * `bascule` -- idem, mais l'armure du candidat prefere au regime `nominal` est poussee au-dela des
                 bornes de degat de l'ability, ce qui EFFONDRE son utilite predite (le selecteur
                 predit SANS PERCAGE : `damageProfile: null` -> `max(0, d - armure)`) et DEPLACE
                 l'argmax sur l'autre candidat. Un port qui ne lirait pas la cle native rendrait la
                 MEME cible dans les deux regimes ;
  * `alea`    -- crit et block NATURELS (aucun flag) : l'identite arithmetique ci-dessus ne tient
                 plus (un `RollCritical` / `RollBlock` consomme ses propres tirages), donc le seul
                 critere est `PORT == NATIF`. C'est le regime qui exerce le pipeline COMPLET -- sans
                 lui, les deux premiers ne mesurent qu'un chemin ou l'alea a ete debranche ;
  * `solo`    -- les DEUX candidats sont EXILES : le pool du selecteur de tri est VIDE. Le natif ne
                 frappe QUE la cible du message et ne stunne QU'ELLE -- mais il CONSOMME QUAND MEME
                 le tirage du tri, parce que `SortUnitsByDamageUtilitySelector$$Select` evalue
                 `damage.Calculate(entities)` AVANT sa boucle par cible. `2 x 1 + 1 = 3` : c'est une
                 prediction FALSIFIABLE de la lecture du decompile, et le seul regime qui la teste.

Aucune valeur attendue codee en dur : l'oracle est le natif qui tourne.

Usage (depuis scripts/python, session Frida chaude) :
    python probe_566_vexilla_magnifica.py [--seed 56600] [--board MC1_67]
                                          [--regimes nominal,bascule]

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

VEXILLA_MAGNIFICA = 1183
CASTER = "custoVexilusPraetor"    # Aesoth -- seul porteur de 1183 (rank 17, dans le pool)
#: FIGURANT DU CAMP JOUEUR, place LOIN. Sans lui, le cast d'Aesoth (qui TERMINE son tour)
#: basculerait le tour au camp adverse DANS l'appel `act`, et le `dumpRng` d'apres compterait, en
#: plus des tirages du cast, ceux du turn-start ennemi (meme piege que probe_509).
P_FILLER = "custoKyrus"
#: TROIS ennemis ADJACENTS au caster : la cible du message + DEUX candidats pour le selecteur de
#: tri. Avec un seul candidat, `First(SortUnitsByDamageUtility(...))` rendrait la meme unite quel
#: que soit le classement -- montage DEGENERE, verdict vide.
FOE_MAIN = "necroWarden"          # cible du message
FOE_A = "bloodMephiston"          # candidat 1
FOE_B = "tauCrisis"               # candidat 2
BOARD = "MC1_67"
RANK = 17
#: (3,4) et ses voisins hex (3,5) / (3,3) / (4,4) -- verifie par `hexgeo.neighbors(3, 4)`.
PLACE_CASTER = "3,4"
PLACE_FILLER = "0,0"
A_PLACES = ((FOE_MAIN, "3,5"), (FOE_A, "3,3"), (FOE_B, "4,4"))
#: Armure du regime `bascule` : au-dela de `maxDmg` de l'ability (4365 au niveau 65), donc la
#: prediction SANS PERCAGE du selecteur (`max(0, d - armure)`) tombe a 0 pour ce candidat.
ARMURE_BASCULE = 9000

#: `UnitDamaged` natif : la SEQUENCE coup par coup (cible, montant, profil), pas un total.
RE_DMG = re.compile(
    r"UnitDamaged e=(\d+).*?Attacker_Id=(\d+) Target_Id=(\d+) Amount=(-?\d+) "
    r"DamageProfileType=(\d+) Active_Ability_Type=(\d+)")
#: TOUS les coups portes pendant l'appel `act` -- sert a ATTRIBUER les tirages.
RE_HIT = re.compile(r"UnitDamaged e=(\d+)\s+UnitStats_RemainingHealth=(-?\d+)")
#: `ReceiveEffect e=<cible> ... Effect_RemainingTurns=<n>` sous un `Effect_Refresh e=.. <<nom>>`.
RE_EFFECT = re.compile(r"\[Effect_(?:Refresh|Add) e=\d+ .(\w+).\]\s*\n\s*ActivateEffect e=(\d+)"
                       r".*?\n\s*ReceiveEffect e=(\d+)[^\n]*?Effect_RemainingTurns=(\d+)")
#: Tirages `genrand_int32` par coup de la famille ATTACK a `critChance = 0` ET `blockChance = 0`
#: (valeur BRUTE + resolve slot-8 gaspille, cf. `behaviours/combat.py`). L'identite ne vaut QUE dans
#: les regimes ou l'alea est neutralise -- mesure du 2026-08-08, a crit/block NATURELS le meme cast
#: consomme 8 tirages des DEUX cotes (le `RollCritical`/`RollBlock` a le sien).
TIRAGES_PAR_COUP = 2
#: `SortUnitsByDamageUtilitySelector$$Select` evalue `damage.Calculate(entities)` UNE fois, et
#: `damage` est un `RandomAmount` -> UN tirage, quel que soit le nombre de candidats.
TIRAGES_DU_TRI = 1
#: `{regime: (neutraliser l'alea ?, neutraliser l'armure du candidat prefere ?, pool VIDE ?)}`
REGIMES = {"nominal": (True, False, False), "bascule": (True, True, False),
           "alea": (False, False, False), "solo": (True, False, True)}
#: Regime `solo` : les DEUX candidats sont exiles a l'autre bout du plateau -> le pool du selecteur
#: de tri est VIDE. Tuiles prises dans la zone de spawn ADVERSE du board (le placement natif rend un
#: NUL SILENCIEUX sur une tuile interdite / reservee / sous brouillard, et `assert_montage` le voit).
EXIL = ((FOE_A, "6,8"), (FOE_B, "5,8"))
#: Ce que le CAST pose, et que le rapport confronte nom par nom : `EffectType` -> nom natif dans la
#: cascade d'events. Les sous-effets du composite `Stunned` (1165/1166/1167) sont poses par
#: `StunnedEffect$$ApplyInternal`, pas par l'arbre : ils sont VERIFIES a part.
EFFET_STUN = 1162
EFFET_DMG_REDUCTION = 1383
NOM_STUN = "Stunned"
NOM_DMG_REDUCTION = "VexillaMagnifica_DmgReduction"


# ------------------------------------------------------------------ transport

def _sid():
    with urllib.request.urlopen(HOST + "/api/admin/status", timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))["session"]["id"]


def _rpc(sid, method, body=None, timeout=120):
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

def build(state_file: str, seed: int, board: str, regime: str, bascule_sur: str | None):
    sans_alea, avec_bascule, pool_vide = REGIMES[regime]
    argv = ["build", "--seed", str(seed), "--board", board, "--rank", str(RANK),
            "--p-units", "%s,%s" % (CASTER, P_FILLER),
            "--a-units", ",".join(v for v, _t in A_PLACES),
            "--no-ai",
            "--place", "%s:%s" % (CASTER, PLACE_CASTER),
            "--place", "%s:%s" % (P_FILLER, PLACE_FILLER),
            "--state-file", state_file]
    exil = dict(EXIL) if pool_vide else {}
    for vid, tile in A_PLACES:
        argv += ["--a-place", "%s:%s" % (vid, exil.get(vid, tile))]
    if sans_alea:
        argv += ["--crit", "0,0", "--block-target", "0,0"]
    if avec_bascule:
        if bascule_sur is None:
            raise SystemExit("regime `bascule` sans candidat a neutraliser : jouer `nominal` avant")
        argv += ["--unit-stat", "%s:Armor=%d,FixedArmor=%d"
                 % (bascule_sur, ARMURE_BASCULE, ARMURE_BASCULE)]
    p = _duel(argv)
    if p.returncode != 0 or not os.path.exists(state_file):
        print("[build %s] rc=%s\n%s\n%s" % (regime, p.returncode, (p.stdout or "")[-1500:],
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
                                  "abilities": u.get("abilities") or []}
    return out, dv


def assert_montage(u, regime):
    """Un montage DEGENERE rendrait l'accord trivial : on echoue AVANT de mesurer, jamais apres."""
    import hexgeo
    _sa, _ab, pool_vide = REGIMES[regime]
    manquants = [v for v in (CASTER, P_FILLER, FOE_MAIN, FOE_A, FOE_B) if v not in u]
    if manquants:
        raise SystemExit("montage invalide : unites absentes %r" % (manquants,))
    voulu = {CASTER: PLACE_CASTER, P_FILLER: PLACE_FILLER}
    voulu.update(dict(A_PLACES))
    if pool_vide:
        voulu.update(dict(EXIL))
    mauvais = [(v, u[v]["pos"], voulu[v]) for v in voulu
               if u[v]["pos"] != tuple(int(x) for x in voulu[v].split(","))]
    if mauvais:
        raise SystemExit("placement REFUSE -- montage invalide, pas de mesure : %r" % (mauvais,))
    c = u[CASTER]["pos"]
    # Regime `solo` : SEULE la cible du message est adjacente -> pool du selecteur de tri VIDE.
    attendus = (FOE_MAIN,) if pool_vide else (FOE_MAIN, FOE_A, FOE_B)
    loin = [v for v in attendus if hexgeo.distance(c, u[v]["pos"]) != 1]
    if loin:
        raise SystemExit("ennemis NON adjacents au caster (%r) : le pool du tri serait tronque"
                         % (loin,))
    if pool_vide:
        proches = [v for v in (FOE_A, FOE_B) if hexgeo.distance(c, u[v]["pos"]) == 1]
        if proches:
            raise SystemExit("regime `solo` : %r est encore adjacent -> le pool n'est PAS vide"
                             % (proches,))


def _ability_entry(u, aid):
    return next((a for a in u["abilities"] if a.get("id") == aid), None)


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


def _effets_portes(st, ids):
    """`{unite: [(effect_type, remaining_turns), ...]}` -- ce que le port a REELLEMENT inscrit."""
    out = {}
    for uid in ids:
        rows = []
        for e in (st.effects.by_unit.get(int(uid), []) if st.effects is not None else []):
            if e.consumed:
                continue
            rows.append((int(e.effect_type), None if e.remaining_turns is None
                         else int(e.remaining_turns)))
        out[int(uid)] = sorted(rows)
    return out


def rejeu_porte(cap, caster_id, target_id, ids):
    """Rejoue le cast par le CHEMIN COMPLET du moteur (`Runner.apply(ActiveAbilityMessage)`), pas
    par un appel direct a `execute_behaviour` : c'est ce qui exerce le registre `ABILITY_CLASSES` et
    rend `ability_handler.last['ported']` -- l'observable qui distingue le port du NO-OP."""
    from engine.runner.messages import ActiveAbilityMessage
    from engine.runner.runner import Runner
    st = etat_porte(cap)
    avant = _effets_portes(st, ids)
    runner = Runner(st).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=int(caster_id), target_id=int(target_id),
                                      ability_type=VEXILLA_MAGNIFICA))
    last = getattr(runner.ability_handler, "last", None) or {}
    seq = [(int(a.get("target")), int(m)) for a in (last.get("attacks") or [])
           for m in ((a.get("attack") or {}).get("per_hit_health") or [])]
    apres = _effets_portes(st, ids)
    # DELTA : ce que CE cast a inscrit (l'etat capte porte deja les passifs de chaque unite).
    poses = {}
    for uid, rows in apres.items():
        neuf = [r for r in rows if r not in avant.get(uid, [])]
        if neuf:
            poses[uid] = sorted(neuf)
    return {
        "ported": last.get("ported"),
        "second": last.get("second_target"),
        "rolls": last.get("sort_rolls"),
        "posed": last.get("posed"),
        "poses": poses,
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
    arbre_fn(st).execute(entities, ectx)
    seq = [(int(p.get("target")), int(m))
           for n, p in ectx.emitted if n == "AttackWithAttackDamage"
           for m in ((p.get("attack") or {}).get("per_hit_health") or [])]
    stun = sorted({int(p.get("target")) for n, p in ectx.emitted
                   if n == "AddEffect" and int(p.get("effect_type") or 0) == 1162})
    return {"seq": seq, "total": sum(m for _t, m in seq), "stun": stun,
            "tirages": tirages(cap["rng"], list(st.rng.mt), st.rng.mti)}


def contre_epreuves(cap, caster_id, target_id):
    """Chaque variante ne change QU'UNE lecture du mirror."""
    from engine.entities.behaviours import AtomicGroup, op_and
    from engine.entities.effect_type import EffectType
    from engine.entities.selectors.accessors import Target
    from engine.entities.selectors.geometry import Cache
    from engine.entities.selectors.tiles import Caster
    from engine.entities.selectors.units import AdjacentEnemies, First, NormalUnits, Union
    from engine.runner.abilities.base import ability_attack_params
    from engine.runner.abilities.behaviours.combat import AttackWithAttackDamage
    from engine.runner.abilities.behaviours.effects import AddEffect
    import engine.runner.abilities.custodes as CU
    import gameconfig as GC

    consts = (GC.ability(CU.VEXILLA_MAGNIFICA_ID) or {}).get("constants") or {}
    prof = consts.get("damageProfile")
    rounds = int(consts.get(CU.CONST_VM_NR_OF_ROUNDS.name) or 0)

    def _pieces(st, pool=None, second=None):
        from engine.runner.abilities.base import convert_rounds_to_turns
        bmin, bmax, _p, _h = ability_attack_params(st, int(caster_id), CU.VEXILLA_MAGNIFICA_ID,
                                                   prof, ranged=False)
        if second is None:
            src = pool if pool is not None else CU.vexilla_magnifica_pool()
            second = Cache(CU.VexillaMagnificaSecondTarget(src, st, bmin, bmax))
        return second, convert_rounds_to_turns(st, rounds)

    def _ref(st):
        second, turns = _pieces(st)
        return CU.vexilla_magnifica_tree(prof, second, turns)

    def _sans_2e_attaque(st):
        second, turns = _pieces(st)
        b1 = AttackWithAttackDamage(Target(), CU.VEXILLA_MAGNIFICA_ID, prof, is_melee=True,
                                    multi=True, ability_type=VEXILLA_MAGNIFICA)
        b3 = AddEffect(CU.VM_STUNNED, EffectType.Stunned.name, Union(Target(), second),
                       duration_rounds=None)
        b4 = AddEffect(CU.VM_DMG_REDUCTION, EffectType.VexillaMagnifica_DmgReduction.name,
                       Caster(), duration_rounds=None, duration_turns=turns,
                       scale_from_source=True)
        return AtomicGroup(op_and(op_and(b1, b3), b4))

    def _pool_sans_soustraction(st):
        second, turns = _pieces(st, pool=NormalUnits(AdjacentEnemies(Caster())))
        return CU.vexilla_magnifica_tree(prof, second, turns)

    def _tri_par_ordre_source(st):
        # `First` NU sur le pool : la tete de l'enumeration d'adjacence, PAS l'argmax d'utilite.
        second, turns = _pieces(st, second=Cache(First(CU.vexilla_magnifica_pool())))
        return CU.vexilla_magnifica_tree(prof, second, turns)

    def _stun_sur_cible_seule(st):
        second, turns = _pieces(st)
        b1 = AttackWithAttackDamage(Target(), CU.VEXILLA_MAGNIFICA_ID, prof, is_melee=True,
                                    multi=True, ability_type=VEXILLA_MAGNIFICA)
        b2 = AttackWithAttackDamage(second, CU.VEXILLA_MAGNIFICA_ID, prof, is_melee=True,
                                    multi=True, ability_type=VEXILLA_MAGNIFICA)
        b3 = AddEffect(CU.VM_STUNNED, EffectType.Stunned.name, Target(), duration_rounds=None)
        b4 = AddEffect(CU.VM_DMG_REDUCTION, EffectType.VexillaMagnifica_DmgReduction.name,
                       Caster(), duration_rounds=None, duration_turns=turns,
                       scale_from_source=True)
        return AtomicGroup(op_and(op_and(op_and(b1, b2), b3), b4))

    variantes = {"ref": _ref, "sans_2e_attaque": _sans_2e_attaque,
                 "pool_sans_soustraction": _pool_sans_soustraction,
                 "tri_par_ordre_source": _tri_par_ordre_source,
                 "stun_sur_cible_seule": _stun_sur_cible_seule}
    return {k: _rejeu_arbre(cap, caster_id, target_id, v) for k, v in variantes.items()}


def tirages(rng_initial, mt_cible, mti_cible, cap=600):
    """Nombre de `genrand_int32` consommes pour aller de l'etat INITIAL a l'etat CIBLE. None si non
    atteint."""
    from engine.runner.prng import IntBasedMersenneTwister
    r = IntBasedMersenneTwister()
    r.mt, r.mti = list(rng_initial["mt"]), rng_initial["mti"]
    for n in range(cap + 1):
        if r.mti == mti_cible and r.mt == mt_cible:
            return n
        r.genrand_int32()
    return None


# ------------------------------------------------------------------ pilotage

def _cast(state_file, rid, cid, tid, aid):
    return _duel(["act", "ability", "--caster", str(cid), "--ability", str(aid),
                  "--target", str(tid), "--state-file", state_file, "--runner", str(rid)])


def _effets_natifs(sortie):
    """`{cible: [(nom, remainingTurns), ...]}` LU dans la cascade d'events du cast."""
    out = {}
    for nom, _act, cible, turns in RE_EFFECT.findall(sortie or ""):
        out.setdefault(int(cible), []).append((nom, int(turns)))
    return {k: sorted(v) for k, v in out.items()}


def mesure(sid, state_file, seed, board, regime, bascule_sur, garder=False):
    rid = build(state_file, seed, board, regime, bascule_sur)
    if rid is None:
        return None
    try:
        u, dv = unites(sid, rid)
        assert_montage(u, regime)
        cid, tid = u[CASTER]["id"], u[FOE_MAIN]["id"]
        ids = [u[v]["id"] for v in (CASTER, FOE_MAIN, FOE_A, FOE_B)]
        ent = _ability_entry(u[CASTER], VEXILLA_MAGNIFICA)
        if not (ent and ent.get("usable") and not ent.get("disabled") and not ent.get("cooldown")):
            raise SystemExit("1183 indisponible au 1er tour -- montage sterile")
        cap = capture(sid, rid)
        port = rejeu_porte(cap, cid, tid, ids)
        ab = contre_epreuves(cap, cid, tid)
        p = _cast(state_file, rid, cid, tid, VEXILLA_MAGNIFICA)
        seq_n = [(int(t), int(a), int(pr))
                 for _e, at, t, a, pr, ab_id in RE_DMG.findall(p.stdout or "")
                 if int(ab_id) == VEXILLA_MAGNIFICA and int(at) == int(cid)]
        coups_tous = RE_HIT.findall(p.stdout or "")
        rng_apres = _rpc(sid, "dumpRng", {"runnerId": rid}, 60)
        return {
            "regime": regime, "rid": rid, "caster": cid, "cible": tid,
            "noms": {u[v]["id"]: v for v in (CASTER, FOE_MAIN, FOE_A, FOE_B)},
            "hp": {u[v]["id"]: u[v]["hp"] for v in (FOE_MAIN, FOE_A, FOE_B)},
            "port": port, "ab": ab,
            "natif": {"seq": [(t, a) for t, a, _pr in seq_n],
                      "profils": [pr for _t, _a, pr in seq_n],
                      "total": sum(a for _t, a, _pr in seq_n),
                      "coups_tous": len(coups_tous),
                      "effets": _effets_natifs(p.stdout),
                      "rc": p.returncode,
                      "out": (p.stdout or "")[-1500:] + (p.stderr or "")[-600:]},
            "tirages_natif": (tirages(cap["rng"], rng_apres.get("mt"), rng_apres.get("mti"))
                              if isinstance(rng_apres, dict) and rng_apres.get("mt") else None),
            "tirages_port": tirages(cap["rng"], port["mt"][0], port["mt"][1]),
        }
    finally:
        if not garder:
            _duel(["dispose", "--state-file", state_file, "--runner", str(rid)], timeout=120)


# ------------------------------------------------------------------ rapport

def rapport(m) -> bool:
    noms = m["noms"]
    print("[566:%s] runner=%s caster=u%s(%s) cible=u%s(%s)"
          % (m["regime"], m["rid"], m["caster"], noms.get(m["caster"]),
             m["cible"], noms.get(m["cible"])))
    print("   PV/adverses : %s" % {("u%d %s" % (k, noms.get(k))): v for k, v in m["hp"].items()})
    sp, sn = m["port"]["seq"], m["natif"]["seq"]
    ok = True
    print("   E1 SEQUENCE  PORT (%d coups) = %s" % (len(sp), sp))
    print("                NATIF(%d coups) = %s   profils=%s"
          % (len(sn), sn, m["natif"]["profils"]))
    print("   E1 total     PORT=%s  NATIF=%s   (ported=%s, rc=%s)"
          % (m["port"]["total"], m["natif"]["total"], m["port"]["ported"], m["natif"]["rc"]))
    cibles_n = sorted({t for t, _a in sn})
    sec_n = [t for t in cibles_n if t != m["cible"]]
    print("   E3 2e CIBLE  PORT=u%s(%s)  NATIF=%s   (tirage du tri cote port : %s)"
          % (m["port"]["second"], noms.get(m["port"]["second"]),
             ["u%d(%s)" % (t, noms.get(t)) for t in sec_n], m["port"]["rolls"]))
    sans_alea, _ab, pool_vide = REGIMES[m["regime"]]
    att = TIRAGES_PAR_COUP * m["natif"]["coups_tous"] + TIRAGES_DU_TRI
    print("   E2 TIRAGES genrand_int32 : PORT=%s  NATIF=%s%s"
          % (m["tirages_port"], m["tirages_natif"],
             ("   attendu = 2 x %d coups + %d (tri) = %d"
              % (m["natif"]["coups_tous"], TIRAGES_DU_TRI, att)) if sans_alea
             else "   (alea NATUREL -> pas d'identite arithmetique, seul PORT == NATIF est exige)"))
    print("   E4 EFFETS   NATIF = %s" % (m["natif"]["effets"],))
    print("               PORT (poses par ce cast) = %s" % (m["port"]["poses"],))
    print("   -- contre-epreuves (hors-ligne, MEME capture, MEME MT) --")
    ref = (m["ab"] or {}).get("ref") or {}
    for nom, r in (m["ab"] or {}).items():
        marque = "== REF" if nom != "ref" and r["seq"] == ref.get("seq") and r["stun"] == ref.get("stun") else ""
        print("      %-24s seq=%-28s stun=%-10s tirages=%-4s %s"
              % (nom, r["seq"], r["stun"], r["tirages"], marque))
    if sp != sn or not sn:
        print("   !! SEQUENCE DIVERGENTE")
        ok = False
    if pool_vide:
        # Le POOL EST VIDE : le natif ne frappe QUE la cible du message, et le port doit rendre
        # `second = None` -- pas une cible de repli. Le tirage du tri, LUI, tombe QUAND MEME
        # (`Select` evalue `damage.Calculate` AVANT sa boucle par cible), et c'est E2 qui le dit.
        if sec_n:
            print("   !! regime `solo` : le natif a frappe une SECONDE cible (%s)" % (sec_n,))
            ok = False
        if m["port"]["second"] is not None:
            print("   !! regime `solo` : le port s'invente une seconde cible (u%s)"
                  % m["port"]["second"])
            ok = False
    elif len(sec_n) != 1:
        print("   !! le natif n'a pas frappe exactement UNE seconde cible (%s)" % (sec_n,))
        ok = False
    elif m["port"]["second"] != sec_n[0]:
        print("   !! SECONDE CIBLE DIVERGENTE")
        ok = False
    if m["tirages_port"] is None or m["tirages_port"] != m["tirages_natif"]:
        print("   !! TIRAGES DIVERGENTS (port %s != natif %s)"
              % (m["tirages_port"], m["tirages_natif"]))
        ok = False
    if sans_alea:
        # L'identite n'a de sens qu'a alea NEUTRALISE -- et c'est elle qui MESURE le tirage du tri.
        if m["tirages_port"] != TIRAGES_PAR_COUP * len(sp) + TIRAGES_DU_TRI:
            print("   !! le port ne consomme pas 2/coup + 1 (tri)")
            ok = False
        if m["tirages_natif"] != att:
            print("   !! l'attribution des tirages natifs ne boucle pas (%s != %s)"
                  % (m["tirages_natif"], att))
            ok = False
    if ref.get("seq") != sn:
        print("   !! l'arbre du module ne rend pas la sequence native")
        ok = False
    # E4 -- LE STUN touche les DEUX cibles frappees, le buff self le CASTER, avec les MEMES durees.
    stun_n = {k: dict(v).get(NOM_STUN) for k, v in (m["natif"]["effets"] or {}).items()
              if any(n == NOM_STUN for n, _t in v)}
    if sorted(stun_n) != cibles_n or not stun_n:
        print("   !! le natif ne stunne pas exactement les cibles frappees (%s vs %s)"
              % (sorted(stun_n), cibles_n))
        ok = False
    stun_p = {k: t for (k, e), t in
              (((k, e), t) for k, rows in m["port"]["poses"].items() for e, t in rows)
              if e == EFFET_STUN}
    if stun_p != stun_n:
        print("   !! STUN DIVERGENT (port %s != natif %s)" % (stun_p, stun_n))
        ok = False
    red_n = {k: dict(v).get(NOM_DMG_REDUCTION) for k, v in (m["natif"]["effets"] or {}).items()
             if any(n == NOM_DMG_REDUCTION for n, _t in v)}
    red_p = {k: t for (k, e), t in
             (((k, e), t) for k, rows in m["port"]["poses"].items() for e, t in rows)
             if e == EFFET_DMG_REDUCTION}
    if red_n != {m["caster"]: red_n.get(m["caster"])} or not red_n:
        print("   !! le natif ne pose pas 1383 sur le SEUL caster (%s)" % (red_n,))
        ok = False
    if red_p != red_n:
        print("   !! BUFF SELF DIVERGENT (port %s != natif %s)" % (red_p, red_n))
        ok = False
    if sorted(ref.get("stun") or []) != cibles_n:
        print("   !! l'arbre du module ne stunne pas les cibles frappees")
        ok = False
    return ok


def discriminantes(mesures) -> bool:
    """Une contre-epreuve doit diverger dans AU MOINS un regime : sinon la lecture qu'elle retire
    n'est mesuree NULLE PART, et l'accord du port serait un accord de hasard."""
    ok = True
    noms = set()
    for m in mesures:
        noms |= set((m["ab"] or {}).keys())
    for nom in sorted(noms - {"ref"}):
        diverge = []
        for m in mesures:
            r = (m["ab"] or {}).get(nom) or {}
            ref = (m["ab"] or {}).get("ref") or {}
            if r.get("seq") != ref.get("seq") or r.get("stun") != ref.get("stun"):
                diverge.append(m["regime"])
        print("[566] contre-epreuve %-24s diverge de la REF sur : %s"
              % (nom, diverge or "AUCUN REGIME"))
        if not diverge:
            ok = False
    secondes = {m["regime"]: m["port"]["second"] for m in mesures
                if not REGIMES[m["regime"]][2]}
    print("[566] SECONDE CIBLE par regime (port, pool NON vide) : %s" % (secondes,))
    if len(secondes) > 1 and len(set(secondes.values())) < 2:
        print("[566] !! REGIME DEGENERE : la 2e cible ne bascule pas entre les regimes -- "
              "le montage ne peut pas distinguer l'argmax d'un `First` d'ordre source")
        ok = False
    return ok


def campagne(sid, base_sf, seed, board, regimes, garder=False, imprimer=True):
    """Joue les regimes DANS L'ORDRE et rend `(mesures, ok)`. FOYER UNIQUE du montage et des
    criteres : `main` et la garde `test_566_vexilla_magnifica_live.py` passent tous deux par ici
    (le test ne duplique NI le montage NI les criteres).

    L'ORDRE compte : `bascule` neutralise le candidat que le natif a PREFERE au regime `nominal`
    -- c'est-a-dire une valeur MESUREE, jamais un `visualId` code en dur."""
    tout_ok = True
    mesures = []
    bascule_sur = None
    for regime in regimes:
        sf = base_sf.replace(".json", "_%s.json" % regime)
        m = mesure(sid, sf, seed, board, regime, bascule_sur, garder=garder)
        if m is None:
            print("[566:%s] BUILD KO" % regime)
            tout_ok = False
            continue
        if imprimer:
            tout_ok = rapport(m) and tout_ok
        mesures.append(m)
        if regime == "nominal":
            sec = m["port"]["second"]
            bascule_sur = m["noms"].get(sec)
            print("[566] candidat prefere au regime nominal = %s -> neutralise au regime bascule"
                  % bascule_sur)
    if imprimer:
        tout_ok = discriminantes(mesures) and tout_ok
    return mesures, tout_ok


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Confrontation live du port COMBAT de 1183")
    ap.add_argument("--seed", type=int, default=56600)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--regimes", default="nominal,bascule,alea,solo")
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--garder", action="store_true")
    a = ap.parse_args(argv)

    import gameconfig as GC
    consts = (GC.ability("VexillaMagnifica") or {}).get("constants") or {}
    print("config VexillaMagnifica : nrOfHits=%s nrOfRounds=%s damageProfile=%s"
          % (consts.get("nrOfHits"), consts.get("nrOfRounds"), consts.get("damageProfile")))

    sid = _sid()
    base_sf = a.state_file or str(Path(PYDIR).parents[1] / "logs"
                                  / ("probe566_%d.json" % os.getpid()))
    _mesures, tout_ok = campagne(sid, base_sf, a.seed, a.board,
                                 [r.strip() for r in a.regimes.split(",") if r.strip()],
                                 garder=a.garder)
    print("[566] VERDICT : %s" % ("OK" if tout_ok else "DIVERGENCE"))
    return 0 if tout_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
