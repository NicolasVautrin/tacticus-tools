# #895 — les actives du boss `tauBossRiptide` : deux casts portés, un refusé

`1194 NovaShield` et `1192 NovaBoost` sont **PORTÉES ET CONFRONTÉES LIVE**. `1193 NovaCharge`
reste **NON PORTÉE** (résidu `#895-r1`) : son behaviour est lu, mais il est invalidable en l'état.

Porteur : `tauBossRiptide`, **npc** de boss de guilde. Il se monte sans greffe —
`rl_duel build --board GB_Riptide_01 --explicit-stats "tauBossRiptide:4" --p-units "tauBossRiptide:4"`
(la chaîne avec palier est VERBATIM des deux côtés) — et arrive avec ses stats, ses traits
(`Boss, Immune, BigTarget, Flying, IndirectFire, Vehicle`) et ses armes.

## 1. L'audit disait `DAMAGE(Particle)`. Les trois casts ne frappent pas.

La colonne de `combat-ability-coverage.md` dérive du `damageProfile` du **kit**, pas du behaviour.
Les trois `ExecuteBehaviour` sont lus et ne portent **aucun** nœud d'attaque : patron 2-PHASES de
`HeavyRailRifle` (1160). `minDmg`/`maxDmg`/`nrOfHits`/`damageProfile` du gameconfig appartiennent
aux triggered de phase 2 (`#895-r4`). Confronté : HP inchangés des deux côtés, sur les deux casts.

    NovaShieldAbility$$ExecuteBehaviour        (masque STATIC-COPY `<TargetingOptions statics>+0x1c0`
                                                -> `+0x1e8` = 0x6000040, RANGE_WHOLE_BOARD, tile-target)
      turns = TurnsFromRounds(GetNumberConstant(0x45 = nrOfRounds = 1))
      Execute( ( ( CreateShield(Caster@+0x48, Direct(GetVariableForLevel(0x27 = shieldHp)),
                                source = AbilityOrEffect(this), turns, null, stackable = true)
                 & AddStaticStatModifierEffect(Owner@+0x30, 1416, StatType.BLOCK_CHANCE,
                                Direct(0x15 = blockChance), turns, isHidden = false) )
               & AddEffect(1415, absRef, targets = GetMarkedTiles(), turns = NULL) )       # 5-args
               & AddBondEffect(1414, absRef, Owner, Owner, bonded = Owner, options = ZERO) )
      GetMarkedTiles = Filter( Target@+0x60 + AdjacentTiles(Target@+0x60),
                               NOT IsTrenchTile(ActiveTarget@+0x68) )

    NovaBoostAbility$$ExecuteBehaviour         (masque PRESET+FLAGS `statics+0x280` -> `+0x2a8`
                                                = 0x8004, OR 0x10 -> **0x8014**, RANGE_SELF, self-cast)
      Execute( AddBondEffect(1409, absRef, Caster, Caster, bonded = Owner, options = ZERO)
             & AddEffect(1410, absRef, source = Caster, targets = GetMarkedTilesSelector(),
                         options = ZERO) )                                                 # 6-args
      GetMarkedTilesSelector = Filter( AdjacentTiles(Caster@+0x48),
                                       NOT IsTrenchTile(ActiveTarget@+0x68) )

Les deux ctors finissent par `AActiveAbility..ctor(this, &opts, 2)` — `AbilityAttackType.Others`,
transcrit tel quel dans `ABILITY_ATTACK_TYPE`.

**La différence structurelle entre les deux zones marquées** : 1194 unionne l'ORIGINE
(`op_Addition` avec `Target`), 1192 **non** (couronne seule). Un mutant qui retire l'union fait
rougir le probe.

## 2. Le bug que la confrontation a trouvé : le mauvais `AbilityState`

`AbilityConfiguration$$GetVariableForLevel(type, abilityState, fallback)` reçoit le **2ᵉ argument
d'`ExecuteBehaviour`** — l'état de CETTE ability. Le port lisait le canal GLOBAL
`StatsComponent.ctx.active_ability_level` / `ability_variables_multiplier`.

| canal | level | multiplier | `shieldHp` |
|---|---|---|---|
| global `ctx.*` (npc : `unitConfig` = `{"error": "config null"}`) | 0 | 100 | **100** |
| per-ability `ActiveAbility.level/.multiplier` (`readAbilityState`) | 55 | 200 | **13686** |

`13686` = `round(6843 × 200/100)` = le `Shields_InitialAmount` de la cascade native. Facteur 137.
**Indistinguable sur un héros** (les deux canaux coïncident), faux sur tout porteur npc — d'où le
résidu `#895-r5` sur le jumeau `_itg_heal_amounts` (1082), non corrigé faute de mesure.

## 3. `1193 NovaCharge` — lue, non portée, et surtout NON CONFRONTABLE aujourd'hui

`GetLineTiles` trace trois lignes parallèles prolongées par `TilesBehindInLine` ;
`GetAdditionalMarkedTiles` prend `First(…, nrOfTargets = 8)` d'une intersection randomisée.
Cinq primitives manquent (`CenterTiles`, `NextTileInLine`, `NextTileClockwise`, `TilesWithEnemies`,
`DirectionTo`). Le blocage n'est pas le volume, c'est le **verrou de confrontation** : son masque
`0x2000000042` porte `CasterHas7Tiles`, le boss monté par `rl_duel` a **1 pied**, et
`abilityTargets(1193)` rend **0** cible légale — un port ne serait validable par aucun canal.
Détail et découpage : `#895-r1`.

## 4. L'empreinte du caster : le canal `feet` ne discrimine pas, le natif si

`decisionView.units[].feet` rend **1 pour toutes les unités** de `GB_Riptide_01`, boss compris —
donc il ne sépare pas « le boss occupe vraiment une tuile » de « le canal rend 1 pour tout le
monde ». Le témoin qui SÉPARE est natif : `1193` porte `CasterHas7Tiles` et
`TargetingQuery$$GetInvalidCasterReason` refuse `GetFeetCount(caster) != 7`. Mesure : `1194`
(aucune règle d'empreinte) rend **66** cibles, `1193` en rend **0** au même instant, sur le même
caster. Le boss monté par ce chemin est donc **MONO-HEX**, et c'est le jeu qui le dit.
Les trois règles d'empreinte ne sont pas portées (`#895-r2`), pas plus que la délégée dynamique de
1192 (`#895-r3`).

## 5. Ce que le témoin discrimine — et ce qu'il ne discrimine pas

* **Le filtre `NOT IsTrenchTile` n'est observable que sur un board qui a des trenches.**
  `GB_Riptide_01` (la carte du boss, `battles[].BoardId`) en porte **6** ; `MC1_67` — le board
  générique — en porte **ZÉRO**. Sur `MC1_67`, un port sans le filtre serait indistinguable d'un
  port avec. Le probe exige donc que le contre-modèle « sans filtre » DIFFÈRE du natif, et il le
  fait sur les deux bras (`(6,1)` en trop). ⚠ Le voisinage se prend en **natif**
  (`Board.neighbours_native`), pas en géométrie even-q : `TileQuery$$IterateAdjacentTiles` applique
  une porte `|dElev| < 2` et les trenches sont à une autre élévation — la cible `(6,0)` bordait
  deux trenches *en géométrie* et zéro *en natif* (premier jet du probe : un bras qui ne prouvait
  rien).
* **La surcharge d'`AddEffect` ne se lit qu'à l'ARITÉ**, et les deux sens sont mesurés : 1194
  appelle la **5-args** (aucun sélecteur source -> `Effect_SourceId` == la TUILE, 4/4), 1192 la
  **6-args** (`Effect_SourceId` == le caster, 0/3 auto-sources).
* **Non discriminé — `remaining` d'après-cast.** Le cast TERMINE le tour, donc
  `decisionView.effects[].remaining` est déjà décrémenté côté natif et pas côté port (1416 : 1 vs
  2). Ce n'est pas un écart de durée : la CASCADE, prise à la pose, donne 2 des deux côtés. La
  garde compare la cascade.
* **Non discriminé — la SOURCE d'`AddStaticStatModifierEffect` (`#893-r2`).** Ici la cible du
  stat-mod EST le caster (`Owner@+0x30`), donc `source = cible` et `source = caster` rendent la
  même chose. Ce cas ne tranche pas le résidu.
* **Non couvert** : la phase 2 (`#895-r4`), la face DÉCISION (les trois `Nova*Playbook` existent
  côté port et n'ont pas été retouchées), le régime multi-hex (aucun porteur à 7 pieds
  disponible).

## 6. Réparations d'outillage tombées de la tranche

* `rl_duel.py` — `_verify_roster` / `_verify_placements` résolvent le `visualId` de config quand
  l'id exact ne trouve rien. **429 unités sur 683** ont `visualId != id` (toutes `npc`/`summons`) :
  `tauBossRiptide` -> `GuildBoss11Boss1TauRiptide`. Tout porteur npc rendait donc
  `demande x1 mais MONTE x0`, un refus **DUR** (`rc 3`) pour une unité qui EST en bataille — et
  c'est le seul canal par lequel un lot d'abilities de boss arrivait « non montable ». Repli
  CONDITIONNEL (`X or Y`) : aucune détection existante ne disparaît. `TACTICUS_ALLOW_ROSTER_DEFICIT`
  n'est plus nécessaire pour monter un boss.
* `.gitattributes` — `docs/rl/index-foyers.md` passe en `text eol=lf`. C'est le SECOND document
  généré sous cliquet d'identité byte-à-byte (`test_603` étage 5) ; sans la ligne, il rougit dans
  **tout worktree frais** sous `core.autocrlf=true` alors que `git diff` du fichier est **vide**.

## 7. Contre-épreuve

`probe_895_nova_boss_riptide.py` (mesure) / `tests/engine/runner/test_895_nova_boss_riptide_live.py`
(12 gardes). **6 mutants sur 6 mordent**, témoin restauré `rc 0` : filtre trench retiré (1194 et
1192), surcharge d'`AddEffect` inversée (dans les deux sens), scaling per-ability -> global,
origine retirée de la zone marquée.
⚠ Le mutant « scaling » ne mordait pas au premier jet : le motif de substitution frappait la
**première** occurrence du fichier (`_ability_level_amount`, l'helper de 1082), pas
`_nova_ability_scaling`. La mutation n'avait pas mordu là où on la croyait — et l'étage [4] du
probe, lui, ne lisait que la cascade NATIVE, donc deux mutants de source passaient verts.

## 8. `#895-r5` — RÉSOLU (2026-08-18) : la même faute sur `1082`, et le remède existait déjà

**Prémisse re-mesurée, confirmée verbatim.**
`IdunBattleLogic.Entities.Abilities.Active.Loki.InspiredToGreatnessAbility$$ExecuteBehaviour(this,
abilityState, entities)` recopie `*(abilityState)` et `*(abilityState + 8)` dans un local, puis
passe **ce local** aux deux `AbilityConfiguration$$GetVariableForLevel` (`0x20 = hpToHeal`,
`0x22 = hpToHeal_2`) — la séquence de recopie est même **répétée** avant chaque lecture. C'est
exactement la forme de `NovaShieldAbility$$ExecuteBehaviour` (§2).

**Ce que la tranche apprend, et qui dépasse `1082`** : le remède était là depuis #895, sous un nom
qui le déclarait faussement spécifique. `_nova_ability_scaling` prenait son `ability_type` **en
paramètre** dès l'origine — il était générique *par construction*, spécifique *par son nom seul*.
C'est ce nom qui a fait ré-écrire la lecture globale dans `_itg_heal_amounts` au lieu de l'appeler.
Renommé **`_ability_scaling`** (un seul appelant, même fichier ; rayon de souffle mesuré : aucun
lecteur exécutable hors `tau.py`).

**Régime.** Les deux canaux **coïncident sur un héros**. Le global ne décroche que sur un porteur
dont `combatSnapshot.unitConfig` vaut `{"error": "config null"}` — un npc. `1082` n'ayant
aujourd'hui que des porteurs `lineup`, l'écart était **latent** ; il devient réel dès qu'un npc
porte l'ability (greffe, injection catalogue).

**Garde** : `tests/engine/runner/test_895r5_itg_scaling_per_ability_offline.py` (4 étages,
7 tests), vu **rouge par mutation** (2 failed / 5 passed en remettant la lecture globale) —
`hpToHeal` rend **15** au canal global contre **1786** au per-ability, facteur ~119. L'étage 0
assertionne que le montage **sépare** les deux canaux (sans quoi tout le reste serait un accord à
vide) ; l'étage 3 garde que l'état d'une **autre** ability n'est pas lu — ce que ni #895 ni aucun
autre étage ne vérifiait ; l'étage 0bis garde que le foyer reste **partagé** avec `NovaShield`.
