#!/usr/bin/env python
"""probe_442_steppable_targeting -- la regle de ciblage `TargetIsNotSteppable` (bit 51, le DECOY).

CE QUE CE PROBE MESURE
----------------------
`IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason` (surcharge 7 arguments), juste
apres `TargetIsTargetable` et AVANT les regles `TargetHasNTiles` (donc avant le volet PORTEE) :

    if ((rules >> 0x33 & 1) == 0) {                      // bit 51 NON pose
        if (TargetingOptions.get_IsUnitTargeting(options)) {
            if ((rules & 0x100000) == 0) goto TEST;      // !AllowSteppableUnit (bit 20)
        }
    } else {
    TEST:
        if (TileExtensions.HasSteppableUnit(puVar12, state)) -> broken(0x8000000000000);
    }

DEUX ARMEMENTS, et le second est le gisement : le bit 51 n'a qu'**UN** porteur au registre
(1011 `TunnelingHorror`, TILE-targeting), tandis que **83** abilities l'ARMENT par
`get_IsUnitTargeting` -- qui n'est pas un bit a lui mais l'ABSENCE des bits 6/44/46, donc VRAI PAR
DEFAUT. L'ATTAQUE NORMALE est dans ce cas (preset `0x4002`) : **on ne peut pas attaquer normalement
une unite `Steppable`**.

LA DEGRADATION EST PERMISSIVE : sans la regle, le port ACCEPTE des casts que le natif REFUSE. Un
accord sur un cast ACCEPTE ne prouve donc RIEN. Ce probe est construit autour du REFUS.

QUI ECRIT L'ETAT QUE LA REGLE LIT -- ET C'EST LA LEcON DE #436
--------------------------------------------------------------
`Steppable` est un **TRAIT** (`UnitTrait.Steppable` = 0x1b), pas un effet : personne n'a a
l'« ecrire » au sens ou le TAUNT devait ecrire sa liste. Il arrive par le substrat de traits deja
porte, et par DEUX canaux distincts que ce probe verifie separement :

  * unite SPAWNEE par le port           -> `build_decoy_context` / `build_summon_context`, seedes du
                                           `traits` gameconfig ;
  * etat RECHARGE depuis un snapshot    -> `snapshot._load_unit_traits`, qui seede depuis
                                           `combatSnapshot.units[].traits` (#264) -- une MESURE de
                                           `UnitExtensions$$HasTrait`, pas une reconstruction.
C'est le second canal qui porte la mesure LIVE ici, et l'etage A l'atteste au lieu de le supposer.

LE MONTAGE, ET POURQUOI CELUI-LA
--------------------------------
27 unites portent `Steppable` au gameconfig : 25 npc (loot, power-ups, `astarNpc1HaywireMine`,
`genesDecoy`) et **2 summons** -- `genesSmnDecoy` et `astarSmnHaywireMine`. Le premier a un
summoner au POOL et une ability ACTIVE portee qui le pose a volonte :

    genesPrimus  --CultDemagogue(1179)-->  un necroWarden  =>  N decoys ALLIES autour de la CIBLE

Les decoys sont ALLIES du caster, donc ENNEMIS du necroWarden -- qui les a a d=1. Son ATTAQUE
NORMALE arme la regle (preset `0x4002`, aucun bit de domaine, pas de bit 20) : le natif doit rendre
`0x8000000000000` sur un decoy, et `0x0` sur une vraie unite ennemie.

⚠ L'ORDRE DE LA CASCADE FAIT LE TRAVAIL : la regle 51 precede le volet PORTEE. Un decoy hors portee
rendrait quand meme `0x8000000000000` -- on ne peut donc pas confondre les deux refus.

QUATRE ETAGES, mesures separement (jamais un scalaire global)
------------------------------------------------------------
  A. SUBSTRAT (live -> offline) -- l'etat RECHARGE apres le cast natif porte-t-il `Steppable` sur
     les decoys ? Sans ce canal la regle serait VERTE ET VIDE, exactement le mode de defaillance
     de #436.
  B. LA REGLE (live) -- accord natif/port du gate d'attaque normale du necroWarden, cible par
     cible, avec la colonne `portAvant` = le port DESARME par le bit 20 (ce que `master` rendait,
     la regle etant gatee par ce seul bit).
  C. LE DESARMEMENT `AllowSteppableUnit` (bit 20) -- offline : il doit lever le refus sur la voie
     unit-targeting. NON CONFRONTE au natif (0 porteur du bit au registre).
  D. LA VOIE DU BIT 51 (offline) -- une ability qui POSE le bit refuse meme AVEC le bit 20 (la
     branche `else` du natif court-circuite le test du desarmement), et elle refuse aussi en mode
     TILE-targeting sur la TUILE du decoy -- c'est le regime de 1011 `TunnelingHorror`.
     CONFRONTE AU NATIF depuis #447 (`probe_447_bit51_native.py`) : la greffe de l'ACTIVE 1011 sur
     une unite du pool amene le bit en bataille, et la meme tuile de decoy est refusee par 51 alors
     que 1166 (bit 12 SANS bit 51) l'ACCEPTE. Seul le bit 20 reste offline (0 porteur au registre).

Usage (depuis scripts/python, session Frida chaude) :
    python probe_442_steppable_targeting.py
    # GENERALISATION : autre board/seed, autre roster adverse.
    python probe_442_steppable_targeting.py --seed 31337 --board C4_09 \
        --a-units "deathBlightlord,deathBlightlord,necroWarden,necroWarden"

ASCII only (cp1252). Dispose SES runners (jamais ceux des autres).
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace as _replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo                                                        # noqa: E402
from rl_collect_batch import _resolve_session, _rpc                  # noqa: E402

import probe_247_splash_targeting as P247                            # noqa: E402
import probe_436_taunt_targeting as P436                             # noqa: E402

from engine.entities.pathfinding.board import Board                  # noqa: E402
from engine.entities.traits.unit_trait import UnitTrait              # noqa: E402
from engine.runner.abilities.handler import ABILITY_CLASSES          # noqa: E402
from engine.runner.abilities.targeting import (                      # noqa: E402
    NORMAL_ATTACK_TARGETING_OPTIONS, TargetingOptions, _NormalAttackTargeting,
    _unit_traits, get_invalid_target_reason, has_steppable_unit)
from engine.runner.abilities.targeting_rule import TargetingRule as TR   # noqa: E402
from engine.runner.snapshot import load_state                        # noqa: E402

CULT_DEMAGOGUE = 1179                 # `CultDemagogue`, porteur `genesPrimus` (HERO, au pool)
NORMAL_ATTACK = 69                    # `Loki_NormalAttack` -- l'id CONCRET, jamais l'abstrait 17
DECOY_VIS = "genesSmnDecoy"
P_UNITS = ["genesPrimus", "genesMagus"]
A_UNITS_DEFAUT = "necroWarden,necroWarden,necroWarden,necroWarden"
STEPPABLE_RULE = int(TR.TargetIsNotSteppable)


class _NormalAttackAllowingSteppable(_NormalAttackTargeting):
    """Etage C -- le masque de l'attaque normale + `AllowSteppableUnit` (bit 20). C'est AUSSI la
    baseline `portAvant` : la regle portee par #442 est gatee par ce seul bit sur la voie
    unit-targeting, donc le poser rend EXACTEMENT ce que `master` rendait."""
    TARGETING_OPTIONS = _replace(
        NORMAL_ATTACK_TARGETING_OPTIONS,
        rules=int(NORMAL_ATTACK_TARGETING_OPTIONS.rules) | int(TR.AllowSteppableUnit))


def _allowing_steppable(klass):
    """Le meme contrefactuel, pour une ability du registre : sa classe avec le bit 20 OR-e sur son
    masque. On ne touche QU'A CE CHAMP -- une ligne que ce seul bit fait basculer prouve que c'est
    bien lui qui desarme, et pas un effet de bord du reste du port."""
    base = klass.TARGETING_OPTIONS

    class _V(klass):                                                  # type: ignore[misc, valid-type]
        __slots__ = ()
        TARGETING_OPTIONS = _replace(base, rules=int(base.rules) | int(TR.AllowSteppableUnit))
    return _V()


class _BitPoseUnitTargeting:
    """Etage D -- une ability qui POSE le bit 51 **et** le bit 20. Le natif teste le bit 51 EN
    PREMIER et saute directement au predicat (`else: goto TEST`) : le desarmement ne s'applique
    qu'a la voie `get_IsUnitTargeting`. Contrefactuel du CHAMP, pas du code."""
    TARGETING_OPTIONS = TargetingOptions(
        rules=int(TR.TargetIsEnemy) | int(TR.TargetIsNotSteppable) | int(TR.AllowSteppableUnit))
    ABILITY_ID = None

    def get_dynamic_invalid_target_reason(self, state, caster_id, target_id) -> int:
        return 0

    def get_dynamic_invalid_caster_reason(self, state, caster_id) -> int:
        return 0


class _BitPoseTileTargeting:
    """Etage D -- le regime de 1011 `TunnelingHorror` : TILE-targeting (bit 6) + bit 51. La cible
    est une TUILE, `HasSteppableUnit` la resout en son OCCUPANT. `AllowUnwalkableTargetTile` est
    pose pour isoler la regle 51 du refus `ValidRequest` de la tete `TargetIsTile`."""
    TARGETING_OPTIONS = TargetingOptions(
        rules=int(TR.TargetIsTile) | int(TR.TargetIsNotSteppable)
        | int(TR.AllowUnwalkableTargetTile))
    ABILITY_ID = None

    def get_dynamic_invalid_target_reason(self, state, caster_id, target_id) -> int:
        return 0

    def get_dynamic_invalid_caster_reason(self, state, caster_id) -> int:
        return 0


def _capture(sid, rid):
    dv = P247._dv(sid, rid)
    ob = P247._r(sid, "observeBattle", {"runnerId": rid}, 60)
    snap = P247._r(sid, "combatSnapshot", {"runnerId": rid}, 60)
    bg = P247._r(sid, "boardGraph", {"runnerId": rid}, 90)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        raise RuntimeError("boardGraph indisponible")
    return dv, (dv, ob, snap, bg)


def _mk_state(payloads):
    dv, ob, snap, bg = payloads
    return load_state(dv, ob, snap, board=Board(bg["tiles"], adjacency="native_sym"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--a-units", default=A_UNITS_DEFAUT, help="roster ADVERSE")
    ap.add_argument("--p-units", default=",".join(P_UNITS),
                    help="roster JOUEUR (le porteur de CultDemagogue en sort)")
    ap.add_argument("--victim-vis", default=None,
                    help="visualId de la CIBLE du cast -- c'est elle qui aura les decoys autour "
                         "d'elle, et c'est elle qui sert d'ATTAQUANT a l'etage B")
    ap.add_argument("--extra-ability", type=int, action="append", default=[],
                    help="ActiveAbilityType SUPPLEMENTAIRE de l'ATTAQUANT a mesurer "
                         "(generalisation : une ability ACTIVE, masque different de celui de "
                         "l'attaque normale)")
    a = ap.parse_args(argv)

    sid = _resolve_session()
    p_units = [x for x in a.p_units.split(",") if x]
    rid, state_file = P436._build(sid, a.seed, a.board, p_units, a.a_units)
    print("[build] runner=%d board=%s seed=%s p_units=%s a_units=%s"
          % (rid, a.board, a.seed, ",".join(p_units), a.a_units))
    try:
        for _ in range(P247.TOURS_DE_CHAUFFE):
            P247._act(sid, rid, {"kind": "endturn"}, 60)

        # GEOMETRIE. `CultDemagogue` cible un ENNEMI a `constants.range` = 2 et pose ses decoys sur
        # les tuiles libres <= 2 hex de la CIBLE -- donc au CONTACT de celle-ci. On amene le porteur
        # au contact : la cible aura ses decoys adjacents, et son attaque normale (clampee en melee
        # parce qu'elle est RANGED et adjacente) les aura a portee.
        victim_id = P436._make_adjacent(sid, rid, "genesPrimus", only_vis=a.victim_vis)
        if victim_id is None:
            print("[FAIL] impossible d'amener genesPrimus au contact de %s"
                  % (a.victim_vis or "un ennemi"))
            return 2
        P247._give_turn_to(sid, rid, "genesPrimus")
        dv_pre, pre_payloads = _capture(sid, rid)
        primus = P247._by_vis(dv_pre, "genesPrimus")
        vic = next((u for u in dv_pre["units"]
                    if int(u["id"]) == victim_id and u.get("alive")), None)
        if primus is None or vic is None:
            print("[FAIL] caster/cible absents apres montage")
            return 2
        cid = int(primus["id"])
        print("[geometrie] caster u%d(genesPrimus) ; cible u%d(%s) d=%d"
              % (cid, victim_id, vic.get("visualId"),
                 hexgeo.distance(P247._pos(primus), P247._pos(vic))))

        # BASELINE NATIVE, AVANT tout decoy : la victime accepte-t-elle ses cibles ? C'est la
        # preuve que le refus mesure ensuite vient bien des decoys et de rien d'autre.
        st_pre = _mk_state(pre_payloads)
        nat_avant = {}
        for u in dv_pre["units"]:
            if not u.get("alive"):
                continue
            tid = int(u["id"])
            nat = P247._nat(sid, rid, victim_id, NORMAL_ATTACK, tid)
            nat_avant[tid] = P247._hexval((nat or {}).get("targetReason") or {})
        print("[baseline natif AVANT cast] %s"
              % {k: (None if v is None else hex(v)) for k, v in sorted(nat_avant.items())})
        # ⚠ CE COMPTE N'EST PAS ATTENDU NUL, et l'observer l'a prouve : la passive `Ambush_Summon`
        # des genestealers pose des decoys A LA MORT de tout porteur du trait `Ambush`, et les
        # endturns du montage suffisent a en faire apparaitre. MESURE (seed 777 / MC1_67) : UN decoy
        # preexistant, que le natif refusait DEJA en `0x8000000000000` -- a d=10, donc AVANT le volet
        # portee, ce qui confirme in vivo la place de la regle 51 dans la cascade.
        n_step_pre = sum(1 for u in dv_pre["units"]
                         if u.get("alive") and has_steppable_unit(st_pre, int(u["id"])))
        print("[baseline substrat] unites Steppable AVANT cast : %d" % n_step_pre)

        # ---------------------------------------------------------------- LE CAST NATIF
        act = {"kind": "ability", "casterId": cid, "abilityType": CULT_DEMAGOGUE,
               "targetId": victim_id}
        r = P247._act(sid, rid, act, 120)
        acts = ((r or {}).get("actions") or [{}])[0]
        print("\n[cast natif] CultDemagogue u%d -> u%d : mutated=%s"
              % (cid, victim_id, acts.get("mutated")))
        if not acts.get("mutated"):
            print("[FAIL] le cast natif n'a pas mute l'etat -> pas de decoy, rien a mesurer")
            return 2

        # ------------------------------------------- #506 : L'ATTAQUANT DE MESURE, ET SA GEOMETRIE
        # L'etage B n'a de sens que si l'attaquant a AU MOINS UN DECOY A PORTEE de son attaque
        # normale : c'est la seule facon d'avoir une ligne ou le port DESARME (bit 20) rende `0x0`,
        # donc ou le contrefactuel « ce que master rendait » soit un ACCEPT. Sans elle, le port
        # desarme tombe sur le refus de PORTEE (`0x8000000`) et l'etage B ne conclut plus rien --
        # l'accord natif/port, lui, reste vrai, parce que la regle 51 PRECEDE le volet portee.
        #
        # Le montage prenait la VICTIME du cast (qui a les decoys au contact par construction), et
        # retombait sinon sur `foes[0]`, choisi par l'ordre de `decisionView`. Depuis `c4be3896`
        # (#419-r6, le defaut passe a << equiper >>) les tours AI immediats des Neophytes TUENT la
        # victime, et `foes[0]` est un ennemi quelconque, hors de portee de tout decoy : MESURE sur
        # `master` nu, les 5 decoys rendaient `portDesarme = 0x8000000` au lieu de `0x0`.
        #
        # On ne subit plus ce tirage : on prend l'ennemi vivant le PLUS PROCHE d'un decoy et on
        # l'AMENE au contact (runner `--no-ai`, `applyAction` ne verifie pas la propriete du
        # `unitId` -- meme geste que `_make_adjacent`). La geometrie de spawn n'est jamais une
        # excuse ; si l'approche echoue, l'etage B le DIT au lieu de rendre un accord vide.
        dv_mid = P247._dv(sid, rid)
        decoys_mid = [u for u in dv_mid["units"]
                      if u.get("alive") and u.get("visualId") == DECOY_VIS]
        foes_mid = [u for u in dv_mid["units"]
                    if u.get("alive") and u.get("owner") != primus.get("owner")]
        if not decoys_mid or not foes_mid:
            print("[FAIL] apres le cast : %d decoy(s) vivant(s), %d ennemi(s) vivant(s)"
                  % (len(decoys_mid), len(foes_mid)))
            return 2

        def _d_min(u):
            return min(hexgeo.distance(P247._pos(u), P247._pos(x)) for x in decoys_mid)

        atk_u = (next((u for u in foes_mid if int(u["id"]) == victim_id), None)
                 or min(foes_mid, key=lambda f: (_d_min(f), int(f["id"]))))
        aid_atk = int(atk_u["id"])
        print("[etage B] attaquant u%d(%s) %s ; decoy le plus proche a d=%d"
              % (aid_atk, atk_u.get("visualId"),
                 "= la VICTIME du cast" if aid_atk == victim_id else "(la victime n'a pas survecu)",
                 _d_min(atk_u)))
        for _ in range(6):
            dnow = P247._dv(sid, rid)
            a2 = next((x for x in dnow["units"] if int(x["id"]) == aid_atk and x.get("alive")), None)
            dec2 = [x for x in dnow["units"] if x.get("alive") and x.get("visualId") == DECOY_VIS]
            if a2 is None or not dec2:
                break
            goal = min(dec2, key=lambda x: hexgeo.distance(P247._pos(a2), P247._pos(x)))
            if hexgeo.distance(P247._pos(a2), P247._pos(goal)) <= 1:
                break
            if not P247._step_toward(sid, rid, aid_atk, P247._pos(goal), 1):
                break

        dv_post, post_payloads = _capture(sid, rid)
        st = _mk_state(post_payloads)

        # ---------------------------------------------------------------- ETAGE A : le SUBSTRAT
        print("\n=== ETAGE A -- SUBSTRAT (l'etat RECHARGE porte-t-il le trait ?)")
        decoys, step_ids = [], []
        for u in dv_post["units"]:
            if not u.get("alive"):
                continue
            tid = int(u["id"])
            tr = _unit_traits(st, tid) or ()
            if u.get("visualId") == DECOY_VIS:
                decoys.append(tid)
            if UnitTrait.Steppable.name in tr:
                step_ids.append(tid)
        print("  decoys `%s` vivants apres le cast natif : %d %s"
              % (DECOY_VIS, len(decoys), decoys))
        print("  entites dont `_unit_traits` porte `Steppable` : %d %s" % (len(step_ids), step_ids))
        print("  `has_steppable_unit` (mirror `TileExtensions$$HasSteppableUnit`) : %s"
              % {t: has_steppable_unit(st, t) for t in decoys})
        okA = bool(decoys) and all(t in step_ids for t in decoys)
        print("  [A] %s%s" % ("PASS" if okA else "FAIL",
                              "" if okA else "  <- le canal de substrat NE PUBLIE PAS le trait : "
                                             "la regle serait VERTE ET VIDE"))

        # ---------------------------------------------------------------- ETAGE B : la REGLE
        # Le CASTER de mesure est l'ennemi choisi et AMENE AU CONTACT ci-dessus (#506).
        atk = next((u for u in dv_post["units"]
                    if u.get("alive") and int(u["id"]) == aid_atk), None)
        if atk is None or not decoys:
            print("[FAIL] pas d'attaquant vivant ou pas de decoy -> rien a mesurer")
            return 2
        apos = P247._pos(atk)
        d_atk = min(hexgeo.distance(apos, P247._pos(u)) for u in dv_post["units"]
                    if u.get("alive") and int(u["id"]) in set(decoys))
        print("[etage B] u%d(%s) @%s ; decoy le plus proche APRES approche : d=%d"
              % (aid_atk, atk.get("visualId"), apos, d_atk))
        # UNE PAIRE (port, port DESARME) PAR ABILITY mesuree. L'attaque normale d'abord (le canal
        # le plus large : 83 abilities arment la regle par le meme chemin), puis les
        # `--extra-ability` de generalisation -- un masque DIFFERENT, lu au ctor de SA classe.
        probes = [(NORMAL_ATTACK, _NormalAttackTargeting(), _NormalAttackAllowingSteppable())]
        for xa in a.extra_ability:
            k = ABILITY_CLASSES.get(int(xa))
            if k is None or getattr(k, "TARGETING_OPTIONS", None) is None:
                print("[skip] ability %d absente du registre ou sans masque -> non mesurable" % xa)
                continue
            probes.append((int(xa), k(), _allowing_steppable(k)))
        okB = okC = True
        rows_par_aid = {}
        for aid, pport, pdes in probes:
            print("\n=== ETAGE B -- la REGLE (natif vs port, ability %d de u%d %s)"
                  % (aid, aid_atk, atk.get("visualId")))
            print("  %-24s %-5s %-3s %-16s %-24s %-16s %-16s %-16s"
                  % ("cible", "id", "d", "natif", "regle natif", "port", "natAvant",
                     "portAvant(b20)"))
            n_agree = n_rows = n_refus51 = n_gain = cf_desarme = n_accept = 0
            rows = []
            for u in dv_post["units"]:
                if not u.get("alive"):
                    continue
                tid = int(u["id"])
                nat = P247._nat(sid, rid, aid_atk, aid, tid)
                tr = (nat or {}).get("targetReason") or {}
                nv = P247._hexval(tr)
                pv = int(get_invalid_target_reason(st, aid_atk, tid, pport))
                dv_ = int(get_invalid_target_reason(st, aid_atk, tid, pdes))
                na = nat_avant.get(tid) if aid == NORMAL_ATTACK else None
                n_rows += 1
                n_agree += 1 if nv == pv else 0
                if nv == STEPPABLE_RULE:
                    n_refus51 += 1
                    if dv_ == 0:
                        n_gain += 1
                if nv == 0:
                    n_accept += 1
                if dv_ != pv:
                    cf_desarme += 1
                print("  %-24s %-5d %-3d %-16s %-24s %-16s %-16s %-16s %s"
                      % ((("SELF " if tid == aid_atk else "") + str(u.get("visualId")))[:24], tid,
                         hexgeo.distance(apos, P247._pos(u)),
                         "-" if nv is None else hex(nv),
                         ",".join(tr.get("reasons") or [])[:24] or "-",
                         hex(pv), "-" if na is None else hex(na), hex(dv_),
                         "OK" if nv == pv else "MISMATCH"))
                rows.append({"target": tid, "vis": u.get("visualId"), "nat": nv, "port": pv,
                             "natAvant": na, "portDesarme": dv_})
            ok = (n_agree == n_rows and n_refus51 > 0 and n_gain > 0 and n_accept > 0)
            print("  [bilan %d] accord %d/%d ; refus 0x%x du natif : %d ; dont le port DESARME "
                  "accepte (0x0) : %d ; lignes acceptees : %d"
                  % (aid, n_agree, n_rows, STEPPABLE_RULE, n_refus51, n_gain, n_accept))
            print("  [B %d] %s" % (aid, "PASS" if ok else "FAIL"))
            print("  [C %d] desarmement bit 20 : %d/%d ligne(s) basculee(s) -> %s   "
                  "(NON CONFRONTE au natif : 0 porteur du bit au registre)"
                  % (aid, cf_desarme, n_rows, "PASS" if cf_desarme > 0 else "FAIL"))
            okB = okB and ok
            okC = okC and (cf_desarme > 0)
            rows_par_aid[aid] = rows
        rows = rows_par_aid[NORMAL_ATTACK]

        # ---------------------------------------------------------------- ETAGE D : la voie du BIT
        print("\n=== ETAGE D -- la voie du BIT 51 (offline ; regime de 1011 `TunnelingHorror`)")
        pbit = _BitPoseUnitTargeting()
        ptile = _BitPoseTileTargeting()
        board = st.board
        d_unit = d_tile = 0
        bit_rows = []
        for tid in decoys:
            v_unit = int(get_invalid_target_reason(st, aid_atk, tid, pbit))
            pos = next((P247._pos(u) for u in dv_post["units"] if int(u["id"]) == tid), None)
            tile_id = board.id_at(pos[0], pos[1]) if (board is not None and pos) else None
            v_tile = (int(get_invalid_target_reason(st, aid_atk, tile_id, ptile))
                      if tile_id is not None else None)
            print("  decoy u%-5d bit51+bit20 (unit-targeting) -> %s ; bit51+bit6 sur SA TUILE t%s "
                  "-> %s" % (tid, hex(v_unit), tile_id,
                             "-" if v_tile is None else hex(v_tile)))
            d_unit += 1 if v_unit == STEPPABLE_RULE else 0
            d_tile += 1 if v_tile == STEPPABLE_RULE else 0
            bit_rows.append({"decoy": tid, "tile": tile_id, "bit51_unit": v_unit,
                             "bit51_tile": v_tile})
        okD = bool(decoys) and d_unit == len(decoys) and d_tile == len(decoys)
        print("  [D] %s -- le bit 51 refuse MALGRE le bit 20 (%d/%d) et en mode TUILE (%d/%d). "
              "NON CONFRONTE au natif : le seul porteur du bit, 1011 `TunnelingHorror`, n'a que "
              "des npc et le summon d'ENVIRONNEMENT `necroSmnDestroyer` "
              "(`EnvFactionSummons:Necrons`, pose par le BOARD, aucun summoner d'unite)."
              % ("PASS" if okD else "FAIL", d_unit, len(decoys), d_tile, len(decoys)))

        allok = okA and okB and okC and okD
        print("\n[VERDICT] %s" % ("PASS" if allok else "FAIL"))
        print("[RAW] " + json.dumps({"caster": cid, "victim": victim_id, "attacker": aid_atk,
                                     "decoys": decoys, "steppable": step_ids, "rows": rows,
                                     "rows_par_ability": {str(k2): v
                                                          for k2, v in rows_par_aid.items()},
                                     "bit51": bit_rows, "steppableAvantCast": n_step_pre}))
        return 0 if allok else 1
    finally:
        try:
            _rpc(sid, "disposeRunner", [{"runnerId": rid}], timeout=30)
            state_file.unlink(missing_ok=True)
            print("[cleanup] runner %d dispose" % rid)
        except Exception as e:                                       # noqa: BLE001
            print("[cleanup] dispose KO: %s" % e)


if __name__ == "__main__":
    sys.exit(main())
