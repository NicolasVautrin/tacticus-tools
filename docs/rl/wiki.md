# Wiki tactique — oracle Tacticus

Le **savoir NON dérivable de gameconfig** : interactions de traits, vérités de
combat observées en live, et tactique. gameconfig porte les **chiffres** (move,
portée, nrOfHits, damageProfiles, variables de traits) ; `i2_en.json` porte le
**texte de règles** ; ce wiki porte **ce qu'aucun des deux ne dit seul** — les
**interactions** entre mécaniques et la réalité du moteur (dégâts réels, ordre de
résolution, triggers de mort). Source : observations validées en duel isolé
(`rl_duel.py`), pas de la doc. Cf. `oracle-plan.md` (couche « wiki »),
mémoire `project_battle_doctrine`, `feedback_recon_units_first`.

> **Règle d'or** : ne JAMAIS raisonner sur les seuls chiffres bruts gameconfig
> ni le texte i2. Une mécanique = la somme de ses **interactions**. Toujours
> croiser avec la **prédiction de dégâts LIVE** (`decisionView`) et le **stream**
> causal (`stream_events`).

---

## 1. Mécaniques de traits transverses (référence — le « QUOI »)

> Le **QUOI FAIRE** (doctrine : overkill les Resilient, ne pas chiper un self-heal,
> tuer les Explodes à distance…) est dans le **skill `tacticus-battle` §6/§7**. Ici
> uniquement le **fait mécanique non dérivable** (gameconfig/i2 ne le disent pas),
> vérifié en duel. Ces traits sont portés par les unités → cf. §2/§3 pour qui les a.

- **`Resilient` × multi-hit** : Resilient ramène à 1 PV au lieu de mourir (sauf
  Overkill) — MAIS contre un actif **multi-hit** (Kharn `KillMaimBurn` 8 coups, Macer
  `JakhalStimms` 4) le 1ᵉʳ coup met à 1, les **coups suivants du même actif tuent**
  (plus « déjà à 1 »). Vérifié : des tanks Resilient (Trajann, Yarrick) tués en un
  seul actif. Resilient ne protège donc PAS d'un burster multi-hit.
- **`FinalJustice`** (Kharn) : riposte (1 attaque normale) **à la mort, sauf Overkill**.
  Fire **même stunné**, **même tué par AoE/killzone** (mort = trigger, pas action).
  Vérifié : killzone tue Kharn à 1113 pile → FinalJustice tue Trajann adjacent.
- **`Explodes` / `PutridExplosion`** : explose à la mort, X% PV max aux **adjacents —
  y compris les unités ALLIÉES** (friendly fire). Vérifié : Morvenn morte → 2385 sur
  des alliés adjacents (Vexilus, Mephiston) en plus de l'ennemi (Pestillian).
- **Blast / faible PiercingRatio vs armure** : dégât **live ≪ chiffre brut gameconfig**
  (armure). Vérifié : Morvenn `SanctorumMissile` « 2×2183-3056 Blast » → **1686** réel
  sur Kharn armuré. Les actifs Blast/low-pierce **ne sont pas des finishers** vs armure.
- **Stun** (`VexillaMagnifica`) : la cible **ne joue pas** au tour ennemi (neutralise
  une burst), mais ses **triggers de mort restent** (FinalJustice cf. supra).
- **`LegendaryCommander` + `StandVigil`** (Trajann/Vexilus) : un **actif allié adjacent**
  à un ennemi → cet ennemi +800 dmg subi (+2 hits pour les Characters alliés s'il est
  aussi adjacent à Trajann) + buff StandVigil. Vérifié : ouvre/booste un focus (Trajann
  2118-3180 → 4749-4902).
- **Overkill** : killing blow dépassant **largement** les PV restants (≈1.5-2×) → nie
  Resilient ET FinalJustice. (Seuil exact à confirmer — cf. §6 TODO.)
- **`Steppable`** : l'unité est **détruite si on MARCHE DESSUS ou si elle est endommagée**,
  mais **ne peut PAS être ciblée** (absente des plans d'attaque). → pour la retirer :
  `act move --to <son hex>`. Porté par les decoys (`genesSmnDecoy`). Vérifié gameconfig.
- **`Ambush`** : à la 1ʳᵉ mort, l'unité laisse un **decoy** (Steppable) ; au début de son
  prochain tour, **ressuscite plein PV** sur un decoy ami restant (**1×** ; Characters
  ressuscitent avant les non-Characters). → kill **temporaire** tant qu'un decoy survit ;
  **détruire les decoys** (marcher dessus) rend le kill permanent. Porté par : Genestealers
  (genesBiophagus, genesKelermorph…).
- **`TerminatorArmour`** : 1ʳᵉ attaque/tour subie réduite, **SAUF dégâts Psychic/Direct**
  (qui passent à plein) ; immunité Suppress. Porté par : blackAbaddon, blackTerminator.
- **`Overwatch`** (trait ou armé par un actif type EarlyWarningOverride) : si l'unité n'a
  pas attaqué, elle riposte quand un ennemi **bouge dans sa portée** au tour adverse. ⚠️
  **pas d'overlay live des zones armées** (GAP, cf. §6 TODO) → éviter au flair / exploiter
  l'angle mort IA. Porté par : darkaAzrael ; armé par : tauCrisis (Re'vas), Maugan Ra…
- **`Parry`** : réduit les attaques **multi-hit** subies de −1 hit (min 1) → mes multi-hit
  sont moins efficaces contre lui. Porté par : templHelbrecht.

---

## 2. Units CHAOS (kits & interactions — faits neutres)

> Description objective du kit (vaut quel que soit le camp qui la joue). Le « quoi
> faire pour/contre » est doctrine générale (skill §6/§7).

- **Kharn (worldKharn, 9035, move3 mêlée)** — `KillMaimBurn` (actif **range 2**,
  8 coups = 1 Pierce + 6 Eviscerate + 1 Plasma ≈ 11-15k). `RapidAssault` (+1 move
  jusqu'à sa 1ʳᵉ attaque = **move 4** ; +dmg 1ʳᵉ attaque & suivantes du tour).
  `TheBetrayer` (si a tué ce combat → **auto move+attaque au début de chaque tour**
  + 2ᵉ attaque après chaque normale). `BlessingsOfKhorne` (+dmg/−Psychic cumulé par
  kill mêlée). `FinalJustice` (à la mort : 1 attaque normale, sauf Overkill). **Pas
  Resilient.** Stun neutralise sa burst un tour.
- **Abaddon (blackAbaddon, 10038, move3, ranged r2 + mêlée)** — `Drachnyen` (actif :
  **SET les PV à 4729** = self-heal + 2ᵉ attaque récurrente ensuite). `FirstAmongTraitors`
  (+364→+1313 dmg aux Chaos alliés à portée 2, scale par attaque). `Resilient`.
  `TerminatorArmour` (1ʳᵉ attaque/tour subie réduite, **sauf Psychic/Direct**).
- **Corrodius (deathBlightbringer, 12551, move2 mêlée)** — `ContagionsOfNurgle`
  (aura : −armure aux ennemis dedans, **s'étend** r1→r2→r3 par round). `Poxwalkers`
  (actif : **summon** Poxwalkers 2183 PV qui attaquent direct). `CursedPlagueBell`
  (Chaos alliés dans l'aura +1 move ; **Psykers ennemis dans l'aura s'auto-blessent
  1310** à chaque attaque Psychic). `Resilient`.
- **Macer (worldJakhal, 9035, move3 mêlée)** — `JakhalStimms` (actif : 4×~2600
  multi-hit + splash, **−25% PV du lanceur**, **ne finit PAS son tour**).
  `Skullsmasher` (+126 dmg / 10% PV manquant → plus fort à bas PV ; + Stun si a
  déjà tué). `BlessingsOfKhorne`, `Resilient`.
- **Pestillian (deathPutrifier, 12047, move2 mêlée)** — `PutridExplosion` (**explose
  à la mort**, Toxic aux adjacents sauf Death Guard). `FoulInfusion` (actif : +2037
  Toxic aux Chaos de l'aura ce round+suivant, puis attaque). `ExplosiveMaladies`
  (buff Blast aux adjacents ; cibles tuées par ces attaques **toujours overkillées**).
  `ContagionsOfNurgle`, `Resilient`.

---

## 3. Units IMPERIUM (kits & interactions — faits neutres)

- **Vexilus/Aesoth (custoVexilusPraetor, 11044, move3 mêlée)** — `VexillaMagnifica`
  (1183, actif : **STUN 2 cibles adjacentes** + dmg + le lanceur −66% dmg subi 1 round,
  cd2). `StandVigil` (alliés à portée 2 : +armure / +dmg non-normal ; étendu si un
  Custodes use un actif). `BigTarget` (alliés adjacents −1 hit ranged ; non déplaçable).
  `Resilient`.
- **Trajann (custoTrajann, 10038, move3 mêlée)** — `MomentShackle` (1184, self-heal
  4365 + zone counter-move 1 round). `LegendaryCommander` (un ennemi adjacent à un
  allié qui a usé un actif ce tour → **+800 dmg subi** ; s'il est aussi adjacent à
  Trajann, les Characters alliés scorent **+2 hits** à leur 1ʳᵉ attaque non-normale).
  `CrushingStrike` (+dmg mêlée normale **s'il n'a PAS bougé**). `Resilient`,
  `MartialKatah` (−dmg des attaques NORMALES subies, pas des actifs).
- **Morvenn (adeptMorvenn, 9539, move3, ranged r3 + mêlée)** — `SanctorumMissile`
  (1062, AoE Blast r3 — **faible vs armure**, cf. §1). `Explodes` (**friendly fire** :
  à la mort, 25% PV max Direct à TOUS les adjacents, cf. §1). `ActOfFaith` (+crit à
  chaque mort/kill d'un Imperial, reset au crit). `RighteousRepugnance` (mêlée normale
  +AoE). `Mechanical` (pas de heal, repair seulement).
- **Mephiston (bloodMephiston, 9537, move3, ranged r2 + mêlée, Psychic Pierce100
  NoBlocking)** — Psychic **bypasse TerminatorArmour**. `Psyker` (attaque ranged
  normale → splash % à un ennemi adjacent à la cible ; **s'auto-blesse dans une aura
  Nurgle**, cf. Corrodius). `TheQuickening` (1151, repositionnement r2). `Terrifying`
  (réduit les dégâts de **mêlée** subis). `RapidAssault`. `FuryOfTheAncients` (après
  move : dmg + **bloque heal/revive/repair 2 rounds** sur la cible).
- **Yarrick (astraYarrick, 7530, move3, ranged r2)** — `SendInTheNextWave` (1016,
  summon 2+ Cadians 2910 PV qui tirent ; cible à portée 2). `Resilient`.

---

## 3bis. Units (autres factions, vues en random) — kit + interactions PAR unité

> Une entrée par unité ; interactions spécifiques sur SA page (traits transverses
> en §1 : Resilient, FinalJustice, Explodes, **Ambush**, **Steppable**, Blast-vs-armure).
> Stats → gameconfig. **Recon AUSSI les unités INVOQUÉES** (decoy, drones, Aberrant,
> Hormagaunt, Guardsman…) via gameconfig dès qu'elles apparaissent — leurs traits
> dictent la gestion (ne pas supposer ; ex. le decoy `Steppable` ci-§1).

- **ultraTitus (Ultramarines)** — `TacticalPrecision` (s'il a chargé = crit ~3638,
  sinon 3× AoE adjacents). **`FuelledByFury`** : 1ʳᵉ mort/tour **NON-overkillable**
  (FinalJustice fire toujours) + **revit à 5456 PV si sa riposte de mort TUE** une
  cible → le tuer en faisant tomber sa FinalJustice sur un **tank** (qu'elle ne tue
  personne). `FinalJustice`, `BeastSlayer`.
- **darkaAzrael (Dark Angels)** — `DarkTalonStrike` (Direct r2 + ligne AoE + Suppress).
  `Overwatch` (armé s'il n'attaque pas — cf. GAP overwatch sous Re'vas). `LionHelm`
  (alliés r2 : +block + overwatch boosté). `FinalJustice`.
- **tauCrisis « Re'vas » (Tau, Flying, Mechanical)** — `EarlyWarningOverride` : 2 Shield
  Drones **+ elle s'arme en OVERWATCH (+1892 dmg)** → sa zone est interdite. ⚠️ **GAP
  outillage** : pas d'overlay des zones d'overwatch armé (la danger zone ≠ « bouger ici
  déclenche l'OW ») → évité « au flair ». TODO : lire l'effet OW armé (Effect_Type 1009)
  + range → overlay pour éviter/bait précis. `RangedSpecialist`, `BigTarget`, Mechanical.
- **templHelbrecht (Black Templars)** — `CrusadeOfWrath` (équipe r2 : +364 dmg + pierce).
  `Parry` (−1 hit aux multi-hit subis → mes multi-hit moins efficaces). `FinalJustice`.
  `DestroyTheWitch` (+move + dmg vs Psykers).
- **genesBiophagus « Hollan » (Genestealer)** — **MOTEUR de l'équipe** : `Healer` +
  `TwistedScience` (cible +2183 PV/maxHP) + `AberrantHypermorph` (summon 5456 PV).
  `Ambush` (§1). → **kill prioritaire** (coupe heal/buff/summon) ; détruire ses decoys
  (Steppable, §1 — marcher dessus) sinon il revient ; 2ᵉ kill permanent.
- **worldEightbound « Azkor » (World Eaters ; Daemon/Resilient/Terrifying/Unstoppable)**
  — **`OverwhelmingWrath`** : Taunt tous les adjacents + −64% dmg ranged subi, puis
  **AoE (2× à tous les adjacents) au DÉBUT de son tour SUIVANT** (retardée). Combo fort :
  Taunter un cluster sur ce tank → l'AoE retardée nettoie (a tué Biophagus + chunké 2).
  `BeaconOfRage` (+315 dmg/coup subi, max 8 ; partage aux Chaos adjacents s'il a tué).
- **tyranWingedPrime (Tyranids, Flying)** — **MOTEUR de SUMMONS** : `AlphaWarrior`
  (Warrior 5820 PV s'il n'a pas bougé) + `SynapticLinchpin` (Hormagaunt sur attaque
  Synapse non-tuante, max 4) → snowball de board (fini 8v1). `Synapse`, `FinalJustice`.
  (Summons : agissent 1× à la création puis **réagissent** — overwatch-like.)
- **blackTerminator « Angrax » (Black Legion)** — `TeleportStrike` (deep strike : drop
  tout hex libre non-adjacent). `BringerOfDespair` (4× cible + 4× un autre adjacent).
  `HatefulAssault` (overwatch mêlée). `TerminatorArmour`.
- **spaceWulfen « Ulf » (Space Wolves)** — **`SavageKiller`** : 5× dmg à **tout summon
  qui s'approche OU tout ennemi qui use un actif adjacent** (avant l'actif) → counter
  anti-summon/anti-caster (fort vs summon-heavy). `GreatFrostAxe` (gros + Ice). `FinalJustice`.
- **genesKelermorph « Judh » (Genestealer)** — `HeroicFusillade` (AoE r2 : move + frappe
  cible + entourage). `HypersensoryAbilities` (1ᵉʳ coup/tour : plancher 50% PV + déplace
  + decoy + contre). `Ambush` (§1). Ranged très survivable.
- **MoW astraOrdnanceBattery (Imperial)** — `MalleusRocketLauncher` : **barrage RETARDÉ**
  (marque un hex via `--to`, fire au DÉBUT du tour MoW SUIVANT ; AoE large + Suppress).
  `ForwardSpotter` : summon Guardsman (cible un allié) qui **attaque immédiatement**.
- **MoW deathCrawler (Death Guard, ennemi)** — `EntropyCannons` / `PlagueburstMortar`
  ne frappent QUE des cibles à **armure réduite OU dans une aura Contagion** → sans ces
  conditions sur le board, ce MoW est largement neutralisé.

---

## 3ter. Summons / NPC (invoqués EN COMBAT — recon dès apparition)

> Les unités invoquées ont leur propre kit/traits (gameconfig : ids `*Smn*` / `*Npc*`).
> **Les recon dès qu'elles apparaissent** — leurs traits dictent la gestion. Stats
> indicatives (texte de l'ability du parent / gameconfig).

- **genesSmnDecoy « Decoy »** (laissé par `Ambush`) — HP0, traits `Steppable` + `Decoy`
  (cf. §1). → le détruire en **marchant dessus** (`act move --to <son hex>`) coupe la
  résurrection Ambush.
- **tyranNpc4Warrior / Tyranid Warrior** (`AlphaWarrior` de WingedPrime) — ~5820 PV,
  ranged ; ne bouge pas le tour d'invocation mais attaque + **réagit** (a tué 2 drones
  en réaction sans jouer de tour).
- **tyranSmnHormagaunt** (`SynapticLinchpin`) — ~2183 PV ; spawn adjacent à une cible
  attaquée non-tuée, attaque immédiatement (max 4 simultanés).
- **astraNpc1Guardsman / Cadian Guardsman** (Yarrick `SendInTheNextWave` / MoW
  `ForwardSpotter`) — ~2910 PV, ranged ; **attaque immédiatement** à l'invocation.
- **tauSmnDroneShield « Shield Drone »** (Re'vas `EarlyWarningOverride`) — ~2910 PV ;
  attaque à l'invocation ; meat-shield (BigTarget réduit les hits ranged sur Re'vas).
- **genesSmnAberrant « Aberrant Hypermorph »** (Biophagus) — ~5456 PV / ~2837 dmg ;
  attaque immédiatement.
- **deathPoxwalker** (Corrodius `Poxwalkers`) — ~2183-2992 PV / ~2546 dmg ; spawn dans
  l'aura Contagion, attaque immédiatement ; tuer le summoner coupe le flux.

---

## 4. Machines of War (MoW)

- **ultraDreadnought / Galatian (Ultramarines)** — `MacroPlasmaIncinerator` (1159,
  **killzone** : marque 1 hex + 2 derrière ; 3×~2183-2619 Plasma à tous les ennemis
  **la 1ʳᵉ fois qu'un ennemi TERMINE son move dans la zone** ; cd1). **Ne touche PAS
  immédiatement** (pose des effets de tile, dmg différé) → juger à la cascade.
  **Visée** : cibler (entité) une **unité avancée du camp du MoW** marque la zone
  **devant** elle → l'adversaire qui avance pour l'attaquer y termine son move → AoE.
  Vérifié : tue les Poxwalkers (2992) et un Kharn stunné à 1113. `DutyEternal` (1158,
  **mur 14550 PV / 2910 armure**, coût 3 munitions, consomme le MoW) — cible une zone
  de hex LIBRES → `act ability --caster <mow> --to col,row --ability 1158` (cible-hex
  supportée, le hook résout le hex en entité-tuile).
- **blackForgefiend (Chaos)** — artillerie `HadesAutocannons` / `DaemonicOrdnance`
  **ranged, frappe n'importe où (~2600-2900/tour)**. Une MoW d'artillerie atteint
  toute case → le repli ne protège pas de son tir (à intégrer dans la menace).

---

## 5. Note de matchup (observé)

Imperium [Trajann/Vexilus/Morvenn/Mephiston/Yarrick + ultraDreadnought] vs Chaos
[Kharn/Corrodius/Abaddon/Macer/Pestillian + blackForgefiend], seed 777, rank 17 :
le côté **Imperium perd structurellement** (4/4 observés). Profil : briques ~9-11k
sans heal soutenu **vs** tanks Resilient / self-heal (Abaddon) / explose 12k +
artillerie MoW → l'**attrition** favorise le Chaos quelle que soit l'exécution.
Meilleure ligne Imperium (outils+doctrine corrects) : Kharn+Macer+Poxwalker retirés
via stun/killzone/actifs, mais Trajann (FinalJustice) puis Morvenn (Pestillian+MoW)
tombent. → Pour démontrer « oracle > IA gloutonne », prendre un **matchup équilibré**.

## 6. TODO (savoir non dérivable encore manquant)
- **Sémantique terrain** (Q2 ouvert oracle-plan) : effet gameplay de Swamp / Water /
  glace / feu / Despoiled Ground (LetTheGalaxyBurn) / Contagion tiles. Non observé.
- Seuil exact d'**Overkill** (ratio dmg/PV) — confirmer la formule.
- Interaction `FuryOfTheAncients` (bloque « restore Health ») × `Drachnyen` (SET HP) :
  bloque-t-il le self-heal d'Abaddon ? Non testé.
