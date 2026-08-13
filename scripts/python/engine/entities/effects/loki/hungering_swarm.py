"""`HungeringSwarm` -- le passif d'ESSAIM des Hormagaunts/Ripper Swarms tyranides (#1018).

i2 `Abilities/HungeringSwarm_CurrentLevelDescription` :
    << Whenever this unit performs a melee attack, it deals +1 hit for each other friendly
    Hormagaunt or Ripper Swarm adjacent to the target. >>

===================================================================================================
RECENSEMENT PAR LE BLOC `methodPointers` -- ce que le build porte VRAIMENT
===================================================================================================

  `IdunBattleLogic.Entities.Abilities.Active.Loki.HungeringSwarmAbility`
      GetEffectType -> `return 0x411` (= `EffectType.HungeringSwarm_ExtraHits` = 1041).
      Classe parente (`frida/classes.tsv`) : `IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility`
      -- l'ability POSE elle-meme son effet sur l'OWNER, il n'y a donc NI `CreateBehaviour` NI
      `CreateTrigger` a porter. Cote port l'effet arrive par la voie normale des effets captes
      (`decisionView.effects[].name` -> `EFFECT_CLASSES`), comme `PowerTrip_FullHealth`.
  `IdunBattle.Entities.Effects.Loki.HungeringSwarmExtraHitsEffect` (`EffectType 0x411 = 1041`)
      .ctor · CreateEffectHitsBonusForAttack

CE QUI N'EXISTE PAS, et c'est un RESULTAT :
  * `CreateActiveCondition` (slot 61) et `CreateTargetSelector` (slot 63) sont declarees ABSTRAITES
    par `IdunBattle.Entities.Effects.BaseEffect` et l'effet les rend par un corps DEDUPLIQUE par
    IL2CPP -- le meme que 320 autres classes (`return null`). Donc : ni gate d'activite
    (pas d'`active_condition_ported`), ni aura (c'est un SELF-effect strict).
  * aucune `GetHits` / `GetCurrentBonus` intermediaire : l'arbre est INLINE dans
    `CreateEffectHitsBonusForAttack`.

===================================================================================================
L'ARBRE (mirror 1:1 du decompile de
`IdunBattle.Entities.Effects.Loki.HungeringSwarmExtraHitsEffect$$CreateEffectHitsBonusForAttack`)
===================================================================================================

    ids = AbilityConfiguration.GetStringArrayConstant(config@this+0x60,
                                                      AbilityConstantType.unitIds = 0x37)
    sel = DSLSelectors.AdjacentUnits(origin = Target@DSLSelectors+0x60,
                                     unique = true, selectionType = 3)
    sel = TargetsSelector.op_Subtraction(sel, Caster@DSLSelectors+0x48)
    sel = DSLSelectors.Friends(of = Owner@DSLSelectors+0x30, entities = sel, selectionType = 3)
    sel = DSLSelectors.UnitsWithIds(sel, ids)
    amt = DSLFormulas.Multiply(
              DSLFormulas.Direct(AbilityConfiguration.GetNumberConstant(config,
                                     AbilityConstantType.extraHit = 0x2b)),
              DSLFormulas.Count(sel))
    trg = DSLTriggers.get_OwnerIsActor & DSLTriggers.IsMeleeAttack()
    return EffectBonus.ForAddition(trg, amt)

Les trois slots de `DSLSelectors` sont ceux deja etablis par le port (`+0x30` = Owner,
`+0x48` = Caster, `+0x60` = Target ; cf. `entities/selectors/accessors.py` et
`entities/abilities/active_ability.py`) -- pas une deduction locale.

## POURQUOI L'ORDRE DES NOEUDS IMPORTE (et pourquoi on ne recopie AUCUN voisin)

La soustraction porte sur `Caster`, et elle est faite **AVANT** le `Friends` : l'ensemble de depart
est `AdjacentUnits(Target)`, donc les DEUX camps ; on en retire le caster ; ensuite seulement on
garde les allies du porteur. Comme `Owner == Caster` sur un effet auto-pose de
`AOwnerEffectTriggeredAbility`, le resultat est bien << each OTHER friendly >> de l'i2. Inverser les
deux etages donnerait le meme ensemble ici, mais ce n'est PAS ce que le natif ecrit -- et le port
mirrore l'arbre, pas son extension sur un cas particulier.

⚠ `AdjacentUnits` ne filtre AUCUNE equipe (contraste `AdjacentEnemies` / `AdjacentFriends`) : c'est
le `Friends` qui le fait, et son referent est `Owner`, pas la cible. Un ennemi Hormagaunt adjacent a
la cible ne compte donc PAS pour l'attaquant.

## LA CONSTANTE `unitIds` NE CONTIENT PAS LES VARIANTES KRONOS/GORGON, ET C'EST LU

`abilities.HungeringSwarm.constants.unitIds` =
    "tyranNpc1Hormagaunt,tyranNpc2RipperSwarm,tyranSmnHormagaunt,tyranSmnRipperSwarm"

Le filtre natif est `IdunBattle.Entities.UnitExtensions$$HasUnitId(unit, id)` =
`idun.shared.UnitNamingConventions$$GetUnitIdWithoutRarity(GetUnitId(unit)) == id`, et
`GetUnitIdWithoutRarity` est LITTERALEMENT `configUnitId.Split(':')[0]` (decompile) -- il retire un
suffixe de RARETE, jamais un suffixe de variante. Les cinq porteurs npc du gameconfig sont
`tyranNpc1Hormagaunt`, `...Kronos`, `...Gorgon`, `..._SyncPvp_Kronos`, `..._SyncPvp_Gorgon` : SEUL
le premier est dans la liste. Deux Kronos adjacents a la meme cible ne se comptent donc PAS l'un
l'autre. Ce n'est pas une approximation du port : c'est ce que la constante dit.

⚠ La docstring de `entities/selectors/units.py::UnitsWithIds` cite encore
`GetUnitIdWithoutLevel` ; sur le build `rnca9r7q6c` le corps appelle
`GetUnitIdWithoutRarity`. Meme semantique pour ce port (comparaison sur l'id de CONFIG),
donc pas de correction de fond a faire ici -- signale, pas edite (foyer d'un autre).

## REDUCTION OFFLINE : AUCUNE, et c'est MESURE

Le champ `visualId` du dict d'unite porte l'id de CONFIG pour une unite spawnee offline et l'id
VISUEL pour une unite seedee du live (cf. la docstring d'`UnitsWithIds`). Or le gameconfig donne
`tyranSmnHormagaunt.visualId == "tyranNpc1Hormagaunt"` et
`tyranSmnRipperSwarm.visualId == "tyranNpc2RipperSwarm"` : la constante liste donc DEJA les deux
formes de chaque unite, exactement comme l'`affectedUnitIds` de SupremeCommander. Le filtre est
EXACT des deux cotes du canal, sans elargissement.

## MAGNITUDE

`abilities.HungeringSwarm.constants.extraHit` = "1". Une CONSTANTE (`GetNumberConstant`, cle
`AbilityConstantType.extraHit` = 0x2b) : ni indexee par niveau, ni scalee par le multiplicateur de
rarete -- meme forme que `HeadClaimer` / `UnstoppableFerocity` / `PowerTrip`.
"""
from __future__ import annotations

from collections.abc import Mapping

from ....dsl.base import DslContext
from ....services.effect_bonus import EffectBonus, for_addition
from ...ability_constant_type import AbilityConstantType
# Sous-modules, JAMAIS le baril `...selectors` : meme forme que `loki/summary_execution.py`, le
# precedent de ce paquet pour un effet qui construit un arbre de selecteurs.
from ...selectors.accessors import Owner, Target
from ...selectors.tiles import Caster
from ...selectors.units import AdjacentUnits, Friends, Sub, UnitsWithIds
from ...unit_selection_type import UnitSelectionType
from ..base import BaseEffect
from ..magnitude import ability_var

#: cle gameconfig de l'ability -- l'`AbilityOrEffect` que le `.ctor` de l'effet passe a `BaseEffect`,
#: donc la config que `GetNumberConstant` / `GetStringArrayConstant` indexent.
ABILITY_ID = "HungeringSwarm"
#: `AbilityConstantType 0x2b = 43` et `0x37 = 55` (`frida/enums.tsv`) -- resolus par leur NOM.
CONST_EXTRA_HIT = AbilityConstantType.extraHit.name       # 0x2b -> "extraHit"
CONST_UNIT_IDS = AbilityConstantType.unitIds.name         # 0x37 -> "unitIds"
#: le litteral `3` passe a `AdjacentUnits` ET a `Friends` par le decompile.
SELECTION_TYPE = UnitSelectionType.OnlyAliveAndTargetable


def hungering_swarm_selector(unit_ids):
    """Mirror 1:1 de l'etage SELECTEUR de
    `...HungeringSwarmExtraHitsEffect$$CreateEffectHitsBonusForAttack` (cf. l'en-tete du module).

    Isole du `create_effect_hits_bonus_for_attack` pour etre confrontable seul (le test #1018
    l'evalue directement contre un `DslContext` fabrique), jamais pour etre reutilise ailleurs.
    """
    adjacents = AdjacentUnits(Target(), None, selection_type=int(SELECTION_TYPE))
    others = Sub(adjacents, Caster())                     # op_Subtraction(., Caster@+0x48)
    friends = Friends(others, reference=Owner(), selection_type=int(SELECTION_TYPE))
    return UnitsWithIds(friends, unit_ids)


def _dsl_context_from_board(c: Mapping) -> "DslContext | None":
    """Monte le `DslContext` que l'arbre ci-dessus interroge, depuis le `board` de
    `IdunBattle.Entities.Formulas.AttackHitsWithModifiersFormula` (les memes cles `pos_by_id` /
    `team_by_id` que les autres consommateurs de ce canal, plus `vid_by_id`).

    `Owner` / `Caster` / `Actor` sont TOUS l'attaquant : le canal `hits_bonus_from_effects`
    n'interroge que les effets de l'ATTAQUANT, et l'effet est auto-pose par
    `AOwnerEffectTriggeredAbility` sur son porteur -- donc `Owner == Caster == Actor == att_id`,
    l'hypothese standard, ici VERIFIEE et non supposee.

    Rend `None` (donc AUCUNE contribution) des qu'une entree manque -- degradation fidele
    << present != applique >>, jamais un compte fabrique.
    """
    att_id, tgt_id = c.get("att_id"), c.get("tgt_id")
    pos, team, vid = c.get("pos_by_id"), c.get("team_by_id"), c.get("vid_by_id")
    # SANTE : `engine/dsl/base.py::_is_alive` (que `_within` applique a CHAQUE unite) classe MORT
    # tout dict sans `hp > 0` ni `hpMax`. Sans ces deux tables, `AdjacentUnits` rend l'ensemble
    # VIDE -- mesure #1018, premier etage divergent du port. Elles sont LUES (jamais un `hp = 1`
    # invente), donc leur absence est un contexte INCOMPLET : on ne contribue pas.
    hp, hpmax = c.get("hp_by_id"), c.get("hpmax_by_id")
    if att_id is None or tgt_id is None or not pos or not team or vid is None \
            or hp is None or hpmax is None:
        return None
    # `attack_pos` = la tuile HYPOTHETIQUE d'ou l'attaque part (face DECISION balayee) ; elle prime
    # sur la position courante de l'attaquant, comme partout ailleurs sur ce canal. La cible, elle,
    # est a `t_pos`.
    override = {att_id: c.get("attack_pos") or pos.get(att_id), tgt_id: c.get("t_pos") or pos.get(tgt_id)}
    units, by_id = [], {}
    for uid, p in pos.items():
        pp = override.get(uid, p)
        if not pp:
            continue
        # `alive: True` n'est pas une invention : les DEUX constructeurs de ce board
        # (`runner/damage_model.py::build_hits_board` et `playbook/prediction/normal_attack.py`)
        # n'y mettent QUE des unites vivantes (#57m -- << le board natif = OCCUPATION DE TUILE >>).
        # `hp`/`hpMax` sont LUS, eux : ils portent la 3e branche de
        # `IdunBattle.Entities.Components.HealthComponent$$IsAlive` (`hp <= 0` ET `max <= 0` ->
        # VIVANT), que `genesSmnDecoy` exerce reellement.
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


class HungeringSwarmExtraHitsEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.HungeringSwarmExtraHitsEffect` (`EffectType 0x411 = 1041`).
    Cf. l'en-tete du module pour l'arbre natif et sa lecture."""

    def create_effect_hits_bonus_for_attack(self, is_normal_attack: bool = True,
                                            att_ctx: "Mapping | None" = None) -> EffectBonus | None:
        c = att_ctx or {}
        # `DSLTriggers$$IsMeleeAttack` -- gate LU au decompile. Tri-etat conserve : `is_melee = None`
        # = nature de l'attaque NON declaree -> le predicat natif ne peut pas etre vrai -> pas de
        # contribution (meme convention que `BigTargetAdjacentEffect` sur ce canal).
        # `get_OwnerIsActor` est deja rendu par le canal (`hits_bonus_from_effects` n'interroge que
        # les effets de l'ATTAQUANT) -- PAS d'`IsNormalAttack` dans l'arbre, donc le bonus vaut
        # aussi pour les attaques d'ABILITY en melee (i2 << performs a melee attack >>).
        if c.get("is_melee") is not True:
            return None
        n = ability_var(ABILITY_ID, CONST_EXTRA_HIT, is_constant=True)   # GetNumberConstant(0x2b)
        ids = _unit_ids()                                               # GetStringArrayConstant(0x37)
        if not n or not ids:
            return None
        ctx = _dsl_context_from_board(c)
        if ctx is None:
            return None
        # DIFFERE, et c'est un differe PORTEUR -- MESURE, pas redoute (#1018) : hisser cet import
        # ferme le cycle `entities.formulas -> services.movement_query -> runner.components ->
        # entities.effects.__init__ -> effects.factory -> CE MODULE -> entities.formulas`, et
        # `import engine.entities.formulas` en process FRAIS leve alors `ImportError` (le module
        # ne s'importe plus seul -- l'invariant << 430/430 >> tombe). Les SELECTEURS, eux, sont en
        # tete : `import engine.entities.selectors.units` seul ne tire PAS ce module (mesure).
        # Forme B (module lie, appels attributaires) : un `monkeypatch.setattr` sur ces noeuds mord.
        import engine.entities.formulas as _F
        cnt = _F.Count(hungering_swarm_selector(ids)).evaluate(ctx)      # DSLFormulas$$Count
        total = _F.Multiply(_F.Get(int(n)),                              # Multiply(Direct(n), Count)
                            _F.Get(int(cnt))).evaluate(ctx)
        return for_addition(True, int(total)) if total else None


def _unit_ids() -> "list[str]":
    """`AbilityConfiguration$$GetStringArrayConstant(config, AbilityConstantType.unitIds = 0x37)`.

    Le gameconfig encode cette constante comme une chaine separee par des virgules (meme forme que
    l'`affectedUnitIds` de SupremeCommander) ; `UnitsWithIds` accepte les deux formes, mais on
    normalise ici pour que le selecteur voie toujours une LISTE -- et pour que le test puisse
    l'assertionner. `[]` si la constante est absente (l'arbre rend alors l'ensemble VIDE, ce que le
    natif fait aussi : l'accumulateur d'`UnitsWithIds` part du selecteur vide)."""
    try:
        import gameconfig as _GC
    except Exception:
        return []
    consts = ((_GC.ability(ABILITY_ID) or {}).get("constants") or {})
    raw = consts.get(CONST_UNIT_IDS)
    return [s.strip() for s in str(raw).split(",") if s.strip()] if raw else []
