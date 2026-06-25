# Backlog outillage (friction & manques signalés par les agents)

Append-only. Tout agent qui bute sur un outil **manquant** ou **améliorable** le signale ici —
jamais de contournement silencieux. `statut` : open|wip|done. `recurrence` = nb de matchs gênés
(prioriser les ≥2). Canal symétrique des hypothèses : `toolfeedback → outillage`.

---

## TF01 — `play --spec` ne gère pas les abilities sur HEX ni les actifs MoW — open — recurrence:3
- **friction** : `--spec` ne couvre que `move` / `ability(target)` / `finish`. Les summons sur hex
  libre (`Incursion --to`, `ResurrectionOrb`, `DeathFromAbove`, `MasterOfTheTutelaries`), le marquage
  MoW (`MalleusRocketLauncher`, `MacroPlasmaIncinerator`) et les self-buffs (`WarHowl`) sortent du flux
  1-appel/round → on retombe en `act ability` un-par-un (coûteux en round-trips).
- **amélioration** : étendre le spec → `{"kind":"ability","caster":N,"to":[c,r],"ability":A}` (hex) et
  `{"kind":"ability","caster":N,"ability":A}` (self) ; + un `{"kind":"mow",...}`. Idéalement un round
  entier (mes actions hétérogènes) en 1 appel.
- **n+1 (seed 80001, ts=b7)** : `BasiliskBarrage` (Thaddeus MoW) est une ability TILE-targeting → passer
  `'target':<entityId>` est REJETÉ (« cast ILLEGAL sans bouger ») même quand l'hex de l'entité est dans le
  now-set ; il faut `'to':[col,row]` (coords de tuile). INCONSISTANT ce match : le 1ᵉʳ barrage a accepté
  `target` (entité à (6,6)) mais un barrage ultérieur a refusé → la forme `to`:[c,r] est la SEULE fiable
  pour les abilities hex/AoE/MoW. Re-confirme le besoin d'un canal `to`:[c,r] explicite pour les MoW/hex.
- vu : G02, G03, seed 80001.

## TF02 — Pas de détecteur « match décidé » pour l'abandon — open — recurrence:3
- **friction** : décider gagné/perdu d'avance se fait à la main (compter HP/unités/win-condition) à
  chaque tour. Sujet à erreur (j'ai sur-estimé 2× « je gagne »).
- **amélioration** : helper `rl_duel.py verdict` → renvoie un score de position (matériel + reach sur la
  win-condition adverse + léthal estimé) + un flag `decided: won|lost|undecided` (prudence asymétrique).
- vu : G01, G02, G03.

## TF03 — `decisionView` bascule de POV (MOI/ENNEMI) quand currentPlayer=4 — open — recurrence:3
- **friction** : quand mon tour s'auto-termine et que la vue passe en POV team-2, les labels MOI/ENNEMI
  s'inversent → re-lectures inutiles, confusion sur les positions. **n+1 (80072)** : B re-confirme le flip,
  ET le `decisionView` du state-file LAG le turn-flip → l'attribution d'équipe est ambiguë sur le tour de
  bascule ; désambiguïser via `status` (autoritatif t1/t2), pas les labels relatifs de la vue.
  **n+2 (80031)** : B a failli mis-play — la 1ʳᵉ vue de son tour labellait « MOI » le set u95-103 (= team1) ;
  caught en dérivant le vrai roster via `myTeam`/`playerUnits`, mais c'est le foot-gun récurrent.
- **amélioration** : option `view --pov me` (toujours mon équipe = MOI), ou afficher teamId explicite.
- vu : G01, seed 80072, seed 80031.

## TF04 — Plans = dmg MAX-roll NON mitigé + label `K!` optimiste (ignore Resilient + réductions + buffs défensifs) — open — recurrence:6
- **friction** : `K!` (« kill sûr ») ne modélise pas Resilient/Terrifying/block → un coup « K! » laisse
  la cible à 1 PV (Azkor). **n+1 (80072)** : au-delà du label, la RANGE dmg des plans est un **MAX-roll NON
  mitigé** — `Doombolt [2409-3613]` a dealt **1343** réel (mitigé par le −50% d'Aun'Shi + block) → l'agent
  a failli mis-committer sur un « kill » fantôme. Induit en erreur sur la létalité ET sur l'output réel.
  **n+2 (80020)** : Dreir LeadingTheCharge prédit gros mais ~821 net sur l'anvil 12k Snotflogga (SupaCyborkBody
  + BeastSnagga block) → charge gaspillée. **n+3 (80085)** : Aesoth normale sur Lucien `[1359-1359 K!]` mais
  SINGLE-HIT floor-à-1 sur un Resilient → ne tue PAS (label `K!` trompeur).
  **n+4 (seed 80004, ts=b7)** : DEUX symptômes convergents sur Njal (TerminatorArmour/Psyker). (a) A : un Shiron
  `Excruciating` `K!` (~3500 prédit) a landé **1010** sur le 1er hit (réduction 1ʳᵉ-attaque TerminatorArmour NON
  modélisée) → un `K!` tagué a laissé Njal à **970 HP** près du round-cap = tour quasi-gaspillé ; doctrine d'ici-là
  = traiter **K! vs TerminatorArmour comme K?** + stacker une 2ᵉ source. (b) B : `Stormcaller` (Njal) prédit
  **4918-5884** dans les PLANS mais réel **1695** (= 3x ~540 Psychic) → B a dû juger par la cascade, pas la
  prédiction (cohérent avec le caveat doctrine : prédictions d'actifs peu fiables). **n+5** = même seed côté B.
- **amélioration** : surfacer le **dmg attendu post-mitigation** (la `DamagePrediction` du jeu existe déjà
  côté caches AI) OU au minimum **tagger la range comme MAX non-mitigé** + une **kill-proba** ; intégrer
  Resilient/Terrifying/Daemon-block/**TerminatorArmour 1ʳᵉ-hit** dans la prédiction (dégrader `K!`→`K?` si trait
  défensif non modélisé).
- vu : G01, seed 80072, seed 80020, seed 80085, seed 80004.

## TF05 — `jq` natif absent (Windows) — done(contournement) — recurrence:0
- **friction** : `npx -y node-jq` lent (re-résout le package à chaque appel).
- **résolution** : on évite jq → parsing via la sortie texte lisible de `rl_duel`/`oracle`. (Installer
  `jq` natif resterait un plus si du JSON structuré devient nécessaire.)
- vu : transverse.

## TF06 — Coexistence multi-runner impossible (le build du 2ᵉ évince le 1ᵉ) — done — recurrence:1
- **friction** : 2 builds (seeds 11111/22222) → le runner buildé en PREMIER devient « not found »
  dès le build du 2ᵉ. PAS de cross-talk (isolation state ✓) → c'est une **PERTE de runner**.
- **diagnostic CORRIGÉ** : ni un bug host, ni une race recorder (mes 2 premières hypothèses — **fausses**,
  héritées d'un framing d'avant-compact). Cause **déterministe** = la **single-build policy d'`initAndStart`**
  (`launch.ts`:490) : elle `disposeRunner()` sur TOUS les runners existants avant d'en construire un. Le
  host n'a aucun auto-dispose automatique (`router.ts`:439 = `DELETE /api/runners/:id` *manuel*).
  `gcRoot.init()` idempotent (pas un blocker). Le recorder match-end auto-dispose existe mais ne
  s'appliquait pas ici (et ne touche que les runners de `watchedRunners`).
- **fix livré (défaut 100% préservé)** : (a) `initAndStart { keepExisting }` opt-in → skip la single-build
  dispose (défaut `false` = mono-runner sûr, borne les pins gcRoot) ; (b) flag `autoDispose` sur l'Entry du
  registre → runners RL (`initRunner`/`initAndStart`/`buildPatchedRunner`) jamais auto-évincés par recorder
  (durcissement secondaire) ; (c) `rl_duel build --keep`.
- **validé** : `listRunners=[1,2]`, `decisionView(1)` ET `decisionView(2)` = ok/Running/10 units ;
  workflow end-to-end 2 runners via `--state-file` isolés, rosters distincts, zéro cross-talk.
- **leçon** : ne pas raisonner depuis un framing d'avant-compact — lire le code de TOUTE la chaîne (ici la
  policy explicite *dans le RPC*) avant d'incriminer une couche. (IDs de corrélation / `getQueueStats` =
  observabilité différée, **PAS** des blockers — coexistence prouvée sans eux.)

## TF07 — `oracle.build_card` crashe en console Windows (cp1252 vs ⚠ U+26A0) — done — recurrence:1
- **friction** : `build_card` rend ⚠ (effets critiques) → `print()` vers une console cp1252 lève
  `UnicodeEncodeError` → `rl_duel build` crashe APRÈS l'init du runner mais AVANT `_save_state` → état non
  sauvé → `view`/`status`/`play` derrière échouent (« pas d'état »). Invisible quand la console était déjà
  en UTF-8 (chance) ; apparu sur des matchups où le ⚠ se déclenche.
- **fix livré** : `sys.stdout/stderr.reconfigure(encoding="utf-8")` au boot de `rl_duel.py`.
- **vu** : validation TF06.

## TF08 — `play --spec` : `to` mal formé + no-op SILENCIEUX donne le tour gratis à l'IA — done — recurrence:2
- **friction** : dans `--spec`, un move attend `"to":[col,row]` (array). Les agents passent souvent
  `"to":"col,row"` (string) → `ac["to"][0]` indexe la string → `applyAction` lève côté Frida
  (`writeS32`) / renvoie `mutated=false`. PIRE : `cmd_play` enchaînait **quand même** `endturn` + tour IA
  → mon action ratée = **tour donné gratis à l'IA** (focus-kill de mes units). Diagnostiqué à tort par un
  agent comme « état hérité runner » (faux : `initAndStart`+`--keep` alloue toujours un runner NEUF au
  setup, launch.ts:494-546 ; transcript confirme `--state-file` utilisé partout).
- **fix livré** : (a) DOC — format exact `"to":[col,row]` (jamais `"c,r"`) explicité dans le prompt de
  combat (point 4) ET le docstring de `cmd_play` ; (b) GARDE anti-no-op — `cmd_play` valide `to` (array
  de 2 entiers, sinon erreur claire) et `_action_failed()` STOPPE le tour AVANT l'endturn ; (c) spec vide → stop.
  PAS de coercition multi-format (1 seul format canonique).
- **correctif v2 (faux positifs)** : la 1ʳᵉ version avortait sur `mutated=false` — FAUX signal. Vérifié dans
  internals.ts:438/545 : `mutated = (sig avant ≠ sig après)` où `sig = squadId:col,row:hp` par unité → c'est
  un **diff pos+hp**, PAS un flag de succès. Donc `mutated=false` est LÉGITIME et fréquent : `finish` (jamais
  de Δpos/hp → toujours false), abilities effet/buff/marque/différée (SeekerMissile fire au tour suivant) et
  attaques hors portée (non consommées). Résultat : ~10 faux « TOUR ABANDONNÉ ` ok=True mutated=False` » sur
  seed 96001 (l'agent a dû contourner via `act ability`). Critère CORRIGÉ : abort sur `ok=False`/`error` (tous
  kinds) ; un **move** n'échoue que s'il n'a AUCUN effet associé = `mutated=false` ET `eventCount==0` (un
  déplacement est dans `changes`/`mutated`, PAS dans `events` → un vrai move ⇒ mutated=True). `ability`/`finish`
  n'avortent QUE sur ok/error.
- **vu** : seeds 95000, 95002 (perdus sur le bug format) ; faux positifs garde v1 sur 96001 → corrigé v2.

## TF09 — `gameconfig.py` ne résout pas le NOM d'affichage + outil pas documenté dans le prompt — done — recurrence:1
- **friction** : un agent VERIF ne connaissait que le NOM « Actus » (vu en combat), pas la clé `admecManipulus`.
  `gameconfig.py --unit Actus` → `--unit` n'existait pas (flag inconnu → mode démo) ; `gameconfig.py Actus` →
  `card_unit` cherchait par CLÉ → « unit inconnue ». L'agent a alors plongé dans `data/gameconfig-units.json`
  (traits en IDs bruts) et **décodé les IDs de traits à la main** par recoupement → **~30 appels gâchés** pour
  une mécanique (le repair-engine d'Actus) que `gameconfig.py admecManipulus` sort en **1 appel** (kit complet,
  traits déjà décodés). Cause double : (1) pas de résolution par nom ; (2) outil **pas documenté dans le prompt**
  (ce n'est pas un MCP auto-documenté → l'agent tâtonne la syntaxe).
- **fix livré** : (a) `gameconfig.py` résout désormais un **nom d'affichage** (`Actus` → `admecManipulus`),
  ajoute le flag **`--unit <id|nom>`**, et **suggère les candidats** si la requête est ambiguë/inconnue
  (`resolve_unit_id` + `_match_units`) ; (b) **mode d'emploi `gameconfig.py` injecté dans les prompts** combat
  (recon) ET vérif via la constante `GC_HELP` du workflow (syntaxe exacte + « passe le NOM, l'outil résout ;
  NE fouille pas data/*.json à la main »).
- **vu** : vague test 97xxx (verif Actus).

## TF10 — `gameconfig.py` pas tolérant au MODE (mauvais flag → l'agent devine au hasard) — done — recurrence:2
- **friction** : un verif `TeleportStrike` (un TRAIT) a tapé `--ability TeleportStrike` → « inconnue » ; au lieu
  d'essayer `--trait`/`--effect` avec LE MÊME nom, il a **deviné ~25 unités au hasard** (SwoopingHawk, Jain Zar,
  Mephiston, Canis Rex, Grey Knight…) → vérif très longue. Même classe que TF09 (Actus) mais sur la CATÉGORIE :
  l'agent a le bon nom mais le mauvais flag, et ne pivote pas. `--effect TeleportStrike` (ou `--trait`) le sortait
  pourtant en 1 appel (« starts in Deep Strike… »).
- **fix livré** : (a) `gameconfig.py` **tolérant au mode** — `_auto_resolve()` : si `--ability/--trait/<unit>`
  ne trouve rien, il cherche le nom dans les AUTRES catégories (ability/trait/effet/unité) et renvoie la carte +
  la catégorie (`--ability TeleportStrike` → « pas une ability, c'est un TRAIT » + description) ; « introuvable »
  seulement si absent PARTOUT ; (b) `GC_HELP` (prompts) durci : « tolérant au mode, 1 appel suffit ; NE devine
  JAMAIS d'autres noms ; si introuvable partout = comportement HARNESS (verdict plausible + toolfeedback) ou
  mauvais nom → ARRÊTE ». → coupe le brute-force ET la mauvaise-route (vérifier le harness contre le jeu).
- **vu** : seed 97xxx (Actus, TF09) + 98003 (TeleportStrike).

## TF11 — verif en rabbit-hole sur un claim NUMÉRIQUE/scaling (gameconfig ne peut pas confirmer un nombre live) — done — recurrence:1
- **friction** : verif `SquigHound Grot summon "pumped"` (seed 98001) — le lookup a marché en **5 appels**
  (`orksRuntherd`→Snotflogga, `--ability SquigHound`→summon, `--trait Summon`→règle) PUIS **35 appels de
  rabbit-hole** dans `data/*.json` (gameconfig.json brut, tables de rareté, gameconfig-abilities/units.json)
  pour trouver POURQUOI le summon était « pumped » (scaling rareté/niveau). Cause = un claim **NUMÉRIQUE/
  émergent** que gameconfig (texte de RÈGLES) ne peut PAS corroborer proprement (la valeur live = niveau ×
  rareté × buffs). 3ᵉ cause de vérif-lente distincte de TF09 (nom) / TF10 (mode).
- **fix livré** : **prompt verif = règle STOP + budget** — portée = corroborer la RÈGLE DISCRÈTE (trigger/
  conditionnel/effet/qui-fait-quoi), PAS un nombre exact ; un claim numérique/scaling → verdict **plausible**
  (chiffre confirmé EN JEU, ne pas inscrire de nombre au wiki) ; **≤ ~5 appels gameconfig.py**, JAMAIS de
  spelunking `data/*.json` ; sinon conclure (plausible/contradicted) et ARRÊTER (nombre live / harness =
  plausible + toolfeedback, pas rabbit-hole).
- **piste combat (non livré)** : le champ `mechanics[].ability` devrait être un NOM canonique (clé ability/
  trait/effet), pas une phrase descriptive (« orksRuntherd SquigHound Grot summon (pumped) ») — mettre le
  qualificatif numérique/état dans `observation`. À ajouter au prompt combat.
- **vu** : seed 98001 (SquigHound summon « pumped »).

## TF12 — `applyAction` : Abraxas `MasterOfTheTutelaries` renvoie `ok=True` SANS summon ET SANS consommer l'action (no-summon non surfacé) — open — recurrence:2
- **friction** : caster `MasterOfTheTutelaries` (Abraxas, summon Pink Horror) via `act ability` renvoie **`ok=True,
  mutated=False`, SEULEMENT un event `User_UseAbility`, AUCUN `Ability_Summon`, AUCUN Pink Horror spawné, et l'action
  N'EST PAS consommée** (Abraxas reste « à activer »). L'agent croit avoir armé son moteur Psychic-snowball (Pink Horror
  → Screamers via dégât Psychic → WeaverOfFate MAX-dmg si 3+ cibles) alors qu'il n'a RIEN posé. Initialement
  hypothétisé comme un gate « zéro hex adjacent libre » (H37) — **RÉFUTÉ seed 70009** : reproduit avec **plusieurs hexes
  adjacents LIBRES confirmés** ((1,1)/(3,1)/(2,0) au cast (2,1)) → toujours no-summon. La règle gameconfig/i2 (« Summon a
  Pink Horror on a free hex adjacent to Abraxas ») est inconditionnelle au-delà du free-hex → un Pink Horror DEVRAIT
  spawn. Donc le no-summon est un **quirk de la pipeline applyAction** (le sous-système de summon de MasterOfTheTutelaries
  n'est pas déclenché), indépendant de l'occupation du board, ET l'échec n'est PAS surfacé au caller (`ok=True` trompeur,
  action non consommée) → tout le wincon Psychic-snowball secondaire d'Abraxas est **non-armable** via cet RPC.
- **amélioration** : (a) surfacer au caller quand un summon-action ne produit aucun `Ability_Summon`/spawn (flag
  `summonSpawned: false` ou erreur explicite) ; (b) root-cause côté hook : pourquoi le summon-subsystem de
  MasterOfTheTutelaries n'est pas appelé par applyAction (comparer à `Incursion`/`ResurrectionOrb`/`DeathFromAbove` qui
  spawnent correctement) ; (c) d'ici-là, doctrine combat = NE PAS dépenser l'action d'Abraxas sur MasterOfTheTutelaries
  (utiliser sa normale Psychic r2) — cf. H37 RÉFUTÉE.
- **vu** : seed 70002 (n=1, hypothétisé free-hex gate) + seed 70009 (n=2, free-hex confirmé → quirk tool/engine confirmé).

## TF13 — `abilities`/legality ne tient pas compte du spawn-tile requirement des summons — open — recurrence:1
- **friction** : `abilities`/`reason` listent un summon (ex. `ScarabHive`, Aleph-Null) comme castable
  now/+move, mais le cast réel échoue `TargetHasFreeAdjacentTile` (cluster sans hex libre adjacent où
  spawn) → l'agent BURNE le move de l'unité avant de découvrir l'illégalité (« TOUR ABANDONNÉ » a bien
  préservé les actions antérieures, mais le move était déjà consommé).
- **amélioration** : intégrer la contrainte free-adjacent-tile (spawn-tile) dans la requête de légalité des
  summons → un summon sans hex de spawn libre = ∉ now/+move (comme une cible hors portée). Apparenté à TF01
  (summons sur hex) et TF12 (summon no-op non surfacé).
- vu : seed 80072 (ScarabHive Aleph-Null).

## TF14 — header `view` « tour N » figé / pas un indicateur de round fiable — open — recurrence:6
- **friction** : l'en-tête `view` affiche « tour 4 » sur plusieurs rounds distincts (compteur =
  `GetAmountOfTurnsStartedByCurrentPlayer`, NON monotone / oscille — cf. note H58) → l'agent qui s'y fie
  mal-time son engagement anti-cap (⏱ horloge round-cap). Distinct de TF03 (POV) : ici c'est le COMPTEUR
  de tour, pas les labels MOI/ENNEMI. **n+1 (80097)** : A (« tour 3 » stale) ET B (« tour 4 » figé tout le
  combat) rapportent INDÉPENDAMMENT le compteur gelé → friction d'observabilité PARTAGÉE (convergence, pas
  divergence).
  **n+2 (seed 80000, ts=b7)** : A re-signale le header décision mislabellé « tour 3 » sur CHACUN de ses tours
  alors que `status` reporte turn=4 puis reset à turn=3 → le numéro de round affiché reste non-fiable pour
  juger la proximité du round-cap ; A a dû inférer le round depuis le jeu cumulatif. (convergence, pas divergence.)
  **n+3 (seed 80003, ts=b7)** : B re-signale le header `view` « tour 4 · joueur 4 » sur un tour où `status` reportait
  turn=4 PUIS turn=3 de façon incohérente entre appels → bruit de compteur de tour, non load-bearing mais re-confirme
  la non-fiabilité du label pour juger la proximité du cap.
  **n+4 (seed 80004, ts=b7)** : A re-signale le label « tour 3 » affiché à CHAQUE tour → confusion sur le round réel,
  ET un effet de bord aggravant : `ResurrectionOrb` (Anuphet, « 1 Necron Warrior par round DÉMARRÉ ») n'a summoné
  qu'**1** Warrior là où A attendait plus, parce que le « tour 3 » affiché ≠ l'index de round interne (cf. wiki §3ter
  Necron Warrior « scaling sur l'INDEX de round interne, PAS le tour affiché ») → A a soupçonné un bug summon alors
  que c'était le label de round non-fiable qui faussait son attente. (convergence avec H58 — compteur per-player.)
  **n+5 (seed 80001, ts=b7)** : A re-signale le header `view` « tour 3 » statique sur de NOMBREUX tours alors que
  `status` reportait turn=4 puis incrémentant → le compteur de round dans le header de la carte ne tracke pas, rendant
  la proximité du round-cap illisible depuis la vue seule (A a dû cross-checker `status`). (convergence, pas divergence.)
- **amélioration** : afficher le **round-state autoritatif** (`TotalTurnsFinished` / round courant) dans
  l'en-tête, pas le compteur per-player oscillant ; doctrine = lire le round-state, pas le label.
- vu : seed 80072, seed 80097, seed 80000, seed 80003, seed 80001.

## TF18 — `play`/`play --spec` : id de l'attaque NORMALE NON-universel (id 69 ≠ toutes les units) + le DÉFAUT résout vers l'ACTIVE → cast illégal → « TOUR ABANDONNÉ » — open — recurrence:2
- **friction** : l'attaque normale d'une unité est un `ActiveAbilityType` CONCRET par-unité (ex. Exitor-Rho =
  `OptimizedGait` id 1123, Loki = `Loki_NormalAttack` id 69) — **id 69 n'est PAS universel**. Un agent qui specke
  la normale d'un multi-unit turn avec id 69 (ou 1013) sur une unité dont la normale est 1123 → cast illégal →
  `cmd_play` ABANDONNE le tour (« TOUR ABANDONNÉ »), perdant le reste du spec. seed 80000 (ts=b7) : A a subi
  DEUX cycles de retry (id 69 puis 1013) avant de trouver 1123 pour Exitor-Rho. Apparenté à la mémoire
  « Normal attack = concrete ability id » (lire `ActiveAbilityComponent.NormalAttackType@0x28`).
  **n+1 (seed 80004, ts=b7)** : variante du DÉFAUT — `rl_duel play` SANS `ability` explicite pour une unité
  qui a un actif résout vers l'**ABILITY ACTIVE** (Shiron a défaulté à `ExcruciatingFrequencies` id 1197) → une
  attaque normale planifiée est rejetée (`TargetIsInRange`/`ValidRequest`) ; A a dû passer `ability:69`
  (`Loki_NormalAttack`) explicite pour la normale. Le défaut devrait résoudre vers l'attaque IN-RANGE que les
  PLANS montrent (ou au moins warn), pas vers l'actif.
- **amélioration** : (a) doctrine combat — **toujours `abilities --unit <id>` pour récupérer l'id exact de la
  normale par-unité AVANT de specker un multi-unit turn** (ne jamais supposer id 69) + **toujours passer `--ability`
  explicite** (ne pas se fier au défaut, qui résout vers l'actif) ; (b) idéalement, `play --spec`
  résout `{"kind":"normal","unit":N}` (sans id explicite) en lisant `NormalAttackType` de l'unité côté outil →
  supprime la classe d'erreur ; le DÉFAUT de `play` devrait viser la normale/l'attaque-en-range des PLANS, pas
  l'actif. Apparenté à TF08 (no-op silencieux qui abandonne le tour).
- vu : seed 80000, seed 80004.

## TF19 — `await` / RPC timeout transitoires pendant le pump Unity de l'adversaire (curl exit-28 -m 100 ; host « RPC timeout 15000ms » ; status urllib TimeoutError) — open — recurrence:5
- **friction** : pendant qu'un agent adverse délibère / pendant un long `applyAction`+pump Unity, l'endpoint
  `await` (et parfois `status`) dépasse le cap `-m 100` de curl (exit 28) OU le host lève « RPC timeout after
  15000ms ». seed 80000 (ts=b7) : A a touché le cap plusieurs fois (re-émissions en aveugle requises, incertitude
  sur « est-ce mon tour ? ») ; B a vu curl exit-28 + un host-side RPC-timeout 15000ms + un status urllib
  TimeoutError mid-pump. Transitoire (re-émettre l'`await` récupère à chaque fois) mais bruyant + latence. ⚠
  **`sleep` foreground BLOQUÉ dans cet environnement** → impossible de temporiser ; B a dû lire le fichier de
  sortie d'un `play` backgroundé directement au lieu de dormir.
  **n+1 (seed 80003, ts=b7)** : A re-signale `/await` timedOut fréquent sur les tours adverses + curl exit-28 (full-
  timeout hangup) → ré-émissions multiples. B re-signale `await` timedOut + un raw « RPC timeout after 30000ms » ⚠
  **easy to misread as a real failure** (la forme raw-error vs `timedOut` est ambiguë), ET un `applyAction` (urllib
  TimeoutError) sur la 1ʳᵉ attaque d'Aleph-Null **qui avait pourtant DÉJÀ appliqué** → B a dû vérifier `status` pour
  éviter un double-apply. Le CLI devrait surfacer un signal clair « applied-but-slow » vs un vrai échec.
- **amélioration** : (a) `await` long-poll plus robuste (re-tente côté outil sur timeout transitoire au lieu de
  remonter exit-28 au caller) OU un endpoint « est-ce mon tour ? » bon-marché non bloquant ; (b) documenter le
  pattern « pas de sleep → lire le task-output file d'un background `play` » dans le prompt combat ; (c) **distinguer
  un `applyAction` applied-but-slow d'un vrai échec** (idempotence / flag `alreadyApplied` au retry) pour éviter le
  double-apply ; (d) uniformiser la forme de l'erreur de timeout (jamais une raw-error qui se lit comme un fail).
  Friction d'observabilité, PAS de correctness (aucune action perdue).
  **n+2 (seed 80004, ts=b7)** : friction PARTAGÉE, mineure ce match. A : un `await` curl a retourné une sortie VIDE
  (le wrapper 100s a timeout AVANT que le timeout serveur 90s ne retourne) → a dû re-émettre. B : un `await` curl a
  touché le cap `-m 100` (exit 28) avant le timeout serveur 90s → harmless, re-émis. Convergent (A+B) — re-confirme
  le pattern transitoire ; aucune action perdue.
  **n+3 (seed 80002, ts=b7)** : friction PARTAGÉE, plus AIGUË ce match (tours adverses multi-units longs). A : un
  `await` a touché un hard server-timeout (exit 28) + une fois un raw `RPC timeout after 45000ms` ; les tours
  adverses dépassaient RÉGULIÈREMENT la fenêtre 90s → **4-6 re-awaits par cycle**. B : `RPC timeout (15000ms)` + curl
  exit-28 répétés (a dû passer `-m 120` côté client) ET un `play --no-ai --end` (deep-strike d'Arjac) a renvoyé un
  **urllib TimeoutError sur la RÉPONSE alors que l'endturn AVAIT appliqué** (handoff effectué — vérifié via `view`).
  Re-confirme le besoin (a) re-try transitoire côté outil et (c) distinguer applied-but-slow d'un vrai échec
  (idempotence) — l'`endturn` applied-mais-réponse-timeout est exactement le cas dangereux (risque de re-jouer).
  **n+4 (seed 80001, ts=b7)** : A re-signale un `curl await` exit 28 (le client `-m 100` race le timeout serveur 90s)
  → harmless, re-émis. Re-confirme le pattern transitoire ; aucune action perdue.
- vu : seed 80000, seed 80003, seed 80004, seed 80002, seed 80001.

## TF20 — collision de glyph board-map : 'b' minuscule = terrain (drybush) ET lettre d'unité (rendu en double sur une rangée) — open — recurrence:2
- **friction** : l'ASCII map réutilise 'b' minuscule pour À LA FOIS un terrain (drybush) ET la lettre d'une
  unité → glyphe ambigu/dupliqué sur une rangée, mis-lecture de position possible. seed 80000-roundcap (B) :
  'b' drybush mis-lu comme le Tyrant Guard → charge fantôme stranded (cf. H60). **n+1 (seed 80000 ts=b7)** : A
  signale Pestillian rendu 'b' DEUX FOIS sur une rangée (artefact d'affichage / echo d'aura) → a dû cross-checker
  les positions réelles via `status` pour ne pas mis-lire les positions ennemies.
- **amélioration** : réserver les minuscules au terrain et les MAJUSCULES (ou un set disjoint) aux unités, OU
  dé-dupliquer le rendu d'unité par rangée ; doctrine d'ici-là = cross-check les positions via `status` (ground
  truth), jamais l'ASCII map seule quand les lettres collisionnent. (cf. hypotheses.md H60, même symptôme côté
  renderer.)
- vu : seed 80000-roundcap, seed 80000-b7.

## TF15 — `act` (single-action) N'APPENDAIT PAS au action_log → trajectoire IL perdue — done — recurrence:2
- **friction** (CRITIQUE dataset) : `cmd_act` exécutait l'action (`applyAction`) mais — contrairement à
  `cmd_play` (l.853/884) — ne l'appendait PAS au `action_log` ni ne `_save_state`. Un player qui joue tout
  ou partie de son tour via `act` (le fallback pris quand `play --spec` le gêne, typiquement après le POV-flip
  TF03) voit ses actions s'exécuter (le runner mute, il peut GAGNER) mais **ABSENTES du dataset**. seed 80031
  b6 : team2 (VAINQUEUR) joué ~100% en `act` → archive `team2=0 action` (démo du vainqueur perdue). seed 80053
  b5 : team1 (vainqueur) 6 actions = capture PARTIELLE. Découvert en auditant les comptes d'actions par side.
- **fix livré** : `cmd_act` logge désormais l'action RÉUSSIE (même critère `_action_failed` que cmd_play) +
  `_save_state` par-action ; `act endturn` append le marqueur. Symétrie complète play↔act → capture quel que
  soit le chemin.
- **résiduel** : 80031 b6 (team2) + 80053 b5 (team1) sont DÉJÀ perdus (jamais loggés, state-files supprimés)
  → irrécupérables tels quels mais **re-runnables via le seed** (build déterministe → démo complète neuve).
  Corrélé à TF03 (le POV-flip pousse vers `act`) → fixer TF03 réduit la fréquence du fallback.
- vu : seed 80031 (b6, vainqueur vide), seed 80053 (b5, partiel).

## TF16 — contrainte de POSITIONNEMENT d'une ability/attaque non surfacée → no-op silencieux (mutated=false) — open — recurrence:4
- **friction** : plusieurs actifs/attaques ont une contrainte de positionnement que le PLAN ne montre pas, et
  un cast/attaque hors-contrainte **no-op silencieusement** (`mutated=false`, action NON consommée, activation
  gaspillée) au lieu d'auto-résoudre le move : (a) **adjacence requise** — une attaque ne s'auto-move PAS en
  range : tuile non-adjacente choisie → no-op (80031 : Tarvakh visé 2× sur (2,5) non-adjacent à Kariyan (3,4)
  → stranded) ; (b) **ligne à DIRECTION FIXE** — `RadBombardment` (Vitruvius) frappe une ligne 6-dir : `--target`
  hors-axe = no-op, il faut `--to` un hex qui aligne (80085) ; (c) **actif qui a besoin de SON propre budget de
  move** — `VigilanceEternal` (Tyrith) gap-close avec son move interne : pré-bouger Tyrith consomme le move →
  actif no-op « sans bouger / TargetIsInRange » (80020).
  **n+1 (seed 80003, ts=b7)** : DEUX variantes du même symptôme. (i) **summon +move hors-range** — A a déplacé
  Bellator à (4,4) pour un `DeathFromAbove` sur Aleph-Null, mais le summon était illégal de là (`TargetIsInRange`)
  → le move était DÉJÀ dépensé = activation gaspillée (apparenté à (c) : vérifier la range de l'actif +move depuis
  la tuile COURANTE avant de committer le move). (ii) **attaque NORMALE de summon hors-portée non rejetée** — A a
  auto-résolu 2 normales Inceptor (id 69) sur Nicodemus à **0 dmg** (mauvaise tuile/range), action consommée, no-op
  SILENCIEUX : contrairement aux casts ciblés, l'attaque hors-portée des units summon n'est PAS rejetée pré-endturn.
  (iii) B : `Incursion` (Archimatos) rejeté `out-of-range` APRÈS un move réussi (cf. TF21 pour le turn-flip associé).
- **amélioration** : surfacer la contrainte dans `abilities`/`reason` (adjacence requise / axe de ligne / move-
  interne / range du +move depuis la tuile courante) et faire ÉCHOUER explicitement (raison structurée) au lieu du
  no-op silencieux — **y compris pour les attaques normales des summons hors-portée** (mêmes garde-fous que les
  casts ciblés). Doctrine d'ici-là : confirmer la tuile/cible EXACTE via `moves`/`abilities` AVANT de committer
  (apparenté TF13 spawn-tile, TF08/TF18 no-op normale, TF21 turn-flip sur cast rejeté).
- vu : seed 80031 (adjacence), seed 80085 (ligne fixe), seed 80020 (move-interne), seed 80003 (summon +move / normale summon hors-portée).

## TF17 — moves de repositionnement (non-attaquants) semblent REVERT au turn-flip en self-play — open — recurrence:1
- **friction** (candidat, single-observer) : B (80097) rapporte que les units qui font un move PUR (sans
  attaque) snap back à leur position au turn-flip (Anuphet/Morvenn/Yarrick) — seules les units ayant ATTAQUÉ
  gardent leur avance → le positionnement défensif délibéré est inefficace. A ne cross-observe pas. Non tranché :
  artefact de la pipeline state-file self-play OU règle réelle du jeu (un move sans attaque est-il « committé » ?).
- **amélioration** : reproduire en replay déterministe (seed 80097) et lire la position post-flip vs in-turn ;
  si artefact tool → fixer la persistance du move dans le state-file self-play. cf. hypotheses.md H74 (même candidat).
- vu : seed 80097.

## TF21 — un ABILITY cast rejeté (out-of-range) APRÈS un MOVE réussi FLIPPE le tour à l'adversaire — le label « TOUR ABANDONNÉ — endturn NON joué » CONTREDIT le state observé (currentPlayer bascule) — open — recurrence:1
- **friction** : sur le tour de B (team2, seed 80003), Archimatos a fait un `move` vers (6,6) RÉUSSI puis un cast
  `Incursion` rejeté `out-of-range`. Résultat observé : le tour a **FLIPPÉ à l'adversaire** (currentPlayer est passé
  à 3, l'opposant a commencé à jouer) ET Archimatos est resté avec **SEULEMENT son move, sans attaque** — alors que
  le message rendu disait « **TOUR ABANDONNÉ — endturn NON joué** ». Le label contredit directement le state (le tour
  a bien été cédé). Attendu : un cast rejeté devrait **laisser l'activation de l'unité disponible pour retry** (move
  déjà consommé, mais l'unité peut encore tenter un autre cast/cible), PAS flipper le tour. La combinaison
  move-réussi + cast-rejeté + label-trompeur = un tour gaspillé en silence (apparenté TF08 « no-op rend le tour gratis
  à l'IA », mais ici via `act ability` single-action, pas `--spec`, et avec un label EXPLICITEMENT faux).
- **amélioration** : (a) un cast rejeté (out-of-range/illégal) NE DOIT PAS déclencher l'endturn/turn-flip — préserver
  l'activation de l'unité (move déjà spent) pour un retry ; (b) corriger le label « endturn NON joué » pour qu'il
  REFLÈTE l'état réel (si le tour a flippé, ne pas afficher « non joué ») ; (c) surfacer la raison structurée du rejet
  (out-of-range) AVANT que le move soit committé (apparenté TF16 contrainte de positionnement / TF13 spawn-tile pour
  les summons). Distinct de TF03 (POV-flip d'affichage) : ici le tour est RÉELLEMENT cédé sur un cast rejeté.
- vu : seed 80003.

## TF22 — `play --no-ai` FAUX-REJET non-déterministe d'un cast à effet SPÉCIAL/DIFFÉRÉ (Foehammer) que `abilities` listait légal-now — `ValidRequest`/`TargetIsInRange` — open — recurrence:1
- **friction** : sur le tour de B (team2, seed 80002), `play --no-ai` a **REJETÉ** (`ok=False`, raison
  `ValidRequest` / `TargetIsInRange`) le cast `Foehammer` (Arjac — Stun à effet différé/spécial) **alors que la
  requête `abilities` listait la cible comme légale-MAINTENANT**. Non-déterministe : a MARCHÉ une fois (sur Bellator)
  puis ÉCHOUÉ deux fois (sur Njal puis Wrask) le même match. C'est un FAUX-REJET (le cast était légal, le harness l'a
  refusé), DISTINCT de TF08-v2 (qui corrigeait l'INVERSE : un faux-ABORT sur un `mutated=false` LÉGITIME). Même CLASSE
  symptomatique que le guard SeekerMissile `mutated=False` (effets purement différés mal gérés par la garde anti-no-op),
  mais ici le résultat est un REJET dur, pas un no-op silencieux → le Stun voulu n'a pas pu être posé de façon fiable
  (B a dû planifier SANS le stun comme dépendance dure, ou retomber sur `act ability` standalone).
- **amélioration** : (a) aligner la garde de `play --no-ai` sur la légalité que `abilities` retourne — si `abilities`
  dit légal-now, ne PAS rejeter sur `ValidRequest`/`TargetIsInRange` (réconcilier les deux chemins de validation pour
  les abilities à effet différé/spécial : Foehammer-Stun, SeekerMissile-mark, casts deferred) ; (b) si un rejet est
  légitime, surfacer la VRAIE raison structurée (pourquoi `abilities` et `play` divergent) ; (c) workaround d'ici-là =
  `act ability` standalone pour les casts à effet différé/spécial (ne pas en faire une dépendance dure du plan).
  Apparenté TF16 (no-op silencieux) / TF21 (cast rejeté flippe le tour) — ici c'est un REJET DUR non-déterministe d'un
  cast pourtant légal.
- vu : seed 80002.

## TF23 — `rl_duel guard --climb` (move-guard 2-ply) trop LENT (sims Unity-pump lourdes) → timeout effectif sur la décision du tour → l'agent décide SANS le guard — open — recurrence:1
- **friction** : le move-guard (`rl_duel guard --climb`, sims 2-ply avec pump Unity) a tourné **très lentement en
  background** sur le tour 2 de A (team1, seed 80002) et a **effectivement timeout pour sa décision** → A a dû décider
  SANS le guard (doctrine de repli : défaut conservateur quand le guard est down). ⚠ COÛT RÉEL ce match : le guard
  flaggait baseline-hold à NET −4.24 (signal « le commit forward sera puni ») — mais comme il n'a pas rendu à temps,
  A a over-committé Bellator forward et l'a perdu (proximate mistake du match). Un guard qui n'arrive pas avant la
  décision = pas de garde-fou au moment critique.
- **amélioration** : (a) un mode guard RAPIDE/heuristique (1-ply ou éval statique de position) qui rend en <quelques s
  pour donner AU MOINS un signal de danger avant la décision, le 2-ply full restant optionnel ; (b) budget-temps
  explicite + retour PARTIEL si le climb dépasse (« voici le meilleur coup trouvé jusqu'ici + le NET du baseline-hold »)
  plutôt qu'un silence ; (c) surfacer le NET du baseline-hold EN PREMIER (cheap) — c'est le signal le plus actionnable
  (« hold est-il NET négatif ? ») et il n'exige pas le climb complet. Doctrine d'ici-là : si le guard ne rend pas,
  défaut conservateur = NE PAS over-committer un engine/carry forward (garder shallow).
- vu : seed 80002.

## TF24 — état de COOLDOWN d'une ability non surfacé : `[indispo]` (vue MES ACTIFS) STALE/trompeur + pas de `RemainingCooldownTurns` + `reason` renvoie `ValidRequest` même cooldown-locked → il faut TENTER un cast réel pour savoir — open — recurrence:1
- **friction** : sur `BasiliskBarrage` (Thaddeus MoW, cooldown MULTI-tour, ≠ recharge 1-tour), les 3 sources de
  légalité DIVERGENT et AUCUNE ne donne le cooldown restant. **A (team1, seed 80001)** : la vue « MES ACTIFS »
  affichait `BasiliskBarrage [indispo]` pendant 2 tours alors que les outils `abilities`/`reason` le reportaient
  CASTABLE (`[manual]`, `ValidRequest`) le MÊME tour → A a tenu passivement (mis-lu le flag `[indispo]` comme un
  hard cooldown) et perdu du tempo de chip. **B (team2, seed 80001)** : symptôme MIROIR — `BasiliskBarrage`
  `indispo`/{NOT-usable} dans la vue ne surface AUCUN compteur de cooldown-turns, ET `reason --caster --ability`
  renvoie `ValidRequest` (ciblage SEULEMENT) même quand l'ability est cooldown-locked → B a dû TENTER un cast réel
  pour découvrir que c'était un cooldown multi-tour (la barrage était indispo ~3 tours consécutifs après un tir).
  Friction d'observabilité PARTAGÉE (A+B, convergente) : ni la vue ni `reason` ne disent « combien de tours avant
  dispo » — le `[indispo]` de la vue ET le `ValidRequest` de `reason` sont tous deux NON-fiables pour le cooldown.
  Distinct de TF22 (FAUX-REJET dur non-déterministe d'un cast légal) : ici la légalité-targeting est correcte mais
  le COOLDOWN n'est exposé nulle part, et le flag `[indispo]` de la vue ne corrèle pas avec la dispo réelle.
- **amélioration** : (a) afficher `RemainingCooldownTurns=N` dans la ligne « MES ACTIFS » de la vue (et dans
  `abilities`) → planifier autour du downtime barrage sans deviner ; (b) réconcilier les 3 chemins (vue `[indispo]`,
  `abilities`, `reason`) sur un MÊME verdict de disponibilité incluant le cooldown ; `reason` ne devrait PAS rendre
  `ValidRequest` (ciblage) quand l'ability est cooldown-locked — surfacer le cooldown comme cause d'indispo.
  Doctrine d'ici-là : ne PAS se fier au flag `[indispo]` de la vue seul (peut être STALE = ability en fait castable,
  cas A) NI au `ValidRequest` de `reason` seul (ciblage-only, ignore le cooldown, cas B) → confirmer la dispo réelle
  d'une ability cooldown via les DEUX, et si ambigu, tenter le cast (no-op/rejet propre si indispo).
- vu : seed 80001.
