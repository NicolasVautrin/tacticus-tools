# #893 — `1049 CrusadeOfWrath` : le no-op fermé, et l'audit qui n'en annonçait qu'une des trois

**Verdict : PORTÉ + CONFRONTÉ LIVE.** Build `rnca9r7q6c`. Porteur `templHelbrecht` (HERO Black
Templars), **déjà au pool** — aucun montage (ni injection catalogue, ni greffe npc, ni summoner).

## 1. L'artefact natif, tel qu'il est lu

`IdunBattleLogic.Entities.Abilities.Active.Loki.CrusadeOfWrathAbility$$ExecuteBehaviour` — **un seul
nœud terminal** passé à `IdunBattle.Entities.Abilities.AActiveAbility$$Execute` :

```
range  = AbilityConfiguration.GetNumberConstant(config@this+0x60, 0x16 = range)      -> 2
buffed = DSLSelectors.Friends(
             of       = Owner@DSLSelectors+0x30,
             entities = DSLSelectors.SurroundingUnits(origin = CasterTile@+0x50, range = range,
                                                      unique = 1, includeCenter = 0,
                                                      unitSelectionType = 3)
                        op_Subtraction Caster@+0x48,
             selectionType = 3)
turns  = DSLFormulas.TurnsFromRounds(2)

[A] dmg    = DSLBehaviors.AddStaticStatModifierEffect(buffed, 0x43e = 1086
                 CrusadeOfWrath_ExtraDamage, statType = 0 Attack,
                 amount = Direct(GetVariableForLevel(8 = extraDmg)), turns, isHidden = false)
[B] pierce = DSLBehaviors.AddStaticStatModifierEffect(buffed, 0x43f = 1087
                 CrusadeOfWrath_ExtraPierce, statType = 0x15 = 21 ExtraPierceMelee,
                 amount = Direct(GetVariableForLevel(0x3f = extraPierceRatio)), turns, isHidden = false)
[C] sel    = DSLSelectors.ValidNormalAttackTargets(CasterTile@+0x50, CasterTile@+0x50, null, null, null)
             op_BitwiseAnd DSLSelectors.AdjacentEnemies(Caster@+0x48, unique = 1, selectionType = 3)
    attack = DSLBehaviors.UseActiveAbility(caster = Owner@+0x30,
                 target = PickRandomly(sel, 1, 0, 0x7fffffff, 0),
                 activeAbilityType = DSLSelectors.UnitNormalAttackType(Owner@+0x30),
                 parentAbility = Nullable(AbilityOrEffect(this+0x10)), trigger/options ZÉROES)
    free   = DSLBehaviors.If(AmountIsGreaterThanZero(Count(sel)), attack, null)

AActiveAbility.Execute(entities, this, [A] op_BitwiseAnd ([B] op_Addition [C]))
```

`...$$GetBuffTargets` est la fonction **nommée** qui porte `buffed` ; `$$ExecuteBehaviour` recopie
l'expression **inline** au lieu de l'appeler → **un seul foyer** côté port. Le natif, lui, appelle
bien `$$GetBuffTargets` depuis un second site : `IdunBattle.AI.Playbook.Loki.CrusadeOfWrathPlaybook$$GetMaxFriendlyUnitsBuffed`
(face DÉCISION, § 5).

## 2. La catégorie annoncée était INCOMPLÈTE — deux mécaniques sur trois

`docs/rl/combat-ability-coverage.md` classait 1049 en `EFFECT/BUFF` (colonne dérivée du
`damageProfile` de l'**arme du porteur**, pas du behaviour). C'est vrai de [A] et [B]. **[C] FRAPPE**
— par l'attaque NORMALE de l'unité, pas par une `AttackWithAbilityDamage` : `abilities.CrusadeOfWrath`
n'a **ni** `minDmg`/`maxDmg`, **ni** `nrOfHits`, **ni** `damageProfile` (gameconfig : deux variables
`extraDmg` / `extraPierceRatio` et une constante `range` = 2). Même configuration que `HolyDuel`
(1050), `UnbreakableDuty` (1061) et `Drachnyen` (1029).

**Le caster ne se buffe PAS**, et le natif l'écrit deux fois : `includeCenter = 0` exclut sa tuile de
`SurroundingUnits`, puis `op_Subtraction Caster@+0x48` l'ôte une seconde fois. C'est le « All
**other** friendly units » de l'i2. Conséquence observable : l'attaque libre part **sans** le
`+extraDmg` du cast — l'inverse de `UnbreakableDuty`, dont l'ordre `[C] dmgBuff` puis `[D] attaque`
fait bénéficier le caster de son propre buff.

## 3. Le masque : surcharge tranchée par ses XREFS ENTRANTES

`...CrusadeOfWrathAbility$$.ctor` recopie les 3 qwords de `<TargetingRange statics>+0x18`
(= `useRangeFromConfig`, `RANGE_FROM_CONFIG`) puis appelle
`TargetingOptions$$.ctor(&opts, 1, &range, 1, 0x400, 0, 0)`, enfin
`AActiveAbility$$.ctor(this, &opts, 2)`.

`IdunBattle.Core.Services.TargetingOptions$$.ctor` a **trois** surcharges ; `list_xrefs` place ce
call-site sur celle à **six paramètres** (`isSelfCasting, range, forceMeleeTarget, rules,
getDynamicInvalidCasterReason, getDynamicInvalidTargetReason`, lue dans `frida/methods.tsv`) — ni
l'overload PRESET+FLAGS, ni la copie pure. Le `0x400` visible **est** donc le masque effectif.

* `rules` = `0x400` = `TargetIsFriendly`, **seul**
* `selfCast` = 1 · `forceMeleeTarget` = 1 = `RangedBool.False` · `range` = `RANGE_FROM_CONFIG`
* `AbilityAttackType` = **2 = `Others`** (3ᵉ argument du ctor, TRANSCRIT — l'arbre frappe, ce qui
  ferait écrire `DirectTargetAttack` à l'œil, et c'est justement la lecture inverse qu'ont donnée
  `HolyDuel` 1050 et `Drachnyen` 1029, même forme d'arbre, littéral `0`).

⚠ **Contre-exemple load-bearing** : le voisin `UnbreakableDuty` (1061), **même forme de ctor** et
**même `TargetingRange` statique**, porte `0x8400` = `TargetIsFriendly | CasterIsPossibleTarget`.
Recopier le masque du voisin aurait ouvert le cast sur le caster — que l'arbre exclut deux fois.

## 4. Ce que la confrontation live DISCRIMINE, et ce qu'elle ne discrimine pas

`tests/engine/runner/test_893_crusade_of_wrath_live.py` — 5 bras, board `MC1_67`, positions FORCÉES
et distances hex **re-assertionnées au runtime** contre `boardGraph` (un montage qui n'installe pas
la géométrie ÉCHOUE, il ne rend jamais un verdict sur le port).

**Quatre témoins NÉGATIFS dans le même runner** : le CASTER, un allié à distance **3**, un ennemi à
distance **2** (dans la portée du buff — c'est `Friends` qui l'écarte, pas la géométrie), et ce même
ennemi non adjacent qui ne doit pas être frappé. L'allié à distance **2** est la BORNE `<= range`.

Mesures live (port == natif sur les six axes) :

| axe | natif | port |
|---|---|---|
| porteurs de 1086 / 1087 | les 2 alliés (dist 1 et 2) — ni caster, ni allié dist 3, ni ennemis | identique |
| magnitude `Attack` | +499 | +499 |
| magnitude `ExtraPierceMelee` | +24 | +24 |
| `statType` (tags `UnitStats_<Stat>_Modification_Change`) | `Attack` / `ExtraPierceMelee` | identique |
| durée (`Effect_RemainingTurns`) | 4 tours | `TurnsFromRounds(2)` → 4 |
| attaque libre | 6 coups mêlée sur l'ennemi adjacent, `Active_Ability_Type = 69 Loki_NormalAttack` | même cible, même séquence coup par coup |
| gate `If(Count > 0)` | aucun ennemi à distance 1 → **aucune** attaque, buffs quand même posés | identique |

⚠ **DEUX FOIS l'écart a d'abord accusé le port, à tort** — et les deux fois c'est le TÉMOIN qui
était faux :

1. **magnitude 499 vs 277.** Le témoin dérivait `extraDmg` du gameconfig **nu** (niveau 50,
   multiplier neutre). Le porteur porte `AbilityVariablesMultiplierPercentage = 180`, et `extraDmg`
   **est** dans `variablesAffectedByRarityBonus` : `round(277 × 1,80) = 499`. Le port le calculait
   déjà. Le témoin dérive désormais ses valeurs de `CrusadeOfWrathAbility._params(state, caster)` —
   c'est ce qui le COUPLE au port. Contrôle croisé : `extraPierceRatio` n'est **pas** dans
   `variablesAffectedByRarityBonus` et vaut 24 des deux côtés, à multiplier 100 comme à 180.
2. **« aucune attaque ».** Le témoin attribuait les `UnitDamaged` par `Source_Id` — un tag qui
   **n'existe pas** sur ce pas ; la clé est `Attacker_Id`. Et l'attaque libre porte
   `Active_Ability_Type = 69 Loki_NormalAttack`, **pas** `1049` : filtrer par l'ability rendait un
   ensemble vide, qui se lisait comme « le natif n'a pas attaqué ».

⚠ **`mutated` n'est PAS un critère de cast réussi.** Mesuré : sur le régime SANS attaque libre le
natif rend `mutated: False` / `changes: []` alors que les **quatre** effets sont posés et
`actionConsumed: True`. Le critère est `actionConsumed` + les événements.

**NON DISCRIMINÉ, et écrit plutôt que tu** :

* le **choix** de la cible du `PickRandomly(sel, 1)` — le montage ne laisse qu'UN ennemi adjacent,
  donc la cible est fixée par la géométrie, pas par le tirage ;
* l'**expiration** effective des deux effets au bout de 2 rounds — seul le compteur `remaining`
  publié à la pose est confronté, pas sa décroissance ;
* le second terme de l'exclusion du caster (`op_Subtraction Caster@+0x48`) **pris seul** : sur une
  unité mono-tuile il est redondant avec `includeCenter = 0`. Le mutant `CASTER_INCLUS` retire donc
  les DEUX ;
* le `selectionType = 3` d'`AdjacentEnemies` : posé parce qu'il est LU, mais **inerte** à ce
  call-site (l'intersection avec `ValidNormalAttackTargets` applique déjà la cascade complète).

### Le banc de mutants — `probe_893_mutants.py`

**9 mutants, 9 mordent en live** (6 mordent aussi offline ; les 3 de `_params` sont live-only, les
bras offline dérivant du gameconfig nu). Arbre restauré vert **avant et après**.

⚠ **Trois mutants étaient INERTES à la première passe**, et le banc l'a dit au lieu de les compter
verts : leur motif matchait **deux fois** dans `blacktemplars.py` — le `_params` du voisin
`UnbreakableDuty` porte les mêmes lignes. L'ancre est passée sur **deux** lignes. Un banc qui ne
vérifie pas l'unicité de son motif rend des mutants qui ne mutent rien.

## 5. Résidus ouverts

* **`#893-r1` — face DÉCISION non portée.** `IdunBattle.AI.Playbook.Loki.CrusadeOfWrathPlaybook`
  est un `ComparablePlaybook<CrusadeOfWrathAbility>` (ctor `0x419 = 1049`). Son
  `$$GetUseProbability` = `<Fix64 statique @ statics+0x08> × $$GetMaxFriendlyUnitsBuffed(unit)`, et
  ce dernier balaie les tuiles rendues par le slot de query `this+0x28` en prenant le **MAX** du
  cardinal de `$$GetBuffTargets(Entity(unit), Entity(tuile))`. C'est le sous-arbre déjà porté,
  évalué **depuis chaque tuile atteignable** — donc un scorer de POSITIONNEMENT, pas un gate.
* **`#893-r2` — la SOURCE de l'entité-effet des `AddStaticStatModifierEffect`.** Lu au décompilé :
  `DSLBehaviors$$AddStaticStatModifierEffect` passe `source = **null**` à
  `AddStatModifierEffectBehaviour$$.ctor`, et `...$$Execute` retombe alors sur la **CIBLE**
  (`lVar9 = <cible courante>; if (source != 0) lVar9 = <source évaluée>;`). Mesuré live :
  `Effect_SourceId` = l'allié buffé, jamais le caster. Le port, dans son foyer **partagé**
  `AddStaticStatModifierEffect.execute`, passe `source = le CASTER`. Aucune conséquence mesurée sur
  1049 (montant, stat, durée et porteurs concordent tous) — mais l'écart est réel et le foyer sert
  au moins **1049 / 1175 BloodChalice / 1222 MassDriverAccelerator / 1106 Waaagh**, d'où un résidu
  plutôt qu'une retouche de feuille partagée dans une tranche d'ability. Le bras live GÈLE la
  mesure NATIVE (il n'accuse pas le port) : s'il rougit, c'est le natif qui a changé.
* **`#468-r13` — l'espace des TÂCHES a rattrapé celui des PR, et `--suggere` ne peut pas le voir.**
  Son corpus de messages est `git log --format=%s%n%b --no-merges` : les **622** commits de merge du
  dépôt, dont le sujet est exactement `merge(#<PR>) : <titre>`, en sont **exclus** — donc tous les
  numéros de PR. Cette tranche a payé la faute **deux fois** :
  1. `--suggere` a d'abord proposé `#888` comme LIBRE, alors que `#888` était le numéro de PR du
     commit de base (`9b51d9cf merge(#888) : …`), et que `#889` / `#890` étaient des PR en vol.
     Numéro pris à la place : `#891`, au-dessus du max PR **alors** mesuré par `gh` (890).
  2. Pendant la tranche, la **PR #891** a été mergée dans `master`
     (`0216e70f merge(#891) : quatre rouges, quatre causes …`). Le numéro de tâche désignait dès
     lors le travail de quelqu'un d'autre : renumérotage complet en **#893** (4 fichiers renommés,
     3 lignes de backlog, la case-doc et les commits refaits).

  `#468-r8` établit que tâche et PR partagent le namespace `#<n>` ; la politique écrite dans le
  probe (« ON GARDE LES NUMEROS DE PR … sauter coûte un entier ») supposait explicitement que
  l'espace des tâches était loin derrière (« borne 480 » vs « ~670 PR »). **Cette hypothèse est
  morte** : borne tâches **891**, max PR **892**. Toute allocation de tâche collisionne désormais
  avec un numéro de PR — et vraisemblablement avec celui de sa PROPRE pull request. Deux volets :
  (a) lire les sujets de merge (coût nul, même `git log`) ; (b) trancher ce qu'on fait quand les
  deux espaces se croisent — un préfixe qui les sépare, ou accepter la collision et l'écrire.
  ⚠ `#893` est pris en sachant qu'il vaudra probablement AUSSI le numéro de cette PR. C'est un choix
  documenté, pas un oubli : une tâche qui porte le numéro de sa propre PR est bien moins ambiguë
  qu'une tâche qui porte le numéro de la PR d'un autre.

## 6. Ce qui n'est PAS couvert

* Les deux porteurs **npc** (`templBossHelbrecht`, `templBossHelbrecht_LHE`) : non confrontés — le
  porteur `lineup` suffit et couvre le même arbre.
* Le fait que l'attaque libre **ne consomme pas** l'attaque normale du tour
  (`UnitStats_ActiveAbility_Id: 69, CanStillBeUsed: 1` dans le flux) : observé, non gardé — c'est le
  foyer de `UseActiveAbility`, pas celui de 1049.
* La face DÉCISION (§ 5, `#893-r1`).
