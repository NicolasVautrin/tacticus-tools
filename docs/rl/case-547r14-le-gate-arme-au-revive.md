# case-547-r14 — le gate `KeepOnRevive` est ARMÉ au revive, et le port ne le lisait nulle part

`#547-r13` avait établi la face NÉGATIVE : sur le chemin de mort, `options.<+0x08>` vaut **0**, donc
`IEffect` slot 2 `get_KeepOnRevive` n'y est **jamais lu**. Ce cas-ci porte la face POSITIVE — le
seul producteur du binaire qui arme ce gate.

## 1. La lecture, re-mesurée sur `t6dpr4k06g`

`IdunBattle.Operations.ReviveUnitOperation$$Execute` appelle le slot 0x5a (`RemoveEffects`)
**INLINE**, entre `IdunBattle.Operations.ReviveUnitOperation$$SetHealth` et l'enregistrement
`HasBeenRevivedByAbility` qui précède la rafale de flags. Les deux écritures qui préparent les
options sont lues verbatim :

    local_438  = 0                      ->  `Nullable<KillUnitStep> step` SANS valeur
    lStack_430 = CONCAT44(_, 1)         ->  `options.<+0x08>` = 1        <- LE GATE
    (*puVar18)(plVar16, unit, &local_408, ...)                          <- slot 0x5a

Et le `if` imbriqué de `IdunBattle.Operations.RemoveEffectsOperation$$Execute`, relu à
l'assembleur, montre que la seconde clause est **indépendante** de la première — le natif y saute
(`goto LAB_180f7d00a`) depuis le test de `HasValue`, donc elle est évaluée dans les deux régimes de
step, et son gate est un **octet** (`*(char *)(options + 8)`) :

    if (options.step.HasValue && effect.<slot 4> != options.step.Value) continue
    if (options.<+0x08>       && effect.<slot 2>)                       continue
    toRemove.Add(effectId)

⇒ le revive retire **tous** les effets du ressuscité **sauf** ceux à `KeepOnRevive = True`.

⚠ `ReviveUnitOperation$$RemoveEffects` n'a **aucune xref CODE** (2 entrées DATA) : son corps est le
doublon émis par IL2CPP. Conclure « mort » de cette absence aurait été faux — c'est la lecture du
corps APPELANT qui tranche.

## 2. Le point le plus facile à mal lire

Le défaut de `IdunBattle.Entities.Effects.BaseEffect` est **True** (`b0 01 c3`). Ce retrait n'est
donc **pas** un retrait de masse : la quasi-totalité des effets survit. Il ne mord que sur les
classes qui renversent le getter à `False` — **trois** dans le binaire, dont **deux** ont un mirror
porté (`PrecisionShot_AimEffect`, `RitesOfMorkaiExtraDamageEffect`). La troisième,
`Loki.HealingBalmsEffect`, n'a **aucun** mirror sous `engine/entities/effects/` : ce qui est porté
sous ce nom est le TRIGGER `HealingBalmsDelayedHeal`, pas une classe d'effet — non-couvert **nommé**,
pas oublié.

Un test qui se contenterait de vérifier « la liste est vide après le revive » serait donc **faux**,
pas seulement faible.

## 3. Les 50 indéterminées ne sont pas un risque — et c'est MESURÉ

La dérivation de constante rend `INDÉTERMINÉ` pour **50 classes sur 465** : leur getter lit un champ
d'instance, écrit par le `.ctor` (`AStatModifierEffect` prend `keepOnRevive` en argument, déposé à
`this+0x481`). Le brief demandait de le **dire** plutôt que de combler.

Mieux que le dire : ces `.ctor` ont été **lus un par un** au décompilé — **30 lectures, 30 à
`keepOnRevive = 1`**. Le résultat structurant est
`IdunBattle.Entities.Effects.DynamicStatModifierEffect$$.ctor`, qui passe la constante **en dur** à
`AStatModifierEffect$$.ctor` pour **toute sa descendance**. L'héritage du défaut `True` est donc
**fidèle** pour ces classes, et aucune surcharge portée n'est justifiée : en poser une serait
inventer.

Ce qui reste ouvert (→ `#547-r15`), et qui n'a **aucun mirror porté** aujourd'hui :

* `IdunBattle.Entities.Effects.NoneEffect` existe en **deux** surcharges de `.ctor` dont la
  signature **nomme** `keepOnRevive` en argument : sa valeur vient du **site d'appel**, pas de la
  classe. Aucune lecture par classe ne peut la trancher.
* **six** `.ctor` absents de la table parce que **dédupliqués** (`ShockAssaultBuffEffect`,
  `PathOfCommandExtraCritEffect`, `RitesOfBattleExtraDmgEffect`, les deux `PropheticSentinel_*`,
  `ADynamicStatModifierEffect`). Leur corps est partagé avec des ctors lus à `1`, ce qui rend `True`
  très probable — mais **non lu individuellement**, et l'absence dans la table ne prouve rien.

## 4. La confrontation live, et les trois calages qui l'ont d'abord fait échouer

Montage (`probe_547r14_keep_on_revive_live.py`, runner 128, board `MC1_67`) : l'active
`1211 RitesOfMorkai` de `spaceWolfPriest` est le **seul** montage du jeu qui pose, du même cast et
sur la même unité, `1502 RitesOfMorkai` (un `ReviveEffect`, donc la `ReviveData`) **et**
`1529 RitesOfMorkai_ExtraDamage` (`KeepOnRevive = False`), sur le sous-ensemble de la zone qui porte
déjà une forme de Final Vengeance. `ultraTitus` porte `FinalJustice`, donc il reçoit les deux.

    avant  [1323, 1324, 1354, 1502, 1516, 1517, 1529]
    revive natif à 2800 PV
    après  [1323, 1324, 1354, 1516, 1517]

**1529 retiré ; cinq témoins à `KeepOnRevive = True` survivants** — le témoin non dégénéré sans
lequel « 1529 est parti » serait aussi compatible avec « le revive retire tout ». Agreement
port ↔ natif **exact**, hors `1502` : celui-là part par sa **propre** voie (`removeEffect = TRUE` au
ctor → `RemoveEffect` explicite du 2ᵉ volet de son behaviour), donc son sort ne dit **rien** du gate,
et l'inclure ferait passer un désaccord pour un accord.

L'i2 corrobore, indépendamment de la dérivation binaire :
`Abilities/RitesOfMorkai_CurrentLevelDescription` — « become *Inspired* for {[nrOfRounds]} round
**or until they are revived** ».

**Trois calages, chacun ayant d'abord fait échouer la confrontation :**

1. **crit et block neutralisés** (`--crit-target 0,0 --block-player 0,0`). La fenêtre létale
   non-overkill d'une arme de dégât `A` est `A/2 < hpAvant <= A` ; elle n'existe donc que si
   `D_max < 2·D_min`. Sans ces drapeaux, la même attaque a rendu **8772, 3010, 2650** (ratio 3,3) :
   la fenêtre est **structurellement vide**, quel que soit le calibrage des PV.
2. **marcher AVANT de caster.** `1502` dure **un round** : caster puis marcher le fait expirer avant
   le premier coup qui morde — mesuré, les cinq autres effets de la victime restant en place.
3. **HP 2800, pour tuer en UN coup.** Un seul attaquant tient au contact sur ce board, donc chaque
   coup supplémentaire coûte un tour, donc le round.

Deux fausses pistes écartées en chemin, toutes deux par la mesure : « overkill » (le coup létal
était dans la fenêtre et il n'y avait pourtant pas de revive → c'était l'expiration), et un
**désaccord port ↔ natif** qui n'était qu'un recenseur faux — `EFFECT_CLASSES` est indexé par **nom**,
pas par ordinal, et l'indexer par `int` rendait *tous* les types « sans classe portée ». C'est
pourquoi le probe **imprime** cette ligne au lieu de la taire.

## 5. Ce qui n'est PAS couvert

* Les deux poches de `#547-r15` ci-dessus.
* `Loki.HealingBalmsEffect` : valeur `False` mesurée au binaire, aucun mirror de classe pour la
  porter.
* La confrontation live porte sur **un** couple (`1529` sur `ultraTitus`). `PhoenixGem`,
  `FuelledByFury` et `TaintedNarthecium` posent aussi des `ReviveData` mais n'ont pas été
  confrontés : rien ne les distingue sur cet axe (le gate est dans l'Operation, pas dans le
  poseur), et le montage exigerait pour chacun un effet à `KeepOnRevive = False` concomitant.
