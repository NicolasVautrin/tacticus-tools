# #585 — `WarHowl` (1106) : la POSE, et le filtre que l'i2 ne dit pas

Ferme le **résidu 6.3** de `case-366-r1-war-howl-extra-damage.md` (« la POSE n'est pas portée »).
Cette fiche-là garde la **LECTURE** de l'effet `WarHowl_ExtraDamage_Unstoppable` (1222) quand le
natif l'a posé ; celle-ci porte **qui le reçoit**, **le trait qu'il accorde**, et **son retrait**.

## 1. Ce que l'ability EST, et ce que l'audit en disait

`1106 WarHowl` est l'active de `spaceBlackmane` « Ragnar » — son **unique** porteur. L'audit la
classe *EFFECT/BUFF*, colonne dérivée du `damageProfile` de l'**arme** du porteur. C'est juste sur
un axe et **muet sur les quatre autres** : il n'y a **aucune attaque** dans
`WarHowlAbility$$ExecuteBehaviour` (ni `AttackWithAttackDamage`, ni `AttackWithAbilityDamage`), la
portée est **board-wide** (aucun rayon), et la mécanique la plus structurante est un **octroi de
trait** — donc un effet de **MOUVEMENT**, pas de dégât.

**CINQ mécaniques**, appariées une à une aux nœuds et au tooltip i2 :

| # | i2 | artefact natif | statut |
|---|---|---|---|
| 1 | « If Ragnar has not moved » | bit `CasterHasNotMoved` du masque | déjà porté (masque) |
| 2 | « he and all friendly Characters that don't have a normal ranged attack » | `op_Addition(Owner, OtherBuffTargets())` | **cette tranche** |
| 3 | « gain Unstoppable until the end of this turn » | `ApplyInternal` → `AddTrait(0x412, isTemporary)` | **cette tranche** |
| 4 | « +{[extraCritChance]}% Crit Chance » | `$$CreateCritChanceBonus` | porté (#366-r1) |
| 5 | « +{[extraDmg]} Damage » | `$$CreateEffectDamageBonusForAttack` | porté (#366-r1) |

Le dernier paragraphe i2 (« does not end Ragnar's turn ») est déjà couvert : 1106 est dans **les
deux** inventaires d'override de `abilities/base.py`.

## 2. L'arbre, lu au décompilé

`IdunBattleLogic.Entities.Abilities.Active.Loki.WarHowlAbility$$ExecuteBehaviour` — **un seul
nœud** :

```
Execute( AddEffect( 0x4c6 = 1222,
                    abilityState = CreateSnapshot(<abilityState du cast>),
                    source       = <DSLSelectors+0x48 = Caster>,
                    targets      = op_Addition(<+0x30 = Owner>, OtherBuffTargets()),
                    turns        = DSLFormulas.Get(1) ) )

OtherBuffTargets() =
    UnitsWithoutTrait(
        UnitsWithoutRangedWeapons(
            Friends( of = <+0x30 = Owner>,
                     entities = op_Subtraction(<+0x20 = AllAliveUnits>, <+0x30>),
                     selectionType = 3 ) ),
        trait = 0x2 = UnitTrait.Summon, selectionType = 3 )
```

Trois lectures **tranchées par les xrefs, pas à l'œil** :
* la surcharge d'`AddEffect` est celle à **six** arguments (`…, source, targets, turns`) — le
  binaire en porte quatre du même nom ; c'est la même que `WaaaghAbility$$GetBuffBehaviour` ;
* `DSLFormulas.Get(1)` est la surcharge `Get(int)` → un `DirectAmount(1)`, donc **1 TOUR** et non
  un `TurnsFromRounds` (le `param_6` d'`AddEffectOperation$$Execute` ne convertit pas) ;
* `AActiveAbility..ctor(this, &opts, 2)` → `AbilityAttackType.Others`, **transcrit**.

## 3. Le quatrième filtre — `selectionType = 3`, et il MORD

`IdunBattle.DSL.TargetsSelector$$SelectUnit(entity, selectionType)` termine par
`UnitExtensions$$MatchesUnitSelectionType`, dont le corps relu est :

```
if (unit == null || GetEntityType(unit) != Unit)  return false;
switch (selectionType) {
  case 1: return IsAlive(unit, state);                             // OnlyAlive
  case 2: return !HasFlag(unit, 0x11 Untargetable);                // OnlyTargetable
  case 3: return IsAlive(unit, state) && !HasFlag(unit, 0x11);     // OnlyAliveAndTargetable
  default: return true;                                            // Any
}
```

**MESURE (`MC1_67` / seed 777, trois Space Wolves du MÊME côté)** :

| | tour 1 (deep strike) | après atterrissage |
|---|---|---|
| `spaceBlackmane` (caster) | **buffé** | **buffé** |
| `spaceRockfist` (ami MÊLÉE pur) | **non buffé** | **buffé** |
| `spaceStormcaller` (arme `Range = 2`) | non buffé | non buffé |
| les deux necrons | non buffé | non buffé |

Arjac est retenu par **tous** les autres filtres (ami, mêlée, non-Summon) : la seule chose qui
change entre les deux colonnes est son `TeleportStrike_TeleportingIn`, qui pose
`UnitFlag.Untargetable` (`unitFlags: [17]`, mesuré). Sans ce `selectionType`, le port **sur-buffait
en silence**.

⚠ **L'annotation « (armes à distance) » de `case-366-r1` §2 est RÉFUTÉE.** Arjac n'a **qu'une**
arme, MÊLÉE (`Range` absent), au gameconfig **comme** dans `data/seed-bc.json` (`Power`, 3 coups).
Ce qui l'écartait ce jour-là était le **camp** — le montage de `probe_366_r1` ne met que deux
unités côté joueur, et `Friends` suffit alors à l'exclure sans qu'aucune arme n'entre en jeu.
C'était une **interprétation**, jamais mesurée ; le montage à trois alliés la tranche.

## 4. Vue ROUGE par mutation — **trois**, chacune vérifiée POSÉE avant le run

| mutation | régime | LIVE | PORT | verdict |
|---|---|---|---|---|
| `SELECTION` → `UnitSelectionType.Any` | `--land-turns 0` | `[81]` | `[81, 83]` | **DIVERGE** |
| `UnitsWithoutRangedWeapons` retiré | `--land-turns 2` | `[81, 83]` | `[81, 83, 85]` | **DIVERGE** |
| `applied_traits()` → `[]` | `--land-turns 2` | trait natif `[81]` | face PORT `[]` | **DIVERGE** |

⚠ **La troisième laisse les DEUX premiers bras VERTS.** Les bras « selecteur » et « trait rendu à
l'état initial » ne lisent que l'**oracle natif** (`combatSnapshot.units[].traits`) : ils ne voient
pas un canal de port éteint. C'est pour ça que le probe rejoue `execute_behaviour` **offline** sur
l'état d'avant le cast et lit les traits **du port** — le bras qui **couple la garde à la valeur du
port**.

⚠ **Une mutation qui ne mord pas est un faux vert**, et ça s'est produit ici : un
`git checkout -- <fichier>` a restauré une version antérieure au dernier commit et le motif de
substitution a disparu — la « mutation » M2 a rendu `OK` sans avoir été posée. Depuis, chaque
mutation **assertionne la présence du motif** (`MOTIF ABSENT -> exit 3`) et la référence est
**commitée avant**.

## 5. Ce que le port a gagné, et ce qu'il coûte

* **Sélecteur** `UnitsWithoutRangedWeapons` (`entities/selectors/units.py`) — mirror de
  `UnitsWithoutWeaponsSelector$$Select`, prédicat `WeaponProfile$$get_IsRanged` (= `!get_IsMelee`,
  seuil `Range >= 2`). Le nœud applique en dur `SelectUniqueUnits(..., 1 = OnlyAlive)`, **littéral
  lu** dans le corps natif — il ne prend pas de paramètre, pour qu'aucun appelant ne lui passe le
  `3` qui appartient à ses voisins.
* **Foyer partagé** `services/battle_query.has_ranged_weapon` — `WeaponsComponent$$HasRangedWeapon`,
  branché sur `ctx.has_ranged_weapon` et sur `playbook/adjacent_unit_preference`, qui en portait sa
  propre copie (fork résorbé). ⚠ **Ce n'est PAS** le tri d'`UnitExtensions$$IsRanged` porté par
  `services/ability_range` (« présence d'un `Range` ») : deux fonctions natives, deux seuils.
* **Mirror** `UnitSelectionType` + `matches_unit_selection_type` (`entities/unit_selection_type.py`),
  inscrit au registre de `probe_313` **dans le même commit**. Câblé en paramètre **optionnel** sur
  `Friends` et `UnitsWithoutTrait` : `None` = comportement historique, donc **zéro** call-site
  existant n'est touché. Relever le littéral aux ~100 call-sites portés est une tranche à part —
  même régime que le flag `unique` de `Units` (résidu **#585-r1**).
* **Canal TRAIT** — `BaseEffect.applied_traits()` (part DATA) + `operations/traits.py`
  (`AddTraitOperation` / `RemoveTraitOperation`, mirrors 1:1) + trois points de câblage :
  `AddEffectOperation.execute` (apply), `remove_effect_instance` (retrait explicite),
  `EndTurnOperation` (expiration). La feuille DSL `AddTrait` **délègue** désormais à la même
  Operation — le natif y arrive par deux voies (nœud DSL et `ApplyInternal`), le port n'a qu'un
  foyer.

⚠ **`applied_trait_grants` porte un cran que la déclaration ne porte pas.** Le natif s'arrête dès
que `coll.Add(trait)` rend `false` (trait DÉJÀ porté), donc un trait de **kit** ne doit pas partir
au retrait de l'effet. Le port fusionne les deux collections natives (`+0x40` permanents / `+0x48`
temporaires) en un seul ensemble de NOMS — seule la liste mémorisée à la pose distingue « posé par
moi » de « déjà là ». **MESURÉ** : `spaceRockfist` et `spaceStormcaller` portent `Unstoppable` au
kit et reçoivent 1222 ; sans ce cran, l'expiration du buff leur volerait leur trait permanent.

`AddDerivedAbilities` (l'étage qui suit le `coll.Add` natif) est un **no-op pour 1042**, et c'est
mesuré : `0x412` n'est clé d'aucun des deux dicts statiques de
`StaticBattleRules.Trait$$.cctor` (41 clés pour `GetTriggeredAbility`, 2 pour `GetActiveAbility`).
L'étage n'est donc pas porté ; `traits.derived_abilities_are_a_noop` le **dit** au lieu de
l'ignorer.

## 6. Effet de bord bénéfique — `#366-r1-src` fermé POUR CETTE VOIE

`scale_from_source=True` est le port du `CreateSnapshot(abilityState)` natif : l'effet **posé**
résout ses `ConfigVar` contre l'`AbilityState` de sa **SOURCE**. Le résidu `#366-r1-src` (#382)
mesurait exactement l'écart que ça produit (`spaceBlackmane` = 200, `spaceWulfen`/`spaceHound` =
180 → 1772 contre 1595). Il reste **entier pour un effet SEEDÉ** (chargement d'un état où le natif
avait déjà posé) : `EffectsState.seed` est clé par PORTEUR.

## 7. Ce qui n'est PAS couvert

* **La face DÉCISION.** `IdunBattle.AI.Playbook.Loki.WarHowlPlaybook` existe et n'est **pas**
  portée — résidu **#585-r2**. Son `$$EvaluateNonComparable` verse une action par cible éligible à
  utilité **constante** `Fix64(1)` ; son `$$GetUseProbability` compte les alliés dont
  `<IBattleQuery slot 0x45>(unit, GetNormalAttackType(unit))` rend un profil non nul et rend
  **50 / 75 / 50 / 100** pour 0 / 1 / 2 / ≥3 — un palier **non monotone** (2 vaut moins que 1),
  lu verbatim et non expliqué.
* **Le gate dynamique CASTER.** Le bit `CasterMatchesDynamicRule` est posé et la classe n'expose
  aucun corps `$$GetDynamicInvalidCasterReason` — l'absence ne prouve rien (dédup IL2CPP). Entrée
  `CASTER_GATE_NOT_READ` inchangée.
* **`is_temporary`** n'a **aucun observable distinct** côté port (les deux collections natives sont
  fusionnées). Le drapeau est transporté ; il documente le call-site lu.
* **Le consommateur du trait** (exemption de blocage `Fire`/`Ice`/`BlockEnteringUnits` par
  `WalkPathfinder$$GetTileBlockingReasons`) est porté mais **non exercé** par ce montage : il
  faudrait un board à tuiles bloquantes sous une unité fraîchement buffée.
* **Le `selectionType` des ~100 autres call-sites** reste à `None` (résidu **#585-r1**).
