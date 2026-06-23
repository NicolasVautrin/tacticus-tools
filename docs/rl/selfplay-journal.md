# Self-play journal (oracle vs oracle) — demos + confrontation

Source : matchs **self-play** (Claude oracle vs Claude oracle) — NE PAS mélanger avec `docs/rl/journal.md` (pipeline oracle-vs-IA). Action logs bruts dans `data/_sp_<seed>_A.json` / `_B.json` (supprimés post-teardown — les séquences clés sont résumées ici).

---

## seed 80000 — winner=team1 (ts=2026-06-22)

### Rosters

| Équipe | Unités |
|--------|--------|
| **team1 (Player A / oracle)** | ultraTigurius (Tigurius) · tyranTyrantGuard (Tyrant Guard) · custoAtlacoya (Atlacoya) · admecRuststalker (Exitor-Rho) · tauMarksman (Sho'syl) |
| **team2 (Player B / oracle)** | spaceRockfist (Arjac) · tauAunShi (Aun'Shi) · orksNob (Tanksmasha) · admecDominus (Vitruvius) · deathPutrifier (Pestillian) |

### Adjudication

- A outcome_perceived = **W** ; B outcome_perceived = **L** → **winner_consensus = true**
- `rl_duel.py status` : `stage=None alive_by_team={}` (battle terminée, runner déjà purgé)
- **authoritative_winner = team1**

### Win-conditions (consensus croisé A.mine ≈ B.theirs et A.theirs ≈ B.mine)

**team1 win-condition** : Tigurius StormOfWrath AoE engine Psychic Pierce100 NoBlocking (until-5-adjacents) + TalonsOfTheEmperor Atlacoya scaling-carry (+728/actif allié cumulatif) enable par DaughterOfTheAbyss aura ; Sho'syl SeekerMissile delayed-nuke + Tigurius StormOfWrath AoE pre-chunk → Vitruvius mark+kill garanti T5.
→ Accord A.mine / B.theirs : **CONSENSUS** (B a correctement identifié Tigurius+Exitor-Rho+Atlacoya carry).

**team2 win-condition** : Aun'Shi SereneUnifier cycle-buff engine (R1 −50% dmg / R2 +1 move / R3 +582 dmg, cyclant) + Vitruvius MasterAnnihilator mark (+1 hit) + RadBombardment ligne croissante ; Pestillian ContagionsOfNurgle aura attrition ; Arjac Resilient+TerminatorArmour anchor.
→ Accord A.theirs / B.mine : **CONSENSUS** (A a correctement identifié Aun'Shi cycle et Vitruvius mark comme les vrais engines).

### Séquences clés (résumé des action logs)

**Player A (team1) :**
- T4 : StormOfWrath sur Aun'Shi (primary 2768 + adjacency-splash Vitruvius 2847) → SeekerMissile mark Vitruvius → TalonsOfTheEmperor finish Aun'Shi (5768, avec +1456 scaling 2 actifs) = double-engine-kill en 2 tours (T4 Aun'Shi, T5 Vitruvius fini par missile + Tigurius normale à 73 HP).
- T6 : Atlacoya retreat de (3,5) vers (1,4) pour sortir de l'aura Pestillian (side-propre doctrine).
- Arjac killed late via Psychic chip (2209 fixed, bypass TerminatorArmour+AnvilShield) → Atlacoya melee finish à 1 HP.

**Player B (team2) :**
- T4 : Foehammer sur Tyrant Guard (5201 stun) → tué T5 (3897). Bonne priorité (GuardianOrganism aura ôtée).
- T5 : Tanksmasha UnstoppableMomentumReworked charge en ligne → hit Tigurius (1415) + Exitor-Rho (952) → mais Tanksmasha avance en tuile EnvEndBombardment → **détruit par bombardement de fin de tour**.
- Pestillian aussi tué par EnvEndBombardment (tuile active, non détectée avant le mouvement).
- Aun'Shi tué avant que le cycle SereneUnifier R3 (Storm of Fire +582) puisse re-cycler.

### Confrontation : consensus vs divergences

#### Mécaniques de CONSENSUS (rapportées des DEUX côtés — cross-observable)

1. **SeekerMissileFrequencyLock = delayed nuke fire au DÉBUT du PROCHAIN tour de Sho'syl** : A (about=mine) + B (about=theirs) concordent. gameconfig confirme verbatim « At the beginning of Sho'syl's next turn... the target is hit. »
2. **TalonsOfTheEmperor +728 par actif allié cumulatif** : A (about=mine, +1456 avec 2 actifs) + B (about=theirs, « scales on ability count »). gameconfig confirme « +728 Damage for each time a friendly Character has used an active ability this battle. »
3. **SereneUnifier cycle R1/R2/R3 exact** : A (about=theirs) + B (about=mine) concordent sur les buffs exacts (R1=SenseOfStone −50% dmg, R2=ZephyrsGrace +1 move, R3=StormOfFire +582 dmg). gameconfig confirme verbatim.
4. **ContagionsOfNurgle aura armor-reduction croissante** : A (about=theirs, ArmorReduction1 observé) + B (about=mine, ChangeStats FixedArmor_Modification négatifs observés). gameconfig confirme portée R1-2=1 / R3-4=2 / R5+=3.
5. **UnstoppableMomentumReworked : charge en ligne droite, hits TOUS les ennemis sur le chemin** : B (about=mine, Tigurius 1415 + Exitor-Rho 952 dans le même tour de charge). gameconfig confirme « Any enemies hit by the charge take 1× Direct Damage. » A ne contre-observe pas (pas présent dans ses threat-cards), mais la description A de Tanksmasha inclut « charge Direct stun BigTarget » = accord implicite sur la mécanique.
6. **TerminatorArmour bypass total par Psychic Pierce100 NoBlocking** : A (about=theirs, Tigurius Psychic 2209 fixed bypasse TermArmour ET AnvilShield) + B (about=theirs Tigurius Psychic NoBlocking dans roster theirs). gameconfig confirme `terminatorArmourExcludedDmgProfiles=Psychic,DirectDamage`.

#### Divergences (entre les deux observateurs)

1. **Mécanisme de mort Tanksmasha et Pestillian** : A dit « Killed by opponent agent » pour les deux. B dit tués par **EnvEndBombardment** (tuiles de bombardement actives sur le board ignorées dans la planification des mouvements). Pas une vraie contradiction — A observait depuis la perspective adverse et a vu les morts sans en connaître la cause. B a fourni la vérité causale. La divergence est d'information, pas de fait.
2. **FoulInfusion fire sur adjacent aléatoire, pas la cible spécifiée** : B seul (about=mine) rapporte ce comportement (FoulInfusion déclenche une attaque normale mêlée sur un ennemi ADJACENT aléatoire, pas l'unité target de l'ability). A ne l'observe pas. Candidat non-consensus → `hypotheses.md`.
3. **MV71 drone minimum range ~2** : A seul (about=mine, drone attack mutated=False à ≤1 hex). B ne cross-observe pas. Candidat non-consensus → `hypotheses.md`.
4. **StormOfWrath AoE adjacency-splash** : A (about=mine) rapporte le splash sur Vitruvius adjacent à Aun'Shi. gameconfig confirme « up to 5 adjacent units » mais B ne cross-observe pas le splash explicitement (mentionne StormOfWrath AoE dans roster theirs). Mécanique confirmée par gameconfig seul, pas double-cross-observation live.

### Erreurs identifiées (leçons)

- **B** : ignorer les tuiles EnvEndBombardment dans la planification des mouvements = 2 kills adverses gratuits (Tanksmasha 3793 HP + Pestillian 12047 HP) en fin de tour → effondrement 3v5 → 1v4 → loss.
- **A** : Sho'syl MV71 drone silently fail à ≤1 hex (min range ~2) → 3 tours perdus sans kill sur Tanksmasha.
- **A** : Tyrant Guard avancé dans l'aura Pestillian ContagionsOfNurgle (12548→3897 sur 2 tours).
- **A** : Exitor-Rho avancé en aura Pestillian inutilement (ne peut pas safely kill un Explodes en mêlée).
- **B** : RadBombardment T1 sur Tigurius hors-portée (mutated=False silencieux) = action Vitruvius gaspillée.
- **B** : FoulInfusion sur Tigurius visé → attack resolves sur TG adjacent aléatoire (FoulInfusion = mêlée aléatoire adjacent, pas la target de l'ability).

### Refs action logs

Action logs complets : `data/_sp_80000_A.json` + `data/_sp_80000_B.json` (supprimés post-teardown, cf. cleanup).

---

## seed 80000 — winner=no-winner (round-cap mutual-wipe) (ts=2026-06-22 (opus run))

> ⚠ **Run distinct du bloc seed 80000 ci-dessus** (run antérieur = team1 W). Même seed, oracle-play différent → trajectoire ET issue différentes. Ce run = **mutual-wipe par EnvEndBombardment, winner=None**.

### Rosters

| Équipe | Unités |
|--------|--------|
| **team1 (Player A / oracle, player 3)** | ultraTigurius (Tigurius) · tyranTyrantGuard (Tyrant Guard) · custoAtlacoya (Atlacoya) · admecRuststalker (Exitor-Rho) · tauMarksman (Sho'syl) |
| **team2 (Player B / oracle, player 4)** | spaceRockfist (Arjac) · tauAunShi (Aun'Shi) · orksNob (Tanksmasha) · admecDominus (Vitruvius) · deathPutrifier (Pestillian) |

### Adjudication

- A outcome_perceived = **uncertain** (5 tours) ; B outcome_perceived = **uncertain** (6 tours) → **winner_consensus = true** (les deux s'accordent : pas de vainqueur clair).
- `rl_duel.py status --state-file data/_sp_80000_A.json` : `stage=None turn=None alive_by_team={}` → BATTLE FINIE, team gagnante = **None**.
- **authoritative_winner = no-winner** (round-cap / mutual-wipe EnvEndBombardment : toutes les unités des DEUX équipes à hp=0, winner=null). Genuine draw, PAS un W/L.

### Win-conditions

**team1 (A self / B reading) — CONSENSUS** : Sho'syl ranged carry + summon-engine (SeekerMissile r5 ~6184 delayed-nuke + MV71 drone summons + Markerlight) feeding off un screen durable (Tyrant Guard BigTarget + Atlacoya Terrifying + Tigurius Psychic-AoE) ; SOURCE = Sho'syl, à protéger derrière l'écran. → A.mine ≈ B.theirs = **accord fort** (les deux identifient Sho'syl comme la source).

**team2 (B self / A reading) — DIVERGENCE PARTIELLE** : A lit team2 comme un snowball mêlée piloté par **Aun'Shi SereneUnifier** (SOURCE = Aun'Shi). B décrit son plan EXÉCUTÉ comme **Vitruvius RadBombardment line-AoE + Arjac Foehammer nuke** comme axe principal, Aun'Shi étant un **enabler qu'il a échoué à protéger** (retraité à 1846 HP hors portée de buff, puis perdu = engine gaspillé). → Les deux conviennent qu'Aun'Shi est un amplificateur, mais divergent sur le fait qu'il fut LA source : A le surpondère, B l'a sous-utilisé. (cf. divergence #1.)

### Séquences clés (résumé des action logs — détail dans les state-files, supprimés en cleanup)

**Player A (team1) :**
- Recon → Aun'Shi identifié comme amplificateur ; **SeekerMissileFrequencyLock depuis une tuile shallow = assassinat d'engine en 2 temps** : la mark a immédiatement chunké Aun'Shi 8536→1846, le missile retardé l'a fini au tour suivant — zéro exposition du carry fragile. Meilleur play du match.
- Hold cluster row 0-1 pendant 3 tours contre un ennemi 4/5 mêlée (H03), chip de l'engine en sécurité.
- Punition du dive Tanksmasha isolé à (3,4) : multi-source (drone Sho'syl 2570-3854 + Atlacoya Talons 2892-6318 + Exitor CordClaw Direct Pierce100 1804-4212) = kill du corps 10040 en un tour ; CordClaw a bypassé le block BeastSnagga.

**Player B (team2) :**
- Hold durable-brick early (Arjac/Pestillian Resilient anchors, fragiles écranés) — doctrine correcte mais minée par des **move-rejections silencieuses** (cf. H55) fragmentant la formation.
- **Alpha-swing en déficit 3v6** : RadBombardment line a chunké QUATRE ennemis en un cast (Tigurius 6525→1954, TG 7530→2512, Exitor 8032→4569, Sho'syl 6527→3917 + drone tué) PUIS Foehammer K! garanti sur Atlacoya full-HP (8032, Ranged-tag bypasse Terrifying, +2183×chars morts) + Stun. 3v6 → 3v4 tous full-HP = combo définissant du match.
- Tour final : 1v2 gagnant (Arjac full-HP Resilient vs 4570 PV ennemi) → mais EnvEndBombardment round-cap a fire et wipe le board = draw avant conversion.

### Confrontation : consensus vs divergences

#### Mécaniques de CONSENSUS (rapportées des DEUX sides, cross-observable — recoupées gameconfig)

1. **SereneUnifier (Aun'Shi)** cycle R1 SenseOfStone −50% dmg / R2 ZephyrsGrace +1 move / R3 StormOfFire +582 dmg, persiste 1 tour même Aun'Shi mort, répète. A(theirs)+B(mine). gameconfig verbatim. (déjà au wiki §3bis, pas ré-inscrit.)
2. **RadBombardment (Vitruvius)** : ligne Toxic Pierce70, chunke tous les units en ligne en UN cast, Contamination + Suppress, longueur +1/round +1/heal-Mechanic. A(theirs, chunk de toute sa ligne) + B(mine, 4 ennemis softés). gameconfig confirme. → **INSCRIT wiki §3bis** (alpha multi-cible).
3. **Foehammer (Arjac)** : Ranged profile=Power → BYPASSE Terrifying (mélée-only), +2183/Character défait, Stun. B(mine, K! Atlacoya full-HP) + A(theirs, threat high scaling+stun). gameconfig confirme. → **INSCRIT wiki §5 synergie**.
4. **SeekerMissileFrequencyLock (Sho'syl)** : HeavyRound r5, Markerlight puis missile retardé au DÉBUT du prochain tour de Sho'syl (5456-6184). A(mine, 2-temps engine-kill) + B(theirs, r5 6184). gameconfig verbatim. (déjà au wiki §3bis.)
5. **MV71SniperDroneSquad (Sho'syl)** : summon MV71 (tauSmnDroneSniper) au LIEU d'une normale, utilise le Damage stat de Sho'syl, max 3 (lowest-HP retiré au cap), Markerlight. A(mine)+B(theirs) concordent (~1996 HP live observé des deux côtés ; base gameconfig 1455 HP — la diff = scaling, observation non-load-bearing). gameconfig confirme la mécanique. (déjà au wiki §3bis.)
6. **EnvEndBombardment (round-cap)** : nuke board-wide terminal → wipe les DEUX équipes, winner=None (draw). A(theirs)+B(theirs), confirmé par `status` (alive_by_team={}). → **INSCRIT wiki §3quater + H51 promue confirmée**.
7. **PutridExplosion (Pestillian)** : explose à la mort = 25% max HP Toxic aux adjacents sauf Death Guard (TRAIT, gameconfig). A(theirs, kill at range / no friendly adjacent) + B(mine). Concordant. (FoulInfusion correctement jugé INERT des deux côtés : Pestillian sole Chaos.)

#### Divergences (entre observateurs)

1. **Source réelle de team2** : A surpondère Aun'Shi comme LA source ; B l'a sous-utilisé (engine gaspillé) et son axe exécuté fut Vitruvius RadBombardment + Arjac Foehammer. → divergence d'interprétation/exécution, PAS de fait sur la mécanique. (Pas une H — c'est une lecture de win-condition.)
2. **Cause de l'isolation de Tanksmasha** : A = dive d'over-extension qu'il a puni ; B = fragmentation involontaire par moves rejetés silencieusement (H55). → **hypotheses.md H56** (divergence causale A/B).
3. **`play --no-ai` rejette silencieusement des moves (ok=true/mutated=false) sans reason-code** : B (massif sur la formation) + A (drone MV71, cf. H53). → **hypotheses.md H55** (friction outil, candidat).
4. **Contribution de PutridExplosion à l'effondrement ennemi** : B (low confidence) infère que l'explosion de son Pestillian a fini le cluster ennemi blessé ; A ne corrobore pas cette causalité. → observateur unique, candidat non retenu au wiki.

### Erreurs identifiées (leçons, des deux sides)

- **A** : sur-extension d'Atlacoya + drone à row 3 pour landerle kill Tanksmasha → focus-killés au tour ennemi (failure-mode dominant : un corps durable laissé forward après un kill reste focusable). Committer le MINIMUM + rapatrier.
- **A** : blob serré contre un ennemi à **line-AoE (RadBombardment) + aura expansion (ContagionsOfNurgle)** = la PIRE forme (multi-hit ligne garanti) ; le plan hold-and-punish présupposait un dive mêlée qui n'est jamais venu. ESPACER vs line-AoE.
- **A** : pas pris en compte le round-cap EnvEndBombardment dans le pacing → survivants critiques bas-PV wipe par le nuke terminal. Le round-cap est une horloge dure quand on est ahead-on-quality / behind-on-bulk.
- **B** : Tanksmasha isolé forward (moves d'escorte rejetés, cf. H55) → focus-killé. Vérifier `mutated=true` avant de committer la formation.
- **B** : fragiles (Aun'Shi puis Vitruvius) parqués dans la reach ranged ennemie (Sho'syl r5 + Tigurius Psychic) → Aun'Shi sniped 1846 puis mort = engine perdu. Garder les fragiles 7+ rows back vs SeekerMissile r5.
- **B** : round-cap ignoré → turtle-vs-turtle a brûlé l'horloge ; un 1v2 gagnant non converti = draw. Forcer l'engagement plus tôt en avance de tempo.
- **B** : re-émission en aveugle du même pattern d'avance malgré les rejets silencieux répétés (H55) sans diagnostiquer la cause.

### Refs action logs

Action logs complets de CE run : `data/_sp_80000_A.json` + `data/_sp_80000_B.json` (supprimés post-teardown — séquences clés résumées ci-dessus).

---

## seed 80000 — winner=team2 (ts=2026-06-22 (opus + moves fix))

> ⚠ **3ᵉ run distinct de la seed 80000** (cf. les 2 blocs ci-dessus : run #1 = team1 W, run #2 = no-winner mutual-wipe EnvEndBombardment). Même seed, oracle-play différent → trajectoire ET issue différentes. CE run = **team2 W par alpha RadBombardment sur blob clusteré à T5**, SANS EnvEndBombardment (combat terminé round ~5, bien avant le round-cap).

### Rosters

| Équipe | Unités |
|--------|--------|
| **team1 (Player A / oracle, player 3) — PERDANT** | ultraTigurius (Tigurius) · tyranTyrantGuard (Tyrant Guard) · custoAtlacoya (Atlacoya) · admecRuststalker (Exitor-Rho) · tauMarksman (Sho'syl) |
| **team2 (Player B / oracle, player 4) — VAINQUEUR** | spaceRockfist (Arjac) · tauAunShi (Aun'Shi) · orksNob (Tanksmasha, DIED) · admecDominus (Vitruvius) · deathPutrifier (Pestillian) |

### Adjudication

- A outcome_perceived = **L** ; B outcome_perceived = **W** → **winner_consensus = true** (A="L" & B="W" → team2).
- `rl_duel.py status --state-file data/_sp_80000_A.json` : `stage=None alive_by_team={}` (battle terminée, runner déjà purgé — état live non lisible post-finish, friction connue).
- Snapshot final corroboré par les DEUX narratifs : team2 = 4 units healthy vs team1 = 3 low-HP survivors (TG + Atlacoya morts, Tigurius 6525→1305, Sho'syl 6527→3917), team2 a pris le dernier tour.
- **authoritative_winner = team2.**

### Win-conditions (consensus croisé A.theirs ≈ B.mine et A.mine ≈ B.theirs)

**team2 win-condition (VAINQUEUR)** : avance cohésive NON-clusterée (Arjac/Pestillian/Tanksmasha screening Vitruvius+Aun'Shi) + **Vitruvius RadBombardment ligne-AoE croissante** (Toxic Pierce70 bypass Terrifying/armure) amplifié par **MasterAnnihilator mark (+1 hit)** et **Aun'Shi SereneUnifier** + **Pestillian ContagionsOfNurgle armor-shred** + **Arjac Foehammer snowball** (+2183/Character défait, Resilient anchor).
→ Accord A.theirs / B.mine = **CONSENSUS** (A a correctement identifié Vitruvius + Aun'Shi comme les vrais engines, et Arjac Foehammer comme snowball).

**team1 win-condition (PERDANT, jamais réalisée)** : focus-burst engine = Atlacoya TalonsOfTheEmperor scaling-finisher (+728/actif allié) séquencé APRÈS Tigurius StormOfWrath (Psychic NoBlocking armor-ignore) + Sho'syl Seeker/drone — mais nécessitait que les engines back-row adverses (Aun'Shi/Vitruvius row 6) soient ATTEIGNABLES, ce qui n'a jamais été le cas (roster mêlée/r2 + 1 sniper r3/r5 = désavantage de reach quasi-structurel).
→ Accord A.mine / B.theirs = **CONSENSUS** (B a correctement lu le turtle ranged-attrition de team1 et son flaw : tout clusterer bas).

### Séquences clés (résumé des action logs)

**Player A (team1, perdant) :**
- T4 : SeekerMissileFrequencyLock arme la mark sur Aun'Shi depuis une tuile SAFE (4,1, zéro move) → chunk 8536→5191 au tour suivant. Bon chip d'engine en sécurité — mais Aun'Shi a retraité row 6, inatteignable ensuite.
- T5 : focus-kill de Tanksmasha (bruiser reachable 10040) via MV71 drone one-shot depuis (4,1), ZÉRO exposition (le drone frappe avec le Damage stat de Sho'syl ~5781). Kill propre MAIS mal priorisé : Tanksmasha n'est pas un engine, et le tuer a FEED Arjac Foehammer (+2183). Exitor avancé inutilement à (5,3) (kill déjà sécurisé par le drone) = stranded forward.
- **Cascade fatale T5→tour adverse** : team1 clusterée bas (rows 0-1) → RadBombardment + Contamination loggés dans le state-file → team1 5-healthy → 3-damaged (TG + Atlacoya morts, 2 fragiles chunked) en une transition de tour. Foehammer aussi loggé (snowball post-Tanksmasha-kill).

**Player B (team2, vainqueur) :**
- T1-4 : avance ESPACÉE (wedge lâche, engines Aun'Shi+Vitruvius une rangée derrière les tanks Arjac/Pestillian/Tanksmasha) spécifiquement pour nier à Tigurius StormOfWrath un cluster 6-unités — discipline anti-blob qui l'a aussi gardé hors de la kill-zone.
- T5 (tour-kill) : Vitruvius FIRST (MasterAnnihilator mark) PUIS Pestillian/Aun'Shi pile sur Exitor-Rho 8032 (Direct-assassin) = kill garanti/overkill (ContagionsOfNurgle avait stripé son armure) ; Arjac (corps le plus durable) pour le K! profond sur Tigurius engine.
- Tanksmasha PERDU vers T4-5 (carry/anti-BigTarget) — le plus forward du wedge, caught dans la cascade adverse ou une réaction (B n'a pas vu le killing cascade clairement).

### Confrontation : consensus vs divergences

#### Mécaniques de CONSENSUS (rapportées des DEUX sides — cross-observable, recoupées gameconfig/i2)

1. **RadBombardment (Vitruvius)** : ligne droite Toxic Pierce70, chunke TOUS les units alignés en UN cast, Contamination + Suppress, longueur +1/round +1/heal-Mechanic, friendly-fire. A(theirs, a SUBI le chunk de toute sa ligne clusterée → TG+Atlacoya morts + 2 fragiles chunked) + B(mine, EXÉCUTÉ comme axe principal). gameconfig confirme (dmg max 3274-4001 Toxic, `nrOfHits:1` mais AoE pleine-ligne). → **DÉCISIF DE CE RUN** : un blob serré bas (rows 0-1) est la PIRE forme. ⚠ cross-validé les DEUX sides 3ᵉ fois sur seed 80000.
2. **MasterAnnihilator (Vitruvius)** : normal attack marque la cible → +1 hit pour toute attaque friendly (sauf Psychic), cap 5456, jusqu'à mort de Vitruvius ou re-mark différent. B(mine, Vitruvius FIRST puis pile = kill Exitor) + A(theirs, threat critical « mark-amplifier »). gameconfig verbatim confirmé.
3. **ContagionsOfNurgle (Pestillian)** : TRAIT aura armor-reduction croissante (R1-2 range1 / R3-4 range2 / R5+ range3 ; -20% / -40% overlapping). A(theirs, FixedArmor_Modification -341 sur Exitor/Sho'syl/drone) + B(mine, ContagionsOfNurgle_ArmorReduction1 sur Exitor+Tigurius amplifiant le focus). gameconfig confirme.
4. **SereneUnifier (Aun'Shi)** : cycle R1 SenseOfStone -50% dmg / R2 ZephyrsGrace +1 move / R3 StormOfFire +582 dmg, self+adjacents+T'au≤2hex, persiste 1 tour même Aun'Shi mort. A(theirs, threat high « -50%/+move/+582 cycle ») + B(mine, ZephyrsGrace +1 move actif ce match). gameconfig verbatim.
5. **StormOfWrath (Tigurius)** : Psychic Pierce100 NoBlocking, cible + jusqu'à 5 adjacents, bypasse armure ET Block (BigTarget/GuardianOrganism). A(mine, AoE armor-ignore) + B(theirs, threat critical « bypasses BigTarget/armor, punishes clusters »). gameconfig confirme.
6. **Foehammer (Arjac)** : +2183/Character défait (snowball), Stun, Ranged-tag → bypasse Terrifying. A(theirs, « killing Tanksmasha FED Arjac Foehammer ») + B(mine, anvil Resilient anchor). gameconfig confirme (déjà au wiki §5 depuis run #2).

#### Divergences (entre les deux observateurs)

1. **Source causale de la cascade fatale T5 : RadBombardment+Foehammer+Contamination (A) vs EnvEndBombardment (B)** — DIVERGENCE MAJEURE. A (about=theirs) attribue le wipe de sa ligne à **RadBombardment + Contamination** (noms d'events explicitement loggés dans son state-file) + Foehammer. B (about=theirs/mistakes) attribue le swing décisif à un **EnvEndBombardment environmental hazard** (confidence: med, « likely a board hazard ») et admet « I won largely BECAUSE of an environmental hazard, not purely through my own engine-denial ». **VERDICT : A a raison, B a mal lu.** Le combat s'est terminé round ~5 (3-4 endturns dans les action logs, both « turns_played:5 ») — BIEN avant le round-cap (~round 10) qui déclenche EnvEndBombardment (cf. H51, run #2). À T5 il ne peut PAS y avoir de bombardement de round-cap ; la cascade était l'alpha RadBombardment+mark+aura+Foehammer de B lui-même. B a sur-attribué sa propre victoire à un hazard absent. → **hypotheses.md H57 (self-play divergence A/B, A=vérifié-correct).**
2. **Aun'Shi : engine sous-exploité par B (auto-lecture) vs threat high par A** — B(mistakes) reconnaît avoir laissé Aun'Shi flank-exposé à (1,5) (poked 8536→5191) puis l'avoir rapatrié = engine sous-utilisé ; A le classe threat high et l'a chippé avec succès. Accord sur la VALEUR (engine fragile), divergence sur l'EXÉCUTION (A l'a chippé / B l'a mal protégé). Pas une mécanique — lecture d'exécution, pas portée au wiki.

### Erreurs identifiées (leçons, des deux sides)

- **A (perdant)** : a clusterée toute sa ligne en blob serré rows 0-1 = l'EXACT anti-pattern seed-80000 (pire forme vs RadBombardment ligne) → TG+Atlacoya+drone wipe en un cast. ESPACER pour ne donner qu'1-2 cibles par ligne.
- **A** : mal priorisé le kill — meilleur tour dépensé sur Tanksmasha (bruiser non-engine) pendant que les vrais engines (Aun'Shi/Vitruvius) restaient intouchés row 6 ; reach quasi-structurellement insuffisant aurait dû être FLAGGÉ au recon → chiper Vitruvius/Aun'Shi avec Sho'syl chaque tour, pas le bruiser.
- **A** : tuer Tanksmasha (un Character) a FEED Foehammer (+2183) sans sécuriser d'avantage board = trade net-négatif une fois l'alpha adverse landé.
- **A** : over-passif T3-4 (hold sans reaction-engine en roster) → tempo gratuit donné à B pour positionner sa ligne ranged en sécurité ; Exitor (anti-armor précieux) over-extended à (5,3) pour un kill déjà sécurisé.
- **B (vainqueur)** : a mené avec son carry Tanksmasha le plus forward (row 3-4) → perdu dans la cascade ; garder le carry une rangée plus profond dans le wedge.
- **B** : Aun'Shi flank-exposé (1,5) early → poked 8536→5191 avant rapatriement (flank-exposure d'un engine non-tank, doctrine H03/70001) ; garder centralement screené dès T1.
- **B** : sous-utilisé RadBombardment tôt (parfaitement aligné sur leur turtle mais a tapé en normale) ; et a mis-attribué sa victoire à un EnvEndBombardment absent (cf. divergence #1) — il a en réalité gagné par son propre engine ranged + discipline anti-cluster.

### Refs action logs

Action logs complets de CE run : `data/_sp_80000_A.json` + `data/_sp_80000_B.json` (supprimés post-teardown — séquences clés résumées ci-dessus).

---

## seed 80000 — winner=no-winner (round-cap mutual-wipe, standoff passif) (ts=2026-06-23)

> ⚠ **4ᵉ run distinct de la seed 80000** (cf. les 3 blocs ci-dessus : run #1 = team1 W ; run #2 = no-winner mutual-wipe EnvEndBombardment ; run #3 = team2 W par alpha RadBombardment à T5 sans round-cap). CE run = **no-winner / draw par EnvEndBombardment round-cap**, comme le run #2, mais via un **standoff QUASI-TOTALEMENT PASSIF** (action logs : A = 1 seul `move` sur tout le combat, B = ZÉRO `move` loggé ; le reste = `finish` en place + `endturn`). Aucun camp n'a fermé le combat → l'horloge l'a fermé pour eux.

### Rosters

| Équipe | Unités |
|--------|--------|
| **team1 (Player A / oracle, player 3)** | ultraTigurius (Tigurius) · tyranTyrantGuard (Tyrant Guard) · custoAtlacoya (Atlacoya) · admecRuststalker (Exitor-Rho) · tauMarksman (Sho'syl) |
| **team2 (Player B / oracle, player 4)** | spaceRockfist (Arjac) · tauAunShi (Aun'Shi) · orksNob (Tanksmasha) · admecDominus (Vitruvius) · deathPutrifier (Pestillian) |

### Adjudication

- A outcome_perceived = **L** (5 tours, infère L du dernier snapshot pré-game-over : team2 full-HP Tanksmasha + Resilient Arjac vs ses 3 fragiles ~1300 HP) ; B outcome_perceived = **uncertain** (4 tours, lit ça comme un round-cap no-winner draw). → **winner_consensus = false** (A croit team2 W ; B dit draw — pas d'accord sur un vainqueur).
- `rl_duel.py status --state-file data/_sp_80000_A.json` : `stage=None turn=None currentPlayer=None alive_by_team={}` → BATTLE FINIE, team gagnante = **None**. State runner finalisé/vidé post-game-over.
- Action logs (ground truth) : A = 1 move + 4 endturns ; B = 0 move + 4 endturns. **Standoff quasi-pur** (finish-en-place), aucun camp ne ferme.
- **authoritative_winner = no-winner** (round-cap EnvEndBombardment, telegraphé `EnvEndBombardment_Incoming` ~1 round avant, fire round ~5-6 et wipe les DEUX blobs ; runner winner=None, alive_by_team={}). Le « L » perçu par A est une INFÉRENCE du snapshot pré-bombardement, PAS un champ winner lu — la vérité runner = draw.

### Win-conditions

**team1 (A self / B reading) — CONSENSUS** : 2 engines ranged fragiles (Tigurius StormOfWrath Psychic NoBlocking AoE 6525 + Sho'syl SeekerMissile r5 + MV71 drones 6527, no-Resilient) screenés par un mur durable (Tyrant Guard BigTarget 12548 + Atlacoya Terrifying + Exitor Direct-assassin) ; SOURCE = Tigurius + Sho'syl à cut au plus tôt. A.mine ≈ B.theirs = **accord fort**. Faille reconnue des deux : roster majoritairement mêlée/courte-portée, UN seul r5 → ne peut pas atteindre l'engine row-9 adverse (Vitruvius).

**team2 (B self / A reading) — CONSENSUS** : noyau amplification/anvil = Vitruvius (RadBombardment ligne Toxic ranged bypasse Terrifying + MasterAnnihilator mark) + Pestillian (ContagionsOfNurgle armor-shred aura + ExplosiveMaladies) + Aun'Shi (SereneUnifier buff-cycle) buffant le cluster, Tanksmasha anti-BigTarget vs Tyrant Guard, Arjac Foehammer finisher Resilient. SOURCE = Vitruvius (held row 9, inatteignable par les mêlées de A) + Pestillian aura. A.theirs ≈ B.mine = **accord fort**.

### Séquences clés (résumé des action logs — détail dans les state-files, supprimés en cleanup)

**Player A (team1, perçoit L) :**
- 1 seul `move` sur tout le combat ; le reste = hold cluster rows 0-1 (Tigurius/Sho'syl/Exitor row 1 derrière TG/Atlacoya row 0). Plan = espacement anti-blob + ne pas over-extend, MAIS jamais réellement exécuté (jamais étalé sur plus de rangées).
- TG tenu stationnaire chaque tour pour armer GuardianOrganism (−33%, cap −1455/hit) → a absorbé les chips RadBombardment ligne sur row 0 comme prévu, MAIS n'a PAS protégé du round-cap board-wide (TG mort dans la cascade).
- N'a JAMAIS déployé Sho'syl Seeker/drones (seul reach r5) pour pressurer Vitruvius row 9 : a jugé chaque tuile de tir trop exposée → ZÉRO progrès offensif quand l'AoE a fire.

**Player B (team2, perçoit uncertain) :**
- ZÉRO `move` loggé ; Tanksmasha (move4) a poké (1,6) puis reculé (3,7) à répétition (bait sans commit) — JAMAIS engagé, fini full HP 10040.
- Erreur+correction : a mis-lu le glyph terrain drybush 'b' comme le Tyrant Guard, chargé Tanksmasha sur une tuile fantôme (UnstoppableMomentum non-collinéaire → charge PASSÉE dans le vide, mutated=False, stranded forward), puis rapatrié.
- Endgame 2v3 (ses 2 units rows 7-8 vs 3 ennemis ~1300-1600 rows 0-1) : distance trop grande, charge Tanksmasha en cooldown → impossible de convertir avant le round-cap. Pas de plan de clôture.

### Confrontation : consensus vs divergences

#### Mécaniques de CONSENSUS (rapportées des DEUX sides — cross-observable, recoupées gameconfig/i2)

1. **EnvEndBombardment (round-cap)** : effet moteur de round-cap, telegraphé `EnvEndBombardment_Incoming`, fire un nuke AoE board-wide → wipe les DEUX équipes (winner=None, draw). A(theirs, « board-wide, flipped 5v5 → 2v3, wiped both blobs ») + B(mine, « ~287-event cascade, stage=Finished winner=None, both sides still had units »). Confirmé runner (`alive_by_team={}`). gameconfig : `EnvEndBombardment_Incoming` = effet moteur connu (pas d'i2 source). → **3ᵉ confirmation self-play seed 80000** (runs #2, #4 + H51). ⚠ NUANCE de timing CE run : fire round ~5-6 (action logs : 4 endturns/side = round ~5), PAS le ~round 10 supposé par H51 — refinement de timing à flagger (le cap peut tomber plus tôt, ou le compteur de round ≠ tours-joueur).
2. **RadBombardment (Vitruvius)** : ligne droite Toxic Pierce70, hits « all units in a straight line » (FRIENDLY-FIRE incl. alliés), Contamination + Suppress, longueur 2 +1/round +1/heal-Mechanic. A(theirs, a subi le chip de sa front-line row 0 depuis row 9 ET observé le friendly-fire de la backline ennemie — Aun'Shi −1707, Vitruvius −1807, Pestillian −2409) + B(mine, ranged bypasse Terrifying). gameconfig confirme verbatim (3274-4001 Toxic, croissance ligne). → friendly-fire sur la propre backline = nouvelle observation A cross-cohérente avec le texte i2.
3. **StormOfWrath (Tigurius)** : Psychic Pierce100 NoBlocking, cible + jusqu'à 5 adjacents, bypasse armure ET block (BigTarget/GuardianOrganism). A(mine) + B(theirs, threat critical « bypasses ALL my armor/block »). gameconfig confirme.
4. **SereneUnifier (Aun'Shi)** : cycle R1 SenseOfStone −50% dmg / R2 ZephyrsGrace +1 move / R3 StormOfFire +582 dmg, self+adjacents+T'au≤2hex, persiste 1 tour même Aun'Shi mort. A(theirs, observé cyclant vers StormOfFire R3 sur les 5 units à son tour 5) + B(mine, ZephyrsGrace +1 move live). ⚠ **les DEUX confirment indépendamment : le NOM de l'effet dans `decisionView.effects` = vérité de la phase, PAS le label UI « tour » (placeholder figé « tour 3 »)**. gameconfig verbatim.
5. **ContagionsOfNurgle (Pestillian)** : TRAIT aura armor-reduction croissante (R1-2 range1 / R3-4 range2 / R5+ range3 ; −20% / −40% overlapping), chip à l'entrée. A(theirs, armor-shred aura) + B(mine, ArmorReduction1 confirmé, chip des deux côtés à l'entrée). gameconfig confirme.
6. **PutridExplosion (Pestillian)** : TRAIT — explose à la mort = 25% maxHP Toxic à tous les adjacents sauf Death Guard (friendly-fire). A(theirs, « finish at range to weaponize onto its own cluster ») + B(mine, friendly-fire risk en cluster). gameconfig confirme.

#### Divergences (entre observateurs)

1. **Issue perçue : A = L (team2 W) vs B = draw/uncertain (no-winner)** — A infère une défaite du dernier snapshot HP pré-bombardement (team2 survivants out-HP ses 3 fragiles) ; B lit correctement le round-cap mutual-wipe = no-winner. → **VERDICT : B a raison sur l'issue formelle (runner winner=None = draw)** ; A a raison sur le fait que la TRAJECTOIRE favorisait team2 (ses survivants étaient plus durables) — mais zéro-sum runner = draw, pas une L. Friction d'observabilité commune : pas de champ winner persisté post-Finished (les deux l'ont signalé). → **hypotheses.md : friction outil (champ winner non persisté).**
2. **Frame du matchup : A = « hold-and-bait-the-dive » vs réalité = engine ranged out-range (jamais besoin de diver)** — A admet en mistake avoir traité le combat comme un bait-the-melee alors que team2 était un ENGINE RANGED back-line (Tanksmasha n'a fait que poker). Pas une divergence A/B (B confirme avoir tenu en standoff aussi) — c'est une leçon partagée : **deux turtles face-à-face = le round-cap tranche**, l'un des deux DOIT fermer.

### Erreurs identifiées (leçons, des deux sides) — CONVERGENTES cette fois

- **A (#1 mistake)** : resté clusteré rows 0-1 TOUT le combat malgré avoir LU la doctrine anti-blob (H57/H51) — n'a jamais réellement étalé ses units → front = blob parfait quand RadBombardment (ligne) ET EnvEndBombardment (board-wide) ont hit, perte des deux tanks d'un coup. « row 0 = safe-from-melee » sur-pondéré, menace environnementale/area sous-pondérée.
- **A** : passivité totale — jamais utilisé son seul reach (Sho'syl Seeker r5 / drones) pour chiper Vitruvius row 9 → zéro progrès offensif au moment du cap. Un drone depuis une tuile modérément forward aurait au moins mis du chip sur l'engine fragile.
- **A** : n'a pas planifié autour du timing EnvEndBombardment malgré avoir vu `EnvEndBombardment_Incoming` telegraphé — aurait dû espacer / repositionner les tanks hors de la lane la plus dense avant la résolution.
- **B (#1 mistake)** : standoff over-passif sans plan de clôture — a tenu de nombreux sous-tours pendant que le compteur stagnait à « tour 4 ». Per doctrine 70061, un standoff qui ne ferme jamais perd au round-cap. Aurait dû commencer une avance cohésive screenée mid-game pour être en killing range AVANT le bombardement.
- **B** : endgame out-of-position — après le gros trade (2v3, 3 ennemis à one-shot HP), ses units 6-7 rangées trop loin + charge Tanksmasha en cooldown → impossible de cleanup les 3 cripples avant le cap. Garder Tanksmasha forward-mais-safe (pas rapatrié à fond), ou avancer le cluster cohésivement plus tôt = la W.
- **B** : mis-lu le glyph terrain 'b' (drybush) comme le Tyrant Guard → charge fantôme stranded forward. Toujours cross-check les positions via `status` (ground truth), pas l'ASCII map quand les lettres collisionnent.
- **LEÇON PARTAGÉE (les DEUX, convergente)** : **deux turtles passifs face-à-face sur seed 80000 = round-cap EnvEndBombardment no-winner garanti.** Le round-cap est une HORLOGE DURE : un camp DOIT forcer une clôture cohésive (grind les anvils lents round 5-6, avancer screené) ; la passivité mutuelle remet la décision au hazard environnemental, qui ne récompense personne (draw).

### Refs action logs

Action logs complets de CE run : `data/_sp_80000_A.json` (1 move + 4 endturns) + `data/_sp_80000_B.json` (0 move + 4 endturns) — supprimés post-teardown ; séquences clés (standoff passif → round-cap) résumées ci-dessus.

---

## seed 80000 — winner=no-winner (round-cap mutual-wipe, QUALITY-AHEAD non converti) (ts=2026-06-23-antipassivity)

> 5ᵉ run self-play seed 80000. **DISTINCT des 4 précédents** : ce run n'est PAS un standoff passif — A a **activement tué 3 héros ennemis** (Tanksmasha + Vitruvius via un StormOfWrath 2-for-1, puis Aun'Shi) et a fini **4v2 EN AVANCE**… et a quand même subi le round-cap no-winner (double-loss). Leçon centrale : **être quality-ahead ne sauve PAS du cap — il faut CONVERTIR avant l'horloge.**

### Rosters

| Équipe | Unités |
|--------|--------|
| **team1 (Player A / oracle)** | ultraTigurius (Tigurius) · tyranTyrantGuard (Tyrant Guard) · custoAtlacoya (Atlacoya) · admecRuststalker (Exitor-Rho) · tauMarksman (Sho'syl) |
| **team2 (Player B / oracle)** | spaceRockfist (Arjac) · tauAunShi (Aun'Shi) · orksNob (Tanksmasha) · admecDominus (Vitruvius) · deathPutrifier (Pestillian) |

### Adjudication

- A outcome_perceived = **L** ; B outcome_perceived = **L** → les DEUX se perçoivent perdants (no-winner = double-loss).
- `rl_duel.py status --state-file data/_sp_80000_A.json` : `stage=None turn=None currentPlayer=None alive_by_team={}` + *« BATTLE FINIE — team gagnante : None »*.
- **authoritative_winner = no-winner (round-cap / mutual-wipe)** — EnvEndBombardment board-wide a wipe les deux équipes (winner=None).
- **winner_consensus = true** (les deux conviennent : pas de vainqueur ; B a explicitement lu le round-cap mutual-wipe, A a perçu "L" en inférant que la trajectoire favorisait team2 — mais le runner = draw formel).

### Win-conditions (consensus croisé)

**team1 win-condition** (A.mine ≈ B.theirs = **CONSENSUS**) : moteur armor/block-bypass — **Tigurius StormOfWrath** (Psychic NoBlocking AoE Pierce100, cible + adjacents) comme cluster-deleter + **Exitor-Rho CordClaw** (4-hit Direct Pierce100, bat Resilient ET TerminatorArmour) + **Atlacoya TalonsOfTheEmperor** (+728/actif allié, Direct vs Psyker) comme tueurs d'anvil ; Sho'syl markerlight en setup. B identifie correctement Tigurius (AoE) + Sho'syl (carry ranged) + Exitor (Direct armor-bypass).

**team2 win-condition** (B.mine ≈ A.theirs = **CONSENSUS**) : moteur buff/sustain escaladant — **Aun'Shi SereneUnifier** (cycle R1 −50% / R2 +1 move / R3 +582 dmg) + **InspiredToGreatness** (réutilise un actif allié + heal) comme SOURCE ; amplifié par **Vitruvius** (Mechanic-repair de l'Arjac Resilient + MasterAnnihilator mark +1 hit + RadBombardment ligne croissante) ; front = 2 anvils Resilient lents (Arjac TerminatorArmour+AnvilShield, Pestillian explodes+contagion) pour staller jusqu'au round-cap. A identifie correctement Aun'Shi cycle + Vitruvius repair/mark comme les vrais engines.

### Séquences clés (résumé des action logs)

**Player A (team1) — agressif et correct mécaniquement :**
- **T4 — la meilleure play du match** : StormOfWrath sur **Tanksmasha** (adjacent à Vitruvius) → le splash AoE Psychic a tué Tanksmasha (carry) ET splash-tué Vitruvius (repair-engine) en UN cast = **2 héros pour 0 coût** (5v5 → 5v3, zéro perte). Clusterer l'ennemi = 2-for-1 gratuit.
- Séquencé Tigurius + TG actives AVANT Atlacoya → TalonsOfTheEmperor pumpé (+728/actif) pour fiabiliser le kill du cluster.
- Aun'Shi (engine #1 visé correctement) chunké au markerlight puis K!'d (868→0) par le TG — mais au tour même où EnvEndBombardment a fire.
- T5 (le tour coûteux) : A a CONSOLIDÉ (sorti Atlacoya de la portée du Foehammer désormais armé ~5094) au lieu de forcer une clôture → a brûlé le tour de conversion pendant que le cap s'armait. Atlacoya est quand même mort sur le tour ennemi (mêlée après ZephyrsGrace +1 move a fermé la distance).

**Player B (team2) :**
- Subi le double-kill StormOfWrath T4 (Tanksmasha+Vitruvius), puis perdu Aun'Shi tardivement → réduit à 2 corps durables (Arjac Resilient + Pestillian).
- Foehammer s'est armé via les 2 kills (devenu ~4730-5094 + Stun, range 2) = one-shot sur tout sub-5k → a delete l'Atlacoya fragile de A et menaçait les fragiles restants.
- B a correctement lu le round-cap : ses 2 survivants (Arjac TermArmour-immune au bombardement, Pestillian durable) étaient les corps qui auraient « survécu » la trajectoire — mais le runner = no-winner.

### Confrontation : consensus vs divergences

#### Mécaniques de CONSENSUS (rapportées des DEUX sides — cross-observable, recoupées gameconfig)

1. **StormOfWrath (Tigurius)** — Psychic NoBlocking AoE, cible **+ jusqu'à 5 adjacents** : A (mine, livre un **2-for-1** Tanksmasha+Vitruvius adjacents) + B (theirs, threat critical « 6-target Psychic NoBlocking, ignores armor/block/SenseOfStone-resist »). gameconfig verbatim (« a unit within 2 hexes and up to 5 adjacent units », Pierce100 NoBlocking). → **clusterer l'ennemi = double-kill gratuit**, nouvelle instance vs runs précédents (ici Tanksmasha+Vitruvius).
2. **Foehammer (Arjac)** — +2183 dmg **par Character défait des DEUX camps** ce combat + Stun, range 2 : A (theirs, « après mes 2 kills devenu ~4730-5094 one-shot ») + B (mine, « ramp partially applied — 2 dead Characters were on MY side at the time, confirming count includes both teams »). gameconfig verbatim (« For each Character that has been defeated in this battle, +2183 »). → **CONSENSUS sur le both-teams-count** : tuer des héros ENNEMIS arme AUSSI l'Arjac ennemi — le snowball coupe dans les deux sens, garder les fragiles HORS de sa r2 en late-game.
3. **TalonsOfTheEmperor (Atlacoya)** — +728/actif allié cumulatif, Direct vs Psyker/adjacent-Custodes : A (mine, plan jusqu'à 6318 après séquençage) + B (theirs, « scales +728/friendly-ability-used, stun denies its scaling active »). gameconfig verbatim.
4. **MasterAnnihilator (Vitruvius)** — mark : +1 hit pour toute attaque alliée vs marqué sauf Psychic, cap 5456 : A (theirs, « chunked my TG 12548→6669 ») + B (mine, « mark + Tanksmasha BeastSlayer = 12548→6669 in one turn »). gameconfig verbatim.
5. **SereneUnifier (Aun'Shi)** — cycle R1 SenseOfStone −50% / R2 ZephyrsGrace +1 move / R3 StormOfFire +582 dmg, self+adjacents+T'au≤2hex, persiste 1 tour même Aun'Shi mort : A (theirs, observé cyclant, « +1 move = pourquoi l'ennemi a fermé la distance plus vite ») + B (mine, « -50% let my 3-unit knot survive untouched »). gameconfig verbatim.
6. **InspiredToGreatness (Aun'Shi)** — réutilise un actif allié adjacent + heal/repair : B (mine, « refreshed Arjac's on-cooldown Foehammer + healed +~1496 »). gameconfig verbatim (1091 / 4365 si non encore utilisé). [confirmé un seul side ce run — candidate, mais déjà au wiki]
7. **EnvEndBombardment (round-cap)** — telegraphé `EnvEndBombardment_Incoming` (RemainingTurns=1), puis nuke board-wide → wipe les DEUX équipes, winner=None : A (theirs, « fired ~AmountOfTurnsStartedByCurrentPlayer=12 ≈ round 6, NOT round 10 ; a no-winner = double-loss même en étant 4v2 ahead ») + B (mine, « Aun'Shi 5989→868, Pestillian 12047→4820, Arjac TermArmour took 0 »). Confirmé runner (`alive_by_team={}`). → **5ᵉ confirmation self-play seed 80000** + **nuance majeure** : A était QUALITY-AHEAD 4v2 et a quand même subi le no-winner → être en avance ne sauve PAS du cap.

#### Divergences (entre observateurs)

1. **Issue perçue : A = "L" vs B = "L" — accord sur l'issue, mais cadrage différent** — A perçoit "L" en inférant que team2 out-durait sur la trajectoire (Arjac TermArmour immune au bombardement + Pestillian durable survivaient, ses 3 fragiles non). B perçoit "L" en lisant le round-cap mutual-wipe formel. → **PAS une vraie divergence** : les deux conviennent du no-winner ; nuance = A pense que la trajectoire favorisait team2, B la lit comme un double-loss neutre. Le runner tranche : **no-winner = draw formel, double-loss en zéro-sum**.
2. **Friction d'observabilité COMMUNE (les deux la signalent)** — `decisionView` NE surface PAS `EnvEndBombardment_Incoming` dans les sections EFFETS CRITIQUES / EFFETS ACTIFS ; il n'apparaît QUE dans le dump brut de cascade (`Effect_Refresh EnvEndBombardment_Incoming RemainingTurns=1`). A : « j'avais zéro warning in-view que le cap était à 1 tick → aurait changé ma décision T5 ». B : « visible seulement comme "(+179 events)" tronqué dans la queue de cascade, facile à rater ». → **hypotheses.md : friction outil (countdown round-cap non surfacé en vue).**

### Erreurs identifiées (leçons, des deux sides)

- **A (#1 = LA loss)** : **CONVERSION FAILURE**. Quality-ahead tout le combat (3 héros ennemis tués avant d'en perdre 1, fini 4v2 up) mais un no-winner round-cap est un **double-LOSS, pas un draw favorable**. Le but était de FERMER avant le cap — pas fait. Le tour T5 « hold / sortir du Foehammer / reset actives » était doctrine-correct EN ISOLATION mais a brûlé le tour de conversion alors que le cap s'armait : avec l'horloge telegraphée, le clock OVERRIDE le « kill-or-hold » — committer une clôture décisive un tour plus tôt, accepter un trade de corps pour continuer à tuer.
- **A** : sous-pondéré l'horloge EnvEndBombardment **malgré que ce soit LE failure documenté de seed 80000 dans sa propre doctrine** → aurait dû front-loader l'agression T3-4 pour éliminer les anvils lents avant round 6.
- **A** : Atlacoya (carry fragile 4493) laissée à portée de trade — sortie de la r2 Foehammer mais morte quand même sur le tour ennemi (ZephyrsGrace +1 move a étendu la reach ennemie au-delà de l'overlay de danger). → reculer les fragiles **un rang de plus** quand un +move buff ennemi est actif.
- **A** : markerlight Sho'syl mis sur Vitruvius (mort au splash de toute façon = mark gâchée) au lieu de setup le kill d'Aun'Shi un tour plus tôt → l'engine #1 aurait pu tomber avant le cap.
- **B (#1 = root cause de SA perte)** : **T5 over-extension de DEUX corps non-Resilient** (Vitruvius mark-engine 9k + Tanksmasha carry 10k) en row 5 contre un core ranged-focus connu (StormOfWrath NoBlocking + Exitor Direct + Sho'syl). SenseOfStone −50% NE suffit PAS à sauver des corps non-Resilient d'un focus 5-unités. Doctrine H03 violée littéralement — engager avec SEULEMENT des corps Resilient (Arjac/Pestillian) forward, garder Vitruvius+Aun'Shi shallow.
- **B** : mis-targeting — a grindé le Tyrant Guard ANVIL 12.5k (low-value attrition, exactement ce que l'ennemi veut) au lieu de setup des kills sur des carries plus softs ; ça a coûté ses 2 meilleurs corps non-anvil.
- **B** : mismatch roster/tempo — équipe quasi toute mêlée lente (move2/2/3) SANS reach tool (r3+/deep-strike/flyer, Arjac TeleportStrike dépensé) vs un core ranged back-row → **structurellement injoignable** ; aurait dû flagger « likely-loss matchup » au recon et jouer un all-in cohésif screené, pas feeder des engines forward.
- **LEÇON CENTRALE (les DEUX, convergente)** : **sur seed 80000, le round-cap EnvEndBombardment est une horloge DURE qui fire ~round 6 (PAS round 10) et donne un no-winner = double-LOSS — même en étant 4v2 EN AVANCE.** Être quality-ahead ne convertit PAS tout seul : un camp DOIT FERMER (finir les anvils lents round 5-6, accepter un body-trade pour continuer à tuer) AVANT le cap. La passivité/consolidation au tour de conversion, même doctrine-correcte en isolation, est la cause proximale de la non-conversion.

### Refs action logs

Action logs complets de CE run : `data/_sp_80000_A.json` (5 turns, dont le StormOfWrath 2-for-1 T4) + `data/_sp_80000_B.json` (4 turns, dont le T5 over-extension décisif) — supprimés post-teardown ; séquences clés résumées ci-dessus.

---

## seed 80000 — winner=no-winner (ts=2026-06-23-roundcap)

> ⚠ **Run DISTINCT** des blocs seed-80000 précédents (run #1 W team1 ; #4 standoff passif no-winner ; #5 quality-ahead non-converti no-winner). Mêmes rosters/teams, **outcome = no-winner round-cap (EnvEndBombardment mutual-wipe)**. C'est la **6ᵉ confirmation** du pattern « pas de clôture avant le cap → double-LOSS », ici vue depuis la perspective NUMÉRIQUE INVERSE des runs précédents (B était 5v2 DEVANT, A 2v5 derrière).

### Rosters

| Équipe | Unités |
|--------|--------|
| **team1 (Player A / oracle)** | ultraTigurius (Tigurius) · tyranTyrantGuard (Tyrant Guard) · custoAtlacoya (Atlacoya) · admecRuststalker (Exitor-Rho) · tauMarksman (Sho'syl) |
| **team2 (Player B / oracle)** | spaceRockfist (Arjac) · tauAunShi (Aun'Shi) · orksNob (Tanksmasha) · admecDominus (Vitruvius) · deathPutrifier (Pestillian) |

### Adjudication

- A outcome_perceived = **L** (no-winner double-defeat) ; B outcome_perceived = **uncertain** (5v2 dominant mais wipe board-wide).
- `rl_duel.py status --state-file data/_sp_80000_A.json` : `stage=None turn=None alive_by_team={}` → *BATTLE FINIE — team gagnante : None*.
- **authoritative_winner = no-winner** (round-cap EnvEndBombardment mutual-wipe).
- **winner_consensus = true** : les DEUX players décrivent INDÉPENDAMMENT le MÊME fire EnvEndBombardment wipant les deux camps (winner=None, alive_by_team={}). A le nomme « no-winner = double-LOSS », B « no-winner / double-defeat despite a dominant 5v2 ». Pas de désaccord sur l'issue.

### Win-conditions (confrontation croisée)

- **team1 win-condition** : Tigurius StormOfWrath AoE Psychic NoBlocking Pierce100 (cluster-burst bypassant TermArmour/armure) = engine SOURCE ; Tyrant Guard (BigTarget/GuardianOrganism −33% + Synapse) = anvil-screen ; Sho'syl SeekerMissile delayed-nuke = softening ranged.
  → **CONSENSUS A.mine / B.theirs** : B a correctement identifié Tigurius (AoE) + Sho'syl (delayed nuke) + Exitor-Rho (assassin Direct) comme les dealers à couper, et le roster « screen+chip turtle sans pump central ».
- **team2 win-condition** : Aun'Shi SereneUnifier engine round-cyclique (R1 −50% / R2 +move / R3 +582 dmg) + InspiredToGreatness heal/re-use = sustain hub ; Vitruvius MasterAnnihilator mark (+1 hit) + RadBombardment + Mechanic repair = amplificateur ; Tanksmasha BeastSlayer carry vs BigTarget ; Arjac/Pestillian Resilient anvils.
  → **CONSENSUS A.theirs / B.mine** : A a correctement identifié Aun'Shi cycle + Vitruvius amplificateur/repair comme les vrais engines (et le repair/heal de Tanksmasha 3249→9232 mid-game).

### Séquences clés (résumé des action logs — supprimés post-teardown)

**Player A (team1, 5 turns)** : hold cohésif du cluster (TG GuardianOrganism + Tigurius PsychicFortress) row 2 T3-5 pour bait le dive ; T contact : Tigurius poussé à (3,5, danger-2) → StormOfWrath splash le cluster gauche packé (Arjac+Vitruvius+Aun'Shi ~2.6-2.7k chacun, bypass TermArmour). **Coût** : Tigurius + Exitor focus-killés le tour ennemi suivant (6525+8032 PV) → collapse 4v5 → 2v5. Final turn (bombardement imminent, 2v5) : focus TG+Atlacoya sur Tanksmasha adjacent → chunké 9232→738 mais **block BeastSlayer = under-kill (survécu)**.

**Player B (team2, 6 turns)** : a tué Tigurius le tour de son dive à (3,5) [Vitruvius normale = mark MasterAnnihilator + Pestillian = dead], Sho'syl à (6,2) [Tanksmasha normale + GetStuckIn bonus hit = dead], Exitor-Rho à (3,3) [Tanksmasha normale K?] → **5v2**. Rescue de Tanksmasha (chunké 3249 par SeekerMissile) via Aun'Shi InspiredToGreatness (+5983 → 9232). **N'a PAS pu fermer les 2 derniers tanks (TG 12548 + Atlacoya 8032 = 20580 PV restants) avant le fire EnvEndBombardment** → no-winner malgré 5v2.

### Key decisions (des 2 sides)

- **A** : recon des 2 rosters → wincon=StormOfWrath ; hold-bait T3-5 (H03 réciproque) ; commit Tigurius forward pour le splash 3-engines ; final focus sur Tanksmasha pour extraire de la valeur avant le wipe.
- **B** : identifier Sho'syl+Tigurius (dealers derrière le screen) comme kill-priority ; rescue Tanksmasha via InspiredToGreatness au lieu de l'abandonner ; séquencer Vitruvius (mark) FIRST dans le focus-stack ; Foehammer kill-snowball comme finisher.

### CONFRONTATION (consensus vs divergences)

- **CONSENSUS (cross-validé A+B, recoupé gameconfig)** :
  - **EnvEndBombardment round-cap = no-winner double-LOSS** : les 2 sides décrivent le même wipe board-wide. ⚠ confirme la doctrine déjà figée (run #4/#5 + RE ghidra nrOfRounds=8) : **l'avance numérique (5v2 ici) ne SAUVE PAS du cap** ; un camp DOIT être en clôture cohésive par son ~6ᵉ tour. 6ᵉ confirmation, perspective inverse (B devant).
  - **SereneUnifier** round-cyclique (R1 −50% / R2 +move / R3 +582) — gameconfig confirme. Déjà inscrit wiki.
  - **StormOfWrath** AoE Psychic NoBlocking Pierce100 cible+5 adjacents, bypass TermArmour — gameconfig confirme. Déjà inscrit.
  - **MasterAnnihilator** +1 hit follow-up (sauf Psychic), **Foehammer** +2183/Character mort, **SeekerMissile** delayed-nuke gated « survit au next turn », **InspiredToGreatness** re-use+heal — tous gameconfig-confirmés, déjà inscrits.
  - **friction COMMUNE** : `EnvEndBombardment_Incoming` surface trop tard dans decisionView (RemainingTurns=1) — A ET B la re-signalent (déjà connue, RE ghidra a ajouté l'horloge statique au `view`).
- **DIVERGENCE / erreur d'attribution** :
  - **A a labellé « BeastSnagga_ExtraBlock » le block qui a under-killé Tanksmasha (738 HP survécu)**. gameconfig : orksNob N'A PAS de trait BeastSnagga — il a **BeastSlayer** (`beastSlayerBlockChance:10, beastSlayerBlockAsMaxArmorPct:100` = 10% chance de bloquer 100% de son armure courante). La MÉCANIQUE (block probabiliste → K? under-kill) est RÉELLE et gameconfig-confirmée, mais le NOM du trait est faux. → flaggé hypotheses.md + nuance ajoutée au wiki Tanksmasha (recoupage gameconfig BeastSlayer).

### Refs action logs

`data/_sp_80000_A.json` (5 turns ; abilities loggées : StormOfWrath 1105 / SeekerMissile 1069 / TalonsOfTheEmperor 1195 / Foehammer-side absente côté A ; 17 finish) + `data/_sp_80000_B.json` (6 turns, 10 abilities) — **supprimés post-teardown** ; séquences clés résumées ci-dessus.

---

## seed 80003 — winner=no-winner (round-cap mutual-wipe) (ts=2026-06-23-conv80003)

### Rosters

| Équipe | Unités |
|--------|--------|
| **team1 (Player A / oracle, player 3)** | tyranDeathleaper (Deathleaper) · astraYarrick (Yarrick) · templSwordBrother (Godswyl) · ultraInceptorSgt (Bellator) · eldarJainZar (Jain Zar) |
| **team2 (Player B / oracle, player 4)** | blackPossession (Archimatos) · necroSpyder (Aleph-Null) · thousSorcerer (Thaumachus) · thousAhriman (Ahriman) · bloodSanguinary (Nicodemus) |

### Adjudication

- A outcome_perceived = **L** ; B outcome_perceived = **L** → **winner_consensus = true** (les 2 sont d'accord : double-defeat, aucun vainqueur)
- `rl_duel.py status --state-file data/_sp_80003_A.json` : `stage=None turn=None alive_by_team={}` + **« BATTLE FINIE — team gagnante : None »** = ground-truth runner
- **authoritative_winner = no-winner** (EnvEndBombardment round-cap mutual-wipe, winner=None) — PAS un draw favorable, un DOUBLE-LOSS zéro-sum.

### Win-conditions (consensus croisé A.mine ≈ B.theirs et A.theirs ≈ B.mine)

**team1 win-condition** : double summon-engine (Yarrick `SendInTheNextWave` Cadian Guardsmen +1/allié mort, max 5 + Bellator `DeathFromAbove` Inceptors = 1/round écoulé) → board-flood out-bodies (8v2) ; enablers Yarrick (Resilient r2 summoner) + Bellator (Flying MkXGravis summoner) tenus shallow pendant que le burst (Jain Zar SilentDeath Pierce80 AoE, Deathleaper Direct Pierce100, Godswyl ThunderousAssault stun+overkill) crack les engines adverses.
→ Accord A.mine / B.theirs : **CONSENSUS** (B a correctement identifié les 2 summoners Yarrick+Bellator comme la SOURCE compounding du body-count + Deathleaper/Jain Zar/Godswyl comme le spearhead).

**team2 win-condition** : Psychic burst-engine — Ahriman + Thaumachus (les 2 `WeaverOfFate`, Psychic Pierce100 NoBlocking armor-ignore) snowball à MAX dmg dès 3+ ennemis prennent du Psychic en un tour, feed par le splash de leur attaque normale ; source = les jumeaux WeaverOfFate (Archimatos, le summon-engine Incursion/Possession, perdu T7) ; sustain via Nicodemus (Healer) + ArcaneShield de Thaumachus.
→ Accord A.theirs / B.mine : **CONSENSUS** (A a correctement identifié Archimatos comme la SOURCE board-flip #1 + Ahriman/Thaumachus WeaverOfFate comme le snowball Psychic ; A a aussi correctement DÉMOTÉ Aleph-Null = repair INERT car seul Mechanical de son camp).

### Séquences clés (résumé des action logs — supprimés post-teardown)

**Player A (team1, 5 tours)** : ouverture cohésive trop prudente sur le grand gap row-0↔row-9 (T3/T5 = avances d'écran lentes). **T7 = KILL Archimatos** (Godswyl `ThunderousAssault`, **Unit_WasOverkilled=1** → pas de death-riposte + stun nié) = la SOURCE board-flip éliminée AVANT toute cascade Bloodletter (« best decision of the match »). ATTENTION le **push de ThunderousAssault a auto-déplacé Godswyl dans le hex vacant d'Archimatos (3,7)** = bruiser stranded deep → focus-killé le tour ennemi suivant (seule perte de héros, trap « push-into-vacated-hex »). Yarrick `SendInTheNextWave` (ab 1016) a summon **3 Guardsmen (pas 2)** — le +1/allié-mort a trigger sur la mort de Godswyl (scaling confirmé). T11 = **Deathleaper Direct kill sur Aleph-Null** → son **`Explodes` (25% maxHP ~2259 Direct) a friendly-fire Thaumachus (7530→5271) + Ahriman (absorbé par ArcaneShield 5483) + mon Deathleaper adjacent (8032→5773)** ; même tour, **Thaumachus tué** via Bellator Inceptors + Guardsmen multi-source. À T11 = **8v2 ET les 2 engines adverses morts**… mais le warning EnvEndBombardment armé T11 (« dans 2 tour(s) ») a fire AVANT le tour 13 → **no-winner**. Erreurs : deep-strike de Deathleaper GASPILLÉ (tenu en deep-strike T3, expiré à move3 normal T5) ; BATCHING bug v2 répété (`play --no-ai` splitté → T7 endturn premature, 3 units sans activation).

**Player B (team2, 5 tours)** : ouverture en holding-advance cohérent (bodies durables Aleph-Null/Nicodemus écranant les Psykers) pour bait le dive all-melee. **Dive-punish propre** : Godswyl (dove isolé à (3,7) après son push) focus-killé par 2 Psykers (Ahriman + Thaumachus, ab 69 normales) ; **Jain Zar one-shotée 6568** via **WeaverOfFate MAX** — déclenché parce que le **Psyker splash** de la normale (extra dmg à un ennemi ADJACENT à la cible) a touché 2 Guardsmen → 3 ennemis distincts en Psychic → les 2 jumeaux WeaverOfFate maxés (mécanique-clé du match). Ahriman `Doombolt` (ab 1102) cast une fois. N'a tué AUCUN summon-engine adverse (Yarrick/Bellator sat safe back-row) → le body-count compound a out-racé. **Over-extension** : Thaumachus déplacé row 6 + Aleph-Null forward (3,6) → les DEUX focus-killés en un tour ennemi (4→2 héros). Archimatos (son propre engine) perdu T1-de-contact derrière l'écran mais atteignable.

### Key decisions (des 2 sides)

- **A** : recon → wincon adverse = Archimatos (kill T7 prioritaire, overkill, la meilleure décision) ; DÉMOTE Aleph-Null (repair INERT, seul Mechanical → self-regen only, kill au RANGE pour l'Explodes splash sur leur cluster — doctrine engine-inerte appliquée correctement) ; lean sur ses 2 summon-engines pour out-body (8v2) sans sur-exposer les héros ; garder les unités SPREAD en portée Psychic pour nier WeaverOfFate.
- **B** : holding-advance pour bait l'all-melee dans la kill-box Psychic (lecture de profil correcte) ; dive-punish des 2 unités sur-engagées isolées (Godswyl puis Jain Zar via WeaverOfFate max) → lead héros 4v3 ; séquencer la normale Psyker pour feed le seuil 3-ennemis-Psychic.

### CONFRONTATION (consensus vs divergences)

- **CONSENSUS (cross-validé A+B, recoupé gameconfig)** :
  - **EnvEndBombardment round-cap = no-winner double-LOSS** : 7ᵉ confirmation, cas le plus FORT — A était **8v2 ET les 2 engines adverses morts**, et a quand même subi le wipe. Ni l'avance numérique massive NI la destruction des engines ne sauvent ; seule la CLÔTURE (ennemi à 0 unité) compte. Cause commune des 2 sides = tempo d'ouverture trop prudent (« should have closed 1-2 turns earlier / it's a RACE »). → wiki §3quater EnvEndBombardment (7ᵉ tac-note).
  - **WeaverOfFate** : 3+ ennemis prennent du Psychic en un tour → les 2 Psykers (Ahriman + Thaumachus) dealent MAX. gameconfig verbatim confirme. Le **feed via Psyker splash** (normale ranged → +dmg à un ennemi ADJACENT à la cible → atteint cheaply le seuil sur un cluster) est la mécanique-clé du match, observée live (one-shot Jain Zar 6568). → wiki §interactions (nouvelle entrée Psyker-splash → WeaverOfFate, distincte du feed-par-AoE StormOfWrath).
  - **LivingMetal** (Aleph-Null, regen % maxHP début de tour — chip non-létal ERASÉ : 1610→6330) — gameconfig confirme (`livingMetalHp:10` + Mechanical). Déjà au wiki ; re-confirmé self-play.
  - **Explodes** (Aleph-Null, 25% maxHP Direct à TOUS les adjacents, **friendly-fire leur propre cluster** : 2259 sur Thaumachus + Ahriman-shielded + mon Deathleaper adjacent) — gameconfig confirme (`explodesDmg:25`). Déjà au wiki ; re-confirmé (exploit canonique = tuer un Explodes AU CENTRE du cluster ennemi = AoE gratuit).
  - **SendInTheNextWave** (2 Guardsmen +1/allié-mort, max 5 — A a observé 3 sur la mort de Godswyl) + **DeathFromAbove** (1 Inceptor/round écoulé) — gameconfig confirme les 2 verbatim. Déjà au wiki.
  - **ArcaneShield** (Thaumachus, bouclier sur l'allié le + proche ≤2 hex — a absorbé le hit Explode sur Ahriman) — base gameconfig 4001 HP (les 5483 live = scaling). Déjà au wiki.
- **DIVERGENCE (priorité, PAS mécanique)** :
  - **Quel summon-engine prioriser face au round-cap** : A a tué l'engine *Psychic* board-flip (Archimatos, crédité best-decision) ; B identifie comme #1 erreur de N'avoir tué AUCUN engine et désigne **Bellator `DeathFromAbove`** (round-scalant) comme la critical clock à tuer EARLY. Mécaniques concordantes (gameconfig), désaccord de PRIORISATION uniquement → flaggé **hypotheses.md H63** (résolution proposée : prioriser l'engine dont l'output COMPOUND avec le round# > engine à output borné). n=1, non tranché.

### Refs action logs

`data/_sp_80003_A.json` (team1, 5 tours ; 8 abilities : SwordBrother/Godswyl 1068+1043 + normale 69, Yarrick SendInTheNextWave 1016, 2× ab 1120, Bellator 1003, Deathleaper/Jain Zar normale 69 ; 11 finish, 14 move) + `data/_sp_80003_B.json` (team2, 5 tours ; 8 abilities : 5× normale Psyker 69 [le feed WeaverOfFate], Nicodemus/Archimatos 1007, Ahriman Doombolt 1102 ; 9 finish, 12 move) — **supprimés post-teardown** ; séquences clés résumées ci-dessus.

---

## seed 80003 — winner=team2 (ts=2026-06-23-batchfix)

> **MÊMES rosters que le bloc `conv80003` ci-dessus, mais MATCH DISTINCT** : ici team2 **CLÔTURE par élimination en 4 tours** (PAS de round-cap — B a confirmé via la cascade finale « last Inceptor 2558→0 TUE, NO EnvEndBombardment event, full team alive »). C'est le contre-exemple positif du bloc `conv80003` (no-winner round-cap) : même matchup, mais le Psyker-trio a **converti le kill assez vite pour fermer avant l'horloge**. La leçon `conv80003` (« seule la CLÔTURE compte, pas l'avance ») est ici exécutée par team2.

### Rosters

| Équipe | Unités |
|--------|--------|
| **team1 (Player A / oracle, player 3)** | tyranDeathleaper (Deathleaper) · astraYarrick (Yarrick) · templSwordBrother (Godswyl) · ultraInceptorSgt (Bellator) · eldarJainZar (Jain Zar) |
| **team2 (Player B / oracle, player 4)** | blackPossession (Archimatos) · necroSpyder (Aleph-Null) · thousSorcerer (Thaumachus) · thousAhriman (Ahriman) · bloodSanguinary (Nicodemus) |

### Adjudication

- A outcome_perceived = **L** ; B outcome_perceived = **W** → **winner_consensus = true** (perspectives OPPOSÉES concordantes sur le même match)
- `rl_duel.py status --state-file data/_sp_80003_A.json` : `stage=None turn=None alive_by_team={}` + **« BATTLE FINIE — team gagnante : None »** = snapshot per-state purgé post-Finished (NON autoritatif, cf. frictions des 2 sides). Vérité = la cascade finale de B (élimination propre, full team B alive) + l'accord W/L A/B.
- **authoritative_winner = team2** (élimination de tous les héros team1 en 4 tours — PAS un round-cap).

### Win-conditions (consensus croisé A.mine ≈ B.theirs et A.theirs ≈ B.mine)

**team1 win-condition** : double summon-engine (Yarrick `SendInTheNextWave` Cadian Guardsmen +1/allié mort max 5 + Bellator `DeathFromAbove` 1 Inceptor/round écoulé 4001-5483HP) pour out-bodies le board, avec Jain Zar (`SilentDeath` Pierce80 3-target AoE + `TerrorsLament` aura) comme carry de mêlée convertissant l'avantage de corps. SOURCE = Yarrick+Bellator (les abilities de summon) ; ENABLER à protéger = Jain Zar (le carry). Jamais venu online : carry+bodies morts à la midline avant d'atteindre les engines adverses.
→ Accord A.mine / B.theirs : **CONSENSUS** (B identifie Deathleaper comme spearhead-carry + Yarrick/Bellator comme les 2 summon-engines refillant le body-count — concordant).

**team2 win-condition** : Psychic NoBlocking burst-trio snowball — Ahriman + Thaumachus + Archimatos (Pierce100 NoBlocking) bypass armor/MkXGravis/Terrifying ; le splash trait `Psyker` (50% à un ennemi ADJACENT à la cible par normale ranged) chunke une 2ᵉ cible par cast ; `WeaverOfFate` (Ahriman+Thaumachus) s'auto-arme à MAX dmg dès 3+ ennemis prennent du Psychic en un tour. SOURCE = les 2 jumeaux WeaverOfFate feedés par le splash ; backstop = summon-engines (Archimatos Incursion/Possession, Aleph-Null ScarabHive) + Nicodemus (Healer) sustain.
→ Accord A.theirs / B.mine : **CONSENSUS** (A identifie correctement le trio Psyker NoBlocking + dual-WeaverOfFate + Nicodemus sustain comme la kill-box, et que MkXGravis = ZÉRO protection vs NoBlocking).

### Séquences clés (résumé des action logs — supprimés post-teardown)

**Player A (team1, 4 tours)** : ouverture tempo correct sur le flood Bloodletter T1 (Yarrick summon K! un, Deathleaper K! un, board +2 Guardsmen → lead bref 7v5). T~3 = **ERREUR FATALE : consolidation des 4 corps survivants à la midline (rows 3-5)** = présente un cluster 3+ parfait à la dual-WeaverOfFate AoE → les 2 Psykers swing à MAX → **4 unités wipées en UN tour ennemi**. Meilleure décision = **Bellator `DeathFromAbove` sur Archimatos depuis un corps mourant (HP5)** → 2× Inceptors 5483HP qui chunkent l'engine 8034→4405 (les Inceptors persistent après la mort de Bellator). Deathleaper deep-strike GASPILLÉ (staging à (3,5) sans kill, mort à 2002 sans engine-kill). Dernier tour (2v7) = gamble Yarrick sur un K? Thaumachus qui roll bas (laissé à 1179) au lieu du K! Bloodletter garanti — moot mais mauvais principe.

**Player B (team2, 4 tours)** : holding-advance puis **dive-punish de l'isolé** : Deathleaper sur-divé à (3,5), 4 rows devant son support → focus-killé T2 par burst Psychic (Doombolt bypasse Terrifying). **Archimatos kill au RANGED** (Deathleaper + Bellator) → `Possession` spawn des corps gratuits (Blue Horror + Bloodletter) = board-presence pour la race. Tue les 2 Guardsmen le tour de leur spawn (deny le snowball Yarrick). Concentre le trio Psychic sur les engines (Bellator) + le carry (Jain Zar, killée T3 au Psychic ranged car `TerrorsLament` gute le mêlée). **Clôture Yarrick (Resilient) correctement T4** : 2 chips Psychic pour floorer à 356, puis **Aleph-Null `Particle` 5-hit** (multi-hit bat Resilient : floor-to-1 puis hit suivant tue depuis 1). Élimination → W.

### Key decisions (des 2 sides)

- **A** : recon correct (wincon adverse = trio Psyker NoBlocking + dual-WeaverOfFate, MkXGravis inutile, Nicodemus sustain) ; plan = gagner la numbers-war via summon-engines + land Jain Zar AoE. **Exécution ratée sur l'exposition** : a clusterisé au lieu de SPREAD vs une AoE NoBlocking, n'a tué AUCUNE tête Psyker avant de turtler dans la nuke-zone.
- **B** : a identifié le Deathleaper sur-divé isolé et commit les dealers Psychic en avant pour le burst (Doombolt bypasse Terrifying) plutôt que de turtler — la race round-cap impose de forcer la décision ; ranged-kill via Archimatos pour `Possession` free bodies ; tue le chaff Guardsmen au spawn ; clôture Yarrick Resilient par multi-hit.

### CONFRONTATION (consensus vs divergences)

- **CONSENSUS (cross-validé A+B, recoupé gameconfig)** :
  - **WeaverOfFate = 3+ ennemis prennent du Psychic en un tour → ce Psyker deal MAX dmg ce tour** : A (about=theirs, double max-swing wipe le cluster 4-unit) + B (about=mine, plan montre rolls fixés MAX 3613-3613 etc.). gameconfig verbatim : « In any turn where 3 or more enemy units have taken Psychic Damage, this unit will deal the maximum possible Damage with its attacks and abilities on that turn. » CONSENSUS.
  - **Trait Psyker splash (`psykerExtraDmg:50`) = +50% du dmg à un ennemi ADJACENT à la cible par normale ranged** : A (about=theirs, implicite via le double-dip) + B (about=mine, splashes 804/1506/2034/2467 observés sur Godswyl + atteint le seuil 3-ennemis cheaply). gameconfig verbatim. CONSENSUS — c'est le MOTEUR du seuil WeaverOfFate (1 cast = 2 cibles Psychic).
  - **MkXGravis / armor = ZÉRO protection vs Psychic NoBlocking** : A (about=mine, Bellator 8533→5 en un tour) + B (about=mine, Pierce100 NoBlocking ignore double-armor). gameconfig (NoBlocking/PiercingRatio100). CONSENSUS.
  - **Resilient battu par MULTI-HIT (floor-to-1 puis kill par le hit SUIVANT du même attack)** : A (about=mine, Yarrick Resilient) + B (about=theirs, Aleph-Null `Particle` 5-hit sur Yarrick : 354→floor→1→1→TUE). gameconfig Resilient verbatim : « its Health is instead reduced to 1 Health, unless Overkilled. » CONSENSUS — un single sub-overkill ne floore qu'à 1 ; il faut multi-hit OU overkill.
  - **TerrorsLament (Jain Zar) = -582 dmg + -1 hit aux MÊLÉE adjacents** : A (about=mine, sous-utilisée en back-anchor, ne protège que l'adjacent) + B (about=theirs, mêlée guté 420-790 / 232-908 vs Jain Zar → forcé à la tuer au Psychic ranged). gameconfig verbatim. CONSENSUS.
  - **Camouflage (Deathleaper) = ranged -1 hit (≤2 hex), -2 si >2 hex** : B (about=theirs, Doombolt 3→2 hits à dist2). gameconfig verbatim « -1 hit … increases to -2 if more than 2 hexes away ». A ne contre-observe pas explicitement (mentionne Camouflage dans son roster). Confirmé gameconfig.
  - **DeathFromAbove** (Bellator, 1 Inceptor/round écoulé, persiste même cast depuis un corps à 5HP) + **SendInTheNextWave** (Yarrick, 2 Guardsmen +1/allié mort) + **Possession** (Archimatos, ranged-kill spawn un corps gratuit) + **Explodes/LivingMetal** (Aleph-Null) — tous re-confirmés des 2 sides, déjà au wiki.
- **DIVERGENCE (perception de résultat, PAS mécanique)** :
  - **Round-cap vs élimination dans la lecture du status post-Finished** : B note explicitement que `status` post-Finished retourne `winner=None alive_by_team={}` — le MÊME affichage qu'un no-winner round-cap — alors que c'était une élimination PROPRE (cascade : last Inceptor 2558→0, AUCUN event EnvEndBombardment, full team B vivante). La harness ne distingue pas « j'ai éliminé » de « mutual round-cap wipe » dans le read post-Finished. **Le teardown qui lit winner=None ne DOIT PAS supposer un draw sans vérifier la cascade finale (élimination vs bombardement).** → friction d'outillage, flaggée hypotheses.md. (Ici tranché par l'accord W/L A/B + la cascade : élimination, team2.)

### Refs action logs

`data/_sp_80003_A.json` (team1, **4 tours** [4 endturns] ; 24 actions : 6 abilities = SendInTheNextWave 1016, ab 1120, 2× normale 69, ab 1043, DeathFromAbove 1003 ; 2 finish, 12 move) + `data/_sp_80003_B.json` (team2, **4 tours** [4 endturns] ; 43 actions : 19 abilities = **16× normale Psyker 69 [le feed splash→WeaverOfFate]**, Ahriman Doombolt 1102, ab 1021, ab 1007 ; 2 finish, 18 move) — **archivés** dans `data/selfplay-logs/sp_80003_2026-06-23-batchfix.json` puis **supprimés post-teardown** ; séquences clés résumées ci-dessus.
