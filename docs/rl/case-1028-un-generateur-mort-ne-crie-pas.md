# #1028 — Un générateur d'audit mort ne crie pas

**Le défaut.** Le 2026-08-13, `scripts/python/audit_npc_registry.py` était INEXÉCUTABLE sur
`master` (`af2e590c`) :

```
ImportError: cannot import name 'TRAIT_COMMON_MAX' from 'audit_kit_coverage'
```

Cause **antérieure et juste** : #1015 a retiré `TRAIT_COMMON_MAX` d'`audit_kit_coverage.py`, parce
que ce seuil de fréquence (12 porteurs) écartait 22 traits en les présumant couverts, dont 3 ne
sont **lus nulle part**. `audit_npc_registry` l'importait encore.

**Ce qui rend ce défaut particulier** : il a vécu une journée entière sans être vu. Un générateur
mort n'émet aucun signal — son fichier de sortie **cesse simplement de changer**, ce qui ressemble
à « rien n'a bougé ». `docs/rl/npc-registry.tsv` n'était plus régénérable, et c'est l'artefact dont
l'orchestrateur tire la classification `[C-]` pour dispatcher.

## 1. Pourquoi aucun cliquet existant ne pouvait l'attraper

C'est plus instructif qu'un cran de plus. Mesure (`git grep -l` sur `scripts/python/tests`) :

| auditeur | fichiers de test qui le citent |
|---|---:|
| `audit_kit_coverage` | **9** |
| `audit_combat_ability_coverage` | 3 |
| `audit_passive_ability_coverage` | 1 |
| **`audit_npc_registry`** | **0** |

Les gardes existantes ne sont pas négligentes : elles gardent le **sujet** de leur tranche (les
voies de couverture #951-r2, le recenseur de faces #979, les canaux de trait #1015) et importent un
auditeur comme **moyen**. Aucune ne pose la question « tous les générateurs tournent-ils encore ? ».

**Une garde qui cite ses auditeurs un par un ne peut pas voir celui que personne n'a cité.** C'est
le vice répété du dépôt — un recenseur ne rend jamais zéro sur ce qu'il ne visite pas — transposé
des **données** aux **outils**.

## 2. La population est DÉRIVÉE, par deux sources, et la seconde est load-bearing

`scripts/python/probe_1028_generateurs_audit_executables.py` :

| source | critère | rend |
|---|---|---:|
| **A** préfixe | `scripts/python/audit_*.py` | 4 |
| **B** artefact | fichier VERSIONNÉ de `docs/rl/` portant « Genere par \`scripts/python/<X>\` » | 5 |

**B n'est pas une ceinture de plus — elle attrape ce que A rate.** Le cinquième générateur,
`probe_251_citation_resolution.py` (qui produit `docs/rl/build-<hash>-citations-perdues.md`), **n'a
pas le préfixe**. Une liste par convention de nom aurait donc raté un générateur réel dès le
premier jour — exactement la faute qu'on répare. B dérive de ce qui est **produit**, pas de la
façon dont c'est **nommé**.

L'étage `test_la_source_ARTEFACT_apporte_ce_que_le_PREFIXE_raterait` exerce cette propriété : sans
lui, la source B pourrait être supprimée sans qu'aucune assertion ne tombe (leçon #1015 étage 3).

## 3. Vu ROUGE avant d'être cru

Aucune cassure artificielle n'a été nécessaire : le défaut réel était encore dans l'arbre.

```
[1028] POPULATION DERIVEE : 5 generateur(s)
       source A (prefixe `audit_*.py`)      : 4
       source B (artefact `docs/rl` qui le nomme) : 5
       vus par B SEULE (que le prefixe raterait) : probe_251_citation_resolution

   ROUGE  audit_npc_registry                             IMPORT_ROUGE
          ImportError: cannot import name 'TRAIT_COMMON_MAX' from 'audit_kit_coverage'

[1028] 4/5 generateur(s) EXECUTABLE(S)
[1028] VERDICT : ROUGE
```

Garde : **1 failed / 7 passed** sur l'état cassé ; **8 passed** une fois la réparation en place.

**Deux contre-épreuves exécutables** (`tmp_path`, pas d'affirmation) : un module témoin cassé DOIT
sortir `IMPORT_ROUGE` avec sa cause nommée, et un module témoin sain DOIT sortir OK. Sans elles, un
`verifier()` qui retomberait sur « vert » rendrait tous les autres étages vrais **par vacuité** —
la faute exacte que #1015 volet 1 a dû réparer trois fois.

## 4. Choix de conception, et ce qui n'est PAS couvert

- **Process FRAIS obligatoire** (`subprocess`). Dans le process courant, un module déjà importé par
  un autre test de la passe rendrait VERT un module qui ne s'importe plus seul.
- **La panne porte son NOM** — `IMPORT_ROUGE` / `DELAI_DEPASSE` / `INTERPRETEUR_MUET`. Leçon
  #467-r6 : un `rc` ne nomme rien, et un capteur qui ne sait pas nommer sa panne fait corriger la
  mauvaise cause.
- **Une mesure incomplète LÈVE** (`MesureIncomplete`) au lieu de rendre une liste vide : une liste
  tronquée se lirait « tous verts ».
- **Une exception est DÉCLARÉE, jamais muette.** `EXCEPTIONS` est vide au 2026-08-13. Une entrée
  porte raison + source + date, et le test vérifie qu'elle correspond encore à un générateur
  **réellement rouge** : une exception posée sur un générateur qui remarche est une scorie qui
  masquerait sa prochaine panne.
- **NON COUVERT — l'EXÉCUTION** (résidu **#1028-r1**). On vérifie que le module **s'importe** et
  qu'il est **lançable** (garde `__main__`), pas qu'il va jusqu'au bout. Aucun générateur n'a de
  mode « à blanc », donc les jouer écrirait dans `docs/rl/` sous les pieds des autres agents. Un
  générateur qui planterait **en cours de route** sort VERT ici.
- **Pas d'entrée dans `scripts/ratchets.ps1`** : `probe_457` **dérive** son périmètre de
  `git ls-files scripts/python/tests`, donc le test neuf y entre seul. Foyer partagé évité.

## 5. Contre-épreuve gratuite : deux réparations indépendantes, une divergence de fond

La même panne a été réparée en parallèle par #1022 (`7d567cf3`). Les deux réparations retirent le
seuil ; **elles divergent sur le PRÉDICAT**, et l'écart est massif.

#1022 conserve `_trait_couvert` (trois registres `TRAIT_TRIGGERS`/`TRAIT_DERIVED_ABILITIES`/
`TRAIT_OWNER_EFFECTS` + effet homonyme). Son commentaire affirme pourtant :

> « `_trait_couvert` (qui delegue a `trait_channels`) repond trait par trait. »

**Il ne délègue pas** : `trait_channels` n'apparaît nulle part ailleurs que dans ce commentaire.
Le prédicat est resté celui d'avant #1015 — celui dont #1015 a **mesuré** qu'il rend des faux
négatifs, faute de voir le canal **dominant** d'un trait : la lecture impérative dans `engine/**`.

Conséquence, mesurée à **code moteur constant** (les trois régimes rejoués dans le même process,
donc tout écart est imputable au seul prédicat) :

| régime | seuil | prédicat | items TRAIT manquants (npc) |
|---|---|---|---:|
| A — `master` avant | 12 | registres | 50 |
| B — #1022 | aucun | **registres** | **963** |
| C — `trait_channels.canaux()` | aucun | canaux | **51** |

**Sur-comptage de 912 items (×18,9)**, réparti sur **25 traits** déclarés manquants à tort, en tête
desquels `Hero` (323 npc), `Mechanical` (98), `Flying` (94). Même forme sur les autres seaux :
summons 137 vs 7, lineup 250 vs 6.

C'est visible **sur l'artefact** que #1022 régénère — `docs/rl/npc-registry.md` y annonce
« kits sans manque : **5** » sur 491 npc (contre 376), et sa table « Travail restant, par ITEM »
ouvre sur *porter le trait `Hero`*, sur 323 porteurs.

Le sur-comptage est le moindre mal (doctrine : un audit qui sous-compte fait RENONCER), mais il
noie les **51** vrais items dans **912** faux, sur le document qui sert à dispatcher — et il rend
`npc-registry.md` incohérent avec son frère `kit-coverage.md`, qui utilise `trait_channels`. C'est
la forme exacte que #979 a fermée : deux prédicats divergents pour la même question. Résidu
**#1022-r4**.

**Correctif** (3 lignes) : supprimer `_trait_couvert`, `import trait_channels as TC`, et
`"covered": bool(TC.canaux(t)) or att is not None` — puis **régénérer** `npc-registry.md`/`.tsv`
(jamais les résoudre à la main). Cette tranche l'avait écrit et mesuré avant d'apprendre que #1022
était en vol sur le même fichier ; il n'est **pas livré ici**, pour ne pas rejouer en conflit une
réparation déjà mergée. Les chiffres du tableau ci-dessus viennent de cette version-là, rejouée
dans le même process que les deux autres régimes.

## 6. Ventilation nominative du delta (mesure conservée)

Le retrait du seuil et le changement de prédicat sont **deux facteurs distincts** — un delta global
les mélangerait. Sur le périmètre **npc** (491 unités, 58 traits distincts) :

**Facteur 1 — retrait du seuil : 38 traits ENTRENT au compte.** Parmi eux, **2 sont NON
COUVERTS** — du travail réellement révélé, que le seuil cachait *précisément parce qu'ils sont
répandus* : `InstinctiveBehaviour` (18 porteurs npc) et `CloseCombatWeakness` (16). Les 36 autres
entrent COUVERTS (`Hero` 323, `Mechanical` 98, `Flying` 94, …).

**Facteur 2 — changement de prédicat : 8 verdicts basculent**, tous NON COUVERT → COUVERT, tous par
le canal `lecture`, **0 régression** :

| trait | porteurs npc | canal qui l'établit |
|---|---:|---|
| `MachineOfWar` | 11 | `lecture` (`triggers/loki/fuelled_by_fury.py:203`) |
| `Boss` | 6 | `lecture` (`playbook/noncomparable/empyric_ambush.py:119`) |
| `Vehicle` | 5 | `lecture` + `TRAITS_MECHANICAL`, `_MOVEMENT_EXEMPT_TRAIT_IDS` |
| `Emplacement` | 3 | `lecture` (`entities/abilities/active_ability.py:473`) |
| `Impervious` | 3 | `lecture` + `TRAIT_CLASSES` |
| `NonAttacking` | 2 | `lecture` (`utilities/move.py:119`) |
| `PermaDeath` | 2 | `lecture` (`runner/abilities/attack_query.py:347`) |
| `Decoy` | 1 | `lecture` (`effects/loki/amulet_of_the_voidwyrm.py:174`) |

**Bilan npc — traits non couverts : 11 → 5.** Sortent : `Boss`, `Decoy`, `Emplacement`,
`Impervious`, `MachineOfWar`, `NonAttacking`, `PermaDeath`, `Vehicle`. Entrent :
`CloseCombatWeakness`, `InstinctiveBehaviour`.

⚠ **Le NET est trompeur, et c'est pourquoi la ventilation est obligatoire** : items TRAIT
manquants **50 → 51** (+1), kits sans manque **378 → 376** (−2). Ces deux deltas quasi nuls cachent
**67 items** et **40 unités** qui changent de camp (19 unités entrent « sans manque », 21 en
sortent). Un delta non ventilé n'aurait été qu'une non-information.

**Triangulation indépendante** : mes comptes par seau somment exactement aux comptes tous-seaux de
#1015 — `InstinctiveBehaviour` 18 npc + 5 summons = **23** ; `Healer` 12 npc + 6 lineup = **18** ;
`TwoManTeam` 4 + 2 = **6** ; `CloseCombatWeakness` **16** ; `BeastSnagga` **1**. Les cinq traits non
couverts de #1015 sont retrouvés, par un chemin de mesure différent.
