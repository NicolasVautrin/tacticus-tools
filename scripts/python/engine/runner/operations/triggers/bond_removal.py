"""Le RETRAIT herite d'`IdunBattle.Entities.Effects.ABondEffect` (#462-r4b-r1-r1-r1-r1).

`IdunBattle.Entities.Effects.ABondEffect$$CreateHandleTriggerAbilitiesInternal` construit JUSQU'A
TROIS `Triggered()` de `RemoveEffect`, communs a TOUTES les classes d'effet BOND. Chacun est sous un
appel VIRTUEL de la classe d'effet -- c'est le virtuel, et lui seul, qui decide si le trigger entre
dans l'`ArraySet` :

    (a) <klass+0x748>() : bool  ->
          Triggered( NOT AmountIsZero(BondedEntityFromEffect(Effect@DSLSelectors+0x38))
                     & ( On(2 = PreUnitDeath_2) | On(0x25 = UnitRemoved) )
                     & IsEntityWithIdTarget(BondedEntityFromEffect(...)),
                     RemoveEffect(Effect@0x38) )

    (b) <klass+0x728>() : Nullable<int> ; si HasValue ->
          Triggered( NOT IsInRange(Owner@DSLSelectors+0x30, BondedEntity, Direct(value))
                     & NOT AmountIsZero(BondedEntity) & On(0x1d = UnitPositionChanged_2),
                     RemoveEffect(Effect@0x38) )

    (c) <klass+0x738>() : bool  ->
          Triggered( NOT IsAdjacent(Owner@0x30, BondedEntity, 3)
                     & NOT AmountIsZero(BondedEntity) & On(0x1d),
                     RemoveEffect(Effect@0x38) )

================================================================================================
1. LES TROIS VIRTUELS SONT NOMMES -- au RUNTIME, parce que les tables ne pouvaient pas le dire
================================================================================================
`probe_462_r4b_r1_r1_r1_r1_bond_removal.py --step vtable` lit les slots sur l'instance et rend le
`il2cpp_method_get_name` de chacun :

    +0x728 = `get_Range`                        (`System.Nullable<System.Int32>`)
    +0x738 = `get_Adjacent`                     (`System.Boolean`)
    +0x748 = `get_RemoveOnBondedEntityDeath`    (`System.Boolean`)

⚠ Ce pas ne CONCLUT pas seul : une vtable IL2CPP n'est materialisee qu'apres
`il2cpp_runtime_class_init`, et la BASE `ABondEffect` -- abstraite, jamais instanciee -- rend le
stub de remplissage paresseux (`Unity.Burst.Unsafe$$AsRef`, qui ne retourne pas) pour les trois
slots. Comparer a elle serait comparer a du bruit. C'est `--step declared` qui conclut : il enumere
`class_get_methods` NIVEAU PAR NIVEAU de la chaine de parents, et une classe qui SURCHARGE declare
son propre `MethodInfo` meme quand IL2CPP a DEDUPLIQUE le corps (le `methodPointer` est partage,
l'entree de la classe ne l'est pas). C'est exactement ce que `frida/methods.tsv` -- indexee par
ADRESSE -- ne peut pas montrer.

Les trois corps triviaux, resolus par leur ADRESSE au decompile (les noms ghidra qui y sont
attaches, `UnityEngine.U2D.IK.Solver2D$$DoValidate` et consorts, sont ceux du proprietaire
ARBITRAIRE du corps partage -- ils ne disent RIEN de l'appelant) :

    `0x1802b4590` = `return 1`   -> bool TRUE
    `0x1802b45a0` = `return 0`   -> bool FALSE
    `0x1802b45b0` = `return 0`   -> `Nullable<int>` VIDE (pas de portee)

================================================================================================
2. LE GATE `NOT AmountIsZero(BondedEntity)` MORD -- et la lecture LITTERALE dit le contraire
================================================================================================
`IdunBattleLogic.Entities.DSLTriggers$$AmountIsZero(selector)` construit
`NOT AmountIsGreaterAbilityTrigger(selector, <DSLFormulas+0x20>)`, et
`IdunBattle.Entities.Conditions.AmountIsGreaterAbilityTrigger$$ShouldTrigger` rend
`minAmount < amount`. Or `<DSLFormulas+0x20>` vaut **1**, pas 0 :

  * `IdunBattleLogic.Entities.DSLFormulas$$.ctor` ecrit `+0x18 <- Direct(0)`, `+0x20 <- Direct(1)`,
    `+0x28 <- Direct(2)`, `+0x30 <- Direct(100)`, `+0x38 <- Direct(-1)` ;
  * `IdunBattleLogic.Entities.DSLTriggers$$AmountIsGreaterThanZero`, lui, lit `+0x18` -- son nom
    colle donc a `minAmount = 0`, et `AmountIsZero` lit bien un AUTRE slot ;
  * `IdunBattle.Entities.Effects.Loki.NeuroparasiteEffect$$GetIncreaseLevelBehaviour` passe
    exactement `+0x20` en 2e argument d'`IdunBattleLogic.Entities.DSLBehaviors$$IncreaseEffectLevel`
    (`effect, amount, max`), et #556 a MESURE live niveau 1 -> 2. `+0x20` vaut 1.

Et `IdunBattle.Entities.Selectors.SelectBondedEntityFromEffectSelector$$Select` rend AU PLUS UN
element : il prend `Enumerable.First` du selecteur d'effet, lit le `BondedEntityId` du composant de
bond, resout l'entite, et passe par `IdunBattleLogic.Extensions.TExtensions$$ToList<T>` -- dont le
corps fait UN SEUL `List<T>.Add`, sans boucle. Sinon il rend une liste VIDE.

Litteralement, `AmountIsZero(x) == (count(x) <= 1)` serait donc TOUJOURS vrai sur ce selecteur, et
`NOT AmountIsZero` TOUJOURS faux : les trois triggers seraient structurellement morts.

**LA MESURE REFUTE CETTE LECTURE.** `--step killlive`, runner `MC1_67`, Neurothrope patche a 1000
PV, victime a 400000 de degat :

    mort d'une unite TIERCE (`ultraCalgar`, notre camp) -> parasite 1218 PRESENT (level 1)
    mort du BONDE (le Neurothrope)                      -> parasite 1218 ABSENT

Et le retrait n'est attribuable a AUCUN autre chemin : `IdunBattle.Operations.RemoveEffectsOperation$$Execute`
-- la voie qu'empruntent `IdunBattle.Operations.KillUnitOperation$$RemoveEffects` et l'etape 14 de
`IdunBattle.Operations.RemoveUnitOperation$$Execute` -- lit la liste des effets sur le composant
d'effets de l'unite QUI MEURT (champ `+0x10`), c'est-a-dire les effets qu'elle PORTE. Le parasite,
lui, est porte par la VICTIME, qui ne meurt pas. Il n'existe aucun nettoyage natif << par SOURCE >>.

⇒ Le port mirrore la semantique MESUREE : `NOT AmountIsZero(BondedEntity)` = << l'entite bondee est
encore resoluble dans l'etat >>. La reconciliation exacte avec le litteral `<DSLFormulas+0x20>` = 1
n'est PAS tranchee -- residu nomme `#462-r4b-r1-r1-r1-r1-r1`. Elle ne change rien au comportement
porte : sur les deux vecteurs `On(2)` et `On(0x25)` le bonde est encore dans l'etat (l'event part
AVANT la consommation des effets, cf. `remove_unit.py` etape 13), donc les deux lectures possibles
du gate coincident sur tout ce qui est confrontable ici.

================================================================================================
3. LA TABLE -- ce qu'elle contient, et pourquoi PAS PLUS
================================================================================================
La cle est l'`EffectType` du PORT ; la valeur est la mesure `--step declared` de la classe NATIVE
correspondante. N'y entrent que les effets de bond que le port POSE (call-sites `AddBondEffect`) ET
dont la classe native est ETABLIE par une preuve directe -- jamais par ressemblance de nom, qui
serait fausse (`EffectType.Taunted_OnlySpecificTargets` est servi par `TauntedEffect`,
`EffectType.ValkyrieStrike_Effect` par `ValkyrieStrikeEffect`).

RESIDUS NOMMES, explicitement HORS table (aucun trigger pose pour eux -- statu quo) :

  * **Les 20 derivees d'`IdunBattle.Entities.Effects.APendingAttackEffect`** : RESOLUES
    (#462-r4b-r1-r1-r1-r1-c). Elles heritent toutes de
    `IdunBattle.Entities.Effects.APendingAttackEffect$$get_RemoveOnBondedEntityDeath`, dont le corps
    est `NOT <klass+0x778>()`. Ce QUATRIEME virtuel est NOMME `IsExecutedIfOwnerDies`, mesure par
    `--step pending` (voie `class_get_methods`, qui n'exige aucune initialisation) et recoupe sur
    vtable materialisee, controle d'alignement passe. Les 20 le DECLARENT en propre : **17 a `false`**
    (donc `get_RemoveOnBondedEntityDeath` VRAI) et **3 a `true`** -- `AnnihilatorBeam`,
    `TargetingProtocols` et `ValkyrieStrike`, donc gate (a) FAUX.
    La sous-famille herite par ailleurs `get_Range` = `Nullable` VIDE et `get_Adjacent` = `false`
    d'`APendingAttackEffect`, qui les surcharge : **ni (b) ni (c) sur aucune des 20**.
    Des trois que le port POSE, seul `ValkyrieStrike_Effect` (1022) entre dans la table ci-dessous.
    Les deux autres restent HORS table, et pas par prudence -- par mesure :
      - `MalleusRocketLauncher` (1308) et `DevastatingRefrain_Target` (1402) ont pour `bondedEntity`
        l'owner du cast, c'est-a-dire une MACHINE OF WAR. `--step pendingporteurs` mesure que cette
        entite est de type `Machine`, `pos=None`, absente de `decisionView.units` et cible legale
        d'AUCUNE attaque : sa mort n'est pas atteignable. Le trigger (a) est CONSTRUIT cote natif et
        INATTEIGNABLE -- l'inscrire serait du code que rien ne peut invalider.
      - S'y ajoute une raison structurelle, suffisante a elle seule : leurs call-sites ne passent
        pas `bonded_ref`, donc `BaseEffect.bonded` reste `None` et `matches` rendrait `False`.
        ⚠ Une TROISIEME raison etait invoquee ici -- << ces effets vivent sur des TUILES alors que
        `collect_effect_triggers` itere `effects.by_unit` >> -- et elle est LEVEE
        (#462-r4b-r1-r1-r1-r1-c-r1) : `by_unit` est clee par id d'ENTITE, donc le collecteur voyait
        deja les tuiles ; c'etait le gate d'owner du dispatch, corrige depuis. Le verdict NON
        CONFRONTABLE tenait deja sur chacune des deux autres raisons.
    ⚠ Ces effets ne sont pas pour autant sans retrait : `APendingAttackEffect$$CreateHandleTriggerAbilitiesInternal`
    ajoute son PROPRE `Triggered( On(0x15) & IsTurnOf(<0x758>()), TriggerAbility(...) &
    RemoveEffect(Effect) )` -- le retrait au declenchement de l'attaque differee, qui est un AUTRE
    foyer que celui-ci. Ce foyer-la est le RETRAIT EFFECTIF de ces trois effets, et il MORD :
    mesure du 2026-08-05, un seul `endturn` apres le cast fait disparaitre 1022 de sa tuile SANS
    qu'aucun bonde ne soit mort. C'est ce qui rend le gate (a) doublement sans consequence ici.
  * **`Taunted_BlockMovement` (25) et `Taunted_CantUseAbility` (26)**, enfants du composite 27 : la
    classe native qui les sert n'est pas etablie (le ctor `IdunBattle.Entities.Effects.TauntedEffect$$.ctor`
    ne porte pas d'`EffectType` -- il vient de la lambda d'`IdunBattle.Core.Services.EffectsDatabase$$InitializeEffects`,
    non lue). Les inscrire par ressemblance serait une hypothese, pas une lecture.

================================================================================================
4. LE TRIGGER (b) `get_Range` -- PORTE, et CONFRONTE (#462-r4b-r1-r1-r1-r1-b)
================================================================================================
Mesure `--step declared` sur les 37 classes de la famille (rejouable par
`probe_462_r4b_r1_r1_r1_r1_b_bond_range.py --step declared`) :

  * (b) arme sur `IdunBattle.Entities.Effects.TauntedEffect`,
    `IdunBattle.Entities.Effects.Taunted_RefreshUnitTurnFinishedEffect`,
    `IdunBattle.Entities.Effects.BlockUnitMovementBondEffect` et
    `Idun.Source.IdunBattle.Logic.Entities.Effects.Loki.MindControl_TaunterEffect` -- les QUATRE
    rendent `Nullable<int>(1)` (corps LUS : `System.Nullable..ctor(&ret, 1)`).
  * (c) arme sur `IdunBattle.Entities.Effects.Loki.HolyDuel_TauntEffect` et sur elle seule.
  * `IdunBattle.Entities.Effects.Loki.HazeOfCorruption_DamageTransferEffect` porte les DEUX en
    CHAMPS (`get_Range` = `this+0x480`, `get_Adjacent` = `this+0x488`) -- et son ctor n'ecrit NI
    l'un NI l'autre, donc `Nullable` vide et `false` : ni (b) ni (c).

CE QUI A DEBLOQUE LA CONFRONTATION. La passe precedente concluait << inobservable >> : le taunt de
`CrushingClaws` (1105) dure `TurnsFromRounds(1)` et tombe au DEUXIEME `endturn`, et son porteur ne
peut pas MARCHER (le composite pose `Taunted_BlockMovement`). Le montage qui tranche n'attend AUCUN
tour et ne fait marcher PERSONNE : une SECONDE unite du meme camp caste `MortisRound` (1004), dont
l'arbre porte `PushUnit(Caster(), Target())`. Le push emet `On(0x1d)` cote natif
(`IdunBattle.Operations.DisplaceUnitOperation$$EventAndAbilitiesAndEffects` : 0x24 -> 0x23 -> 0x1d)
et change la distance -- les deux ingredients du trigger, dans le tour du cast.

Le DISCRIMINANT est la GEOMETRIE du pousseur, pas un parametre du montage. Le push envoie le taunte
en `V - e` (a l'oppose du pousseur), donc `dist(V - e, T) = |e + t|` : pousseur a 1 cran du taunteur
-> distance 2 (HORS portee) ; a 2 crans -> distance 1 (ENCORE a portee). Les deux bras jouent le
MEME geste a une tuile pres.

MESURE (2026-08-05, board `MC1_67`, `tyranTyrantGuard` + `ultraEliminatorSgt` vs `blackPossession`
a 400000 PV, aucun `endturn`) :

    bras ELOIGNE : push (1,1)->(0,0), dist 1 -> 2 ; taunt [25,26,27,1237] -> []      <- RETIRE
    bras PROCHE  : push (1,1)->(0,1), dist 1 -> 1 ; taunt [25,26,27,1237] -> [ide]   <- GARDE

C'est le PARENT qui tombe : les trois sous-effets partent avec lui (`RevertInternal`). Si seul
`Taunted_RefreshUnitTurnFinishedEffect` (1237) avait porte le trigger, 27 serait reste -- la mesure
ATTRIBUE donc `EffectType 27` a une classe qui arme (b), et parmi les quatre c'est `TauntedEffect`
(la seule dont `ApplyInternal` pose ces trois sous-effets ET la liste de cibles forcees, #436).

⚠ La BASCULE DE VTABLE, qui avait servi a attribuer les `APendingAttackEffect` (§7.3 de la fiche),
est INUTILISABLE ici : les six classes de la famille etaient DEJA materialisees avant tout cast
(session partagee, runners d'autres agents). Le pas existe (`--step attrib`) et le DIT.

================================================================================================
5. LE TRIGGER (c) `get_Adjacent` -- PORTE depuis que le port POSE 1091
================================================================================================
Seul `HolyDuel_TauntEffect` l'arme, c'est-a-dire l'`EffectType 1091 HolyDuel_Taunt` que pose
`IdunBattleLogic.Entities.Abilities.Active.Loki.HolyDuelAbility$$ExecuteBehaviour` :

    Execute( AddBondEffect(0x443 = 1091, AbilityStateReference, source = Caster@0x48,
                           targets = Target@0x60, bondedEntity = Caster@0x48, options VIDES)
             & UseActiveAbility(caster, target, UnitNormalAttackType(caster), ...) )

Le porteur `templChampion` EST au pool (rank 17), donc la face NATIVE est confrontable et l'est
(`--step holyduellive`). CE QUI A CHANGE : `HolyDuelAbility` (1050) est entree dans
`ABILITY_CLASSES`, donc **le port pose desormais 1091** -- l'objection << vacuously vrai >> qui
tenait ce trigger hors du fichier est levee par la MESURE, pas par un changement d'avis. La ligne
de `BOND_REMOVAL_GATES` porte les trois virtuels tels que `--step declared` les rend :
`get_Range` VIDE (pas de (b)), `get_Adjacent` VRAI (le (c), unique dans toute la famille),
`get_RemoveOnBondedEntityDeath` VRAI (le (a)).

⚠ (c) N'EST PAS (b) A UN SEUIL PRES : `IsInRange` compare une DISTANCE HEX, `IsAdjacent` delegue a
`BattleQuery$$AreEntitiesAdjacent` -> `MovementUtil$$AreTilesAdjacent`, qui porte une PORTE
D'ELEVATION et un COURT-CIRCUIT D'IDENTITE et compare les EMPREINTES COMPLETES. Cf. la docstring
de `BondRemoveOnAdjacencyLost`.
"""
from __future__ import annotations

from typing import NamedTuple, Optional

import hexgeo

from ...state import State
from ...components import UnitComponent
from ...components import get_unit_feet
from ...abilities.behaviours.context import entities_from_state
from ...abilities.behaviours.effects import RemoveEffect
from ....dsl.effects import ExecutionContext
from ....dsl.event_trigger_type import EventTriggerType
from ....entities.effect_type import EffectType
from ....entities.selectors.tiles import Caster
# Foyer UNIQUE de `BattleQuery$$AreEntitiesAdjacent` (porte d'elevation + court-circuit d'identite
# + empreintes completes) -- le MEME que le noeud DSL `entities/triggers.py::IsAdjacent`.
from ....services.battle_query import are_entities_adjacent
from .base import EffectTrigger, TriggerEvent
from ...components import PositionComponent


class BondRemovalGates(NamedTuple):
    """Les virtuels de la classe d'effet NATIVE, tels que
    `probe_462_r4b_r1_r1_r1_r1_bond_removal.py` les a rendus (`--step declared` pour les trois
    premiers, `--step pending` pour le quatrieme).

    `native` = le nom de la classe native, VERBATIM : c'est lui qui rend la ligne re-verifiable
    d'un rejeu du probe, et c'est la seule chose qui relie une valeur a sa mesure."""
    native: str
    remove_on_bonded_entity_death: bool     # `<klass+0x748> get_RemoveOnBondedEntityDeath`
    range: Optional[int]                    # `<klass+0x728> get_Range` -- None = `Nullable` VIDE
    adjacent: bool                          # `<klass+0x738> get_Adjacent`
    # `<klass+0x778> IsExecutedIfOwnerDies` -- N'EXISTE QUE sous
    # `IdunBattle.Entities.Effects.APendingAttackEffect`, qui redefinit
    # `get_RemoveOnBondedEntityDeath` en `NOT <klass+0x778>()` au lieu de rendre une constante.
    # `None` = la classe n'est PAS de cette sous-famille (le gate (a) y est une constante directe).
    # Quand il est renseigne, `remove_on_bonded_entity_death` DOIT en etre la negation --
    # `assert_pending_gate_consistency()` le verifie, pour qu'une des deux valeurs ne puisse pas
    # deriver sans l'autre.
    is_executed_if_owner_dies: Optional[bool] = None


BOND_REMOVAL_GATES: dict[int, BondRemovalGates] = {
    # Pose par `NeuroparasiteAbility$$CreateBehaviour` (#556). Classe native ETABLIE : c'est
    # `NeuroparasiteEffect$$GetIncreaseLevelBehaviour` / `$$GetMaximumLevel` qui portent la montee
    # en niveau de l'effet 1218, mesuree live sur CET effect_type par #556.
    int(EffectType.Neuroparasite): BondRemovalGates(
        "IdunBattle.Entities.Effects.Loki.NeuroparasiteEffect", True, None, False),
    # #963-r3 -- pose par `LifewardsAbility$$CreateBehaviour` (`AddBondEffect(0x424, ...,
    # bondedEntity = Parent(Owner@<DSLSelectors+0x30>))`, donc le bonde est CELESTINE, la mere du
    # summon). Classe native ETABLIE par `frida/classes.tsv` : `LifewardsBondEffect` a pour base
    # `IdunBattle.Entities.Effects.ABondEffect`, et son `$$CreateActiveCondition` est le SEUL corps
    # propre qu'elle porte.
    # MESURE `--step declared` du 2026-08-15 sur le build `t6dpr4k06g` (rejouable) :
    #     LifewardsBondEffect | get_Range = OWN=none | get_Adjacent = OWN=false
    #                         | get_RemoveOnBondedEntityDeath = OWN=true
    #     TRIGGERS DE RETRAIT CONSTRUITS : LifewardsBondEffect -> a
    # ⚠ **CETTE LIGNE EST LA CONTRE-EPREUVE DE << lire le bloc `methodPointers` suffit >>** : ce bloc
    # ne porte que DEUX entrees pour cette classe (`.ctor`, `CreateActiveCondition`), ce qui
    # donnerait a croire qu'aucun des trois gates n'est declare. Un virtuel a corps TRIVIAL est
    # ICF-deduplique -- absent du bloc des CORPS, present dans la METADATA que lit
    # `class_get_methods`. Conclure du bloc seul aurait pose `(False, None, False)`, donc AUCUN
    # retrait : le bond aurait survecu a la mort de Celestine, en silence.
    # OBSERVABLE : Celestine meurt -> le bond 1060 tombe de la Geminae.
    int(EffectType.Lifewards_BondEffect): BondRemovalGates(
        "IdunBattle.Entities.Effects.Loki.LifewardsBondEffect", True, None, False),
    # Pose par `TunnelingHorrorAbility$$ExecuteBehaviour` (#366-r1) sur la TUILE visee,
    # `bondedEntity` = le caster -- qui QUITTE le plateau dans le meme cast
    # (`RemoveUnitFromItsTiles(Caster, true)`, donc `On(0x25 = UnitRemoved)` sur le bonde).
    # `false` n'est donc PAS une valeur inerte : c'est ce qui laisse le marqueur survivre a
    # l'enfouissement du Destroyer. S'il valait `true`, le kit s'auto-detruirait au cast.
    int(EffectType.TunnelingHorror_PendingSummon): BondRemovalGates(
        "IdunBattle.Entities.Effects.Loki.TunnelingHorror_PendingSummonEffect", False, None, False),
    # Pose par `HazeOfCorruptionAbility` (chaine de bonds, #207/#220/#231). `get_Range` et
    # `get_Adjacent` sont ici des CHAMPS (`this+0x480` / `this+0x488`) que
    # `HazeOfCorruption_DamageTransferEffect$$.ctor` n'ecrit PAS -> `Nullable` vide et `false`.
    int(EffectType.HazeOfCorruption_DamageTransfer): BondRemovalGates(
        "IdunBattle.Entities.Effects.Loki.HazeOfCorruption_DamageTransferEffect", True, None, False),
    # Pose par `ValkyrieStrikeAbility$$ExecuteBehaviour` (`caster@0x160` en 4e ET 6e position, donc
    # `bondedEntity` = le caster). SOUS-FAMILLE `APendingAttackEffect` : le gate (a) n'y est pas une
    # constante, c'est `NOT <klass+0x778> IsExecutedIfOwnerDies` -- et ce virtuel vaut VRAI ici, donc
    # `get_RemoveOnBondedEntityDeath` est FAUX et le natif ne construit AUCUN trigger (a). L'entree
    # est dans la table pour DOCUMENTER ce non-retrait ; `bond_removal_registry_entries` n'en tire
    # aucun trigger, exactement comme pour `TunnelingHorror_PendingSummon`.
    # ⚠ C'est la SEULE ligne du fichier confrontee dans le sens << l'effet SURVIT >>
    # (`--step valkyrielive` : bonde mort, 1022 encore present). Elle vaut donc aussi contre-epreuve
    # de la table `TRIVIAL` du probe, par laquelle toutes les autres valeurs sont lues.
    # `get_Range`/`get_Adjacent` sont HERITES d'`APendingAttackEffect`, qui les surcharge en
    # `Nullable` vide et `false` pour ses 20 derivees : ni (b) ni (c) sur toute la sous-famille.
    int(EffectType.ValkyrieStrike_Effect): BondRemovalGates(
        "IdunBattle.Entities.Effects.Loki.ValkyrieStrikeEffect", False, None, False,
        is_executed_if_owner_dies=True),
    # Pose par `CrushingClawsAbility$$ExecuteBehaviour` (1105) et par
    # `GetEmRuntzAbility$$TauntWithNewChildrenWhoDidDamage` (1045) -- les DEUX passent le TAUNTANT en
    # 5e argument d'`AddBondEffect`, donc `bondedEntity` = le taunteur. Classe native ETABLIE : c'est
    # `IdunBattle.Entities.Effects.TauntedEffect$$ApplyInternal` qui pose les trois sous-effets
    # 25/26/1237 ET la liste de cibles forcees (#436) -- la seule des quatre classes armant (b) qui
    # le fasse. CONFRONTEE au natif dans les DEUX sens (cf. §4 : retire a distance 2, gardee a 1).
    # `get_RemoveOnBondedEntityDeath = true` : le taunt tombe AUSSI a la mort du taunteur -- meme
    # mesure `--step declared`, confrontee par le bras `deathlive` du probe de ce residu.
    int(EffectType.Taunted_OnlySpecificTargets): BondRemovalGates(
        "IdunBattle.Entities.Effects.TauntedEffect", True, 1, False),
    # Pose par `HolyDuelAbility$$ExecuteBehaviour` (1050, `templChampion`) sur la CIBLE, avec
    # `bondedEntity` = le CASTER (`Caster@0x48` en 3e ET en 5e argument d'`AddBondEffect`). Classe
    # native ETABLIE : c'est `IdunBattle.Entities.Effects.Loki.HolyDuel_TauntEffect$$ApplyInternal`
    # qui pose les QUATRE sous-effets du duel (les deux `Taunted` symetriques + 1092 + 1093), et
    # c'est la seule classe du binaire a porter ce nom.
    # Mesure `--step declared` du 2026-08-08 : `get_Range` = OWN=none (donc PAS de trigger (b)),
    # `get_Adjacent` = OWN=true (trigger (c), la SEULE classe de la famille a l'armer),
    # `get_RemoveOnBondedEntityDeath` = OWN=true (trigger (a)).
    # C'est ce qui rend l'i2 exact : 1091 n'a AUCUNE duree par defaut
    # (`StaticBattleRules.Effect$$DefaultAmountOfRounds(0x443)` -> null, relu au decompile), donc
    # « the taunt does not expire with rounds passed » -- il tombe a la rupture d'ADJACENCE ou a la
    # mort du bonde, jamais au tour qui passe.
    int(EffectType.HolyDuel_Taunt): BondRemovalGates(
        "IdunBattle.Entities.Effects.Loki.HolyDuel_TauntEffect", True, None, True),
    # Pose par `IdunBattleLogic.Entities.Abilities.Active.Loki.MindControlAbility$$ExecuteBehaviour`
    # (#552) sur l'ALLIE taunteur, `bondedEntity` = la CIBLE mind-controlee -- le MIROIR du 27 que
    # le meme arbre pose sur la cible, bonde a cet allie.
    # ⚠ CETTE LIGNE ETAIT DEJA MESUREE, ET EN ATTENTE DE SON PORTEUR. §8.7 de
    # `docs/rl/case-462-r4b-r1-r1-r1-r1-retrait-bond.md` la classait << (b) arme a `Nullable<int>(1)`,
    # mais son `EffectType` n'est pas etabli et le port ne pose aucun de ces effets >>. Les deux
    # verrous tombent ici : le port POSE 1367, et l'`EffectType` est etabli par le 2e argument
    # LITTERAL de l'`AddBondEffect` de l'arbre (`0x557`) apparie au NOM de la classe native.
    # Les TROIS virtuels sont MESURES (`probe_462_r4b_r1_r1_r1_r1_bond_removal.py --step declared`,
    # rejoue le 2026-08-08 : `get_Range` = corps propre `...MindControl_TaunterEffect$$get_Range`
    # (`Nullable..ctor(&ret, 1)`, LU au decompile), `get_Adjacent` = false, et
    # `get_RemoveOnBondedEntityDeath` = **true**).
    int(EffectType.MindControl_Taunter): BondRemovalGates(
        "Idun.Source.IdunBattle.Logic.Entities.Effects.Loki.MindControl_TaunterEffect",
        True, 1, False),
    # Pose par `IdunBattleLogic.Entities.Abilities.Active.Loki.AttemptedPossessionAbility$$ExecuteBehaviour`
    # (1101, `thousSorcerer` << Thaumachus >>, #590) sur la cible ET ses enfants vivants, avec
    # `bondedEntity` = le CASTER (`Caster@0x48` en 3e ET 5e argument d'`AddBondEffect`) -- et
    # desormais AUSSI par le trigger de PROPAGATION de l'effet lui-meme (#590-r3,
    # `triggers/loki/possession.py`), qui repose le MEME `EffectType` sur les summons qui
    # apparaissent pendant la possession, bondes au MEME caster.
    # `EffectType` ETABLI par le 2e argument LITTERAL de l'`AddBondEffect` (`0x4b9`) apparie au NOM
    # de la classe native, seule du binaire a le porter.
    # Les TROIS virtuels sont MESURES (`probe_462_r4b_r1_r1_r1_r1_bond_removal.py --step declared`,
    # 2026-08-13) : `get_Range` = OWN=none (PAS de (b)), `get_Adjacent` = OWN=false (PAS de (c)),
    # `get_RemoveOnBondedEntityDeath` = OWN=true (le (a) ARME). Consequence portee : la possession
    # tombe quand le CASTER meurt ou quitte le plateau -- et elle NE tombe ni a la distance ni a la
    # rupture d'adjacence, ce qui est coherent avec l'arbre du cast, qui envoie la proie ATTAQUER
    # (donc s'eloigner de Thaumachus) dans le meme souffle.
    int(EffectType.AttemptedPossession_Possessed): BondRemovalGates(
        "IdunBattle.Entities.Effects.Loki.AttemptedPossession_PossessedEffect", True, None, False),
}


def assert_pending_gate_consistency() -> None:
    """`remove_on_bonded_entity_death == NOT is_executed_if_owner_dies` sur la sous-famille.

    Mirror executable de `APendingAttackEffect$$get_RemoveOnBondedEntityDeath`, dont le corps EST
    cette negation. Sans ce garde, les deux champs pourraient deriver l'un de l'autre au fil des
    editions et la table mentirait sans que rien ne rougisse -- ils sont redondants EXPRES, et
    c'est la redondance qui les garde."""
    for et, g in BOND_REMOVAL_GATES.items():
        if g.is_executed_if_owner_dies is None:
            continue
        attendu = not g.is_executed_if_owner_dies
        if g.remove_on_bonded_entity_death != attendu:
            raise AssertionError(
                "effect_type %d (%s) : get_RemoveOnBondedEntityDeath=%s mais "
                "NOT IsExecutedIfOwnerDies=%s"
                % (et, g.native, g.remove_on_bonded_entity_death, attendu))

_ON_PRE_UNIT_DEATH_2 = int(EventTriggerType.PreUnitDeath_2)      # `On(2)`
_ON_UNIT_REMOVED = int(EventTriggerType.UnitRemoved)             # `On(0x25)`
_ON_UNIT_POSITION_CHANGED_2 = int(EventTriggerType.UnitPositionChanged_2)   # `On(0x1d)`


def bond_removal_tree(effect_type: int) -> RemoveEffect:
    """Arbre du behaviour `IdunBattleLogic.Entities.DSLBehaviors$$RemoveEffect(Effect@0x38)`.

    Frontiere #149 : feuille DECLARATIVE ici, le mutateur
    `IdunBattle.Operations.RemoveEffectOperation` (port : `remove_effect_instance`) EN DESSOUS.
    Le selecteur natif est `Effect@DSLSelectors+0x38` = l'entite-effet COURANTE ; le port n'a que le
    couple (porteur, effect_type), et `Caster()` designe ici le PORTEUR -- meme collapse assume que
    `ChronometronExtraDamageRemove`, legitime par le gate << deja present >> d'`AddEffectOperation`
    qui garantit au plus UNE instance non consommee d'un effect_type par unite.

    Rendu par une USINE et non construit inline : c'est ce qui rend l'arbre INSPECTABLE par un garde
    offline (lecon de #556 §3 -- un garde qui lit le TEXTE d'`execute_behaviour` matche ses propres
    commentaires et ne peut pas rougir)."""
    return RemoveEffect(int(effect_type), Caster())


class BondRemoveOnBondedEntityDeath(EffectTrigger):
    """Trigger (a) d'`ABondEffect$$CreateHandleTriggerAbilitiesInternal`, gate
    `<klass+0x748> get_RemoveOnBondedEntityDeath`.

        Triggered( NOT AmountIsZero(BondedEntityFromEffect(Effect))
                   & ( On(2 = PreUnitDeath_2) | On(0x25 = UnitRemoved) )
                   & IsEntityWithIdTarget(BondedEntityFromEffect(Effect)),
                   RemoveEffect(Effect) )

    Le `CreateTrigger` COLLAPSE imperativement dans `matches` (doctrine #149, comme
    `ChronometronExtraDamageRemove`) ; le behaviour est un ARBRE DSL rendu par
    `bond_removal_tree`.

    UNE SEULE classe pour tous les effect_type, comme le natif : c'est `ABondEffect` -- la BASE --
    qui construit ce `Triggered()` pour toutes ses derivees. L'attribut declaratif `effect_type`
    reste donc a `-1` ; le dispatch (`dispatch/core.py`) fait son lookup sur le `effect_type` de
    l'INSTANCE d'effet, jamais sur celui de la classe de trigger.

    ⚠ L'owner est le PORTEUR de l'effet (vivant), et c'est le BONDE qui est `target` de l'event.
    C'est ce qui fait passer ce trigger a travers le gate << owner vivant >> de `dispatch/core.py`,
    lequel n'a pas d'echappatoire `fire_on_death` sur un `EffectTrigger`."""
    event_id = _ON_PRE_UNIT_DEATH_2
    # `On(2) | On(0x25)` : le dispatch accepte l'entree si `ev.event_id` est `event_id` OU dans
    # `event_ids` -- c'est le seul moyen de mirrorer un `op_BitwiseOr` de deux `On()`.
    event_ids = (_ON_PRE_UNIT_DEATH_2, _ON_UNIT_REMOVED)

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        inst = _bonded_instance(state, int(self.owner_id), _gate_on_death)
        if inst is None:
            return False
        gates = BOND_REMOVAL_GATES.get(int(inst.effect_type))
        if gates is None or not gates.remove_on_bonded_entity_death:
            return False                        # `<klass+0x748>()` faux -> trigger NON CONSTRUIT
        bonded = getattr(inst, "bonded", None)
        if bonded is None:
            return False
        # `NOT AmountIsZero(BondedEntityFromEffect(Effect))` -- semantique MESUREE : l'entite bondee
        # est encore resoluble dans l'etat (cf. §2 de l'en-tete). Sur les deux vecteurs, l'event
        # part AVANT la consommation des effets, donc le bonde y est encore.
        if state.get_entity(int(bonded)) is None:
            return False
        # `IsEntityWithIdTarget(BondedEntityFromEffect(Effect))` --
        # `IdunBattle.Entities.Triggers.IsEntityWithIdAbilityTrigger$$ShouldTrigger` avec
        # `isOwner = 0` : l'id de l'entite selectionnee doit EGALER celui de la CIBLE de l'event.
        # Les deux vecteurs renseignent bien `target_id` = l'unite qui meurt / est retiree.
        return ev.target_id is not None and int(ev.target_id) == int(bonded)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        return _remove_bond(state, int(self.owner_id), _gate_on_death, "BondedEntityDeath")


class BondRemoveOnRangeExceeded(EffectTrigger):
    """Trigger (b) d'`ABondEffect$$CreateHandleTriggerAbilitiesInternal`, gate
    `<klass+0x728> get_Range` (un `Nullable<int>` : le trigger n'existe QUE s'il a une valeur).

        Triggered( NOT IsInRange(Owner@DSLSelectors+0x30, BondedEntityFromEffect(Effect),
                                 Direct(range.Value))
                   & NOT AmountIsZero(BondedEntityFromEffect(Effect))
                   & On(0x1d = UnitPositionChanged_2),
                   RemoveEffect(Effect) )

    `IdunBattleLogic.Entities.DSLTriggers$$IsInRange` construit
    `IdunBattle.Entities.Triggers.IsInRangeAbilityTrigger`, dont `$$ShouldTrigger` rend
    `query.GetDistance(Select(s1), Select(s2)) <= GetAmount(range)` -- comparateur INCLUSIF. Le
    `NOT` en fait donc `distance > range`.
    ⚠ ghidra resout le ctor DEDUPLIQUE de ce noeud vers `IsUnitOnTileEffectTrigger$$.ctor` : c'est
    la signature Frida `(selector1, selector2, range: IAmountFormula)` qui tranche, pas le nom.

    AUCUN gate sur l'ACTEUR de l'event : le natif ne regarde ni `actor` ni `target`. N'importe quel
    mouvement de n'importe quelle unite re-evalue la distance COURANTE -- c'est ce qui rend le
    trigger atteignable alors meme que le taunte, lui, ne peut PAS marcher
    (`Taunted_BlockMovement`).

    Comme (a) : UNE SEULE classe pour tous les `effect_type` (c'est la BASE qui construit le
    `Triggered()`), `effect_type` declaratif a `-1`, lookup du dispatch sur l'instance."""
    event_id = _ON_UNIT_POSITION_CHANGED_2

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        inst = _bonded_instance(state, int(self.owner_id), _gate_range)
        if inst is None:
            return False
        gates = BOND_REMOVAL_GATES.get(int(inst.effect_type))
        if gates is None or gates.range is None:
            return False                        # `get_Range` VIDE -> trigger NON CONSTRUIT
        bonded = getattr(inst, "bonded", None)
        if bonded is None:
            return False
        # `NOT AmountIsZero(BondedEntityFromEffect(Effect))` -- meme semantique MESUREE qu'en (a)
        # (cf. §2) : l'entite bondee est encore resoluble dans l'etat.
        if state.get_entity(int(bonded)) is None:
            return False
        a, b = _tile_of(state, int(self.owner_id)), _tile_of(state, int(bonded))
        if a is None or b is None:
            # `query.GetDistance` sur une entite SANS tuile (hors plateau : `RemoveUnitFromItsTiles`,
            # MoW) n'est pas lisible ici. On ne RETIRE PAS -- le retrait est l'action, donc l'inaction
            # est le choix conservateur -- et on le DIT plutot que de fabriquer une distance.
            return False
        return hexgeo.distance(a, b) > int(gates.range)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        return _remove_bond(state, int(self.owner_id), _gate_range, "RangeExceeded")


class BondRemoveOnAdjacencyLost(EffectTrigger):
    """Trigger (c) d'`ABondEffect$$CreateHandleTriggerAbilitiesInternal`, gate
    `<klass+0x738> get_Adjacent` (un `bool` : le trigger n'existe QUE s'il est vrai).

        Triggered( NOT IsAdjacent(Owner@DSLSelectors+0x30,
                                  BondedEntityFromEffect(Effect@DSLSelectors+0x38), 3)
                   & NOT AmountIsZero(BondedEntityFromEffect(Effect))
                   & On(0x1d = UnitPositionChanged_2),
                   RemoveEffect(Effect) )

    JUMEAU EXACT de (b) ci-dessus, au PREDICAT pres -- et les deux predicats sont des natifs
    DIFFERENTS, pas deux ecritures du meme :

      * (b) `IsInRange` -> `IsInRangeAbilityTrigger$$ShouldTrigger` = `query.GetDistance(a, b) <=
        range` : une DISTANCE HEX pure ;
      * (c) `IsAdjacent` -> `IsAdjacentAbilityTrigger$$ShouldTrigger` = un `forall` sur les paires
        d'entites de `BattleQuery$$AreEntitiesAdjacent` -> `MovementUtil$$AreTilesAdjacent`, qui
        porte une **PORTE D'ELEVATION** (`|dElev| < 2`) et un **COURT-CIRCUIT D'IDENTITE**
        (`t1 == t2`) que la distance ignore, et qui compare les EMPREINTES COMPLETES
        (`GetTiles`), pas les main tiles.
      Ecrire (c) comme `distance > 1` serait donc FAUX sur un board a relief et sur toute unite
      multi-hex. Le port passe par le foyer UNIQUE `services/battle_query.py::are_entities_adjacent`
      -- le meme que le noeud DSL `entities/triggers.py::IsAdjacent` et que le gate de ciblage.

    Le 3e argument `3` de la factory est un `UnitSelectionType` : il part au SELECTEUR (slot 3),
    jamais dans la comparaison par paire (#433-r3). Les deux selecteurs sont ici des SINGLETONS
    (`Owner` et `BondedEntityFromEffect`), donc le `forall` porte sur UNE paire.

    Comme (a) et (b) : UNE SEULE classe pour tous les `effect_type` (c'est la BASE qui construit le
    `Triggered()`), `effect_type` declaratif a `-1`, lookup du dispatch sur l'instance.

    AUCUN gate sur l'ACTEUR de l'event, comme (b) : n'importe quel mouvement re-evalue l'adjacence
    COURANTE. C'est ce qui rend le trigger atteignable alors meme que les DEUX duellistes portent
    `Taunted_BlockMovement` -- un tiers qui pousse (`PushUnit`) ou un `MoveUnit` force suffit."""
    event_id = _ON_UNIT_POSITION_CHANGED_2

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        inst = _bonded_instance(state, int(self.owner_id), _gate_adjacent)
        if inst is None:
            return False
        gates = BOND_REMOVAL_GATES.get(int(inst.effect_type))
        if gates is None or not gates.adjacent:
            return False                        # `get_Adjacent` FAUX -> trigger NON CONSTRUIT
        bonded = getattr(inst, "bonded", None)
        if bonded is None:
            return False
        # `NOT AmountIsZero(BondedEntityFromEffect(Effect))` -- meme semantique MESUREE qu'en (a)/(b)
        # (cf. §2) : l'entite bondee est encore resoluble dans l'etat.
        if state.get_entity(int(bonded)) is None:
            return False
        fa, fb = get_unit_feet(state, int(self.owner_id)), get_unit_feet(state, int(bonded))
        if not fa or not fb:
            # Empreinte VIDE (entite hors plateau) : le natif rend FAUX (la double boucle
            # d'`AreTilesAdjacent(IList, IList)` ne tourne pas), donc `NOT IsAdjacent` serait VRAI et
            # l'effet TOMBERAIT. Le port ne RETIRE PAS -- meme choix conservateur qu'en (b), et il
            # est DIT : le retrait est l'action, l'inaction est le repli qui n'invente rien.
            return False
        return not are_entities_adjacent(fa, fb, getattr(state, "board", None))

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        return _remove_bond(state, int(self.owner_id), _gate_adjacent, "AdjacencyLost")


def _gate_range(g: BondRemovalGates) -> bool:
    return g.range is not None


def _gate_adjacent(g: BondRemovalGates) -> bool:
    return bool(g.adjacent)


def _gate_on_death(g: BondRemovalGates) -> bool:
    return bool(g.remove_on_bonded_entity_death)


def _tile_of(state: State, uid: int):
    """MAIN TILE de l'entite (`IdunBattle.Entities.EntityExtensions$$GetMainTile`). `None` = pas de
    `PositionComponent`, c'est-a-dire une entite hors plateau."""
    e = state.get_entity(int(uid))
    pc = e.get_component(PositionComponent) if e is not None else None
    return None if pc is None else (pc.col, pc.row)


def _bonded_instance(state: State, owner_id: int, gate=_gate_on_death):
    """L'instance NON CONSOMMEE, portee par `owner_id`, dont l'`effect_type` est dans la table ET
    dont le gate demande est arme. `None` sinon.

    Mirror du couple (`Effect@DSLSelectors+0x38`, `ABondEffect$$BondedEntityId`) : le natif tient
    l'entite-effet COURANTE, le port la retrouve par son type sur le porteur. Le `gate` est le
    VIRTUEL du trigger appelant -- les trois `Triggered()` d'`ABondEffect` sont INDEPENDANTS, donc
    chacun ne doit voir que les instances dont SON virtuel est arme."""
    eff = getattr(state, "effects", None)
    if eff is None:
        return None
    for e in eff.by_unit.get(int(owner_id), []):
        if e.consumed:
            continue
        g = BOND_REMOVAL_GATES.get(int(e.effect_type))
        if g is not None and gate(g):
            return e
    return None


def _remove_bond(state: State, owner_id: int, gate, reason: str) -> Optional[dict]:
    """Execution du behaviour commun aux trois `Triggered()` : l'arbre `RemoveEffect(Effect@0x38)`.
    Foyer UNIQUE -- le natif construit le MEME `DSLBehaviors$$RemoveEffect(Effect@0x38)` dans les
    trois branches, seul le trigger differe."""
    inst = _bonded_instance(state, int(owner_id), gate)
    if inst is None:
        return None
    et = int(inst.effect_type)
    ectx = ExecutionContext(state=state, rng=state.rng)
    bond_removal_tree(et).execute(
        entities_from_state(state, int(owner_id), int(owner_id)), ectx)
    removed = sum(int(p.get("removed") or 0) for n, p in ectx.emitted if n == "RemoveEffect")
    if not removed:
        return None
    return {"effect": et, "owner": int(owner_id), "removed": removed,
            "bonded": int(getattr(inst, "bonded", -1)), "reason": reason}


def bond_removal_registry_entries() -> list[tuple[int, type[EffectTrigger]]]:
    """`(effect_type, classe)` a inscrire dans `EFFECT_TRIGGERS`, DERIVE de la table -- jamais ecrit
    a la main. Un effet peut y entrer DEUX fois (deux `Triggered()` distincts dans l'`ArraySet`
    natif) : c'est le cas de `Taunted_OnlySpecificTargets`, qui arme (a) ET (b).

    Une entree dont AUCUN virtuel n'est arme (`TunnelingHorror_PendingSummon`,
    `ValkyrieStrike_Effect`) reste dans la table -- elle y DOCUMENTE le non-retrait, et un garde
    offline peut l'assertionner -- mais n'inscrit aucun trigger : cote natif, le `Triggered()`
    n'entre pas dans l'`ArraySet`.

    (c) `get_Adjacent` a sa ligne depuis que le port POSE `HolyDuel_Taunt` (1091) : c'est la SEULE
    classe de la famille a l'armer, et elle est desormais atteignable (`HolyDuelAbility` 1050 est
    entree dans `ABILITY_CLASSES`). Avant ce port, l'inscrire aurait ete vacuement vrai (cf. §5)."""
    out: list[tuple[int, type[EffectTrigger]]] = []
    for et, g in sorted(BOND_REMOVAL_GATES.items()):
        if g.remove_on_bonded_entity_death:
            out.append((et, BondRemoveOnBondedEntityDeath))
        if g.range is not None:
            out.append((et, BondRemoveOnRangeExceeded))
        if g.adjacent:
            out.append((et, BondRemoveOnAdjacencyLost))
    return out
