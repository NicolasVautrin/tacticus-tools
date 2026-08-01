"""`StructuralAnalyser_Visual` (0x496 = **1174**) — le VOLET « porteur » du passif
`StructuralAnalyser` (TriggeredAbilityType 0x477 = 1143) de `tauDarkstrider`. case-366-r1.

## TROIS classes natives, et 1174 est la SOEUR de 1156 — pas sa fille

`data/symbols/<build>/frida/classes.tsv` (lu du runtime IL2CPP, donc du VRAI `Il2CppClass`) :

    IdunBattle.Entities.Effects.Loki.AStructuralAnalyserEffect        -> BaseEffect
    IdunBattle.Entities.Effects.Loki.StructuralAnalyserAdjacentEffect -> AStructuralAnalyserEffect
    IdunBattle.Entities.Effects.Loki.StructuralAnalyser_VisualEffect  -> AStructuralAnalyserEffect

Le ctor de 1174 est `xor edx, edx ; jmp <corps 0x477>` (relu octet a octet) : un `: base()` nu qui
saute sur le corps `BaseEffect..ctor(this, AbilityOrEffect.op_Implicit(0x477), true)`. Ce corps est
DEDUPLIQUE (deux entrees dans la table de pointeurs de methodes) — le lire comme
« `StructuralAnalyserAdjacentEffect$$.ctor`, donc 1174 derive de 1156 » est exactement le piege
CLAUDE.md « un nom de `$$.ctor` n'est PAS une classe ». `AStructuralAnalyserEffect`, elle, n'est NI
dans `ghidra/functions.tsv` NI dans `frida/methods.tsv` : toutes ses methodes ont un corps partage,
donc la table n'en nomme qu'un proprietaire arbitraire.

## POSE — les DEUX effets d'un bloc, sur le porteur

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.StructuralAnalyser_AddDamageBuffAbility$$CreateBehaviour`
(mirror du decompile) :

    AddEffect(0x484 = 1156 StructuralAnalyserDmgBoost, <abilityStateReference>, targets = Owner,
              turns = <vide>)
  + AddEffect(0x496 = 1174 StructuralAnalyser_Visual,  <idem>)
    (fusionnes par `IdunBattle.DSL.AbilityBehaviour$$op_Addition`)

`turns` vide => PERMANENT : ce qui l'eteint est la CONDITION, pas une duree.

## CE QUE 1174 CIBLE — `Owner`, et c'est la difference avec 1156

Sa table de methodes est `[CreateActiveCondition, CreateTargetSelector, .ctor]` ; le
`CreateTargetSelector` y a le corps ARCHI-DEDUPLIQUE `return <DSLSelectors+0x30>` (= `Owner` ;
~250 entrees dans la table, c'est le selecteur par defaut du jeu). MESURE LIVE qui le confirme, et
qui separe les deux effets d'un seul relevé d'evenements (case-366-r1, runner MC1_67/777) :

    [Effect_Refresh e=94 «StructuralAnalyserDmgBoost»]  ReceiveEffect e=81   <- l'ALLIE
    [Effect_Refresh e=95 «StructuralAnalyser_Visual»]   ReceiveEffect e=79   <- LE PORTEUR

1156 se projette sur les allies (selecteur `AdjacentFriends + T'au ring-2`) ; 1174 reste sur
Darkstrider.

## CONDITION — `AmountIsGreaterThanZero(<le selecteur d'aura de 1156>)`

`IdunBattle.Entities.Effects.Loki.StructuralAnalyser_VisualEffect$$CreateActiveCondition`
(mirror du decompile) :

    DSLTriggers.AmountIsGreaterThanZero(
        StructuralAnalyserAdjacentEffect$$CreateTargetSelector(this) )

et ce selecteur (relu, meme fonction) est

    Unique( AdjacentFriends(Owner)
          + UnitsFromFaction( SurroundingFriends(Owner, range = Direct(2)), 9 = Tau ) )

= « au moins un allie ADJACENT (toute faction) OU un allie T'AU a <= 2 hexes ». C'est le selecteur
d'aura PARTAGE x4 (StructuralAnalyser / SereneUnifier / DotGG / WayOfTheShortBlade,
`docs/rl/case-220/tau.md`), deja porte cote DotGG par
`DefenderOfTheGreaterGoodExtraDmgEffect.aura_selector_covers`. Le porteur ne s'y compte PAS —
MESURE, sinon la condition serait tautologique.

**Table de verite MESUREE** (board C3_01, seed 31337 ; ami non-T'au `astraDreir`, ami T'au
`tauCrisis`, distances hex a Darkstrider) :

    | d(non-Tau) | d(Tau) | 1174.active |
    |     1      |   2    |    True     |
    |     2      |   4    |   False     |   <- un ami NON-T'au a 2 hexes NE SUFFIT PAS
    |     4      |   2    |    True     |   <- le tier T'au ring-2 SUFFIT seul
    |     4      |   4    |   False     |

## CE QUE 1174 NE FAIT PAS — aucune contribution, et c'est MESURE

Le canal `CreateEffectDamageBonusForAttack` (`ForAddition(get_OwnerIsCaster & HasEffect(target,
0x462 = 1122 Markerlight) & IsRangedAttack, ConfigVar(8 = extraDmg))`) n'a **qu'UNE** entree dans la
table de pointeurs de methodes — il appartient a UNE classe, et ce n'est pas celle de 1174. La
mesure le tranche sans dependre du decoupage de table : sur le MEME etat (Darkstrider a (6,6),
`orksNob` MARKERLIGHTE a (6,8)), la prediction native de son attaque normale vaut

    **[18428-27640] avec 1174 ACTIF  ==  [18428-27640] avec 1174 INACTIF**

(et `[16024-24036]` avant la pose du Markerlight, soit le `x1.15` de `MarkerlightEffect`, deja
porte). => 1174 ne porte NI degat, NI coups, NI percage, NI crit pour son porteur.

**Cette entree ne change donc RIEN au comportement** (`BaseEffect` no-op etait deja identique). Elle
existe pour DEUX raisons : fixer l'identite de classe (empecher qu'on donne un jour a Darkstrider le
+extraDmg de 1156 en croyant 1174 derive de lui — ce serait un bug de +extraDmg par coup), et rendre
la `CreateActiveCondition` a sa place NATIVE, la ou tout futur consommateur d'`active_effects` la
trouvera. `1156 StructuralAnalyserDmgBoost` (le canal de degat, cote ALLIES) reste NON porte —
c'est le cas `[opus]` `StructuralAnalyser` de `docs/rl/case-220/tau.md`, hors perimetre de #366.
"""
from __future__ import annotations

from collections.abc import Mapping

from ..base import BaseEffect


class StructuralAnalyserVisualEffect(BaseEffect):
    """`StructuralAnalyser_Visual` (0x496 = 1174) — pose sur `tauDarkstrider` en meme temps que
    `1156`, cible **Owner**, ZERO contribution, ACTIF tant qu'il a un allie adjacent (toute faction)
    ou un allie T'au a <= 2 hexes."""

    # `EffectComponent.IsActive @+0x5c` capte decrit l'etat REEL au moment de la capture ; ici la
    # condition est GEOMETRIQUE, donc elle rebascule des qu'une unite bouge (et le natif la
    # reevalue : `RefreshEffectsOperation$$RefreshEffect` -> `Activate`/`DeactivateEffect`, MESURE
    # sur les evenements de `MoveUnitOperation`). La condition portee fait donc foi.
    active_condition_ported = True
    # PAS de `seed_witness_effect`, et PAS d'entree `ABILITY_INIT_OWNER_EFFECTS["StructuralAnalyser"]`
    # -- MEME arbitrage que `WireweaveNet` (`factory.py`, case-366-r1b §7bis) : materialiser
    # l'instance INACTIVE ne servirait a rien ici (1174 n'a aucun canal et aucun `HasEffect(0x496)`
    # ne le lit) et le seed d'owner-effects lit le KIT gameconfig, pas la MESURE -- donc il poserait
    # 1174 sur une unite privee du passif par `--unit-stat`. La seule chose que le port doit rendre
    # est la CONDITION, sur les instances que le canal live publie.

    def is_active(self, unit_state: "Mapping | None" = None) -> bool:
        """`CreateActiveCondition` = `AmountIsGreaterThanZero(<selecteur d'aura de 1156>)`.

        `structural_analyser_friends` ABSENT du `unit_state` = **non mesure** -> on ne ferme pas
        (degradation fidele, meme regime que `ModifiedExoarmour_ExtraDmg` avec
        `tiles_moved_this_turn`). Cote COMBAT la cle EST posee : `UnitEffectStateView` la calcule
        paresseusement (`runner/components.py::structural_analyser_friends`) des que le porteur a
        une equipe et une tuile."""
        n = (unit_state or {}).get("structural_analyser_friends")
        return True if n is None else int(n) > 0
