"""`IdunBattle.AI.Utilities.DevoutPush_AdjacentRangedEnemies` (UtilityType **53**) -- l'UNIQUE
utilite du bucket que `IdunBattleLogic.Entities.Abilities.Active.Loki.DevoutPushAbility$$.ctor`
construit et range en `<ability>+0xf0`, puis passe en 3e argument de
`IdunBattleLogic.Entities.DSLBehaviors$$PerformAIMovement`. (#996-r1)

`53` est RE-DERIVE du build courant, pas recopie : `data/symbols/<build>/frida/enums.tsv`,
`IdunBattle.Configuration.UtilityType` -> `53=DevoutPush_AdjacentRangedEnemies` sur `rnca9r7q6c`.
Le port n'ecrit donc JAMAIS le litteral, il passe par le MEMBRE.

CORPS NATIF, remis en C# depuis
`IdunBattle.AI.Utilities.DevoutPush_AdjacentRangedEnemies.u003CEvaluateMovementInStepsu003Ed__2$$MoveNext`
(relu au decompile pour cette tranche, pas herite de la fiche #907) :

    IEnumerator<Fix64> EvaluateMovementInSteps(UtilityMovementCase c) {
        if (c.unit != null
            && EntityExtensions.GetMainTile(c.unit, this.<+0x10>)
               == c.UnitPosition.get_MainTile()) {
            yield return Fix64.op_Implicit(-10);        // 0xfffffff6 -- LITTERAL, pas une cle BC
            yield break;                                // <- un SEUL step dans cette branche
        }
        sel     = this.<+0x18>.<+0x90>;                             // DSLSelectors
        subject = DSLSelectors.Get(sel, c.unit);
        tileEnt = DSLSelectors.Get(sel, c.UnitPosition.get_MainTile());   // la tuile CANDIDATE
        adj     = DSLSelectors.AdjacentUnits(sel, tileEnt, unique: 1, selectionType: 3);
        enemies = DSLSelectors.Enemies(sel, subject, adj, 3);
        int v = 0;
        foreach (u in TargetsSelector.SelectAllUnits(enemies, <AbilityEntities ZEROEES>, 3))
            v += UnitExtensions.HasRangedWeapon(u, minRange: null)
                 ? weights["DEVOUTPUSH_AdjacentRangedEnemy"]
                 : weights["DEVOUTPUSH_AdjacentMeleeEnemy"];
        yield return Fix64.op_Implicit(v);
    }

TROIS points LUS, et aucun n'est devinable du nom :

* **le `-10` est un LITTERAL de code, pas un poids BC.** `FixMath.NET.Fix64$$op_Implicit(0xfffffff6)`
  = `-10`. Rester sur sa tuile courante est penalise ; c'est ce terme-la, et lui seul, qui fait
  BOUGER l'unite quand aucun ennemi n'est adjacent a aucune candidate (a utilite plate le
  keep-first de l'argmax la laisserait sur place). Il ne se lit dans aucun BC.
* **les DEUX cles BC ne sont pas devinables** : les litteraux IL2CPP vivent dans
  `global-metadata.dat`, Ghidra n'en montre qu'un slot. Resolus 100 % offline --
  `python probe_212_bc_key_literals.py --symbol "<le symbole ci-dessus>"` rend
  `+0x33fc070 -> 'DEVOUTPUSH_AdjacentRangedEnemy'` (branche `HasRangedWeapon` VRAIE) et
  `+0x33fbf28 -> 'DEVOUTPUSH_AdjacentMeleeEnemy'` (branche FAUSSE), recroises avec
  `data/seed-bc.json` `Utilities.Default.DevoutPush_AdjacentRangedEnemies` = **50** / **30**.
  Les poids sont **POSITIFS** : l'utilite PREFERE les tuiles adjacentes a des ennemis, deux fois
  plus fort pour un porteur d'arme a distance -- c'est le << push >> du nom (le caster va au contact
  des tireurs). Le natif lit ses deux entrees par `TryGetValue` et prend **0** quand la cle manque :
  `Weights.sub` a exactement cette degradation.
* **l'ancre est la tuile CANDIDATE** (`c.UnitPosition.get_MainTile()`), pas la tuile du sujet --
  c'est ce qui rend la feuille DISCRIMINANTE d'une candidate a l'autre. Le sujet ne sert qu'a
  resoudre le CAMP (`Enemies(subject, adj)`).

CONTRASTE AVEC SES DEUX VOISINES, mesure et non recopie :
  * `52 SwornProtector_AvoidAdjacentEnemies` prend `case.get_UnitOrParent` pour sujet et n'a AUCUNE
    garde de sujet nul ; ici c'est `case.unit` NU (`+0x10`), comme `54 RammingSpeed`. Un
    `get_UnitOrParent` recopie du voisin 52 aurait fait vivre cette feuille en regime SPAWN, ou le
    natif deref un nul ;
  * `54 RammingSpeed_MostAdjacentEnemies` compte les ennemis adjacents en BLOC (un seul poids) ;
    ici la somme est PAR ENNEMI et le poids depend de son ARMEMENT -- recopier le comptage en bloc
    aurait rendu 50 x n ou 30 x n au lieu du melange.

SUBSTRAT OFFLINE : `ctx["uid"]`, `ctx["self_pos"]`, `ctx["enemy_units"]` (dicts `{pos, vis, ...}`,
camp deja calcule par rapport au sujet) et `ctx["elev_by_pos"]` / `ctx["neigh_by_pos"]` -- ce que
produisent `tile_leaf_ctx` (face DECISION) et `runner_tile_leaf_ctx` (face RUNNER). L'adjacence
passe par `engine.battle_query.is_adjacent`, FOYER UNIQUE d'`IterateAdjacentTiles` cote port
(distance hex 1 + porte d'elevation), le MEME que `count_adjacent` -- aucun fork d'adjacence.
`HasRangedWeapon` delegue au foyer UNIQUE `engine.services.battle_query.has_ranged_weapon` (#601),
en forme B (module + acces attributaire), comme `playbook/adjacent_unit_preference.py`.

DEGRADATION : pas de sujet (`case.unit == null`, regime SPAWN) -> **0.0**. Le natif LEVE dans ce
regime (`GetMainTile(null)`), et aucun call-site porte n'y amene : l'unique producteur
(`PerformAIMovement` de 1053) passe le CASTER. Rendre 0 est la degradation sure, pas un
comportement natif mirrore -- meme choix, meme raison, que `54 RammingSpeed`.
"""
from __future__ import annotations

from .base import BaseUtility
from .tile import UTILITY_BY_TYPE
from .utility_type import UtilityType
from ..battle_query import is_adjacent, neigh_map
from ..services import battle_query as _sbq

#: `FixMath.NET.Fix64$$op_Implicit(0xfffffff6)` du premier `yield` -- un LITTERAL de code
#: (`mov ecx, 0xfffffff6`), PAS une entree du BC : aucune cle de
#: `Utilities.Default.DevoutPush_AdjacentRangedEnemies` ne vaut -10.
STAY_PUT_PENALTY = -10.0


class DevoutPush_AdjacentRangedEnemies(BaseUtility):
    """`Sigma(ennemis de case.unit adjacents a la tuile candidate)` du poids
    `DEVOUTPUSH_AdjacentRangedEnemy` (50) si l'ennemi porte une arme a distance, sinon
    `DEVOUTPUSH_AdjacentMeleeEnemy` (30) -- et `-10` fixe si la candidate EST la tuile courante.

    Le natif n'a PAS le suffixe `Utility` sur cette classe-la (comme `54 RammingSpeed`)."""
    UTILITY_TYPE = int(UtilityType.DevoutPush_AdjacentRangedEnemies)   # 53 sur `rnca9r7q6c`

    #: `IdunBattle.AI.Utilities.BaseUtility$$GetUtilityValue(query, <cle>)` : le `Dict<string,int>`
    #: `this+0x58`, categorie BC `Utilities.Default.DevoutPush_AdjacentRangedEnemies`.
    WEIGHT_CATEGORY = "DevoutPush_AdjacentRangedEnemies"
    WEIGHT_KEY_RANGED = "DEVOUTPUSH_AdjacentRangedEnemy"     # branche `HasRangedWeapon` VRAIE
    WEIGHT_KEY_MELEE = "DEVOUTPUSH_AdjacentMeleeEnemy"       # branche FAUSSE

    def evaluate(self, tile, meta, ctx, wt) -> float:
        if tile is None:
            return 0.0
        c = ctx or {}
        # `if (c.unit != null && GetMainTile(c.unit) == c.UnitPosition.MainTile) { yield -10; break; }`
        # -- la garde est sur le SUJET, et la comparaison sur la tuile PRINCIPALE. `uid` absent =
        # `case.unit == null` : le natif y deref un nul, on rend 0 (cf. l'entete).
        if c.get("uid") is None:
            return 0.0
        self_pos = c.get("self_pos")
        if self_pos is not None and (tile[0], tile[1]) == (self_pos[0], self_pos[1]):
            return STAY_PUT_PENALTY
        enemies = c.get("enemy_units") or ()
        if not enemies:
            return 0.0
        elev = c.get("elev_by_pos")
        nb = neigh_map(c)
        total = 0.0
        for e in enemies:
            if not isinstance(e, dict):
                continue
            p = e.get("pos")
            if not p:
                continue
            if not is_adjacent((tile[0], tile[1]), (p[0], p[1]), elev, nb):
                continue
            key = (self.WEIGHT_KEY_RANGED if _sbq.has_ranged_weapon(e.get("vis") or "")
                   else self.WEIGHT_KEY_MELEE)
            total += wt.sub(self.WEIGHT_CATEGORY, key)
        return float(total)


DEVOUT_PUSH_ADJACENT_RANGED_ENEMIES = DevoutPush_AdjacentRangedEnemies()

# Mirror d'`IdunBattle.Core.Services.UtilitiesDatabase$$GetUtility` : FEUILLE, pas composite --
# `UtilitiesDatabase$$InitializeUtilities` ne compose que les types qui ont une entree dans son
# `Dictionary<UtilityType, UtilityType[]>`, et 53 n'en a pas, donc `GetUtility` rend directement
# l'instance de la classe (MEME critere que 52, 54 et 67).
#
# L'INSCRIPTION EST FAITE ICI, PAS DANS `tile.py` -- meme patron que `engine/utilities/
# sworn_protector.py` et `engine/utilities/move.py`, et meme raison de perimetre : `tile.py` est un
# foyer tres partage, et une entree de plus dans son litteral `UTILITY_BY_TYPE` collisionne avec
# toute tranche en vol qui le touche.
UTILITY_BY_TYPE[int(UtilityType.DevoutPush_AdjacentRangedEnemies)] = (
    DEVOUT_PUSH_ADJACENT_RANGED_ENEMIES)
