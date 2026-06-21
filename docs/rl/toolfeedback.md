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

## TF03 — `decisionView` bascule de POV (MOI/ENNEMI) quand currentPlayer=4 — open — recurrence:1
- **friction** : quand mon tour s'auto-termine et que la vue passe en POV team-2, les labels MOI/ENNEMI
  s'inversent → re-lectures inutiles, confusion sur les positions.
- **amélioration** : option `view --pov me` (toujours mon équipe = MOI), ou afficher teamId explicite.
- vu : G01.

## TF04 — Label `K!` des plans optimiste (ignore Resilient + réductions défensives) — open — recurrence:1
- **friction** : `K!` (« kill sûr ») ne modélise pas Resilient/Terrifying/block → un coup « K! » laisse
  la cible à 1 PV (Azkor). Induit en erreur sur la létalité.
- **amélioration** : intégrer Resilient/Terrifying/Daemon-block dans la prédiction, ou dégrader le label
  en `K?` quand la cible a un trait défensif non modélisé.
- vu : G01.

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
