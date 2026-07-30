# case-224 item 5 — `CursedPlagueBellAttackAbility` : la riposte Psychique, et le comparateur d'aura enfin mesuré

Cinquieme item de la fiche d'inventaire `case-211` / `#224`. Porte **l'ability triggered**
`IdunBattleLogic.Entities.Abilities.Active.Loki.CursedPlagueBellAttackAbility` — le second volet du
passif de Corrodius (`deathBlightbringer`, POOL-HERO rank 17), celui que l'i2 decrit ainsi :

> Enemy **Psyker** units within Corrodius' **Contagion** aura deal **{nrOfHits}x {dmg} Psychic
> Damage to THEMSELVES** each time one of their attacks deals **Psychic Damage**.

**Pourquoi CET item** (et pas la DangerZone) : il est le seul des trois restants a avoir un
**observable chiffre pilotable sans l'IA** — le psyker est dans MON equipe, je le fais attaquer par
`applyAction`, et la riposte se lit sur SES PV. Et surtout, il **ferme le residu (a) nomme par
`case-224-is-in-contagions-of-nurgle-range.md` §5** : « le comparateur STRICT de la version par
UNITE n'est pas mesure live — son seul consommateur natif est le `CreateTrigger` de
`CursedPlagueBellAttackAbility`, non porte. Le jour ou 1071 entre au registre des triggered,
l'observable est direct : une attaque Psychic d'un Psyker ennemi **adjacent** au porteur **ne doit
pas** declencher la cloche tant que `TurnsStarted(owner) <= 2`. » C'est exactement le montage §4.1.

---

## 1. Le decompile (build `rnca9r7q6c`)

### 1.1 `CreateTrigger`

```csharp
// IdunBattleLogic.Entities.Abilities.Active.Loki.CursedPlagueBellAttackAbility$$CreateTrigger
On(9 = EventTriggerType.Attack, ownerNeedsToBeAlive = 0)
& ( OwnerIsTarget | OwnerIsAlive<DSLTriggers+0x20> )
& !CasterIsTarget
& CurrentAttackDamageProfilesContain(0xd = DamageProfileType.Psychic, includeNotApplied = 0)
& AreEnemies(Actor@DSLSelectors+0x40, Owner@DSLSelectors+0x30, UnitTeamSelectionType = 0)
& HasTrait(Actor@DSLSelectors+0x40, 0x3ea = UnitTrait.Psyker)
& IsInUnitContagionsOfNurgleAura(Actor, Owner)      // = $$IsInContagionsOfNurgleRange, case-224 item 4
& !CurrentAbilityIs(this)
```

`On(9)` est resolu par `IdunBattle.DSL.EventTriggerType` (table VERSIONNEE `frida/enums.tsv`) :
`9 = Attack`. Les deux vecteurs deja cables du port (`after_hit_normal_attack` /
`after_hit_ability_attack`) l'emettent — **rien a creer**.

#### `<DSLTriggers+0x20>` = **OwnerIsAlive**, et c'est LU, pas mesure

C'est le point de RE qui restait ouvert : les deux fiches precedentes ecrivaient
`<DSLTriggers+0x20>` sans le nommer. Il est tranche par
`IdunBattleLogic.Entities.DSLTriggers$$On(triggerType, ownerNeedsToBeAlive)`, dont le corps entier
est :

```c
left  = new EventAbilityTrigger(triggerType);
slot  = ownerNeedsToBeAlive ? 0x20 : 0x70;
return left & this->field[slot];
```

Le slot `+0x20` **EST** le conjoint « owner vivant » — le drapeau `ownerNeedsToBeAlive` du helper
`On` ne fait que le choisir. Recoupement **independant**, par la CONSTRUCTION :
`IdunBattleLogic.Entities.DSLTriggers$$InitializeShared` batit `+0x20` avec le seul `state` — ce
dont `IdunBattle.Entities.Triggers.OwnerIsAliveAbilityTrigger$$ShouldTrigger` a precisement besoin
(`IsUnit(entities.Owner) ? UnitExtensions.IsAlive(entities.Owner, state) : true`) — et `+0x70`
**sans aucun argument** (le trigger neutre). Ce `CreateTrigger`-ci passe `ownerNeedsToBeAlive = 0`
a `On(9)` et remet le conjoint en **OU** avec `OwnerIsTarget` : le porteur doit etre vivant, **ou**
etre la cible de l'attaque (le cas ou le coup vient de le tuer).

⚠ Ce n'est PAS un argument tire d'une absence : la classe du slot n'a pas de `.ctor` nomme dans
`frida/methods.tsv` (corps trivial dedupliqué, cf. CLAUDE.md), et c'est justement pourquoi le nom
vient du **consommateur** (`$$On`) et de la **forme du ctor**, pas de la table.

#### Les deux comparateurs voisins, rappel

`IsInUnitContagionsOfNurgleAura` compare **INCLUSIF** (`dist <= range`) — il instancie un
`AmountIsEqualOrGreaterAbilityTrigger` — et la version d'EQUIPE
(`BattleQuery$$GetInRangeAuraAmount`) compare **INCLUSIF** elle aussi. Le rayon EFFECTIF est donc le
MEME des deux cotes : **1 / 2 / 3** aux paliers `TurnsStarted(Owner)` 1-2 / 3-4 / 5+.
Attribution etablie par lecture du POINTEUR DE CLASSE en #293 — cf. §3.2.

### 1.2 `CreateBehaviour`

```csharp
// IdunBattleLogic.Entities.Abilities.Active.Loki.CursedPlagueBellAttackAbility$$CreateBehaviour
DSLBehaviors.AttackWithAttackDamage(
    caster          = Actor@0x40,                   // le PSYKER -- il s'attaque LUI-MEME
    target          = Actor@0x40,                   // le MEME slot, lu deux fois
    amount          = DSLFormulas.Get( AbilityConfiguration.GetVariableForLevel(cfg, 0xb = dmg,
                                                                               abilityState) ),
    damageProfile   = Nullable<DamageProfileType>( cfg.GetAffectedDamageProfile()
                                                      .GetValueOrDefault(0xd = Psychic) ),
    hits            = AbilityConfiguration.GetNumberConstant(cfg, 0x2f = nrOfHits),
    abilityOrEffect = (AbilityOrEffect)this,
    options         = default(Nullable<AttackDamageBehaviourOptions>),   // 0x28 octets a ZERO
    selectionType   = 2 = UnitSelectionType.OnlyTargetable )
```

**Overload identifie par SA SIGNATURE** dans `frida/methods.tsv` — cinq overloads
d'`AttackWithAttackDamage` coexistent et ils different justement sur ces deux parametres
(`damageProfile:Nullable<DamageProfileType>` + `hits:System.Int32` ; les autres prennent un
`IDamageProfileSelector` et/ou un `IAmountFormula`).

`IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` batit
`AttackDamageBehaviour(state, Caster@0x48, Target@0x60, amount, profile, Direct(hits), …)` puis
`AttackBehaviour(caster, target, <ce behaviour>, abilityOrEffect)` : les deux selecteurs passes
(ici `Actor` **deux fois**) sont ceux de l'`AttackBehaviour` EXTERNE, qui re-ancre le contexte.

`IdunBattleLogic.Entities.DSLFormulas$$Get(int)` = le noeud constante (`Direct`) : le montant est
**fige a la construction de l'arbre**, avec l'`abilityState` du PORTEUR.

Les indices d'enum viennent des tables versionnees : `IdunBattle.Configuration.AbilityVariableType`
`0xb = dmg` et `IdunBattle.Configuration.AbilityConstantType` `0x2f = nrOfHits`.

### 1.3 La dissociation qui ne se devine pas : le MONTANT vient du PORTEUR, l'ATTAQUE du PSYKER

Le caster de l'`AttackWithAttackDamage` est **l'Actor** — donc l'armure, le percage, le crit et le
block sont ceux du **psyker**. Mais `GetVariableForLevel(cfg, dmg, abilityState)` lit la config
**de la cloche**, au niveau de l'ability du **porteur**. Un port qui laisserait la feuille resoudre
ses bornes depuis le caster (le mode BORNES habituel, `ability_attack_params(level_slot=…)`) lirait
le niveau du **psyker** — c'est precisement pourquoi ce port passe par le **mode `amount`** avec la
valeur pre-resolue depuis l'owner.

Gameconfig courant de `CursedPlagueBell` : `nrOfHits = 1`, `affectedDamageProfile = "Psychic"`,
`extraMovement = 1`, `attackRangeType = "Ranged"`, et `dmg` = table par niveau
(18 au niveau 1 … 1310 au niveau 65), **flaggee `variablesAffectedByRarityBonus`** (donc scalee par
`AbilityVariablesMultiplier`).

`options` est passe **VIDE** (`HasValue = 0` — les 0x28 octets sont mis a zero juste avant l'appel) :
aucune variance d'arme sur le montant (`amount_spread_pct = 0`, meme regime que le smite Psyker),
ni `alwaysOverkilled`, ni `alwaysCrit`.

### 1.4 Deux sources DISTINCTES pour un meme « Psychic »

Le gate du trigger lit un **litteral** `0xd` ; le profil de la riposte lit
`GetAffectedDamageProfile().GetValueOrDefault(0xd)`. Elles coincident au gameconfig courant mais
**ne sont pas le meme artefact** : le port les tient separees (`ATTACK_GATE_PROFILE` d'un cote,
`cursed_plague_bell_damage_profile()` de l'autre).

---

## 2. Ce qui est porte

| Fichier | Contenu |
|---|---|
| `engine/runner/operations/triggers/loki/cursed_plague_bell.py` | `CursedPlagueBellAttackAbility` (bloc RE + `matches` + `execute_behaviour`), `cursed_plague_bell_attack_tree`, `cursed_plague_bell_attack_damage` (mirror `GetVariableForLevel` sur l'`abilityState` du PORTEUR), `cursed_plague_bell_attack_hits` |
| `engine/runner/operations/triggers/dispatch/registry.py` | `ABILITY_TRIGGERS["CursedPlagueBell"]` passe a **deux** classes |
| `engine/runner/abilities/deathguard.py` | `cursed_plague_bell_damage_profile()` — FOYER UNIQUE de `$$GetDamageProfile` ; bloc RE de `CreateTrigger` mis a jour (`<DSLTriggers+0x20>` nomme) |
| `engine/playbook/adjacent_unit_preference.py` | `_cursed_plague_bell_damage_profile` **DELEGUE** au foyer ci-dessus (anti-fork) |

**Forme du port (doctrine #149)** : `CreateBehaviour` -> **arbre DSL** (la feuille existante
`AttackWithAttackDamage`, mode `amount`) ; les conjoints du `CreateTrigger` -> collapse imperatif
dans `matches` (patron `master_of_the_tutelaries` / `martial_superiority`), **SAUF**
`IsInContagionsOfNurgleRange` qui est deja un **noeud DSL** porte (case-224 item 4) et dont ce port
est le **PREMIER consommateur moteur** — il etait jusqu'ici appele uniquement par son propre probe
et son propre test.

**Ni `TARGETING_OPTIONS` ni `ABILITY_ATTACK_TYPE`** : parent direct `BaseTriggeredAbility`
(`classes.tsv`), donc `ABILITY_TRIGGERS` et pas `ABILITY_CLASSES` — meme raisonnement que la classe
soeur MOUVEMENT. Les deux garde-fous sont verts et **verifies**, pas supposes.

### 2.1 L'anti-recursion : DEUX gates, et le port les tient tous les deux

La riposte est une attaque **Psychic** portee par le psyker, **dans l'aura**, sur un psyker : sans
gate, elle se re-declencherait indefiniment (le port ré-emet bien `On(9)` depuis
`execute_normal_like` -> `after_hit_ability_attack`).

* `!CasterIsTarget` — la riposte est une **AUTO-attaque** (caster == target), donc le gate mord
  structurellement. Le port n'a pas de slot CASTER distinct sur un evenement d'attaque : collapse
  **assume** `Caster == Actor` sur les deux vecteurs `On(9)`.
* `!CurrentAbilityIs(this)` — porte via `state.triggering_ability`, le foyer que
  `evaluate_trigger_operation` pose deja en mirror de `BaseTriggeredAbility$$Execute`.
  **Pourquoi pas `ability_type`** : ce canal est keye sur l'espace `ActiveAbilityType`, ou **1071
  vaut `AnnihilatorBeam`** (verifie sur `frida/enums.tsv`) — y injecter le `TriggeredAbilityType`
  1071 ferait lire une AUTRE ability par tous les gates de kind. Meme refus que
  `MartialSuperiority` et `MartialApotheosis` pour leur propre id. Les deux champs natifs
  (`CurrentAbility` vs `TriggeringAbility`) sont distincts, mais ils **coincident ici** : le seul
  chemin par lequel `CurrentAbility` peut valoir 1071 sur un `On(9)` est l'execution du behaviour de
  CETTE classe (les deux autres classes du passif n'emettent aucune attaque).

---

## 3. Validation live — et le RENVERSEMENT qu'elle produit

Montage `probe_224_cursed_plague_bell_attack.py`, board `C1_02`, seed `4242`. Les psykers sont du
camp JOUEUR (donc pilotables par `applyAction`, l'IA n'intervient jamais dans la mesure) et Corrodius
du camp adverse ; `--advance N` est le seul levier qui fait monter son `TurnsStarted`, donc le
palier de rayon. Toutes les positions sont DRIVEES (`applyAction move`).

### 3.1 Deux pieges de montage, tous deux MESURES avant d'etre corriges

**a) Le delta de PV de l'attaquant est CONTAMINE.** Premier montage : le psyker perd 850 PV apres son
attaque, et l'ecart avec le port se lisait comme un desaccord. Les tags d'evenement montrent
`Attacker_Id` = une TROISIEME unite : c'etait un overwatch. L'observable retenu est donc
l'**attribution native** — la somme des degats dont l'evenement porte le tag
`Passive_Ability_Type = 1071` **et** `Attacker_Id == Target_Id == le psyker` (la signature exacte
d'`AttackWithAttackDamage(caster = Actor, target = Actor)`). Cote port, le total des invocations de
`execute_behaviour`, captees par un wrapper du PROBE (jamais du moteur).

**b) Un cast hors portee rend `ok: true` avec zero degat.** Deuxieme montage : le port frappait pour
2428 la ou le natif ne faisait rien — parce que l'attaque live n'avait tout simplement pas eu lieu.
Le probe exige desormais que la cible soit LEGALE sans bouger (`abilityTargets.fromHere`) et rend un
etat **`non exerce` + raison** plutot qu'un verdict. Meme discipline pour toutes les autres causes de
montage degrade (tuile occupee, unite morte, PV illisibles) : un cas non exerce ne compte JAMAIS
comme un accord, et le verdict global refuse de conclure si aucun cas ne reunit les trois gates.

### 3.2 Le seuil natif suit `GetCurrentRange` — le comparateur est INCLUSIF

| `TurnsStarted(Corrodius)` | `GetCurrentRange` | d=1 | d=2 | d=3 | d=4 |
|---|---|---|---|---|---|
| 3 | **2** | riposte | **riposte** | — | n/a |
| 5 | **3** | n/a | riposte | **riposte** | — |

Un comparateur STRICT (`dist < range`) rendrait les seuils **1** et **2**. Le seuil mesure vaut
`range` aux DEUX paliers, et il BOUGE avec `TurnsStarted` — ce n'est donc pas un rayon constant.

**C'est un renversement de `case-224-is-in-contagions-of-nurgle-range.md` §2.1**, qui posait
« rayon UNITE == rayon EQUIPE − 1 ». Cette relation etait tiree de la lecture litterale du
comparateur, et elle n'etait verrouillee **que contre le port lui-meme** : le predicat par unite
n'avait alors aucun consommateur MOTEUR, donc aucun montage ne l'opposait au natif. La fiche le
disait d'ailleurs en propres termes (« le comparateur STRICT de la version par UNITE n'est pas
mesure live »). Porter 1071 le rend confrontable — c'etait l'interet annonce de l'item.

**L'ATTRIBUTION de l'ecart d'une unite — tranchee par LECTURE en #293.** Ce cas-ci laissait ouverts
trois modeles observationnellement indiscernables : comparateur inclusif · `MinDistance` natif =
`hexdist − 1` · `GetCurrentRange` natif = table + 1. Les deux derniers sont **REFUTES etage par
etage** (chemin de distance lu jusqu'a `CubeCoordinate$$Distance` = `Max(|dx|,|dy|,|dz|)` ; arbre
`GetRangeOnOwnerTurn` lu en entier et mirroir exact du port). Le premier est **CONFIRME** :

`IsInUnitContagionsOfNurgleAura` appelle bien un ctor que la table nomme
`AmountIsGreaterAbilityTrigger$$.ctor` (`+0x18 = amount`, `+0x20 = minAmount`), et le `ShouldTrigger`
de CETTE classe finit bien par `return minAmount < amount`, STRICT. **Mais ce nom ne designe pas la
classe instanciee** : ce ctor est un corps trivial que IL2CPP **deduplique** entre toutes les
conditions de meme layout, et la table ne lui donne qu'UN proprietaire. Le pointeur de classe charge
juste avant `il2cpp_object_new` est celui de `IdunBattleLogic.Entities.DSLTriggers$$
AmountIsEqualOrGreater`, donc `AmountIsEqualOrGreaterAbilityTrigger`, dont le `ShouldTrigger` finit
par `return minAmount <= amount`. **INCLUSIF, et lu.**

La mesure ci-dessus n'est donc plus le seul appui du `<=` : elle CONFIRME une lecture qui tient
seule. Re-derivation offline, sans runner :
`python scripts/python/probe_293_aura_predicate_comparator.py --inventory`.

### 3.3 Accord bit-exact, y compris le DOUBLE declenchement

`--advance 10` (range 3), trois psykers, `0 desaccord` :

| psyker | d | cloche natif | cloche port | attaque primaire (natif == port) |
|---|---|---|---|---|
| `astraPrimarisPsy` | 2 | **1795** (1 fire) | **1795** (1 fire) | 2418 |
| `bloodMephiston` | 3 | **4860** (2 fires) | **4860** (2 fires) | 813 |
| `spaceStormcaller` | 4 | 0 (0 fire) | 0 (0 fire) | 1662 |

Le cas `bloodMephiston` est le plus instructif : **DEUX** declenchements pour UNE action. Le dump des
coups le montre — `{a:59 t:51 amt:813}` (attaque primaire) · `{a:59 t:59 amt:2430 pass:1071}` ·
`{a:59 t:55 amt:628 **pass:1013**}` · `{a:59 t:59 amt:2430 pass:1071}`. Le tag `1013` est
`PsykerExtraAttack` : le smite du trait `Psyker` est une **attaque distincte**, donc un second
`On(9)`, donc un second coup de cloche. `On(9)` reste bien PER-ATTAQUE (l'hypothese « par coup
d'arme » est REFUTEE : `spaceStormcaller` a 2 coups d'arme et n'a fait qu'un fire quand il attaquait
en melee). Le port reproduit les deux declenchements **et leur montant**, sans rien de specifique :
son propre vecteur `On(9)` sur le smite suffit.

L'egalite sur l'**attaque primaire** (colonne de droite) est le temoin de synchronisation RNG : sans
elle, un accord sur le recul ne vaudrait rien.

### 3.4 Contre-cas, chacun exerce et non deduit

| gate | montage | natif | port |
|---|---|---|---|
| PORTEE (`IsInContagionsOfNurgleRange`) | `spaceStormcaller` d=4, range 3 | aucune riposte | aucune |
| PROFIL (`CurrentAttackDamageProfilesContain`) | `ultraTigurius` **d=2 (DANS l'aura)**, `--tgt-dist 1` -> il frappe au CONTACT, donc avec son arme MELEE **Physical** (tag `prof: 0`) | aucune riposte | aucune |
| `AreEnemies(Actor, Owner)` | `--allies` : les memes psykers, du camp de Corrodius, a d=2 et d=3 (DANS l'aura), attaquant en Psychic | aucune riposte | aucune |

Le contre-cas de PROFIL est le plus propre : **rien ne change** entre lui et un cas positif sauf
l'arme choisie par la geometrie — meme unite, meme aura, meme camp.

### 3.5 Mutations du fix — cinq mutations, quatre signatures DISJOINTES

| mutation | montage nominal (d=2/3/4) | montage PROFIL | montage `--allies` |
|---|---|---|---|
| entree du registre retiree | **2 rouges** (les deux cas dans l'aura) | 0 | 0 |
| rayon d'aura fige a 1 | **2 rouges** | 0 | 0 |
| comparateur remplace par celui de l'AUTRE classe (**STRICT**) | **1 rouge — exactement `d == range`** | 0 | 0 |
| gate PROFIL retire (rendu toujours vrai) | 0 | **1 rouge** (+1795 fantome) | 0 |
| gate `AreEnemies` neutralise | 0 | 0 | **2 rouges** |

La troisieme est celle qui porte le renversement : elle isole `d == range` et rien d'autre.
`registry` et `range1` partagent leur signature sur ce plateau, faute d'un cas `d=1` exerçable
(cf. §4).

### 3.6 Non-regression (toutes VERTES, re-jouees)

`test_cursed_plague_bell_attack_live.py` (**5**) · `test_contagions_aura_range_live.py` (**3** — le
verrou du comparateur y est RETOURNE, avec sa preuve) · `test_cursed_plague_bell_movement_live.py` +
`test_contagions_of_nurgle_new_unit_live.py` + `test_mow_targeting_predicate_live.py` (**17**) ·
`test_tile_term_unit_gated_playbooks_live.py -k deathBlightbringer` (**10** — la face playbook, dont
le helper de profil DELEGUE desormais au foyer runner) · `test_damage_roll_live.py` +
`test_runner_attack_live.py`. Garde-fous du registre : `probe_181_targeting_gaps` et `probe_120`
(sans objet ici — aucune entree dans `ABILITY_CLASSES` — mais verifies, pas supposes).

---

## 4. Ce que ce cas n'etablit PAS

* **Le cas `d = 1` a `range = 1`** (`TurnsStarted <= 2`) n'a **jamais pu etre monte** : sur `C1_02`,
  aucune tuile libre et marchable n'existe a distance 1 de Corrodius aux paliers bas (il est
  entoure). Consequence directe : `registry` et `range1` ne se distinguent pas par leur signature de
  mutation. Le modele porte le predit (riposte), aucune mesure ne le confirme. Un board a voisinage
  ouvert autour du spawn adverse leverait les deux points d'un coup.
* **Le gate `HasTrait(Actor, Psyker)` n'est exerce qu'en POSITIF.** Balayage du roster : **aucune**
  unite ne porte une arme de profil Psychic sans porter aussi le trait `Psyker` (0 sur 683). Le
  contre-cas « non-psyker qui attaque en Psychic » n'existe donc pas dans le jeu, et il n'est pas
  fabricable sans poser un trait en bataille. Le gate est porte (mirror) mais son cote negatif reste
  non mesure.
* **La disjonction `OwnerIsTarget | OwnerIsAlive` n'est pas discriminee** : sur tous les montages
  l'owner est vivant, donc la branche de droite suffit. La branche `OwnerIsTarget` ne devient
  observable que si l'attaque TUE Corrodius dans le meme flot — non exerce.
* **`selectionType = 2 = OnlyTargetable`** (8e argument de l'`AttackWithAttackDamage` natif) n'est
  pas materialise cote port : la cible est l'Actor lui-meme, vivant par construction. Meme residu que
  tous les selecteurs d'occupation du port.
* **Le collapse `Caster == Actor`** du gate `!CasterIsTarget` : le `TriggerEvent` du port n'a pas de
  slot CASTER distinct sur un evenement d'attaque. Le collapse tient sur les deux vecteurs `On(9)`
  portes ; il tomberait pour un vecteur ou le caster de l'ability differe de l'acteur du coup.
* **`!CurrentAbilityIs(this)`** — ce point est **CLOS et REFUTE** par
  `case-292-current-vs-triggering-ability.md` : le canal `state.triggering_ability` EST
  `CurrentAbility` (`AbilityEntities+0x60`). Son NOM designe l'autre champ, sa SEMANTIQUE est la
  bonne — `BaseTriggeredAbility$$Execute` ecrit `+0x60` AVANT le behaviour (ce que le port
  reproduit) et `+0x98` APRES, pour le seul `On(0xd = UnitTriggeredAbility)`, non porte. Ce qui
  reste vrai ici : le gate n'est jamais exerce SEUL, `!CasterIsTarget` le couvrant
  (`probe_224 --mutate nogate` = 0 desaccord). Ce qui est desormais MESURE : la portee du canal,
  par `--mutate persist` (restauration supprimee -> le second coup de cloche du smite 1013
  disparait, 4860/2 fires -> 2430/1 fire).
* **Le `dmg` est lu au niveau du PORTEUR** : dans un runner rank-based, `passive_ability_level` et
  `active_ability_level` coincident souvent, et le psyker attaquant a le meme rank. Le montage ne
  DISTINGUE donc pas « niveau du porteur » de « niveau du caster » — la lecture est celle du
  decompile, elle n'est pas mesuree contre son alternative.
* **`CursedPlagueBellDangerZoneAbility` / `CursedPlagueBell_DangerZoneEffect` (1084)** et la branche
  `isNextTurn = true` : hors perimetre, toujours non portees.

---

## 5. Reproduire

```bash
cd scripts/python
python probe_224_cursed_plague_bell_attack.py --offline-only
python probe_224_cursed_plague_bell_attack.py --board C1_02 --seed 4242 --advance 6  --dists 1,2,3
python probe_224_cursed_plague_bell_attack.py --board C1_02 --seed 4242 --advance 10 --dists 2,3,4
python probe_224_cursed_plague_bell_attack.py --board C1_02 --seed 4242 --advance 10 --dists 2,3 --allies
python probe_224_cursed_plague_bell_attack.py --board C1_02 --seed 4242 --advance 10 --dists 2 \
    --psykers ultraTigurius --tgt-dist 1                       # contre-cas de PROFIL
python probe_224_cursed_plague_bell_attack.py --board C1_02 --seed 4242 --advance 10 --dists 2,3,4 \
    --mutate strict                                            # contre-epreuve du renversement
python -m pytest tests/engine/runner/test_cursed_plague_bell_attack_live.py -q
```

Le probe n'arme **aucun hook** (il ne lit que `decisionView` / `observeBattle` / `combatSnapshot` /
`boardGraph` / `abilityTargets` / `dumpRng` et pilote par `applyAction`), construit et **dispose** son
runner. `--keep` le conserve.

⚠ Les PV sont gonfles (`--hp-player` / `--hp-target` a 999999) : sans cela, `--advance 10` tue les
psykers avant la mesure et la passe rend « aucun cas exerce ».
