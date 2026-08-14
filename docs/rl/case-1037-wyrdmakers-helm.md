# #1037 — `WyrdmakersHelm` (1504), relique unique de `spaceWolfPriest`

Item `R_Booster_Crit_WyrdmakersHelm` (`isRelic`, `isUniqueRelic`, `allowedUnits = ['spaceWolfPriest']`).

> « During his turn, each time Baldr or an adjacent friendly unit gets healed for the first time this
> turn, Baldr immediately performs a normal melee attack. These attacks deal +{extraDmg} Damage and
> add Ice to the target's hex. »

## 1. UN SEUL artefact natif — verifie, pas suppose

`frida/classes.tsv` du build `rnca9r7q6c` ne porte qu'UNE classe `Wyrdmaker*` :
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.WyrdmakersHelmAbility` (base
`IdunBattle.Entities.Abilities.BaseTriggeredAbility`), et `search_symbols_by_name` n'en trouve que
`$$CreateTrigger` et `$$CreateBehaviour`. **Aucune classe d'effet, aucune seconde ability** —
contraste `TheArdentBlade` / `PhasalSubjugator` / `Maugetar`, qui enregistrent plusieurs classes sur
un meme id.

⚠ **1504 et 1505 sont DEUX enums, meme nom** : `TriggeredAbilityType.WyrdmakersHelm = 1504` est
l'ABILITY, `EffectType.WyrdmakersHelm = 1505` est l'etiquette du stat-mod pose puis retire DANS
l'arbre. Les confondre serait silencieux (ordinaux voisins, tous deux valides).

## 2. RE

    WyrdmakersHelmAbility$$CreateTrigger =
        On(0x2c = EventTriggerType.UnitHealedWithRemoveEffects, ownerNeedsToBeAlive: true)
      & ( get_OwnerIsTarget
          | ( IsAdjacent(Owner@DSLSelectors+0x30, Target@DSLSelectors+0x60,
                         selectionType: 3 = UnitSelectionType.OnlyAliveAndTargetable)
            & AreFriends(Owner, Target, comparisonType: 0 = UnitTeamSelectionType.ByCurrentTeam,
                         anyEntity: false) ) )
      & AmountIsEqual( TimesHealedThisTurn(Target@+0x60), <DSLFormulas+0x20> = Constant(1) )
      & <DSLTriggers+0x28> = IsTurnOf(Owner)

    WyrdmakersHelmAbility$$CreateBehaviour =
        AddStaticStatModifierEffectToOwner(0x5e1 = 1505, statType: 0 = StatType.Attack,
                                           ConfigVar(8 = AbilityVariableType.extraDmg), turns: null,
                                           isHidden: false)
      + SetCache( Cache(Tiles(First(SortUnitsByDamageUtility(
            Randomize(ValidNormalAttackTargets(Owner, Tiles(Owner))), Owner,
            UnitNormalAttackType(Owner), UtilityDefinition(0x23 = UtilityType.Damage),
            NormalAttackDamage(Owner), 0 = UnitSelectionType.Any, null), 1, false))), true) )
      + UseNormalAttack(Owner, <la cible choisie>, null, null, <options>)
      + RemoveEffect(Owner, Nullable(0x5e1), null)
      + If( NOT IsDead(Owner), AddEffect(0x11 = EffectType.Ice, AbilityStateReference, <cache>,
                                         turns: null), null )

Trois lectures qui portent la mecanique, et l'ORDRE des `op_Addition` les etablit :

* le bonus d'ATTAQUE est pose AVANT l'attaque et retire APRES -> il ne vaut QUE pour ce coup ;
* `SetCache` FIGE la tuile de la cible AVANT l'attaque -> la glace atterrit meme si la cible y meurt ;
* le `If` final gate sur **NOT IsDead(OWNER)**, pas sur la cible : si Baldr meurt de sa propre
  attaque (riposte, overwatch), la glace n'est pas posee.

**Litteraux tranches par le TYPE DECLARE** (`frida/methods.tsv`), jamais par l'ordinal :
`IsAdjacent.selectionType: UnitSelectionType` (3) et `AreFriends.comparisonType:
UnitTeamSelectionType` (0) sont **deux enums differents** pour deux parametres voisins — les
confondre serait juste en ordinal et faux en semantique. `<DSLFormulas+0x20>` = `Constant(1)` est
etabli par `DSLFormulas$$.ctor` (`+0x18 = 0`, `+0x20 = 1`, `+0x28 = 2`, `+0x30 = 100`, `+0x38 = -1`) :
c'est ce `1` qui EST le « for the FIRST time this turn ».

⚠ **`AmountIsEqual` a TROIS surcharges, dont une MENT** : `180ed5190` construit un
`AmountIsGreaterAbilityTrigger` sous un nom `AmountIsEqual` (fold ICF). Celle appelee est tranchee
par les **XREFS ENTRANTES**, pas par le nom : `WyrdmakersHelmAbility$$CreateTrigger` appelle
`180ed5120`, qui construit bien un `AmountIsEqualAbilityTrigger`. C'est une EGALITE.

## 3. DEUX etages natifs manquaient — c'est l'essentiel de la tranche

Le port aurait ete INERTE sans eux, et silencieusement :

**(a) le compteur `TimesHealedThisTurn`.** `TimesHealedThisTurnFormula$$Calculate` resout son
selecteur et rend `*(uint *)(ActorStatisticsComponent + 0xd4)`. Ce champ est incremente **par soin**
par `HealUnitOperation$$Execute`, et remis a zero par `StartTurnOperation$$ResetUnit` — **pas** par
`ActorStatisticsComponent$$ResetThisTurn`, qui n'efface que `+0xf0`/`+0x78`/`+0xe4`/`+0x58`/`+0xa0`
(lu, pas suppose). Porte en `UnitComponent.times_healed_this_turn`, reset dans `turnflow.py` a sa
place exacte dans la sequence (juste apres le roulement `+0x70 = +0x6c`), publie au dict DSL sous
`timesHealedThisTurn` — **dans `_LIVE_KEYS`**, parce que l'increment natif PRECEDE l'emission du
vecteur : fige au seed, le gate `== 1` lirait 0 et ne matcherait JAMAIS.

**(b) le vecteur `On(0x2c)`.** `HealUnitOperation$$Execute` finit par TROIS appels au slot 0x51
(`OperationProcessor$$EvaluateAbilities(actor, caster, target, trigger, ability)`, surcharge a 5
arguments — slot 81 lu dans `metadata/ioperationprocessor_slots.tsv`) :

    processor.<slot 0x51>(healed, healed, healed, 0x1e, null)
    processor.<slot 0x51>(caster, caster, healed, 0x2b UnitHealed,   abilityOrEffect)
    if (removeEffects) processor.<slot 0x51>(caster, caster, healed, 0x2c, abilityOrEffect)

⚠ **Le gate du troisieme est `removeEffects`, pas `abilityOrEffect`** : les noms Ghidra sont decales
d'un cran sur cette fonction (retour `OperationResult` par pointeur sret), decalage deja documente en
tete de `runner/operations/heal.py` — donc etabli par DEUX lectures independantes. Consequence qui
DISCRIMINE : `HealBehaviourOptions$$ForHeal` pose `removeEffects = 1` (le soin ordinaire declenche la
relique) tandis que `$$ForRegenerate` pose `0` (une REGENERATION ne la declenche pas).

Le triplet `(caster, caster, healed)` donne son sens au `get_OwnerIsTarget` : le porteur doit etre
l'unite QUI RECOIT le soin, jamais celle qui le donne.

Seul `On(0x2c)` est emis : `On(0x1e)` et `On(0x2b)` n'ont pas de consommateur porte (le bras
`On(UnitHealed)` du trait `Swarm` passe par le raccourci direct `on_group_unit_hp_changed`, qui n'est
pas un trigger de registre) — les ajouter serait un vecteur mort. Meme forme que #964-r1 cote
reparation.

## 4. Confrontabilite — ETAT 3 des trois

`spaceWolfPriest` est **hors du seed BC** (aucun `Id` `spaceWolf*` dans `data/seed-bc.json`) : il faut
l'injection catalogue PUIS le montage relique. **MESURE** (`probe_1037_wyrdmakers_helm_live.py`,
fixture `monter_porteur`) — `write_relic_seed_bc` fait les deux temps, et le seed produit porte bien
`('spaceWolfPriest', 1504, 1)` avec la config presente dans `BC.Abilities.PassiveAbilities`. Le
porteur est donc CONFRONTABLE.

⚠ **`equip_relic` rend un RAPPORT, pas la BC.** S'en servir comme valeur de retour ECRASE le seed par
le rapport — le montage sort alors `KO` sans erreur (faute commise a l'ecriture du probe, et c'est
exactement la forme de panne silencieuse que #237 decrit). Passer par `write_relic_seed_bc`.

## 5. Validation

* **27 tests offline** (`tests/engine/runner/test_1037_wyrdmakers_helm_offline.py`), fixture nommee
  `montage`. Les QUATRE gates du `CreateTrigger` ont chacun leur **contre-epreuve** (allie lointain,
  ennemi adjacent a la MEME position que l'allie du cas nominal, second soin du tour, compteur a
  zero, hors tour, porteur mort) : un port qui perdrait tous les gates resterait vert sur un unique
  cas nominal.
* **13 mutants sur 13 sont VUS** (`probe_1037_wyrdmakers_helm_mutants.py`, mutation dans une COPIE de
  l'arbre) : registre retire, `0x2b` au lieu de `0x2c`, chacun des trois gates supprime, egalite
  devenue `>= 1`, stat-mod sur DEFENSE, gate final sur la CIBLE, `RemoveEffect` supprime, increment
  supprime, reset supprime, gate `removeEffects` supprime, compteur retire de `_LIVE_KEYS`.
* **Le niveau SEPARE** : `extraDmg` a 10 paliers (490 -> 728, +48,6 %). Le test mesure les DEUX
  bornes — un port qui lirait toujours le dernier palier (la faute mesuree de #1006 sur
  `Maugetar`/`PhoenixGem`) serait vert au niveau 10 et faux au niveau 1.
* **Un temoin nul a ete trouve et repare** : le montage offline sans `board` faisait rendre `None` a
  `_add_effect_target_id((col,row))`, donc la glace n'etait JAMAIS posee — le test mesurait son
  propre echafaudage. La fixture pose desormais un plateau.

## 6. Ce que ce cas n'etablit PAS

* **Le vecteur COMPORTEMENTAL n'est pas confronte live.** Le montage du porteur, lui, EST mesure
  (SS4) ; ce qui reste a jouer est la bataille : soigner Baldr ou un allie adjacent pendant son tour
  et observer l'attaque non commandee, la glace sur l'hex, et le `+extraDmg` dans le degat. Residu
  `#1037-r2`.
* **`On(0x1e)` et `On(0x2b)` restent non emis** (aucun consommateur porte) — nommes dans
  `operations/heal.py`.
* **L'increment du compteur est un SOUS-ENSEMBLE strict du natif** : le natif incremente aussi quand
  `healed < 1` mais que la cible etait BLESSEE, qu'un effet negatif a ete purge, ou que le caster
  porte le flag `0x17 CanHealFullHealthUnits` ; le port sort plus haut sur `healed <= 0` (aucun des
  trois n'est modelise). Jamais de sur-comptage, seulement un sous-comptage sur ces trois regimes.
  Residu `#1037-r1`.
* **`ignoreForcedTargets: false`** (3e argument de `First`) n'est pas modelise par le noeud du port,
  qui prend un `index`. Pour `amount = 1` / `index = 0` les deux rendent le meme singleton.
* **Le 2e argument de `Cache` (`matchAbilityEntities: true`)** selectionne le mode de memoisation
  keye par contexte ; le port n'a que le slot unique — EXACT ici (arbre rebati par declenchement,
  deux consommateurs sous le meme contexte top-level), pas en general.
