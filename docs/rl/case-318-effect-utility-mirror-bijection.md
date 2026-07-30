# case-318 — `EffectType` et `UtilityType` : les deux dernières dettes de bijection, résorbées

**Tâche** : #318 (`[opus]`). **Build** : `rnca9r7q6c`. **Prédécesseurs** : #270 (ActiveAbilityType),
#275 (`enum_maps`), #313 (le cliquet de bijection et la mesure des deux dettes), #219 (les mêmes
placeholders, dans le mirror voisin).

## 1. Le critère

> `probe_313_enum_mirror_bijection.py` classe-t-il `EffectType` et `UtilityType` en **OK / SOUS
> GARDE** au lieu de **dette déclarée**, sans qu'aucune référence qualifiée ne casse ?

**Oui.** Le registre passe de **8 mirrors sous garde + 2 dettes** à **10 sous garde, 0 dette**.

| mirror | avant | après |
|---|---|---|
| `EffectType` (`engine/entities/effect_type.py`) | port=682, jeu=629 — **(20 manquants, 73 morts, 2 RENUMÉROTÉS)** | port=629, jeu=629 — **(0, 0, 0)** |
| `UtilityType` (`engine/utilities/utility_type.py`) | port=68, jeu=83 — **(15 manquants, 0, 0)** | port=83, jeu=83 — **(0, 0, 0)** |

Étape 3 (références qualifiées `<Classe>.<membre>` par AST, sur du Python suivi) :
**total=1438, INTROUVABLES=0, MORTES=0** — identique avant et après. Aucune référence n'a été
créée ni cassée par la régénération.

## 2. Les 2 RENUMÉROTÉS — la seule forme qui coûtait

`1563` / `1564` portaient `DA_Hero6_Passive_1` / `_2`. Le jeu dit
`SpecialIssueCombiMelta_AdditionalHits` / `SpecialIssueCombiMelta_ExtraDmg`.

Un membre **manquant lève**, un membre **mort est inerte**, un membre **renuméroté résout — et
résout faux**. Ni erreur, ni crash, ni test rouge.

**Ce n'est pas un renommage : c'est une transcription qui n'a jamais été juste.** Mesuré sur les
deux builds versionnés :

```
gqfc5mff6c : 1563=SpecialIssueCombiMelta_AdditionalHits  1564=SpecialIssueCombiMelta_ExtraDmg
rnca9r7q6c : 1563=SpecialIssueCombiMelta_AdditionalHits  1564=SpecialIssueCombiMelta_ExtraDmg
occurrences de "DA_Hero6" dans les deux enums.tsv : 0
```

Les placeholders viennent de `data/il2cpp_enums.tsv` (dump Il2CppDumper supprimé le 2026-07-25) —
**déjà périmé au moment de sa transcription**. C'est exactement le diagnostic de la case-219 sur
`TriggeredAbilityType` (1545 / 1548 / 1551), dont `triggered_ability_type.py` porte encore le
commentaire : *« le même placeholder survit d'ailleurs encore dans `engine/entities/effect_type.py`
(1563/1564) »*. Le motif n'avait jamais été balayé latéralement — c'est ce que #313 puis #318 ont
fait.

**La sémantique est confirmée par une SECONDE source, indépendante de `enums.tsv`** — les classes
d'effet natives portent le même nom, et leur méthode dit ce que l'effet fait :

```
Idun.Source.IdunBattle.Logic.Entities.Effects.Loki.SpecialIssueCombiMelta_AdditionalHitsEffect$$CreateAdditionalHits
Idun.Source.IdunBattle.Logic.Entities.Effects.Loki.SpecialIssueCombiMelta_ExtraDmgEffect$$CreateEffectDamageBonusForAttack
IdunBattleLogic.Entities.Abilities.Triggered.Loki.SpecialIssueCombiMelta_InitAbility$$CreateBehaviour
IdunBattleLogic.Entities.Abilities.Triggered.Loki.SpecialIssueCombiMelta_AddEffectAbility$$CreateTrigger
```

1563 = coups additionnels, 1564 = bonus de dégât, posés sur *self* par le passif **1545
`SpecialIssueCombiMelta`** de `darkaSternguard` (cf. `case-220/dark-angels.md`, qui pose ces deux
ids `AddEffect 1563+1564 self` et laisse leur sémantique en HYPOTHÈSE — elle ne l'est plus).

**Site par site, le code qui citait l'ancien nom** : il n'y en a **aucun**. Balayage textuel des
75 noms (73 morts + 2 renumérotés) sur tous les fichiers suivis, plus recherche des littéraux
`1563` / `1564` / `0x61b` / `0x61c` :

* `enum_maps.py` (630-631) et `frida/hooks/data/effect-type-names.ts` (618-619) disaient **déjà
  juste** — corrigés par #275/#256. Le dépôt portait donc **deux tables du même enum qui se
  contredisaient**, et c'est celle que le code exécutable lit qui était fausse ;
* les seules autres occurrences sont des **docs** (`backlog`, `case-275`, `case-313`,
  `case-220/dark-angels`, `case-72-onmelta-dead-code`) et le cliquet #313 lui-même ;
* aucun `EffectType.DA_Hero6_Passive_*` en Python (étape 3 : 0 morte), aucun littéral 1563/1564
  sous `engine/`.

L'ability n'étant pas portée, **le renumérotage n'a jamais produit de valeur fausse en sortie** :
il attendait le premier port de `SpecialIssueCombiMelta` pour le faire.

## 3. Les 73 MORTS — vérifiés avant retrait (piège #270)

Tous dans la plage **3..104** : les effets de l'ancien moteur `Idun` (`HawkEye_*`, `SpiderWeb*`,
`FireRage_*`, `Polearm_*`, `Bushkin_ExtraAttack`, `BattleTinkerer_ExtraDmg`, `Idun_Concealed`…).
Le build ne les émet plus.

Quatre contrôles avant de les retirer, tous à zéro :

| contrôle | portée | résultat |
|---|---|---|
| étape 3 de `probe_313` (AST, `<Classe>.<membre>`) | Python suivi | **0 référence** |
| balayage textuel des 73 noms | **tous** les fichiers suivis | 0 hit exécutable hors mirror |
| appels `EffectType(<littéral int>)` (AST) | Python suivi | 2 appels, **0 invalide** |
| clés du registre `EFFECT_CLASSES` (`entities/effects/factory.py`) | 124 clés | **0 absente du mirror** |

Le dernier contrôle est le plus important et ne figurait dans aucun cliquet : `EffectType` n'est
pas qu'une table, c'est le **dictionnaire consommé PAR NOM** — `EffectFactory` par ses clés,
`_materialize_owner_effect` par `EffectType.__members__.get(name)`. Une clé qui ne résout plus ne
lève pas : elle produit un effet à `effectType=None`, et le `int(effect_type)` casse bien plus
loin. Il est désormais gardé (`test_le_registre_EFFECT_CLASSES_resout_entierement_dans_le_mirror`).

Smoke offline complémentaire : **305 modules `engine.*` importés, 0 échec** après retrait.

**Hors périmètre, signalé** : `scripts/sql/006_ref_tables.sql` et `013_enum_fk_and_names.sql`
nomment encore les 73 morts (`(13, 'SpiderWeb')`, …) et n'ont pas les 20 nouveaux. Ce sont des
**migrations**, cibles de FK — le backlog les traite déjà (**#270-b**, résidus `ref_effect` /
`ref_triggered_ability` : ajouter est urgent, retirer est inerte). Non touchées ici.

## 4. `UtilityType` — le sens MANQUANT n'est pas inerte

15 membres ajoutés (`68`-`81` + `STRIPPED = 9999`). Purement additif : 0 mort, 0 renuméroté.

La docstring du mirror justifiait le trou par « ajouter au fil des call-sites, jamais deviner ».
**Cette doctrine ne s'applique pas ici**, et c'est le point de la tâche : ces valeurs *traversent
la frontière avec le jeu*. Le RPC `dumpComposedUtility` rend des clés **numériques** du build
courant ; une clé que le port ne sait pas nommer est **jetée**, pas signalée — la feuille
correspondante disparaît de l'inventaire sans un mot. Porter un NOM juste ne coûte rien et rend la
lacune constatable ; c'est porter une **feuille** (lire son
`IdunBattle.AI.Utilities.<X>Utility$$.ctor` et son `EvaluateMovementInSteps`) qui est un travail à
part entière — aucune des 15 n'est implémentée, et le mirror le dit désormais.

À noter : #283 garde ce mirror et ne voyait **aucun** de ces 15, faute de tester le sens manquant.

## 5. Ce que le cliquet garde maintenant

`tests/test_enum_mirror_ratchet_offline.py` — **16 tests, tous verts**. Ajouts de #318 :

* `test_aucune_dette_declaree_ne_subsiste` — le zéro est un **cliquet**, pas un acquis. Rouvrir une
  dette reste possible, mais oblige à éditer ce test : c'est l'effet voulu ;
* `test_les_deux_ids_ex_RENUMEROTES_d_EffectType_portent_le_nom_DU_JEU` — fige la correction PAR
  NOM (`EffectType(1563).name`), et interdit le retour des placeholders ;
* `test_les_20_membres_ajoutes_a_EffectType_sont_nommables_et_les_73_morts_partis` ;
* `test_le_registre_EFFECT_CLASSES_resout_entierement_dans_le_mirror` ;
* `test_UtilityType_nomme_la_queue_que_le_RPC_peut_rendre` — dont le point d'insertion
  `Tile → AttackTile → Elevation` de la MAJ, exprimé **par membre** (`Tile + 1 == AttackTile`),
  jamais par ordinal en dur : doctrine #283/#272.

### Rouge vu avant vert (3 mutations, retirées)

| mutation | test qui mord | message |
|---|---|---|
| `Helspear_IgnoreArmor` retiré + `SpiderWeb = 13` réintroduit | bijection | `EffectType (…) : MANQUANTS=1 MORTS=1 RENUMEROTES=0 / manquants : [(1583, ['Helspear_IgnoreArmor'])] / morts : [(13, ['SpiderWeb'])]` |
| `1563` remis à `DA_Hero6_Passive_1` | bijection **+** test dédié | `renumerotes : [(1563, 'DA_Hero6_Passive_1', ['SpecialIssueCombiMelta_AdditionalHits'])]` puis `assert 'DA_Hero6_Passive_1' == 'SpecialIssue...dditionalHits'` |
| dette `(0,0,0)` re-déclarée sur `UtilityType` | zéro-dette | `dette(s) declaree(s) reintroduite(s) : [('UtilityType', (0, 0, 0), 'MUTATION ADVERSARIALE #318 -- a retirer')]` |

### Le réparateur, corrigé au passage

`regen_enum_mirrors.py` recollait les commentaires de fin de ligne **sans leur espacement**
(`X = 28   # …` → `X = 28# …`) : l'espacement n'était pas capturé par `RX_MEMBRE`. Un seul membre
des dix mirrors en portait un (`UtilityType.DislikeStartingTilesUtility`), donc le défaut ne s'est
vu qu'ici — mais une régénération qui **dégrade** le fichier qu'elle répare est une raison de ne
plus l'utiliser, et c'est la panne du réparateur qui a produit toute cette famille de dettes
(#275 §1). Corrigé + idempotence re-vérifiée : **0 changement sur les 8 mirrors sains**.

## 6. Porteurs des 20 membres ajoutés — la file de portage

Un effet n'est pas nommé par le gameconfig : c'est l'**ability** qui le pose qui l'est. Remontée
par racine du nom, puis ventilation par `kind`, puis gate `rl_duel build --list-pool` (rank 17,
**97 unités**).

| ids | ability | porteur(s) | confrontable ? |
|---|---|---|---|
| 1581, 1582 | `MyWillBeDoneOverlord` | `necroOverlord` (lineup) + 5 npc | **OUI, directement — dans le pool** |
| 1542 / 1543, 1544 | `MassDriverAccelerator`, `ModifiedExoarmour` | `votanChampion` (lineup) | OUI par injection — monté seul avec succès en #270 |
| 1558-1560 | `PropheticSentinel` | `thousSekhetar` (lineup) | OUI par injection — idem |
| 1578, 1580 / 1579 | `EmpyricAmbush`, `WhisperingWeb` | `eldarLhykhis` (lineup) | OUI par injection — idem |
| 1570 | `RedRampage` | `bloodTerminator` (lineup) + `bloodTerminator_LHE` (npc) | hors pool, injection non encore mesurée |
| 1571-1574, 1575, 1576 | `TitanhammerSquad`, `IconOfObstinacy` | `astarLysander` (lineup) | **NON — `initAndStart: system error`, backlog #270-d** |
| 1583 | `Helspear` | **`blackHaarken`** (lineup) par la RELIQUE `R_Crit_Helspear` + 5 npc en `relicAbilities` | **OUI — dans le pool** (relique non équipée par ce seed) |
| 123 | — | — | `Test_BuffAdjacentFriendly` : effet de **test** |

⚠ **La ligne 1583 disait « aucune unité — kit livré en avance » : c'était FAUX** (corrigé par
#323). Le zéro venait de `unit_map find --ability`, aveugle à la voie RELIQUE ; `blackHaarken`,
seul `allowedUnits` de `R_Crit_Helspear`, est **dans le pool**. Ce n'est donc pas un kit livré en
avance, c'est un montage à écrire (poser `BC.Units[].TertiaryAbility`) —
`docs/rl/case-323-unit-map-attribution-voies.md` §5.

Priorité identique à celle de #313 : **`MyWillBeDoneOverlord`** (seul porteur déjà dans le pool,
poids owner *et* non-owner re-synthétisés par `rl_duel build`), puis `PropheticSentinel` /
`EmpyricAmbush` par injection. `TitanhammerSquad` / `IconOfObstinacy` restent **bloqués derrière
#270-d** — tout port en serait invalidable.

Les 15 de `UtilityType` n'ont pas de porteur au sens hero/MoW/summon : ce sont des utilités d'IA,
leur « confrontabilité » est celle du RPC `dumpComposedUtility`, pas d'une unité.

## 7. Ce qui n'est PAS couvert

* **Aucune confrontation live** : la tâche est offline (mirrors + cliquet). Ce qui est prouvé, c'est
  que le port **nomme** ce que le jeu nomme — pas qu'une feuille ou un effet soit *porté*. Les 20
  effets et les 15 utilités restent non implémentés.
* **`scripts/sql/006` et `013`** portent toujours l'ancienne table (73 morts présents, 20 nouveaux
  absents) — #270-b, non touché.
* **Rouge PRÉ-EXISTANT, sans lien** : `test_enum_ordinal_ratchet_offline::test_aucun_ordinal_des_quatre_enums_en_dur_dans_scripts_python`
  échoue sur 3 littéraux `EventTriggerType = 9` (`test_cursed_plague_bell_attack_live.py:47`/`:104`,
  `probe_224_cursed_plague_bell_attack.py:151`). Déjà constaté rouge sur `origin/master` par #313
  (case-313 §8) ; ces fichiers ne sont pas dans le diff de #318, et c'est le territoire d'un autre
  agent (cliquet ORDINAL — celui de #318 est le cliquet de BIJECTION, ce sont deux cliquets
  distincts).
