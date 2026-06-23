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

## H22 — TerrifyingCrescendo (Shiron) : un crit étend-il la durée de ThrillSeekers ? — `provisoire` (pour:0 contre:1-i2)
- **claim (à RÉFUTER)** : un retour combat (seed 95001) affirme qu'« un crit d'ExcruciatingFrequencies
  étend la durée de ThrillSeekers ». **NON supporté par i2** : ThrillSeekers se re-trigger PAR TOUR quand
  l'unité subit des dégâts OU cible un ennemi full-HP (+crit while Thrilled, crit-kill = overkill) — il
  n'y a **aucune clause d'extension-de-durée-sur-crit**. Le CORE de TerrifyingCrescendo (+218 dmg ranged
  par Overkill/Suppress, cap 6 = +1308) est i2-confirmé et inscrit au wiki §2 (entrée Shiron) ; SEUL le
  sous-claim ThrillSeekers-extend est douteux.
- **à valider** : observer la durée effective de Thrilled tour après tour (re-trigger par-tour attendu, PAS
  une extension cumulative par crit).
- **evidence** : seed 95001 (n=1, verdict « plausible » sur l'ensemble mais sous-claim ThrillSeekers
  explicitement non supporté par i2). ⚠ ne pas planifier autour d'une « durée étendue ».
  **seed 70009 (INCONCLUSIVE)** : Shiron présent mais tué avant d'observer une durée multi-tours de ThrillSeekers ;
  aucun claim d'extension-sur-crit testable ce match (le sous-claim reste non supporté par i2, ni confirmé ni réfuté ici).

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

## H53 — MV71 Sniper Drone (Sho'syl) a un range minimum ~2 hexes — `provisoire` (pour:1 contre:0) (self-play divergence A/B)
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
