"""`HeavyWarpFlamer_AttackTracking` (`TriggeredAbilityType` 0x60a = 1546) -- LE COMPTEUR DE COUPS
PSYCHIQUES ALLIES du `1227 HeavyWarpFlamer` de `thousSekhetar` (#523-r1).

#523 a porte la face EXECUTION de l'ACTIVE 1227 et a laisse son compteur a ZERO : le noeud de
LECTURE (`HeavyWarpFlamerAbility$$GetNumExtraHits`, `abilities/thousandsons.py`) interroge deja le
`PersistentDataComponent`, mais RIEN ne l'ecrivait -- `GetPersistentDataFormula$$Calculate` rendait
son `out` par defaut = 0 et `GetNumTotalHits` valait `nrOfHits`. Ce module est l'ECRITURE.

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c` -- decompile = verite)
================================================================================================
Slots `DSLSelectors` : `+0x30 Owner`. Slots `DSLFormulas` (lus dans
`IdunBattleLogic.Entities.DSLFormulas$$.ctor`) : `+0x18 Direct(0) · +0x20 Direct(1) · +0x28 Direct(2)
· +0x30 Direct(100) · +0x38 Direct(-1)`. `<DSLTriggers+0x28>` = `IsTurnOf(Owner)` (identification de
`docs/rl/case-366-r1-turnof-all.md` SS2 : `InitializeShared` construit ce slot avec
`DSLSelectors+0x30 = Owner` et l'etat).

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.HeavyWarpFlamer_AttackTrackingAbility$$CreateTrigger`
(les deux `On` portent `ownerNeedsToBeAlive = 1`, LU a l'assembleur : `mov r8b,1`) :

      ( On(EventTriggerType.Attack = 9, ownerNeedsToBeAlive = 1)
        & <DSLTriggers+0x28 = IsTurnOf(Owner)>
        & NOT AreEqual(Attacker, Owner@DSLSelectors+0x30)
        & AreFriends(Attacker, Owner@+0x30, comparisonType = 0, anyEntity = 0)
        & CurrentAttackDamageProfilesContain(DamageProfileType.Psychic = 0xd,
                                             includeNotApplied = 0) )
    | On(EventTriggerType.TurnEnd = 0x17, ownerNeedsToBeAlive = 1)

`...$$CreateBehaviour(abilityState, triggerType)` :

    if (triggerType == 0x17)                                        # la branche TurnEnd
        return ClearPersistentData( AbilityOrEffect(0x4cb), Owner@+0x30, "PSYCHIC_ATTACKS_KEY" )
    return SetPersistentData( AbilityOrEffect(0x4cb), Owner@+0x30, "PSYCHIC_ATTACKS_KEY",
                              Sum( GetPersistentData(AbilityOrEffect(0x4cb), Owner@+0x30,
                                                     "PSYCHIC_ATTACKS_KEY"),
                                   <DSLFormulas+0x20 = Direct(1)> ) )

TROIS LECTURES QUI NE SE DEVINENT PAS
-------------------------------------
1. **L'`AbilityOrEffect` inscrit par la TRIGGERED est le litteral `0x4cb` = 1227 -- l'id de
   l'ACTIVE, PAS son propre 1546.** Le decompile ne le montre pas (ghidra perd le registre dans les
   trois `AbilityOrEffect$$op_Implicit`) ; il est LU a l'assembleur :
   `...HeavyWarpFlamer_AttackTrackingAbility$$CreateBehaviour+0x49` porte `mov edx, 0x4cb`, pose
   AVANT le `cmp edi, 0x17` -- donc PARTAGE par les deux branches (la branche `TurnEnd`, a
   `+0x187`, entre directement sur `mov rdi,[rax+0x78]` sans re-charger `edx`). Le lecteur cote
   ACTIVE, lui, porte `mov edx,[rbx+0x10]` (`...HeavyWarpFlamerAbility$$GetNumExtraHits+0x4a`), le
   champ de type de l'active = 1227 aussi. Les deux cotes adressent donc la MEME cle composite
   `(1227, "PSYCHIC_ATTACKS_KEY")` -- `AbilityOrEffect$$GetPersistentDataId` rend l'ordinal du
   premier de ses trois `Nullable` renseigne. Ecrire `1546` rendrait le mecanisme INERTE, **sans
   aucune erreur**.
2. **La `dataKey` est la chaine `"PSYCHIC_ATTACKS_KEY"`.** Le decompile n'affiche qu'un
   `DAT_183370b30` (slot de litteral IL2CPP), resolu par
   `data/symbols/rnca9r7q6c/metadata/string_literals.tsv` ligne `13388 0x3370b30
   "PSYCHIC_ATTACKS_KEY"`. Les xrefs du slot sont EXHAUSTIVEMENT les deux fonctions de la paire.
3. **La feuille est `SetPersistentData`, PAS `AddPersistentData`** -- deux classes natives
   distinctes, dans deux namespaces distincts, a deux adresses distinctes
   (`IdunBattle.Entities.Behaviours.SetPersistentDataBehavior$$Execute` vs
   `IdunBattle.Entities.Triggers.AddPersistentDataBehavior$$Execute`), et la sequence d'appels les
   separe : la seconde RELIT par `PersistentDataComponent$$TryGetPersistData<T>` avant d'ecrire, la
   premiere ECRIT seulement. C'est le noeud VALEUR (`Sum(GetPersistentData(...), Direct(1))`) qui
   porte ici l'increment -- pas la feuille. Confondre les deux double-compterait.

LE CHEMIN DE MONTAGE : `activeAbilities` -> triggered DERIVEE
-------------------------------------------------------------
1546 n'a **aucune entree de gameconfig** et `thousSekhetar` ne la liste ni en `passiveAbilities`
(il n'y porte que `PropheticSentinel`) ni ailleurs. Elle arrive par
`IdunBattle.Entities.Factories.UnitFactory$$AddDerivedAbilities`, qui pour chaque ability ACTIVE de
l'unite fait `if (StaticBattleRules.ActiveAbility$$HasDerivedTriggeredAbilities(t))
TriggeredAbilityComponent$$TryAdd(GetDerivedTriggeredAbilities(t))`. Le dictionnaire statique est
peuple par `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.ActiveAbility$$.cctor`
et le couple y est LU verbatim dans le motif d'insertion (valeur ecrite en `[rbp+0x18]`, cle en
`[rbp+0x20]`, puis `Dictionary.Add`) : `... 0x60a -> 0x4cb ...`, encadre par ses voisins deja portes
`0x5e3 -> 0x4be` (1507 Hailstrike_Attack <- 1214 Hailstrike) et `0x613 -> 0x4d0`
(1555 EmpyricAmbush_Reset <- 1232 EmpyricAmbush). C'est donc le TROISIEME chemin de registration du
port -- `ACTIVE_ABILITY_TRIGGERS["HeavyWarpFlamer"]`, celui de ses deux voisins.

DOCTRINE #149 -- ou passe la frontiere
--------------------------------------
`CreateTrigger` est COLLAPSE imperativement dans `matches` (lecture d'etat pure : tour courant,
identite de l'attaquant, camp, profils du coup -- meme choix que `NeuroparasiteAbility`, l'autre
consommateur porte de ce vecteur avec le MEME conjoint `CurrentAttackDamageProfilesContain(0xd)`).
`CreateBehaviour` est un ARBRE DSL : deux feuilles (`SetPersistentData` / `ClearPersistentData`)
au-dessus du `PersistentDataComponent`, et le noeud VALEUR `Sum(GetPersistentData(...), Direct(1))`
est un vrai arbre -- il n'est PAS pre-calcule en Python.

DEUX CLASSES DE PORT POUR UNE SEULE CLASSE NATIVE
-------------------------------------------------
Le natif a UNE classe dont le `CreateTrigger` est une DISJONCTION sur deux events et dont le
`CreateBehaviour` branche sur `triggerType`. Le registre du port est indexe PAR `event_id` : il faut
donc deux entrees, une par disjoint -- exactement le patron `HaywireMinePlaceOnMove` /
`HaywireMinePlaceOnTurnEnd`. Les deux portent le MEME `TRIGGERED_ABILITY_ID` (1546) et la MEME cle
persistante (1227, "PSYCHIC_ATTACKS_KEY").

RESIDUS NOMMES
--------------
* `IdunBattleLogic.Entities.DSLSelectors$$Attacker` -- RESOLU par #523-r4, et il vit desormais dans
  son FOYER UNIQUE `triggers/base.py::attacker_of` (ce module ne le collapse plus). Le sélecteur est
  CONDITIONNEL : `If( AreEqual(<DSLSelectors+0x98>, DirectAbilitySelector(0x434 =
  MV71SniperDroneSquadAttack)), ParentSelector(Caster@+0x48), Caster@+0x48 )`. Sur CE porteur la
  branche MV71 est INERTE (le drone et son parent sont dans la meme equipe, donc `AreFriends` ne
  discrimine pas, et `AreEqual(Attacker, Owner)` ne differerait que si `thousSekhetar` etait le
  parent du drone) : cf. la docstring du foyer, qui porte la RE complete et la raison du
  NON CONFRONTE. Les XREFS du selecteur donnent ses QUATRE consommateurs natifs -- `ShieldOfFaith`,
  `LifeStealEffect`, `HeadwoppasKillchoppaEffect` et celui-ci ; les trois premiers ne sont PAS
  portes, donc le rayon de souffle du residu vaut aujourd'hui EXACTEMENT ce module.
* `AreFriends(..., comparisonType = 0, anyEntity = 0)` : `anyEntity = 0` selectionne l'une des deux
  classes de `AreFriendsAbilityTrigger` construites par `DSLTriggers$$AreFriends` ; le port ne
  modelise que la comparaison d'equipe (`comparisonType = 0 = ByCurrentTeam`, meme collapse que
  `AreEnemies(..., 0)` de `haywire_mine.py`).
* Le compteur est PLAFONNE en LECTURE (`Min(..., maxNrOfHits - nrOfHits)` dans
  `HeavyWarpFlamerAbility$$GetNumExtraHits`), jamais en ECRITURE : ce module ecrit un entier non
  borne, comme le natif.
"""
from __future__ import annotations

from typing import Optional

from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.active_ability_type import ActiveAbilityType
from .....entities.damage_profile_type import DamageProfileType
from .....entities.formulas import GetPersistentData, Sum
from .....entities.selectors.accessors import Owner
from .....entities.triggered_ability_type import TriggeredAbilityType
from ....abilities.behaviours.context import entities_from_state
from ....abilities.behaviours.persistent_data import ClearPersistentData, SetPersistentData
from ....components import OwnerComponent
from ....state import State
from ..base import TriggeredAbility, TriggerEvent
# FORME B (`import <module>` puis `<module>.<nom>`) pour le FOYER `attacker_of`, et non
# `from ..base import attacker_of` : un binding fige au chargement NE MORD PAS sous
# `monkeypatch.setattr(...)` (CLAUDE.md, les 28 fichiers rouges de #484). Le foyer est le SEUL
# point ou la branche MV71 de `DSLSelectors$$Attacker` est substituable, donc le seul par lequel
# une garde peut prouver que ce module le CONSOMME au lieu de re-collapser.
from .. import base as _tb

#: `AbilityOrEffect(0x4cb)` -- l'id de l'ACTIVE, ecrit par la TRIGGERED (cf. lecture n.1 de l'en-tete).
HEAVY_WARP_FLAMER = int(ActiveAbilityType.HeavyWarpFlamer)                  # 0x4cb = 1227
#: `TriggeredAbilityType` de CETTE classe -- l'id sous lequel le natif l'execute, PAS la cle du sac.
ATTACK_TRACKING_ID = int(TriggeredAbilityType.HeavyWarpFlamer_AttackTrackingAbility)   # 0x60a = 1546
#: `DAT_183370b30`, resolu par `data/symbols/rnca9r7q6c/metadata/string_literals.tsv` (cf. lecture n.2).
STACK_KEY = "PSYCHIC_ATTACKS_KEY"
#: `CurrentAttackDamageProfilesContain(0xd, includeNotApplied = 0)`.
PSYCHIC = int(DamageProfileType.Psychic)                                   # 0xd = 13
#: `<DSLFormulas+0x20>` -- l'increment. `DSLFormulas$$.ctor` alloue `0/1/2/100/-1` aux slots
#: `+0x18/+0x20/+0x28/+0x30/+0x38`, donc ce champ vaut 1.
INCREMENT = 1


def attack_tracking_increment_tree() -> SetPersistentData:
    """Branche `triggerType != 0x17` de
    `...HeavyWarpFlamer_AttackTrackingAbility$$CreateBehaviour` -- ARBRE 1:1 :

        SetPersistentData( AbilityOrEffect(0x4cb = 1227), Owner@DSLSelectors+0x30,
                           "PSYCHIC_ATTACKS_KEY",
                           Sum( GetPersistentData(AbilityOrEffect(0x4cb), Owner@+0x30,
                                                  "PSYCHIC_ATTACKS_KEY"),
                                <DSLFormulas+0x20 = Direct(1)> ) )

    Le `Sum(GetPersistentData(...), 1)` est un NOEUD, pas un calcul Python fait avant : c'est lui qui
    porte l'increment, la feuille `SetPersistentData` n'ECRASANT que ce qu'on lui donne (cf. lecture
    n.3 de l'en-tete). Rendu par une USINE pour rester INSPECTABLE par un garde offline."""
    return SetPersistentData(
        HEAVY_WARP_FLAMER, Owner(), STACK_KEY,
        Sum(GetPersistentData(HEAVY_WARP_FLAMER, Owner(), STACK_KEY), Const(INCREMENT)))


def attack_tracking_clear_tree() -> ClearPersistentData:
    """Branche `triggerType == 0x17 = TurnEnd` du MEME `CreateBehaviour` :

        ClearPersistentData( AbilityOrEffect(0x4cb = 1227), Owner@DSLSelectors+0x30,
                             "PSYCHIC_ATTACKS_KEY" )

    `Dictionary.Remove` (no-op sur cle absente) -> le compteur repart de 0 au tour suivant, et
    `GetPersistentDataFormula$$Calculate` rend alors son `out` par defaut = 0."""
    return ClearPersistentData(HEAVY_WARP_FLAMER, Owner(), STACK_KEY)


class HeavyWarpFlamerAttackTrackingAbility(TriggeredAbility):
    """1er disjoint : `On(9 = Attack, ownerNeedsToBeAlive = 1) & IsTurnOf(Owner)
    & NOT AreEqual(Attacker, Owner) & AreFriends(Attacker, Owner) &
    CurrentAttackDamageProfilesContain(Psychic)` -> `SetPersistentData(..., Sum(Get, 1))`.

    OBSERVABLE : chaque attaque d'un ALLIE du porteur (jamais du porteur lui-meme) dont les profils
    contiennent `Psychic`, jouee PENDANT le tour de l'equipe du porteur, ajoute 1 au compteur
    `(1227, "PSYCHIC_ATTACKS_KEY")` -- donc 1 coup au prochain `HeavyWarpFlamer`, jusqu'au plafond
    `maxNrOfHits - nrOfHits` applique EN LECTURE par `GetNumExtraHits`."""
    event_id = int(EventTriggerType.Attack)                    # `On(9)`
    TRIGGERED_ABILITY_ID = ATTACK_TRACKING_ID                  # 0x60a = 1546

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `<DSLTriggers+0x28>` = `IsTurnOf(Owner)` -> `IdunBattle.Entities.Triggers.IsTurnOfUnitTrigger`.
        # Le vecteur `On(9)` ne threade PAS `ev.player_id` (il n'est pose que par les vecteurs de
        # TOUR), donc la source est `state.current_player_id` -- meme repli que
        # `wireweave_net._is_turn_of_owner`, qui prefere lui aussi `ev.player_id` quand il existe.
        pid = ev.player_id if getattr(ev, "player_id", None) is not None \
            else state.current_player_id
        if pid is None:
            return False
        ow = state.get_entity(int(self.owner_id))
        oc = ow.get_component(OwnerComponent) if ow is not None else None
        if oc is None or oc.player is None or int(oc.player) != int(pid):
            return False
        # `Attacker` -- selecteur CONDITIONNEL, desormais porte dans son FOYER UNIQUE
        # (`triggers/base.py::attacker_of`, #523-r4) : hors du cas MV71 il rend le caster de
        # l'attaque (`ev.actor_id`, inchange) ; sur une attaque du drone `MV71SniperDroneSquad` il
        # rend son PARENT. La branche MV71 est INERTE sur CE porteur -- cf. la docstring du foyer,
        # qui dit pourquoi et ce qu'il faudrait pour la confronter.
        attacker = _tb.attacker_of(state, ev)
        if attacker is None:
            return False
        # `NOT AreEqual(Attacker, Owner@+0x30)` -- le porteur ne se compte JAMAIS lui-meme.
        if int(attacker) == int(self.owner_id):
            return False
        # `AreFriends(Attacker, Owner@+0x30, 0 = ByCurrentTeam, 0)`.
        ae = state.get_entity(int(attacker))
        ac = ae.get_component(OwnerComponent) if ae is not None else None
        if ac is None or ac.team is None or oc.team is None or ac.team != oc.team:
            return False
        # `CurrentAttackDamageProfilesContain(0xd = Psychic, includeNotApplied = 0)` ->
        # `IdunBattle.Entities.Triggers.DamageProfilesContainsTrigger$$ShouldTrigger` =
        # `<liste des profils de l'attaque>.Contains(this+0x10)` (liste NULLE -> false). Cote port
        # c'est `ev.profiles`, le SET des profils de TOUTE l'attaque (arme + coups bonus #179) ;
        # repli sur `ev.profile` seul quand le canal n'est pas renseigne, meme convention que
        # `neuroparasite._profiles_contain`.
        name = DamageProfileType(PSYCHIC).name
        got = ev.profiles if ev.profiles is not None else ({ev.profile} - {None})
        return name in got

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        ectx = ExecutionContext(state=state, rng=state.rng)
        # `BaseTriggeredAbility$$Execute` monte l'`AbilityEntities` sur SON porteur : owner == caster
        # == le porteur (c'est ce que `Owner@+0x30` resout). `actor` = l'attaquant du vecteur.
        entities = entities_from_state(state, int(self.owner_id), int(self.owner_id),
                                       actor_id=int(ev.actor_id))
        attack_tracking_increment_tree().execute(entities, ectx)
        posees = [p for n, p in ectx.emitted if n == "SetPersistentData"]
        if not posees:
            return None
        return {"ability": "HeavyWarpFlamer_AttackTracking", "owner": int(self.owner_id),
                "attacker": int(ev.actor_id), "key": STACK_KEY,
                "stacks": int(posees[-1].get("value") or 0), "dsl": True}


class HeavyWarpFlamerAttackTrackingResetAbility(TriggeredAbility):
    """2e disjoint : `On(0x17 = TurnEnd, ownerNeedsToBeAlive = 1)`, **SANS aucun predicat
    supplementaire** -> `ClearPersistentData(1227, Owner, "PSYCHIC_ATTACKS_KEY")`.

    Le disjoint natif est un `On(...)` NU : ni `get_OwnerIsActor`, ni `IsTurnOf(Owner)` (le slot
    `+0x28` n'est conjoint qu'a la branche `On(9)`, ce qui se lit dans l'ordre des `op_BitwiseAnd`
    du decompile -- le `op_BitwiseOr` final n'agrege que `On(0x17)`). Le compteur est donc vide a
    CHAQUE fin de tour, y compris celle de l'equipe adverse -- meme forme que
    `UntilOfEndTurnEffect$$CreateRemoveEffectTrigger`. Ce n'est pas une simplification : sur ce
    porteur l'observable est le meme (le compteur ne se remplit que pendant le tour de l'equipe du
    porteur, et il est deja vide a la fin de CE tour-la), mais on ecrit ce qui est LU."""
    event_id = int(EventTriggerType.TurnEnd)                   # `On(0x17)`
    TRIGGERED_ABILITY_ID = ATTACK_TRACKING_ID                  # 0x60a = 1546

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        return True                       # `On(0x17)` NU (cf. docstring)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, int(self.owner_id), int(self.owner_id))
        attack_tracking_clear_tree().execute(entities, ectx)
        vides = [p for n, p in ectx.emitted if n == "ClearPersistentData"]
        avait = bool(vides and any(v.get("avait") for v in (vides[-1].get("vides") or [])))
        return {"ability": "HeavyWarpFlamer_AttackTracking", "owner": int(self.owner_id),
                "cleared": True, "avait": avait, "dsl": True}
