# #536 — Les trois rouges `genesSmnDecoy` : le contact ne se SUBIT pas, et l'approche ratée refusait le seul geste qui marche

**Statut : FERMÉ (2026-08-07).** Trois fichiers live de la famille `#419-r1-tr14-r5-r2-r1-r2-r1*`
tombaient en ERROR de MONTAGE sur `master` (`d57293b9`), leurs résidus parents étant tous marqués
`FERME 2026-08-04` — donc sans propriétaire. Aucun `engine/**` n'est touché : port et natif sont
d'accord sur les trois, ils n'étaient simplement jamais interrogés.

| fichier | `master` `d57293b9` | après |
|---|---|---|
| `test_419r1tr14r5r2r1r2r1_normal_attack_dynamic_rule_live.py` | 3 passed / **6 errors** | **9 passed** |
| `test_419r1tr14r5r2r1r2r1r1_only_adjacent_live.py` | 5 passed / **7 errors** | **12 passed** |
| `test_419r1tr14r5r2r1r2r1r1r4_melee_clamps_live.py` | 2 passed / **6 errors** | **8 passed** |

Message des trois : « aucun `genesSmnDecoy` vivant ADJACENT a un ennemi » / « aucun `genesSmnDecoy`
sous clamp de melee ».

## 1. Ce que le montage croyait, et ce que la mesure dit

L'en-tête de `probe_419r1tr14r5r2r1r2r1_normal_attack_dynamic_rule.py` écrivait : « on amène
d'abord `genesPrimus` au contact d'un ennemi, on caste ensuite. **Les summons apparaissent autour du
caster, donc au contact.** » La seconde phrase est fausse, et c'est la seule qui portait le montage.

Mesure (`MC1_67`/`4192`, ancre en `(5, 7)`, ennemis en `(6, 7)` / `(6, 8)` / `(5, 8)`) : les trois
`genesSmnDecoy` tombent en `(4, 6)`, `(3, 6)` et `(1, 1)` — **`d = 2`, `3` et `9`**. Aucun n'est
adjacent. Les `genesSmnNeophyte`, eux, en ont un à `d = 1` : le **TÉMOIN était monté et le
DISCRIMINANT non**, ce qui est la pire des deux moitiés — un montage à moitié posé n'aurait rien
prouvé s'il avait passé.

## 2. Trois faits qui fixent la forme du remède, et le troisième renverse une note existante

1. **Les summons ne sont pas activables.** `aiMovableTiles` les publie avec `tiles = []` (mesuré sur
   les trois decoys) — c'est #291 : le natif termine le tour de toute unité qui apparaît pendant le
   tour de son propriétaire. On ne peut pas rapprocher le summon.
2. **Un ennemi n'est activable que quand SON camp a la main.** Pendant notre tour, `aiMovableTiles`
   ne publie que nos unités (mesuré : `[83, 85, 109, 114, 119, 124, 126, 137, 141, 144, 147, 155]`,
   aucun id adverse). Un `move` sur un ennemi n'a alors aucune tuile légale.
3. **C'est le RETOUR de la main à NOTRE camp qui détruit la géométrie, pas le passage à
   l'adversaire.** Mesuré : après `endturn` (`player 3 -> 4`) les trois decoys sont **intacts**, aux
   mêmes tuiles ; après le `endturn` suivant (`4 -> 3`), `PlayAutomaticUnits` joue les summons au
   turn-start (trait `Summon`), les huit neophytes se déplacent, un decoy est remplacé, et
   **l'ennemi qu'on venait d'amener au contact est mort**.

Le point 3 renverse l'avertissement que portait `forcer_contact` dans
`probe_419r1tr14r5r2r1r2r1r1r4_melee_clamp_live.py` : « ON NE PASSE PAS PAR `_step_toward` : son
`_wait_movable` enchaîne des `endturn` […] les `genesSmnDecoy` sont ÉPHÉMÈRES et n'y survivent
pas ». Le fait observé était réel, la conclusion tirée était l'inverse de la bonne : en refusant
*tout* `endturn`, cette implantation ne bougeait l'ennemi que pendant NOTRE tour — donc, par le
point 2, jamais. **Sa propre trace le disait** (« u%d n'est pas activable sans consommer un tour --
arrêt ») sans que personne y lise une impossibilité structurelle.

## 3. Le remède — `P583.forcer_contact`, foyer unique des trois fichiers

Rendre la main à l'adversaire, amener un ennemi à `d = 1` d'un summon de chaque `vis` demandé, et
**y rester** : la mesure se fait pendant le tour adverse. `abilityReason` y répond normalement — ce
n'est pas une action, c'est une requête d'oracle, et elle n'exige pas que le caster soit activable.

Témoin non nul, mesuré après le correctif (`probe_…dynamic_rule.py`, 6 lignes) :

```
  --- CASTER SANS ARME  u137 genesSmnDecoy
      79    tauMarksman      d=1   natif=0x2   portApres=0x2   portAvant=0x0   <- DISCRIMINANT
  --- CASTER ARME       u109 genesSmnNeophyte
      79    tauMarksman      d=1   natif=0x0   portApres=0x0   portAvant=0x0
  VERDICT (refuse/accepte) : accord APRES 6 | accord AVANT 5 | gagnees 1 | PERDUES 0
```

Un seul `move` a suffi (`u79` de `(6, 7)` vers `(5, 6)`, `d 2 -> 1`). Le témoin ARMÉ reste à `0x0`
sur la même cible et à la même distance : c'est l'absence d'arme qui déplace le verdict, pas la
géométrie.

## 4. Généralisation — TROIS couples `(board, seed)`, dont celui qui échouait

`probe_…dynamic_rule.py` rejoué hors de son couple nominal :

| board / seed | lignes | accord APRÈS | gagnées (témoin) | PERDUES |
|---|---|---|---|---|
| `MC1_67` / 4192 (nominal) | 6 | 6 | **1** | 0 |
| `C4_09` / 31337 | 4 | 4 | **1** | 0 |
| `C3_01` / 999 | 6 | 6 | **3** | 0 |

`C4_09`/31337 est précisément le couple que l'ancien `forcer_contact` citait comme « rend 0 clampé »
pour justifier son existence — il passe désormais. Sur `C3_01`/999 le decoy finit adjacent aux
**trois** ennemis : le discriminant y mord sur les trois lignes, le témoin armé sur aucune.

## 5. Ce qui n'est PAS couvert

- **Le montage reste dépendant du fait qu'un ennemi PEUT rejoindre un decoy dans son budget de
  mouvement.** `forcer_contact` itère (8 tours au plus) et rend la distance minimale atteinte ; s'il
  ne descend pas à 1, le `MontageError` d'origine tombe — le montage échoue en le DISANT, il ne part
  pas en skip vert.
- **La mesure se fait maintenant pendant le tour ADVERSE.** `abilityReason` y répond (mesuré, trois
  couples), mais aucune assertion ne garde ce fait : si un jour le natif y court-circuitait sur
  `CanCurrentlyBeUsed`, les lignes deviendraient uniformes et c'est le contrôle de non-dégénérescence
  (`gagnees > 0`) qui rougirait — pas un message qui nommerait la cause.
- **La cause du placement des decoys n'est pas RE-lue.** On mesure qu'ils ne spawnent pas au contact ;
  on ne lit pas au décompilé la règle de choix de tuile de `CultDemagogue` (famille
  `SortTilesByUtility`, cf. #165). Rien dans cette tranche n'en dépend.
