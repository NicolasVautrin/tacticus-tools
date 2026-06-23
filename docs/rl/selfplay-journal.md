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
