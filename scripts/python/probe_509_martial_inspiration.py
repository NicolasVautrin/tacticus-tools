#!/usr/bin/env python
"""probe_509_martial_inspiration -- CONFRONTATION LIVE du port COMBAT de `1191 MartialInspiration`
(`custoBladeChampion` << Kariyan >>, Adeptus Custodes).

QUESTION BINAIRE. Le port rend-il, COUP PAR COUP et TIRAGE PAR TIRAGE, ce que rend le natif -- et
le fait-il dans les TROIS regimes du compteur `TotalTurnsWithAttacksMade` (0, 1, 2) ? Sans les deux
derniers, le premier ne prouve rien : un port qui IGNORERAIT l'effet 1408 matcherait aussi
longtemps que le compteur vaut 0 (produit nul).

MECANIQUE (decompile = verite, build `rnca9r7q6c`).

    IdunBattleLogic.Entities.Abilities.Active.Loki.MartialInspirationAbility$$ExecuteBehaviour
        buff = AddEffect( 0x580 = 1408, AbilityStateReference, source = Caster@0x48,
                          targets = Caster@0x48, turns = Direct(1) )
        atk  = AttackWithAttackDamage( Caster@0x48, Target@0x60, MinMaxDamage(minDmg, maxDmg),
                                       Direct(GetDamageProfile()), Direct(GetHits()), ... )
        Execute( op_BitwiseAnd(buff, atk) )

    IdunBattle.Entities.Effects.Loki.MartialInspiration_ExtraDamageEffect$$CreateEffectDamageBonusForAttack
        ForPercentIncrease( get_OwnerIsCaster & ( CurrentAbilityIs(ActiveAbilityType 1191)
                                                  | CurrentAbilityIs(TriggeredAbilityType 1319) ),
                            Multiply( ConfigVar(0xa = extraDmgPct),
                                      TotalTurnsWithAttacksMade(Owner@DSLSelectors+0x30) ) )

    IdunBattle.Entities.Components.ActorStatisticsComponent$$RegisterAttackMade
        if (Count(+0x40) == 0) +0x30 += 1 ;  Add(+0x40, target)      # UNE fois par TOUR
    IdunBattle.Entities.Components.ActorStatisticsComponent$$ResetUnitsAttackedThisTurn
        Clear(+0x40)                                                  # StartTurnOperation

Le buff est donc pose AVANT l'attaque et la buffe elle-meme (`CurrentAbilityIs(1191)`), et sa
magnitude est `extraDmgPct x <nb de tours ou Kariyan a attaque>` -- NULLE au premier tour.

CE QUE MESURE LE MONTAGE, par cast :

  * `compteur` -- `actorStats[caster].totalTurnsWithAttacksMade`, LU LIVE (le champ `+0x30` que le
                  hook publie deja) : la verite du natif, jamais un derive ;
  * E1  SEQUENCE coup par coup, NATIF (`UnitDamaged` filtre sur `Active_Ability_Type=1191`)
        contre PORT (`per_hit_health` de la feuille) -- un COMPTE de coups juste ne prouve rien ;
  * E2  TIRAGES `genrand_int32` consommes (`dumpRng` avant/apres contre l'etat MT du port) --
        c'est l'etage qui separe une faute d'ARITHMETIQUE d'une faute de STRUCTURE ;
  * E3  le RATIO `total(compteur=n) / total(compteur=0)` cote NATIF, confronte a `1 + n x
        extraDmgPct/100` -- l'etage qui dit que le bonus est bien MULTIPLICATIF et INDEXE par le
        compteur (et non, par exemple, un scale des bornes d'arme).

DEUX REGIMES D'ARMURE, et le second n'est pas decoratif :
  * `nominal`  -- `--hp-target` met Armor/FixedArmor a 0 : le ratio est lisible en clair ;
  * `armure`   -- armure NON nulle : `EffectBonus.ForPercentIncrease` ecrit la %-list du
                  `DamageModifiers` ATTAQUANT, appliquee **APRES** percage/armure. Un port qui
                  scalerait les BORNES D'ARME donnerait le meme resultat a armure 0 et un resultat
                  DIFFERENT ici. C'est le regime qui separe les deux etages.

Aucune valeur attendue codee en dur : l'oracle est le natif qui tourne.

Usage (depuis scripts/python, session Frida chaude) :
    python probe_509_martial_inspiration.py [--seed 50901] [--board MC1_67]
                                            [--regimes nominal,armure] [--tours 6]

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

MARTIAL_INSPIRATION = 1191
CASTER = "custoBladeChampion"     # Kariyan -- seul porteur LINEUP de 1191 (rank 17, dans le pool)
FOE = "necroWarden"               # cible principale
FILLER = "necroOverlord"          # 2e a-unit : la bataille ne se termine pas si la cible tombe
#: FIGURANT DU CAMP JOUEUR, place LOIN. Sans lui, le cast de Kariyan (qui TERMINE son tour)
#: basculerait le tour au camp adverse DANS l'appel `act`, et le `dumpRng` d'apres compterait, en
#: plus des tirages du cast, ceux du turn-start ennemi -- mesure du 2026-08-07 : 24 tirages natifs
#: contre 6 cote port, dans les DEUX regimes, alors que les montants etaient bit-exacts au regime
#: temoin. Un compteur de tirages faux masque exactement ce qu'il est cense montrer.
P_FILLER = "deathRotbone"
BOARD = "MC1_67"
RANK = 17
#: (5,8) est l'UNIQUE voisin libre de (6,8) sur ce board (l'autre, (6,7), porte le figurant) --
#: verifie par `boardGraph` : la tuile (6,8) n'a que DEUX voisins. Toutes les tuiles sont a
#: elevation 1 -> aucun bonus d'elevation ne pollue la mesure.
PLACE_CASTER = "5,8"
PLACE_FILLER = "1,0"
A_PLACES = ((FOE, "6,8"), (FILLER, "6,7"))
HP_FOE = 300000                   # la cible ne meurt jamais : la fenetre de mesure reste ouverte
ARMURE = 2000                     # regime `armure` : etage percage/armure NON degenere

#: `UnitDamaged` natif : la SEQUENCE coup par coup (cible, montant, profil), pas un total.
RE_DMG = re.compile(
    r"UnitDamaged e=(\d+).*?Attacker_Id=(\d+) Target_Id=(\d+) Amount=(-?\d+) "
    r"DamageProfileType=(\d+) Active_Ability_Type=(\d+)")
#: TOUS les coups portes pendant l'appel `act`, y compris ceux qu'aucune `Active_Ability_Type` ne
#: qualifie. Sert a ATTRIBUER les tirages : la famille ATTACK consomme 2 `genrand_int32` par coup
#: a `critChance = 0` (valeur BRUTE + resolve slot-8 gaspille, cf. `behaviours/combat.py`), donc
#: `tirages_natif` doit valoir `2 x <nombre total de coups>` -- et l'ecart avec le port se lit
#: alors comme un NOMBRE DE COUPS, pas comme un mystere.
RE_HIT = re.compile(r"UnitDamaged e=(\d+)\s+UnitStats_RemainingHealth=(-?\d+)")
#: Tirages `genrand_int32` par coup de la famille ATTACK a `critChance = 0`.
TIRAGES_PAR_COUP = 2


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

def build(state_file: str, seed: int, board: str, regime: str):
    argv = ["build", "--seed", str(seed), "--board", board, "--rank", str(RANK),
            "--p-units", "%s,%s" % (CASTER, P_FILLER),
            "--a-units", ",".join(v for v, _t in A_PLACES),
            "--crit", "0,0", "--block-target", "0,0",
            "--place", "%s:%s" % (CASTER, PLACE_CASTER),
            "--place", "%s:%s" % (P_FILLER, PLACE_FILLER),
            "--state-file", state_file]
    for vid, tile in A_PLACES:
        argv += ["--a-place", "%s:%s" % (vid, tile)]
    if regime == "nominal":
        # ⚠ `--hp-target` met AUSSI Armor/FixedArmor a 0 : l'etage armure est DEGENERE ici, et
        # c'est voulu (le ratio se lit en clair). Le regime `armure` le retablit.
        argv += ["--hp-target", str(HP_FOE)]
    else:
        for vid, _t in A_PLACES:
            argv += ["--unit-stat", "%s:Health=%d,RemainingHealth=%d" % (vid, HP_FOE, HP_FOE)]
        argv += ["--armor-target", str(ARMURE)]
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
                                  "ctrl": u.get("ctrl"),
                                  "abilities": u.get("abilities") or []}
    return out, dv


def assert_montage(u, regime):
    """Un montage DEGENERE rendrait l'accord trivial : on echoue AVANT de mesurer, jamais apres."""
    manquants = [v for v in (CASTER, FOE, FILLER, P_FILLER) if v not in u]
    if manquants:
        raise SystemExit("montage invalide : unites absentes %r" % (manquants,))
    voulu = {CASTER: PLACE_CASTER, P_FILLER: PLACE_FILLER}
    voulu.update(dict(A_PLACES))
    mauvais = [(v, u[v]["pos"], voulu[v]) for v in voulu
               if u[v]["pos"] != tuple(int(x) for x in voulu[v].split(","))]
    if mauvais:
        raise SystemExit("placement REFUSE -- montage invalide, pas de mesure : %r" % (mauvais,))
    if int(u[FOE]["hp"] or 0) < 1000:
        raise SystemExit("cible trop fragile (%s PV) : elle mourrait avant la 3e mesure"
                         % u[FOE]["hp"])


def _ability_entry(u, aid):
    return next((a for a in u["abilities"] if a.get("id") == aid), None)


def _normal_id(u):
    """Id CONCRET de l'attaque normale (`kind == "normal"`), per-unite -- jamais le 17 generique."""
    return next((a.get("id") for a in u["abilities"] if a.get("kind") == "normal"), None)


def _counters(sid, rid):
    """`ActorStatisticsComponent+0x30` et `+0x20` per-unite, LUS LIVE (RPC `actorStats`)."""
    resp = _rpc(sid, "actorStats", {"runnerId": rid}, 60)
    units = (resp or {}).get("units")
    if units is None:
        return None                       # canal NON MESURE != canal mesure et vide
    return {u["entityId"]: (int(u.get("totalTurnsWithAttacksMade") or 0),
                            int(u.get("totalAttacksMade") or 0))
            for u in units if u.get("entityId") is not None}


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
    """`State` charge depuis la capture, PRNG cale sur `dumpRng`, compteurs `ActorStatistics`
    seedes depuis `actorStats`.

    ⚠ Sans le calage MT, `execute_ability_attack` SKIPPE le degat par repli defensif : on lirait un
    faux `0`. Sans `actor_stats=`, `turns_with_attacks_made` repartirait a 0 et le bonus serait
    NUL -- l'accord du regime `compteur = 0` serait alors le SEUL atteignable."""
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
    par un appel direct a `execute_behaviour` : c'est ce qui exerce le registre `ABILITY_CLASSES`
    et rend `ability_handler.last['ported']` -- l'observable qui distingue le port du NO-OP."""
    from engine.runner.components import UnitComponent
    from engine.runner.messages import ActiveAbilityMessage
    from engine.runner.runner import Runner
    st = etat_porte(cap)
    e = st.get_entity(int(caster_id))
    uc = e.get_component(UnitComponent) if e is not None else None
    compteur = int(getattr(uc, "turns_with_attacks_made", 0) or 0)
    runner = Runner(st).install_default_handlers(20)
    runner.apply(ActiveAbilityMessage(caster_id=int(caster_id), target_id=int(target_id),
                                      ability_type=MARTIAL_INSPIRATION))
    last = getattr(runner.ability_handler, "last", None) or {}
    seq = [(int(a.get("target")), int(m)) for a in (last.get("attacks") or [])
           for m in ((a.get("attack") or {}).get("per_hit_health") or [])]
    e2 = st.get_entity(int(caster_id))
    uc2 = e2.get_component(UnitComponent) if e2 is not None else None
    return {
        "ported": last.get("ported"),
        "compteur_avant": compteur,
        "compteur_apres": int(getattr(uc2, "turns_with_attacks_made", 0) or 0),
        "posed": last.get("posed"),
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
    arbre_fn().execute(entities, ectx)
    seq = [(int(p.get("target")), int(m))
           for n, p in ectx.emitted if n == "AttackWithAttackDamage"
           for m in ((p.get("attack") or {}).get("per_hit_health") or [])]
    return {"seq": seq, "total": sum(m for _t, m in seq),
            "tirages": tirages(cap["rng"], list(st.rng.mt), st.rng.mti)}


def contre_epreuves(cap, caster_id, target_id):
    """Chaque variante ne change QU'UNE lecture du mirror. Si l'une rendait le MEME resultat que la
    REFERENCE, la lecture correspondante ne serait PAS mesuree par ce montage -- et l'accord du
    port avec le natif serait un accord de hasard.

    `sans_ability_type` est la contre-epreuve qui a MORDU : le port initial omettait le 7e argument
    natif d'`AttackWithAttackDamage` (`abilityOrEffect = AbilityOrEffect(this)`), donc le gate
    `CurrentAbilityIs(1191)` de l'effet 1408 restait ferme. Il etait bit-exact au regime
    `compteur = 0` et faux d'un facteur `1 + n x 33 %` partout ailleurs."""
    from engine.entities.active_ability_type import ActiveAbilityType
    from engine.entities.behaviours import op_and
    from engine.entities.effect_type import EffectType
    from engine.entities.selectors.accessors import Target
    from engine.entities.selectors.tiles import Caster
    from engine.runner.abilities.behaviours.combat import AttackWithAttackDamage
    from engine.runner.abilities.behaviours.effects import AddEffect
    import engine.runner.abilities.custodes as CU
    import gameconfig as GC

    prof = ((GC.ability(CU.MARTIAL_INSPIRATION_ID) or {}).get("constants") or {}).get("damageProfile")
    aid = int(ActiveAbilityType.MartialInspiration)
    eff, nom = CU.MI_EXTRA_DAMAGE, EffectType.MartialInspiration_ExtraDamage.name

    def _buff():
        return AddEffect(eff, nom, Caster(), duration_rounds=None,
                         duration_turns=CU.MI_BUFF_TURNS, scale_from_source=True)

    def _atk(with_type=True):
        return AttackWithAttackDamage(Target(), CU.MARTIAL_INSPIRATION_ID, prof, is_melee=True,
                                      ability_type=(aid if with_type else None))

    variantes = {
        "ref                 ": lambda: CU.martial_inspiration_tree(prof),
        "sans_effet          ": lambda: _atk(),
        "ordre_inverse       ": lambda: op_and(_atk(), _buff()),
        "sans_ability_type   ": lambda: op_and(_buff(), _atk(with_type=False)),
    }
    return {k.strip(): _rejeu_arbre(cap, caster_id, target_id, v) for k, v in variantes.items()}


def tirages(rng_initial, mt_cible, mti_cible, cap=600):
    """Nombre de `genrand_int32` consommes pour aller de l'etat INITIAL a l'etat CIBLE. Deux
    moteurs qui rendent des montants differents mais consomment le MEME nombre de tirages ont un
    bug d'ARITHMETIQUE ; sinon c'est la STRUCTURE. Rend None si non atteint."""
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


def mesure(sid, state_file, seed, board, regime, tours, garder=False):
    rid = build(state_file, seed, board, regime)
    if rid is None:
        return None
    casts = []
    try:
        u, dv = unites(sid, rid)
        assert_montage(u, regime)
        cid, tid = u[CASTER]["id"], u[FOE]["id"]
        me = u[CASTER]["owner"]
        nid = _normal_id(u[CASTER])
        if nid is None:
            raise SystemExit("attaque normale introuvable sur %s" % CASTER)
        for _tour in range(int(tours)):
            u, dv = unites(sid, rid)
            if dv.get("currentPlayer") != me:
                _rendre_la_main(sid, rid, me)
                u, dv = unites(sid, rid)
            ent = _ability_entry(u[CASTER], MARTIAL_INSPIRATION)
            dispo = bool(ent and ent.get("usable") and not ent.get("disabled")
                         and not ent.get("cooldown"))
            cnt = (_counters(sid, rid) or {}).get(cid)
            if not dispo:
                # ATTAQUE NORMALE : elle fait avancer `+0x30` d'un cran (ce tour compte), ce qui est
                # exactement le levier du regime suivant.
                _cast(state_file, rid, cid, tid, nid)
                _rendre_la_main(sid, rid, me)
                continue
            cap = capture(sid, rid)
            port = rejeu_porte(cap, cid, tid)
            ab = contre_epreuves(cap, cid, tid)
            p = _cast(state_file, rid, cid, tid, MARTIAL_INSPIRATION)
            seq_n = [(int(t), int(a), int(pr))
                     for _e, at, t, a, pr, ab_id in RE_DMG.findall(p.stdout or "")
                     if int(ab_id) == MARTIAL_INSPIRATION and int(at) == int(cid)]
            coups_tous = RE_HIT.findall(p.stdout or "")
            rng_apres = _rpc(sid, "dumpRng", {"runnerId": rid}, 60)
            cnt_apres = (_counters(sid, rid) or {}).get(cid)
            casts.append({
                "compteur_live": (cnt or (None, None))[0],
                "attaques_live": (cnt or (None, None))[1],
                "compteur_live_apres": (cnt_apres or (None, None))[0],
                "port": port, "ab": ab,
                "natif": {"seq": [(t, a) for t, a, _pr in seq_n],
                          "profils": [pr for _t, _a, pr in seq_n],
                          "total": sum(a for _t, a, _pr in seq_n),
                          "coups_tous": len(coups_tous),
                          "cibles_tous": sorted({int(e) for e, _hp in coups_tous}),
                          "rc": p.returncode,
                          "out": (p.stdout or "")[-2000:] + (p.stderr or "")[-600:]},
                "tirages_natif": (tirages(cap["rng"], rng_apres.get("mt"), rng_apres.get("mti"))
                                  if isinstance(rng_apres, dict) and rng_apres.get("mt") else None),
                "tirages_port": tirages(cap["rng"], port["mt"][0], port["mt"][1]),
            })
            _rendre_la_main(sid, rid, me)
        return {"regime": regime, "rid": rid, "caster": cid, "cible": tid, "casts": casts,
                "hp_cible": u[FOE]["hp"]}
    finally:
        if not garder:
            _duel(["dispose", "--state-file", state_file, "--runner", str(rid)], timeout=120)


# ------------------------------------------------------------------ rapport

def rapport(m, extra_pct) -> bool:
    print("[509:%s] runner=%s caster=u%s cible=u%s (PV %s)"
          % (m["regime"], m["rid"], m["caster"], m["cible"], m["hp_cible"]))
    if not m["casts"]:
        print("  AUCUN cast mesure -- montage sterile, verdict IMPOSSIBLE")
        return False
    base = None
    ok = True
    for c in m["casts"]:
        n = c["compteur_live"]
        sp, sn = c["port"]["seq"], c["natif"]["seq"]
        print("  -- cast avec TotalTurnsWithAttacksMade = %s (TotalAttacksMade = %s) --"
              % (n, c["attaques_live"]))
        print("     E1 SEQUENCE  PORT (%d coups) = %s" % (len(sp), [a for _t, a in sp]))
        print("                  NATIF(%d coups) = %s   profils=%s"
              % (len(sn), [a for _t, a in sn], c["natif"]["profils"]))
        print("     E1 total     PORT=%s  NATIF=%s   (ported=%s, compteur port=%s -> %s, rc=%s)"
              % (c["port"]["total"], c["natif"]["total"], c["port"]["ported"],
                 c["port"]["compteur_avant"], c["port"]["compteur_apres"], c["natif"]["rc"]))
        # ATTRIBUTION EXACTE DES TIRAGES. Le natif joue, APRES le cast, la triggered
        # `1319 LegacyOfCombat` (passif de Kariyan, NON PORTEE) : ses coups sont dans le MEME appel
        # `act`, donc dans le MEME delta MT. La famille ATTACK consomme 2 tirages par coup a
        # cc = 0, d'ou l'identite `tirages_natif == 2 x <tous les coups>` -- verifiee ici plutot
        # que supposee. Le port, lui, ne joue que les coups de 1191.
        coups_hors = c["natif"]["coups_tous"] - len(sn)
        att = TIRAGES_PAR_COUP * c["natif"]["coups_tous"]
        print("     E2 TIRAGES genrand_int32 : PORT=%s (= 2 x %d coups 1191)  NATIF=%s"
              % (c["tirages_port"], len(sp), c["tirages_natif"]))
        print("        coups natifs TOUS = %d sur les cibles %s -> 2 x %d = %d attendu ; "
              "hors 1191 = %d (triggered 1319 LegacyOfCombat, NON PORTEE)"
              % (c["natif"]["coups_tous"], c["natif"]["cibles_tous"],
                 c["natif"]["coups_tous"], att, coups_hors))
        print("     effet pose  : %s" % (c["port"]["posed"],))
        print("     -- contre-epreuves (hors-ligne, MEME capture, MEME MT) --")
        for nom, r in (c.get("ab") or {}).items():
            marque = "== REF" if nom != "ref" and r["seq"] == (c["ab"] or {})["ref"]["seq"] else ""
            print("        %-20s total=%-8s tirages=%-4s %s" % (nom, r["total"], r["tirages"], marque))
        if c["port"]["compteur_avant"] != n:
            print("     !! le compteur SEEDE du port (%s) differe du LIVE (%s) -- seed KO"
                  % (c["port"]["compteur_avant"], n))
            ok = False
        if sp != sn or not sn:
            ok = False
        if c["tirages_port"] != TIRAGES_PAR_COUP * len(sp):
            print("     !! le port ne consomme pas 2 tirages par coup")
            ok = False
        if c["tirages_natif"] != att:
            print("     !! l'attribution des tirages natifs ne boucle pas (%s != %s)"
                  % (c["tirages_natif"], att))
            ok = False
        ref = (c.get("ab") or {}).get("ref")
        if ref and ref["seq"] != sn:
            print("     !! l'arbre du module ne rend pas la sequence native")
            ok = False
        if n > 0:
            # CHAQUE contre-epreuve DOIT diverger : sinon la lecture qu'elle retire n'est pas mesuree.
            for nom in ("sans_effet", "ordre_inverse", "sans_ability_type"):
                r = (c.get("ab") or {}).get(nom)
                if r and r["seq"] == sn:
                    print("     !! contre-epreuve %s NON discriminante (== natif)" % nom)
                    ok = False
            sans = (c.get("ab") or {}).get("sans_effet")
            if sans and sans["total"]:
                print("     E3 RATIO ref/sans_effet = %.4f   attendu 1 + %s x %s%% = %.4f"
                      % (ref["total"] / float(sans["total"]), n, extra_pct,
                         1.0 + (n * extra_pct) / 100.0))
        if n == 0:
            base = c["natif"]["total"]
    if base is None:
        print("  !! aucun cast a compteur=0 -- le TEMOIN de reference manque")
    regimes = sorted({c["compteur_live"] for c in m["casts"]})
    print("  REGIMES DE COMPTEUR ATTEINTS : %s" % (regimes,))
    if len(regimes) < 2:
        print("  !! REGIME DEGENERE : un seul compteur mesure, l'accord ne prouve pas l'effet")
        ok = False
    return ok


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Confrontation live du port COMBAT de 1191")
    ap.add_argument("--seed", type=int, default=50901)
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--regimes", default="nominal,armure")
    ap.add_argument("--tours", type=int, default=6)
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--garder", action="store_true")
    a = ap.parse_args(argv)

    import gameconfig as GC
    from engine.entities.effects.magnitude import ability_var
    # `extraDmgPct` au niveau du caster : LU de la config, jamais code en dur.
    lvl = 50
    extra = int(ability_var("MartialInspiration", "extraDmgPct", lvl) or 0)
    print("config MartialInspiration : nrOfHits=%s damageProfile=%s extraDmgPct[lvl %d]=%s"
          % (((GC.ability("MartialInspiration") or {}).get("constants") or {}).get("nrOfHits"),
             ((GC.ability("MartialInspiration") or {}).get("constants") or {}).get("damageProfile"),
             lvl, extra))

    sid = _sid()
    base_sf = a.state_file or str(Path(PYDIR).parents[1] / "logs"
                                  / ("probe509_%d.json" % os.getpid()))
    tout_ok = True
    for regime in [r.strip() for r in a.regimes.split(",") if r.strip()]:
        sf = base_sf.replace(".json", "_%s.json" % regime)
        m = mesure(sid, sf, a.seed, a.board, regime, a.tours, garder=a.garder)
        if m is None:
            print("[509:%s] BUILD KO" % regime)
            tout_ok = False
            continue
        tout_ok = rapport(m, extra) and tout_ok
    print("[509] VERDICT : %s" % ("OK" if tout_ok else "DIVERGENCE"))
    return 0 if tout_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
