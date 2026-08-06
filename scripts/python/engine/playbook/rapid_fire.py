"""`IdunBattle.AI.Playbook.Loki.RapidFirePlaybook` -- face ATTACK du triggered `RapidFire` (1135),
passif de 3 npc `ultra*Intercessor*` (`ultraNpc3Intercessor`, `ultraNpc4HeavyIntercessor`,
`ultraNpc4HeavyIntercessorSurv`) et du SUMMON `ultraSmnHeavyIntercessor` : 4 porteurs DISPATCHES,
tete des residus ATTACK a corps NON trivial de #419-r1 par nombre de porteurs.

Feuille `TriggeredAbilitiesUtility(2)` du composite Damage(34), MEME dispatcher que Psyker,
AggressiveOnslaught, SuppressiveFire, Lakrimae, BarbedOvipositor, Neuroparasite, SaviorProtocols,
AvalancheOfMuscle, Boltstorm, FireOfAbsolution, CosmicHorror et LightImUp
(`utilities/tile.py::evaluate_attack_in_steps`, vslot 3).

Ce que le passif fait (i2, qui recoupe le decompile) :

  << The Heavy Intercessor attacks twice if he did not move this turn, with each of the two
  attacks dealing Damage as normal. >>

## Le corps natif, remis en C#

`IdunBattle.AI.Playbook.Loki.RapidFirePlaybook$$CalculateAttackUtilityInStepsInternal` monte la SM
`d__2` -- disposition LUE DANS LE WRAPPER, jamais par analogie : `sm@+0x10 = state`,
`sm@+0x18 = current`, `sm@+0x20 = case`, `sm@+0x28 = this` (le PLAYBOOK). Le delegue `getUtilityVal`
n'est **PAS capture** (comme `Neuroparasite` et `LightImUp`) : la sortie de ce playbook n'est AUCUNE
cle de `Utilities.Default.TriggeredAbilities`. Corps
`RapidFirePlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__2$$MoveNext`, **CINQ** etats de
yield, dans CET ordre :

    if (case.MovementTile != EntityExtensions.GetMainTile(case.Caster, this.<IBattleState @+0x40>))
        yield Fix64.op_Implicit(0);                                          // etat 1
    else if (!IsRegularAttack(case))
        yield Fix64.op_Implicit(0);                                          // etat 2
    else if (UnitExtensions.HasFlag(case.Caster, (UnitFlag)0 /* Moved */))
        yield Fix64.op_Implicit(0);                                          // etat 3
    else {
        var vt = this.<IBattleQuery @+0x60>.<slot 0x42>(                     // GetValidTargets
                     case.Caster, case.CasterPosition, (ActiveAbilityType)0x45);
        if (case.DamagePrediction.Value.WillBeKill)
            ValidTargets.Remove(vt, case.Target);
        if (vt.AllTargets.Count == 0)
            yield Fix64.op_Implicit(0);                                      // etat 4
        Fix64 best = Fix64.op_Implicit(0);
        foreach (IEntity t in vt.AllTargets) {
            Fix64 p = (t == case.Target && case.DamagePrediction.Value.MightBeKill)
                        ? Fix64.Half : Fix64.One;
            var pred = this.<IBattleQuery @+0x60>.<slot 0x22>(               // GetNormalAttackPrediction
                           case.Caster, case.Target, case.CasterPosition);
            best = Fix64.Max(best, CalculateUtilityFromDamageEvent(
                       new ProbableDamageEvent(t, pred, p, null),
                       case.Caster, case.CasterPosition));
        }
        yield best;                                                          // etat 5
    }

Huit lectures qui ne se devinent pas, et dont AUCUNE ne se generalise depuis un voisin de la liste :

1. **La premiere gate est une gate d'IMMOBILITE, et c'est une EGALITE DE TUILES.**
   `IdunBattle.AI.Utilities.UtilityMovementCase$$get_MovementTile` est un corps DEDUPLIQUE
   (`IdunBattle.Core.UnitPosition$$get_MainTile(this + 0x18)`) : sur un `UtilityAttackCase`, `+0x18`
   est `CasterPosition`, donc c'est la TUILE D'ATTAQUE -- le meme quirk de symbole que
   `cosmic_horror.py` (point 1 de son en-tete). L'autre membre est
   `IdunBattle.Entities.EntityExtensions$$GetMainTile(case.Caster, state)` = la tuile REELLE du
   caster. La comparaison est une egalite de POINTEURS d'entite-tuile, donc d'identite de tuile.
   ⇒ le playbook ne vaut QUE sur la tuile courante : toute tuile de deplacement du sweep rend 0.
   C'est le premier playbook attack porte dont la gate d'entree ANNULE tout le balayage de tuiles.

2. **La troisieme gate est `UnitFlag.Moved` (=0)**, enum QUALIFIE (`IdunBattle.Entities.Enum.
   UnitFlag`, `0=Moved`) : `IdunBattle.Entities.UnitExtensions$$HasFlag(unit, flag)` ->
   `IdunBattle.Entities.Components.UnitFlagsComponent$$Has`. Ce n'est PAS un doublon de la gate 1 :
   la 1 dit « la tuile evaluee est celle ou je suis », la 3 dit « je n'ai pas deja bouge CE TOUR »
   -- une unite qui a bouge puis revient sur sa tuile de depart passe la 1 et echoue la 3. Le
   substrat cote port est `scene.has_moved` (canal `combatSnapshot.unitFlags`, #266), TRI-ETAT.

3. **L'ensemble de cibles est celui de l'attaque normale, demande par LITTERAL `0x45`.**
   `IdunBattle.Core.Services.AttackQuery$$GetValidTargets(unit, from, activeAbilityType)` --
   `0x45` = 69 = `ActiveAbilityType.Loki_NormalAttack`, PAS `UnitExtensions.GetNormalAttackType
   (case.Caster)` (qui lit `ActiveAbilityComponent+0x28`) ni `case.AbilityType`. La difference est
   OBSERVABLE : le corps natif de `GetValidTargets` fait
   `unit.GetComponent<ActiveAbilityComponent>().GetOrNull(0x45)` et, si l'unite n'a pas CETTE
   ability, il **LogError puis rend `ValidTargets.Empty`** -> le playbook tombe a l'etat 4 (0).
   Un porteur dont l'attaque normale est concrete et distincte -- il en existe **17** au
   `StaticBattleRules.ActiveAbility` cctor, p. ex. `Boltstorm_NormalAttack` (1128) ou
   `Wraithcannon_NormalAttack` (1138) -- rend donc **0** a ce playbook, quelle que soit la
   geometrie. Les quatre porteurs reels n'ont aucun `*_NormalAttack` a leur gameconfig : ils sont
   tous sur le 69 generique.

4. **Le canal port est `abilityTargets.fromHere`, et c'est le MEME appel natif.** Le RPC
   (`frida/hooks/features/ai-step/rpc-targeting.ts`) resout la surcharge par le TYPE de son 2e
   parametre (`UnitPosition`) et appelle `AttackQuery.GetValidTargets(unit,
   UnitPosition{GetTiles(unit, state)}, abilityType)` -- litteralement le call-site du playbook,
   avec `from` = la position COURANTE. Or la gate 1 impose deja `case.CasterPosition.MainTile ==
   MainTile(caster)` : les deux positions coincident, l'appel est donc le meme. `targets` (l'autre
   champ du RPC) serait FAUX ici -- c'est l'union sur toutes les tuiles de deplacement
   (`GetAllValidTargetsFromAllPossibleMovementTiles`), un SUR-ensemble.

5. **La prediction est calculee UNE FOIS, contre `case.Target`, et RE-UTILISEE pour chaque cible
   de la boucle.** LU A L'ASSEMBLEUR, pas au decompile : au call-site du slot 0x22 les trois
   arguments sont `mov rcx,[rax+0x10]` / `mov r8,[rax+0x20]` / `mov rax,[rax+0x18]` avec
   `rax = sm.case`, soit `(case.Caster, case.Target, case.CasterPosition)` -- l'element courant de
   l'enumerateur (`r15`) n'y entre PAS ; il n'apparait que comme `target` du
   `ProbableDamageEvent`. Le terme varie donc d'une cible a l'autre par DEUX canaux seulement :
   la probabilite (point 6) et le `combinedMax` de la cible que consomme le composite Damage
   (`ProbableDamageEvent.target`). C'est un QUIRK du natif, pas une simplification du port : le
   port hisse l'appel hors de la boucle (fonction pure des memes trois arguments) et le dit.

6. **Les deux probabilites sont `Fix64.Half` et `Fix64.One`, lues au `.cctor`.**
   `FixMath.NET.Fix64$$.cctor` ecrit `statics+0x20 = 0x100000000` (= 1.0) et
   `statics+0x30 = op_Division(0x100000000, 0x200000000)` (= 0.5). Le corps prend `+0x30` quand
   l'element courant EST `case.Target` **et** que `case.DamagePrediction.Value.MightBeKill`, `+0x20`
   dans tous les autres cas. La valeur part en `probability1` du `ProbableDamageEvent`
   (`Nullable<Fix64>`), `probability2` restant NUL (defaut 1.0) --
   `TriggeredAbilityPlaybook<T>$$CalculateUtilityFromDamageEvent` commence par
   `Fix64.op_Multiply(prob2, prob1)`. Semantique : le second tir ne vaut qu'a moitie contre une
   cible qui sera peut-etre deja morte.

7. **`WillBeKill` RETIRE la cible du case de l'ensemble** (`IdunBattle.Entities.Abilities.
   ValidTargets$$Remove`, qui purge l'`OrderedSet@+0x10` ET chaque `OrderedSet` du dictionnaire
   `@+0x18`). Si elle en etait le SEUL element, l'etat 4 rend 0 : quand le premier tir tue A COUP
   SUR et qu'il n'y a personne d'autre a portee, le second tir ne vaut rien. `will_be_kill` /
   `might_be_kill` sont les deux accesseurs ASYMETRIQUES deja mirrores
   (`services/damage_prediction.py`) -- meme couple que `barbed_ovipositor.py`.

8. **La sortie est un MAXIMUM, borne en bas par ZERO.** `Fix64.Max` accumule depuis
   `Fix64.op_Implicit(0)` : ni somme (`fire_of_absolution`), ni moyenne (`psyker`, `light_im_up`),
   ni produit (`boltstorm`). Deux consequences : l'ORDRE d'enumeration de l'`OrderedSet` est
   INDIFFERENT (contrairement a tout keep-first), et une utilite NEGATIVE (le composite Damage sait
   en produire) est ecrasee a 0.

## Face MOVE : `yield Fix64(0)` CONSTANT -- decompile LU

`RapidFirePlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__1$$MoveNext` est un unique
`yield return Fix64.op_Implicit(0)`, rien d'autre. Elle n'entre donc pas au registre
`TRIGGERED_MOVE_PLAYBOOKS`, et son absence EST le comportement natif (meme forme que `Lakrimae`,
`BarbedOvipositor`, `Neuroparasite`, `AvalancheOfMuscle`, `Boltstorm`, `CosmicHorror`, `LightImUp`).

## Residus NOMMES

* `#419-r1-tr9-r1` -- **le canal `fromHere` est LIVE seulement**. `engine.ai.state_bridge` route
  `abilityTargets` vers `ability_targets_offline`, qui ne publie que `targets` (union sur les tuiles
  de deplacement, `GetAllValidTargetsFromAllPossibleMovementTiles`) : il n'a pas d'equivalent
  per-position. Le port lit donc un canal MUET hors-ligne (`fromHere` absent) et rend 0 -- une
  degradation RESTRICTIVE, NOMMEE, et jamais un faux terme. On ne se rabat PAS sur `ctx.plans`
  (dont l'`abilityId` est l'attaque normale CONCRETE de l'unite, pas le litteral 69) : ce repli
  serait faux exactement dans le regime que le point 3 rend observable. Fermeture : ajouter a
  `ability_targets_offline` une enumeration ancree sur la tuile COURANTE pour l'id demande.

* `#419-r1-tr9-r2` -- **`AttackQuery$$IsAlreadyUsedThisTurn` n'est pas porte**. Le natif l'evalue
  entre `GetOrNull` et le vrai ciblage, et rend `ValidTargets.Empty` s'il est vrai. Il est gate en
  tete par `AttackQuery+0x10` puis par
  `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.ActiveAbility$$IsRegularAbilityType`.
  Ce chemin est INERTE dans le regime de DECISION (l'IA evalue une unite qui n'a pas encore agi -- et
  `ActiveAbilityActionGenerator` la coupe en amont sur `HasFlag(unit, ActiveAbilityUsed)`), et le
  canal `fromHere` le traverse de toute facon puisqu'il appelle le MEME `AttackQuery.GetValidTargets`
  -- le port n'a donc rien a re-jouer. NON CONFRONTE.
"""
from __future__ import annotations

from ..entities.active_ability_type import ActiveAbilityType
from ..entities.triggered_ability_type import TriggeredAbilityType
from ..runner.abilities.attack_type import is_regular_attack
from .prediction.normal_attack import make_normal_attack_predictions
from .probable_damage_event import ProbableDamageEvent, calculate_utility_from_damage_event

# Le LITTERAL `0x45` du call-site `GetValidTargets` -- l'attaque normale GENERIQUE, jamais le
# `NormalAttackType` de l'unite (cf. en-tete, point 3).
_LOKI_NORMAL_ATTACK = int(ActiveAbilityType.Loki_NormalAttack)      # 0x45 = 69
# `FixMath.NET.Fix64$$.cctor` : `statics+0x30` et `statics+0x20` (cf. en-tete, point 6).
_FIX64_HALF = 0.5
_FIX64_ONE = 1.0
# Memo PAR-DECISION du canal `fromHere` : `AiDecisionContext` est reconstruit a chaque pas, donc
# une entree ne peut pas survivre a un changement d'etat. L'appel est deterministe pour un
# `(caster, 0x45)` donne a position fixe -- et la gate 1 fixe la position.
_MEMO = "_rapid_fire_from_here"


def valid_normal_attack_targets(ctx, caster_uid: int) -> "list[int] | None":
    """`IBattleQuery <slot 0x42>` = `AttackQuery$$GetValidTargets(case.Caster, case.CasterPosition,
    (ActiveAbilityType)0x45)` -- les cibles LEGALES de l'attaque normale generique DEPUIS LA TUILE
    COURANTE, via le champ `fromHere` du RPC `abilityTargets` (qui appelle litteralement cette
    surcharge, cf. en-tete point 4).

    TRI-ETAT, et la distinction porte : `None` = canal MUET (RPC indisponible, contexte OFFLINE --
    residu `#419-r1-tr9-r1`) ; `[]` = MESURE et vide, c'est-a-dire le `ValidTargets.Empty` que le
    natif rend quand l'unite n'a pas l'ability `0x45` a son `ActiveAbilityComponent`, ou qu'aucune
    cible ne passe le ciblage. Les deux menent a 0 cote sortie, mais seul le second est un fait
    natif -- l'autre est une degradation qu'il faut pouvoir nommer."""
    memo = ctx.__dict__.setdefault(_MEMO, {})
    if caster_uid in memo:
        return memo[caster_uid]
    out = None
    r = ctx.ability_targets(caster_uid, _LOKI_NORMAL_ATTACK) or {}
    for u in (r.get("units") or ()):
        if u.get("unitId") != caster_uid:
            continue
        for a in (u.get("abilities") or ()):
            if int(a.get("abilityId") or -1) != _LOKI_NORMAL_ATTACK:
                continue
            fh = a.get("fromHere")
            if fh is None:                       # cle ABSENTE -> capteur muet, pas « vide mesure »
                continue
            out = [t.get("targetId") for t in fh
                   if t.get("kind") == "unit" and t.get("targetId") is not None]
    memo[caster_uid] = out
    return out


class RapidFirePlaybook:
    """`RapidFirePlaybook` (`IdunBattle.AI.Playbook.Loki`, triggered 1135). Seule la face ATTACK a un
    corps ; la face MOVE est un `yield 0` constant au natif (cf. en-tete)."""

    ability_id: int = int(TriggeredAbilityType.RapidFire)          # 0x46f = 1135

    def calculate_attack_utility_in_steps(self, ctx, attacker_uid: int, ability_id: int,
                                          case_tgt_id: int, attack_tile, prediction=None) -> float:
        """Mirror de `<CalculateAttackUtilityInStepsInternal>d__2$$MoveNext` (cf. en-tete), dans
        l'ORDRE des cinq etats : tuile d'attaque != tuile reelle -> 0 ; ability du case non
        reguliere -> 0 ; caster deja deplace -> 0 ; aucune cible legale a l'attaque normale -> 0 ;
        sinon le MAXIMUM, borne en bas par 0, de l'utilite d'un SECOND tir par cible legale."""
        sc = getattr(ctx, "scene", None)
        if sc is None or attack_tile is None:
            return 0.0
        # etat 1 -- `case.MovementTile == GetMainTile(case.Caster, state)` : la tuile EVALUEE doit
        # etre celle ou le caster se tient DEJA (le passif ne tire deux fois que sans deplacement).
        cur = sc.pos(attacker_uid)
        if cur is None or tuple(attack_tile) != tuple(cur):
            return 0.0
        # etat 2 -- `TriggeredAbilityPlaybook<T>$$IsRegularAttack(case)` : `Contains` sur
        # l'`OrderedSet` statique de `StaticBattleRules.ActiveAbility` (foyer `attack_type`).
        if ability_id is None or not is_regular_attack(int(ability_id)):
            return 0.0
        # etat 3 -- `UnitExtensions.HasFlag(case.Caster, UnitFlag.Moved)`. TRI-ETAT : `None` =
        # capteur `unitFlags` non mesure -> on NE COUPE PAS (comportement d'avant le capteur),
        # `False` mesure passe, `True` coupe.
        if sc.has_moved(attacker_uid) is True:
            return 0.0
        # etat 4 -- `GetValidTargets(caster, casterPosition, 0x45)`, moins la cible du case quand le
        # premier tir la tue A COUP SUR (`ValidTargets.Remove`). Ensemble vide -> 0.
        targets = valid_normal_attack_targets(ctx, attacker_uid)
        if not targets:
            return 0.0
        if prediction is None:
            # Le natif fait `case.DamagePrediction.get_Value()` SANS garde : `HasValue == false`
            # y LEVE `InvalidOperationException`. Ce regime n'existe pas sous le dispatcher
            # `TriggeredAbilitiesUtility(2)` (case bati par `UtilityAttackCase$$ForDamagePrediction`,
            # qui porte toujours la prediction) ; le port rend 0 plutot que de lever.
            return 0.0
        if prediction.will_be_kill():
            targets = [t for t in targets if t != case_tgt_id]
            if not targets:
                return 0.0
        # etat 5 -- `Fix64.Max` sur les cibles, depuis `Fix64(0)`.
        # La prediction est HISSEE hors de la boucle : le natif la recalcule a chaque tour avec les
        # MEMES trois arguments `(case.Caster, case.Target, case.CasterPosition)` -- l'element
        # courant n'y entre pas (en-tete, point 5).
        ev = make_normal_attack_predictions(sc, attacker_uid, case_tgt_id, attack_tile)
        pred = getattr(ev, "prediction", None) if ev is not None else None
        if pred is None:
            return 0.0
        might = prediction.might_be_kill()
        best = 0.0
        for t in targets:
            p = _FIX64_HALF if (t == case_tgt_id and might) else _FIX64_ONE
            # `target_hp` / `target_shield` : la feuille `DamageUtility` lit `GetStat(case.Target,
            # Health, Max|Current)` et `DamageUtility$$GetShield(case.Target)` sur l'ENTITE de
            # l'event, PAS sur le `DamagePredictionResult` (qui porte, lui, la sante de
            # `case.Target` du case). Ce playbook est le PREMIER producteur ou les deux cibles
            # different -- sans ces deux champs, le composite noterait chaque cible avec les PV
            # d'une autre. Les feuilles `KillUnit` / `OverkillUnit`, elles, restent sur la
            # prediction (cf. `utilities/damage.py::DamageUtility.evaluate`).
            u = calculate_utility_from_damage_event(
                ProbableDamageEvent(target=t, prediction=pred, probability1=p,
                                    target_hp=sc.hp(t), target_shield=sc.shield(t)),
                ctx.wt, (ctx.hpmax_by_id or {}).get(t))
            if u > best:
                best = u
        return best


__all__ = ["RapidFirePlaybook", "valid_normal_attack_targets"]
