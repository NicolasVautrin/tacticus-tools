# #287-r11-r1-r1-r2 — le préfixe `IsTurnOfUnit` de `CasterHasNotMoved`, face RUNNER

L'écart était **nommé** depuis #287-r11-r1-r1 (§8) mais **non porté** : `get_invalid_caster_reason`
refusait des casts que le natif accepte. Cette tranche le porte, le confronte live, et le grave.

## 1. Le fait, lu au décompilé

`IdunBattle.Core.Services.TargetingQuery$$GetInvalidCasterReason` garde sa clause 1 par un
préfixe :

    if (battleQuery.<slot 0x35>(caster) && (rules & 0x10))          // CasterHasNotMoved
        if (!(!DidMove(caster) && GetTiles(caster).IsEquivalentTo(casterTiles))) return 0x10;

Le slot `0x35` = **53** = `IsTurnOfUnit`, arité **1** (`data/symbols/<build>/metadata/interface_slots.tsv`,
confirmé par la lambda `IdunBattle.Core.Services.RecordedSimulationRequestsBattleQuery.
u003Cu003Ec__DisplayClass86_0$$u003CIsTurnOfUnitu003Eb__0`, qui relaie le MÊME couple
(slot, classe d'interface) et dont le NOM donne la méthode).

`IdunBattle.Core.Services.BattleQuery$$IsTurnOfUnit`, relu VERBATIM sur `rnca9r7q6c` :

    entity = UnitExtensions.GetUnit(unit, state);
    if (entity == null)  return false;
    turn   = StateExtensions.GetMatchTurn(state);
    owner  = EntityExtensions.GetOriginalOwnerEntity(entity, state);   // null -> NullReference
    return TurnComponent.get_CurrentPlayerId(turn) == owner.Id;

**Quand ce n'est pas le tour du propriétaire d'ORIGINE, la règle est ENTIÈREMENT sautée**, flag
`UnitFlag.Moved` compris.

## 2. Le substrat du port est EXACT — ce n'était pas une approximation à assumer

`IdunBattle.Entities.EntityExtensions$$GetOriginalOwnerEntity` résout
`state.GetEntity(OwnerComponent.<PlayerEntityId @+0x10>)`. Le hook lit **ce même champ `+0x10`**
(`frida/hooks/game/match-state.ts`, `ownerPlayerId: 0x10`) et le publie en
`decisionView.units[].owner`, que `snapshot.load_state` pose dans `OwnerComponent.player`. Le port
compare donc exactement ce que le natif compare.

⚠ **Le voisin immédiat lit un AUTRE champ.** `IdunBattle.Entities.UnitExtensions$$IsControlledByCurrentPlayer`
(`decisionView.units[].ctrl`) passe par l'accesseur
`IdunBattle.Entities.Components.OwnerComponent$$get_CurrentPlayerEntityId`, dont le corps est

    return (this+0x14 != 0) ? this+0x14 : this+0x10;

`+0x14` est l'**override de CONTRÔLE** — les deux divergent sous contrôle mental (`1164 MindControl`,
non portée). Les confondre aurait donné un port juste dans tous les régimes portés et faux dans le
seul qui compte.

⚠ **Un écart NOMMÉ demeure, sans substrat** : `TurnComponent$$get_CurrentPlayerId` déroute vers le
joueur TEMPORAIRE quand le `Nullable` `TurnComponent+0x28` a une valeur, sinon rend le champ brut
`+0x24`. `State.current_player_id` mirroir le champ BRUT ; aucun canal ne publie `+0x28`. Même
borne que celle déjà nommée par `engine/streams/turn_phase.py::prepare_turn`.

## 3. Le foyer, et la DIRECTION de son tri-état

`engine/runner/components.py::is_turn_of_unit` (à côté d'`unit_has_moved`, le lecteur de l'autre
terme de la même clause). Tri-état :

| substrat | rendu | effet sur la clause |
|---|---|---|
| propriétaire connu, joueur courant connu, **différents** | `False` MESURÉ | **SAUTÉE**, comme le natif |
| idem, **égaux** | `True` MESURÉ | évaluée |
| entité absente | `False` | mirror du `if (entity == null) return false` |
| `OwnerComponent` absent / `player` à `None` / `State.current_player_id` à `None` | `None` = **pas mesuré** | **évaluée** |

⚠ **La direction du `None` est le livrable, et elle est l'INVERSE de celle du module DÉCISION.**
Chez `services.ability_caster_gates.invalid_caster_reason`, `None` ne refuse jamais : le tri-état y
borne la ZONE par le HAUT. Ici, `None` ne SOULAGE pas : sauter sur une non-mesure fabriquerait une
acceptation, alors que garder la clause rend exactement le verdict d'avant ce préfixe. Le régime
« non mesuré » est celui de toute fixture construite hors `load_state` — les rabattre sur `False`
aurait désarmé `CasterHasNotMoved` dans toute la banque offline, en silence.

## 4. Le régime qui fait MORDRE le préfixe — et pourquoi il est atteignable

`UnitFlag.Moved` **survit à la fin du tour** : `UnitFlagsComponent$$RemoveTurnFlags` est joué par le
`StartTurnOperation` du **joueur ENTRANT**, pas globalement. Une unité qui bouge puis passe la main
porte donc encore le flag pendant tout le tour adverse — et pendant ce tour, `IsTurnOfUnit(elle)`
est FAUX. Les deux termes de la clause sont alors en opposition : c'est le discriminant.

Ce régime est celui de l'**ORACLE** `abilityReason`, que `AttackQuery$$GetInvalidCasterReason` évalue
pour n'importe quelle unité des deux camps. Sur le chemin du CAST
(`ActiveAbilityOperation$$ExecuteInternal` -> `abilities/handler.py`) le caster est le joueur
courant, donc le préfixe y est INERTE.

## 5. Confrontation LIVE — `probe_287r11r1r1r2_is_turn_of_unit.py`

Board `MC1_67`, seed 777, `1163 BlackRage` / `bloodDeathCompany` (HERO du pool), runner `--no-ai`.
L'oracle est `casterReason` du RPC `abilityReason` = `AttackQuery$$GetInvalidCasterReason(caster,
casterTile, abilityType)` — **il ne prend aucune cible**, donc il isole le volet CASTER.

| bras | natif | port APRÈS | port AVANT | `has_moved` | `is_turn_of_unit` | joueur courant |
|---|---|---|---|---|---|---|
| avant-move (tour de Lucien) | `0x0` | `0x0` | `0x0` | `False` | `True` | 3 |
| en-tour + a bougé | `0x10` | `0x10` | `0x10` | `True` | `True` | 3 |
| **hors-tour + a bougé** | **`0x0`** | **`0x0`** | **`0x10`** | `True` | **`False`** | 4 |

Ventilation native `{0x0, 0x10}` — **non dégénérée**. **0 bras écarté** (aucun `ValidRequest` d'étage
amont). Le port « AVANT » est le code du commit avec `targeting.is_turn_of_unit` substituée par
`lambda: True`, c'est-à-dire la clause évaluée inconditionnellement.

⚠ **Le bras `hors-tour` ne prouve quelque chose que si le substrat des DEUX étages est celui qu'on
croit.** Le probe imprime `has_moved` et `is_turn_of_unit` à chaque bras et **refuse de conclure**
(`rc 3`) si le flag s'est évaporé ou si le préfixe n'est pas FAUX : sans ce cran, l'accord du bras
hors-tour serait un accord de régime DÉGÉNÉRÉ.

## 6. La garde

`tests/engine/runner/test_287r11r1r1r2_is_turn_of_unit_offline.py`, **12 tests / cinq étages** : le
slot et son arité lus dans la table ; les cinq issues du mirror ; le câblage et la DIRECTION du
tri-état ; la BORNE (une ability sans le bit ne consulte jamais le préfixe — avec un compteur
d'appels, sans quoi le test passerait par coïncidence, les deux verdicts valant 0) ; le gravage des
trois bras live et le MUTANT, qui **assertionne son propre non-vide**.

Vue rouge sur l'arbre témoin (`git archive` de la base, arbre COMPLET) : **10 failed / 2 passed** ;
**12 passed** après. Les 2 verts du témoin sont l'étage 1 (la table disait la vérité depuis toujours)
et le bras EN-TOUR (comportement conservé) — le diagnostic, pas une faiblesse.

## 7. Ce qui n'est PAS couvert

* **Le joueur TEMPORAIRE** (`TurnComponent+0x28`) — aucun canal ne le publie ; borne nommée en §2.
* **Le contrôle mental** (`OwnerComponent+0x14`) : le port n'a qu'un champ `player` et `1164
  MindControl` n'est pas portée. Tant qu'elle ne l'est pas, `+0x10` et l'accesseur coïncident.
* **La face DÉCISION n'est pas touchée** : `CasterSubstrate.is_turn_of_unit` portait déjà le
  préfixe (#433-r4-r2-r1-r2-r2-r1-r1-r1-r4, 11 paires sur 42). Les deux faces restent deux
  RESTRICTIONS d'un seul natif à deux substrats.
* **Les autres porteurs du bit ne sont pas confrontés live** : le registre en compte 10
  (`1026`, `1058`, `1112`, `1115`, `1153`, `1163`, `1177`, `1186`, `1204`, `1222` — compte
  re-dérivé, ne pas le citer). Le préfixe ne dépend ni de l'ability ni de son masque, donc leur
  régime est identique — mais c'est un raisonnement, pas une mesure.
* **Rouges PRÉEXISTANTS rencontrés et reproduits À L'IDENTIQUE sur le témoin** (échec de MONTAGE,
  pas de port) : `test_419r1tr14r5r2r1r2r1r1_only_adjacent_live.py` (5 passed / 7 errors),
  `test_419r1tr14r5r2r1r2r1r1r4_melee_clamps_live.py` (2 passed / 6 errors),
  `test_419r1tr14r5r2r1r2r1_normal_attack_dynamic_rule_live.py` (3 passed / 6 errors). Le message
  est explicite : « aucun `genesSmnDecoy` sous clamp de melee -> le regime n'est pas monte ».

## 8. Résidus

Aucun ouvert par cette tranche.
