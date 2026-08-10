# #433-r3-r3 — le balayage des slots cités EXISTAIT ; ce qui manquait était sa PORTÉE

**Livré le 2026-08-10** (build `rnca9r7q6c`). Probe : `scripts/python/probe_433_r3_r3_slots_autre_casse.py`.

## 1. Les deux prémisses de la ligne de backlog étaient PÉRIMÉES

La ligne demandait « un balayage des slots cités en commentaire, au changement de build » et nommait
`docs/rl/case-243-targeting-adjacency.md` comme portant « encore la table datée ». Les deux sont fausses
au 2026-08-10 :

1. **Le balayage existe et il est VERT.** `probe_477r25_slots_autres_interfaces.py` récolte les couples
   `(interface, slot, nom)` sur tout le dépôt (périmètre dérivé de `git ls-files`) et les confronte à
   `data/symbols/<build>/metadata/interface_slots.tsv`. Joué : **0 citation au SLOT/NOM faux**,
   **0 arité fausse**, sur 18 interfaces / 513 slots.
2. **`case-243` ne porte plus de table datée.** Relue ligne à ligne : `0x60/0x61/0x62`
   (`AreEntitiesAdjacent`), `0x7d…0x80` (`GetAdjacentEnemies`), `0x52/0x53` (`GetFreeAdjacentTiles`) —
   les quatre concordent avec le metadata du build courant.

## 2. Ce qui restait : un ANGLE MORT que le balayage nomme lui-même

`probe_477r25.RE_SLOT` est **sensible à la casse**. Son propre recenseur le dit et le chiffre
(`_RE_SLOT_AUTRE_CASSE`, section « PORTEE DE LA MESURE ») : **197 lignes** écrivent `Slot`/`SLOT` et
n'entrent dans **aucune** de ses causes — elles sont *invisibles*, pas *écartées*. Chiffrer un angle
mort ne le referme pas : une partition exacte d'un ensemble incomplet se lit comme exhaustive.

**Méthode** — le même appareil, sur un texte normalisé :

1. périmètre et tables **dérivés du module** #477-r25 (pas de liste blanche recopiée : élargir son
   périmètre élargit celui-ci) ;
2. par fichier, sa récolte est rejouée **deux fois** — texte tel quel (référence), puis texte dont les
   seules occurrences de `slot` à autre casse sont abaissées. Rien d'autre n'est touché ;
3. les citations **nouvelles** sont confrontées aux tables.

⚠ Le probe appelle `_contribution` (la fonction pure par fichier), **jamais** `recolter` : faire entrer
un texte muté dans le cache versionné de #477-r25 y laisserait des verdicts qui ne décrivent aucun
fichier du dépôt.

## 3. Résultat : 8 citations rendues visibles, dont UNE fausse — et c'était bien un glissement de build

`docs/rl/playbook/playbooks.md` (section « MAJ #116 — HammerOfWrath ») attribuait le slot `0x4e` = 78
d'`IBattleQuery` à `BattleQuery.GetAdjacentTiles` <!-- [slot-attribution:refute] : la phrase DÉCRIT
la faute corrigée, elle ne l'affirme pas — sans ce marqueur, `probe_477r25` apparie le couple et
rougit sur la fiche qui répare, ce qui rendrait `master` rouge au merge -->. La fiche **déclare son
build** (`gqfc5mff6c`) : la citation y était juste. Sur `rnca9r7q6c` elle a **glissé d'un cran** —
exactement la forme de décalage que #433-r3-r3 décrivait pour `targeting.py`.

| slot | `rnca9r7q6c` (metadata) | lambda du décorateur |
|---|---|---|
| 78 (`0x4e`) | `GetMinimumTiles180BehindFromTile` / 2 | `…u003Cu003Ec__DisplayClass98_0$$u003CGetMinimumTiles180BehindFromTileu003Eb__0` |
| **79 (`0x4f`)** | **`GetAdjacentTiles` / 4** | `…u003Cu003Ec__DisplayClass99_0$$u003CGetAdjacentTilesu003Eb__0` |
| 80 (`0x50`) | `IterateAdjacentTiles` / 4 | `…DisplayClass100_0$$u003CIterateAdjacentTilesu003Eb__0` |
| 81 (`0x51`) | `GetAdjacentTiles` / 4 | `…DisplayClass101_0$$u003CGetAdjacentTilesu003Eb__0` |
| 82/83 | `GetFreeAdjacentTiles` / 1 | `…DisplayClass102_0` / `103_0` |
| 84 (`0x54`) | `GetTilesBehind` / 5 | `…DisplayClass104_0$$u003CGetTilesBehindu003Eb__0` |

**Deux sources indépendantes**, plus une corroboration au call-site :
`IdunBattle.AI.Playbook.Loki.HammerOfWrathPlaybook$$EvaluateNonComparable` et
`IdunBattle.Core.Services.MovementQuery$$IsAdjacent` invoquent **tous deux** `0x4f`. Le NUMÉRO du
`DisplayClass` n'est pas le slot (décalage −20 sur cette plage) — c'est l'**ordre** qui apparie, et il
est préservé.

**Second glissement, dans le même paragraphe** : le prédicat de tuile libre n'est plus
`TileExtensions$$CanAddUnit` — ce symbole est **ABSENT** de `rnca9r7q6c`. Le call-site invoque
`IdunBattle.Entities.TileExtensions$$IsFreeTile`. Le nom `CanAddUnit` n'y vit plus que côté DSL
(`IdunBattleLogic.Entities.DSLSelectors$$CanAddUnit`,
`IdunBattle.Entities.Selectors.CanAddUnitTileSelector$$Select`,
`IdunBattleLogic.Entities.DSLTriggers$$IsCanAddUnit`) et sous `TileExtensions$$CanAddUnitFromAbility`.

Les deux sont corrigés dans `playbooks.md`, avec l'avertissement de build en tête de section.

## 4. La contre-épreuve a été INERTE deux fois — et c'est la partie instructive

`--mutate` injecte une citation fabriquée en `Slot` (donc invisible sans abaissement) dont le nom est
celui du slot **suivant**. Elle a d'abord été verte deux fois de suite, pour deux causes différentes :

1. **Mutant injecté APRÈS l'abaissement** : il gardait sa majuscule et restait invisible des *deux*
   côtés. La contre-épreuve passait au vert et se lisait comme une preuve, sans rien exercer.
2. **Mutant tombant sur deux SURCHARGES HOMONYMES consécutives.** `IBattleQuery` en aligne beaucoup
   (96/97/98 = `AreEntitiesAdjacent`, 122/123/124 = `GetAdjacentUnits`) : décaler d'un cran y produit un
   couple **juste**. Le tirage « milieu de table » tombait exactement dessus. Le mutant contraint
   désormais `table[s][0] != table[s+1][0]`, et l'absence d'une telle paire est un `SystemExit`, pas un
   vert.

Rouge obtenu, verbatim :

```
[IBattleQuery] slot 0x6f : le site nomme GetAverageDistance, le metadata dit GetMinDistance ;
GetAverageDistance est aux slots 0x70
```

## 5. Ce qui n'est PAS couvert

- **`#433-r3-r3-r2`** — les **301** lignes classées `nom_ecarte_par_un_cran` par la ventilation de
  #477-r25 : un slot chiffré et un nom de l'interface appariée coexistent dans la fenêtre, mais un cran
  conservateur écarte le couple. C'est son plus gros poste (301 sur 816), et il est invisible aux deux
  cliquets — ni confronté, ni compté comme faute.
- Les **65** `nom_seul_sans_numero` (slot désigné par un nom, sans numéro) : aucun couple à confronter,
  mais le nom est une attestation que ce cliquet ne garde pas.
- Les VA **absolues** encore écrites dans `playbooks.md` (fiche historique) : hors périmètre de ce
  résidu, qui porte sur la numérotation de **slots**.
- Ce probe mesure le **corpus**, pas le **code exécutable** : une citation juste dans un commentaire ne
  dit rien de ce que le port appelle réellement.
