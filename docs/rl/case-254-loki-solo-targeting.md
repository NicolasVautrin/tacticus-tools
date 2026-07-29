# case-254 — masques de ciblage des QUATRE abilities a module unique (1076 / 1113 / 1118 / 1151)

**Statut : RESOLU.** Les quatre masques sont poses, decomposes bit a bit et **confrontes live**
(accord natif/port **48/48 lignes** sur deux couples board/seed, **34 casts illegaux** que `master`
acceptait). Un bug du module PARTAGE a ete decouvert en chemin (cf. §4).

**Ce lot SOLDE la campagne « une ability entre au registre AVEC son masque »** : la liste
d'exemption `SANS_TARGETING_OPTIONS` du cliquet passe a **ZERO entree** — 94 abilities au registre,
94 avec masque. Le cliquet reste en place comme garde-fou : toute ability neuve entrant sans masque
fera desormais echouer `test_targeting_options_ne_regresse_pas`.

Le reliquat de la campagne « une ability entre au registre AVEC son masque » hors des lots de
module : quatre abilities, quatre fichiers distincts, et — c'est le fait notable — **quatre formes
de ctor differentes sur quatre abilities**.

| id | ability | forme de ctor | masque EFFECTIF | `TargetingRange` | `forceMeleeTarget` | attackType |
|----|---------|---------------|-----------------|------------------|--------------------|------------|
| 1076 | `MV71SniperDroneSquadAttack` | **4 — factory nommee** | `0x4002` | `TargetingRange statics+0x00` = ADJACENT_IF_MELEE_CASTER | `2` = IfRangedCaster | 1 SummonAndAttackTarget |
| 1113 | `Stormcaller` | **2 — preset + flags** | `0x200004002` | `statics+0x18` = FROM_CONFIG (3) | `1` = RangedBool.False | 0 DirectTargetAttack |
| 1118 | `DoctrinaImperatives` | **1 — flags directs** | `0x80` | `statics+0x60` = RANGE_SELF (0) | `1` = RangedBool.False | 2 Others |
| 1151 | `TheQuickening` | **2 — preset + flags** | `0x806000042` | `statics+0x18` = FROM_CONFIG (2) | `1` = RangedBool.False | 2 Others |

Les quatre `AbilityAttackType` etaient DEJA justes dans `attack_type.py` — relus au 3e argument de
`AActiveAbility..ctor`, aucune divergence a signaler.

---

## 1. La RE, ctor par ctor

### 1076 — la FACTORY NOMMEE, deuxieme occurrence connue

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.MV71SniperDroneSquadAttackAbility$$.ctor`
n'ecrit aucun champ et ne recopie aucun preset :

```
opts = TargetingOptions$$CustomLokiNormalAttackOptions(&opts, 2)
ALoki_NormalAttackAbility..ctor(this, &opts, 1, 0)     # 3e arg FORWARDE a AActiveAbility..ctor
```

`IdunBattle.Core.Services.TargetingOptions$$CustomLokiNormalAttackOptions` recopie le preset
`<TargetingOptions statics>+0x00` champ par champ et **COMBINE** `Rules`, exactement comme la
surcharge « preset + flags » :

```
*param_1                  = *puVar2                       # isSelfCasting
*(param_1+0x08/0x10/0x18) = *(puVar2+0x08/0x10/0x18)      # TargetingRange (0x18 octets)
*(param_1+0x20)           = *(puVar2+0x20)                # forceMeleeTarget
*(param_1+0x28)           = *(puVar2+0x28) | param_2      # <- LE OU
```

`IdunBattle.Core.Services.TargetingOptions$$.cctor` ecrit ce preset : `rules = 0x4002`,
`range <- TargetingRange statics+0x00`, `forceMeleeTarget = 2`. Le masque effectif est donc
`0x4002 | 2` = **`0x4002`** — l'argument `2` etait deja pose par le preset. C'est le CALCUL qui le
dit, pas une supposition : la factory aurait tres bien pu ajouter un bit neuf.

C'est le **deuxieme** exemplaire de la forme 4 apres `TargetingOptions$$SelfCastIfEnemyInCustomRange
Options` (1000, decouverte par #248) ; la recette « chercher le seul `TargetingOptions$$<Xxx>Options`
appele » a fonctionne telle quelle.

### 1113 — preset `+0x180` + flags `0x200000000`

```
opts <- <TargetingOptions statics>+0x180 .. +0x1bf
TargetingOptions..ctor(&opts, &preset, 0x200000000, 0)    # surcharge PRESET + FLAGS
AActiveAbility..ctor(this, &opts, 0, 0)
```

La surcharge PRESET+FLAGS (`*(dst+0x28) = param_3 | *(preset+0x28)`) donne
`0x200000000 | 0x4002` = **`0x200004002`**.

- `0x2` `TargetMatchesDynamicRule` — regle-delegue non portee -> defaut 0 (PERMISSIF).
- `0x4000` `TargetIsEnemy` — PORTEE.
- `0x200000000` `TargetIsNotAnObject` (bit 33) — regle du filtre statique NON portee ; elle refuse
  une cible portant le trait `0xd Object`. **CORRIGE (#249) : 1113 n'est PAS le seul porteur du
  registre, ils sont QUATRE** — 1029 `Drachnyen` (`0x200004000`), 1113 `Stormcaller`
  (`0x200004002`), 1202 `VigilanceEternal` (`0x206004002`), 1214 `Hailstrike`
  (`0x200240000400`). Le compte se re-derive avec
  `scripts/python/probe_249_unported_rule_carriers.py` ; ne pas le citer de memoire.

Piege ecarte : le preset `+0x140` (1014 ArmoriumCherub) porte le MEME `rules = 0x4002` et le MEME
`RANGE_FROM_CONFIG`, et ne differe que par `forceMeleeTarget` (`0` = RangedBool.**True** contre `1` =
False ici). Recopier la voisine aurait donne le bon masque et le **mauvais regime de portee au
contact**.

### 1118 — `AddCaster` seul, et c'est la PORTEE qui gate

```
TargetingOptions..ctor(&opts, 1, &<TargetingRange statics>+0x60, 1, 0x80, 0, 0, 0)
AActiveAbility..ctor(this, &opts, 2, 0)
```

`0x80` = `AddCaster` **seul** : **aucune regle de refus** dans le masque. Ce bit est le
court-circuit du volet self-cast — `IdunBattle.Core.Services.TargetingQuery$$GetCasterNotAddedReason`
commence par `if ((char)rules < 0) return valide;`, c'est-a-dire le test du **bit 7**. Le cast sur
soi est donc VALIDE cote natif, et le `0` que le port rend est exact (meme exception que
`CalibaniteGreatsword`).

Tout le gate vient du `TargetingRange statics+0x60` = `RANGE_SELF` (`overrideRange = 0`) : une cible
autre que le caster tombe sur `range.Value(0) < d(>=1)` -> `TargetIsInRange`. **Le masque seul
n'aurait rien refuse** — c'est l'illustration la plus nette de la regle « `range` accompagne toujours
le masque ».

### 1151 — le piege « preset + flags », VERIFIE et non suppose

```
opts <- <TargetingOptions statics>+0x200 .. +0x23f
TargetingOptions..ctor(&opts, &preset, 0x806000000, 0)
AActiveAbility..ctor(this, &opts, 2, 0)
```

`0x806000000 | *(statics+0x228)` = `0x806000000 | 0x42` = **`0x806000042`** :

- `0x2` `TargetMatchesDynamicRule` — non portee.
- `0x40` `TargetIsTile` — **le domaine du cast**, et il n'est PAS dans le litteral visible : recopier
  `0x806000000` aurait perdu le fait meme que 1151 cible une TUILE.
- `0x2000000 | 0x4000000` = `AllowObscuredTarget` (composite de l'enum) — PERMISSIF.
- `0x800000000` `CasterHas1Tiles` (bit 35) — volet CASTER, non porte.

---

## 2. Confrontabilite des porteurs — et le piege du recensement de 1076

Ventilation lue dans le gameconfig, puis **confrontee live** :

| id | porteurs `lineup` | `npc` | au pool `--list-pool` |
|----|-------------------|-------|-----------------------|
| 1113 | `spaceStormcaller` | `spaceStormcaller_LHE` | oui |
| 1118 | `admecMarshall` | 5 `admecBossMarshall*` | oui |
| 1151 | `bloodMephiston` | — | oui |
| 1076 | **AUCUN** | **AUCUN** | — |

**Le balayage des 669 kits par ID d'ability ne rend RIEN pour 1076.** `tauMarksman` n'y porte que le
PASSIF `MV71SniperDroneSquad` (id `null`) — et le recensement par sous-chaine de nom aurait donc
« trouve » un porteur qui n'en est pas un au sens du gameconfig. Conclure « non confrontable » sur
cette base aurait pourtant ete **FAUX** :

- `decisionView(allAbilities = true)` expose **bel et bien 1076 sur `tauMarksman`** (`usable: null`,
  `cooldown: null`) ;
- `abilityReason(casterId = tauMarksman, abilityType = 1076, targetId = ...)` **traverse la
  cascade** et rend les vraies regles rompues.

⚠ Le cas RESSEMBLE au piege MoW de #249 — `abilityState` est **null**, l'ability etant une
`...Abilities.Triggered.` sans `ActiveAbilityComponent` — mais il en **DIFFERE** :
`IdunBattle.Core.Services.AttackQuery$$GetInvalidTargetReason` ne court-circuite PAS sur `0x1` ici.
En revanche `abilityTargets` rend bien un ensemble VIDE (`targetCount = 0`), donc c'est l'oracle
`abilityReason` — et lui seul — qui mesure quelque chose. **La lecon a retenir : `abilityState =
null` n'implique pas « oracle inexploitable » ; il faut essayer les DEUX oracles avant de conclure.**

---

## 3. Validation live — 48/48, deux couples, seuils encadres serre

`scripts/python/probe_254_loki_solo_targeting.py` (le probe MESURE) /
`scripts/python/tests/engine/runner/test_loki_solo_targeting_live.py` (le test GARDE).

Couples : **`MC1_67`/777** et **`C4_09`/31337**. Geometrie **conduite** (`--no-ai`, les deux camps
deplaces jusqu'a la configuration voulue), jamais subie.

| ability | couple 1 | couple 2 | seuil encadre | casts illegaux fermes |
|---------|----------|----------|---------------|------------------------|
| 1076 | 4/4 | 4/4 | d=3 accepte / **d=4 refuse** | 3 + 3 |
| 1113 | 5/5 | 5/5 | d=3 accepte / **d=4 refuse** | 4 + 4 |
| 1118 | 5/5 | 5/5 | d=0 accepte / **d=1 refuse** | 4 + 4 |
| 1151 | 9/9 | 11/11 | d=2 accepte / **d=3 refuse** | 5 + 7 |

**Zero ligne GAP** : aucune regle non portee n'a eu a etre invoquee pour expliquer un ecart — le
`TargetMatchesDynamicRule` des trois abilities qui le posent n'a jamais mordu cote natif sur ces
montages, et `TargetIsNotAnObject` non plus (aucun decor interrogeable).

### Contrefactuels par champ — dont un champ INERTE, dit comme tel

Pour chaque ability, on rejoue la cascade avec le champ neutralise et on compte les verdicts
DEPLACES **dans les deux sens** :

| ability | `sans <bit>` | `sansRange` | `forceMeleeTrue` |
|---------|--------------|-------------|-------------------|
| 1076 | `TargetIsEnemy` : 2 | 1 | **0 — INERTE** |
| 1113 | `TargetIsEnemy` : 2 | 2 | **0 — INERTE** |
| 1118 | (aucun bit porte) | 4 | **0 — INERTE** |
| 1151 | `TargetIsTile` : 1 a 3 | 4 | **0 — INERTE** |

⚠ **`forceMeleeTarget` n'est valide par AUCUNE de ces mesures.** Le forcer a `RangedBool.True` ne
deplace aucun verdict, parce que le second clamp de `GetRange` exige
`attackQuery.ShouldApplyRangedInMelee(caster, casterTiles, true)` — donc un ENNEMI AU CONTACT du
caster, ce qu'aucun de ces montages n'a (la geometrie y separe justement les distances pour encadrer
les seuils). La valeur posee est celle du decompile ; son EFFET reste non confronte. C'est dit ici
plutot que maquille en validation.

---

## 4. Le bug decouvert en chemin — le volet portee etait INERTE pour toute cible-TUILE

> **CONVERGENCE INDEPENDANTE.** Ce diagnostic a ete pose DEUX FOIS, en parallele et sans
> coordination : ici par 1151 (branche DISTANCE, `RANGE_FROM_CONFIG` = 2) et par le lot `summon`
> (#251) via `MasterOfTheTutelaries` 1096 / `AberrantHypermorph` 1166 (branche `only_adjacent`,
> `RANGE_ADJACENT`). Les deux ont abouti a la MEME correction, sur les DEUX branches du meme
> couple. Le correctif de `master` etant strictement plus large (il applique aussi `entity_tiles`
> au CASTER), c'est lui qui a ete retenu au rebase ; la mesure ci-dessous reste la preuve
> independante de la branche DISTANCE, que le lot `summon` n'exercait pas.

C'est 1151 qui l'a exhibe : **4 lignes MISMATCH** au premier run (natif `TargetIsInRange` sur les
tuiles a d=3 et d=4, port `0`), et `sansRange` ne deplacait rien — signature d'un gate desarme, pas
d'une mauvaise valeur.

`engine/runner/abilities/targeting.py`, `get_range_broken_rule` resolvait la cible ainsi :

```python
dst_feet = get_unit_feet(state, int(target_id))     # mirror de GetUnitFeetIds
```

`components.get_unit_feet` ne couvre que la **3e branche** d'`EntityExtensions$$IterateTiles`
(l'empreinte d'une UNITE) et rend `[]` sur une TUILE -> `return 0`, aucun gate. Or le decompile de
`IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason` (surcharge 7 arguments) calcule la
distance sur la variable `pcVar12` = **la cible RESOLUE** :
`IdunBattle.Entities.EntityExtensions$$GetMainTile(target)` sous `TargetIsTile`,
`IdunBattle.Entities.UnitExtensions$$GetUnit(target)` sinon.

Le mirror correct existait deja dans le meme module — `entity_tiles`, dont la docstring **decrivait
exactement ce faux negatif** pour les regles d'adjacence :

> `components.get_unit_feet` mirror `GetUnitFeetIds`, qui ne couvre QUE la 3e branche et rend `[]`
> sur une tuile : s'en servir ici DESARMERAIT les deux regles d'adjacence pour toute ability
> tile-target.

Le meme piege s'etait referme sur l'autre volet. **Correctif : une ligne**
(`dst_feet = entity_tiles(state, target_id)`, plus la meme chose cote caster dans la version de
`master`). Pour une cible UNITE les deux fonctions coincident (1re branche d'`entity_tiles` =
`get_unit_feet`), donc rien d'autre ne bouge.

### Portee du correctif — les CINQ abilities tile-target a gate de portee reel

| id | ability | `TargetingRange` | etat avant | etat apres |
|----|---------|------------------|------------|------------|
| 1017 | `FragBomb` | `overrideRange = 1` | gate INERTE | arme |
| 1092 | `DarkTalonStrike` | FROM_CONFIG | gate INERTE | arme |
| 1116 | `RadBombardment` | `overrideRange = 1`, onlyAdjacent | gate INERTE | arme |
| 1151 | `TheQuickening` | FROM_CONFIG (2) | gate INERTE | arme |
| 1219 | `IronkinSteeljack` | RANGE_ADJACENT | gate INERTE | arme |

Les dix autres abilities tile-target du registre portent `RANGE_WHOLE_BOARD` (ou aucun range) : le
filtre statique ne teste alors RIEN, elles sont inchangees.

**Non-regression re-jouee** (c'est le lot « ce que mon fix pourrait casser », pas une selection de
confort) : `test_ironkin_steeljack_live.py`, `test_rad_bombardment_live.py`, `test_frag_bomb_live.py`,
`test_dark_talon_strike_live.py`, `test_the_quickening_live.py`, plus les quatre tests de ciblage
generiques (`test_targeting_masks_live.py`, `test_targeting_options_masks_live.py`,
`test_targeting_adjacency_rules_live.py`, `test_targeting_options_sources.py`) et le cliquet
`test_ability_registry_ratchet.py`. **55 tests passent, aucune regression.**

> Le fait qu'aucun test n'ait rougi AVANT le correctif est la preuve du mode de defaillance :
> un gate desarme ne casse rien, il ACCEPTE. Seule une confrontation a l'oracle natif le montre.

---

## 5. Ce qui n'est PAS couvert

1. **`forceMeleeTarget`** — pose au decompile sur les quatre, **effet non confronte** (cf. §3).
   Le fermer demande un montage avec un ennemi AU CONTACT du caster ET une cible hors portee, pour
   les abilities `IfRangedCaster` (1076) et `RangedBool.False` (les trois autres).
2. **`TargetMatchesDynamicRule`** (1076, 1113, 1151) — la regle-delegue
   `<X>Ability$$GetDynamicInvalidTargetReason` n'est portee pour aucune des trois. Aucun ecart
   observe sur ces montages, mais l'absence d'ecart n'est pas une preuve d'inertie : la regle native
   peut mordre sur un etat que ces montages n'atteignent pas.
3. **`TargetIsNotAnObject`** (1113) — regle du filtre statique non portee. Il faudrait une cible
   portant le trait `0xd Object` pour la mesurer. **Le compte de porteurs ecrit ici etait FAUX** :
   « seul porteur du registre » — ils sont QUATRE (1029, 1113, 1202, 1214), corrige par #249. Un
   « seul porteur » faux fait classer un gap comme anecdotique ; le compte se RE-DERIVE
   (`probe_249_unported_rule_carriers.py`), il ne se cite pas.
4. **`CasterHas1Tiles`** (1151) — volet CASTER, non porte. Inerte de fait sur tout heros a empreinte
   1, mais non confronte sur un caster multi-pieds.
5. Le **behaviour** des quatre abilities n'est pas retouche : ce cas ne porte QUE la face
   ciblage (le gate), pas l'execution.
