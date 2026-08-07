# #504 — `1132 KillMaimBurn` : la face COMBAT, et les deux étages que seul un compteur de TIRAGES a montrés

`worldKharn` « Kharn the Betrayer » (HERO, **dans le pool** au rank 17 ; second porteur
`worldBossKharnLHE`, npc). Face DÉCISION portée depuis #362
(`engine/playbook/noncomparable/kill_maim_burn.py`) pendant que l'exécution était un **NO-OP
SILENCIEUX** — 1132 absente d'`ABILITY_CLASSES` ⇒ cast accepté, tour consommé, 0 dégât, 0 effet,
aucune erreur.

## 1. Ce que le décompilé dit

`IdunBattleLogic.Entities.Abilities.Active.Loki.KillMaimBurnAbility$$ExecuteBehaviour` — trois
bandes d'attaque **enchaînées**, à trois plages / trois profils / trois comptes de coups :

```
dmg1/2/3 = MinMaxDamage / MinMaxDamage2 / MinMaxDamage3      (vars 0xc-0xd / 0x36-0x37 / 0x38-0x39)
p1/p2/p3 = GetDamageProfile / 2 / 3                          (Piercing / Eviscerate / Plasma)
h1/h2/h3 = ConfigConst(0x2f) / ConfigConst(0x32) / ConfigConst(0x66)   (nrOfHits 1 / 6 / 1)
n        = GetNumberConstant(0x16 range) = 2

t2 = GetNextTarget(target@0x60, AdjacentEnemies(caster@0x48, 1, 3),                    dmg2)
t3 = GetNextTarget(t2,          Unobscured(caster@0x48,
                                  SurroundingEnemies(caster@0x48, n, 1, 3)),           dmg2)

ExecuteAtomic( Group(Attack(caster, target@0x60, dmg1, p1, h1), target@0x60, 0x20)
             & Group(Attack(caster, t2,          dmg2, p2, h2), t2,          0x20)
             & Group(Attack(caster, t3,          dmg3, p3, h3), t3,          0x20), 0x2a )
```

`KillMaimBurnAbility$$GetNextTarget(previousTarget, validNextTargets, damage)` :

```
pool   = FromTrigger(validNextTargets, op_LogicalNot(IsObjectOrSteppable(It@0x68)), 0)
         .Otherwise(validNextTargets)
sorted = SortUnitsByDamageUtility(pool, caster@0x48, Direct(AbilityOrEffect(1132)),
                                  UtilityDefinition(0x23 = UtilityType.Damage), damage, 3, null)
return If(IsAlive(previousTarget), previousTarget, First(sorted, 1)).Otherwise(previousTarget)
```

Trois lectures qui ne se devinent pas :

* **`damage` vaut `dmg2` aux DEUX appels** (le même `pvVar5` est passé), pas `dmg3` pour la bande 3 ;
* **`SortUnitsByDamageUtilitySelector$$Select` CONSOMME un tirage** : il appelle
  `damage.Calculate(entities)` une fois (hors de la boucle par cible), et
  `IdunBattle.Entities.Formulas.RandomAmount$$Calculate` finit par `query.NextInternal(min, max+1)`
  sur le PRNG de **bataille** (`RandomAmount` reçoit ce PRNG de `DSLFormulas+0x18`). Son `hits`
  est `null` ⇒ le champ reste à `1` et la prédiction de tri vaut `dmgMin == dmgMax == <le tirage>` ;
* **`attackRangeType = Melee`** pour l'ability entière — la `range = 2` ne borne QUE le pool de
  re-ciblage de la bande 3, jamais le gate de cible du cast (`RANGE_ADJACENT`).

Masque : `$$.ctor` est de la forme **preset copié** (aucun `TargetingOptions$$.ctor`) — les 0x40
octets de `<TargetingOptions statics>+0x40`, puis `AActiveAbility..ctor(this, &opts, 0)`.
`TargetingOptions$$.cctor` y écrit `Rules = 0x4000` (`TargetIsEnemy` seul), `forceMeleeTarget = 1`
(`RangedBool.False`), `range <- TargetingRange statics+0x30` = `RANGE_ADJACENT`. Le 3ᵉ argument du
ctor de base est le littéral **`0` = `AbilityAttackType.DirectTargetAttack`**.

i2 concordant, dernière phrase comprise : « *All attacks prioritize the same target until it is
killed and then prioritise kills.* » — c'est exactement le `If(IsAlive(prev), prev, First(sorted))`.

## 2. Les deux bugs, et pourquoi seul un compteur de TIRAGES pouvait les voir

Le port initial rendait, en régime « la bande 1 tue » : **le bon delta par unité** (4000 / 9000) et
**huit montants faux**. Un critère sur le total serait resté **VERT** — les cibles étaient surtuées,
donc le delta valait leurs PV quelle que soit la valeur des coups.

L'étage qui a tranché est le **nombre de `genrand_int32` consommés** (`dumpRng` avant/après le cast
natif, contre l'état du MT après le rejeu porté) : **port 20, natif 24**. Comptes différents ⇒
divergence **structurelle**, pas arithmétique. Un balayage `extras=(e0, e1)` de tirages injectés au
i-ᵉ tri qui trie a rendu un point unique : **`(1, 3)`, 24 tirages, séquence native exacte**.

Les deux causes, toutes deux LUES dans le décompilé une fois qu'on savait où regarder :

1. **`GroupBehaviour$$Execute` évalue son sélecteur de groupe** (`targets = (+0x68).Select(entities)`)
   **avant** le child. Le port ne l'évaluait pas — sa propre docstring transcrivait pourtant la
   ligne, et disait ensuite « jamais évalués ». Sur `KillMaimBurn` le sélecteur de groupe d'une
   bande **est** son nœud de re-ciblage ⇒ une évaluation (et un tirage) perdue par bande.
2. **`IfSelector.Select` évalue `previousTarget` DEUX FOIS sur la branche vraie** : une fois pour le
   trigger `IsAlive(previousTarget)`, une fois parce que le sélecteur rendu **est**
   `previousTarget`. Le port réutilisait la première évaluation.

Comptes prédits par le modèle corrigé, vérifiés au tirage près :
`t2.Select` = 1 tirage (son `previousTarget` est `Target()`, gratuit) ; `t3.Select` = 2 (son
`previousTarget` est `t2`) ; ×2 Select par bande (groupe + child) ⇒ **2 tirages avant la bande 2,
4 avant la bande 3**.

⚠ `Group` est un foyer **PARTAGÉ**. Les deux autres consommateurs ne changent pas de valeur :
PlagueWind passe `Cache(Target())` (mémo amorcé sur la cible du message, aucun tirage) et
SilentDeath passe `Null()` (ensemble vide). `test_plague_wind_live.py` + `test_silent_death_live.py`
rejoués : **10 passed**.

## 3. Confrontation live — quatre régimes, la SÉQUENCE coup par coup

`probe_504_kill_maim_burn.py` (board `MC1_67`, seed 504, `--crit 0,0`, positions **drivées**).
Chaque régime descend d'un cran dans la chaîne. Comparaison = les 8 `UnitDamaged` natifs
(`Active_Ability_Type=1132`) contre les `per_hit_health` du port **capés comme le natif cape**
(`Amount` = PV réellement retirés), plus le compte de tirages.

| régime | ce qu'il exerce | coups | tirages port / natif | verdict |
|---|---|---|---|---|
| R1 survivant | `IsAlive` VRAI partout ⇒ 3 bandes sur la même cible, **aucun tri** | 8 | 16 / 16 | séquence **bit-exacte** |
| R2 une mort | bande 1 tue ⇒ 1ᵉʳ re-ciblage, le survivant **ne meurt pas** | 8 | 24 / 24 | **bit-exacte** |
| R3 deux morts | bande 2 tue aussi — mais `t2` se re-cible seul tant qu'il reste un adjacent | 8 | 23 / 23 | **bit-exacte** |
| R4 pool élargi | les survivants sont HORS adjacence ⇒ pool de `t2` VIDE, `.Otherwise` rend le cadavre, `IsAlive` FAUX, `t3` consulte ENFIN le sien | 8 | 23 / 23 | **bit-exacte** |

Profils natifs observés dans les quatre régimes : `[20, 25×6, 7]` — trois profils distincts,
1 + 6 + 1 coups, dans l'ordre. R1 : `39469` de dégât, identique des deux côtés.

⚠ **R3 ne mesure PAS ce pour quoi on l'avait écrit**, et c'est le résultat qui a fait écrire R4 :
tant qu'il reste un ennemi **adjacent**, `t3` re-évalue `t2`, qui se re-cible tout seul — la bande 3
n'atteint jamais son propre pool. Il faut vider `AdjacentEnemies` pour y descendre.

### Les sept contre-épreuves (mesurées en R4, 7/7 discriminantes)

| variante | total | ce qu'elle change |
|---|---|---|
| REF | **14308** | == NATIF |
| AB1 profils permutés | 15533 | mêmes coups, mêmes plages ; seul le profil tourne |
| AB2 un seul volet | 18768 | les 3 bandes sur `minDmg`/`maxDmg`/`nrOfHits` |
| AB3 ordre inverse | 9000 | bandes 3-2-1 — **même nombre de coups**, seule la séquence change |
| AB4 sans re-ciblage | 4000 | les 3 bandes sur la cible du message, qui meurt à la 1ʳᵉ |
| AB5 pool bande 3 adjacent | 9000 | la bande 3 ne trouve personne ⇒ le pool **élargi** est LU |
| AB6 tri sans tirage | 13553 | le tri prend la borne MIN ⇒ 2 tirages perdus, tout se décale |

`AB5` ne diverge **que** dans R4 (en R1/R2/R3 elle rend la référence) : c'est ce qui rend ce régime
obligatoire, et ce qui prouve que `SurroundingEnemies(caster, range = 2)` est bien lu.

## 4. Ce qui a failli produire un FAUX ZÉRO

Le premier montage n'avait qu'**une** unité côté joueur : le cast terminait le tour de Kharn, `act`
basculait sur le camp adverse, et le **turn-start ennemi rendait à la cible la totalité des PV**
qu'on venait de lui prendre. Le delta lu valait `{}` — un zéro qui accusait le port alors que les
events natifs portaient **exactement** le total du port (39469). Parade : un **figurant** côté
joueur (`deathRotbone`, placé loin) garde le tour, donc la fenêtre de mesure reste ouverte.
Corollaire : un delta HP pris **après** un changement de camp n'est pas une mesure du cast.

## 5. Câblage — le contrat de disjonction, payé en cinq endroits

`ABILITY_CLASSES` (`abilities/handler.py`) + `TARGETING_OPTIONS` sur la classe + `ABILITY_ATTACK_TYPE`
(`DirectTargetAttack`), **dans le même commit** que la sortie de `TARGETING_OPTIONS_UNPORTED`.
Retiré aussi : le snapshot `SNAP_TARGETING_UNPORTED` et ses cardinalités
(`test_270r1_volet2_dict_keys_enum_offline.py`, **36 → 35**, total **120 → 119**, compte
**re-dérivé de la table**, jamais soustrait), et `POOL_ABILITIES_WITHOUT_COMBAT_CLASS` +
sa ligne-journal (`test_433_r4_r2_r1_r2_ability_range_offline.py`).
`DYNAMIC_TARGET_RULE_UNPORTED` : **vérifié, aucune entrée** — 1132 n'a aucun
`KillMaimBurnAbility$$GetDynamicInvalidTargetReason`, et son masque ne porte pas
`TargetMatchesDynamicRule`.

Gardes rejouées vertes : `test_targeting_options_sources`, `test_ability_registry_ratchet`,
`test_270r1_volet2_dict_keys_enum_offline`, `test_433_r4_r2_r1_r2_ability_range_offline`,
`probe_181_targeting_gaps` (0 manquante), `probe_120` étage 0 (aucun littéral de ctor manquant),
`probe_433_..._pool_masks`.

## 6. Résidus

* **#504-r1** — `engine/runner/operations/damage_utility.py` cite
  `UtilityDefinition(0x22 = 34 = Damage)` et un composite `DamageDealt(35) + KillUnit(36) +
  OverkillUnit(38)`. Sur le build `rnca9r7q6c`, `IdunBattle.Configuration.UtilityType` donne
  `34 = TileDistance`, **`35 = Damage`**, `36 = DamageDealt`, `37 = KillUnit`, `38 = OverkillUnit`
  — décalage d'un cran, et les **trois** call-sites natifs lus (`KillMaimBurn`, `Doombolt`,
  `AncestralFortune`) passent bien `0x23`. La citation est donc **périmée d'un build**. Le
  comportement porté, lui, est validé live par les call-sites existants et par ce cas : rien
  n'indique que la formule de `damage_composite` soit fausse, seulement que ses **noms cités** le
  sont. À re-dériver de `data/symbols/<build>/frida/enums.tsv` et à corriger dans les docstrings —
  pas touché ici pour ne pas mêler une correction de citation à un port.
* **Non porté, nommé** : `IsObjectOrSteppable` est monté ici via
  `non_steppable_or_object_units` — c'est le 5ᵉ des call-sites recensés par
  `#462-r4b-r1-r1-r1-r1-b-r1-r1-r2`, qui **passe donc de « non porté » à porté**. Les 4 autres
  restent ouverts.
* **Confonds du porteur, hors périmètre** : `TrophyTaker` (crit-chance, neutralisé par `--crit 0,0`),
  `BlessingsOfKhorne` (indexé sur les défaites mêlée de la bataille, 0 au 1ᵉʳ cast), `RapidAssault`.

## 7. Fichiers

* `scripts/python/engine/runner/abilities/worldeaters.py` — l'arbre, le nœud de re-ciblage, la classe.
* `scripts/python/engine/entities/behaviours.py` — `Group` évalue désormais son sélecteur (foyer partagé).
* `scripts/python/engine/runner/abilities/{handler,attack_type,targeting}.py` — le câblage.
* `scripts/python/probe_504_kill_maim_burn.py` — la MESURE (4 régimes, 7 contre-épreuves).
* `scripts/python/tests/engine/runner/test_504_kill_maim_burn_live.py` — la GARDE (7 tests).
