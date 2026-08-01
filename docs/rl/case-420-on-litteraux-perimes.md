# #420 — Les ordinaux `EventTriggerType` périmés en prose, et les deux gisements que `probe_283` ne voyait pas

**Verdict : 251 citations corrigées, 0 test rendu rouge, et le probe passe de `FAIL` à `PASS`
en 128 s au lieu de 147.** Aucune des 220 citations `On(<n>)` mesurées n'était exécutable :
le risque annoncé (« un test VERT qui asserte sur le mauvais événement ») **n'existait pas**
sous cette forme — mais deux gisements voisins, eux **invisibles au probe**, portaient
31 citations périmées de plus, dont une dans la documentation d'une **composition
`UtilityType`** relue au décompilé.

## 1. La mesure complète (le point de départ était tronqué)

`python scripts/python/probe_283_enum_ordinal_sweep.py` sur `origin/master` : **rc=1,
VERDICT FAIL(1)**, et l'étape 5 comptait **220** sites `On(<n>)` ambigus sur **~80 fichiers**
— pas 5. Le `FAIL(1)`, lui, ne venait **pas** d'`EventTriggerType` : c'était un faux positif
sur `UtilityType` (cf. §5).

Cause racine, re-dérivée de `data/symbols/*/frida/enums.tsv` : `gqfc5mff6c` → `rnca9r7q6c`
**retire `ArmorChanged` (40)** d'`EventTriggerType` (77 → 76 membres), donc **tout ordinal
≥ 40 glisse de −1**. 36 membres déplacés.

### Le risque annoncé, mesuré : nul

L'étape 5 ne scanne que les tokens `COMMENT`/`STRING` — les citations sont **inertes**.
Vérifié en propre : sur les 220 sites, **0** a un littéral **exécutable** de la même valeur
dans un rayon de ±6 lignes. Les étapes 1/2/3 (les trois gates exécutables) étaient déjà
vertes. Un test ne pouvait donc pas « asserter sur le mauvais événement » par cette voie.

Ce que ces citations cassaient, c'est le **lecteur** : `handler.py` portait, sur deux lignes
voisines, `` `On(0x2b)` `` et « le natif émet `PreUnitAbility (0x2a)` ».

## 2. Ne PAS renuméroter mécaniquement — la preuve par les contre-exemples

Un décalage uniforme aurait été **faux** : une partie du dépôt était déjà écrite en
numérotation NOUVELLE. Mesuré, sur le même ordinal :

| Citation | Contexte | Verdict |
|---|---|---|
| `On(0x3d)` = « on-block » | `additional_hits.py`, `attack.py`, `anvil_shield.py` | **PÉRIMÉ** → `0x3c` |
| `On(0x3c)` = « on_blocked » | `damage_hits.py`, `harlequins_panoply.py` | **JUSTE** |
| `On(0x3a)` = `PreDamageTaken` | `damage.py`, `on_toxic_damage.py`, `probe_o10_*` | **PÉRIMÉ** → `0x39` |
| `On(0x3a)` = `PhaseEnd` | `phase.py`, `ramming_speed.py` | **JUSTE** |
| `On(0x36)`/`On(0x35)` | `move_death.py`, `damage.py`, `state.py` | **JUSTE** (nouvelle numérotation) |
| `On(0x37)`/`On(0x36)` | `cosmic_horror.py`, `terrifying_crescendo.py` | **PÉRIMÉ** → `0x36`/`0x35` |

Deux fichiers portaient **les deux conventions à la fois** (`registry.py` :
`On(UnitBlocked=0x3c)` juste ligne 287, `On(0x3d)` périmé ligne 289).

### Trois sites que seul le décompilé tranchait

| Site | Hypothèse « par le sens » | Décompilé `rnca9r7q6c` |
|---|---|---|
| `HazeOfCorruption_DamageTransferEffect$$CreateTargetTrigger` | `On(0x35)` = `PostUnitKill` (contexte de mort) | `On(0x2d)` **`UnitRevived`** + `On(0x34)` **`UnitFled`** |
| `IconOfObstinacy_AddArmourBuffAbility$$CreateTrigger` | `0x28` = `ArmorChanged` (membre **supprimé**) | `DSLTriggers$$On(0x28, true)` = **`UnitFinishedTurn`**, gaté par `AmountIsZero(TimesAttackMadeThisTurn)` |
| `ADamageOperation$$EvaluateAfterHitTriggers` | branche « crit » (ce que disait la doc) | paramètre nommé **`didBlock`** ; `didBlock != 0` → `0x3c` = `UnitBlocked` |

Ancre décisive pour le plus gros cluster (~50 sites) :
`ActiveAbilityOperation$$ExecuteInternal` publie, par adresse croissante,
**`0x2a` → `0xb` → `0xc` → `0xe`**. `On(0x2b)` était donc périmé partout.

Séquence de mort confirmée sur le binaire courant :
`KillUnitOperation$$Execute` = `1` → `2` → `0` → **`0x36`** (`UnitDefeated`) → **`0x35`**
(`PostUnitKill`). Et `ReviveUnitOperation` = `0x2d`, `ResurrectUnitOperation` = `0x2e`,
`ApplyDamageOperation` = `0x39`/`0x1e`/`0xf`/`0x27`/`0x10`, `FinishUnitTurnOperation` =
`0x1c`/`0x28`/`0x29`, `AddEffectOperation` = `0x3d`/`0x3e`/`0x46`, `RemoveEffectOperation` =
`0x3f`/`0x40`/`0x3b`, `AddUnitOperation` = `0x32`/`0x41`.

## 3. La forme livrée : `On(<n> = <Membre>)`

Les 220 sites passent de `On(<n>)` à **`On(<n> = <Membre>)`**. Ce n'est pas cosmétique :
cette forme **sort** de l'étape 5 (indécidable par construction) et **entre** dans l'étape 4,
qui confronte nom ↔ ordinal à chaque run. L'ordinal écrit est **dérivé** d'`enums.tsv`,
jamais saisi.

Étape 5, ancre `On(` : **220 → 0**.

## 4. Les deux gisements INVISIBLES (31 sites de plus)

Ils n'étaient signalés par **aucune** étape — c'est le vrai enseignement du dossier.

**(a) 18 quotes verbatim du helper de publication** — `FUN_<addr>(0x4d|0x50, .., <ordinal>)`,
recopiées du décompilé : ni ancre `On(`, ni membre accolé. S'y ajoute que le nom
`FUN_180026490` **ne résout sur RIEN** dans `rnca9r7q6c` (vérifié : `decompile_function`
→ *not found*) ; le helper courant est `FUN_1800280e0` pour les deux slots — **37**
occurrences renommées.

**(b) 13 citations NOMMÉES à séparateur trop long** pour l'étape 4 (`[\s=:]{0,4}`) :
`` `...,0x37` UnitDefeated ``, `` `0x2f` UnitResurrected ``, `On(UnitRevived = 45 = 0x2e)`
(forme triple : moitié juste, moitié périmée). **12 corrigées, 1 laissée** — voir §6.

## 5. Trois défauts de `probe_283` lui-même, corrigés

1. **Le faux positif qui interdisait d'en faire un cliquet.** `WeightedUtility(utility_type=99999)`
   (`test_353r1_…`) EXIGE un type hors base — le test vérifie que `CalculateUtility` **lève**.
   L'étape 2 le comptait, donc `VERDICT: FAIL` sur `origin/master`. Règle posée : un littéral
   absent des DEUX builds ne **désigne** aucun membre — c'est une sentinelle, listée à part,
   non comptée.
2. **Étape 4bis (GATE)** — même scan prose, séparateur LARGE + forme triple, sous le critère
   **PROUVÉ** « le nombre vaut l'ordinal du build ARCHIVÉ ». Coût mesuré : **+3 s**.
   Quatre filtres, chacun posé sur un faux positif **mesuré** :
   * direction membre-d'abord écartée (les 13 sites vrais sont tous nombre-d'abord ou triple ;
     et `Damage`/`Attack`/`Heal` sont des membres `UtilityType`, donc des mots courants →
     l'étape passait de 46 s à **plus de 300 s**) ;
   * **virgule et slash hors séparateur** : `(SummonDislikeDoorOpening 30 / HeroLikeDoorOpening 31)`
     appariait `30` à sa **voisine**, sur une ligne juste ;
   * un nombre précédé de `On(` est **typé** `EventTriggerType` par le contrat natif — sans
     ce gate, `` `On(0x12)` -> ActivateEffect `` rougissait comme `StepType.ActivateEffect`
     (3 sites) ;
   * exemption **historique** (§6), portée ±3 **lignes** : un bloc `#` est découpé en un token
     par ligne, donc un test au token rate le cas.
3. **Étape 5, seconde ancre** : la quote de publication, au même titre que `On(`. Elle reste un
   COMPTEUR — l'ancre est sûre, le verdict ne l'est pas.

## 6. Le seul site laissé TEL QUEL, et pourquoi

`scripts/python/probe_hazeord_blast_radius.py:34` :

> `⚠ RESOLUS PAR MEMBRE, jamais par ordinal (#283). Cette table portait `55: "UnitDefeated"`,
> juste sur `gqfc5mff6c` : la MAJ `rnca9r7q6c` a retire `ArmorChanged` (40), donc `UnitDefeated`
> vaut 54 et 55 est `AttackChanged`.`

C'est un **rappel historique volontaire** : le corriger détruirait ce qu'il documente.
L'exemption du gate est adossée à ce qui le rend reconnaissable — le **nom du build archivé**
cité à portée. (La ligne 12 du même fichier, elle, était une vraie citation périmée → corrigée.)

## 7. Trouvé par le gate neuf, hors périmètre `EventTriggerType`

`UtilityType.MovementSuggestion` : les deux documentations de sa composition
(`engine/utilities/tile.py`, `engine/runner/abilities/genestealer.py`) citaient la clé `0x20`
et l'enfant `0x21`. Relu sur `rnca9r7q6c` — `UtilitiesDatabase$$InitializeUtilities`, dictionnaire
`UtilitiesDatabase+0x58`, **8 entrées** : la clé est **`0x21`** (MovementSuggestion = 33), les
enfants sont **`[7, 0x22]`** = `Tile(7)` puis `TileDistance(34)`, et **aucune clé `0x20` n'existe**.
Le code exécutable passait déjà par le membre nommé (`UtilityType.MovementSuggestion`) — c'est
la doc seule qui mentait.

## 8. Ce que ça coûte, et la recommandation

A/B **sur le même arbre** (celui d'après correction), back-to-back :

| | probe d'origine | probe #420 |
|---|---|---|
| mur `--step all` | **147,1 s** | **128,0 s** |
| verdict | `FAIL (1)` — faux positif | **`PASS`** |

Le probe **coûte moins cher qu'avant** tout en gagnant deux surfaces de détection : l'étape 5
n'itère plus 220 sites à l'affichage (`on` seul : 39,9 s → 11,4 s) et 4bis coûte ~3 s.
Ventilation `--step` : `diff` 0,5 · `mirror` 46 · `exec` 57-72 · `tables` 34 · `prose`+4bis
33-49 · `on` 11.

⚠ **L'absolu se lit à ±2×, pas au dixième.** Le même probe a été mesuré entre **128 s** et
**260 s** selon le nombre d'agents en vol — c'est exactement le régime décrit par `case-409`
(« 3 mesures alternées, 3 agents en vol : 100,1 / 153,9 / 221,9 s »). Seule la comparaison
**back-to-back** ci-dessus est interprétable ; l'absolu doit être re-mesuré machine calme.
Piège de mesure, payé une fois : poser la copie de référence dans `scripts/python/` la fait
**scanner par le probe** (elle cite `On(0x2b)` dans sa propre docstring) — le verdict tombe à
`FAIL` pour une raison qui n'existe pas dans l'arbre. La supprimer AVANT de mesurer.

**Recommandation — les DEUX, parce qu'elles ne couvrent pas le même risque :**

* **Cliquet permanent** (obligatoire). C'est le seul des deux qui voit la casse qui a
  RÉELLEMENT eu lieu : une **migration de build** a invalidé 220 citations **sans toucher une
  seule ligne** de ces fichiers. Un déclencheur sur diff y est **structurellement aveugle**.
  Coût : 128 s. La banque des 9 cliquets tourne en parallèle et son mur n'est plus `probe_273`
  (24 s depuis #409) mais `pytest signatures` (~59 s en série) — probe_283 **deviendrait le
  nouveau mur**, à ~128 s. C'est le prix à énoncer.
  Réduction disponible si ce prix est jugé trop élevé : ne jouer que les GATES
  (`mirror` + `exec` + `tables` + `prose`) et laisser `on` (compteur) hors banque — ~117 s.
* **Déclencheur sur diff** (complémentaire, quasi gratuit) : dès qu'un diff touche un littéral
  `On(` ou une quote `FUN_<addr>(0x4d|0x50`. Il attrape l'autre moitié du gisement, celle que
  notre propre cadence alimente — et le taux y est **mesuré atroce** : sur les 7 sites écrits
  APRÈS la migration, **6 recopiaient l'ancienne valeur**.

**Le chiffre qui tranche a été produit PAR ce dossier, pendant qu'il se faisait.** Le rebase
sur `origin/master` (**14 commits**, quelques heures) a **ré-ouvert le gisement en direct** :
**15** `On(<n>)` nus neufs (tranche #448-r2), plus **1** littéral EXÉCUTABLE qui faisait
retomber le verdict à `FAIL`. Sur une fenêtre où l'énoncé de départ voyait « 5 sites », la
cadence du dépôt en produit 15 en une demi-journée. Un cliquet qui ne tourne pas à chaque PR
laisse donc le compte remonter plus vite qu'on ne le vide.

(Le littéral exécutable était un **faux positif**, et il valait la peine : la table de
signatures positionnelles de l'étape 2 est GLOBALE, donc un **homonyme** l'empoisonne. `_ev` a
**5 définitions** dans le dépôt, une seule typée — elle faisait lire le `_ev(0)` d'un test
étranger comme un `EventTriggerType`. Corrigé : un nom n'entre dans la table que si TOUTES ses
définitions du périmètre s'accordent sur le même `(index, enum)`.)

## 9. Résidus nommés

* **#420-r1 — 16 quotes `FUN_` restent indécidables.** Elles sont justes aujourd'hui, mais
  l'étape 5 ne peut pas le prouver (pas de membre accolé) et on ne peut pas en ajouter un
  sans **falsifier une citation verbatim**. Piste : un commentaire de fin de ligne portant le
  membre (`# PreUnitAbility`), que 4bis garderait alors — 3 quotes en ont déjà un.
* **#420-r2 — la forme `FUN_<addr>(0x51, .., <LIT>, &args)` n'est pas ancrée** : le littéral y
  est l'AVANT-dernier argument. Émetteurs connus : `ResurrectUnitOperation`,
  `FinishUnitTurnOperation`, une partie d'`ApplyDamageOperation`.
* **#420-r3 — 2 quotes qui élident le slot** (`FUN_1800280e0(.., 0x2a)`) échappent à l'ancre,
  qui exige `0x4d`/`0x50` pour être sûre.
* **#420-r4 — l'étape 4 laisse 15 citations « à lire »** (origine inconnue, ni juste ni ancien
  ordinal). Non traitées ici : ce ne sont pas des ordinaux `EventTriggerType`.

## 10. Ce qui n'est PAS couvert

* **`docs/`** — non traité (périmètre `scripts/python`). Re-mesuré : **153** `On(<n>)` nus
  ambigus + 4 quotes `FUN_`. Arbitrage antérieur maintenu (`case-283` §7, `case-254b-b` §7 :
  les case-docs sont **datées**, on ne rétro-corrige pas un compte rendu produit par un autre
  build). Rangé sous #283-r2.
* **Les trois autres enums renumérotés** (`UtilityType`, `StepType`, `DisplaceDirection`) n'ont
  pas fait l'objet d'un balayage dédié. Le gate 4bis en a sorti **deux** sites `UtilityType`
  (§7) — c'est un échantillon, pas un inventaire.
* **`hooks-legacy/`** : inventorié à part par le probe, hors gate, non touché.
* **Les 15 citations « à lire » de l'étape 4** (#420-r4) : ni justes ni prouvées périmées.
* **Aucune vérification live** n'était possible ni pertinente : le changement est
  intégralement en commentaires et docstrings, sauf `probe_283` lui-même. La preuve d'inertie
  est le `py_compile` des **91** fichiers touchés + le `--collect-only` (185 tests) + les
  8 fichiers de test rejoués.

## 11. Reproduire

```
python scripts/python/probe_283_enum_ordinal_sweep.py            # le balayage complet
python -m pytest scripts/python/tests/test_enum_ordinal_ratchet_offline.py   # son cliquet (18)
```
