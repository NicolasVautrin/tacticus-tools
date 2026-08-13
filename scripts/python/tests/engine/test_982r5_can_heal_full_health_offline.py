"""#982-r5 -- le CLIQUET du 3e disjoint d'`AttackQuery$$EntityCanBeHealed` : le flag
`UnitFlag.CanHealFullHealthUnits` (23) est LU SUR LE CASTER, et il MORD.

`IdunBattle.Core.Services.AttackQuery$$EntityCanBeHealed(caster, target, scope, removeEffects)` :

    if (EntityExtensions.IsMachine(target)) return false;
    if (!(   AttackQuery.IsDamagedUnit(target)
          || (removeEffects && AttackQuery.HasNegativeUnitEffect(target))
          || (caster != null && UnitExtensions.HasFlag(caster, 0x17 CanHealFullHealthUnits))))
        return false;
    ...

POURQUOI CE FICHIER EXISTE. Le port ecrivait, a DEUX endroits, que ce disjoint etait inerte --
« aucun chemin du port ne pose ces flags », « aucun consommateur porte ne le lit ». Les deux sont
FAUX, et les avoir laisses a produit DEUX verdicts de residu errones d'affilee (#966-r2 puis
#982-r5, qui annoncait un port « pas ecrit » alors qu'il l'etait). Le port ne POSE pas le flag et
n'a pas a le faire : `IdunBattle.Entities.Behaviours.AddFlagBehaviour$$Execute` joue COTE NATIF
avant la capture, et `runner/snapshot._load_unit_flags` recopie `combatSnapshot.units[].unitFlags`
dans le `UnitFlagsComponent`.

Corriger la prose ne suffisait pas : rien ne rougissait si le disjoint disparaissait. C'est ce
fichier qui manquait.

CE QU'IL GARDE (offline pur, aucun runner) :

  1. **L'ORDINAL** -- `UnitFlag.CanHealFullHealthUnits == 23`, la valeur MESUREE dans
     `combatSnapshot.unitFlagTypes` (#982-r5, build `rnca9r7q6c`).
  2. **LE DISJOINT MORD** -- sur une cible a PLEINS PV (donc `IsDamagedUnit` FAUX, assertionne),
     un caster PORTANT le flag rend `True` la ou un caster sans le flag rend `False`.
  3. **LE GARDE `caster != null`** -- `caster_id = None` rend `False`, meme cible.
  4. **LE FLAG EST LU SUR LE CASTER, PAS SUR LA CIBLE** -- le poser sur la CIBLE ne change rien.
  5. **LE SEED** -- `snapshot._load_unit_flags` recopie bien `combatSnapshot.units[].unitFlags` dans
     le `UnitFlagsComponent`, et il apparie par l'`entityId` DU SNAPSHOT (qui est le `squadId`
     d'`observeBattle`, piege de mesure nomme dans `attack_query.py`).

ASCII only. Point d'entree : `docs/rl/case-982-lot-capteur-sept-premisses-sur-neuf.md` SS2.
"""
from __future__ import annotations

from engine.entities.unit_flag import UnitFlag
from engine.runner.abilities.attack_query import (entity_can_be_healed, is_damaged_unit,
                                                  UNIT_FLAG_CAN_HEAL_FULL_HEALTH)
from engine.runner.components import (HealthComponent, PositionComponent, StatsComponent,
                                      UnitComponent, UnitFlagsComponent)
from engine.entities.unit_context import UnitContext
from engine.runner.state import State

#: Ce qui doit changer pour que ce FICHIER puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/runner/abilities/attack_query.py",
        "scripts/python/engine/entities/unit_flag.py",
        "scripts/python/engine/runner/components.py",
        "scripts/python/engine/runner/snapshot.py",
        "scripts/python/engine/runner/abilities/loki/healing_balms.py",
        "scripts/python/engine/runner/operations/heal.py"),
    "build": False,
    "toujours": False,
    "raison": "Il garde le 3e disjoint d'`EntityCanBeHealed` (flag `CanHealFullHealthUnits` lu sur "
              "le CASTER), son ordinal, et la voie de seed qui l'alimente.",
}


def _unite(st, *, hp, hp_max, flags=(), visual="u"):
    """Une unite MINIMALE : vivante, positionnee, avec ses PV et ses `UnitFlag`. Aucun trait, aucun
    effet -- le montage doit rester DEGENERE partout SAUF sur l'axe teste."""
    e = st.add_entity()
    e.add_component(UnitComponent(visual_id=visual, alive=True))
    e.add_component(PositionComponent(col=0, row=0))
    e.add_component(HealthComponent(hp=hp, hp_max=hp_max))
    fl = UnitFlagsComponent()
    for f in flags:
        fl.add(int(f))
    e.add_component(fl)
    ctx = UnitContext(entity_id=e.id, visual_id=visual)
    ctx.traits = []
    e.add_component(StatsComponent(ctx=ctx))
    return e.id


def _montage(caster_flags=(), target_flags=()):
    """Le CAS : une cible a PLEINS PV et un caster dont on choisit les drapeaux."""
    st = State()
    caster = _unite(st, hp=100, hp_max=100, flags=caster_flags, visual="caster")
    target = _unite(st, hp=100, hp_max=100, flags=target_flags, visual="target")
    return st, caster, target


def test_l_ordinal_du_flag_est_celui_du_build():
    """(1) `combatSnapshot.unitFlagTypes.CanHealFullHealthUnits` vaut **23** sur `rnca9r7q6c`
    (mesure #982-r5). Un renumerotage du build changerait le membre sans que rien d'autre ne
    bouge -- et la lecture deviendrait silencieusement fausse."""
    assert int(UnitFlag.CanHealFullHealthUnits) == 23, (
        f"`UnitFlag.CanHealFullHealthUnits` vaut {int(UnitFlag.CanHealFullHealthUnits)}, mesure "
        f"23 dans `combatSnapshot.unitFlagTypes` -- le mirror et le build ont diverge")
    assert int(UNIT_FLAG_CAN_HEAL_FULL_HEALTH) == int(UnitFlag.CanHealFullHealthUnits), (
        "`attack_query.UNIT_FLAG_CAN_HEAL_FULL_HEALTH` n'est plus le membre d'enum")


def test_le_regime_est_non_degenere_la_cible_est_a_pv_pleins():
    """(2a) NON-TRIVIALITE. Si la cible etait BLESSEE, le 1er disjoint (`IsDamagedUnit`) suffirait
    et tous les crans suivants rendraient `True` sans rien mesurer."""
    st, _caster, target = _montage()
    assert is_damaged_unit(st, target) is False, (
        "la cible du montage est BLESSEE -- le 1er disjoint d'`EntityCanBeHealed` la rendrait "
        "eligible a lui seul, et les crans suivants ne discrimineraient RIEN")


def test_le_disjoint_du_caster_mord():
    """(2b) LE VERDICT. Meme cible a PV pleins, seul le CASTER change : avec le flag `True`, sans
    le flag `False`. C'est ce couple qui etablit que la regle mord -- un `True` seul serait
    compatible avec un predicat constamment vrai."""
    st_avec, c_avec, t_avec = _montage(caster_flags=(UnitFlag.CanHealFullHealthUnits,))
    st_sans, c_sans, t_sans = _montage()
    avec = entity_can_be_healed(st_avec, c_avec, t_avec, 0, False)
    sans = entity_can_be_healed(st_sans, c_sans, t_sans, 0, False)
    assert avec is True and sans is False, (
        f"le 3e disjoint d'`EntityCanBeHealed` ne mord PAS : caster AVEC le flag "
        f"`CanHealFullHealthUnits` -> {avec} (attendu True), caster SANS -> {sans} (attendu False), "
        f"sur une cible a PLEINS PV dans les deux cas")


def test_le_garde_caster_non_nul():
    """(3) `caster != null` est un TERME du disjoint natif, pas une commodite : sans caster, une
    cible pleine reste inelligible."""
    st, _c, t = _montage(caster_flags=(UnitFlag.CanHealFullHealthUnits,))
    assert entity_can_be_healed(st, None, t, 0, False) is False, (
        "`caster = None` rend une cible a PV pleins eligible -- le garde `caster != null` du 3e "
        "disjoint a saute")


def test_le_flag_est_lu_sur_le_caster_pas_sur_la_cible():
    """(4) Le natif lit `HasFlag(caster, 0x17)`. Poser le flag sur la CIBLE ne doit RIEN changer --
    c'est le cran qui distingue « le disjoint est cable » de « le disjoint est cable du BON cote »."""
    st, c, t = _montage(target_flags=(UnitFlag.CanHealFullHealthUnits,))
    assert entity_can_be_healed(st, c, t, 0, False) is False, (
        "le flag pose sur la CIBLE rend la cible eligible -- le port lit `HasFlag(target, 0x17)` "
        "la ou le natif lit `HasFlag(caster, 0x17)`")


def test_le_seed_recopie_les_unitflags_du_combatsnapshot():
    """(5) LA VOIE DE SEED. C'est elle qui rend le disjoint ATTEIGNABLE offline : le port ne pose
    jamais ce flag, il le RECOIT.

    ⚠ L'appariement se fait sur l'`entityId` DU SNAPSHOT, qui est le `squadId` d'`observeBattle` --
    un lecteur qui apparie par `observeBattle.entityId` lit `flags = None` sur TOUTES les unites et
    conclut faussement que rien n'est seede (piege paye en mesure, #982-r5)."""
    from engine.runner import snapshot as SNAP
    st = State()
    e = st.add_entity()
    e.add_component(UnitComponent(visual_id="baldr", alive=True))
    e.add_component(HealthComponent(hp=100, hp_max=100))
    SNAP._load_unit_flags(st, {"units": [{"entityId": e.id,
                                          "unitFlags": [int(UnitFlag.CanHealFullHealthUnits)]}]})
    fl = st.get_entity(e.id).get_component(UnitFlagsComponent)
    assert fl is not None and fl.has(int(UnitFlag.CanHealFullHealthUnits)), (
        "`snapshot._load_unit_flags` n'a pas recopie `combatSnapshot.units[].unitFlags` dans le "
        "`UnitFlagsComponent` -- le 3e disjoint d'`EntityCanBeHealed` serait alors structurellement "
        "inatteignable offline, et la prose qui l'affirmait redeviendrait vraie")
