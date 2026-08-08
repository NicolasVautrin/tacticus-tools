# #547 — un rouge offline MESURÉ, ÉCRIT, COMMITÉ et LIVRÉ

*2026-08-08. Point de départ : 23 tests offline rouges sur `master` depuis au moins deux merges,
trouvés par des agents, pas par nos cliquets.*

## 1. Les rouges, et leurs trois causes distinctes

`7308543d` (avant les deux derniers merges), arbre propre :
`23 failed, 51 passed` sur trois fichiers. Trois PR différentes, trois mécanismes.

| # | fichier | cause | commit fautif |
| --- | --- | --- | --- |
| 21 | `test_433_r4_r2_r1_r2_r2_r1_r1_r1_r4_caster_reason_offline.py` | le fixture patchait `acg.targeting_options_for` — liaison **disparue** avec le passage en **forme B** | `a30b189b` (#827) |
| 1 | `test_337_dsl_triggers_attestation_offline.py` | `IsKilledThisTurn` entrée au port **sans son attestation** | `18edd540` (#832) |
| 1 | `test_433r4r1r4r2r1r1_derivation_morte_offline.py` | **faux positif** du cliquet sur un **déballage** | `59ec2e60` (#824) |

**La cause A est la troisième bascule de forme que ce fixture traverse**, et chacune l'a cassé
dans un sens différent : **C** (import dans le corps de la fonction — patcher `TGT` mordait) →
**A** (`492c722f`, le nom copié dans le namespace d'`acg` — patcher `TGT` ne mordait plus, #484)
→ **B** (#827, `import … as TGT` — patcher `TGT` mord de nouveau, et `setattr(acg, …)` **lève**).
La garde d'inertie posée par #484 visait un *binding nommé* : elle ne pouvait pas survivre à la
bascule suivante. Elle est réécrite en **comportement** — `invalid_caster_reason` rend `None`
quand le masque n'a pas été lu, un entier quand il l'a été — donc elle survit à la prochaine,
quel qu'en soit le sens. **5 mutants posés, 5 détectés**, dont le retour en forme A : il fait
rougir les 21 tests *par la garde*, au lieu de les rendre silencieusement vacueux.

**La cause C n'est pas une régression du port** : `best, _came = _dijkstra_by_pos(origin,
neigh_by_pos, …)` **consomme** `best`, donc le canal de voisinage a bien mordu. Le critère de
l'étape 3 se lit désormais au niveau du **statement** : la valeur d'une affectation est consommée
dès qu'**une** de ses cibles teintées est relue. Un déballage **intégralement** jeté reste coté
sur chacune de ses cibles (test de contre-épreuve).

## 2. Le rouge `probe_120bis` : réel, et il en cachait deux autres

Confirmé par mesure (pas seulement rapporté), puis **bisect binaire** sur `origin/master`, arbre
témoin complet par `git archive`. **Trois étapes, trois coupables, aucune régression.**

* **[5] — `8abc8415` (#287-r14).** L'étape lisait l'absence de re-résolution par le proxy
  `h.last["target"] == creed`. Depuis que
  `IdunBattle.Core.Services.TargetingQuery$$GetActualTarget` est porté, la cible **finale** d'une
  ability SELF-CAST est le **caster** : tout le corps du natif est sous la garde
  `if (options.<isSelfCasting @+0x00> == 0)`, et `1000 GauntletsOfUltramar` pose ce byte à 1
  (`TargetingOptions$$SelfCastIfEnemyInCustomRangeOptions`). **Le dégât est identique de part et
  d'autre du commit** (`hp creed 400000 -> 395355`) — c'est le proxy qui est faux, pas le port.
* **[8] — `027cb485` (#836)**, qui porte `SwornProtectorAbility$$GetSpawnTile` avec son bucket
  d'utilité. Le montage ramenait le caster au contact par `(cp.col, cp.row - 1)` **sans regarder
  qui l'occupe** : la nouvelle géométrie laisse Creed en (2,3) et **Kell en (2,2)** — exactement
  la case calculée. Le caster était **téléporté sur Kell**, et le 2ᵉ coup ne frappait plus
  personne (`kell 4119 -> 4119`).
* **[9] — même cause, masquée derrière [8].** Les deux régimes ne se choisissent plus par le
  **côté** d'abord (l'ancien `First(…)` dépendait de l'ordre de `board.neighbours`) mais par la
  **distance** : re-dérivé par balayage des 8 tuiles de caster, Kell prend **toujours** (2,2).
  `FOE_POS_ADJACENT = (3,3)` rétablit le régime relais.

⚠ **Le test qui garde ce probe vit dans un fichier `*_live.py`** — `probe_457` exclut le live
**par choix**. Un test purement offline hébergé là est donc invisible **des deux** gardes.

## 3. La cause racine du silence — et ce n'est pas « personne ne joue »

Trois hypothèses, mesurées dans l'ordre.

**(a) La sélection `--since` ratait-elle ces fichiers ?** *Non — réfutée.* Arbre témoin à chaque
commit fautif, `probe_457 --list --since <parent>` : les **trois** fichiers sont dans la
sélection (226/254, 257/257, 223/254). Le `DECLENCHEUR` n'est pas en cause.

**(b) Le geste prescrit avant PR voit-il un rouge existant ?** *Non.* Sur `027cb485` — l'arbre qui
porte les 23 rouges — `probe_457 --measure-missing` rend **`rc = 0` en 2,8 s** et affiche
« les 261 fichier(s) du périmètre ont déjà un poids ET une entrée d'empreinte, **rien à
mesurer** ». C'est un mode de **maintenance des poids**, et il est prescrit à la place d'un mode
de **vérification**. Contre-épreuve exercée : un `assert False` injecté dans un fichier de test
offline existant, commité dans un worktree témoin — `--measure-missing` reste **vert**, quand
`--since HEAD~1` sélectionne 16 fichiers dont le muté et rend `rc = 1`.

**(c) Et la mesure, alors ? Elle avait été faite.** C'est le vrai résultat.
`scripts/ratchets-457-vert-offline.json`, **versionné**, portait **8 entrées `ROUGE`** — toutes
horodatées du 2026-08-08 02:13, toutes écrites par le commit `bfa97ce8` d'un worktree d'agent,
arrivées sur `master` par le squash-merge `785855e2` (PR #835). Les fichiers nommés étaient
**exacts**. Deux d'entre eux étaient encore rouges 24 h plus tard.

> **La mesure existait, elle était juste, elle était versionnée — et rien ne la lisait.**
> `probe_457` **écrit** ce ledger et le consomme pour **sélectionner** ; jamais pour **juger**.

C'est ce qui distingue ce gisement de ses voisins : `#455` garde un fichier intégralement skippé,
`#455-r3` un fichier dont les tests ont disparu, `#486-r15` un déclencheur trop étroit — les trois
gardent une passe **qui a eu lieu**. Ici la passe a eu lieu, a rendu le bon verdict, l'a inscrit,
et personne n'a regardé.

## 4. Le cliquet

`probe_547_ledger_sans_verdict_non_vert.py` — **le ledger versionné du vert offline ne porte que
des `VERT`**.

* **Polarité : liste blanche d'UN seul élément, et elle est dérivée.** Le critère n'est pas « pas
  de `ROUGE` » mais « rien d'autre que `VERT` », `VERT` étant **lu** dans le foyer
  (`ledger_vert_offline.VERT`). `SETUP` (panne de montage) et `VIDE` (le garde `#455`) rougissent
  donc aussi, et un verdict **neuf** introduit demain rougira sans qu'on ait rien à ajouter.
* **Le verdict est RE-DÉRIVÉ du bilan ventilé**, jamais lu sur l'étiquette : une entrée qui
  s'étiquette `VERT` avec `failed: 3` serait sinon acceptée sur sa propre parole.
* **Deux crans sur la liste `NON_VERTS_DECLARES`**, et le second est ce qui l'empêche de pourrir :
  un non-VERT **hors liste** rougit ; une déclaration **redevenue verte** rougit **aussi** et doit
  sortir. Chaque ligne porte le **numéro du résidu** qui la ferme — pas de numéro, pas de ligne.
* **Une panne d'outil rend `EX_NON_MESURE`**, jamais un rouge de gisement (#471).
* **Contre-épreuve intégrée** (idiome #421) : **12 mutants, 12 conformes**, dans les deux
  polarités. Garde : `test_547_ledger_sans_verdict_non_vert_offline.py`, **23 tests, 1,5 s**.

**Ce qu'il IMPRIME sans rougir** — parce qu'un vert muet se lirait « tout l'offline est vert » :
les fichiers du périmètre offline **sans aucune entrée** (jamais joués), les attestations
**périmées** (blob du test changé), et le compte des `*_live.py` hors périmètre.

## 5. Ce que le cliquet a trouvé à son PREMIER passage — quatre rouges de plus

Le geste de ré-attestation (`probe_457 --depuis-ledger`, **269 fichiers / 3 833 tests / 32 min**)
a rendu **6** entrées non-VERT, pas 1. Chacune a été rejouée dans un worktree **témoin** à
`origin/master` **pur** (`4c3601ac`) : **quatre y rendent `rc = 1` aussi**, donc elles
**préexistent** et ne sont pas le fait de cette tranche.

| fichier | assertion | bilan sur `master` pur |
| --- | --- | --- |
| `test_421_effect_active_gate_offline.py` | `test_the_probe_rail_covers_the_whole_registry` | 1 failed / 12 passed |
| `test_448_r1_stormboyz_port_offline.py` | `test_O2_le_noeud_SortTilesByUtility_se_RE_EVALUE` | 1 / 13 |
| `test_462_r4b_r1_r1_defender_additive_carriers_offline.py` | `test_le_registre_des_producteurs_d_additif_defenseur_est_COMPLET` | 1 / 6 |
| `test_486r15_empreinte_par_entree_offline.py` | `test_la_DETTE_ne_peut_pas_absoudre_ce_qui_declare_deja` | 1 / 26 — **réparé sur `master` pendant que cette tranche était en vol** (`dd85e821`) |

Le 5ᵉ (`test_270r4r2r2_differes_offline.py`) était déjà déclaré ; le 6ᵉ
(`test_463r1_ecart_empreinte_offline.py`) était le **seul** dû à cette tranche — le fichier de
test neuf de #547 n'avait pas d'entrée d'empreinte, ce que `--measure-missing` a réglé.

Ces quatre ont été **déclarés** dans `NON_VERTS_DECLARES`, avec leur assertion **verbatim** et le
résidu **`#547-r2`**. Les taire aurait reproduit exactement la faute que ce cliquet garde ; les
réparer à l'aveugle aurait été pire — deux de leurs foyers étaient édités par d'autres tranches
au moment de la mesure. **La déclaration est elle-même sous cliquet** : chaque ligne rougit le
jour où son fichier redevient vert.

**Et ce cran a servi avant même la livraison.** `test_486r15_empreinte_par_entree_offline.py` a
été réparé sur `master` par `dd85e821` (« retirer de la dette un fichier qui DECLARE — signalé
trois fois, jamais réparé ») pendant que cette tranche était en vol. Au rebase suivant, le
**cran 2** a fait rougir sa déclaration devenue périmée, et la ligne est sortie. C'est le cycle de
vie qu'une entrée d'ici doit avoir : **entrer parce qu'un rouge est mesuré, sortir dès qu'il ne
l'est plus** — trois déclarations restent.

> **Le compte des rouges offline de `master` n'était donc pas 23, mais 23 + 5.** Aucun des cinq
> n'était mentionné nulle part — sauf, très exactement, dans le ledger que personne ne lisait.

## 6. `#547-r1` FERMÉ — le geste de PR ne peut plus se lire comme un verdict

`probe_457 --measure-missing` est le geste joué **en premier après chaque merge**. Il rendait
`rc = 0` en 2,8 s sur l'arbre à 23 rouges, et ce `0` a été lu comme « l'offline est vert » pendant
toute une campagne.

**Le correctif est le SILENCE sur un axe qu'il ne mesure pas, pas une mesure de plus** — et c'est
un résultat, pas un pis-aller. Ce mode juge la **complétude** des artefacts de sélection (poids +
entrée d'empreinte) sur les fichiers **neufs** ; il ne joue **jamais** un fichier déjà mesuré, par
construction et à dessein — le lui faire jouer serait un `--measure` complet (~976 s) payé à
chaque merge par tout le monde. La verdeur d'un fichier **existant** lui est donc structurellement
inaccessible.

⇒ **une passe partielle rend `1` (pytest a vu un rouge parmi ce qu'elle a joué) ou
`EX_NON_MESURE = 99`, jamais `0`.** C'est la convention que ce fichier tenait déjà pour ses autres
non-verdicts (CWD refusé, git muet, empreinte non produite). Foyer unique
`_non_verdict_de_verdeur`, qui **nomme** ce qu'il ne juge pas et renvoie vers ce qui juge.
**`--measure` COMPLET garde son `0`** : lui joue tout le périmètre.

**Contre-épreuve exercée, 4 étages** (`probe_547r1_mesure_missing_non_verdict.py`) :

| étage | ce qu'il exerce | mesuré |
| --- | --- | --- |
| 1 | le discriminant est `complete` | COMPLET → `0`, PARTIEL → `99` |
| 2 | le chemin « rien à mesurer » — celui du `rc = 0` historique | `99` |
| 3 | **témoin réel** : `assert False` injecté dans un fichier de test offline **existant**, commité dans un worktree témoin | fichier bien rouge (`pytest rc=1`), geste → **`99`** |
| 4 | **mutant du correctif** : on remet `return 0` | le `0` **revient** |

L'étage 4 est ce qui établit que **c'est le correctif qui agit**, et non le hasard du montage.
Garde : `test_547r1_mesure_missing_non_verdict_offline.py`, **9 tests**, dont le bras
anti-sur-correction (`--measure` doit garder son `0`).

⚠ **UN CLIQUET QUI LANCE LE LANCEUR DE TESTS QUI LE JOUE EST RÉCURSIF — mesuré, pas redouté.**
Ce cliquet lance `probe_457` en sous-process ; `--measure-missing` joue les fichiers **sans entrée
d'empreinte**, dont sa propre garde, qui rappelle le cliquet, qui relance `probe_457`…
**~150 processus chaînés, un toutes les 12 s, 35 minutes durant**, arrêtés par un `taskkill /T`.
Deux crans, et il a fallu les deux : le sous-process porte `TACTICUS_547R1_DANS_TEMOIN=1` et les
trois tests qui relancent `probe_457` sautent quand ils la voient ; **et la garde est retirée du
worktree témoin**, où elle n'a rien à faire — sa présence y faussait en plus l'étage 4, son propre
contrôle d'ancrage la voyant mutée et rendant `1` pour une raison parasite.
**Ce qui me l'a fait manquer deux fois** : les étages à worktree jugent l'arbre **commité**. Poser
la garde sans la **commiter** laisse le témoin rejouer l'ancienne version — exactement ce que la
docstring du cliquet prescrit, et que je n'avais pas appliqué à moi-même.

⚠ **L'ORDRE DES CLIQUETS NE CHANGE PAS** — `--measure-missing` **d'abord**, `probe_486r15`
**ensuite** (#486-r29) : le mode fait toujours son travail (compléter l'empreinte), donc la
confrontation passe bien à deux sources. **Ce qui change est la lecture de son `rc` : `99` est
désormais le retour NOMINAL**, et il ne doit pas être lu comme un échec.

## 7. Le trou structurel, MESURÉ — `#547-r3`

`probe_457` exclut les `*_live.py` **par choix** (la suite sature la session Frida partagée). Un
test purement offline **hébergé** dans l'un d'eux n'entre donc ni dans son périmètre, ni dans le
ledger, ni dans `probe_547`.

**Mesure du 2026-08-08** — collecte pytest sur les **520** fichiers `*_live.py`, **3 322** items :

| borne | critère | items | fichiers |
| --- | --- | --- | --- |
| **HAUTE** | clôture de fixtures ne touchant pas `LIVE_FIXTURE_ROOT` | **1 078** | 189 |
| **BASSE** | nom de l'item terminé par `_offline` — déclaration explicite de l'auteur | **64** | 34 |

La borne haute **surestime** : `probe_457` a déjà mesuré que des dizaines de `*_live.py` montent
leur runner **à la main**, sans passer par la fixture. La borne basse est un **plancher sûr**.

**Ce n'est pas théorique** : `test_pre_unit_ability_fork_live::test_port_reproduces_replaced_target_offline`
était rouge sur `master` et a survécu à toute la campagne par ce trou — trouvé par un bisect, pas
par un garde. Quatre fichiers sont même offline **en entier** (`live == 0`) et seulement mal
nommés. Les trois issues, et pourquoi aucune n'est évidente, sont dans la ligne de backlog.

## 8. Ce qui reste ouvert

* ~~**`#547-r1`**~~ — **FERMÉ**, cf. section 6.
* **`#547-r3`** — les **64** tests offline hébergés dans un `*_live.py`, cf. section 7.
* **`#270-r4-r2-r2-r4`** (déjà nommé dans `test_270r4r2r2_differes_offline.py`) — le seuil des
  imports différés est à **239 pour un plafond de 224**. Déclaré dans `NON_VERTS_DECLARES` : le
  sweep touche 28 fichiers partagés et chaque site doit passer par
  `migrate_485r1_barils_reexport.py morsure` avant d'être hissé en forme B.
* **`#547-r2`** — les quatre rouges de la section 5, **mesurés** et **non diagnostiqués**.
* **Quatre fichiers offline n'avaient aucune entrée au ledger** — jamais joués, donc jamais
  attestés. La passe de ré-attestation les a inscrits (269 entrées pour 269 fichiers, **0** sans
  entrée, **0** attestation périmée).
* **Le trou `*_live.py`** : un test offline hébergé dans un fichier `_live.py` est invisible du
  ledger comme de la banque. C'est ainsi que le rouge de `probe_120bis` a survécu.
