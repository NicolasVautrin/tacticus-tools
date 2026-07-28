# case-209 — la charge utile de `HazeOfCorruption` : le report de dégât sur le relais

**Critère (binaire)** : quand la cible d'un `deathBlightlord` MEURT sous le coup, quel dégât exact le
relais (l'unité liée par le bond `0x435 = 1077` posé par le target-finder de #207) encaisse-t-il, et
le port produit-il le même nombre ?

**Réponse** : le relais encaisse, coup par coup, la liste des `LeftOverDamage` que la cible a
gaspillées — **`demandé − appliqué`** pour le coup qui la tue, et **la BASE nominale entière** pour
tout coup qui tombe ensuite sur le cadavre, coup Toxic bonus compris. Port bit-exact **6/6 montages**
(2 seeds × 3 régimes de PV), montant PAR ENTRÉE et total.

| seed | PV | coups d'arme | entrées natives (= entrées port) | relais natif | relais port |
|---|---|---|---|---|---|
| 777 | 8000 | 2711, 2447, 2196 | — (la cible survit) | **0** | **0** |
| 777 | 6000 | 2711, 2447, 842 | 1354 `Power`, 1397 `Toxic` | **2751** | **2751** |
| 777 | 5000 | 2711, 2289, 0, 0 | 158, **2609** `Power`, 1397 `Toxic` | **4164** | **4164** |
| 88 | 8000 | 2323, 2922, 2371 | — | **0** | **0** |
| 88 | 6000 | 2323, 2922, 755 | 1616 `Power`, 1397 `Toxic` | **3013** | **3013** |
| 88 | 5000 | 2323, 2677, 0, 0 | 245, **2609** `Power`, 1397 `Toxic` | **4251** | **4251** |

---

## 1. Le discriminant : `2609` est une CONSTANTE, pas un jet

Les deux seeds ont des jets d'arme **différents** et rendent le **même 2609** au 2e transfert du
régime 5000. Or la cellule d'arme réduite est `(2087, 3131)` et `(2087 + 3131) / 2 = 2609` **exact**.

C'est ce qui réfute « le leftover est le jet du coup gaspillé » et établit le champ `+0x98` du
message de dégât comme la **base nominale** du coup. Le même invariant vaut pour le coup bonus
(`1397`, profil Toxic, identique sur les deux seeds).

## 2. Les trois artefacts natifs

### 2.1 `IdunBattle.Operations.ApplyDamageOperation$$AddLeftoverHit` — l'alimentation

Trois call-sites **distincts** dans `IdunBattle.Operations.ApplyDamageOperation$$Execute` (aucun
n'est un doublon de décompilation) ; le montant part dans `IdunBattle.Core.LeftOverDamage$$.ctor`
sous forme de `IdunBattle.Core.Damage` (`+0x00` = type, `+0x04` = montant), stockée à
`LeftOverDamage+0x6c` :

| site | condition | montant poussé | suite |
|---|---|---|---|
| A | `UnitExtensions.HasFlag(target, 8 = Overkilled)` | `Damage(type, msg[0x98])` — base nominale | flag littéral `1`, puis `return` (aucun dégât, aucun événement) |
| B | `HealthComponent.IsDead` évalué **avant** l'application | `Damage(type, msg[0x98])` — base nominale | pas de `return` |
| C | après application, `0 < appliqué` et `IsDead` évalué **après** | `Damage(type, demandé_santé − appliqué_santé)` — reste d'overkill | pas de `return` |

`msg` (`param_5`) = `+0x00` DamageType · `+0x04/+0x08/+0x0c` montants santé/armure/bouclier ·
`+0x98` base nominale. La struct `Damage` du site A/B est construite **avant** toute mutation et
n'est plus touchée ensuite (vérifié : aucune écriture entre le ctor et les call-sites).

### 2.2 `IdunBattleLogic.Entities.Abilities.Active.Loki.HazeCorruption_BonusHitAbility`

⚠ Orthographe native **sans le « Of »** — invisible à un grep `HazeOfCorruption`, c'est ce qui l'avait
fait manquer en #207.

```
CreateTrigger   = OnPreDeath(1, 0) & get_OwnerIsActor & IsDead(Target@0x178)
                  & NOT IsDead(Owner@0x148) & NOT TriggeringEffectIs(0x435)
CreateBehaviour = AttackDamage( Owner@0x148, Target@0x178,
                                Get(GetVariableForLevel(config, 8 = extraDmg)),
                                Direct(GetDamageProfile(config)),      # Toxic, DamageProfileType 24
                                Get(GetNumberConstant(config, 0x2f)),  # nrOfHits = 1
                                AbilityOrEffect(this.Id), <options> )
```

Le coup porte sur la **cible**, qui vient de tomber : il n'entame rien (`Amount 0` mesuré) et son
seul effet est la `LeftOverDamage` qu'il laisse. C'est l'implémentation native du « + 1x Toxic
Damage » de l'i2 : le jeu **tape le cadavre pour que le coup déborde**, il ne l'adresse pas au relais.

### 2.3 `IdunBattle.Entities.Effects.Loki.HazeOfCorruption_DamageTransferEffect` (0x435 = 1077)

`$$.ctor` = `ABondEffect..ctor(this, 1, 0, Nullable<AbilityOrEffect>(0x434 = 1076), 0)`.
`$$GetDamageSource` = `EffectSource(Effect@0x150)` (la cible initiale) ;
`ABondEffect$$BondedEntitySelector` = `BondedEntityFromEffect(Effect@0x150)` (le porteur).

```
$$CreateTargetTrigger
    ( OnDeath(1,1) & ( TriggeringAbilityIs(0x435) | AreEqual(Actor@0x158, bonded) )
      | On(0x2e = UnitRevived) | On(0x35 = UnitFled) )
    & IsAlive(bonded) & AreEqual(Target@0x178, EffectSource(Effect@0x150))

$$CreateTargetTriggerBehaviour
    dmgs = GetLeftOverDamages(entities)
    beh  = Nothing() + GetRemoveEffectBehaviour()
    foreach d in dmgs:
        beh += AttackDamage( bonded, Owner@0x148, Get(d.amount@+0x70),
                             Direct(Nullable<DamageType>(d.type@+0x6c)), One@0xc0,
                             AbilityOrEffect(0x435), <défaut> )
    return Attack(bonded, Owner@0x148, beh, <défaut>)
```

`IdunBattleLogic.Entities.DSLFactory$$Attack` → `IdunBattle.Entities.Behaviours.AttackBehaviour$$.ctor
(this, attacker@+0x50, target@+0x58, behaviour@+0x60, options)` : **l'attaquant est le bonded
(le porteur), la cible est le porteur de l'effet (le relais)**.

`$$GetLeftOverDamages` lit la liste sur le `Target` du contexte, et **retombe** sur la cible
INITIALE mémorisée par le `SetPersistentData` du target-finder quand elle est vide
(`GetPersistentData(AbilityOrEffect(0x434), bonded, <clé>)`).

## 3. Le port

* `engine/runner/operations/left_over_damage.py` (**nouveau**) — `LeftOverDamagesComponent` (mirror du
  champ `+0x90`) + `record_left_over_damages`, le re-jeu coup par coup des trois call-sites. Le natif
  appelle `ApplyDamageOperation` **par coup**, le port applique en un bloc au chokepoint
  `AttackDamageOperation._apply_damage_pipeline` et re-joue la séquence — **exactement le patron déjà
  utilisé par `_did_overkill` juste au-dessus**, même source (`hits_result`).
* `engine/runner/operations/damage_hits.py` — `_run_hits` expose `base_nominal` (= `msg[0x98]`) : le
  milieu de la cellule, réduit par `post_roll` en mode roll-then-reduce (ability).
* `engine/runner/operations/damage.py` — appel de `record_left_over_damages` dans le chokepoint,
  AVANT la mutation de PV. Aucune consommation RNG, aucune branche existante modifiée.
* `engine/runner/operations/triggers/loki/haze_of_corruption.py` — `HazeCorruptionBonusHitAbility` et
  `HazeOfCorruptionDamageTransferTrigger`.
* `engine/runner/operations/triggers/dispatch/registry.py` — le bonus rejoint
  `ABILITY_TRIGGERS["HazeOfCorruption"]`, le transfert entre en `EFFECT_TRIGGERS[1077]`.

### Ce qui n'est PAS porté, et pourquoi

* **`AreEqual(Actor@0x158, bonded)` exact** : le port ne STOCKE pas l'entité bondée (le 5e argument
  d'`AddBondEffect`, que `AddEffectOperation` ne transporte pas). Le gate est porté en vérifiant que
  l'auteur du coup fatal **porte `HazeOfCorruption`** — équivalent tant qu'un seul porteur est en jeu.
  Le rendre exact demande un champ `bonded` sur l'instance d'effet. **Résidu nommé.**
* **`NOT TriggeringEffectIs(0x435)`** du coup bonus : porté via `ev.triggering_effect`, que le vecteur
  mort ne renseigne pas → gate PERMISSIF. Ne mord que dans la chaîne à 2 relais, non montée ici.
* **Le repli `GetPersistentData` de `$$GetLeftOverDamages`** : pas de couche persistent-data d'ability
  côté port. Sur les montages à un seul relais la source de l'effet EST la cible initiale, donc la
  première lecture suffit.
* **Le flag `LeftOverDamage+0x7c`** : son seul consommateur connu
  (`ChainLeftOverHitsAttackDamageBehaviour$$GetLeftOverHits`, DakkaDakkaDakka) a son propre port
  DÉRIVÉ (`abilities/behaviours/combat.py::_left_over_hits`) et ne lit pas cette liste-ci.
* **La cible du coup bonus** : le natif frappe le cadavre ; les sélecteurs du port ne rendent que du
  VIVANT. La feuille appelle donc directement l'`Operation` qu'elle appelle en dessous
  (`AttackDamageOperation.execute_ability_attack`), le sélecteur natif étant ici trivial
  (`Target@0x178`, aucune structure déclarative perdue).

## 4. La mesure

```
python probe_209_haze_damage_transfer.py --seeds 777,88 --hp 6000,5000,8000
python probe_209_haze_damage_transfer.py --seeds 777 --hp 4000 --dump-events
python -m pytest tests/engine/runner/test_haze_of_corruption_transfer_live.py -q
```

Montage : géométrie CRAFTÉE de `probe_207_haze_pool_ladder.py` (k = 1) — `deathBlightlord` sur MC1_67,
cible `astraBullgryn` (aucun trigger, aucun summon → **une seule** émission de `On(0x2b)`), relais
`astraDreir` déplacé sur un voisin commun. `--hp-target` pilote le régime de mort.

Le probe TRACE séparément « le trigger est évalué » et « le trigger fire » : sans cette séparation un
volet muet est indiscernable d'un volet non collecté (c'est ce qui a fait croire, une itération
durant, que le coup bonus ne se déclenchait pas alors qu'il tirait sans laisser d'entrée).

### 4.a Garde et contrôle adversarial

`tests/engine/runner/test_haze_of_corruption_transfer_live.py` (6 tests) :

* OFFLINE — les littéraux lus (event `PreUnitDeath`, effet `0x435`, profil `Toxic`, `nrOfHits = 1`) et
  l'inscription des deux volets aux registres ;
* LIVE — port == natif sur les deux régimes de mort (site C seul, puis site B + site C) ;
* LIVE — la cible SURVIT : `0` des deux côtés **et** aucun des deux volets ne fire (anti-sur-tir) ;
* LIVE — la base nominale est INVARIANTE sur deux seeds aux jets différents, et vaut le milieu exact
  de la cellule d'arme (c'est le test qui réfute « le leftover est le jet »).

### 4.b Non-régression rejouée

`test_haze_of_corruption_rng_live.py` + `test_damage_roll_live.py` → **13 passed** ;
`test_flail_swing_live.py` + `test_sworn_protector_kell_live.py` → **10 passed**.

## 5. Ce qui n'est PAS couvert

* **Le flux RNG du report** : natif 8 tirages contre 6 côté port au régime 6000 (4 communs +
  l'arme). Le critère de ce cas est le **dégât**, explicitement hors flux RNG ; l'écart de 2 tirages
  (répartition crit/jet entre le coup bonus et les transferts) est un **résidu nommé, chiffré**.
* **La CHAÎNE à 2 relais** (`k = 2`, bond `(units[0], units[1])`) : le montage `astraCreed` la
  produit, mais aucun régime ne l'a fait tirer (il faut que le premier relais meure du report). C'est
  là que mordent les deux gates approximés (`bonded`, `TriggeringEffectIs`).
* **Les branches `On(UnitRevived)` / `On(UnitFled)`** du trigger de transfert (voies de RETRAIT du
  bond) : non montées.
* **Le régime armure non nulle** : `--hp-target` force `Armor/FixedArmor` à 0. La base nominale y est
  la cellule réduite ; avec une armure non nulle, le champ `+0x98` reste à confronter.
