"""`KardiocoreGalvanus_ExtraCritDmg` (`EffectType` 0x5aa = **1450**) -- le premier `ForAddition` de
l'axe crit-DEGAT porte par une RELIQUE : le porteur frappe plus fort en CRIT pour chaque ami
MECANIQUE adjacent.

## IDENTITE -- le piege d'ordinal est REEL ici, et c'est la SURCHARGE qui le tranche

    EffectType            0x5aa = 1450 = KardiocoreGalvanus_ExtraCritDmg   <- CET effet
    TriggeredAbilityType  0x5b1 = 1457 = KardiocoreGalvanus                <- sa CONFIG
    EffectType            0x5b1 = 1457 = RelicBoltPistol_ExtraPierce       <- une AUTRE relique

`1457` nomme donc DEUX choses. Ce qui tranche n'est ni l'ordinal ni le nom du module, c'est
l'ADRESSE de la surcharge appelee par le `.ctor`, relue OCTET A OCTET :

    ba b1 05 00 00      ; mov  edx, 0x5b1 = 1457
    e8 <rel32>          ; -> `IdunBattle.Core.AbilityOrEffect$$op_Implicit(triggeredAbility:
                        ;    TriggeredAbilityType)` -- la cible du `call` resolue par son RVA, pas
                        ;    par son nom (les quatre surcharges sont HOMONYMES dans les tables)
    41 b0 01            ; mov  r8b, 1  = hasAutomaticActivation
    e8 <rel32>          ; call IdunBattle.Entities.Effects.BaseEffect$$.ctor

Lire `1457` comme un `EffectType` ferait chercher la config de `RelicBoltPistol` : elle EXISTE au
gameconfig, donc l'erreur ne leverait pas -- elle lirait juste la mauvaise variable, en silence.
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.KardiocoreGalvanusAbility$$GetEffectType` a pour
corps ENTIER `return 0x5aa`, donc l'appariement ability -> effet est LU.

## L'ARTEFACT, LU EN ENTIER (build `rnca9r7q6c`) -- SEPT methodes, et DEUX sont DEDUPLIQUEES

`IdunBattle.Entities.Effects.Loki.KardiocoreGalvanus_ExtraCritDmgEffect` (: `BaseEffect`, cf.
`classes.tsv`). Les tables de symboles n'en nomment que CINQ : les deux autres ont un corps
PARTAGE avec une autre classe, donc un seul proprietaire dans la table -- « absent des tables » ne
prouve rien (cf. CLAUDE.md). Elles ont ete retrouvees par la table `methodPointers` du PE, dont le
bloc de la classe s'aligne slot a slot sur celui de ses deux soeurs de forme
(`IntoxicatingElixir_ExtraCritDmgEffect`, `MawClawsOfThyrax_ExtraCritDmgEffect`) :

    $$.ctor                       = BaseEffect..ctor(this, AbilityOrEffect(0x5b1), hasAutomatic: 1)
    $$CreateActiveCondition       = <DSLTriggers+0x70>          <- DEDUPLIQUE, cf. plus bas
    $$CreateTargetSelector        = <DSLSelectors+0x30> = Owner <- DEDUPLIQUE (defaut, ~250 classes)
    $$CreateCritDamageBonus       = EffectBonus.ForAddition( get_OwnerIsCaster, GetExtraCritAmount() )
    $$GetCalculateLevel           = DSLFormulas.Count(
                                        DSLSelectors.MechanicalUnits(
                                            DSLSelectors.AdjacentFriends(Owner@+0x30, unique: 1,
                                                                         selectionType: 3),
                                            selectionType: 3 ) )
    $$GetExtraCritAmount          = DSLFormulas.Multiply(
                                        ConfigVar(0x42 = extraCritDmg, GetAbilityState(effet),
                                                  config@+0x60),
                                        DSLFormulas.EffectLevel(Effect@DSLSelectors+0x38) )
    $$GetLocalizationDataInternal = { AbilityParam(0x21) : <GetExtraCritAmount> }   -- affichage seul

`GetExtraCritAmount` partage son corps avec `MawClawsOfThyrax_ExtraCritDmgEffect$$
GetExtraCritAmount` (c'est ce nom-la que ghidra affiche au call-site ; les deux classes ont la meme
formule a la variable pres). `AbilityVariableType 0x42 = 66 = extraCritDmg` (`enums.tsv`, jamais
recopie du decompile) ; `UnitSelectionType 3 = OnlyAliveAndTargetable`.

## `CreateActiveCondition` -- TOUJOURS VRAI, et c'est ce qui separe cet effet de ses jumeaux

`<DSLTriggers+0x70>` = `IdunBattle.Entities.Triggers.YesTrigger`, le trigger CONSTANT VRAI (identifie
en 2026-08-08, `docs/rl/case-521r1-talons-used-abilities-le-sixieme-chemin.md` sec. « `<DSLTriggers
+0x70>` »). C'est la MEME constante que rend `IdunBattle.Entities.Abilities.
AOwnerEffectTriggeredAbility$$CreateCondition`.

CONSEQUENCE DE HARNAIS, et elle est l'inverse de celle d'`AmuletOfTheVoidwyrm` : l'effet est
**TOUJOURS ACTIF**, donc TOUJOURS present dans le canal `decisionView.effects` (ACTIF-ONLY, #100),
meme sans aucun ami mecanique adjacent. Ni `active_condition_ported`, ni cle de `unit_state`, ni
seed conditionnel ne sont requis -- le regime commun (`BaseEffect.is_active`) coincide avec le
natif, et l'ecrire autrement inventerait un gate que le decompile ne porte pas.

GROUND TRUTH de la pose (runner `MC1_67` / seed 31337, `decisionView`) : `admecMarshall` et
`admecRuststalker` publient `KardiocoreGalvanus_ExtraCritDmg` des le deploiement, sans montage --
ils portent `TertiaryAbility = 1457` AU SEED (`data/seed-bc.json`), et `admecDestroyer`, meme
porteur autorise mais sans relique equipee, ne le publie PAS.

## POSE -- owner-effect PERMANENT, a l'init de l'ability

`classes.tsv` : `KardiocoreGalvanusAbility` derive d'`IdunBattle.Entities.Abilities.
AOwnerEffectTriggeredAbility`, dont le `CreateBehaviour` (corps de BASE) est

    If( CreateTrigger() = OnOwnerSpecificAbilityInit(<this+0x10> = 1457),
        AddEffect( GetEffectType() = 0x5aa,
                   AbilityState(Owner@DSLSelectors+0x30, AbilityType(abilityState)),
                   source  = Owner@DSLSelectors+0x30,
                   targets = Owner@DSLSelectors+0x30,
                   turns   = <zeroe>  ->  PERMANENT ) )

donc **source == porteur == Owner**, une fois a l'initialisation, jamais expire. C'est ce qui rend
le niveau exact : l'`AbilityState` bake dans l'`EffectComponent+0x18` est celui de la relique SUR
SON PORTEUR, c'est-a-dire l'etat TERTIAIRE (`TertiaryAbilityLevel` /
`TertiaryAbilityVariablesMultiplierPercentage`), relu par le foyer UNIQUE
`runner/operations/triggers/base.py::triggered_ability_state` (#357).

## PAS d'entree `ABILITY_INIT_OWNER_EFFECTS`, et c'est MESURE, pas oublie

`runner/operations/spawn.py::_seed_ability_owner_effects` lit
`GC.unit(vid).activeAbilities + passiveAbilities` -- le KIT gameconfig. Or `KardiocoreGalvanus` est
une RELIQUE : le kit d'`admecMarshall` est `['ControlEdict']`, celui d'`admecRuststalker`
`['OptimizedGait']`, celui d'`admecDestroyer` `['HeavyGravCannon']` -- la relique n'y figure PAS
(elle arrive par `BC.Units[].TertiaryAbility`). Une entree serait donc INERTE sur ce chemin, et le
seed DECISION (`playbook/scene.py::_seed_condition_gated_owner_effects`) ne prend que les classes
`active_condition_ported` + `seed_witness_effect`, que cet effet n'a pas puisqu'il est toujours
actif. Meme arbitrage EXPLICITE que `martial_superiority.py` et `structural_analyser.py` : a
rouvrir SI un porteur SPAWNE de cette relique apparait -- il n'en existe aucun aujourd'hui (les
trois porteurs `allowedUnits` sont des HEROES du pool, jamais invoques).

## LE CANAL -- `ForAddition`, et le trigger porte sur le CASTER

`EffectBonus.ForAddition( get_OwnerIsCaster, GetExtraCritAmount() )` -- trigger NU, aucun
`op_BitwiseAnd`. `IdunBattleLogic.Entities.DSLTriggers$$get_OwnerIsCaster` = `AreEqual(Owner@
DSLSelectors+0x30, Caster@DSLSelectors+0x48)` : « le PORTEUR de cet effet est-il l'ATTAQUANT du
coup ? » -- l'exact SYMETRIQUE d'`AmuletOfTheVoidwyrm` / `SupaCyborkBody`, qui lisent
`get_OwnerIsTarget`.

CONSOMMATION, relue : `IdunBattle.Core.Services.DamagePrediction$$GetCritDamageBonusFromEffects`
accumule litteralement `addition - subtraction`, et `$$CalculateCriticalDamage` fait
`Math.Max(0, GetStat(10) + somme)`. Le port rend donc un entier **POSITIF** : c'est le mirror du
terme additif. Aucun risque de saturation ici, contrairement aux deux `ForSubtraction`.

## LA MAGNITUDE -- un PRODUIT, et son second facteur est une LECTURE du niveau STOCKE

    Multiply( ConfigVar(0x42 = extraCritDmg, GetAbilityState(effet), config@+0x60),
              EffectLevel(Effect@DSLSelectors+0x38) )

C'est la MEME forme que `SupaCyborkBody_CritDmgReductionEffect$$GetCritDamageReduction` (dont ce
corps est le voisin immediat au PE) : `DSLFormulas.EffectLevel` lit `EffectComponent+0x68`, un champ
que `IdunBattle.Operations.RefreshEffectsOperation$$UpdateLevel` tient EGAL a `GetCalculateLevel`
(il appelle le slot `CalculateLevel` = `BaseEffect$$CalculateLevel`, formule `this+0x88`, compare et
ECRIT si ca differe). Le niveau stocke EST donc, a tout instant ou le refresh a tourne, le nombre
d'amis mecaniques adjacents.

Le port privilegie le compteur RECALCULE (il suit l'etat courant du board) et retombe sur le niveau
CAPTE quand aucun `state` n'est threade. Les garder tous les deux est ce qui rend l'etage
FALSIFIABLE : si le port diverge apres un deplacement, c'est le compteur qui le dira.

`KardiocoreGalvanus` n'a AUCUN `variablesAffectedByRarityBonus` ni `constants` au gameconfig
(`variables.extraCritDmg` seule, 10 paliers `[295, 311, ..., 438]`) -> le multiplicateur de rarete
ne mord pas ; on le passe quand meme, parce que c'est `ability_var` (donc la config) qui decide,
jamais ce module.

## LE COMPTEUR -- un ARBRE DSL, et son `AdjacentFriends` EXCLUT le porteur

`DSLSelectors$$AdjacentFriends(this, unit, unique, selectionType)` (surcharge tranchee par la
POSITION de ses arguments : l'appel passe `(this, <Owner@+0x30>, 1, 3)`, et un `1` litteral ne peut
pas etre un SELECTEUR de tuile -- c'est donc la variante A, pas la variante B `(unit, unitTile,
unique)`). Son corps, relu :

    Friends( reference = unit,
             Units(AdjacentTiles(unit), unique, selectionType) op_Subtraction unit,
             selectionType )

Le `op_Subtraction unit` EXCLUT le porteur : un porteur mecanique ne se compte jamais lui-meme.
`MechanicalUnitsSelector$$Select` filtre ensuite sur
`IdunBattle.Entities.UnitExtensions$$IsMechanical` = `HasTrait(5 = Mechanical) || HasTrait(0x3e8 =
1000 LivingMetal) || HasTrait(0x405 = 1029 Vehicle)` -- TROIS traits, deja mirrores par le helper
partage `runner.abilities.behaviours.stats.is_mechanical` (case-220).

ASCII only.
"""
from __future__ import annotations

from collections.abc import Mapping

from ..base import BaseEffect
from ..magnitude import ability_var
from ....dsl.base import Const
from ...selectors.accessors import Owner
from ...selectors.units import AdjacentFriends, MechanicalUnits
from ...unit_selection_type import UnitSelectionType
from .. import ctx_keys as _ctx_keys      # #1042-r5 : foyer UNIQUE des chaines de cle de ctx

#: `TriggeredAbilityType 0x5b1 = 1457` -- le litteral du `.ctor`, relu a l'assembleur, et dont la
#: SURCHARGE d'`op_Implicit` etablit qu'il s'agit bien de l'enum des TRIGGERED (l'`EffectType` 1457
#: est `RelicBoltPistol_ExtraPierce`, une autre relique).
_ABILITY_ID = "KardiocoreGalvanus"
#: `AbilityVariableType 0x42 = 66` (`enums.tsv`, jamais recopie du decompile).
_VAR_KEY = "extraCritDmg"
#: `UnitSelectionType 3` -- le litteral que le natif propage aux DEUX etages du compteur.
_SEL = int(UnitSelectionType.OnlyAliveAndTargetable)
#: callable `(owner_id) -> int | None` pose dans le contexte du canal CRIT par `_crit_board`
CTX_COUNT_OF = "adjacent_mechanical_friends_of"
#: callable `(owner_id, ability_name) -> (level, multiplier)` -- mirror de `GetAbilityState(effet)`
CTX_ABILITY_STATE_OF = _ctx_keys.CTX_TERTIARY_ABILITY_STATE_OF


def adjacent_mechanical_friends_selector():
    """L'ARBRE DSL de `...KardiocoreGalvanus_ExtraCritDmgEffect$$GetCalculateLevel`, noeud par noeud
    (doctrine #149 : l'artefact natif est un SELECTEUR, donc le port est un arbre, pas une boucle
    recablee) :

        Count( MechanicalUnits( AdjacentFriends(Owner@+0x30, unique: 1, selectionType: 3),
                                selectionType: 3 ) )

    `reference=Owner()` est passe EXPLICITEMENT a `AdjacentFriends` : la reference d'equipe du
    `Friends` natif EST le centre (`Friends(reference = unit, ...)`), et le defaut du port
    (`ctx.caster`) ne coinciderait que tant que le contexte est bati sur le porteur.

    Import PARESSEUX de `Count` : `entities/formulas` est assemble APRES le package
    `entities/effects` (meme garde anti-cycle et meme convention que `supa_cybork_body` et
    `amulet_of_the_voidwyrm`)."""
    from ...formulas import Count

    return Count(MechanicalUnits(AdjacentFriends(Owner(), Const(1), Owner(), _SEL), _SEL))


class KardiocoreGalvanusExtraCritDmgEffect(BaseEffect):
    """`KardiocoreGalvanus_ExtraCritDmg` (0x5aa = 1450) -- owner-effect PERMANENT de la relique
    `KardiocoreGalvanus` : quand son porteur est l'ATTAQUANT d'un coup CRITIQUE, le degat de crit est
    AUGMENTE de `extraCritDmg[niveau de relique] x <nombre d'amis mecaniques adjacents au porteur>`.

    Troisieme implementeur porte du canal crit-DEGAT cote RELIQUE, et le PREMIER de son axe : les
    deux precedents (`AmuletOfTheVoidwyrm_CritDamageReduction`, `SupaCyborkBody_CritDmgReduction`)
    sont des `ForSubtraction` sur la CIBLE ; celui-ci est un `ForAddition` sur le CASTER.

    PAS d'`active_condition_ported` : la `CreateActiveCondition` native est `<DSLTriggers+0x70>` =
    `YesTrigger`, donc constante VRAIE. Le regime commun (`BaseEffect.is_active`) coincide, et poser
    le flag inventerait un gate que le decompile ne porte pas."""

    @staticmethod
    def _adjacent_mechanical_friends(ctx: "Mapping | None") -> "int | None":
        """`GetCalculateLevel()` EVALUE pour le PORTEUR de CETTE instance.

        Le canal pose `owner_id` par porteur (mirror de l'ecriture `AbilityEntities+0x18` que la
        boucle native fait a chaque iteration), et `_crit_board` pose le callable
        `adjacent_mechanical_friends_of` -- paresseux, donc rien n'est calcule tant qu'aucune
        instance ne le demande.

        TRI-ETAT : callable ou `owner_id` ABSENT => `None` = « non mesure », JAMAIS 0. Un 0 invente
        annulerait le produit et ferait passer un bonus reel pour une absence de bonus."""
        c = ctx or {}
        fn = c.get(CTX_COUNT_OF)
        oid = c.get("owner_id")
        if fn is None or oid is None:
            return None
        n = fn(oid)
        return None if n is None else int(n)

    def _effect_level(self, ctx: "Mapping | None") -> "int | None":
        """`DSLFormulas.EffectLevel(Effect@DSLSelectors+0x38)` = `EffectComponent+0x68`.

        Ce champ est tenu EGAL a `GetCalculateLevel` par
        `IdunBattle.Operations.RefreshEffectsOperation$$UpdateLevel`. Le port privilegie donc le
        compteur RECALCULE, qui suit l'etat courant du board, et retombe sur le niveau CAPTE quand
        aucun `state` n'est threade (probe/test offline).

        ⚠ Ce niveau n'est PAS le niveau d'ability : `self.level` est le niveau de l'EFFET
        (`decisionView.effects[].level`), `_ability_state` rend l'autre. Les confondre lirait
        `extraCritDmg[1] = 295` au lieu du palier reel."""
        n = self._adjacent_mechanical_friends(ctx)
        if n is not None:
            return n
        return None if self.level is None else int(self.level)

    def _ability_state(self, ctx: "Mapping | None") -> tuple:
        """`GetAbilityState(effet)` -> `(level, multiplier)` de l'`AbilityState` bake a la pose.

        `AOwnerEffectTriggeredAbility$$CreateBehaviour` bake `AbilityState(Owner, <cette ability>)`
        et pose l'effet SUR l'Owner : source == porteur, donc le couple se relit sur le porteur
        (`owner_id`) par le foyer UNIQUE `runner/operations/triggers/base.py::
        triggered_ability_state` (#357), qui rend l'etat TERTIAIRE si la relique y est montee et
        l'etat PASSIF sinon.

        Callable absent (contexte sans `state`) -> repli sur les niveaux que l'effet porte deja,
        comme toutes les autres classes d'effet."""
        c = ctx or {}
        fn, oid = c.get(CTX_ABILITY_STATE_OF), c.get("owner_id")
        if fn is not None and oid is not None:
            lvl, mult = fn(oid, _ABILITY_ID)
            if lvl is not None:
                return int(lvl), int(mult if mult is not None else 100)
        lvl = self.ability_level if self.ability_level is not None else self.level
        return lvl, int(self.ability_variables_multiplier or 100)

    def _owner_is_caster(self, att_ctx: "Mapping | None" = None) -> bool:
        """`IdunBattleLogic.Entities.DSLTriggers$$get_OwnerIsCaster` = `AreEqual(Owner@+0x30,
        Caster@+0x48)`. Identite NON PROUVEE (une des deux cles absente) => noeud FAUX, jamais
        permissif -- meme foyer de raisonnement que `SupaCyborkBodyCritDmgReductionEffect.
        _owner_is_target`, sur l'autre slot de l'`AbilityEntities`."""
        c = att_ctx or {}
        oid, aid = c.get("owner_id"), c.get("att_id")
        return oid is not None and aid is not None and oid == aid

    def create_effect_crit_damage_bonus_for_attack(self, att_ctx: "Mapping | None" = None) -> "int | None":
        """MIRROR de `...KardiocoreGalvanus_ExtraCritDmgEffect$$CreateCritDamageBonus` :

            EffectBonus.ForAddition( get_OwnerIsCaster,
                                     Multiply( ConfigVar(0x42 = extraCritDmg,
                                                         GetAbilityState(effet), config@+0x60),
                                               EffectLevel(Effect@+0x38) ) )

        Retour ENTIER POSITIF : `IdunBattle.Core.Services.DamagePrediction$$
        GetCritDamageBonusFromEffects` accumule litteralement `addition - subtraction`, et son
        consommateur est `Math.Max(0, GetStat(10) + somme)` dans `$$CalculateCriticalDamage`.

        Les etages sont SEPARES et chacun peut se taire independamment (aucun scalaire fitte) :
          1. `get_OwnerIsCaster`  -- le porteur est-il l'ATTAQUANT ?
          2. `EffectLevel`        -- tri-etat, `None` = non mesure ;
          3. l'`AbilityState`     -- niveau/multiplicateur de la relique sur le porteur ;
          4. `ConfigVar`          -- `extraCritDmg[niveau]`, relu du gameconfig ;
          5. `Multiply`           -- le produit, puis le signe de `ForAddition`."""
        if not self._owner_is_caster(att_ctx):                 # 1
            return None
        n = self._effect_level(att_ctx)                        # 2
        if n is None:
            return None
        lvl, mult = self._ability_state(att_ctx)               # 3
        v = ability_var(_ABILITY_ID, _VAR_KEY, lvl, multiplier_pct=mult)   # 4  ConfigVar(0x42)
        if v is None:
            return None
        amount = int(v) * int(n)                               # 5  Multiply
        return amount or None                                  #    ForAddition
