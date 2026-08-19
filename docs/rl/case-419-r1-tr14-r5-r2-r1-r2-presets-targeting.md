# `#419-r1-tr14-r5-r2-r1-r2` — les presets `TargetingOptions` `statics+0x00` et `statics+0x80`

**Critere binaire** : les abilities qui recopient ces deux presets portent-elles leur masque
EFFECTIF, ou un masque absent / faux ?

**Verdict** : le REGISTRE (`ABILITY_CLASSES` + `TARGETING_OPTIONS_UNPORTED`) est JUSTE — une seule
de ses entrees consomme l'un des deux presets, et son masque est bon. Le faux etait dans la
**TROISIEME source de masque du port** : l'attaque normale, portee par une constante UNIQUE alors
que le natif la lit PAR TYPE. Corrige, et **confronte live sur un ecart que le port acceptait et
que le natif refuse**.

---

## 1. Les deux constantes, LUES dans la `.cctor`

`IdunBattle.Core.Services.TargetingOptions$$.cctor` ecrit **16 presets de 0x40 octets** dans le bloc
de statiques de la classe. Layout d'un preset (mirror du ctor « flags directs ») :

| offset RELATIF | champ |
|---|---|
| `+0x00` | `isSelfCasting` |
| `+0x08..0x1f` | `range` (`TargetingRange`, 0x18 octets) |
| `+0x20` | `forceMeleeTarget` (`RangedBool`) |
| `+0x28` | **`rules`** — le masque `TargetingRule`, 64 bits |
| `+0x30` / `+0x38` | les deux regles-delegues (ecrites a `0` par la `.cctor`) |

Les deux presets de cette tranche :

| preset | `isSelfCasting` | `range` | `forceMeleeTarget` | **`rules`** |
|---|---|---|---|---|
| `statics+0x00` | `0` | `TargetingRange statics+0x00` = `RANGE_ADJACENT_IF_MELEE_CASTER` | `2` = `RangedBool.IfRangedCaster` | **`0x4002`** |
| `statics+0x80` | `0` | `TargetingRange statics+0x00` = `RANGE_ADJACENT_IF_MELEE_CASTER` | `2` = `RangedBool.IfRangedCaster` | **`0x4000`** |

**Les deux presets sont identiques champ pour champ SAUF le masque**, et l'ecart tient en UN bit :

    0x4002 = TargetIsEnemy (bit 14) | TargetMatchesDynamicRule (bit 1)
    0x4000 = TargetIsEnemy (bit 14)                     <- le bit 1 EN MOINS

Meme motif que le piege mesure en PR #126 (`0x4002` contre `0x4000` sur un meme lot), mais sur une
AUTRE paire de presets : #126 opposait `statics+0x168` (= `rules` du preset `+0x140`) a
`statics+0x68` (= `rules` du preset `+0x40`).

⚠ **Les `+0x30`/`+0x38` du preset ne gouvernent RIEN** (avertissement #558, verifie ici) :
`IdunBattle.Entities.Abilities.AActiveAbility$$.ctor` recopie la struct dans `this+0x70..0xaf` puis
**ECRASE** `this+0xa0` et `this+0xa8` (= `options+0x30` / `options+0x38`) par deux delegues lies aux
slots de vtable `this+0x470` et `this+0x480`. Le masque `+0x28`, lui, est recopie TEL QUEL — c'est
donc bien la constante de la `.cctor` qui fait foi.
`IdunBattle.Entities.Abilities.ADeprecatedActiveAbility$$.ctor` (le socle des attaques normales) ne
fait que RECOPIER la struct et deleguer a `AActiveAbility$$.ctor` : meme conclusion.

## 2. Les consommateurs, ventiles par FORME

Les deux presets ne sont consommes que par la forme **RECOPIE DE STATIQUE** — aucun
`TargetingOptions$$.ctor` appele. Le ctor lit `*(DAT_1833ffc10 + 0xb8)`, copie 8 qwords depuis
`+0x00` (ou `+0x80`) dans une struct locale, et la passe a `ADeprecatedActiveAbility$$.ctor` /
`AActiveAbility$$.ctor`. Forme canonique
(`IdunBattleLogic.Entities.Abilities.Active.Loki.Loki_NormalBossAttackAbility$$.ctor`) :

```
lVar1     = *(longlong *)(DAT_1833ffc10 + 0xb8);
local_48  = *(undefined8 *)(lVar1 + 0x80);   ... uStack_10 = *(undefined8 *)(lVar1 + 0xb8);
ADeprecatedActiveAbility$$.ctor(this, &local_48, 0);
```

### `statics+0x00` → `0x4002` — 18 consommateurs

`69 Loki_NormalAttack`, `1046 TemplarInitiateNormalAttack`, `1063 FireAndReposition`,
`1073 StaffOfStars`, `1086 ProperKilly_NormalAttack`, `1120 FeederTendrils_NormalAttack`,
`1123 OptimizedGait_NormalAttack`, `1128 Boltstorm_NormalAttack`, `1138 Wraithcannon_NormalAttack`,
`1162 AncientFury_NormalAttack`, `1178 ElectroShock_NormalAttack`,
`1182 RighteousRepugnance_NormalAttack`, `1205 TalonOfHorus_NormalAttack`, `1220 Fealty_NormalAttack`,
`1228 SternguardFocus`, `9006 TestDirectKill`, `9008 TestDirectForceOverkill`, `9013 TestMultiHitAttack`.

### `statics+0x80` → `0x4000` — 7 consommateurs

`3 ChainLightning`, `9 HolyBolt`, `13 Test`, `17 NormalAttack`, `1004 MortisRound`,
`1030 Loki_NormalBossAttack`, `1114 BlisteringAssault_NormalAttack`.

**Une seule de ces 25 entrees est au registre du port : `1004 MortisRound`, et son
`TARGETING_OPTIONS` porte deja `0x4000`.** Les 24 autres n'ont aucune classe dans `ABILITY_CLASSES`
ni dans `TARGETING_OPTIONS_UNPORTED` — pour elles la regle « entrer au registre avec son masque »
n'est pas violee : elles n'y sont pas entrees.

**Le zero du gisement TIENT, re-derive** (`probe_181_targeting_gaps.py`) : `ABILITY_CLASSES` =
**102** entrees, **102** masques, **0** manquante ; idem pour `ABILITY_ATTACK_TYPE`.

### Comment cette liste a ete etablie — TROIS sources independantes

1. Lecture directe des `.cctor` et des ctors nommes (ci-dessus).
2. Balayage EXHAUSTIF des **133** `$$.ctor` qui referencent le bloc de statiques, decompiles un par
   un et classes par forme.
3. L'artefact GENERE `docs/rl/case-302-4/tile-target-population.json`, qui porte un champ `preset`
   par entree du registre natif.

Les trois concordent. **Les ecarts apparents de (2) sont tous des DEDUPLICATIONS IL2CPP**, et c'est
ce qui les rend lisibles : (2) rend 13 + 6, (1) et (3) rendent 18 + 7. Les cinq manquants du premier
lot (`1120`, `1128`, `1182`, `1205`, `1220`) n'ont **aucun symbole `$$.ctor` propre** — leur corps
est partage avec
`IdunBattleLogic.Entities.Abilities.Active.Loki.TalonOfHorus_NormalAttackAbility$$.ctor`, dont le
corps entier est `return Loki_NormalAttackAbility$$.ctor(this);`. Le manquant du second
(`1114 BlisteringAssault`) a un symbole, dont le corps entier est
`return Loki_NormalBossAttackAbility$$.ctor(this);`. Illustration exacte de la regle
« l'absence dans les tables ne prouve rien » du `CLAUDE.md`.

### Deux formes voisines a NE PAS confondre avec la recopie

* **`TargetingOptions$$.ctor(this, template)`** — une surcharge a **2** arguments qui recopie le
  template SANS aucun `|`. Le decompile la rend avec deux arguments seulement, ce qui se lit comme
  un `preset+flags` dont le litteral aurait disparu. Cinq abilities l'utilisent
  (`Doombolt`, `BloodyFury`, `MurderousSwing`, `DakkaDakkaDakka`, `Drachnyen`) ; leur masque est
  **exactement** celui du preset. Ne pas leur inventer de flags.
* **`TargetingOptions$$CustomLokiNormalAttackOptions(&opts, extraRules)`** — factory nommee qui
  recopie le preset `statics+0x00` champ par champ PUIS fait `opts.rules = preset.rules | extraRules`.
  Seul appelant : `MV71SniperDroneSquadAttackAbility$$.ctor` (1076). Le `extraRules` n'est pas rendu
  par le decompile (registre RDX perdu) — **LU AUX OCTETS au call-site** : `ba 02 00 00 00` =
  `mov edx, 2`. Donc `0x4002 | 2 = 0x4002` : l'argument etait deja dans le preset, et c'est le CALCUL
  qui le dit.

Aucune autre forme ne touche ces deux presets. Les trois appelants du bloc de statiques absents du
balayage — `BlightGrenades`, `VigilanceEternal`, `HeroicFusillade` — ont ete relus : les deux
derniers ne lisent que les statiques de **`TargetingRange`** (`+0x48` = `RANGE_WHOLE_BOARD`) et
posent un masque LITTERAL ; `BlightGrenades` construit ses options d'un litteral puis applique la
surcharge « template + flags » sur sa PROPRE struct locale.

⚠ **Residu d'artefact, nomme** : `tile-target-population.json` donne `1176 BlightGrenades = 0x4002`,
`form = literal`. C'est un **MINORANT** : le ctor applique ensuite `| 0x2000000`, donc le masque
effectif est `0x2004002`. Sans consequence ici (1176 n'est dans aucune table du port), mais
l'artefact ne doit pas etre lu comme une source de masque sans re-verification du ctor.

## 3. Ou etait le FAUX : la troisieme source de masque

Le port a **trois** sources de `TargetingOptions` : `ABILITY_CLASSES[aid].TARGETING_OPTIONS`,
`TARGETING_OPTIONS_UNPORTED`, et — pour l'attaque normale, qui n'est l'entree d'aucun registre — une
constante de module. **Le natif, lui, n'a pas de constante** :
`IdunBattle.Entities.Selectors.ValidNormalAttackTargetsSelector$$Select` DEMANDE le masque par TYPE.

```
opts = battleQuery.<slot 0x3e>(GetNormalAttackType(unit))
return targetingQuery.<slot 2>(unit, tiles, opts, false).Targets
```

Il y a **18 types d'attaque normale** au registre natif, et **quatre jeux d'options distincts** :

| jeu | `rules` | `range` | `forceMeleeTarget` | types |
|---|---|---|---|---|
| preset `+0x00` | `0x4002` | `RANGE_ADJACENT_IF_MELEE_CASTER` | `2` IfRangedCaster | 69, 1046, 1076, 1086, 1120, 1123, 1128, 1138, 1162, 1178, 1182, 1205, 1220 |
| preset `+0x80` | `0x4000` | `RANGE_ADJACENT_IF_MELEE_CASTER` | `2` IfRangedCaster | 17, 1030, 1114 |
| litteral RogalDorn | `0x4000` | `RANGE_ADJACENT_IF_MELEE_CASTER` | **`1` RangedBool.False** | 1126 |
| litteral FloatingDeath | `0x4000` | **`RANGE_ADJACENT`** (`TargetingRange statics+0x30`) | `2` IfRangedCaster | 1146 |

Les deux derniers ne recopient AUCUN preset de `TargetingOptions` : ils lisent un `TargetingRange`
statique et appellent la surcharge « flags directs ».

```
RogalDorn_NormalAttackAbility$$.ctor    : TargetingOptions$$.ctor(&opts, 0, &<TR statics+0x00>, 1, 0x4000, 0, 0)
FloatingDeath_NormalAttackAbility$$.ctor: TargetingOptions$$.ctor(&opts, 0, &<TR statics+0x30>, 2, 0x4000, 0, 0)
```

Le port appliquait le jeu `preset +0x00` a **toutes** les unites. **Six types sur dix-huit** ne le
portent pas — et pour deux d'entre eux ce n'est pas le masque qui differe, mais un champ qui GATE.

## 4. Ce qui MORD — et ce n'est pas le bit

**Le bit n'est pas decoratif, mais il est INERTE cote port.**
`IdunBattleLogic.Entities.Abilities.Active.Loki.ALoki_NormalAttackAbility$$GetDynamicInvalidTargetReason`
est un vrai corps :

```csharp
return FindAttackWeapon(caster, casterTiles, targetTiles) != null ? 0 : 2 /* TargetMatchesDynamicRule */;
```

(meme slot d'interface que `ALoki_NormalAttackAbility$$FindAttackWeapon`, dont l'implementation est
`IdunBattle.Core.Services.BattleQuery$$GetAttackWeaponForDefaultNormalAttack`). Un type a `0x4002`
consulte cette regle ; un type a `0x4000` ne la consulte JAMAIS. **Le port ne la porte pas** →
degradation PERMISSIVE sur les 13 types a `0x4002`, et rien a porter sur les 5 a `0x4000`. Mesure
(etage 2 du probe) : **0 ligne sur 4** differencie `69` de `1030` cote port. Le bit ne deplace donc
aucun verdict AUJOURD'HUI — le dire, plutot que compter ces types comme une victoire.

Poser le bit partout, comme le faisait le port, arme neanmoins une regle que le natif desarme : le
jour ou `FindAttackWeapon` sera porte, cinq types recevraient un refus que le natif n'applique pas.
C'est la raison NON-observable de la correction ; la raison observable suit.

**Ce qui mord est le `TargetingRange`.** `RANGE_ADJACENT` (`onlyAdjacent = RangedBool.True`,
`overrideRange = 1`) contre `RANGE_ADJACENT_IF_MELEE_CASTER` (`onlyAdjacent = IfNotRangedCaster`,
pas d'override) — deux consequences DISTINCTES dans `get_range` :

* `onlyAdjacent` vrai INCONDITIONNELLEMENT : un caster RANGED est ramene a l'adjacence, la ou
  `IfNotRangedCaster` le laissait sur le test de DISTANCE contre sa portee d'arme ;
* `overrideRange = 1` COURT-CIRCUITE `unit_weapon_range` : avec le jeu generique, une portee d'arme
  non observable fait rendre `None` a `get_range`, donc **aucun gate de portee du tout**. Les deux
  porteurs reels de `FloatingDeath` — `tyranNpc6SporeMine` et le summon `tyranSmnSporeMine` — ont
  precisement `weapons = []` au gameconfig.

Et `forceMeleeTarget = RangedBool.False` (1126) desarme le clamp de melee de `get_range`
(`RangedBoolExtensions.IsTrue(options.ForceMeleeTarget, caster) && ShouldApplyRangedInMelee`), que
le jeu generique applique a tout caster distant engage au corps a corps.

## 5. Le port

`engine/runner/abilities/targeting.py` :

* `NORMAL_ATTACK_TARGETING_OPTIONS_BY_TYPE` — les 18 types, chacun cite son ctor ;
* `normal_attack_type_for(state, caster_id)` — mirror de
  `IdunBattle.Entities.UnitExtensions$$GetNormalAttackType`, delegue au foyer unique
  `engine.services.custom_normal_attack.custom_normal_attack` (cascade passive → active → trait
  `Boss`) sur les canaux de PRODUCTION du `UnitContext` ;
* `normal_attack_targeting_options(state, caster_id)` — mirror du
  `battleQuery.<slot 0x3e>(GetNormalAttackType(unit))` ;
* `valid_normal_attack_targets` les consomme a la place de la constante.

`NORMAL_ATTACK_TARGETING_OPTIONS` reste exportee et vaut le jeu de `69` : c'est le repli quand le
type n'est pas resoluble, et c'est ce que les sous-classes de probe (`probe_436` / `probe_442` /
`probe_444`) surchargent. `_NormalAttackTargeting(options=None)` garde l'attribut de CLASSE, donc
ces sous-classes fonctionnent sans changement.

## 6. La CONFRONTATION

`probe_419r1tr14r5r2r1r2_normal_attack_options.py` — **deux runners APPARIES**, memes unites, meme
board (`MC1_67`), meme seed, meme roster. **Seul `BC.Units["necroWarden"].PassiveAbilities` differe** :

| bras | `PassiveAbilities` | attaque normale NATIVE mesuree |
|---|---|---|
| `float` | `["FloatingDeath"]` | **1146** `FloatingDeath_NormalAttack` |
| `ctrl` | `[]` | **69** `Loki_NormalAttack` |

`necroWarden` est RANGED (arme `Gauss`, portee 3), HERO, au pool. Geometrie PILOTEE : spectre
`(2, 3, 5)` autour du caster, **aucun ennemi adjacent**.

Oracle natif : `abilityReason(casterId, abilityType, targetId)` →
`AttackQuery.GetInvalidTargetReason`.

```
bras `float` (type 1146)                        natif       portParType  portBaseline
  u77 tauMarksman     ENNEMI  d=2               0x8000000   0x8000000    0x0       <- DISCRIMINANT
  u79 tauCrisis       ENNEMI  d=3               0x8000000   0x8000000    0x0       <- DISCRIMINANT
  u81 tauDarkstrider  ENNEMI  d=5               0x8000000   0x8000000    0x8000000
  u85 necroSpyder     ALLIE   d=1               0x4000      0x4000       0x4000

bras `ctrl` (type 69)
  u77 tauMarksman     ENNEMI  d=2               0x0         0x0          0x0
  u79 tauCrisis       ENNEMI  d=3               0x0         0x0          0x0
  u81 tauDarkstrider  ENNEMI  d=5               0x8000000   0x8000000    0x8000000
  u85 necroSpyder     ALLIE   d=1               0x4000      0x4000       0x4000
```

**8 lignes, 8 d'accord PAR TYPE, 6 d'accord BASELINE. 2 lignes GAGNEES, 0 PERDUE.**
`0x8000000` = `TargetIsInRange`. Le port ACCEPTAIT deux cibles que le natif REFUSE — degradation
permissive exacte, sur le seul chemin que la face DECISION emprunte.

### Deux refutations que la MESURE a payees

* **« pas besoin de greffe, `abilityReason` prend l'`abilityType` en argument » — FAUX.**
  Premier jet : 24 lignes a `0x1` (`ValidRequest`), y compris pour `69` sur un `tauMarksman`. Le
  decompile l'explique : `IdunBattle.Core.Services.AttackQuery$$GetInvalidTargetReason` commence par
  `ActiveAbilityComponent.GetOrNull(comp, abilityType)` et rend `ValidRequest` si l'ability n'est pas
  MONTEE sur le caster. Au passage, l'attaque normale de `tauMarksman` n'est pas `69` mais **`1076`**
  (il porte `MV71SniperDroneSquad`) — l'id concret ne se devine pas davantage que le reste.
* **« un ennemi adjacent ne gene pas » — FAUX.** Avec un foe a `d=1`, `forceMeleeTarget = IfRangedCaster`
  + `ShouldApplyRangedInMelee` ramenent DEJA la baseline a l'adjacence : les deux modeles refusent
  `d=2` et le discriminant se REFERME. Le spectre est donc `(2, 3, 5)`, jamais `(1, ...)`.

S'y ajoute le prealable de tout `abilityReason` : sans les `AMORCE_ENDTURNS` de `probe_247`, les
`initialCooldownTurns` font rendre `ValidRequest` partout.

## 7. Ce qui GARDE

* `tests/engine/test_419r1tr14r5r2r1r2_normal_attack_options_live.py` — 8 crans : les deux presets,
  les deux litteraux, « la table n'est pas plate », l'accord live, la contre-epreuve (la baseline
  DOIT diverger, sinon regime degenere), la reciproque (bras `ctrl` inchange), et l'inertie du bit.
* `probe_302_4_tile_target_population.py` `_crosscheck` soumet desormais les **18** masques
  d'attaque normale au controle contre le decompile, au lieu du seul `69` : **106 → 122** entrees
  confrontees, **0 desaccord**.

**CONTRE-EPREUVE JOUEE** : `1146` rabattu sur le preset `+0x00` (mutation du seul littéral) →
**4 tests rouges sur 8**, dont `test_la_constante_unique_diverge_du_natif` sur `REGIME DEGENERE`.
Le port a ete restaure et re-verifie identique a HEAD.

## 8. Residus nommes

* ~~**`#419-r1-tr14-r5-r2-r1-r2-r1` — la regle dynamique de l'attaque normale n'est pas portee.**~~
  **FERME** : `docs/rl/case-419-r1-tr14-r5-r2-r1-r2-r1-regle-dynamique-attaque-normale.md`.
  ⚠ **La chaine annoncee ici etait FAUSSE sur un point** : l'implementation n'est PAS la surcharge a
  `GetAbilityAttackRangeType` (c'est le slot `0xaf`, qu'aucun chemin porte n'emprunte) mais le slot
  **`0xb0`**, `GetAttackWeaponForDefaultNormalAttack(attacker, attackerTiles, targetTiles)`, dont
  tout le corps est `AreTilesAdjacent ? FindMeleeWeapon : FindRangedWeapon`. La confusion venait de
  « `FindAttackWeapon` » au singulier : `ALoki_NormalAttackAbility` en a DEUX surcharges, sur deux
  slots distincts, et `GetDynamicInvalidTargetReason` appelle l'autre.
  L'ecart PERMISSIF est confirme et ferme (6/6 sur le verdict contre 3/6, 3 lignes gagnees,
  0 perdue). Le refus ne mord que sur un caster **sans AUCUNE arme** — les deux autres regimes
  envisageables sont soit deja couverts par le volet portee, soit VIDES au catalogue.
* **`#419-r1-tr14-r5-r2-r1-r2-r2` — les masques recalcules HORS `.ctor` ne sont pas recenses.**
  `IdunBattle.Entities.Abilities.AActiveAbility$$GetTargetingOptionsForContinue` (et sa surcharge
  `GreatFrostAxeAbility`) produisent le SECOND jeu d'options, loge a `this+0xb0`, qu'un recensement
  limite aux `$$.ctor` ne voit pas. Hors chemin du cast top-level (cf. l'en-tete de `targeting.py`),
  donc sans effet mesure ici — mais le recensement n'est exhaustif que sur les `.ctor`.
* **`#419-r1-tr14-r5-r2-r1-r2-r3` — `1076 MV71SniperDroneSquadAttack` reste `measured_partial`
  dans l'artefact `case-302-4`** (le `extraRules` de la factory n'est pas lisible par son extracteur).
  Il est LU ICI aux octets (`mov edx, 2`), mais l'artefact ne le sait pas : son `_crosscheck` classe
  1076 en « non lisible » plutot qu'en accord.
