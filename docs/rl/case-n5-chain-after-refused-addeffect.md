# case-N5 — Chaîne `&` derrière un `AddEffect` REFUSÉ : elle **NE TOMBE PAS**

**Statut** : résidu N5 **RÉFUTÉ** — le port était déjà conforme ; ce qui était faux, c'est la
DOCUMENTATION du port. Corrigée + verrouillée par une garde live.
**Touche** : le combinateur `Seq` (`op_and`/`op_add`) et la feuille `AddEffect` — donc tout arbre DSL
qui chaîne une pose d'effet avec autre chose.

---

## 1. La question

Quand `IdunBattle.Operations.AddEffectOperation$$Execute` abandonne (gate d'immunité `IEffect`
slot 40, cf. `case-224-effect-immunity-gate.md`), la suite de la chaîne `op_BitwiseAnd` qui suit la
feuille `AddEffect` s'exécute-t-elle ?

`case-224` §5.2 et le commentaire in-situ d'`operations/effects.py` affirmaient **non** (« la suite de
la chaîne tombe avec »), sur la foi d'une mesure #112 où la branche Chaos entière d'`ExemplarOfHate`
était absente sur `blackAbaddon`. Le port, lui, poursuivait la chaîne — d'où le résidu N5.

---

## 2. La réponse native (décompilé)

**La chaîne NE TOMBE PAS.** Deux artefacts l'établissent, et l'abandon s'arrête à l'opération.

### 2.1 La feuille JETTE le résultat de l'opération

`IdunBattle.Entities.Behaviours.AddEffectBehaviour$$Execute` :

```
*param_1 = 0 ; param_1[1] = 0 ; … ; param_1[7] = 0        # OperationResult (0x40) zéro-initialisé
foreach target in (this+0x68).Select(entities) :
    if (UnitExtensions.HasFlag(target, 6 = Dead)) continue          # gate PROPRE au behaviour
    …
    FUN_18002abc0(0x10, <IOperationProcessor>, proc, source, target, builder, effectType, &opts)
return param_1                                            # ← JAMAIS réécrit
```

L'appel du slot 0x10 n'affecte rien : la valeur rendue par `AddEffectOperation$$Execute`
(`longlong` = l'entité-effet, `0` sur **chacun** de ses gates) est **jetée**. Le retour du behaviour
est donc *toujours* le `OperationResult` zéro-initialisé.

Contre-exemple qui NOMME le mécanisme (une feuille qui, elle, PROPAGE) :
`IdunBattle.Entities.Behaviours.DiscardHitBehaviour$$Execute` recopie les 8 slots rendus par son
opération dans son propre `param_1`. C'est cette famille-là — et non `AddEffect` — qui peut
court-circuiter un `&`.

### 2.2 Le combinateur ne court-circuite que sur un flag qu'`AddEffect` ne pose jamais

`IdunBattle.DSL.CombinedBehaviour$$Execute` (une seule classe pour `op_BitwiseAnd` **et**
`op_Addition`, left@0x50 / right@0x58) :

```
exec left(entities) ; OperationResult.Combine(param_1, r)
if (*(char *)(param_1 + 4) == 0)                          # byte @+0x20 du résultat
    exec right(entities) ; Combine(param_1, r)
```

et `IdunBattle.Core.OperationResult$$Combine` propage ce byte par OU
(`if (byte@+0x20 == 0) byte@+0x20 = other.byte@+0x20` ; idem +0x21 et +0x22). Un résultat
toujours-nul ne peut donc jamais interrompre la séquence.

### 2.3 Où s'arrête exactement l'abandon

**À l'opération courante, et rien de plus.** Il ne remonte ni à l'itération du sélecteur-cible du
behaviour (les cibles suivantes sont traitées normalement), ni au combinateur parent.

### 2.4 Aucun refus ne se distingue d'un autre

`AddEffectOperation$$Execute` rend `0` sur les trois gates (`target == 0`, immunité, cible `Dead`) —
**et aussi** quand `UpdateExistingEffect` a fait son refresh (`lVar19` reste 0 : c'est la voie
« effet DÉJÀ PRÉSENT », qui n'est même pas un refus, elle incrémente `TimesApplied`). Comme le
behaviour jette ce retour, **la distinction n'a aucun effet observable sur la chaîne**. Corollaire de
portage : poser `stop` dès que `eff is None` serait le fork symétrique — il tuerait des chaînes que le
natif poursuit, y compris sur une simple re-pose.

---

## 3. La mesure live — le confond de `case-224` §5.2, levé

`probe_n5_chain_after_refused_addeffect.py` (runner isolé, board `MC1_67`, seed 112112).
Camp joueur **DÉPLOYÉ au contact** (positions de deploiement calculées depuis les positions réelles
du camp adverse, mesurées par un build de reconnaissance) : c'est ce qui rend l'élection d'attaquant
`ExemplarOfHateAbility$$GetAttacker` **garantie** au lieu d'être subie.

`ExemplarOfHate` (1140, `darkaAsmodai`) = `AddEffect(1293) & If(Chaos, AddEffect(Pinned) &
((AddStatOverrideEffect & UseActiveAbility) & RemoveEffect))`.

| montage | attaquant élu | `Pinned` | override + attaque libre | HP cible |
|---|---|---|---|---|
| `blackAbaddon` (**TerminatorArmour**), caster à d=1 | le caster | **refusé** | **présents** | 10038 → **7442** |
| `blackAbaddon`, caster écarté (d=2), allié ranged à d=2 | `darkaHellblaster` | **refusé** | **présents** | — |
| `blackPossession` (Chaos sans le trait), caster à d=1 | le caster | posé | présents | 8034 → **0** |

Cascade du 1er montage : `ExemplarOfHate_Target` · `TemporaryStatOverride` · `Loki_NormalAttack` ·
6 × dégât · `TerminatorArmour_ReduceDmg` · `TemporaryStatOverride` (retrait). **Aucun groupe `Pinned`.**

**Le confond** : dans le montage de `case-224` §5.2, aucun DarkAngels n'était à portée de la cible.
Sans attaquant élu, les trois feuilles qui suivent le `Pinned` (`AddStatOverrideEffect`,
`UseActiveAbility`, `RemoveEffect`) sont vides **de toute façon** — « chaîne tombée » et « personne
pour attaquer » y étaient indiscernables. Ce montage a d'ailleurs été **reproduit** au premier essai
de ce probe (caster à d=2, allié à d=2 mais sans élection : aucun override, aucune attaque), ce qui
confirme l'origine du malentendu.

---

## 4. Ce qui change dans le code

Aucune modification de comportement — le port était déjà 1:1. Trois corrections **documentaires**,
là où la fausse lecture aurait fait « corriger » le port dans le mauvais sens :

- `engine/runner/operations/effects.py` — le commentaire du gate d'immunité affirmait la chute de
  chaîne comme un GROUND TRUTH ; il énonce désormais l'inverse, avec le mécanisme natif et les
  chiffres.
- `engine/entities/behaviours.py` (`Seq`) — dit maintenant **qui** peut poser le flag @+0x20
  (les feuilles qui propagent, `DiscardHitBehaviour` en exemple) et que `AddEffectBehaviour` ne le
  peut pas.
- `engine/runner/abilities/behaviours/effects.py` (`AddEffect`) — le `return OperationResult.ok()`
  porte la raison native de son inconditionnalité.

---

## 5. Validation

`scripts/python/tests/engine/runner/test_chain_after_refused_addeffect_live.py` (4 tests, ~20 s) :

1. **le critère** — cible `TerminatorArmour`, caster au contact : `Pinned` refusé **et** override +
   attaque + dégât, live ET port (le port est calé sur `dumpRng`, sans quoi `UseActiveAbility` se
   dégrade en no-op et l'on ne distinguerait pas « chaîne tombée » de « attaque non résolvable
   offline ») ;
2. **cas nominal** — cible sans le trait : `Pinned` posé et chaîne poursuivie (garde du chemin où la
   pose aboutit) ;
3. **généralisation** — caster écarté, attaquant élu = l'ALLIÉ ranged : même verdict avec un porteur
   d'attaque différent du caster (et l'élection du port est confrontée à celle du natif) ;
4. **verrou structurel** (offline) — `Seq(AddEffect, Emit(sonde))` : la sonde s'exécute dans les
   **trois** issues qui rendent `None` côté port (refus d'immunité · effet déjà présent · cible
   nulle), et le témoin `Stunned` couvre la pose qui aboutit.

**Vue ROUGE avant d'être verte** : avec la mutation `if eff is None: return OperationResult(stop=True)`
posée dans `AddEffect`, (1) et (4) tombent, (2) reste vert — c'est exactement la signature d'une
régression que le cas nominal ne voit pas.

Gardes rejouées (dépendances de `AddEffectOperation` / du combinateur / d'`ExemplarOfHate`) :
`test_effect_immunity_live` · `test_darkangels_lot1_live` · `test_effect_stun_live`.

---

## 6. Résidus nommés

1. **`UnitsWhoCanAttack` du collapse `_exemplar_of_hate_attackers` ignore la LOS/obstruction.** Le
   port ne teste que « portée d'arme max ≥ distance hex » là où le natif appelle
   `GetBrokenTargetingRules(unit, unit.MainTile, target, unit.NormalAttackType)`. Résidu **déjà
   flaggé** dans la docstring du port ; observé ici de façon compatible : à distance égale (d=2,
   portée 3), un placement élit l'allié et un autre n'élit personne. Non chiffré — il faudrait
   isoler la règle brisée. Sans effet sur le présent cas (les trois montages retenus élisent
   effectivement un attaquant).
2. **Le gate cible-MORTE du BEHAVIOUR** (`HasFlag(target, 6)` dans `AddEffectBehaviour$$Execute`,
   qui **saute la cible** sans appeler l'opération) n'est pas porté ; le port ne porte pas non plus
   son homologue dans l'opération (redondant en pratique, cf. commentaire in-situ). Inchangé par ce
   cas.
