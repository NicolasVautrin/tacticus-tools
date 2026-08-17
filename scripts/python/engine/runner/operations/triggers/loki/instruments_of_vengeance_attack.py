"""PHASE 2 d'`InstrumentsOfVengeance` (1215) -- la TRIGGERED `1519`, declenchee par le `Triggered()`
d'`IdunBattle.Entities.Effects.APendingAttackEffect` (`triggers/pending_attack.py`). #889-r7

Meme emplacement et meme cause que `loki/lions_wrath_attack.py`, `loki/overwhelming_wrath_attack.py`
et `loki/seeker_missile_attack.py` : une ability TRIGGERED vit avec les triggers, pour que
`TRIGGERED_ABILITY_BEHAVIOURS[1519]` soit peuple des que `dispatch/registry.py` est charge, sans
dependre d'`abilities/handler.py` (cliquet `test_503r3_registre_trigger_peuple_offline.py`, dont le
PERIMETRE est DERIVE de `PENDING_ATTACK_EFFECTS`).

===============================================================================================
`...Triggered.Loki.InstrumentsOfVengeance_AttackAbility$$CreateBehaviour(abilityState, trigger)`
===============================================================================================
MIRROR 1:1 du decompile, build `t6dpr4k06g` -- les QUATRE lectures persistantes d'abord :

  eA0 = DSLSelectors$$Entity( DSLFormulas$$GetPersistentData(AbilityOrEffect(this), Owner@+0x30,
                                                            <KEY_TARGET> + "0") )
  eB0 = ... <KEY_DIRECTION> + "0"
  eA1 = ... <KEY_TARGET>    + "1"
  eB1 = ... <KEY_DIRECTION> + "1"

  r = DSLBehaviors$$RemoveEffect( AllTiles@DSLSelectors+0x18, Nullable(0x5ee = 1518) )
      + ( AttackLine(abilityState, eA0, eB0) + AttackLine(abilityState, eA1, eB1) )
      + DSLBehaviors$$ClearAllPersistentData( AbilityOrEffect(this), Owner@+0x30 )

  n     = AbilityConfiguration$$GetVariableForLevel(config@this+0x20, 0x4f = nrOfSummons,
                                                    abilityState, 0)
  t1    = DSLSelectors$$Randomize( CanAddUnit( AdjacentTiles(Owner@+0x30) ) )
  t2    = DSLSelectors$$Randomize( CanAddUnit( AdjacentTiles( UnitsDamagedThisPhase(Owner@+0x30) ) ) )
  t3    = DSLSelectors$$Randomize( DSLSelectors$$Filter( CanAddUnit(AllTiles@+0x18),
              op_LogicalNot( DSLTriggers$$HasAdjacentEnemies(Owner@+0x30, ActiveTarget@+0x68,
                                                             includeObjects: 0,
                                                             includeSteppables: false) ) ) )
  tiles = DSLSelectors$$First( (t2 op_Addition t1) op_Addition t3, n, 0 )
  opts  = SpawnUnitOptions$$WithStatsFromConfig( config@+0x20, abilityState, 0, 0 )
  opts.<+0x18> = DSLBehaviors$$PerformAIAttackFromCurrentPosition( ActiveTarget@+0x68, 0, 0, false )
  return r + DSLBehaviors$$Group(
                 DSLBehaviors$$Spawn( Owner@+0x30, tiles,
                                      AbilityConfiguration$$GetStringConstant(config, 0 = unitId),
                                      opts ),
                 Owner@+0x30, 0x22 = GroupType.Ability_Summon )

  AttackLine(abilityState, edge, direction) =
      DSLBehaviors$$Group(
          DSLBehaviors$$Foreach( edge op_Addition TilesBehindInLine(edge, direction),
                                 AttackTileBehavior(abilityState) ),
          Owner@+0x30, 0x31 = GroupType.Ability_CustomGroup )

  AttackTileBehavior(abilityState) =
      inform = DSLBehaviors$$Inform( 0xc1, DSLFormulas$$EntityId(ActiveTarget@+0x68) )
      cond   = DSLTriggers$$HasUnit(ActiveTarget@+0x68, 3)
               op_BitwiseAnd DSLTriggers$$AreEnemies(Owner@+0x30, ActiveTarget@+0x68, 0)
      atk    = DSLBehaviors$$AttackWithAttackDamage(
                   caster = Owner@+0x30, target = ActiveTarget@+0x68,
                   amount = BaseTriggeredAbility$$MinMaxDamage(this, abilityState),
                   damageProfile = DSLSelectors$$Direct(BaseTriggeredAbility$$GetDamageProfile(this)),
                   hits = DSLFormulas$$Get(BaseTriggeredAbility$$GetHits(this)),
                   abilityOrEffect, options = <STRUCT ZEROEE>, selectionType = 2 )
      return DSLBehaviors$$Group( DSLBehaviors$$If(cond, atk + inform, inform),
                                  Owner@+0x30, 0x31 )

⚠ **`AttackTargetTiles(edge, direction)` = `edge + TilesBehindInLine(edge, direction)` N'EST PAS
APPELEE par `CreateBehaviour`** -- `AttackLine` reconstruit la meme union INLINE. Le port ne la
mirrore donc pas comme fonction separee : ce serait du code que rien n'atteint.

SEPT POINTS DE FIDELITE, tous LUS :

1. **LE DEGAT APPARTIENT A LA TRIGGERED, PAS AU CAST.** Le cast (`...InstrumentsOfVengeanceAbility$$
   ExecuteBehaviour`) ne porte AUCUN noeud d'attaque : il pose les marques `1518` sur les tuiles,
   ecrit les quatre cles persistantes, arme `AddBondEffect(0x5ef = 1519)` et re-arme l'overwatch.
   Tout le degat est ici. Ecrire l'attaque au cast est la faute que l'audit de couverture nomme
   comme ayant deja coute quatre tranches -- la colonne `categorie` derive du KIT, pas du
   BEHAVIOUR.

2. **LE PREMIER JEU DE DEGAT**, contrairement a `TheLionsWrath` : `MinMaxDamage` / `GetDamageProfile`
   / `GetHits` (et non `MinMaxDamage2` / `GetDamageProfile2` / `ConfigConst(0x32)`). Le gameconfig
   de 1215 ne porte d'ailleurs QUE le premier (`constants = {damageProfile: HeavyRound, nrOfHits: 6,
   unitId: darkaSmnTerminator, cooldownTurns: 2}`, `variables = {minDmg, maxDmg, nrOfSummons,
   summonHp, summonDmg, summonArmor}`) -- aucune cle `_2`.

3. **LA CONFIG EST CELLE DE L'ACTIVE 1215.** Mesure : `GC.ability("InstrumentsOfVengeance_PendingAttack")`
   et `GC.ability("InstrumentsOfVengeance_Attack")` rendent **None** tous les deux -- la triggered
   n'a aucune entree gameconfig. Meme forme, meme mesure et meme conclusion que
   `OverwhelmingWrath_Attack`, `SeekerMissileFrequencyLock_Attack` et `TheLionsWrath_PendingAttack`
   (residu #513-r3 pour le site natif de l'attribution, partage).

4. `is_melee=False` : `attackRangeType` de 1215 = `"Ranged"` au gameconfig (contraste LU avec 1217,
   qui est `"Melee"`). C'est la CONFIG qui decide, pas le noeud -- les cinq surcharges de
   `AttackWithAttackDamage` ne portent AUCUN bit melee/ranged (releve #503-r5), et
   `IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack` part de
   `GetAbilityAttackRangeType(<l'ability du coup>)`.

5. `multi=False` : le natif passe `ActiveTarget@+0x68`, le slot de l'element COURANT du `Foreach` --
   donc UNE tuile a la fois. Le `Foreach` EST l'iteration ; poser `multi=True` ferait trier les
   cibles une seconde fois, par-dessus l'ordre du selecteur que le `Foreach` preserve.

6. **`options` ENTIEREMENT A ZERO** (le decompile met a zero `local_88`/`uStack_80`/`local_78`/
   `uStack_70`/`local_68` avant l'appel) : ni `alwaysOverkilled`, ni `alwaysCrit`, ni
   `isNormalAttackDamage`, et **PAS de `crit_allowed_hits`** -- contraste LU avec la phase 2 de
   1217, qui pose une `List<int>{1}` a `options+0x08`. Ici le crit s'eteint apres le premier coup
   non-critique, comme sur les douze autres call-sites a struct zeroee.

7. **LES DEUX `Group` D'`AttackLine` SONT IMBRIQUES**, et c'est LU : `AttackTileBehavior` rend
   deja un `Group(..., Owner, 0x31)`, et `AttackLine` en pose un SECOND autour du `Foreach`. Ce
   n'est pas une redondance de lecture -- le decompile appelle `DSLBehaviors$$Group` aux deux
   etages, avec le meme `Owner@+0x30` et le meme `0x31`.

⚠ **`ATTACKER_EFFECT_SOURCE`, PAS `ATTACKER_BONDED`** pour l'entree `1519` de
`PENDING_ATTACK_EFFECTS` :
`Idun.Source.IdunBattle.Logic.Entities.Effects.Loki.InstrumentsOfVengeance_PendingAttackEffect$$
GetAttackingUnitSelector` est SURCHARGEE en `DSLSelectors$$EffectSource(Effect@DSLSelectors+0x38)`
(corps LU : il prend `<selectors+0x38>` et alloue le selecteur de source, sans passer par
`ABondEffect$$BondedEntitySelector`). Le call-site de pose est pourtant un `AddBondEffect(0x5ef,
AbilityStateReference, source = Owner@+0x30, targets = Owner@+0x30, bondedEntity = Owner@+0x30)` --
les TROIS slots valent `Owner`, donc source et bonde COINCIDENT ici et l'erreur serait INVISIBLE
sur ce porteur, et fausse partout ailleurs. On ecrit ce que le decompile declare.

NI `TARGETING_OPTIONS` NI `ABILITY_ATTACK_TYPE` : `BaseTriggeredAbility`, hors `ABILITY_CLASSES`.
ASCII only.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from ....abilities.behaviours.combat import AttackWithAttackDamage
from ....abilities.behaviours.effects import RemoveEffect
from ....abilities.behaviours.lifecycle import TRIGGERED_ABILITY_BEHAVIOURS
from ....abilities.behaviours.persistent_data import ClearAllPersistentData
from ....abilities.behaviours.summon import PerformAIAttack, Spawn
from ....components import StatsComponent
from .....entities.ability_variable_type import AbilityVariableType
from .....entities.active_ability_type import ActiveAbilityType
from .....entities.behaviours import Foreach, Group, If, Inform, op_add
from .....entities.effect_type import EffectType
from .....entities.effects.magnitude import ability_var
from .....entities.formulas import GetPersistentData
from .....entities.selectors.accessors import ActiveTarget, Owner
from .....entities.selectors.geometry import (Entity, PickFirstN, Randomize, TilesBehindInLine)
from .....entities.selectors.tiles import AdjacentTiles, AllTiles, CanAddUnit, TileUnion
from .....entities.selectors.units import Filter, UnitsDamagedThisPhase
from .....entities.triggered_ability_type import TriggeredAbilityType
from .....entities.triggers import AreEnemies, HasUnit, Not, TriggerAnd, has_adjacent_enemies
from .....entities.unit_team_selection_type import UnitTeamSelectionType
from .....streams.group_type import GroupType

if TYPE_CHECKING:                                  # pragma: no cover
    from ....state import State

#: Le NOM gameconfig de l'ACTIVE 1215 -- la config que lisent LES DEUX PHASES (cf. point 3).
#: DERIVE de l'enum et defini ICI plutot qu'importe d'`abilities/loki/instruments_of_vengeance.py` :
#: ce module doit rester chargeable SEUL par `dispatch/registry.py` (meme discipline que
#: `LW_ACTIVE_ID` / `OW_ACTIVE_ID`).
IOV_ACTIVE_ID = ActiveAbilityType.InstrumentsOfVengeance.name          # "InstrumentsOfVengeance"
IOV_ABILITY = int(ActiveAbilityType.InstrumentsOfVengeance)            # 0x4bf = 1215
#: `TriggeredAbilityType` -- LU au corps entier de `...InstrumentsOfVengeance_PendingAttackEffect$$
#: GetTriggeredAbilityType` (`return 0x5ef`). ⚠ **CE N'EST PAS UN `EffectType`**, meme si les deux
#: enums portent ici le MEME nom pour le MEME ordinal : les deux tables partagent des centaines
#: d'ordinaux, et c'est le NOM de l'enum qui rend la ligne verifiable.
IOV_ATTACK = int(TriggeredAbilityType.InstrumentsOfVengeance_PendingAttack)    # 0x5ef = 1519
#: `EffectType.InstrumentsOfVengeance_LocationTarget` -- la MARQUE posee par la phase 1 sur les
#: TUILES de la ligne, que le `RemoveEffect` d'ici consomme.
IOV_LOCATION_TARGET = int(EffectType.InstrumentsOfVengeance_LocationTarget)    # 0x5ee = 1518
#: Cles de donnee persistante, LUES : les MEMES deux litteraux que la phase 1 (`DAT_183366460` et
#: `DAT_1833661d0` du build, resolus par `data/symbols/<build>/metadata/string_literals.tsv`). La
#: phase 1 les ECRIT sur `Caster@+0x48`, la phase 2 les RELIT sur `Owner@+0x30`.
IOV_KEY_TARGET_TILE = "InstrumentsOfVengeance_TargetTile_"
IOV_KEY_DIRECTION_TILE = "InstrumentsOfVengeance_DirectionTile_"
#: `TagKey` du `DSLBehaviors$$Inform(tag, value)`. Aucun enum de TagKey n'est mirrore dans le port
#: (meme statut que l'`AS_INFORM_TAG` d'`abilities/admec.py` et que l'`Inform(0xc1)` d'`aeldari.py`) :
#: le noeud est un hint AI/UI, NO-OP cote runner.
IOV_INFORM_TAG = 0xc1
#: 3e argument LU de `DSLTriggers$$AreEnemies(unit1, unit2, selectionType)` -- un
#: `UnitTeamSelectionType`, pas un `UnitSelectionType`.
IOV_TEAM_SELECTION = int(UnitTeamSelectionType.ByCurrentTeam)                  # 0


def _persistent_tile(key: str, index: int):
    """`Entity( GetPersistentData(AbilityOrEffect(this), Owner@+0x30, <key> + <index>) )`.

    L'`AbilityOrEffect` de la TRIGGERED designe la MEME entree de `PersistentDataComponent` que
    celle qu'a ecrite l'ACTIVE : le natif construit les deux depuis `AbilityOrEffect$$op_Implicit`
    sur l'ability courante, et `GetPersistentDataId` replie une ability sur son `ActiveAbilityType`.
    Le port passe donc `IOV_ABILITY` (1215) des DEUX cotes -- passer `IOV_ATTACK` (1519) lirait un
    dictionnaire VIDE, et la phase 2 ne frapperait rien, sans erreur."""
    return Entity(GetPersistentData(IOV_ABILITY, Owner(), key + str(int(index))))


def instruments_of_vengeance_attack_tile_behavior():
    """`...InstrumentsOfVengeance_AttackAbility$$AttackTileBehavior(abilityState)` -- cf. l'en-tete.

    ⚠ L'`Inform` est dans les DEUX branches du `If` : le natif le construit UNE fois et le passe a
    la fois en `then` (concatene APRES l'attaque) et en `else`. Le hint part donc pour CHAQUE tuile
    de la ligne, occupee ou non."""
    inform = Inform(IOV_INFORM_TAG)
    # `HasUnit(ActiveTarget@+0x68, 3)` : le port n'a pas de parametre de mode sur ce noeud (il lit
    # les occupants VIVANTS, ce qu'est `UnitSelectionType.OnlyAliveAndTargetable` sur une tuile).
    cond = TriggerAnd(HasUnit(ActiveTarget()),
                      AreEnemies(Owner(), ActiveTarget(), selection_type=IOV_TEAM_SELECTION))
    atk = AttackWithAttackDamage(
        ActiveTarget(),                       # `target = ActiveTarget@+0x68`
        IOV_ACTIVE_ID,                        # cf. point 3 : la config de l'ACTIVE
        _damage_profile(),                    # `GetDamageProfile()` -- PREMIER jeu (point 2)
        is_melee=False,                       # cf. point 4 : `attackRangeType = "Ranged"`
        # PREMIER jeu de bornes et de coups : les defauts de la feuille sont exactement
        # `minDmg`/`maxDmg`/`nrOfHits`, qui SONT `MinMaxDamage` et `Get(GetHits())`.
        level_slot="active",
        multi=False,                          # cf. point 5 : le `Foreach` EST l'iteration
        ability_type=IOV_ATTACK,
        # cf. point 6 : struct d'options ENTIEREMENT zeroee -- surtout PAS de `crit_allowed_hits`.
        force_overkill=False, force_crit=False)
    return Group(If(cond, op_add(atk, inform), inform),
                 int(GroupType.Ability_CustomGroup), Owner())


def instruments_of_vengeance_attack_line(edge, direction):
    """`...InstrumentsOfVengeance_AttackAbility$$AttackLine(abilityState, edge, direction)`.

    `TileUnion(edge, TilesBehindInLine(edge, direction))` transcrit
    `edge op_Addition TilesBehindInLine(edge, direction)` : la tuile CIBLE elle-meme, puis la ligne
    tiree derriere elle. C'est la surcharge a DEUX SELECTEURS de `TilesBehindInLine` (celle que la
    phase 1 rejoue pour s'exclure), pas la surcharge a formule vecteur."""
    ligne = TileUnion(edge, TilesBehindInLine(edge, direction))
    return Group(Foreach(ligne, instruments_of_vengeance_attack_tile_behavior()),
                 int(GroupType.Ability_CustomGroup), Owner())


def instruments_of_vengeance_spawn_tiles():
    """`(t2 + t1) + t3` -- les TROIS viviers de tuiles, dans l'ORDRE du decompile.

    ⚠ **L'ORDRE DE L'UNION EST LOAD-BEARING** : le natif construit `t1` puis `t2` puis `t3`, mais
    les additionne `(t2 + t1) + t3`. Comme le `First(..., n)` qui suit prend les `n` PREMIERS
    elements dans l'ordre du selecteur, les tuiles adjacentes aux unites DEJA BLESSEES CE TOUR
    (`t2`) passent AVANT celles adjacentes au caster (`t1`), et le vivier « n'importe ou, loin des
    ennemis » (`t3`) ne sert qu'en dernier recours. Recopier l'ordre de CONSTRUCTION changerait la
    tuile choisie sans changer l'ensemble candidat.

    Chacun des trois est `Randomize(...)` -- donc l'ordre INTERNE de chaque vivier est tire au
    `state.rng`, et seul l'ordre ENTRE viviers est fixe."""
    t1 = Randomize(CanAddUnit(AdjacentTiles(Owner())))
    t2 = Randomize(CanAddUnit(AdjacentTiles(UnitsDamagedThisPhase(Owner()))))
    # `Filter(CanAddUnit(AllTiles), NOT HasAdjacentEnemies(Owner@+0x30, ActiveTarget@+0x68, 0,
    # false))` : `ActiveTarget` est la tuile CANDIDATE (le slot que `Filter` lie a chaque element),
    # donc le predicat dit « aucune unite ennemie du caster n'est adjacente a CETTE tuile ».
    t3 = Randomize(Filter(CanAddUnit(AllTiles()),
                          Not(has_adjacent_enemies(Owner(), ActiveTarget()))))
    return TileUnion(TileUnion(t2, t1), t3)


def instruments_of_vengeance_attack_tree(nb_summons: int):
    """Arbre de `...InstrumentsOfVengeance_AttackAbility$$CreateBehaviour` -- cf. l'en-tete.

    `nb_summons` = `GetVariableForLevel(0x4f = nrOfSummons)` est resolu par l'APPELANT, parce que le
    port n'a pas de noeud-valeur qui lise la config d'ability par niveau depuis l'interieur d'un
    arbre (meme convention que `invocation_of_machine_vengeance_tree`).

    ⚠ **L'ORDRE DES TROIS PREMIERS TERMES EST LOAD-BEARING** : le `RemoveEffect(1518)` passe AVANT
    les deux `AttackLine`, et le `ClearAllPersistentData` APRES. Deplacer le `Clear` avant les
    lignes viderait les quatre cles que les `Entity(GetPersistentData(...))` viennent tout juste de
    lire -- mais ces selecteurs sont evalues PARESSEUSEMENT, a l'execution du `Foreach`, donc le
    coup ne partirait plus. Et le `RemoveEffect` retire les marques de TOUTES les tuiles
    (`AllTiles`), pas seulement de celles des deux lignes."""
    lignes = op_add(
        instruments_of_vengeance_attack_line(_persistent_tile(IOV_KEY_TARGET_TILE, 0),
                                             _persistent_tile(IOV_KEY_DIRECTION_TILE, 0)),
        instruments_of_vengeance_attack_line(_persistent_tile(IOV_KEY_TARGET_TILE, 1),
                                             _persistent_tile(IOV_KEY_DIRECTION_TILE, 1)))
    r = op_add(op_add(RemoveEffect(IOV_LOCATION_TARGET, AllTiles()), lignes),
               ClearAllPersistentData(IOV_ABILITY, Owner()))
    # `Spawn(Owner@+0x30, First(tiles, n, 0), GetStringConstant(config, 0 = unitId), opts)`.
    # `unit_id_constant` reste le defaut `"unitId"` -- c'est LE constant d'indice 0, et le
    # gameconfig de 1215 le porte (`darkaSmnTerminator`). Le on-appearance est un
    # `PerformAIAttackFromCurrentPosition`, donc `allow_move_action=False` / `move_amount=0` (les
    # defauts EXPLICITES de la feuille, qui sont ceux de cette surcharge-la).
    spawn = Spawn(PickFirstN(instruments_of_vengeance_spawn_tiles(), int(nb_summons)),
                  IOV_ACTIVE_ID,
                  on_appearance=PerformAIAttack(ActiveTarget(), allow_move_action=False,
                                                move_amount=0))
    return op_add(r, Group(spawn, int(GroupType.Ability_Summon), Owner()))


def _damage_profile() -> str:
    """`BaseTriggeredAbility$$GetDamageProfile(this)` -- le PREMIER jeu, lu au gameconfig de
    l'ACTIVE (cf. points 2 et 3). Chaine VIDE si la config manque : la feuille d'attaque traite ce
    cas comme un profil absent, ce qui est une degradation VISIBLE."""
    # DIFFERE et GRATUIT : `gameconfig` n'est pas un module `engine.*`, il n'entre dans aucun cycle
    # du paquet, et le hisser ferait payer le chargement du gameconfig a tout importeur -- donc a
    # `dispatch/registry.py`, qui importe ce module pour effet de bord. (Meme raison, meme forme
    # que `lions_wrath_attack_tree`.)
    import gameconfig as GC
    consts = (GC.ability(IOV_ACTIVE_ID) or {}).get("constants") or {}
    return str(consts.get("damageProfile") or "")


def _nb_summons(state: "State", unit_id: int) -> int:
    """`AbilityConfiguration$$GetVariableForLevel(config, 0x4f = nrOfSummons, abilityState, 0)`.

    `abilityState` est le couple (niveau, multiplicateur) de l'ACTIVE 1215 du porteur, lu au
    `StatsComponent` -- meme voie que `InvocationOfMachineVengeanceAbility._nb_summons`."""
    e = state.get_entity(int(unit_id))
    sc = e.get_component(StatsComponent) if e is not None else None
    cctx = sc.ctx if sc is not None else None
    level = getattr(cctx, "active_ability_level", None)
    mult = int(getattr(cctx, "ability_variables_multiplier", 100) or 100)
    return int(ability_var(IOV_ACTIVE_ID, AbilityVariableType.nrOfSummons.name, level,
                           multiplier_pct=mult) or 0)


def _instruments_of_vengeance_attack_behaviour(state: "State", unit_id: int, entities, ectx):
    """Entree de `TRIGGERED_ABILITY_BEHAVIOURS[1519]` -- la phase 2, declenchee par le noeud
    `TriggerAbility` du `Triggered()` d'`APendingAttackEffect` (`triggers/pending_attack.py`).

    `unit_id` = l'unite declenchee (l'ATTAQUANT). ⚠ Ici l'effet est pose sur `Owner@+0x30` avec
    `source == bondedEntity == Owner` : porteur, source et bonde sont LA MEME unite (le Lion), a la
    difference de 1069/1217 ou ils appartiennent a deux joueurs. C'est ce qui rend l'ecart
    `ATTACKER_BONDED` / `ATTACKER_EFFECT_SOURCE` invisible SUR CE PORTEUR -- raison de plus pour
    ecrire ce que le decompile declare plutot que ce que la mesure ne peut pas separer.

    Le tirage des `Randomize` et les coups se font DANS `ectx`, donc sur le MEME `state.rng` que le
    reste du tour."""
    instruments_of_vengeance_attack_tree(_nb_summons(state, unit_id)).execute(entities, ectx)
    # LES ETAGES du coup, pas seulement son total (meme diag que les trois autres phases 2).
    dmg = [{"target": p.get("target"), "total": (p.get("attack") or {}).get("total"),
            "etages": {k: (p.get("attack") or {}).get(k) for k in
                       ("base_min", "base_max", "pierce", "armor", "did_block", "did_crit",
                        "crits", "rolls", "per_hit", "per_hit_health",
                        "clean_min", "clean_max", "hp_before", "hp_after")}}
           for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
    removed = [{"effect": p.get("effect_type"), "target": p.get("target"),
                "removed": p.get("removed")}
               for n, p in ectx.emitted if n == "RemoveEffect"]
    spawned = [p for n, p in ectx.emitted if n == "Spawn"]
    cleared = [p for n, p in ectx.emitted if n == "ClearAllPersistentData"]
    return {"ability": "InstrumentsOfVengeance_PendingAttack", "phase": 2, "attacker": int(unit_id),
            "damage": dmg, "removed": removed, "spawned": spawned, "cleared": cleared}


TRIGGERED_ABILITY_BEHAVIOURS[IOV_ATTACK] = _instruments_of_vengeance_attack_behaviour


# =================================================================================================
# PAS DE SECOND CHEMIN DE DECLENCHEMENT -- et c'est une LECTURE, pas un oubli
# =================================================================================================
# Contrairement a `TheLionsWrath_PendingAttackEffect` (qui declare son propre
# `$$CreateHandleTriggerAbilitiesInternal` et ajoute un `Triggered(On(0x25 = UnitRemoved) &
# get_OwnerIsTarget, ...)`), la table de symboles ne publie pour
# `Idun.Source.IdunBattle.Logic.Entities.Effects.Loki.InstrumentsOfVengeance_PendingAttackEffect`
# que TROIS corps : `$$.ctor`, `$$GetAttackingUnitSelector` et `$$GetTriggeredAbilityType`.
#
# ⚠ Une absence de la table ne prouve rien en general (les corps triviaux sont dedupliques et n'ont
# qu'un seul proprietaire). Elle vaut ICI parce que le TEMOIN est present : la surcharge homologue
# de `TheLionsWrath` EST publiee, sur le meme build et pour la meme methode. Le seul chemin de
# declenchement porte est donc celui de la BASE `APendingAttackEffect` -- `PendingAttackOnAttackersTurn`,
# inscrit par `pending_attack_registry_entries()` DERIVE de `PENDING_ATTACK_EFFECTS`. Ecrire ici un
# second `EffectTrigger` inventerait un chemin que le natif n'a pas.
