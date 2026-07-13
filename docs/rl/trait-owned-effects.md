# Trait/ability owned-effects : `AOwnerEffectSpecificTriggeredAbility` (RE 2026-07-13, build gqfc5mff6c)

Fondation pour #101b (CrushingStrike runner-side) et #160 (RangedSpecialist prediction) : le layer
"materialiser un effet CONDITIONNEL depuis un trait/ability" que le port n'a PAS.

## Mecanisme natif

Un trait (ou ability) qui pose un effet permanent-mais-conditionnel sur son OWNER le fait via une
`AOwnerEffectSpecificTriggeredAbility` (base ctor `@180fb3790`) : le ctor stocke l'**effet possede**
(EffectType id) `@this+0x60`. Ces triggered-abilities sont enregistrees par
`AbilitiesDatabase.InitializeTriggeredAbilities` (lambdas `<>c.<...>b__28_NN`, ex. CrushingStrike =
`b__28_20 @18101b1b2`), indexees par `TriggeredAbilityType`.

Exemple CrushingStrike (#101b) :
- `CrushingStrikeTraitAbility$$.ctor @1811bf310` = `AOwnerEffectSpecificTriggeredAbility(0x4a2=1186, 0)`.
- Effet possede `0x4a2 = 1186` = `CrushingStrikeEffect` (`Effects.Loki`, ctor `@180f3af20`,
  `CreateDamageModifier @180f3ad90` = +50% si OwnerIsCaster & IsNormalAttack & IsMeleeAttack ;
  `CreateActiveCondition @180f3ad50` = NOT HasFlag(HasMoved)).
- Ids DEMELES (un resume les avait conflates) : `UnitTrait.CrushingStrike=1044`,
  `EffectType.CrushingStrike=1226`, `TriggeredAbilityType.CrushingStrike=1186` (= l'effet materialise,
  celui possede par la triggered-ability). Le trait 1044 -> la triggered-ability 1186 -> l'effet 1186.

## Table complete (xrefs base ctor `180fb3790`) — 18 owner-effect abilities

DakkaAbility, CloseCombatWeakness_AddEffectAbility, TerminatorArmour_AddEffectAbility,
Loki_CamouflageAbility, NetworkedTargetingAbility, OverwatchAutoAttackAbility, BlessingsOfKhorneAbility,
**CrushingStrikeTraitAbility**, Ambush_InitAbility, TalismanOfRageAbility, InfiltrateAddEffectAbility,
BossAdjutant_ReduceDamageAbility_Old, InstinctiveBehaviour_InitAbility, TerrifyingAbilityAbility,
Synapse_AddEffectAbility, ShadowInTheWarp_AddEffectAbility, ParryAbility, DiminutiveAbility.

(Chaque sous-classe = decompiler son ctor pour lire l'EffectType possede `@+0x60`.)

## Le gap runner (pourquoi #101b / #160)

Le runner offline seed `State.effects` UNIQUEMENT depuis `decisionView.effects` live-capture
(`engine/runner/snapshot.py:141`, `EffectsState.seed(effects_by_id, ...)`). `decisionView.effects` est
**IsActive-filtre** cote natif : un owner-effet n'y apparait que lorsque sa condition tient AU MOMENT
de la capture.

- Consequence : si l'effet est INACTIF au seed (condition non remplie a la capture), le runner ne le
  seed pas -> il ne peut PAS le reactiver plus tard (multi-tours) car il n'a jamais materialise l'effet
  depuis le TRAIT. Le runner ne SYNTHETISE jamais un owned-effect depuis le trait.
- CrushingStrike (#101b) : condition = NOT HasMoved. Au debut de tour (pas bouge) l'effet est ACTIF ->
  capture -> seede -> le gate `has_moved` (create_effect_damage_bonus_for_attack, loki.py:312) le gere
  DANS ce tour. Prediction validee #98 (darkaTerminator u80 x2.25). Le gap est le cas seed-inactif
  (unite deja bougee a la capture) puis re-tour sans bouger.

## #101b vs #160 : meme PROBLEME, PAS forcement meme vehicule natif

- #101b CrushingStrike : owner-effet via `AOwnerEffectSpecificTriggeredAbility` (dans la table ci-dessus),
  effet 1186. CAPTURE live quand actif (comme Synapse/ShadowInTheWarp, aussi dans la table et vus dans
  decisionView.effects du Neurothrope).
- #160 RangedSpecialist : **ABSENT de la table** ci-dessus -> mecanisme DIFFERENT (evalue autrement).
  Le re-expert #160 pinne si c'est capture ou evalue a l'attaque depuis le trait. NE PAS presumer
  identique a CrushingStrike.

## Plan (co-implementation apres verdict #160)

Porter un layer "trait->owned-effect materialization" : a l'init de state, pour chaque unite, lire ses
traits -> triggered-abilities owner-effect (table ci-dessus) -> materialiser l'effet possede (gate par sa
CreateActiveCondition, evaluee dynamiquement comme les effets deja portes). Rend le runner auto-suffisant
(independant de l'etat actif au moment de la capture). Couvre CrushingStrike ET les autres owner-effets ;
RangedSpecialist selon le verdict #160 (peut relever d'un chemin distinct).
