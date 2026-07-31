# case-343 — les deux routes tuile qui n'EMETTAIENT pas de cible (residu #336-r1)

Resolution du residu `case-302-4-population-cible-tuile.md` §5.2 : `1166 AberrantHypermorph` et
`1194 NovaShield` lisaient bien le domaine tuile mais rendaient `{"target": None, ...}`.

**Verdict : le natif emet TOUJOURS une cible tuile. Les deux ports etaient des BUGS.**
Probe : `scripts/python/probe_343_tile_target_emission.py` — garde :
`scripts/python/tests/engine/test_tile_target_emission_live.py`.

---

## 1. Le decompile tranche les deux d'un coup

`IdunBattle.AI.Playbook.BasePlaybook$$GetEligibleTargetsSelectable` fabrique, PAR entite eligible, un
struct de **0x128** octets dont `+0x10` est l'**entite cible** (`+0x08`/`+0x18` = le caster, `+0x20` =
`GetMainTile(entity)`, `+0x30` = la tuile du caster balayee). Les deux `EvaluateNonComparable` passent
CE champ en 3e argument :

| ability | chemin |
|---|---|
| 1194 | `...NovaShieldPlaybook$$EvaluateNonComparable` -> `IdunBattle.AI.Playbook.BasePlaybook$$GenerateAction(casterPosition, target, utility)` -> `IdunBattle.AI.ActionGenerators.UnitAction$$.ctor(position, target, abilityType)` |
| 1166 | `...AberrantHypermorphPlaybook$$EvaluateNonComparable` inline le meme ctor ; son utilite NOMME l'argument : `...AberrantHypermorphPlaybook$$GetUtility(caster, summonTile)` |

⇒ aucune de ces deux routes n'a de cible nulle, jamais.

**La degradation etait pire qu'un « target muet »** : `engine/ai/tactic.py` mirrore
`IdunBattle.AI.InputBuilder$$GenerateInputMessagesFromUnitAction`, qui n'emet un `ActiveAbilityMessage`
que si `action.Target != null`. Sans cible ni deplacement, l'action retombait sur
`{"kind": "finish"}` — **le moteur ne castait PAS l'ability du tout**. Mesure : bras ROUGE du probe,
`(None, None)` sur les 4 bras.

## 2. Trois etages corriges, dans cet ordre

1. **La cible** — emettre `ctx.tile_id_by_pos[argmax]` au lieu de `None` (les deux playbooks).
2. **L'ORDRE d'enumeration des cibles** — le selector natif est calcule **par position du caster**
   (`GetEligibleTargetsEntities` = `GetValidTargets(caster, position, ability)`), et
   `Bucket.AddAction` ne remplace que sur amelioration STRICTE : a utilite egale, **la premiere cible
   enumeree gagne**. L'RPC `abilityTargets` publie deux vues NON interchangeables — `fromHere`
   (position courante, ordre exact du selector) et `targets` (union sur toutes les tuiles de move).
   Le port balayait l'union. Mesure (1166, MC1_67/909, caster (1,0), ennemi (0,1)) : memes 3 tuiles,
   ordres differents — `fromHere = [(1,1),(2,0),(0,0)]` contre union-filtree `[(2,0),(0,0),(1,1)]` ;
   deux valent l'utilite 1, le natif emet `(1,1)`. Helper :
   `engine/playbook/noncomparable/_base.py::eligible_target_tiles`.
3. **Le ring de `GetMarkedTiles`** (1194 seulement) —
   `...NovaShieldAbility$$GetMarkedTiles` = `Target + AdjacentTiles(Target)` filtre `!IsTrenchTile`,
   et `AdjacentTiles` passe par `IdunBattle.Core.Services.TileQuery.u003CIterateAdjacentTilesu003Ed__8$$MoveNext`,
   dont le dernier gate est **INCONDITIONNEL** : `|elev(centre) - elev(voisin)| < 2` (la primitive que
   `engine.battle_query.is_adjacent` porte deja). Datapoint discriminant : centres (1,3)@elev4 et
   (1,4)@elev3 a EGALITE 107 avec un ring geometrique ; la porte retire 2 voisins de (1,3) (elev 2)
   et aucun de (1,4) -> 105 contre 107, et le natif emet (1,4).

## 3. Le poids BC `DislikeStartingTiles` — data-gap leve au passage

Le `_WEIGHT = 0.0` de `engine/ai/utilities.py::DislikeStartingTilesUtility` portait la consigne
« a confirmer live : si le poids BC est != 0, cabler ». **Confirme** : a utilite strictement egale
entre l'origine (1,0) et la tuile de move (0,0), le natif emet un `MoveUnitMessage` vers (0,0) — avec
un poids nul il resterait sur place (origine balayee en premier, remplacement STRICT). Valeur :
`Default/DislikeStartingTilesUtility/ActiveAbility_DislikesCurrentTiles = **-40**`, seule cle de la
categorie. Le live prouve le SIGNE, le BC donne la VALEUR ; l'identification de la cle est une
inference (la chaine passee a `GetUtilityValue` est un litteral IL2CPP non lisible statiquement).
**Seul consommateur dans la face DECISION : `nova_shield.py`.**

## 4. Confrontabilite

| item | porteur | chemin |
|---|---|---|
| 1166 | `genesBiophagus` (Hollan) | lineup, **dans `rl_duel build --list-pool`** — porteur naturel |
| 1194 | `tauBossRiptide` seul, **npc** | hors pool, refuse par `buildNormalizedBC` -> **greffe** sur `tauCrisis` (`case-92` §5bis) : le natif charge le playbook PAR ABILITY, et l'utilite de 1194 ne lit ni stats ni traits du caster |

## 5. Residus NOMMES

- **Ordre des cibles pour une tuile de MOVE** : aucun RPC ne rend `GetValidTargets(caster, T, ability)`
  pour `T != position courante` ; le port retombe sur l'ordre de l'union. Atteignable seulement si une
  tuile de move ameliore STRICTEMENT l'utilite. Debloqueur : un parametre de position sur
  `abilityTargets`.
- **`1096 MasterOfTheTutelaries`** porte la MEME approximation d'ordre (union filtree) et n'a pas ete
  touchee (hors perimetre) — meme correctif applicable via `eligible_target_tiles`.
- **`...NovaShieldPlaybook$$ShouldEvaluate`** n'est pas porte : le natif fait
  `IBattleQuery.HasMinimumRemainingTurns(unit, 2) && base.ShouldEvaluate(unit)` (arite 2 -> la methode
  est forcee, cf. §6). Vrai dans une bataille fraiche, donc invisible sur les montages joues.
- **Filtre `!IsTrenchTile`** de `GetMarkedTiles` : non porte (aucune tuile Trench sur les boards
  confrontes). Les 3 flags optionnels de `IterateAdjacentTiles` (temporary / walkable /
  emptyOrSteppable) ne sont pas appliques non plus : la chaine d'offsets qui les relie aux arguments
  `(tile, 0, 1, 1)` du selecteur est ambigue, et la lecture « emptyOrSteppable exclut les tuiles
  OCCUPEES » est **REFUTEE live** (elle ferait emettre (0,3), pas (1,4)).

## 6. Piege d'outillage : l'ancrage de la vtable IBattleQuery est ambigu a ±1 slot

`probe_38b_vtable.py` ancre le bloc d'interface sur `ReachedSummonCap = slot 0xc9`. Avec cet ancrage,
9 des 10 slots documentes concordent — **mais tous ont ete derives par le MEME ancrage**, ce n'est donc
pas un controle independant. Deux call-sites le contredisent d'un cran :

- `...NovaShieldPlaybook$$ShouldEvaluate` appelle le slot `0x1b` avec **2 arguments** ; l'ancrage y
  place `ConvertRoundsToTurns` (**1** argument) et `HasMinimumRemainingTurns` (2 arguments) est en
  `0x1a`. L'arite force `HasMinimumRemainingTurns`.
- `...TheQuickeningPlaybook$$GetNumAttackTargetsInPosition` appelle le slot `0x80`, ou l'ancrage place
  `GetAdjacentFriends`.

⇒ **citer le SYMBOLE, pas le slot.** Pour 1166 la conclusion tient malgre l'ambiguite : les slots
`0x7c..0x7f` sont TOUS des surcharges de `GetAdjacentEnemies`, et le nom de parametre
`GetUtility(caster, summonTile)` la confirme independamment.
