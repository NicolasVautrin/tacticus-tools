# #978 — les cinq faces DÉCISION `NonComparable` Thousand Sons / Eldar

Port des cinq `EvaluateNonComparable` du lot, **confrontés live sur UN SEUL montage**.
Build `rnca9r7q6c`, board `MC1_67`, session 69.

| id | ability | porteur | utilité native | verdict |
|---|---|---|---|---|
| 1102 | `Doombolt` | `thousAhriman` | `Count(SurroundingEnemies(casterTile, ConfigConst(range)))` | **porté, confronté** |
| 1064 | `Loki_SwoopingHawk` | `eldarAutarch` | `#ennemis de la vague − 1` | **porté, confronté + oracle** |
| 1208 | `AetherStride` | `thousDaemonPrince` (MoW) | VETO booléen `psyker adjacent ET summon à portée` | **porté, confronté** |
| 1209 | `InfernalCannon` | `thousDaemonPrince` (MoW) | `1 + PV MAXIMUM de la cible ennemie` | **porté, confronté** |
| 1232 | `EmpyricAmbush` | `eldarLhykhis` | `Max(hi − PV COURANTS de la cible, 1)` | **porté, confronté** |

Base LUE dans `frida/classes.tsv` : **5/5** `NonComparablePlaybook\`1`. Leur `.ctor` décompilé NOMME
`ComparablePlaybook<...>..ctor` — corps gshared trivial dédupliqué, donc mislabelé. Reachability LUE
dans `metadata/active_playbook_builders.tsv` : **5/5** clés du dict `active`.

## 1. Ce que la RE a tranché, et qui ne se devine pas

**Le `statPart` est tout le discriminant, et il est SILENCIEUX.** Trois playbooks au squelette
identique lisent trois choses différentes au même emplacement :

| playbook | appel natif | `StatPart` |
|---|---|---|
| `InfernalCannon` (1209) | `GetStat(u, 5, **2**, 0)` | `Maximum` |
| `EmpyricAmbush` (1232) | `GetStat(t, 5, **0**, 0)` | `Current` |
| `MindControl` (1164) | `GetStat(t, 5, **0**, 0)` | `Current` |
| `ExemplarOfHate` (1140) | `GetStat(t, 5, **1**, 0)` | `CurrentPct` |

Confondre `Maximum` et `Current` entre 1209 et 1232 **inverserait** le classement des cibles — viser
le plus gros au lieu du plus blessé — sans lever la moindre erreur. Les noms sont lus dans
`frida/enums.tsv` (`IdunBattle.Entities.Enum.StatPart`), jamais déduits.

**Deux appels de vtable de CLASSE, appariés par le `global-metadata.dat`.** `Doombolt` appelle
`klass+0x2b8`, `SwoopingHawk` `klass+0x2a8` — deux slots ADJACENTS de `IdunBattle.DSL.TargetsSelector`
que l'ordre de `frida/methods.tsv` n'ordonne pas. `il2cpp_metadata.type_methods` les nomme :
**slot 23 = `Select`**, **slot 24 = `Count`**, recoupés par `ITargetsSelector` (slots 0 et 2) —
deux sources concordantes.

**Le piège #957 dans ses DEUX sens, sur la même tranche.**
* `Doombolt` : l'arbre est construit DANS la boucle mais **ancré sur le CASTER**
  (`SurroundingEnemies(caster@+0x48, casterTile@+0x50, range)`), donc `Count(entities)` rend la
  **même valeur pour toutes les cibles** — l'argmax est décidé par le keep-first de
  `Bucket.AddAction`. Le terme EST constant sur les cibles.
* `SwoopingHawk` : l'arbre dépend de `Target@+0x60`, donc il n'est **pas** constant.

L'ancrage se lit ; il ne se déduit pas de la position de la construction dans le corps.

**`GetUseProbability` est surchargée sur DEUX des cinq, avec des régimes OPPOSÉS.**
* `Doombolt` : `round(NrOfHitsFormula(<contexte ZÉRO>) / 9 · 100)` = un **pourcentage** (33 avec
  `nrOfHits = 3`). `BasePlaybook$$ShouldEvaluate` teste `prob >= 1` ⇒ **True déterministe**. Le
  `should_evaluate` par défaut du port est ici un mirror EXACT.
* `EmpyricAmbush` : `<Fix64 statics>+0x30`, que `Fix64$$.cctor` écrit comme
  `op_Division(0x100000000, 0x200000000)` = **0.5** ⇒ tirage RNG à 50 %, **non porté** (résidu
  `#978-r1`).

Deux surcharges du même getter, deux verdicts inverses : il faut lire la **valeur**, pas seulement
constater la surcharge.

**`SwoopingHawk` n'a PAS de `.cctor`, et sa borne vaut quand même 1.** Les quatre autres lisent
`MIN_UTILITY` dans un statique posé par un `.cctor` ; ici `Fix64.op_Implicit(1)` est calculé
**INLINE** avant le `Nullable<Fix64>..ctor` du Bucket. Le discriminant est le **site de lecture**,
pas la présence du `.cctor` — contraste avec `EarlyWarningOverridePlaybook`, dont le `.cctor` existe
et n'est lu par **aucun** des deux arguments du Bucket (`#433-r4-r2-r3`).

**`AetherStride` : les deux prédicats ne partagent PAS leur tuile.** Chacun balaie l'aire entière de
son côté et rend au premier succès. Exiger la MÊME tuile pour les deux serait plus strict que le
natif. Et le natif écrit `(a & b)` sur deux valeurs déjà produites, pas un `&&` court-circuité.

**Le couple 1208/1209 exerce réellement l'ordre des tiers.** `AetherStride` est tier `0`,
`InfernalCannon` tier `-100` (table mesurée `NATIVE_PRIORITY`, sweep #170) — même porteur. Le
générateur du tier 0 est donc évalué AVANT : quand le veto de 1208 passe, 1209 n'est jamais atteinte,
**par l'ordre des générateurs et non par comparaison d'utilités**. C'est le seul couple de la tranche
où les deux tiers coexistent sur une même unité, et la mesure le montre (voir §3).

## 2. Le montage — UN seul runner pour cinq items

Deux porteurs sont hors pool ; ils entrent par **co-injection**, en un seul appel :
`catalog_inject.write_augmented_seed_bc(out, ["thousDaemonPrince", "eldarLhykhis"])`. Deux
**factions différentes** dans le même seed, même équipe, même bataille — ni `BC.Units` ni
`BC.Abilities` ne sont partitionnés par faction. Les deux autres (`thousAhriman`, `eldarAutarch`)
sont déjà au pool.

**Trois verrous de montage, tous silencieux, tous mesurés :**

1. **`MachineOfWarAmmo`.** `AetherStride` a `munitionsCost = 1` et le seed BC porte un stock de `0` :
   `ActiveAbility$$get_CanCurrentlyBeUsed` teste `!AmmoCost.HasValue || HasEnoughAmmo`, donc le
   **natif lui-même** refuse, et le stock n'est jamais incrémenté par une opération native. Sans le
   patch de `BC.Player.Players[].MachineOfWarAmmo`, l'ability est **structurellement incastable** —
   aucun nombre de tours n'y change rien. Contre-épreuve du patch : `hasAmmo` passe de `false` à
   `true`.
2. **`initialCooldownTurns = 1`** sur 1208/1209/1232. Le champ `cooldown` du canal EST
   `RemainingCooldownTurns` (et non le cooldown nominal — corrigé par #579-r1), donc
   `can_currently_be_used` les refuse au tour 1. Il faut **avancer d'un round**.
3. **`applyAction` attend `kind: "endturn"`**, en minuscules. `"endTurn"` rend `{}` **sans erreur**,
   et le tour adverse passe par `autoPlayRunner`, pas par un `aiTurn` inexistant. Premier jet :
   `turn` figé à 3 sur 6 rounds demandés, et le probe déclarait alors « régime non atteint » — une
   mutation NON MORDANTE prise pour une mesure.

⚠ **Et le témoin de ce troisième verrou était lui aussi faux.** Contrôler `dv.turn` accusait
« FIGE » alors que les trois cooldowns retombaient bel et bien de `1` à `0`. Le probe mesure
désormais **exactement la grandeur que le bloc doit changer** — les cooldowns — et non un proxy.

⚠ **Ne PAS faire jouer l'IA adverse pour avancer** : `autoPlayRunner` lâche cinq ennemis sur trois
héros et la bataille se termine (`stage Finished`) avant la mesure. Un `endturn` par camp avance le
compteur sans qu'aucune unité n'agisse, et préserve la configuration placée.

## 3. La confrontation — `probe_978_thousandsons_eldar_decision.py`

**Géométrie DRIVÉE, jamais subie.** Aux positions de spawn de `MC1_67` les ennemis sont à 7-8 hexes :
`Doombolt` (rayon 2) et `SwoopingHawk` (vague de 3) rendent `no-op certain`, ce qui est la réponse
JUSTE du natif. Le probe déplace donc les **ennemis** — jamais les casters, dont le déplacement
armerait `CasterHasNotMoved` et confondrait un refus de ciblage avec un port muet. Les positions
sont **dérivées** (`hexgeo.disk` pour le rayon, `battle_query.get_tiles_behind` pour la vague) et
l'attendu est écrit **avant** la mesure :

```
Doombolt      : (0,1) et (2,0) dans disk((1,0), range=2)      -> util 2
SwoopingHawk  : get_tiles_behind((0,0), (0,1), 3) = [(0,1),(0,2),(0,3)] -> n=3, util = n-1 = 2
```

**Résultats (rc 0) :**

| id | port | contre-épreuve (registre amputé) | mordante |
|---|---|---|---|
| 1102 | `{target 77, to None, util **2.0**}` | `{target 79, to (1,3), util 78.2}` | oui |
| 1064 | `{target 77, to None, util **2.0**}` | `{target 79, ability **69**, util 63.1}` | oui |
| 1209 | `{target 13, to None, util **11045.0**}` | `{kind finish}` | oui |
| 1232 | `{target 79, to None, util **3012.0**}` | `{target 79, to (2,3), ability 69, util 63.3}` | oui |
| 1208 | voir ci-dessous | | oui |

`11045 = 1 + 11044` = exactement les PV **MAXIMUM** de `custoVexilusPraetor` — le mirror de
`GetStat(u, Health, Maximum)`, au point près.

**ORACLE NATIF** (`aiStepDryRun`) :
`ActiveAbilityMessage{casterId: 90, targetId: 77, abilityType: 1064}` — le jeu choisit
**exactement** ce que le port propose pour `eldarAutarch` : même caster, même cible, même ability.

⚠ **`MORDANT` = « la décision CHANGE », pas « l'ability disparaît ».** Trois des cinq abilities sont
AUSSI des attaques : amputer leur playbook NonComparable les fait retomber sur le
`ComparableAbilityGenerator`, qui les repropose — avec une autre cible, une autre position et une
autre utilité. Le premier jet du probe exigeait la disparition et déclarait donc « non mordante »
une mutation qui mord franchement (1102 : `{77, None, 2.0}` → `{79, (1,3), 78.2}`).

### 1208 — un refus ne confronte RIEN, il faut forcer la branche positive

Dans la configuration ci-dessus, `AetherStridePlaybook` rend `[]`. Mesure **par étage** :

```
aires NON VIDES            : 38 / 38     <- la feuille n'est PAS inerte
predicat SUMMON-EN-PORTEE  : 23 / 38
predicat PSYKER            :  0 / 38     <- ce qui bloque
```

Le veto est **juste** (l'unique allié psyker, `thousAhriman` en (1,0), a ses trois voisins occupés,
donc aucune empreinte valide ne le touche) — mais un refus est compatible avec une feuille inerte
**comme** avec un mirror exact. L'étape 2b **déplace donc le psyker** vers une destination
**calculée** (`voisin libre d'une tuile d'une aire éligible`) :

```
ancre (0,4) -> aire touchee (0,4) -> psyker envoye en (0,5)   [position ATTEINTE verifiee]
predicat PSYKER : 0 -> 5 cibles
port   : {target 16, ability 1208, to None, util 1.0}
ampute : {target 13, ability 1209, util 11045.0}
```

⇒ 1208 est proposée, à l'utilité **1.0** que le corps natif est seul à pouvoir émettre, **et elle
prime sur 1209** — la bascule tier 0 / tier -100 est donc exercée pour de vrai, pas déduite de la
table.

## 4. Ce qui n'est PAS couvert

* **Le tirage RNG à 50 % d'`EmpyricAmbush`** (`GetUseProbability` = `Fix64(0.5)`) : le moteur porté
  est déterministe, `should_evaluate` rend `True` et l'ability est TOUJOURS évaluée là où le natif
  la saute une fois sur deux. Écart assumé, identique à `BlackRage` (0.4) et `ItItches`. Résidu
  **`#978-r1`**.
* **`Damageable`** (Doombolt) n'a pas de canal propre dans `NCContext` : `ctx.epos` est utilisé à sa
  place. L'écart ne peut que SUR-compter.
* **`Unobscured` au-delà de `dist == 2`** : `is_target_tile_obscured` ne répond que pour `dist == 2`,
  le seul régime que le natif exerce avec `range = 2`. Borne supérieure si un build montait `range`.
* **`GetHighestMaxHealthFromNoneBossConfig`** est mirroré sur `obs_units`, qui **exclut les MoW** et
  les unités configurées non spawnées. `hi` est donc sous-estimé ; comme il translate toutes les
  utilités du même montant, le **classement** est inchangé tant que le plancher `1` ne mord pas.
* **Le balayage de POSITION** de 1102/1064 s'appuie sur `cast_positions.positions_castables` : canal
  `castFromTiles` muet ⇒ ensemble vide ⇒ seule l'origine est évaluée. Dégradation conservatrice
  (jamais un cast illégal proposé), mais l'optimisation de position n'est alors pas exercée. Les
  deux mesures ci-dessus rendent `to: None`, donc ce volet reste **non confronté**.

## 5. Effet de bord : `#970-r5` est débloqué

Ce résidu écrivait : « Le substrat `ThreeTileUnitSpawnShape` EXISTE (`engine/services/spawn_tile_shape.py`)
mais exige un `board`, absent de `NCContext` : **c'est l'adaptateur à écrire.** »

Cet adaptateur est écrit — `daemon_prince._CtxBoard` — et **mesuré** (38/38 aires non vides sur un
contexte MACHINE). Il ne porte aucune géométrie : il republie sous les quatre noms attendus
(`tile_at`/`id_at`/`neighbours`/`elevation`) des canaux que `NCContext` porte déjà, et un canal muet
y rend `None`/`[]` plutôt qu'une aire inventée. `1158 DutyEternal` n'attend donc plus son étage.
