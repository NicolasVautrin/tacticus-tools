# case-443-r1 — `SaviorProtocols` (1120), face MOVE : quatre artefacts, un seul à porter

Résidu `#443-r1`. La face ATTACK a été portée par #443 ; la face MOVE n'avait **pas été lue**, et
son absence de `TRIGGERED_MOVE_PLAYBOOKS` était un TROU, pas le comportement natif — contrairement
à `SuppressiveFire` (#419) et `Neuroparasite` (#441), dont les faces MOVE sont des `yield 0`.

## 1. Qui porte quoi — la question à trancher AVANT de porter

Quatre artefacts natifs portent le nom `SaviorProtocols`. **Trois seulement concernent la face
MOVE du playbook**, et le quatrième était déjà porté :

| artefact natif | rôle | statut |
|---|---|---|
| `SaviorProtocolsPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__4$$MoveNext` | la feuille MOVE elle-même | **porté (#443-r1)** |
| `SaviorProtocolsAbility$$TargetIsValidTrigger` | le prédicat DSL, partagé avec la face COMBAT | **porté (#443-r1)**, inliné dans la feuille |
| `SaviorProtocolsPlaybook$$FilterMovementTiles` | slot 1 d'`IPlaybook` | **non porté** — INERTE sur tout porteur connu (§4) |
| `IdunBattle.AI.Utilities.SaviorProtocolsUtility` | feuille `UtilityType.SaviorProtocols(23)`, **le même passif pris à l'ENVERS** | **déjà porté**, `engine/utilities/tile.py` — relu conforme |

La 4ᵉ classe n'a **rien à voir** avec le playbook : elle est la feuille du **PROTÉGÉ**.
`$$CanBeProtector(unit) = HasFaction(unit, 9) && !HasTriggeredAbility(unit, 0x460)` gate le MOVER,
et `$$GetUnitsWithUtilityForMove` compte
`UnitsWithTriggeredAbility(GetFriendsAdjacentToMovementTile(case), 0x460)`, multiplié par
`$$GetUtilityPerUnit` = `SaviorProtocols.PerUnitWithAbilityInRange`. Le port existant
(`_ability_count(meta, 1120) * wt.sub("SaviorProtocols", "PerUnitWithAbilityInRange")`, gate
`unit_faction == 9 and 1120 not in unit_triggered_abilities`) en est le mirror exact — vérifié, non
modifié. Le playbook, lui, est le point de vue du **PROTECTEUR**.

## 2. Le corps MOVE

La SM `d__4` dispose ses champs **AUTREMENT** que la face sœur de la MÊME classe — c'est le piège
propre à cette famille, et il se lit dans la méthode-usine, jamais par transposition :

| state machine | +0x20 | +0x28 | +0x30 |
|---|---|---|---|
| `SaviorProtocolsPlaybook.d__4` (MOVE) | **playbook** | case | délégué scorer |
| `SaviorProtocolsPlaybook.d__5` (ATTACK) | case | **playbook** | délégué scorer |
| `BarbedOvipositorPlaybook.d__5` | case | délégué scorer | — |

Corps, remis en C# :

```csharp
Fix64 x = Fix64.op_Implicit(0);
foreach (var u in this.<>4__this.<query>.GetAdjacentUnits(          // slot 0x7a de l'IBattleQuery
              case.MovementTile, friendsOf: null, enemiesOf: null, ignoreSteppables: false))
{
    var trigger = SaviorProtocolsAbility.TargetIsValidTrigger(this.<>4__this.<ability@+0x58>);
    var tctx = new <TriggerContext>(0x128 octets, zéro) { [+0x10] = u, [+0x18] = case.Unit };
    if (trigger.<vslot +0x188>(tctx, 0x20)) {
        x += Fix64.op_Implicit(GetUtilityValue("SAVIORPROTOCOLS_AdjacentTauFriend"));    // 20
        if (UnitExtensions.GetParent(case.Unit, state) == u)
            x += Fix64.op_Implicit(GetUtilityValue("SAVIORPROTOCOLS_AdjacentTauParent"));  // 30
    }
}
yield return x;
```

### 2.1 Le slot `0x7a` — identifié, pas deviné

`GetAdjacentUnits` est **surchargée trois fois**, et le décompilé ne nomme pas le slot. Il est
tranché par **le compte et l'ordre des arguments** (4 après `this`) confrontés aux signatures que
le décorateur nomme — `RecordedSimulationRequestsBattleQuery$$GetAdjacentUnits(from|tiles,
friendsOf, enemiesOf, ignoreSteppables)` — puis **corroboré par le SEUL autre call-site du même
slot dans tout le binaire** : `ExemplarOfTheKauyonAbility$$GetDynamicInvalidTargetReason`, qui lui
passe une TUILE (vérifiée `TileExtensions$$IsFreeTile` juste avant), donc l'overload TUILE.

Les trois arguments suivants sont les littéraux `0, 0, 0` : **aucun filtre de camp** (c'est le
trigger, plus bas, qui trie ami/ennemi) et **steppables INCLUS**. L'adjacence est celle de
`TileQuery$$IterateAdjacentTiles`, donc avec la porte d'élévation `|Δ| < 2` — `battle_query.
is_adjacent`, jamais `hexgeo.distance == 1` nu (#271).

### 2.2 `Target` et `Owner` — tranchés par les SÉLECTEURS, pas par convention

Le contexte du trigger est construit **à la main** dans la SM, et rien dans le corps ne nomme ses
champs. Ils sont identifiés par ce que lisent les sélecteurs eux-mêmes :

* `IdunBattle.Entities.Selectors.TargetSelector$$Select` lit `context+0x10` ;
* `IdunBattle.Entities.Selectors.OwnerSelector$$Select` lit `context+0x18` ;
* `IdunBattle.Entities.Selectors.ActorSelector$$Select` lirait `context+0x00`, qui reste NUL ici.

Le corps écrit `+0x10 = u` (le voisin) et `+0x18 = case.Unit` (le mover). Donc **`Target` = le
voisin, `Owner` = le mover**. Inverser les deux rendrait le terme **constamment nul** : le mover
porte 1120, et le prédicat exige justement que son sujet ne le porte PAS.

Le même bundle de sélecteurs (`<ability+0x28>+0x90`, `+0x60` = Target, `+0x30` = Owner) est celui
que lisent `$$CreateTrigger` (`IsAdjacent(Owner, Target)`) et `$$CreateBehaviour`
(`TransferDamage(…, Target, Owner, …)`) — les deux confirment le sens : le drone (Owner) encaisse
à la place de l'allié (Target).

### 2.3 `TargetIsValidTrigger` — quatre nœuds

```
AreFriends(Target, Owner)
& HasFaction(Target, 9 = UnitFaction.Tau, 3)
& !ActorHasTriggeredAbility(Target, 0x460 = 1120 SaviorProtocols)
& !AreEqual(Target, Owner)
```

« Ce voisin est un allié T'au que je peux PROTÉGER » — un autre porteur de 1120 est exclu (il se
protège seul). Aucun `On(<event>)` n'entre dans CET arbre (le `On(0x39)` vit dans `$$CreateTrigger`),
donc le `0x20` passé au slot d'évaluation n'a aucun sujet à filtrer.

### 2.4 Le bonus PARENT est IMBRIQUÉ, pas parallèle

`+AdjacentTauParent` n'est versé que **dans** la branche du prédicat : un summoner qui porterait
lui-même 1120, ou d'un autre camp, ne vaudrait NI 20 NI 30. `UnitExtensions$$GetParent(case.Unit,
state)` est le lien enfant → summoner (`ChildComponent.ParentId`), disponible des deux côtés depuis
#378 (`Scene.parent` / `runner.components.parent_of`). Le porteur naturel de 1120 étant un SUMMON,
ce terme désigne **le drone qui reste collé à son invocateur**.

### 2.5 Les deux clés — résolues par leur SLOT, pas par leur nom

`probe_212_bc_key_literals.py` (chaîne `slot → token → `global-metadata.dat``) rend, **dans l'ordre
d'apparition dans le corps** : 1ᵉʳ scorer = `SAVIORPROTOCOLS_AdjacentTauFriend` (BC = 20),
2ᵉ = `SAVIORPROTOCOLS_AdjacentTauParent` (BC = 30). L'attribution n'est donc pas déduite du nom.

## 3. Le canal `unit_parent_id`

`GetParent(case.Unit)` n'avait aucun pendant dans le `ctx` tile-leaf. La clé `unit_parent_id` est
posée dans **les deux** producteurs (`tile_leaf_ctx` côté décision via `Scene.parent`,
`runner_tile_leaf_ctx` côté runner via `components.parent_of`). ⚠ À ne pas confondre avec le
paramètre `parent_id` de `runner_tile_leaf_ctx`, qui est le `dc.parent` du call-site SUMMON
(case-205) : celui-là est un sujet de REMPLACEMENT quand `case.unit` est nul, celui-ci est le parent
DU SUJET. Absente, la clé ne fait taire que le terme PARENT — le terme FRIEND reste versé.

## 4. La mesure — trois régimes sur le porteur NATUREL, cinq contre-épreuves qui mordent

Le montage de mesure est celui de #443 **repris tel quel** (`tauMarksman` tire son attaque RANGED
1076, le drone `tauSmnDroneSniper` naît adjacent), plus **trois voisins amenés après le tir**, un
par nœud du prédicat. C'est le seul état où `GetParent(case.Unit)` est non nul : le probe REFUSE de
mesurer si `unit_parent_id` ne vaut pas l'id du summoner.

`MC1_67` / seed 41504, 19 tuiles balayées autour du drone, poids servis 20 et 30 :

```
tuile      terme  attendu  adj_parent  voisins qualifiés
(0, 3)     20     20       False       ['tauCrisis']          <- ami T'au NON-parent
(2, 3)     50     50       True        ['tauMarksman']        <- le SUMMONER : 20 + 30
(1, 3)     0      0        False       []
...
régimes atteints : termes distincts = [0.0, 20.0, 50.0]
  tuiles adj. au PARENT = 6 ; tuiles à ami T'au NON-parent = 3 ; non conformes = 0
exposition des contre-régimes : {ultraTitus: 3, tauDarkstrider: 3, tauShadowsun: 3}
```

Le régime à **20** est ce qui SÉPARE les deux poids : 50 tout seul ne distinguerait pas `20 + 30`
d'un forfait. L'attendu est calculé depuis le `decisionView` + `faction_value` + le kit **LIVE**
(`unitAbilityStates`) — donc **sans passer par le playbook testé**. Les trois voisins-témoins sont
chacun adjacents à 3 tuiles balayées : leur « 0 » n'est pas un zéro d'absence.

Cinq mutations du port, re-jouées sur la MÊME mesure, restauration vérifiée après chacune :

| # | mutation | verdict |
|---|---|---|
| CE1 | clé `AdjacentTauFriend` -> `AdjacentTauParent` | **MORD** — 9 tuiles changées |
| CE2 | gate `HasFaction(Target, 9)` retiré | **MORD** — 3 tuiles (`ultraTitus` compterait) |
| CE3 | gate `!ActorHasTriggeredAbility` retiré | **MORD** — 3 tuiles (`tauDarkstrider`, 1120 greffé) |
| CE5 | gate `AreFriends` retiré | **MORD** — 3 tuiles (`tauShadowsun`, ennemi T'au) |
| CE4 | entrée 1120 retirée de `TRIGGERED_MOVE_PLAYBOOKS` | **MORD** — 9 tuiles |

### 4bis. Ce qui N'EST PAS couvert — le terme MOVE n'est PAS confronté au natif

**Résidu `#443-r1a`.** L'oracle natif du composite `Tile(7)` par tuile est le hook
`scorerTileTermTrace` ; il n'attribue **aucune** évaluation au porteur. Trois faits de harnais,
mesurés, chacun ayant produit une mesure vide ou fausse :

1. **`aiStepDryRun` ne fait firer AUCUN hook** (0 `tileTerm` / `elev` / `damage`, y compris au dump
   GLOBAL sans filtre d'origine) alors qu'il rend bien `Move` + `ActiveAbility` ;
2. **un état déjà scoré n'est pas RE-scoré** : le `decisionView(allAbilities, maxRank=32)` de la
   mise en place score le porteur, et tout ce qui suit ne capte plus que les autres unités ;
3. **l'event du hook ne porte pas d'`unitId`** — sur `MC1_67`/777, les 4 events captés sont TOUS
   sur des tuiles **occupées par un tiers**, aucun sur une tuile du porteur. Une version antérieure
   du probe, qui ne filtrait pas, a rendu un **accord parfait sur le `Tile(7)` d'une AUTRE unité** :
   le filtre « tuiles attribuables au porteur » est load-bearing, et c'est lui qui a démasqué le
   faux positif.

Le porteur naturel étant un SUMMON, il n'entre de toute façon jamais dans `toActivate` (#291).
**Point d'ancrage à hooker** pour ouvrir cette confrontation :
`IdunBattle.AI.Utilities.TriggeredAbilitiesUtility.u003CEvaluateMovementInStepsu003Ed__2$$MoveNext`
(la feuille dispatcher, PAR TUILE, avec l'`unitId` du mover) — il demande un reinject.

Non couvert également : les **cinq autres porteurs** (3 npc, `tauSmnDroneShield`,
`tauSmnDroneCommandLink`) ; le corps ne lisant du mover que son équipe et son parent, ils
n'ajouteraient aucun régime, mais ce n'est pas mesuré.

### 4ter. Un résidu TROUVÉ EN PASSANT — `probe_193c` retranche les mauvaises feuilles

**Résidu `#443-r1c`**, hors périmètre. `probe_193c._port_leaves` est consommé avec
`leaves.get(8) - leaves.get(9)` sous le commentaire « 8=Elevation 10=TileEffects ». Or la
renumérotation de `UtilityType` (#252, `AttackTile` INSÉRÉ en 8) a décalé l'enum : aujourd'hui
`Elevation = 9` et `TileEffects = 10`. Le probe retranche donc une feuille **inexistante** (8) et
`Elevation` (9), et **jamais** `TileEffects`. Le cliquet `probe_283 --step prose` l'a attrapé sur la
copie faite dans ce probe-ci ; le porteur d'origine n'est pas corrigé par cette tranche.

## 5. `FilterMovementTiles` — inerte sur tout porteur connu (résidu `#443-r1b`)

Le playbook surcharge aussi le slot 1 d'`IPlaybook` (non porté globalement, `case-r1b`). Son corps
ouvre sur `if (UnitExtensions.HasRangedWeapon(unit)) return;` — **court-circuit total**. Les six
porteurs de 1120 (3 npc `tauNpc{2,3,4}Drone*`, 3 summons `tauSmnDrone{Sniper,Shield,CommandLink}`)
portent une arme à distance, donc ce filtre ne retire AUCUNE tuile en bataille : ne pas le porter
n'introduit pas d'écart observable. Le régime « porteur sans arme à distance » n'est atteint par
aucun porteur connu ; le corps y garderait les tuiles ayant un protégeable valide dans le rayon
rendu par le slot `0x77` — signature `(from, range = 2, includeCenter = 0)`, donc vraisemblablement
`GetSurroundingUnits`, **NON tranché** faute d'un second call-site nommé du même slot.

## 6. Fichiers

* Port : `scripts/python/engine/playbook/savior_protocols.py` (la MÊME classe porte les deux faces,
  comme le natif, qui n'a qu'un singleton par type) ; registre :
  `engine/playbook/adjacent_unit_preference.py` ; canal parent : `engine/utilities/tile.py`.
* Mesure : `scripts/python/probe_443r1_savior_protocols_move_term.py` — bras `--parent` (celui qui
  conclut) et bras GREFFE par défaut (celui qui ÉTABLIT que l'oracle natif est indisponible, §4bis).
* Garde : `scripts/python/tests/engine/test_443r1_savior_protocols_move_term_live.py` (5 tests).

⚠ **Numérotation** : la tranche a été dispatchée sous « #448 », mais `#448` désigne déjà Stormboyz
dans le dépôt (`case-448-r1/r2*`, `probe_448_r*`). Elle ferme littéralement le résidu `#443-r1`, et
tous ses artefacts sont nommés d'après lui.
