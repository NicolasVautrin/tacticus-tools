# #287-r4 — `_has_valid_targets` : une INSTANCE, et le volet CASTER

`operations/turnflow._has_valid_targets` est le mirror d'`IdunBattle.Core.Services.AttackQuery$$HasValidTargets`,
le prédicat de `HasActionAvailable` — donc du flag `UnitFlag.NoActionAvailable`. Il portait **deux**
défauts, le second **masqué** par le premier.

## 1. Le rouge de départ

`tests/engine/test_437_overwatch_consumes_armour_live.py` rendait **4 erreurs** sur `master` :

```
TypeError: ActiveAbility.get_dynamic_invalid_target_reason() missing 1 required
           positional argument: 'target_id'
engine/runner/abilities/targeting.py:3005
```

Le site passait la **CLASSE** d'`ABILITY_CLASSES` là où `get_invalid_target_reason` appelle
`ability.get_dynamic_invalid_target_reason(state, caster_id, target_id)` : sur une classe la
méthode est **non liée**, `state` se lie à `self`. Sa voie « ability non portée » fabriquait en plus
un type anonyme `_UnportedTargeting` qui n'avait pas du tout la méthode → `AttributeError`.

## 2. La question de RE, et sa réponse

> La surcharge **7 arguments** de `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason`
> — décrite dans le port comme « le FILTRE STATIQUE PUR », d'où `apply_self_cast_switch=False` —
> consulte-t-elle le délégué dynamique `options+0x38` ?

**OUI.** Relue à l'octet sur `rnca9r7q6c`, entre `TargetIsNotAdjacentToEnemy` (bit 42) et
`TargetIsCasterOrEnemy` (bit 57) :

```c
if ((options.Rules & 2) != 0) {              // TargetMatchesDynamicRule
    d = options.<+0x38>;                     // posé par `AActiveAbility$$.ctor` (vtable +0x480)
    if (d == null) <NullReferenceException>; // un délégué NUL LÈVE -- il ne dégrade pas
    rule = d.Invoke(caster, casterTiles, target, targetTiles);
    if (rule != 0) return GenericBrokenTargetingRule(rule);
}
```

Donc **bug de TYPAGE, pas de cadrage** : le correctif est d'instancier, jamais de retirer
l'évaluation. « Filtre statique pur » ne qualifiait que l'absence de l'**aiguillage self-cast** et
du **volet caster** — tous deux dans les surcharges 5 arguments, en amont. Les trois surcharges
(deux à 5 arguments, une à 7) sont distinguées dans `targeting.py` ; les docstrings qui écrivaient
« statique pur » sont corrigées.

## 3. Le second défaut, que le premier cachait

Une fois l'instanciation posée, le port **répond** — et il répondait faux.
`IdunBattle.Core.Services.TargetingQuery$$GetValidTargets`, la fonction dont cette boucle est le
mirror, **ouvre par le volet caster** :

```c
reason = GetInvalidCasterReason(caster, casterTiles, options);
if (reason.IsInvalid())  return ValidTargets.Empty;     // aucune cible, pas « toutes »
range = GetRange(...); foreach (t in GetPossibleTargetsForOptions(...)) { <la 7 args> }
```

Ses **quatre** surcharges convergent vers ce corps : le volet est dans le chemin quel que soit
l'overload. Ce n'est pas en contradiction avec `apply_self_cast_switch=False` — la 7 arguments n'a
pas le volet, c'est son **appelante** qui le porte. Deux étages, tous deux nécessaires.

**Mesure qui l'a imposé** (`C1_02` / seed 28704, `orksWarboss` après un pas — board et unités
distincts de ceux de #437) : natif `abilityReason.casterReason = CasterHasNotMoved`,
`UnitFlag.NoActionAvailable` **posé** ; le port trouvait `Waaagh` castable et ne posait pas le flag.
Le port savait déjà calculer la raison (`get_invalid_caster_reason` rend bien `0x10`) — il ne
l'appelait pas.

**Ampleur** : **38** des 148 masques lus portent au moins un bit `Caster*`. Les masques d'**attaque
normale** n'en portent **aucun** (mesuré, 21 tables) → `valid_normal_attack_targets` est inerte sur
ce point.

## 4. Chiffres, re-dérivés des deux côtés

Arbre témoin = arbre **complet** d'avant correctif (`git archive`), pour que les caches *lazy* du
gameconfig voient les mêmes entrées.

| Mesure (`probe_287r4_targeting_needs_instance.py`) | avant | après |
|---|---|---|
| ids dont le masque effectif porte `TargetMatchesDynamicRule` | 65 | 65 |
| — voie classe du registre / voie non portée | 47 / 18 | 47 / 18 |
| `_has_valid_targets` sans exception | **0 / 65** (47 `TypeError`, 18 `AttributeError`) | **65 / 65** |
| porteur à règle dynamique **liée** | **0 / 65** | **65 / 65** |
| porteur fabriqué au site (type anonyme) | **65** | **0** |
| volet caster consulté en tête | non | oui |

Le bit du **masque** suffit à entrer dans la branche : plusieurs des 47 (`MultiThreatEliminator`,
`ArmoriumCherub`, `SkyStrike`…) ne surchargent pas la règle et levaient sur le défaut hérité
d'`ActiveAbility`. Un recensement par *surcharge* en aurait manqué la majeure partie.

**Ampleur en bataille** : **54** des 175 unités du seed BC portent une des 65 abilities.

## 5. Le correctif

- **Face classe portée** : `klass()` — même construction qu'`abilities/handler.py`.
- **Face non portée** : classe **nommée** `UnportedAbilityTargeting` (`abilities/targeting.py`,
  pendant de `_NormalAttackTargeting`), portant les **deux** règles-déléguées avec leur
  non-évaluabilité **documentée**. Pas de `getattr` défensif. Le natif a toujours un délégué et
  **lève** s'il est nul ; le port ne peut pas évaluer un corps qu'il n'a pas porté → `0`, la
  dégradation permissive du module (résidu **#287-r4-r1**, §7).
- **Volet caster** : `get_invalid_caster_reason` en tête, `False` (une mesure) et non `None`.

## 6. La garde

`tests/engine/test_287r4_targeting_needs_instance_offline.py` — **offline**, le défaut étant
structurel. Cinq étages (recensement non vide et bi-voie ; aucune exception ; porteur = instance de
classe nommée à méthode liée ; la règle dynamique est **effectivement consultée** ; le volet caster
est en tête) et **quatre mutants** qui prouvent que chaque critère mord :

- **A** — le site qui passe la classe → étages 1-2 ;
- **B** — instancier mais **désarmer le bit** : le correctif paresseux qu'il fallait écarter,
  que les étages 1-2 déclarent vert → seul l'étage 3 le voit ;
- **C** — porteur sans la méthode → étage 4 ;
- **D** — instancier mais **omettre le volet caster** : étages 1-4 verts → seul l'étage 5 le voit.

**Vu rouge** sur l'arbre d'avant : `5 failed, 5 passed` ; vert après : `10 passed`.
`probe_287r4` : `rc=1` avant, `rc=0` après.

⚠ Le substrat (deux entités **nues**) est délibérément dégénéré pour que la cascade descende
jusqu'au bit dynamique — mais le caster y est **sans tuile**, donc le volet caster refuse
légitimement (`AllowNullCasterTile`, cf. #366-r1) sur 39 des 47. Les étages 1-2 **isolent** donc le
volet (`sans_volet_caster`), sans quoi ils seraient verts **par vacuité** ; et l'étage 5 s'appuie
au contraire sur ce refus, via deux masques à **un bit d'écart**.

## 7. Résidu — #287-r4-r1, RÉSOLU (voie (a))

> **Suite** : `case-287r4r1-regles-dynamiques-de-ciblage.md`. Quatre corps portés (1005, 1038,
> 1201, 1145), le rouge `necroWarden` fermé en live (`port` passe de `[0,1]` à `[0,1,4]`), et un
> foyer `DYNAMIC_TARGET_RULE_UNPORTED` pour les abilities sans classe. Reste ouvert : **#287-r5**
> (46 ids sans règle, recensés avec leur symbole) et **#287-r6** (`SquigMine` refuse pour la
> mauvaise raison — gisement du domaine TILE, mesuré indépendant de cette tranche).
> La voie (b) décrite ci-dessous n'a **pas** été prise, et l'analyse qui la classe seconde tient.

**La règle dynamique n'était évaluable que pour 15 des 65 ids.** Ventilation d'alors :

| état de la règle dynamique | ids |
|---|---|
| **surchargée** (évaluable) | 15 |
| classe portée **sans surcharge** (défaut hérité `-> 0`) | 32 |
| voie **non portée** (`UnportedAbilityTargeting -> 0`) | 18 |

Pour les **50** non évaluables, le port rend `0` (« pas de refus ») et `_has_valid_targets` fabrique
un `True` que rien ne mesure. **Divergence observée** : `C1_02` / seed 28704, walker `necroWarden`
(`AdaptiveStrategy` 1005, masque `0x402` = `TargetMatchesDynamicRule | TargetIsFriendly`) — natif
`targetReason = TargetMatchesDynamicRule`, `NoActionAvailable` **posé** ; port `0`, flag **non
posé** (`live=[0,1,4]` vs `port=[0,1]`). Le volet caster est hors de cause (`0x0` des deux côtés).

**Piste, non appliquée ici** : `_has_valid_targets` est **tri-état** et le site refuse déjà de
fabriquer un `True` quand le masque n'est pas lu (« un `True` fabriqué. On le refuse
explicitement »). Le même raisonnement, un cran plus bas, donnerait — par **monotonie**, la règle
dynamique ne pouvant qu'**ajouter** des refus :

- cascade acceptant au moins une cible **et** règle non évaluable → `None` (indéterminé, l'abstention
  est comptée et imprimée par `probe_287r1r1`), au lieu de `True` ;
- cascade refusant toutes les cibles → `False` reste **certain**.

Non appliqué dans cette tranche : il ne **corrige** aucune divergence (il la rend visible), touche
50 ids d'un coup, et exige sa propre validation large. La correction de fond est le **portage** des
règles dynamiques manquantes.

## 8. Ce qui n'est PAS couvert

- Le résidu **#287-r4-r1** ci-dessus — le scénario B (`necroWarden`) reste **rouge**, et ne
  rougissait pas avant seulement parce qu'il **crashait**.
- Les règles du volet caster **non portées** (`CasterCanMove`, `CasterHasCompletedOneTurn`,
  `CasterHas1/3/7Tiles`, `CasterHas2TurnsLeft`, `CasterIsMachine`) : inchangées par cette tranche,
  inventaire dans `get_invalid_caster_reason`.
- `AttackQuery$$HasValidTargets` invoque son prédicat par un **slot d'interface avec délégué** ; que
  ce slot soit `GetValidTargets` est l'établissement de #287-r1-r1, **non re-tranché ici**. Ce qui
  est mesuré, c'est que le natif rend `casterReason` non nul et pose le flag dans le régime où le
  port ne le posait pas.
- L'ordre d'énumération des cibles (`state.entities`) : résidu déjà nommé au site, inchangé.

## 9. Validation rejouée

| | résultat |
|---|---|
| `test_437_overwatch_consumes_armour_live.py` (le rouge d'origine) | **4 passed**, 0 failed, 0 skipped |
| `test_287r4_..._offline.py` | 10 passed (avant : 5 failed / 5 passed) |
| 6 gardes offline du ciblage (#433, #436) + la nouvelle | 122 passed |
| `probe_287r1r1_verify_turn_ended.py` (montage par défaut) | OK |
| généralisation A — `C1_02`/28704, walker `orksWarboss` (`Waaagh`, voie classe) | OK |
| généralisation B — même montage, walker `necroWarden` (voie non portée) | **ÉCHEC** → #287-r4-r1 |
| `probe_477r15a_stream_conformance.py` | VERT — `C1_02` 204/204, `MC1_67` 316/316, 0 nouvelle |

Trajectoire de la généralisation A, en trois temps : **crash** (`TypeError: WaaaghAbility…`) →
`live=[0,1,4]` vs `port=[0,1]` (instanciation seule) → `live=[0,1,4]` vs `port=[0,1,4]` (volet
caster).
