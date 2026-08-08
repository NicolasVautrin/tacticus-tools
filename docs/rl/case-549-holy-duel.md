# #549 — `HolyDuel` (1050) : le duel SYMETRIQUE, et l'etage qui manquait sous lui

`templChampion` « Brother Jaeger » (Black Templars, HERO, **au pool** rank 17). L'ability etait un
**no-op silencieux** : absente d'`ABILITY_CLASSES`, donc `AbilityHandler.visit_ActiveAbilityMessage`
l'ignorait — 0 degat, 0 effet, aucune erreur — alors que la face DECISION
(`playbook/noncomparable/holy_duel.py`) la choisissait deja.

## 1. La categorie annoncee etait FAUSSE, et c'est un resultat

`docs/rl/combat-ability-coverage.md` classait 1050 en **EFFECT/BUFF**. Lecture du decompile :
`IdunBattleLogic.Entities.Abilities.Active.Loki.HolyDuelAbility$$ExecuteBehaviour` **FRAPPE** — mais
par l'attaque **NORMALE** de l'unite, jamais par une attaque d'ability :

```
[1] AddBondEffect( 0x443 = 1091 HolyDuel_Taunt, AbilityStateReference,
                   source = Caster@DSLSelectors+0x48, targets = Target@0x60,
                   bondedEntity = Caster@0x48, options ZEROEES )
[2] UseActiveAbility( Caster@0x48, Target@0x60, UnitNormalAttackType(Caster@0x48), ... )
AActiveAbility.Execute( entities, this, op_BitwiseAnd([1], [2]) )
```

Le gameconfig le confirme : `abilities.HolyDuel` n'a **ni** `minDmg`/`maxDmg`, **ni** `nrOfHits`,
**ni** `damageProfile` — seulement `extraDmg` et `dmgReduction`, toutes deux
`variablesAffectedByRarityBonus`. Le `+582` de l'i2 n'est pas le degat du cast : c'est l'additif que
l'EFFET 1092 verse a chaque attaque du champion contre son duelliste. **Meme configuration que
`Drachnyen` (1029).** Categorie REELLE : **ATTAQUE NORMALE dispatchee + trois effets**.

## 2. Le duel est SYMETRIQUE — trois sous-effets sur quatre vivent sur l'entite BONDEE

`IdunBattle.Entities.Effects.Loki.HolyDuel_TauntEffect$$ApplyInternal(owner, target, effect)` :

```
ctx.<+0x20> = target                                      # le PORTEUR de 1091 = l'ennemi
ctx.<+0x18> = ABondEffect.BondedEntityId(this, effect)    # = le CHAMPION
bonded      = <entites>.GetEntity(ctx.<+0x18>)

AddSubEffectWithSameTurns(this, effect, target, EffectBuilder(ctx, b__0), 0x1b  = 27)
AddSubEffectWithSameTurns(this, effect, bonded, EffectBuilder(ctx, b__1), 0x1b  = 27)
AddSubEffectWithSameTurns(this, effect, bonded, EffectBuilder(ctx, b__2), 0x444 = 1092)
AddSubEffectWithSameTurns(this, effect, bonded, EffectBuilder(ctx, b__3), 0x445 = 1093)
```

Les quatre lambdas appellent toutes `AddEffectBehaviour$$DefaultBondEffectBuilder`, mais **`b__0`**
lui passe `ctx.<+0x18>` (le bonde du parent) et **`b__1`/`b__2`/`b__3`** lui passent
`ctx.<+0x20>.Id` (le porteur du parent). Le couple **(porteur, bonded) bascule ENSEMBLE**, jamais
separement — d'ou le champ UNIQUE `SubEffectSpec.on_bonded_entity`, qui ne peut pas decrire une
combinaison que le natif n'ecrit pas.

Trois foyers partages en decoulent, tous DERIVES des specs (jamais ecrits a la main) :

| foyer | avant | apres |
| --- | --- | --- |
| `AddEffectOperation._spawn_sub_effects` | enfant sur le porteur, bond herite | porteur/bond **croises** si `on_bonded_entity` ; **recursion** (un enfant COMPOSITE spawne les siens et ecrit ses cibles forcees) ; **etat d'ability du parent propage** |
| `remove_effects._remove_sub_effects` | balaye la liste du SEUL porteur | balaye aussi l'entite bondee des qu'une spec la designe |
| `snapshot._load_effect_parent_links` | apparie dans la liste du porteur | apparie dans la liste du porteur DESIGNE PAR LA SPEC |

**Ces trois changements sont INERTES pour les composites anterieurs** (`Stunned` → 1165/1166/1167,
`Taunted` → 25/26/1237) : leurs enfants n'ont ni sous-effets, ni ecriture de cibles forcees, ni
magnitude indexee sur un `AbilityState`. Verifie par re-jeu (`test_taunt_targeting_live`,
`test_damage_crushingclaws_live`).

## 3. L'ETAGE QUI MANQUAIT — `tgt_id` n'etait pas threade, et le port sous-estimait de 40 %

MESURE INTERMEDIAIRE, celle qui a tranche : **effets bit-identiques des deux cotes**, et pourtant
**natif 6140, port 3678** sur le degat du cast. Aucun scalaire n'a ete fitte ; la decomposition par
etage a montre l'accumulateur ATTAQUANT du port :

```
details = [PercentIncrease 25]            <- RapidAssault seul, AUCUN `Addition`
```

Cause : `IdunBattle.Entities.Effects.Loki.HolyDuel_ExtraDmgEffect$$CreateEffectDamageBonusForAttack`
porte le gate `AreEqual(Target@DSLSelectors+0x60, BondedEntityFromEffect(Effect@0x38))` — une
egalite d'**IDENTITE** — et l'`att_ctx` du canal SELF ne portait **pas** `tgt_id`. Il portait deja ce
MEME noeud sous **trois** autres lectures (`t_pos`, `tgt_team`, `tgt_hp`) : il lui manquait l'id.
Threade dans les DEUX faces pour ne pas ouvrir de fork (`damage_model.attacker_modifiers`,
`prediction/normal_attack.py`, `prediction/abilities.py`), avec la meme cle et la meme semantique que
le canal AURA et que l'axe COUPS. Apres : **6140 = 6140, bit-exact**, `additive = 886` =
`extraDmg[50] = 443` x multiplicateur de rarete `200 %`.

⚠ **Aucun effet existant ne lit `tgt_id` dans CET `att_ctx`** (les lecteurs de cette cle vivent tous
dans les ctx AURA / COUPS, qui sont d'autres dicts) : l'ajout ne peut rien changer d'autre.

## 4. La fin du duel — trigger (c) `get_Adjacent`, qui n'avait jamais pu etre porte

`HolyDuel_TauntEffect` est la **SEULE** classe de la famille `ABondEffect` a armer
`<klass+0x738> get_Adjacent`. Mesure `probe_462_r4b_r1_r1_r1_r1_bond_removal.py --step declared`
(2026-08-08) : `get_Range` = **none**, `get_Adjacent` = **true**, `get_RemoveOnBondedEntityDeath` =
**true**.

Le trigger etait volontairement **hors du port** : 1091 n'etait pose par personne, donc l'inscrire
aurait ete « vacuement vrai ». `bond_removal.py` §5 et deux tests portaient cet invariant
CONDITIONNEL et annoncaient qu'ils rougiraient le jour ou 1050 entrerait au registre. **C'est ce qui
est arrive** : les deux ont ete retournes (l'invariant devient « tout effet a `adjacent=True` DOIT
etre cable, et il doit y en avoir au moins un »).

⚠ **(c) n'est PAS (b) a un seuil pres.** `IsInRange` compare une distance hex ; `IsAdjacent` delegue
a `BattleQuery$$AreEntitiesAdjacent` → `MovementUtil$$AreTilesAdjacent`, qui porte une **porte
d'elevation** (`|dElev| < 2`), un **court-circuit d'identite** et compare les **empreintes
completes** (`GetTiles`). Le port passe par le foyer unique
`services/battle_query.py::are_entities_adjacent`, le meme que le noeud DSL `IsAdjacent`.

Et c'est ce trigger — pas une duree — qui rend l'i2 exact :
`StaticBattleRules.Effect$$DefaultAmountOfRounds(0x443)` rend **null** (relu au decompile : `1091`
sort par la branche `return 0` du switch), donc 1091 est **PERMANENT**. « the taunt does not expire
with rounds passed. »

## 5. Le masque de ciblage — forme PRESET + FLAGS

`HolyDuelAbility$$.ctor` recopie les 0x40 octets du preset statique `TargetingOptions statics+0x40`
puis appelle la surcharge **PRESET + FLAGS** `TargetingOptions$$.ctor(&opts, &preset, 0x200000000)`,
enfin `AActiveAbility$$.ctor(this, &opts, 0)`.
`TargetingOptions$$.cctor` ecrit pour ce preset `Rules = 0x4000` a `<preset>+0x28`, donc masque
EFFECTIF = `0x200000000 | 0x4000` = **`TargetIsNotAnObject | TargetIsEnemy`**, `onlyAdjacent`,
`forceMeleeTarget = RangedBool.False`. Le `0x4000` vient du PRESET, pas du litteral visible.
**MIGRE** du dict `targeting.py` vers `HolyDuelAbility.TARGETING_OPTIONS` (contrat de disjonction),
et `ABILITY_ATTACK_TYPE[1050] = DirectTargetAttack` pose dans le meme commit — litteral `0`
TRANSCRIT, bien que l'arbre n'attaque pas « en direct ».

## 6. Ce qui est CONFRONTE, et ce qui ne l'est pas

**Face COMBAT — confrontee** (`probe_549_holy_duel.py`, `tests/engine/runner/test_549_holy_duel_live.py`,
`tests/engine/runner/test_462_r4b_r1_r1_r1_r1_b_bond_range_live.py` bras C) :

* famille posee sur les DEUX porteurs, **identique** natif/port (cible `[25,26,27,1091,1237]`,
  champion `[25,26,27,1092,1093,1237]`) ;
* bonds **croises** et `ForcedAttackTargetsComponent` **croise** (`cible → [champion]`,
  `champion → [cible]`) ;
* degat du cast **bit-exact** (6140), avec l'`Addition` de 1092 NOMMEE dans l'accumulateur, et un
  **controle** : le meme accumulateur contre une TIERCE unite ne porte AUCUN additif ;
* rupture d'adjacence : deux bras geometriques (le meme push a une tuile pres), natif ET port
  concordants, et la cascade vide **les deux** duellistes.

**NON confronte** :

* **la face DECISION**. Elle preexiste (`HolyDuelPlaybook`) et n'a pas ete modifiee ; en revanche le
  `tgt_id` que j'ai threade cote PREDICTION n'a **pas** ete confronte a `aiPlaybookPredict`
  (residu **#549-r1**). Degradation avant le threading : RESTRICTIVE (la prediction ignorait le
  `+extraDmg` et le `-dmgReduction` du duel).
* **le `-dmgReduction` (1093) en situation** : le montage ne fait pas frapper le duelliste. Le gate
  et la magnitude sont mirrores et lus, la contribution n'est pas mesuree contre le natif
  (residu **#549-r1**).
* **le gate (a) sur 1091** (`get_RemoveOnBondedEntityDeath = true`) : MESURE au natif, cable par
  derivation de la table, **pas** confronte live sur cet effet-la (il l'est sur l'effet 27).
* **`EffectsState.on_turn_end`** ne cascade pas entre porteurs. Sans objet ici (1091 est permanent,
  ses enfants aussi par `SAME_TURNS`), donc laisse tel quel plutot qu'etendu a l'aveugle.

## Residus

* **#549-r1** — confronter la face DECISION du duel : `aiPlaybookPredict` sur le champion pendant un
  duel actif doit porter le `+extraDmg` (1092) et le `-dmgReduction` (1093). Inclut le volet COMBAT
  de 1093 (faire frapper le duelliste et mesurer la reduction).
