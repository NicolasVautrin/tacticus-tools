"""Le selecteur `UnitsWithAnyValidTarget` -- filtre « cette unite a-t-elle quelqu'un a frapper ».

Tranche PROPRE (et non un ajout a `units.py`) parce que ce noeud est le SEUL du paquet dont le
predicat traverse toute la cascade de ciblage : il consomme un accesseur de contexte
(`ctx.has_any_valid_target`) que seul `entities_from_state` sait fournir, exactement comme
`ValidNormalAttackTargets` consomme `ctx.valid_normal_attack_targets`.

## DEUX SURCHARGES NATIVES, DEUX CLASSES -- et le port n'en portait qu'UNE

`IdunBattleLogic.Entities.DSLSelectors$$UnitsWithAnyValidTarget` est SURCHARGE, et les deux
surcharges allouent des classes DIFFERENTES (decompile `rnca9r7q6c`) :

    UnitsWithAnyValidTarget(units)            -> IdunBattle.Entities.Selectors.HasAnyValidTargetSelector
    UnitsWithAnyValidTarget(units, ability)   -> IdunBattle.Entities.Selectors.UnitsWithAnyValidTargetSelector

La PREMIERE cable l'attaque normale : son `Select` appelle
`IdunBattle.Entities.UnitExtensions$$GetNormalAttackType(unit)` LUI-MEME.

⚠ **CE PARAGRAPHE DISAIT « DEJA PORTEE », ET C'ETAIT FAUX -- corrige par #1008.** Il renvoyait vers
`runner/abilities/targeting.valid_normal_attack_targets` et le noeud `ValidNormalAttackTargets`
(`selectors/units.py`). Ces deux-la portent bien le PREDICAT, mais pas le SELECTEUR : ils rendent
**les cibles d'UNE unite**, la ou `HasAnyValidTargetSelector` **FILTRE un ENSEMBLE d'unites** sur
« en a-t-elle au moins une ». Les deux domaines sont disjoints -- l'un rend des cibles, l'autre des
attaquants. Le premier consommateur reel
(`IdunBattleLogic.Entities.Abilities.Triggered.Loki.BookOfFateAbility$$CreateBehaviour`, qui
appelle la surcharge a UN argument sur les summons adjacents) n'avait donc AUCUN noeud a monter.
`HasAnyValidTarget` ci-dessous est ce mirror ; il reutilise `ctx.has_any_valid_target`, le MEME
predicat que la seconde surcharge -- aucun 2e port de la cascade.

## `IdunBattle.Entities.Selectors.HasAnyValidTargetSelector$$Select` -- MIRROR du decompile

    result = new List<IEntity>()
    foreach (unit in Select(this.units@+0x20, entities, UnitSelectionType 3)) {
        pos     = EntityExtensions.GetUnitPosition(unit, this.state@+0x10)
        atkType = UnitExtensions.GetNormalAttackType(unit)
        if (this.battleQuery@+0x18.<slot 0x40> HasValidTargets(unit, pos, atkType))
            result.Add(unit)
    }
    return result

DEUX differences LUES avec la surcharge a deux arguments, et elles comptent :
  * l'ability n'est PAS un selecteur : c'est `GetNormalAttackType(unit)`, derive de l'unite courante ;
  * **il n'y a AUCUNE ecriture d'`entities+0x20`** -- le contexte n'est pas mute (rien ne le lit ici).

La SECONDE prend l'ability en PARAMETRE, sous la forme d'un selecteur-de-type evalue PAR UNITE.
C'est celle qu'appelle `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ECogSupportAbility$$
CreateBehaviour`, et c'est elle qui manquait.

## `IdunBattle.Entities.Selectors.UnitsWithAnyValidTargetSelector$$Select` -- MIRROR du decompile

    result = new List<IEntity>()
    foreach (unit in Select(this.units@+0x20, entities, UnitSelectionType 3)) {
        entities.<+0x20> = unit                             # <<< ECRITURE du slot ActiveTarget
        ability = this.abilitySelector@+0x28.Select(entities)   # Nullable<AbilityOrEffect>
        if (ability.HasValue) {
            pos = EntityExtensions.GetUnitPosition(unit, this.state@+0x10)
            if (this.battleQuery@+0x18.<slot 0x40>(unit, pos, ability.Value))   # HasValidTargets
                result.Add(unit)
        }
    }
    return result

TROIS lectures qui ne se devinent pas, et qui sont chacune un mode de panne si on les rate :

1. **L'ECRITURE `entities+0x20 = unit` EST le mecanisme du noeud.** Le selecteur d'ability n'est pas
   evalue une fois : il l'est PAR UNITE, sur un contexte ou l'unite courante a ete POSEE dans le
   slot `activeTarget`. C'est ce qui permet a `ECogSupport` d'y passer
   `UnitNormalRepairType(ActiveTarget@DSLSelectors+0x68)` et d'obtenir le repair-type de CHAQUE
   E-Cog. Evaluer la formule une seule fois, hors boucle, rendrait le repair-type d'une unite
   arbitraire (ou `None`) et le filtre serait constant.
   ⚠ Que `+0x20` soit bien `activeTarget` est TRANCHE, pas suppose :
   `IdunBattle.Entities.Selectors.ActiveTargetSelector$$Select` lit `entities+0x20` (avec repli sur
   `entities+0x10`) et `PreviousActiveTargetSelector$$Select` lit `entities+0x28` -- les deux slots
   voisins, dans l'ordre du ctor a 32 arguments d'`AbilityEntities`.

2. **`ability.HasValue == false` fait SAUTER l'unite**, sans appeler le predicat. Le `Nullable` vide
   n'est donc pas « pas de filtre » : c'est un REJET. Et il est atteignable, parce que
   `IdunBattleLogic.Entities.AbilityTypeSelector.UnitNormalRepairAbilitySelector$$Select` rend
   explicitement un `Nullable` VIDE quand son `SelectSingle` ne resout aucune unite (cf.
   `entities/formulas.py::UnitNormalRepairType`, ou l'asymetrie avec le jumeau ATTACK est lue).

3. **Le `SelectionType 3` (`OnlyAliveAndTargetable`) est passe au `Select` de la SOURCE**, pas
   applique apres coup.

## CE QUE CE NOEUD NE PORTE PAS, ET LE DIT

`ctx.has_any_valid_target` est TRI-ETAT (cf. `runner/abilities/targeting.has_valid_targets`) :
`None` = le masque de ciblage de cette ability n'a pas ete RE-lu. Le noeud ECARTE alors l'unite et
le DECLARE dans `ctx` (`unknown_ability_types`), plutot que de fabriquer un verdict. Sans accesseur
du tout (contexte hors runner : prediction, test de noeud), il rend `[]` -- meme degradation nommee
que `ValidNormalAttackTargets`.
"""
from __future__ import annotations

from dataclasses import replace

from ...dsl.base import TargetsSelector, _units_of
from ..unit_selection_type import UnitSelectionType, selection_ok_from_ctx


class UnitsWithAnyValidTarget(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLSelectors$$UnitsWithAnyValidTarget(units, ability)` ->
    `IdunBattle.Entities.Selectors.UnitsWithAnyValidTargetSelector$$Select` (surcharge a TROIS
    arguments : `this, units, ability`). Arbre natif et pieges : en-tete du module.

    `ability_sel` = le selecteur-de-type natif (`+0x28`), evalue PAR UNITE avec l'unite courante
    posee en `ActiveTarget`. Cote port, tout noeud VALEUR fait l'affaire (`UnitNormalRepairType`
    est le seul call-site lu) : on appelle son `evaluate(ctx)` sur le contexte MUTE.

    `selection_type` = le 3e argument du `Select` de la source (`3 = OnlyAliveAndTargetable` au
    call-site lu)."""
    def __init__(self, source: TargetsSelector, ability_sel,
                 selection_type: int = int(UnitSelectionType.OnlyAliveAndTargetable)):
        self.source, self.ability_sel = source, ability_sel
        self.selection_type = int(selection_type)

    def select(self, ctx):
        probe = getattr(ctx, "has_any_valid_target", None)
        if probe is None:
            # Contexte hors runner : la cascade de ciblage n'est pas evaluable sans `State`.
            # Degradation NOMMEE (meme regime que `ValidNormalAttackTargets`), jamais un filtre
            # invente.
            return []
        out = []
        for u in _units_of(self.source, ctx):
            if not isinstance(u, dict):
                continue
            # `Select(this.units, entities, 3)` -- le filtre est passe a la SOURCE, cf. en-tete.
            if not selection_ok_from_ctx(u, self.selection_type, ctx):
                continue
            # `entities.<+0x20> = unit` : l'unite courante devient l'`ActiveTarget` du contexte, et
            # c'est CE contexte-la que le selecteur d'ability lit.
            sub = replace(ctx, active_target=u)
            ability = self.ability_sel.evaluate(sub)
            if ability is None:              # `if (ability.HasValue)` -- Nullable VIDE => rejet
                continue
            verdict = probe(u, int(ability))
            if verdict is None:              # masque non RE-lu -> on ECARTE et on le DIT
                _declare_unknown(ctx, int(ability))
                continue
            if verdict:
                out.append(u)
        return out


class HasAnyValidTarget(TargetsSelector):
    """`IdunBattleLogic.Entities.DSLSelectors$$UnitsWithAnyValidTarget(units)` (surcharge a UN
    argument) -> `IdunBattle.Entities.Selectors.HasAnyValidTargetSelector$$Select`. Arbre natif et
    ecarts avec la surcharge a deux arguments : en-tete du module.

    Garde les unites de `source` qui ont AU MOINS une cible legale a leur ATTAQUE NORMALE, depuis
    leur position COURANTE. L'ability testee est `GetNormalAttackType(unit)` -- derivee de CHAQUE
    unite, jamais un selecteur ; le contexte n'est PAS mute (pas d'`ActiveTarget`).

    Les deux accesseurs sont TRI-ETAT et le noeud le respecte :
      * `ctx.normal_attack_type(unit)` -> `None` = l'unite n'a pas d'attaque normale resoluble : le
        natif passerait cette valeur au predicat, qui ne peut pas rendre vrai -> on ECARTE ;
      * `ctx.has_any_valid_target(unit, atk)` -> `None` = masque non RE-lu : on ECARTE **et on le
        DECLARE** (`unknown_ability_types`), meme canal d'honnetete que `UnitsWithAnyValidTarget`.
    Sans accesseur du tout (contexte hors runner), le noeud rend `[]` -- degradation NOMMEE."""
    def __init__(self, source: TargetsSelector,
                 selection_type: int = int(UnitSelectionType.OnlyAliveAndTargetable)):
        self.source = source
        self.selection_type = int(selection_type)

    def select(self, ctx):
        probe = getattr(ctx, "has_any_valid_target", None)
        attack_type = getattr(ctx, "normal_attack_type", None)
        if probe is None or attack_type is None:
            return []                     # contexte hors runner -- meme degradation que le jumeau
        out = []
        for u in _units_of(self.source, ctx):
            if not isinstance(u, dict):
                continue
            # `Select(this.units, entities, 3)` -- le filtre est passe a la SOURCE, comme le jumeau.
            if not selection_ok_from_ctx(u, self.selection_type, ctx):
                continue
            atk = attack_type(u)          # `UnitExtensions.GetNormalAttackType(unit)`
            if atk is None:
                continue
            verdict = probe(u, int(atk))
            if verdict is None:           # masque non RE-lu -> on ECARTE et on le DIT
                _declare_unknown(ctx, int(atk))
                continue
            if verdict:
                out.append(u)
        return out


def _declare_unknown(ctx, ability_type: int) -> None:
    """Enregistre dans le contexte qu'une ability a ete ECARTEE faute de masque RE-lu.

    Ce n'est pas du natif : c'est le canal d'HONNETETE du noeud. Sans lui, une unite exclue parce
    que le port ne sait pas lire son masque serait indiscernable d'une unite que le natif exclut
    -- exactement le zero muet que la doctrine interdit. Le conteneur est cree paresseusement et
    reste vide dans le cas nominal."""
    seen = getattr(ctx, "unknown_ability_types", None)
    if seen is None:
        return
    seen.add(int(ability_type))
