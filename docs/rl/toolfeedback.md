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

## TF02 — Pas de détecteur « match décidé » pour l'abandon — done — recurrence:3
- **friction** : décider gagné/perdu d'avance se fait à la main (compter HP/unités/win-condition) à
  chaque tour. Sujet à erreur (j'ai sur-estimé 2× « je gagne »).
- **amélioration** : helper `rl_duel.py verdict` → renvoie un score de position (matériel + reach sur la
  win-condition adverse + léthal estimé) + un flag `decided: won|lost|undecided` (prudence asymétrique).
- **fix livré** : commande `rl_duel.py verdict` — matériel par équipe (HP + nb d'unités), létalité estimée CE TOUR
  (cibles K! distinctes des plans), score de position [-1..+1] (60% HP + 40% unités), flag `decided:
  won|lost|undecided` à PRUDENCE ASYMÉTRIQUE (`won` SEULEMENT à élimination adverse — contre la sur-estimation ;
  `lost` peut s'avancer en early-warning si nettement derrière ; sinon `undecided` + score). `battleStatus`
  autoritatif si match fini. Validé live (5v5 frais → `undecided · score=-0.02 · léthal=0`). RÉSIDUEL : la « reach
  sur la win-condition adverse » n'est pas modélisée (mécanique non exposée simplement) — matériel + léthal-ce-tour
  couvre le cœur du besoin (éviter le mis-juge d'abandon).
- vu : G01, G02, G03.

## TF03 — `decisionView` bascule de POV (MOI/ENNEMI) quand currentPlayer=4 — done — recurrence:4
- **friction** : quand mon tour s'auto-termine et que la vue passe en POV team-2, les labels MOI/ENNEMI
  s'inversent → re-lectures inutiles, confusion sur les positions. **n+1 (80072)** : B re-confirme le flip,
  ET le `decisionView` du state-file LAG le turn-flip → l'attribution d'équipe est ambiguë sur le tour de
  bascule ; désambiguïser via `status` (autoritatif t1/t2), pas les labels relatifs de la vue.
  **n+2 (80031)** : B a failli mis-play — la 1ʳᵉ vue de son tour labellait « MOI » le set u95-103 (= team1) ;
  caught en dérivant le vrai roster via `myTeam`/`playerUnits`, mais c'est le foot-gun récurrent.
  **n+3 (seed 80053, ts=b8)** : B (team2) re-confirme — la 1ʳᵉ `view` qu'il a vue (sur le tour adverse)
  labellait les Blood Angels (= team1) comme `<MOI>`/MAJUSCULE, l'INVERSE de son vrai roster ; a dû réconcilier
  via la liste « À ACTIVER » (= ses vraies units) sur SON tour. Pas de mis-play, mais le label s'inverse entre
  tours et se lit mal. (convergence avec les n précédents — friction d'observabilité récurrente.)
- **amélioration** : option `view --pov me` (toujours mon équipe = MOI), ou afficher teamId explicite.
- **fix livré** : `build_card` accepte `pov_team` (= ma team STABLE lue dans le state-file) → labels MOI/ENNEMI
  par team ABSOLUE (ne flippent plus au POV-switch ; `_is_mine = team==pov_team`) + bannière `⚠ POV ADVERSAIRE`
  explicite quand c'est le tour adverse (rappelle que les PLANS/ACTIFS affichés sont les SIENS). Câblé dans
  `view` (cmd_view) et la carte post-round de `play`. Validé live (header `joueur 3 (team 1)`, labels stables).
- vu : G01, seed 80072, seed 80031, seed 80053.

## TF04 — Plans = dmg MAX-roll NON mitigé + label `K!` optimiste (ignore Resilient + réductions + buffs défensifs) — done — recurrence:8
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
  **n+6 (seed 81001, ts=b9 — FLAVEUR NOUVELLE : attaquant SUMMONED)** : B rapporte que le K! des plans pour les
  unités **SUMMONED** est optimiste — le plan d'attaque d'un Skitarii Vanguard sur un Neophyte (2992 PV) affichait
  `[2992 K!]` mais l'attaque a dealt **2475** (Neophyte laissé à 517) → mis-séquençage d'un kill. ⚠ DISTINCT du
  résiduel reduction-trigger (`↓`) déjà fixé : ici PAS de trait défensif non-modélisé sur la cible — le delta vient
  vraisemblablement du fait que la prédiction **sur-évalue l'OUTPUT de l'attaquant summon** (stats/dmg du Vanguard pas
  pleinement résolues à l'instant de la projection). Doctrine d'ici-là : NE PAS truster les labels K! des plans
  IMPLIQUANT un attaquant summon (Vanguard/Neophyte/decoy-spawn) — vérifier la cascade réelle avant de compter le kill.
  **n+7 (seed 81000, ts=b9 — go/no-go FATAL sur un SELF-HEALER)** : A (team1) rapporte que la prédiction
  `decisionView` sur Incisus (Apothecary) annonçait gros mais l'attaque n'a **chunké qu'à 518** (puis Incisus s'est
  full-heal le tour suivant) — `↓` tags pervasifs, min-max non trustable pour un GO/NO-GO. La sur-estimation a
  DIRECTEMENT causé le coup perdant : A a committé sa carry (Snappa, BigTarget) + Makhotep forward pour un kill
  d'engine **non-garanti** (cru `K?`/gros, réel = chunk) → Incisus a survécu+heal et A a perdu les 2 corps pour zéro
  net. Leçon : un `↓`/range optimiste sur un SELF-HEALER (Apothecary/Drachnyen-class) = **traiter le kill comme
  NON-garanti et ne PAS committer** (doctrine « kill CE tour ou ne pas committer » dépend d'une prédiction qu'on ne
  peut justement pas truster ici → exiger un floor de dmg multi-source au lieu de la prédiction).
- **amélioration** : surfacer le **dmg attendu post-mitigation** (la `DamagePrediction` du jeu existe déjà
  côté caches AI) OU au minimum **tagger la range comme MAX non-mitigé** + une **kill-proba** ; intégrer
  Resilient/Terrifying/Daemon-block/**TerminatorArmour 1ʳᵉ-hit** dans la prédiction (dégrader `K!`→`K?` si trait
  défensif non modélisé).
- **fix livré** : (re-vérifié contre le code) le claim « MAX-roll NON mitigé » est **RÉFUTÉ** — la range des
  plans EST DÉJÀ la prédiction MITIGÉE du moteur (`AccurateHealthDamage.Min/Max` @0x60/0x64, post armure + caps +
  `ApplyTraitDamageLimitsToDamage` Resilient/Impervious ; projection.ts:181-184), pas un max-roll brut.
  `kill`/`killSure` lisent les seuils EFFECTIFS `get_WillBeKill`/`get_MightBeKill` (@0x24/0x28, post floor-Resilient
  + overkill), pas un `dmg≥hp` naïf (commit 256563c). Les effets de réduction-TRIGGER que la prédiction n'évalue PAS
  (TerminatorArmour / `*HitReduction` / …) → tag `↓` + dégradation `K!`→`K?` (commit 2503e95, TF04 predOptimistic).
  RÉSIDUEL mineur : la range reste optimiste pour ces cibles-`↓` (le vrai chiffre n'existe nulle part dans le struct)
  → c'est précisément ce que le `↓` signale.
- vu : G01, seed 80072, seed 80020, seed 80085, seed 80004, seed 81001 (n+6, attaquant summon optimiste), seed 81000 (n+7, go/no-go fatal sur self-healer Incisus).

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

## TF12 — `applyAction` : Abraxas `MasterOfTheTutelaries` renvoie `ok=True` SANS summon ET SANS consommer l'action (no-summon non surfacé) — done — recurrence:2
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
- **fix livré + ROOT-CAUSE CORRIGÉ (validé live, build gqfc5mff6c)** : le no-summon **n'est PAS un quirk engine** — c'est
  une **illégalité de spawn-tile** (classe TF13/TF16). Reproduit live sur Abraxas (`thousInfernalMaster`, ability 1096) :
  cast `MasterOfTheTutelaries` sur une tuile **+move-only** (2,1) → `ok:true, mutated:false, eventCount:2, spawned:0,
  actionConsumed:false` (signature TF12 exacte) ; cast sur la tuile **now-legal** (2,0) → `spawned:1, actionConsumed:true`
  (`AddUnit Unit_IsSummoned=1 Unit_Parent_Id=88` = Pink Horror). Le summon spawn **À LA TUILE `to` du cast** (RE ghidra
  confirme : `Spawn(ctx, …, ctx+0x178=target-tile, …)`) qui DOIT être dans `fromHere` (now-legal). En seed 70009 le cast
  (2,1) n'était PAS la tuile spawn now-legale → no-op. **H37 « free-hex » était sur la bonne piste** (c'est bien la
  spawn-tile) mais sa réfutation a confondu « hex libre adjacent » avec « tuile spawn now-legale de l'engine ».
  **3 garde-fous livrés** : (1) hook `applyOneAction` renvoie `spawned`+`actionConsumed` sur toute ability ;
  (2) `_action_failed` flagge le no-op via `actionConsumed=False` (backstop, même quand `eventCount>=1` à cause de
  `User_UseAbility`) ; (3) la pré-validation tile TF16 **REJETTE proactivement** le cast hors-`fromHere`
  (« hex (2,1) atteignable seulement +move → déplace d'abord »). **DOCTRINE CORRIGÉE** : MoTT **EST armable** — caster les
  summons sur une tuile **now-legal (`fromHere`)**, jamais `+move` ; ne PAS éviter l'ability (l'ancienne doctrine (c) était
  fausse). Note RE : MoTT est un comportement composite `AddEffect(0x4ad) & Spawn(PinkHorror+auto-attaque)` ; l'effet
  installe la triggered `0x495` qui re-summon `On(9)` quand l'unité marquée inflige du Psychic (profil `0xd`).
- **vu** : seed 70002 (n=1, hypothétisé free-hex gate) + seed 70009 (n=2, en fait cast hors-`fromHere`) ; résolu live
  Abraxas seed 555.

## TF13 — `abilities`/legality ne tient pas compte du spawn-tile requirement des summons — done — recurrence:1
- **friction** : `abilities`/`reason` listent un summon (ex. `ScarabHive`, Aleph-Null) comme castable
  now/+move, mais le cast réel échoue `TargetHasFreeAdjacentTile` (cluster sans hex libre adjacent où
  spawn) → l'agent BURNE le move de l'unité avant de découvrir l'illégalité (« TOUR ABANDONNÉ » a bien
  préservé les actions antérieures, mais le move était déjà consommé).
- **amélioration** : intégrer la contrainte free-adjacent-tile (spawn-tile) dans la requête de légalité des
  summons → un summon sans hex de spawn libre = ∉ now/+move (comme une cible hors portée). Apparenté à TF01
  (summons sur hex) et TF12 (summon no-op non surfacé).
- **fix livré (vérifié live via TF12, même mécanisme)** : `abilityTargets.fromHere` = tuiles de spawn **now-legal**
  (légalité EXACTE de l'engine, EXCLUT déjà les tuiles de spawn illégales) ; `targets` = superset `+move`. Confirmé live
  sur `MasterOfTheTutelaries`/`AberrantHypermorph` : `fromHere=now[1]:(2,0)` vs `+move[13]` distingués correctement, et la
  **pré-validation tile TF16 rejette** un cast sur tuile hors-`fromHere` (« atteignable seulement +move → déplace
  d'abord ») AVANT de consommer le move/l'action. Donc la contrainte spawn-tile EST dans `fromHere` + enforced par la
  prévalidation → l'agent ne burn plus son move pour découvrir l'illégalité. **Doctrine** : juger la castabilité d'un
  summon sur `fromHere` (now), pas `targets` (+move). **Résiduel documenté** : `targets` (+move) peut sur-reporter un
  summon dont la tuile de spawn post-déplacement n'est plus libre (l'engine `GetAllValidTargetsFromAllPossibleMovementTiles`
  ne re-vérifie pas la liberté de la spawn-tile pour CHAQUE tuile de déplacement) → toujours re-confirmer via `fromHere`
  après un move.
- vu : seed 80072 (ScarabHive Aleph-Null) ; mécanisme résolu live Abraxas/Genestealer seed 555.

## TF14 — header `view` « tour N » figé / pas un indicateur de round fiable — done — recurrence:6
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
- **fix livré** : l'en-tête `view` affiche désormais `mon tour #N` — N = compteur MONOTONE fiable dérivé des
  marqueurs `endturn` de l'action_log (helper `_turn_no`, la MÊME logique que le guard) — au lieu du `view.turn`
  per-player oscillant. (Pas de `GetTotalTurnsFinished` live exposé côté hook ; le count d'endturn côté outil est
  la source monotone fiable, et se compare directement au cap pour juger le round-cap.) Validé live (`mon tour #1`).
- vu : seed 80072, seed 80097, seed 80000, seed 80003, seed 80001.

## TF18 — `play`/`play --spec` : id de l'attaque NORMALE NON-universel (id 69 ≠ toutes les units) + le DÉFAUT résout vers l'ACTIVE → cast illégal → « TOUR ABANDONNÉ » — done — recurrence:2
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
- **fix livré (amélioration (b))** : `play --spec` ET `_apply_spec_to` (guard) supportent désormais
  `{"kind":"normal","unit":N,"target":T}` (ou `"to":[col,row]`) — l'id de la normale est RÉSOLU côté outil via
  `_normal_ability_map` (ability `kind="normal"` du decisionView = `NormalAttackType` concret par unité), jamais
  deviné ni défauté vers un actif ; pré-validation `_ability_prevalidate` → reject structuré (`TargetIsInRange`)
  si hors portée au lieu d'un cast d'actif erroné. Validé live : necroWarden→id 69 (sa VRAIE normale, lue), reject
  propre hors-portée PUIS apply RÉUSSI en portée (mutated=True, cascade `Loki_NormalAttack`→`NormalAttack_AtomicDamage`).
  RÉSIDUEL : la doctrine (a) reste valable, et le DÉFAUT de `play` sans `ability` vise toujours le plan (non touché).
- vu : seed 80000, seed 80004.

## TF19 — `await` / RPC timeout transitoires pendant le pump Unity de l'adversaire (curl exit-28 -m 100 ; host « RPC timeout 15000ms » ; status urllib TimeoutError) — done — recurrence:11
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
  **n+5 (seed 80053, ts=b8)** : A re-signale plusieurs `timedOut:true` CONSÉCUTIFS sur le `await` 90s pendant que
  l'adversaire (B) délibérait longuement sur plusieurs tours → ré-émission de l'`await` à chaque fois (« as designed »).
  Transitoire, aucune action perdue ; re-confirme le pattern adversaire-lent → await-timeout → re-émettre.
  **n+6 (seed 81003, ts=b9)** : A re-signale de NOMBREUX `await` timedOut (`currentPlayer=4`) pendant les longs
  think-times de B → **~7 ré-émissions par hand-off** (lourd mais transitoire, aucune action perdue, géré par
  re-émission per protocole). B, lui, rapporte `await`/`view`/`play` corrects ce match (le flux partial-turn a marché
  proprement, finish autoritatif `winner=4` correct). Convergence asymétrique : le coût await-retry se concentre côté
  le joueur qui ATTEND le tour adverse long. Re-confirme le besoin (a) re-try transitoire côté outil / endpoint
  « est-ce mon tour ? » bon-marché.
  **n+7 (seed 81001, ts=b9)** : friction PARTAGÉE, mineure (transitoire, aucune action perdue). A : `await` curl
  `timedOut` répétés (opponent thinking, normal) + un background-curl exit-28 — tous transitoires, re-émis sans souci.
  B : un `await` curl exit-28 (client coupé avant le serveur) — transitoire « as documented », re-émis sans impact.
  Convergent (A+B) — re-confirme le pattern adversaire-lent → await-timeout → re-émettre (le fix host avale déjà le
  timeout transitoire en `timedOut` uniforme ; reste cosmétique).
  **n+8 (seed 81002, ts=b9)** : friction PARTAGÉE, transitoire, aucune action perdue. A : hand-off `await` avec
  `timedOut` fréquents + UN `transientError` (« RPC timeout 45000ms ») sur l'attente — tous transitoires, résolus par
  re-émission, aucun faux game-over. B : flux normal de `timedOut`/`transientError` + un curl exit-28 sur un `await`
  backgroundé — tous transitoires, re-émission résout (comportement documenté). Convergent (A+B) — re-confirme que le
  fix host avale le timeout transitoire en signal uniforme ; reste cosmétique, aucune correctness en jeu.
  **n+9 (seed 81004, ts=b9)** : B (team2) re-signale `await` exit-28 / `timedOut` MULTIPLES par tour (2-4 polls)
  pendant la délibération de l'adversaire A → ré-émissions répétées, « expected per protocol, not a failure ».
  Transitoire, aucune action perdue ; re-confirme le pattern adversaire-lent → await-timeout → re-émettre (le coût
  await-retry se concentre côté le joueur qui ATTEND le tour adverse long, cohérent avec n+6). Reste cosmétique.
  **n+10 (seed 81000, ts=b9)** : friction PARTAGÉE, transitoire, aucune action perdue. A (team1) : `await` `timedOut`
  TRÈS fréquents (longue délibération de B) → nombreuses ré-émissions par tour (« transient/expected per TF19, not a
  failure »). B (team2) : `timedOut`/`transientError` multiples + un raw « RPC timeout after 30000ms » pendant un pump
  → re-émission résout chaque fois. Convergent (A+B) — re-confirme le pattern adversaire-lent → await-timeout →
  re-émettre ; le fix host avale déjà le transitoire en signal uniforme, reste cosmétique.
- **fix livré (a/d host-side + b/c doctrine)** : (a/d, `router.ts`) l'endpoint
  `/api/selfplay/:id/await` **AVALE** un timeout/erreur TRANSITOIRE du poll interne
  `battleStatus` (queue RPC saturée pendant le pump adverse) au lieu de remonter un raw 500
  « RPC timeout 15000ms » (qui se lit comme un fail) → il continue à long-poller jusqu'à la
  deadline puis renvoie un `timedOut` UNIFORME (+ `transientError` pour la visibilité) ; seul
  un `ok===false` DÉFINITIF (runner nuké) reste un 502. (b/c, prompt player self-play + skill
  §7) : `curl -m 120` > le timeout serveur 90s (ne le race plus) ; `timedOut`/`transientError`/
  curl exit-28/sortie vide = TOUJOURS transitoire → RE-ÉMETTRE ; un `play`/`applyAction` qui
  timeout sur la RÉPONSE a PEUT-ÊTRE déjà appliqué (applied-but-slow) → vérifier `status`/`view`
  AVANT de re-jouer (ne pas double-apply). RÉSIDUEL : pas de clé d'idempotence DURE côté hook
  (`alreadyApplied`) — la doctrine check-status-avant-retry couvre le double-apply. **Activation :
  changement host → effectif au prochain restart host (reinject).**
- vu : seed 80000, seed 80003, seed 80004, seed 80002, seed 80001, seed 80053, seed 81003, seed 81001, seed 81002, seed 81004, seed 81000.

## TF20 — collision de glyph board-map : 'b' minuscule = terrain (drybush) ET lettre d'unité (rendu en double sur une rangée) — done — recurrence:2
- **friction** : l'ASCII map réutilise 'b' minuscule pour À LA FOIS un terrain (drybush) ET la lettre d'une
  unité → glyphe ambigu/dupliqué sur une rangée, mis-lecture de position possible. seed 80000-roundcap (B) :
  'b' drybush mis-lu comme le Tyrant Guard → charge fantôme stranded (cf. H60). **n+1 (seed 80000 ts=b7)** : A
  signale Pestillian rendu 'b' DEUX FOIS sur une rangée (artefact d'affichage / echo d'aura) → a dû cross-checker
  les positions réelles via `status` pour ne pas mis-lire les positions ennemies.
- **amélioration** : réserver les minuscules au terrain et les MAJUSCULES (ou un set disjoint) aux unités, OU
  dé-dupliquer le rendu d'unité par rangée ; doctrine d'ici-là = cross-check les positions via `status` (ground
  truth), jamais l'ASCII map seule quand les lettres collisionnent. (cf. hypotheses.md H60, même symptôme côté
  renderer.)
- **fix livré** : les glyphes terrain de `_GLYPH` (board.py) passent en SYMBOLES — Swamp `s`→`%`, DryBush `b`→`*` —
  et le fallback `tid[0].lower()` (qui produisait des lettres pour les terrains non mappés) devient `?` dans les DEUX
  renderers (board.py + oracle.py build_card). Les lettres sont donc RÉSERVÉES aux unités (MAJ=moi / min=ennemi), set
  disjoint du terrain → plus de collision 's'/'b'. Légendes mises à jour (`%swamp *drybush ?autre`). Validé live
  (légende correcte, aucun glyphe terrain en lettre sur le board).
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

## TF16 — contrainte de POSITIONNEMENT d'une ability/attaque non surfacée → no-op silencieux (mutated=false) — done — recurrence:5
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
  **n+2 (seed 80031, ts=b8)** : RE-CONFIRMATION variante (a) côté B (owner de Tarvakh) — `act ability`
  MurderousSwing émis APRÈS un move qui avait silencieusement échoué (la tuile choisie était HORS du movable
  set, le caster n'a PAS bougé) → l'attaque a résolu out-of-range en **no-op** mais **A CONSOMMÉ l'activation**
  de Tarvakh (perdue). ⚠ NUANCE vs (a) ci-dessus : ici l'activation a bien été consommée (B « cost me a
  Tarvakh action ») — `act ability` ne pré-vérifie PAS l'adjacence/range avant de consommer, contrairement au
  cas idéal « action NON consommée ». Doctrine confirmée : VÉRIFIER que le move a atterri (`view`/`abilities`)
  AVANT d'émettre l'attaque ; `act ability` n'auto-move PAS le caster vers la tuile du plan.
- **amélioration** : surfacer la contrainte dans `abilities`/`reason` (adjacence requise / axe de ligne / move-
  interne / range du +move depuis la tuile courante) et faire ÉCHOUER explicitement (raison structurée) au lieu du
  no-op silencieux — **y compris pour les attaques normales des summons hors-portée** (mêmes garde-fous que les
  casts ciblés). Doctrine d'ici-là : confirmer la tuile/cible EXACTE via `moves`/`abilities` AVANT de committer
  (apparenté TF13 spawn-tile, TF08/TF18 no-op normale, TF21 turn-flip sur cast rejeté).
- **fix livré** : `_ability_prevalidate` (appelé par `play`/`act` AVANT applyAction) couvre désormais les DEUX
  types de cible → plus de no-op silencieux sur contrainte de positionnement : (a/ENTITÉ) cibles `targetId` via
  `abilityReason` (GetInvalidTargetReason → raisons structurées `TargetIsInRange`/… — déjà en place) ; (b/TILE)
  cibles `to` hex (bombard / ligne à axe FIXE / summon / displace) via `abilityTargets` (énumère les TUILES valides
  now/+move ; `abilityReason` ne gère QUE les entités) → tuile demandée ∉ now → reject structuré « hex (c,r) HORS
  des tuiles valides (axe de ligne / portée / spawn-tile non libre) -> tuiles légales: [...] » ou « atteignable
  seulement +move -> déplace d'abord ». Couvre aussi le spawn-tile des summons (apparenté TF13). Helper `_tile_set`.
  RÉSIDUEL : le cas (c) « actif avec son PROPRE budget de move » (VigilanceEternal — pré-bouger casse l'actif) reste
  une affaire de DOCTRINE (pas un no-op à détecter au sens strict) → consigne au skill.
- vu : seed 80031 (adjacence), seed 80085 (ligne fixe), seed 80020 (move-interne), seed 80003 (summon +move / normale summon hors-portée), seed 80031 (b8, act-ability no-auto-move consomme l'activation).

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

## TF24 — état de COOLDOWN d'une ability non surfacé : `[indispo]` (vue MES ACTIFS) STALE/trompeur + pas de `RemainingCooldownTurns` + `reason` renvoie `ValidRequest` même cooldown-locked → il faut TENTER un cast réel pour savoir — done — recurrence:2
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
  **n+1 (seed 81001, ts=b9)** : A re-signale le PATTERN exact sur `ArmoriumCherub` (Vindicta) — une ability qui ne
  termine PAS le tour (Cherub + normale possibles) mais qui FLIPPE en `[indispo]`/cooldown après UN usage mid-tour.
  La légalité `abilities`/`MES ACTIFS` listait encore des cibles valides (`now[..]`) ALORS que l'état live était
  `[indispo]` → le cast a no-op'd avec `RAISON 'indispo (usable=false)'` → fallback sur la normale. Le `usable=false`
  rendu = le FIX TF24 qui marche (la pré-validation pré-rejette via `abilityState`), MAIS le ciblage `now[..]`
  sur-reporte toujours des cibles pour une ability cooldown-locked → re-confirme la friction state-vs-targeting
  (juger la dispo via `abilityState`/`reason`, JAMAIS le `now[..]` du ciblage seul). Caster ≠ MoW (Cherub porté par un
  `ActiveAbility` standard) → l'`abilityState` était bien renseigné cette fois (vs le résiduel MoW `Primary/Secondary`).
- **amélioration** : (a) afficher `RemainingCooldownTurns=N` dans la ligne « MES ACTIFS » de la vue (et dans
  `abilities`) → planifier autour du downtime barrage sans deviner ; (b) réconcilier les 3 chemins (vue `[indispo]`,
  `abilities`, `reason`) sur un MÊME verdict de disponibilité incluant le cooldown ; `reason` ne devrait PAS rendre
  `ValidRequest` (ciblage) quand l'ability est cooldown-locked — surfacer le cooldown comme cause d'indispo.
  Doctrine d'ici-là : ne PAS se fier au flag `[indispo]` de la vue seul (peut être STALE = ability en fait castable,
  cas A) NI au `ValidRequest` de `reason` seul (ciblage-only, ignore le cooldown, cas B) → confirmer la dispo réelle
  d'une ability cooldown via les DEUX, et si ambigu, tenter le cast (no-op/rejet propre si indispo).
- **fix livré (validé live, build gqfc5mff6c)** : la donnée cooldown EXISTAIT déjà côté hook (`readAbilityState` →
  `RemainingCooldownTurns` → `decisionView.units[].abilities[].cooldown`, rendu `[cdN]` dans MES ACTIFS). Le résiduel
  réel = `reason` (`abilityReason`) ignorait le cooldown (la couche `TargetingRule` n'a **aucun flag cooldown** → rend
  `ValidRequest`). **`abilityReason` renvoie maintenant `abilityState{usable,cooldown,disabled}`** lu sur l'objet
  `ActiveAbility` du caster. Validé live : `u96 PlasmaCannon` (cd1) → `CASTER: ValidRequest` (la couche targeting dit
  valide, IGNORE le cooldown — friction TF24 exacte) MAIS la nouvelle ligne `ÉTAT LIVE: cooldown=1 ⚠ targeting peut dire
  VALID mais COOLDOWN actif` réconcilie ; ability prête → `ÉTAT LIVE: prêt`. rl_duel `reason`/`_ability_reason`
  surfacent le cooldown comme cause d'indispo, et `_ability_prevalidate` **pré-rejette** un cast cooldown-locked/disabled.
  Les 3 chemins (vue `[cdN]`, `abilities.cooldown`, `reason.abilityState`) donnent désormais le MÊME verdict incluant le
  cooldown. **Résiduel** : une ability-machine `Primary/Secondary` dont le cooldown n'est pas porté par un objet
  `ActiveAbility` rend `abilityState=null` (cas `BasiliskBarrage` à re-vérifier sur un MoW live) → la doctrine « confirmer
  via vue + reason » reste le filet.
- vu : seed 80001 ; réconcilié live seed 555 (PlasmaCannon cd1) ; seed 81001 (ArmoriumCherub, n+1 — fix prévalidation a bien pré-rejeté, ciblage `now[..]` sur-reporte encore).

## TF25 — un `FINISH`/play APRÈS une action qui a DÉJÀ terminé le match → « ÉCHEC: stage Finished (need Running) » / « TOUR ABANDONNÉ » alarmant mais inoffensif — done — recurrence:1
- **friction** : sur le tour gagnant de B (team2, seed 80053), l'action précédente (Actus tuant Dante, dernier ennemi)
  avait DÉJÀ terminé le match (FinishMatch, `Match_Winner=4`). Le `FINISH u82` suivant a renvoyé
  « **ÉCHEC: stage Finished (need Running)** » et le harness a affiché « **TOUR ABANDONNÉ** » — COSMÉTIQUEMENT alarmant
  (se lit comme un tour raté) alors que la bataille était GAGNÉE (le kill + le FinishMatch avaient déjà appliqué). Pas
  de perte de correctness (le match était fini), mais le label « abandonné » sur une VICTOIRE est trompeur. Apparenté à
  TF21 (label « TOUR ABANDONNÉ » qui contredit le state réel) mais ici le déclencheur est une action POST-match-end.
- **amélioration** : (a) un `play`/`finish` émis après que le stage est passé `Finished` (match déjà décidé) devrait être
  **silencieusement no-op'd** (ou rendre « match déjà terminé — winner=N », PAS « TOUR ABANDONNÉ ») ; (b) idéalement le
  harness détecte le stage `Finished` AVANT d'émettre l'action trailing et s'arrête proprement avec le verdict. Friction
  d'observabilité (aucune action perdue, aucune correctness en jeu).
- **fix livré** : `cmd_play` lit le `battleStatus` autoritatif quand une action abort ; si `stage==Finished`, affiche
  `*** MATCH DÉJÀ TERMINÉ — winner AUTORITATIF = teamN ***` (+ marqueur `endturn` de fin de trajectoire) et retourne le
  `status`, au lieu de « TOUR ABANDONNÉ ». Le cas « victoire SANS action trailing » était déjà géré (la boucle endturn
  lit `stage != Running` → « battle finie après mon tour »). Validé par revue (réutilise le mapping winner de cmd_status).
- vu : seed 80053.

## TF26 — l'overlay « danger-zone » sous-warne (borne géométrique INFÉRIEURE — ne modélise pas RapidAssault/+move/range-2 actives) → focus réalisé pire que le compte affiché — open — recurrence:1
- **friction** : A (team1, seed 80053) — ses units forward affichaient un danger 2-5, mais le focus RÉALISÉ au tour
  adverse fut PIRE (3 kills en UN tour ennemi) que le compte ne le laissait présager. Cause : l'overlay calcule une
  borne géométrique (portée d'attaque « statique ») mais l'adversaire avait 3 bursters mêlée avec **RapidAssault**
  (+1 move avant la 1ʳᵉ attaque) + actifs **range-2** + charges → leur REACH effective dépasse la zone géométrique
  affichée. Cohérent avec le caveat documenté « danger-zone = lower-bound » mais re-confirmé coûteux ici (A a sous-estimé
  l'exposition de Morvenn/Makhotep/Njal en se fiant au compte). Apparenté à TF04 (prédictions optimistes) mais sur la
  PORTÉE/atteignabilité, pas le dégât.
- **amélioration** : (a) intégrer les bonus de mouvement conditionnels (RapidAssault, +1 move buffs, charge-range) ET la
  portée des actives range-2 dans le calcul de danger-zone → afficher la reach effective MAX, pas la portée statique ;
  (b) à défaut, surfacer explicitement « borne INFÉRIEURE — +move/charge/active-range non modélisés » sur l'overlay.
  Doctrine d'ici-là : traiter le compte danger-zone comme un PLANCHER, pas un plafond — garder les fragiles encore
  plus shallow vs un roster à RapidAssault/charge/range-2 (la reach réelle est ~1-2 hex au-delà de l'overlay).
- vu : seed 80053.

## TF27 — `guard --climb` rend une sortie IDENTIQUE quelle que soit la spec passée (action_log replay DÉSYNC après plusieurs split `play --no-ai`) → guard non-fiable, l'agent décide à la main — done(détection) — recurrence:1
- **friction** : sur un tour de B (team2, seed 80031, ts=b8), `guard --climb` a retourné une sortie **IDENTIQUE**
  (même NET −2.46, même worst-unit, mêmes losses) **quelle que soit la spec** que B passait → le replay de
  l'`action_log` paraissait DÉSYNCHRONISÉ et les actions de la spec n'étaient PAS appliquées au sim cloné. B a dû
  **abandonner le guard** et raisonner manuellement depuis le board + les kits ce tour-là. Apparu APRÈS plusieurs
  tours split `play --no-ai` (B note : « guard reliability degrades after several split play --no-ai turns »).
  DISTINCT de TF23 (guard trop LENT → timeout) : ici le guard RÉPOND vite mais avec une éval CONSTANTE/fausse
  (la spec n'altère pas le sim) → garde-fou silencieusement inutile (pire qu'un timeout, car l'output a l'air valide).
- **amélioration** : (a) le clone-sim du guard doit appliquer la spec passée par-dessus l'état COURANT (pas un
  action_log rejoué périmé) → vérifier que `guard --climb` repart du `_state` à jour, pas d'un replay désynchronisé
  après des tours split ; (b) si le sim ne peut pas appliquer la spec (désync détecté), ÉCHOUER explicitement
  (« guard sim désync — décision manuelle ») plutôt que rendre une éval constante trompeuse ; (c) idéalement un
  hash/marqueur de l'état d'entrée du guard pour détecter qu'il ne bouge pas entre 2 specs distinctes.
  Doctrine d'ici-là : si `guard --climb` rend le MÊME NET pour 2 specs différentes, le considérer DOWN (désync) et
  décider manuellement (défaut conservateur), comme pour TF23.
- **fix livré (détection — améliorations (b)+(c))** : `_sim_turn` compare le snapshot du CLONE post-replay au snapshot
  LIVE (`_replay_desync` : sets d'unités + hp + position par unité) ; toute divergence → ABORT explicite
  `replay désync (clone≠live) — <détails>` au lieu d'une éval constante trompeuse. Le snapshot live est capturé 1× sur
  le runner live et propagé à tous les sims (`guard`/`rollout`, via `_hill_climb`). Le guard signale donc clairement
  quand il est DOWN → décision manuelle (la doctrine de repli), au lieu de mentir. Validé live (tour 1 : zéro
  faux-positif, NET varie bien par spec). **RÉSIDUEL (amélioration (a) NON faite)** : la fidélité du replay en tours
  splittés n'est pas restaurée — le guard abort proprement quand l'état a désync, mais ne « répare » pas le replay
  (re-bâtir le clone depuis l'état COURANT plutôt qu'un action_log rejoué reste un chantier ouvert).
- vu : seed 80031.

## TF28 — pas d'estimation du dmg INCOMING worst-case pour les effets à TIR DIFFÉRÉ (Seeker/RailRifle) sur MES units : `MES ACTIFS`/`decisionView.effects` flagge le Markerlight mais SANS magnitude → l'agent sous-évalue la menace pending-fire — done — recurrence:1
- **friction** : A (team1, seed 80031, ts=b8) — un `SeekerMissileFrequencyLock` avait marqué son admecDestroyer (Sy-gex,
  9537 PV). La vue `MES ACTIFS` / `decisionView.effects` a bien FLAGGÉ le Markerlight (effet actif présent) mais
  **sans AUCUNE magnitude** du tir à venir → A a projeté le hit comme « ~5800 survivable » (le nominal gameconfig
  5456-6184) et a HOLD Sy-gex passivement dans la portée du Seeker. Le missile a landé pour **9263** (amplifié par
  RangedSpecialist + HeavyWeapon + markerlight, BIEN au-delà du nominal) → Sy-gex à 274, mort le tour suivant = perte
  de son Overwatch + HeavyGravCannon peel pour rien. L'outil n'avait AUCUNE prédiction du worst-case incoming amplifié.
  DISTINCT de TF04 (dmg de MES plans optimiste/max-roll non mitigé pour MES attaques sortantes) : ici c'est le dmg
  ENTRANT d'un effet pending-fire ennemi sur MES units qui n'a pas de magnitude estimée du tout.
- **amélioration** : (a) pour chaque effet de tir DIFFÉRÉ actif sur une de MES units (Markerlight/Seeker, RailRifle
  pending, MalleusRocket telegraphié…), surfacer une **estimation worst-case du dmg incoming** (nominal du caster ×
  amplificateurs connus : RangedSpecialist, HeavyWeapon, markerlight) dans `decisionView.effects` / `MES ACTIFS` →
  l'agent voit « Seeker pending ~9000+ sur Sy-gex » et bouge/spend la cible AVANT la résolution ; (b) à défaut,
  TAGGER l'effet pending-fire comme « magnitude amplifiée possible ≫ nominal » pour casser la projection « nominal
  survivable ». Doctrine d'ici-là : un effet pending-fire (Seeker/RailRifle) sur une de mes units = traiter le hit
  comme **potentiellement amplifié bien au-delà du nominal** → ne JAMAIS laisser une unité marquée HOLD passivement
  en portée ; la bouger hors-range (si dodgeable) OU la dépenser offensivement ce tour OU tuer le caster avant le tir.
- **fix livré (amélioration (b) — pur Python oracle.py, 0 hook ; rendu validé synthétique)** : `oracle.py` détecte les
  effets de TIR DIFFÉRÉ (`_is_pending_fire` : `SeekerMissileFrequencyLock`/`HeavyRailRifle_Pending`/`Markerlight`/
  `MalleusRocketLauncher_PendingTarget`|`_SpottedTarget`/`TargetingProtocols_PendingAttack`/`AnnihilatorBeam_PendingAttack`/
  `PoundThemToDust_PendingAttack`) posés par un **ENNEMI** (gate `source ∈ enemy_ids`) sur une de MES units, et émet en
  EFFETS CRITIQUES : `⚠ [PENDING-FIRE≫] uX marqué par uY — TIR DIFFÉRÉ de magnitude AMPLIFIÉE bien au-delà du nominal
  (RangedSpecialist/HeavyWeapon/markerlight : Seeker nominal ~5500 → 9263 observé). NE PAS hold passivement…`. + entrée
  crit `SEEKER` ajoutée à `_CRIT_EFFECTS`. Casse la projection « nominal survivable ». **Volet (a) NON fait** (estimation
  chiffrée du worst-case = nécessite le kit du caster + le modèle d'amplification, non porté par l'outil) → le TAG (b) est
  le filet ; la doctrine « pending-fire = potentiellement ≫ nominal, ne pas hold en portée » reste la règle.
- vu : seed 80031.

## TF29 — un actif qui NE TERMINE PAS le tour (JakhalStimms, `actionConsumed=False` LÉGITIME) est FAUX-flaggé no-op par le backstop TF12 → `play --spec`/`--no-ai` ABANDONNE le tour (« TOUR ABANDONNÉ ») et drop les actions suivantes du spec, alors que l'ability A RÉSOLU (a dealt damage) — done — recurrence:2
- **friction** : `JakhalStimms` (Macer/worldJakhal) est conçu pour **NE PAS consommer l'activation** (on stimm PUIS on
  attaque en normale le MÊME tour). Quand A (team1, seed 81003) l'a joué via `play --no-ai`, l'ability **a bien
  résolu (dealt damage)** mais `play` l'a flaggée comme **no-op / « TOUR ABANDONNÉ »** (`spawned=0`, le caster garde son
  activation) ET **n'a PAS lancé les actions suivantes en file** (la normale de Macer + Abraxas) → A a dû ré-émettre
  chaque follow-up en appels séparés. Aucune activation perdue (splittable), mais le label « abandonné » est trompeur
  (l'ability a fonctionné). ROOT CAUSE probable = le **backstop TF12** (`_action_failed` flagge le no-op via
  `actionConsumed=False`, même avec `eventCount>=1`) : il confond un VRAI no-op (summon non spawné) avec un actif
  **légitimement non-turn-ending** qui A consommé son cast et dealt damage mais ne consomme PAS l'activation de l'unité.
  C'est le FAUX-POSITIF symétrique du fix TF12. Apparenté TF08 (no-op silencieux abandonne le tour) mais ici l'action
  a RÉUSSI et le tour ne devrait PAS s'abandonner.
- **amélioration** : (a) la garde doit distinguer un actif **non-turn-ending qui a résolu** (`ok=True` ET
  (`mutated=True` OU des events de dégât réels) ) d'un VRAI no-op (aucun event/mutation) → ne PAS abort sur le seul
  `actionConsumed=False` quand l'ability a produit du dégât ; idéalement un flag `endsTurn`/`keepsActivation` côté hook
  (lu sur l'ActiveAbility, ex. JakhalStimms) pour que `play --spec` ENCHAÎNE le follow-up sur le même caster au lieu
  d'abandonner ; (b) corriger le label (« actif non-turn-ending résolu — caster garde son activation, continuer le
  spec », PAS « TOUR ABANDONNÉ »). Doctrine d'ici-là : pour un actif no-turn-end (JakhalStimms…), émettre le stimm puis
  les follow-ups en appels `act`/`play` SÉPARÉS (ne pas compter sur l'enchaînement `--spec` sur ce caster).
- **n+1 (seed 81002, ts=b9)** : WarHowl (Ragnar self-buff) via `play --spec`/`--no-ai` — l'ability A APPLIQUÉ le buff
  (les 3 melee Characters ont gagné `WarHowl_ExtraDamage_Unstoppable`) ET Ragnar a GARDÉ son activation, mais `play`
  l'a flaggé « TOUR ABANDONNÉ / NO-OP » → label trompeur (A a failli re-caster / croire à un échec). ⚠ NUANCE vs
  JakhalStimms (n=1, qui a dealt DAMAGE) : WarHowl est un PUR BUFF → AUCUN event de dégât ni mutation pos/hp →
  l'amélioration (a) (« ne pas abort si dmg events / `mutated=True` ») NE le rattraperait PAS → renforce le besoin du
  flag hook `endsTurn`/`keepsActivation` (lu sur l'ActiveAbility) OU de détecter l'application d'un buff (AddEffect)
  pour distinguer un actif non-turn-ending RÉSOLU d'un vrai no-op.
- **fix livré (régression du backstop TF12 — pur Python, vérifié live build gqfc5mff6c)** : `_action_failed` ne flagge
  plus le no-op sur le SEUL `actionConsumed=False` — il exige AUSSI **aucun effet réel** via le helper
  `_ability_had_real_effect(act)` : `mutated` OU `spawned` OU un event de cascade SIGNIFICATIF
  (`UnitDamaged`/`ReceiveEffect`/`RemoveUnit`, décodé via `stream_events.step_name`). Un actif non-turn-ending qui a
  RÉSOLU (JakhalStimms = `UnitDamaged`/mutated ; WarHowl = `ReceiveEffect`) est donc reconnu comme ayant agi → **PAS
  d'abort, le spec CONTINUE** (le caster garde son activation et enchaîne ses follow-ups). Seul le VRAI no-op (cast
  échoué : uniquement le marqueur `User_UseAbility`, 0 dmg/effet/spawn/mutation) reste flaggé. **Vérifié sur données
  RÉELLES** : WarHowl(1106) live → `actionConsumed:false, mutated:false, spawned:0, eventCount:17`, steps =
  {ReceiveEffect, ActivateEffect, ChangeAbility} → `_ability_had_real_effect=True` → **non flaggé (le tour continue)** ;
  + 4 cas unitaires (no-op→abort, JakhalStimms→continue, WarHowl→continue, summon-OK→continue). NB : le label/abort
  d'un VRAI no-op reste correct (et la pré-validation TF16 attrape de toute façon le cas summon-hors-`now` AVANT
  applyAction). Amélioration (a)/(b) du flag hook `endsTurn` non nécessaire — l'event-cascade suffit.
- vu : seed 81003, seed 81002 ; corrigé+vérifié live seed 81002 (WarHowl).

## TF30 — `play --no-ai` parfois dispatché en TÂCHE DE FOND (renvoie un task-id au lieu de la sortie inline) → lire le fichier de sortie pour voir la cascade — open — recurrence:2
- **friction** (cosmétique, harness-side) : B (team2, seed 81003) — un appel `play --no-ai` a été **dispatché de façon
  inattendue en background task** (a retourné un identifiant de tâche au lieu de la sortie inline) → B a dû lire le
  fichier de sortie pour voir la cascade. Aucun impact d'état, purement cosmétique. C'est un comportement du HARNESS
  (heuristique `run_in_background` du tool Bash), PAS un manque de l'outil `rl_duel` — mais signalé comme friction.
  Apparenté à TF19 doctrine (b) qui documente déjà le pattern « pas de sleep → lire le task-output file d'un `play`
  backgroundé ».
- **amélioration** : (a) côté process player self-play, forcer `play --no-ai` en FOREGROUND (sortie inline) ou, si
  background imposé, surfacer clairement « tâche backgroundée → lis <fichier> » ; (b) doctrine (déjà TF19 b) : si un
  `play` renvoie un task-id, lire le task-output file (ne pas re-jouer — l'action peut avoir appliqué, cf. TF19 c
  applied-but-slow). Pas de correctness en jeu.
- **n+1 (seed 81004, ts=b9)** : A (team1) — un `play --no-ai` (T4) a été **relocalisé en tâche de fond à cause
  de la LENTEUR** (applied-but-slow) → a dû lire le fichier de sortie pour confirmer l'application. ⚠ NUANCE vs n=1
  (background « inattendu ») : ici le déclencheur explicite = la durée de l'action a dépassé le seuil foreground du
  harness (apparenté TF19 c applied-but-slow). A a géré PER DOCTRINE (a vérifié l'application via le fichier AVANT de
  continuer = PAS de double-apply). Cosmétique, aucune correctness en jeu. Re-confirme la doctrine TF19(b)/(c) :
  un `play` backgroundé → lire le task-output file ET vérifier l'application avant de re-jouer.
- vu : seed 81003, seed 81004.

## TF31 — `play --no-ai`/`--spec` : un follow-up dont la CIBLE est DÉJÀ MORTE (tuée par une action ANTÉRIEURE du MÊME spec batch) no-op → « TOUR ABANDONNÉ » + DROP des actions restantes → focus-kill front-loadé force le re-submit — open — recurrence:3
- **friction** : A (team1, seed 81001) a front-loadé un focus-kill dans un seul `play --no-ai` spec. Une fois la cible
  morte par la 1ʳᵉ action, les actions SUIVANTES du même batch qui visaient ENCORE cette cible (Cherub + normale de
  Vindicta sur Kariyan déjà mort T3 ; idem sur Calgar T4) ont **no-op'd** (rien à frapper) → `play` a affiché
  « **TOUR ABANDONNÉ** » et **n'a PAS lancé les actions restantes** du spec → A a dû **ré-émettre chaque action
  restante** en appels séparés. Aucune activation perdue (les bonnes units finissent par jouer via re-submit, et la
  cible était bien tuée), MAIS round-trips en plus à chaque focus-kill front-loadé + label « abandonné » trompeur sur
  une séquence qui a en fait RÉUSSI son kill. ROOT CAUSE = le **backstop TF12** (`_action_failed` flagge le no-op via
  `actionConsumed=False`) : il confond un no-op BÉNIN/ATTENDU (cible déjà morte = rien à faire, à SKIPPER) avec un VRAI
  no-op (summon non spawné) → abandonne tout le reste du spec. DISTINCT de TF29 (où l'actif a RÉSOLU/dealt damage) :
  ici l'action no-op VRAIMENT (cible morte) mais c'est ATTENDU et le spec devrait CONTINUER, pas s'abandonner.
- **amélioration** : (a) le runner de spec doit traiter un no-op dont la CIBLE n'existe plus (morte plus tôt dans le
  même batch) comme un **SKIP bénin** (« cible déjà morte — action ignorée, on continue ») et ENCHAÎNER les actions
  restantes, au lieu d'abort le tour ; (b) à défaut, ne pas labelliser « TOUR ABANDONNÉ » quand le batch a déjà produit
  des kills/mutations (distinguer abort-réel d'un skip-cible-morte) ; (c) doctrine d'ici-là : pour un focus-kill
  front-loadé, ne PAS empiler plusieurs actions sur la MÊME cible dans un seul spec — émettre la 1ʳᵉ (le kill) puis
  re-séquencer les follow-ups sur des cibles VIVANTES en appels séparés. Apparenté TF12 (backstop)/TF29 (faux no-op
  abandonne le tour)/TF25 (label « TOUR ABANDONNÉ » trompeur).
- **n+1 (seed 81002, ts=b9)** : A (team1) — une attaque NORMALE (Actus) sur un Shield Drone que Thoread venait de
  TUER (cible déjà morte ce tour) a no-op → `play` a affiché « TOUR ABANDONNÉ » et abandonné le reste du spec → A a dû
  ré-émettre les follow-ups. Même classe que n=1 (no-op BÉNIN/ATTENDU sur cible-morte = à SKIPPER, pas à aborter) ;
  re-confirme que le runner de spec devrait SKIP une action sur cible-morte et ENCHAÎNER. A l'a noté comme friction
  (« une dead-target action devrait être auto-skippée plutôt qu'aborter le spec »).
- **n+2 (seed 81004, ts=b9) — focus sur le RAISON-CODE trompeur** : A (team1) — `play --no-ai` T7 a aborté sur
  Dreir→Isabella avec la raison `TargetIsInRange` (out-of-range) ALORS qu'Isabella avait DÉJÀ été tuée par Maugan Ra
  dans le MÊME spec → le code de rejet (hors-portée) était TROMPEUR vs la vraie cause (cible morte). ⚠ NUANCE ce match :
  A rapporte « partial-apply + continue worked fine » (le reste du spec a été appliqué) → le DROP-des-actions-restantes
  était moins sévère que n=1/n+1, MAIS le RAISON-CODE reste le résiduel. CONTRASTE intra-match : B a rapporté que
  `play --no-ai` a géré le dead-target no-op GRACIEUSEMENT (« TOUR ABANDONNÉ », caster a gardé son activation = OK) →
  l'expérience diverge selon le chemin, ce qui isole le résiduel : c'est le LABEL/raison-code (afficher `TargetIsInRange`
  pour une cible MORTE, et « TOUR ABANDONNÉ » sur une séquence qui a réussi son kill) qui trompe, PAS la préservation
  d'activation. Amélioration (b) renforcée : un no-op cible-morte doit rendre « cible déjà morte — action skippée », JAMAIS
  un faux `TargetIsInRange`/out-of-range.
- vu : seed 81001, seed 81002, seed 81004.

## TF32 — `decisionView` plans : une tuile « attack-from » suggérée est OCCUPÉE (par un decoy) / HORS de la grille `moves` → les tuiles de plan peuvent inclure des hexes non-atteignables/occupés — open — recurrence:1
- **friction** : B (team2, seed 81001) — un plan d'attaque listait une tuile d'attaque-depuis `(1,3)` pour un K!
  (Helbrecht sur Xybia) qui était (a) **OCCUPÉE par un decoy** Genestealer (tuile Steppable non-targetable) ET (b)
  **ABSENTE de la grille `moves`** → la tuile de plan n'était PAS réellement atteignable. Si B avait committé sur la
  tuile du plan sans cross-check, le move aurait no-op/échoué (cf. TF16). Friction d'observabilité : les tuiles
  « attack-from » des plans peuvent inclure des hexes occupés/non-reachable (le moteur `GetAllValidTargetsFrom
  AllPossibleMovementTiles` ne re-filtre pas l'occupation/atteignabilité réelle de CHAQUE from-tile).
- **amélioration** : (a) intersecter les tuiles « attack-from » des plans avec la grille `moves` (atteignables ET
  libres) AVANT de les afficher → ne plus proposer une from-tile occupée par un decoy/unité ou hors-budget de move ;
  (b) à défaut, TAGGER une from-tile de plan « ⚠ ∉ moves (occupée/non-atteignable) — cross-check ». Doctrine d'ici-là :
  TOUJOURS cross-checker une tuile d'attaque-depuis suggérée par un plan contre la grille `moves` (ground truth de
  l'atteignabilité) avant de committer le move. Apparenté TF16 (no-op silencieux sur contrainte de positionnement) /
  TF13 (spawn-tile re-vérifier via `fromHere`).
- vu : seed 81001.

## TF33 — la cascade (`play`/`view`) ne LABELLISE PAS la SOURCE d'un dmg ENTRANT pris par une unité PENDANT sa propre action (réaction/counter/attribution non attribuée) — open — recurrence:1
- **friction** (candidat, observateur unique) : B (team2, seed 81001) — un Skitarii Vanguard summon a pris **~1760 dmg
  dans la MÊME action où il attaquait le Neophyte** (possible réaction/Overwatch/counter, ou quirk d'attribution) → la
  cascade rendue **n'a PAS clairement labellisé la SOURCE** de ce dmg entrant → B n'a pas pu déterminer d'où venait le
  coup (réaction adverse ? counter ? attribution erronée ?). Friction d'observabilité d'ATTRIBUTION : le dmg pris par
  une unité pendant SA propre activation n'est pas rattaché à un attaquant/effet identifiable dans la sortie.
- **amélioration** : (a) dans la cascade, attribuer CHAQUE évènement de dmg à sa source (attaquant entityId + ability/
  effet déclencheur : réaction/Overwatch/counter/DoT) → l'agent voit « Vanguard −1760 par <uX> (Overwatch/reaction) » ;
  (b) à défaut, au moins tagger un dmg entrant non-attribué comme « source non identifiée (réaction/counter probable) »
  pour ne pas le lire comme un bug. Apparenté à l'attribution Effect_Type (cf. MEMORY UnitDamaged Effect_Type) mais ici
  le manque est le RENDU côté `play`/`view`. À re-vérifier sur n>1 (déterminer si c'est une réaction réelle non
  rendue OU un quirk d'attribution).
- vu : seed 81001.

## TF34 — pas d'estimation du dmg INCOMING d'un OVERWATCH armé quand on planifie un MOVE dans l'arc : l'overlay danger COMPTE les menaces mais ne donne AUCUNE magnitude → un move dans un arc d'overwatch multi-hit (surtout superposé) = mort mid-move SANS warning — open — recurrence:1
- **friction** : A (team1, seed 81002) a walké Ragnar (10038, son moteur WarHowl) dans l'arc COMBINÉ Re'vas
  `EarlyWarningOverride` + Calandis `Overwatch` → tué par ~10k de riposte multi-hit DURANT le move, AVANT toute
  attaque. L'overlay danger-zone a bien COMPTÉ des menaces sur la tuile mais n'a JAMAIS convey la MAGNITUDE (« entrer
  dans cet arc = ~10k overwatch multi-hit = mort »). Un move dans un arc d'overwatch ARMÉ (surtout SUPERPOSÉ : EWO +
  hold-OW) n'est PAS flaggé avec un dmg entrant attendu → l'agent ne peut pas voir que le move est LÉTAL avant de le
  committer. C'est exactement le coup qui a perdu le match (cf. wiki §1 Overwatch « arcs superposés = one-shot
  mid-move »). DISTINCT de TF26 (danger-zone = reach géométrique INFÉRIEURE pour le tour ADVERSE, sous-modélise
  RapidAssault/+move/range-2) : ici la menace est la RÉACTION overwatch déclenchée par MON move, multi-hit, dont la
  magnitude n'est estimée nulle part. DISTINCT de TF28 (dmg incoming d'un effet pending-fire/différé sur MES units) :
  ici c'est le dmg RÉACTIF d'un Overwatch ARMÉ déclenché par le déplacement, pas un tir différé.
- **amélioration** : (a) quand une de MES units planifie un MOVE qui ENTRE dans un arc d'overwatch ENNEMI armé (trait
  `Overwatch` actif OU `EarlyWarningOverride`/équivalent posé ce tour), surfacer une estimation worst-case du dmg de
  riposte (nominal × hits × nb d'overwatchers dont l'arc couvre la tuile d'entrée) → « move dans l'arc OW de uX(+uY)
  ≈ ~Nk multi-hit » ; (b) à défaut, TAGGER toute tuile-cible de move située dans un (a fortiori plusieurs) arc(s)
  d'overwatch armé(s) comme « ⚠ OW armé — riposte multi-hit possible ≫, ne pas y walker une unité seule » (filet
  qualitatif si le chiffre n'est pas portable). Apparenté TF28 (magnitude d'un dmg entrant non estimée) et TF26
  (danger-zone borne inférieure). Doctrine d'ici-là (cf. skill §7 + wiki §1 self-play consensus seed 81002) : ne
  JAMAIS walker une unité seule dans un arc d'overwatch armé ; SEUL Infiltrate traverse sans trigger ; mapper les
  overwatchers AVANT d'engager.
- vu : seed 81002.

## TF35 — l'adjacence hex (PARITÉ) et l'atteignabilité (chemin bloqué par mes propres units) ne sont PAS lisibles sur l'ASCII map → planifier move/attaque exige les pré-checks `moves`/`abilities` (rejets corrects mais map insuffisante) — open — recurrence:2
- **friction** (observabilité) : B (team2, seed 81002) a rencontré plusieurs rejets de reachability/adjacence NON
  lisibles sur la carte ASCII : (5,8) inatteignable pour Calandis T1 (chemin bloqué par MES propres units), (4,5)
  inatteignable pour le drone 151 T4, et Corrodius à (2,3) PAS adjacent-mêlée à Actus à (2,2) (parité hex) →
  `TargetIsInRange`. Les rejets étaient CORRECTS et ont préservé les actions déjà appliquées (B a pu ré-émettre le
  reste — fix TF16), MAIS l'adjacence hex (offset de parité ligne paire/impaire) et l'atteignabilité (chemin libre)
  ne se DÉDUISENT PAS de la grille ASCII → les commandes pré-check `moves`/`abilities` étaient OBLIGATOIRES pour
  planifier sans burn. Friction d'observabilité distincte de TF16 (la partie no-op silencieux est FIXÉE — ici les
  rejets sont surfacés/corrects) : le manque est que la MAP elle-même ne rend pas la géométrie hex (« ça a l'air
  adjacent en ASCII » est FAUX à cause de la parité).
  **n+1 (seed 81000, ts=b9 — PARTAGÉE A+B, + extension RANGE d'ATTAQUE)** : DEUX sides re-buttent sur la géométrie
  hex non-lisible. **Move** : A — Makhotep→(2,3) rejeté « HORS du movable set » même APRÈS que le blocker eut quitté
  la tuile (le movable set résolu ≠ ce que l'ASCII suggère) ; B — `play --spec` move Incisus→(5,6) et Shadowsun→(6,6)
  pré-rejetés « HORS movable set » alors que les tuiles paraissaient adjacentes/libres (terrain/footprint), validator
  correct + resume partiel a préservé toutes les actions antérieures (fix TF16). **Range d'ATTAQUE (extension)** : A —
  Abaddon (4,4) NE POUVAIT PAS toucher Incisus (4,6) (straight +2 rangées rejeté hors-r2) MAIS la diagonale
  (3,4)→(4,6) ÉTAIT en r2 → la distance hex N'EST PAS axiale simple ; le même piège de parité s'applique à la PORTÉE
  d'attaque, pas seulement au move/adjacence. Doctrine confirmée+étendue : ne JAMAIS faire de maths hex à la main (ni
  adjacence, ni atteignabilité, ni PORTÉE) → vérifier via `moves`/`abilities`/plans (listes de tuiles), jamais l'œil
  sur l'ASCII.
- **amélioration** : (a) rendre l'adjacence/atteignabilité directement sur la vue (ex. marqueurs des hexes
  adjacents/reachables autour de l'unité active, ou un mini-overlay « cases atteignables ce tour ») pour ne pas
  exiger un pré-check séparé par action ; (a-bis) exposer la PORTÉE EFFECTIVE d'une attaque (set de tuiles en-range
  depuis la tuile courante) — la r2/r3 affichée se lit comme axiale mais ne l'est pas (parité) ; (b) à défaut,
  doctrine (déjà partielle) : TOUJOURS cross-checker une adjacence/atteignabilité/PORTÉE via `moves`/`abilities`/plans
  AVANT de committer (ne JAMAIS juger l'adjacence mêlée NI la portée ranged à l'œil sur l'ASCII — la parité hex fausse
  l'intuition). Apparenté TF16 (contrainte de positionnement) / TF32 (from-tile de plan occupée/hors-grille) / TF20
  (rendu de glyph ambigu).
- vu : seed 81002, seed 81000 (A+B, move + range d'attaque).

## TF36 — les unités SUMMONED (Death Riders / Inceptors) ne sont PAS listées dans « À ACTIVER » mais APPARAISSENT dans PLANS D'ATTAQUE et SONT commandables via `play --spec` → ambiguïté sur quels summons ont encore une action ce tour — open — recurrence:1
- **friction** (observabilité) : A (team1, seed 81004) — ses unités summonées (`astraSmnDeathRider` via Dreir,
  `ultraSmnInceptor` via Bellator) **n'étaient PAS listées dans la section « À ACTIVER »** de la vue, MAIS
  elles **figuraient bien dans les PLANS D'ATTAQUE** et **étaient commandables via `play --spec`**. Résultat :
  ambiguïté sur **quels summons ont encore une action disponible** sur un tour donné — A ne pouvait pas se fier à
  « À ACTIVER » comme liste exhaustive des unités jouables (les summons jouables en sont absents). Aucune action
  perdue (A les a commandées via les PLANS), mais la liste « À ACTIVER » sous-rapporte le set jouable réel.
- **amélioration** : (a) inclure les unités SUMMONED encore actives dans la section « À ACTIVER » (source unique
  de vérité du set jouable, alignée avec ce que `play --spec` accepte) ; (b) à défaut, TAGGER explicitement les
  summons jouables (« +N summons jouables non listés ci-dessus — cf. PLANS ») pour lever l'ambiguïté. Doctrine
  d'ici-là : ne PAS traiter « À ACTIVER » comme exhaustif quand des summons sont sur le board → cross-checker les
  PLANS D'ATTAQUE pour les summons jouables. Apparenté à la friction d'observabilité du set jouable (≠ no-op).
- vu : seed 81004.

## TF37 — un MOVE batché dans un `play --no-ai`/`--spec` multi-action n'applique PAS SILENCIEUSEMENT quand il dépend d'une tuile qu'une action ANTÉRIEURE du même batch doit libérer (ordering/validation intra-batch) → l'unité reste sur place + « à activer », re-émis seul ça marche — open — recurrence:1
- **friction** : B (team2, seed 81004) — un move batché de Makhotep `(5,7)→(5,6)` à l'intérieur d'un spec
  `play --no-ai` multi-action **n'a PAS appliqué SILENCIEUSEMENT** (l'unité est restée sur place, est restée
  « à activer ») ; **re-émis SEUL il a marché**. Hypothèse de B : **quirk d'ordering/validation intra-batch** —
  un move PLUS TARD dans le batch qui dépend d'une tuile qu'une action ANTÉRIEURE du même batch doit d'abord
  LIBÉRER (la tuile cible était peut-être encore occupée par une unité pas-encore-déplacée au moment où le move
  batché a été validé). Aucune activation perdue (re-submit seul = OK), MAIS le move a échoué SANS rejet surfacé
  (≠ TF16 dont les rejets de positionnement sont désormais surfacés ; ≠ TF08 format `to` string) → c'est un
  no-op SILENCIEUX spécifique à la DÉPENDANCE D'ORDRE entre actions d'un même batch.
- **amélioration** : (a) le runner de spec doit valider/appliquer chaque action séquentiellement sur l'état
  RÉSULTANT des actions précédentes du batch (re-résoudre la légalité d'un move APRÈS que les moves antérieurs ont
  libéré leur tuile), pas sur l'état d'entrée figé ; (b) à défaut, si un move batché no-op (tuile occupée au moment
  de la validation), ÉCHOUER explicitement (raison structurée « tuile (c,r) occupée — sera libre après l'action X »)
  au lieu d'un no-op silencieux. Doctrine d'ici-là : pour des moves inter-dépendants (une unité avance sur la tuile
  qu'une autre vient de quitter), les SÉQUENCER en appels séparés (ne pas compter sur l'ordering d'un seul spec) OU
  cross-checker via `view` que chaque move a atterri. Apparenté TF16 (no-op de positionnement) / TF08 (move no-op).
- vu : seed 81004.

## TF38 — `play --no-ai --end` avec un spec VIDE ne TERMINE PAS le tour (`--end` ignoré quand aucune action) → besoin d'un `act endturn` explicite — open — recurrence:1
- **friction** : A (team1, seed 81000) — un `play --no-ai --end` avec un **spec vide** (aucune action) **n'a PAS
  joué l'endturn** : le tour n'a pas été passé tant qu'un `act endturn` explicite n'a pas été émis. Surprise mineure
  (aucune action perdue), MAIS le flag `--end` suggère « finis le tour » → un agent qui veut PASSER son tour (hold
  total, rien à jouer) s'attend à ce que `--end` seul suffise. C'est vraisemblablement le garde-fou « spec vide →
  stop » (hérité du fix TF12, pour éviter qu'un spec no-op flippe le tour gratis à l'IA) qui mange aussi le `--end`
  explicite → ambiguïté entre « spec accidentellement vide » (stop, sûr) et « je VEUX endturn à vide » (intentionnel).
- **amélioration** : (a) quand `--end` est passé EXPLICITEMENT, jouer l'endturn même sur spec vide (le flag = intention
  claire de terminer, distinct d'un spec vide accidentel sans `--end`) ; (b) à défaut, documenter au skill/prompt que
  « passer son tour à vide » exige `act endturn` (et NON `play --no-ai --end` avec spec vide). Apparenté TF12 (garde
  « spec vide → stop ») / TF08 (no-op silencieux donne le tour à l'IA — ici l'inverse : ne flippe PAS, mais surprend).
- vu : seed 81000.
