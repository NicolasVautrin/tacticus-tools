# #1021 -- Le cran d'entree au registre : une active de `ABILITY_CLASSES` porte son VERDICT de face DECISION

**Etat : LIVRE.** Cran pose, dette figee, un item tranche, un rouge de `master` repare.

## 1. La question binaire, et ce qu'elle valait avant

> Une active qui entre dans `ABILITY_CLASSES` peut-elle etre livree SANS verdict de face DECISION ?

Avant cette tranche : **oui, en silence**. `probe_909_decision_actives_kit.py` COMPTAIT les actives
sans face DECISION portee et rendait `rc=0` sur ce compte -- un inventaire deguise en garde-fou.
C'est le defaut EXACT de `probe_181_targeting_gaps.py` avant #430 : cite comme cliquet par le
`CLAUDE.md` et par les case-docs, il rendait `0` inconditionnellement.

Le gisement est celui que **notre propre cadence de portage alimente**, comme `TARGETING_OPTIONS`
et `ABILITY_ATTACK_TYPE` : chaque ability portee en COMBAT sans qu'on dise rien de sa face
DECISION rouvre le trou. La degradation est **muette** -- l'unite s'execute fidelement mais est
CHOISIE par le chemin generique, ce qui est invisible en replay.

### La mesure AVANT (build `rnca9r7q6c`, `master` a `f51b2447`)

`ABILITY_CLASSES` = **171** entrees. Face DECISION : **152 PORTEE**, **3 CONSTANTE**,
**16 SANS AUCUN VERDICT**.

Ces 16 ne sont pas les 14 `[C-]` de `audit_npc_registry` : ce sont **les 14 PLUS DEUX** que nul
inventaire de kit ne montrait --

| id | nom | pourquoi il manquait aux inventaires |
|---|---|---|
| `1076` | `MV71SniperDroneSquadAttack` | **0 porteur** par `activeAbilities` : c'est une attaque NORMALE (cf. §4), attribuee au runtime |
| `1211` | `RitesOfMorkai` | porteur `lineup` seul, donc hors du registre npc |

C'est le fait qui justifie l'axe choisi : **le cran porte sur `ABILITY_CLASSES`**, pas sur une
population de kit. Le registre de la face COMBAT est le seul endroit ou une ability *entre* par un
geste de portage -- c'est donc la que le cliquet doit se tenir.

## 2. La forme : dette FIGEE, et aucun cran ne compare un compte a un nombre

Poser l'obligation seche rendrait `master` rouge sur 16 abilities le jour de la livraison -- donc
la ferait desarmer dans l'heure.

**Precedent copie : `probe_287r9_consommateurs_oracle.py` (#287-r9)** -- registre `DETTE` en dur
dans le module, versionne, plus des crans A/B/C. (`declencheur_guard` / #486-r15 emploie la meme
forme avec la dette dans un fichier texte ; le registre en dur a ete prefere ici parce que chaque
ligne porte sa RAISON, longue, et qu'un TSV la rendrait illisible.)

```
CRAN A  un id sans verdict et ABSENT de `DETTE`               -> ROUGE   (regression)
CRAN B  un id declare `TRANCHE` qui a PERDU son verdict       -> ROUGE   (regression)
CRAN C  population / mirror / voies / verdicts vides          -> ROUGE   (mesure creuse)
---     un id `SANS_VERDICT` qui a ACQUIS son verdict         -> IMPRIME, jamais rouge
```

**Le compte n'est un seuil nulle part, et c'est delibere.** Le 2026-08-13, CINQ cliquets ont rougi
parce qu'une ability avait ete PORTEE : leurs planchers de population (`>= 20`, `>= 1`,
`any(canal peuple)`) lisaient le progres comme une panne. Ici la dette **ne peut que descendre** :
un item tranche se retire, et le CRAN A le protege ensuite pour toujours. L'inverse -- un id qui
reviendrait sans verdict -- est un elargissement de `DETTE`, donc une ligne ajoutee dans un diff.

L'etage 9 du cliquet **grave** cette propriete structurellement : dette VIDEE, le CRAN A doit rendre
EXACTEMENT les sans-verdict, et B et C rester verts. Un cran qui tiendrait a un cardinal le ferait
rougir.

### Vu ROUGIR, pas seulement vu vert

Un cliquet jamais vu rougir ne prouve rien -- c'est le defaut repare ici. Contre-epreuve JOUEE sur
l'arbre reel : `4: ThunderousAssaultAbility` ajoute a `ABILITY_CLASSES`, puis retire.

```
[1021] CRAN A (aucun sans-verdict hors du registre de dette) : FAUTE (1)
   MANQUANT 4      Taunt                          ThunderousAssaultAbility               strike
   => Cette active est entree dans `ABILITY_CLASSES` (face COMBAT portee) sans
      qu'aucun verdict ne dise ce qu'il en est de sa face DECISION. Trois issues,
      et << je verrai plus tard >> n'en est pas une : [...]
[1021] VERDICT : FAUTES
rc=1
```

Et les trois crans ont ete vus rougir **par mutation du probe**, ce qui garde le cliquet lui-meme :
`a = []` fait tomber les etages 4 et 9 ; `b = [... if False]` l'etage 5 ; `if False and hors_mirror:`
l'etage 7.

### Le robinet est ferme la ou il etait ouvert

`probe_909` etape 7 appelle le cran et **AJOUTE ses fautes a son `rouge`**. L'etage 11 du cliquet
garde les deux moities : l'appel ET la propagation -- un appel qui n'influence pas le code de retour
ne garde rien.

## 3. Un ROUGE de `master`, trouve en rejouant les cliquets voisins

`tests/engine/test_979_recenseur_faces_decision_offline.py` rendait **2 failed / 14 passed** a
`f51b2447`, sur une cause ANTERIEURE a cette tranche (`4e712818`, #957-r3). Le temoin exigeait
`not face_portee(1197)` -- << AUCUN conteneur de niveau module ne peut l'exprimer >>. Vrai a #979,
faux depuis que `1197 ExcruciatingFrequencies` est entree dans `_MAKE_DMG_INPUT_OVERRIDES` pour son
`nrOfHits` LITTERAL. Meme forme que #519 : **nos livraisons periment nos temoins**.

Le fait, LU au site (le commit qui l'a cree l'ecrit noir sur blanc dans
`engine/playbook/prediction/abilities.py`) -- les deux canaux **coexistent** et ne disent pas la
meme chose :

* le GENERATEUR bespoke porte le **CHOIX** de l'ability (ses evals ont `rankCount = 0`, elle n'entre
  dans aucun `plan`) ;
* la VOIE de registre porte une **ENTREE de sa prediction de degat** (les hits).

`decision_face_voies.etat` fait deja PRIMER la voie, et c'est correct -- son docstring le prescrit.
L'attestation n'est donc pas fausse : elle a cesse d'etre **DECOMPTANTE**, et reste au ledger parce
qu'elle NOMME le porteur du choix et le tient resolvable.

Repare **sans rien affaiblir** : la voie attendue est nommee exactement (un conteneur en plus OU en
moins fait rougir), la primaute de la voie sur l'attestation est assertionnee, et dans la
contre-epreuve de peremption `1197` **change de bras** au lieu de disparaitre -- on exige desormais
qu'elle reste PORTEE quand son attestation perime, puisqu'une voie ne perime pas avec le build.

## 4. `1076 MV71SniperDroneSquadAttack` -- TRANCHE : `RIEN_A_PORTER`

C'est l'item que rien ne montrait, et c'est le seul du lot dont le playbook natif n'a **aucune
methode propre**. L'absence dans les tables ne prouvant RIEN (IL2CPP deduplique les corps triviaux),
le verdict est etabli par **trois sources independantes** :

**(a) Ghidra -- la classe ne surcharge rien.** `search_symbols_by_name` sur
`MV71SniperDroneSquadAttackPlaybook` rend **un seul symbole**, son `.ctor` :

```
IdunBattle.AI.Playbook.Loki.MV71SniperDroneSquadAttackPlaybook$$.ctor
    -> ALoki_NormalAttackPlaybook<T>$$.ctor(this, 0x434 = 1076, ...)
```

**(b) `frida/classes.tsv` (source DISTINCTE du dump) -- c'est une attaque NORMALE.** Le parent de la
classe d'**ABILITY** est celui que le `CLAUDE.md` nomme pour l'attaque normale :

```
IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility
    -> IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility
```

et la chaine du playbook est `ALoki_NormalAttackPlaybook<T>` -> `ComparablePlaybook<T>` ->
`Playbook<T>` -> `BasePlaybook`.

**(c) Le gameconfig -- `1076` n'a AUCUNE voie de kit.** Balaye sur toutes les cles de tous les kits,
par NOM **et** par ORDINAL : zero. Coherent avec une attaque normale, attribuee au runtime
(`NormalAttackType@0x28`), jamais listee dans `activeAbilities`.

**Le temoin de FAMILLE** confirme le regime plutot qu'un cas isole : la famille
`ALoki_NormalAttackPlaybook<T>` compte **17 classes derivees**, dont **15 coquilles** (0 methode
propre), **toutes les 17 NON PORTEE**, et **une seule au registre COMBAT** -- celle-ci.
`Loki_NormalAttackPlaybook` (id `69`, l'attaque normale generique elle-meme) y figure, coquille et
non portee : si le port devait porter la face DECISION de chaque attaque normale concrete, il
devrait porter celle-la d'abord.

**Ce que la BASE porte, et qui n'est PAS propre a `1076`** -- lu verbatim, pour ne rien cacher :

```
ALoki_NormalAttackPlaybook<T>$$CalculateCustomUtility   ->  Fix64(1)   (constante)
ALoki_NormalAttackPlaybook<T>$$ShouldExecute            ->  if (UnitExtensions$$HasTriggeredAbility(unit, 0x48 = 72 Explosive)) return false;
                                                            return utility > Fix64(0);
ALoki_NormalAttackPlaybook<T>$$MakeDamagePredictions
```

Le gate `Explosive` est un fait de la **BASE**, commun aux 17 : il n'appartient pas a `1076` et ne
se porte pas 17 fois. Residu `#1021-r1` ouvert pour lui.

## 5. `1023 Burrowers` -- LU EN ENTIER, NON TRANCHE (ce n'est PAS `RIEN_A_PORTER`)

Premier item par nombre de porteurs (6, npc + summons). Le RE est fait ; le port ne l'est pas, et
forcer un verdict serait pire que l'absence.

**Piege ecarte d'entree** : `BurrowersPlaybook$$.ctor` se decompile en
`ComparablePlaybook<T>$$.ctor(this, 0x3ff)`, ce qui ferait viser le mauvais registre. C'est un
**mislabel ghidra** des ctors gshared, exactement celui que le `CLAUDE.md` interdit de suivre :
`frida/classes.tsv` donne le vrai parent, `IdunBattle.AI.Playbook.NonComparablePlaybook<T>`. Registre
vise : `playbook.noncomparable.PLAYBOOKS` -- ce que la derivation par methode propre de `probe_909`
annoncait deja (`EvaluateNonComparable` surchargee).

**`BurrowersPlaybook$$EvaluateNonComparable`**, les deux slots d'interface RESOLUS dans
`data/symbols/rnca9r7q6c/metadata/interface_slots.tsv` (jamais devines) :

```
d = IBattleQuery<this+0x28>.<slot 0x6c = 108 GetDistance>(
        EntityExtensions$$GetMainTile(caster, this+0x20),
        UnitPosition$$get_MainTile(casterPosition))
x = Fix64(d)
if (d > 0)
    x = x + IPseudoRNG<this+0x30>.<slot 3 = Next(min, max)>(-Fix64(1), Fix64(1))
BasePlaybook$$GenerateAction(this, casterPosition, caster, x)  ->  Bucket$$AddAction
```

**`BurrowersPlaybook$$ShouldEvaluate`** :

```
d = BasePlaybook$$GetAllNormalAttackTargets(this, unit)
return d.<count@0x18> < 1
```

Lecture : Burrowers n'est evaluee que si le caster n'a **aucune** cible d'attaque normale, et elle
prefere alors la destination la plus **LOINTAINE**, un tirage dans `]-1, +1[` departageant les
distances egales.

**Pourquoi non tranche** : c'est du travail REEL (ce n'est en aucun cas le chemin generique), et le
terme `IPseudoRNG` en fait un port dont la validation live demande son propre montage -- une
comparaison de distribution, pas un datapoint. Residu `#1021-r2`, avec cette lecture en entree.

**Detail a verifier au port** : `BurrowersPlaybook$$.cctor` ecrit `Fix64(1)` dans le champ statique
de la classe, et le corps lit **ce meme statique** comme borne du RNG. Chez les voisins
(`HammerOfWrathPlaybook`) ce statique est le `MIN_UTILITY`. Ne pas recopier le voisin de forme :
verifier lequel des deux roles il tient ici, ou les deux.

## 6. Ce que le cran NE garde PAS (portee imprimee a chaque execution)

* les actives **hors `ABILITY_CLASSES`** -- **85** sur les 260 membres du mirror sont sans verdict et
  hors registre. Leur face COMBAT n'est pas portee, donc elles n'entrent pas dans la population : le
  cran ne les garde pas, et il l'imprime plutot que de rendre un zero ;
* les faces **TRIGGERED / NON-OWNER / SPECIFIC** (dicts `+0x88`, `+0x98`, `+0xa8` de
  `IdunBattle.AI.PlaybookDatabase`) -- autre population, autres inventaires (case-419,
  case-433-r4-r3, case-477r33/r35/r37) ;
* la **FIDELITE** d'un verdict `PORTEE` : le cran dit qu'une voie DESIGNE l'ability, jamais que
  l'utilite portee est juste ;
* la **substance** d'un item en dette : la raison inscrite cite le playbook natif et ses methodes
  propres, qui sont une **borne INFERIEURE** (dedup IL2CPP).

## 7. Un SECOND rouge de `master`, SIGNALE et non repare

`python scripts/python/audit_npc_registry.py` a `f51b2447` :

```
ImportError: cannot import name 'TRAIT_COMMON_MAX' from 'audit_kit_coverage'
```

**L'outil qui produit les `[C-]` -- ceux-la memes dont part cette tranche -- ne tourne plus**, et
`docs/rl/npc-registry.tsv` n'est donc plus regenerable. Cause nommee et anterieure : **#1015** a
supprime ce seuil de `audit_kit_coverage.py`, a raison (il ecartait 22 traits en les *presumant*
couverts, dont 3 lus nulle part dans `engine/**`), en le remplacant par `trait_channels.canaux()` ;
`audit_npc_registry.py` l'importe toujours et s'en sert a deux endroits, tous deux sur l'axe TRAITS.

**Non repare ici, a dessein.** La reparation correcte est la migration vers `trait_channels`, avec
la RE-MESURE du compte de traits npc qu'elle change. Retirer le seuil << a sec >> ferait bouger un
compte sans que personne puisse dire s'il est juste -- le vice meme que #1015 corrigeait. C'est
l'axe TRAITS, pas celui de #1021. Residu `#1021-r3`.

**Le verdict de #1021 n'en depend pas** : ses 16 sans-verdict sont derives par une voie
INDEPENDANTE (`ABILITY_CLASSES` x `decision_face_voies.etat`) et RECOUVRENT les 14 `[C-]`, plus les
deux que nul inventaire ne montrait.

## 8. Residus

* **`#1021-r1`** -- la face DECISION de la BASE `ALoki_NormalAttackPlaybook<T>`, commune aux 17
  attaques normales concretes (gate `HasTriggeredAbility(0x48 = 72 Explosive)` + `CalculateCustomUtility`
  = `Fix64(1)`). Une seule des 17 est au registre COMBAT, donc le cran #1021 n'en voit qu'une.
* **`#1021-r2`** -- porter `1023 Burrowers` (RE complet en §5, slots resolus).
* Les **14** autres lignes de dette restent ouvertes, chacune avec sa substance derivee dans
  `probe_1021_face_decision_au_registre.DETTE`.
