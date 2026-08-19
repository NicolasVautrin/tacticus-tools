# Carnet d'hypothèses (leçons PROVISOIRES — tampon avant doctrine)

Statut : `provisoire` (défaut, n=1) · `confirmée` (≥2 parties OU seed-replay contrôlé → à PROMOUVOIR)
· `réfutée` (à supprimer). Une H ne change PAS mon comportement par défaut tant qu'elle n'est pas
promue en doctrine (skill/wiki). Promotion = passe le filtre d'inscription + statut confirmée.

---

## H01 — Ne pas masser ses summons face à une compo AoE/anti-summon — `provisoire` (pour:1 contre:0)
- **claim** : invoquer plusieurs summons sur des hexes adjacents = ils se font wipe par un MoW
  anti-summon (Forgefiend) ou une AoE (PlagueWind, Blast line). Les **espacer** ; ne pas tout sortir le même tour.
- **test (VALIDATE)** : rejouer **seed 67827** en étalant les invocations (≥2 hex d'écart) → l'avance tient-elle ?
- **evidence** : G02 (pour — violé → wipe de 4 héros)
- **→ doctrine si confirmée** : SKILL §6 (déjà « ne pas clusterer vs AoE » ? à fusionner) / wiki (MoW anti-summon)

## H02 — Prioriser la win-condition adverse, pas le chaff — `confirmée` (n=27 distincts, contre:0) → À PROMOUVOIR
- **claim** : contre une unité qui devient **injouable plus tard** (kiting + self-heal + escalade,
  ex. Neurothrope ; ou un **engine de sustain** type Isabella adeptHospitaller), il faut **committer
  à la tuer/régler TÔT**. Clear du chaff ou re-tuer les revivables pendant que l'engine snowballe =
  défaite lente.
- **test (VALIDATE)** : rejouer **seed 19355** en focalisant le Neurothrope dès qu'atteignable → issue ?
- **evidence** : G03 (pour — violé → one-shot d'Anuphet) ; **seed 70012** (pour — `kill-wincon-first`/
  jamais réglé Isabella → ses revive/heal ont annulé mes kills, défaite) ; **seed 70015** (confirm
  `kill-wincon-first` : focus Mephiston correct mais le reste out-durable) ; **seed 91001** (pour —
  jamais réglé Yarrick summoner → 4 Cadians snowball) ; **seed 91005** (pour — kill Hollan NON-permanent
  via Ambush → revive full + TwistedScience déjà snowballé) ; **seed 91008** (pour — kill le WeaverOfFate
  Ahriman dès qu'atteignable via l'aura Corrodius = W) ; **seed 91012** (pour — H03 SUR-appliqué a empêché
  le kill du summoner Isaak avant CultDemagogue → board flip 4v12) ; **seed 93000** (pour — kill propre des
  3 engines Actus+Archimatos+Sy-gex T1-T2, priorité correcte ; MAIS payé par over-extension → loss : H02
  seul insuffisant si tuer les engines exige de sur-étendre des corps qui meurent ensuite aux briques) ;
  **seed 93001** (pour — kill PERMANENT du Parasite T3 + Magus engine via taunt-forced + permanent en
  réaction = board collapse, W) ; **seed 95001** (pour — Isabella adeptHospitaller, engine de
  résurrection, identifiée comme wincon adverse et tuée à la 1ʳᵉ K! atteignable T4 via le ranged stacké
  de Shiron ; elle n'a ressuscité Roswitha qu'une fois avant de mourir — un tour de plus = elle
  ressuscitait Tjark aussi → W). **NOUVELLE NUANCE (93000)** : H02 doit être payé avec une exposition
  forward MINIMALE — tuer les engines depuis les tuiles les plus shallow + garder un écran, sinon on gagne
  la guerre des engines et on perd l'attrition. **seed 96000** (pour — Farseer/Eldryon (Doom engine, fragile
  7530) + Nauseous Rotbone (reviveur/healer Chaos) identifiés comme wincons et tués T1-T3 AVANT que Typhus
  meure → revive nié ; Canoness (ActOfFaith) aussi tuée tôt ; ordre correct moteurs-avant-kills, W malgré
  over-extension Dante T1). **seed 96001** (INCONCLUSIVE — Isabella adeptHospitaller identifiée
  comme wincon dès le recon, mais INACCESSIBLE ce matchup : row 9, aucune unité en range T1, le
  SeekerMissile de l'état hérité visait Kharn et non Isabella → H02 non appliquée FAUTE DE REACH. Le
  PRINCIPE reste valide — non réfuté — mais non confirmé sur ce matchup : la wincon adverse doit aussi
  être ATTEIGNABLE, sinon H02 ne peut pas porter le combat ; nuance planification : pré-positionner un
  dealer ranged T1 pour qu'un engine back-row entre en portée T2). **seed 96002** (pour — DOUBLE engine-kill
  prioritaire : Eldryon (Doom/Executioner engine, fragile 7530) tuée T4 à 149 HP AVANT scaling Executioner
  létal — near-miss, 1 tour de plus = board-wipe — ET Archimatos (summon engine) éliminé T2 AVANT son
  premier summon de Bloodletter ; ordre correct engines-d'abord, W ; ⚠ illustration de la NUANCE
  atteignabilité+timing : Eldryon devait être tuée DANS la fenêtre T1-T4, pas seulement « tuée »).
  **seed 97001** (INCONCLUSIVE — engines wincon (Hollan TwistedScience-sustain + Sho'syl Seeker)
  correctement identifiés au recon mais INATTEIGNABLES tout le combat : rows 6-9 derrière un mur
  mêlée de 22k Angrax+Tarvakh, mon roster melee/r2 = reach zéro. MÊME échec de reach que 96001 et
  91001 → le PRINCIPE n'est pas réfuté mais ne peut pas porter le combat sans reach tool. Renforce
  la NUANCE atteignabilité : avant d'adopter un plan d'attrition, vérifier que l'engine est
  ATTEIGNABLE — un roster melee/r2 vs engines row-9 = H02-inapplicable structurel ; pré-positionner
  un dealer r3+/deep-strike OU flagger la loss structurelle au recon).
  **seed 97002** (INCONCLUSIVE — priorité d'engine CORRECTE : Winged Prime (summon-engine) +
  Actus (repair-engine) identifiés et Winged Prime tué proprement T2 ; MAIS chasser le 2ᵉ engine
  (Actus) a causé la loss → renforce la NUANCE 93000 : H02 doit être payé avec une exposition
  MINIMALE + un kill SÉCURISÉ, pas une commitment solo profonde sur une prédiction d'actif non
  fiable. Le chip non-létal sur Actus (3302) a été ENTIÈREMENT effacé au tour suivant (+5983 →
  9285) → pour un repair-engine, « kill THIS turn ou ne pas committer » est LITTÉRAL. Ni confirme
  ni réfute clairement le principe central : la priorité était bonne, c'est la MANIÈRE (deep solo +
  finisher de-buffé) qui a échoué).
  **seed 97000** (INCONCLUSIVE — priorité d'engine CORRECTE : Tigurius (Psyker AoE engine + PsychicFortress
  aura) identifié comme la plus haute menace et K!'d T2 (JakhalStimms), + Deathleaper T2 + Vindicta T3 →
  guerre des engines GAGNÉE 5v3/3v2. MAIS la VRAIE wincon late-game = Thaddeus (barrage ranged ~5k
  stationnaire) DERRIÈRE le mur MkXGravis de Calgar, INATTEIGNABLE par mon roster melee → tuer les engines
  FRONT n'a PAS résolu le problème structurel de reach. ÉNIÈME illustration de la NUANCE atteignabilité
  (cf. 91001/96001/97001) : H02 ne porte pas le combat si la vraie wincon est un kiting ranged backline
  hors de portée. Principe non réfuté, juste insuffisant ; le matchup était structurellement défavorable
  — wiki §5).
  **seed 98003** (INCONCLUSIVE — priorité d'engine CORRECTE au recon : Aleph-Null (repair-hub) + Tan Gi'da
  (summon-engine) du noyau Mechanical identifiés comme la wincon, ET Aleph-Null tué T2 via Psychic NoBlocking
  (bypass armure, 6866 en un cast puis Yarrick normal K!) ; MAIS le kill est venu APRÈS la perte de ma ligne
  forward et après que le summon-snowball ait pris le board (5 héros → 12 unités en 2 tours). Énième
  illustration de la NUANCE atteignabilité+fenêtre : un cluster engine row-8/9 est INATTEIGNABLE pour un alpha
  soutenu quand mes outils de reach (deep-strike melee) auto-finissent non-adjacents et la charge est hors
  portée → la priorité d'engine était bonne, mais le matchup était structurellement défavorable de reach et
  H02 ne pouvait pas porter le combat. Principe non réfuté, insuffisant ici ; renforce la règle « flagger la
  loss structurelle au recon quand reach=zéro vers l'engine »).
  **seed 98004** (pour — **engine ATTEIGNABLE → H02 a PORTÉ le W** : Nauseous (deathRotbone) = Healer-engine de
  sustain (heal toute faction ~5000 + Resilient) identifié au recon comme la wincon adverse et tué T3 via
  Haarken+Makhotep chunk → Nicodemus multi-hit finish (186 puis 1→TUÉ, beat Resilient) ; les buff-engines
  Helbrecht/Vitruvius/Aesoth cassés T2-T3 en réactions → wincon de sustain adverse effondrée. NOUVELLE NUANCE
  ANTI-HEALER : coupler le kill d'un Healer-engine avec un HEAL-BLOCK Mephiston (FuryOfTheAncients, 2 rounds) qui
  neutralise le heal/revive sur les unités touchées AVANT/PENDANT le kill ; ET un revive-engine adverse
  (TaintedNarthecium 75% Chaos) peut être STRUCTURELLEMENT INERTE par la composition même — Nauseous seul Chaos,
  4 alliés Imperial → aucun Chaos adjacent à revive → recon le vérifier au lieu de le craindre. Contrairement
  aux losses row-9-inatteignables, l'engine était ici ATTEIGNABLE (Nauseous move2 lent + l'IA a avancé)).
  **seed 98002** (pour — **DOUBLE engine-kill ATTEIGNABLE → H02 a PORTÉ le W** : le noyau Necron sustain+summon
  (Anuphet ResurrectionOrb summoner + Aleph-Null FabricatorClaw/Mechanic repair-amplifier) identifié au recon
  comme la wincon adverse et brisé T2 AVANT le snowball : Aleph-Null (repair-amplifier, soft 9037 no-Resilient)
  tué T2 — finition au RANGED (Abraxas Psychic r2) pour que son Explodes friendly-fire chunke Anuphet+un Warrior —
  ET Anuphet (summoner soft 8536) chunké 8536→2754 par Yazaghor puis fini en réaction. Les engines étaient SOFTS
  et move-in (l'IA a dive) → ATTEIGNABLES = H02 applicable (contraste avec les reach-fail row-9 91001/96001/97001/
  97000/98003). NUANCE 93000 RESPECTÉE : engines tués depuis des tuiles SHALLOW (Abraxas r2, TG mêlée depuis tuile
  courante, Yazaghor short-hop) en gardant le TG en écran → pas de sur-extension pour tuer les engines (la seule
  sur-extension, Kharn, était indépendante des engine-kills). NB Toth (anvil TimeFlux/TerminatorArmour) = corps le
  plus dur mais SANS amplification d'équipe → traité en SECONDAIRE après les engines summon+repair, ordre correct).
  **seed 98000** (INCONCLUSIVE — priorité d'engine PARTIELLE/CORRECTE sur les engines FRONT : Thaumachus (psychic/shield)
  tué K! T2, Dreir (summon-engine) neutralisé par taunt CrushingClaws + AoE-chunké, 3 Death Riders cleavés ; MAIS la
  VRAIE wincon late = Snappawrecka (carry repair-scaling DakkaDakka 6→16 hits) + Aleph-Null (repair-hub) rows 5-7 sont
  restés INATTEIGNABLES pour mes survivants mêlée → tuer les engines FRONT n'a PAS résolu le carry+repair backline.
  ÉNIÈME illustration de la nuance atteignabilité (cf. 96001/97001/97000/98003) : un roster majoritairement mêlée
  (1 ranged) vs un carry ranged repair-scaling derrière un screen ranged = reach-fail structurel sur la vraie wincon ;
  H02 non réfuté, juste insuffisant sans reach au backline carry+repair).
  **seed 98001** (pour — **wincon-set ENTIER ATTEIGNABLE → H02 a PORTÉ le W** : vs un roster miroir summon/sustain
  + 3 Psykers [Hollan TwistedScience-pump/Healer/Ambush/Aberrant + Xybia MindControl/Neophyte/Ambush + Abraxas
  Screamer-cascade] amplifié par Kharn carry [TheBetrayer], j'ai tué l'INTÉGRALITÉ du wincon-set de façon PERMANENTE
  dans le bon ordre : Kharn (carry) chunké+fini T2 AVANT son 1er kill (TheBetrayer non-amorcé) ; Tjark anti-Psyker a
  DELETÉ Xybia 2× (permanent past Ambush, WasOverkilled) + chunké Abraxas 7026→784 → Archimatos ranged-finish ;
  Snotflogga a tué Hollan 2× (permanent). Les engines étaient ATTEIGNABLES (mid-board advance, l'IA a fermé la
  distance) → contraste net avec la série row-9 INATTEIGNABLE (96001/97001/97000/98003/98000). NUANCE 93000 RESPECTÉE
  côté priorité mais VIOLÉE sur 1 finish (Mataneo deep-strike sur Kharn = la seule over-extension). NOUVELLE NUANCE
  ANTI-PSYKER : quand l'engine-set adverse est Psyker-lourd, un assassin anti-Psyker (Tjark HuntersBeyondDeath, +582 vs
  Psyker + aura de suppression) EST l'outil de kill-engine dédié — il rend les casters Psyker atteignables/tuables
  proprement (cf. H11)).
  **seed 70003** (INCONCLUSIVE — priorité d'engine CORRECTE au recon : Patermine snowball (CosmicHorror kill→decoy→
  MightFromBelow Purestrain summons) + Vitruvius (mark MasterAnnihilator + RadBombardment ligne croissante + repair)
  identifiés comme la wincon adverse, et le gate compris (= nier les kills au Patermine + tuer Vitruvius au range AVANT
  amplification). MAIS NI engine n'a été brisé AVANT qu'il fire : le barrage Thaddeus a chippé Vitruvius 9035→6570 sans
  le tuer (il a fire 3810 et tué mon carry) ; le Patermine a tué Nicodemus T1 → decoy → Genestealer = snowball live.
  Ni confirme ni réfute le principe central : la PRIORITÉ était bonne, c'est l'APPLICATION (briser les engines en temps
  voulu) qui a échoué — et l'échec est lié à la sur-extension propre (carry+healer présentés au focus avant que je
  puisse finir les engines) plus qu'à un mauvais ciblage. Renforce la NUANCE 93000/97002 : H02 est insuffisant si tuer
  les engines exige de présenter des fragiles au focus, et un engine de mark/ligne croissante doit être TUÉ ce tour,
  pas chippé — un chip non-létal le laisse fully amplifier).
  **seed 70002** (pour — **engines fragiles ATTEIGNABLES → H02 a PORTÉ le W**, + NUANCE engine-INERTE confirmée n+1 :
  les 2 Psyker-engines adverses (Yazaghor 6525 + Ahriman ennemi 8032, no-Resilient, snowball WeaverOfFate) identifiés au
  recon et tués TÔT — Yazaghor T1 (DoomSiren -4294 + Burchard Frag finish), Ahriman ennemi en réaction quand il a dive
  (Roswitha CondemnorStake +2183 vs Psyker, 4551 KILL) ; le carry autonome Lucien (Resilient) tué en dernier. ⚠ NUANCE
  ENGINE-INERTE (même classe que le revive Chaos inerte 98004) : le repair-hub Aleph-Null (carte wiki = CRITICAL) était
  STRUCTURELLEMENT INERTE car SEUL Mechanical du roster adverse → aucun bénéficiaire de repair → réduit à un gros corps
  soft (Roswitha Brazier one-shot 9037→0). DOCTRINE : au recon, vérifier qu'un engine repair/buff/revive a un
  bénéficiaire VALIDE sur SON équipe ; sinon demote sa menace (CRITICAL→LOW) et traite-le en corps soft normal (kill au
  range pour Explodes). Engines ATTEIGNABLES (l'IA a dive) → contraste avec la série row-9 inatteignable.)
  **seed 70001** (pour — **engine ATTEIGNABLE → H02 a PORTÉ le W** : leur Nicodemus (bloodSanguinary
  Healer-engine = leur sustain, no FJ, no Resilient observé, killable) identifié au recon comme la wincon
  de sustain adverse et tué T2 via un Dante chunk (9035→2301) + Jain Zar SilentDeath AoE qui l'a fini ET
  chunké leur Dante adjacent 7846→5558 dans le même cast → sustain effondré ; leurs carries Dante/Mataneo
  punis ensuite en réactions. Engines ATTEIGNABLES (l'IA a dive move-in, near-mirror Blood Angels) →
  contraste avec la série row-9 inatteignable. NUANCE adjacency-AoE : finir un engine de sustain avec une
  AoE adjacency-chain (SilentDeath) splash GRATIS le carry voisin — un cast = engine mort + carry chunké
  pour le reaction-kill suivant.)
  **seed 70000** (INCONCLUSIVE — priorité d'engine CORRECTE au recon : cascade Psychic (Tigurius AoE +
  PsychicFortress aura, Thaumachus WeaverOfFate-amplifier, Neurothrope Neuroparasite snowball) + double
  summon-engine (Bellator/Anuphet) identifiés comme la wincon adverse, et le gate compris (casser Tigurius
  AoE/block-source + Neurothrope snowball AVANT qu'ils tournent). MAIS exécution ratée pour DEUX raisons :
  (a) AUCUN engine tué cleanly R3 — dmg splité Thaumachus/Tigurius + PsychicFortress a bloqué mes finishers
  (Thaumachus laissé 1225, Tigurius chunké 6525→1694 mais jamais fini, re-fire et K! mon Anuphet) → violation
  de la NUANCE 93000/ordre-de-focus (FULL-focus la SOURCE Tigurius d'abord, pas split) ; (b) la VRAIE wincon
  late (Neurothrope Neuroparasite snowball, backline move2/Flying/r3) est restée INATTEIGNABLE pour mon roster
  melee/r2 — ÉNIÈME illustration de la NUANCE atteignabilité (cf. 96001/97001/97000/98003/98000) : un engine
  backline Flying r3 vs roster melee/r2 sans reach-tool = H02-inapplicable structurel. Principe non réfuté,
  insuffisant ici ; renforce les deux nuances : (1) ordre-de-focus = casser la SOURCE en premier (l'AoE qui
  arme le snowball + le block-aura), pas split ; (2) flagger la loss structurelle au recon quand la wincon late
  est un engine backline inatteignable.)
  **seed 70004** (INCONCLUSIVE — priorité d'engine CORRECTE sur l'engine ÉVIDENT (Tigurius Psyker-AoE +
  PsychicFortress) identifié et K!'d T2 (Ulf SavageKiller a pré-empté son StormOfWrath mid-cast, 2754+2958+813)
  + Angrax dans la même cascade de dive → guerre des engines GAGNÉE 5v5→4v1. MAIS la VRAIE wincon late = Trajann
  STANDALONE (Resilient + MomentShackle heal-to-full REPEATABLE ~+5684 sur cd + 4249/tour) = un mur self-healing
  INKILLABLE par mon roster chip-only burst-ÉPUISÉ (DoomSiren Direct Pierce100, mon seul bypass-block, déjà
  dépensé). NUANCE attainabilité/FENÊTRE distincte des reach-fail row-9 — non par reach (Trajann était atteignable)
  mais par BURST : un anvil self-healing Resilient n'a pas de « floor finissable » tant qu'on ne peut pas l'overkill
  en UN tour pendant que MomentShackle est en cd → H02 sur l'engine évident NE PORTE PAS le combat si la vraie wincon
  late est un self-healer qu'on n'a plus les moyens de tuer. Même classe que 97002 (Maladus/Actus repair-engine :
  « kill CE tour ou ne pas committer » est LITTÉRAL) — ici porté à un Resilient+self-heal : RECONNAÎTRE au recon
  qu'un tel anvil deviendra la wincon late d'un roster burst-léger et RÉSERVER le burst Direct/Psychic pour lui.
  Principe non réfuté, insuffisant ; le bon engine évident a été tué, le mauvais (l'anvil durable) ne pouvait pas l'être.)
  **seed 70007** (INCONCLUSIVE — priorité d'engine CORRECTE au recon : Isaak (genesPrimus board-flip CultDemagogue) +
  Yarrick (summon-engine) identifiés comme summon-engines et Trajann comme l'anvil inkillable late ; Yarrick tué PROPREMENT
  (Sy-gex 4-hit multi-hit kill+overkill) MAIS l'engine qui COMPTAIT — Isaak (board-flip) — était row-7 INATTEIGNABLE T1, et
  j'ai dépensé mon UNIQUE vrai tour sur le LESSER engine Yarrick + heal → Isaak a cast CultDemagogue → board-flip 4v5→3v12.
  Énième reach-fail nuance (cf. 91001/96001/97001/97000/98003/98000/70000) + leçon « tuer l'engine qui ENABLE l'écran, pas le
  plus facile » (déjà vu 91012 : H03 SUR-appliqué a empêché le kill d'Isaak avant CultDemagogue) : mon roster move2/r3 + r2
  Psychic n'avait AUCUN reach vers le summoner backline → à pré-positionner un dealer r3+/deep-strike T1 pour menacer un engine
  back-row T2, OU flagger la loss structurelle au recon quand reach=zéro vers le board-flip engine. Principe non réfuté,
  insuffisant ici — la guerre des engines a été perdue sur le SEUL engine qui décidait le board.)
  **seed 70005** (pour, NUANCE -1-corps : DOUBLE engine/wincon ATTEIGNABLE et tué dans le bon ordre — Abraxas
  (summon-engine soft 7026) tué en réaction T3 quand il a dive adjacent (Ulf SavageKiller 4249→0), ET Trajann
  (wincon wall self-heal) tué T4 via la séquence anti-block (chunké par réactions 7221→4578, puis Typhus Psychic
  Pierce100 NoBlocking 4578→3307, puis Ulf GreatFrostAxe 4-hit actif 3307→0 Overkill pendant MomentShackle en cd) ;
  les DEUX engines/wincons CASSÉS, priorité correcte — MAIS payé trop cher en corps : combat DÉMARRÉ à -1 corps
  (mon carry Lucien focus-killé T1 par over-extension au déploiement, cf. H03) → l'attrition était déjà perdue avant
  que les engines tombent (3v6 → 1v2). NOUVELLE NUANCE : H02 gagner la guerre des engines NE SUFFIT PAS si on
  commence le combat à -1 corps — le carry/engine PERDU AU T1 doit être prévenu (H03 propre) AVANT de raisonner
  priorité d'engine ; même classe que la nuance 93000 « exposition forward minimale » mais portée au DÉPLOIEMENT.
  Contraste positif fort avec 70004 sur le MÊME anvil Trajann : ici le burst anti-block (Typhus Psychic) a été
  RÉSERVÉ et combiné à un actif multi-hit pendant MomentShackle en cd → Trajann TUÉ, alors qu'en 70004 le DoomSiren
  spent tôt = anvil inkillable. Engine ATTEIGNABLE + bon ordre → la priorité H02 était bonne, insuffisante seule.)
  **seed 70008** (INCONCLUSIVE — priorité d'engine CORRECTE et les DEUX summon-engines (Archimatos + Dreir) ATTEIGNABLES
  et tués PROPREMENT : Exitor CordClaw a one-shot Archimatos T2 AVANT tout cycle de summon (et comme Archimatos était la
  VICTIME, aucun Possession body n'a spawné), Imospekh multi-hit a tué Dreir past Resilient+ToughToKill → guerre des
  engines GAGNÉE, mid-game gagné. MAIS le match a été perdu à un wincon late ÉMERGENT — Burchard MkXGravis (12k double-armor
  tank) — que mon roster survivant Power/Physical ne pouvait pas cracker faute d'outil Direct/Psychic vivant. ÉNIÈME
  H02-insuffisant de classe NOUVELLE : ce n'est NI un reach-fail (les engines évidents étaient atteignables et tués), NI un
  self-healer (70004/70005 Trajann) — c'est un **tank high-armor STANDALONE qui DEVIENT le wincon late dès qu'on perd
  l'armor-bypass**. Même famille que 70004 « réserver le burst anti-armor » mais ici le levier = un TYPE de dégât
  (Direct/Psychic/Crit), pas un cooldown : tuer les engines évidents ne suffit pas si le tank MkXGravis devient
  ungrindable une fois les outils bypass-armure morts. Renforce la doctrine 70004/97002 : RÉSERVER l'outil anti-armor.)
  **seed 70050** (INCONCLUSIVE — priorité d'engine CORRECTE au recon : Isaak (genesPrimus board-flip CultDemagogue) +
  Isabella (adeptHospitaller sustain/revive) identifiés comme le wincon-set adverse, mais STRUCTURELLEMENT INATTEIGNABLES
  ce matchup : engines softs (Isaak 7026, Isabella 8533, no-Resilient) row 8-9 derrière un anvil Typhus 12k, mon roster
  melee-heavy n'a qu'UN reach-tool (Neurothrope move2/r3 Flying = reach ~5 depuis row 1, PAS row 9) → Isaak a cast
  CultDemagogue au tour enemy-T1 AVANT que je puisse jamais menacer un engine. ÉNIÈME reach-fail (cf. 96001/97001/97000/
  98003/70000/70007) : un roster melee/r2 + 1 move2/r3 vs des soft backline engines + un Flying-teleport screen
  (Shadowsun) = H02-inapplicable STRUCTUREL ; AGGRAVÉ car Shadowsun a delete CE seul reach-tool (Neurothrope) au 1er tour
  ennemi → même le reach théorique a disparu. Principe non réfuté, insuffisant ici — la wincon adverse doit être
  ATTEIGNABLE ; à flagger la loss structurelle au recon quand reach=zéro vers les engines backline.)
  **seed 70051** (pour — **engines+carry ATTEIGNABLES → H02 a PORTÉ le W** : roster adverse 100% soft (aucun
  Resilient : Sibyll 5522/Aethana 8034/Tjark 8536/Nicodemus 9035/Mephiston 9537) ET 100% melee/r2 → CONTRAINT de
  diver dans mon mur Resilient (Maladus/Dreir/Lucien) → engines exposés à leur sortie. Les buff-engine Aethana
  (PathOfCommand, deep-strike sortie FORWARD à (3,4) → atteignable) + Psychic-nuke Sibyll (5522, le plus soft)
  tués T3, puis le carry Mephiston (Psychic Pierce100 NoBlocking = LE wincon) 8230→0 T4, Nicodemus (Healer-engine)
  fini T5 → wincon adverse démontée dans le bon ordre. INVERSE EXACT de la série row-9 inatteignable (96001/97001/
  97000/98003/70000/70007/70050) : un matchup all-soft+all-melee vs un mur Resilient = engines STRUCTURELLEMENT
  ATTEIGNABLES — pas un reach-fail. + NUANCE ENGINE-INERTE n+1 (cf. 70002/98004) : Tjark anti-Psyker
  (HuntersBeyondDeath +582/hit vs Psyker) ENTIÈREMENT INERTE car MON roster sans aucun Psyker → demote carte
  high→low, traité en corps soft. Symétrie de la règle « engine d'amplification ne vaut que s'il a un
  bénéficiaire/cible valide » portée aux AURAS ANTI-X : compter les cibles valides côté adverse au recon.)
  **seed 70052** (INCONCLUSIVE — priorité d'engine CORRECTE au recon : les 2 soft backline engines (Eldryon
  eldarFarseer 7530 Doom/Executioner + Abraxas thousInfernalMaster 7026 summon-cascade, AUCUN Resilient) identifiés
  comme la wincon adverse ; MAIS STRUCTURELLEMENT INATTEIGNABLES ce matchup : un cluster ennemi ALL-RANGED (Re'vas
  r2 turret + Abraxas r2 + Certus r3 + Eldryon r2 + Adamatar) SCREENÉ par la turret Re'vas EarlyWarningOverride (2
  Shield Drones + OW armé) vs MON roster melee-heavy SANS reach tool (seulement Snappa r3 + Angrax deep-strike). Le
  move-guard a chiffré le coût d'engage : plan A (push Snappa+Angrax pour tuer Abraxas) = NET −3.92 = je perds
  Snappa+Sibyll+Angrax pour 1 engine = 3-for-1 focus disaster → ÉNIÈME reach-fail de classe 96001/97001/97000/98003/
  70000/70007/70050 : H02-inapplicable STRUCTUREL quand tuer l'engine soft exige un 3-for-1 forward dans un screen
  all-ranged. ⚠ AGGRAVÉ par une APPLICATION ratée : un chip NON-LÉTAL sur Abraxas (Snappa seul 7026→3183, max<HP)
  a laissé l'engine caster MasterOfTheTutelaries → board-flip +3 bodies = même classe que 97002 « kill CE tour ou
  ne pas committer » étendue aux summon-engines (un chip non-létal est strictement pire que le hold). Principe non
  réfuté, insuffisant ici ; renforce les deux nuances : flagger la loss structurelle au recon quand reach=zéro vers
  les engines back-row, et ne JAMAIS chiper non-létalement un summon-engine — le kill garanti ou rien.)
  **seed 70056** (pour — **engine ATTEIGNABLE → H02 a PORTÉ le W** : Ragnar (spaceBlackmane) = WarHowl-engine, l'amplificateur
  de toute la ligne mêlée Character adverse (Atlacoya-enemy/Tanksmasha/Kut), identifié au recon comme la wincon SOURCE et tué
  EN RÉACTION T2-T3 AVANT son 1er cast WarHowl → la ligne mêlée n'a JAMAIS été buffée. Engine ATTEIGNABLE car le roster adverse
  était 100% melee + 1 ranged → CONTRAINT de diver dans mon cluster ranged+Overwatch cohésif (même structure que 70051 all-soft/
  all-melee : engines exposés à leur sortie). NUANCE ENGINE-INERTE n+1 (cf. 70002/98004/70051) : Darkstrider StructuralAnalyser
  markerlight-engine STRUCTURELLEMENT INERTE — il était le SEUL ranged d'une équipe melee → aucun 2ᵉ T'au RANGED bénéficiaire du
  +728 → self-fed = demote carte high→low, traité en corps soft tué dans le dive. Symétrie « amplificateur sans bénéficiaire
  valide » désormais portée aux markerlight-engines aussi.)
  **seed 70053** (pour — **DOUBLE engine ATTEIGNABLE → H02 a PORTÉ le W** : les 2 summon-engines adverses (Bellator
  ultraInceptorSgt DeathFromAbove + Archimatos blackPossession Incursion/Possession, AMPLIFIÉS par Abaddon FirstAmongTraitors)
  + l'OW reaction-engine Imospekh identifiés au recon comme la wincon-SOURCE et tués dans le bon ordre AVANT que le snowball
  compound : T4 Snotflogga normal a one-shot Archimatos (8034→0) — et comme il était la VICTIME, ZÉRO Possession body n'a
  spawné (confirme que Possession ne fire que quand Archimatos est l'ACTEUR/killer) — DANS le même tour Aesoth a chunké
  Imospekh 5639→855 + Calandis l'a fini (les 2 summon/OW engines morts T4, guard NET +7.83), puis T5 Bellator+Inceptors. Les
  engines étaient SOFTS (no-Resilient) et l'IA all-melee/move4-Flying/deep-strike a DIVE → ATTEIGNABLES (INVERSE EXACT des
  reach-fail row-9 96001/97001/97000/98003/70000/70007/70050 ; même structure que 70051/70056 : un roster contraint de diver
  expose ses engines à leur sortie). NUANCE 93000 « exposition minimale » globalement respectée — engines tués depuis des
  tuiles atteignables sur le dive, la SEULE over-extension (Aesoth deep à (3,3) 758 HP) était couplée à un engine-kill qui en
  valait le coût, non-décisive. NB Bellator DeathFromAbove = board-flip CROISSANT (3 Inceptors 5483 move4 round 3) que le
  guard 2-ply ne voit pas, mais rendu atteignable PAR le dive même.)
  **seed 70055** (INCONCLUSIVE — NOUVELLE SOUS-CLASSE d'H02-insuffisant « un engine ATTEIGNABLE mais IMMUNE à mon
  damage-TYPE » : j'ai tué les soft autonomous threats dans le bon ordre (Yazaghor T2 via Incursion, Godswyl T3,
  Adamatar T4) → 5v4/4v3/3v2, MAIS le VRAI counter-engine de la wincon adverse — Atlacoya (DaughterOfTheAbyss,
  anti-Psyker) — était structurellement UN-KILLABLE pour mon roster Psyker-heavy : son −1892 Psychic flat a réduit
  mes 2 Psykers à 1-2 dmg ([1-1]/[2-2] toute la partie) ET son Terrifying a blunté la mêlée → mon profil de dégâts
  ENTIER était neutralisé. Distincte des reach-fail row-9 (Atlacoya était EN PORTÉE) ET du self-healer Trajann
  (70004/70005) ET du tank high-armor MkXGravis (70008) : ici le levier manquant n'est ni la portée, ni un cooldown,
  ni un type de bypass-armure — c'est que TOUT mon roster déale du Psychic (négaté) ou de la mêlée (Terrifying-blunted)
  = AUCUNE source non-counterée. Même FAMILLE que la nuance attainabilité-vs-immunité (un ennemi peut être en-range
  ET immune à mon damage profile), nouveau sous-cas « damage-TYPE counter par aura défensive anti-catégorie ». LEÇON =
  au recon, traiter une aura anti-Psychic (Atlacoya DaughterOfTheAbyss) comme un damage-counter STRUCTUREL d'un roster
  Psyker-heavy (miroir de l'engine-inerte : une aura anti-X est LIVE quand JE fielde la catégorie ciblée) → flagger la
  loss probable. Principe H02 non réfuté, insuffisant ici : la guerre des soft threats gagnée, le counter-engine
  injouable par damage-type.)
  **seed 70054** (pour — **anvils KILLABLES ATTEIGNABLES → H02 a PORTÉ le W** : vs un mur d'attrition all-melee SANS
  engine central de pump/summon/sustain, j'ai tué dans le bon ordre les fragiles (Yazaghor T3 6525, Deathleaper T4
  8032) PUIS overkillé les anvils KILLABLES (Tyrant Guard non-Resilient 12548 en UN tour multi-source T5 ; Thoread
  10038 chunké+fini T6-T7) → mur effondré, W. Tous ATTEIGNABLES car l'ennemi all-melee DOIT closer (même structure
  que 70051/70056/70053 : un roster contraint de diver expose ses menaces). NUANCE engine-INERTE-au-recon confirmée
  n+1 sur DEUX conditionnels : Thoread `UnbreakableDuty` (+7275HP/+1455dmg si 2+ Imperial alliés morts) STRUCTURELLEMENT
  INERTE car Thoread = SEUL Imperial de son roster → le trigger ne peut JAMAIS s'armer ; Yazaghor `WeaverOfFate` INERTE
  car aucune source Psychic ne touche mes propres units (le trigger compte 3+ de SES ennemis = mes units). DEMOTÉS à
  corps killables au recon → focus efficace. Même famille que l'engine-inerte-sans-bénéficiaire (98004/70002/70051/70056)
  et l'aura-anti-X-sans-cible : COMPTER les triggers VALIDES d'un conditionnel/engine AU RECON. NUANCE distincte des
  anvils-late-injouables (Trajann self-heal 70004/70005, MkXGravis 70008) : ici les anvils étaient non-Resilient et
  FOCUSABLES → un overkill one-turn multi-source les tue (cf. doctrine-learned §6 anvil-overkill), contredisant le
  réflexe wiki « ne pas investir d'output sur un GuardianOrganism BigTarget » quand c'est l'anvil focusable sur ma ligne
  et que le chip-only perd.)
  **seed 70060** (pour — **engines ATTEIGNABLES → H02 a PORTÉ le W** : DOUBLE wincon-source brisée AVANT qu'elle s'arme —
  Kharn (snowball carry+engine TheBetrayer) NIÉ son 1er kill et tué EN RÉACTION T2 sur son dive (TheBetrayer jamais
  armé = juste une normale absorbable) + Tarvakh (carry NON-pumpé, pas de Hollan/WarHowl → base 9537 chunk-killable) tué
  dans le MÊME mur de réaction T2 AVANT tout kill = leur snowball mort-né ; PUIS le summon-engine Abraxas (soft 7026,
  no-Resilient) tué en UN tour T3 via burst multi-source GARANTI (Supercharge 6366 + 2 normales) AVANT MasterOfTheTutelaries
  = kill-not-chip respecté, ZÉRO board-flip. Engines/carries ATTEIGNABLES car le roster all-melee (4/5 melee + Abraxas r2 +
  Deathleaper deep-strike) était CONTRAINT de diver dans mon Overwatch-turret cluster (même structure favorable que 70051/
  70056/70053/70054 : un roster contraint de diver expose ses menaces). NUANCE engine-INERTE-au-recon n+1 : Nauseous
  TaintedNarthecium-revive (75% Chaos) STRUCTURELLEMENT INERTE car Nauseous = SEUL Chaos de MON roster (4 alliés non-Chaos →
  aucun Chaos adjacent à revive) → recon-flaggé, jamais craint (même classe que 98004 ; ici l'engine inerte était DANS mon
  roster). NUANCE H02-INSUFFISANT-ÉVITÉE sur le tank high-armor : Burchard MkXGravis (12k, bypass Crit/Direct/Psychic
  uniquement, mon roster ZÉRO bypass) = le wincon-late-émergent de classe 70008 — MAIS évité en gagnant la guerre des
  nombres D'ABORD (mur de réaction → 2 carries morts T2 zéro perte) → Burchard affronté en 6v1 (grind trivial : Nauseous
  −armure aura + Storm of Fire +582 → 12038→1362 en un tour focus) au lieu d'en dernier mur ingrindable. CONFIRME la
  doctrine 70008 par l'INVERSE : un MkXGravis standalone n'est ingrindable QUE comme dernier mur après la guerre des nombres
  perdue ; overwhelm via nombres/réactions le neutralise même sans bypass-armure.)
  **seed 70059** (pour — **engine ATTEIGNABLE → H02 a PORTÉ le W** : Ragnar (spaceBlackmane) = WarHowl-engine, la wincon
  SOURCE d'un roster all-melee (pump toute la ligne Character +1164/hit + Unstoppable + crit), identifié au recon et tué T3
  AVANT son 1er cast WarHowl → la ligne all-melee n'a JAMAIS été buffée (chunké T2 via Typhus PlagueWind Psychic, fini T3 via
  Typhus/Archimatos Psychic). Engine ATTEIGNABLE car le bulk all-melee + anvil-heavy était CONTRAINT de diver dans mon cluster
  Resilient/TermArmour (même structure favorable que 70051/70056/70060 : un roster contraint de diver expose ses engines à leur
  sortie). NUANCE engine-INERTE-au-recon n+1 (cf. 70002/98004/70051/70056) : Abaddon FirstAmongTraitors (+364→+1313 dmg aux
  alliés Chaos adjacents) NEAR-INERTE car SEUL allié Chaos = Maladus (Ragnar=Imperial, TG=Xenos, Roswitha=Imperial) → demote
  l'aura au recon ; une fois Maladus mort, aura FULLY inerte → Abaddon réduit à un anvil Resilient soft, traité en DERNIER
  (4v1, overkill Psychic stacké). NUANCE-anvil-KILLABLE confirmée (cf. 70054) : le TG (12.5k BigTarget NON-Resilient) tué en UN
  tour multi-source quand c'est l'anvil focusable adjacent (PlagueWind 3154 + DestroyerHive 3369 + Kharn KillMaimBurn K! 6025) —
  MAIS tuer cet anvil-non-engine a coûté un carry forward (Kharn over-étendu, cf. H03/93000) : H02 sur un anvil-killable peut
  exiger une exposition forward, contrairement à un engine soft tuable depuis le shallow.)
  **seed 70058** (pour — **engine-PAIR ATTEIGNABLE sur le dive → H02 a PORTÉ le W** : la wincon adverse = un ENGINE PAIR
  ranged armor-ignore + delayed-nuke (Njal spaceStormcaller Psychic NoBlocking AoE + LordOfTempests snowball + Sho'syl
  tauMarksman SeekerMissile 6184 délayé + MV71 drone-summons), tous deux move2 back-row mais SCREENÉS par 3 melee/Flying →
  quand ce screen mêlée a dive dans mon reaction-engine HOLD (Sy-gex Overwatch + Aesoth StandVigil) et est MORT T2-T3, les
  2 engines back-row sont devenus ATTEIGNABLES et tués dans le bon ordre T4 (Aesoth K! Sho'syl le summoner/seeker → drones
  inertes ; stun VexillaMagnifica + Sy-gex 4-hit HeavyGravCannon vs Njal TerminatorArmour 6727→0). MÊME STRUCTURE que la série
  des dives-forcés gagnés 70051/70056/70053/70060 : un roster avec ≥3 melee/Flying CONTRAINT de diver expose ses engines
  back-row à la mort de son screen → INVERSE des reach-fail row-9 inatteignables. Le carry Titus (FuelledByFury revive) aussi
  tué PERMANENT en routant la riposte FJ sur le seul corps adjacent high-HP, Aesoth tank → no kill → no revive. NUANCE
  engine-INERTE n+1 (cf. 70002/98004/70051/70056/70054) : Yazaghor ennemi WeaverOfFate INERTE — aucune source Psychic n'a
  touché mes propres units → demote en chaff soft, tué cheap T3.)
  **seed 70057** (pour — **wincon-set ENTIER ATTEIGNABLE → H02 a PORTÉ le W 5v0** : roster adverse all-melee/deep-strike
  (Dante carry deep-strike + Ragnar WarHowl-engine + Helbrecht CrusadeOfWrath buff-engine + Thaddeus/Sarquael ranged
  amplifié) CONTRAINT de closer dans ma range → wincon-set tué dans le bon ordre depuis tuiles SHALLOW/courantes : Dante
  (carry forward, LordOfTheHost amplifier) T3, Helbrecht (CrusadeOfWrath buff-engine, overkillé pour denier FJ) T4, puis
  BOTH Ragnar (WarHowl engine) + Sarquael (ranged+OW) T5 → engines/carries jamais amplifiés. MÊME structure ATTEIGNABLE que
  70051/70053/70056/70060 : un roster contraint de diver expose ses engines. NUANCE NOUVELLE « défang par les bénéficiaires » :
  WarHowl (Ragnar) ne pump QUE les melee Characters sans ranged normal → tuer ses BÉNÉFICIAIRES (Dante+Helbrecht) AVANT
  l'engine le défang (Ragnar réduit au self-buff au moment où je le tue) — une 2ᵉ voie pour neutraliser un pump-engine, par ses
  cibles plutôt que par sa source. Engines screen-on-attack côté MIEN (Sho'syl MV71 drone + Tan Gi'da Vanguard) ont soaké ~14k
  du focus ennemi = ont gardé mes amplificateurs Vitruvius/Abraxas shallow → exposition forward MINIMALE respectée (NUANCE
  93000), sauf 1 slip Tan Gi'da à (5,3) non-décisif.)
  **n=27 (matchups distincts, +2 inconclusive : reach-fail 70052, damage-type-immune 70055)** → confirmée.
- **→ doctrine si confirmée** : SKILL §6 (priorité de cible : la menace qui escalade/heal/kite >
  le chaff ; dans un miroir de sustain, focus l'engine adverse > re-tuer les revivables).

## H03 — Ne pas diver une unité isolée en avant (et PUNIR le dive isolé adverse) — `confirmée` (n=46 distincts, contre:0) → À PROMOUVOIR (URGENT — tag over-extension domine la vague)
- **claim** : une unité projetée seule au contact/à portée se fait **focus-kill** au tour adverse,
  même tanky. Engager en **groupe mutuellement soutenu** ou pas du tout. **Réciproque** : punir
  systématiquement le **dive isolé ADVERSE** (deep-strike sans charge, grapnel solo) = trade gratuit.
- **test** : observer sur les prochains matchs (corrélation dive-isolé → perte de l'unité).
- **evidence** : G01 (Ragnar), G03 (Lucien, Morvenn) ; **seed 70011** (`punish-isolated-dive` confirm :
  Tjark grapnel-dive solo → Destroyer+Apothecary K!, zéro perte) ; **seed 70014** (`opus-vs-sonnet-70014`
  confirm : Mataneo deep-strike isolé sans charge → focus-kill 5v1, puis toute l'équipe adverse dive
  dans la suite de réactions Ulf SavageKiller → 18552 en réaction, W 5-0 zéro perte) ;
  **VAGUE 91000-91014 (réciproque ET propre côté, omniprésent)** : 91002 (punish T2-T4 efficient),
  91003 (les DEUX sens : j'ai perdu Baraqiel dive solo danger-5 / l'IA dive Trajann seul dans mon cluster →
  10038 en réaction), 91004 (Ahriman parqué seul → focus-kill 2-for-0), 91005 (Thaddeus poussé danger-5 +
  Ripper-divers punis), 91006 (Azkor dive isolé dans le gap → ~11k 1 tour + gift LeadingTheCharge), 91008
  (Sword Brother dive MindControl → overkill clean ; mais Corrodius poussé hors revive = perte), 91009
  (Gibbas solo (1,7) + Mataneo forward = lead gaspillé), 91010 (REFUS de dive le cluster -50% = W ; mais
  Nicodemus dans l'arc overwatch armé = 9035->0), 91011 (Dreir+Ulf parqués row3 = 2-for-0 → 4v6), 91013
  (Deathleaper deep-strike isolé puni ; mais j'ai PERDU Forcas/Sy-gex/Tjark forward — « le sens que je
  rate sur MES unités »), 91014 (deep-striker Mataneo isolé focus-kill T1) ;
  **VAGUE 93000-93001** : 93000 (PROPRE-côté violé 3× : Volk dans l'arc Overwatch armé de Sy-gex → 5418 free
  + Tanksmasha laissé forward (2,6) + Mephiston laissé forward (3,6) stun-locké Aesoth → 3 corps perdus = la
  loss), 93001 (RÉCIPROQUE : refus de diver mes fragiles, cluster serré → l'IA charge tout son mur mêlée
  dedans → ~25097 réaction, 3 kills, 1840 subis = W ; minor slip propre-côté : Atlacoya forward bait + Lucien
  chunké à 1) ; **95001** (LES DEUX sens : PROPRE-côté violé 2× — Dreir poussé seul (2,5) T1 → focus-killé en
  tour IA 1 avant d'agir (et a GÂCHÉ son LeadingTheCharge, qui exige NE PAS bouger), Aun'Shi avancée (3,5)
  adjacente T2 à 3394 PV → tuée par les Ork Boys ; RÉCIPROQUE bien jouée — Tjark dive forward à 237 PV →
  fini par une réaction Aberrant ; W malgré tout grâce à H02) ; **96000** (PROPRE-côté VIOLÉ : Dante
  avancé (3,5) T1 dans le reach Farseer (Psychic r2) + Atlacoya (melee move3) → 8312 dmg subis, 9035→1527
  HP quasi-mort T1 ; RÉCIPROQUE bien jouée — l'IA a dive Atlacoya, punie par Overwatch Azrael FJ + réactions
  2781 exact kill ; W grâce à H02 + au burst de réactions massées, PAS à une ligne propre) ; **96001**
  (PROPRE-côté VIOLÉ : Re'vas over-étendue à (2,8) à 2659 PV T1 → focus-killée par Isabella au tour
  suivant ; énième confirmation du côté propre — over-extension a directement coûté une unité, +Toth
  bougé 2× = ghost TimeFlux gâché ; la moitié RÉCIPROQUE non testable, l'IA a approché en groupe) ;
  **96002** (PREMIÈRE application PROPRE RÉUSSIE — côté propre RESPECTÉ, pas violé : Sy-gex maintenue
  turret (5,1→5,3 max) + Burchard turret (4,5), JAMAIS avancés dans la killzone Trajann → Overwatch
  Burchard armé quasiment chaque tour → 4 triggers décisifs ont tué Aesoth/Trajann/Helbrecht en cascade
  de réactions SANS dépenser d'actions offensives = la position défensive maintenue a porté le W ; preuve
  que « les réactions gagnent l'attrition SI le positionnement reste défensif tout le combat »).
  **97001** (INCONCLUSIVE sur le hold-gagne-l'attrition — j'ai tenté de répliquer le turret défensif 96002
  mais il a ÉCHOUÉ ici pour 2 raisons CONDITIONNELLES : (a) mon Overwatcher front était MÊLÉE (Forcas), pas
  un turret RANGED — il a été chunké 9035→333 dans l'échange de réactions T1 puis tué, au lieu de punir
  safe depuis une portée ; (b) le sustain-engine adverse (Hollan TwistedScience) était INTOUCHABLE row 9 et
  out-pumpait mes briques statiques. → la leçon 96002 « les réactions gagnent depuis une turret » est
  CONDITIONNELLE à des Overwatchers RANGED + un ennemi ATTEIGNABLE/tuable ; ne PAS transplanter le turret
  défensif sur une unité MÊLÉE qui doit se tenir dans la killzone. Côté PROPRE non testable proprement —
  Forcas/Aberrant exposés forward, mais le hold était globalement l'intention).
  **97002** (PROPRE-côté VIOLÉ ENCORE : après un kill propre de Winged Prime T2, Mataneo HammerOfWrath
  commit DEEP à (2,6) solo pour chasser Actus — les 2 Jump Pack Intercessors disparaissent au début du
  tour suivant de Mataneo = support éphémère = effectivement solo → focus-killé par Calandis 4494 +
  Tyrant Guard 2748+1793 exactement comme la doctrine le prévient. n+1 du failure-mode dominant. La moitié
  RÉCIPROQUE non testable — l'ennemi a avancé en groupe durable, aucun dive isolé adverse à punir).
  **97000** (PROPRE-côté VIOLÉ 3× dans un même combat = la loss : après avoir gagné l'échange engine 5v3,
  j'ai poussé Mephiston (carry/seul bypass Psychic) à (1,5) → focus-killé par la barrage Thaddeus next-turn
  (6578→0) ; laissé Macer forward (3,5) après JakhalStimms (à 4573) → Vindicta focus-kill ; poussé Helbrecht
  (ranged fragile) à (3,5) pour finir Vindicta → barrage Thaddeus 5382→0. Les 3 fragiles tradés UN-À-UN dans
  la kill-zone ranged ouverte au lieu d'avancer en masse écranée. La RÉCIPROQUE bien jouée au DÉBUT — l'IA a
  over-étendu Tigurius+Deathleaper en mid-board T1 → punis par JakhalStimms (double kill T2) — mais la moitié
  PROPRE a directement causé la défaite. n+1 du failure-mode dominant : même APRÈS avoir gagné la guerre des
  engines, l'over-extension de mes propres fragiles perd l'attrition).
  **98003** (PROPRE-côté VIOLÉ n+1, forme deep-strike : les DEUX carries deep-strike (Aethana+Dante) committés
  forward T1 → le teleport-move les a auto-finis NON-adjacents (ActionsAvailable=0, zéro dégât) puis focus-killés
  → deux kills gratuits. Variante spécifique du failure-mode dominant : un deep-striker MÊLÉE dépensé sans alpha
  soutenu délivrable le même tour = stranded solo. La RÉCIPROQUE non testable — l'ennemi a snowballé en masse,
  aucun dive isolé adverse à punir).
  **98004** (LES DEUX sens, dans un W — RÉCIPROQUE A PORTÉ LE W : l'IA a dive dans mon cluster groupé aux tours
  adverses → ~19590 dmg en réactions (Overwatch/contre) ont tué Helbrecht+Vitruvius T2 puis Morvenn seule T3 =
  3 kills SANS dépenser mes actions offensives ; PROPRE-côté ENCORE violé T2 : Asmodai(3,4)+Mephiston(3,3)
  poussés dans la reach du trio ranged (Vitruvius r2/line, Morvenn r3, Helbrecht r2) → 17189 dmg en un tour
  (Asmodai 9035→332, Mephiston 9537→2454) + Nicodemus mon Healer sur-étendu (1,5)→(2,5) ; W malgré tout car
  les 2 carries mourants ont EXTRAIT leur valeur (mark Asmodai + heal-block Mephiston + reaction-kills) — c'est
  H02 + la RÉCIPROQUE qui sauvent, PAS une ligne propre. n+1 du failure-mode dominant over-extension, ici survécu
  grâce aux réactions massées sur le cluster groupé).
  **98002** (LES DEUX sens, dans un W — RÉCIPROQUE + ligne propre globalement RESPECTÉE → ont PORTÉ le W :
  formation serrée maintenue T1 (TG BigTarget en écran forward, fragiles Abraxas/Yazaghor adjacents, jamais
  poussés en avant) → l'IA a dive TOUTE sa force dans le cluster sur 2 tours adverses → ~22k puis ~20k de
  réactions = 5 kills (Thaumachus+Dante enemy-T1 ; Anuphet+Toth+un Warrior enemy-T2) SANS dépenser mes actions
  offensives = c'est la position défensive tenue qui a gagné l'attrition, comme 96002. SLIP PROPRE mineur :
  Kharn a fini enemy-T1 over-étendu/isolé à (5,5)-(6,5), 2310 HP → 276, et je n'ai PAS pu le retreater sur ma T2
  (chaque move mutated=false — Pinned -1 move + move start-of-turn TheBetrayer probablement déjà consommé) ; il a
  survécu UNIQUEMENT par le choix de cible de l'IA, vs un jeu optimal il meurt là gratis. 2ᵉ application PROPRE
  RÉUSSIE de la session après 96002 — la formation défensive tenue (sauf Kharn) prouve à nouveau « les réactions
  gagnent l'attrition SI le positionnement reste défensif ». Le slip Kharn = n+1 du failure-mode propre, mais ici
  isolé à UNE unité non-engine, non décisif).
  **98000** (PROPRE-côté VIOLÉ n+1 = la loss, RÉCIPROQUE bien jouée : j'ai PUNI le dive early décisivement — Dreir +
  les 3 Death Riders qui ont chargé mon cluster ont été AoE-cleavés par Maugan Ra HarvesterOfSouls en UN cast + taunt
  CrushingClaws sur le summoner Dreir + Overwatch Maugan Ra a tué les Scarabs en réaction = 5v2-up. MAIS j'ai ensuite
  avancé MA LIGNE ENTIÈRE — Maugan Ra (carry ranged r3 fragile) à row 3 + Aethana (buff-engine fragile) à row 2-3 —
  dans la kill-zone ranged mid-board → le focus ranged adverse (~24k : Snappawrecka+Darkstrider+Aleph-Null+Scarabs) a
  deleté Maugan Ra+Tyrant Guard+Aethana en UN tour → bascule 5v2-up → 2v4-down. n+1 du failure-mode dominant, MÊME
  forme que 97000 : même APRÈS avoir gagné l'échange engine/dive, trader mes fragiles dans le focus ranged perd
  l'attrition. Le carry ranged r3 n'avait PAS besoin de row 3 chaque tour ; le buff-engine devait rester untouchable
  row 0-1, pas reachable row 2-3).
  **98001** (PROPRE-côté VIOLÉ UNE fois dans un W, RÉCIPROQUE non testable proprement : après avoir chunké Kharn 9035→2399
  T2, j'ai committé Mataneo (9035 HP) à (2,5) — deep et adjacent à Hollan/Xybia — juste pour LANDER le finish sur Kharn
  → focus-killé prévisiblement au tour suivant = un corps de héros tradé pour un finish que l'auto-Grot ou une unité moins
  exposée aurait pu poser. ⚠ Aggravé par une 2ᵉ erreur couplée : la marge d'overkill sur Kharn (FJ/TheBetrayer carrier)
  était insuffisante (~3900 sur 2399 < 2× = NON-overkill) → la death-riposte a fire ET tué mon Grot + chunké Mataneo,
  l'affaiblissant AVANT le focus-kill. n+1 du failure-mode dominant over-extension MÊME dans un W ; la RÉCIPROQUE n'a pas
  été un test isolé — l'IA a avancé en groupe et s'est fait grinder par mes engines/réactions, pas de dive isolé unique
  punissable. W porté par H02 (kill du wincon-set entier) + H11, PAS par une ligne propre).
  **70003** (PROPRE-côté VIOLÉ = la ROOT CAUSE, RÉCIPROQUE non testable : carry ranged fragile (Thaddeus 6525) + seul
  healer (Nicodemus) laissés STATIONNAIRES mid-board (rows 3-4) dans le reach d'un focus 6-sources au lieu de retraiter
  vers row 0-1 T1 → les DEUX tués en un tour adverse (~18528 dmg : Vitruvius RadBombardment ligne 3810 + Njal r3 +
  Patermine MightFromBelow kill) → snowball live, 3v6 incontestable. n+1 du failure-mode dominant. ⚠ NOUVELLE FORME
  D'ÉCHEC PROPRE = le move-guard `--climb` a donné un verdict « propre » (NET +0.40) qui ne simule QUE l'UNIQUE tour
  d'AVANCE de l'IA (sans contact) → AVEUGLE au focus de contact retardé qui atterrit au 2ᵉ tour IA quand l'ennemi part
  à >1 move ; trusté ce « propre » au lieu de retraiter les fragiles par défaut. Même si le runner a déployé mes units
  mid-board (placeholder rows 0-1 trompeur), le fix — retraiter carry+healer T1 — était disponible et non pris. La
  moitié RÉCIPROQUE non testable : l'IA a fermé la distance en groupe puis focus-fire, pas de dive isolé unique à punir).
  **70002** (LES DEUX sens, dans un W — RÉCIPROQUE A PORTÉ LE W : ligne groupée mutuellement soutenue (Burchard MkXGravis
  anvil + Adamatar +800-ranged aura + Roswitha/Ahriman ranged) → l'IA a dive 2× dans le cluster → ~12k réactions ont tué
  l'Ahriman ennemi (Roswitha CondemnorStake 4551) puis ~4.3k réactions ont tué Lucien EXACTEMENT (4308→0) = 2 kills
  décisifs SANS dépenser mes actions offensives ; ⚠ NOTE : le move-guard `--climb` a CETTE fois été suivi correctement —
  il a flaggé mon Ahriman engine move (3,3) à 31% loss → pulled back → l'engine a survécu tout le combat (contraste avec
  70003 où le « propre » à longue portée a été mal-trusté). PROPRE-côté violé UNE fois : Abraxas (fragile Psyker 7026)
  laissé reachable mid-board (4,4) → focus-killé par Lucien VisionsOfHeresy double-attack + TG = ma SEULE perte ; n+1 du
  failure-mode dominant over-extension, mais coûté un seul fragile non-engine dans un W 4v1-dominant — devait être écranté
  derrière Burchard ou pull row 0-1).
  **70001** (LES DEUX sens, dans un W — RÉCIPROQUE A PORTÉ LE W : ligne tenue + Azrael Overwatch HELD armé (gate=not-attacked,
  pas pushé forward) → l'ennemi a dive Godswyl + leur Dante dans ma ligne → ~11510 dmg de réactions = 2 reaction-kills T3
  (Azrael Overwatch + Jain Zar/Dante counters) SANS dépenser mes actions offensives ; le HOLD d'Azrael armé au lieu d'un
  forward K? non-garanti = la décision décisive = MÊME pattern de W que 96002/98002 (held-line gagne l'attrition). PROPRE-côté
  violé UNE fois = ma SEULE perte hero : Shiron (fragile ranged Blast 8533) laissé sur le FLANC DROIT exposé au deploy (5,1) T1
  → l'ennemi a convergé ses deep-strikers + mêlée à droite et l'a focus-killé T2 (leur Nicodemus 5744 + leur Dante 2789) ;
  n+1 du failure-mode dominant over-extension/flank-exposure — un fragile ranged devait être déployé central + screené behind
  melee, sachant que les 2 Dantes/Mataneo = deep-strikers qui peuvent landera n'importe où. NB le move-guard T1 a CETTE fois
  été SUIVI correctement (Nicodemus engine flaggé 94%-death OVER-EXTENDED → pulled back → engine Healer survécu T1, contraste
  avec 70003 mal-trusté).)
  **70000** (PROPRE-côté VIOLÉ = la ROOT CAUSE, RÉCIPROQUE émoussée : après un hold T1-T2 PROPRE (zéro
  over-extension, GuardianOrganism a gardé TG full + BigTarget a réduit le ranged), j'ai R3 poussé Vindicta
  (fragile 4466) à (4,2) + Anuphet (6733) à (4,3) dans la kill-zone 3-Psyker (Psychic NoBlocking ignore mon
  armure/BigTarget/GuardianOrganism) JUSTE pour focus Thaumachus → les DEUX focus-killées au tour enemy-T3
  (Tigurius K! Anuphet, Neurothrope K! Vindicta) = collapse 5v→3v. n+1 du failure-mode dominant : la mitigation
  défensive ne protège PAS dans une kill-zone armor-ignore Psychic → sur-étendre des fragiles dedans = double
  focus-kill, exactement comme la doctrine le prévient. ⚠ AGGRAVÉ par mon PROPRE FireOfAbsolution (le tir de
  Vindicta sur Thaumachus a friendly-fire mon Anuphet adjacent 6733→3737, rendant son K! enemy possible). La
  moitié RÉCIPROQUE jouée (l'IA a dive R2-R3, j'ai chunké les engines) mais ÉMOUSSÉE par l'absence de Re'vas
  Overwatch dispo ce tour (1×/combat ou long cd) → punition insuffisante, pas de masse de réactions comme
  96002/98002/70001/70002.)
  **70004** (LES DEUX sens, dans un L — RÉCIPROQUE A PORTÉ LE MID-GAME : MOVE-GUARD T1 SUIVI (flaggé mon avance
  row-3/4 over-étendue, Ulf 70% loss → re-planifié un advance shallow row-2 groupé clean) PUIS hold-line T2 →
  l'IA a dive TOUTE sa force dans mon cluster cohésif → 26057 dmg de réactions = Tigurius (Ulf SavageKiller
  pré-empte son StormOfWrath mid-cast) + Angrax tués à 0 coût, ZÉRO perte, 5v5→5v3 = la moitié RÉCIPROQUE +
  le move-guard suivi ont décidé le mid-game (même pattern de réactions-massées-sur-le-dive que 96002/98002/
  70001/70002). PROPRE-côté violé 2× : Vindicta (mon seul ranged dealer 7029) laissée forward (1,3) dans le
  reach focus Trajann+Sy-gex → deletée avant de contribuer (⚠ Sy-gex r3 rend « back » relatif — un ranged
  fragile devait être hors r3+move2, pas juste « en arrière ») ; Ulf (ressuscité 2493) committé adjacent à
  Sy-gex en danger-2 → focus-killé (net OK car FJ a killed Sy-gex, mais a dépensé mon corps de réaction). n+1
  du failure-mode dominant over-extension, ici NON décisif sur l'issue (la loss était structurelle vs l'anvil
  self-healing) mais coûteux : la perte de Vindicta = perte de mon ranged pressure ET du combo ObsessiveAnnunciation+
  ranged. NB POSITIF : 2ᵉ wave d'affilée (après 70001) où le move-guard T1 a été SUIVI correctement → over-extension
  T1 évitée, contraste avec 70003 mal-trusté.)
  **70007** (PROPRE-côté VIOLÉ = ROOT CAUSE des 2 pertes, RÉCIPROQUE émoussée : j'ai trusté le verdict move-guard
  « approche propre » NET +0.50 (qui ne modélise QUE le chip 2-ply, AVEUGLE à un board-flip summon-engine) et avancé
  Archimatos (3,5) + Incisus (mon SEUL sustain, (4,4)) dans le reach move3-Custodes + le flood ranged GSC/Guardsman →
  Aesoth/Trajann melee-killed Archimatos (4025) et le flood a tué Incisus en UN tour enemy (25093 dmg, 2 units). EXACTEMENT
  la forme 70003 : le guard 2-ply ne voit pas le contact-dive + le board-flip du 2ᵉ tour IA. La moitié RÉCIPROQUE jouée mais
  ÉMOUSSÉE — Sy-gex Overwatch (un seul Overwatcher) n'a chunké Yarrick que 3797, négligeable vs un board-flip 12-unités →
  un seul Overwatcher ne « gagne pas l'attrition » quand l'ennemi flippe le board. n+1 du failure-mode dominant : même APRÈS
  un kill propre de Yarrick, l'over-extension de mes fragiles + le sustain reachable perdent le combat.)
  **70005** (LES DEUX sens, dans un L — PROPRE-côté VIOLÉ = ROOT CAUSE sous une NOUVELLE FORME = OVER-EXTENSION AU
  DÉPLOIEMENT : mon carry autonome Lucien (bloodDeathCompany 9035, Resilient) était DÉJÀ déployé forward à (3,5) — PAS
  poussé par un move, mais placé en avant par le déploiement — et le build placeholder affichait mes units rows 0-1, le
  move-guard a verdicté « approche propre » NET +0.20 (0 pertes) sur un hold-all-finish → j'ai HOLD au lieu de RETRAITER
  Lucien row 1-2 → 1er tour IA réel : Aesoth VexillaMagnifica 2687 + Volk FrenziedFiring ~6300 multi-hit → Lucien Resilient
  floored à 1 → Poxwalker DoT 1 = KILL = perte du carry T1, démarrage 4v5. NOUVELLE FORME du failure-mode dominant : le
  fragile n'a PAS avancé, c'est le DÉPLOIEMENT mid-board (caché par le placeholder rows 0-1) + le move-guard « propre »
  trompeur qui l'ont exposé — même blind-spot que 70003 mais sur un fragile DÉJÀ forward au lieu d'un move forward. La
  moitié RÉCIPROQUE A PORTÉ LE MID-GAME : holds cohésifs successifs → l'IA a dive → ~17696 puis ~8412 puis ~5138 dmg de
  réactions (DestroyerHive + CrushingClaws + SavageKiller) ont tué Aesoth/Trajann/Abraxas + 2 Poxwalkers SANS dépenser
  mes actions offensives (même pattern que 70004/70002) — insuffisant car démarrage à -1 corps. n+1 ÉCRASANT : la moitié
  PROPRE reste le défaut structurel, ici sous une variante DÉPLOIEMENT que le move-guard ne couvre pas.)
  **70008** (PROPRE-côté VIOLÉ = la ROOT CAUSE, RÉCIPROQUE bien jouée : j'ai sur-étendu mes 2 SEULS outils armor-bypass
  T1 — Exitor à (3,5) + Atlacoya stranded à (5,5) (échec du reachability check, un seul move/tour) — tous deux focus-killés
  au tour ennemi T1 → perdre Exitor (CordClaw Direct Pierce100) + Atlacoya (Direct) = ce qui a rendu le Burchard 12k
  MkXGravis ungrindable → loss à 1v1. n+1 du failure-mode dominant, VARIANTE « sur-étendre les outils anti-armure
  précieux ». ⚠ couplé au move-guard « clean NET +0.00 » longue-portée trusté (même blind-spot 70003/70007 : aveugle
  au focus de contact retardé une fois l'IA refermée). La moitié RÉCIPROQUE bien jouée — la chaîne Imospekh OW+InescapableDeath
  (8467 dmg + 1 kill) + le swing Gulgortz Waaagh ont porté la récupération de 3v6 à 5v2 — mais inutile faute d'outil
  bypass-armure vivant pour le tank late.)
  **70051** (LES DEUX sens, dans un W — RÉCIPROQUE A PORTÉ LE W : hold cohésif T1-T2 (mes units row 0-1, ennemi row
  8-9) → l'IA a avancé tout son cluster all-soft mid-board puis a dive dans mon mur Resilient (Maladus/Dreir/Lucien)
  → les engines softs (Aethana buff + Sibyll Psychic) exposés à leur sortie, tués T3 sans sur-étendre mes fragiles
  (Judh/Lucien gardés shallow/grouped) ; même pattern de hold-cohésif-baite-le-dive que 96002/98002/70001/70002/70006/
  70009. PROPRE-côté VIOLÉ UNE fois, NON-décisif dans un W = ma SEULE perte hero : Dreir laissé à l'extrémité
  forward-droite (4,0) du hold (la tuile la plus avancée de ma ligne) → focus-killé à 114 HP T2 + heal-block Mephiston
  (FuryOfTheAncients) a coupé sa regen ToughToKill → non-récupérable. n+1 du failure-mode dominant over-extension
  PROPRE, ici sous une SOUS-VARIANTE « unité laissée à l'extrémité de la ligne au déploiement/hold » (pas un move
  forward, une extrémité exposée non-rétractée) — devait être regroupée un rang derrière dès le hold T1. NB ce
  matchup all-soft+all-melee vs mur Resilient est l'INVERSE de la série row-9 inatteignable : pas de reach-fail,
  la RÉCIPROQUE porte proprement.)
  **70052** (PROPRE-côté RESPECTÉ sur le point clé — RÉCIPROQUE non testable, dans un L STRUCTUREL : le move-guard a
  flaggé plan A (push Snappa+Angrax forward pour tuer Abraxas) à NET −3.92 = perdre 3 corps pour 1 engine = 3-for-1
  focus disaster → j'ai REFUSÉ de le jouer (la moitié PROPRE bien appliquée : pas d'over-extension forward dans le
  screen all-ranged) ; j'ai aussi abandonné LIBÉRALEMENT à 3v10 R3 une fois la wincon (contenir Eldryon Executioner +
  le summon-flood) devenue inatteignable. ⚠ MAIS la loss N'EST PAS un classique over-extension : c'est une perte de
  focus/reach STRUCTURELLE (all-ranged enemy out-range + out-focus mon roster melee-heavy), aggravée non par un dive
  mais par un CHIP non-létal sur un summon-engine (Snappa seul sur Abraxas 7026→3183 → board-flip). La RÉCIPROQUE
  (« punir le dive adverse ») non testable — l'ennemi n'a JAMAIS divé (cluster all-ranged qui avance puis focus à
  distance, jamais au contact dans mes counters) → un cluster all-ranged ne se fait PAS baiter dans un mur de
  réactions, c'est le contre-profil exact de la moitié RÉCIPROQUE de H03. Confirme H03-propre (abandon-liberal +
  refus du 3-for-1) mais souligne sa LIMITE : la moitié RÉCIPROQUE est inerte vs un all-ranged qui n'a aucun besoin
  de diver.)
  **70056** (LES DEUX sens, dans un W — RÉCIPROQUE A PORTÉ LE W : hold cohésif T1 + Re'vas EarlyWarningOverride armé
  (Overwatch + 2 drones) → un roster adverse 100% melee + 1 ranged CONTRAINT de diver dans mon cluster ranged+Overwatch →
  l'Overwatch a chunké le Tanksmasha qui dive (10040→6725) AVANT mon tour, puis ~9629 + ~16.7k de réactions sur 2 tours
  adverses ont tué Ragnar (l'engine WarHowl, AVANT son 1er cast) + Atlacoya-enemy + Darkstrider SANS dépenser mes actions
  offensives = même pattern de hold-cohésif-baite-le-dive que 96002/98002/70001/70002/70051/70009. PROPRE-côté VIOLÉ n+1,
  NON-décisif (5v3-up) : (a) Vindicta over-committée à row 2 (4,2) pour lander le kill du Tanksmasha → Vindicta + Calandis
  (mes 2 SEULS ranged dealers) focus-killées au tour adverse — un kill shallow ou une retraite post-kill les aurait gardées ;
  (b) FireOfAbsolution friendly-fire sur Calandis+Corrodius adjacents à la cible (Calandis −3000 HP, wiki §2 — anti-synergie
  propre). n+1 ÉCRASANT du failure-mode dominant : la moitié PROPRE slip ENCORE même dans un W, survécu uniquement grâce au
  dive-punish qui m'avait déjà mis 5v3-up.)
  **70053** (LES DEUX sens, dans un W — RÉCIPROQUE A PORTÉ LE W : hold cohésif T1-T2 (BigTarget Aesoth + 12k Snotflogga en
  écran forward, fragiles derrière ; guard NET +0.00) → un roster adverse all-melee + Bellator move4-Flying + Deathleaper
  deep-strike CONTRAINT de diver dans mon cluster → réactions (Calandis Overwatch 2393, Grot SquigHound 1804 KILL sur un
  Inceptor) + engine-kills depuis tuiles atteignables-sur-le-dive → board renversé sans dépenser d'actions au profit du
  hold (même pattern 96002/98002/70001/70002/70051/70056). PROPRE-côté VIOLÉ n+1, NON-décisif : Aesoth committé DEEP à (3,3)
  à 758 HP T4 juste pour lander le chunk Imospekh → focus-killé T5 (over-extension propre, le failure-mode dominant récidive
  ENCORE dans un W) ; il mourait de toute façon (Pinned/encerclé) et l'engine-kill valait le coup, mais idéalement le chunk
  vient d'une tuile shallower / d'un corps tankier. ⚠ NOUVELLE FORME couplée du slip propre : T3 trois abilities (Snotflogga 69,
  Calandis 1063, Shiron 1197) jouées depuis les tuiles COURANTES sans move-onto la plan tile → mutated=false out-of-range (le
  guard 2-ply les avait résolues comme landing, masquant le whiff) → sous-délivrance d'un tour ; corrigé dès T4 (move legs
  explicites → tous les kills ont landé). NB la moitié RÉCIPROQUE a une fois de plus gagné l'attrition tandis que la moitié
  PROPRE slip — n+1 écrasant.)
  **70055** (PROPRE-côté VIOLÉ = cause contributive, RÉCIPROQUE STRUCTURELLEMENT N/A : j'ai over-étendu Dante
  (carry) forward T3-T4 ((5,5)→(3,4)) pour chunk Atlacoya/Adamatar → focus 9035→3540→mort, EN M'APPUYANT
  implicitement sur un dive-punish réciproque QUI N'EXISTE PAS pour mon roster — AUCUN reaction-engine
  (no Overwatch / no OW-carrier / no counter), seulement des summon-bodies. NOUVELLE SOUS-NUANCE : la
  RÉCIPROQUE de H03 (le hold-baite-le-dive qui porte la plupart des W : 96002/98002/70001/70051/70056/70053)
  REQUIERT un reaction-engine (Overwatch armé / counter / turret) ; un roster summon-only n'a pas d'auto-réaction
  → tenir ne « punit » pas automatiquement le dive, et chaque move forward de Dante l'exposait juste sans
  riposte. Donc côté PROPRE = même failure-mode dominant (over-extension, contributing à la loss), côté
  RÉCIPROQUE = inapplicable faute d'engine de réaction → ne JAMAIS sur-étendre un carry en supposant un
  dive-punish qu'on n'a pas. n+1 écrasant du failure-mode propre, ici dans une L STRUCTURELLE.)
  **70054** (LES DEUX sens, dans un W — RÉCIPROQUE A PORTÉ L'EARLY/MID, PROPRE VIOLÉE = ROOT CAUSE d'une perte
  hero : hold cohésif T1-T2 (Corrodius Resilient + Dante Terrifying en écran, gap large, guard NET+0) → un mur
  adverse 100% mêlée DOIT closer → les divers isolés punis depuis mes ranged (Yazaghor over-étendu à (3,4) T3 →
  focus-kill 3-ranged ; Deathleaper deep-strike isolé à (1,3) T3 → focus-kill T4 Darkstrider+Isaak+Dante). PROPRE-côté
  VIOLÉ = ROOT CAUSE : T3 forward commit de 3 ranged à row 3 pour tuer Yazaghor a strandé Isaak+Archimatos → T4 le mur
  a focus-killé Archimatos (mon Psychic dealer) = la perte décisive. ⚠ COUPLÉ à H40 : le move-guard T3 a verdicté NET+2
  FOCUS-FIRST mais est 2-ply-BLIND au focus de contact RETARDÉ du 2ᵉ tour IA quand le mur ferme la distance → exactement
  le blind-spot, le « propre » a été un faux feu vert pour avancer mes fragiles. n+1 du failure-mode dominant, ici dans
  un W rescué UNIQUEMENT par Isaak Ambush-resurrect full-HP + CultDemagogue board-flip 3v4→9v1 (PAS par une ligne
  propre) → contre un roster avec ne serait-ce qu'un petit engine sustain/summon, l'over-extension T3 aurait pu être
  fatale. NOTE : la RÉCIPROQUE a porté proprement car le roster all-melee CONTRAINT de diver = engines/anvils
  ATTEIGNABLES sur leur sortie [même structure que 70051/70056/70053], MAIS sans reaction-engine (Overwatch/counter)
  le « dive-punish » s'est fait par des FOCUS actifs depuis mes ranged, pas par des réactions auto — proche de la
  sous-nuance 70055 « la réciproque suppose un reaction-engine », ici suppléée par un alpha ranged coordonné.)
  **70060** (LES DEUX sens, dans un W — RÉCIPROQUE A PORTÉ LE W via un DOUBLE reaction-engine, PROPRE quasi-RESPECTÉE
  (3ᵉ application propre nette après 96002/98002, slip mineur guard-approuvé) : j'avais le reaction-engine que 70055
  exigeait — Re'vas EarlyWarningOverride Overwatch-turret (+1892, re-arm sur kill) + Sarquael GrimRetribution held-overwatch
  (gate=not-attacked) + Aun'Shi SereneUnifier −50% aura sur un cluster cohésif. T2 le guard a flaggé baseline-hold NET −2.25
  ET Sarquael-forward = mort → j'ai SUIVI sa retraite (pull-back), armé Re'vas EWO + held Sarquael unactioned → un ennemi
  all-melee (4/5 melee + Abraxas r2 + Deathleaper deep-strike) CONTRAINT de diver dans la killzone → ~18638 dmg en réactions
  ont tué Tarvakh ET Kharn (les 2 carries+engine-source) AVANT que Kharn score un kill (TheBetrayer jamais armé) = la moitié
  RÉCIPROQUE a porté le W, ZÉRO action offensive dépensée, ZÉRO perte hero (même pattern que 96002/98002/70001/70002/70051/
  70056/70009 : held-line défensive gagne l'attrition). PROPRE-côté : LA SEULE exposition forward = Trajann (Resilient) à
  (4,3) row 3 pour compléter le kill garanti d'Abraxas — guard-flaggé « worst u103 100% → floored to 1 », guard-APPROUVÉ
  (NET +5.00, summon-engine mort) et Trajann a survécu (Resilient floor) puis self-healé via MomentShackle (1→5984) le tour
  suivant → slip mineur NON-décisif (6v2, Resilient, kill d'engine valait le coût), pas le focus-kill gratuit habituel. Le
  failure-mode dominant over-extension propre est ici réduit à UN corps Resilient guard-approuvé qui s'est récupéré = la
  ligne propre globalement TENUE a porté le W (contraste net avec la série de slips propres). CONFIRME que la moitié
  RÉCIPROQUE PORTE le W quand le reaction-engine existe ET que le positionnement reste défensif tout le combat.)
  **70059** (LES DEUX sens, dans un W — RÉCIPROQUE A PORTÉ LE W, PROPRE VIOLÉE = MA SEULE perte hero : hold cohésif
  T1-T2 (cluster Resilient/TermArmour Typhus 12k + Wrask + Kharn, gap 5 rangées, Archimatos pull central+écrané) → un roster
  adverse all-melee + anvil-heavy (Maladus/TG/Abaddon/Ragnar mêlée, move2-3) CONTRAINT de fermer la distance → le bulk a dive
  T3 → j'ai bursté sur mon tour (même structure favorable que 70051/70056/70054 : un roster contraint de diver expose ses
  menaces). ⚠ SOUS-NUANCE 70055 CONFIRMÉE n+1 : MON roster n'avait AUCUN reaction-engine (no Overwatch/counter/turret) → le hold
  n'a PAS auto-puni le dive ; à la place mon cluster bruiser Resilient/TermArmour 9.5-12k a ABSORBÉ le dive et j'ai bursté au
  tour suivant — variante « anchors durables absorbent + alpha au tour suivant » de la réciproque, distincte du dive-punish
  auto-réactif (96002/98002/70060). La SEULE « réaction » = Kharn TheBetrayer death-riposte (6481 sur Maladus). PROPRE-côté
  VIOLÉ = ROOT CAUSE : T3 Kharn (mon MEILLEUR carry : KillMaimBurn + FJ + TheBetrayer) committé forward à (4,2) pour K! le
  Tyrant Guard (un anvil NON-engine) → focus-killé par Maladus FlailSwing au tour adverse = ma seule perte. ⚠ COUPLÉ à H40 :
  le guard a flaggé worst=Kharn MORT MAIS a rated le plan best (NET +2.58, aucun pull-back améliore) car tuer le TG exigeait une
  tuile mêlée forward → le NET positif a « approuvé » le sacrifice d'un carry. NOUVELLE FORME du failure-mode propre : tuer un
  ANVIL-killable non-engine (TG focusable adjacent) a STRUCTURELLEMENT exigé un carry mêlée au front (contrainte réelle, pas un
  slip de placement) → j'ai choisi le sacrifice de plus haute valeur de board (Kharn) au lieu de préserver le carry (laisser TG
  vivant, ne tuer que l'engine Ragnar via Psychic) — mais le reach n'autorisait pas un kill Ragnar-only sans commit mêlée. n+1
  ÉCRASANT du failure-mode dominant over-extension propre, ICI dans un W : la moitié RÉCIPROQUE (absorbe-le-dive-puis-burst) a
  porté le W tandis que la moitié PROPRE a coûté un carry — leçon récurrente « un anvil-killable non-engine ne vaut pas un carry
  forward : préférer tuer l'engine au range, ou sacrifier le corps le PLUS expendable, pas le plus précieux ».)
  **seed 70058** (LES DEUX sens, dans un W — RÉCIPROQUE via un REACTION-ENGINE HOLD a PORTÉ le W, PROPRE violée 1× = ma SEULE
  perte hero) : j'ai tenu un cluster cohésif (Sy-gex Overwatch r3 turret HELD-armé + Aesoth BigTarget/StandVigil/Resilient screen
  + Thaddeus +728 feeding Sy-gex) T1-T2 → l'ennemi 3/5 melee/Flying CONTRAINT de diver dedans → l'Overwatch a reaction-KILLED Ulf
  sur le dive (4660→0, pré-chunké BasiliskBarrage) + la conversion T3 a tué Titus (permanent, FJ-route) + Yazaghor ennemi SANS
  dépenser d'actions hors-tour (pattern 96002/98002/70001/70056/70060). PROPRE-côté VIOLÉ : à 5v2 j'ai avancé Jain Zar (7530, un
  NON-tank) à (4,3) dans la reach COMBINÉE de Njal (Psychic AoE r3) + Sho'syl (MV71 drone-summon utilisant le stat de Sho'syl) →
  drone 5924 + Njal 1606 = focus-killée = ma SEULE perte. ⚠ NOUVELLE SOUS-FORME du failure-mode propre : la reach d'un
  drone-summon (le summoner reste back-row, son drone delete un forward) n'est PAS visible dans le danger-zone overlay (summoner
  blind spot, SKILL §4) → over-extension « invisible » ; aggravée par le move-guard indisponible (timeout T2+) sans défaut
  conservateur (NE PAS avancer un non-tank quand le guard est down). n+1 ÉCRASANT du failure-mode dominant over-extension propre,
  ICI dans un W, non-décisif (réciproque déjà 5v2-up) ; règle réaffirmée « n'avancer que la durable Aesoth Resilient comme écran
  forward, garder les fragiles/non-tanks shallow ».)
  **seed 70057** (LES DEUX sens, dans un W 5v0 — RÉCIPROQUE via ACTIVE FOCUS (pas auto-réactions) a PORTÉ le W, PROPRE
  violée 1× NON-décisive) : roster adverse all-melee/deep-strike CONTRAINT de closer dans ma range ; mais MON roster n'avait
  AUCUN reaction-engine (no Overwatch/counter/turret) → la moitié RÉCIPROQUE s'est jouée en FOCUS ACTIF depuis mes ranged/Psychic
  shallow (Sho'syl drone + Mataneo + Abraxas + Vitruvius), PAS en réactions auto — même sous-nuance que 70055/70059 (« la
  réciproque suppose un reaction-engine ; sans, l'absorption/alpha actif la supplée »). Les 2 engines screen-on-attack (Sho'syl
  MV71 drone + Tan Gi'da ControlEdict Vanguard) ont généré des corps qui ont soaké ~14k du focus ennemi = ont gardé mes
  amplificateurs Vitruvius/Abraxas shallow. PROPRE-côté VIOLÉ 1× : T3 Tan Gi'da (non-tank) poussée à (5,3) row 3 pour chip Dante
  → chunkée à 205 HP (98%) pour un dégât marginal — n+1 ÉCRASANT du failure-mode dominant over-extension propre, NON-décisif (5v0,
  Tan Gi'da a survécu + ses Vanguard ont screené). ⚠ COUPLÉ à H40 : T2 j'ai avancé mon cluster row 2 en trustant le verdict guard
  one-ply « safe » → delayed-contact blind-spot (cf. 70003/70007) → quand l'IA a closé (Dante move4 (3,4)), le baseline-hold-row-2
  est devenu NET -4.78/-6.71 ; aurais dû tenir row 0-1 et laisser l'ennemi sur-committer pleinement. Le move-guard a SAUVÉ le tour
  décisif : T3 il a FLAGGÉ l'alpha aggressif OVER-EXTENDED (perte Sho'syl+Vitruvius, NET -1.94) → le pull-back a trouvé la ligne
  Dante-overkill (NET +1.02) qui a gardé mes fragiles shallow.)
  **n=46** → confirmée, écrasante.
- **CONSTAT VAGUE** : `over-extension` = tag dominant (≈11/16 matchs) ; la moitié RÉCIPROQUE de H03
  (« punir le dive adverse ») est bien exécutée, mais la moitié PROPRE (« ne pas diver MES unités/engines »)
  est violée match après match (Baraqiel, Thaddeus, Ahriman, Anuphet+Actus, Corrodius, Nicodemus, Sho'syl,
  Forcas/Sy-gex/Tjark, Maugan Ra+Aethana…). PRIORITÉ DE PROMOTION : insister SKILL §6 sur le côté **propre** + cas spécifiques
  (engine de sustain un rang derrière ; carry ranged fragile reste STATIONNAIRE/hors danger ; ne jamais
  pousser dans une killzone/arc overwatch armé ; garder le revivable adjacent à l'Apothecary).
- **→ doctrine si confirmée** : SKILL §6 (existe partiellement — focus-fire / cible isolée ; renforcer
  + ajouter la réciproque : punir le dive isolé adverse, laisser l'IA dive dans ses propres counters).

## H04 — Le label K! ne tient pas compte de Resilient + réduction défensive — `confirmée` (pour:11 contre:0) → À PROMOUVOIR
- **claim** : un coup mêlée « K! » sur une cible Resilient + Terrifying (-mêlée) peut atterrir pile
  sous l'overkill → Resilient sauve à 1 PV. Prévoir une 2ᵉ source non-réduite (ranged) / overkill.
- **note** : à moitié dérivable de gameconfig (Terrifying = -mêlée) → priorité basse ; risque de me
  faire SUR-investir des dégâts si sur-appliqué. **Le fait « K! ne soustrait pas le clamp Resilient »
  est lui non-dérivable et désormais vérifié n=5** → inscriptible en caveat outil SKILL §7. ⚠ NUANCE
  (cf. H12 réfutée) : le K! est trompeur sur un SINGLE-hit (Resilient sauve à 1) MAIS un MULTI-hit (2+
  hits dans le même actif, ex. BringerOfDespair) TUE quand même (1er hit floor, 2e tue depuis 1) — donc
  un K! affiché sur un Resilient frappé par un multi-hit ≥2 EST fiable, sur un single-hit il ne l'est pas.
- **evidence** : G01 (Azkor sauvé à 1) ; **seed 91004** (K? Macer Resilient mal labellisé) ;
  **seed 91009** (K! optimiste vs Azkor Resilient+Daemon) ; **seed 91013** (plan « (5,5)[1384 K!] » sur
  Azkor mais Resilient l'a sauvé à 1 PV → finish next-turn via MartialApotheosis AUTO) ; **seed 95002**
  (confirm : K! affiché « 570-570 K! » sur Yarrick à 570 PV était TROMPEUR pour un single-hit — Resilient
  aurait floored à 1 ; le multi-hit BringerOfDespair 4+4 a été requis et a bien tué — le label K! ne
  soustrait pas le clamp Resilient ; n+1). 91001 inconclusive (K? Macer mais le floor a quand même
  attrapé) ; **93001 inconclusive** (aucun Resilient ennemi mal-labellisé K! ce match ; mon propre Lucien
  (Resilient) floored à 1 par hits distribués = cohérent avec le floor, pas un test du label K!) ;
  **95001 inconclusive** (aucun Resilient ennemi dans ce matchup) ; **97001 inconclusive** (Angrax a
  TerminatorArmour, PAS Resilient ; les labels K!/K? de Calgar sur Angrax ont suivi les PV réels —
  non testé). **seed 97002** (confirm — ÉLARGIT le périmètre au-delà du clamp Resilient : la prédiction
  d'actif HammerOfWrath de Mataneo affichait [0-0] (plan illisible) ET son dmg RÉEL était ~1015 vs ~5820
  attendu du gameconfig brut (2× 2910). Cause = précondition NON satisfaite : Mataneo avait BOUGÉ le tour
  précédent → la charge gatée « if Mataneo has not moved » n'a pas fire (pas de charge = pas de full dmg,
  pas de summon-attack AggressiveOnslaught). Leçon généralisée : les prédictions d'actif sont non fiables
  NON seulement vs Resilient mais aussi quand une PRÉCONDITION de l'actif (« has not moved », charge,
  position) n'est pas vérifiée → ne jamais committer un finisher profond sur une prédiction d'actif ;
  exiger une K! d'ATTAQUE NORMALE confirmée OU vérifier que la précondition tient).
  **seed 97000 inconclusive** (aucun Resilient ENNEMI mal-labellisé K! ce match ; mon propre Arjac
  (Resilient) est mort EXACTEMENT par le clamp — 327 PV → 326 dmg → 1 PV (Resilient floor) puis « 1 » dmg
  tue depuis 1 — cohérent avec le mécanisme floor-then-finish (wiki §1) mais ce n'est PAS un test du label
  K! sur un ENNEMI). **seed 98004** (confirm n+1 — DEUX labels trompeurs vs Resilient ce match : (a) K!
  Makhotep (Gauss single-source) sur Nauseous affiché K! mais max roll 1697 < 1698 HP → NON-létal, Resilient
  jamais déclenché (le label sur-estime le roll au bord) ; (b) K? Mephiston Psychic sur Aesoth (Resilient)
  joué comme un kill → a laissé Aesoth à 17 PV (floor non atteint, roll bas) → finition multi-hit Nicodemus
  Chain requise (overkill, beat Resilient). Le label K!/K? SOMME les hits bruts au bord du roll et NE
  soustrait PAS le clamp Resilient → budgétiser une 2ᵉ source multi-hit). **seed 98002 inconclusive**
  (aucun ENNEMI Resilient mal-labellisé K! ce match : les Necrons utilisent LivingMetal/Mechanical, pas
  Resilient ; Toth utilise TimeFlux/TerminatorArmour. La K! d'Abraxas Psychic sur Toth a tenu parce que le
  Psychic bypasse TerminatorArmour — PAS un test du clamp Resilient). **seed 98000** (confirm — ÉLARGIT le caveat
  multi-hit-vs-Resilient au cas regen/crit-reduction : Haarken 4-hit normal sur Dreir (Resilient + ToughToKill,
  +1310 Herald mark) → hits 1-3 (1237+1135+229) ont floored Dreir à 1 PV (Resilient fire), puis le 4ᵉ hit a
  délivré **Amount=0** et Dreir a SURVÉCU à 1 (NON tué-depuis-1). N'est PAS une réfutation de la règle floor-then-
  finish (un hit RÉEL >0 à 1 PV tue toujours — wiki §1/H12) : le 4ᵉ hit a résolu à 0 dmg, probablement via
  ToughToKill (−35% crit / −1091 crit dmg) ou un hit bloqué/suppressé une fois la cible au floor → un hit 0-dmg ne
  peut tuer à aucun HP. CAVEAT D'EXÉCUTION : sur un Resilient+regen+crit-reduction (Dreir, Abaddon 91004), un
  multi-hit peut floorer à 1 PUIS échouer à finir si le hit final résout à 0 → **budgétiser un finisher SÉPARÉ**,
  ne pas trust un multi-hit K! pour fully-kill un tank à crit-reduction ; même forme que l'outlier 91004).
  **seed 70004 inconclusive** (le label K! sur l'ennemi Resilient (Trajann) jamais TESTÉ — Trajann n'a JAMAIS
  été amené à un floor finissable : MomentShackle heal-to-full (~+5684 sur cd) l'a constamment reset au-dessus
  de tout seuil tuable → le mécanisme floor-then-finish / multi-hit-beats-Resilient n'a pas pu être exercé. NB
  côté distinct mais cohérent avec le seuil d'Overkill du label : Ulf FinalJustice a tué Sy-gex à EXACTEMENT
  5724 PV avec 5724 dmg = un kill exact-HP n'est PAS un Overkill (>2× requis) → la riposte FinalJustice fire
  normalement ; ce n'est PAS un test du clamp Resilient mais ça re-confirme la définition d'Overkill du label).
  **seed 70007 inconclusive** (aucun Resilient ennemi MAL-labellisé K! ce match : Sy-gex attaque NORMALE 4-HIT sur
  Resilient Yarrick (K?) a both KILLED ET OVERKILLED (Unit_WasOverkilled=1) en un coup → cohérent avec la règle
  multi-hit-bat-Resilient (wiki §1 : le 1er hit floor à 1, les hits suivants tuent depuis 1 et OVERkillent) — un K? multi-hit
  EST fiable, ce n'est PAS le cas trompeur single-hit. Trajann (Resilient) jamais amené à un floor finissable (MomentShackle
  reset, écran jamais cassé). N'est donc PAS un test du clamp K! sur SINGLE-hit, mais re-confirme la sous-règle multi-hit du
  caveat — cohérent, pas un nouveau pour distinct.)
  **seed 70005** (pour — DEUX faces du caveat re-confirmées le MÊME match : (a) côté ENNEMI, Ulf GreatFrostAxe (4-hit ACTIF)
  sur Trajann (Resilient + MartialKatah) affichait K? max 3307 = HP exact → le multi-hit a bien TUÉ (floor-then-finish : le
  1er hit floor à 1, les suivants tuent + Overkill) → cohérent avec la sous-règle « un multi-hit ≥2 K? EST fiable vs
  Resilient » (≠ le cas trompeur single-hit) — CONTRASTE avec 70004 où le MÊME Trajann n'avait jamais été amené à un floor
  finissable (MomentShackle reset) ; ici les réactions l'avaient chunké à 4578 + Typhus Psychic à 3307 AVANT, donc le floor
  ÉTAIT atteignable et le multi-hit l'a battu ; (b) côté SUBI, mon propre Lucien (Resilient) floored à 1 par le focus
  distribué Aesoth+Volk T1 puis tué par un DoT Poxwalker de 1 dmg = floor-then-finish confirmé aussi côté subi — un hit
  RÉEL >0 (même 1 dmg de summon-DoT) à 1 PV tue toujours. Re-confirme la règle des DEUX côtés.)
  **seed 70008** (pour — sous-règle multi-hit-bat-Resilient re-confirmée n+1 : Imospekh 6-hit Gauss sur Dreir
  (Resilient + ToughToKill) → 1er hit floor à 1, un hit mid-séquence a délivré Amount=0 (ToughToKill zeroed) MAIS un
  hit surplus ultérieur (Amount=1) a tué depuis 1 PV = full kill WasOverkilled=1. Confirme que le multi-hit ≥2 K? EST
  fiable vs Resilient TANT QUE des hits surplus >0 restent past le floor — RAFFINE le caveat (cf. H31) : il n'échoue
  que si le hit final résout à 0 (98000), pas si un 0-dmg tombe mid-séquence avec des hits >0 derrière.)
  **seed 70057** (pour — ÉLARGIT le caveat au seuil d'Overkill SUR FinalJustice : sur 4 FJ carriers (Dante/Ragnar/
  Helbrecht/Sarquael), la discipline K!/overkill a tenu sur les 3 voies — (a) Helbrecht (9539) overkillé multi-source
  (Mataneo 7984 + drone 1555, Attack_WasOverkill=1) → FJ NON déclenchée (i2 « unless Overkilled » vérifié) ; (b) Dante tué
  à (3,4) SANS eligible adjacent → FJ a fire (IsActingBeforeDeath=0) mais ZÉRO dmg (no eligible target = no-op) ; (c) Ragnar
  tué NON-overkillé → FJ a fire (IsActingBeforeDeath=1) 7x Chain Pierce20 ~1946 sur Mataneo armuré Mechanical = trivial
  (Pierce20 weak-pen vs armure). Confirme que le label « kill » ne dispense pas de RAISONNER le déclencheur FJ : seul l'Overkill
  (>1× HP restant en marge suffisante) ou un kill SANS eligible adjacent SUPPRIME la riposte ; sinon router la riposte sur un
  corps armuré/tank. Même famille « le label de kill ne soustrait pas le mécanisme défensif » que le clamp Resilient — ici porté
  à la death-riposte FinalJustice.)
  **n=11** → confirmée.
- **→ doctrine si confirmée** : SKILL §7 (caveat outil : K! optimiste) — le label K!/K? SOMME les hits
  bruts et NE soustrait PAS le clamp Resilient (ni l'Overkill requis) → une cible Resilient affichée K!
  sur un SINGLE-hit survit à 1 PV ; budgétiser une 2ᵉ source/Overkill OU un finish AUTO start-of-turn
  (MartialApotheosis) OU un MULTI-hit (≥2 hits dans un actif : le 1er floor, le 2e tue depuis 1).

## H05 — Casser le plancher 50% de Judh (HypersensoryAbilities) en 2 frappes/tour — `provisoire` (pour:1 contre:0)
- **claim** : le plancher « ne peut tomber sous 50% PV courants » ne s'applique qu'au 1er coup chaque
  tour adverse (i2 CONFIRME). Séquence : frapper Judh EN PREMIER avec un TANK (encaisse le plancher +
  la riposte 3x) ; les attaquants suivants ce tour ignorent le plancher -> kill garanti.
- **caveats (gameconfig)** : (a) plancher = % des PV COURANTS, pas max ; (b) la riposte 3x ne part que
  si l'attaquant est à <=2 hex -> un opener RANGED à >2 hex soak le plancher SANS subir la riposte ;
  (c) Ambush : même tuée proprement elle laisse un decoy et ressuscite full-HP au tour suivant s'il
  reste un decoy ami -> nettoyer les decoys.
- **test (VALIDATE)** : rejouer un combat avec Judh en focus 2-frappes/tour -> meurt-elle définitivement
  (decoys clear) ?
- **evidence** : seed 70014 (n=1, validé end-to-end une fois) ; **seed 70050** (INCONCLUSIVE — Judh présente
  (genesKelermorph, HypersensoryAbilities 50%-floor + Ambush + HeroicFusillade 6-hit AoE) mais JAMAIS engagée :
  le board a flippé d'abord (Isaak CultDemagogue 5v5→5v14, Shadowsun teleport-kill de mon reach-tool) → je n'ai
  jamais pu tester la séquence 2-frappes/tour. Carte notée pour la prochaine rencontre : ouvrir au RANGED à >2 hex
  pour soak le plancher sans la riposte 3×, puis 2ᵉ attaquant ce tour ignore le plancher → kill ; clear TOUS les
  decoys (2 sources Ambush) pour la mort permanente).
- **seed 70051** (INCONCLUSIVE côté TUEUR — Judh était MIENNE ce matchup (genesKelermorph), pas une cible à tuer →
  la séquence 2-frappes/tour non testable. EN REVANCHE confirme du côté PORTEUR : sa HypersensoryAbilities (floor
  50% + decoy-spawn quand touchée + Ambush) l'a gardée très survivable comme MON unité — un decoy a spawn quand elle
  a été frappée → cohérent avec le kit défensif. Renforce indirectement que pour la TUER il faut clear les decoys +
  ignorer le floor avec un 2ᵉ attaquant.)
- **seed 70061** (OBSERVATION CONTESTÉE → RÉSOLUE EN FAVEUR DU SCOPE « tour ENNEMI seulement » par Verif) : j'ai vécu
  Makhotep single-source 1553→776 (= exactement 50%) PUIS 2ᵉ hit « 0 » sur MON tour joueur → j'en ai conclu que le floor
  s'appliquait AUSSI sur le tour joueur (contredisant le scope wiki). **Verif gameconfig RÉFUTE l'observation** : le texte i2
  de `HypersensoryAbilities` lit « The first time **each enemy turn** that Judh is attacked, she cannot fall below 50% of her
  current Health » → le trigger est scopé « enemy turn », il NE fire PAS sur le tour joueur. La note wiki (l.799-805 :
  « floor ne s'applique PAS sur le tour joueur ») est donc CONFIRMÉE CORRECTE par l'i2-truth ; mon observation était un
  misread du combat log (ou un cas-limite engine). LEÇON PROCESS : ne pas inverser une note wiki i2-ancrée sur une seule
  observation live ambiguë ; le scope « 1er coup chaque tour ENNEMI » tient. Pour TUER Judh il faut quand même clear les
  decoys ET la frapper sur MON tour (où le floor ne protège pas) — exactement ce que la doctrine wiki dit déjà. n=1
  observation discardée ; H05 (l'exploit 2-frappes côté tour ennemi) reste `provisoire`, NON réfutée.
- **→ doctrine si confirmée** : wiki (Judh déjà l.799-807, ajouter l'exploit + caveat decoy/range) +
  SKILL §6 (focus 2-coups/tour vs unités à plancher conditionnel).

## H06 — necroDestroyer MultiThreatEliminator : Molecular chain, NON armor-bypass + InescapableDeath OW-chain — `confirmée` (pour:2 contre:0) → À PROMOUVOIR
necroDestroyer (Imospekh) MultiThreatEliminator : Ranged, 6x Molecular hits range 2, leftover hits
chain to an enemy ADJACENT to the target (+1 hit per kill, keeps re-targeting). NOT reduced by
Terrifying (melee-only). PiercingRatio=60 => partially armour-reduced (NOT armour-bypass — « no
reduction observed » is an n=1 artifact). Casting the active = « has attacked » => Destroyer is NOT
in Overwatch that turn (but InescapableDeath lets it re-enter Overwatch on overwatch-triggered kills).
- **à valider** : armour effect at max level, overwatch-suppression on next enemy turn.
- **evidence** : seed 70011 (n=1, live) ; **seed 70008** (CONFIRM live n+1, distinct matchup — la chaîne
  InescapableDeath sur Overwatch a fire : 11 OW hits / 8467 dmg, a tué un Death Rider (u141, 6 hits) puis
  Imospekh est RESTÉ en Overwatch et a continué sur l'ennemi suivant (u143) en retenant les hits = chain-on-OW-kill
  confirmé live. + PiercingRatio=60 confirmé partiellement réduit live : Gauss vs MkXGravis double-armor → ~1300-1988
  net/turn, JAMAIS un armor-bypass → la note n=1 « no reduction » était bien un artefact).
- **→ doctrine** : wiki §3bis (Imospekh) / §1 (InescapableDeath + MultiThreatEliminator) — sur un kill OW,
  Imospekh reste en Overwatch et re-fire sur le suivant avec hits−1 (InescapableDeath) ; chaque kill in-chain
  ajoute aussi +1 hit (MultiThreatEliminator) avant le −1 → cascades longues quand ennemis adjacents en range 2.
  Garder Imospekh turret-positionné, NE PAS attaquer avec quand un dive arrive = la value de réaction > un actif.

## H07 — orksBigMek KustomForceFieldReworked : aura d'armure source-anchored (strip à la mort) — `confirmée` (pour:2 contre:0) → À PROMOUVOIR (strip-on-death) ; valeur exacte RÉFUTÉE
orksBigMek (Gibbascrapz) passive KustomForceFieldReworked : aura d'Armure aux unités amies ADJACENTES
à BigMek. **CONFIRMÉ live (seed 91002)** : tuer Gibbas STRIP immédiatement l'aura sur l'adjacent (cascade
`LoseEffect KustomForceField` + `FixedArmor_Modification` retiré sur Arjac → ses hits subis ~doublent,
~150→~600/hit). Aura **source-anchored** = inhérent à un passif d'adjacence → vérité robuste → wiki.
- **valeur exacte RÉFUTÉE** : le « +599 base, pas le legacy +437 » est FAUX — gameconfig extraArmor
  topе à **+437** (lvl65) ; un +599 live = 437 scalé par bonus rareté/star (`variablesAffectedByRarityBonus`),
  PAS un rework de la valeur de base. Ne pas inscrire 599 comme base.
- **evidence** : seed 70011 (n=1, valeur) ; **seed 91002** (strip-on-death confirmé live + valeur contredite).
- **→ doctrine** : wiki §3bis (Gibbascrapz) — préciser « aura source-anchored, strip immédiat à la mort
  du Bigmek → ouvrir une grappe blindée en le tuant » + corriger la note de valeur (base +437, le reste
  = scaling rareté).

## H08 — Un move pur ne termine PAS l'activation (auto-finish EFFECT-GATED) — `provisoire` (pour:3 contre:0)
Un move pur ne termine PAS l'activation par défaut (confirmé : i2 Keywords/Charging + abilities « may
move and attack » / « can move after attacking » ; binaire MoveUnitOperation ne fait pas de
FinishUnitTurn). MAIS certains moves auto-finissent l'unité : pas aléatoire ni lié à la distance —
c'est EFFECT-GATED (SetMovedFlag pose un flag de fin de tour 0xc seulement si l'unité est owner/target
d'effets précis 0x40c/0x40b/0x4d9/0x4d6). Doctrine prudente jusqu'à recon des effets via
decisionView.effects : faire le move porteur d'attaque EN DERNIER, ne jamais re-bouger une unité deux
fois.
- **NOUVELLE PISTE (seed 91000)** : Abaddon move (3,4) AUTO-FINI + a ramassé un effet **LightCover** (tile
  cover) ; Anuphet move (4,4) PAS auto-fini, sans effet ; Actus move (3,3) auto-fini. → supporte
  l'effect-gate (le move ramassant un effet de tile/cover pose le flag) plutôt que pure « no-reachable-enemy ».
  CONFOUND : terrain-cover non isolé du reachability-gate (H09). n=1 chaque, inconclusive sur le gate exact.
  À recon : id d'effet exact sur les unités qui auto-finissent (gameconfig.py --effect, decisionView.effects).
- **SÉPARÉMENT CONFIRMÉ (wiki-worthy)** : **LightCover = effet de tile** « réduit les attaques ranged
  multi-hit subies de 2 hits (min 1) », accordé en posant le pied sur un hex cover (ex. DryBush) →
  rester sur cover blunt le ranged multi-hit ennemi. (i2 Keywords/UnitEffect_LightCover.)
- **NOUVELLE OCCURRENCE (seed 98003)** : un **deep-strike teleport-move** vers un hex libre NON-adjacent
  auto-finit l'unité (ActionsAvailable=0, zéro attaque possible) — DEUX instances propres (Dante vers (3,6),
  Aethana vers (3,5)). Le téléport deep-strike est contraint « pas adjacent à un ennemi » (i2 TeleportStrike),
  donc un deep-striker MÊLÉE (SwoopingHawk/charge melee-init) n'a JAMAIS de cible atteignable à l'arrivée →
  auto-finish systématique = stranded solo, zéro alpha. Cohérent à la fois avec H08 (auto-finish sur un move
  sans cible) et avec le cas particulier deep-strike-melee (la contrainte d'atterrissage et l'init-mêlée sont
  mutuellement exclusives le même tour). Renforce le gate « no-reachable-target → auto-finish » mais ne tranche
  toujours pas effect-gate (H08) vs reachability-gate (H09).
- **à valider** : recon-er l'effet actif sur les unités qui auto-finissent.
- **evidence** : seed 70011 (n=1) ; seed 91000 (n=1, cover-tile→auto-finish) ; **seed 98003** (n=1, deep-strike
  teleport-move non-adjacent → auto-finish ×2, Dante+Aethana) ; recoupe H09. **n=3** observations live.

## H09 — Action economy move2/slow : move sans attaque atteignable auto-finit — `provisoire` (pour:6 contre:0)
Action economy (move2/slow units) : une unité peut move ET attaquer dans la même activation, mais un
move qui ne laisse aucun ennemi atteignable+frappable depuis la destination auto-finit l'unité
(ActionsAvailable=0, drop de « à activer »). Doctrine : avec des unités lentes, ne move que vers un
ennemi qu'on peut effectivement reach ET hit ce tour, sinon le move seul termine son tour. [i2 confirme
SEULEMENT le cadre move+attack same turn (Charging, FireAndReposition exception, abilities
« if has not moved → end of turn ») mais PAS la règle d'auto-finish — comportement moteur ; recoupe H08]
- **TENSION NON TRANCHÉE** : H08 (decompile binaire) = auto-finish EFFECT-gated (flag 0xc), pas
  distance/reachability ; H09 = reachability-gated (« no enemy reachable from destination »). « rien en
  portée » est le SYMPTÔME observé, pas le trigger prouvé. À trancher par seed-replay contrôlé + recon
  decisionView.effects sur les unités qui auto-finissent. Reste provisoire malgré n=6 (règle moteur
  non-dérivable + mécanisme concurrent non résolu → ne pas promouvoir sans replay contrôlé).
- **evidence** : seed 70012 (n=1) ; **VAGUE** : 91005 (move pur sans cible → ActionsAvailable=0 ; move
  avec ennemi reachable garde l'action), 91006 (Azkor/Typhus/KillaKan opening advance), 91011 (Dreir/Ulf/
  Macer parqués row3, tous ActionsAvailable=0), 91012 (les 5 avances d'ouverture), 91014 (move-no-target
  finit, move-with-target garde l'action) ; **seed 96002** (Sy-gex move2 déplacée en (5,3) sans ennemi en
  portée → ActionsAvailable=0 auto-géré ; finish explicite ensuite = no-op mutated=False = DOUBLE-FINISH ;
  corrobore « ne JAMAIS envoyer finish après un move vers une tuile sans ennemi en portée »). **n=7**
  observations live convergentes, gate exact non prouvé (reste provisoire : règle moteur non-dérivable +
  mécanisme concurrent H08 non résolu → ne pas promouvoir sans replay contrôlé).

## H10 — Gibbascrapz mort → despawn de son Grot Tank (2-for-1) ? — `réfutée` (pour:1 contre:1) → supprimer le claim summoner-link, garder le fait BattleFatigue (wiki)
Le claim « summoner-link despawn » est **RÉFUTÉ** (seed 91002) : Gibbascrapz est mort NON-adjacent à
son Grot Tank (Gibbas (2,2) vs Tank (4,4)) et NON overkillé → le Grot Tank a **survécu pleine vie
(7977 PV)** et a continué d'agir. Aucun summoner-link dans gameconfig/i2 ; le despawn observé au seed
70015 = très probablement **BattleFatigue** (chance de fuir/retrait quand un ami ADJACENT est défait,
+chance si overkillé), adjacency-gated → cohérent avec le non-despawn ici (Gibbas non-adjacent ne peut
pas faire roll BattleFatigue). → vérité = BattleFatigue, déjà inscrite au wiki §3bis Gibbascrapz.
- **evidence** : seed 70015 (pour, n=1) ; **seed 91002** (contre — non-adjacent → pas de despawn).
- **action** : ne pas promouvoir le summoner-link (faux) ; le fait BattleFatigue reste au wiki.

## H11 — Terrifying ne réduit QUE la mêlée — bypass = RANGED — `confirmée` (pour:6 contre:0) → À PROMOUVOIR
Terrifying (Mephiston, Dante, Azkor, Atlacoya...) = réduit UNIQUEMENT les dégâts de MELEE subis (i2 :
« Takes {[defensePct]}% Damage from Melee attacks »). Bypass fiable = RANGED. NOTE : armor-ignore/
piercing NE bypasse PAS Terrifying (ce n'est pas un mécanisme d'armure) -> une mêlée même Direct/
perforante reste réduite.
- **evidence** : seed 70015 (n=1) ; **seed 91003** (confirm : Thaddeus ranged Blast a tué la Terrifying
  Atlacoya proprement — le ranged contourne le Terrifying melee-only). 91013 inconclusive (ranged-bypass
  cohérent mais pas d'edge-case armor-ignore-vs-Terrifying testé) ; **seed 93001** (confirm : Atlacoya
  Terrifying a tanké un roster 4-mêlée cheap — Parasite n'a touché que 2891 sur une tuile Power-Pierce ;
  la réduction-mêlée a tenu comme l'edge de l'anchor). **seed 97002** (INCONCLUSIVE — recon a CORRECTEMENT
  flaggé que Maladus (Resilient + TerminatorArmour + Contagion, 12k) exige un bypass Psychic/Direct, MAIS
  mon roster all-melee n'en avait AUCUN → le bypass n'a pas pu être exercé. Le matchup était structurellement
  défavorable dès le déploiement ; le principe reste valide, non testé faute d'outil. Renforce la doctrine
  voisine : un roster all-melee SANS Psychic/Direct vs un anvil Resilient+TerminatorArmour = mur infranchissable
  — à flagger comme loss structurelle au recon, pas à chiper). **seed 98002 INCONCLUSIVE** (DEUX porteurs
  Terrifying présents — Dante ennemi (deep-strike) + Tjark mien — mais j'ai tué Dante en réactions MÊLÉE,
  PAS via un test de bypass ranged isolé : la réduction-mêlée n'a pas été isolée, une réaction multi-source
  l'a submergée. Le principe n'a pas été exercé proprement ce match). **seed 98001** (confirm — APPLICATION
  ANTI-PSYKER DÉCISIVE : Tjark `HuntersBeyondDeath` = +582 PAR HIT vs Psyker + aura de suppression −582 sur
  les Psykers ennemis dans 2 hex ; vs un roster 3-Psyker [Xybia/Abraxas + Archimatos-class], Tjark a K!'d Xybia
  (8514) outright + chunké Abraxas 7026→784 en un hit (~6242) → c'est l'aura/bonus anti-Psyker, PAS un test de
  bypass-Terrifying ranged. NUANCE : ce match confirme le VOLET anti-Psyker de HuntersBeyondDeath comme un hard
  anti-engine tool vs un engine-set Psyker-lourd, distinct du volet Terrifying-melee-only de H11 — les deux sont
  des « bypass d'un mécanisme défensif » mais le levier ici est le +582/suppression Psyker, désormais vérifié
  live n=1 comme assassin de casters). **seed 70001** (confirm — VOLET « bypass d'un mécanisme défensif » côté
  Direct/TerminatorArmour : Azrael DarkTalonStrike = profil **DirectDamage Pierce100** → a bypass entièrement le
  **TerminatorArmour de Njal** (Psychic/Direct exclus de la réduction −75%, cf. §1) ET a chunké/Pinned les deep-strikers
  (Mataneo 5124 + leur Dante 1189 splash) sans réduction. SÉPARÉMENT confirmé même match : un **focus multi-attaquant**
  bat TerminatorArmour en un team-turn — sur Njal, 1ʳᵉ attaque (Dante 4-hit normal) réduite à 418, puis chaque attaquant
  DISTINCT suivant tape full (Jain Zar 4828, Azrael 2786) → Finished T4. NUANCE : la même famille « bypass via Direct/
  Psychic OU multi-attaquant » s'applique à TerminatorArmour comme à Terrifying — distincte de H11 (Terrifying=melee-only)
  mais cousine (les deux = réduction défensive contournable). Cf. wiki §1 TerminatorArmour pour le détail dédié). **seed 70056**
  (confirm — bypass-Terrifying RANGED EXERCÉ proprement : Re'vas (ranged r2) a chunké l'Atlacoya-enemy Terrifying 2956→363 en un
  tir, pleine valeur, AUCUNE réduction-mêlée appliquée → le ranged passe à plein vs Terrifying ; mes 3 ranged dealers
  (Calandis/Vindicta/Re'vas) ont ignoré le Terrifying du mirror Atlacoya tout le combat. Contraste avec mes propres unités mêlée
  qui auraient été réduites). **seed 70055** (INCONCLUSIVE — le VOLET anti-Psyker n'était pas testable et le bypass-Terrifying
  ranged n'a pas pu être exercé : (a) MON Tjark `HuntersBeyondDeath` (anti-Psyker) était ENTIÈREMENT INERTE — l'ennemi
  avait ZÉRO Psyker → confirme la règle SYMÉTRIQUE de l'engine-inerte côté MOI (une aura anti-X ne vaut que s'il existe une
  cible X valide), mais Tjark réduit à un melee plat 4× Physical Pierce1 Terrifying-blunté = pas un test de kill-tool ;
  (b) côté MIROIR, Atlacoya-ennemi était Terrifying MAIS aussi anti-Psyker (DaughterOfTheAbyss −1892 Psychic flat) et mon
  roster n'avait que du Psychic (négaté) + de la mêlée (Terrifying-blunted) → AUCUN ranged non-Psychic pour exercer le
  bypass-Terrifying ranged → le levier H11 n'a pas pu être appliqué. Principe non réfuté ; ce match confirme surtout le
  MIROIR de la règle anti-X (mon aura anti-Psyker INERTE faute de cible) et l'inverse (l'aura anti-Psychic adverse LIVE
  car JE fielde des Psykers), pas le bypass ranged lui-même).
  **n=6** → confirmée.
- **note** : Terrifying transverse est déjà en wiki §1 (réduit la mêlée subie). Le wiki §1 (l.98-101) note
  DÉJÀ « bypass fiable = RANGED ; armor-ignore/perforant ne le bypasse PAS » → inscription FAITE.
- **evidence** : seed 70015, seed 91003, seed 93001.

## H12 — Resilient × multi-hit d'UN SEUL actif : les hits suivants ne finissent PAS forcément depuis 1 PV — `réfutée` (pour:1 contre:2) → SUPPRIMER le claim (le wiki §1 tient ; le cas 91004 = artefact mécanique distinct)
Un multi-hit d'UN SEUL actif qui déclenche Resilient (set à 1 PV via i2 « reduced to 1 Health unless
Overkilled ») ne garantit PAS que ses hits SUIVANTS de la même séquence overkillent/redéfont depuis 1.
**RÉFUTÉE (seed 95002, recoupé Verif vs i2)** : BringerOfDespair 4+4 sur Yarrick (570 PV, Resilient) →
1er hit floored à 1 (Resilient fire, Attack_WasOverkill=0), 2e hit tue (1→0). La précondition i2 Resilient
« If this unit is **not already at 1 Health** and would be defeated, its Health is instead reduced to 1 »
**adjudique explicitement** : hit 1 (unit >1 PV, non-overkill) → Resilient → 1 PV ; hit 2 (unit DÉJÀ à
1 PV) échoue la précondition → Resilient ne peut pas re-trigger → 1→0 mort. C'est une **règle déterministe
i2** (pas statistique) → 1 instance suffit. → le claim fort wiki §1 (« tout hit SUIVANT du même tour trouve
'déjà à 1' et tue », identique pour le multi-hit single-actor) **TIENT**.
- **réconciliation du cas 91004** : Abaddon 5-hit sur Macer (4e met à 1, 5e = 0 dmg, pas de kill) =
  **artefact mécanique DISTINCT** (n=1 anecdotique), PAS une réfutation du clamp : probablement un hit
  bloqué (Daemon/Block, Macer World Eaters), un Attack_DidBlock, ou un hit qui a manqué — pas une preuve
  que « le hit suivant à 1 PV ne tue pas ». Le mécanisme i2 prédit le kill ; le cas 91004 reste un outlier
  non expliqué, pas une règle.
- **doctrine** : NE PAS planifier autour d'« un multi-hit ne tue pas un Resilient » — il LE TUE (clamp
  consommé au 1er hit létal, hits suivants tuent depuis 1, sauf si un hit est bloqué/manqué/Overkill au
  1er). Garder la prudence H04 (le LABEL K! ne soustrait pas le clamp) mais le FAIT mécanique = multi-hit
  bat Resilient.
- **evidence** : seed 91004 (pour, n=1, outlier non expliqué) ; **seed 95002** (contre — BringerOfDespair
  2e hit tue depuis 1 PV, i2-adjudiqué) ; 91001/91002 (cohérents avec « 1 actif floor-puis-2e-source » =
  PAS un contre ; le 2e hit du même actif suffit aussi). **seed 95000 inconclusive** (Abaddon jamais focus
  multi-hit ; Mataneo HammerOfWrath a fini Imospekh non-Resilient). → **n=2 contre, claim supprimé.**

## H13 — Certains actifs AoE héros = USAGE UNIQUE par combat (usable:false/cooldown:null), pas un cooldown — `provisoire` (pour:1 contre:0)
Certains gros actifs AoE (DoomSiren id1199, MurderousSwing id1137, DeathFromAbove id1003) passent à
`usable:false` / `cooldown:null` APRÈS un seul usage et **ne se rafraîchissent JAMAIS** (≠ cooldown qui
revient). Vécu seed 91014 : dumpés tous les 3 en un alpha T1 (2 kills) → plus aucun burst le reste du
combat → attrition perdante vs un stack armure+repair. NON dérivable de gameconfig (le bloc ability ne
porte aucun champ cooldown/charge/once-per-battle — c'est une mécanique de slot runtime).
- **à valider (n=1)** : confirmer le set d'abilities concernées + que c'est bien « once-per-battle » et
  pas un cd long mal lu. **decisionView usable/cooldown = source de vérité runtime** à lire AVANT de
  committer.
- **doctrine candidate** : avant de dépenser DEUX gros AoE dans un même tour, vérifier via decisionView
  si chacun est rechargeable ; contre un stack armure+repair, dépenser le burst sur l'ENGINE DE SUSTAIN
  (Gibbas/repair), pas sur la cible la plus atteignable.
- **evidence** : seed 91014 (n=1, live). **seed 97000 inconclusive** (Foehammer d'Arjac passé à [indispo]
  après un seul usage, jamais rafraîchi le combat → cohérent avec un actif hero once-per-battle ; MAIS
  Foehammer est SINGLE-TARGET (Stun r2), pas un gros AoE → data point FAIBLE pour le set H13 (DoomSiren/
  MurderousSwing/DeathFromAbove, tous AoE) ; corrobore le pattern « certains actifs hero ne se rechargent
  pas » sans confirmer qu'il soit limité aux AoE). **seed 70002 inconclusive / data point NUANCÉ** : DEUX
  comportements opposés observés sur un même combat — (a) Burchard `FragstormGrenadeLauncher` est passé à
  [indispo] après un 1er usage PUIS est RE-APPARU [prêt] et a été ré-utilisé le tour suivant (double-kill
  TG+Scarab) → **NOT once-per-battle = cooldown standard** ; MAIS Frag est un actif single-target Blast,
  pas un gros AoE du set H13 → data point FAIBLE pour le set ; (b) `DoomSiren` (Adamatar, id1199 = membre
  du set H13) est resté [indispo] après son unique usage T1 → **cohérent avec H13** (once-per-battle). Net :
  ce match RENFORCE que le « no-refresh » est ability-spécifique (DoomSiren oui, Frag non) et que le set H13
  doit être lu par-ability via `decisionView usable/cooldown` AVANT de committer, PAS généralisé à « tout gros
  actif ». N'étend PAS le set ; conforte DoomSiren dedans + exclut FragstormGrenadeLauncher.
- **evidence (suite)** : **seed 70001 inconclusive** (DEUX gros actifs AoE hero — DarkTalonStrike (Azrael) +
  SilentDeath (Jain Zar) — sont passés à [indispo] après UN seul usage et ne se sont JAMAIS rafraîchis le reste
  du combat → cohérent avec le pattern once-per-battle (ni cooldown ni munitions surfacés). ⚠ data point favorable
  MAIS candidats potentiels au set, PAS encore membres confirmés (DoomSiren/MurderousSwing/DeathFromAbove) — à
  recon par-ability via decisionView usable/cooldown. NOTE comportementale POSITIVE distincte du failure-mode
  91014 : j'ai dépensé CHAQUE actif UNE fois et à bon escient (chacun a dénié/chunké un deep-striker), pas dump
  des deux AoE en un alpha gâché → le bon usage d'un once-per-battle = le réserver pour un swing décisif, pas
  l'alpha-dump. n'étend PAS le set tant que le no-refresh de DarkTalonStrike/SilentDeath n'est pas re-confirmé n>1).
- **evidence (suite)** : **seed 70004 (confirm DoomSiren + nouveau candidat RitesOfRestoration)** : (a) `DoomSiren`
  (Adamatar, id1199 = membre du set H13) est passé à [indispo] dès le DÉBUT de mon 1er tour d'action et NE s'est
  JAMAIS rafraîchi tout le combat → cohérent avec once-per-battle (n+1, conforte DoomSiren dans le set). ⚠ DÉCISIF :
  DoomSiren est mon SEUL burst Direct Pierce100 (bypass block/armure y compris MomentShackle) — le dépenser tôt m'a
  laissé chip-only vs l'anvil self-healing Trajann = root cause de la loss → le bon usage d'un once-per-battle anti-block
  = le RÉSERVER pour le tank Resilient/self-heal qui sera la wincon late, pas l'alpha-dump (même leçon que 91014, mais
  ici le manque a été décisif sur un anvil INKILLABLE autrement). (b) `RitesOfRestoration` (Isabella, Hero active) est
  AUSSI passé à [indispo] après UN usage (resurrect Ulf + heal) et ne s'est jamais rafraîchi → candidat potentiel au
  pattern hero-active no-refresh, MAIS PAS membre confirmé du set AoE (DoomSiren/MurderousSwing/DeathFromAbove) : c'est
  un actif sustain, pas un gros AoE — à recon par-ability via decisionView usable/cooldown, n'étend PAS le set. NET :
  conforte DoomSiren once-per-battle ; ajoute RitesOfRestoration comme data point hero-active no-refresh (non-AoE).
- **evidence (suite)** : **seed 70052 inconclusive (data point FAIBLE, enemy-active non-testable côté tueur)** :
  Adamatar `DoomSiren` (id1199, membre du set H13) et Re'vas `EarlyWarningOverride` sont des actifs ADVERSES — je
  n'ai pas pu tester leur refresh depuis MON côté (jamais consommés par moi, l'IA les pilote). Re'vas EWO observée
  cast UNE seule fois T1 (2 drones + OW armé) et jamais re-castée le reste du combat = COHÉRENT avec le pattern
  once-per-turn/long-cd déjà inscrit pour EWO (cf. §3bis Re'vas, seed 70000), mais EWO est un actif turret/summon,
  PAS un gros AoE du set H13 (DoomSiren/MurderousSwing/DeathFromAbove). N'étend PAS le set, n'apporte AUCUN nouveau
  data point sur le no-refresh des AoE ; conforte seulement le « EWO non re-armable à volonté » (déjà au wiki).

## H14 — L'IA native concentre le feu pour ~1 kill/tour (HP-agnostique) ; les rosters short-range se font attrition — `provisoire` (pour:1 contre:0)
Vs des compos ranged-lourdes, l'IA native tend à **concentrer le feu** pour sécuriser ~1 kill/tour sur
la cible la plus létale (ignore les PV, même un tank 12k), et les rosters short-range qui ne peuvent pas
fermer la distance se font attritionner. Comportement ÉMERGENT (poids dans BattleConfiguration.Utilities,
PAS une ability gameconfig — « focus-fire »/« danger » n'existent pas comme mécaniques). n=1 (seeds 91001 :
12050 sur Snotflogga T1 puis 11947 sur Atlacoya T2).
- **à valider** : rejouer un seed ranged-vs-melee fixe, confirmer la cadence 1-kill/tour n≥2 avant
  promotion. Counter-test : roster mêlée avec gap-closers/Infiltrate, ou écran ranged à soi.
- **evidence** : seed 91001 (n=1).

## H15 — ExemplarOfHate (Asmodai) : le rider « si Chaos » (Suppress + frappe Dark Angel gratuite) est gaté par la portée d'attaque normale du Dark Angel — `provisoire` (pour:1 contre:0)
ExemplarOfHate applique le +728 mark melee/Overwatch (confirmé i2, n'importe quel ennemi). Le rider
« si la cible est Chaos : Suppress + un Dark Angel allié fait une attaque normale gratuite (100% dmg,
cap 4365/hit) » est conditionnel à la cible Chaos ; i2 ne déclare AUCUN gate de portée, MAIS comme le
rider est littéralement « une attaque normale contre la cible », il est gaté par la portée/LoS du Dark
Angel exécutant. Vécu seed 91002 (n=1) : Asmodai (seul Dark Angel) ~2 hex de Wrask (Chaos) → seul le
mark a atterri, le Suppress+frappe gratuite N'A PAS fire (Asmodai mêlée, cible hors portée mêlée).
- **doctrine candidate** : positionner Asmodai **adjacent** à la cible Chaos visée avant de caster pour
  la pleine valeur. Pas encore prouvé (pourrait aussi être faction-classif ou timing de capture).
- **evidence** : seed 91002 (n=1) ; **seed 98004** (INCONCLUSIVE sur le rider — le rider Chaos (Suppress +
  frappe DA gratuite) NON testable ce match : seul Chaos adverse = Nauseous (deathRotbone), jamais amené
  adjacent à un Dark Angel (Asmodai). Le **mark +728 plat reste CONFIRMÉ** : a boosté Haarken
  HeraldOfTheApocalypse de 2832-4248 → 6024-7436 sur Helbrecht marqué (delta ~3192 ≈ 4 hits × 728 +
  variance LetTheGalaxyBurn/écho) — la partie +728 du claim tient, seul le rider Chaos reste non vérifié).
- **evidence (n+1, seed 81003, ts=b9, team2 W — self-play 2 sides)** : le rider Chaos a PARTIELLEMENT fire — A
  (about:theirs, high) a observé sur Abraxas (Chaos) marqué : `ExemplarOfHate_Target` + **Pinned** (no-retreat) +
  **suppression** → donc la clause Chaos DÉCLENCHE bien des effets (Suppress + Pin) sur cible Chaos. B (about:mine,
  med) confirme le mark + que le +728 a rendu KillMaimBurn exact-K!. ⚠ Le sous-claim spécifique « frappe DA normale
  GRATUITE » n'est explicitement confirmé par AUCUN des deux ce match (adjacence Asmodai↔Abraxas non établie au
  moment du mark) → la partie Suppress+Pin du rider Chaos est désormais OBSERVÉE (pour:2), la frappe-gratuite +
  son gating-portée restent non vérifiés. cf. selfplay-journal seed 81003 (ts=b9).

## H16 — MindControl (Xybia) : tuer le TAUNTER bondé retire le lock mais PAS les modificateurs de dmg (heal requis) — `provisoire` (pour:1 contre:0)
MindControl debuffe la cible (−dmg / +dmg subi) + la Taunt par l'allié adjacent au PLUS HAUT PV (pas le
caster). Les modificateurs de dmg ET le Taunt sont heal/repair-cleansables (i2 confirmé). HYPOTHÈSE n=1
(seed 91008) : tuer le taunter bondé clear le Taunt/BlockMovement/CantUseAbility immédiatement (la cible
ré-agit) MAIS les modificateurs de dmg PERSISTENT → il faut un heal/repair pour les stripper. Cohérent
avec le modèle bonded-taunter mais non stated par gameconfig/i2.
- **NUANCE (seed 98001, n=1, verdict « plausible »)** : ce match-ci le taunter forcé était **Xybia elle-même**
  (le CASTER se trouvait être l'allié adjacent au + haut PV de ma cible MindControlled, Tjark). Le bundle observé
  = 6 sous-effets sur Tjark (`Taunted_OnlySpecificTargets` + `Taunted_BlockMovement` + `Taunted_CantUseAbility` +
  `Taunted_RefreshUnitTurnFinished` + `MindControl_OutgoingDamageReduction(−582)` + `MindControl_IncomingDamageBonus(+20%)`).
  `OnlySpecificTargets` a FORCÉ Tjark à taper Xybia ; tuer Xybia **dans cette même action a clear les 6 effets d'un
  coup** (lock ET modificateurs de dmg). ⚠ Ce n'est PAS un contre de H16 : H16 disait que tuer un **taunter-allié
  bondé ≠ caster** retire le lock mais PAS les débuffs de dmg ; ici on a tué le **CASTER**, ce qui termine TOUTE la
  MindControl (caster mort = effet entier dissipé, distinct du cas taunter-bondé). DOCTRINE émergente : si le taunter
  forcé EST le caster Xybia (adjacent au + haut PV), router la frappe forcée pour la TUER = free-clear total ; si le
  taunter est un autre allié bondé, le tuer ne lève que le lock (cf. H16, heal requis pour les débuffs dmg).
- **à valider** : isoler les deux régimes sur n>1 — tuer-le-caster (clear total) vs tuer-un-taunter-bondé≠caster
  (lock seul). Recoupe le cleanse heal/repair (wiki §1 MindControl) et le counter-play taunt-forced (wiki §1/Xybia §3bis).
- **evidence** : seed 91008 (n=1, live) ; **seed 98001** (n=1, live, verdict « plausible » — kill-du-caster = clear total,
  régime distinct du bonded-taunter).

## H17 — Anuphet ResurrectionOrb = défaut d'`act` sans --ability ; summons non-commandables au tour de spawn — `provisoire` (pour:1 contre:0)
Sur Anuphet (necroOverlord), `act ability` SANS `--ability` auto-résout vers ResurrectionOrb (id 1009,
summon sans dmg) au lieu de l'attaque normale (id 69) → TOUJOURS passer --ability explicite. Les Necron
Warriors invoqués (Gauss r2 ranged) apparaissent **non-commandables le tour du spawn** (jamais dans
« à activer ») mais menacent via Overwatch générique (réagissent au move ennemi en portée s'ils n'ont pas
attaqué). HYPOTHÈSE n=1 : la règle « non-commandable au spawn » n'est pas dans gameconfig/i2 — re-vérifier.
- **lié** : recoupe la règle générale « attaque normale = id concret par unité, passer --ability explicite,
  vérifier mutated=true » (déjà wiki §1) ; ici cas spécifique d'auto-résolution vers un summon.
- **evidence** : seed 91013 (n=1, live) ; **seed 93001** (corrobore la pratique « --ability explicite » :
  act ability 69/1104/1002/1195 passés explicitement tout le match → aucun no-op/auto-résolution ; le
  versant Ambush-genesMagus + MindControl-forced-taunt de ce match part au wiki §1, cf. ci-dessous).
  **seed 98001** (corrobore — `--ability 69` explicite passé sur CHAQUE attaque normale tout le match → zéro
  auto-résolution no-op ; renforce la pratique « toujours --ability explicite ». ⚠ NOTE distincte : une attaque
  Grot-sur-Hollan via `act ability` a montré 0 dmg + consommé l'action du Grot — cohérent avec le constat « les
  summons sont auto-pilotés/non-commandables manuellement » (cf. wiki §3 / 97001) plutôt qu'un test de l'auto-résolution
  d'Anuphet).

## H18 — Azkor Daemon block = 25% chance de bloquer ≤50% de SON propre Damage stat ; NoBlocking/Psychic bypasse-t-il ? — `provisoire` (pour:1 contre:0)
worldEightbound (Azkor) trait Daemon = 25% chance de bloquer **jusqu'à 50% de son PROPRE Damage stat
courant** (PAS 50% du coup entrant — gameconfig daemonBlockChance=25, daemonBlockDamagePercentage=50).
Empilé avec Resilient (1 PV sauf Overkill) + Terrifying (−mêlée) = tank d'attrition melee-proof ;
OVERKILLer le coup létal pour bypasser Resilient. HYPOTHÈSE n=1 (NON prouvée) : NoBlocking / Psychic
ranged bypasse le block Daemon — NoBlocking n'existe que comme effet moteur (pas de source i2), rien ne
prouve qu'il (ou le type Psychic) ignore le block Daemon. Vécu 91009 : 2 hits mêlée gutted (3102→159
avec Attack_DidBlock=1) → la perte du combat 3v1 vient de l'absence de finisher ranged armor/block-ignoring.
- **à valider** : tester un coup NoBlocking/Psychic ranged sur un Azkor et observer Attack_DidBlock.
- **doctrine candidate** : un Resilient+Daemon+Terrifying = cauchemar last-man ; identifier T1 et
  réserver une source RANGED block/armor-ignoring (Psychic NoBlocking) + un finisher Overkill.
- **evidence** : seed 91009 (n=1, live) ; **seed 70006 (INCONCLUSIVE — Azkor (worldEightbound, MIEN ce match : Daemon
  block + Resilient + Terrifying) a TANKÉ l'Overwatch ranged de Maugan Ra (~5675 sur 6 hits) ET la mêlée de Ragnar
  taunt-locké comme prévu = anvil melee-proof reconfirmé ; MAIS je n'ai jamais landé de hit NoBlocking/Psychic ranged SUR
  Azkor ni sur une unité Daemon → le claim central (NoBlocking/Psychic bypasse-t-il le block Daemon ?) reste NON TESTÉ.
  Abraxas (mon seul Psychic ennemi) est mort avant de caster son Psychic ranged sur mes units. Principe d'anvil
  melee-proof re-confirmé, mais le mécanisme de bypass toujours à n=0 — pré-positionner un test délibéré
  Psychic-ranged-sur-Azkor un prochain match)**.

## H19 — Harness : finir un tour via `act endturn`, PAS `act finish` par unité — `provisoire` (pour:1 contre:0)
Pour finir MON tour d'équipe utiliser `act endturn` (EndTurnMessage via runner.Apply), PAS `act finish`
par unité (FinishUnitTurnMessage via le chemin IA = message d'activation par-unité, pas une fin de
tour-équipe). Vécu n=1 (seed 91014) : chaîner `finish` sur toutes les unités a semblé RESET l'activation
(unités de retour en « à activer », positions restaurées) et un `endturn` suivant était un no-op
(mutated=false). Architecture-cohérent (internals.ts : deux messages/chemins différents) mais non
confirmé par gameconfig/i2 (hors domaine). À reproduire avant promotion.
- **note infra connexe (multi-matchs)** : le PREMIER `endturn` après avoir fini ma dernière unité rend
  parfois la preview de menace adverse sans flipper currentPlayer (mutated=false, player inchangé) ; un
  2ᵉ `endturn` flippe correctement. Idem `aiturn` parfois requis 2× pour jouer un tour adverse complet
  (le 1ᵉʳ calcule la preview/réaction). À surveiller dans ai-step.ts (endturn→switch quand une réaction
  Overwatch s'interpose). Vu sur 91000, 91002, 91003, 91006, 91010, 91014.
- **evidence** : seed 91014 (n=1, live) + observations infra récurrentes de la vague. **seed 95000
  inconclusive** : `endturn` utilisé correctement, mais le test du reset/no-op est confondu par les
  erreurs de format `play --spec` (move string `'5,3'` → ERR + cascade mutated=false) qui ont gâché
  les tours indépendamment du chemin endturn/finish.

## H20 — Resilient × DoomSiren multi-hit : un Resilient SURVIT à un DoomSiren létal non-overkill — `provisoire` (pour:1 contre:0) ⚠ à réconcilier vs wiki §1
- **claim (plausible, n=1)** : un Resilient (Lucien) a SURVÉCU à un DoomSiren entrant létal (floored à 1
  PV, non-overkillé) — cohérent avec le texte i2 Resilient (set à 1 PV sauf Overkill). **OPEN QUESTION à
  réconcilier vs wiki §1** : DoomSiren est un actif **3-hit** (gameconfig nrOfHits=3, nrOfUnits=2, Direct
  Pierce100), or la règle canonique §1 prédit que tout hit SUIVANT à 1 PV le même tour tue. Survie
  explicable (DoomSiren répartit sur la cible primaire + ≤2 adjacents random → pas forcément tous les 3
  hits sur Lucien ; les « 5x counters sur Adamatar » sont des ripostes SORTANTES de Lucien, pas des hits
  létaux entrants) mais le mécanisme n'est PAS épinglé.
- **à valider** : confirmer la distribution réelle des hits — si les 3 hits ont touché Lucien et qu'il a
  vécu, ça CONTREDIRAIT « hit suivant à 1 PV tue » ; plus probablement ≤1 hit létal l'a atteint.
- **NE PAS promouvoir au wiki** tant que la distribution n'est pas vérifiée (le floor lui-même est déjà
  canonique §1). Lié à H04/H12. ⚠ ne pas lire comme une règle générale « Resilient survit aux multi-source
  distribués » (contredirait la doctrine focus-kills-Resilient).
- **evidence** : seed 93001 (n=1, live, verdict « plausible »).

## H21 — Drachnyen (Abaddon) : la 2ᵉ attaque enchaînée auto-cible un ennemi DIFFÉRENT du primaire — `provisoire` (pour:1 contre:0)
- **claim (n=1)** : la 2ᵉ attaque récurrente de Drachnyen (3× Pierce80 après chaque normale mêlée) auto-
  ciblerait un ennemi adjacent **différent** de la cible primaire. Vécu seed 95001 : Abaddon a tapé Sy-gex
  en primaire, la chaîne a auto-tapé l'adjacent Tjark pour 2386 total.
- **caveat (gameconfig/i2)** : le CORE est CONFIRMÉ (set 4729 HP capé au max + 2ᵉ attaque permanente 3×
  Pierce80) et inscrit au wiki §2. MAIS i2 ne dit que « an adjacent enemy unit » — il ne stipule PAS que
  ce soit un ennemi DIFFÉRENT du primaire. L'observation est cohérente avec « auto-cible un adjacent au
  hasard » (qui se trouvait être Tjark, Sy-gex n'étant peut-être plus le seul adjacent). Non prouvé.
- **à valider** : observer plusieurs activations où le primaire reste seul adjacent → la chaîne le re-tape-
  t-elle, ou cherche-t-elle obligatoirement un autre ?
- **evidence** : seed 95001 (n=1, live, verdict « confirmed » sur le core, caveat sur le ciblage) ;
  **seed 70003** (INCONCLUSIVE — Abaddon (blackAbaddon/Drachnyen) dans mon roster, voulais tester le ciblage
  de la 2ᵉ attaque enchaînée, mais cela exigeait de mêler Abaddon avec 2 ennemis adjacents = une over-extension
  que j'ai évitée, et le combat s'est terminé (abandon round 2) avant un test sûr → non exercé. Le claim de
  ciblage reste à n=1).
  **seed 70059** (INCONCLUSIVE — Abaddon (blackAbaddon/Drachnyen) présent CÔTÉ ADVERSE, candidat-cible d'H21, mais il n'a
  JAMAIS performé une attaque normale mêlée ce match : resté ranged / grindé via mon Psychic stacké (gardé en ranged-poke
  pour éviter sa riposte Drachnyen double-attack), puis overkill T5 → la 2ᵉ attaque enchaînée Drachnyen ne s'est jamais
  déclenchée → le claim « la chaîne auto-cible un ennemi DIFFÉRENT du primaire » non exercé. Le ciblage reste à n=1).

## H22 — TerrifyingCrescendo (Shiron) : un crit étend-il la durée de ThrillSeekers ? — **RÉFUTÉ** (RE décompilé + live)
- **claim (réfuté)** : un retour combat (seed 95001) affirmait qu'« un crit d'ExcruciatingFrequencies étend
  la durée de ThrillSeekers ».
- **verdict** : **FAUX**, tranché par le décompilé, pas par une statistique.
  `IdunBattleLogic.Entities.Abilities.Triggered.Loki.ThrillSeekersAbility$$CreateTrigger` ne contient
  **aucun** prédicat de crit : ses deux seules branches sont
  `On(PreAttackHit) & IsFirstHitInSeries & OwnerIsCaster & Not(IsWounded(target))` et
  `On(DamageTaken) & OwnerIsTarget`. Le `CreateBehaviour` pose une durée FIXE
  `TurnsFromRounds(nrOfRounds=1)` et, si l'effet est déjà porté, la **REMET** à cette même valeur
  (`ChangeEffectTurns` avec `ChangeType.Set`, jamais `Add`) — donc pas d'extension cumulative possible,
  quelle qu'en soit la cause.
- **evidence live** (`case-thrillseekers`) : durée mesurée `remaining = 2` à chaque pose ET à chaque
  refresh, décrément d'1 par `EndTurn`, retrait au 2e. Le CORE de TerrifyingCrescendo (+218 dmg ranged par
  Overkill/Suppress, cap 6) reste i2-confirmé et porté (#204) — c'est seulement le sous-claim
  « ThrillSeekers-extend » qui tombe.

## H23 — Aberrant (genesSmnAberrant) : « TriggeredAbility 1271 » réaction au mouvement ennemi ? — `provisoire` (pour:1 contre:1-gameconfig)
- **claim (n=1, douteux)** : un retour combat (seed 95001) attribue à l'Aberrant invoqué une
  `TriggeredAbility 1271` qui fire en RÉACTION quand un ennemi bouge adjacent (observé : −1645 sur Tjark
  en réaction, puis kill de Tjark à 237 PV / d'un Ork Boy à l'endturn).
- **CONTRADICTION (gameconfig/i2)** : la carte de genesSmnAberrant n'a **AUCUNE ability triggered/réactive**
  (traits = Summon, Ambush, Resilient ; passif Hypermorph = +15% PV courant en dmg) et l'id 1271 est
  **absent** de `frida/hooks/data/ability-names.ts`. Le « réaction au mouvement » est plus probablement
  une **mésattribution** : un Overwatch d'une autre unité, ou l'auto-attaque Summon (auto move+attack en
  début de tour) prise pour une réaction. La causalité « Hollan a healé l'Aberrant via le spawn » est aussi
  un guess (summon ≠ heal ; TwistedScience se déclenche sur un HEAL).
- **CONFIRMÉ séparément** : l'Aberrant se summon dans un **hex adjacent LIBRE** (cibler --to col,row, PAS
  --target une entité — sinon mutated=False silencieux) ; base 5456 PV / 2837 dmg / 1019 armure ; peut
  attaquer au spawn mais ne peut pas bouger ce tour ; traits Summon/Ambush/Resilient ; les unités GSC
  healées par Hollan gagnent TwistedScience (+2183 max PV one-time non-stacking + 364 dmg) → inflate la PV
  de l'Aberrant au-delà du base (observé 7477 puis 10469). Ces faits sont déjà au wiki (Hollan §3bis +
  summons §). Les valeurs exactes 7477/10469 sont non-dérivables (runtime).
- **à valider** : recon de l'effet/ability exact sur l'Aberrant qui « réagit » (gameconfig.py --effect,
  decisionView.effects) avant de croire à une réaction native.
- **evidence** : seed 95001 (n=1, verdict « plausible » sur le summon-mechanism, mais le claim
  TriggeredAbility 1271 contredit gameconfig → ne pas inscrire au wiki).

## H24 — FireAndReposition (Calandis/eldarRanger) : usability-gate « target in range » → rejet mutated=false ; le slot est-il consommé ? — `provisoire` (pour:1 contre:0)
- **claim (n=1, plausible — recoupé Verif vs i2)** : `FireAndReposition` (Calandis) est gaté par la clause
  i2 explicite « **Can only be used if Calandis has a target in range** » ; sans cible valide en portée,
  l'ability est rejetée avec `mutated=false`. Vécu seed 95002 : Calandis (0,3) FireAndReposition sur
  Guardsman u154 (0,4, adjacent) → `mutated=false` (cible possiblement déjà morte, ou condition non
  remplie).
- **caveat (gameconfig/i2)** : le MÉCANISME GÉNÉRAL (hard-gate « target in range » → non-usable → rejet)
  est i2-confirmé. MAIS i2 ne prouve PAS les spécifiques n=1 : (a) qu'aucune cible n'était réellement en
  portée à (0,3)/(0,4), (b) que la cible était « déjà morte », (c) que le slot d'action a été CONSOMMÉ par
  le rejet silencieux. L'« in range » dépend de la **portée d'attaque normale** de Calandis + validité de
  la cible (vivante, ennemie, LoS), PAS de la simple adjacence — le raisonnement « adjacent donc devrait
  passer » est faible (FireAndReposition = attaque ranged/normale). Le « -2183 Damage from ranged attacks »
  d'i2 est le buff de réduction-dmg du tour suivant, non lié à la cause du rejet.
- **à valider** : (1) le rejet mutated=false consomme-t-il le slot d'action (cf. doctrine « out-of-range
  attack pas forcément consommée », wiki §1 Tyrith VigilanceEternal) ? (2) critères exacts d'« in range »
  (valeur de portée + validité cible). NE PAS inscrire au wiki tant que ces 2 points ne sont pas vérifiés.
- **doctrine candidate** : avant de caster FireAndReposition, vérifier une cible valide en portée via
  decisionView ; un cast à vide est rejeté (et peut-être gâcher le slot — à confirmer).
- **evidence** : seed 95002 (n=1, verdict « plausible »).
- **seed 70056** (INCONCLUSIVE — Calandis (eldarRanger) avait FireAndReposition `[prêt]` mais ne l'a JAMAIS casté ce match
  (utilisé la normale id69 à la place pour le focus du Tanksmasha + retraite manuelle) → ni l'usability-gate « target in range »
  ni la question de consommation-du-slot-sur-rejet n'ont été exercés. La capacité reste un slot non testé ; H24 toujours n=1.
  NB : le retreat de Calandis a été fait par un move pur, pas via FireAndReposition — l'« attaque + repli intégré » de l'actif
  n'a donc pas non plus été observé en action.)
- **seed 70061** (INCONCLUSIVE — Calandis (eldarRanger) ENNEMIE ce matchup a casté FireAndReposition UNE fois T1 (l'effet
  `FireAndReposition_ReduceDmg` est apparu, OW dépensé) mais je n'ai testé NI le gate « target in range » NI la question
  consommation-du-slot-sur-rejet : Calandis est morte T2 (Tanksmasha melee chunk 7029→2300 → Certus OW finish) avant tout
  usage supplémentaire. L'actif a été observé EN ACTION (attaque + reduce-dmg du tour suivant) côté ennemi, mais aucun rejet
  mutated=false n'a été exercé. H24 toujours n=1, les 2 points à valider restent ouverts.)

## H25 — TimeFlux (Toth) : un seul ghost à la fois, relocalisé/écrasé par chaque re-move — `provisoire` (pour:1 contre:0)
- **CORE i2-CONFIRMÉ (inscriptible séparément, déjà non-derivable)** : `TimeFlux` laisse un **time ghost
  sur l'hex quitté à CHAQUE move** ; le ghost **DISPARAÎT si l'hex devient occupé par une autre unité OU
  impassable** (Broken Ice) ; à la **1ʳᵉ mort de Toth chaque combat**, si un ghost est présent → **revive
  2401 PV à l'emplacement du ghost** (marche même si Overkillé).
- **claim HYPOTHÈSE (n=1, NON prouvé par i2)** : Toth n'a **qu'UN SEUL ghost à la fois** — un nouveau move
  RELOCALISE/ÉCRASE le précédent (vu côté moteur comme `LoseEffect`/`DeactivateEffect` sur l'ancienne tile
  + nouveau `ReceiveEffect` sur la nouvelle). i2 parle du ghost « on the hex he moved from » (singulier),
  cohérent avec un modèle un-seul-ghost-qui-se-déplace, mais **n'affirme JAMAIS explicitement l'overwrite
  ni l'invariant single-ghost** (détail d'implémentation moteur).
- **cause de non-revive observée (seed 96001)** : Toth bougé 3× (T1→2,2 ; T2→3,6 ; T3→5,5) → ghost
  relocalisé à chaque move ; à sa mort, aucun revive. **Cause probable corroborée par i2** = ghost invalidé
  car hex occupée par une unité ennemie (le « ghost ≈ position de Jaeger adjacente » reste SPÉCULATION n=1 —
  l'i2 dit que le revive se fait « at its location », PAS conditionné par l'adjacence).
- **doctrine candidate** : déplacer Toth **UNE SEULE FOIS** pour poser le ghost à un endroit SÛR (hex qui
  ne sera ni occupé ni piétiné), puis **ne plus bouger** (sinon le ghost suit le dernier move, souvent au
  contact ennemi = invalidé).
- **à valider** : observer plusieurs moves successifs → reste-t-il un seul ghost (ancien disparu) ou
  plusieurs ? + cause exacte de la non-revive (hex occupé vs adjacence).
- **evidence** : seed 96001 (n=1, verdict « plausible »).

## H26 — Forcas (darkaCompanion) CalibaniteGreatsword = toggle Strike↔Sweep, démarre en Strike/Overwatch → caster RETIRE l'Overwatch (tool trap) — `provisoire` (pour:1 contre:0)
- **⚠ CONFLIT DE NOM À RÉSOUDRE** : l'unitId `darkaCompanion` est inscrit au wiki §3bis (l.959) comme
  **« Sarquael » (Dark Angels, ranged, Supercharge+GrimRetribution)** — MAIS dans ce combat (seed 97000)
  `darkaCompanion` = **« Forcas »** (Dark Angels, melee carry, CalibaniteGreatsword stance-toggle + Parry +
  Camouflage). Kits TOTALEMENT distincts (ranged Plasma vs melee greatsword). Soit (a) deux unités partagent
  le préfixe d'id `darkaCompanion` (display-name divergent selon le héros), soit (b) renommage entre builds.
  **NE PAS conflater Forcas avec l'entrée Sarquael du wiki.** À trancher : recon `gameconfig.py
  darkaCompanion` pour voir quel display-name/kit l'id porte dans le build courant.
- **CORE i2-confirmé (toggle + once-per-turn)** : CalibaniteGreatsword est un **toggle strict Strike↔Sweep**
  (chaque usage switch la Stance active), **une fois par tour** (CanStillBeUsed=0 après cast), **ne termine
  PAS le tour de Forcas**. L'effet `CalibaniteGreatswordStrike` = « commence à Overwatcher à la fin de son
  tour ».
- **claim HYPOTHÈSE (n=1, NON prouvé par gameconfig)** : Forcas ENTRE en combat **déjà en Strike Stance**
  (effet `CalibaniteGreatswordStrike` présent au start = Overwatch-after-turn armé) → **TOOL TRAP** : caster
  l'ability « pour poser l'Overwatch » flip en fait vers Sweep et **RETIRE l'Overwatch déjà armé**. La stance
  de départ n'est PAS dans gameconfig (silence) → observation live-only n=1.
- **doctrine candidate** : si Forcas a l'effet `CalibaniteGreatswordStrike` actif au recon, **NE PAS caster**
  CalibaniteGreatsword si le but est de garder/armer l'Overwatch — ne le caster QUE pour passer aux attaques
  normales AoE de Sweep. Recon la stance via decisionView.effects avant tout cast.
- **à valider** : confirmer la stance de départ (Strike) sur le prochain encounter de Forcas + que le toggle
  retire bien l'Overwatch. Résoudre d'abord le conflit de nom darkaCompanion (Sarquael vs Forcas).
- **evidence** : seed 97000 (n=1, verdict « plausible » recoupé Verif vs i2 sur le toggle/once-per-turn ;
  stance-de-départ + tool-trap = live-only non dérivable).

## H27 — Un cluster défensif avec 2-3 Overwatchers RANGED génère 20-40k de dégâts de réaction sur un dive mêlée adverse — `provisoire` (pour:1 contre:0)
- **claim (plausible, n=1, recoupé Verif vs i2)** : un cluster MIEN défensif tenu, comportant **2-3 unités
  armées en Overwatch**, peut générer **20-40k de dégâts de réaction sur DEUX tours adverses de dive mêlée**
  SANS dépenser d'actions offensives. L'Overwatch fire **indépendamment par unité par move ennemi** → un dive
  groupé empile plusieurs volées par move. Vécu seed 98002 (W) : ~22k puis ~20k de réaction sur 2 tours adverses
  → 5 kills (Thaumachus+Dante enemy-T1, Anuphet+Toth+un Warrior enemy-T2). C'est le MÊME mécanisme que le W 96002
  (turret défensive Burchard/Sy-gex) — la position défensive tenue gagne l'attrition.
- **⚠ CORRECTION D'ATTRIBUTION (Verif vs i2)** : le claim original attribuait une partie de ce dégât à
  **Kharn TheBetrayer** et aux **summons** « en réaction ». **FAUX** : TheBetrayer fire au **DÉBUT du tour de
  Kharn** (pas pendant le move adverse), et les summons (Pink Horror/Screamer) agissent au début de LEUR propre
  tour — **ni l'un ni l'autre ne réagit pendant le tour ennemi**. La masse de dégâts vient des **Overwatch
  empilés** (et des `Counter`/`MartialSuperiority` adjacents, qui eux ripostent bien sur l'attaque entrante).
  Ne pas compter TheBetrayer/summons comme des réactions de tour-adverse dans le bilan.
- **à valider** : reproduire sur ≥2 seeds DISTINCTS avec un cluster Overwatch RANGED + un adversaire dive-happy ;
  isoler la part Overwatch vs Counter ; confirmer le seuil 20-40k. Recoupe la condition H03 (« turret = Overwatchers
  RANGED + ennemi ATTEIGNABLE », cf. 96002 W vs 97001 L où l'Overwatcher MÊLÉE échoue).
- **lié** : H03 (réciproque punish-dive, déjà confirmée n=26 ; cette H quantifie le DÉGÂT de réaction et
  précise QUI réagit) ; doctrine-learned §7 (turret défensif conditionnel à des Overwatchers RANGED).
- **evidence** : seed 98002 (n=1, verdict « plausible » — claim central sain, attribution Kharn/summons corrigée).

## H28 — Thaumachus (thousSorcerer) AttemptedPossession = anti-summon : possède une cible ET ses summons → ils attaquent mon propre camp — `provisoire` (pour:0 contre:0, NON vérifié — recon requis)
- **claim (recon-only, NON exercé seed 98002)** : `AttemptedPossession` (Thaumachus) possèderait un ennemi ET
  **ses summons** → ils attaquent le plus proche ennemi = MES propres unités (jusqu'à 4001/hit) → hard-counter
  d'un plan de mass-summon (Abraxas Pink Horror/Screamer). `ArcaneShield` (4001 PV bouclier à l'allié le plus
  proche après move). Soft (7530, Flying).
- **statut** : **NON VÉRIFIÉ ce match** — Thaumachus est mort T1 dans une réaction Kharn AVANT de caster
  AttemptedPossession ; le claim vient du recon gameconfig, PAS d'une observation live. **AUCUNE entrée wiki
  pour thousSorcerer/Thaumachus n'existe** → ne PAS inscrire le kit au wiki sur la foi du recon seul.
- **incidence sur le PLAY (98002)** : a DISSUADÉ de faire d'Abraxas un mass-summon-engine (utilisé en
  Psyker-burst/InfernalPacts/corps de réaction à la place), et a justifié de tuer Thaumachus TÔT → cohérent
  avec H02 (kill le contrôleur anti-summon avant qu'il agisse). Le choix s'est avéré bon (W) mais le mécanisme
  lui-même n'a pas été testé.
- **à valider** : recon `gameconfig.py thousSorcerer --ability AttemptedPossession` + observer un cast live
  (la possession touche-t-elle vraiment les SUMMONS de la cible ? le dégât retourné ?) AVANT d'inscrire au wiki.
  Recoupe la doctrine « ne pas mass-summoner dans un contrôleur anti-summon » (cf. H01 MoW anti-summon).
- **evidence** : seed 98002 (recon-only, n=0 live ; verdict synergie « avoided » = non déclenchée) ;
  **seed 70000** (INCONCLUSIVE — encore NON testable : Thaumachus a été Taunt-locké tout le combat par
  CrushingClaws de mon Tyrant Guard (Taunted_CantUseAbility) → il n'a JAMAIS pu caster AttemptedPossession.
  Confirme INDIRECTEMENT que le Taunt neutralise totalement cet engine anti-summon (utile pour le play : un
  CrushingClaws sur un Psyker-engine soft = engine-disable propre 1 round), mais le mécanisme anti-summon
  lui-même reste non-vérifié live. TOUJOURS recon-only — ne PAS inscrire le kit au wiki).

## H29 — ArcaneShield (Thaumachus/thousSorcerer) : le bouclier persiste sa durée même si le caster meurt — `provisoire` (pour:1 contre:0)
- **claim (plausible, n=1, recoupé Verif vs i2)** : `ArcaneShield` (id 4001) pose un bouclier (~4001-5483 PV)
  sur l'allié le plus proche après un move ; il dure **une round** (i2 = durée purement round-based, AUCUNE clause
  caster-alive). Vécu seed 98000 : Thaumachus a casté ArcaneShield sur Dreir AVANT de mourir → un bouclier de
  5483 PV a survécu à la mort de Thaumachus et a **absorbé entièrement** une normale Tyrant Guard de 7064 au tour
  suivant (Dreir resté à 2602). → un chip/burst peut être WHOLLY mangé par un bouclier posthume.
- **caveat (gameconfig/i2)** : i2 confirme la durée 1-round sans clause d'annulation à la mort du caster → le texte
  est COHÉRENT avec la survie, mais ne l'affirme PAS explicitement (n=1).
- **doctrine candidate** : si un caster type Thaumachus a posé un ArcaneShield sur une cible que je veux finir,
  budgétiser ~4-5.5k de bouclier en plus de ses PV affichés AVANT de committer le coup létal — le tuer ne dissipe
  PAS le bouclier ce round.
- **à valider** : reconfirmer sur n>1 qu'un bouclier d'un caster mort reste actif sa durée pleine ; valeur exacte
  (4001 base vs 5483 scalé). NE PAS inscrire au wiki tant que non reconfirmé (n=1). **AUCUNE entrée wiki
  thousSorcerer/Thaumachus n'existe** (cf. H28 — kit recon-only non encore inscrit).
- **evidence** : seed 98000 (n=1, live, verdict « plausible ») ; **seed 70000** (INCONCLUSIVE — NON re-testable :
  Thaumachus a été Taunt-locké immédiatement par CrushingClaws de mon Tyrant Guard → il n'a JAMAIS bougé ni
  casté ArcaneShield (Shields_RemainingAmount=0 à chaque hit, aucun bouclier observé) → la persistance posthume
  n'a pas pu être testée. Reste n=1, à re-tester sur un match où Thaumachus n'est PAS Taunt-locké). **n=1**.

## H30 — Taunt = engine-disable (Taunted_CantUseAbility + BlockMovement coupent l'actif d'un summoner/buffer) — `provisoire` (pour:3 contre:0 ; généralisé au-delà de CrushingClaws)
- **CORE i2-confirmé** : `CrushingClaws` = 2× Piercing (1091-1455, ~1440 high-lvl) + **Taunt** + **Suppressed** sur
  la cible.
- **claim HYPOTHÈSE (n=1, au-delà d'i2)** : vécu seed 98000 sur Dreir — le Taunt a posé `Taunted_CantUseAbility`
  qui a **bloqué LeadingTheCharge (id1204)** en laissant seulement la normale (id69) = **a coupé l'actif du
  summoner pour 2 rounds** (i2 dit 1 round → durée 2 non-confirmée, peut refléter upgrade/stacking) ; + **Pinned
  (−1 move)** observé, alors qu'i2 ne liste que Suppressed (le mapping Suppressed→Pinned est un comportement
  moteur non dérivable de gameconfig). = excellent CONTROL : a verrouillé le summoner sur mon anvil et nié 2
  rounds de summons de Death Riders.
- **doctrine candidate** : caster CrushingClaws sur un **summoner** (Dreir) le tour où il dive → coupe son actif
  de summon + le pin sur mon anvil = neutralise l'engine de summon SANS le tuer (utile quand il est Resilient/
  ToughToKill et dur à finir). Reconfirmer la durée (1 vs 2 rounds) et la source du Pinned (Suppressed→Pinned ?).
- **à valider** : durée exacte du Taunted_CantUseAbility (1 vs 2 rounds) + confirmer que Suppressed mappe sur
  Pinned (−1 move) dans le moteur. NE PAS inscrire les spécifiques durée/Pinned au wiki tant que n=1.
- **2ᵉ matchup (seed 70000, verdict Verif « plausible » n=1 sur CE match)** : sur **Thaumachus** (thousSorcerer
  Psyker-engine WeaverOfFate-amplifier), CrushingClaws de mon Tyrant Guard a posé le combo **Taunted_BlockMovement +
  Taunted_CantUseAbility + Pinned** → Thaumachus n'a JAMAIS pu caster AttemptedPossession ni ArcaneShield de TOUT le
  combat (engine-disable propre ; cf. H28/H29 inconclusive pour cette raison). 2× Piercing 1571+1483=3054 observés.
  Confirme le pattern sur une 2ᵉ unité-cible (Dreir summoner → Thaumachus caster) : le Taunt = un tool d'engine-disable
  fiable 1 round contre un Psyker/summoner soft. ⚠ les sous-effets moteur (BlockMovement/CantUseAbility/Pinned) restent
  NON-décrits i2 (n=2 observation) → ne PAS inscrire les spécifiques au wiki ; la durée/Pinned restent à reconfirmer.
- **3ᵉ matchup — SOURCE DIFFÉRENTE (seed 70006, verdict Verif « confirm »)** : `OverwhelmingWrath` (Azkor,
  worldEightbound) a posé sur **Ragnar** (carry mêlée + WarHowl buffer) le combo **Taunted_OnlySpecificTargets +
  Taunted_BlockMovement + Taunted_CantUseAbility + Taunted_RefreshUnitTurnFinished** (visible dans decisionView) →
  Ragnar n'a PAS pu caster **WarHowl** ET était movement-locké, forcé de frapper le taunter (Azkor Terrifying a blunté
  sa mêlée à ~280-420/hit). MÊME famille engine-disable-via-taunt que CrushingClaws, mais d'une **3ᵉ source** (Taunt
  d'un actif World Eaters, pas Tyranid) sur un **3ᵉ type de cible** (buff-engine carry, après summoner Dreir + Psyker
  Thaumachus) → le pattern « le Taunt verrouille les ACTIFS d'un engine pour le round » se généralise au-delà de
  CrushingClaws : c'est un COMPORTEMENT du sous-effet `Taunted_CantUseAbility` lui-même (déjà inscrit §1), pas spécifique
  à une ability. Promu actionnable (§1 Taunt l'a déjà ; ici renforcé = n=3).
- **seed 70054 (INCONCLUSIVE — non testé)** : l'ennemi avait un Tyrant Guard porteur de `CrushingClaws` (Taunt
  engine-disable), MAIS j'ai overkillé le TG en UN tour multi-source AVANT qu'il puisse Taunt-locker une de mes unités →
  le levier engine-disable n'a PAS été exercé ce match (ni côté moi : je n'avais pas de Taunt-carrier ; ni côté lui : il
  est mort avant de caster). Ni confirme ni infirme — note pour traçabilité.
- **evidence** : seed 98000 (Dreir summoner, CrushingClaws, n=1, « plausible ») ; **seed 70000** (Thaumachus caster,
  CrushingClaws, n=1, « plausible ») ; **seed 70006** (Ragnar buff-engine, OverwhelmingWrath, n=1, « confirm ») ;
  **seed 70054** (inconclusive — TG CrushingClaws non exercé, killed before Taunt-lock). Lié :
  §1 Taunt/Taunted_CantUseAbility (déjà inscrit comme « coupe les actifs ») ; ici **3 cas spécifiques d'un engine
  verrouillé via Taunt (summoner / Psyker-amplifier / buff-carry) depuis 2 sources distinctes (CrushingClaws,
  OverwhelmingWrath)**. **n=3** observations live convergentes. ⚠ les sous-effets durée/Pinned moteur de CrushingClaws
  restent non-i2 (à reconfirmer) — mais le CŒUR « Taunt coupe l'actif d'un engine 1 round » est confirmé n=3.

## H31 — Resilient × multi-hit : le hit FINAL peut résoudre à 0 dmg (ToughToKill/crit-reduction) → survie à 1 PV — `confirmée` (pour:3 contre:0) ⚠ géré sous H04 (caveat), pas une réfutation de wiki §1 — RAFFINÉE : le zero-out bloque le kill SEULEMENT s'il est le DERNIER hit
- **claim (confirmé n=3, recoupé Verif vs i2)** : sur un Resilient qui porte AUSSI une crit-reduction (Dreir
  `ToughToKill` −35% crit/−1091 crit dmg ; Macer/Abaddon 91004), un multi-hit d'UN SEUL actif peut floorer la
  cible à 1 PV PUIS un hit résout à **Amount=0** → si ce 0-dmg est le **DERNIER** hit, la cible **survit à 1**.
  Vécu seed 98000 : Haarken 4-hit normal sur Dreir → hits 1-3 (1237+1135+229) floored à 1, hit 4 = 0 dmg, Dreir survit.
- **RAFFINEMENT (seed 70008, CONFIRM n+1, distinct matchup)** : le zero-out ne bloque le kill QUE s'il tombe sur le
  **DERNIER** hit. Sur Dreir (Resilient+ToughToKill), un 6-hit Gauss d'Imospekh a floored Dreir à 1 (Resilient), un hit
  MID-séquence a délivré Amount=0 (ToughToKill zeroed) MAIS un hit ULTÉRIEUR (Amount=1) a tué depuis 1 PV = **full kill
  WasOverkilled=1**. → tant que des hits surplus >0 RESTENT après le zero-out, le multi-hit finit quand même le Resilient.
  Contraste net avec 98000 où le zero ÉTAIT le dernier hit → Dreir a survécu.
- **NON une réfutation de wiki §1** : la règle floor-then-finish TIENT (un hit RÉEL >0 à 1 PV tue toujours,
  i2-adjudiqué, cf. H12 réfutée). La survie en 98000 venait ENTIÈREMENT du **hit final = 0 dmg** (un 0-dmg ne tue à
  aucun HP), explicable par ToughToKill (crit zeroed) ou un hit bloqué/suppressé une fois la cible au floor —
  PAS d'une immunité Resilient post-floor. C'est le MÊME phénomène que l'outlier 91004 (Abaddon 5-hit sur Macer,
  5e hit = 0). Resilient ne fire qu'UNE fois : une fois la cible à 1, la condition « not already at 1 » est fausse pour
  tous les hits suivants ; un hit 0-dmg ne consomme pas Resilient et ne protège pas les hits suivants.
- **doctrine candidate (= caveat H04)** : sur un Resilient + crit-reduction/regen (Dreir, Abaddon, Macer),
  un multi-hit K! tue de façon FIABLE **si des hits surplus >0 existent past le floor** (70008) ; il ÉCHOUE seulement
  si le hit final résout à 0 (98000) → préférer un multi-hit à grand nombre de hits, OU budgétiser un finisher SÉPARÉ.
- **à valider** : est-ce systématiquement le DERNIER hit qui zeroter, ou aléatoire dans la séquence ? Recoupe H04 + H12.
- **evidence** : seed 91004 (Abaddon/Macer, n=1) ; **seed 98000** (Dreir/Haarken, n=1, le zero ÉTAIT le dernier hit → survie) ;
  **seed 70008** (Dreir/Imospekh, n=1, le zero était MID-séquence + surplus hits → full kill WasOverkilled=1, RAFFINE la règle). **n=3**.

## H32 — SYNERGIE ennemie : Aleph-Null repair + Snappawrecka DakkaDakka = carry ranged repair-SCALING — `provisoire` (pour:1 contre:0, status=MISSED)
- **claim (n=1, source gameconfig — composantes PAS toutes Verif-confirmées → candidate, PAS §5bis)** : chaque repair
  d'Aleph-Null (FabricatorClawArray 2910/move + Mechanic) sur **Snappawrecka (orksKillaKan, Mechanical)** AJOUTE **+2
  hits** à son `DakkaDakkaDakka` (6 → 16 hits de 1455-1819, leftover-chain) → **un carry ranged qui devient PLUS létal à
  mesure qu'on le soigne**. Aleph-Null `ScarabHive` summon aussi 2 Scarab Swarms (move4) qui padent le focus ranged.
  C'est le MOTEUR qui out-attritionne un roster mêlée.
- **status = MISSED (leçon la + utile)** : seed 98000, je n'ai atteint NI Snappawrecka NI Aleph-Null (row 5-7, hors de
  portée de mon roster mêlée) → le carry réparé a deleté ma ligne. **NE JAMAIS out-DPS le carry réparé** : tuer
  Aleph-Null (la source de repair) OU Snappawrecka early/au range ; les deux sont softs (~7-9k, non-Resilient).
- **composantes** : repair Aleph-Null = CONFIRMÉ (wiki §3bis) ; **DakkaDakka +2/repair = gameconfig recon, PAS
  Verif-confirmé live ce match** → ne PAS inscrire en §5bis tant que le +2/repair n'est pas observé live (n=1 gameconfig).
- **à valider** : observer live le scaling DakkaDakka (compter les hits avant/après un repair) ; confirmer le cap (16 ?).
- **evidence** : seed 98000 (n=1, gameconfig recon, status=missed).

## H33 — SYNERGIE : Darkstrider markerlight + ranged allié = +728 ranged vs cible marquée — `provisoire` (mécanique markerlight CONFIRMÉE live 70054 ; delta +728 ally-buff toujours non mesuré, n=1)
- **claim (n=1, source gameconfig — composante markerlight PAS Verif-confirmée live → candidate, PAS §5bis)** :
  `StructuralAnalyser` (Darkstrider) markerlight les cibles via ses tirs ranged → les alliés adjacents / T'au à ≤2 hex
  font **+728 ranged** vs cible marquée → feeds le focus de Snappawrecka et du reste du ranged adverse. Buff-engine
  SECONDAIRE après Aleph-Null/Snappawrecka, mais réel.
- **status = MISSED** : seed 98000, jamais tué Darkstrider (resté back r2, a aidé à deleter ma ligne). Kill au RANGED
  (Infiltrate = pas catchable par mon Overwatch) ; priorité après le carry+repair.
- **composantes** : markerlight +728 = gameconfig recon, PAS Verif-confirmé live ce match → candidate.
- **à valider** : observer live le +728 sur une cible marquée (delta dmg avant/après markerlight).
- **evidence** : seed 98000 (n=1, gameconfig recon, status=missed). Lié : §1 Markerlight (déjà inscrit comme effet
  négatif cleansable) ; ici cas spécifique du buff-engine T'au.
- **seed 70056** (INCONCLUSIVE — le +728 toujours NON mesuré live, MAIS la NUANCE engine-INERTE confirmée n+1 : Darkstrider
  était le SEUL ranged d'une équipe 4-melee (Atlacoya-enemy/Ragnar/Tanksmasha/Kut) → AUCUN 2ᵉ T'au RANGED bénéficiaire du
  markerlight → l'engine est self-fed = STRUCTURELLEMENT INERTE pour CE roster adverse. Même famille que l'engine-inerte-sans-
  bénéficiaire (H02 nuance 70002/70051 : un amplificateur ne vaut que s'il a une cible/bénéficiaire valide). DOCTRINE : au recon,
  compter les bénéficiaires RANGED côté adverse avant de craindre un markerlight-engine ; s'il est le seul ranged, demote la
  carte high→low et traite-le en corps soft (tué dans le dive ici). Le +728 delta reste à mesurer live sur un matchup où
  Darkstrider a ≥1 ranged ally — la composante numérique demeure candidate, mais la règle d'inertie est désormais n=2 distinct
  (98000 missed + 70056 inert).
- **seed 70054 (CONFIRM la MÉCANIQUE markerlight live ; +728 ally-delta toujours non mesuré)** : 1ʳᵉ fois que Darkstrider
  était À MOI et ACTIF (les 2 occurrences précédentes côté ennemi/inerte) → vérifié live que chaque tir ranged pose un
  **Markerlight** (Effect_Id 188/208, RemainingTurns=3) + `SuppressiveFire` Pinned (−1 move, 2 turns) sur la cible. Les
  hits PROPRES de Darkstrider ont été ma TOP source single-cast tout le combat (7476 sur Thoread, 4559 plan sur Tyrant
  Guard) = empilement markerlight-self (clause T'au-à-≤2-hex couvre Darkstrider lui-même) × `RangedSpecialist` × buffs.
  ⚠ Le +728 spécifique aux ALLIÉS RANGED vs cible marquée reste NON ISOLÉ numériquement (mes autres ranged ont focus la
  même cible mais le delta exact +728 n'a pas été mesuré avant/après markerlight) → la mécanique markerlight + Pinned est
  désormais CONFIRMÉE live (n=1 actif), mais la composante numérique du buff allié demeure candidate (toujours à mesurer
  par un delta dmg ally avant/après mark sur un matchup où ≥2 de mes ranged tapent une cible marquée). Confirme aussi
  l'usage : ORDONNER Darkstrider EN PREMIER dans chaque focus (poser le markerlight + Pinned avant que les alliés tirent).

## H34 — Grot HP (Snotflogga SquigHound/GetEmRuntz) scale par rareté ; le tooltip 4802 = base avant multiplicateur — `provisoire` (pour:1 contre:0)
- **claim (plausible, n=1, recoupé Verif vs gameconfig)** : les Grots invoqués par Snotflogga (orksRuntherd) `SquigHound`/
  `GetEmRuntz` scalent en PV via `abilityStatMultiplierPct` de Snotflogga (`summonHp` listé dans `variablesAffectedByRarityBonus`)
  → Rare max 6★ = ×1.40 = **6723 PV**, Epic 6★ = ×1.60 = **7683 PV** ; le tooltip i2 « 4802 Health » est la valeur RAW
  niveau-65 AVANT multiplicateur de rareté. Vécu seed 98001 : Grots summonés ~**7312 PV** (entre les deux tiers, n'égale
  aucun step propre — Epic sub-max level ou approximation de mesure) → confirme que la PV in-game **excède** le tooltip,
  mécaniquement attendu. Les Grots **auto-attaquent immédiatement au spawn** ET au début de chacun de leurs tours (trait
  Summon) → chip gratuit chaque tour, self-sustaining body+chip engine.
- **caveat** : la valeur exacte ~7312 N'est PAS dérivable d'un step de rareté propre (entre 6723 et 7683) → le MÉCANISME
  (scaling rareté, base avant multiplicateur, auto-attaque) est confirmé gameconfig mais la valeur live exacte reste runtime.
- **à valider** : observer la PV des Grots à des tiers de rareté/level connus de Snotflogga pour caler le multiplicateur exact.
- **doctrine candidate** : ne jamais lire la PV d'un summon depuis le tooltip i2 seul (= base avant rareté) ; recon-on-appearance
  la PV runtime réelle (souvent > tooltip). Lié : §3bis Snotflogga + §5bis (Grot-farm engine).
- **evidence** : seed 98001 (n=1, gameconfig recon, verdict « plausible »).

## H35 — SYNERGIE mienne : Thaddeus SpotterReworked pump le ranged allié proche (+364/+728) = noyau ranged-turret — `provisoire` (pour:0 contre:0, status=MISSED — composantes NON Verif-confirmées)
- **claim (n=1, gameconfig, NON exercé)** : le passif `SpotterReworked` de Thaddeus (astraOrdnance) donnerait +364
  dmg ranged (+728 si arme lourde) aux alliés ranged à ≤2 hex de lui → Thaddeus + Abaddon/Actus forment un **noyau
  ranged-turret** (garder les dealers ranged groupés à ≤2 de l'ancre Thaddeus pour le bonus). Synergie **MIENNE-À-ENCHAÎNER**
  candidate.
- **caveat (inscription)** : les composantes (SpotterReworked +364/+728, portée ≤2) ne sont **PAS** dans les verdicts
  Verif de cette vague (seuls RadBombardment/BasiliskBarrage/Patermine confirmés) → reste **candidate dans hypotheses.md**,
  PAS au wiki §5bis tant que SpotterReworked n'est pas confirmé gameconfig/i2.
- **vécu (status=MISSED)** : seed 70003 — le noyau ne s'est JAMAIS formé : Thaddeus (l'ancre ET le carry) est mort T1
  avant que la turret se forme → leçon = l'ancre/carry fragile doit être protégée pour que le bonus existe (recoupe H03
  propre : le carry ranged reste stationnaire+intouchable).
- **à valider** : recon gameconfig SpotterReworked (valeur exacte + rayon) ; observer le delta dmg sur un dealer ranged
  à ≤2 de Thaddeus vs hors portée.
- **evidence** : seed 70003 (n=1, gameconfig au recon, MISSED — non exercé en jeu).

## H36 — SYNERGIE mienne : Thoread (templAncient) écran mêlée = AstartesBanner (+1 hit mêlée) + UnbreakableDuty (−33% aura r2) — `provisoire` (pour:0 contre:0, status=MISSED — composantes NON Verif-confirmées)
- **claim (n=1, gameconfig, NON exercé)** : Thoread (templAncient) serait un **ancre d'écran mêlée buff/défense** —
  `AstartesBanner` donne +1 hit mêlée (cap 5456) aux alliés à ≤2 hex, et l'actif `UnbreakableDuty` pose une aura −33%
  dmg subi (r2) sur la grappe → conçu pour être le front durable d'un cluster serré (protège les fragiles/le carry
  derrière). Synergie **MIENNE-À-ENCHAÎNER** candidate (caster UnbreakableDuty T1 sur la grappe pour émousser un focus).
- **caveat (inscription)** : composantes (AstartesBanner +1 hit, UnbreakableDuty −33%/r2) **PAS** dans les verdicts Verif
  de cette vague → reste **candidate dans hypotheses.md**, PAS au wiki §5bis tant que non confirmées gameconfig/i2.
- **vécu (status=MISSED)** : seed 70003 — units tenues ÉPARSES, pas clusterisées serré autour de Thoread ; l'aura
  UnbreakableDuty −33% JAMAIS cast pour protéger Thaddeus/Nicodemus → le ~18k focus a deleté carry+healer. Leçon : contre
  un focus ranged, caster l'aura défensive T1 sur la grappe peut émousser la salve (recoupe H03 propre + « les engines
  un rang derrière l'écran »).
- **à valider** : recon gameconfig AstartesBanner/UnbreakableDuty (valeurs + rayon + durée) ; tester en jeu si l'aura
  −33% cast T1 réduit mesurablement le focus subi par la grappe.
- **evidence** : seed 70003 (n=1, gameconfig au recon, MISSED — non exercé en jeu).

## H37 — Abraxas MasterOfTheTutelaries : zéro hex libre adjacent au cast → résout ok=True mais NO summon (mutated=False), cascade Screamer jamais armée — `RÉFUTÉE` (pour:1 contre:1, le free-hex gating est faux ; cause réelle = quirk TOOL/ENGINE)
- **claim INITIAL (RÉFUTÉ)** : `MasterOfTheTutelaries` summon un Pink Horror sur **un hex LIBRE adjacent à
  Abraxas** (cf. §2 wiki) ; si **tous** les hexes adjacents sont occupés/hors-board, l'ability résout (ok=True,
  `User_UseAbility`) mais aucun Pink Horror ne spawn (`mutated=False`) — la cascade Screamer reste non amorcée.
- **RÉFUTATION (seed 70009, n+1 contrôlé)** : cast à (2,1) avec **PLUSIEURS hexes adjacents LIBRES confirmés**
  ((1,1)/(3,1)/(2,0)/etc) → toujours **ok=True, mutated=False, SEULEMENT un event `User_UseAbility`, AUCUN
  `Ability_Summon`, AUCUN Pink Horror spawné, action NON consommée** (Abraxas resté à activer). MÊME échec qu'en
  seed 70002 mais maintenant avec un free-hex VÉRIFIÉ → l'hypothèse « zéro-hex-libre cause le no-summon silencieux »
  est **RÉFUTÉE** : le free-hex n'a aucune incidence. La règle gameconfig/i2 (« Summon a Pink Horror on a free hex
  adjacent to Abraxas ») est **inconditionnelle au-delà du free-hex** → per règle, un Pink Horror DEVRAIT spawn.
- **CAUSE RÉELLE (verdict Verif = plausible)** : le no-summon est un **quirk TOOL/ENGINE** — la pipeline applyAction
  ne déclenche PAS le sous-système de summon de MasterOfTheTutelaries, indépendamment de l'occupation du board, et
  ne surface PAS l'échec au caller (`ok=True` trompeur, action non consommée). C'est un **TOOLFEEDBACK** (cf.
  docs/rl/toolfeedback.md) : tout le wincon Psychic-snowball (Pink Horror → Screamers via dégât Psychic → WeaverOfFate
  MAX-dmg si 3+ cibles Psychic) reste **non amorçable via applyAction** tant que ce n'est pas corrigé.
- **doctrine candidate (RÉVISÉE)** : NE PAS dépenser l'action d'Abraxas sur MasterOfTheTutelaries en attendant un
  corps/cascade — utiliser sa normale Psychic r2 à la place. Le « vérifier un free-hex avant cast » est INUTILE (le
  free-hex n'est pas le gate) → la vraie correction est côté tool (surfacer le no-summon / fixer la pipeline).
- **à valider** : root-cause côté engine/harness (pourquoi le summon-subsystem n'est pas appelé par applyAction) ;
  si fixé, re-tester que le Pink Horror spawn et que la cascade s'arme.
- **evidence** : seed 70002 (n=1, observé live) + **seed 70009 (n+1 contrôlé, free-hex confirmé → toujours no-summon
  = RÉFUTE le gate free-hex ; verdict Verif=plausible sur la cause tool/engine)** + **seed 70006 (INCONCLUSIVE, COHÉRENT
  avec la réfutation — ici Abraxas-ENNEMI a SUMMON : u199 est apparu (immédiatement tué par mon Guardsman) → un summon a
  bien résolu ⇒ la condition « zéro hex libre » n'était PAS remplie, et le no-summon est intermittent/contextuel (l'IA
  native déclenche bien le summon-subsystem, contraste avec ma pipeline applyAction côté MIEN). Ni le free-hex gating
  (déjà réfuté) ni le no-summon ne sont une RÈGLE de jeu ; la cascade Screamer n'a jamais armé car l'IA n'a jamais eu
  3+ de mes units prenant du dégât Psychic → WeaverOfFate jamais déclenché).

## H38 — DarkTalonStrike (Azrael) : applique Pinned (move-1, 2 rounds) sur tous les touchés + once-per-battle — `provisoire` (pour:1 contre:0, verdict Verif=plausible)
- **CONFIRMÉ séparément (déjà au wiki §3 Azrael)** : `DarkTalonStrike` = **1× DirectDamage Pierce100** sur la
  cible (bypass armure ET TerminatorArmour, Direct exclu de la réduction) + **6× Bolter sur TOUS les ennemis en
  ligne droite ininterrompue depuis la cible** ; tous les touchés deviennent **Suppressed** (i2-confirmé). Ces
  faits sont inscrits.
- **claim HYPOTHÈSE (n=1, NON dans l'i2 de l'ability)** : (a) tous les ennemis touchés reçoivent AUSSI **Pinned
  (move-1, durée 2 rounds)** en plus du Suppressed ; (b) l'ability est **once-per-battle** (passe à [indispo]
  après un usage et ne se rafraîchit jamais — cf. set H13). Vécu seed 70001 : Mataneo 7153→2029 + leur Dante
  splash 1189, les DEUX Pinned + Suppressed ; DarkTalonStrike resté [indispo] le reste du combat.
- **caveat (gameconfig/i2)** : le texte i2 de DarkTalonStrike mentionne le Suppressed mais **pas le Pinned**
  (l'effet Pinned existe dans le moteur mais aucune source i2 ne le lie à cette ability) ; le statut
  once-per-battle n'est pas non plus explicite dans gameconfig (aucun champ cooldown/munitions surfacé). Les
  deux = observation live n=1 → ne PAS inscrire au wiki tant que non re-observé.
- **doctrine candidate** : si confirmé, DarkTalonStrike = à la fois un chunk Direct-bypass ET un **lock
  positionnel** (Pinned −move) sur 2 deep-strikers alignés → l'aimer pour que la ligne Bolter passe par un 2ᵉ
  ennemi, et le réserver pour le swing décisif (once-per-battle, ne pas l'alpha-dump).
- **à valider** : re-observer un cast → le Pinned est-il systématique sur tous les touchés ? l'ability refresh-t-elle
  jamais (cooldown) ou reste-t-elle [indispo] (once-per-battle, conforte le set H13) ?
- **evidence** : seed 70001 (n=1, observé live, verdict Verif=plausible).

## H39 — SummaryExecution (Yarrick passif) : aura de dmg source-anchored (strip à la mort de Yarrick) — `provisoire` (pour:2 contre:0, verdict Verif=plausible)
- **claim** : le passif `SummaryExecution` de Yarrick (« Friendly units with Battle Fatigue GAIN +291 Damage »,
  effet `SummaryExecution_BaseEffect` = Attack_Modification sur les Guardsmen Battle-Fatigued) est **source-anchored**
  = continu-aura inhérent au porteur vivant → **tuer Yarrick le STRIP immédiatement** des alliés bénéficiaires (les
  Guardsmen perdent leur bonus de dmg). Cohérent avec la sémantique d'aura continue (i2 au présent « gain ») et avec
  H07 (KustomForceField source-anchored confirmé).
- **caveat (verdict Verif = plausible, PAS confirmed)** : l'i2 de SummaryExecution **n'a AUCUNE clause explicite
  de death-revoke** (le buff retiré à la mort est cohérent avec une aura mais non écrit dans le texte de règle) →
  comportement in-engine observé, pas garanti par gameconfig/i2. Reste **candidate** (PAS de fait dur au wiki au-delà
  du « probable / à confirmer » déjà noté §3bis Yarrick).
- **vécu** : seed 95002 (n=1, observé live : `SummaryExecution_BaseEffect` disparu à la mort de Yarrick) ;
  **seed 70007** (n+1, observé live : à la mort de Yarrick, le buff Attack_Modification stripé IMMÉDIATEMENT des DEUX
  Cadian Guardsmen u143/u148 → 0). 2 matchups distincts mais Verif maintient « plausible » faute de clause i2.
- **doctrine candidate** : si promu, tuer Yarrick = double dividende (coupe le summon-engine SendInTheNextWave ET
  de-buff ses Guardsmen existants) → renforce la priorité de kill sur Yarrick. À PROMOUVOIR vers une affirmation
  ferme §3bis Yarrick (retirer le « à confirmer ») dès qu'une clause i2/gameconfig confirme l'anchor — actuellement
  le caveat « probable » reste correct.
- **à valider** : recon gameconfig/i2 pour une clause d'anchor/death-revoke explicite sur SummaryExecution_BaseEffect ;
  sinon laisser en candidate malgré n=2 (la règle d'inscription exige non-dérivable + confirmé, pas seulement répété).
- **evidence** : seed 95002 + seed 70007 (n=2 distincts, observés live, verdict Verif=plausible).

## H40 — Le move-guard 2-ply est AVEUGLE au focus d'un fragile forward (déjà déployé OU avancé sur verdict « propre ») — `confirmée` (pour:4 contre:0, 4 matchups DISTINCTS) → À PROMOUVOIR
- **claim** : le `move-guard` (`--climb`/`--auto`, simulation 2-ply du harness oracle) score la SÉCURITÉ d'un PLAN DE
  MOVE (hold ou avance) sur ~2 plis — mais quand un fragile (carry/healer) est **DÉJÀ déployé forward** (hors rows 0-1)
  AU MOMENT de l'évaluation, le verdict « approche propre » (NET positif, 0 pertes) **ne compte PAS la probabilité qu'il
  soit focus-killé au tour adverse suivant** : le NET simulé sous-estime le risque réel d'un hold passif. Le move-guard
  n'est PAS une ability/trait du jeu (introuvable en gameconfig comme `MoveGuard`/`Guard`) = pur concept du harness oracle.
- **caveat (verdict Verif = plausible, PAS confirmed)** : gameconfig ne peut ni confirmer ni infirmer la politique de
  focus de l'IA native (= comportement harness, non-dérivable de l'i2). Cohérent avec le blind-spot DÉJÀ documenté en
  70003 (move-guard « propre » à longue portée aveugle au focus de contact du 2ᵉ tour) et 70007 (aveugle à un board-flip
  summon-engine) — H40 est une **3ᵉ FORME** du même angle mort : le focus d'un fragile DÉJÀ forward au déploiement.
- **vécu** : seed 70005 (n=1, observé live : Lucien bloodDeathCompany carry autonome 9035 Resilient, DÉJÀ déployé forward
  à (3,5) — le build placeholder affichait mes units rows 0-1, masquant le vrai déploiement mid-board — move-guard verdict
  « approche propre » NET +0.20 sur un hold-all-finish → HOLD → 1er tour IA réel : Aesoth VexillaMagnifica 2687 + Volk
  FrenziedFiring ~6300 → Lucien Resilient floored à 1 → Poxwalker DoT 1 = KILL T1, démarrage 4v5 = la loss).
- **doctrine candidate (déjà reflétée dans doctrine-learned §7/H03 pour les formes 70003/70007)** : ne PAS trust un
  verdict move-guard « propre » comme feu vert ; **vérifier la rangée de déploiement RÉELLE** (le placeholder rows 0-1 est
  trompeur, cf. caveat 70003) et **retraiter le carry/fragile forward vers row 1-2 par DÉFAUT** à mon 1er tour, plutôt que
  de hold sur la foi d'une position « safe » affichée. Reste candidate (n=1 sur cette forme spécifique « déjà forward au
  déploiement » ; les formes longue-portée 70003 + board-flip 70007 sont déjà inscrites doctrine-learned §7).
- **à valider** : prochain match où un fragile est déployé forward → le move-guard « propre » prédit-il à nouveau une
  fausse sécurité ? (corrélation fragile-forward + verdict propre + focus-kill T1). Vérifier aussi côté infra si le
  placeholder rows 0-1 peut être réconcilié avec la rangée de déploiement réelle AVANT l'évaluation du guard.
- **evidence** : seed 70005 (n=1, observé live, verdict Verif=plausible) ; **seed 70050** (CONFIRM n+1, 2ᵉ matchup
  DISTINCT — verdict Verif=plausible : move-guard `--climb` T1 a donné un verdict « propre » NET **+0.34 FOCUS-FIRST**
  (0 perte, projetant Shadowsun −34%) sur une AVANCE de mes fragiles (Neurothrope mon SEUL reach-tool 8533 no-Resilient
  → (1,5) + Aun'Shi buff-engine → (2,5)) ; le 2-ply simulé est AVEUGLE au contact réel : tour ennemi = Shadowsun
  (move4 Flying + ExemplarOfTheKauyon teleport) a focus-killé Neurothrope depuis la backline (8533→0) + Isaak
  CultDemagogue a board-flip 5v5→5v14 + Typhus PlagueWind + Judh HeroicFusillade = **34887 dmg / 4 units en UN tour
  enemy** → loss structurelle 4v14. CETTE forme (avance de fragile sur verdict « propre ») est la MÊME que 70003
  (longue portée) + une variante de 70005 (déjà forward) : le dénominateur commun = un verdict « propre » du guard
  2-ply n'est PAS un feu vert pour exposer un fragile vs un profil Flying-teleport / board-flip dont le focus de
  contact atterrit hors de la fenêtre 2-ply. n=2 matchups DISTINCTS → confirmée).
- **evidence (suite)** : **seed 70052** (CONFIRM n+1, 3ᵉ matchup DISTINCT, FORME « hold » — verdict Verif=plausible :
  les verdicts move-guard du HOLD (T1 NET +0.00, T2 NET −0.86 = « hold propre, 0 perte ») ont SOUS-PRICÉ le focus
  all-ranged RETARDÉ qui a atterri une fois l'ennemi fermé : au tour du chip (T2→enemy), le cluster all-ranged a
  focus-killé Sibyll (2555→0, fragile 5522 no-Resilient) + Winged Prime (9430→0, engine no-Resilient) + chunké tous
  mes survivants en UN tour. Le 2-ply n'a NI modélisé la politique de focus de l'IA NI le 2ᵉ-ply board-flip d'Abraxas
  (MasterOfTheTutelaries). NOUVELLE FORME du blind-spot : ici ce n'est ni une avance « propre » (70003/70050) ni un
  fragile déjà forward (70005) — c'est un HOLD dont le verdict « propre/neutre » sous-estime le focus all-ranged qui
  grandit en reach round après round et délete les fragiles même restés shallow (row 0-1). DOCTRINE renforcée : un
  verdict guard « propre/neutre » sur un HOLD n'est PAS une garantie de survie vs un all-ranged focus-fire cluster qui
  étend sa portée — par défaut, retraiter/écranter les fragiles no-Resilient au CENTRE derrière les bricks, ou flagger
  la loss structurelle si aucune tuile safe n'existe. n=3 matchups DISTINCTS → confirmée.)
- **evidence (suite)** : **seed 70054** (CONFIRM n+1, 4ᵉ matchup DISTINCT, FORME « avance FOCUS-FIRST vs mur all-melee
  qui ferme la distance au 2ᵉ tour » — verdict Verif=plausible : le move-guard T3 a verdicté NET **+2 FOCUS-FIRST** sur
  une avance de mes 3 ranged à row 3 pour tuer Yazaghor isolé — mais il est 2-ply-BLIND au focus de CONTACT RETARDÉ : le
  mur adverse 100% mêlée a fermé la distance et focus-killé mon Archimatos (Psychic dealer fragile) au tour enemy-T4. Le
  guard a price le tour T3 (le kill de Yazaghor) mais PAS le tour enemy-T4 où le mur, déjà en mouvement, atteint et focus
  les fragiles que j'ai présentés à row 3. MÊME dénominateur que 70003 [contact-focus du 2ᵉ tour] mais sur une AVANCE
  FOCUS-FIRST « +2 » trompeuse vs un mur mêlée en approche — le verdict positif FOCUS-FIRST n'est PAS un feu vert quand
  l'avance présente des fragiles dans le reach d'un mur all-melee qui closera au tour suivant. ⚠ AGGRAVÉ par l'INFRA :
  plus tard ce même guard a timed out (Deathleaper spec) puis desynced (NET −22.58 à un 9v1 trivialement gagné) →
  fiabilité dégradée tout le match. n=4 matchups DISTINCTS → confirmée.)
- **evidence (suite)** : **seed 70059** (CONFIRM-PAR-CONTRASTE n+1, 5ᵉ matchup DISTINCT, FORME « le guard A VU la perte et l'a
  PRICÉE correctement » — verdict Verif=plausible : CONTRE-EXEMPLE PARTIEL du blind-spot — T3 le move-guard a flaggé worst=Kharn
  MORT (mon meilleur carry committé forward à (4,2) pour K! le Tyrant Guard) ET a quand même rated le plan BEST (NET +2.58, aucun
  pull-back n'améliore) ; l'enemy-turn a CONFIRMÉ exactement la prédiction (Maladus FlailSwing a focus-killé Kharn). Contrairement
  aux 5 formes ci-dessous (70003/70005/70050/70052/70054) où le guard était AVEUGLE au focus-kill, ici le guard 2-ply A
  correctement MODÉLISÉ le focus-kill du carry forward (la cible et la perte étaient dans la fenêtre 2-ply car le contact était
  IMMÉDIAT, pas retardé d'un tour). NUANCE DISTINCTE : le blind-spot de H40 est spécifiquement le focus de contact RETARDÉ (2ᵉ
  tour IA, hors fenêtre 2-ply) ou board-flip ; quand le focus-kill atterrit DANS la fenêtre 2-ply (contact immédiat), le guard le
  voit et le price juste — MAIS il peut alors RECOMMANDER le sacrifice du carry si le NET de board-value est positif (+2.58 ici
  car tuer TG+Ragnar valait plus que Kharn). LEÇON OVERRIDE-MANUEL : un verdict guard « NET positif » qui price explicitement
  worst=MON-carry-MORT n'est PAS un feu vert à suivre aveuglément — le board-value NET peut sur-évaluer un anvil-kill non-engine
  vs la valeur stratégique d'un carry préservé (cf. mistakes 70059 : laisser TG vivant + tuer l'engine Ragnar au range aurait
  préservé Kharn). Le guard optimise le NET 2-ply local, PAS la préservation des pièces clés à long terme. n=4 blind-spot +
  1 contre-exemple « guard exact mais recommande un trade de carry sous-optimal » → la doctrine H40 s'élargit : se méfier du
  guard « NET positif » AUSSI quand il price correctement la perte mais recommande de sacrifier une pièce clé.)
- **NUANCE CONFIRMÉE (n+3)** : le blind-spot couvre désormais 5 formes — (a) avance « propre » longue portée (70003),
  (b) fragile déjà déployé forward au déploiement (70005), (c) avance « propre » d'un fragile dans le reach d'un
  Flying-teleport/board-flip (70050), (d) **HOLD au verdict « propre/neutre » sous-estimant le focus all-ranged retardé
  qui étend sa portée round après round et délete les fragiles même restés shallow (70052)**, (e) **avance FOCUS-FIRST
  « +N » trompeuse présentant des fragiles dans le reach d'un mur ALL-MELEE qui ferme la distance au 2ᵉ tour IA et les
  focus-kill (70054 : guard NET+2 FOCUS-FIRST → Archimatos focus-killé enemy-T4)**. Dans tous les cas le guard ne
  modélise NI la politique de focus de l'IA NI le 2ᵉ-ply (board-flip, extension de portée all-ranged, contact-dive du
  mur mêlée en approche). DOCTRINE : ne JAMAIS trust un verdict guard « propre/neutre/FOCUS-FIRST » pour une avance OU
  un HOLD de fragile vs un roster board-flip (Isaak) / Flying-teleport (Shadowsun) / all-ranged focus-fire (Re'vas+
  Abraxas+Certus+Eldryon+Adamatar) / mur ALL-MELEE en approche — retraiter/écranter les fragiles no-Resilient au CENTRE
  derrière les bricks par DÉFAUT (tuer un fragile isolé avec des corps DURABLES, pas en avançant les fragiles), ou
  flagger la loss structurelle si aucune tuile safe n'existe.

## H41 — Summons auto-agissent ; le piloter manuellement échoue (Ork Boy melee-only + id concret + plan-tile trompeur) — `provisoire` (pour:1 contre:0, verdict Verif=plausible)
- **claim (n=1, source observée live + gameconfig — quirk tool/engine, candidate)** : un summon dont le trait dit « Moves and
  attacks automatically at the beginning of its turn » (ex. orksOrkBoys via Gulgortz Waaagh) **auto-agit au start de son
  tour** → l'oracle ne devrait PAS queue manuellement ses actions. Quand on tente de le piloter à la main, plusieurs échecs
  `mutated=False` apparaissent : (a) la **normale d'Ork Boy est melee-only** (profil Physical, adjacence requise → rejet si
  non-adjacent) ; (b) l'auto-resolve a fallback sur **Stikkbomb (id1051, range 2, IndirectFire)** qui DEVRAIT porter à dist-2
  mais a aussi échoué → l'id concret passé à applyAction doit matcher l'`ActiveAbilityType` RÉEL de l'unité, pas une constante
  hardcodée (cf. project_ability_normal_attack_concrete) ; (c) le **plan-tile de decisionView est trompeur** — il listait le
  hex COURANT du summon vs une cible dist-2 → vérifier la légalité du move/adjacence AVANT l'attaque.
- **caveat (verdict Verif = plausible, PAS confirmed)** : gameconfig confirme que la normale Ork Boy est melee (adjacence) et
  que Stikkbomb est range 2 IndirectFire → l'échec à dist-2 sur Stikkbomb est **harness-side** (mauvais id concret ou gate de
  target-state), PAS une règle de jeu ; le trait « auto-act » signifie que l'oracle ne devrait pas driver le summon du tout.
- **doctrine candidate** : ne PAS queue manuellement les actions d'un summon « auto-act-at-turn-start » ; si on doit le faire,
  passer l'`ActiveAbilityType` concret de l'unité (pas une constante) et VÉRIFIER la légalité du move (glyph/aiMovableTiles)
  avant l'attaque, sachant que le plan-tile peut afficher le hex courant plutôt que la destination. Reste candidate (n=1).
- **à valider** : observer sur d'autres summons auto-act (Bloodletters, Death Riders, Grots) si le pilotage manuel échoue
  pareil ; confirmer côté infra que le no-summon/no-action n'est pas surfacé au caller (lié au quirk Abraxas H37/toolfeedback).
- **evidence** : seed 70008 (n=1, observé live + gameconfig, verdict Verif=plausible).

## H42 — Hollan TwistedScience s'auto-applique à SON Aberrant Hypermorph summon au spawn — `provisoire` (pour:1 contre:0, verdict Verif=plausible)
- **claim (n=1, observé live, candidate)** : à l'apparition de l'Aberrant Hypermorph summonné par Hollan (genesBiophagus),
  le passif `TwistedScience` semble s'auto-appliquer au summon (effets `TwistedScience_ExtraHp`/`_ExtraDmg` présents au
  spawn dans decisionView.effects). HP live observée : **5456 (base gameconfig) → 10469 au spawn** (+~5013), et l'Aberrant
  a survécu le tour ennemi à 9813.
- **caveat (verdict Verif = plausible, PAS confirmed)** : l'i2 indique que TwistedScience se déclenche quand Hollan *soigne*
  une unité (+2183 maxHP, +364 dmg pour les GSC) — le trigger est un HEAL, **PAS un summon**. Le texte i2 n'affirme PAS
  explicitement que le summon reçoit TwistedScience au spawn. La hausse observée (5456→10469) DÉPASSE +2183 seul → cohérent
  avec un cumul scaling niveau/rareté du base de l'Aberrant ET du bonus TwistedScience. Le mécanisme discret (summon spawn =
  heal implicite déclenchant TwistedScience) n'est PAS dérivable de gameconfig/i2 — observé in-game seulement.
- **note wiki** : le wiki §3bis Hollan + §5bis (TwistedScience) affirme DÉJÀ « tout allié healé par Hollan, summons INCLUS »
  (i2 : « Units healed by Hollan … immediately gain 2183 Health ») — H42 raffine ce point sur le canal SPÉCIFIQUE « heal
  implicite au spawn », à confirmer n>1.
- **à valider** : observer sur d'autres spawns d'Aberrant (ou un autre summon de Hollan) si les effets TwistedScience_*
  apparaissent au spawn SANS heal explicite ; recouper le delta HP exact vs base+2183.
- **evidence** : seed 70050 (n=1, observé live, verdict Verif=plausible). Voir aussi seed 98001 (Aberrant ressuscité
  5456→10469, déjà au wiki §5bis comme « Hollan heal un summon sur revive le pompe aussi »).

## H43 — Les summons (Cadian Guardsman, etc.) spawnent à une HP scalée du rang/rareté du summoner, PAS la valeur tooltip — `provisoire` (pour:2 contre:0, verdict Verif=plausible ; n=2 matchups distincts mais le SENS du scaling varie [down 70050, up 70054])
- **claim (n=1, observé live, candidate)** : le Cadian Guardsman summonné par Creed (`SupremeCommander`) a spawné à
  **1376 HP** alors que le tooltip gameconfig hard-code **2910 Health** → la HP de summon scale (ici DOWN) avec le rang/
  rareté du summoner au moment du combat, et le tooltip n'est PAS fiable comme valeur runtime.
- **caveat (verdict Verif = plausible, PAS confirmed)** : gameconfig SupremeCommander hard-code « 2910 Health » sans
  variable de scaling dans les params de l'ability ; le trait Summon n'ajoute aucune règle de scaling HP. La valeur live
  (1376 < 2910) est cohérente avec le pattern connu « les stats de summon dérivent de la progression rang/rareté du
  summoner », mais la formule n'est PAS exposée dans gameconfig/i2 — comportement émergent, non documenté. Aucune
  contradiction trouvée.
- **doctrine candidate** : toujours lire la HP runtime du summon dans decisionView/observeBattle, JAMAIS le tooltip de
  l'ability. (Recoupe le pattern déjà inscrit pour l'Aberrant Hollan en §5bis « recon-on-appearance la PV runtime, jamais
  le tooltip » — H43 généralise au-delà des summons pumpés.)
- **à valider** : observer d'autres summons (Death Riders, Neophytes, Grots, Bloodletters) → la HP live diverge-t-elle
  systématiquement du tooltip selon le rang du summoner ?
- **seed 70054 (CONFIRM n+1, 2ᵉ matchup distinct, SENS = UP cette fois)** : DEUX summons live AU-DESSUS du tooltip —
  (1) **Blue Horror** (Archimatos `Possession`, sur kill RANGED) : runtime **MaxHealth 3888 / Attack 2194** vs tooltip i2
  **2619 / 1310** (~+48 à +67%) ; (2) **Neophyte Hybrid** (Isaak `CultDemagogue`) : runtime **~2992 PV** vs base
  gameconfig **2183** (~+37%). En 70050 le Cadian Guardsman scalait DOWN (1376 < 2910) ; ici les deux summons scalent UP →
  le SENS dépend du rang/rareté du summoner, mais le PRINCIPE « ne jamais lire la HP d'un summon depuis le tooltip i2,
  recon-on-appearance la valeur runtime » est confirmé sur 2 matchups distincts (4 summons : Cadian, Blue Horror,
  Neophyte). Verdict Verif sur le Blue Horror = **plausible** (le scaling est un produit émergent niveau/rareté/buffs au
  spawn, AUCUNE règle discrète exposée en gameconfig/i2 — cohérent avec la famille H43 mais non prouvé comme règle).
- **candidat (Verif=plausible, seed 70054) — Blue Horror scaling spécifique** : Blue Horror (Possession, kill RANGED
  d'Archimatos) — stats live > tooltip i2 (observé 3888 HP / 2194 Atk vs base 2619 / 1310) ; les stats de summon
  semblent scaler avec le summoner ou la progression de partie, cohérent avec la famille H43. AUCUNE règle de scaling
  explicite en gameconfig/i2 → traiter comme émergent (n=1 sur ce summon précis). NON inscrit au wiki (verdict plausible,
  pas confirmed) — le wiki §3bis Blue Horror garde la base 2619/1310 + note « recon-on-appearance la PV runtime ».
- **evidence** : seed 70050 (n=1, Cadian scale DOWN, verdict Verif=plausible) ; **seed 70054** (n+1, Blue Horror +
  Neophyte scale UP, verdict Verif=plausible). **n=2 matchups distincts.**

## H44 — ToughToKill (astraDreir) : la regen passive début-de-tour est BLOQUÉE par un heal-block (FuryOfTheAncients) — `provisoire` (pour:1 contre:0, verdict Verif=plausible)
- **claim (n=1, observé live, candidate)** : la régénération 2183 HP/début-de-tour de `ToughToKill` (Dreir) semble
  SUPPRIMÉE par un heal-block (Mephiston `FuryOfTheAncients`, 2 rounds) → un Dreir floored par Resilient à 114 HP ne
  remonte PAS tant que le heal-block dure → confirme que ToughToKill est un « heal » bloquable, pas une regen passive
  immunisée.
- **caveat (verdict Verif = plausible, PAS confirmed)** : ToughToKill dit « regenerates 2183 Health » (mot =
  « regenerates », pas « heals ») ; FuryOfTheAncients dit « cannot be revived, healed, repaired, nor otherwise restore
  Health » — la clause catch-all « otherwise restore Health » englobe SÉMANTIQUEMENT les régénérations passives, et
  aucune immunité au heal-block n'est mentionnée dans le texte i2 de ToughToKill. MAIS gameconfig ne classifie pas
  explicitement ToughToKill comme « heal » → la suppression effective dépend de l'implémentation moteur HealBlock vs
  RestoreHealth interne. Non contredit, non confirmé explicitement.
- **doctrine candidate** : si confirmé, un brick ToughToKill (ou tout regen/healer-dépendant) face à un heal-block
  move-rider perd sa durabilité active → ordre d'application = poser le heal-block AVANT de floorer la cible ; côté
  PROPRE, tenir un tel brick HORS de la chaîne d'adjacence du Psychic move-rider, ou accepter qu'il devienne un corps
  à usage unique.
- **à valider** : observer un autre heal-block (autre source) sur une autre regen passive (ToughToKill, LivingMetal,
  autres self-regen) → la regen est-elle systématiquement supprimée pendant la durée du heal-block ?
- **evidence** : seed 70051 (n=1, observé live + gameconfig, verdict Verif=plausible).

## H45 — Un cluster ALL-RANGED focus-fire delete un Héros fragile (sans passif défensif) en UN tour, même resté shallow row 0-1 — `provisoire` (pour:1 contre:0, verdict Verif=plausible)
- **claim (n=1, observé live, candidate)** : une équipe adverse majoritairement/entièrement RANGED (r2/r3) qui avance
  ~3-4 rows/tour finit, une fois en portée, par **focus-killer un Héros fragile (no Resilient, pas de passif d'auto-défense)
  en UN seul tour ennemi**, et **tenir mes units à row 0-1 ne suffit PAS** une fois que le cluster a fermé la distance —
  sa portée combinée couvre row 1 (vécu seed 70052 : Sibyll 2555→0 [Common, no self-defense] + Winged Prime 9430→0
  [pas de DR passive] + chunk de Nauseous/Snappa/Angrax en un tour, alors que mes units étaient row 0-1).
- **caveat (verdict Verif = plausible, PAS confirmed)** : gameconfig confirme que Sibyll (Common, Nightshroud ne buffe
  que les alliés ADJACENTS, pas elle-même) et Winged Prime (Hero mêlée, aucune DR passive) n'ont AUCUN passif
  d'auto-protection ni armure sur leur profil — la fragilité structurelle est un FAIT KIT. MAIS « focus-fire » n'est
  PAS une mécanique/trait nommé dans gameconfig : c'est un COMPORTEMENT compositionnel (plusieurs ranged tapant la même
  cible dans un tour d'équipe). Les chiffres exacts de deletion (2555→0, 9430→0) sont émergents (rareté × niveau × buffs),
  non vérifiables depuis les stats de base → verdict plausible. Le PRINCIPE structurel (un Héros fragile sans passif
  défensif meurt en un tour d'équipe face à un focus ranged coordonné une fois en portée, quelle que soit la profondeur
  de positionnement) est COHÉRENT avec la kit-truth et avec SKILL §6 (vs focus-fire compo, ne jamais présenter un fragile).
- **doctrine candidate** : vs un roster all-ranged focus-fire, un fragile no-Resilient sans passif défensif n'est PAS
  protégé par la simple profondeur (row 0-1) une fois le cluster fermé → l'écranter au CENTRE derrière les bricks, OU
  flagger la loss structurelle au recon si aucune tuile safe n'existe (cf. H40 forme « hold » 70052, et la nuance
  reach-fail H02). Reste candidate (n=1, chiffres live non vérifiables).
- **à valider** : 2ᵉ occurrence d'un all-ranged focus qui delete un fragile shallow en un tour → promouvoir à wiki §5
  (note de matchup) / SKILL §6. Recouper si un passif défensif (Resilient/DR/high-rarity HP) suffit à survivre le tour.
- **evidence** : seed 70052 (n=1, observé live + gameconfig, verdict Verif=plausible).

## H46 — Contamination tiles (board hazard `Contaminated_Unit`) : DoT StartTurn faction-agnostic (friendly-fire-style) — `provisoire` (pour:1 contre:0, verdict Verif=plausible)
- **claim (n=1, observé live, candidate)** : une source board (hex `Contaminated_Unit`, possiblement issue de
  `RadBombardment` ou d'une aura Nurgle / swamp-hex) inflige des dégâts au **StartTurn** aux unités présentes sur ses
  hexes, **sans distinction de faction** (style friendly-fire) → vécu seed 70055 : au StartTurn final, une source « u6 »
  a tué MON Tjark (1708) ET l'ennemie Atlacoya (4268) en même temps + chunké Deathleaper (4818). C'est un board/DoT
  hazard, PAS une ability d'unité commandable.
- **caveat (verdict Verif = plausible, PAS confirmed)** : gameconfig — `Contaminated_Unit` est un effet moteur SANS
  description i2 et SANS source trait/ability identifiable (le tool ne peut pas confirmer la sémantique StartTurn) ;
  le trait `Contaminated` n'a aucune traitVariable ; le Parasite of Mortrex n'a AUCUNE ability DoT/board dans son kit
  (ItItches + BarbedOvipositor uniquement). Le wiki §3 (Contamination) documente déjà PARTIELLEMENT (tiles posés par
  RadBombardment / aura Nurgle → `Contaminated_Unit` sur les hexes ; unités dedans subissent Toxic/effets selon la
  source ; sémantique exacte = TODO §6). AUCUNE règle i2 discrète ne confirme le trigger StartTurn ni l'aspect
  faction-agnostic → cohérent avec les tiles Contamination existantes mais NON prouvé.
- **à valider** : (1) quel ability/event a POSÉ les tiles dans ce combat (aucun RadBombardment carrier évident côté
  adverse) ; (2) le DoT StartTurn est-il SYSTÉMATIQUE ou conditionnel ; (3) confirmer le caractère faction-agnostic
  (les deux équipes touchées en même temps). 2ᵉ occurrence d'un DoT StartTurn board-hazard frappant les deux camps →
  promouvoir à wiki §3 Contamination (lever le TODO §6 partiel).
- **evidence** : seed 70055 (n=1, observé live ; verdict Verif=plausible — board hazard cohérent avec les tiles
  Contamination, trigger StartTurn + faction-agnostic non corroborés par i2).

## H47 — MkXGravis (Burchard) : Direct ET Psychic bypassent la double-armure (pas seulement Crit) — `provisoire` (pour:1 contre:0, verdict Verif=plausible)
- **claim (candidate)** : le trait `MkXGravis` fait repasser tout dégât entrant par l'Armour une 2ᵉ fois ; le wiki/doctrine
  affirme que **Crit, Direct ET Psychic** bypassent cette double-armure. i2 ne confirme EXPLICITEMENT que l'exception **Crit**
  (« Does not apply to Crits »). Le bypass **Direct** et **Psychic** est **empirique** (vécu : un roster SANS aucun
  Direct/Psychic/Crit a un output réduit vs Burchard, cohérent avec « ces 3 types passent à plein »), mais PAS inscrit dans
  le texte de règle i2.
- **caveat (verdict Verif = plausible, PAS confirmed)** : « DirectDamage » et « Psychic » ne sont pas résolvables comme
  entrées gameconfig autonomes (probablement des propriétés de profil de dégât, non exposées comme traits) → le tool ne peut
  pas confirmer la sémantique bypass. Le claim numérique (12038→1362 vs Burchard) est un produit live émergent (level × rareté
  × buffs : Nauseous −armure aura + Storm of Fire +582 + 6v1) et n'est PAS vérifiable depuis les stats de base. Le RAISONNEMENT
  contextuel (la double-armure est battable sous conditions favorables : debuffs d'armure + supériorité numérique) EST cohérent
  avec la mécanique double-armure.
- **à valider** : (1) un coup **Direct Pierce100** (DoomSiren) ou **Psychic NoBlocking** (Stormcaller/MightFromBelow) sur Burchard
  passe-t-il à plein (single-armour) vs un coup Power/Physical de même profil (double-armour) ? mesurer le delta net live ;
  (2) confirmer que le bypass ne dépend PAS de Pierce mais bien du TYPE de dégât (Direct/Psychic/Crit).
- **evidence** : seed 70060 (n=1, observé live ; verdict Verif=plausible — i2 confirme l'exception Crit, le bypass
  Direct/Psychic reste empirique non corroboré par le texte i2). ⚠ le « ungrindable wall » n'est réel que quand Burchard est le
  DERNIER mur ET la course aux dégâts déjà perdue ; sous debuffs d'armure + supériorité numérique il reste battable (cf. carte
  wiki Burchard + H02 NUANCE 70008/70060).

## H48 — TerminatorArmour : le −75% s'applique au 1er HIT individuel d'un multi-hit (pas à tous les hits du « 1ʳᵉ attaque event ») ; HeavyGravCannon = hard-counter confirmé — `provisoire` (pour:1 contre:0, verdict Verif=plausible)
- **claim (candidate)** : sur un multi-hit d'une SEULE arme contre un porteur de `TerminatorArmour`, la réduction −75%
  semble ne toucher que le **1er HIT individuel** de la volée, les hits suivants tapant à plein — distinct du texte i2
  qui dit « first **attack** » (event), pas « first hit ». Vécu seed 70058 : Sy-gex 4× Physical r3 sur Njal (TermArmour) =
  2534 + 2490 + 1703 → kill clean (le 1er hit aurait été le seul réduit, les suivants full). Le wiki §1 TerminatorArmour
  dit explicitement « un multi-hit d'une SEULE arme = UNE attaque réduite » → ce claim le NUANCE/CONTREDIT (le réel
  observé = seulement le 1er hit réduit, pas toute la volée d'une même arme).
- **HeavyGravCannon (volet CONFIRMÉ, déjà au wiki §1/§3bis Sy-gex)** : `HeavyGravCannon` = +364 dmg flat ET +60% pierce
  ratio vs cibles `MkXGravis`/`TerminatorArmour`/`Mechanical` (i2 confirmé) → un attaquant Mechanical porteur (Sy-gex)
  est un **hard-counter de TerminatorArmour** : +364 plat + ~+60% pierce négocie la valeur du trait même sur le 1er hit
  blunté. Ce volet est déjà inscrit (n'a PAS besoin de validation) ; SEUL le « 1er hit vs 1ʳᵉ attaque event » est candidate.
- **caveat (verdict Verif = plausible, PAS confirmed)** : i2 TermArmour = « first attack each turn deals {pct}% Damage,
  Psychic/Direct excluded » (−75%) → le texte dit « attack » (event), pas « hit » individuel ; la règle discrète « seul
  le 1er hit de la volée d'une MÊME arme est réduit » n'est PAS explicitement corroborée par i2 (n=1 in-game). Cohérent avec
  le précédent en mémoire « Resilient ne survit PAS à un multi-hit » (le jeu évalue certains traits par-hit dans un multi-hit),
  mais le wiki §1 actuel affirme l'INVERSE pour TermArmour (« multi-hit d'une seule arme = UNE attaque réduite ») → à TRANCHER.
- **à valider** : (1) mesurer hit-par-hit un multi-hit d'UNE arme sur un TermArmour pur (sans HeavyGravCannon, pour isoler) :
  le 1er hit seul est-il à −75% et les suivants à plein, OU toute la volée de cette arme est-elle réduite ? (2) re-tester sur
  un multi-hit NON-Mechanical pour exclure que ce soit l'effet HeavyGravCannon (+pierce) qui « débloque » apparemment les hits.
- **evidence** : seed 70058 (n=1, observé live : Sy-gex 4-hit HeavyGravCannon sur Njal TermArmour 2534+2490+1703 → 6727→0 clean
  ; verdict Verif=plausible — HeavyGravCannon hard-counter CONFIRMÉ par i2, mais « 1er hit vs 1ʳᵉ attaque event » non corroboré,
  confondu avec le bonus pierce HeavyGravCannon). ⚠ Njal était STUN (VexillaMagnifica) → AoE déniée, focus propre.

## H49 — SYNERGIE candidate : Thaddeus SpotterReworked (+728 ranged aux alliés Heavy Weapon) + Sy-gex HeavyWeapon — `provisoire` (pour:1 contre:0, composante NON Verif-confirmée → candidate, PAS au wiki)
- **claim (candidate synergie MIENNE-À-ENCHAÎNER)** : Thaddeus `SpotterReworked` donnerait **+728 ranged** aux alliés porteurs
  d'une **Heavy Weapon** quand ils sont à ≤2 hex de Thaddeus → garder Sy-gex (HeavyWeapon) dans 2 hex de Thaddeus amplifie son
  output d'Overwatch/normale (a contribué à tuer Njal + reaction-killer Ulf seed 70058). PLAY : feeder le HeavyWeapon Overwatcher
  (Sy-gex) avec Thaddeus dans la grappe de hold.
- **caveat (pourquoi candidate, PAS wiki)** : `SpotterReworked` (+728, gate ≤2 hex, cible Heavy Weapon) est une donnée gameconfig/
  i2 issue du recon mais **n'a PAS été incluse dans les verdicts Verif de cette vague** → la mécanique composante n'est pas
  Verif-confirmée pour cette synthèse (règle d'inscription §6bis) ; elle n'est pas non plus encore dans la carte wiki Thaddeus
  (§3bis). À INSCRIRE au wiki (Thaddeus §3bis + §5bis Miennes) une fois la valeur +728 / le gate ≤2hex / le filtre Heavy Weapon
  confirmés par gameconfig/i2.
- **à valider** : (1) confirmer +728 (exact) et le gate ≤2 hex sur SpotterReworked via gameconfig ; (2) confirmer que le filtre
  cible est bien « Heavy Weapon keyword » (Sy-gex HeavyWeapon en bénéficie) ; (3) mesurer le delta d'output Sy-gex avec/sans
  Thaddeus à ≤2 hex.
- **evidence** : seed 70058 (n=1, observé live — Sy-gex a tué Njal + reaction-killé Ulf, output cohérent avec un buff actif, mais
  le +728 n'est pas isolé/mesuré ; composante non Verif-confirmée cette vague).

## H50 — Sho'syl MV71SniperDroneSquadAttack (1076) : le drone est un SUMMON PERSISTANT bodyguard (max 3, SaviorProtocols), PAS un meatshield jetable — `provisoire` (pour:1 contre:0, verdict Verif=plausible)
- **claim** : l'attaque normale de Sho'syl (`MV71SniperDroneSquadAttack`, id 1076) summon une **MV71 Sniper Drone** qui (a)
  attaque **immédiatement** pour ~3854-5782 (Attack_Override=4015, au **Damage stat de Sho'syl**, PAS son profil base) DEPUIS
  la tuile courante/shallow — c'est un **burst-on-demand**, PAS le Seeker différé (`SeekerMissileFrequencyLock`) — ET (b)
  reste comme un **summon PERSISTANT** : max 3 drones coexistent (le plus bas-PV évincé au 4ᵉ summon), ~1455 HP (scale au
  niveau/rareté), Flying + Mechanical + **SaviorProtocols (50% chance d'intercepter les coups visant un allié T'au adjacent)**
  = un vrai garde-du-corps, PAS un one-shot meatshield. Markerlight aussi posé sur la cible jusqu'au prochain tour de Sho'syl.
- **caveat (pourquoi plausible, PAS confirmé/wiki)** : le verdict Verif sur cette mécanique = **plausible** — l'immédiateté du
  summon+attaque (vs le Seeker différé), l'usage du Damage stat de Sho'syl, et « PAS un Seeker différé » sont confirmés par
  gameconfig ; MAIS l'observation originale « drone = 1 body puis meurt (free meatshield) » est **CONTREDITE par gameconfig**
  (le drone est persistant max 3 + SaviorProtocols + 1455 HP, pas un sacrifice jetable). Les valeurs numériques (3854-5782,
  Attack_Override=4015) sont live/émergentes (niveau × rareté × buffs) → plausibles mais non base-vérifiables.
- **à valider** : (1) confirmer le cap 3 drones + l'éviction du plus-bas-PV au 4ᵉ summon live ; (2) confirmer SaviorProtocols
  50% intercept en jeu ; (3) confirmer la persistance multi-tour du drone (vs disparition à la fin du tour de Sho'syl).
- **evidence** : seed 70057 (n=1, observé live — drone a délivré ~5924/burst côté ennemi seed 70058 et ~burst immédiat côté
  mien seed 70057 ; persistance/cap/SaviorProtocols = gameconfig, pas isolés live cette vague).
- **→ wiki si confirmé** : §3bis Sho'syl (carte déjà présente — préciser le drone PERSISTANT bodyguard, pas jetable) + §5bis
  (la synergie screen-on-attack Sho'syl-drone + Tan Gi'da Vanguard suppose la persistance du drone).

## H51 — EnvEndBombardment : hard round cap (~round 10) = bombardement board-wide → mutual wipe both teams, winner=None (draw) — `confirmée` (pour:2 contre:0, cross-validé self-play 2 sides — INSCRITE wiki §3quater)
- **claim** : il existe un **hard round cap** (observé ~round 10) où le moteur déclenche `EnvEndBombardment_Incoming` sur
  ~12 tiles (RemainingTurns=1) = un bombardement environnemental board-wide qui **wipe TOUTES les unités des DEUX équipes**
  → `finalStage=Finished`, `alive_by_team={}`, team gagnante=**None**. Conséquence stratégique MAJEURE : une position
  dominante-mais-NON-convertie devient un **timeout no-winner** (PAS un W). Tenir/chiper dans une position gagnée avec un
  round cap est une LOSS — il faut PRESSER pour wipe l'ennemi AVANT le cap.
- **caveat (pourquoi plausible, PAS confirmé/wiki)** : Verif gameconfig confirme que `EnvEndBombardment` ET `RemainingTurns`
  sont des **effets MOTEUR** (`gameconfig.py --effect` : « effet moteur — pas d'ability/trait source ni description i2 ») →
  AUCUN texte i2, AUCUN profil de dégâts queryable. Le préfixe « Env » + le pattern de nom sont cohérents avec un hazard de
  time-limit environnemental, et winner=None sur un wipe simultané est une logique de jeu cohérente, MAIS ni le **round de
  déclenchement exact** (~10 observé n=1), ni le **scope board-wide**, ni l'**issue draw** ne sont explicitement énoncés par
  gameconfig/i2 — comportement engine-only.
- **à valider** : (1) confirmer le round-cap exact (toujours round 10 ? scale avec rank/board ?) ; (2) confirmer que le wipe
  est board-WIDE (toutes tiles peuplées) et non un sous-ensemble ; (3) confirmer que la majorité numérique au moment du cap
  ne donne PAS la victoire (ex. si une équipe a des survivants hors des tiles bombardés). (4) trouver le compteur live à
  tracker (candidat : `Match_AmountOfTurnsStartedByCurrentPlayer`) pour budgéter le clock.
- **evidence** : seed 70061 (n=1 — board dominant 4v2-3, les 2 summon-engines morts T3-T4, mais Actus repair-engine jamais
  fini + Corrodius 12551 Resilient jamais engagé → round ~10 EnvEndBombardment → mutual wipe → team gagnante=None = L).
  **+ seed 80000 (opus run) self-play — CROSS-VALIDÉ LES DEUX SIDES (2ᵉ observation indépendante → confirmée)** : A (theirs) et
  B (mine) rapportent CHACUN le même nuke terminal qui a wipe tout le board (alive_by_team={}, `winner=None`), overkillant même
  Arjac Resilient (final hp=0) ; `rl_duel.py status` post-match = `stage=None alive_by_team={}` team gagnante=None. B menait 1v2
  (Arjac full-HP) au moment du fire → position gagnante NON convertie devenue draw. A & B concordent sur la leçon (close avant le cap).
- **doctrine candidate (PROMUE wiki §3quater)** : dans une position GAGNÉE (engines adverses morts), SWITCHER de
  hold-and-react à un **push de CLÔTURE** rounds 6-9 pour wipe l'ennemi avant le cap ; commencer à grind un anvil Resilient
  lent (Corrodius) dès round 5-6 plutôt que de le laisser comme un clock qu'on perd. NE PAS over-hold un board dominant.
- **INSCRIT** : wiki §3quater (EnvEndBombardment comme hazard de round-cap, tag [self-play consensus, seed 80000 (opus run)]).
  Reste à valider : round-cap exact (toujours ~10 ? scale ?) + tracker live du compteur de rounds pour budgéter le clock.

## H53 — MV71 Sniper Drone (Sho'syl) a un range minimum ~2 hexes — **INFIRMÉE** (décompilé, 2026-07-22, #61bis)
- **verdict** : il n'existe **AUCUNE portée minimale**. `GetDynamicInvalidTargetReason @181109630` ne contient aucun prédicat de distance : le seul gate dynamique est « il existe au moins une tuile de spawn valide » (`PickTile(firstOnly=1) != null`, @181109ac0). Le comportement observé (« pas de drone au contact ») vient de `IsMeleeAttack @181109960` : **cible adjacente ⇒ l'ability délègue intégralement à l'attaque normale mêlée** (`ExecuteBehaviour @181108900` ET `PredictAttack @18110a5f0` branchent tous deux dessus). C'est un DISPATCH, pas un refus de cible — et il n'y a donc rien à « vérifier avant de compter sur le drone » sinon l'adjacence. Le `mutated=False` observé en self-play relève de l'autre pattern (échecs silencieux du runner, cf. l'entrée voisine), pas d'un min-range. Détail : `docs/rl/case-61bis-mv71-sniper-drone.md` §5.4.
- *(claim d'origine conservée ci-dessous pour traçabilité)*
- **claim** : l'attaque normale de Sho'syl (`MV71SniperDroneSquad`) retourne `mutated=False` quand la cible est à ≤1 hex de Sho'syl (adjacent ou same-column-one-row). Le drone serait invocable/attaquant seulement à distance ≥2.
- **mécanisme proposé** : le drone a `RangedSpecialist` (« if this unit did not START its turn ADJACENT to an enemy unit, it deals +dmg% with ranged attacks ») ET une portée normale = r4 ranged. Invoqué adjacent à un ennemi, le RangedSpecialist serait invalidé et/ou le drone ne peut pas cibler à r=0/1.
- **evidence** : seed 80000 Player A (about=mine) — MV71 attack `mutated=False` sur Tanksmasha à ≤1 hex, 3 tours consécutifs (T5-T7). La cible Tanksmasha (3793 HP) a survécu 4 tours malgré 3 activations Sho'syl contre elle.
- **caveat** : OBSERVATEUR UNIQUE (Player A seulement — Player B n'a pas cross-observé). Le drone est un Summon auto-ciblant — le rejet peut aussi venir d'un obstacle de terrain ou d'un bug de runner, pas forcément du range minimum. Non recoupé par gameconfig (aucun `minRange` trouvé dans le kit `tauSmnDroneSniper`).
- **à valider** : tester explicitement MV71 à distance 1, 2, 3 en duel contrôlé pour confirmer le cutoff.
- **→ wiki si confirmé** : §3bis Sho'syl (MV71 min-range) + ajouter dans la doctrine oracle « vérifier distance cible avant de compter sur le drone ».

## H54 — FoulInfusion (Pestillian) fire l'attaque mêlée sur un ADJACENT ALÉATOIRE, pas la cible d'ability — `provisoire` (pour:1 contre:0) (self-play divergence A/B)
- **claim** : `FoulInfusion` déclenche « an immediate normal melee attack against a random adjacent enemy » (i2 verbatim). La target de l'ability (`u95` = Tigurius) n'est PAS la cible de l'attaque mêlée — c'est un ennemi adjacent au hasard au moment du cast.
- **evidence** : seed 80000 Player B (about=mine) — FoulInfusion castée en ciblant Tigurius (u95), l'attaque normale a résolu sur TG (u97), l'unité ADJACENTE à Pestillian. Perte d'une action ciblée (1 activation Pestillian gaspillée sur une cible non-prioritaire).
- **recoupage i2** : gameconfig confirme le texte « Pestillian then immediately performs a normal melee attack against a **random adjacent enemy** » → le claim est i2-COHÉRENT, pas une surprise. Mais non observé avant = inscrit comme H pour traçabilité.
- **implication doctrine** : positionner Pestillian adjacent UNIQUEMENT aux ennemis qu'on veut que son attaque mêlée aléatoire frappe. Cibler l'ability sur un ennemi ≠ contrôler la cible de l'attaque mêlée.
- **à valider** : re-observer avec un seul ennemi adjacent (no-random : résultat forcé) pour confirmer que la cible ability et la cible mêlée sont bien indépendantes.
- **→ wiki si confirmé** : §3quater Pestillian (FoulInfusion = melee random-adjacent, pas la target ability).

## H55 — `play --no-ai` rejette SILENCIEUSEMENT des moves (ok=true / mutated=false) sans reason-code — `provisoire` (pour:1 contre:0) (self-play divergence A/B)
- **claim** : de nombreux moves via `play --no-ai` reviennent `ok=true` mais `mutated=false` (l'unité reste sur place), sans erreur ni reason-code, avec un cascade vide / 2-events. La cause exacte (hex occupé ? water forced-stop ? footprint d'une BigTarget ? hors-portée ?) n'est PAS surfacée.
- **evidence** : seed 80000 (opus run) Player B (about=mine, friction) — Pestillian (4,9)→(4,6), Vitruvius →(2,7), Arjac →(2,4), Pestillian →(4,5) TOUS rejetés silencieusement ; conséquence directe : la formation s'est fragmentée tour après tour et Tanksmasha s'est retrouvé ISOLÉ à (3,4) → focus-killé. Player A (about=mine) rapporte aussi un échec silencieux analogue (drone MV71 mutated=False, cf. H53) — pattern « mutated=false sans diagnostic » cross-observé sous des formes différentes.
- **caveat** : OBSERVATION OUTIL/HARNESS, PAS une mécanique de jeu queryable via gameconfig/i2. C'est une divergence d'EXPÉRIENCE entre A et B (B l'a subi massivement sur des moves de formation ; A sur un summon-attack). Pas recoupable par gameconfig (comportement du runner/RPC `play`). Distinct de H53 (qui est spécifiquement le drone MV71).
- **implication doctrine** : VÉRIFIER que chaque move a `mutated=true` avant d'enchaîner la formation ; si rejet, re-planifier en single-step plus courts OU sonder la légalité (glyph/aiMovableTiles) — ne pas ré-émettre le même pattern d'avance en aveugle (B l'a fait à répétition).
- **à valider** : (1) faire surfacer un reason-code côté harness (occupied/water/footprint/out-of-range) ; (2) confirmer si le rejet vient du footprint BigTarget ou d'un water forced-stop. → amélioration OUTIL (toolfeedback.md), pas wiki de jeu.
- **MAJ 2026-06-23 (investigation ghidra)** : la primitive de reason-code EXISTE pour les **abilities** — `AttackQuery.GetInvalidTargetReason(attacker, tile, defender, ability)` → `IBrokenTargetingRule.Type` (flag `TargetingRule` : `TargetIsInRange`/`AlreadyUseThisTurn`/`TargetIsHealable`/`TargetTileIsFree`/…) ; énumération via `BattleQuery.GetAllValidTargetsFromAllPossibleMovementTiles(unit, ability)`. **N.B.** ces primitives concernent les **abilities** (le no-op d'ability de A) ; le no-op de **move pur** de B (footprint/water/occupied) reste côté `MovementQuery` (déjà couvert réactivement par la pré-validation `_movable_map`/`moves`). RPC `abilityTargets` plan + détails RE : `docs/rl/ai-step-toolkit.md` §« Légalité ability + RAISON structurée ».

## H56 — Cause de l'isolation de Tanksmasha (over-extension dive vs fragmentation de formation par moves rejetés) — `provisoire` (pour:0 contre:0, divergence causale A/B NON tranchée) (self-play divergence A/B)
- **claim (fait concordant)** : LES DEUX sides s'accordent sur le FAIT — Tanksmasha (orksNob, move4 charger ~10040 HP) s'est retrouvé ISOLÉ forward à (3,4) en avance de son support et a été focus-killé en un tour (textbook over-extension, le failure-mode dominant).
- **divergence sur la CAUSE** : A (theirs) lit ça comme un **dive d'over-extension volontaire/agressif** de l'adversaire qu'A a puni (multi-source focus : drone Sho'syl + Atlacoya Talons + Exitor CordClaw Direct Pierce100 bypass block). B (mine) lit ça comme une **conséquence involontaire** : les moves d'escorte (Arjac/Pestillian) ont été rejetés silencieusement (cf. H55), Tanksmasha a avancé seul faute d'accompagnement, PAS par choix d'agression.
- **caveat** : pas une mécanique de jeu — divergence d'INTERPRÉTATION de la même séquence (un observateur voit un dive, l'autre connaît la cause harness). B a la vérité causale (c'est SON unité et SES moves rejetés) ; A n'a vu que le résultat. Non recoupable gameconfig.
- **implication doctrine** : un corps durable laissé forward (volontairement OU par fragmentation) reste focusable = même leçon que le failure-mode dominant. Le correctif est en amont (vérifier `mutated`, cf. H55) ET en aval (committer le MINIMUM forward, rapatrier après un kill).
- **à valider** : rejouer en vérifiant `mutated=true` sur chaque move d'escorte avant d'avancer un charger ; si la formation reste cohésive, l'isolation disparaît → confirmerait la lecture B. — `provisoire` (pour:0 contre:0, NON tranché — Verif=plausible sur le summon, MkXGravis sur le summon UNCONFIRMED)
- **claim (à vérifier)** : Bellator `DeathFromAbove` summon **1 Inceptor par round écoulé** (round 2 = 2 Inceptors), chacun
  atterrissant adjacent à la cible + attaquant immédiatement ; killer Bellator annule les summons futurs (suit le gating
  standard caster-mort). Question OUVERTE : les Inceptors summonés (`ultraSmnInceptor`) portent-ils **MkXGravis** (double-armure)
  comme Bellator lui-même ?
- **caveat (Verif)** : gameconfig CONFIRME « Summons 1 Inceptor for each round that has started » → round 2 = 2 est correct ;
  type summon = `ultraSmnInceptor`, base gameconfig **4001 HP / 873 Armour** (l'observation live 5483 HP = scaling niveau/rareté,
  plausible non base-vérifiable) ; landing-adjacent + attaque immédiate = i2-confirmé ; kill-stops-flood = plausible (suit le
  gating caster-mort, pas explicite i2). MAIS **gameconfig ne liste PAS MkXGravis sur le `ultraSmnInceptor`** — le trait MkXGravis
  est confirmé sur **Bellator lui-même**, PAS sur le summon → l'observation « les Inceptors portent aussi MkXGravis double-armure »
  est **UNCONFIRMED** (le kit du summon n'est pas vérifié, seules HP/Dmg/Armour de base sont données par i2).
- **à valider** : recon dédié du `ultraSmnInceptor` (gameconfig.py + i2) pour confirmer/infirmer MkXGravis sur le summon ; n>1
  pour le HP live scalé. Si MkXGravis est ABSENT du summon, les Inceptors sont crackables au chip ranged normal (≠ Bellator).
- **evidence** : seed 70061 (n=1 — les 2 Inceptors tués T3 via Tanksmasha+Certus+Makhotep ; « MkXGravis double-armour sur les
  Inceptors » = observation non recoupée par gameconfig). cf. wiki §3bis Bellator DeathFromAbove + §3bis ultraSmnInceptor.
- **→ wiki si confirmé** : §3bis ultraSmnInceptor (préciser MkXGravis présent/absent sur le summon).

## H57 — Mis-attribution de la cascade fatale : EnvEndBombardment (B) vs RadBombardment-engine (A, vérifié-correct) — `réfutée côté B` (pour-A:1 contre-B:1) (self-play divergence A/B)
- **claim (divergence)** : sur le 3ᵉ run seed 80000 (team2 W net à T5), les deux observateurs divergent sur la SOURCE de la cascade qui a wipe la ligne team1. A (about=theirs) attribue le wipe à **RadBombardment + Contamination + Foehammer** (noms d'events explicitement loggés dans son state-file). B (about=theirs, confidence: med) attribue le swing décisif à un **EnvEndBombardment environmental hazard** (« likely a board hazard ») et admet « I won largely BECAUSE of an environmental hazard, not purely through my own engine-denial ».
- **verdict** : **A a raison, B a mal lu.** Le combat s'est terminé round ~5 (3-4 endturns dans les action logs des deux state-files ; both « turns_played:5 »), BIEN avant le round-cap (~round 10) qui déclenche EnvEndBombardment (cf. H51 confirmée sur le run #2 de cette même seed, qui lui s'est étendu jusqu'au cap). À T5 il ne PEUT PAS y avoir de bombardement de round-cap. La cascade était l'alpha de B lui-même : RadBombardment (ligne Toxic Pierce70 sur le blob clusteré rows 0-1) + MasterAnnihilator mark (+1 hit) + ContagionsOfNurgle armor-shred + Foehammer (snowball post-Tanksmasha-kill).
- **caveat** : pas une mécanique de jeu nouvelle — divergence d'ATTRIBUTION causale entre observateurs (un mis-read de B sur sa propre win-condition). Recoupé par le COMPTE DE TOURS (load-bearing) : 3-4 endturns = round ~5 ≪ round-cap. EnvEndBombardment (H51) reste confirmée comme mécanique de round-cap réelle, MAIS elle n'était PAS active dans CE run. B a sur-attribué sa victoire à un hazard absent.
- **implication doctrine** : (1) un observateur doit dater une cascade par le compte de rounds avant d'invoquer EnvEndBombardment (round-cap = ~10, pas T5) ; (2) la vraie leçon pour A (perdant) tient quelle que soit l'attribution — un blob clusteré bas est wipe par RadBombardment+mark+aura, ESPACER ; (3) B a gagné par son propre engine ranged + discipline anti-cluster, PAS par un hazard.
- **evidence** : seed 80000 (opus + moves fix), 3ᵉ run. A state-file = RadBombardment + Contamination + Foehammer loggés ; B = EnvEndBombardment inféré post-hoc (confidence med). Action logs : 4 endturns (A) / 3 endturns (B) = round ~5. cf. wiki §3bis Vitruvius RadBombardment (3ᵉ confirmation) + selfplay-journal seed 80000 bloc #3 (divergence #1).

## H58 — Le round-cap EnvEndBombardment n'est PAS fixé à ~round 10 : peut fire round ~5-6 — `provisoire` (pour:2 contre:0) (self-play, seed 80000 runs #4 + #5)
- **claim** : sur le run #4 seed 80000 (2026-06-23, standoff passif mutuel → no-winner), l'EnvEndBombardment a fire round ~5-6 (action logs : 4 endturns/side = round ~5 ; telegraphé `EnvEndBombardment_Incoming` ~1 round avant) et a wipe les deux blobs. C'est BIEN PLUS TÔT que le « ~round 10 » supposé par H51/H57.
- **enjeu** : H57 a utilisé « round-cap = ~round 10 » comme argument de TIMING pour réfuter l'attribution de B au run #3 (cascade à T5 ⇒ « trop tôt pour le round-cap »). Si le cap peut fire round ~5-6, cet argument de timing à lui seul ne tient plus. (H57 reste néanmoins valide sur l'ÉVIDENCE D'ÉVENTS : run #3 = team2 W net avec RadBombardment + Contamination explicitement loggés, PAS un mutual-wipe — l'attribution event-based de A est correcte indépendamment du timing.)
- **hypothèses alternatives** : (a) le round-cap dépend de la SEED/config de bataille (variable, pas une constante ~10) ; (b) le « compteur de round » interne ≠ le compteur de « tours-joueur » affiché (un round = 1 tour de CHAQUE équipe → 4-5 endturns/side ≈ round 4-5 réels, et le cap serait à ~round 5-6) ; (c) le label UI « tour » est un placeholder figé (cf. SereneUnifier) donc non fiable pour dater le cap.
- **à valider** : instrumenter le compteur de round réel (pas le label UI) sur ≥2 runs qui atteignent le cap ; lire la config de bataille pour un champ round-limit. Tant que non tranché, **ne pas se reposer sur « j'ai jusqu'au round 10 »** — traiter le telegraph `EnvEndBombardment_Incoming` comme l'unique horloge fiable (fermer dès qu'il apparaît).
- **evidence** : seed 80000 run #4 (no-winner, cap ~round 5-6) vs H51/H57 supposant ~round 10. cf. wiki §3quater EnvEndBombardment (nuance timing run #4) + selfplay-journal seed 80000 bloc #4. **2ᵉ data point — run #5 (2026-06-23 antipassivity)** : A a rapporté le fire à `AmountOfTurnsStartedByCurrentPlayer=12` (≈ round 6), CONFIRMANT le ~round 6 indépendamment du run #4 — et cette fois A jouait ACTIVEMENT (3 kills, 4v2 ahead), donc le cap n'est PAS une conséquence de la seule passivité : c'est une horloge de seed/config qui fire ~round 6 quoi qu'il arrive. cf. selfplay-journal seed 80000 bloc #5.

## H59 — Friction outil : `EnvEndBombardment_Incoming` (countdown du round-cap) n'est PAS surfacé dans `decisionView` (EFFETS CRITIQUES/ACTIFS) — `flaggé (self-play, double-observer)` (pour:2 contre:0) (seed 80000 run #5)
- **claim** : le tick de compte-à-rebours du round-cap (`Effect_Refresh EnvEndBombardment_Incoming RemainingTurns=1`) n'apparaît QUE dans le dump brut de cascade d'événements, **jamais** dans les sections synthétisées EFFETS CRITIQUES / EFFETS ACTIFS de `decisionView`. L'oracle n'a donc aucun warning in-view que le cap est à 1 tick de fire au moment de décider son tour.
- **enjeu** : c'est un effet **décisif** (no-winner double-loss). L'absence de surface a directement contribué à la non-conversion run #5 : A a CONSOLIDÉ au tour T5 (sortir Atlacoya du Foehammer) au lieu de fermer, faute de voir que le cap allait fire le tour suivant. Un countdown surfacé aurait changé la décision (A le dit explicitement).
- **fix proposé** : remonter `EnvEndBombardment_Incoming` (+ son `RemainingTurns`) dans une section dédiée de `decisionView` (ex. « ⏱ HORLOGE round-cap : fire dans N tour(s) ») dès que l'effet est présent sur le board, OU dans EFFETS CRITIQUES. Idem surfacer un terminal-summary post-`Finished` (qui est mort au cap, survivants/team) que les 2 sides réclament aussi.
- **double-observer** : flaggé INDÉPENDAMMENT par A (« view did NOT surface EnvEndBombardment_Incoming in EFFETS CRITIQUES/ACTIFS, only in the raw play cascade ; a surfaced countdown would have changed my turn-5 decision ») ET par B (« only visible as truncated "(+179 events)" in the cascade tail, easy to miss ; surfacing the bombardment tick + per-unit damage would help »). → friction outil consensus, PAS une divergence de mécanique.
- **doctrine intérim** (tant que non fixé) : traiter `EnvEndBombardment_Incoming` comme l'unique horloge fiable — dès qu'il apparaît dans la cascade, FERMER au tour suivant (l'avance numérique ne sauve pas du cap, cf. H58/run #5). cf. selfplay-journal seed 80000 bloc #5 (divergence/friction #2) + wiki §3quater EnvEndBombardment run #5.

## H59 — Pas de champ `winner` persisté post-Finished : l'issue d'un match terminé n'est pas lisible (status/state-file = None) — `provisoire` (pour:2 contre:0) (self-play, observabilité — signalé par A ET B)
- **claim (friction outil)** : après `gameOver:true` / `stage=Finished`, le runner est finalisé/vidé : `rl_duel.py status` retourne `stage=None turn=None alive_by_team={}` et le state-file n'a aucun champ `winner`/`winningTeam`. L'issue (W/L/draw) n'est PAS lisible directement — il faut l'INFÉRER du dernier snapshot pré-game-over.
- **conséquence vécue** : sur le run #4 seed 80000 (mutual-wipe no-winner), A a inféré « L » du dernier snapshot HP (team2 survivants out-HP ses fragiles) alors que la vérité runner = **draw / winner=None** ; B a lu correctement « no-winner ». La divergence de perception A/B (L vs draw) découle ENTIÈREMENT de cette absence de champ winner persisté — pas d'un désaccord factuel sur le combat. Les DEUX players ont explicitement signalé la friction.
- **implication** : un teardown DOIT adjuger sur `alive_by_team`/`winner=None` (ground truth runner = draw), JAMAIS sur la perception « L » inférée d'un snapshot pré-cascade. Un mutual-wipe board-wide où les survivants adverses sont plus durables se LIT facilement comme une « L » mais reste un DRAW zéro-sum.
- **à valider / fix proposé** : persister un champ `finalWinner` (team1|team2|null) + `finalAliveByTeam` dans le state-file au moment du game-over, AVANT que le runner ne vide son état — supprimerait l'ambiguïté d'adjudication.
- **evidence** : seed 80000 run #4 — `status --state-file _sp_80000_A.json` = `stage=None ... alive_by_team={}` ; A frictions[] + B frictions[] signalent tous deux l'absence de winner field. cf. selfplay-journal seed 80000 bloc #4 (Adjudication + divergence #1).

## H60 — Collision de glyph board-map : le 'b' minuscule = À LA FOIS le terrain drybush ET la lettre d'unité du Tyrant Guard — `provisoire` (pour:1 contre:0) (self-play, friction renderer — B seul)
- **claim (friction outil)** : dans l'ASCII decision-map, le glyph 'b' minuscule est ambigu : il sert à la fois de glyph TERRAIN (drybush / LightCover) et de lettre d'UNITÉ pour le Tyrant Guard. Un drybush en rows 6-7 a été lu par B comme un Tyrant Guard qui avançait.
- **conséquence vécue** : B a chargé Tanksmasha (UnstoppableMomentum) sur ce « TG » fantôme → charge dans le vide, zéro dégât, Tanksmasha stranded forward (over-extension, le failure-mode dominant). Corrigé au tour suivant (rapatriement (3,7)).
- **implication doctrine** : **toujours cross-check les positions d'unités via `status` (ground truth), jamais inférer depuis l'ASCII map quand une lettre d'unité collisionne avec un glyph terrain.** (single-observer = B ; A n'a pas rapporté la collision mais ne contredit pas.)
- **à valider / fix proposé** : désambiguïser le renderer (glyphs terrain en MAJUSCULE ou jeu de symboles dédié distinct des lettres d'unité ; ou marquer les unités d'un préfixe). n>1 souhaitable pour confirmer la généralité de la collision.
- **evidence** : seed 80000 run #4 — B mistakes[] + mechanics[about=mine, "Board glyph collision"] + frictions[]. cf. selfplay-journal seed 80000 bloc #4 (séquences B).

## H61 — UnstoppableMomentum(Reworked) : un `--to` NON-collinéaire fait charger l'unité PAST la cible dans le vide (mutated=False, zéro dégât, stranded forward) — `provisoire` (pour:1 contre:0, recoupé gameconfig) (self-play, friction outil — B seul)
- **claim** : la charge directionnelle d'UnstoppableMomentumReworked (Tanksmasha) exige que la tuile-cible soit la HEX de l'ennemi ET sur un axe-hex droit depuis le départ. `act ability --to <tuile non-collinéaire>` est accepté silencieusement (ok=true) mais l'unité charge PAST la cible jusqu'au prochain obstacle/BigTarget, sans toucher personne (mutated=False), et reste stranded forward.
- **recoupage gameconfig** : `UnstoppableMomentumReworked` Melee Direct100 = « Charges in one of 6 directions and keeps moving in a straight line until he hits an obstacle or a Big Target » + `initialCooldownTurns:1`. → gameconfig CONFIRME que la charge est strictement directionnelle (6 axes) et s'arrête sur obstacle/Big Target uniquement ; une cible hors-axe n'est jamais « atteinte ».
- **implication doctrine** : avant de committer une charge UnstoppableMomentum, VÉRIFIER l'alignement de lancement via `abilities` (les charge-ends énumérés) — ne committer que si la charge connecte réellement un ennemi sur un axe droit. Après usage, indispo 1 round (initial cooldown).
- **à valider / fix proposé** : un reason-code / pré-check côté `act` qui rejette (ou avertit) si la tuile-charge ne connecte aucun ennemi collinéaire éviterait le commit gaspillé + l'over-extension. (single-observer = B ; mécanique gameconfig-confirmée.)
- **evidence** : seed 80000 run #4 — B mechanics[about=mine, "UnstoppableMomentumReworked"] confidence:high + frictions[] (« charged (4,7)->(1,6), no damage, stranded forward, mutated=False »). gameconfig.py --ability UnstoppableMomentumReworked = verbatim. cf. selfplay-journal seed 80000 bloc #4.

## H62 — Tanksmasha (orksNob) survit à un K? near-lethal via le BLOCK de `BeastSlayer` (10% / 100% armure courante) — `provisoire` (pour:1 contre:0, recoupé gameconfig) (self-play divergence A/B — A a mis-labellé le trait)
- **claim** : un burst multi-source K?-labellé peut UNDER-killer Tanksmasha — vécu chunké 9232→**738 survécu** — parce que sa clause de block absorbe un coup. La MÉCANIQUE est réelle ; **la divergence est sur le NOM du trait** : A l'a appelé « BeastSnagga_ExtraBlock » mais Tanksmasha n'a PAS BeastSnagga.
- **recoupage gameconfig** : `gameconfig.py orksNob` → traits = **BeastSlayer**, GetStuckIn, Unstoppable (PAS de BeastSnagga). `gameconfig.py --trait BeastSlayer` = `{beastSlayerExtraDmgPct:20, beastSlayerBlockChance:10, beastSlayerBlockAsMaxArmorPct:100}` → « +20% mêlée vs Big Targets/Vehicles ; added **10% chance to Block 100% of its current Armour as Damage** ». → le block qui a sous-killé vient de **BeastSlayer**, pas d'un « BeastSnagga ». (NB : BeastSnagga EST un trait Ork distinct — `{beastSnaggaBlockChance:10, beastSnaggaDmgAsMaxHpPct:20}`, block 20% du MAX HP — mais il n'est PAS sur orksNob ; ne pas confondre les deux block-clauses.)
- **implication doctrine** : sur un BeastSlayer-carrier, un finisher **K?** (pas K!) peut whiffer ~10% du temps via block → préférer overkill franc (≥2× barre OU 3+ sources discrètes) quand le kill est décisif. Déjà inscrit comme nuance au wiki Tanksmasha (recoupage gameconfig BeastSlayer).
- **à valider** : confirmer la fréquence de block sur n>1 (10% = rare → l'observation unique peut aussi être un simple plan-vs-actual under-read amplifié par un −50% SenseOfStone actif ce round-là). Single-observer A, confidence med.
- **evidence** : seed 80000 run roundcap — A mechanics[about=theirs, "BeastSnagga_ExtraBlock"] confidence:med (« survived a combined ~5978-10950 focus at 738 HP »). gameconfig orksNob + --trait BeastSlayer/BeastSnagga = source de vérité. cf. selfplay-journal seed 80000 bloc roundcap. (self-play divergence A/B)

## H63 — Priorité summon-engine vs un round-cap : tuer L'ENGINE qui SNOWBALLE LE PLUS VITE, pas n'importe quel engine — `provisoire` (pour:1 contre:0) (self-play divergence A/B — désaccord de priorité, PAS de mécanique)
- **claim (divergence de priorisation, mécaniques concordantes)** : sur seed 80003 (double-summon-engine de chaque côté + round-cap), A et B ne sont PAS d'accord sur QUEL engine prioriser. **A** a tué le summon-engine *Psychic* (Archimatos, blackPossession — Incursion/Possession board-flip) T7 et le crédite « best decision of the match » (jamais de cascade Bloodletter). **B** déclare que sa #1 erreur fut de NE tuer AUCUN des engines adverses (Yarrick `SendInTheNextWave` + Bellator `DeathFromAbove`) et désigne **Bellator** comme « la critical clock-engine » (`DeathFromAbove` = 1 Inceptor PAR ROUND ÉCOULÉ → batches croissantes → out-bodies le plus vite). Les DEUX rosters ont 2 summon-engines ; aucun des deux n'a tué l'engine round-scalant de l'AUTRE camp (A n'a pas tué Yarrick/Bellator ; B n'a pas tué Yarrick/Bellator non plus).
- **point de consensus sous-jacent (non divergent)** : les mécaniques sont concordantes — `DeathFromAbove` = N Inceptors = rounds écoulés (gameconfig confirme « 1 Inceptor for each round that has started »), `SendInTheNextWave` = 2 Guardsmen +1/allié mort, max 5 (gameconfig confirme). La divergence porte UNIQUEMENT sur la priorité de kill, pas sur le fonctionnement.
- **hypothèse de résolution** : face à un round-cap, l'engine à tuer en priorité = celui dont l'output **COMPOUND avec le nombre de rounds** (DeathFromAbove : batch = round# → croît chaque tour), AVANT l'engine à output fixe/borné (SendInTheNextWave : cap 5 ; Incursion : burst one-shot). Tuer le board-flip Psychic (A) prévient une cascade unique ; tuer le clock-engine round-scalant (Bellator) coupe la croissance exponentielle qui out-race le cap. Les deux sont défendables — départager sur n>1.
- **à valider / fix proposé** : sur n>1 matchs avec double-summon + round-cap, mesurer si prioriser l'engine round-scalant (DeathFromAbove-class) convertit mieux que prioriser le board-flip Psychic (Incursion-class). Single-match (n=1), désaccord de priorité non tranché.
- **evidence** : seed 80003 — A key_decisions[0] (« KILL Archimatos T7 … best decision ») + threat_cards[Archimatos threat=critical] ; B mistakes[0] (« never killed a SUMMON-ENGINE ») + threat_cards[Bellator threat=critical, « Kill Bellator EARLY »]. gameconfig DeathFromAbove/SendInTheNextWave = source de vérité (mécaniques concordantes). cf. selfplay-journal seed 80003. (self-play divergence A/B)

## H64 — `status` post-Finished est AMBIGU : `winner=None alive_by_team={}` lit IDENTIQUEMENT une ÉLIMINATION propre et un round-cap mutual-wipe — le teardown DOIT vérifier la cascade finale, pas supposer un draw — `provisoire` (pour:1 contre:0) (self-play — friction d'outillage/adjudication)
- **claim** : après `stage=Finished`, `rl_duel.py status --state-file` retourne `stage=None turn=None alive_by_team={}` + « team gagnante : None » — le **même** affichage que le wiki documente pour un no-winner EnvEndBombardment round-cap. Or sur seed 80003 (batchfix) c'était une **élimination PROPRE par team2** (B : cascade finale « last Inceptor 2558→0 TUE, AUCUN event EnvEndBombardment, full team B alive »), PAS un mutual-wipe. Le snapshot per-state est purgé sur Finished → la harness **ne distingue pas** « j'ai éliminé l'adversaire » de « round-cap double-loss » dans le read post-Finished.
- **conséquence (règle d'adjudication)** : un teardown qui lit `winner=None` ne DOIT PAS conclure « no-winner/draw » par défaut. Il faut **croiser** : (a) l'accord W/L des 2 outcome_perceived (A=L & B=W → un vrai vainqueur, PAS un draw) ; (b) à défaut, la cascade finale dans les action_logs (élimination = dernière unité d'un camp à 0 sans event EnvEndBombardment ; round-cap = wipe board-wide simultané avec EnvEndBombardment). Sur 80003-batchfix, (a) suffit : A=L + B=W = team2.
- **à valider / fix proposé** : (1) côté harness, persister un champ `finalOutcome` (eliminated-team / round-cap) AVANT la purge du snapshot, lisible post-Finished ; OU (2) côté teardown, toujours appliquer la règle de croisement ci-dessus. n=1 (mais friction structurelle, re-observable à chaque match qui finit par élimination rapide). Single-observer principal = B (A note aussi le status vide mais l'attribue à l'orchestrateur).
- **evidence** : seed 80003 (batchfix) — B frictions[0] (« harness cannot distinguish 'I eliminated them' from 'mutual round-cap wipe' in its post-Finished status read ; a teardown that reads winner=None must NOT assume a draw without checking the final cascade ») + A frictions[2] (« status --state-file returned empty stage=None winner=None … the local status file is not the source of truth post-finish »). Adjudication 80003-batchfix résolue par accord W/L A/B = team2. cf. selfplay-journal seed 80003 (ts batchfix). (self-play)

## H65 — Roster team1 NON résoluble depuis la BC statique seule quand `PredefinedUnits` ne contient que le groupe enemy — `provisoire` (pour:0 contre:0, friction d'observabilité, non tranché) (self-play divergence A/B — lecture de roster)
- **claim (divergence de lecture, AUCUNE mécanique de jeu)** : sur seed 80031 (match NON joué — runner 22 absent du host), les 2 observateurs lisent DIFFÉREMMENT le roster team1. **A** déclare team1 **INCONNU** : la BC statique `PredefinedUnits` ne contient que le groupe enemy (Id=12, playerId 12 / team2 : emperNoiseMarine, genesBiophagus, tauMarksman, worldExecutions, admecManipulus) ; le côté player (Id=11 / team1) n'y est PAS énuméré, donc sans runner live A ne peut savoir quelles unités il contrôle. **B** suppose un roster team1 (thousTerminator, spaceWulfen, custoBladeChampion, orksKillaKan, admecDestroyer) lu dans une *autre* source `playerUnits` de la seed BC, mais le **flagge lui-même UNCONFIRMED** (jamais confirmé comme roster actif, jamais vu live).
- **point non divergent** : le roster team2 EST vérifiable (PredefinedUnits Id=12) et concordant des 2 côtés. Seul team1 diverge.
- **hypothèse de résolution** : la BC statique capturée pour un PvpBattle peut n'inscrire le roster joueur-1 QUE dans une section `playerUnits` distincte de `PredefinedUnits` (qui ne tiendrait que le groupe enemy preset). Si exact, le roster B (thousTerminator/…) serait le vrai team1 — mais NON vérifiable ici sans runner live. À NE PAS promouvoir tant qu'un match jouable n'a pas confirmé team1 live.
- **à valider / fix proposé** : (1) côté outillage, faire émettre par `status`/`view` une lecture du roster JOUEUR depuis la BC même hors-runner (parser `playerUnits` si présent) pour lever l'ambiguïté A/B ; (2) ne jamais inférer un roster team1 depuis un seul observateur sans cross-check. n=1, match non joué — divergence purement d'observabilité, pas une affirmation de jeu.
- **evidence** : seed 80031 — A roster_mine=[] + win_condition.mine « UNKNOWN — my own roster (player 11 / team 1) is never enumerated in the static BC (PredefinedUnits holds only the enemy player-12 group) » ; B roster_theirs=[thousTerminator…admecDestroyer] tous taggés UNCONFIRMED (« from seed BC playerUnits, playerId:11 »). cf. selfplay-journal seed 80031 (ts 2026-06-23-b5). (self-play divergence A/B)
- **RÉSOLUTION PARTIELLE (n=2, seed 80020, ts 2026-06-23-b5)** : l'hypothèse de résolution ci-dessus est CONFIRMÉE par le teardown 80020 — le roster team1 EST inscrit dans le state-file, mais dans les champs **`myTeam` + `playerUnits`** (PAS dans `PredefinedUnits`, qui ne tient que le groupe enemy Id=12). Sur 80020 : `myTeam=1` côté A + `myTeam=2` côté B, et `playerUnits` = genesMagus/custoKyrus/astraDreir/worldEightbound/eldarMauganRa (team1, playerId 11), tous résolus en gameconfig. Donc l'attribution d'équipe N'EST PAS impossible — A (« roster mine indéterminé ») ET B (« team attribution impossible faute de second groupe PredefinedUnits ») ont tous deux RATÉ ces champs. Règle de teardown : **toujours lire `myTeam`/`playerUnits` des state-files pour le roster joueur, ne pas se reposer sur `PredefinedUnits`** (qui ne porte que le preset enemy). La divergence A/B était une friction de lecture résoluble offline, pas une limite d'observabilité. (self-play divergence A/B — résolue côté teardown)

## H66 — SETUP self-play peut spawner les player-agents AVANT/SANS enregistrer le runner partagé → match unplayable (runner X not found des 2 côtés) — `provisoire` (pour:2 contre:0) (self-play — friction d'orchestration)
- **claim** : sur seed 80031, le runner partagé 22 (déclaré « déjà construit » dans les préconditions des 2 players) n'a JAMAIS existé dans la session Frida 4 au moment du spawn des agents. Symptômes CROSS-VALIDÉS A+B (ground truth, pas proxy) : `listRunners` (session 4) = `[]` ; `observeBattle({runnerId:22})` → err `runner 22 not found` ; `GET /api/selfplay/4/await?runnerId=22&player=…` retourne **INSTANTANÉMENT** `{"error":"runner 22 not found"}` (ne bloque PAS jusqu'au timeout → la boucle hand-off ne peut jamais atteindre `yourTurn`) ; `rl_duel view/status --state-file` → `runner 22 not found` / `stage=None`. Les 2 state-files sont bien formés (runnerId=22, seed=80031, action_log=[]) mais pointent un runner que le host n'a jamais enregistré.
- **cause probable** : (a) le SETUP n'a pas complété l'enregistrement `buildPatchedRunner` du runner partagé avant de spawner les players (race / échec silencieux du build), OU (b) un reinject/host-restart APRÈS SETUP a vidé le registry in-memory du runner (cf. `feedback_host_restart_kills_mirror` : l'état mémoire du runner est perdu à chaque reinject). Le disque (state-file) survit mais référence un runnerId mort.
- **conduite correcte des players (validée)** : les 2 agents ont REFUSÉ de s'auto-réparer (pas de build/amorce/nav/dispose) — minter un nouveau runnerId aurait désynché l'arène shared et corrompu la coordination. Diagnostiquer + reporter le blocker > produire silencieusement un runner différent. (Conforme à `feedback_fanout_per_item_scope` : n'accepter un résultat que vérifié, jamais deviné.)
- **à valider / fix proposé** : (1) SETUP doit VÉRIFIER (`listRunners` contient le runnerId) APRÈS build et AVANT de spawner les players ; échouer le match tôt sinon. (2) Ajouter un endpoint introspection `GET /api/selfplay/:id/status` (B note que seul `/await` existe → diagnostic plus lent). (3) `/await` devrait distinguer `runner not found` (erreur fatale) d'un `timedOut` (hand-off normal) côté orchestrateur pour re-SETUP automatiquement. n=1 mais friction structurelle re-observable.
- **evidence** : seed 80031 — A frictions (« runnerId 22 does not exist in the host … listRunners returns [] … consistent with SETUP not completing the buildPatchedRunner registration, or a reinject after SETUP wiping the in-memory runner registry ») + B frictions (« HARD BLOCKER: runner 22 (declared 'DEJA construit') does not exist in session 4 … /await returns INSTANTLY … the SETUP/orchestrator step that was supposed to build the shared runner 22 did not complete »). cf. selfplay-journal seed 80031. (self-play)
- **2ᵉ OBSERVATION (n=2, seed 80020, ts 2026-06-23-b5) — affine la cause vers une EVICTION par cap de registry, pas un runner jamais-build** : mêmes symptômes CROSS-VALIDÉS A+B (`view`/`observeBattle`/`await` instantané → `runner 24 not found` des 2 côtés), MAIS un datum NOUVEAU qui distingue 80020 de 80031 : sur 80020 le tracker host `/api/runners` liste **TOUJOURS** runnerId 24 (sessionId 4, `lastLabel:"StartMatch"`, jamais progressé) ET liste les runners 25-31 construits APRÈS 24. Donc le runner partagé a bien été enregistré côté host (le tracker le garde) mais son **handle live IL2CPP script-side a été évincé** quand les builds ultérieurs (25-31) ont rempli le registry — entrée host stale vs handle live mort. Cela renforce la cause (b) « registry vidé/évincé » plutôt que (a) « jamais build ». Sur 80031 `listRunners=[]` (registry vide) ; sur 80020 tracker-host non vide mais handle live évincé → deux variantes du même mode d'échec. **Fix prioritaire affiné** : pin/refcount les runners self-play en vol pour qu'un build ultérieur ne puisse pas évincer le handle live d'un match actif (recommandation explicite des 2 sides 80020). cf. selfplay-journal seed 80020 (ts 2026-06-23-b5). (self-play)

## H67 — BasiliskBarrage (Thaddeus) comme STANDOFF-BREAKER central vs un double-turtle (board-wide AoE/Pin/Suppress, exposition zéro) — `provisoire` (pour:1 contre:0) (self-play divergence A/B — désaccord de SALIENCE, PAS de mécanique)
- **claim** : contre un long standoff/double-turtle (deep gap entre les déploiements), **BasiliskBarrage est le tempo-answer** : un cast board-wide depuis une tuile back STATIONNAIRE chip toute la grappe ennemie REGARDLESS du gap, les Pin (move-1) ET DÉSARME tout Overwatch armé touché (SuppressiveFire = Suppress stoppe l'OW) — convertit un turtle passif en pression proactive **sans exposer aucun corps** (Thaddeus ne bouge pas). Lève le risque de no-winner double-turtle (cf. la série seed 80000 round-cap : un camp DOIT forcer la clôture — le barrage est l'outil pour le faire SANS sur-extension).
- **divergence A/B** : A(mine, seed 80042) a ACTIVEMENT utilisé le barrage T3 (chip 3 ennemis ~2025 + Pin 3 + disarm de l'OW armé de Certus) → l'a observé porter comme l'axe décisif du tempo. B ne le liste PAS comme une menace offensive saillante (Thaddeus threat=high par SpotterReworked-buff, mais « stayed back-row, never reached », pas identifié comme l'axe qui l'a pressé). → divergence de SALIENCE/lecture, PAS de fait : la mécanique elle-même est gameconfig-CONFIRMÉE (« barrage of 5 shells on any target on the battlefield … SuppressiveFire trait applies », croissance +1 obus/round) et déjà au wiki §astraOrdnance. Ce qui est candidat = la DOCTRINE « barrage = standoff-breaker zéro-exposition » (utiliser le board-wide reach pour briser un turtle au lieu d'avancer).
- **à valider** : sur un prochain match avec Thaddeus à MOI vs un turtle, ouvrir le tempo par le barrage stationnaire (pas par une avance) → mesurer si le chip+Pin+disarm-OW force l'engagement adverse sans coûter de corps. Promouvoir au wiki §astraOrdnance Tac si confirmé n≥2.
- **evidence** : seed 80042 — A key_decisions[0] (« Used Thaddeus' board-wide BasiliskBarrage T3 as the standoff-breaker: chipped 3 enemies, Pinned them, and crucially disarmed Certus' armed Overwatch — converting a deep-gap turtle into proactive pressure without exposing anyone ») + A mechanics[BasiliskBarrage, confidence:high] ; B threat_cards[Thaddeus threat=high mais « stayed back-row, never reached »], pas d'observation offensive du barrage. gameconfig --ability BasiliskBarrage = source de vérité (mécanique concordante). cf. selfplay-journal seed 80042 (ts 2026-06-23-b5). (self-play divergence A/B — salience)

## H68 — GAP outillage : pas d'overlay des arcs d'Overwatch ARMÉ → le danger-zone number ne flag PAS le one-shot OW (perte gratuite re-observable) — `provisoire` (pour:2 contre:0) (self-play — friction outil, cross-rapportée)
- **claim** : un Overwatcher armé (Sy-gex r3, Re'vas EWO r2, Certus r3) tire une volée gratuite souvent LÉTALE sur la 1ʳᵉ unité qui BOUGE dans son arc au tour adverse, MAIS le harness n'expose PAS cet arc comme un overlay pré-move : le `danger-zone number` du `view`/`moves` ne distingue pas une tuile « OW-trigger one-shot » d'une tuile danger ordinaire → un move dans l'arc se solde par une perte gratuite SANS warning. Le seul signal est l'effet armé dans `decisionView.effects` (Overwatch_AutoAttack / EarlyWarningOverride_ReactivateOverwatch), à corréler À LA MAIN avec la portée + la position du mover.
- **conduite correcte** : avant de bouger une unité de valeur, (1) lire les effects pour repérer les Overwatchers armés, (2) calculer leur arc r2/r3 à la main, (3) tester l'arc avec un corps durable d'abord OU rester hors portée jusqu'à expiration de l'OW. Exploit : une fois l'OW a fire, il DISARME pour le reste du tour ennemi → avancer le bulk APRÈS le 1er trigger (cf. wiki Sy-gex Tac n+1).
- **fix proposé** : un mode `moves --ow` (ou un tag dans `moves`) qui marque les tuiles déclenchant un Overwatch armé (comme `moves` tag déjà la legality) — recommandé explicitement par B (seed 80042). Distinct de la danger-zone statique.
- **evidence** : seed 80042 — B frictions (« Overwatch-arc reachability is NOT exposed as an overlay — moving into Sy-gex's armed r3 OW arc triggered a fatal free shot that I had no pre-move warning for (the danger-zone number didn't flag it as a one-shot). Had to learn it by losing Yazaghor. A pre-move OW-arc check … would have prevented the loss ») + B mistakes[« Walked Yazaghor into Sy-gex's armed Overwatch r3 arc (6,3 from Sy-gex@3,2) — misjudged the hex distance as safe »] ; A threat_cards corroborent indirectement (« never pathed into its r3 arc » = arc calculé à la main, pas d'overlay). Recoupe la note GAP outillage déjà au wiki Re'vas (l.710 « pas d'overlay des zones d'overwatch armé → lire l'effet armé dans decisionView.effects »). cf. selfplay-journal seed 80042 (ts 2026-06-23-b5). (self-play)

## H69 — Mis-attribution « Terrifying » au [0-0] d'un Bolter RANGED — Terrifying est MÊLÉE-only, le [0-0] ranged vient de l'armure/défense vs Bolter faible-pen — `provisoire` (pour:1 contre:0) (self-play divergence A/B — divergence de CAUSE, pas de fait nouveau)
- **claim** : sur seed 80053, B (team2) a observé que la mêlée non-Psychic ET le **Bolter ranged** (GauntletsOfUltramar) de son Calgar ont fait **[0-0] à Dante** tout le combat, et a HÉSITÉ sur la cause (« Terrifying reduces MELEE only per i2, but the ranged Bolter also read [0-0] — likely combined with Dante's high armor/defense + Terrifying », confidence:med). VÉRIF gameconfig --trait Terrifying = VERBATIM **« Takes {[defensePct]}% Damage from Melee attacks »** → Terrifying ne réduit QUE la mêlée subie. Donc le [0-0] sur le **Bolter ranged** de Calgar n'est PAS imputable à Terrifying (qui ne touche pas le ranged) mais à **l'armure/défense de Dante face au Bolter Pierce20** (faible pen vs un body bien armuré → 0). La règle Terrifying=mêlée-only est DÉJÀ au wiki §1/§bloodMephiston/§bloodDante (« bypass = RANGED ») — la divergence est une mis-attribution de CAUSE par 1 observateur, PAS un fait contradictoire ni nouveau.
- **statut** : RÉSOLU par recoupage gameconfig (pas une vraie incertitude de jeu) — listé pour traçabilité du raisonnement self-play. RIEN à inscrire au wiki (la règle y est déjà). DOCTRINE de lecture : ne JAMAIS attribuer un [0-0] RANGED à Terrifying ; chercher la cause côté armure/pen (Bolter Pierce20 ≪ vs body armuré) ou un autre trait (camo/heavy-weapon mitigation). Le seul contre de Terrifying = RANGED/Psychic, et ça ne se manifeste PAS en réduisant un coup ranged à 0.
- **evidence** : seed 80053 — B mechanics[Terrifying, about:theirs, confidence:med] (« Calgar's non-Psychic melee AND ranged Bolter did 0 damage to Dante all game … Terrifying reduces MELEE only per i2, but … the ranged Bolter also read [0-0] — likely combined with Dante's high armor/defense + Terrifying ») ; A ne rapporte PAS de mis-lecture (Terrifying côté A bien comprise = bypass RANGED). gameconfig --trait Terrifying = source de vérité (mêlée-only). cf. selfplay-journal seed 80053 (ts 2026-06-23-b5). (self-play divergence A/B)

## H70 — Explodes splash réel (~4293 sur Azrael) DÉPASSE 25%maxHP attendu (~2259) — magnitude à re-vérifier — `provisoire` (pour:1 contre:0) (self-play candidate, 1 observateur)
- **claim** : sur seed 80072, B (team2) a tué necroSpyder (Aleph-Null, Explodes) au RANGE pendant qu'Azrael (camp A) était adjacent → l'explosion a chipé Azrael **9539→5246, soit ~4293**, alors que la règle de base = **25% des PV MAX = ~2259** (Aleph-Null ~9037 maxHP × 0.25). B hypothèse une **interaction Direct + tuile/fire** (« more than the ~25%maxHP I expected — possibly Direct + tile/fire interaction », confidence:high sur le FAIT du friendly-fire, mais la magnitude n'est PAS expliquée). gameconfig --trait Explodes = `explodesDmg 25` (% maxHP Direct, adjacents) → la magnitude 25% est VERBATIM, donc ~4293 ne s'explique PAS par le trait seul.
- **statut** : friendly-fire de l'Explodes = CONSENSUS confirmé + inscrit au wiki §Explodes [seed 80072]. La MAGNITUDE (~4293 vs ~2259) est un **candidat 1-observateur non résolu** : soit (a) maxHP de l'Aleph-Null plus haut que lu (le templateOverride/buff aurait gonflé maxHP), soit (b) cumul avec une tuile en feu / un DoT actif sur Azrael ce tour, soit (c) un 2ᵉ tick d'effet mal attribué. NE PAS inscrire une magnitude alternative au wiki tant que non re-mesurée.
- **test (VALIDATE)** : rejouer seed 80072 (archive `logs/selfplay/sp_80072_2026-06-23-b6.json`) et lire le `UnitDamaged` Effect_Type de l'explosion Aleph-Null sur Azrael : confirmer maxHP réel de l'Aleph-Null au moment de sa mort + présence d'une tuile-fire/DoT sur Azrael ; recalculer 0.25×maxHP. Si ~2259 isolé → l'écart venait d'un cumul DoT/fire (pas de l'Explodes) ; si ~4293 isolé sur le seul Effect_Type=explosion → la formule n'est PAS un 25% plat (à investiguer côté Direct/scaling).
- **evidence** : seed 80072 — B mechanics[Explodes, about:theirs, confidence:high] (« On death dealt ~4293 to adjacent Azrael (more than the ~25%maxHP=2259 I expected - possibly Direct + tile/fire interaction) ») ; A liste Explodes comme trait de son propre necroSpyder sans chiffrer la magnitude (pas de contradiction, juste pas de 2ᵉ mesure). gameconfig --trait Explodes (explodesDmg 25) = source de vérité pour la formule de base. cf. selfplay-journal seed 80072 (ts 2026-06-23-b6). (self-play candidate)

## H71 — « Matchup structurellement INGAGNABLE » à flagger AU RECON quand un roster all-Power/Physical/Blast affronte ≥3 anchors Resilient+TerminatorArmour — `provisoire` (pour:1 contre:0) (self-play divergence A/B — divergence d'ASSESSMENT, PAS de mécanique)
- **claim** : un roster de chip/burst SANS reach armor-ignore suffisant (1 seule source Direct/Psychic) affrontant **≥3 anchors Resilient+TerminatorArmour** (Aesoth + Maladus + Njal côté A sur seed 80085) est un **mur inattaquable** : l'attrition est perdue d'avance car le chip ne casse jamais le floor Resilient ni la réduction TermArmour, et la seule clé (Direct/Psychic) est en quantité insuffisante. B (PERDANT) diagnostique cela comme une **loss STRUCTURELLE à reconnaître AU DEPLOY** (« correct plan = pure engine-race + hold, never feed fragiles into the wall ; reserve the lone Direct burst for the late-game Resilient anvil, not spend it on engines »). DOCTRINE candidate : au recon, compter les anchors Resilient/TermArmour adverses vs mes sources armor-ignore — si déséquilibre structurel, jouer l'engine-race + hold (jamais feeder le mur), réserver l'anti-armure pour l'anvil-wincon, accepter le least-bad.
- **divergence A/B (ASSESSMENT, pas mécanique)** : B lit le match comme une **loss structurelle imposée par son roster** (mur 3-Resilient out-attrite ses fragiles ; engines tués mais le mur gagne). A (VAINQUEUR, MÊME match) ne le décrit PAS comme un mismatch structurel mais comme un **out-trade de l'écran adverse** (« j'ai out-tradé son screen jusqu'au lone engine Hollan ») — A attribue sa victoire à l'exécution (kill-engine-on-dive, stun-control, AoE-setup), B à la structure du matchup. → divergence de LECTURE/saillance de la cause de l'issue, PAS un fait de jeu contradictoire (les deux s'accordent sur QUI a gagné = team1, et sur les mécaniques). Aucune mécanique nouvelle.
- **statut** : candidat 1-observateur (B) flaggé divergence d'assessment. NE PAS inscrire au wiki (pas un fait de jeu ; doctrine de recon déjà couverte par le battle-doctrine memory « matchup structurellement unwinnable pour mon roster — pick a non-countered roster »). Recouper sur prochains matchs : un roster all-Power/Physical/Blast vs ≥3 Resilient+TermArmour perd-il systématiquement quand il feed le mur ? Si confirmé n≥2, promouvoir comme heuristique de recon (compter anchors-vs-armor-keys au deploy).
- **evidence** : seed 80085 — B mistakes[3] (« should have flagged this as a STRUCTURAL loss at deploy — all-Power/Physical/Blast chip roster (only ONE Direct source, Azrael) vs THREE Resilient/TerminatorArmour anvils is an uncrackable wall ; correct plan = pure engine-race + hold ») + B mistakes[4] (« spent Azrael's DarkTalonStrike (only armor-ignore burst) on Winged Prime instead of reserving it for the late-game Resilient anvil ») ; A key_decisions (out-trade du screen, exécution) sans framing structurel. Issue = team1 W (consensus). gameconfig : Resilient/TerminatorArmour confirmés sur Aesoth/Maladus/Njal (caps armor-ignore). cf. selfplay-journal seed 80085 (ts 2026-06-23-b6). (self-play divergence A/B — assessment)

## H72 — VigilanceEternal (Tyrith id1202) a besoin de SON propre budget de move : pré-bouger Tyrith consomme le move et rend l'actif no-op — `provisoire` (pour:1 contre:0, recoupé wiki §3 Tyrith) (self-play, friction outil — A seul)
- **claim (friction outil)** : `VigilanceEternal` (Tyrith) cible un ennemi déjà adjacent OU un ennemi ayant un hex libre dans la move range 2 de Tyrith (elle gap-close sur cet hex via SON propre budget de move). Si on **pré-bouge Tyrith manuellement** pour la rapprocher AVANT de caster, le move est consommé → l'actif devient no-op (rejet « cast illegal sans bouger / TargetIsInRange ») même si Tyrith est désormais adjacente. Le label de l'actif annonçait « now/+move » mais après le move manuel il est devenu no-op. **`move-then-VigilanceEternal` != `VigilanceEternal-with-its-own-move`** : l'actif relocate Tyrith lui-même, donc pré-bouger casse l'interaction.
- **conséquence vécue** : A (Player A, team1, seed 80020) a tenté move-then-cast plusieurs fois → rejeté à répétition, fallback sur la normale = output perdu sur un tour de hold critique.
- **implication doctrine** : pour les actifs **mobiles auto-relocateurs** (VigilanceEternal-class : l'ability inclut le move dans son exécution), **NE PAS pré-bouger l'unité** — caster directement depuis la tuile courante en visant l'ennemi (l'actif gap-close lui-même). Cohérent avec wiki §3 Tyrith (VigilanceEternal cible un ennemi déjà adjacent OU un hex libre dans la move range 2 ; « si aucun hex libre éligible n'existe, l'ability ne peut pas s'exécuter »). Single-observer (A) ; recouper sur d'autres actifs mobiles (Waaagh charge, FireAndReposition, LeadingTheCharge) — la règle « le budget de move de l'actif est SÉPARÉ du move de tour » est probablement générale.
- **à valider** : confirmer sur n>1 que pré-bouger une unité avec un actif mobile (qui inclut son propre déplacement) consomme le budget et rend l'actif no-op ; surfacer ce coût dans le plan d'attaque (le label « +move » devrait indiquer que le move est CONSOMMÉ par l'actif, pas additif après un move manuel).
- **evidence** : seed 80020 — A frictions[] (« VigilanceEternal repeatedly rejected as 'cast illegal sans bouger / TargetIsInRange' even after moving Tyrith adjacent — the ability needs its OWN move budget ... pre-moving consumed the move and made the active a no-op ... move-then-VigilanceEternal != VigilanceEternal-with-its-own-move »). B ne cross-observe pas (Tyrith côté adverse). Recoupé wiki §3 Tyrith (i2/gameconfig vérifiés seed 95000). cf. selfplay-journal seed 80020 (ts 2026-06-23-b6, divergence/friction). (self-play, friction outil — A seul)

## H73 — AttemptedPossession (Thaumachus) LIVE-CONFIRMÉ par A (cible + ses summons possédés, summons move-before-attack) — `confirmée côté A + gameconfig` (pour-A:1 contre:0, recoupé gameconfig verbatim) (self-play divergence A/B — A=vérifié-correct, B non-résolu)
- **claim (résolution live)** : `AttemptedPossession` (Thaumachus, range 2) possède la cible **ET tous les summons qu'elle a invoqués** → ils performent immédiatement une attaque normale contre l'**ennemi le plus proche** (= le camp du caster-victime), préférant les cibles non-possédées ; les **summons possédés BOUGENT AVANT d'attaquer** ; dmg = 100% du dmg propre (cap 4001/hit). A (Player A, team1) l'a SUBI : ses 2 Screamers (summons d'Abraxas) hijackés au tour ennemi → déplacés **row 1 → row 6** PUIS forcés d'attaquer son propre camp.
- **divergence A/B** : A (about=mine, **high conf**) résout pleinement l'effet live. B (about=mine, **low conf**) avait l'ability en roster mais ne l'a **jamais résolue** (« ambiguous/risky as a friendly-fire tool from my framing — I avoided gambling on it mid-game ; never resolved its true effect live »). PAS une contradiction de fait : A détient la vérité live, B a simplement évité de gambler l'actif.
- **recoupage gameconfig** : verbatim — « Target an enemy within 2 hexes. The target and any Summons it has summoned become possessed and immediately perform a normal attack against the closest enemy unit, preferring unpossessed targets. Possessed units deal 100% of their own Damage to a maximum of 4001 Damage per hit. **Possessed Summons will move before attacking.** » → confirme les 2 clauses jusqu'ici recon-only (H28) : possède cible+summons ; summons move-before-attack.
- **statut** : PROMU au wiki §Thaumachus avec tag [self-play consensus, seed 80097] (upgrade H28 recon-only → vérifié). Doctrine : garder mes summons hors de la portée 2-hex de Thaumachus tant qu'il vit.
- **evidence** : seed 80097 — A mechanics[AttemptedPossession, about:theirs, confidence:high] (« hijacked my 2 Screamer summons: moved them forward row1→row6 and forced them to attack — confirms Possessed Summons move before attacking ») + A key_decisions (kill Thaumachus T7 before committing summons) ; B mechanics[AttemptedPossession, about:mine, confidence:low] (non-résolu). gameconfig --ability AttemptedPossession = source de vérité. cf. selfplay-journal seed 80097 (ts 2026-06-23-b6). (self-play divergence A/B)

## H74 — Friction self-play : les moves de repositionnement PURS (sans attaque) semblent REVERT au turn-flip — seuls les units ayant ATTAQUÉ gardent leur position forward — `provisoire` (pour:1 contre:0, observateur unique B) (self-play — friction outil, à vérifier : artefact state-file ou règle réelle)
- **claim (friction outil)** : B (Player B, team2, seed 80097) rapporte que les moves PURS (déplacement sans attaque) paraissent **REVENIR à la tuile pré-move après endturn** : Anuphet / Morvenn / Yarrick ont snap back à leur position d'origine au turn-flip, alors que seuls les units qui ont **ATTAQUÉ** ont conservé leur position forward. Conséquence : le positionnement défensif délibéré (avancer une ligne sans tirer) est INEFFICACE — il faut ancrer les positions par une attaque.
- **divergence A/B** : observateur UNIQUE (B). A ne cross-observe pas ce comportement (n'en parle pas dans ses frictions, et A a peu bougé). Donc NON cross-validé — candidat à vérifier.
- **hypothèses de cause** : (a) artefact du STATE-FILE self-play (le runner isolé ne persiste peut-être que les positions attack-ancrées entre les snapshots A/B partagés) ; (b) règle réelle du jeu (improbable — les moves normaux persistent dans le jeu in-battle) ; (c) interaction `play --no-ai` / re-emit (cf. H55 : moves rejetés silencieusement ok=true/mutated=false) où un move « accepté » côté affichage n'est pas committé côté state.
- **à valider** : sur n>1, comparer la position d'une unité APRÈS un move pur + endturn vs après un move+attaque ; instrumenter le state-file pour voir si le champ position diffère pré/post turn-flip. Si artefact self-play → friction d'outillage à corriger (les moves défensifs doivent persister) ; si réel → doctrine « ancrer toute avance par une attaque ».
- **evidence** : seed 80097 — B frictions[] (« Pure repositioning moves (no attack) appear to REVERT on turn-flip — Anuphet/Morvenn/Yarrick snapped back to pre-move tiles after endturn; only units that ATTACKED kept their forward position. This made deliberate defensive line-positioning ineffective ... Possibly a self-play state-file artifact; worth verifying whether non-attacker moves are meant to persist. »). A ne cross-observe pas. cf. selfplay-journal seed 80097 (ts 2026-06-23-b6, divergence/friction). (self-play — friction outil, observateur unique B)

## H75 — Cause de la mort d'Actus (admecManipulus) : free-kill sur over-extension (A) vs trade délibéré forward pour tuer Ulf (B) — `provisoire` (pour:0 contre:0, divergence de RÉCIT d'exécution NON tranchée, PAS de mécanique) (self-play divergence A/B — seed 80031)
- **claim (lecture d'exécution, non-mécanique)** : les DEUX camps conviennent qu'Actus était un corps EXPENDABLE (engine-INERTE : seul Mechanical de son équipe → DefendTheDivineWork self-only, GalvanicField sans bénéficiaire) et qu'il est mort, mais divergent sur le RÉCIT causal de sa mort. A (about=mine, team1) le lit comme un **free-kill quand Actus s'est over-extendu à row 5** (tué PERMANENT depuis des tuiles SAFE via Sy-gex SentinelDirectives HeavyGravCannon ~5690 + Snappa, zéro exposition côté A). B (about=mine, team2, owner d'Actus) le lit comme un **trade DÉLIBÉRÉ** : « spent it forward to kill Ulf — the only hero-side body I lost, a worthwhile trade ». 
- **divergence A/B** : PAS une contradiction de FAIT (Actus est mort forward, et il a participé au kill d'Ulf T5 avant de tomber au tour suivant) ni une mécanique — c'est une divergence d'INTERPRÉTATION du même événement : A voit la punition d'une over-extension qu'il a exploitée ; B voit un sacrifice planifié d'un corps inerte pour cracker un engine (Ulf, le counter SavageKiller). Les deux peuvent être vrais simultanément (B a poussé Actus pour tuer Ulf ; A a encaissé le free-kill au tour d'après). 
- **doctrine sous-jacente (consensuelle, pas une H à valider)** : un corps engine-INERTE peut être dépensé forward pour un kill de valeur (Ulf = counter critique) — c'est un trade acceptable QUAND on est déjà up un corps (note adversariale de B : ç'aurait été plus risqué contre une tourelle Overwatch non-spent). Côté adverse, un engine-inerte qui s'over-extend = free permanent-kill depuis le shallow (A, correct). Aucune action requise : les deux lectures sont cohérentes, juste asymétriques par perspective.
- **evidence** : seed 80031 — A mistakes/key_decisions (Actus « killed it PERMANENTLY for FREE from safe tiles when it over-extended to row 5 ») vs B key_decisions (« Demoted Actus's repair-engine to expendable ... and spent it forward to kill Ulf — the only hero-side body I lost, and a worthwhile trade »). cf. selfplay-journal seed 80031 (ts 2026-06-23-b6, divergence #1). (self-play divergence A/B — lecture d'exécution, non-mécanique)

## H76 — PutridExplosion (Toxic) compte comme la « 1ʳᵉ attaque du tour » sur une cible TerminatorArmour → réduite −75% ET CONSOMME cette réduction (les hits suivants du tour landent plein) — `provisoire` (pour:1 contre:0, recoupé gameconfig = plausible) (self-play candidate, observateur unique A — seed 80000 ts=b7)
- **claim (candidate mécanique)** : quand Pestillian (Resilient+Explodes) meurt adjacent à un porteur de `TerminatorArmour` (Arjac), son `PutridExplosion` (Toxic, 25% maxHP) frappe Arjac et **se comporte comme la 1ʳᵉ attaque du tour subie** par Arjac → réduite −75% par TerminatorArmour (chip ~527 observé au lieu du plein), MAIS **consomme la réduction** : les attaques suivantes du même tour sur Arjac landent à plein. A (about=mine/theirs, high) l'exploite délibérément : tuer Pestillian au RANGE → l'explosion friendly-fire chipe l'Arjac ennemi GRATIS ET « brûle » sa première-réduction → l'overkill suivant (Exitor OptimizedGait + drone) traverse sans la réduction.
- **recoupage gameconfig (= plausible)** : `--trait TerminatorArmour` = « The first attack each turn deals −75% Damage. Hits dealing Psychic or Direct Damage are excluded. » → **Toxic n'est PAS exclu** (seuls Psychic/Direct le sont) donc l'explosion Toxic EST un candidat légitime à « la 1ʳᵉ attaque réduite » ET la consommerait pour le tour. Mécaniquement cohérent. La règle discrète (l'explosion = un « attack event » qui compte comme la 1ʳᵉ et burn la réduction) n'est PAS explicitement dans i2 → plausible, non confirmé.
- **divergence A/B** : observateur UNIQUE — A rapporte l'interaction (et l'exploite), B (owner de Pestillian/Arjac) ne cross-observe PAS le détail TermArmour-consumption (mentionne juste l'Explodes comme deterrent forward). Pas une contradiction, juste non-corroboré côté B.
- **lien** : adjacent à H48 (TerminatorArmour −75% sur le 1er HIT vs 1ʳᵉ attaque-event) — H76 porte sur QUEL event compte comme la 1ʳᵉ attaque (une explosion friendly-fire/DoT-style le peut) et sur la CONSOMMATION par-tour, pas sur le hit-vs-event d'un multi-hit. À valider ensemble : mesurer l'ordre des hits (explosion d'abord = réduite + suivants pleins vs explosion après une attaque = pleine).
- **doctrine d'ici-là (si plausible)** : contre un mur Resilient+TerminatorArmour, **séquencer une explosion/DoT Toxic AVANT le coup létal du tour** pour brûler la 1ʳᵉ-réduction du porteur → l'overkill landé après traverse plein. Weaponiser l'Explodes ennemi (le tuer au range adjacent à leur propre TermArmour-anchor) = chip GRATIS + burn-réduction.
- **evidence** : seed 80000 (ts=b7, team1 W) — A mechanics PutridExplosion (« chipped adjacent enemy Arjac 527, reduced by Arjac's TerminatorArmour, which it also consumed ») + synergies (« killing Pestillian at range let its explosion chip Arjac and burn Arjac's TerminatorArmour reduction »). gameconfig TermArmour (Toxic non-exclu) = plausible. cf. selfplay-journal seed 80000 (ts=20260625-b7, consensus/divergence #1). (self-play candidate, observateur unique A — recoupé gameconfig)

## H77 — Hex En Feu = dmg START-OF-TURN (DoT-class, Effect_Type=5) confirmé live (~142 sur une unité parquée sur un hex en feu au début de son tour) — `provisoire` (pour:1 contre:0, observateur unique B) (self-play candidate — seed 80003 ts=b7)
- **claim (candidate mécanique)** : un hex En Feu (posé par `PsychicStalk`/Doombolt fire-setting / `FlamesOfMutation` / `EnvFireTileDamage`) inflige un **dmg au DÉBUT du tour** de l'unité qui s'y tient (Effect_Type=5 = classe DoT, distincte du dmg d'attaque/overwatch). B (Player B, team2) a observé un `EnvFireTileDamage` Ability_Power frapper Bellator pour **~142 au turn-start** → confirme que les hex-fire tickent en début de tour. Pertinent pour le scaling `Doombolt` (+1 hit/hex En Feu) et le fire-setting des Psykers (PsychicStalk).
- **divergence A/B** : observateur UNIQUE (B, confidence med). A ne cross-observe pas ce tick (n'a pas de fire-setter dans son roster ce match). NON cross-validé → candidat.
- **recoupage** : cohérent avec le wiki §3bis Ahriman (`Doombolt` +1 hit/hex En Feu) + §3ter Blue Horror (`FlamesOfMutation` met le hex En Feu) — la MÉCANIQUE de fire-hex existe, mais le **tick start-of-turn** (montant + timing) n'est pas explicitement chiffré en gameconfig (effet moteur tile, pas d'i2 source de montant). Le ~142 = valeur live non-load-bearing.
- **à valider** : sur n>1, lire l'`UnitDamaged` Effect_Type=5 d'un hex-fire au début du tour d'une unité qui s'y tient → confirmer le timing start-of-turn + le scaling du montant (% maxHP ou fixe). Si confirmé n≥2 → inscrire au wiki §3quater terrain (« hex En Feu = DoT start-of-turn, éviter d'y parker »).
- **evidence** : seed 80003 (ts=b7) — B mechanics[EnvFireTileDamage, about:theirs, confidence:med] (« an EnvFireTileDamage Ability_Power hit Bellator for ~142 at a turn start (Effect_Type=5, DoT-class) — confirms on-fire hexes deal start-of-turn damage »). A ne cross-observe pas. gameconfig : fire-hex mécanique présente (Doombolt/FlamesOfMutation) mais le tick start-of-turn non chiffré (effet moteur tile). cf. selfplay-journal seed 80003 (ts=20260625-b7, divergence #1). (self-play candidate, observateur unique B)

## H78 — LordOfTempests (Njal) = engine secondaire Ice→normal-buff : Stormcaller pose de l'Ice → les NORMALES de Njal deviennent énormes sur une cible Iced (+237/hex d'Ice) — `provisoire` (pour:1 contre:0, observateur unique B, recoupé gameconfig = plausible) (self-play candidate — seed 80004 ts=b7)
- **claim (candidate mécanique)** : la vraie valeur de `Stormcaller` (Njal) n'est PAS le hit Stormcaller lui-même (dmg modeste, ~1695 réel = 3x ~540 Psychic) mais le **setup Ice** : Stormcaller couvre la cible+adjacents d'Ice → `LordOfTempests` fait que les **attaques NORMALES de Njal infligent +237 dmg par hex d'Ice qui l'entoure** → une normale de Njal sur une cible Iced devient near-K! (B a observé un Njal-normal vs Iced Godswyl à **6055 K!**). L'enchaînement Stormcaller(pose Ice)→normale(buffée par LordOfTempests) est donc un ENGINE secondaire distinct du dmg direct de Stormcaller.
- **divergence A/B** : observateur UNIQUE (B, Player B team2, owner de Njal, conf **high**). A (team1) ne cross-observe PAS l'enchaînement (Njal a peu agi côté A, A n'a jamais subi le combo Ice→normale ; A ne mentionne Njal que comme grindy via TerminatorArmour). NON cross-validé live → candidat.
- **recoupage gameconfig (= plausible)** : `--ability LordOfTempests` = verbatim « Njal's normal attacks deal +237 Damage for each hex surrounding him that is covered in Ice. The hex of each enemy that is hit by Njal's normal attacks is covered in Ice at the end of the attack. » + `--ability Stormcaller` (« The target's hex and all adjacent hexes get covered in Ice »). → la RÈGLE des deux abilities EST confirmée ; ce qui est non-cross-observé = l'usage comme ENGINE (Stormcaller-feed → normale-buff comme axe de dmg principal de Njal, pas juste le Stormcaller-hit) et le montant live ~6055 (non-load-bearing, = scaling level/Ice-count).
- **à valider** : sur n>1, lire une normale de Njal après un Stormcaller (compter les hexes d'Ice autour de Njal vs le +dmg observé) ; confirmer que le buff scale par-hex-d'Ice ET que Njal lui-même se met DANS l'Ice (l'Ice est posé sur la cible+adjacents, pas autour de Njal — vérifier si Njal doit être ADJACENT à des hexes Iced pour bénéficier, ce qui contraint le positionnement). Si confirmé n≥2 → inscrire au wiki §3bis Njal (« LordOfTempests : le vrai dmg de Njal = sa NORMALE sur une zone Iced, pas Stormcaller ; positionner Njal entouré d'Ice »).
- **doctrine d'ici-là (si plausible)** : contre un Njal ennemi, **nier les hexes Iced** = ne pas parker une unité dans/adjacent à une zone Ice où Njal pourrait la normaler buffé ; si je contrôlais Njal, séquencer Stormcaller (pose Ice) PUIS une normale sur une cible dans l'Ice pour le burst +237/hex.
- **evidence** : seed 80004 (ts=b7, team1 W) — B mechanics[Stormcaller, about:mine, confidence:high] (« Predicted damage WILDLY inflated in plans (4918-5884, actually 1695) ; Lays Ice on target+adjacent ; LordOfTempests then makes Njal's NORMAL attacks huge on Iced targets (Njal normal vs Iced Godswyl showed 6055 K!). The real value is the Ice→normal-attack buff, not the Stormcaller hit itself. »). A ne cross-observe pas. gameconfig --ability LordOfTempests|Stormcaller = règle confirmée (engine-usage non cross-observé). cf. selfplay-journal seed 80004 (ts=20260625-b7, divergence #1). (self-play divergence A/B — observateur unique B, recoupé gameconfig)

## H79 — `DeathFromAbove` (Bellator) compte le ROUND-INTERNE écoulé, PAS le tour AFFICHÉ : à tour affiché 5 (round-interne ~3) seulement ~2 Inceptors summonés, pas 5 — `provisoire` (pour:1 contre:0, observateur unique A, recoupé gameconfig = plausible) (self-play candidate — seed 80002 ts=b7)
- **claim (candidate mécanique)** : `DeathFromAbove` summon « 1 Inceptor par round COMMENCÉ » mais le décompte utilise le **compteur de round INTERNE du moteur**, PAS le numéro de tour affiché par la vue. A (Player A, team1, owner de Bellator) a observé qu'au **tour affiché 5** le cast n'a donné que **~2 Inceptors** (round-interne ~3), pas 5 → le scaling est sur les rounds-moteur écoulés, désynchro du header `tour N`. Pertinent pour le timing : un commit Bellator tardif rapporte MOINS d'Inceptors que le tour affiché ne le suggère.
- **divergence A/B** : observateur UNIQUE (A, conf high). B (team2, owner du counter-package) n'a PAS cross-observé le décompte — B a observé que le **STUN Foehammer a COUPÉ le flood** (DeathFromAbove indispo après T5), pas le ratio round/tour. NON cross-validé → candidat.
- **recoupage gameconfig (= plausible)** : `--ability DeathFromAbove` = verbatim « Summons 1 Inceptor for each round that has started » → la RÈGLE (1/round) est confirmée ; ce que A précise = le « round » est le round-MOTEUR, désaligné du header `tour` (qui est lui-même figé/non-fiable, cf. TF14/TF03). Cohérent : le wiki §3ter Inceptor dit déjà « 1 par round démarré, plafonné par les hexes adjacents libres » — le plafond hex (cluster serré) PEUT AUSSI expliquer les 2-au-lieu-de-N (si peu d'hexes libres autour de la cible). DEUX causes plausibles non démêlées (round-interne bas VS plafond-hex).
- **à valider** : sur n>1, logger le round-MOTEUR réel (pas le header) au moment d'un cast DeathFromAbove + compter les hexes libres adjacents à la cible vs le nb d'Inceptors spawné → démêler round-interne-bas (claim A) vs plafond-hex (cause connue §3ter). Si round-interne confirmé n≥2 → noter au wiki §3ter Inceptor (« le scaling suit le round-MOTEUR, pas le header tour ; un commit tardif rapporte moins que le tour affiché »).
- **doctrine d'ici-là (si plausible)** : ne PAS compter sur N Inceptors « parce que c'est le tour N » ; committer Bellator quand le round-MOTEUR est haut ET la cible a des hexes adjacents libres (cluster ouvert), pas serré.
- **evidence** : seed 80002 (ts=b7, team2 W) — A mechanics[DeathFromAbove, about:mine, confidence:high] (« Summons '1 Inceptor per round STARTED' but uses the INTERNAL round counter, NOT the displayed turn number — at displayed turn 5 (internal ~round 3) it gave only 2 Inceptors, not 5. Inceptor damage NOT shown in the attack-plan prediction. »). B ne cross-observe pas (a observé le stun coupant le flood). gameconfig --ability DeathFromAbove = règle 1/round confirmée ; round-interne-vs-header + cause plafond-hex non démêlés. cf. selfplay-journal seed 80002 (ts=20260625-b7, divergence #1). (self-play candidate, observateur unique A)

## H80 — `Daemon` block (Azkor) a HALVÉ un BloodyFury (4222→2111 exact) ET empêché le plancher Resilient de trigger (total dmg < PV courant → pas de floor, juste chip) — `provisoire` (pour:1 contre:0, observateur unique A, recoupé gameconfig = plausible) (self-play candidate — seed 80002 ts=b7)
- **claim (candidate mécanique)** : le trait `Daemon` (chance de block extra) a réduit un hit `BloodyFury` (Wrask) sur Azkor de telle sorte qu'Azkor 4222 PV s'est retrouvé à **exactement 2111** (≈ moitié) — le block Daemon a **halvé** le hit, et comme le total-dmg restait **< PV courant**, le plancher Resilient n'a **PAS** triggé (pas de clamp à 1 PV, juste du chip). Conséquence doctrine : vs un porteur Daemon-block, **budgéter ~2× le dmg** pour réellement finir (le block peut halver un coup qu'on croyait létal → laisse la cible à mi-PV au lieu de la flooorer/tuer).
- **divergence A/B** : observateur UNIQUE (A, conf med). B (owner d'Azkor) n'a PAS cross-observé l'interaction block-Daemon (B a juste compté Azkor comme Resilient-anvil survivant). NON cross-validé → candidat.
- **recoupage gameconfig (= plausible)** : `--trait Daemon` = block chance supplémentaire (mécanique présente) ; le « exactement la moitié » (4222→2111) est probablement un artefact de roll/arrondi du block, PAS une règle « halve » garantie — le montant exact est non-load-bearing (live). Le point structurel (Daemon-block peut absorber/réduire un hit attendu létal → le plancher Resilient ne trigge que si le total-dmg ≥ PV courant) est cohérent avec les règles connues (Resilient = clamp à 1 SI un hit aurait tué ; un dmg réduit sous le seuil = juste du chip).
- **à valider** : sur n>1, lire l'`UnitDamaged` d'un coup attendu-létal sur un porteur Daemon → vérifier si le block réduit le total sous PV-courant (pas de floor) vs un Resilient pur (floor à 1). Démêler « Daemon halve systématiquement » (improbable) vs « block proc partiel qui a réduit ce coup-ci ». Si confirmé n≥2 (le block-Daemon empêche régulièrement le floor d'un coup attendu létal) → wiki §1 traits (« vs Daemon-block, budgéter ~2× dmg : le block peut réduire un hit létal sous le seuil → ni floor ni kill »).
- **doctrine d'ici-là (si plausible)** : vs un carry Daemon-block (Azkor), ne PAS compter un kill « pile aux PV » — sur-budgéter (~2× ou un hit de marge) pour que même un block proc reste létal, sinon on laisse la cible à mi-PV (snowball carry survivant = danger).
- **evidence** : seed 80002 (ts=b7, team2 W) — A mechanics[Daemon block (Azkor), about:theirs, confidence:med] (« Wrask BloodyFury on Azkor at 4222 left it at exactly 2111 (~half) — Daemon's extra block chance halved the hit and prevented the Resilient floor from triggering (total dmg < current HP → no floor, just chip). Budget ~2x damage vs Daemon-block carriers to actually finish. »). B ne cross-observe pas. gameconfig --trait Daemon = block-chance présent ; « exactement moitié » = artefact de roll non-load-bearing. cf. selfplay-journal seed 80002 (ts=20260625-b7, divergence #2). (self-play candidate, observateur unique A)

## H81 — `Suppressed` BLOQUE l'activation de l'ability ACTIVE de la cible (généralise : BasiliskBarrage/Thaddeus MoW « pinned » ne re-tire pas SA barrage ; ExemplarOfHate-Suppress sur Abraxas Chaos → ne cast jamais MasterOfTheTutelaries) — `provisoire` (pour:2 contre:0 ; 2 sources Suppress distinctes mais seed 80001 = observé-1-side, seed 81003 = INFÉRÉ-2-sides/confondu ; suppress-applies recoupé gameconfig, blocks-own-active NON confirmable via gameconfig — effet moteur-only) (self-play candidate — seeds 80001/81003)
- **claim (candidate mécanique)** : le `BasiliskBarrage` (Thaddeus MoW) applique `Suppressed` à tout ennemi touché (trait `SuppressiveFire`) ; B rapporte que son T1 barrage sur le Thaddeus mirror (6525→75 + suppress) l'a laissé « pinned at 75 the whole game, never fired its barrage again » → donc `Suppressed` ne serait PAS qu'un malus dmg/move/stop-Overwatch (sémantique wiki actuelle), mais **bloquerait aussi l'ACTIVATION de la barrage de la cible** (la propre ability ranged suppressée ne re-tire pas). Conséquence doctrine (si vrai) : dans un matchup MIRROR MoW, **suppress le Thaddeus adverse T1 = le neutraliser durablement** (pas qu'un chip — il ne re-fire plus son artillery), sans avoir à le tuer.
- **divergence A/B** : observateur UNIQUE (B, about:mine, conf high). A ne cross-observe PAS le blocage (les 2 MoW étaient sur des camps OPPOSÉS et A possédait SON propre Thaddeus, non suppressé) → divergence d'information, non cross-validable ce match.
- **recoupage gameconfig (= partiel)** : `--trait SuppressiveFire` confirme « An enemy hit by this unit's ranged attack becomes Suppressed » (la RÈGLE — suppress APPLIQUE — est verbatim). MAIS l'effet `Suppressed` est **moteur-only** (`gameconfig --effect Suppressed` = « effet moteur — pas d'ability/trait source ni description i2 ») → la SÉMANTIQUE exacte du Suppressed (réduit dmg/move/Overwatch SEULEMENT, OU bloque AUSSI l'activation d'ability) est **non-déductible de gameconfig/i2**. Donc : suppress-applies = CONFIRMÉ ; blocks-own-barrage = **plausible non-confirmable** (live-only).
- **à valider** : sur n>1 (ou via un replay seed 80001), lire l'état d'un MoW suppressé sur plusieurs tours → vérifier si la barrage est listée castable (abilities/reason) mais no-op, OU explicitement bloquée par le `Suppressed`. Démêler « le MoW suppressé est resté à 75 parce que SuppressiveFire bloque sa barrage » vs « il a juste choisi/échoué à re-tirer pour une autre raison (move-gate, repositionnement, AI) ». Si confirmé n≥2 (Suppressed bloque l'activation de la barrage du porteur) → enrichir wiki §3bis Thaddeus (« suppress le MoW mirror = le neutraliser sans le tuer ») + §6 sémantique Suppressed.
- **doctrine d'ici-là (si plausible)** : en MIRROR MoW (2 Thaddeus), ouvrir le barrage T1 sur le Thaddeus adverse clusteré — non seulement le chunke mais le `Suppressed` paraît le pin (ne re-fire plus) → neutralisation durable à exposition zéro ; ne pas dépenser un 2ᵉ tour à le finir tant qu'il reste suppressé/low.
- **evidence** : seed 80001 (ts=b7, team1 W) — B mechanics[BasiliskBarrage, about:mine, conf high] (« SuppressiveFire trait pins/suppresses everything it hits ; enemy mirror Thaddeus stayed pinned at 75 all game, never fired its barrage again »). A ne cross-observe pas (camps MoW opposés). gameconfig --trait SuppressiveFire = suppress-applies verbatim ; --effect Suppressed = moteur-only (sémantique non-i2). cf. selfplay-journal seed 80001 (ts=20260625-b7, divergence #1). (self-play candidate, observateur unique B)
- **evidence (n+1 convergent 2ᵉ SOURCE, seed 81003, ts=b9, team2 W)** : DIFFÉRENTE source de Suppress (ExemplarOfHate
  d'Asmodai, pas BasiliskBarrage) + DIFFÉRENTE victime (Abraxas/`MasterOfTheTutelaries`, pas un MoW) → MÊME symptôme :
  Abraxas Chaos suppressé (A theirs : `ExemplarOfHate_Target` + Pinned + suppression observés) n'a JAMAIS casté son
  summon-engine ensuite (B mine : « Suppress-blocking-the-cast is inferred »). ⚠ INFÉRÉ par les 2, observé directement
  par AUCUN, et **fortement CONFONDU** (Abraxas a aussi été focus-killé rapidement APRÈS le mark + historique du quirk
  spawn-tile TF12 sur MasterOfTheTutelaries) → support FAIBLE mais CONVERGENT (la généralisation « Suppressed bloque
  l'activation d'un actif » tient sur 2 sources/2 victimes distinctes). À valider : un replay où l'unité suppressée
  SURVIT plusieurs tours + a un hex de spawn legal → l'actif est-il listé castable (abilities/reason) mais no-op, OU
  explicitement bloqué par Suppressed ? cf. selfplay-journal seed 81003 (ts=b9). (self-play candidate, 2 sides inféré/confondu)

## H82 — Les crits `ActOfFaith` (Vindicta) BYPASSENT l'armure (MkXGravis double-armure) → seraient le mécanisme qui a tué Calgar — `provisoire` (pour:1 contre:0, observateur unique B, NON recoupable gameconfig) (self-play divergence A/B — divergence de CAUSE, seed 81001)
- **claim (candidate mécanique)** : B (team2 PERDANT) attribue la mort de son tank Calgar (`MkXGravis` double-armure) aux **crits `ActOfFaith` de Vindicta qui bypassent l'armure** pendant le cluster-wipe T-alpha — « ActOfFaith crits BYPASS armour and ramp on each kill ; the crit-snowball is what killed my tank Calgar ». Conséquence doctrine (si vrai) : un tank double-armure (MkXGravis) n'est PAS safe forward face à une Sisterhood `ActOfFaith` une fois le crit-snowball lancé → tuer Vindicta TÔT (soft 7029) pour nier le snowball, ne pas trust le double-armure comme mur.
- **divergence A/B** : observateur UNIQUE (B, about:mine, conf high). A (team1 VAINQUEUR, owner de Vindicta) ne crédite JAMAIS `ActOfFaith` — A attribue la mort de Calgar à un grind **Power/Flame + Foehammer-stun focus** (« Power/Flame ground it down despite MkXGravis ; lost my Psychic so no clean armour-bypass ; killed T4 ») et Vindicta est morte tôt côté A (pas de snowball réalisé dans son récit). → désaccord de CAUSE sur le MÊME kill (crit-bypass-armure de B vs grind-Power/Flame de A).
- **recoupage gameconfig (= partiel/négatif)** : `--trait ActOfFaith` = « +crit chance / +crit dmg à chaque mort/kill d'un Imperial ami ; reset au 1ᵉʳ crit » (le crit-ramp est verbatim) MAIS NE dit RIEN d'un bypass d'armure par les crits → le volet « crits bypass MkXGravis double-armure » est **non-déductible de gameconfig/i2** (claim moteur-only). Le crit-ramp APPLIES = confirmé ; crit-bypasses-armour = **plausible non-confirmable** (live-only).
- **à valider** : sur n>1 (ou replay seed 81001), lire la cascade de dmg sur un tank MkXGravis frappé par un crit Vindicta → le hit ignore-t-il l'armure (dmg ≈ no-armor) OU est-il juste un gros chunk armuré ? Démêler « Calgar mort au crit armor-bypass ActOfFaith (B) » vs « Calgar grindé par Power/Flame + Foehammer-stun (A) ». Si confirmé (crit ActOfFaith bypass armure) → enrichir wiki §3 Vindicta (« crit-snowball = anti-tank double-armure, tuer tôt »).
- **doctrine d'ici-là (si plausible)** : vs une Sisterhood `ActOfFaith` (Vindicta), ne PAS trust un tank double-armure (MkXGravis) comme mur forward une fois des Imperials morts/kills accumulés (crit-snowball armé) → tuer Vindicta tôt (soft 7029) OU garder le tank hors de sa portée crit.
- **evidence** : seed 81001 (ts=b9, team1 W) — B mechanics[ActOfFaith, about:theirs, conf high] + B mistakes (« Trusted Calgar's MkXGravis ... but Vindicta's ActOfFaith crits BYPASS armour and ramp on each kill ; should have killed Vindicta earlier »). A ne crédite PAS ActOfFaith (attribue Calgar à Power/Flame + Foehammer-stun ; Vindicta morte tôt). gameconfig --trait ActOfFaith = crit-ramp verbatim, AUCUN bypass-armure mentionné. cf. selfplay-journal seed 81001 (ts=b9, divergence D2). (self-play candidate, observateur unique B)

## H83 — Actus (`admecManipulus`) N'EST PAS un repair-engine structurellement INERTE « car SEUL Mechanical » : `DefendTheDivineWork` répare TOUT allié adjacent (pas Mechanical-only) et `GalvanicField` trigge sur la réparation d'une AUTRE unité → l'inert-ness OBSERVÉE était SITUATIONNELLE (pas d'allié adjacent vivant à réparer), pas structurelle — `réfuté (cause)` (pour:0 contre:1, claim B contredit par gameconfig, A ne cross-observe pas) (self-play divergence — claim B vs gameconfig, seed 81002)
- **claim (candidate, RÉFUTÉ sur la cause)** : B (team2 VAINQUEUR, owner d'Actus) traite Actus en repair-engine INERTE et le demote en soft body « car SEUL Mechanical de son roster → `GalvanicField` n'a aucun bénéficiaire valide → ne peut que self-repair 4365 » (application de la règle engine-inerte miroir H02 / Thoread §3).
- **divergence** : observateur UNIQUE (B, about:mine). A (owner adverse) ne cross-observe PAS les mécaniques internes d'Actus (le liste juste « DefendTheDivineWork repair + GalvanicField »). NON cross-validé.
- **recoupage gameconfig (= CONTREDIT la cause)** : `--ability DefendTheDivineWork` = « Repairs himself and all friendly ADJACENT units 4365 Health » (AUCUNE restriction Mechanical → répare n'importe quel allié adjacent) ; `--ability GalvanicField` = « Whenever Actus repairs ANOTHER unit, that unit immediately attacks… max 4365/hit » (trigge sur la réparation d'une AUTRE unité, PAS sur le self-repair). Donc Actus PEUT armer GalvanicField en réparant un allié adjacent vivant → il n'est PAS structurellement inerte du fait d'être le seul Mechanical. L'inert-ness OBSERVÉE ce match était SITUATIONNELLE : ses alliés (all-mêlée) étaient morts/forward/non-adjacents au backline Actus → aucun allié adjacent vivant à réparer → seul le self-repair (qui ne trigge PAS GalvanicField) restait. Le wiki §3bis Actus documente déjà correctement « répare self + adjacents ET via GalvanicField chaque unité réparée fait une attaque gratuite » (cohérent gameconfig, INCOHÉRENT avec le « sole-Mechanical-inert » de B).
- **doctrine** : NE PAS appliquer la règle engine-inerte « sole-Mechanical » à Actus (≠ Thoread UnbreakableDuty qui exige VRAIMENT 2+ Imperials morts, conditionnel structurel). Pour neutraliser Actus, raisonner POSITION (le couper de ses alliés adjacents réparables / heal-block) et focus en UN tour (self-repair 4365 ⇒ alpha mono-tour), PAS « il est inerte donc soft body ».
- **evidence** : seed 81002 (ts=b9, team2 W) — B threat_cards[Actus, role:engine, threat:low] (« INERTE repair-engine : sole Mechanical → can only self-repair, GalvanicField has no valid beneficiary ») + B mechanics[Actus self-repair, conf high]. A ne cross-observe pas. gameconfig --ability DefendTheDivineWork (répare TOUT adjacent) + --ability GalvanicField (trigge sur repair d'autrui) CONTREDISENT la cause structurelle. cf. selfplay-journal seed 81002 (ts=b9, divergence D1). (self-play — claim B contredit par gameconfig)

## H84 — Le tueur EXACT d'Azrael (seed 81004, T4) : `HammerOfWrath` doublé de Mataneo SEUL (A) vs Mataneo CHUNK + Godswyl `ChampionOfTheFeast` FINISH non-overkill → FJ (B) — `attribution divergente` (B owner des attaquants = meilleure visibilité ; règle FJ-non-overkill sous-jacente DÉJÀ wiki-cohérente, PAS une contradiction de mécanique) (self-play divergence A/B, seed 81004)
- **claim (attribution divergente, PAS une mécanique nouvelle)** : désaccord sur QUI a porté le coup fatal à Azrael (darkaAzrael, team1) au T4. A (owner d'Azrael = la VICTIME, conf high) : un `HammerOfWrath` **DOUBLÉ** de Mataneo SEUL l'a one-shot (« doved alone T4, killed my Azrael with a doubled hammer », après que le propre chip d'A ait laissé Mataneo à 4488 <50%). B (owner des DEUX attaquants Mataneo+Godswyl, conf high) : Mataneo `HammerOfWrath` a seulement **CHUNK** Azrael, PUIS Godswyl `ChampionOfTheFeast` (passif move-triggered, **2085, NON-overkill**) a délivré le **FINISH** → ce qui a FAIT fire la `FinalJustice` d'Azrael ; le `ThunderousAssault` suivant a no-op sur le cadavre.
- **divergence A/B** : désaccord de CAUSE/attribution sur le MÊME kill, pas de contradiction de règle. B a la meilleure visibilité (owner des 2 attaquants + connaît le dmg exact de ChampionOfTheFeast + voit la FJ fire) ; son récit est cohérent avec (i) l'OW de Maugan Ra qui a chunké Godswyl 9539→49 PENDANT que Godswyl bougeait pour finir Azrael, et (ii) `ChampionOfTheFeast` qui EST move-triggered (cf. wiki §3bis Godswyl) → un finish via ce passif APRÈS un move colle. A a vraisemblablement conflé le chunk-hammer avec le finish réel.
- **recoupage gameconfig (= cohérent, PAS de nouvelle règle)** : `--ability ThunderousAssault` = always-overkill (sur SON kill) ; `--ability ChampionOfTheFeast` = passif move-triggered, 1 hit Power + −armure permanent (AUCUN « always-overkill »). Donc un kill via ChampionOfTheFeast (non-overkill) **déclenche** FinalJustice là où ThunderousAssault (overkill) la **supprimerait** — exactement la règle DÉJÀ inscrite wiki §1 (« kill EXACT non-overkill déclenche FJ » [self-play consensus seed 80072]). Le récit de B RE-CONFIRME cette règle plutôt qu'il n'en propose une nouvelle.
- **à valider** : sur replay seed 81004, lire la cascade T4 sur Azrael → quel event porte le `WasOverkilled=0`/FJ-fire (HammerOfWrath de Mataneo, ou un hit ChampionOfTheFeast `Thorns_DefenseReduction` de Godswyl ?). Démêler « Mataneo doubled-hammer one-shot (A) » vs « Mataneo chunk + Godswyl ChampionOfTheFeast finish (B) ». Pas de doctrine nouvelle en jeu (les deux abilities sont déjà wiki-documentées) — c'est une vérif d'attribution.
- **evidence** : seed 81004 (ts=b9, team1 W) — A synergy[Mataneo HammerOfWrath <=50% double, status:triggered-against-me] + A threat_card[Mataneo : « killed my Azrael with a doubled hammer »] vs B mechanics[ThunderousAssault, about:mine, conf high : « Azrael's kill actually came from ChampionOfTheFeast (NOT overkill) → FinalJustice FIRED »] + B synergy[Mataneo chunk + Godswyl finish on Azrael, status:chained]. gameconfig --ability ChampionOfTheFeast (non-overkill) cohérent avec FJ-fire. cf. selfplay-journal seed 81004 (ts=b9, divergence D1). (self-play divergence A/B — attribution, règle sous-jacente déjà wiki-cohérente)
