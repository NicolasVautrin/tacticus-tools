"""#494-r2 -- CLIQUET : la NATURE du coup d'une attaque normale predite vient du SLOT 2
d'`IBattleQuery`, jamais de l'arme choisie.

Ce que ce fichier garde, et qu'aucune mesure de degat ne garde : le port decidait `isMelee` par
l'ARME (`services/battle_query.select_weapon_pierce` -> `not is_ranged`) la ou
`IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` interroge
`IdunBattle.Core.Services.DamagePrediction$$IsMeleeAttack`, qui delegue au slot 2
= `IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack` :

    if (!ability.HasValue) return false;
    switch (GetAbilityAttackRangeType(ability)) {   // 0 None, 1 Melee, 2 Ranged, 3 Normal
      case 0: return false;   case 1: return true;   case 2: return false;
      case 3: return !UnitExtensions.HasFlag(caster, 0x15)     // UnitFlag.ForceRangedAttack
                     && AreEntitiesAdjacent(casterPosition, target);
    }

et dont la valeur commande, dans le meme corps natif,
`extraMax = isMelee ? 0 : GetStat(attacker, 0x19 = StatType.ExtraMaxDamage)`.

LES TROIS REGIMES, et pourquoi UN SEUL bouge (etage 1) :

  | regime                                  | natif (slot 2) | ancien port (arme) |
  | ADJACENT                                | melee          | melee              |  d'accord
  | NON adjacent, arme ranged EN PORTEE     | ranged         | ranged             |  d'accord
  | NON adjacent, AUCUNE arme eligible      | **ranged**     | **melee**          |  ECART

Le troisieme n'est pas un cas de bord : `get_attack_weapon_for_default_normal_attack` rend
`(None, False)` sur un ensemble vide, donc l'ancien port rendait `True` pour TOUTE unite
melee-only evaluee contre une cible non adjacente. Mesure gameconfig
(`probe_494r2_attack_range_type_normal.py`) : **271** melee-only, **331** mixtes, **0** ranged-only.

⚠ L'etage 1 porte SA PROPRE CONTRE-EPREUVE : il rejoue l'ANCIENNE decision (`select_weapon_pierce`)
sur le meme montage et EXIGE qu'elle DIFFERE. Sans ce cran, un montage ou les deux coincident
rendrait le test vert sans rien prouver -- exactement le « accord en regime degenere » que la
doctrine interdit.

ASCII only.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PYDIR = Path(__file__).resolve().parents[3]                  # scripts/python
sys.path.insert(0, str(PYDIR))

import gameconfig as GC                                                    # noqa: E402
from engine.runner import battle_query_state as BQS                        # noqa: E402
from engine.runner.components import PositionComponent, StatsComponent     # noqa: E402
from engine.runner.operations import damage_utility as DU                  # noqa: E402
from engine.services.battle_query import (attack_range_type,               # noqa: E402
                                          select_weapon_pierce)
from engine.services.custom_normal_attack import (                         # noqa: E402
    CUSTOM_NORMAL_ATTACK_BY_ACTIVE, CUSTOM_NORMAL_ATTACK_BY_PASSIVE, NORMAL_BOSS_ATTACK)
from engine.runner.state import State                                      # noqa: E402

DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/engine/services/battle_query.py",
        "scripts/python/engine/services/custom_normal_attack.py",
        "scripts/python/engine/runner/battle_query_state.py",
        "scripts/python/engine/runner/operations/damage_utility.py",
        "scripts/python/engine/runner/abilities/targeting.py",
    ),
    "build": True,
    "toujours": False,
    "raison": "Le FOYER du slot 2 d'`IBattleQuery` (`BattleQuery$$IsMeleeAttack`), son montage de "
              "substrat runner, et le consommateur qui decidait par l'arme. `build: True` parce "
              "que l'etage 2 lit le gameconfig du build courant (les 18 ids d'attaque normale).",
}


def _ctx(visual_id: str):
    """`UnitContext` reduit a ce que les DEUX decisions lisent -- l'ancienne (arme, percage) et la
    nouvelle (cascade de l'attaque normale). Duck-typing assume : `StatsComponent` ne valide rien,
    et le test mesure un AIGUILLAGE, pas une valeur de degat."""
    return SimpleNamespace(visual_id=visual_id, normal_hits=None, traits=(),
                           extra_pierce=0, extra_pierce_melee=0, extra_pierce_ranged=0,
                           passive_abilities=[], active_abilities=[],
                           config_active_abilities=None)


def _state(visual_id: str, apos: tuple, tpos: tuple) -> State:
    st = State()
    a = st.add_entity(1)
    a.add_component(StatsComponent(_ctx(visual_id)))
    a.add_component(PositionComponent(apos[0], apos[1]))
    t = st.add_entity(2)
    t.add_component(StatsComponent(_ctx(visual_id)))
    t.add_component(PositionComponent(tpos[0], tpos[1]))
    return st


def _weapons(visual_id: str):
    return (GC.unit(visual_id) or {}).get("weapons") or []


def _is_melee_weapon(w) -> bool:
    r = (w or {}).get("Range")
    return r is None or int(r) < 2


def _pick(kind: str) -> str:
    """Un `unitId` du gameconfig, choisi PAR SA FORME D'ARMEMENT et non code en dur : le catalogue
    bouge d'un build a l'autre, un id fige rendrait le test vacant en silence."""
    for bucket in ("lineup", "npc", "summons"):
        for uid in GC.all_unit_ids()[bucket]:
            ws = _weapons(uid)
            if not ws:
                continue
            m = any(_is_melee_weapon(w) for w in ws)
            r = any(not _is_melee_weapon(w) for w in ws)
            if kind == "melee_only" and m and not r:
                return uid
            if kind == "mixte" and m and r and max(int(w.get("Range") or 0)
                                                   for w in ws if not _is_melee_weapon(w)) >= 3:
                return uid
    raise AssertionError("aucune unite %r au catalogue -- le montage est vacant" % kind)


# --------------------------------------------------------------------------------------------
# ETAGE 1 -- l'AIGUILLAGE, avec sa contre-epreuve : l'ancienne decision doit DIFFERER.
# --------------------------------------------------------------------------------------------

def test_etage1_non_adjacent_sans_arme_eligible_est_ranged():
    """Le regime qui SEPARE les deux modeles. `assert` sur les DEUX cotes : la nouvelle valeur, et
    le fait que l'ancienne etait l'INVERSE (sinon le montage ne prouve rien)."""
    uid = _pick("melee_only")
    st = _state(uid, (0, 0), (0, 6))               # distance hex 6 : hors de toute portee melee
    ctx = st.get_entity(1).get_component(StatsComponent).ctx

    # --- ancienne decision, rejouee TELLE QUELLE (`select_weapon_pierce` -> `not is_ranged`) ---
    _p, ancien_is_ranged, _h, _prof = select_weapon_pierce(ctx, False, 6)
    ancien_melee = not ancien_is_ranged
    assert ancien_melee is True, (
        "montage VACANT : l'ancien modele rendait deja 'ranged' sur %r -- il faut une unite "
        "SANS arme ranged en portee pour que le regime soit discriminant" % uid)

    # --- decision courante : le slot 2, branche `Normal(3)`, cible NON adjacente -> ranged ---
    assert DU.normal_attack_is_melee(st, 1, 2) is False, (
        "BattleQuery$$IsMeleeAttack branche Normal(3) : !ForceRangedAttack && AreEntitiesAdjacent "
        "-- la cible n'est PAS adjacente, le natif rend false")


def test_etage1_temoin_adjacent_reste_melee():
    """TEMOIN ou le canal ne doit PAS s'ouvrir : au contact, les deux modeles disent melee. Un
    correctif qui rendrait `False` partout passerait l'assertion precedente et tomberait ici."""
    uid = _pick("melee_only")
    st = _state(uid, (0, 0), (1, 0))
    ctx = st.get_entity(1).get_component(StatsComponent).ctx
    _p, is_ranged, _h, _prof = select_weapon_pierce(ctx, True, 1)
    assert (not is_ranged) is True
    assert DU.normal_attack_is_melee(st, 1, 2) is True


def test_etage1_temoin_arme_ranged_en_portee_reste_ranged():
    """SECOND temoin : une unite MIXTE, cible hors contact mais dans la portee de son arme a
    distance. Les deux modeles disent ranged -- le fix ne doit rien y changer."""
    uid = _pick("mixte")
    st = _state(uid, (0, 0), (0, 2))
    ctx = st.get_entity(1).get_component(StatsComponent).ctx
    _p, is_ranged, _h, _prof = select_weapon_pierce(ctx, False, 2)
    assert is_ranged is True, "montage vacant : %r n'a pas d'arme ranged de portee >= 2" % uid
    assert DU.normal_attack_is_melee(st, 1, 2) is False


def test_etage1_tri_etat_conserve():
    """`None` = couple non predictible (caster sans `StatsComponent`) -- le contrat que
    `_prediction_fields` lit pour retomber sur la cle DEGRADEE. Il ne doit pas devenir `False`."""
    st = State()
    a = st.add_entity(1)
    a.add_component(PositionComponent(0, 0))       # pas de StatsComponent
    t = st.add_entity(2)
    t.add_component(PositionComponent(0, 3))
    assert DU.normal_attack_is_melee(st, 1, 2) is None


# --------------------------------------------------------------------------------------------
# ETAGE 2 -- la MESURE qui justifie la branche prise : les ids d'attaque normale n'ont AUCUNE
# entree gameconfig, donc `GetAbilityAttackRangeType` rend `None` et le natif prend `Normal(3)`.
# Si un build la renseigne, ce test rougit -- et le port, lui, restera juste parce qu'il resout
# et passe le NOM (c'est exactement pourquoi il le resout).
# --------------------------------------------------------------------------------------------

def test_etage2_les_attaques_normales_nont_pas_dattack_range_type():
    noms = (["NormalAttack", "Loki_NormalAttack", NORMAL_BOSS_ATTACK]
            + sorted(CUSTOM_NORMAL_ATTACK_BY_PASSIVE.values())
            + sorted(CUSTOM_NORMAL_ATTACK_BY_ACTIVE.values()))
    noms = sorted(set(noms))
    assert len(noms) >= 17, "registre d'attaques normales anormalement court : %d" % len(noms)
    porteurs = {n: attack_range_type(n) for n in noms if attack_range_type(n) is not None}
    assert porteurs == {}, (
        "des ids d'attaque normale portent desormais un attackRangeType : %r -- relire la branche "
        "prise par BattleQuery$$IsMeleeAttack pour ces ids" % porteurs)


def test_etage2_le_nom_resolu_est_lattaque_normale_concrete():
    """Le port RESOUT le nom (il ne passe pas `None` par commodite) : c'est ce qui le rend juste
    le jour ou l'etage 2 ci-dessus rougit."""
    uid = _pick("melee_only")
    st = _state(uid, (0, 0), (0, 6))
    nom = BQS.normal_attack_name(st, 1)
    assert isinstance(nom, str) and nom, "aucun nom d'attaque normale resolu pour %r" % uid


# --------------------------------------------------------------------------------------------
# ETAGE 3 -- le switch lui-meme n'est PAS re-ecrit dans le montage runner : les branches
# non-`Normal` doivent sortir du foyer `services/battle_query`, sans lire aucune position.
# --------------------------------------------------------------------------------------------

@pytest.mark.parametrize("rt,attendu", [("Melee", True), ("Ranged", False), ("None", False)])
def test_etage3_branches_non_normal_ignorent_la_position(monkeypatch, rt, attendu):
    uid = _pick("melee_only")
    st = _state(uid, (0, 0), (0, 6))               # NON adjacent -- et pourtant `Melee` rend True
    monkeypatch.setattr("engine.services.battle_query.attack_range_type", lambda _n: rt)
    assert BQS.is_melee_attack(st, "PeuImporte", 1, 2) is attendu
