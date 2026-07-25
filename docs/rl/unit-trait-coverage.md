# Couverture des `UnitTrait` (traits d'unites spawnables)

Pendant de l'audit `DamageTrait` (traits de profil de degat). Etabli 2026-07-24 (build `gqfc5mff6c`),
recon offline `scratchpad/unit_traits_recon.py` + `unit_traits_classify.py`.

## Catalogue = COMPLET (mirror 1:1)

- Enum `engine/entities/traits/unit_trait.py` = mirror natif `UnitTrait` (dump.cs TypeDefIndex 24364, ~110 valeurs).
- **Aucun** trait porte par une unite gameconfig n'echappe a l'enum (`[A]` vide) -> meme garantie que `DamageTrait`.
- **61 traits distincts** reellement portes par au moins une unite (pools spawnables : lineup=123, npc=481, summons=65).
- 42 membres enum ne sont portes par personne (moot : Amphibious, Burrow, Dragon, Elemental, Mounted, Polearm,
  Ranged[le trait, distinct du damage-profile], Xenos, ...).

## Cablage : 40/61 references, 21 sans aucune trace (no-op certain)

Signal = reference `UnitTrait.X` (symbolique) OU string literal du nom dans `engine/`. Un trait reference n'est
pas forcement PLEINEMENT wire (il peut l'etre partiellement, via l'ability/effet qu'il accorde OU en direct-read),
mais un trait SANS aucune reference n'est PAS forcement un no-op.

> **ANGLE-MORT trait-level (identifie #73 Terrifying, 2026-07-24)** : le signal « reference du NOM de trait » ne capte
> que le cablage DIRECT-READ (`HasTrait` lu dans le calcul). Un trait cable via le **chemin EFFET** (17.17 pt1 : le trait
> ACCORDE une triggered ability qui pose un effet) n'apparait PAS en reference de nom -- c'est l'EFFET/l'ability qui est
> reference, pas le trait. Donc « 21 non-references » = « 21 non-direct-read », dont certains sont DEJA cables via effet
> (Terrifying #73, deja porte+valide) et d'autres sont de VRAIS gaps effet-path non portes (SuppressiveFire #74). Classer
> chaque « non-reference » exige de verifier l'ability/effet ACCORDE (`TRAIT_DERIVED_ABILITIES` / `TRAIT_TRIGGERS`), pas
> seulement le grep du nom.

### Direct-read damage-math confirmes cables (traits/ hierarchie + services)
`GetStuckIn` (bonus hits), `MkXGravis` (x2 armure, #178), `Resilient`/`Impervious` (caps service),
`HeavyWeapon`/`Emplacement` (LasCannon pierce, #71 en cours), `IndirectFire`, `Steppable` (selecteurs/mouvement),
`Immune` (fire/displace/tiles), `BigTarget` (displace/extra_damage), `Vehicle`/`Summon` (extra_damage),
`CloseCombatWeakness`, `ContagionsOfNurgle`, `Ambush`/`Decoy`/`Hero` (genestealer), `Camouflage` (#59).

### Les 21 traits PORTES mais JAMAIS references -> classes par semantique i2

**A. Gaps DAMAGE-MATH direct-read (vrais gaps moteur, mirror-ables)** :
- ~~`Terrifying`~~ **RESOLU #73 (mergé 9cf5e40) -- EFFET-based, PAS direct-read (premisse refutee)** : trait 34 -> TriggeredAbility 98
  -> pose `Terrifying_ExtraDefense` (melee recu x0.70, magnitude gameconfig `terrifyingBonus=-30`). Etait DEJA porte+cable ;
  2 correctifs de fidelite (magnitude config au lieu du hardcode 30 + seeding factory). Valide bit-exact eldarMauganRa. Reclasse
  hors direct-read (exemple canonique de l'ANGLE-MORT ci-dessus).
- `TwoManTeam` (x6, npc/summons) : "max 50% max HP d'un seul coup (hors Blast) ; plus de heal >50% une fois sous 50%"
  -> **cap par-coup** cote cible = famille `trait_damage_limits` (Resilient/Impervious). Port facile (service existant).
- `Diminutive` (x4, npc/summons) : "reduit les attaques multi-hit de {hitsReduction} coup, min 1" -> **reducteur de
  nombre de coups** cote cible (direct-read).
- `BeastSnagga` (x1, npc) : "+{extraDmgPct}% degat melee vs BigTarget/Vehicle + {blockChance}% block" -> attacker
  damage bonus conditionnel + block (direct-read). Rare (1 carrier).
- ~~`ThrillSeekers`~~ **RESOLU** (`case-thrillseekers`) : le trait 1056 ACCORDE l'ability triggered 1444 (arbre DSL)
  -> pose/refresh l'effet *Thrilled* 1434 = +15 CritChance pour `TurnsFromRounds(1)`, sur
  `On(PreAttackHit) & IsFirstHitInSeries & OwnerIsCaster & Not(IsWounded(target))` OU `On(DamageTaken) & OwnerIsTarget`.
  Feuille DSL + `TRAIT_TRIGGERS` + les 2 vecteurs d'event (6 / 0xf) qui manquaient. Valide live bit-exact sur les 2
  porteurs spawnables (branches, refresh, contre-cas cible-blessee, expiration). RESIDU : le rider overkill-au-crit
  (face PREDICTION `PredictAttackRaw`) reste non porte -> `backlog.md`.
- `Invincible` (x20, npc-only) : pas de desc i2 -> semantique a confirmer (immunite degat probable = cap 0). A RE avant port.

**B. On-hit / on-death effet (applique un effet, pas un scalaire)** :
- ~~`SuppressiveFire`~~ **RESOLU #74 (mergé 6256e97)** : le trait ACCORDE SuppressiveFireAbility (arbre DSL) -> pose
  Pinned/Suppressed (1065) on-ranged-attack. Effet Pinned deja porte ; feuille DSL + `TRAIT_TRIGGERS`. Valide live tauDarkstrider 3/3.
- ~~`LetTheGalaxyBurn` (x33)~~ **VOLET 1 RESOLU #84** : le trait 1058 accorde la triggered 1482 et porte
  l'owner-effect 1477. `LetTheGalaxyBurnEffect.CreateAdditionalHits @180f54e30` = **+1 coup d'ARME**
  (canal `create_effect_hits_bonus_for_attack`, count node NULL, profil -1 -- canal MasterAnnihilator,
  PAS le canal heterogene FleshmetalGuns), gate `OwnerIsCaster & (TargetHasTileEffect | IsPersistentData)`.
  Pose du flag = `On(PreAttack=5) & Maybe(33%) & !HasTileStatusEffect(cible)` @1811076f0 ; clear en fin
  d'attaque @1811078a0. Valide live (34.2 % / 100 % sur les 2 branches). Cf. `case-84-let-the-galaxy-burn.md`.
  **VOLET 2 RESTANT** : `AddEffect(0x5c4=1476 DespoiledGround)` sur les tuiles des cibles (+ 1478
  `DespoiledGround_ExtraDamagePct`) -- le spawn hex-effect.
- `Explodes` (x15) : "explose a la mort, 25% max HP en Direct Damage aux adjacents" -> death-nova (cf. HarbingerOfDestruction
  1008 porte #44 ; verifier si le TRAIT wire l'ability ou si c'est un gap).
- `PutridExplosion` (x6) : idem Explodes en Toxic, epargne DeathGuard adjacents.

**C. Selecteur / mouvement / deploiement (hors damage-math ; certains deja traites/bloques)** :
- `Infiltrate` (x47) : "ne declenche pas d'Overwatch" -> gate selecteur overwatch. **Intersecte #70** (untargetable/Infiltrate en cours).
- `MachineOfWar` (x22) : abilities laterales MoW -> **#54** (blocker harness headless, connu).
- `TeleportStrike` (x33) : Deep Strike (position de depart) -> couche deploiement/positionnement.
- `Unstoppable` (x31) : ne s'arrete pas sur hexes speciaux pendant le mouvement -> regle de pathing (displace/move).

**D. AI-policy / synapse / meta (hors moteur de degat)** :
- `InstinctiveBehaviour` (x23) : politique de ciblage AI hors synapse (DROPPED, cf. memoire instinctive_fatigue).
- `Synapse` (x32) : "amis a <=2 hex ignorent Instinctive + BattleFatigue" -> contre Instinctive/Fatigue (aura AI/effet).
- `PrioritisedEfficiency` (x7) : effet per-tour selon la stance (complexe, effet/AI).
- `Boss` (x6), `PermaDeath` (x4), `NonAttacking` (x2) : flags meta/campagne/AI, pas de math de combat.

## Priorisation port (combat-math, valides spawnable)
1. ~~Terrifying~~ **FAIT #73** (effet-based, deja cable ; correctifs fidelite).
2. ~~SuppressiveFire~~ **FAIT #74** (feuille DSL + TRAIT_TRIGGERS ; Pinned).
3. **TwoManTeam** (x6) - cap 50%/coup dans trait_damage_limits (direct-read confirme -> #75 mirror-offline).
4. **Diminutive** (x4) - reducteur multi-hit cote cible (direct-read -> #75).
5. **A re-trier sous l'angle EFFET-PATH** (cf. ANGLE-MORT) avant de conclure « gap » : `BeastSnagga`, `ThrillSeekers`,
   `Invincible`, + death-nova `Explodes`/`PutridExplosion`/`LetTheGalaxyBurn` (#76) -- verifier l'ability/effet accorde.
5. `LetTheGalaxyBurn` / `Explodes` / `PutridExplosion` (death/additional-hit), `BeastSnagga`, `ThrillSeekers`, `Invincible` (a RE).
