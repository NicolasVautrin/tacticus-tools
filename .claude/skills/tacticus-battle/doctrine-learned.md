# Doctrine apprise — complement a `tacticus-battle` (SKILL §6/§7)

> **Fichier maintenu par le WRITER** (agent de synthese, fin de vague RL). Doctrine
> actionnable APPRISE, qui complete le skill `tacticus-battle` (§6 engagement, §7
> pieges/safety) **sans jamais modifier le `SKILL.md` de base** (cure a la main). Les agents
> combat lisent CE fichier EN PLUS du SKILL §6/§7.
>
> **Cycle de vie d'une lecon** : `hypotheses.md` (provisoire, testee, churne) --[gate]--> ICI
> (active, appliquee en jeu). Le stade « en attente » EST `hypotheses.md` (une H confirmee mais
> sous le gate y reste, flaggee candidate). ICI = uniquement ce qui a passe le gate.

## Regles d'ecriture (pour le writer)

1. Promouvoir ici une hypothese **seulement** si confirmee sur **>=2 matchups DISTINCTS** (pas
   2 combats correles) ET filtre d'inscription (general + verifie + non-derivable). Sous ce
   gate -> elle reste candidate dans `hypotheses.md` (PAS ici).
2. Chaque entree cite sa preuve : `[H## · confirmee N matchups · vague AAAA-MM-JJ]`.
3. Ne pas dupliquer une ligne deja au SKILL §6/§7 ni au wiki ; referencer, pas redefinir.
4. **Ne jamais ecrire dans `.claude/skills/tacticus-battle/SKILL.md`.**
5. Fichier auto-promu donc **audite/elagable a la main** : l'humain peut reformuler, revoquer
   (re-descendre en hypothese dans `hypotheses.md`), ou hisser vers le SKILL de base.

---

## §6 — Engagement / priorisation (appris)

- **Tuer la win-condition d'abord** (summon-engine / reviver / carry) avant le chaff. Vs un duo
  summoner+reviver, cette priorite **prime** sur « punir le dive ». ⚠ **NUANCE (gagner la guerre des
  engines NE suffit pas)** : tuer les engines doit etre **paye avec une exposition forward MINIMALE** —
  depuis les tuiles les plus shallow (back ranged / turret stationnaire), en gardant **au moins un tank
  shallow comme ecran**, et en **pre-evaluant le board POST-engine** (si des briques Resilient durables
  survivent, l'attrition peut etre injouable pour un reliquat fragile). Sinon : engines tues, attrition
  perdue. ⚠ **NUANCE FENETRE/ATTEIGNABILITE** : tuer la wincon suppose qu'elle soit ATTEIGNABLE (engine
  back-row → pre-positionner un dealer ranged T1) ET dans la bonne FENETRE temporelle (un engine a scaling
  exponentiel type Eldryon/Executioner doit mourir AVANT sa phase letale T1-T4, pas seulement « mourir » ;
  vecu seed 96002 : Eldryon tuee T4 a 149 HP = near-miss, 1 tour de plus = board-wipe). ⚠⚠ **REGLE
  D'ATTEIGNABILITE AU RECON (confirmee 3 matchups distincts : 91001, 96001, 97001)** : si l'engine adverse
  (Seeker type Sho'syl, sustain type Hollan/Isabella) reste structurellement INATTEIGNABLE — row 6-9
  derriere un mur melee, et mon roster est melee/r2 SANS reach tool (r3+/deep-strike/flyer) — alors H02
  est INAPPLICABLE : ni un plan d'attrition lent ni un hold defensif ne portent le combat (le sustain-engine
  out-pumpe mes briques statiques). DOCTRINE : VERIFIER l'atteignabilite des engines AU RECON ; si nulle,
  FLAGGER une loss structurelle et abandonner tot (ou jouer un all-in desespere pour cracker le mur) PLUTOT
  qu'un hold lent que le sustain-engine intouchable gagne. ⚠⚠ **REGLE REPAIR-ENGINE (literal, vecu 97002)** :
  vs un **repair-engine** (Actus DefendTheDivineWork 4365 + trait Mechanic, additifs = +5983/tour observe),
  un chip non-letal est **ENTIEREMENT efface** au tour suivant → « kill CE tour ou ne pas committer » est
  LITTERAL : soit le kill securise depuis une tuile shallow, soit le laisser vivre — JAMAIS sur-etendre un
  corps pour le chiper (vecu 97002 : Mataneo deep-commit chasse Actus, chip ~1015 puis Actus re-heale 9285,
  Mataneo stranded → tue = perte nette + engine intact). ⚠⚠ **EXTENSION AUX SUMMON-ENGINES (vecu 70052, L proximate)** :
  la meme regle « kill CE tour ou ne pas committer » est LITTERALE pour un **summon-engine** (Abraxas
  MasterOfTheTutelaries : pas de seuil de PV, tout Abraxas survivant cast → 1 Pink Horror + 1 Screamer par event
  Psychic-Damage = board-flip). Un chip NON-LETAL sur un summon-engine est **strictement pire que le hold** : il ne le
  tue pas ET il lui laisse caster son board-flip (vecu 70052 : Snappa seul 7026→3183 → +Pink Horror +2 Screamers, 5v5→
  effectivement 3v10 avec le focus). DOCTRINE : vs un summon-engine soft, soit un **kill GARANTI ce tour** (multi-source
  depuis tuiles shallow, marge verifiee > HP), soit **HOLD total** pour denier le trigger — JAMAIS un poke a une seule
  source qui ne peut pas one-shot (Snappa r3 max < 7026). ⚠ **CONTRE-EXEMPLE POSITIF (vecu 98004, engine
  ATTEIGNABLE)** : quand l'engine de sustain EST a portee (Healer move2 lent + IA qui avance), H02 PORTE le W —
  Nauseous (deathRotbone Healer-engine) tue T3 via multi-hit overkill (beat Resilient) + HEAL-BLOCK Mephiston
  (FuryOfTheAncients) qui nie son heal/revive 2 rounds AVANT le kill ; ET son revive (TaintedNarthecium 75%
  Chaos) peut etre STRUCTURELLEMENT INERTE si le Healer est le seul Chaos d'un roster mixte (recon le verifier
  au lieu de le craindre). ⚠ **2e CONTRE-EXEMPLE POSITIF (vecu 98002, engines ATTEIGNABLES)** : vs un noyau
  Necron sustain+summon (Anuphet ResurrectionOrb summoner + Aleph-Null FabricatorClaw/Mechanic repair-amplifier),
  les DEUX engines etaient SOFTS (8536/9037 no-Resilient) et move-in (l'IA a dive) → H02 applicable, payee depuis
  des tuiles SHALLOW (Abraxas Psychic r2, TG melee depuis tuile courante, Yazaghor short-hop) en gardant le TG en
  ecran → engines tues T2 AVANT le snowball = le moteur n'a JAMAIS tourne, W 6v0. CLE : briser la SOURCE (summoner
  + repair-amplifier) plutot qu'out-DPS l'output reparte ; finir l'Explodes (Aleph-Null) au RANGE = friendly-fire
  gratis sur leur cluster. ⚠ **3e CONTRE-EXEMPLE POSITIF (vecu 98001, wincon-set ENTIER atteignable)** : vs un roster
  miroir summon/sustain + 3 Psykers (Hollan TwistedScience-pump + Xybia MindControl/Ambush + Abraxas Screamer-cascade)
  amplifie par Kharn carry, j'ai tue l'INTEGRALITE du wincon-set de facon PERMANENTE dans le bon ordre (Kharn chunk+fini
  T2 AVANT son 1er kill ; Xybia 2× + Abraxas via l'assassin anti-Psyker Tjark ; Hollan 2× via Snotflogga ; Gulgortz
  overkille en dernier) pendant que mes engines farmaient → W 6-rounds, mes 4 heros sains. CLE NOUVELLE : quand
  l'engine-set adverse est **Psyker-lourd**, un **assassin anti-Psyker** (Tjark HuntersBeyondDeath, +582/hit vs Psyker +
  aura suppression) EST l'outil de kill-engine dedie — il rend les casters atteignables/tuables proprement (cf. H11) ;
  et un Ambush-engine exige une **2e mort** (premier kill = temp). ⚠⚠ **REGLE ENGINE-INERTE AU RECON (confirmee 2 matchups
  distincts : 98004 revive + 70002 repair)** : un engine d'AMPLIFICATION (repair-hub Mechanical, buff-aura, revive,
  heal-faction-restreint) ne vaut QUE s'il a un **beneficiaire VALIDE sur SON equipe** — un repair-hub (Aleph-Null
  FabricatorClaw/Mechanic) SEUL Mechanical de son roster ne peut que se self-regen = INERTE (vecu 70002 : Brazier l'a
  one-shot 9037→0, son repair n'a jamais eu de cible) ; un revive 75%-Chaos avec 4 allies Imperial = INERTE (vecu 98004).
  DOCTRINE : au recon, COMPTER les beneficiaires valides de chaque engine d'amplification AVANT de le craindre ; s'il n'en
  a aucun, **demote sa menace** (carte wiki CRITICAL → LOW) et traite-le en corps soft normal (kill au RANGE pour Explodes).
  ⚠ **EXTENSION AUX AURAS ANTI-X (vecu 70051) : meme regle, symetrie** — une aura de **suppression/penalite anti-cible**
  (Tjark `HuntersBeyondDeath` = +582/hit vs Psyker + suppression du multi-hit Psyker) ne vaut QUE s'il existe une **cible
  valide** cote adverse : si MON roster n'a **aucun Psyker**, l'aura est ENTIEREMENT INERTE → Tjark reduit a un melee plat
  (8536 PV no-Resilient). DOCTRINE : au recon, **COMPTER mes propres unites de la categorie ciblee (Psyker, Daemon, BigTarget…)
  AVANT de craindre une aura anti-X ennemie** ; s'il n'y en a aucune, demote la carte (CRITICAL/HIGH → LOW) et traite le
  porteur en corps soft. Meme famille que l'engine-inerte sans beneficiaire (un amplificateur ET un suppresseur sont tous
  deux conditionnels a l'existence d'une cible/beneficiaire valide).
  ⚠ **4e CONTRE-EXEMPLE POSITIF (vecu 70002, engines fragiles ATTEIGNABLES)** : vs un roster ou la seule amplification
  (Aleph-Null repair) etait INERTE, j'ai tue les 2 Psyker-engines fragiles (Yazaghor T1, Ahriman ennemi en reaction) + le
  carry autonome Lucien en dernier → W 4v1-dominant. CLE : kill-fragile-Psyker-engines-FIRST quand ils sont softs
  (~6.5-8k no-Resilient) et que l'IA dive → ils tombent T1-en-reaction sans cout. ⚠ **5e CONTRE-EXEMPLE POSITIF
  (vecu 70001, Healer-engine ATTEIGNABLE)** : vs un near-mirror Blood Angels, leur Nicodemus (Healer-engine de sustain,
  no FJ, soft) tue T2 via un Dante chunk (9035→2301) + Jain Zar SilentDeath qui le FINIT ET chunke leur Dante adjacent
  7846→5558 dans le MEME cast → sustain effondre, carry voisin pre-affaibli pour le reaction-kill suivant. CLE NOUVELLE
  (adjacency-AoE engine-finish) : quand un engine de sustain jouxte le carry adverse, le finir avec une AoE adjacency-chain
  (SilentDeath, DoomSiren-class) splash GRATIS le carry → un cast = engine mort + carry chunke ; sequencer APRES un gros
  chunk pour garantir le kill. ⚠ **6e CONTRE-EXEMPLE POSITIF (vecu 70009, carries ATTEIGNABLES → H02 a PORTE le W)** : vs un
  roster focus-carry SANS moteur de pump central (Shiron ranged r3 line-AoE + Tarvakh melee kill-snowball, ecranes par 2
  anvils BigTarget Gulgortz/Kut), j'ai tue les 3 menaces qui escaladent — Tarvakh (snowball carry) chunk-kill AVANT son 1er
  kill (Patermine MightFromBelow Psychic ignore armure + Tanksmasha, dans un burst WarHowl-buffe), Yazaghor (Flying Psyker
  engine) K! outright, Shiron (ranged carry) mopped une fois isole 4v1 — pendant que les anvils BigTarget (puits sans
  amplification) etaient traites en SECONDAIRE. Engines/carries ATTEIGNABLES car l'IA a committe sa melee forward (Tarvakh a
  dive a (3,5)) → contraste avec la serie row-9 inatteignable. NUANCE : un roster « focus-carry sans pump central » est plus
  facile que les compos a engine de pump — tuer les 2-3 carries autonomes (pas les anvils ecran) suffit. ⚠ **NOUVELLE
  CLASSE D'H02-INSUFFISANT (vecu 70008, L) : un tank HIGH-ARMOR STANDALONE devient le wincon late** — j'ai tue PROPREMENT
  les 2 summon-engines evidents ET atteignables (Archimatos one-shot CordClaw T2 pre-summon = zero Possession body ;
  Dreir multi-hit past Resilient+ToughToKill) = guerre des engines GAGNEE, mid-game gagne, MAIS le match perdu a un
  Burchard 12k MkXGravis (double-armure, bypass Crit/Direct/Psychic uniquement) que mon roster Power/Physical residuel
  ne pouvait pas cracker une fois mes outils armor-ignore (Exitor CordClaw + Atlacoya Direct) perdus en over-extension T1.
  Ni reach-fail (engines atteignables et tues) ni self-healer (70004/70005) — c'est un MUR high-armor qui devient
  ingrindable des qu'on perd le bypass-armure. DOCTRINE (meme famille que « reserver l'anti-armor burst » 70004/97002,
  mais le levier = un TYPE de degat) : au recon, identifier un tank MkXGravis comme wincon late emergent ET RESERVER/
  PROTEGER mes 1-2 outils Direct/Psychic/Crit (ne PAS les sur-etendre T1) — tuer les engines evidents NE SUFFIT PAS si
  un tank high-armor reste ingrindable. ⚠ **CONTRE-EXEMPLE POSITIF (vecu 70051, engines+carry ATTEIGNABLES → W)** : vs
  un roster adverse **100% soft (aucun Resilient) ET 100% melee/r2**, l'adversaire DOIT diver → un mur Resilient mien
  (Maladus/Dreir/Lucien) baite le dive et expose chaque engine soft a sa SORTIE → buff-engine Aethana (deep-strike sortie
  FORWARD) + Psychic-nuke Sibyll tues T3, carry Mephiston (LE wincon, Psychic Pierce100 NoBlocking) T4, Healer Nicodemus T5
  = wincon-set demantele dans le bon ordre. INVERSE EXACT des series row-9-inatteignables (96001/97001/70050) : all-soft+
  all-melee vs mur Resilient = engines structurellement ATTEIGNABLES, pas un reach-fail. ⚠ **EXTENSION REGLE
  ENGINE-INERTE AUX MARKERLIGHT-ENGINES (vecu 70056)** : un markerlight-engine (Darkstrider StructuralAnalyser, +728 ranged vs
  cible marquee) ne vaut QUE s'il a un **2e allie RANGED** a feeder — s'il est le SEUL ranged d'une equipe all-melee, l'engine
  est self-fed = INERTE → demote carte high→low, traite-le en corps soft (vecu 70056 : tue dans le dive). Meme famille que
  l'amplificateur sans cible/beneficiaire valide. ⚠ **CONTRE-EXEMPLE POSITIF n+1 (vecu 70056, engine ATTEIGNABLE → W)** :
  Ragnar (spaceBlackmane) = WarHowl-engine, l'amplificateur de toute la ligne melee Character d'un roster 100% melee + 1 ranged,
  identifie comme la wincon SOURCE et tue EN REACTION T2-T3 AVANT son 1er cast WarHowl → la ligne melee n'a JAMAIS ete buffee =
  W 8v alive. Engine ATTEIGNABLE car all-melee CONTRAINT de diver dans mon cluster Overwatch (meme structure que 70051).
  ⚠ **CONFIRME n+1 sur un DOUBLE summon-engine (vecu 70053 W)** : Bellator DeathFromAbove (flood Inceptors croissant) +
  Archimatos Incursion/Possession (amplifies par Abaddon FirstAmongTraitors) ATTEIGNABLES sur le dive d'un roster
  all-melee/move4-Flying/deep-strike → tues dans le bon ordre T4 (Snotflogga K! Archimatos comme VICTIME = ZERO Possession
  body + Aesoth/Calandis K! l'OW-engine Imospekh) avant compounding = W (INVERSE de la serie reach-fail row-9).
  ⚠ **CONFIRME n+1 sur un mur d'attrition all-melee SANS engine central (vecu 70054 W)** : un roster all-melee (Thoread
  −33% aura + TG GuardianOrganism + Corrodius-mirror Resilient screening Deathleaper) n'a AUCUN engine de pump/summon/
  sustain → structurellement plus faible que la classe engine row-9, son mur DOIT closer → kill les fragiles d'abord
  (Yazaghor T3, Deathleaper T4) PUIS overkille les anvils KILLABLES (TG non-Resilient 12548 en UN tour multi-source T5,
  Thoread 10038 T6-T7) = W. ⚠ **EXTENSION REGLE ENGINE-INERTE AUX CONDITIONNELS SCALANTS (vecu 70054)** : un buff
  conditionnel ne vaut que si son DECLENCHEUR peut s'armer dans le matchup — Thoread UnbreakableDuty (+7275HP/+1455dmg si
  2+ Imperial allies morts) INERTE car Thoread = SEUL Imperial de son roster ; Yazaghor WeaverOfFate (max dmg si 3+
  ennemis subissent du Psychic) INERTE car aucune source Psychic ne touche mes propres units. DOCTRINE : COMPTER les
  declencheurs valides d'un conditionnel scalant AU RECON → demote s'il ne peut pas s'armer (meme famille que
  l'amplificateur/aura-anti-X sans cible/beneficiaire). ⚠ **CONTRE-EXEMPLE POSITIF n+1 (vecu 70060 W) : DOUBLE wincon-source
  brisee AVANT amorçage + tank high-armor NEUTRALISE par les nombres** — Kharn (snowball engine TheBetrayer) + Tarvakh (carry
  NON-pumpe) tues EN REACTION dans un mur Overwatch (Re'vas EWO + Sarquael held-OW + Aun'Shi −50% aura) sur leur dive T2 AVANT
  tout kill (TheBetrayer jamais arme = engine mort-ne) ; PUIS summon-engine Abraxas (soft 7026) tue en UN tour T3 via burst
  multi-source GARANTI (Supercharge 6366 + 2 normales > HP verifie) AVANT MasterOfTheTutelaries = kill-not-chip respecte, ZERO
  board-flip. Engines ATTEIGNABLES car all-melee CONTRAINT de diver (structure 70051/70056/70053/70054). NUANCE engine-INERTE
  n+1 DANS MON roster : Nauseous revive (75% Chaos) INERTE car SEUL Chaos de mon equipe (heal 0 aux Imperial) → recon-flagge,
  jamais craint. ⚠⚠ **NUANCE H02-INSUFFISANT-EVITEE (inverse de 70008)** : Burchard MkXGravis (12k, mon roster ZERO Direct/
  Psychic/Crit) = le wincon-late-emergent de classe 70008 — MAIS EVITE en gagnant la guerre des nombres D'ABORD (mur de
  reaction → 2 carries morts T2 zero perte) → Burchard affronte en 6v1 (grind trivial : Nauseous −armure aura + Storm of Fire
  +582 = 12038→1362 en un tour) au lieu d'en dernier mur ingrindable. DOCTRINE confirmee par l'INVERSE de 70008 : un MkXGravis
  standalone n'est ingrindable QUE comme dernier mur apres la guerre des nombres perdue ; overwhelm via nombres/reactions le
  neutralise meme sans bypass-armure. ⚠ **CONTRE-EXEMPLE POSITIF n+1 (vecu 70059 W) : engine ATTEIGNABLE → W, MAIS anvil-kill
  a COUTE un carry** — Ragnar (WarHowl-engine, wincon SOURCE d'un roster all-melee+anvil-heavy) tue T3 AVANT son 1er cast WarHowl
  (chunke T2 Typhus PlagueWind Psychic, fini T3 Psychic) car le bulk CONTRAINT de diver = ATTEIGNABLE (structure 70051/70056/
  70060). NUANCE engine-INERTE n+1 : Abaddon FirstAmongTraitors near-inerte (SEUL allie Chaos = Maladus) → demote, kill last.
  ⚠ **NOUVELLE NUANCE — UN ANVIL-KILLABLE NON-ENGINE PEUT COUTER UN CARRY FORWARD** : tuer le Tyrant Guard (12.5k BigTarget
  NON-Resilient, anvil focusable) en UN tour multi-source (PlagueWind 3154 + DestroyerHive 3369 + Kharn K! 6025) a EXIGE une
  tuile melee forward → mon carry Kharn committe la s'est fait focus-killer (Maladus FlailSwing) = ma seule perte. Distinct du
  contre-exemple 70054 (anvils KILLABLES overkilles sans perte) : ici l'anvil n'etait atteignable QUE par un carry melee au
  front. DOCTRINE : un anvil-killable NON-engine ne vaut PAS un carry forward — preferer tuer l'ENGINE (Ragnar) au range/Psychic
  et LAISSER l'anvil, OU sacrifier le corps le PLUS expendable (pas le meilleur carry) ; H02 sur un anvil (vs un engine soft
  shallow-killable) peut imposer une exposition forward couteuse (cf. nuance 93000 « exposition minimale » + H03 over-extension).
  ⚠ **CONTRE-EXEMPLE POSITIF n+1 (vecu 70058 W) : un ENGINE-PAIR ranged back-row devient ATTEIGNABLE quand son SCREEN melee dive
  et meurt** — la wincon adverse = paire d'engines ranged armor-ignore + delayed-nuke (Njal Psychic NoBlocking AoE + Sho'syl
  SeekerMissile 6184 + MV71 drone-summons), move2 back-row, SCREENEE par 3 melee/Flying. Un reaction-engine HOLD (Sy-gex Overwatch
  r3 turret HELD-arme + Aesoth BigTarget/StandVigil screen + Thaddeus +728 feeding Sy-gex) a CONTRAINT le screen melee a diver →
  reaction-kill du screen (Ulf 4660→0, Titus permanent, Yazaghor ennemi) T2-T3 → les 2 engines back-row exposes et tues dans le
  bon ordre T4 (Aesoth K! Sho'syl le summoner → drones inertes ; stun VexillaMagnifica + Sy-gex 4-hit HeavyGravCannon vs Njal
  TerminatorArmour 6727→0). MEME structure que la serie des dives-forces gagnes (70051/70056/70053/70060) : un roster avec ≥3
  melee/Flying CONTRAINT de diver expose ses engines back-row a la mort de son screen → INVERSE des reach-fail row-9. NUANCE
  engine-INERTE n+1 : Yazaghor ennemi WeaverOfFate INERTE (aucune source Psychic touche mes units) → demote en chaff soft.
  ⚠ **CONTRE-EXEMPLE POSITIF n+1 (vecu 70057 W 5v0) + NOUVELLE VOIE « defang par les beneficiaires »** : wincon-set ENTIER
  ATTEIGNABLE (roster all-melee/deep-strike CONTRAINT de closer dans ma range) → tue dans le bon ordre depuis tuiles SHALLOW :
  Dante (carry deep-strike, LordOfTheHost amplifier) T3, Helbrecht (CrusadeOfWrath buff-engine, OVERKILLE pour denier FJ) T4,
  puis Ragnar (WarHowl engine) + Sarquael (ranged+OW) T5 = engines jamais amplifies (meme structure 70051/70053/70056/70060).
  NUANCE NOUVELLE : un pump-engine (Ragnar WarHowl) ne pump QUE les melee Characters SANS normale ranged → tuer ses BENEFICIAIRES
  (Dante+Helbrecht) AVANT l'engine le DEFANG (Ragnar reduit au self-buff au moment du kill) = 2e voie de neutralisation, par les
  cibles plutot que par la source (a inscrire vs un WarHowl-engine dont les beneficiaires sont plus atteignables que lui).
  Engines screen-on-attack cote MIEN (Sho'syl MV71 drone burst-immediat + Tan Gi'da ControlEdict Vanguard) ont soake ~14k du
  focus ennemi → exposition forward MINIMALE respectee (nuance 93000) sauf 1 slip Tan Gi'da (5,3) non-decisif en 5v0.
  `[H02 · confirmee 27 matchups · 2026-06-17 + 2026-06-19 + 2026-06-20 + 2026-06-21]`
- **Vs un tank `Terrifying`** (Mephiston, Azkor, Atlacoya, Dante, Tjark, Deathleaper) : bypass fiable =
  **RANGED** (Terrifying ne reduit QUE la melee subie). ⚠ l'armor-ignore/perforant/Direct en **melee NE
  bypasse PAS** (ce n'est pas un mecanisme d'armure). Un tank Terrifying tanke un roster majoritairement
  melee a tres bas cout → l'utiliser/le neutraliser en consequence. ⚠ **COROLLAIRE RECON (vecu 97002)** :
  un anvil `Resilient` + `TerminatorArmour` (~12k, ex. Maladus) reduit la 1ʳᵉ attaque melee/tour de −75%
  SAUF Psychic/Direct → un roster **all-melee SANS Psychic/Direct** ne peut PAS le casser (plans 330-954/coup
  observes). Au recon, si mon roster n'a aucun Psychic/Direct et l'adverse aligne un tel anvil + un
  repair-engine, FLAGGER la loss structurelle d'emblee (chip-only = attrition perdue) et jouer un engine-race
  rapide sur les unites softs, sans l'engager. ⚠⚠ **REGLE ANVIL SELF-HEALING RESILIENT (confirmee 2 matchups
  distincts : 97002 repair-engine + 70004 self-heal-engine) — « reserver le burst au recon »** : un anvil
  combinant **Resilient + un self-heal REPEATABLE sur cd** (Trajann MomentShackle heal-to-full ~+5684 tous les
  ~2 tours, PAS once-per-battle) + une reduction des normales (MartialKatah −20%) + ~4249/tour est un MUR que
  tout roster **chip-only** (~2100-3000/tour) ne peut JAMAIS finir : il se heal-to-full plus vite que mon dmg ET
  out-damage mon tank → il devient la **wincon late de facto** une fois les screens tombes (meme apres avoir gagne
  la guerre des engines/dive 4v1). La seule fenetre de kill = un **overkill MULTI-SOURCE en UN tour** pendant que
  le self-heal est en cd, OU un **burst Direct/Psychic** qui bypasse son block (DoomSiren Pierce100). DOCTRINE : au
  recon, IDENTIFIER un tel anvil comme la wincon late d'un roster burst-leger et **RESERVER mon burst anti-block
  (Direct/Psychic) POUR LUI** — ne PAS le dilapider tot sur une cible atteignable. Si mon burst est deja depense/absent
  → FLAGGER la loss structurelle, ne pas grind (vecu seed 70004 L : DoomSiren spent tot → chip-only vs Trajann = loss
  malgre un 4v1 ; meme classe que 97002 ou « kill CE tour ou ne pas committer » est LITTERAL, ici etendu a un
  Resilient+self-heal). ⚠ COROLLAIRE ANTI-REVIVE (vecu 70004) : un carry `FuelledByFury`/`FinalJustice` (Titus) meurt
  PERMANENT si on le finit avec UNIQUEMENT des corps high-HP adjacents — sa riposte FJ frappe un tank qui survit = pas
  de kill = pas de revive ; ECARTER tout fragile/bas-PV de l'adjacence avant le coup fatal (cf. wiki §3bis Titus). ⚠ **VOLET ANTI-PSYKER (vecu 98001) — autre « bypass de mecanisme
  defensif »** : Tjark `HuntersBeyondDeath` = +582 PAR HIT vs Psyker + aura de suppression (−582 dealt) sur les
  Psykers ennemis dans 2 hex → c'est l'assassin de casters dedie vs un engine-set Psyker-lourd (Xybia/Abraxas/
  Archimatos-class) : K!'d Xybia (8514) outright + chunke Abraxas 7026→784 en un hit (~6242). DOCTRINE : router
  l'anti-Psyker sur les casters Psyker ennemis (= kill-engine, cf. H02) ; l'aura blunte aussi les survivants.
  ⚠ **2e OUTIL ANTI-PSYKER (vecu 70002, 2e matchup distinct) : Roswitha (adeptCanoness) CondemnorStake = +2183 dmg vs
  Psyker** → meme FAMILLE « bypass-via-anti-tool dedie » que Tjark : Roswitha devient un assassin de Psykers (a pose le
  free 4551 KILL sur l'Ahriman ennemi Psyker en reaction quand il a dive). DOCTRINE GENERALISEE : quand l'adverse aligne
  ≥1 Psyker-engine fragile et que MON roster a un porteur anti-Psyker (Tjark HuntersBeyondDeath OU Roswitha
  CondemnorStake), le router sur les casters = kill-engine propre/cheap (souvent en reaction si l'IA dive).
  ⚠ **VOLET TERMINATORARMOUR (vecu 70001, autre « bypass de reduction defensive ») — 2 leviers** : vs un
  `TerminatorArmour` (Njal et autres terminators), la reduction −75% ne touche QUE la 1ʳᵉ attaque/tour SAUF
  profils **Psychic/DirectDamage** (exclus = passent a plein meme en 1ʳᵉ attaque). DEUX bypass : (a) un opener
  **Direct/Psychic** (Azrael DarkTalonStrike Pierce100 a bypass entierement le TermArmour de Njal + chunke/Pin
  les deep-strikers) ; (b) un **focus multi-attaquant en un team-turn** — la 1ʳᵉ attaque mange la reduction (Dante
  4-hit normal → 418), chaque attaquant DISTINCT suivant tape full (Jain Zar 4828, Azrael 2786) → mort en un tour
  (vecu 70001, Njal Finished T4). DOCTRINE : « gacher » la 1ʳᵉ attaque sur un terminator avec un coup faible/Direct,
  puis empiler le burst des autres attaquants le MEME tour ; ne jamais traiter un terminator isole en avant comme safe
  (cf. wiki §1 TerminatorArmour). Meme FAMILLE que le bypass Terrifying (RANGED) et anti-Psyker (+582) : une reduction
  defensive contournable par le bon levier — recon le levier disponible (Direct/Psychic/multi-attaquant) au deploiement.
  ⚠ **RE-CONFIRME vecu 70056** : mes 3 ranged dealers (Calandis/Vindicta/Re'vas) ont ignore le Terrifying du mirror Atlacoya
  ennemi tout le combat — Re'vas a chunke l'Atlacoya-enemy 2956→363 en un tir ranged, pleine valeur, AUCUNE reduction-melee.
  `[H11 · confirmee 6 matchups · 2026-06-19 + 2026-06-20]`

## §7 — Pieges / safety (appris)

- **Ne pas SUR-ETENDRE (cote PROPRE)** — defaut dominant (over-extension sur 14/15 defaites).
  Concretement : garder mes engines de sustain en retrait ; ne pas pousser mes carries ranged
  fragiles au contact ; **ne pas avancer dans une killzone-MoW ni dans un arc Overwatch arme** ;
  garder l'unite revivable **adjacente a l'Apothecary**. (Le versant reciproque — punir le dive
  isole adverse — est deja bien joue, cf. SKILL §6.) **Cas specifiques recurrents** : ne pas pousser un
  carry ranged fragile au contact ni dans un **arc Overwatch ARME** (un Overwatcher RANGED punit tout
  move-in dans sa portee, pas seulement la melee — vecu : Volk entrant dans l'arc Sy-gex r3 = 5418 free) ;
  apres un kill, **ne pas laisser le corps forward** (action depensee = focus-kill au tour adverse) ;
  ne jamais laisser une unite de valeur a portee d'un controleur a stun (Aesoth `VexillaMagnifica` : une
  unite stunnee forward ne peut pas retreat = kill quasi-garanti — ⚠ correction : une unite stunnee garde
  1 Movement + son attaque normale, ne perd QUE ses active abilities ; ne pas l'endturn d'office cote
  HARNESS). ✅ **PREUVE QUE CA MARCHE (1ʳᵉ fois)** : seed 96002 = cote PROPRE enfin RESPECTE (Burchard/Sy-gex
  en turret defensive, jamais avances dans la killzone Trajann) → Overwatch arme chaque tour → 4 triggers
  ont tue Aesoth/Trajann/Helbrecht en reactions SANS depenser d'actions offensives = W net porte PAR la
  ligne propre (pas par H02-malgre-sur-extension). Les reactions gagnent l'attrition SI la position reste
  defensive tout le combat. ⚠ **CONDITION (96002 W vs 97001 L, 2 matchups)** : le turret defensif ne gagne
  l'attrition que si (a) les Overwatchers sont **RANGED** (Burchard/Sy-gex tirent depuis la portee sans
  entrer en melee) ET (b) l'ennemi est **ATTEIGNABLE/tuable**. NE PAS transplanter le « turret defensif »
  sur un Overwatcher **MELEE** : il se tient DANS la killzone et meurt dans l'echange (vecu seed 97001 :
  Forcas melee-OW chunke 9035->333 puis tue, hold echoue car le sustain-engine adverse etait intouchable).
  ⚠ **PIEGE SPECIFIQUE (vecu 97002) : un finisher via une ability deep-strike/charge (Mataneo HammerOfWrath)
  n'est PAS un support durable** — les summons qu'il genere (2 Jump Pack Intercessors) **disparaissent au
  debut du tour suivant du caster** → le corps committe est effectivement SOLO et se fait focus-kill. Ne pas
  confondre « j'ai des summons adjacents ce tour » avec une position soutenue. ⚠ **GAGNER LA GUERRE DES
  ENGINES NE DISPENSE PAS DU COTE PROPRE (vecu 97000)** : meme apres avoir K!'d 3 engines/dealers tot
  (Tigurius+Deathleaper T2, Vindicta T3 → 5v3/3v2), pousser ensuite mes fragiles UN-A-UN dans la kill-zone
  ranged ouverte (Mephiston (1,5), Macer (3,5), Helbrecht (3,5)) les fait focus-deleter par le trio ranged
  → l'avance engine est dilapidee. Avancer en MASSE ecranee jusqu'au bout, pas trader les fragiles isoles
  une fois l'echange engine gagne. ⚠ **NOUVELLE FORME (vecu 98003) : un DEEP-STRIKER MELEE est un cas
  particulier d'over-extension** — le teleport-move se pose obligatoirement NON-adjacent (i2) donc un
  deep-striker melee (SwoopingHawk/charge) **auto-finit sans attaquer** (zero degat) et reste stranded solo →
  focus-kill gratuit. NE PAS depenser un deep-striker melee tant qu'un alpha SOUTENU (charge en portee + auras
  stackees + co-fire du ranged) n'est pas posable le MEME tour ; le garder shallow+groupe (cf. wiki §1
  TeleportStrike + §5bis). ⚠ **RAPPEL (vecu 98004, W) : la moitie RECIPROQUE (cluster groupe → punir le dive
  adverse en reactions, ~19590 dmg = 3 kills sans depenser mes actions) porte les W, mais la moitie PROPRE
  reste violee meme dans un W** (Asmodai+Mephiston pousses dans la reach ranged T2 → 17189 dmg) → le W vient
  de H02 + des reactions, PAS d'une ligne propre. ✅ **2e PREUVE QUE LE COTE PROPRE MARCHE (vecu 98002 W, apres
  96002)** : ligne defensive globalement RESPECTEE — Tyrant Guard BigTarget en ecran forward (NON-bouge → arme
  GuardianOrganism −33%), fragiles Abraxas/Yazaghor COLLES adjacents et JAMAIS pousses en avant → le ranged ennemi
  entrant dans la grappe est double-emousse (−1 hit + −33%) → les fragiles SURVIVENT et restent pour reagir → l'IA
  dive toute sa force → ~42k de reactions sur 2 tours adverses = 5 kills SANS depenser mes actions offensives, W 6v0.
  ⚠ SLIP PROPRE isole : Kharn a fini over-etendu/isole forward (2310→276), un-retreatable (Pinned + TheBetrayer
  auto-move deja consomme) → survecu PAR CHANCE de ciblage IA ; lecon = router le carry un rang DERRIERE dans le
  wedge T1 pour que sa position post-reaction ne soit pas stranded (et ⚠ TheBetrayer le garde engage forward →
  tension avec le cote propre). La ligne propre tenue (sauf Kharn) a PORTE le W, comme 96002. ⚠ **n+1 (vecu 98000, L)** :
meme APRES avoir gagne l'echange de DIVE early decisivement (HarvesterOfSouls AoE cleave + taunt-lock du summoner +
Overwatch reaction = 5v2-up), avancer MA LIGNE ENTIERE — carry ranged fragile (Maugan Ra) a row 3 + buff-engine
(Aethana) a row 2-3 — dans la kill-zone ranged mid-board a fait deleter 3 unites en UN tour adverse (~24k focus) →
bascule 5v2-up → 2v4-down → L. Le carry ranged n'avait PAS besoin de row 3 chaque tour ; le buff-engine devait rester
**untouchable row 0-1**, pas reachable row 2-3. MEME forme que 97000 : gagner l'echange engine/dive ne dispense PAS du
cote propre. ⚠ **n+1 dans un W (vecu 98001) : forme « deep-finish »** — apres avoir chunke Kharn 9035→2399 T2, j'ai
committe Mataneo (9035 HP) a (2,5), deep et adjacent aux engines (Hollan/Xybia), JUSTE pour lander le finish sur Kharn
→ focus-kille previsiblement = un corps de heros tradé pour un finish que l'auto-Grot ou une unite shallow aurait pose.
⚠ Couple a une 2e erreur : la marge d'overkill sur Kharn etait insuffisante (~3900 sur 2399 = ratio 1.6× < 2× = NON-overkill,
cf. H04/§1 Overkill) → la death-riposte TheBetrayer a FIRE et affaibli Mataneo AVANT le focus-kill. LECON : ne JAMAIS
deep-committer un heros pour un simple finish disponible ailleurs ; finir avec une unite shallow/un summon/une reaction,
OU laisser la cible inerte si elle ne menace rien sans kill (Kharn non-amorce a bas PV = juste une normale absorbable).
⚠ **NOUVELLE FORME — LE MOVE-GUARD « PROPRE » A LONGUE PORTEE N'EST PAS UNE GARANTIE (vecu 70003, L = ROOT CAUSE)** :
un verdict move-guard `--climb` « approche propre » (NET +0.40, 0 pertes) ne simule QUE l'UNIQUE tour d'AVANCE de l'IA
(sans contact) → il est **AVEUGLE au focus de contact RETARDE** qui atterrit au **2e tour IA** quand l'ennemi part a
>1 move. Vecu 70003 : « propre » T1 → mais le 2e tour IA a ferme la distance et focus-fire ~18528 dmg, deletant mon
carry ranged fragile (Thaddeus 6525) + mon seul healer (Nicodemus) laisses STATIONNAIRES mid-board dans un focus
6-sources. DOCTRINE : ne PAS trust un « propre » a LONGUE portee comme un feu vert ; **retraiter les fragiles
(carry ranged + healer) vers row 0-1 par DEFAUT** quand on affronte un ranged-engine a portee croissante (Vitruvius
RadBombardment ligne +1/round) + un carry move4 (Patermine snowball kill-gated) — le guard ne voit pas 2 tours en avant.
⚠ Couple : un build/placeholder peut afficher mes units rows 0-1 alors que le vrai deploiement est mid-board rows 2-4 →
verifier la rangee de deploiement REELLE avant de tenir une position « hold from the back ».
⚠ **NOTE (vecu 70002, W) : la moitie RECIPROQUE a encore PORTE le W** — un carry BlackRage auto-charge (Lucien) FORCE le
dive dans ma ligne groupee → ~16k reactions = 2 kills decisifs (Ahriman ennemi + Lucien lui-meme 4308→0 exact) sans
depenser mes actions ; la moitie PROPRE violee 1× (Abraxas reachable mid-board (4,4) → focus-kille par la double-attaque
Lucien = ma seule perte) = n+1 du failure-mode dominant, mais isole a UN fragile non-engine dans un W 4v1-dominant. NB
RARE POSITIF : le move-guard `--climb` T1 a CETTE fois ete SUIVI correctement (Ahriman engine flagge 31% loss → pulled
back → survie tout le combat), contrastant avec 70003 ou un « propre » a longue portee a ete mal-trusté.
⚠ **RAPPEL (vecu 70001, W) : la RECIPROQUE via une TURRET Overwatch HELD a porte le W** — tenir Azrael SANS attaquer
(gate Overwatch = not-attacked) AU LIEU de le pousser forward pour un K? non-garanti a converti le dive ennemi (Godswyl +
leur Dante) en ~11510 dmg de reactions = 2 kills T3 SANS depenser mes actions offensives (le LionHelm d'Azrael, +437 sur
les OW allies a ≤2 hex, a boost le multi-source). DOCTRINE : ne PAS pousser un Overwatcher pour un finish incertain — le
HOLD arme + une ligne groupee autour de lui valent mieux (meme mecanisme que 96002/98002). ⚠ **NOUVELLE FORME D'OVER-EXTENSION
PROPRE (vecu 70001, = seule perte hero du W) : FLANK-EXPOSURE d'un fragile ranged vs deep-strikers** — Shiron (fragile ranged
Blast 8533) laisse sur le FLANC DROIT au deploy (5,1) → l'ennemi a converge ses deep-strikers (2 Dantes + Mataneo, qui peuvent
landera N'IMPORTE OU) + sa melee a droite et l'a focus-kille T2. Distincte du « pousser forward » classique : ici le fragile
n'a PAS avance, c'est le DEPLOIEMENT sur un flanc isole qui l'a expose. DOCTRINE : pre-positionner les fragiles ranged
CENTRAL + screenes behind melee des le deploy, surtout face a ≥2 deep-strikers (un flanc isole = une cible de convergence).
⚠ **NOUVELLE FORME — SUR-ETENDRE DANS UNE KILL-ZONE PSYCHIC ARMOR-IGNORE (vecu 70000, L = ROOT CAUSE)** : la mitigation
defensive (armure, BigTarget −1 hit, GuardianOrganism −33%) ne protege PAS dans une kill-zone de Psychic **NoBlocking**
(StormOfWrath Pierce100 NoBlocking bypasse TOUTE la mitigation, cf. wiki §1/§3bis Tigurius). Apres un hold T1-T2 propre,
j'ai R3 pousse 2 fragiles (Vindicta 4466 + Anuphet 6733) a (4,2)/(4,3) dans la portee de la cascade 3-Psyker JUSTE pour
focus un caster → les DEUX focus-killees au tour enemy-T3 (double K!) = collapse 5v→3v. DOCTRINE : compter une zone
exposee a un Psyker NoBlocking comme une **kill-zone OUVERTE** (ma mitigation = 0) — ne JAMAIS y sur-etendre un fragile,
finir les engines depuis des tuiles SHALLOW hors de la portee Psychic. ⚠ AGGRAVE par mon PROPRE FireOfAbsolution
(le tir de Vindicta sur la cible a friendly-fire mon Anuphet adjacent → chunk decisif rendant son K! possible — DEGAGER
mes units de l'adjacence-a-la-cible avant tout tir de Vindicta, cf. wiki §2). La moitie RECIPROQUE (punir le dive) etait
jouee mais EMOUSSEE par l'absence d'un Overwatch dispo le tour cle (Re'vas EarlyWarningOverride once-per-turn/long cd) →
pas de masse de reactions comme 96002/98002/70001/70002. ⚠ **RAPPEL (vecu 70004, L structurel) : la moitie RECIPROQUE +
le move-guard T1 SUIVI ont PORTE le mid-game** — move-guard a flagge mon avance row-3/4 over-etendue (Ulf 70% loss) →
re-plan shallow row-2 groupe clean ; PUIS hold-line → l'IA dive tout → 26057 dmg de reactions = Tigurius (Ulf SavageKiller
pre-empte StormOfWrath mid-cast) + Angrax tues a 0 cout, 5v5→5v3 (pattern 96002/98002/70001/70002). PROPRE-cote viole 2×
(Vindicta seul ranged laissee forward (1,3) dans le focus Trajann+Sy-gex → deletee ; Ulf ressuscite committe adjacent a
Sy-gex → focus-kille, net OK car FJ killed Sy-gex) = n+1 du failure-mode dominant, NON decisif sur l'issue (loss structurelle
vs l'anvil) mais couteux. ⚠ Sy-gex r3 rend « back » RELATIF : un ranged fragile doit etre hors r3+move2 de l'Overwatcher
ennemi, pas juste « en arriere ». NB 2e wave d'affilee (apres 70001) ou le move-guard T1 a ete SUIVI → over-extension T1
evitee. ⚠ **NOUVELLE FORME — LE MOVE-GUARD « PROPRE » EST AVEUGLE A UN BOARD-FLIP SUMMON-ENGINE (vecu 70007, L = ROOT
CAUSE, 2e matchup distinct apres 70003)** : un verdict move-guard « approche propre » (NET +0.50, 0 pertes, « chunks les
engines sur 2-ply ») ne modelise QUE le chip de dmg sur 2 plis — il est **structurellement AVEUGLE a un board-flip
summon-engine** (Isaak CultDemagogue : 1 cast au tour ennemi spawne 3-4 Neophytes + decoys prenant un tour immediat →
4v5 → 3v12) ET au contact-dive melee a portee (move3-Custodes). Vecu 70007 : « propre » T1 trusté → avance groupee →
le tour ennemi a melee-kille Archimatos (carry Psychic fragile) + le flood ranged a tue Incisus (mon SEUL sustain) en
UN tour (25093 dmg, 2 units), board flippe a 3v12. DOCTRINE (generalise depuis 70003) : un verdict move-guard « propre »
n'est PAS un feu vert quand l'adverse fielde **un board-flip/summon-engine non tue** (Isaak, Yarrick, Anuphet…) OU un
**contact-dive melee a portee** — le guard ne voit ni le snowball de summons du 2e tour ni le focus de contact retarde.
Vs un tel board, **retraiter les fragiles + le sustain vers row 0-1 par DEFAUT** (untouchable), independamment du verdict
du guard. ⚠ **n+1 dans un W (vecu 70009) : la RECIPROQUE a PORTE le W, la PROPRE encore violee** — move-guard `--climb` sur
une avance row-2 groupee = verdict « propre » (NET +0.00, 0 pertes) CORRECT au gap de 7 rangees (a tenu, l'IA n'a pas pu
atteindre en 2 tours) ; l'IA a committe sa melee forward (Tarvakh a dive a (3,5)) → punie par un burst WarHowl-buffe 3-kill
en UN tour → 5v2 (dive-punish = la moitie reciproque a porte le W, pattern 96002/98002/70001/70002). MAIS la moitie PROPRE
violee n+1 : Ragnar (carry, over-etendu a (1,5) flanc gauche pour un K!) + Patermine (laisse forward (2,6) post-burst,
reachable Shiron r3) → les DEUX focus-killes au tour adverse = mes 2 SEULES pertes, non-decisives SEULEMENT parce que le
dive-punish m'avait deja mis 5v2-up. Le failure-mode dominant over-extension recidive MEME dans un W ; lecon repetee : apres
un burst, RETRAITER les corps forward (un kill sur le flanc ne justifie pas de presenter le carry au focus). ⚠ **n+1
(vecu 70008, L = ROOT CAUSE) : sur-etendre mes OUTILS ARMOR-BYPASS T1 = perdre la seule reponse au tank late** — Exitor
(3,5) + Atlacoya stranded (5,5) committes forward T1 → focus-killes au tour ennemi = j'ai perdu mes 2 SEULS outils
Direct/armor-ignore (CordClaw Pierce100 + Atlacoya Direct) AVANT de pouvoir les reserver → le Burchard 12k MkXGravis est
devenu ingrindable, loss a 1v1. Variante specifique du failure-mode dominant : quand l'adverse aligne un tank high-armor,
mes outils bypass-armure sont PRECIEUX → les garder SHALLOW/screenes par defaut, jamais le move forward T1 (cf. doctrine
§6 H02 classe « tank high-armor standalone » + wiki §5bis Anti). ⚠ Couple au move-guard « clean NET +0.00 » longue-portee
trusté (meme blind-spot que 70003/70007 : aveugle au focus de contact retarde) + un commit move sans verifier la
reachability/adjacence (Atlacoya finie sans cible, un seul move/tour = stranded). ⚠ **n+1 dans un W (vecu 70051) : la
RECIPROQUE a PORTE le W, la PROPRE violee 1× sous une SOUS-VARIANTE « extremite de ligne »** — hold cohesif T1-T2 (mes
units row 0-1, ennemi row 8-9) → l'IA avance tout son cluster all-soft puis dive dans mon mur Resilient → engines softs
exposes/tues sans sur-etendre mes fragiles (pattern 96002/98002/70001/70002/70006/70009). MAIS ma SEULE perte hero =
Dreir laisse a l'**extremite forward-droite (4,0)** du hold (la tuile la plus avancee de ma ligne) → focus-kille a 114 HP
T2 + heal-block Mephiston (FuryOfTheAncients) a coupe sa regen ToughToKill → non-recuperable. NOUVELLE SOUS-FORME du
failure-mode propre : pas un move forward, une **unite laissee a l'extremite exposee de la ligne au deploiement/hold,
non-retractee** → la regrouper un rang DERRIERE des le hold T1. ⚠ **n+1 (vecu 70052, L STRUCTUREL) : la moitie RECIPROQUE
de H03 est INERTE vs un cluster ALL-RANGED qui ne dive jamais** — un adversaire 4/5 ranged (Re'vas turret + Abraxas r2 +
Certus r3 + Eldryon r2 + Adamatar) avance puis focus-fire a distance SANS jamais entrer dans mes counters → le hold-baite-le-
dive (96002/98002/70051) ne s'applique PAS, c'est le contre-profil exact. Le refus du plan-A 3-for-1 (move-guard NET −3.92 =
perdre Snappa+Sibyll+Angrax pour 1 engine) + l'abandon-liberal a 3v10 = la moitie PROPRE bien appliquee, mais la loss etait
STRUCTURELLE (focus/reach) — a FLAGGER au recon (all-ranged + fragiles no-Resilient + no reach tool = jouer hold pur ou
abandonner tot). ⚠ **n+1 dans un W (vecu 70056) : la RECIPROQUE a PORTE le W via une TURRET Overwatch (Re'vas EWO) + cluster
cohesif vs roster ALL-MELEE** — EWO armee T1 + HOLD → l'adversaire 100% melee CONTRAINT de diver → l'Overwatch chunke le
diveur AVANT mon tour + ~16.7k de reactions sur 2 tours adverses tuent Ragnar (engine WarHowl avant cast) + Atlacoya-enemy +
Darkstrider sans depenser mes actions (pattern 96002/98002/70001/70002/70051/70009). PROPRE-cote VIOLE n+1 NON-decisif (5v3-up) :
Vindicta over-committee row 2 pour lander le kill du Tanksmasha → perte de Vindicta + Calandis (mes 2 SEULS ranged dealers) au
tour adverse + FireOfAbsolution friendly-fire sur Calandis (wiki §2). Le failure-mode dominant over-extension recidive ENCORE
meme dans un W ; survecu uniquement grace au dive-punish qui m'avait deja mis 5v3-up.
  ⚠ **CONFIRME n+1 (vecu 70053 W)** : hold cohesif T1-T2 (BigTarget Aesoth + 12k Snotflogga screen) → roster all-melee +
  Bellator move4-Flying + Deathleaper deep-strike CONTRAINT de diver → reactions + engine-kills sur tuiles atteignables-sur-le-dive
  = W ; PROPRE-cote viole n+1 NON-decisif (Aesoth deep a (3,3) 758 HP T4 → focus-kille T5, dying anyway = ma SEULE perte hero).
  Le failure-mode dominant over-extension recidive ENCORE dans un W.
  ⚠ **NOUVELLE SOUS-NUANCE — LE COTE RECIPROQUE REQUIERT UN REACTION-ENGINE (vecu 70055, L)** : la moitie RECIPROQUE de H03
  (le hold-baite-le-dive qui porte la plupart des W : 96002/98002/70001/70051/70056/70053) **N'EST PAS automatique** — elle
  SUPPOSE un reaction-engine (Overwatch arme / counter / turret) qui punit le dive. Un roster **summon-only** (Incursion/
  BarbedOvipositor Rippers, sans Overwatch/counter) n'a PAS d'auto-reaction → tenir ne « punit » PAS le dive, et sur-etendre
  un carry (Dante forward T3-T4) en SUPPOSANT un dive-punish qu'on n'a pas = simple exposition sans riposte → focus-kille
  (Dante 9035→3540→mort, cause contributive de la L). DOCTRINE : avant d'adopter le plan « hold-baite-le-dive », VERIFIER
  au recon que mon roster a un reaction-engine ; s'il n'en a pas (summon-only), ne JAMAIS sur-etendre un corps en comptant
  sur le dive-punish reciproque — les summon-bodies SCREENENT mais ne RIPOSTENT pas.
  ⚠ **CONFIRME n+1 (vecu 70054 W) : RECIPROQUE a porte l'early/mid, PROPRE violee = ROOT CAUSE d'une perte hero** : hold
  cohesif T1-T2 (Corrodius Resilient + Dante Terrifying en ecran) → un mur 100% melee DOIT closer → divers isoles punis
  depuis mes ranged (Yazaghor over-etendu (3,4) T3, Deathleaper deep-strike isole (1,3) → focus-kill). MAIS PROPRE-cote
  VIOLE = ROOT CAUSE : avance forward de 3 ranged a row 3 pour tuer Yazaghor a strande Isaak+Archimatos → T4 le mur a
  focus-kille Archimatos (mon Psychic dealer). W rescue UNIQUEMENT par Isaak Ambush-resurrect
  full-HP + CultDemagogue board-flip 3v4→9v1, PAS par une ligne propre → contre un roster a engine sustain/summon, cette
  over-extension aurait pu etre fatale. Lecon repetee : tuer un fragile isole avec des corps DURABLES (Dante Terrifying)
  ou tenir, JAMAIS avancer mes fragiles dans le reach d'un mur all-melee qui closera au tour suivant.
  ⚠ **CONFIRME n+1 (vecu 70060 W) : 3e application PROPRE nette + RECIPROQUE via DOUBLE reaction-engine** — j'avais le
  reaction-engine que 70055 exigeait (Re'vas EWO Overwatch-turret + Sarquael GrimRetribution held-OW + Aun'Shi −50% aura) ;
  le guard a flagge baseline-hold NET −2.25 + Sarquael-forward = mort → SUIVI sa retraite → un ennemi all-melee CONTRAINT
  de diver → ~18638 dmg en reactions ont tue Tarvakh ET Kharn T2 (zero perte hero, zero action offensive) AVANT que Kharn
  score un kill = la moitie RECIPROQUE a porte le W (pattern 96002/98002/70001/70056). PROPRE-cote quasi-RESPECTE : LA SEULE
  exposition forward = Trajann (Resilient) guard-approuve (NET +5.00) pour finir Abraxas → floored a 1 puis self-heale via
  MomentShackle = slip mineur recupere, PAS le focus-kill gratuit habituel. La ligne propre TENUE a porte le W (contraste
  net avec la serie de slips propres dominants).
  ⚠ **CONFIRME n+1 (vecu 70059 W) : RECIPROQUE via « anchors absorbent + burst au tour suivant » (sans reaction-engine), PROPRE
  violee = ma SEULE perte hero** — mon roster n'avait AUCUN reaction-engine (no Overwatch/counter/turret) → variante de la
  reciproque 70055 : le cluster bruiser Resilient/TermArmour (Typhus 12k + Wrask + Kharn) a ABSORBE le dive de l'ennemi
  all-melee CONTRAINT de fermer, et j'ai bursté a mon tour suivant (PAS un dive-punish auto-reactif ; la seule « reaction » =
  Kharn TheBetrayer death-riposte 6481). MARCHE car les anchors sont Resilient/TermArmour 9.5-12k. ⚠ PROPRE-cote VIOLE =
  ROOT CAUSE : T3 Kharn (mon MEILLEUR carry) committe forward a (4,2) pour K! un ANVIL non-engine (Tyrant Guard) → focus-kille
  par Maladus FlailSwing. ⚠ COUPLE a H40 : le guard a flagge worst=Kharn MORT mais a rate le plan best (NET +2.58) car tuer le
  TG exigeait une tuile melee forward → le NET positif a « approuve » le sacrifice. NOUVELLE FORME du failure-mode : tuer un
  anvil-killable non-engine a STRUCTURELLEMENT exige un carry au front (pas un slip de placement). DOCTRINE : un anvil-killable
  non-engine ne vaut PAS un carry forward — preferer tuer l'engine au range, ou sacrifier le corps le PLUS expendable, pas le
  meilleur carry (cf. §6 H02 meme nuance).
  ⚠ **CONFIRME n+1 (vecu 70058 W) : RECIPROQUE via un REACTION-ENGINE HOLD a porte le W, PROPRE violee 1× sous une NOUVELLE
  SOUS-FORME « over-extension INVISIBLE (drone-summon) »** — hold cohesif T1-T2 (Sy-gex Overwatch r3 turret HELD-arme + Aesoth
  BigTarget/StandVigil/Resilient screen + Thaddeus +728 feeding Sy-gex) → l'ennemi 3/5 melee/Flying CONTRAINT de diver →
  reaction-kill du screen (Ulf 4660→0, Titus permanent, Yazaghor ennemi) SANS depenser d'actions (pattern 96002/98002/70001/
  70056/70060). PROPRE-cote VIOLE = ma SEULE perte : a 5v2 j'ai avance Jain Zar (7530, un NON-tank) a (4,3) dans la reach
  COMBINEE de Njal (Psychic AoE r3) + Sho'syl (MV71 drone-summon utilisant le stat de Sho'syl) → drone 5924 + Njal 1606 =
  focus-killee. ⚠ NOUVELLE SOUS-FORME : la reach d'un **drone-summon** (le summoner reste back-row, son drone delete un forward)
  n'apparait PAS dans le danger-zone overlay (summoner blind spot, SKILL §4) → over-extension « invisible » ; AGGRAVEE par le
  move-guard indisponible (timeout) sans defaut conservateur (NE PAS avancer un non-tank quand le guard est down). n+1 du
  failure-mode dominant ICI dans un W, non-decisif (reciproque deja 5v2-up) ; regle reaffirmee « n'avancer que la durable Aesoth
  Resilient comme ecran forward, garder les fragiles/non-tanks shallow ». ⚠ **CONFIRME n+1 (vecu 70057 W 5v0)** : LES DEUX sens —
  RECIPROQUE jouee en ACTIVE FOCUS (pas auto-reactions : MON roster sans reaction-engine, sous-nuance 70055/70059, l'ennemi
  all-melee/deep-strike CONTRAINT de closer = engines tues en focus actif depuis le shallow + 2 engines screen-on-attack qui
  soakent ~14k) ; PROPRE-cote VIOLE 1× NON-decisif (Tan Gi'da non-tank poussee (5,3) row 3 a 205 HP pour du chip marginal).
  ⚠ COUPLE H40 : T2 avance row 2 sur un verdict guard one-ply « safe » → delayed-contact blind-spot (cf. 70003/70007), le
  hold-row-2 devient NET -4.78/-6.71 quand l'IA close ; tenir row 0-1 par defaut quand le gap permet la sur-commission ennemie.
  `[H03 · confirmee 46 matchups · 2026-06-17 + 2026-06-19 + 2026-06-20 + 2026-06-21]`
- **Le compteur K! (kill-count) ne soustrait PAS le clamp Resilient** — ne pas s'y fier pour
  conclure un kill sur une unite Resilient ; verifier les PV reels. ⚠ NUANCE : le K! n'est trompeur que
  pour un actif **single-hit** (Resilient floor a 1) ; un **multi-hit** (≥2 hits dans le meme actif, ex.
  BringerOfDespair 4+4, JakhalStimms, KillMaimBurn) TUE quand meme (1er hit floor a 1, 2e hit tue depuis
  1) — un K! affiche sur un Resilient frappe par un multi-hit ≥2 est donc fiable. Pour un single-hit :
  budgetiser une 2e source / Overkill / finish AUTO start-of-turn. ⚠ **ELARGISSEMENT (vecu 97002) : les
  predictions de DEGATS d'ACTIF sont non fiables au-dela du seul Resilient** — quand une **precondition de
  l'actif** n'est pas verifiee (ex. HammerOfWrath gate « if has not moved » : Mataneo avait bouge → dmg
  reel ~1015 vs ~5820 prevu ; charge + summon-attack non declenchees), la prediction sur-estime
  massivement. Un plan d'actif affiche [0-0] est de toute facon illisible. **NE JAMAIS committer un
  finisher PROFOND sur une prediction d'actif** : exiger une K! d'attaque NORMALE confirmee, OU verifier
  que la precondition (has-not-moved/charge/portee) tient AVANT de committer. ⚠ **RE-CONFIRME vs Resilient
  (vecu 98004) : DEUX labels trompeurs au bord du roll** — K! Makhotep (single-source) sur Nauseous max 1697 <
  1698 HP → NON-letal (floor jamais atteint) ; K? Mephiston Psychic sur Aesoth → laisse a 17 HP → finition
  multi-hit Nicodemus Chain requise. Le label SOMME les hits bruts au bord du roll sans soustraire le clamp
  Resilient. ⚠ **NOUVEAU CAVEAT (vecu 98000) : un multi-hit peut FLOORER un Resilient a 1 PUIS ECHOUER a le finir
  si le hit final resout a 0 dmg** sur un tank a crit-reduction/regen (Dreir ToughToKill −35% crit/−1091 crit dmg :
  Haarken 4-hit normal → hits 1-3 floored a 1, 4e hit = Amount=0 → Dreir survit a 1 ; meme forme que l'outlier 91004
  Abaddon/Macer). Ce n'est PAS une refutation du floor-then-finish (un hit REEL >0 a 1 PV tue toujours, wiki §1) :
  la cause = le hit final a zerote (crit reduit a 0 ou hit bloque une fois la cible au floor). DOCTRINE : sur un
  Resilient + crit-reduction/regen (Dreir, Abaddon, Macer), **budgetiser un finisher SEPARE** — ne pas trust un
  multi-hit K! pour fully-kill (cf. H31). ⚠ **RAFFINEMENT (vecu 70008, 2e matchup sur Dreir ToughToKill) : le zero-out
  ne bloque le kill QUE s'il est le DERNIER hit** — un 6-hit Gauss sur Dreir a floored a 1, un hit MID-sequence a fait
  Amount=0 (ToughToKill) MAIS un hit surplus ULTERIEUR (Amount=1) l'a TUE depuis 1 PV (WasOverkilled=1) = full kill.
  Donc un multi-hit a GRAND NOMBRE de hits (surplus >0 past le floor) finit fiablement un Resilient+crit-reduction ;
  il n'echoue que si le 0-dmg tombe sur le hit FINAL (98000). Preferer un multi-hit a beaucoup de hits, OU budgetiser
  un finisher separe sur un multi-hit court (cf. H31). ⚠ **EXTENSION AU SEUIL D'OVERKILL SUR FinalJustice (vecu 70057 W, confirme
  Verif, 4 FJ-carriers geres)** : meme famille « le label de kill ne soustrait pas le mecanisme defensif » que le clamp Resilient,
  portee a la death-riposte FinalJustice — 3 voies pour la nier, validees le meme match : (a) **Overkill** (coup letal >2× PV
  restants : Helbrecht overkille multi-source Mataneo 7984 + drone 1555 `Attack_WasOverkill=1` → FJ NON declenchee, i2 « unless
  Overkilled ») ; (b) **kill SANS eligible target a portee de sa normale** → FJ fire (`IsActingBeforeDeath=0`) mais ZERO dmg
  (no-op : Dante tue a (3,4) sans adjacent eligible = free-kill path distinct de l'Overkill) ; (c) **router la riposte faible-pen
  sur un body ARMURE** (Ragnar FJ 7× Chain Pierce20 ~1946 sur Mataneo armure Mechanical = trivial). DOCTRINE : pour chaque
  FJ-carrier choisir UNE voie — overkiller (riposte forte Dante Pierce80/Gulgortz double-volee), tuer hors-portee-de-sa-normale,
  ou router la faible-pen sur un tank. `[H04 · confirmee 11 matchups · 2026-06-17 + 2026-06-19 + 2026-06-20 + 2026-06-21]`
