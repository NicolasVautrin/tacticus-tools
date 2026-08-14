"""`IdunBattle.AI.Playbook.Loki.SpecialIssueCombiMeltaPlaybook` -- face ATTACK du triggered
`SpecialIssueCombiMelta` (1545), passif de `darkaSternguard` << Ramus >> (HERO, kind `lineup`) et du
npc `darkaBossSternguardLHE` : 2 porteurs, tranche 11 des residus ATTACK de #419-r1.

Feuille `TriggeredAbilitiesUtility(2)` du composite Damage(35), MEME dispatcher que Psyker,
AggressiveOnslaught, SuppressiveFire, Lakrimae, BarbedOvipositor, Neuroparasite, SaviorProtocols,
AvalancheOfMuscle, Boltstorm, FireOfAbsolution, CosmicHorror, LightImUp et RapidFire
(`utilities/tile.py::evaluate_attack_in_steps`, vslot 3).

## Le corps natif, remis en C#

`IdunBattle.AI.Playbook.Loki.SpecialIssueCombiMeltaPlaybook$$CalculateAttackUtilityInStepsInternal`
monte la SM `d__3`. **Sa disposition se LIT dans ce wrapper, jamais par analogie** -- et elle est
INVERSEE par rapport a `CosmicHorror`/`SaviorProtocols` :

    sm@+0x10 = state ; sm@+0x18 = current
    sm@+0x20 = this (le PLAYBOOK)      <- `CosmicHorror.d__3` y met le CASE
    sm@+0x28 = case                    <- `CosmicHorror.d__3` y met le playbook
    sm@+0x30 = getUtilityVal (le delegue scorer)

Corps `SpecialIssueCombiMeltaPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$MoveNext`,
UN SEUL `yield`, et une branche qui n'en fait AUCUN :

    if (this.<IBattleQuery, champ #3 de TriggeredAbilityPlaybook<T>>
            .<slot 0x6c = GetDistance>(case.Target /* @+0x20 */,
                                       case.CasterPosition.MainTile /* @+0x18 */) != 3)
        yield break;                                             // AUCUN yield -- pas un `yield 0`
    yield return Fix64.op_Implicit(getUtilityVal("SpecialIssueCombiMelta_LikesRange3"));

Sept lectures qui ne se devinent pas, et dont aucune ne se transporte d'une tranche voisine :

1. **La tuile lue est celle du CASTER (la tuile d'ATTAQUE), pas celle de la cible.** Le symbole que
   Ghidra donne au getter est `IdunBattle.AI.Utilities.UtilityMovementCase$$get_MovementTile` -- un
   corps `IdunBattle.Core.UnitPosition$$get_MainTile(this + 0x18)` DEDUPLIQUE par l'ICF. Sur un
   `UtilityAttackCase`, `+0x18` est `CasterPosition` (lu au `IdunBattle.AI.Utilities.
   UtilityAttackCase$$.ctor`, 3e parametre) : c'est donc `case.CasterTile`. MEME quirk de symbole
   que `cosmic_horror.py` (point 1) et `rapid_fire.py` (point 1) ; s'y fier ferait lire la tuile
   d'un case de MOUVEMENT.

2. **L'autre argument est `case.Target`** (`UtilityAttackCase@+0x20`, 4e parametre du `.ctor`, le
   meme champ que lisent `Lakrimae`, `SaviorProtocols` et `Neuroparasite`). Le terme est donc une
   fonction de la SEULE geometrie (cible, tuile d'attaque) : ni stat, ni trait, ni effet, ni flag,
   ni prediction, ni propriete du caster autre que la tuile evaluee.

3. **Le service est le champ #3 de la base `TriggeredAbilityPlaybook<T>`**, lu par le chemin
   generique `thunk_FUN_1801f5f80(playbook, fields + 0x60)` (la base est PLEINEMENT PARTAGEE, donc
   l'offset d'objet se resout au runtime). C'est le champ que
   `IdunBattle.AI.Playbook.TriggeredAbilityPlaybooku003C__Il2CppFullySharedGenericTypeu003E$$Init`
   remplit depuis son `param_3` -- l'`IBattleQuery` ; `CosmicHorror` prend, lui, le champ #2
   (`fields + 0x40`, l'`IBattleState`).

4. **Le slot `0x6c` est `GetDistance(IEntity, IEntity)`**, identifie par DEUX proxys NOMMES qui
   l'appellent sur le MEME cache de classe d'interface et consomment sa sortie comme une distance :
   `IdunBattle.AI.Utilities.TileDistanceUtility$$DistanceTo` (qui en fait `-d / 10`) et
   `IdunBattle.Entities.Selectors.NearestSelector$$GetDistance` (qui la rend telle quelle). Il
   retombe sur `IdunBattle.Core.Services.BattleQuery$$GetDistance(IEntity, IEntity)` ->
   `IdunBattle.Core.Services.MovementQuery$$GetDistance(IEntity, IEntity)` =
   `GetTiles` des deux cotes puis MIN sur toutes les paires de
   `IdunBattle.Utils.Hex.CubeCoordinate$$Distance`. **Distance HEXAGONALE, aucun pathfinding**, et
   `int.MaxValue` si un cote est nul ou sans tuile (le natif ne rend PAS 0).

5. **Le `3` est un LITTERAL du corps du playbook**, pas une lecture de config -- et il est corrobore
   DEUX FOIS, independamment : (a) le trigger de la face COMBAT,
   `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SpecialIssueCombiMelta_AddEffectAbility$$CreateTrigger`
   = `On(EventTriggerType.NormalAttack /* 0x26 */) & OwnerIsCaster &
   IsAtRange(Caster, Target, DSLFormulas.Get(3))`, ou `IdunBattleLogic.Entities.DSLFormulas$$Get(int)`
   fabrique un montant CONSTANT ; (b) le nom de la cle BC, `SpecialIssueCombiMelta_LikesRange3`.

6. **La branche « pas a portee 3 » ne fait AUCUN yield** -- `yield break`, pas `yield Fix64(0)`.
   C'est le PREMIER playbook attack porte dans ce cas : tous les autres versent un `Fix64(0)`
   explicite. Sans effet observable, et c'est DEMONTRE, pas suppose : le consommateur
   `IdunBattle.AI.Utilities.TriggeredAbilitiesUtility.u003CEvaluateAttackInStepsInternalu003Ed__3$$MoveNext`
   accumule `total = Fix64.op_Addition(total, step)` sur les steps et rend `total` (seed
   `Fix64.op_Implicit(0)`) -- une enumeration VIDE y contribue exactement 0. Le port rend donc 0.0.

7. **AUCUNE gate sur l'ability du case.** Le corps n'appelle ni
   `TriggeredAbilityPlaybook<T>$$IsRegularAttack`, ni `IdunBattle.AI.Utilities.UtilityAttackCase$$IsNormalAttack`,
   et ne lit pas `case.AbilityType` (`@+0xf0`). Le terme tombe donc pour TOUT case d'attaque a
   distance 3 -- y compris une ability active. C'est une DIVERGENCE assumee avec la face COMBAT de
   la meme ability, dont l'effet `SpecialIssueCombiMelta_ExtraDmg` (1564) ajoute bien
   `DSLTriggers.IsNormalAttack` a son trigger. Ne pas ajouter la gate cote AI serait recopier la
   face combat au lieu de mirrorer le playbook.

8. **La sortie est un poids BC, pas un litteral** : le slot de string literal du corps est
   `SpecialIssueCombiMelta_LikesRange3` -- LU (`probe_212_bc_key_literals.py` sur ce symbole), pas
   devine ; `Utilities.Default.TriggeredAbilities.SpecialIssueCombiMelta_LikesRange3` = **25** au
   seed BC servi. Le playbook n'a pas de `.cctor` : le literal est dans le corps, meme forme que
   `SaviorProtocols`, `CosmicHorror` et `BarbedOvipositor`, l'inverse de `Lakrimae`.

## Face MOVE : `yield Fix64(0)` CONSTANT -- decompile LU, ce n'est pas un trou

`SpecialIssueCombiMeltaPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext` est
un unique `yield return Fix64.op_Implicit(0)`, et son wrapper
`$$CalculateMovementUtilityInStepsInternal` n'ecrit NI le case NI le playbook NI le delegue dans la
SM (state seul). `probe_212_bc_key_literals.py` confirme : AUCUN string literal lu. Elle n'entre donc
pas au registre `TRIGGERED_MOVE_PLAYBOOKS`, et cette absence EST le comportement natif -- meme forme
que `Lakrimae`, `BarbedOvipositor`, `Neuroparasite`, `AvalancheOfMuscle`, `Boltstorm`,
`CosmicHorror`, `LightImUp` et `RapidFire`.

## Les autres artefacts natifs de l'id 1545 -- et pourquoi ils sont HORS PERIMETRE

L'id recouvre SIX classes natives, toutes nommees `SpecialIssueCombiMelta*` :

  * ce PLAYBOOK (2 faces)                                        -> PORTE ici (face DECISION) ;
  * `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SpecialIssueCombiMelta_InitAbility`
    (`CreateBehaviour` = `AddEffect(0x61b) & AddEffect(0x61c)`)   -> face COMBAT ;
  * `IdunBattleLogic.Entities.Abilities.Triggered.Loki.SpecialIssueCombiMelta_AddEffectAbility`
    (`CreateTrigger` = `On(NormalAttack) & OwnerIsCaster & IsAtRange(..., 3)`,
     `CreateBehaviour` = `AddEffect(0x429 = EffectType.Pinned)`)  -> face COMBAT ;
  * `Idun.Source.IdunBattle.Logic.Entities.Effects.Loki.SpecialIssueCombiMelta_AdditionalHitsEffect`
    (`EffectType` **1563**, `EffectAdditionalHits.Create`)        -> face COMBAT ;
  * `Idun.Source.IdunBattle.Logic.Entities.Effects.Loki.SpecialIssueCombiMelta_ExtraDmgEffect`
    (`EffectType` **1564**, `EffectBonus.ForAddition`)            -> face COMBAT ;
  * `IdunBattle.View.AbilityConfigs.Loki.SpecialIssueCombiMeltaVisuals`                -> vue.

Les cinq dernieres sont la face EXECUTION (couverture `combat-ability-coverage`), pas la face
DECISION que #419-r1 recense : elles ne passent pas par `TriggeredAbilitiesUtility` et le port de ce
module ne les touche pas. ⚠ **Enums a QUALIFIER** : a id egal, `EffectType` 1545 =
`NanoscarabRepairProtocols` (mecanique SANS RAPPORT) ; et les ids des DEUX effets de la famille
(1563 / 1564) sont dans un ESPACE DE NUMEROTATION DIFFERENT de l'ability 1545 -- ils se re-derivent
de `data/symbols/<build>/frida/enums.tsv` du build COURANT, jamais d'une fiche anterieure.

## Substrat cote port -- ce que ce terme exige, et qui l'ecrit

Le corps ne lit que les TUILES de la cible et la tuile d'attaque. Les deux canaux existent deja
(`scene.feet_by_id` via `playbook.adjacency.iterate_tiles` ; `attack_tile` est le 5e parametre du
dispatcher) -- aucune piece neuve, donc pas de patron « porte + INERTE ». `prediction`
(`UtilityAttackCase@+0x28`, canal #438) est ACCEPTE et IGNORE, comme le corps natif qui ne lit pas
ce champ.

Residu `#419-r1-tr11-r1` -- **le MULTI-HEX etait collapse a la main tile. FERME.** Le natif prend le
MIN sur toutes les paires de pieds (`IdunBattle.Entities.EntityExtensions$$GetTiles`) ; le port
lisait `scene.pos(cible)`, c.-a-d. la seule MainTile, alors que le seul cote qui puisse avoir
plusieurs pieds ici est bien la CIBLE (la tuile d'attaque, elle, est `case.CasterPosition.MainTile`
au natif meme -- un `(col,row)` unique). Une MoW visee a distance 3 de sa main tile mais 2 d'un de
ses pieds faisait rendre 25 au port la ou le natif rend 0. La fermeture n'a demande AUCUN capteur :
l'empreinte est publiee dans la `Scene` de decision depuis `#419-r1-tr10-r2`
(`decisionView.units[].feet` / `.mows[].{feet,platformTiles}`), et son foyer de lecture est
`playbook.adjacency.iterate_tiles`, le mirror d'`EntityExtensions$$IterateTiles` -- l'enonce du
residu (« fermeture = publier l'empreinte ») etait donc PERIME de ce canal. Sur toute unite
MONO-PIED le resultat est IDENTIQUE au port d'avant (`iterate_tiles` rend `[MainTile]`).
"""
from __future__ import annotations

from ..battle_query import get_distance
from ..entities.triggered_ability_type import TriggeredAbilityType
from .adjacency import iterate_tiles

# Le LITTERAL `3` du corps (`if (GetDistance(...) != 3) yield break;`) -- cf. en-tete, point 5.
_RANGE = 3
# L'UNIQUE string literal de la face ATTACK, lu dans `Utilities.Default.TriggeredAbilities`.
_WEIGHT_KEY = "SpecialIssueCombiMelta_LikesRange3"


class SpecialIssueCombiMeltaPlaybook:
    """`SpecialIssueCombiMeltaPlaybook` (`IdunBattle.AI.Playbook.Loki`, triggered 1545 -- l'id passe
    par `$$.ctor` a la base `TriggeredAbilityPlaybook<T>` est bien `0x609`). Seule la face ATTACK a
    un corps ; la face MOVE est un `yield 0` constant au natif (cf. en-tete)."""

    ability_id: int = int(TriggeredAbilityType.SpecialIssueCombiMelta)      # 1545 = 0x609

    def calculate_attack_utility_in_steps(self, ctx, attacker_uid: int, ability_id: int,
                                          case_tgt_id: int, attack_tile, prediction=None) -> float:
        """Mirror de `<CalculateAttackUtilityInStepsInternal>d__3$$MoveNext` (cf. en-tete) : le poids
        `SpecialIssueCombiMelta_LikesRange3` quand la distance HEXAGONALE entre la CIBLE du case et
        la TUILE D'ATTAQUE vaut EXACTEMENT 3, 0 sinon.

        `attacker_uid`, `ability_id` et `prediction` ne sont pas lus -- le corps natif ne touche que
        `case@+0x20` (la cible) et `case@+0x18` (la position du caster). Aucune gate d'ability :
        point 7 de l'en-tete."""
        sc = getattr(ctx, "scene", None)
        if sc is None or attack_tile is None or case_tgt_id is None:
            return 0.0
        # `#419-r1-tr11-r1` FERME : les tuiles de la CIBLE sont TOUS ses pieds, pas sa seule
        # MainTile. `GetDistance(IEntity, IEntity)` resout chaque cote par
        # `IdunBattle.Entities.EntityExtensions$$GetTiles` puis prend le MIN sur les PAIRES ; sur une
        # entite MULTI-HEX (MACHINE OF WAR, 3 ou 7 pieds) la MainTile seule SUR-ESTIME la distance,
        # donc le port versait 25 la ou le natif rend 0 (et inversement). Le canal existe depuis
        # `#419-r1-tr10-r2` (`scene.feet_by_id` <- `decisionView.units[].feet` /
        # `.mows[].{feet,platformTiles}`) et le foyer de lecture est `adjacency.iterate_tiles`, LE
        # mirror de `EntityExtensions$$IterateTiles` -- aucun capteur neuf, aucun canal propre.
        # Cible sans aucune tuile -> `[]` -> `get_distance` rend `DISTANCE_UNREACHABLE`, donc la
        # gate `== 3` ne passe pas : exactement le `int.MaxValue` du natif, jamais 0.
        tgt_tiles = iterate_tiles(sc, int(case_tgt_id))
        # L'AUTRE cote reste un singleton, et c'est LU : `case.CasterPosition.MainTile`
        # (`UtilityAttackCase@+0x18` -> `UnitPosition$$get_MainTile`) est deja la MAIN TILE au natif
        # -- le playbook ne passe PAS l'entite du caster. Le collapse y est donc FIDELE, pas une
        # degradation.
        if get_distance(tgt_tiles, [attack_tile]) != _RANGE:
            return 0.0                                   # `yield break` -- cf. en-tete, point 6
        return float(ctx.wt.triggered(_WEIGHT_KEY))


__all__ = ["SpecialIssueCombiMeltaPlaybook"]
