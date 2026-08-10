"""#419-r1 tranche 11 -- MONTAGE NOMME de la face ATTACK de `SpecialIssueCombiMelta` (1545), et
mesure natif contre port.

`IdunBattle.AI.Playbook.Loki.SpecialIssueCombiMeltaPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$MoveNext`
rend `GetUtilityValue("SpecialIssueCombiMelta_LikesRange3")` quand
`IBattleQuery.<slot 0x6c = GetDistance>(case.Target, case.CasterPosition.MainTile)` vaut EXACTEMENT
3, et ne fait AUCUN yield sinon (`yield break`, pas `yield Fix64(0)` -- le dispatcher SOMME les
steps, donc 0). C'est un terme de GEOMETRIE PURE : ni stat, ni trait, ni effet, ni prediction, ni
gate d'ability.

## Le porteur, et le seul montage qui l'amene

`darkaSternguard` << Ramus >> est un HERO (`kind` lineup) mais **hors catalogue du seed BC** -- il
figure aux 21 unites que `catalog_inject.py --missing` recense. Il entre donc par
`catalog_inject.write_augmented_seed_bc` + `rl_duel build --seed-bc` (case-92 §6), pas par une
greffe : le playbook est confronte SUR SON PORTEUR REEL.

## UN SEUL BRAS depuis que la face COMBAT est portee (#419-r1-tr11-r3)

`SpecialIssueCombiMelta_InitAbility$$CreateBehaviour` monte sur le porteur les effets
`SpecialIssueCombiMelta_AdditionalHits` (1563, `d == 2`) et `_ExtraDmg` (1564, `d == 1`), qui
modifient la PREDICTION de degat -- donc l'utilite de paire, par un canal qui n'est PAS ce playbook.
Mesure de ce montage : a distance 1 le natif ajoute un montant PLAT, a distance 2 un COUP ENTIER, et
**a distance 3 RIEN**.

Tant que ces deux effets n'etaient pas portes, le montage avait DEUX bras : `raw` (aucun patch,
confrontable a la seule distance 3) et `neutered` (variables de degat forcees a 0 dans le seed BC,
pour faire converger les deux moteurs aux trois distances). **`neutered` a ete SUPPRIME** : le port
modelise maintenant les deux effets, donc le patch desynchroniserait au lieu de converger -- et il
n'a plus d'objet, le bras `raw` collant desormais au natif aux TROIS distances.

  * bras **`raw`** -- seed BC augmente du porteur hors catalogue, rien d'autre. C'est la
    CONFIGURATION REELLE DU JEU : aucun patch n'y entre, donc aucun angle mort `#366-r1`.

CONTRE-EPREUVE VERSIONNEE (`--sans-face-combat`) : desinscrit 1563/1564 d'`EFFECT_CLASSES` et
re-mesure sur le MEME runner. Elle chiffre ce que le port a ferme -- **15 lignes divergentes sur 26,
de 8.35 a 78.01 points** sans la face COMBAT, contre **4 lignes a 0.960412** avec (le residu
`#419-r1-tr11-r5`, bi-canal ROLL/DISPLAY du canal #179).

## Deux cibles, et ce que la seconde est SEULE a trancher

Les deux cibles sont placees ADJACENTES l'une a l'autre : une meme tuile d'attaque est alors a
distance `d` de l'une et `d +/- 1` de l'autre. Un port qui lirait autre chose que `case.Target`
(l'ennemi le plus proche, le caster, ...) rendrait la MEME valeur pour les deux cibles depuis une
meme tuile : ces lignes-la le trahissent.

## Residu d'OUTILLAGE mesure ici -- `aiPredict` desaccorde de `pairUtility` sur certaines tuiles

Le mode `--stage` publie l'etage PREDICTION via `aiPredict`. ⚠ Ce canal s'est revele INFIDELE a la
tuile demandee sur 3 tuiles du montage (il y rend le profil d'une AUTRE distance, de facon stable et
reproductible, `fresh: true` compris) alors que `pairUtility` et le port s'accordent au bit pres.
`aiPredict` n'entre donc dans AUCUNE assertion : il est un diagnostic, pas un oracle. Le fait est
NOMME (`#419-r1-tr11-r2`) et non contourne.

Usage :
    python scripts/python/probe_419r1tr11_combi_melta.py --state-file <ABSOLU> [--stage] [--mutants]

Runners (un par bras) :
    python catalog_inject.py --units darkaSternguard --out <abs>_raw.json
    python rl_duel.py build --seed 41545 --board MC1_67 --seed-bc <abs>_raw.json \
        --p-units darkaSternguard --a-units astraBullgryn,necroWarden --no-ai \
        --state-file <abs unique>.json

ASCII only. Garde jumelle : `scripts/python/tests/engine/test_419r1tr11_combi_melta_live.py`.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import catalog_inject                                            # noqa: E402
import hexgeo                                                    # noqa: E402
import probe_124_line_elevation_decision as P124                 # noqa: E402
from engine import weights as W                                  # noqa: E402
from engine.entities.triggered_ability_type import TriggeredAbilityType   # noqa: E402
from engine.playbook import scene as _scene                      # noqa: E402
from engine.playbook.common import NORMAL_ATTACK_PLAYBOOK        # noqa: E402
from engine.ai import context as _ai_ctx                         # noqa: E402

BOARD = "MC1_67"
SEED = "41545"
CASTER = "darkaSternguard"      # << Ramus >>, HERO hors catalogue -> injection (case-92 §6)
TGT_A = "astraBullgryn"
TGT_B = "necroWarden"
ABILITY = int(TriggeredAbilityType.SpecialIssueCombiMelta)   # 1545 = 0x609
WEIGHT_KEY = "SpecialIssueCombiMelta_LikesRange3"
RANGE = 3                       # le LITTERAL `!= 3` du corps natif
EPS = 1e-4                      # Fix64 natif contre float du port
# Le niveau auquel `buildNormalizedBC` porte les abilities des unites normalisees. Le patch de
# neutralisation doit viser CE palier, sinon il ecrit dans une case que le natif ne lit pas.
ABILITY_LEVEL = 50

# Sorties du run -> `logs/` (gitignore). JAMAIS `data/`, qui ne porte que des ENTREES versionnees.
LOGS = Path(_HERE).resolve().parents[1] / "logs"

BUILD_ARGS = ["--board", BOARD, "--no-ai",
              "--p-units", CASTER, "--a-units", "%s,%s" % (TGT_A, TGT_B)]


class MontageError(RuntimeError):
    """Le montage ne s'installe pas -- la mesure n'a PAS eu lieu (jamais un vert silencieux)."""


# --------------------------------------------------------------------------- seeds BC des 2 bras

def write_raw_seed_bc(path) -> str:
    """Bras `raw` : seed BC AUGMENTE du porteur hors catalogue (`BC.Units` + `BC.Abilities`)."""
    catalog_inject.write_augmented_seed_bc(str(path), [CASTER])
    return str(path)


# ⚠ `write_neutered_seed_bc` A ETE SUPPRIMEE (#419-r1-tr11-r3). Elle ecrivait un seed BC dont les
# variables de degat de 1545 etaient forcees a 0, pour que la face COMBAT non portee cesse de
# perturber la prediction : un patch INVISIBLE DU PORT (#366-r1), licite UNIQUEMENT tant que le port
# ne modelisait pas les effets 1563 / 1564. Ils sont maintenant au registre `EFFECT_CLASSES`, donc
# le meme geste desynchroniserait les deux moteurs au lieu de les faire converger -- et il n'y a
# plus rien a neutraliser : le port colle au natif aux TROIS distances sur le bras `raw`, sans
# aucun patch. Les trois entrees correspondantes de
# `probe_366_r1_bcpatch_port_blindspot._EXCEPTIONS` sont retirees dans le meme commit.

CASTER_ABILITY_NAME = "SpecialIssueCombiMelta"


# --------------------------------------------------------------------------- oracles

def pair_native(rpc, rid, cid, tgt, ab, tile) -> float:
    """`pairUtility` = `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateUtilityFromPredictions`
    pour (ability, cible) DEPUIS `tile`. C'est LE seul oracle d'utilite du montage."""
    r = rpc("pairUtility", {"runnerId": rid, "unitId": cid, "targetId": tgt,
                            "abilityType": ab, "col": tile[0], "row": tile[1]}, 90)
    v = (r or {}).get("utility")
    if not isinstance(v, (int, float)):
        raise MontageError("pairUtility natif indisponible pour %s / cible %s : %r" % (tile, tgt, r))
    return float(v)


def pair_port(ctx, ab, tgt, tile) -> tuple:
    cand = NORMAL_ATTACK_PLAYBOOK.calculate_action_utility(ctx, tile, tgt, ab)
    if cand is None:
        raise MontageError("le port ne produit AUCUNE action depuis %s sur %s" % (tile, tgt))
    return float(cand["u"]), cand["pred"]


def native_prediction(rpc, rid, cid, tgt, ab, tile) -> dict:
    """DIAGNOSTIC SEUL (`--stage`) -- cf. le residu `#419-r1-tr11-r2` en tete : ce canal s'ecarte de
    `pairUtility` sur certaines tuiles. Il n'entre dans aucune assertion."""
    r = rpc("aiPredict", {"runnerId": rid, "unitId": cid, "targetId": tgt, "abilityType": ab,
                          "col": tile[0], "row": tile[1], "fresh": True}, 90)
    return (r or {}).get("pred") or {}


# --------------------------------------------------------------------------- montage

def build_case(sid, rpc, rid: int) -> dict:
    """Place les DEUX cibles cote a cote et le caster a portee, puis rend de quoi mesurer.

    Les unites sont DEPLACEES (`probe_124_line_elevation_decision._drive_to`) : on ne subit pas la
    geometrie de spawn. Le critere de choix des tuiles est la PORTEE de l'arme -- hors portee, le
    natif ne rend que le terme declenche la ou le port produit aussi sa composante de degat, et les
    deux cotes ne parleraient pas de la meme chose (piege releve sur #419/Lakrimae)."""
    elev, walk, _tid = P124._board(sid, rid)
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    units = dv.get("units") or []
    mine = [u for u in units if u.get("ctrl") and u.get("alive")]
    cid = next((u["id"] for u in mine if u.get("visualId") == CASTER), None)
    if cid is None:
        raise MontageError("montage NON INSTALLE : %s absent du roster (injection catalogue ?)"
                           % CASTER)
    myplayer = mine[0].get("owner")
    tgt = {}
    for vis in (TGT_A, TGT_B):
        u = next((x for x in units if x.get("owner") != myplayer and x.get("alive")
                  and x.get("visualId") == vis), None)
        if u is None:
            raise MontageError("montage NON INSTALLE : %s absent du roster adverse" % vis)
        tgt[vis] = u["id"]

    # (a) L'ability 1545 est-elle bien a l'`AbilitiesComponent` du porteur ? Sans elle le
    #     dispatcher ne l'itere jamais et la mesure ne prouverait rien.
    st = rpc("unitAbilityStates", {"runnerId": rid, "unitId": cid}, 60) or {}
    live_ids = [i for u in (st.get("units") or []) for t in (u.get("triggered") or [])
                for i in [((t.get("raw") or [None])[0])] if isinstance(i, int)]
    if ABILITY not in live_ids:
        raise MontageError(
            "montage NON INSTALLE : %d n'est PAS dans l'AbilitiesComponent de %s -- triggered live "
            "lus = %s" % (ABILITY, CASTER, sorted(set(live_ids))))

    # (b) Geometrie : une tuile centrale `A` pour la premiere cible, une VOISINE `B` pour la
    #     seconde, et le caster a distance 3 de `A`. Les trois couronnes 1/2/3 autour de `A`
    #     doivent etre praticables -- c'est ce qui donne les trois regimes du gate.
    cells = sorted(p for p, w in walk.items() if w and elev.get(p) is not None)
    if not cells:
        raise MontageError("montage NON INSTALLE : boardGraph sans tuile walkable")
    ctr = (sum(c for c, _ in cells) / len(cells), sum(r for _, r in cells) / len(cells))
    chosen = None
    for A in sorted(cells, key=lambda q: (q[0] - ctr[0]) ** 2 + (q[1] - ctr[1]) ** 2):
        nb = [q for q in hexgeo.neighbors(A[0], A[1])
              if walk.get(q) and elev.get(q) is not None and abs(elev[q] - elev[A]) < 2]
        if not nb:
            continue
        B = nb[0]                                   # la SECONDE cible, adjacente a la premiere
        ring = {d: [p for p in cells if hexgeo.distance(p, A) == d
                    and abs(elev[p] - elev[A]) < 2 and p not in (A, B)]
                for d in (1, 2, 3)}
        if all(ring[d] for d in (1, 2, 3)):
            chosen = (A, B, ring[3][0])
            break
    if chosen is None:
        raise MontageError("montage NON INSTALLE : aucune tuile centrale avec un voisin et les "
                           "trois couronnes 1/2/3 praticables")
    A, B, C = chosen
    wanted = {cid: C, tgt[TGT_A]: A, tgt[TGT_B]: B}
    if not P124._drive_to(sid, rid, walk, elev, wanted):
        _dv, pos = P124._positions(sid, rid)
        raise MontageError("montage NON INSTALLE : placement incomplet -- voulu %r, obtenu %r"
                           % (wanted, {u: pos.get(u) for u in wanted}))
    P124._give_turn_back(sid, rid, myplayer)

    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mbu = {u.get("unitId"): u for u in (mov.get("units") or [])}
    ctx = _ai_ctx.build(rpc, rid, dv, mbu, cid, W.load(), _scene.build_predictor(rpc, rid))
    ab = next(iter(ctx.normal_ids or ()), None)
    if ab is None:
        raise MontageError("montage NON INSTALLE : aucune attaque normale sur le caster")

    weight = float(ctx.wt.triggered(WEIGHT_KEY))
    if weight == 0:
        raise MontageError("montage NON INSTALLE : le BC servi porte %s = 0 -- rien ne "
                           "discriminerait" % WEIGHT_KEY)

    tpos = {vis: ctx.scene.pos(uid) for vis, uid in tgt.items()}
    if any(p is None for p in tpos.values()):
        raise MontageError("montage NON INSTALLE : position de cible inconnue (%r)" % tpos)
    # Les paires (tuile, cible) mesurables = tuile d'action DANS la portee de l'arme (<= 3, sinon
    # les deux cotes ne calculent pas la meme chose) et hors de la cible elle-meme.
    pairs = []
    for tile in (ctx.action_tiles or []):
        if not tile or tile[0] is None:
            continue
        t = (tile[0], tile[1])
        for vis, uid in tgt.items():
            d = hexgeo.distance(t, tpos[vis])
            if 1 <= d <= RANGE:
                pairs.append((t, vis, uid, d))
    dists = {d for _t, _v, _u, d in pairs}
    if not {1, 2, 3} <= dists:
        raise MontageError("montage NON INSTALLE : les trois distances ne sont pas couvertes "
                           "(vues : %s) -- le gate `== 3` ne serait pas pris dans les deux sens"
                           % sorted(dists))
    # Une tuile d'ou les DEUX cibles sont visees a des distances DIFFERENTES : c'est elle qui
    # tranche que la distance est prise sur `case.Target` et non sur autre chose.
    by_tile = {}
    for t, vis, _u, d in pairs:
        by_tile.setdefault(t, {})[vis] = d
    split = [t for t, m in by_tile.items()
             if len(m) == 2 and set(m.values()) & {RANGE} and len(set(m.values())) == 2]
    if not split:
        raise MontageError("montage NON INSTALLE : aucune tuile d'ou les deux cibles soient a des "
                           "distances DIFFERENTES dont l'une vaut 3")
    return {"rid": rid, "cid": cid, "tgt": tgt, "tpos": tpos, "ab": ab, "ctx": ctx,
            "weight": weight, "pairs": pairs, "A": A, "B": B, "C": C, "split_tiles": split,
            # Le natif ne depend PAS du port : on le memoise pour que les six contre-epreuves ne
            # re-interrogent pas six fois le meme oracle (l'etat de bataille est fige).
            "nat_cache": {}}


def measure(rpc, case: dict) -> list[dict]:
    """Une ligne par (tuile, cible) : natif, port, port SANS le playbook 1545."""
    import engine.playbook.psyker as PSY
    ctx, ab, cid, rid = case["ctx"], case["ab"], case["cid"], case["rid"]
    cache = case.setdefault("nat_cache", {})
    out = []
    for tile, vis, uid, d in case["pairs"]:
        key = (tile, uid)
        if key not in cache:
            cache[key] = pair_native(rpc, rid, cid, uid, ab, tile)
        nat = cache[key]
        port, ppred = pair_port(ctx, ab, uid, tile)
        saved = PSY.TRIGGERED_ATTACK_PLAYBOOKS.pop(ABILITY, None)
        if saved is None:
            raise MontageError("le playbook %d n'est PAS au registre -- rien a muter" % ABILITY)
        try:
            muted, _ = pair_port(ctx, ab, uid, tile)
        finally:
            PSY.TRIGGERED_ATTACK_PLAYBOOKS[ABILITY] = saved
        out.append({"tile": tile, "target": vis, "target_id": uid, "dist": d,
                    "native": nat, "port": port, "port_muted": muted,
                    "port_pred": (ppred["healthDmgMin"], ppred["healthDmgMax"],
                                  ppred["appliedHits"])})
    return out


# --------------------------------------------------------------------------- contre-epreuves

def _mutant_no_gate(self, ctx, attacker_uid, ability_id, case_tgt_id, attack_tile,
                    prediction=None):
    """Gate de distance RETIREE -- le poids tombe partout."""
    return float(ctx.wt.triggered(WEIGHT_KEY))


def _mutant_le_range(self, ctx, attacker_uid, ability_id, case_tgt_id, attack_tile,
                     prediction=None):
    """`<= 3` au lieu de `== 3` -- la lecture la plus PLAUSIBLE et la plus fausse."""
    from engine.battle_query import get_distance
    p = ctx.scene.pos(int(case_tgt_id))
    if p is None or get_distance([p], [attack_tile]) > RANGE:
        return 0.0
    return float(ctx.wt.triggered(WEIGHT_KEY))


def _mutant_range_two(self, ctx, attacker_uid, ability_id, case_tgt_id, attack_tile,
                      prediction=None):
    """Le litteral vaut 2 -- ce que la face COMBAT ferait croire (ses effets mordent a 1 et 2)."""
    from engine.battle_query import get_distance
    p = ctx.scene.pos(int(case_tgt_id))
    if p is None or get_distance([p], [attack_tile]) != 2:
        return 0.0
    return float(ctx.wt.triggered(WEIGHT_KEY))


def _mutant_caster_tile(self, ctx, attacker_uid, ability_id, case_tgt_id, attack_tile,
                        prediction=None):
    """Distance prise depuis la tuile REELLE du caster au lieu de `case.CasterPosition`."""
    from engine.battle_query import get_distance
    p = ctx.scene.pos(int(case_tgt_id))
    c = ctx.scene.pos(int(attacker_uid))
    if p is None or c is None or get_distance([p], [c]) != RANGE:
        return 0.0
    return float(ctx.wt.triggered(WEIGHT_KEY))


def _mutant_caster_not_target(self, ctx, attacker_uid, ability_id, case_tgt_id, attack_tile,
                              prediction=None):
    """Distance CASTER <-> tuile d'attaque au lieu de CIBLE <-> tuile d'attaque."""
    from engine.battle_query import get_distance
    c = ctx.scene.pos(int(attacker_uid))
    if c is None or get_distance([c], [attack_tile]) != RANGE:
        return 0.0
    return float(ctx.wt.triggered(WEIGHT_KEY))


def _mutant_literal_weight(self, ctx, attacker_uid, ability_id, case_tgt_id, attack_tile,
                           prediction=None):
    """Poids code en dur (1) au lieu de la cle BC."""
    from engine.battle_query import get_distance
    p = ctx.scene.pos(int(case_tgt_id))
    if p is None or get_distance([p], [attack_tile]) != RANGE:
        return 0.0
    return 1.0


MUTANTS = {
    "no_gate": _mutant_no_gate,
    "le_range": _mutant_le_range,
    "range_two": _mutant_range_two,
    "caster_tile": _mutant_caster_tile,
    "caster_not_target": _mutant_caster_not_target,
    "literal_weight": _mutant_literal_weight,
}


def run_mutant(rpc, case: dict, name: str) -> list[dict]:
    """Rejoue `measure` avec la face ATTACK du playbook REMPLACEE par le mutant.

    Le critere est le DEPLACEMENT du port par rapport au NATIF (`port - native`) : sur le bras
    `raw` le port NON MUTE colle au natif au bit pres hors du regime residuel
    `#419-r1-tr11-r5`, donc tout ecart >= 1 point EST le mutant.
    ⚠ Sur le bras `raw` ce critere ne vaut qu'aux tuiles a distance 3 (ailleurs la face COMBAT non
    portee ecarte deja les deux cotes)."""
    from engine.playbook.special_issue_combi_melta import SpecialIssueCombiMeltaPlaybook as PB
    fn = MUTANTS[name]
    orig = PB.calculate_attack_utility_in_steps
    PB.calculate_attack_utility_in_steps = fn
    try:
        return measure(rpc, case)
    finally:
        PB.calculate_attack_utility_in_steps = orig


def mutant_bite(rows: list[dict]) -> dict:
    """Deplacement MAX `|port - natif|` par distance, pour un jeu de lignes mutees."""
    per: dict = {}
    for r in rows:
        per[r["dist"]] = max(per.get(r["dist"], 0.0), abs(r["port"] - r["native"]))
    return per


def mutant_inert_lines(rows: list[dict]) -> int:
    """Nombre de lignes ou le mutant NE mord PAS -- la RECIPROQUE : une contre-epreuve qui
    s'ecarte partout ne discrimine rien, elle dit seulement « ce n'est pas la meme fonction »."""
    return sum(1 for r in rows if abs(r["port"] - r["native"]) < EPS)


# --------------------------------------------------------------------------- CLI

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True,
                    help="chemin ABSOLU du state-file du runner (rl_duel build --state-file)")
    ap.add_argument("--stage", action="store_true",
                    help="publier l'etage PREDICTION (DIAGNOSTIC : cf. residu #419-r1-tr11-r2)")
    ap.add_argument("--mutants", action="store_true", help="jouer les contre-epreuves")
    ap.add_argument("--sans-face-combat", action="store_true",
                    help="CONTRE-EPREUVE #419-r1-tr11-r3 : desinscrire les DEUX effets de la face "
                         "COMBAT (1563 / 1564) du registre, pour re-mesurer l'etat d'AVANT leur "
                         "port sur le MEME runner et la MEME geometrie")
    args = ap.parse_args()

    if args.sans_face_combat:
        # Le registre est lu A LA DEMANDE par `EffectFactory.effect_def` (cle = le NOM capte de
        # l'effet), donc le retrait ici suffit : la Scene materialisera un `BaseEffect` nu, sans
        # `additional_hit_groups` ni `create_effect_damage_bonus_for_attack`. C'est EXACTEMENT
        # l'etat d'avant le port -- pas une approximation.
        from engine.entities.effects.factory import EFFECT_CLASSES
        for _k in ("SpecialIssueCombiMelta_AdditionalHits", "SpecialIssueCombiMelta_ExtraDmg"):
            if EFFECT_CLASSES.pop(_k, None) is None:
                raise MontageError("%s n'est PAS au registre -- rien a desinscrire" % _k)
        print("[contre-epreuve] face COMBAT DESINSCRITE (1563 + 1564)")

    import json
    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()
    rid = int(json.load(open(args.state_file, encoding="utf-8"))["runnerId"])

    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    case = build_case(sid, rpc, rid)
    print("runner %d | caster u%d @%s | cibles %s @%s | poids %s = %g"
          % (rid, case["cid"], case["C"], case["tgt"], case["tpos"], WEIGHT_KEY, case["weight"]))
    rows = measure(rpc, case)
    for r in rows:
        print("  %-14s d=%d @%-7s nat=%11.6f port=%11.6f (d=%+.6f) | sans_1545 port=%11.6f "
              "terme_nat=%+.6f"
              % (r["target"], r["dist"], r["tile"], r["native"], r["port"],
                 r["port"] - r["native"], r["port_muted"], r["native"] - r["port_muted"]))
    if args.stage:
        print("-- etage PREDICTION (min,max,hits) -- DIAGNOSTIC, hors assertions (#419-r1-tr11-r2)")
        for r in rows:
            p = native_prediction(rpc, case["rid"], case["cid"], r["target_id"], case["ab"],
                                  r["tile"])
            nat = (p.get("healthDmgMin"), p.get("healthDmgMax"), p.get("appliedHits"))
            flag = "==" if nat == r["port_pred"] else "!="
            print("  %-14s d=%d @%-7s nat=%s %s port=%s"
                  % (r["target"], r["dist"], r["tile"], nat, flag, r["port_pred"]))
    if args.mutants:
        print("-- contre-epreuves (deplacement MAX |port - natif| par distance, + lignes INERTES)")
        for name in sorted(MUTANTS):
            mrows = run_mutant(rpc, case, name)
            per = mutant_bite(mrows)
            print("  %-18s %s  inertes=%d/%d"
                  % (name, " ".join("d%d=%+.3f" % (d, per[d]) for d in sorted(per)),
                     mutant_inert_lines(mrows), len(mrows)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
