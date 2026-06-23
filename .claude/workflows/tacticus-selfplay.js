export const meta = {
  name: 'tacticus-selfplay',
  description: 'Self-play Tacticus oracle-vs-oracle. Par match: SETUP (build runner partage + attach B) -> PLAYERS (2 agents CHAUDS team1/team2, recon 1x puis boucle await->view->play --no-ai, coordonnes UNIQUEMENT par le host /api/selfplay/:id/await ; l\'IA native ne joue JAMAIS) -> TEARDOWN (CONFRONTATION des 2 retours = vraies + adjudication vainqueur + ecriture demos/knowledge consensus). Fan-out borne sur N matchs ; teardown SINGLE-WRITER.',
  whenToUse: 'Generer des demos self-play oracle-vs-oracle (dataset IL two-sided-expert) ET verifier le knowledge par CONSENSUS de 2 observateurs independants. Pre-requis: session Frida DEJA warmee par l\'orchestrateur. cf. docs/rl/design.md §Self-play.',
  phases: [
    { title: 'Setup',    detail: 'build runner partage + attach player B (1 agent court/match)' },
    { title: 'Match',    detail: '2 player agents CHAUDS (team1/team2) en //, recon 1x puis boucle await->view->play --no-ai ; coordonnes UNIQUEMENT par le host (jamais l\'IA native)' },
    { title: 'Teardown', detail: 'CONFRONTATION A vs B (consensus) + adjudication (vainqueur) + ecriture demos/knowledge ; SINGLE-WRITER' },
  ],
}

// =============================================================================
// ARGS CONTRACT
// =============================================================================
// args: {
//   matches?: Array< number | { seed:number, aiUnits?:string[] } >   // 1 entree par match
//   count?:   number        // alternative: genere `count` seeds derives (= NB DE MATCHS)
//   seedBase?: number       // base des seeds derives (defaut 80000 — distinct des waves 70000)
//   matchesInFlight?: number // matchs concurrents (defaut 2, borne [1,6]). LE PUMP FRIDA est le vrai
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
const MATCHES_INFLIGHT = Math.max(1, Math.min(6, Number.isInteger(A.matchesInFlight) ? A.matchesInFlight : 2))
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
  const buildCmd = `python scripts/python/rl_duel.py build --seed ${m.seed} --keep --state-file data/_sp_${m.seed}_A.json${aiCsv ? ` --a-units ${aiCsv}` : ''}`
  return `Tu es l'agent SETUP d'UN match self-play Tacticus (seed ${m.seed}). cwd = racine du repo.
   PRECONDITION: session Frida (id=${sessionId}) DEJA warmee par l'orchestrateur -> NE lance JAMAIS warmupGameSingletons, NE navigue PAS l'UI.
   1. BUILD le runner PARTAGE (team1=joueur, team2=adverse) : \`${buildCmd}\`. Lis le runnerId dans la ligne "[build] runnerId=N" et les 2 rosters ("MON roster (team 1)=..." / "roster ADVERSE (team 2)=...").
   2. CREE le state-file du player B (MEME runner, camp 2) : \`python scripts/python/rl_duel.py attach --from data/_sp_${m.seed}_A.json --team 2 --state-file data/_sp_${m.seed}_B.json\`.
   NE joue PAS le match, NE dispose PAS le runner (c'est le role des players / du teardown).
   Renvoie {ok:true, runnerId:<N>, rosterMine:[team1...], rosterTheirs:[team2...]}. Si le build echoue -> {ok:false, error:"..."}.`
}

function playerPrompt(side, runnerId, m, setup) {
  const s = SIDES[side]
  const sf = `data/_sp_${m.seed}_${side}.json`
  const url = `http://127.0.0.1:8765/api/selfplay/${sessionId}/await?runnerId=${runnerId}&player=${s.pid}&timeoutMs=90000`
  return `Tu es le PLAYER ${side} (équipe ${s.team}, player id ${s.pid}) d'un match SELF-PLAY Tacticus (seed ${m.seed}, oracle vs oracle). Tu joues UNIQUEMENT l'équipe ${s.team}. L'adversaire (équipe ${s.other}) est joué par un AUTRE agent en parallèle — tu ne le vois jamais, tu n'as que TA perspective via decisionView. cwd = racine du repo.
   PRECONDITION (NE PAS y toucher) : session Frida id=${sessionId} DEJA warmee, runner runnerId=${runnerId} DEJA construit. NE lance JAMAIS warmupGameSingletons, NE build PAS, NE navigue PAS l'UI, NE dispose PAS le runner. Toutes tes commandes rl_duel utilisent --state-file ${sf}.
   RESSOURCES :
   - Carte/état : \`python scripts/python/rl_duel.py view --state-file ${sf}\`
   - Jouer ton tour : \`python scripts/python/rl_duel.py play --no-ai --spec '<JSON>' --state-file ${sf}\`
   - Tuiles de MOVE légales (par unité) : \`python scripts/python/rl_duel.py moves [--unit <id>] --state-file ${sf}\` — grille ASCII des tuiles atteignables (la carte \`view\` ne donne que les plans d'ATTAQUE, PAS le set de repositionnement résolu).
   - Hand-off (attendre ton tour) : \`curl -s -m 100 "${url}"\`

   RECON (UNE SEULE FOIS, au début — NE re-lis PAS à chaque tour) :
   1. Lis docs/rl/wiki.md (kits + cartes Tac + synergies §5bis) + .claude/skills/tacticus-battle/SKILL.md (§6/§7) + .claude/skills/tacticus-battle/doctrine-learned.md.
   2. Recon gameconfig→wiki de CHAQUE unité des DEUX camps. ${GC_HELP}
   3. Dérive MA wincon (meilleure synergie/engine + enabler à protéger) et LEUR wincon (engine adverse → la couper à la source).

   BOUCLE DE JEU (au plus 15 de TES tours) :
    a. UN await (curl ci-dessus). Lis le JSON :
       - "gameOver":true -> battle FINIE -> SORS de la boucle (RAPPORT).
       - "timedOut":true -> pas encore ton tour (l'adversaire réfléchit) -> RE-ÉMETS l'await (n'arrête PAS, ce n'est PAS une fin de partie).
       - "yourTurn":true -> joue (b-d).
    b. \`rl_duel view --state-file ${sf}\` : tes units = CTRL/MAJUSCULE ; ennemis = minuscule ; plans d'attaque [min-max, K!/K?] ; ⚠ effets critiques ; effets actifs par unité.
    c. Planifie le tour COMPLET de TOUTES tes units (moves + abilities + finishs) selon la doctrine : tuer la wincon adverse ATTEIGNABLE, ne pas sur-étendre une fragile, séquencer buff→frappe. PAS de move-guard (self-play v1). Pour un MOVE de REPOSITIONNEMENT (sans attaque), lance d'abord \`moves\` et choisis une tuile LÉGALE (un move hors movable set est rejeté avant l'endturn — ne devine pas la reachability à la main, elle est creusée par les blockers/terrain).
    d. ⚠ BATCHING OBLIGATOIRE : \`play --no-ai\` TERMINE ton tour APRÈS le spec (il joue toutes les actions du spec PUIS endturn-flip). Donc UN SEUL \`play --no-ai --spec '[...]'\` par tour, contenant TOUTES tes units. Si tu mets moins d'actions, tes autres units NE JOUENT PAS ce tour (activations gâchées — c'était LE bug de la v2). FORMATS : move {"kind":"move","unit":<id>,"to":[col,row]} ('to'=ARRAY [col,row]) ; ability {"kind":"ability","caster":<id>,"target":<id>[,"ability":N]} ; finish {"kind":"finish","unit":<id>}. Si "TOUR ABANDONNÉ" (action ratée/format) : les actions AVANT l'échec sont conservées et l'endturn n'a PAS eu lieu -> CORRIGE l'action fautive et relance \`play --no-ai\` avec le RESTE des actions (la fin du spec). play --no-ai passe la main sans tour IA — NORMAL.
    e. Retourne en (a) pour attendre ton prochain tour.

   IMPORTANT : tu ne joues QUE sur yourTurn. "timedOut" n'est PAS une fin de partie. Pas d'abandon en self-play : la partie va à son terme (mort d'un camp ou round-cap), joue pour gagner.

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

   1. ADJUDICATION (vainqueur). La self-play est ZERO-SUM. Croise outcome_perceived : si A="W" & B="L" -> team1 gagne ; A="L" & B="W" -> team2 gagne ; sinon (les 2 "W", ou "uncertain", ou divergence) -> lis l'état réel : \`python scripts/python/rl_duel.py status --state-file data/_sp_${m.seed}_A.json\` (+ alive_by_team). authoritative_winner = "team1"|"team2"|"no-winner" (round-cap/mutual-wipe)|"uncertain". winner_consensus = true si A et B sont d'accord sur le vainqueur.

   2. CONFRONTATION A vs B = vérif INDÉPENDANTE par consensus (2 observateurs séparés du même match). Compare :
      - win-condition : A.win_condition.theirs (lecture de B par A) vs B.win_condition.mine (auto-lecture de B) ; et A.mine vs B.theirs. Accord = haute confiance. Divergence = un des deux a mal lu -> divergences[].
      - mechanics : les entrées about="theirs" sont CROSS-OBSERVABLES (A voit les abilities de B, et inversement). Une mécanique rapportée par LES DEUX (concordante) = CONSENSUS -> consensus_mechanics[]. Rapportée par un seul = candidate. Contradictoire entre A et B -> divergences[].
      - threat_cards / menaces : croise la lecture de chaque camp avec l'auto-éval adverse.
      Pour les mécaniques de consensus, recoupe quand même la RÈGLE DISCRÈTE avec gameconfig/i2 si tu as un doute (le consensus est un PRIOR fort, PAS la vérité — les 2 peuvent se tromper pareil). ${GC_HELP}

   3. ÉCRITURE (demos + knowledge) :
      a. DEMOS : append un bloc match à docs/rl/selfplay-journal.md (CRÉE le fichier s'il n'existe pas, avec un titre "# Self-play journal (oracle vs oracle) — demos + confrontation"). Bloc = "## seed ${m.seed} — winner=<...> (ts=${ts})" + rosters + win_condition consensus (mine/theirs) + key_decisions des 2 + le résultat de la CONFRONTATION (consensus vs divergences). Source TAGGÉE self-play (NE mélange PAS avec docs/rl/journal.md qui est la pipeline oracle-vs-IA). Le détail des coups (action_log) est dans data/_sp_${m.seed}_A.json / _B.json — référence-le (les fichiers seront supprimés en 4, donc résume les séquences clés ici si utiles).
      b. KNOWLEDGE CONSENSUS : pour chaque mécanique de consensus_mechanics (confirmée par LES DEUX players), inscris-la dans docs/rl/wiki.md (bonne unité/section) avec un tag [self-play consensus, seed ${m.seed}]. RIEN au wiki sans consensus (ou recoupage gameconfig explicite). Les divergences -> docs/rl/hypotheses.md en candidat flaggé "(self-play divergence A/B)".
      NE modifie JAMAIS .claude/skills/tacticus-battle/SKILL.md. NE touche PAS aux métriques win-rate de loop.md (le W/L self-play est zero-sum, non comparable au win-rate oracle-vs-IA).

   4. CLEANUP : \`python scripts/python/rl_duel.py dispose --state-file data/_sp_${m.seed}_A.json\` (libère le runner ${runnerId}) puis supprime les 2 state-files (rm data/_sp_${m.seed}_A.json data/_sp_${m.seed}_B.json). runner_disposed=true si le dispose a réussi.

   Renvoie le résumé structuré (TEARDOWN_SCHEMA) : seed, authoritative_winner, winner_consensus, consensus_mechanics, divergences, wiki_inscribed, demos_recorded, runner_disposed, files_written, notes.`
}

// =============================================================================
// Pipeline par match : SETUP -> PLAYERS (//) -> TEARDOWN (single-writer)
// =============================================================================
async function playMatch(m) {
  const setup = await agent(setupPrompt(m),
    { label: `setup:${m.seed}`, phase: 'Setup', model, schema: SETUP_SCHEMA })
  if (!setup || setup.ok === false || setup.runnerId == null) {
    log(`match ${m.seed}: SETUP echec${setup && setup.error ? ` (${setup.error})` : ''}`)
    return null
  }
  const R = setup.runnerId
  log(`match ${m.seed}: runner ${R} pret -> 2 players`)
  const [pa, pb] = await parallel([
    () => agent(playerPrompt('A', R, m, setup),
      { label: `player:${m.seed}:A`, phase: 'Match', model, schema: PLAYER_SCHEMA }),
    () => agent(playerPrompt('B', R, m, setup),
      { label: `player:${m.seed}:B`, phase: 'Match', model, schema: PLAYER_SCHEMA }),
  ])
  // TEARDOWN single-writer (confrontation + adjudication + ecriture)
  const td = await serializeWrite(() => agent(teardownPrompt(m, R, pa, pb),
    { label: `teardown:${m.seed}`, phase: 'Teardown', agentType: 'general-purpose', model, schema: TEARDOWN_SCHEMA }))
    .catch(() => null)
  if (td) {
    log(`match ${m.seed}: winner=${td.authoritative_winner}`
      + `${td.winner_consensus === false ? ' (PAS de consensus)' : ''}`
      + `${(td.divergences || []).length ? ` - ${td.divergences.length} divergence(s)` : ''}`
      + `${(td.consensus_mechanics || []).length ? ` - ${td.consensus_mechanics.length} mecanique(s) consensus` : ''}`
      + `${td.runner_disposed === false ? ' - runner NON dispose (fuite!)' : ''}`)
  } else {
    log(`match ${m.seed}: TEARDOWN echec (ecriture perdue, runner peut-etre non dispose)`)
  }
  return td ? { seed: m.seed, ...td } : null
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
const ok = results.filter(Boolean)
const leaked = ok.filter((r) => r.runner_disposed === false).map((r) => r.seed)
const rollup = {
  attempted: matches.length,
  completed: ok.length,
  winners: ok.map((r) => ({ seed: r.seed, winner: r.authoritative_winner, consensus: r.winner_consensus !== false })),
  divergences_total: ok.reduce((n, r) => n + ((r.divergences || []).length), 0),
  consensus_mechanics_total: ok.reduce((n, r) => n + ((r.consensus_mechanics || []).length), 0),
  wiki_inscribed: [...new Set(ok.flatMap((r) => r.wiki_inscribed || []))],
  files_written: [...new Set(ok.flatMap((r) => r.files_written || []))],
  runners_leaked: leaked,
}
log(`self-play fini: ${ok.length}/${matches.length} matchs`
  + ` - ${rollup.consensus_mechanics_total} mecanique(s) consensus, ${rollup.divergences_total} divergence(s) A/B`
  + (leaked.length ? ` - ${leaked.length} runner(s) NON dispose(s): ${leaked.join(',')}` : ''))
return rollup
