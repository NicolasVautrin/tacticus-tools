"""Les DEUX effets de `1175 BloodChalice` (`bloodSanguinary` « Sanguinary Priest ») -- #576.

L'ability les pose tous les deux sur le MEME ensemble (`GetTargets()` = allies adjacents
non-mecaniques et non-`Immune`), pour `TurnsFromRounds(1)`. Elle vit dans
`runner/abilities/bloodangels.py`.

  * **1368 `BloodChalice_HealOnAttack`** (`IdunBattle.Entities.Effects.Loki.
    BloodChalice_HealOnAttackEffect`) -- DEUX volets natifs, tous deux lus :
      - `$$CreateTargetTrigger` / `$$CreateTargetTriggerBehaviour` = le SOIN sur attaque melee,
        porte comme `EffectTrigger` (`runner/operations/triggers/effect_triggers.py`), parce que
        c'est un trigger d'evenement et non un modificateur de lecture ;
      - `$$CreatePiercingBonusForAttack` = le +percage, porte ci-dessous.
  * **1369 `BloodChalice_ExtraPiercing`** (`IdunBattle.Entities.Effects.Loki.
    BloodChalice_ExtraPiercingEffect`) -- un `AStatModifierEffect` sur `StatType.ExtraPierceMelee`,
    dont la seule surcharge est `$$CreateActiveCondition`.

⚠ LES DEUX EFFETS PORTENT DU PERCAGE, ET C'EST LE DECOMPILE QUI LE DIT -- pas une erreur de port.
Les canaux sont DISTINCTS (un `EffectBonus` de lecture d'attaque vs un `StatModifier` sur la stat),
et le port les additionne comme le natif (`runner/abilities/base.py` : `pierce_eff = clamp(profil +
extra + dir_pierce + effect_bonus, 0, 100)`).

⚠ MAIS UN SEUL DES DEUX CONTRIBUE REELLEMENT (#576-r1, tranche du 2026-08-10). La
`CreateActiveCondition` de `1369` lit `Target@DSLSelectors+0x60`, un slot que le contexte
d'evaluation des conditions d'activite (`RefreshEffectsOperation$$ShouldBeActive`) laisse a ZERO :
l'effet est POSE et INERTE A VIE. Le regime « les deux ensemble » qu'on croyait non confronte
N'EXISTE PAS cote natif. Detail et chaine LUE : `BloodChaliceExtraPiercingEffect` ci-dessous.
"""
from __future__ import annotations

from typing import Mapping

from ....services.effect_bonus import EffectBonus, for_piercing
from ..base import BaseEffect
from ..magnitude import ability_var

BLOOD_CHALICE_ID = "BloodChalice"


class BloodChaliceHealOnAttackEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.BloodChalice_HealOnAttackEffect` (effet **1368 = 0x558**).

    `$$.ctor` = `BaseEffect..ctor(this, AbilityOrEffect.op_Implicit(...), **true**)` -- effet
    ORDINAIRE (pas un `AStatModifierEffect`), d'ou l'heritage direct de `BaseEffect` ici.

    `$$CreatePiercingBonusForAttack` -- MIRROR du decompile :

        trigger = get_OwnerIsCaster op_BitwiseAnd IsMeleeAttack
        montant = ConfigVar(0x3f = extraPierceRatio, GetAbilityState(effect), config@+0x60)
        -> EffectBonus.ForPiercing(trigger, montant)          # axe PERCAGE, PAS le scalaire degat

    ⚠ CONTRASTE AVEC SON JUMEAU STRUCTUREL `Supercharge_ExtraPiercingEffect` (1208, meme slot, meme
    `ConfigVar(0x3f)`), et c'est le TRIGGER qui les separe : Supercharge porte
    `DamageProfileIs(Plasma) & **get_OwnerIsTarget**` (l'effet est sur la VICTIME -> le percage de
    QUI l'attaque), BloodChalice porte `**get_OwnerIsCaster** & IsMeleeAttack` (l'effet est sur
    l'ALLIE BENEFICIAIRE -> le percage de SES PROPRES coups de melee). Recopier le voisin aurait
    inverse la face. D'ou `for_piercing(owner_is_caster=**True**, .)`.

    ⚠ AUCUN gate de `damageProfile` : le natif n'appelle PAS `GetDamageProfile` ici (contraste
    Supercharge). Le seul discriminant est MELEE / distance -- l'i2 le confirme (« Melee attacks
    have +{extraPierceRatio}% pierce ratio »).

    `extraPierceRatio` n'est PAS dans `variablesAffectedByRarityBonus` -> `multiplier_pct` inerte,
    passe tout de meme pour rester fidele a l'accesseur natif (indexation par l'`AbilityState` du
    POSEUR, que `scale_from_source=True` a la pose fait atterrir dans `active_ability_level`).

    i2 (`UnitEffects/BloodChalice_HealOnAttack_Description`) : « Melee attacks have
    +{extraPierceRatio}% pierce ratio and performing a melee attack heals this unit for {hpToHeal}
    Health. » -- la SECONDE moitie de cette phrase est le trigger, portee ailleurs (cf. l'entete)."""

    def create_piercing_bonus_for_attack(self, damage_profile: str | None = None,
                                         is_melee: bool | None = None,
                                         attacker_ctx: Mapping | None = None) -> EffectBonus | None:
        if is_melee is not True:                      # IsMeleeAttack -- tri-etat : None => on se tait
            return None
        lvl = (self.active_ability_level if self.active_ability_level is not None
               else self.ability_level)
        v = ability_var(BLOOD_CHALICE_ID, "extraPierceRatio", lvl,
                        multiplier_pct=self.ability_variables_multiplier)
        # `owner_is_caster=True` : l'effet est sur l'unite QUI FRAPPE (get_OwnerIsCaster).
        return for_piercing(True, int(v)) if v else None


class BloodChaliceExtraPiercingEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.BloodChalice_ExtraPiercingEffect` (effet **1369 = 0x559**).

    `$$.ctor` = `AStatModifierEffect..ctor(this, Nullable<AbilityOrEffect>(...), 0, 0, **true**,
    false)` -- un stat-modifier. La MAGNITUDE et la STAT ne sont pas dans la classe : elles viennent
    de la FEUILLE DE POSE (`AddStaticStatModifierEffect(GetTargets(), 0x559, **0x15 =
    StatType.ExtraPierceMelee**, ConfigVar(0x3f extraPierceRatio), TurnsFromRounds(1), isHidden=0)`),
    ecrite dans `StatModifierComponent` -- c'est le chemin generique du port, deja porte, et cette
    classe ne le DUPLIQUE PAS (frontiere #149 : la feuille pose, l'effet modifie).

    Sa SEULE surcharge est `$$CreateActiveCondition` -- MIRROR du decompile :

        return DSLTriggers.IsCharging(Owner@DSLSelectors+0x30, Target@DSLSelectors+0x60)

    c.-a-d. `IdunBattle.Core.Services.BattleQuery$$IsCharging(caster, target)` =
    `AreEntitiesAdjacent(caster, target) && UnitComponent(caster).ChargedUnitIds.Contains(target.Id)`
    (RE : `docs/rl/case-r32-ischarging-consumers.md`, qui recense deja CET effet comme l'unique
    consommateur d'`IsCharging` par le canal `CreateActiveCondition`).

    ⚠ CE N'EST PAS UN GATE QUE LE TOOLTIP ANNONCE. L'i2 de l'ability dit « affected units gain
    +{extraPierceRatio}% pierce ratio with melee attacks », sans condition de charge. La condition
    n'existe QUE dans le decompile. Elle est transcrite telle que lue.

    ⚠ CETTE CONDITION EST STRUCTURELLEMENT FAUSSE, ET C'EST UNE MESURE, PAS UNE INTERPRETATION
    (#576-r1). Elle lit `Target@DSLSelectors+0x60` -- or ce slot n'est PAS renseigne dans le
    contexte ou le natif evalue une `CreateActiveCondition`. Chaine LUE de bout en bout :

      1. `IdunBattle.Operations.RefreshEffectsOperation$$ShouldBeActive` `memset` son
         `AbilityEntities` de 0x128 octets a ZERO, puis n'ecrit QUE quatre champs :
         `<+0x08>` = owner, `<+0x18>` = owner, `<+0x50>` = activePlayer, `<+0x58>` = effectEntity
         (meme quadruplet dans `...$$RefreshEffect` pour le selecteur de cibles) ;
      2. les trois selecteurs qui nous interessent lisent chacun UN champ de ce contexte, et le
         corps entier de leur `Select` le dit :
             `IdunBattle.Entities.Selectors.OwnerSelector$$Select`   -> `ctx+0x18`  (RENSEIGNE)
             `IdunBattle.Entities.Selectors.EffectSelector$$Select`  -> `ctx+0x58`  (RENSEIGNE)
             `IdunBattle.Entities.Selectors.TargetSelector$$Select`  -> `ctx+0x10`  (**ZERO**)
         chacun rendant une `List` VIDE quand son champ est nul ;
      3. `IdunBattle.DSL.TargetsSelector$$SelectUnit` rend `0` sur liste vide ;
      4. `IdunBattle.Entities.Triggers.IsChargingTrigger$$ShouldTrigger` court-circuite :
         `if (SelectUnit(caster) == 0 || SelectUnit(target) == 0) return false;` -- il n'appelle
         meme pas `IdunBattle.Core.Services.BattleQuery$$IsCharging`.

    Donc `1369` est POSE puis **INERTE A VIE** : `ShouldBeActive` rend faux au tout premier
    refresh, `IdunBattle.Operations.RefreshEffectsOperation$$DeactivateEffect` ecrit
    `EffectComponent.IsActive @+0x5c = 0` et vide les cibles, et `...$$ApplyEffectsForTargets`
    (le SEUL appelant du slot `IEffect+0xe` = `ApplyModification`) n'est jamais atteint pour lui.
    La MESURE live #576 concorde exactement : apres le cast, `decisionView` publie `1368` sur la
    cible et **RIEN pour 1369** (`readEffectsByUnit` droppe `IsActive == 0`).

    ⚠ `Target@+0x60` EST renseigne AILLEURS, et c'est ce qui rend le quirk lisible plutot que
    suspect : les canaux de DEGAT batissent leur `AbilityEntities` en `(attacker, attacker,
    defender)` -- c'est ce contexte-la que lit `get_OwnerIsTarget` d'
    `AmuletOfTheVoidwyrm_CritDamageReductionEffect` (cf. `amulet_of_the_voidwyrm.py`). Le natif a
    donc mis dans un canal SANS Target une condition qui en exige un. Le `+percage` que le tooltip
    annonce vient bien du jeu -- mais de l'AUTRE effet (`1368 CreatePiercingBonusForAttack`, porte
    ci-dessus), pas de celui-ci.

    ⚠ CE QUE `is_active -> False` NE FERME PAS ENCORE, et il faut le lire : le port applique le
    `StatModifier` A LA POSE (feuille `AddStaticStatModifierEffect` -> `apply_change_stat`), la ou
    le natif ne l'applique que par `ApplyEffectsForTargets`. Le driver
    `runner/operations/refresh_effects.py::refresh_stat_modifier_effects` RETIRE desormais cette
    contribution des que la condition PORTEE est fausse (#576-r1), mais il ne tourne qu'aux
    declencheurs natifs (`TurnChanged`, `UnitPositionChanged`, degat sur la cible) : entre le cast
    et le premier de ces declencheurs, la stat reste sur-accordee. Le cran restant est le gate de
    la POSE elle-meme."""

    # La `CreateActiveCondition` est PORTEE (elle rend une CONSTANTE, ce qui reste une lecture du
    # natif) -> le flag capte/pose ne fait plus foi pour cette classe. Cf. `case-322` et la
    # docstring ci-dessus.
    active_condition_ported = True

    def is_active(self, unit_state: Mapping | None = None) -> bool:
        """`...BloodChalice_ExtraPiercingEffect$$CreateActiveCondition` evaluee dans le SEUL
        contexte qui l'evalue -- celui d'`IdunBattle.Operations.RefreshEffectsOperation$$
        ShouldBeActive`, ou `Target@ctx+0x10` est ZERO. `IsChargingTrigger$$ShouldTrigger` y rend
        donc `false` INCONDITIONNELLEMENT (cf. la chaine en 4 etages de la docstring de classe).

        `unit_state` est ignore A DESSEIN : la constante ne depend d'AUCUN etat du porteur. Ce
        n'est pas une degradation (« on ne sait pas, on ne ferme pas ») -- c'est le verdict natif,
        lu au decompile."""
        return False
