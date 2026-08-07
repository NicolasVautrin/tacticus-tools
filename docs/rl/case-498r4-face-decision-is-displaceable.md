# #498-r4 — les deux conditions manquantes ne valaient pas d'être câblées ; ce qui MORDAIT était ailleurs

Le résidu demandait d'établir si la face DÉCISION d'`IsDisplaceable` doit porter un **cinquième
canal** `UnitFlag` et la **tête** `EntityType == Unit`. Réponse mesurée : **non pour les deux**, et
pour deux raisons différentes. Mais le cadrage cachait un écart réel, dans le troisième terme du
même prédicat.

## 1. `UnitFlag.Undisplaceable` (0x19) — recensement EXHAUSTIF des écrivains natifs

`#498-r3` disait « l'unique écrivain l'encadre dans une seule exécution d'ability », en n'ayant lu
qu'une des deux voies d'écriture. Les deux sont lues ici, littéral par littéral.

**Voie DSL** — `IdunBattleLogic.Entities.DSLBehaviors$$AddFlag(targets, flag)`, **10** appelants :

| appelant | flag |
|---|---|
| `TheQuickeningAbility$$GetTriggerMovementAbilitiesBehaviour` | `0x1` |
| **`UnstoppableMomentumReworkedAbility$$ExecuteBehaviour`** | **`0x19`** |
| `GalvanicFieldAbility$$CreateBehaviour` | `0x18` |
| `HealingBalmsAbility$$CreateBehaviour` | `0x17` |
| `HunterOfSoulsAbility$$CreateBehaviour` | `0x16` |
| `HunterOfSouls_KilledAbility$$CreateBehaviour` | `0x16` |
| `MV71SniperDroneSquadAttackAbility$$ExecuteBehaviour` | `0x1c` |
| `RapidFireAbility$$CreateBehaviour` | `0x0` |
| `WayOfTheShortBlade_AttackAbility$$CreateBehaviour` | `0x15` |
| `ECogSupport_InitAbility$$CreateBehaviour` | `0x18` |

`$$RemoveFlag` : **3** appelants — `0x19`, `0x1c`, `0x15`, tous dans la fonction qui a posé le même.

**Voie directe** — `IdunBattle.Entities.Components.UnitFlagsComponent$$Add(this, flag)`, **40** sites
de jeu (+1 de test), littéral relu à chacun : `0, 1, 2, 3, 4, 6, 8, 9, 0xc, 0xd, 0xe, 0xf, 0x10,
0x11, 0x12, 0x13, 0x14, 0x1a, 0x1b` — **21 ordinaux distincts, JAMAIS `0x19`**. Y compris les quatre
écrivains PERSISTANTS (les effets), qui étaient les seuls à pouvoir survivre à une ability :
`DamagedEffect` `0x10`, `UntargetableEffect` `0x11`, `DisableTriggersEffect` `0x12`,
`FuelledByFury_BlockOverkillEffect` `0x13`.

`UnitFlagsComponent$$.ctor` construit un `OrderedSet` **VIDE** (aucune unité ne naît avec le flag) ;
`$$RemoveTurnFlags` ne retire que `0, 1, 2, 3, 4, 0xc, 0x1b`.

⇒ **`0x19` n'existe qu'entre l'`AddFlag` et le `RemoveFlag` d'une seule exécution de `1152`**, et la
décision n'évalue jamais là. **Ne pas câbler** — un cinquième canal `UnitFlag` dans `Scene`/
`NCContext` porterait, sur ce build, une donnée toujours fausse.

⚠ **NUANCE NEUVE, que `#498-r3` n'avait pas** : l'encadrement n'est **pas hermétique**.
`UnstoppableMomentumReworkedAbility$$ExecuteBehaviour` porte, ENTRE les deux, un `return 0` sans
retrait — la branche `TargetsSelector$$SelectTile(AtIndex(tiles, i)) == null`, atteignable quand la
ligne derrière la cible est plus courte que le nombre de pas. Le flag peut donc **fuir** au-delà de
l'ability. Ça ne change pas le verdict (le substrat de décision ne le publie toujours pas), mais ça
change le RUNNER : résidu **`#498-r4-r1`**, **FERMÉ** — la fuite est CONFIRMÉE live
(`combatSnapshot.units[].unitFlags` du caster porte `25` après un cast à ligne courte traversée), et
le port la reproduit. La tranche a aussi trouvé un second écart, en amont : le port ne **posait
même pas** le flag (`_load_unit_flags` ne matérialise le `UnitFlagsComponent` que sur une liste non
vide) — foyer ouvert sous `#545`. Détail : `case-498r4r1-fuite-du-flag-undisplaceable.md`.

## 2. La tête `EntityType == Unit` — inerte PAR CONSTRUCTION DU CANAL

Les deux miroirs ne reçoivent leur `unit` que de `ctx.units`. Le foyer OFFLINE
(`ai/state_bridge.py::_dv_units`) **exclut** les MoW (`is_machine_of_war(e) -> continue`, idem
`_obs_units`) ; le foyer LIVE est `decisionView.units`, canal séparé de `.mows`. Et tout id absent
de cette liste rend `None` en amont (`_unit`, `unit_by_pos.get`), ce que les deux miroirs refusent
déjà en première ligne.

**Ne pas porter** : ce serait du code mort. Ce n'est pas « inerte sur ce build » comme `Hulking` —
c'est inerte tant que le canal ne publie pas les MoW, et le cliquet le MESURE sur un `State` qui en
porte une (il rougira le jour où le canal changera).

## 3. Ce qui MORDAIT — le SUBSTRAT de traits, pas les conditions manquantes

`ItItchesPlaybook._is_displaceable` lisait **`_traits(visualId)`**, le KIT gameconfig SEUL.
Le natif lit `IdunBattle.Entities.Components.BaseUnitComponent$$HasTrait`, c'est-à-dire la
collection `BaseUnitComponent+0x48`/`+0x40`, qui porte AUSSI les traits **accordés en bataille**
(leaf DSL `IdunBattleLogic.Entities.DSLFactory$$AddTrait` → `AddTraitOperation$$AddTrait`) et le
pseudo-trait de grande-alliance. L'autre miroir de décision (`MortisRoundPlaybook`) et le foyer
RUNNER lisent, eux, `entity_trait_names`.

Deux miroirs du MÊME prédicat, sur le MÊME substrat disponible, qui divergent : c'est le gisement
exact que `#498-r3` a fermé côté runner (« six copies libres de diverger, et elles avaient
divergé »). Direction : **PERMISSIVE** (`ItItches` jugeait poussable une unité que tout le reste du
port refuse).

Porté : `it_itches` passe à `entity_trait_names(ctx.scene.ctx(id), visualId)`, et le tuple des trois
traits — qui existait en **trois** exemplaires — a un foyer unique,
`runner/components.py::NOT_DISPLACEABLE_TRAITS`.

⚠ **INERTE SUR CE BUILD, et c'est mesuré, pas supposé** : sur les **175** unités de
`data/seed-bc.json`, `BC.Units[].Traits` et le kit s'accordent sur les trois traits refusants —
**0 écart** ; et **0** site du port n'octroie `Immovable`/`Hulking`/`BigTarget` par `AddTrait`. La
réparation est donc structurelle (le canal correct, et une copie de moins), pas un changement de
comportement observable aujourd'hui.

**NON CONFRONTÉ LIVE, pour une raison nommée** : sur ce build, le régime serait DÉGÉNÉRÉ (aucun
porteur ne diverge entre kit et entité sur ces trois traits). Le montage qui le rendrait
discriminant est celui de `#498-r3` §6, transposé : seed BC custom écrivant `BigTarget` dans
`BC.Units[].Traits` de la cible de `1121`, puis A/B du choix d'action de `tyranParasiteOfMortrex`.
Il re-mesurerait au niveau DÉCISION ce que `#498-r3` a déjà confronté LIVE au niveau du prédicat
natif lui-même.

## 4. Le recenseur rendait un FAUX VERT — sur ma propre prose

`probe_498r3_is_displaceable_sites.py` jugeait par **TEXTE**. Dès que les deux miroirs de décision
ont reçu une docstring qui NOMME ce qu'ils ne portent pas, il les a classés `delegue` — donc **5/5
conditions portées, `manque = -`**. Un faux vert fabriqué par un commentaire, dans l'outil même
censé recenser les manques.

Trois durcissements, tous mesurés en cours de tranche :

1. **`delegue` et `appelle_miroir` par AST** (`_appels`) : une délégation est un `ast.Call`, pas une
   mention.
2. **`porte` par AST** (`_symboles`) : `UnitFlag.Undisplaceable` / `MachineComponent` ne comptent
   que s'ils sont des nœuds `Attribute`/`Name` — une docstring est un `ast.Constant`.
3. **Table d'alias GLOBALE** (`_alias_traits_global`, chaînes résolues par point fixe) : sans elle,
   un site qui IMPORTE la constante partagée — la forme saine — perdait ses traits et sortait du
   rôle MIROIR, pendant qu'une copie locale restait visible. **Le recenseur récompensait la
   duplication.** L'union (jamais `update`) est la seconde moitié du correctif : une définition
   locale `_X = <constante importée>` ne porte aucun nom de trait, et écrasait la résolution
   globale par un ensemble vide.

Recensement après : **12 sites**, 7 miroirs runner (0 copie, 0 incomplet), 2 miroirs décision dont
le `manque` affiché est enfin `EntityType,Undisplaceable` pour les DEUX.

## 5. Les cliquets

`tests/engine/test_498r4_face_decision_is_displaceable_offline.py`, **10 tests / cinq étages** :
foyer unique du tuple (comparaison d'OBJETS, pas de contenu) ; substrat des traits accordés + son
MUTANT kit-seul, qui assertionne son propre non-vide ; accord des deux miroirs sur quatre régimes
avec anti-dégénérescence ; inertie de la tête MESURÉE sur un `State` portant une MoW ; et la
CONTRE-ÉPREUVE du durcissement — une fonction dont la seule docstring nomme le foyer, le flag et
les traits ne doit créditer AUCUNE condition, alors que les mêmes symboles ÉCRITS DANS LE CODE
doivent compter.

Vue rouge sur l'arbre témoin (`git archive origin/master`) : **5 failed / 5 passed**, et le rouge
décisif est la divergence elle-même — `('Immovable', False, True, False)` : `MortisRound` refuse,
`ItItches` accepte. **10 passed** après.
