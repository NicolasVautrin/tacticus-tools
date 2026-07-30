# case-313 — les mirrors `IntEnum` du MOTEUR n'étaient gardés par personne

**Question binaire, par mirror** : l'ensemble des membres d'une classe `IntEnum` de `engine/`
coïncide-t-il EXACTEMENT avec celui de `data/symbols/<CURRENT>/frida/enums.tsv`, **dans les deux
sens** ?

Build de référence : `rnca9r7q6c`. Tout ci-dessous est re-dérivable par
`python scripts/python/probe_313_enum_mirror_bijection.py [--verbose] [--porteurs]`.

## 1. Pourquoi personne ne le gardait — vérifié, pas supposé

Deux cliquets voisins existaient. Ni l'un ni l'autre ne couvrait le cas, et ce n'est pas un
oubli d'implémentation mais un **périmètre écrit noir sur blanc** :

| cliquet | ce qu'il garde | pourquoi il ne voyait pas |
|---|---|---|
| #283 `test_enum_ordinal_ratchet_offline` | 4 enums (`EventTriggerType`, `UtilityType`, `StepType`, `DisplaceDirection`) | `probe_283…step_mirror` teste `ref.get(membre) != valeur` sur les membres **présents**. Un membre que le port n'a pas ne peut pas diverger : il est invisible. Aucun `*AbilityType` à son registre. |
| #275 `test_enum_maps_ratchet_offline` | les 6 blocs de `enum_maps.py` | fait bien les trois sens, mais son étape 4 range explicitement `engine/entities/*_type.py` en « informatif, **hors périmètre** ». |

Conséquence mesurée : `enum_maps.PASSIVE_ABILITY_TYPE` était **à jour** (476 membres, régénéré
par #275) pendant que le mirror `engine/entities/triggered_ability_type.py` — celui que le code
**exécutable** lit — en portait encore **575**. Les deux tables du même enum dans le même dépôt,
l'une gardée et juste, l'autre non gardée et fausse.

## 2. Le diff, dans les deux sens

| mirror | port | jeu | MANQUANTS | MORTS | RENUMÉROTÉS | verdict |
|---|---:|---:|---:|---:|---:|---|
| `TriggeredAbilityType` | 575 → **476** | 476 | **8** | **107** | 0 | corrigé, SOUS GARDE |
| `ActiveAbilityType` | 260 | 260 | 0 | 0 | 0 | déjà sain, SOUS GARDE |
| `DamageProfileType` / `UnitTrait` / `UnitFaction` / `DamageTrait` / `EventTriggerType` | — | — | 0 | 0 | 0 | déjà sains, SOUS GARDE |
| `StatType` | 27 | 27 | 0 | 0 | 0 | SOUS GARDE, **valeurs seules** |
| `EffectType` | 682 → **629** | 629 | 20 | 73 | **2** | dette déclarée `(20, 73, 2)` → **résorbée par #318, SOUS GARDE** |
| `UtilityType` | 68 → **83** | 83 | 15 | 0 | 0 | dette déclarée `(15, 0, 0)` → **résorbée par #318, SOUS GARDE** |

Les six mirrors sains le sont **par chance** — le jeu n'y a rien touché à cette MAJ. Rien dans le
dépôt ne le garantissait avant ce cas ; c'est maintenant un cliquet.

`StatType` est gardé en mode **valeurs seules** parce que le port reconventionne délibérément ses
noms (`CRIT_CHANCE` pour `CriticalChance`, UPPER_CASE partout, convention déclarée dans sa
docstring). En mode strict il rendrait **26 faux « renumérotés » sur 27 membres** et noierait tout
signal réel.

## 3. Le sens MANQUANT n'est pas inerte — c'est un dictionnaire, pas une table

`triggered_ability_ids()` fait `TriggeredAbilityType.__members__.get(nom_gameconfig)` puis
`if m is not None`. Un membre absent n'y produit **ni erreur ni trace** : il **retire** un passif
du kit porté. C'est le symptôme qu'avait déjà rencontré #304 sur `ModifiedExoarmour` (1529) —
`triggered_ability_ids('votanChampion')` rendait `[]`, et le dispatcher `TriggeredAbilitiesUtility`
restait muet quel que soit le playbook porté.

Effet **mesuré** du fix (mirror de `de7879b2` vs corrigé, même conversion rejouée) :

* passifs distincts nommés par le gameconfig : **211** — résolus **206 → 210** ;
* **9 unités** voient leur kit passif porté changer, **aucune n'en perd** :
  `astarLysander` +1552, `eldarLhykhis` +1554, `thousSekhetar` +1543, et `necroOverlord`
  +1556 (+ ses 5 déclinaisons npc/boss).
* le seul non résolu restant, **`ShroudPsalm`**, n'est pas un trou : ce nom n'existe pas dans
  `TriggeredAbilityType` — il vit dans `ActiveAbilityType` (1181) et `EffectType` (1366). C'est le
  piège #157/#158 dans sa variante « même NOM, enums différents ».

## 4. Retirer 107 membres morts sans casser le port — le piège #270

#270 avait établi qu'une régénération naïve casse le port en supprimant un nom encore cité. La
suppression n'a donc été faite qu'après **trois** mesures indépendantes, toutes à zéro :

1. **références qualifiées** (AST, tout le Python suivi) : **1438** références `<Classe>.<membre>`,
   **0 introuvable**, **0 morte** ;
2. **gameconfig** : **0** membre mort encore nommé par une `passiveAbilities` ;
3. **conversions par valeur** : aucune occurrence de `TriggeredAbilityType(<int>)` dans le dépôt.

Les 6 noms morts massivement cités dans le dépôt (`Guard` ×355, `Camouflage` ×170, `SpiderWeb`
×19, `Dragon`, `Drunk`, `RoyalGuard`) sont des **homonymes** : `Camouflage` est `UnitTrait` 1037,
`SpiderWeb` est `EffectType` 13, et `Guard` n'apparaît que dans « Death Guard » / « Tyrant Guard »
/ `GuardianOrganismPlaybook`. Aucune ne visait `TriggeredAbilityType`.

## 5. Le cliquet, et pourquoi il a cinq parties

`scripts/python/tests/test_enum_mirror_ratchet_offline.py` — offline pur, 13 tests.

1. **bijection deux sens** sur les mirrors sous garde ;
2. **registre exhaustif** : toute classe `IntEnum`/`IntFlag` de `engine/` est soit appariée à une
   clé `enums.tsv`, soit justifiée `HORS_MIRROR`. *C'est la partie anti-re-creusement* : sans
   elle, le cliquet ne garde que ce qu'on a pensé à y mettre — et c'est exactement ainsi que
   `TriggeredAbilityType` a dérivé. Personne n'avait **décidé** de ne pas le garder ; il n'était
   dans aucune liste, et une absence ne se remarque pas ;
3. **dettes au compte exact**, contrôlées **dans les deux sens** : le test rougit si la dette
   s'aggrave *et* si elle se résorbe — la réponse étant alors de passer le mirror sous garde, pas
   de rafraîchir le nombre. Un chiffre qu'on rafraîchit n'est pas un cliquet, c'est un journal ;
4. **le détecteur mord** : les trois formes de dérive réellement observées, plus les deux
   anti-faux-positifs (alias de valeur `9999 = {STRIPPED, testAssetBundles}` ; mirror qui
   reconventionne ses noms) ;
5. **références qualifiées** : c'est ce qui autorise la suppression d'un membre mort.

### Le réparateur, sans lequel le cliquet se retourne contre nous

`scripts/python/regen_enum_mirrors.py` réécrit les membres depuis `enums.tsv` en **préservant les
commentaires** (bloc précédent + fin de ligne) par nom de membre, et **signale** tout commentaire
rattaché à un membre supprimé au lieu de le jeter. #275 avait établi la cause racine de la dérive
d'`enum_maps` : le réparateur était en panne. Un cliquet qui rougit sans offrir de réparation
pousse à la correction à la main — 476 lignes retranscrites, c'est-à-dire exactement la
transcription approximative qu'on cherche à éliminer.

Idempotence vérifiée : `regen_enum_mirrors.py` (sans `--ecrire`) rend **0 changement** sur les six
mirrors déjà sains.

## 6. Rouge vu avant vert — les quatre mutations

| mutation | test qui tombe | message |
|---|---|---|
| retirer `MyWillBeDoneOverlord = 1556` | bijection + les-huit-membres | `MANQUANTS=1 MORTS=0 … manquants : [(1556, ['MyWillBeDoneOverlord'])]` |
| réintroduire `RaiseSkeletons = 1` | bijection | `MANQUANTS=0 MORTS=1 … morts : [(1, ['RaiseSkeletons'])]` |
| ajouter un `IntEnum` non enregistré sous `engine/` | registre exhaustif | `classe(s) IntEnum sous engine/ ni appariee(s) ni justifiee(s) : SpawnSource` |
| déclarer la dette `EffectType` à `(19, 73, 2)` | dettes | `mesure (20, 73, 2), dette declaree (19, 73, 2)` |

⚠ La quatrième mutation n'est plus reproductible **telle quelle** : #318 a résorbé les deux
dettes, et le registre n'en déclare plus aucune. Le mécanisme « dette au compte exact » reste en
place pour une dette future, et un test de #318 (`test_aucune_dette_declaree_ne_subsiste`) garde
désormais le zéro — c'est LUI qui mord si on re-déclare une dette.

## 7. File de portage — les 8 membres ajoutés, par confrontabilité

Gate : `rl_duel build --list-pool` (rank 17 : 97 unités + 8 MoW). `kind` du gameconfig **ventile**,
il ne tranche pas.

| id | membre | porteur(s) | confrontable |
|---|---|---|---|
| 1556 | `MyWillBeDoneOverlord` | `necroOverlord` (+5 npc/boss) | **OUI — dans le pool** |
| 1543 | `PropheticSentinel` | `thousSekhetar` (lineup) | OUI par **injection catalogue** (case-92 §6) |
| 1552 | `IconOfObstinacy` | `astarLysander` (lineup) | OUI par **injection catalogue** |
| 1554 | `WhisperingWeb` | `eldarLhykhis` (lineup) | OUI par **injection catalogue** |
| 1546 | `HeavyWarpFlamer_AttackTrackingAbility` | aucun (absent même du catalogue `abilities`) | sous-ability interne — via son ability parente |
| 1555 | `EmpyricAmbush_Reset` | aucun (idem) | sous-ability interne — via `EmpyricAmbush` |
| 1557 | `PhasalSubjugator` | **`necroOverlord`** (lineup) par la RELIQUE `R_Booster_Crit_PhasalSubjugator` + 5 npc en `relicAbilities` | **OUI — dans le pool** (relique non équipée par ce seed) |
| 1558 | `Helspear` | **`blackHaarken`** (lineup) par la RELIQUE `R_Crit_Helspear` + 5 npc en `relicAbilities` | **OUI — dans le pool** (relique non équipée par ce seed) |

⚠ **Les deux dernières lignes disaient « aucune unité » — c'était FAUX** (corrigé par #323). Le
zéro venait de `unit_map find --ability`, qui ne lisait alors ni `relicAbilities` ni
`items[*].abilityId + allowedUnits` : **42** abilities du build lui étaient invisibles, dont ces
deux. Ventilation à trois états pour une ability de relique — `équipée au seed` / `porteur au pool,
relique non équipée` / `porteur hors pool` : `docs/rl/case-323-unit-map-attribution-voies.md` §5.

Ces membres **ne sont pas décoratifs** : `rl_duel build` re-synthétise depuis le gameconfig des
clés de poids qui leur correspondent, neuves dans ce build —
`Default/TriggeredAbilities/PropheticSentinel_LikesAdjacentPsykerFriends`,
`IconOfObstinacy_LikesAdjacentTerminatorFriends`,
`MyWillBeDoneOverlord_LikesAdjacentMechanicalFriends`, `EmpyricAmbush_LikesMeleeKills`, plus les
pendants `TriggeredAbilitiesNonOwner`. Le playbook porté qui les lira les trouvera désormais.

Priorité suggérée : **1556 `MyWillBeDoneOverlord`** (seul porteur déjà dans le pool, 6 unités,
poids owner *et* non-owner), puis 1552 / 1543 / 1554 par injection.

## 8. Résidus — mesurés, hors périmètre de ce cas

* **`EffectType`** : `(20 manquants, 73 morts, 2 renumérotés)`. Les 2 renumérotés sont la forme la
  plus coûteuse — `1563` rend `DA_Hero6_Passive_1` là où le jeu dit
  `SpecialIssueCombiMelta_AdditionalHits` (et `1564` / `…_ExtraDmg`). Ce sont les **mêmes
  placeholders** que ceux corrigés dans `TriggeredAbilityType` par case-219 : ils ont survécu dans
  le mirror voisin. Ils **résolvent** et pointent ailleurs : aucune erreur, aucune trace.
  → **RÉSORBÉ par #318** (`case-318-effect-utility-mirror-bijection.md`) : mirror à **629**
  membres, `(0, 0, 0)`, SOUS GARDE. La correction n'était pas un renommage — `DA_Hero6` n'existe
  dans **aucun** des deux `enums.tsv` versionnés, et **aucun** site de code ne citait l'ancien nom.
* **`UtilityType`** : 15 manquants (`ActiveAbilities`, `PreferNonBoss`, `PreferFreshlySpawned`,
  `MinPossibleNormalAttackTarget`, `UnitWithShortestPathToEnemy`, `Remaining`, `PreferAbilities`,
  `PreferSummons`, `LastAbilities`, `UnitOrder`, `Random`, `AdjacentHarmonizedFriend`, …) — les
  utilités ajoutées par la MAJ, qu'aucune feuille portée ne lit encore. À noter : #283 garde ce
  mirror et ne voyait **aucun** de ces 15, faute de tester le sens « manquant ».
  → **RÉSORBÉ par #318** : mirror à **83** membres, `(0, 0, 0)`, SOUS GARDE. Le registre de la
  sonde est désormais à **10 mirrors sous garde, 0 dette déclarée**, et ce zéro est lui-même gardé.
* **Rouge PRÉ-EXISTANT sur `origin/master` (`de7879b2`), sans lien avec ce cas** :
  `test_enum_ordinal_ratchet_offline::test_aucun_ordinal_des_quatre_enums_en_dur_dans_scripts_python`
  échoue sur 3 littéraux `EventTriggerType = 9` (`test_cursed_plague_bell_attack_live.py:47` et
  `:104`, `probe_224_cursed_plague_bell_attack.py:151`), et `probe_283` rend `VERDICT: FAIL (3)`
  sur des citations de prose périmées (`test_tainted_narthecium_revive_live.py:274`,
  `test_tau_lot1_residues_live.py:390`). Les fichiers concernés sont identiques à `de7879b2`
  (`git diff HEAD --stat` vide) : ce n'est pas une régression de ce cas.
