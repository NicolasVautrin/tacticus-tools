"""`IdunBattle.Operations.RefreshEffectsOperation` — ACTIVATION / DESACTIVATION des effets selon leur
`CreateActiveCondition`, et propagation sur les `AStatModifierEffect` (#100).

Chaine native RE'd (build gqfc5mff6c) :

    IdunBattle.Operations.RefreshEffectsOperation$$DeactivateEffect
        if (EffectComponent+0x5c == 0) return ;              # deja inactif -> no-op
        EffectComponent+0x5c = 0 ; UpdateEffectTargets(...)  # +0x5c = le flag IsActive
    IdunBattle.Operations.ActivateEffectOperation$$Execute / DeactivateEffectOperation$$Execute
    IdunBattle.Entities.Effects.AStatModifierEffect$$ApplyModification   -> ChangeStat(part 5) = +montant
    IdunBattle.Entities.Effects.AStatModifierEffect$$RevertModification  -> ChangeStat(part 6) = retrait
    IdunBattle.Entities.Effects.ADynamicStatModifierEffect$$RefreshValueInternal = Revert puis Apply

Le flag `+0x5c` est CE QUE LIT le gate `HasEffect(..., activeOnly=1)` :
`IdunBattle.Entities.EntityExtensions$$IsOwnerOfEffect` skippe toute entree dont `+0x5c == 0` quand son
4e argument est non nul (et TOUS les `DSLFactory$$HasEffect` du cluster AnvilShield passent 1).

## Pourquoi ce driver

Le port evalue `is_active()` A LA LECTURE (predicats/consommateurs) — c'est suffisant pour les GATES.
Mais la **contribution STAT** d'un `AStatModifierEffect` conditionnel doit, elle, entrer et sortir du
`UnitStats` quand la condition bascule : c'est exactement ce que fait `RefreshEffectsOperation` cote
natif. Cas porte : `AnvilShield_BlockChanceBelowHealthCap` (1200) dont l'`ActiveCondition` est
`healthPct(35) >= GetStat(HEALTH, CURRENT_PCT)` -> `blockChance` d'Arjac passe 0 -> 20 quand il tombe
sous 35 % PV (GROUND TRUTH LIVE #100), et redescend s'il repasse au-dessus.

## Perimetre (blast radius NUL par construction)

`refresh_stat_modifier_effects` ne touche QUE les effets qui :
  1. modifient au moins un stat -- soit par le canal ADDITIF (`effect_stat_modifications`, le point
     de verite UNIQUE R16 : la base `get_stat_modification_*` ET l'override `applied_stat_mods(ctx)`
     a magnitude contextuelle), soit par le canal OVERRIDE (`effect_stat_overrides`, part 7/8 --
     `IdunBattle.Entities.Effects.StatOverrideEffect`). Les DEUX sont pilotes par le MEME couple de
     slots d'interface (`IEffect+0xe`/`+0xf` = `BaseEffect$$Apply`/`$$Revert`), donc par le MEME
     verdict `ShouldBeActive` : le driver les traite ensemble, ET
  2. n'ont AUCUNE cle de POSE (`stat_mod_source is None`) -- c'est-a-dire qu'aucun chemin OFFLINE
     (`AddEffectOperation._apply_stat_mods`, feuille `AddStaticStatModifierEffect`) n'a deja pose
     leur contribution sous SA propre cle. Ceux-la sont poses/revertes par leur poseur et par la
     feuille `RemoveEffect`, donc SKIPPES ici.

⚠ Le discriminant du skip est la **cle**, pas la METHODE declaree (#cvc). Il etait « l'effet
declare-t-il `applied_stat_mods` ? » -- ce qui excluait du driver TOUT effet a magnitude
contextuelle, y compris quand il est SEEDE (donc sans cle de pose) et que sa contribution est
attribuee par la passe 2 du seed sous `statmod_source_key`. Consequence MESUREE : la contribution
d'un tel effet ne pouvait plus jamais etre retiree quand sa `CreateActiveCondition` tombait.
⚠ NE PAS FIGER ICI de compte ni de liste (meme raison qu'au bloc `_active_condition_is_ported`
plus bas : ils se periment a chaque port et causent mecaniquement un conflit de rebase par PR).
Deux regimes, et c'est LA distinction qui compte : une classe qui declare `applied_stat_mods`
SANS surcharger `is_active` rend `True` par defaut, donc le driver re-ecrit EXACTEMENT la valeur
que la passe 2 du seed a deja posee sous la MEME cle (`Modify` = replace par-source) : no-op exact.
Une classe qui declare les DEUX (le premier cas est `ReinforcedHiveNode_ExtraArmor`, #366-r1) a sa
`CreateActiveCondition` PORTEE : la re-evaluation est alors l'effet VOULU. Dans les deux cas
l'instance doit etre SEEDEE (`stat_mod_source is None`) pour ne pas etre skippee -- une instance
posee OFFLINE porte deja sa contribution sous SA cle et sort du perimetre du driver.

La cle de source utilisee est **exactement celle de l'instance** (`effect_stat_mod_key` : la cle de POSE
si un chemin offline l'a renseignee, sinon la cle DERIVEE `statmod_source_key` = celle du seed) et
`ValueModification.Modify` est un **replace par-source** -> re-appliquer la meme valeur est un NO-OP
exact. Seule la bascule `is_active() == False` change quelque chose (retrait de la contribution).

## Le FLAG `EffectComponent.IsActive @+0x5c` a desormais son PRODUCTEUR (#cvc)

`IdunBattle.Operations.RefreshEffectsOperation$$RefreshEffect` ECRIT le flag a chaque refresh :
`ActivateEffect` le met a 1, `DeactivateEffect` a 0 (et enchaine `UpdateEffectTargets([])`, donc
`RevertEffectsForTargets` -> `RevertModification`). Cote port le champ `BaseEffect.active` existait
depuis #138 et etait SEEDE par #219 -- mais **rien ne l'ecrivait ensuite** : un effet capte INERTE
le restait a vie, et un effet capte ACTIF ne pouvait pas s'eteindre. Ce driver est ce producteur.
Il n'ecrit QUE les effets qu'il traite (ceux du perimetre ci-dessus), et `active_effects` continue
de lire la CONJONCTION `e.active and e.is_active(unit_state)` -- flag ET condition, comme le natif.

⚠ POURQUOI LA CLE D'INSTANCE ET PAS `statmod_source_key` EN DUR (#118) : le natif n'a qu'UNE entree
`ValueModification.per_source` par entite-effet (la source du `ChangeStat` EST l'entite-effet, cf.
`IdunBattle.Entities.Effects.AStatModifierEffect$$ApplyModification`). Un effet pose par la feuille
`AddStaticStatModifierEffect` porte deja sa contribution sous SA cle de pose ; si ce driver en creait une
SECONDE sous la cle derivee, la contribution serait comptee DEUX FOIS (cas concret : `ThrillSeekers` 1434
pose en combat puis un `refresh` declenche par le degat suivant -> +30 CritChance au lieu de +15).
"""
from __future__ import annotations

from typing import Optional

from ..state import State
from ..components import (StatsComponent, enemy_psykers_alive as _enemy_psykers_alive,
                          unit_state_for_effects)
from ...entities.effects import (effect_stat_mod_key, effect_stat_modifications,
                                 effect_stat_overrides)
from ...entities.effects.base import BaseEffect

# `_enemy_psykers_alive` / `_unit_state` : le CORPS vit dans `runner/components.py` (`enemy_psykers_alive`
# / `unit_state_for_effects`) depuis #208 — foyer UNIQUE du contexte d'évaluation des
# `CreateActiveCondition`, atteignable par TOUS les appelants d'`active_effects` sans cycle d'import
# (`components` n'importe que `state`). Les deux noms restent exportés ici : c'est la face
# `RefreshEffectsOperation` de la même donnée, et des tests/probes les importent sous ces noms.
_unit_state = unit_state_for_effects
__all__ = ["refresh_stat_modifier_effects", "_unit_state", "_enemy_psykers_alive",
           "_active_condition_is_ported"]


def _active_condition_is_ported(effect) -> bool:
    """La `CreateActiveCondition` de CETTE classe d'effet est-elle REELLEMENT portee ?

    = la classe SURCHARGE-t-elle `is_active` ? `BaseEffect.is_active` rend `True`
    INCONDITIONNELLEMENT : c'est une valeur PAR DEFAUT (« aucune condition lue »), pas une lecture
    du natif. Le distinguer est ce qui autorise `refresh_stat_modifier_effects` a ECRIRE le flag
    `EffectComponent.IsActive @+0x5c` — on ne re-evalue que ce qu'on sait lire (cf. le bloc de
    commentaire du driver pour le decompile et les deux mesures live qui ancrent les deux branches).

    ⚠ NE PAS confondre avec `BaseEffect.active_condition_ported`, qui repond a une AUTRE question
    (« le flag CAPTE au seed est-il PERIME pour un effet dont la condition porte sur l'etat SIMULE ? »,
    case-322) et n'est pose que par UNE classe, alors que **13** surchargent `is_active`. Les
    confondre VERROUILLE les 12 autres : une instance seedee INACTIVE ne peut plus se rallumer quand
    sa condition portee devient vraie (mesure : `test_contagions_lifecycle_live`, l'aura qui grandit).

    Resolution par MRO (`type(e).is_active`), donc une surcharge posee sur une base intermediaire
    compte aussi."""
    return type(effect).is_active is not BaseEffect.is_active


def refresh_stat_modifier_effects(state: State, unit_id: Optional[int] = None) -> list:
    """Mirror `RefreshEffectsOperation` (volet stat) : pour chaque effet DECLARATIF a stat porte par
    `unit_id` (ou par TOUTES les unites si None), applique sa contribution si son `ActiveCondition`
    est vraie, la reverte sinon — sur les DEUX canaux natifs, l'ADDITIF (part 5|9 / part 6) et
    l'OVERRIDE (part 7 / part 8). Renvoie la liste des `(unit, stat, valeur|None)` effectivement
    (re)ecrits — diagnostic (`None` = revert/retrait).

    Idempotent : meme cle de source que l'attribution du seed + `Modify` = replace par-source pour
    l'additif ; `SetOverride` ECRASE l'unique slot `ValueOverride` du stat pour l'override."""
    out: list = []
    if state.effects is None:
        return out
    uids = [int(unit_id)] if unit_id is not None else list(state.effects.by_unit.keys())
    for uid in uids:
        effs = state.effects.by_unit.get(int(uid))
        if not effs:
            continue
        ent = state.get_entity(uid)
        sc = ent.get_component(StatsComponent) if ent is not None else None
        us = getattr(sc.ctx, "stats", None) if sc is not None else None
        if us is None:
            continue
        ustate = _unit_state(state, uid)
        ctx = getattr(sc, "ctx", None)
        for e in effs:
            if e.consumed or e.expired:
                continue
            if e.stat_mod_source is not None:
                continue                      # pose EAGER offline sous SA cle : hors driver (cf. en-tete)
            # ORDRE : le FLAG d'abord (mirror `ActivateEffect`/`DeactivateEffect`, qui ecrivent
            # `EffectComponent.IsActive @+0x5c` AVANT que `UpdateEffectTargets` ne joue les
            # `Apply`/`RevertModification`). Les magnitudes contextuelles peuvent LIRE ce flag.
            #
            # ⚠ MAIS ON N'ECRIT PAS UN DEFAUT PAR-DESSUS UNE MESURE (#366-r1b). Le natif
            # `IdunBattle.Operations.RefreshEffectsOperation$$ShouldBeActive`, branche
            # `refreshType == Normal`, lu VERBATIM :
            #
            #     if (effectComponent.<+0x5e>)                  return false;
            #     if (!effect.ShouldRefreshForTrigger(trigger))  return effectComponent.<+0x5c>;
            #     return effect.ShouldBeActive(entities);        // = `CreateActiveCondition`
            #
            # -> le natif a DEUX regimes : re-evaluer la condition, ou **RENVOYER LE FLAG COURANT**.
            # Le port n'a NI `RefreshEffectTrigger` NI `ShouldRefreshForTrigger` : il ne peut pas
            # decider QUAND le natif re-evalue. Il decide donc sur ce qu'il PEUT lire -- a-t-il, oui
            # ou non, un port de la `CreateActiveCondition` de cette classe ?
            #
            #   * OUI (la classe SURCHARGE `is_active`) -> on tient une LECTURE du natif : on
            #     re-evalue et on ECRIT le flag, exactement comme avant #366-r1b.
            #     ⚠ NE JAMAIS FIGER ICI NI UN COMPTE NI LA LISTE DES CLASSES : les deux se
            #     PERIMENT a chaque port qui entre une classe surchargeante, et ils sont la CAUSE
            #     MECANIQUE d'un conflit de rebase par PR -- #366-r1 (`PsychicStalk_VisualEffect`)
            #     et #424 (`MartialSuperiority_Visual`) ont reecrit ce meme bloc en parallele. Le
            #     compte annonçait « 13 » quand `CamoCloak_DmgReduction` etait deja entree, puis « 15 »
            #     quand le seul rebase en avait deja fait 17 : un chiffre ecrit ici est faux AVANT
            #     d'etre merge. L'ensemble se RE-DERIVE, en une expression :
            #         {n for n, c in EFFECT_CLASSES.items() if c.is_active is not BaseEffect.is_active}
            #     Le cliquet qui le tient -- et qui re-derive son propre plancher au lieu de le
            #     recopier -- est `test_refresh_active_flag_discriminant_offline`.
            #   * NON -> `BaseEffect.is_active` rend `True` INCONDITIONNELLEMENT : c'est une VALEUR
            #     PAR DEFAUT, pas une lecture. L'ecrire ECRASERAIT le flag que
            #     `ActivateEffect`/`DeactivateEffect` viennent de poser. On CONSERVE donc le flag et
            #     on conjugue -- c'est aussi ce que fait la branche « je ne re-evalue pas » du natif.
            #
            # ⚠ LE DISCRIMINANT N'EST PAS `active_condition_ported` : ce drapeau repond a une AUTRE
            # question (« le flag CAPTE est-il PERIME ? », case-322) et n'est pose que par UNE seule
            # classe. L'avoir pris pour celui-ci VERROUILLAIT les 12 autres : une instance seedee
            # INACTIVE (le canal `includeInactive` de `decision_view_seed_body` publie `active:false`)
            # dont la condition portee devient vraie en cours de sim ne pouvait plus JAMAIS se
            # rallumer. MESURE : `test_contagions_lifecycle_live` -- l'aura GRANDIT, `1072` passe
            # eligible, live `actif=[1072] armure=1387` contre port `actif=[] armure=2312`.
            #
            # Les DEUX branches sont ancrees sur une mesure LIVE :
            #   * re-evaluer  -> `test_contagions_lifecycle_live` (aura qui grandit) ;
            #   * conserver   -> `test_wireweave_net_counter_is_once_per_enemy_turn` (la riposte
            #     `1111`, sans condition portee, ne doit pas se re-armer apres son
            #     `& DeactivateEffect` -- sinon riposte fantome de 2849 PV au coup suivant).
            # RESIDU NOMME : sans `ShouldRefreshForTrigger`, le port ne mirrore pas le CHOIX natif du
            # regime ; il choisit celui qu'il sait lire. Cf. `docs/rl/case-366-r1b-...` S7bis.
            cond = bool(e.is_active(ustate))
            if _active_condition_is_ported(e):
                e.active = cond
                active = cond
            else:
                active = bool(e.active) and cond
            # ── canal OVERRIDE (`StatOverrideEffect`, parts 7/8), SOUS LE MEME VERDICT `active` ──
            # `IdunBattle.Operations.RefreshEffectsOperation$$UpdateEffectTargets` ne connait PAS la
            # FAMILLE de l'effet : `ApplyEffectsForTargets` appelle le slot d'interface `IEffect+0xe`
            # (= `IdunBattle.Entities.Effects.BaseEffect$$Apply` -> `<Effect>.ApplyInternal`) et
            # `RevertEffectsForTargets` le slot `+0xf` (= `...$$Revert` -> `<Effect>.RevertInternal`).
            # Pour un `AStatModifierEffect` cela donne le couple additif ci-dessous ; pour un
            # `IdunBattle.Entities.Effects.StatOverrideEffect` cela donne
            # `ApplyInternal` = `ChangeStat(Position(stat, part 7), Direct(<comp+0x14>))` ->
            # `ValueOverride.SetOverride`, et `RevertInternal` = `Position(stat, part 8)` ->
            # `RemoveOverride`. Le driver couvre donc les DEUX canaux, et c'est la MEME condition
            # qui les pilote (`ShouldBeActive` est evaluee UNE fois par effet, avant `UpdateEffect
            # Targets`). Premier porteur : `ReinforcedHiveNode_ExtraBlock` (1109, #366-r1).
            # `SetOverride` ECRASE (un seul slot `ValueOverride` par stat) -> re-appliquer la meme
            # valeur est un NO-OP exact, comme `Modify` pour l'additif.
            for _st, _val, _mod in effect_stat_overrides(e):
                if active:
                    us.set_stat_override(int(_st), int(_val), bool(_mod))
                    out.append((int(uid), int(_st), int(_val)))
                else:
                    us.remove_stat_override(int(_st))
                    out.append((int(uid), int(_st), None))
            # `GetStatModification()` — point de verite UNIQUE des deux formes natives (R16).
            mods = effect_stat_modifications(e, ctx)
            stats = {int(st) for st, _amt in mods}
            base_stat = e.get_stat_modification_stat()
            if base_stat is not None:
                # L'instance peut etre INERTE (magnitude nulle/absente) et devoir quand meme etre
                # REVERTEE : le stat a retirer est celui qu'elle declare, pas celui qu'elle rend.
                stats.add(int(base_stat))
            if not stats:
                continue                      # effet non StatModifier
            # UNE cle par instance (cf. en-tete) — jamais une 2e.
            src = effect_stat_mod_key(e)
            if src is None:
                continue
            if active:
                for st, amt in mods:
                    if amt:
                        us.change_stat(int(st), src, int(amt))   # ApplyModification (part 5|9)
                        out.append((int(uid), int(st), int(amt)))
            else:
                for st in sorted(stats):
                    us.revert_stat(int(st), src)                 # RevertModification (part 6)
                    out.append((int(uid), int(st), None))
    return out
