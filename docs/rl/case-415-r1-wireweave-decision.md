# case-415-r1 — le `-30` de `WireweaveNet_FirstAttack` MORD sur la décision, et le port le rend

**Question, binaire.** L'IA native évite-t-elle une Calandis dont le filet `1111` est ARMÉ, et le
port fait-il le même choix — au même endroit, pour le même montant ?

**Réponse : OUI des deux côtés, confronté LIVE en A/B.** Le natif retient la cible SANS filet quand
il est armé, la porteuse du filet quand il ne l'est pas ; le port reproduit les deux, et neutraliser
le seul terme mesuré fait basculer le port exactement là où le natif bascule. Le résidu ouvert
depuis `case-366-r1b` §8 (« la face DÉCISION n'est pas confrontée live ») est **fermé**.

## 1. Pourquoi il fallait un montage dédié — l'oracle de #415 est structurellement aveugle

Le décompilé de `IdunBattle.AI.Playbook.ComparablePlaybooku003C__Il2CppFullySharedGenericTypeu003E$$CalculateActionUtility`,
lu pour ce cas :

    u  = CalculateCustomUtility(vslot 0x338)                     ; 3 sentinelles -> Nullable vide
    u += CalculateUtilityFromPredictions(...)                    ; <- CE QUE `pairUtility` INVOQUE
    if (ShouldExecute(vslot 0x328)) {
        u += vslot 0x348(...)
        util = <dict des utilites @playbook+0x8>[0x37]           ; 0x37 = 55
        u += util.Evaluate(UtilityAttackCase.Base(state, position, target, ability))
        u += CalculateUtilityFromTilePrediction(...)
    }

Le terme est sommé **après** `CalculateUtilityFromPredictions`, dans la même fonction. Le RPC
`pairUtility` invoque `CalculateUtilityFromPredictions` **directement** : il ne peut donc pas le
voir, quel que soit le montage. Le seul oracle qui le voit est la **décision** elle-même
(`aiDryRunAllUnits` -> `IdunBattle.AI.Tactics.DefaultAiUnitTactic$$CalculateNextActionForUnit`).

`0x37 = 55` = `UtilityType.WireweaveNet_FirstAttack` (`data/symbols/rnca9r7q6c/frida/enums.tsv`) —
l'écriture `key-0x36` des docs vient de `gqfc5mff6c`, où l'enum valait 54.

## 2. Le corps natif, relu — le conjoint d'adjacence est bien DÉGÉNÉRÉ

`IdunBattle.AI.Utilities.WireweaveNet_FirstAttack.u003CEvaluateAttackInStepsu003Ed__1$$MoveNext`
(décompilé, pas déduit) : les **deux** opérandes d'`IdunBattle.Entities.TileExtensions$$IsAdjacentTo`
sortent du MÊME `case+0x18` — le décompilateur écrit deux fois
`get_MainTile(case + 0x18)`, il n'y a **aucun** accès à `case+0x20` avant le test.
`case+0x20` (la CIBLE) n'est lu qu'ensuite, pour
`IdunBattle.Entities.EntityExtensions$$GetOwnedEffects(target, this.State, (EffectType?)0x457)`.
Le prédicat du `Any` est le lambda `..u003Cu003Ec$$u003CEvaluateAttackInStepsu003Eb__1_0`, corps
`return *(byte*)(GetComponent<EffectComponent>(e) + 0x5c)` = **`IsActive`**.

⇒ le malus tombe **aussi à distance**, malgré le nom de la clé
(`WIREWEAVENET_AdjacentActiveEffect`). **C'est désormais mesuré, pas seulement lu** : le montage
ci-dessous place les cibles à **distance 2** du caster, et le natif détourne quand même son tir. Une
lecture « gate d'adjacence caster/cible » aurait prédit un terme NUL et donc **aucun** détournement.

Poids : `BC.Utilities.Default.WireweaveNet_FirstAttack.WIREWEAVENET_AdjacentActiveEffect` = **-30**.

## 3. Le montage — ce qui reste quand tout le reste est égalisé

`probe_415_r1_wireweave_decision.py`, board `MC1_67`, seed 41171, deux bras qui ne diffèrent QUE par
le passif de Calandis.

| levier | pourquoi |
|---|---|
| caster `tauMarksman` | **ni `SuppressiveFire`** (sinon le terme +35 de #415 casse l'égalité de paire dès qu'une seule cible porte l'overwatch) **ni `Overwatch`** (sinon son tir automatique TUE une cible à 600 PV pendant le drive) |
| `--unit-stat <caster>:ActiveAbilities=[],PassiveAbilities=[]` | la seule action comparable est l'attaque NORMALE (`69`) |
| `--unit-stat <caster>:Movement=0` | **épingle le caster** : `BattleQuery$$GetCurrentAndMovablePositionsFor` se réduit à la tuile courante, la boucle MÉDIANE (tuiles) n'a qu'un tour, et la décision se réduit EXACTEMENT à la boucle MINEURE (cibles) |
| cibles `eldarRanger` + `astraCreed` (traits = `["Hero"]` seul), abilities retirées | rien d'autre qu'un filet ne les distingue |
| `--hp-target 600` | kill déterministe des deux côtés -> `pair` sature et s'ÉGALISE ; armures à 0 |
| TA/TB à **distance égale** du caster, **même élévation**, **aucun effet de tuile**, `d(TA,TB) >= 2` | aucun modificateur d'attaquant asymétrique |
| `rang_cube(TA) < rang_cube(TB)` | la porteuse du filet est ÉNUMÉRÉE LA PREMIÈRE (`IdunBattle.Core.Services.TileQuery.u003CIterateSurroundingTilesu003Ed__6$$MoveNext`) ; comme `...$$EvaluateInternal` remplace sur `op_GreaterThan` STRICT, elle **gagnerait le tie** sans le terme |

**L'épinglage n'est pas cosmétique.** Sans lui (première mesure du 2026-08-01), le natif se DÉPLACE
vers la cible qu'il retient — `(3,4) -> (4,2)` bras armé, `(3,4) -> (2,3)` bras désarmé — et sur la
tuile qu'il choisit **une seule cible reste légale** : l'égalité de paire n'y est plus vérifiable et
le montage cesse de discriminer. Le garde du probe l'a refusé (`pairUtility NATIF INEGAL sur (4,2) :
0 vs 239.667…`) au lieu de conclure sur un écart non attribuable.

## 4. La mesure

Caster épinglé en `(1,0)`, `action_tiles = [(1,0)]`, Calandis `(0,1)` rang cube `(0,-1)`, astraCreed
`(3,0)` rang cube `(3,-1)`, distance **2** de part et d'autre, élévation 3 partout.

| | bras **ARMÉ** | bras **DÉSARMÉ** (`eldarRanger:PassiveAbilities=[]`) |
|---|---|---|
| effets publiés sur Calandis | `1008,` **`1111`**`, 1009` (tous actifs) | `1008, 1009` |
| `pairUtility` NATIF, Calandis | `239.66777409426868` (`utilRaw 1029365251640`) | idem |
| `pairUtility` NATIF, astraCreed | `239.66777409426868` (`utilRaw 1029365251640`) | idem |
| `pair` PORT (les deux) | `239.66777408637876` (écart 8e-9, Fix64 vs float) | idem |
| `u_action` PORT, Calandis / astraCreed | **240.6678** / **270.6678** | 270.6678 / 270.6678 |
| **NATIF** | ability 69, cible **astraCreed**, pas de move | ability 69, cible **Calandis**, pas de move |
| **PORT** | ability 69, cible **astraCreed** | ability 69, cible **Calandis** |
| **PORT, terme NEUTRALISÉ** | ability 69, cible **Calandis** (≠ natif) | inchangé (≠ rien) |

Les deux `utilRaw` sont **le même entier Fix64** : l'égalité de paire n'est pas « à epsilon près »,
elle est exacte. Le seul discriminant natif restant est le terme mesuré, et il pèse **exactement
-30.0** sur la porteuse du filet armé, **0.0** partout ailleurs (bras désarmé compris).

## 5. Ce qui garde, et ce qui a été vérifié ROUGE

`tests/engine/test_415_r1_wireweave_decision_live.py`, **2 tests**, modèle #456 (conformité +
discriminance). Le montage **exige** ses prérequis et **échoue** s'il ne les obtient pas (#268) :
épinglage effectif, natif immobile, égalité EXACTE de `pairUtility` (valeur ET `utilRaw`), port déjà
conforme À CET ÉTAGE (un fork amont donnerait un faux écart), deux cibles LÉGALES depuis la tuile
épinglée, cibles à distance >= 2, et géométrie IDENTIQUE entre les deux bras.

| mutation | résultat |
|---|---|
| **M1** `wireweave_net_first_attack_utility` -> `0.0` | **2 ROUGES** (`le terme pese 0.0 au lieu de -30.0`) |
| **M2** prédicat sur `has_effect` au lieu d'`active_effects` | **VERT sur la garde LIVE** — le régime qui les sépare n'y est pas atteignable (§6). Fermé OFFLINE, étape `[10]` : **ROUGE** |
| **M3** ordre d'énumération des cibles INVERSÉ (`_best_attack`) | **2 ROUGES** — le tie du bras désarmé est bien porteur, l'assertion n'est pas vide |

**Étape `[10]` de `probe_366_r1b_wireweave_gates.py`, neuve.** L'étape `[9]` ne testait que
`U.evaluate(tile, bool, cat)` — le booléen y est DONNÉ, donc elle était aveugle au choix
`active_effects` vs `has_effect`, et **rien** ne le gardait. `[10]` exerce le seul régime qui les
sépare : l'entité-effet **PRÉSENTE mais ÉTEINTE** (Calandis a déjà contre-attaqué ce tour, via le
`& DeactivateEffect` du behaviour), sur une vraie `Scene.from_state`. Mesure : filet armé ->
prédicat `True`, terme `-30.0` ; filet consommé (encore présent : `has_effect` = `True`) ->
prédicat `False`, terme `0.0`.

**Non-régression** (tests CIBLÉS, après rebase sur `origin/master` à `a12cf7bd`, qui contient #456 et
#457) : `test_415_r1_wireweave_decision_live` 2/2, `runner/test_wireweave_net_counter_live` 6/6 (face
COMBAT du même effet), `test_415_suppressive_fire_pair_term_live` 2/2 (le voisin qui touche le même
foyer), `test_line_elevation_gate_decision_live` 2/2.
**Cliquets** : `probe_181_targeting_gaps`, `probe_120 --step 0`, `probe_273 --only-scan`,
`probe_365`, `probe_330`, `probe_321`, `probe_252`, `probe_va_in_code_vs_prose`,
`probe_366_r1b_wireweave_gates` — tous rc=0.

## 6. Ce qui n'est PAS couvert

* **Le régime « filet PRÉSENT mais DÉSARMÉ » n'est pas atteignable sur la face DÉCISION LIVE**, et
  c'est une MESURE, pas une supposition : `aiDryRunAllUnits` n'évalue que les unités du joueur
  **COURANT** (mesuré — pendant le tour de Calandis il rend `[77, 79]`, jamais mon attaquant `81`).
  Or la seule fenêtre où le canal `decisionView` par défaut cesse de publier l'instance est
  précisément le tour de son porteur (vérifié : les effets publiés y tombent à `[(1008, True)]`).
  L'autre voie — faire consommer le filet par une riposte, puis décider avec une SECONDE unité dans
  le MÊME tour — reste ouverte mais casse l'égalité de paire (l'attaque qui déclenche la riposte
  entame les PV de Calandis) ; il faudrait un attaquant à `Damage=0` pour la préserver. **NON
  CONFRONTÉ**, gardé OFFLINE par l'étape `[10]`.
* **Le gate `CasterPosition.MainTile == null`** (`yield break`) n'a pas d'observable live : un
  caster en bataille a toujours une tuile. Gardé offline par `[9]`.
* **La branche CONTACT** (caster adjacent à la porteuse) n'est pas jouée : sous la lecture
  dégénérée du conjoint elle prédit la même chose que la branche distante, donc elle ne
  discriminerait rien de plus. C'est la branche DISTANTE qui est falsifiante, et c'est elle qui est
  jouée.
* **Le terme `vslot 0x348`** de `CalculateActionUtility` (sommé entre les prédictions et le terme
  55) n'est pas identifié par ce cas — il est hors périmètre, et l'accord bit-exact port/natif sur
  `pair` puis sur la DÉCISION montre qu'il n'introduit pas d'écart sur ce montage.
* **Un seul couple (board, seed)** : `MC1_67` / 41171. La mécanique mesurée n'est pas géométrique
  (le conjoint d'adjacence est dégénéré), donc la discipline « deux boards » ne mord pas ici ; mais
  le montage n'a pas été rejoué ailleurs.

## 7. Artefacts

| quoi | où |
|---|---|
| montage + mesure (A/B armé/désarmé, verdict) | `scripts/python/probe_415_r1_wireweave_decision.py` |
| garde à deux volets (conformité + discriminance) | `scripts/python/tests/engine/test_415_r1_wireweave_decision_live.py` |
| garde du prédicat `IsActive` (offline, étape `[10]`) | `scripts/python/probe_366_r1b_wireweave_gates.py` |
| le port confronté | `scripts/python/engine/utilities/wireweave_net.py` + `engine/playbook/base.py` (`calculate_action_utility`) |
