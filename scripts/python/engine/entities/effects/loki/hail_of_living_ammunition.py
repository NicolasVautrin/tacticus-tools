"""`HailOfLivingAmmunition` -- le passif d'ESSAIM RANGED des Termagants tyranides (#1078).

i2 `Abilities/HailOfLivingAmmunition_CurrentLevelDescription` :
    << This unit has +1 hit in ranged attacks for each Termagant it is adjacent to. >>

===================================================================================================
RECENSEMENT PAR LES TABLES -- ce que le build porte VRAIMENT
===================================================================================================

  `IdunBattleLogic.Entities.Abilities.Active.Loki.HailOfLivingAmmunitionAbility`
      GetEffectType -> corps ENTIER `return 0x412` (= `EffectType.HailOfLivingAmmunition_ExtraHits`
      = 1042). Classe parente (`frida/classes.tsv`) :
      `IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility` -- l'ability POSE elle-meme son
      effet sur l'OWNER, il n'y a donc NI `CreateBehaviour` NI `CreateTrigger` a porter.
      ⚠ Le namespace `Active` ne dit PAS la voie : le kit l'attribue en `passiveAbilities` et
      l'ordinal 1042 est un `TriggeredAbilityType` (`ActiveAbilityType` 1042 = `FlailSwing`, un
      homonyme d'ORDINAL qui ne nomme pas la meme chose). Apparier par le NOM.
  `IdunBattle.Entities.Effects.Loki.HailOfLivingAmmunitionExtraHitsEffect` (`EffectType 0x412`)
      .ctor · CreateEffectHitsBonusForAttack

CE QUI N'EXISTE PAS, et c'est un RESULTAT : aucune `CreateActiveCondition`, aucune
`CreateTargetSelector`, aucune `GetHits` intermediaire -- l'arbre est INLINE dans
`CreateEffectHitsBonusForAttack`, et c'est un SELF-effect strict (pas d'aura).

===================================================================================================
L'ARBRE (mirror 1:1 du decompile de
`IdunBattle.Entities.Effects.Loki.HailOfLivingAmmunitionExtraHitsEffect$$CreateEffectHitsBonusForAttack`)
===================================================================================================

    ids = AbilityConfiguration.GetStringArrayConstant(config@this+0x60,
                                                      AbilityConstantType.unitIds = 0x37)
    sel = DSLSelectors.AdjacentFriends(unit = Owner@DSLSelectors+0x30,
                                       unique = true, selectionType = 3)
    sel = DSLSelectors.UnitsWithIds(sel, ids)
    amt = DSLFormulas.Multiply(
              DSLFormulas.Direct(AbilityConfiguration.GetNumberConstant(config,
                                     AbilityConstantType.extraHit = 0x2b)),
              DSLFormulas.Count(sel))
    trg = DSLTriggers.get_OwnerIsActor & DSLTriggers.IsRangedAttack()
    return EffectBonus.ForAddition(trg, amt)

## CE N'EST PAS LE JUMEAU `HungeringSwarm`, ET LES DEUX ECARTS SONT LUS

`HungeringSwarm` (1041, Hormagaunts) partage la famille -- meme `AOwnerEffectTriggeredAbility`,
memes constantes `extraHit`/`unitIds`, meme canal de COUPS -- mais son arbre est DIFFERENT sur les
deux axes qui decident du resultat :

    HungeringSwarm  : Friends(Owner, AdjacentUnits(**Target**, 3) op_Subtraction Caster, 3)
                      trigger `get_OwnerIsActor & IsMeleeAttack`
    HailOfLiving... : AdjacentFriends(**Owner**, unique = 1, 3)
                      trigger `get_OwnerIsActor & IsRangedAttack`

Le centre est l'ATTAQUANT ici, la CIBLE la-bas ; le gate est DISTANCE ici, MELEE la-bas. Recopier
le voisin de forme aurait compte le mauvais voisinage sur la mauvaise attaque.

⚠ `AdjacentFriends` EXCLUT le porteur (`Friends(unit, Units(AdjacentTiles(unit), unique,
selectionType) op_Subtraction unit, selectionType)`) et RIEN ne le re-ajoute (pas d'`op_Addition
Owner`, contraste `KustomForceFieldReworked`) -- << for each Termagant it IS ADJACENT TO >>.

## LA CONSTANTE `unitIds` COUVRE LES VARIANTES, ET C'EST LU (contraste `HungeringSwarm`)

`abilities.HailOfLivingAmmunition.constants.unitIds` =
    "tyranNpc3Termagant,tyranSmnTermagant,GuildBoss1Npc1TyranTermagantLeviathan,
     GuildBoss1Npc2TyranTermagantKronos,GuildBoss1Npc3TyranTermagantGorgon"

Les CINQ porteurs npc du gameconfig sont `tyranNpc3Termagant`, `...Kronos`, `...Gorgon`,
`..._SyncPvp_Kronos`, `..._SyncPvp_Gorgon`, plus le summon `tyranSmnTermagant`. Leurs `visualId`
gameconfig :

    tyranNpc3Termagant                 -> (absent)  => l'id de config lui-meme
    tyranNpc3TermagantKronos           -> GuildBoss1Npc2TyranTermagantKronos
    tyranNpc3TermagantGorgon           -> GuildBoss1Npc3TyranTermagantGorgon
    tyranNpc3Termagant_SyncPvp_Kronos  -> GuildBoss1Npc2TyranTermagantKronos
    tyranNpc3Termagant_SyncPvp_Gorgon  -> GuildBoss1Npc3TyranTermagantGorgon
    tyranSmnTermagant                  -> tyranNpc3Termagant

La constante liste donc les DEUX formes de chaque variante -- le filtre est EXACT quel que soit le
cote du canal (`UnitsWithIds` compare l'id de CONFIG cote natif, le `visualId` du `decisionView`
cote port ; cf. la docstring d'`entities/selectors/units.py::UnitsWithIds`). C'est mesure, pas
suppose : cf. `probe_1078_hail_of_living_ammunition.py`, phase `kronos`.

## MAGNITUDE

`constants.extraHit` = "1". Une CONSTANTE (`GetNumberConstant`, cle `AbilityConstantType.extraHit`
= 0x2b) : ni indexee par niveau, ni scalee par le multiplicateur de rarete -- meme forme que
`HungeringSwarm` / `HeadClaimer` / `PowerTrip`.
"""
from __future__ import annotations

from collections.abc import Mapping

from ....dsl.base import Const, DslContext
from ....services.effect_bonus import EffectBonus, for_addition
from ...ability_constant_type import AbilityConstantType
# Sous-modules, JAMAIS le baril `...selectors` : meme forme que `loki/hungering_swarm.py`, le
# precedent immediat de ce paquet pour un effet qui construit un arbre de selecteurs.
from ...selectors.accessors import Owner
from ...selectors.units import AdjacentFriends, UnitsWithIds
from ...unit_selection_type import UnitSelectionType
from ..base import BaseEffect
from ..magnitude import ability_var

#: cle gameconfig de l'ability -- l'`AbilityOrEffect` que le `.ctor` de l'effet passe a `BaseEffect`,
#: donc la config que `GetNumberConstant` / `GetStringArrayConstant` indexent.
ABILITY_ID = "HailOfLivingAmmunition"
#: `AbilityConstantType 0x2b = 43` et `0x37 = 55` (`frida/enums.tsv`) -- resolus par leur NOM.
CONST_EXTRA_HIT = AbilityConstantType.extraHit.name       # 0x2b -> "extraHit"
CONST_UNIT_IDS = AbilityConstantType.unitIds.name         # 0x37 -> "unitIds"
#: le litteral `3` passe a `AdjacentFriends` par le decompile (surcharge `(unit, unique,
#: selectionType)` -- le 3e argument du call-site est le litteral booleen `1`, pas un
#: `TargetsSelector*`, donc la surcharge `(unit, unitTile, unique)` est exclue).
SELECTION_TYPE = UnitSelectionType.OnlyAliveAndTargetable


def hail_of_living_ammunition_selector(unit_ids):
    """Mirror 1:1 de l'etage SELECTEUR de
    `...HailOfLivingAmmunitionExtraHitsEffect$$CreateEffectHitsBonusForAttack` (cf. l'en-tete).

    `reference` est EXPLICITEMENT `Owner()` : le natif ecrit `Friends(unit = Owner, ...)`, la
    reference d'equipe EST le centre. Le collapse implicite sur `ctx.caster` donnerait le meme
    ensemble ici (Owner == Caster sur un effet auto-pose d'`AOwnerEffectTriggeredAbility`) mais ce
    n'est pas ce que le natif ecrit.

    Isole pour etre confrontable seul, jamais pour etre reutilise ailleurs.
    """
    ring = AdjacentFriends(Owner(), Const(1), Owner(), selection_type=int(SELECTION_TYPE))
    return UnitsWithIds(ring, unit_ids)


def _dsl_context_from_board(c: Mapping) -> "DslContext | None":
    """Monte le `DslContext` que l'arbre ci-dessus interroge, depuis le `board` de
    `IdunBattle.Entities.Formulas.AttackHitsWithModifiersFormula` (memes cles que le jumeau de
    famille `loki/hungering_swarm.py`).

    `Owner` / `Caster` / `Actor` sont TOUS l'attaquant : le canal `hits_bonus_from_effects`
    n'interroge que les effets de l'ATTAQUANT, et l'effet est auto-pose par
    `AOwnerEffectTriggeredAbility` sur son porteur -- donc `Owner == Caster == Actor == att_id`.

    Rend `None` (donc AUCUNE contribution) des qu'une entree manque -- degradation fidele
    << present != applique >>, jamais un compte fabrique.
    """
    att_id, tgt_id = c.get("att_id"), c.get("tgt_id")
    pos, team, vid = c.get("pos_by_id"), c.get("team_by_id"), c.get("vid_by_id")
    # SANTE : `engine/dsl/base.py::_is_alive` (que `_within` applique a CHAQUE unite) classe MORT
    # tout dict sans `hp > 0` ni `hpMax`. Sans ces deux tables, l'anneau sort VIDE -- meme mesure
    # que #1018. Elles sont LUES, jamais fabriquees.
    hp, hpmax = c.get("hp_by_id"), c.get("hpmax_by_id")
    if att_id is None or tgt_id is None or not pos or not team or vid is None \
            or hp is None or hpmax is None:
        return None
    override = {att_id: c.get("attack_pos") or pos.get(att_id),
                tgt_id: c.get("t_pos") or pos.get(tgt_id)}
    units, by_id = [], {}
    for uid, p in pos.items():
        pp = override.get(uid, p)
        if not pp:
            continue
        u = {"id": uid, "pos": {"col": int(pp[0]), "row": int(pp[1])},
             "team": team.get(uid), "visualId": vid.get(uid), "alive": True,
             "hp": hp.get(uid), "hpMax": hpmax.get(uid)}
        units.append(u)
        by_id[uid] = u
    att, tgt = by_id.get(att_id), by_id.get(tgt_id)
    if att is None or tgt is None:
        return None
    return DslContext(units=units, caster=att, target=tgt, owner=att, actor=att,
                      board=c.get("dsl_board"))


class HailOfLivingAmmunitionExtraHitsEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.HailOfLivingAmmunitionExtraHitsEffect`
    (`EffectType 0x412 = 1042`). Cf. l'en-tete du module pour l'arbre natif et sa lecture."""

    def create_effect_hits_bonus_for_attack(self, is_normal_attack: bool = True,
                                            att_ctx: "Mapping | None" = None) -> EffectBonus | None:
        c = att_ctx or {}
        # `DSLTriggers$$IsRangedAttack` -- gate LU au decompile. Tri-etat #106 : `is_melee = None`
        # = nature du coup NON declaree -> `BattleQuery$$IsRangedAttack` ne peut pas etre vrai ->
        # pas de contribution (meme convention que `BigTargetAdjacentEffect` sur ce canal).
        # `get_OwnerIsActor` est deja rendu par le canal (`hits_bonus_from_effects` n'interroge que
        # les effets de l'ATTAQUANT). PAS d'`IsNormalAttack` dans l'arbre : le bonus vaut aussi pour
        # une attaque d'ABILITY a distance.
        if c.get("is_melee") is not False:
            return None
        n = ability_var(ABILITY_ID, CONST_EXTRA_HIT, is_constant=True)   # GetNumberConstant(0x2b)
        ids = _unit_ids()                                               # GetStringArrayConstant(0x37)
        if not n or not ids:
            return None
        ctx = _dsl_context_from_board(c)
        if ctx is None:
            return None
        # DIFFERE, et il est PORTEUR -- meme mesure que `loki/hungering_swarm.py` (#1018) : hisser
        # cet import ferme le cycle `entities.formulas -> services.movement_query ->
        # runner.components -> entities.effects.__init__ -> effects.factory -> CE MODULE ->
        # entities.formulas`. Les SELECTEURS, eux, sont en tete (import isole mesure).
        # Forme B (module lie, appels attributaires) : un `monkeypatch.setattr` sur ces noeuds mord.
        import engine.entities.formulas as _F
        cnt = _F.Count(hail_of_living_ammunition_selector(ids)).evaluate(ctx)   # DSLFormulas$$Count
        total = _F.Multiply(_F.Get(int(n)),                                     # Multiply(Direct(n),
                            _F.Get(int(cnt))).evaluate(ctx)                     #          Count)
        return for_addition(True, int(total)) if total else None


def _unit_ids() -> "list[str]":
    """`AbilityConfiguration$$GetStringArrayConstant(config, AbilityConstantType.unitIds = 0x37)`.

    Le gameconfig encode cette constante comme une chaine separee par des virgules ;
    `UnitsWithIds` accepte les deux formes, mais on normalise ici pour que le selecteur voie
    toujours une LISTE -- et pour que le test puisse l'assertionner. `[]` si la constante est
    absente (l'arbre rend alors l'ensemble VIDE, ce que le natif fait aussi : l'accumulateur
    d'`UnitsWithIds` part du selecteur vide)."""
    try:
        import gameconfig as _GC
    except Exception:
        return []
    consts = ((_GC.ability(ABILITY_ID) or {}).get("constants") or {})
    raw = consts.get(CONST_UNIT_IDS)
    return [s.strip() for s in str(raw).split(",") if s.strip()] if raw else []
