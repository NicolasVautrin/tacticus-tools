# Case #27 — Overrides `CalculateCustomUtility` (terme d'ACTION de l'utilité Comparable)

> **Statut : PRÉPARATION (triage fait, fan-out non lancé).** Ce doc fige l'énumération
> exhaustive des overrides natifs et le protocole du fan-out `re-expert` (un item par agent).
> Énumération ghidra du 2026-07-23 (build `gqfc5mff6c`), requête symbole `CalculateCustomUtility`
> (functions only) : **27 corps**, triés ci-dessous.

## 1. Contexte

`ComparablePlaybook.CalculateCustomUtility @181407840` est le terme d'ACTION ajouté à l'utilité
Comparable (cf. `engine/playbook/base.py`, docstring `_custom_utility`). La base vaut `Fix64(0)` ;
chaque playbook per-ability peut l'overrider. Un override non porté = un biais d'utilité qui ne se
voit QUE quand l'ability du porteur entre en concurrence serrée (miss d'agreement « choix d'action »).

## 2. Déjà couverts (ne PAS refaire)

| Corps natif | VA | Où c'est porté |
|---|---|---|
| `ComparablePlaybook<T>` (base) | `@181407840` | `base.py` `_custom_utility` = 0 |
| `ALoki_NormalAttackPlaybook<T>` (générique partagé) | `@1813726e0` | `common.py` : `Fix64(1)` constant (preuve L3 #64) |
| `Idun.NormalAttackPlaybook<T>` (générique partagé) | `@18149ee60` | idem `common.py` (même corps partagé) |
| `Loki_NormalBossAttackPlaybook` | `@1811497c0` | idem : `Fix64(1)` constant (docstring `common.py`) |
| `TwistedScience_HealPlaybook` | `@18116fb00` | `common.py` HealPlaybook : +100, +100 si cible Genestealers |

## 3. À porter — 22 items du fan-out

Notes préremplies quand un doc existant cite déjà le porteur/l'ability (prediction.py, base.py).

| # | Playbook | VA | Notes connues |
|---|---|---|---|
| 1 | `ProperKilly_NormalAttackPlaybook` | `@1811532a0` | Exception au générique Fix64(1) (docstring `common.py`) ; logique melee ; passif orksWarboss (klaw, cf. `prediction.py` `_MELEE_KLAW_PASSIVES`) |
| 2 | `PlagueburstMortarPlaybook` | `@181134e00` | — |
| 3 | `LightOfSanguiniusPlaybook` | `@181133d70` | 1147, cf. `prediction.py` #172 (blood) |
| 4 | `ArmoriumCherubPlaybook` | `@18111c530` | cf. `prediction.py` (ArcScourge/Cherub, GetHits @180fb16c0) |
| 5 | `ChronometronPlaybook` | `@181125ab0` | — |
| 6 | `DaemonicOrdnancePlaybook` | `@1811286c0` | 1148 blackForgefiend (MoW), cf. `prediction.py` #172 |
| 7 | `DevoutPushPlaybook` | `@18112c7b0` | — |
| 8 | `DoomSirenPlaybook` | `@18112cd30` | — |
| 9 | `DrachnyenPlaybook` | `@18112dc60` | Quirk `count>=2` (cité `base.py`) |
| 10 | `ForwardObserversPlaybook` | `@18113bb70` | — |
| 11 | `HealingBalms_HealPlaybook` | `@181142dc0` | Comparer au patron TwistedScience_Heal déjà porté |
| 12 | `HeraldOfTheApocalypsePlaybook` | `@1811441b0` | 1020 blackHaarken (cité `base.py` + `prediction.py`) |
| 13 | `InstrumentsOfVengeancePlaybook` | `@1811460d0` | — |
| 14 | `MartialExemplarPlaybook` | `@18114ae20` | — |
| 15 | `MortarionsPlagueWindPlaybook` | `@18114ca30` | — |
| 16 | `MortisRoundPlaybook` | `@18114d190` | Quirk displacement (cité `base.py`) |
| 17 | `PlasmaGrenadePlaybook` | `@181151040` | — |
| 18 | `Repair_GalvanicFieldPlaybook` | `@181155520` | Patron repair (cf. étage repair #45d) |
| 19 | `SavageEchoesPlaybook` | `@1811586d0` | — |
| 20 | `SorcerousFacadePlaybook` | `@18115b9d0` | 1100 thousTzaangor, cf. `prediction.py` #171/#99 |
| 21 | `StikkbombPlaybook` | `@18115f7c0` | — |
| 22 | `TheLionsWrathPlaybook` | `@18116aba0` | — |

## 4. Protocole du fan-out (au lancement)

- **Un item = un agent `re-expert`** (`isolation: "worktree"`, junction `data/` en étape 1) —
  jamais le framing batch dans le prompt d'un item (`feedback_fanout_per_item_scope`).
- **Par item, dans l'ordre** :
  1. **Reachability d'abord** (`feedback_verify_reachability_before_porting_decision`) : le playbook
     est-il enregistré ET atteignable (porteur réel, bucket créé) ? Du code registered-but-dead existe.
  2. **Porteur spawnable en runner ?** (`unit_map.py`). Non spawnable → NE PAS porter
     (`feedback_no_unvalidatable_ability_ports`) : documenter en résidu et clore l'item.
  3. RE du corps (decompile = vérité, mirror 1:1, VAs citées), port dans le playbook Python
     correspondant, validation live ciblée (scénario crafté où le terme custom change le classement).
- **Verdicts attendus fréquents** : constante triviale (cf. Fix64(1)), délégation au générique,
  ou vrai quirk (Drachnyen/MortisRound/ProperKilly). Les constantes se regroupent en un seul
  commit de synthèse ; les quirks ont chacun leur port.
- **Synthèse** : à la fin du fan-out, ce doc passe en case CLOS avec le verdict par item
  (constante / quirk porté / invalidable-résidu).
