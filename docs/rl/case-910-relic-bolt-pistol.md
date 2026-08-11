# #910 — `RelicBoltPistol` : deux canaux, un multiplicateur qui n'est pas un gate, et un substrat de traits qui rendait le gate MORT

Relique `R_Crit_RelicBoltPistol` (Mythic, voie `item`), **7 porteurs `lineup`** — la plus volumineuse
des reliques ouvertes. i2 : « The relic bearer gains +10% pierce ratio with melee attacks and deals
+877 Crit Damage with ranged attacks. **These bonuses are doubled against Chaos or Xenos enemies.** »

## 1. Identité — trois enums, deux collisions d'ordinal SUR LE CHEMIN

```
TriggeredAbilityType  0x5bb = 1467 = RelicBoltPistol                  <- la CONFIG des DEUX effets
EffectType            0x5b1 = 1457 = RelicBoltPistol_ExtraPierce      <- effet MELEE
EffectType            0x5b2 = 1458 = RelicBoltPistol_ExtraCritDamage  <- effet RANGED

TriggeredAbilityType  0x5b1 = 1457 = KardiocoreGalvanus               <- une AUTRE relique
TriggeredAbilityType  0x5b2 = 1458 = PhoenixGem                       <- une AUTRE relique
EffectType            0x5bb = 1467 = SelfRepairMechanism              <- rien a voir
```

Les deux `EffectType` sont les littéraux passés à `IdunBattleLogic.Entities.DSLBehaviors$$AddEffect`
(2ᵉ argument, typé `IdunBattle.Entities.Enum.EffectType` dans `frida/methods.tsv`). Le `1467` est le
littéral du `.ctor` de l'effet, relu **octet à octet** :

```
ba bb 05 00 00      ; mov  edx, 0x5bb = 1467
e8 <rel32>          ; call IdunBattle.Core.AbilityOrEffect$$op_Implicit
                    ;   surcharge tranchée par son ADRESSE : son corps appelle
                    ;   `AbilityOrEffect$$set_TriggeredAbility` (les surcharges sont homonymes)
41 b0 01            ; mov  r8b, 1  = hasAutomaticActivation
e8 <rel32>          ; call IdunBattle.Entities.Effects.BaseEffect$$.ctor
```

⚠ Ce `.ctor` est **PARTAGÉ** par les deux classes d'effet :
`RelicBoltPistol_ExtraCritDamageEffect$$.ctor` est absent des tables (IL2CPP déduplique les corps
identiques), ce qui **prouve** que les deux lisent la même config — et non l'inverse (« absent donc
non surchargé » serait le faux négatif documenté au CLAUDE.md).

## 2. La pose — deux owner-effects PERMANENTS, INCONDITIONNELS

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.RelicBoltPistolAbility$$CreateBehaviour` :

```
AddEffect(0x5b1, AbilityStateReference, source = Owner@DSLSelectors+0x30,
          targets = Owner@DSLSelectors+0x30, options = <zeroe>)
& AddEffect(0x5b2, ... idem ...)
```

La surcharge d'`AddEffect` est tranchée par l'**adresse** de son `call` (relue à l'assembleur) : son
6ᵉ paramètre est `options: System.Nullable<AddEffectBehaviourOptions>`, **pas une durée**. Il n'y a
donc aucune durée à poser — les deux effets sont PERMANENTS. Aucun `If(...)` ne les enveloppe
(contrairement au corps de base `AOwnerEffectTriggeredAbility$$CreateBehaviour`), et aucune des deux
classes ne porte de `CreateActiveCondition` (`ghidra/functions.tsv` ne connaît pour elles que
`.ctor`, `CreatePiercingBonusForAttack`, `CreateCritDamageBonus`).

**Conséquence de harnais, MESURÉE** : les deux instances sont toujours actives, donc toujours
publiées par `decisionView.effects` (canal ACTIF-ONLY). Mesure sur un runner
`--equip-relic darkaHellblaster:RelicBoltPistol:3` :
`effects: ['RelicBoltPistol_ExtraPierce', 'RelicBoltPistol_ExtraCritDamage']`.
⇒ **aucune entrée `ABILITY_INIT_OWNER_EFFECTS` n'est nécessaire**, et en ajouter une serait nuisible
(le seed lit les passives du KIT gameconfig, où une relique ÉQUIPÉE ne figure pas — même arbitrage
que `WireweaveNet` / `StructuralAnalyser`).

## 3. Les deux canaux — même corps, à la variable et à la nature du coup près

`...RelicBoltPistol_ExtraPierceEffect$$CreatePiercingBonusForAttack` et
`...RelicBoltPistol_ExtraCritDamageEffect$$CreateCritDamageBonus`, relus **des deux côtés** :

```
traitOr = HasTrait(Target@DSLSelectors+0x60, 0x3ee = 1006 Xenos)
          | HasTrait(Target@DSLSelectors+0x60, 0x7ea = 2026 Chaos)
cv      = ConfigVar(<0x3f extraPierceRatio | 0x42 extraCritDmg>, GetAbilityState(effect), config@+0x60)
amount  = If( traitOr, Multiply(cv, <DSLFormulas+0x28>), cv )
return    EffectBonus.ForAddition( get_OwnerIsCaster & <IsMeleeAttack | IsRangedAttack>, amount )
```

### 3.1 `<DSLFormulas+0x28>` = `Direct(2)` — et c'est une MAGNITUDE, pas un gate

Lu dans `IdunBattleLogic.Entities.DSLFormulas$$.ctor`, qui alloue cinq constantes dans l'ordre
`+0x18 = Direct(0)`, `+0x20 = Direct(1)`, **`+0x28 = Direct(2)`**, `+0x30 = Direct(100)`,
`+0x38 = Direct(-1)`.

Le trait de la cible est la **condition d'un `If`**, pas le gate du `ForAddition` : sans le trait, le
bonus vaut `cv`, il ne disparaît PAS. Confondre les deux — écrire le trait comme un gate, à
l'imitation de `GravitonRifle_ExtraPierce` dont le `traitOr` EST conjoint au gate — aurait annulé le
bonus contre tout Imperial. Écart PERMISSIF pour le défenseur et SILENCIEUX. Le bras `NODOUBLE` du
cliquet garde exactement cette distinction : il doit mordre **ssi** la cible est Chaos/Xenos.

### 3.2 `<DSLSelectors+0x60>` = `Target` — établi SANS hériter d'aucune citation

`IdunBattleLogic.Entities.DSLTriggers$$get_OwnerIsTarget` = `AreEqual(<+0x30>, <+0x60>)` et
`$$get_OwnerIsCaster` = `AreEqual(<+0x30>, <+0x48>)` : le membre **commun** aux deux est `Owner`,
donc `+0x30 = Owner`, `+0x48 = Caster`, `+0x60 = Target`. Deux fonctions de trois lignes suffisent —
`DSLSelectors$$InitializeShared` n'en dit rien (ses ctors sont tous mislabellés par ghidra).

### 3.3 `Xenos` / `Chaos` sont des pseudo-traits de GRANDE-ALLIANCE — LE fait porteur de la tranche

**MESURE : 0 unité du gameconfig (lineup + npc + summons) ne porte `Xenos` ou `Chaos` dans son
`traits`.** Ils viennent de `idun.Idun.Source.Shared.GrandAlliance$$GetTrait` (Imperial → 26,
Xenos → 0x3ee, Chaos → 0x7ea) et la couche meta les injecte dans la `BattleConfiguration`
(`BC.Units[].Traits`), donc dans `BaseUnitComponent+0x40` — ce que lit `HasTrait`.

Or `engine/runner/abilities/base.py::ability_pierce_effect_bonus` — le **foyer unique** du contexte
du canal PERÇAGE — relisait `gameconfig.unit(visual_id).traits`, c'est-à-dire le **KIT**. Le
doublement de `RelicBoltPistol_ExtraPierce` y était donc structurellement **MORT**, en silence.

Le trou était invisible parce que le seul autre demandeur de `target_traits` sur ce canal
(`GravitonRifle_ExtraPierce` : TerminatorArmour / MkXGravis / Mechanical) teste des traits qui, eux,
**sont** dans le kit. Les deux autres canaux avaient déjà migré : le canal DÉGÂT (`_target_traits`)
et le canal CRIT (`_crit_board::tgt_traits`, #889-r5) lisent `entity_trait_names` (#264).

**Réparation** : `ability_pierce_effect_bonus` lit désormais `entity_trait_names(tsc.ctx,
tuc.visual_id)`. Bénéfice collatéral non mesuré ici mais réel : un trait ACCORDÉ EN BATAILLE
(`DSLFactory$$AddTrait`, ex. `EnhancementAddTrait:MkXGravis`) devient visible du gate de
`GravitonRifle`, comme côté natif.

### 3.4 Le niveau lu est le TERTIAIRE

`source == targets == Owner` ⇒ l'`AbilityState` baké est celui de la relique **sur son porteur**,
donc l'état TERTIAIRE quand elle est équipée (`BC.Units[].TertiaryAbilityLevel`, cf. `case-237`). Le
port le relit par le foyer unique `runner/operations/triggers/base.py::triggered_ability_state`
(#357). Le canal CRIT le posait déjà (`_crit_board`) ; le canal PERÇAGE ne le posait pas — ajouté
ici sous la même clé `tertiary_ability_state_of`.

Sans ce discriminant, une relique de niveau 3 lit le niveau des PASSIFS (50 en runner normalisé) donc
le **dernier palier** : `extraPierceRatio` 10 au lieu de 6, `extraCritDmg` 877 au lieu de 654.
MESURÉ par le bras `PASSIF` : `693 -> 944` sur le canal perçage.

## 4. Confrontation live — 6 montages, 5 mutants, tous mordants

Porteur : **`darkaHellblaster` (Sarquael)** — l'un des 5 porteurs autorisés présents au pool, et le
SEUL à porter **deux armes** (`Physical` melee et `Plasma` r3). Un seul porteur exerce donc les deux
canaux, par la seule DISTANCE. Cible : `astraBullgryn`, dont les traits sont **écrits**
(`--unit-stat '<vid>:Traits=["Xenos"]'` → `BC.Units[].Traits`, le substrat que lit le natif).

| trait cible | canal | live | port | NOCHANNEL | NODOUBLE | PASSIF | KIT_TRAITS | CROISE |
|---|---|---|---|---|---|---|---|---|
| Hero (témoin) | PERÇAGE | 364 | 364 | 42 | 364 (=) | 591 | 364 (=) | 42 |
| Hero (témoin) | CRIT | 5755 | 5755 | 5287 | 5755 (=) | 5786 | — | 5561 |
| Xenos | PERÇAGE | 693 | 693 | 42 | 364 | 944 | 364 | 42 |
| Xenos | CRIT | 5900 | 5900 | 5287 | 5755 | 5050 | — | 5247 |
| Chaos | PERÇAGE | 693 | 693 | 42 | 364 | 944 | 364 | 42 |
| Chaos | CRIT | 5900 | 5900 | 5287 | 5755 | 5050 | — | 5247 |

`(=)` = ne mord pas, **et c'est l'attendu** : sur le témoin neutre, ni le `Direct(2)` ni le substrat
de traits ne peuvent changer quoi que ce soit. C'est ce qui interdit qu'un bras rougisse « par
construction ».

Étages du port (`--verbose`) sur `Xenos/PERÇAGE` : `ability_state = (3, 100)`,
`config_var_pierce = 6`, **`bonus_pierce = 12`**, `bonus_crit = None` (le canal ranged se tait en
mêlée). Symétriquement sur `Xenos/CRIT` : **`bonus_crit = 1308`**, `bonus_pierce = None`.

### 4.1 DEUX régimes dégénérés trouvés en montant, et ce sont eux la vraie leçon

**(a) Le CRIT rend le PERÇAGE inobservable.** Premier montage avec `--crit 100,2000` : le port
calculait bien `bonus_pierce = 12`, et pourtant `NOCHANNEL` **ne mordait pas** — live == port == 4196
des deux côtés. Un coup critique ne traverse pas l'armure de la même façon (`MkXGravis` : « Does not
apply to Crits »). Le canal perçage exige donc `--crit 0,0`, et le canal crit `--crit 100,<cd>` :
**deux builds, jamais un seul**.

**(b) Une armure trop FAIBLE rend le perçage inobservable, et l'algèbre le dit.**
`total = base × p + max(0, base × (1-p) - armure)` vaut `base - armure` **indépendamment de `p`** tant
que `base × (1-p) > armure`. Mesure (base = 4200) : armure 200 / 800 / 3000 → dégât 4000 / 3400 /
1200, **identique avec et sans le canal**. Il faut que l'armure absorbe TOUTE la part non percée :
armure 6000 → 42 (sans) contre 693 (avec).

Les deux régimes ont la même signature — un accord parfait qui ne mesure rien — et aucun des deux ne
se voit sans un mutant. C'est l'argument pour lequel les mutants ne sont pas une formalité.

### 4.2 Deux refus SILENCIEUX du montage, tous deux mesurés

* **`my_player` dérivé de la première unité vivante** du `decisionView` est celui de la CIBLE (owner
  adverse) : le tour amené est le mauvais, l'attaque part, rend `ok: true` et ne mute RIEN
  (`mutated: false, changes: []`). Le porteur doit être désigné explicitement.
* **Une tuile à `hexgeo.distance == 1` mais absente de la liste d'adjacence STOCKÉE** donne
  exactement le même refus : le natif teste l'adjacence par
  `TileQuery$$IterateAdjacentTiles` = `tile.<+0x30>.<+0x10>`, une liste stockée, aucune géométrie
  (déjà mesuré par #589-r1-r1-r2-r1-r8, re-rencontré ici). Les candidats mêlée viennent donc de
  `board.neighbours_native`.

## 5. Ce qui n'est PAS couvert

* **La face DÉCISION des DEUX canaux**, et c'est un résidu **PRÉEXISTANT et PARTAGÉ**, pas propre à
  cette relique. Il est déjà écrit dans le dépôt :
  `services/battle_query.py::select_weapon_pierce` dit « la PRÉDICTION ne passe pas [le bonus
  d'effet] (résidu documenté : la face décision ignore ce canal, comme elle ignorait déjà
  GravitonRifle) » ; et les deux agrégateurs de crit (`crit_damage_bonus_from_effects`,
  `crit_chance_bonus_from_effects`) n'ont **qu'un seul appelant**,
  `runner/operations/damage.py::_crit_params` — la face EXÉCUTION. L'IA ne voit donc ni le +perçage
  ni le +crit-dégât de la relique, pour AUCUN de leurs implémenteurs (1115, 1116, 1222, `SmashaEad`,
  `EmpyricAmbush`, `AmuletOfTheVoidwyrm`, `SupaCyborkBody`…). Résidu `#910-r1`.
* **`astarCyrus` et `darkaSternguard`** (2 des 7 porteurs) ne sont pas au pool : état 3 de la gate
  relique (injection catalogue). NON CONFRONTÉS — sans conséquence sur le verdict, car les deux
  canaux ne lisent **rien** du porteur hors son `AbilityState` (aucun trait, aucune stat, aucune
  position), ce qui rend le mécanisme indépendant de l'identité du porteur.
* **Le régime OVERWATCH.** Le gate natif est `IsRangedAttack` **seul** — il n'y a AUCUN
  `IsOverwatchAttack` dans ce corps, contrairement à `Hailstrike_ExtraPierceEffect` qui teste la
  disjonction. Le port passe donc `is_ranged` tel quel et ignore `is_overwatch`, ce qui est le
  mirror ; mais ce qu'`IsRangedAttack` rend POUR un tir d'overwatch n'a pas été mesuré ici.
* **La non-linéarité observée du pipeline aval.** Les quatre valeurs du canal perçage (bonus 0 / 6 /
  12 / 20 → 42 / 364 / 693 / 944) sont **monotones** mais pas affines en `p`. L'étage responsable est
  en AVAL de ce canal (résolution armure/perçage, déjà portée et validée ailleurs) : ce port verse un
  scalaire dans une somme, il ne décide pas de sa consommation.

## 6. Foyers

| fichier | rôle |
|---|---|
| `engine/entities/effects/loki/relic_bolt_pistol.py` | les deux classes d'effet (NEUF) |
| `engine/entities/effects/factory.py` | inscription des deux clés dans `EFFECT_CLASSES` |
| `engine/runner/abilities/base.py` | canal PERÇAGE : `target_traits` = substrat d'ENTITÉ + `tertiary_ability_state_of` |
| `probe_910_relic_bolt_pistol_live.py` | la MESURE (montage `flags_de_build`, 5 mutants) |
| `tests/engine/runner/test_910_relic_bolt_pistol_live.py` | le CLIQUET (10 tests, dont 2 offline) |

Résidus ouverts : **`#910-r1`** (face DÉCISION des deux canaux — structurel, partagé).
