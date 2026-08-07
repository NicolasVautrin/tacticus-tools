# #520 — HEAL/REPAIR : le « BLOQUE » de l'audit designait le mauvais bloqueur

L'audit annoncait une categorie bloquee sur une Operation ABSENTE. Les deux Operations existaient.
Le vrai bloqueur etait qu'une des deux etait **INCOMPLETE**, et qu'aucun compteur ne pouvait le voir.

## 1. Le verdict d'etage 1 — la premisse est FAUSSE sur les deux termes

`audit_combat_ability_coverage.py` ecrivait, dans la section « Priorisation » de
`docs/rl/combat-ability-coverage.md` :

> **HEAL** / lifesteal / **REPAIR** -> **BLOQUE** sur un `HealOperation`/`RepairOperation` combat
> absent du runner (tache #94). A construire avant de porter cette categorie.

Les deux Operations sont portees, et l'une des deux l'est depuis #299 :

| Operation native | module | gate | pipeline de montant |
|---|---|---|---|
| `IdunBattle.Operations.RepairUnitOperation$$Execute` | `engine/runner/operations/repair.py` (#299) | `AttackQuery$$EntityCanBeRepaired` | `DamagePrediction$$PredictRepair`, 4 etages |
| `IdunBattle.Operations.HealUnitOperation$$Execute` | `engine/runner/operations/heal.py` | **ABSENT** | **ABSENT** |

`HealUnitOperation` etait un `FillUpStatComponent$$FillUp` NU derriere un gate `EffectType.Cursed`.
Son parametre `source_id` n'etait **lu nulle part** — un parametre mort, alors que le gate natif en
depend.

**Le degat de la citation perimee est double** : elle a fait renoncer a dispatcher une categorie
entiere, ET elle designait le mauvais bloqueur. Les QUATRE abilities HEAL deja au registre
(`1002 CombatRestoratives`, `1037 RevitalizingMalignancy`, `1082 InspiredToGreatness`,
`1117 DefendTheDivineWork`) rendaient `ported: True` en soignant des cibles que le natif REFUSE.
Un no-op silencieux **dans** une ability declaree portee n'est vu par aucun compteur de cet audit :
il ne compte que les absentes du registre. Corrige **dans le generateur**, pas dans le fichier genere.

## 2. Ce que le natif ecrit, et ce que le port n'avait pas

`IdunBattle.Operations.HealUnitOperation$$Execute` (MIRROR, lu verbatim) :

    if (!attackQuery.<slot 0x11>(caster, target, scope, removeEffects)) return {};  # EntityCanBeHealed
    cursed = EntityExtensions.HasEffect(target, state, 0x4f Cursed, null)
    if (removeEffects) removedNegativeUnitEffects = processor.<slot 0x5b>(target, ...)
    pred = damagePrediction.<slot 1>(caster, GetMainTile(caster), target, amount, scope)  # PredictHeal
    healAmount = cursed ? 0 : pred.fillUp
    wasWounded = HealthComponent.IsWounded(fillUp)
    healed = FillUpStatComponent.FillUp(fillUp, healAmount)                          # LA mutation
    if (!wasWounded && healed < 1 && removedNegativeUnitEffects < 1
        && !UnitExtensions.HasFlag(caster, 0x17)) return {};
    ... <Action=HealInfo>, triggers On(0x1e)/On(0x2b)/On(0x2c), RefreshEffects

⚠ **Les noms de parametres Ghidra sont decales d'un cran** (retour `OperationResult` de 0x40 octets,
donc `rcx` = pointeur sret) — meme decalage que celui documente par `engine/streams/heal_unit.py`.
Recoupement supplementaire, interne : l'appel du slot 0x11 passe `(<ghidra:target>, <ghidra:amount>,
<ghidra:removeEffects>, <ghidra:abilityOrEffect>)` contre la signature
`EntityCanBeHealed(caster, target, scope, removeEffects)`.

### Les trois ecarts de STRUCTURE avec `PredictRepair` — lus, aucun deduit

  1. le gate de l'etage bonus est `EntityExtensions$$IsUnit(caster)`, **pas** `IsActor(caster)` ;
  2. le bonus de soin est **purement ADDITIF** (`predicted += <Nullable<int>>.GetValueOrDefault()`),
     la ou `PredictRepair` applique `(flatBonus + amount) * multiplier`. **Il n'existe aucun
     multiplicateur de soin** ;
  3. `PredictHeal` porte une branche **NEGATIVE** (`-MaxReduce(-predicted, false)`) que
     `PredictRepair` n'a pas : un « soin » negatif RETIRE des PV.

### L'etage BONUS est INERTE sur ce build, et c'est MESURE

Le descripteur que `BaseEffect$$HealBonus` lit est fabrique par un slot virtuel dont les
implementeurs se nomment `<X>Effect$$CreateEffectHealBonus`, sur le modele exact des trois
`CreateEffectRepairBonus`. Sur `rnca9r7q6c`, les **178** implementeurs de `CreateEffect*` se
ventilent en **sept** familles :

| famille | n |
|---|---|
| `DamageBonusForAttack` | 107 |
| `DamageMalusForDefense` | 39 |
| `HitsBonusForAttack` | 28 |
| `RepairBonus` | 3 |
| `UpgradeGroupHandler` / `CappedDamageMalusForDefense` / `CappedDamageBonusForAttack` | 1 chacune |

**Aucune n'est un heal bonus.** Deux canaux independants le confirment
(`data/symbols/<build>/frida/methods.tsv` et `ghidra/functions.tsv`) : `HealBonus` n'y porte que la
methode de BASE et le `ToString` de la struct. L'etage est donc porte comme un **no-op EXPLICITE** :
`predicted` inchange, isomorphisme conserve, zero valeur inventee.

⚠ Ce n'est pas un argument par absence de symbole (que la doctrine interdit) : le corps par defaut
`BaseEffect$$CreateEffectHealBonus` est trivial (`return null`) donc **deduplique par IL2CPP**, mais
un corps qui CONSTRUIT un descripteur ne l'est jamais — c'est precisement pourquoi les trois
`CreateEffectRepairBonus` apparaissent, eux.

## 3. Les OPTIONS — la feuille `Heal` n'en avait aucune

Le build porte deux fabriques, exactement comme du cote repair :

| fabrique | `scope@+0x2c` | `removeEffects@+0x30` | call-sites |
|---|---|---|---|
| `HealBehaviourOptions$$ForHeal` | 0 | 1 | 19 |
| `HealBehaviourOptions$$ForRegenerate` | 1 | 0 | 6 |

Les SIX `ForRegenerate`, lus aux xrefs : `SavageEchoesAbility$$ExecuteBehaviour`,
`MedicusMinistorumAbility$$CreateBehaviour`, `LifeStealEffect$$CreateTargetTriggerBehaviour`,
`SanguinaryPriestAbility$$CreateBehaviour`, `TimeFluxAbility$$CreateBehaviour`,
`ToughToKill_HealAbility$$CreateBehaviour`. **Deux sont portes** et tournaient en `scope 0` :

  * `engine/runner/abilities/bloodangels.py` (SavageEchoes) — le commentaire du site **ecrivait deja
    le mot `ForRegenerate`** pendant que le port l'ignorait ;
  * `engine/runner/operations/triggers/loki/time_flux.py` (TimeFlux).

Ecart mesure sur leurs porteurs : **NUL** (tous deux mono-membres, donc `GetGroupUnitHealLimit` rend
`int.MaxValue`). Ce qui est declare est la **fabrique**, pas un effet — et c'est ce qui le gardera
vrai si un kit change. Cliquet : `test_520_heal_pipeline_offline.py` etage 4 (par AST).

Un troisieme call-site ne prend NI l'une NI l'autre :
`FirstAidHealEffect$$CreateTargetTriggerBehaviour` construit un `HealBehaviourOptions` a la main et
n'ecrit que `<+0x32> = 1` (mode de selection du soigneur — une TUILE). `scope`/`removeEffects`
restent les defauts du ctor, relus verbatim : `HealBehaviourOptions$$.ctor` ecrit `+0x30 = 1` et
laisse `+0x2c` a 0 — c'est-a-dire exactement le couple de `ForHeal`. **Lu, pas suppose.**

## 4. L'ecart CHIFFRE du gate

`probe_520_heal_gate_ventilation.py` — chaque unite est **blessee** (`hp = hp_max - 1`) avant
l'interrogation, sinon `IsDamagedUnit` est faux pour tout le monde et la ventilation serait
degeneree.

| montage (seed 777, board MC1_67) | acceptees | refusees | cause du refus |
|---|---|---|---|
| `--p-units ultraApothecary,necroWarden,admecDominus` / `--a-units necroSpyder,orksNob,tyranWingedPrime` | 3 | **3** | `!IsAffectedByHealType(0)` — MECANIQUE sans `AffectedByHealAndRepair` |
| `--p-units thousTerminator,ultraApothecary,deathRotbone` / `--a-units orksNob,tyranWingedPrime` | 5 | 0 | (temoin de NON-REGRESSION : les porteurs de soin passent tous) |
| seed 777 nu (`test_heal_operation_live.py`) | 7 | **3** | idem |

Les trois refusees du premier montage sont exactement les mecaniques (`necroSpyder` et `necroWarden`
`LivingMetal`+`Mechanical`, `admecDominus` `Mechanical`). **Avant #520 le port les soignait toutes.**

Le second montage est le contre-poids qui manquerait a une mesure a un seul regime : les porteurs de
`TimeFlux` (`thousTerminator` — Thousand Sons, **pas** un necron), `1002` (`ultraApothecary`) et
`1037` (`deathRotbone`) restent tous acceptes.

## 5. Le rouge que le fix a produit, et pourquoi c'est un GAIN

`test_dawn_blade_repair.py::test_the_repair_modifier_is_applied` est une **contre-epreuve** : elle
reroute `RepairUnitOperation` sur `HealUnitOperation` (la faute #310) et exigeait que le mutant
retombe sur le montant NU (7273, sans `RepairModifier`). Le mutant rend desormais **0**.

Cause : la cible de DawnBlade est MECANIQUE (il la REPARE), donc le gate de soin la refuse.
**Confondre les deux Operations est plus destructeur que #310 ne l'avait mesure** : ce n'est pas
« le bon montant sans son bonus », c'est « aucun PV du tout ». L'attendu est re-derive, et un
INVARIANT independant de la valeur (`mutated != base`) est ajoute a cote.

⚠ Effet de bord a connaitre : `test_cursed_does_not_block_the_repair` (R3) attend `0` du mutant.
Ce `0` a maintenant **deux causes** (le gate `Cursed`, et le gate d'entree), donc il ne prouve plus
que `Cursed` a joue. Le test qui ISOLE `Cursed` est
`test_heal_operation_live.py::test_heal_operation_fillup_cap` etape 5, sur une cible ACCEPTEE.

## 6. Ce qui est porte, ce qui ne l'est pas

**Porte** : le gate `EntityCanBeHealed` (le mirror existait deja dans `abilities/attack_query.py`,
il n'etait simplement **jamais appele** depuis l'Operation) ; `predict_heal` complet ;
`HealthComponent.max_reduce` (mirror de `FillUpStatComponent$$MaxReduce`, le pendant PUR de
`reduce`) ; les options des deux feuilles ; le foyer partage
`operations/fill_up_prediction.py` (les deux etages de substrat que `PredictHeal` et `PredictRepair`
ecrivent mot pour mot — les dupliquer aurait cree deux lectures d'une meme limite).

**NON porte, nomme** : la purge `removeEffects` (`processor.<slot 0x5b>`) — pas de marqueur « effet
negatif » cote port, meme trou que `attack_query.has_negative_unit_effect`, et sans effet sur les PV ;
les statistiques et l'event (porte a part dans `engine/streams/heal_unit.py`) ; les trois vecteurs de
trigger `On(0x1e)`/`On(0x2b)`/`On(0x2c)` et le `RefreshEffects` de queue, dont le seul consommateur
porte (`Swarm`) est deja cable par `on_group_unit_hp_changed`.

## 7. Etage 4 — NON FAIT, et la RE est laissee pour le suivant

Aucune ability n'entre dans `ABILITY_CLASSES` : le contrat de disjonction en cinq points ne
s'applique donc pas a cette tranche. Les trois `ExecuteBehaviour` lus, par cout croissant :

  * **`1175 BloodChalice`** — LE plus simple, et le candidat recommande. L'effet
    `BloodChalice_HealOnAttackEffect` tient en deux lignes :
    `CreateTargetTrigger = On(9) & OwnerIsCaster & IsMeleeAttack` ;
    `CreateTargetTriggerBehaviour = Heal(healer: EffectSource(<+0x38>), targets: <sel@+0x30>,
    amount: ConfigVar(0x20 hpToHeal), options: ForHeal)`. Reste a lire : `BloodChaliceAbility`
    elle-meme (qui POSE l'effet), son masque et son `AbilityAttackType` ; et a verifier son unique
    porteur au pool ;
  * **`1039 RitesOfRestoration`** — `Heal(<Caster@+0x48>, GetHealTargets(), ConfigVar(0x20), ForHeal)
    & Resurrect(PickRandomly(UnitsWithTrait(possibles, 0x10), c[0x43]) + PickRandomly(UnitsWithTrait(
    possibles, 0x2), c[0x10]), CanAddUnit(AdjacentTiles(<+0x50>)), ConfigVar(0x1d))`. Exige un
    `ResurrectUnitOperation` **et** un `PickRandomly` (tirages PRNG a compter) ;
  * **`1231 TitanhammerSquad`** — quatre volets en `op_BitwiseAnd` (`AddEffect(0x623)` & `Heal` &
    `AddDynamicStatModifierEffect(0x624)` & `AddEffect(0x625)`), selecteur
    `Filter(SurroundingFriends(c[0x16]), HasTrait(0x40f)) + Caster`, durees en
    `TurnsUntilUnitOwnerTurn`. Le plus lourd des trois.

## 8. Residus ouverts

  * **`#520-r1`** — les QUATRE call-sites `ForRegenerate` **non portes**
    (`MedicusMinistorumAbility`, `LifeStealEffect`, `SanguinaryPriestAbility`,
    `ToughToKill_HealAbility`) : leur `scope = 1` arme le cap de GROUPE, seul regime ou
    `GetGroupUnitHealLimit` mord. Aucun n'a de test ; le cap n'est donc **jamais exerce** sur une
    cible multi-membres, dans aucune passe.
  * **`#520-r2`** — l'etage BONUS de `PredictHeal` est inerte **sur ce build**. Un `CreateEffectHealBonus`
    apparaissant a une mise a jour rendrait le no-op FAUX en silence, et rien ne le detecterait :
    la ventilation des sept familles de `CreateEffect*` n'est pas sous cliquet.
