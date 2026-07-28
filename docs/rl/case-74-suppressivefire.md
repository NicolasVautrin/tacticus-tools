# Case #74 — trait `SuppressiveFire` (1010) : pose Pinned/« Suppressed » on-hit ranged

**Status : PORTE + VALIDE LIVE (Pinned pose live==offline sur attaque ranged ; 2 discriminants
live+offline : melee->rien, non-porteur->rien), RE COMPLETE (decompile-citee, build gqfc5mff6c).
Zero-regression (agreement stages seed 31337 : PREDICTION 6/6, UTILITE 6/6, ability 8/8, move 13/13
= byte-inert, roster sans carrier ; par construction `collect_triggered_abilities` inchange hors
carrier).**

## Ce que c'est (i2)
Trait `UnitTrait.SuppressiveFire` (id 1010, x49 unites dont 8 lineup) : « An enemy hit by this unit's
ranged attack becomes Suppressed. » -> a chaque attaque a DISTANCE du porteur, la cible recoit l'effet
`Pinned` (0x429=1065, UI « Suppressed »).

Le trait ACCORDE une ability triggered `SuppressiveFireAbility` (triggered id 1044,
triggered-ability-names.ts:175) — l'artefact natif est un ARBRE DSL (doctrine #149), pas un helper
imperatif ; le port est une feuille DSL (AddEffect) + gate collapses au-dessus, l'effet Pinned
impuratif en-dessous (deja porte).

## RE native (decompile-citee, build gqfc5mff6c)

### Symboles
| Symbole | VA | Role |
|---|---|---|
| `SuppressiveFireAbility$$CreateTrigger`   | `0x181225d00` | conditions (arbre DSL) |
| `SuppressiveFireAbility$$CreateBehaviour` | `0x181225c50` | pose de l'effet (feuille E) |
| `PinnedEffect$$ApplyInternal`             | `0x180f5e6d0` | effet 1065 (deja porte, status.py) |
| `DSLFactory$$Units` (`UnitsOnTilesSelector`) | `0x180e01340` | selecteur cible |

Ids : trait `SuppressiveFire` **1010** ; triggered ability **1044** ; EffectType `Pinned`
**0x429=1065** (effect-type-names.ts:189).

### Le trigger (@181225d00) — arbre DSL, conjonction `op_BitwiseAnd`
```
On(PreAttack=5) & IsRangedAttack & get_OwnerIsActor
  & AreEnemies(owner@0x148, target@0x178)
  & AmountIsGreaterThanZero(Units(target@0x178, kind=2))
```
= « quand le porteur (actor) fait une attaque a DISTANCE contre un ennemi avec >=1 cible valide ».
`IsRangedAttack` (`DSLFactory.IsRangedAttack @180df4d90`) est **POSITION-based** (caster non-adjacent =
ranged), PAS le type d'arme -> une unite a arme ranged qui frappe au CONTACT ne suppress PAS.

### Le behaviour (@181225c50) — feuille E UNIQUE
```
AddEffect(0x429=Pinned, source=AbilityStateReference(=owner), cible=Units(target@0x178, kind=0),
          dureeNode=struct ZERO -> DefaultAmountOfRounds(0x429)=1)
```
`Units` = `UnitsOnTilesSelector` (unites sur les tuiles de la cible ; positions exclusives -> la cible
elle-meme) -> pose Pinned sur l'UNITE cible, source=le porteur, duree DEFAUT (1 round).

### L'effet Pinned (0x429=1065) — DEJA porte, non re-porte
`PinnedEffect` (`entities/effects/loki/status.py`, valide live) : `ChangeStat(4=Movement,
-EffectConfig(1)=PinnedMovementReduction)` (la cible ne peut plus avancer) + malus degat ATTAQUANT du
porteur x0.70 (`ForPercentIncrease(OwnerIsCaster, -EffectConfig(0)=PinnedDmgReductionPct=30)`).
ActiveCondition `Not(HasTrait(0x40f=1039=TerminatorArmour))` -> sur un Terminator l'effet est POSE
puis INERTE (il n'est PAS refuse : mesure #208, `decisionView { includeInactive: true }` le publie
avec `active: false`). C'est `RefreshEffectsOperation$$ShouldBeActive` qui evalue cette condition et
ecrit `EffectComponent.IsActive @+0x5c` ; cf. `case-224-effect-immunity-gate.md` §4/§4bis. Le
discriminant (4) de `test_suppressive_fire_live.py` verrouille les deux canaux sur ce vecteur.

## Port (mirror 1:1)
`engine/runner/operations/triggers/loki/suppressive_fire.py::SuppressiveFireAddEffectAbility`
(feuille `suppressive_fire_tree()` = `AddEffect(Pinned=1065, Target(), duration=None)`),
enregistre `TRAIT_TRIGGERS["SuppressiveFire"] = [SuppressiveFireAddEffectAbility]` (dispatch.py),
export `triggers/loki/__init__.py`.

- `matches` (predicats COLLAPSES imperativement, doctrine #149) : OwnerIsActor (`ev.actor_id ==
  owner`) + AreEnemies (teams differentes) + cible presente + **IsRangedAttack POSITION-based**
  (`_is_ranged_position`, PAS `ev.ranged` qui en voie normale est weapon-selection-based).
- `execute_behaviour` : arbre DSL AddEffect -> `AddEffectOperation` (feuille DSL au-dessus, effet
  Pinned impuratif en-dessous).

### DISPATCH (vecteur) : `On(NormalAttack=38)` (choix documente)
Le natif ecoute `On(PreAttack=5)` (emis AVANT le degat, UNE fois par attaque, cible primaire). Le port
n'emet pas de vecteur PreAttack -> route sur `On(NormalAttack=38)` (`after_hit_normal_attack`, emis UNE
fois par attaque NORMALE, cible primaire, y compris pour un tir Blast dont le splash est en
sous-operation SANS NormalAttack). **OBSERVABLE IDENTIQUE** : Suppressed pose sur la cible primaire
d'une attaque ranged, independamment du timing avant/apres degat (Pinned n'affecte PAS le degat
ENTRANT ; il ne borne que le mouvement + le degat FUTUR du porteur suppresse).

## Validation live ADVERSARIALE
`tests/engine/runner/test_suppressive_fire_live.py` (carrier=tauDarkstrider Pulse r2, cible=astraYarrick
Resilient durable non-Terminator, board MC1_67, `--hp-target 200000`) :

| Cas | Position | live | offline | verdict |
|---|---|---|---|---|
| RANGED (porteur, trait ON) | d=2 (non-adjacent) | Pinned rem=1 sur cible | Pinned rem_turns=1, source=carrier | **agreement present==present** |
| MELEE (porteur, position OFF) | d=1 (adjacent) | AUCUN Pinned | AUCUN Pinned | discriminant POSITION (IsRangedAttack=False) |
| NON-CARRIER (trait OFF) | d=2 | (offline) | non-porteur -> AUCUN Pinned ; controle positif porteur meme geometrie -> Pinned | discriminant TRAIT/registre |

3/3 pass. Le port materialise Pinned (source=owner, duree 1) exactement quand le natif le fait (attaque
ranged d'un porteur), et JAMAIS sinon (melee de position, ou attaquant sans le trait).

## Residus (honnetes, documentes dans le module)
- **Attaques d'ABILITY ranged** : le natif `On(PreAttack=5)` est GENERIQUE (normale ET ability) ; le port
  ne cable que `On(NormalAttack=38)`. Un carrier qui suppress via une ATTAQUE-ABILITY ranged n'est pas
  couvert -> extensible en ajoutant `Attack(9)` a `event_ids`, MAIS `Attack(9)` fire PAR-CIBLE (splash)
  alors que le natif suppress la cible PRIMAIRE seule (PreAttack once) => sur-suppression des victimes de
  splash. NormalAttack(38) evite ce piege ET couvre 100% des 8 carriers (attaque normale ranged).
- **Cible tuee par l'attaque** : le port fire APRES le degat (vecteur after-hit) vs natif AVANT
  (PreAttack) — Pinned pose meme sur un cadavre (== convention LordOfTempests AddIce), no-op observable.
- **Reduction de Movement de Pinned** : NON portee dans le chemin de combat (residu pre-existant du
  `PinnedEffect`, §17.4 status.py — le mouvement n'est pas dans le pipeline degat porte). Le malus degat
  x0.70 du porteur suppresse, lui, EST porte+valide (probe_57b).
