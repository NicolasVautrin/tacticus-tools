"""KissOfDeathPlaybook (1108, `eldarNpc3Harlequin` / `eldarSmnHarlequin`) -- face DECISION
(residu `#940-r2` ; la face COMBAT est portee et confrontee par #940,
`engine/runner/abilities/aeldari.py`).

Base `NonComparablePlaybook`1` -- LUE dans `data/symbols/<build>/frida/classes.tsv`
(`IdunBattle.AI.Playbook.Loki.KissOfDeathPlaybook  112  IdunBattle.AI.Playbook.NonComparablePlaybook`1`).
Le `.ctor` decompile en `ComparablePlaybook<...>$$.ctor(this, 0x454)` : corps gshared DEDUPLIQUE
par l'ICF, exactement le mislabel que la fiche `#893-r1` avait recopie pour `CrusadeOfWrath` et que
`#487-r1` / `#552` / `#590` / `#945` avaient deja documente. `0x454 = 1108`.

LE CORPS, TERME A TERME
------------------------
`IdunBattle.AI.Playbook.Loki.KissOfDeathPlaybook$$EvaluateNonComparable(caster, casterPosition,
abilityState)` :

    bucket = new Bucket<UnitAction>( priority: 0, minUtility: Nullable(Fix64.op_Implicit(2)) )
    foreach e in BasePlaybook$$GetEligibleTargetsEntities(caster, casterPosition.get_MainTile()):
        n = <IBattleQuery slot 16>.GetChainedUnits(e, onlyFriends: true, additionalCondition: null)
                                  .<ICollection slot 0 = get_Count>()
        bucket.AddAction( BasePlaybook$$GenerateAction(casterPosition, e, Fix64.op_Implicit(n)) )
    return bucket

⚠ **CE CORPS EST LE JUMEAU EXACT DE `StormOfWrathPlaybook$$EvaluateNonComparable` (1019)**, et ce
n'est PAS une deduction par ressemblance de nom (« ne jamais recopier le voisin de forme ») : les
DEUX decompiles ont ete lus cote a cote et concordent instruction par instruction -- memes
pointeurs de metadata-usage (`DAT_1833c5188`, `DAT_1833c5040`, `DAT_18336fe98`, `DAT_1833d1810`,
`DAT_1833407b0`, `DAT_183364c10`, `DAT_1833c42a8`), meme litteral `Fix64.op_Implicit(2)`, meme
`Nullable<Fix64>$$.ctor`, meme slot d'interface `+0x10` sur `this+0x28`, memes arguments
`(cible, 1, 0)`, meme `GenerateAction(casterPosition, cible, utilite)`. Ce sont deux corps compiles
DISTINCTS (adresses differentes) au contenu identique -- pas une fusion d'ICF.

LE BLOCAGE `etage` DE LA FICHE EST LEVE, ET IL L'ETAIT DEJA
-----------------------------------------------------------
La fiche `#940-r2` annoncait « les TROIS appels d'interface qui produisent l'utilite ne sont pas
resolus (slots de metadata-usage a xref unique) -- les nommer est le premier etage ». Les trois se
lisent dans une entree VERSIONNEE du depot, `data/symbols/<build>/metadata/interface_slots.tsv` :

  * `IBattleQuery 16 GetChainedUnits 3`  -- le slot `+0x10` sur le query `this+0x28` ;
  * le slot 0 de l'interface du retour = `get_Count` (appel a 0 argument rendant un `int`) ;
  * `get_MainTile` / `GetEligibleTargetsEntities` / `GenerateAction` sont des appels DIRECTS,
    jamais des slots.

Et `GetChainedUnits` etait DEJA porte, par `StormOfWrathPlaybook` (#945). Le blocage etait donc
perime au moment ou il a ete ecrit : ce port ne leve aucun etage, il consomme un foyer existant --
desormais `engine.battle_query.get_chained_units`, ou le corps a ete factorise A CE SECOND SITE
(meme geste que `BattleQuery$$IsMeleeAttack` a #419-r1-tr14).

LA SEMANTIQUE, ET POURQUOI LE SEUIL 2 EST LOAD-BEARING
-------------------------------------------------------
`onlyFriends` vaut `true` (litteral `1` du call-site) : l'utilite N'EST PAS un comptage d'ennemis
autour de la cible, c'est la taille de la COMPOSANTE CONNEXE d'unites AMIES DE LA CIBLE, de proche
en proche. `GetChainedUnitsInternal` fait `adj.Add(tile)` avant d'enumerer, donc la cible entre
elle-meme dans le set : une cible ISOLEE vaut **1**, et le `minUtility = 2` du `Bucket` la rejette.
Traduction de jeu : le Harlequin ne pique que dans un GROUPE -- il faut au moins un rebond.

Cela colle a la face COMBAT deja portee (#940), dont le lambda de saut est
`Enemies(of = Caster, entities = AdjacentUnits(lastTargets))` : decider compte exactement la
population que l'execution va parcourir. ⚠ Une DISSYMETRIE reste, et elle est du NATIF : la face
DECISION compte les AMIS de la cible (`onlyFriends: true` sur la cible), la face COMBAT saute vers
les ENNEMIS du caster. Sur une cible ennemie du caster les deux ensembles coincident, ce qui est le
regime nominal ; le port ne les reconcilie pas -- il transcrit chaque face telle qu'elle est ecrite.

BORNES DE PORT, nommees
------------------------
* Le terme est POSITION-INDEPENDANT (la tuile candidate du caster n'entre pas dans la formule).
  `Bucket$$AddAction` ne remplacant que sur amelioration STRICTE, le caster reste donc en place des
  qu'une cible atteignable depuis l'origine atteint le maximum -- meme regime que 1019.
* `IsFriend` compare le joueur COURANT : substrat `ctx.obs_units[].teamId` (l'equipe courante, celle
  que suit un controle mental), jamais `playerId`.
* Les ecarts du canal `obs_units` sont ceux nommes dans `_base.occupant_ids_by_pos` : MACHINES OF
  WAR absentes, tuile PRINCIPALE seule en offline. Les deux SOUS-declarent l'occupation, donc
  bornent le compte par en dessous.
* `additionalCondition` est `null` au call-site -- rien a porter.

CONFRONTABILITE -- etablie par #940, RELUE ici
-----------------------------------------------
`eldarNpc3Harlequin` est **npc** ; `eldarSmnHarlequin` est **summon** dont l'unique declarant est
`EnvFactionSummons:Aeldari` (spawner d'ENVIRONNEMENT rattache a AUCUNE unite du catalogue) -- la
voie summon est FERMEE. La voie retenue est la **GREFFE** sur une unite du pool
(`docs/rl/case-92-catalog-injection.md` §5bis), dont la CONDITION est verifiee et RE-LUE au
decompile ci-dessus : le playbook est enregistre PAR ABILITY
(`metadata/active_playbook_builders.tsv` : `active 1108 IdunBattle.AI.Playbook.Loki.KissOfDeathPlaybook`)
et `EvaluateNonComparable` ne lit NI stat NI trait du caster -- le caster n'entre que par
`GetEligibleTargetsEntities` et `casterPosition`.
"""
from __future__ import annotations

from engine import battle_query as bq
from engine.entities.active_ability_type import ActiveAbilityType

from ._base import NCContext, _PlanTargetPlaybook, occupant_ids_by_pos

#: `Bucket<T>$$.ctor(0, Nullable(Fix64.op_Implicit(2)))` -- litteral LU dans
#: `KissOfDeathPlaybook$$EvaluateNonComparable`, INLINE dans la methode : la classe native ne
#: declare que `..ctor` et `EvaluateNonComparable` (`frida/methods.tsv`), donc AUCUN `.cctor` ne
#: pourrait le porter. Meme forme, et meme valeur, que `StormOfWrathPlaybook`.
_MIN_CHAINED = 2


class KissOfDeathPlaybook(_PlanTargetPlaybook):
    """`IdunBattle.AI.Playbook.Loki.KissOfDeathPlaybook$$EvaluateNonComparable` --
    utilite = |chaine d'unites amies de la cible, cible COMPRISE| ; MIN_UTILITY = 2."""
    ABILITY_ID = int(ActiveAbilityType.KissOfDeath)     # 0x454 = 1108 (argument du ctor natif)
    MIN_UTILITY = float(_MIN_CHAINED)
    PRIORITY = 0        # hors `NATIVE_PRIORITY` (defaut `AbilityPriority.Normal`, sweep #170)

    def evaluate_non_comparable(self, tile, target, ctx: NCContext):
        """`Fix64(GetChainedUnits(target, onlyFriends: true, additionalCondition: null).Count)`."""
        occ, team_by_id = occupant_ids_by_pos(ctx)
        n = len(bq.get_chained_units(target, occ, team_by_id,
                                     elev_by_pos=ctx.elev_by_pos, neigh_by_pos=bq.neigh_map(ctx),
                                     only_friends=True))     # `onlyFriends` = litteral `1`
        return float(n)

    def damage_predictions(self, tile, target, ctx: NCContext) -> list:
        """AUCUNE prediction de degat n'est construite : `KissOfDeathPlaybook` ne declare que
        `..ctor` et `EvaluateNonComparable` (`frida/methods.tsv` comme `ghidra/functions.tsv`),
        donc ni `MakeDamagePredictions` ni gate `WillNormalAttackKill`. La sequence que l'oracle
        `ncPlaybookPredict` voit est VIDE -- ce qui est un resultat, pas un defaut."""
        return []
