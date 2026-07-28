# Residu `blackObliterator` (case-o10 SS 6) : ce n'etait pas le DEGAT, c'etait le CHARGEMENT

**Question binaire du cas.** *A quel etage nomme les deux valeurs (live 2668 / offline 1440) se
separent-elles ?*

> **Reponse : a AUCUN etage du calcul de degat.** Elles se separent a l'etage de CHARGEMENT de
> l'etat. `load_state` ne reconstruisait pas le `UnitFlagsComponent`, donc `UnitFlag.Moved` etait
> TOUJOURS absent sur un etat recharge. Le gate no-move de
> `IdunBattle.Entities.Effects.Loki.HeavyWeapon_ExtraDmgEffect$$CreateDamageModifier` ne mordait
> jamais, et l'offline accordait a Volk un **+25 % de degat ranged que le natif lui refuse** parce
> qu'il venait de se deplacer.

Build de reference : `gqfc5mff6c`.

---

## 1. Etape 0 — l'ecart se reproduit a l'identique

Montage du rapport d'origine, rejoue verbatim (`probe_o10_volk_hp_residual.py`, seed 777, board
`MC1_67`, `--roster 2 --p-units blackObliterator,adeptHospitaller --a-units necroWarden,necroWarden`) :

```
attaque 0 : LIVE hp=2668 (degat=5868) | OFFLINE hp=1440 (degat=7096) | DELTA=-1228
```

⚠ **Vocabulaire du rapport d'origine a corriger** : `live_hp`/`off_hp` du helper
`tests/engine/runner/_on_hit_tile_effect_replay.py` sont les PV de la **CIBLE**, pas ceux de Volk.
« live 2668 / offline 1440 » veut donc dire que **l'offline SUR-INFLIGE 1228**.

Porteur confronte : `blackObliterator`, `necroWarden` et `adeptHospitaller` sont TOUS TROIS presents
dans `python rl_duel.py build --list-pool` (la seule porte valable). Cas confrontable.

## 2. Decomposition par etage — ce que l'ecart n'est PAS

Le ratio 7096/5868 = 1,209 n'a jamais servi de piste. Chaque etage a ete mesure des DEUX cotes.

### 2.1 L'etage `GetAttackHits` est JUSTE (capteur `hitTrace`)

`hitTraceArm` hooke `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` et rend la sequence de
coups a la source (index + `DamageProfileType`). Sur l'attaque 0 :

| | coups | sequence |
|---|---|---|
| LIVE | 9 | 7 x profil 19 (HeavyRound), puis 2 x profil 8 (Melta) |
| OFFLINE | 9 | 6 (arme) + 1 (groupe `LetTheGalaxyBurn`, profil emprunte) + 2 (groupe `FleshmetalGunsFocusedMalice`, Melta) |

Meme cardinalite, memes profils, meme ordre.

### 2.2 La consommation RNG est IDENTIQUE

`mt_same=True` : l'offline termine sur le MEME etat MT que le live (`mti` 624 -> 12 des deux cotes,
tableau `mt` identique). Aucun tirage ajoute ni supprime. L'ecart n'est donc ni un coup en trop, ni
un coup manquant — c'est une **magnitude par coup**.

### 2.3 Le levier qui a tranche : `IsRangedAttack`

Le trigger de `IdunBattle.Entities.Effects.Loki.BaseFleshmetalGunsEffect$$CreateAdditionalHits` est
`OwnerIsCaster & IsRangedAttack`. **En melee, FleshmetalGuns ne produit aucun groupe** : une attaque
de melee de Volk n'exerce donc que la phase d'arme. Mesure (`probe_o10_volk_stage_split.py --dist 1`)
— live == offline, **ecart 0, 2/2**. La phase d'arme et le canal `LetTheGalaxyBurn` sont justes.

### 2.4 Le renversement

Le meme probe en ranged **avec `--hp-target`/`--armor-target`** rendait `ecart 0` alors que le
montage d'origine rendait 1228 — a armure et PV identiques. La variable n'etait donc ni les PV, ni
l'armure, ni la formule : elle etait dans le **protocole du montage**.

Croisement final, toutes choses egales par ailleurs (meme seed, meme board, meme couple d'unites,
meme armure 2008, positions imprimees) :

| montage | Volk a-t-il bouge ? | live | offline | ecart |
|---|---|---|---|---|
| Volk drive en (3,7), cible en (6,8) | **OUI** | 5868 | 7096 | **1228** |
| Volk laisse a son spawn (1,0), cible amenee a dist 3 | **NON** | 7096 | 7096 | **0** |

**L'offline rend EXACTEMENT `7096` dans les deux cas** — meme `per_hit`, meme `clean=[2988,4482]`.
Cette insensibilite est la signature d'un gate aveugle, et elle designe l'etage : un predicat d'ETAT
de l'attaquant que l'etat recharge ne porte pas.

## 3. Le decompile

`IdunBattle.Entities.Effects.Loki.HeavyWeapon_ExtraDmgEffect$$CreateDamageModifier`, lu verbatim :

```
EffectBonus.ForPercentIncrease(
    get_OwnerIsCaster & IsRangedAttack
      & ((df@0xa0 & !HasFlag(Self@0x148, 3 = TurnFinished)) | !df@0xa0)
      & (!HasFlag(Self@0x148, 0 = Moved) | HasFlag(Self@0x148, 0xc = Teleported)),
    ConditionalAmount(TriggeringAbilityIs(0x3ec = 1004 MortisRound),
                      Multiply(base, Direct(2)), base))          # base = ConfigConst 0xf = 25
```

Cause racine cote port : `components.unit_has_moved` est le lecteur UNIQUE de `HasFlag(Moved)`, et
son seul poseur etait `set_moved_flag`, appele par le seul `MoveUnitOperation` — c'est-a-dire la voie
**self-play/rollout offline**. Sur un etat monte depuis un snapshot LIVE (tout replay-diff, tout
test live), rien ne le peuplait. La docstring du port le disait deja (« le RPC n'expose pas les
UnitFlags ») — **et c'etait faux**.

## 4. Le fix — aucun hook, aucun reinject

Le capteur existait deja : `frida/hooks/features/ai-step/rpc-snapshot.ts` (section O5) projette
`combatSnapshot.units[].unitFlags` (ids `UnitFlag` poses, obtenus en invoquant la fonction NOMMEE
`IdunBattle.Entities.UnitExtensions$$HasFlag`, une fois par valeur d'enum) **plus**
`combatSnapshot.unitFlagTypes` (mapping nom -> id lu au RUNTIME par `dumpEnum`). Il n'etait consomme
que pour `PreventOverkill`. Mesure du canal, avant/apres un `applyAction move` reel
(`probe_o10_moved_flag_source.py`) : `unitFlags` passe de absent a `[0, 1, 4]` =
`Moved`/`ArrivedAtFinalTile`/`NoActionAvailable`. Aucun autre champ des trois RPC ne porte
l'information (`effects[].active` ne bouge pas : le gate est **compute-time**, pas une
active-condition).

| face | fichier | mirror |
|---|---|---|
| seed du composant | `runner/snapshot.py::_load_unit_flags` (+ appel dans `load_state`) | `IdunBattle.Entities.Components.UnitFlagsComponent` |
| branche teleport | `runner/components.py::unit_has_teleported` | `HasFlag(Self@0x148, 0xc)` |
| threading | `runner/damage_model.py::attacker_modifiers` -> `att_ctx["has_teleported"]` | contexte per-coup |
| gate | `entities/effects/loki/extra_damage.py::HeavyWeaponExtraDmgEffect` | `(!HasFlag(Moved) | HasFlag(Teleported))` |

**La branche `| HasFlag(Teleported)` est portee DANS LE MEME COMMIT, et c'est obligatoire** : tant
que `has_moved` etait toujours faux elle etait masquee ; activer le flag sans elle aurait REFUSE le
bonus a un porteur teleporte, la ou le natif l'accorde — une regression creee par le fix lui-meme.
Elle est **specifique a HeavyWeapon** : la condition soeur
`IdunBattle.Entities.Effects.Loki.CrushingStrikeEffect$$CreateActiveCondition` est `!HasFlag(Self, 0)`
**seul** (decompile relu) — le port de CrushingStrike est donc laisse tel quel.

Degradation : champ `unitFlags` absent ou vide -> aucun composant pose = flag absent = comportement
anterieur. Cote PREDICTION, `has_moved` designe une tuile candidate et non un flag : la cle
`has_teleported` y est absente, donc `.get()` rend `None` et la branche est inchangee.

## 5. Validation

**Le cas d'origine, ferme** : `2668 / 1440` -> **`2668 / 2668`**. Tous les etages bougent
coheremment : `clean` `[2988,4482]` -> `[2394,3588]` (x0,8 exact) et les coups Melta du groupe
`1395/1399` -> `1116/1119` (/1,25) — le bonus s'applique bien aussi aux coups additionnels, des deux
cotes.

**Second cas discriminant** (exige : un montage ou l'hypothese predit une valeur DIFFERENTE et tombe
juste) — board `C2_02`, seed `31337`, board et seed tous deux distincts du cas d'origine :

| regime | `clean` offline | live | offline | ecart | `mt_same` |
|---|---|---|---|---|---|
| Volk DEPLACE (`--move-volk`) | `[2394,3588]` | 4608 / 3415 | 4608 / 3415 | **0** (2/2) | True |
| Volk IMMOBILE | `[2988,4482]` | 6161 | 6161 | **0** | True |

Les deux regimes predisent des valeurs differentes et tombent juste tous les deux.

**Gardes posees, et VERIFIEES DISCRIMINANTES.** Avec `_load_unit_flags` neutralise, les **trois**
tombent (mesure faite) ; restaure, les 17 passent :

1. `test_heavy_weapon_moved_gate_live.py` — nouvelle assertion « seed brut » : `load_state` SEUL,
   sans aucune pose ni retrait manuel, doit reproduire le live dans les DEUX regimes. Sans elle les
   deux cas existants continueraient de passer si le seed disparaissait (ils posaient le flag
   eux-memes) — c'est exactement le trou par lequel l'ecart a vecu.
2. `test_on_fire_damage_migration_live.py` — les PV sont desormais assertes **quand `mt_same`**
   (memes tirages => meme sequence de coups => les PV doivent concorder). C'est le regime exact ou
   l'ecart de magnitude vivait ; les confrontations `mt_same=False` relevent du residu SS 6.
3. `test_ability_target_gate_live.py::test_caster_has_not_moved_rule_matches_live` — reecrit :
   l'etat charge oppose maintenant `CasterHasNotMoved` **comme le natif** (`d["after"]`, precondition
   deja mesuree par le test), contrefactuel construit par RETRAIT explicite du flag.

**Tests rejoues, tous verts** : `test_heavy_weapon_moved_gate_live` (2), `test_ability_target_gate_live`
(13), `test_damage_roll_live` + `test_runner_attack_live` + `test_daemon_extra_block_live` (6),
`test_additional_hits_amount_bounds_live` + `test_additional_hits_rounding_live` +
`test_ability_hits_channel_live` (13), `test_on_fire_damage_migration_live` (2),
`test_runner_move_live` (2+1 xfail), `test_case231_charge_forcecrit_live` +
`test_ambush_migration_live` (11).

**Echecs PRE-EXISTANTS, non causes par ce fix** (verifie en remisant le fix et en rejouant a
l'identique sur la base) : `test_avalanche_of_muscle_live.py` — 3 echecs, messages identiques avec et
sans le fix (`aucun delta positif charge vs no-charge [0,0,0,0]`, `bonus_per_hit: 599`). Le gate
`IsCharging` de cet effet ne discrimine plus sur ce montage. **Hors perimetre, mais reel.**

> **FERME le 2026-07-28 (#o10-a).** Ce n'etait pas le CODE : c'etait l'ATTENDU. Bisect —
> `64d875d` 3 PASSED, `964dd15` (case-r32) 3 FAILED. `964dd15` a remplace le proxy `has_moved` par le
> predicat natif `IdunBattle.Core.Services.BattleQuery$$IsCharging` sans retirer le test qui gatait par
> le proxy. Le fichier a ete SUPPRIME : sa methode (snapshot APRES le pas + charge DECLAREE par
> `set_moved_flag`) etait structurellement incapable de reproduire le 2e terme du predicat
> (`UnitComponent.ChargedUnitIds@+0x190`, qu'aucun RPC n'exposait alors), et il n'exercait que les deux
> regimes ou proxy et predicat COINCIDENT. Le verrou vivant du meme effet 1025 est
> `test_ischarging_extra_damage_live.py` (3 regimes dont le DISCRIMINANT, 2 couples board/seed).
>
> **MAJ #230 (2026-07-29)** : le canal manquant EXISTE desormais (`combatSnapshot.chargedUnitIds`,
> `f790ff4`) et `load_state` le consomme, donc un snapshot post-pas PORTE la charge — a condition
> d'etre pris MI-ACTIVATION. C'est `test_load_state_turn_state_live.py` qui exerce cette voie.
> Ce qui reste definitivement faux dans la methode retiree : **declarer** la charge par le proxy
> `set_moved_flag` au lieu de la **lire**.

## 6. Ce qui n'est PAS couvert

1. **Residu de CARDINALITE du canal #179 sur ce meme porteur** (distinct, ANTERIEUR, inchange par ce
   fix). Sur le montage d'origine, attaques 2 et 3 : le live fait 9 coups la ou l'offline en fait 8
   puis 6 — il manque le groupe `LetTheGalaxyBurn` (round `RuinousSalvo`) puis LUI ET le groupe
   `FleshmetalGunsWarpHail` (`addhits=None` alors que le live emet 2 coups de profil 19). Mesure
   identique avant et apres le fix. Non reproduit sur `C2_02`/`31337`, ou les groupes Melta et Flame
   sortent bien : le declencheur exact n'est pas etabli. Entree backlog ouverte.
2. **Les flags AUTRES que `Moved`/`Teleported` sont desormais seedes eux aussi** (`TurnFinished`,
   `ActiveAbilityUsed`, `NoActionAvailable`, …), ce qui est l'etat REEL de la capture mais n'a ete
   confronte que par les tests ci-dessus. Aucun test de turn-flow n'a bouge, mais la surface est plus
   large que le seul cas mesure.
3. **La branche `(df@0xa0 & !HasFlag(TurnFinished)) | !df@0xa0)`** du meme trigger n'est pas portee
   (`df@0xa0` est un trigger partage non identifie) — elle etait deja absente avant ce fix.
4. **La branche Teleported n'est pas confrontee live** : elle est lue au decompile et portee, mais
   aucun montage n'a fait TELEPORTER un porteur `HeavyWeapon` (il faudrait un porteur cumulant le
   trait et un `TeleportStrike`/`FearOfTheUnseen`).
