# case-890 — les deux actives du Hive Tyrant Leviathan (`1032 Catalyst`, `1056 StranglethornCannon`)

Port COMBAT des deux actives de `tyranBossHiveTyrantLeviathan` (**seul porteur** des trois).
`1052 CallRipperSwarms` : RE faite, port **non fait** — résidu `#890-r3`.

Build de RE : `rnca9r7q6c`. Confrontation live : board **`CE2_boss`** (la carte que le gameconfig
déclare pour ce boss), boss monté par `--explicit-stats tyranBossHiveTyrantLeviathan:4`.

---

## 1. Ce que la fiche d'audit annonçait, et ce que le décompilé dit

| id | audit | LU au décompilé |
|---|---|---|
| 1032 Catalyst | `EFFECT/BUFF` | **exact** — trois `AddStaticStatModifierEffect`, aucun nœud d'attaque |
| 1056 StranglethornCannon | `DAMAGE(Blast)` | **exact** — deux `AttackWithAttackDamage`, profil `Blast` |
| 1052 CallRipperSwarms | `SUMMON` | **incomplet** — summon **DIFFÉRÉ** : le cast ne spawne rien, il pose un effet dont le trigger de *turn-start* spawne |

La colonne d'audit dérive du `damageProfile` de l'ARME du porteur, pas du behaviour : elle se
trouve concorder sur les deux premières, ce qui ne la rend pas fiable. La troisième le montre.

---

## 2. `1032 Catalyst` — mirror

`IdunBattleLogic.Entities.Abilities.Active.Loki.CatalystAbility$$ExecuteBehaviour` :

```
armor       = GetVariableForLevel(config@0x60, 0x1b = 27 extraArmor,  abilityState, 0)
blockDmg    = GetVariableForLevel(config@0x60, 0x14 = 20 blockDmg,    abilityState, 0)
blockChance = GetNumberConstant  (config@0x60, 0x2d = 45 blockChance)
factionId   = GetStringConstant  (config@0x60, 0x3d = 61 factionId)          # "Tyranids"
targets = Cache( op_Subtraction( Friends( gs@0x48 = Caster,
                                          UnitsFromFaction(gs@0x20 = AllAliveUnits, factionId, 3), 3 ),
                                 gs@0x48 = Caster ), unique = 1 )
Execute( op_Addition( op_Addition(
    AddStaticStatModifierEffect(targets, 0x420 Catalyst_ExtraArmor_Effect,       0x10 FixedArmor,  Direct(armor),       Nullable(2), isHidden=0),
    AddStaticStatModifierEffect(targets, 0x422 Catalyst_ExtraBlockChance_Effect, 0x07 BlockChance, Direct(blockChance), Nullable(2), isHidden=0) ),
    AddStaticStatModifierEffect(targets, 0x421 Catalyst_ExtraBlockDamage_Effect, 0x08 BlockDamage, Direct(blockDmg),    Nullable(2), isHidden=0) ) )
```

`GetEffectTargetsSelector` reconstruit **le même** sous-arbre sans le `Cache` — le port partage
donc la fonction (`catalyst_targets_selector`).

Trois points qui ne se devinent pas :

* **La durée est un `System.Nullable<int>(2)` LITTÉRAL**, pas un `TurnsFromRounds` — donc déjà en
  TOURS (`duration_turns=2`). La surcharge appelée est tranchée par ses **xrefs entrantes** : les
  trois call-sites de `CatalystAbility$$ExecuteBehaviour` pointent celle qui prend un
  `Nullable<int>` et le convertit elle-même en nœud `Direct` (la même que `MightOfHeroes` et
  `DoomSiren`).
* **L'appariement effet ↔ stat ne suit pas l'ordre des ids** : `0x421`
  (`Catalyst_ExtraBlockDamage_Effect`) est le TROISIÈME volet, `0x422` (`…BlockChance`) le
  deuxième. Les trois couples sont lus au call-site.
* **Le caster est EXCLU** (`op_Subtraction(…, Caster)`) alors que son masque le déclare
  `CasterIsPossibleTarget` : le masque gouverne la LÉGALITÉ du cast (self-cast), le sélecteur
  gouverne QUI reçoit.

### Masque — forme **STATIC-COPY** (3ᵉ des six)

`CatalystAbility$$.ctor` n'appelle aucun `TargetingOptions$$.ctor` : il recopie les 0x40 octets du
preset statique `+0x280`, puis `AActiveAbility..ctor(this, &opts, 2)` → `AbilityAttackType.Others`.
Contenu relu dans `IdunBattle.Core.Services.TargetingOptions$$.cctor` :
`isSelfCasting = 1` · `range ← TargetingRange statics+0x60` (= `RANGE_SELF`) ·
`forceMeleeTarget = 1` (= `RangedBool.False`) · **`rules = 0x8004`** =
`CasterMatchesDynamicRule | CasterIsPossibleTarget` (décomposition exhaustive, aucun bit résiduel).
1032 ne surcharge pas `GetDynamicInvalidCasterReason` → défaut 0.

---

## 3. `1056 StranglethornCannon` — mirror

`IdunBattleLogic.Entities.Abilities.Active.Loki.StranglethornCannonAbility$$ExecuteBehaviour` :

```
profile = GetDamageProfile(config@0x60).Value                          # Blast
mainDmg = AActiveAbility.MinMaxDamage (this, abilityState)             # minDmg  / maxDmg
adjDmg  = AActiveAbility.MinMaxDamage2(this, abilityState)             # minDmg_2/ maxDmg_2
hits    = GetNumberConstant(config@0x60, 0x2f = 47 nrOfHits)           # 3
hits2   = GetNumberConstant(config@0x60, 0x32 = 50 nrOfHits_2)         # 1
adj     = DSLSelectors.AdjacentUnits(gs@0x60 = Target, unique = 1, 3)
ExecuteAtomic( op_BitwiseAnd( op_BitwiseAnd(
      InformWeapon(...),
      AttackWithAttackDamage(gs@0x48 = Caster, gs@0x60 = Target, mainDmg, Nullable(profile), hits,  ...) ),
      AttackWithAttackDamage(gs@0x48 = Caster, adj,             adjDmg,  Nullable(profile), hits2, ...) ),
   entities, 0x55 = GroupType.StranglethornCannon_AtomicGroup )
```

Le tag `0x55` est **confirmé live** : le stream ouvre bien un groupe nommé
`StranglethornCannon_AtomicGroup`.

* Le ring-1 est passé **BRUT**, sans wrapper `Enemies` (contraste PlasmaGrenade / ScythingTalons /
  HarvesterOfSouls) → **FRIENDLY-FIRE** ; `AdjacentUnits` exclut son origine → la cible ne prend pas
  de coup splash en plus de ses 3.
* Le `selectionType = 3` (`OnlyAliveAndTargetable`) est porté PAR le sélecteur : c'est le seul
  filtre de l'ensemble splash, faute de wrapper — d'où **pas** de `Alive(…)` ajouté par le port.
* `InformWeapon` n'est pas matérialisé en feuille — résidu `#890-r1`.

### Masque — forme **PRESET + FLAGS** (2ᵉ des six)

`StranglethornCannonAbility$$.ctor` recopie le preset `+0x140`, puis appelle
`TargetingOptions$$.ctor(&opts, &preset, 0x100000000)`. **Surcharge tranchée par ses xrefs
entrantes** (les trois surcharges décompilent sous le même nom) : le call-site figure dans les
xrefs de `(this, template, additionalRules)`, la même qu'appellent `ThunderousAssaultAbility` et
`TheQuickeningAbility`. Son corps, lu : `this+0x28 = additionalRules | template+0x28` — un **OU**,
pas un remplacement.

Preset `+0x140` relu dans le `cctor` : `isSelfCasting = 0` · `range ← TargetingRange statics+0x18`
(= `RANGE_FROM_CONFIG`, `constants.range` = 3) · `forceMeleeTarget = 0` (= `RangedBool.True`) ·
`rules = 0x4002`.

⇒ masque **effectif** `0x4002 | 0x100000000` = **`0x100004002`** :
`TargetMatchesDynamicRule` (bit 1, pas de surcharge dynamique → défaut 0) |
`TargetIsEnemy` (bit 14) | **`TargetIsNotAdjacent`** (bit 32, **ajouté par le ctor** — sans lui le
port laisserait le boss tirer au contact, ce que le natif refuse).
`AActiveAbility..ctor(this, &opts, 0)` → `AbilityAttackType.DirectTargetAttack`.

---

## 4. Le piège qui a fait diverger le port — la NATURE du coup ne se déduit PAS de la portée

Premier port : `is_melee=False` (« l'ability est à portée 3, donc *Ranged* »). **Faux, et
observable.**

`IdunBattle.Core.Services.BattleQuery$$IsRangedAttack` part de
`$$GetAbilityAttackRangeType(ability)` = `gameconfig.abilities[<nom>].attackRangeType`. Or **1056
n'en a aucun** (ses constantes : `damageProfile`, `nrOfHits`, `nrOfHits_2`, `range`) — contraste
`HarvesterOfSouls` / `Supercharge` / `Stikkbomb`, tous `Ranged`. `rangeType` absent ⇒
`IsMeleeAttack` **faux** ET `IsRangedAttack` **faux** ⇒ les gates de nature sont tous inertes
(convention `hits_channel_is_melee(is_melee=None)`, déjà utilisée par `EntropyCannons`).

Ce que ça changeait, mesuré : `IdunBattle.Entities.Effects.Loki.BigTargetAdjacentEffect$$CreateEffectHitsBonusForAttack`
= `Direct(-1)` cappé à `Direct(1)`, sous `get_OwnerIsTarget & IsRangedAttack`. En déclarant
`Ranged`, le port armait ce gate et retirait **un coup** dès qu'un `BigTarget` allié était adjacent
à la cible : **2 coups au lieu de 3**.

**Décomposition par étage qui l'a localisé** (aucun scalaire fitté) :

| étage | port | natif |
|---|---|---|
| `ability_attack_params` (`nrOfHits`) | 3 | 3 |
| `attack_hits_with_modifiers` | **2** | 3 |
| … en retirant `aura_sources` | 3 | — |
| … en retirant la seule source `tyranTyrantGuard` (BigTarget, d=1 de la cible) | 3 | — |

Puis **variation d'entrée** : le même montage avec le `BigTarget` déplacé hors du ring-1 rend
`port == natif` bit-exact — l'écart était donc exactement ce terme.

⚠ Contrôle de non-généralisation : l'attaque **NORMALE** ranged du boss, dans la MÊME géométrie,
ne fait **qu'un coup** (au lieu de 2). Le terme `BigTarget` n'est donc pas faux en soi — c'est son
application au vecteur ABILITY, sur une ability sans `attackRangeType`, qui l'était.

---

## 5. Le comblement du niveau d'ability d'un BOSS (`#890`, `snapshot.py`)

`combatSnapshot.units[].unitConfig` rend **`{"error": "config null"}`** pour un boss monté par
`--explicit-stats` (les héros normaux portent `activeAbilityLevel: 50`,
`abilityVariablesMultiplier: 180`). Conséquence silencieuse : `ctx.active_ability_level = 0` →
`ability_var(…, level=0)` lit l'INDEX 0, c'est-à-dire le **niveau 1** — `Catalyst.extraArmor` **10**
au lieu de **1190**, `blockDmg` **15** au lieu de **1786**.

Le canal `unitAbilityStates.units[].actives[]`, lui, porte `type`/`level`/`mult` par ability :
`configId = "tyranBossHiveTyrantLeviathan:4"`, quatre actives à `level 55, mult 200`.

`_load_active_ability_levels` écrit donc deux choses :

1. `UnitContext.active_ability_levels = {ActiveAbilityType: (level, mult)}` — additif, personne
   n'est obligé de le lire. `abilities/base.py::active_ability_state` s'en sert (Catalyst), avec
   repli explicite sur le scalaire.
2. le scalaire `ctx.active_ability_level` / `ability_variables_multiplier`, **uniquement quand le
   trou existe**.

**La règle du comblement est vérifiable** (c'est ce qui la rend non arbitraire) : on prend le
**maximum** des niveaux d'actives, avec le `mult` de cette entrée — et sur les unités qui portent
DÉJÀ leur scalaire, cette règle le reproduit : `ultraCalgar` porte `1000@50` + `69@1` (l'attaque
normale a son propre niveau 1) pour un `unitConfig.activeAbilityLevel` de `50` ; `tyranTyrantGuard`
porte `1105@50` + `69@1` pour `50`.

⚠ `bind_live_rpc` est **obligatoire** côté appelant, et son absence est SILENCIEUSE : sans
transport lié, `load_state` rend `ability_states_seed.source == "no-transport"` et le canal n'est
pas tiré. `probe_890_hive_tyrant.offline_state` **LÈVE** dans ce cas au lieu de mesurer au
niveau 1.

---

## 6. Le montage — recette

```
python scripts/python/rl_duel.py build --board CE2_boss --seed 777 \
       --state-file <ABSOLU, hors data/> \
       --explicit-stats "tyranBossHiveTyrantLeviathan:4" \
       --p-units "tyranBossHiveTyrantLeviathan:4,..." --a-units "..." \
       --place "tyranBossHiveTyrantLeviathan:4:0,0" --a-place "ultraCalgar:2,0" ...
```

* `--explicit-stats` est **répétable** (un flag par unité) ; `--p-units` est à virgules ; et
  `--place` veut l'id **avec son palier** (`tyranBossHiveTyrantLeviathan:4:col,row`).
* **Aucune échappatoire de roster n'est posée, et c'est délibéré.** Le garde butait sur l'id
  d'entité remappé (`GuildBoss2Boss1TyranHiveTyrantLeviathan`) et rendait
  `demande x1 mais MONTE x0` sur un boss pourtant EN BATAILLE ; ce probe a d'abord tourné sous
  `TACTICUS_ALLOW_ROSTER_DEFICIT=1`. **#895 a réparé le garde** (il résout le remappage) → le build
  passe `rc=0` sans rien neutraliser, VÉRIFIÉ. La variable est même **retirée de l'environnement**
  hérité : la garder ferait taire un vrai déficit.
* Le boss est `moveNone` → tout volet dépendant d'un déplacement du CASTER est **NON CONFRONTÉ**.
* Board : `CE2_boss` (7×10, `IsBossBoard`, 1 `BossPlatform` de 3 tuiles) — celui que le gameconfig
  déclare pour ce boss, contre `MC1_67` (7×9, 0 `BossPlatform`).

### Ce que les témoins DISCRIMINENT

* **Catalyst** — 4 non-cibles pour 3 raisons différentes : le CASTER (`op_Subtraction`), deux
  alliés NON-Tyranides (`UnitsFromFaction`), un Tyranide **ENNEMI** (`Friends`). Et les montants
  couvrent deux régimes : `extraArmor`/`blockDmg` scalés à 200 %, `blockChance` non (constante).
* **StranglethornCannon** — le ring-1 de la cible contient à la fois deux ennemis **et un allié du
  caster**, un autre allié restant à distance 3 ; la cible est à 2 du caster (donc
  `TargetIsNotAdjacent` satisfait *et* dans `range`). Le friendly-fire est la seule chose qui
  distingue ce port d'un port qui aurait recopié le patron voisin.

### Ce que les témoins NE discriminent PAS (limites écrites)

* **`feet`** — 1 tuile partout, y compris le boss placé exactement sur une tuile de la
  `BossPlatform`. Ce canal **ne discrimine rien** (il rend `1` pour tout le monde), et ce cas n'en
  conclut donc rien. ⚠ **La question générale, elle, est TRANCHÉE par #895/#896, et pas par ce
  canal** : un boss monté par `rl_duel` est **MONO-HEX**, prouvé par une porte NATIVE —
  `1193 NovaCharge` porte `TargetingRule.CasterHas7Tiles` et `abilityTargets` y rend 0 quand sa
  voisine rend 66 au même instant. Les deux masques du Hive Tyrant (`0x8004`, `0x100004002`) ne
  portent **aucun** bit `CasterHas{1,3,7}Tiles` : ce boss-ci n'offre pas cette porte. Ce qui reste
  ouvert est en amont — la `BossPlatform` de 3 tuiles existe dans le dump de board et n'est
  consommée par aucun étage de notre voie de montage (résidu `#890-r4`).
* Le volet **PERÇAGE** de la nature `None` : le boss a `extra_pierce_ranged = extra_pierce_melee =
  0`, donc `ranged=not is_melee` reste inobservable ici.
* Le **camp** : le boss est monté côté JOUEUR (`--p-units`), alors qu'en campagne il est côté
  ennemi (`TeamWithPlayerIndex` 1, groupe de spawn à 8 points contre 5).
* La branche `AttackRangeType.Normal(3)` n'est pas portée (résidu antérieur, case-122 §6).

---

## 6ante. `#890-r1` — FERMÉ : la feuille EXISTAIT, et le `Nullable` n'était PAS vide

Deux prémisses tombent d'un coup.

**(a) « le nœud n'est pas matérialisé en feuille » est PÉRIMÉ.** La feuille
`runner/abilities/behaviours/combat.py::InformWeapon` existe et deux autres arbres l'utilisent
(`admec`, `blacktemplars`). Ce qui manquait, c'est le **câblage** dans l'arbre `1056`.

**(b) La note du port lisait le call-site à l'envers.** Elle écrivait
`InformWeapon(Nullable<DamageProfileType>(), null, null)` — un `Nullable` **VIDE**. Relu,
`StranglethornCannonAbility$$ExecuteBehaviour` fait `Nullable__ctor(&local_210, local_res8)` sur le
**MÊME** `local_res8` que les deux `AttackWithAttackDamage` — c'est-à-dire la **valeur** de
`GetDamageProfile(config@0x60)`. Et l'écart comptait, parce que `DSLBehaviors$$InformWeapon` écrit

```
tags[0x93 Attack_Weapon_DamageProfile] = damageProfileType.HasValue ? (int)value : -1
tags[0x92 Attack_Weapon_IsMelee]       = isMelee                       // INCONDITIONNEL
if (useSpecial != 0) tags[0x94 Attack_Weapon_Use_Special] = useSpecial // CONDITIONNEL
```

⇒ un `Nullable` vide aurait fait écrire `-1` (`DamageProfileType.None_`) là où le natif écrit
`Blast` — et la mesure live du même case (`= 18`) l'aurait contredit. Porter la note telle quelle
aurait donc introduit un **faux** que rien n'aurait rattrapé côté état (le nœud est combat-inerte).

Câblage livré : `op_and(op_and(inform, main), splash)` — l'association du natif. Le nœud ne consomme
aucun tirage, donc l'attaque reste **bit-exacte** ; `test_890_hive_tyrant_live.py` (10 tests) rejoué
vert. `is_melee=False` ici ne contredit pas `STRANGLETHORN_IS_MELEE = None` : le **tag d'arme** du
flux et la **nature du coup** (`attackRangeType`, absent pour `1056`) sont deux questions distinctes.

Garde : `tests/engine/test_890r1_inform_weapon_offline.py` (4 tests). **Vue ROUGE** en dé-câblant :
`l'arbre doit porter TROIS feuilles (inform, main, splash) : ['AttackWithAttackDamage', 'AttackWithAttackDamage']`.

## 6bis. `#890-r2` — FERMÉ : la source de l'entité-effet est **la CIBLE**, et le décompilé le dit deux fois

Le résidu tenait sur **une** mesure live (`ReceiveEffect e=92 Effect_SourceId=92`). Le décompilé la
confirme, et il la rend structurelle plutôt qu'observationnelle :

```
IdunBattle.Entities.Behaviours.AddStatModifierEffectBehaviour$$Execute
    src = <sel@+0x58>.SelectSingle(entities)
    foreach (cible in <sel@+0x60>.Select(entities))
        source = (src != null) ? src : cible            <-- LE DÉFAUT EST LA CIBLE

IdunBattle.Entities.Behaviours.AddStatModifierEffectBehaviour$$.ctor
    (this, logger, isDynamic, source, targets, effectType, statType, amount, turns, isHidden,
     abilityState)  ->  +0x50 / +0x58 / +0x60 / +0x68 / +0x6c / +0x70 / +0x78 / +0x80 / +0x88 / +0x90

IdunBattleLogic.Entities.DSLBehaviors$$AddStaticStatModifierEffect(targets, effectType, statType,
                                                                   amount, turns, isHidden)
    -> .ctor(logger, isDynamic = 0, source = NULL, targets, ...)    <-- LITTÉRAL NUL
```

⇒ `+0x58 == null` pour **tout** call-site de la factory statique : la branche prise est **toujours**
« la cible ». Le variant `…$$AddStaticStatModifierEffectToOwner` passe
`source = targets = DSLSelectors+0x30` — même entité des deux côtés, même résultat.

⚠ **Le jumeau DYNAMIQUE n'a PAS ce vice et ne doit PAS être aligné** :
`…$$AddDynamicStatModifierEffect(targets, source, …)` porte un vrai sélecteur `+0x58`, que le port
lit déjà (`AddDynamicStatModifierEffect.source_sel`). Uniformiser les deux feuilles « pour la
cohérence » casserait la voie dynamique — le test l'interdit explicitement.

⚠ `abilityState` (`+0x88`) est lui aussi un **littéral nul** sur la voie statique : il n'y a rien à
y propager, et le port n'a donc pas à le modéliser ici.

**Rayon de souffle mesuré** : la feuille est partagée par `BloodChalice`, `CrusadeOfWrath`,
`UnbreakableDuty`, `MassDriver`, `Catalyst`, `NovaShield`, `Waaagh`, `RedRampage` et le lot
crit-chance de `blacklegion`. Rejoués — 11 fichiers offline (153 tests) et 11 fichiers live.
Deux ROUGES trouvés, **tous deux PRÉ-EXISTANTS sur `master` `28429702`** (vérifié en restaurant le
foyer à `HEAD` et en rejouant) : `test_statmod_captured_channel_offline.py::test_no_unclassified_
ability_state_rederivation_in_the_registry` (`HealingBalms_ExtraCritChance` /
`HealingBalms_ExtraCritDamage` non classées) et `test_893_crusade_of_wrath_live.py::
test_arbre_offline` (`UseActiveAbility` n'a plus d'attribut `subject_sel`).

Garde : `scripts/python/tests/engine/runner/test_890r2_statmod_source_offline.py`. **Vue ROUGE** en
remettant `source = caster` : `assert 11 == 22`, `AVANT #890-r2 le port inscrivait le CASTER (11)`.

## 7. Fichiers

* Port : `scripts/python/engine/runner/abilities/tyranids.py` (`CatalystAbility`,
  `StranglethornCannonAbility`) + les trois registres.
* Comblement : `scripts/python/engine/runner/snapshot.py::_load_active_ability_levels`,
  `engine/entities/unit_context.py::active_ability_levels`,
  `engine/runner/abilities/base.py::active_ability_state`.
* Mesure : `scripts/python/probe_890_hive_tyrant.py` (`--case feet|catalyst|cannon`).
* Garde : `scripts/python/tests/engine/test_890_hive_tyrant_live.py` (10 tests, dont la VUE ROUGE
  `test_cannon_declaring_ranged_over_reduces_live`).
