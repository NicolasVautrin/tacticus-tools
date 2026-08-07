# #506 -- Les cinq rouges LIVE de `master` n'en font qu'UN : la bascule « equiper » de #419-r6

**Pourquoi cette fiche.** Cinq familles de rouges LIVE ont ete signalees par cinq agents
differents pendant la journee du 2026-08-07, chacune prouvee ANTERIEURE a la tranche qui la
rapportait. Aucune n'a ete traitee : elles etaient hors du perimetre de chacun. **Aucun cliquet ne
les voit** -- ce sont des tests LIVE, et la banque qui tourne a chaque PR (`probe_457`) est
OFFLINE. Ils peuvent donc pourrir indefiniment : c'est le mode de defaillance que #455 a documente
sur l'axe du SKIP, transpose a l'axe LIVE/OFFLINE.

**Regime de mesure.** Worktree a `6f9f6071`, **exactement** `origin/master` au moment de la mesure
(`git rev-parse HEAD == git rev-parse origin/master`, verifie). Tout rejeu ci-dessous est donc un
rejeu sur `master` NU, sans aucune edition. Session Frida `5`, drain off, warmup passe. Build du
jeu `rnca9r7q6c` == `data/symbols/CURRENT` (verifie : le build du jeu n'a PAS bouge, ce n'est pas
la cause).

---

## 1. Inventaire -- les cinq, mesures un par un, puis le TEMOIN

Colonne « TEMOIN » = **le meme fichier, rejoue avec `TACTICUS_BIS_ITEMS=0`** (le drapeau qui
restitue le regime d'AVANT `c4be3896`, sans toucher a une ligne de code).

| # | Fichier (`scripts/python/`) | Signalement | Mesure sur `master` nu | TEMOIN `BIS_ITEMS=0` |
|---|---|---|---|---|
| 1 | `tests/engine/test_419r1tr14r5r2r1r1r1_normal_attack_kill_gate_live.py` | 1 failed / 9 passed | **1 failed / 9 passed** | (cf. §2.1) |
| 2 | `tests/engine/test_tile_term_unit_gated_playbooks_live.py` | 13 failed / 12 passed / 5 skipped | **13 failed / 12 passed / 5 skipped** | **30 passed** |
| 3 | `tests/engine/runner/test_steppable_targeting_live.py` | 2 failed / 6 passed | **2 failed / 6 passed** | **8 passed** |
| 4 | `tests/engine/runner/test_cultdemagogue_migration_live.py` | 6 errors `KeyError: 'units'` | **6 errors** | **6 passed** |
| 5 | `tests/engine/runner/test_summon_consumers_live.py` | 1 failed | **1 failed / 28 passed** | **29 passed** |

**Les cinq signalements sont EXACTS au test pres.** Et les quatre premiers temoins mesures
redeviennent **integralement verts** dans le regime d'avant la bascule.

## 2. La cause unique -- `c4be3896`, #419-r6, 2026-08-06 14:01

    #419-r6 : basculer le defaut a << equiper >> -- 17 fichiers repares, perimetre DERIVE,
    causalite etablie par TEMOIN (#742)

Depuis ce commit, `rl_duel build` **equipe** chaque unite de ses items Best-In-Slot avant la
formule de stats. La bascule est **JUSTE et reste** : sans items, `CouldCrit`
(`IdunBattle.Core.Services.DamageCalculations$$CouldCrit` = `GetStat(9) > 0 && GetStat(10) > 0`)
etait FAUX sur **106/106** unites du seed, cote natif COMME port -- tout accord sur le crit etait
un accord en regime DEGENERE. Ce qui change aussi, mecaniquement : `FixedArmor` sur **49/106**
unites, les degats, les PV. Donc **toute trajectoire native, toute geometrie et tout seuil de
degat calibres AVANT le 2026-08-06 ont bouge**.

Le commit lui-meme nomme son residu : **`#419-r6-r1` -- « perimetre restant + face DECISION +
les 7 preexistants »**. Son perimetre derive couvrait trois canaux (coup propre exige **38**,
deja neutralises **34**, valeur en dur **25**) ; **aucun des cinq fichiers ci-dessus n'y figure**.
Les cinq rouges sont donc **exactement le residu annonce**, jamais ouvert.

**Ce que la reparation N'EST PAS.** Repasser les montages sous `TACTICUS_BIS_ITEMS=0` fabriquerait
des verts en regime degenere -- precisement ce que #419-r6 a supprime. Chaque montage se
**re-etalonne sous le regime EQUIPE**.

### 2.1 -- La forme du degat, montage par montage

* **#2 -- trajectoire NATIVE decalee.** Le montage epingle un PAS (`step=34`, `28`, `26`, `19`) sur
  une trajectoire marchee par `aiStepDryRun -> applyAction`, donc 100 % native. Les stats ayant
  change, l'ordre d'activation a glisse : au pas 34 c'est `bloodIntercessor` qui est active, pas
  `blackTerminator` ; au pas 28 et 26, `templChampion` au lieu de `darkaAsmodai` ; au pas 19,
  `bloodMephiston` au lieu de `deathBlightbringer`. Un cinquieme cas (`MC1_67/777` pas 25) part
  desormais en **skip** -- la bataille FINIT au pas 23. Fait notable : le 5e test de chaque cas,
  `test_best_attack_tile_agrees_with_native`, **passe partout** -- le PORT est d'accord avec le
  natif ; seul le montage est perime.
* **#3 -- geometrie du contrefactuel perdue.** Toutes les lignes s'accordent natif/port (`nat ==
  port` sur 18/18) ; ce qui tombe est le contrefactuel « le port d'AVANT acceptait » : desarme du
  bit `AllowSteppableUnit`, le port ne rend plus `0` sur les decoys mais `0x8000000` -- une AUTRE
  regle de refus mord d'abord. Le montage ne fabrique plus la fenetre ou le bit 51 est le SEUL
  refus.
* **#4 -- la bataille se termine avant le cast.** `decisionView` ne publie plus `units` quand la
  bataille est finie (comportement connu et deja gere ailleurs : `_summon_montage.py` lit
  `dv.get("units") or []`). Ici la lecture est nue (`dv["units"]`), donc `KeyError` au lieu d'un
  diagnostic. Deux defauts distincts : la trajectoire (cause) et la lecture nue (ce qui rend le
  symptome illisible).
* **#5 -- la garde conditionnelle est defaite par un effet TIERS.** Le volet live de
  `test_waaagh_buff_effects_posed_live_and_port` est garde par `if d["live_effects"]:`, et sa
  docstring explique pourquoi : dans ce roster le cast epuise les activations, le tour bascule, et
  les 3 buffs `Direct(1)` ont deja expire quand `decisionView` est relu -- `live_effects` etait
  donc VIDE et la garde sautait. Depuis la bascule, le caster porte `BigTarget_AdjacentEffect`
  (effet tiers, qui n'expire pas) : `live_effects` est non vide sans contenir aucun Waaagh, et
  l'assertion mord sur un regime qu'elle n'a jamais voulu juger.
* **#1 -- la premisse d'un BRAS n'est plus vraie.** Le carre apparie oppose un bras `nokill`
  (cible a PV pleins) a un bras `kill` (cible a 1 PV). Equipe, `ultraEliminatorSgt` tue desormais
  la cible A PV PLEINS d'une attaque normale : la contre-epreuve mord dans le bras `nokill`, ou
  elle doit etre inerte. Ce n'est pas le gate qui est faux -- c'est le bras qui ne realise plus sa
  propre premisse.

---

## 3. Ce que cette tranche a repare

(section renseignee au fil des reparations)

---

## 4. Residus

* `#506-r1` -- (a renseigner)
