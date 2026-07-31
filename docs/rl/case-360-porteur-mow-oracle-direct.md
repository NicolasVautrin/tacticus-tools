# case-360 — une MoW pour CASTER : le verrou était le harnais, et la greffe cachait un bug

`#350-r3` avait confronté `1147 HadesAutocannons` et `1148 DaemonicOrdnance` sur une unité
**GREFFÉE**, faute d'oracle acceptant leur porteur réel (`blackForgefiend`, MoW). Deux verrous y
étaient nommés : **(a)** `aiPlaybookPredict` rend `count = -1 / listNull = true`, **(b)**
`engine.ai.context.build` rend `ctx.me is None`. Les deux ont été mesurés. **Aucun des deux n'était
une propriété du jeu.**

## Ce que le décompilé dit de la position d'un caster Machine

`IdunBattle.AI.Tactics.DefaultMachineTactic.u003CCalculateNextActionForUnitu003Ed__5$$MoveNext`
appelle, pour chaque générateur :

    gen.GenerateActions(machine, UnitPosition$$NullPosition(), new OrderedSet<…>(), 0)

et `IdunBattle.Core.UnitPosition$$NullPosition` **n'est pas un struct nul** : son corps est
`new List<ITile>()` — une position dont la liste de tuiles est **VIDE mais non nulle**.
`IdunBattle.Core.UnitPosition$$get_MainTile` la traite sans lever (il teste `Count` avant d'indexer
et rend `null` sur zéro) : c'est un argument **légal** partout où le natif la passe lui-même.

Le harnais, lui, substituait la `UnitPosition` de la **CIBLE**. Aucun antécédent natif. La casse est
lisible dans `IdunBattle.AI.Playbook.Playbooku003C__Il2CppFullySharedGenericTypeu003E$$GetEntitiesFromSelector`,
qui pose `ctx.<+0xc0> = UnitPosition$$get_MainTile(casterPosition)` : donner la tuile de la cible
fait évaluer le sélecteur depuis un point de vue qui n'existe pas.

## (a) — MESURE DISCRIMINANTE

Même montage (MoW déployée par `--a-mow`, deux `deathPoxwalker` posés par `1040 SpawnPoxwalkers`),
même `MakeDamagePredictions`, **deux positions** :

| RPC | position passée | résultat |
|---|---|---|
| `aiPlaybookPredict` | celle de la **CIBLE** | `count = -1`, `listNull = true` (le natif LÈVE ; `makeDamagePredictions` avale) |
| `ncPlaybookPredict` (`via = makeDamagePredictions`) | celle du **CASTER** (= `NullPosition`) | **1 event, `(324, 492, 6)`** |
| `pairUtility` | celle du **CASTER** | `utility = 13.627` |

Correctif : `nullUnitPosition()` (`frida/hooks/features/ai-step/playbook-predict.ts`), et les
**trois** oracles partent désormais de la même position pour un caster Machine. ⚠ **Code hooks —
inactif tant qu'une fenêtre de reinject n'a pas eu lieu.** Bundle vérifié (`frida-compile` OK,
1 047 273 o) ; `tsc -p tsconfig.hooks.json` sans erreur sur les trois fichiers touchés.

## (b) — N'ÉTAIT PAS UN VERROU

`engine.ai.context.build_machine` existe (mirror de `DefaultMachineTactic` : `origin = None`,
`action_tiles = []`, `plans = {}`, `me` lu dans `decisionView.mows`) et `engine_validate.py` route
déjà dessus via `machine_row`. `build` rend `me = None` sur une Machine **parce que c'est la
fonction des UNITÉS** : `decisionView.units` ne contient jamais de Machine. Le probe `#350-r3`
appelait simplement la mauvaise. Mesuré : `build_machine` → `ctx.me = blackForgefiend`,
`abilities = [1147]`, `scene.ctx(<MoW>)` non nul, `origin = None`.

## La confrontation, et ce qu'elle a révélé

### `1147` — la greffe est VALIDÉE, terme à terme

| bras | niveau | (minDmg, maxDmg) | natif **MoW réelle** | natif **greffe** (`#350-r3`) |
|---|---|---|---|---|
| A (`3 mod 4`) | 4 | (58, 77) | **(324, 492, 6)** | (324, 492, 6) |
| B (`1 mod 4`) | 2 | (43, 58) | **(240, 360, 6)** | (240, 360, 6) |

`to_even` seule nulle sur les deux bras, code livré = natif sur les deux. **Même verdict, mêmes
chiffres** : la greffe était une mesure équivalente, et on le sait maintenant par mesure.

### `1148` — un BUG que seule la greffe cachait

Le gate de sélecteur porté par `#350-r3` (`_daemonic_ordnance_target_gate`) commence par
`if scene.team(caster_id) is None: return False`. Or `engine.playbook.scene.step_context` ne versait
que `decisionView.units` dans ses tables par-id — donc `scene.team(<MoW>)` valait **`None`**, et le
gate se dégradait en **NÉGATIF pour tout caster MoW** :

| régime | natif | port AVANT | port APRÈS |
|---|---|---|---|
| zone froide | ∅ | ∅ (**par accident** : `team = None`) | ∅ (`gate = False`, tuile non en feu) |
| zone en feu (après un cast **de la MoW**) | (3, 3, 3) | **∅** | **(3, 3, 3)** |

Sous-prédiction **muette**, symétrique de la sur-prédiction que `#350-r3` avait fermée sur le même
sélecteur — et invisible tant que l'ability était mesurée par greffe sur une unité, qui a une équipe.
L'accord du régime froid était donc obtenu par une **donnée manquante**, pas par le port.

Correctif : `step_context` verse aussi `dv.mows` dans `hp_by_id` / `pos_by_id` / `team_by_id` (clé
`casterId` = `machineId`, la même que `context.machine_row`). Purement **additif** — les ids de
Machine sont disjoints de ceux de `.units`, et `units` reste `dv.units`, donc les consommateurs qui
COMPTENT des unités (`_enemy_psykers_alive`) ne voient rien changer.

## Gardes

| garde | ce qu'elle verrouille |
|---|---|
| `test_360_mow_caster_oracle_live.py` (4) | la position du caster ouvre l'oracle MoW ; `build_machine` rend le contexte ; `1147` MoW == `1147` greffe ; `1148` en accord dans les **deux** régimes **et** `scene.team(<MoW>)` non nul |
| `test_350r3_mow_carrier_live.py` — 2 | reformulé : ce test verrouillait le symptôme (`listNull`, `ctx.me is None`) comme s'il était le jeu |
| `probe_360_mow_caster_oracle.py` | `--step a` (discriminant), `--step b` (1147, 2 bras), `--step c` (1148, 2 régimes de feu) |

**Mutations jouées, rouges** : (1) faire repasser `_native_mow` par `aiPlaybookPredict` → « bras a
KO : aiPlaybookPredict n'a rendu AUCUN event » ; (2) router `ctx_machine` vers `build` → «
`build_machine` ne construit plus le contexte de la MoW : None » ; (3) retirer la boucle `mows` de
`step_context` → « `scene.team(<MoW>)` est de nouveau None ».

Le test #360 est **tri-état sur le bundle** : `aiPlaybookPredict` publie `posSrc`, et `machine:*`
signe le bundle corrigé. Avant la fenêtre, la garde vérifie que le symptôme est bien celui qu'on
corrige ; après, elle exige l'ACCORD des deux oracles. Aucun `skip`.

## Ce qui n'est PAS couvert

- **La branche « bundle corrigé » n'est pas encore exécutée** : la session porte le bundle
  antérieur, donc `test_the_caster_position_is_what_opens_the_mow_oracle` passe aujourd'hui par sa
  branche `else`. Mesure à rejouer APRÈS la fenêtre de reinject :
  `python probe_360_mow_caster_oracle.py --step a` — attendu `posSrc = machine:NullPosition` et
  `aiPlaybookPredict` égal à `ncPlaybookPredict`.
- **Le volet AoE de `1147`** : sur le bras B le natif émet **2** events (un par summon retenu), le
  port **1**. Inchangé par ce cas — axe distinct, déjà nommé par `#350-r3`.
- **Les autres MoW** : la mesure porte sur `blackForgefiend` (2 des 8 MoW du pool, ses deux
  abilities). Les `mythicAbilities` des sept autres ne sont pas confrontées.
- **`scene.hp(<MoW>)` / `scene.pos(<MoW>)`** sont désormais renseignés mais aucun consommateur
  mesuré ne les lit encore : ils sont versés pour la même raison que `team` (la ligne les porte),
  pas sur une divergence observée.
