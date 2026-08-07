# #457-r10 / #486-r22 / #526-r1 / #526-r2 — trois artefacts qui dérivent, trois déclencheurs

Trois résidus, un même patron : **un artefact du dépôt se périme sans que rien ne le dise**, parce
que le geste qui le rafraîchit n'a aucun déclencheur. Les trois réponses sont différentes, et c'est
le point de cette fiche : le déclencheur juste dépend de **qui paie** et de **quand la décision est
prenable**.

---

## 1. `#457-r10` — la prose disait VERSIONNÉ, le chemin disait `logs/`

Le même bloc de commentaire se contredisait à dix lignes d'écart :

```
ligne 513  « VERSIONNE a dessein : sans lui, un checkout frais retomberait sur le repli md5 »
ligne 524  « le prix a payer est que `logs/` est gitignore, donc un checkout frais retombe
             sur le repli md5 »
```

`git ls-files logs/` rend **0**. La première phrase était donc fausse, et tout worktree d'agent
retombait **déjà** sur le repli.

**Tranché en tenant l'intention (option a), sur la mesure.** Le résidu exigeait de chiffrer le
repli avant de choisir. Sur les 254 fichiers du périmètre et les poids réels, à 8 shards :

| répartition | mur | charges des shards |
| --- | --- | --- |
| par POIDS (LPT) | **189,8 s** | 190 × 8 |
| repli md5 | **377,9 s** | 378 / 239 / 210 / 195 / 166 / 132 / 115 / 81 |

**+99 %** — le repli ne rend pas le mur « sous-optimal », il le **double**, pour un plancher
insécable de 100,8 s. Et ce mur est payé dans chaque worktree d'agent, à chaque PR (`ratchets.ps1`
chiffre `probe_457` à 67 % du coût de la banque, ~891 s par agent et par PR).

Le déplacement ne coûte rien : `scripts/ratchets-457-durations.json` vit **exactement où**
`ratchets-457-footprints.json` vit déjà, écrit par le **même** `--measure`, au **même** endroit du
code. `#455` (« jamais sous `scripts/python/` », parce que la banque y court en parallèle et que
plusieurs cliquets l'énumèrent) reste tenu : `scripts/` lui-même n'est pas énuméré. Aucune
concurrence n'est ajoutée — les poids ne sont écrits que par `--measure` / `--measure-missing`,
modes de maintenance mono-process, jamais par les 8 shards.

**Le tri-état de `#463-r1` reste**, sa cause première seulement est fermée. « Poids absents » ne
peut plus être l'état permanent d'un worktree, mais un fichier peut toujours manquer — et un
critère qui ne saurait plus le dire retomberait dans le zéro fabriqué.

Vérifié : 254 poids lus depuis un worktree frais, là où il y en avait **0**.

---

## 2. `#486-r22` — le déclencheur existait déjà, personne ne le lisait

Mesure : `probe_313 --verifier-cache` rend **rc=3, 38 divergences** (5 SHA PÉRIMÉ, 33 ENTRÉE
ABSENTE) pendant que le régime normal rend **rc=0 en 10 s**. Une entrée périmée est recalculée,
**réécrite**, et jamais rougie.

**Le fait qui donne le cran** : le régime normal **réécrit le fichier versionné**. Mesuré —
`git status` après une passe rend `M scripts/cliquets-cache/probe_313_….tsv`. Donc la question
« du code est-il entré sans que le cache suive ? » a déjà sa réponse sur le disque ; il suffisait
de la poser.

Le résidu nommait le piège de forme, et ce cran n'en est aucune des deux branches :

- exiger `--verifier-cache` vert à chaque passe déplacerait le coût sur tout le monde (recalcul
  intégral en mode espion, le mode le plus cher) ;
- ne l'exiger jamais laisse la dérive.

`verdict_cache.rendre_compte_du_cache()` **ne calcule rien de plus** : le run vient d'écrire de
toute façon, on lui demande si l'écriture a changé quelque chose (`git diff --quiet` sur un chemin,
~20 ms). Il rougit (`rc=6`, distinct de `1` = gisement) **exactement quand du code entre**, et se
tait le reste du temps.

Deux points tranchés à la mesure :

- **le critère est « diffère de l'INDEX », pas « de HEAD »**. Écrit avec `git status --porcelain`,
  le cran restait rouge **après `git add`** — donc inextinguible tant que l'auteur n'a pas commité.
  `git diff --quiet` applique au passage la normalisation `core.autocrlf`, que la comparaison
  d'octets aurait vue comme une modification.
- **le gisement portait bien sur les trois caches** : `probe_477r24r1` et `probe_477r25` ont rendu
  `rc=6` à leur première passe sous le nouveau cran. Les quatre caches sont régénérés dans ce
  commit.

---

## 3. `#526-r1` et `#526-r2` — l'inventaire, et la seule cadence que le merge autorise

**`#526-r1` : ni recalé, ni retiré — daté.** Le recaler remettrait l'horloge à l'heure sans traiter
la cause (rien n'oblige une PR à toucher la ligne du résidu qu'elle ferme) : il re-divergerait au
rythme mesuré, **23 % en quatre jours**. Le retirer casserait ~20 renvois qui pointent des sections
précises et détruirait sa **RE par entrée**, qui garde toute sa valeur. Il porte donc un bandeau
« INSTANTANÉ HISTORIQUE », avec le tableau des écarts mesurés — même traitement que `STATUS.md`.

**`#526-r2` : un cliquet à zéro est INTERDIT ici, et pas pour son coût.** Pour partir de zéro il
faudrait retirer les 19 lignes périmées d'un coup, soit une modification de **masse** de
`backlog.md` — que `CLAUDE.md` interdit, mesure à l'appui : **36 des 40 dernières PR mergées**
touchent ce fichier (90 % ; le suivant est à 15), donc une passe qui réécrit des lignes de tableau
partout entre en conflit avec **chaque** PR en vol, sur des lignes modifiées des deux côtés. Un
cliquet à seuil, lui, se dégraderait en silence.

D'où un signal **restitué**, pas un verdict, et servi **au bon moment** : `loop_status` tourne au
hook `Stop`, donc juste après un merge — quand il reste **une** ligne à retirer, pas dix-neuf.
C'est le « au fil de l'eau, jamais en masse » que la doctrine prescrit déjà pour ce fichier,
appliqué à la fraîcheur. Coût : **zéro appel supplémentaire** — la fenêtre PR est déjà lue pour la
livraison des branches (#479-r4) et le titre y est déjà demandé.

Le critère est le **titre d'une PR mergée**, l'un des deux signaux que #526 avait retenus (10/278,
dont 6 invisibles autrement). Les deux réfutés ne sont pas re-tentés : `git log` corps compris rend
187/278 et ne discrimine rien (un résidu est cité par le commit qui l'**ouvre**) ; la case-doc au
numéro exact rend 5/278.

**La dérive a DOUBLÉ en un jour** : 10 PERIME-CANDIDAT sur 278 le 2026-08-07, **19 sur 285** le
2026-08-08. Notre cadence de livraison l'alimente plus vite qu'aucune passe ne la résorbe — ce qui
est l'argument décisif pour un signal continu plutôt qu'une passe.

### Le signal a été livré MUET une première fois

`_SECTION_OUVERTE` était écrit `## Taches ouvertes`, sans son accent : il ne matchait rien, et le
poste rendait « PAS MESURÉ » en permanence. **C'est le tri-état qui l'a montré** — la cause était
nommée (`section introuvable`) là où une liste vide l'aurait caché. La borne suivante est le
**témoin non nul** de `probe_526r2_fraicheur_backlog.py` étape 1 : le signal doit être vu **tirer**
sur le vrai backlog avant qu'un silence soit cru.

Trois faux positifs gardés, dont celui que le résidu exigeait de préserver :

```
PR OUVERTE (pas mergee)          -> rien
id absent de la section ouverte  -> rien       (deja ferme, ou jamais ouvert)
COMPTEUR ROULANT (#217, #419-r1) -> rien       mis a jour a chaque livraison partielle,
                                               donc nomme sans etre ferme
gh muet                          -> PAS MESURE, jamais « 0 residu perime »
```

⚠ Une mutation de ce probe a d'abord été écrite **inopérante** : `"#217".rstrip("-r1") + "-r1"`
fabriquait `#217-r1`, qui n'existe pas — la mutation ne mordait sur rien et se lisait comme un
vert. Le roulant est désormais **dérivé** de la section ouverte, avec son propre témoin d'existence.

---

## 4. Ce qui n'est PAS couvert

- **Les 19 PERIME-CANDIDAT ne sont pas traités** — délibérément (cf. §3). Ils se retirent au fil
  de l'eau ; le signal est ce qui les rendra visibles un par un.
- **Le second signal de #526** (« id en position de sujet d'un commit postérieur au blame », 7/278,
  indépendant de `gh`) n'est **pas** câblé. Résidu `#526-r3`.
- **La fenêtre `gh` du hook est saturable** (limite 120) : une PR plus ancienne y est invisible.
  La portée le dit ; le signal ne conclut jamais au négatif. Résidu `#526-r3`.
- **L'inventaire n'est pas appariable** au backlog (0,3 %) : ses clés `R*`/`N*`/`O*` sont hors du
  corpus de `probe_468`, d'où quatre homonymies qu'aucun cliquet n'a vues. Résidu `#526-r3`.
- **Le coût réel du nouvel emplacement des poids** (#457-r10) n'est pas re-mesuré *après*
  déplacement : le chiffre `+99 %` compare deux répartitions sur les **mêmes** poids, ce qui est la
  question posée. Le mur d'une banque complète n'a pas été rejoué.
