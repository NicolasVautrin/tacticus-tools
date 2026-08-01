# #429 — Trois inventaires de la même question, et le compte de porteurs était faux par construction

**Livré le 2026-08-01.** Build de référence : `rnca9r7q6c` (celui qui fait foi).

## 1. Ce que le dépôt croyait recenser

Trois artefacts répondaient à « quelles règles de ciblage ne sont pas portées ». Chacun se lisait
comme une réponse **entière** ; aucun ne l'était, et aucun ne le disait.

| # | artefact | forme | ce qu'il énumérait | verdict qu'il rendait |
|---|---|---|---|---|
| T1 | `probe_249_unported_rule_carriers.py::TARGET_RULES_AUDIT` | table Python **saisie** | **13** règles | « 6 abilities touchées / 103 » |
| T2 | `probe_targeting_coverage.py::PORTEES` (+ `NON_REGLES`) | deux listes **saisies** (7 + 16) | **19** règles non portées, par complément | « 48 masques / 102 » |
| T3 | en-tête de `engine/runner/abilities/targeting.py` | prose tabulaire | **30** membres classés, **11** marqués NON | pas de compte global |

**Mesure re-dérivée : 25 règles GATE non portées sur 46, et 103 / 103 abilities touchées.**
Les trois verdicts étaient donc faux, chacun dans un sens différent — T1 sous-estimait d'un facteur
17, T2 sur-estimait le nombre de règles non portées en en listant **dix qui sont portées**.

> Le brief annonçait 13 / 6 / 5 entrées, union 19, intersection 0. **Ma mesure diffère et fait
> foi** : je trouve 13 / 7 / 30 entrées énumérées. Les deux comptes ne mesurent pas la même chose —
> le brief comptait vraisemblablement les noms *reconnaissables par regex*, ce qui rate les formes
> abrégées (`CasterHas1/3/7Tiles` est un seul token, pas trois noms). Le fond est identique et il
> tient : trois recensements partiels, aucun conscient de l'être.

## 2. La faute commune, et elle n'est pas l'oubli

Les trois comptaient **les porteurs du BIT**. Or **trois règles du filtre statique ne sont pas
armées par leur propre bit** — relu sur `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason`
(surcharge 7 arguments) :

| règle | ce qui l'ARME réellement | par le bit | par l'armement |
|---|---|---|---|
| `TargetIsAllowedForCaster` (TAUNT) | `TargetIsEnemy \| TargetIsCasterOrEnemy`, désarmé par `AllowIgnoreForcedAttackTarget` — **son bit n'est jamais testé** | **0** | **59** |
| `TargetIsNotSteppable` | son bit **OU** `get_IsUnitTargeting` sans `AllowSteppableUnit` | **1** | **83** |
| `TargetIsUnit` | l'**absence** de `TargetIsTile \| TargetIsMachine \| TargetIsActor` | — | par défaut |

`get_IsUnitTargeting` ne lit pas un bit à lui : `TargetingOptions$$get_IsUnitTargeting` rend
« ni tuile, ni machine, ni acteur », donc **vrai par défaut**. D'où le « 0 porteur, rien à y
porter » qui accompagnait `TargetIsAllowedForCaster` : un **zéro de méthode**, pas un zéro de fait.

Deux règles s'y ajoutent, ratées pour d'autres raisons :

* `TargetIsUnobscured` (bit 24) — la **ligne de vue**. Seule règle du filtre dont le refus ne passe
  pas par `TargetingRuleExtensions$$GenericBrokenTargetingRule` : le natif boxe
  `IdunBattle.Core.Services.ObscuredTerrainBrokenTargetingRule`, dont `get_Type` rend `0x1000000`.
  **Aucun bit ne l'arme** (les bits 25/26 ne font que la désarmer) : elle tourne pour les **103**
  masques lisibles, et elle est non portée.
* `CasterIsPossibleTarget` (bit 15) — `targeting.py` le donnait pour « flag DÉCLARATIF, n'apparaît
  NI dans le filtre cible NI dans `GetInvalidCasterReason` », en précisant « vérifié
  exhaustivement sur les DEUX cascades ». Il y a une **troisième** cascade :
  `TargetingQuery$$GetCasterNotAddedReason` teste `rules >> 0xf & 1` et **ré-applique la cascade
  CIBLE complète au caster pris comme cible**. Non portée, **13** masques l'arment.

Enfin, une règle rend un code qui n'est pas son nom : la tête de domaine `TargetIsTile` rend le
littéral `1` = `ValidRequest`. Un audit qui chercherait « le port rend-il `TargetIsTile` ? »
conclurait à tort au non-port — c'est le champ `reason_code` de l'inventaire.

## 3. Le sort des trois tables

* **T1 `probe_249`** — table saisie **supprimée**. Le probe **dérive** désormais, garde son nom
  (case-docs et backlog le citent) et devient une **vue explicitement bornée** : cascade CIBLE
  seule, et il l'imprime. Il chiffre en plus, par règle, l'écart entre le compte par le bit et le
  compte par l'armement.
* **T2 `probe_targeting_coverage`** — les deux listes saisies **supprimées**. Le probe dérive
  `PORTE` de l'AST et `NON-RÈGLE` du rôle natif. Il garde son angle propre : la vue **par ability**.
* **T3 en-tête de `targeting.py`** — **borné explicitement** : il décrit désormais l'**ORDRE** de
  la cascade (ce qui fixe la raison rendue), pas le recensement. Les deux comptes faux (`0 porteur`
  pour les bits 23 et 51) sont corrigés sur place avec leur armement, la ligne de vue entre au
  tableau, et la note « vérifié exhaustivement sur les DEUX cascades » est rectifiée.

L'inventaire unique est **`engine/runner/abilities/targeting_rule_inventory.py`** : les **60**
membres, leur rôle natif, leur lecteur, leur armement. Il ne déclare **aucun nom de bit** (ses clés
sont des chaînes confrontées au mirror généré) — l'invariant « une seule source de noms » tient.

## 4. Ce qui est dérivé, et pourquoi c'est *cette* colonne

**« Porté / non porté » n'est saisi nulle part.** C'est la donnée qui bouge à chaque tranche livrée,
donc celle qui pourrit en silence dans une table écrite — les trois l'ont fait. Elle se dérive de
l'AST du port : une règle est portée si le port peut la **rendre** comme code de refus
(`return int(TR.<X>)`).

Le critère a dû être durci : « un `TR.<X>` sous un `return` » captait aussi les **getters
déclaratifs** (`return self.has(TR.CasterIsPossibleTarget)`), qui ne refusent rien. Seul
`int(TR.<X>)` est un code de refus.

## 5. La garde — `tests/engine/runner/test_targeting_rule_inventory.py` (16 tests, 6,0 s, offline)

Elle tient les **deux directions** de la différence symétrique `enum <-> inventaire` :

* **VIVANTE** — `dump \ inventaire` vide : un membre neuf au re-dump fait échouer tant qu'il n'est
  pas classé ;
* **MORTE** — `inventaire \ dump` vide : une entrée dont le membre a disparu fait échouer aussi.
  C'est la direction qu'aucun des trois ne tenait.

Plus : `mirror <-> dump du build courant`, la bijection `armed_by` ⟷ prédicats (sans elle un compte
retomberait sur le bit), l'intégrité des `kind`/`reader`/`reason_code`, et deux contre-mesures
chiffrées qui échouent si `TargetIsAllowedForCaster` ou `TargetIsNotSteppable` retombent au compte
par le bit.

**Trois contre-épreuves sont INTÉGRÉES** (mode de défaillance EXECUTION de #427 : une garde juste
mais jamais jouée ne vaut rien) — membre neuf, entrée morte, prédicat d'armement retiré. Chacune
vérifie d'abord que **sa mutation a mordu**.

### La contre-épreuve qui a menti

Premier jet : ajout de `__MutantRule = 1 << 58` au mirror. **VERT.** `enum` **ignore** les noms
privés — le mirror gardait ses 60 membres, la mutation n'avait pas eu lieu, et le vert se lisait
« la garde ne mord pas ». Renommé `MutantRule` → ROUGE (`mirror \ dump = ['MutantRule']`),
restauré → vert. D'où l'`assert ..., "la mutation n'a pas mordu"` en tête de chaque contre-épreuve.

Seconde contre-épreuve, sur l'**assertion** et non sur la donnée : `manquants = []` dans la
direction vivante → ROUGE sur `test_contre_epreuve_direction_vivante` (`DID NOT RAISE`), restauré →
vert. Les contre-épreuves gardent donc bien le code de la garde, pas seulement ses entrées.

### Un trou de ma propre garde, mesuré sur moi-même

`test_mirror_couvre_le_dump_du_build_courant` compare les **noms** de membres. Les deux dumps
déclarant le même enum, un mirror généré depuis un build **archivé** restait parfaitement vert avec
une **estampille qui mentait** — et c'est exactement ce que mon arbre a porté un moment, un
`git checkout --` de contre-épreuve ayant annulé la régénération sans que rien ne rougisse. D'où
`test_estampille_du_mirror_est_le_build_courant`, qui lit le hash cité dans la docstring du mirror.
Contre-épreuve : estampille remise à `gqfc5mff6c` → ROUGE ; `gen_targeting_rule.py` → vert.
**La coïncidence des noms entre deux builds est un accident de ce build, pas une propriété.**

## 6. Trouvé en chemin

**Le mirror `targeting_rule.py` était généré depuis un build ARCHIVÉ.** `gen_targeting_rule.py` et
`probe_targeting_rule_bits.py` lisaient tous deux `sorted(glob("*/BUILD"))[0]` — le premier build
par ordre **alphabétique**, soit `gqfc5mff6c`, alors que `data/symbols/CURRENT` vaut `rnca9r7q6c`.
Aucun dégât : les deux dumps déclarent le même enum, donc le mirror était juste **par chance**. Et
le probe censé garder la cohérence lisait **la même** entrée périmée — deux lecteurs qui partagent
une entrée périmée s'accordent toujours. Les deux passent par `symbols_layout.current_build()`, et
`test_mirror_couvre_le_dump_du_build_courant` ferme la classe.

**Trois indices de slot `IBattleQuery` ont bougé de +1** entre `gqfc5mff6c` et `rnca9r7q6c` :
`GetFreeAdjacentTiles` 0x51 → 0x52 (bits 5 et 21), `AreTilesAdjacent` 0x61 → 0x62 (bit 32),
`GetAdjacentEnemies` 0x7f → 0x80 (bit 42). `IAttackQuery` est inchangé (0x11 / 0x12) — deux
interfaces distinctes. Aucun dégât fonctionnel (le port n'appelle pas par slot), mais les slots
cités en commentaire dans `targeting.py` ne résolvent plus ; le décalage est nommé dans son en-tête.

## 7. Résidus nommés

* **`AbilityIsNotDisabledByConfigModification` (bit 34) et `AllowDeadTarget` (bit 38) — lecteur non
  localisé** dans les huit fonctions relues. Ce n'est **pas** une preuve de mort : le terme i2
  `IdunLocalization.Tooltips$$BattleHUD_Tooltip_AbilityDisabledByConfigModification_Description`
  existe, donc la raison est présentée quelque part. Classés `READER_UNKNOWN`, sous garde.
  ⚠ `mcp__ghidra__search_code` **ne prouve pas une absence** : mesuré, il rend `literal_total: 1`
  pour un motif présent deux fois dans une fonction décompilée à la demande. Son index est partiel.
* **Les trois gros gisements de non-port**, désormais chiffrés et actionnables : ligne de vue
  (`TargetIsUnobscured`, 103), `TargetIsNotSteppable` (83), TAUNT `TargetIsAllowedForCaster` (59).
  Les trois dégradent **permissivement** (le moteur accepte des casts que le natif refuse), donc
  invisibles en self-play. Le gisement **ciblé** — hors règles armées par défaut — vaut
  **26 abilities / 103**.
  → **Deux sont fermés depuis** : le TAUNT par #436 (`case-436-taunt-target-is-allowed-for-caster.md`),
  `TargetIsNotSteppable` par #442 (`case-442-target-is-not-steppable.md`). Reste la ligne de vue.
* **`GetCasterNotAddedReason` non portée** reste le verrou de `CasterHasFreeAdjacentTile`
  (2 porteurs) et de `CasterIsPossibleTarget` (13 masques armés).

## 8. Re-dériver

```
python scripts/python/probe_429_targeting_rule_inventory.py            # inventaire complet
python scripts/python/probe_429_targeting_rule_inventory.py --only-gaps
python scripts/python/probe_249_unported_rule_carriers.py             # vue bornee : cascade CIBLE
python scripts/python/probe_targeting_coverage.py                     # vue par ABILITY
python -m pytest tests/engine/runner/test_targeting_rule_inventory.py -q
```

⚠ Les chiffres de cette fiche se **re-dérivent**. Ils bougent à chaque règle portée.
