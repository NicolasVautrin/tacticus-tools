"""#61 -- CANAL DE COUPS des attaques d'ABILITY : le COMBAT le traverse, la PREDICTION non.

Chaine NATIVE (decompile ghidra, build gqfc5mff6c) :
  - `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` -> `AttackDamageBehaviour` (le noeud
    `hits` de l'ability est stocke en champ +0x80 ; `IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$ExecuteTarget`
    l'EVALUE et le range dans le `Nullable<int>` de l'AttackData) -> `IdunBattle.Operations.AttackDamageOperation$$Execute`
    -> `IdunBattle.Operations.AttackDamageOperation$$GetAttackHits` (slot d'interface 0xb5) ->
    `IdunBattle.Core.Services.DamagePrediction$$GetAttackHits` = `base + ExtraHits(0x11) +
    (IsMeleeAttack ? ExtraHitsMelee(0x17))`, `Math.Max(.,0)`, puis la boucle des effets (bonus
    `OwnerIsCaster` / malus `OwnerIsTarget` / clamps min). => MEME formule que l'attaque NORMALE, seule
    la BASE change (noeud `hits` de l'ability au lieu du nb de coups de l'arme).
  - `IdunBattle.Operations.AbilityDamageOperation$$Execute` (famille `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage`)
    N'APPELLE PAS `GetAttackHits` : il lit le `Nullable<int>` et l'utilise BRUT (defaut 1). => canal NON
    traverse pour cette famille, d'ou le gate `is_attack_damage_op` du port.
  - `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$GenerateMultiHitAttackPredictions`
    (chemin DECISION) evalue le noeud `hits` de l'ability et le passe TEL QUEL a `PredictAttack` (slot
    0x27) : la formule n'est PAS interposee. => la PREDICTION d'une attaque speciale IGNORE Parry &
    consorts. Asymetrie NATIVE, pas un bug du port.

Ce que ces tests PROUVENT (relations mesurees sur le natif qui tourne -- AUCUNE constante de coups en dur ;
la base vient de `constants.nrOfHits`, la difference vient du TRAIT de la cible) :
  (1) COMBAT : la MEME ability (FlailSwing 1042, `nrOfHits`=3) applique `base-1` coups contre une cible
      `Parry_ReduceHits` et `base` contre le TEMOIN -- et le port REPRODUIT les deux, per-coup bit-exact
      sur le temoin. Avant #61 le port rendait `base` dans les deux cas.
  (2) COUNTERFACTUEL load-bearing : sur le MEME etat, `is_attack_damage_op=False` (famille ABILITY, qui
      n'appelle pas `GetAttackHits`) rend `base` -- le gate de famille est le SEUL ecart et il CHANGE le
      resultat (le fold n'est donc ni mort ni inconditionnel).
  (3) PREDICTION : `aiPlaybookPredict` de la MEME ability sur la MEME cible Parry rend `base` (et non
      `base-1`) -- le port doit rendre `base` aussi. Anti-regression contre la tentation de "corriger"
      l'asymetrie.
  (4) FrenziedFiring (1036) : les coups ne sont PAS `nrOfHits` mais le noeud GEOMETRIQUE
      `IdunBattleLogic.Entities.Abilities.Active.Loki.FrenziedFiringAbility$$GetHitsForOriginalTarget` ;
      natif == port sur DEUX geometries distinctes, et le compte VARIE entre elles (anti-constante).
  (5) FrenziedFiring, VOLET AoE : le playbook emet un SECOND batch
      `GenerateMultiHitAttackPredictions` sur
      `IdunBattleLogic.Entities.Abilities.Active.Loki.FrenziedFiringAbility$$GetTargets`
      (ennemis du caster sur l'anneau hex de la cible) a `hits = 1` LITTERAL -- natif == port
      (cibles, coups ET degat) avec 0 puis 3 voisins ennemis, le caster etant REELLEMENT DEPLACE
      (le `UnitFlag.Moved` que le pas pose est lu des deux cotes, cf. `_reposition_caster`).

Drive les positions (`applyAction move` ignore portee et propriete). Lit l'etat LIVE ; aucune tuile/RVA
hardcodee. ASCII only. Runners auto-disposes par la fixture `build_runner`.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))      # import du helper sibling
from _config_oracle import trait_variable           # noqa: E402

import hexgeo
from engine.entities.pathfinding.board import Board
from engine.runner.snapshot import load_state
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.abilities.base import ability_attack_params
from engine.runner.operations.damage import AttackDamageOperation

FLAIL = 1042                     # deathBlightlord -- nrOfHits CONSTANT (3), famille ATTACK
FLAIL_NAME = "FlailSwing"
CASTER_VIS = "deathBlightlord"
PARRY_VIS = "templChampion"      # porteur du trait Parry (reduction de coups MELEE recus)
CTRL_VIS = "necroWarden"         # temoin : aucun modificateur de coups
FRENZY = 1036                    # blackObliterator -- hits = noeud GEOMETRIQUE
FRENZY_NAME = "FrenziedFiring"
FRENZY_VIS = "blackObliterator"
# 4 ennemis : 1 cible + jusqu'a 3 voisins pilotes sur son anneau (volet AoE).
FRENZY_FOES = ["necroWarden", "templChampion", "ultraTitus", "astraBullgryn"]


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _seed_rng(s):
    r = IntBasedMersenneTwister()
    r.mt = list(s["mt"]); r.mti = s["mti"]
    return r


def _board(rpc, rid):
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    return Board(bg["tiles"], adjacency="native_sym")


def _dv(rpc, rid):
    return rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 120)


def _find(dv, vis):
    return next((u for u in (dv.get("units") or [])
                 if u.get("visualId") == vis and u.get("alive")), None)


def _pos(u):
    p = u.get("pos") or {}
    return (p.get("col"), p.get("row")) if p.get("col") is not None else None


def _move(rpc, rid, uid, coord):
    rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "move", "unitId": uid, "to": {"col": coord[0], "row": coord[1]}}}, 60)


def _my_turn(rpc, rid, owner, max_turns=8):
    for _ in range(max_turns):
        if _dv(rpc, rid).get("currentPlayer") == owner:
            return True
        rpc("applyAction", {"runnerId": rid, "action": {"kind": "endturn"}}, 60)
    return False


def _reposition_caster(rpc, rid, board, cid):
    """DEPLACE REELLEMENT le caster d'UN PAS : la tuile la plus PROCHE de son movable set, la plus
    degagee a egale distance (tie-break sur le nombre de voisins marchables). Rend sa position finale.

    Le deplacement fait poser `UnitFlag.Moved` par
    `IdunBattle.Operations.MoveUnitOperation$$Execute` -> `IdunBattle.Entities.UnitExtensions$$SetMovedFlag`,
    et le port le LIT des deux cotes : `snapshot._load_unit_flags` seede le `UnitFlagsComponent` cote
    COMBAT, `Scene.moved_by_id` -> `prediction.prediction_has_moved` cote PREDICTION -- tous deux
    depuis `combatSnapshot.units[].unitFlags`. Le +25% ranged d'`HeavyWeapon_ExtraDmg` (que Volk
    porte) est donc desarme a l'identique live et offline.

    ⚠ UN SEUL essai : une unite ne dispose que d'UN deplacement par tour, donc la destination ne peut
    pas etre re-choisie apres coup. On prend le PAS MINIMAL (le but est de poser le flag, pas de
    deplacer le scenario)."""
    return _step_caster_aside(rpc, rid, board, cid, None, frozenset())


def _step_caster_aside(rpc, rid, board, cid, tpos, forbidden):
    """Pas minimal du caster, sous contraintes de geometrie. `tpos` non None -> la destination doit
    rester a distance 2..3 de la cible (ni adjacente -- ce qui changerait le `Count` de tuiles libres
    lu par `FrenziedFiringAbility$$GetHitsForOriginalTarget` -- ni hors portee) et hors de
    `forbidden` (l'anneau AoE + la tuile de la cible). Rend la position finale, inchangee si aucune
    destination ne convient."""
    mt = rpc("aiMovableTiles", {"runnerId": rid, "side": "friendly"}, 60)
    row = next((x for x in ((mt or {}).get("units") or []) if x.get("unitId") == cid), None)
    dv = _dv(rpc, rid)
    cur = _pos(_find_id(dv, cid))
    occupied = {_pos(u) for u in (dv.get("units") or []) if u.get("alive")} - {cur}

    def nbf(c):
        nid = board.id_at(c[0], c[1])
        return len([n for n in board.neighbours(nid) if board.walkable(n)]) if nid is not None else 0

    tiles = [c for c in ((t["col"], t["row"]) for t in ((row or {}).get("tiles") or []))
             if c != cur and c not in forbidden and c not in occupied
             and (tpos is None or 2 <= hexgeo.distance(c, tpos) <= 3)]
    if not tiles:
        return cur
    tiles.sort(key=lambda c: (hexgeo.distance(c, cur) if cur else 0, -nbf(c)))
    _move(rpc, rid, cid, tiles[0])
    return _pos(_find_id(_dv(rpc, rid), cid)) or cur


def _find_id(dv, uid):
    return next((u for u in (dv.get("units") or []) if u.get("id") == uid), None)


def _park_far(rpc, rid, board, dv, keep_ids, from_coord):
    """Parque LOIN toutes les unites hors `keep_ids` (isole la geometrie du scenario)."""
    far = [t for t in sorted(board.by_id)
           if board.walkable(t) and hexgeo.distance(board.coord(t), from_coord) > 5]
    it = iter(far)
    for u in (dv.get("units") or []):
        if u.get("id") in keep_ids or not u.get("alive"):
            continue
        t = next(it, None)
        if t is None:
            break
        _move(rpc, rid, u["id"], board.coord(t))


def _cast_perhit(rpc, rid, cid, tid, ability):
    """Caste et rend la liste des degats PAR COUP appliques a `tid` (1 entree == 1 coup)."""
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": cid, "targetId": tid, "abilityType": ability},
        "captureEvents": True}, 120)
    per = []
    for act in (res.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" in td and td.get("Target_Id") == tid \
                    and td.get("Active_Ability_Type") == ability:
                per.append(td.get("Amount"))
    return per, res


def _setup_melee(rpc, build_runner, seed, target_vis):
    """1v1 melee DRIVE : `CASTER_VIS` colle a `target_vis`, tout le reste parque loin.
    Rend `{rid, board, cid, tid, dv, ob, snap}` (etat capture JUSTE avant le cast) ou skip."""
    rid = build_runner(seed, extra=["--roster", "1", "--p-units", CASTER_VIS,
                                    "--a-units", f"{PARRY_VIS},{CTRL_VIS}",
                                    "--hp-target", "90000"])["rid"]
    board = _board(rpc, rid)
    dv = _dv(rpc, rid)
    me = _find(dv, CASTER_VIS)
    tgt = _find(dv, target_vis)
    if me is None or tgt is None:
        pytest.skip(f"{CASTER_VIS} ou {target_vis} absent du build")
    if not _my_turn(rpc, rid, me.get("owner")):
        pytest.skip("tour du caster non atteint")
    dv = _dv(rpc, rid)
    me = _find(dv, CASTER_VIS); tgt = _find(dv, target_vis)
    if me is None or tgt is None:
        pytest.skip("unite manquante post-turn")
    cpos = _pos(me)
    _park_far(rpc, rid, board, dv, {me["id"], tgt["id"]}, cpos)
    nbrs = [n for n in board.neighbours(board.id_at(*cpos)) if board.walkable(n)]
    if not nbrs:
        pytest.skip("aucun voisin marchable du caster")
    _move(rpc, rid, tgt["id"], board.coord(nbrs[0]))
    at = rpc("abilityTargets", {"runnerId": rid, "unitId": me["id"], "abilityType": FLAIL}, 120)
    ab = next((a for u in (at.get("units") or []) for a in (u.get("abilities") or [])
               if a.get("abilityId") == FLAIL), {})
    if tgt["id"] not in [x.get("targetId") for x in (ab.get("fromHere") or [])]:
        pytest.skip("cast FlailSwing non legal apres placement")
    dv2 = _dv(rpc, rid)
    ob2 = rpc("observeBattle", {"runnerId": rid}, 60)
    snap2 = rpc("combatSnapshot", {"runnerId": rid}, 90)
    return {"rid": rid, "board": board, "cid": me["id"], "tid": tgt["id"],
            "dv": dv2, "ob": ob2, "snap": snap2}


def _offline_hits(ctx, rng_state, **kw):
    """Rejoue l'attaque d'ability OFFLINE (memes args que le port) et rend le dict resultat."""
    st = load_state(ctx["dv"], ctx["ob"], ctx["snap"], board=ctx["board"])
    st.rng = _seed_rng(rng_state)
    bmin, bmax, pierce, hits = ability_attack_params(st, ctx["cid"], FLAIL_NAME, "Power",
                                                     ranged=False)
    args = dict(damage_profile="Power", is_melee=True, is_attack_damage_op=True,
                force_overkill=True)
    args.update(kw)
    return AttackDamageOperation.execute_ability_attack(
        st, ctx["cid"], ctx["tid"], bmin, bmax, pierce, hits, **args), hits


# ============================================================ (1)+(2) COMBAT : canal + counterfactuel

def test_ability_hits_channel_combat_defender_malus(live_session, rpc, build_runner):
    """COMBAT. Une SEULE variable entre les deux runs : le trait de la cible.
    - TEMOIN (`necroWarden`) : natif == `nrOfHits` config, port == natif, per-coup BIT-EXACT.
    - PARRY (`templChampion`) : natif == `nrOfHits - 1`, port == natif.
    Le port DOIT suivre les deux (avant #61 il rendait `nrOfHits` partout)."""
    ctl = _setup_melee(rpc, build_runner, "61101", CTRL_VIS)
    s0 = rpc("dumpRng", {"runnerId": ctl["rid"]}, 30)
    if not _ok(s0):
        pytest.skip("dumpRng KO")
    off_ctl, base_cfg = _offline_hits(ctl, s0)
    live_ctl, _ = _cast_perhit(rpc, ctl["rid"], ctl["cid"], ctl["tid"], FLAIL)
    if not live_ctl:
        pytest.skip("aucun degat live sur le temoin")
    print(f"\n[#61 combat] base_cfg={base_cfg} TEMOIN natif={len(live_ctl)} {live_ctl} "
          f"port={off_ctl.get('hits')} {off_ctl.get('per_hit')}")

    assert len(live_ctl) == base_cfg, \
        f"temoin : natif {len(live_ctl)} != nrOfHits config {base_cfg} (scenario non neutre)"
    assert off_ctl.get("hits") == len(live_ctl), \
        f"temoin : port {off_ctl.get('hits')} != natif {len(live_ctl)}"
    assert off_ctl.get("per_hit") == live_ctl, \
        f"temoin : per-coup port {off_ctl.get('per_hit')} != natif {live_ctl} (devrait etre bit-exact)"

    par = _setup_melee(rpc, build_runner, "61102", PARRY_VIS)
    tgt_fx = [e.get("name") for u in (par["dv"].get("units") or []) if u.get("id") == par["tid"]
              for e in (u.get("effects") or [])]
    if "Parry_ReduceHits" not in tgt_fx:
        pytest.skip(f"la cible ne porte pas Parry_ReduceHits (effets={tgt_fx})")
    s1 = rpc("dumpRng", {"runnerId": par["rid"]}, 30)
    if not _ok(s1):
        pytest.skip("dumpRng KO")
    off_par, base_cfg2 = _offline_hits(par, s1)
    live_par, _ = _cast_perhit(rpc, par["rid"], par["cid"], par["tid"], FLAIL)
    if not live_par:
        pytest.skip("aucun degat live sur la cible Parry")
    print(f"[#61 combat] PARRY natif={len(live_par)} {live_par} port={off_par.get('hits')} "
          f"{off_par.get('per_hit')} | tgt_effects={tgt_fx}")

    assert base_cfg2 == base_cfg, "les deux runs n'ont pas la meme base config"
    # LE MALUS EST UNE VALEUR BRUTE, LE PLANCHER UN LITTERAL NATIF. `ParryEffect$$CreateEffectHits
    # BonusForAttack` = `EffectBonus.ForAdditionWithMinimum(OwnerIsTarget & IsMeleeAttack,
    # Direct(-GetNumberConstant(config, 0x2c)), Direct(1))` -> coups = `Max(base - parryHitReduction, 1)`.
    #   * l'amplitude `-parryHitReduction` se LIT en config (le meme slot 0x2c porte
    #     `camouflageHitReduction_1`/`diminutiveHitReduction`, de MEME valeur : la cle exacte est
    #     load-bearing, une voisine passerait vert) ;
    #   * le minimum `Direct(1)` est un LITTERAL du natif (pas une constante de config) -> il reste litteral.
    # La garde ci-dessous exige que le scenario DISCRIMINE : si `base - reduction` retombait sur le
    # plancher, l'assertion serait verte meme avec le canal de coups debranche.
    parry_reduction = trait_variable("Parry", "parryHitReduction")
    expected_par = max(base_cfg - parry_reduction, 1)          # ForAdditionWithMinimum(., Direct(1))
    assert expected_par > 1, (
        f"base {base_cfg} - parryHitReduction {parry_reduction} sature le plancher natif Direct(1) : "
        f"le scenario ne DISCRIMINE plus (l'assertion serait verte moteur casse)")
    assert len(live_par) == expected_par, \
        (f"natif {len(live_par)} != base {base_cfg} - parryHitReduction {parry_reduction} "
         f"(= {expected_par}) sur une cible Parry : le canal de coups ne serait PAS traverse par le "
         f"vecteur ability (premisse du cas #61 fausse)")
    assert off_par.get("hits") == len(live_par), \
        (f"port {off_par.get('hits')} != natif {len(live_par)} : le vecteur ability ne traverse pas "
         f"la formule de coups partagee (canal #61 non branche)")

    # (2) COUNTERFACTUEL : famille ABILITY (`AbilityDamageOperation`, qui n'appelle PAS GetAttackHits)
    #     -> base PLEINE. Le gate de famille est le SEUL ecart et il CHANGE le resultat.
    off_noch, _ = _offline_hits(par, s1, is_attack_damage_op=False)
    print(f"[#61 combat] COUNTERFACTUEL famille ABILITY : hits={off_noch.get('hits')} "
          f"(attendu base={base_cfg}, != {off_par.get('hits')})")
    assert off_noch.get("hits") == base_cfg, \
        (f"famille ABILITY : {off_noch.get('hits')} != base {base_cfg} -- le fold s'appliquerait aussi "
         f"a `AbilityDamageOperation`, ce que le decompile exclut")
    assert off_noch.get("hits") != off_par.get("hits"), \
        "le gate `is_attack_damage_op` ne change RIEN -> le fold n'est pas load-bearing"


# ============================================================ (3) PREDICTION : PAS de canal (natif)

def test_ability_hits_prediction_has_no_channel(live_session, rpc, build_runner):
    """PREDICTION. `GenerateMultiHitAttackPredictions` passe le noeud `hits` TEL QUEL a `PredictAttack` :
    la meme FlailSwing PREDIT `nrOfHits` coups contre la cible Parry (alors qu'elle en APPLIQUE
    `nrOfHits-1`). Le port doit rendre la meme chose -- anti-regression contre une "correction" de
    l'asymetrie, qui est NATIVE."""
    par = _setup_melee(rpc, build_runner, "61103", PARRY_VIS)
    rid, cid, tid = par["rid"], par["cid"], par["tid"]
    tgt_fx = [e.get("name") for u in (par["dv"].get("units") or []) if u.get("id") == tid
              for e in (u.get("effects") or [])]
    if "Parry_ReduceHits" not in tgt_fx:
        pytest.skip(f"la cible ne porte pas Parry_ReduceHits (effets={tgt_fx})")
    st = load_state(par["dv"], par["ob"], par["snap"], board=par["board"])
    _bmin, _bmax, _pierce, base_cfg = ability_attack_params(st, cid, FLAIL_NAME, "Power",
                                                            ranged=False)
    r = rpc("aiPlaybookPredict", {"runnerId": rid, "unitId": cid, "targetId": tid,
                                  "abilityType": FLAIL}, 90)
    ev = next((e for e in ((r or {}).get("events") or []) if e.get("targetId") == tid), None)
    if ev is None:
        pytest.skip(f"aucun event de prediction (r={str(r)[:160]})")
    nat_pred = int(ev.get("appliedHits") or 0)

    from engine.playbook import scene as SC
    from engine.playbook.scene import Scene
    from engine.playbook import prediction as PRED
    predictor = SC.build_predictor(lambda m, b=None, t=120: rpc(m, b, t), rid)
    sctx = SC.step_context(predictor, _dv(rpc, rid))
    scene = Scene.from_predictor_sctx(predictor, sctx, None)
    evs = PRED.make_damage_predictions(scene, cid, tid, FLAIL, FLAIL_NAME,
                                       attack_pos=scene.pos(cid))
    main = next((e for e in (evs or []) if e.target == tid), None)
    if main is None:
        pytest.skip("le port n'emet pas d'event pour la cible principale")
    port_pred = int(main.prediction.applied_hits)
    print(f"\n[#61 pred] base_cfg={base_cfg} natif={nat_pred} port={port_pred} | tgt={tgt_fx}")

    assert nat_pred == base_cfg, \
        (f"la PREDICTION native rend {nat_pred} != base {base_cfg} sur une cible Parry -> le canal "
         f"SERAIT interpose cote decision (verdict #61 a revoir)")
    assert port_pred == nat_pred, \
        f"port {port_pred} != natif {nat_pred} en prediction"


# ============================================================ (4) FrenziedFiring : base GEOMETRIQUE

def test_frenzied_firing_hits_is_geometric(live_session, rpc, build_runner):
    """`FrenziedFiringAbility$$GetHitsForOriginalTarget` = `Min(nrOfHits + Count(tuiles adjacentes a la
    CIBLE, marchables, non tenues par un ennemi du caster), maxNrOfHits)`. On mesure DEUX geometries
    (cible degagee vs cible collee a un bord) : natif == port dans les deux, ET le compte VARIE (sinon
    le port pourrait n'etre qu'une constante bien choisie)."""
    rid = build_runner("61104", extra=["--roster", "1", "--p-units", FRENZY_VIS,
                                       "--a-units", CTRL_VIS, "--hp-target", "90000"])["rid"]
    board = _board(rpc, rid)
    dv = _dv(rpc, rid)
    me = _find(dv, FRENZY_VIS)
    tgt = _find(dv, CTRL_VIS)
    if me is None or tgt is None:
        pytest.skip(f"{FRENZY_VIS} ou {CTRL_VIS} absent du build")
    if not _my_turn(rpc, rid, me.get("owner")):
        pytest.skip("tour du caster non atteint")

    walk = [board.coord(t) for t in sorted(board.by_id) if board.walkable(t)]

    def nb_free(coord):
        tid_ = board.id_at(coord[0], coord[1])
        return sum(1 for n in board.neighbours(tid_) if board.walkable(n))

    open_tiles = [c for c in walk if nb_free(c) == 6]
    edge_tiles = [c for c in walk if nb_free(c) <= 4]
    if not open_tiles or not edge_tiles:
        pytest.skip(f"board sans les deux geometries (open={len(open_tiles)} edge={len(edge_tiles)})")

    from engine.playbook import scene as SC
    from engine.playbook.scene import Scene
    from engine.playbook import prediction as PRED

    def measure(tcoord):
        """Place la cible sur `tcoord` et le caster a portee, puis mesure natif ET port. La geometrie
        rendue est celle de la position REELLE de la cible apres le move (`applyAction` peut refuser
        une tuile) -- jamais celle demandee."""
        cand = [c for c in walk if 1 <= hexgeo.distance(c, tcoord) <= 2 and c != tcoord]
        if not cand:
            return None
        _move(rpc, rid, tgt["id"], tcoord)
        _move(rpc, rid, me["id"], cand[0])
        dvm = _dv(rpc, rid)
        tu = next((u for u in (dvm.get("units") or []) if u.get("id") == tgt["id"]), None)
        real = _pos(tu) if tu else None
        if real is None:
            return None
        r = rpc("aiPlaybookPredict", {"runnerId": rid, "unitId": me["id"],
                                      "targetId": tgt["id"], "abilityType": FRENZY}, 90)
        ev = next((e for e in ((r or {}).get("events") or [])
                   if e.get("targetId") == tgt["id"]), None)
        if ev is None:
            return None
        predictor = SC.build_predictor(lambda m, b=None, t=120: rpc(m, b, t), rid)
        sctx = SC.step_context(predictor, dvm)
        scene = Scene.from_predictor_sctx(predictor, sctx, None)
        evs = PRED.make_damage_predictions(scene, me["id"], tgt["id"], FRENZY, FRENZY_NAME,
                                           attack_pos=scene.pos(me["id"]))
        main = next((e for e in (evs or []) if e.target == tgt["id"]), None)
        if main is None:
            return None
        return int(ev.get("appliedHits") or 0), int(main.prediction.applied_hits), nb_free(real)

    a = measure(open_tiles[0])
    b = None
    for c in edge_tiles:                       # jusqu'a obtenir une geometrie REELLEMENT differente
        b = measure(c)
        if b is not None and a is not None and b[2] != a[2]:
            break
    if a is None or b is None:
        pytest.skip("prediction FrenziedFiring indisponible sur ce board")
    if b[2] == a[2]:
        pytest.skip(f"aucune 2e geometrie atteignable (voisins libres {a[2]} partout)")
    print(f"\n[#61 frenzy] OUVERT natif={a[0]} port={a[1]} (voisins libres={a[2]}) | "
          f"BORD natif={b[0]} port={b[1]} (voisins libres={b[2]})")

    assert a[1] == a[0], f"geometrie ouverte : port {a[1]} != natif {a[0]}"
    assert b[1] == b[0], f"geometrie de bord : port {b[1]} != natif {b[0]}"
    assert a[0] != b[0], \
        (f"le natif rend {a[0]} dans LES DEUX geometries -> le scenario n'est pas discriminant "
         f"(voisins libres {a[2]} vs {b[2]})")
    assert a[0] - b[0] == a[2] - b[2], \
        (f"l'ecart de coups ({a[0] - b[0]}) ne suit pas l'ecart de tuiles adjacentes libres "
         f"({a[2] - b[2]}) -> la formule geometrique portee n'est pas la bonne")


# ============================================================ (5) FrenziedFiring : volet AoE (2e batch)

def _pred_rows(rpc, rid, cid, tid, dv):
    """(natif, port) = liste de (targetId, appliedHits, dmgMin, dmgMax) pour le MEME etat.

    NATIF = `aiPlaybookPredict` invoque le `FrenziedFiringPlaybook.MakeDamagePredictions` natif et
    decode TOUS ses ProbableDamageEvent -- donc les DEUX batchs (cible d'origine + volet AoE)."""
    from engine.playbook import scene as SC
    from engine.playbook.scene import Scene
    from engine.playbook import prediction as PRED
    r = rpc("aiPlaybookPredict", {"runnerId": rid, "unitId": cid, "targetId": tid,
                                  "abilityType": FRENZY}, 90)
    nat = [(e.get("targetId"), e.get("appliedHits"), e.get("healthDmgMin"), e.get("healthDmgMax"))
           for e in ((r or {}).get("events") or [])]
    predictor = SC.build_predictor(lambda m, b=None, t=120: rpc(m, b, t), rid)
    sctx = SC.step_context(predictor, dv)
    scene = Scene.from_predictor_sctx(predictor, sctx, None)
    evs = PRED.make_damage_predictions(scene, cid, tid, FRENZY, FRENZY_NAME,
                                       attack_pos=scene.pos(cid)) or []
    port = [(e.target, e.prediction.applied_hits, e.prediction.accurate_health_damage.min,
             e.prediction.accurate_health_damage.max) for e in evs]
    return sorted(nat, key=lambda x: x[0] or 0), sorted(port, key=lambda x: x[0] or 0)


def test_frenzied_firing_aoe_batch_matches_native(live_session, rpc, build_runner):
    """`FrenziedFiringPlaybook.MakeDamagePredictions` emet DEUX batchs
    `GenerateMultiHitAttackPredictions` : la cible d'origine (`hits` = noeud GEOMETRIQUE, deja
    valide en (4)) PUIS un batch AoE sur `FrenziedFiringAbility$$GetTargets`
    (= `AdjacentEnemies(caster@0x160, TargetTiles@0x190, 1)` = ennemis du caster sur l'anneau hex
    de la CIBLE) avec `hits = 1` LITTERAL, concatene au premier.

    On mesure la MEME cible dans DEUX geometries pilotees, sur le MEME runner :
      - K=0 voisin ennemi  -> le volet AoE est INERTE : le natif rend UN seul event (garde de
        NON-REGRESSION du batch d'origine) ;
      - K=3 voisins ennemis -> le natif rend 1+3 events, les 3 secondaires a `hits = 1`.
    Le port doit rendre exactement les MEMES cibles, les MEMES coups et le MEME degat.

    LE CASTER EST DEPLACE au montage (`_reposition_caster`, plein champ) : le `UnitFlag.Moved` que
    `MoveUnitOperation$$Execute` pose desarme le +25% ranged d'`HeavyWeapon_ExtraDmg` que Volk porte,
    et le port lit ce flag du meme canal que le natif -- `combatSnapshot.units[].unitFlags` ->
    `Scene.moved_by_id` -> `prediction.prediction_has_moved` (#266). Les DEUX termes que la
    prediction native voit sous `HasFlag(Self, Moved)` sont donc portes : le flag reel ET la tuile
    simulee (`SimulateEffectsOperation$$DoActionInSimulatedTile` -> `SetMovedFlag`)."""
    rid = build_runner("61105", extra=["--roster", "1", "--p-units", FRENZY_VIS,
                                       "--a-units", ",".join(FRENZY_FOES),
                                       "--hp-target", "90000"])["rid"]
    board = _board(rpc, rid)
    dv = _dv(rpc, rid)
    me = _find(dv, FRENZY_VIS)
    if me is None:
        pytest.skip(f"{FRENZY_VIS} absent du build")
    if not _my_turn(rpc, rid, me.get("owner")):
        pytest.skip("tour du caster non atteint")
    dv = _dv(rpc, rid)
    me = _find(dv, FRENZY_VIS)
    foes = [u for u in (dv.get("units") or [])
            if u.get("alive") and u.get("owner") != me.get("owner")]
    if me is None or len(foes) < 4:
        pytest.skip(f"roster insuffisant (caster={bool(me)} ennemis={len(foes)})")

    cpos = _reposition_caster(rpc, rid, board, me["id"])   # DEPLACEMENT REEL -> pose `UnitFlag.Moved`
    walk = [board.coord(t) for t in sorted(board.by_id) if board.walkable(t)]

    def nb_free(coord):
        return [n for n in board.neighbours(board.id_at(*coord)) if board.walkable(n)]

    # Cible en PLEIN CHAMP (6 voisins marchables) et a portee (range 3) du caster.
    open_tiles = [c for c in walk if len(nb_free(c)) == 6 and 2 <= hexgeo.distance(c, cpos) <= 3]
    if not open_tiles:
        pytest.skip(f"aucune tuile a 6 voisins marchables a portee du caster @{cpos}")
    tgt, others = foes[0], foes[1:]
    _move(rpc, rid, tgt["id"], max(open_tiles, key=lambda c: hexgeo.distance(c, cpos)))
    dv = _dv(rpc, rid)
    tu = next((u for u in (dv.get("units") or []) if u.get("id") == tgt["id"]), None)
    tpos = _pos(tu) if tu else None
    if tpos is None:
        pytest.skip("cible non placee")
    # Anneau exploitable = voisins marchables de la cible, hors tuile du caster.
    ring = [board.coord(n) for n in nb_free(tpos) if board.coord(n) != cpos]
    far = [c for c in walk
           if hexgeo.distance(c, tpos) > 4 and hexgeo.distance(c, cpos) > 4]
    if len(ring) < 3 or len(far) < len(others):
        pytest.skip(f"geometrie insuffisante (anneau={len(ring)} tuiles lointaines={len(far)})")

    def adjacent_foes():
        d = _dv(rpc, rid)
        return sorted(u["id"] for u in (d.get("units") or [])
                      if u.get("alive") and u.get("id") != tgt["id"]
                      and u.get("owner") != me.get("owner") and _pos(u)
                      and hexgeo.distance(_pos(u), tpos) == 1), d

    # --- K = 0 : tous les autres ennemis LOIN -> volet AoE inerte (non-regression) -------------
    for i, u in enumerate(others):
        _move(rpc, rid, u["id"], far[(i * 7) % len(far)])
    adj0, dv0 = adjacent_foes()
    if adj0:
        pytest.skip(f"des ennemis restent adjacents a la cible malgre le parking : {adj0}")
    nat0, port0 = _pred_rows(rpc, rid, me["id"], tgt["id"], dv0)

    # --- K = 3 : trois ennemis SUR l'anneau -> volet AoE mordant -------------------------------
    for i, u in enumerate(others[:3]):
        _move(rpc, rid, u["id"], ring[i])
    adj3, dv3 = adjacent_foes()
    nat3, port3 = _pred_rows(rpc, rid, me["id"], tgt["id"], dv3)

    print(f"\n[#61 frenzy AoE] caster u{me['id']} @{cpos} (DEPLACE -> UnitFlag.Moved pose) "
          f"cible u{tgt['id']} @{tpos}")
    print(f"  K=0 adj={adj0} natif={nat0}")
    print(f"      port ={port0}")
    print(f"  K=3 adj={adj3} natif={nat3}")
    print(f"      port ={port3}")

    # (a) Le scenario DISCRIMINE : le natif lui-meme change de nombre d'events entre les 2 geometries.
    assert len(nat0) == 1, \
        (f"sans voisin ennemi le natif rend {len(nat0)} events (attendu 1) -> le volet AoE ne "
         f"serait pas gate par la geometrie : {nat0}")
    assert len(adj3) == 3 and len(nat3) == 1 + len(adj3), \
        (f"avec {len(adj3)} voisins ennemis le natif rend {len(nat3)} events (attendu "
         f"{1 + len(adj3)}) -> le 2e batch n'est pas `AdjacentEnemies(cible)` : {nat3}")

    # (b) Le batch AoE natif est bien a `hits = 1` LITTERAL, cible par cible.
    aoe_nat = [row for row in nat3 if row[0] != tgt["id"]]
    assert sorted(r[0] for r in aoe_nat) == adj3, \
        f"cibles du 2e batch natif {sorted(r[0] for r in aoe_nat)} != voisins ennemis {adj3}"
    assert {r[1] for r in aoe_nat} == {1}, \
        (f"le 2e batch natif n'est pas a 1 coup par cible ({[r[1] for r in aoe_nat]}) -> le "
         f"litteral `hits=1` lu au decompile est faux")

    # (c) PORT == NATIF, event par event, dans LES DEUX geometries (cibles + coups + degat).
    assert port0 == nat0, f"K=0 : port {port0} != natif {nat0}"
    assert port3 == nat3, f"K=3 : port {port3} != natif {nat3}"

    # (d) Le batch d'ORIGINE reste geometrique et n'a pas ete casse : ses coups DIMINUENT d'autant
    #     que des ennemis occupent l'anneau (chaque voisin ennemi retire une tuile du Count et
    #     ajoute un event AoE) -> anti-constante sur les DEUX volets a la fois.
    main0 = next(r for r in nat0 if r[0] == tgt["id"])
    main3 = next(r for r in nat3 if r[0] == tgt["id"])
    assert main0[1] - main3[1] == len(adj3), \
        (f"coups du batch d'origine {main0[1]} -> {main3[1]} : l'ecart ne vaut pas le nombre de "
         f"voisins ennemis ({len(adj3)}) -> la base geometrique (4) a bouge")


# ================================================ (6) FrenziedFiring : volet AoE, face COMBAT
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.FrenziedFiringAbility$$ExecuteBehaviour` (MIRROR) :
#     hitsNode = GetHitsForOriginalTarget(this)
#     A = SetCache(hitsNode) & AttackWithAttackDamage(caster@0x160, target@0x178, hits = hitsNode)
#     B = SetCache(hitsNode) & AttackWithAttackDamage(caster@0x160,
#                                 AdjacentEnemies(caster@0x160, targetTiles@0x190, 1),
#                                 hits = DSLFactory.Direct(1))
#     AtomicGroup(0x4e, <ExecuteBehaviour>b__0)  ou b__0 = Execute( op_Addition(A, B) )
#
# La face DECISION (5) ne PREDIT pas la face COMBAT : rien ne garantissait que l'execution reprenne le
# meme sous-arbre. La lecture montre qu'elle le reprend -- MEME selecteur (`GetTargets`) et MEME
# `hits = 1` (ici `Direct(1)`, la un immediat du call-site) -- d'ou la reutilisation stricte de `_AOE`
# et `AOE_HITS`, et la seule DEFINITION de `GetHitsForOriginalTarget` (partagee par les deux faces).
#
# ROSTER TEMOIN OBLIGATOIRE : aucune des 4 cibles ne porte de modificateur du canal de coups partage
# (BigTarget/Parry/LightCover/Camouflage/Diminutive). Avec un roster quelconque, les malus/bonus de ce
# canal (case-61 §1.2, deja livres, appliques aux DEUX vecteurs) melangent leur verdict a celui du
# volet mesure ici -- constate : un `astraBullgryn` (aura BigTarget) sur l'anneau retire 1 coup a la
# cible cote PORT alors que le natif n'en retire pas.
FRENZY_WITNESSES = ["necroWarden", "necroOverlord", "admecMarshall", "eldarAutarch"]
FRENZY_PROFILE_HEAVY_ROUND = 19     # `DamageProfileType.HeavyRound` = profil des DEUX volets de 1036


def _frenzy_cast_by_target(rpc, rid, cid, tid):
    """Caste 1036 et ventile les coups appliques PAR CIBLE et PAR PROFIL :
    `({cible: [coups HeavyRound]}, {cible: [coups d'un AUTRE profil]})`.

    La ventilation est INDISPENSABLE : `blackObliterator` porte en permanence un effet du cycle
    `FleshmetalGuns`, dont `IdunBattle.Operations.AttackDamageOperation$$ExecuteAdditionalHitsWithout
    DamageProfileType` greffe des coups d'un profil PROPRE (Melta/Flame/HeavyRound selon le tour du
    cycle) sur CHAQUE attaque. Ces coups appartiennent au canal #179, pas a l'arbre 1036."""
    res = rpc("applyAction", {"runnerId": rid, "action": {
        "kind": "ability", "casterId": cid, "targetId": tid, "abilityType": FRENZY},
        "captureEvents": True}, 120)
    per, other = {}, {}
    for act in (res.get("actions") or []):
        for e in (act.get("events") or []):
            td = e.get("tags")
            if not td:
                continue
            td = json.loads(td) if isinstance(td, str) else td
            if "Amount" not in td or td.get("Active_Ability_Type") != FRENZY:
                continue
            dst = per if td.get("DamageProfileType") == FRENZY_PROFILE_HEAVY_ROUND else other
            dst.setdefault(td.get("Target_Id"), []).append(td.get("Amount"))
    return per, other, res


def _frenzy_offline(rpc, rid, board, cid, tid):
    """Rejoue 1036 OFFLINE (arbre DSL `frenzied_firing_tree`) sur l'etat live, `state.rng` cale via
    `dumpRng` -- DERNIER RPC avant le cast live. Rend `{cible: [coups]}` du volet 1036."""
    from engine.runner.abilities.handler import ABILITY_CLASSES
    dv = _dv(rpc, rid)
    ob = rpc("observeBattle", {"runnerId": rid}, 60)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 90)
    st = load_state(dv, ob, snap, board=board)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not _ok(s0):
        return None
    st.rng = _seed_rng(s0)
    res = ABILITY_CLASSES[FRENZY]().execute_behaviour(st, cid, tid) or {}
    out = {tid: list(((res.get("origin_attack") or {}).get("per_hit")) or [])}
    for row in (res.get("aoe") or []):
        out[row["target"]] = list((row.get("attack") or {}).get("per_hit") or [])
    return out


def _frenzy_combat_geometry(rpc, build_runner, seed, k):
    """Monte un runner ISOLE, place la cible en PLEIN CHAMP a portee du caster et `k` de ses
    allies sur l'anneau hex de la cible (placement ADAPTATIF : un ennemi pose entre le caster et la
    cible OBSCURCIT la ligne de tir et rend le cast illegal -- on essaie l'anneau du plus LOIN au plus
    proche et on ne garde que les placements qui preservent la legalite). Caste ensuite l'ability et
    rend `(natif_HeavyRound, natif_autres_profils, port, adj, nb_voisins_marchables)`.

    UN RUNNER PAR GEOMETRIE : le cast CONSOMME l'activation de l'ability, donc deux geometries ne
    peuvent pas etre mesurees sur la meme bataille."""
    rid = build_runner(seed, extra=["--roster", "1", "--p-units", FRENZY_VIS,
                                    "--a-units", ",".join(FRENZY_WITNESSES),
                                    "--hp-target", "90000"])["rid"]
    board = _board(rpc, rid)
    dv = _dv(rpc, rid)
    me = _find(dv, FRENZY_VIS)
    if me is None:
        pytest.skip(f"{FRENZY_VIS} absent du build")
    if not _my_turn(rpc, rid, me.get("owner")):
        pytest.skip("tour du caster non atteint")
    dv = _dv(rpc, rid)
    me = _find(dv, FRENZY_VIS)
    foes = [u for u in (dv.get("units") or [])
            if u.get("alive") and u.get("owner") != me.get("owner")]
    if me is None or len(foes) < 1 + k:
        pytest.skip(f"roster insuffisant (caster={bool(me)} ennemis={len(foes)})")

    cpos = _pos(me)
    walk = [board.coord(t) for t in sorted(board.by_id) if board.walkable(t)]

    def nb_free(coord):
        return [n for n in board.neighbours(board.id_at(*coord)) if board.walkable(n)]

    open_tiles = [c for c in walk if len(nb_free(c)) == 6 and 2 <= hexgeo.distance(c, cpos) <= 3]
    if not open_tiles:
        pytest.skip(f"aucune tuile a 6 voisins marchables a portee du caster @{cpos}")
    tgt, others = foes[0], foes[1:]

    def castable():
        at = rpc("abilityTargets", {"runnerId": rid, "unitId": me["id"],
                                    "abilityType": FRENZY}, 120)
        ab = next((x for u in (at.get("units") or []) for x in (u.get("abilities") or [])
                   if x.get("abilityId") == FRENZY), {})
        return tgt["id"] in [x.get("targetId") for x in (ab.get("fromHere") or [])]

    _move(rpc, rid, tgt["id"], max(open_tiles, key=lambda c: hexgeo.distance(c, cpos)))
    dv = _dv(rpc, rid)
    tu = next((u for u in (dv.get("units") or []) if u.get("id") == tgt["id"]), None)
    tpos = _pos(tu) if tu else None
    if tpos is None:
        pytest.skip("cible non placee")
    ring = sorted((board.coord(n) for n in nb_free(tpos) if board.coord(n) != cpos),
                  key=lambda c: -hexgeo.distance(c, cpos))
    far = [c for c in walk
           if hexgeo.distance(c, tpos) > 4 and hexgeo.distance(c, cpos) > 4]
    if len(ring) < k or len(far) < len(others):
        pytest.skip(f"geometrie insuffisante (anneau={len(ring)} tuiles lointaines={len(far)})")

    for i, u in enumerate(others):                    # tout le monde LOIN d'abord
        _move(rpc, rid, u["id"], far[(i * 7) % len(far)])
    free_ring, placed = list(ring), 0
    for i, u in enumerate(others):
        if placed >= k:
            break
        for c in list(free_ring):
            _move(rpc, rid, u["id"], c)
            cur = next((x for x in (_dv(rpc, rid).get("units") or [])
                        if x.get("id") == u["id"]), None)
            if _pos(cur) == c and castable():
                free_ring.remove(c)
                placed += 1
                break
            _move(rpc, rid, u["id"], far[(i * 7) % len(far)])     # rejete -> reparque loin

    d = _dv(rpc, rid)
    adj = sorted(u["id"] for u in (d.get("units") or [])
                 if u.get("alive") and u.get("id") != tgt["id"]
                 and u.get("owner") != me.get("owner") and _pos(u)
                 and hexgeo.distance(_pos(u), tpos) == 1)
    if len(adj) != k or not castable():
        pytest.skip(f"geometrie K={k} non montee (adj={adj}, castable={castable()})")
    # DEPLACEMENT REEL DU CASTER, en DERNIER (cf. docstring) : il pose `UnitFlag.Moved` et le port le
    # lit. Il doit venir APRES tout le pilotage adverse -- une unite qui a bouge n'a plus d'action
    # pendante, donc bouger un ennemi ensuite ferait BASCULER le tour (roster 1v4 : `currentPlayer`
    # passe a l'adversaire, mesure) et le cast deviendrait impossible.
    moved_to = _step_caster_aside(rpc, rid, board, me["id"], tpos, set(ring) | {tpos})
    if moved_to == cpos:
        pytest.skip("aucun pas du caster ne preserve la geometrie -> flag Moved non exerce")
    if not castable():
        pytest.skip(f"le pas du caster vers {moved_to} a rendu le cast illegal")
    off = _frenzy_offline(rpc, rid, board, me["id"], tgt["id"])
    if off is None:
        pytest.skip("dumpRng KO -> aucune comparaison per-coup possible")
    nat, other, _res = _frenzy_cast_by_target(rpc, rid, me["id"], tgt["id"])
    return {"cid": me["id"], "tid": tgt["id"], "adj": adj, "nb_free": len(nb_free(tpos)),
            "nat": nat, "other": other, "port": off, "cpos": cpos, "moved_to": moved_to}


def _frenzy_assert_geometry(g, n_hits):
    """Assertions COMMUNES aux deux geometries : cibles touchees, base geometrique du volet
    d'origine, `hits = Direct(1)` du volet AoE, et concordance natif/port -- chaque compte borne par
    le +1 `LetTheGalaxyBurn` (chance-gate par ATTAQUE, cf. la docstring du test)."""
    tid, adj = g["tid"], g["adj"]
    expected_main = n_hits + g["nb_free"] - len(adj)   # Min(nrOfHits + Count(tuiles libres), cap)
    assert sorted(g["nat"]) == sorted([tid] + adj), \
        (f"K={len(adj)} : le natif frappe {sorted(g['nat'])} (attendu cible + voisins "
         f"{sorted([tid] + adj)}) -> le volet AoE n'est pas "
         f"`AdjacentEnemies(caster@0x160, TargetTiles@0x190, 1)`")
    assert sorted(k for k, v in g["port"].items() if v) == sorted(g["nat"]), \
        (f"K={len(adj)} : cibles du port {sorted(k for k, v in g['port'].items() if v)} != "
         f"natif {sorted(g['nat'])}")
    assert expected_main <= len(g["port"][tid]) <= expected_main + 1, \
        (f"K={len(adj)} : le port applique {len(g['port'][tid])} coups a la cible d'origine, attendu "
         f"nrOfHits({n_hits}) + tuiles adjacentes marchables SANS ennemi ({g['nb_free']} - "
         f"{len(adj)}) = {expected_main} (+1 LetTheGalaxyBurn au plus) -> la base GEOMETRIQUE a bouge")
    for t in adj:
        assert 1 <= len(g["port"][t]) <= 2, \
            (f"volet AoE, cible u{t} : le port applique {len(g['port'][t])} coups, attendu le "
             f"litteral `DSLFactory.Direct(1)` (+1 LetTheGalaxyBurn au plus)")
    for t in g["nat"]:
        assert abs(len(g["nat"][t]) - len(g["port"][t])) <= 1, \
            (f"cible u{t} : natif {len(g['nat'][t])} coups vs port {len(g['port'][t])} -- ecart > 1, "
             f"hors de la tolerance `LetTheGalaxyBurn` (cf. docstring)")


def test_frenzied_firing_aoe_combat_matches_native(live_session, rpc, build_runner):
    """COMBAT. `IdunBattleLogic.Entities.Abilities.Active.Loki.FrenziedFiringAbility$$ExecuteBehaviour`
    (MIRROR du DECOMPILE) :

        hitsNode = GetHitsForOriginalTarget(this)
        A = SetCache(hitsNode) & AttackWithAttackDamage(caster@0x160, target@0x178, hits = hitsNode)
        B = SetCache(hitsNode) & AttackWithAttackDamage(caster@0x160,
                                    AdjacentEnemies(caster@0x160, targetTiles@0x190, 1),
                                    hits = DSLFactory.Direct(1))
        AtomicGroup(0x4e, <ExecuteBehaviour>b__0)   ou b__0 = Execute( op_Addition(A, B) )

    DEUX geometries, UN RUNNER CHACUNE (le cast consomme l'activation) :
      - K=0 -> volet AoE INERTE : le natif ne frappe QUE la cible (non-regression du volet d'origine)
        et, a nombre de coups egal, le port est BIT-EXACT coup par coup ;
      - K>=1 -> volet AoE MORDANT : le natif frappe la cible + chaque ennemi de l'anneau, et les
        coups du volet d'origine TOMBENT d'autant (chaque ennemi de l'anneau retire une tuile du
        `Count` ET ajoute une cible) -- l'anti-correlation des DEUX volets.
    Le nombre de coups attendu est DERIVE a chaque fois de la config (`nrOfHits`) et du board
    (voisins marchables de la cible), jamais code en dur ; la geometrie K est celle REELLEMENT
    obtenue (le placement d'anneau est adaptatif, cf. `_frenzy_combat_geometry`).

    LE CASTER EST DEPLACE, en DERNIER, juste avant le cast (`_step_caster_aside`) : le
    `UnitFlag.Moved` pose par `MoveUnitOperation$$Execute` desarme le +25 % ranged
    d'`HeavyWeapon_ExtraDmg` que Volk porte, et `load_state` le lit du MEME canal que le natif
    (`combatSnapshot.units[].unitFlags` -> `snapshot._load_unit_flags` ->
    `components.unit_has_moved`). Le degat reste donc bit-exact.
    L'ORDRE est contraint par le turn-flow, pas par le port : une unite qui a bouge n'a plus d'action
    pendante, et sur un roster 1 vs 4 tout deplacement ADVERSE qui suit fait basculer `currentPlayer`
    (mesure) -- le cast deviendrait illegal. Le pas est donc pris apres toute la geometrie, contraint
    a rester a distance 2..3 de la cible et hors de l'anneau (sans quoi il changerait le `Count` de
    tuiles libres que lit `FrenziedFiringAbility$$GetHitsForOriginalTarget`).

    ROSTER TEMOIN : aucune cible ne porte de modificateur du canal de coups partage (case-61 §1.2) --
    sans cela, un `astraBullgryn` (aura BigTarget) sur l'anneau retire 1 coup a la cible cote PORT
    alors que le natif n'en retire pas, et le verdict du volet mesure ici serait melange au leur.

    RESIDU ADMIS, borne a +-1 coup par cible : le trait `LetTheGalaxyBurn` de Volk arme, au
    `On(PreAttack=5)` de CHAQUE attaque, un flag `Maybe(chance)` qui vaut +1 coup. Le vecteur est
    desormais emis sur le chemin ability (sans quoi le K=0 n'etait JAMAIS bit-exact), et le tirage est
    consomme des DEUX cotes -- mais le VERDICT du `Maybe` peut differer (residu nomme, cf.
    docs/rl/case-61-ability-hits-channel.md §6). Le test borne donc l'ecart a 1 coup par cible et
    n'exige le bit-exact que lorsque les comptes concordent."""
    from engine.entities.effects.magnitude import ability_var
    n_hits = int(ability_var(FRENZY_NAME, "nrOfHits", is_constant=True) or 1)

    g0 = _frenzy_combat_geometry(rpc, build_runner, "61106", 0)
    print(f"\n[#61 frenzy AoE COMBAT] caster DEPLACE {g0['cpos']} -> {g0['moved_to']} "
          f"(UnitFlag.Moved pose -> gate no-move HeavyWeapon ferme des deux cotes)")
    print(f"[#61 frenzy AoE COMBAT] K=0 cible u{g0['tid']} ({g0['nb_free']} voisins marchables) "
          f"natif={ {t: len(v) for t, v in g0['nat'].items()} } "
          f"port={ {t: len(v) for t, v in g0['port'].items()} } "
          f"(canal #179 natif={ {t: len(v) for t, v in g0['other'].items()} })")
    assert set(g0["nat"]) == {g0["tid"]}, \
        (f"sans voisin ennemi le natif frappe {sorted(g0['nat'])} (attendu la seule cible "
         f"u{g0['tid']}) -> le volet AoE ne serait pas gate par la geometrie")
    _frenzy_assert_geometry(g0, n_hits)
    if len(g0["nat"][g0["tid"]]) == len(g0["port"][g0["tid"]]):   # meme verdict `Maybe` -> rng aligne
        assert g0["port"][g0["tid"]] == g0["nat"][g0["tid"]], \
            (f"K=0 : per-coup port {g0['port'][g0['tid']]} != natif {g0['nat'][g0['tid']]} -- a "
             f"nombre de coups EGAL le flux `state.rng` doit etre aligne coup par coup")

    g3 = _frenzy_combat_geometry(rpc, build_runner, "61107", 3)
    print(f"[#61 frenzy AoE COMBAT] caster DEPLACE {g3['cpos']} -> {g3['moved_to']}")
    print(f"[#61 frenzy AoE COMBAT] K={len(g3['adj'])} adj={g3['adj']} cible u{g3['tid']} "
          f"({g3['nb_free']} voisins marchables) "
          f"natif={ {t: len(v) for t, v in g3['nat'].items()} } "
          f"port={ {t: len(v) for t, v in g3['port'].items()} } "
          f"(canal #179 natif={ {t: len(v) for t, v in g3['other'].items()} })")
    assert len(g3["adj"]) >= 1, "geometrie K>=1 non obtenue -> le volet AoE n'est pas exerce"
    _frenzy_assert_geometry(g3, n_hits)
    # Le scenario DISCRIMINE : le natif lui-meme frappe un nombre DIFFERENT de cibles entre les deux
    # geometries (sinon un port qui n'emettrait que le volet d'origine passerait vert).
    assert len(g3["nat"]) == 1 + len(g3["adj"]) > len(g0["nat"]), \
        (f"le natif frappe {len(g3['nat'])} cibles a K={len(g3['adj'])} et {len(g0['nat'])} a K=0 -> "
         f"le scenario n'oppose pas les deux geometries")
