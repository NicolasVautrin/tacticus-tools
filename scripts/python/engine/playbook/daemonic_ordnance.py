"""`DaemonicOrdnancePlaybook` (1148) — SECOND membre de la route de decision a cibles TUILE.

## L'artefact natif, lu en entier

`IdunBattle.AI.Playbook.Loki.DaemonicOrdnancePlaybook$$CalculateCustomUtility(caster, casterPosition,
target, abilityState, possibleTargets)` :

    sel = DaemonicOrdnanceAbility.GetTargetAreaTiles();               // arbre DSL (zone de tir)
    ent = AbilityEntities(owner: caster, caster: null, target: target);
    x   = Fix64(0);
    foreach (tileEntity in TargetsSelector.<slot 10>(sel, ent)) {     // Select, pas Count
        unit = UnitExtensions.GetUnit(tileEntity, state);             // occupant de la tuile
        if (unit != null && UnitExtensions.IsEnemy(unit, caster, state))
            x = Fix64.op_Addition(x, Fix64(0xa));                     // <-- CONSTANTE EN DUR
    }
    return x;

Quatre lectures que le decompile impose, et que le port respecte :

1. **`10` est une CONSTANTE DU BINAIRE, pas un poids de `BattleConfiguration`.** Le corps appelle
   `FixMath_NET_Fix64__op_Implicit(0xa)` et JAMAIS
   `IdunBattle.AI.Playbook.Playbooku003C__Il2CppFullySharedGenericTypeu003E$$GetUtilityValue` —
   contraste NET avec 1169, dont le meme terme passe par `GetUtilityValue(
   "PlagueburstMortar_AdjacentEnemy")`. Ne PAS aller chercher une cle dans `BC.Utilities` : il n'y en
   a pas, et en inventer une rendrait le terme dependant d'une table qui ne le pilote pas.
2. **La boucle est IMPERATIVE, seul l'ENSEMBLE est un arbre DSL.** Le natif n'appelle ni un selecteur
   `Enemies(...)` ni un `Count` : il ITERE les entites-tuiles et resout l'occupant de chacune. Le port
   mirrore cette forme (arbre DSL pour la zone, boucle pour le comptage) au lieu de recabler
   `Count(Enemies(Units(zone)))` — qui DEDOUBLONNERAIT par unite, la ou le natif compte PAR TUILE.
3. **`casterPosition` n'entre PAS dans l'`AbilityEntities`** (meme lecture que 1169) : le terme custom
   est INDEPENDANT de la tuile depuis laquelle le caster tire. Ce qui reste position-dependant, c'est
   le terme `Tile(7)` ajoute en aval par `CalculateActionUtility`.
4. **Le slot `caster` de l'`AbilityEntities` est NUL ici** (`ctor(entities, caster, 0, target, ...)`,
   la ou 1169 passe `ctor(entities, caster, caster, target, ...)`). Sans consequence : l'arbre
   `GetTargetAreaTiles` ne lit que `target@0x178` et l'etat de tour ; le `caster` du test d'ennemi est
   l'ARGUMENT de la fonction, pas un slot de l'`AbilityEntities`.

`IdunBattleLogic.Entities.Abilities.Active.Loki.DaemonicOrdnanceAbility$$GetTargetAreaTiles` :

    dir = If( IsPositionMachineForCurrentPlayer(2), Direct(1), Direct(4) )
    return TilesOnSameElevation( target@0x178, TilesInTriangleShape(target@0x178, dir), maxDiff = 1 )

C'est le MEME artefact que la face COMBAT (portee par #90) : le port appelle donc
`engine.runner.abilities.blacklegion.daemonic_ordnance_target_area_tiles`, il ne le recable pas.
`target@0x178` est une entite TUILE (masque `...DaemonicOrdnanceAbility$$.ctor` = `0x46000040`, bit 6
`TargetIsTile`), d'ou `FixedTileIds([target])` comme vehicule de collapse — exactement comme la face
COMBAT (`blacklegion.DaemonicOrdnanceAbility.execute_behaviour`).

⚠ `If(IsPositionMachineForCurrentPlayer(2), 1, 4)` fait dependre la GEOMETRIE de la zone du cote du
plateau ou la MoW du joueur COURANT est deployee. Ce predicat n'avait aucun canal cote DECISION avant
cette tranche : il rendait False d'office, donc `dir = 4` TOUJOURS, et la zone etait la mauvaise des
que le joueur courant avait sa MoW en `Bottom`. Le canal est desormais
`decisionView.mows[].owner/.slot` -> `AiDecisionContext.mow_slot_by_player` ->
`tile_targets.dsl_context_for_tile_target`.

## Pourquoi la route NON-ATTAQUE et pas `_best_attack`

Meme raison que 1169 : 1148 a un `damageProfile` (Plasma), donc `state_bridge._is_attack_ability` la
laisse entrer dans les `attackPlans` — mais la structure d'affichage par-unite ne range pas une ability
qui cible une TUILE, si bien que `_best_attack` (qui consomme `ranked`) ne peut structurellement rien en
faire. Le critere reel de la route non-attaque est « Comparable **invisible de `_best_attack`** »
(cf. l'en-tete de `nonattack.py`), et 1148 y repond.

## Les DEUX termes de `CalculateActionUtility` sont portes (#359-r3)

`ComparablePlaybook<T>.CalculateActionUtility` somme `custom + CalculateUtilityFromPredictions(
MakeDamagePredictions(...))`.

- **custom** — `CalculateCustomUtility` ci-dessus (`case-302` tranche 3).
- **prediction** — `MakeDamagePredictions`, cf. la docstring de la methode. Le playbook a un corps
  BESPOKE : il boucle sur `GetEntitiesFromSelector(DaemonicOrdnanceAbility$$GetAllDamageableTargets,
  ...)`, jamais sur `<Target>` — et pour cause, `<Target>` est ici une entite TUILE, qui ne prend
  aucun degat. Jusqu'a #359-r3 ce terme valait `0` cote port par le seul heritage de
  `NonAttackComparablePlaybook.make_damage_predictions` (qui rend `[]`), alors que la MECANIQUE
  etait portee et confrontee depuis #359-r1 : il ne manquait que le BRANCHEMENT.

`GetAllDamageableTargets` = **les ennemis debout sur une tuile DEJA EN FEU** de la zone. Or c'est ce
meme cast qui POSE le feu, en DERNIER etage de son behaviour (`ExecuteBehaviour` [5]
`AddEffect(Fire -> zone)`) : sur une zone qui ne brule pas encore, le selecteur rend l'ensemble VIDE
et la somme des predictions vaut REELLEMENT `0`. Le terme n'est donc VISIBLE que dans le regime
« zone deja embrasee » — d'ou un montage de validation qui CASTE 1148 une premiere fois avant de
mesurer la decision suivante (aucun autre chemin ne pose ce feu).

⚠ Ce que le branchement CHANGE, et qu'il faut savoir avant de lire un test rouge : des que la zone
brule, l'utilite d'action de 1148 monte de la somme des `CalculateUtilityFromDamageEvent` de ses
events. La garde `test_prediction_term_is_zero_because_the_area_is_not_burning` (#359-r1) encodait
l'ANCIEN comportement « toujours zero » ; elle a ete REECRITE en une garde de REGIME (zero sur zone
froide, non-zero sur zone en feu) — c'est le contrat natif, pas une constante.
"""
from __future__ import annotations

from ..entities.active_ability_type import ActiveAbilityType
from ..entities.selectors.accessors import FixedTileIds
from ..runner.abilities.blacklegion import (DAEMONIC_ORDNANCE_ID,
                                            daemonic_ordnance_all_damageable_targets,
                                            daemonic_ordnance_target_area_tiles)
import engine.playbook.prediction as prediction   # sous-paquet FRERE, pas `from . import` (#270-r4-r2)
from .prediction.abilities import _PLAYBOOK_PROFILE_OVERRIDE
from .nonattack import NonAttackComparablePlaybook, register_nonattack
from .probable_damage_event import ProbableDamageEvent
from .tile_targets import dsl_context_for_tile_target, unit_on_tile


class DaemonicOrdnancePlaybook(NonAttackComparablePlaybook):
    """`IdunBattle.AI.Playbook.Loki.DaemonicOrdnancePlaybook` — cf. l'en-tete du module."""

    __slots__ = ()
    ability_id = int(ActiveAbilityType.DaemonicOrdnance)           # 0x47c = 1148
    ability_name = DAEMONIC_ORDNANCE_ID                            # cle gameconfig
    # `FixMath_NET_Fix64__op_Implicit(0xa)` litteral du corps natif — AUCUN `GetUtilityValue`, donc
    # AUCUNE cle `BC.Utilities` (contraste avec `PlagueburstMortar_AdjacentEnemy` de 1169).
    ENEMY_IN_AREA = 10.0

    def calculate_custom_utility(self, ctx, caster_tile, target, ability_id) -> float:
        """`DaemonicOrdnancePlaybook$$CalculateCustomUtility` — mirror 1:1.

        `caster_tile` est ignore PARCE QUE LE NATIF L'IGNORE : son `AbilityEntities` ne porte que
        `owner`/`target`, jamais `casterPosition`.

        Contexte DSL indisponible (Scene ou board absents) -> `0.0` : aucune utilite INVENTEE. La
        degradation est conservatrice — l'action reste generee par la route avec `u = 0`, elle perd
        seulement sa preference — et elle est visible (`probe_302_3 --stage`)."""
        dctx = dsl_context_for_tile_target(ctx)
        if dctx is None or target is None:
            return 0.0
        caster_team = (dctx.caster or {}).get("team")
        area = daemonic_ordnance_target_area_tiles(FixedTileIds([int(target)])).select(dctx)
        total = 0.0
        for tile in (area or []):
            # `UnitExtensions.GetUnit(tileEntity, state)` puis `UnitExtensions.IsEnemy(unit, caster,
            # state)` — ce dernier compare `GetCurrentPlayer(x).Team.Index` des deux cotes, ce que le
            # substrat de decision expose en `unit["team"]` (meme convention que le noeud `Enemies`).
            # PAS de dedoublonnage : le natif accumule PAR TUILE (la zone, elle, est deja un HashSet
            # de 3 tuiles au plus, `BattleQuery$$GetTilesInTriangleShape`).
            u = unit_on_tile(dctx, tile)
            if u is not None and u.get("team") != caster_team:
                total += self.ENEMY_IN_AREA
        return total

    def make_damage_predictions(self, ctx, caster_tile, target, ability_id):
        """`DaemonicOrdnancePlaybook$$MakeDamagePredictions` — mirror 1:1 :

            list = new List<ProbableDamageEvent>()
            sel  = DaemonicOrdnanceAbility$$GetAllDamageableTargets()
            hits = AActiveAbility$$GetHits()                                     # HORS boucle
            foreach (e in Playbook<T>$$GetEntitiesFromSelector(sel, caster, casterPosition, target)) {
                damage = DaemonicOrdnanceAbility$$GetDamage(Entity(e), state, isPrediction: 1)
                list.AddRange(ComparablePlaybook<T>$$GenerateMultiHitAttackPredictions(
                                  caster, casterPosition, e, DSLSelectors$$Entity(e),
                                  damage, hits, 0, Nullable<DamageProfile>(null), 0))
            }
            return list

        QUATRE lectures que le decompile impose, et qu'il faut avoir avant de porter :

        1. **Il n'y a PAS de « cible principale ».** Le corps ne predit rien sur `<Target>` : il
           boucle sur les entites de SON selecteur. C'est structurel ici — `<Target>` est une entite
           TUILE (masque `...DaemonicOrdnanceAbility$$.ctor` = `0x46000040`, bit 6 `TargetIsTile`),
           qui ne prend aucun degat. La forme « main + AoE » de
           `engine.playbook.prediction.make_damage_predictions` est le mirror du regime a cible
           UNITE (celui de l'oracle `aiPlaybookPredict`, #359-r1) ; sur la route de DECISION, ou la
           cible est une tuile, c'est la BOUCLE qui est le mirror — donc cet override, exactement
           comme `PlagueburstMortarPlaybook.make_damage_predictions`.
        2. **`GetDamage` est evalue DANS la boucle mais IGNORE son argument `target`** : son corps
           est `IdunBattle.Entities.Abilities.AActiveAbility$$MinMaxDamage(state, isPrediction)`
           SEUL. La base est donc la meme pour toutes les entites -> le chemin generique par cible
           (`generate_multi_hit_attack_prediction`) est EXACTEMENT le bon, rien a surcharger.
        3. **`param_8 = Nullable<DamageProfile>(null)`** — pierce 0, armure PLEINE (#172). La valeur
           est LUE dans `_PLAYBOOK_PROFILE_OVERRIDE[1148]`, foyer unique deja confronte live par
           #350-r3/#359-r1 : la recopier ici en litteral creerait un second foyer, donc une
           divergence possible entre les deux faces de la meme prediction.
        4. **Aucun poids** (`param_10 = 0`) -> `probability2 = Fix64(1)` ; aucun event SELF
           (`GetHealthToLose` absent du corps) ; aucun plafond secondaire.

        `caster_tile` EST utilise (contrairement au custom) : le natif passe `casterPosition` a
        `GenerateMultiHitAttackPredictions`, qui la forwarde a `PredictAttack` — d'ou
        `attack_pos = caster_tile`, qui porte les modificateurs positionnels et le gate `HasMoved`.

        Contexte DSL indisponible -> `[]` : le terme de prediction est alors NUL, jamais invente.
        Meme degradation que le custom, et elle est visible (`probe_302_3 --stage`)."""
        dctx = dsl_context_for_tile_target(ctx)
        if dctx is None or target is None or getattr(ctx, "scene", None) is None:
            return []
        # Lecture SEULE du registre de profils de la face PREDICTION (cf. point 3). L'import est
        # MODULE-LEVEL depuis #270-r4-r2 (le cycle `playbook <-> playbook.*` qui l'imposait est mort).
        profile = _PLAYBOOK_PROFILE_OVERRIDE.get(int(ability_id))
        sel = daemonic_ordnance_all_damageable_targets(FixedTileIds([int(target)]))
        events = []
        for u in (sel.select(dctx) or []):
            tid = u.get("id") if isinstance(u, dict) else None
            if tid is None:
                continue
            dp = prediction.generate_multi_hit_attack_prediction(
                ctx.scene, ctx.uid, int(tid), int(ability_id), self.ability_name,
                attack_pos=caster_tile, profile_override=profile)
            if dp is not None:
                events.append(ProbableDamageEvent(target=int(tid), prediction=dp))
        return events


register_nonattack(DaemonicOrdnancePlaybook())
