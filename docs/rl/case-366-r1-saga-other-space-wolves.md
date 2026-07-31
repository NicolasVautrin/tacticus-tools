# case-366-r1 — `1224 SagaOfTheWarriorBorn_OtherSpaceWolves` : UNE classe native pour DEUX `EffectType`

> Dernier des trois residus NOMMES du gisement des 96 (`case-366-gisement-96-effets.md` §3.3).
> Ses deux freres : `1107` (#373, canal STAT projete) et `1183` (#372, canal de LECTURE per-coup).
> **Ce cas n'est ni l'un ni l'autre** : il n'ouvre AUCUN canal — il ecrit UNE ligne de registre.

## 1. Le fait que ce cas etablit

`1224` n'est pas un CALQUE de `1223`, c'est **la MEME classe native**. Mesure, pas lecture de nom :

| ce qu'on compare | 1223 | 1224 |
|---|---|---|
| fabrique | `…EffectsDatabase.u003Cu003Ec$$u003CInitializeEffectsu003Eb__14_241` | `…b__14_242` |
| slot `Il2CppClass*` | `0x1833a1190` | `0x1833a1190` |
| ctor appele | `IdunBattle.Entities.Effects.Loki.SagaOfTheWarriorBorn_OwnerEffect$$.ctor` | idem |
| argument | **aucun** (corps bit-identique) | **aucun** |

Sur les **607** enregistrements d'`IdunBattle.Core.Services.EffectsDatabase$$InitializeEffects`
(formes A + B), ce slot ne couvre **que ces deux ids** — aucun jumeau. Le ctor porte une CONSTANTE
partagee : `mov edx, 0x49e` -> `IdunBattle.Core.AbilityOrEffect$$op_Implicit` ->
`IdunBattle.Entities.Effects.BaseEffect$$.ctor(this, abilityOrEffect, hasAutomaticActivation: 1)`,
avec `0x49e = 1182 = TriggeredAbilityType.SagaOfTheWarriorBorn`. **Les deux effets lisent donc la
meme config d'ability**, donc les memes `extraHits` (`ConfigVar` 0x13) et `extraCritDmg` (0x42).
Seul le PORTEUR change.

⇒ Le port pointe **la meme classe** depuis les deux entrees d'`EFFECT_CLASSES`. Ecrire une seconde
classe aurait introduit une distinction que le natif n'a pas — et divergerait au premier changement
de l'une des deux. C'est ce que verrouille `test_registry_shares_one_class`.

## 2. La POSE, relue au desassemblage

```
SagaOfTheWarriorBorn_KillAbility$$CreateTrigger
    = OnDeath(triggerOnOverkill: 1, triggerOnSteppable: 0)
    & get_OwnerIsActor
    & HasTrait(Target, 0x10 = UnitTrait.Hero)

SagaOfTheWarriorBorn_KillAbility$$CreateBehaviour
    = AddEffect( 0x4c8 = 1224,
                 BaseTriggeredAbility$$get_AbilityStateReference(owner),
                 source  = Owner,
                 targets = UnitsFromFaction( Friends(Owner, <pool partage>, OnlyAlive) - Owner,
                                             0xd = UnitFaction.SpaceWolves, OnlyAlive ),
                 <Nullable vide = aucune duree> )
```

`SagaOfTheWarriorBorn_InitAbility$$GetEffectType` = `0x4c7` (corps litteral) : c'est la face 1223,
posee d'emblee sur Ragnar.

⚠ **AUCUN RAYON — correction d'une mé-lecture.** `case-ischarging-hits-channel.md` §7 ecrivait
`Friends(owner@0x148, <radius @+0x80>, 1)`. `IdunBattleLogic.Entities.DSLSelectors$$Friends(of,
entities, selectionType)` n'a **pas** de parametre de distance : son 2e argument est le POOL
D'ENTITES a filtrer (un selecteur partage pre-construit par
`IdunBattleLogic.Entities.DSLSelectors$$InitializeShared`, champ `+0x20`), pas une portee.
Recoupe par l'i2, qui ne mentionne aucune distance : « If Ragnar has defeated one or more enemy
**Characters** this battle, friendly **Space Wolves** also gain this ability » (« Characters » =
libelle UI du trait `Hero`). L'effet touche donc **toute l'equipe Space Wolves vivante**, ou qu'elle
soit, et il est **permanent**.

## 3. Confrontabilite — HERO, voie directe

`unit_map find --ability SagaOfTheWarriorBorn` -> **1** unite, `spaceBlackmane` (Ragnar), au pool.
Receveurs possibles : les 5 autres Space Wolves `lineup`, dont **4 au pool** (`spaceHound`,
`spaceRockfist`, `spaceStormcaller`, `spaceWulfen` ; `spaceWolfPriest` hors pool, non requis).
Aucun montage relique/summon/npc. Receveur retenu : **`spaceWulfen`** <<Ulf>> — 3 coups d'arme, donc
`extraHits[50] = 3` **double** la salve (le rapport le plus large des quatre).

## 4. Le criterion, et le carre qui le tranche

> « Le port compte-t-il la contribution de `1224` comme le natif ? », mesure la ou l'effet MORD.

Une seule mesure ne suffit pas : il faut croiser la PRESENCE de l'effet et le REGIME de charge,
sinon on ne sait pas ce que l'accord atteste. `probe_366_r1_saga_other_space_wolves.py`, deux bras
x deux regimes, **live == offline bit-exact dans les quatre cases** :

| MC1_67 / seed 777 | 1224 PRESENT (Ragnar tue un Hero) | 1224 ABSENT (temoin) |
|---|---|---|
| **CHARGE** | **n=6** `[2679, 3724, 2879, 3771, 3273, 3750]` | n=3 `[3532, 3206, 3454]` |
| **STEP_ADJACENT** | n=3 `[3161, 3350, 3864]` | n=3 `[3011, 3786, 2652]` |

La ligne CHARGE isole l'EFFET (6 vs 3), la colonne PRESENT isole le GATE `IsCharging` (6 vs 3).
Generalisation `C1_25` / seed 31337 : meme carre, bit-exact (CHARGE n=6, ailleurs n=3).

**Vue ROUGE par mutation** (inscription retiree d'`EFFECT_CLASSES`), verbatim :

```
[KILL/CHARGE] LIVE    n=6 [2679, 3724, 2879, 3771, 3273, 3750]
[KILL/CHARGE] OFFLINE n=3 [2679, 3724, 2879]
[KILL/CHARGE] VERDICT hits DIVERGE | per_hit DIVERGE
```

Les 3 premiers coups sont **deja bit-exacts** : la divergence est localisee au NOMBRE de coups, pas
a leur valeur. Sous la meme mutation, le cliquet rend **3 failed / 5 passed** — tombent le test
structurel et les deux CHARGE (deux boards) ; `STEP_ADJACENT`, le temoin et le gate tri-etat restent
VERTS. La garde discrimine donc l'inscription de `1224`, et rien d'autre.

## 5. ~~Residu NOMME et MESURE~~ — FERME par #382 (`case-382-effect-source-ability-state.md`)

C'est le seul point ou `1224` sollicite le port autrement que `1223` — c'est ce cas qui a EXPOSE
l'ecart, #382 le ferme.

Le natif BAKE : `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$DefaultEffectBuilder` copie les
0x24 octets de l'`AbilityStateReference` dans `EffectComponent[+0x18..+0x38]` **a la pose**, et
`IdunBattle.Entities.Effects.BaseEffect$$GetAbilityStateReference` /
`IdunBattle.DSL.AbilityStateFromEffectSelector$$Select` relisent ce meme champ — donc l'etat de la
SOURCE. Pour `1223` porteur == source (inobservable) ; pour `1224` ils different **par
construction**.

Sous `buildNormalizedBC` les niveaux valent 50 des deux cotes -> ecart numeriquement nul, ce qui est
la raison pour laquelle aucune garde ne l'avait vu. DISSOCIES (MC1_67 / 777, Ragnar
`PassiveAbilityLevel=1`, Ulf 50), il apparait :

```
natif    n=4  [2679, 3724, 2879, 3771]                 # extraHits[1]  = 1  (niveau SOURCE)
port     n=4  [2679, 3724, 2879, 3771]                 # apres #382 : ability_level=1, mult=200
(avant)  n=6  [2679, 3724, 2879, 3771, 3273, 3750]     # extraHits[50] = 3  (niveau PORTEUR)
```

Le **multiplier de rarete** est dissocie lui aussi (source 200, porteur 180) — et il l'est meme sans
`--unit-stat`, donc il touche AUSSI la face CRIT (`extraCritDmg` est la seule variable scalee).

Repro : `probe_382_effect_source_ability_state.py` (montage dedie) ou
`probe_366_r1_saga_other_space_wolves.py --arms KILL --regimes CHARGE --extra="--unit-stat"
--extra="spaceBlackmane:PassiveAbilityLevel=1"`. Foyer du correctif :
`engine.entities.effects_state.baked_ability_state`, alimente par les DEUX seams (COMBAT
`runner/snapshot.py`, PREDICTION `playbook/scene.py`).

## 6. Ce qui n'est PAS couvert

* **La face POSE.** Le trigger `OnDeath & OwnerIsActor & HasTrait(Hero)` n'existe pas cote port :
  un moteur 100 % offline ne posera jamais `1224` de lui-meme. Ce cas ferme la **LECTURE** (quand le
  natif l'a pose, le port en compte la contribution) ; il ne ferme pas la pose.
* **La face CRIT de 1224 n'est pas mesuree live.** Le canal
  (`create_effect_crit_damage_bonus_for_attack`) est celui de `1223`, deja valide
  (`case-ischarging-crit-channel`), et la classe est PARTAGEE — la couverture est donc structurelle,
  pas experimentale. Le montage manquant : `--crit` sur le receveur (la normalisation met le crit a 0).
* ~~Le residu §5~~ — FERME par #382.
* **Les Space Wolves qui APPARAISSENT apres le kill** (summons) ne recoivent rien : le behaviour
  n'est evalue qu'au trigger. Conforme au natif, non teste.
* **Un seul receveur mesure** (`spaceWulfen`). Les trois autres receveurs du pool ne sont pas
  confrontes — la classe etant partagee et la magnitude ne dependant pas du receveur, le risque est
  structurel-nul, mais il n'est pas mesure.
