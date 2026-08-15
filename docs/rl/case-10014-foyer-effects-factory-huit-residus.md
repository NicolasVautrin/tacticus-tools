# #10014 — le foyer `effects/factory.py`, troisième passe : deux fois la même faute, et un canal qu'on cherchait dans le mauvais fichier

Tranche du 2026-08-15, build `t6dpr4k06g`. Huit résidus, dont plusieurs déjà travaillés la nuit
précédente (#1102 / #1109) — d'où l'exigence de re-mesurer chaque prémisse plutôt que de recopier
sa fiche.

| résidu | prémisse re-mesurée | verdict | `BLOCAGE` avant → après |
|---|---|---|---|
| `#1008-r4` | **CONFIRMÉE**, et l'énoncé qui la bloquait était FAUX | **PORTÉ** — ligne fermée | `aucun` → *(fermé)* |
| `#963-r5` | **CONFIRMÉE** | **PORTÉ + gardé** — ligne fermée | `etage` → *(fermé)* |
| `#952-r2` | **RÉFUTÉE à moitié, l'autre moitié précisée** | **volet AJOUT LIVRÉ** — ligne fermée | `aucun` → *(fermé)* |
| `#1020-r5` | CONFIRMÉE, mais le blocage désignait le mauvais fichier | non résolu, blocage re-qualifié | `etage` → `etage` |
| `#922-r1` | volet (b) **PÉRIMÉ** (livré par #1109) | non résolu — (a) et (c) restent | `aucun` → `aucun` |
| `#924-r1` | **CONFIRMÉE**, un énoncé de la fiche périmé | non résolu (dépend de #924-r2) | `aucun` → `aucun` |
| `#965-r2` | **CONFIRMÉE** terme à terme | non résolu | `etage` → `etage` |
| `#894-r2` | **CONFIRMÉE** | non résolu — NON CONFRONTÉ | `seeding` → `seeding` |

Cinq prémisses tiennent, une est périmée, une est à moitié fausse, une est vraie sur le fond mais
accuse le mauvais foyer. **Le taux annoncé (« fausses une fois sur deux ») ne se vérifie toujours
pas sur ce foyer** — mais deux des trois fiches déjà « traitées » portaient encore un énoncé faux,
et c'est ce que la re-mesure attrape.

## 1. La MÊME faute, deux fois, sur deux résidus indépendants : une CONVENTION à la place d'un LITTÉRAL

C'est le fait de la tranche, et il n'était visible qu'en mettant les deux côte à côte.

**`#952-r2` — dériver l'ability accordée du NOM du passif.** `ai/state_bridge.py::_granted_abilities`
résout `Heal_<Passif>` dans l'enum. Mesuré contre les trois littéraux natifs :

| passif | littéral natif | convention `Heal_<P>` | |
|---|---|---|---|
| `TwistedScience` | `0x48f` = `Heal_TwistedScience` | `Heal_TwistedScience` | **1167 trouvé** |
| `HealingBalms` | `0x4bc` = `HealingBalms_Heal` | `Heal_HealingBalms` | `None` — **raté** |
| `GalvanicField` | `0x45f` = `Repair_GalvanicField` | `Heal_GalvanicField` | `None` — **raté** |

Un sur trois passe, **et c'est par accident** : son enum est nommé dans ce sens-là. C'est ce tiers
qui rendait le trou invisible. Effet chiffré : `entity_active_ability_ids` rendait `[1117]` pour
`admecManipulus` là où le natif rend `[1117, 1119]`.

**`#1020-r5` — reconnaître une famille d'effets par le SUFFIXE de son nom.**
`engine/battle_query.py::can_use_ability` filtre `str(e["name"]).endswith("_CantUseAbility")`, en se
déclarant explicitement « proxy offline du check par CLASSE d'effet (couvre les 2 membres connus et
**tout futur membre de la famille**) ». Le 3ᵉ membre s'appelle `RapidFire_BlockAbilities` : il ne
porte pas le suffixe.

Dans les deux cas la dégradation est **muette et permissive**, et dans les deux cas le CLAUDE.md
l'énonce déjà mot pour mot : *la VOIE ne dit pas l'enum — seul le NOM écrit au site tranche*. Ici,
ce nom est le **littéral du décompilé**.

## 2. `#1008-r4` — le bloc `methodPointers` en portait CINQ, et l'énoncé qui bloquait le port était écrit ailleurs

`runner/abilities/astartes.py` affirmait, en toutes lettres, que l'effet `1549` est « NUMÉRIQUEMENT
INERTE » et que sa classe « n'a que DEUX méthodes (`frida/methods.tsv`) ». La seconde moitié est le
piège que le CLAUDE.md documente — `methods.tsv` est indexée par ADRESSE et IL2CPP déduplique par
ICF. Le bloc du PE, borné par `list_xrefs` sur les deux corps nommés puis par lecture des pointeurs
voisins (l'entrée suivante bascule sur `StructuralAnalyserAdjacentEffect$$.ctor`), en porte **cinq** :

```
+0x00  StrikeFromTheShadowsEffect$$.ctor
+0x08  ICF WisdomOfTheAncients_DamageReductionEffect$$CreateActiveCondition = <DSLTriggers+0x70>  (YesTrigger)
+0x10  ICF WhisperingWebEffect$$CreateTargetSelector            = <DSLSelectors+0x30>  (Owner)
+0x18  StrikeFromTheShadowsEffect$$CreateEffectDamageMalusForDefense
+0x20  ICF WayOfTheShortBladeEffect$$IgnoreArmor  = ConfigVar(armorIgnored 0x40, GetAbilityState(this), config@+0x60)
+0x28  StructuralAnalyserAdjacentEffect$$.ctor      <- bloc SUIVANT (borne)
```

La **première** moitié de l'énoncé, elle, était une lecture EXACTE : les six slots de magnitude de
l'`EffectBonus` valent bien zéro. C'est la **conclusion** qui ne suivait pas —
`BaseEffect$$DamageMalusForDefense` évalue AUSSI `this.<vtable +0x718>()` dans le bloc gaté par le
trigger. Un `EffectBonus` à magnitude nulle est précisément ce que ce canal attend : le natif SÉPARE
la condition et la magnitude, le slot les recombine (mécanisme lu par #1008-r2 sur `Helspear`).

**La gate n'est pas celle de son voisin, et c'est mesuré** :

```
Helspear_IgnoreArmor (1583) :  get_OwnerIsTarget & IsUnit(Caster@<DSLSelectors+0x48>)
StrikeFromTheShadows (1549) :  IsRangedAttack()  & get_OwnerIsTarget
```

**Deuxième écriture, non annoncée par la fiche** : le call-site `AddEffect` n'armait pas
`scale_from_source` (le 2ᵉ argument natif `abilityState = get_AbilityStateReference(this)`). L'écart
est silencieux et large — `armorIgnored` a **65 paliers pleins** : index 0 rend **6**, un runner
normalisé (`level 50`, mult 180) rend **599**.

⚠ Cette mesure a elle-même failli entrer FAUSSE dans le module : un `print` de diagnostic tronquait
la table à `[:6]`, et le commentaire écrit sur cette base annonçait « SIX paliers ». Corrigé avant
commit — un artefact d'affichage vaut une fausse lecture du décompilé.

## 3. `#963-r5` — les deux objections avaient la MÊME cause, donc écrire le lien ne les contourne pas

La fiche refusait l'inscription, à raison, avec deux conséquences chiffrées : l'instance sans lien
(1) satisfait le gate `NOT HasEffect(Owner, 0x424)` et **bloque la pose correcte** ; (2) rend
`BOND_REMOVAL_GATES[1060]` muet, puisque son gate (a) lit `BaseEffect.bonded`. Les deux ont la même
cause. Écrire le lien **retire ce sur quoi le refus portait**.

Arbre lu verbatim :

```
LifewardsAddEffectAbility$$CreateBehaviour =
    If( NOT HasEffect(Owner@<DSLSelectors+0x30>, 0x424 = 1060, onlyActive: 0, effectTarget: 6),
        AddBondEffect( 0x424, get_AbilityStateReference(this),
                       source       = Owner@<DSLSelectors+0x30>,
                       targets      = Owner@<DSLSelectors+0x30>,
                       bondedEntity = Parent(Owner@<DSLSelectors+0x30>, root: 0),
                       options      = <ZÉROÉES> ) )
```

**La dégradation est LUE, pas devinée.** `AddEffectBehaviour$$GetEffectBuilder`, dans ses deux
surcharges : `method = (bondedEntityId != 0) ? <builder de BOND> : <builder ORDINAIRE>`. Un
`bondedEntity` non résolu ne fait donc **pas** échouer la pose — refuser de poser serait RESTRICTIF,
écrire `0` mentirait (l'entité 0 existe). Le port pose avec `bonded = None`.

Livré : `ABILITY_INIT_OWNER_BOND_EFFECTS`, **troisième** canal d'init (après les owner-effects
ordinaires et les flags), portant une donnée de plus — le **sélecteur** du 5ᵉ argument, écrit en
toutes lettres et résolu par le foyer déjà porté du nœud (`components.parent_of`).

## 4. Ce que la re-mesure a trouvé de PÉRIMÉ dans les fiches

- **`#922-r1` volet (b)** : les trois entrées `ABILITY_INIT_OWNER_EFFECTS` sont **posées** (livrées
  par #1109), et `_charge_regime.py` porte déjà son paramètre `inactifs`. Le paragraphe est périmé ;
  restent (a) la décomposition de l'écart `[462, 1600, 988]` et (c) le rayon du harnais.
- **`#924-r1`** : la phrase « `damage_ops/normal.py` ne threade `trigger_ability_type` que vers
  `build_hits_board`, jamais vers `attacker_modifiers` » est **fausse sur le code courant** —
  `trigger_ability_type` est un paramètre déclaré d'`attacker_modifiers`. Cohérent avec la MAJ #1084
  qui réfutait déjà l'attribution `etage`, mais en contradiction avec le paragraphe qui la précède
  dans la même ligne de backlog.
- **`#952-r2`** : « `RemoveActiveAbility` n'a aucun canal d'init » — **faux**,
  `PASSIVE_REMOVES_ACTIVE_ABILITY` existe depuis #1015-r1.
- **`#1020-r5`** : « `IsAbilityBlocked` n'a aucun pendant porté, cf. `runner/operations/turnflow.py` ».
  Vrai pour `turnflow.py`, **mais l'axe ABILITY n'y a jamais vécu** : il est dans
  `engine/battle_query.py::can_use_ability`, porté et consommé au point de couture `ai/context.py`.
  La fiche cherchait au mauvais endroit — d'où un blocage `etage` qui désignait un étage inexistant.

## 5. Le RE de `#1020-r5`, livré même sans le port

Le substrat de blocage est lu terme à terme, ce qui rend la prochaine tranche mécanique :

```
UpdateActiveAbilityBlockerOperation$$AddBlocker(caster, target, effect, incNormal, incMachinePrimary) :
    blockerId = caster.OwnerComponent.CurrentPlayerEntityId        # $$GetBlockerId
    target.ActiveAbilityComponent.<+0x18 blockers>.Add(
        key   = effect.Id,
        value = { blockerId, effectId, incNormal @+8, incMachinePrimary @+9 } )
    SendUpdateAction(target, effect)

UnitExtensions$$IsAbilityBlocked(unit, abilityType) :
    si kind(unit) n'est ni Unit(1) ni Machine(6)                    -> false
    si ActiveAbility.IsRegularAttack(abilityType)                   -> NormalAttackIsBlocked()
    si kind == Machine && abilityType == comp.<+0x30>               -> MachinePrimaryAbilityIsBlocked()
    sinon                                                           -> ActiveAbilitiesAreBlocked()

    ActiveAbilitiesAreBlocked()        = blockers.Count > 0     (INCONDITIONNEL)
    NormalAttackIsBlocked()            = any(v[+8])
    MachinePrimaryAbilityIsBlocked()   = any(v[+9])

BlockActiveAbilityEffect$$ApplyInternal / $$RevertInternal = le même slot 0x73, add=1 / add=0,
    avec `this+0x480` (includeNormalAttack) et `this+0x481` (includeMachinePrimaryAbility).
```

**Le seul verrou restant est un APPARIEMENT** : `BlockActiveAbilityEffect$$.ctor` a exactement trois
appelants de code, tous des lambdas **anonymes** de `EffectsDatabase$$InitializeEffects`, aux mêmes
littéraux `(1, 0, 1)`. Deux membres se nomment par leur suffixe ; le troisième ne peut pas être
nommé depuis les xrefs. `1137` est le seul candidat plausible — **et un candidat plausible n'est pas
une lecture**. Résidu d'outillage : **#1020-r7**.

## 6. Validation adversariale

| tranche | étages | mutations | verdict |
|---|---|---|---|
| `#963-r5` | 9 | 8 | **8 MORD, 0 MUET** (1ʳᵉ passe : 7 MORD / 1 MUET) |
| `#952-r2` | 10 | 6 | **6 MORD, 0 MUET** |

⚠ **Le MUET de la première passe est le résultat le plus utile.** Remplacer le test
`selector == BOND_PARENT_OF_OWNER` par `if True:` laissait la garde **verte**, parce que le seul
sélecteur du registre EST `Parent(Owner)`. Un bond futur dont le `bondedEntity` serait un autre nœud
aurait alors reçu le PARENT en silence — **un lien FAUX, pire que pas de lien**. L'étage 9 injecte
un sélecteur non déclaré et exige la dégradation native.

Parmi les six mutations de `#952-r2`, l'une est « dériver par la convention `Heal_<P>` au lieu du
littéral » : c'est exactement la faute que le registre existe pour empêcher, et elle mord.

## Ce qui n'est PAS couvert

- **Aucune confrontation LIVE.** Les trois ports sont validés offline et par mutation ; aucun bras
  live n'a été monté. Pour `#1008-r4` le montage est écrit et immédiat — `astarCyrus` est HORS du
  pool spawnable (noté par le port lui-même), donc il passe par l'injection catalogue ; le régime
  séparant est une attaque **à distance** contre une cible marquée, sur une cible dont l'armure est
  non nulle (sinon `max(armure − pén, 0)` sature et le témoin est dégénéré).
- **`#924-r1`, `#965-r2`, `#894-r2`, `#922-r1` (a) et (c)** : non résolus, prémisses re-mesurées et
  blocages inchangés. `#894-r2` reste **NON CONFRONTÉ** — le blocage `seeding` (l'empreinte 3 tuiles
  que `--explicit-stats` ne donne pas à `GuildBoss10Boss1AdmecBelisarius`) n'a pas été retravaillé.
- **`#1020-r5`** : RE livré, port refusé faute d'appariement prouvé — et même établi,
  l'élargissement du critère resterait INERTE tant que rien ne pose `1137`, donc le trigger
  `RapidFire` doit entrer dans le même commit.
- **`#952-r7`** (`state_bridge._granted_abilities` doit déléguer au registre littéral) : le fichier
  était tenu par un autre agent, d'où l'abstention plutôt qu'un fork de la table.
- **Une baseline rencontrée, indépendante de cette tranche** :
  `tests/engine/test_909_decision_actives_offline.py` rend 8 erreurs de MONTAGE, parce que
  `data/symbols/t6dpr4k06g/metadata/active_playbook_builders.tsv` n'existe pas (régénération exigeant
  le binaire).
