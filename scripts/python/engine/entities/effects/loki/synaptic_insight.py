"""`IdunBattle.Entities.Effects.Loki.SynapticInsight_ExtraHitsEffect` (`EffectType 0x4cf = 1231`) --
l'owner-effect PERMANENT du passif `SynapticInsight` (`TriggeredAbilityType 0x4a9 = 1193`), porte par
le summon `tyranSmnBarbgaunt` et ses deux jumeaux npc `tyranNpc5Barbgaunt` /
`tyranNpc5BarbgauntSurv` (#1073).

i2 `SynapticInsight` : << This unit's ranged attacks score +2 hits against targets that are within
Synapse range or adjacent to another Tyranid. >>

===================================================================================================
L'ABILITY -- `SynapticInsightAbility`, trigger d'INIT partage, behaviour a UN noeud
===================================================================================================

`frida/classes.tsv` la donne fille de `IdunBattle.Entities.Abilities.BaseTriggeredAbility`, et le
`global-metadata.dat` lui declare exactement TROIS entrees --
`[CreateTrigger (slot 26), CreateBehaviour (slot 28), .ctor]`.

`...SynapticInsightAbility$$CreateTrigger` **n'existe pas comme symbole** : son corps est fondu par
l'ICF. L'appartenance est etablie slot a slot dans le bloc `methodPointers` du PE, ancre sur son
`$$CreateBehaviour` (le seul symbole propre de la classe) et INDEXE par la position metadata -- la
position 0 y pointe le corps de
`IdunBattleLogic.Entities.Abilities.Active.Loki.SummaryExecutionAddBaseEffectAbility$$CreateTrigger`,
dont le corps ENTIER est `return <DSLTriggers+0x30>`.

Et `<DSLTriggers+0x30>` est ECRIT par `IdunBattleLogic.Entities.DSLTriggers$$InitializeShared` :

    EventTrigger(0x21 = AbilityInit) & <DSLTriggers+0x70> & get_OwnerIsActor

`<+0x70>` est le `YesTrigger` (`IdunBattleLogic.Entities.DSLTriggers$$.ctor` en alloue trois
instances de la meme classe : `+0x40`, `+0x48` = son `op_LogicalNot`, `+0x70`), c'est-a-dire la
branche `ownerNeedsToBeAlive: false` d'`IdunBattleLogic.Entities.DSLTriggers$$On(triggerType,
ownerNeedsToBeAlive)`, dont le corps est
`EventTrigger(t) & <this + (ownerNeedsToBeAlive ? 0x20 : 0x70)>`. Le trigger est donc
`On(AbilityInit, ownerNeedsToBeAlive: false) & get_OwnerIsActor` -> canal **O**
(`ABILITY_INIT_OWNER_EFFECTS`), jamais `ABILITY_TRIGGERS`.

`...SynapticInsightAbility$$CreateBehaviour` :

    AddEffect( 0x4cf = 1231 SynapticInsight_ExtraHits,
               <BaseTriggeredAbility.get_AbilityStateReference>,
               targets = Owner@<DSLSelectors+0x30>,
               turns   = null )                                   -> effet PERMANENT

La surcharge est tranchee par la CIBLE DU `call rel32`, pas par l'arite (quatre surcharges
`DSLBehaviors$$AddEffect` existent, deux d'arite 4) : `+0x56` du corps appelle
`IdunBattleLogic.Entities.DSLBehaviors.AddEffect(effectType, abilityState, targets:
IdunBattle.DSL.ITargetsSelector, turns: System.Nullable<System.Int32>)`, et le `turns` passe est le
litteral `0` -- donc `null`, donc PERMANENT.

===================================================================================================
L'EFFET -- `SynapticInsight_ExtraHitsEffect$$CreateEffectHitsBonusForAttack`, mirror 1:1
===================================================================================================

    EffectBonus.ForAddition(
        trigger  = get_OwnerIsCaster
                 & IsRangedAttack()
                 & (   Any( AdjacentFriends( unit     = Owner@<DSLSelectors+0x30>,
                                             unitTile = Target@<DSLSelectors+0x60>,
                                             unique   = true ),
                            HasFaction( ActiveTarget@<DSLSelectors+0x68>,
                                        UnitFaction.Tyranids = 0xc,
                                        UnitSelectionType.OnlyAliveAndTargetable = 3 ) )
                     | IsInTeamSynapseRange( Target@<+0x60>, Owner@<+0x30> ) ),
        addition = ConfigConst( AbilityConstantType.extraHit = 0x2b, config@this+0x60 ) )

Les DEUX disjoints sont joints par `IdunBattle.DSL.AbilityTrigger$$op_BitwiseOr`, et le tout par
`op_BitwiseAnd` avec `get_OwnerIsCaster & IsRangedAttack` -- l'ordre ci-dessus est celui du corps.

## LA SURCHARGE d'`AdjacentFriends` est la **VARIANTE B**, et le 3e argument n'est PAS un booleen

Les deux surcharges ont la MEME arite (3 arguments apres `this`) et le pseudo-C les affiche sous le
MEME nom -- c'est le TYPE des arguments qui tranche, pas la forme :

  * variante A `(unit: ITargetsSelector, unique: System.Boolean, selectionType: UnitSelectionType)`
    = `Friends(unit, Units(AdjacentTiles(unit), unique, selectionType) - unit, selectionType)` ;
  * variante B `(unit: ITargetsSelector, unitTile: ITargetsSelector, unique: System.Boolean)`
    = `Friends(unit, Units(AdjacentTiles(unitTile), unique, 3) - unitTile, 3)`.

Le call-site passe `(<Sel+0x30>, <Sel+0x60>, 1)` : son 2e argument est un CHAMP de `DSLSelectors`
(un selecteur alloue), pas un petit entier -- c'est donc `unitTile`, et le `1` final est `unique`.
Lire la variante A y donnerait `selectionType = 1 = OnlyAlive`, le filtre qui n'ecarte PAS
`Untargetable` : l'inverse exact de ce que le natif applique.

⚠ Et ce n'est pas la forme des arguments qui tranche ici, c'est la **CIBLE DU `call rel32`** : le
`+0xe2` du corps appelle `IdunBattleLogic.Entities.DSLSelectors$$AdjacentFriends` a la VA de la
variante B (celle dont `frida/methods.tsv` donne la signature `unit, unitTile, unique`), pas celle
de la variante A. Les DEUX surcharges ont la meme arite et le meme nom affiche -- seul le tirage de
l'adresse les separe. Mesure complete de l'ordre des noeuds, lue de la meme facon :
`get_OwnerIsCaster` `+0x66`, `IsRangedAttack` `+0x8d`, `op_BitwiseAnd` `+0x9b`, `AdjacentFriends`
`+0xe2`, `HasFaction` `+0x130`, `Any` `+0x14a`, `IsInTeamSynapseRange` `+0x18a`, `op_BitwiseOr`
`+0x198`, `op_BitwiseAnd` `+0x1a6`, `ConfigConst` `+0x1d7`, `EffectBonus.ForAddition` `+0x216`.

⇒ **L'ANCRE GEOMETRIQUE EST LA CIBLE DU COUP, LA REFERENCE D'EQUIPE EST LE PORTEUR.** Le port lit
donc « les unites adjacentes a la CIBLE (cible elle-meme retiree par l'`op_Subtraction`) qui sont
AMIES du porteur », puis `Any(., HasFaction(It, Tyranids))`. C'est litteralement le
<< adjacent to another Tyranid >> de l'i2, ou << another >> est l'`op_Subtraction`.

⚠ **Le PORTEUR n'est PAS exclu de cet ensemble** : le natif ne soustrait que `unitTile` (la cible).
Un Barbgaunt adjacent a sa propre cible se compte donc lui-meme -- il est ami de lui-meme et
Tyranide. Regime rare (arme `HeavyWeapon` a distance), mais LU, donc porte.

## `IsInTeamSynapseRange`, deja porte (#1011)

`IdunBattleLogic.Entities.DSLTriggers$$IsInTeamSynapseRange(target, team)` alloue
`IsInAuraRangeTrigger(state, query, effectType = 0x41c = 1052 Synapse_Effect, target, team)`. Le
mirror (rayon 2, trait emetteur `Synapse`, centre EXCLU) vit dans `norn_crown._in_team_synapse_range`
-- FOYER UNIQUE, reutilise ici tel quel avec son substrat `team_synapse_positions`.

⚠ **L'ORDRE DES ARGUMENTS EST (target, team)** et le call-site passe `(<Sel+0x60>, <Sel+0x30>)` :
la bulle interrogee est celle de l'EQUIPE DU PORTEUR, evaluee a la position de la CIBLE. C'est
l'inverse de la patte SELF de `NornCrownEffect`, qui interroge la position du PORTEUR.

## MAGNITUDE -- une CONSTANTE, jamais un niveau

`ConfigConst(0x2b)` = `AbilityConstantType.extraHit`, soit la constante `extraHit` de l'ability
`SynapticInsight` (= **2** sur ce build ; le gameconfig ne lui donne AUCUNE `variables` ni
`variablesAffectedByRarityBonus`). Elle n'est donc ni indexee par niveau ni scalee par la rarete --
meme cle `0x2b` que `PowerTrip.extraHit` / `Waaagh.extraHit` / `VoltagheistField.extraHit`.

⚠ Corollaire pour la confrontation : ce passif ne lit AUCUNE variable par niveau, donc le defaut de
harnais d'`--explicit-stats` sur l'`AbilityState` (`#1049-r1`) ne peut pas fausser sa magnitude.

===================================================================================================
CANAL DE PORT
===================================================================================================

`EffectBonus.ForAddition` sur le slot `CreateEffectHitsBonusForAttack` -> un terme de
`IdunBattle.Entities.Formulas.AttackHitsWithModifiersFormula$$Calculate`, canal ATTAQUANT
(`entities/effects/__init__.py::hits_bonus_from_effects`). Ce n'est PAS un
`EffectAdditionalHits` (canal #179) : le bonus ajoute des coups d'ARME, pas un groupe a degat propre.
"""
from __future__ import annotations

from collections.abc import Mapping

from ....dsl.base import Const
from ....services.effect_bonus import EffectBonus, for_addition
from ..base import BaseEffect
from ..magnitude import ability_var
from ...selectors.accessors import Owner, Subject, Target
from ...selectors.units import AdjacentFriends
from ...unit_faction import UnitFaction
from ...unit_selection_type import UnitSelectionType
#: FOYER UNIQUE d'`IsInTeamSynapseRange` (#1011). Liaison de MODULE (forme B) et non de NOM : un
#: `from X import f` gele le binding et desarme tout `monkeypatch.setattr("....norn_crown.<f>", ...)`
#: pose par un test -- cf. la regle d'import du CLAUDE.md, mesuree sur les 28 rouges de #484.
from . import norn_crown as _norn

#: cle gameconfig de l'ability (`TriggeredAbilityType.SynapticInsight = 0x4a9 = 1193`) --
#: l'`AbilityOrEffect` que le `.ctor` de l'effet passe a `BaseEffect`, donc la config du `ConfigConst`.
#: ⚠ Le gameconfig ne porte AUCUNE entree `SynapticInsight_ExtraHits` : la config lue est bien celle
#: de l'ABILITY, pas celle de l'effet homonyme.
ABILITY_ID = "SynapticInsight"
#: `AbilityConstantType 0x2b` (`frida/enums.tsv`), jamais recopie du decompile.
CONST_EXTRA_HIT = "extraHit"
#: `UnitSelectionType 3` -- le litteral que la variante B d'`AdjacentFriends` code EN DUR aux deux
#: etages (`Units(..., unique, 3)` puis `Friends(unit, ..., 3)`).
_SEL = int(UnitSelectionType.OnlyAliveAndTargetable)
#: `HasFaction(ActiveTarget@<DSLSelectors+0x68>, 0xc, 3)` -- `UnitFaction.Tyranids`.
FACTION_TYRANIDS = UnitFaction.Tyranids
#: cle du contexte per-coup : tri-etat du PREMIER disjoint (`Any(AdjacentFriends(...), HasFaction)`),
#: evalue par les deux faces (`runner/components.py` en COMBAT, `playbook/scene.py` en PREDICTION).
#: `None` / cle absente = NON MESURE -> le disjoint se FERME, jamais un `False` invente.
CTX_ADJACENT_TYRANID = "synaptic_insight_adjacent_tyranid"


def adjacent_tyranid_friend_trigger():
    """L'ARBRE DSL du PREMIER disjoint de
    `...SynapticInsight_ExtraHitsEffect$$CreateEffectHitsBonusForAttack`, noeud par noeud
    (doctrine #149 : l'artefact natif est un SELECTEUR sous un trigger existentiel, donc le port est
    un arbre) :

        Any( AdjacentFriends(unit = Owner@+0x30, unitTile = Target@+0x60, unique: true),
             HasFaction(ActiveTarget@+0x68, UnitFaction.Tyranids = 0xc, 3) )

    `AdjacentFriends(center = Target(), radius = Const(1), reference = Owner(), selection_type = 3)`
    est la VARIANTE B cote port : son 3e parametre natif est l'ANCRE GEOMETRIQUE (`center` ici) et le
    1er la REFERENCE D'EQUIPE (`reference`). Le defaut `reference = ctx.caster` du port serait ici
    JUSTE par coincidence (`get_OwnerIsCaster` fait du porteur le caster), mais il est passe
    EXPLICITEMENT : c'est ce que le natif ecrit, et le collapse ne survivrait pas a un contexte bati
    sur une autre unite.

    `Subject()` = `ActiveTarget@<DSLSelectors+0x68>` = l'element courant lie par le `Any`
    (`XAnyYTrigger.<>c__DisplayClass4_0$$<ShouldTrigger>b__0` construit un `AbilityEntities` NEUF ou
    `ability+0x180` porte l'element) -- le MEME slot que celui d'un `Filter`.

    Le collapse `Any(sel, P) -> P(sel)` attesté pour `HasEffect` NE VAUT PAS ici : le `HasFaction` du
    port resout UNE entite (`resolve_unit`, mirror de `TargetsSelector$$SelectFirst`, #521) et non
    l'ensemble, donc sans le noeud `Any` seule la PREMIERE unite adjacente serait testee.

    Import DIFFERE et **PORTEUR**, classe MECANIQUEMENT (regle du CLAUDE.md) : charger
    `engine.entities.triggers` SEUL dans un process FRAIS re-entre `engine.entities.effects.factory`
    (via `services.movement_query` -> `runner.components` -> `entities.effects`), donc CE module,
    donc `engine.entities.triggers` partiellement initialise -- `ImportError: cannot import name
    'Any'`. Hisser fermerait le cycle. Les deux autres consommateurs de `...triggers` sous
    `effects/loki/` (`daemonic_patrons`, `hits`) portent le MEME differe pour la MEME cause ; celui
    d'`instinctive_behaviour_condition` est au niveau module parce que `factory.py` n'importe PAS ce
    module-la (il n'importe que son voisin `instinctive_behaviour`)."""
    from ...triggers import Any, HasFaction
    return Any(AdjacentFriends(Target(), Const(1), Owner(), _SEL),
               HasFaction(Subject(), int(FACTION_TYRANIDS)))


class SynapticInsightExtraHitsEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.SynapticInsight_ExtraHitsEffect` (`EffectType 0x4cf` = 1231).
    Cf. l'en-tete du module pour l'arbre natif complet et les deux pieges de surcharge.

    CE QUE LA CLASSE DECLARE (`global-metadata.dat`, `il2cpp_metadata.type_methods`) -- QUATRE
    entrees, et **`frida/methods.tsv` n'en montre que DEUX** (l'absence n'y prouve rien : les deux
    autres ont un corps fondu par l'ICF) :

        [.ctor, CreateActiveCondition (slot 62), CreateTargetSelector (slot 64),
         CreateEffectHitsBonusForAttack (slot 84)]

    Les deux sans symbole propre sont lues dans le bloc `methodPointers` du PE, calage retenu par
    MAXIMISATION des concordances (2/2 methodes nommees, positions 0 et 3 -- donc le bloc est
    encadre, pas extrapole) :

        CreateActiveCondition -> corps partage avec
                                 `WayOfTheShortBlade_AdditionalAttackMarkerEffect$$
                                 CreateActiveCondition` = `return <DSLTriggers+0x40>` = constante
                                 VRAIE (meme classe que le `YesTrigger` de `<+0x70>`, cf.
                                 `IdunBattleLogic.Entities.DSLTriggers$$.ctor`) -> TOUJOURS ACTIF ;
        CreateTargetSelector  -> corps partage avec `WhisperingWebEffect$$CreateTargetSelector`
                                 = `return <DSLSelectors+0x30>` = `Owner` -> SELF-effect.

    Donc : PAS d'`active_condition_ported` (le regime commun `BaseEffect.is_active` coincide, et
    poser le flag inventerait un gate que le decompile ne porte pas), et le canal est bien celui de
    l'ATTAQUANT (l'effet vit sur son porteur), pas une aura.

    ⚠ Corollaire de montage : `CreateActiveCondition` constante VRAIE => l'effet est TOUJOURS capte
    par `decisionView.effects` sur un runner frais, donc le seed `ABILITY_INIT_OWNER_EFFECTS` est un
    FILET idempotent, pas le seul chemin."""

    def create_effect_hits_bonus_for_attack(self, is_normal_attack: bool = True,
                                            att_ctx: "Mapping | None" = None) -> EffectBonus | None:
        """`ForAddition( get_OwnerIsCaster & IsRangedAttack & (<adjacent Tyranide> | <bulle Synapse>),
        ConfigConst(0x2b = extraHit) )`.

        `get_OwnerIsCaster` est satisfait STRUCTURELLEMENT sur ce canal : l'agregateur n'itere que
        les effets de l'ATTAQUANT.

        ⚠ **AUCUN noeud `IsNormalAttack`** -- contraste `PowerTrip_FullHealth` / `VoltagheistField`
        / `Waaagh_ExtraHits`, qui sont ses voisins de forme sur ce canal. Le bonus s'applique donc
        AUSSI aux attaques d'ability de la famille ATTACK, qui traversent la meme formule. Ne pas
        recopier le voisin.
        """
        c = att_ctx or {}
        # `IsRangedAttack()` = la nature du coup est PROUVEE distance. TRI-ETAT (#106) : le canal
        # COUPS porte `is_melee`, dont `None` = nature NON DECLAREE -> le gate se FERME (il ne
        # fabrique pas une attaque a distance). Mirror de `entities/effects/base.py::is_ranged_attack`
        # applique au canal qui expose `is_melee` plutot qu'`is_ranged`.
        if c.get("is_melee") is not False:
            return None
        # Les DEUX disjoints se ferment INDEPENDAMMENT quand LEUR substrat manque : le natif rend un
        # `op_BitwiseOr`, donc un disjoint indecidable ne doit pas contaminer l'autre (meme
        # discipline que `DeathwingEffect._double_effect_condition`).
        # 1. `Any(AdjacentFriends(Owner, Target, unique), HasFaction(It, Tyranids, 3))` -- l'ARBRE
        #    vit dans `adjacent_tyranid_friend_trigger()` et est evalue par les deux faces, qui
        #    posent son verdict ici. `None` = NON MESURE, jamais un `False` invente.
        if (c.get(CTX_ADJACENT_TYRANID) is not True
                # 2. `IsInTeamSynapseRange(Target@+0x60, Owner@+0x30)` -- la bulle de l'EQUIPE DU
                #    PORTEUR (l'attaquant sur ce canal), evaluee a la position de la CIBLE. Foyer
                #    UNIQUE `norn_crown._in_team_synapse_range` (#1011), meme substrat
                #    `team_synapse_positions`.
                and _norn._in_team_synapse_range(                       # noqa: SLF001 (foyer UNIQUE)
                    (c.get("team_by_id") or {}).get(c.get("att_id")),
                    c.get("t_pos"), c) is not True):
            return None
        n = ability_var(ABILITY_ID, CONST_EXTRA_HIT, is_constant=True)   # ConfigConst 0x2b (= 2)
        return for_addition(True, int(n)) if n else None                 # EffectBonus +0x10
