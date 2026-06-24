# Backlog outillage (friction & manques signalés par les agents)

Append-only. Tout agent qui bute sur un outil **manquant** ou **améliorable** le signale ici —
jamais de contournement silencieux. `statut` : open|wip|done. `recurrence` = nb de matchs gênés
(prioriser les ≥2). Canal symétrique des hypothèses : `toolfeedback → outillage`.

---

## TF01 — `play --spec` ne gère pas les abilities sur HEX ni les actifs MoW — open — recurrence:2
- **friction** : `--spec` ne couvre que `move` / `ability(target)` / `finish`. Les summons sur hex
  libre (`Incursion --to`, `ResurrectionOrb`, `DeathFromAbove`, `MasterOfTheTutelaries`), le marquage
  MoW (`MalleusRocketLauncher`, `MacroPlasmaIncinerator`) et les self-buffs (`WarHowl`) sortent du flux
  1-appel/round → on retombe en `act ability` un-par-un (coûteux en round-trips).
- **amélioration** : étendre le spec → `{"kind":"ability","caster":N,"to":[c,r],"ability":A}` (hex) et
  `{"kind":"ability","caster":N,"ability":A}` (self) ; + un `{"kind":"mow",...}`. Idéalement un round
  entier (mes actions hétérogènes) en 1 appel.
- vu : G02, G03.

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

## TF04 — Plans = dmg MAX-roll NON mitigé + label `K!` optimiste (ignore Resilient + réductions + buffs défensifs) — open — recurrence:4
- **friction** : `K!` (« kill sûr ») ne modélise pas Resilient/Terrifying/block → un coup « K! » laisse
  la cible à 1 PV (Azkor). **n+1 (80072)** : au-delà du label, la RANGE dmg des plans est un **MAX-roll NON
  mitigé** — `Doombolt [2409-3613]` a dealt **1343** réel (mitigé par le −50% d'Aun'Shi + block) → l'agent
  a failli mis-committer sur un « kill » fantôme. Induit en erreur sur la létalité ET sur l'output réel.
  **n+2 (80020)** : Dreir LeadingTheCharge prédit gros mais ~821 net sur l'anvil 12k Snotflogga (SupaCyborkBody
  + BeastSnagga block) → charge gaspillée. **n+3 (80085)** : Aesoth normale sur Lucien `[1359-1359 K!]` mais
  SINGLE-HIT floor-à-1 sur un Resilient → ne tue PAS (label `K!` trompeur).
- **amélioration** : surfacer le **dmg attendu post-mitigation** (la `DamagePrediction` du jeu existe déjà
  côté caches AI) OU au minimum **tagger la range comme MAX non-mitigé** + une **kill-proba** ; intégrer
  Resilient/Terrifying/Daemon-block dans la prédiction (dégrader `K!`→`K?` si trait défensif non modélisé).
- vu : G01, seed 80072, seed 80020, seed 80085.

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

## TF14 — header `view` « tour N » figé / pas un indicateur de round fiable — open — recurrence:2
- **friction** : l'en-tête `view` affiche « tour 4 » sur plusieurs rounds distincts (compteur =
  `GetAmountOfTurnsStartedByCurrentPlayer`, NON monotone / oscille — cf. note H58) → l'agent qui s'y fie
  mal-time son engagement anti-cap (⏱ horloge round-cap). Distinct de TF03 (POV) : ici c'est le COMPTEUR
  de tour, pas les labels MOI/ENNEMI. **n+1 (80097)** : A (« tour 3 » stale) ET B (« tour 4 » figé tout le
  combat) rapportent INDÉPENDAMMENT le compteur gelé → friction d'observabilité PARTAGÉE (convergence, pas
  divergence).
- **amélioration** : afficher le **round-state autoritatif** (`TotalTurnsFinished` / round courant) dans
  l'en-tête, pas le compteur per-player oscillant ; doctrine = lire le round-state, pas le label.
- vu : seed 80072, seed 80097.

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

## TF16 — contrainte de POSITIONNEMENT d'une ability/attaque non surfacée → no-op silencieux (mutated=false) — open — recurrence:3
- **friction** : plusieurs actifs/attaques ont une contrainte de positionnement que le PLAN ne montre pas, et
  un cast/attaque hors-contrainte **no-op silencieusement** (`mutated=false`, action NON consommée, activation
  gaspillée) au lieu d'auto-résoudre le move : (a) **adjacence requise** — une attaque ne s'auto-move PAS en
  range : tuile non-adjacente choisie → no-op (80031 : Tarvakh visé 2× sur (2,5) non-adjacent à Kariyan (3,4)
  → stranded) ; (b) **ligne à DIRECTION FIXE** — `RadBombardment` (Vitruvius) frappe une ligne 6-dir : `--target`
  hors-axe = no-op, il faut `--to` un hex qui aligne (80085) ; (c) **actif qui a besoin de SON propre budget de
  move** — `VigilanceEternal` (Tyrith) gap-close avec son move interne : pré-bouger Tyrith consomme le move →
  actif no-op « sans bouger / TargetIsInRange » (80020).
- **amélioration** : surfacer la contrainte dans `abilities`/`reason` (adjacence requise / axe de ligne / move-
  interne) et faire ÉCHOUER explicitement (raison structurée) au lieu du no-op silencieux. Doctrine d'ici-là :
  confirmer la tuile/cible EXACTE via `moves`/`abilities` AVANT de committer (apparenté TF13 spawn-tile, TF08 no-op).
- vu : seed 80031 (adjacence), seed 80085 (ligne fixe), seed 80020 (move-interne).

## TF17 — moves de repositionnement (non-attaquants) semblent REVERT au turn-flip en self-play — open — recurrence:1
- **friction** (candidat, single-observer) : B (80097) rapporte que les units qui font un move PUR (sans
  attaque) snap back à leur position au turn-flip (Anuphet/Morvenn/Yarrick) — seules les units ayant ATTAQUÉ
  gardent leur avance → le positionnement défensif délibéré est inefficace. A ne cross-observe pas. Non tranché :
  artefact de la pipeline state-file self-play OU règle réelle du jeu (un move sans attaque est-il « committé » ?).
- **amélioration** : reproduire en replay déterministe (seed 80097) et lire la position post-flip vs in-turn ;
  si artefact tool → fixer la persistance du move dans le state-file self-play. cf. hypotheses.md H74 (même candidat).
- vu : seed 80097.
