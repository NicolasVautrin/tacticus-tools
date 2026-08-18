"""`IdunBattle.AI.Playbook.Loki.LightImUpPlaybook` -- face ATTACK du triggered `LightImUp` (1103),
passif d'`orksWarboss` << Gulgortz >> (HERO, au pool rank 17) et de 4 npc (`orksBossWarboss`,
`orksBossWarbossLHE`, `orksNpcWarboss`, `orksNpcWarbossSurv`) : 5 porteurs DISPATCHES, tete des
residus ATTACK a corps NON trivial de #419-r1.

Feuille `TriggeredAbilitiesUtility(2)` du composite Damage, MEME dispatcher que Psyker,
AggressiveOnslaught, SuppressiveFire, Lakrimae, BarbedOvipositor, Neuroparasite, SaviorProtocols,
AvalancheOfMuscle et Boltstorm (`utilities/tile.py::evaluate_attack_in_steps`, vslot 3).

(!) PIEGE DU NOM, leve : `1103` designe TROIS artefacts distincts. Enums QUALIFIES --
`TriggeredAbilityType.LightImUp = 1103` (CE playbook), `ActiveAbilityType.Supercharge = 1103`,
`EffectType.KanOpener_ReduceArmor = 1103`. Corollaire OUTILLAGE : `gameconfig.ability_name(1103)`
rend **"Supercharge"** (l'index est celui d'`ActiveAbilityType`) -- toute lecture de config passe
donc par le NOM `"LightImUp"`, jamais par l'id.

## Ce que le passif fait (tooltip i2, qui recoupe le decompile)

  << After performing a normal attack, Boss Gulgortz performs a second attack against the same
  enemy, dealing 3x 1091-1455 Projectile Damage. If the target is defeated, leftover hits are
  allocated to any random enemy target within 3 hexes. >>

## Le corps natif, remis en C#

`IdunBattle.AI.Playbook.Loki.LightImUpPlaybook$$CalculateAttackUtilityInStepsInternal` monte la SM
`d__2` -- disposition LUE DANS LE WRAPPER, jamais par analogie : `sm@+0x10 = state`,
`sm@+0x18 = current`, `sm@+0x20 = this` (le PLAYBOOK), `sm@+0x28 = case`. Le delegue `getUtilityVal`
n'est **PAS capture** (comme `Neuroparasite`, et contrairement a `BarbedOvipositor`/`Boltstorm`) :
la sortie de ce playbook n'est AUCUNE cle de `Utilities.Default.TriggeredAbilities`. Le corps est
`LightImUpPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__2$$MoveNext`, **CINQ** etats de
yield, dans CET ordre :

    if (!IsMeleeAttack(case))    yield Fix64(0);                              // etat 1
    else if (!IsRegularAttack(case)) yield Fix64(0);                          // etat 2
    else {
        var st     = GetAbilityState(case.Caster);          // etat per-ability du passif
        int hits   = ability.GetHits();                     // ConfigConst(0x2f = nrOfHits)
        var avg    = ability.GetAverageDamage(st);          // BaseTriggeredAbility.MinMaxDamageAverage
        int amount = avg.Calculate(new AbilityEntities());  // <IAmountFormula slot 1>, entities NULLES
        var profil = ability.GetDamageProfile();            // AbilityConfiguration.GetDamageProfile

        var pred1 = Query.<slot 0x22>(case.Caster, case.Target, case.CasterPosition);
        if (pred1.WillBeKill)
            yield CalculateAttackUtilityForSecondaryTarget(case, hits);       // etat 3
        else {
            var pred2 = Query.<slot 0x28>(case.Caster, case.Target, case.CasterPosition,
                                          case.AbilityType, amount, profil, hits);
            pred2.Add(pred1);
            if (!pred2.MightBeKill)
                yield CalculateAttackUtilityForMainTarget(case, hits);        // etat 4
            else
                yield (CalculateAttackUtilityForMainTarget(case, hits)
                       + CalculateAttackUtilityForSecondaryTarget(case, hits)) / Fix64(2);  // etat 5
        }
    }

et les deux methodes PROPRES au playbook (symboles a part, decompilees separement) :

    Fix64 CalculateAttackUtilityForMainTarget(case, hits) {
        <st / amount / profil : les MEMES trois lectures que ci-dessus>
        var pred = Query.<slot 0x28>(case.Caster, case.Target, case.CasterPosition,
                                     case.AbilityType, amount, profil, hits);
        return CalculateUtilityFromDamageEvent(new ProbableDamageEvent(case.Target, pred),
                                               case.Caster, case.CasterPosition);
    }

    Fix64 CalculateAttackUtilityForSecondaryTarget(case, hits) {
        var entities = new AbilityEntities {          // memset 0x128 a 0, PUIS quatre champs
            Actor = Caster = Owner = case.Caster,     // +0x00 / +0x08 / +0x18
            Target = case.Target,                     // +0x10
            CasterTile = case.CasterPosition.MainTile };  // +0x40
        var sel = ability.GetPossibleSecondaryTargets();
        var targets = sel.Select(entities, 3);
        if (targets.Count == 0) return Fix64(0);
        <st / amount / profil : encore les MEMES trois lectures>
        Fix64 total = 0;
        foreach (var t in targets)
            total += CalculateUtilityFromDamageEvent(
                new ProbableDamageEvent(t, Query.<slot 0x28>(case.Caster, t, case.CasterPosition,
                                                            case.AbilityType, amount, profil, hits)),
                case.Caster, case.CasterPosition);
        return total / Fix64(targets.Count);          // MOYENNE
    }

et le selecteur, `IdunBattleLogic.Entities.Abilities.Triggered.Loki.LightImUpAbility$$
GetPossibleSecondaryTargets` :

    Damageable( SurroundingEnemies(unit = Caster@DSLSelectors+0x48, unitTile = <+0x50>,
                                   range = ConfigConst(0x16) = 3, unique = 1, sel = 3)
                |> Unobscured(Owner@+0x30, _)
                |> _ - Target@+0x60 )

Sept lectures qui ne se devinent pas, et dont AUCUNE ne se generalise depuis un voisin de la liste :

1. **Deux gates, dans cet ordre, et la PREMIERE est une gate de MELEE.** `IsMeleeAttack` est
   `IBattleQuery` **slot 2** (`IdunBattle.Core.Services.BattleQuery$$IsMeleeAttack`, identifie par
   `IdunBattle.Core.Services.DamagePrediction$$IsMeleeAttack` qui appelle le MEME slot sur la MEME
   klass d'interface) :

       if (!ability.HasValue) return false;
       switch (GetAbilityAttackRangeType(ability)) {         // 0 None, 1 Melee, 2 Ranged, 3 Normal
         case 0: return false;
         case 1: return true;
         case 2: return false;
         case 3: return !UnitExtensions.HasFlag(caster, 0x15) && AreEntitiesAdjacent(casterPos, target);
         default: throw new NotImplementedException();
       }

   `0x15` = `UnitFlag.ForceRangedAttack` (21) -- enum LU (`frida/enums.tsv`), pas devine.
   `AreEntitiesAdjacent(UnitPosition, IEntity)` = `MovementUtil$$AreTilesAdjacent` -> foyer
   `battle_query.is_adjacent` (porte d'elevation `|delta| < 2` INCONDITIONNELLE). C'est donc
   l'attaque **DU CASE** qui doit etre en melee -- pas l'ability du passif, qui est `Ranged`.
   Le passif est un contre-attaque au corps a corps qui TIRE : la gate melee et le profil
   `Projectile` cohabitent, et confondre les deux inverserait le port.

2. **Le montant est `Half(Sum(minDmg, maxDmg))`, arrondi DEMI-VERS-LE-PAIR.**
   `IdunBattle.Entities.Abilities.BaseTriggeredAbility$$MinMaxDamageAverage` =
   `Half(Sum(Direct(GetVariableForLevel(0xc)), Direct(GetVariableForLevel(0xd))), mode = 0)` --
   `0xc` = `minDmg`, `0xd` = `maxDmg`, mode `0` = round-half-to-even du foyer
   `entities.formulas._round_fix64`. Ce N'EST PAS `MinMaxDamage` (= `RandomAmount(min, max)`, la
   forme de la face COMBAT) : les deux ne different que sur `min+max == 3 mod 4`, et c'est
   exactement le regime discriminant que `probe_369_playbook_keyspace.py` monte (831 + 1112 = 1943
   -> troncature 971, demi-vers-le-pair 972). L'arbre est evalue contre un `AbilityEntities`
   **entierement nul** (memset 0x128) : ses deux feuilles sont des `Direct`, il n'a besoin d'aucune
   entite -- lire l'entites-nulles comme un bug serait un contresens.

3. **Le canal de prediction est le slot 0x28 = `GetMultiHitAttackPrediction`, pas le 0x23.**
   `IdunBattle.Core.Services.BattleQuery$$GetMultiHitAttackPrediction(attacker, target,
   attackerPosition, ability, damage, damageProfile, hits)` -- SEPT arguments, exactement ceux du
   call-site. Son corps chaine `hits` appels au slot 0x23 (`$$GetAttackPrediction`, dont le litteral
   `1` force `hits = 1` au slot 10 d'`IDamagePredictionQuery`) en threadant
   `DamagePredictionResult.DefaultBlockScenario` d'un coup a l'autre, puis `Add`. C'est mot pour mot
   `services/damage_prediction.get_multi_hit_attack_prediction(hits = 3)` -- le
   `x hits` vit DANS le foyer, il ne se refait pas ici. `psyker`/`avalanche_of_muscle` appellent le
   0x23 nu (hits 1) ; ce playbook-ci est le PREMIER a passer par le 0x28.

3bis. **Le montant PASSE PAR LE SPREAD +/-20 %, il n'est PAS << predefini >>.** C'est une MESURE, pas
   une lecture : sur `orksWarboss` rank 17 (`amount = 1940` -- level 50, multiplicateur de rarete
   200 %), le natif capture pour `ultraTitus` (armure 2312, aucun bouclier)
   `healthDmg = [1047, 1572]` sur 3 coups, soit `[349, 524]` par coup. `0.8 x 1940 x p = 349` et
   `1.2 x 1940 x p = 524` avec `p = 0.225` : les DEUX bornes tombent EXACTEMENT, et un canal
   << predefini >> (min == max) ou un `RandomAmount(minDmg, maxDmg)` (`[1662, 2218] x p x 3 =
   [1122, 1497]`) sont l'un et l'autre REFUTES par ce couple. Le port laisse donc `spread_pct` a son
   defaut.
   ⚠ `#419-r1-tr5-r2` -- FERME, dans CE sens : c'est la lecture ci-dessus qui est juste. `psyker.py`
   et `avalanche_of_muscle.py` ont ete corriges par #449 (capture DIRECTE des bornes natives : 402 ->
   `[322, 482]` la ou `spread_pct=0` rendait `[402, 402]`), et #419-r1-tr14-r3 l'a reconfirme par les
   PALIERS du composite (seuls sensibles au spread) : terme natif +139.368771 en regime `kill`,
   reproduit a 4e-9 au spread par defaut, contre +59.966777 d'ecart a `spread_pct=0`.
   RAISON STRUCTURELLE, qui interdit toute divergence future entre les deux familles : la surcharge
   `casterPosition:IEntity` (slot 0x23) construit un `IdunBattle.Core.UnitPosition$$.ctor` puis
   APPELLE celle a `casterPosition:UnitPosition` (slot 0x24) -- c'est un THUNK, un seul code, un seul
   `request+0x6a = 1`. Detail : `docs/rl/case-419-r1-tr14-r3-spread-paliers-kill.md`.

4. **L'`ability` transmise a la prediction est `case.AbilityType`, JAMAIS 1103.** C'est l'attaque
   EVALUEE par le case (l'attaque normale, garantie par la gate `IsRegularAttack`). Consequence
   directe et non devinable : les gates DSL `IsNormalAttack` / `IsMeleeAttack` /`IsRangedAttack` des
   effets d'attaquant (`IdunBattle.Entities.Triggers.IsMeleeAttackAbilityTrigger$$ShouldTrigger`
   appelle le MEME `IBattleQuery` slot 2 sur l'`AbilityEntities.Ability`) s'evaluent sur l'ATTAQUE
   NORMALE. D'ou `is_normal_attack = True` et `is_ranged = False` dans le builder de modifiers, et
   `ExtraPierceMelee(21)` -- et non `ExtraPierceRanged(22)` -- dans le percage : les deux sont
   DETERMINES par les gates, pas choisis. Le PROFIL, lui, reste celui du PASSIF (`Projectile`),
   passe explicitement en argument.

4bis. **`IsMeleeAttack` SE RE-EVALUE PAR CIBLE dans les modifiers, et ce n'est PAS la gate du corps.**
   La gate (lecture 1) porte sur `case.Target` ; le predicat que consomment les effets d'attaquant
   porte, lui, sur la cible DE LA PREDICTION COURANTE :
   `IdunBattle.Entities.Triggers.IsMeleeAttackAbilityTrigger$$ShouldTrigger` appelle
   `IBattleQuery.<slot 2>(entities.Ability, caster, casterPosition, entities.Target)`, et
   `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` pose `entities.Target =
   request.target`. Une cible SECONDAIRE a 2-3 hex n'est donc pas << en melee >>, meme si le case
   l'etait. MESURE : sur le meme caster et le meme montant, `astraBullgryn` a distance 2 rend
   `2.909806` cote natif contre `4.366376` si l'on force le regime melee (facteur 1.5006 = le
   modifier melee du caster) -- et l'ecart se propageait a `...ForSecondaryTarget` sous la forme
   d'un DECALAGE CONSTANT de `+0.485523` (= 1.456570 / 3 cibles) sur les trois cases dont
   l'ensemble secondaire contenait cette unite, et de ZERO sur celui ou elle etait la cible
   PRINCIPALE. C'est cette signature -- constante et nulle au bon endroit -- qui a nomme la cause.

5. **Les trois sorties sont un arbre de KILL, pas un poids plat.** `pred1` = la prediction de
   l'attaque NORMALE (slot 0x22 = `BattleQuery$$GetNormalAttackPrediction(caster, target,
   casterPosition)`, le meme slot que `SorcerousFacadePlaybook` -- cf.
   `prediction/abilities.py::_PREPEND_NORMAL_ATTACK_EVENT`). Si elle tue A COUP SUR (`WillBeKill`),
   les 3 coups du passif partent tous ailleurs -> SECONDAIRE seul. Sinon on somme `normale + passif`
   (`pred2.Add(pred1)`) : si ce TOTAL ne peut meme pas tuer (`!MightBeKill`), les 3 coups restent sur
   la cible -> PRINCIPAL seul ; sinon on ne sait pas ou ils tombent -> MOYENNE des deux. C'est la
   mise en utilite du << leftover hits >> du tooltip. `will_be_kill` / `might_be_kill` sont les deux
   accesseurs ASYMETRIQUES deja mirrores (`services/damage_prediction.py`).

6. **Le disque des cibles secondaires est ancre sur la TUILE D'ATTAQUE, la visee sur la tuile
   REELLE.** La surcharge appelee est `SurroundingEnemies(unit, unitTile, range, unique,
   unitSelectionType)` -- SIX arguments, dont le 2e est nomme `unitTile` dans la metadata et porte
   TOUTE la geometrie :
   `Enemies(unit, Units(SurroundingTiles(unitTile, includeCenter: 1, range) - Tiles(unitTile), ...))`.
   Le playbook alimente `AbilityEntities.CasterTile` (+0x40) avec `case.CasterPosition.MainTile` --
   il est le SEUL des dix playbooks attack portes a le faire, et c'est ce que le selecteur `<+0x50>`
   consomme. `Unobscured`, lui, prend `Owner@+0x30` (une ENTITE) : sa ligne de vue part de la
   MainTile REELLE du caster (`EntityExtensions$$GetMainTile`), MEME quirk d'ancrage que
   `boltstorm.py` et `SavageEchoesAbility$$GetDamage` (#216). Les deux ancrages coexistent dans le
   MEME arbre ; les confondre deplacerait le disque ou la visee.
   L'ancrage n'est PAS deduit du nom du champ : il est MESURE. Sur une tuile candidate `(4,3)` dont
   le disque de rayon 3 contient `{u79, u81}` la ou celui de la tuile courante contient
   `{u79, u81, u83}`, le natif rend `14.647084008902311` ; la variante du port ancree sur la TUILE
   D'ATTAQUE rend `14.64708400285278` (ecart 6e-9), celle ancree sur la tuile REELLE
   `10.734658006212678`. Les deux variantes DIVERGENT -- le montage discrimine, et il tranche.

7. **La sortie secondaire est une MOYENNE** (`Fix64.op_Division` par `targets.Count`), pas une
   somme -- meme forme que `psyker.py`, et l'inverse de `boltstorm.py` (produit poids x cardinal).
   `Count == 0` rend `Fix64(0)` AVANT tout calcul de montant.

## Face MOVE : `yield Fix64(0)` CONSTANT

`LightImUpPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__1$$MoveNext` est deja
inventorie par #193 comme rendant 0. Elle n'entre donc pas au registre `TRIGGERED_MOVE_PLAYBOOKS`,
et son absence EST le comportement natif (meme forme que `Lakrimae`, `BarbedOvipositor`,
`Neuroparasite`, `AvalancheOfMuscle` et `Boltstorm`).

## Residus NOMMES

* `#419-r1-tr5-r3` -- les branches `Melee(1)` / `Ranged(2)` d'`is_melee_attack` ne sont exercees par
  AUCUN montage, et c'est structurel : `IsRegularAttack` garantit que l'ability du case est une
  attaque NORMALE, dont l'entree n'existe pas au gameconfig (`ab_name_by_id[69] =
  "Loki_NormalAttack"`, `GC.ability(...) -> null`). Le port prend donc toujours la branche
  `Normal(3)`, qui est CELLE QUE LE NATIF PREND pour l'id 69 -- mesure : `astraBullgryn` a 2 hex
  rend `isMeleeAttack: false`, les trois cibles adjacentes `true`. Les deux autres branches sont du
  mirror de fidelite pour un `NormalAttackType` concret qui serait, lui, type au gameconfig (ex.
  `1076 MV71SniperDroneSquadAttack`) : NON CONFRONTEES.

* `#419-r1-tr5-r1` -- `UnitFlag.ForceRangedAttack` (21) n'est pas capture par `combatSnapshot.
  unitFlags` (la Scene n'en stocke que quatre : PreventOverkill / Moved / Teleported /
  ActiveAbilityUsed). Le port le lit donc comme ABSENT. La degradation est PERMISSIVE-EN-PLUS et
  ne mord que sur une attaque normale de type `Normal(3)` dont le porteur serait sous
  ForceRangedAttack tout en etant adjacent -- aucun effet du gameconfig ne pose ce flag sur un
  porteur de `LightImUp`. Le capteur manquant est nomme : ajouter `"ForceRangedAttack"` a la liste
  de `scene._unit_flag_from_snapshot`.
"""
from __future__ import annotations

from fractions import Fraction

import gameconfig as GC

from .. import battle_query as bq
from ..entities.effects import calculate_attacker_modifiers_for_prediction
from ..entities.effects.magnitude import ability_var
from ..entities.formulas import _round_fix64
from ..entities.stats import ARMOR_STAT_TYPES
from ..entities.traits import target_hit_multiplier
from ..entities.traits.factory import TraitFactory
from ..entities.triggered_ability_type import TriggeredAbilityType
from ..services.battle_query import is_melee_attack as _is_melee_attack
from ..services.damage_prediction import get_attack_prediction
from .adjacency import iterate_tiles          # `EntityExtensions$$GetTiles` cote DECISION (#10024)
from .probable_damage_event import ProbableDamageEvent, calculate_utility_from_damage_event
from .prediction._shared import (
    _PROFILE_INDEX, _add_positional_and_defender_mods, _apply_ally_attack_dmg_bonus,
    _entity_traits, _target_damage_limits, prediction_has_moved, prediction_has_teleported
)
from .prediction.normal_attack import make_normal_attack_predictions
from .prediction._shared import _prediction_is_charging, defender_prediction_block_amount
from .prediction._shared import _entity_rarity   # #1025-r1 (rarete de la CIBLE)

# Cle gameconfig de l'ability : le membre d'enum EST le nom de config. Le passer par
# `GC.ability_name(1103)` rendrait `"Supercharge"` (index `ActiveAbilityType`) -- cf. en-tete.
_ABILITY_NAME = TriggeredAbilityType.LightImUp.name          # "LightImUp"
# `GetVariableForLevel(config, 0xc | 0xd, abilityState)` -- les deux bornes de `MinMaxDamageAverage`.
_VAR_MIN_DAMAGE = "minDmg"
_VAR_MAX_DAMAGE = "maxDmg"
# `BaseTriggeredAbility$$GetHits` = `GetNumberConstant(config, 0x2f)` = `constants.nrOfHits` (= 3).
_CONST_HITS = "nrOfHits"
# `LightImUpAbility$$GetPossibleSecondaryTargets` : `GetNumberConstant(config, 0x16)` = `constants.
# range` (= 3), le rayon du disque de cibles secondaires.
_CONST_RANGE = "range"
# `AbilityConfiguration$$GetDamageProfile` = `constants.damageProfile` (= "Projectile").
_CONST_PROFILE = "damageProfile"


class LightImUpPlaybook:
    """`LightImUpPlaybook` (`IdunBattle.AI.Playbook.Loki`, triggered 1103). Seule la face ATTACK a un
    corps ; la face MOVE est un `yield 0` constant au natif (cf. en-tete)."""

    ability_id: int = int(TriggeredAbilityType.LightImUp)     # 0x44f = 1103

    # ---- les trois lectures de config, communes aux trois call-sites natifs ------------------
    def _ability_state(self, scene, uid: int):
        """`TriggeredAbilityPlaybook<T>$$GetAbilityState(caster)` -> le couple `(Level,
        VariableMultiplierPercentage)` PER-ABILITY (`ActiveAbility._abilityState`, canal #100
        `scene.ability_state`). Repli sur le canal GLOBAL quand le capteur per-ability manque --
        MEME cascade qu'`avalanche_of_muscle.py`."""
        st = scene.ability_state(uid, self.ability_id) or {}
        lvl = st.get("level")
        if lvl is None:
            lvl = (scene.ablvl_by_id or {}).get(uid)
        mult = st.get("multiplier")
        if mult is None:
            mult = (scene.mult_by_id or {}).get(uid)
        return lvl, int(mult or 100)

    def _average_damage(self, scene, uid: int):
        """`MassiveScythingTalonsAbility$$GetAverageDamage` (corps DEDUPLIQUE de
        `BaseTriggeredAbility$$MinMaxDamageAverage` -- le nom de la table est un mislabel de
        deduplication, la STRUCTURE tranche) = `Half(Sum(Direct(minDmg), Direct(maxDmg)), 0)`,
        evalue par `<IAmountFormula slot 1>` = arrondi DEMI-VERS-LE-PAIR (`_round_fix64` mode 0).
        `None` si l'une des deux variables manque."""
        lvl, mult = self._ability_state(scene, uid)
        lo = ability_var(_ABILITY_NAME, _VAR_MIN_DAMAGE, lvl, multiplier_pct=mult)
        hi = ability_var(_ABILITY_NAME, _VAR_MAX_DAMAGE, lvl, multiplier_pct=mult)
        if lo is None or hi is None:
            return None
        return int(_round_fix64(Fraction(int(lo) + int(hi), 2), 0))

    @staticmethod
    def _hits() -> int:
        """`BaseTriggeredAbility$$GetHits` = `AbilityConfiguration.GetNumberConstant(0x2f)`."""
        return int(ability_var(_ABILITY_NAME, _CONST_HITS, is_constant=True) or 0)

    @staticmethod
    def _secondary_range() -> int:
        """`LightImUpAbility$$GetPossibleSecondaryTargets` : `GetNumberConstant(0x16)` = le rayon."""
        return int(ability_var(_ABILITY_NAME, _CONST_RANGE, is_constant=True) or 0)

    @staticmethod
    def _profile_name() -> str:
        """`BaseTriggeredAbility$$GetDamageProfile` = `AbilityConfiguration$$GetDamageProfile`."""
        return (((GC.ability(_ABILITY_NAME) or {}).get("constants") or {}).get(_CONST_PROFILE)
                or "")

    # ---- mirror de la gate `IBattleQuery` slot 2 ---------------------------------------------
    @staticmethod
    def is_melee_attack(ctx, scene, ability_id, attack_tile, tgt_pos) -> bool:
        """`TriggeredAbilityPlaybook<T>$$IsMeleeAttack(case)` -> `IBattleQuery` slot 2 =
        `BattleQuery$$IsMeleeAttack(case.AbilityType, caster, casterPosition, target)` (cf. en-tete,
        lecture 1). `AttackRangeType` : 0 None -> faux, 1 Melee -> vrai, 2 Ranged -> faux,
        3 Normal -> `!HasFlag(caster, ForceRangedAttack) && AreEntitiesAdjacent(casterPos, target)`.

        Le type de portee vient de `GetAbilityAttackRangeType` = la config de l'ability EVALUEE
        (`gameconfig.attackRangeType`). Les attaques normales CONCRETES (id per-unite) n'ont pas
        d'entree nommee au gameconfig : elles retombent donc sur la branche `Normal(3)`, qui est
        precisement la semantique << melee si adjacent >>. `ForceRangedAttack` : cf. le residu
        `#419-r1-tr5-r1` de l'en-tete (lu comme absent).

        FOYER (#419-r1-tr14) : le corps a migre dans `services/battle_query.is_melee_attack` --
        `HeavyBoltPistolPlaybook` consomme le MEME slot 2, et le natif n'a qu'UNE fonction. Cette
        methode reste l'ADAPTATEUR `(ctx, scene, ability_id)` -> `(nom d'ability, elevations)`.

        `tgt_pos` accepte desormais une TUILE **ou une EMPREINTE** (#10024) : la surcharge que le
        natif appelle est `IdunBattle.Core.Services.BattleQuery$$AreEntitiesAdjacent(tiles:IList<IEntity>,
        unit:IEntity)`, qui commence par `tiles2 = EntityExtensions.GetTiles(unit, state)` -- donc
        l'empreinte COMPLETE de la cible. Les deux call-sites de ce playbook passent desormais
        `playbook.adjacency.iterate_tiles`, le foyer DECISION de `GetTiles`.
        ⚠ `attack_tile`, lui, reste une TUILE et c'est un residu NOMME : le 3e parametre natif est
        une `IdunBattle.Core.UnitPosition`, et `IdunBattle.Core.Services.MovementQuery$$GetMovablePositionsFor`
        rend `IOrderedSet<UnitPosition>` -- pour une unite MULTI-HEX, une position candidate est un
        ENSEMBLE de tuiles, que la face DECISION du port ne materialise pas. Exact pour tout caster
        a un pied (le cas de tous les heros), SOUS-ESTIME pour un caster multi-hex."""
        if ability_id is None or attack_tile is None or not tgt_pos:
            return False
        name = (getattr(ctx, "ab_name_by_id", None) or {}).get(int(ability_id))
        return _is_melee_attack(name, attack_tile, tgt_pos,
                                getattr(scene, "elev_by_pos", None),
                                neigh_by_pos=bq.neigh_map(scene))

    # ---- mirror du slot 0x28 : `GetMultiHitAttackPrediction` ---------------------------------
    def _predict_extra_vs_target(self, scene, att_id: int, tgt_id: int, amount: int, hits: int,
                                 attack_tile, profile_name: str, is_melee: bool):
        """`IBattleQuery` slot 0x28 = `BattleQuery$$GetMultiHitAttackPrediction(caster, target,
        casterPosition, case.AbilityType, amount, profil, hits)` : `hits` coups CHAINES d'un montant
        PREDEFINI (spread 0), chacun passant par le slot 0x23 avec `hits = 1` et le
        `DefaultBlockScenario` du precedent. Le foyer `get_attack_prediction` -> `get_multi_hit_
        attack_prediction` EST cette boucle (cf. en-tete, lecture 3).

        `is_normal_attack=True` vient de la gate `IsRegularAttack` du corps : elle garantit que
        l'`ability` que le natif transmet a la requete -- `case.AbilityType` -- EST une attaque
        normale (en-tete, lecture 4). Le PROFIL reste celui du passif (`Projectile`).

        `is_melee`, LUI, SE RE-EVALUE PAR CIBLE, et ce n'est pas la gate du corps (en-tete, lecture
        4bis) : `IsMeleeAttackAbilityTrigger$$ShouldTrigger` interroge
        `IBattleQuery.IsMeleeAttack(entities.Ability, caster, casterPosition, entities.TARGET)`, et
        `PredictAttackRaw` pose `entities.Target = request.target` -- la cible DE CETTE PREDICTION,
        pas celle du case. Il commande `is_ranged` du builder de modifiers, la direction du percage
        (`ExtraPierceMelee(21)` vs `ExtraPierceRanged(22)`) et les faces positionnelle/alliee."""
        actx = scene.ctx(att_id)
        if actx is None or amount is None or int(amount) <= 0 or int(hits) <= 0:
            return None
        prof = GC.damage_profile(profile_name) or {}
        dir_pierce = actx.extra_pierce_melee if is_melee else actx.extra_pierce_ranged
        pierce = max(0, min(100, int(prof.get("PiercingRatio") or 0)
                            + actx.extra_pierce + dir_pierce))
        _hm = prediction_has_moved(scene, att_id, attack_tile)
        _tctx = scene.ctx(tgt_id)
        _tar = (_tctx.stats.has_negative_modifier(ARMOR_STAT_TYPES)
                if _tctx is not None and _tctx.stats is not None else None)
        _tgt_traits = _entity_traits(scene, tgt_id)
        mods = calculate_attacker_modifiers_for_prediction(
            scene.effects(att_id), is_ranged=not is_melee, has_moved=_hm, is_normal_attack=True,
            target_traits=_tgt_traits, target_armor_reduced=_tar,
            att_ctx={"att_pos": attack_tile,
                     "tile_effects_by_pos": scene.tile_effects_by_pos,
                     "is_charging": _prediction_is_charging(scene, att_id, attack_tile, tgt_id),
                     "has_teleported": prediction_has_teleported(scene, att_id, attack_tile),
                     "att_grand_alliance": (GC.unit(scene.vis_by_id.get(att_id))
                                            or {}).get("GrandAllianceId"),
                     "damage_profile": profile_name,
                     "t_pos": scene.pos(tgt_id),
                     "tgt_team": scene.team(tgt_id),
                     # #1025-r1 -- `HasRarity(Target@<DSLSelectors+0x60>, idun.meta.Rarity
                     # .Mythic = 5)` + `AreFriends(Target@<DSLSelectors+0x60>, EffectSource(
                     # Effect@<DSLSelectors+0x38>))`, les deux conjoints utiles d'`Electrochaff
                     # Backups_DamageReductionPct` (1446). Son `$$CreateDamageModifier` ne porte
                     # NI `IsNormalAttack` NI `IsMeleeAttack` -> il entre AUSSI sur ce vecteur.
                     # MEMES cles que la normale et que la face COMBAT -- pas de fork. TRI-ETAT
                     # sur la rarete (`None` = non mesure -> gate FERME), cf. `_entity_rarity`.
                     "tgt_rarity": _entity_rarity(scene, tgt_id),
                     "team_by_id": scene.team_by_id})
        _add_positional_and_defender_mods(mods, scene, att_id, tgt_id, is_melee, attack_tile,
                                          scene.pos(tgt_id), damage_profile=profile_name,
                                          is_normal_attack=True)
        _apply_ally_attack_dmg_bonus(mods, scene, att_id, attack_tile, is_melee, _tar,
                                     tgt_id=tgt_id, is_normal_attack=True,
                                     damage_profile=profile_name)
        hit_mult = target_hit_multiplier(TraitFactory.create_many(_tgt_traits))
        return get_attack_prediction(
            target_current_health=scene.hp(tgt_id) or 0, initial_damage=int(amount),
            hits=int(hits),                          # slot 0x28 : la boucle multi-coups EST ici
            profile_type=_PROFILE_INDEX.get(profile_name, 0), pierce_pct=pierce,
            armor=scene.armor(tgt_id), mods=mods, hit_mult=hit_mult,
            # spread_pct : le DEFAUT (+/-20 %) -- MESURE, cf. en-tete lecture 3bis.
            target_shield=scene.shield(tgt_id),
            target_limits=_target_damage_limits(scene, tgt_id, profile_name),
            target_prevents_overkill=scene.prevents_overkill(tgt_id),
            defender_block_amount=defender_prediction_block_amount(scene, tgt_id, profile_name),
            attacker_effects=scene.effects(att_id),
            attacker_ctx=actx)

    # ---- mirror `LightImUpAbility$$GetPossibleSecondaryTargets` ------------------------------
    def possible_secondary_targets(self, scene, att_id: int, case_tgt_id: int,
                                   attack_tile) -> list:
        """`Damageable( (SurroundingEnemies(Caster@+0x48, <CasterTile @+0x50>, range = 3,
        unique: 1, sel: 3) |> Unobscured(Owner@+0x30)) - Target@+0x60 )`, evalue contre
        l'`AbilityEntities` que `CalculateAttackUtilityForSecondaryTarget` construit
        (`Actor = Caster = Owner = case.Caster`, `Target = case.Target`,
        `CasterTile = case.CasterPosition.MainTile`).

        Les trois gates, dans l'ordre natif : ennemi VIVANT du caster (`Enemies` + `Damageable`),
        a distance <= `range` de la TUILE D'ATTAQUE (`SurroundingTiles(unitTile, includeCenter: 1,
        range) - Tiles(unitTile)` -> disque cube MOINS le centre), et non obscurci depuis la tuile
        REELLE du caster (`Unobscured(Owner)`, cf. en-tete lecture 6). La cible du case est retiree
        par `op_Subtraction`.

        Degradations, toutes NOMMEES : cible/caster sans position -> liste vide (le natif deref sans
        garde, il n'a pas de repli a mirrorer) ; `range <= 0` -> liste vide (disque vide)."""
        rng = self._secondary_range()
        cpos = scene.pos(att_id)
        if rng <= 0 or cpos is None or attack_tile is None:
            return []
        cteam = scene.team(att_id)
        if cteam is None:
            return []
        elev = getattr(scene, "elev_by_pos", None)
        foes, pos_by_uid = [], {}
        for u in (scene.units or ()):
            uid = u.get("id")
            if uid is None or uid == att_id or uid == case_tgt_id:
                continue                                   # `- Target@+0x60` (et le caster n'est
                                                           #  jamais son propre ennemi)
            if not u.get("alive") or u.get("team") == cteam:
                continue                                   # `Enemies(Caster, ...)` + `Damageable`
            p = scene.pos(uid)
            if p is not None:
                foes.append(p)
                pos_by_uid[uid] = p
        # `SurroundingEnemies(..., unitTile = CasterTile, ...)` : disque cube autour de la TUILE
        # D'ATTAQUE, centre retire (`- Tiles(unitTile)`).
        in_range = bq.surrounding_enemies_in_range(tuple(attack_tile), foes, rng)
        out = []
        for uid, p in pos_by_uid.items():
            if (p[0], p[1]) not in in_range:
                continue
            # `Unobscured(Owner@+0x30, _)` -- ligne de vue depuis la MainTile REELLE du caster.
            if bq.is_target_tile_obscured(cpos, (p[0], p[1]), elev):
                continue
            out.append(uid)
        return out

    # ---- les deux methodes PROPRES du playbook ------------------------------------------------
    def _predict_and_score(self, ctx, attacker_uid: int, ability_id, tgt_id: int, amount: int,
                           hits: int, attack_tile, profile_name: str):
        """Prediction du passif vs `tgt_id` (slot 0x28) -> `CalculateUtilityFromDamageEvent`
        (composite Damage standard, hpmax EFFECTIF). `is_melee` est re-evalue POUR CETTE CIBLE
        (en-tete, lecture 4bis) -- c'est le foyer unique des trois call-sites natifs."""
        sc = ctx.scene
        # `AreEntitiesAdjacent(casterPosition, target)` prend l'EMPREINTE de la cible (#10024) --
        # `iterate_tiles` est le foyer DECISION de `EntityExtensions$$GetTiles`, et il degrade
        # tout seul sur la MainTile quand aucun canal de pieds n'est capte.
        melee = self.is_melee_attack(ctx, sc, ability_id, attack_tile, iterate_tiles(sc, tgt_id))
        pred = self._predict_extra_vs_target(sc, attacker_uid, tgt_id, amount, hits, attack_tile,
                                             profile_name, melee)
        if pred is None:
            return None, None
        ev = ProbableDamageEvent(target=tgt_id, prediction=pred)
        return pred, calculate_utility_from_damage_event(ev, ctx.wt,
                                                         (ctx.hpmax_by_id or {}).get(tgt_id))

    def calculate_attack_utility_for_main_target(self, ctx, attacker_uid: int, ability_id,
                                                 case_tgt_id: int, attack_tile, hits: int) -> float:
        """`LightImUpPlaybook$$CalculateAttackUtilityForMainTarget(case, hits)` : la prediction du
        passif vs la cible du case -> `CalculateUtilityFromDamageEvent`.

        `ability_id` = `case.AbilityType`, que le natif relit DANS le case : le port l'eclate en
        parametre, il n'est pas ajoute."""
        amount = self._average_damage(ctx.scene, attacker_uid)
        _pred, u = self._predict_and_score(ctx, attacker_uid, ability_id, case_tgt_id, amount,
                                           hits, attack_tile, self._profile_name())
        return 0.0 if u is None else u

    def calculate_attack_utility_for_secondary_target(self, ctx, attacker_uid: int, ability_id,
                                                      case_tgt_id: int, attack_tile,
                                                      hits: int) -> float:
        """`LightImUpPlaybook$$CalculateAttackUtilityForSecondaryTarget(case, hits)` : MOYENNE des
        utilites de la MEME prediction portee sur chaque cible secondaire possible. `Count == 0`
        rend 0 AVANT tout calcul de montant (ordre natif)."""
        sc = ctx.scene
        targets = self.possible_secondary_targets(sc, attacker_uid, case_tgt_id, attack_tile)
        if not targets:
            return 0.0
        amount = self._average_damage(sc, attacker_uid)
        profile_name = self._profile_name()
        total = 0.0
        for uid in targets:
            _pred, u = self._predict_and_score(ctx, attacker_uid, ability_id, uid, amount, hits,
                                               attack_tile, profile_name)
            if u is not None:
                total += u
        return total / len(targets)                  # `Fix64.op_Division` par `targets.Count`

    # ---- mirror `<CalculateAttackUtilityInStepsInternal>d__2$$MoveNext` -----------------------
    def calculate_attack_utility_in_steps(self, ctx, attacker_uid: int, ability_id: int,
                                          case_tgt_id: int, attack_tile, prediction=None) -> float:
        """Mirror du corps natif (cf. en-tete), dans l'ORDRE des cinq etats.

        `prediction` (`case.DamagePrediction`) est ACCEPTE et IGNORE : le corps natif ne lit pas
        `UtilityAttackCase@+0x28` -- il RECALCULE la prediction de l'attaque normale par le slot
        0x22 (`GetNormalAttackPrediction`), qui est un artefact DISTINCT du champ du case."""
        sc = getattr(ctx, "scene", None)
        if sc is None or attack_tile is None:
            return 0.0
        tpos = iterate_tiles(sc, case_tgt_id)      # EMPREINTE de la cible (#10024), pas sa MainTile
        # etat 1 -- `IsMeleeAttack(case)` : l'attaque DU CASE doit etre en melee.
        if not self.is_melee_attack(ctx, sc, ability_id, attack_tile, tpos):
            return 0.0
        # etat 2 -- `IsRegularAttack(case)` = `StaticBattleRules.ActiveAbility$$IsRegularAttack`
        # sur `case.AbilityType` : l'ability evaluee est l'attaque NORMALE de l'unite.
        if ability_id is None or int(ability_id) not in (ctx.normal_ids or ()):
            return 0.0
        hits = self._hits()
        amount = self._average_damage(sc, attacker_uid)
        if hits <= 0 or not amount:
            return 0.0
        # `pred1` = slot 0x22 `GetNormalAttackPrediction(caster, target, casterPosition)`.
        ev1 = make_normal_attack_predictions(sc, attacker_uid, case_tgt_id, attack_tile)
        pred1 = getattr(ev1, "prediction", None) if ev1 is not None else None
        if pred1 is None:
            return 0.0
        # etat 3 -- l'attaque normale tue A COUP SUR : les `hits` coups partent tous ailleurs.
        if pred1.will_be_kill():
            return self.calculate_attack_utility_for_secondary_target(
                ctx, attacker_uid, ability_id, case_tgt_id, attack_tile, hits)
        pred2, main = self._predict_and_score(ctx, attacker_uid, ability_id, case_tgt_id, amount,
                                              hits, attack_tile, self._profile_name())
        if pred2 is None:
            return 0.0
        pred2.add(pred1)                             # `DamagePredictionResult$$Add` (normale + passif)
        # etat 4 -- meme le TOTAL ne peut pas tuer : les `hits` coups restent sur la cible.
        if not pred2.might_be_kill():
            return main
        # etat 5 -- issue indeterminee : MOYENNE des deux scenarios.
        sec = self.calculate_attack_utility_for_secondary_target(
            ctx, attacker_uid, ability_id, case_tgt_id, attack_tile, hits)
        return (main + sec) / 2.0


__all__ = ["LightImUpPlaybook"]
