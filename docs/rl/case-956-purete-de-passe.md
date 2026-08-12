# #956 — Le verdict de la banque offline dépendait de la **composition des shards**

`probe_457 --jobs N` répartit les fichiers de test offline en **shards** : chaque shard est un
processus pytest où plusieurs fichiers tournent ensemble, et N shards tournent **en parallèle sur
un seul arbre de travail**. Si un fichier de test **écrit** dans un fichier **versionné**, un autre
fichier de test qui le **lit** voit un état qui dépend de qui a tourné avant lui — donc de `N`.
Aucun de nos cliquets ne regardait cet axe : `probe_547` lit le ledger, `probe_486r15` lit les
déclencheurs, `--since` lit le diff. **Aucun ne regarde qui ÉCRIT.**

## 1. L'accusation d'origine était fausse — et sa réfutation est la première mesure

La tranche part de :

```
pytest tests/test_463r1_ecart_empreinte_offline.py            -> 1 passed
pytest tests/test_457_r8_...py tests/test_463r1_...py         -> 1 failed, 54 passed
```

**Refait sur un arbre témoin détaché à `origin/master` (`82d0ac3d`)**, les trois formes rendent le
**même** verdict :

| geste | résultat | `git status` après |
|---|---|---|
| le nodeid seul | 1 failed | propre |
| le fichier seul | 1 failed, 32 passed | propre |
| la paire `457_r8` → `463r1` | 1 failed, 54 passed | propre |

Il n'y a **aucune dépendance à l'ordre sur cette paire**. Le `1 passed` initial ne peut venir que
d'un arbre où `scripts/ratchets-457-footprints.json` était **déjà modifié** — l'arbre principal,
dont le `git status` montrait précisément ce fichier `M`. **Deux arbres différents, une seule
accusation** : le même piège que « deux `origin/master` font une fausse accusation ».

La cause réelle du rouge : `5fcf1cf8` (#951) livre `tests/engine/test_951_trophy_taker_offline.py`
**sans jouer `--measure-missing`**. Le cliquet #463-r1 faisait exactement son travail, et il le
faisait **indépendamment de l'ordre**. Geste appliqué : `--measure-missing`, 1 fichier joué sur
338, empreinte 337 → 338.

> **Ce que ça enseigne** : un verdict de cliquet ne vaut que **relativement à l'état de l'arbre**,
> et nos artefacts à cliquets sont dans l'arbre. Comparer deux mesures prises sur deux arbres
> différents fabrique une dépendance qui n'existe pas — pendant qu'une vraie, ailleurs, reste
> invisible.

## 2. Le mécanisme, mesuré — deux écrivains sur 75

Instrument : `probe_956_purete_de_passe.py`, hook d'audit `open` **mode-aware** + événements
`os.*` / `shutil.*`, attribution **par fichier de test**. Périmètre : les **75** fichiers de test
offline (sur 338) qui portent au moins un site d'écriture ou de lancement de processus — filtre
statique **sur-approximant** (`replace` matche aussi `str.replace`, `subprocess.run` matche aussi
un `git status`). 4 processus, ~600 s de mur.

**Résultat : 2 écrivains de fichiers versionnés.**

### (a) `tests/test_546_capteurs_fenetre_offline.py` — un vrai danger

Ses huit contre-épreuves **écrivaient les sources de hook versionnées**
`frida/hooks/features/ai-step/rpc-{targeting,board,snapshot}.ts`, puis les restauraient dans un
`finally`. Deux conséquences, les deux chiffrées :

* **fenêtre de fausseté mesurée : 4 à 12 ms par mutation**, ~7 mutations par passe, soit **~60 ms
  par passe** pendant lesquelles un fichier versionné est FAUX sur disque ;
* **11 fichiers de test offline lisent `frida/hooks/`** (dérivé de l'empreinte versionnée) — dix
  autres que `test_546`, donc répartis dans d'autres shards.

La collision est **rare et non reproductible** : une course lancée 55 s (un processus rejouant
`test_546`, un autre relisant les étapes) a rendu **44 lectures, 0 faux verdict**. C'est exactement
ce qui rend le défaut dangereux — quand il tire, il produit un rouge (ou un vert) que personne ne
sait rejouer. S'y ajoute que ces `.ts` sont des **entrées de build** (#365/#480-r1) : une
interruption pendant les 60 ms laisse la mutation **sur disque**, dans un fichier versionné.

**Réparé** : la substitution porte désormais sur `probe_546._lire`, **foyer unique de lecture** du
probe (11 sites y passent), donc **en mémoire**. La mutation traverse le même code, n'écrit rien.
Trois crans pour que « la mutation a MORDU » reste un fait : le motif doit exister dans la source
réelle, la substitution doit changer le texte, et `_lire` doit avoir été **réellement appelé** sur
ce chemin pendant l'étape. Plus un test qui compare le **sha du fichier** de part et d'autre.

### (b) `tests/engine/test_270r4r2r2_differes_offline.py` — exempté, et l'exemption est conditionnée

Il écrit `scripts/cliquets-cache/probe_270r4r2_import_en_premier.tsv`, le **cache de verdict par
fichier** (#486-r1). Ce cache est **content-addressed** : sa clé porte le sha256 du contenu jugé,
donc une entrée périmée ne peut que **MANQUER** — donc faire recalculer — jamais mentir. Sa
neutralité n'est pas une déclaration : `verdict_cache.verifier` **recalcule tout en ignorant le
cache** et confronte entrée par entrée, et `tests/test_486_r1_cache_verdict_offline.py` le joue.

L'exemption est donc **une classe d'artefact dont la neutralité est prouvée ailleurs**, pas une
allowlist de circonstance. Elle est tenue par quatre crans :

1. le préfixe est **dérivé** de `verdict_cache.DOSSIER`, jamais recopié ;
2. le foyer est **unique** — `probe_457._prefixes_neutres()` **délègue** à
   `probe_956.prefixes_neutres()`, et un test vérifie la délégation ;
3. l'exemption est **UNIQUE** (le test compare l'ensemble entier : une seconde entrée rougit) ;
4. la **preuve** doit exister (`verdict_cache.verifier` + son fichier de test), sinon le test rougit.

Elle est **imprimée à chaque passe** : une exemption tue est indistinguable d'un angle mort.

## 3. Le remède : les trois familles, pesées

| famille | ce qu'elle coûte | retenu ? |
|---|---|---|
| **isoler** — le test écrit dans un temporaire | il faut re-prouver que la mutation MORD ; ici, gratuit, parce que le probe avait déjà un **foyer unique de lecture** à substituer | **oui, pour (a)** |
| **restaurer** — une fixture qui remet l'artefact après chaque fichier | masque le vice au lieu de le supprimer, et ne protège **pas** du shard concurrent qui lit **pendant** | **non** |
| **refuser** — un cliquet qui rougit si la passe laisse l'arbre sale | ne répare rien, mais rend le fait visible et **non régressif** ; ~0,4 s par shard | **oui, en plus** |

Les deux retenus sont **complémentaires par construction**, et le test le **mesure** :

* le **capteur du shard** (`probe_457`) : deux `git status --no-optional-locks` de part et d'autre
  de la passe, **empreinte de contenu** sur les fichiers déjà sales. Exhaustif, quasi gratuit,
  couvre les **processus fils** — mais **n'attribue à personne** et **ne voit pas** une écriture
  défaite avant la borne. *Il n'aurait donc pas trouvé (a).*
* le **probe attribuant** (`probe_956`) : hook d'audit par fichier de test, voit les écritures
  **transitoires** — mais ne franchit pas la frontière de **processus**. *Il n'aurait pas vu une
  écriture faite par un fils.*

Aucun ne subsume l'autre, et `test_956_purete_de_passe_offline.py` le **démontre** sur un dépôt
jetable : `--sans-git` rate l'écriture du fils, `git` seul rate la restauration.

**Le refus est branché au bon endroit** : la salissure devient le **4ᵉ refus d'écriture du ledger**
(`_ecrire_ledger`) — une attestation dit « vert **sur cet arbre** », et si la passe a changé
l'arbre, elle ne désigne plus un état retrouvable. Le shard rend alors `VERDICT: FAIL` en
**distinguant** « les tests sont verts » de « la passe a changé l'arbre ».

**Pourquoi l'empreinte de CONTENU et pas la liste** : un worktree d'agent est **sale avant** la
passe — c'est la règle, un worktree propre est auto-supprimé. Comparer deux listes rendrait
invisible le cas le plus dangereux, un artefact **déjà modifié** que la passe modifie **encore** —
c'est-à-dire l'état exact où la confusion du §1 est née. On ne hache que les fichiers déjà sales :
zéro dans un arbre propre.

**Pourquoi `--no-optional-locks`** : `git status` rafraîchit l'index, donc prend `index.lock`. Le
capteur tourne dans **chaque** shard et `--jobs N` en lance N ensemble ; sans le drapeau, le
capteur de la dépendance au découpage serait lui-même dépendant du découpage.

## 4. Ce qui n'est PAS couvert — et il faut le lire

* **Le canal MÉMOIRE.** Deux fichiers d'un même shard partagent `sys.modules`, les caches mémoïsés
  et tout `monkeypatch` mal défait. La composition change qui partage un processus **et dans quel
  ordre**. Un hook d'audit sur les écritures ne peut pas le voir, et le mesurer exhaustivement
  demanderait O(n²) passes. **Résidu #956-r1.**
* **Les écritures hors-versionné** (`logs/`, `__pycache__`, temporaires) : comptées et rendues,
  jamais bloquantes. Deux shards peuvent s'y marcher dessus — c'est le gisement mesuré par #455 sur
  `scripts/python`, distinct de celui-ci.
* **Les 263 fichiers écartés** par le filtre statique. Le filtre sur-approxime (il ne rate pas une
  écriture, mais il ne prouve rien sur ce qu'il écarte) ; `--tout` existe, au prix de la banque.
* **Le TEMPS.** Deux découpages ne rendront jamais les mêmes durées — l'un trouve le cache de
  verdict chaud, l'autre froid. C'est voulu, et c'est une raison de plus pour qu'un **chronomètre
  ne prouve rien** sur cet axe.

## 5. Le critère de réussite, mesuré : deux découpages, un seul verdict

Périmètre de l'épreuve : les **14** fichiers de test offline dont l'empreinte **mesurée** dit
qu'ils ouvrent quelque chose sous `scripts/` — c'est-à-dire exactement ceux que le canal disque
peut faire diverger (les lecteurs et écrivains des artefacts à cliquets partagés). 302 s cumulés.

| découpage | forme |
|---|---|
| **A** | **1** processus, les 14 fichiers, dans l'ordre du recensement |
| **B** | **3** processus **concurrents** (LPT sur les poids : 7 / 3 / 4 fichiers), ordre **inversé** dans chacun |

Verdict comparé **par cas** (`--junit-xml`, jamais un chronomètre — sur machine partagée un
chronomètre ne prouve rien) :

```
decoupage A : 283 cas ; decoupage B : 283 cas
cas presents seulement en A : 0 ; seulement en B : 0
ECARTS DE VERDICT : 0
```

**283 cas sur 283, même verdict.** Aucun cas ne disparaît d'un côté — ce qui est la seconde
manière dont un découpage peut mentir (#455-r3 : un fichier dont tous les tests ont disparu
n'émet aucun report).

⚠ **Ce que cette épreuve ne fait PAS** : elle ne montre pas le défaut **avant** correction. Le
défaut de `test_546` est une **course** dont la fenêtre mesure ~60 ms par passe (§2a) : une
tentative de le déclencher (55 s, un processus rejouant `test_546`, un autre relisant les étapes)
a rendu **44 lectures, 0 faux verdict**. Un défaut qu'on ne sait pas déclencher à la demande ne se
prouve pas par une épreuve — il se prouve par sa **cause**, qui elle est lue : le fichier
versionné **est** faux sur disque pendant ces 60 ms, et **11 fichiers de test** lisent ce
répertoire.

## 6. Le geste qui vérifie

```powershell
cd scripts/python
python probe_956_purete_de_passe.py          # attribuant, borne aux candidats derives
```

et, sans rien demander à personne, **chaque passe de la banque** : le capteur du shard est
toujours armé, et son `VERDICT: PASS` affirme désormais **deux** faits — les tests sont verts, **et
la passe n'a modifié aucun fichier versionné**.

## 7. Le dixième rouge de `master` : `test_449_r2` — une cause de détecteur, deux attestations

Quatre tests rouges, trois causes, **aucune assertion ajustée** :

1. **Faux positif du détecteur** (`parametre MORT`). `probe_449r2_spread_inventory` ne cherchait
   les lectures d'un paramètre de `__init__` que dans les **autres méthodes de la même
   `ClassDef`**. `ChainAttackDamage` n'a **que** son `__init__` : il range la variance dans
   `self.damage`, et c'est `ChainAbilityDamage.execute` — la classe de **base** — qui lit
   `self.damage`. `_methodes_heritees` remonte désormais les bases, transitivement, et **refuse de
   suivre** un nom de base qui ne désigne pas exactement **une** `ClassDef` de l'arbre : un doute
   laisse le compte **minoré**, donc rouge, et il est **rapporté**. Suivre au hasard fabriquerait
   un faux négatif, la seule direction dangereuse de ce détecteur.
2. **Deux attestations manquantes, lues au décompilé** (`rnca9r7q6c`).
   `IdunBattleLogic.Entities.DSLBehaviors$$ChainAttackDamage` **nomme** son argument
   `damageOptions` — 10ᵉ position, un `Nullable<AttackDamageBehaviourOptions>` de 0x20 octets
   recopié tel quel dans `IdunBattle.Entities.Behaviours.ChainAttackDamageBehaviour$$.ctor`. Ses
   **deux** consommateurs mettent les quatre qwords à **zéro juste avant l'appel** :
   `IdunBattleLogic.Entities.Abilities.Active.Loki.KissOfDeathAbility$$ExecuteBehaviour` et
   `IdunBattleLogic.Entities.Abilities.Triggered.Loki.FuryOfTheAncientsAbility$$CreateBehaviour`.
   Nullable **vide** → octet d'aiguillage `+6` nul →
   `IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` prend la branche **plate**. Le
   `amount_spread_pct = 0` du port est donc **lu**, pas supposé. ⚠ Ce **n'est pas** le 8ᵉ argument
   d'`$$AttackWithAttackDamage` : la raison est **écrite à part**, pas recopiée de la voisine.
3. **Justification périmée.** `UseNormalAttack` ne surcharge plus `__init__` — il hérite celui
   d'`UseActiveAbility`, qui porte déjà son attestation. Son entrée d'`EXPECTED_DEFAULT` ne
   désignait plus aucune signature.

Trois cas d'auto-test ajoutés : le patron (C7quater), la **borne** — base qui ne lit plus
l'attribut, le paramètre redevient MORT (C7quinquies) — et le **doute** sur une base homonyme
(C7sexies), qui vérifie aussi qu'il est **rapporté**.

## 8. Résidus ouverts

* **#956-r1** — le canal MÉMOIRE de la dépendance au découpage (§4).
