"""`UnitSelectionType` -- le filtre que TOUT selecteur d'unite applique a sa sortie
(`IdunBattle.Entities.Enum.UnitSelectionType`).

C'est le 2e argument d'`IdunBattle.DSL.TargetsSelector$$SelectUnit` / `$$Select`, et le 3e de
`IdunBattleLogic.Entities.DSLTriggers$$IsAdjacent` / `DSLSelectors$$Enemies` / ... Le foyer qui le
consomme est `IdunBattle.Entities.UnitExtensions$$MatchesUnitSelectionType(unit, selectionType,
state)`, MIRROR de son decompile (build `rnca9r7q6c`) :

    if (unit == null)                       return false;
    if (!EntityExtensions.IsUnit(unit))     return false;
    if (selectionType == 1)                 return UnitExtensions.IsAlive(unit, state);
    if (selectionType == 2)                 return !UnitExtensions.HasFlag(unit, 0x11);
    if (selectionType == 3)                 return UnitExtensions.IsAlive(unit, state)
                                                   && !UnitExtensions.HasFlag(unit, 0x11);
    return true;                            // 0 = Any

`0x11` = `UnitFlag.Untargetable` (17) -- cf. `engine/entities/unit_flag.py`.

⚠ NE PAS LE CONFONDRE avec les autres << selection types >> du build : c'est CE type-la qui est
declare au 3e parametre d'`IsAdjacent` et au 2e de `SelectUnit`, et il n'a que QUATRE membres.

Le mirror entre au registre de `probe_313_enum_mirror_bijection.py` DANS LE COMMIT QUI LE CREE
(#524) -- cle LUE dans `data/symbols/<CURRENT>/frida/enums.tsv`.
"""
from __future__ import annotations

from enum import IntEnum

# Feuille pure (`enum` seul) : l'importer ici n'allonge la cascade d'AUCUN module `engine.*` --
# mesure : `import engine.entities.unit_selection_type` en charge 3 avec, 3 sans. C'est ce qui
# permet au DERIVATEUR ci-dessous de vivre au meme endroit que l'enum qu'il sert (#433-r3-r2).
from .unit_flag import UnitFlag


class UnitSelectionType(IntEnum):
    """`IdunBattle.Entities.Enum.UnitSelectionType` -- VERBATIM du build (4 valeurs).

    Re-derivable : `data/symbols/<CURRENT>/frida/enums.tsv`, cle
    `IdunBattle.Entities.Enum.UnitSelectionType`."""

    Any = 0
    OnlyAlive = 1
    OnlyTargetable = 2
    OnlyAliveAndTargetable = 3


def matches_unit_selection_type(selection_type, *, is_unit: bool | None = True,
                                alive: bool | None = None,
                                targetable: bool | None = None) -> bool:
    """FOYER du mirror d'`IdunBattle.Entities.UnitExtensions$$MatchesUnitSelectionType`, decompile
    relu en entier sur `rnca9r7q6c` (#419-r1-tr10-r4) :

        if (unit == null)                    return false;
        if (!<IsUnit>(unit))                 return false;
        if (selectionType == OnlyAlive)               return IsAlive(unit, state);
        if (selectionType == OnlyTargetable)          return !HasFlag(unit, UnitFlag.Untargetable);
        if (selectionType == OnlyAliveAndTargetable)  return IsAlive(unit, state)
                                                             && !HasFlag(unit, Untargetable);
        return true;                                  // Any -- et TOUTE autre valeur

    ⚠ La branche par defaut est `true`, pas `false` : une valeur hors des quatre membres passe le
    filtre. C'est ce que fait le `switch` natif (les trois tests sont des comparaisons successives,
    et le chemin qui n'en satisfait aucune saute au `return true`). Ne pas la durcir.

    TRI-ETAT sur les deux predicats -- `None` = **PAS MESURE**, jamais rabattu sur un booleen :
    la clause correspondante DEGRADE EN VRAI. Un `False` invente ecarterait une unite que le natif
    compte (degradation RESTRICTIVE silencieuse), et c'est exactement la faute que la convention
    `turns_started` / `turns_finished` de `playbook/scene.py` nomme. C'est ce qui rend ce foyer
    utilisable AVANT que le canal `Untargetable` existe partout : il se comporte alors comme le port
    d'avant (volet `IsAlive` seul), sans mentir sur ce qu'il n'a pas lu.

    `is_unit` : mirror du `<IsUnit>(unit)` qui precede le switch. Les appelants qui itere DEJA une
    liste d'unites (tout `scene.units`) passent le defaut `True` -- ce n'est pas un raccourci, c'est
    que leur substrat ne contient que des unites."""
    if is_unit is False:
        return False
    st = int(selection_type)
    if st == int(UnitSelectionType.OnlyAlive):
        return alive is not False
    if st == int(UnitSelectionType.OnlyTargetable):
        return targetable is not False
    if st == int(UnitSelectionType.OnlyAliveAndTargetable):
        return alive is not False and targetable is not False
    return True                                       # `Any`, et toute valeur hors enum


def selection_type_from_only_alive(only_alive) -> UnitSelectionType:
    """La SURCHARGE BOOLEENNE des factories `DSLSelectors` n'est pas un autre axe -- c'est un SUCRE
    sur `selectionType`, et le corps le dit litteralement (#585-r1, build `rnca9r7q6c`) :

        IdunBattleLogic.Entities.DSLSelectors$$Enemies(this, of, entities, onlyAlive)
            -> Enemies(this, of, entities, (onlyAlive & 0xff) + 2)
        IdunBattleLogic.Entities.DSLSelectors$$Units(this, entities, unique, onlyAlive)
            -> UnitsOnTilesSelector..ctor(..., unique, (onlyAlive & 0xff) + 2)

    Soit `false -> 2` (`OnlyTargetable`) et `true -> 3` (`OnlyAliveAndTargetable`).

    ⚠ CONSEQUENCE, et c'est elle qui compte : **la surcharge booleenne ne peut JAMAIS produire
    `Any` (0) ni `OnlyAlive` (1)**. Tout call-site natif qui l'emprunte filtre donc au MINIMUM
    `UnitFlag.Untargetable`. Un port qui n'arme aucun filtre y est strictement plus permissif que
    le plancher natif -- exactement l'ecart mesure par #585 (une unite en deep strike retenue a
    tort). Et pour le releve des ~100 call-sites, un `bool` litteral au natif se DERIVE ici sans
    ambiguite, au lieu d'exiger un arbitrage entre quatre valeurs.

    ⚠ Ne PAS s'en servir pour deviner : il faut avoir LU que le call-site emprunte bien la surcharge
    booleenne. Les deux surcharges portent le meme nom et la meme arite -- seul le corps les separe
    (celle a `selectionType` alloue le selecteur, celle a `onlyAlive` se re-appelle avec `+2`)."""
    return (UnitSelectionType.OnlyAliveAndTargetable if bool(only_alive)
            else UnitSelectionType.OnlyTargetable)


def _untargetable_effect_types():
    """Le domaine `UNTARGETABLE_EFFECT_TYPES`, importe DIFFERE et memoise.

    ⚠ DIFFERE **PORTEUR**, et le classement est MESURE (protocole du CLAUDE.md : charger la cible
    seule dans un process frais et regarder si le module courant y atterrit) : charger
    `engine.entities.effects.aura_selectors` charge `engine.entities.unit_selection_type` --
    hisser l'import fermerait donc un cycle. S'y ajoute le COUT : `aura_selectors` tire **108**
    modules `engine.*`, la ou cette feuille en tire **3**. L'y hisser detruirait exactement ce qui
    permet aux deux consommateurs (`selectors/units.py` et `entities/triggers.py`) de partager ce
    foyer sans arete.
    """
    global _UNTARGETABLE
    if _UNTARGETABLE is None:
        from .effects.aura_selectors import UNTARGETABLE_EFFECT_TYPES
        _UNTARGETABLE = tuple(UNTARGETABLE_EFFECT_TYPES)
    return _UNTARGETABLE


_UNTARGETABLE = None


def selection_ok_from_ctx(unit, selection_type, ctx) -> bool:
    """DERIVATEUR unique des deux predicats de `matches_unit_selection_type` depuis un `DslContext`.

    Mirror de `IdunBattle.DSL.TargetsSelector$$SelectUnit(entity, selectionType)` cote RUNNER : le
    substrat y est l'ECS -- `alive`/`hp` du dict d'unite pour `IsAlive`, et DEUX canaux pour
    `UnitFlag.Untargetable` (`0x11`).

    ⚠ CE FOYER EST HISSE ICI (#433-r3-r2), et ce n'est pas une commodite. Il vivait dans
    `selectors/units.py::_selection_ok`, qui declarait deja << un SECOND port du predicat aurait ete
    un fork >> ; le noeud `entities/triggers.py::IsAdjacent` en avait pourtant ecrit un TROISIEME --
    un filtre `IsAlive` a la main, aveugle au volet `Untargetable`.

    ⚠ **`ctx.has_unit_flag` N'EST PLUS INERTE (#433-r3-r2-r1), et la description qui vivait ici
    n'etait pas seulement perimee -- elle etait INCOMPLETE.** Deux corrections :

    (1) Le port INSCRIT desormais `0x11` : `AddEffectOperation._apply_untargetable_flag` (mirror
        `UntargetableEffect$$ApplyInternal`) et `remove_effects.remove_effect_instance` (mirror
        `$$RevertInternal`). Le canal DIRECT repond donc pour de vrai sur le domaine
        `UNTARGETABLE_EFFECT_TYPES`.

    (2) **`UntargetableEffect` n'est PAS le seul poseur du flag cote natif** (#433-r3-r2-r1-r1), et
        la phrase precedente laissait croire le contraire -- donc qu'un domaine d'`EffectType`
        pouvait couvrir TOUTE la non-ciblabilite. Mesure exhaustive sur `t6dpr4k06g` (tous les
        `call` ET `jmp` rel32 vers `UnitFlagsComponent$$Add`/`$$Remove` a immediat `edx == 0x11`) :
        **TROIS poseurs et TROIS retireurs**. Outre l'effet, ce sont
        `IdunBattle.Operations.ResurrectUnitOperation$$Execute` et
        `IdunBattle.Operations.AddUnitOperation$$Execute`, qui encadrent chacune leur propre corps
        d'un `Add(0x11)` ... `Remove(0x11)` -- fenetre TRANSITOIRE intra-operation, HORS de tout
        effet, donc invisible de `has_effect`. Les deux sont desormais PORTEES
        (`operations/resurrect.py`, `operations/spawn.py`), et c'est le canal FLAG qui les rend
        visibles ici : le canal EFFET, lui, ne les verra jamais.

    Les deux canaux sont lus, dans cet ordre :

      1. `ctx.has_unit_flag(unit, Untargetable)` -- le canal DIRECT, et le SEUL qui voie les
         fenetres de resurrection et de spawn ;
      2. `ctx.has_effect(unit, <type>)` sur `UNTARGETABLE_EFFECT_TYPES` -- le canal EFFET, le MEME
         que lit `playbook/adjacency.py::is_targetable` cote DECISION.
      Ils ne sont donc PAS redondants, et la disjonction n'est pas une ceinture-bretelles : chacun
      voit ce que l'autre ne peut pas voir. Le seul regime ou ils DIVERGENT en sens inverse est le
      MULTI-EFFETS simultane -- `$$RevertInternal` retire le flag NU, sans comptage de references,
      donc le natif redevient ciblable alors qu'un second effet du domaine vit encore, et le canal
      EFFET dit le contraire. Le OU choisit alors le canal EFFET. Residu `#433-r5`.

    TRI-ETAT preserve : AUCUN des deux canaux branche -> `targetable = None` = **PAS MESURE**, et
    `matches_unit_selection_type` degrade alors la clause en VRAI. Un `False` invente ecarterait une
    unite que le natif compte -- degradation RESTRICTIVE silencieuse.
    """
    if not isinstance(unit, dict):
        return False                                  # `!EntityExtensions.IsUnit(unit)`
    hf = getattr(ctx, "has_unit_flag", None)
    he = getattr(ctx, "has_effect", None)
    untargetable = None
    if hf is not None:
        untargetable = True if bool(hf(unit, int(UnitFlag.Untargetable))) else False
    if not untargetable and he is not None:
        # OU logique : le flag et le domaine d'effets decrivent la MEME chose cote natif (l'un est
        # pose PAR l'autre), donc un seul canal qui l'affirme suffit.
        if any(bool(he(unit, int(t))) for t in _untargetable_effect_types()):
            untargetable = True
    targetable = None if untargetable is None else (not untargetable)
    alive = bool(unit.get("alive", True)) and (unit.get("hp") or 0) > 0
    return matches_unit_selection_type(selection_type, alive=alive, targetable=targetable)


__all__ = ["UnitSelectionType", "matches_unit_selection_type", "selection_type_from_only_alive",
           "selection_ok_from_ctx"]
