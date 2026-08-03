"""#419-r1 tranche 14 -- MONTAGE NOMME de la face ATTACK de `HeavyBoltPistol` (1083), natif contre
port.

`IdunBattle.AI.Playbook.Loki.HeavyBoltPistolPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__2$$MoveNext`
rend l'utilite (composite Damage) d'une prediction de montant PREDEFINI `dmg[niveau du passif]`,
hits FORCES 1, au profil de l'ABILITY (`Bolter`), contre `case.Target` -- et RIEN si le caster n'est
pas DEJA au contact de sa cible. RE complete et lectures non devinables :
`engine/playbook/heavy_bolt_pistol.py` (en-tete).

## L'inventaire du nom -- TROIS artefacts sous l'id 1083

`TriggeredAbilityType.HeavyBoltPistol = 1083` (CE playbook), `ActiveAbilityType.NeedsMoreDakka = 1083`,
`EffectType.ChampionOfTheFeast_ReduceArmor = 1083`. `gameconfig.ability_name(1083)` rend
**"NeedsMoreDakka"** : toute lecture de config passe par le NOM.

## Pourquoi une GREFFE, et sur quel hote

Les 2 porteurs de 1083 sont le npc `templNpc1Initiate` et le SUMMON `templInitiate`.
`buildNormalizedBC` refuse tout npc, et le summon n'a **AUCUN invocateur-unite** : le balayage
prescrit par `case-92` §5bis recours 2 rend DEUX abilities qui le declarent
(`EnvFactionSummons:BlackTemplars` et `EnvFactionSummons:SpaceWolves`, `nrOfSummons` 3), que
**personne** ne porte dans `activeAbilities`/`passiveAbilities` -- c'est un summon d'ENVIRONNEMENT.
La voie « spawner son summoner » n'existe donc pas, il ne reste que le recours 3.

La greffe est LEGITIME et c'est LU, pas suppose : le corps ne consulte du caster QUE son identite
(pipeline modifiers), sa position, et le NIVEAU de son propre passif 1083 -- ni arme (le profil est
`AbilityConfiguration.GetDamageProfile` = `Bolter`), ni stat, ni trait.

## Le BRAS APPARIE -- ce qui rend le terme MESURABLE cote NATIF

Deux runners, IDENTIQUES en tout sauf le passif greffe :

    `graft` : `BC.Units[<hote>].PassiveAbilities = [1083]`
    `base`  : `BC.Units[<hote>].PassiveAbilities = []`     (le bras `graft` MOINS 1083)

`terme_natif = natif_graft - natif_base` sur la MEME paire, la MEME tuile et la MEME geometrie.
⚠ Le bras `base` est le bras greffe MOINS 1083, surtout PAS « les passifs d'origine de l'hote » :
`replace=True` les a deja retires (piege mesure par #419-r1-tr9).

## Les QUATRE crans, et ce que chacun est SEUL a trancher

La cible `T` ne bouge JAMAIS. Le caster occupe deux emplacements, et on evalue depuis DEUX tuiles
d'attaque -- c'est le produit croise qui est discriminant, parce que la gate du corps et la
prediction n'ont PAS la meme ancre (en-tete du module, lectures 1 et 2) :

    cran                position REELLE de C   tuile d'attaque   terme attendu
    `adj`               A (adjacente a T)      A                 > 0
    `realAdj_tileFar`   A (adjacente a T)      B (loin de T)     > 0   <- la gate lit le REEL
    `far`               B (loin de T)          B                 = 0
    `tileAdj_realFar`   B (loin de T)          A (adjacente)     = 0   <- la gate IGNORE la tuile

⚠ Les deux crans DIAGONAUX sont LES crans de cette tranche. Tous les playbooks attack portes qui
gatent sur une geometrie le font depuis la TUILE D'ATTAQUE (`avalanche_of_muscle` :
`<slot 0x60>(casterTile, target)` ; `cosmic_horror` : `case.CasterPosition.MainTile` ;
`special_issue_combi_melta` : distance cible <-> tuile d'attaque). Celui-ci gate sur la position
REELLE, parce que son trigger DSL prend deux ENTITES. Un port ecrit par analogie se tromperait sur
les deux diagonales -- et sur AUCUN des deux crans alignes.

`adj` et `realAdj_tileFar` different en outre par `is_melee` (vrai depuis A, faux depuis B) : le
terme n'y est pas le meme nombre, et c'est le second fait que le montage installe.

## Contre-epreuves -- critere = DEPLACEMENT par rapport au port NON MUTE

Jamais l'ecart au natif : un mutant inerte le franchirait aussi (piege #441/#446).

  `gate_tile`       -- gate d'adjacence sur la TUILE D'ATTAQUE  -> mord sur les DEUX diagonales
  `no_gate`         -- aucune gate d'adjacence                  -> mord en `far` et `tileAdj_realFar`
  `melee_from_real` -- `is_melee` depuis la position REELLE     -> mord en `realAdj_tileFar`
  `profile_weapon`  -- profil = l'arme du caster, pas `Bolter`  -> mord la ou le terme existe
  `amount_half`     -- montant `dmg` divise par deux            -> mord la ou le terme existe
  `spread0`         -- `spread_pct = 0` (pas de +/-20 %)        -> mord la ou le terme existe

Chaque mutant est joue a TOUS les crans ; la reciproque compte autant : aucun ne doit mordre sur un
cran ou le terme natif est nul, sauf `no_gate` et `gate_tile`, dont c'est precisement la signature.

Usage :
    python scripts/python/probe_419r1tr14_heavy_bolt_pistol.py --state-file <chemin ABSOLU>
        [--state-file-base <chemin ABSOLU>] [--mutants]

ASCII only. Garde jumelle :
`scripts/python/tests/engine/test_419r1tr14_heavy_bolt_pistol_live.py`.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import catalog_inject                                            # noqa: E402
import gameconfig as GC                                          # noqa: E402
import hexgeo                                                    # noqa: E402
import probe_124_line_elevation_decision as P124                 # noqa: E402
import probe_380_seed_bc_patch_survival as P380                  # noqa: E402
from engine import battle_query as bq                            # noqa: E402
from engine import weights as W                                  # noqa: E402
from engine.ai import context as _ai_ctx                         # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType   # noqa: E402
from engine.playbook import scene as _scene                      # noqa: E402
from engine.playbook.common import NORMAL_ATTACK_PLAYBOOK        # noqa: E402
from engine.runner.abilities.attack_type import is_regular_attack  # noqa: E402

BOARD = "MC1_67"
SEED = "41083"
HOST = "tauMarksman"            # HERO au pool, arme distance `Piercing` portee 3 -- `replace=True`
ALLY = "necroWarden"            # garage ami (n'entre dans aucun terme : le corps ne compte rien)
T_MAIN = "astraBullgryn"        # la cible, FIXE dans tous les crans
FOE1 = "astraCreed"             # garage ennemi
FOES = (T_MAIN, FOE1)
MINE = (HOST, ALLY)

ABILITY = int(TriggeredAbilityType.HeavyBoltPistol)              # 1083
EPS = 1e-4                      # Fix64 natif contre float du port
HP = 10000                      # personne ne meurt (dmg ~1091 x 1.2 << HP), et le composite
                                # DamageDealt reste dans sa zone LINEAIRE -> les mutants d'echelle
                                # (`amount_half`, `spread0`) deplacent visiblement le terme
ATTACK_RANGE = 3                # arme distance de `tauMarksman` -- RE-ATTESTEE au montage

# (emplacement REEL du caster, tuile d'attaque) par cran, et le terme natif attendu NON NUL.
# ORDRE : les deux emplacements sont groupes (B puis A) pour ne driver les unites que DEUX fois, et
# le cran a terme NON NUL est place en DERNIER -- c'est celui sur lequel la garde de CABLAGE
# (`triggered_abilities_attack_utility`) est evaluee, et un cran a terme nul n'y prouverait rien.
STEPS = (("far", "B", "B", False),
         ("tileAdj_realFar", "B", "A", False),
         ("adj", "A", "A", True),
         ("realAdj_tileFar", "A", "B", True))
MUTANTS = ("gate_tile", "no_gate", "melee_from_real", "profile_weapon", "amount_half", "spread0")


class MontageError(RuntimeError):
    """Le montage ne s'installe pas -- la mesure n'a PAS eu lieu (jamais un vert silencieux)."""


# --------------------------------------------------------------------------- oracles

def pair_native(rpc, rid, cid, tgt, ab, tile) -> float:
    r = rpc("pairUtility", {"runnerId": rid, "unitId": cid, "targetId": tgt,
                            "abilityType": ab, "col": tile[0], "row": tile[1]}, 90)
    v = (r or {}).get("utility")
    if not isinstance(v, (int, float)):
        raise MontageError(f"pairUtility natif indisponible pour {tile} / cible {tgt}: {r}")
    return float(v)


def pair_port(ctx, ab, tgt, tile) -> float:
    cand = NORMAL_ATTACK_PLAYBOOK.calculate_action_utility(ctx, tile, tgt, ab)
    if cand is None:
        raise MontageError(f"le port ne produit AUCUNE action depuis {tile} sur {tgt}")
    return float(cand["u"])


def pair_port_muted(ctx, ab, tgt, tile) -> float:
    """Le port avec le playbook 1083 RETIRE du registre -- la reference qui isole le terme cote
    PORT, exactement comme le bras `base` l'isole cote NATIF."""
    import engine.playbook.psyker as PSY
    saved = PSY.TRIGGERED_ATTACK_PLAYBOOKS.pop(ABILITY, None)
    if saved is None:
        raise MontageError(f"le playbook {ABILITY} n'est PAS au registre -- rien a isoler")
    try:
        return pair_port(ctx, ab, tgt, tile)
    finally:
        PSY.TRIGGERED_ATTACK_PLAYBOOKS[ABILITY] = saved


# --------------------------------------------------------------------------- seed BC (les 2 bras)

def seed_bc(logs_dir: str, arm: str) -> str:
    """Le seed BC du bras `graft` (1083 monte sur l'hote) ou `base` (le MEME, moins 1083)."""
    out = os.path.join(logs_dir, f"hbp_{arm}_seedbc.json")
    p, reports = catalog_inject.write_grafted_seed_bc(
        out, [f"{HOST}:{TriggeredAbilityType(ABILITY).name}"], replace=True)
    after = list((reports[0] or {}).get("passiveAbilitiesAfter") or ())
    if ABILITY not in after:
        raise MontageError(f"greffe RATEE : PassiveAbilities={after} ne contient pas {ABILITY}")
    if arm == "base":
        bc = json.loads(open(p, encoding="utf-8").read())
        for u in (bc.get("Units") or ()):
            if u.get("Id") == HOST:
                u["PassiveAbilities"] = [a for a in after if a != ABILITY]
        open(p, "w", encoding="utf-8").write(json.dumps(bc))
    P380.assert_survives(p)
    return str(p)


def build_args(logs_dir: str, arm: str) -> list:
    """Les arguments `rl_duel build` du bras demande, SANS `--seed` ni `--state-file`."""
    stats = ";".join(f"{v}:Health={HP},RemainingHealth={HP}" for v in MINE + FOES)
    return ["--board", BOARD, "--p-units", ",".join(MINE), "--a-units", ",".join(FOES),
            "--unit-stat", stats, "--seed-bc", seed_bc(logs_dir, arm)]


# --------------------------------------------------------------------------- geometrie

def find_layout(cells: list, elev: dict) -> "dict | None":
    """Cherche `(T, A, B, K1, K2)` satisfaisant EXACTEMENT le regime decrit en tete.

    `A` voisin NATIF de `T` (`bq.is_adjacent`, porte d'elevation comprise) ; `B` NON adjacent a `T`,
    a portee de tir (`2 <= dist(B,T) <= ATTACK_RANGE`) et a `dist(A,B) <= 2` pour que le caster
    (Movement 2) puisse faire l'aller-retour A <-> B ; `K1`/`K2` deux garages ni adjacents a `T`, ni
    sur `A`/`B`."""
    d = hexgeo.distance
    for t in cells:
        adj = [q for q in hexgeo.neighbors(t[0], t[1]) if q in set(cells) and bq.is_adjacent(t, q, elev)]
        for a in adj:
            bs = [q for q in cells
                  if q not in (t, a) and not bq.is_adjacent(t, q, elev)
                  and 2 <= d(q, t) <= ATTACK_RANGE and 1 <= d(a, q) <= 2]
            for b in bs:
                busy = {t, a, b}
                garages = [q for q in cells
                           if q not in busy and not bq.is_adjacent(t, q, elev)
                           and d(q, t) >= 2 and d(q, a) >= 2 and d(q, b) >= 2]
                picked = []
                for q in garages:
                    if all(d(q, o) >= 2 for o in picked):
                        picked.append(q)
                    if len(picked) == 2:
                        break
                if len(picked) == 2:
                    return {"T": t, "A": a, "B": b, "K1": picked[0], "K2": picked[1]}
    return None


def attest_layout(lay: dict, elev: dict) -> None:
    """RE-MESURE le regime geometrique et refuse s'il n'est pas celui voulu. C'est l'arbitre des
    crans, jamais le port."""
    d = hexgeo.distance
    checks = [
        ("A adjacente a T", bq.are_entities_adjacent(lay["A"], lay["T"], elev)),
        ("B NON adjacente a T", not bq.are_entities_adjacent(lay["B"], lay["T"], elev)),
        ("B a portee de tir de T", d(lay["B"], lay["T"]) <= ATTACK_RANGE),
    ]
    bad = [name for name, ok in checks if not ok]
    if bad:
        raise MontageError(f"layout NON INSTALLE : contraintes violees {bad} -- {lay}")


# --------------------------------------------------------------------------- montage

def _fresh_ctx(rpc, rid, cid):
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mbu = {u.get("unitId"): u for u in (mov.get("units") or [])}
    return dv, _ai_ctx.build(rpc, rid, dv, mbu, cid, W.load(), _scene.build_predictor(rpc, rid))


def _roster(rpc, rid: int) -> tuple:
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    units = dv.get("units") or []
    mine = [u for u in units if u.get("ctrl") and u.get("alive")]
    if not mine:
        raise MontageError("montage NON INSTALLE : aucune unite controlee")
    myplayer = mine[0].get("owner")
    ids = {}
    for key, vis in (("C", HOST), ("F", ALLY)):
        u = next((x for x in mine if x.get("visualId") == vis), None)
        if u is None:
            raise MontageError(f"montage NON INSTALLE : {vis} absent du roster ami")
        ids[key] = u["id"]
    for key, vis in (("T", T_MAIN), ("E1", FOE1)):
        u = next((x for x in units if x.get("owner") != myplayer and x.get("alive")
                  and x.get("visualId") == vis), None)
        if u is None:
            raise MontageError(f"montage NON INSTALLE : {vis} absent du roster adverse")
        ids[key] = u["id"]
    return dv, ids, myplayer


def _attest_wired(rpc, rid: int, cid: int, expect_ability: bool) -> list:
    """Moitie CABLAGE du patron #419 : 1083 est-il DANS l'`AbilitiesComponent` du caster ? Et quels
    AUTRES playbooks du registre y sont ? Le bras apparie neutralise ces derniers par difference,
    mais on les IMPRIME plutot que de les supposer absents."""
    import engine.playbook.psyker as PSY
    st = rpc("unitAbilityStates", {"runnerId": rid, "unitId": cid}, 60) or {}
    live = sorted({i for u in (st.get("units") or []) for t in (u.get("triggered") or [])
                   for i in [((t.get("raw") or [None])[0])] if isinstance(i, int)})
    has = ABILITY in live
    if has != expect_ability:
        raise MontageError(
            f"montage NON INSTALLE : {ABILITY} {'absent' if expect_ability else 'PRESENT'} de "
            f"l'AbilitiesComponent de {HOST} (attendu {'present' if expect_ability else 'absent'})"
            f" -- triggered live lus = {live}")
    return [i for i in live if i in PSY.TRIGGERED_ATTACK_PLAYBOOKS and i != ABILITY]


def stage(sid, rpc, rid: int, layout: "dict | None", expect_ability: bool) -> dict:
    """Installe le montage sur UN runner. `layout` fourni -> il est REJOUE a l'identique (c'est ce
    qui apparie les deux bras) ; `None` -> il est cherche sur le board."""
    elev, walk, _tid = P124._board(sid, rid)
    _dv, ids, myplayer = _roster(rpc, rid)
    others = _attest_wired(rpc, rid, ids["C"], expect_ability)
    cells = sorted(p for p, wk in walk.items() if wk and elev.get(p) is not None)
    if not cells:
        raise MontageError("montage NON INSTALLE : boardGraph sans tuile walkable")
    lay = layout if layout is not None else find_layout(cells, elev)
    if lay is None:
        raise MontageError(f"montage NON INSTALLE : aucune configuration (T,A,B,K1,K2) sur {BOARD} "
                           f"-- les quatre crans ne seraient pas installables")
    attest_layout(lay, elev)
    return {"rid": rid, "cid": ids["C"], "ids": ids, "myplayer": myplayer,
            "layout": lay, "walk": walk, "elev": elev, "other_playbooks": others}


def place(sid, case: dict, spot: str) -> dict:
    """Amene le caster sur l'emplacement `spot` (`A` ou `B`), la cible sur `T`, les deux autres au
    garage, puis RE-MESURE les positions."""
    lay, ids = case["layout"], case["ids"]
    wanted = {ids["C"]: lay[spot], ids["T"]: lay["T"],
              ids["F"]: lay["K1"], ids["E1"]: lay["K2"]}
    if not P124._drive_to(sid, case["rid"], case["walk"], case["elev"], wanted):
        _dv, pos = P124._positions(sid, case["rid"])
        raise MontageError(f"emplacement {spot} NON INSTALLE (runner {case['rid']}) : placement "
                           f"incomplet -- voulu {wanted}, obtenu { {u: pos.get(u) for u in wanted} }")
    P124._give_turn_back(sid, case["rid"], case["myplayer"])
    _dv2, pos = P124._positions(sid, case["rid"])
    got_c, got_t = pos.get(ids["C"]), pos.get(ids["T"])
    if got_c != lay[spot] or got_t != lay["T"]:
        raise MontageError(f"emplacement {spot} NON INSTALLE : C={got_c} (voulu {lay[spot]}), "
                           f"T={got_t} (voulu {lay['T']})")
    return pos


# --------------------------------------------------------------------------- contre-epreuves

def _mutant_class(mutant: str, host_visual: str):
    """Sous-classe du port LIVRE dont UNE lecture est retournee. On derive du module reel : un
    mutant qui reimplemente tout ne prouverait rien sur le code livre."""
    from engine.playbook import heavy_bolt_pistol as HB

    class _Mut(HB.HeavyBoltPistolPlaybook):
        # `gate_tile` / `no_gate` : la gate d'adjacence, seule lecture retournee.
        def calculate_attack_utility_in_steps(self, ctx, attacker_uid, ability_id, case_tgt_id,
                                              attack_tile, prediction=None):
            if mutant not in ("gate_tile", "no_gate", "melee_from_real"):
                return super().calculate_attack_utility_in_steps(
                    ctx, attacker_uid, ability_id, case_tgt_id, attack_tile, prediction)
            sc = getattr(ctx, "scene", None)
            if sc is None or attack_tile is None:
                return 0.0
            if ability_id is None or not is_regular_attack(int(ability_id)):
                return 0.0
            tpos = sc.pos(case_tgt_id)
            elev = getattr(sc, "elev_by_pos", None)
            if mutant == "gate_tile":
                if tpos is None or not bq.are_entities_adjacent(tuple(attack_tile), tpos, elev):
                    return 0.0
            elif mutant == "melee_from_real":
                if not self.should_trigger(sc, attacker_uid, case_tgt_id):
                    return 0.0
            amount = self._damage(sc, attacker_uid)
            if not amount:
                return 0.0
            profile_name = self._profile_name()
            from engine.services.battle_query import is_melee_attack as _ima
            ab_name = (getattr(ctx, "ab_name_by_id", None) or {}).get(int(ability_id))
            anchor = sc.pos(attacker_uid) if mutant == "melee_from_real" else attack_tile
            melee = _ima(ab_name, anchor, tpos, elev)
            pred = self._predict_vs_target(sc, attacker_uid, case_tgt_id, int(amount), attack_tile,
                                           profile_name, melee)
            if pred is None:
                return 0.0
            from engine.playbook.probable_damage_event import (
                ProbableDamageEvent, calculate_utility_from_damage_event)
            cteam, tteam = sc.team(attacker_uid), sc.team(case_tgt_id)
            ev = ProbableDamageEvent(target=case_tgt_id, prediction=pred,
                                     friendly=(cteam is not None and tteam is not None
                                               and cteam == tteam))
            return calculate_utility_from_damage_event(ev, ctx.wt,
                                                       (ctx.hpmax_by_id or {}).get(case_tgt_id))

        # `profile_weapon` : le profil de l'ARME du caster au lieu de celui de l'ability.
        @staticmethod
        def _profile_name() -> str:
            if mutant != "profile_weapon":
                return HB.HeavyBoltPistolPlaybook._profile_name()
            ws = (GC.unit(host_visual) or {}).get("weapons") or []
            ranged = [w for w in ws if w.get("Range")]
            return ((ranged or ws)[0] or {}).get("DamageProfile") or ""

        # `amount_half` : le montant `dmg`, divise par deux.
        def _damage(self, scene, uid):
            v = super()._damage(scene, uid)
            if mutant == "amount_half" and v:
                return int(v) // 2
            return v

        # `spread0` : la prediction sans le spread +/-20 %.
        def _predict_vs_target(self, *a, **kw):
            if mutant != "spread0":
                return super()._predict_vs_target(*a, **kw)
            saved = HB.get_attack_prediction
            HB.get_attack_prediction = lambda **k: saved(**{**k, "spread_pct": 0})
            try:
                return super()._predict_vs_target(*a, **kw)
            finally:
                HB.get_attack_prediction = saved

    return _Mut


def measure_mutant_here(ctx, ab, tgt, tile, mutant: str, ref: float, host_visual: str) -> dict:
    """Le port MUTE sur la geometrie COURANTE (le cran qui vient d'etre place)."""
    import engine.playbook.psyker as PSY
    saved = PSY.TRIGGERED_ATTACK_PLAYBOOKS[ABILITY]
    PSY.TRIGGERED_ATTACK_PLAYBOOKS[ABILITY] = _mutant_class(mutant, host_visual)()
    try:
        got = pair_port(ctx, ab, tgt, tile)
    finally:
        PSY.TRIGGERED_ATTACK_PLAYBOOKS[ABILITY] = saved
    return {"mutant": mutant, "port": got, "port_ref": ref, "shift": got - ref}


def measure(sid, rpc, graft: dict, base: dict, mutants: bool = False) -> tuple:
    """Un cran = un emplacement IDENTIQUE sur les deux bras + une tuile d'attaque, puis quatre
    nombres : `nat_graft`, `nat_base` (leur DIFFERENCE est le terme natif), `port` et `port_muted`
    (leur difference est le terme porte). Les contre-epreuves sont jouees PENDANT que le cran est
    installe."""
    rows, muts = [], []
    placed = {"graft": None, "base": None}
    for step, spot, tile_key, expect_term in STEPS:
        if placed["graft"] != spot:
            place(sid, graft, spot)
            place(sid, base, spot)
            placed["graft"] = placed["base"] = spot
        lay = graft["layout"]
        tile = lay[tile_key]
        _dvg, ctx = _fresh_ctx(rpc, graft["rid"], graft["cid"])
        graft["ctx"] = ctx
        ab = next(iter(ctx.normal_ids or ()), None)
        if ab is None:
            raise MontageError("montage NON INSTALLE : aucune attaque normale sur le caster")
        if not is_regular_attack(int(ab)):
            raise MontageError(f"montage NON DISCRIMINANT : l'attaque normale {ab} de {HOST} n'est "
                               f"pas dans `REGULAR_ATTACK_ABILITY_TYPES` -- la gate du corps natif "
                               f"couperait le terme a TOUS les crans")
        if tile not in [t for t in (ctx.action_tiles or []) if t and t[0] is not None]:
            raise MontageError(f"cran {step} NON MESURABLE : tuile {tile} hors des tuiles d'action "
                               f"du caster (emplacement {spot})")
        tgt = graft["ids"]["T"]
        nat_g = pair_native(rpc, graft["rid"], graft["cid"], tgt, ab, tile)
        nat_b = pair_native(rpc, base["rid"], base["cid"], base["ids"]["T"], ab, tile)
        port = pair_port(ctx, ab, tgt, tile)
        muted = pair_port_muted(ctx, ab, tgt, tile)
        rows.append({"step": step, "spot": spot, "tile": tile, "ab": ab, "expect_term": expect_term,
                     "native_graft": nat_g, "native_base": nat_b, "native_term": nat_g - nat_b,
                     "port": port, "port_muted": muted, "port_term": port - muted})
        if mutants:
            for m in MUTANTS:
                r = measure_mutant_here(ctx, ab, tgt, tile, m, port, HOST)
                r["step"] = step
                muts.append(r)
    return rows, muts


# --------------------------------------------------------------------------- CLI

def _build(state_file: str, extra: list) -> int:
    argv = [sys.executable, "rl_duel.py", "build", "--seed", SEED,
            "--state-file", state_file, *extra]
    p = subprocess.run(argv, cwd=_HERE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise MontageError(f"rl_duel build a echoue (rc={p.returncode}) : "
                           f"{(p.stderr or p.stdout or '')[-800:]}")
    return int(json.load(open(state_file, encoding="utf-8"))["runnerId"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True,
                    help="chemin ABSOLU du state-file du bras GREFFE")
    ap.add_argument("--state-file-base",
                    help="chemin ABSOLU du state-file du bras APPARIE (defaut : <state-file>_base)")
    ap.add_argument("--mutants", action="store_true",
                    help="joue les six contre-epreuves a CHAQUE cran (elles doivent MORDRE)")
    args = ap.parse_args()

    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()

    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    sf_g = args.state_file
    sf_b = args.state_file_base or (os.path.splitext(sf_g)[0] + "_base.json")
    logs = os.path.dirname(os.path.abspath(sf_g))
    os.makedirs(logs, exist_ok=True)

    rid_g = _build(sf_g, build_args(logs, "graft"))
    rid_b = _build(sf_b, build_args(logs, "base"))
    graft = stage(sid, rpc, rid_g, None, True)
    base = stage(sid, rpc, rid_b, graft["layout"], False)
    lay = graft["layout"]
    print(f"runners graft={rid_g} base={rid_b} | hote {HOST} u{graft['cid']}")
    print(f"  layout T={lay['T']} A={lay['A']} B={lay['B']} K1={lay['K1']} K2={lay['K2']}")
    if graft["other_playbooks"]:
        print(f"  NB autres playbooks du registre sur le caster : {graft['other_playbooks']} "
              f"(neutralises par le bras apparie)")

    rows, muts = measure(sid, rpc, graft, base, mutants=args.mutants)
    for r in rows:
        print(f"  [{r['step']:<16}] spot={r['spot']} tile={r['tile']} "
              f"natG={r['native_graft']:.6f} natB={r['native_base']:.6f} "
              f"TERME_NAT={r['native_term']:+.6f} | port={r['port']:.6f} "
              f"mute={r['port_muted']:.6f} TERME_PORT={r['port_term']:+.6f} "
              f"ecart={r['port_term'] - r['native_term']:+.9f}")
    for m in muts:
        print(f"  [mutant {m['mutant']:<16} @{m['step']:<16}] deplacement du port = "
              f"{m['shift']:+.9f} ({'MORD' if abs(m['shift']) > EPS else 'inerte'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
