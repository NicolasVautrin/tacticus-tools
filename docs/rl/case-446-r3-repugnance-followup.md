# #446-r3 — le TROISIÈME mold d'attaque normale : `RighteousRepugnance`, gate MELEE

Résidu §8 de `case-446-r1-boltstorm-followup.md`. Deux volets nommés : **(A)** porter et confronter
`IdunBattleLogic.Entities.Abilities.Active.Loki.RighteousRepugnance_NormalAttackAbility$$PredictAttack`,
que **aucun registre ne dispatchait** ; **(B)** trancher le `mods=None` de `get_klaw_attack1_prediction`.

Le porteur était à trouver : c'est **`adeptMorvenn`** (Morvenn Vahl), **HERO au pool** — aucun montage
catalogue, aucune greffe. Le port du mold **existait déjà** (c'est le même corps que celui de
`Boltstorm`) ; ce qui manquait était **la moitié CÂBLAGE**, sous l'autre gate.

## 1. Ce que dit le décompilé

```csharp
// ...RighteousRepugnance_NormalAttackAbility$$PredictAttack
base   = ALoki_NormalAttackAbility.PredictAttack(entities, abilityState);
weapon = ALoki_NormalAttackAbility.FindAttackWeapon(entities, abilityState);
if (weapon != null && weapon.get_IsMelee()) {        //  <-- `IsMelee != 0`, l'INVERSE de Boltstorm
    add = GetAdditionalDamagePrediction(entities, abilityState);
    DamagePredictionResult.Add(&add, &base);
    return add;
}
return base;
```

`RighteousRepugnance_NormalAttackAbility$$GetAdditionalDamagePrediction` a le **corps identique**
à celui de `Boltstorm` — mêmes appels (`TalonOfHorus_NormalAttackAbility$$GetAdditionalDamageAmount`,
SLOT 4 `AAmountFormula$$CalculateAverage`, `GetNumberConstant(0x2f)`, `GetDamageProfile`), mêmes slots
d'interface ; seuls le guard statique et l'adresse diffèrent (copies COMDAT non fusionnées). **Un seul
mold Python sert donc les deux**, et c'est l'APPELANT qui porte la gate.

**Le balayage des surcharges est CLOS et vérifié dans les deux sens.** `<X>_NormalAttackAbility$$PredictAttack`
n'existe que pour `ALoki` (la base), `Boltstorm`, `ProperKilly` et `RighteousRepugnance` ; chacun des
trois dérivés porte **exactement 2 xrefs DATA** (table de méthodes + vtable), donc aucun n'est un corps
**dédupliqué** partagé par plusieurs classes — le faux négatif que le `CLAUDE.md` met en garde de tirer
d'une absence de symbole ne s'applique pas ici, et c'est mesuré, pas supposé.

### L'asymétrie qui piège : fold d'EXÉCUTION sans fold de PRÉDICTION

`<X>_NormalAttackAbility$$GetAdditionalDamageBehaviour` (la face COMBAT) existe pour **QUATRE**
abilities : `Boltstorm`, `RighteousRepugnance`, **`Fealty`** et **`TalonOfHorus`**. Mais
`$$GetAdditionalDamagePrediction` n'existe **que pour les deux premières**, et ni `Fealty` ni
`TalonOfHorus` ne portent de `$$PredictAttack`. Ces deux-là foldent donc **en combat et pas en
décision** — quirk natif. Les inscrire au registre par analogie serait un fork de port ; le bloc de
registre le dit désormais en toutes lettres.

## 2. Le piège de la tranche, et comment il est désamorcé

Le montage qui exerce le mold de #446-r1 est le **tir à distance** — exactement celui qui
n'exercerait PAS celui-ci. Le régime nominal est donc le **CONTACT**, et le probe **refuse de
mesurer** s'il ne l'a pas installé (`MontageError`, jamais un vert silencieux). Trois attestations
gardent le régime, chacune capable de faire échouer le montage :

* l'attaque normale **LIVE** du caster vaut **`1182`** (`RighteousRepugnance_NormalAttack`) — c'est
  la preuve que la sous-classe surchargeante est instanciée ; le bras apparié exige l'**inverse** ;
* le caster est **adjacent au sens NATIF** (`bq.is_adjacent`, porte d'élévation `|delta| < 2`) ;
* `1107` est dans l'`AbilitiesComponent` live (moitié câblage), et la tuile témoin `RANGED` n'est
  **pas** adjacente native — sans quoi les deux crans mesureraient la même chose.

`adeptMorvenn` porte les deux armes qu'il faut pour ce contrôle : `Power` mêlée (2 coups, pierce 40)
et `Bolter` distance 3 (3 coups, pierce 20). Le même porteur donne donc les deux côtés de la gate,
sans rien déplacer d'autre que la tuile de tir.

## 3. Mesure — trois crans, accord EXACT champ à champ

`MC1_67` / seed `41504`, cible `astraBullgryn` en `(3,4)`, caster `u81` :

| cran | tuile | mods de l'attaque porteuse | natif `(rawMin, rawMax, hits)` | port | fold du port |
|---|---|---|---|---|---|
| `melee` | `(3,5)` | aucun | `2885, 4324, 5` | **identique** | `1341, 2010, 3` |
| `melee_elev` | `(2,3)` | `[1.5]` (élévation) | `4324, 6487, 5` | **identique** | `1341, 2010, 3` |
| `ranged` | `(3,6)` | aucun | `1158, 1737, 3` | **identique** | *aucun* — gate fausse |

5 coups = 2 (arme mêlée) + 3 (`nrOfHits` = constante `0x2f` du passif). Montant du fold, à level 50 /
multiplicateur 180 : `CalculateAverage(1197, 1595)` = **1396** (et non `1197`, la lecture « slot 4 =
MIN » que #446-r1 a réfutée).

## 4. Le CONTRÔLE APPARIÉ — la base native mesurée, pas supposée

Même board, même seed, même layout ; seule différence `--unit-stat "adeptMorvenn:PassiveAbilities=[]"`,
qui ramène l'attaque normale à la générique `69` et fait **disparaître le fold côté natif** :

| | `(rawMin, rawMax, hits)` |
|---|---|
| base NATIVE mesurée | `1544, 2314, **2**` |
| base du PORT | `1544, 2314, **2**` — **accord exact** |
| **fold natif isolé** (`melee` moins base appariée) | **`1341, 2010, 3`** |
| **fold du port** | **`1341, 2010, 3`** — **identique** |

La décomposition base/fold est donc **mesurée**, pas fittée : aucun scalaire n'a été ajusté. À la
différence de #446-r1, la base n'a **aucun résidu** ici (`#446-r2` ne se reproduit pas sur ce porteur).

> ⚠ **Le bras apparié exige de muter AUSSI le port, et ça n'est pas cosmétique.** Le port dispatche
> sur le **kit gameconfig**, que `--unit-stat PassiveAbilities=[]` ne touche pas (il patche le BC).
> Au premier passage, le port foldait donc dans un bras où le natif ne foldait plus, et le diff
> affichait un faux écart de `+1341/+2010/+3` — il mesurait le **harnais**, pas le moteur. Vider
> `_MELEE_FOLLOWUP_PASSIVES` le temps de cette lecture est le **pendant exact** du patch natif.
> #446-r1 n'a pas rencontré ce piège parce que son registre était encore vide au moment de la mesure.

## 5. Contre-épreuves — critère = déplacement du port NON MUTÉ

| mutant | `melee` | `melee_elev` | `ranged` |
|---|---|---|---|
| `no_dispatch` (registre vidé) | −1341 / −2010 / −3 coups | −2010 / −3015 / −3 coups | — |
| `amount_min` (« slot 4 = MIN ») | −192 / −288 | −285 / −429 | — |
| `no_mods` (l'ancien `mods=None`) | **vert** | −669 / −1005 | — |
| `gate_flip` (gate branchée sur `!IsMelee`) | −1341 / −2010 / −3 coups | −2010 / −3015 / −3 coups | **+1341 / +2010 / +3 coups** |

`gate_flip` est la contre-épreuve **propre à cette tranche** : c'est exactement ce qu'aurait produit
une recopie par analogie du mold `Boltstorm`. Elle déplace les **deux** côtés — le fold disparaît au
contact et apparaît à distance —, donc la gate portée est bien celle du natif et non son inverse.

**`no_mods` reste VERT au plain-pied, et c'est DIT plutôt que masqué** : sur une tuile de plain-pied
les modifiers de l'attaquant sont **vides** (le probe l'imprime : `mods = None`), donc `mods=None` et
`mods=mods` rendent la même chose pour une raison qui n'a rien à voir avec le port. C'est pourquoi le
cran `melee_elev` a été ajouté — une tuile adjacente **en surplomb**, qui arme le bonus d'élévation.
C'est le **même facteur** que #446-r1 avait fini par nommer après avoir réfuté deux traits au nom
évocateur. Le test exempte `no_mods` **uniquement** quand le board n'offre pas ce cran.

## 6. Généralisation

* **`C2_02` / seed `31337` / `--armor-target 3000`** : accord exact sur `melee` et `ranged`.
  Les valeurs sont **identiques** à `MC1_67` — normal, la prédiction IA est **pré-armure** pour
  l'attaque normale (`armorBefore = 0`), donc `--armor-target` ne mord pas sur ce canal. Le board
  étant plat, `melee_elev` n'existe pas et `no_mods` y reste vert, pour la raison ci-dessus.
* **`--unit-stat "adeptMorvenn:Damage=900"`** (axe structurel) : la base bouge fortement — `ranged`
  `1158..1737` → `432..648`, `melee` `2885..4324` → `1917..2874` — et le **fold reste exactement
  `1341, 2010, 3`**, accord natif/port exact sur les trois crans. Le montant du mold vient donc bien
  de la **config d'ability**, pas du stat Attack : c'est le mirror, vérifié par un levier qui
  déplace tout le reste.

## 7. Volet (B) — `get_klaw_attack1_prediction` : corrigé, NON confronté

**Le site souffrait du même défaut, et c'est un mirror, pas une analogie.** Ni le slot appelé par le
mold klaw ni celui du mold additional-damage ne transporte de `DamageModifiers` en argument — c'est
lisible dans les deux décompilés —, et les **deux surcharges** de
`IdunBattle.Core.Services.DamagePrediction$$PredictAttack` convergent sur le **même**
`IdunBattle.Core.Services.DamagePrediction$$PredictAttackRaw` : ses **seuls** appelants sont les
closures `<PredictAttack>b__0` de `DisplayClass12_0` et `DisplayClass13_0` (xrefs mesurées). C'est
donc le service qui recalcule les modifiers, **sur les deux chemins**. Garder la valeur `None` aurait
été conserver précisément la lecture que #446-r1 a réfutée par mesure sur le mold jumeau.

`mods` est donc threadé jusqu'à ce mold aussi. **Mais le bras n'est PAS confronté** :
`ProperKilly` n'a **aucun porteur** dans ce build — `unit_map find --ability ProperKilly` rend 0 sur
les 5 voies dérivables, **et** un balayage direct de tous les `all_unit_ids()` du gameconfig rend 0
lui aussi (deux sources indépendantes ; Ghazghkull n'est pas au catalogue). Le registre
`_MELEE_KLAW_PASSIVES` est donc **inerte par construction**, et aucune mesure ne peut l'atteindre.

## 8. Livré

* `scripts/python/engine/playbook/prediction/normal_attack.py` — registre
  `_MELEE_FOLLOWUP_PASSIVES = ("RighteousRepugnance",)` + son dispatch ; `mods` threadé jusqu'à
  `get_klaw_attack1_prediction` ; le bloc de registre documente les **trois** molds, la clôture du
  balayage et l'asymétrie `Fealty`/`TalonOfHorus`.
* `scripts/python/probe_446_r3_repugnance_followup.py` — montage attesté, trois crans, contrôle
  apparié, quatre contre-épreuves.
* `scripts/python/tests/engine/test_446_r3_repugnance_followup_live.py` — 5 gardes.

## 9. Résidus NOMMÉS

* **`#446-r3a` — le mold klaw (`ProperKilly`) reste NON CONFRONTÉ.** Correction posée sur lecture du
  décompilé ; zéro porteur dans ce build, donc inatteignable par toute mesure. À rejouer au prochain
  build qui introduirait Ghazghkull au catalogue.
* **`#446-r3b` — `Fealty` (1512) et `TalonOfHorus` (1205) foldent en COMBAT sans folder en
  DÉCISION.** L'asymétrie est lue au décompilé (`GetAdditionalDamageBehaviour` sans
  `GetAdditionalDamagePrediction` ni `PredictAttack`) mais **non confrontée live** : personne n'a
  vérifié que la face COMBAT de ces deux-là est portée, ni que la face DÉCISION reste bien sans fold
  sur un porteur réel. C'est un mirror à garder, pas un trou à combler.
* **Le playbook TRIGGERED `RighteousRepugnance` (`TriggeredAbilityType` **1107**) n'est toujours pas
  porté** — il est l'un des 13 résidus ATTACK de `#419-r1`, et **cette tranche ne le touche pas**.
  Conséquence directe : `pairUtility` sur `adeptMorvenn` porte encore l'écart de ce terme, et c'est
  pourquoi l'oracle de cette tranche est `aiPlaybookPredict` (l'étage PRÉDICTION) et non
  `pairUtility`. Ne pas lire un écart de paire sur ce porteur comme un reliquat du mold.
* **Capteur manquant, nommé (inchangé depuis #446-r1)** : `IndividualHitDamage@0x80`
  (`List<HitDamage>`, un élément par coup) n'est pas exposé par `readDamagePredictionResult`
  (`frida/hooks/game/damage-prediction.ts`). Il aurait tranché la décomposition base/fold **par
  coup**, en une mesure au lieu d'un contrôle apparié + un second runner. **Aucun reinject demandé** :
  rien de ce qui est livré ici n'en dépend.
* **Non couvert par ce montage** : le régime `FindAttackWeapon == null` (le porteur a toujours une
  arme), la cible à **bouclier** (le split bouclier du fold n'est pas exercé), et le régime `hit_mult`
  (`MkXGravis` sur la cible).
