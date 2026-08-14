"""`TalismanOfRage_CritDamageReduction` (0x5ad = **1453**) -- l'axe REDUCTION du canal crit-DEGAT,
indexe sur les DEFAITES EN MELEE de la bataille. Relique des World Eaters. #998.

## IDENTITE -- TROIS enums, et 1460 designe DEUX objets differents

    EffectType            0x5ad = 1453 = TalismanOfRage_CritDamageReduction   <- CET effet
    TriggeredAbilityType  0x5b4 = 1460 = TalismanOfRage                       <- sa CONFIG
    EffectType            0x5b4 = 1460 = AmuletOfTheVoidwyrm_CritDamageReduction  <- une AUTRE relique

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.TalismanOfRageAbility$$GetEffectType` rend
litteralement `0x5ad`, et son `.ctor` est

    IdunBattle.Entities.Abilities.AOwnerEffectSpecificTriggeredAbility$$.ctor(this, 0x5b4)

dont le corps ecrit `*(int*)(this + 0x60) = type` -- le champ que relit
`AOwnerEffectSpecificTriggeredAbility$$CreateTrigger` pour construire
`OnOwnerSpecificAbilityInit(<this+0x60>)`. La config lue est donc celle de la TRIGGERED **1460**,
pas l'EffectType 1453 ; et 1460 en `EffectType` est `AmuletOfTheVoidwyrm_CritDamageReduction`, une
relique VOISINE portee par le meme canal. C'est le piege « qualifier les enums » a l'etat pur : les
deux abilities ont la meme variable (`critDmgReduction`) et le meme signe, seuls le PALIER et le
COMPTEUR different.

## POSE -- owner-effect PERMANENT, a l'init de l'ability

Meme forme qu'`AmuletOfTheVoidwyrm` : `AOwnerEffectTriggeredAbility$$CreateBehaviour` (corps de
BASE) = `If(<CreateTrigger de la sous-classe>, AddEffect(GetEffectType(), AbilityState(entities,
Owner@DSLSelectors+0x30, <l'ability elle-meme>), source = Owner, targets = Owner, turns = <zeroe>))`.
Donc **source == porteur == Owner**, pose une fois a l'initialisation, jamais expiree.

L'`AbilityState` bake dans l'`EffectComponent+0x18` est celui de la relique SUR SON PORTEUR :
l'etat TERTIAIRE (`BC.Units[].TertiaryAbilityLevel`, cf. `case-237`), relu par le foyer unique
`runner/operations/triggers/base.py::triggered_ability_state` -- exact ICI parce que la source EST
le porteur.

## LE CANAL -- `ForSubtraction`, trigger `get_OwnerIsTarget` SEUL

`IdunBattle.Entities.Effects.Loki.TalismanOfRage_CritDamageReductionEffect$$CreateCritDamageBonus`
(mirror ; `ForSubtraction` est INLINE par ghidra -- il se reconnait a l'OFFSET ECRIT dans la struct
`EffectBonus` : `+0x00` = trigger, `+0x10` = addition, `+0x18` = subtraction ; ici c'est `+0x18`
qui recoit le montant) :

    EffectBonus.ForSubtraction( get_OwnerIsTarget,
                               Multiply( ConfigVar(0x97 = critDmgReduction,
                                                   GetAbilityState(effect), config@+0x60),
                                         GetMultiplierBasedOnDefeatedInMelee() ) )

`IdunBattleLogic.Entities.DSLTriggers$$get_OwnerIsTarget` = `AreEqual(Owner@DSLSelectors+0x30,
Target@DSLSelectors+0x60)` : « le PORTEUR de cet effet est-il le DEFENSEUR du coup ? ». Aucun
`op_BitwiseAnd`, exactement comme `AmuletOfTheVoidwyrm`.

CONSOMMATION : `IdunBattle.Core.Services.DamagePrediction$$GetCritDamageBonusFromEffects` accumule
`addition - subtraction`, et `$$CalculateCriticalDamage` fait `Math.Max(0, GetStat(10) + somme)`.
Le port rend donc un entier **NEGATIF** -- mirror du terme soustractif, pas une convention locale.

## LA MAGNITUDE -- un PRODUIT, et son second facteur est PARTAGE avec un trait

`IdunBattle.Entities.Effects.Loki.TalismanOfRage_CritDamageReductionEffect$$GetCritReduction`
(statique, `(abilityState, config, dsl)`) est le MEME corps, extrait :

    DSLFormulas.Multiply( ConfigVar(0x97 = critDmgReduction, abilityState, config),
                          BlessingsOfKhorne_ModifiersEffect$$GetMultiplierBasedOnDefeatedInMelee(dsl) )

⚠ **Le second facteur n'est PAS une methode de cette classe** : le decompile appelle nommement
`IdunBattle.Entities.Effects.Loki.BlessingsOfKhorne_ModifiersEffect$$GetMultiplierBasedOnDefeatedInMelee`,
le multiplicateur du TRAIT `BlessingsOfKhorne` (1046) -- deja porte, et **deja consomme par deux
autres canaux** (`create_effect_damage_malus_for_defense`, `create_effect_damage_bonus_for_attack`
de `BlessingsOfKhorneModifiersEffect`). Le port ne le duplique donc pas : il appelle le foyer
`status.py::multiplier_based_on_defeated_in_melee`.

`AbilityVariableType 0x97 = 151 = critDmgReduction` (relu de `ability_variable_type.py`, jamais
recopie du decompile). Paliers gameconfig : `[295, 311, ..., 438]` (10). `TalismanOfRage` n'a pas de
`variablesAffectedByRarityBonus` -> le multiplicateur ne mord pas ; on le passe quand meme, parce
que c'est `ability_var` (donc la config) qui decide.

## CE QUE CE PORT A OUVERT DANS LE FOYER PARTAGE -- une branche declaree MORTE qui est VIVANTE

`GetMultiplierBasedOnDefeatedInMelee` porte un terme conditionnel a CETTE relique :

    If( ActorHasTriggeredAbility(Owner@+0x30, 0x5b4 = TalismanOfRage), <kills melee DE L'OWNER>, 0 )

Le port de `BlessingsOfKhorne` le declarait « INERTE-PAR-ROSTER : AUCUN unit du gameconfig courant
ne porte TalismanOfRage (verifie unit_map) ». **C'est FAUX, et re-mesure** : `unit_map.py find
--ability TalismanOfRage` rend **6** unites (3 `lineup` par voie `item` -- `worldEightbound`,
`worldExecutions`, `worldJakhal` -- et 3 bosses npc par voie `relic`, ou l'ability est CABLEE AU
KIT). Le verdict venait de l'angle mort #323 : `unit_map` lisait 2 voies d'attribution sur 5 et
etait **aveugle aux reliques**. La branche est donc portee -- detail : `status.py`.

## PAS D'ENTREE `ABILITY_INIT_OWNER_EFFECTS`, et c'est MESURE

`runner/operations/spawn.py::_seed_ability_owner_effects` lit `GC.unit(vid).activeAbilities +
passiveAbilities` -- le KIT gameconfig, ou une relique ne figure JAMAIS (elle arrive par
`BC.Units[].TertiaryAbility`). Une entree y serait **inerte**. Meme arbitrage que les quatre
reliques deja portees.

⚠ Nuance propre a CETTE relique, et elle n'invalide pas la regle : les 3 bosses npc la portent au
KIT (voie `relic` du gameconfig). Ils ne sont pas montables par `--equip-relic` mais par
`--explicit-stats` ; leur seeding passe par le canal de kit, pas par celui-ci.

## PAS DE `CreateActiveCondition` PROPRE -- et c'est dit, pas suppose

Les seuls symboles de la classe sont `.ctor`, `GetCritReduction` et `CreateCritDamageBonus`. On NE
pose donc PAS `active_condition_ported` : le flag `EffectComponent.IsActive` capte fait foi, comme
pour tout effet sans condition lue. (L'absence d'un symbole dans la table ne PROUVE pas qu'il n'y a
pas de surcharge -- IL2CPP deduplique les corps triviaux ; ici le choix conservateur est justement
de ne rien affirmer et de laisser le flag natif decider.)

ASCII only.
"""
from __future__ import annotations

from collections.abc import Mapping

from ..base import BaseEffect
from ..magnitude import ability_var
from .. import ctx_keys as _ctx_keys      # #1042-r5 : foyer UNIQUE des chaines de cle de ctx

_ABILITY_ID = "TalismanOfRage"      # TriggeredAbilityType 0x5b4 = 1460 (la CONFIG de la relique)
_VAR_KEY = "critDmgReduction"       # AbilityVariableType 0x97 = 151
#: callable `(owner_id, ability_name) -> (level, multiplier)` -- mirror de `GetAbilityState(effect)`.
#: MEME cle que celle posee par `_crit_board` pour les autres reliques (foyer unique du canal).
CTX_ABILITY_STATE_OF = _ctx_keys.CTX_TERTIARY_ABILITY_STATE_OF


class TalismanOfRageCritDamageReductionEffect(BaseEffect):
    """`TalismanOfRage_CritDamageReduction` (0x5ad = 1453) -- owner-effect PERMANENT de la relique
    `TalismanOfRage` : quand son porteur est la CIBLE d'un coup CRITIQUE, le degat de crit de
    l'attaquant est reduit de `critDmgReduction[niveau de relique] x N`, ou `N` est le
    multiplicateur `BlessingsOfKhorne` (defaites en MELEE de la bataille, cappe a
    `MaxDefeatedUnits`).

    DEUXIEME implementeur porte de l'axe REDUCTION du canal crit-DEGAT (`ForSubtraction`), apres
    `AmuletOfTheVoidwyrm` et `NetherRealmCasket`."""

    #: Compte BRUT (non cappe) des defaites en melee, seede par duck-typing
    #: (`entities/effects_state.py::seed_battle_counters`, foyer PARTAGE par les deux faces).
    #: `None` = **non mesure** -> l'effet est inerte, jamais un 0 invente.
    melee_defeats: "int | None" = None
    #: Kills de MELEE imputables au PORTEUR (branche `ActorHasTriggeredAbility`). Meme tri-etat.
    melee_defeats_by_owner: "int | None" = None

    def _n(self) -> int:
        """`GetMultiplierBasedOnDefeatedInMelee`, via le foyer PARTAGE.

        Import DIFFERE **PORTEUR** et forme B (module, pas symbole) : `status` et ce module sont
        tous deux tires par `effects/factory.py`, et `status` importe deja la chaine `magnitude` ->
        `gameconfig` ; passer par le module garde le foyer substituable par `monkeypatch.setattr`
        (forme A gelerait la liaison et desarmerait les contre-epreuves)."""
        from . import status as _status
        return _status.multiplier_based_on_defeated_in_melee(
            self.melee_defeats,
            self_kills=self.melee_defeats_by_owner,
            owner_has_talisman=True,          # CET effet n'existe que sur un porteur de 1460
        )

    def _ability_state(self, ctx: "Mapping | None") -> tuple:
        """`GetAbilityState(effect)` -> `(level, multiplier)` de l'`AbilityState` bake a la pose.

        `AOwnerEffectTriggeredAbility$$CreateBehaviour` bake `AbilityState(entities, Owner, <cette
        ability>)` et l'effet est pose SUR l'Owner : source == porteur, donc le couple se relit sur
        le porteur (`owner_id`). C'est l'etat TERTIAIRE quand la relique est EQUIPEE, l'etat PASSIF
        quand elle est cablee au kit d'un npc -- exactement l'arbitrage de `triggered_ability_state`
        (#357), et les DEUX regimes existent pour cette relique (3 lineup / 3 bosses).

        Callable absent (contexte sans `state` : probe, test offline) -> repli sur les niveaux que
        l'effet porte deja, comme toutes les autres classes d'effet."""
        c = ctx or {}
        fn, oid = c.get(CTX_ABILITY_STATE_OF), c.get("owner_id")
        if fn is not None and oid is not None:
            lvl, mult = fn(oid, _ABILITY_ID)
            if lvl is not None:
                return int(lvl), int(mult if mult is not None else 100)
        lvl = self.ability_level if self.ability_level is not None else self.level
        return lvl, int(self.ability_variables_multiplier or 100)

    def _owner_is_target(self, att_ctx: "Mapping | None" = None) -> bool:
        """`IdunBattleLogic.Entities.DSLTriggers$$get_OwnerIsTarget` = `AreEqual(Owner@+0x30,
        Target@+0x60)`. Identite NON PROUVEE (une des deux cles absente) => noeud FAUX, jamais
        permissif -- meme foyer de raisonnement qu'`AmuletOfTheVoidwyrmCritDamageReductionEffect`."""
        c = att_ctx or {}
        oid, tid = c.get("owner_id"), c.get("tgt_id")
        return oid is not None and tid is not None and oid == tid

    def create_effect_crit_damage_bonus_for_attack(self, att_ctx: "Mapping | None" = None) -> "int | None":
        """MIRROR de `...TalismanOfRage_CritDamageReductionEffect$$CreateCritDamageBonus` :

            EffectBonus.ForSubtraction( get_OwnerIsTarget,
                                        Multiply( ConfigVar(0x97 = critDmgReduction,
                                                            GetAbilityState(effect), config@+0x60),
                                                  GetMultiplierBasedOnDefeatedInMelee() ) )

        Retour ENTIER NEGATIF : `GetCritDamageBonusFromEffects` accumule `addition - subtraction`.

        Les etages sont SEPARES et chacun peut se taire independamment (aucun scalaire fitte) :
          1. `get_OwnerIsTarget`  -- le porteur est-il le defenseur ?
          2. le MULTIPLICATEUR    -- defaites en melee, cappe (tri-etat : non mesure => 0 => inerte)
          3. l'`AbilityState`     -- niveau/multiplicateur de la relique sur le porteur ;
          4. `ConfigVar`          -- `critDmgReduction[niveau]`, relu du gameconfig ;
          5. `Multiply`           -- le produit, puis le signe de `ForSubtraction`."""
        if not self._owner_is_target(att_ctx):                 # 1
            return None
        n = self._n()                                          # 2
        if n <= 0:
            return None
        lvl, mult = self._ability_state(att_ctx)               # 3
        v = ability_var(_ABILITY_ID, _VAR_KEY, lvl, multiplier_pct=mult)   # 4  ConfigVar(0x97)
        if v is None:
            return None
        amount = int(v) * int(n)                               # 5  Multiply
        return -amount if amount else None                     #    ForSubtraction
