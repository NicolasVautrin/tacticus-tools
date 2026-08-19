export const meta = {
  name: 'tacticus-selfplay',
  description: 'Self-play Tacticus oracle-vs-oracle. Par match: SETUP (build runner partage + attach B) -> PLAYERS (2 agents CHAUDS team1/team2, recon 1x puis boucle await->view->play --no-ai, coordonnes UNIQUEMENT par le host /api/selfplay/:id/await ; l\'IA native ne joue JAMAIS) -> TEARDOWN (CONFRONTATION des 2 retours = vraies + adjudication vainqueur + ecriture demos/knowledge consensus). Fan-out borne sur N matchs ; teardown SINGLE-WRITER.',
  whenToUse: 'Generer des demos self-play oracle-vs-oracle (dataset IL two-sided-expert) ET verifier le knowledge par CONSENSUS de 2 observateurs independants. Pre-requis: session Frida DEJA warmee par l\'orchestrateur. cf. docs/rl/design.md §Self-play.',
  phases: [
    { title: 'Setup',    detail: 'build runner partage + attach player B (1 agent court/match)' },
    { title: 'Match',    detail: '2 player agents CHAUDS (team1/team2) en //, recon 1x puis boucle await->view->play --no-ai ; coordonnes UNIQUEMENT par le host (jamais l\'IA native)' },
    { title: 'Teardown', detail: 'CONFRONTATION A vs B (consensus) + adjudication (vainqueur) + ecriture demos/knowledge ; SINGLE-WRITER' },
    { title: 'Cleanup',  detail: 'dispose runners orphelins (retry leaks + stragglers) + verif atelier vide' },
  ],
}

// =============================================================================
// ARGS CONTRACT
// =============================================================================
// args: {
//   matches?: Array< number | { seed:number, aiUnits?:string[] } >   // 1 entree par match
//   count?:   number        // alternative: genere `count` seeds derives (= NB DE MATCHS)
//   seedBase?: number       // base des seeds derives (defaut 80000 — distinct des waves 70000)
//   matchesInFlight?: number // matchs concurrents (defaut 2, borne [1,8] ; 8 = 16 agents = cap harness). LE PUMP FRIDA est le vrai
//                            //   plafond (tous les runners partagent 1 session) -> petit par defaut ;
//                            //   mesurer GET /api/rpc-queue pour monter.
//   sessionId?: number      // id de la session Frida warmee (defaut 1) — pour l'URL host await.
//   model?:    string       // override modele pour TOUS les agents ("sonnet"|"opus"|...) ; defaut = session.
//   ts?:       string       // timestamp de la vague (Date.now() throw dans le sandbox).
// }
//
// ARCHITECTURE (cf. docs/rl/design.md §Self-play) :
//   - Le HAND-OFF de tour est fait par le HOST (currentPlayer + long-poll /api/selfplay/:id/await),
//     PAS par le workflow ni par un relais : les 2 players se coordonnent A TRAVERS le host.
//   - Un player = UN agent() LONG (recon 1x, joue tous ses tours dans un seul contexte = CHAUD).
//   - Fidelite : A et B en contextes SEPARES, perspectives separees (decisionView perspective-scoped).
//     Le teardown (referee) voit les 2 retours mais ne passe JAMAIS d'info privee d'un camp a l'autre.
//   - Le TEARDOWN est SINGLE-WRITER (mutex JS) : les ecritures (selfplay-journal, wiki) serialisees.
//   - Vainqueur : la self-play est zero-sum -> l'adjudication se fait par CONSENSUS des outcome_perceived
//     (A dit W de SON cote + B dit L => team A gagne). Divergence -> flag (lecture autoritative = TODO).
// =============================================================================

const PLAYER_SCHEMA = {
  type: 'object',
  required: ['side', 'team', 'outcome_perceived', 'win_condition', 'turns_played'],
  properties: {
    side: { enum: ['A', 'B'] },
    team: { type: 'integer' },                                    // 1 ou 2
    outcome_perceived: { enum: ['W', 'L', 'uncertain'] },         // de MON cote : W = MA team a gagne
    turns_played: { type: 'integer' },
    roster_mine: { type: 'array', items: { type: 'string' } },
    roster_theirs: { type: 'array', items: { type: 'string' } },
    win_condition: {                                              // DERIVEE des synergies (cf. SKILL 2ter)
      type: 'object', required: ['mine', 'theirs'],
      properties: { mine: { type: 'string' }, theirs: { type: 'string' } },
    },
    threat_cards: { type: 'array', items: {                       // lecture des units ADVERSES (cross-observable)
      type: 'object', required: ['target', 'role', 'threat'],
      properties: {
        target: { type: 'string' },
        role: { enum: ['engine', 'carry', 'anvil', 'control', 'chaff'] },
        threat: { enum: ['critical', 'high', 'med', 'low'] },
        counter: { type: 'string' },
        note: { type: 'string' },
      },
    } },
    mechanics: { type: 'array', items: {                          // mecaniques OBSERVEES (surtout abilities adverses = cross-observables)
      type: 'object', required: ['ability', 'observation', 'confidence'],
      properties: {
        ability: { type: 'string' },
        observation: { type: 'string' },
        confidence: { enum: ['low', 'med', 'high'] },
        about: { enum: ['mine', 'theirs'] },                      // mecanique d'une de MES units, ou d'une unite ADVERSE (cross-observable)
      },
    } },
    synergies: { type: 'array', items: {
      type: 'object', required: ['pieces', 'effect'],
      properties: {
        pieces: { type: 'string' }, effect: { type: 'string' },
        status: { enum: ['avoided', 'chained', 'missed', 'triggered-against-me', 'na'] },
      },
    } },
    key_decisions: { type: 'array', items: { type: 'string' } },  // 2-4 decisions clefs (raisonnement DISTILLE)
    mistakes: { type: 'array', items: { type: 'string' } },       // revue adversariale (meme sur un W)
    frictions: { type: 'string' },                                // friction outil (await/play/view) — important
  },
}

// ce que le TEARDOWN a ecrit + le resultat de la CONFRONTATION
const TEARDOWN_SCHEMA = {
  type: 'object',
  required: ['seed', 'authoritative_winner', 'runner_disposed', 'files_written'],
  properties: {
    seed: { type: 'integer' },
    authoritative_winner: { type: 'string' },                    // "team1" | "team2" | "no-winner" | "uncertain"
    winner_consensus: { type: 'boolean' },                       // les 2 players sont-ils d'accord sur le vainqueur ?
    consensus_mechanics: { type: 'array', items: { type: 'string' } },  // mecaniques confirmees par LES DEUX -> wiki
    divergences: { type: 'array', items: { type: 'string' } },   // desaccords A/B (wincon, mecanique, menace, issue)
    wiki_inscribed: { type: 'array', items: { type: 'string' } },
    demos_recorded: { type: 'boolean' },
    runner_disposed: { type: 'boolean' },
    files_written: { type: 'array', items: { type: 'string' } },
    notes: { type: 'string' },
  },
}

const SETUP_SCHEMA = {
  type: 'object',
  required: ['ok'],
  properties: {
    ok: { type: 'boolean' },
    runnerId: { type: ['integer', 'string'] },
    rosterMine: { type: 'array', items: { type: 'string' } },    // team 1
    rosterTheirs: { type: 'array', items: { type: 'string' } },  // team 2
    error: { type: 'string' },
  },
}

const SQ = (x) => JSON.stringify(x)

// =============================================================================
// Validation / normalisation des args
// =============================================================================
function need(cond, msg) { if (!cond) throw new Error(`[tacticus-selfplay] args: ${msg}`) }
let A = args || {}
if (typeof A === 'string') {
  try { A = JSON.parse(A) } catch (e) { throw new Error(`[tacticus-selfplay] args: string non-JSON (${e.message})`) }
}
need(typeof A === 'object' && !Array.isArray(A), 'doit etre un objet JSON (ni string ni array)')
need(A.matches || A.count, 'fournir args.matches OU args.count')

let matches = (A.matches || []).map((s) => (typeof s === 'number' ? { seed: s } : s))
if (matches.length === 0 && A.count) {
  const base = A.seedBase || 80000
  matches = Array.from({ length: A.count }, (_, i) => ({ seed: base + i }))
}
need(matches.length > 0, 'aucun match a lancer')
need(matches.every((m) => Number.isInteger(m.seed)), 'chaque match a besoin d\'un seed entier')

const sessionId = Number.isInteger(A.sessionId) ? A.sessionId : 1
const model = A.model || undefined
// Borne [1,8] : 8 matchs en vol = 8×2 players = 16 agents au pic = EXACTEMENT le cap
// de concurrence harness (min(16, max(2, coeurs-2))). 8 = plafond naturel (sature le cap
// sans rien mettre en queue) ; au-delà (9+), les players excédentaires queueraient au cap.
const MATCHES_INFLIGHT = Math.max(1, Math.min(8, Number.isInteger(A.matchesInFlight) ? A.matchesInFlight : 2))
const ts = A.ts || 'inconnu'

log(`args OK: ${matches.length} matchs self-play - ${MATCHES_INFLIGHT} en vol - sessionId=${sessionId}${model ? ` - modele=${model}` : ''}`)
log('hand-off = HOST (/api/selfplay/:id/await) ; players CHAUDS ; teardown SINGLE-WRITER (confrontation A/B)')

// =============================================================================
// Mutex single-writer pour le teardown (les ecritures fichiers se serialisent)
// =============================================================================
let writerChain = Promise.resolve()
function serializeWrite(fn) {
  const r = writerChain.then(fn, fn)        // s'execute apres le precedent, qu'il ait reussi ou non
  writerChain = r.then(() => {}, () => {})  // la chaine continue quoi qu'il arrive
  return r
}

// =============================================================================
// Prompts
// =============================================================================
const GC_HELP =
  `OUTIL gameconfig.py = VÉRITÉ du jeu (chiffres gameconfig + texte de règles i2). Usage EXACT :
     - python scripts/python/gameconfig.py <unitId|nom>  -> KIT COMPLET d'une unité en 1 SEUL appel.
     - python scripts/python/gameconfig.py --ability <Nom> / --effect <Nom> / --trait <Nom>.
     TOLÉRANT AU MODE (résout dans une autre catégorie + te dit laquelle). NE fouille JAMAIS data/*.json
     à la main, NE DEVINE JAMAIS de noms au hasard. Introuvable partout = mauvais nom -> ARRÊTE de chercher.`

const SIDES = {
  A: { team: 1, pid: 3, other: 2 },
  B: { team: 2, pid: 4, other: 1 },
}

function setupPrompt(m) {
  const aiCsv = m.aiUnits ? m.aiUnits.map((u) => String(u).split(':')[0]).join(',') : null
  const buildCmd = `python scripts/python/rl_duel.py build --seed ${m.seed} --board MC1_67 --state-file logs/runners/_sp_${m.seed}_A.json${aiCsv ? ` --a-units ${aiCsv}` : ''}`
  return `Tu es l'agent SETUP d'UN match self-play Tacticus (seed ${m.seed}). cwd = racine du repo.
   PRECONDITION: session Frida (id=${sessionId}) DEJA warmee par l'orchestrateur -> NE lance JAMAIS autoBootExtraire, NE navigue PAS l'UI.
   ⚠ INVARIANT (matchs concurrents) : la coexistence est le DÉFAUT côté hooks — un build ne détruit JAMAIS les runners frères, mais un cap dur (MAX_RUNNERS) fait REFUSER le build si l'atelier est plein. DONC : lance EXCLUSIVEMENT la commande build ci-dessous (son --state-file DÉDIÉ garantit que le retry remplace TON runner, pas un frère), JAMAIS un build ad-hoc avec un autre state-file, et NE lance JAMAIS \`dispose\` (réservé au teardown). Si le build échoue avec "runner cap reached" -> renvoie {ok:false, error:"cap runners atteint"} (l'orchestrateur/cleanup arbitre, ce n'est PAS à toi de disposer). Si tu dois ré-essayer, relance EXACTEMENT la même commande.
   1. BUILD le runner PARTAGE (team1=joueur, team2=adverse) : \`${buildCmd}\`. Lis le runnerId dans la ligne "[build] runnerId=N" et les 2 rosters ("MON roster (team 1)=..." / "roster ADVERSE (team 2)=...").
   2. CREE le state-file du player B (MEME runner, camp 2) : \`python scripts/python/rl_duel.py attach --from logs/runners/_sp_${m.seed}_A.json --team 2 --state-file logs/runners/_sp_${m.seed}_B.json\`.
   3. GATE D'ADRESSABILITÉ (OBLIGATOIRE avant de rendre ok) — vérifie que le runner est joignable par LE MÊME chemin que les players (l'endpoint await), pour attraper un runner nuké par un build concurrent AVANT de spawn 2 players dessus : \`curl -s -m 10 "http://127.0.0.1:8765/api/selfplay/${sessionId}/await?runnerId=<N>&player=3&timeoutMs=3000"\` (remplace <N> par le runnerId du build). VERDICT : réponse JSON avec \`"ok":true\` (\`yourTurn\` OU \`timedOut\`) = runner ADRESSABLE -> rends ok. Réponse avec \`"error"\` (ex. "runner <N> not found", HTTP 502) = runner ABSENT du registry -> NE rends PAS ok:true : renvoie {ok:false, error:"runner <N> non adressable post-build"} pour que le workflow RE-SETUP (le retry rebuild est non destructif pour les frères : coexistence par défaut, replace scoped à TON state-file).
   NE joue PAS le match, NE dispose PAS le runner (c'est le role des players / du teardown).
   Renvoie {ok:true, runnerId:<N>, rosterMine:[team1...], rosterTheirs:[team2...]} UNIQUEMENT si la gate (3) passe. Si le build echoue OU la gate echoue -> {ok:false, error:"..."}.`
}

function playerPrompt(side, runnerId, m, setup) {
  const s = SIDES[side]
  const sf = `logs/runners/_sp_${m.seed}_${side}.json`
  const url = `http://127.0.0.1:8765/api/selfplay/${sessionId}/await?runnerId=${runnerId}&player=${s.pid}&timeoutMs=90000`
  return `Tu es le PLAYER ${side} (équipe ${s.team}, player id ${s.pid}) d'un match SELF-PLAY Tacticus (seed ${m.seed}, oracle vs oracle). Tu joues UNIQUEMENT l'équipe ${s.team}. L'adversaire (équipe ${s.other}) est joué par un AUTRE agent en parallèle — tu ne le vois jamais, tu n'as que TA perspective via decisionView. cwd = racine du repo.
   PRECONDITION (NE PAS y toucher) : session Frida id=${sessionId} DEJA warmee, runner runnerId=${runnerId} DEJA construit. NE lance JAMAIS autoBootExtraire, NE build PAS, NE navigue PAS l'UI, NE dispose PAS le runner. Toutes tes commandes rl_duel utilisent --state-file ${sf}.
   RESSOURCES :
   - Carte/état : \`python scripts/python/rl_duel.py view --state-file ${sf}\` — la section "MES ACTIFS" affiche pour CHAQUE actif sa légalité now/+move (now[..] = castable SANS bouger ; +move[..] = seulement après déplacement ; ∅ = no-op certain), Y COMPRIS les abilities NON-attaque (buff/heal/summon/hex) absentes des PLANS D'ATTAQUE. Les MoW affichent aussi leurs cibles.
   - Jouer ton tour : \`python scripts/python/rl_duel.py play --no-ai --spec '<JSON>' --state-file ${sf}\`
   - Tuiles de MOVE légales (par unité) : \`python scripts/python/rl_duel.py moves [--unit <id>] --state-file ${sf}\` — grille ASCII des tuiles atteignables (la carte \`view\` ne donne que les plans d'ATTAQUE, PAS le set de repositionnement résolu).
   - Cibles LÉGALES par ability (détail) : \`python scripts/python/rl_duel.py abilities [--unit <id>] [--ability <N>] --state-file ${sf}\` — l'analogue de \`moves\` pour les abilities : par (unité × ability) les cibles now/+move. À utiliser pour une ability NON-attaque (buff/heal/summon/hex) ou pour vérifier qu'un cast passe SANS bouger.
   - Pourquoi un cast échoue (raison structurée) : \`python scripts/python/rl_duel.py reason --caster <id> --ability <N> [--target <id>] --state-file ${sf}\` — flag TargetingRule exact (TargetIsInRange / TargetIsTargetable / AlreadyUseThisTurn / NoBroken=valide…).
   - Hand-off (attendre ton tour) : \`curl -s -m 120 "${url}"\` (le \`-m\` client EST > le timeout serveur 90s pour ne PAS le racer ; un curl exit-28 / sortie VIDE = le wrapper a coupé AVANT le serveur = TRANSITOIRE → RE-ÉMETS, ce n'est PAS un échec).

   RECON (UNE SEULE FOIS, au début — NE re-lis PAS à chaque tour) :
   1. Lis docs/rl/wiki.md (kits + cartes Tac + synergies §5bis) + .claude/skills/tacticus-battle/SKILL.md (§6/§7) + .claude/skills/tacticus-battle/doctrine-learned.md.
   2. Recon gameconfig→wiki de CHAQUE unité des DEUX camps. ${GC_HELP}
   3. Dérive MA wincon (meilleure synergie/engine + enabler à protéger) et LEUR wincon (engine adverse → la couper à la source).

   ⏱ TEMPO / HORLOGE DURE (ANTI-STANDOFF — lis docs/rl/wiki.md §EnvEndBombardment) : le combat a un ROUND-CAP CONNU. \`rl_duel view\` affiche en tête une ligne **⏱ HORLOGE round-cap** (cap lu du BC = round 8 ≈ tes 8 premiers tours) si ce combat a l'EnvEndBombardment : au cap, un bombardement AoE board-wide WIPE LES DEUX camps → no-winner. À ~2 tours de la fin une 2ᵉ ligne **⏱ [ROUND-CAP] fire dans N tour(s)** (effet \`EnvEndBombardment_Incoming\`) s'arme = ALARME FINALE, déjà trop tard pour planifier une clôture. ⚠ Le cap = round 8 (≈ tes 8 tours), PAS « round 10 » : sois en CLÔTURE pour ton ~6ᵉ tour. ⚠ L'adversaire est un oracle AUSSI prudent que toi : si tu attends qu'IL s'engage, il attend pareil → double-turtle → vous êtes wipe tous les deux. UN NO-WINNER ROUND-CAP N'EST PAS UN NUL ACCEPTABLE : c'est une DOUBLE-DÉFAITE (échec de conversion) — un oracle DOIT clore. DONC, par défaut, joue pour FORCER une décision AVANT le cap : ouvre l'engagement TÔT, concentre le feu pour TUER (clôture cohésive, ne grignote pas en attrition basse-PV), commence à grind les anvils/Resilient lents dès ton ~5ᵉ tour. Ne JAMAIS over-hold en espérant que l'autre commit le premier. Dès que la ligne ⏱ [ROUND-CAP] apparaît en EFFETS CRITIQUES (N tour(s) restant(s)) : tu es à court de temps → engage tes MEILLEURS trades MAINTENANT, l'avance numérique ne sauve PAS du cap. (La seule raison de temporiser = un avantage de tempo CONCRET et NOMMÉ — buff qui arme un burst le tour suivant, ennemi qui doit s'exposer — pas « j'attends de voir ».)

   BOUCLE DE JEU (au plus 15 de TES tours) :
    a. UN await (curl ci-dessus). Lis le JSON :
       - "gameOver":true -> battle FINIE -> SORS de la boucle (RAPPORT).
       - "timedOut":true (avec OU sans "transientError") -> pas encore ton tour (l'adversaire réfléchit ; un \`transientError\` = un poll interne a timeout pendant le pump = TOUJOURS transitoire, jamais un fail) -> RE-ÉMETS l'await. Idem si le curl exit non-zéro / sortie vide -> transitoire -> RE-ÉMETS (n'arrête PAS, ce n'est PAS une fin de partie).
       - "yourTurn":true -> joue (b-d).
    b. \`rl_duel view --state-file ${sf}\` : tes units = CTRL/MAJUSCULE ; ennemis = minuscule ; plans d'attaque [min-max, K!/K?] ; ⚠ effets critiques ; effets actifs par unité.
    c. Planifie le tour COMPLET de TOUTES tes units (moves + abilities + finishs) selon la doctrine : tuer la wincon adverse ATTEIGNABLE — PROACTIVEMENT (cf. ⏱ TEMPO : n'attends PAS que l'adversaire s'engage le premier ; chaque tour passé sans pression rapproche le no-winner), ne pas sur-étendre une fragile, séquencer buff→frappe. PAS de move-guard (self-play v1). Pour un MOVE de REPOSITIONNEMENT (sans attaque), lance d'abord \`moves\` et choisis une tuile LÉGALE (un move hors movable set est rejeté avant l'endturn — ne devine pas la reachability à la main, elle est creusée par les blockers/terrain). LÉGALITÉ DES ABILITIES — ne devine pas la portée : "MES ACTIFS" de \`view\` (ou \`abilities\`) donne par actif now[..] (castable SANS bouger) / +move[..] (après déplacement) / ∅ (no-op certain), Y COMPRIS les abilities NON-attaque (buff/heal/summon/hex, absentes des PLANS D'ATTAQUE) et les MoW → cible ∈now = caste maintenant ; ∈+move seul = bouge d'abord ; ∉ des deux = n'essaie pas. Un cast ciblé illégal est rejeté avant l'endturn avec la raison exacte (TargetIsInRange / TargetIsTargetable / …).
    d. FIN DE TOUR : le JEU termine ton tour AUTOMATIQUEMENT dès que TOUTES tes units ont agi (jouées ou \`{"kind":"finish","unit":<id>}\`) — \`play --no-ai\` ne force RIEN. Si ton spec est PARTIEL, le tour CONTINUE (play affiche « il reste [ids] ») → relance \`play --no-ai\` avec le reste : tu peux SPLITTER sans risque, aucune activation perdue (c'était LE bug de la v2, corrigé). Si tu juges ton tour FINI alors que des units pourraient encore agir (réserve délibérée — ex. garder une unité hors de portée), termine EXPLICITEMENT : \`play --no-ai --end --spec '[...]'\` (applique + finit) ou \`act endturn\`. Le passage de main à l'adversaire se fait au flip de currentPlayer (auto ou via --end). FORMATS : move {"kind":"move","unit":<id>,"to":[col,row]} ('to'=ARRAY [col,row]) ; ability {"kind":"ability","caster":<id>,"target":<id>[,"ability":N]} ; finish {"kind":"finish","unit":<id>}. Si "TOUR ABANDONNÉ" (action ratée/format) : les actions AVANT l'échec sont conservées et l'endturn n'a PAS eu lieu -> CORRIGE l'action fautive et relance \`play --no-ai\` avec le RESTE des actions (la fin du spec). play --no-ai passe la main sans tour IA — NORMAL. ⚠ APPLIED-BUT-SLOW : si un \`play --no-ai\` TIMEOUT sur la RÉPONSE (curl/urllib timeout, pas de confirmation), l'action a PEUT-ÊTRE DÉJÀ été appliquée → vérifie \`status\`/\`view\` AVANT de re-jouer la MÊME action (ne la double-apply PAS — un timeout de réponse ≠ un échec).
    e. Retourne en (a) pour attendre ton prochain tour.

   IMPORTANT : tu ne joues QUE sur yourTurn. "timedOut" n'est PAS une fin de partie. Pas d'abandon en self-play : la partie va à son terme (mort d'un camp ou round-cap), joue pour gagner — et un no-winner round-cap = DOUBLE-DÉFAITE, pas un nul : joue pour CLORE avant le cap (cf. ⏱ TEMPO).

   RETOUR STRUCTURE (PLAYER_SCHEMA) — n'écris AUCUN fichier (le teardown écrit) :
   - side="${side}", team=${s.team}, turns_played, outcome_perceived (de MON côté : W=MA team a gagné / L / uncertain d'après le dernier état).
   - win_condition {mine, theirs} = NOMME la synergie/engine dominante de chaque camp + sa SOURCE (cf. SKILL 2ter), pas juste l'unité. (Ces lectures seront CONFRONTÉES à celles de l'adversaire.)
   - threat_cards = les units ADVERSES (role/menace/counter) — TA lecture (sera croisée avec l'auto-éval adverse).
   - mechanics = mécaniques notables observées, avec about="mine"|"theirs" (les "theirs" = abilities adverses, cross-observables = précieuses pour le consensus).
   - synergies, key_decisions (2-4, ton raisonnement distillé), mistakes (revue adversariale même sur un W), frictions (tout outil await/play/view qui a mal réagi).`
}

function teardownPrompt(m, runnerId, pa, pb) {
  return `Tu es l'agent TEARDOWN d'UN match self-play Tacticus (seed ${m.seed}). Tu es SINGLE-WRITER (aucun autre agent n'écrit en parallèle à cet instant — pas de mutex à gérer, mais LIS l'état courant des fichiers avant d'éditer). cwd = racine du repo.
   Entrées — les 2 retours des players (contextes SÉPARÉS, perspectives OPPOSÉES sur le MÊME match) :
   - PLAYER A (team 1, player 3) : ${SQ(pa)}
   - PLAYER B (team 2, player 4) : ${SQ(pb)}
   (un retour peut être null si le player a échoué — note-le et adjuge avec ce que tu as.)

   1. ADJUDICATION (vainqueur). La self-play est ZERO-SUM. SOURCE AUTORITATIVE = \`python scripts/python/rl_duel.py status --state-file logs/runners/_sp_${m.seed}_A.json\` qui imprime désormais \`*** BATTLE FINIE — winner AUTORITATIF = team1|team2|no-winner ***\` (champ NATIF battleStatus.winner, lisible post-Finished — H59). ⚠ NE te fie PAS à \`alive_by_team={}\` post-Finished : decisionView refuse hors-Running donc il est VIDE — IDENTIQUE pour une élimination ET un no-winner round-cap (c'était le piège H59). authoritative_winner = EXACTEMENT ce que cette ligne reporte. Recoupe avec outcome_perceived des 2 players (A="W"&B="L"→team1 ; A="L"&B="W"→team2 ; mutual "L"/ "uncertain"→souvent no-winner) : winner_consensus = true si A et B s'accordent ET que ça MATCHE le winner autoritatif (sinon flag la divergence).

   2. CONFRONTATION A vs B = vérif INDÉPENDANTE par consensus (2 observateurs séparés du même match). Compare :
      - win-condition : A.win_condition.theirs (lecture de B par A) vs B.win_condition.mine (auto-lecture de B) ; et A.mine vs B.theirs. Accord = haute confiance. Divergence = un des deux a mal lu -> divergences[].
      - mechanics : les entrées about="theirs" sont CROSS-OBSERVABLES (A voit les abilities de B, et inversement). Une mécanique rapportée par LES DEUX (concordante) = CONSENSUS -> consensus_mechanics[]. Rapportée par un seul = candidate. Contradictoire entre A et B -> divergences[].
      - threat_cards / menaces : croise la lecture de chaque camp avec l'auto-éval adverse.
      Pour les mécaniques de consensus, recoupe quand même la RÈGLE DISCRÈTE avec gameconfig/i2 si tu as un doute (le consensus est un PRIOR fort, PAS la vérité — les 2 peuvent se tromper pareil). ${GC_HELP}

   3. ÉCRITURE (demos + knowledge) :
      a. DEMOS : append un bloc match à docs/rl/selfplay-journal.md (CRÉE le fichier s'il n'existe pas, avec un titre "# Self-play journal (oracle vs oracle) — demos + confrontation"). Bloc = "## seed ${m.seed} — winner=<...> (ts=${ts})" + rosters + win_condition consensus (mine/theirs) + key_decisions des 2 + le résultat de la CONFRONTATION (consensus vs divergences). Source TAGGÉE self-play (NE mélange PAS avec docs/rl/journal.md qui est la pipeline oracle-vs-IA). Le détail des coups (action_log) est ARCHIVÉ en 4 (la trajectoire = le dataset IL, dans logs/selfplay/sp_${m.seed}_<ts>.json) — référence ce chemin ; résume AUSSI les séquences clés ici pour la lecture humaine.
      b. KNOWLEDGE CONSENSUS : pour chaque mécanique de consensus_mechanics (confirmée par LES DEUX players), inscris-la dans docs/rl/wiki.md (bonne unité/section) avec un tag [self-play consensus, seed ${m.seed}]. RIEN au wiki sans consensus (ou recoupage gameconfig explicite). Les divergences -> docs/rl/hypotheses.md en candidat flaggé "(self-play divergence A/B)".
         ⚠ DISCIPLINE "THIN OVERLAY" (le wiki = SEULEMENT le NON-déductible de gameconfig) : une entrée wiki = l'INSIGHT non-déductible (interaction trait×trait, quirk émergent, condition de snowball, doctrine actionnable, counter) + un POINTEUR vers gameconfig pour la règle/les chiffres — JAMAIS un restatement. INTERDIT : recopier du "gameconfig VERBATIM" (la règle/les nombres sont DANS gameconfig → cite "cf. gameconfig --ability/--trait/--effect <Nom>", ne duplique pas) ; mettre des chiffres SPÉCIFIQUES AU MATCH (HP transitions type 8536→1770, dmg exacts, play-by-play) — ceux-là vont au JOURNAL/archive (preuve + trajectoire), pas au wiki durable. Le recoup gameconfig sert à VÉRIFIER avant d'inscrire, PAS à copier dans le wiki. Vise 2-4 lignes d'insight par entrée, pas un dump. Si la "mécanique" est entièrement déductible de gameconfig (pas d'interaction/quirk/doctrine émergente) → NE l'inscris PAS (elle est déjà dans gameconfig).
      c. BACKLOG OUTILLAGE (NE PAS oublier) : si un player a rapporté une friction outil (champ \`frictions\`, OU un "TOUR ABANDONNÉ"/cast illégal/label trompeur/POV-flip dans ses key_decisions/mistakes), METS À JOUR docs/rl/toolfeedback.md (LIS-le d'abord). Pour CHAQUE friction : (i) cherche un TF EXISTANT au même symptôme → si trouvé, **incrémente son \`recurrence\`** dans le header, **ajoute la seed à \`vu\`**, et append une ligne d'evidence "**n+1 (seed ${m.seed})** : <observé>" ; (ii) sinon **CRÉE** \`## TF<NN>\` (prochain numéro libre) — \`— open — recurrence:1\` + sous-champs **friction** / **amélioration** / **vu : seed ${m.seed}**. NE duplique PAS un TF déjà présent. Une friction outil ne va NI au wiki (knowledge de JEU only) NI aux hypotheses (mécaniques de jeu only) — son canal dédié est toolfeedback.md.
      NE modifie JAMAIS .claude/skills/tacticus-battle/SKILL.md. NE touche PAS aux métriques win-rate de loop.md (le W/L self-play est zero-sum, non comparable au win-rate oracle-vs-IA).

   4. ARCHIVE + CLEANUP (dans CET ordre — l'archive AVANT toute suppression) :
      a. ARCHIVE la trajectoire (= le dataset IL ; IMPÉRATIF avant le rm) : \`python scripts/python/archive_demo.py --a logs/runners/_sp_${m.seed}_A.json --b logs/runners/_sp_${m.seed}_B.json --ts '${ts}' --winner <authoritative_winner>\` → écrit logs/selfplay/sp_${m.seed}_<ts>.json (action_logs des 2 camps + rosters + outcome, rejouable via seed). Mets le chemin imprimé dans files_written.
      b. DISPOSE le runner : \`python scripts/python/rl_duel.py dispose --state-file logs/runners/_sp_${m.seed}_A.json\` (libère le runner ${runnerId}). runner_disposed=true si OK.
      c. SUPPRIME les 2 state-files : \`rm logs/runners/_sp_${m.seed}_A.json logs/runners/_sp_${m.seed}_B.json\` (UNIQUEMENT après a+b réussis).

   Renvoie le résumé structuré (TEARDOWN_SCHEMA) : seed, authoritative_winner, winner_consensus, consensus_mechanics, divergences, wiki_inscribed, demos_recorded, runner_disposed, files_written, notes.`
}

// =============================================================================
// Pipeline par match : SETUP -> PLAYERS (//) -> TEARDOWN (single-writer)
// =============================================================================
// RÉSILIENCE 529 : agent() a un budget de retry BORNÉ -> sous surcharge soutenue il
// surface un échec dur (null). On ré-essaie AU NIVEAU WORKFLOW : le setup (qui ne
// construit RIEN s'il échoue -> 0 fuite, retry gratuit) et le MATCH entier si un player
// meurt (le runner précédent fuit -> tracké/disposé après ; les state-files sont réécrits
// par le setup suivant). Les retries cumulés = fenêtre de retry étendue -> encaisse une
// surcharge FINIE. (Une surcharge longue échouera quand même après MATCH_TRIES.)
const SETUP_TRIES = 4
const MATCH_TRIES = 3

async function playMatch(m) {
  const leaked = []
  for (let att = 1; att <= MATCH_TRIES; att++) {
    // --- SETUP avec retry (absorbe un 529 transitoire sur l'agent court) ---
    let setup = null
    for (let s = 1; s <= SETUP_TRIES; s++) {
      const sLabel = `setup:${m.seed}${att > 1 || s > 1 ? ` (a${att}.${s})` : ''}`
      setup = await agent(setupPrompt(m), { label: sLabel, phase: 'Setup', model, schema: SETUP_SCHEMA })
      if (setup && setup.ok !== false && setup.runnerId != null) break
      setup = null
    }
    if (!setup) { log(`match ${m.seed}: SETUP KO apres ${SETUP_TRIES} essais (tentative ${att}/${MATCH_TRIES}) -> 529 soutenu ?`); continue }
    const R = setup.runnerId
    log(`match ${m.seed}: runner ${R} pret -> 2 players (tentative ${att}/${MATCH_TRIES})`)
    const [pa, pb] = await parallel([
      () => agent(playerPrompt('A', R, m, setup),
        { label: `player:${m.seed}:A${att > 1 ? ` #${att}` : ''}`, phase: 'Match', model, schema: PLAYER_SCHEMA }),
      () => agent(playerPrompt('B', R, m, setup),
        { label: `player:${m.seed}:B${att > 1 ? ` #${att}` : ''}`, phase: 'Match', model, schema: PLAYER_SCHEMA }),
    ])
    if (!pa || !pb) {
      // un player mort (529 -> null) : match à 1 camp = invalide -> rejoue TOUT le match.
      leaked.push(R)
      log(`match ${m.seed}: player KO (A=${pa ? 'ok' : 'NULL'} B=${pb ? 'ok' : 'NULL'}) tentative ${att}/${MATCH_TRIES} -> RETRY match (runner ${R} laissé, à disposer ; state-files réécrits au prochain setup)`)
      continue
    }
    // --- les 2 players OK -> TEARDOWN single-writer (confrontation + adjudication + écriture) ---
    const td = await serializeWrite(() => agent(teardownPrompt(m, R, pa, pb),
      { label: `teardown:${m.seed}`, phase: 'Teardown', agentType: 'general-purpose', model, schema: TEARDOWN_SCHEMA }))
      .catch(() => null)
    if (td) {
      log(`match ${m.seed}: winner=${td.authoritative_winner}`
        + `${td.winner_consensus === false ? ' (PAS de consensus)' : ''}`
        + `${(td.divergences || []).length ? ` - ${td.divergences.length} divergence(s)` : ''}`
        + `${(td.consensus_mechanics || []).length ? ` - ${td.consensus_mechanics.length} mecanique(s) consensus` : ''}`
        + `${td.runner_disposed === false ? ' - runner NON dispose (fuite!)' : ''}`)
      return { seed: m.seed, ...td, retries_leaked: leaked }
    }
    log(`match ${m.seed}: TEARDOWN echec (ecriture perdue, runner ${R} peut-etre non dispose)`)
    return { seed: m.seed, authoritative_winner: 'uncertain', runner_disposed: false, retries_leaked: [...leaked, R], files_written: [] }
  }
  log(`match ${m.seed}: ECHEC apres ${MATCH_TRIES} tentatives (surcharge API soutenue ?) - runners laissés: ${leaked.join(',') || 'aucun'}`)
  return leaked.length ? { seed: m.seed, authoritative_winner: 'failed', runner_disposed: false, retries_leaked: leaked, files_written: [] } : null
}

// =============================================================================
// Fan-out borne sur les matchs (matchesInFlight concurrents ; le PUMP est le vrai plafond)
// =============================================================================
async function boundedPool(items, limit, fn) {
  const out = new Array(items.length)
  let i = 0
  async function worker() {
    while (i < items.length) {
      const k = i++
      out[k] = await fn(items[k], k)
    }
  }
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker))
  return out
}

const results = await boundedPool(matches, MATCHES_INFLIGHT, playMatch)

// =============================================================================
// Roll-up final
// =============================================================================
const all = results.filter(Boolean)
const done = all.filter((r) => r.authoritative_winner !== 'failed')   // teardown réel (≠ abandon 529)
const failed = all.filter((r) => r.authoritative_winner === 'failed').map((r) => r.seed)
// runner IDs laissés par les retries (529) OU un teardown non disposé -> à disposer après run.
const leakedRunners = [...new Set(all.flatMap((r) => r.retries_leaked || []))]
const rollup = {
  attempted: matches.length,
  completed: done.length,
  failed_seeds: failed,                                              // matchs abandonnés (529 soutenu)
  winners: done.map((r) => ({ seed: r.seed, winner: r.authoritative_winner, consensus: r.winner_consensus !== false })),
  divergences_total: done.reduce((n, r) => n + ((r.divergences || []).length), 0),
  consensus_mechanics_total: done.reduce((n, r) => n + ((r.consensus_mechanics || []).length), 0),
  wiki_inscribed: [...new Set(done.flatMap((r) => r.wiki_inscribed || []))],
  files_written: [...new Set(done.flatMap((r) => r.files_written || []))],
  runners_leaked: leakedRunners,                                     // runner IDs à disposer (cf. rl_duel dispose / host)
}
log(`self-play fini: ${done.length}/${matches.length} matchs aboutis`
  + ` - ${rollup.consensus_mechanics_total} mecanique(s) consensus, ${rollup.divergences_total} divergence(s) A/B`
  + (failed.length ? ` - ${failed.length} ECHEC(s) 529: seeds ${failed.join(',')}` : '')
  + (leakedRunners.length ? ` - runners a disposer: ${leakedRunners.join(',')}` : ''))

// =============================================================================
// Cleanup final — coexistence par défaut : un build NE balaie JAMAIS les
// stragglers (et le cap MAX_RUNNERS refuse les builds si l'atelier est plein),
// donc on dispose EXPLICITEMENT tout runner restant : les leaks de retry
// (trackés) ET tout straggler non tracké (ex. gate-fail rebuild). Garantit un
// atelier vide quel que soit le déroulé. cf. project_multirunner_coexistence.
// =============================================================================
phase('Cleanup')
const cleanup = await agent(
  `Tu es l'agent CLEANUP du run self-play. Session Frida id=${sessionId}. Objectif : atelier VIDE (aucun runner orphelin). cwd = racine du repo.
   1. Dispose ces runners orphelins connus (retry leaks) : [${leakedRunners.join(', ') || 'aucun'}].
   2. LISTE l'atelier : \`curl -s -X POST http://127.0.0.1:8765/api/scripts/${sessionId}/rpc -H "Content-Type: application/json" -d '{"method":"listRunners","args":[],"timeout":10000}'\`.
   3. Pour CHAQUE runnerId encore présent (étape 1 + étape 2), dispose-le : \`curl -s -X POST http://127.0.0.1:8765/api/scripts/${sessionId}/rpc -H "Content-Type: application/json" -d '{"method":"disposeRunner","args":[{"runnerId":<N>}],"timeout":15000}'\` (remplace <N>).
   4. RE-LISTE (listRunners) pour CONFIRMER que l'atelier est vide. NE build RIEN, NE amorce PAS, NE navigue PAS l'UI.
   Renvoie {disposed:[...ids effectivement libérés...], remaining:[...ids encore présents après cleanup...]}.`,
  { label: 'cleanup', phase: 'Cleanup', model, agentType: 'general-purpose',
    schema: { type: 'object', required: ['disposed', 'remaining'], properties: {
      disposed: { type: 'array', items: { type: 'integer' } },
      remaining: { type: 'array', items: { type: 'integer' } } } } },
).catch(() => null)
if (cleanup) {
  rollup.cleanup = cleanup
  log(`cleanup: ${(cleanup.disposed || []).length} disposé(s)`
    + (cleanup.remaining && cleanup.remaining.length ? ` - ${cleanup.remaining.length} ENCORE présent(s): ${cleanup.remaining.join(',')} (à disposer à la main)` : ' - atelier vide ✓'))
} else {
  log('cleanup: agent KO -> vérifier listRunners à la main')
}
return rollup
