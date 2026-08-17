"""#232 -- GARDE : les gates de soin/repair de la couche DECISION mirrorent `IsAffectedByHealType`.

CRITERE BINAIRE : les gates de `engine/playbook/noncomparable/heals.py` rendent-ils le MEME verdict
que `IdunBattle.Entities.UnitExtensions$$IsAffectedByHealType(u, healType)` natif ?

    if (GetBaseUnitComponent(u) != null && HasTrait(u, 0x421 AffectedByHealAndRepair)) return true;
    if (healType == 0 &&  IsMechanical(u)) return false;      // Heal   : pas les mecaniques
    if (healType == 1 && !IsMechanical(u)) return false;      // Repair : QUE les mecaniques
    return true;                                              // healType 2 : aucun filtre

    IdunBattle.Entities.UnitExtensions$$IsMechanical =
        HasTrait(Mechanical=5) OU HasTrait(LivingMetal=0x3e8) OU HasTrait(Vehicle=0x405)

Avant #232 le module testait `"Mechanical" not in gameconfig.traits` : ni le disjunct 0x421, ni
`LivingMetal`, ni `Vehicle`, et sur un substrat STATIQUE par visualId (aveugle a `AddTrait`).

Trois etages :
  etage 0 -- TABLE DE VERITE (offline) : les 4x2x3 combinaisons de traits x healType confrontees
             au decompile, y compris les cas que l'ancien critere ratait.
  etage 1 -- NEUTRALITE (live) : sur une bataille reelle, le nouveau gate rend EXACTEMENT le meme
             verdict que l'ancien critere pour toutes les unites. Le gameconfig courant n'a
             AUCUNE unite `LivingMetal`/`Vehicle` sans `Mechanical` et 0/669 portent 0x421
             (`probe_232_heal_type_gate.py`) -> le fix ne doit RIEN deplacer sans octroi.
  etage 2 -- DISCRIMINATION (live + octroi) : un allie MECANIQUE qui recoit `AffectedByHealAndRepair`
             EN BATAILLE entre dans le compte d'utilite de `RitesOfRestorationPlaybook`. Le chemin
             d'ecriture est le leaf DSL deja porte `AddTrait` (mirror de
             `IdunBattleLogic.Entities.DSLBehaviors$$AddTrait` -> `AddTraitOperation`, collection
             `BaseUnitComponent+0x40`), exactement le levier de #225.

PORTABILITE DE L'ETAGE 2 : la voie NATIVE d'octroi de 0x421 est la relique
`items/R_Defensive_SupaCyborkBody` (`SupaCyborkBodyAbility_AddTrait$$CreateBehaviour`), dont les 9
porteurs gameconfig sont TOUS `kind=npc` et qu'aucun canal de `rl_duel build` ne sait equiper.
L'octroi est donc fait ici par le MIRROR PORTE du leaf, pas par le natif : c'est une garde de
COHERENCE decision/combat sur le meme etat, pas une confrontation d'un octroi natif.

ASCII only. Dispose SES runners (fabrique `build_runner`).
"""
from __future__ import annotations

import pytest

import gameconfig as GC
import hexgeo
from engine.ai.state_bridge import build_from_state
from engine.dsl.effects import ExecutionContext
from engine.entities.pathfinding.board import Board
from engine.entities.selectors.accessors import Target
from engine.entities.traits.unit_trait import UnitTrait, unit_trait_names
from engine.playbook.noncomparable._base import NCContext
from engine.playbook.noncomparable._base import _traits
from engine.playbook.noncomparable.heals import (RitesOfRestorationPlaybook,
                                                 _affected_by_heal_type)
from engine.runner.abilities.behaviours.context import entities_from_state
from engine.runner.abilities.behaviours.grants import AddTrait
from engine.runner.components import (HealthComponent, PositionComponent, StatsComponent,
                                      UnitComponent)
from engine.runner.snapshot import load_state

AFFECTED = UnitTrait.AffectedByHealAndRepair          # 0x421 = 1057
MECH_TRAITS = ("Mechanical", "LivingMetal", "Vehicle")
P_UNITS = "adeptHospitaller,admecManipulus,adeptRetributor"   # 3 Imperial (Rites filtre 0x1a)


# --------------------------------------------------------------------------- etage 0 : offline

class _FakeCtx:
    """`UnitContext` minimal : seul `.traits` est lu par `entity_trait_names`."""

    def __init__(self, traits):
        self.traits = list(traits)
        self.visual_id = None


class _FakeScene:
    def __init__(self, by_id):
        self._d = by_id

    def ctx(self, uid):
        return self._d.get(uid)


def _ctx_with(traits) -> NCContext:
    c = NCContext(uid=1, origin=None, reach_nc=[], epos=[], fpos=[], plan={}, hp_cur_by_id={})
    c.scene = _FakeScene({1: _FakeCtx(traits)})
    return c


def _native(traits, heal_type: int) -> bool:
    """Re-derivation INDEPENDANTE de la table du decompile (elle ne passe par AUCUN code du port)."""
    if "AffectedByHealAndRepair" in traits:
        return True
    mech = any(t in traits for t in MECH_TRAITS)
    if heal_type == 0 and mech:
        return False
    if heal_type == 1 and not mech:
        return False
    return True


@pytest.mark.parametrize("traits", [
    (),                                   # ni mecanique ni 0x421
    ("Mechanical",),                      # le SEUL cas que l'ancien critere voyait
    ("LivingMetal",),                     # rate par l'ancien critere (necrons)
    ("Vehicle",),                         # rate par l'ancien critere
    ("Mechanical", "LivingMetal"),
    ("AffectedByHealAndRepair",),         # disjunct absent de l'ancien port
    ("Mechanical", "AffectedByHealAndRepair"),
    ("LivingMetal", "AffectedByHealAndRepair"),
])
@pytest.mark.parametrize("heal_type", [0, 1, 2])
def test_gate_matches_native_truth_table(traits, heal_type):
    """Chaque combinaison (traits x healType) rend le verdict du decompile."""
    got = _affected_by_heal_type(_ctx_with(traits), {"squadId": 1, "visualId": None}, heal_type)
    want = _native(traits, heal_type)
    assert got == want, ("traits=%s healType=%d : port=%s natif=%s"
                         % (sorted(traits), heal_type, got, want))


def test_old_criterion_was_wrong_on_at_least_one_case():
    """Verrou anti-tautologie : l'ancien critere (`Mechanical` seul, sans 0x421) DIVERGE du natif
    sur au moins un cas de la table -- sinon ce fichier ne garderait rien."""
    diverge = []
    for traits in (("LivingMetal",), ("Vehicle",), ("AffectedByHealAndRepair",),
                   ("Mechanical", "AffectedByHealAndRepair")):
        for ht in (0, 1):
            old = ("Mechanical" not in traits) if ht == 0 else ("Mechanical" in traits)
            if old != _native(traits, ht):
                diverge.append((sorted(traits), ht, old, _native(traits, ht)))
    print("[#232 table] divergences ancien critere vs natif : %s" % (diverge,))
    assert len(diverge) >= 4, "l'ancien critere ne divergeait nulle part -- montage non discriminant"


def test_gameconfig_has_no_static_divergence():
    """MESURE du gisement STATIQUE : aucune unite du gameconfig n'est `LivingMetal`/`Vehicle` sans
    `Mechanical`, et 0/669 portent 0x421. C'est ce qui rend l'etage 1 (neutralite) attendu -- et ce
    qui dit que le fix ne mord QUE sur un octroi en bataille."""
    ids = sorted(sum((GC.all_unit_ids() or {}).values(), []))
    assert ids, "gameconfig vide"
    bad = [u for u in ids
           if any(t in unit_trait_names(u) for t in MECH_TRAITS[1:])
           and "Mechanical" not in unit_trait_names(u)]
    with421 = [u for u in ids if AFFECTED.name in unit_trait_names(u)]
    print("[#232 gisement] %d unites | LivingMetal/Vehicle sans Mechanical = %d | 0x421 = %d"
          % (len(ids), len(bad), len(with421)))
    assert not bad, ("des unites sont mecaniques SANS le trait `Mechanical` (%s) : l'etage 1 ne peut "
                     "plus etre une neutralite, il faut re-qualifier la mesure" % bad[:10])
    assert not with421, "des unites portent 0x421 au gameconfig (%s) -- re-qualifier" % with421[:10]
    # Le NOUVEAU chemin lit `GC.unit(vis)` en direct (`unit_trait_names`), l'ANCIEN passait par
    # `resolve_unit_id` (`_traits`). Sur TOUT le corpus les deux doivent rendre le meme verdict
    # `Mechanical`, sans quoi le fix regresserait sur la RESOLUTION du visualId, pas sur le gate.
    resolv = [u for u in ids
              if ("Mechanical" in unit_trait_names(u)) != ("Mechanical" in (_traits(u) or ()))]
    assert not resolv, ("resolution divergente entre `unit_trait_names` et `_traits` sur %s"
                        % resolv[:10])


# --------------------------------------------------------------------------- harnais live

@pytest.fixture(scope="module")
def rites_state(rpc, build_runner):
    """Bataille LIVE 3v3 Imperial, chargee en `State`. Aucune valeur en dur."""
    rid = build_runner("777", board="MC1_67", extra=["--p-units", P_UNITS])["rid"]
    bg = rpc("boardGraph", {"runnerId": rid}, 60)
    if not (isinstance(bg, dict) and bg.get("tiles")):
        pytest.skip("boardGraph indispo")
    board = Board(bg["tiles"], adjacency="native_sym")
    walkable = {(t["col"], t["row"]) for t in bg["tiles"] if t.get("walkable")}
    dv = rpc("decisionView", {"runnerId": rid, "maxRank": 1, "allAbilities": True}, 180)
    ob = rpc("observeBattle", {"runnerId": rid}, 40)
    cs = rpc("combatSnapshot", {"runnerId": rid}, 60)
    state = load_state(dv, ob, cs, board=board)
    return state, walkable


def _by_visual(state, vis):
    for eid, e in state.entities.items():
        uc = e.get_component(UnitComponent)
        if uc is not None and uc.visual_id == vis:
            return eid
    return None


def _nc_ctx(state, uid) -> NCContext:
    """`State` -> NCContext, par le MEME mapping que `NonComparableGenerator.generate`."""
    d = build_from_state(state, uid)
    return NCContext(
        uid=d.uid, origin=d.origin, reach_nc=d.reach_nc, epos=d.epos, fpos=d.fpos,
        enemies=d.enemies, neigh_by_pos=d.neigh_by_pos, walkable_by_pos=d.walkable_by_pos,
        plan=d.plans.get(d.uid) or {}, plans=d.plans, hp_cur_by_id=d.hp_cur_by_id,
        elev_by_pos=d.elev_by_pos, ability_targets=d.ability_targets, wt=d.wt,
        is_temporary_by_pos=d.is_temporary_by_pos, effects_by_pos=d.effects_by_pos,
        obs_units=d.obs_units, tile_id_by_pos=d.tile_id_by_pos,
        active_levels=d.active_ability_levels, ability_config=d.heal_config,
        units=d.units, cast_from_tiles=d.cast_from_tiles, scene=d.scene)


# --------------------------------------------------------------------------- etage 1 : neutralite

def test_gate_is_neutral_on_a_real_battle(rites_state):
    """Sur une bataille LIVE et SANS octroi, le nouveau gate rend le verdict de l'ancien critere
    pour TOUTES les unites, aux DEUX healTypes. C'est la preuve que le fix ne deplace rien du
    comportement deja valide (Rites/CombatRestoratives/DefendTheDivineWork/RevitalizingMalignancy)."""
    state, _ = rites_state
    ctx = _nc_ctx(state, next(iter(
        eid for eid, e in state.entities.items()
        if e.get_component(UnitComponent) is not None
        and e.get_component(StatsComponent) is not None)))
    checked = 0
    for u in (ctx.obs_units or []):
        vis = u.get("visualId")
        # CABLAGE : `_affected_by_heal_type` lit `ctx.scene.ctx(obs["squadId"])`. Si cette cle ne
        # resolvait pas, le gate retomberait SILENCIEUSEMENT sur la borne statique et l'etage 2 ne
        # prouverait rien -- on l'exige donc explicitement plutot que de le supposer.
        assert ctx.scene.ctx(u.get("squadId")) is not None, (
            "scene.ctx(squadId=%s) est None pour %s : le substrat d'ENTITE n'est pas cable"
            % (u.get("squadId"), vis))
        # ANCIEN critere VERBATIM : `_traits` (= `_unit_cfg` -> `resolve_unit_id` + `GC.unit`), PAS
        # `unit_trait_names` -- sinon les deux cotes partageraient l'accesseur et la garde serait
        # aveugle a une regression de RESOLUTION du visualId (le nouveau chemin appelle `GC.unit`
        # en direct, sans `resolve_unit_id`).
        old_mech = "Mechanical" in (_traits(vis) or ())
        assert _affected_by_heal_type(ctx, u, 0) == (not old_mech), (
            "heal(0) diverge de l'ancien critere sur %s (traits %s)" % (vis, sorted(_traits(vis))))
        assert _affected_by_heal_type(ctx, u, 1) == old_mech, (
            "repair(1) diverge de l'ancien critere sur %s" % vis)
        checked += 1
    print("[#232 neutralite] %d unites : verdicts identiques a l'ancien critere" % checked)
    assert checked >= 2, "moins de 2 unites confrontees (%d)" % checked


# --------------------------------------------------------------------------- etage 2 : discrimination

def test_in_battle_granted_trait_enters_the_rites_heal_count(rites_state):
    """MESURE DISCRIMINANTE. `RitesOfRestorationPlaybook` score `util = 1 + Count(GetHealTargets)`
    avec `GetHealTargets = Healable(self + AdjacentFriends(self,1))`. Un allie MECANIQUE adjacent
    (`admecManipulus`) est HORS du compte ; apres l'octroi de `AffectedByHealAndRepair` EN BATAILLE
    le natif l'y remet (1er disjunct d'`IsAffectedByHealType`), et le port doit suivre.

    Montage crafte (les unites sont DEPLACEES, on ne subit pas la geometrie de spawn) :
      - `adeptRetributor` est MIS A MORT -> `ShouldEvaluate` (Count(GetPossibleResurrectTargets) > 0) ;
      - `admecManipulus` est POSE sur une tuile adjacente au caster -> il est dans `AdjacentFriends`.
    """
    state, walkable = rites_state
    hosp = _by_visual(state, "adeptHospitaller")
    mani = _by_visual(state, "admecManipulus")
    dead = _by_visual(state, "adeptRetributor")
    assert hosp and mani and dead, ("montage incomplet : hosp=%s mani=%s dead=%s"
                                    % (hosp, mani, dead))
    assert "Mechanical" in unit_trait_names("admecManipulus"), "admecManipulus n'est plus mecanique"
    assert AFFECTED.name not in unit_trait_names("admecManipulus"), (
        "admecManipulus porte DEJA 0x421 au gameconfig : cas statique et dynamique indiscernables")

    # -- la mort qui ouvre ShouldEvaluate (obs_units.isDead <- UnitComponent.alive)
    duc = state.get_entity(dead).get_component(UnitComponent)
    duc.alive = False
    dhc = state.get_entity(dead).get_component(HealthComponent)
    if dhc is not None:
        dhc.hp = 0

    # -- on POSE le mecanique a cote du caster (tuile libre du voisinage, board reel)
    hpc = state.get_entity(hosp).get_component(PositionComponent)
    mpc = state.get_entity(mani).get_component(PositionComponent)
    origin = (hpc.col, hpc.row)
    mani_ent = state.get_entity(mani)
    free = [n for n in hexgeo.neighbors(*origin)
            if n in walkable and state.unit_at(n) in (None, mani_ent)]   # unit_at rend l'ENTITE
    assert free, "aucune tuile libre adjacente au caster -- montage impossible sur ce board"
    mpc.col, mpc.row = free[0]

    ctx = _nc_ctx(state, hosp)
    pb = RitesOfRestorationPlaybook()
    before = pb.generate_candidates(ctx)
    assert before, ("aucun candidat AVANT l'octroi : ShouldEvaluate ou le gate de resurrection n'est "
                    "pas satisfait -- le montage ne mesure rien")
    u_before = before[0]["pred"]

    ectx = ExecutionContext(state=state, rng=None)
    AddTrait(Target(), AFFECTED).execute(entities_from_state(state, mani, mani), ectx)
    assert [p for n, p in ectx.emitted if n == "AddTrait"], "le leaf AddTrait n'a rien emis"

    ctx2 = _nc_ctx(state, hosp)
    mani_obs = next(u for u in ctx2.obs_units if u.get("squadId") == mani)
    assert _affected_by_heal_type(ctx2, mani_obs, 0), (
        "le trait 0x421 accorde EN BATAILLE n'atteint pas le gate de decision -- il lit encore un "
        "substrat STATIQUE")
    after = pb.generate_candidates(ctx2)
    assert after, "plus aucun candidat APRES l'octroi (regression)"
    u_after = after[0]["pred"]
    print("[#232 discrimination] Rites util %s -> %s (admecManipulus entre dans GetHealTargets)"
          % (u_before, u_after))
    assert u_after == u_before + 1.0, (
        "l'utilite n'a pas augmente de 1 (Count(GetHealTargets) +1) : %s -> %s" % (u_before, u_after))
