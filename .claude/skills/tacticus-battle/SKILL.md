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
`currentPlayer` bascule sur l'équipe 2. `view` garde MES units labellées MOI
(**POV stable** — les labels ne s'inversent plus) et affiche `⚠ POV ADVERSAIRE`
+ la liste `À ACTIVER` des units de l'équipe 2 = **celles à jouer ce tour** — je
les joue via `act` exactement comme les miennes, ou je laisse l'IA jouer (`aiturn`).

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

---

## 2. Monter la battle

```bash
# rosters ALÉATOIRES (déterministe par --seed). --board OBLIGATOIRE (cf. runner.md).
PYTHONIOENCODING=utf-8 python scripts/python/rl_duel.py build \
  --seed 777 --board MC1_67 --rank 17 --roster 5 [--advance K] [--maxpump 2000]

# rosters CHOISIS (+ MoW optionnels)
PYTHONIOENCODING=utf-8 python scripts/python/rl_duel.py build --rank 17 --board MC1_67 \
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
> deux équipes.** « Kit complet » = pour CHAQUE unité, ses **3 dimensions** :
> **(1) STATS** (PV, move, portée d'arme, profils/PiercingRatio de dégâts),
> **(2) ABILITIES** (actif(s) : effet, nrOfHits, range, cooldown/munitions, cibles),
> **(3) TRAITS** (passifs + traits transverses : Resilient, FinalJustice, Flying,
> Psyker, Healer, Mechanical, Overwatch…). Les trois ensemble — pas seulement
> l'actif. Sauter cette étape = se faire surprendre (ex. le snowball de Kharn
> ci-dessous). C'est non négociable.

> **ORDRE IMPÉRATIF — gameconfig D'ABORD, wiki ENSUITE (complément).**
> 1. **`gameconfig.py` + `i2_en.json` = la SOURCE DE VÉRITÉ** : lire le kit complet
>    de **CHAQUE** unité des deux rosters EN PREMIER (chiffres + texte de règles).
>    C'est la base ; ne JAMAIS commencer par autre chose.
> 2. **PUIS `docs/rl/wiki.md` en COMPLÉMENT** : il n'ajoute QUE le non-dérivable
>    (interactions de traits, vérités de combat observées). Il ne remplace pas la
>    recon gameconfig — il la complète, pour les unités/traits déjà documentés.
> Inverser l'ordre (wiki avant gameconfig) est une ERREUR : le wiki est partiel
> (ne couvre pas tout roster) et second par nature.

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

> **RECON CONTINUE — pas que le tour 1.** Dès qu'une **unité INVOQUÉE / ressuscitée
> apparaît** en combat (ids `*Smn*` / `*Npc*` : decoy, drone, Aberrant, Hormagaunt,
> Guardsman, Poxwalker…), faire **IMMÉDIATEMENT** `gameconfig.py <visualId>` — ses
> **traits/abilities dictent comment la gérer**, ne JAMAIS supposer. Vécu : decoy
> `genesSmnDecoy` laissé non-recon → j'ignorais son trait `Steppable` (« détruit en
> marchant dessus, non-ciblable ») → je n'ai pas coupé l'`Ambush` → Biophagus a
> ressuscité. (Ex. à connaître : decoy `Steppable` → marcher dessus ; unité qui explose
> en mourant → tuer à distance ; counter/aura → kit des voisins.) Cf. wiki §3ter Summons/NPC.

> **RECON DES EFFETS — à l'apparition, comme un summon.** `decisionView` expose par
> unité ses **effets actifs** (champ `effects` — lus depuis la liste native du jeu
> `EffectsOwnedComponent`, = ce que l'UI render en icônes ; nom + `remaining` tours +
> `source`). Noms typiques : `Ice`, `Stunned`, `Overwatch_AutoAttack`, `Markerlight`,
> `FuryOfTheAncients`, `Taunted_*`, `ContagionsOfNurgle_ArmorReduction*`,
> `TeleportStrike_TeleportingIn`, `HeavyRailRifle_PendingTarget`… **Dès qu'un effet
> INCONNU apparaît, le RECON** avec **`python scripts/python/gameconfig.py --effect <nom>`** :
> ça strippe le suffixe `<Ability/Trait>_<…>` → résout l'ability/trait SOURCE et imprime
> ses chiffres gameconfig + texte de règles i2 (ne JAMAIS supposer). Effet **moteur pur**
> sans source (`Ice`, `Stunned`, `Taunted_*`) → la commande le signale → **wiki §1 Traits**. **Ne jamais ignorer un
> effet « pending » sur MES unités** : `HeavyRailRifle_PendingTarget` = railgun armé
> sur cette unité → la faire **BOUGER ≥3 hex** ce tour (−30 % dmg/hex traversé), sinon
> tir plein. Vécu (défaite) : Ahriman gardé statique malgré le mark → **7240** → carry
> mort. `remaining` : `r>0` = effet temporisé, `r0` = permanent/aura.
> **TIR DIFFÉRÉ = magnitude ≫ nominal (TF28)** : un effet pending-fire ENNEMI sur MES
> units (`SeekerMissileFrequencyLock`, `Markerlight`, `HeavyRailRifle_Pending`,
> `MalleusRocketLauncher_*`, `TargetingProtocols_PendingAttack`…) est tagué
> `⚠ [PENDING-FIRE≫]` dans EFFETS CRITIQUES. Le hit réel est **AMPLIFIÉ bien au-delà du
> nominal gameconfig** (RangedSpecialist + HeavyWeapon + markerlight cumulés : Seeker
> nominal ~5500 → **9263** observé sur 9537 PV). **NE PAS** projeter « nominal survivable »
> ni HOLD passivement en portée : bouge la cible hors-range / dépense-la offensivement ce
> tour / tue le caster AVANT le tir.

- **`docs/rl/wiki.md` — LECTURE OBLIGATOIRE au recon, mais EN COMPLÉMENT (étape 2,
  APRÈS gameconfig/i2 de l'étape 1, jamais avant)** : une fois le kit chiffré lu,
  lire l'entrée wiki des unités **déjà documentées** (kits, quirks, traits — §2
  Chaos / §3 Imperium / §4 MoW) + la référence des **mécaniques de traits
  transverses** (§1 : Resilient×multi-hit, FinalJustice, Explodes, Blast vs
  armure…). C'est le savoir-jeu NON dérivable de gameconfig/i2 (qui n'ont que
  noms+chiffres+texte, jamais les interactions) — donc un **ajout**, pas un
  substitut : une unité absente du wiki se joue quand même (gameconfig suffit). **L'ENRICHIR après chaque combat**
  (nouvelle unité rencontrée, interaction observée). La doctrine ACTIONNABLE (quoi
  FAIRE de ces mécaniques) est dans le skill §6/§7 — le filet de sécurité que je lis
  toujours, même si j'oublie le wiki.

> **RÈGLE D'INSCRIPTION (classer AVANT d'écrire) — n'inscrire qu'un fait
> GÉNÉRAL + VÉRIFIÉ + NON-DÉRIVABLE. Le reste est jetable.** Un constat tiré
> d'un combat passe ce filtre AVANT d'aller en doctrine, sinon il m'induit en
> erreur ailleurs :
> - **Rejeter l'overfit contextuel** : ce qui dépend de CE match (positions,
>   « row 2 = safe », un roll, un placement) ne se généralise pas. Garder le
>   **noyau général** s'il existe (souvent déjà couvert par un principe du skill →
>   alors rien à ajouter), jeter le contexte.
> - **Ne pas dupliquer le dérivable** : si gameconfig/i2 le dit déjà (ex.
>   « Terrifying = −dmg **Melee** » → un ranged n'est pas réduit), c'est de la
>   recon, pas de la doctrine → rien à écrire.
> - **Ne pas inscrire une devinette** : un mécanisme supposé / n=1 non vérifié
>   (ex. « la ligne du MoW suit les axes hex ») se **vérifie** (gameconfig/i2/probe)
>   AVANT d'être écrit ; sinon ne rien écrire.
>
> Destination une fois le filtre passé : **savoir-jeu non-dérivable → wiki**
> (interactions de traits §1, kits §2-4) ; **doctrine actionnable + caveats
> OUTIL/process** (label `K!` optimiste, fiabilité d'un RPC/d'un actif, géométrie
> hex…) **→ skill** — jamais dans le wiki, qui ne décrit QUE le jeu, jamais mes
> outils. Cf. [[feedback_oracle_kb_architecture]].

**Grab AUSSI les ids + l'état LIVE des actifs au recon** : `view` (decisionView
`allAbilities:true`, défaut depuis le fix) affiche la section **« MES ACTIFS (état
live) »** = par unité ses actifs `Nom(id) [prêt/cdN/disabled/munitionsN]`. Les
**ids** servent à `act ability --ability <id>` (les noms seuls sont déjà dans
gameconfig → inutiles) ; l'**état** dit ce qui est **castable CE tour** (cooldown/
munitions) — info que gameconfig NE PEUT PAS donner. Les MoW affichent idem.
> ⚠️ La **prédiction de dégâts** d'un actif dans les plans n'est PAS fiable
> (decisionView rend ~les chiffres de l'attaque NORMALE pour tout actif) : se fier
> aux **tuiles + l'état**, et juger le **résultat réel à la cascade** (cf. wiki §1
> Blast vs armure). Les chiffres bruts gameconfig sur-estiment (armure ignorée).

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

> 🛡️ **AVANT CHAQUE TOUR — MOVE-GUARD (anti-over-extension, OBLIGATOIRE).**
> L'over-extension (pousser une unité où l'IA la focus pour rien) est le failure-mode
> DOMINANT, et elle se **construit tour par tour** (le danger d'un move n'est souvent
> visible qu'au tour où l'IA peut l'atteindre). Donc : **avant CHAQUE `play`** (T1, T2,
> T3, …), simule ton tour proposé :
> ```
> python scripts/python/rl_duel.py guard --climb --spec '<mon tour COMPLET>'
> ```
> Le guard **clone** le combat (ne touche PAS le live), **reconstruit le tour courant**
> en rejouant l'historique de tes vrais moves (`action_log`, enregistré automatiquement
> par `play`), applique ton spec, **fait jouer 1 tour à l'IA ADVERSE** (CheatRunAIMessage
> = ground truth ; **l'IA ne joue JAMAIS ta team**), et reporte le **NET** du tour +
> un **spec recommandé** (il recule les units qui mourraient pour rien).
> - **NET = leurs_pertes − mes_pertes sur CE tour.** **NET < 0 = l'IA te focus AVANT toi
>   = OVER-EXTENDED.** **NET ≥ 0 = focus-first (tu tiens / gagnes l'échange).**
> - **VERDICT `OVER-EXTENDED`** → joue le **spec recommandé** affiché (`play --spec
>   '<recommandé>'`), PAS le tien.
> - **`FOCUS-FIRST` / `SERRÉ-neutre`** → joue ton tour tel quel.
> Coût ~5 sims, **déterministe** (RNG combat reproductible → 1 sim/plan ; le replay
> reconstruit l'état live à l'identique, vérifié). À appeler **à chaque tour tant qu'il
> reste un risque de contact** ; inutile une fois le combat clairement gagné/perdu.
> Détails : `docs/rl/move-guard.md`.

1. `view` (ou la carte déjà affichée).
2. **Lire la carte** (§4).
3. Décider l'ordre d'activation + les actions.
4. **Une action à la fois, ré-éval entre chaque** (`act` ré-affiche les plans
   après l'action — base de la décision suivante) :
   - **Jouer une unité « en 2 temps »** : `act move --unit U --to C,R`, observer
     le résultat, **puis** `act ability --caster U --target T --ability <id>`.
   - **Abilities ciblant un HEX LIBRE** (summons type AlphaWarrior/ForwardSpotter,
     mur DutyEternal, marquage sur case vide) : `act ability --caster U --to C,R
     --ability <id>` (PAS `--target`). Le hook résout le hex → entité-tuile
     (`ActiveAbilityMessage` n'a pas de champ position). `--ability` obligatoire
     (pas de plan auto-résolu sans cible ennemie). Validé : AlphaWarrior → Warrior
     7976 PV. (Cibler une ENTITÉ : `--target <id>` ; sa tile sert pour MacroPlasma.)
   - **TOUJOURS passer `--ability <id>` explicite** (id depuis la section « MES
     ACTIFS » / le label du plan). L'**auto-résolve n'est PLUS fiable** depuis
     `allAbilities` : il peut piocher le mauvais id (un actif au lieu de l'attaque
     normale) → l'unité **consomme son action pour un no-op** (vécu : Trajann tape
     « 0 » et est grillé). Attaque normale = **id 69** (générique « Loki_NormalAttack »,
     partagé par bcp d'unités) ou l'id propre de l'unité. **En `play --spec`, utiliser
     `{"kind":"normal","unit":N,"target":T}`** : l'outil résout la `NormalAttackType`
     CONCRÈTE de l'unité (jamais 69 à deviner, jamais un actif par défaut) et pré-valide
     la portée — cf. §8.
   - **VÉRIFIER que le move a réussi AVANT d'attaquer** : `act move` vers une tile
     illégale (block `#`, hors portée) est **rejeté SILENCIEUSEMENT** (l'unité reste
     sur place) → l'attaque part alors hors portée = no-op qui grille l'action.
     Lire la position effective (`view`) si doute. (Vécu : repli sur (1,0)=block
     ignoré ; Mephiston resté exposé.) Rappel : un **move ne consomme PAS**
     l'activation (on peut move puis attaquer) ; seule une **attaque/ability** la
     consomme (`TurnFinished=1`). Pour le **set de repositionnement résolu** (par
     blockers/terrain), `moves [--unit U]` = grille ASCII des tuiles légales.
   - **LÉGALITÉ d'une ability — NE PLUS deviner la portée.** « MES ACTIFS » de
     `view` donne, par actif, `now[..]` (castable **SANS bouger**) / `+move[..]`
     (seulement **après déplacement**) / `∅` (**no-op certain**) — Y COMPRIS les
     abilities **NON-attaque** (buff/heal/summon/hex, **absentes des PLANS
     D'ATTAQUE**) et les MoW. Détail par `abilities [--unit U] [--ability A]`.
     → cible ∈now = caste maintenant ; ∈+move seul = **bouge d'abord** ; ∉ des deux
     = **n'essaie pas** (no-op certain). En `play`/`act`, un cast illégal — cible
     ENTITÉ (`--target`) **OU** hex/tuile (`--to` : bombard / ligne à axe FIXE / summon
     sans spawn-tile) — est désormais **rejeté avant l'endturn** avec la raison exacte
     (axe / portée / spawn-tile), plus de no-op silencieux ; sinon
     `reason --caster U --ability A [--target T]` diagnostique le no-op (flag
     `TargetingRule` : `TargetIsInRange` / `TargetIsTargetable` / `AlreadyUseThisTurn`
     / `NoBroken`=valide…). `reason` affiche aussi l'**ÉTAT LIVE** (`cooldown=N`/
     `disabled`/`prêt`) : la couche targeting peut dire `ValidRequest` alors que
     l'ability est **cooldown-locked** — l'ÉTAT LIVE tranche (TF24).
   - **SUMMONS sur hex** (MasterOfTheTutelaries d'Abraxas, AberrantHypermorph,
     AlphaWarrior, ScarabHive…) : le Pink Horror/l'unité **spawn À LA TUILE `--to`**,
     qui DOIT être ∈`now` (`fromHere`). Caster sur une tuile **`+move` seule = NO-OP**
     (`ok=True` mais `spawned=0`, `actionConsumed=False`, action NON consommée — le
     piège TF12). Ces summons sont **bien armables** (l'ancienne doctrine « éviter
     MoTT » était fausse) : prends une tuile de la liste `now` du summon dans `MES
     ACTIFS`/`abilities`, pas `+move`. La pré-validation rejette déjà la tuile `+move`
     (« atteignable seulement +move → déplace d'abord »).
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
(`*** BATTLE FINIE — team gagnante : X ***`). Puis `dispose`. Pour **juger l'abandon
sans compter HP/unités à la main** (sur-estimer « je gagne » est un piège récurrent) :
`verdict` → `decided: won|lost|undecided` + score de position (`won` n'est déclaré qu'à
élimination adverse = prudence asymétrique).

`play --spec '[...]'` fait un round complet en un coup (mes actions + endturn +
`aiturn` + status + carte suivante) — pratique **uniquement** contre `ia` ; pour
`claude`/`humain` rester en `act` pas-à-pas.

---

## 4. Lire la carte décision

```
=== CARTE DÉCISION — mon tour #N · joueur P (team M) ===
  ⚠ POV ADVERSAIRE — …       <- ligne présente UNIQUEMENT au tour de l'adversaire
       0 1 2 3 4 5 6 ...        <- index colonnes
r 6   . . a . B . .             <- une ligne par row
...
```

- **En-tête `mon tour #N`** = compteur de tour FIABLE (monotone, dérivé de l'historique) —
  s'y fier pour juger la proximité du round-cap. **POV stable** : MES units sont TOUJOURS
  labellées MOI / l'adversaire ENNEMI, même quand `currentPlayer` bascule sur l'adversaire ;
  dans ce cas une ligne `⚠ POV ADVERSAIRE` rappelle que les PLANS/ACTIFS affichés sont
  les SIENS (c'est son tour). (Plus de label MOI/ENNEMI qui s'inverse au flip.)
- **MAJUSCULE** = mes units, **minuscule** = ennemis (détail en légende).
- **Glyphes terrain — des SYMBOLES, jamais des lettres** (donc toute lettre sur la carte
  est une UNITÉ, jamais du terrain) : `.` grass · `~` water · `#` block · `=` bridge ·
  `%` swamp · `*` drybush · `?` autre · espace = non jouable.
- **Chiffre `1..N` sur une tile = danger zone** : NB d'ennemis pouvant frapper
  cette tile au prochain tour (move ∪ portée, **LoS incluse** pour ranged).
  `1` = effleuré, `N` = focus → ne pas y laisser un fragile.
  > ⚠️ **POINT DE VIGILANCE — la danger-zone est une BORNE BASSE : elle SOUS-AVERTIT.**
  > Calcul géométrique sur le `move` de **base** × portée d'**ARME** seulement. Un chiffre
  > bas ou **0 n'est PAS « safe »**, surtout pour le carry. Elle IGNORE :
  > - **buffs de move** (`RapidAssault` +1 jusqu'à l'attaque, conditionnels type
  >   `DestroyTheWitch`, auras, `Unstoppable`) → reach réel > affiché ;
  > - **actifs RANGED** (`PlasmaCannon` r3, `Stormcaller` r3, `RadBombardment`…) : une
  >   unité **sans arme ranged** (affichée « mêlée », ex. Baraqiel) peut frapper **à
  >   distance** — `unit_kit` ne lit que `weapons`, pas les actifs ;
  > - **deep-strike / `TeleportStrike`** (reach = **TOUT le plateau**), **MoW artillerie**
  >   (frappe **partout**, souvent absente du calcul), **summoners** (posent un corps qui
  >   attaque **adjacent à MON unité**, indépendant de leur reach) ;
  > - les **dégâts** : c'est un COMPTE de menaces, pas une létalité — « menacée par 1 »
  >   peut tuer (burst ~8k, Psychic qui **ignore l'armure**).
  > De plus le numéro **sous le glyphe de MA propre unité est caché** → juger la sécurité
  > du carry via les **kits ennemis** (recon §2bis : qui a move-buff / actif-ranged /
  > deep-strike / summon), **pas** via le seul overlay. **Compenser à la main** : traiter
  > deep-strikers / MoW / summoners en **omni-menaces**, et juger « tuable ? » aux dégâts,
  > pas au compte. (Vécu seed 33182 : Calandis jugée « safe » en (3,1) contre la mêlée →
  > tuée par du **ranged** ; `PlasmaCannon` r3 de Baraqiel modélisé « mêlée ».)
- **Légende** : `u<id> [visualId] «nom» <MOI|ENNEMI> HP<hp> move<M> <mêlée|ranged rN>`.
- **PLANS D'ATTAQUE** : par unité, `vs u<cible> : (col,row)[min-max{K!|K?}] > ...`
  rankés par utilité IA.
  - **`K!`** = kill **garanti** (dmgMin ≥ hp, indépendant du roll).
  - **`K?`** = kill **possible** (dmgMax ≥ hp mais dmgMin < hp → dépend du roll).
- **`À ACTIVER`** = mes units avec action restante (suit les kills dynamiquement).
- **`MES ACTIFS`** = par unité contrôlée, ses actifs + état live (`prêt`/`cdN`/
  `disabled`/munitions) **+ cibles légales** `now[..]` (sans bouger) / `+move[..]`
  (après déplacement) / `∅` (no-op certain) — couvre les abilities **non-attaque**
  invisibles dans PLANS D'ATTAQUE. La section **MoW** affiche idem ses cibles. (cf. §3
  « LÉGALITÉ d'une ability », commandes `abilities`/`reason`.)

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
  move+range (on a perdu une unité ainsi) — **y compris via un actif RANGED** (ex.
  `PlasmaCannon` r3 de Baraqiel touche cible + 2 derrière → a chunké Calandis « safe »
  en (2,0)). La danger-zone **sous-estime** ces portées (cf. §4) : juger à la main.
- **Vs une compo FOCUS-FIRE (concentre ~20k+/tour) : ne JAMAIS présenter de cible
  ISOLÉE.** Une unité seule au contact / à portée — même un tank 12k, même un Wrask
  shieldé — meurt en **UN tour** (vécu seed 33182 : Jaeger puis Wrask focus-down). Garder
  les units **groupées et en soutien mutuel** ; n'engager qu'avec une **masse** que
  l'ennemi ne peut pas focus-kill entièrement ; **réduire leur output** (tuer les dealers
  + le moteur de sustain) plutôt que chercher à out-trade un adversaire qui focus mieux.
  Compo focus + sustain (heal/revive) + summons (Apothecary + MoW `ForwardSpotter`) =
  **hard-counter** de mon roster de briques mêlée → pour démontrer « oracle > IA », prendre
  un **matchup équilibré** (cf. [[project_battle_doctrine]]).
- **Deep-strike (`TeleportStrike`, mes units type Wrask) = redéploiement TURN-1 ONLY, à
  utiliser TOUT DE SUITE** (il expire au 1ᵉʳ `endturn` ; le « garder en réserve » le
  gaspille et l'unité doit ensuite traverser à pied). **NE JAMAIS le projeter SEUL en
  avant** : il atterrit non-adjacent (pas d'attaque = **« tour de gap »**) → focus-down
  isolé avant d'agir (= mort de Wrask). Le téléport sert à **sauter la traversée (unité
  lente) / infiltrer un flanc-backline**, et **uniquement s'il arrive en GROUPE supporté**
  (ou sur un atterrissage hors de portée). Mécanique complète : wiki §1 `TeleportStrike`.
- **Actif à move INTERNE (gap-close) : NE PAS pré-bouger le caster.** Certains actifs se
  déplacent EUX-MÊMES avant de frapper (ex. `VigilanceEternal`/Tyrith) — pré-bouger l'unité
  consomme son move → l'actif no-op (`TargetIsInRange`, activation gaspillée). Lire la
  légalité `now` de l'actif (`abilities`/« MES ACTIFS ») AVANT de bouger : si castable `now`,
  il gère le move lui-même → **ne pas pré-déplacer**. (TF16 — la pré-validation outil ne
  couvre pas ce cas : c'est une règle de séquencement.)
- **Anticiper aura/contre** : lire le kit de la cible et des voisins avant
  d'approcher/frapper (cf. §5).
- **Summons** : les units `genes*` auto-spawn Decoy (HP0) + Neophyte (ranged) —
  meat shields ; ne pas se laisser distraire dans les comptes.
- **`Resilient` ne sauve PAS d'un multi-hit** : 1ᵉʳ coup → 1 PV, coups suivants du
  MÊME actif tuent. Vs burster multi-hit (Kharn, Macer) la défense = **STUN ou mur**,
  PAS le HP. **Overkill** les Resilient (sinon retour à 1 PV gratuit). Détail : wiki §1.
- **`FinalJustice` (Kharn) → riposte mortelle à la mort sauf OVERKILL** — même
  stunné, même tué à l'AoE/killzone. Ne jamais le tuer « pile » : **overkill**, ou
  ne pas laisser d'unité adjacente quand il meurt.
- **Ne pas chiper `Drachnyen`/Abaddon** (SET PV à 4729 = re-heal) : alpha+overkill
  en UN tour, ou ignorer. Mephiston (Psychic) bypasse son TerminatorArmour.
- **`Explodes` = friendly fire** : tuer les ennemis `Explodes` (Pestillian) **à
  distance** ; ne pas coller MES unités à mon unité `Explodes` (Morvenn) si elle peut mourir.
- **Ouvrir un focus par un ACTIF adjacent** (LegendaryCommander+StandVigil → +800
  + hits bonus + ouvre des tuiles). Le stun (VexillaMagnifica) neutralise un burster 1 tour.
- **MoW killzone** (MacroPlasma) : cibler **une de MES unités avancées** marque la
  zone devant elle → la meute qui avance la traverse → AoE (tue Poxwalkers, finit les low).
- **L'artillerie du MoW ennemi frappe partout** (ranged ~2600-2900/tour) : le repli
  ne protège pas les fragiles → l'inclure dans la menace.
- **Tuer le MOTEUR en priorité** : l'unité qui heal / summon / buff l'équipe
  (ex. Biophagus, Re'vas-drones, un buffer) vaut bien plus que sa barre de PV — la
  retirer coupe le sustain adverse. (Attention aux résurrections `Ambush` : decoy →
  retour 1×, le 2ᵉ kill est permanent ; détruire les decoys si on peut.)
- **Summon-snowball** (roster summon : WingedPrime, MoW ForwardSpotter…) : invoquer
  TÔT (via `--to`, cf. §3) → présence de board croissante ; les summons **tradent en
  réaction** (overwatch/contre) même sans jouer leur tour. A renversé un matchup
  équilibré (fini 8 units vs 1).
- **AoE retardée / Taunt** = pattern fort : Taunter un cluster sur un tank + AoE qui
  fire au tour suivant (Eightbound OverwhelmingWrath) ; barrage MoW marqué au tour T,
  fire à T+1. Setup défensif + dégâts groupés.

> **Sans présupposer le niveau adverse** : ces tactiques visent un jeu optimal.
> Ne PAS tendre des pièges qui ne marchent que contre une IA gloutonne.

---

## 7. Pièges (NE PAS refaire)

- **Amorce manquant après reinject** → `applyAction` / les builds de runner
  échouent (caches `MethodInfo*` + init IL2CPP vides), crash `0x2c`. Voir §1.
- **`py` au lieu de `python`** → psycopg2, ingest PG skippé silencieusement.
- **Move rejeté silencieusement** : `ok=true` mais `mutated=false` + cascade vide
  = tile illégale/inatteignable → traiter comme **illégal**, ne pas réessayer à
  l'identique.
- **Attaquer/caster HORS PORTÉE** : `play`/`act` **pré-rejettent** désormais ce cas avant
  l'endturn avec la raison (`TargetIsInRange` pour une cible entité, « hex hors tuiles
  valides » pour un cast `--to`) — plus de no-op silencieux. Discipline maintenue :
  déplacer l'unité sur la tuile du plan AVANT l'attaque. ⚠️ une action rejetée n'est
  **PAS forcément consommée** — vécu : le Terminator est resté
  dans `à activer` après (donc ré-utilisable), contrairement à ce que je croyais.
  Règle sûre : `act move --to <tuile du plan>` PUIS `act ability` ; et après un coup à
  0/cible inchangée, **RE-VÉRIFIER `à activer`** (l'unité est souvent encore dispo —
  ne pas la croire grillée). (Cas Guardsman retiré de la liste = inexpliqué, summons ?)
- **Overwatch ennemi armé non visible** : je n'ai pas d'overlay des zones d'overwatch
  (la danger zone ≠ trigger-en-bougeant). En attendant le fix, lire les kits (qui peut
  overwatch : Re'vas EarlyWarningOverride, Azrael, Maugan Ra…) + estimer position+range,
  et router à distance / depuis le côté opposé. Cf. wiki §3bis (GAP) + [[project_overwatch_blindspot]].
- **Console Windows cp1252** : préfixer `PYTHONIOENCODING=utf-8` sinon crash sur
  `→` / `⚠` / `«»`.
- **Pump bloque le main thread** : `aiturn`/`--advance` est chunké (≤ 2-4 tours)
  sinon `UnityFreezeDetector` tue le jeu. Combat entier = boucle de chunks (Unity
  pompe ses frames entre les appels).
- **Timeout de RÉPONSE ≠ échec (applied-but-slow)** : pendant un pump lourd, un
  `applyAction`/`play` peut timeout sur la **réponse** alors que l'action a **DÉJÀ
  appliqué** → **vérifier `status`/`view` AVANT de re-jouer la même action** (ne pas
  double-apply). En self-play, l'endpoint host `/api/selfplay/:id/await` **avale** les
  timeouts internes transitoires (pump) et renvoie un `timedOut` propre (+ `transientError`),
  jamais un raw-fail → **ré-émettre** l'await. (TF19.)
- **Ne pas restart le host en plein combat** : perd le runner + la sync mirror.
  Mémoire : `feedback_host_restart_kills_mirror`.

---

## 8. Référence — sous-commandes `rl_duel.py`

| Commande | Effet |
|----------|-------|
| `build [--seed S] [--rank R] [--roster N] [--p-units …] [--a-units …] [--p-mow id] [--a-mow id] [--mow] [--list-pool] [--advance K]` | Monte le runner (rosters choisis ou aléatoires + MoW), sauve l'état, affiche la carte |
| `view` | Ré-affiche la carte décision (MES ACTIFS + MoW incluent les cibles now/+move) |
| `moves [--unit U]` | Grille ASCII des tuiles de MOVE **légales** par unité (set résolu par blockers/terrain) |
| `abilities [--unit U] [--ability A]` | Cibles **légales** par (unité × ability) : `now` (sans bouger) / `+move` (après déplacement) / `∅` — incl. abilities NON-attaque + MoW |
| `reason --caster U --ability A [--target T]` | **Raison structurée** d'un cast invalide (flag `TargetingRule` : range/targetable/already-used/…) |
| `act move --unit U --to C,R` | Déplace une unité (footprint destination) |
| `act ability --caster U --target T [--ability A]` | Ability (auto-résout l'id depuis le plan ; **`--ability` obligatoire pour les MoW**) |
| `act finish --unit U` | Termine l'activation d'une unité |
| `act endturn` | Fin de mon tour → main à l'adverse |
| `aiturn [--maxpump N]` | 1 tour de l'IA native, décode **toute la cascade** (SUBI/MA RÉACTION/kills) |
| `play --spec '[JSON actions]'` | 1 round complet auto (vs `ia` uniquement) |
| `guard --climb --spec '[…]'` (ou `--auto hold\|gentle\|aggressive`) `[--cap 5]` | **MOVE-GUARD per-turn** (avant CHAQUE `play`) : clone-sim de ton tour (mes moves → endturn → 1 tour IA adverse, ground truth ; l'IA ne joue jamais ma team) → **NET du tour** (NET<0 = over-extended) + pull-back → **spec recommandé**. Reconstruit le tour courant via `action_log`. Ne touche pas le live. |
| `status` | Stage + survivants par équipe + winner |
| `verdict` | Score de position : matériel (HP + unités/équipe), létalité `K!` ce tour, flag `decided: won\|lost\|undecided` à **prudence asymétrique** (`won` seulement à élimination adverse) — juger l'abandon sans compter à la main (TF02) |
| `dispose` | Libère le runner |

Format `--spec` : `[{"kind":"move","unit":95,"to":[3,2]},`
`{"kind":"ability","caster":97,"target":89},`
`{"kind":"normal","unit":95,"target":89},{"kind":"finish","unit":95}]`.
`normal` = attaque normale, id `NormalAttackType` résolu par l'outil (jamais 69 à deviner, TF18).

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
- Skill socle (injection/builder) : (file:///C:/Users/nicolasv/tacticus-tools/.claude/skills/tacticus/SKILL.md)
- Mémoire : `project_oracle_pipeline`, `project_turn_order_dynamic`,
  `project_overwatch_blindspot`, `project_effect_type_attribution`,
  `project_ability_normal_attack_concrete`, `feedback_no_amorce_needed`.
