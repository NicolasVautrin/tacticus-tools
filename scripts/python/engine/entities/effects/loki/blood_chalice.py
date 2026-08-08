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
extra + dir_pierce + effect_bonus, 0, 100)`). Ce qui reste OUVERT est le regime ou les deux
contribuent EN MEME TEMPS -- residu #576-r1, cf. `is_active` ci-dessous.
"""
from __future__ import annotations

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
                                         is_melee: bool | None = None) -> EffectBonus | None:
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

    ⚠ `is_active` N'EST PAS PORTEE ICI, ET C'EST DELIBERE -- `active_condition_ported` reste `False`
    (le defaut). Deux raisons MESUREES, pas supposees :
      1. `CreateActiveCondition` prend `Target@+0x60` -- l'ACTIVE TARGET du contexte d'evaluation.
         `is_active(unit_state)` du port ne recoit que l'etat du PORTEUR : la cible de l'attaque en
         cours n'y est pas threadee. Rendre `True`/`False` sans elle serait deviner.
      2. La consommation du flag differe : le natif reevalue par
         `IdunBattle.Operations.RefreshEffectsOperation$$RefreshEffect`, qui REVERSE le
         `StatModifier` quand l'effet devient inactif ; le port, lui, applique le modifier UNE FOIS
         a la pose (`AddStaticStatModifierEffect` -> `apply_change_stat`) et le reverse au retrait.
         Poser `is_active` sans brancher ce revert conditionnel ne changerait RIEN a la stat -- un
         faux-semblant de fidelite.
    CONSEQUENCE CHIFFREE, ecrite plutot que tue : le port applique `+extraPierceRatio` a la stat
    `ExtraPierceMelee` pour TOUTE la duree, la ou le natif ne la compte qu'en situation de CHARGE.
    Le port SUR-ACCORDE donc sur ce terme, exactement comme le proxy `has_moved` que #r32 a corrige
    ailleurs -- residu **#576-r1** (`docs/rl/backlog.md`), qui porte les deux volets ensemble
    (threader l'ActiveTarget jusqu'a `is_active`, et brancher le revert conditionnel).

    Aucune methode : la classe existe pour que l'effet soit NOMME dans `EFFECT_CLASSES` (sans quoi il
    retombe sur `BaseEffect` anonyme) et pour porter cette RE."""
