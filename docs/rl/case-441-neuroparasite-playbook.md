# case-441 — `Neuroparasite` (1183), et le playbook ATTACK qui ne lit AUCUN poids

Deuxième des résidus ATTACK de `case-419` §7, à égalité de tête (**7 porteurs dispatchés**).
Le corps n'avait pas été lu ; il ne ressemble à aucun de ses voisins — et surtout pas à `1204`.

**Résultat** : le playbook est porté et confronté live. Le câblage ouvert par #438
(`case.DamagePrediction`) ne lui sert à **rien** : son corps ne lit que `case@+0x20`. Ce qu'il
exigeait, c'est un **état qui n'existe pas au déploiement** — et c'est là que le montage se joue.

## 1. Le corps natif — DEUX sorties, et pas une seule clé de poids

`IdunBattle.AI.Playbook.Loki.NeuroparasitePlaybook$$CalculateAttackUtilityInStepsInternal` monte la
SM `d__2`. **Sa structure se lit dans le wrapper, pas dans un nom** : `sm@+0x20 = case`,
`sm@+0x28 = this` (le PLAYBOOK), `sm@+0x10 = 0`. Le troisième paramètre — le délégué scorer
`getUtilityVal` — **n'est pas stocké**. Corps :
`NeuroparasitePlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__2$$MoveNext`.

```
target = case@+0x20
if (EntityExtensions.HasEffect(target, this.State, (EffectType)0x4c2, onlyActive: null))
    yield return Fix64.op_Implicit(1)        // état 2
else
    yield return Fix64.op_Implicit(0)        // état 1
```

* **La valeur est le LITTÉRAL `1`.** `FixMath.NET.Fix64$$op_Implicit` = `(long)(int)value << 0x20`,
  soit 1.0 exactement. Pas de `GetUtilityValue`, pas de `.cctor`, **aucune entrée
  `Utilities.Default.TriggeredAbilities`** — c'est le seul playbook ATTACK porté à ce jour dont la
  sortie ne vient pas du BC. Chercher une clé `NEUROPARASITE_*` serait chercher ce qui n'existe pas,
  et le piège #271 (poids servi à 0) est **sans objet** ici.
* **`0x4c2` = 1218 = `EffectType.Neuroparasite`**, à QUALIFIER : `1183` est le
  `TriggeredAbilityType` du **même nom** (l'ability, celui que `$$.ctor` passe à la base —
  `0x49f`). Le playbook lit l'**EFFET**, pas l'ability. L'effet est matérialisé **côté cible**,
  mesuré live dès #86 (`engine/entities/effects/loki/damage_reduction.py::NeuroparasiteEffect`).
* **`onlyActive` = littéral `0`** ⇒ `IsOwnerOfEffect(e, state, type, 0) || IsTargetOfEffect(...)`
  sans lecture de `EffectComponent.IsActive @+0x5c` — donc `EffectsState.has_effect`, jamais
  `active_effects`. C'est **exactement** le call-site de `SuppressiveFire` (`0x3f1`) : le prédicat
  est mis en foyer partagé `battle_query.scene_has_effect` et `suppressive_fire` y pointe désormais,
  au lieu d'en porter une copie locale (fork de port du même corps natif).
* **Face MOVE** : `d__1$$MoveNext` est un `yield Fix64.op_Implicit(0)` CONSTANT (décompilé lu) —
  son absence de `TRIGGERED_MOVE_PLAYBOOKS` EST le comportement natif.

## 2. Le sens — le playbook n'est PAS l'inverse du trigger, et le confondre est facile

`NeuroparasiteAbility$$CreateTrigger` monte `On(9) & OwnerIsCaster & !HasEffect(target, 0x4c2, …) &
IsUnit(target) & CurrentAttackDamageProfilesContain(0xd) & !(OwnerIsActor & OwnerIsTarget)` :
le trigger **exclut** les cibles déjà infectées, le playbook **les préfère**. Ce n'est pas une
contradiction — le `!HasEffect` dit seulement que la POSE (`$$CreateBehaviour` =
`DSLBehaviors.AddBondEffect(0x4c2, …)`) ne se rejoue pas. Le gain est ailleurs :
`NeuroparasiteEffect$$GetIncreaseLevelBehaviour` (`IncreaseEffectLevel`, plafonné par
`$$GetMaximumLevel`), armé par `$$GetDamageTakenTrigger`
(`OwnerIsTarget & CurrentAttackDamageProfilesContain(0xd)`), **monte le niveau** — et c'est ce
niveau que multiplie l'additif de `$$CreateEffectDamageMalusForDefense`.

## 3. Le montage — le régime utile N'EXISTE PAS au déploiement, il se CONSTRUIT

Aucune unité n'est parasitée au déploiement : un montage nu tombe **entier** dans la sortie 0, où
port et natif sont d'accord… pour rien. Le probe fabrique donc le régime :

1. le Neurothrope **TIRE** — l'arme psychique (range 3), seul profil que le trigger accepte
   (`0xd` = `Psychic`) ; son arme de mêlée est `Physical` et ne pose **rien** ;
2. `endturn` ×2 lui rend son action (même ré-armement que `probe_124._drive_to`), puis le placement
   est **re-vérifié** (le tour adverse a pu déplacer les cibles) ;
3. mesure.

⚠ **Piège de dégénérescence MESURÉ** : avec les deux cibles **adjacentes**, le tir en a infecté
**DEUX** — le témoin sain disparaissait. D'où `MIN_SEP = 4` entre les deux cibles, imposé et
attesté par le montage.

Le probe mesure **AVANT et APRÈS** sur la MÊME cible : c'est l'**anti-confond temporel** — elle doit
passer de « manque 0 » à « manque exactement 1 ».

## 4. Mesure — board `MC1_67`, seed 41504, caster `tyranNeurothrope` (HERO **au pool**)

```
[before] astraBullgryn  infecte=False nat= 6.674666 port= 6.674666 d=+6e-9 | manque=-0.000000006
[before] astraCreed     infecte=False nat=15.021749 port=15.021749 d=+2e-9 | manque=-0.000000002
[after ] astraBullgryn  infecte=True  nat=14.502825 port=14.502825 d=-7e-9 | manque=+1.000000007
[after ] astraCreed     infecte=False nat=15.021749 port=15.021749 d=+2e-9 | manque=-0.000000002
[lvl2  ] astraBullgryn  infecte=True  nat=22.374431 port=22.374431 d=-2e-9 | manque=+1.000000002
[lvl3  ] astraBullgryn  infecte=True  nat=31.353482 port=31.353482 d=+2e-9 | manque=+0.999999998
```

Conformité exacte partout ; playbook retiré du registre ⇒ le port perd **exactement 1.0** sur
l'infectée et **rien** sur la saine.

**La généralisation par NIVEAU est le discriminant fort** : l'utilité totale de la cible infectée
passe de 14.50 à 22.37 puis 31.35 (l'additif de dégât, lui, MULTIPLIE par `EffectLevel`), tandis que
le terme du playbook reste **1.0** aux trois niveaux. Un port qui aurait lu le niveau au lieu de la
présence divergerait de 1, 2, 3 — cette garde le verrait. `escalate` ÉCHOUE si le niveau ne monte
pas : une contre-épreuve qui ne mord pas ne prouve rien.

## 5. Contre-épreuves JOUÉES (sur une contre-épreuve, VERT est le résultat suspect)

L'ancre du patch a été vérifiée présente (`git diff` relu) **avant** de lire chaque verdict.

1. **Prédicat inversé** (`if not scene_has_effect(...)`) → `test_..._matches_native` et
   `test_..._reads_the_effect_not_the_ability` ROUGISSENT (« rend 0.0 … alors qu'elle doit rendre
   1.0 »).
2. **Enum confondu** (`1183` l'ability au lieu de `1218` l'effet) → les deux MÊMES tests rougissent.
   C'est précisément le faux-ami que ce cas porte : deux entiers, un seul nom.
3. **Registre vidé de 1183** → les 5 tests partent en ERROR sur « le playbook 1183 n'est PAS au
   registre — rien à muter » : un rouge franc, jamais un vert silencieux.

⚠ `test_..._term_is_load_bearing` reste VERT sous (1) et (2) — il compare le natif au port **muté**,
donc il mesure la taille du trou natif, pas le port. C'est `matches_native` qui attrape. Les trois
gardes ne sont pas redondantes.

Après chaque contre-épreuve, la restauration a été vérifiée identique au commit (`git diff` vide).

## 6. Ce que ce cas ne couvre PAS

* **La branche `IsTargetOfEffect`** de `HasEffect` : l'effet 1218 est **possédé** par la victime, le
  montage n'exerce donc que `IsOwnerOfEffect`. La seconde branche est portée (foyer partagé) mais
  non confrontée sur ce type.
* **Le canal live du kit (#419)** : `1183` est dans les `passiveAbilities` du gameconfig, donc le
  repli offline suffisait — ce montage ne prouve rien sur la lecture live de l'`AbilitiesComponent`
  (c'est `case-419`/`Lakrimae` qui la garde).
* **Le régime MULTI-EVENTS (AoE)** : même angle mort que `#438-r1`. Le terme s'ajoute par event ;
  ici l'attaque psychique du Neurothrope **éclabousse** bien le voisin de la cible (mesuré §3), mais
  la mesure a été faite sur des cibles séparées pour garder un témoin.
* **Les 6 porteurs npc** : non confrontés — le HERO du pool suffisait, et le corps ne lit ni stats
  ni traits du caster.
* **Le plafond `$$GetMaximumLevel`** : balayé jusqu'au niveau 3, pas jusqu'au plafond.

## 7. Fichiers

* Port : `scripts/python/engine/playbook/neuroparasite.py` ; registre : `engine/playbook/psyker.py` ;
  foyer partagé : `engine/battle_query.py::scene_has_effect` (+ `engine/playbook/suppressive_fire.py`
  qui y pointe).
* Mesure : `scripts/python/probe_441_neuroparasite_pair_term.py`.
* Garde : `scripts/python/tests/engine/test_441_neuroparasite_pair_term_live.py` (5 tests).
