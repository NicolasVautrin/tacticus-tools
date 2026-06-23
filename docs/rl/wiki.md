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
>
> **Cartes tactiques** — chaque unité (§2/§3) et trait (§1) porte une ligne de synthèse scannable :
> `▸ Tac: [rôle=engine|carry|anvil|control|chaff] · menace=critical|high|med|low (contexte) · counter=<1-ligne> [n=X]`
> (rôle pour les unités ; les traits = menace+counter). C'est de l'**APPRIS** — ça **évolue** et est
> **contextuel** (dépend de mon roster) → **distinct des FAITS KIT** (gameconfig/i2-vérifiés, la prose ci-dessus/dessous).
> Échelle de menace = poids wincon : `critical` = décide le combat si non traité (engine/carry/anvil dur) ;
> `high` = burst/contrôle majeur ; `med`/`low` = gérable/chaff. Maintenue par la synthèse depuis le
> feedback combat (`threat_cards`). **Recon = LIRE ces cartes côté ennemi → la plus haute menace = leur wincon.**

- **`Resilient` × multi-hit / × focus** : Resilient ramène à 1 PV au lieu de mourir (sauf
  Overkill) — la règle est sur l'**ÉTAT de PV**, pas sur la source : le 1ᵉʳ coup létal met
  à 1 (Resilient fire **une fois**), tout coup **SUIVANT du même tour** trouve « déjà à 1 »
  et **tue**. **Adjudiqué par i2** : la précondition Resilient est « **If this unit is not already
  at 1 Health** and would be defeated, its Health is instead reduced to 1, unless Overkilled » → au
  1er hit létal (PV >1, non-overkill) Resilient fire → 1 PV ; au hit SUIVANT (PV DÉJÀ à 1) la
  précondition échoue → Resilient ne peut PAS re-trigger → 1→0 mort. S'applique donc identiquement au
  **multi-hit d'un seul actif** (Kharn `KillMaimBurn` 8 coups, Macer `JakhalStimms` 4, **Angrax
  `BringerOfDespair` 4+4** vérifié seed 95002 : Yarrick 570 PV Resilient → 1er hit floored à 1, 2e hit
  tue) ET au **focus de PLUSIEURS attaquants distincts** (vécu : Nauseous 10337 PV tué en un tour par
  Shiron+Sarquael+Re'vas). Vérifié : des tanks Resilient (Trajann, Yarrick) tués en un seul actif
  multi-hit. Resilient ne protège donc PAS d'un burster multi-hit (≥2 hits dans l'actif) **ni d'un focus
  multi-source** — garder un moteur Resilient un rang DERRIÈRE les corps plus tanky, jamais cible la plus
  proche. ⚠ Caveat exécution : un actif **single-hit** affiché « K! » sur un Resilient ne tue PAS (floor
  à 1) — il faut ≥2 hits, ou une 2ᵉ source, ou l'Overkill (cf. §1 K!/H04). ⚠ **Floor-then-finish par
  N'IMPORTE QUELLE source >0, summon-DoT inclus** : une fois floored à 1 (la save ne fire qu'UNE fois,
  condition « not already at 1 Health »), l'unité n'a plus AUCUNE protection → tout hit suivant ≥1 dmg tue,
  y compris une **auto-attaque de summon de 1 dmg** (vérifié seed 70005 : mon Lucien Resilient floored à 1
  par le focus Aesoth+Volk au T1, puis tué par un hit Poxwalker de 1 dmg tagué [dot] — un summon-DoT/auto-attaque
  suffit à finir un Resilient déjà floored ; côté offensif comme subi, ne JAMAIS laisser un Resilient floored
  vivre un tour, le moindre chip l'achève).
  `▸ Tac: menace=high · counter=multi-hit (≥2 hits) dans UN actif / overkill (>2× PV restants) / focus multi-source / DoT — ne survit PAS à ça [n≥5]`
- **`FinalJustice`** (TRAIT, alias affiché « Final Vengeance ») : à la perte du dernier PV, l'unité
  fait **immédiatement UNE attaque normale** sur une cible éligible puis meurt — **sauf Overkill**
  (Overkill = défait par un Crit OU dégât du coup létal > 2× PV restants). La riposte utilise l'arme
  d'attaque normale du porteur (ex. Ragnar = 7× Chain → riposte 7 hits, ~1419 vérifié ; vérifié seed 93001 :
  Ragnar tué EN RÉACTION par une chaîne Shiron → ses 7 hits Chain ~281 chacun ont fire sur l'Apothecary).
  **Trigger SOURCE-AGNOSTIQUE** : fire **même stunné**, **même tué par AoE/killzone**, **même tué par une
  riposte/Overwatch** (mort = trigger, pas action ; le texte i2 ne fait AUCUNE exception sur la source du
  coup). Pour le supprimer : **chunk puis overkill** (le coup final dépasse 2× les PV restants). Porteurs :
  Kharn, **Ragnar (spaceBlackmane)**, **Dante (bloodDante)**, **Gulgortz (orksWarboss)**,
  **Azrael (darkaAzrael)**, **Thoread (templAncient)**, Trajann, Helbrecht, Winged Prime…
  (n>1, plusieurs porteurs). Vérifié : killzone tue Kharn à
  1113 pile → FinalJustice tue Trajann adjacent ; Ulf overkillé (WasOverkill=1) → AUCUNE riposte ;
  **Dante (seed 95000)** tué par Maugan Ra → riposte normale = son arme **4× Piercing (Pierce80)** =
  4 hits (~242+204+245+223 ≈ 914) sur l'attaquant le plus proche (Abaddon), peu importe le tueur (mort
  = trigger, pas de condition de source ; Overkill non exercé ici). **Confirmé seed 97002** : Winged
  Prime (porteur trait 1014) tué par une **normale mêlée Ragnar NON-overkill** → riposte = sa normale
  ~6 hits sur Aesoth adjacent (mort = trigger, source-agnostique ; le chip était évitable par overkill).
  **Re-confirmé seed 70006 (Winged Prime, n+1)** : tué à EXACTEMENT ses PV restants (1627 dealt, `WasOverkill=0`)
  → FJ a fire (`IsActingBeforeDeath=1`) et a fait une normale qui a choisi ma **Judh (230 PV)** adjacente et l'a
  TUÉE. ⚠ **La cible FJ suit la PORTÉE D'ATTAQUE NORMALE du porteur, PAS une contrainte d'adjacence dure** (i2 =
  « eligible target ») — l'adjacence observée reflète juste que Judh était à portée de sa normale, pas une règle
  d'adjacence ; un fragile DANS la portée normale du porteur est un candidat FJ. ⚠ **Le label K! ne warne PAS** :
  il sommait les hits bruts = exactement les PV restants (kill exact ≠ Overkill, >2× requis) → overkiller
  (>2× PV restants) OU finir au RANGE sans fragile à portée de sa normale.
  ⚠️ **CAS GULGORTZ (orksWarboss,
  vérifié seed 95001)** : sa riposte FinalJustice n'est PAS une simple attaque normale — son attaque
  normale (mêlée Eviscerate Pierce50) **déclenche automatiquement le passif `LightImUp`** (2ᵉ volée 3×
  Projectile Pierce15 r3, hits restants redistribués à un ennemi aléatoire ≤3 hex) → sa mort = **double
  volée mêlée + ranged** sur les adjacents (vécu seed 95001 : 2× Eviscerate 902+991 + LightImUp 190 = 2083
  sur Aun'Shi déjà chunkée, a contribué à sa perte au tour suivant ; **confirmé seed 95002** : Gulgortz
  3197 PV tué par une normale Dante NON-overkill → FJ Eviscerate 754+824 + LightImUp 3× Projectile 160 =
  1738 = **kill exact de Dante** par la chaîne de mort ; **confirmé seed 70009** : Gulgortz 3933 PV tué par
  Tanksmasha NON-overkill (4520 > 3933 mais < 2×) → FJ volée mêlée 1598+1416 (Passive_Ability_Type=1024) +
  LightImUp 3-hit ranged 0[bloqué]+261+262 (Passive_Ability_Type=1103) = ~3537 sur le Tanksmasha adjacent,
  n=3). ⚠ LightImUp **chaîne automatiquement** la posthume FJ car il se déclenche « after performing a normal
  attack » → FJ exécute une attaque normale → LightImUp s'enchaîne dessus. Donc overkiller Gulgortz est encore
  plus impératif que pour un FinalJustice « plat ».
  ⚠ **3 VOIES POUR NIER FJ (confirmé seed 70057, 4 carriers gérés)** : (a) **Overkill** (coup létal >2× PV
  restants — confirmé verbatim i2 « unless Overkilled » : Helbrecht 9539 overkillé multi-source Mataneo 7984 +
  drone 1555 `Attack_WasOverkill=1` → FJ NON déclenchée) ; (b) **kill SANS eligible target à portée de sa
  normale** : la riposte FJ exige une cible éligible — un kill où aucun ennemi n'est à portée de la normale du
  porteur fait FIRE le trait (`IsActingBeforeDeath=0`) mais résout en **no-op ZÉRO dégât** (confirmé : Dante tué
  à (3,4) sans adjacent éligible → 0 dmg = la seule « free kill » sur Dante hors Overkill) ; (c) **router la
  riposte sur un corps ARMURÉ/tank** si le porteur a une normale faible-pen : Ragnar FJ = 7× Chain **Pierce20**
  (weak armor-pen) → ~232-333/hit (~1946 total) sur Mataneo armuré Mechanical = trivial (confirmé seed 70057 ;
  cohérent §1 Ragnar 7-hit). DOCTRINE : overkiller les FJ à riposte forte (Dante Pierce80, Gulgortz double-volée),
  router la riposte faible-pen (Ragnar Pierce20) sur un body armuré, ou tuer hors-portée-de-la-normale.
- **`Explodes` / `PutridExplosion`** : explose à la mort, **25% des PV MAX** en dégâts (Direct pour
  Explodes ; Toxic Pierce70 pour PutridExplosion, sauf Death Guard) à TOUS les **adjacents — y compris
  les unités ALLIÉES** (friendly fire, pas de filtre ami/ennemi). Vérifié sur Morvenn (2385 sur alliés
  adjacents), **orksKillaKan/Snappawrecka** (2259 sur 2 ennemis adjacents + mon propre Mataneo — donc
  exploitable : tuer un Explodes au CENTRE d'un cluster ennemi = AoE gratuit sur eux), **necroSpyder/
  Aleph-Null** (vérifié seed 98002 : fini au RANGED, Abraxas Psychic r2, pendant qu'Anuphet + un Necron
  Warrior étaient adjacents → l'Explodes les a friendly-fired GRATIS — i2 « all adjacent units », aucun
  filtre faction ; ⚠ DOUBLE-TRANCHANT re-vérifié seed 70005 : Aleph-Null **dans MON roster** tué par Abraxas
  → l'explosion a frappé l'Aesoth ENNEMI adjacent 759→0 KILL MAIS AUSSI mes propres TG 2259 + Typhus 2259
  adjacents → ne JAMAIS coller mes unités à mon propre Explodes s'il peut mourir ; positionner pour que son
  splash ne touche QUE des ennemis), **Pestillian/deathPutrifier** (Toxic aux adjacents, finir au RANGED pour ne toucher aucun
  allié + chiper l'ennemi adjacent gratis). NB Pestillian a aussi Resilient → le coup final doit Overkill/être
  un 2ᵉ hit pour qu'il meure et déclenche l'explosion. **Exploit canonique** : tuer un Explodes positionné au
  centre d'un cluster ennemi DEPUIS LE RANGE → AoE gratuit sur tous ses voisins, zéro coût, et mes fragiles
  hors adjacence.
- **`BattleFatigue`** (Guardsman + la plupart des NPC/summon-trash : Cadian Guardsman, Ripper Swarm,
  Grot…) : quand un allié est **défait dans un hex ADJACENT**, **%-chance** que le porteur **fuie et
  soit retiré du combat** (+% supplémentaire si la défaite était un **Overkill**). **Adjacency-gated ET
  probabiliste** : seuls les VOISINS du défait roulent ; les porteurs non-adjacents ne sont pas affectés.
  Se déclenche sur **N'IMPORTE QUELLE mort d'allié adjacent** (pas seulement celle du summoner). Vérifié
  seed 95002 : à la mort de Yarrick, le Guardsman u154 (adjacent) a fui (`UnitFled`, retiré), u156
  (non-adjacent) non. ⚠ probabiliste → une seule fuite observée ne prouve PAS que l'adjacence FORCE la
  fuite ; c'est un roll. **Tactique** : overkiller une unité d'un cluster de trash BattleFatigue adjacents
  peut **chain-rout** les voisins (réduit le board ennemi gratis). Les Grots amis de Snotflogga **ignorent**
  BattleFatigue (exception kit, §3bis).
  `▸ Tac: menace=low · counter=N/A (c'est un trait ENNEMI exploitable) · exploit=overkiller une mort au CENTRE d'un paquet de trash BattleFatigue = roll de fuite sur chaque voisin → peut vider un flanc de chaff [n≥1]`
- **Repairing/Healing = cleanse PARTIEL** : restaure les PV ET retire l'ensemble curable de débuffs
  négatifs — **Taunted, Suppressed, Markerlight, Stunned** ET les débuffs **MindControl** (les deux
  sous-effets `MindControl_OutgoingDamageReduction`/`_IncomingDamageBonus` + le Taunt, retirés ensemble)
  (PAS tous : la regen/`Restore` n'en retire AUCUN — distinction Heal/Repair vs Regen). Repairing marche
  sur Mechanical ; Healing a le même cleanse mais **aucun effet sur Mechanical**. → tout actif repair
  (ex. Actus `DefendTheDivineWork`) sur un allié Markerlighté **neutralise** le setup TwinSmartMissile/
  Markerlight T'au ; un heal Apothecary (`CombatRestoratives`) sur un allié MindControlled le **cleanse**
  (vérifié seed 93001). Les changements d'effet ne flaggent PAS `mutated`. Vérifié.
- **Blast / faible PiercingRatio vs armure** : dégât **live ≪ chiffre brut gameconfig**
  (armure). Vérifié : Morvenn `SanctorumMissile` « 2×2183-3056 Blast » → **1686** réel
  sur Kharn armuré. Les actifs Blast/low-pierce **ne sont pas des finishers** vs armure.
- **Stun / `Stunned`** (effet engine, source ex. `VexillaMagnifica` ; **retiré par Healing/Repairing**) :
  ⚠ **NE bloque PAS toutes les actions** (correction i2 source-de-vérité, line 16100 `Stunned_Description`
  / Keywords `UnitEffect_Stunned` : « only 1 Movement, deals -X% Damage and cannot use active Abilities.
  Healing or repairing removes the effect »). La cible stunnée **garde 1 Movement**, peut **toujours faire
  son ATTAQUE NORMALE** (ex. id=69) mais à **dégâts réduits**, et perd **UNIQUEMENT les ACTIVE abilities**
  (UI « Blocked by Stunned »). Ses **triggers de mort restent** (FinalJustice cf. supra). ⚠ **Ne PAS
  `endturn` d'office une unité stunnée** — elle conserve 1 move + son attaque normale (un `mutated=False`
  observé sur TOUTES ses actions = artefact runner n=1, PAS la sémantique du Stun). **Tactique de l'attaquant** :
  une unité-clé sur-étendue et stunnée garde 1 move mais ne peut pas réellement retreat hors d'une killzone
  mêlée (1 move ≪ besoin) → reste un kill quasi-garanti si forward, mais ce n'est pas un lock total.
- **`LegendaryCommander` + `StandVigil`** (Trajann/Vexilus) : un **actif allié adjacent**
  à un ennemi → cet ennemi +800 dmg subi (+2 hits pour les Characters alliés s'il est
  aussi adjacent à Trajann) + buff StandVigil. Vérifié : ouvre/booste un focus (Trajann
  2118-3180 → 4749-4902). ⚠ **Le trigger fire pour l'équipe qui CONTRÔLE Trajann** : quand
  c'est MOI qui possède Trajann, user un de MES actifs adjacent à un ennemi applique le +800
  à cet ennemi (vérifié seed 70009 : Patermine a usé MightFromBelow adjacent à Tarvakh →
  LegendaryCommander_ExtraDamage appliqué à Tarvakh, e=85 ReceiveEffect from Trajann e=95,
  Effect_SourceTriggeredAbility=1310). gameconfig : « Enemies receive +800 Damage if they are
  adjacent to any friendly unit that has used an active ability this turn ».
- **Overkill** : killing blow dépassant les PV restants par un seuil **STRICT = dégât > 2× PV
  restants** (i2 Keywords/Overkill VERBATIM : « if the damage of the attack that defeats it is **more
  than double its remaining Health**, the unit is Overkilled ») → nie Resilient ET FinalJustice/
  TheBetrayer death-riposte. ⚠ **Dépasser les PV restants NE SUFFIT PAS** — il faut > 2× : vérifié
  seed 98001, un coup ~3900 sur un Kharn à **2399 PV** (ratio ~1.6×, < 4798) **n'a PAS overkillé** → la
  death-riposte TheBetrayer (4× Eviscerate) a fire et tué un Grot adjacent + chunké Mataneo. Pour
  overkiller Kharn à 2399 PV il fallait **> 4798 dmg**. Budgétiser une marge >2× PV restants, pas juste
  « assez pour tuer ». `▸ Tac: pour nier FJ/death-riposte sur un porteur (Kharn/Gulgortz/Ragnar…), le coup
  létal doit dépasser STRICTEMENT 2× les PV restants OU être un Crit — sinon stacker chip+gros-finisher [n=1, 98001]`
- **`Steppable`** : l'unité est **détruite si on MARCHE DESSUS ou si elle est endommagée**,
  mais **ne peut PAS être ciblée** (absente des plans d'attaque). → pour la retirer :
  `act move --to <son hex>`. Porté par les decoys (`genesSmnDecoy`). Vérifié gameconfig.
- **`Ambush`** : trait → effet `Ambush_CanResurrect`, **1× SEULEMENT**. À la **1ʳᵉ mort**
  (toute première défaite, pas seulement overkill), l'unité laisse un **decoy** (Steppable) ;
  au début de son prochain tour, si un decoy ami **survit**, elle **ressuscite plein PV** sur
  un decoy au hasard et **agit immédiatement** (Characters ressuscitent avant les non-Characters).
  Le **2ᵉ kill est PERMANENT** (effet consommé). → kill **temporaire** tant qu'un decoy survit ;
  résurrection niée **uniquement si AUCUN decoy ami ne survit** → **détruire les decoys** (marcher
  dessus / les endommager) avant/au moment du kill. ⚠️ **Judh (genesKelermorph)** empile **2
  sources de decoy** (HypersensoryAbilities-sur-attaque + Ambush-à-la-mort) → retirer un seul decoy
  ne suffit pas, il faut **clear TOUS** les decoys amis pour rendre le kill définitif. Porté par :
  Genestealers (genesBiophagus, genesKelermorph, **genesMagus**…). ⚠ **C'est un TRAIT** (lu via la carte
  unité ; `--ability Ambush` renvoie « inconnue »). Vérifié n=3 sur **genesMagus (Xybia)** (seed 70014 +
  93001 + 98001) : 1ʳᵉ mort → decoy (genesSmnDecoy HP0) + resurrect full au début de son prochain tour sur un
  decoy ami random (agit immédiatement ; les Characters ressuscitent avant les non-Characters) ; **2ᵉ kill =
  PERMANENT, peu importe combien de decoys restent** (seul le PREMIER trigger ; vérifié seed 98001 : 2ᵉ mort =
  `RemoveUnit WasOverkilled=1`, AUCUN decoy, AUCUN revive — le 2ᵉ kill est permanent **indépendamment de
  l'overkill**). Donc si je ne peux pas clear le decoy, accepter le kill temporaire et planifier la 2ᵉ mort
  (réaction/focus du tour suivant).
- **`TerminatorArmour`** : SEULE la **1ʳᵉ ATTAQUE/tour** subie est réduite (gameconfig
  `terminatorArmourDmgReduction=-75` → −75%, soit 25% du dmg), **SAUF profils Psychic/DirectDamage**
  (gameconfig `terminatorArmourExcludedDmgProfiles=Psychic,DirectDamage` → exclus ENTIÈREMENT = passent
  à plein **même en 1ʳᵉ attaque**) ; immunité Suppress. ⚠️ Le compteur « 1ʳᵉ attaque » est un **compteur
  GLOBAL par tour (n'importe quel attaquant)** qui se reset après le 1ᵉʳ attaquant, peu importe qui frappe
  ensuite. Gaté par « attaque » (un multi-hit d'une SEULE arme = une attaque réduite) : **toute attaque
  DISTINCTE après la 1ʳᵉ ce tour-là tape à plein** → NE protège PAS d'un focus multi-attaquant soutenu :
  un TerminatorArmour SANS Resilient peut être supprimé en un tour-équipe (vérifié : Baraqiel 11044 PV tué
  par un focus 12-hits sur une tuile danger-5 ; vérifié seed 70001 : Njal — 1ʳᵉ attaque Dante 4-hit normal
  réduite à 418, puis Jain Zar 4828 + Azrael 2786 full → mort en un team-turn). **Counter** : étaler les
  attaques sur 2+ unités le même team-turn (seule la PREMIÈRE est pénalisée), OU ouvrir avec un Psychic/
  Direct (bypass total), OU « gâcher » la 1ʳᵉ attaque avec un coup faible jeté en premier.
  Porté par : blackAbaddon, blackTerminator, darkaTerminator (Baraqiel), worldTerminator (Wrask),
  spaceStormcaller (Njal), **thousTerminator (Toth)**.
  `▸ Tac: menace=med · counter=Psychic/Direct passe à plein ; sinon focus multi-attaquant (la 2ᵉ attaque distincte du tour tape plein) ou "gâcher" la 1ʳᵉ attaque avec un coup faible [n≥4]`
  `▸ Tac (AoE-Psychic bypass, n+1) : un seul cast Psychic AoE (Typhus PlagueWind, Pierce100 NoBlocking) passe à PLEIN sur TOUS les targets de la chaîne (primary + adjacent + further-adjacent) même si plusieurs sont TermArmour — l'exclusion Psychic/Direct s'applique par-hit, pas une seule fois (vécu seed 70059 : PlagueWind a touché Ragnar 3914 + TG 3154 + Maladus 2432 simultanément, full damage, malgré TermArmour actif sur TG/Maladus). Doctrine : vs un MUR de 2-3 anvils TermArmour groupés, un Psychic AoE est l'outil de bris optimal (1 cast = 3 chunks pleins) [n=1, 70059]`
- **`TimeFlux`** (passif **thousTerminator « Toth »**) : la **1ʳᵉ mort de Toth par combat**, si son time
  ghost est sur le board → il **revit** au hex du ghost (PV scale au niveau, **~2400 base**, observé ~4487 à
  niveau plus haut). **Fire même sur Overkill** ET sur une mort en réaction/cascade (vérifié seed 98002 :
  Toth tué dans une cascade de réactions a ressuscité ~4487 PV, la 2ᵉ mort Abraxas Psychic fut permanente).
  **2ᵉ mort = PERMANENTE** (one-per-battle). **Doctrine : toujours budgéter une 2ᵉ source de kill ; traiter
  Toth comme s'il avait 2 barres de vie.** ⚠ le ghost se relocalise à chaque move de Toth (un seul ghost à la
  fois, invalidé si l'hex devient occupé/impassable, cf. H25) → si je contrôlais Toth je le bougerais UNE seule
  fois pour poser un ghost sûr. `▸ Tac: budget 2ᵉ kill obligatoire ; le finisher permanent = la 2ᵉ mort [n=1, 98002]`
- **`Terrifying`** : réduit UNIQUEMENT les dégâts de **MÊLÉE** subis. **Bypass fiable = RANGED**
  (vérifié : Thaddeus Blast ranged tue la Terrifying Atlacoya proprement). ⚠️ l'armor-ignore/
  perforant/Direct **NE bypasse PAS** Terrifying (ce n'est pas un mécanisme d'armure) — une mêlée
  même Direct/Pierce100 reste réduite. Porté par : Mephiston, Dante, Azkor, Atlacoya, Tjark, Deathleaper…
- **`Psychic` (PiercingRatio 100 + NoBlocking) = bypass définitif des cibles Mechanical blindées**
  (confirmé seed 98003) : un profil d'arme Psychic à **100% pierce** ignore TOUTE l'Armure, et le trait
  **`NoBlocking`** (« Cannot be blocked », i2 DMG_Psychic) bypasse le Block. Les **DEUX couches** d'un stack
  défensif Mechanical sont donc nettement bypassées. ⚠️ `NetherRealmCasket` (Necron) ne réduit que la
  **Crit Damage** (−par Mechanical adjacent), PAS le dégât flat → un hit Psychic **non-crit** est totalement
  non mitigé. Le trait `Mechanical` lui-même n'a **aucune réduction de dégât innée** (juste repair-only au
  lieu de heal). ⇒ une source Psychic NoBlocking (ex. Sibyll `PsychicMaelstrom`) délivre **plein pot** à un
  noyau Mechanical haut-Armure type Aleph-Null/Vanguards-sous-Protector (vérifié : 6866 en un cast,
  9037→2171). Doctrine : **réserver le Psychic NoBlocking pour les engines blindés (repair-hub/summon-engine
  Mechanical sous +582 armure), pas le chaff** — c'est souvent le SEUL bypass d'un stack Mechanical+armure.
- **`TeleportStrike`** (deep strike) : l'unité démarre en deep strike — **intouchable
  jusqu'à ce qu'elle AGISSE ou termine son tour**, donc la protection est **TURN-1 ONLY**
  (consommée dès le 1ᵉʳ `endturn`, même si l'unité n'a rien fait). Le téléport pose sur
  **tout hex libre NON-adjacent** à un ennemi → **pas d'attaque à l'arrivée** (« tour de
  gap »), ou move normal depuis sa position. **Doctrine (non-dérivable, vécu seed 33182) :**
  – **redéploiement one-shot** → **ne PAS le « garder en réserve »** : il expire turn 1
    inutilisé (gaspillé), et l'unité doit ensuite traverser le plateau **à pied** ;
  – **ne JAMAIS le projeter seul en avant** → isolé au contact, il se fait **focus down
    au tour adverse AVANT d'avoir agi** (tour de gap) — c'est exactement comme ça que Wrask
    est mort ;
  – vrai usage = **tempo pour une unité LENTE** (sauter la traversée) **+ infiltrer un
    flanc / backline** inatteignable (contourner l'écran ennemi), **UNIQUEMENT s'il survit
    au tour de gap** : atterrissage hors de portée / terrain / **arriver en GROUPE supporté**
    (jamais en cible isolée) ;
  – **asymétrie de survie** : viable pour un terminator très tanky que l'adversaire ne peut
    pas punir (Baraqiel projeté seul en (1,4) a **survécu** — aucune réponse à un terminator),
    **fatal** sinon (Wrask projeté pareil → tué par le ranged/psychic concentré).
  – ⚠️ **AUTO-FINISH d'un deep-striker MÊLÉE (confirmé seed 98003)** : le téléport pose obligatoirement sur
    un hex **NON-adjacent** à un ennemi (i2 TeleportStrike : « any free hex … not adjacent to an enemy »).
    Or un deep-striker dont l'actif est **melee-init** (SwoopingHawk d'Aethana, charge LightOfSanguinius
    de Dante = range≤5 depuis la position) n'a **AUCUNE cible atteignable à l'arrivée** → le teleport-move
    **auto-finit l'unité** (ActionsAvailable=0, zéro attaque possible, cf. H08/H09). La contrainte
    d'atterrissage et l'init-mêlée sont **mutuellement exclusives le même tour** → un deep-striker mêlée
    NE PEUT PAS délivrer d'alpha sur un cluster lointain au tour du téléport ; le manual teleport-move le
    **strande solo** = focus-kill gratuit. ⇒ NE PAS dépenser un deep-striker mêlée tant qu'un alpha
    soutenu (charge en portée + auras stackées + co-fire du ranged) n'est pas posable le **même tour** ;
    le garder shallow+groupé. (Les deep-strikers à actif **RANGED** — Baraqiel PlasmaCannon — ou un
    move-normal-depuis-la-position avec cible mêlée adjacente PEUVENT agir après déploiement.)
  Porté par : worldTerminator (Wrask, cf. §2), darkaTerminator (Baraqiel), **eldarAutarch (Aethana,
  melee SwoopingHawk → auto-finish), bloodDante (Dante, LightOfSanguinius charge)**.
  `▸ Tac (bloodDante « Dante » — deep-strike Terrifying carry, LightOfSanguinius 5× Melta + −30% dmg debuff aura, LordOfTheHost +655 mêlée aux alliés Flying/RapidAssault, FinalJustice overkill-to-suppress) : rôle=carry · menace=high · counter=ne PAS lui présenter un fragile ISOLÉ à sa charge (Terrifying réduit la MÊLÉE → il tanke la mêlée cheap, bypass = RANGED §1) ; s'il dive un cluster GROUPÉ il se fait focus-killer en réactions (vécu seed 98002 : dove solo dans mon cluster screené → mort en réactions enemy-T1 ; vécu seed 70001 : chunké via Azrael DarkTalonStrike line-splash 1189 + Jain Zar SilentDeath adjacency 7846→5558 + Nicodemus chip → tué en RÉACTION quand il a dive ma held-line, sa FinalJustice riposte ABSORBÉE par mes forward units Terrifying/TerrorsLament) ; Overkill pour nier FinalJustice [n=2, 98002/70001]`
  `▸ Tac (n+1 FJ-no-eligible-adjacent + dive-forward-punished, seed 70057 W, confirmé Verif) : Dante a dive forward solo move4 à (3,4) T3 (over-commit) → focus-killé depuis tuiles SHALLOW (drone Sho'syl + Mataneo + Abraxas Psychic qui bypasse Terrifying). ⚠ **2ᵉ free-kill path sur Dante (en plus de l'Overkill)** : tué SANS eligible target adjacent à portée de sa normale → FinalJustice a fire (`IsActingBeforeDeath=0`) mais ZÉRO dmg (no-op, cf. §1). 9035 PV soft → le tuer où il a dive isolé = gratuit + supprime son LordOfTheHost amplifier ; Psychic/RANGED bypasse son Terrifying. DOCTRINE = punir le dive forward de Dante depuis le shallow, le tuer hors-portée-de-sa-normale OU overkill [n=3, +70057]`
- **`Overwatch`** (trait ou armé par un actif type EarlyWarningOverride) : **gate = NOT-ATTACKED, PAS
  not-moved** — l'unité peut **bouger PUIS armer l'Overwatch** ; tant qu'elle n'a pas fait d'attaque NORMALE
  ce tour, elle riposte quand un ennemi **bouge dans sa portée** au tour adverse (vérifié seed 98000 :
  Maugan Ra a bougé T1 et l'a quand même armé). **Chaque ennemi entrant en portée = une riposte SÉPARÉE**
  → un dive mêlée/summon qui fait entrer ses unités UNE PAR UNE prend un hit par mover (cascade de KILLs
  possible). ⚠️ **pas d'overlay live des zones armées** (GAP, cf. §6 TODO) → éviter au flair / exploiter
  l'angle mort IA. Porté par : darkaAzrael ; armé par : tauCrisis (Re'vas), Maugan Ra…
  ⚠️ **Amplificateur LionHelm (Azrael, range 2, vérifié seed 70001)** : les alliés à ≤2 hex d'Azrael font
  **+437 dmg sur LEURS PROPRES attaques déclenchées par Overwatch** → grouper plusieurs Overwatchers/contre-
  attaquants autour d'Azrael transforme un dive ennemi en **reaction-kill multi-source boosté** (vécu : 11510 dmg
  de réactions, 2 kills, sur le dive Godswyl+Dante). Coupler avec le HOLD d'Azrael (ne pas attaquer = OW armé) +
  une ligne groupée = la moitié RÉCIPROQUE de H03 portée par le boost.
  `▸ Tac: menace=high (vs roster mêlée/move-in ; un dive séquentiel se fait décimer 1 riposte/mover) · counter=ne PAS pather dans l'arc ; out-range ; Infiltrate/Teleport pour skip ; ou forcer l'OW sur un chaff d'abord [n≥2]`
- **`Parry`** : réduit les attaques **multi-hit** subies de −1 hit (min 1) → mes multi-hit
  sont moins efficaces contre lui. Porté par : templHelbrecht.
- **`Taunt`** (effet, variantes `Taunted_*`) : force la cible à **attaquer le taunter**.
  La variante **`Taunted_BlockMovement`** l'**immobilise** (0 hex) ; `Taunted_CantUseAbility`
  lui coupe ses actifs ; un taunt « must-attack » l'empêche aussi de **heal/summon** (elle
  DOIT taper le taunter). **Usage-clé = LOCK** pour les abilities « tir retardé, dégâts
  réduits par hex parcouru » (railgun `HeavyRailRifle`, cf. §4) : une cible taunted **déjà
  adjacente** au taunter ne bouge pas → tir à plein pot au tour suivant. ⚠️ si le taunter
  est **LOIN**, la cible **marche** vers lui pour l'attaquer (= mouvement) → le lock ne
  sert plus au railgun ; il faut que le taunter soit **collé** à la cible AU MOMENT du
  lock. Sources observées : **Jaeger `HolyDuel`** (taunt **mutuel, sans expiration**,
  bloque le mouvement + coupe les actifs — verrouille un engine adjacent), **les Grots de
  Snotflogga** (`GetEmRuntz`/`SquigHound` : le Grot **summon adjacent à la cible** et la
  Taunt avec `BlockMovement` → lock **immédiat**, sans avancer une de mes unités).
  Vérifié : Apothecary HolyDuel-locké → railgun quasi plein (3563) = kill propre de
  l'engine ; **Baraqiel non locké** → il a bougé → railgun **1876** (gâché).
- **Attaque normale = id CONCRET par unité** (fait outil/moteur, non dérivable des chiffres) :
  l'attaque normale est un `ActiveAbilityType` **propre à chaque unité** (lu live via
  `NormalAttackType` / decisionView), **JAMAIS** l'abstrait `NormalAttack=17` ni l'id d'une autre
  unité (`69=Loki_NormalAttack` n'appartient qu'à Loki). Passer un id étranger/abstrait **no-op
  silencieusement** (`mutated=false`, **aucune erreur**) → un coup avalé peut gâcher un kill (vécu :
  un Aberrant a perdu son hit qui tuait le TyrantGuard). **Pièges fréquents** : les **summons**
  (ex. Aberrant : Physical melee propre + auto-attaque Summon) et les **Mechanicus** (ex. Actus =
  admecManipulus, dont le seul actif est `DefendTheDivineWork=1117`, PAS une attaque normale).
  Règle : toujours passer l'id normal **concret** de la vue live et **vérifier `mutated=true`**.
  **Détails moteur (i2 Keywords/UnitEffect_Taunted)** : une cible Taunted **ne peut QUE
  cibler/attaquer le taunter**, ne peut PAS s'éloigner, PAS user son actif, **PAS heal/repair** ;
  les attaques **non ciblées (AoE/untargeted) peuvent quand même toucher d'autres** ;
  **Healing (ou Repair pour Mechanical) RETIRE le Taunted**.
- **`play --spec` / `act move` — format de `to` = array d'entiers, JAMAIS un string** (fait
  harness/outil, vérifié par code seed 95000) : le champ `to` d'une action move DOIT être un array
  JSON d'entiers `[col,row]` (ex. `[5,3]`), **jamais** le string `"5,3"`. Un string est indexé
  positionnellement (`to[0]="5"`, `to[1]=","`) et atteint le `writeS32` de Frida en non-entier →
  **ERR `build: expected an integer`** ; le message n'est jamais construit donc **`mutated=false`**,
  mais le slot d'action de la boucle est **silencieusement consommé** (la boucle par-action a déjà
  avancé). Effet identique à ne pas agir → un move raté en string cascade : tous les actions suivants
  du même spec échouent. **Toujours passer des arrays d'entiers ; vérifier `mutated=true` avant de
  chaîner les abilités sur un move critique.**
- **`MindControl`** (genesMagus, range 3, cible un ennemi adjacent à ≥1 allié) : pour CE round
  et le suivant (**2 rounds**) l'ennemi déale **−582** dmg, subit **+20%** dmg, et devient
  **Taunted par l'allié adjacent au PLUS HAUT PV courant**. Combo `Taunted_BlockMovement` +
  `Taunted_CantUseAbility` + `MindControl_OutgoingDamageReduction(−582)` +
  `MindControl_IncomingDamageBonus(+20%)`. Counter-play : la cible contrôlée DOIT taper le
  taunter — router sa frappe forcée vers le **finish d'un bas-PV qu'on veut tuer** (mettre ce
  bas-PV comme l'allié-adjacent-au-plus-haut-PV pour baiter), ou neutraliser une grosse menace
  2 rounds. Vérifié : Mephiston taunted bridé à 15-1221 dmg → frappe forcée routée sur le finish
  du taunter (Magus). **2ᵉ confirmation (Atlacoya, seed 93001)** : le `Taunted_CantUseAbility` coupe
  l'ACTIF de la cible — sur Atlacoya il neutralise `TalonsOfTheEmperor` (l'attaque Direct anti-Psyker,
  justement l'outil censé tuer le Magus) et ne lui laisse que son attaque NORMALE, forcée sur le taunter
  (allié adjacent au plus haut PV). Donc taunter via une unité collée à la cible-à-finir route la frappe
  forcée sur ce finish ; à l'inverse, taunter via le Magus lui-même fait taper le Magus. Le débuff de dmg
  (`MindControl_OutgoingDamageReduction −582` + `MindControl_IncomingDamageBonus +20%`) est **curable** :
  per i2 UnitEffects/MindControl_Description, tout **Healing OU Repair** retire l'effet (les deux
  sous-effets d'un coup ; vérifié : Apothecary `CombatRestoratives` sur Atlacoya = `RemovedNegativeUnitEffects=2`).
- **`ContagionsOfNurgle`** (porté par Nauseous/deathRotbone, Maladus/deathBlightlord, Corrodius/deathBlightbringer) :
  aura centrée sur le porteur qui **DEBUFFE l'armure des ennemis dedans** — **−20% Armour (1 aura)** ou **−40% Armour
  (2+ auras Contagion qui se chevauchent)** (valeurs exactes gameconfig). **S'étend par round** : range 1 (rounds 1-2)
  → range 2 (rounds 3-4) → range 3 (round 5+). Cible les ENNEMIS exclusivement (jamais d'ambiguïté allié). Tag d'effet
  live observé : `ContagionsOfNurgle_ArmorReduction1` = palier 1-aura (vérifié seed 70052 : les ennemis près de mon
  Nauseous ont pris l'effet → l'aura s'étend et tague bien les ennemis). → empiler 2 porteurs Contagion sur le même
  cluster ennemi double le strip d'armure (−40%) ; complémentaire d'un finisher Power/Pierce vs un cluster armuré.
  `▸ Tac: menace/valeur=med · counter=à MOI = l'utiliser comme softener d'armure avant un burst Pierce/Power (empiler 2 auras = −40%) ; côté ennemi = ne pas stationner mes unités dans l'aura si je crains un burst ennemi armor-augmenté, mais l'effet reste positionnel/lent (range 1 early) [n=1, 70052]`

---

## 2. Units CHAOS (kits & interactions — faits neutres)

> Description objective du kit (vaut quel que soit le camp qui la joue). Le « quoi
> faire pour/contre » est doctrine générale (skill §6/§7).

- **Kharn (worldKharn, 9035, move3 mêlée)** — `KillMaimBurn` (actif **range 2**,
  8 coups = 1 Pierce + 6 Eviscerate + 1 Plasma ≈ 11-15k). `RapidAssault` (+1 move
  jusqu'à sa 1ʳᵉ attaque = **move 4** ; +dmg 1ʳᵉ attaque & suivantes du tour).
  `TheBetrayer` (si a tué un ennemi ce combat → au **DÉBUT de chaque tour de Kharn**, auto-move
  **jusqu'à 2 hex** vers l'unité la plus proche puis **4× Eviscerating Damage (Pierce50)** sur un
  adjacent ; privilégie les ennemis mais **frappe un ALLIÉ si aucun ennemi à portée** ; +2ᵉ attaque 4×
  Eviscerate après chaque normale). **Conséquence : une fois « amorcé » par un kill, Kharn devient une
  menace récurrente garantie de 4 hits/tour SANS action dépensée** (vécu seed 96001 : après kill de
  Godswyl T1 → a tué le Shield Drone u153 puis chunké Toth ~3522 en début de tour, en cascade).
  `BlessingsOfKhorne` (+dmg/−Psychic cumulé par kill mêlée). `FinalJustice` (à la mort : 1 attaque
  normale, sauf Overkill). **Pas Resilient.** Stun neutralise sa burst un tour.
  `▸ Tac: rôle=carry · menace=high · counter=le tuer AVANT son 1er kill (TheBetrayer non-amorcé sans kill = juste une normale absorbable ; une fois amorcé = snowball auto move+4-hit/tour + BlessingsOfKhorne) ; ranged/délai (SeekerMissile a fini Kharn 6298+4534) ; pas Resilient → tout K! franc le défait hors-FJ ; ⚠ OVERKILL STRICT pour nier FJ/TheBetrayer death-riposte = dégât **>2× PV restants** (vécu seed 98001 : Snotflogga chunk 9035→2399 puis Mataneo ~3900 NON-overkill (ratio 1.6×) → TheBetrayer 4× Eviscerate a FIRE, tué mon Grot + chunké Mataneo ; il fallait >4798) ; ⚠ NE PAS finir Kharn avec un de mes héros forward (Mataneo deep-finish à (2,5) → focus-killé) — préférer l'auto-Grot/une unité shallow, OU le laisser non-amorcé à bas PV (TheBetrayer dort sans kill) [n=2]`
  `▸ Tac (n+1 dive-punish, seed 70060 W) : confirmé tué EN RÉACTION sur son dive AVANT son 1er kill = TheBetrayer JAMAIS armé → réduit à une normale absorbable, le snowball mort-né. Un mur de réaction « hold-baits-the-dive » (Re'vas EarlyWarningOverride Overwatch-turret + Sarquael GrimRetribution held-OW) l'a one-turn-tué en réactions (~5594 OW : 3264+2330) avec ZÉRO kill scoré — un ennemi all-melee est CONTRAINT de diver dedans. Pas Resilient → tout K! franc le défait ; overkill >2× PV restants si on finit au range (déni FJ/TheBetrayer death-riposte, cf. §1 Overkill). Carte KIT exacte [n=3, 98001/98002/70060]`
  `▸ Tac (À MOI — carry burst + death-riposte value, seed 70059 W mais COÛTEUX) : KillMaimBurn = chaîne 3-hits "prioritise kills" — sa structure (1 Pierce adjacent → 6 Eviscerate même cible jusqu'au kill → 1 Plasma range-2) fait que le K! du primaire SPILL le 3ᵉ hit Plasma sur la cible SUIVANTE (vécu : K! le Tyrant Guard 6025 ET splash Ragnar 3226 dans le même cast). Death-riposte = grosse valeur quand il meurt ADJACENT à un anvil chunké : FJ normale (sauf Overkill) → TheBetrayer 4× Eviscerate déchargent ensemble (vécu : Kharn tué par Maladus → riposte 6481 sur Maladus, 9615→1935 = setup d'1-shot next turn). ⚠ LEÇON COÛTEUSE : committer Kharn (mon MEILLEUR carry) forward pour K! un ANVIL NON-engine (TG) l'a fait focus-killer = perte du carry ; un anvil-killable ne vaut PAS un carry forward → préférer tuer l'engine au range / sacrifier le corps le PLUS expendable, pas Kharn. SI Kharn doit mourir, l'orienter adjacent à un anvil chunké (death-riposte ~6481) plutôt que dans le vide [n=1, 70059]`
- **Abaddon (blackAbaddon, 10038, move3, ranged r2 + mêlée)** — `Drachnyen` (actif :
  **SET les PV à 4729** (i2 vérifié : « set to 4729 Health », **plafonné à son max PV** — donc
  set-à-4729 seulement si 4729 ≤ max, PAS un heal au-delà du max) + une attaque normale mêlée
  immédiate ; **PERMANENT pour le reste du combat** : après CHAQUE attaque normale mêlée, Abaddon
  refait une **2ᵉ attaque (3× Piercing Pierce80, ~873-1091/hit @lvl65)** sur un ennemi adjacent →
  il double-frappe en mêlée à vie. Vérifié seed 95001 (chunk Gulgortz 10040→2592 en une activation ;
  la chaîne auto-tape un adjacent — ⚠ « 2ᵉ attaque sur un ennemi DIFFÉRENT du primaire » = n=1 non
  prouvé, i2 ne dit que « an adjacent enemy unit » → cf. H21). `FirstAmongTraitors`
  (+364→+1313 dmg aux Chaos alliés à portée 2, scale par attaque). `Resilient`.
  `TerminatorArmour` (1ʳᵉ attaque/tour subie réduite, **sauf Psychic/Direct**).
  `▸ Tac: rôle=anvil · menace=high (Resilient + TerminatorArmour + Drachnyen self-heal-to-4729 + FirstAmongTraitors buffe les Chaos adjacents) · counter=RANGED multi-source floor-then-finish — Resilient floor any non-overkill lethal hit à 1 HP, un 2ᵉ hit DEPUIS 1 HP = kill propre (non-overkill, WasOverkilled=1) ; PRÉFÉRER le ranged pour finir (ne PAS le mêler librement : Drachnyen est une riposte OFFENSIVE, chaque normale mêlée d'Abaddon génère une 2ᵉ attaque 3-hit Piercing → meleer dedans = absorber la double-attaque) ; Psychic/Direct bypasse TerminatorArmour ; FirstAmongTraitors devient quasi-INERTE si son bénéficiaire Chaos adjacent principal meurt → le démoter et le laisser pour la FIN (vécu seed 70053 : FirstAmongTraitors mort avec Archimatos → Abaddon laissé T7, fini via Snotflogga chunk 5976→772 → Calandis floor-to-1 → Shiron finish, RANGED multi-source, zéro Drachnyen riposte) ; priorité APRÈS les engines/le duo OW (vécu seed 95000 : a survécu tout le match faute de focus) [n=2, 95000/70053]`
- **Corrodius (deathBlightbringer, 12551, move2 mêlée)** — `ContagionsOfNurgle`
  (aura : −armure aux ennemis dedans, **s'étend** r1→r2→r3 par round). `Poxwalkers`
  (actif : **summon** Poxwalkers 2183 PV qui attaquent direct). `CursedPlagueBell`
  (Chaos alliés dans l'aura +1 move ; **Psykers ennemis dans l'aura s'auto-blessent
  1310** à chaque attaque Psychic). `Resilient`.
  `▸ Tac: rôle=control/summoner · menace=med (tank LENT move2 12551 Resilient : menace surtout POSITIONNELLE/attrition — aura Contagion −armure croissante r1→r3 + Poxwalkers summon 2183 attaquant direct + CursedPlagueBell) · ⚠ **COÛT PSYKER** : un Psyker À MOI dans son aura Contagion s'auto-blesse à CHAQUE hit Psychic (i2 base 1310, scale niveau → ~1795 observé) → COMPTER ce self-damage avant de spammer du Psychic dans son aura ; acceptable sur un gros corps (Typhus 12k) mais à budgétiser, idéalement frapper depuis HORS aura ou le tuer/en sortir (vécu seed 70005 : a coûté ~1795 à mon Typhus sur son cast anti-Trajann) ; ⚠ ses Poxwalkers finissent un Resilient floored (un hit summon de 1 dmg tué mon Lucien floored à 1, cf. §1) · counter=Resilient → multi-hit (≥2)/Overkill ; move2 LENT → kitable ; menace positionnelle, pas une priorité de kill devant les engines/carries ; ⚠ n+1 (vécu seed 70054 : Corrodius-mirror = DERNIER ennemi debout, move2 SLOW → kité puis grindé 12551→0 via multi-source depuis un 9v1 ; ses Poxwalker summons (757-2992) = chaff trivialement K!'d ; un Resilient devant 6 attaquants = overkill trivial) → confirme : menace d'attrition/positionnelle, à laisser pour la FIN derrière les engines/anvils focusables ; ⚠ **n+1 (vécu seed 70061, CONTRIBUTING ROOT CAUSE) — un Resilient 12k JAMAIS COMMENCÉ À CHIPER = garanti un-finished au round cap** : je l'ai laissé sitting alive comme un clock et le combat a atteint le round-10 cap (EnvEndBombardment mutual wipe → no-winner) AVEC Corrodius encore plein. NUANCE CONTRE 70054 : « laisser pour la fin » ne vaut QUE s'il n'y a PAS de hard round cap ; quand un cap existe, un anvil Resilient 12k doit être COMMENCÉ tôt (multi-hit grind round 5-6) — sinon il devient le clock qu'on perd. Le kiter/ignorer indéfiniment est une LOSS si le board ne se ferme pas avant le cap [n=4, 96001/70005/70054/70061]`
- **Macer (worldJakhal, 9035, move3 mêlée)** — `JakhalStimms` (actif : 4×~2600
  multi-hit + splash, **−25% PV du lanceur**, **ne finit PAS son tour**).
  `Skullsmasher` (+126 dmg / 10% PV manquant → plus fort à bas PV ; + Stun si a
  déjà tué). `BlessingsOfKhorne`, `Resilient`.
- **Pestillian (deathPutrifier, 12047, move2 mêlée)** — `PutridExplosion` (**explose
  à la mort**, Toxic aux adjacents sauf Death Guard). `FoulInfusion` (actif : +2037
  Toxic aux Chaos de l'aura ce round+suivant, puis attaque). `ExplosiveMaladies`
  (buff Blast aux adjacents ; cibles tuées par ces attaques **toujours overkillées**).
  `ContagionsOfNurgle`, `Resilient`.
  `▸ Tac: rôle=anvil · menace=med (menace surtout POSITIONNELLE : aura Contagion −armure + explosion Toxic à la mort + buff Blast adjacents) · counter=le tuer au RANGED (PutridExplosion = Toxic AoE aux adjacents → ne JAMAIS coller mes unités) ; Resilient → multi-hit (≥2) ou Overkill (sinon floor à 1, le coup final ne déclenche pas l'explosion) ; move2 lent → kitable (vécu seed 96001 : n'a pas attaqué activement, trop loin/engagé) [n=1]`
  `▸ Tac (n+1 ContagionsOfNurgle attrition CONFIRMÉ self-play consensus, seed 80000) : aura live = **ArmorReduction1** (portée R1-2=1, R3-4=2) observée des DEUX côtés — A (theirs, observed ChangeStats −armure sur Atlacoya/TG/Exitor entrant dans la portée) + B (mine, FixedArmor_Modification négatifs confirmés sur u97/u95). Impact quantifié : Atlacoya 8032→2307 HP sur 2 tours d'exposition aura + attaques ennemies. DOCTRINE : **ne JAMAIS avancer des melee-units dans la portée de l'aura sans plan de kill-en-un-tour** — l'attrition est garantie dès qu'une unité ENTRE dans la portée ; reculer dès que l'aura couvre sa tuile. [self-play consensus, seed 80000]. [n=2, 96001/80000-sp]`
- **Wrask (worldTerminator, 9537, move2 mêlée, 4× Flame OnFire)** — **brawler / ANVIL
  Khorne, PAS un assassin.** `BloodyFury` (actif : 1× Chain à un adjacent **+1 hit par
  fois que Wrask a été ATTAQUÉ ce combat** (max 8) ; surplus alloué aux adjacents,
  priorise les kills) → **il VEUT être focus** : sa frappe **scale avec les coups subis**.
  `WrathfulDevotion` (passif : shield **2910 PV** à lui + Chaos adjacents, **à l'arrivée de
  deep-strike OU à chaque kill mêlée**, 1 round). `BlessingsOfKhorne` (+dmg / −Psychic subi
  **par kill mêlée**, cumulé). `RapidAssault` (+1 move jusqu'à la 1ʳᵉ attaque ; 1ʳᵉ +
  suivantes du tour +dmg). `TeleportStrike` (deep strike = **outil de POSITIONNEMENT**, pas
  un snipe : drop sur tout hex libre non-adjacent, non-ciblable jusqu'à ce qu'il agisse),
  `TerminatorArmour`, `Unstoppable` (cf. §1). **Doctrine : le déployer TÔT au FRONT** comme
  anvil (encaisse le focus à la place des fragiles) + empiler hits-subis (BloodyFury) et
  kills mêlée (Khorne + re-shield). **NE PAS le planquer** « pour assassiner » : anti-synergie
  totale — caché = 0 hit subi = BloodyFury à **1 coup** (vécu rematch seed 33182 : sorti
  tard → frappe minable ~2484).
- **Archimatos (blackPossession, 8034, move3, ranged r2 + mêlée, Psychic 100 NoBlocking)** —
  summoner. Psychic NoBlocking = **ignore armure/block**. `Incursion` (actif r2) : spawn
  1 Bloodletter (2837 PV / 1601 dmg) à la fois sur la cible, **jusqu'à 6 TANT QUE la cible
  n'est pas tuée** (+ reste à r2 + a un hex libre adjacent). **C'est un FARM de corps, pas
  un kill** : pour décrocher les 6 (≈ **17k PV de board**), viser un **gros-PV en ESPACE
  DÉGAGÉ** qui survit aux 6× ~1601 ; sur du **chaff/bas-PV la cible meurt après ~2 spawns →
  seulement 2 Bloodletters** (vécu seed 67827 : Incursion sur Neophyte 2992 → 2 seulement).
  **Éviter un Resilient comme cible** (un Bloodletter overkill le 1-PV → défait → la boucle
  stoppe). ⚠ **Ne pas farmer sur un tank à AoE/aura de zone** (Typhus `PlagueWind` +
  `DestroyerHive`, Corrodius) : les Bloodletters collés à lui se font **AoE en retour** →
  choisir un sponge sans AoE, ou accepter le trade. `Possession` (passif) : kill **mêlée**
  → Bloodletter dans le hex de la victime ; kill **ranged** → Blue Horror (2619 PV) → donc
  **finir au ranged = +1 corps gratuit**. ⚠ **Possession ne fire que quand Archimatos est le TUEUR**
  (l'acteur), PAS quand il est la VICTIME : le tuer LUI avec MON unité = **zéro Possession body** (il
  ne déclenche jamais son propre passif sur sa mort) → priorité = l'éliminer T1-T2 avec mon unité avant
  qu'il summon. `Psyker` (sur attaque ranged normale, splash %dmg
  à un ennemi adjacent à la cible), `LetTheGalaxyBurn` (cf. §1).
  `▸ Tac: rôle=engine · menace=high (summon-farm Bloodletters + body-par-kill) · counter=le tuer AVANT son PREMIER cycle de summon (T2 au plus tard) AVEC mon unité (il est la victime → AUCUN Possession body spawné) ; soft (8034, pas Resilient), Psychic NoBlocking mais base faible → focusable T1-T2 (vécu seed 67827 : Mephiston move-rider + normal l'a one-shot une fois chunké ; vécu seed 96002 : éliminé T2 via FGL Pinned Burchard + JakhalStimms Macer AVANT tout summon ; vécu seed 70008 : Exitor CordClaw 4× Direct Pierce100 l'a one-shot 8034→0 T2 pre-summon, aucun body ; vécu seed 70053 : Snotflogga normal multi-hit l'a one-shot 8034→0 T4 EN TANT QUE VICTIME → ZÉRO Possession body confirmé live + breaking-the-summoner-cheaply = pas de body spawné) [n=4, 96002/70008/70053]`
  `▸ Tac (À MOI — summon-engine + double-hit normal, seed 70059 W) : les Bloodletters d'Incursion SCALENT au-delà du tooltip (live ~3888 HP / ~1608 dmg vs base 2837/1601 ; level/rarity) et auto-attaquent la cible AU SPAWN (~1608/hit immédiat) → utiles comme chair-à-trade/écran. ⚠ NE PAS les summoner pour qu'ils divent dans des anvils Resilient/TermArmour (valeur limitée à du chip) — préférer un hex où ils ÉCRANENT ou farment un sponge. Sa NORMALE ranged = bursts à 2-hits : LetTheGalaxyBurn (chance d'extra-hit) + PsykerExtraAttack splash à un adjacent de la cible (vécu : double-hit 2758+2412 = 5170 sur Abaddon en un cast, a contribué à overkill un Resilient). USAGE À MOI = soft Psyker NoBlocking → garder shallow+écrané (c'est MON engine fragile), ouvrir Incursion sur un sponge, finir un Resilient avec son double-hit (Pierce100 bypasse TermArmour) [n=1, 70059]`
- **Abraxas (thousInfernalMaster, Thousand Sons, ranged r2 + mêlée, Psychic Pierce100 NoBlocking)** —
  caster/summon-engine. `MasterOfTheTutelaries` (actif) : cible un **HEX LIBRE adjacent** à Abraxas (PAS
  un ennemi → `--target` un ennemi renvoie `mutated=false` ; cibler via `--to col,row`) ; summon **1 Pink
  Horror** (thousSmnPinkHorror, 2619 PV / 655 dmg) immédiatement, PUIS jusqu'à fin de tour, **CHAQUE fois
  qu'un ennemi subit du Dégât Psychic, summon 1 Screamer de Tzeentch** (thousSmnScreamer, 3274 PV / 1310
  dmg) sur hex libre proche d'un ennemi. Les summons **attaquent immédiatement** une cible à portée mais
  **ne peuvent pas se déplacer** ce tour. → coupler avec une chaîne de dégâts Psychic (Psyker splash,
  Patriarch MightFromBelow…) cascade les summons (vécu seed 96000 : 1 PinkHorror + 2 Screamers qui ont
  fourni les kills DÉCISIFS en réaction — Farseer, Nauseous, Typhus). Trait `Psyker` (cf. §1) : sur une
  **attaque RANGED normale uniquement** (pas les actifs), inflige **+50% des dégâts de l'attaque à un
  ennemi ALÉATOIRE adjacent à la cible** (psykerExtraDmg=50 ; vécu : tir sur Farseer → splash 904 sur
  Nauseous adjacente). Psychic NoBlocking = ignore armure/block.
  `▸ Tac: rôle=engine · menace=high (summon-cascade via dégât Psychic + Psyker splash multiplie les hits Psychic → snowball de Screamers) · counter=le tuer TÔT avant qu'il monte une chaîne Psychic ; soft (Psychic NoBlocking mais base fragile, PAS Resilient) → un burst franc le défait, et un assassin anti-Psyker (Tjark HuntersBeyondDeath +582 vs Psyker) le chunke 7026→784 en UN hit (~6242) puis finition triviale = réponse propre vs Abraxas-ENNEMI (vécu seed 98001) ; à MOI = engine de réaction décisif (MasterOfTheTutelaries + Psyker splash = burst de réactions massées qui finit les wincons adverses, vécu seed 96000 ; ranged-finish via Psychic = bypass armure + free body si Possession-class) ; ⚠ re-confirmé engine SOFT défait par une CHAÎNE DE RÉACTIONS (vécu seed 70005 : Abraxas-ENNEMI tué par Ulf SavageKiller en réaction 4249→0 quand il a dive adjacent — MasterOfTheTutelaries JAMAIS cast, mort avant ; 7026 no-Resilient = un seul gros hit de réaction le défait, le tuer TÔT avant la cascade Psychic ; vécu seed 70006 : Abraxas-ENNEMI a summon u199 (immédiatement tué par mon Guardsman) puis chunké par réactions Guardsmen et fini par une K! de la normale multi-hit de Volk — WeaverOfFate jamais armé car jamais 3+ de mes units prenant du Psychic → nier ses cibles Psychic l'empêche d'escalader) ; ⚠⚠ **NE JAMAIS CHIPER NON-LÉTALEMENT (vécu seed 70052 triggered-against-me)** : Abraxas-ENNEMI chippé NON-létalement (Snappa seul 7026→3183) a CASTÉ MasterOfTheTutelaries → +1 Pink Horror +2 Screamers = board-flip qui a scellé la loss. Pas de seuil de PV : tout Abraxas survivant cast → un poke à une seule source qui ne peut pas one-shot un 7026 est strictement PIRE que le hold (« kill CE tour garanti ou hold total pour dénier le trigger », cf. doctrine-learned §6 summon-engine) [n=5, 96000/98001/70005/70006/70052]`
  `▸ Tac (n+1 kill-not-chip APPLIQUÉ, seed 70060 W) : ✅ règle kill-not-chip RESPECTÉE = ZÉRO board-flip — Abraxas-ENNEMI (soft 7026, no-Resilient) tué en UN tour T3 via un burst multi-source GARANTI (Sarquael Supercharge 6366 + Aun'Shi normale + Trajann normale, total vérifié > HP AVANT de committer) → erasé 7026→0 AVANT tout cast MasterOfTheTutelaries = AUCUN Pink Horror/Screamer. Contraste positif net avec 70052 (chip non-létal → board-flip). PLAY confirmé : lead avec un nuke ranged (Supercharge no-move = HeavyWeapon +dmg) sur l'engine soft, puis séquencer 2 normales melee pour garantir le kill le MÊME tour [n=6, 96000/98001/70005/70006/70052/70060]`
- **Ahriman (thousAhriman, move3, Flying, Psyker)** — `Doombolt` (1102, actif Ranged r2, Psychic
  **Pierce100 + NoBlocking = ignore armure/block**) : 3 hits 873-1164 **répartis ÉQUITABLEMENT sur
  TOUS les ennemis dans 2 hexes** → frappe multi-cibles (overkill une cible chunkée ET softening d'un
  voisin dans le même cast), +1 hit/hex En Feu (max 9), et **se recharge** si Ahriman tue avec son tir
  normal après l'avoir déjà utilisé. `WeaverOfFate` (tout tour où **3+ ennemis** subissent du Psychic →
  Ahriman fait le dégât **MAX** sur toutes ses attaques/abilités ce tour ; un AoE Psychic multi-cibles
  peut s'auto-armer). `PsychicStalk`, `Psyker`. ⚠️ Dans une **aura Nurgle (Corrodius CursedPlagueBell)**
  il s'auto-blesse 1310/hit Psychic → un Doombolt 3-hit = ~3930 self-damage (vérifié seed 91008 : tué
  cheap ainsi). Le tuer tôt = nuke armor-ignore neutralisé.
  `▸ Tac: rôle=engine · menace=med · counter=Psyker fragile (8032, no-Resilient) = 2ᵉ engine de snowball Psychic (Doombolt armor-ignore AoE + WeaverOfFate) → le tuer TÔT ; un anti-Psyker (Roswitha CondemnorStake +2183 vs Psyker, Tjark HuntersBeyondDeath) le delete proprement ; ⚠ ne PAS deep-dive pour le chasser — laisse-le venir : s'il dive une ligne groupée, le free-kill arrive en RÉACTION (vécu seed 70002 : Roswitha CondemnorStake 4551 KILL GRATUIT en réaction quand l'Ahriman ennemi a dive) [n=1, 70002]`
- **Tarvakh (worldExecutions, mêlée snowball carry)** — `MurderousSwing` (1137, Melee, Piercing **Pierce80**
  → mange l'armure/overkille) : 1 hit à **TOUS les ennemis adjacents** ; **+1746 dmg UNIQUEMENT si le
  cast touche exactement 1 ennemi** (toucher 2+ troque le bonus contre le spread). ⚠️ usage-unique/
  no-refresh observé live (n=1, H13) — pas dans gameconfig. `BlessingsOfKhorne` (+dmg / −Psychic subi par
  kill mêlée), `TrophyTaker` (+dmg vs cibles ≤50% PV), `RapidAssault`. **Pas Resilient → fragile au focus
  réaction** (vécu seed 93001 : mort dans ma chaîne de counters).
  `▸ Tac: rôle=carry · menace=high — **CRITICAL si TwistedScience-pumped** (un Hollan/Biophagus le pompe à ~12.5k : 9537→12529 vécu seed 97001) ; snowball par kill (BlessingsOfKhorne +dmg/-Psychic, TrophyTaker +dmg vs ≤50%) + MurderousSwing AoE adjacent (+1746 si touche exactement 1) · counter=lui NIER les kills (casse le snowball) + ne JAMAIS laisser une de mes unités tomber ≤50% près de lui (TrophyTaker) ; fragile à la réaction massée (pas Resilient, 9537) SI on peut l'atteindre — mais derrière un anvil (Angrax) il devient un mur intouchable pumpé → focaliser le PUMPER (Hollan) plutôt que de chiper un Tarvakh déjà à 12.5k ; ✅ **NON-pumpé = chunk-killable AVANT son 1er kill (vécu seed 70009)** : a over-étendu à (3,5) en divant → chunk-kill via Patermine MightFromBelow (Psychic Pierce100 ignore armure ~5753) + Tanksmasha dans un burst WarHowl-buffé, AVANT qu'il score un seul kill = snowball mort-né [n=3, 70009]`
  `▸ Tac (n+1 NON-pumpé chunk-killable, seed 70060 W) : confirmé n+2 — AUCUN pumper présent (pas de Hollan/WarHowl) → resté à base 9537 = chunk-killable, PAS le mur 12.5k pumpé. Tué dans mon mur de réaction T2 (Sarquael 5214 OW + Re'vas OW finish) AVANT tout kill (déni BlessingsOfKhorne/TrophyTaker) ; pas Resilient → meurt à une réaction massée quand l'IA all-melee le force à diver. RÈGLE recon = COMPTER les pumpers adverses (Hollan/Ragnar) : aucun → demote Tarvakh de CRITICAL à high-killable [n=4, 97001-pumped/93001/70009/70060]`
- **Adamatar (emperKakophonist, mêlée/caster)** — `DoomSiren` (1199, seul actif) : 3× **Direct
  Pierce100** (ignore l'armure, ex. TerminatorArmour) à un ennemi adjacent + jusqu'à 2 autres ennemis
  **ADJACENTS À LA CIBLE** (PAS au lanceur, **splash target-relative confirmé**) → positionner la cible
  prime au milieu d'un cluster. Chaque ennemi **Overkillé par DoomSiren** donne +1 hit perma aux attaques
  normales d'Adamatar le reste du combat. ⚠️ probablement usage-unique (no-cd, H13 — vécu seed 70002 :
  resté [indispo] après son unique usage T1, cohérent). **Vérifié live seed 70002** : un cast a chunké
  Yazaghor (primaire 3 hits ~-4294) ET Tyrant Guard (adjacent-à-cible 3 hits ~-6363) en UN cast → le Pierce100
  a traversé l'armure du TG 12.5k trivialement = chunk-2-corps gratuit (le fragile primaire pour le kill + l'anvil
  voisin en collatéral).
  `▸ Tac: rôle=control · menace=med · counter=ne PAS clusterer mes unités adjacentes à un même hex (DoomSiren = 3× Direct Pierce100 AoE adjacent ; ignore armure/TerminatorArmour ; splash target-relative) ; ObsessiveAnnunciation aura = +800 dmg ranged subi aux adjacents ; pas de revive/FinalJustice → finisher trivial une fois chunké · si à MOI : lead DoomSiren sur un fragile collé à un anvil/cluster → splash l'anvil GRATIS (bypass armure), positionner Adamatar adjacent pour que son aura +800-ranged feed mes kills ranged suivants ; ⚠ côté ENNEMI dans une compo all-ranged = ObsessiveAnnunciation +800-ranged aux adjacents AMPLIFIE le focus du cluster (le vrai danger ≫ DoomSiren ici) ; seul diveur melee de la compo mais non-décisif quand le cluster ranged fait le killing (vécu seed 70052 : avancé melee-side (3,4), DoomSiren pas la pièce décisive) [n=3, 70002/70052]`
  `▸ Tac (n+1 soft-vs-melee, seed 70055) : 10038 PV mais AUCUN Terrifying/Parry/Resilient → SOFT à un carry mêlée tanky (chunk-then-K! propre) : vécu seed 70055 chunké par une normale Dante (2824-4240) puis guaranteed-K! le tour suivant ; ne PAS clusterer mes unités face à son DoomSiren AoE (3× Direct Pierce100) ; à traiter en cible de chunk-and-finish accessible — c'est UN des soft autonomous threats à tuer cheaply (avec Yazaghor/Godswyl) AVANT de buter sur le counter-engine (Atlacoya/Deathleaper) [n=4, 70002/70052/70055]`
- **Volk (blackObliterator, Black Legion, ranged r3, HeavyRound Pierce55)** — `FrenziedFiring` (1036,
  actif r3) : **AoE** = 1× 1455-1819 Heavy Round à la cible primaire ET à **TOUS les ennemis adjacents
  à elle** (cluster-softener) ; SÉPARÉMENT, score des hits EN PLUS sur la **cible primaire SEULEMENT**,
  un par hex libre autour d'elle (max 10 hits) ; les **hits bonus de FleshmetalGuns sont scorés contre
  CHAQUE ennemi touché** (i2-confirmé seed 70006). → viser un ennemi forward au CENTRE d'un cluster serré
  pour étaler le dmg sur 2-3 unités (vérifié seed 93000 : primaire Actus −6384 + splash Archimatos −2593
  + Sy-gex −1614 en un cast ; vérifié seed 70006 : Winged Prime primaire −7439 + splash Trajann adjacent
  −2888 + KILL un Hormagaunt frais adjacent −2992 en UN cast = 3-target value qui casse un summon-engine +
  chip l'anvil voisin + nie le snowball simultanément). `LetTheGalaxyBurn` (trait, confirmé carte) : chaque
  attaque a une **chance d'un hit en plus** + **Despoiled Ground** (hit en plus auto, sans Despoiled, si la
  cible est déjà sur un effet de hex). HeavyRound **Pierce55 = fort vs armure** ; HeavyWeapon : +dmg si Volk
  n'a PAS bougé ce tour.
  `▸ Tac: rôle=carry · menace=high (ranged r3 AoE carry = LE DPS qui ferme les kills : FrenziedFiring cluster-softener + LetTheGalaxyBurn extra-hits + HeavyWeapon +dmg si immobile + Daemon block → multi-hit ~5500-6300/tour observé, a fini Lucien T1 ET Ulf ; Daemon block + BigTarget = tanky 10-12.5k) · counter=si ENNEMI : ne JAMAIS présenter un corps isolé dans son arc r3+move2 (FrenziedFiring score +1 hit par hex LIBRE adjacent à la cible → viser-l'éviter dans un ESPACE OUVERT) ; le laisser pour la FIN (tanky Daemon/BigTarget) et nier ses cibles ; move2 LENT → kitable mais frappe à r3 donc « back » relatif ; si à MOI, l'utiliser depuis une tuile shallow HORS arc Overwatch armé pour chunker une grappe forward — NE PAS le pousser au contact [n=2, 93000/70005]`
- **Shiron (emperNoiseMarine, Emperor's Children, ranged r3 + mêlée, HeavyWeapon)** — **carry ranged
  finisher tardif.** `ExcruciatingFrequencies` (actif, profile **Blast Pierce15** `HitsMultipleMembers`,
  ~3492-4365 lvl65) = **ligne AoE de 3 hexes en ligne droite (1 des 6 directions)**, tirée À TRAVERS la
  cible visée ; touche **CHAQUE ENNEMI** sur les 3 hexes (les alliés sur la ligne NE sont PAS touchés) et
  les **Suppresse** ; **+30% Crit Chance PAR unité sur les hexes affectés** → multi-crit facile (i2
  vérifié seed 95001 : double CRIT Tjark −4268 + Sy-gex −7759 en un cast). **Attaque normale ranged = 6×
  Eviscerate Pierce50 r3** (vérifié seed 70001 : a fini un Mataneo Pinned depuis la tuile courante, ~2029
  sommé, zéro exposition de mouvement → finisher safe d'un isolé à distance). Passif `SuppressiveFire`
  (tout ennemi touché par son ranged devient Suppressed)
  + `TerrifyingCrescendo` (passif : ses attaques RANGED déalent **+218 dmg par fois qu'il a Overkillé OU
  aurait Suppressé un ennemi, cap 6 = +1308 max** ; i2-vérifié) → auto-snowball : SuppressiveFire feed le
  compteur, ExcruciatingFrequencies suppresse+crit, HeavyWeapon (+ranged s'il ne bouge pas) → **late-game
  ranged finisher** capable de gros K! depuis sa tuile sans bouger. ⚠ le sous-claim « un crit ÉTEND la
  durée de ThrillSeekers » est **NON supporté par i2** (ThrillSeekers se re-trigger par tour sur
  dégât-subi/cible-full-HP, PAS sur crit) → cf. H22, ne pas s'y fier. **Doctrine : le garder STATIONNAIRE
  (HeavyWeapon + InescapableAccuracy-like) en arrière, laisser le compteur Crescendo monter, l'utiliser
  comme finisher de fin de partie sur l'engine adverse.**
  `▸ Tac: rôle=carry · menace=high (finisher ranged tardif : TerrifyingCrescendo stacke +218/Overkill-ou-Suppress, cap 6 ; ExcruciatingFrequencies = ligne AoE multi-crit ; PAS de Resilient/FinalJustice, 8533) · counter=si ENNEMI, c'est LA menace standoff la plus dangereuse — le tuer TÔT avant que le compteur Crescendo monte (soft, fragile) ; **ne JAMAIS laisser un fragile STATIONNAIRE dans sa portée r3+move** (vécu seed 70009 : a deleté mon Patermine forward ~7788 en un tour ranged) ; fermer le gap comme un mur HP-screené et le meleer (tué proprement sur 2 tours une fois isolé 4v1 : Tanksmasha 8533→4013, Trajann chunk→1547, Trajann K!) ; si à MOI, le garder STATIONNAIRE en arrière, réserver son K! stacké pour l'engine adverse (vécu seed 95001 : a one-shot Isabella 8533 PV à r3 sans bouger après lvl5 stacks) [n=2, 70009]`
- **Haarken « Haarken Worldclaimer » (blackHaarken, Black Legion, Chaos, move4 Flying, mêlée burst)** —
  `HeraldOfTheApocalypse` (actif mêlée) : **frappe DEUX cibles en un cast** — 2× Piercing (~1310-1892/hit
  lvl65) à l'**ennemi adjacent** ciblé ET à **un ennemi directement DERRIÈRE la cible** ; les **DEUX**
  reçoivent le debuff **+1310 dmg de la prochaine attaque** subie (i2 « Affected enemies », pluriel = les
  deux). Double-target confirmé (vécu seed 98004 : a touché Helbrecht 5364 ET Aesoth derrière 5390 en un
  cast + posé le debuff +1310 sur les deux). → bloquer/tuer l'une des deux cibles supprime la moitié des
  dégâts ; aligner deux ennemis (cible + arrière) maximise le cast. `Terrifying` (réduit la mêlée subie →
  bypass = RANGED, §1). move4 + Flying = grosse portée d'engagement.
  `▸ Tac: rôle=carry · menace=high (burst mêlée double-target : HeraldOfTheApocalypse touche cible + l'ennemi derrière, +1310 debuff sur les deux ; move4 Flying = reach énorme) · counter=si ENNEMI, le tuer TÔT au RANGED (Terrifying ne protège que la mêlée) avant qu'il aligne mes 2 unités ; si à MOI, le chaîner APRÈS un mark Asmodai ExemplarOfHate (+728/hit team melee → 4-hit burst amplifié 2832-4248 → 6024-7436, vécu seed 98004) sur une cible avec un ennemi derrière elle [n=1]`

---

## 3. Units IMPERIUM (kits & interactions — faits neutres)

- **Lucien (bloodDeathCompany « Death Company », Blood Angels, ~8429 PV, mêlée carry autonome)** —
  carry **focus-killer auto-pilote**. `Resilient` (coup létal non-Overkill → 1 PV ; cf. §1). `RapidAssault`
  (+1 move + bonus dmg sur les 1ʳᵉ/répétées attaques). `VisionsOfHeresy` (**2ᵉ attaque GRATUITE r2 à chaque
  activation** ciblant *n'importe quel* ennemi ≤r2 — **i2 dit « an enemy within range 2 », PAS « the same enemy »**
  → la 2ᵉ attaque peut frapper une cible DISTINCTE de la normale → **double-finisher en une activation** si deux
  ennemis bas-PV sont tous deux à portée r2 ; + **+20% Piercing quand Lucien ≤50% PV** = double-attaque qui pierce
  mieux à bas PV).
  `BlackRage` (set à 50% PV, **auto-charge** puis devient un **auto-attaquant INCONTRÔLABLE** qui fonce sur
  l'ennemi le plus proche). → un **focus-killer autonome** : RapidAssault+VisionsOfHeresy = double-attaque,
  BlackRage le lance tout seul. **Vérifié live seed 70002** : Doombolt 2-hit l'a chunké 8429→4308 SANS que
  Resilient interfère (aucun seuil de défaite atteint) ; sa double-attaque VisionsOfHeresy a focus-killé mon
  Abraxas ; puis BlackRage l'a auto-chargé dans mon cluster groupé → tué EXACTEMENT en réaction multi-source
  (4308→0, multi-source bat Resilient).
  `▸ Tac: rôle=carry · menace=high (autonome : Resilient + RapidAssault double-attaque + VisionsOfHeresy 2ᵉ attaque gratuite +20% pierce ≤50% + BlackRage auto-charge incontrôlable = focus-killer self-driving) · counter=multi-hit/multi-source pour battre Resilient (une source floor à 1, la suivante tue) ; ⚠ overkill si je le tue ACTIVEMENT ; MEILLEUR counter = le laisser diver une ligne groupée → reaction-kill (vécu seed 70002 : 4308→0 en réactions, ZÉRO action offensive dépensée — BlackRage le force à charger mon cluster) ; il a tué mon Abraxas via la double-attaque → garder mes fragiles HORS de sa reach (move3+RapidAssault=move4, r2) [n=1, 70002]`
- **Vexilus/Aesoth (custoVexilusPraetor, 11044, move3 mêlée)** — `VexillaMagnifica`
  (1183, actif : **STUN 2 cibles adjacentes** + dmg + le lanceur −66% dmg subi 1 round,
  cd2). `StandVigil` (alliés à portée 2 : +armure / +dmg non-normal ; étendu si un
  Custodes use un actif). `BigTarget` (alliés adjacents −1 hit ranged ; non déplaçable).
  `Resilient`.
- **Trajann (custoTrajann, 10038, move3 mêlée)** — `MomentShackle` (1184, self-heal ~4365 base (scale
  niveau/rareté → +5684 observé seed 70004) + pour 1 round **+20% Block + 873 flat block** et **2× Bolter en
  riposte** à chaque ennemi qui sort d'un hex adjacent). ⚠ **REPEATABLE = actif standard sur cd (~2 tours),
  PAS once-per-battle** (gameconfig : aucun champ charges/perBattle ; vérifié seed 70004 : Trajann a heal
  4354→10038 un tour PUIS attaqué 4249 le suivant, ré-heal au cd). `LegendaryCommander` (un ennemi adjacent à
  un allié qui a usé un actif ce tour → **+800 dmg subi** ; s'il est aussi adjacent à Trajann, les Characters
  alliés scorent **+2 hits** à leur 1ʳᵉ attaque non-normale). `CrushingStrike` (+dmg mêlée normale **s'il n'a
  PAS bougé**). `Resilient`, **`MartialKatah` (−20% dmg des attaques NORMALES subies SEULEMENT** ; les ACTIFS
  bypassent — ex. Kariyan MartialInspiration/LegacyOfCombat tape à plein ; clause à part : +100% dmg vs Summons).
  → **chip gâché** (heal+block annulent) : ne committer QUE des dégâts qui sécurisent un kill/Overkill.
  ⚠ **MUR STRUCTUREL self-healing (vérifié seed 70004)** : Resilient (floor à 1, sauf Overkill) **+** MomentShackle
  heal-to-full REPEATABLE sur cd **+** ~4249/tour d'attaque **+** MartialKatah (−20% normales) = un anvil qu'un roster
  **chip-only** (~2100-3000/tour) NE PEUT PAS finir : il se heal-to-full tous les ~2 tours ET out-damage le tank, donc
  il devient la **wincon late de facto** une fois les screens tombés. Fenêtre de kill = un **overkill multi-source en UN
  tour** pendant que MomentShackle est en cd, OU un **Direct/Psychic** qui bypasse son block (DoomSiren Direct Pierce100).
  ✅ **TUABLE EN UN TOUR — SÉQUENCE VÉRIFIÉE (seed 70005)** : la fenêtre EXISTE et a été exploitée — Trajann chunké par
  réactions (DestroyerHive + CrushingClaws) 7221→4578 le tour précédent, PUIS le tour suivant (MomentShackle en cd) :
  Typhus **Psychic normal** (Pierce100 + NoBlocking → bypass block ET MartialKatah) 4578→3307, PUIS Ulf GreatFrostAxe
  (**4-hit ACTIF** → bypass MartialKatah qui ne réduit QUE les normales + bat Resilient floor-then-finish) 3307→0 Overkill.
  La SÉQUENCE = chunk-par-réactions → Psychic-bypass-block → actif-multi-hit-finish, le MÊME tour, MomentShackle en cd.
  Contraste avec 70004/70007 où il est resté full (burst épuisé / écran jamais cassé) : la différence = avoir RÉSERVÉ le
  burst Psychic (Typhus) au lieu de le dépenser tôt.
  `▸ Tac: rôle=anvil · menace=critical (MUR self-healing : MomentShackle heal-to-full REPEATABLE ~+5684 sur cd + Resilient + ~4249/tour + MartialKatah −20% normales → INKILLABLE par un roster chip-only/burst-épuisé = wincon late de facto une fois les screens tombés ; LegendaryCommander +800 amplifie le focus équipe) · counter=NE PAS chiper (heal+block+Resilient annulent tout chip non-létal) ; KILL via (a) Direct/Psychic bypass-block (DoomSiren Pierce100) OU (b) overkill MULTI-SOURCE en UN tour pendant que MomentShackle est en cd, OU (c) RÉACTIONS/Overwatch massées (vécu seed 96002 : tué 702 HP par 2 triggers Burchard Overwatch sans actions offensives ; vécu seed 70006 : tué EN RÉACTION — Volk AoE splash + Aesoth 4160 counter + Guardsman finish — AVANT qu'il cast MomentShackle : Resilient ne sauve qu'1× (→ 1 HP), MomentShackle est CAST-ONLY (no auto-trigger) → un burst de réactions qui floor PUIS finit AVANT son action le tue sans qu'il self-heal) ; ⚠ RÉSERVER mon burst anti-block POUR LUI au recon (vécu seed 70004 : DoomSiren dépensé tôt → chip-only vs l'anvil = loss structurelle, j'ai gagné 4v1 mais pas pu le finir) ; si mon burst est dépensé/absent → FLAGGER la loss, ne pas grind ; ⚠ il est aussi le mur derrière lequel se cache un DOUBLE summon-engine (Isaak board-flip + Yarrick attrition) : NE PAS le chiper, casser ses ÉCRANS (les summon-engines) à la place (vécu seed 70007 : Trajann full 10038 tout le combat, mes Psychic au mieux ~2-3k chip annulé par MomentShackle → le board a flippé 3v12 avant toute fenêtre de kill) ; ✅ **TUABLE confirmé (vécu seed 70005)** : chunké par réactions 7221→4578 PUIS Typhus Psychic Pierce100 NoBlocking 4578→3307 PUIS Ulf GreatFrostAxe 4-hit actif 3307→0 Overkill, le MÊME tour, MomentShackle en cd = mur self-healing DÉTRUIT — la fenêtre existe SI on a RÉSERVÉ un burst Psychic/Direct + un actif multi-hit (cf. §5bis) ; ✅ **2e fenêtre confirmée = RÉACTIONS PURES (vécu seed 70006)** : tué en réaction (Volk AoE splash + Aesoth 4160 counter + Guardsman finish) AVANT qu'il cast MomentShackle = la fenêtre n'exige PAS forcément un burst dédié si l'IA dive dans une ligne de réactions massées (Resilient floor 1× + MomentShackle cast-only → mort avant self-heal) [n=5, 96002/70004/70007/70005/70006]`
  `▸ Tac (n+1 à MOI = combo Resilient+MomentShackle recovery, seed 70060 W) : ✅ quand Trajann est dans MON roster, le combo Resilient + MomentShackle est une boucle de récup gratuite — Resilient sauve à 1 HP (floor, sauf Overkill), puis MomentShackle self-heal +4365 (scaled) le ramène quasi-full le tour suivant (vécu seed 70060 : floored à 1 par Resilient en avançant pour finir un engine → MomentShackle 1→5984 + Block buff le tour d'après, zéro perte). MartialKatah −20% normales a aussi réduit les attaques de Burchard vs Trajann. → un corps forward Resilient+MomentShackle peut être committed un tour pour landa un kill d'engine guard-approuvé SANS le perdre (mais une ligne plus propre évite l'exposition forward — cf. journal mistake) [n=6, 96002/70004/70007/70005/70006/70060]`
- **Morvenn (adeptMorvenn, 9539, move3, ranged r3 + mêlée)** — `SanctorumMissile`
  (1062, AoE Blast r3 — **faible vs armure**, cf. §1). ⚠️ **Le splash (1× sur TOUS les
  hexes adjacents à la cible) est POSITIONNEL, pas filtré ennemi → friendly fire** : touche
  MES propres unités adjacentes à la cible. i2 n'exempte QUE l'hex de Morvenn elle-même ;
  tout autre adjacent (allié inclus) est touché. **Ne jamais le tirer quand une de mes
  unités est adjacente à la cible** (même classe de risque qu'`Explodes`). Vérifié : tir sur
  Calandis/Mephiston → overkill/dmg sur mon propre Biophagus / Dreir+Dante adjacents.
  `Explodes` (**friendly fire** : à la mort, 25% PV max Direct à TOUS les adjacents, cf. §1).
  `ActOfFaith` (+crit à chaque mort/kill d'un Imperial, reset au crit). `RighteousRepugnance`
  (mêlée normale +AoE). `Mechanical` (pas de heal, repair seulement).
  `▸ Tac: rôle=carry · menace=high (dealer ranged Blast r3 2183-3056 ×2 + splash adjacent friendly-fire + Explodes 25% maxHP Direct à la mort + ActOfFaith crit-snowball) · counter=la tuer au RANGED/réaction sans coller mes unités à sa mort (Explodes friendly-fire — vécu seed 98004 : 2×2385 sur Haarken+Nicodemus, survie OK ; tuée en réaction T3) ; HEAL-BLOCKable (Mephiston FuryOfTheAncients) pour nier un revive Healer adverse (Nauseous) ; Blast ≪ vs armure (SanctorumMissile pas un finisher) ; pas de Resilient → un burst franc la défait [n=1]`
- **Mephiston (bloodMephiston, 9537, move3, ranged r2 + mêlée, Psychic Pierce100
  NoBlocking)** — Psychic **bypasse TerminatorArmour**. `Psyker` (attaque ranged
  normale → splash % à un ennemi adjacent à la cible ; **s'auto-blesse dans une aura
  Nurgle**, cf. Corrodius). `TheQuickening` (1151, repositionnement r2). `Terrifying`
  (réduit les dégâts de **mêlée** subis — ⚠️ l'armor-ignore/perforant NE bypasse PAS
  Terrifying, ce n'est pas un mécanisme d'armure ; seul le **RANGED** le contourne).
  `RapidAssault`. `FuryOfTheAncients` (actif **déclenché par le mouvement**, PAS un passif :
  après qu'il a bougé, 2× Psychic **Pierce100 + NoBlocking = ignore armure** à un ennemi
  adjacent ET un 2ᵉ ennemi adjacent à celui-ci ; **s'il ne bouge pas, auto-fire en fin de son
  tour**) → applique un **blocage 2 rounds** : les unités touchées ne peuvent être **revives,
  heal, repair, ni restaurer leur PV** (shut-down de `ToughToKill` / tout heal type Nicodemus).
  Fan sur **2 unités/cast** → peut nier tout un noyau de sustain vite. Le tuer tôt = nuke
  armor-ignore + déni de sustain. **Vérifié seed 93000** : chaque MOVE auto-fire 2× Psychic sur la chaîne
  adjacente (ex. Archimatos −2561 + Sy-gex −1646 sur un move ; Sy-gex −1443 + Aesoth −1398 sur un autre)
  + heal-block 2 rounds appliqué → traiter son **mouvement comme une AoE garantie** ; garder mes bas-PV/
  healer-dépendants hors de sa chaîne d'adjacence. **Confirmé seed 95002** : Mephiston move adjacent à
  Atlacoya → FuryOfTheAncients a appliqué le HEAL-BLOCK live sur Atlacoya (visible dans decisionView, 2
  rounds, r3 restant) — le blocage frappe **TOUTE unité touchée par l'AoE** (la primaire ET le 2e
  adjacent), pas seulement la cible primaire (n=2). **Confirmé seed 70051** : move-rider 2× Psychic + heal-block
  2 rounds sur Dreir + Creed (chaîne d'adjacence : primaire + 1 adjacent à la primaire, PAS rayon Mephiston) →
  a **coupé la regen `ToughToKill` de Dreir** (un Dreir floored à 114 par Resilient n'a PAS remonté tant que le
  heal-block durait) → confirme que `ToughToKill` est un « heal » bloquable (cf. H44) et que la chaîne touche
  bien la primaire ET le 2ᵉ adjacent (n=3).
  `▸ Tac: rôle=carry · menace=critical (nuke armor-ignore Pierce100 NoBlocking bypasse TerminatorArmour+Terrifying + déni-sustain move-rider heal-block 2 rounds + shred un roster mêlée à distance) · counter=le tuer T1-T2 AVANT FuryOfTheAncients si ENNEMI (priorité 1 wincon — vécu seed 95002 : combiné à Makhotep a effacé Tarvakh 9537→0, jamais défait du match faute de l'atteindre ; seed 70051 : LE wincon adverse, focus multi-source 8230→0 T4 dès qu'il a dive, pas de Resilient → tout focus suffisant le tue franc) ; son heal-block coupe la regen ToughToKill/Nicodemus → tenir mes bricks regen-dépendants HORS de sa chaîne d'adjacence (sur Dreir(114)→non-régen→perdu) ; DaughterOfTheAbyss (Atlacoya) −33% Psychic aux alliés adjacents = insuffisant seul vs son output plein ; si à MOI, son move = AoE Psychic gratuite sur 2 cibles — chaîner le move-rider AVANT le normal, ne pas le laisser forward (Terrifying ne protège que la mêlée → focus-killable au ranged) [n=4]`
- **Yarrick (astraYarrick, 7530, move3, ranged r2)** — `SendInTheNextWave` (1016, summon **2 Cadian
  Guardsmen +1 par allié DÉFAIT** ce combat, **cap 5** ; apparaissent à r2 de la cible et **tirent
  immédiatement** au cast, Las r2 Pierce10). Snowball en moteur d'attrition au fur et à mesure que JE
  perds des unités → ne pas lui donner de kills faciles ; tuer ses summons ne le refill PAS (seules
  MES pertes le font). `Resilient`. ⚠ observé live (seed 95002, NON re-vérifié gameconfig) : un buff
  `SummaryExecution_BaseEffect` sur ses Guardsmen a disparu **immédiatement à la mort de Yarrick** (les
  Guardsmen perdent un bonus de dmg quand il meurt) — aura source-anchored probable, à confirmer.
  `▸ Tac: rôle=engine · menace=med (summon-engine d'attrition : SendInTheNextWave summon 2 Cadian Guardsmen +1 par allié DÉFAIT, cap 5 ; les Guardsmen ~3989 PV alimentent le snowball + finissent les fragiles ; ⚠ LESSER engine — ne PAS lui dépenser mon tour si un board-flip engine (Isaak) est aussi sur le board et non tué) · counter=le tuer TÔT et AVANT d'accumuler mes défaites ; Resilient → MULTI-hit (BringerOfDespair 4+4 : 1er floor à 1, 2e tue depuis 1 — vérifié seed 95002 ; Sy-gex attaque NORMALE 4-HIT both KILL+OVERKILL en un coup — vérifié seed 70007) OU 2ᵉ source/Overkill ; sa mort retire le buff SummaryExecution des Guardsmen (re-observé seed 70007 : Attack_Modification stripé des 2 Guardsmen à sa mort = aura source-anchored probable, cf. H39) + roll BattleFatigue sur les Guardsmen adjacents (un a fui à sa mort, seed 95002) ; ⚠ en MIROIR (2 Yarricks sur le board, seed 98003) le throughput SendInTheNextWave DOUBLE = snowball encore plus rapide [n=3, 95002/98003/70007]`
- **Vindicta (adeptRetributor, Sisterhood, move3, ranged r2)** — passif **`FireOfAbsolution`** : à
  CHAQUE attaque ranged (normale OU `ArmoriumCherub`), splash **3× Flame** (Pierce25, OnFire, ~499→1455
  max) sur **TOUTES les unités ADJACENTES À LA CIBLE** + 30% Fire sur chaque hex adjacent. ⚠️ **splash
  positionnel NON filtré ennemi → FRIENDLY FIRE** (pas d'exception lanceur/allié, contrairement à
  SanctorumMissile) : un cluster ennemi serré se punit lui-même quand elle tire, mais MES unités
  adjacentes à la cible sont aussi touchées (vécu : 3992 d'auto-dégâts sur alliés ; 439→0 sur mon
  propre Archimatos). **Dégager mes unités de l'adjacence-à-la-cible avant tout tir de Vindicta.**
  Aussi `ArmoriumCherub` (4× Flame, ne termine PAS son tour) + `ActOfFaith` (crit-ramp à chaque mort/kill
  d'Imperial). Fragile 7029, Psychic-vulnérable.
  `▸ Tac: rôle=carry · menace=high (dealer Flame ranged : FireOfAbsolution splash + ActOfFaith crit-ramp qui scale sur les morts/kills Imperial) · counter=la tuer AVANT qu'elle empile ActOfFaith (chunk Psychic Mephiston + finisher mêlée) ; fragile/over-étend (vécu seed 97000 : poussée (2,5) → tuée — mais elle a focus-killé mon Macer forward ~4573 d'abord) ; ne PAS laisser une de mes unités adjacente à sa cible (FireOfAbsolution friendly-fire — confirmé du côté ENNEMI seed 70007 : Vindicta a tué son propre Neophyte + chunké son propre Aesoth 698×6 en tirant sur un cluster serré → un Vindicta adverse se punit lui-même, et la mienne punit les MIENS adjacents à la cible) ; ⚠ **RE-CONFIRMÉ côté MIEN (vécu seed 70056 triggered-against-me)** : ArmoriumCherub + normale sur Tanksmasha alors que mes Calandis (2,1) + Corrodius (2,0) étaient adjacents à la cible → 2 splashes ont coûté ~3000 HP à Calandis (4953→1959) ; DÉGAGER mes units de l'adjacence-à-la-cible AVANT tout tir de Vindicta [n=3, 97000/70007/70056]`
- **Arjac (spaceRockfist)** — `Foehammer` (Ranged Power, range 2, 1 hit, Pierce40) : inflige
  **Stunned** sur la cible jusqu'au DÉBUT du prochain tour d'Arjac (engine RemainingTurns=2) → la cible
  garde son attaque NORMALE mais perd **TOUS ses actifs** (vérifié seed 97000 : Calgar stunné ne pouvait
  PAS user GauntletsOfUltramar) + réduite à 1 Movement (MovementOverride=1) ; Heal/Repair retire le Stun.
  ET **+2183 dmg flat par Character (n'importe quel camp) défait ce combat** par-dessus sa base 364-728
  (0 kill → base seule ~2860). Snowball en one-shot finisher quand le board s'amincit → le GARDER pour le
  mid/late game ; inutile T1. ⚠ observé **usage unique par combat** ([indispo] après un tir, n=1 — type
  cooldown engine, PAS dans gameconfig ; lire decisionView avant de re-committer). `Resilient`,
  **`AnvilShield`** : baseline = absorbe 728 dmg supplémentaires + couvre l'hex de l'attaquant en Glace à
  chaque Block ; **sous 35% PV** (OU si l'attaquant est sur un hex glacé) Arjac gagne **+20% Block chance**
  ET ice-**Stun** tout attaquant MÊLÉE dont il Block le coup. ⚠ **synergie clé avec Resilient** : une fois
  Resilient déclenché (floor à 1 PV), Arjac est par définition sous 35% → le mode renforcé d'AnvilShield
  s'active pour CHAQUE mêlée suivante → survie last-man dramatiquement allongée (vécu seed 97000 : Arjac
  327→ heavy-blocks 326+1 de Calgar, a tenu ~3 tours ennemis avant de tomber).
  `▸ Tac: rôle=anvil/finisher · menace=high (Foehammer = Stun-lock l'actif d'une cible-clé 2 tours + finisher snowball +2183/Character mort ; AnvilShield+Resilient = last-man dur à finir) · counter (usage à MOI) = réserver Foehammer pour locker l'actif d'un anvil/control adverse (vécu seed 97000 : a coupé GauntletsOfUltramar de Calgar) + finir un fragile une fois le board aminci ; ne PAS le compter pour percer un mur double-armure (Power Pierce40 ~1075/tour vs MkXGravis) [n=1]`
  `  ▸ Tac (n+1 Foehammer = both-teams-count CONFIRMÉ self-play consensus, seed 80000 run #5) : le +2183/Character compte les morts des **DEUX camps** (gameconfig « each Character that has been defeated in this battle », sans restriction de camp) → **le snowball coupe dans les DEUX sens : tuer des héros ENNEMIS arme AUSSI l'Arjac ennemi**. Vécu : après 2 kills, Foehammer ennemi est devenu un **one-shot ~4730-5094 + Stun à range 2** sur tout sub-5k → a delete un Atlacoya fragile. ⚠ cross-validé les 2 sides (A theirs : « became a ~5094 one-shot after my 2 kills » ; B mine : « ramp partially applied — 2 dead Characters were on MY side, confirming both teams count »). DOCTRINE : en late-game, dès que des Characters sont morts (peu importe le camp), garder TOUS mes fragiles HORS de la r2 de l'Arjac ennemi — kiter (l'Arjac est lent move2). [self-play consensus, seed 80000 run #5]`
- **Jaeger « Brother Jaeger » (templChampion, Black Templars, mêlée)** — `MartialSuperiority` (passif
  COUNTER) : si Jaeger est **ciblé par une attaque de mêlée d'un ennemi adjacent pendant le tour ennemi**,
  il inflige **2× Power Damage (Pierce40, 1455-1601 lvl65)** à l'attaquant **AVANT que l'attaque ennemie
  ne s'exécute** → punit tout engagement mêlée adjacent ; le counter part même si l'attaquant a plus de
  PV (ne tue pas forcément), mais réduit/chunke la cible avant son coup (vécu seed 96001 : Tarvakh a pris
  1279+1315=2594 AVANT que son coup parte). `HolyDuel` (actif) : taunt **MUTUEL sans expiration** (Jaeger
  ET la cible sont Taunted l'un par l'autre) → coupe l'ACTIF de la cible via `Taunted_CantUseAbility`
  (+`Taunted_BlockMovement` immobilise, cf. §1) : la cible ne peut PAS lancer son actif (vécu seed 96001 :
  Tarvakh locké ne peut PAS `MurderousSwing`, **seule l'attaque normale forcée sur Jaeger reste possible**)
  → **neutralise une unité de valeur pour tout le combat**. Curable par Healing/Repairing (retire le
  Taunt). `Terrifying` (réduit la mêlée subie → bypass = RANGED, cf. §1).
  `▸ Tac: rôle=control · menace=high (lock total d'une pièce-clé via HolyDuel + counter qui punit le contact mêlée) · counter=ne JAMAIS laisser une unité-clé adjacente seule à lui (HolyDuel = la verrouille tout le combat, coupe son actif) ; l'attaquer depuis le RANGED pour éviter MartialSuperiority (counter mêlée seulement) ; un Healing/Repair retire le Taunt ; Overkill pour FinalJustice si présent (vécu seed 96001 : a locké Tarvakh → duel perdu vs counter) [n=1]`
- **Calgar « Marneus Calgar » (ultraCalgar, Ultramarines, mêlée/tank, MkXGravis)** — `GauntletsOfUltramar`
  (1000, **Ranged AoE**, profil **Bolter** (PiercingRatio 20)) : inflige **1× Bolter à TOUS les ennemis
  dans un rayon de 2 hexes** en un seul cast — **vrai splash multi-cible**, PAS des hits bonus sur une
  seule cible (la classe expose GetAdjacentTargetsSelector + GetSurroundingTargetsSelector +
  GetAllTargetsSelector). Vérifié seed 97001 : un cast depuis une tuile stationnaire (4,2) a touché à la
  fois Angrax (-2230) ET Exitor (-2113), 2 ennemis à des positions distinctes. **`MkXGravis`** (double-armure,
  cf. §1) + `FinalJustice` (riposte à la mort, §1) + `RitesOfBattle`. → faible vs armure (Bolter Pierce20),
  mais **haute valeur depuis une tuile stationnaire** (zéro exposition, couverture large si 2+ ennemis
  clusterisés à ≤2 hexes).
  **MkXGravis confirmé seed 97000** : les dégâts entrants passent l'Armour une SECONDE fois (sauf Crits)
  → ~HALVE le dmg mêlée non-crit (mon Arjac 3× Power Pierce40 ne faisait ~1075-1098/tour à Calgar tout le
  combat) → **mur quasi-inkillable pour un roster mêlée sans crit/armor-bypass**.
  `▸ Tac: rôle=tank/anvil · menace=med EN GÉNÉRAL, **CRITICAL vs un roster majoritairement MÊLÉE** (MkXGravis double-armure ~halve le dmg mêlée non-crit + FinalJustice + RitesOfBattle +946 buff-aura Imperial → wincon-anchor late-game inkillable au chip mêlée, vécu seed 97000 ~1080/tour à travers l'armure) · counter=Crit / armor-ignore / Psychic (bypasse la 2ᵉ passe d'armure) OU le Stun (Foehammer coupe GauntletsOfUltramar) ; NE PAS planifier de l'out-grind en mêlée — tuer les dealers plus softs qu'il buffe et accepter de ne pas le trade ; à MOI = GauntletsOfUltramar STATIONNAIRE quand 2+ ennemis ≤2 hexes (splash gratuit) + turret défensive (FinalJustice punit la mort) [n=1]`
- **Tigurius « Tigurius » (ultraTigurius, Ultramarines, Psyker, ranged)** — kit **recon-CONFIRMÉ vs gameconfig**
  (seed 98003 : la carte provisoire amorcée seed 97000 matche gameconfig). Engine Psyker AoE : **`StormOfWrath`**
  (~1819-2183 **Psychic Pierce100 NoBlocking** sur la cible **+ jusqu'à 5 adjacents = 6 unités max** ; PiercingRatio=100
  ignore l'armure ET NoBlocking bypasse les Block-abilities — **BigTarget, GuardianOrganism n'appliquent PAS** ; vécu
  seed 70000 : ~2562-2762/hit sur 6 de mes units après mitigation, mes drones non-couverts morts) — **un cast arme
  trivialement `WeaverOfFate`** (Thaumachus/Neurothrope MAX-dmg dès 3+ ennemis touchés en Psychic) ET escalade
  Neuroparasite sur chaque cible. Aura **`PsychicFortress`** : tous les alliés autour de Tigurius gagnent un **block
  50% chance de 437 dmg (any-type)** ET **−873 Psychic subi** ; les DEUX effets **stackent sur un hit Psychic** (jusqu'à
  1310 mitigation totale). **L'aura est perdue à la mort de Tigurius** — vécu seed 70000 : PsychicFortress a BLOQUÉ
  plusieurs de mes finishers sur Thaumachus (hits Amount=0 DidBlock=1 → l'a laissé à 1225 au lieu de mort) ; tuer
  Tigurius re-active les finishers Psychic sur les alliés protégés. **Fragile ~6525, PAS Resilient** ; over-étend
  facilement (vécu seed 97000 : avancé (3,6) T1 → puni).
  `▸ Tac: rôle=engine · menace=critical (Psyker AoE NoBlocking ignore-armure 6 cibles = arme WeaverOfFate + Neuroparasite snowball ; PsychicFortress block-aura mange MES finishers ET blunt MON Psychic — vécu seed 98003 vs Sibyll, seed 70000 vs mes finishers sur Thaumachus) · counter=le tuer EN PREMIER (fragile 6525, pas Resilient → tout K! franc : JakhalStimms l'a K!'d seed 97000 ; Roswitha CondemnorStake +2183 vs Psyker = cible d'alpha prime) → drop la block-aura + retire l'AoE ; FULL-FOCUS la SOURCE Tigurius, ne PAS split (vécu seed 70000 : split Thaumachus/Tigurius → PsychicFortress a bloqué mes finishers, Tigurius survit 1694, re-fire et K! mon Anuphet = root cause partagée de la loss) ; ne PAS clusterer 3+ de mes units exposées à StormOfWrath ; punir son over-extension forward (T1 dive mid-board = kill gratuit ; ⚠ s'il dive ADJACENT à un Ulf SavageKiller, sa StormOfWrath est PRÉ-EMPTÉE — tué mid-cast avant que l'AoE résolve, vécu seed 70004 : 2754+2958+813 KILL en réaction) [n=4]`
  `  ▸ Tac (n+1 StormOfWrath OFFENSIVE = 2-for-1 cluster-delete CONFIRMÉ self-play consensus, seed 80000 run #5) : **à MOI, viser un ennemi ADJACENT à un 2ᵉ héros ennemi = double-kill gratuit** — le splash Psychic NoBlocking touche la cible + les adjacents en bypassant armure ET block sur TOUS. Vécu : cibler Tanksmasha (adjacent à Vitruvius) a tué le carry ET splash-tué le repair-engine Vitruvius en UN cast (5v5 → 5v3, 0 perte = la play la plus haute-leverage du match). ⚠ corollaire offensif du « ne pas clusterer MES units » : quand l'ENNEMI cluster 2 héros fragiles, StormOfWrath les delete tous les deux. ⚠ séquencer Tigurius (+ autres actifs alliés) AVANT un Atlacoya TalonsOfTheEmperor pour pumper le +728/actif sur le kill du même cluster. Cross-validé les 2 sides (A mine : exécuté ; B theirs : a subi le double-kill T4). [self-play consensus, seed 80000 run #5]`

---

## 3bis. Units (autres factions, vues en random) — kit + interactions PAR unité

> Une entrée par unité ; interactions spécifiques sur SA page (traits transverses
> en §1 : Resilient, FinalJustice, Explodes, **Ambush**, **Steppable**, Blast-vs-armure).
> Stats → gameconfig. **Recon AUSSI les unités INVOQUÉES** (decoy, drones, Aberrant,
> Hormagaunt, Guardsman…) via gameconfig dès qu'elles apparaissent — leurs traits
> dictent la gestion (ne pas supposer ; ex. le decoy `Steppable` ci-§1).

- **ultraTitus (Ultramarines)** — `TacticalPrecision` (s'il a chargé = crit ~3638,
  sinon 3× AoE adjacents ; **un revive/résurrection RE-DÉBLOQUE TacticalPrecision** même
  déjà utilisé ce combat — clause sur l'actif TacticalPrecision). **`FuelledByFury`** :
  1ʳᵉ mort/tour **NON-overkillable** (Final Vengeance fire toujours, sauf Overkill) +
  **revit à max 5456 PV UNIQUEMENT si sa Final Vengeance DÉFAIT un ennemi** (attaque
  NORMALE sur une cible **éligible/adjacente**, gated « 1ʳᵉ défaite/tour »). **Pas de kill =
  pas de revive** (un simple chip ne suffit pas). → le tuer en **niant le kill de riposte**
  (ne laisser aucune unité fragile/adjacente quand il meurt) OU en l'**Overkillant** (la
  protection no-Overkill ET le revive sont tous deux « 1ʳᵉ fois/tour »). Vérifié : 1ʳᵉ mort
  Final Vengeance tue un Grot → revive + re-arme TacticalPrecision ; 2ᵉ mort chip sans kill
  → mort permanente. `FinalJustice`, `BeastSlayer`.
  ⚠ **KILL-SAFETY vérifié seed 70004 (anti-revive par adjacence high-HP)** : la 1ʳᵉ défaite/tour
  bloque l'overkill → FinalJustice fire TOUJOURS ; le revive (5456 PV) ne déclenche QUE si la
  riposte FJ DÉFAIT un ennemi adjacent. → finir Titus en gardant **SEULEMENT des corps high-HP
  adjacents** : la riposte FJ frappe un tank qui SURVIT = pas de kill = pas de revive = mort
  permanente (vérifié : tué avec Adamatar 10038 + Isabella 6604 adjacents → FJ a frappé Isabella
  4678, 6604→1926 survécu → no revive, FuelledByFury strippé, Titus resté mort).
  ⚠ **RE-CONFIRMÉ seed 70058 (revive gated sur la DÉFAITE par la riposte FJ — n=2)** : i2 FuelledByFury =
  « The first time each turn he defeats an enemy with an attack triggered by Final Vengeance he is immediately
  revived with a maximum of 5456 Health » → la riposte doit **DÉFAIRE (tuer)** la cible, pas seulement la chiper.
  Vérifié : Titus tué à 2314 par Aesoth VexillaMagnifica (WasOverkilled=0) avec **SEULEMENT le tank Aesoth 11044
  adjacent** → la riposte FJ a frappé Aesoth 587 (−66% absorbé par le self-debuff de VexillaMagnifica), Aesoth
  a survécu → no kill → no revive = mort PERMANENTE confirmée. ⚠ **BeastSnagga/BeastSlayer = +20% mêlée vs mes
  unités `BigTarget`/`Vehicle`** (observé seed 70058 : amplifie ses coups sur Aesoth BigTarget / Sy-gex Vehicle).
  `▸ Tac: rôle=carry · menace=high (FinalJustice non-overkillable 1ʳᵉ mort/tour + revive-to-5456 si FJ kill + TacticalPrecision re-armé sur revive + BeastSlayer/BeastSnagga +20% vs mes BigTarget/Vehicle) · counter=le finir avec UNIQUEMENT des corps high-HP adjacents (FJ ne peut alors sécuriser aucun kill → pas de revive, mort permanente — vécu seed 70004 ET 70058 : Aesoth 11044 seul adjacent → FJ 587, survécu, no revive) ; ÉCARTER tout fragile/bas-PV de l'adjacence avant le coup fatal (sinon FJ le tue → Titus revive) ; alternative = l'Overkiller (la protection no-Overkill ET le revive sont « 1ʳᵉ fois/tour ») [n=2, 70004+70058]`
- **darkaAzrael « Azrael » (Dark Angels, ranged r2 + Overwatch turret)** — `DarkTalonStrike`
  (actif r2 : **1× DirectDamage Pierce100** sur la cible + **6× Bolter sur TOUS les ennemis en ligne
  droite ininterrompue depuis la cible** ; tous les touchés deviennent **Suppressed** ; le Direct
  Pierce100 **bypass armure ET TerminatorArmour** (Direct exclu de la réduction, cf. §1) → outil de
  décapitation/chunk anti-tank-blindé qui catche un 2ᵉ ennemi aligné en splash (vérifié seed 70001 :
  5124 Direct sur Mataneo + 1189 Bolter splash sur leur Dante aligné). ⚠ **Pinned (move-1) sur les touchés
  + once-per-battle** observés n=1 mais NON dans l'i2 de l'ability → cf. H38, traiter comme hypothèse.
  `Overwatch` (cf. §1 — **gate = NOT-attacked, pas not-moved** ; le tenir SANS attaquer ré-arme l'Overwatch
  dans le tour adverse). `LionHelm` (passif, **range 2** : les alliés à ≤2 hex font **+437 dmg sur leurs
  propres attaques déclenchées par Overwatch** → permet des reaction-kills multi-source quand des alliés
  sont groupés autour d'Azrael ; vérifié seed 70001 sur le dive ennemi). `FinalJustice` (cf. §1).
  `▸ Tac: rôle=carry/turret · menace=high (DarkTalonStrike Direct Pierce100 bypass armure/TermArmour + ligne Bolter qui catche un 2ᵉ ennemi aligné + Overwatch turret + LionHelm boost les OW alliés) · counter=si ENNEMI, ne pas l'aligner avec une 2ᵉ unité (la ligne Bolter splash) ni pather dans son arc Overwatch armé ; si à MOI, **HOLD Azrael SANS attaquer pour garder l'OW armé** dans le tour adverse (gate=not-attacked) + grouper des alliés à ≤2 hex pour le boost LionHelm → le dive ennemi se fait reaction-killer en multi-source ; réserver le Direct DarkTalonStrike pour un tank Psychic/Direct-only (Njal TerminatorArmour) OU un deep-striker à Pinner ; NE PAS le pousser forward pour un K? non-garanti — le HOLD armé vaut mieux (vécu seed 70001 : held → 11510 dmg de réactions, 2 kills) [n=1, 70001]`
- **tauCrisis « Re'vas » (Tau, Flying, Mechanical)** — `EarlyWarningOverride` : summon 2 Shield Drones
  **+ elle s'arme en OVERWATCH jusqu'à son prochain tour (+1892 dmg)** ET **se ré-arme (reste en
  Overwatch, −1 hit par chaîne) à chaque kill d'Overwatch** → sa zone est interdite. L'Overwatch est
  une riposte **déclenchée par un ennemi qui BOUGE dans sa portée** au tour adverse (distinct de la
  danger zone statique) : router un move dans son arc r2 = tir gratuit, souvent **létal** (Pulse +
  CyclicIonBlaster 3 hits + 1892 ; vérifié : a tué mon Nicodemus 9035→0 en se déplaçant dans l'arc
  malgré le warning ` [OVERWATCH] armed`). **Ne JAMAIS pather dans l'arc d'un Overwatcher armé** ;
  contourner ou le tuer/déplacer d'abord. ⚠️ **GAP outillage** : pas d'overlay des zones d'overwatch
  armé → lire l'effet armé dans decisionView.effects. ⚠ **[indispo] après usage = once-per-turn**
  (EarlyWarningOverride pas re-castable immédiatement le tour suivant, vérifié seed 70000) → la turret n'est
  pas re-armable à volonté ; planifier un seul gros tour d'Overwatch, pas une réaction garantie chaque round.
  `RangedSpecialist`, `BigTarget`, Mechanical.
  `▸ Tac: rôle=turret défensif (à MOI) · menace/valeur=high (EarlyWarningOverride = arme Re'vas en Overwatch +1892 + 2 Shield Drones + ré-arme à chaque kill OW + BigTarget −1 hit ranged aux adjacents) · usage à MOI = poser EarlyWarningOverride et HOLD (ne pas attaquer = garder l'OW armé) pour punir le dive ennemi en réactions ; ⚠ once-per-turn ([indispo] après cast) → ne PAS compter sur une masse de réactions chaque tour, la fenêtre est unique/cd (vécu seed 70000 : la punition du dive a été ÉMOUSSÉE faute d'OW dispo le tour clé R3) ; coller mes fragiles BigTarget adjacents pour le −1 hit ranged ; les drones non couverts par BigTarget ne sont PAS protégés du Psychic NoBlocking ; ⚠ côté ENNEMI = anchor turret/screen qui out-range une approche melee et ÉCRANE le soft backline (Eldryon/Abraxas) de mon reach (vécu seed 70052 : EWO castée T1 = 2 Shield Drones u148/u152 3989 + OW armé [effects Overwatch_AutoAttack + EarlyWarningOverride_ReactivateOverwatch] ; a avancé en flanc (2,1) comme front screen durable → engines softs inatteignables = composante de la loss de reach) ; ✅ **côté À MOI = a PORTÉ un W (vécu seed 70056)** : EWO casté T1 (Overwatch armé + 2 drones), HOLD → un roster adverse 100% melee CONTRAINT de diver → l'Overwatch a chunké le Tanksmasha qui dive 10040→6725 AVANT mon tour, puis la masse de réactions (~16.7k sur 2 tours adverses) a tué Ragnar/Atlacoya-enemy/Darkstrider sans dépenser mes actions = la moitié RÉCIPROQUE de H03 ; le BigTarget −1 hit ranged a screené mes adjacents ; ne JAMAIS pather dans son arc r2 [n=3, 70000/70052/70056]`
  `▸ Tac (n+1 à MOI, seed 70060 W) : ✅ EWO Overwatch-turret a RE-PORTÉ un W — casté T2 (2 Shield Drones + OW armé +1892, re-arm −1 hit par kill OW) → sur le dive d'un ennemi all-melee, l'OW a délivré ~13700 réparti sur Tarvakh+Kharn, scoré 2 KILLS et s'est ré-armé = le CŒUR du mur de réaction « hold-baits-the-dive » (couplé à Sarquael GrimRetribution held-OW + Aun'Shi −50% aura → ~18638 total, 2 carries morts T2 zéro perte). PLAY = armer EWO + HOLD le cluster cohésif (ne PAS pousser) ; chaque kill OW prolonge la chaîne à hit-count décroissant. Confirme « le reaction-engine PORTE le W si la ligne reste défensive » (pattern 96002/98002/70001/70056) [n=4, 70000/70052/70056/70060]`
- **templHelbrecht (Black Templars)** — `CrusadeOfWrath` (équipe r2 : +364 dmg + pierce).
  `Parry` (−1 hit aux multi-hit subis → mes multi-hit moins efficaces). `FinalJustice` (§1 — riposte
  normale à la mort SAUF Overkill). `DestroyTheWitch` (+move + dmg vs Psykers).
  `▸ Tac: rôle=engine · menace=high (CrusadeOfWrath = team +364 dmg/+24% pierce melee = BUFF-ENGINE qui amplifie le focus de l'équipe ; DestroyTheWitch +1 move +1091 melee vs mes Psykers = fait de mes Psyker des cibles prioritaires à screener ; FinalJustice riposte de mort) · counter=casser le buff-engine en le tuant tôt effondre l'amplification (vécu seed 98004 : Asmodai mark → Haarken Herald 5364 → Makhotep 2125 → tué en réaction Nicodemus 1391, pas de FJ visible = burst multi-source/overkill) ; Overkill OU absence de cible éligible pour neutraliser FinalJustice ; Parry → préférer un GROS coup unique aux multi-hit (Parry retire 1 hit) ; tuable par réactions/Overwatch (vécu seed 96002 : tué 891 HP par Sy-gex Overwatch + réaction Burchard SANS FinalJustice visible = Overkill/burst multi-source, le Pinned ne bloque que l'Overwatch, jamais FinalJustice) [n=2]`
  `▸ Tac (n+1 OVERKILL-DEFEATS-FJ, seed 70057 W, confirmé Verif) : buff-engine (CrusadeOfWrath) à tuer EARLY pour collapse l'amplification melee de l'équipe — tué T4 AVANT qu'il amplifie une swing mêlée. 9539 PV, soft, no Resilient → Mataneo normal one-shot ~half (7984) depuis adjacent. ⚠ FinalJustice neutralisé par **OVERKILL multi-source** : Mataneo 7984 + drone 1555 (`Attack_WasOverkill=1`) → FJ NON déclenchée (confirme i2 « unless Overkilled » §1). DOCTRINE = empiler assez de dmg combiné pour garantir l'Overkill margin sur Helbrecht plutôt qu'un kill exact-HP (qui ferait fire la riposte) [n=3, +70057]`
- **genesBiophagus « Hollan » (Genestealer)** — **MOTEUR de l'équipe** : `Healer` +
  `TwistedScience` (chaque allié soigné par Hollan est affecté **jusqu'à sa mort**, gagne **+2183 PV +
  +2183 max-HP**, 1× par unité non-réappliquable ; les GSC affectés +364 dmg ; Hollan peut soigner des
  full-HP pour le trigger → ses alliés snowballent en murs, vécu Eldryon/Aesoth pumpés 10.5k/14k ;
  **AUCUNE restriction d'adjacence/portée sur le PASSIF lui-même** — la portée vit uniquement sur
  l'ACTION de heal de Hollan, donc une fois soigné un allié backline NON-adjacent reste un mur pour le
  combat ; vérifié seed 97001 : Sho'syl 6527→9519 et Tarvakh 9537→12529 pompés depuis row 9 ; vérifié seed
  98001 : Xybia 5522→8514 dès T1) +
  `AberrantHypermorph` (summon 5456 PV). `Ambush` (§1 — lui ET son Aberrant). ⚠ **TwistedScience s'applique à
  N'IMPORTE QUEL allié healé par Hollan, summons INCLUS** : un Aberrant healé sur revive est explicitement en scope
  (i2 : « Units healed by Hollan, other than himself, are affected … immediately gain 2183 Health and their maximum
  Health increases by the same amount ») → vérifié seed 98001, l'Aberrant ressuscité pompé à **10469** (base 5456).
  Traiter CHAQUE heal de Hollan comme un événement d'inflation de stats PERMANENT (jusqu'à défaite, 1×/unité,
  non-stackable). → **kill prioritaire TÔT et PERMANENT** (coupe heal/buff/summon) ; détruire ses decoys (Steppable,
  §1 — marcher dessus) sinon il revient ; 2ᵉ kill permanent.
  `▸ Tac: rôle=engine · menace=CRITICAL (sustain-engine : pompe les alliés ET summons en murs permanents +2183 PV one-time + Aberrant summons + Ambush revive ; couplé à un Seeker-engine comme Sho'syl = backline qui out-sustain un roster mêlée) · counter=le tuer TÔT et PERMANENT (avant qu'il soigne quiconque), focaliser le PUMPER pas l'output pumpé ; via reach r3+/deep-strike/flyer/assassin ; vs un roster pur melee/r2 PAS de counter s'il reste row 9 (inatteignable seed 97001 → loss structurelle au recon) MAIS s'il est ATTEIGNABLE (mid-board) il meurt comme tout soft non-Resilient — Snotflogga l'a tué 2× (permanent past Ambush) seed 98001 = W ; ⚠ le harness n'expose PAS l'action Healer via act ability → même MON Hollan ne peut pas caster TwistedScience comme oracle [n=3, 97001/98001/…]`
- **worldEightbound « Azkor » (World Eaters ; Daemon/Resilient/Terrifying/Unstoppable)**
  — **`OverwhelmingWrath`** : Taunt tous les adjacents + −64% dmg ranged subi, puis
  **AoE (2× à tous les adjacents) au DÉBUT de son tour SUIVANT** (retardée). Combo fort :
  Taunter un cluster sur ce tank → l'AoE retardée nettoie (a tué Biophagus + chunké 2).
  `BeaconOfRage` (+315 dmg/coup subi, max 8 ; partage aux Chaos adjacents s'il a tué).
- **tyranWingedPrime (Tyranids, Flying)** — **MOTEUR de SUMMONS** : `AlphaWarrior`
  (Warrior 5820 PV s'il n'a pas bougé) + `SynapticLinchpin` (Hormagaunt sur attaque
  Synapse non-tuante, max 4) → snowball de board (fini 8v1). `Synapse`, `FinalJustice`.
  (Summons : agissent 1× à la création puis **réagissent** — overwatch-like.)
  **`SynapticLinchpin`** (i2-confirmé seed 97002 + seed 70006) : toute attaque NORMALE non-tuante du Winged Prime
  **OU de tout allié Synapse** sur un ennemi summon **1 Hormagaunt adjacent à la cible**, qui **attaque
  immédiatement** l'ennemi (cap 4 Hormagaunts ; HP/Dmg/Arm scalent avec le rank — base ~2183, observé
  2992). ⚠ Confirmé seed 70006 : une normale du Winged Prime sur ma Judh **qui A SURVÉCU** (plancher 50%
  HypersensoryAbilities) a IMMÉDIATEMENT summon un Hormagaunt (u150) adjacent → l'engine fire sur N'IMPORTE quelle
  normale Synapse qui NE TUE PAS la cible (la survie via floor déclenche le summon). ⚠ Une fois que le Winged Prime
  a BOUGÉ il ne peut plus `AlphaWarrior`, mais ses attaques normales **continuent de spawner des Hormagaunts** →
  le tuer AVANT qu'il attaque (retire CETTE source ; d'autres unités Synapse trigger encore le passif) (et
  **OVERKILL** pour sa FinalJustice).
  `▸ Tac: rôle=engine · menace=high (double summon-engine : AlphaWarrior si immobile + Hormagaunt par normale non-tuante ; FinalJustice ; soft 10038, no-Resilient) · counter=le tuer T1-T2 ATTEIGNABLE quand l'IA dive (vécu seed 70006 : une AoE ranged Volk FrenziedFiring l'a chunké 9066→1627 depuis la tuile courante ET splash les adjacents + kill un Hormagaunt frais dans le MÊME cast = brise le summon-engine + chip l'anvil voisin + nie le snowball simultanément) ; ⚠⚠ **OVERKILL (>2× PV restants) OU finir au RANGE sans fragile adjacent** — FinalJustice fire sur toute mort NON-overkill et choisit une cible adjacente éligible (vécu seed 70006 : K! non-overkill 1627 dealt = exactement les PV restants → FJ a TUÉ ma Judh 230 PV adjacente ; le label K! n'a PAS warné car hits sommés = PV restants, aucune marge ; cf. seed 97002 : a riposté ~6 hits sur Aesoth) ; nier sa 1ʳᵉ normale non-tuante stoppe le snowball SynapticLinchpin Hormagaunt ; killable aussi via burst WarHowl (Ragnar 8652-10038 K? observé) [n=2, 97002/70006]`
- **tyranTyrantGuard « Tyrant Guard » (Tyranids, move3, ~12.5k PV, anvil)** — `BigTarget` (alliés
  adjacents −1 hit ranged ; **non déplaçable**), `GuardianOrganism` (−33% dmg subi / cap **−1455/hit**
  s'il **n'a pas bougé** le tour précédent OU est dans une aura Synapse → ~70% de réduction empilé à BigTarget ;
  ⚠ **ne couvre QUE les alliés dans la zone BigTarget de TG** (adjacents) — les allies hors adjacence (drones,
  backline) ne bénéficient PAS de la réduction, vécu seed 70000 : TG gardé full 12548 mais mes drones non-couverts
  morts ; ⚠ **ne réduit PAS le Psychic NoBlocking** type StormOfWrath qui bypasse Block — vécu seed 70000),
  `CrushingStrike` (+dmg mêlée normale **s'il n'a PAS bougé**), `CrushingClaws` (Taunt + push + Suppress ;
  ⚠ pose en moteur Taunted_BlockMovement + Taunted_CantUseAbility + Pinned = **engine-disable propre 1 round**
  d'un Psyker/summoner soft — vécu seed 70000 : Thaumachus n'a JAMAIS casté AttemptedPossession/ArcaneShield, cf. H30).
  Mur d'attrition quasi-inkillable au chip ranged low-pierce (vérifié seed 97002 : SquigLaunchas Pierce1
  full-pierce quand même ~70% réduit). Focus-killer de mes corps deep/isolés (2748+1793 sur Mataneo).
  `▸ Tac: rôle=anvil · menace=high (12.5k + GuardianOrganism −33%/−1455 + BigTarget = ~70% réduction ; focus-killer de mes corps isolés) · counter=ne PAS investir d'output dessus (puit de dégâts) ; le FAIRE bouger (zoner) pour stripper GuardianOrganism/CrushingStrike ; l'ignorer et racer les unités softs ; ne JAMAIS lui présenter un corps isolé (vécu seed 97002 : a co-tué Mataneo deep) ; ⚠ un Direct Pierce100 (DoomSiren) BYPASS son armure → le chunker GRATIS en collatéral splash quand il jouxte la cible primaire (vécu seed 70002 : DoomSiren adjacent-à-cible -6363 + Burchard Frag leftover-Blast l'a FINI 2759 = anvil 12.5k tombé sans investir d'action dédiée) [n=2, 70002]`
  `▸ Tac (CORRECTION KILLABILITÉ — seed 70054) : ⚠ TG n'est PAS Resilient. GuardianOrganism = −33% dmg/hit (cappé) quand en range Synapse OU s'il n'a PAS bougé le tour précédent ; BigTarget n'ajoute AUCUNE protection contre les dégâts. C'est une RÉDUCTION en pourcentage, PAS une immunité — il n'y a AUCUN filet survive-at-1HP. Donc QUAND c'est l'anvil FOCUSABLE non-Resilient sur ma ligne et que le chip-only PERD, un overkill multi-source en UN tour le tue OUTRIGHT (vécu seed 70054 : Darkstrider 4559 + Isaak 3362 + Corrodius 2739 + Dante 1888 = 12548 → mort en un tour ; le guard a flippé d'un plan défensif perdant −2.5 à FOCUS-FIRST +1.16). NUANCE vs le « ne pas investir d'output » ci-dessus : ce réflexe TIENT quand le TG est juste un écran qu'on peut ignorer/racer ; il NE TIENT PAS quand le TG est l'anvil focusable sur ma ligne et que l'attrition chip-only est en train de perdre — réserver/concentrer le burst pour un kill one-turn. Markerlight (Darkstrider en 1er) pumpe ce focus. La réduction −33% ralentit mais n'empêche PAS un overkill coordonné [n=1, 70054]`
  `▸ Tac (CONFIRM n+1 killabilité + COÛT — seed 70059 W) : confirme NON-Resilient → un overkill one-turn multi-source le tue OUTRIGHT quand il dive forward (vécu : il a BOUGÉ en divant → a perdu CrushingStrike/GuardianOrganism → strippé sa réduction ; chunké PlagueWind 3154 + DestroyerHive 3369 puis Kharn KillMaimBurn K! 6025 = mort). ⚠ COÛT CONFIRMÉ : tuer le TG quand c'est l'anvil focusable adjacent a EXIGÉ une tuile mêlée forward → mon carry (Kharn) committé là s'est fait focus-killer = trade carry-pour-anvil. Donc « le tuer quand c'est l'anvil focusable » TIENT, mais peser le COÛT forward : si tuer le TG exige un CARRY au front, préférer tuer l'ENGINE (Ragnar) au range et laisser le TG, OU sacrifier le corps le plus expendable. La réduction −33% est strippée dès qu'il bouge (dive) → l'attaquant qui le force à diver le rend plus tuable [n=2, 70054/70059]`
- **blackTerminator « Angrax » (Black Legion, ~11k PV, anvil)** — `TeleportStrike` (deep strike : drop
  tout hex libre non-adjacent). `BringerOfDespair` (actif **Melee, 4× sur la cible + 4× un autre ennemi
  adjacent**, ~1528-1964/hit @lvl65) — **multi-hit qui BAT le Resilient** (1er hit floor la cible à 1, 2e
  hit tue depuis 1, sauf si un hit est bloqué/manqué ; vérifié seed 95002 : a tué Yarrick Resilient 570 PV).
  `HatefulAssault` (overwatch mêlée, cf. §3). `TerminatorArmour` (1ʳᵉ attaque/tour réduite SAUF Psychic/
  Direct ; **PAS Resilient**).
  `▸ Tac: rôle=anvil · menace=med (TerminatorArmour + ~11k PV = durable, mais sans Resilient ni self-heal il n'est pas un wincon ; sert d'ÉCRAN deep-strike pour les engines backline) · counter=Psychic/Direct passe à plein (bypasse TerminatorArmour) ; sinon focus multi-attaquant (la 2ᵉ attaque distincte du tour tape plein), ou AoE chip (Calgar Gauntlets l'a chunké 6517→4287 en un AoE qui touchait aussi Exitor, seed 97001) ; ⚠ ne PAS dumper tout le burst dessus pendant que les vrais engines (Sho'syl/Hollan) restent intouchés derrière — focuser le wincon d'abord (vécu seed 95002 : Angrax 11046 jamais atteint un seuil tuable) ; usage à MOI : BringerOfDespair = mon outil anti-Resilient (bypass le clamp en multi-hit) ; ⚠ CONFIRMÉ écran-pas-wincon (vécu seed 70004 : acté hors Deep Strike T2 puis MORT dans ma cascade de réactions au dive ~7000+ depuis mon cluster — correctement NON priorisé sur Tigurius l'engine) [n=3]`
- **spaceWulfen « Ulf » (Space Wolves)** — **`SavageKiller`** (réaction mêlée, 5 hits Power,
  PiercingRatio 40) : se déclenche (a) quand un **Summon spawn/bouge adjacent** à Ulf, et
  (b) quand **n'importe quel ennemi adjacent tente un actif** — dans le cas (b) les dégâts
  **résolvent AVANT** que l'actif s'active → counter anti-summon/anti-caster (fort vs
  summon/dive-heavy ; punit l'adjacence + l'usage d'actif de façon préemptive). Vérifié :
  ~7k sur un Winged Prime qui dive + kill d'un Tyranid Warrior summon spawné adjacent, **en
  réaction**, avant que l'ennemi agisse. `GreatFrostAxe` (gros + Ice). `FinalJustice`.
  ⚠ **SavageKiller + FinalJustice synergie (vérifié seed 70004)** : SavageKiller intercepte
  TOUT actif cast adjacent à Ulf (fire son 5-hit Power AVANT que l'actif résolve → peut le
  NÉGOCIER en tuant le caster mid-cast — a killed Tigurius mid-StormOfWrath 2754+2958+813).
  FinalJustice fire une free normale à la mort SAUF Overkill — un **kill exact-HP n'est PAS
  un Overkill** donc FinalJustice fire quand même (a killed Sy-gex à exactement 5724 PV avec
  5724 dmg). Combinés, Ulf menace des réactions létales sur les casters ET riposte sur le coup
  fatal → corps de réaction de haute valeur **même fragile ou ressuscité** (Isabella peut le
  ramener pour relancer le moteur, cf. §5bis).
  `▸ Tac: rôle=engine de réaction · menace/valeur=high (à MOI : SavageKiller pré-empte tout caster/summon adjacent — tue Tigurius mid-cast — + FinalJustice riposte sur sa mort, fire même à kill exact-HP) · usage à MOI = bait le dive IA sur un cluster cohésif (NE PAS le sur-étendre forward) → l'ennemi qui cast adjacent meurt en réaction AVANT d'agir ; le garder comme anchor SavageKiller persistant (vécu seed 70004 : 26k réactions T2 tuent Tigurius+Angrax à 0 coût ; ⚠ committé adjacent à Sy-gex T3 = focus-killé, net OK car FJ a killed Sy-gex mais a dépensé l'anchor) ; ressuscitable par Isabella (RitesOfRestoration) pour relancer le moteur [n=1, 70004]`
  `▸ Tac (ENNEMI Ulf) : rôle=control · menace=med (SavageKiller 5-hit réaction vs caster/summon adjacent + GreatFrostAxe + FinalJustice ; soft-ish ~9037, PAS de Resilient) · counter=NE rien caster/summon adjacent à lui (sinon SavageKiller fire) ; le laisser DIVER dans un Overwatch ranged armé (Sy-gex r3) → reaction-killé sur la dive sans déclencher SavageKiller (vécu seed 70058 : pré-chunké BasiliskBarrage T1 puis 1875+1473+1312=4660→0 par l'Overwatch sur le dive) ; soft no-Resilient → K! propre une fois reachable [n=1, 70058]`
- **genesKelermorph « Judh » (Genestealer)** — `HeroicFusillade` (ability **move+attaque** : cible un
  ennemi qui possède une **case libre adjacente atteignable à move-range 2** de la position courante de
  Judh (ou si Judh est déjà adjacente) ; Judh **se déplace sur cette case libre** puis frappe **6×**
  la cible + **tous les ennemis l'entourant** (Projectile, +crit par case libre autour de la cible).
  ⚠ **injouable** (`mutated=False` silencieux) si AUCUNE case adjacente à la cible n'est à reach-2 →
  **pré-positionner** Judh pour amener une case valide à portée AVANT de lancer (vécu seed 96002 : 2
  tentatives ratées depuis (1,6)/(2,7) → pré-move (2,8) → réussie sur 3 cibles). **Redevient utilisable
  après résurrection Ambush** même si déjà consommée). `HypersensoryAbilities` (**1ᵉʳ coup de CHAQUE TOUR ENNEMI
  seulement** : plancher 50% PV + déplace + decoy + contre). ⚠ **Le floor est scopé « 1ᵉʳ coup CHAQUE tour ennemi »**
  (vérifié seed 70006) : les hits SUIVANTS du même tour ennemi chip normalement (focus ~5793 → survie à 230 PV), et
  le floor **ne s'applique PAS sur le tour JOUEUR** (un FinalJustice/ability sur MON tour la tue normalement —
  vécu : FJ du Winged Prime l'a tuée à 230 sur mon tour). `Ambush` (§1 — 1ʳᵉ mort SEULEMENT → decoy + **resurrect
  FULL HP au début de SON prochain tour** si un decoy ami survit ; **2ᵉ mort ne ressuscite jamais**,
  first-defeat-only). NET = très STICKY : survit à un focus multi-hit à ~50%, peut mourir à une ability tour-joueur,
  et revient full HP le round suivant → harceleuse forward résiliente. Ranged très survivable.
  `▸ Tac: rôle=carry · menace=high (ranged survivable + AoE 6-hit + floor 50% 1er-coup-tour-ennemi + Ambush full-HP revive) · counter=si ENNEMI, clear TOUS ses decoys (2 sources : Hypersensory + Ambush) pour rendre un kill définitif, et la tuer sur MON tour (le floor ne protège PAS sur le tour joueur) ; si à MOI, pré-positionner pour la contrainte HeroicFusillade move-range-2 adjacente AVANT de lancer (sinon no-op silencieux) ; ⚠ NE PAS la laisser fragile (≤ ~50% PV restants) adjacente à un FJ-carrier ennemi sur MON tour — un kill non-overkill du carrier déclenche une FJ qui peut la tuer (vécu seed 70006 : FJ du Winged Prime l'a tuée à 230, lavé seulement par Ambush) ; ⚠ menace contributive confirmée seed 70050 (HeroicFusillade a contribué ~5k au focus de 34887 dmg qui a wipe 4 de mes units en un tour ennemi — non engagée par moi car le board a flippé d'abord) ; ⚠ **n+1 (vécu seed 70061)** : tuée une fois T3 (Certus OW) mais decoy survivant → revived FULL via Ambush ; sur le re-kill j'ai **single-sourcé Makhotep → seulement FLOORED 1553→776** puis sa contre+le tour ennemi ont tué Makhotep. ⚠ **CONTRADICTION DE MENACE RÉSOLUE (notes)** : j'ai d'abord lu le floor comme s'appliquant sur MON tour (776 = exactement 50%) → MISREAD ; Verif gameconfig CONFIRME le scope i2 « 1er coup chaque tour ENNEMI seulement » (le floor NE protège PAS sur le tour joueur) → la note ci-dessus (l.800-805) TIENT. Pour la tuer : clear les decoys (2 sources) ET la frapper sur MON tour OU stacker un 2ᵉ attaquant ce tour si on la frappe au tour ennemi (1 source single = seulement floor) [n=4, 70006/70050/70061]`
- **MoW astraOrdnanceBattery (Imperial)** — `MalleusRocketLauncher` : **barrage RETARDÉ**
  (marque un hex via `--to`, fire au DÉBUT du tour MoW SUIVANT ; AoE large + Suppress).
  `ForwardSpotter` : summon Guardsman (cible un allié) qui **attaque immédiatement**.
- **MoW deathCrawler (Death Guard, ennemi)** — `EntropyCannons` / `PlagueburstMortar`
  ne frappent QUE des cibles à **armure réduite OU dans une aura Contagion** → sans ces
  conditions sur le board, ce MoW est largement neutralisé.
- **ultraApothecary (Imperial)** — `Narthecium` : revive un allié **NON-Mechanical**
  **uniquement s'il est ADJACENT** à l'Apothecary **au moment de sa mort** (cap 4365 PV),
  **sauf si le coup létal est un Overkill**. Hard-gated **1×/tour**. Une mort NON-adjacente =
  **perte permanente** même sur un coup non-overkill → garder les unités revivables **collées
  adjacentes** à l'Apothecary. Vécu (perte gratuite) : Atlacoya morte à 2 hex de l'Apothecary
  (BigMek entre les deux) → pas de revive malgré 538 non-overkill.
- **spaceHound « Tjark » (Imperial, mêlée 4× Physical Pierce1 = ignore armure)** — passif
  **`HuntersBeyondDeath`** = aura anti-Psyker positionnelle (« dans les 2 hexes de Tjark ») : les
  Psykers ennemis proches déalent **−582** dmg et (sauf Immune) **perdent le multi-hit de leur tir
  normal** ; Tjark lui-même fait **+582 PAR HIT vs Psykers** (= +2328 sur ses 4 hits → assassin
  anti-Psyker, vérifié : one-shot d'un Neurothrope 8533 PV en une activation). ⚠️ son moindre dmg vs
  NON-Psykers = simplement l'absence du bonus +582, **PAS** son trait Terrifying (Terrifying réduit le
  dmg que Tjark SUBIT, pas celui qu'il INFLIGE). Aura **ancrée sur la source** → strippée dès que Tjark
  meurt → tuer Tjark libère un Psyker suppressé. ⚠ traits additionnels : **`Infiltrate`** (ne déclenche
  PAS l'Overwatch ennemi → peut s'approcher gratis), **`Terrifying`** (réduit la mêlée subie),
  **`GrapnelLauncher`** (tire/repositionne) ; **PAS de Resilient** → un burst ranged peut le tuer franc.
  Il dive agressivement en avant → punir en gardant mes unités ranged en retrait. **Doctrine : prioriser
  Tjark sur les psykers ennemis ; sinon le punir au RANGED quand il s'isole.**
  `▸ Tac: rôle=carry · menace=high (assassin anti-Psyker + dive agressif + Infiltrate no-OW) · counter=RANGED (bypasse Terrifying, pas Resilient → burst le tue franc) ; garder mes ranged en retrait pour punir son dive (vécu seed 95001 : dive forward T2 → ExcruciatingFrequencies crit −4268 puis réaction Aberrant le finit à 237 PV) ; Infiltrate = il peut bouger sans trigger mon OW [n=1]`
  `▸ Tac (CORRECTION CONDITIONNELLE, seed 70051) : rôle=chaff · menace=LOW **quand MON côté n'a AUCUN Psyker** — son passif HuntersBeyondDeath (+582/hit vs Psyker + suppression) est ENTIÈREMENT INERTE faute de cible Psyker → réduit à un melee plat 4× Physical Pierce1 de 8536 PV, no Resilient. Demote high→low ; killable franc (no Resilient), tué en finition T5 (Lucien VisionsOfHeresy). RÈGLE DE RECON : COMPTER les Psykers de MON côté AVANT de craindre son aura (symétrie de l'engine-inerte H02 : une aura anti-X ne vaut que s'il existe une cible X valide). Infiltrate = il dive sans trigger mon OW mais sans valeur d'engine ici [n=1, 70051]`
- **adeptHospitaller « Isabella » (Imperial)** — **MOTEUR de SUSTAIN** : `RitesOfRestoration`
  (heal self + alliés adjacents 2183 ; **ressuscite 1 Imperial Character + jusqu'à 2 Imperial
  Summons** défaits ce combat, à **1819 PV FIXE**, qui ne peuvent agir ce tour ; non-Mechanical
  seulement) + `MedicusMinistorum` (alliés adjacents non-mech : **+873 regen** à chaque fois qu'ils
  SUBISSENT des dégâts, sauf défaite). ⚠ la PV de résurrection est **fixée à 1819** — `ActOfFaith` (de
  Roswitha ou d'un autre Imperial) ne la boost PAS (ActOfFaith ne donne que Crit Chance/Damage, aucun
  PV) ; tout « ressuscité à 2493 » observé = misread/regen post-rez, PAS la rez elle-même (vérifié
  gameconfig seed 95001). ⚠ **`MedicusMinistorum` = heal CROSS-FACTION** (vérifié seed 96001) : « friendly »
  = **MÊME ÉQUIPE, PAS même faction** → soigne TOUT allié adjacent non-mécanique de team 2 ayant subi des
  dégâts, sauf défaite (heal 1197 sur Kharn=Chaos par Isabella=Sisterhood). En Tacticus les équipes
  multi-factions sont la norme → ne pas supposer qu'un healer ne soigne que sa faction. (Ne soigne pas les
  unités mécaniques.) Net : elle **annule kills (revive) et chunks (regen+heal)** plus vite que le
  dmg/tour typique → **prioriser la tuer/silencer** plutôt que re-tuer les revivables dans un miroir de
  sustain. **PAS de Resilient, PAS de FinalJustice** → n'importe quel K! la défait proprement ; elle se
  retire après avoir healé → la catcher au RANGED. Vérifié : a ressuscité Dante + ramené Shiron
  ~3172→7880 en un cycle ; seed 95001 a ressuscité Roswitha une fois avant d'être tuée.
  ⚠ **À MOI (vérifié seed 70004)** : RitesOfRestoration peut **restaurer un moteur de réaction** — a ressuscité
  mon Ulf défait (Imperial Character) à 2493 PV (1819 base scaled) dans un hex libre adjacent (TurnFinished=1 = ne
  peut agir ce tour) + self-heal 2992 → a relancé SavageKiller/FinalJustice d'Ulf. ⚠ **[indispo] après UN usage**
  (once-per-battle ou long-cd, cf. H13 hero-active) → c'est un swing UNIQUE : le réserver pour ramener le corps le
  plus impactant (reaction-engine, carry), pas le 1er mort venu.
  `▸ Tac: rôle=engine · menace=critical (resurrect chain + heal/regen annule kills+chunks ; MedicusMinistorum heal CROSS-FACTION tout allié same-team adjacent) · counter=la tuer TÔT (T2) AVANT qu'elle use RitesOfRestoration ; pas de Resilient/FinalJustice → tout K! suffit ; se retire après heal → la catcher au RANGED ; H02 prime MAIS exige le REACH — si elle est back-row (row 9) hors portée T1-T2, pré-positionner un dealer ranged T1 pour l'atteindre T2 (vécu seed 95001 : tuée T4 ranged stacké Shiron = W ; vécu seed 96001 : identifiée wincon mais INACCESSIBLE row 9 → jamais atteinte → L ; vécu seed 70050 : identifiée wincon (soft 8533 no-Resilient) mais INATTEIGNABLE row 8-9 à mon roster melee/r2 + 1 move2/r3 dont le seul reach-tool a été deleté par Shadowsun → sustain-engine intact = loss structurelle) · à MOI : RitesOfRestoration = swing UNIQUE ([indispo] après 1 usage) qui ramène un Imperial Character défait (reaction-engine type Ulf SavageKiller) à 1819 PV scaled, ne peut agir ce tour — le réserver pour le corps le plus impactant (vécu seed 70004 : ramené Ulf 2493 → moteur SavageKiller relancé) [n=3 ennemi, +1 mien 70004]`
- **astraPrimarisPsy « Sibyll » (Imperial, Psyker, ranged, fragile ~5522, no Resilient)** — `PsychicMaelstrom`
  (Psychic **Pierce100 + NoBlocking** = ignore armure ET block, hits chaînés ; cf. §1 — délivre plein pot à un
  noyau Mechanical/armuré, vérifié 6866 en un cast 9037→2171). `Nightshroud` (passif : les alliés adjacents
  gagnent **Infiltrate** + infligent **−364/hit** aux ennemis qui les frappent = émousse mes coups sur ses
  voisins). **La cible la plus SOFT d'un roster** (5522) → focus prioritaire.
  `▸ Tac: rôle=control (Psyker-nuke) · menace=med (PsychicMaelstrom Pierce100 NoBlocking ignore mon armure + Nightshroud émousse mes coups sur ses voisins) · counter=la tuer TÔT — fragile 5522, no Resilient → un burst/K? la défait franc (vécu seed 70051 : tuée T3 par Lucien) ; priorité car NoBlocking ignore mon armure ET son Nightshroud blunt mes attaques sur ses adjacents → cible de focus prioritaire avec un autre engine soft (Aethana) [n=1, 70051]`
- **bloodIntercessor « Mataneo » (Blood Angels, deep-strike Imperial)** — `HammerOfWrath` : charge
  (2× Power + 1× Physical AoE adjacents, range 5, gagne Infiltrate) **UNIQUEMENT s'il N'A PAS bougé**
  ce tour ; si **MATANEO lui-même** est <=50% PV, dégâts **doublés** (`HammerOfWrath_ConditionalDamage`
  — c'est SON PV, pas celui de la cible). `AggressiveOnslaught` : à la **charge SEULEMENT**, summon
  **2 Jump Pack Intercessors** (bloodSmnIntercessor, base 3638 PV/1310 dmg/1310 armure — scale avec
  les buffs du match) adjacents à la cible, **attaquant immédiatement** ; ils **quittent le terrain
  au début de chaque tour de Mataneo** (blockers/chip ~1 tour, ne pas compter sur la persistance).
  **Pas de charge** (il a bougé, ou aucun ennemi avec hex libre adjacent en range) = **0 dmg ET 0
  summon** → le tuer/déplacer **avant la charge** nie tout le package. Vérifié : deep-strike isolé
  sans charge T1 (0 dmg, 0 summon) → focus-kill gratuit.
  ⚠️ **GATE no-move = effondrement de dégâts (vérifié seed 97002)** : si Mataneo **a bougé** le tour,
  la charge (2× Power + summon-attack AggressiveOnslaught) ne fire PAS → dégâts **chutent de ~5820
  (2× 2910) à ~1015** (seul un coup réduit/normal part). **NE JAMAIS** compter sur HammerOfWrath
  comme kill quand Mataneo a déjà bougé — c'est la précondition « has not moved » qui produit toute
  la fenêtre létale.
  `▸ Tac: rôle=deep-strike carry/summoner · menace=med (burst conditionnel + 2 summons éphémères) · counter=le tuer/déplacer AVANT la charge ; quand il deep-strike dans ma zone, le punir IMMÉDIATEMENT avant qu'il charge (vécu seed 70001 : deep-struck T1 → Azrael Overwatch 1882, puis T2 Azrael DarkTalonStrike Direct line 5124 + Pinned l'a chunké 7153→2029 ET le Pinned a tué tout move de charge → Shiron 6-hit ranged normal l'a fini 2029 depuis la tuile courante, zéro exposure ; carte exacte « kill/displace AVANT que la charge nullifie le package ») ; usage à MOI = ne committer HammerOfWrath en finisher QUE si Mataneo N'A PAS bougé (gate « has not moved ») ; ⚠ deep-commit solo via HammerOfWrath = corps isolé (les 2 JPI disparaissent au début du tour suivant de Mataneo = pas de support durable) → focus-killé (vécu seed 97002 : commit deep (2,6) chasse Actus, dmg de-buffé ~1015, Mataneo stranded → tué Calandis 4494 + Tyrant Guard) [n=2]`
- **tauShadowsun (Tau)** — **`ExemplarOfTheKauyon` (id 1087) = TÉLÉPORT de repositionnement, PAS un
  nuke ciblé** : la cible = un **hex adjacent à un allié** ; elle s'y téléporte et **auto-attaque
  l'ennemi LE PLUS PROCHE** (2× 2183 Blast), et une **Command-Link Drone** stationnaire est summonée
  dans son ancien hex. Cibler un ENNEMI = invalide (ni téléport ni attaque). La drone **étend l'aura
  ranged** `DefenderOfTheGreaterGood` (+364 dmg ranged + chance d'un hit en plus, T'au dans 2 hexes).
  Pour des dégâts ranged fiables : utiliser son **attaque normale Melta (id 69, r2)**, boostée par
  `RangedSpecialist` (si elle n'a pas démarré adjacente à un ennemi) + DefenderOfTheGreaterGood ;
  `Camouflage` la rend tanky vs ranged. (Chiffres exacts runtime-dépendants.) ⚠ **REACH PLEINE-PLANCHE
  CONFIRMÉ (vécu seed 70050)** : `ExemplarOfTheKauyon` se téléporte sur N'IMPORTE quel hex adjacent à un
  allié (AUCUN cap de move-range) + `Flying` (traverse terrain/units) = **reach pleine-planche** quel que
  soit le terrain ; elle a atteint et 3-hit (3941+3246+1346=KILL) mon Neurothrope depuis la backline puis
  summoné une Command-Link Drone (3989 PV) dans l'hex vacaté. Les 3 hits = normale 2× Blast + 2× Blast
  additionnels de l'ability. → **AUCUNE unité ranged backline n'est en sécurité tant que Shadowsun a un
  allié quelque part près d'elle** : prioriser l'élimination de ses alliés ou de Shadowsun elle-même AVANT
  qu'elle se repositionne ; le danger-zone overlay est INUTILE pour la sécurité d'un fragile vs elle (le
  teleport ignore la portée affichée).
  `▸ Tac: rôle=carry · menace=high (move4 Flying + ExemplarOfTheKauyon teleport = reach pleine-planche + Camouflage [ranged −1/−2/−3 hits] + Infiltrate [no overwatch] + Melta Pierce75 ranged carry — supprime tout fragile pas en row 0-1 ; vécu seed 70050 : a tué mon Neurothrope 8533→0 depuis la backline) · counter=garder mes fragiles row 0-1 INTOUCHABLES ; elle n'a PAS de Resilient → un burst focalisé la tue, mais il faut SURVIVRE à son teleport-reach d'abord (tuer ses alliés-ancres ou elle-même tôt) ; le teleport+Flying rend le danger-zone overlay inutile pour la safety d'un fragile [n=1, 70050]`
- **astraDreir « Dreir » (Astra Militarum ; Hero/Resilient/Unstoppable)** — `ToughToKill` (passif) :
  **regen FIXE au DÉBUT de son tour** (scale jusqu'à **2183** PV/max lvl, `hpToHeal`), **PAS un
  re-heal full/%** ; **plafonné à max PV** ; ALSO −35% crit chance / −1091 crit dmg sur toutes les
  attaques subies. Sa durabilité = cette regen **+ Resilient** (survit à 1 PV sauf Overkill), pas un
  top-to-full. `LeadingTheCharge` (actif) : **hard-gated « Dreir n'a PAS bougé »** ce tour — s'il a
  bougé, indispo même si [prêt]/usable s'affiche. Sur fire : gagne Infiltrate (fin de tour), charge
  un ennemi qui a un hex libre adjacent en move range 4 (3× Power, +10% pierce par allié défait ce
  combat), puis summon jusqu'à **4 Death Riders** (3638 PV/1892 dmg/873 armure) adjacents qui
  attaquent immédiatement. → **agir AVANT de le bouger** + cible avec hex adjacent libre.
  `▸ Tac: rôle=engine (summon + sustain) · menace=high (LeadingTheCharge jusqu'à 4 Death Riders gated « n'a pas bougé » + ToughToKill regen 2183/tour + Resilient + −crit) · counter=TAUNT (CrushingClaws Taunted_CantUseAbility, cf. H30) pour NIER les summons 2 rounds, puis kill PERMANENT via MULTI-HIT (bat Resilient) ou Overkill ; ⚠ **le zero-out ToughToKill bloque le kill SEULEMENT s'il est le DERNIER hit** (cf. H31/H04) : seed 98000 un 4-hit l'a floored à 1 PUIS le 4ᵉ hit = 0 dmg → survécu ; MAIS seed 70008 un 6-hit Gauss l'a floored à 1, un hit MID-séquence a fait 0 (ToughToKill) ET un hit surplus ultérieur (Amount=1) l'a TUÉ depuis 1 PV (WasOverkilled=1) = full kill → un multi-hit À GRAND NOMBRE de hits (surplus >0 past le floor) le finit ; sur un multi-hit court, BUDGÉTISER un finisher séparé ; ToughToKill regen un Dreir à 1 PV jusqu'à 2184 [n=2, 98000/70008]`
- **necroSpyder « Aleph-Null » (Necron, move3, mêlée Particle 5×)** — **NOYAU de SUSTAIN dur** :
  `ScarabHive` (actif) summon **2 Scarab Swarms** (necroSmnSwarm, move4, ~1455 PV baseline + scaling,
  655 dmg, Swarm/Flying) à côté de la cible qui **attaquent IMMÉDIATEMENT** (Piercing 1ᵉʳ hit).
  Stack de self-heal : `LivingMetal` (regen % max PV au début du tour joueur, le rend aussi
  **Mechanical**), `FabricatorClawArray` (passif : répare un Mechanical adjacent **2910** après move,
  sinon fin de tour), `Mechanic` (répare comme action = Damage × max weapon hits). Mechanical ⇒
  ne peut être heal, **seulement repair**. ALSO `Explodes` à la mort (25% PV max Direct à tous les
  adjacents — peut toucher ses propres Scarabs) et les Swarms ont `ReanimationProtocols` (35% revive
  à 25% PV sauf **Overkill**). → focus en **Overkill** (nie Reanimation) + out-tempo avant que le
  moteur repair/summon snowballe (out-DPS le stack de heal de front = impraticable).
  `▸ Tac: rôle=engine (repair-hub) · menace=CRITICAL **SI ≥1 autre allié Mechanical/LivingMetal sur son équipe**, sinon **LOW** (cœur d'un noyau Mechanical auto-réparant : FabricatorClawArray 2910 + Mechanic + LivingMetal/NetherRealmCasket regen alimente toute la grappe blindée — il faut le tuer TÔT) · ⚠ **NUANCE INERTE (vécu seed 70002)** : si Aleph-Null est le SEUL Mechanical du roster adverse, son kit repair/regen est **STRUCTURELLEMENT INERTE** (aucun bénéficiaire = ne peut que se self-regen, jamais amplifier un allié) → demote CRITICAL→LOW, traite-le comme un gros corps soft (recon : compter les autres Mechanical/LivingMetal AVANT de le craindre) · counter=Psychic NoBlocking (PiercingRatio100 + Cannot-be-blocked bypasse TOTALEMENT son armure Mechanical + NetherRealmCasket : 6866 en UN cast 9037→2171, vérifié seed 98003) = le bypass le plus fiable ; mais sans repair-target il est si soft qu'un **2× Flame Brazier le one-shot 9037→0** (vécu seed 70002) ; le finir au RANGED + en **Overkill** (Scarabs ReanimationProtocols + LivingMetal regen %max/tour) ; `Explodes` à la mort (**25% PV max Direct à TOUS les adjacents SEULEMENT — units 2+ hex épargnées** = friendly-fire, kill au RANGE pour garder mes fragiles clear ; vécu seed 70002 : 2259 sur mon Adamatar adjacent, Roswitha 2 hex non touchée) → le tuer DANS son propre cluster pour chunker la grappe gratis (vérifié seed 98003 : Yarrick ennemi 1160→1, Vanguard, Scarab ; seed 98002 : finition Abraxas Psychic r2 → Explodes a friendly-fired Anuphet + un Warrior) ; soft 9037 no-Resilient → killable en réaction s'il dive ; ⚠ chaque repair (FabricatorClaw/Mechanic) sur un carry DakkaDakka (Snappawrecka) **AJOUTE +2 hits** à son attaque (6→16) → tuer Aleph-Null coupe AUSSI le scaling du carry (vécu seed 98000 : repair-hub backline jamais atteint par mon roster mêlée = a décidé l'attrition) ; ⚠ **NUANCE INERTE re-vérifiée DANS MON roster (vécu seed 70005)** : Aleph-Null seul Mechanical de MON équipe → FabricatorClaw INERTE (aucun bénéficiaire), seul LivingMetal self-regen actif = un simple corps soft + son `Explodes` est un RISQUE pour MOI (à sa mort il a friendly-fired mes TG 2259 + Typhus 2259 adjacents tout en tuant l'Aesoth ennemi 759→0) → ne pas coller mes unités à lui s'il peut mourir [n=5, 98000/98002/98003/70002/70005]`
- **necroDestroyer « Imospekh » (Necron, ranged r2, Overwatch+InescapableDeath)** — tourelle OW à chaîne.
  `MultiThreatEliminator` (actif Ranged, **6× Molecular** range 2, PiercingRatio 60 = partiellement
  réduit par l'armure ; les hits restants **chaînent vers un ennemi ADJACENT à la cible**, +1 hit par
  kill, re-cible ; NON réduit par Terrifying = melee-only). Caster l'actif = « a attaqué » → PAS en
  Overwatch ce tour-là. `InescapableDeath` (passif, gameconfig) : **+655 dmg/hit en Overwatch** ET
  **reste en Overwatch sur un kill déclenché par Overwatch** → chaîne de ripostes OW gratuites tant
  qu'il tue. `LivingMetal` (regen %max PV en début de tour ; Mechanical → repair-only, pas heal).
  **Pas Resilient** → tuable proprement une fois atteint (vécu seed 95000 : 8032→0 via Dante
  LightOfSanguinius -4607 + Mataneo HammerOfWrath finish). **H06 CONFIRMÉ live (n=2, seed 70008)** :
  la chaîne InescapableDeath sur Overwatch a fire — 11 OW hits / 8467 dmg, tué un Death Rider (u141, 6 hits)
  puis Imospekh est RESTÉ en Overwatch et a continué sur l'ennemi suivant (u143) en retenant les hits ;
  chaque kill in-chain ajoute +1 hit (MultiThreatEliminator) AVANT le −1 InescapableDeath → cascades longues
  quand ennemis adjacents en range 2. PiercingRatio=60 confirmé partiellement réduit live (Gauss vs MkXGravis
  double-armor → ~1300-1988 net/turn, JAMAIS un armor-bypass).
  `▸ Tac: rôle=control/engine-de-réaction · menace=high (OW + InescapableDeath = chaîne OW sur les kills — un seul tour ennemi a rendu 8467 dmg + 1 kill seed 70008) · counter=approcher sous Infiltrate (Shadowsun/Dante LightOfSanguinius=no-OW) ; pas Resilient → kill franc une fois en portée ; LivingMetal = repair-only → le tuer vite avant que la regen s'accumule · à MOI = LE garder turret-positionné, screené (BigTarget Gulgortz), et NE PAS attaquer avec quand un dive arrive → la value de réaction (chaîne OW) > un actif (vécu seed 70008 : la chaîne OW + InescapableDeath a porté la récupération de 3v6 à 5v2) ; ⚠ côté ADVERSE : son OW armé en r2 GATE mon avance early → NE PAS entrer en r2 (hold/contourner), puis le tuer franc une fois qu'il avance dans ma portée (no-Resilient → kill propre avant que la chaîne OW snowball ; vécu seed 70053 : tué T4 EN ÉVITANT son r2 — Aesoth chunk 5639→855 + Calandis finish — comme l'un des 2 summon/OW engines tués le tour décisif) [n=3, 95000/70008/70053]`
- **thousTzaangor « Yazaghor » (Thousand Sons, Flying, ~6525 PV, Psyker/chaff)** — `WeaverOfFate` (tout
  tour où **3+ ennemis** subissent du Psychic → dégât MAX sur toutes ses attaques ce tour — engine de
  snowball Psychic, cf. §2 Ahriman pour le même trait). `SorcerousFacade` : échange sa position avec un
  Psyker allié (ajoute un bonus Psychic). **Bas PV + Flying mais fragile.**
  `▸ Tac: rôle=chaff/engine · menace=med · counter=le tuer TÔT (6525 PV, fragile, no-Resilient) pour couper le snowball WeaverOfFate (max dmg si 3+ cibles Psychic touchées) ; SorcerousFacade = position-swap → ne pas compter sur sa position fixe ; Flying = slippery à pin → le K! quand en portée ; vécu seed 95000 : survécu 3 rounds malgré -2072 du HammerOfWrath AoE faute de focus ; vécu seed 70002 : tué T1 (DoomSiren primaire -4294 + Burchard Frag finish) = exactement la carte « kill early » ; vécu seed 70009 : K!'d outright par Ragnar WarHowl-buffé (overkillé, Flying Psyker éliminé) → vaut le kill pour nier le moteur Psychic adverse (miroir de mon propre Abraxas/Patermine WeaverOfFate) [n=3, 70002/70009]`
  `▸ Tac (DEMOTE low — WeaverOfFate INERT, seed 70055/70054) : menace=LOW quand l'ENNEMI (son équipe) n'a AUCUN dealer Psychic → WeaverOfFate (3+ ennemis subissent du Psychic → max dmg) ET RealityUnbound (bonus/différent ennemi marqué Psychic) sont PERMANENTS INERTES faute de source Psychic côté SON équipe → Yazaghor réduit à un fragile Common ranged 6525 = simple corps soft, priorité basse. RÈGLE DE RECON (symétrie engine-inerte) : compter les dealers Psychic de SON équipe AVANT de craindre son snowball ; s'il n'y en a aucun → demote. Vécu seed 70055 : WeaverOfFate inert → tué T2 via Archimatos Incursion + Eldryon Executioner. Vécu seed 70054 (n+1) : aucune source Psychic ne touche MES propres units (le trigger compte 3+ de SES ennemis = mes units) → WeaverOfFate inert, démoté à fragile killable et focus-killé T3 avec 3 ranged (clean H03-reciprocal sur son dive isolé à (3,4)). Vécu seed 70058 (n+1) : Yazaghor ENNEMI, aucune source Psychic ne touche mes units → WeaverOfFate inert, demoté à chaff soft → forward-most diver T2, tué T3 par une normale Thaddeus + stun-splash VexillaMagnifica depuis les tuiles courantes (no over-extension) [n=6, 70002/70009/70055/70054/70058]`
- **orksBigMek « Gibbascrapz » (Orks)** — `Mechanic` (répare un Mechanical ami comme action ; heal =
  Damage × max weapon hits = **4** pour Gibbas → quasi-full en une action sur son Grot Tank Mechanical ;
  vérifié : Grot Tank 4338→8974 en un tour → chiper le Tank pendant que Gibbas vit est GÂCHÉ, tuer le
  repair-engine Gibbas, pas le sponge) + **aura `KustomForceField` (+Armure aux alliés ADJACENTS,
  base +437 ; tout > 437 = scaling rareté/star, PAS un rework +599)**. ⚠️ **aura source-anchored** :
  tuer Gibbas **strip immédiatement** l'armure de la grappe (cascade `LoseEffect KustomForceField` +
  `FixedArmor_Modification` retiré → leurs hits subis ~doublent ; vérifié seed 91002) → tuer le Bigmek
  ouvre une grappe blindée. Summon **Grot Tank** (orksGrotTank/orksNpc3GrotTank, ~5093 PV base, ranged
  r3 Blast Pierce15, `Ramshackle` −364 dmg vs ≤30% pierce, Vehicle/Mechanical → repairable par Gibbas,
  Ragnar BeastSlayer +20% mêlée s'applique via Vehicle) qui auto-move+attaque au début de son tour
  (trait `Summon`). **H10 RÉFUTÉ** : tuer Gibbas NON-adjacent au Tank ne le despawn PAS (vérifié seed
  91002 : Gibbas (2,2) mort, Tank (4,4) survit pleine vie) — la seule mécanique de retrait est
  `BattleFatigue` (fuir/retiré si un ami ADJACENT est défait, +chance si overkillé), adjacency-gated.
- **custoAtlacoya « Atlacoya » (Custodes, mêlée)** — `TalonsOfTheEmperor` (**Melee = range 1, frappe
  un ennemi ADJACENT**, profile Power +40% Pierce) : passe en **Direct** (ignore armure/réduction, comme
  Psychic) si la cible est un **Psyker** OU si Atlacoya est adjacente à un Custodes allié. Snowball :
  **+728 dmg par actif utilisé par un Character allié** ce combat. Passif `DaughterOfTheAbyss` (DEUX
  volets) : (1) **OFFENSIF** : +20% Damage aux Psykers ennemis à ≤2 hex ; (2) **DÉFENSIF** : **réduit
  fortement le Psychic SUBI** (−1892 Psychic flat par hit / −33% Psychic aux alliés proches, gameconfig)
  → **neutralise quasi-complètement le Psychic ennemi vs Atlacoya** (vérifié seed 96000 : Patriarch
  `MightFromBelow` Psychic vs Atlacoya = mêmes valeurs que son attaque NORMALE non-Psychic → le Psychic est
  annulé). ⚠ ce n'est PAS une immunité au ranged en général (un ranged NON-Psychic ou un combo heal-block
  la règle quand même à distance — cf. seed 95002 Mephiston). Combiné (1) → Talons sur un Psyker tape
  Direct + amplifié = souvent one-shot d'un caster fragile (vérifié : Eldryon Farseer one-shot 7530).
  `Terrifying`. ⚠ **Talons
  exige l'adjacence (range 1)** : la caster sur une cible non-adjacente est **rejetée silencieusement**
  (`mutated=false`, **aucune erreur**, activation potentiellement gâchée — vérifié seed 95002 : Atlacoya
  (1,3) → cible (3,4), dist 3 → rejet) ; vérifier l'adjacence (glyph/aiMovableTiles) AVANT de caster.
  Note : `Taunted_CantUseAbility` (Xybia MindControl) coupe AUSSI Talons (cf. §1 MindControl). **Doctrine :
  engager les casters ennemis avec Atlacoya en priorité, depuis l'adjacence.**
  `▸ Tac: rôle=anvil/carry · menace=med-high (mur anti-Psyker : Terrifying + Parry + DaughterOfTheAbyss −Psychic ; Talons Direct +20% one-shot un caster fragile ; TalonsOfTheEmperor scale +728/actif allié = snowball si laissée vivante) · counter=si ENNEMI, l'attaquer au RANGED (bypass Terrifying) et en NON-Psychic (DaughterOfTheAbyss annule le Psychic vs elle) ; Parry → ne pas gaspiller un burst multi-hit dessus si d'autres cibles prioritaires (−1 hit) ; soft sans Resilient → tuable en réaction massée (vécu seed 96000 : tuée par Overwatch Azrael FJ + réactions 2781 exact kill) ; si à MOI, l'engager adjacent à un caster ennemi (Direct anti-Psyker) · ⚠ **à MOI = OUTIL DIRECT-vs-Psyker/armor-bypass à RÉSERVER, NE PAS sur-étendre** : Talons range 1 → un move vers une tuile NON-adjacente à un ennemi la laisse SANS cible ET un seul move/tour = STRANDED gâchée (vécu seed 70008 : committée à (5,5) sans vérifier l'adjacence → finie sans cible, impossible de re-move, puis focus-killée T1 = perdu mon 2ᵉ outil bypass-armure → Burchard MkXGravis ungrindable, loss) → vérifier la légalité du move + l'adjacence AVANT de committer son unique move ; la garder shallow/screenée et réservée pour le tank high-armor émergent ; ⚠ **vs un Atlacoya ENNEMI (mirror), mes 3 ranged dealers l'ignorent** (vécu seed 70056 : Re'vas a chunké l'Atlacoya-enemy Terrifying 2956→363 en un tir ranged, pleine valeur ; son angle Talons-Direct-vs-Psyker est MOOT si mon roster n'a aucun Psyker → corps soft sans Resilient tué dans le dive) [n=4, 96000/95002/70008/70056]`
  `▸ Tac (n+1 TalonsOfTheEmperor scaling CONFIRMÉ self-play consensus, seed 80000 W) : **+728/actif allié cumulatif est MASSIF en fin de bataille** — avec seulement 2 actifs utilisés par des alliés (Tigurius StormOfWrath + Sho'syl SeekerMissile), Atlacoya a frappé à 5768 (base ~4365 + 1456 bonus) pour one-shot-finisher Aun'Shi 8536→5768→0 depuis l'adjacence. Séquencer les actifs alliés AVANT TalonsOfTheEmperor : chaque actif allié joué avant son tour gonfle son prochain cast. ⚠ **cross-validé par les DEUX sides du self-play** (A observé son output ; B identifié la menace côté theirs) → [self-play consensus, seed 80000]. [n=5, 96000/95002/70008/70056/80000-sp]`
  `▸ Tac (RÉVISION MENACE — vs un roster PSYKER-HEAVY, seed 70055) : menace=CRITICAL (pas med-high). DaughterOfTheAbyss (−1892 Psychic flat sur elle) réduit le Psychic de mes Psyker-dealers à ~1-2 dmg (vérifié : plans Eldryon/Archimatos [1-1]/[2-2] vs elle TOUTE la partie, elle est restée near-full de mon Psychic) → elle hard-countre le profil de dégâts ENTIER d'un roster Psyker-heavy : Psychic négaté + Terrifying blunte ma mêlée + Parry −1 multi-hit + Talons Direct one-shot un Psyker fragile. Pour un tel roster elle est quasi-IMTUABLE et devient le counter-engine STRUCTUREL de la wincon adverse (endgame 3v2 injouable, seed 70055 L). COUNTER = la tuer EARLY avec du dégât NON-Psychic NON-Terrifying-réduit (RANGED Blast/Physical d'un non-Psyker) ; NE PAS s'appuyer sur des Psykers pour la casser ; si mon roster est Psyker-heavy sans source non-négatée, FLAGGER la loss STRUCTURELLE au recon (miroir de l'engine-inerte : son aura anti-Psychic est LIVE précisément parce que je fielde des Psykers). ⚠ CONTRADICTION de menace assumée : la carte KIT ci-dessus liste menace=med-high (générique) ; vs Psyker-heavy c'est CRITICAL — le contexte du roster décide [n=1, 70055]`
- **admecMarshall « Tan Gi'da » (AdMech, summon-engine)** — `DoctrinaImperatives` (1118, switch
  Protector +582 Armure / Conqueror +582 dmg vs armure réduite, 1×/tour ; **peut attaquer après le
  switch**). Passif `ControlEdict` : sous **Protector**, après CHAQUE attaque de Tan Gi'da, summon
  gratuit d'un **Skitarii Vanguard** (admecSmnVanguard, base 2546 PV, peut scale plus haut) dans un hex
  adjacent libre, **cap 5** ; sous **Conqueror**, les summons Mechanical adjacents co-attaquent sa cible.
  Summons indépendants/persistants → un roster low-output se fait **out-attritionner**. **Tuer Tan Gi'da
  ou casser Protector, pas les Vanguards un par un.** Vanguards = Toxic r2 + RadSaturation.
  `▸ Tac: rôle=engine (summon-engine) · menace=CRITICAL (sous Protector summon 1 Vanguard ~2546-3878 PV par attaque, cap 5, persistants + donne +582 armure aux Mechanical adjacents = blinde la grappe + KardiocoreGalvanus +crit-dmg) · counter=tuer Tan Gi'da OU casser Protector pour stopper le snowball — ne JAMAIS clear les Vanguards un par un (un low-output se fait out-attritionner) ; le +582 armure se bypasse au **Psychic NoBlocking** (cf. §1) ; 8533 PV ranged r2, à atteindre tôt — s'il reste hors reach il summon le board entier (vécu seed 98003 : jamais atteint, a aidé à tuer mes carries via les Vanguards) [n=1]`
  `▸ Tac (n+1 MINE, seed 70057 W, ControlEdict-Protector confirmé Verif) : Tan Gi'da côté MIEN = SCREEN-engine. Sous Protector, chaque attaque normale summon un Skitarii Vanguard (~3878 HP, 1662+886 armure observé) sur un hex adjacent libre (cap 5) → mes attaques génèrent des corps-écrans qui SOAKENT le focus ranged ennemi (drone Sho'syl + Vanguard ont absorbé ~14k vécu seed 70057). Usage = attaquer chaque tour sous Protector pour fabriquer un mur de bodies devant mes fragiles ; MAIS ⚠ NE PAS la pousser forward pour chip (vécu : Tan Gi'da à (5,3) row 3 chunkée 205 HP — over-extension n+1) : la garder shallow, ses Vanguard font le screen, pas son corps avancé. La branche Conqueror fait plutôt co-attaquer tous les Mechanical Summons adjacents sur sa cible. [n=1, 70057-mine]`
- **admecRuststalker « Exitor-Rho » (AdMech, mêlée, move4)** — `CordClaw` (4× Melee Direct Pierce100 →
  ignore armure ; vs Resilient : floored à 1, prévoir finisher). Traits `Infiltrate` (ne déclenche PAS
  l'Overwatch) + `Unstoppable` (ignore les effets de hex qui stoppent). Passif `OptimizedGait` : la clause
  « Exitor-Rho se déplace sur l'hex du mort » fire dès qu'un ennemi ADJACENT à lui est défait par
  **N'IMPORTE QUEL ami Mechanical** (pas seulement lui) → un kill d'un allié Mechanical peut le **tirer
  involontairement en avant** sur l'hex vacant ; surveiller l'exposition. ⚠ **Finisher létal à TOUT HP** :
  move4 + Infiltrate + Direct Pierce100 lui permettent de traverser le board et de one-shot un fragile
  même à très bas PV (vérifié seed 97001 : à 1173 HP il a traversé pour tuer Vindicta 3862+2372+795 en une
  activation).
  `▸ Tac: rôle=chaff/finisher · menace=HIGH (PAS low/skirmisher — move4+Infiltrate+CordClaw Direct Pierce100 = finisher mobile qui ignore armure ET Overwatch) · counter=LE TUER quand un kill est dispo, ne JAMAIS le laisser à bas-PV « parce qu'il est spent » (à 1173 HP il a reach-killed Vindicta) ; sa mobilité + armor-ignore font d'un Exitor bas-PV un kill garanti sur un fragile au tour suivant ; OptimizedGait peut aussi le tirer en avant via les kills d'alliés Mechanical · ✅ **à MOI = OUTIL ANTI-ARMURE PRÉCIEUX À RÉSERVER/PROTÉGER** : CordClaw Direct Pierce100 = un de mes seuls bypass d'un tank MkXGravis/double-armure → ne PAS le sur-étendre T1 (vécu seed 70008 : Exitor à (3,5) over-étendu T1 → focus-killé → j'ai perdu mon SEUL bypass du MkXGravis de Burchard → tank ungrindable, loss) ; le garder SHALLOW/screené et le réserver pour le tank high-armor émergent ; il one-shot un summon-engine soft (Archimatos 8034→0 T2) = aussi un finisher d'engine [n=2, 97001/70008]`
- **admecDestroyer « Sy-gex » (AdMech, move2, Mechanical/Vehicle/HeavyWeapon)** — **Overwatcher RANGED
  trait-natif** : arme normale **4× Physical r3** (Pierce1) → s'il n'attaque pas en NORMAL, il s'arme en
  Overwatch et **tout ennemi qui BOUGE dans son arc r3 (mêlée OU non)** se prend la volée 4 hits gratis
  au tour adverse (vécu seed 93000 : ~5418 sur un Volk entrant dans l'arc — 879+1699+1650+1190 — AVANT
  qu'il agisse). `SentinelDirectives` (actif r3, 1 hit + Suppress 1 round, interdit si ennemi adjacent)
  **ne finit PAS son tour et ne DÉSARME PAS l'Overwatch** — seule une **attaque NORMALE** désarme → il
  peut FIRE l'actif PUIS overwatcher le même tour (**fire-then-overwatch double-menace**). `HeavyGravCannon`
  (+364 dmg / +60% pierce vs Gravis/TerminatorArmour/Mechanical → tape plus fort un terminator). `HeavyWeapon`
  (+25% ranged s'il n'a pas bougé). Counter (cf. §1 Overwatch) : ne PAS pather dans l'arc r3, out-range,
  ou forcer l'OW sur un chaff d'abord ; Vehicle → bonus BeastSlayer applicable.
  `▸ Tac: rôle=carry/control · menace=high (ranged punch + Overwatch armé r3 + HeavyGravCannon anti-Terminator) · counter=ne JAMAIS pather dans son arc r3 ; le tuer/déplacer ou forcer l'OW sur un chaff avant de bouger une unité de valeur dedans ; ⚠ HeavyGravCannon (+364 dmg/+60% pierce vs TerminatorArmour/Mechanical) = menace EXTRÊME pour un terminator allié (Abaddon) → tuer Sy-gex TÔT si je joue du Terminator (vécu seed 95001 : ExcruciatingFrequencies crit −7759 puis Abaddon le tue) ; pas Resilient, soft → kill franc une fois en portée ; Mechanical = les dégâts COLLENT (pas de heal-back) → bait son actif avec une adjacency-bait Ulf (SavageKiller) ou le chunk-finir (vécu seed 70004 : tué par la riposte FinalJustice d'Ulf 5724 quand Sy-gex a focus-killé Ulf) [n=3]`
- **admecManipulus « Actus » (AdMech, repair-engine, Mechanical)** — `DefendTheDivineWork` (1117, seul
  actif — PAS une attaque normale, cf. §1) : **répare self + adjacents 4365** ET via `GalvanicField`
  **chaque unité réparée fait immédiatement une attaque gratuite** (100% dmg, cap 4365/hit) = moteur
  **sustain + action economy**. `DefendTheDivineWork` strip aussi les effets négatifs des réparés
  (= cleanse, ex. retire Markerlight, cf. §1). Soft (~9537 PV, **pas Resilient**) → focalisable sur la
  tuile d'engagement. ⚠ déni : Mephiston `FuryOfTheAncients` (heal/repair-block 2 rounds) coupe ses
  réparations.
  ⚠️ **DEUX vecteurs de réparation S'ADDITIONNENT par cycle de tour (vérifié seed 97002)** :
  `DefendTheDivineWork` (self + adjacents 4365) **+** trait **Mechanic** (action de réparation = Dommage ×
  hits, sur self ou allié Mechanical ; Actus est aussi trait **Mechanical** → réparable par d'autres
  Mechanics). Le **+5983 observé en un tour** dépasse le plafond DefendTheDivineWork seul (4365) → preuve
  que les deux sources se cumulent. **Conséquence H02 LITTÉRALE pour un repair-engine** : un chip
  non-létal (Actus chunké 9537→3302) est **ENTIÈREMENT effacé** au tour suivant (→9285) → **kill CE
  tour ou ne pas committer** ; ne PAS sur-étendre un corps pour le chiper. Il kite (move3) en backline
  après réparation.
  `▸ Tac: rôle=engine · menace=critical (repair 4365 DefendTheDivineWork + Mechanic action additifs = +5983/tour observé ; GalvanicField free-attack par réparé) · counter=kill FIRST (H02) en UN tour, soft & non-Resilient → focus down depuis tuiles SHALLOW (ne JAMAIS sur-étendre un corps pour le chiper : chip effacé + corps stranded = vécu seed 97002, Mataneo deep-commit → mort + Actus re-healé 9285) ; OU heal-block FuryOfTheAncients ; soit le kill sécurisé, soit le laisser vivre ; ⚠ **n+1 (vécu seed 70061, CONTRIBUTING ROOT CAUSE)** : après avoir tué le summoner Bellator, j'ai seulement CHUNKÉ Actus 9537→4468 et HOLD au lieu de sécuriser le kill depuis le shallow → Actus a SURVÉCU jusqu'au timeout round-10 (EnvEndBombardment) = un repair-engine non-fini est un clock qu'on perd ; le « kill ce tour ou ne pas committer » est LITTÉRAL — une fois Bellator mort, Actus DEVAIT devenir le focus #1, pas un chip ; NB DefendTheDivineWork répare ANY adjacent friendly (PAS Mechanical-gated) donc l'engine est LIVE dès qu'Actus a des alliés adjacents, même s'il est le seul Mechanical de son équipe [n=3, 97002/.../70061]`
- **deathBlightlord « Maladus » (Death Guard, move2 lent, Resilient + TerminatorArmour, ~12k PV)** —
  **anvil d'attrition.** `ContagionsOfNurgle` (aura : −armure aux ennemis dedans, **s'étend** r1→r3 sur
  les rounds ; booste aussi son offensive). `FlailSwing` (3× Power Pierce40 ~3274-3710 ≈ ~10k burst mêlée ;
  overkill sur défaite + chaîne Haze ; vérifié seed 97002 : 1984+1795+1935 sur Azkor en un tour).
  Move2 (lent) → **KITER**. `Resilient` (1 PV sauf Overkill) + `TerminatorArmour` (1ʳᵉ attaque/tour
  réduite **−75%** SAUF Psychic/Direct exclus de la réduction) + 12k PV = nécessite un **burst
  2-hit-ou-Overkill** Psychic/Direct, PAS du chip. ⚠️ **Hard-counter d'un roster all-melee SANS
  Psychic/Direct** : chaque tour-d'attaque frais retape la réduction Terminator −75% empilée à
  l'armure de base + aura −armure de Maladus → mes plans mêlée Pierce-only tombaient à **330-954/coup**
  (vérifié seed 97002) = effectivement INKILLABLE. Bypass = Psychic/Direct OU Overkill/multi-hit.
  `▸ Tac: rôle=anvil · menace=high (one-shot des fragiles, quasi-inkillable) · counter=KITER (move2) ; bypass Terminator au Psychic/Direct (les seuls à ignorer le −75% 1ʳᵉ-hit) ; budgétiser un burst 2-hit/Overkill, jamais du chip ; ⚠ pour un roster all-melee SANS Psychic/Direct = MUR INFRANCHISSABLE → traiter comme une loss structurelle au recon, NE PAS l'engager, gagner sur les unités softs avant que l'attrition tourne (vécu seed 97002 : plans mêlée 330-954 vs lui = nul) [n=1]`
  `▸ Tac (CONFIRM bypass-Psychic = killable + FlailSwing-focus-kill, seed 70059 W) : avec un outil Psychic Pierce100 (Typhus PlagueWind/Archimatos), Maladus est TUABLE proprement — Psychic bypasse TermArmour à plein (chunké 2432 par PlagueWind T2), puis floored à 4 par un Psychic 1931, puis tué DEPUIS le floor par un extra-hit (LetTheGalaxyBurn 4, WasOverkilled=1 — multi-hit bat Resilient une fois floored, cf. §1). CONTRASTE avec 97002 (all-melee sans bypass = mur) : un roster AVEC Psychic/Direct le crack. ⚠ FlailSwing ~10k burst CONFIRMÉ focus-killer d'un carry forward (a tué mon Kharn over-étendu à (4,2)) → ne JAMAIS présenter un carry adjacent à Maladus ; sa lenteur move2 permet de kiter mais s'il atteint un fragile = ~10k. Sa death-riposte subie : il a aussi encaissé 6481 de la death-riposte TheBetrayer de mon Kharn (setup d'1-shot next-turn) [n=1, 70059]`
- **worldJakhal « Macer » (World Eaters, mêlée, Resilient)** — `JakhalStimms` (4× Melee Physical
  Pierce1 en cleave sur la cible **+ tous les ennemis adjacents À LA FOIS à Macer ET à la cible**
  (cône d'adjacence-aux-deux, gameconfig-confirmé) ; **coûte 25% de la PV COURANTE** de Macer ;
  **NE termine PAS son tour** → enchaîner une attaque normale 3× Chain le même tour, ~8400
  burst observé). Le **volume 4-hit overcome le Terrifying** (réduction-mêlée) d'une cible chunkée :
  vécu seed 97000 — un cast a K!'d Tigurius (6525→0, 3503+3022) ET splash-chunké le Terrifying
  Deathleaper adjacent-aux-deux de 8032→303 (7729 sur 4 hits), puis Macer normal-finit Deathleaper
  (double kill, une activation). `Skullsmasher` (+dmg par 10% PV manquant + Stun après 1er kill).
  `Resilient`/`BlessingsOfKhorne`. Engager Resilient/jetable à fort burst single-turn.
  `▸ Tac: rôle=carry · menace=high (burst single-turn ~8400 : JakhalStimms cleave AoE + normale, no-turn-end ; Resilient = last-man) · counter=le focus-reaction (pas Resilient-proof : multi-hit/Overkill) ; ne PAS clusterer mes unités adjacentes-aux-deux d'une cible qu'il vise (cleave les attrape) ; à MOI = double-kill-engine T2 (le 4-hit splash bat le Terrifying d'une cible chunkée — vécu seed 97000 : Tigurius K! + Deathleaper 8032→303 en un cast) [n=1]`
- **eldarMauganRa « Maugan Ra » (Aeldari, ranged r3, move3, carry fragile ~4248-7029 PV)** — garder
  **STATIONNAIRE** chaque tour empile 3 bonus gatés « has not moved/attacked » : `HeavyWeapon` (+dmg
  ranged), `InescapableAccuracy` (s'il n'a PAS bougé : ses tirs ranged **ignorent les réductions de hit**
  → **BYPASSENT le Camouflage** de Shadowsun/Deathleaper (−1/−2/−3 hits) ; +15% crit chance, +728 crit
  dmg ; **s'applique aux cibles de HarvesterOfSouls ET aux tirs Overwatch** ; i2 vérifié seed 95000),
  `Overwatch` : riposte tout ennemi entrant en portée — **gate = NOT-ATTACKED (PAS not-moved)** : Maugan Ra
  peut **bouger PUIS armer son Overwatch** (vérifié seed 98000 : a bougé T1 puis l'effet Overwatch_AutoAttack
  s'est activé au StartTurn et il a auto-tué des Scarab Swarms en réaction au tour adverse). Chaque ennemi
  entrant en portée déclenche une **riposte SÉPARÉE** → une mêlée/summon qui walk ses unités une par une se
  prend une volée par mover (cascade KILLs sur des Scarabs observée). `HarvesterOfSouls` (actif r3) : **vraie AoE
  multi-cibles** — 2× Heavy Round sur la cible + **TOUS les ennemis adjacents à la cible ET en range 3 de
  Maugan Ra** (vérifié seed 98000 : 1 cast sur Dreir a splashé Dreir + 3 Death Riders = 4 cibles, ~1400-3600
  chacun → cleave dévastateur sur une grappe de dive) ; **+1 hit supplémentaire (extraHit) si Maugan Ra n'a
  PAS bougé**, et InescapableAccuracy s'applique aux cibles (ignore les réductions de hit, +15% crit, +crit dmg).
  → une mêlée qui approche se fait chiper gratis à répétition. **Bouger pour atteindre une cible drop les 3 bonus
  ET expose la carry** → tourelle stationnaire de dissuasion/chip, ne repositionner que sous pression dure.
  `▸ Tac: rôle=carry · menace=critical SI statique, HIGH si l'IA le fait bouger (tourelle OW statique : HeavyWeapon + InescapableAccuracy bypass-Camouflage + HarvesterOfSouls AoE r3 punit tout mover) · counter=NE PAS walker mes movers UN PAR UN dans sa r3 (chaque entrée = une riposte SÉPARÉE — vécu seed 70006 : a chipé mon Azkor 6× ~5675 total + un Guardsman) ; le FORCER à bouger (zoner/menacer en mêlée) pour stripper les 3 bonus statiques ET son Overwatch ET restaurer la protection Camouflage (vécu seed 70006 : l'IA agressive l'a bougé/fait-attaquer chaque tour → il n'a jamais re-armé longtemps = menace DOWN critical→high dans ce matchup) ; fragile (~7029, pas Resilient) une fois isolé → fini avec une K! Volk depuis la tuile courante ; approcher seulement sous Infiltrate (no-OW) — vécu : a shot Dante 6x 777-1111/hit + kill, ne respecte PAS Camouflage quand statique [n=2, 70006]`
- **eldarRanger « Calandis » (Aeldari, ranged r3, fragile ~7029, pas Resilient)** — `HeavyWeapon` (+dmg
  ranged **s'il n'a PAS bougé**). `FireAndReposition` (attaque + repli ; **gate « target in range » → rejet
  mutated=false sans cible valide en portée**, cf. H24 ; dépense l'Overwatch du tour → après l'avoir usée
  T1, **plus d'OW T2**). `WireweaveNet` (contre une attaque mêlée NORMALE 2× ~873-1310 Pierce80 ; **si
  l'attaquant meurt, son attaque mêlée est annulée** → ne PAS poke-mêlée un fragile dessus). `Overwatch`
  quand stationnaire. Dealt 4494 sur Mataneo (kill-assist, seed 97002).
  `▸ Tac: rôle=carry · menace=med (chip ranged + OW + WireweaveNet counter ; HeavyWeapon si immobile) · counter=la tuer au RANGED ou avec un corps EXPENDABLE (WireweaveNet punit le poke mêlée normal + annule l'attaque si l'attaquant meurt) ; la focus TÔT (fragile 7029, pas Resilient = tout K! franc) ; exploiter qu'elle dépense l'OW via FireAndReposition T1 → safe d'approcher T2 ; ⚠ **n+1 (vécu seed 70061)** : easiest kill du match — a dive forward T1 + casté FireAndReposition (OW dépensé) → T2 Tanksmasha melee chunk 7029→2300 + Certus OW finish 2300→0 ; un fragile ranged qui s'avance se fait reaction-kill GRATIS (chunk melee + un Overwatch held finit) [n=2, …/70061]`
- **genesPatriarch « The Patermine » (Genestealer, Legendary, move4, Infiltrate/Synapse/Terrifying/
  Unstoppable)** — `MightFromBelow` : 5× **Psychic Pierce100 + NoBlocking** (ignore armure/block,
  brutal vs briques armurées, vécu 5422 sur un Toth armuré en une activation), puis summon une
  Purestrain Genestealer sur **CHAQUE decoy adjacent au Patermine** (attaque mêlée immédiate, pas de
  move ce tour). Decoys via passif `CosmicHorror` (posés quand le Patermine LUI-MÊME tue ; +heal 2910
  si le Patermine marche sur un decoy). Purestrain (genesSmnGenestealer) : move3 mêlée, Infiltrate
  (pas d'Overwatch) + Ambush (1ʳᵉ mort → decoy + resurrect full ; 2ᵉ kill permanent). **Garder les carries
  armurées hors de l'adjacence du Patermine + nier les decoys.** ⚠ **SNOWBALL ENTIÈREMENT KILL-GATED** : un kill
  via MightFromBelow chaîne IMMÉDIATEMENT en un Genestealer sur l'hex du mort (kill→CosmicHorror decoy→
  summon, même tour) → **nier les kills au Patermine = nier les decoys = nier les summons**. Le contre est
  POSITIONNEL (ne présenter AUCUN fragile killable dans son move4 reach), pas réactif (vécu seed 70003 : le
  Patermine a tué Nicodemus T1 → Purestrain u151 4487 PV summon là = snowball live ; le Psychic Pierce100
  ignore l'armure → un healer/fragile non-blindé est une cible parfaite). ⚠ **Summon DÉCOY-GATED, PAS
  cast-gated (vérifié seed 70009)** : l'event `Ability_Summon` fire à CHAQUE cast de MightFromBelow mais
  **produit RIEN s'il n'y a aucun decoy adjacent au Patermine** (Patermine sans kill préalable → pas de decoy
  CosmicHorror → Ability_Summon e=103 a fire mais spawné 0 unité). Le 5× Psychic Pierce100 (DamageProfileType=13,
  ~5753 ignore armure) tape toujours ; seul le summon est gaté sur les decoys (= sur les kills du Patermine).
  `▸ Tac: rôle=carry · menace=critical (snowball self-feeding kill-gated + 5× Psychic Pierce100 ignore armure + move4 reach + Terrifying 10038 → bypass = RANGED, ma mêlée fait réduit) · counter=DENY-KILL positionnel (aucun fragile dans son move4 reach = pas de decoy = pas de snowball) ; le tuer au RANGED tôt avant son 1er kill ; une fois qu'il a tué une fois le snowball est live et un set de survivants mêlée ne le rattrape pas [n=1]`
- **genesPrimus « Isaak » (Genestealer, GSC, move3, Ambush+Hero)** — `CultDemagogue` (actif r2) :
  cible un ennemi ≤2 hex, éparpille jusqu'à **8 decoys** ≤2 hex autour, puis summon des **Neophyte
  Hybrids sur LA MOITIÉ** des decoys (4→8 selon niveau) qui **prennent immédiatement un tour** (Summon
  auto move+attack) = **board-flip + flanc en un tour** (vécu 4v4 → 4v12). Neophytes ranged r2, chacun
  `Ambush` (resurrect sur decoy ami). ⚠️ Isaak a AUSSI `Ambush` → un seul kill ne le retire pas.
  **Tuer Isaak AVANT le cast** (H02 prime sur H03 vs summoner+reviver) ET nier/clear les decoys.
  `▸ Tac: rôle=engine (board-flip summoner) · menace=CRITICAL (le proximate wincon-enabler : 1 cast CultDemagogue au tour ennemi = board-flip 4v5→3v12 — 3-4 Neophyte Hybrids 2992 PV ranged r2 chacun Ambush + decoys prenant un tour IMMÉDIAT ; ~7026 HP, pas Resilient mais Ambush) · counter=DOIT mourir AVANT sa fenêtre de cast (T2 au plus tard) ; backline row-7/9 + Ambush (exige 2 kills/clear-decoy) → si INATTEIGNABLE T1 sans dealer r3+/deep-strike, c'est un reach-fail STRUCTUREL → flagger la loss et jouer un turret défensif (fragiles row 0-1) plutôt qu'avancer des fragiles dans le reach Custodes/GSC ; ⚠ ne PAS dépenser mon unique vrai tour sur le LESSER engine (Yarrick) en laissant Isaak libre — tuer l'engine qui ENABLE l'écran, pas le plus facile (vécu seed 70007 : Isaak row-7 jamais menacé → CultDemagogue a fire = la loss ; cf. 91012) ; ⚠ **n+1 vécu seed 70050** : 1 cast CultDemagogue au tour enemy-T1 a spawné 3 Neophyte Hybrids (2992 PV chacun, ranged r2, Ambush) + decoys prenant un tour IMMÉDIAT → 5v5 → 5v14 en une activation ; Isaak row 8-9 INATTEIGNABLE à mon roster melee/r2 + 1 move2/r3 = reach-fail structurel → board flippé avant toute fenêtre de kill = la loss [n=3, 91012/70007/70050 triggered-against-me]`
  `▸ Tac (À MOI — engine bidirectionnel, board-flip FOR me + Ambush self-resurrect, seed 70054 W) : CultDemagogue est tout aussi DÉVASTATEUR quand JE le contrôle — détail confirmé : cible un ennemi ≤r2, place jusqu'à 8 decoys dans 2 hex autour, summon des Neophyte Hybrids sur la MOITIÉ (≤4), TOUS les Neophytes de la zone agissent IMMÉDIATEMENT (Summon = auto move+attack ; chacun Ambush = resurrect-once + tour immédiat ; ranged r2). USAGE : le réserver pour SEIZE l'avantage numérique une fois l'ennemi aminci → vécu seed 70054 : cast T7 (ciblant un Poxwalker) → board-flip 3v4 → 9v1 = a délivré le surnombre qui a fini le combat. ⚠ Isaak `Ambush` (à MOI) : à sa 1ʳᵉ mort il laisse un decoy + ressuscite à PV PLEIN (7026) sur un decoy ami survivant AU DÉBUT de son prochain tour, puis agit IMMÉDIATEMENT — CONDITIONNEL : s'il ne reste AUCUN decoy ami quand son tour commence, il reste mort. Vécu seed 70054 : Isaak focus-killé T5 (3465→0) → resurrected full-HP (1,3) T6 = a récupéré le corps « perdu » à l'over-extension. SOURCE-à-protéger côté moi = Isaak (le board-flip engine qui snowball une fois cast) ; un kill sur Isaak n'est que TEMPORAIRE tant qu'un decoy survit [n=1, 70054 chained]`
- **deathTyphus « Typhus » (Death Guard, ~12047 PV, mêlée lent, Resilient + TerminatorArmour)** —
  **anvil d'attrition + AoE Psychic.** Passif **`DestroyerHive`** : au DÉBUT de CHAQUE tour de Typhus,
  inflige **1× 1019-1164 (lvl65) Direct Damage (PiercingRatio 100, ignore l'armure)** à **UN ennemi
  adjacent aléatoire** — **PAS** du friendly-fire ni du self-damage : la cible est un ennemi adjacent de
  Typhus (i2 vérifié seed 96000 : « Deals 1x 1019-1164 Direct Damage to one random adjacent enemy at the
  start of his turn »). **Implication : ne JAMAIS laisser une unité fragile (support/glass-cannon)
  collée à Typhus au début de son tour** (one-shot possible — a tué Dante à 99 HP final, frappé Patriarch
  2385/1018/1018). `PlagueWind` (AoE Psychic Pierce100). `Resilient` (1 PV sauf Overkill) + `TerminatorArmour`
  (1ʳᵉ attaque/tour réduite SAUF Psychic/Direct) + 12k PV = nécessite un **burst multi-hit/multi-source en
  un tour** (la 2ᵉ attaque distincte du tour bypasse TerminatorArmour ; Overkill ou multi-hit bypasse
  Resilient) — Psychic/Direct passent à plein. **Impossible à tuer proprement 1v1** (vécu seed 96000 : tué
  en réaction par 7 sources distinctes — FJ Thoread + Screamers + PinkHorror).
  `▸ Tac: rôle=anvil · menace=critical (12047 HP + Resilient + TerminatorArmour + DestroyerHive auto-dmg adjacent start-of-turn + PlagueWind r2 Psychic Pierce100 NoBlocking AoE) · counter=multi-source focus en UN tour pour bypasser TerminatorArmour (2ᵉ attaque distincte tape plein) + Overkill/multi-hit pour bypasser Resilient ; Psychic/Direct bypasse TerminatorArmour ; NE PAS laisser une unité fragile adjacente à son démarrage de tour (DestroyerHive one-shot) ; ⚠ il est l'ÉCRAN (anvil) — casser les SOFT engines derrière lui (Isaak/Isabella) plutôt que de chiper Typhus ; ⚠ vécu seed 70050 : PlagueWind a frappé mon cluster + tué mon Guardsman dans le focus de 34887 dmg [n=2, 96000/70050]`
  `▸ Tac (À MOI — anvil bidirectionnel + outil de bris anti-TermArmour, seed 70059 W) : Typhus est un anvil-baiteur PARFAIT pour MON côté — 12k Resilient/TermArmour ancre un cluster que l'ennemi all-melee est CONTRAINT de diver. Son PlagueWind = LE bris d'un mur d'anvils : 3-target Psychic AoE (primary + adjacent + further-adjacent) Pierce100 NoBlocking bypasse TOUT TermArmour/Resilient/armure à PLEIN sur chaque cible (vécu : Ragnar 3914 + TG 3154 + Maladus 2432 en UN cast, malgré TermArmour sur TG/Maladus). DestroyerHive (auto-Direct StartTurn) = chip GRATUIT sur un ennemi adjacent à mon démarrage de tour (3369 sur le TG adjacent) → positionner Typhus collé à un anvil ennemi en fin de mon tour précédent pour le farmer. USAGE : ancre forward + ouvrir la salve sur un cluster d'anvils groupés avec PlagueWind → softène 3 anvils simultanément, enable les multi-kills suivants [n=1, 70059]`
- **deathRotbone « Nauseous Rotbone » (Death Guard, Chaos, ~12047 PV, mêlée lent, Resilient + Healer)** —
  **engine de sustain/revive.** Trait **`Healer`** (cf. §1 transverse) : peut soigner **N'IMPORTE QUELLE
  unité alliée comme action** (y compris Xenos/Imperial — PAS restreint Chaos), montant = **Damage × plus
  haut nombre de hits d'arme** (4× Power → gros heal ~5000+). ⚠️ **À NE PAS confondre avec son active
  `RevitalizingMalignancy`**, qui ne soigne que **2546 self+adjacents (+2546 Chaos, 0 aux Imperial)** :
  un gros heal (~5000) sur un allié non-Chaos vient du **trait Healer**, pas de l'active (vécu seed 96000 :
  a restauré Farseer/Eldryon 2407→7530 full entre T1 et T2 via le trait Healer, Eldryon étant Aeldari/Xenos).
  `TaintedNarthecium` (passif) : **75% chance de revive un Chaos adjacent défait** (n'a jamais tiré seed
  96000 car aucun Chaos n'est mort adjacent à lui — Farseer est Aeldari, non Chaos ; le flag revive
  apparaît actif chaque tour mais ne fire que sur une mort de Chaos ADJACENT). `ContagionsOfNurgle`,
  `Resilient`.
  `▸ Tac: rôle=engine · menace=critical (Healer = heal toute faction ~5000+ annule les chunks/kills + TaintedNarthecium 75% revive Chaos adjacent) · counter=le tuer TÔT et AVANT accumulation de pertes Chaos adjacentes ; Resilient → multi-hit/2ᵉ source/Overkill (vécu seed 98004 : K! Makhotep TROMPEUR — max 1697 < 1698 HP → floor, fini par Nicodemus multi-hit Chain 186 puis 1→TUÉ) ; sa mort empêche le revive de boucler sur un Chaos tanky (vécu seed 96000 : tué T3 multi-source 4412 exact kill → revive Typhus nié) ; ⚠ son **TaintedNarthecium-revive est STRUCTURELLEMENT INERTE** dans un roster où il est le SEUL Chaos (4 alliés Imperial → aucun Chaos adjacent à revive) → la menace = le HEAL, PAS le revive ; coupler le kill avec un HEAL-BLOCK Mephiston (FuryOfTheAncients) qui nie son heal/revive 2 rounds (vécu seed 98004) [n=2]`
  `▸ Tac (n+1 à MOI = anti-armure + revive-INERTE, seed 70060 W) : ✅ ContagionsOfNurgle −armure aura (−20%, s'étend r1→r3) appliquée aux ennemis qui entrent dedans (Deathleaper puis Burchard) = OUTIL ANTI-ARMURE qui offset PARTIELLEMENT le double-armure Burchard MkXGravis → aide un roster SANS Direct/Psychic/Crit à grind le mur (12038→1362 en un tour focus avec Storm of Fire +582). ⚠ son **RevitalizingMalignancy/TaintedNarthecium revive = STRUCTURELLEMENT INERTE si Nauseous est le SEUL Chaos de MON roster** (heal ne donne RIEN aux Imperial — Sarquael/Trajann 0 ; revive Chaos-only → aucun Chaos à revive ; heal ne profite qu'aux Xenos Aun'Shi/Re'vas) → recon-flagger l'inertie, ne pas compter sur le revive (vécu seed 70060 : jamais nécessaire, zéro perte hero). MÊME classe d'engine-inerte que 98004 mais ici DANS mon propre roster [n=3, 96000/98004/70060]`
- **eldarFarseer « Eldryon » (Aeldari/Xenos, ~7530 PV, ranged caster, fragile)** — **Doom engine /
  control.** Passif aura **`Doom`** (range « **exactement 2** ») : les ennemis à **EXACTEMENT 2 hexes**
  d'Eldryon (PAS plus près, PAS adjacent) sont marqués (effet `Doom_extraDmg`) : ils **prennent +Damage
  des attaques normales des AUTRES alliés**, et les **alliés Aeldari déalent +Damage avec TOUTES leurs
  attaques** vs les marqués (i2 vérifié seed 96000 : « +655 Damage from other friendly unit's normal
  attacks » / Aeldari « +873 Damage with all their attacks » ; gate = distance EXACTE, pas ≤2). ⚠️
  **owner = Eldryon, PAS un générique « Farseer »** (corrige une mésattribution courante). `Executioner`
  (scale par round → très dangereux R5+). **PAS de Resilient/FinalJustice, fragile 7530** → tuable T1-T2
  si focus.
  `▸ Tac: rôle=engine · menace=critical (Executioner scale +582-2183 Psychic/round commencé → exponentiel après R3 = board-wipe ; Doom aura +dmg aux ennemis à exactement 2 hex) · counter=le tuer dans la FENÊTRE T1-T4 AVANT que l'Executioner monte (fragile ~7530, pas Resilient/FJ = glass cannon, priorité ABSOLUE) ; garder mes unités HORS des 2 hex exacts de Doom ; ⚠ peut être ré-healé full par un Healer adverse (Nauseous) → le focus doit l'ACHEVER, pas le chunker (vécu seed 96000 : ré-healé full T2 → tué T3 par réaction 1490 exact kill ; vécu seed 96002 : tué T4 à 149 HP — near-miss, 1 tour de plus = scaling létal) ; ⚠ **STRUCTURELLEMENT INATTEIGNABLE derrière un screen all-ranged (Re'vas turret+drones) pour un roster melee-heavy SANS reach tool** → reach-fail (vécu seed 70052 : jamais atteignable, l'engage coûtait 3-for-1 par guard A NET −3.92, loss structurelle à flagger au recon) [n=3, +70052]`
- **templAncient « Thoread » (Imperium, Black Templars, mêlée, buff-tank + FinalJustice)** —
  `UnbreakableDuty` (actif, range 2) : **buff self-centré sur alliés** — Thoread + tous les alliés dans
  2 hex reçoivent **−33% Damage jusqu'au début de leur prochain tour**. ⚠️ **ne prend PAS de cible
  ennemie** : viser un ennemi renvoie `mutated=false` sur lui MAIS le buff allié s'applique quand même
  (vérifier le type de cible d'un actif défensif avant de le caster — vécu seed 96000 : ciblé Atlacoya
  ennemie = mutated=false, tour à demi-gâché). Effet secondaire conditionnel : si **2+ Imperial Characters
  alliés sont morts**, Thoread gagne **+7275 HP / +1455 Damage jusqu'à la fin de la bataille** et frappe
  immédiatement un ennemi adjacent en normale. Trait **`FinalJustice`** (cf. §1 — attaque normale à la
  mort sauf Overkill ; vécu seed 96000 : FJ Thoread a dealé 345+271 sur Typhus puis contribué au kill
  multi-source).
  `▸ Tac: rôle=anvil/control · menace=med (buff d'équipe −33% dmg + scaling conditionnel sur pertes Imperial) · counter=N/A (à MOI) · usage=UnbreakableDuty est self/friendly-area (caster SANS cible ennemie, --to une zone alliée) ; le garder au cœur de la grappe pour le −33% ; FinalJustice = riposte de mort utile en réaction [n=1]`
  `▸ Tac (DEMOTE quand ENNEMI — scaling conditionnel INERT, seed 70054) : ⚠ le +7275HP/+1455dmg de UnbreakableDuty exige « 2+ Imperial Characters alliés MORTS » → STRUCTURELLEMENT INERTE si Thoread est le SEUL Imperial de SON roster (le trigger ne peut JAMAIS s'armer). RÈGLE DE RECON (engine/conditionnel-inerte, miroir H02/§6) : COMPTER les bénéficiaires/déclencheurs VALIDES d'un conditionnel AU RECON avant de craindre son scaling ; ici 0 autre Imperial → demote Thoread à un PLAIN killable tank ~10k (no-Resilient) + l'aura −33% d'équipe + FinalJustice. Vécu seed 70054 : le scaling jamais armé → traité en corps killable, Darkstrider markerlight 10038→412 en ~2 tours, fini par Corrodius normale. L'aura −33% RESTE active (elle, non-conditionnelle) → le tuer coupe AUSSI la réduction d'équipe [n=1, 70054]`
- **eldarAutarch « Aethana » (Aeldari, mêlée, ~8034 PV, no Resilient)** — passif `PathOfCommand` (aura,
  **range 2**) : les autres alliés ≤2 hex gagnent +Damage (scale, max +291), **+20% Crit**, et les alliés
  Aeldari un +Damage additionnel (max +218). **Positionnel** : suit Aethana → la bouger hors de portée strip
  le buff de groupe ; la garder centrale au cluster à buffer. `Flying` + `TeleportStrike` (deep strike, cf. §1 —
  **non-ciblable jusqu'à sa 1ʳᵉ action OU fin de tour ; landing = action → protection tombe immédiatement**) ;
  actif mêlée `SwoopingHawk` → auto-finish si posée non-adjacente (cf. §1). ⚠ **vérifié seed 70051** : l'IA la
  pose en AVANT (PathOfCommand range-2 incite à la rapprocher de la grappe) → elle a landed FORWARD à (3,4) au
  1ᵉʳ tour IA → dès qu'elle a agi/landed elle est devenue ciblable et **ATTEIGNABLE** → K! T3 (Creed 6288→0).
  Un deep-striker buff-engine qui sort forward s'auto-expose au focus.
  `▸ Tac: rôle=engine (buff-engine) · menace=high (PathOfCommand +291/+218 Aeldari + +20% crit aux alliés ≤2hex = dépompe TOUTE l'équipe ; Flying + TeleportStrike = intouchable jusqu'à sa 1ʳᵉ action) · counter=intouchable en deep-strike, MAIS dès qu'elle land/agit elle est ciblable → si elle sort FORWARD (l'IA le fait pour le buff range-2) elle devient atteignable au tour suivant → K! (no Resilient → tout K! la tue ; vécu seed 70051 : sortie forward (3,4) T1 → tuée T3 par Creed) ; la tuer = dépomper l'équipe entière ; si à MOI, la poser ARRIÈRE/flanc, jamais forward si la menace adverse peut la cibler dès T2 [n=1, 70051]`
- **custoVexilusPraetor « Aesoth » (Custodes, mêlée)** — `VexillaMagnifica` (Melee, adjacent, cd2,
  réutilisable) : frappe la cible adjacente ET un 2ᵉ ennemi adjacent (~2910-4365 Physical), **Stun les
  DEUX pour 1 ROUND** (pas 2 tours), et Aesoth **−66% dmg subi 1 round**. Adjacency-gated : il faut 2
  ennemis adjacents à Aesoth au cast pour les 2 stuns. ⚠ **C'est un outil de CONTROL d'abord, pas un
  finisher** (vérifié seed 70006) : le STUN est garanti mais le **dmg est fortement modifié par les
  buffs/blocks de la cible** (1338 dealt vs un plan 2247-3674 quand Ragnar/BeastSlayer a réduit l'entrant)
  → ne PAS budgétiser VexillaMagnifica comme un K? fiable vs une cible à réduction de dégâts ; la jouer
  pour le stun + l'auto-défense −66%, et finir avec une autre source. Quand le tank atteint ma ligne, peut lock une
  unité-clé (sustain carry) un tour entier → garder les unités de valeur hors de son adjacence. `Resilient`,
  `BigTarget` (alliés adjacents −1 hit ranged ; non-déplaçable), `MartialKatah` (−dmg des attaques NORMALES
  subies → bypass aux ACTIFS/Direct/Psychic), `StandVigil` (buffe les alliés +armure/+dmg). ⚠ **le stun
  CONVERTIT une unité sur-étendue en kill quasi-garanti** : une cible stunnée en portée mêlée garde 1
  Movement + son attaque normale (cf. §1 Stun corrigé — il ne perd QUE ses ACTIVE abilities) mais 1 move
  ≪ ce qu'il faut pour sortir d'une killzone → elle ne peut quasiment pas retreat et se fait focus-kill
  (vécu seed 93000 : Mephiston forward stunné → mort, ne pouvait pas reculer). C'est la pièce qui PUNIT
  mes erreurs de positionnement. ⚠ **côté HARNESS** : une unité À MOI stunnée n'est PAS « complètement
  bloquée » — ne pas l'`endturn` d'office ; elle conserve 1 move + son attaque normale (vécu seed 96002 :
  VexillaMagnifica a stunné Burchard+Sy-gex ; le `mutated=False` sur mes actions = artefact runner, pas la
  sémantique du Stun — mais leur attaque normale/Overwatch restaient exploitables).
  `▸ Tac: rôle=control/anvil · menace=high (Resilient + stun-lock qui transforme une sur-extension en kill quasi-garanti ; StandVigil buffe l'équipe +armure/+dmg) · counter=garder mes unités de VALEUR hors de son adjacence (pré-positionnement défensif AVANT qu'Aesoth atteigne ma ligne — vécu seed 96002 : a stunné Burchard+Sy-gex = activation perdue, évitable) ; bypass MartialKatah avec actifs/Direct/Psychic ; Resilient → Overkill/2-hit (vécu seed 98004 : Mephiston Psychic K? l'a laissé à 17 HP = K? TROMPEUR → Nicodemus Chain l'a fini en overkill) ; exploitable via le splash ARRIÈRE d'un burst double-target (Haarken HeraldOfTheApocalypse derrière sa cible l'a chunké 11044→5654, seed 98004) ; le tuer via réactions/Overwatch si je tiens une turret (vécu seed 96002 : Aesoth 2026 HP tué par cascade Burchard Overwatch) ; ⚠ move3 mêlée → atteint ma ligne et melee-kill un fragile sur-étendu (vécu seed 70007 : a melee-killé mon Archimatos 4025 forward après chip de Trajann) → garder les fragiles untouchable, ne pas les avancer dans le reach move3 ; ⚠⚠ **SOFT pour un Psyker/multi-source → le tuer TÔT vaut + que sa barre PV (engine de buff StandVigil)** : casser Aesoth retire StandVigil = DEPUMP l'équipe (sa durabilité ajoutée à Trajann/Volk disparaît) (vécu seed 70005 : chunké 11044→759 en réactions puis TUÉ par l'EXPLOSION de mon propre Aleph-Null Explodes 25% maxHP Direct adjacent 759→0 → StandVigil retiré) ; ⚠ **À MOI = control-tool confirmé n+1** : VexillaMagnifica hit 2 adjacents (Bellator + Inceptor) plein dmg + Stun 1 round les DEUX (CantUseAbility bloque leurs ACTIFS, laisse leur normale usable) + Aesoth −66% dmg subi 1 round, cd montrée cd1 next-turn puis [pret] = REPEATABLE (~cd2) ; le stun-then-finish sur un engine (T3 stun Bellator + chunk Inceptor ; T5 stun Bellator+Inceptor puis Calandis finit Bellator) est la séquence (vécu seed 70053 W) [n=6, 96002/98004/70007/70005/70053]`
- **tauAunShi « Aun'Shi » (Tau, buff-engine)** — `SereneUnifier` (range 2) : au début de son tour,
  buffe lui + adjacents + T'au ≤2 hex sur un **cycle de 3 rounds** (r1 Sense of Stone **−50% dmg subi**
  / r2 Zephyr **+1 move** / r3 Storm **+582 dmg**), puis répète indéfiniment. Le buff dure **jusqu'au
  début du prochain tour de l'unité** (donc le −50% couvre TOUT mon tour intercalé) et **persiste 1 round
  même si Aun'Shi meurt** (vérifié i2 seed 95001) — ⚠ nuance : le cycle ne « s'arrête » pas tant qu'il
  cesse simplement de **distribuer de NOUVEAUX buffs** à la mort d'Aun'Shi ; les buffs déjà posés
  persistent jusqu'au prochain tour de leurs porteurs (vécu : Aun'Shi morte T2 → pas de Storm of Fire
  R3, mais les unités buffées R2 gardent +1 move ce round). **Counter : tuer Aun'Shi AVANT le round dont
  le buff me fait le plus mal (ex. avant R1 Sense of Stone si je veux burst, ou avant R3 Storm si la
  menace est leur dmg) ; ne pas burst les T'au −50%-buffés ce round — attendre, ou taper du
  non-T'au/unbuffé ; et anticiper que le buff du round précédent persiste 1 tour après sa mort.**
  ⚠ **PHASE DE BUFF = nom de l'effet, PAS le label « tour » affiché (CONFIRMÉ vécu seed 70050)** : le cycle
  est tracké par le compteur de ROUND du jeu, jamais par un label UI « tour N ». Malgré un placeholder
  build « tour 3 », l'effet RÉEL sur mes units était `SenseOfStone` (R1, −50% dmg) au start, cyclant vers
  `ZephyrsGrace` (R2, +1 move) après mon tour. → **lire le NOM de l'effet dans `decisionView.effects`**
  (ground truth de la phase active), jamais le numéro de round affiché ; et le round-state pilote la
  décision : R1 SenseOfStone (−50%) favorise HOLD (laisser l'ennemi venir dans le cushion), PAS avancer
  dans l'ouvert où 7-10 ennemis focus à travers la réduction.
  ⚠ **RE-CONFIRMÉ self-play seed 80000 (run #4, 2026-06-23) par les DEUX sides indépendamment** : le label UI placeholder est resté figé « tour 3 » pendant les vrais tours 3/4/5 alors que l'effet RÉEL cyclait de `SenseOfStone` (R1) → `StormOfFire` (R3, +582 sur les 5 units T'au au tour 5). A (theirs) ET B (mine) ont chacun signalé la même friction → **toujours lire `decisionView.effects` (nom d'effet) pour la phase, jamais le compteur de tour affiché.** [self-play consensus, seed 80000, run #4]
  `▸ Tac: rôle=buff-engine (cycle R1 −50%dmg / R2 +1move / R3 +582dmg sur Aun'Shi+adjacents+T'au ≤2hex) · menace=med (buff-engine fragile, no-Resilient) · counter=tuer Aun'Shi AVANT le round dont le buff me fait le plus mal ; ne pas burst les T'au −50%-buffés (attendre R2/R3 ou taper unbuffé) ; à MOI = jouer la phase via le NOM de l'effet (R1 SenseOfStone = HOLD, pas avance) [n=1, 70050]`
  `▸ Tac (n+1 à MOI, seed 70060 W) : ✅ buff-engine défensif décisif dans un mur de réaction — clusteriser mes T'au (+adjacents) près d'Aun'Shi AVANT le dive ennemi : les phases R1 Sense of Stone −50% dmg ont fait SURVIVRE mon cluster au dive all-melee avec ZÉRO perte hero ; R3 Storm of Fire +582 a boosté mon chip sur Burchard MkXGravis bien au-dessus de l'estimation à la main (offset le no-bypass). Le buff persiste jusqu'au prochain tour de CHAQUE bénéficiaire même si Aun'Shi bouge/meurt → tenir Aun'Shi central/vivante = aura survie + dmg pour tout le cluster. Composante-clé du « hold-baits-the-dive » (avec Re'vas EWO + Sarquael held-OW) [n=2, 70050/70060]`
  `▸ Tac (n+1 engine-kill-first CONFIRMÉ vs Aun'Shi, self-play consensus seed 80000) : tuer Aun'Shi AVANT que R3 Storm of Fire (+582 dmg) puisse re-cycler est le **kill-wincon-first** applicable à son cas exact — cycle observé T4 (R1 SenseOfStone actif) ; Tigurius StormOfWrath chunk + Atlacoya TalonsOfTheEmperor finish = kill T4 avant la next Storm of Fire. ✅ **Cross-validé par les DEUX sides du self-play** (A = kill intentionnel T4 avant R3 ; B = reconnaît que l'engine a été stoppé avant son storm-repeat). gameconfig confirme le cycle « After round 3, the cycle begins again ». [self-play consensus, seed 80000]. [n=3, 70050/70060/80000-sp]`
- **ultraEliminatorSgt « Certus » (Ultramarines, sniper, ~6025 PV, soft NON-Resilient, CamoCloak, Infiltrate)** — `MortisRound` (1004, single
  target r3, Heavy Round Pierce55, push 1 hex) ; **HeavyWeapon double l'ability SEULEMENT s'il n'a pas
  bougé** (bouger forfait le bonus, mais base reste un gros nuke). `Overwatch` (riposte si pas attaqué
  + ennemi entre en portée). `Infiltrate` (Certus ne déclenche pas l'Overwatch ennemi). Tir rejeté
  no-op si hors portée/LoS (action préservée) → repositionner d'abord.
  `▸ Tac: rôle=carry (artillerie kiting) · menace=med (MortisRound r3 nuke 3274-3638, HeavyWeapon ×2 si immobile, push 1 ; Overwatch armé ; Infiltrate = skip MON Overwatch) · counter=le tuer au RANGED (Infiltrate = pas catchable par mon OW) ; soft 6025 no-Resilient → finisher franc une fois atteignable ; reste en backline rows 5-8 comme artillerie → part du focus all-ranged qui out-attritionne un roster melee (vécu seed 70052 : kiting artillery, non-décisif seul mais a contribué au out-range) ; ⚠ INATTEIGNABLE pour un roster melee/r2 sans reach tool = composante d'une loss structurelle de reach [n=1, 70052]`
  `▸ Tac (À MOI — TURRET Overwatch HELD, CONFIRMÉ live seed 70061) : `Overwatch` (trait, gate NOT-attacked, cf. §1) fire sur CHAQUE ennemi qui bouge dans sa portée r3 au tour adverse, tant que Certus n'a pas attaqué sur SON tour (ni après) — **AUCUN cap once-per-turn** : tenir son action offensive arme des reaction-kills illimités. Le bonus HeavyWeapon s'applique aussi quand elle n'a PAS bougé. PLAY : la HOLD (ne pas attaquer ce tour) → l'ennemi qui dive séquentiellement se fait reaction-kill 1-par-mover GRATIS (vécu seed 70061 : 3 reaction-kills successifs sur le dive — Calandis 2300, Judh 2214, Bellator 1819 — SANS dépenser une seule action offensive = highest-value engine du match). C'est l'analogue Ultramarines du held-OW turret (cf. Azrael/Sy-gex/Re'vas EWO §1) : la garder en turret arrière quand l'ennemi DOIT closer, ne pas la pousser pour un finish incertain (le HOLD armé vaut mieux). [n=1, 70061 chained]`
- **orksRuntherd « Snotflogga » (Orks, summon/lock engine, ~12k tank)** — `GetEmRuntz` (1045) : summon
  1 Grot dans **CHAQUE hex adjacent ayant un ennemi adjacent** ; chaque Grot attaque immédiatement en
  mêlée (pas de move) et l'ennemi touché est **Taunted 1 round** (i2 : 1 round — engine effects
  `Taunted_OnlySpecificTargets`+`BlockMovement`+`CantUseAbility` → la cible ne peut QUE taper le Grot,
  pas bouger, pas user d'actif/heal/repair). Soft-lock 1 round d'un caster/summoner-clé pour le coût
  d'un Grot (HP max gameconfig 4802 / dmg 2401, scale rareté). Passif `SquigHound` : attaque normale
  **+2 hits Physical (single-target, PAS de cleave/spill)** ; après attaque, summon 1 Grot adjacent à
  la cible (cap <5) ; les Grots amis ignorent BattleFatigue. ⚠️ le « spill sur ennemis adjacents » n'est
  PAS dans son kit (réfuté — seules les abilities qui le déclarent le font ; un kill chaîné observé venait
  d'un Grot summon immédiat, pas du spill).
  `▸ Tac: rôle=anvil/engine (Grot-summoner) · menace=high (12049 PV tank + GetEmRuntz summon Grots Taunt-lock 1 round + SquigHound +2 hits & Grot summon après attaque = alimente le snowball) · counter=énorme HP, dur à retirer → kite/ignorer SAUF burst dispo ; la priorité « tuer-les-summoners-d'abord » sur Tan Gi'da/Aleph-Null passe AVANT de chiper cet anvil (vécu seed 98003 : survécu full 12049 PV tout le combat, avancé à (1,7) — chiper aurait gaspillé du dmg) ; ses Grots Taunt + summons feed le board → traiter comme une source secondaire, pas la cible #1 · ✅ **à MOI = engine self-sustaining** : SquigHound farme un Grot (~7312 PV pumpé, scale rareté cf. H34) à chaque normale qui auto-attaque/chip GRATIS chaque tour → l'ennemi gaspille des tours entiers à tuer mes Grots remplaçables pendant que mes héros restent sains (vécu seed 98001 W) ; **`BeastSlayer`** (+dmg vs BigTarget/Vehicle + block ajouté) → Snotflogga est l'overkiller IDÉAL d'un BigTarget comme Gulgortz (1248→dead, FinalJustice supprimée seed 98001) ; ✅ **À MOI = melee-finish anti-mitigation confirmé n+1** : les 3 frappes Physical DISCRÈTES (1× base + 2× SquigHound) résolvent indépendamment → CONTOURNENT partiellement Terrifying (réduction mêlée) ET Camouflage (anti-ranged) ET Resilient (multi-hit ≥2) — ~7-8k en une activation : a tué Archimatos 8034→0 ET chunké Deathleaper 8032 past Terrifying via les hits discrets ; chaque normale auto-summon un Grot 7312 qui auto-chip/reaction-kill (un Grot a reaction-killé l'Inceptor u140 1804) → Snotflogga est la réponse melee-finish à un assassin Terrifying/Camouflage (vécu seed 70053 W : routé sur Deathleaper T6 near-one-shot) [n=3, 98001/98003/70053]`
- **orksWarboss « Gulgortz » (Orks, Boss, mêlée + ranged passif, Mechanical, ~10k PV)** — anvil/carry
  Ork. Attaque normale mêlée = Eviscerate Pierce50. Passif **`LightImUp`** (Ranged Projectile Pierce15,
  3 hits, range 3) : après CHAQUE attaque normale, Gulgortz fait une **2ᵉ attaque sur la même cible (3×
  Projectile) ; si la cible est défaite, les hits restants sont redistribués à un ennemi aléatoire ≤3
  hex** → sa normale = mêlée + volée ranged enchaînée. `Waaagh` (actif, **gated « Gulgortz n'a PAS bougé »**) =
  swing de comeback : summon **2 Ork Boyz** (orksOrkBoys, ~4986 PV live) dans des hex adjacents libres + buff
  d'équipe (**tous les Orks amis + les units adjacentes à Gulgortz gagnent +1 Movement et leurs normales mêlée
  +582 dmg / +1 hit** jusqu'à fin de tour) + **charge un ennemi ciblé EN MOVE RANGE** (normale mêlée) + **tous
  les Ork Boyz amis prennent un tour immédiatement** (vécu seed 70008 : un cast a chunké Kut 9539→2675, tué un
  Death Rider, chunké Dreir 9304→2044 → a flippé 3v6-down en 5v2-up en une activation). ⚠ la charge exige une
  cible **en move range avec un hex adjacent libre** : charge sur Godswyl dist2 rejetée (mutated=False), charge
  sur Kut dist1 a fire (toolfeedback : contrainte free-adjacent-hex non explicite en i2). `CrushingStrike`
  (+dmg mêlée s'il N'A PAS bougé). Trait **`FinalJustice`** (cf. §1) — ⚠ sa riposte de mort déclenche
  LightImUp = double volée mêlée+ranged, BIEN plus lourde qu'une normale plate (vécu seed 95001 : 2083
  sur Aun'Shi ; **re-confirmé n+1 seed 70008** : Godswyl a tué Gulgortz NON-overkill → FJ a fire une normale et a
  TUÉ le Godswyl 458 PV adjacent = trade 1-pour-1 — un FJ-carrier qui meurt adjacent à un ennemi bas-PV auto-trade
  un kill, positionner le carrier près d'une cible chunkée avant sa mort). `Mechanical` (pas de heal, repair-only).
  **PAS Resilient.** → l'**Overkiller** (chunk puis coup létal > 2× PV restants, ou Crit) est impératif pour
  nier sa FinalJustice ; ne pas le tuer sur un coup juste-létal adjacent à une de mes unités chunkées.
  `▸ Tac: rôle=anvil/carry · menace=high (FinalJustice + LightImUp = riposte de mort double volée mêlée+ranged ; Waaagh summon 2 Ork Boys ; HeavyWeapon ranged + CrushingStrike si stationnaire) · counter=Mechanical (repair-only) ; pas Resilient → OVERKILLER (chunk puis coup létal >2× PV restants, ou Crit) pour nier FinalJustice — sinon sa mort = double volée sur l'adjacent (vécu seed 95001 : Drachnyen chunk 10040→2592 puis Shiron normal NON-overkill → FJ 2083 sur Aun'Shi ; CONFIRMÉ seed 95002 : Dante normal NON-overkill (3197 frappé pile 3197) → FJ Eviscerate 754+824 + LightImUp 3× Projectile 160 = 1738 = mort de Dante) ; ✅ **SUPPRESSION VÉRIFIÉE seed 98001** : Gulgortz chippé sur plusieurs tours puis tué depuis **1248 PV** par Snotflogga BeastSlayer (gros hit, >2× = overkill) → AUCUNE FJ/LightImUp observée dans la cascade (i2 « unless Overkilled » confirmé) ; budgétiser dmg >2× PV restants (Gulgortz ~10k → besoin >6394 sur une cible pleine, ex. Dante LightOfSanguinius 5× Melta ; Snotflogga/Tanksmasha BeastSlayer vs BigTarget = overkiller idéal) ; ce n'est PAS le wincon (no Ambush/no pump) → le chiper sur plusieurs tours puis l'overkiller, le laisser pour la fin après les engines ; tuer AVANT le Waaagh ou accepter les Boys ; ⚠ **VARIANTE SAFETY si on ne peut PAS overkiller (vécu seed 70009 triggered-against-me)** : tué NON-overkill (Tanksmasha 4520 sur 3933) → FJ a fire (~3537 mêlée+LightImUp), MAIS routé sur le seul adjacent = un TANK high-HP (Tanksmasha, survécu) = riposte absorbée sans perte ; si l'overkill est impossible, finir Gulgortz avec UNIQUEMENT un corps high-HP adjacent (jamais un fragile) [n=4, 70009]`
- **adeptCanoness « Roswitha » (Imperium, Sisters of Battle, ranged/mêlée, anti-Psyker)** — `BrazierOfHolyFire`
  (Flame range 2 ; **2× Flame hits vs cibles non-Daemon ; vs Daemon : 4× hits AU LIEU de 2 + aura +60% dmg à
  tous les Daemons dans 2 hex ce round et le suivant — Daemons Immune : +20% seulement**. Bonus Daemon STRICTEMENT
  gaté sur la faction de la cible : Necrons/Xenos/autres non-Chaos ne reçoivent QUE le chemin 2×). `CondemnorStake`
  (**+2183 dmg vs Psykers** → fait de Roswitha un **assassin de Psykers dédié**, comme Tjark côté anti-Psyker ;
  non pertinent face à un roster sans Psyker). `ActOfFaith` (+Crit Chance/Damage à chaque mort/kill
  d'un Imperial, reset au crit — PAS de bonus de PV, cf. note RitesOfRestoration). **PAS de Resilient,
  PV modeste** → finisher trivial une fois chunkée ; cible prioritaire APRÈS l'engine Isabella. Peut être
  **ressuscitée par Isabella** (RitesOfRestoration, à 1819 PV) → la re-tuer est gâché si Isabella vit
  encore. **Vérifié live seed 70002** (à MOI) : Brazier 2× Flame (~4085+4952) = **one-shot d'Aleph-Null 9037→0**
  (Necron = non-Daemon → chemin 2× appliqué, pas de bonus Daemon, kill propre quand même) ; CondemnorStake +2183
  vs Psyker a posé le **4551 KILL GRATUIT sur l'Ahriman ennemi (Psyker) en réaction** quand il a dive.
  `▸ Tac: rôle=carry/control · menace=med (seule menace anti-Daemon sérieuse vs un roster Chaos/summons ; ActOfFaith stacke le crit par kill/death Imperial) · counter=tuer TÔT (8533 PV, pas Resilient) ; si un reviver vit (Isabella), tuer le reviver d'abord ; ⚠ BrazierOfHolyFire DOUBLE vs Daemons (4× hits Flame au lieu de 2 + aura +60% Daemon dmg 2 rounds ; Immune +20%) → NE PAS clusterer mes Daemons/summons (PinkHorror/Screamers) adjacents à ses cibles ; CondemnorStake +2183 vs Psykers → ne pas présenter Abraxas/Patriarch adjacent · si à MOI : Brazier = gros nuke single-target (2× ~4-5k = one-shot un 9k non-Daemon, 4× +60% vs Daemons — garder au RANGE vs cibles Explodes) ; router Roswitha sur les Psykers ennemis (CondemnorStake = assassin de casters dédié) ; soft → finisher trivial une fois chunkée (vécu seed 96000 : tuée T2 par Azrael+Patriarch ; vécu seed 70002 à MOI : one-shot Aleph-Null + free 4551 KILL CondemnorStake sur Ahriman Psyker) [n=3, 70002]`
  `▸ Tac (CONTRE MA COMPO summon+Psyker — seed 70059 W) : confirmée comme HARD-COUNTER DÉDIÉ de ma compo Chaos summon+Psyker (BrazierOfHolyFire 4× +60% aura vs mes Bloodletter/Blue Horror Daemons + CondemnorStake +2183 vs mes 2 Psykers Typhus/Archimatos) → au recon, traiter Roswitha comme une menace SPÉCIFIQUE quand JE fielde Daemons+Psykers (miroir de l'aura-anti-X LIVE). Mitigation appliquée : ne pas clusterer mes Daemon-summons sur ses cibles + ne pas présenter mes Psykers adjacents + la tuer TOP-early parmi les softs (soft 8533, no-Resilient → Tarvakh MurderousSwing 4146 + Typhus 604 l'ont chunkée puis tuée). Elle tombe vite une fois le dive l'expose [n=1, 70059]`
- **custoKyrus « Tyrith » (Custodes, Resilient, counter)** — passif `UnwaveringSentinel` : à chaque
  tour ennemi, après que Tyrith est attaquée par une unité ≤range 2, elle inflige **2× Bolter** (Pierce20)
  à l'attaquant (range tombe à 1 si un ennemi lui est adjacent). `Resilient` : coup létal non-Overkill
  → 1 PV ; un 2ᵉ hit à 1 PV tue (pas de re-trigger) ; one-shot = besoin d'Overkill. **`VigilanceEternal`
  (id 1202, actif)** : mêlée mobile **3× Power** (PiercingRatio 40, range 2, cd 2, initial cd 0),
  **réutilisable plusieurs fois/combat** et **ne termine PAS son tour**. Cible UNIQUEMENT un ennemi
  **déjà adjacent** OU ayant **un hex libre adjacent dans la move range 2** de Tyrith (elle gap-close
  sur cet hex) ; **si aucun hex libre éligible n'existe, l'ability ne peut pas s'exécuter** (les plans
  affichent ~0 dmg). i2/gameconfig vérifiés (seed 95000). NB owner = Tyrith (PAS « Kyrus » comme un
  retour combat l'a écrit par erreur ; `--unit Kyrus` = unité inconnue en gameconfig).
- **custoBladeChampion « Kariyan » (Custodes, anvil anti-normal-attack, Resilient)** — suite défensive :
  `MartialKatah` (−20% dmg de TOUTES les attaques NORMALES subies ; +100% dmg vs Summons) + `Parry`
  (−1 hit aux attaques MÊLÉE multi-hit subies, min 1) + `BeastSlayer` (10% CHANCE de bloquer 100% de
  l'armure courante en dmg — occasionnel, pas fiable) + `Resilient`. Net : blunt fortement un focus
  multi-source d'attaques NORMALES mêlée, et Resilient achète exactement 1 hit de plus avant la mort.
  Actifs `MartialInspiration` (3× Eviscerate Pierce50) + `LegacyOfCombat` bypassent SON MartialKatah
  (actifs ≠ normales) → un porteur de MartialKatah se craque à l'ACTIF, pas à la normale.
- **tauMarksman « Sho'syl » (Tau, ranged, move2, Camouflage+RangedSpecialist)** — actif
  `SeekerMissileFrequencyLock` (1069, range 5) : marque (Markerlight + lock) ; au **DÉBUT du PROCHAIN
  tour de Sho'syl, s'il est encore vivant**, la cible prend 1× Heavy Round (Pierce55, 5456-6184, capé
  aux PV cible) — tue à travers le délai, contournable seulement en tuant Sho'syl avant. Attaque normale
  = passif `MV71SniperDroneSquad` (id 1076) : summon une MV71 Sniper Drone (1455 PV) qui attaque avec le
  Damage stat de Sho'syl + pose un Markerlight (max 3 drones). **Synergie : coupler le Seeker-mark avec
  un Taunt/BlockMovement** pour que la cible ne puisse fuir le tir retardé. ⚠ **AUTO-TARGET hérité** :
  vérifié seed 96001 — le missile **fire au DÉBUT du tour de Sho'syl, PAS à l'endturn** ; un missile
  hérité d'un état runner précédent garde sa cible auto-armée (visait Kharn au lieu de la wincon
  Isabella) → dès le build, **re-cibler/annuler les missiles hérités vers la vraie wincon** avant de
  jouer. **Caveat outil** : dans `play --spec`, le cast `SeekerMissileFrequencyLock` a `mutated=False`
  (effets purement DIFFÉRÉS, aucun dégât immédiat) → la garde anti-no-op déclenche TOUR ABANDONNÉ à tort
  ; **workaround = `act ability` individuel** pour les abilities à effets différés. (n=1)
  ⚠ **MV71 DRONE = FORCE-MULTIPLIER FOCUS-KILL confirmé (Verif seed 70058)** : i2 MV71SniperDroneSquad =
  « This attack uses Sho'syl's Damage stat, while other effects, like buffs, are taken from the Drone » → le
  drone summoné **frappe avec le Damage stat de Sho'syl, PAS son profil base 1528** → un drone back-row peut
  **delete un forward sans que Sho'syl bouge** (observé : 5924 KILL sur ma Jain Zar à (4,3)). Drone HP observé
  1996 > base 1455 (scale au niveau/rareté du summon). Le drone devient **chair inerte (~1996, dmg ~base 1528)
  dès que Sho'syl meurt** → tuer Sho'syl coupe ET le Seeker ET la menace drone. **Ne PAS avancer une unité dans
  la reach COMBINÉE de Sho'syl (drone-summon) + un autre dealer back-row** : la reach/dmg du drone n'apparaît
  PAS dans le danger-zone overlay (summoner blind spot, SKILL §4).
  ⚠ **MV71 DRONE = BURST IMMÉDIAT ON-DEMAND côté MIEN (vécu seed 70057 W, Sho'syl dans MON roster)** : l'attaque
  normale de Sho'syl summon un drone qui attaque **immédiatement** pour ~3854-5782 (Attack_Override=4015, au Damage
  stat de Sho'syl) DEPUIS la tuile courante/shallow — c'est un **burst-on-demand**, PAS le Seeker différé. Permet de
  délivrer un gros chunk SANS exposer Sho'syl + le drone reste comme **screen** (SaviorProtocols 50% intercept pour
  les T'au adjacents). Combiné à Tan Gi'da ControlEdict (Vanguard-on-attack) = chaîne de corps-écrans qui soakent le
  focus ennemi (vécu seed 70057 : drone + Vanguard ont absorbé ~14k du focus au lieu de mes héros).
  `▸ Tac (n+1 MINE, seed 70057 W) : Sho'syl côté MIEN = carry burst + screen-generator. La normale (MV71 drone) = chunk IMMÉDIAT ~3854-5782 depuis tuile shallow + un drone-screen persistant → délivrer du dmg sans avancer Sho'syl ; garder Sho'syl shallow/écrané (c'est l'amplificateur à protéger). [n=1, 70057-mine]`
  `▸ Tac: rôle=engine (summoner/seeker) · menace=CRITICAL (Seeker = ~5456-6184 kill garanti undodgeable au début de SON prochain tour, fire quelle que soit la position de la cible — ne se dodge PAS en bougeant, contrairement à HeavyRailRifle ; + MV71 drone qui frappe au Damage stat de Sho'syl = focus-kill ~5924 d'un forward sans bouger Sho'syl ; + reçoit TwistedScience pump 6527→9519) · counter=DOIT mourir avant que son 1er Seeker résolve — il est la SOURCE du Seeker ET des drones (drones inertes ~1996 une fois mort) ; il kite row 7-9 derrière le mur mêlée = souvent inatteignable pour un roster melee/short-range MAIS devient ATTEIGNABLE si son screen mêlée dive et meurt (vécu seed 70058 : Aesoth K! Sho'syl T4 une fois le screen tombé) ; Camouflage blunt la rétorsion ranged (-1/-2/-3 hits) → un kill mêlée/adjacent fonctionne (Aesoth K? 6527 exact) ; NE PAS over-extendre un non-tank dans la reach Sho'syl+drone (drone-reach invisible à l'overlay) [n=2, 97001+70058]`
- **necroOverlord « Anuphet » (Necron, move3, mêlée Energy)** — passif `MartialApotheosis`
  **[AUTO:StartTurn]** : au début du tour d'Anuphet, auto-inflige **2× Energy (Pierce30) à un ennemi
  adjacent au hasard**, HORS de son activation → **finit gratis un survivant à 1 PV** (ex. un Resilient
  laissé à 1) sans dépenser d'action. Garder les unités bas-PV hors de l'adjacence au début de son tour.
  `ResurrectionOrb` (1009, summon SANS dmg) = défaut d'`act` sans --ability → toujours passer --ability
  explicite (cf. §1) ; Warriors invoqués non-commandables au spawn mais menacent via Overwatch (H17).
  **`ResurrectionOrb` = SNOWBALL (i2 vérifié seed 98002)** : summon **1 Necron Warrior par round écoulé**
  + **1 par allié LivingMetal déjà défait dans le combat** (clause qui RÉCOMPENSE mes kills sur ses Necrons).
  Les stats imprimées dans le texte (4365 PV / 1455 dmg / 1091 armure) sont **PRE-scaling** : le PV runtime est
  plus haut (observé **~5983** à niveau plus élevé ; Necron Warrior summon = move2, ranged r2 Gauss). ⚠ **[indispo]
  après le cast = once-per-turn** (pas re-castable le tour suivant, vérifié seed 70000 — standard active-ability
  cooldown). **Doctrine : tuer Anuphet TÔT** (soft 8536, no-Resilient,
  killable en réaction s'il dive) avant que le board flood de corps LivingMetal/ReanimationProtocols ; killé T2
  ici (chunké par Yazaghor, fini par réaction TG).
  `▸ Tac: rôle=engine (summoner) · menace=high (ResurrectionOrb = 1 Warrior 4365-5983 PV/round +1/LivingMetal mort + LivingMetal self-regen + MartialApotheosis auto-2hit start-of-turn ; source du snowball Necron) · counter=focus-kill TÔT avant que le board se remplisse (soft 8536, no-Resilient → tout K! franc/réaction le tue) ; killable s'il dive, MAIS s'il reste backline (vécu seed 70000 enemy Anuphet (6,2-6,6) intouchable tout le combat) = SECONDAIRE après les engines AoE/snowball atteignables ; ne PAS out-DPS l'output réparé, briser la SOURCE (lui + Aleph-Null repair) [n=2, 98002/70000]`
- **necroWarden « Makhotep » (Necron, mêlée, Mechanical, anvil/aura)** — `RelentlessMarch` (actif/aura) :
  **aura START-OF-TURN** — donne **+1 Movement à TOUS les alliés qui DÉMARRENT leur tour dans un hex
  adjacent** à Makhotep, ET **répare les Mechanical** parmi eux de **1455 PV** (i2 vérifié seed 95002 :
  RelentlessMarch_Effect apparu sur Yarrick + Gulgortz au début du tour ennemi, r1 restant). Sa valeur
  réelle = ce **buff de mobilité d'équipe + repair-aura** (donne +1 move à Gulgortz/OrkBoyz, répare les
  Mechanical/summons) bien plus que ses dégâts directs. `AdaptiveStrategy` (actif, non observé live ce
  match). `LivingMetal` (regen %max PV début de tour → Mechanical, repair-only). **Tuer Makhotep = nier
  le +1 move + le repair-aura à toute la grappe adjacente.** ⚠ « non-character summons get repaired » et
  « DangerZone effect » d'un retour combat = NON dans i2 (i2 dit « Mechanical units » sans distinction
  character/summon ; DangerZone = effet moteur sans source ability/trait) → ne pas inscrire ces nuances.
  `▸ Tac: rôle=anvil/engine · menace=med (aura +1 move équipe + repair 1455 Mechanical au start-of-turn = accélère/sustain la grappe) · counter=le tuer pour stripper le +1 move + le repair-aura aux summons/Mechanical adjacents (Gulgortz/OrkBoyz) ; LivingMetal = repair-only → kill en burst, pas du chip [n=1]`
- **tyranDeathleaper « Deathleaper » (Tyranid, assassin, Camouflage)** — `Camouflage` : attaques RANGED
  contre lui = **−1 hit ; −2 hits si l'attaquant est à >2 hex ; −3 hits en Tall Grass** (plancher
  toujours ≥1 hit). → un finisher ranged multi-hit à distance perd la moitié/plus de ses hits = **peu
  fiable pour l'achever** (vécu : normal 4 hits >2 hex ⇒ ~1-2 hits). Pour fiabiliser : se rapprocher
  à ≤2 hex (−1 hit seulement), éviter Tall Grass, ou finir en mêlée / via un proc AUTO garanti (Seeker
  StartTurn). Melee-finish > ranged-finish vs Deathleaper hors de portée. Aussi `Terrifying` (réduit la
  mêlée subie, §1) + deep-strike/Infiltrate (pas d'OW) + FeederTendrils (heal 2401 à la charge) ; fragile
  8032, **PAS Resilient**.
  `▸ Tac: rôle=control/assassin · menace=high (deep-strike + Infiltrate + Camouflage + Terrifying + self-heal sur charge) · counter=MELEE-finish (Camouflage rend le ranged peu fiable ; le Terrifying réduit la mêlée MAIS un multi-hit splash type JakhalStimms 4-hit l'overcome — vécu seed 97000 : chunké 8032→303 en un splash adjacent-aux-deux) ; le tuer le tour où il est exposé (avant FearOfTheUnseen / re-vanish) ; pas Resilient → un K! franc multi-hit suffit ; ⚠ confirmé n+1 que le multi-hit DISCRET d'une normale melee (Snotflogga SquigHound 3 hits) overcome Terrifying ET Camouflage en une activation (~8k, near-one-shot 8032) → router un melee multi-hitter dessus le tour où il sort du deep-strike (vécu seed 70053 : resté en deep-strike T1, émergé T2, tué T6 par Snotflogga AVANT FearOfTheUnseen vanish/re-strike) ; ⚠ n+1 RANGED-À-COURTE-PORTÉE (vécu seed 70054) : Camouflage ne retire que −1 hit à ≤2 hex (vs −2/−3 à >2 hex/Tall Grass) → un focus ranged à ≤2 hex chunke ENCORE gros (Darkstrider 3654 + Isaak 3383 + Dante melee 995 = ~7400 overkill T4 sur Deathleaper isolé à (1,3)) → le focus-down du tour où il sort du deep-strike marche AUSSI au ranged si on est collé à ≤2 hex, la mêlée fiabilise le finish [n=3, 97000/70053/70054]`
  `▸ Tac (n+1 backline-reach, seed 70055) : ⚠ deep-strike (sortie NON-adjacente) + Infiltrate + move3 = reach quasi pleine-planche → il atteint la backline « safe » (a tué mon Archimatos 4822 que je croyais protégé) ; ne JAMAIS laisser un fragile dans sa zone de reach (move3 + deep-strike). Camouflage blunte le ranged ET Terrifying blunte la mêlée → dur à FINIR efficacement → le focus-down d'UN gros source le tour où il est exposé/ciblable ; sinon il survit chunké (~3214 fin de partie seed 70055) et contribue au wipe. MELEE-finish préféré (multi-hit discret bat Terrifying, cf. n=2 ci-dessus) [n=3, 97000/70053/70055]`
  `▸ Tac (n+1 focus-kill-on-emerge, seed 70060 W) : confirmé tué LE TOUR où il émerge du deep-strike, AVANT FearOfTheUnseen re-vanish — combo CLOSE-RANGE-ranged + MULTI-HIT-melee : Sarquael 5124 ranged depuis r3 (Camouflage à ≤2-3 hex ne retire qu'1-2 hits → chunk gros) + Aun'Shi 5-hit melee (les hits discrets battent Terrifying) = 8022→0 clean. Nauseous ContagionsOfNurgle −armure aura aide aussi. Pas Resilient → un focus coordonné le tour exposé suffit ; ne PAS attendre qu'il re-vanish [n=4, 97000/70053/70055/70060]`
- **bloodSanguinary « Nicodemus » (Blood Angels, healer)** — `BloodChalice` (1175) : **SET tous les
  alliés non-Mechanical hex-adjacents à 50% PV** (set absolu, pas heal-to-min) → **FRIENDLY FIRE sur
  tout allié au-dessus de 50%** (vécu : mon Snotflogga 12049→6024), heal seulement les alliés <50% ;
  Mechanical non affectés. Les mêmes gagnent `BloodChalice_HealOnAttack` (jusqu'au début de leur prochain
  tour : +20% pierce mêlée + heal 3638 sur une attaque mêlée). **Énumérer TOUS les hex-voisins avant de
  caster.** `SanguinaryPriest` (passif observé seed 70051 : regen ~1091-1601 aux alliés adjacents quand
  Nicodemus se déplace). **PAS de Resilient, PAS de FinalJustice** (seed 70051) → tout K! le tue propre.
  `▸ Tac: rôle=engine (Healer de sustain) · menace=high (BloodChalice set-50% + HealOnAttack 3638 + SanguinaryPriest regen-on-move 1091-1601 = sustain l'équipe entière) · counter=le tuer/chunker AVANT qu'il sustain le dive ; no Resilient/no FJ → tout K! le défait propre (vécu seed 70051 : chunké 9035→1465 T4 puis fini T5 par Lucien avant tout cycle de heal significatif) ; se cache souvent en row arrière → le catcher au RANGED ou en réaction quand il dive [n=1, 70051]`
- **eldarJainZar « Jain Zar » (Aeldari, mêlée)** — `SilentDeath` (Melee, Piercing **Pierce80** =
  contourne l'armure) : 3 hits sur la cible primaire **ET jusqu'à 3 ennemis ADJACENTS entre eux**
  (adjacency-chain AoE → 1 cast cleave un cluster). **Arme lancée** : Jain Zar **ne se déplace PAS**
  (l'arme revient dans ses mains) → cast depuis sa position sans s'exposer. Comme les dégâts résolvent en
  hits discrets, **bat Resilient sur CHAQUE cible** (hit 1 → 1 PV, hits 2-3 tuent, sauf Overkill). Peut
  **tuer une unité ET chunker une voisine dans le même cast** (vérifié seed 70001 : a fini leur Nicodemus
  2301 ET chunké leur Dante adjacent 7846→5558 en un cast) → finisher d'engine qui splash GRATIS le carry
  voisin. Excellent vs clusters armurés. ⚠ **once-per-battle observé live (seed 70001 : [indispo] après un
  usage, jamais rafraîchi)** — NON corroboré par gameconfig (aucun champ cooldown/munitions) → cf. H13, le
  réserver pour un swing décisif, ne pas l'alpha-dump. `Infiltrate` (ne déclenche **PAS** l'Overwatch ennemi
  → s'approche gratis, peut flanker la backline) ; `TerrorsLament` (aura −582 dmg / −1 hit mêlée aux ennemis
  adjacents → blunt aussi les ripostes mêlée et les death-ripostes FinalJustice de mes forward units).
  `▸ Tac: rôle=carry · menace=high (assassin flanker : SilentDeath spread AoE Pierce80 + Infiltrate no-OW + aura debuff mêlée) · counter=la tuer TÔT au RANGED avant qu'elle atteigne la backline (Infiltrate = mon OW ne la stoppe pas) ; NE PAS stacker mes unités adjacentes (SilentDeath cleave un cluster) ; un burst ranged la défait franc [n=1]`
  `▸ Tac (anti-TerrorsLament — la TUER au RANGED/Psychic, JAMAIS finir en mêlée, [self-play consensus, seed 80003]) : son aura `TerrorsLament` gute le mêlée adjacent (vérifié live des 2 sides : ripostes mêlée réduites à 420-790 / 232-908 vs Jain Zar) → un gang-mêlée pour la finir se fait blunt et laisse un survivant. Réponse propre = **chip + finish au RANGED/Psychic** (ignore l'aura, qui ne touche QUE le mêlée adjacent). Corollaire défensif quand JAIN ZAR EST À MOI : back-anchor avec TerrorsLament ne protège que l'ADJACENT (near-worthless vs un core Psyker ranged) → elle doit KILLER des casters, pas anchorer. Vécu seed 80003 (team2 W) : team2 a été FORCÉ de la tuer au Psychic ranged car le mêlée était inefficace.`
- **admecDominus « Vitruvius » (AdMech, ranged)** — `RadBombardment` : AoE en **LIGNE droite** (Toxic
  Pierce70) qui **FRIENDLY-FIRE** (i2 « all units in a straight line », PAS « all enemies » → touche
  les alliés sur la ligne ; vécu : 3789 sur son propre Patermine). Pose Contamination sur chaque hex de
  la ligne + **Suppressed (Pinned)** sur tous les touchés. Longueur = 2 hexes +1 par round écoulé +1
  par heal Mechanic ami. Viser pour ne clipper QUE des ennemis. `Mechanic` (repair-engine). **Dégât
  max level = 3274-4001 Toxic (70% pierce)** ; `nrOfHits:1` mais c'est un **AoE pleine-ligne en UN cast**
  → CHAQUE unité sur la ligne prend un hit FULL indépendant (vécu seed 70003 : Thaddeus 3810 + Nicodemus
  3282 sur la MÊME ligne en un seul cast — une grappe mid-board prise dans la ligne perd plusieurs units
  d'un coup). Croissance rapide → peut atteindre le mid-board T2-T3, surtout avec un Mechanic support.
  `▸ Tac: rôle=engine · menace=high (dealer ranged r2/line : RadBombardment = ligne AoE Toxic 3274-4001 qui GRANDIT +1/round et +1/heal Mechanic + Suppress + friendly-fire ; MasterAnnihilator marque → team +1 hit vs marqué = amplificateur de focus) · counter=soft (~9035, pas Resilient) → le FINIR au range (un chip ne suffit PAS : un engine de mark/ligne croissante survit pour fully amplifier) ; le tuer en réaction quand il dive (vécu seed 98004 : a chunké Mephiston 3624 + Asmodai 3300 T2 en line ranged puis tué en réaction T2) ; casser le buff-engine effondre l'amplification du focus ranged [n=2]`
  `  ⚠ CONTRADICTION counter (seed 70003) : chippé 9035→6570 par le barrage T1 mais PAS fini → il a fire RadBombardment 3810 et tué mon carry au tour suivant. Le « focusable/punissable » de 98004 (kill en réaction) NE tient que si on le TUE ; un chip-sans-kill le laisse amplifier = il faut un set-up de FINISH au range, pas un poke.`
  `  ▸ Tac (n+1 RadBombardment = ALPHA multi-cible le plus impactant d'un combat, CONFIRMÉ self-play consensus, seed 80000 (opus run)) : un SEUL cast a chunké QUATRE ennemis groupés en ligne + tué un drone — Tigurius 6525→1954, Tyrant Guard 7530→2512, Exitor-Rho 8032→4569, Sho'syl 6527→3917 (+ drone 1996→0), Contamination + Suppress sur tous (probablement amplifié par MasterAnnihilator +1 hit). Le profil Toxic Pierce70 BYPASSE Terrifying/armure. ⚠ **cross-validé les DEUX sides** : B (mine) a exécuté l'alpha, A (theirs) a subi le chunk de toute sa ligne clusterée = un BLOB serré est la PIRE forme vs RadBombardment (multi-hit ligne garanti). DOCTRINE défensive : ESPACER les units pour ne donner qu'1-2 cibles par ligne, jamais un blob dans une rangée droite. [self-play consensus, seed 80000 (opus run)]`
  `  ▸ Tac (3ᵉ run seed 80000 = RadBombardment SEUL gagne, sans EnvEndBombardment) : run distinct (team2 W net à T5, PAS un mutual-wipe) — un blob team1 serré rows 0-1 a été chunké/wipe (TG + Atlacoya morts, Tigurius 6525→1305, Sho'syl 6527→3917) sur la transition de tour T5, state-file loggant RadBombardment + Contamination (+ Foehammer post-kill). ⚠ confirme que RadBombardment+MasterAnnihilator-mark+ContagionsOfNurgle-shred+Foehammer SUFFISENT à gagner par eux-mêmes — pas besoin du round-cap. A (theirs) a correctement attribué la cascade à RadBombardment ; B (mine) l'a mal attribuée à un EnvEndBombardment (absent à round ~5, cf. H57). Le clustered-low-blob reste la PIRE forme vs cet engine, 3ᵉ confirmation. [self-play consensus, seed 80000 (opus + moves fix), 3ᵉ run]`
  `  ▸ Tac (4ᵉ run seed 80000, 2026-06-23 — FRIENDLY-FIRE backline confirmé live) : la ligne tirée depuis row 9 a chipé MA front-line row 0 à longue portée ET friendly-firé SA PROPRE backline ennemie clusterée (Aun'Shi −1707, Vitruvius −1807, Pestillian −2409 dans le MÊME barrage) — A (theirs) a directement observé l'auto-chip d'un backline blob serré. Cross-cohérent avec i2 « all units in a straight line » : un cluster ENNEMI dans une rangée droite s'auto-chip aussi → viser pour clipper que MES ennemis, et un blob ennemi serré est exploitable (le forcer à manger son propre barrage). [self-play consensus, seed 80000, run #4]`
- **darkaCompanion « Sarquael » (Dark Angels, ranged)** — `Supercharge` (1103, Ranged Plasma, range 3,
  +35% pierce) : hit la cible (3274-4001 lvl65) ET **jusqu'à 2 ennemis dans les hexes DIRECTEMENT
  DERRIÈRE la cible** (2183-2619 chacun) → outil de décapitation vs formations alignées (summoner/carry
  avec des unités derrière) ; laisse aussi un debuff +35% Plasma-pierce sur tous les touchés jusqu'à son
  prochain tour. Passif `GrimRetribution` (overwatch) : chaque tour ennemi, SI aucun ennemi adjacent à
  Sarquael ET il (ou un Dark Angel adjacent) a été attaqué, auto-fire 1× Plasma (Pierce65, ~2183-2619)
  sur le 1ᵉʳ attaquant en portée. Lever = le garder hors de l'adjacence mêlée (pas « skip son action »).
  ⚠ **GATE Overwatch = NOT-ATTACKED (Verif-confirmé seed 70060)** : l'Overwatch (trait + GrimRetribution) s'arme seulement s'il
  N'A PAS attaqué ce tour (trait « nor after that ») → laisser Sarquael **unactioned** près du cluster = OW armé qui auto-tire
  un diveur au tour ennemi (vécu seed 70060 : 5214 [overwatch] sur un attaquant). ⚠ **id-unité** : le hero « Sarquael » apparaît
  aussi sous l'id `darkaHellblaster` (variante Hellblaster, même kit Supercharge r3 + GrimRetribution).
  `▸ Tac: rôle=turret ranged (à MOI) · valeur=high (Supercharge r3 décapitation 6366 + GrimRetribution held-overwatch) · usage à MOI = HOLD Sarquael unactioned près du cluster (OW armé only-if-not-attacked) pour punir le dive ennemi en réaction ; ne JAMAIS le pousser en coin (coin = hors portée OW r3 → NET +0.17 vs NET +4.01 à tenir près du cluster, vécu seed 70060) ; lead Supercharge (no-move = HeavyWeapon +dmg) sur un engine soft aligné = chunk décisif + debuff Plasma-pierce ; le garder hors adjacence mêlée pour que GrimRetribution fire [n=1, 70060]`
  `▸ Tac (ENNEMI, seed 70057 W, GrimRetribution confirmé Verif) : rôle=control · menace=med (r3 Plasma + Overwatch + GrimRetribution counter + FinalJustice + HeavyWeapon, 7029 soft no-Resilient) · counter=BUDGÉTER le contre-coup : si AUCUN ennemi n'est adjacent à Sarquael, toute attaque RANGED sur lui (ou un Dark Angel adjacent) déclenche un Overwatch Plasma counter ~2183-2619 (observé 2760 sur mon Vitruvius qui a survécu) → soit COLLER un de mes corps adjacent à Sarquael pour suppress GrimRetribution avant de le poke, soit accepter/absorber le counter sur un corps tanky ; le tuer enlève l'Overwatch + la menace ranged. FJ présent → overkill ou route la riposte [n=1, 70057]`
- **blackTerminator « Angrax » (Black Legion)** — (cf. aussi §3bis ci-dessus) overwatch `HatefulAssault` :
  riposte (2× Power ~873-1237) quand un ennemi adjacent **BOUGE HORS** d'un hex adjacent à Angrax
  (disengagement, PAS l'approche) → se désengager de sa mêlée se paie mid-move.
- **darkaAsmodai « Asmodai » (Dark Angels, mêlée)** — `ExemplarOfHate` : applique un **mark +728 dmg
  melee/Overwatch** sur n'importe quel ennemi, **pour ce round et le suivant** (2 rounds = RemainingTurns=4
  ticks internes, 2 game-rounds × 2 side-turns). **TOUS les alliés** déalent +728/hit melee/OW vs la cible
  marquée → **multiplicatif avec les armes multi-hit** : un burst 4-hit gagne +728×4 = +2912 (vérifié seed
  98004 : a amplifié Haarken `HeraldOfTheApocalypse` 2832-4248 → 6024-7436 sur Helbrecht marqué, delta ~3192
  cohérent avec 4 hits × 728 + écho LetTheGalaxyBurn/+1310). Rider « si la cible est **Chaos** » (Suppress
  + une attaque normale gratuite d'un Dark Angel allié, cap 4365/hit) — HYPOTHÈSE (H15) : gaté par la
  portée d'attaque normale du Dark Angel exécutant ; positionner Asmodai adjacent à la cible Chaos avant
  de caster pour la pleine valeur. `FearedInterrogator` : +728 dmg vs cibles Suppressed/Stunned/adjacentes
  à un Dark Angel. `Terrifying` (réduit la mêlée subie → bypass = RANGED, cf. §1).
  `▸ Tac: rôle=control · menace=med · counter=Terrifying → le tuer/chunker au RANGED (la mêlée est réduite) ; le viser AVANT qu'il mark une pièce-clé (+728 à toute mêlée/OW alliée 2 rounds) ; reste souvent en retrait jusqu'au mid-game (vécu seed 95000 : a atteint (2,2) T3 et tué Mataneo) [n=1]`
- **templSwordBrother « Godswyl » (Black Templars, mêlée)** — `ThunderousAssault` : 1 hit 4365-4729
  Power (Pierce40), push la cible adjacente 1 hex, **Stun 1 round** (PAS 2), puis **GODSWYL lui-même
  avance sur l'hex vacant** (repositionnement forward designé, pas un push d'allié), et les cibles
  défaites par l'attaque sont **toujours overkillées**. `ChampionOfTheFeast` (passif **move-triggered**,
  PAS un counter-attack) : **après avoir bougé**, 1× Power Damage (Pierce40) à un ennemi adjacent **ET
  réduit son Armour de 728 PERMANENT (rest of battle)** ; **s'il ne bouge pas, fire en fin de son tour**.
  Surface dans la cascade comme `Thorns_DefenseReduction`. → un Godswyl qui avance débuffe l'armure d'un
  adjacent à vie (set-up pour la suite). (Vérifié seed 96001.) `RapidAssault` (+move/+dmg) ; `Parry` (−1 hit
  mêlée subi → préférer UN gros hit à un multi-hit contre lui).
  `▸ Tac: rôle=chaff/striker secondaire · menace=med (PAS la wincon : Common sans valeur d'engine ; danger réel = le burst ThunderousAssault 4365-4729 + Stun sur un corps bas-PV, PAS une valeur stratégique) · counter=soft (~9539, pas Resilient) = killable franc ; Parry → le frapper en UN gros hit (pas multi-hit) ; le traiter en SECONDAIRE après les engines (Patermine/Vitruvius/Nicodemus) — NE PAS investir d'output dessus, le laisser DIVER ma ligne tenue et le DELETE en réactions (vécu seed 70001 : a dive Godswyl + leur Dante dans ma held-line → mort à un reaction-kill 4-sources T3 ; son Stun ne neutralise que 1 round et la cible garde 1 move + son attaque normale, cf. §1 Stun ; vécu seed 70008 : chaff/striker confirmé — tué proprement par une réaction Gulgortz FJ-trade, et son ChampionOfTheFeast a bien appliqué Thorns_DefenseReduction −728 armure permanent sur un de mes adjacents) [n=3, 70001/70008]`
  `▸ Tac (3ᵉ confirmation rôle=chaff, seed 70055) : rôle=chaff/striker CONFIRMÉ n+1 (soft 9539 no-Resilient → tué cleanly T3 : Dante normal 5343-6669 + finish Parasite) ; le danger reste UNIQUEMENT le burst ThunderousAssault 4365-4729 + Stun 1 round sur un corps bas-PV, Parry → le frapper en UN gros hit. À traiter en SECONDAIRE (un des soft autonomous threats à tuer cheaply avec Yazaghor/Adamatar), PAS la wincon → la CONTRADICTION rôle=carry ci-dessous est RÉSOLUE : 3 matchups (70001/70008/70055) = chaff/striker secondaire [n=4, 70001/70008/70055]`
  `  ⚠ CONTRADICTION rôle RÉSOLUE (3 matchups 70001/70008/70055) : la carte KIT ci-dessus liste rôle=carry (tooltip), mais en jeu Godswyl s'est comporté en CHAFF/striker secondaire à CHAQUE fois (Common, aucune valeur d'engine, dive-puni/tué cleanly). Tag effectif = rôle=chaff/striker ; menace=med (le burst reste réel sur un fragile).`
- **templAggressor « Burchard » (Black Templars, mêlée + ranged, ~12k PV, MkXGravis)** — anvil lourd qui
  **DEVIENT le wincon late** dès qu'on perd l'armor-bypass. **`MkXGravis`** (cf. §1) = double-armure (tout dmg
  entrant repasse l'Armour, **sauf Crit/Direct/Psychic**) → un roster Power/Physical low-pierce est gutté :
  vécu seed 70008, mon Imospekh Gauss Pierce60 → ~1300-1988 net/turn, Arjac Power Pierce40 → ~900/turn, Ork Boy
  Physical Pierce1 → 56-227/hit (négligeable). Ranged r2 `FragstormGrenadeLauncher` (6 Blast, leftover-hits →
  peut finir un voisin) + `Boltstorm`. **move2 (lent) = kitable** — mais il faut quand même un bypass-armure
  (Crit/Direct/Psychic) pour réellement le tuer ; sinon il out-damage 1v1 (~2786/turn observé) et overkill un
  Resilient via multi-hits.
  `▸ Tac: rôle=anvil → wincon late ÉMERGENT · menace=critical POUR UN ROSTER SANS Direct/Psychic/Crit (un tank 12k MkXGravis standalone devient INGRINDABLE une fois les screens/engines morts ; ce n'est ni un self-healer ni un reach-fail — c'est un mur high-armor que SEUL un bypass-armure tue) · counter=RÉSERVER un burst Direct/Psychic/Crit POUR LUI au recon (même famille que « réserver l'anti-armor burst » 70004/97002) ; un Power/Physical low-pierce ne peut PAS l'out-grind → ne pas planifier de le trade en mêlée, tuer les softs qu'il accompagne et accepter de ne pas le cracker SI le bypass est perdu = FLAGGER la loss ; move2 lent → kitable mais ça ne tue pas ; ⚠ vécu seed 70008 : j'ai perdu mes 2 SEULS bypass (Exitor CordClaw Direct Pierce100 + Atlacoya Direct) en over-extension T1 → Burchard est devenu le wincon imbattable, loss à 1v1 [n=1, 70008]`
  `▸ Tac (n+1 menace CONDITIONNELLE, seed 70060 W) : ⚠ menace=critical SEULEMENT comme DERNIER mur après la guerre des nombres perdue — à 6v1 c'est un GRIND TRIVIAL même sans bypass-armure : vécu seed 70060, mon roster ZÉRO Direct/Psychic/Crit a chunké Burchard 12038→1362 en UN tour focus (4 sources) puis K! le tour suivant, grâce à Nauseous ContagionsOfNurgle −armure aura (−20%) + Aun'Shi Storm of Fire +582 qui ont offset MkXGravis. La clé = GAGNER LA GUERRE DES NOMBRES D'ABORD (ici un mur de réaction Overwatch a tué les 2 carries T2 zéro perte) → affronter Burchard en 6v1 (puits trivial) au lieu d'en dernier mur ingrindable (70008). CONFIRME l'INVERSE de 70008 : un MkXGravis standalone n'est ingrindable QUE quand il est le dernier debout ET la course aux dégâts déjà perdue ; overwhelm via nombres + une −armure aura override le no-bypass [n=2, 70008/70060]`
- **spaceStormcaller « Njal » (Space Wolves, Psyker, ranged r3, move2)** — `TerminatorArmour` (cf. §1 —
  réduit la 1ʳᵉ attaque/tour hors Psychic/Direct ; sur Njal LUI-MÊME → bypass = Psychic/Direct ou 2ᵉ attaque
  distincte ; **ne peut pas être Suppressed**). `Stormcaller` (actif Psychic, **PiercingRatio=100 + trait
  `NoBlocking`** → ignore armure ET block, cf. §1 Psychic-vs-Mechanical) : **AoE = hex de la cible + TOUS
  les hexes adjacents** (Ice-covered) → touche toute la grappe ; **stun les unités FLYING touchées** (vérifié
  seed 70001 : a touché 3 de mes units ~5468 total en ignorant l'armure, et menace de stun mon Dante Flying).
  `LordOfTempests` (snowball : **+237 dmg par hex d'Ice adjacent** → monte en puissance plus la zone Ice
  s'étend). `Unstoppable`. move2 (lent) mais le reach r3 actif est profond.
  `▸ Tac: rôle=engine (Psychic-AoE armor-ignore, la wincon-pair avec un seeker/summoner type Sho'syl) · menace=high (Psychic NoBlocking bypasse l'armure ET TerminatorArmour de mes Terminators ; AoE hex+adjacents → multi-unit cluster threat ; stun mes Flying carries ; LordOfTempests +237/ice-hex snowball ; ne peut pas être Suppressed) · counter=STUN-le d'abord (Aesoth VexillaMagnifica) pour dénier son AoE un round, PUIS focus-kill ; bypass de SON TerminatorArmour = Psychic/Direct OU focus multi-attaquant en un team-turn (1ʳᵉ attaque réduite, le reste full — vécu seed 70001 : 1er hit 418 puis 4828+2786 → mort T4) OU un attaquant Mechanical HeavyGravCannon (Sy-gex +364/+60% pierce vs TermArmour : 4-hit 2534+2490+1703 → 6727→0 clean, vécu seed 70058) ; move2 lent → le zoner/out-ranger avec des r3 dealers, devient ATTEIGNABLE une fois son screen mêlée dive/mort (vécu seed 70058 : tué T4) ; NE PAS laisser un carry Flying stationnaire dans sa portée Ice (risque stun) [n=3, 70001+70058]`
- **astraBullgryn « Kut » (Astra Militarum, mêlée, anvil/BigTarget)** — `BigTarget` (cf. §1 — alliés
  adjacents −1 hit ranged ; non déplaçable). KIT (observé n=1, NON Verif-confirmé ce wave — à recon
  gameconfig avant de planifier autour) : `FragBomb` 6× hits + 3× splash à TOUS les adjacents à la
  cible ; `AvalancheOfMuscle` +437 dmg en chargeant ; bruiser lent.
  `▸ Tac: rôle=anvil · menace=med (écran/anvil des dealers, PAS la wincon : son aura BigTarget −1 hit ranged shield leurs dealers de mon ranged ; FragBomb cluster-splash + AvalancheOfMuscle +437 = danger s'il atteint une grappe) · counter=ne PAS investir d'output dessus (puits) ; racer les softs/engines ; éviter de clusterer mes units face à son FragBomb-splash (vécu seed 70003 : barrage-chippé à 8621, n'a pas engagé T1) ; ⚠ **PAS de Resilient/FinalJustice (9539) → K! propre une fois atteignable** (vécu seed 70009 : Trajann WarHowl-buffé l'a K!'d depuis sa tuile dans le burst ; vécu seed 70008 : chunké 9539→2675 par une charge Gulgortz Waaagh puis fini par une normale Arjac = anvil sans wincon confirmé n+1 ; vécu seed 70056 : pur anvil SANS amplificateur (Ragnar WarHowl mort) → secondaire, tué EN DERNIER une fois isolé 1006→0 par une K! Re'vas depuis sa tuile, aucun FJ/Resilient = confirme « anvil sans wincon, faible valeur stratégique » n+2 ; son aura BigTarget devient sans objet une fois isolé) [n=4, 70009/70008/70056]`
- **astraDreir « Dreir »** — (déjà décrit ci-dessus, inchangé)
- **genesMagus « Xybia » (Genestealer, Psyker, summon-engine)** — wincon classique : `MindControl`
  (cf. §1 — range 3, Taunt l'allié adjacent au + haut PV + débuff dmg + coupe l'actif de la cible),
  summon de **Neophyte Hybrids**, et trait **`Ambush`** (cf. §1 — 1ʳᵉ mort → decoy + resurrect full ;
  2ᵉ kill PERMANENT). Psychic Pierce100 NoBlocking = ignore armure. Le 1ᵉʳ kill est TEMP tant qu'un decoy
  survit → clear les decoys (Steppable, marcher dessus) OU accepter le temp-kill et planifier la 2ᵉ mort.
  Contre-pièces : Atlacoya Talons passe Direct vs Psyker (sauf taunt-lock) ; un heal cleanse ses débuffs
  MindControl ; tout Psychic NoBlocking ignore son armure.
  `▸ Tac: rôle=engine · menace=critical (summon + MindControl + Ambush-resurrect = wincon) · counter=kill early MAIS 1ᵉʳ kill TEMP (Ambush) sauf decoys clear → 2ᵉ kill PERMANENT (vérifié seed 98001 : Xybia tuée 1× → decoy HP0 + revive full T+1 ; 2ᵉ kill = RemoveUnit WasOverkilled, AUCUN decoy, AUCUN revive — first-defeat-only confirmé) ; un assassin anti-Psyker (Tjark +582) la K! outright à 8514 PV ; ⚠ quand ELLE MindControl une de mes unités, le `Taunted_OnlySpecificTargets` FORCE ma unité à taper LE taunter (Xybia adjacente) → si elle est l'allié-adjacent-au-plus-haut-PV, tuer LE taunter dans cette même action clear les 6 sous-effets instantanément (vécu seed 98001 : MindControl sur Tjark → Tjark forcé sur Xybia → je la tue, Tjark libéré) ; heal cleanse le MindControl [n=2]`
- **tyranParasite « Parasite of Mortrex » (Tyranid, move4 Flier, summon-engine)** — `ItItches` summon des
  **Ripper Swarms** (~4583-6282 PV, cf. summons §) + `BarbedOvipositor` (spawn un Ripper quand IL tue une
  cible non-Mechanical). **PAS de resurrect** → le tuer PERMANENT et tôt pour nier le snowball Rippers.
  ~9035 PV, tuable en un tour par 2-3 sources focalisées (melee/Blast + Psychic). Move4 = très mobile,
  difficile à kiter.
  `▸ Tac: rôle=engine · menace=high (Ripper snowball, move4 mobile) · counter=kill PERMANENT et tôt (pas de revive) ; focus 2-3 sources en un tour ; surveiller ses Rippers (BattleFatigue à la mort d'un ami adjacent) [n=1]`
- **spaceBlackmane « Ragnar » (Space Wolves, mêlée carry)** — `WarHowl` : self-cast (--target sur Ragnar
  lui-même) qui octroie, **jusqu'à la fin du tour**, à **Ragnar ET tous les Characters alliés SANS normale
  RANGED** (exclut p.ex. Abraxas qui a une normale ranged) : **Unstoppable + +1164 dmg de mêlée + +36% Crit
  Chance** (i2-vérifié seed 70009 : a refresh WarHowl_ExtraDamage_Unstoppable RemainingTurns=1
  VariableMultiplierPercentage=200 sur 4 Characters mêlée e=95/99/101/103, PAS sur Abraxas). ⚠ **ne CONSOMME
  PAS le tour de Ragnar** (resté à activer après le cast) ET exige que **Ragnar n'ait PAS bougé** avant de
  caster → le séquencer EN PREMIER, avant le burst (cf. §5bis MIEN-À-ENCHAÎNER). `SagaOfTheWarriorBorn`
  (+3 hits à la charge). Attaque normale **7× Chain Pierce20** (faible pen armure → armure/Terrifying
  blunt). Trait **`FinalJustice`** (cf. §1 — riposte normale 7-hit à la mort, source-agnostique, sauf
  Overkill ou aucun adjacent éligible).
  `▸ Tac: rôle=carry · menace=high (buff d'équipe + charge +3 hits) / med si on peut LOCK son WarHowl · counter=le tuer AVANT WarHowl ; 7× Chain Pierce20 = faible pen → armure/Terrifying l'amortit ; ⚠ **un TAUNT lui coupe WarHowl** (vécu seed 70006 : Azkor OverwhelmingWrath Taunt = Taunted_OnlySpecificTargets + BlockMovement + CantUseAbility → Ragnar n'a PAS pu caster WarHowl, movement-locké, forcé de frapper le taunter Azkor Terrifying qui a blunté sa mêlée à ~280-420/hit ; cf. H30) ; un STUN (Aesoth VexillaMagnifica) le verrouille aussi (Stunned r2 + MovementOverride=1 + CantUseAbility) = engine-disable total ; pour neutraliser FinalJustice : Overkill OU positionner pour que sa riposte tape un TANK (vécu seed 70006 : FJ absorbée par Aesoth tanky = 453 trivial) OU pas d'adjacent éligible · si à MOI : caster WarHowl EN PREMIER (Ragnar n'a pas bougé, ne finit pas le tour) PUIS le burst mêlée des Characters buffés — le +1164/hit énorme sur les multi-hit (Patermine 5× Psychic, Tanksmasha 3× Eviscerate) a converti des plans 2025-3039 en 3885-4899 + plusieurs K!, 3 kills en UN tour (vécu seed 70009) · ⚠ **vs un Ragnar ENNEMI = la SOURCE-wincon d'un roster all-melee** (WarHowl pump toute la ligne mêlée) → le tuer AVANT son 1er cast gutte toute l'offense ennemie (vécu seed 70056 : Ragnar tué EN RÉACTION dans mon cluster Overwatch/dive-punish AVANT d'avoir jamais casté WarHowl → Atlacoya-enemy/Tanksmasha/Kut sont restés un-buffés tout le combat = W ; son FJ 7× Chain Pierce20 = faible pen, routée sur un tank ou overkill) ; ⚠ **CONFIRM n+1 (seed 70059 W)** : Ragnar = SOURCE-wincon de la ligne all-melee (TG + Maladus bénéficiaires WarHowl), chunké T2 via Typhus PlagueWind Psychic AoE (3914) puis tué T3 via Typhus/Archimatos Psychic AVANT tout WarHowl → la ligne n'a JAMAIS été buffée ; ATTEIGNABLE parce que le bulk all-melee+anvil était CONTRAINT de diver (son FJ 7× Chain Pierce20 = ~80/hit sur mon Typhus, négligeable) [n=5, 70009/70006/70056/70059]`
  `▸ Tac (n+1 DÉFANG-PAR-LES-BÉNÉFICIAIRES, seed 70057 W) : WarHowl ne pump QUE les melee Characters SANS normale ranged (cf. KIT) → une 2ᵉ voie pour neutraliser l'engine = **tuer ses BÉNÉFICIAIRES avant l'engine lui-même**. Vécu seed 70057 : tué Dante+Helbrecht (les melee Characters bénéficiaires) T3-T4 → au moment où j'ai tué Ragnar T5, WarHowl ne pouvait plus que le SELF-buff = engine défangé même non-pré-empté ; son FJ 7× Chain Pierce20 a fire (non-overkill) mais ~232-333/hit (~1946) sur mon Mataneo armuré Mechanical = trivial (confirme la routing-onto-armored §1). DOCTRINE : contre un WarHowl-engine, soit le tuer pre-cast (n=5 ci-dessus), soit vider sa liste de bénéficiaires melee s'ils sont plus atteignables que lui [n=6, +70057]`
- **orksNob « Tanksmasha » (Orks, mêlée carry, ~10040 PV, move4, BigTarget, NON-Resilient)** — traits gameconfig
  (Verif seed 70056) : **Hero, GetStuckIn, BeastSlayer (+dmg vs BigTarget/Vehicle), Unstoppable — AUCUN FinalJustice,
  AUCUN Resilient**. Bruiser mobile move4 + charge (Suppress) ; `FragBomb`/Eviscerate multi-hit. **`UnstoppableMomentumReworked`**
  (actif charge, Verif seed 70061) = **DirectDamage Pierce100** (1 hit, base 873-1091 lvl65 **+73 dmg par hex traversé** ; +437
  `SmashaEad` après un move 2+ hex). **Pas de death-riposte ni de plancher HP** → meurt proprement à tout coup finisseur une fois chunké.
  `▸ Tac: rôle=carry · menace=high (move4 charge + BigTarget + BeastSlayer = shred mes BigTarget/Vehicle s'il connecte ; over-extend agressivement) · counter=PUNIR le dive (move4 = il dive profond — vécu seed 70056 : dove à (3,1) dans MA moitié T1 → chunké 10040→6725 par l'Overwatch Re'vas AVANT mon tour, puis focus-killé 6725→0 depuis mes back tiles, AUCUN forward push nécessaire puisqu'il est venu À MOI) ; ⚠ **PAS de Resilient/FinalJustice → K! propre une fois atteignable**, aucun floor ni riposte à respecter ; BeastSlayer ne compte que vs mes BigTarget (Re'vas) → screener mes BigTarget s'il connecte, mais il n'a jamais connecté ici [n=1, 70056]`
  `▸ Tac (n+1 UnstoppableMomentumReworked multi-target-in-line CONFIRMÉ self-play consensus, seed 80000) : la charge hit TOUS les ennemis sur la LIGNE droite en UN passage — **vécu seed 80000** (B, about=mine) : une seule charge a touché Tigurius (1415 dmg) ET Exitor-Rho (952 dmg) dans la même rangée. gameconfig confirme « Any enemies hit by the charge take 1× Direct Damage ». ⚠ **directionnel** : la ligne choisie au moment du cast décide QUI est hit ; un groupe linéaire adverse = frappe multi-cible gratuit, un groupe en arc = un seul hit. Planifier la direction de la charge pour maximiser le hit-count (jusqu'à toute la diagonale/rangée). ⚠ **tuile d'arrêt = mort** si c'est une EnvEndBombardment active : Tanksmasha s'est arrêté post-charge sur une tuile de bombardement et a été détruit à l'endturn — évaluer la tuile d'arrivée avant de caster. [self-play consensus, seed 80000]. [n=2, 70056/80000-sp]`
  `▸ Tac (NUANCE block BeastSlayer — self-play seed 80000 roundcap + recoupage gameconfig) : ⚠ **le « K! propre / aucun floor » ci-dessus a un caveat probabiliste** — `BeastSlayer` porte une clause de BLOCK (gameconfig `beastSlayerBlockChance:10, beastSlayerBlockAsMaxArmorPct:100` = **10% chance de bloquer 100% de son armure courante** sur un coup entrant). Vécu seed 80000 (A, about=theirs, confidence med) : un burst multi-source K?-labellé a chunké Tanksmasha 9232→**738 et il a SURVÉCU** — le block a absorbé assez pour qu'un K? sous-kill. ⚠ A a mis-labellé ça « BeastSnagga_ExtraBlock » mais gameconfig confirme : orksNob n'a PAS BeastSnagga, c'est la clause block de **BeastSlayer** (cf. hypotheses.md, divergence A/B flaggée). DOCTRINE : un finisher **K?** (pas K!) sur un BeastSlayer-carrier peut whiffer 10% du temps via block → préférer un OVERKILL franc (≥2× la barre, ou 3+ sources discrètes) quand le kill est décisif, ne pas budgétiser un K? near-lethal comme garanti. [self-play seed 80000 roundcap, recoupé gameconfig BeastSlayer]`
  `▸ Tac (À MOI — anti-MkXGravis, CONFIRMÉ Verif seed 70061) : `UnstoppableMomentumReworked` = **Direct Pierce100** → bypasse ENTIÈREMENT la double-armure MkXGravis (Bellator/Inceptors : « incoming damage va à travers l'armure 2× SAUF Crit/Direct », cf. §1) puisque DirectDamage ignore l'armure. ⚠ MAIS le dmg est **distance-dépendant et LOW à courte portée** (base 873-1091 + seulement +73/hex) → de 1 hex avec SmashaEad ≈ ~1463, **PAS un Bellator-cracker fiable seul** (vécu seed 70061 : ~1463 sur Bellario insuffisant ; le kill réel = Certus HeavyRound Pierce55 + réactions cluster). USAGE : réserver Tanksmasha pour une CHARGE LONGUE (maximiser les hex traversés = +73/hex + SmashaEad) sur la cible MkXGravis, OU le combiner à un finisher ranged (Certus Pierce55 + reactions) — ne jamais compter sur la seule charge courte pour cracker un tank double-armuré. [n=1, 70061 chained]`
- **orksKillaKan « Snappawrecka » (Orks, ranged, carry, ~9037 PV, BigTarget, NON-Resilient)** — `DakkaDakkaDakka`
  (ranged multi-hit ~1455-1819/hit, leftover chaîne vers un ennemi proche) : son nombre de hits **SCALE avec les
  repairs reçus = +2 hits par repair** (6 → 16 hits ; Snappawrecka est **Mechanical** donc repairable par Aleph-Null/
  Gibbas). `PowerTrip` ignore l'armure. `Explodes` à la mort (cf. §1, friendly-fire). = **carry ranged repair-SCALING
  qui devient PLUS létal à mesure qu'on le soigne.**
  `▸ Tac: rôle=carry · menace=CRITICAL (DakkaDakka 6→16 hits via repairs + PowerTrip armor-ignore + leftover-chain ; un repair-hub backline en fait un nuke ranged croissant) · counter=NE JAMAIS out-DPS le carry réparé — KILL Snappawrecka OU sa SOURCE de repair (Aleph-Null) early/au range ; soft 9037 no-Resilient mais BigTarget ; `Explodes` à la mort → finir au range ; ⚠ une source de repair (Aleph-Null) row 5-7 le rend inatteignable pour un roster mêlée = STRUCTURAL counter (vécu seed 98000 : carry+repair jamais atteints = a décidé l'attrition) [n=1, 98000]`
- **tauDarkstrider « Darkstrider » (T'au, ranged, control, ~7530 PV, soft NON-Resilient)** — `StructuralAnalyser`
  (ses attaques ranged posent un **markerlight** : les alliés adjacents / T'au à ≤2 hex font **+728 ranged** vs cible
  marquée). `RangedSpecialist`, `SuppressiveFire` (Suppress/Pinned via ranged), `FightingRetreat` (attaque + repli, ne
  finit PAS le tour), `Infiltrate` (ignore l'Overwatch ennemi → s'approche gratis et n'est PAS attrapé par MA tourelle OW).
  `▸ Tac: rôle=control (buff-engine markerlight) · menace=high SI ≥1 autre T'au/allié RANGED à feeder, sinon **LOW (engine INERTE)** · counter=le tuer au RANGED (Infiltrate = pas catchable par mon OW) ; ⚠ **DEMOTE high→low quand Darkstrider est le SEUL ranged de SON équipe** (markerlight +728 sans bénéficiaire = self-fed = inerte, même famille engine-inerte-sans-bénéficiaire H02/H33 — vécu seed 70056 : équipe 4-melee → demote LOW, traité en corps soft, tué dans le dive) ; SECONDAIRE après les vrais carries ; soft 7530 [n=2, 98000/70056]`
  `▸ Tac (À MOI — CONFIRMÉ live, seed 70054) : `StructuralAnalyser` (passif) = CHAQUE tir ranged pose un **Markerlight** (Effect_Id 188/208, 3 rounds) sur la cible ; les alliés ADJACENTS + les T'au à ≤2 hex de Darkstrider font +728 ranged vs cible marquée (Darkstrider SE qualifie via la clause T'au-à-≤2-hex). `SuppressiveFire` (trait) = chaque tir ranged Suppress AUSSI la cible (Pinned −1 move, confirmé live 2 tours). STACK : RangedSpecialist × markerlight-self × buff d'adjacence → Darkstrider = mon dealer ranged single-source DOMINANT quand le positionnement est tenu (vécu seed 70054 : 7476 sur Thoread, 4559 plan sur Tyrant Guard = mes plus gros hits du combat). USAGE : ORDONNER Darkstrider EN PREMIER dans chaque focus (poser markerlight + Pinned AVANT que les alliés tirent) ; le garder en portée pour que ses propres tirs + le buff d'équipe empilent. ⚠ le delta +728 spécifique aux ALLIÉS reste non isolé numériquement (cf. H33) mais la mécanique markerlight + Pinned est confirmée live [n=1, 70054 chained]`
- **thousSorcerer « Thaumachus » (Thousand Sons, Psyker, engine, ~7530 PV, soft NON-Resilient, Flying)** — ⚠ KIT
  encore en partie recon-only (cf. H28/H29, pas pleinement live-vérifié) : `ArcaneShield` (bouclier ~4001-5483 PV à
  l'allié non-Mechanical le + proche ≤2 hex, **priorité Thousand Sons > Chaos > autre allié > self** ; dure 1 round —
  **persiste possiblement même si Thaumachus meurt**, cf. H29 ; vécu seed 98000 : a absorbé 7064 de Tyrant Guard sur
  Dreir après la mort du caster). ⚠ **TRIGGER confirmé live (seed 70053)** : se déclenche APRÈS son move, OU à la FIN
  de son tour s'il N'A PAS bougé → tenir Thaumachus stationnaire/finishing repose le bouclier (~5483 PV) sur le même
  allié chaque tour (a gardé mon Shiron ranged carry intact tout le combat) ; `AttemptedPossession`
  (mind-control une cible ET ses summons → ils attaquent mon camp, cf. H28 — recon-only, non live-vérifié) ;
  `WeaverOfFate` (max-dmg si 3+ ennemis ont subi du Psychic). Psychic NoBlocking (ignore armure, menace les carries
  fragiles 1913-3539).
  `▸ Tac: rôle=engine (psychic/shield + anti-summon + WeaverOfFate-amplifier) · menace=high (ArcaneShield protège leur carry + AttemptedPossession anti-mes-summons + WeaverOfFate MAX-dmg si 3+ cibles Psychic + Psychic armor-ignore) · counter=(1) le DISABLE par CrushingClaws Taunt (Taunted_CantUseAbility) le neutralise TOTALEMENT 1 round — vécu seed 70000 : Taunt-locké tout le combat, n'a JAMAIS casté AttemptedPossession/ArcaneShield (= le meilleur disable, cf. H30) ; (2) le tuer TÔT avec un ranged no-move K! (Maugan Ra l'a fait seed 98000) → retire bouclier + possession + menace psychic ; soft 7530 NON-Resilient → killable franc, MAIS ne PAS le focus AVANT Tigurius (le block-aura PsychicFortress + l'AoE re-firante de Tigurius valent plus, vécu seed 70000 : split-focus Thaumachus/Tigurius = erreur, FULL-focus Tigurius d'abord) ; ⚠ budgétiser le bouclier posthume (~4-5.5k) sur sa cible avant de committer un coup létal dessus (H29) ; ✅ **À MOI = durabilité gratuite sur le carry** : le garder STATIONNAIRE/finishing → ArcaneShield (no-move → end-of-turn trigger) repose ~5483 PV sur l'allié non-Mechanical le + proche chaque tour (priorité Thousand Sons > Chaos > autre) → glue mon ranged carry à ≤2 hex pour qu'il reste shielded en continu (vécu seed 70053 : Shiron effectivement intouchable tout le combat) [n=3, 98000/70000/70053]`
- **ultraInceptorSgt « Bellator » (Ultramarines, Flying, move4, MkXGravis)** — **`DeathFromAbove`** = summon-engine :
  invoque **1 Inceptor par ROUND ÉCOULÉ** (round 1 = 1, round 2 = 2, …), chacun atterrit **adjacent à la cible** et
  l'attaque **immédiatement** (i2 vérifié seed 70000 ; Inceptor base gameconfig 4001 PV / 728 dmg / 873 armure /
  move4 mêlée — cf. entrée summon Inceptor §3bis ; live ~5483 = scaling niveau/rareté). Passif **`ShockAssault`** :
  quand Bellator attaque, tout Inceptor adjacent à LUI ré-attaque aussi (+364 dmg). **`MkXGravis`** = double-armure
  SAUF **Crit/Psychic/Direct** (cf. §1) → vulnérable au Direct Pierce100 (vécu seed 70000 : Adamatar DoomSiren l'a
  chunké 8533→3947). Flying move4 = mobile.
  `▸ Tac: rôle=engine (summoner) · menace=high (DeathFromAbove = flood d'Inceptors croissant chaque round 5483 PV move4 + ShockAssault re-attaque ; MkXGravis double-armure le rend dur au chip ranged) · counter=le tuer pour couper le flood ; son MkXGravis se BYPASSE au **Direct/Psychic/Crit** (DoomSiren Direct Pierce100 l'a chunké 8533→3947 + 2 Inceptors en un cast, vécu seed 70000) — réserver un Direct/AoE-Direct pour un cluster Bellator+Inceptors ; mobile (Flying move4) donc le catcher quand il close ; ⚠ confirmé n+1 que DeathFromAbove = board-flip CROISSANT que le move-guard 2-ply ne voit pas (cast round 3 → 3 Inceptors 5483 PV move4 landent adjacents à ma backline + attaquent direct pour 4755 dmg) — MAIS rendu ATTEIGNABLE quand l'IA dive forward (le Bellator move4 Flying close vite) → le tuer/stun EARLY pour couper le flood ; HP plus basse que son rôle ne suggère (8533, mort T5 une fois chunké) ; stun-then-finish via VexillaMagnifica (vécu seed 70053 W : T3 stun Bellator + chunk Inceptor, T5 stun puis Calandis finit) ; ⚠ **n+1 (vécu seed 70061)** : killer Bellator a STOPPÉ le flood (pas de 3-Inceptor wave round-3) → tuer le summoner coupe les casts futurs (gating caster-mort) ; le crack pratique = **Certus HeavyRound Pierce55 (partiellement à travers la double-armure) ~7534 + réactions cluster sur le dive**, PAS le Tanksmasha Direct Pierce100 (trop low à courte portée, ~1463 — bypasse MkXGravis mais ne crack pas seul) ; ⚠ « les Inceptors summonés portent MkXGravis » = OBSERVÉ non recoupé (gameconfig liste MkXGravis sur Bellator, PAS sur ultraSmnInceptor — cf. H52) [n=3, 70000/70053/70061]`
- **tyranNeurothrope « Neurothrope » (Tyranids, Psyker, move2, Flying, backline)** — **`Neuroparasite`** = snowball-engine :
  escalade en dégât Psychic à chaque hit (~+1237/niveau, cap ~15) ; **`SpiritLeech`** self-heal ~60% → **inkillable en
  late game** une fois empilé (r3 + Flying + heal). `Synapse` (buff les Tyranids autour) + **`ShadowInTheWarp`** (réduit
  MON Psychic). Le Psychic NoBlocking bypasse armure/BigTarget. Vraie wincon late-game d'une compo Psychic-cascade
  (armé par tout ce qui touche 3+ de mes units en Psychic, ex. Tigurius StormOfWrath → WeaverOfFate).
  `▸ Tac: rôle=engine (snowball Psychic) · menace=CRITICAL (Neuroparasite escalade +1237/niveau/hit + SpiritLeech self-heal 60% + r3 Flying = inkillable late ; devient la vraie wincon une fois snowballé) · counter=LE TUER EN PREMIER avant qu'il snowball ; MAIS backline + move2 + Flying + r3 = très dur à atteindre pour un roster melee/r2 → pré-positionner un reach-dealer r3+/deep-strike T1 OU flagger la loss structurelle au recon (vécu seed 70000 : resté FULL tout le combat, jamais atteignable = root cause partagée + énième reach-fail, cf. série 19355/96001/97001) ; ShadowInTheWarp réduit MON Psychic = ne pas compter sur un finish Psychic facile [n=2, 19355/70000]`

> Les unités invoquées ont leur propre kit/traits (gameconfig : ids `*Smn*` / `*Npc*`).
> **Les recon dès qu'elles apparaissent** — leurs traits dictent la gestion. Stats
> indicatives (texte de l'ability du parent / gameconfig).

- **genesSmnDecoy « Decoy »** (laissé par `Ambush`) — HP0, traits `Steppable` + `Decoy`
  (cf. §1). → le détruire en **marchant dessus** (`act move --to <son hex>`) coupe la
  résurrection Ambush.
- **tyranNpc4Warrior / Tyranid Warrior** (`AlphaWarrior` de WingedPrime) — ~5820 PV,
  ranged ; ne bouge pas le tour d'invocation mais attaque + **réagit** (a tué 2 drones
  en réaction sans jouer de tour).
- **tyranSmnHormagaunt** (`SynapticLinchpin`) — base ~2183 PV (scale rank, observé 2992 seed 97002) ;
  spawn adjacent à une cible attaquée par une **normale Synapse non-tuante** (Winged Prime ou tout allié
  Synapse), **attaque immédiatement** la cible (max 4 simultanés).
- **astraNpc1Guardsman / Cadian Guardsman** (Yarrick `SendInTheNextWave` / MoW
  `ForwardSpotter`) — ~2910 PV, ranged ; **attaque immédiatement** à l'invocation.
- **tauSmnDroneShield « Shield Drone »** (Re'vas `EarlyWarningOverride`) — ~2910 PV ;
  attaque à l'invocation ; meat-shield (BigTarget réduit les hits ranged sur Re'vas).
- **genesSmnAberrant « Aberrant Hypermorph »** (Biophagus) — ~5456 PV / ~2837 dmg ;
  attaque immédiatement.
  `▸ Tac: rôle=chaff · menace=med (juste un summon de Hollan, Resilient/Summon mais SANS snowball) · counter=PAS une priorité sur les hero-engines (Hollan/Xybia/Abraxas) → le tuer quand pratique ; ⚠ HP gonflée bien au-dessus du base par le heal-revive Hollan TwistedScience (vécu seed 98001 : pumpé à 10469 vs 5456 base — recon-on-appearance la PV runtime, jamais le tooltip) ; Snotflogga BeastSlayer l'a one-shot 10469→dead [n=1, 98001]`
- **deathPoxwalker** (Corrodius `Poxwalkers`) — ~2183-2992 PV / ~2546 dmg ; spawn dans
  l'aura Contagion, attaque immédiatement ; tuer le summoner coupe le flux. ⚠ **trait `Summon`** (Verif
  gameconfig/i2 seed 70056) : i2 = « **Moves and attacks automatically at the beginning of its turn** » →
  **non-commandable** (absent de « À ACTIVER » ; `act=ability` renvoie `ok=True/mutated=False`) — auto-acté par
  l'engine, l'oracle ne doit PAS queue ses actions (même H41 pattern que tout summon Summon-trait : Ork Boys,
  Death Riders…). Ne pas gaspiller de micro à tenter de le piloter.
- **necroSmnSwarm « Scarab Swarm »** (Aleph-Null `ScarabHive`) — ~1455 PV baseline (scale),
  655 dmg, **move4**, Swarm/Flying ; spawn 2× à côté de la cible, **attaquent immédiatement**
  (Piercing 1ᵉʳ hit) ; `ReanimationProtocols` (35% revive à 25% PV sauf **Overkill**).
- **bloodSmnIntercessor « Jump Pack Intercessor »** (Mataneo `AggressiveOnslaught`, sur charge) —
  base 3638 PV/1310 dmg/1310 armure (scale match) ; Summon/Flying/RapidAssault/RedThirst ;
  attaque immédiatement ; **quitte le terrain au début de chaque tour de Mataneo** (~1 tour).
- **astraSmnDeathRider** (Dreir `LeadingTheCharge`) — ~3638-4432 PV/1892 dmg/873 armure ; move4, FragLance ;
  jusqu'à 4, adjacents à Dreir, attaquent immédiatement.
  `▸ Tac: rôle=chaff · menace=med (soft, non-Resilient) · counter=les AoE/focus down (Maugan Ra HarvesterOfSouls a cleavé les 3 en UN cast quand ils ont dive clusterisés) ; mieux : NIER le summon en amont (taunt Dreir avant son cast, ou tuer Dreir avant LeadingTheCharge) [n=1, 98000]`
- **admecSmnVanguard / Skitarii Vanguard** (Tan Gi'da `ControlEdict` sous Protector) — base 2546 PV /
  509 dmg / 1091 armure (scale), Mechanical, **Summon** (auto move+attaque en début de tour), 3× Toxic
  r2 (Pierce70) + mêlée, passif `RadSaturation` (Contamination sur son hex) ; cap 5 simultanés.
- **astraSmnGuardsman / Cadian Guardsman** (Yarrick `SendInTheNextWave`) — base 2910 PV / 1746 dmg /
  582 armure ; Las r2 (Pierce10) ; **Summon** (auto move+attack) + **BattleFatigue** (peut fuir si un
  ami adjacent meurt, pire si overkill) ; tire immédiatement au cast. (NB id `astraSmnGuardsman`, pas
  `astraNpc1Guardsman`.)
- **genesSmnNeophyte / Neophyte Hybrid** (Isaak `CultDemagogue`) — HP jusqu'à 2183 / dmg 1746 / armure
  437 (max niveau ; **observé live ~2992 seed 70007 = scaling émergent niveau × rareté, pas une contradiction**) ;
  ranged r2 (2× Projectile) ; **Summon** + **Ambush** (1ʳᵉ mort →
  decoy → resurrect full sur decoy ami) ; prend un tour immédiat au spawn.
  `▸ Tac: rôle=chaff (issu du board-flip Isaak) · menace=med (~2992 PV, ranged r2, CHACUN porte Ambush ; 3+ spawnés par CultDemagogue prennent un tour immédiat → out-number + chip-kill une ligne fragile) · counter=le VRAI fix = tuer Isaak AVANT le cast (cf. Tac Isaak) ; une fois spawnés, clear les Hybrids ET piétiner les decoys (Steppable) pour nier le resurrect Ambush ; ne pas les chiper un par un pendant que l'engine tourne (vécu seed 70007 : 3 Neophytes + 4 decoys = board-flip 3v12) [n=1, 70007]`
- **genesSmnGenestealer / Purestrain** (Patermine `MightFromBelow`) — base 3274 PV (scale), move3 mêlée
  Bio Pierce30 ; **Infiltrate** (pas d'Overwatch) + **Ambush** (resurrect full sur decoy ami) +
  Unstoppable ; attaque immédiate au spawn, pas de move ce tour.
- **thousSmnBlueHorror / Blue Horror** (Archimatos `Possession`, sur kill RANGED) — base 2619 PV /
  1310 dmg ; ranged r2 Flame+OnFire, move3 ; Summon/WeaverOfFate/Daemon ; `FlamesOfMutation` (met le
  hex En Feu à la mort sauf Overkill). (Kill MÊLÉE → Bloodletter base 2837 PV/1601 dmg à la place.)
- **thousSmnPinkHorror / Pink Horror** (Abraxas `MasterOfTheTutelaries`) — base 2619 PV / 655 dmg ;
  **Summon** (attaque immédiate au spawn, pas de move ce tour) ; spawné sur un hex libre adjacent à
  Abraxas. (Vécu seed 96000 : a fourni un kill décisif en réaction.)
- **thousSmnScreamer / Screamer of Tzeentch** (Abraxas `MasterOfTheTutelaries`, chaîne) — base 3274 PV /
  1310 dmg ; **Summon** (attaque immédiate au spawn, pas de move) ; spawné **1 par dégât Psychic infligé
  à un ennemi** (jusqu'à fin de tour) sur un hex libre proche d'un ennemi → un AoE/splash Psychic
  multi-cibles peut en cascader plusieurs (vécu seed 96000 : 2 Screamers = 2 instances de dégât Psychic
  → ils ont tué Farseer/Nauseous/Typhus en réaction).
- **necroNpc1Warrior / Necron Warrior** (Anuphet `ResurrectionOrb`) — base 4365 PV / 1455 dmg / 1091
  armure (scale ; **1 par round DÉMARRÉ** +1 par allié Living Metal défait — scaling sur l'INDEX de
  round interne, PAS le tour affiché) ; 2× Gauss r2 + LivingMetal/ReanimationProtocols ;
  non-commandable le tour du spawn mais menace via Overwatch (H17).
- **tyranNpc2RipperSwarm / Ripper Swarm** (Parasite `ItItches`/`BarbedOvipositor`) — ~4583-6282 PV
  (scale), move3, Swarm (5 membres) + **BattleFatigue** (peut fuir si un ami adjacent meurt) ; spawn
  dans un hex vacant, attaque immédiatement. NB : un Ripper « disparu » à la mort du Parasite =
  BattleFatigue probable, PAS un despawn-summoner (aucun lien de mort prouvé).
- **ultraSmnInceptor / Inceptor** (Bellator `DeathFromAbove`) — base 4001 PV / 728 dmg / 873 armure
  (peut scale plus haut) ; **1 par round démarré, plafonné par les hexes ADJACENTS LIBRES** autour de
  la cible (cluster serré ⇒ 1 seul spawn) ; atterrissent adjacents à la cible, attaquent immédiatement.
  Passif `ShockAssault` : quand **Bellator** attaque, tout Inceptor adjacent à LUI ré-attaque (+dmg).

---

## 3quater. Terrain / effets de tile (confirmés)

> Effets moteur portés par les hexes (gameconfig `aiUtilities.Default.TileEffects` + i2). Résout
> partiellement le TODO « sémantique terrain » du §6.

- **Razor Wire** (moteur : `Thorns_*` / Swamp) — un hex de Razor Wire : (1) une unité qui s'y TIENT
  subit **+50% Damage** (StaticStatModifierEffect `Thorns_DefenseReduction`) ; (2) une unité non-Flying
  non-Unstoppable qui ENTRE sur le hex **termine son mouvement** là (besoin d'un tour de plus pour le
  traverser) ; Flying/Unstoppable ne sont pas affectés. L'IA native pénalise s'y tenir (TileEffect
  utility −25, même bande que Fire/Ice/SpiderWeb). **Tactique** : attirer un ennemi dessus (+50% dmg
  subi) ; ne JAMAIS y parquer mes unités au sol. Vérifié (decompile + i2 Keywords/TileRazorwire).
- **LightCover** (ex. hex DryBush) — accordé en posant le pied sur un hex cover : **réduit les attaques
  ranged multi-hit subies de 2 hits (min 1)**. Rester sur cover blunt le ranged multi-hit ennemi.
  (Effet de tile, i2 Keywords/UnitEffect_LightCover ; possible lien avec l'auto-finish H08.)
- **Contamination** (tiles posés par RadBombardment / aura Nurgle) — `Contaminated_Unit` sur les hexes ;
  les unités dedans subissent Toxic/effets selon la source. Sémantique exacte = TODO §6.
- **EnvEndBombardment** (effet moteur de round-cap — pas d'ability/trait source ni texte i2) — quand la
  limite de rounds approche, des effets `EnvEndBombardment_Incoming` tickent en compte-à-rebours sur le
  board, puis un **bombardement AoE board-wide** fire et inflige des dégâts massifs à TOUTES les unités
  des DEUX équipes. ⚠ **CONFIRMÉ self-play consensus, seed 80000 (opus run)** : observé par les DEUX sides
  comme un nuke terminal qui a **wipe l'intégralité du board** (alive_by_team={}, `winner=None`) = **draw /
  no-winner par sudden-death**. Il **overkill même un Resilient** (A : « final hp=0 sur Arjac Resilient »).
  Il PUNIT les états d'attrition bas-PV (un blob chipé est wipe net) et **annule une position gagnante** non
  convertie (B menait 1v2 avec Arjac full-HP Resilient quand le bombardement a fire). DOCTRINE (n+1, recoupe
  §3bis Corrodius/Actus H51) : **le round-cap est une HORLOGE DURE** — quand on est ahead-on-quality mais
  qu'un anvil/engine adverse Resilient traîne, il faut FERMER le combat avant le cap (commencer à grind les
  anvils lents round 5-6, pousser une clôture cohésive) ; ne JAMAIS over-hold ni laisser le board en attrition
  basse-PV jusqu'au cap. [self-play consensus, seed 80000 (opus run)]. [n=3, 70061/80000-sp(×2)]
  `  ▸ Tac (3ᵉ confirmation self-play seed 80000, 2026-06-23 — STANDOFF PASSIF MUTUEL) : run distinct où les DEUX oracles ont joué quasi-passif (action logs : A=1 move, B=0 move sur tout le combat ; le reste = finish-en-place). Aucun camp n'a fermé → EnvEndBombardment a fire et wipe les deux blobs = no-winner (winner=None, alive_by_team={}). ⚠ **les DEUX players ont identifié l'over-passivité comme leur #1 mistake** : « deux turtles face-à-face = round-cap no-winner garanti, l'un DOIT forcer une clôture cohésive ». ⚠ **NUANCE de timing** : ici le bombardement a fire round ~5-6 (action logs = 4 endturns/side = round ~5), telegraphé ~1 round avant via `EnvEndBombardment_Incoming` — PAS le « ~round 10 » de H51. → le round-cap peut tomber PLUS TÔT que round 10 (ou le compteur de rounds ≠ tours-joueur) : ne pas se reposer sur « j'ai jusqu'au round 10 ». [self-play consensus, seed 80000, run #4]`
  `  ▸ Tac (5ᵉ confirmation self-play seed 80000, run #5 « antipassivity » — QUALITY-AHEAD non converti) : run DISTINCT du standoff passif #4 — A a JOUÉ activement et tué **3 héros ennemis** (StormOfWrath 2-for-1 Tanksmasha+Vitruvius T4, puis Aun'Shi) et fini **4v2 EN AVANCE**… et a quand même subi le no-winner board-wide (winner=None, alive_by_team={}). ⚠ **LEÇON FORTE : être quality-ahead ne SAUVE PAS du cap — un no-winner round-cap est un DOUBLE-LOSS, pas un draw favorable.** A a confirmé fire ~AmountOfTurnsStartedByCurrentPlayer=12 (≈ round 6, PAS round 10). Cause proximale de la non-conversion = A a CONSOLIDÉ au tour de conversion (sortir Atlacoya de la r2 Foehammer, reset actives) — doctrine « kill-or-hold » correcte EN ISOLATION mais l'**horloge OVERRIDE** : avec le cap telegraphé, FERMER un tour plus tôt, accepter un body-trade pour continuer à tuer. ⚠ friction COMMUNE re-signalée par les 2 sides : `EnvEndBombardment_Incoming` n'est PAS surfacé dans decisionView (EFFETS CRITIQUES/ACTIFS), seulement dans le dump brut de cascade → countdown facile à rater. [self-play consensus, seed 80000, run #5]
  `  ▸ Tac (6ᵉ confirmation self-play seed 80000, run roundcap 2026-06-23 — PERSPECTIVE NUMÉRIQUE INVERSE) : run DISTINCT — cette fois **team2 (B) était 5v2 DEVANT** (a tué Tigurius+Sho'syl+Exitor sur 2 engage-turns, rescue Tanksmasha via InspiredToGreatness) et a quand même subi le no-winner board-wide (winner=None, alive_by_team={}) faute de fermer les 2 derniers tanks (TG 12548 + Atlacoya 8032 = 20580 PV) avant le fire. ⚠ **re-confirme depuis l'autre côté** : que ce soit A 4v2 (#5) ou B 5v2 (ici) en avance, **l'avance numérique ne convertit PAS toute seule** — le cap est symétrique, il faut être en clôture cohésive par le ~6ᵉ tour. Cause proximale commune des 2 sides = tempo d'ouverture trop prudent face à un oracle turtle (« should have forced contact 1-2 turns earlier »). friction `EnvEndBombardment_Incoming` (RemainingTurns=1 trop tard) re-signalée par les 2. [self-play consensus, seed 80000, run roundcap]`
  `  ▸ RE DÉFINITIF (ghidra + mesure live standoff passif seed 80000, 2026-06-23) — RÉSOUT les estimations floues #4/#5 : le cap = la constante **`nrOfRounds`** de la config EnvEndBombardment, **= 8** (lue dans le BC : `EnvironmentAbilities.ConfigId=EnvEndBombardment` Type 1281 + `EnvEndBombardment.Constants.nrOfRounds:"8", healthPct:"20"` → nuke = 20% PV max board-wide). 3 abilities Loki : `EnvEndBombardment_WarningAbility` (pose l'effet Incoming), `_MarkerAbility`, `_DamageAbility` (le nuke). DSL : Warning fire quand **`TotalTurnsFinished == TurnsFromRounds(nrOfRounds)`**, Damage à `nrOfRounds + offset`. MESURE 1v1 : `TurnsFromRounds(8)=16` → Incoming arme à TotalTurnsFinished=16 (= **8 tours par camp**), RemainingTurns 2→1→fire ⇒ **nuke ~2 turns (1 round) après le warning**, soit round ~9-10. ⚠ Les « round ~5-6 » (#4) et « AmountOfTurnsStartedByCurrentPlayer=12 » (#5) étaient des **artefacts de compteur** : `GetAmountOfTurnsStartedByCurrentPlayer` (= `view.turn`) N'EST PAS monotone (oscille 3↔4 sur les tours passifs ; pas de `GetTotalTurnsFinished` simple) ; le vrai compteur DSL = `TotalTurnsFinished`. → **le cap réel = round 8 (≈ tes 8 tours/camp), PAS round 5-6**. TOOLING (H58 + horloge) : `rl_duel view` affiche désormais (1) **⏱ HORLOGE round-cap** STATIQUE dès le tour 1 (cap lu du BC, « ≈ tes 8 premiers tours, clôture par ton ~6ᵉ ») + (2) la ligne **⏱ [ROUND-CAP]** (effet Incoming, RemainingTurns) à ~2 tours de la fin = alarme finale. DOCTRINE figée : sois en CLÔTURE cohésive pour ton **~6ᵉ tour** ; l'avance numérique ne sauve PAS du wipe. [RE ghidra, mesure live seed 80000]`
  `  ▸ Tac (7ᵉ confirmation self-play seed 80003, 2026-06-23 — POSITION GAGNANTE MAXIMALE non convertie) : cas le plus FORT à ce jour — team1 (A) était **8v2** ET avait tué **les DEUX engines adverses** (Archimatos T7 overkill + Thaumachus T11) ; team2 (B) à 2 unités avec ses summon-engines morts. **MALGRÉ une position structurellement gagnante (8v2 + engines ennemis détruits), le no-winner board-wide a fire** avant le tour 13 de A (warning armé au tour 11, « dans 2 tour(s) ») → winner=None, alive_by_team={}. ⚠ **DÉMONSTRATION DÉFINITIVE : ni l'avance numérique massive (8v2) NI la destruction des engines adverses ne sauvent du cap** — seule la CLÔTURE (réduire l'ennemi à 0 unité) compte. Cause proximale commune aux 2 sides = **tempo d'ouverture trop prudent** sur le grand gap row-0↔row-9 (A : « should have engaged the forward baits harder T3/T5 to bank kills 1-2 turns earlier » ; B : « held one turn too long, failed to recognize it's a RACE »). [self-play consensus, seed 80003]`

---

## 4. Machines of War (MoW)

- **ultraDreadnought / Galatian (Ultramarines)** — `MacroPlasmaIncinerator` (1159,
  **killzone** : marque 1 hex + 2 derrière ; 3×~2183-2619 Plasma (Pierce65) à tous les ennemis
  **la 1ʳᵉ fois qu'un ennemi TERMINE son move dans la zone** ; cd1). **Ne touche PAS
  immédiatement** (pose des effets de tile, dmg différé) → juger à la cascade. ⚠️ **la danger
  overlay NE marque PAS cette killzone** — lire l'effet armé `MacroPlasmaIncinerator_AutoAttack`
  dans decisionView.effects et NE JAMAIS terminer un move dedans (vécu : ~6.5k-7.9k sur 2 carries).
  **Visée** : cibler (entité) une **unité avancée du camp du MoW** marque la zone **devant** elle →
  l'adversaire qui avance pour l'attaquer y termine son move → AoE. Vérifié : tue les Poxwalkers
  (2992) et un Kharn stunné à 1113.
  `DutyEternal` (1158, coût 3 munitions, consomme le MoW) — **déploie le Dreadnought comme UNITÉ
  « Galatian » (ultraSmnDreadnought)** : base **14550 PV / 1601 dmg / 2910 armure** (scale), **move0
  (tourelle stationnaire)**, 5× Power mêlée + **6× Projectile r2 ranged**, BigTarget (non déplaçable)
  / Overwatch / Vehicle-Mechanical (repair-only). Passif `AncientFury` (les attaques normales splashent :
  mêlée → ennemis adjacents à la cible ET à Galatian ; ranged → ennemis adjacents à la cible ET à exactement
  2 hex de Galatian). ⚠️ **STRUCTUREL** : comme move0, il ne « termine jamais un move » → la killzone
  MacroPlasma d'un MoW ennemi NE le déclenche JAMAIS, et DutyEternal est un summon (0 dmg offensif) →
  **une MoW seule ne peut PAS endommager un MoW Galatian stationnaire**. Le tuer = une carry RANGED qui
  reste HORS de sa r2 ; si cette carry meurt, le tank 14.5k+ devient injouable pour un reliquat mêlée.
- **blackForgefiend (Chaos)** — artillerie `HadesAutocannons` / `DaemonicOrdnance` (1148) **ranged,
  frappe n'importe où** (off-battlefield = **inciblable**). DaemonicOrdnance = Plasma 3×1310-1746
  (Pierce65), pose Fire sur hex cible+2 derrière. ⚠️ **CRIT RAMP** : **+20% Crit Chance des DEUX
  abilities par usage de DaemonicOrdnance** (cumulatif) → burst observé ~5681 en un tour (3 hits crit
  >2600 chacun, one-shot Morvenn). **Cap** : après 3+ crits dans SON tour, plus aucun crit le reste du
  combat. Le repli ne protège pas (frappe partout) → anticiper le ramp dès les 1ᵉʳˢ usages.
- **astraOrdnance « Thaddeus Noble » (Imperial)** — `BasiliskBarrage` (actif, fire SEULEMENT s'il n'a
  pas bougé) : 5 obus board-wide, chacun 2× Blast (Pierce15, HitsMultipleMembers). **SCATTER** : 3 obus
  au hasard sur la cible/hexes adjacents, 2 sur l'anneau extérieur → **softener de zone, PAS un sniper**
  (ne peut PAS fiablement finir une unité précise sur l'hex visé ; vécu : visé Hollan → Hollan 0). Chaque
  **round ÉCOULÉ** ramène +1 obus sur l'hex cible (les extérieurs migrent vers le centre) → plus fiable
  tard. Tous les touchés gagnent **Suppressed/Pinned** (−30% dmg, −1 move, stop Overwatch ; heal/repair
  retire). **Attaque normale** = 3× Blast **range 3** single-target, **SANS bouger** → nuke single-target
  fiable depuis sa tuile (distinct du barrage qui scatter ; vécu K! sur 5522/6086). → barrage pour le
  spread, attaque normale pour un kill single-target. **Move-gate confirmé live seed 97000** : sur un tour
  STATIONNAIRE, barrage/normale ont déalé 3237+2145=5382 = one-shot Helbrecht ; sur le tour où Thaddeus a
  BOUGÉ, seulement ~1273-1314 (la normale single-hit, ~1/4 de l'output) → **forcer un repositionnement
  ≈ halve son dmg**. **SuppressiveFire trait** : tout ennemi touché par le barrage devient **Suppressed**
  (zone-Suppress automatique). VALEUR RÉELLE = déni de zone + chip incident sur la grappe ADJACENTE à la
  cible (le scatter atterrit derrière), **PAS** du gros dégât (Pierce15 = faible vs armure) — vécu seed
  70003 : visé Patermine@(4,8), 5 obus ont scatter sur la grappe r9 derrière → chunke Vitruvius 9035→6570
  (l'engine de mark, −2465/27%), Kut −918, Njal −236 + Pinned 2 sur Vitruvius+Kut, mais aucun kill.
  `▸ Tac: rôle=carry · menace=critical vs roster mêlée lent (artillery board-wide ~5k stationnaire derrière un mur ; delete 1 unité/tour, inatteignable) · counter=un dealer ranged/Psychic à soi pour le tuer T1-T2, OU le ZONER/forcer à bouger chaque tour (move-gate : barrage void s'il a bougé → ~1/4 dmg) ; contre un roster pure-mêlée = engine de loss structurelle (wiki §5) — vécu seed 97000 : Arjac a fini par le solo-kill mais trop tard (3 fragiles déjà delete par sa barrage) [n=1]`
- **tauBroadside « Tson'ji » (Tau)** — `HeavyRailRifle` (1160, **RAILGUN** : cible un
  ennemi, **part au DÉBUT du prochain tour du MoW** ; 2×~3638-4365 Piercing **80%** ;
  **+75% vs Vehicles/BigTargets** ; cd1, 1 munition). ⚠️ **MÉCANIQUE-CLÉ : dégâts réduits
  de −30% PAR HEX que la cible a parcouru à SON dernier tour** (→ min 0). Donc sur une
  cible **mobile, le tir est gâché**. **RÈGLE : ne PAS l'armer sans LOCK.** Lock = un
  taunt/`BlockMovement` (cf. §1) posé le **MÊME tour**, par un taunter **déjà adjacent**
  à la cible (Jaeger `HolyDuel`, Grot de Snotflogga) → la cible bouge 0 hex → plein pot.
  À défaut de lock : soit **garder** le tir, soit viser un **ranged déjà à portée de mes
  unités** (l'IA l'attaque sur place → bouge peu = quasi-lock comportemental, moins
  fiable). vs MoW (au lieu de dégâts) : +1 cd sur l'ability secondaire, 75% sur la
  primaire. `TwinSmartMissileSystem` (1161, prêt d'emblée) : 3×~1310-1601 Blast à
  **chaque ennemi DÉJÀ Markerlighté** + pose un Markerlight 2 rounds sur la cible → le
  **1ᵉʳ** tir ne fait **que marquer** (0 dmg si personne n'est encore marqué ; Blast
  low-pierce ≪ vs armure de toute façon). Vérifié duel seed 33182.
- **orksRukkatrukk (Orks)** — `SquigLaunchas` (1200, Ranged, 3 hits Physical **Pierce1 = FULLY
  armor-piercing**, 1 munition, cd1) : **adjacency-gated** — ne cible un ennemi QUE s'il a **≥1 Ork
  allié OU ≥2 unités alliées adjacentes** ; summon une Large Squig (4729 PV) seulement si **≥2 Orks
  OU ≥4 unités alliées adjacentes** à la cible (≈ injouable pour un roster non-Ork). Roster Chaos =
  besoin de 2 de mes unités collées à la cible pour tirer du tout. ⚠️ output faible vs un TyrantGuard
  N'EST PAS l'armure (Pierce1 = full pierce) mais **GuardianOrganism (−33% + cap −1455/hit)** empilé à
  **BigTarget (−1 hit ranged → 3 hits → 2 landed)** → ~70% de réduction. **Pas un finisher vs un tank
  Guard-protégé.** `SquigMine` (1201, trap) : marque tout hex LIBRE (seule contrainte : hex inoccupé ;
  range 2 gouverne les 4 marques secondaires) — frappe quand un ennemi MARCHE sur un hex marqué ; marquer
  près des ennemis est tactique, PAS une contrainte moteur (un rejet sur hex libre = contrainte de
  range/valid-tile, pas « doit être enemy-relevant »).

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

## 5bis. SYNERGIES / COMBOS (couche transverse — ARÊTES, pas nœuds)

Une synergie est une **relation entre deux abilities/traits/units**, donc elle n'appartient
à aucune carte d'unité unique (où elle serait invisible depuis l'autre bout). On la capitalise
ICI, en premier rang, pour qu'elle **compose** et soit **pré-planifiée** au recon (pas
redécouverte par unité). Format d'une entrée :

`<pièce A> + <pièce B / trigger>` — **CLASSE** : effet → **PLAY actionnable**. [n=, seed]

CLASSES : **ENNEMI-À-ÉVITER** (ne pas déclencher leur combo) · **MIEN-À-ENCHAÎNER**
(séquencer mon combo, ordre imposé) · **ENGINE** (1 unité active l'équipe → la tuer
effondre le reste) · **ANTI** (anti-synergie : ne pas jouer ce combo).

> RÈGLE INSCRIPTION : une synergie ne va ici que si ses mécaniques composantes sont
> **confirmées** (Verif vs gameconfig/i2). Sinon → candidate dans `hypotheses.md`.

### Ennemies — à ne PAS déclencher (ou à couper en tuant la source)
- `Sho'syl MV71SniperDroneSquad (drone frappe au Damage stat de Sho'syl) + MA unité avancée dans la reach combinée Sho'syl+Njal` —
  **ENGINE (ENNEMI-À-ÉVITER, status=TRIGGERED-AGAINST-ME — ma seule perte seed 70058)** : un summoner back-row (Sho'syl) peut
  **focus-delete un de mes forwards sans bouger** via sa drone MV71, qui frappe avec **le Damage stat de Sho'syl, PAS le profil
  base 1528 du drone** (i2 confirmé, cf. §3bis Sho'syl) → un drone-hit one-shot-class (5924 KILL sur ma Jain Zar 7530 à (4,3),
  + Njal 1606 = focus-kill). ⚠ La reach/dmg du **drone-summon n'apparaît PAS dans le danger-zone overlay** (summoner blind spot,
  SKILL §4) → over-extension « invisible ». PLAY (à ÉVITER) : NE PAS avancer une unité (surtout un non-tank) dans la reach
  COMBINÉE d'un summoner-drone (Sho'syl) + d'un autre dealer back-row (Njal Psychic AoE) ; n'avancer que la durable Aesoth
  Resilient comme écran. SOURCE à couper = tuer Sho'syl → les drones deviennent chair inerte (~1996, dmg ~base 1528). Vécu seed
  70058 : j'ai VIOLÉ ça à 5v2 (non-décisif, déjà gagnant) → ma seule perte. (composante confirmée Verif : §3bis Sho'syl MV71 =
  drone frappe au Damage stat de Sho'syl.) [n=1, 70058 triggered-against-me]
- `Bellator DeathFromAbove (flood Inceptors croissant) + Archimatos Incursion/Possession (Bloodletter-farm + body-par-kill) + Abaddon FirstAmongTraitors (+364→+1313 au Chaos adjacent = Archimatos)` —
  **ENGINE (ENNEMI-À-ÉVITER, status=chained)** : DOUBLE summon-engine snowball — Bellator flood 1 Inceptor/round (5483 PV move4) +
  Archimatos farme des Bloodletters & spawn un body par kill, AMPLIFIÉ par l'aura adjacente d'Abaddon → board-flip 5v5 → 8v5 si
  laissé tourner. SOURCE = tuer Archimatos + Bellator EARLY (les deux SOFTS, no-Resilient) ; tuer Archimatos AVEC mon unité (il =
  VICTIME) = ZÉRO Possession body (cf. §2 Archimatos). PLAY : un roster all-melee + Bellator move4-Flying + Deathleaper deep-strike
  est CONTRAINT de diver → HOLD cohésif T1-T2 pour baiter le dive, puis tuer les DEUX engines dès qu'ils sont ATTEIGNABLES sur leur
  avance (vécu seed 70053 W : Snotflogga K! Archimatos comme victime + Aesoth/Calandis K! l'OW-engine Imospekh T4, source coupée
  avant compounding ; FirstAmongTraitors d'Abaddon devenu quasi-inert une fois Archimatos mort). (composantes confirmées Verif :
  §3bis Bellator DeathFromAbove flood croissant + §2 Archimatos Possession killer-identity + §2 Abaddon FirstAmongTraitors.) [n=1, 70053 chained]
- `Bellator DeathFromAbove (flood Inceptors croissant 5483 PV move4) + Corrodius Poxwalkers/Contagion (Resilient anvil + −armor aura screen) + Actus DefendTheDivineWork/GalvanicField (repair-cluster + free-attack par réparé)` —
  **ENGINE (ENNEMI-À-ÉVITER, status=chained)** : TRIPLE summon/sustain core — Bellator flood des Inceptors croissants (la SOURCE), Corrodius
  ajoute des Poxwalkers + une aura Contagion −armure (screen lent Resilient 12551), Actus répare le cluster + chaque réparé fait une free-attack
  → board COMPOUND si laissé tourner. SOURCE = tuer Bellator (le flood) + Actus (le repair) EARLY, les DEUX SOFTS (8533/9537 no-Resilient) ;
  Corrodius (anvil Resilient move2 LENT) = secondaire MAIS doit être COMMENCÉ tôt s'il y a un round cap (cf. §3bis Corrodius/H51). PLAY :
  un Bellator move4-Flying + un screen lent CONTRAINT de closer → HOLD cohésif + held-Overwatch turret (Certus) baite le dive → tuer les
  engines à leur sortie. ⚠ **VÉCU seed 70061 (status=chained PARTIEL → L timeout)** : Bellator tué T4 (flood stoppé, jamais de wave round-3)
  + les 2 Inceptors clearés T3, MAIS Actus seulement CHUNKÉ 9537→4468 (jamais fini) + Corrodius jamais engagé → board dominant 4v2-3 NON
  CONVERTI avant le round-10 cap = EnvEndBombardment mutual-wipe no-winner. LEÇON : casser la SOURCE flashy (Bellator) ne suffit PAS — FINIR
  le repair-engine (Actus) + grind l'anvil (Corrodius) AVANT le cap, sinon les 2 engines secondaires survivent au timeout. (composantes
  confirmées Verif : §3bis Bellator DeathFromAbove + §1/§5bis Actus GalvanicField free-attack + §2 Corrodius Poxwalkers/Contagion.) [n=1, 70061 chained]
- `Ragnar WarHowl (pump +1164/hit + Unstoppable + +36% crit) + ligne mêlée Character all-melee (Atlacoya/Tanksmasha/Kut…)` —
  **ENGINE (ENNEMI-À-ÉVITER, status=avoided)** : WarHowl est l'**amplificateur de burst d'un roster pur-mêlée** — un seul cast
  buffe toute la ligne Character mêlée jusqu'à la fin du tour. SOURCE = Ragnar → le tuer (ou le taunt/stun-lock, cf. H30 Azkor
  OverwhelmingWrath) AVANT son 1er cast laisse toute la ligne adverse un-buffée = gutte leur offense. PLAY : prioriser Ragnar
  comme la wincon (H02) ; un roster all-melee est CONTRAINT de diver → laisser mes réactions/Overwatch le tuer à sa sortie
  (le burst ne fire jamais). Vécu seed 70056 : Ragnar tué EN RÉACTION dans mon cluster Overwatch AVANT WarHowl → Atlacoya-enemy/
  Tanksmasha/Kut restés un-buffés tout le combat = W. ⚠ **CONFIRM n+1 (seed 70059 W)** : ligne all-melee = TG + Maladus
  bénéficiaires WarHowl → Ragnar chunké T2 (Typhus PlagueWind Psychic 3914) puis tué T3 (Typhus/Archimatos Psychic) AVANT tout
  cast → la ligne n'a JAMAIS été buffée. ATTEIGNABLE car le bulk anvil-heavy était CONTRAINT de fermer la distance (même
  structure que 70056) ; ici sans reaction-engine, le bris s'est fait par un FOCUS Psychic actif sur sa sortie au lieu de
  réactions auto. (composantes confirmées Verif : §3bis Ragnar WarHowl = self-cast, +1164/hit + Unstoppable + crit sur les
  Characters mêlée, ne finit pas le tour ; seed 70059 verdict confirmé.) ⚠ **CONFIRM n+1 + NOUVELLE VOIE (seed 70057 W) —
  DÉFANG PAR LES BÉNÉFICIAIRES** : WarHowl ne pump QUE les melee Characters SANS normale ranged → une 2ᵉ voie pour le
  neutraliser = tuer ses BÉNÉFICIAIRES (Dante+Helbrecht) AVANT l'engine. Vécu seed 70057 : Dante T3 + Helbrecht T4 tués →
  au moment où j'ai tué Ragnar T5, WarHowl ne pouvait plus que self-buff = engine défangé même non-pré-empté ; sa FJ
  7× Chain Pierce20 (~1946) routée sur mon Mataneo armuré = triviale. PLAY = soit kill pre-cast (n=2 ci-dessus), soit
  vider sa liste de bénéficiaires melee s'ils sont plus atteignables que lui. (composante confirmée Verif seed 70057 :
  Ragnar FJ 7× Chain Pierce20 weak-pen.) [n=3, 70056/70059/70057 avoided]
- `Kharn TheBetrayer (kill→auto move+4-hit/tour + BlessingsOfKhorne) + Tarvakh carry autonome (kill-snowball BlessingsOfKhorne/TrophyTaker)` —
  **ENGINE (ENNEMI-À-ÉVITER, status=avoided)** : DOUBLE carry snowball WorldEaters — Kharn est l'engine-source (1 SEUL kill →
  TheBetrayer s'arme = auto move+4× Eviscerate au START de chaque tour de Kharn SANS action + BlessingsOfKhorne cumulatif =
  carry incontrôlable) amplifié par Tarvakh qui snowball INDÉPENDAMMENT par kill (BlessingsOfKhorne +dmg/−Psychic, TrophyTaker
  +dmg vs ≤50% PV). SOURCE à casser = **nier à Kharn (et Tarvakh) leur PREMIER kill** ET les tuer sur leur dive AVANT que
  TheBetrayer s'arme. Les DEUX sont no-Resilient (Kharn 9035 / Tarvakh 9537 NON-pumpé) → killables à une réaction massée SI on
  les atteint. PLAY : un roster all-melee est CONTRAINT de diver → tenir un mur de réaction (Overwatch-turret + held-OW + aura
  −50%) qui les tue à leur sortie AVANT tout kill ; ne JAMAIS laisser une de mes unités tomber ≤50% près de Tarvakh (TrophyTaker).
  Vécu seed 70060 W : Kharn + Tarvakh tués TOUS LES DEUX dans mon mur de réaction T2 avec ZÉRO kill scoré → TheBetrayer jamais
  armé, leur engine n'a JAMAIS tourné. (composantes confirmées Verif : §2 Kharn TheBetrayer/BlessingsOfKhorne kill-gated + §2
  Tarvakh BlessingsOfKhorne/TrophyTaker snowball, NON-pumpé chunk-killable.) [n=1, 70060 avoided]
- `Abaddon FirstAmongTraitors (+364→+1313 dmg aux alliés Chaos adjacents, scale par attaque) + alliés CHAOS sur SON équipe` —
  **ENGINE (ENNEMI-À-ÉVITER, status=avoided) — DEMOTE si le bénéficiaire Chaos manque** : l'aura ne vaut que par le NOMBRE
  d'alliés Chaos adjacents. SOURCE = compter les alliés Chaos au recon : si UN SEUL (ou zéro), l'aura est NEAR-INERTE → demoter
  Abaddon de wincon à anvil Resilient soft, le laisser pour la FIN. PLAY : vécu seed 70059 W — seul allié Chaos = Maladus
  (Ragnar=Imperial, TG=Xenos, Roswitha=Imperial) → aura démotée au recon, Abaddon traité en DERNIER (4v1) ; une fois Maladus
  mort l'aura est FULLY inerte → Abaddon overkillé en Psychic stacké sans urgence. Même classe « engine-inerte-sans-bénéficiaire »
  que le revive Chaos inerte (98004/70060) et l'amplificateur sans cible (Darkstrider markerlight 70056). (composantes confirmées
  Verif : §2 Abaddon FirstAmongTraitors aura Chaos-gated + faction des alliés.) [n=1, 70059 avoided]
- `overkill raté → FinalJustice` (Helbrecht/Ragnar/Gulgortz/Trajann/Azrael…) — **ENNEMI-À-ÉVITER** :
  si tu ne tues pas en **OVERKILL**, la cible riposte une volée (≈ son attaque normale) →
  **overkill obligatoire** sur ces porteurs, sinon ne pas engager. ⚠ **VARIANTE SAFETY si l'overkill est impossible
  (vécu seed 70009 triggered-against-me)** : Gulgortz tué NON-overkill (Tanksmasha 4520 sur 3933) → FJ + LightImUp ont
  fire (~3537), MAIS routés sur le seul adjacent = un TANK high-HP (Tanksmasha, survécu) = riposte absorbée SANS perte.
  Si tu ne peux pas overkiller un FJ-carrier, finir avec UNIQUEMENT un corps high-HP adjacent (jamais un fragile) ; un
  chunk de plus pour amener <2× PV restants reste préférable (déni FJ complet). ✅ **VOLET POSITIF (vécu seed 70008)** :
  quand c'est MON FJ-carrier qui meurt adjacent à un ennemi bas-PV, le trade joue EN MA FAVEUR — Godswyl a tué mon Gulgortz
  NON-overkill → FJ a fire une normale et a TUÉ le Godswyl 458 PV adjacent = trade 1-pour-1 GRATUIT → positionner un
  FJ-carrier près d'une cible chunkée avant qu'il meure. ⚠ **CONFIRM n+1 — 3 VOIES VALIDÉES LE MÊME MATCH (seed 70057 W,
  4 FJ-carriers gérés)** : (a) **Overkill** — Helbrecht 9539 overkillé multi-source (Mataneo 7984 + drone 1555,
  `Attack_WasOverkill=1`) → FJ NON déclenchée (i2 « unless Overkilled ») ; (b) **kill SANS eligible adjacent** — Dante tué
  à (3,4) sans cible à portée de sa normale → FJ a fire (`IsActingBeforeDeath=0`) mais ZÉRO dmg (no-op) = free-kill path
  distinct de l'Overkill ; (c) **route faible-pen sur un body armuré** — Ragnar tué non-overkill → FJ 7× Chain **Pierce20**
  ~1946 sur mon Mataneo armuré Mechanical = trivial. DOCTRINE = pour chaque FJ-carrier choisir UNE des 3 voies : overkiller
  (riposte forte type Dante Pierce80/Gulgortz double-volée), tuer hors-portée-de-sa-normale, ou router la riposte faible-pen
  sur un tank/body armuré. (toutes composantes confirmées Verif seed 70057.) [n≥6, 93000/97002/70009/70008/70057/…]
- `repair Actus → GalvanicField` — **ENNEMI-À-ÉVITER / ENGINE** : chaque repair d'Actus
  déclenche une **free-attack** de l'unité réparée (≤4365) → **tuer Actus** coupe repair + free-attacks
  (et il re-heal self+adjacents 4365). ⚠ NOTE : DefendTheDivineWork répare ANY allié adjacent (PAS Mechanical-gated)
  → l'engine est LIVE dès qu'Actus a des alliés adjacents, même s'il est le SEUL Mechanical de son équipe (≠ aura
  d'amplification inerte-sans-bénéficiaire). ⚠ **n+1 (vécu seed 70061, status=MISSED → CONTRIBUTING ROOT CAUSE)** :
  après avoir tué le summoner Bellator j'ai seulement CHUNKÉ Actus 9537→4468 et HOLD au lieu de le FINIR depuis le
  shallow → il a survécu jusqu'au round-10 timeout (EnvEndBombardment) = engine intact à la fin. « Kill ce tour ou ne
  pas committer » est LITTÉRAL pour un repair-engine ; une fois la SOURCE flashy (summoner) morte, le repair-engine
  DEVIENT le focus #1 — ne pas le chiper-et-tenir. [n=3, 97002/…/70061 missed]
- `TwistedScience (Hollan) → pump carry/summon` — **ENNEMI-À-ÉVITER / ENGINE** : tout allié healé par Hollan
  (autre que lui-même), **summons INCLUS**, gagne +2183 maxHP permanent (scale rareté) +364 dmg si GSC, 1×/unité
  jusqu'à défaite → transforme un carry/summon en mur (Tarvakh 9.5k→12.5k seed 97001 ; Xybia 5522→8514 + l'Aberrant
  ressuscité 5456→10469 seed 98001 — **un Hollan qui heal un summon sur revive le pompe aussi**). Aucune contrainte
  d'adjacence sur le PASSIF. → **focaliser le PUMPER (Hollan) pas l'output pumpé** ; le tuer TÔT et PERMANENT (avant
  qu'il soigne quiconque) ; une fois Hollan mort, rien n'est re-pumpé et les corps gonflés meurent normalement (vécu
  seed 98001 W). [n=2, 97001/98001]
- `Abraxas MasterOfTheTutelaries (Pink Horror + Screamer-cascade-on-Psychic) + chip non-létal / AI ranged focus` —
  **ENNEMI-À-ÉVITER / ENGINE** : un summon-engine Abraxas **chippé non-létalement** (aucun seuil de PV → tout Abraxas
  survivant cast) déclenche MasterOfTheTutelaries → +1 Pink Horror (3589) + 1 Screamer (4487) par event Psychic-Damage
  ennemi = **board-flip +3 bodies en un tour ennemi**, transformant un 5v5 en 3v10 pendant que le cluster ranged
  focus-kill les fragiles exposés. ⚠ **RÈGLE KILL-OU-HOLD (vécu seed 70052 triggered-against-me)** : un chip à une
  seule source qui ne peut pas one-shot un 7026 (Snappa r3 max < HP → 7026→3183) est **strictement pire que le hold** —
  soit un **kill GARANTI ce tour** (multi-source depuis tuiles shallow, marge > HP), soit **HOLD total** pour dénier le
  trigger. JAMAIS un poke non-létal sur un summon-engine. (composantes confirmées Verif : §2 Abraxas MasterOfTheTutelaries
  1 Pink Horror sur cast + 1 Screamer par event Psychic-Damage, no HP threshold.) ✅ **CONTRE-EXEMPLE POSITIF (vécu seed
  70060 W, status=avoided)** : règle kill-not-chip RESPECTÉE → un kill GARANTI multi-source en UN tour (Sarquael Supercharge
  6366 + 2 normales = 7026→0, min-total vérifié > HP AVANT de committer) a erasé Abraxas AVANT son cast = ZÉRO board-flip,
  ZÉRO summon. Confirme l'INVERSE de 70052 : kill garanti ce tour OU hold total — jamais le poke. [n=2, 70052 triggered-against-me / 70060 avoided]
- `Re'vas EarlyWarningOverride (2 Shield Drones + Overwatch armé) + BigTarget screen ranged` — **ENNEMI-À-ÉVITER / ANTI** :
  Re'vas caste EWO T1 → spawne un **écran forward de 2 Shield Drones** (3989, BigTarget −1 hit ranged, SaviorProtocols) +
  **arme un Overwatch turret** (+1892, re-arme −1 hit sur chaque kill OW) → interdit une approche melee ET **ÉCRANE le soft
  backline (Eldryon/Abraxas) de mon reach**. PLAY : ne JAMAIS pather dans son arc r2 (no OW trigger) ; mais le screen rend
  les engines back-row inatteignables pour un roster melee → si je n'ai pas de reach tool (r3+/deep-strike/flyer) pour
  contourner le screen et atteindre les engines softs, **flagger la loss structurelle de reach au recon** (vécu seed 70052 :
  screen tenu, engines softs jamais atteints = composante de la loss). (composantes confirmées Verif : §3bis Re'vas EWO =
  2 Shield Drones tauSmnDroneShield + Overwatch armé/re-arm.) [n=1, 70052 avoided]
- `buff-engine → ranged dealers` (Calgar `RitesOfBattle` +946 / Trajann `LegendaryCommander` /
  **Helbrecht `CrusadeOfWrath` + Aesoth `StandVigil` + Vitruvius `MasterAnnihilator` = TRIPLE
  amplificateur empilé**) — **ENNEMI-À-ÉVITER / ENGINE** : le(s) buff(s) feed les dealers (team +364
  dmg/+pierce + armure + +1 hit vs marqué = ~17k focus/tour, kite + focus-kill 1/tour) → **tuer les
  engines de buff** AVANT d'échanger avec les dealers ; casser Helbrecht+Aesoth+Vitruvius effondre
  l'amplification (vécu seed 98004 : les 3 cassés T2-T3 en réactions → focus ranged neutralisé). ⚠ **CONFIRM n+1 (seed 70057 W)** :
  buff-stack mixte Helbrecht `CrusadeOfWrath` (melee +364/+24% pierce, live source) + Thaddeus `SpotterReworked` (+364/+728
  ranged aux alliés ≤2 hex, source gameconfig) feeding la ligne de focus → Helbrecht (le buff-engine melee) tué T4 par OVERKILL
  multi-source AVANT d'amplifier une swing mêlée ; Thaddeus tué EN DERNIER (no FJ/no Resilient = clean) une fois ses alliés
  ranged morts → son Spotter n'avait plus personne à feeder = inert. PLAY = casser le buff-engine LIVE en premier (Helbrecht,
  soft 9539, overkill pour nier FJ), garder le buff sans-bénéficiaire (Thaddeus Spotter) pour la fin. (composante confirmée
  Verif seed 70057 : Helbrecht overkill defeats FinalJustice.) [n≥4, 96002/97000/98004/70057]
- `Vitruvius MasterAnnihilator (mark +1 hit team vs marqué) + RadBombardment (ligne AoE croissante) + team focus` —
  **ENNEMI-À-ÉVITER / ENGINE** : la mark donne à toute la team +1 hit vs la cible marquée (sauf Psychic) ET RadBombardment
  est une ligne AoE Toxic qui GRANDIT +1 hex/round écoulé +1/heal Mechanic (et friendly-fire sa propre ligne) → un dealer
  ranged-AoE qui atteint le mid-board vite ET amplifie le focus de toute l'équipe. ⚠ **RÈGLE FINISH-PAS-CHIP (vécu seed
  70003 triggered-against-me)** : Vitruvius est SOFT (~9035, pas Resilient) mais un CHIP non-létal le laisse fully amplifier
  — chippé 9035→6570 par le barrage T1, il a fire RadBombardment 3810 et tué mon carry au tour suivant. → contre ce
  buff/repair-engine, prévoir un FINISH au range (pas un poke) AVANT qu'il close ; le tuer effondre la mark + la ligne.
  (composantes confirmées Verif : §3bis Vitruvius RadBombardment ligne croissante 3274-4001.) [n=1, 70003 triggered-against-me]
- `Ambush + decoy ami survivant → resurrect full` (Kelermorph/Judh, Magus, Biophagus…) — **ENNEMI-À-ÉVITER** :
  **1ʳᵉ mort SEULEMENT** → respawn plein PV au début du tour suivant si un decoy ami survit →
  **clear le decoy** OU forcer une **2ᵉ mort** (first-defeat-only, jamais 2×, indépendant de l'overkill).
  ⚠ NE PAS traiter le 1er kill d'une unité Ambush comme un retrait : budgétiser la 2ᵉ mort d'avance. Vécu seed
  98001 : Xybia ET Hollan ont eu chacun un revive gratuit (decoys inaccessibles) → gagné quand même via 2ᵉ morts
  (Xybia 2× par Tjark, Hollan 2× par Snotflogga), mais clear-decoys aurait économisé 2 tours de cleanup — pré-planifier
  une unité pour piétiner les decoys (Steppable) quand une unité Ambush meurt près de ma ligne. ⚠ **n+1 (vécu seed 70061,
  triggered-against-me)** : Judh (genesKelermorph) tuée une fois T3 (Certus OW) mais decoys survivants → revived FULL 6023 le
  tour suivant ; sur la 2ᵉ tentative j'ai single-sourcé son re-kill (Makhotep) et seulement FLOORED 776 (= 50% sur le TOUR
  ENNEMI, scope i2 confirmé) → sa contre+le tour ennemi ont tué Makhotep. LEÇON re-confirmée : un 1er kill d'unité Ambush
  n'est PAS un retrait — budgétiser la 2ᵉ mort (PERMANENTE) d'avance ; pour une Judh floored, stacker un 2ᵉ attaquant >
  HP-floored le MÊME tour, OU clear le decoy avant, OU ignorer et presser les engines. [n≥4, …/98001/70061]
- `Aleph-Null (necroSpyder repair-hub) + Tan Gi'da (admecMarshall summon-engine) → noyau Mechanical` —
  **ENNEMI-À-ÉVITER / ENGINE** : Aleph-Null répare/regen la grappe Mechanical (FabricatorClawArray 2910 +
  Mechanic + LivingMetal/NetherRealmCasket) pendant que Tan Gi'da la blinde (+582 Protector) et summon des
  Skitarii Vanguards (cap5) après chaque attaque → noyau **auto-réparant, blindé, croissant** qui out-attritionne
  un roster low-output (snowball 5 héros → 12 unités en 2 tours, seed 98003). → **tuer les SOURCES** (Tan Gi'da
  + Aleph-Null) TÔT au **Psychic NoBlocking** (bypasse le +582, cf. §1), ne PAS chiper l'output Vanguard/Snotflogga ;
  si les engines sont structurellement INATTEIGNABLES (row 8-9, reach=zéro), flagger la loss au recon. [n=1, 98003 missed]
- `summon-engine miroir : Tan Gi'da (ControlEdict) + Yarrick(s) (SendInTheNextWave) + Aleph-Null (ScarabHive)` —
  **ENNEMI-À-ÉVITER / ENGINE** : trois moteurs de summon INDÉPENDANTS (Vanguards 1/attaque cap5 sous Protector +
  2 Guardsmen +1/allié-défait cap5 — clause snowball qui récompense MES pertes — + 2 Scarabs/use) peuvent flooder
  5→12+ unités en 2 tours ; **deux Yarricks DOUBLENT** le throughput SendInTheNextWave. Un roster low-output qui ne
  peut pas burst-down Yarrick avant son actif déclenche le snowball via ses propres morts. → couper les sources, ne
  pas clear le chaff un par un. [n=1, 98003]
- `Anuphet ResurrectionOrb (necroOverlord summoner) + Aleph-Null FabricatorClaw/Mechanic repair (necroSpyder)` —
  **ENNEMI-À-ÉVITER / ENGINE** : noyau Necron sustain-snowball — Anuphet summon un Necron Warrior **4365-5983 PV
  chaque round** (+1 par LivingMetal mort, clause qui récompense MES kills), Aleph-Null les garde top/réparés
  (2910/repair + LivingMetal regen) → le board flood de corps tanky réparés inout-attritionnables pour un roster
  non-burst. → **briser la SOURCE** : tuer Aleph-Null (amplificateur de repair) + Anuphet (summoner) TÔT plutôt
  qu'out-DPS l'output réparé. Les DEUX sont SOFTS (8536/9037, no-Resilient) et move-in → killables en réaction
  s'ils dive (vécu seed 98002 W : Aleph-Null tué T2, Anuphet chunké puis fini en réaction → le snowball n'a JAMAIS
  tourné). [n=1, 98002 avoided]
- `Patermine CosmicHorror (kill→decoy) + MightFromBelow (summon sur decoys)` — **ENNEMI-À-ÉVITER / ENGINE** :
  moteur de summon self-feeding ENTIÈREMENT KILL-GATED — chaque kill du Patermine pose un decoy (passif CosmicHorror)
  puis MightFromBelow (5× Psychic Pierce100 NoBlocking, ignore armure) summon un **Purestrain Genestealer** (4487 PV,
  Ambush+Infiltrate) sur chaque decoy adjacent → un kill via MightFromBelow chaîne IMMÉDIATEMENT en un Genestealer sur
  l'hex du mort. Gaté UNIQUEMENT sur le Patermine OBTENANT des kills (pas de kill = pas de decoy = pas de summon). →
  **DÉNI POSITIONNEL** : ne présenter AUCUN fragile killable dans son move4 reach (le contre n'est PAS réactif). Le
  Patermine porte Terrifying (10038) → bypass = RANGED, le tuer au range AVANT son 1er kill ; une fois qu'il a tué une
  fois, le snowball est live et un set de survivants mêlée ne le rattrape pas. Vécu seed 70003 : a tué Nicodemus T1 →
  Genestealer summon = snowball live → 3v6. (composantes confirmées Verif : §3bis Patermine CosmicHorror/MightFromBelow.)
  [n=1, 70003 triggered-against-me]
- `Isaak CultDemagogue (board-flip r2) + Neophyte/Isaak Ambush` — **ENNEMI-À-ÉVITER / ENGINE (board-flip instantané)** :
  UN cast de CultDemagogue au tour ennemi éparpille jusqu'à 8 decoys ≤2 hex de la cible, convertit la MOITIÉ en Neophyte
  Hybrids (~2992 PV, ranged r2, CHACUN Ambush) qui prennent un tour IMMÉDIAT + tirent sur ma ligne → board-flip 4v5 → 3v12
  en une activation. Les decoys restants (Steppable HP0) alimentent aussi DecoysAndMisdirection (resurrect/move-on-decoy
  +582 dmg pour les unités GSC). → **tuer Isaak AVANT le cast** (T2 au plus tard) ; s'il est INATTEIGNABLE (row-7/9, mon
  roster move2/r3 + r2 sans reach r3+/deep-strike) = reach-fail STRUCTUREL → flagger la loss et jouer un turret défensif
  (fragiles row 0-1), PAS avancer des fragiles dans le reach Custodes/GSC. ⚠ **status=triggered-against-me** (vécu seed
  70007 L) : Isaak row-7 jamais menacé (j'ai dépensé mon unique vrai tour sur le LESSER engine Yarrick + heal) → CultDemagogue
  a fire = la loss directe. ⚠ leçon « tuer l'engine qui ENABLE l'écran, pas le plus facile » (cf. 91012). (composantes confirmées
  Verif : §3bis Isaak CultDemagogue ≤8 decoys + Neophyte Hybrids Ambush auto-act + §1 Ambush.) [n=2, 91012/70007 triggered-against-me]
- `Isaak CultDemagogue (board-flip r2) + Shadowsun (move4 Flying + ExemplarOfTheKauyon teleport) + Typhus 12k anvil EN ÉCRAN` —
  **ENNEMI-À-ÉVITER / ENGINE (board-flip + Flying-teleport-reach derrière un anvil)** : Isaak flippe le board (3 Neophytes 2992 +
  decoys prenant un tour IMMÉDIAT, 5v5→5v14) PENDANT que Shadowsun Flying-teleporte au-delà de TOUT écran (reach pleine-planche,
  aucun cap de move) pour delete mon outil fragile de reach, le tout derrière un anvil Typhus 12k (Resilient+TerminatorArmour) qui
  écrane les soft engines. → **HOLD les fragiles row 0-1, écraner avec des corps de summon UNIQUEMENT, NE JAMAIS avancer un fragile
  reach-tool** ; forcer l'IA à venir sur un cluster cohésif. ⚠ **status=triggered-against-me** (vécu seed 70050 L) : les deux engines
  étaient INATTEIGNABLES (Isaak/Isabella row 8-9 ; mon Neurothrope move2+r3 = reach ~5 depuis row 1, PAS row 9), pourtant j'ai avancé
  Neurothrope (1,5) sur un verdict move-guard « propre » → Shadowsun teleport-kill (8533→0) + Isaak board-flip + Typhus PlagueWind +
  Judh HeroicFusillade = 34887 dmg / 4 units en UN tour ennemi → 4v14, sustain-engine intact, AUCUNE reach restante = loss structurelle.
  ⚠ leçon : vs un profil board-flip + Flying-teleport, un verdict move-guard 2-ply « propre » est un faux feu vert (cf. H40) — tenir
  les fragiles row 0-1 par DÉFAUT. (composantes confirmées Verif : §3bis Isaak CultDemagogue board-flip + §3bis Shadowsun
  ExemplarOfTheKauyon teleport reach-pleine-planche + §3bis Typhus anvil.) [n=1, 70050 triggered-against-me]
- `Isabella RitesOfRestoration (revive/heal engine) + Isaak Ambush + Judh Ambush + Neophyte Ambush` —
  **ENNEMI-À-ÉVITER / ENGINE (sustain/revive EMPILÉ sur multi-Ambush)** : un engine de sustain+revive (Isabella, soft no-Resilient/no-FJ
  → tout K! la tue proprement) superposé à PLUSIEURS porteurs d'Ambush (Isaak/Judh + chaque Neophyte) → mes kills sont soit ANNULÉS
  (revive Isabella) soit TEMPORAIRES (decoy Ambush). → **wincon = tuer Isabella tôt ET Isaak avant cast** ; une fois les deux online +
  le board flippé, mes kills sont réversibles et je n'ai plus de reach. ⚠ **status=missed** (vécu seed 70050 L) : jamais atteint la
  fenêtre — Isabella/Isaak row 8-9 inatteignables à mon roster melee/r2 + 1 move2/r3 → flagger la loss au recon quand reach=zéro vers
  ces engines. (composantes confirmées Verif : §3bis Isabella RitesOfRestoration revive 1819 fixe + §1 Ambush first-defeat-only.)
  [n=1, 70050 missed]
- `Trajann LegendaryCommander (+800 vs adjacent-à-un-ability-user) + Aesoth StandVigil/VexillaMagnifica stun + Trajann MomentShackle self-heal + DOUBLE summon-engine (Isaak+Yarrick) en ÉCRAN` —
  **ENNEMI-À-ÉVITER / ENGINE (anvil Custodes screené par summons)** : triple-stack Custodes — Trajann amplifie le focus de
  l'équipe (+800) ET se heal-to-full REPEATABLE sur cd (mur inkillable, cf. l'entrée Trajann ci-dessous) pendant qu'Aesoth
  stun (VexillaMagnifica) et buffe (StandVigil) → un mur self-sustaining qui out-grind un roster chip une fois les ÉCRANS
  (Isaak board-flip + Yarrick attrition) construits. → NE PAS chiper Trajann (chip annulé) ; casser les ÉCRANS (les
  summon-engines) en premier — c'est la seule manière de toucher l'anvil. ⚠ **status=avoided mais MOOT** (vécu seed 70007 L) :
  correctement NE PAS chipé Trajann, MAIS échoué à casser l'écran (Isaak engine) → l'évitement n'a servi à rien, le board a
  flippé avant toute fenêtre de kill sur l'anvil. ✅ **CONTRE-EXEMPLE — mur CASSÉ (vécu seed 70005, sans summon-engine en écran)** :
  ce matchup le wall Trajann+StandVigil n'avait PAS de double summon-engine devant lui → la fenêtre était atteignable : Aesoth (la
  SOURCE StandVigil) tué d'abord (par l'Explosion friendly-fire de mon Aleph-Null mourant, 759→0) = DEPUMP l'équipe, PUIS Trajann
  tué en un tour via la séquence anti-block Typhus Psychic + Ulf GreatFrostAxe (cf. Miennes ci-dessous) pendant MomentShackle en cd.
  LEÇON : casser Aesoth retire StandVigil (depump) ; le wall n'est inkillable que TANT QUE ses écrans (summon-engines) tiennent ET
  que MomentShackle est up — sans écran summon et avec un burst Psychic+actif réservé, il TOMBE. (composantes confirmées Verif :
  §3bis Trajann MomentShackle/LegendaryCommander + §3bis Aesoth VexillaMagnifica/StandVigil ; le board-flip Isaak ci-dessus.)
  [n=2, 70007 avoided / 70005 broken]
- `Tigurius StormOfWrath (Psychic NoBlocking AoE 6-cibles) + WeaverOfFate (Thaumachus/Neurothrope) + Neuroparasite (Neurothrope)` —
  **ENNEMI-À-ÉVITER / ENGINE (cascade Psychic)** : UN cast de Tigurius (Psychic Pierce100 NoBlocking, cible + 5 adjacents =
  6 unités) touche 3+ de mes units → **arme `WeaverOfFate`** (Thaumachus/Neurothrope dealent MAX ce tour) ET escalade
  **`Neuroparasite`** (+1237/niveau, cap ~15) sur chaque cible touchée → cascade qui snowballe inkillable. Le Psychic
  NoBlocking ignore TOUTE ma mitigation (armure, BigTarget, GuardianOrganism). → **casser la SOURCE** : tuer **Tigurius
  EN PREMIER** (l'AoE qui touche 3+ ET la block-aura PsychicFortress qui mange mes finishers) PUIS **Neurothrope** (le
  snowball-engine) AVANT qu'ils tournent ; ne PAS clusterer 3+ de mes units exposées à StormOfWrath ; mon dmg étant
  idéalement NON-Psychic ne feed PAS leur WeaverOfFate/Neuroparasite (anti-synergie défensive). ⚠ **status=MISSED**
  (vécu seed 70000 L) : j'ai split mon focus Thaumachus/Tigurius au lieu de FULL-focus Tigurius → PsychicFortress a bloqué
  mes finishers, Tigurius (1694) a survécu et re-fire → la cascade a tourné ; Neurothrope backline jamais atteint. ⚠⚠ si
  le roster est melee/r2 sans reach au Neurothrope backline (move2/Flying/r3) = HARD-COUNTER structurel, flagger la loss au
  recon. (composantes confirmées Verif : §3bis Tigurius StormOfWrath Psychic Pierce100 NoBlocking 6-cibles + PsychicFortress
  block-aura + §3bis Neurothrope Neuroparasite.) [n=1, 70000 missed]
- `Psyker splash (attaque RANGED normale → +dmg à un ennemi ADJACENT à la cible) → seuil 3+ ennemis-Psychic → WeaverOfFate MAX (Ahriman + Thaumachus)` —
  **ENNEMI-À-ÉVITER / ENGINE (cascade Psychic SANS AoE actif)** : distinct du feed-par-AoE (StormOfWrath ci-dessus). Une **simple
  attaque ranged NORMALE** d'un Psyker (Ahriman/Thaumachus) splash %dmg sur un ennemi adjacent à la cible → contre un cluster
  ennemi, UNE normale touche 2-3 ennemis distincts en Psychic, **arme `WeaverOfFate` sur les DEUX Psykers** (RemainingTurns=1) →
  ils dealent MAX ce tour → **one-shot** (vécu : Jain Zar 6568 one-shotée le tour où le splash a touché 2 Guardsmen adjacents → 3
  ennemis-Psychic → max). → **NE PAS clusterer 3+ de mes units dans la portée Psychic** : garder les unités SPREAD nie le seuil et
  empêche les jumeaux WeaverOfFate de monter à MAX (les deux observateurs concordent : le caster déclenche cheaply via splash, le
  défenseur dénie via spacing). (recoupé gameconfig : `WeaverOfFate` « 3+ enemy units have taken Psychic Damage → maximum Damage » +
  trait `Psyker` splash ranged normale.) [self-play consensus, seed 80003]
  `▸ MIEN-À-EXÉCUTER (côté OFFENSIF — le splash-feed est un ENGINE de victoire, pas qu'un piège défensif, [self-play consensus, seed 80003 — team2 W]) :`
  avec 2-3 Psykers, **spam la normale RANGED** (pas seulement les abilities) pour feed le seuil — vécu seed 80003 (batchfix) : team2 a
  cast **16× normale Psyker (ab 69)** pour atteindre/maintenir 3+ ennemis-Psychic/tour → `WeaverOfFate` MAX armé → kills garantis (one-shot
  Jain Zar, focus du Deathleaper isolé), **élimination en 4 tours** (clôture AVANT le round-cap). Le Psyker NoBlocking bypasse armure
  (MkXGravis = ZÉRO protection : Bellator 8533→5 en un tour) ET `Terrifying`/Camouflage (réductions MÊLÉE only). ⚠ Garder les casters à
  **range 2** : une normale adjacente (range 1) auto-sélectionne l'arme MÊLÉE faible (Flame ~417), pas le Psychic ranged (gaspille le tour).
  Coupler avec `Possession`-class (Archimatos) : un RANGED-kill spawn un corps gratuit dans le hex de la victime = board-presence pour la race.
- `Njal Stormcaller (Psychic NoBlocking AoE Ice) + mes carries FLYING stationnaires` — **ENNEMI-À-ÉVITER** :
  Stormcaller = Psychic Pierce100 NoBlocking (ignore armure ET TerminatorArmour) AoE sur hex-cible + tous adjacents,
  **stun les unités FLYING touchées** ET +237 dmg/hex d'Ice adjacent (`LordOfTempests` snowball). → NE PAS laisser un
  carry Flying (mon Dante) stationnaire dans la portée Ice de Njal (risque stun + dmg armor-ignore sur toute la grappe).
  Couper la source = tuer Njal (move2 lent → kitable/out-rangeable par des r3, ou focus multi-attaquant qui bat son
  TerminatorArmour, cf. §1). (composantes confirmées Verif : §3bis Njal Stormcaller Psychic NoBlocking + stun Flying.)
  [n=1, 70001 avoided]
- `Trajann MomentShackle (self-heal REPEATABLE ~4365 base) + Resilient + MartialKatah (−20% normales) + ~4249/tour` —
  **ENNEMI-À-ÉVITER / ENGINE (mur self-healing)** : MomentShackle est un actif STANDARD sur cd (~2 tours), PAS
  once-per-battle → Trajann se heal-to-full (~+5684 scaled) tous les ~2 tours pendant que Resilient absorbe tout
  spike sub-Overkill ET que MartialKatah réduit mes normales de 20% ET qu'il tape ~4249/tour. Pour un roster
  **chip-only** (~2100-3000/tour) c'est un mur INKILLABLE qui se répare plus vite que mon dmg ET out-damage mon
  tank → il devient la **wincon late de facto** une fois les screens (Angrax/Tigurius) tombés. → fenêtre de kill =
  un **overkill MULTI-SOURCE en UN tour** pendant que MomentShackle est en cd, OU un **Direct/Psychic** qui bypasse
  son block (DoomSiren Pierce100). ⚠ **RÈGLE RECON-RÉSERVE-LE-BURST (vécu seed 70004 triggered-against-me)** : au
  recon, si l'adverse aligne un Trajann (ou tout anvil Resilient+self-heal) et que mon roster est burst-léger,
  **RÉSERVER mon burst anti-block (Direct/Psychic) POUR LUI** ; le dépenser tôt = chip-only vs l'anvil = loss
  structurelle (j'ai gagné la guerre des engines/dive 4v1 mais DoomSiren déjà spent → jamais pu finir Trajann).
  Même classe que le repair-engine 97002 (« kill CE tour ou ne pas committer ») porté à un Resilient+self-heal.
  (composantes confirmées Verif : §3bis Trajann MomentShackle REPEATABLE + Resilient + MartialKatah.) [n=1, 70004 triggered-against-me]

### Miennes — à ENCHAÎNER (ordre imposé)
- `Volk FrenziedFiring (AoE r3) + grappe ennemie dive (summon-engine adjacent à un anvil/chaff)` — **MIEN-À-ENCHAÎNER
  (cluster-softener 3-target)** : FrenziedFiring frappe la cible primaire + TOUS les adjacents À ELLE, score des
  hits bonus sur la primaire par hex libre (max 10), et les bonus FleshmetalGuns frappent CHAQUE ennemi touché
  (cf. §2 Volk). PLAY : quand l'IA dive un soft summon-engine dans une grappe serrée, viser l'engine avec
  FrenziedFiring **depuis la tuile courante** (garder HeavyWeapon = +dmg si Volk n'a pas bougé) → l'engine est chunké
  POUR le kill, les threats adjacents (anvil, summons frais) eatent le splash, et la mécanique de leftover-hit kill le
  chaff adjacent GRATIS. Vécu seed 70006 : un cast a fait −7439 sur le Winged Prime (summon-engine) + −2888 splash sur
  Trajann (anvil) adjacent + KILL un Hormagaunt frais (−2992) = un seul cast qui casse le summon-engine, chip le mur, ET
  nie le snowball simultanément. (composantes confirmées Verif : §2 Volk FrenziedFiring AoE + per-free-hex + FleshmetalGuns +
  HeavyWeapon.) [n=1, 70006 chained]
- `Typhus PlagueWind (3-target Psychic AoE Pierce100 NoBlocking) + grappe ennemie diving into a tight cluster` —
  **MIEN-À-ENCHAÎNER (anti-mur-TermArmour, 3-target full-bypass)** : un seul cast de PlagueWind frappe la cible primaire +
  l'adjacent + le further-adjacent, et chaque hit Psychic Pierce100 passe à PLEIN à travers TOUT TerminatorArmour/Resilient/armure
  (l'exclusion Psychic est par-hit, cf. §1 TerminatorArmour). PLAY : quand le bulk all-melee ennemi s'est BUNCHÉ en fermant la
  distance (rows 5-6 closing), caster PlagueWind sur la grappe → softène 2-3 anvils TermArmour simultanément à pleine valeur,
  enable les multi-kills du tour suivant. C'est l'OUTIL de bris d'un mur de 2-3 anvils TermArmour groupés (là où une mêlée
  Pierce-only tomberait à 330-954/coup). Vécu seed 70059 W : un cast a chunké Ragnar 3914 + TG 3154 + Maladus 2432 d'un coup
  (3 anvils TermArmour softés) → enabled le triple-objectif T3 (K! TG + kill Ragnar + chunk Maladus). (composantes confirmées
  Verif : §2 Typhus PlagueWind Psychic Pierce100 NoBlocking 3-target cascade + §1 TerminatorArmour exclut Psychic par-hit.)
  [n=1, 70059 chained]
- `Kharn FinalJustice/TheBetrayer death-riposte + Kharn mourant ADJACENT à un anvil chunké` —
  **MIEN-À-ENCHAÎNER (extraction de valeur sur la mort)** : à la mort de Kharn (sauf Overkill), FJ tire une normale → TheBetrayer
  chaîne une 2ᵉ attaque 4× Eviscerate, les deux déchargeant ensemble sur l'adjacent. PLAY : si Kharn DOIT mourir au front,
  l'orienter adjacent à un anvil ENNEMI chunké → sa death-riposte extrait un gros burst qui setup un 1-shot du tour suivant.
  Vécu seed 70059 (status=chained, NON-intentionnel — Kharn over-étendu, cf. H03) : Kharn tué par Maladus → death-chain 6481 sur
  Maladus (9615→1935) = Maladus devenu 1-shot le tour d'après (tué T4). ⚠ C'est le VOLET POSITIF d'un over-extension subi :
  préférer NE PAS sacrifier Kharn (mon meilleur carry) du tout, mais s'il tombe forward, orienter sa mort vers un anvil chunké
  plutôt que le vide. (composantes confirmées Verif : §2 Kharn KillMaimBurn chaîne + FJ/TheBetrayer death-riposte 4× Eviscerate.)
  [n=1, 70059 chained]
- `Certus held-Overwatch turret (r3, gate NOT-attacked) + cluster cohésif Resilient (Nauseous Healer + Gibbas KustomForceField armor-aura) baitant le dive` —
  **MIEN-À-ENCHAÎNER (reaction-engine, demi-réciproque H03)** : un ennemi tout-soft/move-in est CONTRAINT de closer dans le cluster
  Resilient tenu → il dive dans l'arc de Certus held-Overwatch → chaque mover qui entre en portée r3 se prend une riposte SÉPARÉE
  (aucun cap once-per-turn, cf. §3bis Certus + §1 Overwatch). PLAY : HOLD Certus (ne pas attaquer = OW armé) DERRIÈRE le cluster
  armor-buffé → les soft carries qui dive se font reaction-kill GRATIS sans dépenser d'action offensive. Vécu seed 70061 (status=avoided,
  T1-T5) : 3 reaction-kills successifs sur le dive — Calandis 2300, Judh 2214, Bellator 1819 (le summon-engine !) → highest-value engine
  du match. C'est le pattern H03-réciproque (cf. 96002/98002/70056). ⚠ MAIS le HOLD doit FINIR une fois les engines morts (cf. H51) :
  en 70061 j'ai over-held après que le reaction-engine ait gagné la guerre des engines → round-cap timeout. (composantes confirmées Verif :
  §3bis Certus Overwatch sans cap + §1 Overwatch riposte-par-mover.) [n=1, 70061 avoided]
- `Azkor OverwhelmingWrath (Taunt-lock) + AoE retardée + grappe cohésive` — **MIEN-À-ENCHAÎNER (engine-disable + chunk)** :
  OverwhelmingWrath Taunt place sur tous les adjacents Taunted_OnlySpecificTargets + BlockMovement + CantUseAbility
  (cf. H30 = engine-disable) → un carry/buffer ennemi adjacent est forcé de frapper le taunter Azkor (Terrifying blunte
  sa mêlée) ET movement-locké + actifs coupés (no WarHowl-class) ; PUIS l'AoE retardée d'Azkor chunke la cible au tour
  suivant. PLAY : caster OverwhelmingWrath quand un carry/buffer mêlée ennemi est adjacent à Azkor → taunt-lock (disable
  ses actifs class-WarHowl pour le round) + laisser l'AoE retardée le chunker ; le Terrifying d'Azkor rend la mêlée forcée
  quasi-gratuite. Vécu seed 70006 : a taunt-locké Ragnar (no WarHowl) + AoE retardée 2036+2320 = un carry mêlée neutralisé
  comme buff-engine ET chunké, payé seulement avec les PV d'Azkor (tanky). (composantes confirmées Verif : H30 Taunt
  coupe l'actif n=3 ; §3bis Azkor OverwhelmingWrath Taunt + AoE retardée.) [n=1, 70006 chained]
- `Imospekh Overwatch (held, non-attaqué) + InescapableDeath (chain-on-OW-kill)` — **MIEN-À-ENCHAÎNER / ENGINE
  (turret de réaction)** : tenir Imospekh HORS d'attaque arme son Overwatch ; sur un kill déclenché par Overwatch
  il **RESTE en Overwatch** (retenant 1 hit de moins, InescapableDeath) et **chaîne sur l'ennemi suivant** ; chaque
  kill in-chain ajoute +1 hit (MultiThreatEliminator) avant le −1 → un seul tour ENNEMI a rendu **8467 dmg + 1 kill**
  (11 OW hits) plus la regen LivingMetal. PLAY : garder Imospekh turret-positionné, screené (BigTarget Gulgortz),
  et NE PAS attaquer avec lui quand un dive arrive → la value de réaction (chaîne OW) > un actif. Vécu seed 70008 :
  la chaîne OW a tué un Death Rider puis continué sur l'adjacent en retenant les hits → a porté la récupération de
  3v6 à 5v2. (composantes confirmées Verif : H06 §3bis Imospekh InescapableDeath OW-chain + MultiThreatEliminator
  +1-hit/kill.) [n=1, 70008 chained]
- `Gulgortz Waaagh (summon 2 Ork Boyz + buff d'équipe + charge) comme swing de comeback` — **MIEN-À-ENCHAÎNER /
  ENGINE (board-swing en une activation)** : un cast (gated « n'a pas bougé ») ajoute 2 corps ~4986 HP + buffe les
  Orks/adjacents (+1 move, normales mêlée +582/+1 hit) + charge un ennemi EN MOVE RANGE + tous les Ork Boyz prennent
  un tour. PLAY : caster depuis une position avec une cible de charge VALIDE en move range + des hex adjacents libres
  (la charge sur une cible trop loin / sans hex libre est rejetée mutated=False). Vécu seed 70008 : un cast a chunké
  Kut 9539→2675, tué un Death Rider, chunké Dreir 9304→2044 → a flippé 3v6-down en 5v2-up. (composantes confirmées
  Verif : §3bis Gulgortz Waaagh nrOfSummons=2 + buff d'équipe + charge-en-move-range + Ork Boyz take-a-turn.)
  [n=1, 70008 chained]
- `Arjac Foehammer (+2183/Character défait) snowball` — **MIEN-À-ENCHAÎNER (finisher snowball, range 2, Stun)** :
  Foehammer scale **+2183 dmg par Character tué dans la bataille** (cumulatif) + Stun jusqu'au prochain tour d'Arjac
  → après plusieurs kills il monte à ~9k et peut one-shot un tank ~8k. ⚠ **CAVEAT (vécu seed 70008 status=MISSED)** :
  il est sur une **LONGUE cooldown de bataille** → il est resté [indispo] tout l'endgame quand j'en avais besoin
  contre Burchard. PLAY : séquencer les character-kills d'abord pour pomper Foehammer, MAIS ne JAMAIS en faire la
  SEULE réponse à un tank (il ne sera pas dispo au moment voulu) ; le coupler à un bypass-armure persistant.
  (composantes confirmées Verif : §3bis Arjac Foehammer +2183/Character + Stun.) [n=1, 70008 missed]
- `Vitruvius RadBombardment (ligne Toxic AoE) + Arjac Foehammer (nuke Ranged-tagged, même tour)` — **MIEN-À-ENCHAÎNER
  (alpha-swing quand on est en déficit de board)** : le même player-turn, RadBombardment soften 4 ennemis groupés (cf. §3bis
  Vitruvius) PUIS Foehammer one-shot un carry full-HP. Foehammer est tagué **Ranged profile=Power** (gameconfig confirme) →
  **BYPASSE Terrifying** (réduction MÊLÉE only) et touche un carry Terrifying à plein PV ; le +2183/Character défait scale le
  nuke (vécu seed 80000 (opus run) : avec 2 de mes Characters déjà morts, Foehammer a délivré un K! franc sur un Atlacoya full-HP
  + Stun). ⚠ **cross-validé les DEUX sides** : B (mine) a exécuté l'alpha (« 3v6 → 3v4 tous mes units full HP »), A (theirs) a
  identifié Foehammer comme menace high (« scaling nuke + stun »). PLAY : en déficit numérique, l'attrition lente perd — l'alpha
  AoE-line + finisher Ranged-tagged en un tour est le bon swing. [self-play consensus, seed 80000 (opus run)]
- `Exitor CordClaw (Direct Pierce100) one-shot Archimatos (le summoner) → aucun Possession body` — **MIEN-À-ENCHAÎNER
  (déni d'engine + déni de body)** : Possession spawn un corps sur CHAQUE kill d'Archimatos (mêlée→Bloodletter,
  ranged→Blue Horror) ; tuer Archimatos avec MON unité (il est la VICTIME, pas le tueur) = **zéro Possession body**
  ET retire le summon-engine. PLAY : focus le summon-engine avec un one-shot armor-ignore AVANT qu'il summon ;
  l'identité du tueur compte pour Possession. Vécu seed 70008 : Exitor CordClaw 4× Direct Pierce100 a one-shot
  Archimatos 8034→0 T2 pre-summon, aucun body. (composantes confirmées Verif : §2 Exitor CordClaw Direct Pierce100 ;
  §2 Archimatos Possession trigger = killer-identity.) [n=1, 70008 chained]
- `Yarrick SendInTheNextWave (Cadian Guardsmen) + zone de contact → corps de réaction/écran jetables` — **MIEN-À-ENCHAÎNER
  (chaff-screen + reaction-bodies)** : chaque cast summon 2 Cadian Guardsmen +1 par allié DÉFAIT (cap 5, ~3989 PV, tirent
  immédiatement, cf. §3bis Yarrick) → les summoner VERS la zone de contact ajoute des corps de réaction qui screen ET
  punissent les summons-on-appearance adverses ET chip les casters/turrets au range, **sans dépenser les actions de mes
  héros**. PLAY : poser les Guardsmen au contact → ils tuent les summons ennemis qui apparaissent (Pink Horror/Screamer/
  Neophyte) ET chipent les casters/turrets en réaction. Vécu seed 70006 : 3 Guardsmen ont tué le summon d'Abraxas (u199)
  à l'apparition + chipé Abraxas/Maugan Ra ~4424 en réaction = chaff jetable qui screen et trade gratis. ⚠ leur compte
  scale avec MES défaites (la mort de Judh a ajouté +1) → un kit qui se renforce à mesure que je perds des corps. ⚠ ils
  consomment leur action au tour IA (réaction) → indisponibles à mon tour immédiatement suivant. (composantes confirmées
  Verif : §3bis Yarrick SendInTheNextWave cap5 +1/défaite + tir immédiat.) [n=1, 70006 chained]
- `WarHowl (Ragnar) → burst mêlée des Characters buffés` — **MIEN-À-ENCHAÎNER (ENABLER de burst)** : poser le
  **buff WarHowl AVANT** la frappe burst (WarHowl en 1er, l'attaque ensuite). WarHowl est un **no-move gate**
  (Ragnar ne doit PAS avoir bougé) qui **ne finit PAS son tour** → buffe Ragnar + tous les Characters mêlée
  alliés SANS normale ranged (exclut Abraxas) avec **Unstoppable + +1164 dmg/hit + +36% Crit** jusqu'à la fin
  du tour. Le +1164 FLAT est énorme sur les normales **multi-hit** (Patermine 5× Psychic, Tanksmasha 3×
  Eviscerate). PLAY : WarHowl EN PREMIER → puis délivrer le burst des Characters buffés le MÊME tour. Vécu
  seed 70009 : a converti des plans 2025-3039 / 2815-4225 en 3885-4899 / 7245-8655 → **3 K! en UN tour**
  (Tarvakh/Yazaghor/Kut) = enabler décisif du dive-punish. (composantes confirmées Verif : §3bis Ragnar WarHowl
  exclusion-ranged + does-not-end-turn + +1164.) [n=2, 97002/70009 chained]
- `Patermine MightFromBelow (5× Psychic Pierce100 NoBlocking) → lead-burst sur la cible la + armurée` —
  **MIEN-À-ENCHAÎNER (anti-armure)** : MightFromBelow = 5× Psychic Pierce100 NoBlocking → **ignore armure/block**,
  ~5753 en un cast même sur un low roll → idéal vs les corps mêlée high-armor. PLAY : **mener** le burst avec
  MightFromBelow sur la cible la plus dure/blindée (vécu seed 70009 : Tarvakh, ~5753), puis **finir avec une K!
  d'attaque normale d'une autre unité** (Tanksmasha). ⚠ la clause de summon (Purestrain) ne chaîne QUE si le
  Patermine a des decoys adjacents (kill-gated CosmicHorror) — sans decoy, l'Ability_Summon fire mais produit
  RIEN (cf. §3bis Patermine). (composantes confirmées Verif : §3bis Patermine MightFromBelow Psychic Pierce100 +
  summon décoy-gated.) [n=1, 70009 chained]
- `Ulf SavageKiller (réaction 5-hit Power) + dive IA (ennemi active-user move adjacent)` — **MIEN-À-ENCHAÎNER /
  ENGINE de réaction** : SavageKiller résout AVANT l'actif de l'ennemi adjacent → pré-empte ET peut tuer le caster
  mid-cast (a killed Tigurius mid-StormOfWrath, 2754+2958+813). PLAY : tenir une **ligne cohésive**, NE PAS
  sur-étendre, et laisser l'IA dive son engine adjacent à Ulf → kill GRATUIT en réaction (vécu seed 70004 : 26057 dmg
  de réactions T2 ont tué Tigurius+Angrax à 0 coût, 5v5→5v3). Coupler à Isabella RitesOfRestoration pour relancer le
  moteur si Ulf meurt (cf. entrée ci-dessous). (composantes confirmées Verif : §3bis Ulf SavageKiller résout-avant-l'actif.)
  ⚠ re-confirmé n+1 (vécu seed 70005 : 3 vagues de réactions successives DestroyerHive+CrushingClaws+SavageKiller ont tué
  Abraxas (4249→0 quand il a dive adjacent) + 2 Poxwalkers SANS dépenser d'actions offensives ; même pattern « ligne cohésive
  → l'IA dive → reaction-kill gratuit » que 70004/70002). [n=2, 70004/70005 chained]
- `Re'vas EarlyWarningOverride (Overwatch armé +2 Shield Drones) + cluster ranged cohésif shallow vs roster ALL-MELEE` —
  **MIEN-À-ENCHAÎNER / ENGINE de réaction** : caster EWO T1 (arme Re'vas en Overwatch + 2 Shield Drones screen) puis **HOLD**
  toute ma ligne ranged en cluster cohésif → un adversaire **100% melee + 1 ranged** est CONTRAINT de diver dans ma killzone →
  l'Overwatch chunke le 1er diveur AVANT mon tour + la masse de réactions (Overwatch + WireweaveNet counter + Corrodius aura)
  fait le killing SANS dépenser mes actions offensives. PLAY : armer l'OW (NE PAS attaquer = garder le gate not-attacked), tenir
  cohésif et shallow, focus-killer le diveur over-étendu depuis mes back tiles — laisser le reste se faire shredder en réaction.
  ⚠ once-per-turn (EWO [indispo] après cast) → planifier UN gros tour d'Overwatch, pas une masse garantie chaque round (cf. §3bis
  Re'vas). Vécu seed 70056 : EWO T1 → OW chunke Tanksmasha qui dive 10040→6725 avant mon tour → ~9629 + ~16.7k de réactions sur
  2 tours adverses ont tué Ragnar (l'engine WarHowl AVANT son cast) + Atlacoya-enemy + Darkstrider = la moitié RÉCIPROQUE de H03,
  W 8v alive. Même classe que `Ulf SavageKiller + dive IA` (le reaction-engine porte le W si la ligne reste défensive/cohésive,
  pattern 96002/98002/70001/70002/70051/70009). ⚠ CONTRE-INDICATION : INERTE vs un cluster ALL-RANGED qui ne dive jamais (cf.
  §Ennemies Re'vas-côté-ennemi 70052 — le hold-baite-le-dive est le contre-profil de l'all-ranged focus-fire). (composantes
  confirmées Verif : §3bis Re'vas EWO = 2 drones + OW armé/re-arm +1892.) [n=1, 70056 chained]
- `Re'vas EarlyWarningOverride (Overwatch-turret +1892 re-arm/kill) + Sarquael GrimRetribution (held ranged OW) + Aun'Shi SereneUnifier (−50% dmg aura R1) + cluster cohésif` —
  **MIEN-À-ENCHAÎNER / ENGINE de réaction (mur « hold-baits-the-dive » TRIPLE-stack)** : empiler 2 reaction-engines (Re'vas
  Overwatch-turret qui re-arme à chaque kill + Sarquael GrimRetribution held-overwatch ranged) DERRIÈRE une aura défensive
  (Aun'Shi −50% dmg subi R1) sur un cluster cohésif → un ennemi all-melee est CONTRAINT de diver dedans = ~18638 dmg en
  réactions sur le tour adverse = plusieurs carries morts SANS dépenser mes actions offensives, pendant que l'aura −50% garde
  ma ligne à ZÉRO perte hero. PLAY : armer Re'vas EWO + laisser Sarquael **unactioned** (OW armé only-if-not-attacked) le tour
  AVANT le contact, tenir le cluster groupé, NE PAS pousser les fragiles forward ; clusteriser mes T'au près d'Aun'Shi pour
  l'aura −50% avant le dive. Closer = focus-kill l'engine adverse (summon/carry) une fois le board nettoyé par les réactions.
  Vécu seed 70060 W : le dive-punish a tué Tarvakh + Kharn (les 2 carries+engine-source) T2 zéro perte, AVANT que Kharn score
  un kill (TheBetrayer jamais armé) = la moitié RÉCIPROQUE de H03 ; même classe que `Re'vas EWO + cluster vs ALL-MELEE`
  ci-dessus mais avec un 2ᵉ overwatcher ranged + l'aura −50% qui rend la survie GRATUITE (pattern 96002/98002/70001/70056).
  ⚠ même CONTRE-INDICATION : INERTE vs un cluster ALL-RANGED qui ne dive jamais (cf. §Ennemies Re'vas 70052). (composantes
  confirmées Verif : §3bis Re'vas EWO 2 drones + OW re-arm ; Sarquael GrimRetribution held-OW gate=not-attacked ; Aun'Shi
  SereneUnifier cycle R1 −50%.) [n=1, 70060 chained]
- `Sarquael Supercharge (ranged Plasma r3, décapitation : cible + ≤2 hex derrière) + follow-up melee multi-source → one-turn kill d'un engine soft` —
  **MIEN-À-ENCHAÎNER (anti-summon-engine one-turn kill)** : Supercharge front-load ~6366 sur un engine soft (summon/caster
  ~7k no-Resilient), puis 2 normales melee cheap le FINISSENT le même tour → kill GARANTI d'un 7k summon-engine AVANT son cast.
  ORDRE/RÈGLE : lead Supercharge (no-move = HeavyWeapon +dmg) sur l'engine, **vérifier min-total > HP cible AVANT de committer**
  (kill-not-chip, cf. §Ennemies Abraxas — un chip non-létal laisse l'engine caster son board-flip), puis séquencer 2 melee normals
  pour garantir le kill. Vécu seed 70060 W : Supercharge 6366 + Aun'Shi normale + Trajann normale = Abraxas 7026→0 en un tour T3,
  ZÉRO MasterOfTheTutelaries (pas de Pink Horror/Screamer). Le debuff +35% Plasma-pierce que Supercharge laisse aide aussi le
  follow-up. (composantes confirmées Verif : §2 Sarquael Supercharge décapitation r3 + §2 Abraxas MasterOfTheTutelaries no-HP-threshold.)
  [n=1, 70060 chained]
- `Typhus Psychic normal (Pierce100 + NoBlocking) + Ulf GreatFrostAxe (4-hit ACTIF) → kill Trajann (Resilient+MartialKatah+block) en UN tour` —
  **MIEN-À-ENCHAÎNER (anti-anvil self-healing)** : la fenêtre de kill d'un mur Trajann (MomentShackle en cd) existe via une
  séquence à 3 temps : (1) chunker Trajann par RÉACTIONS le tour précédent (DestroyerHive/CrushingClaws) ; (2) **Typhus Psychic
  d'abord** (Pierce100 + NoBlocking → bypass son block ET MartialKatah −20%, qui ne réduit QUE les normales) pour le chunker
  sous le seuil ; (3) **Ulf GreatFrostAxe ENSUITE** (4-hit ACTIF → bypass aussi MartialKatah + bat Resilient floor-then-finish →
  Overkill) le MÊME tour. ORDRE IMPOSÉ : Psychic-bypass-block PUIS actif-multi-hit-finish. EXIGE que MomentShackle soit en cd
  (sinon il heal-to-full ~+5684 et la fenêtre se referme — cf. 70004 où le burst était épuisé, et 70007 où l'écran n'a jamais
  été cassé). Vécu seed 70005 : 4578→3307 (Typhus Psychic) → 3307→0 Overkill (Ulf GreatFrostAxe) = mur self-healing DÉTRUIT.
  ⚠ NE PAS chiper (heal+block annulent un dmg non-létal). (composantes confirmées Verif : §3bis Trajann MartialKatah −20%-normales-only
  + §1 Resilient × multi-hit + Typhus Psychic Pierce100 NoBlocking + GreatFrostAxe 4-hit actif.) [n=1, 70005 chained]
- `Titus FuelledByFury/FinalJustice + mes finisseurs UNIQUEMENT high-HP adjacents` — **MIEN-À-ENCHAÎNER (anti-revive)** :
  la 1ʳᵉ défaite/tour de Titus bloque l'overkill → FinalJustice fire TOUJOURS, mais son revive (5456) ne déclenche QUE si
  la riposte FJ DÉFAIT un ennemi adjacent. PLAY : pré-chunk avec un tank, **finir avec un autre corps high-HP**, et garder
  TOUS mes fragiles (Ulf/Tjark) NON-adjacents → FJ frappe un tank qui survit = pas de kill = pas de revive = mort
  permanente (vécu seed 70004 : tué avec Adamatar 10038 + Isabella 6604 adjacents → FJ a frappé Isabella 4678, survécu à
  1926 → no revive, Titus resté mort). ⚠ **n+1 APPLIQUÉ avec un STUN-debuff (vécu seed 70058)** : tuer Titus avec une ability
  qui pose AUSSI un self-debuff sur le tank survivant aide la riposte FJ à ne RIEN tuer — Aesoth VexillaMagnifica a K!'d Titus
  à 2314 avec SEULEMENT Aesoth 11044 adjacent, et le **−66% dmg de VexillaMagnifica** a réduit la riposte FJ à 587 sur Aesoth
  (survécu) → no kill → no revive = mort PERMANENTE (WasOverkilled=0 vérifié). PLAY : router le coup fatal sur Titus quand SEUL
  un tank high-HP est adjacent, idéalement via une ability qui DEBUFF le tank (absorbe la riposte). (composantes confirmées Verif :
  §3bis Titus FuelledByFury revive-gated-on-FJ-kill.) [n=2, 70004 avoided + 70058 applied]
- `Isabella RitesOfRestoration + Imperial Character défait (reaction-engine type Ulf)` — **MIEN-À-ENCHAÎNER (recover-engine)** :
  ressuscite 1 Imperial Character défait (+ ≤2 Imperial Summons) dans un hex libre adjacent à 1819 PV base scaled (ne peut
  agir ce tour) + self/adjacents heal → **récupère un moteur de réaction** (Ulf SavageKiller/FinalJustice). PLAY : caster
  APRÈS avoir perdu un corps Imperial à un trade pour relancer la punition du dive (vécu seed 70004 : ramené Ulf 2493 →
  moteur SavageKiller relancé). ⚠ **[indispo] après 1 usage** (once/long-cd, cf. H13) → swing UNIQUE, le réserver pour le
  corps le plus impactant. (composantes confirmées Verif : §3bis Isabella RitesOfRestoration resurrect-Imperial-Character.)
  [n=1, 70004 chained]
- `FGL/SuppressiveFire (Burchard) → Pinned → Overwatch turret` — **MIEN-À-ENCHAÎNER** : Pin coupe
  l'Overwatch/déplacement adverse pendant que MA turret Overwatch punit les moves entrants —
  position défensive maintenue = gagne l'attrition par réactions. [n=1, 96002 W]
- `Burchard FragstormGrenadeLauncher (6× Blast, range 2, leftover hits prioritise kills) → kill-chain 2-for-1` —
  **MIEN-À-ENCHAÎNER (kill-chain)** : i2 verbatim « Deals up to 6× Blast Damage to a target within 2 hexes. Any
  leftover hits are allocated to enemy units within 2 hexes, **prioritising kills** » → après avoir tué la cible
  primaire, les hits Blast RESTANTS s'auto-allouent aux AUTRES ennemis dans 2 hex en **priorisant les kills** =
  finit automatiquement un voisin bas-PV. PLAY : tirer Frag sur une primaire déjà chunkée qui jouxte un autre corps
  faible → un cast = 2 kills (vécu seed 70002 : KILLED Tyrant Guard 2759 PUIS chaîné sur le Scarab Swarm adjacent
  2218 = double-kill ; plus tôt un Frag a fini Yazaghor). ⚠ **PAS once-per-battle** : Frag est un actif Blast
  standard à **cooldown** (revient à [prêt] dans le même combat, contraste avec le set H13 DoomSiren/MurderousSwing
  no-refresh) → ré-utilisable chaque cd. (composantes confirmées : i2 rule text verbatim, aucun champ
  once-per-battle dans gameconfig.) [n=1, 70002 chained]
- `Adamatar DoomSiren (3× Direct Pierce100, primaire + 2 adjacents-à-la-cible) + ObsessiveAnnunciation aura (+800 ranged subi)` —
  **MIEN-À-ENCHAÎNER (chunk-2-corps + setup ranged)** : DoomSiren bypasse l'armure (Pierce100) et splash la cible primaire
  + jusqu'à 2 ennemis adjacents À LA CIBLE → lead DoomSiren sur un **fragile collé à un anvil/cluster** = chunke le fragile
  POUR le kill ET chunke l'anvil voisin GRATIS (vécu seed 70002 : Yazaghor primaire -4294 [→ 1-shot kill] ET Tyrant Guard
  adjacent-à-cible -6363, le 12.5k anvil chunké pour rien). PUIS positionner Adamatar **adjacent à un ennemi** pour que son
  aura ObsessiveAnnunciation (+800 dmg ranged subi) **feed mes kills ranged suivants** (Roswitha/Ahriman). PLAY : DoomSiren
  d'abord (le burst Pierce100), Adamatar reste adjacent pour l'aura, ranged ensuite. ⚠ **CAS MkXGravis (vécu seed 70000)** :
  le Direct Pierce100 **bypasse aussi la double-armure MkXGravis** (qui ne réduit pas les Crit/Psychic/Direct, cf. §1) →
  réserver DoomSiren pour un **cluster d'units armurées MkXGravis/Inceptors** : a chunké Bellator 8533→3947 + 2 Inceptors
  adjacents en un cast. Chaque OVERKILL ramp les normales d'Adamatar (ObsessiveAnnunciation +1 hit perma) → viser des cibles
  overkillables pour amorcer le snowball (raté seed 70000 : aucun overkill). ⚠ **status=MISSED (vécu seed 70004)** : le volet
  ObsessiveAnnunciation+ranged n'a JAMAIS pu chaîner car mon seul ranged (Vindicta) est mort AVANT — laissée forward (1,3) dans
  le focus Trajann+Sy-gex → deletée → plus de ranged à amplifier ; leçon = protéger le dealer ranged qui doit consommer l'aura
  AVANT de positionner Adamatar pour le +800. ⚠ **CAS ANTI-BLOCK (vécu seed 70004)** : DoomSiren Direct Pierce100 bypasse aussi
  le **block MomentShackle de Trajann** = le SEUL outil de mon roster qui touchait l'anvil self-healing à travers son block →
  le dépenser tôt (sans cible overkill) = chip-only vs l'anvil = loss structurelle ; RÉSERVER DoomSiren pour l'anvil Resilient+
  self-heal au recon (cf. §3bis Trajann + §5bis Ennemies). (composantes confirmées Verif : §2 Adamatar DoomSiren Direct Pierce100
  splash target-relative + §1 MkXGravis exclut Crit/Psychic/Direct.) [n=3, 70002/70000 chained, 70004 missed]
- `Roswitha BrazierOfHolyFire (2× Flame, nuke single-target) + CondemnorStake (+2183 vs Psyker, assassin de casters)` —
  **MIEN-À-ENCHAÎNER (nuke + anti-Psyker)** : Brazier = gros nuke single-target (2× Flame ~4-5k each → **one-shot un corps
  ~9k non-Daemon** ; 4× hits + aura +60% vs Daemons) → route Brazier sur le plus gros soft-body atteignable (vécu seed
  70002 : Aleph-Null 9037→0). SÉPARÉMENT, CondemnorStake fait de Roswitha un **assassin de Psykers dédié** (+2183/attaque vs
  Psyker, même famille « bypass-via-anti-tool » que Tjark anti-Psyker H11) → router Roswitha sur les Psykers ennemis (elle a
  posé le free 4551 KILL sur l'Ahriman ennemi Psyker en réaction). ⚠ garder au RANGE vs cibles Explodes. (composantes
  confirmées Verif : §3 Roswitha Brazier 2×/4× Daemon-gaté + CondemnorStake +2183.) [n=1, 70002 chained]
- `kill confirmé (K!) AVANT l'attaque normale` (même unité) — **MIEN-À-ENCHAÎNER (séquençage)** :
  jouer l'**ability/attaque qui CONFIRME le kill en premier**, pas après une normale qui a déjà
  dépensé l'action → 97002 a raté un kill en inversant l'ordre (Azkor). [n=1, 97002]
- `Aethana PathOfCommand (+291/+218 Aeldari) + Dante LordOfTheHost (+655 Flying/RapidAssault) + LightOfSanguinius` —
  **MIEN-À-ENCHAÎNER (⚠ conditionnel à la livraison)** : les 2 auras de carry stack quand les deep-strikers
  atterrissent à ≤2 hex l'un de l'autre ET d'une cible → buffe le burst Melta LightOfSanguinius (alpha 1-tour).
  ⚠️ **PIÈGE (vécu seed 98003, status=missed)** : un deep-strike ne peut PAS atterrir adjacent à un ennemi et le
  teleport-move **auto-finit** le deep-striker mêlée non-adjacent (cf. §1 TeleportStrike) → l'alpha est
  **INDÉLIVRABLE** sur un cluster lointain le même tour. **NE PAS dépenser les deep-strikers** quand le cluster
  ennemi est hors charge-range et qu'un atterrissage non-adjacent les strande → les garder **groupés+shallow**
  avec le ranged, alpha SEULEMENT quand tout le roster peut co-fire. (J'ai violé ça = perte des 2 carries T1.) [n=1, 98003 missed]
- `Sibyll PsychicMaelstrom (Psychic NoBlocking) → engine Mechanical blindé` — **MIEN-À-ENCHAÎNER / ANTI-armure** :
  réserver le Psychic NoBlocking (le SEUL bypass du stack Mechanical +582, cf. §1) pour les **engines blindés**
  (Tan Gi'da summon-engine, Aleph-Null repair-hub), JAMAIS le chaff ; pré-positionner la caster T1 pour qu'un
  engine entre en r2+move3 reach T2, plutôt que de strander les carries. (6866 sur Aleph-Null en un cast,
  9037→2171, vérifié.) [n=1, 98003 chained]
- `Tjark HuntersBeyondDeath (anti-Psyker) → casters Psyker ennemis (Xybia/Abraxas/Archimatos-class)` —
  **MIEN-À-ENCHAÎNER / ANTI-engine Psyker** : Tjark fait **+582 PAR HIT vs Psyker** (= ~+2328 sur ses 4 hits =
  assassin de casters) ET son aura suppresse les Psykers ennemis dans 2 hex (−582 dealt, pas d'extra-target sur
  leur normale ranged). Vs un engine-set **Psyker-lourd** (≥2 casters), c'est l'OUTIL DE KILL-ENGINE dédié : router
  Tjark sur les Psyker-casters (Xybia, Abraxas) pour les assassiner, l'aura blunte les survivants. Vécu seed 98001 :
  K!'d Xybia (8514) outright + chunké Abraxas 7026→784 en un hit → le wincon-set Psyker démantelé proprement = W.
  (composantes confirmées : §1 H11 anti-Psyker +582/suppression.) [n=1, 98001 chained]
- `Archimatos Possession + finish RANGED (Psychic NoBlocking) → free Blue Horror` —
  **MIEN-À-ENCHAÎNER (body-snowball)** : un kill RANGED (Psychic) d'Archimatos spawn un **Blue Horror gratuit** dans
  l'hex de la victime (un kill MÊLÉE → Bloodletter) ; le Psychic NoBlocking ignore l'armure. PLAY : finir les
  ennemis bas-PV avec le ranged Psychic d'Archimatos plutôt qu'en mêlée → +1 corps gratuit par kill + bypass armure.
  Vécu seed 98001 : utilisé pour finir Abraxas (784) et le dernier Ork Boy = bodies gratis. ⚠ killer-identity (cf. §2) :
  Archimatos doit être le TUEUR (l'acteur), PAS la victime — vécu seed 70054 : Archimatos ranged-killed un Poxwalker
  (u179) T4 → spawn Blue Horror u189 ; ⚠ le body spawné scale AU-DESSUS du tooltip (runtime 3888 HP / 2194 Atk vs i2
  2619 / 1310 — recon-on-appearance la PV runtime, cf. H43). (composantes confirmées : §2 Archimatos Possession/Psychic
  NoBlocking killer-identity.) [n=2, 98001/70054 chained]
- `Snotflogga SquigHound + attaque normale → Grot auto-attaquant gratuit (engine self-sustaining)` —
  **MIEN-À-ENCHAÎNER (board-farm)** : chaque normale de Snotflogga ajoute +2 hits ET auto-summon un Grot (~7312 PV
  pumpé, cf. H34) adjacent à la cible qui **attaque immédiatement** (cap <5 Grots) → body+chip engine qui se
  nourrit seul. PLAY : juste **continuer d'attaquer avec Snotflogga** chaque tour — chaque swing farme un Grot qui
  trade/chip GRATIS ; l'ennemi gaspille des tours entiers à tuer mes Grots remplaçables pendant que mes héros
  restent sains (vécu seed 98001 W = attrition décisive). (composantes confirmées : §3bis Snotflogga SquigHound +
  Summon auto-attaque.) [n=1, 98001 chained]
- `Snotflogga normale (SquigHound 3 hits discrets) + GetStuckIn → melee-finish d'un assassin Terrifying/Camouflage (Deathleaper)` —
  **MIEN-À-ENCHAÎNER (anti-mitigation melee-finish)** : les 3 frappes Physical DISCRÈTES d'une normale de Snotflogga résolvent
  INDÉPENDAMMENT → contournent partiellement Terrifying (réduction mêlée) ET Camouflage (anti-ranged) ET Resilient (multi-hit ≥2)
  → ~7-8k en une activation. PLAY : router Snotflogga sur un assassin Terrifying/Camouflage (Deathleaper) le tour où il sort du
  deep-strike → near-one-shot AVANT son vanish/re-strike (FearOfTheUnseen). Vécu seed 70053 : a tué Deathleaper 8032 past
  Terrifying via les hits discrets T6 (et a one-shot Archimatos 8034 le même pattern). (composantes confirmées Verif : §3bis
  Snotflogga SquigHound 3 hits discrets ; §2 Deathleaper Terrifying/Camouflage.) [n=1, 70053 chained]
- `Aesoth VexillaMagnifica (stun 2 adjacents + −66% self, cd2 repeatable) + follow-up ranged/melee → stun-then-finish d'un engine` —
  **MIEN-À-ENCHAÎNER (control-then-kill)** : VexillaMagnifica frappe 2 ennemis adjacents plein dmg + les Stun 1 round (CantUseAbility
  coupe leurs ACTIFS, laisse leur normale) + Aesoth −66% dmg subi → l'engine stunné ne peut pas user son actif ce round, et le chunk
  prépare un kill same/next-turn. PLAY : caster VexillaMagnifica quand 2 ennemis (un engine + un body) sont adjacents à Aesoth →
  stun-lock l'engine + chunk, puis finir avec une autre source. Vécu seed 70053 : T3 stun Bellator + chunk un Inceptor ; T5 stun
  Bellator(1654)+Inceptor(5483) puis Calandis finit Bellator = stun-then-finish sur le summon-engine. ⚠ ne PAS budgétiser le dmg de
  VexillaMagnifica comme un K? fiable (fortement réduit par les buffs/blocks de la cible, cf. §3bis Aesoth) — c'est le STUN qui est
  l'arme. (composantes confirmées Verif : §3bis Aesoth VexillaMagnifica stun-2 + −66% + cd2 repeatable.) [n=1, 70053 chained]
- `Thaumachus ArcaneShield (no-move → end-of-turn trigger) → ranged carry le + proche (Shiron) chaque tour` —
  **MIEN-À-ENCHAÎNER / ENGINE (durabilité gratuite sur le carry)** : ArcaneShield repose un bouclier ~5483 PV sur l'allié non-Mechanical
  le + proche ≤2 hex APRÈS le move de Thaumachus, OU à la FIN de son tour s'il N'A PAS bougé (priorité Thousand Sons > Chaos > autre >
  self) → tenir Thaumachus stationnaire/finishing glue le bouclier sur mon ranged carry chaque tour. PLAY : garder Thaumachus immobile
  à ≤2 hex de mon carry ranged → bouclier ré-appliqué en continu = carry effectivement intouchable. Vécu seed 70053 : Shiron shielded
  chaque tour, sain tout le combat. (composantes confirmées Verif : §3bis Thaumachus ArcaneShield no-move trigger + closest-friendly.) [n=1, 70053 chained]
- `chunk + Calandis ranged floor-to-1 + Shiron ranged finish → bat Abaddon Resilient SANS triggerer Drachnyen melee-riposte` —
  **MIEN-À-ENCHAÎNER / ANTI (anti-Resilient-anvil + anti-riposte)** : Resilient floor tout coup létal non-overkill à 1 HP ; un 2ᵉ hit
  DEPUIS 1 HP = kill propre (non-overkill, WasOverkilled=1). En RANGED multi-source on évite Drachnyen (la riposte OFFENSIVE perma-double
  d'Abaddon, qui ne fire que sur SES normales mêlée → ne pas le mêler) → l'anvil tombe sans représailles. PLAY : finir un anvil
  Resilient+Drachnyen-class par chunk → floor-to-1 ranged → finish ranged (jamais en mêlée). Vécu seed 70053 : Snotflogga chunk
  5976→772 → Calandis ranged floor-to-1 → Shiron ranged finish (WasOverkilled=1) = Abaddon défait T7, zéro Drachnyen riposte.
  (composantes confirmées Verif : §1 Resilient floor + §3bis Abaddon Drachnyen riposte offensive sur mêlée.) [n=1, 70053 chained]
- `BeastSlayer carrier (Snotflogga / Tanksmasha-orksNob) + enemy BigTarget/Vehicle (Gulgortz, Kut…) → anvil-killer dédié` —
  **MIEN-À-ENCHAÎNER** : `BeastSlayer` = +dmg vs BigTarget/Vehicle + block ajouté vs l'armure courante → router le
  porteur BeastSlayer SPÉCIFIQUEMENT sur les anvils BigTarget adverses (il les frappe bien plus fort que mes hitters
  normaux : plan Tanksmasha vs Gulgortz/Kut = 4551-6285 BeastSlayer vs ~3000 pour un hitter plat, vécu seed 70009). Sur
  un FinalJustice-carrier (Gulgortz), pairer avec une **marge d'overkill** (>2× PV restants) pour **supprimer sa
  FinalJustice/LightImUp double-volée**. PLAY : envoyer le BeastSlayer (pas un soft) overkiller Gulgortz — le
  multiplicateur transforme un Gulgortz à 1248 PV en overkill clean (vécu seed 98001 : tué depuis 1248 → AUCUNE FJ).
  ⚠ vécu seed 70009 : Tanksmasha a chunk-kill Gulgortz NON-overkillé (FJ a fire mais absorbée par Tanksmasha tank) ET
  pressuré Kut → la marge d'overkill manquait ; budgétiser un chunk de plus pour le déni FJ complet. (composantes
  confirmées : §1 FinalJustice/Overkill >2× + §3bis Gulgortz/Snotflogga BeastSlayer.) [n=2, 98001/70009 chained]
- `tuer un Explodes ennemi DANS son propre cluster → AoE friendly-fire gratis` (Aleph-Null/necroSpyder,
  Snappawrecka, Morvenn…) — **MIEN-À-ENCHAÎNER** : Explodes = 25% PV max Direct à TOUS les adjacents, **sans
  filtre ami/ennemi** (cf. §1) → tuer l'unité Explodes pendant qu'elle est entourée de SES alliés chunke la
  grappe gratis (vécu seed 98003 : Aleph-Null tué → Yarrick ennemi 1160→1, Vanguard 3878→2218, Scarab
  2218→1775 ; vécu seed 98002 : Aleph-Null fini au RANGED (Abraxas Psychic r2) pendant qu'Anuphet + un Necron
  Warrior étaient adjacents → Explodes les a chunkés GRATIS, accélérant l'effondrement du noyau). Silver-lining
  même sur une ligne perdue ; **finir au RANGE** pour garder MES fragiles hors de l'AoE. [n≥3, 98002/98003 chained]
- `Asmodai ExemplarOfHate (mark +728 team melee/OW) → Haarken HeraldOfTheApocalypse (burst multi-hit)` —
  **MIEN-À-ENCHAÎNER (ordre imposé)** : le mark +728 s'applique **par hit** à toute la team → multiplicatif
  avec un burst multi-hit ; **MARK D'ABORD (Asmodai), PUIS le burst Haarken** sur la cible marquée → le
  Herald 4-hit passe de 2832-4248 à **6024-7436** ET touche 2 cibles (la marquée + l'ennemi derrière, qui
  prennent +1310 next-attack). Aligner une cible adverse avec un ennemi derrière elle maximise le combo.
  [n=1, 98004 chained]
- `Tyrant Guard BigTarget (−1 hit ranged aux adjacents) + GuardianOrganism (−33%/−1455 si TG n'a pas bougé) + fragiles adjacents` —
  **MIEN-À-ENCHAÎNER (écran défensif)** : garder le Tyrant Guard en écran forward (NON-bougé pour armer
  GuardianOrganism) et coller mes fragiles (Abraxas Psyker, Yazaghor) adjacents → le ranged ennemi entrant dans
  la grappe est doublement émoussé (−1 hit + −33% dmg) → les fragiles SURVIVENT dans la danger-zone et restent
  pour réagir. C'est l'écran qui permet à la moitié RÉCIPROQUE de H03 (punir le dive en réactions) de fonctionner :
  ligne tenue = réactions gagnent l'attrition (vécu seed 98002 W : Abraxas/Yazaghor adjacents au TG ont survécu le
  ranged adverse et contribué au burst de réactions). ⚠ ne PAS faire bouger le TG (perd GuardianOrganism). [n=1, 98002 chained]
- `Kharn TheBetrayer (kill earné) → auto move+4× Eviscerate au DÉBUT de chaque tour de Kharn` —
  **MIEN-À-ENCHAÎNER (chip récurrent gratis)** : une fois Kharn amorcé par un kill, il auto-move 2 hexes + frappe
  4× Eviscerate un adjacent au START de chacun de ses tours, **SANS action dépensée** → chip récurrent (~900-1300/proc)
  chaque round (vécu seed 98002 : a grindé Toth tour après tour). ⚠ **NE réagit PAS au tour adverse** (fire à son
  PROPRE start-of-turn, pas un Overwatch) → ne pas le compter dans le bilan de réactions ; ⚠ le chip auto-move garde
  Kharn ENGAGÉ forward → tension avec « ne pas sur-étendre mon carry » (Kharn over-étendu/un-retreatable seed 98002).
  [n=1, 98002 chained]
- `cluster MIEN groupé + soutien mutuel → punir le dive adverse en réactions` — **MIEN-À-ENCHAÎNER /
  réciproque H03** : garder mes unités groupées et en soutien mutuel → quand l'IA s'avance dans la grappe,
  ~19590 dmg en réactions (Overwatch/contre) = plusieurs kills SANS dépenser mes actions offensives (vécu
  seed 98004 : Helbrecht+Vitruvius T2, Morvenn T3 tués en réaction = 3 kills ; vécu seed 70002 : ~12k réactions
  ont tué l'Ahriman ennemi puis ~4.3k réactions ont tué Lucien Resilient EXACTEMENT 4308→0 = 2 kills décisifs
  zéro action offensive — un carry BlackRage auto-charge FORCE le dive dans la grappe). C'est la moitié RÉCIPROQUE
  de H03 (bien jouée) qui porte les W ; ⚠ ne PAS la confondre avec la moitié PROPRE (ne pas sur-étendre MES
  carries — violée seed 98004 ET seed 70002 [Abraxas reachable mid-board → focus-killé]). ⚠ **CAS STRUCTUREL
  FORT (vécu seed 70051)** : un adversaire SANS aucun Resilient ET sans carry ranged kiting unreachable **DOIT
  diver** pour porter le combat (100% melee/r2) → un mur Resilient MIEN (Maladus/Dreir/Lucien) absorbe le dive
  et chaque engine soft devient atteignable à sa SORTIE = matchup all-soft+all-melee vs mur Resilient est
  **structurellement favorable** (l'INVERSE exact des séries row-9-inatteignables 96001/97001/70050 — PAS un
  reach-fail) → hold cohésif T1-T2, l'IA avance tout son cluster mid-board, engines softs (Aethana/Sibyll)
  exposés T3 = H02 portée par H03-réciproque. [n≥4, 93001/98004/70002/70051 chained]
- `Maugan Ra HarvesterOfSouls (AoE r3) → grappe de dive ennemie clusterisée` — **MIEN-À-ENCHAÎNER** :
  HarvesterOfSouls splash la cible + TOUS les ennemis adjacents à elle ET en range 3 de Maugan Ra (vrai multi-cibles,
  cf. §3bis Maugan Ra) → cibler **l'ennemi le plus clusterisé APRÈS qu'ils ont dive in** = un cast cleave plusieurs
  corps (vécu seed 98000 : Dreir + 3 Death Riders = 4 cibles en un cast, setup d'un tour de clean-up multi-kill).
  ⚠ **PIÈGE (tension H03 propre)** : caster depuis row 3 expose la carry ranged fragile → privilégier l'angle le
  plus SHALLOW possible, ou accepter un AoE moins optimal plutôt que pousser Maugan Ra dans la kill-zone (vécu
  seed 98000 : la pousser à row 3 chaque tour a contribué à sa mort). [n=1, 98000 chained]
- `Tyrant Guard CrushingClaws (Taunted_CantUseAbility) → engine ennemi soft (summoner OU Psyker-amplifier)` —
  **MIEN-À-ENCHAÎNER (control / engine-disable)** : caster CrushingClaws sur un engine adverse soft → le combo moteur
  **Taunted_BlockMovement + Taunted_CantUseAbility + Pinned coupe TOTALEMENT ses actifs 1 round** (cf. §1 Taunt) sans
  le tuer (utile vs un engine Resilient/ToughToKill dur à finir, OU pour leader un focus pendant qu'il est inerte).
  Verrouille aussi la cible sur mon anvil (ne peut cibler que TG). DEUX cas vécus : (a) **summoner** Dreir (seed 98000) →
  LeadingTheCharge bloqué = 0 summon de Death Riders ; (b) **Psyker-amplifier** Thaumachus (seed 70000) → AttemptedPossession
  ET ArcaneShield jamais castés de TOUT le combat = engine-disable propre + lead du focus. ⚠ durée 2 rounds observée
  (i2 dit 1) + source Pinned non confirmée → cf. H30 (n=2). [n=2, 98000/70000 chained]
- `Azrael Overwatch HELD armé (LionHelm +437) + ligne groupée Terrifying/TerrorsLament + dive mêlée ennemi` —
  **MIEN-À-ENCHAÎNER / engine de réactions (réciproque H03)** : tenir Azrael SANS attaquer ré-arme son Overwatch dans
  le tour adverse (gate=not-attacked, cf. §1) ; le `LionHelm` (range 2) donne **+437 dmg sur les attaques Overwatch des
  alliés à ≤2 hex** → un dive ennemi dans la grappe se fait reaction-killer en multi-source boosté SANS dépenser mes
  actions offensives, et mes forward bodies Terrifying (Dante) + TerrorsLament (Jain Zar, −582/−1 hit mêlée aux adjacents)
  **blunt aussi la mêlée entrante ET les death-ripostes FinalJustice** des ennemis tués en réaction. PLAY : NE PAS pousser
  Azrael forward pour un K? non-garanti — le HOLD armé + grouper des alliés à ≤2 hex = la moitié RÉCIPROQUE de H03 portée
  par le boost (vécu seed 70001 : held → 11510 dmg de réactions = 2 kills T3 sur le dive Godswyl+Dante, FJ ripostes absorbées
  par mes forward Terrifying/TerrorsLament). MÊME mécanisme de W que 96002/98002 (turret défensive RANGED = gagne l'attrition).
  (composantes confirmées Verif : §1 Overwatch gate=not-attacked + §3 Azrael LionHelm +437 + §1 Terrifying/TerrorsLament.)
  [n=1, 70001 chained]
- `Azrael DarkTalonStrike (1× Direct Pierce100 + 6× Bolter LINE) → 2 ennemis ALIGNÉS (deep-strikers)` —
  **MIEN-À-ENCHAÎNER (chunk-2-corps + lock + bypass blindage)** : le Direct Pierce100 sur la cible **bypass armure ET
  TerminatorArmour** (Direct exclu de la réduction, cf. §1) ET la ligne de 6× Bolter touche **TOUS les ennemis en ligne
  droite ininterrompue depuis la cible** → aligner le tir pour que la ligne Bolter passe par un **2ᵉ ennemi clusterisé**
  = chunke deux deep-strikers en un cast + les Suppress (+ Pinned move-1 observé, cf. H38). PLAY : viser DarkTalonStrike de
  sorte que la ligne catche un 2ᵉ ennemi sur le même axe → chunke 2 deep-strikers + les Pin, puis FINIR le chunké avec un
  ranged normal cheap depuis une tuile shallow (vécu seed 70001 : 5124 Direct sur Mataneo + 1189 Bolter splash sur leur
  Dante, both Pinned+Suppressed → Shiron 6-hit normal a fini Mataneo 2029 depuis la tuile courante). ⚠ once-per-battle
  observé (H38) → réserver pour un swing décisif (deux deep-strikers alignés / un tank Psychic/Direct-only type Njal).
  (composantes confirmées Verif : §3 Azrael DarkTalonStrike Direct Pierce100 + ligne Bolter + Suppress ; Pinned/once-per-battle
  = H38.) [n=1, 70001 chained]
- `Jain Zar SilentDeath (3 hits primaire + ≤3 adjacents adjacency-chain) → 2 engines ennemis ADJACENTS` —
  **MIEN-À-ENCHAÎNER (engine-finish + chunk-carry GRATIS)** : SilentDeath = arme lancée (caster ne bouge PAS) qui frappe
  la primaire ET jusqu'à 3 ennemis adjacents entre eux, Pierce80 (bat l'armure ET Resilient sur chaque cible via hits
  discrets). PLAY : quand un engine de sustain adverse (leur Nicodemus) jouxte le carry (leur Dante), **finir le LOWER
  avec SilentDeath** → splash GRATIS le carry voisin dans le même cast ; séquencer APRÈS un gros chunk pour garantir le
  kill de l'engine (vécu seed 70001 : a fini leur Nicodemus 2301 ET chunké leur Dante adjacent 7846→5558 en un cast =
  sustain mort + carry pré-affaibli pour le reaction-kill suivant). ⚠ once-per-battle observé (cf. H13) → réserver pour
  ce double-coup décisif, ne pas l'alpha-dump. (composantes confirmées Verif : §3bis Jain Zar SilentDeath adjacency-chain
  Pierce80, thrown/immobile.) [n=1, 70001 chained]
- `Sy-gex (admecDestroyer) Overwatch HELD armé + ligne groupée` — **MIEN-À-ENCHAÎNER / engine de réactions (réciproque H03)** :
  tenir Sy-gex SANS attaquer en NORMAL ré-arme son Overwatch r3 (gate=not-attacked, cf. §1/§3bis Sy-gex) → tout ennemi qui
  BOUGE dans son arc r3 (mêlée OU non) se prend la volée 4 hits gratis au tour adverse. PLAY : le HOLD armé + grouper la ligne
  = la moitié RÉCIPROQUE de H03 (même mécanisme que la turret Azrael/Burchard). ⚠ **LIMITE (vécu seed 70007 chained)** : un
  SEUL Overwatcher ranged est NÉGLIGEABLE vs un board-flip summon-engine (3797 chunk sur Yarrick, mais l'ennemi a flippé le
  board 3v12 le tour suivant) → l'Overwatch hold ne « gagne l'attrition » que SANS board-flip adverse en jeu (cf. la condition
  turret 96002 vs 97001). ⚠ **CONTRE-EXEMPLE POSITIF n+1 (vécu seed 70058 W)** : le MÊME Sy-gex Overwatch HELD-armé + un screen
  cohésif (Aesoth BigTarget/StandVigil/Resilient) a PORTÉ le W vs un ennemi 3/5 melee/Flying CONTRAINT de diver → l'Overwatch a
  reaction-KILLED Ulf sur le dive (4660→0, pré-chunké BasiliskBarrage) ET la dive a exposé les 2 engines back-row (Sho'syl/Njal),
  tués T4 — ici PAS de board-flip adverse → le hold-armé a bien gagné l'attrition (pattern 96002/98002/70001/70056/70060). PLAY :
  feeder Sy-gex (HeavyWeapon) avec un buffeur ranged (Thaddeus +728) amplifie l'output de l'Overwatch. (composantes confirmées
  Verif : §3bis Sy-gex Overwatch 4× Physical r3 gate=not-attacked.) [n=2, 70007 chained + 70058 W]
- `Sy-gex (admecDestroyer) attaque NORMALE 4× Physical r3 (multi-hit) → cible Resilient` — **MIEN-À-ENCHAÎNER
  (anti-Resilient propre)** : l'attaque normale de Sy-gex = 4 HITS → bat fiablement Resilient (le 1er hit floor à 1, chaque hit
  suivant tue puis OVERkille) → l'outil correct pour tuer CLEAN un summon-engine Resilient (vécu seed 70007 : a both KILLED ET
  OVERKILLED Resilient Yarrick en un coup, ce qui a AUSSI stripé SummaryExecution de ses Guardsmen). PLAY : router le 4-hit de
  Sy-gex sur une cible Resilient finissable plutôt qu'un single-hit K? trompeur (cf. H04/§1 multi-hit-bat-Resilient) ; ⚠ le
  HeavyGravCannon (+364 dmg/+60% pierce) ne s'ajoute QUE vs Mechanical/Terminator Armour/MK X Gravis → inutile vs cibles
  non-armurées. (composantes confirmées Verif : §3bis Sy-gex 4× Physical r3 Pierce1 + §1 Resilient floor-then-finish.) [n=1, 70007 chained]
- `Sy-gex (admecDestroyer) attaque NORMALE 4× Physical r3 + HeavyGravCannon → cible TerminatorArmour (après STUN)` —
  **MIEN-À-ENCHAÎNER (anti-TerminatorArmour propre)** : `HeavyGravCannon` (+364 dmg flat + +60% pierce vs Mechanical/TermArmour/
  MkXGravis, i2 confirmé) fait de Sy-gex (Mechanical attaquant) un **hard-counter de TerminatorArmour** : le multi-hit 4× Physical
  passe la 1ʳᵉ-attaque-réduite (seul le 1er hit blunté, cf. §1 TermArmour) PUIS chaque hit suivant tape full + bonus → tue clean.
  PLAY : (1) STUN d'abord l'engine TermArmour (Aesoth VexillaMagnifica) pour dénier son AoE/actif le round, (2) finir avec le 4-hit
  HeavyGravCannon de Sy-gex. Vécu seed 70058 : Njal (Psychic-AoE engine + TermArmour) stun → Sy-gex 4-hit 2534+2490+1703 → 6727→0
  clean. ⚠ le « seul le 1er HIT (pas toute la 1ʳᵉ attaque-event) est réduit » reste candidate (H48, plausible — le +pierce
  HeavyGravCannon peut « débloquer » apparemment les hits) ; le bonus HeavyGravCannon LUI-MÊME est confirmé i2. (composante
  confirmée Verif : i2 HeavyGravCannon +364/+60% pierce vs TermArmour ; §1 TermArmour 1ʳᵉ attaque réduite.) [n=1, 70058 chained]
- `Lucien normale (Loki) + VisionsOfHeresy (2ᵉ attaque GRATUITE r2) → 2 ennemis bas-PV distincts ≤r2` —
  **MIEN-À-ENCHAÎNER (double-finisher)** : la 2ᵉ attaque gratuite de Lucien cible *n'importe quel* ennemi ≤r2 (i2
  « an enemy within range 2 », pas « the same enemy », cf. §3 Lucien) → elle peut frapper une cible DISTINCTE de la
  normale → **une seule activation de Lucien = 2 kills** quand deux ennemis bas-PV sont tous deux à portée r2 l'un de
  l'autre. PLAY : garder Lucien comme finisher double — quand 2 ennemis bas-PV sont à ≤r2, sa normale K! le premier et
  la 2ᵉ attaque K! le second → 2 kills/activation (peut FinishMatch en un cast). Vécu seed 70051 : normale K! Nicodemus +
  VisionsOfHeresy a fini Tjark 1317→0 dans le MÊME cast → FinishMatch. (composante confirmée Verif : §3 Lucien
  VisionsOfHeresy cible indépendante ≤r2.) [n=1, 70051 chained]
- `Creed SwornProtector → Kell body-block (6548 PV) + SupremeCommander → Guardsmen écran jetable` —
  **MIEN-À-ENCHAÎNER (ressource d'écran, status=na)** : quand Creed a été ciblé, `SwornProtector` spawn Kell
  (6548 PV) comme body-block ; `SupremeCommander` peut poser des Guardsmen jetables pour bait/screen. PLAY : noter
  comme ressource de board disponible pour densifier le bait du dive adverse — sortir les summons-screens TÔT (T1)
  contre un adversaire plus dur aurait densifié le bait (vécu seed 70051 : Kell a spawn passivement quand Creed a été
  ciblé, mais SupremeCommander jamais cast car le combat s'est résolu vite ; ressource sous-utilisée, na). [n=1, 70051 na]
- `Archimatos Incursion (sur un fragile forward) + body-screen → substitut de reaction-engine` — **MIEN-À-ENCHAÎNER
  (board-flip zero-loss / écran-de-réaction)** : Incursion summon des Bloodletters qui **attaquent immédiatement** la
  cible (jusqu'à 6, remplissant les hex adjacents, cf. §2 Archimatos) → les corps créés OCCUPENT les hex, **bloquent
  physiquement les routes d'approche de l'IA et absorbent son focus du tour suivant** → un Incursion sur une cible
  soft/bas-PV devient net-positif MÊME sans kill garanti, et **SUBSTITUE à un reaction-engine manquant** (Overwatch/
  counter absent du roster). PLAY : préférer Incursion à un normal-attack snipe quand la cible a des hex adjacents
  libres ET que la présence-board AI est la contrainte → les summons tradent dans le tour IA pendant que mes héros
  ne meurent pas. Vécu seed 70055 : Incursion sur Yazaghor (fragile) → Bloodletters ont aidé à le tuer ET screené mes
  fragiles → NET +2.00, ZÉRO perte, flip à 5v4 full HP (vs un normal-snipe = perdre Archimatos 1-pour-1) ; a porté
  l'early/mid (5v4→4v3→3v2). ⚠ un roster summon-only n'a PAS de RIPOSTE (les bodies SCREENENT mais ne contre-attaquent
  pas) → ne pas confondre « j'ai un écran » avec un dive-punish (cf. §7 H03 réciproque-requiert-reaction-engine).
  (composantes confirmées Verif : §2 Archimatos Incursion immediate-attack + ≤6 bodies adjacents occupent les hex.)
  [n=1, 70055 chained]
- `Parasite BarbedOvipositor (kill non-Mechanical ciblé → Ripper dans l'hex de la victime) + summon-engines comme écran jetable` —
  **MIEN-À-ENCHAÎNER (body-par-kill + screen disposable)** : quand le Parasite tue une cible NON-Mechanical qu'il a
  ciblée (normale OU ability), un **Ripper Swarm spawn dans l'hex de la victime** et peut agir (cf. §2/§3bis Parasite
  BarbedOvipositor — ne fire PAS sur Mechanical) → couplé à mes autres summon-engines (Incursion d'Archimatos, ItItches),
  ces corps jetables laissent l'ennemi all-melee diver dans le chaff au lieu de mes héros. PLAY : mener avec les
  summon-engines pour bâtir un écran ; finir les soft ennemis avec l'écran + 1 héros, garder mes Psykers/fragiles
  derrière. Vécu seed 70055 : un kill normale du Parasite sur Godswyl (non-Mechanical) a auto-spawné un Ripper Swarm
  (u156, 4010 PV) dans son hex = corps d'écran GRATUIT depuis un kill ; mes 4 héros sont restés sains T2-T4 pendant que
  je tuais Yazaghor/Godswyl/Adamatar. (composantes confirmées Verif : §2/§3bis Parasite BarbedOvipositor Ripper-on-kill
  non-Mechanical dans l'hex de la victime.) [n=1, 70055 chained]
- `Darkstrider StructuralAnalyser markerlight (sur tir ranged) + mes alliés ranged (adjacents / T'au ≤2 hex) + SuppressiveFire Pinned` —
  **MIEN-À-ENCHAÎNER (focus-amplifier ranged + control)** : chaque tir ranged de Darkstrider pose un **Markerlight**
  (Effect_Id 188/208, 3 rounds) → les alliés ADJACENTS + T'au à ≤2 hex font **+728 ranged** vs la cible marquée
  (Darkstrider self-qualifie via la clause T'au-≤2-hex) ET `SuppressiveFire` **Pin** (−1 move, 2 turns) la cible. PLAY :
  ORDONNER Darkstrider EN PREMIER dans chaque focus (poser markerlight + Pinned avant que les alliés tirent) → ses
  propres hits empilés (RangedSpecialist × markerlight-self × buffs) en font mon dealer single-source DOMINANT (vécu
  seed 70054 : 7476 sur Thoread, 4559 plan sur Tyrant Guard = mes plus gros hits), et les alliés ranged pompent le
  même focus. ⚠ le delta +728 ALLIÉ reste non isolé numériquement (cf. H33), mais markerlight + Pinned sont CONFIRMÉS
  live. ⚠ INERTE si Darkstrider est le SEUL ranged de mon équipe (markerlight sans bénéficiaire = self-fed). (composantes
  confirmées Verif : §3bis Darkstrider StructuralAnalyser markerlight-sur-tir + SuppressiveFire Suppress/Pinned.) [n=1, 70054 chained]
- `Isaak CultDemagogue (board-flip r2) + Neophyte Hybrids (Ambush, tour immédiat) → seize numeric advantage` —
  **MIEN-À-ENCHAÎNER / ENGINE (board-flip instantané EN MA FAVEUR)** : 1 cast cible un ennemi ≤r2, place jusqu'à 8 decoys
  dans 2 hex autour, summon des Neophyte Hybrids sur la MOITIÉ (≤4, ~2992 PV, ranged r2, CHACUN Ambush) qui agissent
  IMMÉDIATEMENT (Summon auto move+attack). C'est le MÊME engine que le wiki flagge CRITICAL côté ennemi, ici utilisé POUR
  moi = board-flip + flanc en une activation. PLAY : le réserver pour SEIZE l'avantage numérique une fois l'ennemi aminci
  (vécu seed 70054 : cast T7 sur un Poxwalker → 3v4 → 9v1 = le surnombre qui a fini le combat). Bidirectionnel : dévastateur
  enemy-owned (à tuer Isaak avant cast) ET player-owned (engine décisif une fois l'ennemi thinned). (composantes confirmées
  Verif : §3bis Isaak CultDemagogue ≤8 decoys + Neophyte Hybrids Ambush auto-act ; §1 Ambush.) [n=1, 70054 chained]
- `Isaak Ambush (self-resurrect full-HP sur decoy ami) + mes decoys → récupère un corps focus-killé` —
  **MIEN-À-ENCHAÎNER / ENGINE (recover-engine)** : à sa 1ʳᵉ mort, Isaak laisse un decoy + ressuscite à PV PLEIN (7026)
  sur un decoy ami survivant AU DÉBUT de son prochain tour, puis agit IMMÉDIATEMENT — CONDITIONNEL : s'il ne reste AUCUN
  decoy ami quand son tour commence, il reste mort. PLAY : un kill sur Isaak n'est que TEMPORAIRE tant qu'un decoy survit
  → ne PAS paniquer si l'IA focus mon Isaak chunké ; ses decoys (semés par HypersensoryAbilities/Ambush/CultDemagogue) le
  ramènent full. Vécu seed 70054 : Isaak focus-killé T5 (3465→0) → resurrected full-HP (1,3) T6, a récupéré le corps perdu
  à l'over-extension → le board-flip CultDemagogue T7 a suivi. (composantes confirmées Verif : §1 Ambush self-resurrect
  full-HP-sur-decoy, conditionnel decoy-survivant.) [n=1, 70054 chained]
- `Sho'syl MV71 drone (normale = burst immédiat + drone-screen) + Tan Gi'da ControlEdict (Vanguard-on-attack, Protector) → mur de bodies screen-on-attack` —
  **MIEN-À-ENCHAÎNER / ENGINE (chaîne d'écrans générée par mes attaques, status=chained)** : DEUX engines screen-on-attack qui
  fabriquent des corps à CHAQUE de mes attaques — la normale de Sho'syl summon un MV71 drone (~2k HP, SaviorProtocols 50%
  intercept) qui **attaque IMMÉDIATEMENT** (3854-5782 au Damage stat de Sho'syl) + persiste comme screen ; chaque attaque de
  Tan Gi'da sous Protector summon un Skitarii Vanguard (~3.9k HP) adjacent (cap 5). PLAY : attaquer chaque tour avec Sho'syl +
  Tan Gi'da → mes swings délivrent du dmg ET génèrent des corps-écrans qui SOAKENT le focus ranged ennemi au lieu de mes
  héros/amplificateurs (Vitruvius/Abraxas restent shallow). Idéal vs un ennemi focus-fire : il dépense ses tours à tuer mes
  drones/Vanguard remplaçables. Vécu seed 70057 W : drone + Vanguard ont absorbé ~14k du focus ennemi = mes 5 héros survivent
  (5v0). ⚠ ces bodies SCREENENT mais ne contre-attaquent pas au tour adverse (sauf le hit immédiat du drone à la pose) → ne pas
  les confondre avec un dive-punish reaction-engine (réciproque H03 jouée en ACTIVE focus, cf. §7). (composantes confirmées Verif
  seed 70057 : Tan Gi'da ControlEdict Vanguard-on-attack Protector ; Sho'syl MV71 immediate-attack au Damage stat de Sho'syl ;
  ⚠ la persistance/bodyguard du drone reste candidate hypotheses.md.) [n=1, 70057 chained]

### Anti-synergies
- `Roswitha BrazierOfHolyFire (4× Flame + aura +60% dmg vs Daemons, 2 rounds) + CondemnorStake (+2183 dmg vs Psykers) vs MA compo summon-Daemon + Psyker` —
  **ANTI (triggered-against-me, seed 70059 W — HARD-COUNTER de compo, MITIGÉ)** : Roswitha est le counter DÉDIÉ d'un roster qui
  summon des Daemons (Bloodletter/Blue Horror via Archimatos) ET field des Psykers (Typhus/Archimatos) — Brazier passe de 2× à 4×
  hits + aura +60% Daemon-dmg sur mes summons clusterés, et CondemnorStake +2183 fait d'elle un assassin de mes Psykers. RÈGLE DE
  RECON (miroir de l'aura-anti-X LIVE, cf. Atlacoya ci-dessous) : quand JE fielde Daemons+Psykers, une Roswitha adverse est une
  menace SPÉCIFIQUE à neutraliser tôt. COUNTER appliqué (status=avoided) : (1) ne PAS clusterer mes Daemon-summons sur ses cibles
  (éviter le 4× + aura) ; (2) ne PAS présenter mes Psykers adjacents (éviter CondemnorStake) ; (3) la tuer TOP-early parmi les
  softs (8533, no-Resilient → Tarvakh MurderousSwing 4146 + Typhus 604 l'ont défaite vite). Contrairement à Atlacoya (anti-Psychic
  STRUCTUREL, quasi-imtuable), Roswitha est SOFT → le counter est de la tuer tôt avant qu'elle AoE mes summons / assassine un
  Psyker. (composantes confirmées Verif : §2 Roswitha BrazierOfHolyFire Daemon-gated 4×+aura + CondemnorStake +2183 vs Psyker.)
  [n=1, 70059 avoided]
- `Atlacoya DaughterOfTheAbyss (anti-Psychic −1892 flat) + double-Terrifying core (Atlacoya + Deathleaper) vs MON roster Psyker-heavy` —
  **ANTI (triggered-against-me, seed 70055 — DAMAGE-TYPE COUNTER STRUCTUREL)** : un noyau défensif anti-caster qui NÉGATE
  le profil de dégâts ENTIER d'un roster Psyker-heavy : (1) Atlacoya `DaughterOfTheAbyss` (−1892 Psychic flat sur elle,
  cf. §3bis) réduit mes Psyker-dealers à ~1-2 dmg (vérifié : plans Eldryon/Archimatos [1-1]/[2-2] vs elle TOUTE la partie) ;
  (2) le double `Terrifying` (Atlacoya + Deathleaper) blunte ma mêlée → mes survivors melee tapent réduit. Résultat : mes
  2 ennemis les moins counterés (Atlacoya anti-Psyker + Deathleaper Terrifying deep-strike) survivent à tout mon damage et
  grindent mes fragiles → endgame 3v2 STRUCTURELLEMENT injouable (seed 70055 L : mes 3 survivors chunkés Eldryon/Archimatos
  négatés + Tjark low ne pouvaient pas les damager). COUNTER = tuer Atlacoya EARLY avec du dégât NON-Psychic NON-Terrifying-
  réduit (RANGED Blast/Physical d'un non-Psyker) — mais elle est Terrifying+Parry+self-Psychic-reduction = quasi-imtuable
  pour un roster Psyker/melee → le VRAI counter est la SÉLECTION DE ROSTER (non-Psyker-reliant). RÈGLE DE RECON (miroir de
  l'engine-inerte H02/§6) : une aura anti-X (anti-Psychic) est LIVE précisément quand JE fielde la catégorie ciblée (Psykers)
  → flagger « Psyker-heavy vs anti-Psychic Atlacoya + Terrifying core = loss STRUCTURELLE probable » au recon, ne PAS
  s'appuyer sur des Psykers pour la casser. (composantes confirmées Verif : §3bis Atlacoya DaughterOfTheAbyss −1892 Psychic
  flat ; §1 Terrifying melee-only ; §2 Deathleaper Terrifying/Camouflage deep-strike.) [n=1, 70055 triggered-against-me]
- `FinalJustice-carrier ennemi (Winged Prime/Ragnar/Gulgortz/Trajann…) tué NON-overkill + MA fragile à portée de sa normale` —
  **ANTI (triggered-against-me, seed 70006)** : tuer un FJ-carrier SANS overkill (dégât ≤ 2× PV restants) déclenche une
  free normale qui choisit une cible ÉLIGIBLE **dans la portée d'attaque normale du porteur** (PAS une adjacence dure,
  cf. §1 FinalJustice) → elle a tué ma Judh quasi-morte (230 PV). ⚠ **Le label K! NE warne PAS** : il sommait les hits
  bruts = exactement les PV restants (1627 = 1627, aucune marge d'overkill). PLAY : AVANT de délivrer le coup fatal sur un
  FJ-carrier, garantir **OVERKILL (>2× PV restants)** OU **finir au RANGE** (aucune de mes fragiles à portée de sa normale)
  OU positionner pour que la riposte tape un TANK high-HP (cf. variante safety §5bis Ennemies / doctrine-learned §6). Vécu
  seed 70006 : Azkor K! non-overkill sur Winged Prime → FJ a tué Judh adjacente (lavé seulement par Ambush full-HP revive =
  chance, évitable). C'est la combinaison K!-trompeur (H04) + fragile adjacente à un FJ-carrier à sa mort. (composantes
  confirmées Verif : §1 FinalJustice fire-si-non-overkill + ciblage-portée-normale + §1 Overkill >2×.) [n=1, 70006 triggered-against-me]
- `Vindicta FireOfAbsolution (splash 3× Flame aux adjacents-à-la-cible) + MES units adjacentes à la cible` —
  **ANTI (friendly-fire propre, triggered-against-me seed 70000)** : à CHAQUE tir ranged de MA Vindicta, le splash
  3× Flame touche TOUS les units adjacents à la cible **SANS filtre faction** → friendly-fire mes propres units collées
  à la cible. Vécu seed 70000 : le tir de Vindicta sur Thaumachus (3,4) a splash mon TG (3,3) ET mon Anuphet (4,3)
  adjacents → chunk décisif Anuphet 6733→3737 = a rendu son K! enemy possible (= aggravation de la root-cause loss).
  PLAY : **DÉGAGER mes units de l'adjacence-à-la-cible AVANT tout tir de Vindicta** (cf. §2 Vindicta + doctrine-learned §7) ;
  à 4 hits/normale le passif se déclenche 4×. ⚠ NB : côté ENNEMI le même passif punit le cluster ADVERSE (re-confirmé seed
  70007 : un Vindicta adverse a tué son PROPRE Neophyte + chunké son PROPRE Aesoth 698×6 en tirant sur un cluster serré → le
  splash no-filtre joue dans LES DEUX sens), mais côté MIEN c'est une anti-synergie à gérer. (composantes confirmées Verif :
  §2 Vindicta FireOfAbsolution splash no-filtre.) ⚠ **RE-TRIGGERED-AGAINST-ME (seed 70056)** : ArmoriumCherub + normale sur
  Tanksmasha (3,1) avec mes Calandis (2,1) + Corrodius (2,0) adjacents à la cible → chaque tir a splash 3× → Calandis −~3000 HP
  (4953→1959) ; DÉGAGER mes units de l'adjacence-à-la-cible AVANT de tirer Vindicta (un kill shallow ou un repositionnement
  d'abord). [n=3, 70000 triggered-against-me / 70007 enemy-side confirm / 70056 triggered-against-me]
- `Aleph-Null Explodes (25% maxHP Direct à TOUS les adjacents) + MES units adjacentes (TG/Typhus) à sa mort` —
  **ANTI (friendly-fire propre, triggered-against-me seed 70005)** : Aleph-Null (mon roster) a `Explodes` → à sa mort, 25% maxHP
  en Dégât Direct à TOUTES les units adjacentes, **sans filtre allié/ennemi** (cf. §1). Vécu seed 70005 : tué par Abraxas →
  l'explosion a frappé l'Aesoth ENNEMI adjacent 759→0 (KILL utile) MAIS AUSSI mes propres TG 2259 + Typhus 2259 adjacents =
  chunk auto-infligé évitable. PLAY : **NE PAS coller mes units à un porteur d'Explodes À MOI** s'il peut mourir (même classe
  que Morvenn/Pestillian Explodes) → pré-positionner pour que son splash de mort touche UNIQUEMENT des ennemis ; ici le kill
  d'Aesoth a compensé mais le chunk sur mes 2 corps était évitable. (composantes confirmées Verif : §1 Explodes 25% maxHP Direct
  no-filtre.) [n=1, 70005 triggered-against-me]
- `Corrodius CursedPlagueBell (aura Contagion) + MON Psyker (Typhus) dealant du Psychic DANS l'aura` —
  **ANTI (self-damage Psyker, triggered-against-me seed 70005)** : tout Psyker ENNEMI (= à MOI vs Corrodius) qui est DANS l'aura
  Contagion de Corrodius **s'auto-blesse à CHAQUE attaque Psychic** (i2 base 1310, scale niveau → ~1795 observé). Vécu seed 70005 :
  mon Typhus (Psyker) dans l'aura a pris 1795 self-damage sur son cast Psychic anti-Trajann. PLAY : **COMPTER ce self-damage avant
  de spammer du Psychic dans l'aura d'un Corrodius/Nurgle** — acceptable sur un gros corps (Typhus 12k) mais à BUDGÉTISER ;
  idéalement tuer/sortir de l'aura ou frapper depuis HORS aura. ⚠ tension directe avec la séquence anti-Trajann (mon Psychic =
  mon seul bypass-block) → chaque cast coûte ~1795 de PV. (composantes confirmées Verif : §2 Corrodius CursedPlagueBell self-damage
  Psyker.) [n=1, 70005 triggered-against-me]
- `Mataneo deep-strike/HammerOfWrath finish + cible chunkée lointaine → corps isolé bas-PV` — **ANTI
  (triggered-against-me, seed 98001)** : committer le corps deep-strike pour LANDER un finish le pose **isolé**
  (adjacent aux engines ennemis) à bas PV → focus-killé au tour suivant (même pattern 97002/97000/98000). PLAY :
  **NE PAS** finir une cible chunkée avec un héros exposé qu'on pourrait garder en sécurité — utiliser l'auto-Grot,
  une réaction, ou une unité shallow ; OU laisser la cible à bas PV si elle est inerte sans kill (un Kharn
  non-amorcé à 2399 PV ne fait qu'une normale absorbable). Vécu seed 98001 : Mataneo (9035) committé à (2,5) pour
  finir Kharn à 2399 → focus-killé = un héros tradé pour un finish gratis-disponible ailleurs. C'est la moitié
  PROPRE de H03 violée sous la forme « deep-finish ». [n=1, 98001 triggered-against-me]
- `assassin Khorne planqué` (ex. carry `BloodyFury` Chaos) — **ANTI** : ces carries scalent sur
  les **kills mêlée** (Khorne + re-shield) → **NE PAS** le planquer « pour assassiner », il faut
  qu'il combatte ; le cacher = anti-synergie. [cf. wiki §2]
- `Mephiston FuryOfTheAncients (heal-block 2 rounds) → Healer-engine adverse (Nauseous, Isabella…)` —
  **ANTI (anti-Healer/anti-revive)** : après un MOVE de Mephiston, l'AoE Psychic pose un blocage 2 rounds
  (la cible ne peut être healed/repaired/revived/restore Health, cf. §1 Mephiston) → **arme dédiée pour
  neutraliser un Healer/reviver adverse**. PLAY : après le move-rider, taper la/les cible(s) que le Healer
  adverse voudrait soigner/revive (surfacé en ⚠ critique dans decisionView) → annule le sustain sur ces
  unités (Morvenn heal-blocked → ne peut être soignée ni revive). Coupler avec un kill d'engine. [n=1, 98004 chained]
- `Nauseous Healer + TaintedNarthecium-revive + roster 100% Imperial allies` — **ANTI (revive
  structurellement inerte)** : le revive-engine (75% revive un Chaos adjacent défait) est **INERTE par la
  composition même** quand le Healer est le SEUL Chaos de l'équipe (4 alliés Imperial → aucun Chaos
  adjacent à revive) → l'engine ne vaut QUE par le trait Healer (heal toute faction), JAMAIS par le revive.
  PLAY : contre ce roster mixte, le Healer reste à tuer (heal-block Mephiston + multi-hit overkill vs son
  Resilient) mais **le revive ne menace jamais** → recon vérifier la faction des alliés du reviver au lieu
  de craindre le revive. [n=1, 98004 avoided]
- `repair-hub Mechanical (Aleph-Null FabricatorClaw/Mechanic/LivingMetal) + AUCUN autre allié Mechanical` —
  **ANTI (engine repair structurellement inerte)** : le repair-engine ne répare QUE des unités **Mechanical/
  LivingMetal** → si Aleph-Null est le **SEUL** Mechanical de SON équipe, son kit entier (FabricatorClawArray 2910 +
  Mechanic + LivingMetal repair) **n'a aucun bénéficiaire** = il ne peut que se self-regen, JAMAIS amplifier un allié
  → réduit à un gros corps soft (9037, no-Resilient). MÊME CLASSE que le revive Chaos inerte (98004) : un engine
  d'amplification est conditionnel à l'existence d'une cible valide sur SON équipe. PLAY : au recon, **compter les
  autres Mechanical/LivingMetal alliés AVANT de craindre le repair-hub** ; s'il n'y en a aucun, demote sa menace
  (carte wiki CRITICAL → LOW) et traite-le en corps soft normal — kill au RANGE (Explodes) ; un 2× Flame Brazier
  l'one-shot (vécu seed 70002 : Aleph-Null 9037→0, son repair n'a jamais eu de cible). [n=1, 70002 avoided]
- `MES seuls outils armor-bypass (Exitor CordClaw Direct Pierce100 + Atlacoya Direct) over-étendus T1 + tank MkXGravis
  ennemi` — **ANTI (missed, seed 70008 = ROOT CAUSE)** : quand l'adverse aligne un tank high-armor MkXGravis (Burchard,
  Calgar…) qui DEVIENDRA le wincon late, mes SEULES réponses sont les outils Direct/Psychic/Crit ; les sur-étendre T1
  (= les exposer au focus de contact) les fait focus-killer AVANT de pouvoir les réserver → le tank devient INGRINDABLE
  par mon roster Power/Physical résiduel = loss structurelle. PLAY : au recon, **identifier le tank MkXGravis comme wincon
  late émergent ET marquer mes 1-2 outils bypass-armure comme PRÉCIEUX À RÉSERVER/PROTÉGER** → les garder SHALLOW/screenés
  par défaut (jamais le move forward T1), les conserver pour cracker le tank une fois les screens tombés. Même famille que
  « réserver l'anti-armor burst » (70004 self-heal, 97002 repair-engine) mais ici le levier = un TYPE de dégât, pas un
  cooldown. Vécu seed 70008 : Exitor (3,5) + Atlacoya stranded (5,5) committés T1 → focus-killés → Burchard 12k MkXGravis
  ungrindable (Power Pierce40 ~900/turn, Physical Pierce1 56-227/hit) → L à 1v1. (composantes confirmées Verif : §1 MkXGravis
  double-armure bypass Crit/Direct/Psychic ; §2 Exitor CordClaw Direct Pierce100 ; §3bis Atlacoya Talons Direct-vs-Psyker.)
  [n=1, 70008 missed]
- `Mephiston FuryOfTheAncients (heal-block move-rider, 2 rounds) + MA brick ToughToKill/healer-dépendante (Dreir…)` —
  **ANTI (triggered-against-me, seed 70051)** : le heal-block 2 rounds de Mephiston (cf. §1 Mephiston) coupe la regen
  `ToughToKill` de Dreir (2183/tour) ET tout heal externe → un Dreir floored par Resilient à 114 PV devient
  **NON-récupérable ce round** (Resilient floor 1 mais aucune regen pour remonter) → perdu. ⚠ **repose sur H44
  (verdict Verif=plausible : ToughToKill comme « heal » bloquable via la clause catch-all « otherwise restore
  Health »)** — la composante heal-block est confirmée, l'interaction ToughToKill-bloquable est plausible.
  PLAY : un brick ToughToKill/healer-dépendant face à un heal-block move-rider perd sa durabilité active → le
  tenir **HORS de la chaîne d'adjacence du Psychic move-rider**, ou accepter qu'il devienne un corps à usage
  unique ; ordre d'application côté MIEN = poser le heal-block AVANT de floorer la cible. Vécu seed 70051 : Mephiston
  a heal-block Dreir+Creed T2 → Dreir condamné (seule perte hero d'un W). [n=1, 70051 triggered-against-me]
- `Tjark HuntersBeyondDeath (aura anti-Psyker) INERTE faute de cible Psyker (côté ennemi OU côté moi)` —
  **ANTI (aura inerte, n=2 : avoided seed 70051 + mienne-inerte seed 70055)** : l'aura anti-Psyker de Tjark (+582/hit
  vs Psyker + suppression du multi-hit Psyker) est **ENTIÈREMENT INERTE faute de cible Psyker** → Tjark réduit à un
  melee plat 4× Physical Pierce1 (8536 PV, no Resilient). MÊME CLASSE que l'engine repair/revive inerte (70002 Aleph-Null
  / 98004 Nauseous) mais portée aux **AURAS ANTI-X** : une aura d'amplification/suppression ne vaut que s'il existe une
  cible/bénéficiaire valide. DEUX DIRECTIONS confirmées : (a) **Tjark ENNEMI vs MON roster sans Psyker** (seed 70051) →
  demote la carte adverse high→low, traite Tjark en corps soft (tué T5, jamais une menace) ; (b) **MON Tjark vs un ENNEMI
  sans Psyker** (seed 70055) → Tjark était dead weight sur l'OFFENSE tout le combat (+582/hit, suppression, multi-hit-block
  tous gated-Psyker = zéro contribution), réduit à un melee Physical Pierce1 low-pen Terrifying-blunté = un effective unit's
  worth de output perdu dans un endgame damage-starved. PLAY : au recon, **COMPTER les Psykers de l'équipe CIBLE (la sienne
  pour une aura ennemie, l'adverse pour MON porteur) AVANT de valoriser un porteur anti-Psyker** → s'il n'y en a aucun, ne
  PAS slotter/craindre l'anti-Psyker (carte high→low / corps soft killable franc). (composantes confirmées Verif : §1 H11 /
  Tjark HuntersBeyondDeath conditionnel-aux-cibles-Psyker.) [n=2, 70051 avoided / 70055 mienne-inerte]
- `conditionnel d'engine adverse INERTE faute de déclencheur valide (Thoread UnbreakableDuty / Yazaghor WeaverOfFate)` —
  **ANTI (engine/conditionnel inerte, avoided seed 70054)** : EXTENSION de la règle engine-inerte aux **conditionnels
  SCALANTS et triggers d'AMPLIFICATION** — un buff conditionnel ne vaut QUE si son déclencheur PEUT s'armer dans le
  matchup. DEUX cas confirmés ce match : (a) **Thoread `UnbreakableDuty` +7275HP/+1455dmg** exige « 2+ Imperial Characters
  alliés MORTS » → INERTE car Thoread est le SEUL Imperial de SON roster (le compteur ne peut JAMAIS atteindre 2) → demote
  à plain killable ~10k tank ; (b) **Yazaghor `WeaverOfFate`** (max dmg si 3+ ennemis subissent du Psychic dans le tour)
  → INERTE car aucune source ne dealait du Psychic à ses ennemis (= mes units) → demote à fragile Common 6525. MÊME CLASSE
  que le revive Chaos inerte (98004), le repair-hub sans Mechanical (70002), l'aura anti-X sans cible (70051/70055) : un
  amplificateur/conditionnel est conditionnel à l'existence d'un déclencheur VALIDE. PLAY : au recon, **COMPTER les
  déclencheurs valides d'un conditionnel scalant (allié-mort-de-tel-type, ennemi-subit-tel-dégât, bénéficiaire-de-tel-buff)
  AVANT de craindre son scaling** ; s'il ne peut pas s'armer dans CE matchup → demote la menace (CRITICAL/HIGH → MED/LOW)
  et traite le porteur en corps killable normal. Vécu seed 70054 : Thoread+Yazaghor demotés au recon → focus efficacement
  (Yazaghor T3, Thoread T7) au lieu de les craindre. (composantes confirmées Verif : gameconfig Thoread UnbreakableDuty
  condition 2+-Imperial-dead + Yazaghor WeaverOfFate condition 3+-enemies-take-Psychic.) [n=1, 70054 avoided]

## 6. TODO (savoir non dérivable encore manquant)
- **Sémantique terrain** (Q2 ouvert oracle-plan) : effet gameplay de Swamp / Water /
  glace / feu / Despoiled Ground (LetTheGalaxyBurn) / Contagion tiles. Non observé.
- Seuil exact d'**Overkill** (ratio dmg/PV) — confirmer la formule.
- Interaction `FuryOfTheAncients` (bloque « restore Health ») × `Drachnyen` (SET HP) :
  bloque-t-il le self-heal d'Abaddon ? Non testé.
