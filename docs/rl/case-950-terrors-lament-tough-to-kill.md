# #950 — `TerrorsLament` (`eldarJainZar`) et `ToughToKill` (`astraDreir`)

Deux passifs de kit, chacun le DERNIER item manquant de son kit. Portés, confrontés live (cinq bras,
égalité **à l'unité** port/natif), sous garde `tests/engine/test_950_terrors_lament_tough_to_kill_live.py`.
Montage et verdicts : `scripts/python/probe_950_terrors_lament_tough_to_kill.py`.

## 1. `TerrorsLament` — `TriggeredAbilityType 0x45e = 1118`

`IdunBattleLogic.Entities.Abilities.Triggered.Loki.TerrorsLamentAbility` : `BaseTriggeredAbility`
(**lu dans `frida/classes.tsv`**). Bloc `methodPointers` du PE ancré sur `$$CreateBehaviour` —
`[CreateTrigger = <0xec98b0>, CreateBehaviour = <0x12ba210>, .ctor = <0x2ea440>]`, les deux premiers
fondus par l'ICF (aucun symbole propre).

    $$CreateTrigger   = <DSLTriggers+0x30> = On(0x21 = AbilityInit) & <Yes@+0x70> & get_OwnerIsActor
    $$CreateBehaviour = AddEffect(0x45f, AbilityStateReference, targets = Owner@+0x30, turns = null)
                      + AddEffect(0x460, AbilityStateReference, targets = Owner@+0x30, turns = null)

La surcharge d'`AddEffect` est tranchée par l'**adresse de la cible du `call`** (`0xe9eca0`, quatre
paramètres, `turns: Nullable<int>`) et non par le pseudo-C : `turns` sans valeur ⇒ **permanent**, et
`targets = Owner` ⇒ **les deux effets vivent sur Jain Zar**.

Les deux effets (`: BaseEffect`), quatre corps chacun dont trois dédupliqués
(`.ctor` partagé, `CreateActiveCondition = <DSLTriggers+0x40>` = constante VRAIE,
`CreateTargetSelector = <DSLSelectors+0x30>` = `Owner`) :

    1119 …TerrorsLament_DamageReductionEffect$$CreateEffectDamageMalusForDefense
        = EffectBonus.ForSubtraction( IsAdjacent(Caster@+0x48, Owner@+0x30, 3)
                                      & AreEnemies(Owner@+0x30, Caster@+0x48, 0)
                                      & IsMeleeAttack,
                                      ConfigVar(0x12 = dmgReduction) )

    1120 …TerrorsLament_HitReductionEffect$$CreateEffectHitsBonusForAttack
        = EffectBonus.ForAdditionWithMinimum( <les trois mêmes conjoints>
                                              & NOT HasTrait(Caster@+0x48, 0x19 = UnitTrait.Immune),
                                              Multiply(<DSLFormulas+0x38> = Direct(-1),
                                                       ConfigConst(0x2c = hitsReduction)),
                                              Direct(1) )

⚠ **Le quatrième conjoint n'est que sur la moitié COUPS.** Trois `op_BitwiseAnd` d'un côté, quatre
plus un `op_LogicalNot` de l'autre. Recopier un trigger sur l'autre est une faute silencieuse dans
les deux sens.

⚠ **`<DSLFormulas+0x38>` = `Direct(-1)`** : le `.ctor` de `DSLFormulas` y écrit `Direct(0xffffffff)`
(voisins : `+0x18 = 0`, `+0x20 = 1`, `+0x28 = 2`, `+0x30 = 100`). Et `hitsReduction` est une
**constante** (`ConfigConst`) : ni palier de niveau, ni multiplicateur de rareté.

⚠ **Trois enums, et les ordinaux mentent.** `EffectType` 1119/1120 = ces deux effets, mais
`TriggeredAbilityType` 1119/1120 nomment `MV71SniperDroneSquad` / `SaviorProtocols` — deux abilities
RÉELLES, donc une confusion d'enum ne lèverait pas : elle lirait une autre config.

## 2. `ToughToKill` — `TriggeredAbilityType 0x5c5 = 1477`, DEUX classes natives

Le gameconfig ne connaît qu'un nom ; le build en dérive deux abilities de bases **différentes**
(`classes.tsv`), voisines dans le bloc `methodPointers` :

    ToughToKill_CritAbility : AOwnerEffectTriggeredAbility   -- n'override QUE `GetEffectType`,
                              dont le corps ENTIER est `return 0x5c0` -> owner-effect 1472 permanent
    ToughToKill_HealAbility : BaseTriggeredAbility
        $$CreateTrigger   = On(0x13 = TurnStart_Other, ownerNeedsToBeAlive: 1) & <DSLTriggers+0x28
                            = IsTurnOf(Owner)>            (corps fondu, partagé avec RelentlessMarch)
        $$CreateBehaviour = Heal(healer = Owner, selector = Owner,
                                 amount  = Get(GetVariableForLevel(0x20 = hpToHeal, abilityState, 0)),
                                 options = HealBehaviourOptions$$ForRegenerate)

    1472 IdunBattleLogic.Entities.Effects.ToughToKillEffect  (: BaseEffect)
        $$CreateActiveCondition = <DSLTriggers+0x70> = YesTrigger   -> TOUJOURS ACTIF
        $$CreateCritChanceBonus = ForSubtraction(get_OwnerIsTarget, ConfigVar(0x98 = critChanceReduction))
        $$CreateCritDamageBonus = ForSubtraction(get_OwnerIsTarget, ConfigVar(0x97 = critDmgReduction))

`$$ForSubtraction` = `0x1048090`, et non `$$ForAddition` = `0x1047dc0` : c'est l'adresse qui tranche.
⚠ `TriggeredAbilityType 0x5c0 = EcstaticSlaughter` — une ability qui EXISTE.

## 3. Le port : DEUX pattes par effet, populations disjointes

Le trigger de 1119/1120 porte sur `(Caster, Owner)`, **jamais sur la cible**. Les deux boucles
natives qui les consomment sont board-wide et écrivent `AbilityEntities+0x18 (Owner) <- la cible de
l'effet` (`EffectsQuery$$GetActiveEffectsWithBonuses`, puis
`DamageCalculations$$CalculateDefenderModifiersForPrediction` surcharge 4-args et
`DamagePrediction$$GetAttackHits`). Le port scinde parce que ses agrégateurs scindent :

| Owner ==  la cible | `create_effect_damage_malus_for_defense` · `create_effect_hits_malus_for_defense` |
| Owner !=  la cible | `create_aura_defense_damage_malus_for_ally` · `create_aura_hits_bonus_for_attack` |

Les deux populations sont disjointes par construction (les agrégateurs d'aura excluent la cible).
Jain Zar ATTAQUANTE : `AreEnemies(Owner, Caster)` est FAUX quand `Owner == Caster`, donc aucun canal
attaquant n'est implémenté — ce n'est pas un oubli.

Quatre clés de contexte ajoutées, chacune **un nœud DSL** et posée symétriquement dans les DEUX
façades (combat `runner/damage_model.py`, prédiction `playbook/prediction/`) : `att_pos` /
`owner_pos` (les deux arguments d'`IsAdjacent`), `att_team` + `is_melee` sur le canal aura-défense,
`att_traits` sur le board de coups. Et `create_effect_hits_malus_for_defense` reçoit désormais le
`board` complet (`att_ctx`) : le natif n'a **qu'un** canal et passe le même `AbilityEntities` à tous
les effets de sa boucle — rien n'y borne les nœuds lisibles au défenseur.

## 4. Ce que la confrontation a trouvé — un bug de FOYER PARTAGÉ

`AttackDamageOperation._crit_params` évaluait `could_crit(cc, cd)` sur les valeurs **post-bonus**.
Le conjoint `cd > 0` y supprimait le **tirage** dès qu'une réduction de crit-dégât rendait `cd <= 0`,
donc **désynchronisait le flux PRNG de toute l'attaque** (un `NextBool` de moins par coup) — pas
seulement le dégât. Relu verbatim :

* `DamagePrediction$$RollCritical` : `cc = GetStat(9) + Σ` ; `< 0` faux ; `>= 101` clampé à 100 ;
  `< 1` faux ; sinon `NextBool(cc)`. **La seule grandeur qui supprime le tirage est la CHANCE.**
* `DamagePrediction$$CalculateCriticalDamage` : `Math.Max(0, GetStat(10) + Σ)` — plancher, pas gate.
* `DamageCalculations$$CouldCrit(attacker)` = `GetStat(9) > 0 && GetStat(10) > 0` n'a que des xrefs
  **DATA** : il n'est pas sur le chemin d'exécution d'un coup (constat déjà mesuré par
  `entities/effects/loki/inescapable_accuracy.py`, où `GetStat(9) == 0` crite quand même).

Correctif : `crit_enabled = (cc post-bonus >= 1)` et `cd = max(0, …)`. Le gisement était
**inatteignable** avant : aucun effet porté ne poussait `cd` sous zéro. `ToughToKill` le fait
(`critDmgReduction[50] × 160 % = 1330` contre `GetStat(10) = 700`).

MESURE (bras `ttk`) — natif `[1619, 1789, 1355, 1624, 1215, 1352]` (`Attack_DidCrit = 1` sur les deux
premiers), port avant correctif `[1415, 1619, 1515, 1789, 1397, 1355]` : **six coups divergents**, et
l'ordre trahit le décalage de flux. Après : égalité à l'unité.

⚠ Le premier correctif tenté (`could_crit` sur les stats **brutes**) a rendu
`test_inescapable_accuracy_crit_chance_live.py` ROUGE 4/7 — la version brute éteint le canal d'un
`eldarMauganRa` à `GetStat(9) == 0` porté à 15 par son passif. C'est ce test-là qui a tranché.

## 5. La confrontation live — géométrie CALCULÉE, cinq bras

`MC1_67`, quatre tuiles `Grass` à l'élévation **3** (vérifié offline **et** assertionné live contre
le `boardGraph`) : victime `(0,0)`, attaquant `(0,1)`, Jain Zar près `(0,2)` ou loin `(0,4)`.
`TILE_J_NEAR` est à **2 hex de la victime** : un port qui lirait l'adjacence à la CIBLE au lieu de
l'adjacence à l'ATTAQUANT rendrait le bras `aura` identique au témoin.

| bras | natif | port |
|---|---|---|
| `tl_away` (témoin) | 6 coups, `[1415, 1619, 1515, 1789, 1397, 1355]` = 9090 | identique |
| `tl_aura` | **5** coups, `[618, 822, 718, 992, 600]` = 3750 | identique |
| `tl_self` | 5 coups, mêmes valeurs | identique |
| `ttk` | 6 coups, 8954 ; regen **+2659** | identique, regen +2659 |
| `ttk_ctl` (témoin) | 6 coups, 12975 | identique |

Écart par coup `tl_away → tl_aura` : **−797 sur les CINQ coups restants**, soit exactement
`dmgReduction[50] × 180 % = 797`. Et le 6ᵉ coup disparaît (`hitsReduction = 1`).

CONTRE-ÉPREUVE (registre neutralisé = l'état d'`origin/master`) : les bras porteurs divergent
(`tl_aura` 5/3750 natif contre 6/9090 port ; `ttk` 8954 contre 12975 ; regen 2659 contre 0), les
témoins ne bougent pas. La mutation MORD — un bras mutant vert serait le résultat suspect.

## 6. Ce qui n'est PAS couvert

* `NOT HasTrait(Caster, Immune)` (le conjoint propre à 1120) — **28 porteurs du trait, aucun
  `lineup`** : npc, summons et power-ups. Résidu **#950-r1**.
* La face **PRÉDICTION** (playbook) des deux passifs : les clés sont posées symétriquement dans
  `playbook/prediction/`, mais aucune mesure live ne la confronte. Résidu **#950-r2**.
* Le bras `ttk_ctl` ne discrimine pas la regen (Dreir y est à PV pleins, donc `healed = 0` des deux
  côtés) : c'est le bras `ttk` qui la porte.
