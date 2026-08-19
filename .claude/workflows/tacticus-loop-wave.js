export const meta = {
  name: 'tacticus-loop-wave',
  description: 'Vague RL Tacticus: 2 etages - COMBAT (pool N, //, chaque combat-agent AUTO-VERIFIE ses mecaniques observees contre gameconfig/i2, en mode adversarial) -> SYNTHESE (consommateur concurrence 1, single-writer sans mutex, agent FRAIS par combat). Plus d\'etage verif separe. Seule l\'ecriture est serialisee.',
  whenToUse: 'Jouer N combats Tacticus en parallele ; chaque combat-agent verifie LUI-MEME ses observations (gameconfig/i2 deja en contexte) ; la SEULE etape qui ecrit (synthese=single-writer) est serialisee. Pre-requis: session Frida deja warmee par l\'orchestrateur.',
  phases: [
    { title: 'Combat',   detail: 'pool de N agents combat en //, chacun joue de bout en bout, AUTO-VERIFIE ses mecaniques observees (adversarial vs gameconfig/i2) + dispose son runner ; zero ecriture partagee' },
    { title: 'Synthese', detail: 'CONSOMMATEUR concurrence 1 (single-writer sans mutex): agent FRAIS par combat qui ECRIT journal+hypotheses+wiki+metriques+promotion a partir du combat + ses verdicts AUTO-verifies' },
  ],
}

// =============================================================================
// ARGS CONTRACT  (pas de champ meta pour ca -> convention projet, documente ici)
// =============================================================================
// args: {
//   battles?:  Array< number | {                       // une spec par combat
//                seed: number,                          // identifie/reproduit le matchup
//                aiUnits?: string[],                    // roster IA impose (ids, ":level" tolere/strippe) -> --a-units
//                randomizeAi?: boolean,                 // bake RandomizeAiInput=True (via _wave_build.py)
//                hypothesis?: string,                   // H a tester ce combat (validate)
//              } >
//   count?:    number      // alternative a battles: genere `count` specs (seeds derives) = NB DE COMBATS (file)
//   pool?:     number      // PLAFOND GLOBAL d'agents concurrents (combat+synthese).
//                          //   defaut 15 ; borne dure a 15 (le runtime cappe de toute facon a min(16, coeurs-2)).
//                          //   l'ordonnanceur a priorite repartit ce budget dynamiquement (synthese > combat).
//   seedBase?: number      // base des seeds derives quand on utilise `count` (defaut 70000)
//   randomizeAi?: boolean   // applique a TOUTES les specs derivees de `count` (defaut false)
//   model?:    string      // override GLOBAL: force ce modele pour TOUS les etages: "sonnet"|"opus"|"haiku"
//                          //   (alias -> version courante: opus=Opus 4.8, sonnet=Sonnet 4.6, haiku=Haiku 4.5)
//                          //   defaut (si omis): combat + synthese heritent du model de session (opus).
//   focus?:    string      // consigne de vague (ex: "tester AnvilShield <35%")
//   ts?:       string      // timestamp de la vague (Date.now() throw dans le sandbox)
// }
// MODES:
//   EXPLORE  -> seeds distincts (count, ou battles varies) +/- randomizeAi : decouvrir des failure modes
//   VALIDATE -> battles avec seed FIXE + hypothesis, SANS randomize : test causal reproductible
//
// ARCHITECTURE = ORDONNANCEUR A PRIORITE sur un BUDGET GLOBAL (`MAX` = pool, <=15) :
//   Au plus `MAX` agents en parallele (combat + synthese). Des qu'un slot se libere, on lance
//   le travail DISPONIBLE le plus PRIORITAIRE :
//     1. SYNTHESE  (si un combat est pret a etre ecrit ET aucune synthese ne tourne deja)
//                  -> ECRIT les fichiers. Concurrence 1 = single-writer (sans mutex).
//     2. COMBAT    (sinon, si un seed reste) -> joue 1 bataille, AUTO-VERIFIE ses mecaniques,
//                  + DISPOSE son runner.
//   Dependances: combat(b) -> synthese(b) (des que combat est fini ; il porte deja ses verdicts).
//   POURQUOI prioriser synthese>combat: la synthese (serielle, single-writer) est le goulot
//   -> on la sert en 1er ; le combat (qui PRODUIT du travail) en dernier, juste pour garder le
//   pipeline plein sans sur-produire.
//
// NOTE (2026-06-22) — l'etage VERIF separe a ete SUPPRIME. La verification d'une mecanique
//   OBSERVEE est faite par le combat-agent LUI-MEME (il a deja gameconfig.py + les kits en
//   contexte, et il a VU le combat), en mode ADVERSARIAL (il essaie de REFUTER avant de
//   confirmer) pour limiter le biais de confirmation. Le gate « rien au wiki sans verdict
//   confirmed » reste cote SYNTHESE. Fallback si la qualite wiki se degrade : re-ajouter un
//   verif lean (1 agent batche/vague).
// =============================================================================

// ---- schemas de retour (JSON Schema = objets JS purs) ----
const BATTLE_SCHEMA = {
  type: 'object',
  required: ['seed', 'outcome', 'rounds', 'roster', 'win_condition', 'decisive_cause',
             'tags', 'mechanics', 'doctrines_applied', 'mistakes', 'journal_entry', 'runner_disposed'],
  properties: {
    seed: { type: 'integer' },
    runnerId: { type: ['integer', 'string'] },
    runner_disposed: { type: 'boolean' },                         // le worker DOIT disposer son runner (100 combats sinon = 100 runners)
    outcome: { enum: ['W', 'L'] },
    abandoned: { type: 'boolean' },                               // L par abandon vs combat mene a terme
    rounds: { type: 'integer' },
    roster: {                                                     // unites de chaque cote (suivi diversite matchup)
      type: 'object', required: ['mine', 'theirs'],
      properties: {
        mine: { type: 'array', items: { type: 'string' } },
        theirs: { type: 'array', items: { type: 'string' } },
      },
    },
    win_condition: {                                              // wincon identifiee au recon, structuree
      type: 'object', required: ['mine', 'theirs'],
      properties: { mine: { type: 'string' }, theirs: { type: 'string' } },
    },
    decisive_cause: { type: 'string' },
    tags: { type: 'array', items: { type: 'string' } },           // taxonomie loop.md (inclut bon-coup)
    doctrines_applied: { type: 'array', items: {                  // attribution: quelle doctrine j'ai appliquee + impact percu
      type: 'object', required: ['ref', 'helped'],
      properties: {
        ref: { type: 'string' },                                  // ex "H03", "SKILL §6 kill-wincon", "doctrine-learned §7 over-extend"
        helped: { enum: ['yes', 'no', 'partial', 'na'] },
        note: { type: 'string' },
      },
    } },
    mistakes: { type: 'array', items: { type: 'string' } },       // revue adversariale: ce que j'aurais du faire autrement (meme sur un W)
    threat_cards: { type: 'array', items: {                       // lecture tactique par unite/trait ENNEMI -> alimente les cartes du wiki
      type: 'object', required: ['target', 'role', 'threat', 'counter'],
      properties: {
        target: { type: 'string' },                               // unite / trait / ability ennemi
        role: { enum: ['engine', 'carry', 'anvil', 'control', 'chaff'] },
        threat: { enum: ['critical', 'high', 'med', 'low'] },
        counter: { type: 'string' },                              // comment la neutraliser (mecanique si possible)
        note: { type: 'string' },                                 // contexte si la menace est conditionnelle (ex "high vs roster melee")
      },
    } },
    // MECANIQUES — chaque entree porte SON PROPRE VERDICT d'auto-verification (l'etage verif
    // separe a ete supprime : le combat-agent verifie lui-meme, en adversarial, cf. combatPrompt).
    mechanics: { type: 'array', items: {
      type: 'object',
      required: ['ability', 'observation', 'source', 'confidence',
                 'verdict', 'evidence', 'proposed_destination'],
      properties: {
        ability: { type: 'string' },
        observation: { type: 'string' },
        source: { enum: ['observed', 'gameconfig'] },             // observed = infere du combat -> a AUTO-verifier ; gameconfig = lu (deja verite)
        confidence: { enum: ['low', 'med', 'high'] },
        // --- verdict d'AUTO-verification (ex-VERDICT_SCHEMA, desormais inline) ---
        verdict: { enum: ['confirmed', 'plausible', 'contradicted'] },  // confirmed = gameconfig/i2 corrobore EXPLICITEMENT ; plausible = coherent non prouve (ex. nombre live/scaling) ; contradicted = la verite dit autre chose
        evidence: { type: 'string' },                             // ce que dit gameconfig/i2 (la corroboration DISCRETE, ou son absence)
        proposed_destination: { enum: ['wiki', 'hypotheses', 'discard'] },  // confirmed->wiki, plausible->hypotheses, contradicted->discard
        proposed_text: { type: 'string' },                        // ligne(s) style wiki que la synthese inscrira
      },
    } },
    synergies: { type: 'array', items: {                          // ARETES ability/unite (wiki §5bis) : combos vus/joues/rates
      type: 'object', required: ['pieces', 'class', 'effect', 'play'],
      properties: {
        pieces: { type: 'string' },                               // ex "repair Actus -> GalvanicField", "WarHowl + MurderousSwing"
        class: { enum: ['enemy-avoid', 'mine-chain', 'engine', 'anti'] },
        effect: { type: 'string' },                               // ce que le combo produit
        play: { type: 'string' },                                 // action: couper la source / sequencer / overkill / ne pas planquer…
        status: { enum: ['avoided', 'chained', 'missed', 'triggered-against-me', 'na'] }, // l'ai-je bien joué ?
        source: { enum: ['observed', 'gameconfig'] },             // observed -> mecaniques composantes a auto-verifier (verdict dans mechanics[])
      },
    } },
    hypotheses_touched: { type: 'array', items: {
      type: 'object',
      properties: {
        id: { type: 'string' },
        verdict: { enum: ['confirm', 'refute', 'inconclusive'] },
        note: { type: 'string' },
      },
    } },
    journal_entry: { type: 'string' },                            // bloc markdown pret a append
    infra_anomalies: { type: 'string' },
  },
}

// retour de la SYNTHESE PAR COMBAT (single-writer) — ce qu'a ecrit le consommateur
const WRITE_SCHEMA = {
  type: 'object',
  required: ['seed', 'journal_appended', 'files_written'],
  properties: {
    seed: { type: 'integer' },
    journal_appended: { type: 'boolean' },
    hypotheses_updated: { type: 'array', items: { type: 'string' } },
    wiki_inscribed: { type: 'array', items: { type: 'string' } },   // verdicts "confirmed" inscrits
    promotions: { type: 'array', items: { type: 'string' } },       // H promues en doctrine CE combat (>=2 matchups)
    metrics_line: { type: 'string' },                               // ligne win-rate glissant recomputee
    files_written: { type: 'array', items: { type: 'string' } },
    discarded: { type: 'array', items: { type: 'string' } },
    notes: { type: 'string' },
  },
}

const SQ = (x) => JSON.stringify(x)

// =============================================================================
// Validation / normalisation des args  (fail-fast : le gate d'entree que l'outil ne fournit pas)
// =============================================================================
function need(cond, msg) { if (!cond) throw new Error(`[tacticus-loop-wave] args: ${msg}`) }
let A = args || {}
if (typeof A === 'string') {            // tolere le gotcha "args stringifie": on parse au lieu de rejeter
  try { A = JSON.parse(A) } catch (e) { throw new Error(`[tacticus-loop-wave] args: string non-JSON (${e.message})`) }
}
need(typeof A === 'object' && !Array.isArray(A), 'doit etre un objet JSON (ni string ni array)')
need(A.battles || A.count, 'fournir args.battles OU args.count')

// accepte [70011, 70012] OU [{seed:...}, ...] ; normalise en specs objets
let specs = (A.battles || []).map((s) => (typeof s === 'number' ? { seed: s } : s))
if (specs.length === 0 && A.count) {
  const base = A.seedBase || 70000
  const rand = A.randomizeAi === true
  // count -> seeds distincts (explore par variete de matchup) ; randomizeAi optionnel
  specs = Array.from({ length: A.count }, (_, i) => (rand ? { seed: base + i, randomizeAi: true } : { seed: base + i }))
}
need(specs.length > 0, 'aucun combat a lancer')
need(specs.every((s) => Number.isInteger(s.seed)), 'chaque spec a besoin d\'un seed entier')

const focus = A.focus || 'explore: decouvrir des failure modes'

// modeles. `A.model` (global) force TOUT ; sinon combat + synthese heritent du model de session
// (opus). Le combat (jeu tactique + AUTO-verif) et la synthese (jugement/promotion/ecriture
// multi-fichiers) tournent tous deux en opus par defaut.
const GLOBAL_MODEL = A.model || null
if (GLOBAL_MODEL !== null) need(typeof GLOBAL_MODEL === 'string' && GLOBAL_MODEL.length > 0, 'args.model doit etre une string (ex: "sonnet", "opus", "haiku")')
const combatModel = GLOBAL_MODEL || undefined                 // undefined => herite du model de session (opus)
const synthModel = GLOBAL_MODEL || undefined                  // undefined => herite du model de session (opus)

// MAX = PLAFOND GLOBAL d'agents concurrents (combat + synthese). Defaut 15, borne dure a 15 (>=1).
const MAX = Math.max(1, Math.min(15, (A.pool && A.pool > 0) ? Math.floor(A.pool) : 15))

log(`args OK: ${specs.length} combats - MAX ${MAX} agents concurrents (combat+synthese) - focus: ${focus}`)
log(GLOBAL_MODEL ? `modele unique force: ${GLOBAL_MODEL} (tous les agents)` : 'modeles: combat=herite(opus), synthese=herite(opus)')
log('ordonnanceur a priorite (synthese > combat), single-writer = synthese concurrence 1 ; verif FOLD-IN dans combat')

// ---- prompts ----------------------------------------------------------------
// Mode d'emploi gameconfig.py injecte dans combat (recon ET auto-verif) : l'outil n'est PAS
// un MCP auto-documente -> l'agent doit avoir la syntaxe EXACTE sous les yeux.
const GC_HELP =
  `OUTIL gameconfig.py = VÉRITÉ du jeu (chiffres gameconfig + texte de règles i2). Usage EXACT :
     - python scripts/python/gameconfig.py <unitId|nom>  -> KIT COMPLET d'une unité en 1 SEUL appel
       (traits décodés + actifs + passifs, chacun avec sa description i2). Accepte la CLÉ (admecManipulus)
       OU le NOM d'affichage (Actus) ; plusieurs unités en args ; si ambigu il LISTE les candidats.
     - python scripts/python/gameconfig.py --ability <Nom>  -> chiffres + règles i2 d'une ability.
     - python scripts/python/gameconfig.py --effect <Nom>   -> recon d'un effet (noms de decisionView.effects).
     - python scripts/python/gameconfig.py --trait <Nom>    -> texte de règles d'un trait.
     TOLÉRANT AU MODE : peu importe le flag, si le nom existe dans une AUTRE catégorie l'outil le résout et te
       dit laquelle (ex. \`--ability TeleportStrike\` -> « pas une ability, c'est un TRAIT » + description). Donc
       1 appel suffit, quel que soit le flag. NE fouille JAMAIS data/*.json à la main et NE DEVINE JAMAIS
       d'autres noms au hasard. Si l'outil répond « introuvable » partout : c'est soit un comportement du
       HARNESS/outil (PAS une règle du jeu -> verdict plausible + note toolfeedback), soit un mauvais nom -> ARRÊTE de chercher.`

function combatPrompt(b) {
  const sf = `/tmp/wave_${b.seed}.json`
  const aiCsv = b.aiUnits ? b.aiUnits.map((u) => String(u).split(':')[0]).join(',') : null
  const buildCmd = b.randomizeAi
    ? `python scripts/python/_wave_build.py --seed ${b.seed} --state-file ${sf}`
    : `python scripts/python/rl_duel.py build --seed ${b.seed} --board MC1_67 --state-file ${sf}${aiCsv ? ` --a-units ${aiCsv}` : ''}`
  const disposeCmd = `python scripts/python/rl_duel.py dispose --state-file ${sf}`
  return `Tu es l'oracle Tacticus. Tu joues EXACTEMENT UN (1) combat: seed ${b.seed}. Puis tu renvoies ton retour structure et tu T'ARRETES.
   Tu n'es PAS responsable des autres combats de la vague (l'orchestrateur lance un agent distinct par seed). NE joue/build/recon AUCUN autre seed, MEME si le theme ci-dessous mentionne d'autres seeds ou un nombre de combats a faire.
   PRECONDITION: la session Frida est DEJA warmee par l'orchestrateur - NE lance JAMAIS autoBootExtraire, NE navigue PAS l'UI in-game.
   1. Lis la doctrine: docs/rl/wiki.md, .claude/skills/tacticus-battle/SKILL.md (sections 6/7) ET .claude/skills/tacticus-battle/doctrine-learned.md (doctrine APPRISE active - applique-la comme le SKILL), docs/rl/loop.md (abandon asymetrique + taxonomie tags). Lis aussi docs/rl/hypotheses.md : si une H ouverte concerne une unite de TON matchup, teste-la DELIBEREMENT et reporte le verdict dans hypotheses_touched.
   2. Recon gameconfig->wiki pour CHAQUE unite (player + AI). Ne devine jamais. ${GC_HELP} LIS la carte tactique (ligne "▸ Tac:" role/menace/counter) de chaque unite ENNEMIE dans le wiki (menace/counter PAR unite). Si une unite n'a pas de carte (ou elle est fausse), evalue-la toi-meme et reporte-la dans threat_cards. ATTENTION: la menace d'une unite ISOLEE ne suffit PAS a deduire le wincon -- ne conclus PAS le wincon ici, attends d'avoir mappe les synergies (2bis) puis derive-le en 2ter.
   2bis. SYNERGIES = RECALL + INFERENCE (ne te limite PAS au connu). (a) RECALL: lis wiki §5bis et applique les combos deja repertories de CE matchup. (b) INFERENCE des combos PAS encore dans §5bis: la plupart des trigger-synergies sont des CONDITIONNELS ECRITS dans le texte i2 d'une ability/trait -> pour CHAQUE unite, lis son kit (\`gameconfig.py <nom>\` donne le texte i2) et repere le langage conditionnel ("whenever / if / after a kill / when repaired / if NOT overkilled / while / each time") = un TRIGGER a mapper ; puis CROISE le board: pour CHACUNE de mes abilities, est-ce qu'une autre de mes units l'enable/amplifie (buff->frappe, Pin/Suppress->turret, pump->carry, debuff-armure->burst) ? AVANT de jouer, dresse (1) les trigger-synergies ENNEMIES a NE PAS declencher -> couper la SOURCE / overkill / forcer 2e mort ; (2) MES chaines a SEQUENCER (buff AVANT frappe, kill confirme AVANT la normale, Pin AVANT turret). Joue en respectant ces listes ET reporte TOUT dans synergies (source="gameconfig" si lu dans le texte i2, "observed" si infere du combat ; status avoided/chained/missed/triggered-against-me). Les synergies INFEREES nouvelles (absentes de §5bis) sont les plus precieuses a remonter.
   2ter. WIN-CONDITION = DERIVEE des synergies (2bis), PAS d'une menace isolee. La win-condition est une propriete EMERGENTE des synergies. LEUR wincon = la SYNERGIE/ENGINE dominante (le combo qui, s'il tourne a terme, gagne). Regle: si la plus haute menace est AMPLIFIEE/ENABLED par une autre unite (pump, buff, repair, trigger, summon), alors le wincon EST cette synergie et le COUNTER = casser sa SOURCE (tuer l'enabler/engine TOT, nier le trigger, empecher la chaine) -- PAS affronter la sortie amplifiee (le mur pumpe / la cible re-healed est ~inkillable ; l'enabler, lui, est tuable). Si la menace est AUTONOME (carry sans enabler) -> elle EST le wincon directement. Pareil pour MA wincon = la meilleure synergie que JE peux assembler + son enabler a proteger. Renseigne win_condition {mine, theirs} en NOMMANT la synergie/engine et sa source, pas juste l'unite (ex. "Hollan TwistedScience pump Tarvakh -> tuer Hollan T1-T2", pas "Tarvakh carry").
   3. Runner ISOLE. BUILD: \`${buildCmd}\`. TOUS tes appels rl_duel suivants utilisent --state-file ${sf} (il porte TON runnerId - ne te fie JAMAIS au "runner courant" global, d'autres workers tournent en parallele).
   3bis. MOVE-GUARD PER-TURN (anti-over-extension, OBLIGATOIRE avant CHAQUE \`play\`). L'over-extension est le failure-mode DOMINANT et se CONSTRUIT tour par tour (le danger d'un move n'est souvent visible qu'au tour ou l'IA peut l'atteindre) -> donc AVANT CHAQUE tour (T1, T2, T3, ...), planifie ton tour COMPLET (moves + attaques) puis simule-le : \`python scripts/python/rl_duel.py guard --climb --spec '<mon tour complet>' --state-file ${sf}\`. Le guard CLONE le combat (ne touche PAS ton runner), RECONSTRUIT le tour courant en rejouant l'historique de tes VRAIS moves (action_log, enregistre automatiquement par \`play\`), applique ton spec, FAIT JOUER 1 tour a l'IA ADVERSE (CheatRunAIMessage = ground truth ; l'IA ne joue JAMAIS ta team), et rend le NET du tour + un VERDICT + un "spec recommande" corrige (recule les units qui mourraient pour rien). NET = leurs_pertes - mes_pertes sur CE tour : NET<0 = l'IA te focus AVANT toi = OVER-EXTENDED ; NET>=0 = focus-first (tu tiens/gagnes l'echange). Regle : VERDICT "OVER-EXTENDED" -> joue le spec RECOMMANDE affiche (PAS le tien) ; "FOCUS-FIRST"/"SERRE-neutre" -> joue ton tour. A RAPPELER a CHAQUE tour tant qu'un contact reste possible (inutile une fois clairement gagne/perdu). Si le guard ERREUR/abort -> joue ton tour directement (ne bloque pas). Reporte ce que le guard a dit + si tu as suivi sa reco dans mistakes/notes.
   4. Joue CE combat TOUR PAR TOUR via \`python scripts/python/rl_duel.py play --spec '<JSON>' --state-file ${sf}\` (1 appel = mon tour : mes actions + endturn + tour IA ; \`play\` enregistre mes actions dans action_log pour le guard). RE-FAIS l'etape 3bis AVANT chaque \`play\`. Pour un MOVE de REPOSITIONNEMENT (sans attaque), lance d'abord \`python scripts/python/rl_duel.py moves [--unit <id>] --state-file ${sf}\` (grille ASCII des tuiles légales par unité — la carte ne donne que les plans d'ATTAQUE) et choisis une tuile LÉGALE : ne devine PAS la reachability à la main (creusée par blockers/terrain), un move hors-set est rejeté avant l'endturn. FORMATS EXACTS des actions (RESPECTE-les a la lettre, sinon le tour est ABANDONNE) : {"kind":"move","unit":<id>,"to":[col,row]} -- 'to' est un ARRAY [col,row] (deux entiers), JAMAIS une string "col,row" ; {"kind":"ability","caster":<id>,"target":<id>} (ou ajoute "ability":<N>) ; {"kind":"finish","unit":<id>}. Si play affiche "TOUR ABANDONNE" (action ratee / mauvais format / hors portee / mutated=false), l'endturn n'a PAS ete joue et l'IA n'a PAS joue : CORRIGE l'action et relance \`play\` (les actions deja appliquees avant l'echec sont conservees). Abandonne (L) des que tu ne peux plus contrer leur win-condition (liberal); W SEULEMENT si finalStage=Finished VERIFIE (jamais devine, jamais "position gagnee").
   5. Theme de la vague (CONTEXTE seulement, PAS une instruction de jouer plusieurs combats): ${focus}${b.hypothesis ? ` -- teste l'hypothese: ${b.hypothesis}` : ''}.
   6. Revue auto-ADVERSARIALE ("suppose ma defaite de ma faute -> root cause") -> remplis mistakes (ce que j'aurais du faire autrement, MEME sur un W).
   6bis. AUTO-VERIFICATION des mecaniques (l'etage verif separe a ete SUPPRIME -> c'est TOI qui verifies). Pour CHAQUE entree de mechanics que tu reportes, attribue un verdict en mode ADVERSARIAL -- SOIS TON PROPRE SCEPTIQUE : ne confirme PAS par defaut ce que tu CROIS avoir vu en combat, exige la corroboration DISCRETE dans gameconfig/i2 (tu as deja l'outil + les kits en contexte du recon). ${GC_HELP}
      - source="gameconfig" (tu l'as LU au recon) -> verdict="confirmed" + evidence = ce que dit le texte.
      - source="observed" (infere du combat) -> RECOUPE-la : verdict="confirmed" si gameconfig/i2 corrobore EXPLICITEMENT la REGLE DISCRETE (trigger/conditionnel/effet/qui-fait-quoi) ; "plausible" si coherent mais non prouve -- en particulier tout NOMBRE/SCALING live ("pumped", "+X dmg", valeur precise) est "plausible" (gameconfig donne la base, pas la valeur live emergente, n'inscris PAS de nombre au wiki) ; "contradicted" si la verite dit autre chose.
      - proposed_destination: confirmed->wiki, plausible->hypotheses, contradicted->discard. proposed_text = 1-2 lignes style wiki (que la synthese inscrira). evidence = la corroboration DISCRETE trouvee (ou son absence). Inscription (loop.md + SKILL §2bis): general + verifie + non-derivable ; n=1 reste hypothese.
      - Budget: pas de rabbit-hole. Apres le kit + l'ability/trait/effet pertinents, CONCLUS. Un nombre live ou un comportement harness = plausible + note dans infra_anomalies/notes.
   7. DISPOSE OBLIGATOIRE: a la fin (W/L/abandon), libere TON runner -> \`${disposeCmd}\` (100 combats sans dispose = 100 runners empiles -> OOM). Mets runner_disposed=true seulement si le dispose a reussi.
   RETOUR STRUCTURE (n'ecris AUCUN fichier partage - c'est la phase Synthese qui ecrit) - en plus des champs de base, renseigne OBLIGATOIREMENT :
    - roster {mine, theirs} = les unites de chaque cote ; win_condition {mine, theirs} = la wincon de CHAQUE cote DERIVEE des synergies (cf. 2ter) : NOMME la synergie/engine dominante + sa SOURCE a casser, pas juste l'unite.
    - doctrines_applied = quelles doctrines (par ref: "H##", "SKILL §6/7", "doctrine-learned §6/7") tu as reellement APPLIQUEES, et si ca a aide (yes/no/partial/na) + note courte.
    - abandoned = true si L par abandon (vs combat mene a terme). runner_disposed = true si dispose OK.
    - threat_cards = pour chaque unite ENNEMIE notable: role/menace/counter (ta lecture tactique -> alimente les cartes du wiki ; corrige si la carte existante etait fausse/incomplete).
    - synergies = les COMBOS de CE matchup (cf. 2bis) : pieces (A+B/trigger), class (enemy-avoid|mine-chain|engine|anti), effect, play, status (l'ai-je bien joue ?) -> alimente wiki §5bis. Inclus surtout ceux que tu as RATES (status=missed/triggered-against-me) = lecons.
    - mechanics[] = CHAQUE mecanique notable AVEC son verdict d'auto-verification (cf. 6bis): source, confidence, verdict, evidence, proposed_destination, proposed_text. C'est CE verdict qui gate l'inscription wiki cote synthese -- sois honnete et adversarial.`
}

function synthesePrompt(b, battle) {
  return `Etage SYNTHESE (CONSOMMATEUR concurrence 1 = tu es le SEUL ecrivain a cet instant, AUCUN autre agent n'ecrit en parallele -> pas de mutex). D'autres combats ont ecrit AVANT toi et ecriront APRES (1 a la fois). LIS l'etat COURANT de chaque fichier avant de l'editer. Le journal est APPEND-ONLY (ne reecris jamais l'existant). Tu ecris la doctrine d'UN SEUL combat (seed ${b.seed}).
   Entrees:
   - Combat (retour structure, AVEC les verdicts d'auto-verification deja DANS battle.mechanics[]): ${SQ(battle)}
   - Timestamp de la vague: ${A.ts || 'inconnu'}
   NOTE: il n'y a plus d'etage verif separe -- le combat-agent a AUTO-verifie ses mecaniques (mode adversarial vs gameconfig/i2). Tu te FIES a battle.mechanics[].verdict pour le routage, mais le gate « rien au wiki sans verdict 'confirmed' » reste STRICT.
   Actions EN SERIE (pour CE combat uniquement):
   1. APPEND battle.journal_entry a la fin de docs/rl/journal.md (ne touche pas aux entrees existantes).
   2. Applique battle.hypotheses_touched (confirm/refute/inconclusive) dans docs/rl/hypotheses.md.
   3. Par mecanique de battle.mechanics[] (selon son verdict) : "confirmed"->inscris proposed_text dans docs/rl/wiki.md (bonne unite/section) ; "plausible"->docs/rl/hypotheses.md (candidat) ; "contradicted"->rien (rapporte dans discarded). RIEN au wiki sans verdict "confirmed".
   4. METRIQUES: recompte le win-rate glissant + la frequence par tag depuis l'INTEGRALITE de docs/rl/journal.md (inclut CE combat + tous ceux ecrits avant toi), mets a jour docs/rl/loop.md (section Metriques). Renvoie la ligne win-rate dans metrics_line.
   5. PROMOTION DOCTRINE: toute hypothese de docs/rl/hypotheses.md desormais confirmee sur >=2 matchups DISTINCTS (gate strict, pas 2 combats correles) + filtre d'inscription -> ajoute-la en doctrine actionnable a .claude/skills/tacticus-battle/doctrine-learned.md (§6 engagement ou §7 pieges, avec preuve [H## · N matchups]). Sous le gate -> elle reste candidate flaggee dans hypotheses.md. NE modifie JAMAIS .claude/skills/tacticus-battle/SKILL.md de base.
   6. CARTES TACTIQUES WIKI: pour chaque battle.threat_cards, ajoute/affine la ligne "▸ Tac: role=… · menace=… · counter=…" sur l'entree de l'unite (§2/§3) ou du trait (§1) dans docs/rl/wiki.md, evidence-tagged [n=]. Garde KIT (faits gameconfig/i2) et Tac (appris) VISUELLEMENT distincts. Signale toute contradiction de menace/counter (champ notes).
   6bis. SYNERGIES WIKI §5bis: pour chaque battle.synergies, ajoute/affine la ligne au FORMAT \`<pieces> — CLASSE : effet -> PLAY [n=, seed]\` dans la bonne sous-section de §5bis (Ennemies-a-eviter / Miennes-a-enchainer / Anti). N'inscris une synergie que si ses MECANIQUES COMPOSANTES sont "confirmed" dans battle.mechanics[] (sinon -> candidate dans hypotheses.md). Incremente [n=]/seeds si la synergie existe deja. PRIORISE les status missed/triggered-against-me (ce sont les lecons les plus utiles).
   7. Le journal doit refleter roster + win_condition (mienne/leur) + mistakes ; signale (notes) toute doctrine dont doctrines_applied.helped="no" = candidate a reformuler/revoquer.
   Renvoie SEULEMENT le resume structure de ce que TU as ecrit (WRITE_SCHEMA).`
}

// =============================================================================
// ORDONNANCEUR A PRIORITE (budget global MAX, synthese > combat)
//   File d'attente par etage. A chaque slot libre, pump() lance le travail
//   disponible le plus prioritaire. Event-driven : chaque completion re-pump.
// =============================================================================
const combatQ = specs.slice()     // seeds pas encore joues
const synthQ = []                 // { st } : un combat pret a etre ECRIT (combat fini, verdicts inclus)
const done = []                   // resultats finaux (1 / synthese terminee)
const synthFailed = []            // seeds dont la synthese a echoue (ecriture perdue)
let running = 0                   // agents en vol (combat+synthese) -> jamais > MAX
let synthRunning = false          // synthese en cours ? (single-writer : 1 max)

let resolveDone
const finished = new Promise((r) => { resolveDone = r })

function tryFinish() {
  if (running === 0 && combatQ.length === 0 && synthQ.length === 0) {
    resolveDone()
    return true
  }
  return false
}

function onCombatDone(b, battle) {
  running--
  if (!battle) { log(`combat ${b.seed}: ECHEC (null)`); return pump() }
  if (battle.runner_disposed === false) log(`combat ${b.seed}: runner NON dispose (fuite possible)`)
  const mech = (battle.mechanics || []).length
  const conf = (battle.mechanics || []).filter((m) => m.verdict === 'confirmed').length
  log(`combat ${b.seed}: ${battle.outcome}${battle.abandoned ? '(abandon)' : ''} ${battle.rounds}r -> ${mech} mecaniques (${conf} confirmed) -> synthese`)
  synthQ.push({ st: { b, battle } })   // combat porte deja ses verdicts -> direct synthese
  pump()
}

function onSynthDone(st, write) {
  running--; synthRunning = false
  const { b, battle } = st
  if (write) log(`synthese ${b.seed} ecrite${(write.promotions || []).length ? ` - PROMO: ${write.promotions.join('; ')}` : ''}`)
  else { log(`synthese ${b.seed}: ECHEC ecriture`); synthFailed.push(b.seed) }
  done.push({
    seed: b.seed, outcome: battle.outcome, abandoned: !!battle.abandoned,
    rounds: battle.rounds, tags: battle.tags || [], runner_disposed: !!battle.runner_disposed,
    promotions: (write && write.promotions) || [], files_written: (write && write.files_written) || [],
  })
  pump()
}

// pump : remplit les slots libres selon la PRIORITE synthese > combat (1 synthese max)
function pump() {
  while (running < MAX) {
    if (synthQ.length > 0 && !synthRunning) {
      const { st } = synthQ.shift()
      running++; synthRunning = true
      agent(synthesePrompt(st.b, st.battle),
        { label: `synthese:${st.b.seed}`, phase: 'Synthese', agentType: 'general-purpose', model: synthModel, schema: WRITE_SCHEMA })
        .then((w) => onSynthDone(st, w), () => onSynthDone(st, null))
    } else if (combatQ.length > 0) {
      const b = combatQ.shift()
      running++
      agent(combatPrompt(b),
        { label: `combat:${b.seed}`, phase: 'Combat', model: combatModel, schema: BATTLE_SCHEMA })
        .then((battle) => onCombatDone(b, battle), () => onCombatDone(b, null))
    } else {
      break  // rien de demarrable maintenant -> on attend des completions
    }
  }
  tryFinish()
}

pump()                 // amorce (au depart seuls des combats sont eligibles)
await finished
const results = done

// =============================================================================
// Roll-up final : agregation JS (aucune ecriture - tout a deja ete ecrit par combat)
// =============================================================================
const wins = results.filter((r) => r.outcome === 'W').length
const leaked = results.filter((r) => r.runner_disposed === false).map((r) => r.seed)
const rollup = {
  attempted: specs.length,
  battles: results.length,
  win_rate: results.length ? `${wins}/${results.length} = ${Math.round((100 * wins) / results.length)}%` : 'n/a',
  promotions: results.flatMap((r) => r.promotions),
  files_written: [...new Set(results.flatMap((r) => r.files_written))],
  runners_leaked: leaked,
  synthese_failed: synthFailed,
  per_combat: results.map((r) => ({ seed: r.seed, outcome: r.outcome, abandoned: r.abandoned, rounds: r.rounds, tags: r.tags })),
}
log(`vague finie: ${rollup.win_rate} - ${rollup.promotions.length} promo(s)${leaked.length ? ` - ${leaked.length} runner(s) NON dispose(s): ${leaked.join(',')}` : ''}${synthFailed.length ? ` - ${synthFailed.length} synthese(s) ECHOUEE(s): ${synthFailed.join(',')}` : ''}`)
return rollup
