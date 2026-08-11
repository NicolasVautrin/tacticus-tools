# #932 — `Deathwing` (`darkaTerminator` « Baraqiel ») : quatre faces, une DEAD, une inexistante

Passif `TriggeredAbilityType 0x4dd = 1245`, effet `EffectType 0x526 = 1318`. Porteur HERO **du
pool** (`rl_duel build --list-pool`, rank 17) — aucun montage, aucune injection.

i2 (`Abilities/Deathwing_CurrentLevelDescription`) : « Each time Baraqiel **blocks damage during an
attack**, all further incoming damage is reduced by `{dmgReduction}` and the damage Baraqiel deals
with melee or *Plasma Cannon* attacks is increased by `{extraDmg}` **for 1 round**. This effect is
doubled against Chaos enemies or when standing adjacent to another friendly Dark Angel. »

## 1. Le compte des FACES — l'audit en annonçait UNE, il y en a QUATRE

| face | artefact natif | verdict |
|---|---|---|
| DÉCISION owner, MOUVEMENT | `IdunBattle.AI.Playbook.Loki.DeathwingPlaybook$$GetAdjacentFriendUtility` | **PORTÉE** (`TRIGGERED_MOVE_PLAYBOOKS`) |
| DÉCISION owner, branche ENNEMIS | `...DeathwingPlaybook$$GetAdjacentEnemyUtility` | override EXPLICITE `return 0` — rien à porter |
| DÉCISION, ATTACK / REPAIR | `TriggeredAbilityPlaybook<T>$$CalculateAttackUtilityInStepsInternal` / `...Repair...` | **DEAD** (`yield return Fix64.op_Implicit(0)`) |
| DÉCISION non-owner | — | **N'EXISTE PAS** (aucune classe, aucune clé BC) |
| COMBAT, accumulation | `...DeathwingAbility$$CreateTrigger` + `$$CreateBehaviour` | **PORTÉE** (`ABILITY_TRIGGERS`) |
| COMBAT, magnitude ×2 | `...DeathwingEffect$$CreateEffect{DamageBonusForAttack,DamageMalusForDefense}` | **PORTÉES** (`EFFECT_CLASSES`) |

`docs/rl/kit-coverage.md` annonçait `missing = 1`.

**Ce que la table des symboles ne disait pas, et qui a fallu lire au `global-metadata.dat`** :
`DeathwingEffect` DÉCLARE **sept** méthodes, dont `CreateActiveCondition` (slot 62) et
`CreateTargetSelector` (slot 64) qui n'ont **aucun symbole** — corps fondus par l'ICF. Lus au bloc
`methodPointers` du PE, ancré sur le `.ctor` et indexé par la position metadata :

    CreateActiveCondition -> corps partagé avec `WisdomOfTheAncients_DamageReductionEffect`
                             = `return <DSLTriggers+0x70>` = `YesTrigger`  -> TOUJOURS ACTIF
    CreateTargetSelector  -> corps partagé avec `WhisperingWebEffect`
                             = `return <DSLSelectors+0x30>` = `Owner`      -> SELF-effect

Même voie pour `DeathwingPlaybook`, dont le bloc est `[.ctor, GetAdjacentFriendUtility, <ret 0>]` :
le `<ret 0>` **est** `GetAdjacentEnemyUtility` (le metadata le déclare au slot 14), et la classe
n'a **ni** cap (`GetMaxAdjacentFriendsToCount`) **ni** filtre (`FilterAdjacentFriends`).

## 2. Le PIÈGE d'homonymie — le parent se lit dans `classes.tsv`

    IdunBattle.Entities.Effects.Loki.DeathwingEffect         -> IdunBattle.Entities.Effects.BaseEffect
    IdunBattle.Entities.Effects.Loki.FuryOfTheAncientsEffect -> IdunBattle.Entities.Effects.HealBlockingEffect

Les deux `.ctor` partagent **le même corps** (ICF : `<base>..ctor(this, AbilityOrEffect(<type>),
true)`), et c'est celui que ghidra nomme `DeathwingEffect$$.ctor`. #927 avait suivi le pseudo-C dans
l'autre sens et y avait failli lire un effet de DÉGÂT là où l'i2 annonce un blocage de soin ; ici
c'est l'inverse exact. La table des CLASSES tranche, jamais le pseudo-C — et les quatre overrides de
dégât que `DeathwingEffect` déclare le corroborent.

Même forme pour le playbook : le pseudo-C de son `.ctor` appelle
`AdjacentToOwnerNonOwnerPlaybook<...>..ctor` (fold gshared), `classes.tsv` dit
`AdjacentUnitPreferenceTriggeredAbilityPlaybook`1`. C'est ce qui établit qu'il n'y a **pas** de face
non-owner — recoupé par une seconde source : `Utilities.Default.TriggeredAbilitiesNonOwner`
(25 clés) ne porte aucune clé `DEATHWING*`.

## 3. Les arbres (mirror 1:1)

```
DeathwingAbility$$CreateTrigger =
    On(EventTriggerType.Attack = 9, ownerNeedsToBeAlive: true) & get_OwnerIsTarget & WasBlock()

DeathwingAbility$$CreateBehaviour =
    If( HasEffect(Owner@+0x30, GetEffectType(), onlyActive: false, EffectTargetType.Both = 6),
        IncreaseEffectLevel( EffectFromOwner(Owner@+0x30, GetEffectType()), NULL, NULL ),
        AddEffect( GetEffectType(), AbilityStateReference, source = Owner, targets = Owner,
                   turns = TurnsFromRounds(1) ) )

DeathwingEffect$$GetDoubleEffectCondition(isDefense) =
    X = isDefense ? Actor@+0x40 : Target@+0x60
    ( HasTrait(X, UnitTrait 0x7ea = grande-alliance Chaos) & AreEnemies(X, Owner@+0x30, 0) )
    | AmountIsGreaterThanZero( UnitsFromFaction( AdjacentFriends(Owner@+0x30, unique: true, 3),
                                                 UnitFaction.DarkAngels = 0xa, 3 ) )

DeathwingEffect$$GetEffectAmount(base, isDefense) =
    If( GetDoubleEffectCondition(isDefense), Double(Multiply(base, EffectLevel(Effect@+0x38))),
        Multiply(base, EffectLevel(Effect@+0x38)) )

DeathwingEffect$$CreateEffectDamageBonusForAttack =
    ForAddition( get_OwnerIsActor & (IsMeleeAttack() | NOT IsNormalAttack()),
                 GetEffectAmount(ConfigVar(AbilityVariableType.extraDmg = 8), isDefense: false) )

DeathwingEffect$$CreateEffectDamageMalusForDefense =
    ForSubtraction( get_OwnerIsTarget,
                    GetEffectAmount(ConfigVar(AbilityVariableType.dmgReduction = 0x12), isDefense: true) )
```

**Les surcharges sont tranchées par leurs XREFS ENTRANTES**, jamais par le pseudo-C :
`UnitsFromFaction` overload **enum** (`0x180eb3d30`) et non `String` ; `AmountIsGreaterThanZero`
overload **`ITargetsSelector`** (`0x180ed5360`) ; `AdjacentFriends(unit, unique, selectionType)`
(`0x180eac2a0`) et non la variante B ; `IncreaseEffectLevel` **3-args** (`0x180ea3610`) et non la
4-args qu'utilise `FuelledByFury` ; `IsMeleeAttack()` / `IsNormalAttack()` 0-arg ; `On(type, bool)` ;
`AddEffect(..., turns: IAmountFormula)`.

### Ce que le natif dit et qu'aucune table ne disait

1. **Le gate de nature n'est pas symétrique.** La face ATTAQUE porte `IsMeleeAttack | NOT
   IsNormalAttack` — donc une attaque **normale à distance** n'en bénéficie pas, et **toute**
   attaque d'ability en bénéficie. Le natif ne nomme jamais `PlasmaCannon` : il dit « pas une
   attaque normale », ce qui est **plus large** que l'i2. La face DÉFENSE, elle, n'a **aucun** gate
   de nature ni de profil — contraste `TerminatorArmour_ReduceDmg`, que le même porteur transporte
   via son trait.
2. **`On(9)` est émis UNE FOIS PAR ATTAQUE** (`FinishAttackOperation$$Execute`), pas par coup : le
   stack monte de +1 par **attaque** bloquée. Le régime mono-coup est dégénéré.
3. **Aucun cap.** `IncreaseEffectLevel(amount = NULL, max = NULL)` — l'`amount` nul retombe sur
   `Const(1)`, le `max` nul désactive le clamp. Le gameconfig `Deathwing` n'a d'ailleurs **aucune**
   constante (`upgrades: null`, deux variables et rien d'autre).
4. **Le canal se lit aux OFFSETS**, pas au nom d'une fabrique : les deux corps construisent le
   `Nullable<EffectBonus>` à la main. `EffectBonus+0x10` = Addition (face attaque),
   `+0x18` = Subtraction (face défense) — relevés dans `EffectBonus$$ForAddition` /
   `$$ForSubtraction` / `$$ForPercentIncrease` (`+0x08`).
5. **Le trigger a TROIS termes, et c'est tout.** Ni gate de profil, ni gate de bouclier, ni
   exigence de dégât aux PV — alors que son voisin de forme `TerminatorArmour_ReduceDmg_Effect$$
   CreateTargetTrigger`, sur le MÊME porteur et le MÊME `On(9) & OwnerIsTarget`, en porte cinq.

## 4. Le substrat du DOUBLEMENT

Les trois nœuds sont threadés dans le contexte per-coup, **aux mêmes clés des deux côtés** (COMBAT
`runner/damage_model.py`, PRÉDICTION `playbook/prediction/`) — élargir un seul côté recréerait le
fork « ce que le moteur fait ≠ ce que la prédiction annonce » :

| nœud natif | face ATTAQUE (`att_ctx`) | face DÉFENSE (`attacker_ctx`) |
|---|---|---|
| `HasTrait(X, 0x7ea)` | `tgt_grand_alliance` | `grand_alliance` (**neuve**) |
| `AreEnemies(X, Owner)` | `tgt_team` + `att_team` (**neuve**) | `team` + `owner_team` (**neuve**) |
| `AmountIsGreaterThanZero(<sélecteur>)` | `adjacent_dark_angels_friends` (**neuve**) | idem |

Le compteur a un **foyer unique** par substrat — `runner/components.py::
adjacent_dark_angels_friends_count` (ECS) et `playbook/scene.py::Scene.adjacent_dark_angels_friends`
(tables de `Scene`) — sur le modèle d'`adjacent_taunted_enemies` (#911) et
d'`adjacent_friendly_mechanical_units` (#908). L'ARBRE, lui, vit dans la classe d'effet
(`adjacent_dark_angels_friends_selector`, doctrine #149).

**Tri-état STRICT** : clé absente ⇒ le disjoint concerné est **FERMÉ** (dégradation restrictive : on
sous-estime, on n'invente jamais un doublement) ; compteur `None` ⇒ ce disjoint seul se ferme, pas
l'autre (le natif rend un `op_BitwiseOr`).

## 5. Ce que la validation live a mesuré

`probe_932_deathwing.py`, board `MC1_67`, seed `4321`, rank 17. Cinq bras, chacun rejoué OFFLINE
depuis la capture prise avant la première attaque, avec le MÊME flux RNG, comparaison **coup par
coup** ET sur le **niveau** de stack (`EffectComponent+0x68`).

| bras | régime exercé | sain | mutant `trigger` | mutant `effet` | mutant `double` |
|---|---|---|---|---|---|
| `defense` | malus DÉFENSE + accumulation | **EGAL** (niveau 2 = 2) | DIVERGE (+808, niveau `None`) | DIVERGE (+808) | inerte — condition FAUSSE dans ce régime |
| `chaos` | disjoint 1 (attaquant Chaos) | **EGAL** (niveau 3 = 3) | — | DIVERGE (+808) | DIVERGE (+404) |
| `amiDA` | disjoint 2 (ami DA adjacent) | **EGAL** | — | — | DIVERGE (+808) |
| `attaque` | bonus ATTAQUE | **EGAL** | inerte — une seule attaque, rien à accumuler | DIVERGE (−935) | inerte — condition FAUSSE |
| `attaqueChaos` | bonus ATTAQUE **doublé** | **EGAL** | inerte | — | DIVERGE (−915) |

Les mutants inertes le sont **par construction du régime**, et chacun est nommé avec sa cause : un
mutant qui ne peut pas mordre dans un bras mord dans un autre. Aucun régime n'est laissé sans
mutant mordant.

Chiffres d'ancrage : `extraDmg[L50] = dmgReduction[L50] = 112`, multiplicateur de rareté **180**,
donc **202 par coup et par niveau** (`round(112 × 1.8)`), **404** quand la condition double.

### TROIS pièges de MONTAGE, tous mesurés

1. **Le porteur arrive en Deep Strike.** `TeleportStrike_TeleportingIn` = **`EffectType` 1035** le
   rend non-ciblable tant qu'il n'a pas agi, et l'attaque rend alors une **cascade VIDE** (`ok:
   true`, `mutated: false`) — pas un « 0 dégât ». Il faut **deux** appels d'`aiPlayByUnit` : le
   premier joue MON tour, le second celui de l'adversaire, et c'est celui-là qui le fait agir.
   ⚠ L'ordinal voisin **1572** est `TitanhammerSquad_ExtraBlockDamage` : le lire à sa place rendait
   un faux « sorti ».
2. **`maxPump = 40` rend l'IA INERTE.** Six tours joués, PV inchangés des deux côtés. Le défaut de
   `rl_duel.py` est **2000**. Le bras qui dépend de l'IA rendait `indisponible` pour une cause qui
   n'avait rien à voir avec le port.
3. **`--hp-target/--hp-player 400000` rend l'IA INERTE aussi** : elle ne porte aucune attaque. Le
   bras `attaque` tourne donc à PV **natifs** ; le bras `defense`, qui pilote ses propres attaques,
   garde le plafond.

### Le défaut du HARNAIS de mutation, trouvé par un mutant inerte

Les mutants étaient posés **après** `load_state`. Or `EFFECT_CLASSES` n'est lu qu'à la **création**
des instances (`EffectFactory.create`) : un `pop` postérieur arrive trop tard pour un effet déjà
présent au seed. Résultat mesuré : le mutant `effet` du bras `attaque` rendait **EGAL** — un faux
vert. Le bras `defense`, lui, mordait quand même, parce que son effet est posé **pendant** le
rejeu. Deux bras, deux régimes, un seul ordre correct : **mutants d'abord, `load_state` ensuite**.

## 6. Résidus NOMMÉS

* **`On(9)` du port ne couvre pas les attaques déclenchées par un TRIGGER** (tir d'overwatch,
  attaque supplémentaire) — divergence STRUCTURELLE préexistante, documentée dans
  `dispatch/attack.py::attack_damage_attack_triggers` et déjà au compte de `TerminatorArmour`.
  Conséquence ici : un blocage sur un tel vecteur ne monte pas le stack côté port. **MESURÉE** :
  avec `worldKharn` en attaquant, le stack natif monte à 3 là où le port reste à 2 (écart −4915).
* **`blackTerminator` fait diverger le port pour d'autres causes** : trait `LetTheGalaxyBurn`
  (effet 1477, `CreateAdditionalHits`) et `TerminatorArmour`. Écart **−1455** quand il attaque,
  **−35** quand il est frappé. Le MÊME bras rend `écart = 0` contre `worldKharn`,
  `deathBlightbringer`, `tauAunShi` et `astraBullgryn` — l'écart n'accuse donc pas `Deathwing`.
* **La face DÉCISION est évaluée à la position COURANTE, pas à la tuile candidate** :
  `Scene.adjacent_dark_angels_friends` lit `pos_by_id`, comme `adjacent_taunted_enemies` (#911).
  Un plan qui éloigne Baraqiel de ses frères prédit encore le doublement. La face COMBAT, elle,
  mesure la position réelle au moment du coup.
* **`DeathwingKnight`** (`TriggeredAbilityType` 1510, `EffectType` 1512) porte le MÊME corps à
  l'`EffectType` près (`DeathwingKnightAbility` n'override que `GetEffectType`) et la même forme de
  playbook (`DEATHWINGKNIGHT_AdjacentDAFriend`, = 10 elle aussi). Ses porteurs sont un npc
  (`darkaNpc3Terminator`) et un SUMMON (`darkaSmnTerminator`). NON PORTÉE — une ability par tranche.
