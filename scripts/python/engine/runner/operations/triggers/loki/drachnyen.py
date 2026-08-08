"""`IdunBattleLogic.Entities.Abilities.Triggered.Loki.Drachnyen_ExtraAttackAbility` (triggered
`0x5cd` = **1485**) -- l'attaque SUPPLEMENTAIRE d'Abaddon (`blackAbaddon`, HERO Black Legion), armee
par l'effet `0x5bf` = 1471 `Drachnyen_ExtraAttack` que pose l'active 1029. #BL-1029r,
`docs/rl/case-bl-1029-1020.md` Sec.5.1.

## Le CHEMIN DE MONTAGE : `GetDerivedTriggeredAbilities`, pas `EFFECT_TRIGGERS`

La fiche annoncait `EFFECT_TRIGGERS[1471]` (le registre indexe par EFFET). Le decompile dit autre
chose, et c'est verifie des DEUX cotes :

    idun...StaticBattleRules.ActiveAbility$$.cctor, dict range en `<statics>+0x30`
    (= celui que lit `...$$GetDerivedTriggeredAbilities`) :
        GetDerivedTriggeredAbilities[0x405 /* 1029 Drachnyen */] = [ 0x5cd /* 1485 */ ]
    -- l'unique occurrence de `0x5cd` ET de `0x405` dans tout ce cctor.

C'est donc `ACTIVE_ABILITY_TRIGGERS` (cle = le NOM gameconfig de l'ACTIVE), monte par
`IdunBattle.Entities.Factories.UnitFactory$$AddDerivedAbilities` : **toute unite qui POSSEDE
l'active 1029 porte 1485 des l'init**, independamment de tout effet. C'est le gate
`HasEffect(Owner, 0x5bf)` du trigger qui rend l'entree INERTE tant que l'active n'a pas ete castee
-- exactement le patron `Hailstrike` (1214 -> 1507, meme dict, meme forme de gate). Inscrire cette
ability dans `EFFECT_TRIGGERS` aurait pose la triggered sur un chemin que le natif n'emprunte pas,
et surtout AVEC UN OWNER FAUX (l'effet 1471 est pose sur Abaddon, donc ca aurait coincide ici --
mais par accident, pas par lecture).

## La CONFIG : celle de l'ACTIVE 1029, et il n'y a PAS d'entree `Drachnyen_ExtraAttack`

`IdunBattle.Core.Services.AbilitiesDatabase$$GetConfig(configId)` interroge, dans l'ordre :
`TriggeredAbility.GetActiveAbilityUsedForConfig` (dict `<statics>+0x48`), puis
`GetTriggeredAbilityUsedForConfig` (`+0x58`), puis `IsEnvironmentAbility`, puis le passif homonyme.
La PREMIERE branche court-circuite tout le reste :

    StaticBattleRules.TriggeredAbility$$.cctor, dict `<statics>+0x48` :
        GetActiveAbilityUsedForConfig[0x5cd /* 1485 */] = 0x405 /* 1029 Drachnyen */
    (voisins immediats du meme dict, dont le cas DEJA connu qui valide la lecture cle/valeur :
     `0x5c1->0x4b3`, **`0x5cd->0x405`**, `0x5d1->0x4b7`, **`0x5e3->0x4be`** = Hailstrike_Attack ->
     Hailstrike)

`1485` lit donc `minDmg`/`maxDmg`/`nrOfHits`/`damageProfile` de la config **`Drachnyen`** -- ce qui
est heureux, puisque le gameconfig n'a AUCUNE entree `Drachnyen_ExtraAttack` (verifie : 572
abilities, une seule contient << Drachnyen >>). Sans cette lecture, le port aurait invente une
magnitude.

## `$$CreateTrigger` (MIRROR du decompile, build `rnca9r7q6c`)

    On( 0x26 = NormalAttack, ownerNeedsToBeAlive = 1 )
    & get_OwnerIsCaster
    & IsMeleeAttack
    & <DSLTriggers+0x20>                                     # = `OwnerIsAlive`, cf. plus bas
    & HasEffect( Owner@DSLSelectors+0x30, 0x5bf = 1471, 0, 6 )
    & AmountIsGreaterThanZero( NonSteppableUnits( AdjacentEnemies(Owner@+0x30, 1, 3), 3 ) )

DEUX corrections a la fiche, toutes deux LUES :
 * `<dsl+0x98>` y etait note comme un verrou non identifie. Le slot est `<DSLTriggers+0x20>`, et il
   EST identifie depuis #448-r1 : `IdunBattle.Entities.Triggers.OwnerIsAliveAbilityTrigger`
   (`entities/triggers.py::OwnerIsAlive`), le singleton qu'`IdunBattleLogic.Entities.DSLTriggers$$
   InitializeShared` alloue avec le `MatchState`. Il est REDONDANT ici avec le
   `ownerNeedsToBeAlive = 1` du `On(...)`, mais on le porte parce qu'il est ecrit.
 * le sélecteur est `NonSteppableUnits`, PAS `NonSteppableOrObjectUnits` : le volet
   `UnitsWithoutTrait(0xd = Object)` n'existe pas ici (cf. `selectors/units.py`).

## `$$CreateBehaviour` (MIRROR du decompile)

    damage  = MinMaxDamage(this, abilityState)               # RandomAmount(minDmg[lvl], maxDmg[lvl])
    pool    = NonSteppableUnits( AdjacentEnemies(Owner@+0x30, 1, 3), 3 )
    target  = First( SortUnitsByDamageUtility(pool, damage, 3, null), 1 )
    profile = GetDamageProfileOrDefault(0x14 = Piercing)     # config 1029 -> `Piercing`
    hits    = GetHits()                                      # GetNumberConstant(0x2f) -> nrOfHits = 3
    AttackWithAttackDamage( Behaviors@dsl+0x78, caster = Owner@+0x30, targets = target,
                            damage, Nullable(profile), hits, AbilityOrEffect(this.Id), <opts>, 2 )

`$$ValidTargets` = le MEME `NonSteppableUnits(AdjacentEnemies(Owner, 1, 3), 3)`.

⚠ **L'ATTAQUANT EST L'OWNER**, pas l'acteur de l'evenement : le 2e argument d'`AttackWithAttackDamage`
est `*(DSLSelectors+0x30)`. Sur une triggered `OwnerIsCaster` les deux coincident, mais c'est le
littéral qui est porte.

## `SortUnitsByDamageUtility` -- le noeud que la fiche disait MANQUANT

Il ne l'est plus : `engine/runner/operations/damage_utility.py` le porte integralement depuis
#494-r1-r1 (cle = la PREDICTION COMPLETE par cible, armure/percage/defense compris ; tri decroissant
STABLE ; `damageProfile: null` -> percage 0). Le collapse `First(SortUnitsByDamageUtility(...), 1)`
= `first_by_damage_utility`, doctrine deja appliquee a FinalJustice / AncestralFortune / Doombolt /
KillMaimBurn.

La surcharge appelee est celle a 5 arguments (`this, targets, damage, unitSelectionType, hits`), qui
remplit elle-meme `caster = DSLSelectors+0x48`, `ability = DSLSelectors+0x88` et
`utilityDefinition = new UtilityDefinition(0x23 = UtilityType.Damage)`. `hits` vaut `null` -> la
prediction de tri porte sur **UN** coup, comme les quatre autres call-sites portes.

⚠ **UN TIRAGE PRNG dans la cle de tri.** `SortUnitsByDamageUtilitySelector$$Select` appelle
`damage.Calculate(entities)` UNE fois, avant la boucle par cible ; `damage` est ici `MinMaxDamage` =
`RandomAmount(minDmg, maxDmg)`, dont le `Calculate` finit sur le PRNG de BATAILLE. C'est la meme
lecture que `KillMaimBurnNextTarget` (`abilities/worldeaters.py`), ou elle a ete MESUREE au tirage
pres (#504 : 24 tirages natifs contre 20 pour un port qui n'evaluait pas). Le port consomme donc ce
tirage, au meme endroit, AVANT les tirages par coup de l'attaque.
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....components import OwnerComponent, StatsComponent, UnitComponent
from ....abilities.behaviours.combat import AttackWithAttackDamage
from ....abilities.behaviours.context import entities_from_state
from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.damage_profile_type import DamageProfileType
from .....entities.effect_type import EffectType
from .....entities.formulas import RandomAmount
from .....entities.selectors.accessors import Target
from .....entities.selectors.tiles import Caster
from .....entities.selectors.units import AdjacentEnemies, non_steppable_units
from .....entities.effects.magnitude import ability_var
from .....entities.triggered_ability_type import TriggeredAbilityType
from ...damage_utility import first_by_damage_utility
from ..base import TriggeredAbility, TriggerEvent

#: La CONFIG lue par `BaseTriggeredAbility$$MinMaxDamage` / `$$GetHits` / `$$GetDamageProfileOrDefault`
#: -- celle de l'ACTIVE 1029, resolue par `GetActiveAbilityUsedForConfig[1485] = 1029` (cf. en-tete).
DRACHNYEN_ABILITY = "Drachnyen"
DRACHNYEN_EXTRA_ATTACK_EFFECT = int(EffectType.Drachnyen_ExtraAttack)            # 0x5bf = 1471
DRACHNYEN_EXTRA_ATTACK_TRIGGERED = int(TriggeredAbilityType.Drachnyen_ExtraAttack)   # 0x5cd = 1485

#: `GetDamageProfileOrDefault(0x14)` -- le DEFAUT natif si la config ne definit pas de profil.
#: `DamageProfileType(20) = Piercing`. La config 1029 en definit un (`Piercing` aussi) -> ce defaut
#: n'est jamais retenu ; il reste porte pour ne pas maquiller le decompile.
_DEFAULT_PROFILE = DamageProfileType.Piercing.name


def _damage_profile_or_default() -> str:
    """`IdunBattle.Entities.Abilities.BaseTriggeredAbility$$GetDamageProfileOrDefault(defaultValue)` =
    `AbilityConfiguration.GetDamageProfile() ?? defaultValue`, sur la config `Drachnyen`."""
    import gameconfig as _GC
    v = ((_GC.ability(DRACHNYEN_ABILITY) or {}).get("constants") or {}).get("damageProfile")
    return str(v) if v else _DEFAULT_PROFILE


def drachnyen_extra_attack_targets() -> "object":
    """`$$ValidTargets` (et le `pool` du behaviour, MEME expression) :
    `NonSteppableUnits( AdjacentEnemies(Owner@DSLSelectors+0x30, 1, 3), 3 )`.

    `Caster()` = l'Owner : sur une triggered gatee `OwnerIsCaster`, les deux slots coincident, et
    c'est `Caster()` que le contexte du port materialise."""
    return non_steppable_units(AdjacentEnemies(Caster(), Const(1)))


def drachnyen_extra_attack_tree(hits: int, profile: str) -> AttackWithAttackDamage:
    """Arbre de `$$CreateBehaviour` (MIRROR) :

        AttackWithAttackDamage( caster = Owner@+0x30, targets = <la cible resolue>,
                                MinMaxDamage, Nullable(profile), hits,
                                AbilityOrEffect(1485) )

    La factory native est `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` (LU sur les
    callees, pas devine au nom) -> famille ATTACK (`native_factory="attack"`, le defaut), donc
    `AttackBehaviour` neuf par cible : crit/block et 2 tirages par coup a `critChance = 0`.

    Le SELECTEUR `First(SortUnitsByDamageUtility(pool, damage, 3, null), 1)` est COLLAPSE en amont
    (`execute_behaviour`) et la cible RESOLUE passee via `Target()` -- meme doctrine que
    `psyker.py` / `final_justice.py` : le selecteur AI-target n'a pas d'equivalent noeud.

    Mode BORNES (pas `amount`) : `MinMaxDamage(abilityState)` EST la paire `minDmg`/`maxDmg` de la
    config, que la feuille relit par `ability_attack_params(DRACHNYEN_ABILITY, profile)` -- le
    `RandomAmount` par coup est fait par le pipeline d'attaque, exactement comme le natif re-evalue
    son noeud de degat par coup. `level_slot="active"` (defaut) : la config 1029 est l'ACTIVE
    d'Abaddon, donc `activeAbilityLevel`.

    `is_melee=True` : LU du sélecteur, pas d'un litteral de config (1029 n'a pas d'`attackRangeType`)
    -- le pool EST `AdjacentEnemies`, donc toute cible est au contact."""
    return AttackWithAttackDamage(Target(), DRACHNYEN_ABILITY, profile, is_melee=True,
                                  hits=int(hits),
                                  ability_type=DRACHNYEN_EXTRA_ATTACK_TRIGGERED)


class DrachnyenExtraAttackAbility(TriggeredAbility):
    """`Drachnyen_ExtraAttackAbility` (triggered 1485) -- cf. l'en-tete du module pour les deux arbres
    natifs. `owner_id` = l'unite qui POSSEDE l'active 1029 (Abaddon), instanciee par le registre
    `ACTIVE_ABILITY_TRIGGERS` (mirror de `GetDerivedTriggeredAbilities`)."""
    event_id = EventTriggerType.NormalAttack        # On(0x26, ownerNeedsToBeAlive = 1)
    TRIGGERED_ABILITY_ID = TriggeredAbilityType.Drachnyen_ExtraAttack

    def _pool(self, state: State) -> list:
        """`NonSteppableUnits(AdjacentEnemies(Owner, 1, 3), 3)` -- evalue par le MEME arbre DSL des
        DEUX cotes (gate du trigger et pool du behaviour), comme le natif qui construit la meme
        expression dans `$$CreateTrigger`, `$$CreateBehaviour` et `$$ValidTargets`."""
        sel = drachnyen_extra_attack_targets()
        return list(sel.evaluate(entities_from_state(state, self.owner_id)) or [])

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        if ev.actor_id is None or int(ev.actor_id) != int(self.owner_id):
            return False                                   # get_OwnerIsCaster
        # `IsMeleeAttack` : `ev.ranged` est la nature du coup threadee par le vecteur (voie normale :
        # arme selectionnee par adjacence). MELEE == `not ranged` -- meme lecture que le gate
        # symetrique de `psyker.py` (`IsRangedAttack` -> `ev.ranged`).
        if ev.ranged:
            return False
        owner = state.get_entity(self.owner_id)
        uc = owner.get_component(UnitComponent) if owner is not None else None
        if uc is None or not uc.alive:                     # <DSLTriggers+0x20> = OwnerIsAlive
            return False                                   # (redondant avec ownerNeedsToBeAlive = 1)
        if state.effects is None or not state.effects.has_effect(     # HasEffect(Owner, 0x5bf, 0, 6)
                int(self.owner_id), effect_type=DRACHNYEN_EXTRA_ATTACK_EFFECT):
            return False
        return bool(self._pool(state))                     # AmountIsGreaterThanZero(pool)

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        pool = self._pool(state)
        if not pool:
            return None
        e = state.get_entity(self.owner_id)
        sc = e.get_component(StatsComponent) if e is not None else None
        ctx = getattr(sc, "ctx", None) if sc is not None else None
        if ctx is None:
            return None
        lvl = getattr(ctx, "active_ability_level", None)   # MinMaxDamage(abilityState) : ability ACTIVE
        mult = int(getattr(ctx, "ability_variables_multiplier", 100) or 100)
        bmin = int(ability_var(DRACHNYEN_ABILITY, "minDmg", lvl, multiplier_pct=mult) or 0)
        bmax = int(ability_var(DRACHNYEN_ABILITY, "maxDmg", lvl, multiplier_pct=mult) or 0)
        hits = int(ability_var(DRACHNYEN_ABILITY, "nrOfHits", is_constant=True) or 0)
        if not hits or not bmax:
            return None                                    # config incomplete -> pas d'attaque inventee
        ents = entities_from_state(state, self.owner_id, None)
        # `damage.Calculate(entities)` du selecteur de tri -- UN tirage, AVANT la boucle par cible
        # (cf. l'en-tete : meme lecture que `KillMaimBurnNextTarget`, mesuree au tirage pres #504).
        roll = int(RandomAmount(Const(bmin), Const(bmax),
                                rng=getattr(state, "rng", None)).calculate(ents))
        # `First(SortUnitsByDamageUtility(pool, damage, 3, null), 1)` : argmax du composite
        # `UtilityType.Damage`, ordre source = celui du selecteur (tri natif STABLE). `hits = null`
        # -> la cle predit UN coup, d'ou `hits=1`. Le noeud d'ability du selecteur
        # (`DSLSelectors+0x88`) est NUL -> le foyer resout l'ARME NORMALE du caster, comme pour
        # `AncestralFortune` (meme surcharge 5-args).
        ids = [u.get("id") for u in pool if u.get("id") is not None]
        best = first_by_damage_utility(state, ids, roll, roll, owner_id=int(self.owner_id), hits=1)
        if best is None:
            return None
        profile = _damage_profile_or_default()
        ectx = ExecutionContext(state=state, rng=state.rng)
        drachnyen_extra_attack_tree(hits, profile).execute(
            entities_from_state(state, self.owner_id, int(best)), ectx)
        hit = next((p for n, p in ectx.emitted if n == "AttackWithAttackDamage"), None)
        atk = (hit or {}).get("attack") or {}
        # ⚠ DIAGNOSTIC SERIALISABLE : on n'expose PAS l'`atk` brut. `attack_state` y porte
        # `failed_block`, un **`set`** (`operations/damage_hits.attack_state_out`), et le retour d'un
        # trigger remonte dans `AbilityHandler.last`, que les probes passent a `json.dumps`. Un port
        # qui renvoie l'objet entier fait donc TOMBER l'oracle de mesure sur un `TypeError`, pas sur
        # une divergence -- exactement le genre d'echec de MONTAGE qui se lit comme un resultat.
        return {"ability": "Drachnyen_ExtraAttack", "owner": int(self.owner_id),
                "target": int(best), "roll": roll, "hits": hits, "profile": profile,
                "pool": ids, "total": atk.get("total"), "per_hit": atk.get("per_hit"),
                "base": atk.get("base"), "pierce": atk.get("pierce"),
                "additional_hits": atk.get("additional_hits")}


def _team_of(state: State, uid: Optional[int]):
    """Helper de diagnostic (les gates natifs d'equipe vivent dans `AdjacentEnemies`)."""
    e = state.get_entity(uid) if uid is not None else None
    oc = e.get_component(OwnerComponent) if e is not None else None
    return oc.team if oc is not None else None
