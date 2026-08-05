# #419-r1-tr14-r1 — `HeavyBoltPistol` (1083) sur ses PORTEURS RÉELS

La tranche 14 avait porté et confronté ce playbook **par greffe** sur `tauMarksman`, faute de
pouvoir amener en bataille ses deux porteurs. Le débloqueur `--explicit-stats` (#419-r1-tr12-r2)
les y amène. Ce que la confrontation sur le porteur réel **ajoute**, ce qu'elle **perd**, et les
**trois bornes** qu'elle rencontre.

## 1. Les deux porteurs, et leurs deux régimes de stats

| | `templNpc1Initiate:33` | `templInitiate` |
|---|---|---|
| catégorie | npc | summon d'ENVIRONNEMENT |
| chemin de stats | `UnitProgression$$GetNpcStats`, table `units.npc[].stats[]`, palier = suffixe `:33` | `UnitProgression$$GetSummonStats`, variables `summon*` |
| nature | **mirror de CATALOGUE** | **MONTAGE** (état post-spawn ; le jeu écrit `Health = 0` au catalogue pour les 65 summons) |
| Health / Damage / FixedArmor | 5792 / 2289 / 1154 | 3324 / 1330 / 665 |
| `(level, multiplier)` du passif 1083, **mesurés live** | **50 / 180** | **50 / 100** |
| montant `dmg` qui en découle | **1496** | **831** |
| traits d'entité mesurés | `['NPC', 'Imperial']` | `['Summon', 'Imperial']` |

Kits par ailleurs **identiques** : même `visualId` (`templNpc1Initiate` — c'est LU au gameconfig,
pas supposé), même arme `Chain` à 2 coups, même `Movement` 3, mêmes `passiveAbilities`
(`HeavyBoltPistol`) et `activeAbilities` (`DevoutPush`).

`templInitiate` est déclaré par **deux** abilities (`EnvFactionSummons:BlackTemplars` et
`:SpaceWolves`) aux stats **identiques**, et `summon_stats` le mesure avant de choisir. Il n'est
**pas** l'un des 9 summons hors portée des trois constantes de `GetSummonStats`
(#419-r1-tr12-r2-r1) — vérifié : `templInitiatePyreblaster`, lui, l'est.

## 2. Le montage — bras apparié sur le porteur réel

```
graft : le porteur RÉEL, PassiveAbilities = [1083]   (son état NATUREL, pas une greffe)
base  : le MÊME, PassiveAbilities = []               (--unit-stat, le levier de #446-r1 §4)
```

Board `MC1_67`, seed `141083`, `Health = RemainingHealth = 10000` pour tout le monde (zone
linéaire du composite `DamageDealt`, personne ne meurt). **Seul `Health` est écrasé** : `Damage`,
`FixedArmor`, `PassiveAbilityLevel` et le multiplicateur restent ceux du chemin explicite, et le
probe l'atteste.

Layout mesuré : `T=(0,0) A=(0,1) B=(0,2) K1=(0,4) K2=(0,6)`, roster
`templNpc1Initiate:33 + necroWarden` contre `astraBullgryn` (cible fixe) et `astraCreed`.

⚠ **Retirer 1083 change AUSSI l'attaque normale de l'entité** — c'est une clé de
`StaticBattleRules.TriggeredAbility$$GetCustomNormalAttack`. Les deux bras sont donc interrogés
avec la MÊME `abilityType`, celle du bras `graft`, **lue et attestée**.

## 3. La mesure — accord EXACT aux quatre crans, sur le porteur réel

`probe_419r1tr14r1_heavy_bolt_pistol_real_carriers.py --carrier npc --mutants` :

| cran | spot | tuile | natif greffé | natif apparié | **TERME natif** | port | port muté | **TERME porté** | écart |
|---|---|---|---|---|---|---|---|---|---|
| `far` | B | (0,2) | 0.000000 | 0.000000 | **+0.000000** | 9.148170 | 9.148170 | **+0.000000** | 0 |
| `tileAdj_realFar` | B | (0,1) | 9.148170 | 9.148170 | **+0.000000** | 9.148170 | 9.148170 | **+0.000000** | 0 |
| `adj` | A | (0,1) | 12.137572 | 9.148170 | **+2.989402** | 12.137572 | 9.148170 | **+2.989402** | +9e-9 |
| `realAdj_tileFar` | A | (0,2) | 2.989402 | 0.000000 | **+2.989402** | 12.137572 | 9.148170 | **+2.989402** | +9e-9 |

**Le terme vaut exactement ce que la greffe donnait** (`+2.989402`), et ce n'est pas une
coïncidence à commenter : c'est **décomposé**. `tauMarksman` normalisé rank 17 porte
`(level 50, multiplier 180)` ; la ligne `stats[33]` du npc porte `AbilityLevel 50` et
`ProgressionIndex 15` → `heroProgressionSteps[15].abilityStatMultiplierPct = 180`. Le couple étant
le même, `ability_var(HeavyBoltPistol, dmg, 50, 180) = 1496` des deux côtés. Le corps ne lit du
caster que son identité, sa position et le niveau de son propre passif — la greffe était donc
**légitime, et la mesure le confirme au lieu de le supposer**.

Le cran `far` est **DÉGÉNÉRÉ** (les deux bras nuls) et le probe le nomme.

### Ce que la mesure ajoute par rapport à la greffe

1. **Le dispatch d'attaque normale est confronté sur son porteur NATUREL.** L'entrée
   `1083 HeavyBoltPistol → 1046 TemplarInitiateNormalAttack` de #419-r1-tr14-r5-r1 n'avait été
   confrontée que par **greffe sur `astraBullgryn`**. Ici l'`Initiate` la reçoit de lui-même, et
   le bras `base` retombe sur `69 Loki_NormalAttack`.
2. **Un second point sur l'axe du montant**, obtenu par changement de PORTEUR et non par mutation
   du port : le summon rend `dmg = 831` (multiplicateur 100) contre 1496 pour le npc.
3. **Le régime d'arme change** : `Chain` (mêlée, 2 coups) au lieu de `Piercing` portée 3 — ce qui
   ouvre le régime « tuile d'attaque hors de portée », d'où le §5.

### Ce que la mesure PERD — et il faut le dire

**`profile_weapon` est ALGÉBRIQUEMENT INERTE sur le porteur réel.** L'arme de l'`Initiate` est
`Chain` et l'ability porte `Bolter` : **tous deux `PiercingRatio = 20`**, et `astraBullgryn` ne
porte aucune limite de dégât par profil. La faute que ce mutant simule — « et si le port lisait
l'arme du caster ? » — est donc **inobservable ici**, alors qu'elle mordait à `+8.978204` sur la
greffe (`Piercing`, ratio 80).

Sur cet axe précis, **la greffe était un meilleur discriminant que le porteur réel**. La lecture
« le profil vient de l'ABILITY » resterait donc sans garde — d'où une **septième contre-épreuve**,
`profile_foreign`, qui force un profil de `PiercingRatio` différent (**choisi par mesure**, pas
écrit en dur : `Acid`, ratio 40) et mord aux deux crans à terme non nul. L'équivalence
`Chain ≡ Bolter` est elle-même **assertée** : si elle cesse, `profile_weapon` doit redevenir
mordant.

## 4. Les sept contre-épreuves

| mutant | `far` | `tileAdj_realFar` | `adj` | `realAdj_tileFar` |
|---|---|---|---|---|
| `gate_tile` (gate sur la TUILE) | inerte | **+2.989402** | inerte | **−2.989402** |
| `no_gate` | **+2.989402** | **+2.989402** | inerte | inerte |
| `amount_half` | inerte | inerte | **−1.489702** | **−1.489702** |
| `profile_foreign` (NEUF) | inerte | inerte | **+2.989402** | **+2.989402** |
| `profile_weapon` | inerte | inerte | inerte | inerte |
| `melee_from_real` | inerte | inerte | inerte | inerte |
| `spread0` | inerte | inerte | inerte | inerte |

`gate_tile` garde sa signature exacte : il mord sur **les deux diagonales et elles seules**. Les
trois inertes sont gardés **à l'envers**, avec leur cause : `melee_from_real` et `spread0` sont les
résidus `#419-r1-tr14-r2` et `-r3` inchangés ; `profile_weapon` est le cas neuf du §3.

## 5. `#419-r1-tr14-r1-r1` — la PORTÉE de l'arme gate l'attaque normale : **FERMÉ**

Détail complet : `docs/rl/case-419-r1-tr14-r1-r1-portee-arme.md`. Ce qui a été mesuré ici :

| tuile | distance à la cible | natif | port AVANT | port APRÈS |
|---|---|---|---|---|
| `A` = (0,1) | 1 (à portée) | `732..1098`, **2** coups | `732..1098`, 2 — exact | idem |
| `B` = (0,2) | 2 (**hors portée** de `Chain`) | **`0..0`, 1 coup** | **`732..1098`, 2** | **`0..0`, 1** |

Le natif produit bien un `UtilityAttackCase` depuis la tuile hors portée — c'est ce qui permet à la
feuille `TriggeredAbilities(2)` d'y verser son terme, mesuré `+2.989402` — mais la prédiction de
l'**arme** y est nulle : `ALoki_NormalAttackAbility$$PredictAttack` commence par
`weapon = FindAttackWeapon(entities)` (slot `0xaf`) et branche sur la voie SANS ARME quand elle rend
`null`. Le port sélectionnait l'arme avec un **repli croisé** que la surcharge `0xaf` n'a pas.

La garde du §4 (test 8) est devenue un **ACCORD aux quatre crans**, bornes et nombre de coups.

## 6. Le porteur SUMMON : arrivée CONFRONTÉE, terme NON CONFRONTABLE — démontré, pas affirmé

**Confronté** : `templInitiate` arrive en bataille, `configId = templInitiate`, trait `Summon`,
stats du chemin `summon-spawn`, `(level 50, multiplier 100)` → `dmg = 831`, attaque normale native
`1046`.

**Non confronté — le TERME**, et quatre mesures le disent :

1. **Il n'est pas commandable.** `PlayAutomaticUnits` le rejoue au turn-start de sa team (#291).
   Un `_drive_to` vers la tuile à 2 hex le retrouve **au contact** — `(0,1)` au lieu de `(0,2)`.
2. **Le placement écrit lui est REFUSÉ**, et la cause est tranchée par **bras apparié, seul le
   trait changeant** : `necroWarden` sans `Summon` est placé à `(0,2)` (« placements vérifiés
   OK ») ; le **même** `necroWarden` avec `Summon` greffé (`catalog_inject.write_trait_seed_bc`)
   apparaît à `(1,5)` — le `--place` est **détourné**. Sur `templInitiate` lui-même, le même
   montage rend « non déployé », et **ce n'est pas la tuile** : refusé aussi sur sa propre tuile de
   spawn.
3. **Il n'expose plus aucune tuile d'action hors la sienne** (`aiMovableTiles` = `[(0,1)]`) : les
   deux crans DIAGONAUX sont hors de portée par construction, puisqu'ils exigent une tuile
   d'attaque **différente** de la position réelle.
4. **Le bras apparié se ROMPT.** Le summon attaque la cible à chaque turn-start, et il l'attaque
   **plus fort du côté `graft`** — c'est exactement ce que le passif ajoute. Mesuré : cible à
   **7945 PV** côté `graft` contre **8518** côté `base`. La différence `natif_graft − natif_base`
   mélange alors le terme et un écart d'ÉTAT ; l'écart lu dans ce régime (**−2.775445**)
   n'accusait **pas** le port.

Le contournement « placer LA CIBLE au lieu du caster » — légitime en principe, la gate lisant les
deux positions réelles — **ne sauve rien** : `--a-place` sort les deux a-units de
`BC.PredefinedUnits` et **inverse les camps**. Le summon devient l'IA, joue immédiatement et blesse
la cible (`HP 9368` sur 10000, mesuré). `Movement = 0` sur les unités placées ne l'empêche pas.

Le probe **exécute** cette démonstration (`run_case_summon`) : il pilote la géométrie puis appelle
`attest_paired`, qui **doit** lever, et rend la divergence chiffrée. Si un jour il ne lève plus, le
test rougit — un « non confrontable » ne se rend jamais sans être re-mesuré.

**Débloqueur nommé** : un canal qui empêche `PlayAutomaticUnits` de jouer une unité désignée (ou un
placement écrit qui honore le trait `Summon`). Ni l'un ni l'autre n'existe aujourd'hui, et les deux
vivent dans `frida/hooks/**` — donc une fenêtre de reinject.

## 7. Ce qui n'est PAS couvert

* Les **quatre crans sur le summon** (§6) — couverts sur le npc, dont il partage `visualId`, arme,
  `Movement`, passifs, actifs et attaque normale ; et ce que les diagonales tranchent (la gate lit
  le RÉEL) ne lit ni stat, ni trait, ni arme.
* **La face COMBAT** (`#419-r1-tr14-r4`) : `HeavyBoltPistolAbility$$CreateBehaviour` n'a toujours
  aucun mirror dans `engine/runner`. Un chemin de stats ne dit rien de l'exécution.
* Les résidus `#419-r1-tr14-r2` (ancrage positionnel de la prédiction) et `-r3` (spread ±20 %)
  restent **ouverts et inchangés** : le porteur réel ne porte pas davantage de modifier gaté
  melee/ranged, le board reste plat, et `HP = 10000` interdit toujours tout kill.
* Le résidu `#419-r1-tr14-r1-r1` (§5) est **FERMÉ** : la garde du §4 est devenue un accord aux
  quatre crans. Détail : `docs/rl/case-419-r1-tr14-r1-r1-portee-arme.md`.

## 8. Artefacts

| rôle | chemin |
|---|---|
| probe (MESURE) | `scripts/python/probe_419r1tr14r1_heavy_bolt_pistol_real_carriers.py` |
| garde (TEST) | `scripts/python/tests/engine/test_419r1tr14r1_heavy_bolt_pistol_real_carriers_live.py` |
| tranche mère | `docs/rl/case-419-r1-tr14-heavy-bolt-pistol-playbook.md` |
| débloqueur | `docs/rl/case-419-r1-tr12-r2-stats-npc-summon.md` |

**Aucun fichier d'`engine/` n'est modifié** : le port de la tranche 14 est confirmé tel quel, à
`9e-9` près (Fix64 natif contre float du port).

**Éprouvé par MUTATION du port livré** (motif vérifié avant écriture) : `should_trigger` renvoyé à
`True` → **4 rouges / 11** ; `_damage` divisé par deux → **1 rouge / 11** ; restauration →
**11 passed**.
