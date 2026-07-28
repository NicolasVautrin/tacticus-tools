# case-224 — Gate d'IMMUNITÉ d'effet (`BaseEffect.EntityIsImmuneToEffect` + `get_CanBeImmuneTo`)

**Statut** : porté + validé live (deux branches). Un résidu nommé subsiste (§5).
**Touche** : TOUS les vecteurs de pose d'effet — l'unique feuille `AddEffectOperation`.

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
- `PinnedEffect` : `can_be_immune_to = True`, surcharge `TerminatorArmour` (§4), `is_active` ;
- `ContaminatedEffect` (classe NEUVE) : `can_be_immune_to = True`, surcharge
  ContagionsOfNurgle | Mechanical | base.

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
> par mesure directe le 2026-07-28, cf. §4.

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

**État du port (inchangé à ce commit, et c'est délibéré)** : `PinnedEffect.entity_is_immune_to_effect`
COLLAPSE encore l'`ActiveCondition` dans le gate d'immunité. Le collapse est faux sur le MÉCANISME
mais rend le bon observable dans le cas courant. Le retirer seul introduirait une **régression** :
`PinnedEffect.is_active(unit_state)` lit `unit_state["traits"]`, or presque tous les appelants d'
`EffectsState.active_effects` passent `{"hp": ...}` **sans `traits`** (seul `refresh_effects.py`
construit `traits`) ⇒ traits inconnus ⇒ actif ⇒ le `×0.70` de
`PinnedEffect$$CreateEffectDamageBonusForAttack` s'appliquerait à un porteur `TerminatorArmour`.
Le chantier de sortie est décrit en §5.1.

---

## 5. Résidus nommés

1. **Défaire le collapse de `PinnedEffect.entity_is_immune_to_effect`** — le stade natif est
   désormais IDENTIFIÉ (§4), c'est le PORT qui reste à faire, et il n'est pas local. Il faut, dans le
   même changement, sinon on régresse :
   - retirer la surcharge `entity_is_immune_to_effect` de `PinnedEffect` (garder celle de
     `ContaminatedEffect`, qui elle est un vrai override natif) ;
   - faire porter `traits` par l'`unit_state` passé à `EffectsState.active_effects` **à tous** les
     call-sites qui décident d'une contribution — `damage_model.py` (5 sites), `damage_ops/ability.py`,
     `additional_hits.py`, `components.py`, `playbook/scene.py`, `abilities/base.py` (ce dernier ne
     passe même pas d'`unit_state`) ;
   - garde de non-régression MESURABLE : sur `blackAbaddon` porteur d'un `Pinned` inerte, le dégât
     qu'il inflige doit rester **inchangé** (pas de `×0.70`), et `has_effect(1065)` doit rendre
     **vrai** (le natif a bien alloué l'entité-effet).

   Critère binaire du chantier : après le fix, poser `Pinned` sur une cible `TerminatorArmour` crée
   l'effet ET ne change aucun nombre ; le retirer de l'état (comportement actuel) ne satisfait que la
   seconde moitié.
2. ~~**Chaîne `&` derrière un `AddEffect` refusé**~~ — **CLOS le 2026-07-27, le résidu était un
   CONFOND** (`case-n5-chain-after-refused-addeffect.md`). L'abandon s'arrête à l'OPÉRATION : il ne
   remonte ni à l'itération du sélecteur-cible ni au combinateur. `AddEffectBehaviour$$Execute` jette
   la valeur de retour de l'opération et rend un `OperationResult` zéro-initialisé, que
   `CombinedBehaviour$$Execute` lit comme « ne pas court-circuiter ». La branche Chaos paraissait
   absente parce qu'**aucun DarkAngels n'était à portée** — avec le camp joueur DÉPLOYÉ au contact,
   `Pinned` est refusé ET l'override + l'attaque libre s'exécutent (cible 10038 → 7442 HP). Le port
   était donc déjà conforme ; c'est le commentaire d'`operations/effects.py` qui était faux (corrigé),
   et une garde live verrouille désormais les deux sens.
3. **5 des 7 classes `CanBeImmuneTo == true` ne sont pas portées** (§1.3) : tant qu'elles n'ont pas de
   classe côté port, `effect_def` rend `BaseEffect` ⇒ jamais immune. Inoffensif (aucune unité du
   roster ne porte `Immune`), à reprendre au portage de ces effets de tuile.
4. **`IsMechanical`** est approximé par le trait `Mechanical` (approximation pré-existante #154,
   conservée) : la propriété native peut couvrir davantage.

---

## 6. Validation

`scripts/python/tests/engine/runner/test_effect_immunity_live.py` (7 tests, 86 s) :

- **branche immunisée** : `SentinelDirectives` sur `blackAbaddon` → live ET port ne posent pas Pinned ;
- **branche non immunisée** : même ability, `blackPossession` → live ET port posent Pinned ;
- **montage #112** : `ExemplarOfHate` × 2 cibles, même dichotomie (assertion bornée au volet Pinned,
  cf. résidu §5.2) ;
- **non-sur-immunité** (offline) : sur la MÊME cible `TerminatorArmour`, `Stunned` (1162,
  `CanBeImmuneTo` faux) PASSE et `Pinned` est refusé ; sur la cible sans le trait, `Pinned` PASSE ;
- **canal déclaratif** : `effect_def` rend le bon prédicat par classe, un effet non porté n'invente
  aucune immunité ;
- **anti-fork** : `_is_immune_to_contaminated` délègue, plus de liste de traits en dur.

Gardes rejouées (dépendances de `AddEffectOperation` / `refresh_effects._unit_state`) :
`test_suppressive_fire_live` · `test_effect_stun_live` · `test_effect_duration_rounds_live` (9 ✅) ;
`test_anvil_shield_stun_live` · `test_load_state_tile_effects_live` · `test_damage_crushingclaws_live`
(7 ✅) ; `test_darkangels_lot1_live` (8 ✅).

Probes livrés : `probe_224_effect_immunity.py` (mesure live des deux branches, 4 montages),
`probe_224_can_be_immune_to.py` (inventaire vtable de `get_CanBeImmuneTo`).
