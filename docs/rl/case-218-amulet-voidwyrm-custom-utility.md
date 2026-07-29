# case-218 — `AmuletOfTheVoidwyrmPlaybook` n'override PAS `CalculateCustomUtility`

**Verdict binaire : NON.** Le « 13bis » de `docs/rl/case-27-custom-utility.md` — la 28e classe
overridante, « invisible des tables par dédup IL2CPP », entrée au backlog comme 10e résidu — est un
**FAUX POSITIF de lecture HORS VTABLE**. C'est exactement le piège (b) que `case-27` nommait
elle-même (« les `Il2CppClass` sont contigus en mémoire, donc lire au-delà d'une vtable retombe sur
la classe voisine et peut rendre un `MethodInfo` parfaitement nommé »), et le contrôle de bornes de
la tranche 3 ne l'a pas attrapé parce qu'il était **heuristique** (« regarder où les noms deviennent
du bruit ») là où le débordement tombait, lui, sur une vtable parfaitement propre.

Rien à porter. Un fix de code est livré quand même : **le sweep qui a produit l'erreur est borné**,
et le faux positif silencieux devient un statut explicite.

Repro : `cd scripts/python && python probe_218_amulet_custom_utility.py`
Garde : `scripts/python/tests/engine/test_218_amulet_custom_utility_vtable.py`

## 1. Comment le verdict est établi — trois piliers POSITIFS, aucun argument d'absence

L'absence d'un symbole dans `methods.tsv` / `ghidra/functions.tsv` ne prouve rien (tables indexées
par ADRESSE, corps dédupliqués). Aucun des trois piliers ci-dessous n'en dépend.

### Pilier A — la chaîne d'héritage (offline, source indexée par NOM)

`data/symbols/<build>/frida/classes.tsv` porte `classe → parent`, dérivée du dump de métadonnées
IL2CPP. Elle n'a pas le défaut d'indexation par adresse :

```
AmuletOfTheVoidwyrmPlaybook -> TriggeredAbilityPlaybook`1 -> Object
ControlEdictPlaybook        -> TriggeredAbilityPlaybook`1 -> Object
PlasmaGrenadePlaybook       -> ComparablePlaybook`1 -> Playbook`1 -> BasePlaybook -> Object
```

`CalculateCustomUtility` est un virtuel déclaré par `IdunBattle.AI.Playbook.ComparablePlaybook`1`.
`IdunBattle.AI.Playbook.TriggeredAbilityPlaybook`1` descend **directement de `System.Object`** : les
deux branches sont DISJOINTES. La méthode n'est ni héritée ni overridable depuis là.

Confirmé au décompilé sur la STRUCTURE des ctors (ghidra mislabel les corps gshared — on lit l'appel,
jamais le nom) : `IdunBattle.AI.Playbook.Loki.PlasmaGrenadePlaybook$$.ctor` appelle
`IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$.ctor(this,
0x44a, …)` — `0x44a` = 1098 `PlasmaGrenade`, un `ActiveAbilityType` ; alors que
`IdunBattle.AI.Playbook.Loki.AmuletOfTheVoidwyrmPlaybook$$.ctor` appelle un ctor de base gshared
avec `(this, 0x5b8, …)` — `0x5b8` = **1464**, un `TriggeredAbilityType`.

### Pilier B — la vtable RÉELLE de la base, lue sur une classe SŒUR initialisée

`ControlEdictPlaybook` a la même base et sa classe EST initialisée dans la session : sa vtable tient
en **13 slots** (`+0x138`..`+0x1f8`), tous nommés, et il n'y a **pas de 14e** :

```
Equals, Finalize, GetHashCode, ToString,                       <- System.Object
Init, FilterMovementTiles,
CalculateMovementUtilityInSteps, CalculateAttackUtilityInSteps, CalculateRepairUtilityInSteps,
FilterMovementTiles,
CalculateMovementUtilityInStepsInternal, CalculateAttackUtilityInStepsInternal,
CalculateRepairUtilityInStepsInternal
```

Un `TriggeredAbilityPlaybook` n'a **que des méthodes d'utilité par pas** (mouvement / attaque /
réparation) : `CalculateCustomUtility` n'y a même pas de place. La taille d'instance le corrobore
(96 pour cette branche, 112 pour la branche `Playbook`1`).

### Pilier C — l'arithmétique du débordement

Mesuré live (session 16, build `gqfc5mff6c`) :

| | valeur |
|---|---|
| `klass(AmuletOfTheVoidwyrmPlaybook)` | `0x207c1b3f050` |
| `klass(PlasmaGrenadePlaybook)` | `0x207c1b3f260` |
| delta | **`0x210`** |
| slot « trouvé » sur Amulet par le sweep non borné | `+0x548` |
| VRAI slot `CalculateCustomUtility` de PlasmaGrenade | `+0x338` |
| `0x548 - 0x338` | **`0x210`** |

Et la confrontation ne porte pas sur un seul slot : **les 39 slots** de la vtable de
`PlasmaGrenadePlaybook` (`+0x138`..`+0x398`) se retrouvent **bit-identiques** à `+0x348`..`+0x5a8`
vus depuis `AmuletOfTheVoidwyrmPlaybook` (`Equals`, `Finalize`, … `EvaluateInternal`,
`CalculateCustomUtility`, `MakeDamagePredictions`, … `MakeFinalTilePrediction`). Le « slot 0x548 »
n'est pas un slot d'Amulet : c'est la vtable de la classe suivante, lue par-dessus la fin de la
sienne.

`0x210 = 0x138 (en-tête `Il2CppClass`) + 13 × 0x10 (les 13 slots) + 8 d'alignement` : la taille
mesurée de la classe **confirme** le compte de 13 slots du pilier B.

### Pourquoi le débordement a été SILENCIEUX

La vtable propre d'`AmuletOfTheVoidwyrmPlaybook` est **NULLE** : la classe n'a jamais été
instanciée dans la session, et IL2CPP ne remplit les `VirtualInvokeData` qu'à l'initialisation de la
classe. Le balayage `0x108..0x808` ne trouvait donc **rien chez elle** et se poursuivait jusqu'à la
première vtable REMPLIE en aval. Même signature sur `OmnissiahsBlessingPlaybook`,
`PrehensilePincerTailPlaybook`, `RedRampagePlaybook` (0 slot lisible).

## 2. Le fix : le sweep est BORNÉ, et l'indéterminé devient explicite

`resolveVtableSlot` (`frida/hooks/features/introspect.ts`) lit `klass+off` en aveugle : **il n'a pas
accès à `vtable_count`**. Rien côté hook ne peut donc arrêter un balayage trop large — c'est
l'appelant qui doit borner. `probe_27_custom_utility_inventory.sweep_vtable` le fait désormais :
**premier bloc CONTIGU de slots nommés depuis `+0x138`**, et trois statuts au lieu de deux —

| statut | sens |
|---|---|
| `ok` | slot trouvé DANS la vtable propre (offset rendu) |
| `no-slot` | vtable propre LUE, aucun `CalculateCustomUtility` — verdict ferme |
| `vtable-uninit` | vtable NULLE (classe jamais instanciée) — **INDÉTERMINÉ explicite**, à trancher par la chaîne d'héritage |

Le troisième statut est le cœur du correctif : le régime qui produisait le faux positif rend
maintenant un « je ne sais pas » nommé, au lieu de la vtable du voisin.

**Limite assumée** : `vtable-uninit` est un vrai angle mort du sweep (93 classes sur 377 dans la
session de mesure). Il ne se résout pas au balayage mais à la chaîne d'héritage (pilier A) — ou en
faisant instancier la classe. L'ancien régime ne le résolvait pas non plus : il le **masquait**.

## 3. Chiffres de `case-27` corrigés (sweep borné, build `gqfc5mff6c`, session 16)

| | tranche 3 (non borné) | re-dérivé (borné) |
|---|---|---|
| classes `*Playbook*` vues | 377 | 377 |
| classes portant le slot | 101 | **93** |
| offsets de slot rencontrés | `0x338` ×94 + `0x548`/`0x5a8`/`0x668`/`0x7b8` ×7 | **`0x338` ×93, et rien d'autre** |
| corps DISTINCTS | 27 | **27** (inchangé) |
| classes overridantes | 28 | **27** |
| users du corps `PlasmaGrenadePlaybook$$CalculateCustomUtility` | 2 | **1** |

**Les 7 « slots hors +0x338 » étaient les 7 mêmes faux positifs**, pas une disposition de vtable
alternative : re-balayées bornées, aucune des 7 ne porte le slot dans sa propre vtable. Leurs bases
— `TriggeredAbilityPlaybook`1`, `AdjacentUnitPreferenceTriggeredAbilityPlaybook`1` (fille de la
précédente) et `NonComparablePlaybook`1` — sont **toutes hors** de la branche `ComparablePlaybook`1`
qui déclare la méthode. Il n'existe donc **qu'un seul offset de slot** pour ce virtuel, `+0x338`, et
la mise en garde « ne pas figer l'offset » de `case-27` reposait entièrement sur l'artefact.

Conséquence de découpe : les **résidus de `case-27` passent de 10 à 9**, et le verrou
« `GenerateMultiHitAttackPredictions` sur un sous-set de cibles » ne tient plus que 1051/1142 et
1098.

## 4. Ce qui reste OUVERT sur `AmuletOfTheVoidwyrm` (1464) — et ce n'est pas ce cas

`AmuletOfTheVoidwyrmPlaybook` **est** un playbook de MOUVEMENT, avec un corps propre
`IdunBattle.AI.Playbook.Loki.AmuletOfTheVoidwyrmPlaybook$$CalculateMovementUtilityInStepsInternal`
(+ sa machine à états `u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext`), plus une
face NonOwner `IdunBattle.AI.Playbook.Loki.AmuletOfTheVoidwyrmNonOwnerPlaybook$$GetAdjacencyUtility`
(base `AdjacentToOwnerNonOwnerPlaybook`1`). C'est le gisement réel, et il est **déjà inventorié** :
rang B de `docs/rl/case-193-inventaire-playbooks-mouvement.md` (§5, « 22 autres corps actifs
confrontables », corps NON lu). Fermer #218 ne ferme pas cet item-là — ne pas confondre les deux.

## 5. Le verrou de NIVEAU des reliques — localisé, et il n'est PAS lu par la bataille

La question était : où vit le niveau minimum exigé pour équiper une relique, et qui le lit ?

* **Pas dans la config de l'item.** `items["R_Booster_Crit_AmuletOfTheVoidwyrm"]` porte
  `isRelic`, `abilityId`, `allowedUnits` (`genesBiophagus`, `genesPrimus`, `genesKelermorph`) et
  ses 10 `levels` — qui sont les niveaux **de la relique** (coûts d'upgrade, `critChanceBonus` 6,
  `critDmgBonus` 350→521). **Aucun seuil de héros.**
* **Le seuil est global et porte sur la PROGRESSION** : `globalValues` →
  `tertiaryAbilityUnlockProgressionRequirement = 16` (`…RequirementMow = 16`). La relique est
  l'**ability TERTIAIRE** de l'unité.
* **Il est lu côté META, pas côté BATAILLE.**
  `IdunMetaLogic.UserProgress.UnitProgression$$ProgressionLevelNeededToUnlockTertiaryAbility(this,
  isMoW)` rend `gameConfig+0xa0` (MoW) ou `+0x9c` (non-MoW) — les deux valeurs ci-dessus. Tous ses
  consommateurs, comme ceux de `IdunMetaLogic.UserProgress.TertiaryAbilities$$GetTertiaryAbility`,
  vivent dans `IdunMetaLogic.UserProgress.*` (`GetAbilities`, `GetPower`,
  `GetTertiaryAbilityConfig`, `GetTertiaryAbility`). **Aucun caller `IdunBattle.*`.**
* **Ce que la bataille reçoit** est le champ déjà résolu `BattleConfiguration.Units[].TertiaryAbility`
  — et le seed BC partagé en porte **4** (`necroSpyder`→1462, `orksRuntherd`→1475,
  `admecMarshall`→1457, `admecRuststalker`→1457).

**Conséquence pratique** (à réutiliser le jour où une relique devra être confrontée live) : le seuil
de niveau **ne bloque pas la voie runner**. Il se contourne en écrivant `TertiaryAbility` dans la
seed BC augmentée (`catalog_inject`), exactement comme le seed en porte déjà quatre — la couche
bataille ne re-vérifie aucun niveau, elle consomme le champ. Ce n'était donc pas le verrou
qu'on craignait ; ce cas-ci n'en avait de toute façon pas besoin (rien à porter).

## 6. Technique généralisable

**Un « contrôle de bornes » qui regarde où les noms deviennent du bruit ne borne rien.** Le
débordement d'une vtable ne tombe pas dans du bruit : il tombe sur la vtable de la classe SUIVANTE,
qui est parfaitement formée et parfaitement nommée — `Equals / Finalize / GetHashCode / ToString`
en tête, puis des méthodes de playbook plausibles. La tranche 3 a vu « cohérent jusqu'à 0x5a8 puis
du bruit » et a conclu « 0x548 est bien dedans » : les deux moitiés de la phrase étaient vraies, et
la conclusion fausse.

**Trois bornes qui, elles, tranchent** — aucune ne demande de nouveau hook :

1. **La séquence répétée.** Si les slots `k..k+n` d'une classe reproduisent EXACTEMENT les slots
   `0..n` d'une autre, on lit l'autre. Un `Equals` en tête de séquence est le marqueur : une vtable
   ne contient qu'UN début.
2. **L'arithmétique des adresses.** `klass(B) - klass(A)` donne la taille réelle de A ; tout offset
   au-delà appartient à B. Deux appels `resolveVtableSlot` suffisent (il rend `klass`).
3. **La classe SŒUR initialisée.** Quand la classe visée a une vtable nulle, une autre classe de la
   MÊME base, elle initialisée, donne la forme exacte de la vtable — nombre de slots et noms. C'est
   la preuve POSITIVE, et c'est aussi ce qui sauve du symétrique : `slots = 0` ne veut pas dire
   « n'override pas », ça veut dire « je n'ai rien lu ».

**Et la borne structurelle qui rend tout le reste secondaire** : avant de chercher un override,
vérifier que la classe est dans la branche qui DÉCLARE le virtuel (`classes.tsv`, indexée par NOM).
Une classe hors branche ne peut pas overrider — aucune mesure de vtable n'est nécessaire pour le
savoir, et aucune mesure de vtable ne peut le contredire. Le réflexe « la dédup IL2CPP cache
peut-être un override » est juste ; il ne dispense pas de regarder si l'héritage rend l'override
possible.
