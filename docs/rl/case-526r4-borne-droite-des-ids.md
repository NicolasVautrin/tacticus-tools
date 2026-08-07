# #526-r4 — l'id d'un résidu n'a pas de borne droite, et l'allowlist masquait le vrai signal

`loop_status._residus_livres` extrayait les ids du **titre d'une PR mergée** par
`#\d+(?:-r\d+)+`, sans borne droite. Sur `#462-r4b-r3-r1` le `+` s'arrête devant le `b` et rend
`#462-r4` — un id qui **existe** et qui est **ouvert**. C'est la cause du faux positif
`#462-r4 (PR #724)` remonté par le hook `Stop` le 2026-08-08.

## 1. Ce qui a été mesuré

Fenêtre **200** dernières PR mergées : **24** extractions tronquées, 3 familles
(`#462-r4` ×14, `#419-r1` ×9, `#446-r3` ×1). Effet sur le signal : **18** émis, dont **14**
étaient la troncature — soit **78 % de bruit**.

Historique **complet** (799 PR mergées) : **88** troncatures, **10** familles.

⚠ **La fenêtre courte ment sur l'allowlist, et c'est le résultat le plus important.**
`RESIDUS_ROULANTS = ("#217", "#419-r1")` : sur 200 PR, `#419-r1` est nommé **exactement 0**
fois et tronqué 9 fois — on conclurait que l'entrée ne tait qu'une troncature. Sur 799 PR, elle
masque **9 occurrences EXACTES** (`#419-r1 tranche 14 : …`, PR #541, #523, #518, #514, #495,
#493, #492, #487, #485) pour 28 troncatures : **l'entrée est pleinement justifiée**. Un compte
tiré d'une fenêtre non saturée reste un compte *sur cette fenêtre*.

## 2. La borne ne répare pas — c'est la LARGEUR qui répare

Grammaire élargie : `#[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+(?![-\w])`. Sous elle, `-r4b` est un
segment ordinaire, donc la troncature se dissout d'elle-même. Ce que la borne garde *encore*,
c'est le suffixe **collé hors classe** (`#116-e_bis` ne doit pas rendre `#116-e`). Les deux
crans sont éprouvés **séparément** (`probe_526r2` étape 5 (a1) et (a2)) pour que l'un ne passe
pas pour la cause du vert de l'autre.

**Mesure de l'élargissement** : **212 des 619** premières cellules de la section ouverte étaient
hors de l'ancienne grammaire — familles entières (`#419-r1-tr14-…`, `#462-r4b-…`, `#350-r3a`,
`#446-r3b`) et racines non numériques (`#BF-chance`, `#PAI-c`, `#haze-ord`). Résidus ouverts vus :
**191 → 278**. Signal réel gagné : **`#175-r`** (livré par la PR #825, toujours ouvert), que rien
ne pouvait voir.

## 3. Trois défauts trouvés en réparant, tous de la même famille

- **`startswith` bâillonnait les DESCENDANTS.** `rid.startswith(RESIDUS_ROULANTS)` silencie
  **31 résidus ouverts** sous `#419-r1`. Chacun a sa propre ligne et son propre cycle de vie :
  le caractère roulant du parent ne se transmet pas. Inoffensif tant que la grammaire ne savait
  pas produire ces ids — un bâillon dès qu'elle le sait. → appariement **exact**.
- **`#217` est structurellement INERTE.** C'est une racine nue, et `_RE_ID_TITRE` exige au moins
  un segment (c'est ce qui le sépare d'un numéro de PR : un titre cite couramment `#832`, id de
  racine parfaitement valide). Aucun titre ne peut la produire. L'entrée est **conservée** et
  **recensée** : `probe_526r2` imprime `RESIDUS_ROULANTS[#217] est INERTE : …` à chaque passe et
  exige qu'au moins une entrée reste effective.
- **`probe_526r2 --etat` rendait un ZÉRO FAUX.** `livraison.lire_fenetre_pr` ne demandait pas
  `title` à `gh`, et `_titres_mergees` rendait `[]` en se justifiant « le signal se tait, il ne
  se trompe pas ». Il se trompait : l'appelant imprimait `0 residu(s) … (aucun -- mesure, pas
  suppose)`. Mesuré le même jour, même dépôt : **voie manuelle 0, voie du hook 4**. Corrigé des
  deux côtés — `title` demandé, et une fenêtre sans titre rend **NON MESURÉ avec sa cause**.

## 4. Ce qui n'est PAS concerné, vérifié

- Les deux autres extractions d'id de `loop_status.py` sont ancrées par `\s*\|` (1re cellule) :
  hors sujet.
- **`probe_468` (les deux modes) ne porte pas le défaut** — lu *et* mesuré :
  `RE_TOKEN_LARGE = #[0-9a-zA-Z][0-9a-zA-Z_-]*` et `RE_OCCURRENCE` consomment l'id **entier**
  (`#462-r4b-r3-r1` → `#462-r4b-r3-r1`). Aucun ancêtre n'y est fabriqué.

## 5. Ce qui reste ouvert

- La **racine nue n'est jamais signalée**, par exigence (anti-collision avec un numéro de PR).
  Borne assumée et nommée dans `_RE_ID_TITRE`, pas découverte plus tard.
- Le foyer de la grammaire est désormais **unique** (`loop_status._residus_ouverts`,
  `_RE_ID_DEFINI`, `_RE_ID_TITRE`) : `probe_526r2` l'**appelle** au lieu de la recopier — un
  cran qui juge une règle qu'il a recopiée ne juge que sa copie.

**Cliquet** : `python scripts/python/probe_526r2_fraicheur_backlog.py` — étape 5, **5 mutations
vues ROUGE** (grammaire d'origine, borne, largeur, préfixe, accent) + le recensement des entrées
inertes. `--etat` restitue les deux colonnes (signalés / écartés comme roulants).
