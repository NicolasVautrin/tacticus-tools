# #1023 — `OmnissiahsBlessing`, et le verdict re-établi de `GalvanicField`

Deux passifs **AdeptusMechanicus**. L'un était un **GAP-ABSENT** intégral, l'autre un verdict
**attesté** que cette tranche re-mesure au lieu de le recopier.

| passif | `TriggeredAbilityType` | porteurs | état à l'entrée | verdict |
|---|---|---|---|---|
| `OmnissiahsBlessing` | `0x513` = 1299 | `admecSmnTechpriest` (summon) · `admecNpc2Techpriest` (npc) | GAP-ABSENT | **PORTÉ + CONFRONTÉ LIVE** |
| `GalvanicField` | `0x4af` = 1199 | `admecManipulus` (pool) + 5 npc | `RIEN_A_PORTER` attesté (#952) | **verdict CONFIRMÉ**, RE re-lue |

---

## 1. `GalvanicField` — le verdict tient, et ma RE le re-établit

Décompilé relu ce jour, indépendamment de #952 :

```
IdunBattleLogic.Entities.Abilities.Triggered.Loki.GalvanicFieldAbility$$CreateBehaviour
      DSLBehaviors.AddFlag( Owner@DSLSelectors+0x30, 0x18 = UnitFlag.CanRepairFullHealthUnits )
    & DSLBehaviors.RemoveActiveAbility( Owner@+0x30, 0x1c = ActiveAbilityType.Repair )
    & DSLBehaviors.AddActiveAbility( Owner@+0x30, 0x45f = ActiveAbilityType.Repair_GalvanicField,
                                     abilityState )
```

Les trois feuilles, à l'identique de la fiche `case-952` §3 : aucun `CreateTrigger` propre (le
corps est fondu par l'ICF avec le trigger d'init partagé), donc c'est un état posé à l'INIT, pas
un événement. Les trois consommateurs sont portés — `snapshot._load_unit_flags` →
`attack_query.entity_can_be_repaired` (4ᵉ disjunct) ; `ABILITY_CLASSES[1119]` ; et « rien à
retirer », le port ne dérivant jamais `Repair` d'un trait.

**Confirmé LIVE par le montage de ce lot, incidemment et sans le viser** : sur le runner de
`probe_1023`, `admecManipulus` expose `{id: 1119, kind: "granted"}` dans `decisionView.units[].
abilities` — l'échange `28 → 1119` a bien eu lieu, côté natif, avant la capture. Le cliquet
`test_952_hunters_beyond_death_offline.py` rejoué : **34 passed**.

⇒ **aucune ligne de port**. Le verdict attesté (`scripts/ratchets-951r2-couverture-attestee.json`,
`passif:GalvanicField` = `RIEN_A_PORTER`, build `rnca9r7q6c`) est **valide au commit courant** et
n'est pas touché.

---

## 2. `OmnissiahsBlessing` — les deux corps, lus verbatim sur `rnca9r7q6c`

Slots : `DSLSelectors+0x30 Owner`, `+0x60 Target` ; `DSLFactory+0x78 Behaviors`, `+0x80 Formulas`,
`+0x88 Triggers`, `+0x90 Selectors`.

```
OmnissiahsBlessingAbility$$CreateTrigger
    On( 0x30 = 48 UnitRepaired, ownerNeedsToBeAlive: 1 )
      & get_OwnerIsCaster
      & HasEffect( Owner@+0x30, 0x555 = 1365 MachineVengeance, onlyActive = 0, targetType = 6 )
      & op_LogicalNot( get_OwnerIsTarget )

OmnissiahsBlessingAbility$$CreateBehaviour(abilityState, triggerType)
    lvl = DSLFormulas.EffectLevel( DSLSelectors.EffectFromOwner(Owner@+0x30, 0x555) )
    b1  = DSLBehaviors.AddEffectOrIncreaseLevel( 0x555, AbilityStateReference,
                                                 source = Owner@+0x30, targets = Target@+0x60,
                                                 level = lvl, maxLevel = NULL )
    b2  = DSLBehaviors.RemoveEffect( Owner@+0x30, Nullable<EffectType>(0x555), NULL )
    return AbilityBehaviour.op_BitwiseAnd( b1, b2 )
```

i2 : « Whenever the Tech-Priest Enginseer repairs another unit, it transfers all levels of Machine
Vengeance it has to the repaired unit. » — les quatre conjoints et les deux behaviours, phrase pour
phrase.

**Les surcharges sont LUES, pas déduites de l'ordre du call-site** :
`AddEffectOrIncreaseLevel(this, effectType, abilityState, source, targets, level, maxLevel)` a sept
paramètres ; `RemoveEffect` est la variante à quatre arguments (`this, selector, effectType,
replaceableEffectType`), l'autre prenant une entité-effet directe. Le `Nullable<EffectType>` est
monté juste avant l'appel, le `replaceableEffectType` vaut littéralement `0`.

### Ce que la lecture des ÉTAGES a établi, et qui ne se devine pas

1. **`EffectLevel` prend un SÉLECTEUR D'EFFETS et rend une SOMME.**
   `IdunBattle.Entities.Formulas.EffectLevelFormula$$Calculate` part de `0` et ACCUMULE
   `EffectComponent+0x68` sur toutes les entités-effet rendues. Le sélecteur est
   `IdunBattle.Entities.Selectors.EffectWithTypeSelector$$Select` = `foreach entity : eff =
   EntityExtensions.GetOwnedEffect(entity, state, effectType) ; if (eff != null) list.Add(eff)`.
   `GetOwnedEffect` (corps relu) itère l'`EffectsOwnedComponent` et compare `EffectComponent.Type
   @+0x58` — **ni `IsActive`, ni niveau** ; d'où le filtre `consumed` SEUL côté port.
2. **`maxLevel = NULL` ⇒ aucun cap.** Le plafond de `MachineVengeance` qui existe ailleurs
   (`ArcScourgeAbility$$GetDynamicInvalidCasterReason` refuse le cast au-delà de `effectLevel_2` =
   9) est un gate de CASTER sur une AUTRE ability.
3. **`NOT get_OwnerIsTarget` n'est PAS redondant avec `get_OwnerIsCaster`** : `RepairAbility$$.ctor`
   pose `TargetingRule.CasterIsPossibleTarget` (masque `0x8002`), donc un mécanicien PEUT se
   réparer lui-même. Sans ce conjoint, une auto-réparation poserait puis retirerait la pile sur le
   même porteur — **perte sèche**.
4. **`onlyActive = 0` est le littéral du call-site**, comme sur les deux call-sites
   `MachineVengeance` d'`ArcScourgeAbility`.

---

## 3. LE COLLAPSE V ÉTAIT ICI UNE PERTE D'INVARIANT — mesuré, pas redouté

Le port a d'abord résolu `EffectLevel(EffectFromOwner(Owner, 0x555))` en **scalaire avant l'arbre**,
exactement comme le font `runner/abilities/custodes.py::talons_used_abilities_level` et
`triggers/loki/red_rampage.py::_remaining_turns_of_extra_movement` — le collapse V standard du dépôt
pour ce motif, justifié par le fait qu'`entities/selectors/geometry.py::EffectFromOwner` rend `[]`
hors-ligne.

**Mesure** : sous ce collapse, le mutant « ordre inverse » (`RemoveEffect` AVANT le transfert) reste
**VERT**. Le niveau étant déjà figé, l'inversion ne change plus rien — alors que le natif
transférerait **0** et que la pile disparaîtrait quand même, sans erreur ni compte global qui bouge.

**La différence avec les deux précédents** : chez eux, rien ne RÉÉCRIT l'effet lu dans le même
arbre. Ici, le `RemoveEffect` du `op_BitwiseAnd` vide précisément la pile que le transfert lit.

⇒ le port passe un **nœud VALEUR paresseux** (`MachineVengeanceLevelOfOwner`), évalué par
`AddEffectOrIncreaseLevel` au moment où il s'exécute — comme le natif. Le mutant devient ROUGE.
Ce que ce choix coûte : le nœud CAPTURE le `state`, faute d'accesseur de NIVEAU d'effet sur le
`DslContext` (`ctx.has_effect` n'est qu'un booléen).

**Généralisation** : le collapse V est légitime tant que la lecture n'a **aucun réécrivain dans le
même arbre**. Ce critère est vérifiable au décompilé (chercher un `RemoveEffect`/`SetEffectLevel`
sur le même `effectType` dans le `CreateBehaviour`), et c'est lui qu'il faut appliquer, pas
l'habitude.

---

## 4. Le porteur — trois voies fermées, une ouverte

Les DEUX porteurs sont hors pool : `admecNpc2Techpriest` (npc) et `admecSmnTechpriest` (SUMMON dont
l'unique invocateur, `InvocationOfMachineVengeance`, n'est porté que par `admecBossBelisarius`,
npc). Et les **trois** sources de `1365 MachineVengeance` sont, elles aussi, hors pool :

| source | porteur | portée ? |
|---|---|---|
| `ArcScourge` (active 1173) | `admecBossBelisarius` (npc) | **oui** (`ABILITY_CLASSES[1173]`) |
| `ShroudPsalm` (1181) | `admecBossBelisarius` (npc) | non — et elle EXCLUT le caster de ses cibles |
| `VengeanceForTheOmnissiah` (passif) | le Tech-Priest lui-même | non |

⇒ **GREFFE** sur `admecManipulus` (HERO du pool, trait `Mechanic` donc réparateur), condition
VÉRIFIÉE : `OmnissiahsBlessing` n'a **aucune variable ni constante** au gameconfig, et ses deux
faces ne lisent ni stat, ni trait, ni arme du caster (seuls canaux : `HasEffect(Owner, 0x555)` et
les sélecteurs `Owner`/`Target`).

```
PassiveAbilities += 1299    # le passif confronté
PassiveAbilities  ⊇ 1199    # GalvanicField CONSERVÉ -> c'est lui qui accorde 1119, donc la RÉPARATION
ActiveAbilities   = [1173]  # ArcScourge : le vecteur de pose, porté des DEUX côtés
```

### Deux verrous de montage, tous deux MESURÉS

* **La config d'`ArcScourge` doit être injectée EXPLICITEMENT** dans `BC.Abilities.ActiveAbilities`.
  Le rafraîchissement de `rl_duel._load_seed_bc` (`catalog_inject.refresh_ability_configs`) MET À
  JOUR les entrées présentes, il n'en CRÉE pas — et `ArcScourge` est absente de la capture. Sans
  elle : `{"ok": false, "error": "system error"}` au cast, **même verrou que #226/#237**.
* **RE-CASTER n'incrémente RIEN** : le 2ᵉ cast rend `ok: true` avec DEUX events et la pile reste à
  son niveau. C'est le **nombre de MAILLONS** qui fait le niveau (`AddPersistentData(+1)` par
  maillon). D'où le placement de l'allié MÉCANIQUE au contact de l'ennemi : le sélecteur de saut
  d'`ArcScourge` PRIORISE les `Mechanical` adjacents, **alliés compris**, et sur un allié la branche
  n'incrémente que le compteur (aucun dégât).

---

## 5. Confrontation — `probe_1023_omnissiahs_blessing.py --chain 2`

| mesure | natif | port (même capture) |
|---|---|---|
| après `ArcScourge`, chaîne 2 maillons | `{admecManipulus: 2}` | `before = {carrier: 2, ally: 0}` |
| après la réparation d'`admecDestroyer` | `{admecDestroyer: 2}` | `after = {carrier: 0, ally: 2}` |
| le passif a-t-il tiré ? | — | `fired = 1`, `level = 2`, `removed = 1` |
| **contre-bras** `ability_states=False` | — | `fired = 0`, `after = {carrier: 2, ally: 0}` |

**Le niveau 2 est load-bearing** : à une pile de 1, « transfère TOUT » et « transfère UN » rendent
le même nombre et la mesure ne conclut rien. La garde live l'assertionne AVANT le transfert
(`test_le_temoin_est_NON_DEGENERE`).

**Offline** — `tests/engine/test_1023_omnissiahs_blessing_offline.py`, 21 tests, fixture nommée
`_blessing_state`. Contre-épreuve par **MUTATION DU PORT**, **9/9 mutants ROUGES** :

| mutant | garde qui tombe |
|---|---|
| M1 ordre inversé | `test_le_transfert_nominal…` + 5 autres |
| M2 gate `NOT OwnerIsTarget` retiré | `test_gate_NOT_OwnerIsTarget…` |
| M3 gate `HasEffect` retiré | `test_gate_HasEffect…` |
| M4 cap posé sur `AddEffectOrIncreaseLevel` | `test_le_transfert_CUMULE…SANS_cap` |
| M5 cible = `Owner` au lieu de `Target` | `test_le_transfert_nominal…` + 5 autres |
| M6 gate `OwnerIsCaster` retiré | `test_gate_OwnerIsCaster…` |
| M7 `EffectLevel` = MAX au lieu de SOMME | `test_le_niveau_lu_est_une_SOMME…` |
| M8 retour au collapse scalaire | `test_le_niveau_transfere_est_un_NOEUD_PARESSEUX…` |
| M9 `active_only` inversé | `test_NON_MORSURE_MESUREE…` |

### La mutation qui NE MORD PAS — écrite comme un résultat

Basculer `active_only` **ne change aucun verdict de ce montage** : `1365` n'a AUCUNE classe dans
`EFFECT_CLASSES`, donc son instance n'a pas d'`ActiveCondition` et `is_active` rend vrai quoi qu'il
arrive. Ce qui est gardé, c'est la **valeur écrite au site** (M9 fait tomber ce test-là). Un lecteur
futur ne doit pas prendre cette non-morsure pour un oubli.

---

## 6. Résidu

* **#1023-r1 — le canal DÉGÂT de `1365 MachineVengeance` n'est PAS porté.** Son unique canal natif
  est
  `IdunBattle.Entities.Effects.Loki.MachineVengeanceEffect$$CreateEffectDamageBonusForAttack` =
  `EffectBonus.ForPercentIncrease( get_OwnerIsCaster, Multiply( Get(GetNumberConstant(config, 7)),
  EffectLevel(Effect@DSLSelectors+0x38) ) )` — un bonus de dégât en **pourcentage, par niveau**,
  quand le porteur ATTAQUE (`AbilityConstantType 7 = MachineVengeanceExtraPct`, `BC.Effect` porte
  la valeur **5**). L'effet n'a aucune classe dans `EFFECT_CLASSES`.
  ⚠ La classe native n'expose que **deux corps propres** dans les tables (`.ctor` et ce
  `CreateEffectDamageBonusForAttack`), et **cela ne prouve RIEN sur ses autres faces** — un
  `CreateActiveCondition` / `CreateTargetSelector` trivial est fondu par l'ICF chez un propriétaire
  arbitraire. La première tâche du résidu est de **segmenter son bloc `methodPointers`**, comme
  #952 l'a fait pour `HuntersBeyondDeath`.
  **L'écart est INCHANGÉ par ce port** : la pile d'`ArcScourge` était déjà posée sans canal de
  dégât avant cette tranche — ce port en change seulement le PORTEUR. Il est nommé ici plutôt que
  masqué, et `test_l_effet_1365_n_a_PAS_de_classe_et_c_est_le_residu_1023r1` AFFIRME l'absence pour
  qu'un port futur le fasse rougir au lieu de passer inaperçu.
  ⚠ **Point de contact** : #1027 (actives de `admecBossBelisarius`) travaille sur le même effet et
  peut le fermer — vérifier avant d'ouvrir un agent dessus.
* **`VengeanceForTheOmnissiah`** (l'autre passif du même Tech-Priest, qui POSE la pile) reste non
  porté. Hors périmètre de ce lot ; c'est lui qui rendrait le porteur RÉEL auto-suffisant, donc la
  greffe inutile.
