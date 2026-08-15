# #419-t6 — `CosmicHorror` (1277), face ATTACK : PORTÉ + CONFRONTÉ LIVE

Sixième tranche des résidus ATTACK de `#419-r1`. Porteurs : **4** — `genesPatriarch` (HERO, **au
pool** `rl_duel build --list-pool`) et 3 npc (`genesBossPatriarch`, `genesBossPatriarchLHE`,
`genesNpcPatriarch`). Ni MoW, ni summon. Le porteur HERO suffit : aucune injection catalogue,
aucune greffe.

Re-dérivation de l'inventaire : `python scripts/python/probe_419_triggered_playbook_inventory.py
--residuals`.

## 1. Ce que dit le décompilé

`IdunBattle.AI.Playbook.Loki.CosmicHorrorPlaybook$$CalculateAttackUtilityInStepsInternal` monte la
SM `d__3` — disposition LUE dans ce wrapper, jamais par analogie : `sm@+0x20 = case`,
`sm@+0x28 = this` (le playbook), `sm@+0x30 = getUtilityVal`, `sm@+0x10 = 0`. Même forme à trois
champs que `SaviorProtocolsPlaybook.d__5`, pas celle de `BarbedOvipositor` (deux champs), et pas
celle de la face MOVE de la MÊME classe (`d__2`, qui n'écrit que l'état).

`IdunBattle.AI.Playbook.Loki.CosmicHorrorPlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$MoveNext`
— UN seul `yield` :

```csharp
int v = 0;
Tile tile = case.CasterPosition.MainTile;                  // UtilityAttackCase@+0x18
IEntity u = UnitExtensions.GetUnit(tile, this.<>4__this.State);
if (u != null && UnitExtensions.HasTrait(u, 0x41d /* UnitTrait.Decoy */)
              && UnitExtensions.IsFriend(u, case.Caster /* @+0x10 */, state))
    v = getUtilityVal("COSMICHORROR_StepOnDecoyToAttack");
yield return Fix64.op_Implicit(v);
```

Cinq lectures qui ne se devinent pas :

1. **La tuile lue est celle du CASTER.** Le symbole du getter est
   `IdunBattle.AI.Utilities.UtilityMovementCase$$get_MovementTile` — corps
   `UnitPosition.get_MainTile(this + 0x18)` **dédupliqué par l'ICF**. Sur un `UtilityAttackCase`,
   `+0x18` est `CasterPosition` (lu au `$$.ctor` et aux trois usines `$$Base` /
   `$$ForDamagePrediction`). Le nom du symbole désigne le propriétaire du corps, pas le type
   réellement passé : s'y fier ferait lire « la tuile de mouvement » d'un case d'attaque.
2. **`GetUnit(tile, state)` est l'OCCUPANT**, pas le caster. La surcharge appelée est la
   polymorphe (xref entrant depuis `d__3$$MoveNext`) : entité rendue telle quelle si c'est une
   unité, `TileContentComponent.IsFilled` → entité contenue si c'est une tuile, remontée au parent
   si c'est un pied. Une tuile n'a qu'UN occupant.
3. **C'est donc un terme de TUILE D'ATTAQUE, pas de cible** — le seul playbook attack porté à ce
   jour dont la sortie ne dépend d'AUCUNE propriété de la cible. Il ne vaut que dans le régime où
   le caster attaque depuis une tuile déjà occupée, possible parce que
   `IdunBattle.Entities.TileExtensions$$IsEmptyOrSteppable` laisse les tuiles à occupant
   `Steppable` dans le movable set. Le nom de la clé le dit : `StepOnDecoyToAttack`.
4. **`0x41d` = 1053 = `UnitTrait.Decoy`** — enum à QUALIFIER : à id égal, `TriggeredAbilityType`
   1053 = `BroodProgenitor`, `ActiveAbilityType` 1053 = `DevoutPush`, `EffectType` 1053 =
   `ShadowInTheWarp_LessDmg_Effect`. ⚠ Le natif ne filtre **pas** sur `Steppable` ici (contrairement
   à `TileExtensions$$GetSteppableUnit` de la feuille MOVE 20) : il prend l'occupant tel quel.
   Les deux traits coïncident sur les deux seuls porteurs du catalogue (`genesDecoy` npc et
   `genesSmnDecoy` summon portent `['Steppable', 'Decoy']`) — coïncidence de DONNÉES, pas le gate.
5. **La sortie est un poids BC**, string literal du corps (pas de `.cctor` sur cette classe) :
   `COSMICHORROR_StepOnDecoyToAttack`, **LU** par `probe_212_bc_key_literals.py` sur ce symbole
   (slot `+0x3371c38`). `Utilities.Default.TriggeredAbilities` : **10** au seed BC servi **et** 10
   au gameconfig vivant → pas de piège #271.

**Le piège du NOM, vérifié** : `1277` vaut `TriggeredAbilityType.CosmicHorror` (l'artefact porté),
`EffectType.TheWildHost_Tile`, et **rien** en `ActiveAbilityType`. Aucune face de 1277 n'était déjà
portée.

Le gate d'ami rejoue, en sens INVERSE, la branche Decoy de `SteppableUnitUtility` (feuille MOVE
20) : celle-ci PÉNALISE de −50 (`SteppableUnit.FriendlyDecoy`) le fait de marcher sur son propre
leurre, ce playbook-ci en REND 10 quand la tuile sert à attaquer. Les deux ne s'annulent pas (deux
composites distincts, Tile(7) contre Damage(34)) — le Patermine n'écrase son leurre que s'il y
gagne une attaque.

## 2. Face MOVE : `yield Fix64(0)` CONSTANT — décompilé LU

`CosmicHorrorPlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext` est un
unique `yield return Fix64.op_Implicit(0)` ; son wrapper n'écrit même pas le case dans la SM.
`probe_212` confirme : aucun string literal lu. Son absence de `TRIGGERED_MOVE_PLAYBOOKS` EST le
comportement natif — même forme que `Lakrimae`, `BarbedOvipositor`, `Neuroparasite`, à l'inverse de
`SaviorProtocols` (résidu `#443-r1`).

## 3. Le montage — le kit du porteur FABRIQUE lui-même son substrat

Aucune injection, aucune greffe : la face COMBAT de la MÊME ability 1277 « places a decoy on the
hex of that enemy » quand le Patermine défait un ennemi. Le montage est donc dans le régime naturel
du jeu — un Patermine tue une proie fragile à l'écart, la cible de mesure est amenée ENSUITE contre
le leurre, et on mesure la même paire (caster, cible) depuis **trois** tuiles d'attaque toutes
adjacentes à la cible :

| tuile | occupant | terme attendu |
|---|---|---|
| `D` | le leurre | le poids (régime `friend`) / 0 (régime `enemy`) |
| `F` | rien | 0 |
| `C` | le CASTER lui-même (ami, NON leurre) | 0 |

`C` est ce qui rend le montage discriminant sur le gate `HasTrait` : un port qui l'oublierait
passerait `D` et `F`.

**Les DEUX sens du gate `IsFriend`.** Un leurre ami ne prouve que le sens passant. Le régime
`--regime enemy` refait le montage avec un **second Patermine, ADVERSE**, qui tue une de NOS unités
— le leurre qu'il laisse appartient à SON camp. Toute la géométrie est identique ; seul le camp du
leurre change.

**Quatre pièges de montage, MESURÉS** :

* **Tout `endturn` rend la main à l'IA, qui éloigne la proie.** Un `applyAction` d'attaque posé
  après un tour perdu échoue en silence. Le kill re-place (`_drive_to` compense) puis frappe DANS
  LE MÊME TOUR, et la légalité du cast est lue à `abilityTargets.fromHere`, jamais au retour de
  `applyAction`.
* **`decisionView.units[].traits` vaut `null`** sur ce runner : une attestation « c'est bien un
  leurre » bâtie dessus rend FAUX sur un montage pourtant correct. Le trait est lu au canal
  `combatSnapshot.units[].traits` (ids `UnitTrait` de l'ECS) — source **indépendante** du substrat
  que consomme le port, donc un port aveugle aux traits ne peut pas se faire valider par sa propre
  cécité.
* **Une proie qui INVOQUE pollue la géométrie** : `astraCreed` fait apparaître `astraSmnKell`, qui
  occupe des tuiles du montage. Proie et cible sont prises dans les unités du pool dont aucune
  ability ne mentionne summon/spawn/place.
* **La tuile témoin `F` ne se dérive pas hors-ligne** : un `F` choisi par `_gated_path` (qui ignore
  les occupants et le coût réel) tombe couramment hors du movable set, et `pairUtility` la refuse.
  Elle est choisie APRÈS le montage, dans `ctx.action_tiles` réelles.

Le kill a lieu à `>= 3` de la cible : la même ability pose `Suppressed` sur les ennemis
**entourant** le défunt avec une CHANCE (60 % au palier haut, `DisableRandomness = false` au seed
BC). Tuer à côté de la cible rendrait son état aléatoire d'un run à l'autre.

## 4. Mesures (`MC1_67` / seed `51277`, `genesPatriarch`)

`genesPatriarch` n'a **qu'un** triggered (`kit_triggered_ability_ids` = `{1277}`) : la feuille ne
peut mélanger aucun autre terme.

Régime `friend` (leurre `u99 genesSmnDecoy`, traits ECS `[27, 1006, 1053]`, ami) :

| tuile | natif | port | port muté | manque |
|---|---|---|---|---|
| `D` (3,4) | 11.320493 | 11.320493 | 1.320493 | **+10.000000** |
| `F` (4,5) | 0.879996 | 0.879996 | 0.879996 | −0.000000005 |
| `C` (3,5) | 0.879996 | 0.879996 | 0.879996 | −0.000000005 |

Régime `enemy` (leurre `u133`, mêmes traits, **ennemi**) :

| tuile | natif | port | port muté | manque |
|---|---|---|---|---|
| `D` (3,4) | 1.320493 | 1.320493 | 1.320493 | +0.000000010 |
| `F` (4,5) | 0.879996 | 0.879996 | 0.879996 | −0.000000005 |
| `C` (3,5) | 0.879996 | 0.879996 | 0.879996 | −0.000000005 |

**La mesure qui tranche le gate d'amitié** : la MÊME tuile `D`, même géométrie, même cible — le
**natif lui-même** rend `11.320493` avec un leurre ami et `1.320493` avec un leurre ennemi, soit
exactement le poids `10.000000` d'écart. Aucune autre mesure ne distingue `IsFriend(u, case.Caster)`
de « il y a un leurre ».

**Pas de résidu** : `|port − natif| < 1.1e-8` sur les six points (Fix64 natif contre float du
port). Cette paire n'a donc pas l'écart constant de #446, et le test asserte le NIVEAU.

Contre-épreuves (critère = déplacement vs le port NON MUTÉ, **jamais** l'écart au natif — piège
#441) :

| mutant | `friend` | `enemy` |
|---|---|---|
| `no_trait` (gate `HasTrait` retiré) | MORD (`C` +10) | MORD (`C` +10) |
| `invert_friend` (gate `IsFriend` inversé) | MORD (`D` −10) | MORD (`D` **+10**) |
| `target_tile` (tuile de la CIBLE lue) | MORD (`D` −10) | inerte — le port rend déjà 0 partout |

L'inertie de `target_tile` en `enemy` est un RÉSULTAT, pas un défaut : ce mutant ne peut que
RETIRER le terme, et ce régime n'en verse aucun. La table `MUST_BITE` du probe porte cette
distinction, et le test rougit AUSSI si un mutant mord là où il ne devrait pas.

**Le test peut rougir — vérifié par mutation du port lui-même** (et non du seul mutant en
mémoire) : gate `IsFriend` retiré → **5 échecs / 9**, dont
`test_cosmic_horror_friend_gate_has_the_right_sign` ; gate `HasTrait` retiré → **7 échecs / 9**.
Restauration → 9 verts.

## 5. Substrat côté port — ni canal neuf, ni patron « porté + INERTE »

Le corps ne lit ni stats, ni effets, ni prédiction : uniquement la position d'attaque et l'occupant
de cette tuile. `attack_tile` est déjà le 5ᵉ paramètre du dispatcher
(`utilities/tile.py::evaluate_attack_in_steps`), l'occupant se lit sur `Scene.pos_by_id` +
`units[].alive`, et le trait par le foyer partagé
`playbook/prediction/_shared.py::_entity_traits` (tri-état, mesuré). Aucune pièce n'était à poser
par un tiers — contrairement à `Lakrimae` (canal live du kit) et `BarbedOvipositor` (canal
`prediction`). `prediction` est accepté et IGNORÉ, comme le corps natif.

## 6. Non couvert

* ~~**Occupant `Decoy` NON `Steppable`**~~ — **COUVERT depuis le 2026-08-15 (`#419-t6-r1`), §8.**
  La prémisse tenait (les 2 seuls porteurs de `Decoy` du catalogue portent aussi `Steppable`,
  re-mesuré sur `t6dpr4k06g`) ; ce qui était faux, c'est « il n'existe aucune donnée » — **le
  porteur se FABRIQUE**.
* **Tuile d'attaque occupée par un `Steppable` NON leurre** — même cause : les deux porteurs de
  `Steppable` du catalogue Genestealer portent aussi `Decoy`. La tuile `C` (occupant ami, non
  leurre) en est le substitut le plus proche et suffit à faire mordre `no_trait`.
* **Les 3 porteurs npc** (`genesBossPatriarch`, `genesBossPatriarchLHE`, `genesNpcPatriarch`) ne
  sont pas confrontés directement ; ils exécutent le MÊME corps natif, chargé PAR ABILITY, et
  l'utilité ne lit ni stats ni traits du caster.
* **Unité multi-tuiles sur la tuile d'attaque** — le natif remonte au parent (`GetUnit` sur un
  pied) ; le port lit la `MainTile` de `pos_by_id`, ce qui rend la remontée implicite mais n'a pas
  été exercé (aucun leurre n'est multi-tuiles).

## 7. Livré

* `scripts/python/engine/playbook/cosmic_horror.py` — le port, RE en tête.
* `scripts/python/engine/playbook/psyker.py` — entrée `TRIGGERED_ATTACK_PLAYBOOKS[1277]`. Ability
  **TRIGGERED** : ni `TARGETING_OPTIONS` ni `ABILITY_ATTACK_TYPE` (ces registres sont ceux des
  ACTIVES).
* `scripts/python/probe_419_t6_cosmic_horror_pair_term.py` — montage nommé, deux régimes, mutants.
* `scripts/python/tests/engine/test_419_t6_cosmic_horror_pair_term_live.py` — la garde jumelle
  (9 tests).

## 8. `#419-t6-r1` — le gate `HasTrait(Decoy)` SEUL, MESURÉ (`BLOCAGE: porteur` tombe)

Le résidu portait `BLOCAGE: porteur`. La prémisse **tient** — re-mesure sur `t6dpr4k06g` : les deux
seuls porteurs de `Decoy` du catalogue (`genesDecoy` npc, `genesSmnDecoy` summon) portent
`['Decoy', 'Steppable']`. Ce qui était faux, c'est la conclusion : **le porteur se fabrique**.

`catalog_inject.add_unit_trait(bc, 'genesPatriarch', 'Decoy')` écrit `BC.Units[].Traits`, que
`buildNormalizedBC` **LIT sans jamais l'ÉCRIRE** — l'injection survit à la normalisation. Le
Patermine ne porte NI `Decoy` NI `Steppable` (`Hero, Infiltrate, Synapse, Terrifying, Unstoppable`),
donc l'accorder produit exactement le porteur manquant.

**Et c'est le CASTER qu'on équipe, par lecture et non par commodité.** Une tuile n'entre dans les
tuiles d'action que si elle est vide ou si son occupant est `Steppable`
(`IdunBattle.Entities.TileExtensions$$IsEmptyOrSteppable`) : un leurre NON `Steppable` posé à côté
serait structurellement hors du movable set, et `pairUtility` refuserait la tuile — le régime serait
**inatteignable** par cette voie. La tuile COURANTE du caster, elle, est toujours acceptée : c'est la
tuile `C` de §3, celle qui y rend 0 parce que son occupant est ami mais **pas** leurre. Le
discriminant est donc la tuile témoin de la tranche précédente, **retournée**.

`IsFriend(u, case.Caster, state)` avec `u == caster` passe trivialement :
`IdunBattle.Entities.UnitExtensions$$IsFriend` compare `GetCurrentPlayer(x).<+0x20>.<+0x24>` des
deux côtés, **sans aucune exclusion de l'identité** — lu, pas supposé.

### Mesure (`MC1_67` / seed `51278`, deux runners, disposés)

| bras | `C` = tuile courante du caster | `F` = tuile libre voisine de la cible |
|---|---|---|
| SANS le trait | natif **1.320493** / port 1.320493 → terme **+0** | 0.879996 → +0 |
| AVEC le trait | natif **11.320493** / port 11.320493 → terme **+10.000000** | 0.879996 → +0 |

Le seul écart entre les deux runners est le trait accordé, et le **natif lui-même** bouge du poids
exact. Écart natif↔port **NUL** sur les 4 lignes. Traits ECS du caster au bras AVEC :
`[16, 34, 1004, 1006, 1042, 1053, 2024]` — `Decoy` (1053) présent, `Steppable` (27) **absent**, lu
au canal `combatSnapshot.units[].traits`, source indépendante du substrat que consomme le port.

### Les contre-épreuves, et pourquoi elles ne sont pas colinéaires

* `steppable_too` (le gate `Decoy && Steppable`, c'est-à-dire **exactement le port que #419-t6 ne
  pouvait pas écarter**) : perd le poids sur `C` **dans le bras AVEC** → 1.320493 contre un natif à
  11.320493, **divergence de 10**.
* `no_trait` : gagne le poids sur `C` **dans le bras SANS** → 11.320493 contre un natif à 1.320493,
  divergence de 10.

Chacune est **inerte dans l'autre bras**, et la garde l'assertionne dans les deux sens : le montage
exerce deux faits distincts, pas deux fois le même.

### Livré

* `scripts/python/probe_419t6r1_decoy_sans_steppable.py` — montage nommé, deux bras, deux mutants ;
  il **lève** si le porteur fabriqué porte aussi `Steppable` (le montage retomberait alors dans le
  régime que #419-t6 ne séparait pas).
* `scripts/python/tests/engine/test_419t6r1_decoy_sans_steppable_live.py` — 7 gardes.

### Ce qui reste NON couvert

Le second point de §6 — « tuile d'attaque occupée par un `Steppable` NON leurre » — n'est **pas**
fermé par cette tranche : `add_unit_trait` sait poser `Steppable`, mais une unité `Steppable` non
leurre placée sur une tuile voisine exige un montage de placement, pas seulement un trait. La tuile
`C` reste son substitut.
