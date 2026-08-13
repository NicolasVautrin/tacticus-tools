# case-982 — le lot « BLOCAGE: capteur » : sept prémisses sur neuf étaient fausses

Neuf résidus portaient `BLOCAGE: capteur`, regroupés pour ne payer **qu'une** fenêtre de reinject
au lieu de neuf. Résultat mesuré : **deux** en exigent une. Les sept autres étaient bloqués par une
prémisse périmée, pas par un capteur manquant.

## 1. Le mode de panne, et il est unique

Un `BLOCAGE: capteur` s'écrit **au moment où l'on referme une tranche** — donc à partir de ce que
l'auteur avait sous la main ce jour-là. Rien ne le re-mesure ensuite. Les sept prémisses tombées
ici se répartissent en trois formes :

| forme | résidus | ce qui l'a périmée |
|---|---|---|
| le capteur a été **livré depuis** | `#419-r6-r1-r1`, `#959-r1` | une PR ultérieure l'a mergé et injecté |
| le canal **existait déjà** | `#966-r2`, `#916-r1`, `#590-r2` | `combatSnapshot.unitFlags` ; `interface_slots.tsv` ; `resolveVtableSlot` |
| la question se tranche **offline** | `#590-r5` | le `.cctor` de la classe PARENTE écrit les deux constantes |

⇒ **Re-mesurer la prémisse est la première étape**, avant d'écrire la moindre ligne de capteur.
Trois `curl` de RPC (`status` d'un capteur, un `grep` dans `data/symbols/`, un `decompile`) ont
suffi à retirer sept résidus de la file d'attente d'une fenêtre.

## 2. Ce qui a été TRANCHÉ, et par quoi

### `#419-r6-r1-r1` — RÉSOLU, prémisse réfutée
Le capteur `sortUtilityTrace` **et** son correctif `raxToInt64` (#419-r7) sont déjà chargés :
`sortUtilityTrace {action:"status"}` rend `diag.keysAtInt64Max`, champ qui n'existe que dans le
bundle corrigé. Le volet CLÉ, seul non mesuré, l'est donc : `keysAtInt64Max: 0` dans les deux bras,
et l'utilité d'`u81` passe de **133.2406 → 148.2406** quand `MightCrit` bascule — soit exactement
`+15.0`, ce que le port prévoyait au chiffre près. Le flag EST classant ; il n'y a aucun étage
neutralisant à chercher.
**Non couvert** : le TIE-BREAK du sélecteur (aucune égalité sur ce montage) et
`preventOverkill`/`forceOverkill`.

### `#959-r1` — RÉSOLU (port + confrontation)
`triggeredMoveTraceStatus` répond `installDone: true`. Le port de la face DÉCISION de
`GrimEfficiency` (1490) est bit-exact sur 38 lignes, dont **13 non nulles** (5/10/15 = 1/2/3 amis
× poids 5), et **discriminant** (sans le playbook : 13 écarts).
Deux écarts LUS avec son voisin `AstartesBanner`, qui changent le compte : `includeCenter = 0`
(l'ami sur la tuile candidate ne compte pas) et `units.Remove(case.unit)` (le mover ne se compte
pas depuis son origine). Query = `GetSurroundingFriends` (**slot 121**, filtre `IsFriend` appliqué
par `FilterInPlace` APRÈS coup), pas `GetSurroundingUnits` (slot 117, filtre `!IsEnemy` INTERNE).

### `#590-r5` — TRANCHÉ offline : la constante de rejet est ÉLIMINATOIRE
Les deux statiques ne sont pas sur `OnlyCertainTargetUtility` (qui n'en a aucun) mais sur sa classe
PARENTE, dont le `.cctor` est nommé : `IdunBattle.AI.Utilities.BaseUtility$$.cctor` écrit
`statics+0x00 = Fix64.op_Implicit(0)` et `statics+0x20 = Fix64.statics+0x18`, et
`FixMath.NET.Fix64$$.cctor` écrit `Fix64.statics+0x18 = 0x8000000000000000` = **`Fix64.MinValue`**.

> cible **dans** la liste → `0.0` (neutre) · cible **hors** liste → `-2147483648.0` (plancher du type)

Le port de #590 (élimination) est donc **CONFIRMÉ**. Ce n'est pas un malus calibré : `BaseUtility`
porte trois sentinelles quasi-minimales (`MinValue`, `MinValue/1.000001`, `MinValue/1.000002`) pour
ordonner des rejets tous éliminatoires — écrire `-1e9` casserait cet ordre.

### `#916-r1` — le slot est NOMMÉ, et l'appariement du résidu est FAUX
`data/symbols/<build>/metadata/interface_slots.tsv` porte `IEffect 5 get_AlwaysCreateOneEntityPerEffect`
et `IEffect 3 get_KeepOnChangeOwner`. Les VALEURS se dérivent sans fenêtre : `resolveVtableSlot`
est déjà chargé, la vtable est calibrée à `klass+0x138` par la signature `System.Object`, et
`interfaceOffset(BaseEffect, IEffect) = 4`. Valeurs de la base, lues **aux octets** :

| slot | RVA | octets | valeur |
|---|---|---|---|
| 3 `KeepOnChangeOwner` | `0x2b4590` | `b0 01 c3` | **true** |
| 5 `AlwaysCreateOneEntityPerEffect` | `0x2b45a0` | `32 c0 c3` | **false** |

⚠ Ghidra nomme ces deux corps `UnityEngine.U2D.IK.Solver2D$$DoValidate` et
`Stash.Native.StashNative$$get_IsPurchaseProcessing` : ce sont les propriétaires **arbitraires** de
corps **dédupliqués**. Le nom n'est pas l'identité.

**Et la mesure RÉFUTE le résidu** : `ActOfFaithBuffEffect`, dont l'empilement additif est mesuré
live (`145 290 435`), **hérite** — donc `false`. Le slot 5 n'est pas `stacks_stat_mod_on_add` :
quand `UpdateExistingEffect` retient une instance, elle incrémente `EffectComponent+0x6c` et écrit
`statModifierValue`, **c'est ça** l'empilement. Le slot 5 dit « une entité SÉPARÉE par
application » — taunts, liens, attaques en attente.
⇒ « Dériver le drapeau au lieu de le poser à la main » aurait écrit `False` sur `ActOfFaith` et
**cassé un comportement live-validé**.

Recensement (`probe_916r1_effect_slots.py`, 244 mesurées / 465) — slot 5 `true` : `ABondEffect`,
`APendingAttackEffect`, `BlockUnitMovementBondEffect`, `AttemptedPossession_PossessedEffect`,
`ExemplarOfTheMontkaEffect`, `HazeOfCorruption_DamageTransferEffect`, `HolyDuel_TauntEffect`,
`LifewardsBondEffect`, `NeuroparasiteEffect`, `OverwhelmingWrath_PendingAttackEffect`,
`TauntedEffect`, `Taunted_RefreshUnitTurnFinishedEffect`.

### `#590-r2` — le slot est NOMMÉ, son SENS est LU, la purge est MINUSCULE
Slot 3 = `get_KeepOnChangeOwner`, et `RemoveEffects` retire quand il rend **FAUX**. Or la base rend
**true** : par défaut un effet **survit** au changement de propriétaire. Sur les 244 classes
mesurées, **2** rendent faux — `TauntedEffect` et `HolyDuel_TauntEffect`.
⇒ « ne rien purger » (le port actuel) est correct pour tout le reste ; la dégradation est bien plus
petite qu'annoncée, et le correctif tient en deux classes.

#### `#590-r2` / `#982-r4` — **PORTÉ**, et la mesure a dû changer de SOURCE en chemin

Les « 244 classes mesurées » venaient de la **vtable RUNTIME** (`probe_916r1_effect_slots.py`).
Re-jouée le 2026-08-13, la même mesure rend **53 classes sur 465** et **« AUCUN override »** — un
**faux zéro**, parce qu'IL2CPP ne remplit la vtable qu'à l'**initialisation** de la classe et
qu'aucun taunt n'avait été posé dans cette session. Le probe le dit et range les autres en
`NON MESURÉE` ; il n'empêche que le verdict aurait été « rien à purger ».

La dérivation qui conclut est donc **OFFLINE et complète** — celle de `probe_175r2_can_be_immune_to`,
qui répond à la même forme de question pour l'autre slot d'`IEffect` :

* **QUI DÉCLARE** ← la table des méthodes du type dans `global-metadata.dat`. C'est la seule source
  qui distingue « la classe surcharge » de « le corps est dédupliqué » : `get_KeepOnChangeOwner`
  n'apparaît **nulle part** dans `frida/methods.tsv` (indexée par ADRESSE), et son absence ne
  prouvait rien.
* **QUELLE VALEUR** ← les **OCTETS** du corps dans le bloc `methodPointers` : `b0 01 c3`
  (`mov al,1 ; ret`) = vrai, `32 c0 c3` (`xor al,al ; ret`) = faux.

Résultat : **465** classes couvertes, **0 INCONNU**, **3 déclarants** — `BaseEffect` (vrai) et
exactement `IdunBattle.Entities.Effects.TauntedEffect` + `IdunBattle.Entities.Effects.Loki.HolyDuel_TauntEffect`
(tous deux **faux**). Le chiffre du résidu est donc **confirmé**, par une route qui n'exige ni
session chaude ni vtable. Probe : `scripts/python/probe_982r4_keep_on_change_owner.py`.

**La question laissée ouverte est tranchée** : `ChangeUnitOwnerOperation$$Execute` a été relu en
entier — `RemoveEffects` court **AVANT** la lecture du nouveau propriétaire et l'écriture du slot
d'override, et il n'y a **aucun re-`Apply`** des effets conservés. Rien de plus à porter.

Port : `_remove_effects_on_owner_change` matérialise le domaine **avant** le premier retrait (le
natif fait deux boucles, et le retrait mute la liste du porteur), puis passe par
`remove_effect_instance` = `RemoveEffectOperation$$Execute` — donc avec `On(0x3f)`/`On(0x40)`, les
reverts et la cascade des enfants. Mesuré : les trois sous-effets du taunt (`25`/`26`/`1237`)
partent avec lui, `Stunned` et ses trois enfants restent.

Garde : `tests/engine/test_982r4_keep_on_change_owner_offline.py` (5 tests). **Vue ROUGE** en
retirant la surcharge de `TauntedEffect` : 4 tests tombent, dont
`temoin : l'effet purgeable doit avoir ete REPOSE`.

### `#966-r2` — le canal existe, et le résidu se trompe de lecteur
`combatSnapshot` publie `unitFlagTypes` (dont **`CanHealFullHealthUnits: 23`**) et un canal
`unitFlags` par unité — mesuré en live. « Ni `combatSnapshot` ni `decisionView` ne publient les
flags » est **faux**.
Deux corrections de RE, en plus : le lecteur n'est pas « le `18 Heal` générique » mais
`IdunBattle.Core.Services.AttackQuery$$EntityCanBeHealed` (slot 17 d'`IAttackQuery`, atteint par
TOUTE ability de soin) ; et le flag y est lu **sur le CASTER**, dans une disjonction
`IsDamagedUnit(target) || (removeEffects && HasNegativeUnitEffect(target)) || HasFlag(caster, 0x17)`.
Le poseur n'est pas une Operation — c'est
`IdunBattle.Entities.Behaviours.AddFlagBehaviour$$Execute`, qui mute directement l'`OrderedSet` du
`UnitFlagsComponent` et **rend un résultat d'opérations vide** : écriture ECS **silencieuse**,
invisible de tout flux d'events.
⚠ `unitFlags` a un angle mort **connu et documenté** : il est alimenté sur les unités VIVANTES, donc
aveugle à `UnitFlag.Fled` (#429-r1-r3-r1). Il ne l'est pas pour `23`.

## 3. Les DEUX qui exigent vraiment la fenêtre

| résidu | capteur livré | ce qu'il mesure |
|---|---|---|
| `#969-r1` | `frida/hooks/probes/should-evaluate-trace.ts` | `p` et le tirage de `BasePlaybook$$ShouldEvaluate` |
| `#975-r1` | `frida/hooks/probes/valid-targets-from.ts` | `GetValidTargets(unit, UnitPosition(<tuile arbitraire>), ability)` |

**`#969-r1`** — la porte est `p >= 1 → true ; p <= 0 → false ; sinon NextBool(p)`. `p` ne sort
jamais de `ShouldEvaluate` : on ancre donc AUSSI
`IdunBattle.Utils.PRNG.IntBasedMersenneTwister$$NextBool` (overload **`Fix64`**, slot 4 —
l'overload `int` du slot 5 est un POURCENTAGE, les confondre fausserait tout), et on n'attribue un
tirage que s'il est IMBRIQUÉ dans la porte sur le MÊME thread ; les autres sont comptés à part
(`rngHorsPortee`) et jamais attribués.
Point d'ancrage **mesuré non chaud** : dans
`ActiveAbilityActionGenerator.u003CGenerateActionsu003Ed__7$$MoveNext`, les slots 4 et 5 tirent
**une fois par couple (unité, ability)**, avant toute énumération de tuile. Le slot 6, lui, tire
PAR POSITION — il n'est **pas** ancré (et n'a pas de tirage : c'est un gate `IsTemporary`).

**`#975-r1`** — `IdunBattle.Core.UnitPosition` est un `ValueType` de **8 octets utiles** = un seul
pointeur vers la LISTE des tuiles occupées (pas un couple `(q,r)`). On construit la position par le
ctor NOMMÉ `UnitPosition$$.ctor(this, tile)` — exactement ce que fait
`ExemplarOfTheKauyonPlaybook$$HasEnemyInRange` — plutôt qu'en mutant la liste de `GetTiles`.
⚠ `AttackQuery$$GetValidTargets` (slot 6) porte **trois portes qui rendent VIDE sans erreur** :
`abilityType == 0`, ability absente de l'`ActiveAbilityComponent`, et `IsAlreadyUsedThisTurn`. Un
`count == 0` peut donc venir d'un COOLDOWN, pas de la géométrie — d'où le `control.fromCurrent`
obligatoire, qui doit reproduire `abilityTargets.fromHere`.

## 4. Ce que la mesure a coûté en faux verdicts (deux, tous deux attrapés)

- **Un faux « régime dégénéré »** sur `#959-r1` : la clé d'appariement `(unitId, tile)` réduisait 38
  lignes à 10, puis `(unitId, utility, tile)` à 20 — le delta rendait 0 partout pendant que
  `check_value` voyait 13 lignes basculer. Un agrégat qui perd des lignes ne peut pas montrer
  celles qu'il a perdues. L'appariement est désormais **positionnel**, avec contrôle d'alignement
  qui REFUSE de conclure.
- **Un faux « calibration impossible »** sur `probe_916r1` : `resolveVtableSlot` avance par pas de
  `0x10`, donc partir de `0x100` n'atteint jamais `0x138`. Les deux phases sont balayées.

## 5. Résidus ouverts

`#982-r4` (port du gate `KeepOnChangeOwner`), `#982-r5` (port du `UnitFlag` + `EntityCanBeHealed`),
`#982-r6` (recensement partiel : 221/465 classes non initialisées).
Détail : `docs/rl/backlog.md`.

⚠ Les numéros sont **r4/r5/r6, pas r1/r2/r3** : `probe_468 --suggere 982` a compté r1–r3 comme
PRIS parce que ce fichier même les citait déjà quand l'allocation a eu lieu. Le corpus lit
`docs/rl`, donc **écrire un numéro le consomme** — allouer AVANT de rédiger, ou aligner après.
