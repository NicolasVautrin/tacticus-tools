"""#446-r3 -- le TROISIEME mold de prediction d'attaque normale : `RighteousRepugnance`, gate MELEE.

`IdunBattleLogic.Entities.Abilities.Active.Loki.RighteousRepugnance_NormalAttackAbility$$PredictAttack`
a la structure du mold ferme par #446-r1 et la gate INVERSEE :

    base   = ALoki_NormalAttackAbility.PredictAttack(entities, abilityState);
    weapon = ALoki_NormalAttackAbility.FindAttackWeapon(entities, abilityState);
    if (weapon != null && weapon.get_IsMelee()) {          //  <-- `IsMelee != 0`, pas `== 0`
        add = GetAdditionalDamagePrediction(entities, abilityState);
        DamagePredictionResult.Add(&add, &base);
        return add;
    }
    return base;

et son `GetAdditionalDamagePrediction` a le corps IDENTIQUE a celui de `Boltstorm` (memes appels,
memes slots, meme SLOT 4 `AAmountFormula$$CalculateAverage` ; seuls le guard statique et l'adresse
different -- copies COMDAT non fusionnees). C'est donc le MEME mold Python, sous l'autre gate.

⚠ LE PIEGE DE CETTE TRANCHE : le montage qui exerce le mold de #446-r1 (tir A DISTANCE) est
EXACTEMENT celui qui n'exercerait PAS celui-ci. Le regime NOMINAL est donc le CONTACT, et le
probe REFUSE de mesurer s'il ne l'a pas installe (`MontageError`, jamais un vert silencieux).

Porteur : `RighteousRepugnance` est le passif d'`adeptMorvenn` (Morvenn Vahl), HERO **AU POOL** --
aucun montage catalogue n'est necessaire. Elle porte les deux armes qu'il faut pour le controle
apparie de gate : `Power` melee (2 coups, pierce 40) et `Bolter` distance 3 (3 coups, pierce 20).

Trois crans, tous sur le MEME runner et la MEME paire (seule la TUILE DE TIR change) :

    `melee`   -- caster ADJACENT NATIF a la cible : arme melee choisie -> le mold FOLDE.
    `ranged`  -- caster a distance 2..3 : arme Bolter choisie -> le mold NE FOLDE PAS.
                 C'est la contre-epreuve de GATE, et elle est indispensable : un port qui folderait
                 inconditionnellement passerait tout le reste.

et un QUATRIEME cran sur un runner SEPARE (controle apparie) :

    `base`    -- meme board, meme seed, meme layout, seule difference
                 `--unit-stat "adeptMorvenn:PassiveAbilities=[]"` : l'attaque normale retombe sur la
                 generique et le fold DISPARAIT cote natif. C'est ce qui MESURE la base native au
                 lieu de la supposer -- la manoeuvre qui a debloque #446-r1. `natif_melee moins
                 base_native` EST alors le fold natif, isole, comparable au fold du port.

Usage :
    python scripts/python/probe_446_r3_repugnance_followup.py --state-file <chemin ABSOLU>
        [--board MC1_67] [--seed 41504] [--mutants] [--paired --state-file-b <chemin ABSOLU>]

ASCII only. Garde jumelle : `scripts/python/tests/engine/test_446_r3_repugnance_followup_live.py`.
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
from engine import battle_query as bq                            # noqa: E402
from engine import weights as W                                  # noqa: E402
from engine.ai import context as _ai_ctx                         # noqa: E402
from engine.entities.effect_type import EffectType               # noqa: E402
from engine.playbook import scene as _scene                      # noqa: E402

BOARD = "MC1_67"
SEED = "41504"
CASTER = "adeptMorvenn"          # HERO AU POOL ; `RighteousRepugnance` est son SEUL passif
TARGET = "astraBullgryn"         # la cible mesuree
FILLER = "astraCreed"            # une seconde unite adverse, garee LOIN (elle ne doit rien changer)
FOES = (TARGET, FILLER)
PASSIVE = "RighteousRepugnance"
NORMAL_ATTACK_ID = 1182          # `1182 RighteousRepugnance_NormalAttack` -- ATTESTE live, jamais suppose
TRIGGERED_ID = 1107              # `TriggeredAbilityType.RighteousRepugnance` (le passif du kit)
OVERWATCH = int(EffectType.Overwatch_AutoAttack)   # 1009
RANGED_RANGE = 3                 # `Bolter` d'`adeptMorvenn` (gameconfig) -- RE-ATTESTE au montage
HP = 40000                       # personne ne doit mourir : `Health` ET `RemainingHealth` (#438)
EPS = 1e-4

_BASE_ARGS = ["--board", BOARD, "--p-units", CASTER, "--a-units", ",".join(FOES),
              "--unit-stat", ";".join(f"{v}:Health={HP},RemainingHealth={HP}"
                                      for v in (CASTER,) + FOES)]
# CONTROLE APPARIE : le SEUL delta est le passif retire -> l'attaque normale retombe sur la
# generique et le natif cesse de folder. Mirror de la manoeuvre #446-r1.
PAIRED_EXTRA = ["--unit-stat", f"{CASTER}:PassiveAbilities=[]"]


class MontageError(RuntimeError):
    """Le montage ne s'installe pas -- la mesure n'a PAS eu lieu (jamais un vert silencieux)."""


# --------------------------------------------------------------------------- oracles

def native_fields(rpc, rid, cid, tgt, ab, tile) -> dict:
    """`aiPlaybookPredict` -- les champs de l'event que le playbook NATIF construit pour la paire,
    PREDITS DEPUIS `tile`. C'est l'ORACLE de cette tranche (l'etage PREDICTION)."""
    import engine_agreement_stages as EAS
    r = rpc("aiPlaybookPredict", {"runnerId": rid, "unitId": cid, "targetId": tgt,
                                  "abilityType": ab, "col": tile[0], "row": tile[1]}, 60) or {}
    if not r.get("ok"):
        raise MontageError(f"aiPlaybookPredict indisponible depuis {tile} / cible {tgt}: {r}")
    evs = r.get("events") or []
    ev = next((e for e in evs if e.get("targetId") == tgt), evs[0] if evs else None)
    if ev is None:
        raise MontageError(f"aiPlaybookPredict ne rend AUCUN event depuis {tile} / cible {tgt}")
    return EAS._fields_from_native_event(ev, block_amount=0), ev


def port_fields(scene, cid, tgt, tile) -> dict:
    from engine.playbook.prediction.normal_attack import make_normal_attack_predictions
    ev = make_normal_attack_predictions(scene, cid, tgt, tile)
    if ev is None:
        raise MontageError(f"le port ne produit AUCUNE prediction depuis {tile} sur {tgt}")
    return ev.composite_fields(), ev


_CMP_KEYS = ("rawHealthDmgMin", "rawHealthDmgMax", "healthDmgMin", "healthDmgMax", "appliedHits")


def compare(off_f: dict, nat_f: dict) -> dict:
    """Diff CHAMP A CHAMP restreint aux champs que ce mold peut deplacer. Un dict VIDE = accord."""
    return {k: {"off": off_f.get(k), "nat": nat_f.get(k)}
            for k in _CMP_KEYS if off_f.get(k) != nat_f.get(k)}


# --------------------------------------------------------------------------- montage

def _fresh_ctx(rpc, rid, cid):
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    mov = rpc("aiMovableTiles", {"runnerId": rid}, 60)
    mbu = {u.get("unitId"): u for u in (mov.get("units") or [])}
    return dv, _ai_ctx.build(rpc, rid, dv, mbu, cid, W.load(),
                             _scene.build_predictor(rpc, rid))


def find_layout(cells: list, elev: dict) -> dict | None:
    """Cherche `(T, MELEE, RANGED, PARK)` :

      `T`      la cible ;
      `MELEE`  une tuile ADJACENTE AU SENS NATIF de `T` (`bq.is_adjacent`, porte d'elevation
               `|delta| < 2` comprise) -- sans elle la gate `IsMelee` n'est PAS exercee ;
      `PARK`   un garage lointain pour le filler (il ne doit toucher a rien).

    ⚠ La tuile `RANGED` n'est PAS choisie ici : elle doit appartenir aux TUILES D'ACTION de
    l'oracle, qui ne sont connues qu'APRES le drive (elles dependent de la position reelle du
    caster). La choisir sur la seule geometrie donne une tuile hors portee de mouvement, et le
    montage echoue au dernier moment -- mesure du premier passage de ce probe."""
    d = hexgeo.distance
    cs = set(cells)
    ctr = (sum(c for c, _ in cells) / len(cells), sum(r for _, r in cells) / len(cells))
    for t in sorted(cells, key=lambda q: (q[0] - ctr[0]) ** 2 + (q[1] - ctr[1]) ** 2):
        adj = [q for q in hexgeo.neighbors(t[0], t[1])
               if q in cs and bq.is_adjacent(t, q, elev)]
        if not adj:
            continue
        park = [q for q in cells if d(t, q) >= 4 and q not in adj]
        if not park:
            continue
        return {"T": t, "MELEE": adj[0], "PARK": park[0]}
    return None


def pick_melee_elev_tile(ctx, tpos, elev) -> tuple | None:
    """La tuile d'un TROISIEME cran : adjacente NATIVE a la cible (donc la gate `IsMelee` tient
    encore) mais EN SURPLOMB (`elev(tuile) > elev(cible)`), ce qui arme le bonus d'ELEVATION.

    ⚠ Sans ce cran la contre-epreuve `no_mods` NE MORD PAS -- mesure du premier passage : sur une
    tuile de PLAIN-PIED les modifiers de l'attaquant sont vides, donc `mods=None` et `mods=mods`
    rendent la MEME chose et le bras reste vert pour une raison qui n'a rien a voir avec le port.
    C'est le meme facteur que #446-r1 avait fini par nommer (bonus d'elevation de la tuile de tir,
    et non un trait au nom evocateur)."""
    acts = [tuple(t) for t in (ctx.action_tiles or []) if t and t[0] is not None]
    te = elev.get(tuple(tpos))
    if te is None:
        return None
    cand = [q for q in acts
            if bq.is_adjacent(tpos, q, elev) and (elev.get(q) or 0) > te]
    return cand[0] if cand else None


def pick_ranged_tile(ctx, tpos, elev) -> tuple | None:
    """La tuile du cran TEMOIN, choisie DANS les tuiles d'action de l'oracle : a portee du `Bolter`
    (distance hex 2..3 de la cible), NON adjacente au sens NATIF (sinon l'arme melee serait encore
    choisie et les deux crans mesureraient la meme chose), et non obscurcie."""
    d = hexgeo.distance
    acts = [tuple(t) for t in (ctx.action_tiles or []) if t and t[0] is not None]
    cand = [q for q in acts
            if 2 <= d(tpos, q) <= RANGED_RANGE and not bq.is_adjacent(tpos, q, elev)
            and not bq.is_target_tile_obscured(q, tpos, elev)]
    return cand[0] if cand else None


def _stage(sid, rpc, rid: int, *, expect_fold: bool) -> dict:
    """Installe le montage et ATTESTE tout ce dont la mesure depend. `expect_fold=False` = le bras
    de CONTROLE APPARIE (passif retire) : on y exige l'INVERSE sur l'attaque normale live."""
    elev, walk, _tid = P124._board(sid, rid)
    dv = rpc("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
    units = dv.get("units") or []
    mine = [u for u in units if u.get("ctrl") and u.get("alive")]
    cid = next((u["id"] for u in mine if u.get("visualId") == CASTER), None)
    if cid is None:
        raise MontageError(f"montage NON INSTALLE : {CASTER} absent du roster")
    myplayer = mine[0].get("owner")
    vis_uid = {}
    for vis in FOES:
        u = next((x for x in units if x.get("owner") != myplayer and x.get("alive")
                  and x.get("visualId") == vis), None)
        if u is None:
            raise MontageError(f"montage NON INSTALLE : {vis} absent du roster adverse")
        vis_uid[vis] = u["id"]

    # (a) LES DEUX ARMES. Sans une melee ET une distance sur le MEME porteur, le controle de gate
    #     n'existe pas -- on ne pourrait pas separer « le mold ne folde pas » de « l'arme choisie
    #     n'a pas change ».
    from engine.services.battle_query import find_ranged_weapon
    kit = __import__("gameconfig").unit(CASTER) or {}
    weapons = kit.get("weapons") or []
    # Le gameconfig ne porte PAS de flag `melee` : le discriminant est `Range` (absent/0 = melee).
    def _is_melee(w):
        return int(w.get("Range") or 0) <= 0
    if not any(_is_melee(w) for w in weapons) or not any(not _is_melee(w) for w in weapons):
        raise MontageError(f"montage NON INSTALLE : {CASTER} n'a pas les DEUX armes -- {weapons}")
    rw = find_ranged_weapon(CASTER)
    if rw is None or int(rw.get("Range") or 0) != RANGED_RANGE:
        raise MontageError(f"montage NON INSTALLE : l'arme distance de {CASTER} vaut {rw}, "
                           f"portee attendue {RANGED_RANGE}")

    # (b) LA GEOMETRIE, puis le DRIVE (jamais « bloque par le spawn »).
    cells = sorted(p for p, wk in walk.items() if wk and elev.get(p) is not None)
    if not cells:
        raise MontageError("montage NON INSTALLE : boardGraph sans tuile walkable")
    lay = find_layout(cells, elev)
    if lay is None:
        raise MontageError(f"montage NON INSTALLE : aucune configuration (T, MELEE, RANGED) sur "
                           f"{BOARD} -- la gate `IsMelee` ne serait pas exercee")
    ids = {"C": cid, "T": vis_uid[TARGET], "F": vis_uid[FILLER]}
    wanted = {ids["C"]: lay["MELEE"], ids["T"]: lay["T"], ids["F"]: lay["PARK"]}
    if not P124._drive_to(sid, rid, walk, elev, wanted):
        _dv, pos = P124._positions(sid, rid)
        raise MontageError(f"montage NON INSTALLE : placement incomplet -- voulu {wanted}, "
                           f"obtenu { {u: pos.get(u) for u in wanted} }")
    P124._give_turn_back(sid, rid, myplayer)
    _dv2, pos = P124._positions(sid, rid)
    tp = pos[ids["T"]]
    if not bq.is_adjacent(pos[ids["C"]], tp, elev):
        raise MontageError(f"regime MELEE NON INSTALLE : le caster {pos[ids['C']]} n'est PAS "
                           f"adjacent NATIF a la cible {tp} -- la gate n'est pas exercee")

    dv, ctx = _fresh_ctx(rpc, rid, cid)
    lay["MELEE_ELEV"] = pick_melee_elev_tile(ctx, tp, elev)
    lay["RANGED"] = pick_ranged_tile(ctx, tp, elev)
    if lay["RANGED"] is None:
        raise MontageError(f"regime RANGED NON INSTALLE : aucune tuile d'action a distance 2..{RANGED_RANGE} "
                           f"de la cible {tp} qui ne lui soit PAS adjacente NATIVE -- le cran temoin "
                           f"de la gate n'existe pas, et un port qui folderait inconditionnellement "
                           f"passerait la mesure")

    # (c) L'ATTAQUE NORMALE LIVE. C'est L'ATTESTATION centrale : `1182` prouve que la SOUS-CLASSE
    #     surchargeante est bien instanciee. Le bras apparie exige l'inverse (retour a la generique).
    ab = next(iter(ctx.normal_ids or ()), None)
    if ab is None:
        raise MontageError("montage NON INSTALLE : aucune attaque normale sur le caster")
    if expect_fold and int(ab) != NORMAL_ATTACK_ID:
        raise MontageError(f"montage NON INSTALLE : l'attaque normale live du caster est {ab}, "
                           f"attendu {NORMAL_ATTACK_ID} -- la sous-classe surchargeante n'est PAS "
                           f"instanciee, rien de ce qui suit ne mesurerait le mold")
    if not expect_fold and int(ab) == NORMAL_ATTACK_ID:
        raise MontageError(f"controle apparie NON INSTALLE : l'attaque normale est TOUJOURS {ab} "
                           f"malgre le passif retire -- il n'y aurait pas de base sans fold")

    # (d) Le passif dans l'AbilitiesComponent (moitie CABLAGE), meme exigence inversee.
    st = rpc("unitAbilityStates", {"runnerId": rid, "unitId": cid}, 60) or {}
    live_ids = [i for u in (st.get("units") or []) for t in (u.get("triggered") or [])
                for i in [((t.get("raw") or [None])[0])] if isinstance(i, int)]
    if expect_fold and TRIGGERED_ID not in live_ids:
        raise MontageError(f"montage NON INSTALLE : {TRIGGERED_ID} n'est PAS dans "
                           f"l'AbilitiesComponent de {CASTER} -- triggered lus {sorted(set(live_ids))}")
    if not expect_fold and TRIGGERED_ID in live_ids:
        raise MontageError(f"controle apparie NON INSTALLE : {TRIGGERED_ID} est TOUJOURS dans "
                           f"l'AbilitiesComponent malgre le patch")

    # (e) Pas d'overwatch sur la cible : il ajouterait un event et brouillerait le diff.
    u = next((x for x in (dv.get("units") or []) if x.get("id") == ids["T"]), None)
    types = {int(e["effectType"]) for e in ((u or {}).get("effects") or [])
             if isinstance(e, dict) and e.get("effectType") is not None}
    if OVERWATCH in types:
        raise MontageError(f"montage AMBIGU : la cible porte l'overwatch {OVERWATCH}")

    for key, tile in (("MELEE", lay["MELEE"]), ("RANGED", lay["RANGED"])):
        acts = [t for t in (ctx.action_tiles or []) if t and t[0] is not None]
        if tuple(tile) not in [tuple(t) for t in acts]:
            raise MontageError(f"montage NON INSTALLE : la tuile {key} {tile} n'est pas dans les "
                               f"tuiles d'action de l'oracle -- natif et port ne compareraient pas "
                               f"la meme chose")
    return {"rid": rid, "cid": cid, "myplayer": myplayer, "ids": ids, "ab": int(ab), "ctx": ctx,
            "dv": dv, "layout": lay, "walk": walk, "elev": elev, "wanted": wanted}


def _steps(lay: dict) -> list[tuple]:
    """Les crans mesurables, tous sur la MEME paire : seule la TUILE DE TIR change. `melee_elev`
    n'existe que si le board offre un surplomb adjacent atteignable (cf. `pick_melee_elev_tile`)."""
    out = [("melee", lay["MELEE"])]
    if lay.get("MELEE_ELEV"):
        out.append(("melee_elev", lay["MELEE_ELEV"]))
    out.append(("ranged", lay["RANGED"]))
    return out


def measure(rpc, case: dict) -> list[dict]:
    """Les crans de gate, sur la MEME paire : seule la TUILE DE TIR change."""
    rows = []
    for step, tile in _steps(case["layout"]):
        nat_f, nat_ev = native_fields(rpc, case["rid"], case["cid"], case["ids"]["T"],
                                      case["ab"], tile)
        off_f, off_ev = port_fields(case["ctx"].scene, case["cid"], case["ids"]["T"], tile)
        fw = _followup_of(case, tile)
        rows.append({"step": step, "tile": tile,
                     "nat": {k: nat_f.get(k) for k in _CMP_KEYS},
                     "off": {k: off_f.get(k) for k in _CMP_KEYS},
                     "delta": compare(off_f, nat_f), "followup": fw})
    return rows


def _followup_of(case: dict, tile) -> dict | None:
    """Le fold que le PORT calcule pour cette tuile, isole (None = pas de fold). Sert a dire si le
    cran `ranged` est bien un cran SANS fold, et a chiffrer le fold du cran `melee`."""
    from engine.playbook.prediction.normal_attack import get_additional_damage_prediction
    from engine.services.battle_query import are_tiles_adjacent
    scene = case["ctx"].scene
    tgt = case["ids"]["T"]
    if not are_tiles_adjacent(tile, scene.pos(tgt), scene.board):
        return None                       # cran ranged : la gate `IsMelee` est fausse
    fw = get_additional_damage_prediction(scene, case["cid"], tgt, PASSIVE)
    if fw is None:
        return None
    return {"rawMin": fw.raw_health_damage.min, "rawMax": fw.raw_health_damage.max,
            "hits": fw.applied_hits}


# --------------------------------------------------------------------------- contre-epreuves

def mutants(rpc, case: dict) -> list[dict]:
    """CONTRE-EPREUVES du fix. Le critere est le DEPLACEMENT du PORT par rapport au port NON MUTE,
    JAMAIS l'ecart au natif : la paire peut porter des residus hors perimetre (cf. `#446-r2`), donc
    `abs(port - natif) > EPS` serait vrai meme pour un mutant INERTE.

      `no_dispatch` -- registre `_MELEE_FOLLOWUP_PASSIVES` vide : plus aucun fold en melee.
      `amount_min`  -- montant = `minDmg` seul (l'ancienne lecture « slot 4 = MIN »).
      `no_mods`     -- fold sans les modifiers de l'attaque porteuse (l'ancien `mods=None`).
      `gate_flip`   -- la gate INVERSEE (le mold branche sur `!IsMelee`, comme si on avait recopie
                       `Boltstorm` par analogie) : le fold doit DISPARAITRE en melee ET APPARAITRE
                       a distance. C'est la contre-epreuve propre a CETTE tranche.
    """
    import engine.playbook.prediction.normal_attack as NA
    tiles = dict(_steps(case["layout"]))
    scene = case["ctx"].scene
    tgt = case["ids"]["T"]

    def _port_all():
        return {k: port_fields(scene, case["cid"], tgt, t)[0] for k, t in tiles.items()}

    ref = _port_all()
    out = []
    for name in ("no_dispatch", "amount_min", "no_mods", "gate_flip"):
        saved_mel = NA._MELEE_FOLLOWUP_PASSIVES
        saved_rng = NA._RANGED_FOLLOWUP_PASSIVES
        saved_fn = NA.get_additional_damage_prediction
        saved_avg = NA.calculate_average
        try:
            if name == "no_dispatch":
                NA._MELEE_FOLLOWUP_PASSIVES = ()
            elif name == "amount_min":
                NA.calculate_average = lambda mn, mx: int(mn)
            elif name == "no_mods":
                NA.get_additional_damage_prediction = (
                    lambda *a, **k: saved_fn(*a, **{**k, "mods": None}))
            elif name == "gate_flip":
                NA._MELEE_FOLLOWUP_PASSIVES = ()
                NA._RANGED_FOLLOWUP_PASSIVES = saved_rng + (PASSIVE,)
            got = _port_all()
        finally:
            NA._MELEE_FOLLOWUP_PASSIVES = saved_mel
            NA._RANGED_FOLLOWUP_PASSIVES = saved_rng
            NA.get_additional_damage_prediction = saved_fn
            NA.calculate_average = saved_avg
        shift = {k: {c: (got[k].get(c) or 0) - (ref[k].get(c) or 0) for c in _CMP_KEYS}
                 for k in tiles}
        bites = any(v for k in tiles for v in shift[k].values())
        out.append({"mutant": name, "shift": shift, "bites": bites})
    return out


def mods_of(case: dict, tile) -> list:
    """Les %-modifiers de l'ATTAQUE PORTEUSE a cette tuile -- ce que le fold recoit. Sert a DIRE si
    un bras `no_mods` vert est vert parce que le port est bon ou parce que le regime n'a AUCUN
    modifier a perdre (mesure, pas supposition)."""
    from engine.playbook.prediction.normal_attack import make_normal_attack_predictions
    ev = make_normal_attack_predictions(case["ctx"].scene, case["cid"], case["ids"]["T"], tile,
                                        meta=True)
    return (ev[1] or {}).get("mods") if isinstance(ev, tuple) else None


# --------------------------------------------------------------------------- CLI

def build(state_file: str, extra: list[str], board: str, seed: str) -> int:
    argv = [sys.executable, "rl_duel.py", "build", "--seed", seed,
            "--state-file", state_file,
            *(a if a != BOARD else board for a in _BASE_ARGS), *extra]
    p = subprocess.run(argv, cwd=_HERE, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if p.returncode != 0:
        raise MontageError(f"rl_duel build a echoue (rc={p.returncode}) : "
                           f"{(p.stderr or p.stdout or '')[-800:]}")
    return int(json.load(open(state_file, encoding="utf-8"))["runnerId"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-file", required=True, help="chemin ABSOLU du state-file")
    ap.add_argument("--state-file-b", default=None,
                    help="chemin ABSOLU du state-file du runner APPARIE (requis avec --paired)")
    ap.add_argument("--board", default=BOARD)
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--runner", type=int, default=None, help="reutilise un runner deja monte")
    ap.add_argument("--armor-target", default=None,
                    help="force l'armure des a-units (regime PERCAGE) -- generalisation")
    ap.add_argument("--caster-damage", default=None,
                    help="force le stat Damage du caster : DEPLACE la base et doit laisser le FOLD "
                         "INCHANGE (le montant du mold vient de la CONFIG d'ability, pas du stat)")
    ap.add_argument("--mutants", action="store_true",
                    help="joue les contre-epreuves (chacune doit MORDRE)")
    ap.add_argument("--paired", action="store_true",
                    help="monte le runner APPARIE (passif retire) et chiffre le fold NATIF isole")
    args = ap.parse_args()

    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()

    def rpc(method, body=None, timeout=90):
        r = _rpc(sid, method, [body] if body is not None else [], timeout=timeout)
        return r["result"] if isinstance(r, dict) and "result" in r else r

    extra = (["--armor-target", args.armor_target] if args.armor_target else []) + \
            (["--unit-stat", f"{CASTER}:Damage={args.caster_damage}"] if args.caster_damage else [])
    rid = args.runner or build(args.state_file, extra, args.board, args.seed)
    case = _stage(sid, rpc, rid, expect_fold=True)
    lay = case["layout"]
    print(f"runner {rid} | board {args.board} seed {args.seed} | caster u{case['cid']} "
          f"({CASTER}) | attaque normale live = {case['ab']} (attendu {NORMAL_ATTACK_ID})")
    print(f"  layout T={lay['T']} MELEE={lay['MELEE']} MELEE_ELEV={lay.get('MELEE_ELEV')} "
          f"RANGED={lay['RANGED']} PARK={lay['PARK']}")
    rows = measure(rpc, case)
    for r in rows:
        print(f"  [{r['step']:<10} @ {r['tile']}] NAT ={r['nat']}")
        print(f"  [{r['step']:<10} @ {r['tile']}] PORT={r['off']}")
        print(f"      mods de l'attaque porteuse = {mods_of(case, r['tile'])} | "
              f"fold du port = {r['followup']} | "
              f"{'ACCORD' if not r['delta'] else 'DELTA ' + json.dumps(r['delta'])}")
    if args.paired:
        if not args.state_file_b:
            raise MontageError("--paired exige --state-file-b (chemin ABSOLU distinct)")
        rid_b = build(args.state_file_b, PAIRED_EXTRA + extra, args.board, args.seed)
        case_b = _stage(sid, rpc, rid_b, expect_fold=False)
        lay_b = case_b["layout"]
        if (lay_b["MELEE"], lay_b["T"]) != (lay["MELEE"], lay["T"]):
            raise MontageError(f"controle apparie NON COMPARABLE : layout {lay_b} != {lay}")
        nb, _ = native_fields(rpc, case_b["rid"], case_b["cid"], case_b["ids"]["T"],
                              case_b["ab"], lay_b["MELEE"])
        # ⚠ Le port dispatche sur le KIT GAMECONFIG, que `--unit-stat PassiveAbilities=[]` ne touche
        # PAS (il patche le BC). Sans muter le registre, le port folderait ici alors que le natif ne
        # folde plus, et le diff mesurerait le HARNAIS, pas le moteur. Vider le registre est le
        # PENDANT EXACT du patch cote natif -- c'est ce qui rend les deux bases comparables.
        import engine.playbook.prediction.normal_attack as NA
        _saved = NA._MELEE_FOLLOWUP_PASSIVES
        NA._MELEE_FOLLOWUP_PASSIVES = ()
        try:
            pb, _ = port_fields(case_b["ctx"].scene, case_b["cid"], case_b["ids"]["T"],
                                lay_b["MELEE"])
        finally:
            NA._MELEE_FOLLOWUP_PASSIVES = _saved
        mel = next(r for r in rows if r["step"] == "melee")
        print(f"  [base apparie @ {lay_b['MELEE']}] attaque normale = {case_b['ab']} | "
              f"NAT={ {k: nb.get(k) for k in _CMP_KEYS} }")
        print(f"  {'':<20} {'':<{len(str(lay_b['MELEE']))}} PORT={ {k: pb.get(k) for k in _CMP_KEYS} }")
        print(f"      base NAT vs PORT : "
              f"{'ACCORD' if not compare(pb, nb) else json.dumps(compare(pb, nb))}")
        fold_nat = {k: (mel["nat"].get(k) or 0) - (nb.get(k) or 0) for k in _CMP_KEYS}
        print(f"      FOLD NATIF ISOLE (melee moins base apparie) = {fold_nat}")
        print(f"      FOLD DU PORT                                = {mel['followup']}")
        print(f"      runner apparie {rid_b} -- pense a le disposer")
    if args.mutants:
        for m in mutants(rpc, case):
            det = " | ".join(f"{k}:" + ",".join(f"{c}{v:+d}" for c, v in m["shift"][k].items() if v)
                             for k in m["shift"] if any(m["shift"][k].values()))
            print(f"  [mutant {m['mutant']:<12}] {det or '(aucun deplacement)'} "
                  f"({'MORD' if m['bites'] else 'NE MORD PAS'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
