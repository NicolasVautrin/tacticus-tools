# #498-r3 — `IsDisplaceable` : le constat disait « 4 conditions, 5 sites, 2 portées ». Re-dérivé : **8 sites, et le 8ᵉ n'en portait AUCUNE**

Le constat d'origine (rapport d'agent du 2026-08-07) n'avait ni ligne de backlog ni case-doc — il
ne vivait que dans une phrase de `docs/rl/dsl-port-attestations.tsv:19`, sous le nom **#498-r2**.
Cette fiche le rétablit comme fait mesuré, le corrige, et le met sous cliquet.

**Ce que le constat disait** : `IdunBattle.Entities.UnitExtensions$$IsDisplaceable` teste **quatre**
conditions ; les **cinq** sites Python du substrat n'en portent que **deux** (`Immovable`,
`BigTarget`).

**Ce que la re-dérivation donne** : les quatre conditions sont exactes, **et il y a une cinquième
lecture** (la tête `EntityType == Unit`) ; le recensement rend **12 sites**, dont **9 miroirs** du
prédicat (7 runner, 2 décision) — et le site que personne n'avait compté,
`SwitchPositionOperation`, **n'en portait aucune**. Un compte hérité se périme ; une liste de cinq
entrées ne peut pas montrer le sixième site.

---

## 1. Le décompilé — relu VERBATIM sur `rnca9r7q6c`

`IdunBattle.Entities.UnitExtensions$$IsDisplaceable(unit)` :

```
if (unit == null)                                        return false;
if (GetEntityType(unit) != EntityType.Unit)              return false;   // iface, slot 1
if (GetBaseUnitComponent(unit) != null
    && BaseUnitComponent.HasTrait(unit, 0x11))           return false;   // Immovable
if (GetBaseUnitComponent(unit) != null
    && BaseUnitComponent.HasTrait(unit, 0x3))            return false;   // Hulking
big = GetBaseUnitComponent(unit) != null
      && BaseUnitComponent.HasTrait(unit, 0x3f9);                        // BigTarget
return !UnitExtensions.HasFlag(unit, 0x19) && !big;              // UnitFlag.Undisplaceable
```

**Qualification des ordinaux** (`data/symbols/<build>/frida/enums.tsv`, jamais devinés —
`probe_498r3_is_displaceable_sites.py` étage 0 les re-confronte) :
`IdunBattle.Entities.Enum.UnitTrait` → `3=Hulking`, `17=Immovable`, `1017=BigTarget` ;
`IdunBattle.Entities.Enum.UnitFlag` → `25=Undisplaceable` ;
`IdunBattle.Entities.Enum.EntityType` → `1=Unit`, `6=Machine`.

**Deux faits que le nom de la fonction ne laisse pas deviner** :

* ⚠ **Il n'y a AUCUNE liveness.** Ni PV, ni `UnitFlag.Dead`, ni appartenance au pool `AliveUnits`.
  Le gate `alive` que portaient les sites du port est une condition **EN PLUS** du natif — direction
  **RESTRICTIVE**. Il est conservé, **hors du foyer**, et nommé au site (§5).
* ⚠ **`0x19` désigne deux choses différentes à deux lignes d'écart.** Dans `IsDisplaceable` c'est un
  `UnitFlag` (`Undisplaceable`) ; dans `IdunBattle.Core.Services.DamagePrediction$$GetKnockback`,
  juste après l'appel, c'est un `UnitTrait` (`Immune`). Le port fusionnait les trois traits dans un
  seul `has_any_trait(traits, (Immovable, BigTarget, Immune))` : **l'écart n'était pas visible à
  l'ordinal**.

Consommateurs natifs (xrefs) : `DisplaceUnitOperation$$Execute` (tête, **avant** le
`switch(direction)` — donc ses 7 cases), `DamagePrediction$$GetKnockback`,
`CanBeDisplacedTrigger$$Evaluate`, `UnstoppableMomentumReworkedAbility$$Push`,
`ArmouredMight_MoveAbility$$Push`, `TargetingQuery$$GetInvalidTargetReason`,
`ItItchesPlaybook$${CanBePushed, EvaluateNonComparable}`,
`Playbook<T>$${GetTargetUtilityDiffOnDisplace, GetPushableTiles}`.

---

## 2. Le recensement — DÉRIVÉ, pas hérité

`python scripts/python/probe_498r3_is_displaceable_sites.py`. Le critère est un test sur le TEXTE
de chaque fonction d'`engine/**` (citation du symbole natif, **ou** test conjoint de `Immovable` et
`BigTarget`), jamais une liste écrite dans le probe. **12 sites**, ventilés par rôle
(MIROIR / CONSOMMATEUR / NON-PORTÉ) — confondre les trois faisait rougir des sites qui n'ont rien à
porter, et c'est ce que la 1ʳᵉ version du probe faisait.

État **AVANT** cette tranche, condition par condition :

| site | face | Immovable | Hulking | BigTarget | Undisplaceable | EntityType |
|---|---|---|---|---|---|---|
| `runner/operations/displace.py::DisplaceUnitOperation.execute` (push) | RUNNER | oui | **non** | oui | **non** | **non** |
| `runner/operations/displace.py::PullUnitOneTileOperation.execute` | RUNNER | oui | **non** | oui | **non** | **non** |
| `runner/operations/displace.py::DirectDisplaceOperation.execute` | RUNNER | oui | **non** | oui | **non** | **non** |
| `runner/operations/displace.py::_apply_knockback_to` (`GetKnockback`) | RUNNER | oui | **non** | oui | **non** | **non** |
| `runner/abilities/loki/momentum.py::_is_displaceable` | RUNNER | oui | **non** | oui | **non** | **non** |
| **`runner/operations/displace.py::SwitchPositionOperation.execute`** | RUNNER | **non** | **non** | **non** | **non** | **non** |
| `playbook/loki_custom.py::MortisRoundPlaybook._is_displaceable` | DÉCISION | oui | oui | oui | **non** | **non** |
| `playbook/noncomparable/it_itches.py::ItItchesPlaybook._is_displaceable` | DÉCISION | oui | oui | oui | **non** | **non** |

Le constat comptait **cinq** sites runner. Il y en a **six** — et le sixième était le seul à ne rien
porter du tout. Il a été raté parce qu'il ne cite ni `Immovable` ni `BigTarget` : **on ne peut pas
trouver par grep un site dont le défaut est une ABSENCE**. C'est le recensement par *consommateur
natif* (`Execute` gate ses 7 cases) qui le fait apparaître, pas le recensement par mot-clé.

---

## 3. Verdict par condition, et le SENS de chaque dégradation

| condition | portée avant | direction | verdict |
|---|---|---|---|
| `EntityType == Unit` (tête) | **0 site / 8** | **PERMISSIF** (le port déplacerait une `EntityType.Machine`) | **PORTÉE** (§4). **INERTE mesurée** : une MoW est matérialisée sans `PositionComponent` (`snapshot._load_machines`), donc les trois `execute()` sortent en `no position` avant le gate. Mais aucun **trait** ne l'arrêtait : les **8 MoW** du seed BC ne portent ni `BigTarget` ni `Immovable`. |
| `!HasTrait(Immovable=0x11)` | 8/8 | — | déjà conforme |
| `!HasTrait(Hulking=0x3)` | 2/8 (décision seule) | **PERMISSIF** | **PORTÉE**. **INERTE par ABSENCE DE PORTEUR, mesurée** : `Hulking` = **0 occurrence** dans `gameconfig.json` et **0** sur les 175 unités de `data/seed-bc.json` (idem `Immovable`, pourtant porté depuis toujours). Le canal `BC.Units[].Traits` pourrait néanmoins en publier un — il diffère du kit **dans les deux sens** (#264) — donc l'inertie est un **état du build**, pas une propriété. |
| `!HasTrait(BigTarget=0x3f9)` | 7/8 (tous sauf `SwitchPosition`) | **PERMISSIF** sur `SwitchPosition` | **PORTÉE — et la seule qui MORD, confrontée LIVE (§6)** |
| `!HasFlag(Undisplaceable=0x19)` | **0 site / 8** | **PERMISSIF** | **PORTÉE** côté runner. **INERTE dans l'état actuel du port** : le flag n'a qu'**un** écrivain — les `AddFlag`/`RemoveFlag` qui encadrent la charge de 1152 (`momentum.py::_set_charge_flag`) — et il ne porte donc que sur le **caster**, que ses propres gates n'évaluent jamais. Il mordrait dès qu'un déplacement viserait ce caster **pendant** sa charge (trigger de riposte, overwatch qui pousse l'attaquant). |
| gate `alive` **en plus** | 5/8 | **RESTRICTIF** | **CONSERVÉ, hors foyer, nommé** (§5) |

---

## 4. Le fix — UN foyer, six lecteurs

`scripts/python/engine/runner/components.py::unit_extensions_is_displaceable(entity)`, posé à côté
d'`unit_extensions_is_alive` (même famille `UnitExtensions`, même discriminant `MachineComponent`
pour `EntityType.Machine`). Substrat de traits = `entity_trait_names` (le FOYER : kit gameconfig +
traits **accordés en bataille** + pseudo-trait d'alliance), pas `sc.ctx.traits` brut.

Les six sites runner y délèguent : les quatre `execute()` de `displace.py` (dont
**`SwitchPositionOperation`, qui n'avait rien**), `_apply_knockback_to`, et
`momentum.py::_is_displaceable`. **Pourquoi un foyer et pas six correctifs** : les six copies
étaient libres de diverger, et elles avaient divergé — deux d'entre elles portaient trois traits,
quatre en portaient deux, une n'en portait aucun. Le cliquet (§7) interdit d'en réécrire une.

---

## 5. Le gate `alive` : conservé, hors foyer, et NOMMÉ

Le natif ne teste aucune liveness. Le port en a une aux trois `execute()` de push/pull/direct et
dans `momentum::_is_displaceable`. Elle est **conservée** : ce n'est pas un oubli à corriger au
passage, c'est un comportement déjà livré, déjà ventilé `INERTE-VIVANT` par
`case-462-…-substrat-traits-inventaire`, dont le retrait changerait le comportement de **tous** les
push sans qu'aucune mesure de cette tranche ne l'établisse. Elle est donc **sortie du foyer** et
**écrite au site** avec sa direction (RESTRICTIVE).

`SwitchPositionOperation` ne l'a **pas**, et c'est délibéré : le natif y traite la mort
**explicitement**, `HasFlag(u, UnitFlag.Dead)` moitié par moitié — c'est déjà porté, et y ajouter un
gate `alive` créerait une divergence neuve. Le test étage 5 verrouille les deux faits ensemble.

---

## 6. La confrontation LIVE — le natif REFUSE, le port d'avant ACCEPTAIT

`probe_498r3_switch_position_gate.py` / `test_498r3_switch_position_gate_live.py`.
Board `MC1_67`, seed 49831, montage #287 (`thousTzaangor` Yazaghor + allié Psyker `thousSorcerer`).

Le consommateur exercé est `SorcerousFacade_SwitchAbility$$CreateBehaviour` =
`SwitchPosition(Caster@0x48, Target@0x60)` → `DisplaceUnitBehaviour(direction = 5,
displacingUnit = Caster, displacedUnit = Target)`, donc le `target` que la tête gate **est l'allié
visé par le cast**. Le port collapse le `TriggerAbilityDelayed` inline : l'échange est observable
**dans** le cast, live comme offline (mesure #287).

**Ce qui rend la condition ATTEIGNABLE** : l'allié du montage ne porte aucun des trois traits
refusants. On lui **ajoute** `BigTarget` dans `BC.Units[].Traits` par un seed BC custom
(`--seed-bc`) — le canal que `snapshot._load_unit_traits` lit. Sans cette écriture, la condition
serait trivialement satisfaite et l'accord ne prouverait rien.

| bras | traits natifs de l'allié (`combatSnapshot.units[].traits`) | natif | port corrigé | **mutant** (foyer → `True` = état d'avant) |
|---|---|---|---|---|
| `base` | `[4, 16, 1002, 1041, 2026]` | **ÉCHANGE** `(1,0) ↔ (0,4)` | échange | échange |
| `big` | `[4, 16, 1002, **1017**, 1041, 2026]` | **N'ÉCHANGE PAS** | n'échange pas | **ÉCHANGE** |

Le bras `base` est le **témoin non dégénéré** : sans lui, un refus systématique passerait pour un
gate qui marche. Le mutant est l'**A/B causal** : il interdit d'attribuer l'accord du bras `big` à
autre chose que ce gate. `1017` est bien **lu par le natif** (présent dans le seul bras `big`) — une
écriture de seed BC silencieusement perdue aurait rendu les deux bras identiques.

⇒ **Réponse au critère** : oui, il existe un état de jeu, atteignable et monté, où le natif refuse
un déplacement que le port autorisait.

---

## 7. Les cliquets

* `probe_498r3_is_displaceable_sites.py` — étage 0 : les six ordinaux nomment-ils encore la même
  chose dans `enums.tsv` ; étage 1 : recensement **dérivé** ; étage 2 : **aucune copie du prédicat
  hors du foyer**, côté runner, et aucun miroir runner incomplet ; étage 3 : ce qui n'est **pas**
  couvert, imprimé au lieu d'être rabattu sur un zéro.
* `test_498r3_is_displaceable_offline.py` — 23 tests, 6 étages. Les ordinaux sont **figés au site**
  (`probe_313` compare le *mirror* au *build* et redeviendrait vert après un renumérotage ; ce cran
  garde la valeur **mesurée à la conversion**). L'étage 4 est la **contre-épreuve** : on réintroduit
  dans un arbre témoin la forme exacte d'avant, et le recenseur DOIT rougir — sans elle l'étage 3
  serait un vert qui ne prouve rien.
* `test_498r3_switch_position_gate_live.py` — 4 tests, les trois bras du §6.

**Vérification que les gardes MORDENT** (2026-08-07) : quatre mutations appliquées au foyer, une par
condition — retrait de `Hulking` : 3 rouges ; neutralisation du flag : 4 rouges ; neutralisation de
la tête `MachineComponent` : 1 rouge. La 3ᵉ tentative de mutation avait d'abord frappé
**`unit_extensions_is_alive`** (même ligne à l'octet près, 40 lignes plus haut) et le fichier
restait vert : une mutation qui ne mord pas au bon endroit est un faux négatif de contre-épreuve.

---

## 8. Ce qui N'EST PAS couvert

* **Face DÉCISION** — les deux miroirs (`MortisRoundPlaybook`, `ItItchesPlaybook`) portent les trois
  traits mais **pas** `Undisplaceable` ni la tête `EntityType` : leur substrat (`Scene` /
  `NCContext`) ne publie que **quatre** `UnitFlag` (`Moved`, `Teleported`, `ActiveAbilityUsed`,
  `PreventOverkill`). Résidu **#498-r4**. Direction : PERMISSIVE, mais l'écrivain unique du flag
  l'encadre à l'intérieur d'**une seule** exécution d'ability — il n'est donc jamais posé au moment
  où la décision évalue.
* **`TargetingQuery$$GetInvalidTargetReason`** appelle `IsDisplaceable` : c'est la règle de ciblage
  **18 `TargetIsDisplaceable`** (`0x40000`), recensée `NON (0 porteur)` dans
  `runner/abilities/targeting.py`. Non portée, **hors de cette tranche** — le probe la range en
  `NON-PORTE` et l'imprime.
* **Les autres consommateurs natifs** (`ArmouredMight_MoveAbility$$Push`,
  `Playbook<T>$$GetPushableTiles`, `$$GetTargetUtilityDiffOnDisplace`) n'ont pas de site porté :
  rien à corriger, rien à garder.
* **Le gate `alive`** reste une divergence RESTRICTIVE assumée (§5) — non levée, nommée.
* **Le recensement ne voit qu'`engine/**`** : un miroir écrit dans un probe ou un test lui échappe
  (`probe_27_r3_mortis_round_ab.py` MUTE le site de décision au lieu d'en écrire un — c'est
  correct, mais c'est une frontière du recenseur, pas une absence).
* **`Hulking` et la tête `EntityType`** ne sont exercés qu'**offline** : aucun porteur (`Hulking`) /
  aucune MoW positionnée (`EntityType`) ne permet de les confronter live sur ce build.
