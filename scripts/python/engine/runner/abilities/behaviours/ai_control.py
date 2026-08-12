"""Feuilles DSL de la famille AI-CONTROL — faire AGIR une ou plusieurs unites TIERCES.

Namespace natif `IdunBattle.Entities.Behaviours`. Wrappers MINCES au-dessus des Operations portees
(la frontiere DSL/imperatif = leur `.execute`). cf. docs/rl/dsl-effect-nodes.md.

  * `PerformAIAction` (`PerformAIActionBehaviour`) -> `operations/summon_ai.py::ComputerActionOperation` :
    un TOUR d'IA complet, l'ability est choisie par l'IA.
  * `PerformAIAbility` (`PerformAIAbilityUnitBehaviour`, surcharge a 6 arguments) -> le corps porte
    `loki/summon.py::perform_ai_ability_unit_behaviour` : UNE ability IMPOSEE, avec budget de
    deplacement et utilite personnalisee. Ajoutee par #590.

⚠ **`PerformAIAbility` et `PerformAIAttack` (`summon.py`) INSTANCIENT LA MEME CLASSE NATIVE.** Le
binaire porte trois noeuds `DSLBehaviors`/`DSLFactory` qui allouent un
`IdunBattle.Entities.Behaviours.PerformAIAbilityUnitBehaviour` :
`PerformAIAttackFromCurrentPosition`, `PerformAIAttack` (tous deux dans `summon.py`) et
`IdunBattleLogic.Entities.DSLBehaviors$$PerformAIAbility` -- ce dernier etant le SEUL a remplir les
champs `+0x68 getAbilityType`, `+0x78 overrideMovement`, `+0x80 utilityEntity` et
`+0x90 customUtility` autrement que par des constantes. Le CORPS reste unique
(`perform_ai_ability_unit_behaviour`), conformement au de-fork de #338 : cette feuille-ci ne fait
qu'apporter les quatre parametres que les deux autres noeuds n'exposent pas.
"""
from __future__ import annotations

from typing import Optional

import inspect

from ....dsl.base import AAmountFormula, TargetsSelector, resolve_unit
from ....dsl.effects import AbilityBehaviour, OperationResult
from ...operations.summon_ai import ComputerActionOperation
# FORME B (`import <module>` puis `<module>.<nom>`) -- `ComputerMovementActionOperation` etait
# DIFFERE dans `PerformAIMovement.execute` alors que la ligne au-dessus charge DEJA le meme module :
# ni cycle possible (l'arete existe au niveau module), ni cout. Hisser en forme A (l'ajouter a
# l'import ci-dessus) gelerait la liaison et DESARMERAIT tout `monkeypatch.setattr` futur sur ce nom
# -- mesure `migrate_485r1_barils_reexport.py morsure` : AUCUN patcheur aujourd'hui, et c'est
# precisement pourquoi la forme qui n'en interdit pas est la bonne.
from ...operations import summon_ai


class PerformAIAction(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLBehaviors$$PerformAIAction(selector, asGroup, resetTurnFlags)` ->
    `PerformAIActionBehaviour` (IdunBattle.Entities.Behaviours.PerformAIActionBehaviour$$.ctor : selector@+0x50, asGroup@+0x58, resetTurnFlags@+0x59)
    -> `IdunBattle.Entities.Behaviours.PerformAIActionBehaviour$$Execute` (MIRROR 1:1) :

        units = selector.Select(entities)                       # iface TargetsSelector slot 4
        if (!asGroup)  foreach (u in units) proc.ComputerAction(u, resetTurnFlags)    # iface slot 0x34
        else                                proc.ComputerAction(units, resetTurnFlags) # iface slot 0x35

    `Core.Services.OperationProcessor$$ComputerAction (mono) / Core.Services.OperationProcessor$$ComputerAction (groupe) ->
    `IdunBattle.Operations.ComputerActionOperation$$Execute / IdunBattle.Operations.ComputerActionOperation$$Execute.

    Les deux booleens (LUS du decompile, pas devines) :
      • `asGroup` (+0x58) : FAUX -> une action AI **par unite, sequentielle et independante**
        (`IdunBattle.Core.Services.AiControl$$ExecuteFor(unit), une seule passe de decision par unite) ;
        VRAI -> le set est confie au GROUP OPERATOR (`IdunBattle.Core.Services.AiControl$$ExecuteFor(group) qui
        BOUCLE `PickNextUnit` jusqu'a epuisement des unites valides).
      • `resetTurnFlags` (+0x59) : VRAI -> les flags de tour de chaque cible sont **sauvegardes,
        effaces, puis restaures** autour de l'action -> l'unite agit meme si elle avait deja fini son
        tour, ET **l'action supplementaire ne consomme pas son tour**. C'est la semantique
        d'ordonnancement du mecanisme (cf. `ComputerActionOperation`).

    Appels natifs recenses (xrefs IdunBattleLogic.Entities.DSLBehaviors$$PerformAIAction) : `IdunBattleLogic.Entities.Abilities.Active.Loki.SupremeCommanderAbility$$ExecuteBehaviour`
    (`asGroup=1, reset=1`), `IdunBattleLogic.Entities.Abilities.Active.Loki.CultDemagogueAbility$$ExecuteBehaviour` (`0, 1`),
    `IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$ExecuteBehaviour` + `GetTriggerSummonsBehaviour`,
    `IdunBattleLogic.Entities.Abilities.Active.Loki.ReanimationBeamAbility$$GetSummonsTakeActionBehaviour`,
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.BlackRage_ActivationAbility$$CreateBehaviour`, `AdaptiveStrategyAbility.ExecuteBehaviour`.

    Effet PUR (`stop=False`). Journalise `PerformAIAction` (diag replay-diff)."""
    __slots__ = ("selector", "as_group", "reset_turn_flags")

    def __init__(self, selector: TargetsSelector, as_group: bool = False,
                 reset_turn_flags: bool = True):
        self.selector = selector
        self.as_group = bool(as_group)
        self.reset_turn_flags = bool(reset_turn_flags)

    def execute(self, entities, ectx):
        state = ectx.state
        if state is None:
            return OperationResult.ok()
        units = self.selector.evaluate(entities) or []
        uids = [u.get("id") for u in units if isinstance(u, dict) and u.get("id") is not None]
        if self.as_group:
            res = ComputerActionOperation.execute_group(state, uids, self.reset_turn_flags)
        else:
            res = [ComputerActionOperation.execute(state, uid, self.reset_turn_flags)
                   for uid in uids]
        ectx.emit("PerformAIAction", units=uids, as_group=self.as_group,
                  reset_turn_flags=self.reset_turn_flags, results=res)
        return OperationResult.ok()


class PerformAIMovement(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLBehaviors$$PerformAIMovement(unit, range, overrideUtility)` ->
    `IdunBattle.Entities.Behaviours.PerformAIMovementBehaviour` (`$$.ctor` : `unit@+0x50`,
    `range@+0x58`, `overrideUtility@+0x60` -- signature LUE dans `frida/methods.tsv` :
    `unit:ITargetsSelector, range:IAmountFormula, overrideUtility:UtilityDefinition`).

    `IdunBattle.Entities.Behaviours.PerformAIMovementBehaviour$$Execute` :

        var range = this.range.Calculate(entities);                          // iface IAmountFormula
        var units = this.unit.Select(entities, UnitSelectionType(3));        // iface slot 4
        foreach (var u in units)
            processor.ComputerMovementAction(u.Id, (int?)range, this.overrideUtility);  // slot 54

    -> `Core.Services.OperationProcessor$$ComputerMovementAction` ->
    `IdunBattle.Operations.ComputerActionOperation$$ExecuteMovementFor` ->
    `IdunBattle.Core.Services.AiControl$$ExecuteMovementFor`, dont le port est
    `operations/summon_ai.py::ComputerMovementActionOperation` (les trois etages y sont transcrits).

    ⚠ **CE N'EST PAS `PerformAIAction`** : celui-ci fait jouer un TOUR d'IA complet (l'ability est
    choisie par l'IA) ; celui-la ne demande qu'un DEPLACEMENT, avec un budget (`range`) et un
    scoring de tuile IMPOSE (`overrideUtility`). Le confondre ferait attaquer des unites que le
    natif se contente de faire avancer.

    `override_utility` = les `UtilityType` des buckets du `UtilityDefinition` que l'ability construit
    dans son `.ctor`. Pour `1144 BioMinefield`, `BioMinefieldAbility$$.ctor` alloue un tableau d'UN
    `IdunBattleLogic.AI.Utilities.UtilityBucket` construit avec `0x3e` =
    `UtilityType.BioMinefield_MoveTowardsTarget` (62), puis le range a `<ability>+0xf0`. `None` =
    aucun override -> le scoring du playbook de mouvement par DEFAUT (branche
    `overrideUtility == null` du generateur natif).

    ⚠ **INERTE AUJOURD'HUI POUR SON UNIQUE CONSOMMATEUR, ET C'EST NOMME** : la feuille 62 lit
    `meta["movetowards_hexdist"]`, une cle qu'AUCUN producteur de `meta` du depot ne remplit
    (residu **#175-r**). Score plat -> argmax keep-first -> position courante -> aucun
    `MoveUnitOperation`. La degradation est celle du natif a utilite plate, pas une invention ; ce
    qui manque est l'etage `MoveTowardsUnitUtility$$GetMinDistanceToTarget`. Detail et mesure :
    `movement_action_with_override` (`engine/ai/action_generators.py`).

    Effet PUR (`stop=False`). Journalise `PerformAIMovement` (diag replay-diff). (#939)"""
    __slots__ = ("selector", "range", "override_utility")

    def __init__(self, selector: TargetsSelector, range_formula: Optional[AAmountFormula] = None,
                 override_utility=None):
        self.selector = selector
        self.range = range_formula
        self.override_utility = override_utility

    def execute(self, entities, ectx):
        state = ectx.state
        if state is None:
            return OperationResult.ok()
        # `range.Calculate(entities)` est evalue UNE FOIS, AVANT la boucle sur les unites -- LU :
        # le natif le calcule en tete d'`Execute` et reutilise le meme `Nullable<int>` a chaque
        # `ComputerMovementAction`. L'evaluer par unite serait une infidelite invisible tant que la
        # formule est constante (elle l'est chez 1144 : `Direct(1)`).
        rng = None
        if self.range is not None:
            rng = int(self.range.evaluate(entities))
        units = self.selector.evaluate(entities) or []
        uids = [u.get("id") for u in units if isinstance(u, dict) and u.get("id") is not None]
        moved = []
        for uid in uids:
            moved.append(summon_ai.ComputerMovementActionOperation.execute(
                state, int(uid), override_range=rng,
                override_tile_utility=self.override_utility))
        ectx.emit("PerformAIMovement", units=uids, range=rng,
                  override_utility=([int(t) for t in (self.override_utility or ())]
                                    if self.override_utility is not None else None),
                  moved=moved)
        return OperationResult.ok()


class PerformAIAbility(AbilityBehaviour):
    """`IdunBattleLogic.Entities.DSLBehaviors$$PerformAIAbility(unit, getAbilityType, allowOnlyMove,
    overrideMovement, utilityEntity, customUtility)` -- la surcharge a SIX arguments (l'autre, a
    trois, prend `movementTiles` et n'a qu'un appelant : `BurrowersAbility_Appear`). Elle alloue un
    `IdunBattle.Entities.Behaviours.PerformAIAbilityUnitBehaviour` dont le `.ctor` a 8 parametres
    ecrit (LU, c'est LA source du mapping -- pas le decompile d'`Execute`, ou ghidra decale les
    arguments) :

        +0x50 unit          +0x68 getAbilityType   +0x70 allowOnlyMove   +0x71 skipAtomicCheck
        +0x78 overrideMovement                     +0x80 utilityEntity   +0x90 customUtility

    Le CORPS reste `loki/summon.py::perform_ai_ability_unit_behaviour` -- l'UNIQUE port de
    `PerformAIAbilityUnitBehaviour$$Execute`, partage avec `PerformAIAttack` (de-fork #338). Cette
    feuille n'apporte que les parametres que les deux autres noeuds ne peuvent pas exprimer.

    Appelants natifs recenses (xrefs de la surcharge a 6 args) : `ShockAssaultAbility$$CreateBehaviour`,
    `ECogSupportAbility$$CreateBehaviour`,
    `IdunBattleLogic.Entities.Abilities.Active.Loki.AttemptedPossessionAbility$$ExecuteBehaviour`,
    `DaGreatWaaaghAbility$$ExecuteBehaviour` + `$$GetMoveAndAttackBehaviour`,
    `ItItchesAbility$$ExecuteBehaviour`. Seul le troisieme est porte (#590).

    PARAMETRES DU PORT, et ce que chacun mirrore :

      * `selector` (`+0x50`) -- les ACTEURS. Domaine UNITE (le call-site 1101 y passe le selecteur
        des possedes) ; l'itere est resolu en ids et chaque acteur agit SEQUENTIELLEMENT, dans
        l'ordre du selecteur, comme le `foreach` natif.
      * `override_movement` (`+0x78`) -- un noeud VALEUR, evalue PAR ACTEUR en un `Nullable<int>`
        passe tel quel a `ABaseAiUnitTactic$$GenerateActionTiles(unit, true, maxDistance)` : `0` =
        la tuile COURANTE seule, une valeur > 0 = le budget de deplacement autorise. `None` (aucun
        noeud) = la plage normale de l'unite. C'est ce champ qui porte le << Possessed Summons will
        move before attacking >> de l'i2 de 1101.
      * `allow_only_move` (`+0x70`) -- ajoute le `MovementActionGenerator` : l'IA peut choisir un
        deplacement PUR si aucune attaque n'est bonne. `False` chez 1101 (litteral `0`).
      * `custom_utility` (`+0x90`) -- un delegue evalue PAR ACTEUR. ⚠ Sa signature native n'est
        PAS `Func<AbilityEntities, ...>` : le behaviour lui passe un **`ValueTuple`** dont
        `Item1` = l'ACTEUR courant et `Item2` = l'`utilityEntity` resolu (LU dans
        `PerformAIAbilityUnitBehaviour$$Execute` :
        `ValueTuple..ctor(&tuple, <acteur>, <utilityEntity>)` puis invocation du delegue `+0x90`
        sur ce tuple). Cote port : un callable `(state, actor_id) -> set[int] | None` qui rend
        l'ensemble des ids de cible AUTORISES (`None` = aucune contrainte) ; s'il declare un
        TROISIEME parametre, il recoit en plus l'id de l'`utility_entity` (cf. ci-dessous).
        Cf. l'ecart nomme plus bas (score -> exclusion).
      * `utility_entity` (`+0x80`) -- **CONSOMME, et le residu `#590-r4` le decrivait a tort comme
        inerte** (RE refaite le 2026-08-10 sur `rnca9r7q6c`). Deux points de sa fiche sont
        REFUTES : il n'est pas << passe a la couche d'utilite comme entite de reference du
        scoring >> -- il n'a AUCUN autre lecteur que le `ValueTuple` du `customUtility` ci-dessus,
        donc quand `+0x90` est nul il est effectivement mort ; et sa resolution est le **slot 1
        d'`ITargetsSelector` = `SelectFirst`** (LU : `<invocateur>(1, <ITargetsSelector>, sel,
        entities)`), faite **UNE SEULE FOIS AVANT la boucle** sur les acteurs, pas par acteur.
        Chez `1101` il devient le parametre **`caster`** de
        `IdunBattleLogic.Entities.Abilities.Active.Loki.AttemptedPossessionAbility$$GetPreferredAttackTarget(caster,
        possessedUnit)` -- son `$$GetAttackCustomUtility` fait
        `GetPreferredAttackTarget(this, input+8, input+0)`, donc `Item2` (= `utility_entity`) va
        en `caster` et `Item1` (= l'acteur) en `possessedUnit`.
        Le port THREADE desormais ce canal, en COMPATIBILITE : un `custom_utility` a deux
        parametres garde EXACTEMENT son comportement d'avant (value-preserving), un
        `custom_utility` a trois recoit l'id resolu. La valeur COINCIDAIT deja pour `1101` (le
        consommateur capturait `caster_id` par fermeture au call-site, et `Owner()` y resout au
        caster) -- mais c'etait un COURT-CIRCUIT : la valeur ne venait pas du selecteur `+0x80`,
        donc un call-site qui y passerait autre chose que l'owner serait rendu FAUX en silence.

    ⚠ **`get_ability_type` (`+0x68`) N'EST PAS UN PARAMETRE DU PORT, ET C'EST UNE LECTURE.** Le
    natif y passe un `Func<IEntity,int>` -- pour 1101, le lambda sans capture mis en cache dans le
    singleton `<>c` d'`AttemptedPossessionAbility` (champ statique `+8`). Son CORPS est
    **DEDUPLIQUE** : aucun symbole ne le nomme, ni dans `frida/methods.tsv` ni dans
    `ghidra/functions.tsv` (la classe `<>c` n'y porte que son `.cctor` et le lambda
    `<GetPreferredAttackTarget>b__5_1`). Deux sources CONCORDANTES etablissent qu'il rend
    l'ATTAQUE NORMALE de l'acteur, sans qu'on ait lu le lambda :
      1. i2 verbatim -- << ... immediately **perform a normal attack** against the closest enemy
         unit ... >> ;
      2. le generateur de candidats de la MEME ability
         (`AttemptedPossessionAbility.<>c__DisplayClass5_0$$<GetPreferredAttackTarget>b__0`) appelle
         `IdunBattle.Entities.UnitExtensions$$GetNormalAttackType(unit)` sur ses DEUX branches pour
         enumerer les cibles -- il enumere donc les cibles de l'ability que le behaviour va jouer.
    C'est le MEME corps que les deux autres noeuds de cette famille (dont un proprietaire nomme
    existe : `ShockAssaultAbility.<>c$$<CreateBehaviour>b__1_0`, 7 slots de delegate y pointent).
    Le port passe donc `NORMAL_ATTACK_ID`, comme `PerformAIAttack`.

    ⚠ **LE `customUtility` EST MATERIALISE EN EXCLUSION DE CANDIDAT, PAS EN SCORE -- ECART NOMME.**
    Le natif range l'utilite `IdunBattle.AI.Utilities.OnlyCertainTargetUtility` dans une
    `UtilityDefinition` que `ActiveAbilityActionGenerator$$GenerateActions` consulte ; son
    `$$EvaluateAttackInSteps` yield **l'une de DEUX constantes statiques** de la classe selon que
    `this.targets.Contains(utilityAttackCase.Target)` ou non (LU : `statics+0x00` si contient,
    `statics+0x20` sinon). **La POLARITE de ces deux constantes n'est pas lisible offline** -- la
    classe n'a pas de `.cctor` nomme et les deux slots sont des `DAT_*`. Le port retient
    l'ELIMINATION (une cible hors liste n'est pas candidate), pour trois raisons LUES :
    le nom de la classe (<< Only Certain Target >>), le fait que `GetAttackCustomUtility` rend
    **null** -- donc AUCUNE contrainte -- quand `GetPreferredAttackTarget` ne trouve rien (il ne
    fabrique une utilite que pour CONTRAINDRE), et le fait que la << preference >> de l'i2 est
    deja entierement resolue en amont, dans `b__0` (repli sur la liste non filtree si le filtre
    << non possedes >> la vide) : ce qui sort est UNE cible, pas un souhait.
    Si la constante de rejet etait seulement BASSE et non eliminatoire, le port refuserait de
    frapper la ou le natif frapperait faute de mieux -- degradation CONSERVATRICE (on n'invente
    pas un degat). Residu `#590-r5` (`BLOCAGE: capteur` -- trancher demande de lire les deux
    champs statiques a l'execution).

    Effet PUR (`stop=False`). Journalise `PerformAIAbility` (diag replay-diff)."""
    __slots__ = ("selector", "override_movement", "allow_only_move", "utility_entity",
                 "custom_utility", "get_ability_type")

    def __init__(self, selector: TargetsSelector,
                 override_movement: Optional[AAmountFormula] = None,
                 allow_only_move: bool = False,
                 utility_entity: Optional[TargetsSelector] = None,
                 custom_utility=None,
                 get_ability_type=None):
        self.selector = selector
        self.override_movement = override_movement
        self.allow_only_move = bool(allow_only_move)
        self.utility_entity = utility_entity
        self.custom_utility = custom_utility
        # `+0x68` MATERIALISE (#964-r1) -- cf. l'avertissement ci-dessus, qui reste vrai pour 1101 :
        # son `Func` est le lambda CACHE `GetNormalAttackType`, donc `None` = comportement d'avant,
        # octet pour octet. `ECogSupportAbility$$CreateBehaviour` en fournit un AUTRE
        # (`<>c$$<CreateBehaviour>b__3_0` = `UnitExtensions$$GetRepairType`), et le rabattre sur
        # l'attaque normale ferait ATTAQUER un E-Cog que le natif fait REPARER.
        # Contrat du port : un callable `(state, unit_id) -> int | None` (`None` = pas d'ability,
        # l'acteur est saute -- le natif, lui, appellerait l'IA avec un type nul).
        self.get_ability_type = get_ability_type

    @staticmethod
    def _accepte_utility_entity(fn) -> bool:
        """Le `custom_utility` declare-t-il un TROISIEME parametre positionnel ?

        C'est ce qui rend le threading du canal `+0x80` VALUE-PRESERVANT : les consommateurs
        ecrits avant (contrat `(state, actor_id)`) ne voient AUCUN changement, et un consommateur
        qui veut la donnee la declare. Une signature illisible (builtin, C-extension) est traitee
        comme un refus -- on ne tente pas un appel a trois arguments pour voir.
        """
        try:
            sig = inspect.signature(fn)
        except (TypeError, ValueError):
            return False
        positionnels = [p for p in sig.parameters.values()
                        if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
        if any(p.kind is p.VAR_POSITIONAL for p in sig.parameters.values()):
            return True
        return len(positionnels) >= 3

    def execute(self, entities, ectx):
        from ..loki.summon import perform_ai_ability_unit_behaviour
        state = ectx.state
        if state is None:
            return OperationResult.ok()
        units = self.selector.evaluate(entities) or []
        uids = [u.get("id") for u in units if isinstance(u, dict) and u.get("id") is not None]
        # `+0x80` est resolu UNE SEULE FOIS, AVANT la boucle sur les acteurs -- LU : dans
        # `PerformAIAbilityUnitBehaviour$$Execute` le `SelectFirst` du champ precede le `foreach`,
        # et son resultat (`local_460`) est reutilise tel quel a chaque tour de boucle. Le resoudre
        # PAR ACTEUR serait une infidelite invisible tant que le selecteur est constant.
        ue = resolve_unit(self.utility_entity, entities) if self.utility_entity is not None else None
        ue_id = ue.get("id") if isinstance(ue, dict) else None
        acted = []
        for uid in uids:
            # `+0x78` evalue PAR ACTEUR : le natif re-ecrit l'ACTEUR dans l'`AbilityEntities` avant
            # d'appeler `Calculate`, donc la formule voit `Actor` = l'unite courante. Cote port,
            # `entities` porte deja ce binding (`entities_from_state(... actor=...)` cote appelant) ;
            # on le repositionne ici pour que la formule le lise sans que le call-site ait a
            # dupliquer l'arbre par acteur.
            move_amount = None
            if self.override_movement is not None:
                prev = getattr(entities, "actor", None)
                try:
                    entities.actor = next((u for u in units
                                           if isinstance(u, dict) and u.get("id") == uid), None)
                    move_amount = int(self.override_movement.evaluate(entities))
                finally:
                    entities.actor = prev
            allowed = None
            if self.custom_utility is not None:
                # Mirror du `ValueTuple(Item1 = acteur, Item2 = utilityEntity)` que le natif passe
                # au delegue `+0x90`. Le 3e argument n'est fourni qu'aux consommateurs qui le
                # declarent (cf. `_accepte_utility_entity`) : c'est ce qui garde la migration
                # value-preservante pour ceux qui capturaient deja la valeur par fermeture.
                if self._accepte_utility_entity(self.custom_utility):
                    allowed = self.custom_utility(state, int(uid), ue_id)
                else:
                    allowed = self.custom_utility(state, int(uid))
            # `+0x68` evalue PAR ACTEUR : le natif invoque le `Func<IEntity,int>` sur l'acteur
            # courant (`GetRepairType(e)` pour ECogSupport). `None` = le champ n'est pas fourni ->
            # l'attaque normale, comme les huit appelants d'avant.
            aid = None if self.get_ability_type is None else self.get_ability_type(state, int(uid))
            if self.get_ability_type is not None and aid is None:
                # Le `Func` n'a rien rendu : l'acteur n'a pas cette ability. On le SAUTE plutot que
                # de lui faire jouer autre chose.
                acted.append({"unit": int(uid), "ability_type": None, "result": None})
                continue
            res = perform_ai_ability_unit_behaviour(
                state, int(uid), self.allow_only_move, move_amount,
                allowed_targets=allowed, ability_type=aid)
            acted.append({"unit": int(uid), "move_amount": move_amount,
                          "ability_type": aid,
                          "allowed_targets": (sorted(allowed) if allowed is not None else None),
                          "result": res})
        # `utility_entity` est JOURNALISE : le residu #590-r4 l'annoncait deja comme tel, mais
        # l'`emit` ne le portait pas -- le seul canal d'observation du champ etait donc muet.
        ectx.emit("PerformAIAbility", units=uids, allow_only_move=self.allow_only_move,
                  utility_entity=ue_id, acted=acted)
        return OperationResult.ok()
