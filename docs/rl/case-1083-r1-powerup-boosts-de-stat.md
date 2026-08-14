# #1083-r1 (tranche 1) — les CINQ `PowerUp_*` de BOOST DE STAT : portés, confrontés 5/5

**Verdict en une ligne** : les cinq passifs sont portés et confrontés au natif (accord exact sur la
stat, le bouclier et les PV) ; le fait qui ne se lisait **pas** dans leur `CreateBehaviour` est que
`dmgPct` / `healthPct` sont **multiplicatifs**, et ça se lit **quatre étages plus bas**, dans la
classe d'effet.

## 1. La surface portée

| passif | id `TriggeredAbilityType` | vslot surchargé | effet posé (`EffectType`) | constante |
|---|---|---|---|---|
| `PowerUp_Armor` | 1136 | `$$AdditionalBehavior` (`+0x398`) | `PowerUp_Armor` 1138 | `healthPct` (dyn.) |
| `PowerUp_Health` | 1137 | `$$get_PctBasedStatBoost` (`+0x378`) | `PowerUp_Health` 1143 | `healthPct` = 200 |
| `PowerUp_MeleeHits` | 1138 | `$$get_AbsoluteStatBoost` (`+0x388`) | `PowerUp_MeleeHits` 1142 | `extraHit` = 4 |
| `PowerUp_Damage` | 1139 | `$$get_PctBasedStatBoost` | `PowerUp_Damage` 1139 | `dmgPct` = 100 |
| `PowerUp_Hits` | 1140 | `$$get_AbsoluteStatBoost` | `PowerUp_Hits` 1141 | `extraHit` = 2 |

⚠ **Les deux enums divergent, et le seul ordinal qui coïncide le fait par accident** :
`TriggeredAbilityType.PowerUp_MeleeHits` = 1138 = `EffectType.PowerUp_Armor`. Écrire un ordinal ici
aurait été faux quatre fois sur cinq, **sans erreur ni crash**.

⚠ **`PowerUp_Armor` n'est PAS un « boost de stat » comme les quatre autres** : il ne surcharge NI
getter de boost, mais `AdditionalBehavior`, et pose un modificateur **dynamique** dont la magnitude
vit dans une classe d'effet (`PowerUp_ArmorEffect$$GetDynamicStatModificationAmount` = 100 % de la
`Health/Maximum` du ramasseur). L'énoncé de la tranche annonçait « seulement leur getter de boost » :
c'est faux pour lui, et c'est la première chose que la mesure a corrigée.

## 2. Le trigger commun — le jumeau d'`HaywireMineSteppable`

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.APowerUpAbility$$CreateTrigger`, nœud par nœud
(`DSLSelectors+0x30` = `Owner`, `+0x40` = `Actor`, `+0x48` = `Caster`, `+0x60` = `Target` — mapping
**mesuré** sur `DSLTriggers$$get_OwnerIsActor` / `$$get_OwnerIsTarget` / `$$get_OwnerIsCaster` /
`$$get_CasterIsTarget`, qui construisent chacun le même nœud à deux sélecteurs) :

    EventTrigger(1 = PreUnitDeath) & <DSLTriggers+0x70> & NOT TargetIsOverkilled()
  & <DSLTriggers+0x70> & get_OwnerIsTarget
  & HasDeathReason(Owner, 2 = DamageReason.Steppable, <Nullable VIDE>)
  & NOT HasTrait(Actor, 0x1b = Steppable) & IsAlive(Actor)

C'est le trigger d'`HaywireMineSteppableAbility` **moins** son `AreEnemies(Owner, Actor)` — un
power-up profite à **quiconque** marche dessus, ami compris ; l'absence est **lue** (aucun appel à
`DSLTriggers$$AreEnemies` dans le corps) — **plus** le gate overkill.

Le vecteur existe déjà côté port depuis `#462-r4b-…-r2` : `movement.py::_kill_steppable_units` →
`_kill_steppable_kill_unit` grave `DamageReason.Steppable` puis joue `KillUnitOperation$$Execute`
en entier, `On(1)` compris. **Aucun étage n'a eu à être ouvert** pour cette tranche.

⚠ `<DSLTriggers+0x70>`, lu **deux fois** dans la conjonction, n'est **pas porté** : c'est le trigger
CONSTANT VRAI, donc un conjoint neutre. Deux mesures indépendantes l'établissent — (a)
`DSLTriggers$$InitializeShared` compose `+0x30 = EventTrigger(0x21) & <+0x70> & OwnerIsActor` (si
`<+0x70>` était faux, ce trigger partagé serait mort) ; (b) `BaseEffect$$NeedsRefreshing` fait un
`isinst` sur ce type pour décider qu'un effet n'a **pas** besoin d'être rafraîchi.

## 3. LE FAIT QUI NE SE LIT PAS DANS `AddPctBasedBoost`

`APowerUpAbility$$AddPctBasedBoost` passe `Get(GetNumberConstant(dmgPct))` **nu** à
`AddStaticStatModifierEffect`. Lu littéralement, `PowerUp_Damage` donnerait **+100 d'attaque plate**.
Le port l'a d'abord écrit ainsi. La chaîne réelle, lue étage par étage :

1. `EffectsDatabase.<InitializeEffects>b__14_167/168` construisent
   `PowerUp_Effect(source = TriggeredAbilityType.PowerUp_Damage / PowerUp_Health,
   locaConstant = dmgPct / healthPct, isMultiply = **1**)` ; `b__14_169/170` (Hits, MeleeHits)
   passent `isMultiply = **0**` ;
2. `PowerUp_Effect$$.ctor` transmet le flag à `AStatModifierEffect$$.ctor(sourceAbility,
   unitEffectType, canBeImmuneTo = 0, keepOnRevive = 1, isMultiply)` → champ `+0x482` ;
3. `AStatModifierEffect$$ApplyModification` choisit sa `StatPart` dessus :
   `part = (this+0x482 != 0) ? 9 = MultiplierModification : 5 = Modification` ;
4. `StatComponent$$ApplyModifier` / `FillUpStatComponent$$ApplyModifier` **case 9** appellent
   `ValueModification$$Modify(…, isMultiplier = 1, initialValue = <la part INITIAL du stat>)`, qui
   alloue un `ValueModification.MultiplyModifier` dont `$$UpdateValue` vaut
   `GetAmountRounded(Fix64(initialValue) * pct / 100)`.

⚠ **Le premier argument de `PowerUp_Effect$$.ctor` est un `TriggeredAbilityType`, pas un
`EffectType`** — la signature le dit (`frida/methods.tsv`). `0x472` y désigne
`TriggeredAbilityType.PowerUp_MeleeHits`, pas `EffectType.PowerUp_Armor`. Exactement le piège
« un énoncé peut se tromper d'enum, silencieusement ».

**Collapse porté, numériquement exact** : le port n'a pas de sac multiplicatif (ses `StatPart` 5 et
9 partagent le même `ValueModification`), donc il pose directement
`PercentageOf(pct, StatAmount(target, stat, Initial))`. L'`initialValue` natif est **le même
nombre** — `StatComponent+0x48` pour un stat simple, `FillUpStatComponent+0x10` pour `Health`, et
les deux sont ce que `get_stat_part(StatPart.INITIAL)` rend côté port.

## 4. La confrontation — 5/5, témoin non dégénéré

`probe_1083r1_power_up_stat_boosts.py`, ramasseur `ultraCalgar` (HP init 9537), board `MC1_67`,
un runner par cas. Le power-up est posé **à côté** du ramasseur (`--a-place` / `--place`) et le
crush est joué par un `applyAction` de MOUVEMENT réel ; le port rejoue le même `MoveUnitMessage`
depuis la **même** capture.

| cas | stat | natif | port | bouclier (natif = port) |
|---|---|---|---|---|
| `hits` | `extraHits` | 0 → **2** | 0 → 2 | 0 → 9537 |
| `meleehits` | `extraHitsMelee` | 0 → **4** | 0 → 4 | 0 → 9537 |
| `damage` | `attack` | 2811 → **5622** | 2811 → 5622 | 0 → 9537 |
| `armor` | `fixedArmor` | 2008 → **11545** | 2008 → 11545 | 0 → 9537 |
| `health` | `healthMax` | 9537 → **28611** | 9537 → 28611 | 0 → 9537 |

`health` bouge **aussi** les PV courants (9537 → 28611 des deux côtés) : c'est le second étage du
volet, un `ChangeStat(Health, Add, <le même montant>)` — sans lui, un +200 % de PV max laisserait
l'unité au même nombre de PV.

Le bouclier `9537` est commun aux cinq : `shieldPct = 100` % de la part **INITIAL** de `Health`,
pour `TurnsFromRounds(nrOfRounds = 1)`.

**Contre-épreuve** (`--regime hors-tuile`, `damage` et `health`) : le ramasseur se déplace sur une
tuile **voisine**. Natif et port sont **tous deux inertes**, et le power-up **survit**. C'est ce bras
qui sépare « le port joue le trigger » de « le port buffe à chaque déplacement ».

## 5. Deux faux négatifs de MON propre probe, tous deux trouvés par la mesure

1. **`Health` est une stat FILL-UP.** Le moteur écrit dans le `HealthComponent` de l'entité (via
   `stat_ops._fillup_component`), pas dans `UnitStats.components`. Lire le second rendait
   `port_apres == port_avant` — un port **juste** affiché comme intégralement inerte. Le probe lit
   désormais par le **même dispatch** que l'écriture.
2. **`decisionView.units[].effects` publie un `name`, jamais un `type`.** La première version lisait
   la mauvaise clé et rendait **toujours** `[]`, ce qui se serait lu comme « le natif ne pose rien ».
   C'est maintenant un **cran du verdict** (`effet_pose_natif` / `effet_pose_port`), pas un
   affichage.

## 6. Ce qui reste OUVERT

- **`#1089`** — `PowerUp_ArmorEffect$$CreateHandleTriggerAbilitiesInternal` n'est **pas porté** : le
  natif re-pose l'effet à chaque `On(0x1e = HealthChanged)`, donc son armure suit la `Health/Maximum`
  du porteur. Le port fige la valeur au ramassage. Régime qui les sépare, et il est atteignable :
  ramasser `PowerUp_Armor` **puis** `PowerUp_Health`.
- **`#1083-r1` (reste)** — les **17** autres `PowerUp_*`. Ce ne sont **pas** des variantes : cinq
  d'entre eux (`HeroSpawn`, `Reinforcement`, `ReinforcementShield`, `Resurrect`, `SummonSpawn`)
  surchargent `$$CreateBehaviour` **en entier**, donc la base ne s'applique pas à eux ; trois
  (`Bomb`, `Healing`, `ReactivateAbility`) surchargent `$$AdditionalBehavior` et réutilisent la base.
- `SelfContainedBoostEffect` (vslot `+0x368`) : **aucune** des 22 classes `PowerUp_*` ne le surcharge
  (balayage exhaustif de `ghidra/functions.tsv`) — la branche prise est `Nothing()`, le volet est omis.
