# case-224 / #208 — Gate d'IMMUNITÉ d'effet, et l'étage qu'on confondait avec lui

**Statut** : CLOS. Le gate d'immunité (`BaseEffect$$EntityIsImmuneToEffect` + `get_CanBeImmuneTo`) est
porté et validé live ; l'étage `CreateActiveCondition`, longtemps collapsé dans ce gate, l'a été aussi
(#208, 2026-07-28) — le collapse est DÉFAIT et son trou de câblage refermé.
**Touche** : TOUS les vecteurs de pose d'effet — l'unique feuille `AddEffectOperation` — et TOUS les
lecteurs d'effets actifs (`EffectsState.active_effects`).

> **Le fait central, si on ne lit qu'une ligne** : `TerminatorArmour` n'a **jamais** empêché la pose de
> `Pinned`. Le natif POSE l'effet et le laisse **inerte** (`IsActive = false`). Le canal
> `decisionView` par DÉFAUT droppe les effets inactifs — c'est ce filtre, pas le jeu, qui faisait lire
> un refus. `decisionView { includeInactive: true }` le montre en une ligne.

---

## 1. L'artefact natif

### 1.1 Le CONSOMMATEUR — où le gate mord

`IdunBattle.Operations.AddEffectOperation$$Execute`, dans l'ordre exact du décompilé :

```
def = EffectsDatabase.Get(effectType)              # interface IEffectsDatabase slot 0
On(PreEffectAdded = 0x3e)                          # message émis AVANT tous les gates
if (target == 0)                       -> log "couldn't apply, no target" ; return 0
if (def.EntityIsImmuneToEffect(target)) -> return 0            # <<< LE GATE
if (IsUnit(target) && HasFlag(target, 6 = Dead)) -> log ; return 0
duration = ... ; UpdateExistingEffect(...) ; AddNewEffect(...)
```

L'appel est une **invocation d'interface** `IEffect` slot 40 — la même que celle de
`IdunBattle.Core.Services.BattleQuery$$IsUnitImmuneTo`, dont le corps entier est
`EffectsDatabase.Get(effectType).<slot 40>(unit)` : c'est ce doublon qui NOMME le slot.
Vérification indépendante de l'offset d'interface (`interfaceOffsets(IEffect) = 4`, entrée de vtable
`i` à `klass + 0x138 + i*0x10`) sur trois slots consommés ailleurs dans le même fichier :
slot `0xb` → `ShouldBeActive`, slot `0xc` → `ShouldRefreshForTrigger`, slot `5` →
`get_AlwaysCreateOneEntityPerEffect` (lu par `UpdateExistingEffect`, sémantiquement parlant).

**Conséquence observable** : le gate est vrai ⇒ **aucune entité-effet, aucun événement d'ajout**.
Ce n'est PAS « posé puis désactivé ».

### 1.2 La BASE — le prédicat

`IdunBattle.Entities.Effects.BaseEffect$$EntityIsImmuneToEffect` (octets relus, pas seulement le
pseudo-C) :

```
mov  edx, 0x19                      ; UnitTrait.Immune = 25
call UnitExtensions.HasTrait        ; HasTrait(entity, Immune)
test al, al ; je -> return false
mov  rax, [klass + 0x4e8]           ; vtable slot get_CanBeImmuneTo
call rax                            ; this.CanBeImmuneTo
setne al ; return
```

soit `EntityIsImmuneToEffect(e) = HasTrait(e, UnitTrait.Immune) && this.CanBeImmuneTo`.

`UnitExtensions$$HasTrait` → `BaseUnitComponent$$HasTrait` : trois `OrderedSet<UnitTrait>` —
`+0x50` (retirés, prioritaire), `+0x40` (base), `+0x48` (temporaires, `AddTraitOperation` avec
`isTemporary`). Entité sans `BaseUnitComponent` (tuile) ⇒ faux.

### 1.3 `get_CanBeImmuneTo` — le drapeau par classe

Virtuel de `BaseEffect`, corps de base = stub partagé `return 0` ⇒ **faux par défaut**.

⚠ **Aucun `get_CanBeImmuneTo` n'apparaît dans `data/symbols/<build>/frida/methods.tsv`** (une seule
ligne, `NoneEffect`) : IL2CPP **partage** les corps triviaux `return 0` / `return 1` et le dump est
keyé par RVA — toutes les surcharges collapsent sur une seule ligne. Le seul inventaire fiable est la
lecture de la **vtable RUNTIME par classe**, en matchant le NOM de la méthode et non un offset fixe
(le bloc des virtuels de classe est décalé par le nombre d'interfaces implémentées) :
`scripts/python/probe_224_can_be_immune_to.py`.

**Inventaire complet (442 classes de `IdunBattle.Entities.Effects.*`) — `CanBeImmuneTo == true` :**

| classe d'effet | portée dans `engine/` |
|---|---|
| `PinnedEffect` (1065) | ✅ `entities/effects/loki/status.py` |
| `ContaminatedEffect` (1244) | ✅ `entities/effects/loki/status.py` (créée par #224) |
| `FireEffect` | ❌ non portée |
| `IceEffect` | ❌ non portée |
| `BlockEnteringUnitsTileEffect` | ❌ non portée |
| `BlockTileMovementEffect` | ❌ non portée |
| `ContagionsOfNurgle_ArmorReduction_Effect` | ❌ non portée |

Recoupement i2 du trait `Immune` : « immune to special hexes and hex effects, and cannot have its
Armour, hits, Movement or Range reduced » — exactement ces 7 (hexes = Fire/Ice/BlockTile*/Contaminated,
Movement = Pinned, Armour = ContagionsOfNurgle_ArmorReduction). Les autres clauses du même i2 (« cannot
be Stunned, Suppressed or Taunted ») passent par des gates PAR ABILITY (cf. case-219 : `If(Not(HasTrait(
Target, 25)), …)`), pas par ce canal : `StunnedEffect` / `TauntedEffect` ont `CanBeImmuneTo == false`.

### 1.4 Les surcharges de `EntityIsImmuneToEffect`

`search_symbols_by_name EntityIsImmuneToEffect` → **2 fonctions dans tout le binaire** :

- `IdunBattle.Entities.Effects.BaseEffect$$EntityIsImmuneToEffect` (§1.2) ;
- `IdunBattle.Entities.Effects.Loki.ContaminatedEffect$$EntityIsImmuneToEffect` =
  `HasTrait(e, 0x7eb = 2027 = ContagionsOfNurgle) || UnitExtensions.IsMechanical(e) || base(e)`.

L'inventaire est donc CLOS : aucune autre classe n'override le prédicat.

---

## 2. Ce qui est porté

**Canal DÉCLARATIF (part DATA, `entities/effects/`)** :

- `BaseEffect.can_be_immune_to` — attribut de classe simple (pas de field dataclass ⇒ surchargeable
  par la MRO), défaut `False` = mirror du stub `return 0` ;
- `BaseEffect.entity_is_immune_to_effect(trait_names)` — mirror 1:1 de §1.2 ;
- `PinnedEffect` : `can_be_immune_to = True`, **AUCUNE surcharge d'`entity_is_immune_to_effect`**
  (l'inventaire §1.4 est clos : le binaire n'en a que 2, `BaseEffect` et `ContaminatedEffect`) ;
  son `TerminatorArmour` vit dans `is_active` = `CreateActiveCondition` (§4) ;
- `ContaminatedEffect` (classe NEUVE) : `can_be_immune_to = True`, surcharge
  ContagionsOfNurgle | Mechanical | base — **vrai override natif**, à ne pas confondre avec le
  collapse retiré de `PinnedEffect`.

**Résolution de l'effet-DEF** : `EffectFactory.effect_def(effect_type, name)` — mirror
d'`EffectsDatabase.Get(effectType)`. Le registre du port est keyé par NOM d'EffectType (c'est ce que
threadent les vecteurs de pose) ; nom absent ou classe non portée ⇒ `BaseEffect` ⇒ `can_be_immune_to`
faux ⇒ **jamais immune** : un effet non porté n'invente aucune immunité.

**Façade IMPÉRATIVE (part runner)** : `engine/runner/operations/effects.py::entity_is_immune_to_effect`
= mirror de `BattleQuery$$IsUnitImmuneTo`. Seule part impérative : lire les traits de la cible
(`StatsComponent.ctx.traits`). Deux consommateurs, une seule porte :

1. `AddEffectOperation.execute` — **au stade natif exact** (après le message pre-add et le gate
   cible-nulle, avant le gate cible-morte et avant toute matérialisation) ;
2. `ContaminatedTileEffect` (`operations/triggers/effect_triggers.py::_is_immune_to_contaminated`),
   qui portait la même liste de traits **EN DUR** — fork « 1 nœud natif → 2 portes offline »
   supprimé (doctrine `check-own-port`). Un test de garde interdit sa réintroduction.

**Corrections de lecture au passage** : l'en-tête d'`operations/effects.py` étiquetait ce gate
« déjà-présent (query 0x28 def↔cible) » — c'était FAUX, c'est le gate d'immunité.

---

## 3. Mesure live (ce que fait le natif)

Runner isolé, board `MC1_67`, seed 112112 (`scripts/python/probe_224_effect_immunity.py`).

**Montage discriminant PUR** — `SentinelDirectives` (1139, `admecDestroyer`) : `(InformWeapon +
Attack) + AddEffect(Pinned)`, aucune branche conditionnelle, aucune élection d'attaquant.

| cible | traits | groupe `AddEffect` Pinned | `decisionView.effects` |
|---|---|---|---|
| `blackAbaddon` | Chaos, Hero, LetTheGalaxyBurn, Resilient, **TerminatorArmour** | **absent** | **pas de 1065** |
| `blackPossession` | Chaos, Hero, LetTheGalaxyBurn, Psyker | présent (`entity=100 source=Pinned`) | `1065 Pinned rem=2` |

L'attaque, elle, a lieu dans les DEUX cas (dégât 903 / 3109) : seule la pose de `Pinned` diffère.

> ⚠ **L'inférence tirée de ce tableau était FAUSSE, et c'est le cœur du cas.** On lisait « aucun
> événement d'ajout ⇒ l'opération a **abandonné**, l'effet n'est pas posé-mais-inactif ». Le pas de
> trop : un effet **inactif n'applique aucune modification**, donc n'émet **aucun** groupe
> d'événement — l'absence d'événement ne distingue pas « pas posé » de « posé et inerte ». Réfuté
> par mesure directe le 2026-07-28, cf. §4 **et §4bis** (où le MÊME montage, relu avec
> `decisionView { includeInactive: true }`, affiche l'effet 1065 avec `active: false`).
> La colonne « `decisionView.effects` » de ce tableau est le canal ACTIF-ONLY — elle ne dit pas
> « pas d'effet », elle dit « pas d'effet ACTIF ».

**GÉNÉRALISATION** (`--generalise`) — 2e porteur du trait, autre faction, **sans** `Resilient` (⇒ ce
n'est pas un artefact de `blackAbaddon`), et 2e contrôle :

| cible | traits | groupe Pinned | HP avant→après (vivante) |
|---|---|---|---|
| `deathTyphus` | …, **TerminatorArmour** | **absent** (seuls `TerminatorArmour_Visual`/`_ReduceDmg`, consommés) | 12047 → 11144 |
| `blackObliterator` | Chaos, BigTarget, Daemon, HeavyWeapon, SuppressiveFire | présent | — |

(`blackTerminator` a été écarté : son `TeleportStrike_TeleportingIn` le rend inciblable au tour 1.)

**Montage de la MESURE #112** — `ExemplarOfHate` (1140, `darkaAsmodai`) : même dichotomie sur les
mêmes deux cibles (`ExemplarOfHate_Target` 1293 posé dans les deux cas, `Pinned` seulement sur la
cible sans le trait).

---

## 4. `TerminatorArmour` ↔ `Pinned` : il n'y a JAMAIS eu de refus de pose

**RÉSOLU le 2026-07-28 par mesure directe** (hook `frida/hooks/features/effect-immunity-observe.ts`,
session 15, même montage `sentinel` qu'en §3). Le discriminant est le couple de compteurs
`AddEffectOperation$$Execute` vs `BaseEffect$$EntityIsImmuneToEffect` :

| observable, cast `SentinelDirectives` sur `blackAbaddon` | valeur mesurée |
|---|---|
| `AddEffectOperation$$Execute(effectType=1065 Pinned)` appelé | **oui** |
| son abandon (valeur de retour nulle) | **NON** — retval non nul, une entité-effet EST allouée |
| `EntityIsImmuneToEffect` appelé sur `PinnedEffect` | oui, **retour `false`** |
| `HasTrait(blackAbaddon, 0x19 = Immune)` | **`false`** |

Donc **le gate d'immunité n'a rien refusé** : la pose ABOUTIT, et c'est bien l'`ActiveCondition` qui
rend l'effet inerte — exactement la lecture (2) que §3 avait écartée sur une inférence fautive.

L'étage natif complet, du haut vers le bas :

1. `IdunBattle.Entities.Effects.Loki.PinnedEffect$$CreateActiveCondition` =
   `Not(DSLFactory.HasTrait(Self, 0x40f = 1039 = UnitTrait.TerminatorArmour))` — cohérent avec l'i2
   (« This unit cannot be Suppressed ») et avec `case-74-suppressivefire.md` §54.
2. `IdunBattle.Entities.Effects.BaseEffect$$CreateActiveConditionAndCache` construit cet arbre **une
   seule fois** et le mémoïse dans le champ de l'effet à `+0x90` (slot de vtable `+0x518`).
3. `IdunBattle.Operations.RefreshEffectsOperation$$ShouldBeActive` **évalue** l'arbre et rend le
   booléen d'activation. Sa structure, dans l'ordre :
   - un paramètre de FORÇAGE (`1` ⇒ actif, `2` ⇒ inactif, autre valeur non nulle ⇒
     `ArgumentOutOfRangeException`) ;
   - un verrou en `EffectComponent+0x5e` : s'il est posé, **inactif** sans rien évaluer ;
   - **pas d'arbre** (ou pas d'implémentation de l'interface) ⇒ le flag COURANT `+0x5c` est conservé
     tel quel ;
   - sinon l'arbre est évalué contre un contexte de 0x130 octets, et son résultat est rendu.

`+0x5c` est le flag `EffectComponent.IsActive` déjà porté par #138 : ce n'est donc pas une donnée
neuve, c'est **son producteur** qui manquait.

Pistes écartées à l'époque, et qui restent justement écartées — elles cherchaient toutes un refus qui
n'existe pas : `AddEffectBehaviour$$Execute` (ne filtre que `HasFlag(target, Dead)`), les 4
surcharges de `DSLFactory$$AddEffect`, `OperationProcessor$$AddEffect`, `UpdateExistingEffect`, un
`AddTrait(Immune)` quelque part (aucun call-site).

### 4bis. Le RECOUPEMENT indépendant — `decisionView { includeInactive: true }`

Le hook ad hoc de #151 n'était pas nécessaire, et l'instrument existait depuis `d9d0008` :
`readEffectsByUnit` (`frida/hooks/game/effects.ts`) **droppe** par défaut les effets dont
`EffectComponent.IsActive @+0x5c` est faux, et le publie tel quel sous `includeInactive`.
Même montage `sentinel`, `probe_208_pinned_inactive.py` :

| cible | `decisionView` (défaut) | `decisionView includeInactive` | menace de la cible, `exposureView` reachDmgMax |
|---|---|---|---|
| `blackAbaddon` (TerminatorArmour) | pas de 1065 | **1065 `active: false`** | 1626 → **1626** (ratio **1.0**) |
| `blackPossession` (contrôle) | 1065 | 1065 `active: true` | 2895 → **2026** (ratio **0.6998** = ×0.70) |
| `deathTyphus` (TerminatorArmour, DeathGuard) | pas de 1065 | **1065 `active: false`** | 3251 → **3251** (ratio **1.0**) |

`exposureView` (attaque NORMALE seule) donne le dégât que la cible peut infliger, calculé par le
prédicteur NATIF : c'est la moitié « aucun nombre ne change » du critère, mesurée sans RNG.
`PinnedDmgReductionPct` = 30 ⇒ ×0.70, retrouvé **exactement** sur le contrôle et **absent** sur les
deux porteurs du trait.

**État du port (#208, ce commit)** — le collapse est DÉFAIT, et le trou qui l'imposait est refermé :

- `PinnedEffect.entity_is_immune_to_effect` **supprimée** (l'inventaire §1.4 est clos : le binaire
  n'a que 2 corps, aucun pour `PinnedEffect`). Reste `is_active` = mirror littéral de la
  `CreateActiveCondition`, et `can_be_immune_to = True` (le trait `Immune`, lui, immunise bien).
- **Le `unit_state` a désormais UN SEUL constructeur.** Le collapse existait parce que chaque
  appelant d'`active_effects` bricolait son `{"hp": ...}` : toute clé ABSENTE dégrade son prédicat en
  VRAI, donc `Pinned` restait actif et posait un ×0.70 fantôme. Foyer unique :
  `runner/components.py::unit_state_for_effects` (vue Mapping PARESSEUSE sur l'ECS — `hp`, `max_hp`,
  `traits`, `enemy_psykers_alive`, ce dernier calculé seulement s'il est LU, car `active_effects` est
  appelé dans des boucles par-porteur) et son pendant prédiction `Scene.unit_state`.
  `refresh_effects._unit_state` / `_enemy_psykers_alive` y délèguent (le corps a migré dans
  `components.py`, qui n'importe que `state` — donc aucun cycle, import direct depuis tous les
  appelants). **13 call-sites runner** re-câblés : `damage_model.py` (9), `components.py`,
  `operations/additional_hits.py`, `operations/damage_ops/ability.py`,
  `operations/triggers/loki/reactivate_overwatch.py`, `abilities/base.py` (qui ne passait AUCUN
  `unit_state`) + `playbook/scene.py`.
- Effet de bord VOULU du même câblage : `max_hp` (`AnvilShield_BlockChanceBelowHealthCap`) et
  `enemy_psykers_alive` (`DestroyTheWitch_*`) étaient eux aussi absents des call-sites de dégât et
  dégradaient en VRAI. Ils sont désormais évalués partout. Gardes rejouées, vertes (§6).

**Conséquence à connaître** : un `Pinned` INERTE existe maintenant dans l'état offline, donc les
lectures de PRÉSENCE le voient. C'est fidèle et vérifié au décompilé :
`IdunBattle.Entities.Selectors.EntitiesWithAnyEffectSelector$$Select` appelle
`EntityExtensions$$HasOneOfEffects(entity, …, **0**, targetTypeMask, …)` — le littéral `0` occupe la
position que `EntityExtensions$$IsOwnerOfEffect(entity, state, effectType, activeOnly)` utilise pour
`activeOnly` (c'est ce paramètre qui, non nul, fait sauter les entrées à `+0x5c == 0`). Donc
`EntitiesWithAnyEffect` compte les effets **quel que soit** leur flag ⇒
`FearedInterrogator_TargetEffect.marks_target`, qui lit `by_unit`, reste conforme.
Correspondance à retenir : **port `by_unit` ≙ `decisionView includeInactive`** ;
**port `active_effects` ≙ `decisionView` par défaut**.

---

## 5. Résidus nommés

1. ~~**Défaire le collapse de `PinnedEffect.entity_is_immune_to_effect`**~~ — **LIVRÉ (#208,
   2026-07-28)**, détail en §4bis. Critère binaire atteint et mesuré des deux côtés : poser `Pinned`
   sur une cible `TerminatorArmour` **crée** l'effet (`has_effect(1065)` vrai == canal
   `includeInactive`) **et ne change aucun nombre** (plage de dégât de la cible inchangée : live
   1626 → 1626, port 1808 → 1808 ; contrôle live 3644 → 2550 et port 1930 → 1351, soit ×0.70).
2. ~~**Chaîne `&` derrière un `AddEffect` refusé**~~ — **CLOS le 2026-07-27, le résidu était un
   CONFOND** (`case-n5-chain-after-refused-addeffect.md`). L'abandon s'arrête à l'OPÉRATION : il ne
   remonte ni à l'itération du sélecteur-cible ni au combinateur. `AddEffectBehaviour$$Execute` jette
   la valeur de retour de l'opération et rend un `OperationResult` zéro-initialisé, que
   `CombinedBehaviour$$Execute` lit comme « ne pas court-circuiter ». La branche Chaos paraissait
   absente parce qu'**aucun DarkAngels n'était à portée** — avec le camp joueur DÉPLOYÉ au contact,
   `Pinned` ne contribue pas ET l'override + l'attaque libre s'exécutent (cible 10038 → 7442 HP). Le
   port était donc déjà conforme ; c'est le commentaire d'`operations/effects.py` qui était faux
   (corrigé), et une garde live verrouille désormais les deux sens.
   ⚠ **Montage re-qualifié (#208)** : le `Pinned` de ce montage n'est pas *refusé*, il est *inerte*.
   Le verrou structurel de `test_chain_after_refused_addeffect_live` exerce désormais un VRAI refus
   (trait `Immune` accordé sur l'état chargé — le natif peut l'accorder en bataille via
   `AddTraitOperation`, qui écrit la collection `BaseUnitComponent+0x48`), et l'axe `Pinned` des
   tests live se lit sur le canal ACTIF des deux côtés. La conclusion — la chaîne tient — est
   inchangée, et même renforcée : elle vaut pour les TROIS issues qui rendent `None`.
3. **5 des 7 classes `CanBeImmuneTo == true` ne sont pas portées** (§1.3) : tant qu'elles n'ont pas de
   classe côté port, `effect_def` rend `BaseEffect` ⇒ jamais immune. Inoffensif (aucune unité du
   roster ne porte `Immune`), à reprendre au portage de ces effets de tuile.
4. **`IsMechanical`** est approximé par le trait `Mechanical` (approximation pré-existante #154,
   conservée) : la propriété native peut couvrir davantage.

---

## 6. Validation

`scripts/python/tests/engine/runner/test_effect_immunity_live.py` (**8 tests, 53 s**) :

- **pose INERTE** (le critère du cas) : `SentinelDirectives` sur `blackAbaddon` → l'effet EST créé
  des deux côtés (`live includeInactive` == port `by_unit`), il est INACTIF des deux côtés
  (`live decisionView` défaut == port `active_effects`), et **le dégât de la cible ne bouge pas**
  (live 1626 → 1626, port 1808 → 1808) ;
- **contre-cas ACTIF** : même ability, `blackPossession` → effet actif des deux côtés et **×0.70**
  des deux côtés (live 3644 → 2550, port 1930 → 1351) ;
- **montage #112** : `ExemplarOfHate` × 2 cibles, même dichotomie sur le canal ACTIF ;
- **le gate d'immunité ne connaît QUE `Immune`** (offline) : sur la cible `TerminatorArmour`,
  `entity_is_immune_to_effect` rend `False` pour `Pinned` ET pour `Stunned`, les trois poses
  ABOUTISSENT, et seul le `Pinned` du porteur du trait est inactif ;
- **canal déclaratif** : `effect_def` rend le bon prédicat par classe ; `PinnedEffect` n'immunise
  PAS sur `TerminatorArmour` mais son `is_active` y est faux ; un effet non porté n'invente aucune
  immunité ;
- **anti-fork** : `_is_immune_to_contaminated` délègue, plus de liste de traits en dur ;
- **garde de non-régression #208** (statique) : aucun appelant d'`active_effects` dans `engine/` ne
  passe un dict LITTÉRAL — le `unit_state` vient du foyer unique. C'est ce test qui empêche la
  ré-ouverture silencieuse du trou (un seul `{"hp": …}` réintroduit et le ×0.70 fantôme revient).

**Généralisation** — `test_suppressive_fire_live` cas (4), AUTRE POSEUR (trigger de trait, pas cast
d'active) : `tauDarkstrider` tire sur `blackAbaddon` → live `includeInactive` publie 1065
`active=false`, canal par défaut vide ; port `by_unit` présent, `active_effects` vide.
`probe_208_pinned_inactive.py --generalise` ajoute un 2e porteur du trait d'une AUTRE faction
(`deathTyphus`, sans `Resilient`) : ratio de dégât **1.0**.

Gardes rejouées après le re-câblage du `unit_state` (toutes VERTES) :
`test_suppressive_fire_live` (4) · `test_effect_stun_live` · `test_anvil_shield_stun_live` ·
`test_effect_duration_rounds_live` (8) · `test_destroy_the_witch_live` (7) ·
`test_damage_crushingclaws_live` + `test_darkangels_lot1_live` (9) ·
`test_damage_roll_live` + `test_runner_attack_live` (4) ·
`test_aura_position_live` + `test_unit_flags_live` (4) ·
`test_noblocking_prediction_live` + `test_load_state_tile_effects_live` +
`test_hailstrike_phase2_live` (9) · `test_chain_after_refused_addeffect_live` (4, montage corrigé).

Probes livrés : `probe_208_pinned_inactive.py` (les DEUX canaux `decisionView` + le volet chiffré
`exposureView`, 3 montages), `probe_224_effect_immunity.py` (mesure live, 4 montages),
`probe_224_can_be_immune_to.py` (inventaire vtable de `get_CanBeImmuneTo`).

**Ce qui n'est PAS couvert** : (a) un `Pinned` inerte ne peut pas arriver par `load_state`, puisque
la capture `decisionView` par défaut le droppe — seule la pose OFFLINE l'exerce (le seed pourrait le
faire en passant `includeInactive`, non fait ici) ; (b) le contrôle de généralisation
`blackObliterator` donne un ratio 0.583 et non 0.70 — mesure PUREMENT live (aucun port en jeu),
confond non chassé (l'attaque du montage lui fait perdre des membres d'escouade) ; la valeur exacte
de ×0.70 est établie sur `blackPossession` ; (c) les 5 classes `CanBeImmuneTo == true` non portées
(résidu §5.3, inchangé).
