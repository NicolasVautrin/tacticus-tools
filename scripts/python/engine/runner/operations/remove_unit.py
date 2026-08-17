"""Retrait d'unite du plateau -- `IdunBattle.Operations.RemoveUnitOperation$$Execute` (mutateur ECS
IMPERATIF). **Un DESPAWN, PAS une mort** : aucun vecteur on-death, aucune attribution de tueur,
les PV ne sont pas touches et le flag `Dead (6)` n'est PAS pose.

Frontiere DSL (#149) : la feuille `IdunBattleLogic.Entities.DSLBehaviors$$RemoveUnit` (au-dessus,
structurelle) APPELLE cette Operation (en-dessous, imperative). Chaine native complete :

    IdunBattleLogic.Entities.DSLBehaviors$$RemoveUnit(sel)
      -> IdunBattle.Entities.Behaviours.RemoveUnitBehaviour$$Execute
           resout le selecteur `+0x50` (groupType 3), puis PAR UNITE :
           slot +6 de l'interface `Core.Services.OperationProcessor` avec `(unitId, 1, 0)`
      -> Core.Services.OperationProcessor$$RemoveUnit           (gate `this+0x1f0 != 0`)
      -> IdunBattle.Operations.RemoveUnitOperation$$Execute(state, entity, removeEffects=1, param4=0)

QUATRE APPELANTS DU SLOT 6, PAS UN -- ET LE PLUS IMPORTANT EST LA MORT (#10015-r3)
---------------------------------------------------------------------------------
Le residu `#10015-r2` affirmait que << la CHAINE NATIVE qui retire du plateau une unite TUEE n'est
pas identifiee >> et que `IdunBattle.Operations.KillUnitOperation$$Execute` << n'appelle **jamais**
`IOperationProcessor` slot 6 = `RemoveUnit` >>, ses appels sur cette interface etant << les slots
77, 80, 85, 99, 130, 143 >>. **C'EST FAUX**, et la mesure qui le montre coute une requete :

    recherche LITTERALE `DAT_18336edb0,6)` sur tout le pseudo-C  ->  3 fonctions
        IdunBattle.Operations.KillUnitOperation$$Execute
        IdunBattle.Entities.Behaviours.RemoveUnitBehaviour$$Execute
        IdunBattle.Messages.InputMessageProcessor$$Visit
    recherche LITTERALE `(6,DAT_18336edb0`               ->  1 fonction
        IdunBattle.Operations.FleeOperation$$Execute

⚠ **CE QUI A FAIT MANQUER `KillUnitOperation`, ET C'EST LA LECON REUTILISABLE** : un appel
d'interface IL2CPP a DEUX formes dans le pseudo-C, et un recensement d'UNE seule forme rend un zero
qui se lit comme une absence.
  * forme DISPATCHER -- `FUN_<x>(<slot>, <iface>, <obj>, ...)`, le slot en PREMIER argument. C'est
    elle que le recensement precedent a balayee, et c'est d'elle que sortent << 77, 80, 85, ... >> ;
  * forme WALK D'ITABLE INLINE -- le decompile deroule la recherche de l'interface dans l'itable
    (`while (itable[i] != <iface>) ...`), calcule le slot en INLINE (`(base + 6) * 0x10 + 0x138`),
    et n'appelle `FUN_1801e72b0(<obj>, <iface>, <slot>)` qu'en REPLI, le slot en TROISIEME argument.
    Le call-site final est un `(*pcVar2)(...)` anonyme. **Aucun** filtre sur le premier argument ne
    peut le voir.
`KillUnitOperation$$Execute` utilise la SECONDE forme, et `FleeOperation` les deux (la premiere pour
son `RemoveUnit`, la seconde pour son `EvaluateAbilities`) -- donc le binaire fournit lui-meme le
contre-exemple qui invalide le recensement.

⚠ **LE DEPOT PORTAIT DEJA LES DEUX AFFIRMATIONS, CONTRADICTOIRES** : `runner/components.py` ecrit
<< `KillUnitOperation$$Execute` n'appelle **jamais** [le] slot 6 >> tandis que
`runner/operations/damage.py` ecrit, a l'endroit exact, << Le natif intercale entre eux le retrait
de l'unite du plateau (`processor.<slot 6>` + `matchState.<slot 0x31>`) >>. La seconde est la bonne.

ORDRE DANS `KillUnitOperation$$Execute`, offsets MESURES (adresses de retour des call-sites) --
le retrait s'insere entre les deux premiers `RemoveEffects`, exactement ou `damage.py` l'annonce :

    +0x7dc   On(1  = PreUnitDeath)                       <- AVANT la garde revive
    +0x81c   garde  if (!unitComponent.PendingRevive.HasValue)
    +0x828   unitComponent.KilledThisTurn@+0x17a = 1
    +0x8b9   RegisterDefeatedUnit
    +0x97a   On(2  = PreUnitDeath_2)
    +0x9be   KillUnitOperation$$RemoveEffects(killed, PreUnitRemove)
    +0xd34   >>> IOperationProcessor slot 6 = RemoveUnit(killed, removeEffects: 0, keepActive: 1)
    +0xd88   MatchState slot 0x31
    +0xd9c   KillUnitOperation$$RemoveEffects(killed, AfterUnitRemove)
    +0xdf9   On(0  = UnitDeath)
    +0xeac   On(54 = UnitDefeated)
    +0xf35   garde HEAL (return si hp > 0)
    +0xf59   KillUnitOperation$$RemoveEffects(killed, AfterDeathTrigger)
    +0x10ac  On(53 = PostUnitKill)

Le `+0xd34` est DANS la branche non-revive : profondeur d'accolades du pseudo-C **jamais inferieure
a 9** entre le `+0x17a = 1` (premiere instruction de cette branche) et l'appel -- meme methode que
celle qui avait tranche la semantique de la garde.

CONSEQUENCES, et elles depassent `turn_defeated` :
  a. une unite TUEE (sans revive en attente) TRAVERSE bien cet ecrivain -- `TurnDefeated@+0x17c`
     est donc ecrit par la MORT, et `EnvAmbushResurrect` n'est pas structurellement mort ;
  b. `keepActive: 1` SAUTE l'etape 11 et `removeEffects: 0` SAUTE l'etape 14 -- sur la voie MORT,
     ce foyer ne consomme donc AUCUN effet (c'est `KillUnitOperation$$RemoveEffects` qui s'en
     charge, en trois temps, autour de lui) ;
  c. **`On(0x25 = UnitRemoved)` (etape 13) EST PUBLIE A CHAQUE MORT effective.** Il ne l'est pas
     cote port, et c'est un vecteur ENTIER manquant pour ses six consommateurs
     (`bond_removal`, `armour_of_shrieking_souls`, `ghost_revive`, `lions_wrath_attack`,
     `instruments_of_vengeance_attack`, `pending_attack`).

⚠ **CONFIRMATION CROISEE, independante du decompile de `KillUnitOperation`** : le trigger natif
d'`ArmourOfShriekingSoulsResurrectOnRemoved` est `On(0x25 = UnitRemoved) & get_OwnerIsTarget &
IsDead(Owner@+0x30)`. Le conjoint `IsDead` n'aurait AUCUN regime ou etre vrai si `On(0x25)` ne
partait que sur des retraits d'unites vivantes -- le trigger serait mort-ne. Sa seule existence
etablit que le retrait s'applique aux morts.

SEQUENCE de `RemoveUnitOperation$$Execute`, LUE au decompile (`operationCtx+0x10` = `MatchState`,
`+0x18` = journal d'events de match, `+0x20` = logger, `+0x28` = `OperationProcessor`) :

  1. `entity == 0`                                     -> log d'erreur, RETURN (aucune mutation)
  2. `IdunBattle.Entities.EntityExtensions$$IsUnit`    -> faux : log d'erreur, RETURN
  3. **GATE** `IdunBattle.Entities.UnitExtensions$$HasFlag(entity, 0x1a)` vrai -> log, RETURN
     (`0x1a = 26 = UnitFlag.Removed`, dump d'enums -- anti-double-retrait)
  4. gate d'appartenance : `MatchState` slot 0x2f -> collection, slot 4 `(entity)` -> bool ;
     faux : log d'erreur, RETURN
  5. log << removing unit >>
  6. `OperationProcessor` slot 7 `(entity, false)`
  7. `PlayerComponent` du proprietaire (`MatchState` slot 0x29) :
     `List.Remove(unitId)` sur `+0x30` (units) puis `List.Add(unitId)` sur `+0x38` (unites RETIREES)
  8. `MatchState` slot 0x32 `(entity, options)` -- retrait des TUILES
  9. `IdunBattle.Entities.Components.UnitFlagsComponent$$Add(entity, 0x1a)` -- pose `Removed`
 10. sur le `BaseUnitComponent` : `+0x17c = TurnComponent$$GetAmountOfTurnsStartedByPlayer(...)`,
     `+0x180 = 1` (tour de retrait + booleen)
 11. si `param4 == 0` : `OperationProcessor` slot 0x55 `(entity, false)`
 12. event de MATCH : journal slot 2, type `0xc`, payload
     `{0x88: HasFlag(entity, 6=Dead), 0x89: HasFlag(entity, 8=Overkilled)}`
 13. **PUBLICATION `On(0x25 = 37 = UnitRemoved)`** : `OperationProcessor` slot 0x51 avec
     `(a = entity, b = entity, c = entity, eventType = 0x25, options)`
     -> **actor = caster = target = l'unite retiree**
 14. si `removeEffects != 0` : bloc INLINE identique a
     `IdunBattle.Operations.RemoveUnitOperation$$RemoveEffects` (`OperationProcessor` slot 0x5a)
 15. `OperationProcessor` slot 0x2f avec `{5, 0}` (meme appel de cloture qu'en fin de
     `IdunBattle.Operations.ResurrectUnitOperation$$Execute` -- non porte, comme la-bas)

ORDRE LOAD-BEARING : l'event `On(0x25)` part **APRES** la pose du flag `Removed` et le retrait des
tuiles, mais **AVANT** la consommation des effets portes (etape 14). Un port qui consommerait les
effets d'abord rendrait invisible, aux consommateurs de `On(0x25)`, tout effet porte par l'unite
retiree. Les deux sites de despawn du port faisaient exactement cela (et n'emettaient rien).

COLLAPSES ET RESIDUS NOMMES du port :
  * etape 8 (retrait des tuiles) -> `UnitComponent.alive = False`. C'est ce que les deux sites de
    despawn du port faisaient deja, et c'est ce qui LIBERE l'occupation (`_occupied` / `CanAddUnit`
    excluent les non-`alive`) -- indispensable au spawn qui suit l'eviction MV71. L'ecart avec le
    natif (qui ne touche NI les PV NI le flag `Dead`) est donc assume et INCHANGE par ce foyer ;
    la donnee fidele qui manquait est le flag `Removed`, desormais pose.
  * etapes 7 et 12 : ni `PlayerComponent.units`/`removedUnits` ni l'event de match ne sont portes --
    aucun consommateur porte ne les lit (cf. `playbook/noncomparable/doctrina_imperatives.py`, qui
    documente deja la liste `+0x30`).
  * etape 10 : **PORTEE depuis #462-r4b-r1-r1-r1-r1-b-r1-r1-r3-r1-r3-r1**. La justification d'avant
    (<< aucun consommateur porte ne la lit >>) etait FAUSSE : `triggers/genestealer.py::
    _eligible_for_resurrect` LIT `uc.turn_defeated` pour le gate
    `AmountIsEqual(Difference(CurrentPlayerTurnsStarted, TurnDefeated(u)), 1)` d'`EnvAmbushResurrect`.
    Et ce foyer-ci est le SEUL ecrivain natif du champ : balayage a l'ENCODAGE des deux sections de
    code (`disp32 == 0x17c`, ModRM `mod=10`) -> 66 ecritures dans tout le binaire, dont **3** sur un
    `UnitComponent` : `$$.ctor+0x133` (init a `-1`), `$$Copy+0x582` (recopie) et
    `$$Execute+0x4f6` (ici). Le `+0x180 = 1` qui suit n'a aucun lecteur identifie -> non porte.
    ⚠ **Le port garde `None` la ou le natif a `-1`**, et c'est voulu : `None` = NON MESURE (tri-etat),
    donc `_eligible_for_resurrect` refuse explicitement au lieu de comparer contre une sentinelle ;
    les deux rendent le meme verdict (`cur - (-1) == 1` exige `cur == 0`, jamais atteint).
  * etapes 6, 11, 15 : slots `OperationProcessor` non identifies, non portes (aucune autre Operation
    portee ne les porte non plus).
  * `IdunBattle.Operations.ResurrectUnitOperation$$Execute` retire le flag (`Remove(0x1a)`, avec
    6/0xf/8/9) -- porte dans `resurrect.py`, ce qui referme le cycle pose/retrait.
"""
from __future__ import annotations

from typing import Optional

from ..state import State
from ..components import OwnerComponent, UnitComponent, UnitFlagsComponent


class RemoveUnitOperation:
    """Mirror `IdunBattle.Operations.RemoveUnitOperation$$Execute`.

    `remove_effects` = le `param_3` natif (`RemoveUnitBehaviour$$Execute` passe **1** a son unique
    call-site ; `KillUnitOperation$$Execute` passe **0**). Rend `None` quand un gate refuse (entite
    inconnue, pas une unite, deja retiree) -- aucune mutation, aucun event ; sinon un dict de trace.

    `allow_already_dead` = le call-site MORT, et c'est un ECART NOMME, pas une commodite. Le natif
    ne gate QUE sur `HasFlag(0x1a = Removed)` et l'appartenance au plateau -- jamais sur la VIE.
    Cote port, `alive` porte DEUX sens fondus (vivante, et sur le plateau) parce que l'etape 8 est
    collapsee dessus ; sur la voie MORT, `alive` est deja `False` quand `KillUnitOperation` atteint
    le slot 6, si bien que le gate ci-dessous refuserait le retrait que le natif effectue. Le
    drapeau leve donc EXACTEMENT ce que le collapse a introduit, et rien d'autre : les trois gates
    natifs (entite, `IsUnit`, `Removed`) restent en place.
    """
    __slots__ = ()

    @staticmethod
    def execute(state: State, unit_id: Optional[int], *,
                remove_effects: bool = True,
                allow_already_dead: bool = False) -> Optional[dict]:
        if unit_id is None:                                    # 1. entity == 0
            return None
        e = state.get_entity(int(unit_id))
        if e is None:                                          # 4. gate d'appartenance (collapse)
            return None
        uc = e.get_component(UnitComponent)
        if uc is None:                                         # 2. `EntityExtensions$$IsUnit`
            return None
        fl = e.get_component(UnitFlagsComponent)
        if fl is None:
            fl = e.add_component(UnitFlagsComponent())
        if fl.has(UnitFlagsComponent.REMOVED):                 # 3. GATE anti-double-retrait
            return None
        if not uc.alive and not allow_already_dead:
            # Corollaire du collapse etape 8 : une unite deja hors-plateau cote port (retiree par un
            # site qui ne posait pas encore le flag) n'est pas re-retiree. La voie MORT, elle, DOIT
            # passer -- cf. `allow_already_dead` dans la docstring.
            return None
        uc.alive = False                                       # 8. retrait des TUILES (collapse)
        fl.add(UnitFlagsComponent.REMOVED)                     # 9. `UnitFlagsComponent.Add(0x1a)`
        # 10. `uc->[0x17c] = TurnComponent$$GetAmountOfTurnsStartedByPlayer(GetMatchTurn(state),
        #     ownerPlayerId)` -- le compteur de tours du joueur PROPRIETAIRE au moment du retrait.
        #     ORDRE natif : APRES la pose du flag `Removed`, AVANT l'`On(0x25)` ci-dessous.
        #     Le repli `0` est FIDELE, pas defensif : `TurnComponent$$GetAmountOfTurnsStartedByPlayer`
        #     ouvre sur `if (!dict.ContainsKey(playerId)) return 0`. Un `State` dont `turn_counts`
        #     est vide rend donc la MEME valeur que le natif sur un joueur inconnu.
        oc = e.get_component(OwnerComponent)
        if oc is not None and oc.player is not None:
            uc.turn_defeated = state.turn_counts.get(int(oc.player), 0)
        # 13. `On(UnitRemoved = 0x25)` -- AVANT la consommation des effets (etape 14).
        from .triggers.dispatch.move_death import unit_removed_triggers
        downstream = unit_removed_triggers(state, int(unit_id))
        consumed = []
        if remove_effects and state.effects is not None:       # 14. `RemoveUnitOperation$$RemoveEffects`
            for eff in state.effects.by_unit.get(int(unit_id), []):
                if not eff.consumed:
                    eff.consumed = True
                    consumed.append(int(eff.effect_type))
        return {"removed": int(unit_id), "effects_consumed": consumed, "downstream": downstream}
