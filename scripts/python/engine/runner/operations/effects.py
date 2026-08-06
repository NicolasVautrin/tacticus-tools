"""Matérialisation des effets — `IdunBattle.Operations.AddEffectOperation` (gqfc5mff6c).

C'est le CŒUR de la matérialisation : l'opération atomique dans laquelle TOUS les vecteurs de
pose d'effet (à l'ATTAQUE via after-hit trigger, au MOVE via after-move trigger, au CAST d'active,
en début de tour, à la mort) finissent par converger. On porte d'abord cette FEUILLE (RE-first :
porter la feuille propre avant le caller), puis on branchera les vecteurs dessus.

Chaîne native RE'd (VA citées) :

    IdunBattle.Operations.AddEffectOperation$$Execute   (op, source, target, builder, effectType, valuePtr)
      → get_EffectsDatabase → query def par effectType            (record msg 0x3e = pre-add)
      → GATES :
          • target == 0                         → log + abandon
          • **IMMUNITÉ** `def.EntityIsImmuneToEffect(target)` (IEffect slot 40, == le corps de
            `BattleQuery$$IsUnitImmuneTo`) → `return 0` : ni entité-effet ni événement (#224).
            L'ancienne lecture « déjà-présent » de ce gate était FAUSSE (corrigée 2026-07-26).
          • IsUnit(target) && HasFlag(target,6) → **cible MORTE** → log + abandon
            (`IdunBattle.Entities.Enum.UnitFlag` : 6 = `Dead` — l'ancienne lecture « immunité » de ce
             gate etait FAUSSE, corrigee 2026-07-25 depuis le dump d'enums du build)
      → durée = override (valuePtr/param_6) sinon `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$DefaultAmountOfRounds (sinon fallback 1)
      → IdunBattle.Operations.AddEffectOperation$$UpdateExistingEffect : refresh d'un même-type existant → si oui, FIN
        sinon NOUVEAU :
          PlayerIdGenerator.Next → builder(param_4) crée l'entité-effet
          → EffectComponent.Type     @+0x58 = effectType
          → EffectComponent.Duration @+0x68 = durée
          → (parent @+0x70 + liste enfants @+0x78 si effet chaîné)
          → RemoveExistingEffect → IdunBattle.Operations.AddEffectOperation$$AddNewEffect :
              EffectComponent.SourceUnit @+0x10 = source
              EffectComponent.Target     @+0x14 = target
              EffectComponent.TimesApplied @+0x6c = 1   (l'`Active` est @+0x5c — l'ancienne
                 attribution « Active @+0x6c » de cette docstring était FAUSSE : `EffectComponent$$.ctor`
                 initialise @+0x68 (Level) ET @+0x6c (TimesApplied) à 1, et c'est @+0x6c que lisent
                 `BaseEffect$$GetTimesApplied` / `TimesEffectAppliedFormula$$Calculate` — corrigé R9)
              EffectComponent.Value      @+0x60/+0x64 (flag @+0x5d) = valeur (si portée)
              + ajout de l'entité-effet à la liste portée de la cible (EffectsOwnedComponent)
          → record msgs 0x30 (added) / 0x3f
      → record msgs 0x47 / 0x2f (applied)

⚠ PORTAGE STRUCTUREL : le chemin NOUVEAU (effet absent → matérialisé) est porté fidèlement
(champs/durée/registre). Détails non portés : (1) le gate cible-MORTE `HasFlag(target,6)` (redondant
en pratique, cf. le commentaire in-situ) ; (2) le refresh de stack `UpdateExistingEffect` (règles
d'empilement par EffectType) ; (3) la valeur exacte (param_6) qui dépend du builder du vecteur
appelant. Le gate d'IMMUNITÉ, lui, EST porté (#224, `entity_is_immune_to_effect` ci-dessous).
"""
from __future__ import annotations

from typing import Optional

from ..state import State
from ..components import EffectsOwnedComponent, StatsComponent
from ...entities.effect_type import EffectType
from ...entities.effects.base import BaseEffect, SAME_TURNS
from ...entities.effects.factory import EffectFactory
from ...entities.effects import effect_stat_mod_key
from ...entities.stats import StatType
from ..components import ForcedAttackTargetsComponent
from .stat_ops import apply_change_stat
from .stat_ops import apply_stat_override
from .stat_ops import remove_stat_override
from .stat_ops import revert_change_stat

# `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$IsUpdatable` : la fonction
# parcourt les GROUPES d'effets de la table statique et, si le type n'appartient a aucun groupe, sort sur
# `return param_1 != 0x472` -- le SEUL type litteralement non-updatable du build (0x472 = 1138
# `Wraithcannon_NormalAttack`, deja cite tel quel dans `runner/abilities/attack_type.py`).
_EFFECT_NOT_UPDATABLE = EffectType.PowerUp_Armor


# Table `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$DefaultAmountOfRounds (port 1:1 du switch décompilé).
# EffectType (int) → nb de rounds par défaut ; absent = None (Nullable null natif : la durée doit
# alors venir d'un override, sinon fallback 1 dans Execute).
_DEFAULT_ROUNDS: dict[int, int] = {
    EffectType.Cursed: 3,                    # 79   = 0x4f
    EffectType.Pinned: 1,                    # 1065 = 0x429
    EffectType.Stunned: 1,                   # 1162 = 0x48a
    EffectType.Fire: 2,                      # 5    = 0x05
    EffectType.Ice: 2,                       # 17   = 0x11
    EffectType.BrokenIceBlocker: 2,          # 18   = 0x12
    EffectType.Darkness: 2,                  # 58   = 0x3a
    # `Contaminated` : le switch natif
    # `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$DefaultAmountOfRounds`
    # renvoie 2 pour 0x4dc (verifie : `0x4dc >= 0x42a & != 0x48a & == 0x4dc` -> LAB local_res8 = 2),
    # PAS 1 (bug de transcription corrige 2026-07-12, cf. #132).
    EffectType.Contaminated: 2,              # 1244 = 0x4dc
    EffectType.DespoiledGround: 2,           # 1476 = 0x5c4
}


def default_amount_of_rounds(effect_type: int) -> Optional[int]:
    """`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$DefaultAmountOfRounds — durée par défaut (rounds) d'un
    EffectType, ou None si le natif renvoie un Nullable null (la durée vient alors d'un override)."""
    return _DEFAULT_ROUNDS.get(int(effect_type))


# L'AUTRE membre porté de `StaticBattleRules.Effect` — `IsTileStatusEffect` — vit dans
# `engine/services/static_battle_rules.py` : il est consommé par `entities/` ET par `runner/`, et
# `entities/` n'importe jamais `runner/` (cf. le commentaire d'implantation là-bas).


def entity_is_immune_to_effect(state: State, target: int, effect_type: int,
                               *, name: Optional[str] = None) -> bool:
    """`IdunBattle.Core.Services.BattleQuery$$IsUnitImmuneTo(unit, effectType)` — mirror 1:1 :

        effectsDatabase.Get(effectType).EntityIsImmuneToEffect(unit)

    C'est LA façade du gate d'immunité : elle résout l'effet-DEF (`EffectFactory.effect_def`, mirror
    d'`EffectsDatabase.Get`) puis délègue au point d'extension DÉCLARATIF de la classe d'effet. La seule
    part IMPÉRATIVE ici est la lecture des traits de la cible (`StatsComponent.ctx.traits`, côté runner) —
    la logique de trait, elle, vit sur l'effet (`entities/effects/`), jamais dupliquée par appelant.

    Consommateurs : `AddEffectOperation.execute` (gate de pose) et le vecteur tile-effect
    `ContaminatedTileEffect`. Cible sans `StatsComponent` (tuile) → `[]` traits → jamais immune (mirror
    `UnitExtensions.HasTrait` qui passe par `GetBaseUnitComponent`, null ⇒ faux)."""
    from .triggers.base import _unit_trait_names
    return EffectFactory.effect_def(int(effect_type), name).entity_is_immune_to_effect(
        _unit_trait_names(state, int(target)))


class AddEffectOperation:
    """`IdunBattle.Operations.AddEffectOperation` IdunBattle.Operations.AddEffectOperation$$Execute — matérialise un effet sur une cible.

    Feuille partagée par tous les vecteurs de pose. Ici on porte le chemin NOUVEAU (effet absent)
    fidèlement ; gates/refresh/immunité = structure portée + TODO (cf. en-tête de module)."""
    __slots__ = ()

    @staticmethod
    def execute(state: State, source: Optional[int], target: Optional[int], effect_type: int,
                *, name: Optional[str] = None, duration_override: Optional[int] = None,
                value: Optional[int] = None, level: Optional[int] = None,
                ability_level: Optional[int] = None, active_ability_level: Optional[int] = None,
                multiplier_pct: Optional[int] = None,
                bonded: Optional[int] = None,
                active: bool = True) -> Optional[BaseEffect]:
        """Pose l'effet `effect_type` sur `target` (posé par `source`). Renvoie l'effet matérialisé
        (`BaseEffect`) ou None si la pose est abandonnée (pas de cible / déjà présent / pas d'EffectsState).

        `name` = nom d'EffectType (`decisionView.effects[].name`) pour l'enregistrement diffable ;
        `duration_override`/`value` = paramètres du builder du vecteur appelant (param_6 natif).
        `level` = niveau de STACK initial (`EffectComponent.Level @+0x68`) — posé par le seul vecteur
        `IdunBattleLogic.Entities.DSLFactory$$AddEffectOrIncreaseLevel` (branche AddEffect de son lambda `b__0 IdunBattleLogic.Entities.DSLFactory.u003Cu003Ec__DisplayClass569_0$$u003CAddEffectOrIncreaseLevelu003Eb__0`, qui passe
        l'INCRÉMENT comme niveau de la 1re pose) ; None = niveau non porté (tous les autres vecteurs).
        `ability_level`/`active_ability_level`/`multiplier_pct` = paramètres de SCALING de l'effet
        matérialisé (§17.21 — l'équivalent de ce que `EffectsState.seed` fournit aux effets CAPTÉS) : sans
        eux un effet dont la magnitude vient d'un `ConfigVar` reste inerte. Renseignés par les vecteurs qui
        connaissent l'unité de référence ; None = comportement historique (mult 100, niveaux None).
        `bonded` = l'ENTITÉ BONDÉE (`BaseEffect.bonded`) — mirror du champ `+0x10` du composant de bond
        qu'écrit `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$DefaultBondEffectBuilder`. Côté natif
        c'est le BUILDER qui la porte (`GetEffectBuilder` résout le sélecteur `bondedEntity` en id, et
        bascule sur le builder de bond ssi cet id est non nul) ; le port passe l'id résolu ici, l'opération
        n'a qu'à le recopier sur l'instance. None = builder d'effet ORDINAIRE (aucun bond).

        `active` = valeur INITIALE du flag `EffectComponent.IsActive @+0x5c`. NATIVEMENT il naît **FAUX** :
        `IdunBattle.Entities.Components.EffectComponent$$.ctor` écrit `+0x48`/`+0x50`/`+0x78` (listes),
        `+0x68` et `+0x6c` (= 1), et **n'écrit PAS `+0x5c`** — le champ reste zéro-initialisé. C'est le
        premier `IdunBattle.Operations.RefreshEffectsOperation$$RefreshEffect` qui l'active (`= 1`) et qui
        applique la `ValueModification` par `UpdateEffectTargets` → `ApplyEffectsForTargets`. Le défaut
        `True` du port est un RACCOURCI historique (aucun vecteur offline ne rejouait de refresh à la
        pose) : il est conservé pour tous les vecteurs existants, dont la contribution stat est posée
        EAGER par `_apply_stat_mods` juste en dessous. Un vecteur qui veut le chemin NATIF — pose inerte
        puis activation par `refresh_stat_modifier_effects` — passe `active=False` (cas
        `ContagionsOfNurgle_ArmorReduction1/2`, dont les DEUX instances coexistent et dont une seule doit
        porter une modification)."""
        # `On(PreEffectAdded=0x3d=61)` — le natif émet ce message TOUT EN HAUT d'`IdunBattle.Operations.AddEffectOperation$$Execute`
        # (`FUN_1800280e0(0x50, …, 0x3d)` juste après la construction de l'`AbilityEntities`), donc AVANT
        # le gate cible-nulle, AVANT le gate « déjà présent » et AVANT le gate d'immunité : l'événement
        # fire même si la pose est finalement abandonnée (sémantique « would have », cf.
        # TerrifyingCrescendo « would have Suppressed »). Émis ICI, à la MÊME place.
        from .triggers.dispatch.move_death import pre_effect_added_triggers
        pre_effect_added_triggers(state, source, target, int(effect_type))
        # GATE : pas de cible → abandon (Execute log "couldn't apply, no target" puis return 0).
        if target is None:
            return None
        # GATE d'IMMUNITÉ — `effectsDatabase.Get(effectType).EntityIsImmuneToEffect(target)` (interface
        # `IEffect` slot 40 ; le MÊME appel qu'expose `IdunBattle.Core.Services.BattleQuery$$IsUnitImmuneTo`).
        # PLACEMENT = celui du natif : APRÈS le message pre-add 0x3e et le gate cible-nulle, AVANT le gate
        # cible-MORTE et AVANT toute matérialisation. Vrai ⇒ `return 0` : aucune entité-effet, aucun
        # événement d'ajout. Le PRÉDICAT est DÉCLARATIF, porté par la classe d'effet
        # (`BaseEffect.entity_is_immune_to_effect` + surcharges) — jamais recâblé ici.
        # ⚠ L'ABANDON S'ARRÊTE À CETTE OPÉRATION — il ne remonte NI à l'itération du sélecteur-cible NI
        # au combinateur parent. `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$Execute` JETTE la
        # valeur de retour (appel via le slot 0x10 du processeur) et rend un `OperationResult`
        # zéro-initialisé, que `IdunBattle.DSL.CombinedBehaviour$$Execute` lit comme « ne pas
        # court-circuiter » (byte @+0x20). Une chaîne `op_add`/`&` derrière un `AddEffect` refusé
        # CONTINUE donc — MESURÉ (N5, `probe_n5_chain_after_refused_addeffect.py`) : `ExemplarOfHate`
        # sur `blackAbaddon` (`TerminatorArmour`, caster au contact) → `Pinned` refusé MAIS override
        # d'Attack + attaque libre + retrait exécutés, cible 10038 → 7442 HP. L'ancienne lecture
        # inverse (case-224 §5.2, « la branche Chaos entière est absente ») était un CONFOND : aucun
        # attaquant DarkAngels n'était à portée dans ce montage.
        if entity_is_immune_to_effect(state, target, effect_type, name=name):
            return None
        if state.effects is None:
            # Pas d'EffectsState matérialisé (snapshot sans combatSnapshot) → on ne peut pas poser
            # l'effet structuré. Le diff de NOMS (EffectsOwnedComponent) reste possible si présent.
            return None
        # GATE cible MORTE : `IsUnit(target) && HasFlag(target, 6)` — `UnitFlag.Dead` (dump d'enums du
        # build : 0=Moved 1=ArrivedAtFinalTile 2=ActiveAbilityUsed 3=TurnFinished 4=NoActionAvailable
        # 5=Automatic **6=Dead** 8=Overkilled...). L'ancienne lecture « immunité » etait FAUSSE. Non
        # porte ici car REDONDANT en pratique : les vecteurs de pose passent par le dispatch de trigger
        # (gate owner/cible vivant) ou par une ability dont l'acteur est vivant (#70) ; a porter le jour
        # ou un vecteur peut poser un effet sur un cadavre.
        # DURÉE — mirror EXACT de la cascade IdunBattle.Operations.AddEffectOperation$$Execute (lVar14) :
        #   1. `param_6.NullableA.HasValue`  -> la valeur TELLE QUELLE (l'appelant l'a deja convertie ;
        #      c'est `duration_override` ici, exprime en TOURS) ;
        #   2. sinon `DefaultAmountOfRounds(type).HasValue` -> `BattleQuery.ConvertRoundsToTurns(rounds)`
        #      (slot d'interface 0x1b, `FUN_180003b40(0x1b, …, battleQuery, rounds)` du decompile) ;
        #   3. sinon 0 = PERMANENT.
        # La CONVERSION ne porte QUE sur la branche 2 (#98) : c'est litteralement ce que fait le natif.
        # MESURE live PRE-tick (2 unites/camp) : `Pinned 1065` (DefaultAmountOfRounds=1) = remaining 2,
        # `Contaminated 1244` (=2 rounds) = remaining 4 -> facteur = count(joueurs non-Environment) = 2.
        # si les DEUX sont absents → **AUCUNE durée = PERMANENT** (`lVar14 = 0` du natif,
        # observable `remaining = 0`). ⚠ CORRIGÉ : l'ancien fallback `1` faisait EXPIRER au 1er tick tout
        # effet posé sans durée et hors table — GROUND TRUTH LIVE (runner 1181, decisionView.effects) :
        # `MasterAnnihilator_extraHit` posé par l'attaque native de Vitruvius = `remaining 0, level 1`
        # (idem RelentlessMarch_DangerZone / FleshmetalGuns* / AnvilShield_AdditionalBlock / HeavyWeapon_
        # ExtraDmg : TOUS `rem=0, level=1`). Le `1` du décompilé (`local_588[0] = 1`) n'est PAS la durée
        # mais le **NIVEAU** (`EffectComponent.Level @+0x68`, cf. `IncreaseEffectLevelOperation.Execute
        # IdunBattle.Operations.IncreaseEffectLevelOperation$$Execute` qui lit/écrit CE champ comme niveau) — porté ci-dessous par `level`.
        # `remaining = 0` → `EffectFactory.create` mappe rem<=0 → None = permanent (retrait par TRIGGER).
        duration = duration_override
        if duration is None:
            rounds = default_amount_of_rounds(effect_type)
            if rounds is not None:
                from ..abilities.base import convert_rounds_to_turns   # lazy : evite le cycle d'import
                duration = convert_rounds_to_turns(state, rounds)
        if duration is None:
            duration = 0                       # pas de timer -> permanent (mirror `lVar14 = 0`)
        # NIVEAU : `param_6` NullableB sinon **1** (`local_588[0] = 1` IdunBattle.Operations.AddEffectOperation$$Execute) -> `EffectComponent.Level`.
        if level is None:
            level = 1
        # NOUVEL effet : entité-effet via le builder natif (PlayerIdGenerator.Next). Côté Python on
        # matérialise l'instance BaseEffect (via la factory, sous-classe 1:1 si portée). Champs =
        # EffectComponent : Type/Duration/SourceUnit/Target/Value/Active (Active implicite = présent).
        # On la crée AVANT le gate « déjà-présent » pour interroger sa classe (`stacks_stat_mod_on_add`).
        captured = {"name": name or _effect_name(effect_type), "effectType": int(effect_type),
                    "level": level, "remaining": duration, "source": source,
                    "active": bool(active)}
        eff = EffectFactory.create(captured,
                                   ability_variables_multiplier=(100 if multiplier_pct is None
                                                                 else int(multiplier_pct)),
                                   ability_level=ability_level,
                                   active_ability_level=active_ability_level)
        eff.target = target
        eff.value = value
        # `DefaultBondEffectBuilder(id, abilityState, bondedEntityId)` : le champ `+0x10` du composant de
        # bond de l'entite-effet, que relit `IdunBattle.Entities.Effects.ABondEffect$$BondedEntityId`.
        # Ecrit ICI, a la creation de l'entite-effet, exactement comme le natif (le builder EST ce qui
        # construit l'entite). None => builder ordinaire, champ absent.
        eff.bonded = bonded
        # GATE : déjà-présent — pas de re-pose d'un même type non consommé. (Le natif n'a PAS de gate
        # « déjà présent » distinct : il passe par `UpdateExistingEffect` ; ce no-op en est l'équivalent
        # observable, cf. ci-dessous. La query 0x28 qu'on lui attribuait est le gate d'IMMUNITÉ, #224.)
        # ⚠ Le refresh de stack `UpdateExistingEffect` (RE slice-20 Q3 : gate `IsUpdatable(type)` + match
        # effectType+SOURCE) n'est PAS porté ; ici un même-type déjà présent = simple no-op (return None) =
        # refresh-équivalent (mirror suffisant pour les effets UPDATABLE Fire/Pinned/Stunned). EXCEPTION :
        # un effet `stacks_stat_mod_on_add` (ActOfFaith) applique un stat-mod FRAIS à chaque pose → on SKIP
        # le no-op et on matérialise une NOUVELLE instance (reproduit l'observable additif live-validé).
        if not eff.stacks_stat_mod_on_add and state.effects.has_effect(
                target, effect_type=effect_type, name=name):
            # R9 — la SEULE ecriture que `IdunBattle.Operations.AddEffectOperation$$UpdateExistingEffect`
            # fait AVANT tout le reste sur cette voie : `*(int*)(effComp + 0x6c) += 1` (le compteur
            # `TimesApplied`, cf. `BaseEffect.times_applied`). Le no-op ci-dessus est l'equivalent
            # observable du refresh POUR LA DUREE/LE NIVEAU ; il perdait le COMPTEUR, et c'est lui que
            # multiplie `Chronometron_ExtraDamage`. On l'incremente donc sur l'instance deja portee, en
            # mirror des DEUX gates natifs restants : type identique (`EffectComponent.Type @+0x58`) et
            # meme effet PARENT (`@+0x70`) — le gate `IsUpdatable(type)` etant vrai pour tout type sauf
            # `0x472` (`idun.…StaticBattleRules.Effect$$IsUpdatable` : `return param_1 != 0x472` en
            # sortie de boucle). Inerte pour tout effet qui ne lit pas `times_applied`.
            if int(effect_type) != _EFFECT_NOT_UPDATABLE:
                for _e in state.effects.by_unit.get(int(target), []):
                    if (not _e.consumed and _e.effect_type == effect_type
                            and _e.parent_type == eff.parent_type):
                        _e.times_applied = int(_e.times_applied or 1) + 1
                        break
            return None
        # AddNewEffect : enregistrement sur la cible (liste structurée + liste de NOMS diffable).
        state.effects.add_effect(target, eff)
        _register_name(state, target, eff.name)
        # `AStatModifierEffect.ApplyInternal → ApplyModification` (vtable 0x728, RE slice-20 Q4) : applique
        # les ChangeStat déclarés par l'effet (part DATA `applied_stat_mods`). Séparé d'`AddNewEffect` (pure
        # matérialisation ECS) côté natif → séparé ici aussi (frontière déclaratif feuille / impératif op).
        AddEffectOperation._apply_stat_mods(state, target, eff)
        # `<Effect>.ApplyInternal` part OVERRIDE (MV71 InitialDmg IdunBattle.Entities.Effects.Loki.MV71SniperDroneSquad_InitialDmgEffect$$ApplyInternal) : overrides part 7 aux
        # valeurs CURRENT du PARENT (= la source de la pose), snapshotées ICI (nœud Direct évalué à l'apply).
        AddEffectOperation._apply_stat_overrides(state, target, eff)
        # `<Effect>.ApplyInternal` part MODIFICATIONS D'ABILITY (`AddUnitActiveAbilityModification`) :
        # ecrit des deltas de CONSTANTES d'ability sur les cibles du `CreateTargetSelector` de l'effet
        # (qui peut viser une AUTRE unite que le porteur — `ListenUpMaggotsEffect` = `Parent(Self)`).
        from .ability_modifications import apply_ability_modifications
        apply_ability_modifications(state, target, eff)
        # Effet COMPOSITE : `<Effect>.ApplyInternal` spawne ses SOUS-effets (enfants) juste après le
        # parent (ex. Stunned 1162 → 1165/1166/1167). Effet-driven : la liste vient de la classe d'effet.
        AddEffectOperation._spawn_sub_effects(state, source, target, eff)
        # `<Effect>.ApplyInternal` part CIBLES D'ATTAQUE FORCÉES (le TAUNT) — placée ICI parce que le
        # natif l'écrit APRÈS ses trois `AddSubEffectWithSameTurns`
        # (`IdunBattle.Entities.Effects.TauntedEffect$$ApplyInternal`).
        AddEffectOperation._apply_forced_attack_targets(state, target, eff)
        return eff

    @staticmethod
    def _apply_stat_mods(state: State, target: int, eff: BaseEffect) -> None:
        """Mirror `AStatModifierEffect.ApplyInternal → ApplyModification` (vtable 0x728) : EXÉCUTE les
        `(StatType, montant)` déclarés par l'effet (`applied_stat_mods`, DATA côté `entities/`) via l'op
        runner `apply_change_stat`, keyés par une source UNIQUE par instance (revert par-source exact via la
        feuille `RemoveEffect`, symétrique de `reverted_stats()`). No-op si l'effet ne déclare aucun stat-mod
        (effet non StatModifier) ou si la cible n'a pas de `StatsComponent`. Stocke `stat_mod_source` sur
        l'effet (clé du revert). La source unique = `(effectType, target, nb de stacks actifs du même type)`
        → chaque instance revert exactement SON delta."""
        ent = state.get_entity(target)
        sc = ent.get_component(StatsComponent) if ent is not None else None
        if sc is None:
            return
        mods = eff.applied_stat_mods(sc.ctx) or []
        if not mods:
            return
        # source unique par instance : indexée par le nb de stacks du même type DÉJÀ actifs (hors `eff`
        # lui-même, déjà ajouté à la liste) → une clé distincte par stack pour un revert par-source exact.
        stack_n = sum(1 for e in state.effects.by_unit.get(int(target), [])
                      if (not e.consumed) and e.effect_type == eff.effect_type and e is not eff)
        src = (int(eff.effect_type), int(target), stack_n)
        for stat, amount in mods:
            apply_change_stat(state, target, int(stat), src, int(amount))
        eff.stat_mod_source = src

    @staticmethod
    def _apply_stat_overrides(state: State, target: int, eff: BaseEffect) -> None:
        """Mirror `IdunBattle.Entities.Effects.Loki.MV71SniperDroneSquad_InitialDmgEffect$$ApplyInternal` : pour chaque StatType
        déclaré par l'effet (`overridden_stats()`, DATA côté `entities/`), lit `GetStat(parent, stat,
        CURRENT)` — **parent = `eff.source`** (la pose native passe `AbilityStateReference` = le caster,
        qui EST le `GetParentUnit(drone)` : Unit_Parent_Id = casterId, GT case-61bis §2) — et pose
        l'OVERRIDE (part 7, `apply_stat_override`, modifiable). Valeurs SNAPSHOTÉES à l'apply (nœud
        `Direct(...)` natif évalué à l'exécution du ChangeStat). Stocke `stat_override_stats` sur
        l'instance (la liste que le retrait reverte via `remove_stat_override`, part 8 — mirror
        `IdunBattle.Entities.Effects.Loki.MV71SniperDroneSquad_InitialDmgEffect$$RevertInternal`). No-op si l'effet ne déclare aucun override / parent sans stats."""
        stats = eff.overridden_stats() or []
        if not stats:
            return
        src = eff.source
        pe = state.get_entity(src) if src is not None else None
        psc = pe.get_component(StatsComponent) if pe is not None else None
        pus = getattr(psc.ctx, "stats", None) if psc is not None else None
        if pus is None:
            return
        applied = []
        for st in stats:
            val = pus.get_stat(int(st), 0)                 # GetStat(parent, stat, CURRENT) — snapshot
            apply_stat_override(state, target, int(st), int(val), is_modifiable=True)
            applied.append(int(st))
        eff.stat_override_stats = applied

    @staticmethod
    def revert_stat_overrides(state: State, target: int, eff: BaseEffect) -> None:
        """Mirror `IdunBattle.Entities.Effects.Loki.MV71SniperDroneSquad_InitialDmgEffect$$RevertInternal` = `IdunBattle.Entities.Effects.Loki.MV71SniperDroneSquad_InitialDmgEffect$$ResetStat` ×N (part 8 = REMOVE_OVERRIDE) :
        retire les overrides posés par `_apply_stat_overrides` (liste `stat_override_stats` de
        l'instance). Appelé à la CONSOMMATION de l'effet (ex. TargetTrigger `On(AttackDamageAttack)&
        OwnerIsCaster` de MV71 InitialDmg, exécuté par l'ability après l'attaque commandée).

        VOLET `ACTIVE_ABILITY_LEVEL` (#114 résidu 2) : la feuille `AddStatOverrideEffect` écrit CE stat
        dans `UnitContext.active_ability_level` en plus du `UnitStats` — c'est le seul canal que lisent
        `ability_var` / `ability_attack_params`, donc le seul mirror OBSERVABLE de
        `GetStat(unit, ACTIVE_ABILITY_LEVEL)` — et mémorise la valeur précédente dans
        `overridden_prev`. Le `ResetStat` (part 8) doit donc la RESTAURER symétriquement, sinon le
        retrait de `InspiredToGreatness_OverrideLevel` (1180) laisserait le niveau plafonné à vie."""
        stats = getattr(eff, "stat_override_stats", None) or []
        for st in stats:
            remove_stat_override(state, target, int(st))
        if int(StatType.ACTIVE_ABILITY_LEVEL) in [int(s) for s in stats] \
                and hasattr(eff, "overridden_prev"):
            te = state.get_entity(int(target))
            tsc = te.get_component(StatsComponent) if te is not None else None
            if tsc is not None and tsc.ctx is not None:
                tsc.ctx.active_ability_level = eff.overridden_prev
        eff.stat_override_stats = []

    @staticmethod
    def _apply_forced_attack_targets(state: State, target: int, eff: BaseEffect) -> None:
        """Queue d'`IdunBattle.Entities.Effects.TauntedEffect$$ApplyInternal` — MIRROR :

            comp = target.GetComponent<ForcedAttackTargetsComponent>();
            list = new List<int>(); list.Add(ABondEffect.BondedEntityId(this, effect));
            comp.<+0x50> = list;                                  // REMPLACE la liste

        Gate = la part DATA `BaseEffect.writes_forced_attack_targets()` (seul `TauntedEffect` la
        pose). La VALEUR est le `BondedEntityId` de l'instance = `eff.bonded`.

        `eff.bonded is None` -> **AUCUNE écriture**, et c'est un choix. Le natif rendrait `0` (le
        `BondedEntityId` d'un effet sans `BondComponent` : branche `else` du décompilé, qui LOGGUE
        une erreur puis rend `0`) et poserait donc la liste `[0]`, c'est-à-dire une restriction que
        AUCUNE entité ne satisfait -> tout cast refusé. Reproduire ce `[0]` sur un call-site du port
        dont le `bondedEntity` n'a simplement pas encore été RE-lu fabriquerait un refus universel
        à partir d'une donnée manquante. Les deux call-sites portés de l'effet 27 renseignent leur
        bonded (relu au décompilé : `CrushingClawsAbility$$ExecuteBehaviour` et
        `GetEmRuntzAbility$$TauntWithNewChildrenWhoDidDamage` passent tous deux le sélecteur du
        TAUNTANT en 5e argument d'`IdunBattleLogic.Entities.DSLBehaviors$$AddBondEffect`), donc
        cette branche ne mord sur aucun d'eux.

        Le composant est CRÉÉ à la demande (le natif l'a par blueprint sur toute unité ; offline il
        n'existe que là où une écriture a eu lieu — `GetOnlyTargets` traite son absence comme la
        liste vide, exactement comme le `TryGetComponent` faux du natif)."""
        if not eff.writes_forced_attack_targets():
            return
        bonded = getattr(eff, "bonded", None)
        if bonded is None:
            return
        ent = state.get_entity(int(target))
        if ent is None:
            return
        comp = ent.get_component(ForcedAttackTargetsComponent)
        if comp is None:
            comp = ForcedAttackTargetsComponent()
            ent.add_component(comp)
        comp.set_from_effect(eff, [int(bonded)])

    @staticmethod
    def _spawn_sub_effects(state: State, source: Optional[int], target: int,
                           parent: BaseEffect) -> None:
        """Matérialise les sous-effets déclarés par `parent.sub_effects_on_apply()` (mirror des
        `Add*SubEffect`/`AddEffect` de `ApplyInternal`). Durée : SAME_TURNS → durée du parent ;
        0/None → permanent (lié au parent, rem=0 natif) ; N>0 → N. Chaque enfant porte
        `parent_type` (lien `ParentEffect@+0x70`). Enfants déjà présents = skip (idempotent)."""
        for spec in parent.sub_effects_on_apply():
            if state.effects.has_effect(target, effect_type=spec.effect_type, name=spec.name):
                continue
            if spec.turns == SAME_TURNS:
                rem = parent.remaining_turns
            elif spec.turns and int(spec.turns) > 0:
                rem = int(spec.turns)
            else:
                rem = None          # 0/None natif = permanent, lié au cycle de vie du parent
            child = EffectFactory.create({"name": spec.name, "effectType": int(spec.effect_type),
                                          "level": None, "remaining": rem, "source": source})
            child.target = target
            child.parent_type = parent.effect_type
            state.effects.add_effect(target, child)
            _register_name(state, target, child.name)


class ChangeEffectTurnsOperation:
    """`IdunBattle.Operations.ChangeEffectTurnsOperation$$Execute(effectEntity, amount, changeType)` — MIRROR :

        comp = effectEntity.GetComponent<EffectComponent>()          ; null -> abandon
        if (!comp.HasTurns @+0x5d)  { log("...") ; return }          # effet SANS timer -> no-op journalise
        cur = comp.Duration @+0x64
        new = max(0, BattleQuery.GetAmount(cur, amount, changeType)) # `IdunBattle.Core.Services.BattleQuery$$GetAmount`
        comp.Duration @+0x64 = new
        -> events UpdateEffectTurns (0x14/0x16) + `RefreshEffectOptions(0, 4, 0, 0, 0)`

    `IdunBattle.Core.Services.BattleQuery$$GetAmount(current, amount, changeType)` (mirror EXACT) :
    `IdunBattle.Entities.Enum.ChangeType` **0 = Add** (`current + amount`), **1 = Set** (`amount`) ; toute
    autre valeur -> `ArgumentOutOfRangeException` native.

    Port : `effect` = l'instance `BaseEffect` materialisee (`EffectsState`), son `remaining_turns` EST le
    `EffectComponent.Duration`. `remaining_turns is None` = effet PERMANENT (le natif : `HasTurns == 0`)
    -> **no-op**, mirror de la branche de log. Retour = la nouvelle duree, ou None si l'op a abandonne."""
    __slots__ = ()

    CHANGE_ADD = 0                                       # IdunBattle.Entities.Enum.ChangeType.Add
    CHANGE_SET = 1                                       # IdunBattle.Entities.Enum.ChangeType.Set

    @staticmethod
    def get_amount(current: int, amount: int, change_type: int) -> int:
        """`IdunBattle.Core.Services.BattleQuery$$GetAmount` — mirror 1:1 (Add=0 / Set=1)."""
        ct = int(change_type)
        if ct == ChangeEffectTurnsOperation.CHANGE_ADD:
            return int(current) + int(amount)
        if ct == ChangeEffectTurnsOperation.CHANGE_SET:
            return int(amount)
        raise ValueError(f"ChangeType hors domaine: {ct}")   # mirror ArgumentOutOfRangeException

    @staticmethod
    def execute(state: State, effect: BaseEffect, amount: int,
                change_type: int = 0) -> Optional[int]:
        if effect is None or effect.remaining_turns is None:
            return None                                  # `HasTurns == 0` -> log + return (no-op)
        new = ChangeEffectTurnsOperation.get_amount(effect.remaining_turns, amount, change_type)
        effect.remaining_turns = max(0, new)             # `if (-1 < iVar4) iVar11 = iVar4` = clamp >= 0
        return effect.remaining_turns


def revert_stat_mods_of_removed_effects(state: State) -> list:
    """Mirror `IdunBattle.Entities.Effects.AStatModifierEffect$$RevertModification` (ChangeStat part 6) au
    RETRAIT d'un effet : quand une instance qui a APPLIQUE une `ValueModification` est retiree — expiree
    par son timer OU consommee — sa contribution doit SORTIR du `UnitStats`.

    Cote natif c'est `IdunBattle.Operations.RemoveEffectOperation$$Execute` ->
    `IdunBattle.Operations.RefreshEffectsOperation$$DeactivateEffect` ->
    `IdunBattle.Operations.RefreshEffectsOperation$$RevertEffectsForTargets` -> le virtuel `RevertInternal`
    de l'effet, qui pour la famille `AStatModifierEffect` EST `RevertModification` :
    `ChangeStat(Entity(target), Position(stat, part 6), 4, <noeud vide>, Entity(<effectEntity>))` ->
    `IdunBattle.Entities.Components.ValueModification$$ReverseModification` retire la contribution de
    l'entite-effet. Il n'y a AUCUNE voie native ou un effet a stat-mod disparait en laissant sa
    contribution : la source est l'entite-effet, elle part avec elle.

    CLE = `effect_stat_mod_key(e)` (cf. `entities/effects/__init__.py`) : la cle de POSE si un chemin
    offline l'a renseignee, SINON la cle DERIVEE `statmod_source_key` — celle sous laquelle
    l'ATTRIBUTION DU SEED (`stat_modifications_by_source` -> `seed_unit_stats(attributed=...)`) a ecrit la
    contribution d'un effet CAPTE. C'est le correctif #118 : avant, ce foyer exigeait un
    `stat_mod_source` et ne faisait donc **strictement rien** pour un effet SEEDE — un stat-mod a TIMER
    deja actif au chargement du `State` (ex. `ThrillSeekers` 1434, +15 CritChance) restait applique POUR
    TOUJOURS alors que le live le retire a l'expiration.

    R16 : #118 n'avait ferme QUE la forme MONO-STAT de la base. Les effets dont `ApplyModification` est
    OVERRIDE (magnitude lue sur le `StatsComponent.ctx` du porteur : `ActOfFaithBuffEffect`,
    `ProtectorImperativeEffect`, `AncestralFortune*`, `AugmentedAssault_ReduceArmor`,
    `BlackRage_ExtraMove`, `Waaagh_ExtraMovement`) tombaient dans le MEME trou, par les DEUX bouts :
    l'attribution du seed ne les voyait pas (leur contribution restait dans le residu opaque) et
    `effect_stat_mod_key` rendait `None` (discriminant `get_stat_modification_stat`). Les deux bouts sont
    fermes : l'attribution passe par `effect_stat_modifications` (point de verite unique des DEUX formes
    natives) et le discriminant est `reverted_stats()`. Mesure : `probe_r16_eager_statmod_revert.py`.

    CROISEMENT avec le retrait a echeance (O3) : le gate d'entree est `consumed OR expired`, donc ce
    foyer voyait DEJA une instance dont le timer venait d'atteindre 0 — le passage de `expired` seul a
    `expired ET consumed` ne change NI le tour NI le nombre de reverts. L'appelant
    (`EndTurnOperation.execute`) tick d'abord toutes les entites puis appelle ce foyer : la contribution
    sort donc dans le MEME passage que l'effet, mirror de `EndTurnOperation$$RefreshEffects` qui enfile
    `RefreshEffect` (branche de retrait -> virtuel `RevertInternal`). Le seul membre du gisement EAGER a
    porter un vrai timer est `Waaagh_ExtraMovement` (0x44b=1099, `duree@dsl+0xc0 = Direct(1)`) ; les
    autres sont PERMANENTS et partent par une feuille `RemoveEffect`. Garde :
    `tests/engine/runner/test_seeded_eager_statmod_expiry.py`.

    Idempotent : `stat_mod_reverted` marque l'instance (et `stat_mod_source` est efface quand il existait).
    UNE SEULE fois, quel que soit l'ordre des deux foyers de retrait : la feuille `RemoveEffect` skippe
    d'emblee un effet deja `consumed`, ce foyer skippe une instance deja `stat_mod_reverted`, et
    `ValueModification$$ReverseModification` retire UNE cle (un 2e passage est structurellement un no-op).
    Sans rapport avec le compteur `TimesApplied @+0x6c` de `UpdateExistingEffect` (R9), qui vit sur
    l'AUTRE voie du gate « deja-present » d'`AddEffectOperation.execute` (celle qui `return None` sans
    jamais materialiser ni appliquer de stat-mod).
    Renvoie la liste des `(unit, effect_type, stat)` revertes — diagnostic."""
    out: list = []
    if state.effects is None:
        return out
    for uid, effs in state.effects.by_unit.items():
        for e in effs:
            if not (e.consumed or e.expired):
                continue
            if e.stat_mod_reverted:
                continue                                 # deja reverte (pas de re-listing a chaque tick)
            src = effect_stat_mod_key(e)
            if src is None:
                continue
            for stat in (e.reverted_stats() or []):
                revert_change_stat(state, int(uid), int(stat), src)
                out.append((int(uid), e.effect_type, int(stat)))
            e.stat_mod_source = None                     # idempotence (pas de double ReverseModification)
            e.stat_mod_reverted = True
    return out


def _effect_name(effect_type: int) -> str:
    """Nom lisible de repli quand le vecteur appelant ne fournit pas le nom d'EffectType (la table
    enum int→nom vit côté hooks `ability-names`/`effect-names` ; offline on garde le type brut)."""
    return f"Effect_{int(effect_type)}"


def _register_name(state: State, target: int, name: Optional[str]) -> None:
    """Ajoute `name` à l'`EffectsOwnedComponent` de la cible (liste de NOMS triée, base du diff
    structurel d'effets). Crée le composant s'il manque. No-op si pas d'entité/nom."""
    if not name:
        return
    ent = state.get_entity(target)
    if ent is None:
        return
    comp = ent.get_component(EffectsOwnedComponent)
    if comp is None:
        comp = ent.add_component(EffectsOwnedComponent(effects=[]))
    if name not in comp.effects:
        comp.effects.append(name)
        comp.effects.sort()


def unregister_name(state: State, target: int, name: Optional[str]) -> None:
    """SYMETRIQUE de `_register_name` : retire `name` de l'`EffectsOwnedComponent` de la cible quand
    plus AUCUNE instance non consommee de ce nom n'y reste. Mirror de `IdunBattle.Operations.
    RemoveEffectOperation$$Execute`, qui retire l'id de l'entite-effet de `EffectsOwnedComponent.
    ActiveEffectIds` — sans quoi un effet POSE PUIS RETIRE dans le meme cast (couples transitoires
    `AddStatOverrideEffect(0x510)`/`RemoveEffect(0x510)`, `AddEffect(0x529 ForcedInMelee)`/
    `RemoveEffect(0x529)` de TheQuickening, reset ActOfFaith...) laisserait son NOM colle sur l'unite,
    alors que la mesure live dit « net-zero, aucun effet persistant ». Le canal des NOMS est LU par la
    couche decision (`ai/state_bridge.py` gates d'effets, `playbook/scene.py`) — une fuite y est
    observable. No-op si pas d'entite/nom/composant."""
    if not name:
        return
    ent = state.get_entity(target)
    if ent is None:
        return
    comp = ent.get_component(EffectsOwnedComponent)
    if comp is None or name not in comp.effects:
        return
    if state.effects is not None and any(
            (not e.consumed) and e.name == name
            for e in state.effects.by_unit.get(int(target), [])):
        return                                   # un autre stack du MEME nom reste actif -> on garde
    comp.effects.remove(name)
