# #1079 — cinq résidus `BLOCAGE: seeding` sur un foyer, et **trois prémisses fausses sur cinq**

Cinq résidus de cinq familles butaient sur `engine/playbook/noncomparable/_base.py` avec le même
mot de blocage. Ils ne partageaient pas un bloqueur : ils partageaient une structure
sous-alimentée, `NCContext`, sur le chemin OFFLINE / face DÉCISION.

| résidu | verdict | ce qui a tranché |
|---|---|---|
| #983-r1 | **CÂBLÉ** | le substrat d'entité était en mémoire ; il manquait le pont `rid == 0` |
| #979-r1 | **PORTÉ — prémisse RÉFUTÉE** | `Scene.turns_finished` existe depuis #27-r8 ; **les deux bornes de la fiche étaient décalées d'un cran** |
| #1027-r5 | **volet OFFLINE câblé — énoncé FAUX sur deux points** | le plafond n'arrivait pas « vide » ; les deux sites lisaient un **attribut inexistant** |
| #1030-r2 | **PORTÉ** | ce n'est pas une translation d'offsets : le natif **reconstruit** `{t} ∪ ring1(t)` |
| #976-r2 | **hypothèse temporelle RÉFUTÉE** | son `GetUseProbability` ne lit **aucun** compteur de tour |

---

## 1. #983-r1 — le canal existait des deux côtés, il manquait une arête

`AiDecisionContext.live_triggered_kits()` ouvrait par `if not self.rid: return {}`. Or le substrat
n'est pas le RPC : c'est le `TriggeredAbilityComponent`, dont `UnitContext.triggered_abilities` est
l'image, **déjà seedée** côté `State` par `snapshot._load_triggered_abilities` — depuis ce même RPC.

`state_bridge._triggered_kits_from_state(scene)` la publie dans `offline_triggered_kits` ; les deux
voies (`live_triggered_kits`, `live_triggered_ability_ids` — ex-résidu N13-b) la servent quand `rid`
est faux.

**Le tri-état est au grain de l'ENTITÉ, pas de la table.** Une unité dont `triggered_abilities is
None` reste ABSENTE — surtout pas une liste vide, qui se lirait « aucun passif monté » et
RETIRERAIT un id que le kit gameconfig connaît. C'est le sens exact de la faute #456-r1
(`tauCrisis` greffé : natif `[1120, 1030]`, port `[1133]` — divergence **dans les deux sens**).

Le gate consommateur (`1189 CalibaniteGreatsword`, `HasTriggeredAbility(caster, 0x5f2)`) reste
inerte sur ce build : aucune des 669 unités ne porte `1522 RedemptionOfTheRisen`. Le fil est donc
**CÂBLÉ, non CONFRONTÉ**.

---

## 2. #979-r1 — rien ne manquait, et les deux bornes étaient fausses

La fiche annonçait `BLOCAGE: seeding` et « `Scene.turns_started` existe, son pendant FINISHED n'est
pas publié à `NCContext` ». **Faux** : `Scene.turns_finished_by_id` existe depuis #27-r8, il est
renseigné par les deux voies (`from_state` et `combatSnapshot.units[].turnsFinished`),
`NCContext.scene` **est** cette `Scene`, et `InstrumentsOfVengeancePlaybook.should_evaluate_unit`
portait déjà exactement ce patron à soixante lignes de là.

`IdunBattle.AI.Playbook.Loki.DutyEternalPlaybook$$GetUseProbability`, lu verbatim :

    c = AbilityConfiguration.GetNumberConstant(<ability+0x68>.<config+0x60>, 0x68)  // initialCooldownTurns
    t = UnitExtensions.GetTurnsFinished(unit)
    return Fix64.FromIntFraction((t - c + 1) * 0x21, 0x64)                          // 33 / 100

Bornes **re-dérivées**, contre celles de la fiche :

| | fiche | mesuré |
|---|---|---|
| refus déterministe | `t < c - 1` | **`t <= c - 1`** |
| accept déterministe | `t >= c + 2` | **`t >= c + 3`** |

La fiche se contredisait elle-même : son énumération `33/66/99` donne bien **trois** valeurs de
tirage, donc `t ∈ {c, c+1, c+2}`. Ce qui place la borne haute à `+3` et non `+2` est que
`3 × 33 = 99 < 100`, et que `FixMath.NET.Fix64$$FromIntFraction` **divise en virgule fixe**
(`(long)(int)n << 0x20` des deux côtés) — `99/100` vaut `0.99`, pas `0`.

Le triage des trois branches de `BasePlaybook$$ShouldEvaluate` vit désormais dans le foyer partagé
`_base.probability_gate` ; seule la bande ouverte reste l'écart assumé (`#969-r1`). Sur ce build
`c = 2` : refus tant que `turnsFinished <= 1`.

⚠ `GetNumberConstant` (sans `Try`) est `int.Parse(GetStringConstant(key))` — le natif **lève** sur
une clé absente. Le port ne peut pas lever à sa place (il s'évaluerait sur des abilities greffées) :
clé absente → `None` = NON MESURÉ → le triage répond `True`, jamais un refus fabriqué.

---

## 3. #1027-r5 — le vrai trou n'était pas celui annoncé

L'énoncé disait « le `State` n'existe pas sur la face DÉCISION, donc le plafond arrive **VIDE** et
le gate rend toujours `True` ». Deux points faux :

1. **Le plafond n'arrivait pas vide.** `victory_config.get_max_rounds` a un défaut **dérivé** de
   `data/seed-bc.json` (entrée versionnée), où `MainPlayerRoundLimitation` est absente. `True` y
   était donc déjà une **lecture**, pas une convention permissive.
2. **Le vrai trou** : `SolarAtomizerPlaybook.should_evaluate` et `TheLanternPlaybook.should_evaluate`
   lisaient `getattr(ctx, "state", None)` — **un attribut que `NCContext` n'a jamais porté**. La
   valeur était donc invariablement `None`, et le foyer jugeait sur la **seed** quelle que soit la
   BC de la bataille en cours.

`NCContext` et `AiDecisionContext` transportent maintenant les **deux entrées** du natif, en
tri-état : `victory_conditions` (`<victoryConfig @+0x18>`) et `turns_ended_by_first_player`
(`TurnComponent.<Dictionary @+0x40>`). `state_bridge` les lit du `State` ; le foyer
`_base.has_minimum_remaining_turns` les sert.

**La dégradation permissive se ferme** : là où un plafond existe, le gate REFUSE. C'est le
correctif, pas une régression.

Reste ouvert, volet **LIVE** : aucun RPC ne publie `BC.Victory` ni le compteur **par joueur**. Le
bundle porte bien `readTurnsEnded`, mais c'est `GetAmountOfTurnsEnded(state, 0)` = la **somme sur
tous les joueurs** — précisément le voisin que `services/battle_query` nomme comme faux ici.

---

## 4. #1030-r2 — le natif ne transporte pas l'empreinte, il la reconstruit

`IdunBattle.Core.Services.MovementQuery$$GetPossibleTileListsFromMovableTiles(movableTiles,
numFeet)` branche sur le nombre de pieds ; pour `7` :

    foreach (t in movableTiles) {
        adj = <IBattleQuery slot 0x4f = GetAdjacentTiles>(t, 0, 1, 1);
        if (movableTiles.ContainsAll(adj)) {
            set = new OrderedSet<Tile>(); set.Add(t); set.AddRange(adj);
            result.Add(set);
        }
    }

(`numFeet == 1` → `GetKCombs(.., 1)` ; `== 3` → `GetKCombs(.., 3)` ; autre → `null`.)

Donc l'empreinte d'une `UnitPosition` à sept pieds est `{t} ∪ GetAdjacentTiles(t)`, **recalculée à
chaque position**. L'ordre est load-bearing (`Add` avant `AddRange` : `target_area` retranche
`feet[:1]` = la main tile).

Le ring-1 porte les filtres **lus** au call-site `(t, onlyEmptyOrSteppable: 0, onlyWalkableTiles: 1,
allowTemporary: 1)` : porte d'élévation `|dElev| < 2` **inconditionnelle**
(`TileQuery.<IterateAdjacentTiles>d__8$$MoveNext`), `IsWalkable` armé, temporaires autorisées,
occupation non filtrée. C'est `battle_query.is_adjacent` — surtout pas `hexgeo.disk`, qui n'a pas de
porte d'élévation (c'est `SurroundingTiles` qui n'en a pas, et le port le distingue déjà).

Nombre de pieds non mesuré → `[position]`, comportement d'avant : le port n'invente pas une
empreinte à sept tuiles pour une unité dont il ignore la taille.

**Résidu ouvert `#1079-r1`** : le `ContainsAll` — le natif ÉCARTE une position dont les six
voisines ne sont pas toutes movables. `ctx.reach_nc` sort d'un flood-fill de main tiles sans ce
filtre, donc le port évalue des positions que le natif n'aurait pas produites. Écart permissif, mais
il peut déplacer l'argmax (`Bucket$$AddAction` ne remplace que sur amélioration stricte). Le
corriger touche `action_tiles_for`, foyer partagé par tous les NonComparable — d'où la séparation.

---

## 5. #976-r2 — l'hypothèse temporelle est réfutée, le blocage reste

`IdunBattle.AI.Playbook.Loki.TitanhammerSquadPlaybook$$GetUseProbability`, re-lu verbatim, ne lit
**aucun** compteur de tour. Ses deux entrées sont `UnitExtensions$$HasFlag(unit, 1 =
UnitFlag.ArrivedAtFinalTile)` et le cardinal de
`TitanhammerSquadAbility$$GetCurrentlyAffectedFriends`, plus deux `GetUtilityValue`.

Le `BLOCAGE: seeding` de sa fiche reste **juste**, mais il porte sur le **BC** (les trois clés de
poids `Titanhammer*` absentes de `BattleConfiguration.Utilities.Default`), pas sur `NCContext`.

Ce qui serait portable sans les poids : la branche `HasFlag(unit, ArrivedAtFinalTile) → Fix64(0)`,
un refus déterministe. Elle exige un canal que la face DÉCISION n'a pas — `Scene` porte
`moved_by_id` / `teleported_by_id` / `active_ability_used_by_id`, **pas** `ArrivedAtFinalTile`
(que `combatSnapshot.units[].unitFlags` publie pourtant, cf. `CasterSubstrate.has_moved`).

---

## 6. Le cran

`scripts/python/tests/engine/test_1079_nccontext_seeding_offline.py`, 10 étages, 100 % offline.
Six mutations jouées, **6/6 rouges**, témoin vert :

| mutation | effet |
|---|---|
| `live_triggered_kits` → `{}` d'office | 1 rouge |
| `live_triggered_ability_ids` → `[]` d'office | 1 rouge |
| `should_evaluate` → `True` (état d'avant) | 1 rouge |
| `victory_conditions` non transporté | 2 rouges |
| borne basse du triage relâchée | 2 rouges |
| tri-état par entité perdu | 1 rouge |

Un contrôle porte sur l'**AST**, pas sur le texte : les deux playbooks *citent* l'ancienne lecture
`getattr(ctx, "state", None)` dans leur prose pour expliquer la faute, et un `in src` la confondrait
avec un appel.
