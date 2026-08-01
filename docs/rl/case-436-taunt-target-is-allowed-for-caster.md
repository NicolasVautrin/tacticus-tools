# #436 — `TargetIsAllowedForCaster` : la règle du TAUNT, armée chez 59 abilities et par l'attaque normale

**Livré le 2026-08-01.** Build de référence : `rnca9r7q6c`.

## 1. La règle, relue verbatim

`IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason` (surcharge **7 arguments**), juste
après `TargetIsEnemy` et avant `TargetIsDisplaceable` :

```
if ((rules >> 0xe & 1) != 0 || (rules >> 0x39 & 1) != 0) {     // TargetIsEnemy | TargetIsCasterOrEnemy
    if ((rules >> 0x28 & 1) == 0) {                            // !AllowIgnoreForcedAttackTarget
        list = UnitExtensions.GetOnlyTargets(caster);          // null -> NRE
        if (0 < list.Count) {
            found = false;
            foreach (id in list) { if (id == EntityId(puVar12)) found = true; }
            if (!found) -> broken(0x800000);
        }
    }
}
```

Trois gates **dans cet ordre** — armement, désarmement, `Count > 0`. Une liste vide (le cas de toute
unité non tauntée) ne refuse rien : c'est ce qui rend la règle invisible tant qu'aucun taunt n'est
posé, et permissive quand elle manque.

**Son bit 23 n'est jamais testé** : il n'est que le code rendu. D'où le « 0 porteur » qu'affichait
tout recensement par le bit (#429) alors que **59** abilities du registre l'arment — plus
l'**ATTAQUE NORMALE**, dont le preset vaut `0x4002` (`TargetIsEnemy | TargetMatchesDynamicRule`).
C'est ce canal-là qui porte la mesure, parce que le taunt ferme les abilities actives du taunté par
un autre chemin (`Taunted_CantUseAbility`, effet 26).

La cible comparée est `puVar12`, la cible **résolue par la tête de domaine** (tuile sous
`TargetIsTile`, machine sous `TargetIsMachine`, sinon `GetUnit(target)` — qui résout une tuile en son
occupant), pas la cible d'origine. Porté par `_resolved_target_id` (`abilities/targeting.py`), volet
RÉSOLUTION de la même tête dont `get_target_domain_broken_rule` portait déjà le volet REFUS.

## 2. Qui écrit la liste — quatre écrivains, un seul confrontable

`IdunBattle.Entities.UnitExtensions$$GetOnlyTargets(unit)` lit un `ForcedAttackTargetsComponent`
(champ `List<int>` @+0x50), sous un gate `OwnerComponent$$IsOverridden`.

| écrivain natif | effet sur la liste | porté |
|---|---|---|
| `IdunBattle.Entities.Effects.TauntedEffect$$ApplyInternal` | `:= [ABondEffect.BondedEntityId]` (**remplace**) | **oui** (#436) |
| `TauntedEffect$$RevertInternal` | `:= []` | **oui** |
| `AddForcedAttackTargetBehaviour$$Execute` | `Add` incrémental | non — unique constructeur `InstinctiveBehaviour_UpdateTargetAbility$$CreateBehaviour`, 23 porteurs, tous summons Tyranides |
| `RemoveForcedAttackTargetBehaviour$$Execute` | `Remove` | oui (`RemoveAllForcedAttackTargets`, 1011/1023) |

Le TAUNT est donc l'effet **27 `Taunted_OnlySpecificTargets`**, et deux abilities **portées** le
castent : `CrushingClaws` (1105, `tyranTyrantGuard` — HÉROS du pool) et `GetEmRuntz` (1045). Les deux
call-sites passent le **5e argument** `bondedEntity` d'`IdunBattleLogic.Entities.DSLBehaviors$$AddBondEffect`
(le tauntant : `<sel +0x48>` pour 1105, `child` pour 1045) — le port ne le renseignait **pas**, donc
sa liste serait restée vide. Deux autres chemins natifs posent le même effet 27 et ne sont **pas**
portés : `TauntAbility$$CreateBehaviour` (`AddBondEffect(0x1b, …, Enemies(AdjacentUnits(caster)), …,
Direct(2))` ; `ActiveAbilityType.Taunt` = 4, **0 porteur** sur les 5 voies gameconfig) et
`IdunBattle.Entities.Effects.Loki.HolyDuel_TauntEffect$$ApplyInternal` (effet 1091, qui ajoute **deux**
sous-effets 27 — un par duelliste ; `unit_map find --ability HolyDuel` : 6 unités, dont le lineup
`templChampion`).

## 3. Le lien effet → écriture, et pourquoi il n'est pas une mutation nue

Côté natif, l'invariant « effet 27 retiré ⇒ liste vidée » tient parce que **tout** retrait passe par
`DeactivateEffect -> RevertInternal`. Côté port, un effet disparaît par plusieurs chemins
(`remove_effect_instance`, l'expiration de timer d'`EffectsState.on_turn_end`, une poignée de
`consumed = True` ad hoc) dont un seul est un foyer. Une mutation posée au seul foyer serait
désynchronisée — et une liste fantôme fait **refuser** un cast que le natif accepte, dégradation
RESTRICTIVE, l'inverse de la convention permissive de tout ce module.

`ForcedAttackTargetsComponent` porte donc `written_by` (l'instance d'effet écrivain) et son `get()`
rend `[]` dès que cet effet est `consumed` : le `RevertInternal` est rendu quel que soit le chemin de
retrait. `clear()` (le `Remove` de `RemoveAllForcedAttackTargets`) **délie** l'écrivain — sans quoi la
liste repousserait alors que le natif n'a aucune ré-écriture.

**Écart nommé** : `RevertInternal` natif vide la liste entière, y compris ce qu'un `Add` de la voie 3
y aurait mis ; ici seule l'écriture de cet effet est annulée. Aucun porteur (les deux voies ne
coexistent nulle part offline).

**Non porté, nommé** : le gate `OwnerComponent$$IsOverridden` (`owner+0x14 != 0`, le champ
`OverriddenPlayerEntityId` du mind control). Le port n'a que le CURRENT owner (`OwnerComponent.player`),
sans distinguer original et override. Une unité à la fois mind-contrôlée et tauntée verrait le port
maintenir une restriction que le natif lève — dégradation restrictive, sans porteur offline (aucun
écrivain d'override d'owner hors capture).

## 4. La confrontation — `probe_436_taunt_targeting.py`, trois étages

Montage : `tyranTyrantGuard` amené au **contact** d'un `necroWarden`, `ultraCalgar` amené au contact
**aussi**. Ce second contact est load-bearing : `necroWarden` est RANGED, et un caster ranged adjacent
à un ennemi est clampé en mêlée (`forceMeleeTarget = IfRangedCaster` du preset d'attaque normale) — à
d=2, le natif rendait déjà `TargetIsInRange` avant tout taunt, et la ligne cessait de montrer la
**permissivité** (elle restait discriminante : le taunt la faisait passer à `0x800000`, ce qui prouve
au passage que la règle 23 précède le volet portée).

| cible | d | natif AVANT | natif APRÈS | port AVANT | port APRÈS | bit 40 |
|---|---|---|---|---|---|---|
| `tyranTyrantGuard` (le TAUNTANT) | 1 | `0x0` | `0x0` | `0x0` | `0x0` | `0x0` |
| `ultraCalgar` (l'AUTRE ennemi) | 1 | `0x0` | **`0x800000`** | **`0x0`** | **`0x800000`** | `0x0` |
| les 4 `necroWarden` (alliés + soi) | — | `0x4000` | `0x4000` | `0x4000` | `0x4000` | `0x4000` |

Accord natif/port **6/6** ; une ligne refusée `TargetIsAllowedForCaster` que le port **acceptait**
avant la tranche ; le tauntant reste légal. Les étages :

* **A — vecteur de pose** (offline) : l'arbre `crushing_claws_tree` rejoué par le port produit
  `get_only_targets(taunté) == [caster]`. C'est ce qui garde le `bondedEntity` du call-site.
* **B — la règle** (live) : le tableau ci-dessus.
* **C — désarmement** : `AllowIgnoreForcedAttackTarget` (bit 40) posé sur le masque lève le refus.
  **NON CONFRONTÉ** au natif : aucune ability du registre ne pose ce bit, aucun cast live ne l'exerce.

Garde : `tests/engine/runner/test_taunt_targeting_live.py` (7 tests, ~22 s).

## 5. Résidus nommés

* **#436-r1 — le canal de capture ne publie pas le `bonded`.** `frida/hooks/game/effects.ts`
  (`readEffect`) lit `EffectComponent.SourceUnitId @+0x10` et `OwnerId @+0x14`, **pas** le
  `BondComponent` de l'entité-effet (`+0x10 = bondedEntityId`, ce que relit
  `IdunBattle.Entities.Effects.ABondEffect$$BondedEntityId`). Conséquence : un état reconstruit
  **depuis un snapshot natif** est aveugle à un taunt posé par le jeu — le port ne voit la
  restriction que quand c'est LUI qui a posé l'effet. Le point d'ancrage est nommé, le capteur
  demande une fenêtre de reinject. Pour les quatre producteurs lus, `bondedEntityId == source de
  l'effet` ; hydrater par `source` serait une **déduction**, pas une lecture — non fait.
* **`AllowIgnoreForcedAttackTarget` non confronté** (§4, étage C) — 0 porteur au registre.
* **`OwnerComponent$$IsOverridden` non porté** (§3).
* **Trouvé en chemin** : `probe_429_targeting_rule_inventory.py` levait un `KeyError` dans son mode
  par défaut — la clé de `rendues` est le CODE rendu, pas le nom de la règle, et les deux diffèrent
  pour `TargetIsTile` (qui rend `ValidRequest`). Le sélecteur employait déjà `code(n)`, l'affichage
  non. Corrigé ; le dernier bloc du probe ne s'était donc **jamais** imprimé.

## 6. Re-dériver

```
python scripts/python/probe_436_taunt_targeting.py
python scripts/python/probe_429_targeting_rule_inventory.py --only-gaps
python -m pytest tests/engine/runner/test_taunt_targeting_live.py -q
```

Après cette tranche, `probe_429` compte **24** règles GATE non portées sur 46 (contre 25), les deux
gisements restants étant la ligne de vue (`TargetIsUnobscured`, 103 abilities) et
`TargetIsNotSteppable` (83). ⚠ Chiffres à re-dériver, pas à citer.
