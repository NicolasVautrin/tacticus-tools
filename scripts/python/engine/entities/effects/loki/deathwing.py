"""`IdunBattle.Entities.Effects.Loki.DeathwingEffect` (`EffectType 0x526 = 1318`) -- l'effet posE par
le passif `Deathwing` (`TriggeredAbilityType 0x4dd = 1245`) de `darkaTerminator` << Baraqiel >>
(#932). Il porte les DEUX faces de degat d'un meme effet, ce qui est rare :

  * `CreateEffectDamageBonusForAttack`   -> +degat SORTANT (melee ou attaque d'ability) ;
  * `CreateEffectDamageMalusForDefense`  -> -degat ENTRANT (toutes attaques recues).

i2 `UnitEffects/Deathwing_Description` : << All incoming damage is reduced by {dmgReductionCurrent}.
Outgoing melee and *Plasma Cannon* damage is increased by {extraDmgCurrent}. Effect is doubled
against Chaos enemies or when standing adjacent to a friendly Dark Angel. >>

===================================================================================================
LA PARENTE EST LUE DANS `frida/classes.tsv`, PAS DANS LE PSEUDO-C
===================================================================================================

    IdunBattle.Entities.Effects.Loki.DeathwingEffect  ->  IdunBattle.Entities.Effects.BaseEffect

Le `.ctor` (`DeathwingEffect$$.ctor(triggeringAbilityType)` = `BaseEffect..ctor(this,
AbilityOrEffect(<arg>), hasAutomaticActivation: true)`) partage son corps, par ICF, avec ceux de
`FuryOfTheAncientsEffect` et `MischiefMakersEffect`, qui derivent eux de `HealBlockingEffect`
(cf. `heal_blocking.py`). Suivre le pseudo-C dans un sens ou dans l'autre donne la mauvaise
mecanique -- c'est exactement le piege que #927 a documente, et le nom `DeathwingEffect` en est le
declencheur. Ici la table des CLASSES dit `BaseEffect`, et les quatre overrides de DEGAT que la
classe declare le confirment.

===================================================================================================
CE QUE LA CLASSE DECLARE (`global-metadata.dat`, `il2cpp_metadata.type_methods`) -- 7 entrees
===================================================================================================

    [.ctor, CreateActiveCondition (slot 62), CreateTargetSelector (slot 64),
     CreateEffectDamageBonusForAttack (78), CreateEffectDamageMalusForDefense (80),
     GetEffectAmount, GetDoubleEffectCondition]

Les DEUX premieres n'ont AUCUN symbole propre (corps fondus par l'ICF) : elles sont lues dans le
bloc `methodPointers` du PE, ancre sur le `.ctor` et INDEXE par la position metadata --

    CreateActiveCondition -> corps partage avec `WisdomOfTheAncients_DamageReductionEffect`
                             = `return <DSLTriggers+0x70>` = `YesTrigger` -> TOUJOURS ACTIF ;
    CreateTargetSelector  -> corps partage avec `WhisperingWebEffect`
                             = `return <DSLSelectors+0x30>` = `Owner` -> SELF-effect.

Donc : aucune `active_condition_ported`, aucun selecteur d'aura -- l'effet vit sur son porteur et y
reste actif tant qu'il n'a pas expire.

===================================================================================================
LES ARBRES (mirror 1:1 du decompile)
===================================================================================================

`IdunBattle.Entities.Effects.Loki.DeathwingEffect$$CreateEffectDamageBonusForAttack` :

    EffectBonus.ForAddition(
        get_OwnerIsActor & ( IsMeleeAttack() | NOT IsNormalAttack() ),
        GetEffectAmount( ConfigVar(AbilityVariableType.extraDmg = 8, GetAbilityState(this),
                                   config@this+0x60),
                         isDefense: false ),
        AbilityOrEffect(<source de l'effet>) )

`IdunBattle.Entities.Effects.Loki.DeathwingEffect$$CreateEffectDamageMalusForDefense` :

    EffectBonus.ForSubtraction(
        get_OwnerIsTarget,
        GetEffectAmount( ConfigVar(AbilityVariableType.dmgReduction = 0x12 = 18,
                                   GetAbilityState(this), config@this+0x60),
                         isDefense: true ),
        AbilityOrEffect(<source de l'effet>) )

`IdunBattle.Entities.Effects.Loki.DeathwingEffect$$GetEffectAmount(baseAmount, isDefense)` :

    amt = Multiply( baseAmount, EffectLevel(Effect@DSLSelectors+0x38) )
    return DSLFormulas.If( GetDoubleEffectCondition(isDefense), Double(amt), amt )

`IdunBattle.Entities.Effects.Loki.DeathwingEffect$$GetDoubleEffectCondition(isDefense)` :

    X   = isDefense ? Actor@DSLSelectors+0x40 : Target@DSLSelectors+0x60
    cnt = UnitsFromFaction( AdjacentFriends(Owner@+0x30, unique: true,
                                            UnitSelectionType.OnlyAliveAndTargetable = 3),
                            UnitFaction.DarkAngels = 0xa,
                            UnitSelectionType.OnlyAliveAndTargetable = 3 )
    return ( HasTrait(X, UnitTrait 0x7ea = grande-alliance Chaos)
             & AreEnemies(X, Owner@+0x30, UnitTeamSelectionType 0) )
           | AmountIsGreaterThanZero(cnt)

## Les SURCHARGES sont tranchees par leurs XREFS ENTRANTES, jamais par le pseudo-C

  * `UnitsFromFaction(entities, faction: UnitFaction, unitSelectionType)` -- l'overload ENUM
    (`0x180eb3d30`), pas celui qui prend un `System.String` (`0x180eb3c80`) ;
  * `AmountIsGreaterThanZero(amount: ITargetsSelector)` (`0x180ed5360`) -- << le selecteur rend au
    moins une entite >>, pas l'overload `IAmountFormula` ;
  * `AdjacentFriends(unit, unique: bool, selectionType)` (`0x180eac2a0`), pas la variante B
    `(unit, unitTile, unique)` ;
  * `IsMeleeAttack()` / `IsNormalAttack()` -- les surcharges SANS argument ;
  * `ConfigVar(variableType, abilityState: IAbilityStateSelector, config: AbilityConfiguration)`.

## LES DEUX FACES N'ONT PAS LE MEME GATE, ET CE N'EST PAS UNE SYMETRIE

Le bonus d'ATTAQUE porte `IsMeleeAttack() | NOT IsNormalAttack()` -- une attaque a DISTANCE et
NORMALE n'en beneficie pas, alors que TOUTE attaque d'ability (donc `PlasmaCannon`, ranged) en
beneficie. C'est le << melee or Plasma Cannon >> de l'i2, mais ecrit PLUS LARGE que lui : le natif ne
nomme pas `PlasmaCannon`, il dit << pas une attaque normale >>. Le malus de DEFENSE, lui, n'a
AUCUN gate de nature : toutes les attaques recues sont reduites.

## CANAL DE PORT -- lu aux OFFSETS de la struct `EffectBonus`, pas au nom de la fabrique

Les deux corps construisent le `Nullable<EffectBonus>` A LA MAIN (ecriture directe des champs puis
`Nullable<>..ctor`), sans appeler `ForAddition`/`ForSubtraction`. L'offset ECRIT tranche :

    EffectBonus  +0x00 Trigger · +0x08 PercentIncrease · +0x10 Addition · +0x18 Subtraction
                 +0x28 Override · +0x30 <int32> · +0x34..+0x4c AbilityOrEffect

(offsets releves dans `IdunBattle.Entities.Effects.EffectBonus$$ForAddition` /
`$$ForSubtraction` / `$$ForPercentIncrease`). La face ATTAQUE ecrit `+0x10` -> `for_addition` ;
la face DEFENSE ecrit `+0x18` -> `for_subtraction(owner_is_caster = False)` = `flat_reductions`,
plat PRE-percage cote defenseur (famille Nightshroud, #120).

## MAGNITUDE

`extraDmg` et `dmgReduction` sont TOUS DEUX dans `variablesAffectedByRarityBonus` du gameconfig
`Deathwing` -> scale par le multiplicateur de rarete du porteur. Les deux tableaux ont 65 paliers
(`extraDmg[L50] = 112`, `dmgReduction[L50] = 112`, tous deux `146` a L65).
`GetAbilityState(this)` sur un `AbilityOrEffect` TRIGGERED resout le niveau du PASSIF du porteur ->
`self.ability_level` (jamais `active_ability_level`), meme cascade que `CamoCloak`/`FuelledByFury`.

## LE NIVEAU DE L'EFFET EST UN FACTEUR, PAS UN DECOR

`Multiply(baseAmount, EffectLevel(Effect))` : la magnitude est `V x niveau de l'instance`. Le
niveau monte de 1 a CHAQUE blocage (face TRIGGER, `runner/operations/triggers/loki/deathwing.py`)
et l'effet expire apres `TurnsFromRounds(1)`. Le niveau abouti arrive tel quel dans
`decisionView.effects[].level` -> on lit `self.level`, sans recalcul offline (meme regime que
`FuelledByFury_ExtraDamage` / `TerrifyingCrescendo_ExtraDmg` / `BeaconOfRage_ExtraDamage`).
Niveau ou niveau d'ability inconnu -> INERTE (degradation fidele, meme regle que ses trois jumeaux).

## LE PREDICAT DE DOUBLEMENT ET SON SUBSTRAT (tri-etat STRICT)

Les trois noeuds du `GetDoubleEffectCondition` sont threades dans le contexte per-coup, aux MEMES
cles et avec la MEME semantique des deux cotes (COMBAT `runner/damage_model.py`, PREDICTION
`playbook/prediction/`) -- un seul cote elargi recreerait le fork << ce que le moteur fait != ce
que la prediction annonce >> :

    face ATTAQUE (`att_ctx`)     : `tgt_grand_alliance`, `tgt_team`, `att_team`,
                                   `adjacent_dark_angels_friends`
    face DEFENSE (`attacker_ctx`): `grand_alliance`, `team`, `owner_team`,
                                   `adjacent_dark_angels_friends`

CLE ABSENTE => le DISJOINT concerne est FERME (degradation RESTRICTIVE : on sous-estime, on
n'invente jamais un doublement). Le compteur d'amis Dark Angels est un TRI-ETAT (`None` = porteur
sans equipe ni tuile), jamais un 0 rabattu.
"""
from __future__ import annotations

from collections.abc import Mapping

from ....services.effect_bonus import EffectBonus, for_addition, for_subtraction
from ..base import BaseEffect, is_melee_attack
from ..magnitude import ability_var
from ....dsl.base import Const
from ...selectors.accessors import Owner
from ...selectors.units import AdjacentFriends, UnitsFromFaction
from ...unit_faction import UnitFaction
from ...unit_selection_type import UnitSelectionType

#: cle gameconfig de l'ability (`TriggeredAbilityType.Deathwing = 0x4dd = 1245`) -- l'`AbilityOrEffect`
#: que le `.ctor` de l'effet passe a `BaseEffect`, et donc la config que `ConfigVar` indexe.
ABILITY_ID = "Deathwing"
#: #1073 -- la MEME classe native `DeathwingEffect` sert le passif `DeathwingKnight`, avec une AUTRE
#: config. C'est LU dans `EffectsDatabase.u003Cu003Ec$$u003CInitializeEffectsu003Eb__14_340`, qui
#: construit `DeathwingEffect..ctor(this, 0x5e6)` la ou `...b__14_339` passe `0x4dd` : le seul
#: parametre du `.ctor` est `triggeringAbilityType:IdunBattle.Entities.Enum.TriggeredAbilityType`
#: (`frida/methods.tsv`), donc l'`AbilityOrEffect` du `BaseEffect` -- et donc la config du `ConfigVar`.
ABILITY_ID_KNIGHT = "DeathwingKnight"
#: alias de portee : dans un corps de CLASSE, `ABILITY_ID = ABILITY_ID` se resout bien (le nom n'est
#: pas encore lie dans l'espace de la classe) mais se lit comme une auto-reference. L'alias rend la
#: source LUE explicite.
_ABILITY_ID_BARAQIEL = ABILITY_ID
#: `AbilityVariableType 8` / `0x12 = 18` (`frida/enums.tsv`, jamais recopies du decompile).
VAR_EXTRA_DMG = "extraDmg"
VAR_DMG_REDUCTION = "dmgReduction"
#: `UnitTrait 0x7ea = 2026` -- grande-alliance Chaos, DERIVEE du `GrandAllianceId` par
#: `idun.Idun.Source.Shared.GrandAlliance$$GetTrait` (Imperial 26 · Xenos 0x3ee · Chaos 0x7ea).
#: Elle n'est PAS dans le `traits` gameconfig : c'est le BattleConfiguration qui l'ajoute (meme
#: derivation que `dark_angels_passives._GRAND_ALLIANCE_CHAOS` et `RitesOfBattle`/`BeaconOfRage`).
GRAND_ALLIANCE_CHAOS = "Chaos"
#: `UnitSelectionType 3` -- le litteral que le natif propage aux DEUX etages du compteur.
_SEL = int(UnitSelectionType.OnlyAliveAndTargetable)
#: cles du contexte per-coup (cf. l'en-tete). Le compteur porte le MEME nom des deux cotes.
CTX_ADJACENT_DA = "adjacent_dark_angels_friends"


def adjacent_dark_angels_friends_selector():
    """L'ARBRE DSL du SECOND disjoint de `...DeathwingEffect$$GetDoubleEffectCondition`, noeud par
    noeud (doctrine #149 : l'artefact natif est un SELECTEUR, donc le port est un arbre) :

        UnitsFromFaction( AdjacentFriends(Owner@+0x30, unique: true, selectionType: 3),
                          UnitFaction.DarkAngels = 0xa, selectionType: 3 )

    `reference=Owner()` est passe EXPLICITEMENT a `AdjacentFriends` : la reference d'equipe du
    `Friends` natif EST le centre (`Friends(reference = unit, ...)`), et le defaut du port
    (`ctx.caster`) ne coinciderait que tant que le contexte est bati sur le porteur.

    `UnitsFromFaction` compare le `FactionId` gameconfig au NOM de la valeur d'enum -- c'est ce que
    le natif fait (`System.Enum.ToString(UnitFaction)` puis `String.Equals` sur
    `FactionComponent+0x30`), et c'est pourquoi la constante est `UnitFaction.DarkAngels.name` et
    non l'ordinal `10`.

    Import PARESSEUX de `Count` : `entities/formulas` est assemble APRES le package
    `entities/effects` (meme garde anti-cycle et meme convention que `kardiocore_galvanus` et
    `nether_realm_casket`)."""
    from ...formulas import Count

    return Count(UnitsFromFaction(AdjacentFriends(Owner(), Const(1), Owner(), _SEL),
                                  UnitFaction.DarkAngels.name, _SEL))


class DeathwingEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.DeathwingEffect` (`EffectType 0x526 = 1318`). Cf. l'en-tete
    du module pour les quatre arbres natifs, la parente lue dans `classes.tsv` et le tri-etat des
    cles de contexte.

    PAS d'`active_condition_ported` : la `CreateActiveCondition` native est `<DSLTriggers+0x70>` =
    `YesTrigger`, constante VRAIE. Le regime commun (`BaseEffect.is_active`) coincide, et poser le
    flag inventerait un gate que le decompile ne porte pas."""

    #: #1073 -- la cle gameconfig est un attribut de CLASSE, pas la constante de module : la MEME
    #: classe native sert DEUX `EffectType` avec DEUX configs (cf. `ABILITY_ID_KNIGHT`). Le
    #: `ConfigVar` natif s'indexe sur l'`AbilityOrEffect` passe au `.ctor`, qui differe par instance.
    ABILITY_ID = _ABILITY_ID_BARAQIEL

    # -- `GetDoubleEffectCondition(isDefense)` ------------------------------------------------------

    @staticmethod
    def _adjacent_dark_angels(ctx: Mapping | None) -> "int | None":
        """`AmountIsGreaterThanZero( UnitsFromFaction(AdjacentFriends(Owner, 1, 3), DarkAngels, 3) )`
        -- le compteur EVALUE pour le PORTEUR de cette instance.

        Sur les DEUX canaux de degat, le porteur de l'effet EST l'unite dont le builder itere les
        effets (`unit_id`) : la valeur est donc posee directement par le builder, pas via un
        callable per-instance (contraste les compteurs du canal CRIT, ou la boucle native reecrit
        `AbilityEntities+0x18` a chaque iteration).

        TRI-ETAT : cle absente ou `None` => `None` = << non mesure >>, JAMAIS 0. Un 0 invente
        fermerait le disjoint en silence et ferait passer un doublement reel pour son absence."""
        n = (ctx or {}).get(CTX_ADJACENT_DA)
        return None if n is None else int(n)

    @classmethod
    def _double_effect_condition(cls, ctx: Mapping | None, *,
                                 other_grand_alliance, other_team, owner_team) -> bool:
        """`GetDoubleEffectCondition` -- `( HasTrait(X, Chaos) & AreEnemies(X, Owner) ) | <cnt> > 0`,
        ou `X` est la CIBLE du coup cote attaque et l'ACTEUR (l'attaquant) cote defense.

        Chaque disjoint se ferme independamment quand SON substrat manque : le natif rend un
        `op_BitwiseOr`, donc un disjoint indecidable ne doit pas contaminer l'autre."""
        n = cls._adjacent_dark_angels(ctx)
        if n is not None and n > 0:                       # AmountIsGreaterThanZero(<selecteur>)
            return True
        if other_grand_alliance != GRAND_ALLIANCE_CHAOS:  # HasTrait(X, 0x7ea)  (None -> FERME)
            return False
        if other_team is None or owner_team is None:      # AreEnemies(X, Owner) non mesure -> FERME
            return False
        return int(other_team) != int(owner_team)

    def _amount(self, ctx: Mapping | None, var_key: str, *, doubled: bool) -> "int | None":
        """`GetEffectAmount(baseAmount, isDefense)` =
        `If(<condition>, Double(Multiply(base, EffectLevel)), Multiply(base, EffectLevel))`.

        `Multiply` natif est un produit d'ENTIERS (`MultiplyAmount$$Calculate`) : la valeur de config
        est arrondie par `ability_var` AVANT d'etre multipliee, et `Double` s'applique au produit."""
        lvl = self.level                                  # EffectLevel(Effect@DSLSelectors+0x38)
        if not lvl or int(lvl) <= 0:
            return None
        if self.ability_level is None:                    # ConfigVar sans AbilityState -> inerte
            return None
        # #1073 -- `self.ABILITY_ID`, pas la constante de module : `DeathwingKnightEffect` lit la
        # config `DeathwingKnight`. Les deux tables sont DISTINCTES dans le gameconfig (meme si leurs
        # 65 paliers coincident sur CE build) -- indexer les deux sur `Deathwing` serait un fit.
        per = ability_var(self.ABILITY_ID, var_key, self.ability_level,
                          multiplier_pct=self.ability_variables_multiplier)
        if not per:
            return None
        amt = int(per) * int(lvl)
        return amt * 2 if doubled else amt

    # -- face ATTAQUE ------------------------------------------------------------------------------

    def create_effect_damage_bonus_for_attack(self, is_ranged: bool | None = None,
                                              has_moved: bool | None = None,
                                              target_traits=None, is_prediction: bool = False,
                                              is_normal_attack: bool | None = True,
                                              target_armor_reduced: bool | None = None,
                                              att_ctx=None) -> EffectBonus | None:
        """`...DeathwingEffect$$CreateEffectDamageBonusForAttack` =
        `ForAddition( get_OwnerIsActor & (IsMeleeAttack | NOT IsNormalAttack),
                      GetEffectAmount(ConfigVar(extraDmg), isDefense: false) )`.

        `get_OwnerIsActor` est satisfait STRUCTURELLEMENT sur ce canal : l'agregateur n'itere que
        les effets de l'ATTAQUANT.

        Le disjoint `IsMeleeAttack | NOT IsNormalAttack` : nature du coup INCONNUE (`is_ranged` a
        `None`) => `is_melee_attack` rend Faux, et `is_normal_attack` a `None` ferme aussi le second
        terme -- aucune contribution, degradation fidele."""
        c = att_ctx or {}
        melee = is_melee_attack(is_ranged)                # IsMeleeAttack()
        not_normal = (is_normal_attack is False)          # NOT IsNormalAttack()  (None -> FERME)
        if not (melee or not_normal):
            return None
        doubled = self._double_effect_condition(
            c,
            other_grand_alliance=c.get("tgt_grand_alliance"),   # HasTrait(Target@+0x60, 0x7ea)
            other_team=c.get("tgt_team"),                       # AreEnemies(Target@+0x60, Owner)
            owner_team=c.get("att_team"))                       #   -- l'Owner EST l'attaquant ici
        amt = self._amount(c, VAR_EXTRA_DMG, doubled=doubled)
        return for_addition(True, amt) if amt else None         # EffectBonus +0x10 = Addition

    # -- face DEFENSE ------------------------------------------------------------------------------

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                               damage_profile: str | None = None,
                                               attacker_ctx: Mapping | None = None
                                               ) -> EffectBonus | None:
        """`...DeathwingEffect$$CreateEffectDamageMalusForDefense` =
        `ForSubtraction( get_OwnerIsTarget, GetEffectAmount(ConfigVar(dmgReduction),
        isDefense: true) )`.

        `get_OwnerIsTarget` est satisfait STRUCTURELLEMENT sur ce canal (le builder n'itere que les
        effets de la CIBLE), et c'est le SEUL noeud du trigger : **aucun** gate de nature de coup
        (contraste la face ATTAQUE), **aucun** gate de profil de degat (contraste `TerminatorArmour`,
        que le meme porteur transporte via son trait).

        `for_subtraction(owner_is_caster = False)` = le bac `flat_reductions`, plat PRE-percage cote
        defenseur -- le mirror du champ `Subtraction @EffectBonus+0x18` (famille Nightshroud, #120)."""
        c = attacker_ctx or {}
        doubled = self._double_effect_condition(
            c,
            other_grand_alliance=c.get("grand_alliance"),  # HasTrait(Actor@+0x40, 0x7ea)
            other_team=c.get("team"),                      # AreEnemies(Actor@+0x40, Owner)
            owner_team=c.get("owner_team"))                #   -- l'Owner EST la CIBLE ici
        amt = self._amount(c, VAR_DMG_REDUCTION, doubled=doubled)
        return for_subtraction(False, amt) if amt else None    # EffectBonus +0x18 = Subtraction


class DeathwingKnightEffect(DeathwingEffect):
    """`IdunBattle.Entities.Effects.Loki.DeathwingEffect` instancie avec
    `triggeringAbilityType = 0x5e6` (= 1510 `TriggeredAbilityType.DeathwingKnight`) -- l'effet
    `EffectType 0x5e8 = 1512 DeathwingKnight` du passif du summon `darkaSmnTerminator` et de son
    jumeau npc `darkaNpc3Terminator` (#1073).

    ⚠ **IL N'EXISTE AUCUNE CLASSE `DeathwingKnightEffect` NATIVE**, et ce n'est pas une deduction :
    `frida/classes.tsv` (build `rnca9r7q6c`) ne porte, pour cette famille, que
    `IdunBattle.Entities.Effects.Loki.DeathwingEffect` et
    `IdunBattle.Entities.Effects.Loki.HuntTheFallen_DeathwingQuarryEffect`. Les DEUX `EffectType`
    sont servis par la MEME classe, et c'est LU dans les deux fabriques de l'`EffectsDatabase` :

        u003Cu003Ec$$u003CInitializeEffectsu003Eb__14_339 -> DeathwingEffect..ctor(this, 0x4dd)
        u003Cu003Ec$$u003CInitializeEffectsu003Eb__14_340 -> DeathwingEffect..ctor(this, 0x5e6)

    Le seul parametre du `.ctor` est `triggeringAbilityType` (`frida/methods.tsv`), qu'il passe a
    `IdunBattle.Entities.Effects.BaseEffect$$.ctor` sous forme d'`AbilityOrEffect` : c'est donc la
    CONFIG (`ConfigVar`) qui differe entre les deux instances, RIEN d'autre. Les DEUX faces de
    degat de cette classe sont donc, LITTERALEMENT, celles du parent --
    `IdunBattle.Entities.Effects.Loki.DeathwingEffect$$CreateEffectDamageBonusForAttack` et
    `IdunBattle.Entities.Effects.Loki.DeathwingEffect$$CreateEffectDamageMalusForDefense` -- au
    meme titre que `GetEffectAmount` et `GetDoubleEffectCondition`. Il n'y a qu'un corps.

    ⚠ Ces deux symboles sont CITES ICI, et pas seulement dans le parent, parce que
    `probe_437r1r1r1_effect_face_table.py` resout la classe native d'un effet par son NOM
    (`<EffectType>Effect`) et retombe sur la CITATION quand ce nom n'existe pas. Or il n'existe
    pas : c'est le fait meme que cette classe documente. Sans la citation, le cliquet classait
    `DeathwingKnight` en << NATIF NON RESOLU >> -- un rouge qui accusait le port d'une hypothese du
    recenseur (un `EffectType` = une classe native), fausse ici par construction.

    ⚠ **QUATRE ordinaux, quatre enums, ne jamais les rapprocher** : `TriggeredAbilityType 1245`
    `Deathwing` / `EffectType 1318` `Deathwing` / `TriggeredAbilityType 1510` `DeathwingKnight` /
    `EffectType 1512` `DeathwingKnight`. `EffectType 1510`, lui, est `MastersOfManoeuvre` -- sans
    aucun rapport (cf. le meme avertissement dans `effects/factory.py`).

    L'i2 de `DeathwingKnight` dit << the damage he deals is increased >> la ou celui de `Deathwing`
    dit << the damage Baraqiel deals with melee or *Plasma Cannon* attacks >>. Le NATIF, lui, ne
    distingue pas : le gate `IsMeleeAttack() | NOT IsNormalAttack()` est celui du corps PARTAGE. La
    prose i2 diverge, le code non -- et c'est le code qui est porte."""

    #: `DeathwingEffect..ctor(this, 0x5e6 = 1510)` -- l'`AbilityOrEffect`, donc la config du
    #: `ConfigVar`. Tables `extraDmg` / `dmgReduction` propres a `DeathwingKnight` (65 paliers,
    #: toutes deux dans `variablesAffectedByRarityBonus`, comme celles de `Deathwing`).
    ABILITY_ID = ABILITY_ID_KNIGHT
