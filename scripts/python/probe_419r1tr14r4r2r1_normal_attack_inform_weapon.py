#!/usr/bin/env python
"""Probe #419-r1-tr14-r4-r2-r1 -- CONFRONTATION LIVE d'`InformWeapon` sur l'ATTAQUE NORMALE.

LA QUESTION BINAIRE, ET SA REPONSE MESUREE
------------------------------------------
Le flux natif porte-t-il `Attack_Weapon_*` quand une unite fait une ATTAQUE NORMALE ? **OUI.**
Mesure du 2026-08-06 (MC1_67, seed 41902, session Frida 1) : deux attaques normales, **4** lignes
`Tag=Attack_Weapon_*` dans `replayOutputStream`, chacune sous un

    Group=Ability_Power Entity=<caster> Source=Loki_NormalAttack InitialTarget=<cible>
        Action=Info Entity=NO_ENTITY
            Tag=Attack_Weapon_IsMelee:1
            Tag=Attack_Weapon_DamageProfile:14

⚠ POURQUOI `probe_477r15a_stream_conformance.py` EST VERT SANS RIEN DIRE DE CELA. Il ne compare
QUE le groupe racine `System_GameSetup` (`groupe_racine(flux, "System_GameSetup")`) -- le
DEPLOIEMENT. Ces lignes-ci vivent dans un groupe racine `User_UseAbility`, jamais visite. Son vert
est donc HONNETE MAIS MUET : c'est un TROU DE PERIMETRE de l'oracle, pas un accord. Le present
probe est ce qui couvre ce morceau-la.

CE QUI REND LA MESURE HONNETE -- l'entree du port ne vient PAS du flux
---------------------------------------------------------------------
Le port ne lit jamais `Attack_Weapon_*` pour se construire. Sa chaine est :

    visualId (observeBattle) + adjacence/distance (boardGraph + positions)
      -> `battle_query.get_attack_weapon_for_default_normal_attack`  (GAMECONFIG)
      -> `InformWeapon.from_weapon(weapon)`  == `DSLBehaviors$$InformWeapon(weapon, useSpecial)`
      -> `inform_ops.get_inform_weapon_tags` -> `inform_ops.inform`  == `InformOperation$$Execute`

LE DISCRIMINANT, ET SON TEMOIN
------------------------------
`isMelee` n'est PAS un litteral sur cette voie : il est DERIVE de l'arme choisie, donc de la
DISTANCE. Le corpus porte donc trois montages, choisis pour que DEUX pieges soient fermes :

  * `IsMelee` DIFFERE (1 vs 0)               -> un port a constante echoue ;
  * deux porteurs de MEME `DamageProfile` (0 = Physical) ont des `IsMelee` OPPOSES
    -> un port qui deduirait `isMelee` DU PROFIL echoue aussi. Sans ce second temoin, le premier
       ne separerait pas les deux fautes.

ASCII only (cp1252).
Usage: python probe_419r1tr14r4r2r1_normal_attack_inform_weapon.py [--seed N] [--contre-epreuve]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo  # noqa: E402
import stream_events as SE  # noqa: E402
from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
from engine.entities.pathfinding.board import Board  # noqa: E402
from engine.runner.abilities.behaviours.combat import InformWeapon  # noqa: E402
from engine.services.battle_query import (get_attack_weapon_for_default_normal_attack,  # noqa: E402
                                          weapon_is_melee)
from engine.services.custom_normal_attack import (custom_normal_attack,  # noqa: E402
                                                  inform_weapon_use_special)
from engine.streams.dispatcher import StreamDispatcher
from engine.streams.stream_cache import StreamCache  # noqa: E402
from engine.streams.group_type import GroupType  # noqa: E402
from engine.streams.inform_ops import inform  # noqa: E402
from engine.streams.tag_key import TagKey  # noqa: E402

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
BOARD = "MC1_67"

#: (visualId, distance VOULUE, charge). Le corpus est choisi pour que TROIS pieges soient fermes :
#:   * `astraBullgryn` et `admecDestroyer` partagent le profil `Physical` (0) avec des `IsMelee`
#:     OPPOSES -> `isMelee` ne peut pas se deriver du profil ;
#:   * `admecDestroyer` a DEUX armes -> `isMelee` depend de la DISTANCE, pas de l'unite ;
#:   * `tyranDeathleaper` (passif `FeederTendrils`) attaque EN CHARGE -> c'est le SEUL regime du
#:     corpus ou le natif pose `Attack_Weapon_Use_Special`, et il n'avait JAMAIS ete confronte.
#: `charge` = le caster est deplace AU CONTACT de la cible avant d'attaquer (`UpdateCharging`).
#: `dist` = ou la CIBLE est posee ; `dist_att` = la distance AU MOMENT de l'attaque (elle differe
#: quand le caster charge : il vient au contact). En mode LIVE, `dist_att` est MESUREE et remplace
#: cette valeur ; elle ne sert qu'a la contre-epreuve hors ligne.
PORTEURS = [
    {"vis": "deathBlightlord", "dist": 1, "dist_att": 1, "nom": "deathBlightlord@1",
     "charge": False},
    {"vis": "astraBullgryn", "dist": 1, "dist_att": 1, "nom": "astraBullgryn@1", "charge": False},
    {"vis": "admecDestroyer", "dist": 3, "dist_att": 3, "nom": "admecDestroyer@3",
     "charge": False},
    {"vis": "tyranDeathleaper", "dist": 3, "dist_att": 1, "nom": "tyranDeathleaper@charge",
     "charge": True},
]

#: MESURE LIVE du 2026-08-06 (runner MC1_67, seed 41902, session Frida 1) -- figee pour que la
#: CONTRE-EPREUVE s'exerce sans re-monter un runner. `Use_Special` est ABSENTE des trois premiers
#: (PREDICTION `useSpecial == 0` du foyer `ALoki_NormalAttackAbility$$ExecuteBehaviour`, verifiee et
#: non contournee) et PRESENTE a `1` sur le quatrieme.
MESURE_NATIVE = {
    "deathBlightlord@1": {"Attack_Weapon_IsMelee": 1, "Attack_Weapon_DamageProfile": 14},
    "astraBullgryn@1": {"Attack_Weapon_IsMelee": 1, "Attack_Weapon_DamageProfile": 0},
    "admecDestroyer@3": {"Attack_Weapon_IsMelee": 0, "Attack_Weapon_DamageProfile": 0},
    "tyranDeathleaper@charge": {"Attack_Weapon_IsMelee": 1, "Attack_Weapon_DamageProfile": 22,
                                "Attack_Weapon_Use_Special": 1},
}


def _r(sid, method, body, t=120):
    return (_rpc(sid, method, [body], timeout=t).get("result") or {})


def _tags(ev) -> dict:
    try:
        return json.loads(ev.get("tags") or "{}")
    except Exception:
        return {}


def _cascade(r) -> list:
    out = list(r.get("cascade") or [])
    for a in (r.get("actions") or []):
        out += list(a.get("events") or [])
    return out


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row"))


def build(seed: int):
    sf = ROOT / "logs" / "runners" / f"iw-na-{uuid.uuid4().hex[:8]}.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(sf),
         "--board", BOARD, "--roster", "1", "--record-replay",
         "--p-units", ",".join(p["vis"] for p in PORTEURS),
         "--a-units", "necroWarden,necroWarden,necroWarden",
         "--hp-target", "400000", "--hp-player", "400000"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not sf.exists():
        print(f"[iwna] build KO: {(proc.stderr or proc.stdout or '')[-400:]}")
        return None, None
    return int(json.loads(sf.read_text())["runnerId"]), sf


def _mon_tour(rpc, rid, vis):
    for _ in range(20):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        u = next((x for x in (dv.get("units") or [])
                  if x.get("visualId") == vis and x.get("alive")), None)
        if u is None:
            return None, None
        if dv.get("currentPlayer") == u.get("owner"):
            return dv, u
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return None, None


def _place(rpc, rid, board, dv, caster, dist_voulue: int):
    """DRIVE les positions (`applyAction move` ignore portee et propriete) : parque les ennemis
    LOIN, puis pose UNE cible a la distance hex EXACTE voulue. Rend `(targetId, dist)` ou
    `(None, None)` -- jamais « bloque par la geometrie de spawn »."""
    myp = caster.get("owner")
    cpos = _pos(caster)
    enemies = [u for u in (dv.get("units") or []) if u.get("alive") and u.get("owner") != myp]
    if not enemies:
        return None, None
    tgt, autres = enemies[0], enemies[1:]
    far = [t for t in sorted(board.by_id)
           if board.walkable(t) and hexgeo.distance(board.coord(t), cpos) > 5]
    it = iter(far)
    for e in autres:
        ft = next(it, None)
        if ft is None:
            break
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": e["id"],
            "to": {"col": board.coord(ft)[0], "row": board.coord(ft)[1]}}}, 60)
    def _poser(depuis):
        for t in [x for x in sorted(board.by_id)
                  if board.walkable(x) and hexgeo.distance(board.coord(x), depuis) == dist_voulue]:
            tc = board.coord(t)
            rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "move", "unitId": tgt["id"], "to": {"col": tc[0], "row": tc[1]}}}, 60)
            dv2 = rpc("decisionView", {"runnerId": rid}, 90)
            t2 = next((u for u in (dv2.get("units") or []) if u.get("id") == tgt["id"]), None)
            if t2 is not None and _pos(t2) == tc:
                return tgt["id"], hexgeo.distance(tc, depuis)
        return None, None

    tid, d = _poser(cpos)
    if tid is not None:
        return tid, d
    # REPLI : la geometrie de spawn peut boucher TOUS les voisins du caster (les trois porteurs
    # sont deployes cote a cote). On DEPLACE alors le CASTER vers une zone degagee, puis on repose
    # la cible autour de sa NOUVELLE position -- « deplacer les unites », jamais « bloque par la
    # geometrie ». Le caster est deplace AVANT la cible : il n'arrive donc adjacent a personne, et
    # aucune CHARGE parasite n'est creee.
    dvc = rpc("decisionView", {"runnerId": rid}, 90)
    occupes = {_pos(u) for u in (dvc.get("units") or []) if u.get("alive")}
    tpos_act = next((_pos(u) for u in (dvc.get("units") or []) if u.get("id") == tgt["id"]), None)
    for t in sorted(board.by_id):
        tc = board.coord(t)
        if not board.walkable(t) or tc in occupes:
            continue
        # jamais adjacent a la cible : le caster arriverait au contact et CHARGERAIT, ce qui
        # polluerait la cle conditionnelle sur un porteur ou elle doit rester absente.
        if tpos_act is not None and hexgeo.distance(tc, tpos_act) <= 1:
            continue
        libres = sum(1 for n in board.neighbours(t)
                     if board.walkable(n) and board.coord(n) not in occupes)
        if libres < 3:
            continue
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": caster["id"], "to": {"col": tc[0], "row": tc[1]}}}, 60)
        dv3 = rpc("decisionView", {"runnerId": rid}, 90)
        c3 = next((u for u in (dv3.get("units") or []) if u.get("id") == caster["id"]), None)
        if c3 is None or _pos(c3) != tc:
            continue
        tid, d = _poser(tc)
        if tid is not None:
            return tid, d
    return None, None


def _charger(rpc, rid, board, caster, target_id):
    """DEPLACE le caster sur une tuile ADJACENTE a la cible -- c'est ce pas qui remplit
    `UnitComponent.ChargedUnitIds@+0x190` (`IdunBattle.Operations.MoveUnitOperation$$UpdateCharging`
    ajoute les unites NOUVELLEMENT adjacentes). Rend `(decisionView, caster, dist)`."""
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    tgt = next((u for u in (dv.get("units") or []) if u.get("id") == target_id), None)
    if tgt is None:
        return None, None, None
    ttile = board.id_at(*_pos(tgt))
    for n in [x for x in board.neighbours(ttile) if board.walkable(x)]:
        nc = board.coord(n)
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": caster["id"], "to": {"col": nc[0], "row": nc[1]}}}, 60)
        dv2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
        c2 = next((u for u in (dv2.get("units") or []) if u.get("id") == caster["id"]), None)
        if c2 is not None and _pos(c2) == nc:
            return dv2, c2, hexgeo.distance(nc, _pos(tgt))
    return None, None, None


def _tags_info_du_cast(cast) -> list:
    """Les dicts de tags des pas `StepType.Info` de la cascade qui portent un
    `Attack_Weapon_DamageProfile` -- ceux qu'emet `IdunBattle.Operations.InformOperation$$Execute`."""
    s_info = SE.step_id("Info")
    return [t for t in (_tags(ev) for ev in _cascade(cast) if ev.get("step") == s_info)
            if "Attack_Weapon_DamageProfile" in t]


def _tags_du_port(vis: str, dist: int, charge: bool) -> dict:
    """Ce que le PORT pose pour cette unite a cette distance et dans cet etat de charge. Chaine
    ENTIEREMENT independante du flux : gameconfig -> selection d'arme -> derivation -> dict de tags.

    `charge` n'est PAS lu du flux : c'est le MONTAGE (le probe a lui-meme deplace le caster au
    contact), au meme titre que la distance."""
    w, _ranged = get_attack_weapon_for_default_normal_attack(vis, is_adjacent=(dist <= 1),
                                                             dist=dist)
    if w is None:
        return {}
    # Le MEME foyer que le runner : la cascade `custom_normal_attack` dit quelle attaque normale
    # l'unite porte, `inform_weapon_use_special` dit si son `ExecuteBehaviour` pose la 3e cle.
    na = custom_normal_attack(passive_abilities=None, active_abilities=None, visual_id=vis,
                              traits=None)
    us = inform_weapon_use_special(na, is_charging=charge, weapon_melee=weapon_is_melee(w))
    return dict(InformWeapon.from_weapon(w, use_special=us).tags())


def _lignes_info_du_flux(flux: str) -> list:
    """Chaque bloc `Action=Info` du flux natif qui porte un `Attack_Weapon_*`, rendu STRIPPE
    (la ligne d'action puis ses `Tag=`). C'est le SECOND canal : le texte canonique, pas la
    cascade RPC."""
    lignes = flux.split("\n")
    out = []
    for i, l in enumerate(lignes):
        if l.strip() != "Action=Info Entity=NO_ENTITY":
            continue
        bloc, j = [l.strip()], i + 1
        while j < len(lignes) and lignes[j].strip().startswith("Tag="):
            bloc.append(lignes[j].strip())
            j += 1
        if any("Attack_Weapon" in x for x in bloc):
            out.append(bloc)
    return out


def _bloc_du_port(tags: dict) -> list:
    """Le MEME bloc, ecrit par le port : `InformOperation$$Execute` dans un groupe
    `Ability_Power`. Rendu STRIPPE pour que l'indentation (profondeur du groupe englobant, hors
    perimetre de cette tranche) n'entre pas dans la comparaison."""
    capt = []

    class _C:
        def on_root_group_finished(self, g):
            capt.append(g)

        def on_log(self, chunk):
            pass

    cache = StreamCache()
    cache.add_listener(_C())
    events = StreamDispatcher()
    events.subscribe(cache)
    events.start_group(int(GroupType.Ability_Power), 0, "Loki_NormalAttack", None)
    inform(events, tags)
    events.finish_group()
    return [x.strip() for x in capt[0].split("\n")
            if x.strip().startswith(("Action=Info", "Tag="))]


def _confronter(natif: dict, porte: dict, prefixe: str = "iwna", bavard: bool = True) -> int:
    """[1] les deux cles inconditionnelles concordent ; [2] les `IsMelee` DIFFERENT ;
    [2b] deux porteurs de MEME profil ont des `IsMelee` OPPOSES ; [3] la conditionnelle est
    absente des deux cotes. Rend le nombre d'ecarts."""
    ko = 0
    for nom in sorted(natif):
        t, p = natif[nom], porte.get(nom) or {}
        for cle in (TagKey.Attack_Weapon_DamageProfile, TagKey.Attack_Weapon_IsMelee):
            v_nat, v_port = t.get(cle.name), p.get(cle)
            etat = ("OK" if v_nat is not None and v_port is not None and int(v_nat) == int(v_port)
                    else "KO")
            ko += (etat == "KO")
            if bavard:
                print(f"[{prefixe}][1] {nom:20s} {cle.name:30s} natif={v_nat} port={v_port} {etat}")
    # [3] LA CLE CONDITIONNELLE, dans les DEUX SENS. Elle etait « absente des deux cotes » tant
    # qu'aucun montage ne l'exercait ; depuis #419-r1-tr14-r4-r2-r1 le corpus porte un regime ou le
    # natif la POSE (`FeederTendrils` en charge), donc on compare presence ET valeur.
    n_pose = p_pose = 0
    for nom in sorted(natif):
        v_nat = natif[nom].get(TagKey.Attack_Weapon_Use_Special.name)
        v_port = (porte.get(nom) or {}).get(TagKey.Attack_Weapon_Use_Special)
        n_pose += (v_nat is not None)
        p_pose += (v_port is not None)
        etat = "OK" if ((v_nat is None) == (v_port is None)
                        and (v_nat is None or int(v_nat) == int(v_port))) else "KO"
        ko += (etat == "KO")
        if bavard:
            print(f"[{prefixe}][3] {nom:24s} Use_Special natif={v_nat} port={v_port} {etat}")
    # TEMOIN DU CONDITIONNEL : le corpus doit l'exercer DANS LES DEUX ETATS, sinon « conditionnel »
    # n'est pas teste -- un port qui la poserait toujours, ou jamais, passerait.
    etat = "OK" if 0 < n_pose < len(natif) else "KO"
    ko += (etat == "KO")
    if bavard:
        print(f"[{prefixe}][3b] temoin du conditionnel : natif la pose sur {n_pose}/{len(natif)} "
              f"porteur(s), le port sur {p_pose}/{len(natif)} (il faut STRICTEMENT entre 0 et N) "
              f"{etat}")
    # [2] anti-regime-degenere.
    vals = {n: int(t.get(TagKey.Attack_Weapon_IsMelee.name, -99)) for n, t in natif.items()}
    if len(natif) < 2:
        ko += 1
        if bavard:
            print(f"[{prefixe}][2] NON CONFRONTE -- {len(natif)}/3 porteurs, le discriminant exige "
                  "au moins DEUX valeurs d'IsMelee")
    else:
        etat = "OK" if len(set(vals.values())) >= 2 else "KO"
        ko += (etat == "KO")
        if bavard:
            print(f"[{prefixe}][2] discriminant IsMelee natif {vals} (doivent DIFFERER) {etat}")
    # [2b] TEMOIN DU TEMOIN : meme profil, IsMelee opposes.
    par_profil = {}
    for n, t in natif.items():
        par_profil.setdefault(t.get(TagKey.Attack_Weapon_DamageProfile.name), set()).add(
            t.get(TagKey.Attack_Weapon_IsMelee.name))
    duo = [pr for pr, ms in par_profil.items() if len(ms) >= 2]
    etat = "OK" if duo else "KO"
    ko += (etat == "KO")
    if bavard:
        print(f"[{prefixe}][2b] temoin du temoin : profil(s) portant DEUX IsMelee = {duo} "
              f"(sinon `isMelee` pourrait se deduire du profil) {etat}")
    return ko


def _porte_courant() -> dict:
    return {p["nom"]: _tags_du_port(p["vis"], p["dist_att"], p["charge"]) for p in PORTEURS}


def contre_epreuve() -> int:
    """Mutations hors ligne contre la `MESURE_NATIVE` figee. `a_mordu` est publie SEPAREMENT du
    verdict : une mutation NON EXERCEE se DECLARE, elle ne se compte pas verte."""
    base = _porte_courant()
    ref = _confronter(MESURE_NATIVE, base, prefixe="ce-ref", bavard=False)
    print(f"[ce] reference (port intact) ecarts={ref} -> {'PASS' if ref == 0 else 'FAIL'}")
    if ref:
        print("[ce] ABANDON : la reference ne passe pas, une mutation ne prouverait rien")
        _confronter(MESURE_NATIVE, base, prefixe="ce-ref")
        return 1

    def _mute(nom, **kw):
        out = {k: dict(v) for k, v in base.items()}
        out[nom] = dict(kw.get("tags", out[nom]))
        return out

    def _cst_melee(v: int):
        return {n: {**t, TagKey.Attack_Weapon_IsMelee: v} for n, t in base.items()}

    def _du_profil():
        """La faute que le temoin [2b] existe pour attraper : `isMelee` deduit du PROFIL."""
        return {n: {**t, TagKey.Attack_Weapon_IsMelee:
                    int(t[TagKey.Attack_Weapon_DamageProfile] != 0)} for n, t in base.items()}

    def _interversion(nom):
        s = base[nom]
        return _mute(nom, tags={TagKey.Attack_Weapon_DamageProfile: s[TagKey.Attack_Weapon_IsMelee],
                                TagKey.Attack_Weapon_IsMelee: s[TagKey.Attack_Weapon_DamageProfile]})

    def _use_special(nom):
        s = dict(base[nom])
        s[TagKey.Attack_Weapon_Use_Special] = 0
        return _mute(nom, tags=s)

    def _sans_use_special(nom):
        s = {k: v for k, v in base[nom].items() if k != TagKey.Attack_Weapon_Use_Special}
        return _mute(nom, tags=s)

    mutations = [
        ("M1 IsMelee constant 1 partout", _cst_melee(1), True),
        ("M2 IsMelee constant 0 partout", _cst_melee(0), True),
        ("M3 IsMelee DEDUIT du profil", _du_profil(), True),
        ("M4 Use_Special inconditionnelle (deathBlightlord@1)",
         _use_special("deathBlightlord@1"), True),
        # M4b -- LE GATE `FeederTendrils` LUI-MEME : sans lui, la cle disparait du seul porteur qui
        # la porte. C'est la mutation qui distingue « la cle est portee » de « la cle est absente
        # partout », etat du port AVANT cette tranche.
        ("M4b gate FeederTendrils desarme (charge)",
         _sans_use_special("tyranDeathleaper@charge"), True),
        ("M5 interversion 0x92/0x93 (deathBlightlord@1)", _interversion("deathBlightlord@1"), True),
        # ⚠ INERTE PAR ALGEBRE, et c'est MESURE, pas subi : sur `admecDestroyer@3` le profil
        # `Physical` vaut **0** ET `isMelee` vaut **0** -- intervertir les deux cles n'y change
        # RIEN. C'est `deathBlightlord@1` (14 vs 1) qui revele la faute, d'ou M5. L'equivalence
        # est assertionnee dans les DEUX SENS (`a_mordu` ET `rougit` attendus a False) : sa
        # disparition rougira au lieu de passer. Meme forme que le M4b du parent.
        ("M6 interversion 0x92/0x93 (admecDestroyer@3)", _interversion("admecDestroyer@3"), False),
    ]
    ko = 0
    for nom, mute, mord_attendu in mutations:
        a_mordu = any(mute[n] != base[n] for n in base)
        rougit = _confronter(MESURE_NATIVE, mute, prefixe="ce", bavard=False) > 0
        ok = (a_mordu == mord_attendu) and (rougit == mord_attendu)
        ko += (not ok)
        print(f"[ce] {nom:52s} a_mordu={a_mordu!s:5s} (attendu {mord_attendu!s:5s}) "
              f"rougit={rougit!s:5s} {'OK' if ok else 'KO'}")
    print(f"[ce] BILAN CONTRE-EPREUVE: {'PASS' if ko == 0 else 'FAIL'} ({ko} ecart(s))")
    return 0 if ko == 0 else 1


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=41902)
    ap.add_argument("--contre-epreuve", action="store_true",
                    help="mutations hors ligne contre la MESURE_NATIVE figee (aucun runner)")
    args = ap.parse_args(argv)
    if args.contre_epreuve:
        return contre_epreuve()

    sid = _resolve_session()
    rid, sf = build(args.seed)
    if rid is None:
        return 2

    def rpc(m, b, t=120):
        return _r(sid, m, b, t)

    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (bg or {}).get("tiles"):
        print("[iwna] NON CONFRONTE -- boardGraph indispo")
        return 2
    board = Board(bg["tiles"], adjacency="native_sym")
    natif, dists, flux = {}, {}, ""
    try:
        for p in PORTEURS:
            dv, caster = _mon_tour(rpc, rid, p["vis"])
            if caster is None:
                print(f"[iwna] {p['nom']}: NON CONFRONTE -- tour/unite indisponible")
                continue
            tid, dist = _place(rpc, rid, board, dv, caster, p["dist"])
            if tid is None:
                print(f"[iwna] {p['nom']}: NON CONFRONTE -- distance {p['dist']} non montable")
                continue
            if p["charge"]:
                # DEPLACER LE CASTER au contact : c'est ce pas qui remplit
                # `UnitComponent.ChargedUnitIds` (`MoveUnitOperation$$UpdateCharging`). Le
                # repositionnement de la CIBLE, lui, ne fait charger personne.
                dv, caster, dist = _charger(rpc, rid, board, caster, tid)
                if caster is None:
                    print(f"[iwna] {p['nom']}: NON CONFRONTE -- charge non montable")
                    continue
            na = next((a for a in (caster.get("abilities") or [])
                       if a.get("kind") == "normal"), None)
            if na is None:
                print(f"[iwna] {p['nom']}: NON CONFRONTE -- aucune attaque normale publiee")
                continue
            cast = rpc("applyAction", {"runnerId": rid, "action": {
                "kind": "ability", "casterId": caster["id"], "targetId": tid,
                "abilityType": int(na["id"])}, "captureEvents": True}, 180)
            if not (isinstance(cast, dict) and cast.get("ok")):
                print(f"[iwna] {p['nom']}: NON CONFRONTE -- attaque refusee: {str(cast)[:200]}")
                continue
            infos = _tags_info_du_cast(cast)
            if not infos:
                print(f"[iwna] {p['nom']}: NON CONFRONTE -- aucun pas Info porteur")
                continue
            natif[p["nom"]] = infos[0]
            dists[p["nom"]] = (dist, p["charge"])
            print(f"[iwna] {p['nom']} (dist={dist}, charge={p['charge']}) natif -> "
                  f"{json.dumps(infos[0], sort_keys=True)}")
        flux = (rpc("replayOutputStream", {"runnerId": rid, "maxChars": 8000000})
                .get("outputStream") or "")
    finally:
        try:
            rpc("disposeRunner", {"runnerId": rid}, 60)
        except Exception:
            pass
        if sf is not None:
            Path(sf).unlink(missing_ok=True)

    # Le port est evalue A LA DISTANCE REELLEMENT MONTEE, pas a celle qu'on voulait.
    porte = {n: _tags_du_port(next(p["vis"] for p in PORTEURS if p["nom"] == n), d, c)
             for n, (d, c) in dists.items()}
    ko = _confronter(natif, porte)

    # --- [4] SECOND CANAL : le TEXTE canonique du flux, ligne a ligne.
    blocs = _lignes_info_du_flux(flux)
    print(f"[iwna][4] flux natif : {len(blocs)} bloc(s) `Action=Info` porteur(s) de "
          f"`Attack_Weapon_*` pour {len(natif)} attaque(s) confrontee(s)")
    if not blocs:
        print("[iwna][4] NON CONFRONTE -- le flux ne porte aucun bloc (recordReplay arme ?)")
        ko += 1
    attendus = [_bloc_du_port(porte[n]) for n in sorted(porte)]
    for b in blocs:
        egal = any(b == a for a in attendus)
        print(f"[iwna][4] {' | '.join(b)} -> {'OK' if egal else 'KO'}")
        ko += (not egal)

    # --- [5] garde de NON-DERIVE : la mesure du jour doit reproduire celle qu'a figee le fichier.
    for nom, t in natif.items():
        attendu = MESURE_NATIVE.get(nom)
        if attendu is not None and t != attendu:
            ko += 1
            print(f"[iwna][5] {nom}: le flux natif a DERIVE depuis la mesure figee "
                  f"{attendu} -> {t} (la contre-epreuve hors ligne est PERIMEE)")
    if len(natif) < len(PORTEURS):
        print(f"[iwna] PORTEE : {len(natif)}/{len(PORTEURS)} porteurs confrontes")
    print(f"[iwna] BILAN: {'PASS' if ko == 0 else 'FAIL'} ({ko} ecart(s))")
    return 0 if ko == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
