# Case #118 — Stat-mods des effets SEEDES : reversibles ou cuits ?

**Question binaire posee.** Quand un `State` offline est charge depuis une capture
(`decisionView` + `combatSnapshot`), certains effets sont **deja poses** sur les unites — leur
contribution de stat est **deja cuite** dans les stats captees. Le natif applique-t-il cette
contribution comme une `ValueModification` **par-source ordinaire**, donc **retirable** quand
l'effet expire, ou passe-t-elle par un autre chemin, non reversible ?

**Reponse : PAR-SOURCE, ET REVERSIBLE.** Le port DIVERGEAIT structurellement. Corrige.

---

## 1. RE — le natif (build `gqfc5mff6c`, decompile ghidra)

### 1.1 La source d'un ChangeStat d'effet EST l'entite-effet

`IdunBattle.Entities.Effects.AStatModifierEffect$$ApplyInternal` appelle
`IdunBattle.Entities.Effects.AStatModifierEffect$$ApplyModification`, qui construit :

```
stat, hidden = (**this.vtable+0x728)(this, ...)          # GetStatModification()
part          = 9 si this+0x482 != 0 sinon 5             # MULTIPLIER_MODIFICATION / MODIFICATION
ChangeStat( dslFactory,
            Entity(param_3),                  # la CIBLE du stat-mod
            Position(stat, part),
            4,
            Direct(amount),
            Entity(param_4),                  # <-- la SOURCE = L'ENTITE-EFFET
            0, 0, hidden, 0 )
```

`param_4` est bien l'entite-effet : c'est sur elle qu'`ApplyModification` fait
`GetComponent<StatModificationComponent>(param_4)` puis ecrit le montant resolu en `+0x14` — le
champ que relit `IdunBattle.Entities.Effects.StaticStatModifierEffect$$GetStatModificationAmount`
(`+0x14`), a cote du StatType lu par
`IdunBattle.Entities.Effects.AStatModifierEffect$$GetStatModificationStat` (`+0x10`).

### 1.2 Le retrait rejoue le MEME appel en `part 6`

`IdunBattle.Entities.Effects.AStatModifierEffect$$RevertModification` :

```
stat, hidden = (**this.vtable+0x728)(this, ...)          # LE MEME GetStatModification()
ChangeStat( dslFactory, Entity(param_3), Position(stat, 6), 4,
            dslFactory+0xb8,                  # noeud de montant vide (part 6 n'en a pas besoin)
            Entity(param_4), 0, 0, hidden, 0 )
```

`part 6` = `StatPart.RESET_MODIFICATION` ->
`IdunBattle.Entities.Components.ValueModification$$ReverseModification` : la contribution de CETTE
entite-effet est retiree du `total`, les autres sources restent.

### 1.3 Qui declenche le revert

`IdunBattle.Operations.EndTurnOperation$$RefreshEffects` decremente la duree
(`IdunBattle.Entities.Components.EffectComponent$$RemoveOneTurn` = `+0x64 -= 1`, plancher 0), puis
`IdunBattle.Operations.RemoveEffectOperation$$Execute` ->
`IdunBattle.Operations.RefreshEffectsOperation$$DeactivateEffect` ->
`IdunBattle.Operations.RefreshEffectsOperation$$RevertEffectsForTargets`, qui appelle **par cible**
le virtuel d'interface slot `0xf` de l'effet — pour la famille `AStatModifierEffect`, c'est
`RevertModification`.

**Conclusion RE** : il n'existe AUCUNE voie native ou un effet a stat-mod disparait en laissant sa
contribution. La source etant l'entite-effet, elle part avec elle. Corollaire lu, pas suppose :
`ApplyModification` et `RevertModification` derivent leur `Position(stat, …)` du **meme**
`GetStatModification()` — un `AStatModifierEffect` reverte donc toujours *le* stat qu'il modifie.

### 1.4 Ce que la BattleConfiguration porte (et ne porte pas)

Verification faite sur `data/seed-bc.json` : la BC **ne pre-pose aucun effet sur une unite**
(`BC.Units[*]` n'a pas de champ d'effets ; `UnitModifiers` est le canal Guild Boss, vide ici ;
`Board.SpawnPointSets[*].TileEffectSpawnPoints` est vide). Le mot « seede » du port ne designe donc
PAS un pre-etat de BC : il designe **l'etat capte a l'instant T** que `load_state` materialise. Le
cas est donc generique — il vaut pour **tout stat-mod materialise par un behaviour puis capte**.

---

## 2. Le port — ou etait la divergence

Deux voies materialisent un effet offline, et une seule savait reverter :

| voie | cle de la `ValueModification` | revert a l'expiration |
|---|---|---|
| POSE en combat (`AddStaticStatModifierEffect`, `AddEffectOperation._apply_stat_mods`) | posee sur l'instance (`eff.stat_mod_source`) | OUI (`revert_stat_mods_of_removed_effects`) |
| SEED (`EffectsState.seed` + `UnitContext.from_snapshot`) | `statmod_source_key(eff)`, calculee par `stat_modifications_by_source` puis **oubliee** | **NON** |

L'attribution du seed existait deja et etait correcte (`seed_unit_stats(attributed=…)` ecrit bien
la contribution sous `statmod_source_key`). Ce qui manquait, c'est que **les deux consommateurs du
retrait** (`revert_stat_mods_of_removed_effects` au tick, feuille `RemoveEffect` au retrait
explicite) exigeaient un `eff.stat_mod_source`, absent sur une instance seedee — ils ne faisaient
donc **strictement rien**. Un stat-mod a timer deja actif au chargement restait applique **a vie**.

Second etage du probleme : l'effet `ThrillSeekers` (1434) n'avait **aucune classe** cote port, donc
`get_stat_modification_stat/amount` rendaient `None` et sa contribution n'etait meme pas attribuee —
elle tombait dans le residu opaque `CAPTURED_SOURCE`, hors d'atteinte de toute source. Le capteur ne
peut pas combler ce trou : `frida/hooks/game/effects.ts` n'expose ni le StatType ni le montant d'un
effet (EffectType / remaining / level / source seulement).

---

## 3. Le correctif

1. **Une seule cle par instance d'effet** — `entities/effects/__init__.py::effect_stat_mod_key(eff)` :
   `eff.stat_mod_source` si un chemin de pose l'a renseignee, sinon la cle DERIVEE
   `statmod_source_key(eff)` (celle du seed), sinon `None` (l'effet ne modifie aucun stat). C'est le
   mirror direct du natif : une entite-effet = une entree `per_source`.
2. **Les trois consommateurs lisent cette cle** :
   `runner/operations/effects.py::revert_stat_mods_of_removed_effects` (expiration par timer),
   feuille `RemoveEffect` (retrait explicite), et
   `runner/operations/refresh_effects.py::refresh_stat_modifier_effects` (driver d'ActiveCondition).
   `runner/abilities/behaviours/context.py::_stat_modifier_amount`
   (`CurrentStatModifierAmountFormula`) s'aligne aussi.
3. **`BaseEffect.reverted_stats()` par defaut = `[get_stat_modification_stat()]`** — mirror du fait
   que `ApplyModification` et `RevertModification` partagent le meme `GetStatModification()` (§1.2).
   Les effets multi-stats (ActOfFaith) et les stat-mods EAGER gardent leur override explicite.
4. **`ThrillSeekersEffect`** (`entities/effects/loki/status.py`, registre `"ThrillSeekers"`) declare
   `(CRIT_CHANCE=9, extraCritChance)` — les deux valeurs que le natif bake dans le
   `StatModificationComponent` de l'entite-effet, re-derivees de la MEME source de config
   (`traits.ThrillSeekers.variables.thrillSeekersExtraCritChance`, la constante d'ability `0x30` que
   lit `ThrillSeekersAbility$$CreateBehaviour`).

### Pourquoi le point 2 sur `refresh_stat_modifier_effects` est LOAD-BEARING

Le driver keyait en dur avec `statmod_source_key`. Des lors qu'un effet pose en combat porte AUSSI
une classe declarant `get_stat_modification_stat` (ce que le point 4 introduit), il aurait cree une
**SECONDE** entree `per_source` pour la meme entite-effet. Mesure adversariale (fix 2 retire,
`test_thrill_seekers_damage_taken_then_refresh`) : **moteur cc = 30 vs live 15**. Le natif n'a
qu'une entree par entite-effet ; le port doit avoir la meme.

---

## 4. Validation

### 4.1 Divergence prouvee live (avant / apres), 2 couples porteur x board

`test_thrill_seekers_live.py::test_thrill_seekers_seeded_stat_mod_reverts_on_expiry`
(`[adamatar-8118-MC1_67]` melee et `[shiron-4242-C4_09]` ranged) : capture prise **APRES** la pose
(`Thrilled` actif, `rem=2`), `load_state`, N x `EndTurnOperation` jusqu'a expiration.

| | crit chance a la capture | crit chance apres expiration |
|---|---|---|
| LIVE (oracle) | 15 | **0** |
| MOTEUR avant fix | 15 | **15** (erreur relative 100 %) |
| MOTEUR apres fix | 15 | **0** |

Les deux parametrisations ECHOUENT sur `origin/master` (886335f) et PASSENT avec le fix.

### 4.2 Probe offline rejouable

`scripts/python/probe_118_seeded_statmod_revert.py` (aucune session Frida) — mesure sur un `State`
minimal :

```
avant : classe BaseEffect          per_source(cc) = {'captured': 15}                 cc 55 -> 55
apres : classe ThrillSeekersEffect per_source(cc) = {('statmod',1434,7,'…'): 15}     cc 55 -> 40
```

### 4.3 Non-regression (perimetre nomme : ActOfFaith / DoctrinaImperatives / AnvilShield)

Tous verts avec le fix :

| fichier | resultat |
|---|---|
| `test_thrill_seekers_live` (5 tests, dont les 2 nouveaux) | PASS |
| `test_anvil_shield_stun_live`, `test_getstat_live` | 4 PASS |
| `test_act_of_faith_live`, `_second_stack_`, `_reset_`, `_ability_reset_`, `_normal_crit_resets_` | 9 PASS |
| `test_doctrina_imperatives_live`, `test_doctrina_gate_cap_live` | 6 PASS |
| `test_effect_duration_rounds_live`, `test_turnflow_live`, `test_effect_stun_live` | 8 PASS |
| `test_rad_saturation_live`, `test_mv71_sniper_drone_live`, `test_runner_state_live` | 13 PASS |
| `test_damage_roll_live`, `test_runner_attack_live` | 4 PASS |
| offline : `test_act_of_faith_crit_resets_both_paths`, `test_turnflow_endturn_flags`, `test_triggered_ability_component`, `test_attack_nature_gates_offline`, `test_config_oracle_offline` | 31 PASS |

Effets DECLARATIFS touches par le changement de cle/`reverted_stats` et leur comportement apres fix :
`AnvilShield_BlockChanceBelowHealthCap` (1200, permanent, condition-driven — inchange),
`AnvilShield_AdditionalBlock` (1202, permanent — inchange),
`AnvilShield_FrozenAttackerAdvantage` (1201 — un stack SEEDE consomme par son trigger reverte
desormais son +20 BlockChance, ce qui EST le comportement live #100),
`Contaminated_Unit` (1245 — magnitude `value` absente au seed, donc no-op),
`StandVigil_ExtraArmor`, `Swarm_HitReduction` (permanent, cle partagee inchangee).

---

## 5. Ce qui n'est PAS couvert (residu nomme, hors perimetre)

**Les stat-mods EAGER seedes** (`applied_stat_mods`) restent non attribues et donc non revertables :
`ActOfFaith_Effect` (1017), `ProtectorImperative`/`ConquerorImperative` (1247/1248),
`AnvilShield_FrozenAttackerAdvantage` par sa face eager. Leur magnitude se calcule depuis le
`StatsComponent.ctx` du porteur (`applied_stat_mods(stats_ctx)`), or l'attribution du seed est
calculee **avant** que le `UnitStats` n'existe (`UnitContext.from_snapshot` : `attributed` precede
`seed_unit_stats`), et ActOfFaith lit justement `StatPart.INITIAL` du crit-damage — dependance
circulaire a demeler. Deja documente cote code (`ActOfFaithBuffEffect` : « un stack SEEDE ne connait
pas ses deltas »). Chantier separe, non ouvert ici.

Autres non-couverts, explicitement :
- la **magnitude** d'un effet seede reste RE-DERIVEE de la config offline, jamais lue de l'entite-effet
  (le capteur n'expose pas `StatModificationComponent+0x10/+0x14`). Point d'ancrage natif a hooker si
  on veut la lire : `IdunBattle.Entities.Effects.AStatModifierEffect$$GetStatModificationStat` /
  `IdunBattle.Entities.Effects.StaticStatModifierEffect$$GetStatModificationAmount` (ou, plus
  simplement, le `StatModificationComponent` de l'entite-effet dans `frida/hooks/game/effects.ts`) —
  **exige un rebuild + reinject**, non fait ici ;
- la branche **MULTIPLICATIVE** de `ValueModification` (`part 9`, `MultiplyModifier`) reste non
  portee (residu pre-existant, cf. `entities/stats.py`) ;
- aucun autre effet du roster n'a ete dote d'une classe : les effets seedes qui ne declarent toujours
  pas de stat-modification gardent leur contribution dans le residu opaque `CAPTURED_SOURCE` (present
  mais non attribue) — degradation fidele, mais non reversible.
