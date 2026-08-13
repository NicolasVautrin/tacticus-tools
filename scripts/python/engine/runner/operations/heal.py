"""Operation de SOIN -- `IdunBattle.Operations.HealUnitOperation$$Execute`.

Mutateur ECS inverse du degat : remonte les PV d'une cible, plafonne a `hp_max` (FillUp).
JUMEAU de `operations/repair.py`, et le natif les ecrit comme tels -- deux Operations distinctes,
deux `BehaviourOptions`, deux slots de l'`OperationProcessor` (`<slot 0x57>` = `HealUnit`,
`<slot 0x58>` = `RepairUnit`).

POURQUOI CE MODULE A ETE REECRIT (#520). L'audit `docs/rl/combat-ability-coverage.md` annoncait la
categorie HEAL/REPAIR « BLOQUEE sur un `HealOperation`/`RepairOperation` combat absent du runner ».
Les deux Operations EXISTAIENT ; le vrai bloqueur etait ailleurs, et il etait INVISIBLE : celle-ci
n'etait qu'un `FillUp` NU derriere un gate `EffectType.Cursed`. Il lui manquait les DEUX etages que
son jumeau porte depuis #299 -- le gate `AttackQuery$$EntityCanBeHealed` et tout
`DamagePrediction$$PredictHeal`. Consequence CHIFFREE, mesuree : le port soignait une unite
MECANIQUE (que le natif refuse), une MACHINE OF WAR, et une cible a trait `Object`. C'est la meme
forme de bug que #310 (`LivingMetal` cable sur `HealUnitOperation` au lieu de `RepairUnitOperation`),
dans l'autre sens.

CHAINE NATIVE (decompile = verite), du behaviour jusqu'a la mutation :

    <X>Ability$$CreateBehaviour
      -> IdunBattleLogic.Entities.DSLBehaviors$$Heal(healer, targets, amount, source, options)
      -> IdunBattle.Entities.Behaviours.HealBehaviour$$Execute
           healer = <selecteur@+0x50>            # le SOIGNEUR (`Caster` sur les call-sites lus)
           foreach target in <selecteur@+0x58> :
               amount = <+0x60>.Calculate(entities)
               processor.<slot 0x57>(healer, target, amount,
                                     options.scope@+0x2c, options.removeEffects@+0x30,
                                     source@+0x20)
      -> Core.Services.OperationProcessor$$HealUnit          (caller MINCE, aucune logique)
      -> IdunBattle.Operations.HealUnitOperation$$Execute    <-- CE MODULE

`HealUnitOperation$$Execute` (MIRROR, lu verbatim) :

    if (!attackQuery.<slot 0x11>(caster, target, scope, removeEffects)) return {};  # EntityCanBeHealed
    cursed = EntityExtensions.HasEffect(target, state, 0x4f Cursed, null)
    removedNegativeUnitEffects = 0
    if (removeEffects) removedNegativeUnitEffects = processor.<slot 0x5b>(target, ...)
    pred = damagePrediction.<slot 1>(caster, GetMainTile(caster), target, amount, scope)
                                                                   # = DamagePrediction$$PredictHeal
    healAmount = cursed ? 0 : pred.fillUp
    fillUp = GetFillUpStatComponent(target, Health)
    wasWounded = HealthComponent.IsWounded(fillUp)
    healed = FillUpStatComponent.FillUp(fillUp, healAmount)         # <-- LA MUTATION
    processor.<slot 0x5c>(target)
    if (!wasWounded && healed < 1 && removedNegativeUnitEffects < 1
        && !UnitExtensions.HasFlag(caster, 0x17)) return {};
    result.healed += healed ; <statistiques> ; <Action=HealInfo> ;
    processor.<slot 0x51>(target, target, target, 0x1e, ...)
    processor.<slot 0x51>(caster, caster, target, 0x2b, ...)
    if (removeEffects) processor.<slot 0x51>(caster, caster, target, 0x2c, ...)
    processor.<slot 0x2f>(RefreshEffectOptions{3, null})

⚠ LES NOMS GHIDRA DES PARAMETRES SONT DECALES D'UN CRAN (retour `OperationResult` de 0x40 octets ->
`rcx` porte le pointeur sret). Meme decalage, meme recoupement que dans `engine/streams/heal_unit.py`,
qui le documente : ce que Ghidra nomme `target` est le **caster**, `amount` est la **cible**, `scope`
est le **montant**, `removeEffects` est le **scope**, `abilityOrEffect` est **removeEffects**.
Le recoupement interne tient ici en un point supplementaire : l'appel du slot 0x11 passe
`(<ghidra:target>, <ghidra:amount>, <ghidra:removeEffects>, <ghidra:abilityOrEffect>)`, or la
signature de `AttackQuery$$EntityCanBeHealed` est `(caster, target, scope, removeEffects)`.

`IdunBattle.Core.Services.DamagePrediction$$PredictHeal` (MIRROR) :

    predicted = amount
    if (EntityExtensions.IsUnit(caster)) {
        # collecte INLINE des descripteurs `BaseEffect$$HealBonus` de TOUS les EffectComponent
        # du combat, puis :  foreach (b in bonuses) predicted += b.<+0x30>.GetValueOrDefault()
    }
    health = UnitExtensions.GetStat(target, 5 Health, 0 Current)
    if (scope == 1) predicted = Min(predicted, GetGroupUnitHealLimit(target, health))
    if (UnitExtensions.IsBoss(target))
        predicted = Min(predicted, GetStat(target, 5 Health, 3 Initial) - health)
    if (predicted < 0) return CONCAT44(-FillUpStatComponent.MaxReduce(fillUp, -predicted, false),
                                       health)
    return CONCAT44(FillUpStatComponent.MaxFillUp(fillUp, Math.Max(0, predicted)), health)

TROIS ECARTS DE STRUCTURE avec `PredictRepair`, tous LUS et aucun deduit :

  * le gate de l'etage bonus est `EntityExtensions$$IsUnit(caster)`, pas `IsActor(caster)` ;
  * le bonus est PUREMENT ADDITIF (`predicted += <Nullable<int>>.GetValueOrDefault()`), la ou
    `PredictRepair` delegue a `RepairCalculations$$CalculateRepairModifierForPrediction` et applique
    `(flatBonus + amount) * multiplier`. Il n'existe AUCUN multiplicateur de soin ;
  * `PredictHeal` porte une branche NEGATIVE (`MaxReduce`) que `PredictRepair` n'a pas : un « soin »
    negatif RETIRE des PV.

⚠ L'ETAGE BONUS EST INERTE SUR CE BUILD, ET C'EST MESURE -- pas suppose. Le descripteur que
`BaseEffect$$HealBonus` lit est fabrique par un slot virtuel dont les implementeurs se nomment
`<X>Effect$$CreateEffectHealBonus`, sur le modele EXACT des trois `CreateEffectRepairBonus` que
`operations/repair.py` cite. Sur `rnca9r7q6c`, les 178 implementeurs de `CreateEffect*` du build se
ventilent en SEPT familles -- `DamageBonusForAttack` (107), `DamageMalusForDefense` (39),
`HitsBonusForAttack` (28), `RepairBonus` (3), `UpgradeGroupHandler` (1),
`CappedDamageMalusForDefense` (1), `CappedDamageBonusForAttack` (1) -- et **AUCUNE** n'est un heal
bonus. Deux canaux INDEPENDANTS le disent (`data/symbols/<build>/frida/methods.tsv` et
`ghidra/functions.tsv`) : `HealBonus` n'y a que la methode de BASE et le `ToString` de la struct.
La boucle est donc portee comme un NO-OP EXPLICITE : `predicted` inchange, isomorphisme conserve,
zero valeur inventee. Le jour ou un build ajoute un `CreateEffectHealBonus`, c'est ce paragraphe
qu'il faut re-mesurer.

ASCII only (console cp1252).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..components import HealthComponent
from ...entities.effect_type import EffectType
from ...services.trait_damage_limits import get_group_unit_heal_limit
from .fill_up_prediction import group_unit_members, is_boss

if TYPE_CHECKING:
    from ..state import State

# EffectType.Cursed (79) -- GATE heal-block. `HealUnitOperation$$Execute` fait
# `EntityExtensions.HasEffect(target, Cursed)` : si l'effet est present, le montant de soin est force
# a 0 (`healAmount = cursed ? 0 : predicted`) -- SANS sortie anticipee. #158.
CURSED = int(EffectType.Cursed)


def predict_heal(state: "State", caster_id, target_id: int, amount: int,
                 scope: int = 0) -> int:
    """`IdunBattle.Core.Services.DamagePrediction$$PredictHeal` -> son champ `fillUp` (le HIGH dword
    du `CONCAT44(MaxFillUp(...), GetStat(target, Health))` que le natif renvoie).

    Le champ LOW (`currentHealth`) n'est PAS rendu : cote EXECUTION il n'a aucun consommateur (c'est
    la face PREDICTION qui le lit, `engine.predict.predict_heal_effective`). PENDANT EXACT de
    `operations/repair.py::predict_repair`. Etages, dans l'ORDRE natif :

      1. BONUS des effets, GATE par `EntityExtensions$$IsUnit(caster)` -- **INERTE sur ce build**
         (0 implementeur de `CreateEffectHealBonus` sur 178 `CreateEffect*`, cf. l'en-tete de
         module). Ecrit comme no-op EXPLICITE, jamais comme une valeur inventee ;
      2. cap de GROUPE `GetGroupUnitHealLimit`, GATE par `scope == 1` -- le meme foyer
         (`services/trait_damage_limits.get_group_unit_heal_limit`) que `predict_repair` ;
      3. cap BOSS `GetStat(Health, Initial) - current`, gate `IsBoss(target)` : `is_boss` rend
         toujours `False` (champ `UnitComponent+0x88` hors substrat, cf.
         `operations/fill_up_prediction.py`). La branche est ecrite pour rester isomorphe ;
      4. `MaxFillUp` = `Min(Max(0, predicted), CurrentMaximumValue - current)` si `predicted >= 0`,
         sinon `-MaxReduce(-predicted, ignoreMinimum: false)` -- un « soin » NEGATIF retire des PV.

    ⚠ LA BRANCHE NEGATIVE EST PORTEE PARCE QUE LE NATIF L'ECRIT, PAS PARCE QU'UN CALL-SITE PORTE LA
    PREND. Aucun des `Heal(...)` portes ne peut y arriver : la feuille `abilities/behaviours/stats.py
    ::Heal` filtre `amount > 0` avant d'appeler, exactement comme le decompile de `HealBehaviour` ne
    filtre rien du tout -- c'est donc, cote port, une branche INERTE, et la mesurer est le seul moyen
    de le savoir."""
    e = state.get_entity(int(target_id))
    hc = e.get_component(HealthComponent) if e is not None else None
    if hc is None or hc.hp is None or hc.hp_max is None:
        return 0
    amt = int(amount)
    # (1) `if (IsUnit(caster)) { foreach (b in <HealBonus descriptors>) predicted += b.GetValueOrDefault(); }`
    #     -- boucle INERTE sur `rnca9r7q6c` : aucun effet du build ne fabrique de descripteur de heal
    #     bonus. `predicted` sort donc inchange, et c'est une MESURE (en-tete de module), pas un oubli.
    cur, mx = int(hc.hp), int(hc.hp_max)
    # (2) `if (scope == 1) predicted = Min(predicted, GetGroupUnitHealLimit(target, health))` : le cap
    #     « ce qu'on peut restaurer SANS REVEILLER de membre mort » d'une unite multi-membres.
    #     `GetGroupUnitHealLimit` rend `int.MaxValue` a `nrOfMembers < 2` (heros) -> `Min` no-op.
    if int(scope) == 1:
        amt = min(amt, get_group_unit_heal_limit(mx, group_unit_members(state, int(target_id)), cur))
    # (3) cap BOSS : `is_boss` rend toujours False (cf. `fill_up_prediction.is_boss`).
    _ = is_boss(state, int(target_id))
    if amt < 0:
        # `-MaxReduce(fillUp, -predicted, ignoreMinimum: false)` = `-Min(-predicted, current)`, borne
        # en plus par le plancher `Minimum` quand il est pose (`HealthComponent.max_reduce`).
        return -hc.max_reduce(-amt)
    return min(max(0, amt), mx - cur)                          # (4) MaxFillUp


class HealUnitOperation:
    """`IdunBattle.Operations.HealUnitOperation$$Execute` (caller mince
    `Core.Services.OperationProcessor$$HealUnit`).

    Imperatif par DOCTRINE (#149) : c'est un mutateur ECS, pas un arbre DSL. La feuille DSL qui
    l'appelle est `runner/abilities/behaviours/stats.py::Heal`
    (`IdunBattleLogic.Entities.DSLBehaviors$$Heal` -> `HealBehaviour$$Execute`).

    NON PORTE (nomme, secondaire pour la fidelite d'ETAT PV) -- MEME liste que son jumeau
    `RepairUnitOperation`, et pour les MEMES raisons :
      * le volet `removeEffects` (`processor.<slot 0x5b>`, purge des effets negatifs de la cible) :
        `HealBehaviourOptions$$ForHeal` pose bien `removeEffects = 1`, mais le port n'a pas de
        marqueur « effet negatif » (meme trou que `attack_query.has_negative_unit_effect`, NOMME
        la-bas). Consequence CHIFFREE : `removedNegativeUnitEffects` vaut toujours 0 cote port, donc
        un soin qui ne restaure AUCUN PV et ne fait que purger rend `healed = 0` des deux cotes --
        l'ecart ne porte que sur les effets purges, jamais sur les PV ;
      * l'EVENT `Action=HealInfo` (porte a part, `engine/streams/heal_unit.py`) et les statistiques
        (`ActorStatisticsComponent$$AddRestoreHealthAction`, compteurs `+0xc8`/`+0xd4`/`+0xe4`) ;
      * les vecteurs de trigger `processor.<slot 0x51>` `On(0x1e)`, `On(0x2b)`, `On(0x2c)` et le
        `RefreshEffects(RefreshEffectOptions{3, null})` de queue. Le SEUL consommateur porte est le
        stat-mod EXTRA_HITS du trait `Swarm`
        (`IdunBattleLogic.Entities.Abilities.Active.Loki.SwarmAbility$$CreateTrigger`, bras
        `On(UnitHealed=43)`), deja cable par l'appel direct a `on_group_unit_hp_changed` ci-dessous
        -- MEME raccourci que `RepairUnitOperation`, et deja valide live (`probe_203_swarm.py`) ;
      * la PORTE DE RESULTAT VIDE de QUEUE (#982-r5, LUE sur `rnca9r7q6c`) :

            if (!wasWounded && healed < 1 && removedNegativeUnitEffects < 1
                && !UnitExtensions.HasFlag(caster, 0x17 CanHealFullHealthUnits))  return this;

        C'est le SECOND usage natif du flag `CanHealFullHealthUnits`, et il est lu SUR LE CASTER :
        il empeche le natif de rendre un resultat VIDE quand rien n'a ete soigne. Le premier usage
        est le gate d'entree `IdunBattle.Core.Services.AttackQuery$$EntityCanBeHealed`, lui PORTE
        (cf. `entity_can_be_healed` plus bas) et MORDANT (cliquet
        `tests/engine/test_982r5_can_heal_full_health_offline.py`). Le port, lui, sort sur
        `healed <= 0` sans consulter le flag : l'ecart ne porte QUE sur les sorties listees
        ci-dessus (event, statistiques, triggers, `RefreshEffects`), JAMAIS sur les PV -- `FillUp`
        rend 0 sur une cible pleine dans les deux regimes. NOMME plutot que tu : sans cette ligne,
        un lecteur conclut que le flag 23 est integralement porte, alors que seul son etage de GATE
        l'est."""
    __slots__ = ()

    @staticmethod
    def execute(state: "State", caster_id, target_id: int, amount: int,
                scope: int = 0, remove_effects: bool = False, ability_or_effect=None) -> int:
        """Soigne `target_id` et rend le montant REELLEMENT restaure (0 si le gate refuse, si la
        cible est deja pleine, si elle porte `Cursed`, ou si ses PV ne sont pas lisibles).

        `ability_or_effect` = le SEPTIEME argument natif d'`IdunBattle.Operations.
        HealUnitOperation$$Execute`, celui que Ghidra ne nomme pas parce qu'il arrive sur la PILE
        (`in_stack_00000040`) -- a ne pas confondre avec le parametre que Ghidra APPELLE
        `abilityOrEffect`, qui est en realite `removeEffects` (cf. le decalage documente en tete de
        module). PORTE PAR SYMETRIE avec `RepairUnitOperation.execute` (#908), ou il a un
        consommateur reel.
        ⚠ **AUCUN CONSOMMATEUR PORTE ICI, et c'est ecrit plutot que tu** : cote natif il n'alimente
        que les vecteurs de trigger `On(0x2b)` / `On(0x2c)` (non modelises) -- et surtout,
        `IdunBattle.Core.Services.DamagePrediction$$PredictHeal` NE LE RECOIT PAS, contrairement a
        `PredictRepair`. C'est pourquoi il n'est PAS relaye a `predict_heal` : le canal de bonus du
        soin n'a pas de champ de cause.

        `scope` / `remove_effects` = `HealBehaviourOptions+0x2c` / `+0x30`, ecrits par
        `IdunBattle.Entities.Behaviours.HealBehaviourOptions$$ForHeal` (= `0` / `1`) ou
        `$$ForRegenerate` (= `1` / `0`) -- ce sont les deux SEULES fabriques du build (relues
        verbatim sur `rnca9r7q6c`), et elles portent les MEMES couples que leurs homonymes
        `RepairBehaviourOptions`.

        SOUS `scope == 1`, le gate natif prend une condition de plus (`scope != 0 &&
        IsAtGroupUnitHealLimit(target)`). Cote port `attack_query.is_at_group_unit_heal_limit` est un
        stub `False` (residu NOMME la-bas), donc le gate laisse passer. CONSEQUENCE CHIFFREE : nulle
        sur l'etat PV, et pour la MEME raison que du cote repair -- `IsAtGroupUnitHealLimit` est,
        terme a terme, `GetGroupUnitHealLimit <= 0`, donc l'etage (2) de `predict_heal` rend
        `predicted <= 0` exactement quand le gate aurait refuse."""
        from ..abilities.attack_query import entity_can_be_healed
        if target_id is None:
            return 0
        # GATE `attackQuery.<slot 0x11>` = `IdunBattle.Core.Services.AttackQuery$$EntityCanBeHealed`
        # (surcharge 4 arguments, caster en tete) -- mirror deja porte, cf. `abilities/attack_query.py`.
        # Le natif sort ICI sur un `OperationResult` VIDE : aucune mutation, aucun event, aucun trigger,
        # et surtout AUCUN `FillUp` -- l'accumulateur `over_reduce` n'est donc PAS purge sur ce chemin.
        if not entity_can_be_healed(state, caster_id, int(target_id),
                                    scope=int(scope), remove_effects=bool(remove_effects)):
            return 0
        e = state.get_entity(int(target_id))
        hc = e.get_component(HealthComponent) if e is not None else None
        if hc is None or hc.hp is None or hc.hp_max is None:
            return 0
        predicted = predict_heal(state, caster_id, int(target_id), int(amount), scope=int(scope))
        # GATE heal-block `EffectType.Cursed`(79) : `healAmount = cursed ? 0 : predicted`. Le natif
        # n'en fait PAS une sortie anticipee -- il appelle `FillUp` AVEC 0 (#462-r4e-o-r2). La
        # difference est observable : `FillUp` purge `over_reduce` en queue, inconditionnellement.
        if state.effects is not None and state.effects.has_effect(int(target_id), effect_type=CURSED):
            predicted = 0
        # `FillUpStatComponent$$FillUp` : `healed = Min(amount, CurrentMaximumValue - current)` ;
        # `current += healed` ; `+0x24 = 0`. FOYER UNIQUE (`HealthComponent.fill_up`) -- appele AVANT
        # toute sortie anticipee, comme le natif (son early-return est APRES le `FillUp`).
        healed = hc.fill_up(int(predicted))
        if healed <= 0:
            return 0
        # #60 : bras `On(UnitHealed=43) & OwnerIsTarget` du
        # `IdunBattleLogic.Entities.Abilities.Active.Loki.SwarmAbility$$CreateTrigger` -- re-evalue le
        # stat-mod EXTRA_HITS du trait Swarm apres la remontee de PV (des membres reviennent -> malus
        # reduit).
        from ..abilities.loki.swarm import on_group_unit_hp_changed
        on_group_unit_hp_changed(state, int(target_id))
        return healed
