# `#419-r1-tr14-r5-r2-r1-r2` — les presets `TargetingOptions` `statics+0x00` et `statics+0x80`

**Critere binaire** : les abilities qui recopient ces deux presets portent-elles leur masque
EFFECTIF, ou un masque absent / faux ?

**Verdict** : le REGISTRE (`ABILITY_CLASSES` + `TARGETING_OPTIONS_UNPORTED`) est JUSTE — une seule de
ses entrees consomme l'un des deux presets et son masque est bon. Le faux est ailleurs, dans la
**TROISIEME source de masque du port** : la constante UNIQUE de l'attaque normale.

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

C'est exactement le motif mesure en PR #126 (`0x4002` contre `0x4000` sur un meme lot) — mais sur
une AUTRE paire de presets : #126 opposait `statics+0x168` (rules du preset `+0x140`) a
`statics+0x68` (rules du preset `+0x40`).

⚠ **Les `+0x30`/`+0x38` du preset ne gouvernent RIEN** (avertissement #558, verifie ici) :
`IdunBattle.Entities.Abilities.AActiveAbility$$.ctor` recopie la struct dans `this+0x70..0xaf` puis
**ECRASE** `this+0xa0` et `this+0xa8` (= `options+0x30` / `options+0x38`) par deux delegues lies aux
slots de vtable `this+0x470` et `this+0x480`. Le masque `+0x28`, lui, est recopie TEL QUEL — c'est
donc bien la constante de la `.cctor` qui fait foi.
`IdunBattle.Entities.Abilities.ADeprecatedActiveAbility$$.ctor` (le socle des deux attaques normales
de cette tranche) ne fait que RECOPIER la struct et deleguer a `AActiveAbility$$.ctor` : meme
conclusion.

## 2. Les consommateurs, ventiles par FORME

Les deux presets ne sont consommes que par la forme **RECOPIE DE STATIQUE** (aucun `TargetingOptions$$.ctor`
appele) : le ctor lit `*(DAT_1833ffc10 + 0xb8)`, copie 8 qwords depuis `+0x00` (ou `+0x80`) dans une
struct locale, et la passe a `ADeprecatedActiveAbility$$.ctor` / `AActiveAbility$$.ctor`.

Forme canonique, `IdunBattleLogic.Entities.Abilities.Active.Loki.Loki_NormalBossAttackAbility$$.ctor` :

```
lVar1     = *(longlong *)(DAT_1833ffc10 + 0xb8);
local_48  = *(undefined8 *)(lVar1 + 0x80);   ... uStack_10 = *(undefined8 *)(lVar1 + 0xb8);
ADeprecatedActiveAbility$$.ctor(this, &local_48, 0);
```

### `statics+0x00` -> `0x4002` — 18 consommateurs

`69 Loki_NormalAttack`, `1046 TemplarInitiateNormalAttack`, `1063 FireAndReposition`,
`1073 StaffOfStars`, `1086 ProperKilly_NormalAttack`, `1120 FeederTendrils_NormalAttack`,
`1123 OptimizedGait_NormalAttack`, `1128 Boltstorm_NormalAttack`, `1138 Wraithcannon_NormalAttack`,
`1162 AncientFury_NormalAttack`, `1178 ElectroShock_NormalAttack`,
`1182 RighteousRepugnance_NormalAttack`, `1205 TalonOfHorus_NormalAttack`, `1220 Fealty_NormalAttack`,
`1228 SternguardFocus`, `9006 TestDirectKill`, `9008 TestDirectForceOverkill`, `9013 TestMultiHitAttack`.

### `statics+0x80` -> `0x4000` — 7 consommateurs

`3 ChainLightning`, `9 HolyBolt`, `13 Test`, `17 NormalAttack`, `1004 MortisRound`,
`1030 Loki_NormalBossAttack`, `1114 BlisteringAssault_NormalAttack`.

**Une seule de ces 25 entrees est au registre du port : `1004 MortisRound`, et son masque
`TARGETING_OPTIONS` vaut deja `0x4000`.** Les 24 autres n'ont aucune classe dans `ABILITY_CLASSES`
ni dans `TARGETING_OPTIONS_UNPORTED` — pour elles la regle « entrer au registre avec son masque »
n'est pas violee : elles n'y sont pas entrees.

## 3. Ou est le FAUX : la troisieme source de masque

*(en cours de redaction)*
