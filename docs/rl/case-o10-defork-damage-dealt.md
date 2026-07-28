# De-fork du vecteur `On(DamageDealt = 0x10)` — et le bug d'ORDRE qu'il cachait

**Verdict des deux questions binaires du cas.**

| question | reponse |
|---|---|
| **(a)** apres de-fork, `OnFireDamage` / `OnToxicDamage` declenchent-ils dans EXACTEMENT les memes cas qu'avant ? | **NON — et c'est le resultat.** Le declenchement change parce que l'ancien etait FAUX : mauvais MOMENT (apres les vecteurs de mort au lieu d'avant), et ensemble de sites d'emission plus etroit que le natif. |
| **(b)** la consommation de tirages est-elle INCHANGEE ? | **OUI en CARDINALITE** (meme nombre de tirages, meme `mti` final), **NON en AFFECTATION** (les tirages sont PERMUTES). L'affectation d'avant etait la mauvaise : mesuree live, elle se trompait **3 fois sur 6**. |

Le critere de renoncement (« si (b) ne peut pas etre tenu, laisse le fork ») **ne s'applique pas** :
le de-fork ne desynchronise rien — il remet chaque tirage a la place que le natif lui donne.

Build de reference : `gqfc5mff6c`.

---

## 1. Le fork, tel qu'il etait

Un concept natif, deux chemins offline :

* **le BUS** — `operations/triggers/dispatch/attack.py::damage_dealt_triggers`, emis par le chokepoint
  `AttackDamageOperation._apply_damage_pipeline` en mirror d'
  `IdunBattle.Operations.ApplyDamageOperation$$Execute` (sequence `On(0x3a)` -> `On(0xf)` ->
  `On(0x10)`), sous le gate « reduction de PV REELLEMENT appliquee > 0 » ;
* **les appels IMPERATIFS** de `_on_fire_damage_ability` / `_on_toxic_damage_ability`, poses APRES la
  resolution complete de l'attaque (`after_hit_normal_attack` cote NORMALE,
  `damage_ops/ability.py::execute_ability_attack` cote ABILITY), sans gate.

Or les deux abilities ecoutent bien `On(0x10)` — decompile relu, pas herite :

```
IdunBattleLogic.Entities.Abilities.Damage.Loki.OnFireDamageAbility$$CreateTrigger
    On(0x10, 1) & DamageProfileHasTrait(1 = OnFire)  & !TriggeringEffectIs(5)
IdunBattleLogic.Entities.Abilities.Damage.Loki.OnToxicDamageAbility$$CreateTrigger
    On(0x10, 1) & DamageProfileHasTrait(4 = OnToxic) & !TriggeringEffectIs(0x4dc)
IdunBattleLogic.Entities.Abilities.Active.Loki.FleshMetalGuns_TileEffectAbility$$CreateTrigger
    On(0x10, 1) & get_OwnerIsCaster & HasEffect(Self@0x148, 0x4c5 = WarpHail, 0, 6)
```

**Recensement AVANT** (`probe_o10_defork.py --tag before`, registres re-derives — jamais cites de
memoire) : le vecteur `On(0x10)` n'avait **1 seul auditeur** (`FleshmetalGunsTileEffectAbility`,
cle `FleshmetalGuns`) pour **6 sites d'emission**, tandis que les deux abilities de profil vivaient
sur **4 lignes d'appel imperatif** couvrant seulement 2 de ces sites.

---

## 2. Ce que le fork cachait : un bug d'ORDRE, mesure live

### 2.1 Le regime discriminant

`ApplyDamageOperation$$Execute` emet `On(0x10)` **avant** que la mort ne soit traitee
(`VerifyDeaths` -> `IdunBattle.Operations.KillUnitOperation$$Execute`). L'appel imperatif, lui,
tombait **apres**. Les deux ne different donc que si **un vecteur de mort consomme un tirage**.

Montage construit pour exercer exactement ca (`probe_o10_rng_order.py`) :

* attaquant **`tyranParasite`** (HERO, present dans `rl_duel build --list-pool`) — arme `Toxic`
  1 coup **et** passif `BarbedOvipositor`, dont
  `IdunBattleLogic.Entities.Abilities.Triggered.Loki.BarbedOvipositorAbility$$CreateBehaviour`
  consomme un `PickRandomly` sur `On(0 = UnitDeath)` ;
* victime **`astraBullgryn`** — ni `Mechanical` ni `Steppable`, donc elle passe les deux exclusions
  du `CreateTrigger` de l'Ovipositor ; `rl_duel build --hp-target 500` la rend one-shottable, donc
  le kill est DETERMINISTE ;
* la meme attaque est rejouee OFFLINE sur le MEME etat MT (`dumpRng`), dans les DEUX ordres
  reconstruits **analytiquement** par permutation de la liste de tirages OBSERVEE — on ne devine
  aucun tirage, on les remet dans un autre ordre.

### 2.2 Le chiffre

6 confrontations, 3 seeds (`777`, `31337`, `4242`), toutes avec kill + tirage de mort :

| seed / # | tirages observes | `Maybe` si ordre BUS | `Maybe` si ordre APRES-MORT | BUS | APRES-MORT | **LIVE** |
|---|---|---|---|---|---|---|
| 777 / 0 | `(5421,8134)=6655`, `(0,1)`, `(1,100)` | **9** | 31 | pose | rien | **pose** |
| 777 / 1 | `(3614,5423)=4363`, … | 36 | 87 | rien | rien | **rien** |
| 31337 / 0 | `(5421,8134)=6224`, … | 26 | **16** | rien | pose | **rien** |
| 31337 / 1 | `(3614,5423)=4149`, … | **24** | 46 | pose | rien | **pose** |
| 4242 / 0 | `(5421,8134)=7542`, … | 37 | 76 | rien | rien | **rien** |
| 4242 / 1 | `(3614,5423)=4389`, … | 36 | 68 | rien | rien | **rien** |

```
ordre BUS (place native)        : 6/6 d'accord avec le live
ordre APRES-MORT (le port)      : 3/6, desaccords DANS LES DEUX SENS
                                  (2 contaminations manquees, 1 de trop)
```

Les desaccords bilateraux **sont la signature** : un ordre systematiquement decale produirait un
biais dans un seul sens. Ici c'est une PERMUTATION.

### 2.3 Le piege de mesure — `delta mti` est AVEUGLE a une permutation

Les deux ordres consomment **exactement les memes tirages**, donc terminent sur le **meme etat MT**
(`mti` identique, `mt` identique — verifie : `MT == live` etait VRAI pour les deux modeles). Un
critere de non-regression fonde sur le **delta `mti` entre deux `dumpRng`** aurait donc conclu
« rien ne bouge » alors que le comportement observable changeait une fois sur deux.

> **A retenir** : `delta mti` prouve qu'aucun tirage n'a ete AJOUTE ou SUPPRIME. Il ne prouve RIEN
> sur l'ORDRE. Des qu'un changement peut PERMUTER deux tirages de meme cardinalite, il faut un
> observable AVAL (ici : le verdict de pose de `Contaminated`), pas l'etat du PRNG.

Apres de-fork, le port lui-meme est confronte : **port == live 6/6** (`--out rng-order-after-*`),
re-verifie apres rebase.

---

## 3. Le port

| face | fichier | mirror |
|---|---|---|
| registre GLOBAL (abilities sans owner) | `triggers/dispatch/registry.py::GLOBAL_TRIGGERS` + `triggers/dispatch/core.py::collect_global_triggers` | famille `IdunBattleLogic.Entities.Abilities.Damage.Loki.*` |
| consommateur FEU | `triggers/loki/fire.py::OnFireDamageAbility` | `OnFireDamageAbility$$CreateTrigger` / `$$CreateBehaviour` |
| consommateur TOXIC | `triggers/loki/on_toxic_damage.py::OnToxicDamageAbility` | `OnToxicDamageAbility$$CreateTrigger` / `$$CreateBehaviour` |
| payload du vecteur | `triggers/dispatch/attack.py::damage_dealt_triggers` (+`is_first_hit`, +`triggering_effect`) | `AbilityEntities+0x110`, `TriggeringEffectIs` |
| threading depuis les sites | `operations/damage.py::_apply_damage_pipeline` et ses 6 appelants | `ApplyDamageOperation$$Execute` |

**Pourquoi un registre GLOBAL et pas une inscription par unite.** Le `CreateTrigger` des deux
abilities ne porte AUCUN predicat d'owner : il ne teste que le PROFIL du coup. Une inscription
par entite les ferait firer N fois par evenement — et pour 1203 cela consommerait N `NextBool`.
La cardinalite est **mesuree** : le live en consomme **exactement un** par serie de coups
(`test_on_toxic_damage_live.py`, oracle = etat MT). `owner_is_global` fait donc bypasser les gates
unit-entity/alive **et** le cap par phase, qui est porte par le `TriggeredAbilityComponent` de
l'owner — inexistant ici.
**RESIDU** : le SITE natif de cette inscription unique n'est pas RE'd
(`IdunBattleLogic.Core.Services.Caches.AbilityAndEffectCache$$AddEntity` n'ajoute que les abilities
PORTEES par l'entite). C'est la cardinalite observee qui fonde ce registre, pas un decompile.

**`is_first_hit`** vient desormais de l'EVENEMENT et non d'un litteral. Le bus emet par GROUPE de
degat resolu (le natif emet par COUP) ; le drapeau signifie « ce groupe contient le coup d'index 0 ».
Phase d'arme et 1re serie sur une cible : `True`. Groupe de coups ADDITIONNELS (#179, index de
sortie > 0) : `False` -> aucun tirage 1203, mirror du court-circuit natif de
`IdunBattle.DSL.MultipleAbilityTrigger$$ShouldTrigger`. Degat DIRECT / DoT / knockback : `None`
(pas d'index de coup) -> `IsFirstHitInSeries` FAUX, mirror du `Nullable<int>` vide.

**`!TriggeringEffectIs(...)`** est desormais PORTE au lieu d'etre « structurellement satisfait » par
la place de l'appel — c'etait justifiable tant que le canal n'etait appele que depuis les vecteurs
d'attaque ; ca ne l'est plus depuis qu'il est sur le bus, que les DoT traversent aussi.

**Recensement APRES** : 3 auditeurs de `On(0x10)`, **0 site imperatif**.

### 3.1 Residu voisin FERME au passage

`on_fire_damage_tree` passe enfin `source_from_target=True`. La surcharge `AddEffect` a 5 arguments
passe un selecteur SOURCE **NUL**, et `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$Execute`
retombe alors sur la CIBLE : **la source du FEU est la TUILE, pas le caster**. Ground truth live du
JUMEAU (meme surcharge, memes arguments) : `FleshMetalGuns_TileEffectAbility` pose DespoiledGround
avec `source` = l'id de la tuile (#85, `probe_85_despoiled_ground.py`, runners 365 / 8514). Une
garde a ete ajoutee dans `test_on_fire_damage_migration_live.py` pour que le caster ne revienne pas.

---

## 4. L'ELARGISSEMENT — ce que le de-fork change EN PLUS de l'ordre

Le bus est emis depuis **6 sites** ; l'appel imperatif n'en couvrait que **2**. Ventilation des 4
sites neufs, et ce qu'ils font :

| site | couvert avant ? | effet du de-fork | natif ? |
|---|---|---|---|
| `damage_ops/normal.py` (phase d'arme) | oui | inchange (`is_first_hit=True`) | oui |
| `damage_ops/ability.py` | oui | inchange (`is_first_hit=True`) | oui |
| `additional_hits.py` (groupes #179) | **non** | pose de tile-effect au profil DU GROUPE ; **aucun** tirage 1203 (`is_first_hit=False`) | oui |
| `damage_ops/normal_like.py` (splash / on-appearance) | **non** | pose + 1 tirage 1203 si le profil est `Toxic` | oui |
| `damage_ops/normal_like.py` (`execute_direct`, DoT) | **non** | pose seulement ; pas de tirage (`is_first_hit=None`) | oui |
| `displace.py` (knockback) | **non** | **inerte** : `profile=None` | — |

**Le seul site neuf qui pose du FEU en pratique est celui des coups bonus**, et il a ete confronte
live : `blackObliterator` (« Volk ») n'a aucune arme `OnFire` (`Power` 4 coups, `HeavyRound` 6 coups
r3) mais son passif `FleshmetalGuns` accorde, un round sur trois, **+2 coups de profil `Flame`**
(`FleshmetalGunsRuinousSalvo` 0x4bc) — le seul profil portant `OnFire`. C'est le regime exact ou
l'ancien port ne POUVAIT PAS poser de feu et ou le nouveau le peut.
Garde : `test_on_fire_damage_migration_live.py::test_on_fire_from_bonus_hit_group_agrees_with_live`
— **5 confrontations, verdict de feu offline == live 5/5** (dont 2 poses).

Le site `normal_like` avec un profil `Toxic` (attaque ON-APPEARANCE d'un summon, ex.
`admecSmnVanguard` 3 coups `Toxic`) ajouterait un tirage la ou l'ancien port n'en faisait aucun.
Il est **conforme au natif** mais **non confronte** : le porteur n'est pas activable par le joueur
(deja etabli et mesure dans `case-1203-on-toxic-damage.md` §5.2, `probe_1203_toxic_multihit.py`).

---

## 5. Validation

* `probe_o10_rng_order.py` x3 seeds, AVANT : bus 6/6, apres-mort 3/6. APRES : **port 6/6**
  (re-verifie post-rebase sur `a493b7b`).
* `probe_o10_defork.py` `--tag before` / `--tag after` : auditeurs de `On(0x10)` **1 -> 3**, sites
  imperatifs **4 -> 0** ; scenario NON letal **bit-identique** (memes tirages, meme ordre, meme
  `mti`, meme pose) ; scenario letal = la permutation attendue, et rien d'autre.
* Tests live re-joues verts, **apres rebase** : `test_on_fire_damage_migration_live` (2, dont la
  garde d'elargissement et la garde de SOURCE), `test_on_toxic_damage_live` (7),
  `test_despoiled_ground_live` (5), `test_rad_bombardment_live` (4), `test_damage_roll_live` +
  `test_runner_attack_live` + `test_daemon_extra_block_live` (7), `test_lot_pose_live` +
  `test_let_the_galaxy_burn_live` (6). Avant rebase, egalement verts : `test_damage_ability/block/
  crit_live`, `test_rad_saturation_live`, `test_tile_effect_dynamics_live`,
  `test_brazier_of_holy_fire_live`, `test_control_edict_live`, `test_death_nova_live`,
  `test_tile_leaf_unit_traits_live`. `probe_120_pre_unit_ability_fork.py` : `PROBE OK`.

---

## 6. Ce qui n'est PAS couvert

1. **Le site natif d'inscription des abilities `Abilities.Damage.Loki`** (§3) : non RE'd. Le registre
   GLOBAL est fonde sur la CARDINALITE mesuree live, pas sur un decompile de la construction du cache.
2. **Le site `normal_like` a profil `Toxic`** (§4) : conforme au natif, non confronte faute de
   porteur activable.
3. **`triggering_effect` n'est pas encore threade depuis les DoT** (`FireTileDoT` route par
   `execute_ability_attack` avec le profil `Flame`) : le gate `!TriggeringEffectIs(5)` est donc
   toujours inerte sur ce chemin. Sans consequence observable — la re-pose du MEME effet sur la MEME
   tuile est un no-op `already-present` d'`AddEffectOperation` — mais c'est un residu nomme.
4. **Le conjoint `hitInfo+0x94` du gate d'emission** de `On(0x10)` : toujours non modelise (residu
   herite de #85 ; il ne peut que RESTREINDRE l'emission native).
5. **Granularite par GROUPE et non par COUP** : le port emet le vecteur une fois par groupe de degat
   resolu. Pour la pose d'un tile-effect c'est sans consequence (idempotent) ; pour le tirage 1203
   non plus, parce que `IsFirstHitInSeries` ne laisse passer que le coup d'index 0. Un futur
   consommateur de `On(0x10)` qui aurait besoin des coups 2..N exigerait un vrai index de coup.
6. ~~**Les PV de `blackObliterator` divergent** (live 2668 / offline 1440 sur la 1re attaque du
   montage §4)~~ — **RESOLU**, cf. `case-o10-volk-moved-flag.md`. Ce constat etait juste sur un
   point (independant de ce canal) et trompeur sur l'autre : ce n'etait **pas** un ecart du modele
   de DEGAT. `drive_to_firing_position` DEPLACE Volk avant de tirer, et `load_state` ne
   reconstruisait pas `UnitFlag.Moved` (`combatSnapshot.units[].unitFlags` existait deja mais
   n'etait consomme que pour `PreventOverkill`) : le gate no-move de
   `IdunBattle.Entities.Effects.Loki.HeavyWeapon_ExtraDmgEffect$$CreateDamageModifier` ne mordait
   jamais et l'offline accordait un +25 % ranged que le natif refuse. Ferme par
   `snapshot._load_unit_flags` ; les PV sont desormais **assertes** par la garde d'elargissement
   quand `mt_same` (memes tirages => meme sequence de coups). Residu SEPARE, toujours ouvert : la
   CARDINALITE des groupes #179 de ce porteur (live 9 coups / offline 8 ou 6 sur les attaques
   suivantes) — backlog.
