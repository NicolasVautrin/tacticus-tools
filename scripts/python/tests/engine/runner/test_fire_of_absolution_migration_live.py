"""#149 slice-14 : FireOfAbsolution (passif adeptRetributor «Vindicta») MIGRATION vers l'arbre DSL
`fire_of_absolution_tree()` (mirror 1:1 de `IdunBattleLogic.Entities.Abilities.Active.Loki.FireOfAbsolutionAbility$$CreateBehaviour`, RE decompile).

Arbre natif (`&` = op_BitwiseAnd, gauche->droite) :
    Inform(0xb3, EntityId(target))
  & AttackWithAttackDamage(caster, AdjacentUnits(target,0,3) − caster − target, Direct(dmg=var0xb), Flame, hits=3)
  & Maybe(SetOnFire, AdjacentTiles(target), chance=30)
Le passif fire sur toute attaque RANGED de Vindicta. On confronte le NOUVEAU `_fire_of_absolution_after_attack`
(qui DELEGUE a l'arbre : Inform no-op + splash `AttackWithAbilityDamage(multi)` + `Foreach(AdjacentTiles,
Maybe(30, SetOnFire))`) a une COPIE de reference de l'ANCIEN corps hybride imperatif (selecteur DSL + boucle
`execute_ability_attack` + boucle ignite `next_bool`/`AddEffect`). REPLAY-DIFF sur DEUX etats INDEPENDANTS
issus de la MEME capture LIVE, seedes IDENTIQUEMENT -> meme splash (set + per-coup) + memes tuiles ignitees =
BIT-EXACT (meme Operations, meme ordre splash->ignite, meme `state.rng`).

Caster = adeptRetributor «Vindicta» (BUILDABLE, porte le passif FireOfAbsolution). Cible ENNEMIE choisie via
le SELECTEUR DE SPLASH lui-meme (>=1 occupant non-ami adjacent) -> splash NON VIDE = chemin exerce. Lit l'etat
LIVE. ASCII-only. NON committe (tests confront live, hors depot).
"""
from __future__ import annotations

import pytest

from engine.runner.snapshot import load_state
from engine.runner.prng import IntBasedMersenneTwister
from engine.runner.components import StatsComponent, OwnerComponent, UnitComponent, PositionComponent
from engine.runner.operations.damage import AttackDamageOperation
from engine.runner.operations.effects import AddEffectOperation
from engine.runner.operations.triggers.loki import _fire_of_absolution_after_attack
# #951 : la chance d ignition est LUE du gameconfig (GetNumberConstant(chance)), elle
# n est plus une constante figee -- le temoin imperatif ci-dessous lit donc la MEME source.
from engine.runner.operations.triggers.loki import FIRE_TILE, fire_of_absolution_ignite_chance
from engine.runner.abilities.base import ability_attack_params
from engine.runner.abilities.behaviours.context import entities_from_state
from engine.entities.selectors.accessors import Target, TargetTile
from engine.entities.selectors.tiles import Caster
from engine.entities.selectors.units import AdjacentUnits, Alive, Sub
from engine.entities.pathfinding.board import Board

CASTER_VIS = "adeptRetributor"              # «Vindicta» : porte FireOfAbsolution (passif)
BUILD = ["--roster", "1", "--p-units", CASTER_VIS,
         "--a-units", "necroWarden,necroDestroyer,necroSpyder,necroOverlord"]   # ennemis clusterises -> splash


def _ok(r):
    return isinstance(r, dict) and r.get("ok")


def _seed_rng(s):
    rng = IntBasedMersenneTwister()
    rng.mt = list(s["mt"]); rng.mti = s["mti"]
    return rng


def _team(state, eid):
    e = state.get_entity(eid)
    oc = e.get_component(OwnerComponent) if e is not None else None
    return oc.team if oc is not None else None


def _alive(state, eid):
    e = state.get_entity(eid)
    uc = e.get_component(UnitComponent) if e is not None else None
    return uc.alive if uc is not None else True


def _visual(state, eid):
    e = state.get_entity(eid)
    uc = e.get_component(UnitComponent) if e is not None else None
    return uc.visual_id if uc is not None else None


def _splash_selector():
    """Selecteur de splash EXACT (mirror natif `AdjacentUnits(target) − caster − target`, position-domain,
    board-independant) — sert AUSSI a PICKER une cible avec splash non vide."""
    return Alive(Sub(Sub(AdjacentUnits(TargetTile()), Caster()), Target()))


def _splash_map(passive):
    """{splash_target -> per_hit} depuis la liste retournee par _fire_of_absolution_after_attack."""
    out = {}
    for p in (passive or []):
        for s in (p.get("splash") or []):
            out[s["target"]] = (s.get("attack") or {}).get("per_hit")
    return out


def _ignited(passive):
    out = set()
    for p in (passive or []):
        out |= set(p.get("ignited_tiles") or [])
    return out


def _fire_of_absolution_imperative_ref(state, attacker_id, target_id, ranged):
    """Copie VERBATIM de l'ANCIEN corps hybride de `_fire_of_absolution_after_attack` (AVANT slice-14) :
    splash via le SELECTEUR DSL + boucle `execute_ability_attack` + boucle ignite `next_bool`/`AddEffect`.
    ORACLE du replay-diff (independant du code migre : ne passe PAS par l'arbre)."""
    if not ranged or state.board is None or state.effects is None or state.rng is None:
        return []
    import gameconfig as GC
    e = state.get_entity(attacker_id)
    uc = e.get_component(UnitComponent) if e is not None else None
    if uc is None or "FireOfAbsolution" not in ((GC.unit(uc.visual_id) or {}).get("passiveAbilities") or []):
        return []
    dmg, _dmg_max, pierce, hits = ability_attack_params(
        state, attacker_id, "FireOfAbsolution", "Flame", ranged=True, min_key="dmg", max_key="dmg")
    _ents = entities_from_state(state, attacker_id, target_id)
    _splash_ids = sorted(u.get("id") for u in _splash_selector().evaluate(_ents) if u.get("id") is not None)
    splash = []
    for sid in _splash_ids:
        satk = AttackDamageOperation.execute_ability_attack(
            state, attacker_id, sid, dmg, dmg, pierce, hits, damage_profile="Flame", is_melee=False)
        splash.append({"target": sid, "attack": satk})
    tp = state.get_entity(target_id)
    tpc = tp.get_component(PositionComponent) if tp is not None else None
    ttile = state.board.id_at(tpc.col, tpc.row) if tpc is not None else None
    ignited = []
    if ttile is not None:
        for ntile in state.board.neighbours(ttile):
            if state.rng.next_bool(fire_of_absolution_ignite_chance()):
                if AddEffectOperation.execute(state, source=attacker_id, target=ntile,
                                              effect_type=FIRE_TILE, name="Fire") is not None:
                    ignited.append(ntile)
    if not splash and not ignited:
        return []
    return [{"passive": "FireOfAbsolution", "by": attacker_id, "on": target_id,
             "splash": splash, "ignited_tiles": ignited}]


def _pick_target_with_splash(state, caster_id):
    """Cible ENNEMIE dont le SELECTEUR DE SPLASH natif rend >=1 unite (splash non vide = chemin exerce)."""
    cteam = _team(state, caster_id)
    sel = _splash_selector()
    for tid in state.entities:
        if _team(state, tid) == cteam or not _alive(state, tid):
            continue
        ents = entities_from_state(state, caster_id, tid)
        if any(u.get("id") is not None for u in sel.evaluate(ents)):
            return tid
    return None


def test_fire_of_absolution_migration_matches_imperative(live_session, rpc, build_runner):
    """Le nouveau `_fire_of_absolution_after_attack` (arbre DSL `fire_of_absolution_tree`) reproduit l'ANCIEN
    corps hybride imperatif BIT-EXACT : meme set + per-coup de splash, memes tuiles ignitees, sous le MEME
    `state.rng` seede, sur DEUX etats INDEPENDANTS issus de la MEME capture LIVE."""
    rid = build_runner("777", extra=BUILD)["rid"]
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not _ok(dv):
        pytest.skip("decisionView KO")
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not _ok(s0):
        pytest.skip("dumpRng KO")
    # native_sym = adjacence unite-unite CORRECTE (mirror natif). Les DEUX faces (arbre + ref) PARTAGENT ce
    # board -> la branche ignite (board.neighbours) est identique quel que soit le mode (replay-diff board-agnostique).
    board = Board(bg["tiles"], adjacency="native_sym")

    st0 = load_state(dv, ob, snap, board=board)
    if st0.effects is None:
        pytest.skip("EffectsState non charge (combatSnapshot absent) -> gate FireOfAbsolution KO")
    caster_id = next((eid for eid in st0.entities
                      if _visual(st0, eid) == CASTER_VIS and _alive(st0, eid)
                      and st0.get_entity(eid).get_component(StatsComponent) is not None), None)
    if caster_id is None:
        pytest.skip("caster adeptRetributor (StatsComponent) introuvable offline")
    target_id = _pick_target_with_splash(st0, caster_id)
    if target_id is None:
        pytest.skip("aucune cible ennemie avec occupant adjacent (splash FireOfAbsolution non exercable)")

    # DEUX etats INDEPENDANTS depuis la MEME capture, MEME board, seedes IDENTIQUEMENT -> arbre vs ref.
    st_new = load_state(dv, ob, snap, board=board); st_new.rng = _seed_rng(s0)
    st_ref = load_state(dv, ob, snap, board=board); st_ref.rng = _seed_rng(s0)

    res_new = _fire_of_absolution_after_attack(st_new, caster_id, target_id, ranged=True)   # arbre DSL migre
    res_ref = _fire_of_absolution_imperative_ref(st_ref, caster_id, target_id, ranged=True)  # ancien imperatif

    new_splash, ref_splash = _splash_map(res_new), _splash_map(res_ref)
    new_ign, ref_ign = _ignited(res_new), _ignited(res_ref)

    print(f"\n[FIREOFABS migration] caster={caster_id} target={target_id}")
    print(f"[FIREOFABS migration] splash new={ {k: new_splash[k] for k in sorted(new_splash)} } "
          f"ref={ {k: ref_splash[k] for k in sorted(ref_splash)} }")
    print(f"[FIREOFABS migration] ignited new={sorted(new_ign)} ref={sorted(ref_ign)}")

    # 0) le passif a REELLEMENT fire (splash non vide) -> arbre exerce
    assert ref_splash, "splash FireOfAbsolution vide cote reference -> chemin non exerce (setup)"
    # 1) MEME set + per-coup de splash (feuille AttackWithAbilityDamage multi == boucle execute_ability_attack)
    assert new_splash == ref_splash, f"splash arbre {new_splash} != imperatif {ref_splash}"
    # 2) MEMES tuiles ignitees (Foreach(AdjacentTiles, Maybe(30, SetOnFire)) == boucle ignite next_bool)
    assert new_ign == ref_ign, f"ignited arbre {sorted(new_ign)} != imperatif {sorted(ref_ign)}"


def test_521r8_le_CABLAGE_joue_le_passif_UNE_fois_par_attaque_normale(live_session, rpc,
                                                                     build_runner, monkeypatch):
    """#521-r8 -- CE QUE LE TEST CI-DESSUS NE TOUCHE PAS : le CABLAGE.

    Le test de migration appelle `_fire_of_absolution_after_attack` DIRECTEMENT ; il resterait donc
    VERT si le passif n'etait plus branche a rien. C'est exactement le mode de panne de cette
    tranche : le passif a change de SITE (`after_hit_normal_attack` -> le vecteur `On(0x4a)`), et
    les deux moities doivent bouger ensemble sous peine de ZERO splash ou de DOUBLE splash.

    Ce test-ci joue une attaque normale par la VOIE MESSAGE (`DamageHandler.visit_AttackUnitMessage`,
    le chemin de production) et compte les invocations, sur un etat LIVE. Trois crans :
      * le passif part EXACTEMENT UNE fois (ni zero, ni deux) ;
      * il part AVANT `On(0x26 = NormalAttack)` -- le rang natif, `EvaluateAbilities(0x4a)` etant
        compose par `...ALoki_NormalAttackAbility$$ExecuteNormalAttack` et `On(0x26)` emis plus tard
        par `$$ExecuteTriggerAbilities` ;
      * la cible qu'il recoit est celle de l'attaque RESOLUE, pas celle du message."""
    from engine.runner.operations import damage as DM
    from engine.runner.operations.triggers.dispatch import ability as AB
    from engine.runner.operations.triggers.dispatch import attack as ATT
    from engine.runner.messages import AttackUnitMessage

    rid = build_runner("777", extra=BUILD)["rid"]
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 90)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    snap = rpc("combatSnapshot", {"runnerId": rid}, 40)
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    s0 = rpc("dumpRng", {"runnerId": rid}, 30)
    if not (_ok(dv) and _ok(s0) and isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("capture LIVE incomplete (decisionView / dumpRng / boardGraph)")
    board = Board(bg["tiles"], adjacency="native_sym")
    st = load_state(dv, ob, snap, board=board)
    if st.effects is None:
        pytest.skip("EffectsState non charge -> gate FireOfAbsolution KO")
    st.rng = _seed_rng(s0)
    caster_id = next((eid for eid in st.entities
                      if _visual(st, eid) == CASTER_VIS and _alive(st, eid)
                      and st.get_entity(eid).get_component(StatsComponent) is not None), None)
    if caster_id is None:
        pytest.skip("caster adeptRetributor introuvable offline")
    target_id = _pick_target_with_splash(st, caster_id)
    if target_id is None:
        pytest.skip("aucune cible ennemie avec occupant adjacent")

    # DEPLACER pour forcer le regime : le passif est gate `IsRangedAttack`, donc il FAUT que le
    # caster ne soit PAS adjacent a sa cible -- on ne se contente pas de la geometrie de spawn.
    cp = st.get_entity(caster_id).get_component(PositionComponent)
    tp = st.get_entity(target_id).get_component(PositionComponent)
    occupees = {(p.col, p.row) for p in
                (st.get_entity(e).get_component(PositionComponent) for e in st.entities)
                if p is not None}
    t_tile = board.id_at(tp.col, tp.row)
    ring1 = set(board.neighbours(t_tile))
    # ring 2 EXACTEMENT : non adjacent (le gate `IsRangedAttack` mord) mais assez pres pour que
    # `ALoki_NormalAttackAbility$$FindAttackWeapon` trouve encore l'arme a DISTANCE. Une tuile
    # « n'importe ou » rendrait `weapon == null` -> aucune attaque, donc un temoin VIDE.
    ring2 = {n for t in ring1 for n in board.neighbours(t)} - ring1 - {t_tile}
    loin = next((tid for tid in sorted(ring2) if board.coord(tid) not in occupees), None)
    if loin is None:
        pytest.skip("aucune tuile libre au ring 2 de la cible sur ce board")
    cp.col, cp.row = board.coord(loin)
    assert board.id_at(cp.col, cp.row) not in set(board.neighbours(t_tile)), (
        "le caster est encore adjacent : le gate `IsRangedAttack` refuserait, regime NON exerce")

    appels: list = []
    ordre: list = []
    vrai = AB._fire_of_absolution_after_attack

    def _compteur(state, a, t, ranged, *rest, **kw):
        appels.append((int(a), int(t), bool(ranged)))
        ordre.append("FIREOFABS")
        return vrai(state, a, t, ranged, *rest, **kw)

    monkeypatch.setattr(AB, "_fire_of_absolution_after_attack", _compteur)
    vrai_eval = ATT.evaluate_trigger_operation

    def _trace_ev(state, ev):
        ordre.append(int(ev.event_id))
        return vrai_eval(state, ev)

    monkeypatch.setattr(ATT, "evaluate_trigger_operation", _trace_ev)

    handler = DM.DamageHandler(st)
    handler.visit_AttackUnitMessage(AttackUnitMessage(caster_id, target_id))

    from engine.dsl.event_trigger_type import EventTriggerType
    # L'ETAT MT FINAL : c'est LUI qui dit si la migration a deplace des TIRAGES, et non seulement
    # des appels. La fiche du residu l'annoncait comme le cout a mesurer.
    print(f"\n[521-r8 cablage] mti final = {st.rng.mti}")
    print(f"[521-r8 cablage] attaque resolue = {handler.last}")
    print(f"[521-r8 cablage] appels={appels}")
    print(f"[521-r8 cablage] events emis (dispatch/attack) = {ordre}")
    assert handler.last is not None, (
        "l'attaque normale n'a PAS eu lieu (arme introuvable a cette distance, ou gate amont) -- "
        "temoin VIDE : rien n'est prouve sur le cablage")
    assert handler.last.get("ranged") is True, (
        f"l'attaque resolue est en MELEE ({handler.last.get('ranged')}) : le gate `IsRangedAttack` "
        f"du passif refuserait, le regime n'est pas celui qu'on veut exercer")
    assert len(appels) == 1, (
        f"`FireOfAbsolution` part {len(appels)} fois par attaque normale au lieu d'UNE -- "
        f"zero = les deux moities de la migration n'ont pas bouge ensemble ; deux = l'appel "
        f"imperatif d'`after_hit_normal_attack` est revenu. appels={appels}")
    assert appels[0][2] is True, "le passif recoit `ranged=False` : son gate `IsRangedAttack` refuserait"
    na = int(EventTriggerType.NormalAttack)
    assert na in ordre, (
        "aucun `On(0x26 = NormalAttack)` emis par cette attaque -- le repere d'ordre n'existe pas, "
        "l'assertion de RANG ci-dessous ne prouverait rien")
    assert ordre.index("FIREOFABS") < ordre.index(na), (
        f"RANG FAUX : le passif part APRES `On(0x26)`, c'est-a-dire au rang qu'il avait AVANT la "
        f"migration. Le natif compose `EvaluateAbilities(0x4a)` dans `ExecuteNormalAttack`, donc "
        f"avant `ExecuteTriggerAbilities`. ordre={ordre}")
