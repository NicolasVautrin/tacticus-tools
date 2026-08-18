# #10027 — six fichiers de cliquets rouges sur `master` : trois verdicts, six causes

Tranche du 2026-08-18. Six fichiers de tests-cliquets rendus rouges sur un arbre propre. La
consigne était de trancher, pour chacun, entre **le cliquet a RAISON**, **la PRÉMISSE a EXPIRÉ**
et **l'INVENTAIRE est FAUX** — et de ne jamais rendre un rouge vert en retirant le cran.

**Verdicts** — les trois catégories sont représentées, et deux fichiers en portent deux à la fois :

| fichier | verdict | ce qui l'établit |
|---|---|---|
| `test_928_legacy_of_combat_offline.py` | RAISON **+** INVENTAIRE FAUX | un consommateur neuf réel ; et 11 classes sur 328 hors du balayage |
| `test_933_premisse_regime_offline.py` | INVENTAIRE FAUX | 4/4 faux positifs, dont **3 que le remède prescrit CASSERAIT** |
| `test_952r1_geometrie_non_consommee_offline.py` | PRÉMISSE EXPIRÉE | égalité figée contre une entrée légitime, entrée avec son lecteur |
| `test_nc_priority_tiers_offline.py` | PRÉMISSE EXPIRÉE (montage) | un champ de contexte ajouté par #979, jamais répercuté au stub |
| `test_366_r1_bcpatch_port_blindspot_offline.py` | INVENTAIRE FAUX | le fichier avait **annoncé** la cause et sa croissance |
| `test_431_build_pin_offline.py` | RAISON | 4 résolutions d'artefact par hash en dur, **3 déjà périmées** |

---

## 1. `#928` — le vecteur `On(0xb)` : un consommateur réel, et un balayage qui ne visitait pas ce
qu'il nommait

**Le rouge** : `BattleFocusEffectTrigger` écoute `EventTriggerType.UnitAbility` sans être attesté.

**Il a RAISON.** Relu sur le build **courant** :
`IdunBattle.Entities.Effects.Loki.BattleFocusEffect$$CreateTargetTrigger` appelle
`IdunBattleLogic.Entities.DSLTriggers$$On(<DSLSelectors+0x88>, 0xb, ownerNeedsToBeAlive: 1)` en
premier conjoint, puis `AbilityHasAttackType(CurrentAbility@<+0x88>, 0)`,
`get_OwnerIsTarget | get_OwnerIsCaster`, `NOT IsMoving(Owner@<+0x30>)`, `CanMove(Owner@<+0x30>)`.
L'écoute est donc bien celle du vecteur émis par #928 (port #1080). Attesté avec ce verbatim.

**Et l'INVENTAIRE était FAUX, sur deux axes** — le balayage listait ses conteneurs à la main :

* `GLOBAL_TRIGGERS` était **NOMMÉ mais jamais visité** : c'est une `list`, et le filtre exigeait un
  `dict` (`if not isinstance(d, dict): continue`). C'est le pire des deux cas — le lecteur croit la
  couverture acquise ;
* `POWER_UP_SPAWN_ABILITIES` n'était pas même nommé.

Mesure : **11 classes à `event_id` invisibles sur 328**. Aucune ne portait `0xb` — le trou n'a rien
masqué, mais rien ne l'en empêchait. Le balayage **dérive** désormais les conteneurs du module et
descend quelle que soit leur forme (dict / list / imbrication). Deux planchers assertionnent son
non-vide (≥ 300 classes visitées ; les 9 conteneurs porteurs toujours présents) — c'est ce second
cran qui rougirait si quelqu'un ré-introduisait un filtre de forme.

## 2. `#933` — 4 faux positifs sur 4, et le remède prescrit en casserait 3

Les quatre accusés (`test_1001_votann_relics_live`, `test_1009_reliques_dark_angels_live`,
`test_1013_paragon_spear_live`, `test_martial_apotheosis_live`) ont été lus un par un :

* **`1013`** neutralise déjà `CritChance` sur son porteur (`--unit-stat <CARRIER>:CritChance=<0|100>`) ;
* **`1001`** ne mesure **aucun jet de critique** — il compare des **DELTAS** de stat, invariants par
  translation de la base BiS —, et son probe de montage écrit `--unit-stat votanUthar:CritChance=…`
  en le documentant ;
* **`1009`** ne lit pas la stat `BlockChance` du tout : la sous-chaîne vient de `BlockChanceInfo` et
  de la variable de gameconfig `blockChance`, dont le fichier dit lui-même qu'elle est « CONSTANTE
  (10) sur les dix paliers » ;
* **`martial_apotheosis`** **EXERCE** le régime crit (bande par régime `[bmin+cd, bmax+cd]`) et porte
  `assert cd > 0` en garde de non-dégénérescence — **le remède prescrit (`CritDamage=0`) le rendrait
  ROUGE par cette assertion même**.

**Cause structurelle, mesurée** : le recenseur ne cherchait le montage que dans le **fichier de
test**, alors que **9 suspects sur 39** portent leur `--unit-stat`/`--crit`/`--block-*` dans un
module **IMPORTÉ**. `_classe_fichier` avait déjà rencontré ce gisement sur l'axe LIVE/OFFLINE et
l'avait fermé là ; il restait grand ouvert sur l'axe NEUTRALISATION.

`_montage_importe` suit ces imports (**un seul niveau**, provenance IMPRIMÉE dans
`neutralise_via`). Effet : **39 → 30 suspects**.

**Ce que la réparation fait de la liste** — et c'est un renforcement, pas un allègement :

* les **8 attestés** ainsi éclaircis **SORTENT** d'`_ATTESTES` et entrent dans le tuple `repares` :
  ils passent du régime « dette tolérée » au régime « si le levier disparaît, le cliquet ROUGIT » ;
* les **3 faux positifs restants** entrent dans `_FAUX_POSITIFS_MESURES`, liste **distincte**
  d'`_ATTESTES` (qui dit « pas tranché ») : celle-ci dit « tranché, le recenseur a tort », avec la
  mesure de chacun ;
* **deux crans neufs** : les listes sont **DISJOINTES** (une régénération mécanique par `--attester`
  remettrait les faux positifs dans `_ATTESTES`, où ils perdraient leur mesure), et **toute entrée
  de liste est ENCORE ACCUSÉE** par le recenseur — une entrée qui ne l'est plus ne protège plus,
  elle **masque**.

`1013` sort par la mesure. `1001`, `1009`, `martial_apotheosis` sont les trois faux positifs
qualifiés. Résidu **`#10027-r2`** : la détection « fichier lecteur » par sous-chaîne (le remède
évident — une frontière de mot — est **mesuré et écarté** : il retire le statut de lecteur à
**7 fichiers**, donc il rétrécit la population au lieu d'affiner le critère).

**Réfuté en chemin** : « neutraliser la CHANCE rend le DÉGÂT inerte, donc une stat de la paire
suffit ». Faux — `ForceCrit` (trait `Charge`, cf. `test_case231_charge_forcecrit_live.py`) fait
critter à `CritChance = 0`. L'exigence de paire est juste en général.

## 3. `#952-r1` — une égalité figée contre un registre qui a le droit de grandir

Le cliquet écrivait `set(EFFECT_TARGET_SELECTORS) == {1026, 1191, 1052}`. `1500
WayOfTheShortBlade_AdditionalAttackMarker` y est entré avec **#1019-r2**, et **avec son lecteur** :
`engine/runner/operations/triggers/loki/way_of_the_short_blade.py` appelle
`_is_effect_target(state, ev.actor_id, ADDITIONAL_ATTACK_MARKER) is True` — le gate
`IsEffectTarget(Caster@<DSLSelectors+0x48>, 0x5dc)` de
`...Triggered.Loki.WayOfTheShortBlade_AttackAbility$$CreateTrigger`. **PRÉMISSE EXPIRÉE.**

Les deux propositions que l'égalité voulait garder sont désormais gardées **séparément** :

1. `1190 HuntersBeyondDeath` reste **DEHORS** (invariant inchangé), **plus** un cran neuf : il doit
   rester absent de la dérivation des lecteurs — sinon le refus de #952-r1 ne tient plus ;
2. **toute entrée a un LECTEUR**, **dérivé** d'`engine/**` au lieu d'être recopié.

**Le point dur de la dérivation, et il a mordu.** Un premier point fixe sur « la fonction appelle
quelque chose qui atteint le foyer » a rendu **361 relais** — `execute`, `apply`, `matches`,
`generate`, `_score` : la quasi-totalité du moteur. Le cran devenait **VACANT** (on voyait sortir
des « lecteurs » pour les effets `0`, `1`, `2`, `5`…). Le critère qui tient est **« TRANSMET »** :
une fonction n'est un relais que si elle passe **l'un de ses propres PARAMÈTRES** en position
effect_type. Résultat : **5 relais**, 8 effets couverts, les 4 entrées du registre toutes couvertes.
Contre-épreuve exécutable : une entrée **FICTIVE** doit sortir orpheline (elle sort).

Sous-cran : `bool` est un `int` en Python — sans le refuser, le `unknown_is_target=True` de
`IsEffectTarget(Owner(), SYNAPSE_EFFECT, unknown_is_target=True)` prouvait un lecteur pour
« l'effet 1 ».

## 4. `test_nc_priority_tiers_offline` — le montage, pas le port

`AttributeError: 'types.SimpleNamespace' object has no attribute 'machine_of_war_position'`.
`NonComparableGenerator.generate` lit `ctx.machine_of_war_position` en accès **direct** depuis #979
(le prédicat `IsPositionMachineForCurrentPlayer(2)` de `DevastatingRefrainAbility$$GetShape`), là où
ses voisins immédiats passent par `getattr(ctx, …, None)`. Le champ **est** porté par
`AiDecisionContext` : la production ne casse jamais. C'est le `SimpleNamespace` écrit à la main dans
le test qui a péri — **un changement de harnais périme les prémisses d'un test**.

Le stub replie désormais à `None` sur ce qu'il ne porte pas — exactement le contrat que `NCContext`
déclare pour ce champ (`machine_of_war_position: object = None`, tri-état « non mesuré »). Ce n'est
pas un affaiblissement : ce que le fichier garde reste asserté explicitement (un générateur devenu
muet ferait rougir `action["ability"] == …`). Un cran garde le contrat du repli, dunder compris.

## 5. `#366-r1` — l'inventaire faux que le fichier avait ANNONCÉ

Cinq fichiers arrivés en « trou de couverture » (ni ability ni variable déterminables). Le fichier
nommait déjà quatre trous, et l'un d'eux écrivait :

> CE N'EST PAS UN SITE INTRINSÈQUEMENT INDÉTERMINABLE — c'est une lacune de l'outil, et elle va
> CROÎTRE : écrire le membre d'enum plutôt que le littéral est ce que CLAUDE.md prescrit, donc ce
> patron se répandra. Résidu #484-r1.

Les cinq trous neufs **sont** cette croissance. Le résolveur apprend les deux formes :

* **`_membre_d_enum`** — `<Enum>.<membre>.name`, y compris via un nom lié
  (`CONST_NR_OF_SUMMONS = AbilityConstantType.nrOfSummons`), et `Enum(int(Enum.M)).name` (identité
  d'`Enum`). Résolu **syntaxiquement** : aucun import, aucune exécution ;
* **`_alias_de_modules`** — la constante d'un module **IMPORTÉ en FORME B** (`from pkg import mod as
  M` puis `M.CONST`), imports relatifs et `engine.*`. C'est l'écriture que la doctrine **prescrit**,
  et elle créait des trous.

**Effet mesuré : 9 fichiers aveugles → 3.** Ferme les 5 trous neufs sauf `power_up.py` (cause
différente — résidu **`#10027-r1`**), et rend **mortes** deux entrées déjà nommées (`predict.py`,
`genestealer.py`, #935). `red` / `orphan_exceptions` / `unresolved` restent vides ; la MORSURE
(6 formes d'écriture de patch) passe toujours ; la seconde source (grep littéral) ne perd rien.

**Cran neuf** : `test_aucun_trou_declare_orphelin` — un trou nommé qui n'est plus aveugle ROUGIT.
Symétrique de `test_aucune_exception_orpheline`. Sans lui, les deux entrées mortes créées par cette
tranche même seraient restées en place, et la **réapparition** du trou serait passée inaperçue.

## 6. `#431` — le méta-cliquet avait raison, et trois de ses quatre accusés étaient déjà périmés

`probe_431_build_literals` rendait `rc=1` sur l'arbre intact : **4 résolutions d'artefact par hash
de build en dur**. Un chemin en dur court-circuite `data/symbols/CURRENT` **et** le binaire
installé — aucune garde de synchronisation ne peut le voir.

| site | hash | réparation |
|---|---|---|
| `probe_988_ancres_utilite_playbook.py` | `rnca9r7q6c` **périmé** | `build_pin.versioned_build()` / `functions_tsv()`, tri-état conservé |
| `tests/engine/test_963r4_areenemies_null_operand_offline.py` | `rnca9r7q6c` **périmé** | `build_pin.versioned_build()` + `build_dir()` |
| `probe_10018_effectsdatabase_registry.py` | `t6dpr4k06g` | `require_pinned` + `game_dll()` / `functions_tsv()` / `build_dir()` |
| `probe_547_ledger_sans_verdict_non_vert.py` | `rnca9r7q6c` **périmé** | citation en prose → chemin générique `data/symbols/<build>/…` |

Les deux premiers ne sont pas des détails de forme : `probe_988` **confrontait** l'adresse d'un
capteur live à une table qui ne décrit plus le binaire chargé (son accord comme son désaccord ne
voulaient plus rien dire), et `test_963r4` confrontait les slots attendus d'`ITargetsSelector` à la
table d'un **autre build** — l'inverse exact de ce que sa docstring promet. Après réparation,
`probe_988` résout **167** ancres sur le build courant.

**Le piège de forme, mesuré** : `probe_431` reconnaît le foyer par un critère **LOCAL ET EXACT** —
l'argument doit être un **littéral du `Call`** —, par refus assumé de lire un contexte (son en-tête
mesure les deux critères contextuels qui l'ont déjà rendu faux, dans les deux sens). Une constante
de module passée à `require_pinned` deux lignes plus bas reste donc classée RESOLUTION : c'est le
dernier des quatre rouges, et il n'est tombé qu'à l'**inlining** du littéral dans l'appel.

---

## Ce que la tranche NE couvre PAS

* **`#10027-r1`** — `power_up._const`, relais dont les deux axes sont des paramètres, reste un trou
  nommé de `#366-r1`. Perte mesurée nulle aujourd'hui (aucune intersection entre les constantes de
  power-up et les 3 abilities / 5 variables que le dépôt patche).
* **`#10027-r2`** — `probe_933._lit_stats` classe « lecteur » par sous-chaîne. Le remède évident est
  mesuré et écarté (il retire le statut de lecteur à 7 fichiers).
* Ce qui reste de **`#484-r1`** : `_relay_args` de `#366-r1` transporte les nœuds AST des appelants
  mais les résout contre l'env du **définisseur** — `abilities/base.py` reste aveugle pour cette
  troisième raison.
* Les **trois faux positifs qualifiés de `#933`** sont inventoriés, pas supprimés : leur cause
  (sous-chaîne, exigence de paire, test qui exerce le régime) demande un critère que la tranche n'a
  pas écrit.
* **Aucun re-jeu LIVE** : les six items sont offline, et les quatre fichiers `_live.py` cités
  (`1001`, `1009`, `1013`, `martial_apotheosis`) n'ont **pas** été rejoués — la tranche ne touche
  ni leur montage ni leur code.
