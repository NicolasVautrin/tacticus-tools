"""#419-r1-tr9-r4 -- DECOMPOSITION PAR ETAGE de l'ecart de PREDICTION sur l'attaque normale
CONCRETE `1128 Boltstorm_NormalAttack` (`templAggressor`), et sa fermeture.

Le releve de #419-r1-tr9 (regime `foreign`) donnait, contre `necroWarden` :

    port  [1762, 2642]      natif [ 876, 1314]

soit un rapport ~2.01 sur les DEUX bornes -- alors que le MEME montage rendait, contre
`astraBullgryn`, `port [2628, 3942]` / `natif [2631, 3945]`. L'ecart n'etait donc NI un doublement
structurel du fold NI un residu de base : il etait PAR CIBLE.

Ce probe ne fitte AUCUN scalaire. Il decompose la prediction en ses DEUX etages natifs
(`IdunBattleLogic.Entities.Abilities.Active.Loki.Boltstorm_NormalAttackAbility$$PredictAttack` =
`ALoki_NormalAttackAbility$$PredictAttack` + `GetAdditionalDamagePrediction`, sommes par
`IdunBattle.Core.Services.DamagePredictionResult$$Add`) et mesure CHAQUE etage des deux cotes :

    ETAGE 1 -- BASE : bras APPARIE `--unit-stat templAggressor:PassiveAbilities=[]` (l'attaque
              normale retombe a la generique `69`, aucun fold natif) contre le port avec le registre
              `_RANGED_FOLLOWUP_PASSIVES` VIDE. Meme board, meme seed, meme placement, memes stats
              -- appariement par `visualId`.
    ETAGE 2 -- FOLD : `total - base`, des deux cotes. `DamagePredictionResult$$Add` etant une somme
              champ a champ, la soustraction est EXACTE cote natif.

CE QUE LA MESURE A TROUVE. Le champ qui portait tout l'ecart est `appliedHits` : natif `h2`
(1 de base + 1 de fold), port `h4` (1 + `nrOfHits` = 3). La cible etait sur une tuile `DryBush`,
donc porteuse de l'effet `LightCover` (-2 coups) -- et le natif applique ce malus AU FOLD AUSSI.
Le decompile le dit : `GetAdditionalDamagePrediction` passe `GetNumberConstant(cfg, 0x2f)` au slot
`0xb5` de l'`IBattleQuery` (= `IdunBattle.Core.Services.BattleQuery$$GetAttackHits` ->
`IdunBattle.Core.Services.DamagePrediction$$GetAttackHits`), avec le MEME couple (caster, cible)
que la base. `nrOfHits` est donc la BASE D'ARME du fold, pas son compte de coups.

## Les trois regimes, et ce que chacun est SEUL a trancher

| regime | ce qu'il installe | ce qu'il tranche |
|---|---|---|
| `plain` | 3 cibles a distance 2, MEME elevation, hors cover, non adjacentes | le socle : sans malus de coups, base et fold valent `weaponHits` et `nrOfHits` -- c'est le regime ou l'ancien port etait DEJA juste (garde de non-regression) |
| `cover` | une cible sur `DryBush` -> effet `LightCover` (-2 coups, cap a 1) | que le malus DEFENSEUR traverse le fold |
| `bigtarget` | une cible ADJACENTE a `astraBullgryn` (trait `BigTarget`, -1 coup RANGED aux allies adjacents) | la MEME conclusion par une source DIFFERENTE : une AURA d'allie de la cible, d'amplitude -1 et non -2 |

Le regime `bigtarget` n'est pas un doublon de `cover` : il change a la fois la PROVENANCE du malus
(aura d'un tiers vs effet porte par la cible) et son AMPLITUDE. Un port qui n'aurait cable que le
canal `LightCover` au fold passerait `cover` et echouerait `bigtarget`.

## Contre-epreuves -- critere = DEPLACEMENT par rapport au port NON MUTE

Jamais l'ecart au natif : la paire peut porter des residus hors perimetre, donc
`abs(port - natif) > EPS` serait vrai meme pour un mutant inerte.

  `hits_raw`   -- le fold reprend `nrOfHits` BRUT (l'etat d'avant le fix)
  `fold_twice` -- le fold applique DEUX fois (l'hypothese « etage compte deux fois »)
  `amount_min` -- montant du fold = `minDmg` seul (l'ancienne lecture « slot 4 = MIN »)

Usage :
    python scripts/python/probe_419r1tr9_r4_boltstorm_pred.py --state-file <chemin ABSOLU>
        [--regime plain|cover|bigtarget] [--mutants] [--no-baseline]

ASCII only. Garde jumelle :
`scripts/python/tests/engine/test_419r1tr9_r4_boltstorm_pred_live.py`.
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

import hexgeo                                                    # noqa: E402
import probe_124_line_elevation_decision as P124                 # noqa: E402
from engine import weights as W                                  # noqa: E402
from engine.ai import context as _ai_ctx                         # noqa: E402
from engine.entities.effects.loki.hits import LIGHT_COVER_TILE_ID  # noqa: E402
from engine.playbook import scene as _scene                      # noqa: E402

BOARD = "MC1_67"
SEED = "41904"
CASTER = "templAggressor"          # HERO au pool ; `Boltstorm` (1090) est son SEUL passif, et son
                                   # attaque normale CONCRETE est `1128 Boltstorm_NormalAttack`.
BIG_TARGET = "astraBullgryn"       # porte le trait `BigTarget` -- la source d'aura du 3e regime
FOES = ("astraBullgryn", "tauAunShi", "necroWarden")
HP = 40000                         # personne ne meurt : `Health` ET `RemainingHealth` (#438)
REGIMES = ("plain", "cover", "bigtarget", "melee")
# La cible sur laquelle le regime installe son malus (les autres restent des temoins SANS malus,
# et leur accord est ce qui interdit de lire un fix global la ou on veut un fix cible).
FOCUS = {"plain": None, "cover": "necroWarden", "bigtarget": "tauAunShi", "melee": "tauAunShi"}
# Le regime `melee` change de PORTEUR : `adeptMorvenn` porte `RighteousRepugnance`, le mold JUMEAU
# (corps identique, gate INVERSE `IsMelee`), et surtout son arme melee fait **2** coups quand
# `RighteousRepugnance.nrOfHits` en vaut **3**. C'est le SEUL regime qui distingue
# `weapon_hits = nrOfHits` de `weapon_hits = <coups de l'arme>` -- sur `templAggressor` les deux
# valent 3 et la mesure ne trancherait rien (le decompile, lui, tranche : `GetNumberConstant(0x2f)`).
CASTER_OF = {"plain": CASTER, "cover": CASTER, "bigtarget": CASTER, "melee": "adeptMorvenn"}
MUTANTS = ("hits_raw", "hits_from_base", "amount_min")


class MontageError(RuntimeError):
    """Le montage ne s'installe pas -- la mesure n'a PAS eu lieu (jamais un vert silencieux)."""


# --------------------------------------------------------------------------- montage

def build_args(regime: str, arm: str = "kit") -> list:
    """Arguments `rl_duel build` du bras demande, SANS `--seed` ni `--state-file`.

    `kit`  : le kit d'origine -- le passif monte, attaque normale CONCRETE (`1128` / `1182`).
    `base` : MEME bataille, `<caster>:PassiveAbilities=[]` -- l'attaque normale retombe a la
             generique `69` et le natif ne folde plus. C'est le bras qui rend la BASE NATIVE
             mesurable (protocole de #446-r1 SS4)."""
    caster = CASTER_OF[regime]
    stats = ";".join(f"{v}:Health={HP},RemainingHealth={HP}" for v in (caster,) + FOES)
    if arm == "base":
        stats += f";{caster}:PassiveAbilities=[]"
    return ["--board", BOARD, "--p-units", caster, "--a-units", ",".join(FOES),
            "--unit-stat", stats]


def _build(state_file: str, regime: str, arm: str = "kit") -> int:
    argv = [sys.executable, "rl_duel.py", "build", "--seed", SEED,
            *build_args(regime, arm), "--state-file", state_file]
    p = subprocess.run(argv, cwd=_HERE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise MontageError(f"rl_duel build a echoue (rc={p.returncode}) : "
                           f"{(p.stderr or p.stdout or '')[-800:]}")
    return int(json.load(open(state_file, encoding="utf-8"))["runnerId"])


def _fresh_ctx(rpc, rid, cid):
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mbu = {u.get("unitId"): u for u in (mov.get("units") or [])}
    return dv, _ai_ctx.build(rpc, rid, dv, mbu, cid, W.load(), _scene.build_predictor(rpc, rid))


def _normal_ability_id(rpc, rid, uid) -> int:
    """L'`ActiveAbilityType` CONCRET de l'attaque normale de `uid` (`abilityTargets`, `kind ==
    normal`) -- `1128` avec le passif, `69` sans lui."""
    r = rpc("abilityTargets", {"runnerId": rid, "unitId": uid}, 60) or {}
    for u in (r.get("units") or ()):
        if u.get("unitId") != uid:
            continue
        for a in (u.get("abilities") or ()):
            if a.get("kind") == "normal":
                return int(a.get("abilityId"))
    raise MontageError(f"u{uid} n'a pas d'attaque normale au canal abilityTargets")


def _ring2(c, cells, elev, walk, *, same_elev: bool, cover: bool | None, tid):
    """Tuiles a distance EXACTEMENT 2 de `c`, atteignables a pied. `cover=None` = indifferent,
    `True`/`False` = filtre sur `DryBush` (le terrain qui porte `LightCover`).

    Distance 2, jamais 1 : l'adjacence basculerait l'arme en MELEE et changerait le regime de degat
    d'une cible a l'autre -- or la gate du mold RANGED est precisement `!weapon.IsMelee`."""
    out = []
    for q in cells:
        if q == c or hexgeo.distance(c, q) != 2:
            continue
        if same_elev and elev.get(q) != elev.get(c):
            continue
        if cover is not None and (tid.get(q) == LIGHT_COVER_TILE_ID) != cover:
            continue
        if not P124._gated_path(c, q, walk, elev):
            continue
        out.append(q)
    return out


def _find_layout(cells, elev, walk, tid, regime: str):
    """`(C, {visualId: tuile})` pour le regime demande. Chaque regime IMPOSE sa geometrie -- on
    DEPLACE les unites, on ne subit jamais le placement de spawn."""
    ctr = (sum(c for c, _ in cells) / len(cells), sum(r for _, r in cells) / len(cells))
    for c in sorted(cells, key=lambda q: (q[0] - ctr[0]) ** 2 + (q[1] - ctr[1]) ** 2):
        if len(P124._move_ring(c, walk, elev)) < 3:
            continue
        if regime == "plain":
            # Trois cibles isolees les unes des autres, meme elevation, hors cover : AUCUN malus de
            # coups n'est en jeu -- c'est le socle de non-regression.
            free = _ring2(c, cells, elev, walk, same_elev=True, cover=False, tid=tid)
            picked = []
            for q in free:
                if all(hexgeo.distance(q, r) >= 2 for r in picked):
                    picked.append(q)
                if len(picked) == 3:
                    return c, dict(zip(FOES, picked))
            continue
        if regime == "cover":
            cov = _ring2(c, cells, elev, walk, same_elev=False, cover=True, tid=tid)
            free = _ring2(c, cells, elev, walk, same_elev=False, cover=False, tid=tid)
            for qc in cov:
                picked = [q for q in free if hexgeo.distance(q, qc) >= 2]
                keep = []
                for q in picked:
                    if all(hexgeo.distance(q, r) >= 2 for r in keep):
                        keep.append(q)
                    if len(keep) == 2:
                        break
                if len(keep) == 2:
                    pos = {FOCUS["cover"]: qc}
                    pos.update(dict(zip([f for f in FOES if f != FOCUS["cover"]], keep)))
                    return c, pos
            continue
        if regime == "melee":
            # La cible mesuree AU CONTACT du caster (`FindAttackWeapon` prend alors l'arme melee ->
            # gate `IsMelee` du mold `RighteousRepugnance` SATISFAITE), les deux autres a distance 2
            # (arme RANGED -> gate NON satisfaite : elles sont les temoins de la gate).
            near = [q for q in P124._move_ring(c, walk, elev) if q in set(cells)]
            free = _ring2(c, cells, elev, walk, same_elev=True, cover=False, tid=tid)
            for qf in near:
                rest = [q for q in free if hexgeo.distance(q, qf) >= 2]
                keep = []
                for q in rest:
                    if all(hexgeo.distance(q, r) >= 2 for r in keep):
                        keep.append(q)
                    if len(keep) == 2:
                        break
                if len(keep) == 2:
                    pos = {FOCUS["melee"]: qf}
                    pos.update(dict(zip([f for f in FOES if f != FOCUS["melee"]], keep)))
                    return c, pos
            continue
        # `bigtarget` : la cible mesuree ADJACENTE au porteur de `BigTarget`, les deux a distance 2
        # du caster et hors cover (sinon les deux malus se cumuleraient et le regime ne
        # discriminerait plus lequel traverse).
        free = _ring2(c, cells, elev, walk, same_elev=False, cover=False, tid=tid)
        for qb in free:
            adj = [q for q in free if q != qb and hexgeo.distance(q, qb) == 1
                   and P124._gated_path(qb, q, walk, elev)]
            for qf in adj:
                rest = [q for q in free if hexgeo.distance(q, qb) >= 2
                        and hexgeo.distance(q, qf) >= 2]
                if rest:
                    third = [f for f in FOES if f not in (BIG_TARGET, FOCUS["bigtarget"])][0]
                    return c, {BIG_TARGET: qb, FOCUS["bigtarget"]: qf, third: rest[0]}
    return None, None


def _attest(case: dict, regime: str) -> None:
    """Le regime est-il REELLEMENT installe ? Un montage qui echoue silencieusement rendrait un
    accord de complaisance -- on refuse la mesure plutot que de lire un chiffre vide."""
    sc = case["ctx"].scene
    focus = FOCUS[regime]
    names = {v: {e.name for e in (sc.effects(case["vis_uid"][v]) or [])} for v in FOES}
    if regime == "melee":
        from engine.services.battle_query import are_tiles_adjacent
        for v in FOES:
            adj = are_tiles_adjacent(case["C"], sc.pos(case["vis_uid"][v]), sc.board)
            if (v == focus) != (adj is True):
                raise MontageError(
                    f"regime melee NON INSTALLE : {v} adjacent={adj} au caster (attendu "
                    f"{'True' if v == focus else 'False'}) -- la gate `IsMelee` du mold n'est pas "
                    f"celle qu'on croit exercer")
        return
    if regime == "plain":
        # ⚠ `BigTarget_AdjacentEffect` est porte par le PORTEUR DU TRAIT lui-meme (`astraBullgryn`),
        # qui n'en subit AUCUN malus : le -1 vise ses ALLIES ADJACENTS. L'attester sur sa presence
        # refuserait le montage a tort. Ce qui definit le socle, c'est qu'aucune cible ne soit
        # SOUMISE a un malus : ni `LightCover`, ni voisinage du porteur `BigTarget`.
        from engine.services.battle_query import are_tiles_adjacent
        bt = sc.pos(case["vis_uid"][BIG_TARGET]) if BIG_TARGET in case["vis_uid"] else None
        for v, ns in names.items():
            if "LightCover" in ns:
                raise MontageError(f"regime plain NON INSTALLE : {v} porte `LightCover` -- le "
                                   f"socle sans malus de coups n'est pas le socle")
            if v != BIG_TARGET and bt is not None and \
                    are_tiles_adjacent(sc.pos(case["vis_uid"][v]), bt, sc.board) is True:
                raise MontageError(f"regime plain NON INSTALLE : {v} est adjacent au porteur "
                                   f"`BigTarget` -- il subirait le -1 coup RANGED")
        return
    if regime == "cover" and "LightCover" not in names[focus]:
        raise MontageError(f"regime cover NON INSTALLE : {focus} ne porte pas `LightCover` "
                           f"(effets lus : {sorted(names[focus])})")
    if regime == "bigtarget":
        # ⚠ Le -1 coup de `BigTarget` n'est PAS un effet pose sur le voisin : `BigTarget_AdjacentEffect`
        # ne vit que sur le PORTEUR du trait, et le malus est evalue A LA VOLEE comme une AURA depuis
        # lui (c'est le canal `aura_sources` de la facade de coups). L'attester sur les effets de la
        # cible refuserait le montage a tort -- ce qui l'installe, c'est la GEOMETRIE : adjacence
        # NATIVE au porteur, et meme camp que lui (le trait ne vise que les allies).
        from engine.services.battle_query import are_tiles_adjacent
        b_uid = case["vis_uid"][BIG_TARGET]
        f_uid = case["vis_uid"][focus]
        if are_tiles_adjacent(sc.pos(f_uid), sc.pos(b_uid), sc.board) is not True:
            raise MontageError(f"regime bigtarget NON INSTALLE : {focus} n'est pas adjacent NATIF "
                               f"au porteur `BigTarget` ({sc.pos(f_uid)} vs {sc.pos(b_uid)})")
        if sc.team(f_uid) != sc.team(b_uid):
            raise MontageError(f"regime bigtarget NON INSTALLE : {focus} n'est pas dans le camp du "
                               f"porteur `BigTarget` -- le trait ne vise que les allies")
        if "LightCover" in names[focus]:
            raise MontageError(f"regime bigtarget AMBIGU : {focus} porte AUSSI `LightCover` -- "
                               f"les deux malus se cumuleraient")
    for v in FOES:
        if v == focus:
            continue
        bad = names[v] & {"LightCover"}
        if bad and regime == "cover":
            raise MontageError(f"regime cover AMBIGU : le temoin {v} porte aussi {sorted(bad)}")


def _terrain_map(scene, cells) -> dict:
    """`{tuile: nom de terrain}` -- le MEME canal que le port (`Scene.board.terrain_at`, #124), pas
    le `id` du `boardGraph` : ce dernier est un INDEX de tuile, pas un nom, et le confondre fait
    rendre `aucune geometrie` a toute recherche par terrain."""
    b = getattr(scene, "board", None)
    if b is None:
        raise MontageError("montage NON INSTALLE : la Scene n'a pas de board -- le terrain "
                           "(`DryBush` = `LightCover`) est illisible")
    return {p: b.terrain_at(p[0], p[1]) for p in cells}


def build_case(sid, rpc, rid: int, regime: str, drive: bool = True) -> dict:
    elev, walk, _tileid = P124._board(sid, rid)
    cells = sorted(p for p, wk in walk.items() if wk and elev.get(p) is not None)
    if not cells:
        raise MontageError("montage NON INSTALLE : boardGraph sans tuile walkable")
    dv, _pos = P124._positions(sid, rid)
    units = [u for u in (dv.get("units") or []) if u.get("alive")]
    mine = [u for u in units if u.get("ctrl")]
    if not mine:
        raise MontageError("montage NON INSTALLE : aucune unite controlee")
    cid, myplayer = mine[0]["id"], mine[0]["owner"]
    vis_uid = {}
    for vis in FOES:
        u = next((x for x in units if x.get("owner") != myplayer and x.get("alive")
                  and x.get("visualId") == vis), None)
        if u is None:
            raise MontageError(f"montage NON INSTALLE : {vis} absent du roster adverse")
        vis_uid[vis] = u["id"]

    if drive:
        _dv0, _ctx0 = _fresh_ctx(rpc, rid, cid)          # lecture du TERRAIN avant tout placement
        tid = _terrain_map(_ctx0.scene, cells)
        C, want_vis = _find_layout(cells, elev, walk, tid, regime)
        if C is None:
            raise MontageError(f"montage NON INSTALLE : aucune geometrie `{regime}` sur {BOARD}")
        want = {cid: C}
        want.update({vis_uid[v]: p for v, p in want_vis.items()})
        if not P124._drive_to(sid, rid, walk, elev, want):
            _dv, pos = P124._positions(sid, rid)
            raise MontageError(f"montage NON INSTALLE : placement incomplet -- voulu {want}, "
                               f"obtenu { {u: pos.get(u) for u in want} }")
        P124._give_turn_back(sid, rid, myplayer)
    else:
        # INSPECTION d'un runner deja place (ex. celui d'un AUTRE probe) : positions telles quelles.
        C = _pos.get(cid)
        want = {cid: C}
        want.update({vis_uid[v]: _pos.get(vis_uid[v]) for v in FOES})
        tid = None
    dv, ctx = _fresh_ctx(rpc, rid, cid)
    if tid is None:
        tid = _terrain_map(ctx.scene, cells)
    if drive and ctx.origin != C:
        raise MontageError(f"montage NON INSTALLE : le caster est en {ctx.origin}, voulu {C}")
    ab = _normal_ability_id(rpc, rid, cid)
    case = {"rid": rid, "cid": cid, "C": C, "ab": ab, "ctx": ctx, "elev": elev, "walk": walk,
            "tid": tid, "myplayer": myplayer, "vis_uid": vis_uid, "want": want, "regime": regime}
    if drive:
        _attest(case, regime)
    return case


# --------------------------------------------------------------------------- oracles

def native_fields(rpc, rid, cid, tgt, ab, tile) -> dict:
    """`aiPlaybookPredict` -- le `DamagePredictionResult` que le NATIF construit pour la paire,
    depuis `tile`. C'est l'oracle de DECISION (celui que `pairUtility` consomme)."""
    r = rpc("aiPlaybookPredict", {"runnerId": rid, "unitId": cid, "targetId": tgt,
                                  "abilityType": ab, "col": tile[0], "row": tile[1]}, 60) or {}
    if not r.get("ok"):
        raise MontageError(f"aiPlaybookPredict indisponible pour {tile} / cible {tgt}: {r}")
    evs = r.get("events") or []
    ev = next((e for e in evs if e.get("targetId") == tgt), evs[0] if evs else None)
    if ev is None:
        raise MontageError(f"aiPlaybookPredict n'a rendu AUCUN event pour la cible {tgt}")
    return {"rawMin": ev.get("willKillDmg") or 0, "rawMax": ev.get("mightKillDmg") or 0,
            "hits": ev.get("appliedHits") or 0,
            "hpBefore": ev.get("hpBefore") or 0, "shieldBefore": ev.get("shieldBefore") or 0,
            "healthMin": ev.get("healthDmgMin") or 0, "healthMax": ev.get("healthDmgMax") or 0}


def port_fields(scene, cid, tgt, tile, *, fold: bool = True) -> dict:
    """Le port. `fold=False` vide les DEUX registres de fold additional-damage (`_RANGED_...` ET
    `_MELEE_...`) -> la BASE seule (`ALoki_NormalAttackAbility$$PredictAttack`), qui est l'etage 1
    du mold natif. Vider le seul registre RANGED laisserait le fold MELEE en place et rendrait, dans
    le regime `melee`, une « base » qui est en fait le total."""
    import engine.playbook.prediction.normal_attack as NA
    from engine.playbook.prediction.normal_attack import make_normal_attack_predictions
    saved_r, saved_m = NA._RANGED_FOLLOWUP_PASSIVES, NA._MELEE_FOLLOWUP_PASSIVES
    if not fold:
        NA._RANGED_FOLLOWUP_PASSIVES = NA._MELEE_FOLLOWUP_PASSIVES = ()
    try:
        ev, meta = make_normal_attack_predictions(scene, cid, tgt, tile, meta=True)
    finally:
        NA._RANGED_FOLLOWUP_PASSIVES, NA._MELEE_FOLLOWUP_PASSIVES = saved_r, saved_m
    p = ev.prediction
    f = ev.composite_fields()
    return {"rawMin": p.raw_health_damage.min, "rawMax": p.raw_health_damage.max,
            "hits": p.applied_hits,
            "hpBefore": f.get("hpBefore"), "shieldBefore": f.get("shieldBefore"),
            "healthMin": f.get("healthDmgMin"), "healthMax": f.get("healthDmgMax"),
            "meta": meta}


def _sub(a: dict, b: dict) -> dict:
    """`a - b` sur les champs sommes par `DamagePredictionResult$$Add` (le fold est une SOMME)."""
    return {k: (a.get(k) or 0) - (b.get(k) or 0) for k in ("rawMin", "rawMax", "hits")}


def target_context(case: dict, uid: int) -> dict:
    """Le CONTEXTE GEOMETRIQUE de la paire, tel que le port le lit -- ce qui decide l'arme (donc la
    gate `!IsMelee` du mold), le compte de coups d'arme et le bonus d'elevation. Sans ces champs, un
    ecart de coups se lit comme un mystere ; avec eux il se rattache a une lecture."""
    from engine.playbook.prediction._shared import _weapon_pierce
    from engine.services.battle_query import are_tiles_adjacent
    ctx, tile = case["ctx"], case["C"]
    sc = ctx.scene
    t_pos = sc.pos(uid)
    adj = are_tiles_adjacent(tile, t_pos, sc.board)
    dist = hexgeo.distance(tile, t_pos) if (tile and t_pos) else None
    pierce, ranged, whits, prof = _weapon_pierce(sc, case["cid"], adj, dist)
    return {"pos": t_pos, "dist": dist, "adjacent": adj,
            "elev_caster": case["elev"].get(tuple(tile)),
            "elev_target": case["elev"].get(tuple(t_pos)) if t_pos else None,
            "terrain": case["tid"].get(tuple(t_pos)) if t_pos else None,
            "weapon": {"pierce": pierce, "ranged": ranged, "hits": whits, "profile": prof},
            "tgt_effects": [e.name for e in (sc.effects(uid) or [])] or None}


# --------------------------------------------------------------------------- mesure

def measure(rpc, case: dict) -> list:
    """Une ligne par cible : natif TOTAL, port TOTAL, port BASE (registre vide), port FOLD."""
    out = []
    ctx, tile, ab, cid = case["ctx"], case["C"], case["ab"], case["cid"]
    for vis in FOES:
        uid = case["vis_uid"][vis]
        nat = native_fields(rpc, case["rid"], cid, uid, ab, tile)
        prt = port_fields(ctx.scene, cid, uid, tile, fold=True)
        prt_base = port_fields(ctx.scene, cid, uid, tile, fold=False)
        out.append({"vis": vis, "uid": uid, "native": nat, "port": prt,
                    "port_base": prt_base, "port_fold": _sub(prt, prt_base),
                    "focus": vis == FOCUS[case["regime"]],
                    "ctx": target_context(case, uid),
                    "armor": ctx.scene.armor(uid), "shield": ctx.scene.shield(uid),
                    "hpmax": ctx.hpmax_by_id.get(uid)})
    return out


def native_baseline(sid, rpc, case: dict, make_rid, dispose=None) -> dict:
    """BRAS APPARIE : re-monte la MEME bataille avec `templAggressor:PassiveAbilities=[]`, y rejoue
    le MEME placement (apparie par `visualId`, les ids d'entite differant d'un runner a l'autre) et
    rend la prediction NATIVE de chaque cible.

    `fold_natif = total_natif - base_natif` devient une difference de deux mesures NATIVES : le port
    n'entre pas dans sa definition. Le runner du bras est DISPOSE des la mesure faite."""
    rid = make_rid()
    try:
        elev, walk, _tid = P124._board(sid, rid)
        dv, _pos = P124._positions(sid, rid)
        units = [u for u in (dv.get("units") or []) if u.get("alive")]
        mine = [u for u in units if u.get("ctrl")]
        if not mine:
            raise MontageError("bras BASE : aucune unite controlee")
        cid2, myplayer2 = mine[0]["id"], mine[0]["owner"]
        vis_uid2 = {}
        for vis in FOES:
            u = next((x for x in units if x.get("owner") != myplayer2 and x.get("alive")
                      and x.get("visualId") == vis), None)
            if u is None:
                raise MontageError(f"bras BASE : {vis} absent du roster adverse")
            vis_uid2[vis] = u["id"]
        want = {cid2: case["C"]}
        want.update({vis_uid2[v]: case["want"][case["vis_uid"][v]] for v in FOES})
        if not P124._drive_to(sid, rid, walk, elev, want):
            raise MontageError(f"bras BASE : placement incomplet -- voulu {want}")
        P124._give_turn_back(sid, rid, myplayer2)
        ab2 = _normal_ability_id(rpc, rid, cid2)
        if ab2 == case["ab"]:
            raise MontageError(f"bras BASE NON INSTALLE : l'attaque normale y vaut encore "
                               f"{ab2} -- `PassiveAbilities=[]` n'a pas retire `Boltstorm`")
        out = {"ab": ab2}
        for vis in FOES:
            out[vis] = native_fields(rpc, rid, cid2, vis_uid2[vis], ab2, case["C"])
        return out
    finally:
        if dispose is not None:
            dispose(rid)


def mutants(case: dict, rows: list) -> list:
    """CONTRE-EPREUVES. Critere = DEPLACEMENT du port par rapport au port NON MUTE, jamais l'ecart
    au natif (cf. en-tete)."""
    import engine.playbook.prediction.normal_attack as NA
    ctx, tile, cid = case["ctx"], case["C"], case["cid"]
    ref = {r["vis"]: (r["port"]["rawMin"], r["port"]["rawMax"], r["port"]["hits"]) for r in rows}
    whits_of = {r["vis"]: r["ctx"]["weapon"]["hits"] for r in rows}
    out = []
    for name in MUTANTS:
        saved_avg = NA.calculate_average
        saved_fn = NA.get_additional_damage_prediction
        saved_hits = NA.attack_hits_with_modifiers
        cur = {"vis": None, "calls": 0}
        try:
            if name == "hits_raw":
                # L'ETAT D'AVANT LE FIX : `nrOfHits` pris pour le compte de coups du fold.
                NA.get_additional_damage_prediction = (
                    lambda *a, **k: saved_fn(*a, **{**k, "hits_ctx": None}))
            elif name == "hits_from_base":
                # Le MODELE CONCURRENT : le fold reprendrait la base d'arme de l'ATTAQUE PORTEUSE au
                # lieu de `nrOfHits`. Indiscernable sur `templAggressor` (3 == 3) -- c'est le regime
                # `melee` (`adeptMorvenn` : arme 2 coups, `nrOfHits` 3) qui le fait mordre.
                # Le 2e appel de la facade d'une meme prediction EST celui du fold : la base est
                # calculee avant lui dans `make_normal_attack_predictions`, et `cur["calls"]` est
                # remis a zero par cible (une cible sans fold n'en fait qu'un).
                def _from_base(**kw):
                    cur["calls"] += 1
                    if cur["calls"] == 2:
                        kw = {**kw, "weapon_hits": whits_of[cur["vis"]]}
                    return saved_hits(**kw)
                NA.attack_hits_with_modifiers = _from_base
            elif name == "amount_min":
                NA.calculate_average = lambda mn, mx: int(mn)
            got = {}
            for r in rows:
                cur["vis"], cur["calls"] = r["vis"], 0
                f = port_fields(ctx.scene, cid, r["uid"], tile, fold=True)
                got[r["vis"]] = (f["rawMin"], f["rawMax"], f["hits"])
        finally:
            NA.calculate_average = saved_avg
            NA.get_additional_damage_prediction = saved_fn
            NA.attack_hits_with_modifiers = saved_hits
        shift = {v: tuple(got[v][i] - ref[v][i] for i in range(3)) for v in ref}
        out.append({"mutant": name, "shift": shift,
                    "bites": any(any(x != 0 for x in s) for s in shift.values()),
                    "bites_focus": (any(x != 0 for x in shift[FOCUS[case["regime"]]])
                                    if FOCUS[case["regime"]] else None)})
    return out


def run_regime(sid, rpc, rid: int, regime: str, make_base_rid=None, dispose=None,
               with_mutants: bool = False, drive: bool = True) -> dict:
    case = build_case(sid, rpc, rid, regime, drive=drive)
    rows = measure(rpc, case)
    base = native_baseline(sid, rpc, case, make_base_rid, dispose) if make_base_rid else None
    if base is not None:
        for r in rows:
            r["native_base"] = base[r["vis"]]
            r["native_fold"] = _sub(r["native"], base[r["vis"]])
    return {"case": case, "rows": rows, "base": base,
            "mutants": mutants(case, rows) if with_mutants else []}


# --------------------------------------------------------------------------- CLI

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True, help="chemin ABSOLU du state-file")
    ap.add_argument("--regime", choices=REGIMES, default="cover")
    ap.add_argument("--runner", type=int, default=None, help="reutilise un runner deja monte")
    ap.add_argument("--no-baseline", action="store_true",
                    help="saute le bras apparie (ne monte qu'UN runner)")
    ap.add_argument("--no-drive", action="store_true",
                    help="INSPECTE un runner deja place (avec --runner) sans rien deplacer")
    ap.add_argument("--mutants", action="store_true", help="joue les contre-epreuves")
    args = ap.parse_args()

    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()

    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    rid = args.runner if args.runner else _build(args.state_file, args.regime, "kit")
    base_state = os.path.splitext(args.state_file)[0] + "_base.json"

    def _make_base():
        return _build(base_state, args.regime, "base")

    def _dispose(_rid):
        subprocess.run([sys.executable, "rl_duel.py", "dispose", "--state-file", base_state],
                       cwd=_HERE, capture_output=True, text=True)

    res = run_regime(sid, rpc, rid, args.regime,
                     make_base_rid=None if args.no_baseline else _make_base,
                     dispose=_dispose, with_mutants=args.mutants, drive=not args.no_drive)
    case, rows, base = res["case"], res["rows"], res["base"]
    print(f"runner {rid} | regime {args.regime} | caster u{case['cid']} @ {case['C']} "
          f"| attaque normale = {case['ab']}")
    if base is not None:
        print(f"  bras BASE : attaque normale = {base['ab']} (le fold natif y est ABSENT)")
    for r in rows:
        n, p, pb, pf = r["native"], r["port"], r["port_base"], r["port_fold"]
        tag = "*" if r["focus"] else " "
        print(f" {tag}[{r['vis']:<15}] u{r['uid']} armor={r['armor']} hpmax={r['hpmax']}")
        print(f"      TOTAL  nat=({n['rawMin']}, {n['rawMax']}, h{n['hits']})   "
              f"port=({p['rawMin']}, {p['rawMax']}, h{p['hits']})   "
              f"d=({p['rawMin'] - n['rawMin']:+d}, {p['rawMax'] - n['rawMax']:+d}, "
              f"h{p['hits'] - n['hits']:+d})")
        if "native_base" in r:
            nb, nf = r["native_base"], r["native_fold"]
            print(f"      BASE   nat=({nb['rawMin']}, {nb['rawMax']}, h{nb['hits']})   "
                  f"port=({pb['rawMin']}, {pb['rawMax']}, h{pb['hits']})   "
                  f"d=({pb['rawMin'] - nb['rawMin']:+d}, {pb['rawMax'] - nb['rawMax']:+d}, "
                  f"h{pb['hits'] - nb['hits']:+d})")
            print(f"      FOLD   nat=({nf['rawMin']}, {nf['rawMax']}, h{nf['hits']})   "
                  f"port=({pf['rawMin']}, {pf['rawMax']}, h{pf['hits']})   "
                  f"d=({pf['rawMin'] - nf['rawMin']:+d}, {pf['rawMax'] - nf['rawMax']:+d}, "
                  f"h{pf['hits'] - nf['hits']:+d})")
        else:
            print(f"      BASE   port=({pb['rawMin']}, {pb['rawMax']}, h{pb['hits']})   "
                  f"FOLD port=({pf['rawMin']}, {pf['rawMax']}, h{pf['hits']})")
        mb = pb.get("meta") or {}
        c = r["ctx"]
        print(f"      meta port : base={mb.get('base')} hits={mb.get('hits')} "
              f"pierce={mb.get('pierce')} mods={mb.get('mods')} "
              f"followup={(p.get('meta') or {}).get('followup')}")
        print(f"      ctx : pos={c['pos']} dist={c['dist']} adj={c['adjacent']} "
              f"elev={c['elev_caster']}->{c['elev_target']} terrain={c['terrain']} "
              f"weapon_hits={c['weapon']['hits']} tgt_effects={c['tgt_effects']}")
    for mu in res["mutants"]:
        det = " ".join(f"{k}:{v}" for k, v in sorted(mu["shift"].items()))
        print(f"  [mutant {mu['mutant']:<11}] deplacement du port [{det}] "
              f"({'MORD' if mu['bites'] else 'NE MORD PAS'}"
              f"{'' if mu['bites_focus'] is None else '; focus ' + ('MORD' if mu['bites_focus'] else 'NON')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
