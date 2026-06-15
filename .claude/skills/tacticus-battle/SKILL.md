---
name: tacticus-battle
description: Mener une bataille Tacticus de bout en bout. Claude (oracle) pilote SON équipe via la vue décision + applyAction ; l'adversaire est un driver au choix — IA native du jeu, humain qui dicte, ou Claude en self-play — sans présupposer son niveau. Boucle view -> act (1 action à la fois, ré-éval entre chaque) -> endturn -> tour adverse, jusqu'au winner. Use when conducting/playing a Tacticus battle as the oracle.
user-invocable: true
allowed-tools: Read, Bash, Glob, Grep, Edit, Write
---

# Tacticus — Mener une bataille (oracle)

Conduire une bataille **de bout en bout** sur un runner isolé persistant. Claude
est la **policy de l'équipe 1** (joueur humain). L'**équipe 2 a un driver** au
choix, **sans présupposer son niveau** :

| Driver | Qui joue l'équipe 2 | Commande du tour adverse |
|--------|---------------------|--------------------------|
| `ia` | IA native du jeu (gloutonne) | `aiturn` |
| `humain` | l'utilisateur dicte les actions | Claude les relaie via `act ...` |
| `claude` | Claude en self-play (au mieux) | Claude décide + `act ...` |

**Au début d'une battle, demander quel driver adverse** si l'utilisateur ne l'a
pas dit. Mécaniquement c'est le même harnais : après mon `endturn`, le
`currentPlayer` bascule sur l'équipe 2, donc `view` la montre comme « MOI »
(`ctrl` suit le joueur courant) — je joue ses unités exactement comme les
miennes (`act`), ou je laisse l'IA jouer (`aiturn`).

> **Ne JAMAIS tuner ma propre policy sur la faiblesse supposée de l'adversaire.**
> Jouer robuste : viser la victoire contre un jeu **optimal**, exploiter les
> fautes adverses **seulement quand le stream les montre** (overwatch encaissé,
> suicide dans une aura…), jamais les supposer à l'avance.

---

## 1. Pré-vol (obligatoire, dans l'ordre)

1. **Host up** : `curl -s http://127.0.0.1:8765/api/health` → `{"status":"ok"}`.
   Sinon `cd frida && npm run dev` (background).
2. **Rebuild/reinject si besoin** :
   - `frida/hooks/*` modifié → `cd frida && npm run build:hooks` puis réinject
     `POST /api/admin/inject` (body `{}`) — **pas** de restart host.
   - `frida/host/*` modifié → restart host complet (réinjecte via auto-restore).
3. **WARMUP — INCONDITIONNEL après CHAQUE (re)inject, AVANT tout RPC/probe,
   SANS EXCEPTION** (même un build seed-BC sur disque) :
   ```bash
   # session running courante : GET /api/sessions -> [{ id, status, ... }]
   SID=$(curl -s http://127.0.0.1:8765/api/sessions \
     | npx -y node-jq -r 'map(select(.status=="running")) | .[0].id')
   curl -s -X POST http://127.0.0.1:8765/api/scripts/$SID/rpc \
     -H 'content-type: application/json' \
     -d '{"method":"warmupGameSingletons","args":[{"force":true}],"timeout":120000}'
   ```
   (Ou plus simple : `rl_duel.py`/`rl_probe_step.py` résolvent la session seuls
   via `_resolve_session()` — mais ils ne warmup PAS, à faire avant.)
   `warmupGameSingletons` est **AUTONOME** : il pilote toute la nav UI lui-même
   (campagne → node → play → capture ctor → pause → retreat). **Ne JAMAIS
   demander à l'utilisateur de cliquer une battle in-game.** Sans warmup, un
   reinject repart avec caches `MethodInfo*` vides + init IL2CPP non amorcée →
   `applyAction`/`buildPatchedRunner` crashent (`0x2c`). Mémoire :
   `feedback_warmup_after_every_reinject`, `feedback_auto_reinject_on_hooks_change`.

---

## 2. Monter la battle

```bash
# rosters ALÉATOIRES (déterministe par --seed)
PYTHONIOENCODING=utf-8 python scripts/python/rl_duel.py build \
  --seed 777 --rank 17 --roster 5 [--advance K] [--maxpump 2000]

# rosters CHOISIS (+ MoW optionnels)
PYTHONIOENCODING=utf-8 python scripts/python/rl_duel.py build --rank 17 \
  --p-units custoTrajann,custoVexilusPraetor,adeptMorvenn,bloodMephiston,astraYarrick \
  --a-units worldKharn,deathBlightbringer,blackAbaddon,worldJakhal,deathPutrifier \
  --p-mow ultraDreadnought --a-mow blackForgefiend

PYTHONIOENCODING=utf-8 python scripts/python/rl_duel.py build --rank 17 --list-pool  # ids dispo
```

- **Choisir les équipes** : `--p-units`/`--a-units` (ids virgule), `--p-mow`/`--a-mow`
  (1 id), `--mow` (auto-pick 1 MoW/équipe), `--list-pool` (pool spawnable). Sans
  `--p-units`/`--a-units` → tirage **aléatoire** seedé (`--roster N`).
- Pool @ rank 17 ≈ **97 units régulières + 8 MoW** (seed BC `arena-…json` = quasi
  roster complet, toutes factions). MoW : adeptExorcist, astraOrdnanceBattery,
  blackForgefiend, deathCrawler, orksRukkatrukk, tauBroadside, tyranBiovore,
  ultraDreadnought. La board arena a les slots MoW des 2 côtés (déploie sans drop) ;
  sur une autre board, `build` **warn** si pas de slot MoW.
- Runner **persistant** (registry par `runnerId`), état dans
  (file:///C:/Users/nicolasv/tacticus-tools/data/duel_state.json).
- `--advance K` : laisse l'IA jouer K tours d'amorce (IA vs IA) avant ma main.
- Toujours `python` (psycopg3), **jamais `py`**. Mémoire : `feedback_rl_batch_python_psycopg3`.

---

## 2bis. RECON des units — LA PREMIÈRE CHOSE, AVANT le tour 1 (obligatoire)

> **Avant de jouer le moindre coup, scouter le KIT COMPLET de CHAQUE unité des
> deux équipes.** Sauter cette étape = se faire surprendre (ex. le snowball de
> Kharn ci-dessous). C'est non négociable.

```bash
# pour CHAQUE unitId des deux rosters (affichés par build) :
PYTHONIOENCODING=utf-8 python scripts/python/gameconfig.py worldKharn custoTrajann ...
```

`gameconfig.py <id>` croise **3 sources** (indispensable — aucune seule ne suffit) :
- **gameconfig** = les CHIFFRES (move, portée d'arme, nrOfHits, range des actifs,
  damageProfiles, variables de traits).
- **`data/i2_en.json`** = le TEXTE DE RÈGLES (`ability_description`/`trait_description`)
  — c'est là que vivent les **conditionnels** qu'aucun chiffre ne révèle : snowball,
  triggers, auto-attaques, ripostes. `card_unit` les affiche en `« … »`.
- **stream** (en jeu) = pour OBSERVER les triggers se déclencher (cf. §5).

**Décoder le PROFIL DE MENACE de chaque ennemi (et les synergies des miennes)** :
- **Actifs multi-hit / burst** : ex. Kharn `KillMaimBurn` = 8 coups (1 Pierce + 6
  Eviscerate + 1 Plasma) **range 2** → ~10k. Sur **cooldown** (suivre dans la cascade).
- **Range des actifs ≠ portée d'arme** : un actif range 2 + `RapidAssault` (+move) =
  menace bien plus loin que la portée d'arme. Mes tiles « safe » ne le sont pas.
- **Passifs / traits qui SNOWBALLENT ou se DÉCLENCHENT** (le piège n°1) :
  - `TheBetrayer` (Kharn) : si un kill ce combat → **auto move+attaque au DÉBUT de
    chaque tour** (en plus du manuel) → **ne jamais le laisser tuer quoi que ce soit**
    (même un summon).
  - `BlessingsOfKhorne` : +dmg cumulatif par kill mêlée → snowball.
  - `FinalJustice` : **attaque en mourant** (sauf si **overkill**) → overkill les units
    qui l'ont, ou anticiper la riposte.
  - `RapidAssault` : +move avant d'attaquer, +dmg sur attaques multiples.
  - **counter/thorns** (riposte mêlée), **aura** (`ContagionsOfNurgle` = dégâts en
    ENTRANT dans la portée), **overwatch** (dégât en bougeant dans la zone).
- En sortir une **liste de menaces** (qui burst, qui snowball, qui contre, portées
  réelles) et **planifier le tour 1 autour** : ne pas entrer dans la zone d'un burster ;
  refuser tout kill aux snowballers ; overkill les `FinalJustice` ; respecter aura/counter.

---

## 3. La boucle de tour (1 round = mon tour + tour adverse)

### MON TOUR (oracle, équipe 1)

1. `view` (ou la carte déjà affichée).
2. **Lire la carte** (§4).
3. Décider l'ordre d'activation + les actions.
4. **Une action à la fois, ré-éval entre chaque** (`act` ré-affiche les plans
   après l'action — base de la décision suivante) :
   - **Jouer une unité « en 2 temps »** : `act move --unit U --to C,R`, observer
     le résultat, **puis** `act ability --caster U --target T` (l'`abilityId`
     est auto-résolu depuis le plan, sinon `--ability A`).
   - Souvent : `act ability` **direct depuis la tile courante** (zéro move, zéro
     exposition) si la cible est déjà à portée.
   - **MoW** (ability-only, ne bougent pas) : `act ability --caster <machineId>
     --target T --ability <id>`. Les abilities + le casterId sont dans la section
     « MoW » de la carte (§4). **`--ability` OBLIGATOIRE** (pas de plan auto-résolu
     pour les MoW). Les MoW **chargent** : `hasAction=False` à l'ouverture, prêts
     après ~1 tour (apparaissent alors dans `À ACTIVER`). Certaines abilities sont
     de l'**artillerie AoE retardée** (ex. MacroPlasmaIncinerator pose des effets
     sur tiles, dégâts différés) → **juger par la cascade**, pas par `mutated`
     (qui peut être `False` car les effets de tile ne changent pas la signature).
   - `act finish --unit U` si une unité n'a rien d'utile à faire.
5. `act endturn` → la main passe à l'équipe 2.

> **Interdit de batcher un tour entier sur une vue périmée.** Le board change
> après chaque action — re-lire les plans entre chaque, surtout pour le
> **focus-fire** (s'arrêter dès qu'une cible meurt, rediriger le surplus).

### TOUR ADVERSE (équipe 2) — selon le driver

- **`ia`** : `aiturn` (= `aiPlayByUnit maxTurns:1 captureEvents:true`). Décode
  **toute la cascade** du tour (champ `cascade`) en bilan uniforme : `SUBI`
  (dégâts encaissés) / `MA RÉACTION` (overwatch/contre/aura — chacun labellisé
  via `effect`) / kills. **L'overwatch n'est PAS un cas spécial** — c'est un
  `UnitDamaged` taggé `[overwatch]` (Effect_Type=1009), comme `[dot]`.
- **`claude` (self-play)** : `view` montre l'équipe 2 comme « MOI » → décider
  + `act ...` au mieux pour l'équipe 2 → `act endturn`.
- **`humain`** : l'utilisateur dicte les actions ; Claude les relaie via `act ...`
  → `act endturn`. (Même chemin `applyAction` ; `currentPlayer` doit être
  l'équipe 2.)

> ⚠️ **Première validation à faire** pour `claude`/`humain` : piloter l'équipe 2
> via `act` emprunte le **même chemin `applyAction`** que ma propre équipe, mais
> on ne l'a exercé jusqu'ici que pour MON équipe + l'IA native via `aiturn`. Au
> premier `act` côté équipe 2, **vérifier `mutated=true` + cascade non vide**. Si
> l'`applyAction` rejette les messages côté adverse, le signaler (on ajoutera un
> sous-commande de confort `oppact`), ne pas insister à l'identique.

### Après chaque round

`status` → survivants par équipe + winner. **Boucler** jusqu'à une équipe à 0
(`*** BATTLE FINIE — team gagnante : X ***`). Puis `dispose`.

`play --spec '[...]'` fait un round complet en un coup (mes actions + endturn +
`aiturn` + status + carte suivante) — pratique **uniquement** contre `ia` ; pour
`claude`/`humain` rester en `act` pas-à-pas.

---

## 4. Lire la carte décision

```
=== CARTE DÉCISION — tour T · joueur P (team N) ===
       0 1 2 3 4 5 6 ...        <- index colonnes
r 6   . . a . B . .             <- une ligne par row
...
```

- **MAJUSCULE** = mes units, **minuscule** = ennemis (détail en légende).
- **Glyphes terrain** : `.` grass · `~` water · `#` block · `=` bridge ·
  `s` swamp · `b` drybush · espace = non jouable.
- **Chiffre `1..N` sur une tile = danger zone** : NB d'ennemis pouvant frapper
  cette tile au prochain tour (move ∪ portée, **LoS incluse** pour ranged).
  `1` = effleuré, `N` = focus → ne pas y laisser un fragile.
- **Légende** : `u<id> [visualId] «nom» <MOI|ENNEMI> HP<hp> move<M> <mêlée|ranged rN>`.
- **PLANS D'ATTAQUE** : par unité, `vs u<cible> : (col,row)[min-max{K!|K?}] > ...`
  rankés par utilité IA.
  - **`K!`** = kill **garanti** (dmgMin ≥ hp, indépendant du roll).
  - **`K?`** = kill **possible** (dmgMax ≥ hp mais dmgMin < hp → dépend du roll).
- **`À ACTIVER`** = mes units avec action restante (suit les kills dynamiquement).

---

## 5. Observer (après chaque action ET après le tour adverse)

**Ne PAS inférer depuis les seuls deltas HP — lire le stream causal** (qui frappe
qui, et pourquoi). (file:///C:/Users/nicolasv/tacticus-tools/scripts/python/stream_events.py)
décode/analyse la cascade `StreamDispatcher` capturée par `applyAction` :

`stream_events.analyze(cascade, my_ids)` classe **uniformément** par direction :
`received` (dégâts encaissés), `dealt` (dégâts infligés / ma réaction), `deaths`,
`effects`. Chaque `UnitDamaged` porte attacker / target / amount / crit / killed /
ability / `effect` (label). `aiturn` capture **toute la cascade** du tour adverse
(champ `cascade`, pas que l'overwatch) → bilan `SUBI / MA RÉACTION / kills`.

- **Overwatch = un event comme un autre** : `UnitDamaged` taggé `effect=overwatch`
  (`Effect_Type=1009`), au même titre que `dot` (5). Aucun traitement spécial — il
  apparaît dans `received` (si subi) ou `dealt` (ma réaction overwatch).
- **Aura / contagion** (ex. `ContagionsOfNurgle` de `deathBlightbringer`) : dégâts
  en **ENTRANT** dans la portée — **pas** un contre. Lire le kit de la cible **et
  des voisins** avant d'approcher.
- **Contre / thorns** (`AutoCounterAttackAbility`, `CounterAttackEffect`,
  `EffectType.Thorns`, `GrimRetribution`) : riposte quand l'unité est **frappée
  en mêlée**.

> ⚠️ **`DamagePrediction` est SORTANT uniquement** (dégât que J'INFLIGE) — il
> n'inclut **jamais** le dégât REÇU (aura / contre / overwatch). Anticiper ces
> coûts via le **kit + la géométrie** (gameconfig + hexgeo), pas via les plans.

---

## 6. Doctrine (apprise — sound quel que soit l'adversaire)

- **Tuer tôt** les ranged / psykers / casters, **souvent depuis la tile courante**
  (zéro move, zéro exposition).
- **AoE / splash** (ex. `thousSorcerer`) quand plusieurs cibles sont groupées.
- **Kiter** les tanks lents (move faible) à distance.
- **Focus-fire avec éval inter-action** : enchaîner sur une cible jusqu'au kill,
  s'arrêter **dès qu'elle meurt**, rediriger le surplus (no overkill — ex. laisser
  une cible à 377 puis l'achever pile `K!`).
- **Éviter l'overwatch** : ne pas entrer dans la zone d'un overwatcher armé. Si
  l'ennemi s'y jette (faute), l'**observer** dans le stream et le punir.
- **Protéger les fragiles** : un fragile en row 0 n'est PAS safe si l'ennemi est à
  move+range (on a perdu une unité ainsi).
- **Anticiper aura/contre** : lire le kit de la cible et des voisins avant
  d'approcher/frapper (cf. §5).
- **Summons** : les units `genes*` auto-spawn Decoy (HP0) + Neophyte (ranged) —
  meat shields ; ne pas se laisser distraire dans les comptes.

> **Sans présupposer le niveau adverse** : ces tactiques visent un jeu optimal.
> Ne PAS tendre des pièges qui ne marchent que contre une IA gloutonne.

---

## 7. Pièges (NE PAS refaire)

- **Warmup manquant après reinject** → `applyAction`/`buildPatchedRunner`
  échouent (caches `MethodInfo*` + init IL2CPP vides), crash `0x2c`. Voir §1.
- **`py` au lieu de `python`** → psycopg2, ingest PG skippé silencieusement.
- **Move rejeté silencieusement** : `ok=true` mais `mutated=false` + cascade vide
  = tile illégale/inatteignable → traiter comme **illégal**, ne pas réessayer à
  l'identique.
- **Console Windows cp1252** : préfixer `PYTHONIOENCODING=utf-8` sinon crash sur
  `→` / `⚠` / `«»`.
- **Pump bloque le main thread** : `aiturn`/`--advance` est chunké (≤ 2-4 tours)
  sinon `UnityFreezeDetector` tue le jeu. Combat entier = boucle de chunks (Unity
  pompe ses frames entre les appels).
- **Ne pas restart le host en plein combat** : perd le runner + la sync mirror.
  Mémoire : `feedback_host_restart_kills_mirror`.

---

## 8. Référence — sous-commandes `rl_duel.py`

| Commande | Effet |
|----------|-------|
| `build [--seed S] [--rank R] [--roster N] [--p-units …] [--a-units …] [--p-mow id] [--a-mow id] [--mow] [--list-pool] [--advance K]` | Monte le runner (rosters choisis ou aléatoires + MoW), sauve l'état, affiche la carte |
| `view` | Ré-affiche la carte décision |
| `act move --unit U --to C,R` | Déplace une unité (footprint destination) |
| `act ability --caster U --target T [--ability A]` | Ability (auto-résout l'id depuis le plan ; **`--ability` obligatoire pour les MoW**) |
| `act finish --unit U` | Termine l'activation d'une unité |
| `act endturn` | Fin de mon tour → main à l'adverse |
| `aiturn [--maxpump N]` | 1 tour de l'IA native, décode **toute la cascade** (SUBI/MA RÉACTION/kills) |
| `play --spec '[JSON actions]'` | 1 round complet auto (vs `ia` uniquement) |
| `status` | Stage + survivants par équipe + winner |
| `dispose` | Libère le runner |

Format `--spec` : `[{"kind":"move","unit":95,"to":[3,2]},`
`{"kind":"ability","caster":97,"target":89},{"kind":"finish","unit":95}]`.

---

## 9. Liens

- Harnais duel : (file:///C:/Users/nicolasv/tacticus-tools/scripts/python/rl_duel.py)
- Merge / carte : (file:///C:/Users/nicolasv/tacticus-tools/scripts/python/oracle.py) ·
  (file:///C:/Users/nicolasv/tacticus-tools/scripts/python/board.py) ·
  (file:///C:/Users/nicolasv/tacticus-tools/scripts/python/hexgeo.py) ·
  (file:///C:/Users/nicolasv/tacticus-tools/scripts/python/gameconfig.py)
- Décodage events : (file:///C:/Users/nicolasv/tacticus-tools/scripts/python/stream_events.py)
- Probe pas-à-pas : (file:///C:/Users/nicolasv/tacticus-tools/scripts/python/rl_probe_step.py)
- RPC / RE toolkit : (file:///C:/Users/nicolasv/tacticus-tools/docs/rl/ai-step-toolkit.md)
- Hooks `applyAction`/`decisionView`/`aiPlayByUnit` :
  (file:///C:/Users/nicolasv/tacticus-tools/frida/hooks/features/ai-step.ts)
- Skill socle (injection/warmup/builder) : (file:///C:/Users/nicolasv/tacticus-tools/.claude/skills/tacticus/SKILL.md)
- Mémoire : `project_oracle_pipeline`, `project_turn_order_dynamic`,
  `project_overwatch_blindspot`, `project_effect_type_attribution`,
  `project_ability_normal_attack_concrete`, `feedback_warmup_after_every_reinject`.
