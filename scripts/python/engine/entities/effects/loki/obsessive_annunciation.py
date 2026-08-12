"""`ObsessiveAnnunciation` (`TriggeredAbilityType 0x5a3 = 1443`) -- passif de kit de
`emperKakophonist` << Adamatar >> (Emperor's Children / Chaos), HERO **DU POOL**.

i2 `Abilities/ObsessiveAnnunciation_CurrentLevelDescription` :
    << All enemy units adjacent to Adamatar take +{[extraDmg]} Damage from ranged attacks. If an
    enemy was Overkilled this turn, enemies adjacent to Adamatar take +{[extraCritDmg]} Crit Damage
    from all attacks by friendly Chaos units. >>

===================================================================================================
RECENSEMENT PAR LE BLOC `methodPointers` (jamais par grep de nom) -- ET LA FONTE ICF QUI CHANGE TOUT
===================================================================================================

Bases LUES dans `data/symbols/<build>/frida/classes.tsv`, jamais dans le nom du `.ctor` :

    IdunBattleLogic...Triggered.Loki.ObsessiveAnnunciationAbility        : AOwnerEffectTriggeredAbility
        -> [ GetEffectType = `return 0x598`, .ctor ]     (owner-effect a l'init : `ABILITY_INIT_OWNER_EFFECTS`)
    IdunBattleLogic...Triggered.Loki.ObsessiveAnnunciation_OverkillAbility : BaseTriggeredAbility
        -> [ CreateTrigger, CreateBehaviour, .ctor ]     (face TRIGGER : `runner/.../obsessive_annunciation.py`)
    IdunBattle.Entities.Effects.Loki.ObsessiveAnnunciation_ExtraDmgEffect     (`EffectType 0x598 = 1432`)
        -> [ .ctor, CreateActiveCondition, CreateTargetSelector, CreateEffectDamageBonusForAttack ]
    IdunBattle.Entities.Effects.Loki.ObsessiveAnnunciation_ExtraCritDmgEffect (`EffectType 0x599 = 1433`)
        -> [ .ctor, CreateActiveCondition, CreateTargetSelector, CreateCritDamageBonus ]
    IdunBattle.AI.Playbook.Loki.ObsessiveAnnunciationPlaybook : TriggeredAbilityPlaybook<...Ability>
        -> face DECISION (`playbook/obsessive_annunciation.py`)

⚠ **LES DEUX EFFETS SONT DES AURAS, ET LE SECOND NE LE DIT PAS.** Un grep de nom ne rend qu'UN
`CreateTargetSelector` (celui d'`_ExtraDmgEffect`, `0x106a5c0`) : le bloc `methodPointers` du PE
montre que le slot correspondant d'`_ExtraCritDmgEffect` pointe sur **LA MEME ADRESSE** -- corps
FONDU par l'ICF, donc invisible autrement. Les deux blocs, lus cote a cote :

    _ExtraCritDmg : [ .ctor <0x106a610>, CreateActiveCondition <0xec58e0>,
                      CreateTargetSelector <0x106a5c0>, CreateCritDamageBonus <0x106a370> ]
    _ExtraDmg     : [ .ctor <0x106a610>, CreateActiveCondition <0xec58e0>,
                      CreateTargetSelector <0x106a5c0>, CreateEffectDamageBonusForAttack <0x106a660> ]

Ne pas le voir aurait donne un effet CRIT qui ne touche que son porteur -- or Adamatar n'est jamais
la cible du regime vise, donc le bonus n'aurait JAMAIS mordu, sans erreur ni trace.
(`<0xec58e0>` = `return <DSLTriggers+0x40>`, la constante VRAIE : les deux effets sont TOUJOURS
ACTIFS, comme `TerrorsLament` et `ToughToKill`. `<0x106a610>` = un `.ctor` PARTAGE par les deux
classes -- lui aussi fondu.)

===================================================================================================
LES ARBRES (mirror 1:1 ; surcharges tranchees par l'ADRESSE de la cible du `call`, `E8 rel32`)
===================================================================================================

    $$CreateTargetSelector  (LES DEUX effets, meme corps) =
        AdjacentEnemies( Owner@DSLSelectors+0x30, unique: true,
                         UnitSelectionType.OnlyAliveAndTargetable = 3 )
        -- surcharge `(unit, unique, selectionType)` = `0xeac220`, PAS `(unit, unitTile, unique)`
           = `0xeac190` : lire la seconde ferait du 3e argument une ENTITE au lieu d'un booleen.

    1432 $$CreateEffectDamageBonusForAttack =
        EffectBonus.ForAddition(
            get_OwnerIsTarget
            & IsRangedAttack                                   # surcharge SANS argument (`0xed9990`)
            & AreFriends( EffectSource(Effect@DSLSelectors+0x38), Caster@DSLSelectors+0x48,
                          UnitTeamSelectionType.ByCurrentTeam = 0, anyEntity: false ),
            ConfigVar(AbilityVariableType.extraDmg = 8, GetAbilityState(this), config@this+0x60) )

    1433 $$CreateCritDamageBonus =
        EffectBonus.ForAddition(
            get_OwnerIsTarget
            & AreFriends( EffectSource(Effect@+0x38), Caster@+0x48, ByCurrentTeam, false )
            & HasTrait( Caster@DSLSelectors+0x48, UnitTrait.Chaos = 0x7ea ),
            ConfigVar(AbilityVariableType.extraCritDmg = 0x42, GetAbilityState(this), config@+0x60) )

## ⚠ LES DEUX MOITIES NE PORTENT PAS LES MEMES CONJOINTS -- recopier l'une sur l'autre est FAUX

Elles ont TOUTES DEUX trois conjoints, et DEUX seulement sont communs :

    commun            get_OwnerIsTarget · AreFriends(EffectSource, Caster)
    DEGAT seul        IsRangedAttack                     <- absent de la moitie CRIT
    CRIT seul         HasTrait(Caster, Chaos)            <- absent de la moitie DEGAT

L'i2 le dit dans l'autre sens et confirme : << +Damage from RANGED attacks >> contre << +Crit Damage
from ALL attacks by friendly CHAOS units >>. Un port qui recopierait le gate ranged sur la moitie
crit tuerait le bonus sur toute attaque de melee d'un allie Chaos ; l'inverse ferait profiter du
+crit un allie non-Chaos. Les deux fautes sont silencieuses.

## `ForAddition` DES DEUX COTES (`0x1047dc0`), jamais `ForSubtraction` (`0x1048090`)

C'est l'ADRESSE qui tranche, pas le nom rendu par ghidra. Les deux montants sont donc POSITIFS --
contraste exact avec `ToughToKill` (#950), dont les deux canaux crit sont des `ForSubtraction`.

## MAGNITUDES

`extraDmg` (`AbilityVariableType 8`) et `extraCritDmg` (`0x42 = 66`) sont **TOUS DEUX** dans
`VariablesAffectedByUnitRarityMultiplier` (`[8, 66]` au BC) -- le multiplicateur de rarete mord des
DEUX cotes. C'est l'ecart avec #947/#948, ou une seule des deux variables etait scalee : le fait ne
se lit QUE dans la config, jamais dans le decompile.

`GetAbilityState(this)` sur un `AbilityOrEffect` TRIGGERED resout le niveau du PASSIF de la SOURCE
(Adamatar) -> `ability_level` / `ability_variables_multiplier` de l'instance, poses par le seed
`ABILITY_INIT_OWNER_EFFECTS` comme par la capture `decisionView.effects`.

## OU VIT CHAQUE FACE COTE PORT, ET POURQUOI

Le natif n'a qu'UNE boucle par axe -- `EffectsQuery$$GetActiveEffectsWithBonuses` rend
`(effet, CIBLES)` et ECRIT `AbilityEntities+0x18 (Owner) <- la cible courante de l'effet` avant
d'evaluer chaque trigger (relu verbatim dans
`IdunBattle.Core.Services.DamagePrediction$$GetCritDamageBonusFromEffects` : la copie de
l'`AbilityEntities` recoit l'entite de la cible a `+0x18` juste avant l'appel du slot 0x22).
`get_OwnerIsTarget` y signifie donc **<< la cible du coup est l'une des cibles de l'effet >>**, et
non << le porteur est la cible >>. Le port, dont les agregateurs posent `owner_id = le PORTEUR`,
rend ce gate en RE-EVALUANT le `CreateTargetSelector` :

    axe DEGAT  -> `create_aura_defense_damage_malus_for_ally` (agregateur
                  `aura_defense_damage_malus_from_units`, deja board-wide) ;
    axe CRIT   -> `create_effect_crit_damage_bonus_for_attack` (agregateur
                  `crit_damage_bonus_from_effects`, board-wide depuis #589-r1-r1).

⚠ Aucun des deux ne portait de GEOMETRIE PAR PORTEUR : c'est la SEULE cle de contexte neuve de ce
port -- `adjacent_enemy_ids_of(owner_id)`, un callable PARESSEUX pose dans les DEUX facades (meme
forme et meme raison que les six compteurs par-porteur qui vivent deja dans `_crit_board`). Il rend
les ids de `AdjacentEnemies(...)` evalues contre l'etat REEL, donc **avec la porte d'elevation** du
ring-1 natif (`TileQuery.IterateAdjacentTiles`) -- ce qu'un `hexgeo.distance == 1` ecrit au site ne
porterait pas (#271 : sur-compte au bord d'une marche).
"""
from __future__ import annotations

from collections.abc import Mapping

from ....dsl.base import Const
from ....services.effect_bonus import EffectBonus, for_addition
from ...effect_type import EffectType   # #270-r1-r1-r3
from ...selectors.accessors import Owner
from ...selectors.units import AdjacentEnemies
from ...traits.unit_trait import UnitTrait
from ...unit_selection_type import UnitSelectionType
from ..base import BaseEffect
from ..magnitude import ability_var

#: Nom gameconfig du passif -- la CONFIG que `ConfigVar(..., config@+0x60)` indexe
#: (`TriggeredAbilityType 0x5a3 = 1443 = ObsessiveAnnunciation`).
#: ⚠ Les `EffectType` 0x598/0x599 nomment, dans l'enum des TRIGGERED, `ArmourOfShriekingSouls` et
#: `EnhancementRegeneration` -- deux abilities REELLES, donc une confusion d'enum ne leverait pas :
#: elle lirait la mauvaise config, en silence.
ABILITY_ID = "ObsessiveAnnunciation"
#: `AbilityVariableType 8` et `0x42 = 66` (`frida/enums.tsv`), resolus par leur NOM. Les DEUX sont
#: dans `variablesAffectedByRarityBonus`.
VAR_EXTRA_DMG = "extraDmg"
VAR_EXTRA_CRIT_DMG = "extraCritDmg"

#: `EffectType 0x598 = 1432` / `0x599 = 1433` -- les deux auras.
OBSESSIVE_ANNUNCIATION_DMG_EFFECT = EffectType.ObsessiveAnnunciation_ExtraDmg
OBSESSIVE_ANNUNCIATION_CRIT_EFFECT = EffectType.ObsessiveAnnunciation_ExtraCritDmg
#: `HasTrait(Caster@+0x48, 0x7ea)` -- la GRANDE-ALLIANCE de l'attaquant, DERIVEE du `GrandAllianceId`
#: par `idun.Idun.Source.Shared.GrandAlliance$$GetTrait` (elle n'est PAS dans le kit gameconfig).
_CHAOS = int(UnitTrait.Chaos)
#: Cle du callable PAR PORTEUR pose par les DEUX facades -- mirror du `CreateTargetSelector` des
#: deux effets, evalue contre l'etat REEL. Rend un `frozenset` d'ids, ou `None` = NON MESURE.
CTX_ADJACENT_ENEMY_IDS_OF = "adjacent_enemy_ids_of"


def adjacent_enemies_selector():
    """L'ARBRE DSL du `CreateTargetSelector` PARTAGE par les deux effets (doctrine #149 : l'artefact
    natif est un SELECTEUR, donc le port est un arbre) :

        AdjacentEnemies( Owner@DSLSelectors+0x30, unique: true,
                         UnitSelectionType.OnlyAliveAndTargetable = 3 )

    Surcharge `(unit, unique, selectionType)` (`0xeac220`), tranchee par l'ADRESSE de la cible du
    `call` : elle PROPAGE le `selectionType` aux DEUX etages (`Units(AdjacentTiles(unit), unique,
    sel)` puis `Enemies(..., sel)`). La variante `(unit, unitTile, unique)` (`0xeac190`) aurait fait
    du 3e argument une ENTITE, et son `3` serait en dur -- l'ecart se lit au call-site, pas au nom.

    `Const(1)` est le RAYON cote port (`AdjacentEnemies(center, radius, selection_type)`), c.-a-d.
    le ring-1 qu'`AdjacentTiles` produit ; le `unique: true` natif est absorbe (les selecteurs du
    port rendent deja des ensembles). Contraste `supa_cybork_body::adjacent_enemies_selector`, qui
    laisse `selection_type` a `None` : ici le litteral `3` est LU au call-site, donc porte."""
    return AdjacentEnemies(Owner(), Const(1),
                           selection_type=int(UnitSelectionType.OnlyAliveAndTargetable))


def _caster_is_chaos(att_traits) -> bool:
    """`HasTrait(Caster@DSLSelectors+0x48, 0x7ea = UnitTrait.Chaos)`.

    Substrat = `att_traits` du canal CRIT (`entity_trait_names`, substrat d'ENTITE -- #264, jamais
    le kit gameconfig). Le trait d'alliance est ajoute par le `BattleConfiguration` a partir du
    `GrandAllianceId`, donc il EST dans les traits d'entite. Traits NON mesures (`None`) -> FAUX
    (degradation RESTRICTIVE : on ne fabrique pas une alliance)."""
    names = set(att_traits or ())
    return _CHAOS in {int(t) for t in names if isinstance(t, int)} \
        or UnitTrait.Chaos.name in names


def _owner_is_target(ctx: "Mapping", owner_id, tgt_id) -> "bool | None":
    """`get_OwnerIsTarget` DEVELOPPE -- << la cible du coup est-elle l'une des cibles de l'effet ? >>

    Le natif ne pose pas la question autrement : sa boucle `effets x CIBLES` ecrit
    `AbilityEntities+0x18 (Owner) <- la cible courante`, puis `AreEqual(Owner, Target)` ne retient
    que l'iteration ou les deux coincident. Le port, dont les agregateurs posent `owner_id = le
    PORTEUR`, re-evalue donc le `CreateTargetSelector` par le callable `adjacent_enemy_ids_of`.

    TRI-ETAT : `None` = NON MESURE (callable absent, ou porteur sans equipe ni tuile) -- l'appelant
    se tait alors, jamais un bonus devine. C'est la meme discipline que les six compteurs
    par-porteur de `_crit_board`."""
    if owner_id is None or tgt_id is None:
        return None
    resolver = (ctx or {}).get(CTX_ADJACENT_ENEMY_IDS_OF)
    if not callable(resolver):
        return None
    targets = resolver(int(owner_id))
    if targets is None:
        return None
    return int(tgt_id) in targets


def _source_and_caster_are_friends(owner_team, att_team) -> bool:
    """`AreFriends( EffectSource(Effect@DSLSelectors+0x38), Caster@DSLSelectors+0x48,
    UnitTeamSelectionType.ByCurrentTeam = 0, anyEntity: false )`.

    `EffectSource(Effect)` = `EffectComponent.SourceUnit @+0x10` = le POSEUR. Les DEUX effets sont
    poses avec `source = Owner` (owner-effect a l'init pour 1432 ;
    `AddEffect(..., source = Owner@+0x30, ...)` pour 1433), donc la SOURCE **est** le porteur, et
    l'equipe que l'agregateur pose PAR PORTEUR est bien celle demandee.
    `IdunBattle.Entities.UnitExtensions$$IsFriend` n'ecarte PAS l'egalite : Adamatar attaquant est
    son propre ami -- mais `get_OwnerIsTarget` l'exclut de toute facon (il n'est pas dans ses
    propres `AdjacentEnemies`). Une equipe non mesuree FERME (degradation RESTRICTIVE)."""
    return owner_team is not None and att_team is not None and owner_team == att_team


class ObsessiveAnnunciationExtraDmgEffect(BaseEffect):
    """`...ObsessiveAnnunciation_ExtraDmgEffect` (`EffectType 0x598 = 1432`, nom capte
    `ObsessiveAnnunciation_ExtraDmg`) -- AURA PERMANENTE posee sur Adamatar a l'init par
    `ObsessiveAnnunciationAbility` (`AOwnerEffectTriggeredAbility`, `GetEffectType` =
    `return 0x598`), et PROJETEE sur ses ennemis adjacents par son `CreateTargetSelector`.

    Effet : ces ennemis prennent `+extraDmg` de degat de la part des attaques **A DISTANCE** des
    ALLIES d'Adamatar. Cf. l'en-tete du module pour l'arbre natif et les DEUX moities.

    `CreateActiveCondition` = `<DSLTriggers+0x40>` = la constante VRAIE (corps FONDU) -> l'effet est
    TOUJOURS actif, donc TOUJOURS publie par le canal ACTIF-ONLY : pas d'`active_condition_ported`
    (il n'y a rien a recalculer), exactement comme `ToughToKill` et `TerrorsLament`."""

    def _amount(self) -> "int | None":
        """`ConfigVar(AbilityVariableType.extraDmg = 8, GetAbilityState(this), config@+0x60)`.
        `extraDmg` EST dans `variablesAffectedByRarityBonus` -> le multiplicateur mord."""
        lvl = self.ability_level if self.ability_level is not None else self.level
        v = ability_var(ABILITY_ID, VAR_EXTRA_DMG, lvl,
                        multiplier_pct=int(self.ability_variables_multiplier or 100))
        return int(v) if v else None

    def create_aura_defense_damage_malus_for_ally(self, ctx: "Mapping | None" = None) -> "EffectBonus | None":
        """`ForAddition( get_OwnerIsTarget & IsRangedAttack & AreFriends(EffectSource, Caster),
        ConfigVar(extraDmg) )` -- servi par la boucle `effets x cibles` de
        `IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction`.

        Le canal s'appelle `..._malus_for_ally` par son HISTOIRE (`DaughterOfTheAbyss_FriendlyDmg
        ReductionPct`), mais il sert dans les DEUX sens : c'est le seul agregateur qui balaie les
        porteurs TIERS pour un modifier du DEGAT RECU. La contribution est ici POSITIVE
        (`ForAddition`), comme celle de `DaughterOfTheAbyss_ExtraDamagePct`.

        `is_melee is False` = `IsRangedAttack` (tri-etat #106 : `None` = nature non declaree -> le
        gate se FERME, jamais un ranged devine)."""
        c = ctx or {}
        if c.get("is_melee") is not False:                          # IsRangedAttack
            return None
        if _owner_is_target(c, c.get("owner_id"), c.get("tgt_id")) is not True:
            return None
        if not _source_and_caster_are_friends(c.get("owner_team"), c.get("att_team")):
            return None
        v = self._amount()
        return for_addition(True, v) if v else None

    #: `...ObsessiveAnnunciation_ExtraDmgEffect$$CreateEffectDamageBonusForAttack` implemente le slot
    #: ATTAQUANT du natif -- sa contribution part donc dans `attackModifiers`, pas dans les modifiers
    #: du defenseur, alors que le port l'evalue par le canal AURA-DEFENSE (le seul qui balaie les
    #: porteurs TIERS). MEME arbitrage, MEME motif que `DaughterOfTheAbyss_ExtraDamagePctEffect`
    #: (#437-r1-r1-r1) : le nom natif le dit, c'est la FACE qui en etait deduite a tort.
    AURA_DEFENSE_MALUS_NATIVE_FACE = "attacker"


class ObsessiveAnnunciationExtraCritDmgEffect(BaseEffect):
    """`...ObsessiveAnnunciation_ExtraCritDmgEffect` (`EffectType 0x599 = 1433`, nom capte
    `ObsessiveAnnunciation_ExtraCritDmg`) -- AURA d'UN TOUR posee sur Adamatar par
    `ObsessiveAnnunciation_OverkillAbility` quand un ennemi vient d'etre OVERKILL, et projetee sur
    ses ennemis adjacents par le MEME `CreateTargetSelector` (corps FONDU avec celui de 1432).

    Effet : ces ennemis prennent `+extraCritDmg` de degat de CRIT de la part de TOUTE attaque d'un
    allie **CHAOS** d'Adamatar. Cf. l'en-tete du module.

    Septieme implementeur porte du canal crit-DEGAT, et le PREMIER qui soit une AURA : les six
    autres vivent sur l'attaquant ou sur la cible."""

    def _amount(self) -> "int | None":
        """`ConfigVar(AbilityVariableType.extraCritDmg = 0x42, GetAbilityState(this), config@+0x60)`.
        `extraCritDmg` EST dans `variablesAffectedByRarityBonus` (`[8, 66]`) -> le multiplicateur
        mord ici AUSSI -- contraste #947/#948, ou une seule variable de la paire etait scalee."""
        lvl = self.ability_level if self.ability_level is not None else self.level
        v = ability_var(ABILITY_ID, VAR_EXTRA_CRIT_DMG, lvl,
                        multiplier_pct=int(self.ability_variables_multiplier or 100))
        return int(v) if v else None

    def create_effect_crit_damage_bonus_for_attack(self, att_ctx: "Mapping | None" = None) -> "int | None":
        """`ForAddition( get_OwnerIsTarget & AreFriends(EffectSource, Caster) &
        HasTrait(Caster@+0x48, Chaos), ConfigVar(extraCritDmg) )`.

        **AUCUN `IsRangedAttack` ici** -- c'est le conjoint que porte la moitie DEGAT et pas
        celle-ci (cf. l'en-tete). Le recopier eteindrait le bonus sur toute attaque de melee d'un
        allie Chaos, qui est precisement le regime que l'i2 decrit.

        `owner_id` est pose PAR PORTEUR par `crit_damage_bonus_from_effects` (mirror de l'ecriture
        `AbilityEntities+0x18`) ; `team_by_id`, `att_team` et `att_traits` viennent de
        `_crit_board`. Retour ENTIER POSITIF (`ForAddition`) : `CalculateCriticalDamage` fait
        `Math.Max(0, GetStat(10) + somme)`."""
        c = att_ctx or {}
        owner_id = c.get("owner_id")
        if _owner_is_target(c, owner_id, c.get("tgt_id")) is not True:
            return None
        if not _source_and_caster_are_friends((c.get("team_by_id") or {}).get(int(owner_id)),
                                              c.get("att_team")):
            return None
        if not _caster_is_chaos(c.get("att_traits")):           # HasTrait(Caster, 0x7ea = Chaos)
            return None
        v = self._amount()
        return int(v) if v else None                            # ForAddition -> POSITIF
