# Case #203 — trait **LivingMetal** (régénération Necron, tout le roster)

> Port de la face COMBAT du trait `LivingMetal` (UnitTrait 1000) — 51 unités Necron
> (41 npc + 6 lineup + 4 summons). Artefact natif : l'ability triggered `LivingMetalRepair`
> (TriggeredAbilityType `0x3f2`=1010), accordée par le trait. Livré : port + probes + doc.

## 1. RE — décompilé = vérité (VAs `gqfc5mff6c`)

### 1.1 Les deux arbres DSLFactory de `LivingMetalRepairAbility`

- **`CreateTrigger @181222630`** =
  `OwnerIsActor(@0xa0) & On(TurnStart_Other=0x13=19) & IsDamaged(self)`.
  - `On(TurnStart_Other=19)` = **2e des 5 events** émis par `StartTurnOperation.Execute @180ea3fb0`
    (séquence `FUN_180026490(..,0x12->0x13->0x14->0x15->0x16)` ; `0x16`=TurnStart_Actions). Le même
    event `0x13` porte **FirstAid** (tile-effect, `tiles.py`).
  - `@0xa0` = trigger partagé bâti dans `DSLFactory.InitializeShared @180df2670` (ctor gshared que ghidra
    mislabel `HasUsedActiveAbilityThisTurnTrigger` — **nom NON fiable**) = scoping « le propriétaire est le
    joueur ENTRANT ». **Prouvé live** (probe_203) : la régen ne fire QU'au tour du propriétaire (delta 0 au
    tour adverse). Porté = `ev.player_id == OwnerComponent.player`.
  - `IsDamaged(self)` (`DSLFactory.IsDamaged @180df32e0`) =
    `Not(UnitsWithStatEqualToTrigger(self, HEALTH=5, part MISSING=4, Direct(0)@factory+0xb8))`
    (`UnitsWithStatEqualToTrigger.ctor @180f04e00` ; `Direct(0)` = `DSLFactory.ctor @180e020b0` champ `+0xb8`)
    = missing HP > 0 = **HP courant < HP max**. Le dispatch gate déjà owner VIVANT → une unité MORTE ne
    régen PAS (pas d'auto-résurrection ; `LivingMetalRepairAbility` n'est PAS fire-on-death).

- **`CreateBehaviour @1812224e0`** =
  `Repair(source=self, target=self, amount, cause=AbilityOrEffect(LivingMetalRepair 0x3f2), options=ForRegenerate)`
  (`DSLFactory.Repair @180dfa030` → `RepairBehaviour.ctor @180fcf0e0`).
  - `amount = PercentageOf(StatAmount(self, HEALTH=5, MAXIMUM=2)=maxHP, Direct(GetNumberConstant(0x12)))`
    (`StatAmount` = `StatAmountFormula.ctor @180f230f0` via `DSLFactory.StatAmount @180dfbf60` ;
    `PercentageOf.ctor @180f217c0` via `DSLFactory.PercentageOf @180df8720`).
  - `GetNumberConstant(config, 0x12) @181576af0` = `Int32.Parse(GetStringConstant(config, 0x12))` ; la valeur
    vient du trait var gameconfig **`livingMetalHp` = 10** (scalaire flat — PAS de courbe par niveau).
  - `PercentageOf.CalculateInternal @180f20fc0` + `RoundFix64Result @180ffa110` (mode 0 = `Fix64.Round
    @1815636e0` = **round-half-to-even**, banker's) ⇒ **amount = round_half_even(maxHP × 10 / 100)** = **10 % du maxHP**.

### 1.2 L'Operation impérative sous la feuille + les gates

- `ForRegenerate @180fce8c0` (options `+0x10=1, +0x14=0, +0x18=3`) ≠ `ForRepair @180fce920` (`+0x14=1`) ≠
  ctor défaut `@180fce970` (`+0x14=1`). **Mode DISTINCT** (cf. §3 swarm).
- `RepairBehaviour.Execute @180fce990` → `RepairUnitOperation.Execute @180e8b820` →
  `FillUpStatComponent.FillUp @180f9b2e0` (`healed = Min(amount, get_CurrentMaximumValue - cur)` ;
  `get_CurrentMaximumValue @180f9c010` = max de BASE, non group-aware = maxHP plein). Gate d'exécution =
  `EntityCanBeRepaired @181055080` : `!IsMachine & (IsDamaged || missing shield || …) & !HasHealBlockers
  @180ed6810 & IsAffectedByHealType(1) @180ed77d0`. `IsAffectedByHealType(1)` = **IsMechanical** (ou trait
  `0x421`=1057) : **TOUS les 51 porteurs LivingMetal sont Mechanical** → gate toujours vraie. `HasHealBlockers`
  = dict heal-blockers (où vit `Cursed` 79).
- Port du mutateur = **`HealUnitOperation`** (`runner/operations/heal.py`) : même `FillUpStatComponent.FillUp`
  (cape maxHP + gate `Cursed` + re-dérivation swarm via `on_group_unit_hp_changed`).

### 1.3 Face DÉCISION/PRÉDICTION — aucune consommatrice

L'effet `NetherRealmCasket_LivingMetalBonus` (EffectType 1456, `CreateEffectRepairBonus @180f5b650`) est
documenté **INERTE** sur le chemin Repair/Galvanic (`predict.py`, case-34). Aucune face décision à porter.

## 2. Port

- **`runner/operations/triggers/loki/living_metal.py`** — `LivingMetalRepairAbility(TriggeredAbility)` :
  `event_id = TurnStart_Other(19)` ; `matches` = `OwnerIsActor` (`ev.player_id == oc.player`) & `IsDamaged`
  (`hp < hp_max`) ; `execute_behaviour` = `HealUnitOperation.execute(self, round_half_even(maxHP × pct/100))`,
  **capé group-unit** (cf. §3).
- **`triggers/dispatch.py`** — `LivingMetalRepairAbility` dans `TRAIT_TRIGGERS["LivingMetal"]` + vecteur
  `turn_start_other_triggers(state, player_id)` (dispatch `On(TurnStart_Other=19)`).
- **`triggers/__init__.py`** — export `turn_start_other_triggers`.
- **`operations/turnflow.py`** — `StartTurnOperation.execute` appelle `turn_start_other_triggers(player)` à
  côté de `first_aid_heal` (même event `0x13`).

## 3. Le cas SWARM — verdict RE + correction de case-60

**Découverte (probe_203_swarm, live)** : un scarab (`necroSmnSwarm`, maxHP 2218, 5 membres = 443.6/membre)
endommagé à **888/2218** (2 membres pleins = frontière de membre) **ne régen PAS** via LivingMetal
(`live_regen = 0`, bloqué à 888 tour après tour).

**Explication** : `ForRegenerate` = repair **« NO-WAKE »** — le montant est capé au
`get_group_unit_heal_limit @1810325e0` = `maxHealthWith(membres RESTANTS) − hp` (ce qu'on peut soigner **sans
réveiller** de membre mort), DISTINCT de `ForRepair` (admecManipulus `Repair_GalvanicField` 1119) qui
**RÉVEILLE** des membres. Les membres d'un swarm member-capé (défense #57d) sont **toujours pleins à une
frontière** → heal-limit **0**. Et `10 % du maxHP` (222) **< 1 membre** (444) ⇒ **LivingMetal est INERTE sur
le swarm 5-membres** (la régen n'est jamais assez pour réveiller un membre, et il n'y a pas de membre partiel
à compléter).

**Correction case-60** : le « `LivingMetal` full-revive 444→1775 » observé en case-60 (probe roster
`necroSpyder,admecManipulus`) était **admecManipulus** (`ForRepair`, WAKE), **MAL attribué** à LivingMetal.
Reproduit ici : avec manipulus, le scarab 888→2218 pendant le tour ; **sans** manipulus, il reste bloqué à 888.

**Port** : pour un group-unit (`ctx.number_of_members >= 2`), `amount = min(amount,
get_group_unit_heal_limit(maxHP, n, hp))` (helpers case-60 validés). Single unit (n<2) → `heal_limit =
int.MaxValue` → pas de cap. Le cap est **LOAD-BEARING** : sans lui le port soignerait 222 = divergence.

## 4. Validation (adversariale, offline-vs-live, zéro tolérance)

- **probe_203_livingmetal.py** (necroWarden, maxHP 30000) — face COMBAT `load_state(S)` +
  `turn_start_other_triggers` :
  - montant : **offline healed = 3000 == live_regen = 3000 == round_half_even(10 % × 30000)** (NON capé) ;
  - scoping : offline `turn_start_other_triggers(A_player)` ne régen PAS le warden (P) ; live delta 0 au tour A ;
  - le necroDestroyer (A, plein) ne régen dans aucun résultat.
- **Ground truth mécanisme** (bracket d'endturns purs, mesuré) : `+3000` UNIQUEMENT au tour du propriétaire
  (0 au tour adverse) ; cape à maxHP (dernier tick `+2615 = min(3000, missing)`) ; **stop à PV pleins**
  (IsDamaged) ; banker's confirmé offline (445→44, 455→46, 30005→3000).
- **probe_203_swarm.py** (scarab 888/2218) — **offline healed = 0 == live_regen = 0** (LivingMetal inerte au
  boundary ; le 10 % non-capé de 222 aurait divergé — le cap group-unit l'évite).
- **Zéro-régression** : `engine_agreement_stages --build --seeds 31337 --steps 20` = **100 %** sur les 4 étages
  (PREDICTION 10/10, UTILITE 10/10, ability 13/13, move 18/18), AVANT et APRÈS le cap group-unit.
- **Généralisation** : stages roster Necron (`necroWarden,necroDestroyer,necroSpyder` vs sang, seed 909) =
  **100 %** (6/6 steps EXACT/MATCH) jusqu'à fin de bataille — aucun crash, aucune régression décision avec
  LivingMetal actif.

## 5. Résidus

- **Swarm « no-wake top-off » (non exercé live)** : pour un swarm à une HP **non-frontière** (membre
  partiellement endommagé, ex. 700/2218), `get_group_unit_heal_limit` > 0 → LivingMetal complèterait le membre
  vivant jusqu'à la frontière (ex. 700→888). Le port le fait (structurel, mirror `get_group_unit_heal_limit`),
  mais c'est **INVALIDÉ live** : le member-cap (défense #57d) maintient les swarms **toujours aux frontières**,
  donc ce chemin n'est jamais atteint par le combat normal (seul un dégât non-member-capé — Blast — poserait un
  membre partiel). À revalider si un tel état apparaît.
- **Quantification exacte du repair WAKE (`ForRepair`)** hors scope #203 (manipulus/ReanimationBeam) : le port
  LivingMetal (NO-WAKE) n'en dépend pas.
