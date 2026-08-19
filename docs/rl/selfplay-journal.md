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

`data/_sp_80003_A.json` (team1, **4 tours** [4 endturns] ; 24 actions : 6 abilities = SendInTheNextWave 1016, ab 1120, 2× normale 69, ab 1043, DeathFromAbove 1003 ; 2 finish, 12 move) + `data/_sp_80003_B.json` (team2, **4 tours** [4 endturns] ; 43 actions : 19 abilities = **16× normale Psyker 69 [le feed splash→WeaverOfFate]**, Ahriman Doombolt 1102, ab 1021, ab 1007 ; 2 finish, 18 move) — **archivés** dans `logs/selfplay/sp_80003_2026-06-23-batchfix.json` puis **supprimés post-teardown** ; séquences clés résumées ci-dessus.

---

## seed 80031 — winner=no-result (MATCH NON JOUÉ — runner absent) (ts=2026-06-23-b5)

### Rosters

| Équipe | Unités |
|--------|--------|
| **team1 (Player A, playerId 11)** | INCONNU — jamais énuméré dans la BC statique (PredefinedUnits ne contient que le groupe enemy Id=12) ; aucun runner live n'a pu le résoudre. *(team2.theirs côté B suppose : thousTerminator · spaceWulfen · custoBladeChampion · orksKillaKan · admecDestroyer, lus dans une autre source seed BC `playerUnits` — NON CONFIRMÉ comme roster actif.)* |
| **team2 (Player B, playerId 12)** | emperNoiseMarine · genesBiophagus · tauMarksman · worldExecutions · admecManipulus *(vérifiable dans la BC statique PredefinedUnits Id=12 ; aucune unité jamais observée live)* |

### Adjudication

- **authoritative_winner = no-result** (ni élimination ni round-cap — la battle n'a JAMAIS démarré).
- `rl_duel.py status --state-file data/_sp_80031_A.json` : `stage=None turn=None currentPlayer=None alive_by_team={}` et **AUCUNE ligne `*** BATTLE FINIE — winner AUTORITATIF ***`** n'est imprimée. Le H59 ne tranche que post-Finished : ici il n'y a pas de `battleStatus.winner` à lire (runner inexistant), donc PAS de winner autoritatif. À distinguer d'un `no-winner` round-cap (qui exige une battle Finished).
- `rl_duel.py view --state-file …A.json` → `decisionView ERROR: runner 22 not found`. RPC `listRunners` (session 4) = `[]`. `observeBattle({runnerId:22})` → `ok:false, err 'runner 22 not found'`. Les deux state-files (`_sp_80031_A.json` / `_sp_80031_B.json`) sont bien formés et référencent `runnerId 22 / seed 80031` mais pointent un runner que le host n'a jamais enregistré.
- **winner_consensus = false** — il n'y a pas de vainqueur sur lequel s'accorder. A.outcome=`uncertain`, B.outcome=`uncertain`, `turns_played=0` des deux côtés : consensus, mais sur l'ÉCHEC du SETUP, pas sur un résultat de combat.

### CONFRONTATION (consensus vs divergences)

- **CONSENSUS (cross-validé A+B) — sur le BLOCKER, pas une mécanique de jeu** : runner 22 n'existe pas dans la session Frida 4. Les deux observateurs indépendants rapportent EXACTEMENT le même diagnostic, depuis la ground truth (pas un proxy) :
  - `listRunners` (session 4) = `[]` (registry vide, répété).
  - `observeBattle({runnerId:22})` → `ok:false`, err `runner 22 not found`.
  - `GET /api/selfplay/4/await?runnerId=22&player=3|4` → retourne INSTANTANÉMENT `{"error":"runner 22 not found"}` (NE bloque PAS jusqu'au timeout — donc la boucle de hand-off ne peut jamais atteindre `yourTurn`). A confirme via une await full-90s.
  - `rl_duel view/status --state-file` → `runner 22 not found` / `stage=None`.
  - **Cause probable** : le SETUP n'a jamais complété l'enregistrement `buildPatchedRunner` du runner partagé 22 en session 4, OU un reinject après SETUP a vidé le registry in-memory (cf. `feedback_host_restart_kills_mirror` : un host restart / reinject perd l'état mémoire du runner).
- **AUCUNE mécanique de jeu cross-observable** (mechanics about="theirs") n'a pu être collectée : zéro tour joué, zéro decisionView, zéro effet vu live. Les `threat_cards` de A sont toutes taggées **INFERRED from id only** (LOW confidence, aucun recon gameconfig/i2 ni decisionView possible) → **non promouvables au wiki** (rien sans consensus OU recoupage gameconfig explicite ; ici ni l'un ni l'autre n'est observé live).
- **DIVERGENCE (lecture du roster team1, PAS une mécanique)** : A déclare team1 INCONNU (absent de la BC statique). B suppose un roster team1 (thousTerminator/spaceWulfen/custoBladeChampion/orksKillaKan/admecDestroyer) lu dans une *autre* source `playerUnits` de la seed BC, mais le flagge lui-même **UNCONFIRMED**. Aucun des deux n'a observé team1 live → roster team1 non établi. → hypotheses.md (self-play divergence A/B).

### Key decisions (des 2 sides)

- **A** : a awaité son tour d'abord (correct — le runner live se résout via le hand-off host, pas le state-file disque) ; a diagnostiqué le blocker depuis la ground truth (listRunners=[] + observeBattle err + await full-90s = erreur, PAS `timedOut:true`), pas un proxy ; a **REFUSÉ de s'auto-réparer** (pas de build/amorce/nav/dispose) car minter un nouveau runnerId désyncherait la coordination shared-runner avec B et corromprait le match.
- **B** : a poll `/await` + `listRunners` sur ~30s pour écarter une race de SETUP (le runner n'est jamais apparu) ; a **REFUSÉ de rebuild runner 22** (corromprait l'arène shared dont A dépend) ; a complété le recon one-time (SKILL §6/§7 + doctrine-learned H02/H03/H04/H11) pour appliquer la doctrine SI le runner avait existé. Note outillage : absence d'endpoint `selfplay/:id/status` (seulement `/await`) ralentit le diagnostic.

### Refs action logs

`data/_sp_80031_A.json` / `data/_sp_80031_B.json` (team1=0 actions, team2=0 actions — **aucun tour joué**, `action_log=[]` des deux côtés) — archivés dans `logs/selfplay/sp_80031_2026-06-23-b5.json` (winner=no-result) puis supprimés post-teardown. Pas de séquence de jeu à résumer : le match n'a jamais démarré (runner 22 absent du host).

---

## seed 80020 — winner=no-result (MATCH NON JOUÉ — runner absent) (ts=2026-06-23-b5)

### Rosters

| Équipe | Unités |
|--------|--------|
| **team1 (Player A, playerId 11)** | genesMagus (Xybia) · custoKyrus (Tyrith) · astraDreir (Dreir) · worldEightbound (Azkor) · eldarMauganRa (Maugan Ra) — *lus dans `playerUnits` des DEUX state-files (`myTeam=1` côté A) ; jamais observés live (decisionView/observeBattle impossibles).* |
| **team2 (Player B, playerId 12)** | orksRuntherd (Snotflogga) · tauMarksman (Sho'syl) · adeptHospitaller (Isabella) · eldarFarseer (Eldryon) · blackPossession (Archimatos) — *= seul groupe `PredefinedUnits` (Id=12) présent dans la BC statique ; `myTeam=2` côté B ; jamais observés live.* |

> **NB — correction vs seed 80031** : ici l'attribution d'équipe est RÉCUPÉRABLE depuis les state-files (`myTeam` différencie bien A=team1/B=team2, et `playerUnits` contient le roster team1). B avait conclu « team attribution impossible » faute de second groupe `PredefinedUnits` tagué TeamId — mais l'info est dans `myTeam`/`playerUnits`, pas dans la BC `PredefinedUnits`. La BC statique n'a effectivement qu'UN groupe (team2), parce que le SETUP a avorté avant de committer le déploiement deux-équipes.

### Adjudication

- **authoritative_winner = no-result** (ni élimination ni round-cap — la battle n'a JAMAIS démarré).
- `python scripts/python/rl_duel.py status --state-file data/_sp_80020_A.json` : `stage=None turn=None currentPlayer=None alive_by_team={}` et **AUCUNE ligne `*** BATTLE FINIE — winner AUTORITATIF ***`** n'est imprimée. Le H59 (lecture `battleStatus.winner` natif) ne tranche que post-Finished : ici il n'y a pas de battle Finished à lire (runner inexistant), donc PAS de winner autoritatif. À distinguer d'un `no-winner` round-cap (qui exige une battle Finished).
- 3 sondes indépendantes confirment l'absence du runner live (ground truth, pas un proxy) : (1) `rl_duel view --state-file …A.json` → `runner 24 not found` ; (2) `GET /api/selfplay/4/await?runnerId=24&player=3|4` → retourne **INSTANTANÉMENT** `{"error":"runner 24 not found"}` (NE bloque PAS jusqu'au timeout 90s — donc la boucle de hand-off ne peut jamais atteindre `yourTurn`), répété 4-7× par chaque side ; (3) `observeBattle({runnerId:24})` (session 4) → `ok:false, runner:null, err 'runner 24 not found'`.
- **Stale-tracker** : `/api/runners` liste TOUJOURS runnerId 24 (sessionId 4, `lastLabel:"StartMatch"`, jamais progressé) ET les runners 25-31 construits APRÈS 24. Le tracker host garde une entrée périmée alors que le registry IL2CPP-handle script-side a évincé le handle live du 24. Cap/eviction de registry probable : quand 25-31 ont été build, le 24 (le plus ancien encore actif) a été évincé du registry live, mais l'entrée host est restée.
- `action_log=[]` des deux côtés, `turns_played=0`. PredefinedUnits = 1 seul groupe (team2) → déploiement deux-équipes jamais committé.
- **winner_consensus = false** — il n'y a pas de vainqueur sur lequel s'accorder. A.outcome=`uncertain`, B.outcome=`uncertain`, `turns_played=0` des deux : consensus, mais sur l'ÉCHEC du SETUP, pas sur un résultat de combat.

### CONFRONTATION (consensus vs divergences)

- **CONSENSUS (cross-validé A+B) — sur le BLOCKER, PAS une mécanique de jeu** : runner 24 absent du registry live de la session Frida 4. Les deux observateurs indépendants rapportent EXACTEMENT le même diagnostic depuis la ground truth (3 chemins d'accès concordants : `await` instantané-en-erreur, `view/decisionView`, `observeBattle`). Cause probable : SETUP n'a jamais complété l'enregistrement du runner partagé 24, OU eviction par cap de registry quand les runners 25-31 ont été build après (cf. `feedback_host_restart_kills_mirror` : un reinject/restart perd l'état mémoire du runner ; ici plutôt un cap d'eviction, le host tournant toujours).
- **AUCUNE mécanique de jeu cross-observable** (mechanics about="theirs") n'a pu être collectée : zéro tour, zéro decisionView, zéro effet vu live. Les `mechanics` rapportées par B (Incursion/Possession Archimatos, RitesOfRestoration Isabella, Executioner Eldryon, MV71/SeekerMissile Sho'syl) sont TOUTES taggées **recon-only, confidence=low, NOT observed in battle** → **non promouvables au wiki** (rien sans consensus d'OBSERVATION ou recoupage gameconfig explicite ; ici les abilities existent en gameconfig mais ne sont PAS un consensus issu du match — elles sont déjà documentées au wiki par ailleurs, non re-tagguées self-play). A n'a fourni aucune mechanic (roster mine indéterminé de son point de vue).
- **DIVERGENCE (lecture des rosters, PAS une mécanique de jeu)** : A déclare son propre roster INDÉTERMINÉ (runner introuvable → pas de recon) ; B déclare l'attribution d'équipe IMPOSSIBLE (un seul groupe PredefinedUnits non-tagué). Or les state-files CONTIENNENT `myTeam` + `playerUnits` qui tranchent : team1 = genesMagus/custoKyrus/astraDreir/worldEightbound/eldarMauganRa, team2 = le groupe PredefinedUnits Id=12. Aucun des deux n'a exploité ces champs → friction de lecture, pas une contradiction sur le jeu. → flaggée hypotheses.md (self-play divergence A/B).
- **DIVERGENCE outillage (déjà notée seed 80031, re-confirmée)** : `/api/selfplay/:id/status` renvoie 404 (seul `/await` existe) — pas d'endpoint de diagnostic d'état de match. Et `/await` sur un runnerId inconnu renvoie une erreur INSTANTANÉE indistinguable (pour la boucle) d'un "pas encore enregistré" : recommandation des 2 sides = (a) pin/refcount les runners self-play pour qu'un match en vol ne soit pas évincé par des builds ultérieurs ; (b) SETUP doit vérifier `observeBattle` adressable AVANT de spawn les 2 players ET avant de build les runners suivants ; (c) `/await` doit bloquer-ou-erreur-distinctement entre "inconnu" et "pas encore mon tour".

### Key decisions (des 2 sides)

- **A** : a synchronisé via `/api/selfplay/4/await` D'ABORD (correct — le runner live se résout via le hand-off host, pas le state-file disque) ; a diagnostiqué depuis la ground truth via 3 sondes indépendantes (pas un proxy) ; a **REFUSÉ de s'auto-réparer** (pas de build/amorce/nav/dispose) car c'est le rôle de l'orchestrateur SETUP et minter un nouveau runnerId désyncherait la coordination shared-runner avec B.
- **B** : a poll `/await` 7+× pour écarter une race de SETUP (le runner n'est jamais apparu, l'erreur étant instantanée et non un timeout → eviction, pas une race attendable) ; a **REFUSÉ de rebuild runner 24 OU de hijacker les runners 25-31** (qui appartiennent à d'autres matchs) ; a extrait le signal roster de la BC persistée pour un read recon explicitement low-confidence plutôt que de fabriquer des observations de board jamais eues (cf. memory: measure ground truth not proxy).

### Refs action logs

`data/_sp_80020_A.json` / `data/_sp_80020_B.json` (team1=0 actions, team2=0 actions — **aucun tour joué**, `action_log=[]` des deux côtés) — archivés dans `logs/selfplay/sp_80020_2026-06-23-b5.json` (winner=no-result, rejouable via seed 80020) puis supprimés post-teardown. Pas de séquence de jeu à résumer : le match n'a jamais démarré (runner 24 évincé du registry live de la session 4).

---

## seed 80042 — winner=team1 (ts=2026-06-23-b5)

> **Match DÉCISIF** (pas un draw round-cap) : team1 a converti une over-extension adverse en un **3-engine focus-kill en UN tour** (Gibbascrapz summoner + Re'vas OW/ranged engine + Tigurius Psyker engine) → effondrement total du wincon-set de team2 (6v3 → engines tous morts). Combat terminé round ~6, bien avant un round-cap. Compo MIROIR de la série seed 80000 inversée côté unités : ici team1 = AdMech ranged-turret + Imperial artillery (Sy-gex/Thaddeus/Actus/Tjark/Yazaghor) vs team2 = Tau OW-turret + Ork summons + Ultramarines Psyker (Re'vas/Gibbascrapz/Certus/Tigurius/Yazaghor-enemy).

### Rosters

| Équipe | Unités |
|--------|--------|
| **team1 (Player A / oracle, player 3) — VAINQUEUR** | admecDestroyer (Sy-gex) · spaceHound (Tjark) · admecManipulus (Actus, DIED T~4) · astraOrdnance (Thaddeus) · thousTzaangor (Yazaghor, DIED T~5) |
| **team2 (Player B / oracle, player 4) — PERDANT** | tauCrisis (Re'vas) · orksBigMek (Gibbascrapz) · thousTzaangor (Yazaghor-enemy) · ultraEliminatorSgt (Certus) · ultraTigurius (Tigurius) |

### Adjudication

- A outcome_perceived = **W** (6 tours) ; B outcome_perceived = **L** (5 tours) → **winner_consensus = true** (A="W" & B="L" → team1, ET ça MATCHE le winner autoritatif).
- `rl_duel.py status --state-file data/_sp_80042_A.json` : `stage=Finished currentPlayer=3` + *« BATTLE FINIE — winner AUTORITATIF = team1 (battleStatus.winner=3, unitsAlive=13) »*. ⚠ `alive_by_team={}` (decisionView refuse hors-Running) — non utilisé pour l'adjudication (piège H59) ; le champ NATIF `battleStatus.winner=3` est la source.
- **authoritative_winner = team1.**

### Win-conditions (consensus croisé A.mine ≈ B.theirs et A.theirs ≈ B.mine)

**team1 win-condition (VAINQUEUR)** : noyau **ranged-turret Mechanical** — Sy-gex (HeavyGravCannon anti-Mechanical +364/+pierce, one-shot les engines Mechanical adverses) + Thaddeus (BasiliskBarrage board-wide AoE/Pin/Suppress = standoff-breaker qui chip la grappe ennemie REGARDLESS du gap + SpotterReworked +728 ranged aux alliés HeavyWeapon) ancré par un écran durable (Sy-gex 9537, Tjark 8536 Terrifying) ; SOURCE = le barrage Thaddeus (chip board-wide ignore le standoff) + la punch HeavyGravCannon de Sy-gex (one-shot les engines Mechanical) — converti par un **3-engine focus-kill en un tour** sur le dive adverse.
→ Accord A.mine / B.theirs = **CONSENSUS** (B identifie correctement Actus repair-engine comme sustain SOURCE + Sy-gex re-arming OW comme deterrent ; A décrit son propre axe barrage+grav-punch).

**team2 win-condition (PERDANT, jamais réalisée)** : noyau **summon-snowball + amplification** — Re'vas (EarlyWarningOverride = 2 Shield Drones + arme OW +1892 + CyclicIonBlaster +437 vs Mechanical/RangedSpecialist) + Gibbascrapz (GrotTank summon-engine + KustomForceField) + Tigurius (StormOfWrath Psychic NoBlocking AoE + PsychicFortress block-aura) ; SOURCE = les TROIS engines, qui doivent rester vivants et écraner les fragiles — tous tués en UN tour sur l'over-extension.
→ Accord A.theirs / B.mine = **CONSENSUS** (A lit correctement les 3 engines summon/OW/Psyker ; B auto-lit son plan summon-snowball + son flaw : présenter les fragiles isolés à un focus discipliné).

### Séquences clés (résumé des action logs — détail dans `logs/selfplay/sp_80042_2026-06-23-b5.json`)

**Player A (team1, VAINQUEUR) :**
- **T3 — standoff-breaker** : BasiliskBarrage (Thaddeus stationnaire) a chip 3 ennemis ~2025 chacun, Pin (move-1) 3 ennemis ET **disarmé l'Overwatch armé de Certus** (Suppress stoppe l'OW) en un cast → convertit un deep-gap turtle en pression proactive sans exposer personne.
- **Crippling de Re'vas (leur meilleure unité 10542)** : Sy-gex normal HeavyGravCannon-boosté depuis une tuile shallow (4,2) → 10542→3742 (~6800, +364 dmg/+60% pierce vs Mechanical), pas d'over-commit de fragiles pour un kill non-garanti ; fini de la tuile courante au tour suivant (kill-this-turn-or-don't-commit, payé cheap).
- **LE TOUR DÉCISIF — 3-engine focus-kill** : sur le dive de tout le bulk ennemi dans sa face, A a converti ses 3 activations en 3 K! GARANTIS sur les 3 ENGINES (Gibbascrapz summoner + Re'vas OW/ranged + Tigurius Psyker) — PAS le chaff — collapse 6v3 → engines tous morts (textbook « kill-the-wincon-source-on-the-dive », H02).
- Tigurius (4500, fragile, NOT Resilient) K!'d outright depuis une tuile back row 2 (Thaddeus Blast normal) → PsychicFortress aura morte avec lui.
- **Close** : le lone Certus survivant fini en MÊLÉE (Tjark) pour bypasser sa CamoCloak/HeavyWeapon ranged-mitigation ; Tjark pré-positionné le tour d'avant pour fermer avant le round-cap.

**Player B (team2, PERDANT) :**
- **T1 — summon-snowball agressif** (correct vs round-cap) : Re'vas EWO (2 Shield Drones 3989 + arme OW +1892) + Gibbascrapz GrotTank (7977) → board 5→8 units en un tour = numbers lead réel.
- **Sur contact — priorité d'engine CORRECTE** : focus-kill d'Actus (repair-engine Mechanical) la turn de contact via Re'vas CyclicIonBlaster +437-vs-Mechanical (~6452) + GrotTank finish — « kill THIS turn or don't commit » respecté sur le repair-engine (sinon DefendTheDivineWork le re-répare) ; puis Yazaghor-enemy (Psyker dealer le plus soft) focus-killé.
- **FATAL over-extension (le tour de l'effondrement)** : Gibbascrapz committé deep (4,3) pour un chip NON-LÉTAL sur Sy-gex + Tigurius (fragile 4500, son seul armor-ignore AoE) poussé forward (2,5) en danger-3, avec Re'vas déjà blessée (3742) exposée → le focus-compo ranged discipliné de team1 a delete les TROIS en UN tour, flippant 6v3 → 3v3. **Ce seul tour a perdu le combat.**
- **Perte gratuite antérieure** : Yazaghor-enemy mort plus tôt en marchant dans l'arc r3 de l'Overwatch armé de Sy-gex (6,3 depuis (3,2)) — one-shot 6525 en 3 shots OW AVANT de pouvoir agir (hex distance mal jugée).

### Confrontation : consensus vs divergences

#### Mécaniques de CONSENSUS (rapportées des DEUX sides — cross-observable, recoupées gameconfig/i2)

1. **EarlyWarningOverride (Re'vas)** : summon 2 Shield Drones (immédiate-attack, no-move ce tour) + Re'vas s'arme en Overwatch +1892 jusqu'à son prochain tour + re-arm (−1 hit/chaîne) à chaque kill OW ; **once-per-turn ([indispo] après cast)**. A(theirs, « EWO ballonne le front 5→8 en un tour, once-per-turn/cd ») + B(mine, « 2 Shield Drones 3989 + arme Re'vas OW + Gibbascrapz GrotTank simultané, took board 5→8 »). gameconfig verbatim (2 drones tauSmnDroneShield + +1892 OW + re-arm −1 hit). Déjà au wiki §3bis/Re'vas — pas ré-inscrit, juste confirmé n+1.
2. **CyclicIonBlaster +437 vs Mechanical (Re'vas)** : normal attack = 3× Particle hits additionnels (Pierce35) qui deal **+437 Damage si la cible a Markerlight OU le trait Mechanical**. A(mine, « +437/hit anti-Mechanical a aidé à focus-kill mon Actus 9537 ; discount Mechanical HP vs anti-Mechanical ranged ») + B(mine, « ~6452 en une activation sur Actus Mechanical, les +437-vs-Mechanical Particle hits par-dessus les Pulse de base »). gameconfig verbatim (« If the target has a Markerlight or the Mechanical trait these hits deal +437 Damage »). → **INSCRIT wiki Re'vas** (CyclicIonBlaster anti-Mechanical, manquait).
3. **Sy-gex re-arming Overwatch r3 (admecDestroyer)** : arme normale 4× Physical r3, s'arme en OW s'il n'attaque pas en normal, **tout ennemi qui BOUGE dans son arc r3 = volée gratuite souvent létale** ; DISARME pour le reste du tour ennemi après avoir fire, RE-ARME au début de son tour. A(theirs, « OW-armed plusieurs tours, jamais pathé dans son arc r3 ; barrage T3 l'a disarmé une fois ») + B(theirs, « arc r3 depuis (3,2) a atteint (6,3) et one-shot mon Yazaghor 6525 en 3 shots, puis disarmé, mon GrotTank est passé dans l'ancien arc sans réaction »). gameconfig confirme (Overwatch trait natif). Déjà au wiki Sy-gex — confirmé n+1 ; **la NUANCE disarm-après-fire/re-arm-au-tour-suivant cross-observée des deux côtés est inscrite**.
4. **Actus DefendTheDivineWork + GalvanicField (admecManipulus)** : répare self+adjacents 4365 + chaque réparé fait une attaque gratuite immédiate (GalvanicField, cap 4365/hit) = sustain + action economy ; un chip non-létal est effacé next turn (« kill THIS turn or don't commit »). A(mine, « repair-engine 4365 + GalvanicField, DIED T~4 ») + B(theirs, « repair-loop, killed ON the turn of contact AVANT qu'il repair-loop »). gameconfig confirme. Déjà au wiki Actus — confirmé n+1.
5. **HuntersBeyondDeath (Tjark, spaceHound)** : +582 dmg vs Psykers + Psykers ennemis dans 2 hex deal −582 + (sauf Immune) perdent le multi-hit de leur normale ranged. A(mine, « anti-Psyker dédié vs Tigurius/Yazaghor-enemy, mais les Psykers ennemis sont restés back early → aura jamais appliquée positionnellement ») + B(theirs, « −582 à mes Tigurius/Yazaghor dans 2 hex + suppress multi-hit, made committing my Psykers doubly costly »). gameconfig verbatim. Déjà au wiki Tjark — confirmé n+1. ⚠ NUANCE cross-confirmée : l'aura n'a de valeur que si les Psykers ennemis entrent dans les 2 hex — A note qu'elle « n'a jamais porté positionnellement » car les casters sont restés back ; B la lit comme un deterrent QUI A pesé sur son refus d'avancer ses Psykers → l'aura agit aussi comme **menace de zone** (déni de l'approche Psyker), pas seulement comme dégât appliqué.
6. **CamoCloak (Certus, ultraEliminatorSgt)** : −364/hit quand un tir RANGED entrant a son hit-count réduit → affecte les dealers ranged, PAS la mêlée. A(theirs, « finished Certus en MÊLÉE Tjark pour bypasser CamoCloak/HeavyWeapon ranged-mitigation ») + B(theirs roster, « bypass Terrifying with RANGED ; CamoCloak réduit mes hits ranged »). Recoupé i2. → confirme la doctrine « finir un CamoCloak/HeavyWeapon en MÊLÉE » (le ranged-mitigation ne s'applique pas à la mêlée).

#### Divergences (entre observateurs)

1. **Cause de mort d'Actus : ranged-focus anti-Mechanical (consensus) — pas de divergence de fait** : A et B s'accordent sur le mécanisme (Re'vas CyclicIonBlaster +437-vs-Mechanical + GrotTank finish la turn de contact). Pas de divergence — listée pour mémoire.
2. **Valeur de BasiliskBarrage comme standoff-breaker** : A(mine) la traite comme le **tempo-answer central** (chip board-wide + Pin + disarm OW = convertit le double-turtle en pression sans exposition). B ne la liste PAS dans ses threat_cards offensives (« stayed back-row, never reached », threat=high par sa SpotterReworked-buff mais pas observée firing offensivement contre lui). → divergence de SALIENCE, pas de fait : A a activement utilisé le barrage (donc l'a observé porter), B a surtout subi le chip sans l'identifier comme l'axe décisif. Pas une mécanique contradictoire ; la mécanique elle-même (board-wide AoE/Pin/Suppress) est gameconfig-confirmée et déjà au wiki. → noté en hypotheses.md comme observation single-side-saillante.
3. **Frictions outil cross-rapportées (non-mécaniques)** : (a) **pas d'overlay des arcs d'Overwatch armé** — B a perdu Yazaghor-enemy en marchant dans l'arc r3 de Sy-gex sans warning pré-move (le danger-zone number ne flag pas le one-shot OW) ; A confirme indirectement (« never pathed into its r3 arc » = a dû le calculer à la main). → friction outil connue (GAP overlay OW, déjà notée au wiki Re'vas l.710) — re-confirmée n+1. (b) **label de tour stale dans le header de la vue** (« tour 3 · joueur 3 » même tard) — A s'est fié à `status` alive_by_team/À-ACTIVER au lieu du header. (c) **moves silencieusement rejetés « HORS du movable set »** côté B (danger/footprint blocking dur à prédire à l'œil) — friction H55 connue, re-confirmée.

### Erreurs identifiées (leçons, des deux sides)

- **B (#1, ROOT CAUSE)** : over-extension des fragiles/key units une fois le lead acquis — Gibbascrapz (summon-engine #2) committé deep pour un chip + Tigurius (seul armor-ignore AoE, 4500) poussé en danger-3 SANS écran, Re'vas blessée (3742) exposée → focus-compo ranged a delete Re'vas+Gibbascrapz+Tigurius en UN tour (6v3 → 3v3). Failure-mode dominant : présenter des fragiles isolés à un focus discipliné. Garder les summons en écran, tenir les fragiles groupés/back, avancer en masse cohésive.
- **B** : Yazaghor-enemy marché dans l'arc OW armé r3 de Sy-gex (one-shot 6525 avant de fire) — vérifier l'arc OW (move d'un corps durable d'abord, OU rester hors r3 jusqu'à expiration de l'OW). Hex-distance mal jugée.
- **B** : StormOfWrath (Tigurius, seul outil armor-ignore vs le cluster tanky Sy-gex/Tjark 9537/8536) JAMAIS fire — laissé back trop longtemps puis over-extended à la mort. Vs un cluster tanky, set up une position forward SUPPORTÉE pour le caster armor-ignore TÔT, derrière l'écran durable, pas en solo.
- **B** : mis-pacé la close (8v5 fort dépensé inefficacement — un deep chip sur Sy-gex non-létal qui a coûté Gibbascrapz). « kill THIS turn or don't commit » appliqué à Sy-gex : ne pas pouvoir le one-turn → ne pas strander Gibbascrapz à côté.
- **A (vainqueur, mais des slips réels)** : sur-étendu son écran Mechanical à row 2-3 (T4-5) SANS compter le +437/hit anti-Mechanical de Re'vas + RangedSpecialist → a perdu Actus (repair-engine 9537) puis Yazaghor (fragile) avant le dive-punish (3v6 transitoire). **NUANCE anti-Mechanical** : discount le HP des Mechanicals vs une compo Tau anti-Mechanical ranged ; garder le repair-engine + les fragiles une rangée plus back.
- **A** : a avancé Sy-gex à (4,2) pour attaquer, cédant sa valeur d'Overwatch-turret armé (un Sy-gex stationnaire armé aurait puni le dive en réactions GRATIS) — ça a marché (cripple Re'vas + survie) mais a payé des HP inutiles. **Doctrine held-OW-turret** (cf. Re'vas/Certus/Azrael) : tenir l'OW armé vaut souvent mieux que pousser pour une attaque.
- **A** : a laissé Thaddeus bouger à (2,2) pour landerle K! Tigurius (OK ici = engine-kill garanti, mais a nudgé l'engine-barrage forward) — sur un tour non-décisif, garder le barrage-carrier maximalement back (le move-gate void le barrage s'il bouge).
- **A** : a perdu 2/5 units (40%) pour convertir — le W est venu de l'over-extension ADVERSE qui a gifté le 3-engine focus-kill, PAS d'une ligne défensive propre. Vs un adversaire qui ne dive PAS, sitter le cluster Mechanical à row 2-3 vs une compo Tau anti-Mechanical ranged aurait saigné A (cf. la série reach/attrition).

### Refs action logs

Action logs complets de CE run : `data/_sp_80042_A.json` + `data/_sp_80042_B.json` → archivés dans `logs/selfplay/sp_80042_2026-06-23-b5.json` (winner=team1, rejouable via seed 80042) puis supprimés post-teardown ; séquences clés (standoff-breaker T3 → 3-engine focus-kill sur le dive → close mêlée) résumées ci-dessus.

## seed 80053 — winner=team1 (ts=2026-06-23-b5)

**Adjudication AUTORITATIVE** : `rl_duel.py status --state-file data/_sp_80053_A.json` →
`*** BATTLE FINIE — winner AUTORITATIF = team1 (battleStatus.winner=3, unitsAlive=10) ***`.
Élimination complète de team2 (`unitsAlive=10` = les 10 emplacements team1 vivants ; team2 wipé).
**Consensus de résultat** : A (team1) = « W » + B (team2) = « L » → MATCHE le winner autoritatif →
`winner_consensus = true`. (`alive_by_team={}` post-Finished est attendu/non-discriminant — decisionView
refuse hors-Running, cf. H59 ; ne PAS l'interpréter.)

**Rosters**
- **team1 (A, VAINQUEUR)** : bloodMephiston (Mephiston) — Psyker carry Pierce100 NoBlocking r2 + FuryOfTheAncients heal-block ;
  bloodDante (Dante) — deep-strike melee carry, Pierce80, LordOfTheHost amplifier, FinalJustice, Flying, Terrifying ;
  necroWarden (Makhotep) — Gauss r3, RelentlessMarch move/repair engine ;
  adeptMorvenn (Morvenn Vahl) — Blast SanctorumMissile r3 + Bolter r3, BigTarget, Explodes, Mechanical, ActOfFaith ;
  spaceStormcaller (Njal) — Psyker Pierce100 NoBlocking r2, TerminatorArmour, Stormcaller Ice AoE r3, Unstoppable.
- **team2 (B, PERDANT)** : worldKharn (Kharn) — TheBetrayer snowball + KillMaimBurn burst, FinalJustice, RapidAssault ;
  spaceBlackmane (Ragnar) — WarHowl melee buff-engine, FinalJustice, BeastSlayer, RapidAssault ;
  ultraCalgar (Calgar) — MkXGravis double-armor tank, RitesOfBattle aura, GauntletsOfUltramar AoE r2, FinalJustice ;
  tauDarkstrider (Darkstrider) — markerlight engine (near-inert : seul Actus est ranged côté team2), Pulse r2, Infiltrate ;
  admecManipulus (Actus) — repair engine INERTE (aucun allié Mechanical bénéficiaire côté team2), Flying, Energy r2.

**win_condition (consensus A/B — concordant)**
- **team1 (gagnante)** : DOUBLE noyau Psychic armor-ignore (Mephiston + Njal, tous deux Pierce100 NoBlocking) qui
  bypasse intégralement MkXGravis/TerminatorArmour → neutralise l'anvil Calgar ; backé par Dante (deep-strike carry +
  LordOfTheHost) et Morvenn SanctorumMissile Blast AoE r3 pour le softening de cluster ; Makhotep RelentlessMarch =
  move-engine. **A le lit (mine) IDENTIQUE à l'auto-lecture B (theirs)** → consensus haute confiance.
- **team2 (perdante)** : engine mêlée snowball/amplifier — Ragnar WarHowl (+1164 dmg/+36% crit/Unstoppable à la ligne
  mêlée sans normale ranged) feeding un alpha Kharn KillMaimBurn ~10k. **N'A JAMAIS fire** : Ragnar+Kharn tués T5/avant
  tout cast de WarHowl. **A le lit (theirs) IDENTIQUE à l'auto-lecture B (mine)** → consensus.

**key_decisions — team1 (A)**
- Tenue de position T3 + avance cohésive vers row 2-3 sans contact → l'ennemi all-melee CONTRAINT de diver dans sa portée.
- T5 « engine break » : Blast/Ice/Psychic splash a softené le cluster ennemi serré, puis Makhotep K!'d Kharn (snowball)
  et Dante K!'d Ragnar (WarHowl) AVANT que l'un ou l'autre engine s'arme. Darkstrider (markerlight sans feeders ranged)
  et Actus (repair sans allié Mechanical) démotés en corps softs dès le recon.
- Njal (seul Psyker atteignable) assigné au focus Calgar → 4786 en un hit en bypassant MkXGravis.
- Endgame séquencé en kills garantis depuis tuiles peu profondes ; Calgar final (337 PV) overkillé au Gauss Makhotep pour
  nier sa FinalJustice → clôture ~round 7, avant le cap round-8.

**key_decisions — team2 (B)**
- T1 (son 1er vrai tour) : avance du wedge mêlée (Ragnar+Kharn forward row 6) pour combler le gap round-cap et set up un
  alpha buffé. **ROOT-CAUSE** : l'adversaire avait DÉJÀ avancé son cluster Psychic armor-ignore à row 2-3 → row 6 a mis
  l'engine (Ragnar) + le carry (Kharn) dans sa portée Psychic+dive → focus-killés sur le tour ennemi, wincon détruit.
- Après la perte Ragnar+Kharn (3v5) : kill propre de Mephiston à 644 PV avec Darkstrider depuis sa tuile (Infiltrate =
  pas d'overwatch, zéro exposition) — meilleure valeur dispo, retire leur top armor-ignore carry.
- Refus correct de feed Calgar/Actus dans le cluster sain 4-unités (down 3v4) — bon sur la valeur, mais position déjà
  structurellement perdue. Chip final concentré sur Morvenn (9539→2205) mais les rolls K? bas → survit.

**Résultat de la CONFRONTATION : consensus vs divergences** — détail en sous-sections ci-dessous.

### Confrontation : consensus vs divergences

#### Mécaniques de CONSENSUS (rapportées des DEUX sides — cross-observable, recoupées gameconfig/i2)

1. **WarHowl (Ragnar)** : self-cast (Ragnar n'a pas bougé, ne finit PAS son tour) → Ragnar + tous les Characters
   alliés SANS normale ranged gagnent **Unstoppable + +1164 dmg mêlée + +36% Crit Chance** jusqu'à fin de tour →
   doit être casté LE MÊME TOUR que l'attaque buffée. A(theirs, « jamais observé firing — Ragnar tué T5 avant cast ;
   tuer la source pre-cast = engine jamais armé ») + B(mine, « never fired: committed forward AVANT de pouvoir attaquer ;
   requires Ragnar has NOT moved ; does NOT end his turn »). gameconfig --ability WarHowl **VERBATIM** (« +36% Crit Chance
   and deal +1164 Damage … Unstoppable … If Ragnar has not moved … does not end Ragnar's turn »). Déjà au wiki §spaceBlackmane —
   confirmé n+1 (le « kill before WarHowl » et la condition no-move y sont déjà). **n+1 NOTABLE inscrit** : la FinalJustice de
   Ragnar (tué non-overkill) a chunké Mephiston PLEIN-PV **9537→644** (puis fini) = une seule riposte FJ peut quasi-tuer un
   carry full-HP — overkill ou dégager les valuables de l'arc FJ avant le coup létal.
2. **MkXGravis (Calgar) bypassé par Psychic Pierce100 NoBlocking** : double-armure (« Any incoming Damage has to go through
   Armour a second time. Does not apply to Crits ») → ~halve le dmg mêlée/Power non-crit, MAIS une arme Pierce100 NoBlocking
   ignore l'armure entièrement (la 2ᵉ passe d'armure n'existe pas s'il n'y a pas d'armure traversée). A(theirs, « Psychic Njal
   Pierce100 NoBlocking bypasse MkXGravis = 4786 en un hit ; le designated tank-killer ») + B(mine, « Calgar double-armor
   worthless vs cet adversaire ; chipé 9537→4751→337 malgré MkXGravis car les 2 carries sont Pierce100 NoBlocking »).
   gameconfig --trait MkXGravis VERBATIM + weapon profile Njal `Psychic{PiercingRatio:100, NoBlocking}`. Déjà au wiki §ultraCalgar +
   §spaceStormcaller — confirmé n+1. ⚠ PRÉCISION (recoupée gameconfig) : le bypass vient du **profil d'arme Pierce100/NoBlocking**
   (ignore toute armure), PAS d'une exemption MkXGravis spécifique au Psychic — la seule exemption native de MkXGravis est le **Crit**.
3. **SanctorumMissile (Morvenn, Blast HitsMultipleMembers r3)** : 2× Blast sur la cible + 1× Blast à TOUS les hexes adjacents
   à la cible (sauf l'hex de Morvenn) → multi-engine softening sur un cluster serré. A(mine, « un cast a touché Kharn 2546 +
   splashé Ragnar -2318 + Darkstrider -2434 simultanément ») + B(theirs, « SanctorumMissile Blast AoE r3 punit le clustering ;
   chipé 9539→2205 »). gameconfig --ability SanctorumMissile VERBATIM (« 2x … and 1x … to all hexes adjacent to the target »).
   Déjà au wiki §adeptMorvenn — confirmé n+1.
4. **FuryOfTheAncients heal-block (Mephiston)** : après mouvement, 2× Psychic Pierce100 NoBlocking sur un ennemi adjacent + le
   2ᵉ adjacent, appliquant un **blocage heal/repair 2 rounds**. B(theirs, « heal-block mon Darkstrider 2 rounds — confirme que
   c'est un AoE sur les ennemis adjacents APRÈS que Mephiston a bougé, pas un passif »). A ne le mentionne pas explicitement
   (n'a pas eu l'occasion d'être touché) → rapporté par 1 seul side mais **gameconfig-confirmé + déjà richement au wiki §bloodMephiston** →
   confirmé n+1 (pas une divergence : absence de mention ≠ contradiction).

#### Divergences (entre observateurs)

1. **Calgar GauntletsOfUltramar (ranged Bolter) [0-0] vs Dante — cause attribuée par B = "Terrifying", or Terrifying est MÊLÉE-only** :
   B(mine, confidence:med) rapporte que la mêlée non-Psychic ET le **Bolter ranged** de Calgar ont fait 0 à Dante tout le combat,
   et hésite (« Terrifying reduces MELEE only per i2, but the ranged Bolter also read [0-0] — likely combined with Dante's high
   armor/defense + Terrifying »). gameconfig --trait Terrifying = VERBATIM **« Takes X% Damage from Melee attacks »** → Terrifying
   ne réduit QUE la mêlée. Donc le [0-0] sur le **Bolter ranged** de Calgar n'est PAS imputable à Terrifying (qui ne s'applique
   pas au ranged) mais à l'armure/défense de Dante face au Bolter Pierce20 (faible pen). → divergence de CAUSE (B mal-attribue),
   PAS un fait nouveau : la règle Terrifying=mêlée-only est déjà au wiki §1/§bloodMephiston/§bloodDante. Flaggée hypotheses.md.

### Erreurs identifiées (leçons, des deux sides)

- **B (#1, ROOT CAUSE)** : over-extension de l'engine (Ragnar) + du carry (Kharn) à row 6 sur son 1er vrai tour, dans la portée
  Psychic armor-ignore déjà-avancée de l'adversaire → les DEUX focus-killés en un tour ennemi = wincon détruit, jamais de WarHowl,
  jamais de burst Kharn. Failure-mode dominant. Aurait dû avancer le tank durable (Calgar) FORWARD avec Ragnar/Kharn écranés
  DERRIÈRE, ou tenir un tour de plus et baiter le cluster Psychic-melee-less DANS sa propre portée KillMaimBurn.
- **B** : mis-identifié son propre ownership au 1er tour (a joué les units 95-103 de team1 au lieu de ses 85-93 team2) en se
  fiant au label « MOI »/currentPlayer de la vue sans grounding `status` (flag CTRL). Friction outil cross-rapportée (header de tour
  stale / off-by-one) → TOUJOURS `status` pour confirmer CTRL=mon équipe avant d'agir.
- **B (structurel)** : roster all-melee SANS aucun outil Psychic/armor-ignore vs un adversaire double-Psychic + Terrifying Dante
  (Calgar a fait littéralement 0 à Dante tout le combat) → désavantage structurel à reconnaître au recon = jouer turtle-and-counter,
  pas un close agressif.
- **A (VAINQUEUR, slips réels)** : a tué Ragnar (engine) avec une SEULE source non-overkill alors que Mephiston était dans l'arc
  FinalJustice de Ragnar → FJ a chunké Mephiston 9537→644 (puis fini) = sa SEULE perte d'unité, entièrement évitable. Aurait dû
  OVERKILL Ragnar OU dégager Mephiston de l'arc FJ avant le coup létal.
- **A** : over-commit T5 (4/5 units forward dans le cluster 5-ennemis) — a marché parce que les 2 engines sont morts, mais a exposé
  Mephiston au FJ + au focus adverse. Un kill plus shallow ou router le carry Psyker un rang en arrière l'aurait préservé.
- **A** : no-op gaspillé en cliquant la normale de Morvenn comme id 69 (générique) au lieu de son id réel **1182**
  (RighteousRepugnance_NormalAttack) — l'action n'a PAS été consommée (récupéré) mais a coûté un round-trip. Lire l'id de
  normale par-unité depuis `abilities` avant de tirer pour les units à id spécifique (re-confirme la friction id-69 connue).

### Refs action logs

Action logs complets de CE run : `data/_sp_80053_A.json` + `data/_sp_80053_B.json` → archivés dans
`logs/selfplay/sp_80053_2026-06-23-b5.json` (winner=team1, rejouable via seed 80053) puis supprimés post-teardown ;
séquences clés (tenue de position T3 → T5 engine-break double-K! Kharn+Ragnar pre-arm + Njal anti-Calgar Psychic →
overkill final Calgar pour nier FJ) résumées ci-dessus.

---

## seed 80064 — winner=team2 (ts=2026-06-23-b5)

### Rosters

| Équipe | Unités |
|--------|--------|
| **team1 (Player A / oracle — PERDANT)** | darkaTerminator (Baraqiel) · spaceStormcaller (Njal) · admecMarshall (Tan Gi'da) · eldarAutarch (Aethana) · tauDarkstrider (Darkstrider) |
| **team2 (Player B / oracle — VAINQUEUR)** | darkaAzrael (Azrael) · tyranNeurothrope (Neurothrope) · genesPatriarch (The Patermine) · templChampion (Jaeger) · adeptHospitaller (Isabella) |

### Adjudication

- A outcome_perceived = **L** ; B outcome_perceived = **W** → **winner_consensus = true**
- `rl_duel.py status --state-file data/_sp_80064_A.json` : `*** BATTLE FINIE — winner AUTORITATIF = team2 (battleStatus.winner=4, unitsAlive=11) ***`
- **authoritative_winner = team2** (champ NATIF battleStatus.winner=4 = team2, lisible post-Finished — H59). ⚠ `alive_by_team={}` VIDE post-Finished (decisionView refuse hors-Running) = NORMAL, ne pas l'interpréter comme draw (H64). L'élimination est confirmée par `unitsAlive=11` (full team2 alive + summons ; team1 wipe).

### Win-conditions (consensus croisé A.mine ≈ B.theirs et A.theirs ≈ B.mine)

**team1 win-condition (A.mine ≈ B.theirs)** : stack d'amplification ranged feeding un carry Psychic — Aethana `PathOfCommand` (+291/+218 Aeldari aura à TOUS) + Darkstrider `StructuralAnalyser` (Markerlight +728 ranged) + Tan Gi'da summon-engine → amplifient Njal (Psychic Pierce100 NoBlocking universal-bypass) + Baraqiel PlasmaCannon line-AoE. SOURCE = les 2 buff-engines (aura Aethana + markerlight Darkstrider).
→ Accord A.mine / B.theirs : **CONSENSUS** (B a correctement identifié les 2 buff-engines comme la vraie source à couper ; « cut them and Njal/Baraqiel are just two un-amplified bodies »).

**team2 win-condition (B.mine ≈ A.theirs)** : core armor-ignore (Patermine MightFromBelow 5× Psychic Pierce100 NoBlocking + Neurothrope SpiritLeech Psychic self-heal + Azrael DarkTalonStrike DirectDamage Pierce100) — chaque kill bypasse armure/TerminatorArmour/block. PAS de buff-engine unique : carry Patermine + engine snowball Neurothrope, screenés par Jaeger (anvil) + Isabella (sustain/revive). SOURCE = les TYPES de dégâts eux-mêmes (Psychic + Direct) qui ignorent toute armure.
→ Accord B.mine / A.theirs : **CONSENSUS** (A a correctement identifié Isabella+Neurothrope comme le sustain-core et Patermine comme le carry à tuer au RANGED — Terrifying).

### Séquences clés (résumé des action logs ; détail rejouable dans l'archive)

**Player A (team1, PERDANT) :**
- T1-T2 : avancé à row 2 (tuiles danger-0) puis HOLD pour recevoir la charge (doctrine « bait-the-dive »). ROOT-CAUSE MISTAKE : vs un adversaire plus rapide/melee-heavy (Patermine move4+Infiltrate) qui avançait, tenir a laissé l'ENNEMI choisir l'engagement → focus-kill de Tan Gi'da (T2) + Darkstrider (T3) GRATIS avant que le moteur markerlight+summon ne fire.
- T3 : spread-fire sur les 5 ennemis (Njal Ice-AoE 3 cibles + Baraqiel→Jaeger + Darkstrider→Patermine) au lieu de concentrer un kill — vs un double-sustain (Isabella revive/regen + Neurothrope self-heal) le chip étalé est largement undone.
- T4 : focus-kill PROPRE du Patermine (PlasmaCannon-line + Njal + Aethana finish) = bonne priorité (retire le snowball-carry), MAIS Aethana sur-étendue à (4,3) = focus-killée le tour suivant ; jamais atteint la backline engines (Isabella/Neurothrope row 5-6).
- T5 : trade Baraqiel+Njal forward pour tuer Jaeger — meleer Jaeger a mangé un counter MartialSuperiority **4307** sur Baraqiel + sa FinalJustice a fini Baraqiel blessé (aurait dû finir Jaeger purement au RANGE).

**Player B (team2, VAINQUEUR) :**
- Engagé proactivement dans le standoff (round-cap EnvEndBombardment actif) : avancé les bricks durables (Patermine Terrifying 10038 + Jaeger 11046 Parry), fragiles (Neurothrope + Isabella) un rang derrière → forcer la décision avant le cap.
- Tué les AMPLIFIER engines dans l'ordre de leverage (Tan Gi'da summoner → Darkstrider markerlight → Aethana aura) avec NoBlocking/Direct ignorant leurs buffs d'armure, au lieu de trader dans le tank TerminatorArmour (Baraqiel) → l'offense ennemie n'a JAMAIS scalé.
- Bon outil armor-bypass sur le bon mur : Azrael DarkTalonStrike (Direct 5015 full sur Njal, Attack_Is_First_Hit=1, ZÉRO réduction) + Neurothrope SpiritLeech (Psychic 2227) **même tour** = Njal 8032→790 malgré TerminatorArmour.
- Accepté un trade Jaeger-for-Baraqiel : anvil bas-PV isolé forward, sa FinalJustice + MartialSuperiority counter ont rendu l'échange neutre-à-favorable.
- ⚠ MISTAKE dominante de B (qui a quand même GAGNÉ) : sur-extension du carry Patermine à (4,2) deep dans le cluster pour finir Darkstrider → focus-killé le tour ennemi suivant (perte de sa meilleure pièce dans un fight déjà gagné). Aurait dû finir Darkstrider avec le Direct K! garanti d'Azrael et retraiter le Patermine.

### CONFRONTATION (vérif indépendante par 2 observateurs séparés)

**Consensus mécaniques (rapportées + concordantes des DEUX sides, gameconfig-CONFIRMÉES) :**
1. **MartialSuperiority (Jaeger)** — counter mêlée AVANT que l'attaque ennemie résolve : A(theirs, high, « 2135+2172=4307 Power sur Baraqiel meleeing Jaeger en une activation ») + B(threat card Jaeger anvil + synergie « MartialSuperiority counters the melee attacker before it hits »). gameconfig --ability MartialSuperiority VERBATIM (« 2x 1455-1601 Power Damage to the attacker before the enemy attack executes »). Déjà au wiki §3bis Jaeger — confirmé n+1.
2. **FinalJustice (Jaeger/Azrael)** — death-attack à la perte du dernier PV, fire même tué au RANGED, sauf Overkill : A(theirs, high, « FJ de Jaeger tué par Njal ranged a aidé à finir Baraqiel adjacent ») + B(mine, « Jaeger FinalJustice ripostes on death », trade salvagé). gameconfig --trait FinalJustice VERBATIM (« immediately performs a normal attack … unless Overkilled »). Déjà au wiki §1 + §3bis — confirmé n+1.
3. **TerminatorArmour Psychic/Direct EXCLUDED (Baraqiel/Njal)** — la 1ʳᵉ attaque/tour est réduite SAUF Psychic ET DirectDamage : B(theirs, high, « DarkTalonStrike Direct 5015 full sur Njal Attack_Is_First_Hit=1 sans réduction ; mon Patermine/Neurothrope Psychic bypassent aussi ») + A(mine, win_condition « Njal Psychic NoBlocking universal-bypass ignores armor », Baraqiel Pierce65 ranged bypasse Terrifying). gameconfig --trait TerminatorArmour VERBATIM (`terminatorArmourExcludedDmgProfiles:"Psychic,DirectDamage"`). Déjà au wiki §1 — confirmé n+1.
4. **SpiritLeech (Neurothrope)** — Psychic r3 self-heal ~60%, engine self-sustaining : A(theirs, high, « Njal 8032→790 + Neurothrope 8014→8533 self-heal en un tour ») + B(mine, high, « self-heals ~60% of damage dealt, Neurothrope 8014→8533 »). gameconfig --ability SpiritLeech VERBATIM (« heals itself … for Health equal to 60% of the total damage dealt »). Déjà au wiki §3bis Neurothrope — confirmé n+1.
5. **PathOfCommand (Aethana)** — aura +291 dmg / +20% crit / +218 Aeldari aux alliés ≤2 hex, amplificateur UNIVERSEL (tous types) : A(mine, synergie « +291 dmg/+20% crit/+218 Aeldari ») + B(theirs, high, « universal amplifier — higher leverage than markerlight ; killing it defangs the whole enemy offense »). gameconfig --ability PathOfCommand VERBATIM. Déjà au wiki §3bis Aethana — confirmé n+1.
6. **Stormcaller Ice→Stun-on-Flying (Njal)** — r3 AoE Ice, les Flying touchés sont Stunned 1 round : B(theirs, high, « a STUNNÉ mon Neurothrope Flying → 4 Stunned, denied SpiritLeech ce tour ») + A(mine, high, « no-move r3 a touché 3 ennemis à la fois Psychic NoBlocking »). gameconfig --ability Stormcaller VERBATIM (« Flying enemies damaged this way get Stunned for 1 round »). Déjà au wiki §3bis Njal — confirmé n+1.
7. **MightFromBelow DECOY-gated (Patermine)** — 5× Psychic Pierce100 NoBlocking ; le summon Genestealer fire mais produit 0 unité si AUCUN decoy adjacent (gaté sur les decoys/kills, PAS sur le cast) : A(theirs, threat « Step on its decoys to deny Genestealer summon ») + B(mine, high, « 5536 sur Tan Gi'da ignorant +582 ProtectorImperative ; Ability_Summon fired but produced 0 units — decoy-gated, not cast-gated »). gameconfig --ability MightFromBelow VERBATIM (« summons a Purestrain Genestealer on each decoy adjacent to the Patermine »). Déjà au wiki §3bis Patermine + §5bis — confirmé n+1.
8. **CosmicHorror decoy (Patermine)** — pose un genesSmnDecoy (HP0, Steppable) sur l'hex du mort quand le Patermine LUI-MÊME tue ; ancre de summon, destructible en marchant dessus : A(theirs, med, « sur kill Darkstrider, decoy sur l'hex de mort ; Aethana SwoopingHawk a stepped through → détruit → summon nié ») + B(mine, med, « genesSmnDecoy HP0 spawn sur l'hex de mort de Darkstrider »). Déjà au wiki §3bis Patermine + §5bis — confirmé n+1.
9. **Overwatch armé (Azrael)** — fire sur le MOUVEMENT (move-in) dans l'arc au tour adverse, PAS seulement la mêlée ; gate = NOT-ATTACKED : A(theirs, high, « 1166 free sur Baraqiel move-in, Effect_Type=1009, séparé du counter mêlée — ranged OW punit tout move-in ») + B(threat card Azrael control « Overwatch armé all game »). Déjà au wiki §1 Overwatch (gate=NOT-ATTACKED) — confirmé n+1 (variante RANGED-OW-punit-le-mouvement déjà documentée).

**Divergences (entre observateurs) :** AUCUNE divergence de mécanique de jeu. A et B sont remarquablement concordants : les 2 win-conditions sont cross-lues correctement (A lit la source-engine de B = les 2 buff-engines à couper ; B lit la source de A = les types Psychic/Direct), toutes les mécaniques about=theirs concordent. Seule nuance non-contradictoire : les DEUX sides identifient leur PROPRE sur-extension de carry forward comme la slip dominante (A : Aethana à (4,3) ; B : Patermine à (4,2)) — un MÊME failure-mode (carry/fragile laissé dans la kill-zone après un kill agressif) vécu symétriquement, pas un désaccord. Rien à flagger en hypotheses.md pour ce match.

### Erreurs identifiées (leçons, des deux sides)

- **A (PERDANT, ROOT CAUSE)** : HOLD à row 2 T1-T2 vs un adversaire plus rapide/melee-heavy (Patermine move4+Infiltrate) qui avançait → le danger-overlay lisait danger-0 mais SOUS-warnait la reach d'envelopment move4+Infiltrate → l'ennemi a tué les 2 engine-enablers (Tan Gi'da summoner, Darkstrider markerlight-feeder) GRATIS avant que le moteur fire. La doctrine « hold-to-bait-the-dive » suppose un edge de reach/cohésion qu'A n'avait PAS ici (mirror inverse de seed 70056/70000 où le hold a marché GRÂCE à l'OW armé + reach).
- **A** : spread T3 sur 5 ennemis vs un double-sustain core (Isabella revive/regen + Neurothrope self-heal) = chip undone ; aurait dû concentrer Njal+Baraqiel+Darkstrider sur UN engine pour un kill garanti.
- **A** : jamais menacé les SUSTAIN ENGINES backline (Isabella/Neurothrope row 5-6) — seuls Aethana (Flying) et Njal avaient le reach, jamais routés dessus tôt → sustain adverse online tout le combat (mirror reach-fail de la série 70000/19355).
- **A** : deep-strikes (Baraqiel/Aethana) gaspillés en avance forward T1 (téléport « anywhere » turn-1-only utilisé pour avancer 1 rang) — option perdue pour rien ; aurait pu pré-positionner un reach-asset sur les engines.
- **B (VAINQUEUR, slip réelle)** : sur-extension du carry Patermine à (4,2) deep pour finir Darkstrider → focus-killé le tour suivant (perte de sa meilleure pièce dans un fight déjà gagné). Aurait dû finir Darkstrider avec le Direct K! garanti d'Azrael / striker depuis un hex shallow + retraite. Failure-mode dominant = carry/fragile laissé dans la kill-zone (IDENTIQUE au slip d'A sur Aethana).
- **B** : Jaeger (3979) laissé isolé forward-right à (5,3) sans support — trade pour Baraqiel mais une formation plus serrée aurait pu tuer Baraqiel au range et garder Jaeger.

### Frictions outil (cross-rapportées — déjà documentées)

- **decisionView damage predictions pour les ABILITIES systématiquement [0-0]/non fiables** (A) : PlasmaCannon, Stormcaller, SwoopingHawk montraient [0-0] alors qu'ils ont fait 3000-5000 — juger par la CASCADE, pas la prédiction (friction connue, déjà documentée).
- **play --no-ai re-runs le --spec ENTIER depuis le dernier état commité** (A+B) : re-issuer un spec multi-action dont une partie est déjà appliquée → « already acted »/« TOUR ABANDONNÉ ». Splitter par-unit est plus sûr ; re-view + re-issuer SEULEMENT les units restantes (friction connue H-play-spec).
- **map ASCII glyph stale/overlapping vs targeting engine** (B) : un glyph ennemi ('b' à (3,6)) stale tandis que abilities/moves/status plaçaient Njal autoritativement à (2,2) ; le glyph collait aussi le 'b' drybush terrain. Faire confiance à abilities/moves/status > au glyph map (friction connue).

### Refs action logs

Action logs complets de CE run : `data/_sp_80064_A.json` + `data/_sp_80064_B.json` → archivés dans
`logs/selfplay/sp_80064_2026-06-23-b5.json` (team1=33 actions, team2=21 actions, winner=team2, rejouable via seed 80064)
puis supprimés post-teardown ; séquences clés (A hold-row-2 T1-T2 → engine-enablers tués gratis T2-T3 → focus Patermine T4 mais
Aethana over-extend → trade Baraqiel/Njal forward T5 mauvais melee-into-Jaeger ; B engage proactif → kill amplifier-engines en
ordre Tan Gi'da→Darkstrider→Aethana via Psychic/Direct bypass → Njal one-turn 8032→790 → Patermine over-extend mais déjà gagnant)
résumées ci-dessus.

---

## seed 80072 — winner=team2 (ts=2026-06-23-b6)

**Adjudication** : winner AUTORITATIF = **team2** (battleStatus.winner=4, unitsAlive=10 post-Finished, H59). Consensus des observateurs : A (team1) outcome="L", B (team2) outcome="W" → **winner_consensus = true** (A/B concordent ET matche l'autoritatif). Match terminé par **élimination** (5v0 effectif côté team2 ; team1 réduit 5v5→3v5→1v5), pas round-cap.

**Rosters :**
- **team1 (A, PERDANT)** : deathRotbone (Nauseous, Resilient/Healer tank + ContagionsOfNurgle −armure + TaintedNarthecium Chaos-only revive) · necroSpyder (Aleph-Null, Explodes/LivingMetal/Mechanic — repair INERTE car seul Mechanical) · darkaAzrael (DarkTalonStrike Direct Pierce100 + Bolter-line + Overwatch + FinalJustice) · thousAhriman (Doombolt Psychic NoBlocking AoE + WeaverOfFate) · tyranNeurothrope (SpiritLeech Psychic + self-heal + Neuroparasite + Synapse).
- **team2 (B, VAINQUEUR)** : ultraApothecary (Incisus, CombatRestoratives heal 4365/5456 + Narthecium 100% revive adjacent) · tauAunShi (Aun'Shi, SereneUnifier buff-cycle + InspiredToGreatness) · tauDarkstrider (Infiltrate + StructuralAnalyser markerlight +728 ranged) · ultraEliminatorSgt (Certus, MortisRound Heavy r3 + Overwatch + HeavyWeapon + Infiltrate + CamoCloak) · thousSorcerer (Thaumachus, Psychic NoBlocking + AttemptedPossession + ArcaneShield 4001).

**Win-conditions (consensus, cross-lues correctement) :**
- **mine (team2, VAINQUEUR)** : umbrella de sustain Apothecary (CombatRestoratives mass-heal + Narthecium 100% revive du cluster adjacent) **un-out-damageable par un roster chip/burst-once**, amplifiée par le buff-cycle Aun'Shi SereneUnifier (−50%dmg / +move / +582dmg) et les markerlight/Heavy ranged (Darkstrider→Certus). SOURCE protégée = l'Apothecary back-screené (jamais atteignable par le roster r2/r3 adverse).
- **theirs (team1, PERDANT)** : alpha Psychic/Direct coordonné — Ahriman Doombolt + Neurothrope SpiritLeech (armor-ignore, arme WeaverOfFate à 3+ cibles Psychic + snowball Neuroparasite) + Azrael DarkTalonStrike (Direct single + Bolter-line) derrière un screen Nauseous Resilient/heal + une tourelle OW Azrael. SOURCE = les 2 Psykers + le burst Azrael.
- **Cross-lecture validée** : A.win_condition.theirs (lecture de B par A) ≈ B.win_condition.mine (auto-lecture B) — accord total sur l'umbrella Apothecary + buff-cycle Aun'Shi. A.mine ≈ B.theirs — accord sur le snowball Psychic + sur l'**over-commit forward** comme la slip qui a exposé les 2 engines.

**Key decisions (les 2 sides) :**
- **A (PERDANT)** : recon correct des 2 wincons + demote correct de son propre necroSpyder (repair INERTE car seul Mechanical) ; TIMED son alpha sur la phase non-(−50%) d'Aun'Shi (8536→1770 + chip Thaumachus/Darkstrider) ; choisit de NE PAS finir Aun'Shi à 1770 (raisonnement « le revive le ramènerait à 4365>1770 » sound en isolation mais MOOT — l'Apothecary l'a heal à 7753 de toute façon) ; **committé forward dans le danger-5 (anti-turtle round-cap)** → Nauseous puis Neurothrope focus-killés → snowball 5v5→3v5→1v5.
- **B (VAINQUEUR)** : **HOLD/cohésion** au lieu d'un dive solo (Certus tourelle OW stationnaire + Thaumachus ArcaneShield) → a bait l'over-commit adverse en territoire atteignable ; **heal-then-strike** sur le tour décisif (CombatRestoratives d'ABORD : Aun'Shi 1770→7753 + clear Pinned ×3, PUIS attaque) ; **kill des 2 engines en un tour à zéro perte** (Nauseous via Certus MortisRound→1HP + finition Aun'Shi normale ; Neurothrope one-shot Darkstrider) ; protège ses engines de sustain de l'over-extension (retire Aun'Shi de la radius Explodes, refuse d'envoyer Incisus en mêlée FinalJustice).

**CONFRONTATION (consensus vs divergences) :**
- **CONSENSUS (mécaniques cross-observées, confirmées par LES DEUX + recoupées gameconfig/i2)** :
  1. **CombatRestoratives + Narthecium umbrella (Apothecary)** — heal 4365/5456-Imperial + revive 100% à 4365 (unless Overkilled, once/turn, non-Mechanical) du cluster adjacent ; A « Aun'Shi 8536→1770 puis 7753 next turn », B « +5983 sur Aun'Shi + cleared Pinned ×3 ». gameconfig VERBATIM (CombatRestoratives 4365/5456 Imperial ; Narthecium 100% → 4365 unless Overkilled, 1×/tour, non-Mechanical). → wiki.
  2. **SereneUnifier cycle (Aun'Shi)** — R1 SenseOfStone −50%dmg / R2 ZephyrsGrace +1move / R3 StormOfFire +582dmg, à self+adjacents+T'au ≤2hex, persiste 1 round post-mort. Les DEUX l'observent live (A « −50% a halvé mon alpha » ; B « les 3 rotating, −50% blunt leur Psychic »). gameconfig VERBATIM. → wiki (re-confirme seed 80000).
  3. **Neuroparasite snowball + clear-on-death (Neurothrope)** — +1237 Psychic/niveau, monte sur Psychic-dmg OU Suppress, **clear quand le Neurothrope meurt OU la cible est heal**. A « Psychic sur cible parasitée = 2993 » ; B « parasite removed on its death ». gameconfig VERBATIM (+1237/niveau, clear on heal/Neurothrope-defeat). → wiki.
  4. **FinalJustice fires unless Overkilled (Azrael)** — fire même sur un kill cumulatif NON-overkill ; B « kill exact Certus → FJ a chunké Thaumachus 5592→1977 » ; A le liste comme trait Azrael. gameconfig VERBATIM (« unless Overkilled »). → wiki déjà documenté §FinalJustice (n+1).
  5. **Explodes friendly-fire au range (Aleph-Null)** — 25% maxHP Direct à TOUS les adjacents, friendly inclus ; B « ~4293 splash sur Azrael en le tuant au range » ; A confirme le trait. gameconfig VERBATIM (explodesDmg 25). → wiki déjà documenté §Explodes (n+1). (Note : B a observé ~4293 > 25%maxHP=2259 attendu — anomalie de splash, possible interaction Direct+tile/fire ; PAS une contradiction de la règle de base.)
- **DIVERGENCES** : **AUCUNE divergence de mécanique.** A et B sont entièrement concordants ; toutes les entrées about="theirs" matchent les auto-lectures adverses. Seule nuance non-contradictoire : les DEUX identifient l'**over-extension forward du carry/screen** comme la slip dominante de leur propre side (A : Nauseous (3,6) + Neurothrope (4,4) ; B : Darkstrider stranded (6,5)/(6,4)) — MÊME failure-mode vécu symétriquement, pas un désaccord. Rien à flagger en hypotheses.md comme contradiction.
- **CANDIDATES (1 seul observateur, non promues au wiki)** : ArcaneShield no-move → shield 4001 fin-de-tour à l'allié le + proche (B uniquement — A ne voyait pas le cast adverse) ; ScarabHive rejeté TargetHasFreeAdjacentTile sur cluster sans hex libre (A uniquement) ; MortisRound push 1 hex + secondary/splash (B uniquement, recoupé gameconfig « pushed back 1 hex » + « Heavy Weapon double »).

**Erreurs / leçons (les 2 sides) :**
- **A (PERDANT, ROOT CAUSE STRUCTURELLE)** : mis-recon — un roster chip/burst-once (r2/r3, AUCUN reach-tool, aucun moyen de toucher l'Apothecary back-screené) vs un engine 100%-revive + mass-heal = **textbook « can't out-damage the sustain » (H02 reach-fail + H11 self-healing anvil)**. Aurait dû flagger la loss structurelle AU RECON et jouer le least-bad all-in SPÉCIFIQUEMENT sur l'Apothecary (jamais tenté de l'atteindre).
- **A** : over-extension forward (Nauseous (3,6) + Neurothrope (4,4) dans le danger-5) → les deux focus-killés le tour suivant (Nauseous ~4740 juste en move-in via OW/réactions) — a tradé son screen + un Psyker pour du chip heal-off.
- **A** : jamais armé WeaverOfFate (Psychic ne touchait que 1-2 ennemis/tour → Ahriman jamais MAX → snowball Neuroparasite stalled) ; aurait dû positionner Doombolt pour catch 2-3 ennemis clusterés.
- **B (VAINQUEUR, slip réelle)** : final-blow sequencing sur Azrael — Certus a délivré le kill EXACT (pas overkill) → FinalJustice a fire et chunké Thaumachus 5592→1977 (harmless car Azrael était le dernier ennemi). Ligne correcte = chip-first puis UN coup overkillant, OU router le kill pour qu'aucune pièce de valeur ne soit adjacente.
- **B** : a tenu Certus (r3) + Thaumachus trop en arrière (row 9) les 1ers tours → a cédé le first-strike et mangé l'alpha ; monter la ligne ranged 1 tour plus tôt (toujours screenée) aurait permis de tirer en premier. Et Darkstrider laissé stranded forward post-kill — survit seulement parce que l'ennemi collapsait déjà.

**Frictions outil (cross-rapportées — déjà documentées) :**
- **rl_duel PLANS = MAX-roll damage** qui sur-state l'output réel vs blocking/cover/buffed : A « Doombolt plan [2409-3613] a dealt 1343 » → a failli mis-commit sur un « kill » inexistant. La vue devrait flagger expected (post-mitigation) ou marquer la range comme un max non-mitigé.
- **abilities-legality ne tient pas compte du spawn-tile requirement des summons** : ScarabHive listé castable now/+move, mais le cast réel a échoué TargetHasFreeAdjacentTile (cluster sans hex libre adjacent) → A a burné le move d'Aleph avant de découvrir le cast illégal. « TOUR ABANDONNÉ » a correctement préservé les actions antérieures.
- **labels MOI/ENNEMI de `view` RELATIFS à currentPlayer et FLIPPÉS entre captures** (B) ; le decisionView du state-file LAG le turn-flip → désambiguïser via `status` (autoritatif t1/t2), pas les labels relatifs de la vue.
- **header `view` figé « tour 4 »** sur plusieurs rounds distincts (B) — le compteur de tour affiché n'est pas un indicateur de round fiable ; lire le round-state, pas le label.

### Refs action logs

Action logs complets de CE run : `data/_sp_80072_A.json` + `data/_sp_80072_B.json` → archivés dans
`logs/selfplay/sp_80072_2026-06-23-b6.json` (action_logs des 2 camps + rosters + outcome, rejouable via seed 80072)
puis supprimés post-teardown. Séquence clé : A TIMED l'alpha hors-phase-(−50%) (Aun'Shi 8536→1770) mais committé forward dans le danger-5
(anti-cap) → Nauseous + Neurothrope focus-killés → 5v5→3v5→1v5 ; B HOLD cohésif (Certus OW-turret + Thaumachus ArcaneShield) bait l'over-commit,
puis tour décisif heal-first (Incisus CombatRestoratives Aun'Shi 1770→7753 + clear Pinned) → kill des 2 engines au range zéro perte
(Nauseous Resilient→1HP via MortisRound + finition normale ; Neurothrope one-shot Darkstrider) → swing 5v5→5v3 → élimination.

---

## seed 80085 — winner=team1 (ts=2026-06-23-b6)

### Rosters

| Équipe | Unités |
|--------|--------|
| **team1 (Player A / oracle)** | spaceStormcaller (Njal, Psyker/Stormcaller AoE + TermArmour) · tyranWingedPrime (Winged Prime, summon-engine AlphaWarrior+Hormagaunt, Flying, FJ) · custoVexilusPraetor (Aesoth, Resilient+BigTarget+VexillaMagnifica double-stun) · spaceBlackmane (Ragnar, WarHowl pump-engine + FJ + Saga charge) · deathBlightlord (Maladus, Resilient+TermArmour+ContagionsOfNurgle aura, FlailSwing overkill) |
| **team2 (Player B / oracle)** | admecDominus (Vitruvius, repair-engine + RadBombardment line-AoE) · genesBiophagus (Hollan, Healer+TwistedScience+Aberrant summon+Ambush) · darkaAzrael (Azrael, Overwatch + DarkTalonStrike Direct + LionHelm) · bloodDeathCompany (Lucien, Resilient + BlackRage auto-charge + Blast) · astraBullgryn (Kut, BigTarget anvil + FragBomb) |

### Adjudication

- `rl_duel.py status` : `*** BATTLE FINIE — winner AUTORITATIF = team1 (battleStatus.winner=3, unitsAlive=14) ***`
- A outcome_perceived = **W** (team1) ; B outcome_perceived = **L** (team2) → **winner_consensus = true** (les 2 sides + la source autoritative concordent)
- ⚠ `alive_by_team={}` post-Finished = VIDE (decisionView refuse hors-Running, piège H59) — non utilisé pour l'adjudication.
- **authoritative_winner = team1**

### Win-conditions (consensus croisé A.mine ≈ B.theirs et A.theirs ≈ B.mine)

**team1 win-condition** : mur durable **3 anchors Resilient/TerminatorArmour** (Maladus + Aesoth + Njal) qui kill les engines depuis des tuiles shallow à exposition quasi-nulle, pendant que le summon-engine (Winged Prime AlphaWarrior + Hormagaunt) screen et que WarHowl (Ragnar) burst la ligne mêlée ; l'aura ContagionsOfNurgle (Maladus) -armure croissante enable le FlailSwing one-shot du repair-engine.
→ Accord A.mine / B.theirs : **CONSENSUS** (B lit correctement le mur 3-Resilient comme la SOURCE, engines = gravy).

**team2 win-condition** : core sustain-summon Genestealer/Imperium ancré sur Hollan (Heal + TwistedScience pump + Ambush revive + Aberrant summon), screené par Kut BigTarget, nourri par Vitruvius repair + MasterAnnihilator mark ; Azrael Overwatch/LionHelm + Lucien BlackRage = pression dive.
→ Accord A.theirs / B.mine : **CONSENSUS** (A identifie Hollan comme le vrai wincon back-screené ; B confirme « engine-denial + reaction-punish, Hollan sustaining »).

### Confrontation A vs B (2 observateurs indépendants)

**CONSENSUS de mécaniques (confirmées par LES DEUX + recoupées gameconfig — inscrites au wiki, tag [self-play consensus, seed 80085])** :
1. **FinalJustice (Ragnar / Winged Prime)** — DEUX voies en UN match : Winged Prime tué par Lucien en OVERKILL → FJ DÉNIÉE (`IsActingBeforeDeath=0`) ; Ragnar tué à EXACTEMENT 1787 (no overkill) → FJ a fire ~3771 et a TUÉ le finisseur Hollan. gameconfig VERBATIM « unless Overkilled ». → wiki §FinalJustice (n+1).
2. **Ambush (Hollan / genesSmnAberrant)** — kill avec decoy un-cleared → résurrection FULL-HP (7477) next turn ; 2ᵉ kill (Ambush consommé) = permanent. Confirme Ambush sur un SUMMON. gameconfig VERBATIM. → wiki §Ambush (n+1).
3. **VexillaMagnifica (Aesoth)** — double-stun (cible + 1 ennemi adjacent additionnel) + Aesoth -66% dmg, cd2 ; single-hit Physical → ne tue PAS un Resilient. A « stun+kill Kut » / B « stun mon Kut → denié FragBomb → setup focus-kill ». gameconfig VERBATIM. → wiki §Aesoth (n+1).
4. **ContagionsOfNurgle (Maladus)** — aura -armure croissante (r1→r2→r3) tague les ennemis qui approchent (ArmorReduction1) ; A « softened chaque approchant, enable le FlailSwing one-shot Vitruvius » / B « chip mon armure effective avant contact ». → wiki §ContagionsOfNurgle (n+1).
5. **BlackRage (Lucien)** — set à 50% PV + auto-attaquant INCONTRÔLABLE. A (adversaire) « HP-halving + drift/auto-charge » / B (propriétaire) idem. gameconfig VERBATIM. → wiki §Lucien (n+1).

**SINGLE-OBSERVER recoupé gameconfig (1 detailed observer, A possédait Njal — inscrit au wiki avec recoup explicite, PAS tag consensus)** :
- **Stormcaller (Njal)** — UN cast a frappé Azrael (4185→2282) ET Hollan (5522→3771) en même temps (cible + adjacents Ice) = outil d'ouverture de focus multi-cible ; multi-hit Psychic ignore armure + bat floor Resilient. B liste Njal en threat mais il a turtlé (jamais online contre B) → pas de 2ᵉ observation live, recoupé gameconfig à la place. → wiki §Njal Tac.

**DIVERGENCES** : **AUCUNE divergence de mécanique.** A et B sont entièrement concordants sur tous les faits de jeu. Une seule divergence d'**ASSESSMENT** (PAS de mécanique) → flaggée hypotheses.md **H71** : B (perdant) lit le match comme une **loss STRUCTURELLE** (roster all-Power/Physical/Blast, 1 seule source Direct, vs 3 anchors Resilient+TermArmour = mur inattaquable, à flagger AU RECON) ; A (vainqueur) le décrit comme un **out-trade d'exécution** du screen jusqu'au lone engine Hollan. Désaccord sur la CAUSE de l'issue, pas sur un fait — les deux s'accordent sur winner=team1 et toutes les mécaniques.

### Séquences clés (résumé des action logs)

**Player A (team1, VAINQUEUR) :**
- Ouverture : SUMMON (AlphaWarrior → Warrior 7976 PV) + wedge cohésif, anchors Resilient (Maladus/Aesoth) en bait avant, fragiles (Njal/Ragnar) + engine (Winged Prime) screenés derrière. Cushion qualité avant contact (gap 7 rangées non rushé).
- Sur le dive ennemi (Vitruvius/Kut forward) : kill du REPAIR-ENGINE Vitruvius pour FREE — Maladus FlailSwing 3-hit depuis sa tuile courante (zéro over-extension), enable par WarHowl + l'aura ContagionsOfNurgle ; HazeOfCorruption splash sur le kill. (engine-over-anvil doctrine)
- Aesoth VexillaMagnifica stun+chunk l'anvil Kut (+ protège Aesoth bas-PV -66%) → fini par anchors depuis tuiles shallow ; carry jamais envoyé chasser l'anvil.
- Clôture proactive sous le round-cap : charge Ragnar pour chunk Azrael, puis Njal Stormcaller AoE (Azrael+Hollan en un cast) → finishes garantis → 4v1 propre → élimination. Hollan (back row 9) correctement caché par B mais le screen out-tradé jusqu'au lone engine.

**Player B (team2, PERDANT) :**
- Won the ENGINE WAR : overkill Winged Prime (FJ dénié) une fois avancé en reach, puis fini Ragnar (pump-engine) — bonne priorité engines>anvil + Direct/overkill pour denier FJ sur WP.
- Vitruvius RadBombardment tiré up la colonne ennemie : Suppress + chip 3 units (WP 3547, Njal 806, Maladus 887) = fort tempo MAIS le move qui aligne la ligne a stranded Vitruvius forward (3,4) → focus-killé (ROOT CAUSE : engine tradé pour du chip sur un mur Resilient = net loss, 1er domino).
- Azrael tenu un-attacked early (arm OW) mais l'adversaire a turtlé → reaction-engine jamais payé ; converti en dégâts actifs quand le clock a forcé l'engagement.
- LESSON-clé : fini Ragnar à EXACTEMENT 1787 (no overkill) avec son dernier corps Hollan → FJ riposte ~3771 a tué Hollan = 0 vs 3.

### Erreurs / leçons (les 2 sides)

- **A (VAINQUEUR, slip réelle)** : OVER-EXTENSION du Winged Prime (summon-engine) vers une tuile d'attaque forward (4,4) pour chip Kut + trigger un Hormagaunt → focus-killé le tour suivant (6491→mort). Le chip ne valait PAS l'engine ; failure-mode d'over-extension dominant, a coûté le meilleur snowball-engine pour le reste du match.
- **A** : tué l'Aberrant mais LAISSÉ son decoy un-cleared → résurrection full-HP (7477) next turn (Ambush). Aurait dû marcher sur le genesSmnDecoy (Steppable) le même tour. Coûté un tempo + un re-kill.
- **A** : no-op (tenté Aesoth normale sur Lucien avant de move Aesoth adjacent — harmless, action non consommée) + parking de Ragnar bas-PV (1787) adjacent à Hollan en fin (Hollan avait un K! dessus, non-décisif à 4v1).
- **B (PERDANT, ROOT CAUSE STRUCTURELLE)** : stranded Vitruvius (repair-engine) forward (3,4) pour RadBombardment → focus-killé (engine tradé pour chip sur Resilient = net loss, 1er domino). + over-extension sérielle de chaque corps dans la zone contact row5/6 (Kut, Aberrant, Azrael, Hollan) → le mur durable out-trade les fragiles un à un (failure-mode répété 5+ fois).
- **B** : final-blow sequencing — Ragnar fini à PILE 1787 (no overkill) avec le dernier Hollan → FJ a tué Hollan = double-mort, 0 vs 3. Ligne correcte = budgétiser l'overkill OU accepter de laisser Ragnar neutralisé à 1787.
- **B (recon-level)** : aurait dû flagger la loss STRUCTURELLE au deploy (roster all-Power/Physical/Blast, 1 seule source Direct = Azrael, vs 3 Resilient/TermArmour anvils = mur inattaquable) ; correct plan = engine-race + hold, jamais feeder les fragiles dans le mur, RÉSERVER l'unique burst armor-ignore (DarkTalonStrike) pour l'anvil-wincon late au lieu de le dépenser sur le Winged Prime. (cf. H71)

### Frictions outil (cross-rapportées)

- **RadBombardment (Vitruvius) = ligne à DIRECTION FIXE, pas free-aim** : `--target` sur un hex ennemi no-op silencieux (mutated=false, action NON consommée) quand le caster est hors de l'axe → repositionner + viser via `--to` un hex qui met les ennemis sur une ligne 6-directions. Non-obvious depuis le plan (qui montrait la cible reachable). (B)
- **Move silencieusement rejeté vers une tuile bloquée/unreachable** (mutated=false, unit reste sur place) → re-run `view`/`abilities` pour confirmer la position réelle AVANT d'attaquer ; le « move-then-ability » deux-temps doit être explicite. Un move qui n'a plus de cible/ability en range auto-finit l'activation. (A + B)
- **K! sur un SINGLE-HIT vs Resilient over-claim** : Aesoth normale sur Lucien `[1359-1359 K!]` mais single-hit floor à 1, ne tue pas — label trompeur, cohérent doctrine mais à flagger. (A)
- **header `view` figé « tour 3 »** + compteur turn interne stuck à 3 (flip à 4 sur endturn) → relié sur les unit-counts + l'absence de l'effet ⏱[ROUND-CAP] pour tracker le round réel vs le cap. (A)
- **await endpoint timedOut fréquent** (opponent oracle deliberating) → re-await ; worked as designed mais slow. (A + B)

### Refs action logs

Action logs complets de CE run : `data/_sp_80085_A.json` + `data/_sp_80085_B.json` → archivés dans
`logs/selfplay/sp_80085_2026-06-23-b6.json` (team1=37 actions, team2=27 actions, rosters + outcome, rejouable via seed 80085)
puis supprimés post-teardown. Séquence décisive : A bait-and-trade — anchors Resilient avant + summon screen, kill du repair-engine
Vitruvius pour FREE depuis tuile courante (FlailSwing + WarHowl + aura), stun-control de Kut (VexillaMagnifica), puis clôture
Stormcaller-AoE (Azrael+Hollan) → 4v1 → élim ; B engine-race (overkill WP/FJ-denied, kill Ragnar) mais stranded son repair-engine
forward (1er domino) et fini Ragnar non-overkill avec son dernier corps → FJ a tué Hollan (0 vs 3). Mur 3-Resilient a out-attrité le chip roster.

---

## seed 80020 — winner=team2 (ts=2026-06-23-b6)

> ⚠ **Run JOUÉ distinct du bloc seed 80020 ci-dessus** (ts=b5 = MATCH NON JOUÉ, runner absent, 0 action). CE run = match complet (team1=51 actions, team2=71 actions), **team2 W par démontage anti-Resilient + summon-snowball** d'un mur reaction-engine HOLD.

### Rosters

| Équipe | Unités |
|--------|--------|
| **team1 (Player A / oracle, player 3) — PERDANT** | genesMagus (Xybia) · custoKyrus (Tyrith) · astraDreir (Dreir) · worldEightbound (Azkor) · eldarMauganRa (Maugan Ra) |
| **team2 (Player B / oracle, player 4) — VAINQUEUR** | orksRuntherd (Snotflogga) · tauMarksman (Sho'syl) · adeptHospitaller (Isabella) · eldarFarseer (Eldryon) · blackPossession (Archimatos) |

### Adjudication

- A outcome_perceived = **L** ; B outcome_perceived = **W** → **winner_consensus = true** (A="L" & B="W" → team2).
- `rl_duel.py status --state-file data/_sp_80020_A.json` : `*** BATTLE FINIE — winner AUTORITATIF = team2 (battleStatus.winner=4, unitsAlive=38) ***` (champ NATIF battleStatus.winner post-Finished, H59).
- **authoritative_winner = team2** (élimination, PAS round-cap : 38 units team2 vivantes à la fin, team1 wipe). winner consensus parfait (A et B s'accordent ET ça matche le winner autoritatif).

### Win-conditions (consensus croisé A.theirs ≈ B.mine et A.mine ≈ B.theirs)

**team2 win-condition (VAINQUEUR)** : summon-snowball + attrition multi-hit anti-Resilient. SOURCE = **TRIPLE summon-engine** (Snotflogga SquigHound auto-Grots 7312 + Archimatos Incursion Bloodletters + Sho'syl MV71 drones) générant des corps depuis les rows 7-9, screené par le 12k Snotflogga anvil et sustained par **Isabella** (MedicusMinistorum regen aura + 2183 heal), JAMAIS besoin de diver ; **Snotflogga SquigHound multi-hit beat le floor Resilient** (floor-to-1 puis overkill dans la même activation) pour SOLO chaque anchor 9.5-10k.
→ Accord A.theirs / B.mine = **CONSENSUS** : A a correctement lu les 3 summon-engines + Isabella sustain comme le noyau structurellement UNREACHABLE derrière l'anvil.

**team1 win-condition (PERDANT, jamais réalisée)** : reaction-engine HOLD (Tyrith UnwaveringSentinel + Maugan Ra Overwatch r3 + Azkor OverwhelmingWrath Taunt) ancré sur 3 corps 9.5-10k Resilient, baitant le dive pour le punir (H03), + Dreir/Xybia summon-engines pour la masse board.
→ Accord A.mine / B.theirs = **CONSENSUS** : B a lu le mur Resilient + Overwatch reaction-side et son flaw — un roster melee/r2-r3 (seul Maugan Ra r3) SANS reach tool vers les engines/Healer row 7-9 = reach-fail structurel ; et H03 dive-punish INERTE vs un back-row qui ne dive jamais (le contre-profil 70052).

### Séquences clés (résumé des action logs — détail dans le state-file archivé)

**Player A (team1, perdant) :**
- T3-5 : avance cohésive, fragiles screenés — propre. L'erreur est venue à T7.
- T7 (ROOT CAUSE) : Dreir LeadingTheCharge dans le 12k bait-anvil Snotflogga à row 6 (+ Azkor/Tyrith suivant) sous pression d'horloge → over-extension de corps durables dans le focus ennemi DEPUIS une position où ses réactions (Sentinel/Overwatch/Taunt) ne pouvaient PAS trigger (l'ennemi tape au range/summons). Death-Riders summonés (4432 HP/2304 atk) mais Dreir projeté row 6 = focus-killé (Resilient overkillé).
- Chip futile sur Snotflogga : 1174 dealt → Isabella regen +1197 (net POSITIF pour l'anvil). MindControl +20% window gaspillé (Isabella out-healed tout le chip). Commit étalé T7-T8 → héros focus-killés un à un (Dreir → Azkor → Tyrith → Maugan Ra).

**Player B (team2, vainqueur) :**
- Hold cohésif (Snotflogga 12k anvil + Grots/drones screen des fragiles) ; refus de diver l'Overwatch Maugan Ra r3 + counter Tyrith ; laissé les anchors forced-melee adverses closer dans SA zone summon/AoE.
- Snotflogga SquigHound multi-hit a SOLO chaque Resilient en UNE activation : floor Dreir(10038) et Azkor(5307) à 1 puis le hit suivant overkille (WasOverkill=1) → multi-hit beat le clamp Resilient ; a freed Snotflogga des MindControl-taunts et cancelled l'AoE pending d'Azkor.
- Kill priority correcte (Dreir → Azkor → Tyrith counter → Maugan Ra turret), Resilient survivants finis par une 2ᵉ source/overkill (Tyrith floored par un Bloodletter puis overkillé à 46) ; Archimatos Incursion + drones Sho'syl ont flood un screen. Final : push de la summon-wave sur la Xybia fuyarde → wipe Xybia+Neophyte (one splash) → Finished AVANT round-cap. 38 units alive vs 0.

### Confrontation : consensus vs divergences

#### Mécaniques de CONSENSUS (rapportées des DEUX sides — cross-observable, recoupées gameconfig/i2)

1. **SquigHound (Snotflogga normale) multi-hit BEAT le floor Resilient** : 3 base hits + GetStuckIn + SquigHound extra hit ; floor un Resilient à 1 puis un hit LATER dans la MÊME activation overkille (WasOverkill=1) → SOLO Dreir 10038 ET contribue le floor sur Tyrith 9537. Summon un Grot 7312 après attaque ; un hit sur Xybia splash-tua un Neophyte adjacent. A(theirs, « multi-hit one-shots through Resilient, killed before ToughToKill/LeadingTheCharge ») + B(mine, séquence floor→overkill décrite). gameconfig `Resilient` confirme « reduced to 1 Health, unless Overkilled » → un multi-hit floor-puis-overkill-en-une-activation est LE mécanisme anti-Resilient. → **renforce wiki §3bis Snotflogga + §1 Resilient** [self-play consensus, seed 80020] (déjà au wiki, 3ᵉ confirmation : multi-hit ≥2 + floor→same-activation-overkill).
2. **MindControl (Xybia) — observé du côté VICTIME (B)** : Snotflogga repeatedly Taunted_OnlySpecificTargets + BlockMovement + CantUseAbility (−582 outgoing, +20% incoming) → forcé d'attaquer le taunter, actif disabled ; MAIS sa NORMALE sur le taunter reste dispo, et tuer le taunter clear le taunt immédiatement (free same-turn). A(mine, cast MindControl, +20% window) + B(theirs, subi le débuff exact, kill-taunter-clears). gameconfig §1 confirme verbatim (−582 / +20% / Taunted plus-haut-PV, curable par heal). → wiki §1 MindControl déjà complet (caster ET victime) [self-play consensus, seed 80020].
3. **OverwhelmingWrath (Azkor) = AoE PENDING annulée si Azkor tué avant son prochain tour** : cast → OverwhelmingWrath_PendingAttack (Taunt adjacents + −64% ranged subi) puis 2× AoE aux adjacents au DÉBUT du tour suivant. B(theirs, tuer Azkor avant son tour a cancelled l'AoE) + A(mine, OverwhelmingWrath taunt Snotflogga −64% ranged mais Azkor focus-killé, AoE pending non résolue). gameconfig confirme verbatim (« Deals 2x ... at the beginning of Azkor's next turn »). → wiki §3 Azkor déjà documenté (AoE retardée) [self-play consensus, seed 80020].
4. **Overwatch (Maugan Ra) reste ARMÉ across turns tant qu'il ne tire pas** : Overwatch_AutoAttack (critical effect), r3, fire free sur tout ennemi entrant ; disarm seulement après un tir. B(theirs, évité son arc plusieurs tours, disarm après un tir, attaque depuis >3 hex à gauche) + A(mine, reaction-engine HOLD avec Maugan Ra Overwatch — resté inerte car l'ennemi n'a jamais divé). gameconfig/wiki §3bis confirment (gate NOT-ATTACKED, peut bouger PUIS armer). [self-play consensus, seed 80020].
5. **Ambush (Xybia/Neophytes) = decoy + resurrect full au DÉBUT du tour suivant SI un decoy ami survit** : Neophytes revived 2× (whack-a-mole) ; tuer le SOURCE Xybia + le DERNIER Neophyte simultanément a flip Finished (équipe à 0 vivants) → la fenêtre resurrect ne s'est jamais ouverte. B(theirs, decoy/revive whack-a-mole) + A(mine, Xybia SpiritualLeader decoys/Neophytes a généré de la masse). gameconfig `Ambush` confirme verbatim (« at the beginning of their next turn, if there is still a friendly decoy ... resurrected with full Health »). → wiki §1 Ambush + Xybia déjà complets [self-play consensus, seed 80020].
6. **SupaCyborkBody + BeastSnagga block (Snotflogga) = damage-predictions over-estimate massivement** : Dreir LeadingTheCharge prédit gros mais landa ~821 net sur le 12k anvil (hits 950/1129 lourdement mitigés). A(mine, charge predicted high, landed ~821 net) — B ne contre-observe pas le chiffre exact mais décrit Snotflogga comme l'anvil-screen qui out-trade. Crédit confirmé par doctrine (prédictions vs block/crit-reduction non fiables). Candidat single-strong-observer + doctrine → pas une nouvelle inscription wiki (déjà couvert : juger au cascade, pas à la prédiction).

#### Divergences (entre observateurs)

Aucune divergence de FAIT sur les mécaniques (les 6 consensus concordent, recoupés gameconfig). Les deux lectures de win-condition s'accordent parfaitement (A.theirs ≈ B.mine ET A.mine ≈ B.theirs). La seule asymétrie est interprétative/d'exécution, PAS factuelle :
- **B (auto-critique)** : reconnaît avoir gaspillé un tour sur Ambush-reviving des Neophytes au lieu de beeliner le SOURCE Xybia un tour plus tôt (Xybia re-summonait) — exécution, pas mécanique.
- **Friction outil VigilanceEternal (Tyrith, A)** : « move-then-VigilanceEternal != VigilanceEternal-with-its-own-move » — l'actif a besoin de SON propre budget de move pour gap-close sur l'hex libre ; pré-bouger Tyrith consomme le move et rend l'actif no-op (« cast illegal sans bouger / TargetIsInRange »). → cohérent avec wiki §3 Tyrith (VigilanceEternal cible un ennemi déjà adjacent OU un hex libre dans la move range 2). → **hypotheses.md (friction outil, candidat self-play).**

### Erreurs identifiées (leçons, des deux sides)

- **A (perdant, ROOT CAUSE)** : commit forward T7 (Dreir charge row 6 + Azkor/Tyrith suivant) dans un cluster summon turtling qui n'avait AUCUNE raison de diver → réactions (Sentinel/Overwatch/Taunt) STRUCTURELLEMENT INERTES car l'ennemi tape au range/summons (H03 dive-punish ne s'applique PAS vs un back-row qui ne dive jamais — contre-profil 70052). Devait tenir un cluster défensif serré, pas feeder ses anvils.
- **A** : chip répété sur le 12k anvil Snotflogga pendant qu'Isabella out-heal chaque hit (regen +1197 > chip 1174) → gaspillé la charge Dreir, l'attaque Tyrith, et la window MindControl +20% sur une cible inkillable. Ignorer entièrement l'anvil unreachable.
- **A (recon-level)** : aurait dû flagger au recon que son roster all-melee/r2-r3 (seul Maugan Ra r3) n'a AUCUN reach tool vers les engines/Healer row 7-9 = reach-fail structurel. Avec un round-cap dur, pas de ligne gagnante → jouer un hold no-winner-parity propre plutôt que jeter 4 héros dans le focus.
- **A** : commit étalé sur plusieurs tours (Dreir T7, Azkor T7, Tyrith T8) → focus-killés un à un (death by piecemeal — le pire des deux mondes : ni all-in ensemble, ni hold).
- **B (vainqueur)** : T6 drone-chip sur Death Rider u147 = no-op (cible avait bougé/déjà fini) — re-check la tuile live avant de committer un summon. + SeekerMissile T4 dépensé sur Azkor (Resilient, floor wasted) — marker plus de valeur sur une cible soft non-Resilient. + late game sur Ambush-revive au lieu de beeliner Xybia.
- **LEÇON CENTRALE (consensus)** : vs un **back-row triple-summon-engine + Healer-sustain UNREACHABLE** (le contre-profil 70052 du reaction-engine HOLD), un roster melee/r2-r3 SANS reach n'a PAS de ligne gagnante — H03 (bait-the-dive) est INERTE car l'ennemi ne dive jamais. Reconnaître au recon : si reach=zéro vers les engines back-row ET l'ennemi est un turtle ranged/summon, le commit forward FEED le focus ; jouer pure-hold ou flagger la loss structurelle. Réciproquement, **Snotflogga SquigHound multi-hit est LE démanteleur de mur Resilient** (floor→overkill en une activation), démontable une-anchor-par-tour quand on le laisse closer dans sa zone.

### Refs action logs

Action logs complets de CE run : `data/_sp_80020_A.json` (51 actions) + `data/_sp_80020_B.json` (71 actions) → archivés dans
`logs/selfplay/sp_80020_2026-06-23-b6.json` (rosters + outcome team2, rejouable via seed 80020) puis supprimés post-teardown.
Séquence décisive : B hold cohésif (Snotflogga 12k anvil + summon screen, refus de diver Overwatch/counter) → A over-commit T7
(Dreir charge dans le bait-anvil row 6 + Azkor/Tyrith suivant, réactions inertes) → Snotflogga SquigHound multi-hit SOLO chaque
Resilient anchor (floor→overkill), Isabella regen négatant tout chip adverse, Archimatos/Sho'syl flood le board → focus-kill piecemeal
des 4 héros A → wipe Xybia final → 38 vs 0.

---

## seed 80097 — winner=team2 (ts=2026-06-23-b6)

> Match self-play oracle vs oracle. **team2 (Player B) VAINQUEUR** par snowball summon-flood (Yarrick SendInTheNextWave)
> + focus-kill ordonné des engines, malgré DEUX over-extensions early. team1 (Player A) a gagné la guerre des engines EARLY
> (Parasite + Thaumachus tués) mais a PERDU la guerre d'attrition LATE (le flood Yarrick+Anuphet + Morvenn carry back-row
> ont out-bodied sa force épuisée d'un lead 4v3 à 1v5).

### Rosters

| Équipe | Unités |
|--------|--------|
| **team1 (Player A / oracle, player 3) — PERDANT** | deathRotbone (Nauseous, Healer/revive) · thousInfernalMaster (Abraxas, summon-engine Psyker) · spaceWulfen (Ulf, durable melee FinalJustice) · astraPrimarisPsy (Sibyll, Psyker PsychicMaelstrom) · necroSpyder (Aleph-Null, LivingMetal/Explodes/Flying) |
| **team2 (Player B / oracle, player 4) — VAINQUEUR** | astraYarrick (Yarrick, summon-engine SendInTheNextWave, Resilient) · thousSorcerer (Thaumachus, control: Possession+ArcaneShield, DIED) · tyranParasite (Parasite of Mortrex, Flying melee Ripper-summon, DIED) · adeptMorvenn (Morvenn Vahl, Legendary ranged carry SanctorumMissile) · necroOverlord (Anuphet, LivingMetal sustain + ResurrectionOrb) |

### Adjudication

- `rl_duel.py status --state-file data/_sp_80097_A.json` : `stage=Finished` + ***« BATTLE FINIE — winner AUTORITATIF = team2 (battleStatus.winner=4, unitsAlive=21) »***.
- A outcome_perceived = **L** (6 tours) ; B outcome_perceived = **W** (7 tours) → **winner_consensus = true** (A="L" & B="W" → team2, MATCHE le winner autoritatif natif H59).
- ⚠ `alive_by_team={}` post-Finished (decisionView refuse hors-Running) — NON utilisé pour l'adjudication (piège H59) ; le champ natif `battleStatus.winner=4` est la vérité.
- **authoritative_winner = team2.** Élimination (pas de round-cap : 21 units team2 vivantes, team1 wipé).

### Win-conditions (consensus croisé A.theirs ≈ B.mine et A.mine ≈ B.theirs)

**team2 win-condition (VAINQUEUR)** : **Yarrick SendInTheNextWave summon-flood** (2 Cadian Guardsmen +1/allié défait, cap 5 ; back-row zéro-exposition ; les pertes propres de B MAXENT le flood) = la SOURCE qui a flippé un déficit 5v7 en 8v4 + grind les engines softés ; secondaire = Anuphet ResurrectionOrb (Necron Warriors round-scaling + LivingMetal regen ~854/tour) + Morvenn SanctorumMissile Blast r3 AoE depuis un back-row jamais atteint.
→ Accord A.theirs / B.mine = **CONSENSUS FORT** (A a correctement identifié Yarrick+Anuphet flood + Morvenn carry comme les engines qui l'ont out-bodied).

**team1 win-condition (PERDANT, jamais aboutie)** : **engine Psychic-summon-snowball** = Abraxas MasterOfTheTutelaries (cascade Screamer/Psychic-event) + Sibyll PsychicMaelstrom NoBlocking, sustain = Nauseous Healer/revive 75% Chaos. Source à protéger = la paire Psyker Abraxas+Sibyll.
→ Accord A.mine / B.theirs = **CONSENSUS** (B a correctement lu la paire Psyker Pierce100 NoBlocking comme le kill-vector, et l'a démantelée — Sibyll focus-kill puis Abraxas).

### Séquences clés (résumé des action logs — détail archivé en 4)

**Player A (team1, perdant) :**
- T4 : Aleph-Null placé forward (4,3) sur une tuile Thorns → focus-killé au tour ennemi AVANT de contribuer son ScarabHive (seul son Explodes a tradé ~2259 sur Parasite). Over-extension d'un durable qui aurait dû screener.
- T5 : Parasite (engine exposé) tué — cascade summon Abraxas a chunké 6776→3499 puis Ulf GreatFrostAxe 4-hit l'a fini EXACTEMENT (3499→0, Ice posé). Kill propre d'engine sur le dive (durable melee = bon outil).
- T7 : Sibyll PsychicMaelstrom a one-cast-K!'d Thaumachus (6305 en un cast, multi-hit 3466+2839, NoBlocking bypass shield) le moment où il a avancé en portée — priorité control-engine correcte. MAIS Nauseous (Healer slow move2) poussé forward (3,5) comme « bait » → focus-deleté (10761→1006→mort) SANS heal (ne peut pas heal l'Imperial Ulf, Chaos déjà morts). Engine sustain jamais livré.
- Late : chip Anuphet 8536→1159 avec 2 units mourantes mais pas fini (LivingMetal regen → 2013) ; le flood Yarrick (3 Guardsmen 3989/3989/723) + Morvenn back-row ont out-bodied le lead 4v3 → 1v5 → wipe.

**Player B (team2, vainqueur) :**
- Ouverture : Anuphet ResurrectionOrb + avance cohésive row-7 (board presence sans exposition).
- Over-extension #1 (la faute dominante, H03) : Parasite committé deep (4,4) pour finir l'INERT Aleph-Null (chaff non-engine) → focus-killé le tour ennemi, pendant qu'Abraxas restait libre de cast son flood (board flip 5v7 contre B).
- Over-extension #2 : Thaumachus (control fragile) poussé (3,6) pour finir un Ulf 1627 → focus-killé de loin (perte de l'outil Possession pour un kill de chaff).
- Ulf tué au RANGE à (3,4) SANS allié éligible adjacent → **FinalJustice no-op (zéro riposte)** — removal propre de l'anti-summon avant de flooder.
- **THE comeback move** : Yarrick SendInTheNextWave back-row (zéro exposition) → 5 Guardsmen (scalés par les propres pertes de B) + ~4000 burst sur Nauseous → 5v7 → 8v4, puis focus-kill ordonné (Nauseous sustain → Sibyll Psyker → Horrors → Abraxas) = la W.

### Confrontation : consensus vs divergences

#### Mécaniques de CONSENSUS (cross-observable des DEUX sides — recoupées gameconfig)

1. **SendInTheNextWave (Yarrick)** : summon 2 Cadian Guardsmen +1/allié défait (cap 5), back-row no-move, fire immédiat ; le flood se MAXE par les pertes propres. A(theirs) + B(mine). gameconfig verbatim (base 2910 HP/1746 ; B a observé 3989/2394 = buffé par sa propre aura Contagions, non load-bearing). → **INSCRIT wiki §Yarrick** (wincon late d'attrition + paradoxe de scaling).
2. **MasterOfTheTutelaries (Abraxas)** : 1 cast → Pink Horror + 2 Screamers car les summons auto-attaquent au spawn et leurs hits Psychic (via InfernalPacts) re-déclenchent la clause Screamer-par-Psychic = cascade self-feeding ; summons action dépensée au spawn (ne peuvent pas re-agir). A(mine) + B(theirs). gameconfig verbatim. → **INSCRIT wiki §Abraxas** (cascade self-feeding + summon action spent).
3. **Pink Horror → Split → 2 Blue Horrors** (à la mort, sauf Overkill) : daemon resilience qui gonfle le body-count. A(mine) + B(theirs). gameconfig verbatim : `Split {thousSmnBlueHorror}` base 1528 HP (live 2093 = scaling), « Does not apply if Overkilled ». → **INSCRIT wiki §thousSmnPinkHorror** (nouveauté — n'y était pas).
4. **AttemptedPossession (Thaumachus)** : possède la cible ET ses summons → ils attaquent le camp du caster-victime ; **les summons possédés bougent AVANT d'attaquer** (A a vu ses Screamers row1→row6 puis attaquer son camp). A(mine, high conf) live-confirme le recon-only H28 ; gameconfig verbatim. B(mine, low conf) ne l'a jamais résolu live. → **INSCRIT wiki §Thaumachus** (upgrade H28 recon-only → vérifié).
5. **FinalJustice no-op sans cible éligible adjacente (Ulf)** : tué à (3,4) sans allié éligible adjacent → riposte fire avec ZÉRO dmg. B(theirs) + A(roster/threat). gameconfig confirme « performs a normal attack on an ELIGIBLE target ... unless Overkilled ». Déjà richement documenté wiki §1/§Ulf (n multiples) — RE-CONFIRMÉ, pas ré-inscrit (redondant).
6. **Resilient single-hit clamp → besoin d'un finisher (Nauseous)** : un K! single-hit floor à 1 HP, NE tue PAS ; budgéter un coup séparé. B(theirs, « K!-count ne soustrait pas le clamp Resilient ») + A(threat « Overkill or Resilient drops to 1 »). gameconfig verbatim. Déjà documenté wiki §1 (n multiples) — RE-CONFIRMÉ, pas ré-inscrit.

#### Divergences (entre les deux observateurs)

1. **AttemptedPossession résolu vs non-résolu** : A l'a SUBI live (high conf, effet pleinement observé) ; B ne l'a jamais résolu (low conf, « ambiguous/risky as a friendly-fire tool from my framing, never resolved its true effect live »). PAS une contradiction de fait — A a la vérité live + gameconfig la confirme ; B a simplement évité de gambler l'ability. → consigné en hypotheses.md comme divergence de confiance/résolution (A=vérifié-correct).
2. **Persistance des moves de repositionnement (non-attaquants)** : B (friction, about=mine) rapporte que les moves PURS (sans attaque) semblent REVERT au turn-flip (Anuphet/Morvenn/Yarrick snap back ; seuls les units qui ont ATTAQUÉ gardent leur position forward) → positionnement défensif délibéré inefficace. A ne cross-observe pas ce comportement (n'en parle pas). Observateur unique, candidat friction-outil. → hypotheses.md (self-play divergence A/B, à vérifier : artefact state-file self-play ou règle réelle).
3. **Header de tour figé** : A (« tour 3 · joueur 3 » stale chaque tour) ET B (« tour 4 » figé tout le combat) rapportent INDÉPENDAMMENT un compteur de tour UI gelé → friction d'observabilité PARTAGÉE (pas une divergence : les deux convergent que le label « tour » est un placeholder, fier au round-counter interne de `status`). → déjà friction connue (cf. blocs antérieurs).

### Erreurs identifiées (leçons, des deux sides)

- **A (perdant)** : a gagné la guerre des engines EARLY (Parasite T5 + Thaumachus T7) mais a PERDU la guerre d'attrition LATE — il a continué à FEED le front avec des units bas-PV (Nauseous 1664, Sibyll 2664) dans le focus ranged-summon adverse → out-tradé d'un lead 4v3 en 1v5. Une fois Nauseous/Sibyll chunkés, il fallait CONSOLIDER (Abraxas + summons cohésifs, refuser les trades), PAS présenter des units mourantes à un flood de focus-fire supérieur.
- **A** : Aleph-Null forward (4,3) Thorns T4 = over-extension d'un durable qui aurait dû screener → focus-killé avant tout apport ScarabHive.
- **A** : Nauseous (Healer slow) poussé « bait » (3,5) T7 → deleté sans heal (ne peut pas heal l'Imperial Ulf, Chaos déjà morts) ; le Healer-engine n'a JAMAIS livré de sustain → l'aurait dû tenir back-anchor ou l'accepter non-contributeur.
- **A** : summons committés forward dans la reach 2-hex de Thaumachus → Possession les a retournés (row1→row6 + attaque son camp) ; reconnaître la menace Possession et garder les summons hors-portée tant que Thaumachus vit.
- **A** : chip Anuphet 8536→1159 non-létal (LivingMetal regen → 2013) = dmg gaspillé sur une sustain-body regen ; mieux valait tuer 2 Guardsmen actifs (retirer des corps qui shootent ses fragiles) que demi-tuer un engine qui regen.
- **B (vainqueur)** : DEUX over-extensions propres (Parasite deep pour finir l'INERT Aleph-Null ; Thaumachus forward pour finir un Ulf 1627) → 2 héros tradés pour du chaff, laissant Abraxas libre de flooder. A GAGNÉ MALGRÉ ces fautes UNIQUEMENT grâce au flood Yarrick (amplifié par ses propres pertes) — contre un roster sans son comeback-engine, ces 2 trades auraient été fatals. H02 = kill l'ENGINE pas le chaff ; H03 = ne pas over-extend un durable pour du chaff.

### Refs action logs

Action logs complets de CE run archivés dans `logs/selfplay/sp_80097_2026-06-23-b6.json` (action_logs des 2 camps + rosters + outcome team2, rejouable via seed 80097) puis state-files supprimés post-teardown. Séquences décisives résumées ci-dessus.

---

## seed 80031 — winner=team2 (ts=2026-06-23-b6)

> Match self-play DÉCISIF par ÉLIMINATION (PAS un round-cap no-winner) : team2 a wipe team1 en ~8 tours. `status` → `*** BATTLE FINIE — winner AUTORITATIF = team2 (battleStatus.winner=4, unitsAlive=17) ***`. Matchup STRUCTUREL : un roster team1 melee/short-r3 SANS reach-tool (no r4+/deep-strike/flyer) vs un engine ranged-summon team2 (drone+Aberrant body-advantage) safe row 8 → reach-fail loss à flagger au recon (classe H02-inapplicable, cf. 97001/98000).

### Rosters

| Équipe | Unités |
|--------|--------|
| **team1 (Player A / oracle, player 3) — PERDANT** | thousTerminator (Toth) · spaceWulfen (Ulf) · custoBladeChampion (Kariyan) · orksKillaKan (Snappawrecka) · admecDestroyer (Sy-gex) |
| **team2 (Player B / oracle, player 4) — VAINQUEUR** | emperNoiseMarine (Shiron) · genesBiophagus (Hollan) · tauMarksman (Sho'syl) · worldExecutions (Tarvakh) · admecManipulus (Actus) |

### Adjudication

- A outcome_perceived = **L** (8 tours) ; B outcome_perceived = **W** (8 tours) → **winner_consensus = true** (A="L" & B="W" → team2, ET ça MATCHE le winner autoritatif).
- `rl_duel.py status --state-file data/_sp_80031_A.json` : `stage=Finished currentPlayer=4 alive_by_team={}` (decisionView refuse hors-Running → alive vide, NON-discriminant ; cf. piège H59) + `*** winner AUTORITATIF = team2 (battleStatus.winner=4, unitsAlive=17) ***` (champ NATIF battleStatus.winner = autoritatif).
- **authoritative_winner = team2** (élimination, PAS no-winner — 17 units team2 vivantes, team1 wipe).

### Win-conditions (consensus croisé A.theirs ≈ B.mine et A.mine ≈ B.theirs)

**team2 win-condition (VAINQUEUR)** : body-snowball summon/drone + focus ranged depuis la sécurité. SOURCE = **Hollan** (genesBiophagus : Healer + Ambush-revive + TwistedScience HP-buff + AberrantHypermorph 7477-HP Resilient screen) + **Sho'syl** (tauMarksman : SeekerMissile delayed-nuke + MV71SniperDroneSquad → jusqu'à 3 drones 1996-HP renouvelables) construisant des CORPS expendables qui focus-fire row 8 sans exposer les fragiles ; carries **Shiron** (line-AoE ranged ExcruciatingFrequencies) + **Tarvakh** (Khorne/TrophyTaker melee snowball). Le moteur qui a GAGNÉ = l'avantage-corps drone/Aberrant out-number la turtle adverse et la démonte sans diver.
→ Accord A.theirs / B.mine = **CONSENSUS** (A a correctement lu Sho'syl comme la source un-counterée de la chip-war + Hollan comme l'engine de sustain/summon).

**team1 win-condition (PERDANT, jamais réalisée)** : mur mêlée durable (Kariyan Resilient-scaling + Toth TerminatorArmour/TimeFlux-revive + Ulf FinalJustice) screenant une **tourelle Sy-gex Overwatch** (HeavyGravCannon anti-Mechanical/Terminator) + Snappa BigTarget ranged — SOURCE = attrition via réactions (Overwatch + FinalJustice) en baitant la mêlée adverse dans le cluster durable. **INERTE ICI** : l'ennemi n'a JAMAIS eu à diver (son ranged out-range), et la mêlée team1 ne pouvait pas atteindre les engines row 8.
→ Accord A.mine / B.theirs = **CONSENSUS** (B a correctement lu la reaction-turtle dive-punish de team1 et son flaw = reach-zéro vers ses back-row engines + bait inerte vs une ligne ranged qui ne dive jamais).

### Séquences clés (résumé des action logs — archivés, cf. refs)

**Player B (team2, vainqueur) :**
- Dérivé la propriété du roster quand la vue a flippé sur son tour (team B = Shiron/Hollan/Sho'syl/Tarvakh/Actus, PAS le set u95-103 labellé « MOI » à la 1ʳᵉ vue tour-ennemi) — caught avant de mis-play (foot-gun `view` perspective-currentPlayer, cf. divergence outil).
- Frame dive-punish-INVERSE : a mené avec un screen expendable Aberrant+Actus, fragiles+carry safe row 8 ; baité l'ennemi à over-committer (a poussé son screen 7477→544 mais n'a jamais touché un héros).
- **Kill-order ENGINE/THREAT depuis tuiles SAFE ou expendables** : Ulf FIRST T5 (retire le counter SavageKiller anti-summon — chunké via NORMALES depuis des corps déjà-adjacents pour ne PAS trigger SavageKiller) → Snappa T6 (best ranged + son Explodes a chunké Toth 9035→5646 ET Kariyan 5973→3714 = 2 kills mis en place gratis) → Kariyan Resilient (floor-à-1 par drone, fini par Tarvakh = 1er kill Khorne) → la tourelle Sy-gex (après avoir baité son Overwatch avec Tarvakh 710) → Toth en dernier (focus outright, TimeFlux revive n'a pas porté).

**Player A (team1, perdant) :**
- Recon-flag CORRECT : Actus engine-INERTE (seul Mechanical de son équipe → DefendTheDivineWork self-only, GalvanicField inerte) demoté de repair-engine craint à chaff soft (cf. H02 nuance engine-inerte). Killé PERMANENT pour FREE depuis tuiles safe (Sy-gex SentinelDirectives HeavyGravCannon ~5690 + Snappa) — le SEUL clean play du match.
- Hold cohésif les ~4 premiers tours pour baiter la mêlée dans le mur durable + Sy-gex Overwatch (doctrine réciproque H03) — bon INSTINCT mais INERTE ici (l'ennemi avait une ligne ranged self-suffisante qui n'a jamais eu besoin de diver → le dive-bait n'a jamais payé, la chip-war l'a run down).
- REFUS correct d'envoyer Snappa deep pour un K? non-garanti sur Hollan (revive via Ambush + expose son Explodes-on-death) — « kill CE tour ou ne pas committer ».
- Salvage des doomed units : Kariyan 2380 a tué l'Aberrant PERMANENT (2ᵉ kill, multi-hit MartialInspiration beat Resilient) avant de mourir ; Toth a tué des drones.

### Confrontation : consensus vs divergences

#### Mécaniques de CONSENSUS (rapportées des DEUX sides — cross-observable, recoupées gameconfig)

1. **SavageKiller (Ulf)** : réaction 5-hit Power QUI NE SE DÉCLENCHE QUE (a) sur un summon spawn/move adjacent, ou (b) un ennemi adjacent qui tente un ACTIF (résout AVANT l'actif) — une **attaque NORMALE depuis un corps DÉJÀ-adjacent ne le trigger PAS**. B(theirs, a EXPLOITÉ : chunk Ulf safely via normales pour ne jamais feed SavageKiller) + A(mine, Ulf dans son roster, counter anti-summon). gameconfig verbatim (seuls summon-adjacency + actif-adjacent triggent). → **INSCRIT wiki §3bis (Ulf) [self-play consensus, seed 80031]** : l'actionable = pour tuer Ulf sans le trigger, frapper en NORMALE depuis une unité déjà-adjacente (ni summon, ni actif).
2. **Explodes (Snappa)** : à la mort, 25% maxHP Direct à TOUS les adjacents (friendly-fire). B(theirs, killing Snappa adjacent à Toth+Kariyan a dealt ~2260 à chacun = 2 kills setup gratis) + A(mine, clustering Snappa serré pour BigTarget aura = son explosion risquait/touchait sa propre ligne). gameconfig confirme `explodesDmg=25` Direct, all-adjacent, no friend/foe filter. Déjà wiki §1 (n multiples) — RE-CONFIRMÉ self-play, pas ré-inscrit (la TENSION BigTarget-veut-adjacence × Explodes-punit-adjacence est notée en mistake A).
3. **TimeFlux (Toth)** : self-regen RÉPÉTABLE (873 + dmg du dernier hit reçu, cap 4365/tour) + revive ONE-TIME au time-ghost à 2401 (même si Overkill). B(theirs, observé 5646→9035 et 1684→3161, out-DPS via 6v1 numbers, final focus K! outright) + A(mine, son unit le plus durable = last man standing). gameconfig verbatim. Déjà wiki §1 + §3bis (Toth) — RE-CONFIRMÉ, pas ré-inscrit. ⚠ doctrine cross-confirmée : un Toth affaibli heal-back vite → le tuer en UN tour focus, PAS le chiper.
4. **Overwatch (Sy-gex)** : tire UNE volée sur le 1er mover dans l'arc r3 puis est SPENT le reste du tour ennemi (2ᵉ mover passe sans réaction), RE-ARME au début de SON propre tour (gate=not-attacked). B(theirs, Tarvakh ate 710 puis fragiles/drones sont passés free) + A(mine, tourelle Overwatch armée). gameconfig (trait Overwatch). Déjà wiki §1 + §3bis (Sy-gex l.1038, cross-observé seed 80042) — RE-CONFIRMÉ self-play 2ᵉ fois, pas ré-inscrit. EXPLOIT = bait l'OW avec un corps durable, puis opérer free dans l'arc.
5. **Ambush (Aberrant summon de Hollan)** : à la 1ʳᵉ mort → decoy Steppable + RESURRECT full-HP (7477) au début du prochain tour si un decoy survit ; 2ᵉ mort PERMANENT. B(mine, l'Aberrant tué à 544 par FinalJustice d'Ulf a revive full 7477) + A(theirs, l'a SUBI : chip 544 → kill → decoy → revive full, puis 2ᵉ kill Kariyan PERMANENT). gameconfig (`Ambush_CanResurrect` 1×). Déjà wiki §1 [self-play consensus, seed 80085] (Aberrant summon Ambush) — RE-CONFIRMÉ 2ᵉ self-play, pas ré-inscrit. Doctrine : kill un summon Resilient renouvelable SEULEMENT quand le 2ᵉ/permanent kill est on the table (sinon il revive full).
6. **Resilient (Kariyan)** : un hit létal single floor à 1 PV (saved), un hit SÉPARÉ suivant le tue ; un multi-hit bypass en un cast. B(theirs, 912→1 via drone, fini ensuite) + A(mine, Kariyan a tué l'Aberrant via multi-hit MartialInspiration beat Resilient). gameconfig (i2 « if not already at 1 HP »). Déjà wiki §1 (n multiples) — RE-CONFIRMÉ, pas ré-inscrit.
7. **SeekerMissileFrequencyLock / Markerlight (Sho'syl)** : lock + missile retardé qui fire au DÉBUT du prochain tour de Sho'syl, TRACK la cible (impossible à dodge en bougeant), removable seulement par repair/heal-cleanse. A(mine, markerlit Kariyan ~3564 puis Sy-gex 5585→mort) + B(theirs, SeekerMissile delayed-nuke). gameconfig verbatim. Déjà wiki §3bis (Sho'syl) — RE-CONFIRMÉ, pas ré-inscrit.
8. **PowerTrip (Snappa)** : au full HP les normales font +1 hit / armor-shred mais self-loss 5% maxHP ; en-dessous du full il perd le bonus ignore-armor PowerTrip_FullHealth. B(theirs, Snappa s'est drop 9037→7681 juste en attaquant) + A(mine, DakkaDakka self-cost). gameconfig verbatim (`extraHit=1, hpPct=5`). → Cohérent, déjà couvert par l'entrée Snappa (PowerTrip ignore l'armure) — la NUANCE self-cost 5%/full-only est mineure, notée mais non décisive.

#### Divergences (entre les deux observateurs)

1. **Cause de la mort d'Actus** : A (about=mine) = killé PERMANENT pour FREE quand il a over-extendu à row 5 (Sy-gex SentinelDirectives HeavyGravCannon + Snappa depuis tuiles safe). B (about=mine) = « spent it forward to kill Ulf — the only hero-side body I lost, a worthwhile trade ». → divergence de RÉCIT causal, PAS de fait : B a délibérément poussé Actus (engine-inerte demoté) forward pour participer au kill d'Ulf T5, et A l'a achevé quand il était exposé. Les deux conviennent qu'Actus était un corps expendable (engine-inerte) ; A voit un free-kill d'over-extension, B un trade choisi. → hypotheses.md (self-play divergence A/B, lecture d'exécution non-mécanique).

### Erreurs identifiées (leçons, des deux sides)

- **A (perdant) — RECON MISS STRUCTUREL** : aurait dû flagger une probable reach-fail loss au recon — roster 4 melee/short-r3 SANS reach-tool vs des engines softs safe row 8 derrière un screen Resilient renouvelable + une ligne ranged self-suffisante. Per H02 reach-attainability : quand les engines sont structurellement inatteignables ET l'ennemi ranged out-range, ni l'attrition lente ni le hold ne portent. A a joué un hold-and-bait hopeful qu'une ligne ranged ne-divant-jamais a simplement out-chipé.
- **A** : clusterer Snappa (Explodes friendly-fire) serré au CENTRE de sa ligne pour la BigTarget aura → quand l'ennemi a focus-killé Snappa dans le cluster, l'explosion a touché sa propre ligne. Garder l'Explodes au BORD du cluster, pas au centre (tension BigTarget-veut-adjacence × Explodes-punit-adjacence).
- **A** : staged le mur à row 5 + laissé Ulf (chipped 6420) le plus forward → 1er focus-kill. Pousser dans la kill-zone d'une ligne ranged qui out-range = handed le 1er trade ; reconnaître le dive-bait inerte plus tôt et soit all-in pour crack le screen T4-5, soit grind défensif — pas un demi-pas en avant.
- **A** : early-turns passifs pendant que l'ennemi chipait free — le round-cap + l'avantage de portée adverse rendait les tours passifs favorables à EUX. Forcer une décision ~T5 (clock mandate) au lieu de drifter dans une attrition perdue d'avance.
- **B (vainqueur)** : 2× émis une attaque Tarvakh en supposant l'auto-move-into-range ; la tuile choisie (2,5) n'était pas hex-adjacente à Kariyan (3,4) → no-op, Tarvakh stranded (2,5), activation gaspillée. Utiliser `moves`/`abilities` pour confirmer la tuile adjacente EXACTE (4,4 valide) AVANT de committer (cf. friction outil #1).
- **B** : perdu le compte des units déjà spent → fired un drone/Tarvakh sur une unité sans action restante (mutated=False no-op). Harmless mais sloppy — lire « A ACTIVER » entre chaque action dans un tour multi-kill.
- **B (note adversariale même en W)** : exposer Sho'syl + Actus forward pour sécuriser le kill d'Ulf n'était acceptable QUE parce que B était déjà up un corps ; contre une tourelle live (Overwatch non-spent) ça aurait pu coûter un fragile pour moins de reward.

### Refs action logs

Action logs complets de CE run archivés dans `logs/selfplay/sp_80031_2026-06-23-b6.json` (action_logs des 2 camps + rosters + outcome team2, rejouable via seed 80031) puis state-files supprimés post-teardown. Séquences décisives résumées ci-dessus.

---

## seed 80000 — winner=team1 (ts=20260625-b7)

> ⚠ **6ᵉ run self-play DÉCISIF de la seed 80000** (cf. blocs antérieurs : run #1 team1 W, #2/#4/#6 no-winner round-cap, #3 team2 W, #5 no-winner quality-ahead). CE run = **team1 W NET par CONVERSION offensive avant le round-cap** : A a tué l'unique ranged ennemi (Vitruvius) T4 pour convertir l'ennemi en ALL-MELEE, puis a screené ses fragiles derrière un mur mêlée inatteignable et focus-killé l'engine-buff (Aun'Shi) + le carry (Tanksmasha) une fois le buff défensif Aun'Shi expiré. **AUCUN EnvEndBombardment** (combat fermé round ~4-5). `status` autoritatif = **winner=team1 (battleStatus.winner=3, unitsAlive=13)**.

### Rosters

| Équipe | Unités |
|--------|--------|
| **team1 (Player A / oracle, player 3) — VAINQUEUR** | ultraTigurius (Tigurius) · tyranTyrantGuard (Tyrant Guard) · custoAtlacoya (Atlacoya) · admecRuststalker (Exitor-Rho) · tauMarksman (Sho'syl) |
| **team2 (Player B / oracle, player 4) — PERDANT** | spaceRockfist (Arjac) · tauAunShi (Aun'Shi) · orksNob (Tanksmasha) · admecDominus (Vitruvius) · deathPutrifier (Pestillian) |

### Adjudication

- A outcome_perceived = **W** ; B outcome_perceived = **L** → A="W" & B="L" → **winner_consensus = true** (concorde avec l'autoritatif).
- `rl_duel.py status --state-file data/_sp_80000_A.json` : `stage=Finished currentPlayer=3 alive_by_team={}` + ligne autoritative **« BATTLE FINIE — winner AUTORITATIF = team1 (battleStatus.winner=3, unitsAlive=13) »**. ⚠ `alive_by_team={}` post-Finished est VIDE par construction (decisionView refuse hors-Running) — NE rien inférer de ce vide ; le champ NATIF `battleStatus.winner=3` = vérité (H59/H64).
- **authoritative_winner = team1.**

### Win-conditions (consensus croisé A.mine ≈ B.theirs et A.theirs ≈ B.mine)

**team1 win-condition (VAINQUEUR)** : burst ranged armor-bypass + AoE Psychic = Sho'syl (SeekerMissile / MV71 drone, RangedSpecialist) one-shot la backline depuis tuile safe, enable par Tigurius StormOfWrath (Psychic NoBlocking AoE bypassant armure ET block) + Atlacoya TalonsOfTheEmperor scaling-finisher. SOURCE/enablers à protéger = Sho'syl (reach-tool qui tue l'unique ranged ennemi) + Tigurius (AoE qui softène le cluster).
→ Accord A.mine / B.theirs = **CONSENSUS** (B identifie correctement Sho'syl drone-summoner + Tigurius armor-bypass comme le focus-core ranged, screené par les tanks TG/Atlacoya).

**team2 win-condition (PERDANT, jamais réalisée)** : melee-brawl + buff-aura + repair = Aun'Shi SereneUnifier cycle-buff engine + Pestillian Nurgle armor-strip + Tanksmasha BeastSlayer anti-BigTarget carry, sustained par Vitruvius repair-engine ; devait CLOSER et grind. SOURCES = Aun'Shi (buff) + Vitruvius (repair) — wincon crippled car (a) le buff Aun'Shi ne touchait que self+adjacent (seul T'au, pas d'extension) et (b) le Mechanic de Vitruvius était inerte (aucun allié Mechanical à réparer).
→ Accord A.theirs / B.mine = **CONSENSUS** (A lit correctement Aun'Shi SOURCE + Vitruvius enabler ranged, et la limite de portée du buff).

### Séquences clés (résumé des action logs — détail archivé)

**Player A (team1, VAINQUEUR) :**
- **T4 — kill l'UNIQUE ranged ennemi (Vitruvius) en premier** via MV71 drone de Sho'syl (one-shot ~9035 depuis back-left, zéro exposition) → convertit l'ennemi en ALL-MELEE → A peut désormais screener ses fragiles derrière un mur mêlée que l'ennemi ne peut plus atteindre. **Coup décisif du match.**
- **Tour défensif de consolidation EN AVANCE** (au lieu de pousser les fragiles) : mur mêlée (TG/Atlacoya/Exitor) devant, Tigurius/Sho'syl/drones derrière ; laisse l'ennemi all-melee diver, et PUNIT au tour SUIVANT une fois le buff défensif Aun'Shi (SenseOfStone −50% dmg subi) EXPIRÉ → ses coups landent à plein.
- **T5 double-kill** (buff −50% tombé) : TG CrushingClaws + Tigurius StormOfWrath (splash AoE touche Tanksmasha ET Aun'Shi) + Sho'syl drone → kill Tanksmasha ; puis Exitor (expendable 292 PV) CordClaw finit l'Aun'Shi AoE-softé = coupe le buff-engine à la source.
- Pestillian (Resilient+Explodes) tué au RANGE / 2-hit → l'explosion 25%maxHP chipe Arjac GRATIS (consomme la 1ʳᵉ réduction TerminatorArmour d'Arjac) ; puis Arjac Resilient overkillé via Exitor OptimizedGait multi-hit + drone Sho'syl.

**Player B (team2, PERDANT) :**
- T1 (ROOT MISTAKE) : avance toute la ligne mêlée à row 5 + engines (Vitruvius/Aun'Shi) screenés row 6 → met les engines screenés DANS la reach ranged+Psychic-NoBlocking ; Vitruvius (repair-engine, unique ranged) focus-delete T4 = enemy converti en all-melee à son désavantage.
- T2 : focus-kill correct d'Exitor-Rho (Direct-assassin, 8032→292) avec Tanksmasha+Arjac, DÉCLINE de le finir avec Aun'Shi pour ne pas exposer l'aura-engine — bonne priorité (engine≫anvil) mais kill non bouclé.
- T3 (désespéré 2v6) : commit ses 2 derniers durables (Arjac/Pestillian Resilient) forward pour chunker Sho'syl — tue un drone, ne finit pas Sho'syl ; opponent cleanup. Throughout : **PAS de reaction-engine** (zéro Overwatch armé) → le « hold-and-punish » réciproque ne s'est jamais matérialisé.

### Confrontation : consensus vs divergences

#### Mécaniques de CONSENSUS (rapportées des DEUX sides — cross-observable, recoupées gameconfig/i2)

1. **SereneUnifier R1 SenseOfStone = DÉFENSIF (−50% dmg SUBI, pas dealt)** : A(theirs, high) + B(mine, high) concordent que la phase R1 réduit le dmg PRIS → le cluster buffé est tanky CE round. ⚠ **TIMING DÉCISIF côté VAINQUEUR ce run** : A a explicitement TIMÉ son burst APRÈS l'expiration du −50% → dmg effectif ~doublé (le SeekerMissile dépensé PENDANT le buff sur Pestillian n'a fait que ~2793 au lieu de ~5782). gameconfig : `SenseOfStone` = effet moteur sans i2 (sémantique au wiki). → **n+1 inscrit wiki §3bis Aun'Shi** (côté gagnant cette fois).
2. **MV71SniperDroneSquad (Sho'syl)** : drone summon qui frappe au **Damage stat de Sho'syl** (boosté RangedSpecialist +80%) → one-shot Vitruvius (~9035) depuis back-left SANS bouger Sho'syl ; chaque cast summon un drone permanent qui re-attaque chaque tour. A(mine, high) + B(theirs, high : « 2 drones up by turn 2, chunked Aun'Shi 2946 from safe row 6 »). gameconfig confirme. (déjà au wiki §3bis — pas ré-inscrit.)
3. **StormOfWrath (Tigurius)** : Psychic NoBlocking AoE, primary + splash jusqu'à 5 adjacents, bypasse armure ET block (AnvilShield/BigTarget/GuardianOrganism/Terrifying), Psychic exclu de TerminatorArmour. A(mine, splash a touché Tanksmasha + Pestillian + Aun'Shi) + B(theirs, critical « ignores ALL my mitigation, killed Vitruvius »). gameconfig confirme. (déjà au wiki §3bis + synergie §5bis.)
4. **PutridExplosion (Pestillian)** : explose à la mort = 25% maxHP Toxic aux adjacents sauf Death Guard (friendly-fire). A(theirs, « kill at range → l'explosion chipe Arjac GRATIS ») + B(mine, « ideal forward Explodes/Resilient body »). gameconfig confirme (25% maxHP Toxic). (déjà au wiki §1/§3bis.)
5. **Foehammer (Arjac)** : Ranged-tag Power, +dmg/Character défait (snowball, les DEUX camps comptent), Stun. A(theirs, « stunned + chunked Sho'syl, scales per kill, don't feed it ») + B(mine, anvil Resilient). gameconfig confirme. (déjà au wiki §3bis + §5bis.)

#### Divergences (entre les deux observateurs)

1. **PutridExplosion consomme la 1ʳᵉ réduction TerminatorArmour de la cible adjacente** : A seul (about=mine/theirs, high) rapporte que l'explosion (Toxic) compte comme la « 1ʳᵉ attaque du tour » d'Arjac → réduite −75% par sa TerminatorArmour ET CONSOMME cette réduction (les coups suivants du tour landent plein). B ne cross-observe pas cette interaction. Mécaniquement cohérent avec gameconfig (TermArmour −75% 1ʳᵉ attaque, Toxic NON exclu — seul Psychic/Direct le sont). → **hypotheses.md H76 (self-play candidate, observateur unique A, recoupé gameconfig = plausible).**
2. **Source réelle de team2** : A surpondère Aun'Shi comme LA source ; B décrit son plan exécuté comme un brawl mêlée + buff + repair où Vitruvius était l'enabler ranged-clé qu'il a perdu T4 (root mistake d'avoir avancé les engines screenés dans la reach ranged). Accord sur la VALEUR des engines, divergence d'EXÉCUTION/lecture — PAS une mécanique.

### Erreurs identifiées (leçons, des deux sides)

- **B (perdant) — ROOT CAUSE** : avancer toute la ligne (engines Vitruvius+Aun'Shi screenés inclus) à row 5/6 T1 DANS la reach d'une compo ranged+Psychic-NoBlocking + drone. « Row 6 safe » est FAUX vs NoBlocking/ranged/drone-reach — Vitruvius (repair-engine + unique ranged) deleted T1/T4 = enemy converti all-melee à son désavantage. Garder les engines row 0-1 (intouchables), ne pousser QUE les Resilient/Explodes comme screen.
- **B — RECON reach-fail** : roster melee-only (après mort Vitruvius) SANS reach-tool (r3+/deep-strike/flyer) pour toucher Tigurius (back-row Psychic NoBlocking) ni Sho'syl (kiting summoner) → matchup structurellement hard vs ranged-summoner+NoBlocking-core. À FLAGGER au recon (H02/H71) et jouer un screen serré depuis l'arrière, pas avancer dans l'ouvert.
- **B** : over-commit du mur row 5 T2 (Tanksmasha + Aun'Shi forward) → perdus au focus de retour ; Aun'Shi (aura-engine) aurait dû être rapatrié row 0-1 après avoir granté son buff, pas laissé à (5,6).
- **B** : aucun reaction-engine (Overwatch/counter/turret) sur le roster Chaos/Xenos brawl → le « hold-and-punish-the-dive » réciproque ne pouvait PAS se déclencher (doctrine : la réciprocité exige un reaction-engine). A nourri des corps dans le focus sans riposte.
- **A (vainqueur, notes adversariales malgré la W)** : laissé Sho'syl (fragile reach-tool clé) à (1,5) où Arjac a closé + Foehammer (stun + chunk ~1812) — survécu seulement car A dominait déjà ; screener son flanc Est plus dur ou la rapatrier le tour d'avant.
- **A** : Atlacoya dive (5,5) deep-behind-lines pour setup le kill Aun'Shi avant de réaliser qu'Exitor (expendable) pouvait finir depuis une tuile plus naturelle — over-extension mineure d'un tank durable, non punie car l'ennemi collapsait.
- **A** : SeekerMissile dépensé sur Pestillian PENDANT le buff Aun'Shi −50% → halvé (~2793 au lieu de ~5782) ; mis-timé (cible non-buffée aurait donné full value). Cf. consensus #1 (timing post-buff).

### Refs action logs

Action logs complets de CE run archivés dans `logs/selfplay/sp_80000_20260625-b7.json` (action_logs des 2 camps + rosters + outcome team1, rejouable via seed 80000) puis state-files supprimés post-teardown. Séquences décisives résumées ci-dessus.

---

## seed 80003 — winner=team1 (ts=20260625-b7)

> ⚠ **3ᵉ outcome DISTINCT pour les rosters seed 80003** (cf. les 2 blocs 80003 ci-dessus : `conv80003` = no-winner round-cap ; `batchfix` = team2 W par élimination). CE run = **team1 W par élimination PROPRE** (`battleStatus.winner=3, unitsAlive=15` ⇒ pas un mutual-wipe : team1 ferme 9v1→cleanup AVANT le round-cap). C'est la PREMIÈRE victoire du roster double-summon-engine + alpha Deathleaper/Jain Zar : **punir l'over-commit du Psyker-trio** par un alpha-strike d'une seule activation collective.

### Rosters

| Équipe | Unités |
|--------|--------|
| **team1 (Player A / oracle, player 3) — VAINQUEUR** | tyranDeathleaper (Deathleaper) · astraYarrick (Yarrick) · templSwordBrother (Godswyl) · ultraInceptorSgt (Bellator) · eldarJainZar (Jain Zar) |
| **team2 (Player B / oracle, player 4) — PERDANT** | blackPossession (Archimatos) · necroSpyder (Aleph-Null) · thousSorcerer (Thaumachus) · thousAhriman (Ahriman) · bloodSanguinary (Nicodemus) |

### Adjudication

- A outcome_perceived = **W** (4 tours) ; B outcome_perceived = **L** (3 tours) → **winner_consensus = true** (A="W" & B="L" → team1, ET matche le winner autoritatif).
- `rl_duel.py status --state-file data/_sp_80003_A.json` : `*** BATTLE FINIE — winner AUTORITATIF = team1 (battleStatus.winner=3, unitsAlive=15) ***` (champ NATIF post-Finished, H59). `unitsAlive=15` = team1 a 15 corps vivants (5 héros + Guardsmen/Inceptors summonés) = élimination, PAS un round-cap (qui aurait `winner=None`).
- **authoritative_winner = team1.**

### Win-conditions (consensus croisé A.mine ≈ B.theirs et A.theirs ≈ B.mine)

**team1 win-condition (VAINQUEUR)** : alpha-assassination de l'over-commit — **Deathleaper `FearOfTheUnseen`** (vanish 1 round → teleport sur N'IMPORTE QUEL hex libre + attaques +3x Direct bonus = re-crée un deep-strike-avec-attaque APRÈS que le deep-strike est dépensé → atteint la SOURCE board-flip Archimatos qu'aucune autre unité ne peut toucher) couplé à **Jain Zar `SilentDeath`** (Pierce80 adjacency-chain AoE : un cast a tué Thaumachus + chipé Aleph-Null + touché Ahriman dans le même cluster) et **Godswyl `ThunderousAssault`** (stun + overkill finisher). Source = la reach teleport de Deathleaper + l'AoE de Jain Zar permettant d'alpha toute la ligne Psyker en UN tour quand l'ennemi a clusteré en portée. Summon-engines (Bellator Inceptors, Yarrick Guardsmen) = écran expendable + chip sans risquer les héros.
→ Accord A.mine / B.theirs : **CONSENSUS** (B lit team1 comme « board-flood double summon-engine + fast-alpha Deathleaper teleport + Jain Zar cleave » — concorde sur la SOURCE alpha = Deathleaper + Jain Zar).

**team1 win-condition (PERDANT, jamais réalisée)** : triple-Psyker armor-ignore AoE engine (Ahriman `Doombolt` Pierce100 NoBlocking + Thaumachus `AttemptedPossession`/`ArcaneShield` + Archimatos `Incursion`/`Possession` summons) amplifié par `WeaverOfFate` (max-roll si 3+ ennemis prennent du Psychic) + Nicodemus heal + Aleph-Null repair. SOURCE = les 2 carries armor-ignore (Ahriman/Thaumachus). **Edge GASPILLÉ** : team ranged/Psyker fragile qui devait KITER l'ennemi all-melee et AoE le cluster depuis la safety (rows 7-8), PAS diver.
→ Accord A.theirs / B.mine : **CONSENSUS** (A a correctement identifié Archimatos = engine board-flip #1, Ahriman/Thaumachus WeaverOfFate = snowball Psychic, et DÉMOTÉ Aleph-Null = repair INERT car seul Mechanical → CRITICAL→LOW).

### Séquences clés (résumé des action logs — archivés en 4)

**Player A (team1, VAINQUEUR, 4 tours) :**
- **T3-4 (setup, REFUS du bait)** : refus de diver le bait forward (Aleph-Null, un repair-hub INERT) avec les carries fragiles dans la portée Psychic → avance cohésive, summon Guardsmen/Inceptors comme écran forward expendable, et **pré-arme Deathleaper `FearOfTheUnseen`** (vanish + teleport-strike au prochain tour).
- **T5 (DÉCISIF)** : l'adversaire over-commit TOUT son cluster rows 5-6 en portée → alpha de TOUTE la ligne Psyker en UN tour en ordre de priorité : **Deathleaper `FearOfTheUnseen` K! Archimatos (summon-engine) EN PREMIER** (8034→K!, +3x bonus Direct ignore armure) ; Jain Zar `SilentDeath` AoE tue Thaumachus ; Yarrick finit Aleph-Null (son `Explodes` pope l'`ArcaneShield` d'Ahriman) ; Bellator Inceptors + Godswyl `ThunderousAssault` finissent Ahriman. **5v5 → 9v1.**
- A tué les engines/Psykers AVANT qu'ils puissent cluster-AoE + armer `WeaverOfFate` (roster A = zéro Psyker, mais WeaverOfFate trigger sur LES UNITÉS DE A prenant du Psychic) → snowball adverse nié.
- Erreurs (notées même sur W) : T4 Bellator déplacé à (4,4) pour un `DeathFromAbove` sur Aleph-Null mais hors-portée (`TargetIsInRange`) = move déjà dépensé = activation gaspillée (cf. TF16). T6 deux normales Inceptor (id 69) auto-résolues sur Nicodemus = 0 dmg no-op consommant l'action (cf. TF16/TF18 — out-of-range non rejeté pour les summons). Adversarial : tuer Archimatos a nécessité de teleport Deathleaper deep à (6,5) + Jain Zar/Godswyl forward rows 5-6 = SUR-EXTENSION qui n'a marché QUE parce que l'alpha fut létal en un tour ; vs un adversaire prudent gardant ses Psykers back, ce deep-commit aurait stranded les carries.

**Player B (team2, PERDANT, 3 tours) :**
- **T1 (mistake)** : HOLD passif comme team ranged (nudge 2 écrans durables Aleph-Null/Nicodemus, casters back) MAIS SANS repositionner les casters pour kiter/maximiser la range → tempo gratuit donné à l'ennemi (avance + 2 Guardsmen summonés).
- **T2 (ROOT CAUSE)** : commit les TROIS casters fragiles (Ahriman/Thaumachus/Archimatos) forward rows 5-7 pour chiper des engines qu'il ne POUVAIT PAS tuer (6000+ HP, Resilient/MkXGravis) → over-extension textbook → l'ennemi a alpha les 4 casters en un tour. WeaverOfFate armé live (Doombolt split 3-way Bellator+Yarrick+Guardsman → 3+ ennemis-Psychic) MAIS max-roll gaspillé en attaquant Bellator en MÊLÉE adjacente (Flame Pierce25 ~646 vs MkXGravis double-armure, au lieu du Psychic Pierce100 à range 2).
- **Final (1v8)** : Nicodemus seul → tua un Guardsman 326-HP du coin le moins menacé (seule action constructive ; loss déjà structurelle).

### CONFRONTATION (consensus vs divergences)

#### Mécaniques de CONSENSUS (rapportées des DEUX sides — cross-observable, recoupées gameconfig)

1. **`FearOfTheUnseen` (Deathleaper) = re-deep-strike full-board + 3x bonus Direct** : A(theirs→mine, K! Archimatos full-HP 8034 depuis backline) + B(theirs, effets `FearOfTheUnseen_TeleportingIn` + `_ExtraDamage`, relocate (1,0)→(6,5), untargetable while vanished). gameconfig confirme verbatim (« vanishes, cannot be targeted 1 round ; next turn attacks deal +3x Direct ET move to any free hex within Synapse / Tall Grass / non-adjacent à un ennemi »). → **INSCRIT wiki §3bis Deathleaper** (l'insight non-déductible = RECRÉE un deep-strike-avec-attaque APRÈS dépense du deep-strike → atteint N'IMPORTE QUELLE backline = engine-killer ; à TIMER pré-armé avant le tour où l'ennemi cluster en portée).
2. **`SilentDeath` (Jain Zar) = thrown adjacency-chain AoE, caster NE bouge PAS** : A(mine, 1 cast = kill Thaumachus + chip Aleph-Null + hit Ahriman même cluster) + B(theirs, « cleaves target + up to 3 adjacent, Pierce80 beats Resilient per-target, never cluster fragiles »). gameconfig confirme. (déjà au wiki §3bis Jain Zar — re-confirmé.)
3. **`Doombolt` (Ahriman) = 3 hits TOTAL distribués sur tous les ennemis ≤2 hex, +1/fire hex (cap 9), re-usable on kill** : A(theirs, AoE Psychic NoBlocking ignore armure/MkXGravis) + B(mine, observé split 3-ways ~1342/1519/1355 — concentré single-target ~2409-3613, spread = ~1 hit chacun mais arme WeaverOfFate cheap). gameconfig confirme verbatim. (déjà au wiki §2 Ahriman — re-confirmé.)
4. **`WeaverOfFate` (Ahriman+Thaumachus) feed-par-Psyker-splash, ORDRE compte** : A(theirs, snowball si 3+ MES unités prennent du Psychic) + B(mine, Doombolt split 3-way ARME → cast Thaumachus SUIVANT = max-roll ; ⚠ le cast trigger doit PRÉCÉDER le bénéficiaire dans le même tour). gameconfig confirme le trait. (déjà au wiki §interactions Psyker-splash→WeaverOfFate — l'ordre-intra-tour re-confirmé.)
5. **`ArcaneShield` (Thaumachus) absorbe le spill avant les HP** : A(theirs, shield ~5483 a mangé le SilentDeath spill sur Ahriman → HP resté 8032 ; pope-le d'abord via Explodes/chip) + B(mine). gameconfig confirme (4001 base, le live = scaling). (déjà au wiki §3bis Thaumachus — re-confirmé.)
6. **`MkXGravis` (Bellator) double-armure bypassée par Psychic NoBlocking/Pierce100, MAIS bloque la mêlée low-pen** : A(theirs, Bellator MkXGravis inutile vs core Psychic) + B(mine, Flame Pierce25 near-fully blocked ~646 vs MkXGravis double-armor → attaquer DEPUIS la range 2 pour le profil Psychic Pierce100). gameconfig confirme (« any incoming Damage goes through Armour a second time ; not on Crits »). (déjà au wiki §1/§3bis — re-confirmé, leçon weapon-selection-à-range pour le caster.)
7. **`Explodes` (Aleph-Null) = 25% maxHP Direct aux adjacents, friendly-fire leur cluster + pope shields** : A(theirs/mine, killer Aleph-Null DANS leur cluster → pope l'ArcaneShield d'Ahriman GRATIS) + B(mine, friendly-fire risk). gameconfig confirme (`explodesDmg:25`). (déjà au wiki §1/§3bis — re-confirmé.)
8. **`DeathFromAbove` (Bellator) = 1 Inceptor/round écoulé, land adjacent + attaque immédiate, caster doit MOVE en range** : A(mine, 3 Inceptors à round 5 chip Ahriman 7360→3155 + corps durables) + B(theirs, 3 Inceptors round 3 = +3 corps qui surround). gameconfig confirme verbatim. (déjà au wiki §3bis/§3ter — re-confirmé ; ⚠ le caster doit move en range AVANT, sinon no-op = TF16.)

#### Divergences (entre les deux observateurs)

1. **`EnvFireTileDamage` / fire hexes = dmg start-of-turn (DoT-class, Effect_Type=5)** : B seul (about=theirs, ~142 sur Bellator au start, lié à PsychicStalk fire-setting + Doombolt +1-hit/fire-hex). A ne cross-observe pas. → candidat single-observer (confidence med B) → `hypotheses.md` (self-play divergence A/B).
2. **`Thorns_DefenseReduction` sur entrée de tile (4,6) sur Aleph-Null** : B seul (about=mine, Effect_Refresh depuis une tile-source). A ne cross-observe pas. → candidat single-observer (confidence low B) → `hypotheses.md` (terrain tile-effect à reconfirmer ; apparenté §3quater Thorns côté Godswyl).
3. **Issue : aucun désaccord d'issue** (A="W"/B="L" concordent avec le winner autoritatif team1) — pas une divergence.

### Refs action logs

Action logs complets de CE run archivés dans `logs/selfplay/sp_80003_20260625-b7.json` (action_logs des 2 camps + rosters + outcome team1, rejouable via seed 80003) puis state-files supprimés post-teardown. Séquences décisives résumées ci-dessus.

---

## seed 80004 — winner=team1 (ts=20260625-b7)

### Rosters

| Équipe | Unités |
|--------|--------|
| **team1 (Player A / oracle, player 3) — VAINQUEUR** | necroOverlord (Anuphet, DIED) · thousAhriman (Ahriman, DIED) · emperNoiseMarine (Shiron, survived) · templSwordBrother (Godswyl, DIED) · thousTerminator (Toth, survived) · necroSmnWarrior (Necron Warrior summoné, survived) |
| **team2 (Player B / oracle, player 4) — PERDANT** | astraCreed (Creed) · darkaCompanion (Forcas) · thousTzaangor (Yazaghor) · spaceStormcaller (Njal) · darkaAsmodai (Asmodai) · astraSmnKell (Kell summoné) · astraNpc1Guardsman x2 (summonés) |

### Adjudication

- A outcome_perceived = **W** (6 tours) ; B outcome_perceived = **L** (5 tours) → A="W" & B="L" → **team1**.
- `rl_duel.py status --state-file data/_sp_80004_A.json` : `*** BATTLE FINIE — winner AUTORITATIF = team1 (battleStatus.winner=3, unitsAlive=14) ***` (champ NATIF battleStatus.winner). `alive_by_team={}` post-Finished (decisionView vide hors-Running — NON discriminant, cf. H59).
- **authoritative_winner = team1.** **winner_consensus = true** (A et B s'accordent ET ça MATCHE le winner autoritatif).

### Win-conditions (consensus croisé A.mine ≈ B.theirs et A.theirs ≈ B.mine)

**team1 win-condition (VAINQUEUR)** : **moteur de burst Psychic** = Ahriman `Doombolt` (Psychic Pierce100/NoBlocking, 3 hits répartis sur tous les ennemis ≤2 hex) spread du Psychic sur 3+ ennemis en UN cast → **arme `WeaverOfFate` sur Ahriman ET Toth** (MAX dmg ce tour) → Toth `HellfyreMissileRack` au MAX frappe la cible primaire PLUS chaque ennemi ayant subi du Psychic ce tour = multi-kill en une activation. SOURCE/enabler = Ahriman (le seul spreader Psychic) ; Shiron `ExcruciatingFrequencies` (Blast r3 6-hit) = l'exécuteur single-target fiable + Toth `TimeFlux` anvil durable ; Anuphet `ResurrectionOrb` = body-engine d'écran.
→ Accord A.mine / B.theirs = **CONSENSUS** (B a correctement identifié Anuphet summon-engine + Ahriman Doombolt burst comme sources, Shiron+Toth comme backbone durable).

**team2 win-condition (PERDANT, jamais pleinement réalisée)** : double engine = Creed `SupremeCommander` summon-snowball (Guardsmen qui agissent au spawn + Kell bodyguard via `SwornProtector`) + Njal `Stormcaller` Psychic-AoE armor-ignore, package réaction Dark-Angel = Forcas (Overwatch Strike-stance anvil) + Asmodai (`ExemplarOfHate` mark +728 melee/OW + anti-Chaos sur le roster 100% Chaos de A). Le snowball Psychic secondaire (Yazaghor `WeaverOfFate` fed par Njal) n'a JAMAIS fired (Njal n'a jamais touché 3+ unités de A).
→ Accord A.theirs / B.mine = **CONSENSUS** (A a correctement lu Creed bodies + Asmodai mark/exec comme sources, Njal/Yazaghor Psychic comme engine inerte).

### Séquences clés (résumé des action logs)

**Player A (team1, vainqueur) :**
- T1 : `ResurrectionOrb` (Anuphet) pour un Necron Warrior gratuit (round-scaling, zéro risque) → écran de la back-line fragile (le Warrior a survécu jusqu'à la fin).
- Tour décisif : `Doombolt` (Ahriman) → spread Psychic sur 3 ennemis → **`WeaverOfFate` armé sur Ahriman ET Toth** (cascade Effect_Refresh sur e=90 et e=96) → Toth `HellfyreMissileRack` au MAX a **one-shot les DEUX Cadian Guardsmen** (2564/2569 HP) + double-tap Forcas en UNE activation. ⚠ pour atteindre la portée Doombolt, Ahriman a marché dans l'Overwatch armé de Forcas (~6500 dmg, 8032→1589) puis est mort le tour suivant = enabler perdu.
- Priorité de kill : enablers/carries dans l'ordre (Asmodai l'anti-Chaos → Kell pour stripper le bodyguard de Creed → Creed → Yazaghor le Psychic-engine → Njal) plutôt que grind le chaff.
- Shiron `Eviscerate` r3 6-hit = l'exécuteur single-target qui a fermé chaque kill suivant.

**Player B (team2, perdant) :**
- T4 : avance cohésive forward + Creed summon-screen + Forcas Overwatch arm depuis une position turtle héritée → MAIS over-extension (Forcas à (4,5) + Guardsmen auto-pathés forward-right) → 3 corps dans la reach r4-5 ennemie → focus-killés au tour ennemi pour UN Ahriman chunké.
- T5 : conversion propre du dive → K! Ahriman (le carry Psychic critique) avec une normale Creed cheap (1589 exact) = meilleur play du match ; puis focus du Godswyl marqué (Njal+Asmodai+Yazaghor) MAIS Yazaghor roll bas → Godswyl laissé à 100 HP (K? au lieu de garantir).
- T6 : K! Anuphet (summon-engine) via Creed 5342 + Yazaghor 3194 → démantèle le wincon ennemi (Ahriman+Anuphet+Godswyl morts). Gagne la guerre des engines (passe de their-5 à their-3).
- T6-T8 : MAIS bleed sa propre ligne un corps à la fois (Asmodai, Creed, Yazaghor focus-killés sur des tours consécutifs — JAMAIS rétractés après chaque kill) → gagne les engines mais PERD l'attrition vs le backbone durable Shiron(Blast)+Toth(self-heal) → fin 0v3.

### Confrontation : consensus vs divergences

#### Mécaniques de CONSENSUS (rapportées des DEUX sides — cross-observable, recoupées gameconfig)

1. **`WeaverOfFate` armé par UN Doombolt → MAX-dmg sur les DEUX Psykers (Ahriman+Toth) le même tour** : A(mine, cascade Effect_Refresh e=90/e=96, conf high) + B(theirs, Doombolt re-arm + Psychic-spread). gameconfig `--trait WeaverOfFate` confirme « In any turn where 3 or more enemy units have taken Psychic Damage, this unit will deal the maximum possible Damage. » → l'INSIGHT non-déductible = un SEUL Doombolt (3 hits distribués ≤2 hex) suffit à dépasser le seuil 3-ennemis-Psychic ET arme le trait sur CHAQUE Psyker allié possédant WeaverOfFate (pas que le caster).
2. **`HellfyreMissileRack` (Toth) = profil HeavyRound (PAS Psychic) qui frappe la cible PLUS chaque ennemi ayant subi du Psychic CE tour, au MAX sous Weaver** : A(mine, 1 cast = kill 2 Guardsmen + double-tap Forcas, conf high) + B(theirs, scale sur les ennemis Psychic-damaged). gameconfig `--ability HellfyreMissileRack` confirme verbatim (« additional 1x to each enemy unit on the map that was dealt Psychic Damage this turn »). Cooldown multi-tour (indispo 2 tours).
3. **`Overwatch_AutoAttack` (Forcas, Strike stance) fire à l'INSTANT où un ennemi MOVE en range, même si Forcas a attaqué ce tour** : A(theirs, 6 hits ~6500 sur Ahriman entrant, conf high) + B(mine, Strike stance auto-OW ré-armé à l'endturn). gameconfig (`darkaCompanion`/CalibaniteGreatsword) confirme « Strike Stance: At the end of his turn, Forcas starts Overwatching, even if he attacked. » → l'INSIGHT = le warning OVERWATCH de la vue était EXACT ; ignorer un OW armé = perte de l'enabler.
4. **`SupremeCommander`/`SwornProtector` (Creed) = 2 Guardsmen qui agissent au spawn + Kell auto-bodyguard au 1er ciblage de Creed** : A(theirs, Kell doit mourir avant que Creed soit killable, conf high) + B(mine, Guardsmen ~3989 HP agissent immédiatement, Kell ~5107 HP). gameconfig confirme (SupremeCommander summon 2 + Kell étend à 3 ; SwornProtector = Kell switch-hex et prend le dmg à la place de Creed s'ils sont adjacents).
5. **`ResurrectionOrb` (Anuphet) = 1 Necron Warrior par round écoulé (+1 par LivingMetal mort), corps durable d'écran** : A(mine, T1 free body, screen back-line, survived) + B(theirs, snowball SOURCE à couper, 1/round). gameconfig confirme verbatim. (déjà au wiki §3bis Anuphet — re-confirmé self-play.)
6. **`TimeFlux` (Toth) = self-heal anvil (873 + dmg du dernier hit subi, cap 4365/tour) + revive une fois à 2401 HP → le chip est gaspillé** : A(mine, backbone durable) + B(theirs, mes chips 818-841 quasi-fully regen, conf high). gameconfig confirme verbatim. (déjà au wiki §1 TimeFlux — re-confirmé : « budgéter une 2ᵉ source de kill, traiter comme 2 barres de vie ».)
7. **`TerminatorArmour` (Njal) blunt les gros hits single-source + can't-be-Suppressed → grindy** : A(theirs, K! Shiron over-stated, 1010 au lieu de ~3500 sur le 1er hit, conf med) + B(mine, TermArmour). gameconfig confirme (−75% 1ʳᵉ attaque/tour, exclut Psychic/Direct). → l'INSIGHT = les prédictions `K!` over-statent vs un porteur TermArmour (la réduction 1ʳᵉ-hit non modélisée) → traiter K! vs TermArmour comme K? + stacker une 2ᵉ source. (friction → TF04.)

#### Divergences (entre les deux observateurs)

1. **`LordOfTempests` (Njal) : les normales de Njal deviennent énormes sur une cible Iced (+237/hex d'Ice) — engine secondaire Ice→normal-buff** : B SEUL (about=mine, high — « Njal normal vs Iced Godswyl montrait 6055 K! ; la vraie valeur de Stormcaller = le buff Ice→normale, pas le hit Stormcaller lui-même »). A ne cross-observe PAS (Njal a peu agi côté A, jamais subi l'enchaînement Ice→normale). gameconfig `--ability LordOfTempests` confirme la RÈGLE (« +237 Damage for each hex surrounding him covered in Ice ; hex of each enemy hit gets covered in Ice ») → candidat single-observer (la règle est confirmée mais l'enchaînement Stormcaller-Ice→LordOfTempests-normale-buff comme ENGINE n'est pas cross-observé). → `hypotheses.md` H78 (self-play divergence A/B, B=conf high + recoupé gameconfig).
2. **`Doombolt` re-cast + scaling fire-hex (PsychicStalk pose des feux, +1 hit/hex En Feu)** : B seul (about=theirs, conf med — « un Ahriman vivant snowballe Fire+Psychic, killing it à 1589 essentiel avant re-arm »). A ne mentionne pas le fire-setting. gameconfig confirme verbatim (Doombolt re-usable on kill + +1 hit/fire hex). Déjà au wiki §3bis Ahriman → PAS une vraie divergence (mécanique déjà connue, juste non cross-observée ce match). Pas porté.
3. **Issue : aucun désaccord d'issue** (A="W" / B="L" concordent avec le winner autoritatif team1).

### Erreurs identifiées (leçons, des deux sides)

- **A (vainqueur)** : a marché Ahriman (son enabler Psychic) dans l'Overwatch EXPLICITEMENT armé de Forcas pour atteindre la portée Doombolt (~6500 dmg, mort le tour suivant) → ligne plus propre = armer WeaverOfFate depuis une tuile HORS arc OW, ou tuer/déplacer Forcas d'abord, préservant l'engine pour des Doombolts répétés.
- **A** : over-extension d'Anuphet à (4,4) + Godswyl à (4,5) deep dans le cluster ennemi → focus-killés. Trade net hugement positif (perdu 3, tué 7) MAIS les pièces-engine sont mortes → 5v2 dominant transformé en 3v2 grindier.
- **A** : trop confiance dans le tag `K!` vs un TermArmour/Psyker (Njal) — un K! tagué a laissé Njal à 970 HP → near-round-cap, aurait dû pré-empiler une 2ᵉ source. (cf. TF04.)
- **B (perdant)** : over-extension T4 (failure-mode dominant récurrent) — Forcas à (4,5) + Guardsmen auto-pathés forward dans la reach r4-5 ennemie T1 → 3 corps focus-killés pour UN Ahriman chunké. Garder Forcas une rangée back (OW fire sans être le focus).
- **B** : K? sur Godswyl avec Yazaghor (low roll laissé à 100 HP) au lieu de séquencer un kill garanti → Njal a dû mop un corps 100-HP le tour suivant (potentiel 6055 K! gaspillé).
- **B** : ligne propre VIOLÉE à répétition — après chaque kill, l'unité tueuse laissée forward (Creed, Asmodai stranded mid-board, Yazaghor) → chacune focus-deletée le tour ennemi suivant. A gagné chaque engine-kill mais JAMAIS rétracté les corps → bleed matériel plus vite que l'adversaire.
- **B** : mal-jugé l'attrition au recon — roster fragile/mêlée vs backbone durable Shiron(Blast carry)+Toth(self-heal/revive anvil) qui out-attritione un reliquum 2-3 units même après avoir gagné la guerre des engines. Aurait dû valoriser la SURVIE des corps sur les kills max une fois clair qu'il ne pouvait pas tuer Toth/Shiron.

### Refs action logs

Action logs complets de CE run archivés dans `logs/selfplay/sp_80004_20260625-b7.json` (action_logs des 2 camps + rosters + outcome team1, rejouable via seed 80004) puis state-files supprimés post-teardown. Séquences décisives résumées ci-dessus.

---

## seed 80002 — winner=team2 (ts=20260625-b7)

> ⚠ **team2 W net par ATTRITION RANGED-ENGINE + STRUCTURAL REACH-FAIL côté team1.** B (team2) a out-tradé via un DOUBLE summon-engine ranged (Sho'syl MV71 drones + Anuphet ResurrectionOrb) screené par un triple-anvil (Azkor Resilient/Terrifying + TG BigTarget + Arjac Resilient/TermArmour), sans jamais exposer son carry fragile. A (team1) avait un roster bricks-mêlée mid-pierce + un Mechanic INERTE, SANS reach-tool (r3+/deep-strike/flyer) pour atteindre Anuphet bloqué row-8 → **engine adverse inatteignable = loss structurelle à flagger au recon** (doctrine H02/H71). `status` autoritatif = **winner=team2 (battleStatus.winner=4, unitsAlive=17)** — board flooded 5v5 → 1v8 → 17 vivants = élimination par les summon-engines, PAS un round-cap.

### Rosters

| Équipe | Unités |
|--------|--------|
| **team1 (Player A / oracle, player 3) — PERDANT** | bloodSanguinary (Nicodemus) · worldTerminator (Wrask) · spaceStormcaller (Njal) · admecManipulus (Actus) · ultraInceptorSgt (Bellator) |
| **team2 (Player B / oracle, player 4) — VAINQUEUR** | worldEightbound (Azkor) · tauMarksman (Sho'syl) · tyranTyrantGuard (Tyrant Guard) · necroOverlord (Anuphet) · spaceRockfist (Arjac) |

### Adjudication

- A outcome_perceived = **L** (5 tours) ; B outcome_perceived = **W** (6 tours) → A="L" & B="W" → **winner_consensus = true** (concorde avec l'autoritatif).
- `rl_duel.py status --state-file data/_sp_80002_A.json` : `stage=Finished currentPlayer=4 alive_by_team={}` + ligne autoritative **« BATTLE FINIE — winner AUTORITATIF = team2 (battleStatus.winner=4, unitsAlive=17) »**. ⚠ `alive_by_team={}` post-Finished est VIDE par construction (decisionView refuse hors-Running) — NE rien inférer de ce vide ; le champ NATIF `battleStatus.winner=4` = vérité (H59). `unitsAlive=17` (5 héros team2 + flood drones MV71/Necron Warriors) = élimination via summon-flood, pas un round-cap (qui aurait `winner=None`).
- **authoritative_winner = team2.**

### Win-conditions (consensus croisé A.mine ≈ B.theirs et A.theirs ≈ B.mine)

**team2 win-condition (VAINQUEUR)** : DOUBLE summon-engine ranged scaling-rounds = Sho'syl (SeekerMissile undodgeable r5 + MV71 drones frappant au Damage stat de Sho'syl depuis tuile safe, max 3) + Anuphet (ResurrectionOrb Necron Warriors scaling chaque round + LivingMetal self-regen), screenés par un triple-anvil (Azkor Resilient/Terrifying/Daemon + TG BigTarget 12.5k + Arjac Resilient/TermArmour) → out-trade ranged sans exposer le carry fragile, le board passe de 5v5 à 1v8 puis 17 vivants. SOURCE = l'output drone de Sho'syl + le flood Necron d'Anuphet, baitant l'ennemi sur les tanks pendant que les ranged farment.
→ Accord A.theirs / B.mine = **CONSENSUS** (A lit correctement Sho'syl + Anuphet comme le double summon-engine, Anuphet row-8 inatteignable, Azkor/TG/Arjac comme le screen).

**team1 win-condition (PERDANT, jamais réalisée)** : summon-snowball (Bellator DeathFromAbove Inceptors) + healer-sustain (Nicodemus BloodChalice/regen) + Psychic armor-bypass (Njal Stormcaller Pierce100 NoBlocking = seul outil contournant Terrifying/TermArmour des bruisers Resilient adverses) ; Actus Mechanic repair-engine INERTE (aucun autre allié Mechanical) = démoté en simple ranged. SOURCE/enablers = Bellator (seul engine board-flip) + Njal (seul vrai dealer). Wincon crippled : ZÉRO reach-tool pour toucher Anuphet row-8 (reach max = Bellator move4-Flying, pas de ligne r3+).
→ Accord A.mine / B.theirs = **CONSENSUS** (B identifie Njal = leur SEUL armor/Terrifying-bypass = le vrai dealer ; Nicodemus + Bellator = les 2 engines à couper ; Actus correctement démoté INERTE).

### Séquences clés (résumé des action logs — détail archivé en 4)

**Player B (team2, VAINQUEUR, 6 tours) :**
- **RECON FLIP corrigé T1** : la vue MOI suit currentPlayer → B a d'abord lu les rosters à l'envers, corrigé sur son 1er tour (il contrôle Azkor/Sho'syl/TG/Anuphet/Arjac). Bonne identification de Sho'syl = SON engine et Njal/Nicodemus/Bellator = le wincon-set ADVERSE (cf. TF03 POV-flip).
- **T4 — open Seeker sur le sustain-engine (Nicodemus)** : Markerlight undodgeable (~5844 chunk, 9035→3191) pré-commit un kill, puis avance cohésive du triple-anvil avec les fragiles (Sho'syl/Anuphet) screenés derrière (round-cap force une décision, pas de turtle).
- **Kill engines en ORDRE de priorité depuis tuiles shallow/ranged (exposition minimale)** : Bellator (stun Foehammer + drone 4079, DÉNIE le summon) → Actus (drones, no deep-dive) → Nicodemus (1 drone 3191) → Njal (THROWAWAY-FIRST-HIT Azkor mange le −75% TermArmour, puis drone Sho'syl tape PLEIN 5252 = kill). Drones (ranged, full-damage) = source de kill sans exposer Sho'syl.
- **Wrask (near-unkillable : shield WrathfulDevotion + TermArmour) sous round-cap** : BURN le shield ~3989 avec le coup throwaway d'Azkor (qui mange AUSSI la réduction first-hit), PUIS finit aux drones full-damage le MÊME tour (2672-4009 chacun) au lieu de chipper dans le shield. Convertit un 9v1 en wipe propre avant le cap.

**Player A (team1, PERDANT, 5 tours) :**
- T1 (sound) : aucune attaque en portée, seule BloodChalice castable (aurait HEAL des alliés full-HP) → avance cohésive mesurée, fragiles screenés. ⚠ A a CASSÉ le deep-strike de Wrask en le « finissant » T1 (le « fin de tour » trigger le reveal LoseEffect TeleportStrike_TeleportingIn → Wrask devenu ciblable) → perte de l'option deep-strike supportée (mais DÉCLENCHE WrathfulDevotion +shield).
- **T2 (PROXIMATE MISTAKE)** : commit Bellator (summon-engine) + Inceptors FORWARD pour drop un écran/chip après le dive ennemi → tombé pile dans le package hard-counter taunt(TG)/stun(Arjac Foehammer)/markerlight(Sho'syl) : Bellator stunné (DeathFromAbove indispo, 1 move) ET markerlighté → neutralisé puis focus-killé ; Inceptors taunt-lockés (Pinned, forced target). Le move-guard (`rl_duel guard --climb`) flaggait baseline-hold NET −4.24 → A aurait dû lire « le commit engine sera puni » et garder Bellator shallow. Perte Bellator + 2 Inceptors pour ~2300 chip = even 5v5 → tempo perdant.
- Late : reconnaît la loss structurelle, switch cohésion défensive + Njal Psychic chip depuis tuiles shallow sur les bruisers Resilient (Azkor chunké 6652→2111 via Njal Pierce100 + Wrask BloodyFury multi-hit, jamais fini car Daemon-block a halvé) + K! un drone avec la dernière action de Wrask. Mais le double summon-engine intouché avait déjà flippé le board.

### CONFRONTATION (consensus vs divergences)

#### Mécaniques de CONSENSUS (rapportées des DEUX sides — cross-observable, recoupées gameconfig)

1. **`TerminatorArmour` throwaway-first-hit = double-spend sur le MÊME corps blindé** : A(theirs, « Foehammer+markerlight chain », observe le profil) + B(mine, high : séquencer un opener faible Azkor mange le −75% → l'attaquant suivant Sho'syl-drone tape PLEIN 5252 = kill Njal ; même levier crack Wrask). gameconfig confirme (`terminatorArmourDmgReduction:-75`, 1ʳᵉ attaque/tour, exclut Psychic/Direct). Déjà au wiki §1 comme doctrine — ce run CONFIRME côté VAINQUEUR appliqué 2× (Njal + Wrask) → n+1. → tac self-play sur Wrask (le corps qui cumule shield+TermArmour à dépenser).
2. **`WrathfulDevotion` shield (Wrask) = BURN-avant-HP** : A(mine, high : finir le deep-striker Wrask a trigger +3989 shield) + B(theirs, high : shield ~3989 TurnsLeft=1 absorbe TOUT le chip — drones 0-166 / TG 0-0 ; le brûler 2818 + first-hit réduction d'Azkor, PUIS drones full 2672-4009 = dead). gameconfig confirme (shield à l'arrivée deep-strike OU kill mêlée, 1 round). Insight non-déductible = NE JAMAIS chipper dans le shield ; le BURN avec un throwaway (qui dépense AUSSI la réduction TermArmour du même corps), puis finir full le MÊME tour. → **INSCRIT wiki §3bis Wrask.**
3. **`MV71SniperDroneSquad` (Sho'syl) = drone frappant au Damage stat de Sho'syl, summon-on-normal** : A(theirs, « markerlighted Nicodemus −5800 puis Bellator ») + B(mine, high : 4079 Bellator / 5310 Actus / 5252 Njal / 3191 Nicodemus depuis tuile shallow, persistent comme écran). gameconfig confirme. (déjà au wiki §3bis Sho'syl — re-confirmé, pas ré-inscrit.)
4. **`SeekerMissileFrequencyLock` (Sho'syl) = mark→fire-au-début-du-prochain-tour, undodgeable** : A(theirs, « one-shot fragiles next turn ») + B(mine, high : marque Nicodemus T4 → ~5844 au start, 9035→3191, indépendant de la position cible ; cast mutated=False déféré mais applique via play --no-ai). gameconfig confirme. (déjà au wiki §3bis Sho'syl — re-confirmé.)
5. **`Foehammer` (Arjac) = Stun qui DÉNIE l'actif d'un engine** : A(theirs, stun+markerlight a neutralisé Bellator → DeathFromAbove indispo, focus-killé) + B(mine, med : Stunned_CantUseAbility a dénié DeathFromAbove à Bellator ; 154 dmg seulement vs MkXGravis, la valeur = le stun ; +2183/Character défait). gameconfig confirme. (déjà au wiki §3bis Arjac — re-confirmé ; le stun-deny-summon réitéré.)
6. **`OverwhelmingWrath` (Azkor) + `CrushingClaws` (TG) = double-taunt qui LOCK un summon forward** : A(theirs, « Taunt + Pin a verrouillé mes 2 Inceptors, forced target, no move/ability ») + B(mine, high : les deux appliquent Taunted_BlockMovement + Taunted_CantUseAbility → ancrent les 2 Inceptors diveurs sur les tanks pendant que je kill les engines). gameconfig confirme (OverwhelmingWrath Taunt adjacents ; CrushingClaws Taunt+push+Suppress). (déjà au wiki §3bis Azkor/TG — confirmation self-play du LOCK d'un summon-screen forward.)
7. **`DeathFromAbove` (Bellator) = Inceptors landent adjacents + attaquent immédiatement, dmg Inceptor INVISIBLE au plan** : A(mine, high : Inceptors chipent Arjac ~2300 à travers TermArmour, dmg PAS dans la prédiction du plan — seul le hit de Bellator s'affiche) + B(theirs, le stun a empêché le flood après T5). gameconfig confirme (« land adjacent to target, attack immediately »). (déjà au wiki §3bis/§3ter Bellator/Inceptor — re-confirmé.)

#### Divergences (entre les deux observateurs)

1. **`DeathFromAbove` compte le ROUND-INTERNE, PAS le tour affiché** : A seul (about=mine, high : à tour affiché 5 / round-interne ~3 → seulement 2 Inceptors, pas 5). B ne cross-observe pas le compteur (il a observé que le STUN a coupé le flood, pas le décompte). Cohérent avec gameconfig (« 1 Inceptor for each round that has started ») + le fait connu que le header `view` « tour N » est figé/non-fiable (TF14/TF03). → `hypotheses.md` (self-play divergence A/B, observateur unique A, recoupé gameconfig = plausible : round-interne ≠ tour affiché).
2. **`Daemon` block (Azkor) a halvé un BloodyFury ET empêché le plancher Resilient de trigger** : A seul (about=theirs, med : Wrask BloodyFury sur Azkor 4222 → exactement 2111 ≈ moitié ; le block Daemon a halvé le hit, total dmg < PV courant → pas de floor Resilient, juste du chip). B ne cross-observe pas. Cohérent gameconfig (Daemon = block chance extra). → `hypotheses.md` (self-play divergence A/B, observateur unique A : budgéter ~2× dmg vs porteurs Daemon-block pour finir).
3. **Issue : aucun désaccord d'issue** (A="L"/B="W" concordent avec le winner autoritatif team2) — pas une divergence.

### Erreurs identifiées (leçons, des deux sides)

- **A (perdant) — ROOT (structural reach-fail)** : roster bricks-mêlée mid-pierce + Mechanic INERTE (Actus) vs un snowball-carry + DOUBLE summon-engine + double-Resilient-anvil, avec Anuphet (ResurrectionOrb) row-8 STRUCTURELLEMENT inatteignable (reach max = Bellator move4-Flying, AUCUNE ligne r3+/deep-strike pour menacer row-8). Per doctrine H02/H71, à FLAGGER au recon comme « engine inatteignable → likely L ». L'engine intouché a flood librement = root cause.
- **A — PROXIMATE** : over-commit du summon-engine (Bellator) + Inceptors forward DANS le package taunt(TG)/stun(Arjac Foehammer)/markerlight(Sho'syl) = exactement le hard-counter aux summons forward. Perdu Bellator + 2 Inceptors tôt pour ~2300 chip = 5v5 even → tempo perdant. Le guard NET −4.24 + « Bellator stunné » aurait dû garder l'engine SHALLOW.
- **A** : n'a PAS priorisé un kill garanti multi-source sur Sho'syl (le summon-engine soft ATTEIGNABLE + source markerlight) tôt, quand ça aurait retiré ET un summoner ET la menace missile — a dépensé son commit summon à chipper un anvil Resilient (Arjac), low value.
- **A** : tempo — roster lent a passé T1-2 à repositionner pendant que les summon-engines adverses compoundaient ; jamais forcé un engine-kill décisif dans la fenêtre, l'attrition (favorisant les summoners) a fait son œuvre.
- **A (mineur)** : a cassé le deep-strike de Wrask en le finissant T1 (revealed early) → perte de l'option d'un deep-strike alpha supporté plus tard.
- **B (vainqueur, notes adversariales malgré la W)** : over-commit de 2 corps low-HP forward — Azkor poussé (5,3)→(3,3) tombé à 2111, fini boxed-in (0 move légal) adjacent à Wrask, survécu SEULEMENT via Resilient + ennemi déjà gutté. Dans un match serré, ce carry stranded = focus-kill ; router Azkor une rangée plus shallow après chaque engine-kill.
- **B** : activations extra pour finir Actus (engine quasi-inerte, low-value) — a exposé Sho'syl forward (3,5) + dive Arjac (2,3) ; payoff stratégique faible vs le risque de positionnement (acceptable seulement parce que déjà 7v5 up).
- **B** : mal-timé la peur round-cap tôt (header `tour` figé à « tour 4 » 6 tours durant, TF14) → a failli pousser vers des deep-dives prématurés. Tracker SON propre compte de tours joués, pas le header.

### Refs action logs

Action logs complets de CE run archivés dans `logs/selfplay/sp_80002_20260625-b7.json` (action_logs des 2 camps + rosters + outcome team2, rejouable via seed 80002) puis state-files supprimés post-teardown. Séquences décisives résumées ci-dessus.

---

## seed 80001 — winner=team1 (ts=20260625-b7)

> ⚠ **team1 W par SUMMON-ENGINE BOARD-FLIP (Archimatos Incursion) ressuscitant un combat PERDU 2v3.** A (team1) a été grindé à 2v3 (les 2 anvils Resilient focus-killés en se poussant forward vs un ennemi all-ranged out-rangeant), PUIS un seul cast `Incursion` sur le carry Resilient Abaddon a chain-killé Abaddon ET flood 5 Bloodletters = flip 2v3 → 7v2 = la W. La défaite de B = **kill-not-chip violé sur un summon-engine** (H02) : B a laissé Archimatos à 909 HP au lieu de le tuer, ET a poussé son meilleur anvil Abaddon forward à (3,3) pour le chip non-létal → le flood l'a one-shot. `status` autoritatif = **winner=team1 (battleStatus.winner=3, unitsAlive=18)** — élimination par le flood Bloodletter, pas un round-cap (qui aurait `winner=None`).

### Rosters

| Équipe | Unités |
|--------|--------|
| **team1 (Player A / oracle, player 3) — VAINQUEUR** | ultraTigurius (Tigurius) · blackPossession (Archimatos) · astraOrdnance (Thaddeus, MoW) · deathBlightlord (Maladus) · custoTrajann (Trajann) |
| **team2 (Player B / oracle, player 4) — PERDANT** | ultraEliminatorSgt (Certus) · astraOrdnance (Thaddeus, MoW) · blackAbaddon (Abaddon) · admecManipulus (Actus) · thousInfernalMaster (Abraxas) |

### Adjudication

- A outcome_perceived = **W** (7 tours) ; B outcome_perceived = **L** (7 tours) → A="W" & B="L" → **winner_consensus = true** (concorde avec l'autoritatif).
- `rl_duel.py status --state-file data/_sp_80001_A.json` : `stage=Finished currentPlayer=3 alive_by_team={}` + ligne autoritative **« BATTLE FINIE — winner AUTORITATIF = team1 (battleStatus.winner=3, unitsAlive=18) »**. ⚠ `alive_by_team={}` post-Finished est VIDE par construction (decisionView refuse hors-Running) — NE rien inférer de ce vide ; le champ NATIF `battleStatus.winner=3` = vérité (H59). `unitsAlive=18` (héros team1 survivants + 5 Bloodletters d'Incursion) = élimination par le summon-flood, pas un round-cap (`winner=None`).
- **authoritative_winner = team1.**

### Win-conditions (consensus croisé A.mine ≈ B.theirs et A.theirs ≈ B.mine)

**team1 win-condition (VAINQUEUR)** : Archimatos `Incursion`/`Possession` summon-engine (un cast chain-kill le carry Resilient Abaddon ET flood 5 Bloodletters = board-flip de 2v3-perdant à 7v2-gagnant — le game-winner), ENABLÉ par Thaddeus-MoW `BasiliskBarrage` (artillery board-wide Blast, anti-turtle vs un ennemi all-ranged inatteignable — tue Abraxas le summon-engine adverse AVANT son cast) + Tigurius `StormOfWrath` (Psychic NoBlocking armor-bypass AoE — tue 2 Blue Horrors en splash + chunke le carry Resilient).
→ Accord A.mine / B.theirs = **CONSENSUS** (B identifie Archimatos Incursion/Possession comme la SOURCE board-flip qui a gagné, Tigurius comme engine Psychic secondaire).

**team2 win-condition (PERDANT, jamais convertie)** : Abraxas `MasterOfTheTutelaries` summon-engine (Pink Horror/Screamer cascade sur dégât Psychic) comme board-flood + Abaddon carry (`FirstAmongTraitors` +364 Chaos-buff aura), screenés par un turtle all-ranged (Certus Overwatch r3 + dual astraOrdnance MoW barrage) qui a gagné l'attrition ranged. Engine jamais compoundé — Abraxas tué par le barrage AVANT son cascade.
→ Accord A.theirs / B.mine = **CONSENSUS** (A lit le turtle all-ranged + le double summon-engine ; B reconnaît avoir gagné l'attrition mais perdu sur le board-flip).

### Séquences clés (résumé des action logs — détail archivé en 4)

**Player A (team1, VAINQUEUR, 7 tours) :**
- **Opener anti-turtle** : `BasiliskBarrage` board-wide chaque fois qu'off-cooldown sur la grappe ennemie serrée — l'outil correct vs un ennemi all-ranged inatteignable (ne demande pas de closer). A killé Abraxas (le summon-engine soft 4848) au moment décisif AVANT tout cascade Screamer = must-kill SOURCE retiré.
- Maladus `FlailSwing` + aura `ContagionsOfNurgle` (−armure) → one-shot Actus (repair-engine INERTE, correctement démoté au recon : seul Mechanical = lui-même).
- **MISTAKE — push des Resilient forward** : Trajann (anvil self-heal + LegendaryCommander) over-étendu à (4,5) pour tuer un chaff Pink Horror (qui a SPLIT en 2 Blue Horrors anyway) → focus-killé par l'ennemi all-ranged. Maladus + Tigurius aussi perdus à l'exposition forward → chute à **2v3**.
- **WIN — board-flip Incursion** : à 2v3 (2 survivants HP critiques), `Incursion` sur Abaddon (Resilient carry) depuis une tuile NON-mouvante → la chain Bloodletter a tué Abaddon ET laissé 5 Bloodletters (3888 HP each) = flip 2v3 → 7v2 = salvage d'un combat perdu sur l'attrition.
- Préservation : Thaddeus (75 HP) tiré en coin danger-0 (0,0) pour préserver le board-wide weapon → a délivré le barrage Abraxas-killing 2 tours plus tard.

**Player B (team2, PERDANT, 7 tours) :**
- T1 : `BasiliskBarrage` sur le cluster engine-corner ennemi (Tigurius/Archimatos/Thaddeus stackés) — crush le mirror artillery 6525→75 + suppressed + chunk Archimatos. Strongest opener vs cluster serré.
- Mid : hold cohésif (anvils Resilient Abaddon/Actus forward, fragiles shallow) ; punit le dive des anvils ennemis (Trajann focus-killé par 2 Blue Horrors + Abraxas depuis tuiles courantes, zéro exposition ; Maladus grindé sur 2 tours en menant par un weak-hit burn-TermArmour).
- Late : Tigurius avancé en portée → focus-kill propre (no-Resilient) au Thaddeus one-shot. Atteint **6v2**.
- **FATAL** : a chunké Archimatos (summon-engine) à 909 au lieu de le KILLER, ET a poussé l'anvil durable Abaddon forward à (3,3) pour le faire → Archimatos a casté `Incursion` → 5 Bloodletters one-shot Abaddon → board flip 6v2 → 2v7 → loss. La normale max d'Abaddon (5425) < HP d'Archimatos (6801) → AUCUN kill dispo ce tour-là → n'aurait JAMAIS dû committer Abaddon (H02 : kill garanti CE tour ou HOLD total).

### CONFRONTATION (consensus vs divergences)

#### Mécaniques de CONSENSUS (rapportées des DEUX sides — cross-observable, recoupées gameconfig)

1. **`Incursion` (Archimatos) = chain-kill + board-flood en UN cast** : A(mine, high : un cast tue le Resilient Abaddon ET laisse 5 Bloodletters permanents = flip 2v3 → 7v2) + B(theirs, high : 5 Bloodletters 3888/1601 immediate-attack one-shot mon Abaddon forward + finissent mes 2 derniers = ce qui a gagné). gameconfig confirme verbatim (« Keeps summoning Bloodletters up to a max of 6, as long as the target has not been defeated, is in range and has a free hex adjacent »). → INSIGHT cross-confirmé : la prédiction de dmg du plan SOUS-LIT massivement la chain (le board-value ≈ 17k de corps, pas le ~2572-3860 affiché). (déjà au wiki §2 Archimatos — re-confirmé self-play ; nouveau tac ajouté.)
2. **kill-not-chip sur un summon-engine (Archimatos)** : A(mine, a GAGNÉ via le board-flip en tant que propriétaire) + B(theirs/ROOT-CAUSE, a PERDU en laissant Archimatos à 909 → Incursion flood). Les DEUX sides confirment la doctrine depuis des perspectives opposées (owner-W vs victim-L) sur le MÊME match. (déjà au wiki §2 Archimatos « NE JAMAIS CHIPER NON-LÉTALEMENT » — re-confirmé n+1 self-play ; nouveau tac ajouté.)
3. **`BasiliskBarrage` (Thaddeus MoW) = anti-turtle board-wide, one-shot un soft engine clusteré, ≪ vs TerminatorArmour** : A(mine, high : concentrer le centre sur Abraxas 4848 soft = one-shot ; Blast réduit −315 seulement sur Abaddon TermArmour) + B(mine, high : T1 crush le mirror 6525→75 + suppress + chunk Archimatos). gameconfig confirme (Blast Pierce15 HitsMultipleMembers, scatter, +1 obus/round). (déjà au wiki §3bis Thaddeus move-gate/scatter/≪-armure — re-confirmé self-play.)
4. **`StormOfWrath` (Tigurius) = Psychic Pierce100 NoBlocking, bypass TermArmour total + AoE splash** : A(mine, high : bypasse la TermArmour d'Abaddon plein + one-shot 2 Blue Horrors adjacents en splash en un cast ; mon Psychic sur LEURS units ne trigger PAS leur Abraxas WeaverOfFate — celui-ci key sur MES units prenant du Psychic) + B(theirs, roster « StormOfWrath Psychic AoE NoBlocking ignore mon armure »). gameconfig confirme. (déjà au wiki §1/§3bis — re-confirmé.)
5. **`TerminatorArmour` first-attack −75% (Psychic/Direct exclus) ; throwaway-burn n'aide QUE même-tour** : A(mine, Blast réduit sur Abaddon TermArmour) + B(theirs/mine, high : mon lead weak physical sur Maladus lourdement réduit (Abaddon 255-345 chip), Abraxas Psychic plein ~2.6-3.3k ; la réduction RESET chaque tour → burn-then-finish même tour). gameconfig confirme (`terminatorArmourDmgReduction:-75`, exclut Psychic,DirectDamage). (déjà au wiki §1 — re-confirmé.)
6. **`Resilient` vs ranged massé = NE survit PAS** : A(mine, high : mes 2 anvils Resilient Trajann/Maladus focus-KILLÉS poussés forward vs l'ennemi all-ranged — multi-hit grind past Resilient, 1 HP → next hit kills) + B(theirs, high : Trajann tué par multi-hit séquentiel SANS overkill explicite — cumul de 3 ranged → final hit WasOverkill=1 member-kill = floor-then-finish). gameconfig confirme (`Resilient` = 1 HP sauf Overkill). (déjà au wiki §1 + TF04 — re-confirmé n+1 self-play des 2 sides.)
7. **`MasterOfTheTutelaries` / Pink Horror Split-on-death = killer un Pink Horror donne PLUS de corps (2 Blue Horrors)** : A(mine, high : tuer le Pink Horror 3589 l'a SPLIT en 2 Blue Horrors 2093 each → mieux d'AoE le pack ou tuer la SOURCE Abraxas que chasser les Horrors individuels) + B(theirs, summon-screen). gameconfig confirme `Split {unitId:thousSmnBlueHorror}` (« summons 2 Blue Horrors… Does not apply if Overkilled »). (déjà au wiki §3ter Pink Horror `Split` [self-play consensus, seed 80097] — re-confirmé n+1.)
8. **`DefendTheDivineWork`/Mechanic (Actus) = repair-engine INERTE (seul bénéficiaire = lui-même)** : A(mine, high : démoté au recon, seul Mechanical sur son équipe = self-regen only → killé cheap en 1er) + B(mine, high : AUCUNE cible chaque tour, no-op all game). gameconfig confirme (« Repairs himself and all friendly adjacent units » + Mechanical-only repair). → DOCTRINE engine-inerte-at-recon : compter les bénéficiaires valides AVANT de craindre un repair/amplify engine. (déjà au wiki §3bis Actus — re-confirmé self-play des 2 sides.)

#### Divergences (entre les deux observateurs)

1. **`SuppressiveFire`/Suppressed (BasiliskBarrage) bloque la propre ability de la cible (mirror MoW pinned all game)** : B SEUL (about=mine, high : son T1 barrage a suppress le Thaddeus mirror 6525→75 ET « stayed pinned at 75 the whole game, never fired its barrage again » → Suppressed = blocage de la barrage adverse, pas qu'un malus dmg/move). A ne cross-observe PAS ce blocage (les 2 MoW étaient sur des camps opposés ; A possédait son propre Thaddeus). gameconfig : `SuppressiveFire` confirme « enemy hit becomes Suppressed » MAIS le `Suppressed` effect est moteur-only (pas de sémantique i2 sur le blocage d'ability) → la RÈGLE (suppress applique) est confirmée, l'EFFET (Suppressed bloque l'activation barrage) est single-observer non-recoupable. → `hypotheses.md` (self-play divergence A/B, observateur unique B, recoupé partiellement : suppress-applies=confirmé, blocks-own-barrage=plausible non-confirmable via gameconfig).
2. **Mécanisme de mort de mes anvils (perspective)** : A décrit ses propres Trajann/Maladus focus-killés en se poussant forward ; B décrit les MÊMES kills depuis sa perspective (Trajann par 2 Blue Horrors + Abraxas depuis tuiles courantes ; Maladus grindé sur 2 tours via burn-TermArmour). Accord causal complet (multi-hit ranged bat Resilient) — divergence d'INFORMATION (chaque side voit sa moitié), PAS de fait. Pas une H.
3. **Issue : aucun désaccord d'issue** (A="W"/B="L" concordent avec le winner autoritatif team1) — pas une divergence.

### Erreurs identifiées (leçons, des deux sides)

- **B (perdant) — ROOT CAUSE (H02 violé)** : kill-not-chip violé sur un summon-engine. Laissé Archimatos vivant à 909 (un poke non-létal) → Incursion-flood 5 Bloodletters one-shot l'Abaddon forward, flip dominant 6v2 → 2v7. La normale max d'Abaddon (5425) < HP Archimatos (6801) → AUCUN kill dispo ce tour → n'aurait PAS dû committer Abaddon du tout, le garder en screen, attendre un kill multi-source garanti.
- **B — over-extension** : poussé son meilleur anvil survivant (Abaddon) deep à (3,3) adjacent au summoner pour un chip non-létal → atterri pile dans la tuile où le flood pouvait le focus. Compose l'erreur H02 avec le failure-mode dominant d'over-extension.
- **B** : a brûlé la valeur summon-engine (Abraxas) en grindant le mur Maladus au lieu de la préserver (corps expendables OK, mais Abraxas est un engine).
- **A (vainqueur, notes malgré la W)** : over-extension de Trajann (Resilient self-heal anvil + LegendaryCommander) à (4,5) pour tuer un chaff Pink Horror (qui a SPLIT anyway) → focus-killé. A tradé sa pièce durable la PLUS précieuse pour de la valeur NÉGATIVE — failure-mode dominant : ne JAMAIS pousser un corps Resilient précieux dans le focus all-ranged pour du chaff (Resilient ne survit PAS au multi-hit massé).
- **A** : a perdu Maladus + Tigurius à l'exposition forward aussi — vs un ennemi all-ranged qui out-range, CHAQUE corps forward (même les tanks) se fait grind ; aurait dû s'appuyer plus dur sur l'attrition barrage + tenir fragiles/tanks en cluster arrière serré au lieu de feeder un par un (chute à 2v3 avant le salvage Incursion).
- **A** : mis-lu la dispo de `BasiliskBarrage` 2 tours (a traité le « [indispo] » comme un hard cooldown et tenu passivement) alors que les outils abilities/reason le disaient castable → tempo perdu (cf. TF22/friction).

### Refs action logs

Action logs complets de CE run archivés dans `logs/selfplay/sp_80001_20260625-b7.json` (action_logs des 2 camps + rosters + outcome team1, rejouable via seed 80001) puis state-files supprimés post-teardown. Séquences décisives résumées ci-dessus.

---

## seed 80053 — winner=team2 (ts=b8)

> Run self-play oracle-vs-oracle, seed 80053. **team2 (Space Wolves/Khorne/Ultramarines/T'au/AdMech) bat team1 (Blood Angels/Necron/AdMech)** par un alpha **3-kills en UN tour** (T4), amplifié par WarHowl, collapsant un 5v5 -> 5v2. team1 (Blood Angels) avait un wincon structurellement valide (double Psychic NoBlocking anti-armure + Blast AoE + deep-strike) mais l'a perdu par **over-extension** (la mistake dominante des DEUX sides). NB : seed 80053 a un precedent run team1-W (cf. wiki §3bis Ragnar FJ tag « seed 80053 W ») — CE run = team2-W, trajectoire/issue distinctes.

### Rosters

| Equipe | Unites |
|--------|--------|
| **team1 (Player A / oracle, player 3) — PERDANT** | bloodMephiston (Mephiston) · bloodDante (Dante) · necroWarden (Makhotep) · adeptMorvenn (Morvenn Vahl) · spaceStormcaller (Njal) |
| **team2 (Player B / oracle, player 4) — VAINQUEUR** | spaceBlackmane (Ragnar) · worldKharn (Kharn) · ultraCalgar (Calgar) · tauDarkstrider (Darkstrider) · admecManipulus (Actus) |

### Adjudication

- **SOURCE AUTORITATIVE** `rl_duel.py status --state-file data/_sp_80053_A.json` : `*** BATTLE FINIE — winner AUTORITATIF = team2 (battleStatus.winner=4, unitsAlive=10) ***`. (alive_by_team={} post-Finished = decisionView refuse hors-Running, NON probant — c'est le champ natif `battleStatus.winner=4` qui tranche, H59.)
- A outcome_perceived = **L** ; B outcome_perceived = **W** -> **winner_consensus = true** (A="L" & B="W" -> team2, ET ca MATCHE le winner autoritatif team2).
- **authoritative_winner = team2.**

### Win-conditions (consensus croise A.theirs ~ B.mine et A.mine ~ B.theirs)

**team2 win-condition (VAINQUEUR)** : alpha melee-burst amplifie par stacking d'enablers de buff — **Kharn KillMaimBurn** (~7.5k multi-hit r2, snowball via BlessingsOfKhorne par kill melee + TheBetrayer free-chain) + **Ragnar charge** (Saga +hits), les MULTIPLICATEURS-source etant **WarHowl** de Ragnar (+1164 dmg/melee + crit + Unstoppable, ne finit PAS le tour) et **RitesOfBattle** aura de Calgar. **WarHowl = la keystone** : a converti le coup de Ragnar sur Njal de K? en K! GARANTI -> a permis un tour-3-kills au lieu de 2.
-> Accord A.theirs / B.mine = **CONSENSUS** (A a correctement identifie Ragnar WarHowl comme la SOURCE-amplificateur, Kharn comme le snowball-killer, et flagge Actus repair-engine comme INERT (seul Mechanical sur son equipe) + Darkstrider markerlight-engine comme near-self-fed).

**team1 win-condition (PERDANT, jamais realisee)** : triple Psychic NoBlocking (Mephiston FuryOfTheAncients heal-block + Njal Stormcaller — bypass Calgar MkXGravis armure & neutralise Actus repair) + Morvenn Blast AoE + Dante deep-strike charge carry. Enabler a proteger = Mephiston (engine anti-armure + heal-block).
-> Accord A.mine / B.theirs = **CONSENSUS** (B a lu team1 comme un charge-synergy Blood Angels pilote par Dante LordOfTheHost aura + 2 Psyker-carries anti-armure ; B l'a cut en tuant les carries avant convergence).

### Sequences cles (resume des action logs)

**Player A (team1, perdant) :**
- Recon SOLIDE : Ragnar=engine WarHowl SOURCE, Kharn=snowball-killer, Actus repair-engine flagge INERT, Darkstrider markerlight near-self-fed -> kill-priority Ragnar > Kharn, demote Actus/Darkstrider. Cette partie etait juste.
- Dante garde en deep-strike reserve (untargetable) T3-T4 (correct — never solo-deep-strike) -> K! propre sur Darkstrider (3822) une fois l'ennemi committe.
- T4 : SanctorumMissile sur le cluster ennemi (~10.5k spread : Darkstrider -3708, Kharn -2198, Actus -4184 ; hit direct sur Ragnar BLOQUE a 0 par BeastSlayer block). High-value MAIS a laisse Morvenn forward (4,2) + Makhotep (3,3) + Njal (2,2) dans la reach des bursters melee.
- T5 : focus-kill de Ragnar (Mephiston + Fury) + Darkstrider (Dante K!) = 2 kills — mais damage-control sur un board deja perdu (3 units deja mortes), Mephiston a mange ~6631 (FJ Ragnar + cluster move-counters) pour finir l'engine point-blank.

**Player B (team2, vainqueur) :**
- T2 (1er) : avance cohesive rows 5-6 pour casser le double-turtle (round-cap force l'engagement) ; accepte une volee gratuite (~15k spread, surtout sur les supports fragiles Darkstrider/Actus) comme prix d'entree en strike range pour T4.
- T4 : **WarHowl FIRST** (ne finit pas le tour) -> upgrade le coup sur Njal en K! garanti -> **alpha 3-kills** : Kharn->Makhotep, Ragnar->Njal K!, Darkstrider+Actus->Morvenn. 5v5 -> 5v2 en un tour.
- TheBetrayer free-chain : apres le kill de Makhotep, auto-2e-attaque ~1142 sur Njal adjacent ; apres le kill de Mephiston, chain ~2819 sur Dante adjacent (4892->2073) gratis.
- Morvenn et Dante finis depuis tuiles NON-adjacentes/range pour esquiver Explodes (Actus a distance 2 = 0 dmg explosion) et minimiser l'exposition FinalJustice.

### Confrontation : consensus vs divergences

#### Mecaniques de CONSENSUS (rapportees des DEUX sides — cross-observable, recoupees gameconfig)

1. **WarHowl (Ragnar)** : self-buff +1164 dmg + ~36% crit sur la melee normale + Unstoppable, **ne finit PAS le tour** (cast d'abord, puis move+attack). A converti le coup de Ragnar sur Njal de K? en K! GARANTI = la diff entre un alpha 2-kills et 3-kills. A(theirs, « SOURCE buff-engine amplifiant Kharn/Calgar ») + B(mine, « la keystone, K?->K! »). gameconfig verbatim confirme. -> **INSCRIT wiki §5bis** (keystone d'alpha 3-kills, cross-confirme 2 sides).
2. **KillMaimBurn + TheBetrayer (Kharn)** : KillMaimBurn ~7.5k multi-hit (Pierce adjacent -> 6x Eviscerate meme cible -> Plasma r2) ; apres un kill melee, TheBetrayer auto-2e-attaque chain ~1142 sur Njal puis ~2819 sur Dante adjacents (GRATIS). BlessingsOfKhorne snowball par kill. A(theirs, « ~10k 8-hit burst, snowball + Betrayer counter ») + B(mine, « overkill Makhotep + chain free »). gameconfig confirme. (deja au wiki §2 — pas re-inscrit.)
3. **MkXGravis (Calgar)** : dmg entrant repasse par l'armure une 2e fois, **seul le Crit bypasse**. Power/Bolter/Blast de A ont fait ~400-430 sur Calgar (lourdement reduit) ; seul le Psychic NoBlocking de A pouvait le damage. A(theirs, threat high « double-armor, Crit-only bypass ») + B(mine, « Calgar MkXGravis anvil bypasse seulement par les Psyker »). gameconfig confirme. (deja au wiki §3 — pas re-inscrit.)
4. **FuryOfTheAncients / heal-block (Mephiston)** : actif move-triggered, 2x Psychic NoBlocking (cible + 1 adjacent) + heal-block 2 rounds (cible ne peut etre revive/heal/repair). Applique un heal-block sur Calgar. A(mine, « finit Ragnar ce match ») + B(theirs, « heal-block sur mon Calgar, Psychic bypasse MkXGravis »). gameconfig verbatim. (deja au wiki §3bis — pas re-inscrit.)
5. **Explodes (Morvenn)** : explose a la mort = 25% maxHP Direct aux adjacents (friendly-fire des DEUX cotes). A(mine, « chunke Ragnar ~2385, friendly-fire risk ») + B(theirs, « Ragnar a mange ~2385 car adjacent ; Actus l'a finie a distance 2 = 0 dmg explosion »). gameconfig confirme (radius = adjacent uniquement ; kill au range = 0). (deja au wiki §1 — pas re-inscrit, B re-confirme « kill au range non-adjacent = 0 explosion ».)
6. **FinalJustice (Ragnar + Dante)** : a la mort (sauf Overkill), 1 attaque normale riposte. Ragnar tue non-overkill a fire une normale dans Mephiston (~995) ; Dante (dernier ennemi) a fire 727+836 sur Kharn adjacent meme tue. A(theirs, Ragnar FJ ~995 + move-counters -> Mephiston 9537->2906) + B(theirs, Dante FJ confirme « fire sur une mort non-overkill »). gameconfig confirme. -> **lecon FJ-chunks-full-HP-carry DEJA au wiki §3bis Ragnar (tag seed 80053)** ; re-confirmee.
7. **BeastSlayer block (Ragnar)** : a bloque les hits directs de SanctorumMissile entierement (Amount=0, DidBlock=1). A(mine, « missile bloque a 0 »). Cross-coherent avec la nuance block deja au wiki §3bis Tanksmasha (BeastSlayer = clause de block). (candidate single-side cote Ragnar, mais coherent avec la regle existante.)

#### Divergences (entre les deux observateurs)

**AUCUNE divergence mecanique ni d'issue ce run.** Les deux observateurs s'accordent sur le vainqueur (team2), sur toutes les mecaniques cross-observees (WarHowl, Kharn burst+Betrayer, MkXGravis, Fury/heal-block, Explodes, FinalJustice), et sur le failure-mode dominant de team1 (over-extension). Consensus exceptionnellement propre — recoupage gameconfig confirme chaque mecanique.

### Erreurs identifiees (lecons, des deux sides)

- **A (perdant) — ROOT CAUSE (over-extension, failure-mode dominant)** : a avance toute sa ligne 5-units en rows 2-4 (T3-4) DANS la reach de TROIS bursters melee (Kharn ~10k, Ragnar 7-hit, Calgar) et laisse les fragiles (Morvenn 4,2 ; Makhotep 3,3 ; Njal 2,2) exposes -> focus-kill de 3 units en UN tour ennemi (5v5 -> 2v5). A presente des cibles isolees atteignables a une compo focus-fire — exactement ce que la doctrine interdit.
- **A** : aurait du tenir les fragiles SHALLOW (rows 0-1, screenes par Morvenn BigTarget) et laisser l'ennemi se rapprocher dans une kill-box, puis alpha avec Dante deep-strike + tout le ranged simultanement — au lieu de dribbler du chip en expose.
- **A** : T5 Mephiston bouge ADJACENT au cluster pour tuer Ragnar -> ~6631 de FJ + move-counters ; tuer un FJ-engine point-blank avec son carry = trop cher. Mais a ce stade plus d'unite expendable.
- **A** : mis-lu la pression round-cap comme « must engage early » -> avance agressive, alors que la bonne lecture = « engager decisivement depuis une position SUPPORTEE et shallow ». L'horloge ne justifie pas de feeder des fragiles dans la reach melee.
- **B (vainqueur)** : avance T2 a pousse les supports fragiles (Darkstrider 3822, Actus 5353 post-volee) au front de l'arc de tir ennemi -> ont absorbe toute la volee ; les garder une rangee plus en arriere (derriere les anvils FJ) aurait preserve plus de PV (Darkstrider partiellement perdu a cause de cette sur-exposition early).
- **B** : a laisse Ragnar a (3,3) adjacent a Morvenn quand Actus l'a finie -> Ragnar a mange ~2385 Explodes (6765->4380) -> sa moindre HP a contribue a son focus-kill au tour ennemi ; une formation plus propre aurait sorti la melee de l'adjacence de Morvenn avant sa mort.
- **B** : a committe Ragnar ET le fragile Darkstrider profond en rows 3-4 T4 ; les deux sont morts au tour ennemi. Le trade 3-pour-2 etait clairement gagnant (5v2), mais une formation plus serree (mener avec Calgar/Kharn tanky, garder Darkstrider ranged plus en arriere) aurait pu fermer en perdant 0-1 unite au lieu de 2.

### Refs action logs

Action logs complets de CE run archives dans `logs/selfplay/sp_80053_b8.json` (action_logs des 2 camps + rosters + outcome team2, rejouable via seed 80053) puis state-files supprimes post-teardown. Sequences decisives (WarHowl-first -> alpha 3-kills T4) resumees ci-dessus.

---

## seed 80031 — winner=team2 (ts=b8)

### Rosters

| Équipe | Unités |
|--------|--------|
| **team1 (Player A / oracle, player 3) — PERDANT** | thousTerminator (Toth) · spaceWulfen (Ulf) · custoBladeChampion (Kariyan) · orksKillaKan (Snappawrecka) · admecDestroyer (Sy-gex) |
| **team2 (Player B / oracle, player 4) — VAINQUEUR** | emperNoiseMarine (Shiron) · genesBiophagus (Hollan) · tauMarksman (Sho'syl) · worldExecutions (Tarvakh) · admecManipulus (Actus) |

### Adjudication

- A outcome_perceived = **L** ; B outcome_perceived = **W** → **winner_consensus = true** (A="L" & B="W" → team2).
- `rl_duel.py status --state-file data/_sp_80031_A.json` : `*** BATTLE FINIE — winner AUTORITATIF = team2 (battleStatus.winner=4, unitsAlive=15) ***` (champ natif, lisible post-Finished — H59 ; `alive_by_team={}` VIDE = normal post-Running, NON un draw).
- **authoritative_winner = team2.** Issue formelle confirmée par le champ winner natif ET les deux narratifs (B a fini avec ses engines + carry intacts ; A a perdu son seul peel out-trade Sy-gex puis s'est fait out-focus).

### Win-conditions (consensus croisé A.theirs ≈ B.mine et A.mine ≈ B.theirs)

**team2 win-condition (VAINQUEUR)** : DOUBLE moteur sustain/summon. SOURCE = genesBiophagus (Hollan) — Healer + TwistedScience (pump permanent +PV/+maxHP des alliés healés, summons inclus) + AberrantHypermorph summon (corps-écran 7477 PV) + Ambush revive ; amplifié par admecManipulus (Actus) — Mechanic repair + GalvanicField (réparé fait une attaque gratuite immédiate). Pression avant = worldExecutions (Tarvakh) BlessingsOfKhorne snowball mêlée + MurderousSwing AoE, ET surtout tauMarksman (Sho'syl) SeekerMissile delayed-nuke qui a chunké le seul peel out-trade adverse (Sy-gex) 9537->274 pour zéro exposition.
→ Accord A.theirs / B.mine = **CONSENSUS** (A a correctement identifié Hollan+Actus comme les engines à cut + Sho'syl/Tarvakh comme la pression avant ; B s'auto-lit pareil, en notant que SES amplifiers Hollan/Actus furent largement INERTES — Actus sans 2e Mechanical à galvaniser, TwistedScience jamais castée safely — et qu'il a gagné sur le TEMPO ranged + les corps-summons jetables, pas sur le sustain).

**team1 win-condition (PERDANT, jamais réalisée)** : durable-brick attrition. SOURCE = les 2 ranged out-trade (Snappawrecka DakkaDakka r3 + Sy-gex HeavyGravCannon r3 bonus vs leurs Mechanicals) + Kariyan anti-summon MartialKatah, front-line Resilient/revive (Kariyan + Toth) absorbant le focus. FAILLE = ZÉRO team-sustain : une fois Sy-gex (le seul ranged qui out-trade ET le seul peel anti-engine) mort au Seeker, les bricks n'avaient plus de peel et se sont fait out-focus par un roster qui out-sustain.
→ Accord A.mine / B.theirs = **CONSENSUS** (B a correctement lu le mur durable ancré sur l'UNIQUE reaction-engine Sy-gex Overwatch + HeavyGravCannon, sans 2e Mechanical bénéficiaire — et a ciblé Sy-gex EN PREMIER via le Seeker).

### Séquences clés (résumé des action logs — détail archivé dans logs/selfplay/sp_80031_b8.json)

**Player B (team2, VAINQUEUR) :**
- T1 : Sho'syl SeekerMissile markerlight sur le turret Overwatch Sy-gex depuis une tuile écranée + summon Aberrant (corps-écran 7477 gratuit). Le Seeker landa pour un chunk massif (Sy-gex 9537->274) = neutralise le SEUL reaction-engine adverse pour zéro coût héros, setup d'un kill cheap. **Meilleur play du match.**
- T3 : tué le Sy-gex à 274 avec un corps DURABLE Flying low-value (Actus, amplifier inerte) au lieu d'un héros + chip Snappawrecka avec l'Aberrant EXPENDABLE ; puis Actus FINIT Snappawrecka depuis une tuile telle que son Explodes (2259 Direct) frappe LEUR Ulf + Kariyan, pas les siens (free 2-target chip sur team1).
- T5-6 : Tarvakh MurderousSwing dans le cluster → floor Resilient Kariyan à 1 + chunk Ulf à 475 en un AoE ; puis kill Ulf par OVERKILL via un hit drone ranged (FinalJustice nié, WasOverkill=1), puis Kariyan(1) et Toth finis au range. A utilisé l'horloge round-cap pour forcer l'engagement proactif plutôt qu'un double-turtle.

**Player A (team1, PERDANT) :**
- R3 : avance cohésive flanc-gauche danger<=2 + Sy-gex sur Overwatch (départ sain, zéro cible isolée) ; anti-bait HOLD quand B a avancé Tarvakh+Tau en bait (correct en principe) — MAIS a laissé Sy-gex passivement DANS la portée Seeker, fatal.
- Focus-kill de l'Aberrant à 2 ranged (Snappawrecka+Sy-gex) au lieu de diver Kariyan profond (carry safe) ; 1re kill exact-HP = resurrection Ambush, 2e kill = overkill permanent.
- R5 conversion désespérée : tué Hollan (Ulf 475 via FinalJustice) + Actus + Drone en un tour en dépensant ses units mourantes (Kariyan 1HP sur le Drone) — valeur max extraite de corps condamnés, engines égalisés mais TROP TARD.

### Confrontation : consensus vs divergences

#### Mécaniques de CONSENSUS (rapportées des DEUX sides — cross-observable, recoupées gameconfig/i2)

1. **SeekerMissileFrequencyLock (Sho'syl)** : Markerlight T → missile fire au DÉBUT du prochain tour de Sho'syl s'il survit ; **undodgeable** (homing, pas de falloff par-hex), annulable SEULEMENT en tuant le caster avant le tir. A(theirs, 9263 sur Sy-gex 9537->274) + B(mine, ~9k chunk sur le turret). gameconfig verbatim (« At the beginning of Sho'syl's next turn, if he is still in play, the target is hit »). NB : le 9263 réel >> nominal 5456-6184 = amplifié RangedSpecialist/HeavyWeapon (numérique/match-spécifique → JOURNAL, pas wiki ; déjà au wiki §3bis « kill garanti undodgeable »). → friction outil TF28 (pas de magnitude incoming surfacée).
2. **TimeFlux (Toth)** : revive 1x/battle GATÉ sur la présence d'un time-ghost (créé en bougeant). A(mine, revive @2401 via ghost) + B(theirs, « Toth never moved enough to leave a usable ghost → no revive fired → permanent kill from full »). gameconfig verbatim (« if his time ghost is on the battlefield then he revives »). → **INSCRIT wiki §1** (inverse actionnable : Toth immobile = pas de ghost = kill permanent sans 2e source).
3. **FinalJustice (Ulf)** : death-riposte (1 normale à la mort) NIÉE par OVERKILL (>2x PV restants). A(mine, fire même stunned/AoE sauf OVERKILL) + B(theirs, drone overkill sur Ulf 475 → IsActingBeforeDeath=0, pas de riposte). gameconfig verbatim (« unless Overkilled »). (déjà au wiki §1, n>1.)
4. **SavageKiller (Ulf)** : réaction 5-hit Power AVANT l'ability de l'ennemi, sur (a) summon move/spawn adjacent OU (b) ennemi adjacent qui tente un ACTIF. A(mine, anti-summon/anti-caster adjacent) + B(theirs, a mangé un counter 5294 en castant MurderousSwing adjacent à Ulf). gameconfig verbatim (« deals his Damage before that unit's ability is activated »). (déjà au wiki §5 + loophole normale-from-adjacent inscrit seed 80031 b6/b7.)
5. **Explodes (Snappawrecka)** : à la mort, 25% maxHP Direct à TOUS les adjacents (friendly-fire). A(mine, risque friendly près de mon cluster) + B(theirs, killed Snappawrecka adjacent à SON cluster → 2259 sur Ulf+Kariyan = free chip team1). gameconfig verbatim (explodesDmg:25). (déjà au wiki §1, exploit kill-at-range-into-enemy-cluster.)
6. **Ambush (Hollan / genesSmnAberrant)** : 1re mort → decoy ; resurrect FULL HP au début du prochain tour si decoy ami survit ; kill EXACT-HP déclenche le revive, OVERKILL le nie ; decoys Steppable (clearables). A(theirs, exact kill de l'Aberrant → resurrection, overkill next = permanent ; Hollan revive aussi sur exact-HP) + B(mine, Ambush revive cité comme part de l'engine). gameconfig verbatim (trait). (déjà au wiki §1 + §3bis, n>1.)
7. **GalvanicField / Mechanic (Actus)** : répare un allié → le réparé fait une attaque gratuite immédiate (<=4365). A(theirs, force-multiplier free-attack) + B(mine, mais largement INERTE = pas de 2e Mechanical à galvaniser, seul self-repair). gameconfig verbatim. (déjà au wiki §3 Actus ; INERTE-sans-2e-Mechanical = nuance déjà documentée, cf. Aleph-Null/§3.)

#### Divergences (entre les deux observateurs)

**AUCUNE divergence substantielle.** Match à TRÈS HAUTE CONCORDANCE : les deux observateurs s'accordent sur le vainqueur (team2), sur les win-conditions croisées (A.theirs ≈ B.mine = dual-engine sustain/summon ancré Hollan+Actus + pression Sho'syl/Tarvakh ; A.mine ≈ B.theirs = durable-brick ancré sur l'UNIQUE reaction-engine Sy-gex), et sur les 7 mécaniques cross-observées ci-dessus. Seule nuance d'interprétation (NON une contradiction de fait) : B s'auto-lit comme ayant gagné sur le TEMPO ranged + corps-summons jetables avec ses amplifiers (Hollan TwistedScience / Actus GalvanicField) **largement INERTES**, tandis qu'A surpondère le sustain comme LA raison de la défaite ; les deux conviennent que le pivot mécanique fut le Seeker T1 sur Sy-gex (suppression du seul peel out-trade) — lecture d'exécution convergente, pas une H.

### Erreurs identifiées (leçons, des deux sides)

- **A (perdant, FATAL)** : a HOLD Sy-gex passivement Markerlighté DANS la portée Seeker en projetant le hit comme ~5800 « survivable » → 9263 réel → Sy-gex à 274 → mort = perte de son UNIQUE peel (Overwatch + HeavyGravCannon out-trade) pour rien. Aurait dû tuer le Tau ce tour (annule le Seeker), OU spend Sy-gex offensivement (SentinelDirectives), OU le retirer hors-range avant la résolution. → friction TF28 (pas de magnitude incoming surfacée).
- **A** : structural — a amené un roster brick SANS aucun team-sustain dans un matchup dual-engine sustain + sniper (hard-counter connu par doctrine). Les bricks n'avaient plus de peel une fois Sy-gex mort ; la loss était largement décidée au niveau roster, mais le misplay Sy-gex l'a accélérée d'un tour plein.
- **A** : sur-respect du bait — le double-hold R3 a cédé du tempo à une compo qui grind plus vite qu'il ne trade ; contre un sustain SANS réponse, la passivité = mort lente, il fallait committer le peel ranged sur un engine plus tôt.
- **A** (défendable) : n'a pas détruit les decoys Aberrant/Hollan (Steppable) pour nier Ambush — mais les atteindre exigeait de suicider Kariyan profond → omission défendable, pas une erreur claire.
- **B (vainqueur)** : a casté MurderousSwing (un ACTIF) ADJACENT à Ulf → SavageKiller 5294 self-damage (Tarvakh 9537->4243). SavageKiller reconnu au recon mais non anticipé — aurait dû frapper Ulf en normale/range, ou rester non-adjacent.
- **B** : a gaspillé une activation Tarvakh full late-game (act-ability après un move qui avait silencieusement échoué hors movable set → attaque out-of-range no-op qui A CONSOMMÉ l'action — TF16). Doctrine : VÉRIFIER que le move a atterri avant d'attaquer.
- **B** : Shiron ExcruciatingFrequencies over-extended deep + ligne mal-visée depuis (3,5) → a touché 1 seul ennemi (Kariyan 2799) au lieu du triple-line col-2 visé → carry ranged stranded pour un chip single-target.
- **B** : a avancé Sho'syl à (5,6) T1 pour le Seeker → mis Sho'syl (et Tarvakh) dans la reach 2-tours adverse (a dû consolider un tour) ; le payoff Seeker le justifiait mais une tuile Seeker plus shallow eût été plus propre.

### Refs action logs

Action logs complets de CE run archivés dans `logs/selfplay/sp_80031_b8.json` (action_logs des 2 camps + rosters + outcome team2, rejouable via seed 80031) puis state-files supprimés post-teardown. Séquences décisives (Seeker T1 sur Sy-gex → suppression du peel → out-focus du mur durable) résumées ci-dessus.

---

## seed 81003 — winner=team2 (ts=b9)

| Équipe | Roster |
|--------|--------|
| **team1 (Player A / oracle, player 3) — PERDANT** | blackTerminator (Angrax) · thousInfernalMaster (Abraxas) · darkaHellblaster (Sarquael) · necroWarden (Makhotep) · worldJakhal (Macer) |
| **team2 (Player B / oracle, player 4) — VAINQUEUR** | spaceWulfen (Ulf) · blackHaarken (Haarken) · darkaAsmodai (Asmodai) · worldKharn (Kharn) · worldJakhal (Macer) |

### Adjudication

- A outcome_perceived = **L** ; B outcome_perceived = **W** → **winner_consensus = true** (A="L" & B="W" → team2).
- `rl_duel.py status --state-file data/_sp_81003_A.json` : `*** BATTLE FINIE — winner AUTORITATIF = team2 (battleStatus.winner=4, unitsAlive=10) ***` (champ natif, lisible post-Finished — H59 ; `alive_by_team={}` VIDE = normal post-Running, NON un draw).
- **authoritative_winner = team2.** Confirmé par le champ winner natif ET les deux narratifs (B a out-bursté la ligne fragile mixte d'A en un focus-dive concentré ; A a perdu son seul reaction-engine Sarquael au tour 3 puis s'est effondré 4v3 → 1v3).

### Win-conditions (consensus croisé A.theirs ≈ B.mine et A.mine ≈ B.theirs)

**team2 win-condition (VAINQUEUR)** : focus-dive 5-mêlée concentré. SOURCE = worldKharn (Kharn) — carry snowball : `KillMaimBurn` ~10k range-2 prioritise-kills (1 Pierce + 6 Eviscerate + 1 Plasma) + `TheBetrayer`/`BlessingsOfKhorne` snowball — force-multiplié par darkaAsmodai (Asmodai) `ExemplarOfHate` (mark Chaos +728 + Suppress/Pin + frappe DA gratuite) + `FearedInterrogator` (anti-Chaos), ouvert par worldJakhal (Macer) `Skullsmasher` (normale buffée par PV-manquant → overkill).
→ Accord A.theirs / B.mine = **CONSENSUS** (A a correctement identifié Kharn comme le carry/snowball à chip-from-range avant son 1er kill + Asmodai comme l'enabler anti-Chaos ; B s'auto-lit pareil, en notant que garder Kharn écrané full-HP T2-3 puis le committer au tour-4-kill window fut LA décision porteuse).

**team1 win-condition (PERDANT, jamais réalisée)** : moteur summon Psychic derrière écran. SOURCE = thousInfernalMaster (Abraxas) `MasterOfTheTutelaries` (cascade Pink Horror + Screamers par dégât Psychic) + `WeaverOfFate`, soutenu par darkaHellblaster (Sarquael) tourelle Overwatch r3 (le punisher de réaction vs un all-melee dive), screené par blackTerminator (Angrax) deep-strike TerminatorArmour + necroWarden (Makhotep) RelentlessMarch/LivingMetal. FAILLE = l'engine n'est JAMAIS venu online (Abraxas jamais en r2, Ulf SavageKiller verrouillait les summons, Asmodai a Pin+Suppress Abraxas, puis Abraxas focus-killé avant tout cast ; Sarquael, l'UNIQUE reaction-engine, focus-killé T3 → ligne fragile effondrée).
→ Accord A.mine / B.theirs = **CONSENSUS** (B a correctement lu Abraxas comme l'engine à kill-en-un-burst-garanti + Sarquael comme le turret Overwatch à bait/overkill, et les a éliminés dans cet ordre).

### Séquences clés (résumé des action logs — détail archivé dans logs/selfplay/sp_81003_b9.json)

**Player B (team2, VAINQUEUR) :**
- T2-3 : GARDA Kharn (le carry/snowball) écrané en arrière full-HP au lieu de le diver → dispo pour le tour-4 KillMaimBurn décisif. **Décision porteuse du match.**
- T3 : tua Sarquael avec une paire expendable+tank (Macer overkill + Haarken Herald) — Macer chunké-à-1360 (85% PV manquant) → sa normale buffée Skullsmasher a **OVERKILLÉ** Sarquael → FinalJustice NIÉ (Attack_WasOverkill=1, IsActingBeforeDeath=0). HELD ExemplarOfHate pour l'engine (marqua Abraxas le tour AVANT de l'atteindre) au lieu de le dépenser sur une cible non-Chaos.
- T4 : committa Kharn à (1,1) → `KillMaimBurn` tua Abraxas (7026, **exact K! avec ExemplarOfHate +728**) ET **spill** tua Makhotep (5705) ET chunka Macer-ennemi à 2222 — **triple impact, 2 kills en 1 cast**, flip 3v4 → 3v2.
- T5+ : `TheBetrayer` auto-attaqua Angrax au début du tour suivant (~1503) ; Ulf GreatFrostAxe overkilla le Macer chunké ; ferma l'anvil Angrax isolé 3v1.

**Player A (team1, PERDANT) :**
- T1-T2 : HOLD cohésif coin bas-gauche vs l'all-melee — Angrax deep-strike écran avant (expire à l'endturn, donc utilisé non gaspillé), Sarquael held pour armer Overwatch r3, fragiles au plus profond. Doctrine correcte (forcer le dive dans mes réactions) mais coin exigu.
- T3 : held Overwatch + chip enemy-Macer (3379→1360) pour setup un OW-overkill au lieu de décharger le ranged. En hindsight le hold OW n'a PAS sauvé Sarquael (focus-killé quand même).
- T4 (tourelle de réaction morte) : trada agressivement — tua enemy-Macer + Haarken, chunka Ulf → 4v3 — valeur extraite de corps condamnés, en évitant STRICTEMENT Ulf SavageKiller (Angrax NORMALE only ; Macer JakhalStimms depuis (1,0), non-adjacent à Ulf).
- T5 (1v3) : Angrax `BringerOfDespair` (dual-target) chunka Kharn 3702 + Asmodai 4674 pour l'attrition ; aucune ligne gagnante restante.
- ROOT CAUSE : a laissé l'ennemi lander le 1er focus-dive (leur T3) dans le coin exigu → Sarquael (UNIQUE reaction-engine) mort → fragiles 7k sans protection → effondrement 4v3 → 1v3 au tour suivant.

### Confrontation : consensus vs divergences

#### Mécaniques de CONSENSUS (rapportées des DEUX sides — cross-observable, recoupées gameconfig/i2)

1. **ExemplarOfHate (Asmodai) — enabler anti-Chaos** : A(theirs, high : Abraxas Chaos → `ExemplarOfHate_Target` + **Pinned** (no-retreat) + suppression ; team +728 + frappe DA gratuite 4365) + B(mine, med : cast sur Abraxas Chaos ; le +728 a rendu KillMaimBurn **exact K!**). gameconfig verbatim (`--ability ExemplarOfHate` : +728 melee/OW round+suivant ; si Chaos → Suppressed + 1 normale DA gratuite ≤4365). → **INSCRIT wiki §3 Asmodai** (hard-counter anti-Chaos doctrine) ; rider gating → H15 ; « Suppressed bloque le cast actif » INFÉRÉ par les 2 (non confirmé) → **H81** (n+1 convergent, 2ᵉ source).
2. **TheBetrayer (Kharn) — snowball gaté-kill** : A(theirs, high : actif SEULEMENT après un kill, puis auto-move+attaque début de tour) + B(synergy : après les 2 kills, auto-attaqua Angrax début du tour suivant ~1503). gameconfig verbatim (`--trait TheBetrayer`). **Entièrement déductible de gameconfig → NON ré-inscrit** (déjà wiki §2 Kharn).
3. **KillMaimBurn (Kharn) — prioritise-kills multi-target spill** : A(threat card : ~10k range-2, 1 Pierce + 6 Eviscerate + 1 Plasma) + B(mine, high : 1 cast a tué Abraxas + spill-tué Makhotep + chunké Macer = 2 kills 1 cast). gameconfig verbatim (« prioritise kills »). Structure déjà wiki §2 Kharn ; le **combo avec le mark Asmodai** (mark Chaos → exact K! + spill) = **NOUVELLE entrée synergie** au wiki.
4. **SavageKiller (Ulf) — anchor anti-summon/anti-actif** : A(theirs, med, dérivé : routé tout le match, jamais déclenché) + B(synergy : positionné pour instakill summons / pré-empter casts adjacents ; jamais fire car l'ennemi n'a jamais summon/cast adjacent). gameconfig verbatim (« deals his Damage before that unit's ability is activated »). Les 2 ont routé normales-depuis-adjacent + casts-depuis-non-adjacent → INERTE tout le match. → wiki §5 Ulf evidence n+1 (dissuasion qui peut ne jamais fire + routing confirmé 2 sides).
5. **BringerOfDespair (Angrax) — dual-target multi-hit** : A(mine, high : frappe la cible mêlée ET un autre ennemi adjacent ALÉATOIRE du même 4-hit ; bat Resilient) + B(threat card : « hits target + random adjacent »). gameconfig verbatim (« 4x à une cible mêlée et 4x à un autre ennemi adjacent aléatoire »). **Déductible de gameconfig → NON inscrit.**
6. **Skullsmasher (worldJakhal Macer) — scaling PV-manquant + anti-chip Resilient** : A(threat card : Resilient a survécu mon chip à 1 PV ; Skullsmasher Stun après un kill ; le tuer AVANT son 1er kill) + B(mine, high : Macer chunké-à-1360 → normale buffée OVERKILL Sarquael → FJ nié ; « a damaged Resilient World Eater hits harder » ; overkill pour nier le floor). gameconfig verbatim (`--ability Skullsmasher` +126/10% PV manquant + Stun-après-kill ; `--trait Resilient` floor sauf Overkill). → **INSCRIT wiki §2 worldJakhal** (interaction Resilient × Skullsmasher = anti-chip).
7. **FinalJustice nié par OVERKILL** : A(mine : FJ fire même stunned/AoE sauf OVERKILL) + B(mine : Macer overkill sur Sarquael → Attack_WasOverkill=1, IsActingBeforeDeath=0 → pas de riposte). gameconfig verbatim (« unless Overkilled »). (déjà wiki §1, n>1.)

#### Divergences (entre les deux observateurs)

**AUCUNE divergence de fait substantielle.** Une seule TENSION apparente, réconciliée (PAS une contradiction) :
- **Magnitude Overwatch de Sarquael** : B(theirs, high : OW Plasma stationnaire HeavyWeapon-boosté sur Macer ~**5656** ≫ nominal ~2.5k — le bonus no-move stacke sur l'OW) vs A(mine : son OW n'a chip Haarken que ~**2150** sur le dive). RÉCONCILIÉ par le mouvement : stationnaire = bonus HeavyWeapon stacké sur l'OW (~5656) ; si Sarquael a bougé → pas de bonus (~2150) — deux tirs distincts, deux états no-move différents. **Cohérent avec le wiki EXISTANT** (§3bis darkaHellblaster « STATIONNAIRE empile HeavyWeapon » + synergie « HeavyWeapon amplifie l'Overwatch ») → aucune nouvelle entrée ; le ~5656 = numérique/match-spécifique → JOURNAL only.
- **« Suppressed bloque le cast de MasterOfTheTutelaries d'Abraxas »** : INFÉRÉ par les DEUX (B explicitement « inferred » ; A a observé Pin+suppression), confirmé par AUCUN, CONFONDU par le focus-kill d'Abraxas + l'historique quirk spawn-tile TF12 → PAS un consensus dur → **H81** (candidat convergent 2ᵉ source, voir hypotheses).

### Erreurs identifiées (leçons, des deux sides)

- **A (perdant, FATAL)** : a laissé l'ennemi choisir le timing/l'angle du 1er focus-dive dans son coin exigu → Sarquael (UNIQUE reaction-engine) focus-killé T3 → fragiles 7k (Abraxas, Makhotep) sans protection → ligne effondrée. Doctrine corner-hold correcte mais le coin était trop serré ET la vitesse de fermeture all-melee sous-estimée (T2 danger-map montrait les tuiles arrière à danger-0, l'ennemi a atteint le cluster au tour suivant — classe TF26 : danger-zone = borne INFÉRIEURE vs RapidAssault/+move/range-2).
- **A** : n'a JAMAIS mis son wincon (Abraxas summon-engine) online — structurellement bloqué (jamais r2, Ulf SavageKiller menaçait les summons, puis Pin+killé). Aurait dû soit summon un Pink Horror screen tôt (T2/T3, pré-contact, loin d'Ulf) pour la présence board, soit accepter l'engine mort et repositionner Abraxas purement défensivement.
- **A (défendable)** : hold OW T3 vs unload ranged — le hold n'a PAS sauvé Sarquael (focus-killé quand même), donc le softening pré-dive forgone aurait peut-être été meilleur.
- **B (vainqueur)** : sur-committa son mur profond (Haarken 7386 Terrifying + Macer) à (2,0)/(2,1) T3 → l'ennemi focus-killa les DEUX (Terrifying mêlée-only n'a PAS sauvé Haarken vs Psychic+ranged) → trade down qui l'a brièvement mis 3v4. Aurait dû tuer Sarquael avec des corps moins profonds + reculer les survivants (ne pas laisser le tank forward post-kill). Le W est venu MALGRÉ ça, via le triple-kill Kharn T4.
- **B** : laissa le fragile Macer manger l'Overwatch HeavyWeapon-boosté de Sarquael (~5656) sur l'approche T2 (routé dans l'arc OW d'abord) — un tank full-HP aurait dû mener pour bait/absorber ce tir.

### Refs action logs

Action logs complets de CE run archivés dans `logs/selfplay/sp_81003_b9.json` (action_logs des 2 camps + rosters + outcome team2, rejouable via seed 81003) puis state-files supprimés post-teardown. Séquences décisives (Kharn écrané T2-3 → triple-kill KillMaimBurn T4 sur l'engine marqué Asmodai → snowball TheBetrayer) résumées ci-dessus.

## seed 81001 — winner=team1 (ts=b9)

### Rosters

| Équipe | Unités |
|--------|--------|
| **team1 (Player A / oracle, player 3) — VAINQUEUR** | u88 adeptRetributor (Vindicta) · u90 astraOrdnance (Thaddeus) · u92 spaceRockfist (Arjac) · u94 tauDarkstrider (Darkstrider) · u96 genesMagus (Xybia) |
| **team2 (Player B / oracle, player 4) — PERDANT** | u78 templHelbrecht (Helbrecht) · u80 admecMarshall (Tan Gi'da) · u82 custoBladeChampion (Kariyan) · u84 custoAtlacoya (Atlacoya) · u86 ultraCalgar (Calgar) |

### Adjudication

- A outcome_perceived = **W** ; B outcome_perceived = **L** → **winner_consensus = true** (A="W" & B="L" → team1).
- `rl_duel.py status --state-file data/_sp_81001_A.json` : `*** BATTLE FINIE — winner AUTORITATIF = team1 (battleStatus.winner=3, unitsAlive=20) ***` (champ natif, lisible post-Finished — H59 ; `alive_by_team={}` VIDE = normal post-Running, NON un draw).
- **authoritative_winner = team1.** Confirmé par le champ winner natif ET les deux narratifs (A, all-ranged, a tenu un coin cohésif et forcé l'all-mêlée ennemi à traverser, puis focus-killé les pièces over-extended tour par tour ; B s'est sur-clusteré profond dans le coin pour un alpha T3 puis s'est fait cluster-wipe 6→2 par l'AoE+crit en un tour ennemi). A a gagné T6, 2 tours sous le round-cap de 8 — MAIS en perdant 3 de ses 5 héros (victoire coûteuse).

### Win-conditions (consensus croisé A.theirs ≈ B.mine et A.mine ≈ B.theirs)

**team1 win-condition (VAINQUEUR)** : suprématie RANGED vs un all-mêlée sans portée. SOURCE = astraOrdnance (Thaddeus) `BasiliskBarrage` (artillery board-wide qui tire n'importe où s'il n'a pas bougé) + ligne ranged r2 qui bypass Terrifying, frontée par l'anvil Resilient stun-tank spaceRockfist (Arjac) `Foehammer` (scaling +2183/Character) et nourrie en corps gratuits par genesMagus (Xybia) `SpiritualLeader` (Neophyte + decoy). L'ennemi n'ayant AUCUN ranged global/long (tout r2) était STRUCTURELLEMENT forcé de traverser dans le coin cohésif → pattern dive-punish.
→ Accord A.mine / B.theirs = **CONSENSUS** (B lit correctement A comme « ranged kite + crit-snowball + anywhere-AoE artillery derrière un anvil unkillable » ; SOURCE = Thaddeus artillery feeding Vindicta + l'anvil Arjac/Foehammer). NUANCE : B crédite la `ActOfFaith` crit-snowball de Vindicta comme un moteur-clé de A (« crits bypass armor, killed my Calgar »), alors que A ne mentionne JAMAIS ActOfFaith (Vindicta morte tôt) → divergence de CAUSE (cf. confrontation + H82).

**team2 win-condition (PERDANT, jamais réalisée)** : brick-wall mêlée Imperial converti par un buff-engine empilé. SOURCE = ultraCalgar (Calgar) `RitesOfBattle` (+946 Imperial adjacent) + templHelbrecht (Helbrecht) `CrusadeOfWrath` (+364 melee/+pierce) + admecMarshall (Tan Gi'da) `ControlEdict` Skitarii-Vanguard summon-screens + burst anti-Psyker (custoAtlacoya Atlacoya `DaughterOfTheAbyss`/Direct + Helbrecht `DestroyTheWitch` +1091 vs Psyker). Plan : fermer la distance en masse durable cohésive et écraser la ligne ranged soft en mêlée buffée avant le round-cap.
→ Accord A.theirs / B.mine = **CONSENSUS sur le PACKAGE** (web buff-aura Calgar+Helbrecht+Tan Gi'da + summon-engine + anti-Psyker + close-as-cohesive-mass). DIVERGENCE de SALIENCE sur le CARRY : A foregrounde **Kariyan-as-carry** (Resilient snowball MartialInspiration/RapidAssault, menace critique) ; B s'auto-lit en foregroundant les **enablers Calgar (buff-aura) + Tan Gi'da (summons)** comme SOURCE et traite Kariyan comme une pièce de dive expendable (« Resilient ne survit PAS au focus multi-hit concentré »). Réconciliable : carry (Kariyan) vs enablers (Calgar/Tan Gi'da) du MÊME package buffé.

### Séquences clés (résumé des action logs — détail archivé dans logs/selfplay/sp_81001_b9.json)

**Player A (team1, VAINQUEUR) :**
- T1-T2 : HOLD le coin serré + barrage global. Lecture : l'all-mêlée ennemi n'a AUCUN ranged global → forcé de traverser → A tient un cluster cohésif, chip-free avec l'artillery Thaddeus, et laisse Xybia stationnaire minter Neophytes/decoys. Pas un double-turtle — A était le SEUL camp à dealer du dmg, forçant l'ennemi à venir.
- T3 : focus-kill le Kariyan over-extended (Resilient snowball carry) en multi-hit OVERKILL, APRÈS calcul de l'adjacence hex pour que le kill land AVANT que `FireOfAbsolution` de Vindicta puisse friendly-fire (Cherub no-op'd sur la cible déjà morte = zéro splash sur Xybia).
- T4 : Foehammer-stun + kill Calgar (anvil MkXGravis) ET kill Tan Gi'da (summon-engine) — collapse 3 de leurs 5 héros en deux tours ; dépense délibérément des Neophytes expendable pour FireOfAbsolution-clear les Vanguards chaff.
- T5-T6 : convertit le 2v1 : kill Atlacoya au ranged (bypass Terrifying), puis kill Helbrecht avec le tank (Arjac) positionné pour absorber son FinalJustice — gagne au tour 6.

**Player B (team2, PERDANT) :**
- T1-T2 : avance en masse cohésive plutôt que racer les units rapides (Kariyan move4) — correct vs un focus-fire team.
- T2-3 : alpha tua les DEUX engines ennemis PERMANENTS (Xybia summon/revive-Psyker via dive Kariyan + Helbrecht ; Darkstrider markerlight via `GauntletsOfUltramar` 5-cibles de Calgar), summona des Vanguard screens, chunka Vindicta/Thaddeus/Arjac → atteint un cluster 6v.
- ROOT-CAUSE ERROR : clustera toute sa force 6-units PROFOND dans le coin ennemi (cols 0-2) pour l'alpha T3 → présenta un blob serré à une team AoE+crit.
- Endgame : `BasiliskBarrage` (Blast HitsMultipleMembers) + `FireOfAbsolution` splash + crits `ActOfFaith` ont cleavé 4 units (Calgar, Tan Gi'da, 2 Vanguards) en UN tour ennemi (6→2) ; resta à grinder un anvil Arjac 9543 Resilient + Foehammer-scalé-en-one-shot sans aucune ligne pour le cracker (perte de son Direct quand Kariyan est mort → Atlacoya Direct n'avait plus de Custodes-adjacent).

### Confrontation : consensus vs divergences

#### Mécaniques de CONSENSUS (rapportées des DEUX sides — cross-observable, recoupées gameconfig/i2)

1. **BasiliskBarrage (Thaddeus)** : A(mine : artillery board-wide, Blast devastate-soft / near-useless-vs-armor — MkXGravis a soaké le même volley à ~683 vs ~4647 sur Atlacoya no-armor ; applique SuppressiveFire/Pinned) + B(theirs : anywhere-on-board AoE Blast pierce15 HitsMultipleMembers, grows +1 shell/round, chunka Atlacoya 4647 T1, l'engine qui punit le clustering). gameconfig verbatim (`--ability BasiliskBarrage` : 5 shells board-wide, +1/round écoulé, SuppressiveFire applies). **DÉJÀ pleinement au wiki §3bis Thaddeus** (board-wide scatter + move-gate + Bl`Pierce faible vs armure` + Suppress) → re-confirmation, AUCUNE nouvelle entrée (numériques match-spécifiques → journal).
2. **Foehammer (Arjac) — both-teams-count scaling** : A(mine : +2183/Character défait, snowball one-shot, multi-round cooldown) + B(theirs : +2183/Character + Stun r2, ~13k one-shot late, « trading Characters fed the anvil → ungrindable »). gameconfig verbatim (« each Character defeated in this battle »). DÉJÀ wiki §3 Arjac (self-play consensus seed 80000) → **n+1 evidence ajouté** : B (le PERDANT) confirme que sa propre approche attrition-trade (y compris SES propres morts) a armé l'Arjac ennemi en one-shot ungrindable.
3. **ControlEdict / Protector (Tan Gi'da) — summon-engine** : A(theirs : summon Skitarii Vanguard après attaque sous ProtectorImperative ; tuer Tan Gi'da ORPHELINE les Vanguards existants) + B(mine : chaque attaque auto-summon un Vanguard dans un hex adjacent libre, screen répétable). gameconfig verbatim (`--ability ControlEdict` : Protector → summon Vanguard/attaque, cap 5). DÉJÀ wiki §5 Tan Gi'da → **n+1 self-play consensus ajouté** : tuer l'engine stoppe la production (Vanguards existants orphelins/persistent), ne JAMAIS clear les Vanguards un par un — cross-validé les 2 sides.
4. **SpiritualLeader + Ambush (Xybia) — summon/decoy/revive engine** : A(mine : Xybia stationnaire summon Neophyte + decoy fin de tour ; bouger drop aussi un decoy) + B(theirs : tuer Xybia/Neophyte laisse un decoy Steppable NON-targetable + revive une fois sur un decoy au tour suivant full HP + tour immédiat ; decoys inatteignables pour la mêlée sauf en steppant dessus → 2 kills requis pour la retirer permanent). gameconfig verbatim (`--ability SpiritualLeader` : decoy on move, 2+ decoys → Neophyte ; `--trait Ambush` : 1ʳᵉ mort → decoy + resurrect full HP + tour immédiat). **DÉJÀ wiki §5 Xybia** (1ᵉʳ kill TEMP sauf decoys clear → 2ᵉ kill PERMANENT) → re-confirmation. Refinement B-only (decoy = tuile Steppable non-targetable que la mêlée ne peut cibler sauf en steppant) = observateur unique → journal, pas wiki.
5. **Resilient overkill (Kariyan)** : A(theirs : Unit_WasOverkilled=1 — multi-hit overkill en un team-turn défait Resilient outright, save 1×-à-1PV sauf overkill) + B(mine : `MartialInspiration` dive… Resilient n'a PAS sauvé Kariyan du focus de retour). gameconfig verbatim (`--trait Resilient`). **DÉJÀ canonique** (wiki §2 Kariyan MartialKatah + multi-hit-bat-Resilient, self-play consensus seed 80020) → re-confirmation.
6. **TerminatorArmour 1ʳᵉ-hit + FinalJustice blunted (Arjac)** : A(mine : FinalJustice de Calgar a fire sur Arjac mais TerminatorArmour l'a réduit à ~263) + B(theirs : 1ʳᵉ attaque/tour réduite ~-75% excl Psychic/Direct ; n'a pas pu cracker 9543). gameconfig/wiki couverts (TF04 n+4 + wiki §3 Arjac) → re-confirmation.
7. **SuppressiveFire (Thaddeus/Darkstrider)** : A(mine : barrage applique Suppress/Pinned) + B(theirs : ranged hit → Suppressed → move réduit ; Helbrecht endgame seulement 9 move tiles, ne pouvait pas atteindre le Thaddeus soft). gameconfig verbatim (`--trait SuppressiveFire`). DÉJÀ wiki §3bis + §6 → re-confirmation (la sémantique « bloque-t-il l'ACTIF du porteur » reste H81, non tranché).
8. **FireOfAbsolution (Vindicta) — splash all-adjacent (friendly-fire)** : A(mine : à chaque ranged, splash 3x~1455 Flame à TOUTES les units adjacentes À LA CIBLE, Y COMPRIS les miennes) + B(synergy/threat : « FireOfAbsolution adjacent splash » comme volet du cluster-wipe). gameconfig verbatim (« 3x 1455 Flame to ALL units adjacent to the target »). **DÉJÀ pleinement wiki §3 Vindicta** (friendly-fire confirmé n=3) → re-confirmation.

#### Divergences (entre les deux observateurs)

- **D1 (SALIENCE win-con team2) — RÉCONCILIÉE, pas une contradiction** : A foregrounde Kariyan-as-carry (le Resilient snowball buffé) ; B s'auto-lit en foregroundant Calgar (buff-aura) + Tan Gi'da (summons) comme SOURCE et traite Kariyan en pièce de dive expendable. Les deux décrivent le MÊME package (mêlée buffée + summons + anti-Psyker) ; carry (A) vs enablers (B) = deux faces du même engine → journal only, pas de mécanique nouvelle.
- **D2 (CAUSE de la mort de Calgar / contribution ActOfFaith) — divergence de FAIT** : B(mine, conf high) attribue la mort de son tank Calgar aux crits `ActOfFaith` de Vindicta qui « bypass MkXGravis double-armour » pendant le cluster-wipe ; A(mine) attribue la mort de Calgar à un grind Power/Flame + Foehammer-stun focus (« Power/Flame ground it down despite MkXGravis ; killed T4 ») et ne mentionne JAMAIS ActOfFaith (Vindicta morte tôt côté A). gameconfig `--trait ActOfFaith` confirme le crit-ramp (+crit chance/dmg par mort/kill Imperial, reset au 1ᵉʳ crit) mais NE dit RIEN d'un bypass d'armure par les crits → claim B non-déductible. → **H82** (candidat mécanique flaggé self-play divergence A/B).

### Erreurs identifiées (leçons, des deux sides)

- **A (vainqueur, mais victoire coûteuse)** : a perdu Xybia (son SEUL Psyker / outil armour-bypass) en la poussant forward à (0,3) pour le shot Psychic du kill-Kariyan → boxée, sans lane de retraite, focus-killée au tour ennemi. A ensuite dû grinder le MkXGravis de Calgar sans bypass (a marché, plus risqué). Aurait dû sécuriser le kill Kariyan sans committer Xybia forward.
- **A** : a perdu Darkstrider ET Vindicta sur les tours ennemis post-T3/T4 — over-extension classique : après les kills, fragiles laissés en reach sans lane de retraite, Vindicta tradée pour des Vanguards chaff. Net : 3 de 5 héros perdus malgré la win. Corner-hold avec 4 fragiles derrière UN seul tank ne pouvait pas screener le dive T3 (Kariyan/Calgar ont atteint 2 fragiles à la fois).
- **B (perdant, FATAL)** : deep mass over-cluster dans une killzone AoE/crit. Vs une team à anywhere-AoE + multi-member Blast + crit-snowball, ne JAMAIS présenter un cluster serré — spread l'alpha ou stagger la profondeur. (classe TF26 : danger-zone = borne INFÉRIEURE.)
- **B** : a trusté le MkXGravis de Calgar comme tank forward safe, mais les crits ActOfFaith (selon B) bypassent l'armure → tank pas safe une fois le crit-snowball lancé. Aurait dû tuer Vindicta (soft 7029, atteignable) PLUS TÔT pour nier le snowball.
- **B** : Kariyan solo deep-dive (T2) — Resilient ne survit PAS au focus multi-hit concentré, focus-killé (carry tradé pour un kill temp-Xybia). Et a nourri le Foehammer d'Arjac via l'attrition (chaque Character tradé, y compris les siens, → Arjac ~13k one-shot ungrindable).

### Refs action logs

Action logs complets de CE run archivés dans `logs/selfplay/sp_81001_b9.json` (action_logs des 2 camps + rosters + outcome team1, rejouable via seed 81001) puis state-files supprimés post-teardown. Séquences décisives (HOLD coin + barrage global force le dive → focus-kill Kariyan T3 puis Calgar+Tan Gi'da T4 → convert 2v1 T5-6 en gérant FinalJustice via le tank) résumées ci-dessus.

## seed 81002 — winner=team2 (ts=b9)

### Rosters

| Équipe | Unités |
|--------|--------|
| **team1 (Player A / oracle, player 3) — PERDANT** | u88 templAncient (Thoread) · u90 spaceBlackmane (Ragnar) · u92 admecManipulus (Actus) · u94 darkaAsmodai (Asmodai) · u96 tauDarkstrider (Darkstrider) |
| **team2 (Player B / oracle, player 4) — VAINQUEUR** | u78 templAggressor (Burchard) · u80 tauCrisis (Re'vas) · u82 deathBlightbringer (Corrodius) · u84 bloodDeathCompany (Lucien) · u86 eldarRanger (Calandis) |

### Adjudication

- A outcome_perceived = **L** ; B outcome_perceived = **W** → **winner_consensus = true** (A="L" & B="W" → team2).
- `rl_duel.py status --state-file data/_sp_81002_A.json` : `*** BATTLE FINIE — winner AUTORITATIF = team2 (battleStatus.winner=4, unitsAlive=20) ***` (champ natif, lisible post-Finished — H59 ; `alive_by_team={}` VIDE = normal post-Running, NON un draw).
- **authoritative_winner = team2.** Confirmé par le champ winner natif ET les deux narratifs (B, ranged + double-overwatch turtle, a HOLD un coin cohésif et armé son filet de réaction ; A, all-mêlée WarHowl, FORCÉ par le round-cap de traverser, a perdu son moteur Ragnar mid-move dans le mur d'overwatch AVANT toute attaque → loss structurelle). 0 perte de héros côté B.

### Win-conditions (consensus croisé A.theirs ≈ B.mine et A.mine ≈ B.theirs)

**team2 win-condition (VAINQUEUR)** : filet de réaction ranged + double-overwatch. SOURCE = tauCrisis (Re'vas) `EarlyWarningOverride` (arme un Overwatch multi-hit +1892/hit + summon 2 Shield Drones) + eldarRanger (Calandis) `Overwatch` (HeavyWeapon r3) = un MUR de réaction superposé qui one-shot un mover mid-move ; backstop = anvil deathBlightbringer (Corrodius) Resilient + aura `ContagionsOfNurgle` (-armure croissante) + summon Poxwalker (board-flip), + le mur templAggressor (Burchard) MkXGravis. Plan : HOLD un coin cohésif, forcer l'all-mêlée à diver dans le filet, punir, puis grinder les survivants avec ranged aura-boosté + masse summon.
→ Accord A.theirs / B.mine = **CONSENSUS** (les 2 sides nomment le MÊME package : Re'vas EWO + Calandis Overwatch = le filet décisif, Corrodius aura+summon, Burchard mur).

**team1 win-condition (PERDANT, jamais réalisée)** : burst mêlée WarHowl. SOURCE = spaceBlackmane (Ragnar) `WarHowl` (engine : +dmg/+crit/Unstoppable à toute la ligne mêlée Characters sans normale ranged) + templAncient (Thoread) `AstartesBanner` (+1 hit mêlée) + `UnbreakableDuty` (-33% aura) ; Asmodai anti-Chaos (ExemplarOfHate Suppress + FearedInterrogator) vs Corrodius ; le crit WarHowl bypass le MkXGravis de Burchard. JAMAIS cashé — la ligne ne pouvait pas atteindre les cibles sans mourir au mur d'overwatch.
→ Accord A.mine / B.theirs = **CONSENSUS** (B lit A comme « WarHowl-buffed melee dive, SOURCE = Ragnar, doit lander buffé pour gagner » ; A confirme « SOURCE/enabler = Ragnar + Thoread, NEVER cashed »). Les 2 s'accordent : Ragnar mort sur le dive AVANT d'armer WarHowl = la ligne jamais buffée.

### Séquences clés (résumé des action logs — détail archivé dans logs/selfplay/sp_81002_b9.json)

**Player A (team1, PERDANT) :**
- T1-T2 : avance cohésive tank-led vers l'ennemi turtle-coin (round-cap force le camp mêlée à fermer). Sain en principe, MAIS a brûlé `UnbreakableDuty` (Thoread) T1 spéculativement (aucun ennemi en portée) → gaspillé (cooldown multi-tour → indispo pour le vrai engagement T3).
- T3 : a obtenu WarHowl gratis (quirk de label TF29 — le buff s'est appliqué malgré le « TOUR ABANDONNÉ ») et committé Ragnar pour chunk Corrodius — FATAL : il a marché dans l'arc d'overwatch Re'vas+Calandis et est mort mid-move (~10k multi-hit) AVANT d'attaquer. Cette seule erreur (ne pas avoir mappé la portée/magnitude de l'overwatch) a perdu le moteur + le match.
- Salvage : Darkstrider (Infiltrate, OW-immune) a chunk Calandis 7029→1752 proprement (markerlight), puis hold/pull-back pour préserver les units et bait les dives plutôt que de feeder le mur.
- A a flaggé le matchup comme contre-structurel : roster mêlée-burst incapable d'engager un turtle ranged + multi-hit-overwatch (seul Infiltrate traverse) backé par 2 anvils ~12k + un summoner Poxwalker — et le round-cap force à traverser la kill-zone.

**Player B (team2, VAINQUEUR) :**
- T1-T2 : HOLD un coin cohésif + tuck la fragile Calandis + arme le double-overwatch (Re'vas EWO drones+OW, Calandis HeavyWeapon OW) au lieu de lunge dans leur cluster danger-5. L'all-mêlée FORCÉ de diver → le filet a tué Ragnar (la SOURCE-wincon) à coût zéro = swing décisif.
- T3 : pivot pour tuer le Darkstrider over-extended isolé (Corrodius melee + Burchard Fragstorm, 2 units) spécifiquement pour retirer le pending-fire markerlight différé sur Calandis (1752) per TF28 — l'a sauvée + retiré le moteur markerlight.
- T5 : priorise tuer Thoread AVANT le self-repair Actus, pour nier le +7275 balloon de UnbreakableDuty (2 Imperials déjà morts) ; ranged aura-boosté pour un overkill min-sum>HP garanti.
- Presse l'avantage avant le round-cap 8 : explosion 8-Poxwalker comme board-flip pour gut Actus, finit T6, ZÉRO perte de héros.

### Confrontation : consensus vs divergences

#### Mécaniques de CONSENSUS (rapportées des DEUX sides — cross-observable, recoupées gameconfig/i2)

1. **EarlyWarningOverride (Re'vas)** : A(theirs : mur d'overwatch multi-hit ~7-10k combiné qui a tué Ragnar 10038 mid-move avant attaque ; reste en OW après un kill) + B(mine : arme Overwatch +1892 jusqu'à son prochain tour + summon 2 Shield Drones, single-use [indispo] après). gameconfig `--ability EarlyWarningOverride` verbatim (+1892, 2 drones, « remains in Overwatch after defeating a unit, retaining 1 fewer hits »). **DÉJÀ wiki §1 Overwatch + §3bis Re'vas** → re-confirmation + **n+1 consensus ajouté §1** (arcs d'overwatch SUPERPOSÉS = un seul mover prend toutes les ripostes = one-shot mid-move).
2. **Calandis Overwatch + HeavyWeapon** : A(theirs : fired 2502 sur Asmodai T2, 3205 sur Ragnar T3 ; spent une fois tiré, re-arme au début de son tour) + B(mine : fire si pas attaqué sur 1er ennemi entrant en r3 au tour adverse ; +dmg si pas bougé = HeavyWeapon). gameconfig `eldarRanger` verbatim (HeavyWeapon + Overwatch). **DÉJÀ wiki §3bis Calandis** → re-confirmation.
3. **Corrodius Poxwalkers** : A(theirs : ~8 Poxwalkers 2992 dans hexes libres de l'aura Contagion croissante, flood à 14 units) + B(mine : aura range 3 round 5+ → spawn HUIT Poxwalkers 2992 PV/3490 atk, les adjacents attaquent IMMÉDIATEMENT au spawn = board-flip, Actus 5022→570). gameconfig confirme le summon. **DÉJÀ wiki §2 Corrodius** → re-confirmation (numériques match-spécifiques → journal).
4. **ContagionsOfNurgle (Corrodius)** : A(theirs : armor-aura en expansion) + B(mine : -armure ENNEMIE croissante R1→R5, range 1→3, stack -40% si 2+ auras, -764 FixedArmor observé). gameconfig `--trait ContagionsOfNurgle` verbatim. **DÉJÀ wiki §1 + §2 (self-play consensus seed 80085)** → re-confirmation.
5. **Darkstrider Infiltrate (OW-immune) + StructuralAnalyser markerlight** : A(mine : trait permanent, traverse l'arc Re'vas/Calandis en prenant ZÉRO overwatch, shot 5277 sur Calandis — SEULE unité à traverser le mur) + B(theirs : Infiltrate ignore mon overwatch, markerlight + pending-fire sur Calandis 7029→1752). gameconfig `--trait Infiltrate` verbatim. **DÉJÀ wiki §1 Overwatch + §3bis Darkstrider** → re-confirmation.
6. **Ragnar WarHowl (engine all-mêlée)** : A(mine : SOURCE/enabler, NEVER cashed) + B(theirs : WarHowl-engine, tué sur le dive AVANT d'armer le buff/1er kill = jamais amplifié la ligne). gameconfig `--ability WarHowl` verbatim. **DÉJÀ wiki §3bis Ragnar** (« tuer AVANT WarHowl gutte l'offense all-mêlée ») → re-confirmation.
7. **Asmodai Terrifying (melee-only)** : A(implicite, mistakes « Terrifying tank = useless vs ranged ») + B(theirs explicite : réduit la MÊLÉE seulement, 4 ranged l'ont tué full value). gameconfig `--trait Terrifying` verbatim (melee-only). **DÉJÀ wiki §1** → re-confirmation.
8. **Thoread UnbreakableDuty** : A(mine : cooldown MULTI-tour, [indispo] T2-5 après un cast T1) + B(theirs : balloon conditionnel — 2+ Imperial Characters alliés morts → +7275 HP/+1455 dmg + free attack, killed before re-cast). gameconfig `--ability UnbreakableDuty` confirme le balloon (PAS le cooldown — live-only). **wiki §3 Thoread** a déjà le balloon + demote-sole-Imperial → **n+1 ajouté** : cooldown multi-tour → ne pas burner l'aura -33% spéculativement.

#### Divergences (entre les deux observateurs / vs gameconfig)

- **D1 (Actus « repair-engine INERTE car SEUL Mechanical ») — CONTREDITE par gameconfig** : B(mine, conf high) traite Actus en engine inerte car « sole Mechanical → GalvanicField sans bénéficiaire, ne peut que self-repair ». gameconfig `--ability DefendTheDivineWork` = « répare self ET TOUS les alliés ADJACENTS » (AUCUNE restriction Mechanical) et `GalvanicField` trigge « quand Actus répare UNE AUTRE unité » → Actus PEUT réparer un allié adjacent et armer GalvanicField. L'inert-ness observée était donc SITUATIONNELLE (ses alliés mêlée morts/non-adjacents au backline Actus → pas d'allié adjacent vivant à réparer ; le self-repair seul ne trigge PAS GalvanicField), PAS structurelle (sole-Mechanical). A ne cross-observe pas. → **H83** (candidat flaggé, claim B contredit par gameconfig — la règle engine-inerte ne s'applique PAS ici).
- **D2 (tour de mort de Ragnar) — non-matériel** : A dit T3, B dit « ~T2 » → artefact TF14 (compteur de tour per-player non fiable). Les 2 s'accordent que Ragnar est mort sur le dive AVANT WarHowl → PAS une vraie divergence mécanique.

### Erreurs identifiées (leçons, des deux sides)

- **A (perdant, FATAL)** : a walké Ragnar (10038, moteur WarHowl) dans l'arc combiné Re'vas EWO + Calandis OW T3 → tué par ~10k multi-hit overwatch DURANT le move, avant toute attaque. N'a pas mappé la portée/magnitude de l'overwatch avant de committer ; aurait dû savoir que Re'vas EWO = mur one-shot multi-hit et que SEUL Darkstrider (Infiltrate) traverse.
- **A** : a brûlé UnbreakableDuty (-33% aura) T1 sans ennemi en portée — cooldown multi-tour → mitigation indispo pour l'engagement T3 où il en avait le plus besoin.
- **A** : a envoyé Asmodai (Terrifying tank = inutile vs ranged, 9035) sur la tuile la plus forward T2, mangeant un OW Calandis 2502 pour rien ; aurait dû mener avec les tanks Parry/block (Thoread/Ragnar) et screener Asmodai.
- **A** : a engagé dans la kill-zone ranged+OW sans neutraliser les overwatchers d'abord — vu le contre-structurel, un hold/bait plus strict (ou accepter la loss plus tôt) avait sans doute un EV pas pire que feeder le mur.
- **B (vainqueur)** : Calandis chunk 7029→1752 par le pending-fire markerlight de Darkstrider — laissée à (5,7) dans la r2+Infiltrate de Darkstrider (Infiltrate = son overwatch ne le déterrait pas) ; aurait dû l'anticiper et la pull row 8. A survécu seulement car Darkstrider tué le tour suivant.
- **B** : chip Re'vas sur Actus T5 partiellement gaspillé (Actus self-repair 4365) — réserver le dmg sur un self-repairer pour un alpha en un tour (rendu moot par l'explosion Poxwalker, mais le principe tient).

### Refs action logs

Action logs complets de CE run archivés dans `logs/selfplay/sp_81002_b9.json` (action_logs des 2 camps + rosters + outcome team2, rejouable via seed 81002) puis state-files supprimés post-teardown. Séquences décisives (B HOLD coin + arme double-overwatch → A all-mêlée forcé de diver par le round-cap → Ragnar mort mid-move dans le mur OW AVANT WarHowl = swing décisif → B grind les survivants avec aura Corrodius + flood Poxwalker, finit T6 sans perte) résumées ci-dessus.

## seed 81004 — winner=team1 (ts=b9)

### Rosters

| Équipe | Unités |
|--------|--------|
| **team1 (Player A / oracle, player 3) — VAINQUEUR** | u88 ultraInceptorSgt (Bellator) · u90 ultraApothecary (Incisus) · u92 astraDreir (Dreir) · u94 eldarMauganRa (Maugan Ra) · u96 darkaAzrael (Azrael) · + summons astraSmnDeathRider ×4 (Dreir) + ultraSmnInceptor ×3 (Bellator) |
| **team2 (Player B / oracle, player 4) — PERDANT** | u78 necroWarden (Makhotep) · u80 templSwordBrother (Godswyl) · u82 bloodIntercessor (Mataneo) · u84 worldJakhal (Macer) · u86 adeptHospitaller (Isabella) |

### Adjudication

- A outcome_perceived = **W** ; B outcome_perceived = **L** → **winner_consensus = true** (A="W" & B="L" → team1).
- `rl_duel.py status --state-file data/_sp_81004_A.json` : `*** BATTLE FINIE — winner AUTORITATIF = team1 (battleStatus.winner=3, unitsAlive=19) ***` (champ natif, lisible post-Finished — H59 ; `alive_by_team={}` VIDE = normal post-Running, NON un draw).
- **authoritative_winner = team1.** Confirmé par le champ winner natif ET les deux narratifs (A, reaction-cluster HOLD + double summon-engine, a tenu un coin serré OW-armé jusqu'à ce que l'ennemi mêlée dive, puis flood Death Riders + Inceptors pour flip 5v5→9v1 et clore sur le tour-cap 8 ; B, sustain + snowball-carry mêlée, n'a jamais pu délivrer un alpha cohésif dans le coin sans trade-down → loss structurelle pour un roster mêlée-brick face à un turtle + double-summon). A a fini T8 = le tour exact du round-cap.

### Win-conditions (consensus croisé A.theirs ≈ B.mine et A.mine ≈ B.theirs)

**team1 win-condition (VAINQUEUR)** : reaction-cluster HOLD + double summon-engine snowball. SOURCE = darkaAzrael (Azrael) `LionHelm` aura (+dmg sur les attaques Overwatch des alliés à ≤2 hex) + held-Overwatch de Maugan Ra/Azrael (Maugan Ra `InescapableAccuracy` = ses ripostes OW ignorent les hit-reductions/Parry) forçant l'ennemi mêlée à diver dans le coin où la carry fragile (Maugan Ra) était écran-mêlée ; puis astraDreir `LeadingTheCharge` (4 Death Riders) + ultraInceptorSgt `DeathFromAbove` (Inceptors croissants) ont flippé 5v5 en 9v1. Incisus `Narthecium`/`CombatRestoratives` = sustain (adjacent-only).
→ Accord A.mine / B.theirs = **CONSENSUS** (B lit A comme « sustain-turtle-then-summon-flood : SOURCE = Dreir LeadingTheCharge + Bellator DeathFromAbove gated derrière un corner-turtle + 2 OW amplifiés LionHelm + Incisus heal/revive ; held jusqu'au commit/bait puis unleash les 2 engines = flip 4v4→4v9 »). Les 2 sides nomment le MÊME package décisif.

**team2 win-condition (PERDANT, jamais réalisée)** : sustain + snowball-carry mêlée. SOURCE = adeptHospitaller (Isabella) `RitesOfRestoration` heal/revive-Imperial + bursts mêlée (templSwordBrother Godswyl `ThunderousAssault` stun + always-overkill, bloodIntercessor Mataneo `HammerOfWrath` deep-strike) + carry snowball worldJakhal (Macer) `JakhalStimms` (multi-hit qui bat Resilient) + necroWarden (Makhotep) `RelentlessMarch` tempo aura ; Makhotep `Gauss` r3 bypasse le Terrifying de Maugan Ra.
→ Accord A.theirs / B.mine = **CONSENSUS** (A lit B comme « sustain + snowball-carry mêlée, SOURCE = Isabella reviver feeding Godswyl/Mataneo bursts + Macer snowball »). Les 2 s'accordent : B n'a jamais pu lander un alpha cohésif dans le coin sans trade-down ; `AdaptiveStrategy`/repair de Makhotep INERTE (aucun allié non-Character/Mechanical).

### Séquences clés (résumé des action logs — détail archivé dans logs/selfplay/sp_81004_b9.json)

**Player A (team1, VAINQUEUR) :**
- T1-T3 : HOLD un coin serré, Maugan Ra (carry fragile) écran-mêlée par ses propres units, Overwatch armé → force l'ennemi mêlée-lourd à diver dans le reaction-cluster plutôt que d'over-extendre les fragiles dans la portée ennemie. (légèrement TROP passif : 3 holds consécutifs vs un oracle aussi prudent → la fenêtre de closure tombe pile au round-cap.)
- T4 : refuse l'over-commit sur un kill Mataneo non-garanti ; heal Maugan Ra + chip. ⚠ ERREUR : le chip d'Azrael (`DarkTalonStrike`) laisse Mataneo à 4488 (juste SOUS son seuil 50% = 4517) → arme un `HammerOfWrath` DOUBLÉ qui tue Azrael (perte de l'ancre LionHelm/FinalJustice).
- T5 : kill propre de Mataneo (Maugan Ra multi-hit + Dreir, garanti).
- T6 : casse PROACTIVEMENT le double-turtle naissant (cap round-8 = double-defeat) avec Dreir `LeadingTheCharge` sur la carry Macer → la tue (multi-hit bat Resilient) + flood 4 Death Riders pour forcer l'engagement.
- T7 : focus le reviver Isabella + Godswyl quasi-mort, via Maugan Ra (6-hit, cible no-Parry) + Bellator `DeathFromAbove` round-7. T8 : clôt Makhotep 9v1 = win sur le tour-cap.

**Player B (team2, PERDANT) :**
- A targété Azrael en 1er kill (atteignable, no Terrifying/Resilient, PAS adjacent à Incisus → pas de revive) — correctement strip le LionHelm + un dealer ranged. MAIS l'exécution a over-committé Mataneo deep (perdu) ET envoyé Godswyl dans l'arc OW de Maugan Ra (chunké 9539→49 puis mort).
- T5 : tour preserve/bait (lone Resilient Macer forward, hold le reste) en espérant contrer l'avance — LE PIRE choix vs un summon-engine turtle : Macer est devenu la cible qui a armé `LeadingTheCharge` (4 Death Riders) + le focus qui a tué la carry.
- Une fois floodé à 3v8, pivot pour convertir les Death Riders (Godswyl K! + gang Makhotep/Isabella) — triage correct mais bien trop tard.

### Confrontation : consensus vs divergences

#### Mécaniques de CONSENSUS (rapportées des DEUX sides — cross-observable, recoupées gameconfig/i2)

1. **Maugan Ra held-Overwatch + InescapableAccuracy (ignore Parry/hit-reduction)** : A(mine : OW armé dans le cluster, dive-punish a gutté Godswyl sans dépenser d'action offensive) + B(theirs : not-moved OW = 6 hits ~9490 sur Godswyl 9539→49, IGNORE Parry ; InescapableAccuracy override-hits ≈ one-shot un 9.5k durable). gameconfig `--ability InescapableAccuracy` (ignore hit-reductions, s'applique aux tirs OW) + `--trait Parry` (−1 hit multi-hit). **DÉJÀ wiki §1 Overwatch + §3bis Maugan Ra + §1 Parry** → re-confirmation.
2. **Azrael LionHelm aura buffe l'Overwatch allié** : A(mine : LionHelm buff les attaques OW → dive-punish ; killer Azrael retire l'aura) + B(theirs : aura buffe l'OW allié +437/block, amplifie la léthalité réactive du coin ; retirée en tuant Azrael). gameconfig `--ability LionHelm`. **DÉJÀ wiki §1 Overwatch (amplificateur LionHelm) + §3bis Azrael** → re-confirmation.
3. **Incisus/Apothecary CombatRestoratives + Narthecium = sustain ADJACENT-ONLY (chunks hors-adjacence STICK)** : A(mine : heal self + adjacent only → ne pouvait pas atteindre Azrael à 2 hex → ni heal ni revive → Azrael perdu) + B(theirs : heal Maugan Ra adjacent 5338→7029, mais Dreir/Azrael à distance-2 NON soignés → chunks STICK). gameconfig `--ability CombatRestoratives|Narthecium`. **DÉJÀ wiki §3bis ultraApothecary [self-play consensus seed 80072]** → re-confirmation (seed 81004 ajoutée au tag) ; doctrine confirmée : garder les revivables COLLÉS adjacents à l'Apothecary.
4. **Double summon-engine TURTLE : Dreir LeadingTheCharge (4 Death Riders, gate « n'a pas bougé ») + Bellator DeathFromAbove (Inceptors croissants/round)** : A(mine : flood 4 Death Riders + 3 Inceptors, snowball 5v5→9v1 ; DeathFromAbove cap par hexes libres autour de la cible ; LeadingTheCharge = charge 3x + 4 Death Riders qui attaquent immédiatement) + B(theirs : Dreir 4 permanent Death Riders + Bellator 3 Inceptors, les DEUX gated derrière le turtle — fire SEULEMENT quand on présente une cible forward → flood 4v4→4v9). gameconfig `--ability LeadingTheCharge` (gate « has not moved » + 4 Death Riders VERBATIM) + `--ability DeathFromAbove` (1 Inceptor/round démarré VERBATIM). **NOUVELLE entrée combo wiki §combos** (turtle-then-flood + doctrine total-denial-OR-guaranteed-engine-kill) [self-play consensus, seed 81004].
5. **Mataneo HammerOfWrath : 2 Jump Pack Intercessors summonés à la charge + Infiltrate (no-OW sur la charge)** : A(theirs : re-summon 2 Jump Pack Intercessors à la charge ; doublé <=50% PV de Mataneo) + B(mine : grants Infiltrate → AUCUN OW sur la charge ; ses 2 summons + Mataneo occupent les hexes adjacents = ont WALLÉ son propre follow-up mêlée). gameconfig `--ability HammerOfWrath|AggressiveOnslaught`. **DÉJÀ wiki §3bis Mataneo (doublage <=50%, 2 JPI, Infiltrate VERBATIM)** → re-confirmation. (Le doublage <=50% n'est rapporté QUE par A ce match mais déjà wiki/gameconfig-vérifié.)
6. **Godswyl ThunderousAssault = always-overkill (vs FinalJustice)** : A(theirs : counter = overkiller son ThunderousAssault stun+forced-overkill) + B(mine : « always overkill » s'applique à SON kill — mais ChampionOfTheFeast (passif move-triggered, NON-overkill) a délivré le finish sur Azrael → a FAIT fire FinalJustice). gameconfig `--ability ThunderousAssault|ChampionOfTheFeast`. **DÉJÀ wiki §1 (FJ : kill non-overkill déclenche FJ) + §3bis Godswyl (ChampionOfTheFeast move-triggered)** → re-confirmation de la règle (cohérente). Le DÉSACCORD sur QUI a tué Azrael (attribution) → divergence D1.

#### Divergences (entre les deux observateurs / vs gameconfig)

- **D1 (tueur EXACT d'Azrael, T4) — attribution divergente** : A(victime, conf high) attribue la mort d'Azrael à un `HammerOfWrath` DOUBLÉ de Mataneo SEUL (« doved alone T4, killed my Azrael with a doubled hammer »). B(owner des DEUX attaquants, conf high) attribue la mort à Mataneo `HammerOfWrath` **CHUNK** PUIS Godswyl `ChampionOfTheFeast` (2085, NON-overkill) **FINISH** → ce qui a fait fire la FinalJustice d'Azrael ; le ThunderousAssault suivant a no-op sur le cadavre. Le récit de B est cohérent avec l'OW de Godswyl (Godswyl a bougé pour finir Azrael → a mangé l'OW Maugan Ra 9539→49, et ChampionOfTheFeast EST move-triggered) et avec la règle wiki §1 (un kill non-overkill déclenche FJ). B (owner des attaquants) a la meilleure visibilité → son attribution est probablement correcte. → **H84** (self-play divergence A/B — divergence d'ATTRIBUTION sur le même kill ; la règle sous-jacente FJ-non-overkill est DÉJÀ wiki-cohérente, ce n'est PAS une contradiction de mécanique).

### Erreurs identifiées (leçons, des deux sides)

- **A (vainqueur, erreur proximale non-fatale)** : a chippé Mataneo à 4488 (juste SOUS son seuil 50% = 4517) → a ARMÉ le `HammerOfWrath` doublé qui a tué Azrael. Doctrine : garder un Mataneo STRICTEMENT >50% PV OU ne pas le chipper du tout quand un kill garanti n'est pas dispo (cf. wiki §3bis Mataneo : SON PV <=50% = doublage).
- **A** : erreur de géométrie de cluster — Azrael à 2 hex d'Incisus → l'Apothecary ne pouvait NI heal NI revive (CombatRestoratives/Narthecium adjacent-only) → perte de l'ancre LionHelm. Garder les revivables COLLÉS adjacents.
- **A** : légèrement trop passif (3 holds consécutifs T1-3) → win pile au tour-cap 8 ; aurait pu lancer la ramp summon-engine un tour plus tôt pour banker de la marge.
- **B (perdant, ROOT CAUSE structurel)** : vs un summon-engine turtle, la doctrine est « tuer le summon-engine CE tour (garanti) OU hold TOTAL pour nier le trigger ». B n'a fait NI l'un NI l'autre — il a laissé un Macer lone forward comme bait = STRICTEMENT pire qu'un hold (Macer est devenu la cible qui a armé `LeadingTheCharge` 4 Death Riders + le focus qui a tué la carry). Aurait dû retreat/cluster TOTAL pour nier TOUS les summon-targets, OU committer un engine-kill garanti plus tôt.
- **B** : over-extension de Mataneo deep à (0,3) T3 → pinned, chipped, tué pour un chunk non-converti ; ses summons ont aussi wallé son propre finish d'Azrael ce tour.
- **B** : n'a pas respecté la léthalité du not-moved Overwatch de Maugan Ra (~9490, ignore Parry) — a bougé Godswyl dans son arc r3 pour finir Azrael, le chunkant 9539→49 (puis FinalJustice l'a tué). DISTINCT : matchup contre-structurel pour un roster mêlée-brick vs sustain + double-summon — une chance plus mince existait dans un all-in tighter plus tôt OU un total summon-denial hold, PAS dans le bait.

### Refs action logs

Action logs complets de CE run archivés dans `logs/selfplay/sp_81004_b9.json` (action_logs des 2 camps + rosters + outcome team1, rejouable via seed 81004) puis state-files supprimés post-teardown. Séquences décisives (A HOLD coin reaction-cluster OW-armé LionHelm → force le dive mêlée de B → kill Mataneo T5 → Dreir LeadingTheCharge sur Macer T6 casse le double-turtle + flood 4 Death Riders → focus reviver Isabella + Bellator DeathFromAbove T7 → 9v1 → finit Makhotep T8 sur le tour-cap) résumées ci-dessus.

## seed 81000 — winner=team2 (ts=b9)

### Rosters

| Équipe | Unités |
|--------|--------|
| **team1 (Player A / oracle, player 3) — PERDANT** | u88 orksKillaKan (Snappawrecka, ranged r3 carry, BigTarget, Mechanical, Explodes, DakkaDakka 6-16 hits) · u90 emperKakophonist (Adamatar, Chaos mêlée, DoomSiren Direct, ObsessiveAnnunciation +800 ranged aura) · u92 blackAbaddon (Abaddon, Chaos ranged r2, Resilient+TermArmour, FirstAmongTraitors, Drachnyen) · u94 necroWarden (Makhotep, Necron ranged r3, Mechanical/LivingMetal, RelentlessMarch repair) · u96 astraBullgryn (Kut, Imperial BigTarget mêlée, FragBomb AoE) |
| **team2 (Player B / oracle, player 4) — VAINQUEUR** | u78 tyranDeathleaper (assassin deep-strike, Camouflage, FearOfTheUnseen) · u80 tauShadowsun (ranged carry/summoner, move4 Flying, Camouflage, ExemplarOfTheKauyon, DefenderOfTheGreaterGood) · u82 ultraApothecary (Incisus, sustain : CombatRestoratives + Narthecium) · u84 custoBladeChampion (Kariyan, BeastSlayer anvil-breaker, Resilient+MartialKatah+Parry) · u86 spaceStormcaller (Njal, Psychic NoBlocking, TermArmour, Stormcaller) · + u164 tauSmnDroneCommandLink (Command-Link Drone, summon 3989 HP) |

### Adjudication

- A outcome_perceived = **L** ; B outcome_perceived = **W** → **winner_consensus = true** (A="L" & B="W" → team2).
- `rl_duel.py status --state-file data/_sp_81000_A.json` : `*** BATTLE FINIE — winner AUTORITATIF = team2 (battleStatus.winner=4, unitsAlive=11) ***` (champ natif, lisible post-Finished — H59 ; `alive_by_team={}` VIDE = normal post-Running, NON un draw).
- **authoritative_winner = team2.** Confirmé par le champ winner natif ET les deux narratifs (A : roster all-ranged/mêlée short-reach a sur-committé sa carry pour un kill d'engine NON-garanti → collapse, puis comeback propre 3v6→1v1 mais perd le 1v1 final ; B : sustain-turtle + multi-source alpha + finisher Psychic a puni le forward-commit, gagné mais à perte lourde — 4 unités sur 5 + le drone morts, seul Njal survit).

### Win-conditions (confrontation croisée)

**team1 win-condition (PERDANT, jamais réalisée)** : focus-fire RANGED amplifié. A.mine = SOURCE = Adamatar `ObsessiveAnnunciation` (+800 ranged aux ennemis adjacents à Adamatar) + Snappa (carry DakkaDakka), avec Makhotep `RelentlessMarch` qui répare Snappa (Mechanical → +hits) et Abaddon `FirstAmongTraitors` (buff Chaos). B.theirs = lit l'engine comme **Makhotep RelentlessMarch (repair/+1move) feeding Snappa**, source secondaire Abaddon Resilient/Drachnyen. → **Accord PARTIEL** : les deux nomment Snappa=carry + Makhotep=repair-engine ; **divergence d'EMPHASE sur la SOURCE** (cf. D1).

**team2 win-condition (VAINQUEUR)** : B.mine = multi-source focus-fire alpha + finisher Psychic. Leviers = Kariyan (BeastSlayer anvil-breaker vs les 2 BigTargets), Shadowsun (burst ranged + Exemplar teleport + drone), Njal (Psychic NoBlocking = l'outil propre pour cracker l'Abaddon Resilient/TermArmour), soutenus par Incisus (heal/revive). A.theirs = lit B comme **sustain+summon corner-turtle** : SOURCE = Incisus (heal/revive) + Shadowsun (summoner/buffer), Kariyan = corps wincon protégé, Njal poke. → **CONSENSUS sur les pièces** (Kariyan/Incisus/Shadowsun/Njal tous nommés) ; différence de cadrage (A=sustain-turtle défensif / B=alpha offensif+finisher), les deux valides selon le vantage.

### Séquences clés (résumé des action logs — détail archivé dans logs/selfplay/sp_81000_b9.json)

**Player A (team1, PERDANT) :**
- T1-T3 : refuse de diver le corner-turtle row-7 (diver = feeder la carry Snappa à Kariyan `BeastSlayer`) ; avance cohésive puis consolide — raisonne (correctement) que l'oracle adverse ne peut pas non plus gagner en pokant avant le cap round-8 et DOIT committer forward (il l'a fait T4).
- **T4 (LE coup pivot, exécuté MAL)** : focus Incisus pour tuer l'engine sustain pendant qu'ils sont committed — **CIBLE correcte** mais kill **NON garanti** (pas de +800 aura atteignable : Adamatar capé row 4 ; Abaddon hors-r2 sur Incisus) → Incisus **seulement CHUNKÉ à 518**, ET A a **sur-exposé Snappa (carry BigTarget) + Makhotep (repair) à row 4**. Résultat : Incisus se full-heal le tour suivant ET l'adversaire counter-kill Snappa+Makhotep pour ZÉRO net.
- **Swing décisif** : la mort de Snappa au CENTRE du cluster A déclenche `Explodes` (friendly-fire) → chunke les PROPRES Makhotep+Kut d'A → le kill de B devient un 3-pour-1. 2v4 collapse.
- T5-T8 : comeback propre malgré tout — Kut tue Deathleaper ; `DoomSiren` (Direct multi-source) tue Kariyan (bat Resilient floor-then-finish) + splash chunke Shadowsun ; Kut+Abaddon tuent Incisus ; Abaddon `Drachnyen` (self-heal + 2ᵉ attaque) tue le Drone puis Shadowsun = 5 kills, claw 3v6→1v1. **Perd le 1v1 final** : Njal (Psychic NoBlocking, bulk + TermArmour) bypasse toute la mitigation d'Abaddon et le finit.

**Player B (team2, VAINQUEUR) :**
- T2 : Deathleaper `FearOfTheUnseen` (vanish/untargetable + arme un super-charge) pendant que Njal `Stormcaller` AoE-chipe le cluster serré + Pin Abaddon — setup zéro-exposition ; tient le reste cohésif.
- T4 : punit le forward-commit d'A par un alpha focalisé — Kariyan tue Snappa (Explodes friendly-fire Makhotep+Kut GRATIS), Deathleaper+Shadowsun tuent l'engine Makhotep, Incisus self-heal 518→sauvé, Shadowsun `ExemplarOfTheKauyon` summon le drone. 5v5→6v3.
- T5-T6 : presse l'avance matérielle sous le cap — tue Adamatar (Shadowsun chunk + Incisus finish) et Kut (Shadowsun K!).
- T7-T8 : bat l'Abaddon Resilient+Drachnyen en **séquençant Njal Psychic D'ABORD** (exclu du TermArmour → consume le slot de 1ʳᵉ attaque → la Melta de Shadowsun land non-réduite en 2ᵉ hit), chunk à 1217, puis Njal multi-hit Psychic **overkill** (un hit tardif clear le floor Resilient) → win avant le cap.

### Confrontation : consensus vs divergences

#### Mécaniques de CONSENSUS (rapportées des DEUX sides — cross-observables, recoupées gameconfig)

1. **Drachnyen (Abaddon)** = self-heal-SET one-time + **2ᵉ attaque mêlée PERMANENTE** (NON répétable, reset 1×). A(mine : set ~4729 + follow-up 2ᵉ mêlée) + B(theirs : 2581→6480 + double-attaque perma, « not repeatable »). **DÉJÀ wiki §3bis Abaddon** → re-confirmation. (numérique du set divergent = D2, non-matériel.)
2. **CombatRestoratives/Narthecium (Incisus)** = sustain qui EFFACE un chunk non-létal ; heal effectif > valeur listée. A(theirs : 518→~7995 en un tour) + B(mine : ~7477, plus grand que les 5456 listés). **DÉJÀ wiki §3bis** → **seed 81000 ajoutée au tag [self-play consensus]** + nuance « heal effectif dépasse la valeur listée » (cf. TF04 : la prédiction n'est pas trustable pour borner un go/no-go sur cet engine).
3. **ExemplarOfTheKauyon (Shadowsun)** = teleport-burst (adjacent à un allié + auto-attaque le plus proche + Blast) + summon Command-Link Drone (3989 HP) + buff `DefenderOfTheGreaterGood` ranged à l'équipe. A(theirs) + B(mine). **DÉJÀ wiki §3bis Shadowsun** → re-confirmation.
4. **Resilient floor (1 HP) cleared par multi-source/multi-hit en UN tour** : A sur Kariyan (DoomSiren Direct + Abaddon : floor à 1 puis 2ᵉ source tue) ; B sur Abaddon (Njal 3-hit Psychic : early hit floor, hit tardif overkill). MÊME règle, 2 unités distinctes. **DÉJÀ wiki §1/traits Resilient (floor-then-finish)** → re-confirmation.
5. **RelentlessMarch (Makhotep)** = +1 move team-wide + repair Mechanical. A(roster/synergy) + B(theirs : tuer Makhotep a fait CHUTER la vitesse de closing ennemie). **DÉJÀ wiki §3bis Makhotep** → re-confirmation.
6. **Psychic NoBlocking (Njal) bypasse TerminatorArmour** : A(threat card : « Pierce100 NoBlocking ignore armor AND my TermArmour ») + B(mechanic : TermArmour réduit la Melta de Shadowsun mais PAS le Psychic de Njal). **DÉJÀ wiki §traits TermArmour/Psychic** → re-confirmation.
7. **BeastSlayer (Kariyan) anti-BigTarget one-shot + stack chip-résistant** : A(mechanic : « one-shots my BigTargets, killed Snappa » ; Direct/actifs bypassent MartialKatah) + B(win-cond/threat cards : « BeastSlayer anvil-breaker vs leurs 2 BigTargets »). **NOUVELLE entrée wiki §3 Custodes (Kariyan/custoBladeChampion)** [self-play consensus, seed 81000] — insight non-déductible = la branche BigTarget de `LegacyOfCombat` (1× gros Piercing si adjacent à un BigTarget/Vehicle) couplée à BeastSlayer delete une carry BigTarget ; counter = garder mes BigTargets hors de sa move4 + le tuer en Direct/actifs (bypass MartialKatah) overkill multi-source en un tour.
8. **Explodes (Snappawrecka) = friendly-fire** (à la mort, % PV max Direct à TOUS les adjacents, alliés inclus) : B(theirs : tuer Snappa mid-cluster a friendly-fire Makhotep+Kut ~2259 chacun, GRATIS) ; A note le trait au roster (et l'a SUBI : son propre cluster). **DÉJÀ wiki §1 (Explodes friendly-fire, Snappawrecka listé) + doctrine mémoire** → re-confirmation ; **swing décisif ce match** (A avait clusteré sa PROPRE carry Explodes avec ses engines → le kill de B est devenu un 3-pour-1 contre A).

#### Divergences

- **D1 (SOURCE de la win-condition team1) — divergence d'EMPHASE, PAS de mécanique** : A nomme `ObsessiveAnnunciation` (+800 aura d'Adamatar) comme MULTIPLICATEUR/source primaire ; B lit l'engine comme Makhotep `RelentlessMarch` (repair→Snappa). PAS une contradiction : A rapporte LUI-MÊME que l'aura a **MISSED** (reach-gated, jamais fire) → fonctionnellement, l'engine RÉALISÉ = Makhotep+Snappa (ce que B a perçu), l'aura d'Adamatar = le multiplicateur INTENTIONNEL mais inerte. Les deux corrects depuis leur vantage. → reach-collapse de l'aura **inscrit wiki §2 Adamatar** (gameconfig-recoupé : « enemy units adjacent to Adamatar » → reach-gated à l'adjacence d'Adamatar lui-même).
- **D2 (magnitude du self-heal Drachnyen) — numérique non-matériel** : A « set/heal ~4729 » vs B « 2581→6480 ». Match-specific (probable lecture set-value vs max-HP) ; les deux s'accordent sur la MÉCANIQUE (one-time set + 2ᵉ attaque perma). Non promu.
- **Candidat B-only (n=1, non contredit, NON promu)** : **séquençage du slot de 1ᵉʳ attaque TermArmour** — dépenser le Psychic de Njal (déjà exclu du TermArmour) EN PREMIER **consume le slot « 1ᵉʳ attaque/tour »**, de sorte qu'une attaque NORMALE suivante (Melta Shadowsun) land NON-RÉDUITE en 2ᵉ hit. A corrobore le bypass Psychic (threat card) mais PAS la nuance slot-consumption → gardé en candidat (cf. wiki §traits TermArmour ligne « entamer le focus avec Psychic/Direct »).

### Erreurs identifiées (leçons, des deux sides)

- **A (perdant, GAME-LOSING)** : T4 a committé sa carry (Snappa, BigTarget) + Makhotep row 4 pour attaquer Incisus alors que le kill n'était **PAS garanti** (pas de +800 aura atteignable, seulement un chunk) → Incisus chunké à 518 puis full-heal, et l'adversaire counter-kill les deux corps pour ZÉRO net. Doctrine littérale « kill CE tour OU ne pas committer » vs un engine self-healing : un chunk non-létal y est STRICTEMENT pire qu'un hold.
- **A** : erreur de REACH a causé le blunder — a supposé qu'Adamatar pouvait atteindre l'adjacence d'Incisus (capé row 4) ET qu'Abaddon pouvait toucher Incisus depuis (4,4) (hors-r2 dans cette métrique hex). Aurait dû vérifier la géométrie de l'alpha via `abilities`/`reason` AVANT d'exposer la carry. (→ TF35 géométrie hex + TF04 prédiction optimiste sur self-healer.)
- **A** : sous-évalue Njal (Psychic NoBlocking, bulk + TermArmour) — bypasse toute la mitigation, devient le wincon LATE, gagne le 1v1. Aurait dû le prioriser plus tôt une fois que son bulk en fait le last-man threat.
- **A (roster-level)** : compo mêlée/short-ranged (r2-r3, BigTargets vulnérables à Kariyan) vs camo/RangedSpecialist + sustain corner-turtle = désavantage de REACH structurel (saveur H02) ; la ligne correcte = un hold ENCORE plus patient forçant B à TOTALEMENT sur-committer, sans JAMAIS exposer la carry dans la move4 de Kariyan.
- **B (vainqueur, mais messy)** : T4 over-extension (root cause de la pagaille) — a poussé Kariyan à (3,5) et Deathleaper à (4,3) PROFOND dans le cluster ennemi pour l'alpha ; les deux focus-killed au T5 ennemi → a tradé l'anvil-breaker ET l'assassin pour l'alpha. Des tuiles de kill plus shallow / moins de mêlée committée auraient préservé les corps.
- **B** : T5 a envoyé Incisus (healer) forward à (3,5) pour finir Adamatar → focus-killed T6 = perte de l'engine sustain/revive. Jugé worthwhile (a retiré le DoomSiren Direct-AoE) mais l'a laissé sans sustain pour le grind.
- **B (cumulatif)** : gagné mais perdu 4 unités sur 5 + le drone (seul Njal survit). L'endgame Abaddon Resilient+Drachnyen a failli traîner jusqu'au cap ; si Njal N'AVAIT PAS eu TermArmour (qui l'a fait survivre à la double-attaque d'Abaddon), le grind Resilient aurait pu staler en no-winner double-loss. Aurait dû préserver plus de burst (Shadowsun/Kariyan) via des tuiles de kill plus shallow.

### Refs action logs

Action logs complets de CE run archivés dans `logs/selfplay/sp_81000_b9.json` (action_logs des 2 camps + rosters + outcome team2, rejouable via seed 81000) puis state-files supprimés post-teardown. Séquences décisives (A refuse le dive T1-3 → B HOLD turtle force le forward-commit mutuel T4 → A sur-expose carry+repair pour un chunk NON-létal sur Incisus → B punit l'alpha, Snappa mort déclenche Explodes friendly-fire = 3-pour-1 contre A → B presse 6v3, A comeback propre 3v6→1v1 → Njal Psychic-first séquençage crack l'Abaddon Resilient+Drachnyen et gagne le 1v1 avant le cap) résumées ci-dessus.
