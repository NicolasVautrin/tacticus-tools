"""Revive-EN-PLACE d'unite -- sous-systeme `ReviveData` (case-66 / #88-#89). DISTINCT de
`ResurrectUnitOperation` (ambush tile-choice, resurrect.py) : le REVIVE remet l'unite VIVANTE a la MEME
position (in-place) ; il n'y a PAS de tuile choisie ni de flag one-shot Ambush.

--------------------------------------------------------------------------------------------------
LE PIVOT : `UnitComponent + 0xa8` = `Nullable<ReviveData>` (case-89 volet C, RE 2026-07-25)
--------------------------------------------------------------------------------------------------
La feuille DSL `Revive` NE MUTE RIEN. Le sous-systeme est en DEUX TEMPS, articules autour du champ
`Nullable<ReviveData>` @UnitComponent+0xa8 :

  1. POSE      `IdunBattleLogic.Entities.DSLBehaviors$$Revive` -> `IdunBattle.Entities.Behaviours.ReviveBehaviour$$Execute` : pour chaque
               cible du selecteur, `amount = Min(formule, IdunBattle.Entities.Behaviours.ReviveBehaviour$$GetMaxReviveAmount)`, construit la
               `ReviveData` puis, SI `IdunBattle.Entities.Behaviours.ReviveBehaviour$$IsPreferredRevive`, ECRIT les 9 qwords
               `unitComponent + 0xa8 .. +0xe8`. AUCUNE mutation de PV/flag/position ici.
  2. GARDE     `IdunBattle.Operations.KillUnitOperation$$Execute` : `On(PreUnitDeath)` est emis @IdunBattle.Operations.KillUnitOperation$$Execute+0x7dc PUIS
               @IdunBattle.Operations.KillUnitOperation$$Execute+0x82e la garde `pcVar21 = thunk_FUN_1801f3000(unitComponent + 0xa8,
               <hasValue de Nullable<ReviveData>>) ; if (*pcVar21 == '\\0') { ... }`. TOUT le reste de
               la mort est DANS ce bloc (verifie a la profondeur d'accolades : `On(PreUnitDeath)` @depth 7,
               `On(PreUnitDeath_2)`/`On(UnitDeath)`/`On(UnitDefeated)`/`On(PostUnitKill)` @depth 9). Un revive POSE pendant `On(PreUnitDeath)`
               **ANNULE la mort** -- cf. `damage.py::_fire_death_if_killed`.
  3. APPLICATION `IdunBattle.Operations.KillUnitOperation$$Execute`, DANS LA MEME FONCTION que la garde du cran 2 :
               la branche `else` de ce `if (!pendingRevive.HasValue)` appelle
               `Core.Services.OperationProcessor$$ReviveUnit(killed)` -> `IdunBattle.Operations.ReviveUnitOperation$$Execute`
               (ICI) qui LIT la `ReviveData`, applique, et REMET LES 9 QWORDS A 0
               @IdunBattle.Operations.ReviveUnitOperation$$Execute+0xda7+.

Le port met donc 2 et 3 au meme endroit (`kill_unit_revive_gate`, appelee par `_fire_death_if_killed`
juste apres `On(PreUnitDeath)`) parce que LE NATIF LES Y MET : ce n'est pas un collapse, c'est la
structure lue.

⚠ **LE REVIVE N'A AUCUNE PHASE, ET C'EST UN RESULTAT MESURE** (#477-r24). Trois tranches ont
ecrit ici que le cran 3 etait le drain de `RunPhase(PhaseType.ProcessRemovals /*0xd*/)`
d'`IdunBattle.Messages.InputMessageProcessor$$VerifyDeaths`.
C'est faux, et trois voies INDEPENDANTES le disent :
  * `data/symbols/<CURRENT>/frida/enums.tsv` NOMME l'enum -- `IdunBattle.Core.PhaseType` =
    `0=StartBattle, ..., 12=ProcessDeaths, 13=ProcessRemovals`. **Aucun membre ne nomme un revive**
    (mirror : `engine/streams/phase_type.py`) ;
  * la lambda passee a `RunPhase(PhaseType.ProcessRemovals /*0xd*/)` est
    `IdunBattle.Messages.InputMessageProcessor.u003Cu003Ec__DisplayClass50_0$$u003CVerifyRemovedUnitsu003Eb__0`,
    qui vide la file des RETRAITS -- `VerifyDeaths` en inline le corps d'`IdunBattle.Messages.InputMessageProcessor$$VerifyRemovedUnits` ;
  * `Core.Services.OperationProcessor$$ReviveUnit(killed)` n'a AUCUNE xref CODE dans le binaire
    (ses deux seules xrefs sont des entrees DATA de tables de methodes) : son unique site
    d'invocation est la branche `else` du cran 3 ci-dessus.
⇒ le revive s'execute SYNCHRONIQUEMENT dans le kill, donc dans la phase de l'action qui a PROVOQUE
ce kill -- `PhaseType.ProcessDeaths` quand le kill vient du drain de `VerifyDeaths`, mais tout
aussi bien `PhaseType.Damage` ou `PhaseType.ActiveAbility` quand `KillUnit` est appele en ligne.

--------------------------------------------------------------------------------------------------
`IdunBattle.Operations.ReviveUnitOperation$$Execute` (mutateur ECS IMPERATIF, mirror ci-dessous)
--------------------------------------------------------------------------------------------------
  * garde        @IdunBattle.Operations.ReviveUnitOperation$$Execute+0x2ba : `if (!pendingRevive.HasValue)` -> `Logger.Error` + RETURN (pas de revive)
  * IdunBattle.Operations.ReviveUnitOperation$$SetHealth : hp = Min(ReviveData.amount, GetStat(unit, Health=5, MAX=3))  (re-clamp)
  * RemoveEffects INLINE (#547-r14) : `processor.<slot 0x5a>(unit, {step: SANS valeur, +0x08: 1})`
                 -> `IdunBattle.Operations.RemoveEffectsOperation$$Execute` retire TOUS les effets
                 du ressuscite SAUF ceux a `IEffect` slot 2 `get_KeepOnRevive = True`. C'est le SEUL
                 des sept `$$RemoveEffects` du binaire a armer ce gate (#547-r13) -- sur le chemin
                 de MORT il vaut 0, donc le slot 2 n'y est jamais lu.
  * flags        IdunBattle.Operations.ReviveUnitOperation$$Execute+0x7e0 : Remove(0xf), Remove(8=overkill), Add(0x14) -> l'unite redevient VIVANTE
                 (PAS 0xe AmbushConsumed -- un revive-en-place N'EST PAS un ambush one-shot)
  * IdunBattle.Operations.ReviveUnitOperation$$SetRevivePosition : repositionne sur la tuile de l'unite -> IN-PLACE
  * emet `On(UnitRevived = 0x2d = 45)` @IdunBattle.Operations.ReviveUnitOperation$$Execute+0xac1 (`FUN_1800280e0(0x4d,...,lVar16,0x2d)`)  # On(UnitRevived)
  * PUIS purge `unitComponent + 0xa8 .. +0xe8 = 0` @IdunBattle.Operations.ReviveUnitOperation$$Execute+0xda7+ (donc APRES le dispatch de On(0x2d = UnitRevived))

Frontiere DSL (#149) : la feuille `Revive` (declaratif, `triggers/revive_effect.py`) POSE ; l'Operation
(imperatif, ICI) APPLIQUE. On NE fusionne PAS.
"""
from __future__ import annotations

from typing import Optional

from ..state import State
from ..components import UnitComponent, HealthComponent
from ..components import PositionComponent, record_tiles_moved
from ..components import UnitFlagsComponent
from ...entities.unit_flag import UnitFlag
from .movement import _kill_steppable_units
# FORME B (liaison de MODULE) -- arete GRATUITE, MESUREE en process frais : `import
# engine.runner.operations.remove_effects` seul ne charge PAS ce module (pas de cycle), et
# `remove_effects` est de toute facon deja tire par la cascade de `movement` ci-dessus. La forme B
# est choisie pour que le foyer reste substituable par un `monkeypatch.setattr` (CLAUDE.md : c'est
# la SEULE des trois formes qui morde).
from . import remove_effects as _remove_effects
from .triggers.dispatch.move_death import (
    unit_position_changed_1_triggers, unit_position_changed_2_triggers
)
from .triggers.dispatch.move_death import unit_revived_triggers
from ...battle_query import get_distance
from ..abilities.loki.swarm import on_group_unit_hp_changed

# `Revive(..., healType, sourceId, ?, priority, ?)` -- priorite par defaut des consommateurs
# (`IdunBattle.Entities.Effects.ReviveEffect$$CreateTargetTriggerBehaviour` et `FuelledByFury_ReviveAbility.CreateBehaviour
# IdunBattleLogic.Entities.Abilities.Triggered.Loki.FuelledByFury_ReviveAbility$$CreateBehaviour` passent 0 ; `IdunBattleLogic.Entities.Abilities.Triggered.Loki.PhoenixGem_ReviveAbility$$CreateBehaviour` passe **-1000**
# = 0xfffffc18, la plus BASSE -> tout autre revive lui est prefere).
REVIVE_PRIORITY_DEFAULT = 0


def is_preferred_revive(existing: Optional[dict], new: dict) -> bool:
    """`IdunBattle.Entities.Behaviours.ReviveBehaviour$$IsPreferredRevive` (mirror 1:1) :

        if (!existing.HasValue) return true;                       // aucun revive en attente
        if (new.priority > existing.priority) return true;         // param_3[6] vs local_30
        if (new.priority < existing.priority) return false;
        return existing.amount < new.amount;                       // local_48[0] < *param_3

    (Le decompile teste `param_3[6] <= local_30` puis `local_30 <= param_3[6]` : le premier `if` filtre
    `new.priority > existing.priority` -> true ; l'egalite retombe sur la comparaison des `amount`.)"""
    if existing is None:
        return True
    ep, np_ = int(existing.get("priority") or 0), int(new.get("priority") or 0)
    if np_ > ep:
        return True
    if np_ < ep:
        return False
    return int(existing.get("amount") or 0) < int(new.get("amount") or 0)


def post_pending_revive(state: State, unit_id: int, amount, heal_type: int = 0,
                        source=None, priority: int = REVIVE_PRIORITY_DEFAULT,
                        revive_position=None) -> Optional[dict]:
    """Mirror de l'ECRITURE de `IdunBattle.Entities.Behaviours.ReviveBehaviour$$Execute` : pose la `ReviveData` sur
    `unitComponent + 0xa8` si `IsPreferredRevive`. AUCUNE mutation de PV/flag/position (c'est
    `ReviveUnitOperation` qui les fait, plus tard). Renvoie la `ReviveData` posee, ou None si le gate
    `IsPreferredRevive` l'a rejetee (ou entite/composant absent).

    `source` = le `sourceId` (`Nullable<AbilityOrEffect>`) : `AbilityOrEffect(effect.Id)` pour un
    `ReviveEffect` (IdunBattle.Entities.Effects.ReviveEffect$$CreateTargetTriggerBehaviour `param_1[2]`), `AbilityOrEffect(this.Id)` pour une TriggeredAbility
    autonome (PhoenixGem 1458 IdunBattleLogic.Entities.Abilities.Triggered.Loki.PhoenixGem_ReviveAbility$$CreateBehaviour, FuelledByFury 1251 IdunBattleLogic.Entities.Abilities.Triggered.Loki.FuelledByFury_ReviveAbility$$CreateBehaviour). Il est relu par le noeud
    `CurrentAbilityIs` des triggers `On(UnitRevived)`.

    `revive_position` = le champ `Nullable<UnitPosition>` de la `ReviveData` (#213). Il est renseigne
    par `ReviveBehaviour$$Execute` UNIQUEMENT quand le 7e argument de `IdunBattleLogic.Entities.
    IdunBattleLogic.Entities.DSLBehaviors$$Revive` (`targetsTile`) est NON NUL : le decompile evalue alors ce selecteur
    (`FUN_180024d10(10, …, param_2+0x90, entities)`), en prend l'element d'index de la CIBLE COURANTE
    (`IList.get_Item(i)`), le `ToList()` et l'enveloppe dans le `Nullable`. Tous les consommateurs
    portes AVANT #213 passent `targetsTile = 0` -> `None` = revive **IN-PLACE** (c'est le
    `if (!revivePosition.HasValue) return;` en tete de
    `IdunBattle.Operations.ReviveUnitOperation$$SetRevivePosition`). Le SEUL poseur non-nul du build
    est `IdunBattle.Entities.Effects.Loki.GhostEffect$$CreateTargetTriggerBehaviour` (`tiles =
    Owner@0x148` = la TUILE porteuse du ghost). Le port collapse la `UnitPosition` (liste de tuiles,
    une par pied) en un `(col, row)` -- meme collapse que `PositionComponent`."""
    e = state.get_entity(unit_id)
    if e is None:
        return None
    uc = e.get_component(UnitComponent)
    if uc is None:
        return None
    data = {"amount": (None if amount is None else int(amount)), "heal_type": int(heal_type),
            "source": source, "priority": int(priority),
            "revive_position": (None if revive_position is None
                                else (int(revive_position[0]), int(revive_position[1])))}
    if not is_preferred_revive(uc.pending_revive, data):
        return None
    uc.pending_revive = data
    return data


def _set_revive_position(state: State, unit_id: int, pos) -> Optional[tuple]:
    """`IdunBattle.Operations.ReviveUnitOperation$$SetRevivePosition(revivePosition, unit)` -- MIRROR.

    C'est le SEUL endroit du sous-systeme revive ou la POSITION change, et la garde qui l'ouvre est
    la premiere instruction de la fonction :

        if (!revivePosition.HasValue) return;              <- revive IN-PLACE (cas par defaut)
        pos      = revivePosition.Value
        feet     = UnitExtensions.GetUnitFeet(unit)        \\
        ResetPreviousTileIfStillOwned(unit, feet)           > liberation des tuiles occupees
        ResetFeet(unit)                                    /
        newTiles = BattleQuery.<slot 0x8d>(pos)
        processor.<slot 0x7e = SetUnitPosition>(unit, pos, false)  <- ECRITURE de la position
        KillSteppableUnits(unit, newTiles)                  <- ce qui trainait sur la tuile est ecrase
        if (mainTile != null && pos.MainTile != null)                                   # <- #347
            RecordTilesMoved(unit, BattleQuery.GetDistance(mainTile, pos.MainTile), state)
        AbilityEntities.ctor(unit, unit, unit, …, feet, …, pos, …)
        publie On(0x24 = UnitPositionChanged_1)
        publie On(0x1d = UnitPositionChanged_2)

    Le port n'a ni entites-pieds ni reservation de tuile -> `ResetPreviousTileIfStillOwned`/`ResetFeet`
    n'ont pas d'equivalent observable (la position exclusive du port suffit : ecrire la nouvelle tuile
    libere l'ancienne). Le reste est porte tel quel : ecriture de `PositionComponent`, crush des
    Steppable de la tuile d'arrivee (MEME helper que le move, `movement._kill_steppable_units`), le
    comptage de tuiles, puis les DEUX events de position.

    #347 -- **le 4e call-site de `IdunBattle.Entities.UnitExtensions$$RecordTilesMoved`** : un revive
    A POSITION facture la **distance HEXAGONALE** entre la tuile d'avant et celle d'apres
    (`GetDistance(Tile, Tile)`, slot 0x6c de `IBattleQuery` -> mirror `battle_query.get_distance`),
    **pas** la longueur d'un chemin -- contrairement a `MoveUnitOperation$$Execute`, qui facture
    `GetNumTilesMoved(connectedPath)`. Un revive IN-PLACE (`revivePosition` sans valeur) sort avant
    et n'enregistre rien ; le seul poseur non-nul du build est
    `IdunBattle.Entities.Effects.Loki.GhostEffect$$CreateTargetTriggerBehaviour`.

    ⚠ `On(0x24)` est precisement l'un des cinq retraits de `GhostEffect` (« une autre unite arrive sur
    la tuile du ghost ») : une resurrection sur un ghost peut donc en retirer un AUTRE. Le ghost sur
    lequel on ressuscite, lui, s'est deja retire par son propre `GetRemoveEffectBehaviour`.

    Renvoie la position ecrite, ou `None` si le revive est resté in-place (garde native)."""
    if pos is None:
        return None                                   # `if (!revivePosition.HasValue) return;`
    e = state.get_entity(unit_id)
    if e is None:
        return None
    to = (int(pos[0]), int(pos[1]))
    pc = e.get_component(PositionComponent)
    # `mainTile = GetMainTile(unit, state)` -- LU EN TETE, avant toute ecriture de position.
    main_tile_before = (pc.col, pc.row) if pc is not None else None
    if pc is None:
        e.add_component(PositionComponent(to[0], to[1]))
    else:
        pc.col, pc.row = to
    # `KillSteppableUnits(unit, newTiles)` -- MEME operation que celle du move (helper partage, pas
    # une 2e implementation) : un decoy/spore-mine sur la tuile d'arrivee est ecrase par un kill
    # PROPRE (aucun death-trigger).
    _kill_steppable_units(state, to, unit_id)
    # #347 -- `if (mainTile != null) { if (revivePosition.Value.MainTile != null) {
    #     RecordTilesMoved(unit, battleQuery.GetDistance(mainTile, revivePosition.Value.MainTile),
    #                      state); } }`
    # RANG NATIF EXACT : apres `KillSteppableUnits`, AVANT la construction des `AbilityEntities` et
    # les deux events de position. La garde native est double (les DEUX tuiles doivent exister) ;
    # `record_tiles_moved` re-applique par ailleurs son propre `< 1 -> no-op`, ce qui neutralise le
    # cas « meme tuile » (distance 0).
    if main_tile_before is not None:
        record_tiles_moved(state, unit_id, get_distance([main_tile_before], [to]))
    # `On(0x24 = UnitPositionChanged_1)` puis `On(0x1d = UnitPositionChanged_2)`, {actor = target =
    # l'unite ressuscitee} (`AbilityEntities.ctor(unit, unit, unit, …)` lu au decompile).
    unit_position_changed_1_triggers(state, unit_id)
    unit_position_changed_2_triggers(state, unit_id)
    return to


class ReviveUnitOperation:
    """Mirror `IdunBattle.Operations.ReviveUnitOperation$$Execute` (mutateur ECS, revive-EN-PLACE). Signature NATIVE
    = `Execute(operation, entity)` : le HP n'est PAS un parametre, il vient de la `ReviveData` posee sur
    `UnitComponent + 0xa8` (mirror exact ici). `IdunBattle.Operations.ReviveUnitOperation$$SetHealth` re-clampe `Min(amount, hp_max)`.
    Position INCHANGEE (in-place)."""
    __slots__ = ()

    @staticmethod
    def execute(state: State, unit_id: int) -> Optional[dict]:
        e = state.get_entity(unit_id)
        if e is None:
            return None
        uc = e.get_component(UnitComponent)
        if uc is None:
            return None
        data = uc.pending_revive
        if data is None:
            # @IdunBattle.Operations.ReviveUnitOperation$$Execute+0x2ba : `if (!pendingRevive.HasValue)` -> Logger.Error + RETURN (aucun revive).
            return None
        hc = e.get_component(HealthComponent)
        hp = data.get("amount")
        # IdunBattle.Operations.ReviveUnitOperation$$SetHealth : hp = Min(amount, GetStat(unit, Health, MAX)). Sans HealthComponent/max
        # capte -> on pose l'amount brut (fidelite-safe : le clamp natif est un Min, jamais un boost).
        set_hp = None
        if hc is not None and hp is not None:
            set_hp = int(hp)
            if hc.hp_max is not None:
                set_hp = min(set_hp, int(hc.hp_max))     # Min(amount, maxHP)
            # ⚠ LE REVIVE PURGE L'ACCUMULATEUR DE SUR-REDUCTION -- et `#462-r4e-o-r2` disait le
            # CONTRAIRE (« quirk natif, ne pas corriger »). MESURE LIVE #462-r4e-o-r2-r1 :
            # apres un revive `TaintedNarthecium` NATIF, l'attaque suivante rend la cardinalite
            # PLEINE (5 events), pas 1 ; le port rendait 1.
            # POURQUOI le RE offline se trompait : `IdunBattle.Operations.ReviveUnitOperation$$SetHealth`
            # n'appelle bien NI `IdunBattle.Entities.Components.FillUpStatComponent$$FillUp` NI
            # `$$Initialize` -- mais ce ne sont PAS les seuls ecrivains du zero. Il pose un
            # modificateur `{StatType.Health, ModifierType 0, Min(amount, maxHP)}` qui descend par
            # `IdunBattle.Entities.UnitExtensions$$ApplyStatModifiers` ->
            # `IdunBattle.Entities.UnitExtensions$$ApplyStatModifier` ->
            # `IdunBattle.Entities.Components.FillUpStatComponent$$ApplyModifier`, dont le `case 0`
            # ecrit `Current` **ET** `this[0x24] = 0`. C'est le QUATRIEME ecrivain, et c'est
            # exactement le vice que `-r2` reprochait a `-r1` : une table d'ecrivains reputee
            # exhaustive qui ne l'etait pas.
            # FOYER du mirror : `HealthComponent.apply_modifier_set_current` (ecriture ABSOLUE +
            # purge), pendant du `fill_up` RELATIF que prennent soin/reparation/resurrection.
            hc.apply_modifier_set_current(set_hp)
        # RETRAIT DES EFFETS DU RESSUSCITE (#547-r14) -- `processor.<slot 0x5a RemoveEffects>(unit,
        # options)`, appele **INLINE** par `IdunBattle.Operations.ReviveUnitOperation$$Execute`
        # entre `IdunBattle.Operations.ReviveUnitOperation$$SetHealth` et l'enregistrement
        # `HasBeenRevivedByAbility` qui suit -- c'est le RANG NATIF, lu, pas choisi.
        #
        # OPTIONS, lues aux DEUX ecritures qui precedent l'appel dans le decompile :
        #   `local_438 = 0`                 -> `Nullable<KillUnitStep> step` SANS valeur -> AUCUN
        #                                      filtre par step : TOUT l'inventaire est candidat ;
        #   `lStack_430 = ...CONCAT44(_, 1)` -> `options.<+0x08> = 1` -> le gate de la SECONDE
        #                                      clause est ARME.
        # C'est le SEUL des sept `$$RemoveEffects` du binaire a armer ce gate (#547-r13) : le natif
        # retire donc ici TOUS les effets du ressuscite SAUF ceux a `KeepOnRevive = True`.
        #
        # ⚠ CE N'EST PAS UN RETRAIT DE MASSE, ET C'EST LE POINT LE PLUS FACILE A MAL LIRE : le
        # DEFAUT de `IdunBattle.Entities.Effects.BaseEffect` est `True` (derive : `b0 01 c3`), donc
        # la quasi-totalite des effets SURVIT. Le retrait ne mord que sur les classes qui renversent
        # le getter a `False` -- TROIS dans le binaire (`Loki.HealingBalmsEffect`,
        # `Loki.PrecisionShot_AimEffect`, `Loki.RitesOfMorkai_ExtraDamageEffect`), dont DEUX ont un
        # mirror porte. Le port d'avant #547-r14 n'en retirait AUCUN.
        #
        # RANG relatif a l'etat : le retrait a lieu APRES l'ecriture des PV et AVANT `Add(0x14 =
        # Revived)` / `uc.alive = True`, donc les vecteurs `On(0x3f)`/`On(0x40)` que
        # `remove_effect_instance` publie voient une unite aux PV RETABLIS mais pas encore marquee
        # vivante -- exactement l'ordre du decompile.
        _remove_effects.remove_effects_operation(state, unit_id, step=None,
                                                 keep_on_revive_gate=True)
        # flags `IdunBattle.Operations.ReviveUnitOperation$$Execute` : `Remove(0xf = Downed)`,
        # `Remove(8 = Overkilled)`, `Add(0x14 = Revived)` -> l'unite redevient VIVANTE.
        # Le port modelise l'etat de vie via `uc.alive` ; `Remove(8)` est load-bearing (le flag est
        # le gate du SITE (A) d'`IdunBattle.Operations.ApplyDamageOperation$$Execute`, et il est lu
        # par `HasFlag(unit, 8)` du volet OVERKILL de DoomSiren) -- sans lui, une unite revive apres
        # overkill (TaintedNarthecium `ReviveOnOverkill`) resterait marquee overkillee.
        # `Add(0x14)` n'a AUCUN LECTEUR PORTE (recense #462-r4e-o-r2-r1) : il est pose pour que
        # l'etat de flags egale celui du natif -- MESURE live `[0, 1, 20]` contre port `[0, 1]`.
        # `Remove(0xf = Downed)` n'a aucun POSEUR porte : inerte, pose pour completer la rafale.
        # ENREGISTREMENT `HasBeenRevivedByAbility` (#213) : mirror du bloc que le natif execute
        # ENTRE `SetHealth` et les flags -- `if (sourceId.HasValue) { GetComponent<
        # ActorStatisticsComponent>(unit)@+0xe0 .Add(sourceId.Value) }`. C'est CE set que relit
        # `HasBeenRevivedAbilityTrigger$$ShouldTrigger`, et il n'est JAMAIS remis a zero : le gate
        # `NOT HasBeenRevivedByAbility(self, 1186)` de `GhostReviveAbility`/`GhostEffect` est donc un
        # « une seule fois par BATAILLE ». Loge sur le `UnitComponent` du port (residu structurel
        # documente, cf. `components.py`).
        src = data.get("source")
        if src is not None:
            uc.revived_by_abilities.add(int(src))
        # #545 : le composant est CREE s'il manque, jamais saute. `UnitFlagsComponent$$.ctor`
        # construit un `OrderedSet` VIDE et `IdunBattle.Entities.Factories.UnitFactory` le monte sur
        # CHAQUE unite -- natif, « composant absent » n'existe pas, donc un `if fl is not None:` qui
        # SAUTE la rafale est un no-op SILENCIEUX (ici : `Add(0x14 = Revived)` jamais pose). Meme
        # geste que `resurrect.py` et que `turnflow.FinishUnitTurnOperation`, qui le faisaient deja.
        fl = e.get_component(UnitFlagsComponent)
        if fl is None:
            fl = e.add_component(UnitFlagsComponent())
        fl.remove(UnitFlag.Downed)                           # Remove(0xf)
        fl.remove(UnitFlagsComponent.OVERKILLED)             # Remove(8)
        fl.add(UnitFlagsComponent.REVIVED)                   # Add(0x14)
        uc.alive = True
        # IdunBattle.Operations.ReviveUnitOperation$$SetRevivePosition : appele ICI (apres les flags,
        # AVANT `On(0x2d = UnitRevived)`). Le natif sort immediatement si `revivePosition` n'a pas de valeur -> le
        # revive est alors IN-PLACE (aucune ecriture de position), ce qui est le cas de TOUS les
        # consommateurs sauf le ghost de `thousTerminator` (#213).
        moved_to = _set_revive_position(state, unit_id, data.get("revive_position"))
        # #60 : re-eval du stat-mod EXTRA_HITS du trait Swarm au retour a la vie (bras On(UnitRevived=45) du
        # IdunBattleLogic.Entities.Abilities.Active.Loki.SwarmAbility$$CreateTrigger), comme ResurrectUnitOperation.
        if hc is not None and set_hp is not None:
            on_group_unit_hp_changed(state, unit_id)
        # `On(UnitRevived = 0x2d = 45)` @IdunBattle.Operations.ReviveUnitOperation$$Execute+0xac1 -- emis AVANT la purge du champ (ordre natif lu).
        # Consommateurs portes : `PhoenixGem_CanReviveEffect` (IdunBattle.Entities.Effects.Loki.PhoenixGem_CanReviveEffect$$CreateHandleTriggerAbilitiesInternal : retrait du marqueur 1451 sous
        # `CurrentAbilityIs(PhoenixGem)`), et tout futur `On(0x2d = UnitRevived)`.
        fired = unit_revived_triggers(state, unit_id, current_ability=data.get("source"))
        # purge des 9 qwords @IdunBattle.Operations.ReviveUnitOperation$$Execute+0xda7+ : la `ReviveData` est consommee.
        uc.pending_revive = None
        return {"revived": int(unit_id), "hp": set_hp, "in_place": moved_to is None,
                "revive_position": moved_to,
                "source": data.get("source"), "on_revived": fired}


def kill_unit_revive_gate(state: State, unit_id: int) -> Optional[dict]:
    """**GARDE de `KillUnitOperation.Execute` @IdunBattle.Operations.KillUnitOperation$$Execute+0x82e**, et son
    unique consequence : l'appel a `Core.Services.OperationProcessor$$ReviveUnit(killed)` dans la
    branche `else` de cette meme garde. LES DEUX SONT DANS LA MEME FONCTION NATIVE -- il n'y a rien
    a fondre ici, et surtout AUCUNE PHASE (#477-r24 : `RunPhase(PhaseType.ProcessRemovals /*0xd*/)`
    draine les RETRAITS, cf. l'entete du module).

    A appeler JUSTE APRES `On(PreUnitDeath = 1)` et AVANT `On(PreUnitDeath_2 = 2)` :
      * renvoie `None`  -> `pendingRevive.HasValue == false` : la garde PASSE, la mort CONTINUE
        (le caller emet `On(PreUnitDeath_2)`, `On(UnitDeath)`, `On(UnitDefeated)`, `On(PostUnitKill)` et fait le bookkeeping de mort) ;
      * renvoie un dict -> un revive etait EN ATTENTE : la garde ECHOUE, **toute la suite de la mort est
        COURT-CIRCUITEE** cote natif ; on applique ici le revive (mirror `ReviveUnitOperation.Execute`)
        et le caller DOIT s'arreter."""
    e = state.get_entity(unit_id)
    uc = e.get_component(UnitComponent) if e is not None else None
    if uc is None or uc.pending_revive is None:
        return None                                     # garde franchie -> la mort suit son cours
    # branche `else` de la garde : `processor.ReviveUnit(killed)`, DANS `KillUnitOperation$$Execute`.
    return ReviveUnitOperation.execute(state, unit_id)


def reset_revive_gates(state: State) -> None:
    """Debut de tour -> REACTIVE le passif revive (remet `revive_used_this_turn=False` pour TOUTES les
    unites). Mirror de la RE-ACTIVATION au turn-start de l'effet `ReviveEffect` desactive par `DeactivateEffect`
    apres un revive reussi (i2 « Can only be triggered once per turn »). Meme patron que `reset_times_attacked`
    (per-unite, per-tour). Appele par `start_turn_triggers`."""
    for e in state.entities.values():
        uc = e.get_component(UnitComponent)
        if uc is not None:
            uc.revive_used_this_turn = False
