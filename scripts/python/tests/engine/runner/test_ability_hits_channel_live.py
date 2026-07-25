"""#61 -- CANAL DE COUPS des attaques d'ABILITY : le COMBAT le traverse, la PREDICTION non.

Chaine NATIVE (decompile ghidra, build gqfc5mff6c) :
  - `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage` -> `AttackDamageBehaviour` (le noeud
    `hits` de l'ability est stocke en champ +0x80 ; `IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$ExecuteTarget`
    l'EVALUE et le range dans le `Nullable<int>` de l'AttackData) -> `IdunBattle.Operations.AttackDamageOperation$$Execute`
    -> `IdunBattle.Operations.AttackDamageOperation$$GetAttackHits` (slot d'interface 0xb5) ->
    `IdunBattle.Core.Services.DamagePrediction$$GetAttackHits` = `base + ExtraHits(0x11) +
    (IsMeleeAttack ? ExtraHitsMelee(0x17))`, `Math.Max(.,0)`, puis la boucle des effets (bonus
    `OwnerIsCaster` / malus `OwnerIsTarget` / clamps min). => MEME formule que l'attaque NORMALE, seule
    la BASE change (noeud `hits` de l'ability au lieu du nb de coups de l'arme).
  - `IdunBattle.Operations.AbilityDamageOperation$$Execute` (famille `IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage`)
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

Drive les positions (`applyAction move` ignore portee et propriete). Lit l'etat LIVE ; aucune tuile/RVA
hardcodee. ASCII only. Runners auto-disposes par la fixture `build_runner`.
"""
from __future__ import annotations

import json

import pytest

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
    assert len(live_par) == base_cfg - 1, \
        (f"natif {len(live_par)} != base-1 ({base_cfg - 1}) sur une cible Parry : le canal de coups "
         f"ne serait PAS traverse par le vecteur ability (premisse du cas #61 fausse)")
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
