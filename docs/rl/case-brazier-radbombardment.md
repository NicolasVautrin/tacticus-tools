# Face COMBAT de BrazierOfHolyFire (1041) et RadBombardment (1116)

> **Verdict** : les deux abilities sont PORTÉES et confrontées au live sur deux géométries chacune.
> Deux gaps ADJACENTS (étages partagés, indépendants de ces abilities) ont été mesurés et chiffrés en
> route ; ils sont au backlog, pas corrigés ici.

## 1. Le trou, mesuré AVANT d'écrire une ligne

« NO-OP » dans l'audit veut dire « absent du registre COMBAT », **pas** « inerte » — contre-exemple
avéré : `FrenziedFiring`, classée NO-OP alors que ses coups traversaient déjà la formule partagée. On
a donc monté le cast et lu ce que faisait le moteur (`probe_brazier_radbombardment.py`, runner
MC1_67, seed 777) :

| ability | LIVE | PORT (avant) |
|---|---|---|
| 1041 BrazierOfHolyFire | 2 coups `[1899, 1599]` sur la cible + `Fire` (5) sur sa tuile | `ported:false`, **0 dégât, aucune erreur** |
| 1116 RadBombardment | 1 coup `3389` + `Pinned` (1065) sur la cible + `Contaminated` (1244) sur 2 tuiles | `ported:false`, **0 dégât, aucune erreur** |

Le trou était bien « absent du registre » : divergence d'état **silencieuse**, exactement le profil
qu'un entraînement RL irait exploiter.

## 2. BrazierOfHolyFire (1041, `adeptCanoness` — Canoness, HERO Sisterhood)

`IdunBattleLogic.Entities.Abilities.Active.Loki.BrazierOfHolyFireAbility$$ExecuteBehaviour`
(`AActiveAbility.Execute` PLAIN, aucun `ExecuteAtomic`) :

```
dmg    = MinMaxDamage(this, entities)                                    # minDmg(0xc)/maxDmg(0xd)
prof   = GetDamageProfile(config@0x60, 0)                                # constants.damageProfile = Flame
hits   = GetNumberOfHits(target@0x178)
attack = AttackWithAttackDamage(caster@0x160, target@0x178, dmg, prof, hits,
                                AbilityOrEffect(this+0x10 = 0x411 = 1041), <options ZERO>)
fire   = AddEffect(5 = Fire, AbilityStateReference, TargetTiles@0x190)   # surcharge 4-ARGS
dae    = UnitsWithTrait(SurroundingUnits(target@0x178, ConfigConst(0x44), 1, 1, 3), 0x3fb, 3)
mark   = AddEffect(0x433 = 1075, AbilityStateReference, source = caster@0x160, dae, TurnsFromRounds(2))
Execute((attack & fire) & mark)
```

`…$$GetNumberOfHits(u)` = `ConditionalAmount(HasTrait(u, 0x3fb = 1019 Daemon), ConfigConst(0x32),
ConfigConst(0x2f))`, appelé avec `target@0x178` → **la cible Daemon prend `nrOfHits_2` coups, sinon
`nrOfHits`**. `…$$GetEffectTargets` expose le MÊME `dae` (confirme la lecture du sélecteur).

### Clés de config : tranchées par ÉLIMINATION, pas devinées

Le dump `AbilityVariableType` de `data/symbols/<build>/frida/enums.tsv` **ne contient NI `nrOfHits_2`
NI `range_2`** (158 entrées, une seule manquante à l'index 132) — il est incomplet sur cette enum, on
ne s'appuie donc PAS dessus. La config 1041 n'a que 5 constantes (`damageProfile`, `range`, `range_2`,
`nrOfHits`, `nrOfHits_2`) et `IdunBattle.Configuration.AbilityConfiguration$$GetStringConstant` **lève**
si la clé manque → les trois index lus (0x2f, 0x32, 0x44) sont forcément 3 de ces 5 noms.

- `0x2f = nrOfHits` — ancré par `IdunBattleLogic.Entities.Abilities.Active.Loki.ArmoriumCherubAbility$$GetHits`
  (corps foldé réutilisé par RadBombardment, dont la config n'a QUE `nrOfHits`).
- `0x32 = nrOfHits_2` — l'autre branche du `ConditionalAmount` de coups.
- `0x44 = range_2` — **nommé par l'i2** : « ALL Daemons within `{[range_2]}` hexes of the target ».
  (`range` et `range_2` valent 2 tous les deux → le choix est numériquement inerte, mais on lit le bon nom.)

### Points de fidélité

- **Famille ATTACK** : le call-site appelle `IdunBattleLogic.Entities.DSLFactory$$AttackWithAttackDamage`
  (surcharge partagée avec SentinelDirectives/ScythingTalons/Executioner ; vérifié par `list_xrefs`,
  ABSENT des xrefs d'`AttackWithAbilityDamage`) → `native_factory="attack"` = 2 tirages/coup à cc=0.
- **`SurroundingUnits(…, 1, 1, 3)`** : le 5ᵉ argument (`param_5 = 1`) est `includeCenter` →
  **la cible elle-même compte** si elle est Daemon. Aucun filtre d'équipe (pas de `Enemies`) → les
  Daemons ALLIÉS sont marqués aussi, ce que l'i2 dit mot pour mot (« ALL Daemons »).
- **Le FEU et sa SOURCE** : la surcharge `AddEffect` **4-args** passe littéralement `0` comme sélecteur
  SOURCE. `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$Execute` fait alors
  `lVar14 = <cible courante>; if (<résultat du sélecteur source>) lVar14 = <ce résultat>;` →
  **sélecteur source absent ⇒ la source EST la cible**, pas le caster. D'où le paramètre
  `AddEffect(source_from_target=True)` ajouté (défaut `False` = comportement historique inchangé).
- **Le volet FEU est un no-op en pratique, et c'est FIDÈLE** : le profil `Flame` porte le DamageTrait
  `OnFire`, dont le canal after-hit (`OnFireDamageAbility`) pose déjà `Fire` sur la tuile au 1ᵉʳ coup.
  L'`AddEffect` explicite qui suit tombe donc sur le gate « déjà présent » d'`AddEffectOperation` —
  exactement comme le natif. Mesuré : `placed:false` côté port, tuile en feu des DEUX côtés.
- **PHASE 2 non portée (documentée, pas inventée)** : `BrazierOfHolyFire_ExtraDmgEffect` (1075) =
  `ForPercentIncrease(get_OwnerIsTarget, ConditionalAmount(HasTrait(target@0x178, 0x19 = 25 Immune),
  ConfigVar(0x48 = extraDmgPct_2), ConfigVar(10 = extraDmgPct)))`. Le CAST pose l'effet ; la
  CONSOMMATION du +X% encaissé est un port d'effet séparé.

## 3. RadBombardment (1116, `admecDominus` — Dominus, HERO AdeptusMechanicus)

Cast **TILE-TARGET** : `…$$.ctor` passe `TargetingRange.CustomRange(1)` → la cible du message est une
tuile ADJACENTE au caster = l'**AIM** (la direction du tir). Confirmé live (`abilityTargets` 1116 :
`kind="tile"`, `fromHere` = les voisines libres du caster).

```
tiles  = GetAffectedTiles()
units  = Units(tiles, 0, 3)
attack = AttackWithAbilityDamage(caster@0x160, units, MinMaxDamage, DamageProfileFromConfig,
                                 Get(ArmoriumCherubAbility$$GetHits() = ConfigConst(0x2f)),
                                 AbilityOrEffect(this+0x10 = 0x45c = 1116))
pin    = AddEffect(0x429 = 1065 Pinned, stateRef, source = caster@0x160, units, <opts ZERO>)
contam = AddEffect(0x4dc = 1244 Contaminated, stateRef, tiles)           # surcharge 4-ARGS
Execute((attack + pin) + contam)

GetAffectedTiles() = SortReverse(TilesBehindInLine(CasterTile@0x168, TargetTiles@0x190,
                                 settings{+0x10 = 0, +0x11 = 1}, AffectedTileAmount()))
                     op_Subtraction Blocking(<le même>)
AffectedTileAmount() = Sum(Get(1), RoundsStarted(caster@0x160),
                           TotalRepairActionsAmount(UnitsWithTrait(Friends(caster@0x160, AllUnits@0x80, 3),
                                                                   0xc = 12 Mechanic, 3)))
```

L'i2 confirme les trois termes : « The length of the line starts at 2 hexes and increases by 1 hex for
each round that has passed and by 1 hex each time a friendly Mechanic restores Health of a unit »
(au round 1 : `Get(1) + RoundsStarted = 1 + 1 = 2`).

### Points de fidélité

- **Settings de ligne** : le ctor écrit `*(short*)(settings + 0x10) = 0x100` = **`+0x10 (checkWalkable)
  à 0`, `+0x11 (updateReference) à 1`** (little-endian) — même couple que
  `…DeathOnTheWindAbility$$GetTilesInLine`. `check_walkable=False` désarme AUSSI le gate d'ÉLÉVATION
  (il vit dans la branche walkable d'`IdunBattle.Core.Services.TileUtil$$IsTileValidForList`) : la
  ligne traverse les dénivelés.
- **Famille ABILITY** : le call-site appelle `IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage`
  (vérifié par `list_xrefs`) → 1 tirage/coup, pas de crit/block.
- **ORDRE des cibles — `Foreach`, PAS `multi=True`** : `IdunBattle.Entities.Behaviours.AbilityDamageBehaviour$$Execute`
  (famille ABILITY) ÉNUMÈRE son sélecteur **tel quel** — aucun `OrderBy`, contrairement à
  `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute` qui pose `targets.OrderBy(b__5_0)` dès que
  `Count > 1`. Or la feuille portée `AttackWithAttackDamage(multi=True)` folde l'`OrderBy` de la famille
  ATTACK : l'employer ici trierait par id une liste que le natif laisse dans l'ordre du sélecteur
  (après `SortReverse` : de la tuile la PLUS LOINTAINE vers l'aim) → désync RNG dès deux unités
  alignées. D'où `Foreach(Units(tiles), AttackWithAttackDamage(Subject(), …, multi=False))`.
- **Source du `Contaminated`** : surcharge 4-args → chaque TUILE est sa propre source
  (`source_from_target=True`), même mécanique que le FEU de Brazier.
- **Résidu nommé** : `AbilityDamageBehaviour$$Execute` tient un `OrderedSet` et passe à `ExecuteTarget`
  un flag « 1re occurrence de cette unité » ; il écarte aussi les cibles `!IsTargetable` et celles
  portant le trait `0x40e`. Inerte ici (`Units(tiles)` ne peut rendre deux fois la même unité, sauf
  BigTarget multi-hex — substrat non modélisé, déjà au backlog).

## 4. Masques de ciblage (règle de non-régression `154b5f0`)

Les deux masques sont **RE-lus**, pas recopiés d'un littéral visible.

| ability | masque | provenance |
|---|---|---|
| 1041 | `0x4002` | Le `.ctor` n'appelle **aucune** des trois surcharges de `TargetingOptions$$.ctor` (vérifié par `list_xrefs`) : il **copie un PRESET STATIQUE** (0x40 octets à `TargetingOptions.<statiques> + 0x140`). Le masque est le champ `+0x28` de ce preset, écrit par `IdunBattle.Core.Services.TargetingOptions$$.cctor` (table de presets ; l'entrée `+0x140` pose `+0x20 = 0`, `+0x28 = 0x4002`). |
| 1116 | `0xa0000000042` | `TargetingOptions..ctor(&opts, 0, &CustomRange(1), 1, 0xa0000000042, 0, 0, 0)` — surcharge **FLAGS DIRECTS** (7 args, `*(options+0x28) = param_5`), PAS l'overload PRESET+flags (qui ferait `+0x28 = flags \| preset.+0x28`). Le littéral EST donc le masque. |

Décomposition (`IdunBattle.Core.Services.TargetingRule`) :

- 1041 : `0x2` TargetMatchesDynamicRule + `0x4000` TargetIsEnemy. **1041 ne surcharge PAS**
  `GetDynamicInvalidTargetReason` (ses seuls membres sont `.ctor`, `ExecuteBehaviour`,
  `GetNumberOfHits`, `GetEffectTargets`) → il hérite du défaut de base (0, aucun refus), ce que rend
  déjà `ActiveAbility` : fidèle, pas une dégradation.
- 1116 : `0x2` TargetMatchesDynamicRule + `0x40` TargetIsTile + bits 37/39 (noms hors du dump 32 bits,
  non décomposés, non portés — même régime que le bit 32 de Waaagh). Le bit `0x2` est **servi** :
  `…RadBombardmentAbility$$GetDynamicInvalidTargetReason` est porté (refus `1` si l'aim est la tuile du
  caster, refus `2` si la ligne calculée depuis cet aim est VIDE, `0` sinon).

## 5. Briques DSL ajoutées

| nœud | natif | note |
|---|---|---|
| `Blocking` (selectors/geometry) | `IdunBattleLogic.Entities.DSLFactory$$Blocking` | MÊME classe de sélecteur que `…$$Walkable` — seul le dernier littéral change (**1** vs **0**). Le ctor gshared est mislabelé `EffectWithTypeSelector$$.ctor` par ghidra (foldé : `AtIndex`/`IsMechanical`/`MechanicalUnits`… l'appellent aussi) → structure lue (`+0x18` = source, `+0x20` = le littéral), jamais le nom. |
| `SortReverse` (selectors/geometry) | `IdunBattle.Entities.Selectors.SortReverseSelector$$Select` | `Enumerable.Reverse(source).ToList()` — inversion pure, aucun filtre malgré le nom. |
| `RoundsStarted` (formulas) | `IdunBattle.Entities.Formulas.RoundsStartedFormula$$Calculate` | **SOMME** de `turnsStarted` sur le sélecteur (le décompilé itère et accumule — pas un `First`, contraste `UnitTurnsStartedFormula`). Pas de plancher `max(1, …)` ici : c'est un ajout propre au call-site Executioner. |
| `TotalRepairActionsAmount` (formulas) | `IdunBattle.Entities.Formulas.TotalRepairActionsAmountFormula$$Calculate` | SOMME d'un compteur per-unité (`component+0xe8`), DISTINCT de `TimesRepaired` (`+0xd0`). **RÉSIDU** : ce compteur n'est capté par aucun canal offline → rend 0, valeur EXACTE tant qu'aucun Mechanic ami n'a soigné (régime de tout runner frais). |
| `Sub` étendu (selectors/units) | `TargetsSelector.op_Subtraction` | Tolère désormais le domaine TUILE (clé = l'élément brut si ce n'est pas un dict d'unité) — le natif compare des références d'entité sans distinguer le domaine. Aucune régression : un non-dict levait auparavant. |
| `AddEffect(source_from_target)` | `AddEffectBehaviour$$Execute` | Mirror du fallback « sélecteur source NULL ⇒ source = cible » (cf. §2). Défaut `False` = inchangé pour tous les autres call-sites. |

## 6. Validation

`test_brazier_of_holy_fire_live.py` (3) et `test_rad_bombardment_live.py` (4), **12/12 verts** avec les
gardes `test_sentinel_directives_live` + `test_sanctorum_missile_live`, rejoués APRÈS rebase.

- **Brazier / géométrie 1** (`necroWarden`, non-Daemon) : `hits = nrOfHits = 2`, dégât per-coup
  **bit-exact** `[1899, 1599]` live == offline, feu sur la tuile de la cible, et — assertion négative —
  aucun 1075 posé (aucun Daemon à portée).
- **Brazier / géométrie 2** (`blackObliterator`, Daemon) : `hits = nrOfHits_2 = 4` live ET offline
  (**le scénario discriminant** : un port qui lirait `nrOfHits` en dur passe la géométrie 1 et tombe
  ici), 1075 posé sur la cible elle-même (`includeCenter`), 1ᵉʳ coup bit-exact.
- **RadBombardment / géométrie 1** (1 unité alignée) : ensemble des tuiles `Contaminated` live ==
  offline (l'observable DIRECT de `GetAffectedTiles`), dégât bit-exact, `Pinned` posé.
- **RadBombardment / géométrie 2** (2 unités alignées) : **séquence des cibles** live == offline, tuiles
  contaminées identiques, `Pinned` sur les deux, 1ᵉʳ dégât bit-exact.
- **Garde déterministe de l'ORDRE** (offline pur) : la géométrie de spawn peut faire COÏNCIDER
  l'ordre-ligne et l'ordre par id (le test live imprime `discriminant_vs_tri_par_id`). Un test
  synthétique construit donc une ligne où les deux DIVERGENT (cible lointaine id 200, cible proche
  id 100) et exige `[200, 100]` — un port resté en `multi=True` rendrait `[100, 200]`.

### Deux artefacts de MESURE, pas des écarts de port

1. **Delta de PV pollué par le tick de fin de tour** : 1041/1116 posent les turn-flags par défaut, donc
   le cast finit le tour du caster ; en 1v1 strict le moteur bascule de joueur et TICKE avant la
   relecture. Mesure : coups `[1899, 1599]` = 3498 demandés, delta PV live 3071 = 3498 − 427, et 427 =
   5 % des 8536 PV max de la cible = son `LivingMetal`. **On asserte donc le `Amount` PAR COUP**, jamais
   le delta de PV. Pour RadBombardment, une 2ᵉ unité d'ESCORTE (qui ne caste pas) garde une activation
   au joueur → pas de bascule, pas de tick, lecture PRE-tick des effets.
2. Sans cette escorte, un `Pinned` fraîchement posé pouvait avoir été décrémenté/retiré avant la
   relecture — le test l'a effectivement rencontré sur la 2ᵉ cible.

### Ce qui n'est PAS couvert

- **1041** : la consommation du bonus 1075 (phase 2), la branche `Immune` de sa magnitude, le
  friendly-fire du marquage (aucun Daemon allié dans les rosters testés).
- **1116** : le friendly-fire de la ligne (le natif ne filtre PAS l'équipe — non mis en scène), le
  terme `TotalRepairActionsAmount` (toujours 0 offline), la troncature `- Blocking` sur un board à murs
  (MC1_67 n'en présente pas sur les lignes testées). ~~L'écart de conso RNG dû au canal `OnToxic`
  au-delà de la 1ʳᵉ cible~~ est FERMÉ (cf. §7.2) : le dégât per-coup est désormais confronté sur toutes
  les cibles.
- **Les deux** : `abilityTargets` n'a pas été confronté aux nouveaux `TARGETING_OPTIONS` (le gate est
  posé, mais aucun test ne vérifie qu'un cast ILLÉGAL est bien refusé par le port).

## 7. Gaps ADJACENTS mesurés (étages PARTAGÉS) — les DEUX sont FERMÉS

Tous deux touchent bien plus que ces deux abilities et changent la conso RNG d'un grand nombre
d'attaques → ils ont été traités à part, avec leur propre re-validation. Ils formaient les **deux
moitiés du même étage RNG** (les tirages que le port sautait pendant une attaque) et ont été
re-confrontés ENSEMBLE le 2026-07-27.

1. **`Daemon_ExtraBlock` (1034) inerte côté COMBAT — FERMÉ (#221, `case-221-daemon-extrablock-rng.md`)**.
   `AttackDamageOperation._block_sources` appelait `defender_effect_block_sources(effets, armure)`
   **sans** l'Attack courante du défenseur, dont `DaemonExtraBlockEffect.create_effect_block_source_
   for_defense` a besoin (`amount = defender_attack × daemonBlockDamagePercentage / 100`, `None` si 0)
   → le port sautait le jet de block que le natif roule (**+1 tirage natif par attaque contre toute
   unité Daemon**). L'Attack est désormais threadée ; la confrontation de dégât de la géométrie 2 de
   ce case porte donc sur les **4 coups** (le bridage `compare_hits=1` est levé). Reproduction :
   `probe_daemon_extrablock_gap.py`, `probe_brazier_daemon_offset.py` (qui rejoue aussi la variante
   « legacy » pour chiffrer l'écart).
2. **`OnToxicDamageAbility` (1203) — FERMÉ (`case-1203-on-toxic-damage.md`)**.
   `CreateBehaviour` = `If(IsFirstHitInSeries() & Maybe(ConfigConst(1203, Self@0x148, 0x2a)),
   AddEffect(0x4dc, …, Tiles(target)))` : le ET natif COURT-CIRCUITE, donc le `Maybe` consomme
   **UN tirage par SÉRIE de coups**, c.-à-d. une fois par cible d'une attaque de profil `Toxic`.
   Le canal est porté (`triggers/loki/on_toxic_damage.py`) et câblé sur les deux vecteurs d'attaque
   → la confrontation per-coup de `test_rad_bombardment_live` n'est plus bornée à la 1ʳᵉ cible
   (`compare_damage_targets` revenu au défaut = TOUTES les cibles, géométrie 2 verte).
