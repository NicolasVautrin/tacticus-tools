"""#419-r1 tranche 13 -- MONTAGE NOMME de la face ATTACK de `Shrapnel` (1116), natif contre port.

`IdunBattle.AI.Playbook.Loki.ShrapnelPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__2$$MoveNext`
SOMME, sur chaque unite adjacente a la CIBLE et non `Invincible`, `nrOfHits` (2) fois l'utilite
(composite Damage) d'une prediction de montant `minDmg[niveau du passif]`, hits FORCES 1, au profil
LITTERAL `Blast`. AUCUN filtre de camp : un ALLIE du caster y entre, et son event est NIE par les
trois feuilles dominantes du composite. RE complete et lectures non devinables :
`engine/playbook/shrapnel.py` (en-tete).

## L'inventaire du nom -- TROIS artefacts sous l'id 1116

`TriggeredAbilityType.Shrapnel = 1116` (CE playbook), `ActiveAbilityType.RadBombardment = 1116`,
`EffectType.InescapableAccuracy_extraCritDmg = 1116` (porte par #414, axe CRIT). Aucun autre enum ne
porte le NOM `Shrapnel` : pas de mold d'attaque normale sous un autre id.

## Pourquoi une GREFFE, et sur quel hote

Les 3 porteurs de 1116 sont 2 npc (`astraNpc4Mortar`, `astraNpc4MortarSurv`) et le SUMMON
`astraSmnMortar`. `buildNormalizedBC` refuse tout npc, et le summon n'a **AUCUN invocateur-unite** :
le balayage prescrit par `case-92` §5bis recours 2 rend une seule ability qui le declare,
`EnvFactionSummons:AstraMilitarum`, que **personne** ne porte dans
`activeAbilities`/`passiveAbilities` -- c'est un summon d'ENVIRONNEMENT. La voie « spawner son
summoner » n'existe donc pas, il ne reste que le recours 3.

La greffe est LEGITIME et c'est LU, pas suppose : le corps ne consulte du caster QUE son identite
(pipeline modifiers), sa position, et le NIVEAU de son propre passif 1116 -- ni arme (le profil est le
LITTERAL `Blast`), ni stat, ni trait. Tout le reste vient de `case.Target` et du board.

## Le BRAS APPARIE -- ce qui rend le terme MESURABLE cote NATIF

Deux runners, IDENTIQUES en tout sauf le passif greffe :

    `graft` : `BC.Units[<hote>].PassiveAbilities = [1116]`
    `base`  : `BC.Units[<hote>].PassiveAbilities = []`     (le bras `graft` MOINS 1116)

`terme_natif = natif_graft - natif_base` sur la MEME paire, la MEME tuile et la MEME geometrie.
⚠ Le bras `base` est le bras greffe MOINS 1116, surtout PAS « les passifs d'origine de l'hote » :
`replace=True` les a deja retires (piege mesure par #419-r1-tr9).

Le critere principal est ici `terme_natif == terme_port` a EPS pres -- pas un poids plat a retrouver
mais une utilite de degat complete, donc un accord bien plus contraignant que sur les tranches a
poids BC. Les residus hors-perimetre du couple (caster, cible) s'annulent dans la DIFFERENCE.

## Les QUATRE crans, et ce que chacun est SEUL a trancher

La cible `T` et le caster `C` ne bougent JAMAIS ; on ne deplace que ce qui l'entoure. `C` n'est
JAMAIS adjacent a `T` (sinon il serait son propre voisin AMI a tous les crans, et `cF` cesserait de
discriminer). Les cardinaux sont RE-DERIVES des positions live avec l'adjacence NATIVE
(`bq.is_adjacent`, porte d'elevation comprise), jamais supposes.

    `c0`  0 voisin                  -> terme 0        (boucle vide -> `yield acc` avec acc = 0)
    `c1`  1 voisin ENNEMI           -> terme > 0      <- le terme existe
    `c2`  2 voisins ENNEMIS         -> terme(c2) > terme(c1) + EPS  <- SOMME, pas MOYENNE
    `cF`  1 voisin AMI du caster    -> terme < 0      <- PAS de filtre de camp, et negation friendly

⚠ `c2` et `cF` sont LES deux crans de cette tranche. `Psyker` (1013) fait exactement le meme balayage
`Damageable(AdjacentUnits(CIBLE))` et DIVISE par `Count` ; `LightImUp` moyenne ses cibles
secondaires. Ici il n'y a aucune division. Et tous les playbooks attack portes a ce jour qui comptent
des voisins filtrent par camp (`Enemies(...)` / `Friends(...)`) : celui-ci ne filtre pas, et le signe
du terme s'INVERSE sur un ami. Un port ecrit par analogie se tromperait sur les deux.

## Contre-epreuves -- critere = DEPLACEMENT par rapport au port NON MUTE

Jamais l'ecart au natif : un mutant inerte le franchirait aussi (piege #441/#446).

  `mean`            -- divise la somme par |cibles|          -> mord en `c2`
  `enemies_only`    -- ignore les voisins AMIS               -> mord en `cF`
  `hits1`           -- ne multiplie pas par `nrOfHits`       -> mord en `c1`, `c2`, `cF`
  `avg_minmax`      -- montant = moyenne(minDmg, maxDmg)     -> mord en `c1`, `c2`, `cF`
  `no_friendly_neg` -- `friendly=False` sur les amis         -> mord en `cF` SEUL
  `include_target`  -- compte AUSSI la cible principale      -> mord PARTOUT, `c0` compris

Chaque mutant est joue a TOUS les crans ; la reciproque compte : aucun ne doit mordre partout sauf
`include_target`, dont c'est precisement la signature.

Usage :
    python scripts/python/probe_419r1tr13_shrapnel.py --state-file <chemin ABSOLU>
        [--state-file-base <chemin ABSOLU>] [--mutants]

ASCII only. Garde jumelle :
`scripts/python/tests/engine/test_419r1tr13_shrapnel_live.py`.
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
SEED = "41116"
HOST = "tauMarksman"            # HERO au pool, arme distance portee 3 -- greffon, `replace=True`
ALLY = "necroWarden"            # AMI du caster : le voisin du cran `cF`
T_MAIN = "astraBullgryn"        # la cible, FIXE dans tous les crans
FOE1 = "astraCreed"             # ennemi mobile 1
FOE2 = "astraDreir"             # ennemi mobile 2
FOES = (T_MAIN, FOE1, FOE2)
MINE = (HOST, ALLY)

ABILITY = int(TriggeredAbilityType.Shrapnel)                     # 1116
EPS = 1e-4                      # Fix64 natif contre float du port
HP = 10000                      # personne ne meurt (minDmg ~443 x 1.2 << HP), et le composite
                                # DamageDealt reste dans sa zone LINEAIRE -> `hits1` / `mean`
                                # deplacent visiblement le terme
ATTACK_RANGE = 3                # arme distance de `tauMarksman` -- RE-ATTESTEE au montage

STEPS = ("c0", "c1", "c2", "cF")
# (ennemis adjacents a T, amis adjacents a T) attendus, RE-DERIVES et verifies contre le live.
EXPECTED_COUNT = {"c0": (0, 0), "c1": (1, 0), "c2": (2, 0), "cF": (0, 1)}
MUTANTS = ("mean", "enemies_only", "hits1", "avg_minmax", "no_friendly_neg", "include_target")


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
    """Le port avec le playbook 1116 RETIRE du registre -- la reference qui isole le terme cote
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
    """Le seed BC du bras `graft` (1116 monte sur l'hote) ou `base` (le MEME, moins 1116)."""
    out = os.path.join(logs_dir, f"shrap_{arm}_seedbc.json")
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

def native_neighbours(t: tuple, cells: set, elev: dict) -> list:
    """Voisins de `t` au sens d'`IterateAdjacentTiles` : ring-1 hex AVEC la porte
    `|delta elevation| < 2`. Le voisinage NU (`hexgeo.neighbors`) sur-compte."""
    return [q for q in hexgeo.neighbors(t[0], t[1]) if q in cells and bq.is_adjacent(t, q, elev)]


def find_layout(cells: list, elev: dict) -> "dict | None":
    """Cherche `(C, T, P1, P2, K1, K2, K3)` satisfaisant EXACTEMENT le regime decrit en tete.

    `T` a portee de tir de `C` et NON adjacente a `C` (sinon `C`, qui est son propre ami, serait un
    voisin AMI a TOUS les crans -- `c0` ne serait plus un zero et `cF` ne discriminerait plus) ;
    `P1`/`P2` deux tuiles voisines-NATIVES de `T` ; `K1..K3` trois garages NON voisins de `T`."""
    d = hexgeo.distance
    cs = set(cells)
    ctr = (sum(c for c, _ in cells) / len(cells), sum(r for _, r in cells) / len(cells))
    for c in sorted(cells, key=lambda q: (q[0] - ctr[0]) ** 2 + (q[1] - ctr[1]) ** 2):
        for t in [q for q in cells if 2 <= d(c, q) <= ATTACK_RANGE
                  and not bq.is_adjacent(c, q, elev)]:
            nb = [q for q in native_neighbours(t, cs, elev) if q != c]
            if len(nb) < 2:
                continue
            p1, p2 = nb[0], nb[1]
            busy = {c, t, p1, p2}
            garages = [q for q in cells
                       if q not in busy and not bq.is_adjacent(t, q, elev)
                       and d(q, t) >= 2 and d(q, c) >= 2]
            picked = []
            for q in garages:
                if all(d(q, o) >= 2 for o in picked):
                    picked.append(q)
                if len(picked) == 3:
                    break
            if len(picked) < 3:
                continue
            return {"C": c, "T": t, "P1": p1, "P2": p2,
                    "K1": picked[0], "K2": picked[1], "K3": picked[2]}
    return None


def attest_layout(pos: dict, ids: dict, elev: dict) -> None:
    """RE-MESURE le regime sur les positions LIVE et refuse s'il n'est pas celui voulu."""
    d = hexgeo.distance
    p = {k: pos.get(uid) for k, uid in ids.items()}
    missing = [k for k, v in p.items() if v is None]
    if missing:
        raise MontageError(f"montage NON INSTALLE : position inconnue pour {missing}")
    checks = [
        ("T a portee de C", d(p["C"], p["T"]) <= ATTACK_RANGE),
        ("T NON adjacente a C", not bq.is_adjacent(p["C"], p["T"], elev)),
    ]
    bad = [name for name, ok in checks if not ok]
    if bad:
        raise MontageError(f"montage NON INSTALLE : contraintes violees {bad} -- positions {p}")


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
    for key, vis in (("T", T_MAIN), ("E1", FOE1), ("E2", FOE2)):
        u = next((x for x in units if x.get("owner") != myplayer and x.get("alive")
                  and x.get("visualId") == vis), None)
        if u is None:
            raise MontageError(f"montage NON INSTALLE : {vis} absent du roster adverse")
        ids[key] = u["id"]
    return dv, ids, myplayer


def _attest_wired(rpc, rid: int, cid: int, expect_ability: bool) -> list:
    """Moitie CABLAGE du patron #419 : 1116 est-il DANS l'`AbilitiesComponent` du caster ? Et quels
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
    dv, ids, myplayer = _roster(rpc, rid)
    others = _attest_wired(rpc, rid, ids["C"], expect_ability)
    cells = sorted(p for p, wk in walk.items() if wk and elev.get(p) is not None)
    if not cells:
        raise MontageError("montage NON INSTALLE : boardGraph sans tuile walkable")
    lay = layout if layout is not None else find_layout(cells, elev)
    if lay is None:
        raise MontageError(f"montage NON INSTALLE : aucune configuration (C,T,P1,P2,K1..K3) sur "
                           f"{BOARD} -- les quatre crans ne seraient pas installables")
    return {"rid": rid, "cid": ids["C"], "ids": ids, "myplayer": myplayer, "dv": dv,
            "layout": lay, "walk": walk, "elev": elev, "other_playbooks": others}


def place(sid, case: dict, step: str) -> dict:
    """Amene le cran `step` sur le runner de `case`, puis RE-MESURE les positions."""
    lay, ids = case["layout"], case["ids"]
    wanted = {
        "c0": {ids["C"]: lay["C"], ids["T"]: lay["T"],
               ids["F"]: lay["K1"], ids["E1"]: lay["K2"], ids["E2"]: lay["K3"]},
        "c1": {ids["C"]: lay["C"], ids["T"]: lay["T"],
               ids["F"]: lay["K1"], ids["E1"]: lay["P1"], ids["E2"]: lay["K3"]},
        "c2": {ids["C"]: lay["C"], ids["T"]: lay["T"],
               ids["F"]: lay["K1"], ids["E1"]: lay["P1"], ids["E2"]: lay["P2"]},
        "cF": {ids["C"]: lay["C"], ids["T"]: lay["T"],
               ids["F"]: lay["P1"], ids["E1"]: lay["K2"], ids["E2"]: lay["K3"]},
    }[step]
    if not P124._drive_to(sid, case["rid"], case["walk"], case["elev"], wanted):
        _dv, pos = P124._positions(sid, case["rid"])
        raise MontageError(f"cran {step} NON INSTALLE (runner {case['rid']}) : placement incomplet "
                           f"-- voulu {wanted}, obtenu { {u: pos.get(u) for u in wanted} }")
    P124._give_turn_back(sid, case["rid"], case["myplayer"])
    _dv2, pos = P124._positions(sid, case["rid"])
    attest_layout(pos, ids, case["elev"])
    return pos


def derive_counts(pos: dict, ids: dict, elev: dict) -> tuple:
    """`(|ennemis du caster adjacents a T|, |amis du caster adjacents a T|)`, RE-DERIVES des
    positions live avec l'adjacence NATIVE. C'est l'arbitre du cran, jamais le port. Le CASTER est
    compte parmi les amis : le selecteur natif ne le retire pas."""
    tp = pos.get(ids["T"])
    if tp is None:
        raise MontageError("cardinal NON DERIVABLE : position de la cible inconnue")
    foes = sum(1 for k in ("E1", "E2")
               if pos.get(ids[k]) is not None and bq.is_adjacent(tp, pos[ids[k]], elev))
    friends = sum(1 for k in ("C", "F")
                  if pos.get(ids[k]) is not None and bq.is_adjacent(tp, pos[ids[k]], elev))
    return foes, friends


# --------------------------------------------------------------------------- contre-epreuves

def _mutant_class(mutant: str):
    """Sous-classe du port LIVRE dont UNE lecture est retournee. On derive du module reel : un
    mutant qui reimplemente tout ne prouverait rien sur le code livre."""
    from engine.playbook import shrapnel as SH
    from engine.playbook.probable_damage_event import (ProbableDamageEvent,
                                                       calculate_utility_from_damage_event)
    from engine.entities.effects.magnitude import ability_var

    class _Mut(SH.ShrapnelPlaybook):
        def calculate_attack_utility_in_steps(self, ctx, attacker_uid, ability_id, case_tgt_id,
                                              attack_tile, prediction=None):
            sc = getattr(ctx, "scene", None)
            if sc is None or attack_tile is None:
                return 0.0
            if ability_id is None or not is_regular_attack(int(ability_id)):
                return 0.0
            targets = SH.splash_targets(sc, attacker_uid, case_tgt_id)
            if mutant == "include_target" and case_tgt_id is not None:
                targets = list(targets) + [case_tgt_id]
            cteam = sc.team(attacker_uid)
            if mutant == "enemies_only":
                targets = [u for u in targets if sc.team(u) != cteam]
            if not targets:
                return 0.0
            amount = self._min_damage(sc, attacker_uid)
            if mutant == "avg_minmax":
                mx = ability_var(SH._ABILITY_NAME, "maxDmg",
                                 (sc.ability_state(attacker_uid, self.ability_id) or {}).get("level")
                                 or (sc.ablvl_by_id or {}).get(attacker_uid),
                                 multiplier_pct=int(
                                     (sc.ability_state(attacker_uid, self.ability_id) or {})
                                     .get("multiplier")
                                     or (sc.mult_by_id or {}).get(attacker_uid) or 100))
                if amount and mx:
                    amount = (int(amount) + int(mx)) // 2
            if not amount:
                return 0.0
            hits = 1 if mutant == "hits1" else self._hits()
            if hits <= 0:
                return 0.0
            total = 0.0
            for u_id in targets:
                pred = self._predict_vs(sc, attacker_uid, u_id, int(amount), attack_tile)
                if pred is None:
                    continue
                t_u = sc.team(u_id)
                friendly = (cteam is not None and t_u is not None and t_u == cteam
                            and mutant != "no_friendly_neg")
                ev = ProbableDamageEvent(target=u_id, prediction=pred, friendly=friendly)
                total += hits * calculate_utility_from_damage_event(
                    ev, ctx.wt, (ctx.hpmax_by_id or {}).get(u_id))
            return total / len(targets) if mutant == "mean" else total

    return _Mut


def measure_mutant_here(ctx, ab, tgt, tile, mutant: str, ref: float) -> dict:
    """Le port MUTE sur la geometrie COURANTE (le cran qui vient d'etre place)."""
    import engine.playbook.psyker as PSY
    saved = PSY.TRIGGERED_ATTACK_PLAYBOOKS[ABILITY]
    PSY.TRIGGERED_ATTACK_PLAYBOOKS[ABILITY] = _mutant_class(mutant)()
    try:
        got = pair_port(ctx, ab, tgt, tile)
    finally:
        PSY.TRIGGERED_ATTACK_PLAYBOOKS[ABILITY] = saved
    return {"mutant": mutant, "port": got, "port_ref": ref, "shift": got - ref}


def measure(sid, rpc, graft: dict, base: dict, mutants: bool = False) -> tuple:
    """Un cran = un placement IDENTIQUE sur les deux bras, puis quatre nombres : `nat_graft`,
    `nat_base` (leur DIFFERENCE est le terme natif), `port` et `port_muted` (leur difference est le
    terme porte). Les contre-epreuves sont jouees PENDANT que le cran est installe."""
    rows, muts = [], []
    for step in STEPS:
        pos_g = place(sid, graft, step)
        pos_b = place(sid, base, step)
        cnt_g = derive_counts(pos_g, graft["ids"], graft["elev"])
        cnt_b = derive_counts(pos_b, base["ids"], base["elev"])
        if cnt_g != cnt_b:
            raise MontageError(f"cran {step} DESAPPARIE : cardinaux {cnt_g} != {cnt_b}")
        if cnt_g != EXPECTED_COUNT[step]:
            raise MontageError(f"cran {step} NON INSTALLE : (ennemis, amis) RE-DERIVES = {cnt_g}, "
                               f"attendu {EXPECTED_COUNT[step]}")
        tile = pos_g[graft["ids"]["C"]]
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
            raise MontageError(f"cran {step} NON MESURABLE : tuile {tile} hors des tuiles d'action")
        tgt = graft["ids"]["T"]
        nat_g = pair_native(rpc, graft["rid"], graft["cid"], tgt, ab, tile)
        nat_b = pair_native(rpc, base["rid"], base["cid"], base["ids"]["T"], ab,
                            pos_b[base["ids"]["C"]])
        port = pair_port(ctx, ab, tgt, tile)
        muted = pair_port_muted(ctx, ab, tgt, tile)
        rows.append({"step": step, "foes": cnt_g[0], "friends": cnt_g[1], "tile": tile, "ab": ab,
                     "native_graft": nat_g, "native_base": nat_b, "native_term": nat_g - nat_b,
                     "port": port, "port_muted": muted, "port_term": port - muted})
        if mutants:
            for m in MUTANTS:
                r = measure_mutant_here(ctx, ab, tgt, tile, m, port)
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
    print(f"runners graft={rid_g} base={rid_b} | hote {HOST} u{graft['cid']} @ {lay['C']}")
    print(f"  layout T={lay['T']} P1={lay['P1']} P2={lay['P2']} "
          f"K1={lay['K1']} K2={lay['K2']} K3={lay['K3']}")
    if graft["other_playbooks"]:
        print(f"  NB autres playbooks du registre sur le caster : {graft['other_playbooks']} "
              f"(neutralises par le bras apparie)")

    rows, muts = measure(sid, rpc, graft, base, mutants=args.mutants)
    for r in rows:
        print(f"  [{r['step']}] foes={r['foes']} friends={r['friends']} "
              f"natG={r['native_graft']:.6f} natB={r['native_base']:.6f} "
              f"TERME_NAT={r['native_term']:+.6f} | port={r['port']:.6f} "
              f"mute={r['port_muted']:.6f} TERME_PORT={r['port_term']:+.6f} "
              f"ecart={r['port_term'] - r['native_term']:+.9f}")
    for m in muts:
        print(f"  [mutant {m['mutant']:<16} @{m['step']}] deplacement du port = {m['shift']:+.9f} "
              f"({'MORD' if abs(m['shift']) > EPS else 'inerte'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
