#!/usr/bin/env python
"""Probe #419-r1-tr14-r4-r2-r1-r1 / -r2 -- les DEUX branches SPECIALES de l'attaque normale.

VOLET 1 (`-r1`) -- `FeederTendrils_NormalAttackAbility$$ExecuteBehaviour`, branche de CHARGE
------------------------------------------------------------------------------------------
Sous `(IsCharging(caster, target) & WeaponProfile.get_IsMelee(weapon))`, le natif joue, ENTRE
`ExecuteInformWeapon(useSpecial: 1)` et `ExecuteNormalAttack` :

    ExecuteAtomic( Heal(caster, caster, ConfigVar(hpToHeal), ForHeal)
                 + AddEffect(0x429 = Pinned, src = AbilityStateReference, target, turns: null),
                   entities, 0x2a )

Le port ne jouait NI le soin NI l'effet. La QUESTION MESUREE ici : le caster est-il soigne, et la
cible pinnee, des DEUX cotes -- et le gate a-t-il bien QUATRE regimes distincts ?

VOLET 2 (`-r2`) -- `OptimizedGait_NormalAttackAbility$$ExecuteBehaviour`, l'ANCRE du gate
----------------------------------------------------------------------------------------
Le gate est `EntityExtensions$$HasEffect(<entite du champ +8 des AbilityEntities>, state,
0x4e2, null)`. `+8` est-il le CASTER ou la CIBLE ? La RE tranche CASTER (`AbilityEntities$$.ctor`,
six getters concordants -- cf. `engine/services/custom_normal_attack.py`). Ce probe le CONFRONTE en
montant les DEUX regimes sur `admecRuststalker` (porteur reel, dans le pool) :

  * bras `caster`  -- le CASTER porte `CordClaw_AdditionHits`, la cible NON ;
  * bras `cible`   -- la CIBLE le porte, le CASTER NON (deux `admecRuststalker`, un par camp) ;
  * bras `aucun`   -- personne ne le porte (temoin).

`Tag=Attack_Weapon_Use_Special:1` dans le flux natif DESIGNE l'ancre. Un seul des deux premiers bras
peut l'ecrire ; s'ils l'ecrivent tous les deux ou aucun, l'ancre n'est PAS tranchee par la mesure et
le probe le DIT au lieu de conclure.

ANTI-REGIME-DEGENERE : `--contre-epreuve` mute le foyer et exige que chaque mutation MORDE ; le
`a_mordu` est publie SEPAREMENT du verdict.

ASCII only (cp1252).
Usage: python probe_419r1tr14r4r2r1r1_normal_attack_special_branches.py
           [--seed N] [--volet 1|2|both] [--contre-epreuve]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hexgeo  # noqa: E402
import stream_events as SE  # noqa: E402
from rl_collect_batch import _resolve_session, _rpc  # noqa: E402
from engine.entities.effect_type import EffectType  # noqa: E402
from engine.entities.pathfinding.board import Board  # noqa: E402
from engine.entities.effects.magnitude import ability_var  # noqa: E402
from engine.services.custom_normal_attack import (custom_normal_attack,  # noqa: E402
                                                  feeder_tendrils_special_applies,
                                                  inform_weapon_use_special)
from engine.streams.tag_key import TagKey  # noqa: E402

# Le probe PARENT (#419-r1-tr14-r4-r2-r1) sait deja monter une charge au contact et lire le flux :
# on REUTILISE ses primitives de pilotage plutot que d'en ecrire de secondes.
from probe_419r1tr14r4r2r1_normal_attack_inform_weapon import (  # noqa: E402
    _cascade, _charger, _mon_tour, _place, _pos, _r, _tags)

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
BOARD = "MC1_67"

PINNED = int(EffectType.Pinned)                       # 0x429 = 1065
ADDITION_HITS = int(EffectType.CordClaw_AdditionHits)  # 0x4e2 = 1250


def _build(seed: int, p_units: str, a_units: str, tag: str):
    sf = ROOT / "logs" / "runners" / f"nasp-{tag}-{uuid.uuid4().hex[:8]}.json"
    sf.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--state-file", str(sf),
         "--board", BOARD, "--roster", "1", "--record-replay",
         "--p-units", p_units, "--a-units", a_units,
         "--hp-target", "400000", "--hp-player", "400000"],
        cwd=str(PYDIR), capture_output=True, text=True, encoding="utf-8", errors="replace")
    if not sf.exists():
        print(f"[nasp] build KO ({tag}): {(proc.stderr or proc.stdout or '')[-500:]}")
        return None, None
    return int(json.loads(sf.read_text())["runnerId"]), sf


def _units(rpc, rid, dv=None):
    dv = dv if dv is not None else rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    return dv, [u for u in (dv.get("units") or []) if u.get("alive")]


def _effets(rpc, rid, uid) -> list:
    """Les `effectType` portes par l'unite, lus de `decisionView.units[].effects`.

    ⚠ C'est le SEUL canal qui les porte : `observeBattle.units[]` n'a PAS de champ `effects`
    (mesure du 2026-08-06 -- ses cles sont armor/hp/col/row/... et rien d'autre). Un lecteur branche
    dessus rend une liste VIDE sans erreur, et le probe conclut alors « regime non arme » alors que
    l'effet est bien pose : c'est exactement ce faux negatif qui a fait echouer la 1re passe."""
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    out = []
    for u in (dv.get("units") or []):
        if u.get("id") != uid:
            continue
        for e in (u.get("effects") or []):
            t = e.get("effectType", e.get("type"))
            if t is None:
                t = e.get("id")
            if t is not None:
                out.append(int(t))
    return out


def _hp(rpc, rid, uid):
    dv = rpc("decisionView", {"runnerId": rid}, 90)
    for u in (dv.get("units") or []):
        if u.get("id") == uid:
            return u.get("hp"), u.get("maxHp", u.get("hpMax"))
    return None, None


def _attendre_action(rpc, rid, vis, uid=None, max_end=24):
    """Enchaine des `endturn` jusqu'a ce que ce soit le tour du camp de l'unite ET qu'elle ait
    encore son activation (`hasAction`).

    C'est le cran que `_mon_tour` seul ne donne pas : il rend la main des que le joueur courant est
    le bon, meme si l'unite a DEJA agi -- et un cast sur une unite sans activation est refuse EN
    SILENCE (`ok=True`, aucun effet, signature #111).

    `uid` FIGE l'unite visee. Sans lui, quand les DEUX camps ont le meme `visualId`, le selecteur
    « premier <vis> dont l'owner est le joueur courant » designe tantot le mien tantot celui d'en
    face -- confond mesure de la 2e passe (le meme id a casté dans deux bras opposes).
    Rend `(decisionView, unite)`."""
    for _ in range(max_end):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        u = next((x for x in (dv.get("units") or [])
                  if x.get("alive") and dv.get("currentPlayer") == x.get("owner")
                  and (x.get("id") == uid if uid is not None
                       else x.get("visualId") == vis)), None)
        if u is not None and u.get("hasAction"):
            return dv, u
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return None, None


def _amener_au_contact(rpc, rid, board, dv, caster_id, target_id) -> bool:
    """Pose `target_id` sur une tuile ADJACENTE a `caster_id`, en PARQUANT d'abord les autres
    unites qui encombrent le voisinage -- « deplacer les unites », jamais « bloque par la geometrie
    de spawn ». Ne deplace JAMAIS le caster (son activation doit rester intacte pour le cast)."""
    us = [x for x in (dv.get("units") or []) if x.get("alive")]
    cpos = next((_pos(x) for x in us if x["id"] == caster_id), None)
    if cpos is None:
        return False
    if hexgeo.distance(next(_pos(x) for x in us if x["id"] == target_id), cpos) == 1:
        return True
    ctile = board.id_at(*cpos)
    voisins = [x for x in board.neighbours(ctile) if board.walkable(x)]
    occupe = {_pos(x): x["id"] for x in us}
    loin = [t for t in sorted(board.by_id)
            if board.walkable(t) and hexgeo.distance(board.coord(t), cpos) > 5]
    it = iter(loin)
    for n in voisins:
        nc = board.coord(n)
        gene = occupe.get(nc)
        if gene is not None and gene not in (caster_id, target_id):
            ft = next(it, None)
            if ft is not None:
                rpc("applyAction", {"runnerId": rid, "action": {
                    "kind": "move", "unitId": gene,
                    "to": {"col": board.coord(ft)[0], "row": board.coord(ft)[1]}}}, 60)
    for n in voisins:
        nc = board.coord(n)
        rpc("applyAction", {"runnerId": rid, "action": {
            "kind": "move", "unitId": target_id, "to": {"col": nc[0], "row": nc[1]}}}, 60)
        _dv, us2 = _units(rpc, rid)
        t2 = next((x for x in us2 if x["id"] == target_id), None)
        if t2 is not None and _pos(t2) == nc:
            return True
    return False


def _blesser(rpc, rid, board, victime, min_total: int = 0, max_coups: int = 10) -> int:
    """Fait ENCAISSER des attaques normales a `victime` par des adverses amenes au contact, jusqu'a
    lui avoir retire AU MOINS `min_total` PV. Rend le total retire.

    DEUX raisons, et la seconde n'est apparue qu'a la mesure :

    1. la garde `Healable` du natif (`HealableUnitsSelector` = HP < max) rend le `Heal` INERTE sur
       une unite pleine -- sans blessure, l'accord serait DEGENERE (400000 -> 400000 des deux cotes) ;
    2. `HealUnitOperation` PLAFONNE le soin a `hp_max`. Une blessure INFERIEURE au montant soigne
       ecrete donc la mesure et fait lire un « ecart de montant » qui n'existe pas : mesure du
       2026-08-06, blessure de 1356 pour un `hpToHeal` de 3290 -> delta observe 1356. Il faut donc
       CREUSER un trou plus profond que le soin attendu pour que le montant soit OBSERVABLE."""
    hp_ini, _ = _hp(rpc, rid, victime)
    if hp_ini is None:
        return 0
    total = 0
    for _ in range(max_coups):
        dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
        us = [x for x in (dv.get("units") or []) if x.get("alive")]
        v = next((x for x in us if x["id"] == victime), None)
        if v is None:
            break
        touche = False
        for e in [x for x in us if x.get("owner") != v.get("owner")]:
            dv2 = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
            if not _amener_au_contact(rpc, rid, board, dv2, victime, e["id"]):
                continue
            dv3, _u = _attendre_action(rpc, rid, None, uid=e["id"])
            if dv3 is None:
                continue
            hp0, _ = _hp(rpc, rid, victime)
            _attaque_normale(rpc, rid, e["id"], victime)
            hp1, _ = _hp(rpc, rid, victime)
            if hp0 is not None and hp1 is not None and hp1 < hp0:
                total = int(hp_ini) - int(hp1)
                touche = True
                break
        if not touche or total >= min_total:
            break
    if total:
        print(f"    caster blesse de {total} PV au total (cible de {min_total})")
    return total


def _niveau_et_multiplier(rpc, rid, uid):
    """`(level, multiplier_pct)` de l'attaque normale de l'unite, lus du `decisionView` -- les deux
    entrees que `ability_var` indexe. Sert a calculer le montant que le PORT poserait, sans monter
    de `State` offline."""
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 150)
    for u in (dv.get("units") or []):
        if u.get("id") != uid:
            continue
        for a in (u.get("abilities") or []):
            if a.get("level") is not None:
                return a.get("level"), a.get("multiplier", 100)
    return None, 100


def _attaque_normale(rpc, rid, caster, target):
    """Joue l'attaque NORMALE de `caster` sur `target` et rend la reponse RPC."""
    at = None
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True}, 120)
    for u in (dv.get("units") or []):
        if u.get("id") == caster:
            for a in (u.get("abilities") or []):
                if a.get("kind") == "normal":
                    at = a.get("id")
    if at is None:
        return None
    return rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": caster, "targetId": target,
        "abilityType": int(at)}}, 90)


def _tags_use_special(res) -> list:
    """Les dicts de tags des pas `StepType.Info` porteurs d'un `Attack_Weapon_DamageProfile`."""
    s_info = SE.step_id("Info")
    return [t for t in (_tags(ev) for ev in _cascade(res) if ev.get("step") == s_info)
            if "Attack_Weapon_DamageProfile" in t]


# ===================================================================== VOLET 1 -- FeederTendrils

def volet1(seed: int) -> int:
    """`tyranDeathleaper` (passif `FeederTendrils`) : quatre regimes du gate `IsCharging & IsMelee`.

    Le caster est BLESSE avant chaque mesure -- sans quoi la garde `Healable` (HP < max) rend le
    `Heal` INERTE des deux cotes et l'accord ne prouverait rien (regime degenere)."""
    print("=" * 78)
    print("VOLET 1 -- FeederTendrils : Heal(caster) + AddEffect(Pinned, cible) sous charge melee")
    print("=" * 78)
    na = custom_normal_attack(visual_id="tyranDeathleaper")
    print(f"  cascade d'attaque normale (port) : {na}")
    if na != "FeederTendrils_NormalAttack":
        print("  KO : le porteur ne recoit pas l'attaque normale attendue")
        return 1

    print("  TABLE DU GATE (port, offline) -- les QUATRE combinaisons :")
    quatre = {}
    for ch in (True, False):
        for me in (True, False):
            v = feeder_tendrils_special_applies(na, is_charging=ch, weapon_melee=me)
            quatre[(ch, me)] = v
            print(f"    IsCharging={int(ch)} IsMelee={int(me)} -> branche speciale = {v}")
    if sum(1 for v in quatre.values() if v) != 1 or not quatre[(True, True)]:
        print("  KO : le gate n'est pas la CONJONCTION lue au decompile")
        return 1

    rid, sf = _build(seed, "tyranDeathleaper", "necroWarden,necroWarden,necroWarden", "v1")
    if rid is None:
        return 1
    ko = 0
    try:
        sid = _resolve_session()

        def rpc(m, b, t=120):
            return _r(sid, m, b, t)

        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (bg or {}).get("tiles"):
            print("  NON CONFRONTE -- boardGraph indisponible")
            return ko + 1
        board = Board(bg["tiles"], adjacency="native_sym")
        moi = None
        for regime, dist, charge in (("CHARGE", 2, True), ("NO_STEP", 1, False)):
            dv, u = _mon_tour(rpc, rid, "tyranDeathleaper")
            if dv is None:
                print(f"  [{regime}] mon tour non atteint")
                ko += 1
                continue
            moi = u["id"]
            # TEMOIN NON NUL du `Heal` : sans blessure, la garde `Healable` le rend inerte des DEUX
            # cotes et l'accord serait DEGENERE.
            # ⚠ INCONDITIONNEL : `decisionView.units[]` ne porte AUCUN champ de PV MAX (mesure --
            # ses cles sont hp/pos/effects/abilities/...), donc `hp >= hp_max` ne peut pas servir de
            # garde. Une garde branchee sur un champ ABSENT ne se declenche jamais, en silence :
            # c'est ce qui a laisse la 1re passe mesurer un caster a PV pleins.
            # La cible de blessure est 2x le montant attendu : le soin doit tenir ENTIER dans le
            # trou, sinon `HealUnitOperation` l'ecrete a `hp_max` et le montant n'est pas observable.
            _lvl0, _mult0 = _niveau_et_multiplier(rpc, rid, moi)
            _vise = 2 * int(ability_var("FeederTendrils", "hpToHeal", _lvl0,
                                        multiplier_pct=_mult0) or 0)
            if not _blesser(rpc, rid, board, moi, min_total=_vise):
                print(f"  [{regime}] AVERTISSEMENT : caster non blessable -- le `Heal` sera INERTE "
                      f"et la mesure du soin ne prouvera rien")
            dv, u = _mon_tour(rpc, rid, "tyranDeathleaper")
            if dv is None:
                print(f"  [{regime}] mon tour non re-atteint apres la blessure")
                ko += 1
                continue
            tid, d = _place(rpc, rid, board, dv, u, dist)
            if tid is None:
                print(f"  [{regime}] geometrie a distance {dist} non realisable")
                ko += 1
                continue
            if charge:
                dv, u, d = _charger(rpc, rid, board, u, tid)
                if dv is None:
                    print(f"  [{regime}] charge au contact impossible")
                    ko += 1
                    continue
            hp_av, hp_max = _hp(rpc, rid, u["id"])
            eff_av = _effets(rpc, rid, tid)
            res = _attaque_normale(rpc, rid, u["id"], tid)
            if res is None or not res.get("ok"):
                print(f"  [{regime}] attaque normale refusee")
                ko += 1
                continue
            hp_ap, _ = _hp(rpc, rid, u["id"])
            eff_ap = _effets(rpc, rid, tid)
            tags = _tags_use_special(res)
            us = any(TagKey.Attack_Weapon_Use_Special.name in t for t in tags)
            delta = (int(hp_ap) - int(hp_av)) if (hp_av is not None and hp_ap is not None) else None
            lvl, mult = _niveau_et_multiplier(rpc, rid, u["id"])
            porte = int(ability_var("FeederTendrils", "hpToHeal", lvl,
                                    multiplier_pct=mult) or 0)
            print(f"  [{regime}] dist={d} caster hp {hp_av} -> {hp_ap} (delta={delta}) "
                  f"| Pinned(cible) {PINNED in eff_av} -> {PINNED in eff_ap} | Use_Special={us}")
            print(f"           effets cible avant={sorted(set(eff_av))} apres={sorted(set(eff_ap))}")
            print(f"           HEAL : natif delta={delta}  |  port hpToHeal(lvl={lvl},"
                  f"mult={mult})={porte}")
            attendu = (regime == "CHARGE")
            if us != attendu:
                print(f"           KO : Use_Special attendu {attendu}")
                ko += 1
            if (PINNED in eff_ap) != attendu:
                print(f"           KO : Pinned sur la cible attendu {attendu}")
                ko += 1
            if attendu:
                # Le caster ENCAISSE aussi la riposte/l'overwatch eventuels ; le delta est donc
                # `heal - degats subis`. On exige que le SOIN ait eu lieu (delta > 0) et qu'il vaille
                # EXACTEMENT ce que le port pose, faute de quoi on l'affiche sans le maquiller.
                if delta is None or delta <= 0:
                    print("           KO : le natif n'a PAS soigne le caster sous charge melee")
                    ko += 1
                elif delta != porte:
                    print(f"           ECART DE MONTANT : natif={delta} port={porte}")
                    ko += 1
            elif delta:
                print(f"           KO : soin HORS branche speciale (delta={delta})")
                ko += 1
    finally:
        try:
            _r(_resolve_session(), "disposeRunner", {"runnerId": rid}, 30)
        except Exception:
            pass
    return ko


# ===================================================================== VOLET 2 -- OptimizedGait

def volet2(seed: int) -> int:
    """`admecRuststalker` des DEUX cotes : l'effet `CordClaw_AdditionHits` sur le caster / sur la
    cible. Le bras qui ecrit `Use_Special:1` DESIGNE l'ancre du champ `+8`."""
    print("=" * 78)
    print("VOLET 2 -- OptimizedGait : l'ANCRE du gate HasEffect(<+8>, 0x4e2)")
    print("=" * 78)
    na = custom_normal_attack(visual_id="admecRuststalker")
    print(f"  cascade d'attaque normale (port) : {na}")
    print(f"  port : gate=True  -> useSpecial={inform_weapon_use_special(na, False, True, True)}")
    print(f"  port : gate=False -> useSpecial={inform_weapon_use_special(na, True, True, False)}")

    rid, sf = _build(seed, "admecRuststalker",
                     "admecRuststalker,necroWarden", "v2")
    if rid is None:
        return 1
    ko = 0
    observe = {}
    try:
        sid = _resolve_session()

        def rpc(m, b, t=120):
            return _r(sid, m, b, t)

        bg = rpc("boardGraph", {"runnerId": rid}, 60)
        if not (bg or {}).get("tiles"):
            print("  NON CONFRONTE -- boardGraph indisponible")
            return ko + 1
        board = Board(bg["tiles"], adjacency="native_sym")
        # PROTOCOLE (chaque marche a deja coute une passe) :
        #  1. atteindre MON tour AVANT tout deplacement -- un `applyAction move` consomme une
        #     activation et peut faire basculer le joueur courant, apres quoi le cast est refuse
        #     EN SILENCE (`ok=True`, aucun degat : signature #111) ;
        #  2. ne deplacer QUE le ruststalker adverse, au contact (CordClaw est une melee, et
        #     l'attaque normale doit pouvoir le prendre pour cible) ;
        #  3. armer l'effet, PUIS re-atteindre mon tour (le cast termine l'activation) ;
        #  4. seulement alors, l'attaque normale.
        # MON camp est fige AU PREMIER TOUR et ne se redecouvre plus : il y a un
        # `admecRuststalker` dans CHAQUE camp, donc « le premier ruststalker dont l'owner est le
        # joueur courant » designe tantot le mien, tantot celui d'en face. C'est ce glissement qui a
        # fait caster le MEME id (83) dans les bras `caster` ET `cible` a la passe precedente.
        dv0, u0 = _attendre_action(rpc, rid, "admecRuststalker")
        if dv0 is None:
            print("  NON CONFRONTE -- activation initiale non obtenue")
            return ko + 1
        mine, moi = u0["owner"], u0["id"]
        adv = next((x for x in (dv0.get("units") or [])
                    if x.get("alive") and x.get("owner") != mine
                    and x.get("visualId") == "admecRuststalker"), None)
        if adv is None:
            print("  NON CONFRONTE -- pas de ruststalker adverse")
            return ko + 1
        tid = adv["id"]
        print(f"  caster (mon camp) = {moi} ; cible (ruststalker adverse) = {tid}")

        for bras in ("aucun", "caster", "cible"):
            dv, u = _attendre_action(rpc, rid, "admecRuststalker", uid=moi)
            if dv is None:
                print(f"  [{bras}] activation du caster {moi} non obtenue")
                ko += 1
                continue
            if not _amener_au_contact(rpc, rid, board, dv, moi, tid):
                print(f"  [{bras}] ruststalker adverse non placable au contact")
                ko += 1
                continue
            # Les poses sont de VRAIS `MoveUnitOperation` -- elles peuvent faire basculer le joueur
            # courant, apres quoi le cast serait refuse EN SILENCE (signature #111).
            dv, u = _attendre_action(rpc, rid, "admecRuststalker", uid=moi)
            if dv is None:
                print(f"  [{bras}] activation non disponible apres le placement")
                ko += 1
                continue
            # arme le regime d'effet -- `CordClaw` pose `CordClaw_AdditionHits` sur SON PROPRE
            # caster (self-buff, MESURE : remaining=3 sur le lanceur, RIEN sur sa cible). C'est ce
            # qui dissocie les deux ancres : faire caster l'ADVERSAIRE met l'effet sur la CIBLE de
            # notre attaque, et sur elle SEULE.
            if bras in ("caster", "cible"):
                lanceur = moi if bras == "caster" else tid
                victime = tid if bras == "caster" else moi
                # Le LANCEUR doit avoir SON activation : au bras `cible` c'est l'unite ADVERSE, donc
                # il faut passer la main a son camp. Sans ce cran, `applyAction` rend `ok=True` et
                # ne pose RIEN (mesure : 0x4e2 absent du lanceur) -- le refus est SILENCIEUX.
                dvl, _ul = _attendre_action(rpc, rid, "admecRuststalker", uid=lanceur)
                if dvl is None:
                    print(f"  [{bras}] activation du lanceur {lanceur} non obtenue")
                    ko += 1
                    continue
                _dv3, us3 = _units(rpc, rid, dvl)
                cc = next((a.get("id") for x in us3 if x["id"] == lanceur
                           for a in (x.get("abilities") or [])
                           if str(a.get("name") or "") == "CordClaw"), None)
                if cc is None:
                    print(f"  [{bras}] CordClaw introuvable sur {lanceur}")
                    ko += 1
                    continue
                rc = rpc("applyAction", {"runnerId": rid, "action": {
                    "kind": "ability", "casterId": lanceur, "targetId": victime,
                    "abilityType": int(cc)}}, 90)
                arme = ADDITION_HITS in _effets(rpc, rid, lanceur)
                print(f"    [{bras}] cast CordClaw par {lanceur} sur {victime} "
                      f"ok={rc.get('ok')} -> 0x4e2 sur {lanceur} = {arme}")
                if not arme:
                    print(f"    [{bras}] NON ARME ; effets de {lanceur} : "
                          f"{sorted(set(_effets(rpc, rid, lanceur)))}")
                    ko += 1
                    continue
            dvx, ux = _attendre_action(rpc, rid, "admecRuststalker", uid=moi)
            if dvx is None:
                print(f"  [{bras}] activation non re-obtenue apres le cast")
                ko += 1
                continue
            if not _amener_au_contact(rpc, rid, board, dvx, moi, tid):
                print(f"  [{bras}] contact perdu apres le cycle de tour")
                ko += 1
                continue
            dvx, ux = _attendre_action(rpc, rid, "admecRuststalker", uid=moi)
            if dvx is None:
                print(f"  [{bras}] activation perdue au re-contact")
                ko += 1
                continue
            # lecture APRES le cycle de tour : l'effet dure 2 rounds, il doit SURVIVRE jusqu'ici.
            porte_caster = ADDITION_HITS in _effets(rpc, rid, moi)
            porte_cible = ADDITION_HITS in _effets(rpc, rid, tid)
            res = _attaque_normale(rpc, rid, moi, tid)
            if res is None or not res.get("ok"):
                print(f"  [{bras}] attaque normale refusee")
                ko += 1
                continue
            tags = _tags_use_special(res)
            if not tags:
                print(f"  [{bras}] AUCUN pas Info -- l'attaque n'a rien produit (cast refuse en "
                      f"silence ?) ; la mesure de ce bras ne vaut RIEN")
                ko += 1
                continue
            us = any(TagKey.Attack_Weapon_Use_Special.name in t for t in tags)
            observe[bras] = {"caster_porte": porte_caster, "cible_porte": porte_cible,
                             "use_special": us}
            print(f"  [{bras}] 0x4e2 caster={porte_caster} cible={porte_cible} "
                  f"-> Use_Special={us}   tags={tags}")
    finally:
        try:
            _r(_resolve_session(), "disposeRunner", {"runnerId": rid}, 30)
        except Exception:
            pass

    print("-" * 78)
    print("  VERDICT D'ANCRE :")
    b_cas, b_cib = observe.get("caster"), observe.get("cible")
    if b_cas is None or b_cib is None:
        print("    NON TRANCHE PAR LA MESURE -- un des deux bras n'a pas ete monte.")
        return ko + 1
    if not b_cas["caster_porte"] or not b_cib["cible_porte"]:
        print("    NON TRANCHE -- le regime voulu n'a pas ete arme (l'effet n'est pas la ou il faut).")
        return ko + 1
    if b_cas["use_special"] and not b_cib["use_special"]:
        print("    ANCRE = CASTER (mesure CONCORDANTE avec la RE d'`AbilityEntities$$.ctor`)")
    elif b_cib["use_special"] and not b_cas["use_special"]:
        print("    ANCRE = CIBLE -- la MESURE CONTREDIT la RE : le port est FAUX, ne pas livrer.")
        ko += 1
    else:
        print("    NON TRANCHE -- les deux bras repondent pareil ; la mesure ne separe pas.")
        ko += 1
    return ko


# ===================================================================== contre-epreuve

def contre_epreuve() -> int:
    """MUTATIONS du foyer -- chacune doit MORDRE. `a_mordu` est publie SEPAREMENT du verdict :
    une mutation qui ne change RIEN n'est pas une garde qui tient, c'est un test qui ne mesure rien.

    Aucun runner : tout est offline (le foyer est une fonction pure)."""
    import engine.services.custom_normal_attack as CNA
    print("=" * 78)
    print("CONTRE-EPREUVE -- mutations du foyer (0 runner)")
    print("=" * 78)
    na_ft, na_og = "FeederTendrils_NormalAttack", "OptimizedGait_NormalAttack"

    def etat():
        return (CNA.inform_weapon_use_special(na_ft, True, True),
                CNA.inform_weapon_use_special(na_ft, True, False),
                CNA.inform_weapon_use_special(na_ft, False, True),
                CNA.inform_weapon_use_special(na_og, False, True, True),
                CNA.inform_weapon_use_special(na_og, True, True, False),
                CNA.feeder_tendrils_special_applies(na_ft, True, True),
                CNA.feeder_tendrils_special_applies(na_ft, True, False))

    ref = etat()
    print(f"  reference : {ref}")
    attendu = (True, False, False, True, False, True, False)
    ko = 0 if ref == attendu else 1
    if ko:
        print(f"  KO : reference {ref} != attendue {attendu}")

    muts = []

    def _m(nom, applique, restaure, doit_mordre=True):
        applique()
        try:
            got = etat()
        finally:
            restaure()
        a_mordu = got != ref
        muts.append((nom, a_mordu, doit_mordre, got))
        return a_mordu

    orig_ft = CNA._USE_SPECIAL_NORMAL_ATTACK
    orig_og = CNA._USE_SPECIAL_NORMAL_ATTACK_ON_EFFECT
    orig_gate = CNA.USE_SPECIAL_GATE_EFFECT
    orig_f = CNA.inform_weapon_use_special
    orig_g = CNA.feeder_tendrils_special_applies

    # M1 : le gate de FeederTendrils devient un `IsCharging` SEUL (le piege nomme).
    def m1():
        CNA.inform_weapon_use_special = (
            lambda n, is_charging, weapon_melee, caster_has_gate_effect=None:
            bool(is_charging) if n == orig_ft
            else orig_f(n, is_charging, weapon_melee, caster_has_gate_effect))
        CNA.feeder_tendrils_special_applies = (
            lambda n, is_charging, weapon_melee:
            n == orig_ft and bool(is_charging))
    _m("M1 gate FeederTendrils = IsCharging SEUL (sans IsMelee)", m1,
       lambda: (setattr(CNA, "inform_weapon_use_special", orig_f),
                setattr(CNA, "feeder_tendrils_special_applies", orig_g)))

    # M2 : le gate d'OptimizedGait ancre sur la CIBLE -- ici modelise en INVERSANT le predicat.
    def m2():
        CNA.inform_weapon_use_special = (
            lambda n, is_charging, weapon_melee, caster_has_gate_effect=None:
            (not caster_has_gate_effect) if n == orig_og
            else orig_f(n, is_charging, weapon_melee, caster_has_gate_effect))
    _m("M2 ancre d'OptimizedGait INVERSEE", m2,
       lambda: setattr(CNA, "inform_weapon_use_special", orig_f))

    # M3 : OptimizedGait retire du foyer (l'etat AVANT cette tranche).
    def m3():
        CNA._USE_SPECIAL_NORMAL_ATTACK_ON_EFFECT = "__aucune__"
    _m("M3 OptimizedGait retire du foyer (etat d'avant)", m3,
       lambda: setattr(CNA, "_USE_SPECIAL_NORMAL_ATTACK_ON_EFFECT", orig_og))

    # M4 : l'effet du gate devient un AUTRE effet (0x429 Pinned au lieu de 0x4e2).
    #      INERTE PAR ALGEBRE et c'est ASSERTIONNE : `USE_SPECIAL_GATE_EFFECT` n'est pas relu par
    #      le foyer (le call-site le lit et passe un BOOLEEN). La garde de cette constante est donc
    #      le call-site de `normal.py`, pas ce foyer -- et le dire est le resultat.
    def m4():
        CNA.USE_SPECIAL_GATE_EFFECT = PINNED
    m4_mordu = _m("M4 effet du gate 0x4e2 -> 0x429 (INERTE ATTENDU sur le foyer)", m4,
                  lambda: setattr(CNA, "USE_SPECIAL_GATE_EFFECT", orig_gate),
                  doit_mordre=False)

    # M5 : FeederTendrils retire du foyer.
    def m5():
        CNA._USE_SPECIAL_NORMAL_ATTACK = "__aucune__"
    _m("M5 FeederTendrils retire du foyer", m5,
       lambda: setattr(CNA, "_USE_SPECIAL_NORMAL_ATTACK", orig_ft))

    print("-" * 78)
    print("  | mutation                                              | a_mordu | attendu | verdict")
    for nom, a_mordu, doit, got in muts:
        v = "OK" if a_mordu == doit else "KO"
        ko += (v == "KO")
        print(f"  | {nom:<52} | {str(a_mordu):<7} | {str(doit):<7} | {v}")
    print("-" * 78)
    print("  M4 est INERTE PAR ALGEBRE, et c'est MESURE, pas subi : le foyer recoit un BOOLEEN "
          "deja resolu,")
    print("  donc la constante d'effet ne peut pas l'atteindre. Son gardien est le call-site "
          "(`normal.py`),")
    print("  ce que l'etage 4 du test offline assertionne DANS LES DEUX SENS.")
    if CNA.USE_SPECIAL_GATE_EFFECT != orig_gate or CNA._USE_SPECIAL_NORMAL_ATTACK != orig_ft:
        print("  KO : le foyer n'a pas ete restaure")
        ko += 1
    return ko


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=41902)
    ap.add_argument("--volet", default="both", choices=["1", "2", "both"])
    ap.add_argument("--contre-epreuve", action="store_true")
    a = ap.parse_args(argv)
    if a.contre_epreuve:
        ko = contre_epreuve()
        print(f"\n[nasp] contre-epreuve : {'PASS' if ko == 0 else 'FAIL'} ({ko} ecart(s))")
        return 0 if ko == 0 else 1
    ko = 0
    if a.volet in ("1", "both"):
        ko += volet1(a.seed)
    if a.volet in ("2", "both"):
        ko += volet2(a.seed)
    print(f"\n[nasp] {'PASS' if ko == 0 else 'FAIL'} ({ko} ecart(s))")
    return 0 if ko == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
