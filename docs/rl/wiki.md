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

- **`Resilient` × multi-hit / × focus** : la save (PV→1 au lieu de mourir) fire **UNE seule fois** car
  sa précondition i2 est « **not already at 1 Health** » — elle s'applique à l'**ÉTAT de PV**, pas à la
  source. Conséquence non dérivable : 1ᵉʳ coup létal → floor à 1 (save consommée) ; tout coup **suivant
  du même tour** trouve « déjà à 1 » → la précondition échoue → **tue**. Vaut identiquement pour un
  **multi-hit d'un seul actif** (≥2 hits) ET pour un **focus de plusieurs attaquants distincts** : des
  tanks Resilient (Trajann, Yarrick) sont tombés en un seul actif multi-hit. Donc Resilient ne protège
  PAS d'un burster ≥2 hits **ni** d'un focus multi-source → garder un moteur Resilient un rang DERRIÈRE
  les corps plus tanky, jamais cible la plus proche. ⚠ Exécution : un actif **single-hit** affiché « K! »
  sur un Resilient ne tue PAS (floor à 1) — il faut ≥2 hits, une 2ᵉ source, ou l'Overkill. ⚠ **Floor-then-finish
  par N'IMPORTE QUELLE source >0, summon-DoT/auto-attaque de 1 dmg incluse** (la save ne re-fire jamais) :
  une fois floored à 1, l'unité n'a plus aucune protection → ne JAMAIS laisser un Resilient floored vivre
  un tour, le moindre chip l'achève. (chiffres/règle : cf. gameconfig --trait Resilient ; abilities --ability Kharn/Macer/Angrax pour les multi-hit)
  `▸ Tac: menace=high · counter=multi-hit (≥2 hits) dans UN actif / overkill (>2× PV restants) / focus multi-source / DoT — ne survit PAS à ça [n≥5]`
- **`FinalJustice`** (TRAIT, alias affiché « Final Vengeance ») : à la perte du dernier PV, l'unité
  fait **immédiatement UNE attaque normale** sur une cible éligible puis meurt — **sauf Overkill**
  (= défait par Crit OU dégât du coup létal > 2× PV restants). Non dérivable : la riposte utilise l'arme
  **d'attaque normale du porteur** (un Pierce80 4-hit fait mal, un Pierce20 7-hit est trivial sur armure).
  **Trigger SOURCE-AGNOSTIQUE** : fire **même stunné**, **même tué par AoE/killzone**, **même tué par une
  riposte/Overwatch** (mort = trigger, pas action ; i2 ne fait aucune exception de source). ⚠ La cible FJ
  suit la **PORTÉE D'ATTAQUE NORMALE du porteur** (i2 = « eligible target »), PAS une contrainte d'adjacence
  dure — un fragile DANS la portée normale du porteur est un candidat FJ. ⚠ Le label **K! ne warne pas** :
  il somme les hits bruts ; un kill à PILE les PV restants (= K!) n'est PAS un Overkill (> 2× requis) → FJ fire.
  Porteurs : Kharn, Ragnar (spaceBlackmane), Dante (bloodDante), Gulgortz (orksWarboss), Azrael (darkaAzrael),
  Thoread (templAncient), Trajann, Helbrecht, Winged Prime… (n>1). (cf. gameconfig --trait FinalJustice + --ability <normale du porteur>)
  ⚠️ **CAS GULGORTZ (orksWarboss)** : sa riposte FJ n'est PAS une simple normale — son attaque normale
  (mêlée Eviscerate) **chaîne automatiquement le passif `LightImUp`** (volée ranged ajoutée, hits restants
  redistribués à un ennemi proche), car LightImUp se déclenche « after performing a normal attack » → FJ
  exécute une normale → LightImUp s'enchaîne dessus. Sa mort = **double volée mêlée + ranged** sur les
  proches ; vérifié à plusieurs reprises comme **kill exact d'un finisseur non-overkillant** (Dante seed 95002,
  Tanksmasha seed 70009). → overkiller Gulgortz est encore plus impératif qu'un FinalJustice « plat ».
  (cf. gameconfig --ability Eviscerate/LightImUp)
  ⚠ **3 VOIES POUR NIER FJ (confirmé seed 70057, 4 carriers gérés)** : (a) **Overkill** (coup létal > 2× PV
  restants — verbatim i2 « unless Overkilled » : `Attack_WasOverkill=1` → FJ NON déclenchée) ; (b) **kill SANS
  eligible target à portée de sa normale** : le trait FIRE (`IsActingBeforeDeath=0`) mais résout en **no-op
  zéro dégât** — seule « free kill » hors Overkill (ex. tuer un porteur isolé sans corps de valeur à portée
  de sa normale) ; (c) **router la riposte sur un corps ARMURÉ/tank** si le porteur a une normale faible-pen
  (ex. Ragnar 7× Chain Pierce20 → trivial sur Mataneo Mechanical). DOCTRINE : overkiller les FJ à riposte forte
  (Dante Pierce80, Gulgortz double-volée), router la riposte faible-pen sur un body armuré, ou tuer hors-portée
  de la normale.
  `▸ [self-play consensus, seed 80072]` **Azrael FJ — kill EXACT (non-overkill) déclenche FJ.** Confirmé par
  les DEUX sides : stacker plusieurs attaquants en VISANT l'overkill ne suffit pas si le coup létal tombe à
  PILE les PV restants (`Attack_WasOverkill=0`) → FJ fire = riposte mêlée sur l'adjacent le plus proche. Ligne
  correcte = chip-first puis UN coup overkillant (>2×), OU router le kill pour qu'aucune pièce de valeur ne soit
  à portée de la normale du porteur. [self-play consensus, seed 80072]
  `▸ [self-play consensus, seed 80085]` **Ragnar FJ — DEUX voies en UN match : overkill nie, kill-exact fire.**
  Match symétrique, les DEUX sides concordent. (a) Winged Prime tué avec OVERKILL (ratio >2×) → `IsActingBeforeDeath=0`,
  FJ DÉNIÉE. (b) Ragnar tué en fin de partie à EXACTEMENT ses PV restants (no overkill) → `IsActingBeforeDeath=1`,
  riposte multi-hit qui a TUÉ le finisseur (mort = trigger). Doctrine : overkill (>2×) OU finir avec un body que la
  riposte ne peut pas tuer-back ; en 4v1 final, mieux vaut LAISSER un porteur neutralisé que sacrifier le dernier
  corps à sa riposte. [self-play consensus, seed 80085]

- **`Explodes` / `PutridExplosion` = friendly-fire AoE exploitable** : explose à la mort, dégâts (% PV MAX)
  à TOUS les adjacents **y compris les unités ALLIÉES** — AUCUN filtre ami/ennemi (i2 « all adjacent units »).
  **DOUBLE-TRANCHANT** : (a) **exploit** = tuer un Explodes ennemi positionné au CENTRE d'un cluster ennemi
  DEPUIS LE RANGE → AoE gratuit sur tous ses voisins, zéro coût, mes fragiles hors adjacence ; (b) **danger**
  = ne JAMAIS coller mes unités à mon propre Explodes s'il peut mourir (son splash frappe MES units adjacentes).
  Porté par : Morvenn, orksKillaKan/Snappawrecka, necroSpyder/Aleph-Null, Pestillian/deathPutrifier. NB :
  Pestillian a aussi **Resilient** → le coup final doit Overkill (ou être un 2ᵉ hit) pour qu'il meure et déclenche
  l'explosion. (cf. gameconfig --trait Explodes / --trait PutridExplosion / --ability explodesDmg)
  `▸ [self-play consensus, seed 80072]` n+1 friendly-fire confirmé : Aleph-Null tué au RANGE pendant qu'un allié
  (même camp) était adjacent → l'explosion a chipé cet allié (« kill l'Explodes au range = free chip sur leur
  cluster, garder MES units non-adjacentes »). ⚠ B a observé un splash **> 25% maxHP attendu** — **anomalie**
  (possible interaction Direct + tile/fire) à re-vérifier ; PAS une contradiction de la règle de base. [self-play consensus, seed 80072]
- **`BattleFatigue`** (Guardsman + la plupart des NPC/summon-trash : Cadian Guardsman, Ripper Swarm, Grot…) :
  à la mort d'un allié **dans un hex ADJACENT**, **%-chance** que le porteur fuie et soit retiré (+% si Overkill).
  **Adjacency-gated ET probabiliste** : seuls les VOISINS du défait roulent ; déclenche sur N'IMPORTE QUELLE mort
  d'allié adjacent (pas seulement le summoner). ⚠ probabiliste → une fuite observée ne prouve PAS que l'adjacence
  FORCE la fuite (c'est un roll). **Tactique** : overkiller une unité au CENTRE d'un cluster de trash BattleFatigue
  adjacents peut **chain-rout** les voisins (vide un flanc de chaff gratis). Les Grots amis de Snotflogga
  **ignorent** BattleFatigue (exception kit, §3bis). (cf. gameconfig --trait BattleFatigue)
  `▸ Tac: menace=low · counter=N/A (trait ENNEMI exploitable) · exploit=overkiller une mort au CENTRE d'un paquet de trash BattleFatigue = roll de fuite sur chaque voisin → peut vider un flanc de chaff [n≥1]`
- **Repairing/Healing = cleanse PARTIEL** (distinction load-bearing) : restaure les PV ET retire l'ensemble curable
  de débuffs négatifs (Taunted, Suppressed, Markerlight, Stunned, et les deux sous-effets MindControl + son Taunt,
  retirés ensemble) — **MAIS la regen/`Restore` n'en retire AUCUN** (distinction Heal/Repair vs Regen). Repairing
  marche sur Mechanical ; Healing a le même cleanse mais **aucun effet sur Mechanical**. → un actif repair sur un
  allié Markerlighté **neutralise** le setup TwinSmartMissile/Markerlight T'au ; un heal Apothecary sur un allié
  MindControlled le **cleanse** (vérifié seed 93001). Les changements d'effet ne flaggent PAS `mutated`.
  (cf. gameconfig --effect MindControl / --ability DefendTheDivineWork / --ability CombatRestoratives)
- **Blast / faible PiercingRatio vs armure** : dégât **live ≪ chiffre brut gameconfig** (l'armure mange une grosse
  part). Conséquence actionnable : les actifs Blast/low-pierce **ne sont PAS des finishers** vs cibles armurées —
  ne pas les budgétiser comme killing blow sur du tanky. (cf. gameconfig --ability SanctorumMissile)
- **`Stunned` ≠ lock total** (contre-intuition, source-de-vérité i2) : NE bloque PAS toutes les actions. La cible
  stunnée **garde 1 Movement**, peut **toujours faire son ATTAQUE NORMALE** (à dégâts réduits), et perd
  **UNIQUEMENT les ACTIVE abilities** (UI « Blocked by Stunned »). Ses **triggers de mort restent** (FinalJustice
  inclus). Retiré par Healing/Repairing. ⚠ **Ne PAS `endturn` d'office une unité stunnée** (un `mutated=False` sur
  toutes ses actions = artefact runner n=1, PAS la sémantique). **Tactique attaquant** : 1 move ≪ besoin pour
  retreat hors d'une killzone mêlée → une unité-clé sur-étendue + stunnée reste un kill quasi-garanti si forward,
  mais ce n'est pas un lock complet. (cf. gameconfig --effect Stunned / --ability VexillaMagnifica)
- **`LegendaryCommander` + `StandVigil`** (Trajann/Vexilus) : un **actif allié adjacent à un ennemi** → cet ennemi
  +dmg subi (et +hits pour les Characters alliés s'il est aussi adjacent à Trajann) + buff StandVigil. ⚠ **Le
  trigger fire pour l'équipe qui CONTRÔLE Trajann** — quand c'est MOI qui possède Trajann, user un de MES actifs
  adjacent à un ennemi applique le malus à cet ennemi (vérifié seed 70009 : un actif allié adjacent → ExtraDamage
  appliqué à l'ennemi, ReceiveEffect from Trajann). Setup canonique : poser un actif « ouvreur » adjacent à la
  cible avant le focus. (cf. gameconfig --ability StandVigil / --trait LegendaryCommander)
- **`Overkill` = seuil STRICT > 2× PV restants** (load-bearing) : dépasser les PV restants NE SUFFIT PAS — il faut
  **dégât > 2× PV restants** (i2 Overkill). Nie Resilient ET FinalJustice/TheBetrayer death-riposte. ⚠ vérifié
  seed 98001 : un coup à ratio ~1.6× **n'a PAS overkillé** → la death-riposte TheBetrayer a fire. **Doctrine** :
  budgétiser une marge **>2× PV restants**, pas juste « assez pour tuer » ; sinon stacker chip + gros-finisher (ou
  viser un Crit) pour nier FJ/death-riposte sur un porteur (Kharn/Gulgortz/Ragnar…). (cf. gameconfig --trait Overkill)
  `▸ Tac: pour nier FJ/death-riposte sur un porteur (Kharn/Gulgortz/Ragnar…), le coup létal doit dépasser STRICTEMENT 2× les PV restants OU être un Crit — sinon stacker chip+gros-finisher [n=1, 98001]`
- **`Steppable`** : l'unité est **détruite si on MARCHE DESSUS ou si elle est endommagée**, mais **ne peut PAS être
  ciblée** (absente des plans d'attaque). → pour la retirer : `act move --to <son hex>`. Porté par les decoys
  (`genesSmnDecoy`). (cf. gameconfig --trait Steppable)
- **`Ambush` = revive 1× SEULEMENT, niée uniquement en clearant TOUS les decoys** : à la **1ʳᵉ mort** (toute
  défaite, pas que overkill), l'unité laisse un **decoy** (Steppable) ; au début de son prochain tour, si un decoy
  ami **survit**, elle **ressuscite plein PV** sur un decoy au hasard et **agit immédiatement** (Characters
  ressuscitent avant les non-Characters). Le **2ᵉ kill est PERMANENT, indépendamment de l'overkill** (effet
  consommé). → kill **temporaire** tant qu'un decoy survit ; résurrection niée **uniquement si AUCUN decoy ami ne
  survit** → **détruire les decoys** (marcher dessus, Steppable) avant/au moment du kill. ⚠️ **Judh (genesKelermorph)**
  empile **2 sources de decoy** (HypersensoryAbilities-sur-attaque + Ambush-à-la-mort) → il faut **clear TOUS** les
  decoys. **C'est un TRAIT** (lu via la carte unité ; `--ability Ambush` renvoie « inconnue »). Porté par les
  Genestealers (genesBiophagus, genesKelermorph, genesMagus…). Vérifié n=3 sur genesMagus (seeds 70014/93001/98001).
  Doctrine : si je ne peux pas clear le decoy, accepter le kill temporaire et planifier la 2ᵉ mort au tour suivant.
  (cf. gameconfig --trait Ambush / --effect Ambush_CanResurrect)
  `▸ [self-play consensus, seed 80085]` **n+1 sur genesSmnAberrant (summon de Hollan) — Ambush porté par un SUMMON,
  pas que le Character.** A a tué l'Aberrant mais a LAISSÉ le `genesSmnDecoy` un-cleared → résurrection FULL-HP au
  début de son prochain tour (coût tempo + re-kill) ; 2ᵉ kill = PERMANENT. **Re-confirme** : `Ambush_CanResurrect`
  s'applique aux summons, et la résurrection est niée UNIQUEMENT en clearant TOUS les decoys amis au même tour que
  le kill. [self-play consensus, seed 80085]
- **`TerminatorArmour`** : SEULE la **1ʳᵉ ATTAQUE/tour** subie est réduite, **SAUF profils
  Psychic/DirectDamage** (exclus ENTIÈREMENT → passent à plein **même en 1ʳᵉ attaque**) ; immunité
  Suppress. ⚠️ Le compteur « 1ʳᵉ attaque » est **GLOBAL par tour (n'importe quel attaquant)**, reset après
  le 1ᵉʳ attaquant. Gaté par « attaque » (un multi-hit d'une SEULE arme = une attaque réduite) : **toute
  attaque DISTINCTE après la 1ʳᵉ ce tour-là tape à plein** → NE protège PAS d'un focus multi-attaquant
  soutenu : un TerminatorArmour SANS Resilient peut être supprimé en un team-turn (vérifié seed 70001 :
  Njal — 1ʳᵉ attaque réduite, puis 2 attaques full → mort en un team-turn). **Counter** : étaler les
  attaques sur 2+ unités le même team-turn (seule la PREMIÈRE est pénalisée), OU ouvrir avec un Psychic/
  Direct (bypass total), OU « gâcher » la 1ʳᵉ attaque avec un coup faible jeté en premier.
  (cf. gameconfig --trait TerminatorArmour) Porté par : blackAbaddon, blackTerminator, darkaTerminator
  (Baraqiel), worldTerminator (Wrask), spaceStormcaller (Njal), **thousTerminator (Toth)**.
  `▸ [self-play consensus, seed 80064]` CONFIRMÉ que Psychic ET DirectDamage bypassent la réduction EN 1ʳᵉ
  attaque : Azrael `DarkTalonStrike` (DirectDamage Pierce100) a frappé Njal à PLEIN (Attack_Is_First_Hit=1,
  ZÉRO réduction) le même tour que Neurothrope `SpiritLeech` (Psychic) malgré son TerminatorArmour. Deux
  observateurs concordent (Direct full + Psychic NoBlocking universal-bypass). Doctrine : ouvrir le focus
  d'un tank TerminatorArmour avec un Psychic/Direct (pas un coup réduit gaspillé).
  `▸ Tac: menace=med · counter=Psychic/Direct passe à plein ; sinon focus multi-attaquant (la 2ᵉ attaque distincte du tour tape plein) ou "gâcher" la 1ʳᵉ attaque avec un coup faible [n≥4]`
  `▸ Tac (AoE-Psychic bypass, n+1) : un seul cast Psychic AoE (Typhus PlagueWind, Pierce100 NoBlocking) passe à PLEIN sur TOUS les targets de la chaîne (primary + adjacents) même si plusieurs sont TermArmour — l'exclusion Psychic/Direct s'applique PAR-HIT, pas une seule fois (vécu seed 70059 : PlagueWind a touché 3 targets full, malgré TermArmour actif sur 2). Doctrine : vs un MUR de 2-3 anvils TermArmour groupés, un Psychic AoE est l'outil de bris optimal (1 cast = N chunks pleins) [n=1, 70059]`
- **`TimeFlux`** (passif **thousTerminator « Toth »**) : la **1ʳᵉ mort de Toth par combat**, si son time
  ghost est sur le board → il **revit** au hex du ghost (PV scale au niveau). **Fire même sur Overkill** ET
  sur une mort en réaction/cascade (vérifié seed 98002 : Toth tué dans une cascade de réactions a
  ressuscité, la 2ᵉ mort Psychic fut permanente). **2ᵉ mort = PERMANENTE** (one-per-battle). **Doctrine :
  toujours budgéter une 2ᵉ source de kill ; traiter Toth comme s'il avait 2 barres de vie.** ⚠ le ghost se
  relocalise à chaque move de Toth (un seul ghost à la fois, invalidé si l'hex devient occupé/impassable,
  cf. H25) → si je contrôlais Toth je le bougerais UNE seule fois pour poser un ghost sûr.
  (cf. gameconfig --ability TimeFlux) `▸ Tac: budget 2ᵉ kill obligatoire ; le finisher permanent = la 2ᵉ mort [n=1, 98002]`
- **`Terrifying`** : réduit UNIQUEMENT les dégâts de **MÊLÉE** subis. **Bypass fiable = RANGED**
  (vérifié : Thaddeus Blast ranged tue la Terrifying Atlacoya proprement). ⚠️ l'armor-ignore/
  perforant/Direct **NE bypasse PAS** Terrifying (ce n'est pas un mécanisme d'armure) — une mêlée
  même Direct/Pierce100 reste réduite. (cf. gameconfig --trait Terrifying) Porté par : Mephiston, Dante,
  Azkor, Atlacoya, Tjark, Deathleaper…
- **`Psychic` (PiercingRatio 100 + NoBlocking) = bypass définitif des cibles Mechanical blindées**
  (confirmé seed 98003) : un profil d'arme Psychic à **100% pierce** ignore TOUTE l'Armure, et le trait
  **`NoBlocking`** (« Cannot be blocked ») bypasse le Block. Les **DEUX couches** d'un stack défensif
  Mechanical sont donc nettement bypassées. ⚠️ `NetherRealmCasket` (Necron) ne réduit que la **Crit
  Damage** (par Mechanical adjacent), PAS le dégât flat → un hit Psychic **non-crit** est totalement non
  mitigé. Le trait `Mechanical` lui-même n'a **aucune réduction de dégât innée** (juste repair-only au lieu
  de heal). ⇒ une source Psychic NoBlocking (ex. Sibyll `PsychicMaelstrom`) délivre **plein pot** à un
  noyau Mechanical haut-Armure type Aleph-Null/Vanguards-sous-Protector (vérifié : full damage en un cast).
  Doctrine : **réserver le Psychic NoBlocking pour les engines blindés (repair-hub/summon-engine Mechanical
  sous grosse armure), pas le chaff** — c'est souvent le SEUL bypass d'un stack Mechanical+armure.
  (cf. gameconfig --trait NoBlocking / --effect NetherRealmCasket)
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
    pas punir (Baraqiel projeté seul a **survécu** — aucune réponse à un terminator),
    **fatal** sinon (Wrask projeté pareil → tué par le ranged/psychic concentré).
  – ⚠️ **AUTO-FINISH d'un deep-striker MÊLÉE (confirmé seed 98003)** : le téléport pose obligatoirement sur
    un hex **NON-adjacent** à un ennemi. Or un deep-striker dont l'actif est **melee-init** (SwoopingHawk
    d'Aethana, charge LightOfSanguinius de Dante) n'a **AUCUNE cible atteignable à l'arrivée** → le
    teleport-move **auto-finit l'unité** (ActionsAvailable=0, zéro attaque possible, cf. H08/H09). La
    contrainte d'atterrissage et l'init-mêlée sont **mutuellement exclusives le même tour** → un
    deep-striker mêlée NE PEUT PAS délivrer d'alpha sur un cluster lointain au tour du téléport ; le manual
    teleport-move le **strande solo** = focus-kill gratuit. ⇒ NE PAS dépenser un deep-striker mêlée tant
    qu'un alpha soutenu (charge en portée + auras stackées + co-fire du ranged) n'est pas posable le **même
    tour** ; le garder shallow+groupé. (Les deep-strikers à actif **RANGED** — Baraqiel PlasmaCannon — ou
    un move-normal-depuis-la-position avec cible mêlée adjacente PEUVENT agir après déploiement.)
  (cf. gameconfig --trait TeleportStrike) Porté par : worldTerminator (Wrask, cf. §2), darkaTerminator
  (Baraqiel), **eldarAutarch (Aethana, melee SwoopingHawk → auto-finish), bloodDante (Dante,
  LightOfSanguinius charge)**.
  `▸ Tac (bloodDante « Dante » — deep-strike Terrifying carry, LightOfSanguinius Melta + debuff aura, LordOfTheHost aura mêlée aux alliés Flying/RapidAssault, FinalJustice overkill-to-suppress) : rôle=carry · menace=high · counter=ne PAS lui présenter un fragile ISOLÉ à sa charge (Terrifying réduit la MÊLÉE → il tanke la mêlée cheap, bypass = RANGED §1) ; s'il dive un cluster GROUPÉ il se fait focus-killer en réactions (vécu seed 98002 : dove solo dans mon cluster screené → mort en réactions enemy-T1 ; vécu seed 70001 : chunké via DarkTalonStrike line-splash + SilentDeath adjacency + chip → tué en RÉACTION quand il a dive ma held-line, sa FinalJustice riposte ABSORBÉE par mes forward units Terrifying/TerrorsLament) ; Overkill pour nier FinalJustice [n=2, 98002/70001]`
  `▸ Tac (n+1 FJ-no-eligible-adjacent + dive-forward-punished, seed 70057 W, confirmé Verif) : Dante a dive forward solo (over-commit) → focus-killé depuis tuiles SHALLOW (incl. Abraxas Psychic qui bypasse Terrifying). ⚠ **2ᵉ free-kill path sur Dante (en plus de l'Overkill)** : tué SANS eligible target adjacent à portée de sa normale → FinalJustice a fire (`IsActingBeforeDeath=0`) mais ZÉRO dmg (no-op, cf. §1). PV soft → le tuer où il a dive isolé = gratuit + supprime son LordOfTheHost amplifier ; Psychic/RANGED bypasse son Terrifying. DOCTRINE = punir le dive forward de Dante depuis le shallow, le tuer hors-portée-de-sa-normale OU overkill [n=3, +70057]`
- **`Overwatch`** (trait ou armé par un actif type EarlyWarningOverride) : **gate = NOT-ATTACKED, PAS
  not-moved** — l'unité peut **bouger PUIS armer l'Overwatch** ; tant qu'elle n'a pas fait d'attaque NORMALE
  ce tour, elle riposte quand un ennemi **bouge dans sa portée** au tour adverse (vérifié seed 98000 :
  Maugan Ra a bougé T1 et l'a quand même armé). **Chaque ennemi entrant en portée = une riposte SÉPARÉE**
  → un dive mêlée/summon qui fait entrer ses unités UNE PAR UNE prend un hit par mover (cascade de KILLs
  possible). ⚠️ **pas d'overlay live des zones armées** (GAP, cf. §6 TODO) → éviter au flair / exploiter
  l'angle mort IA. (cf. gameconfig --trait Overwatch) Porté par : darkaAzrael ; armé par : tauCrisis
  (Re'vas), Maugan Ra…
  ⚠️ **Amplificateur LionHelm (Azrael, range 2, vérifié seed 70001)** : les alliés à ≤2 hex d'Azrael font
  **+dmg sur LEURS PROPRES attaques déclenchées par Overwatch** → grouper plusieurs Overwatchers/contre-
  attaquants autour d'Azrael transforme un dive ennemi en **reaction-kill multi-source boosté** (vécu : 2
  kills sur le dive Godswyl+Dante). Coupler avec le HOLD d'Azrael (ne pas attaquer = OW armé) + une ligne
  groupée = la moitié RÉCIPROQUE de H03 portée par le boost. (cf. gameconfig --ability LionHelm)
  `▸ Tac: menace=high (vs roster mêlée/move-in ; un dive séquentiel se fait décimer 1 riposte/mover) · counter=ne PAS pather dans l'arc ; out-range ; Infiltrate/Teleport pour skip ; ou forcer l'OW sur un chaff d'abord [n≥2]`

- **`Parry`** : réduit les attaques **multi-hit** subies de −1 hit (min 1) → mes multi-hit
  sont moins efficaces contre lui. Porté par : templHelbrecht. (cf. gameconfig --trait Parry)
- **`Taunt`** (effet, variantes `Taunted_*`) : force la cible à attaquer le taunter ; une cible
  Taunted ne peut QUE cibler le taunter, **ne peut PAS s'éloigner / user son actif / heal/repair**
  (les AoE/untargeted peuvent quand même toucher d'autres). **`Taunted_BlockMovement`** l'immobilise,
  `Taunted_CantUseAbility` coupe ses actifs. **Quirk-clé = LOCK** pour les abilities « tir retardé,
  dégâts réduits par hex parcouru » (railgun, cf. §4) : une cible taunted **déjà adjacente** au taunter
  ne bouge pas → tir à plein pot. ⚠️ si le taunter est **LOIN**, la cible **marche** vers lui (= mouvement)
  → le lock ne sert plus au railgun ; le taunter doit être **collé** à la cible AU MOMENT du lock.
  **Healing (ou Repair pour Mechanical) RETIRE le Taunted.** Sources : **Jaeger `HolyDuel`** (taunt
  **mutuel, sans expiration**, bloque mouvement + coupe actifs — verrouille un engine adjacent), **Grots
  de Snotflogga** (`GetEmRuntz`/`SquigHound` : summon **adjacent à la cible** + Taunt `BlockMovement` →
  lock **immédiat**, sans avancer une de mes unités). Insight vérifié : cible HolyDuel-lockée → railgun
  quasi plein = kill propre ; cible non lockée → elle bouge → railgun gâché. (cf. gameconfig --effect Taunted)
- **Attaque normale = id CONCRET par unité** (fait outil/moteur, non dérivable des chiffres) :
  l'attaque normale est un `ActiveAbilityType` **propre à chaque unité** (lu live via
  `NormalAttackType` / decisionView), **JAMAIS** l'abstrait `NormalAttack=17` ni l'id d'une autre
  unité. Passer un id étranger/abstrait **no-op silencieusement** (`mutated=false`, **aucune erreur**)
  → un coup avalé peut gâcher un kill (vécu : un Aberrant a perdu son hit qui tuait le TyrantGuard).
  **Pièges fréquents** : les **summons** (ex. Aberrant : melee propre + auto-attaque Summon) et les
  **Mechanicus** (ex. Actus = admecManipulus, dont le seul actif est `DefendTheDivineWork`, PAS une
  attaque normale). Règle : toujours passer l'id normal **concret** de la vue live et **vérifier
  `mutated=true`**.
- **`play --spec` / `act move` — format de `to` = array d'entiers, JAMAIS un string** (fait
  harness/outil, vérifié par code seed 95000) : le champ `to` d'un move DOIT être un array JSON
  d'entiers `[col,row]`, **jamais** le string `"5,3"`. Un string est indexé positionnellement et
  atteint le `writeS32` de Frida en non-entier → **ERR `build: expected an integer`** ; le message
  n'est jamais construit donc **`mutated=false`**, mais le slot d'action de la boucle est
  **silencieusement consommé**. Effet identique à ne pas agir → un move raté en string cascade : tous
  les actions suivants du même spec échouent. **Toujours passer des arrays d'entiers ; vérifier
  `mutated=true` avant de chaîner les abilités sur un move critique.**
- **`MindControl`** (genesMagus, cible un ennemi adjacent à ≥1 allié) : pour CE round et le suivant
  (**2 rounds**) l'ennemi déale moins de dmg, subit +dmg, et devient **Taunted par l'allié adjacent au
  PLUS HAUT PV courant** (combo `Taunted_BlockMovement` + `Taunted_CantUseAbility` +
  `MindControl_OutgoingDamageReduction` + `MindControl_IncomingDamageBonus`). **Counter-play** : la cible
  contrôlée DOIT taper le taunter — router sa frappe forcée vers le **finish d'un bas-PV** (mettre ce
  bas-PV comme l'allié-adjacent-au-plus-haut-PV pour baiter), ou neutraliser une grosse menace 2 rounds.
  **Côté VICTIME confirmé (seed 80020)** : la victime garde sa **NORMALE dispo sur le taunter** (seul
  l'ACTIF est coupé) ; **tuer le taunter dans cette même action clear les 6 sous-effets immédiatement**
  (free same-turn). [self-play consensus, seed 80020]
  **2ᵉ confirmation (Atlacoya, seed 93001)** : le `Taunted_CantUseAbility` coupe l'ACTIF de la cible
  (sur Atlacoya il neutralise `TalonsOfTheEmperor`, justement l'outil anti-Psyker censé tuer le Magus)
  et ne lui laisse que la NORMALE, forcée sur le taunter. Donc taunter via une unité collée à la
  cible-à-finir route la frappe forcée sur ce finish ; taunter via le Magus lui-même fait taper le Magus.
  Le débuff de dmg est **curable** : tout **Healing OU Repair** retire l'effet (les deux sous-effets d'un
  coup ; vérifié : Apothecary `CombatRestoratives` sur Atlacoya). (cf. gameconfig --effect MindControl)
- **`ContagionsOfNurgle`** (porté par Nauseous/deathRotbone, Maladus/deathBlightlord, Corrodius/deathBlightbringer) :
  aura centrée sur le porteur qui **DEBUFFE l'armure des ENNEMIS dedans** (jamais d'ambiguïté allié) ;
  **2+ auras Contagion qui se chevauchent doublent le strip**. **S'étend par round** : range 1 (early) →
  range 3 (round 5+). Tag live : `ContagionsOfNurgle_ArmorReduction1`. → empiler 2 porteurs Contagion sur le
  même cluster ennemi double le strip ; complémentaire d'un finisher Power/Pierce vs un cluster armuré.
  (cf. gameconfig --effect ContagionsOfNurgle)
  `▸ Tac: menace/valeur=med · counter=à MOI = softener d'armure avant un burst Pierce/Power (empiler 2 auras) ; côté ennemi = ne pas stationner mes unités dans l'aura si je crains un burst armor-augmenté, mais l'effet reste positionnel/lent (range 1 early) [n=1, 70052]`
  `▸ [self-play consensus, seed 80085]` **n+1 ContagionsOfNurgle (Maladus) — aura -armure croissante confirmée par les DEUX sides + enable d'un one-shot.** Aura armor-reduction croissante (range 1→3) softene chaque ennemi approchant la ligne → inflate tous les dégâts du propriétaire (a permis un FlailSwing one-shot d'un repair-engine armure-réduite + WarHowl) ; côté victime, chip l'armure effective avant contact en entrant dans le rayon, et le reach grandit (punit l'approche tardive). DOCTRINE consensus : Maladus en anchor avant = punit l'approche + multiplie le burst des alliés sur tout ennemi qui dive sa ligne ; côté adverse, ne pas feeder son armure dans le rayon (kite/ignore le mur Death Guard). [self-play consensus, seed 80085]

---

## 2. Units CHAOS (kits & interactions — faits neutres)

> Description objective du kit (vaut quel que soit le camp qui la joue). Le « quoi
> faire pour/contre » est doctrine générale (skill §6/§7).

- **Kharn (worldKharn, move3 mêlée)** — `KillMaimBurn` (actif range 2, chaîne multi-hits qui
  « prioritise kills » : Pierce → Eviscerate même cible jusqu'au kill → Plasma range-2). `RapidAssault`
  (+1 move jusqu'à sa 1ʳᵉ attaque ; +dmg). `TheBetrayer` (si a tué un ennemi ce combat → au **DÉBUT de
  chaque tour de Kharn**, auto-move jusqu'à 2 hex vers l'unité la plus proche puis **4× Eviscerate
  Pierce** sur un adjacent ; privilégie les ennemis mais **frappe un ALLIÉ si aucun ennemi à portée** ;
  **+2ᵉ attaque 4× Eviscerate après chaque normale**).
  **Quirk-clé : une fois « amorcé » par un kill, Kharn devient une menace récurrente garantie de 4
  hits/tour SANS action dépensée** (snowball move+4-hit/tour, vérifié). `BlessingsOfKhorne` (+dmg/−Psychic
  cumulé par kill mêlée). `FinalJustice` (à la mort : 1 attaque normale, sauf Overkill). **Pas Resilient.**
  Stun neutralise sa burst un tour. (cf. gameconfig --ability KillMaimBurn / --trait TheBetrayer)
  `▸ Tac: rôle=carry · menace=high · counter=le tuer AVANT son 1er kill (TheBetrayer non-amorcé = juste une normale absorbable ; amorcé = snowball + BlessingsOfKhorne) ; ranged/délai ; pas Resilient → tout K! franc le défait hors-FJ ; ⚠ OVERKILL STRICT pour nier FJ/TheBetrayer death-riposte = dégât **>2× PV restants** (vécu seed 98001 : finish NON-overkill ratio 1.6× → TheBetrayer 4× Eviscerate a FIRE) ; ⚠ NE PAS finir Kharn avec un de mes héros forward (deep-finish → focus-killé) — préférer l'auto-Grot/une unité shallow, OU le laisser non-amorcé à bas PV (TheBetrayer dort sans kill) [n=2]`
  `▸ Tac (n+1 dive-punish, seed 70060 W) : confirmé tué EN RÉACTION sur son dive AVANT son 1er kill = TheBetrayer JAMAIS armé → réduit à une normale absorbable, snowball mort-né. Un mur de réaction « hold-baits-the-dive » (Re'vas EarlyWarningOverride Overwatch-turret + Sarquael GrimRetribution held-OW) l'a one-turn-tué en réactions avec ZÉRO kill scoré — un ennemi all-melee est CONTRAINT de diver dedans. Pas Resilient → tout K! franc le défait ; overkill >2× PV restants si on finit au range (déni FJ/TheBetrayer, cf. §1 Overkill) [n=3, 98001/98002/70060]`
  `▸ Tac (À MOI — carry burst + death-riposte value, seed 70059 W mais COÛTEUX) : structure de KillMaimBurn (Pierce adjacent → Eviscerate même cible jusqu'au kill → Plasma range-2) fait que le K! du primaire SPILL le 3ᵉ hit Plasma sur la cible SUIVANTE (1 cast peut K! + splash 2 cibles). Death-riposte = grosse valeur quand il meurt ADJACENT à un anvil chunké : FJ normale (sauf Overkill) → TheBetrayer 4× Eviscerate déchargent ensemble (setup d'1-shot next turn). ⚠ LEÇON COÛTEUSE : committer Kharn (mon MEILLEUR carry) forward pour K! un ANVIL NON-engine l'a fait focus-killer = perte du carry ; un anvil-killable ne vaut PAS un carry forward → préférer tuer l'engine au range / sacrifier le corps le PLUS expendable, pas Kharn. SI Kharn doit mourir, l'orienter adjacent à un anvil chunké (death-riposte) plutôt que dans le vide [n=1, 70059]`

- **Abaddon (blackAbaddon)** — `Drachnyen` = self-heal-SET capé au max PV (set-à-valeur seulement si ≤ max, PAS un heal au-delà du max) + **PERMANENT pour le reste du combat** : après CHAQUE attaque normale mêlée, une 2ᵉ attaque Piercing auto sur un adjacent → **double-frappe mêlée à vie**. ⚠ « 2ᵉ attaque sur un ennemi DIFFÉRENT du primaire » = n=1 non prouvé, i2 ne dit que « an adjacent enemy unit » (cf. H21). `Resilient`. `TerminatorArmour` (1ʳᵉ attaque/tour subie réduite, **sauf Psychic/Direct**). `FirstAmongTraitors` buffe les Chaos alliés adjacents. (cf. gameconfig --ability Drachnyen --trait FirstAmongTraitors/Resilient/TerminatorArmour)
  `▸ Tac: rôle=anvil · menace=high · counter=RANGED multi-source floor-then-finish — Resilient floor tout hit létal non-overkill à 1 HP, un 2ᵉ hit DEPUIS 1 HP = kill propre ; PRÉFÉRER le ranged pour finir (ne PAS le mêler librement : Drachnyen est une riposte OFFENSIVE, chaque normale mêlée d'Abaddon génère une 2ᵉ attaque 3-hit → meleer dedans = absorber la double-attaque) ; Psychic/Direct bypasse TerminatorArmour ; FirstAmongTraitors devient quasi-INERTE si son bénéficiaire Chaos adjacent principal meurt → le démoter et le laisser pour la FIN (vécu seed 70053) ; priorité APRÈS les engines/le duo OW (vécu seed 95000 : a survécu tout le match faute de focus) [n=2, 95000/70053]`
- **Corrodius (deathBlightbringer, move2)** — `ContagionsOfNurgle` (aura −armure aux ennemis, **s'étend r1→r2→r3 par round**). `Poxwalkers` (actif : **summon** Poxwalkers attaquant direct). `CursedPlagueBell` (Chaos alliés dans l'aura +1 move ; **Psykers ENNEMIS dans l'aura s'auto-blessent à chaque hit Psychic**). `Resilient`. (cf. gameconfig --ability Poxwalkers --trait ContagionsOfNurgle/CursedPlagueBell)
  `▸ Tac: rôle=control/summoner · menace=med (tank LENT move2 Resilient : menace surtout POSITIONNELLE/attrition) · ⚠ **COÛT PSYKER** : un Psyker À MOI dans son aura s'auto-blesse à CHAQUE hit Psychic (scale niveau) → BUDGÉTISER ce self-damage avant de spammer du Psychic dans l'aura ; idéalement frapper depuis HORS aura ou le tuer/en sortir (vécu seed 70005) ; ⚠ ses Poxwalkers finissent un Resilient floored à 1 (un hit summon de 1 dmg tue) · counter=Resilient → multi-hit (≥2)/Overkill ; move2 LENT → kitable ; pas une priorité de kill devant engines/carries · ⚠ **n+1 CONTRIBUTING ROOT CAUSE (seed 70061) — un Resilient 12k JAMAIS COMMENCÉ À CHIPER = garanti un-finished au round cap** : laissé sitting-alive comme un clock → cap round-10 atteint (mutual wipe → no-winner) Corrodius encore plein. NUANCE vs 70054 : « laisser pour la fin » ne vaut QUE s'il n'y a PAS de hard round cap ; AVEC cap, un anvil Resilient 12k doit être COMMENCÉ tôt (grind round 5-6) sinon il devient le clock qu'on perd. Le kiter/ignorer indéfiniment est une LOSS si le board ne se ferme pas avant le cap [n=4, 96001/70005/70054/70061]`
- **Macer (worldJakhal, move3 mêlée)** — `JakhalStimms` (actif : multi-hit + splash, **−25% PV du lanceur**, **ne finit PAS son tour**). `Skullsmasher` (+dmg / 10% PV manquant → plus fort à bas PV ; + Stun si a déjà tué). `BlessingsOfKhorne`, `Resilient`. (cf. gameconfig --ability JakhalStimms --trait Skullsmasher)
- **Pestillian (deathPutrifier, move2 mêlée)** — `PutridExplosion` (**explose à la mort**, Toxic aux adjacents sauf Death Guard). `FoulInfusion` (actif : +Toxic aux Chaos de l'aura ce round+suivant, puis attaque). `ExplosiveMaladies` (buff Blast aux adjacents ; cibles tuées par ces attaques **toujours overkillées**). `ContagionsOfNurgle`, `Resilient`. (cf. gameconfig --ability PutridExplosion/FoulInfusion --trait ExplosiveMaladies)
  `▸ Tac: rôle=anvil · menace=med (menace surtout POSITIONNELLE : aura Contagion −armure + explosion Toxic à la mort + buff Blast adjacents) · counter=le tuer au RANGED (PutridExplosion = Toxic AoE aux adjacents → ne JAMAIS coller mes unités) ; Resilient → multi-hit (≥2) ou Overkill (sinon floor à 1, le coup final ne déclenche pas l'explosion) ; move2 lent → kitable (vécu seed 96001) [n=1]`
  `▸ Tac (n+1 ContagionsOfNurgle attrition CONFIRMÉ self-play consensus, seed 80000) : aura live = **ArmorReduction1** (R1-2=−1, R3-4=−2 armure) observée des DEUX côtés (A theirs + B mine, FixedArmor_Modification négatifs confirmés). DOCTRINE : **ne JAMAIS avancer des melee-units dans la portée de l'aura sans plan de kill-en-un-tour** — l'attrition est garantie dès qu'une unité ENTRE dans la portée ; reculer dès que l'aura couvre sa tuile. [self-play consensus, seed 80000]. [n=2, 96001/80000-sp]`
- **Wrask (worldTerminator, move2 mêlée)** — **brawler / ANVIL Khorne, PAS un assassin.** `BloodyFury` (actif : Chain à un adjacent **+1 hit par fois que Wrask a été ATTAQUÉ ce combat**, max 8 ; surplus aux adjacents, priorise les kills) → **il VEUT être focus** : sa frappe **scale avec les coups subis**. `WrathfulDevotion` (passif : shield à lui + Chaos adjacents, **à l'arrivée de deep-strike OU à chaque kill mêlée**, 1 round). `BlessingsOfKhorne` (+dmg / −Psychic subi **par kill mêlée**, cumulé). `RapidAssault` (+1 move jusqu'à la 1ʳᵉ attaque). `TeleportStrike` (deep strike = **outil de POSITIONNEMENT**, pas un snipe : drop sur tout hex libre non-adjacent, non-ciblable jusqu'à ce qu'il agisse), `TerminatorArmour`, `Unstoppable` (cf. §1). **Doctrine : le déployer TÔT au FRONT** comme anvil (encaisse le focus à la place des fragiles) + empiler hits-subis (BloodyFury) et kills mêlée (Khorne + re-shield). **NE PAS le planquer** « pour assassiner » : anti-synergie totale — caché = 0 hit subi = BloodyFury à **1 coup** (vécu rematch seed 33182 : sorti tard → frappe minable). (cf. gameconfig --ability BloodyFury/TeleportStrike --trait WrathfulDevotion/BlessingsOfKhorne)
  `▸ Tac (WrathfulDevotion = BURN-avant-HP, [self-play consensus, seed 80002 — team2 W]) : insight non-déductible = le shield WrathfulDevotion (TurnsLeft=1) absorbe TOUT le chip (drones/TG ont tapé 0-166) → chipper dedans est gaspillé. DOCTRINE vs Wrask-ENNEMI : NE JAMAIS chipper dans le shield ; le BURN d'un coup throwaway (qui dépense AUSSI la 1ʳᵉ-réduction TerminatorArmour du MÊME corps — double-spend), PUIS piler les attaquants full-damage le MÊME tour pour le finir (vécu : Azkor a brûlé ~2818 du shield + la réduction, drones suivants 2672-4009 chacun = dead). Le shield se re-arme à chaque arrivée deep-strike OU kill mêlée → ne pas lui laisser un round pour le re-trigger. ⚠ COROLLAIRE : « finir » Wrask pendant son deep-strike le REVEAL ET trigger WrathfulDevotion (+shield) → préférer le burst quand il est DÉJÀ révélé, ou accepter le shield et le burn dans le même tour. Les 2 sides concordent (A mine = finir le deep-striker a trigger le shield ; B theirs = burn-then-finish). (cf. gameconfig --trait WrathfulDevotion/TerminatorArmour) [self-play consensus, seed 80002]`
- **Archimatos (blackPossession, move3, Psychic 100 NoBlocking)** — summoner. Psychic NoBlocking = **ignore armure/block**. `Incursion` (actif r2) : spawn 1 Bloodletter à la fois sur la cible, **jusqu'à 6 TANT QUE la cible n'est pas tuée** (+ reste à r2 + a un hex libre adjacent). **C'est un FARM de corps, pas un kill** : pour décrocher les 6 (≈ **17k PV de board**), viser un **gros-PV en ESPACE DÉGAGÉ** qui survit aux 6 spawns ; sur du **chaff/bas-PV la cible meurt après ~2 spawns → seulement 2 Bloodletters** (vécu seed 67827). **Éviter un Resilient comme cible** (un Bloodletter overkill le 1-PV → défait → la boucle stoppe). ⚠ **Ne pas farmer sur un tank à AoE/aura de zone** (Typhus, Corrodius) : les Bloodletters collés se font **AoE en retour** → choisir un sponge sans AoE, ou accepter le trade. `Possession` (passif) : kill **mêlée** → Bloodletter dans le hex de la victime ; kill **ranged** → Blue Horror → donc **finir au ranged = +1 corps gratuit**. ⚠ **Possession ne fire que quand Archimatos est le TUEUR** (l'acteur), PAS quand il est la VICTIME : le tuer LUI avec MON unité = **zéro Possession body** → priorité = l'éliminer T1-T2 avant qu'il summon. `Psyker`, `LetTheGalaxyBurn` (cf. §1). (cf. gameconfig --ability Incursion --trait Possession/Psyker)
  `▸ Tac: rôle=engine · menace=high (summon-farm Bloodletters + body-par-kill) · counter=le tuer AVANT son PREMIER cycle de summon (T2 au plus tard) AVEC mon unité (il est la victime → AUCUN Possession body spawné) ; soft (pas Resilient), Psychic NoBlocking mais base faible → focusable T1-T2 (vécu seed 67827 ; 96002 éliminé T2 AVANT tout summon ; 70008 one-shot T2 pre-summon ; 70053 one-shot EN TANT QUE VICTIME → ZÉRO Possession body confirmé live + breaking-the-summoner-cheaply = pas de body spawné) [n=4, 96002/70008/70053]`
  `▸ Tac (À MOI — summon-engine + double-hit normal, seed 70059 W) : les Bloodletters d'Incursion SCALENT au-delà du tooltip (level/rarity) et auto-attaquent la cible AU SPAWN (hit immédiat) → utiles comme chair-à-trade/écran. ⚠ NE PAS les summoner pour qu'ils divent dans des anvils Resilient/TermArmour (valeur limitée à du chip) — préférer un hex où ils ÉCRANENT ou farment un sponge. Sa NORMALE ranged = bursts à 2-hits : LetTheGalaxyBurn (extra-hit) + PsykerExtraAttack splash à un adjacent de la cible (a contribué à overkill un Resilient). USAGE À MOI = soft Psyker NoBlocking → garder shallow+écrané (c'est MON engine fragile), ouvrir Incursion sur un sponge, finir un Resilient avec son double-hit (Pierce100 bypasse TermArmour) [n=1, 70059]`
  `▸ [self-play consensus, seed 80001] Incursion = BOARD-FLIP de SALVAGE (ressuscite un combat PERDU) + kill-not-chip confirmé owner-W/victim-L sur le MÊME match.` INSIGHT non-déductible cross-confirmé des DEUX sides : (a) **côté À MOI** — un seul cast `Incursion` sur un carry Resilient depuis une tuile non-mouvante a chain-killé la cible ET flood 5 Bloodletters = flip d'un 2v3-PERDANT en 7v2-gagnant → c'est le **comeback-engine ultime quand on est behind-on-bodies** : viser le carry Resilient ennemi (la chain le grind past le floor 1-HP) tant qu'il a un hex libre adjacent. (b) **côté ENNEMI** — B a PERDU en laissant Archimatos à 909 HP (chip non-létal) + en poussant son meilleur anvil forward pour le faire ; le flood l'a one-shot. Confirme H02 « kill garanti CE tour ou HOLD total » des DEUX perspectives : ne JAMAIS committer un corps pour un chip non-létal sur Archimatos (la normale max de l'attaquant < HP d'Archimatos = ZÉRO kill dispo → garder en screen, attendre un kill multi-source garanti). (cf. gameconfig --ability Incursion, doctrine §6 summon-engine) [self-play consensus, seed 80001]`
- **Abraxas (thousInfernalMaster, Thousand Sons, ranged r2 + mêlée, Psychic Pierce100 NoBlocking)** — caster/summon-engine. `MasterOfTheTutelaries` (actif) : cible un **HEX LIBRE adjacent** à Abraxas (PAS un ennemi → `--target` ennemi renvoie `mutated=false` ; cibler via `--to col,row`) ; summon **1 Pink Horror** immédiatement, PUIS jusqu'à fin de tour, **CHAQUE fois qu'un ennemi subit du Dégât Psychic, summon 1 Screamer**. Les summons **attaquent immédiatement** une cible à portée mais **ne peuvent pas se déplacer** ce tour. → coupler avec une chaîne de dégâts Psychic cascade les summons (vécu seed 96000 : 1 PinkHorror + 2 Screamers ont fourni les kills DÉCISIFS). Trait `Psyker` (cf. §1) : sur une **attaque RANGED normale uniquement**, splash %dmg à un ennemi ALÉATOIRE adjacent à la cible. Psychic NoBlocking = ignore armure/block. (cf. gameconfig --ability MasterOfTheTutelaries --trait Psyker)
  `▸ Tac: rôle=engine · menace=high (summon-cascade via dégât Psychic + Psyker splash multiplie les hits Psychic → snowball de Screamers) · counter=le tuer TÔT avant qu'il monte une chaîne Psychic ; soft (Psychic NoBlocking mais base fragile, PAS Resilient) → un burst franc le défait, et un assassin anti-Psyker le chunke en UN hit puis finition triviale = réponse propre vs Abraxas-ENNEMI (vécu seed 98001) ; à MOI = engine de réaction décisif (MasterOfTheTutelaries + Psyker splash = burst de réactions massées qui finit les wincons adverses, vécu seed 96000 ; ranged-finish via Psychic = bypass armure + free body si Possession-class) ; ⚠ re-confirmé engine SOFT défait par une CHAÎNE DE RÉACTIONS (seed 70005 : Abraxas-ENNEMI tué en réaction quand il a dive adjacent — MasterOfTheTutelaries JAMAIS cast, mort avant ; un seul gros hit de réaction le défait ; seed 70006 : nier ses cibles Psychic l'empêche d'escalader, WeaverOfFate jamais armé car jamais 3+ de mes units prenant du Psychic) ; ⚠⚠ **NE JAMAIS CHIPER NON-LÉTALEMENT (seed 70052 triggered-against-me)** : Abraxas-ENNEMI chippé NON-létalement a CASTÉ MasterOfTheTutelaries = board-flip qui a scellé la loss. Pas de seuil de PV : tout Abraxas survivant cast → un poke mono-source qui ne peut pas one-shot est strictement PIRE que le hold (« kill CE tour garanti ou hold total pour dénier le trigger », cf. doctrine-learned §6 summon-engine) [n=5, 96000/98001/70005/70006/70052]`
  `▸ Tac (n+1 kill-not-chip APPLIQUÉ, seed 70060 W) : ✅ règle kill-not-chip RESPECTÉE = ZÉRO board-flip — Abraxas-ENNEMI (soft, no-Resilient) tué en UN tour T3 via un burst multi-source GARANTI (total vérifié > HP AVANT de committer) → erasé AVANT tout cast = AUCUN Pink Horror/Screamer. Contraste positif net vs 70052 (chip non-létal → board-flip). PLAY confirmé : lead avec un nuke ranged (Supercharge no-move = HeavyWeapon +dmg) sur l'engine soft, puis séquencer 2 normales melee pour garantir le kill le MÊME tour [n=6, 96000/98001/70005/70006/70052/70060]`
  `▸ [self-play consensus, seed 80097]` **À MOI — cascade SELF-FEEDING via InfernalPacts (1 cast → 3 corps).** Confirmé des DEUX sides (A mine, B theirs). Un seul cast de MasterOfTheTutelaries a produit **Pink Horror + 2 Screamers** parce que les summons **auto-attaquent au spawn**, et leurs auto-attaques infligent du **dégât Psychic** (`InfernalPacts` ajoute un hit Psychic aux ranged Chaos adjacents) → RE-déclenche la clause « 1 Screamer par event Psychic » → **cascade auto-amorcée même SANS chaîne Psychic externe pré-arrangée** (le moteur se nourrit de ses propres summons). ⚠ **les summons ont leur action DÉPENSÉE par l'auto-attaque au spawn → ils ne peuvent PAS agir à nouveau ce tour** (re-cast normale id-69 sur un summon fraîchement spawné = mutated=False no-op silencieux). DOCTRINE À MOI : le burst de cascade est haut-tempo MAIS éphémère — les Screamers spawnés forward sont vulnérables à la Possession (Thaumachus) et meurent vite sans convertir ; ne pas committer la cascade près d'un Thaumachus vivant, compter sur le chunk immédiat plutôt que sur la persistance des corps. (cf. gameconfig --trait InfernalPacts) [self-play consensus, seed 80097]
- **Ahriman (thousAhriman, move3, Flying, Psyker)** — `Doombolt` (actif Ranged r2, Psychic **Pierce100 + NoBlocking = ignore armure/block**) : hits **répartis ÉQUITABLEMENT sur TOUS les ennemis dans 2 hexes** → frappe multi-cibles (overkill une cible chunkée ET softening d'un voisin dans le même cast), +1 hit/hex En Feu, et **se recharge** si Ahriman tue avec son tir normal après l'avoir déjà utilisé. `WeaverOfFate` (tout tour où **3+ ennemis** subissent du Psychic → Ahriman fait le dégât **MAX** sur toutes ses attaques/abilités ce tour ; un AoE Psychic multi-cibles peut s'auto-armer). `PsychicStalk`, `Psyker`. ⚠️ Dans une **aura Nurgle (Corrodius CursedPlagueBell)** il s'auto-blesse à chaque hit Psychic → un Doombolt 3-hit = gros self-damage (vérifié seed 91008 : tué cheap ainsi). Le tuer tôt = nuke armor-ignore neutralisé. (cf. gameconfig --ability Doombolt --trait WeaverOfFate/Psyker)
  `▸ Tac: rôle=engine · menace=med · counter=Psyker fragile (no-Resilient) = 2ᵉ engine de snowball Psychic (Doombolt armor-ignore AoE + WeaverOfFate) → le tuer TÔT ; un anti-Psyker le delete proprement ; ⚠ ne PAS deep-dive pour le chasser — laisse-le venir : s'il dive une ligne groupée, le free-kill arrive en RÉACTION (vécu seed 70002 : KILL GRATUIT en réaction quand l'Ahriman ennemi a dive) [n=1, 70002]`

- **Tarvakh (worldExecutions, mêlée snowball carry)** — `MurderousSwing` = AoE à TOUS les adjacents, MAIS le gros bonus dmg ne s'applique QUE si le cast touche EXACTEMENT 1 ennemi (toucher 2+ troque le bonus contre le spread). ⚠️ usage-unique/no-refresh observé live (n=1, H13) — pas dans gameconfig. Snowball-engine : `BlessingsOfKhorne` (+dmg / −Psychic subi par kill mêlée), `TrophyTaker` (+dmg vs cibles ≤50% PV), `RapidAssault`. **Pas Resilient → fragile au focus réaction.** (cf. gameconfig --ability MurderousSwing --trait BlessingsOfKhorne|TrophyTaker)
  `▸ Tac: rôle=carry · menace=high — **CRITICAL si TwistedScience-pumped** (un Hollan/Biophagus le pompe à ~12.5k) ; snowball par kill + MurderousSwing AoE adjacent · counter=lui NIER les kills (casse le snowball) + ne JAMAIS laisser une de mes unités tomber ≤50% près de lui (TrophyTaker) ; fragile à la réaction massée (pas Resilient) SI on peut l'atteindre — mais derrière un anvil (Angrax) il devient un mur intouchable pumpé → focaliser le PUMPER (Hollan) plutôt que de chiper un Tarvakh déjà pumpé ; ✅ **NON-pumpé = chunk-killable AVANT son 1er kill** : chunk-kill dans un burst AVANT qu'il score un seul kill = snowball mort-né [n=3, 70009]`
  `▸ Tac (n+1 NON-pumpé chunk-killable, seed 70060 W) : confirmé n+2 — AUCUN pumper présent (pas de Hollan/WarHowl) → resté à base = chunk-killable, PAS le mur pumpé. Tué dans mon mur de réaction (OW + OW finish) AVANT tout kill (déni BlessingsOfKhorne/TrophyTaker) ; pas Resilient → meurt à une réaction massée quand l'IA all-melee le force à diver. RÈGLE recon = COMPTER les pumpers adverses (Hollan/Ragnar) : aucun → demote Tarvakh de CRITICAL à high-killable [n=4, 97001-pumped/93001/70009/70060]`
- **Adamatar (emperKakophonist, mêlée/caster)** — `DoomSiren` (seul actif) : Direct **Pierce100** (ignore l'armure, ex. TerminatorArmour) à un ennemi adjacent + jusqu'à 2 autres ennemis **ADJACENTS À LA CIBLE** (PAS au lanceur, **splash target-relative confirmé**) → positionner la cible prime au milieu d'un cluster. Chaque ennemi **Overkillé par DoomSiren** donne +1 hit perma aux attaques normales d'Adamatar le reste du combat. ⚠️ probablement usage-unique (no-cd, H13 — vécu seed 70002 : resté [indispo] après son unique usage T1). Le Pierce100 traverse trivialement l'armure d'un anvil (TerminatorArmour) = chunk-2-corps gratuit (fragile primaire + anvil voisin en collatéral). (cf. gameconfig --ability DoomSiren)
  `▸ Tac: rôle=control · menace=med · counter=ne PAS clusterer mes unités adjacentes à un même hex (DoomSiren = Direct Pierce100 AoE adjacent, ignore armure ; splash target-relative) ; ObsessiveAnnunciation aura = +dmg ranged subi aux adjacents ; pas de revive/FinalJustice → finisher trivial une fois chunké · si à MOI : lead DoomSiren sur un fragile collé à un anvil/cluster → splash l'anvil GRATIS (bypass armure), positionner Adamatar adjacent pour que son aura +ranged feed mes kills ranged suivants ; ⚠ côté ENNEMI dans une compo all-ranged = ObsessiveAnnunciation +ranged aux adjacents AMPLIFIE le focus du cluster (le vrai danger ≫ DoomSiren ici) ; seul diveur melee de la compo mais non-décisif quand le cluster ranged fait le killing [n=3, 70002/70052]`
  `▸ Tac (n+1 soft-vs-melee, seed 70055) : PV élevés mais AUCUN Terrifying/Parry/Resilient → SOFT à un carry mêlée tanky (chunk-then-K! propre) ; ne PAS clusterer mes unités face à son DoomSiren AoE (Direct Pierce100) ; à traiter en cible de chunk-and-finish accessible — c'est UN des soft autonomous threats à tuer cheaply (avec Yazaghor/Godswyl) AVANT de buter sur le counter-engine (Atlacoya/Deathleaper) [n=4, 70002/70052/70055]`
- **Volk (blackObliterator, Black Legion, ranged r3, HeavyRound Pierce55)** — `FrenziedFiring` (actif r3) : **AoE** = 1 Heavy Round à la cible primaire ET à **TOUS les ennemis adjacents à elle** (cluster-softener) ; SÉPARÉMENT, score des hits EN PLUS sur la **cible primaire SEULEMENT**, un par hex libre autour d'elle (max 10 hits) ; les **hits bonus de FleshmetalGuns sont scorés contre CHAQUE ennemi touché** (i2-confirmé seed 70006). → viser un ennemi forward au CENTRE d'un cluster serré pour étaler le dmg sur 2-3 unités (vérifié live : 3-target value qui casse un summon-engine + chip l'anvil voisin + nie le snowball simultanément). `LetTheGalaxyBurn` (trait, confirmé carte) : chaque attaque a une **chance d'un hit en plus** + **Despoiled Ground** (hit en plus auto, sans Despoiled, si la cible est déjà sur un effet de hex). HeavyRound **Pierce55 = fort vs armure** ; HeavyWeapon : +dmg si Volk n'a PAS bougé ce tour. (cf. gameconfig --ability FrenziedFiring --trait LetTheGalaxyBurn)
  `▸ Tac: rôle=carry · menace=high (ranged r3 AoE carry = LE DPS qui ferme les kills : FrenziedFiring cluster-softener + LetTheGalaxyBurn extra-hits + HeavyWeapon +dmg si immobile + Daemon block → multi-hit/tour ; Daemon block + BigTarget = tanky) · counter=si ENNEMI : ne JAMAIS présenter un corps isolé dans son arc r3+move2 (FrenziedFiring score +1 hit par hex LIBRE adjacent à la cible → viser-l'éviter dans un ESPACE OUVERT) ; le laisser pour la FIN (tanky Daemon/BigTarget) et nier ses cibles ; move2 LENT → kitable mais frappe à r3 donc « back » relatif ; si à MOI, l'utiliser depuis une tuile shallow HORS arc Overwatch armé pour chunker une grappe forward — NE PAS le pousser au contact [n=2, 93000/70005]`
- **Shiron (emperNoiseMarine, Emperor's Children, ranged r3 + mêlée, HeavyWeapon)** — **carry ranged finisher tardif.** `ExcruciatingFrequencies` (actif, profile **Blast Pierce15** `HitsMultipleMembers`) = **ligne AoE de 3 hexes en ligne droite (1 des 6 directions)**, tirée À TRAVERS la cible visée ; touche **CHAQUE ENNEMI** sur les 3 hexes (les alliés sur la ligne NE sont PAS touchés) et les **Suppresse** ; **+30% Crit Chance PAR unité sur les hexes affectés** → multi-crit facile (i2 vérifié seed 95001 : double CRIT en un cast). **Attaque normale ranged = Eviscerate Pierce50 r3 multi-hit** → finisher safe d'un isolé à distance, zéro exposition de mouvement (vérifié seed 70001 : a fini un Mataneo Pinned depuis la tuile courante). Passif `SuppressiveFire` (tout ennemi touché par son ranged devient Suppressed)
  + `TerrifyingCrescendo` (passif : ses attaques RANGED gagnent +dmg par fois qu'il a Overkillé OU aurait Suppressé un ennemi, cap 6 ; i2-vérifié) → auto-snowball : SuppressiveFire feed le compteur, ExcruciatingFrequencies suppresse+crit, HeavyWeapon (+ranged s'il ne bouge pas) → **late-game ranged finisher** capable de gros K! depuis sa tuile sans bouger. ⚠ le sous-claim « un crit ÉTEND la durée de ThrillSeekers » est **NON supporté par i2** (ThrillSeekers se re-trigger par tour sur dégât-subi/cible-full-HP, PAS sur crit) → cf. H22, ne pas s'y fier. **Doctrine : le garder STATIONNAIRE (HeavyWeapon) en arrière, laisser le compteur Crescendo monter, l'utiliser comme finisher de fin de partie sur l'engine adverse.** (cf. gameconfig --ability ExcruciatingFrequencies --trait TerrifyingCrescendo|SuppressiveFire)
  `▸ Tac: rôle=carry · menace=high (finisher ranged tardif : TerrifyingCrescendo stacke par Overkill-ou-Suppress, cap 6 ; ExcruciatingFrequencies = ligne AoE multi-crit ; PAS de Resilient/FinalJustice) · counter=si ENNEMI, c'est LA menace standoff la plus dangereuse — le tuer TÔT avant que le compteur Crescendo monte (soft, fragile) ; **ne JAMAIS laisser un fragile STATIONNAIRE dans sa portée r3+move** (vécu seed 70009 : a deleté mon Patermine forward en un tour ranged) ; fermer le gap comme un mur HP-screené et le meleer (tué proprement sur 2 tours une fois isolé 4v1) ; si à MOI, le garder STATIONNAIRE en arrière, réserver son K! stacké pour l'engine adverse (vécu seed 95001 : a one-shot une cible full-HP à r3 sans bouger après stacks) [n=2, 70009]`
- **Haarken « Haarken Worldclaimer » (blackHaarken, Black Legion, Chaos, move4 Flying, mêlée burst)** —
  `HeraldOfTheApocalypse` (actif mêlée) : **frappe DEUX cibles en un cast** — l'**ennemi adjacent** ciblé ET **un ennemi directement DERRIÈRE la cible** ; les **DEUX** reçoivent le debuff **+dmg de la prochaine attaque** subie (i2 « Affected enemies », pluriel = les deux). Double-target confirmé (vécu seed 98004 : a touché 2 unités alignées + posé le debuff sur les deux). → bloquer/tuer l'une des deux cibles supprime la moitié des dégâts ; aligner deux ennemis (cible + arrière) maximise le cast. `Terrifying` (réduit la mêlée subie → bypass = RANGED, §1). move4 + Flying = grosse portée d'engagement. (cf. gameconfig --ability HeraldOfTheApocalypse --trait Terrifying)
  `▸ Tac: rôle=carry · menace=high (burst mêlée double-target : HeraldOfTheApocalypse touche cible + l'ennemi derrière, +dmg debuff sur les deux ; move4 Flying = reach énorme) · counter=si ENNEMI, le tuer TÔT au RANGED (Terrifying ne protège que la mêlée) avant qu'il aligne mes 2 unités ; si à MOI, le chaîner APRÈS un mark Asmodai ExemplarOfHate (+dmg/hit team melee → burst amplifié, vécu seed 98004) sur une cible avec un ennemi derrière elle [n=1]`

---

## 3. Units IMPERIUM (kits & interactions — faits neutres)

- **Lucien (bloodDeathCompany « Death Company », Blood Angels, mêlée carry autonome)** —
  carry **focus-killer auto-pilote**. `Resilient` (coup létal non-Overkill → 1 PV ; cf. §1). `RapidAssault` (+1 move + bonus dmg). `VisionsOfHeresy` (**2ᵉ attaque GRATUITE r2 à chaque activation** ciblant *n'importe quel* ennemi ≤r2 — **i2 dit « an enemy within range 2 », PAS « the same enemy »** → la 2ᵉ attaque peut frapper une cible DISTINCTE de la normale → **double-finisher en une activation** si deux ennemis bas-PV sont tous deux à portée r2 ; + **+20% Piercing quand Lucien ≤50% PV** = double-attaque qui pierce mieux à bas PV).
  `BlackRage` (set à 50% PV, **auto-charge** puis devient un **auto-attaquant INCONTRÔLABLE** qui fonce sur l'ennemi le plus proche). → un **focus-killer autonome** : RapidAssault+VisionsOfHeresy = double-attaque, BlackRage le lance tout seul. **Vérifié live seed 70002** : chunké SANS que Resilient interfère (aucun seuil de défaite atteint) ; sa double-attaque VisionsOfHeresy a focus-killé un fragile ; puis BlackRage l'a auto-chargé dans mon cluster groupé → tué EXACTEMENT en réaction multi-source (multi-source bat Resilient). (cf. gameconfig --ability VisionsOfHeresy --trait Resilient|RapidAssault|BlackRage)
  `▸ Tac: rôle=carry · menace=high (autonome : Resilient + RapidAssault double-attaque + VisionsOfHeresy 2ᵉ attaque gratuite +pierce ≤50% + BlackRage auto-charge incontrôlable = focus-killer self-driving) · counter=multi-hit/multi-source pour battre Resilient (une source floor à 1, la suivante tue) ; ⚠ overkill si je le tue ACTIVEMENT ; MEILLEUR counter = le laisser diver une ligne groupée → reaction-kill (vécu seed 70002 : tué en réactions, ZÉRO action offensive dépensée — BlackRage le force à charger mon cluster) ; il a tué un fragile via la double-attaque → garder mes fragiles HORS de sa reach (move3+RapidAssault=move4, r2) [n=1, 70002]`
  `▸ [self-play consensus, seed 80085]` **BlackRage n+1 — set à 50% PV + auto-charge incontrôlable confirmé par les DEUX sides.** B (propriétaire) observe le HP-halving + statut auto-attaquant incontrôlable ; A (adversaire) observe le HP-halving + Lucien qui drifte/auto-charge ensuite. Une fois BlackRage cast, Lucien n'est plus pilotable et fonce tout seul → sur le FLANC, isolé, c'est un kill facile au multi-hit (Resilient floored à 1 par le 1er hit, fini par le suivant). Doctrine : ne pas chasser le carry auto-pilote ; le peeler/laisser diver puis le mopper isolé. [self-play consensus, seed 80085]
- **Vexilus/Aesoth (custoVexilusPraetor, move3 mêlée)** — `VexillaMagnifica` (actif : **STUN 2 cibles adjacentes** + dmg + le lanceur −66% dmg subi 1 round, cd2). `StandVigil` (alliés à portée 2 : +armure / +dmg non-normal ; étendu si un Custodes use un actif). `BigTarget` (alliés adjacents −1 hit ranged ; non déplaçable). `Resilient`. (cf. gameconfig --ability VexillaMagnifica --trait StandVigil|BigTarget|Resilient)
  `▸ [self-play consensus, seed 80085]` **VexillaMagnifica = outil de CONTRÔLE, pas finisher** : SINGLE-HIT Physical → ne tue PAS un Resilient (floor à 1). Valeur = double-stun (déni d'actions sur 2 ennemis adjacents — ex. couper une ability clé avant un focus-kill) + auto-protection Aesoth (−66%). Setup canonique : stun+chunk → un 2ᵉ anchor finit depuis tuile shallow. (cf. gameconfig --ability VexillaMagnifica)

- **Trajann (custoTrajann, move3 mêlée)** — `MomentShackle` = self-heal (scale niveau/rareté) + 1 round de Block buff + riposte 2× Bolter à chaque ennemi qui sort d'un hex adjacent. ⚠ **REPEATABLE = actif standard sur cd (~2 tours), PAS once-per-battle** (gameconfig : aucun champ charges/perBattle ; vérifié seed 70004 : heal-to-full un tour PUIS attaque/ré-heal au cd). `LegendaryCommander` (ennemi adjacent à un allié ayant usé un actif ce tour → +dmg subi ; bonus de hits aux Characters alliés si aussi adjacent à Trajann). `CrushingStrike` (+dmg mêlée normale **s'il n'a PAS bougé**). `Resilient`. ⚠ **`MartialKatah` = −dmg des attaques NORMALES subies SEULEMENT** ; les ACTIFS **bypassent** (clause à part : +dmg vs Summons). → **chip gâché** (heal+block annulent) : ne committer QUE des dégâts qui sécurisent un kill/Overkill.
  ⚠ **MUR STRUCTUREL self-healing (vérifié seed 70004)** : Resilient (floor à 1, sauf Overkill) **+** MomentShackle heal-to-full REPEATABLE sur cd **+** dmg/tour **+** MartialKatah (−normales) = un anvil qu'un roster **chip-only** NE PEUT PAS finir (se heal-to-full tous les ~2 tours ET out-damage le tank) → devient **wincon late de facto** une fois les screens tombés. Fenêtre de kill = **overkill multi-source en UN tour** pendant que MomentShackle est en cd, OU **Direct/Psychic** qui bypasse son block (ex. DoomSiren Direct Pierce100).
  ✅ **TUABLE EN UN TOUR — SÉQUENCE VÉRIFIÉE (seed 70005)** : la fenêtre EXISTE et a été exploitée. Pré-chunké par réactions le tour précédent, PUIS le tour suivant (MomentShackle en cd) : **Psychic normal** (Pierce100 + NoBlocking → bypass block ET MartialKatah) PUIS **actif multi-hit** (bypass MartialKatah qui ne réduit QUE les normales + bat Resilient floor-then-finish) = Overkill. La SÉQUENCE = chunk-par-réactions → Psychic-bypass-block → actif-multi-hit-finish, le MÊME tour, MomentShackle en cd. Contraste avec 70004/70007 (resté full, burst épuisé / écran jamais cassé) : la différence = avoir **RÉSERVÉ le burst Psychic** au lieu de le dépenser tôt. (cf. gameconfig --ability MomentShackle --trait MartialKatah)
  `▸ Tac: rôle=anvil · menace=critical (MUR self-healing : MomentShackle heal-to-full REPEATABLE sur cd + Resilient + dmg/tour + MartialKatah −normales → INKILLABLE par un roster chip-only/burst-épuisé = wincon late de facto une fois les screens tombés ; LegendaryCommander amplifie le focus équipe) · counter=NE PAS chiper (heal+block+Resilient annulent tout chip non-létal) ; KILL via (a) Direct/Psychic bypass-block (DoomSiren Pierce100) OU (b) overkill MULTI-SOURCE en UN tour pendant que MomentShackle est en cd, OU (c) RÉACTIONS/Overwatch massées (vécu seed 96002 : tué par 2 triggers Burchard Overwatch sans actions offensives ; vécu seed 70006 : tué EN RÉACTION — splash AoE + counter + finish — AVANT qu'il cast MomentShackle : Resilient ne sauve qu'1× → 1 HP, MomentShackle est CAST-ONLY no auto-trigger → un burst de réactions qui floor PUIS finit AVANT son action le tue sans self-heal) ; ⚠ RÉSERVER mon burst anti-block POUR LUI au recon (vécu seed 70004 : DoomSiren dépensé tôt → chip-only vs l'anvil = loss structurelle, gagné 4v1 mais pas pu le finir) ; si mon burst est dépensé/absent → FLAGGER la loss, ne pas grind ; ⚠ il est aussi le mur derrière lequel se cache un DOUBLE summon-engine (Isaak board-flip + Yarrick attrition) : NE PAS le chiper, casser ses ÉCRANS (les summon-engines) à la place (vécu seed 70007 : Trajann full tout le combat, mes Psychic chip annulé par MomentShackle → board flippé 3v12 avant toute fenêtre) ; ✅ **TUABLE confirmé (vécu seed 70005)** : pré-chunk réactions → Psychic Pierce100 NoBlocking → actif multi-hit Overkill, MÊME tour MomentShackle en cd = mur self-healing DÉTRUIT — la fenêtre existe SI on a RÉSERVÉ un burst Psychic/Direct + un actif multi-hit (cf. §5bis) ; ✅ **2e fenêtre = RÉACTIONS PURES (vécu seed 70006)** : tué en réaction AVANT qu'il cast MomentShackle = n'exige PAS forcément un burst dédié si l'IA dive dans une ligne de réactions massées (Resilient floor 1× + MomentShackle cast-only → mort avant self-heal) [n=5, 96002/70004/70007/70005/70006]`
  `▸ Tac (n+1 à MOI = combo Resilient+MomentShackle recovery, seed 70060 W) : ✅ quand Trajann est dans MON roster, le combo Resilient + MomentShackle est une boucle de récup gratuite — Resilient sauve à 1 HP (floor, sauf Overkill), puis MomentShackle self-heal le ramène quasi-full le tour suivant (vécu seed 70060 : floored à 1 en avançant pour finir un engine → quasi-full + Block buff le tour d'après, zéro perte). MartialKatah −normales a aussi réduit les attaques adverses vs Trajann. → un corps forward Resilient+MomentShackle peut être committed un tour pour landa un kill d'engine guard-approuvé SANS le perdre (mais une ligne plus propre évite l'exposition forward — cf. journal mistake) [n=6, 96002/70004/70007/70005/70006/70060]`
- **Morvenn (adeptMorvenn, 9539, move3, ranged r3 + mêlée)** — `SanctorumMissile` (AoE Blast r3 — **faible vs armure**, cf. §1). ⚠️ **Le splash (sur TOUS les hexes adjacents à la cible) est POSITIONNEL, pas filtré ennemi → friendly fire** : touche MES propres unités adjacentes à la cible. i2 n'exempte QUE l'hex de Morvenn elle-même ; tout autre adjacent (allié inclus) est touché. **Ne jamais le tirer quand une de mes unités est adjacente à la cible** (même classe de risque qu'`Explodes`). `Explodes` (**friendly fire** : à la mort, % PV max Direct à TOUS les adjacents, cf. §1). `ActOfFaith` (+crit à chaque mort/kill d'un Imperial, reset au crit). `RighteousRepugnance` (mêlée normale +AoE). `Mechanical` (pas de heal, repair seulement). (cf. gameconfig --ability SanctorumMissile --trait Explodes)
  `▸ Tac: rôle=carry · menace=high (dealer ranged Blast r3 ×2 + splash adjacent friendly-fire + Explodes Direct à la mort + ActOfFaith crit-snowball) · counter=la tuer au RANGED/réaction sans coller mes unités à sa mort (Explodes friendly-fire — vécu seed 98004 : encaissé sur 2 units, survie OK ; tuée en réaction T3) ; HEAL-BLOCKable (Mephiston FuryOfTheAncients) pour nier un revive Healer adverse (Nauseous) ; Blast ≪ vs armure (SanctorumMissile pas un finisher) ; pas de Resilient → un burst franc la défait [n=1]`
- **Mephiston (bloodMephiston, 9537, move3, ranged r2 + mêlée, Psychic Pierce100 NoBlocking)** — Psychic **bypasse TerminatorArmour**. `Psyker` (attaque ranged normale → splash % à un ennemi adjacent à la cible ; **s'auto-blesse dans une aura Nurgle**, cf. Corrodius). `TheQuickening` (repositionnement r2). `Terrifying` (réduit les dégâts de **mêlée** subis — ⚠️ l'armor-ignore/perforant NE bypasse PAS Terrifying, ce n'est pas un mécanisme d'armure ; seul le **RANGED** le contourne). `RapidAssault`. ⚠ **`FuryOfTheAncients` = actif déclenché par le MOUVEMENT, PAS un passif** : après qu'il a bougé, 2× Psychic Pierce100 + NoBlocking à un ennemi adjacent ET un 2ᵉ ennemi adjacent à celui-ci ; **s'il ne bouge pas, auto-fire en fin de tour** → applique un **heal-block 2 rounds** : unités touchées ne peuvent être revives, heal, repair, ni restaurer leur PV (shut-down de `ToughToKill` / tout heal type Nicodemus). Fan sur **2 unités/cast** → peut nier tout un noyau de sustain vite. Le tuer tôt = nuke armor-ignore + déni de sustain.
  **Vérifié seed 93000** : chaque MOVE auto-fire 2× Psychic sur la chaîne adjacente + heal-block 2 rounds → traiter son **mouvement comme une AoE garantie** ; garder mes bas-PV/healer-dépendants hors de sa chaîne d'adjacence. **Confirmé seed 95002** : le heal-block frappe **TOUTE unité touchée par l'AoE** (la primaire ET le 2e adjacent), pas seulement la primaire (n=2). **Confirmé seed 70051** : la chaîne d'adjacence = primaire + 1 adjacent à la primaire (PAS rayon Mephiston) → a **coupé la regen `ToughToKill`** (un Dreir floored par Resilient n'a PAS remonté tant que le heal-block durait) → confirme que `ToughToKill` est un « heal » bloquable (cf. H44) et que la chaîne touche bien primaire + 2ᵉ adjacent (n=3). (cf. gameconfig --ability FuryOfTheAncients --trait Terrifying)
  `▸ Tac: rôle=carry · menace=critical (nuke armor-ignore Pierce100 NoBlocking bypasse TerminatorArmour+Terrifying + déni-sustain move-rider heal-block 2 rounds + shred un roster mêlée à distance) · counter=le tuer T1-T2 AVANT FuryOfTheAncients si ENNEMI (priorité 1 wincon — vécu seed 95002 : combiné à Makhotep a effacé Tarvakh, jamais défait faute de l'atteindre ; seed 70051 : LE wincon adverse, focus multi-source l'a tué T4 dès qu'il a dive, pas de Resilient → tout focus suffisant le tue franc) ; son heal-block coupe la regen ToughToKill/Nicodemus → tenir mes bricks regen-dépendants HORS de sa chaîne d'adjacence ; DaughterOfTheAbyss (Atlacoya) −Psychic aux alliés adjacents = insuffisant seul vs son output plein ; si à MOI, son move = AoE Psychic gratuite sur 2 cibles — chaîner le move-rider AVANT le normal, ne pas le laisser forward (Terrifying ne protège que la mêlée → focus-killable au ranged) [n=4]`
- **Yarrick (astraYarrick, 7530, move3, ranged r2)** — `SendInTheNextWave` (summon Cadian Guardsmen, **+1 par allié DÉFAIT** ce combat, **cap 5** ; apparaissent à r2 de la cible et **tirent immédiatement** au cast, Las r2). Snowball en moteur d'attrition au fur et à mesure que JE perds des unités → ne pas lui donner de kills faciles ; tuer ses summons ne le refill PAS (seules MES pertes le font). `Resilient`. ⚠ observé live (seed 95002, NON re-vérifié gameconfig) : un buff `SummaryExecution_BaseEffect` sur ses Guardsmen a disparu **immédiatement à la mort de Yarrick** → aura source-anchored probable, à confirmer. (cf. gameconfig --ability SendInTheNextWave)
  `▸ Tac: rôle=engine · menace=med (summon-engine d'attrition : SendInTheNextWave summon 2 Cadian Guardsmen +1 par allié DÉFAIT, cap 5 ; les Guardsmen alimentent le snowball + finissent les fragiles ; ⚠ LESSER engine — ne PAS lui dépenser mon tour si un board-flip engine (Isaak) est aussi sur le board et non tué) · counter=le tuer TÔT et AVANT d'accumuler mes défaites ; Resilient → MULTI-hit (BringerOfDespair 4+4 : 1er floor à 1, 2e tue depuis 1 — vérifié seed 95002 ; Sy-gex attaque NORMALE 4-HIT both KILL+OVERKILL en un coup — vérifié seed 70007) OU 2ᵉ source/Overkill ; sa mort retire le buff SummaryExecution des Guardsmen (re-observé seed 70007 : Attack_Modification stripé des 2 Guardsmen à sa mort = aura source-anchored probable, cf. H39) + roll BattleFatigue sur les Guardsmen adjacents (un a fui à sa mort, seed 95002) ; ⚠ en MIROIR (2 Yarricks sur le board, seed 98003) le throughput SendInTheNextWave DOUBLE = snowball encore plus rapide [n=3, 95002/98003/70007]`
  `▸ [self-play consensus, seed 80097]` **DÉCISIF comme WINCON late d'attrition contre un roster summon/Psyker fragile-au-front.** SendInTheNextWave casté **back-row SANS bouger (zéro exposition)** a flood le cap **+ burst** en UN cast → a flip un déficit de corps (5v7 → 8v4), puis focus-kill des engines ennemis en ordre = la W. ⚠ **PARADOXE de scaling confirmé live des DEUX sides** : le cap-5 du flood est ATTEINT en LAISSANT mourir ses propres unités (chaque allié défait = +1 Guardsman) → les pertes early ont MAXÉ le flood = le « comeback engine » se nourrit de l'attrition de son propre camp. A (about=theirs) le lit comme « the flood that out-bodied me once my heroes were depleted, scales with my dead allies so my late losses fed it ». DOCTRINE vs Yarrick-ENNEMI : le tuer AVANT que la course d'attrition n'arme le flood max ; ne PAS jouer une guerre d'usure longue contre lui (chaque mort, la sienne OU la tienne, le renforce). [self-play consensus, seed 80097]
- **Vindicta (adeptRetributor, Sisterhood, move3, ranged r2)** — passif **`FireOfAbsolution`** : à CHAQUE attaque ranged (normale OU `ArmoriumCherub`), splash Flame (Pierce25, OnFire) sur **TOUTES les unités ADJACENTES À LA CIBLE** + Fire sur chaque hex adjacent. ⚠️ **splash positionnel NON filtré ennemi → FRIENDLY FIRE** (pas d'exception lanceur/allié, contrairement à SanctorumMissile) : un cluster ennemi serré se punit lui-même quand elle tire, mais MES unités adjacentes à la cible sont aussi touchées. **Dégager mes unités de l'adjacence-à-la-cible avant tout tir de Vindicta.** Aussi `ArmoriumCherub` (4× Flame, ne termine PAS son tour) + `ActOfFaith` (crit-ramp à chaque mort/kill d'Imperial). Fragile 7029, Psychic-vulnérable. (cf. gameconfig --ability FireOfAbsolution --trait ActOfFaith)
  `▸ Tac: rôle=carry · menace=high (dealer Flame ranged : FireOfAbsolution splash + ActOfFaith crit-ramp qui scale sur les morts/kills Imperial) · counter=la tuer AVANT qu'elle empile ActOfFaith (chunk Psychic Mephiston + finisher mêlée) ; fragile/over-étend (vécu seed 97000 : poussée → tuée — mais elle a focus-killé mon Macer forward d'abord) ; ne PAS laisser une de mes unités adjacente à sa cible (FireOfAbsolution friendly-fire — confirmé du côté ENNEMI seed 70007 : Vindicta a tué son propre Neophyte + chunké son propre Aesoth en tirant sur un cluster serré → un Vindicta adverse se punit lui-même, et la mienne punit les MIENS adjacents à la cible) ; ⚠ **RE-CONFIRMÉ côté MIEN (vécu seed 70056 triggered-against-me)** : ArmoriumCherub + normale sur une cible alors que mes units étaient adjacentes → 2 splashes ont coûté ~3000 HP à mon Calandis ; DÉGAGER mes units de l'adjacence-à-la-cible AVANT tout tir de Vindicta [n=3, 97000/70007/70056]`
- **Arjac (spaceRockfist)** — `Foehammer` (Ranged Power, range 2, 1 hit, Pierce40) : inflige **Stunned** sur la cible jusqu'au DÉBUT du prochain tour d'Arjac → la cible garde son attaque NORMALE mais perd **TOUS ses actifs** (vérifié seed 97000 : Calgar stunné ne pouvait PAS user GauntletsOfUltramar) + réduite à 1 Movement ; Heal/Repair retire le Stun. ET **+dmg flat par Character (n'importe quel camp) défait ce combat** par-dessus sa base. Snowball en one-shot finisher quand le board s'amincit → le GARDER pour le mid/late game ; inutile T1. ⚠ observé **usage unique par combat** ([indispo] après un tir, n=1 — type cooldown engine, PAS dans gameconfig ; lire decisionView avant de re-committer). `Resilient`. **`AnvilShield`** : baseline = absorbe du dmg supplémentaire + couvre l'hex de l'attaquant en Glace à chaque Block ; **sous 35% PV** (OU si l'attaquant est sur un hex glacé) Arjac gagne **+Block chance** ET ice-**Stun** tout attaquant MÊLÉE dont il Block le coup. ⚠ **synergie clé avec Resilient** : une fois Resilient déclenché (floor à 1 PV), Arjac est par définition sous 35% → le mode renforcé d'AnvilShield s'active pour CHAQUE mêlée suivante → survie last-man dramatiquement allongée (vécu seed 97000 : heavy-blocks répétés, a tenu ~3 tours ennemis avant de tomber). (cf. gameconfig --ability Foehammer --trait AnvilShield)
  `▸ Tac: rôle=anvil/finisher · menace=high (Foehammer = Stun-lock l'actif d'une cible-clé 2 tours + finisher snowball +dmg/Character mort ; AnvilShield+Resilient = last-man dur à finir) · counter (usage à MOI) = réserver Foehammer pour locker l'actif d'un anvil/control adverse (vécu seed 97000 : a coupé GauntletsOfUltramar de Calgar) + finir un fragile une fois le board aminci ; ne PAS le compter pour percer un mur double-armure (Power Pierce40 vs MkXGravis) [n=1]`
  `  ▸ Tac (n+1 Foehammer = both-teams-count CONFIRMÉ self-play consensus, seed 80000 run #5) : le +dmg/Character compte les morts des **DEUX camps** (gameconfig « each Character that has been defeated in this battle », sans restriction de camp) → **le snowball coupe dans les DEUX sens : tuer des héros ENNEMIS arme AUSSI l'Arjac ennemi**. Vécu : après 2 kills, Foehammer ennemi est devenu un **one-shot + Stun à range 2** sur tout fragile → a delete un Atlacoya. ⚠ cross-validé les 2 sides (A theirs : « became a one-shot after my 2 kills » ; B mine : « ramp partially applied — 2 dead Characters were on MY side, confirming both teams count »). DOCTRINE : en late-game, dès que des Characters sont morts (peu importe le camp), garder TOUS mes fragiles HORS de la r2 de l'Arjac ennemi — kiter (l'Arjac est lent move2). [self-play consensus, seed 80000 run #5]`

- **Jaeger « Brother Jaeger » (templChampion, Black Templars, mêlée)** — verrou total d'une pièce-clé.
  `MartialSuperiority` (passif COUNTER) : punit tout engagement mêlée adjacent en frappant l'attaquant
  **AVANT** que son coup ne résolve → chunke la cible avant son attaque, mais ne tue pas forcément
  (counter mêlée SEULEMENT → bypass = RANGED). `HolyDuel` (actif) : taunt **MUTUEL sans expiration** →
  coupe l'ACTIF de la cible (`Taunted_CantUseAbility`) + l'immobilise (`Taunted_BlockMovement`, cf. §1) :
  la cible ne peut PLUS lancer son actif, seule l'attaque normale forcée sur Jaeger reste possible →
  **neutralise une unité de valeur pour TOUT le combat**. Curable (Healing/Repairing retire le Taunt).
  `Terrifying` (réduit la mêlée subie → bypass = RANGED, cf. §1). (cf. gameconfig --ability MartialSuperiority / HolyDuel)
  `▸ Tac: rôle=control · menace=high (lock total d'une pièce-clé via HolyDuel + counter qui punit le contact mêlée) · counter=ne JAMAIS laisser une unité-clé adjacente seule à lui (HolyDuel la verrouille tout le combat, coupe son actif) ; l'attaquer depuis le RANGED (MartialSuperiority = counter mêlée seulement) ; un Healing/Repair retire le Taunt ; Overkill pour FinalJustice si présent [n=1]`
  `▸ [self-play consensus, seed 80064]` MartialSuperiority CONFIRMÉ n+1 — le counter mêlée résout AVANT l'attaque ennemie (double-hit Power en une activation) ;
  combiné à FinalJustice (death-attack même tué au ranged), le melee-into-Jaeger coûte un tank. Les 2 sides concordent. **DOCTRINE re-confirmée** :
  ne JAMAIS trader en mêlée dans Jaeger — le finir purement au RANGE (Psychic) ET garder les fragiles bas-PV hors de l'arc FinalJustice adjacent (ou overkill).
- **Calgar « Marneus Calgar » (ultraCalgar, Ultramarines, mêlée/tank, MkXGravis)** — mur quasi-inkillable au chip mêlée.
  `GauntletsOfUltramar` (Ranged AoE, profil Bolter) : **vrai splash multi-cible** (1 cast = tous les ennemis ≤2 hexes,
  PAS des hits bonus sur une seule cible — la classe expose Adjacent/Surrounding/AllTargetsSelector ; vérifié seed 97001 :
  un cast stationnaire a touché 2 ennemis à positions distinctes) → faible vs armure (Bolter PiercingRatio bas) mais
  haute valeur stationnaire (zéro exposition, large si 2+ ennemis clusterisés ≤2 hexes). `MkXGravis` (double-armure, cf. §1)
  + `FinalJustice` (§1) + `RitesOfBattle` (buff-aura). LOAD-BEARING : MkXGravis fait repasser le dmg entrant par l'Armour
  une 2ᵉ fois **sauf Crits** → ~HALVE le dmg mêlée non-crit → **mur quasi-inkillable pour un roster mêlée sans crit/armor-bypass**
  (cf. gameconfig --ability GauntletsOfUltramar / --trait MkXGravis).
  `▸ Tac: rôle=tank/anvil · menace=med EN GÉNÉRAL, **CRITICAL vs un roster majoritairement MÊLÉE** (MkXGravis ~halve le dmg mêlée non-crit + FinalJustice + RitesOfBattle → wincon-anchor late-game inkillable au chip mêlée) · counter=Crit / armor-ignore / Psychic (bypasse la 2ᵉ passe d'armure) OU Stun (Foehammer coupe GauntletsOfUltramar) ; NE PAS planifier de l'out-grind en mêlée — tuer les dealers softs qu'il buffe et accepter de ne pas le trade ; à MOI = GauntletsOfUltramar STATIONNAIRE quand 2+ ennemis ≤2 hexes (splash gratuit) + turret défensive (FinalJustice punit la mort) [n=1]`
- **Tigurius « Tigurius » (ultraTigurius, Ultramarines, Psyker, ranged)** — engine Psyker AoE, cible d'alpha prime.
  Kit recon-CONFIRMÉ vs gameconfig (seed 98003). `StormOfWrath` : **Psychic Pierce100 NoBlocking sur la cible + jusqu'à 5 adjacents
  = 6 unités max** ; PiercingRatio=100 ignore l'armure ET **NoBlocking bypasse les Block-abilities → BigTarget, GuardianOrganism
  n'appliquent PAS** → un cast arme trivialement `WeaverOfFate` (Thaumachus/Neurothrope MAX-dmg dès 3+ ennemis Psychic touchés) ET
  escalade Neuroparasite sur chaque cible. Aura `PsychicFortress` : alliés autour gagnent un block (50% chance, any-type) ET −Psychic subi,
  les DEUX effets **stackent sur un hit Psychic** → **mange MES finishers Psychic** (hits Amount=0 DidBlock=1). **L'aura est perdue à la
  mort de Tigurius** → le tuer re-active les finishers. **Fragile, PAS Resilient** (→ tout K! franc passe) ; over-étend facilement
  (cf. gameconfig --ability StormOfWrath / --trait PsychicFortress).
  `▸ Tac: rôle=engine · menace=critical (Psyker AoE NoBlocking ignore-armure 6 cibles = arme WeaverOfFate + Neuroparasite snowball ; PsychicFortress block-aura mange MES finishers ET blunt MON Psychic) · counter=le tuer EN PREMIER (fragile, pas Resilient → tout K! franc ; un anti-Psyker type CondemnorStake = cible d'alpha prime) → drop la block-aura + retire l'AoE ; FULL-FOCUS la SOURCE Tigurius, ne PAS split (split = PsychicFortress bloque mes finishers, Tigurius survit, re-fire — root cause partagée de loss seed 70000) ; ne PAS clusterer 3+ de mes units exposées à StormOfWrath ; punir son over-extension forward (T1 dive mid-board = kill gratuit ; ⚠ s'il dive ADJACENT à un Ulf SavageKiller, sa StormOfWrath est PRÉ-EMPTÉE — tué mid-cast avant que l'AoE résolve, seed 70004) [n=4]`
  `  ▸ Tac (n+1 StormOfWrath OFFENSIVE = 2-for-1 cluster-delete CONFIRMÉ self-play consensus, seed 80000 run #5) : **à MOI, viser un ennemi ADJACENT à un 2ᵉ héros ennemi = double-kill gratuit** — le splash Psychic NoBlocking touche la cible + les adjacents en bypassant armure ET block sur TOUS. Corollaire offensif du « ne pas clusterer MES units » : quand l'ENNEMI cluster 2 héros fragiles, StormOfWrath les delete tous les deux. ⚠ séquencer Tigurius (+ autres actifs alliés) AVANT un Atlacoya TalonsOfTheEmperor pour pumper le +/actif sur le kill du même cluster. Cross-validé les 2 sides. [self-play consensus, seed 80000 run #5]`

---

## 3bis. Units (autres factions, vues en random) — kit + interactions PAR unité

> Une entrée par unité ; interactions spécifiques sur SA page (traits transverses
> en §1 : Resilient, FinalJustice, Explodes, **Ambush**, **Steppable**, Blast-vs-armure).
> Stats → gameconfig. **Recon AUSSI les unités INVOQUÉES** (decoy, drones, Aberrant,
> Hormagaunt, Guardsman…) via gameconfig dès qu'elles apparaissent — leurs traits
> dictent la gestion (ne pas supposer ; ex. le decoy `Steppable` ci-§1).

- **ultraTitus (Ultramarines)** — carry self-reviving ; le tuer en NIANT le kill de riposte.
  `TacticalPrecision` (crit s'il a chargé, sinon AoE adjacents ; **un revive RE-DÉBLOQUE TacticalPrecision** même déjà
  utilisé ce combat — quirk : clause sur l'actif). `FuelledByFury` : 1ʳᵉ mort/tour **NON-overkillable** (Final Vengeance
  fire toujours sauf Overkill) + **revit à full-HP UNIQUEMENT si sa Final Vengeance DÉFAIT (tue) un ennemi
  éligible/adjacent**, gaté « 1ʳᵉ défaite/tour ». LOAD-BEARING : **pas de KILL de riposte = pas de revive** (un simple chip
  ne suffit pas) ; protection no-Overkill ET revive sont tous deux « 1ʳᵉ fois/tour ». `FinalJustice`, `BeastSlayer`/`BeastSnagga`
  (**+20% mêlée vs mes `BigTarget`/`Vehicle`**). (cf. gameconfig --ability FuelledByFury / TacticalPrecision)
  ⚠ **KILL-SAFETY (anti-revive par adjacence high-HP, vérifié seed 70004) :** finir Titus en gardant **SEULEMENT des corps
  high-HP adjacents** → la riposte FJ frappe un tank qui SURVIT = pas de kill = pas de revive = mort permanente
  (FuelledByFury strippé). À l'inverse, un fragile adjacent au coup fatal → FJ le tue → Titus revive.
  ⚠ **RE-CONFIRMÉ seed 70058 (revive gaté sur la DÉFAITE par FJ — n=2) :** i2 FuelledByFury exige que la riposte
  **DÉFAISE** la cible, pas seulement la chipe — un tank adjacent absorbe FJ (ex. via un self-debuff −% de l'attaquant)
  et survit → no kill → no revive → mort PERMANENTE.
  `▸ Tac: rôle=carry · menace=high (FinalJustice non-overkillable 1ʳᵉ mort/tour + revive-to-full si FJ kill + TacticalPrecision re-armé sur revive + BeastSlayer/BeastSnagga +20% vs mes BigTarget/Vehicle) · counter=le finir avec UNIQUEMENT des corps high-HP adjacents (FJ ne sécurise alors aucun kill → pas de revive, mort permanente — vécu seed 70004 ET 70058) ; ÉCARTER tout fragile/bas-PV de l'adjacence avant le coup fatal (sinon FJ le tue → Titus revive) ; alternative = l'Overkiller (no-Overkill ET revive sont « 1ʳᵉ fois/tour ») [n=2, 70004+70058]`

- **darkaAzrael « Azrael » (Dark Angels, ranged r2 + Overwatch turret)** — `DarkTalonStrike`
  = décapitation/chunk anti-tank-blindé : le Direct Pierce100 **bypass armure ET TerminatorArmour**
  (Direct exclu de la réduction, cf. §1), et la ligne Bolter catche un **2ᵉ ennemi aligné** en splash ;
  **tous les touchés deviennent Suppressed**.
  ⚠ **Pinned (move-1) sur les touchés + once-per-battle** observés n=1 mais NON dans l'i2 → cf. H38,
  hypothèse. `Overwatch` (cf. §1 — **gate = NOT-attacked, pas not-moved** ; le tenir SANS attaquer
  ré-arme l'Overwatch au tour adverse). `LionHelm` (passif, **range 2** : alliés à ≤2 hex font +dmg sur
  LEURS propres attaques déclenchées par Overwatch → reaction-kills multi-source quand des alliés sont
  groupés autour d'Azrael). `FinalJustice` (cf. §1). (cf. gameconfig --ability DarkTalonStrike|LionHelm)
  `▸ Tac: rôle=carry/turret · menace=high (DarkTalonStrike Direct Pierce100 bypass armure/TermArmour + ligne Bolter qui catche un 2ᵉ ennemi aligné + Overwatch turret + LionHelm boost les OW alliés) · counter=si ENNEMI, ne pas l'aligner avec une 2ᵉ unité (la ligne Bolter splash) ni pather dans son arc Overwatch armé ; si à MOI, **HOLD Azrael SANS attaquer pour garder l'OW armé** dans le tour adverse (gate=not-attacked) + grouper des alliés à ≤2 hex pour le boost LionHelm → le dive ennemi se fait reaction-killer en multi-source ; réserver le Direct DarkTalonStrike pour un tank Psychic/Direct-only (Njal TerminatorArmour) OU un deep-striker à Pinner ; NE PAS le pousser forward pour un K? non-garanti — le HOLD armé vaut mieux [n=1, 70001]`
- **tauCrisis « Re'vas » (Tau, Flying, Mechanical)** — `EarlyWarningOverride` : summon 2 Shield Drones
  **+ elle s'arme en OVERWATCH jusqu'à son prochain tour** ET **se ré-arme (reste en Overwatch, −1 hit
  par chaîne) à chaque kill d'Overwatch** → sa zone est interdite. L'Overwatch est une riposte
  **déclenchée par un ennemi qui BOUGE dans sa portée** au tour adverse (distinct de la danger zone
  statique) : router un move dans son arc r2 = tir gratuit, souvent **létal**. **Ne JAMAIS pather dans
  l'arc d'un Overwatcher armé** ; contourner ou le tuer/déplacer d'abord. ⚠️ **GAP outillage** : pas
  d'overlay des zones d'overwatch armé → lire l'effet armé dans decisionView.effects. ⚠ **[indispo]
  après usage = once-per-turn** (EarlyWarningOverride pas re-castable immédiatement, seed 70000) → la
  turret n'est pas re-armable à volonté ; planifier un seul gros tour d'Overwatch, pas une réaction
  garantie chaque round. `RangedSpecialist`, `BigTarget`, Mechanical. **`CyclicIonBlaster` (attaque
  normale)** = **burst anti-Mechanical** : hits Particle additionnels PAR-DESSUS la volée de base **+dmg
  si la cible a Markerlight OU le trait Mechanical** → focus-kill un Mechanical en une activation.
  ⚠ **DOCTRINE anti-Mechanical** : vs une Re'vas/un roster Tau RangedSpecialist, **discount le HP de MES
  Mechanicals** (Sy-gex/Actus/Abaddon-term moins tanky que leur HP suggère) → garder repair-engines +
  fragiles Mechanicals une rangée plus back, ne pas les sur-étendre dans la reach ranged d'une Re'vas.
  (cf. gameconfig --ability EarlyWarningOverride|CyclicIonBlaster) `[self-play consensus, seed 80042]`
  `▸ Tac: rôle=turret défensif (à MOI) · menace/valeur=high (EarlyWarningOverride = arme Re'vas en Overwatch + 2 Shield Drones + ré-arme à chaque kill OW + BigTarget −1 hit ranged aux adjacents) · usage à MOI = poser EarlyWarningOverride et HOLD (ne pas attaquer = garder l'OW armé) pour punir le dive ennemi en réactions ; ⚠ once-per-turn ([indispo] après cast) → ne PAS compter sur une masse de réactions chaque tour, la fenêtre est unique/cd (seed 70000 : punition du dive ÉMOUSSÉE faute d'OW dispo le tour clé) ; coller mes fragiles BigTarget adjacents pour le −1 hit ranged ; les drones non couverts par BigTarget ne sont PAS protégés du Psychic NoBlocking ; ⚠ côté ENNEMI = anchor turret/screen qui out-range une approche melee et ÉCRANE le soft backline de mon reach (seed 70052 : EWO castée T1 = front screen durable → engines softs inatteignables = composante de la loss de reach) ; ✅ **côté À MOI = a PORTÉ un W (seed 70056)** : EWO T1 + HOLD → un roster adverse 100% melee CONTRAINT de diver → l'Overwatch chunke avant mon tour puis la masse de réactions tue plusieurs carries sans dépenser mes actions = la moitié RÉCIPROQUE de H03 ; ne JAMAIS pather dans son arc r2 [n=3, 70000/70052/70056]`
  `▸ Tac (n+1 à MOI, seed 70060 W) : ✅ EWO Overwatch-turret a RE-PORTÉ un W — casté T2 (2 Shield Drones + OW armé, re-arm −1 hit par kill OW) → sur le dive d'un ennemi all-melee, l'OW a scoré 2 KILLS et s'est ré-armé = le CŒUR du mur de réaction « hold-baits-the-dive » (couplé à Sarquael GrimRetribution held-OW + Aun'Shi −50% aura → 2 carries morts T2 zéro perte). PLAY = armer EWO + HOLD le cluster cohésif (ne PAS pousser) ; chaque kill OW prolonge la chaîne à hit-count décroissant. Confirme « le reaction-engine PORTE le W si la ligne reste défensive » (pattern 96002/98002/70001/70056) [n=4, 70000/70052/70056/70060]`
- **templHelbrecht (Black Templars)** — `CrusadeOfWrath` (équipe r2 : +dmg + pierce melee = BUFF-ENGINE
  qui amplifie le focus de l'équipe). `Parry` (−1 hit aux multi-hit subis → préférer un GROS coup unique
  aux multi-hit). `FinalJustice` (§1 — riposte normale à la mort SAUF Overkill). `DestroyTheWitch` (+move
  + dmg vs Psykers → fait de MES Psyker des cibles prioritaires à screener).
  (cf. gameconfig --ability CrusadeOfWrath|DestroyTheWitch --trait Parry)
  `▸ Tac: rôle=engine · menace=high (CrusadeOfWrath = team buff melee qui amplifie le focus ; DestroyTheWitch vs mes Psykers ; FinalJustice riposte de mort) · counter=casser le buff-engine en le tuant tôt effondre l'amplification (seed 98004 : tué en réaction, pas de FJ visible = burst multi-source/overkill) ; Overkill OU absence de cible éligible pour neutraliser FinalJustice ; Parry → préférer un GROS coup unique aux multi-hit ; tuable par réactions/Overwatch (seed 96002 : tué par Overwatch + réaction SANS FinalJustice visible = Overkill/burst multi-source ; le Pinned ne bloque que l'Overwatch, jamais FinalJustice) [n=2]`
  `▸ Tac (n+1 OVERKILL-DEFEATS-FJ, seed 70057 W, confirmé Verif) : buff-engine (CrusadeOfWrath) à tuer EARLY pour collapse l'amplification melee — soft, no Resilient → one-shottable ~half par un carry adjacent. ⚠ FinalJustice neutralisé par **OVERKILL multi-source** (`Attack_WasOverkill=1`) → FJ NON déclenchée (confirme i2 « unless Overkilled » §1). DOCTRINE = empiler assez de dmg combiné pour garantir l'Overkill margin plutôt qu'un kill exact-HP (qui ferait fire la riposte) [n=3, +70057]`
- **genesBiophagus « Hollan » (Genestealer)** — **MOTEUR de l'équipe** : `Healer` +
  `TwistedScience` (chaque allié soigné par Hollan est affecté **jusqu'à sa mort**, gagne **+PV +max-HP
  permanents, 1× par unité non-réappliquable** ; les GSC affectés +dmg ; Hollan peut soigner des full-HP
  pour le trigger → ses alliés snowballent en murs). **AUCUNE restriction d'adjacence/portée sur le
  PASSIF lui-même** — la portée vit uniquement sur l'ACTION de heal de Hollan, donc une fois soigné un
  allié backline NON-adjacent reste un mur pour le combat. `AberrantHypermorph` (summon). `Ambush` (§1 —
  lui ET son Aberrant). ⚠ **TwistedScience s'applique à N'IMPORTE QUEL allié healé par Hollan, summons
  INCLUS** : un Aberrant healé sur revive est explicitement en scope (vérifié seed 98001, Aberrant
  ressuscité pompé bien au-dessus de sa base). Traiter CHAQUE heal de Hollan comme un événement
  d'inflation de stats PERMANENT (jusqu'à défaite, 1×/unité, non-stackable). → **kill prioritaire TÔT et
  PERMANENT** (coupe heal/buff/summon) ; détruire ses decoys (Steppable, §1 — marcher dessus) sinon il
  revient ; 2ᵉ kill permanent. (cf. gameconfig --trait Healer|Ambush --ability AberrantHypermorph)
  `▸ Tac: rôle=engine · menace=CRITICAL (sustain-engine : pompe les alliés ET summons en murs permanents + Aberrant summons + Ambush revive ; couplé à un Seeker-engine = backline qui out-sustain un roster mêlée) · counter=le tuer TÔT et PERMANENT (avant qu'il soigne quiconque), focaliser le PUMPER pas l'output pumpé ; via reach r3+/deep-strike/flyer/assassin ; vs un roster pur melee/r2 PAS de counter s'il reste row 9 (inatteignable seed 97001 → loss structurelle au recon) MAIS s'il est ATTEIGNABLE (mid-board) il meurt comme tout soft non-Resilient — tué 2× (permanent past Ambush) seed 98001 = W ; ⚠ le harness n'expose PAS l'action Healer via act ability → même MON Hollan ne peut pas caster TwistedScience comme oracle [n=3, 97001/98001/…]`
- **worldEightbound « Azkor » (World Eaters ; Daemon/Resilient/Terrifying/Unstoppable)**
  — **`OverwhelmingWrath`** : Taunt tous les adjacents + −dmg ranged subi, puis **AoE retardée à tous
  les adjacents au DÉBUT de son tour SUIVANT**. Combo fort : Taunter un cluster sur ce tank → l'AoE
  retardée nettoie. ⚠ **l'AoE PENDING est ANNULÉE si Azkor est tué avant son prochain tour** (la fenêtre
  Taunt+−ranged reste mais le AoE ne résout jamais) → contre-play : tuer Azkor AVANT son StartTurn cancel
  l'AoE entièrement (cross-observé DEUX sides) [self-play consensus, seed 80020].
  `BeaconOfRage` (+dmg/coup subi, cap ; partage aux Chaos adjacents s'il a tué).
  (cf. gameconfig --ability OverwhelmingWrath|BeaconOfRage)
- **tyranWingedPrime (Tyranids, Flying)** — **MOTEUR de SUMMONS** : `AlphaWarrior`
  (summon un Warrior s'il n'a pas bougé) + `SynapticLinchpin` (Hormagaunt sur attaque
  Synapse non-tuante, cap 4) → snowball de board. `Synapse`, `FinalJustice`.
  (Summons : agissent 1× à la création puis **réagissent** — overwatch-like.)
  **`SynapticLinchpin`** (i2-confirmé seed 97002 + 70006) : toute attaque NORMALE non-tuante du Winged
  Prime **OU de tout allié Synapse** sur un ennemi summon **1 Hormagaunt adjacent à la cible**, qui
  **attaque immédiatement** (cap 4 ; HP/Dmg/Arm scalent avec le rank). ⚠ Confirmé seed 70006 : une
  normale sur une unité **qui A SURVÉCU** (plancher 50% HypersensoryAbilities) a IMMÉDIATEMENT summon un
  Hormagaunt → l'engine fire sur N'IMPORTE quelle normale Synapse qui NE TUE PAS la cible (la survie via
  floor déclenche le summon). ⚠ Une fois que le Winged Prime a BOUGÉ il ne peut plus `AlphaWarrior`, mais
  ses attaques normales **continuent de spawner des Hormagaunts** → le tuer AVANT qu'il attaque (retire
  CETTE source ; d'autres unités Synapse trigger encore le passif) (et **OVERKILL** pour sa FinalJustice).
  (cf. gameconfig --ability AlphaWarrior|SynapticLinchpin --trait Synapse)
  `▸ Tac: rôle=engine · menace=high (double summon-engine : AlphaWarrior si immobile + Hormagaunt par normale non-tuante ; FinalJustice ; soft, no-Resilient) · counter=le tuer T1-T2 ATTEIGNABLE quand l'IA dive (seed 70006 : une AoE ranged FrenziedFiring l'a chunké depuis la tuile courante ET splash les adjacents + kill un Hormagaunt frais dans le MÊME cast = brise le summon-engine + chip l'anvil voisin + nie le snowball simultanément) ; ⚠⚠ **OVERKILL (>2× PV restants) OU finir au RANGE sans fragile adjacent** — FinalJustice fire sur toute mort NON-overkill et choisit une cible adjacente éligible (seed 70006 : K! non-overkill = exactement les PV restants → FJ a TUÉ ma fragile adjacente ; le label K! n'a PAS warné car hits sommés = PV restants, aucune marge) ; nier sa 1ʳᵉ normale non-tuante stoppe le snowball SynapticLinchpin ; killable aussi via burst WarHowl [n=2, 97002/70006]`
- **tyranTyrantGuard « Tyrant Guard » (Tyranids, move3, anvil)** — `BigTarget` (alliés
  adjacents −1 hit ranged ; **non déplaçable**), `GuardianOrganism` (−% dmg subi / cap par hit
  s'il **n'a pas bougé** le tour précédent OU est dans une aura Synapse → empilé à BigTarget ;
  ⚠ **ne couvre QUE les alliés dans la zone BigTarget de TG** (adjacents) — backline/drones hors
  adjacence ne bénéficient PAS de la réduction, vécu seed 70000 ; ⚠ **ne réduit PAS le Psychic
  NoBlocking** type StormOfWrath qui bypasse Block — vécu seed 70000), `CrushingStrike` (+dmg mêlée
  normale **s'il n'a PAS bougé**), `CrushingClaws` (Taunt + push + Suppress ; ⚠ pose en moteur
  Taunted_BlockMovement + Taunted_CantUseAbility + Pinned = **engine-disable propre 1 round** d'un
  Psyker/summoner soft — vécu seed 70000 : Thaumachus n'a JAMAIS casté ses abilities, cf. H30).
  Mur d'attrition quasi-inkillable au chip ranged low-pierce. Focus-killer de mes corps deep/isolés.
  (cf. gameconfig --ability CrushingStrike|CrushingClaws --trait BigTarget|GuardianOrganism)
  `▸ Tac: rôle=anvil · menace=high (gros PV + GuardianOrganism + BigTarget = forte réduction ; focus-killer de mes corps isolés) · counter=ne PAS investir d'output dessus (puit de dégâts) ; le FAIRE bouger (zoner) pour stripper GuardianOrganism/CrushingStrike ; l'ignorer et racer les unités softs ; ne JAMAIS lui présenter un corps isolé (seed 97002 : a co-tué un corps deep) ; ⚠ un Direct Pierce100 (DoomSiren) BYPASS son armure → le chunker GRATIS en collatéral splash quand il jouxte la cible primaire (seed 70002 : DoomSiren adjacent-à-cible + leftover-Blast l'a FINI = anvil tombé sans investir d'action dédiée) [n=2, 70002]`
  `▸ Tac (CORRECTION KILLABILITÉ — seed 70054) : ⚠ TG n'est PAS Resilient. GuardianOrganism = réduction en POURCENTAGE (cappé) quand en range Synapse OU s'il n'a PAS bougé le tour précédent ; BigTarget n'ajoute AUCUNE protection contre les dégâts. PAS une immunité — AUCUN filet survive-at-1HP. Donc QUAND c'est l'anvil FOCUSABLE non-Resilient sur ma ligne et que le chip-only PERD, un overkill multi-source en UN tour le tue OUTRIGHT (seed 70054 : 4 sources combinées = mort en un tour ; le guard a flippé d'un plan défensif perdant à FOCUS-FIRST). NUANCE vs « ne pas investir d'output » ci-dessus : ce réflexe TIENT quand le TG est juste un écran qu'on peut ignorer/racer ; il NE TIENT PAS quand le TG est l'anvil focusable sur ma ligne et que l'attrition chip-only perd — réserver/concentrer le burst pour un kill one-turn. Markerlight pumpe ce focus. La réduction ralentit mais n'empêche PAS un overkill coordonné [n=1, 70054]`
  `▸ Tac (CONFIRM n+1 killabilité + COÛT — seed 70059 W) : confirme NON-Resilient → un overkill one-turn multi-source le tue OUTRIGHT quand il dive forward (il a BOUGÉ en divant → a perdu CrushingStrike/GuardianOrganism → strippé sa réduction puis fini par un K!). ⚠ COÛT CONFIRMÉ : tuer le TG quand c'est l'anvil focusable adjacent a EXIGÉ une tuile mêlée forward → mon carry committé là s'est fait focus-killer = trade carry-pour-anvil. Donc « le tuer quand c'est l'anvil focusable » TIENT, mais peser le COÛT forward : si tuer le TG exige un CARRY au front, préférer tuer l'ENGINE au range et laisser le TG, OU sacrifier le corps le plus expendable. La réduction est strippée dès qu'il bouge (dive) → l'attaquant qui le force à diver le rend plus tuable [n=2, 70054/70059]`
- **blackTerminator « Angrax » (Black Legion, anvil)** — `BringerOfDespair` = **multi-hit qui BAT le
  Resilient** : 4× sur la cible + 4× un autre ennemi adjacent → le 1er hit floor la cible à 1, un hit
  suivant tue depuis 1 (sauf si un hit est bloqué/manqué). `TeleportStrike` (deep strike). `HatefulAssault`
  (overwatch mêlée, cf. §3). `TerminatorArmour` réduit la **1ʳᵉ attaque/tour SAUF Psychic/Direct** ; **n'est
  PAS Resilient** → la 2ᵉ attaque distincte du tour tape plein. (cf. gameconfig --ability BringerOfDespair|TerminatorArmour)
  `▸ Tac: rôle=anvil · menace=med (durable mais sans Resilient ni self-heal = PAS un wincon ; sert d'ÉCRAN deep-strike pour les engines backline) · counter=Psychic/Direct bypasse TerminatorArmour ; sinon focus multi-attaquant (2ᵉ attaque du tour plein) ou AoE chip ; ⚠ ne PAS dumper tout le burst dessus pendant que les vrais engines (Sho'syl/Hollan) restent intouchés — focuser le wincon d'abord ; usage à MOI : BringerOfDespair = mon outil anti-Resilient (bypass le clamp en multi-hit) ; ⚠ CONFIRMÉ écran-pas-wincon (seed 70004 : acté hors Deep Strike puis MORT dans ma cascade de réactions au dive — correctement NON priorisé sur l'engine) [n=3]`
- **spaceWulfen « Ulf » (Space Wolves)** — **`SavageKiller`** (réaction mêlée 5-hit Power) : se déclenche
  UNIQUEMENT sur (a) un **Summon spawn/move adjacent** à Ulf, OU (b) un **ennemi adjacent qui tente un ACTIF**
  — dans le cas (b) les dégâts **résolvent AVANT** que l'actif s'active → peut NÉGOCIER un cast en tuant le
  caster mid-cast (counter anti-summon/anti-caster préemptif). ⚠ un **move non-summon + une NORMALE** depuis
  l'adjacence ne sont NI (a) NI (b) = zéro trigger. `GreatFrostAxe`. `FinalJustice` (free normale à la mort
  SAUF Overkill — un **kill exact-HP n'est PAS un Overkill** → FJ fire quand même). **PAS de Resilient.**
  Synergie SavageKiller+FinalJustice → corps de réaction de haute valeur **même fragile ou ressuscité**
  (Isabella peut le ramener, cf. §5bis). (cf. gameconfig --ability SavageKiller|FinalJustice)
  `▸ Tac: rôle=engine de réaction · menace/valeur=high (à MOI : SavageKiller pré-empte tout caster/summon adjacent + FinalJustice riposte sur sa mort, fire même à kill exact-HP) · usage à MOI = bait le dive IA sur un cluster cohésif (NE PAS le sur-étendre forward) → l'ennemi qui cast adjacent meurt AVANT d'agir ; le garder comme anchor SavageKiller persistant (seed 70004 : grosses réactions tuent 2 engines à 0 coût ; ⚠ committé adjacent à un carry = focus-killé, net OK car FJ a tué le carry mais a dépensé l'anchor) ; ressuscitable par Isabella pour relancer le moteur [n=1, 70004]`
  `▸ Tac (ENNEMI Ulf) : rôle=control · menace=med (réaction 5-hit vs caster/summon adjacent ; soft-ish, PAS de Resilient) · counter=NE rien caster/summon adjacent à lui ; le laisser DIVER dans un Overwatch ranged armé → reaction-killé sur la dive sans déclencher SavageKiller (seed 70058) ; soft no-Resilient → K! propre une fois reachable [n=1, 70058]`
  `▸ [self-play consensus, seed 80031]` ⚠ **2ᵉ voie pour cracker un Ulf ennemi sans feed SavageKiller = le focus en ATTAQUE NORMALE depuis des corps DÉJÀ-adjacents.** Cross-confirmé DEUX sides : SavageKiller ne se déclenche QUE sur (a) summon spawn/move adjacent OU (b) ennemi adjacent qui tente un ACTIF — donc un move (non-summon) + une normale depuis l'adjacence = zéro trigger. DOCTRINE offensive : pré-positionner les corps adjacents AU TOUR PRÉCÉDENT (sans summon ni actif adjacent), puis le focus en normales ce tour-ci ; ne JAMAIS le toucher avec un ACTIF adjacent ni faire spawner/bouger un summon à côté. NB FinalJustice fire quand même à sa mort → finir au range ou Overkill si un fragile est adjacent. (cf. gameconfig --ability SavageKiller) [self-play consensus, seed 80031]
- **genesKelermorph « Judh » (Genestealer)** — `HeroicFusillade` = ability **move+attaque** (6× la cible +
  tous les ennemis l'entourant, +crit par case libre autour) ⚠ **injouable** (`mutated=False` silencieux) si
  AUCUNE case adjacente à la cible n'est atteignable à move-range 2 → **pré-positionner** Judh AVANT de lancer.
  **Redevient utilisable après résurrection Ambush** même si déjà consommée. `HypersensoryAbilities` =
  plancher 50% PV scopé **« 1ᵉʳ coup de CHAQUE TOUR ENNEMI seulement »** (+ move/decoy/contre) : les hits
  SUIVANTS du même tour ennemi chip normalement, et le floor **ne s'applique PAS sur le tour JOUEUR** (une
  ability/FJ sur MON tour la tue normalement). `Ambush` (§1, first-defeat-only : decoy + **resurrect FULL HP
  au début de SON prochain tour** si un decoy ami survit ; **2ᵉ mort ne ressuscite jamais**). NET = très
  STICKY : survit à un focus multi-hit à ~50%, mais tuable à une ability sur tour-joueur, et revient full HP.
  (cf. gameconfig --ability HeroicFusillade|HypersensoryAbilities|Ambush)
  `▸ Tac: rôle=carry · menace=high (ranged survivable + AoE 6-hit + floor 50% 1er-coup-tour-ennemi + Ambush full-HP revive) · counter=si ENNEMI, clear TOUS ses decoys (2 sources : Hypersensory + Ambush) pour un kill définitif, et la tuer sur MON tour (le floor ne protège PAS sur le tour joueur) ; si à MOI, pré-positionner pour la contrainte HeroicFusillade move-range-2 AVANT de lancer (sinon no-op silencieux) ; ⚠ NE PAS la laisser fragile (≤ ~50% PV) adjacente à un FJ-carrier ennemi sur MON tour — un kill non-overkill du carrier déclenche une FJ qui peut la tuer (seed 70006) ; ⚠ menace contributive confirmée seed 70050 (a contribué à un focus de tour ennemi qui a wipe 4 units) ; ⚠ **n+1 (seed 70061)** : revived FULL via Ambush ; un **single-source** sur le re-kill ne fait que FLOOR (besoin de stacker un 2ᵉ attaquant au tour ennemi). ⚠ **CONTRADICTION DE MENACE RÉSOLUE** : le floor à 50% peut faire croire qu'il protège sur MON tour (un re-kill flooré à exactement 50%) → MISREAD ; le scope i2 est « 1er coup chaque tour ENNEMI seulement », le floor NE protège PAS sur le tour joueur. Pour la tuer : clear les decoys (2 sources) ET la frapper sur MON tour OU stacker un 2ᵉ attaquant au tour ennemi [n=4, 70006/70050/70061]`
- **MoW astraOrdnanceBattery (Imperial)** — `MalleusRocketLauncher` : **barrage RETARDÉ** (marque un hex via
  `--to`, fire au DÉBUT du tour MoW SUIVANT ; AoE large + Suppress). `ForwardSpotter` : summon Guardsman qui
  **attaque immédiatement**. (cf. gameconfig --ability MalleusRocketLauncher|ForwardSpotter)
- **MoW deathCrawler (Death Guard, ennemi)** — `EntropyCannons` / `PlagueburstMortar` ne frappent QUE des
  cibles à **armure réduite OU dans une aura Contagion** → sans ces conditions sur le board, ce MoW est
  largement neutralisé. (cf. gameconfig --ability EntropyCannons|PlagueburstMortar)
- **ultraApothecary (Imperial)** — `Narthecium` : revive un allié **NON-Mechanical** **uniquement s'il est
  ADJACENT** à l'Apothecary **au moment de sa mort**, **sauf si le coup létal est un Overkill**. Hard-gated
  **1×/tour**. Une mort NON-adjacente = **perte permanente** même sur un coup non-overkill → garder les unités
  revivables **collées adjacentes** à l'Apothecary. (cf. gameconfig --ability Narthecium)
  `▸ [self-play consensus, seed 80072]` **Umbrella Narthecium + CombatRestoratives = un-out-damageable par un roster chip/burst-once.** Confirmé par LES DEUX sides : `CombatRestoratives` = mass-heal à self+adjacents **ET clear les effets négatifs (Pinned, etc.)** ; couplé au revive **100%** du cluster adjacent, l'engine reset une ligne battered à near-full chaque tour. **STRUCTURE** : un cluster tight où CHAQUE membre est adjacent au reviver = umbrella total ; un roster adverse SANS reach-tool (r2/r3, pas de deep-strike/flyer-assassin) ne peut PAS toucher l'Apothecary back-screené → **loss structurelle à flagger AU RECON** (H02 reach-fail + H11 self-healing anvil). Counter = atteindre/tuer l'Apothecary EN PREMIER (reach-asset pré-positionné) OU le draw-out ; à défaut, least-bad = all-in SPÉCIFIQUEMENT sur l'Apothecary, pas du chip réparti. (cf. gameconfig --ability CombatRestoratives|Narthecium)
- **spaceHound « Tjark » (Imperial, mêlée Pierce = ignore armure)** — passif **`HuntersBeyondDeath`** = aura
  anti-Psyker positionnelle (« dans les 2 hexes de Tjark ») : les Psykers ennemis proches déalent moins et
  (sauf Immune) **perdent le multi-hit de leur tir normal** ; Tjark fait **+dmg PAR HIT vs Psykers** → assassin
  anti-Psyker (peut one-shot un Psyker). ⚠ son moindre dmg vs NON-Psykers = simplement l'absence du bonus,
  **PAS** son trait Terrifying (Terrifying réduit le dmg que Tjark SUBIT, pas celui qu'il INFLIGE). Aura
  **ancrée sur la source** → strippée dès que Tjark meurt → tuer Tjark libère un Psyker suppressé. Traits :
  **`Infiltrate`** (ne déclenche PAS l'Overwatch ennemi), **`Terrifying`** (réduit la mêlée subie),
  **`GrapnelLauncher`** (repositionne) ; **PAS de Resilient** → un burst ranged le tue franc. Dive agressif.
  (cf. gameconfig --ability HuntersBeyondDeath ; --trait Infiltrate|Terrifying)
  `▸ Tac: rôle=carry · menace=high (assassin anti-Psyker + dive agressif + Infiltrate no-OW) · counter=RANGED (bypasse Terrifying, pas Resilient → burst le tue franc) ; garder mes ranged en retrait pour punir son dive (seed 95001) ; Infiltrate = il bouge sans trigger mon OW [n=1]`
  `▸ Tac (CORRECTION CONDITIONNELLE, seed 70051) : rôle=chaff · menace=LOW **quand MON côté n'a AUCUN Psyker** — HuntersBeyondDeath est ENTIÈREMENT INERTE faute de cible Psyker → réduit à un melee plat, no Resilient. Demote high→low ; killable franc. RÈGLE DE RECON : COMPTER les Psykers de MON côté AVANT de craindre son aura (symétrie de l'engine-inerte H02 : une aura anti-X ne vaut que s'il existe une cible X valide). Infiltrate = dive sans trigger mon OW mais sans valeur d'engine ici [n=1, 70051]`
- **adeptHospitaller « Isabella » (Imperial)** — **MOTEUR de SUSTAIN** : `RitesOfRestoration` (heal self +
  alliés adjacents ; **ressuscite 1 Imperial Character + jusqu'à 2 Imperial Summons** défaits, à **PV FIXE**,
  qui ne peuvent agir ce tour ; non-Mechanical seulement) + `MedicusMinistorum` (alliés adjacents non-mech :
  **regen à chaque fois qu'ils SUBISSENT des dégâts**, sauf défaite). ⚠ la PV de résurrection est **FIXE** —
  `ActOfFaith` (Roswitha ou autre Imperial) ne la boost PAS (ActOfFaith ne donne que Crit, aucun PV) ; tout
  « ressuscité à PV plus haut » = misread/regen post-rez, PAS la rez. ⚠ **`MedicusMinistorum` = heal
  CROSS-FACTION** : « friendly » = **MÊME ÉQUIPE, PAS même faction** → soigne TOUT allié adjacent non-mécanique
  de team 2 ayant subi des dégâts (ex. heal un Chaos par une Sisterhood). En Tacticus les équipes
  multi-factions sont la norme → ne pas supposer qu'un healer ne soigne que sa faction. Net : elle **annule
  kills (revive) et chunks (regen+heal)** plus vite que le dmg/tour typique. **PAS de Resilient, PAS de
  FinalJustice** → n'importe quel K! la défait ; elle se retire après avoir healé → la catcher au RANGED.
  `RitesOfRestoration` = **[indispo] après UN usage** (once-per-battle/long-cd, cf. H13) → swing UNIQUE.
  (cf. gameconfig --ability RitesOfRestoration|MedicusMinistorum|ActOfFaith)
  `▸ Tac: rôle=engine · menace=critical (resurrect chain + heal/regen annule kills+chunks ; MedicusMinistorum heal CROSS-FACTION tout allié same-team adjacent) · counter=la tuer TÔT (T2) AVANT qu'elle use RitesOfRestoration ; pas de Resilient/FinalJustice → tout K! suffit ; se retire après heal → la catcher au RANGED ; H02 prime MAIS exige le REACH — si elle est back-row hors portée T1-T2, pré-positionner un dealer ranged T1 pour l'atteindre T2 (seed 95001 : tuée T4 ranged stacké = W ; seed 96001 : wincon mais INACCESSIBLE row 9 → jamais atteinte → L ; seed 70050 : wincon soft no-Resilient mais INATTEIGNABLE row 8-9 à un roster melee/r2 dont le seul reach-tool a été deleté → sustain-engine intact = loss structurelle) · à MOI : RitesOfRestoration = swing UNIQUE ([indispo] après 1 usage) qui ramène un Imperial Character défait (reaction-engine type Ulf) à PV fixe scaled, ne peut agir ce tour — le réserver pour le corps le plus impactant (seed 70004 : ramené Ulf → moteur SavageKiller relancé) [n=3 ennemi, +1 mien 70004]`

- **astraPrimarisPsy « Sibyll » (Imperial, Psyker, ranged, fragile, no Resilient)** — `PsychicMaelstrom`
  Psychic **Pierce100 + NoBlocking** = ignore armure ET block (cf. §1) → délivre plein pot à un noyau
  Mechanical/armuré. `Nightshroud` (passif) : alliés adjacents gagnent **Infiltrate** ET infligent un
  contre-dégât aux ennemis qui les frappent = **émousse mes coups sur ses voisins**. **La cible la plus
  SOFT d'un roster typique** → focus prioritaire. (cf. gameconfig --ability PsychicMaelstrom / Nightshroud)
  `▸ Tac: rôle=control (Psyker-nuke) · menace=med (PsychicMaelstrom Pierce100 NoBlocking ignore mon armure + Nightshroud émousse mes coups sur ses voisins) · counter=la tuer TÔT — fragile, no Resilient → un burst la défait franc ; priorité car NoBlocking ignore mon armure ET son Nightshroud blunt mes attaques sur ses adjacents → cible de focus prioritaire avec un autre engine soft (Aethana) [n=1, 70051]`
- **bloodIntercessor « Mataneo » (Blood Angels, deep-strike Imperial)** — `HammerOfWrath` charge AoE adjacents
  gagne Infiltrate, **UNIQUEMENT s'il N'A PAS bougé** ce tour ; si **MATANEO lui-même** est <=50% PV, dégâts
  **doublés** (`HammerOfWrath_ConditionalDamage` — c'est SON PV, PAS celui de la cible). `AggressiveOnslaught` :
  à la **charge SEULEMENT**, summon **2 Jump Pack Intercessors** (bloodSmnIntercessor, scale avec les buffs du
  match) attaquant immédiatement ; ils **quittent le terrain au début de chaque tour de Mataneo** (blockers/chip
  ~1 tour, ne pas compter sur la persistance). **Pas de charge** (a bougé, ou aucun ennemi avec hex libre
  adjacent en range) = **0 dmg ET 0 summon** → le tuer/déplacer **avant la charge** nie tout le package.
  ⚠️ **GATE no-move = effondrement de dégâts** : si Mataneo a bougé, la charge + summon-attack ne fire PAS →
  seul un coup réduit/normal part. **NE JAMAIS** compter sur HammerOfWrath comme kill quand Mataneo a déjà bougé
  — la précondition « has not moved » produit toute la fenêtre létale.
  (cf. gameconfig --ability HammerOfWrath / AggressiveOnslaught)
  `▸ Tac: rôle=deep-strike carry/summoner · menace=med (burst conditionnel + 2 summons éphémères) · counter=le tuer/déplacer AVANT la charge ; quand il deep-strike dans ma zone, le punir IMMÉDIATEMENT avant qu'il charge (Overwatch + une attaque Direct + Pinned qui annule le move de charge le neutralisent depuis la tuile courante, zéro exposure ; carte « kill/displace AVANT que la charge nullifie le package ») ; usage à MOI = ne committer HammerOfWrath en finisher QUE si Mataneo N'A PAS bougé ; ⚠ deep-commit solo via HammerOfWrath = corps isolé (les 2 JPI disparaissent au début du tour suivant de Mataneo = pas de support durable) → focus-killé (seed 97002 : commit deep, dmg de-buffé, Mataneo stranded → tué) [n=2]`
- **tauShadowsun (Tau)** — **`ExemplarOfTheKauyon` (id 1087) = TÉLÉPORT de repositionnement, PAS un nuke ciblé** :
  la cible = un **hex adjacent à un ALLIÉ** ; elle s'y téléporte et **auto-attaque l'ennemi LE PLUS PROCHE**
  (Blast), et une **Command-Link Drone** stationnaire est summonée dans son ancien hex. Cibler un ENNEMI =
  invalide (ni téléport ni attaque). La drone **étend l'aura ranged** `DefenderOfTheGreaterGood`. Pour des dégâts
  ranged fiables : son **attaque normale Melta (id 69, r2)**, boostée par `RangedSpecialist` (si elle n'a pas
  démarré adjacente à un ennemi) + DefenderOfTheGreaterGood ; `Camouflage` la rend tanky vs ranged.
  ⚠ **REACH PLEINE-PLANCHE CONFIRMÉ** : `ExemplarOfTheKauyon` se téléporte sur N'IMPORTE quel hex adjacent à un
  allié (**AUCUN cap de move-range**) + `Flying` (traverse terrain/units) = **reach pleine-planche** quel que
  soit le terrain (vécu seed 70050 : a atteint et KILL un Neurothrope backline depuis sa propre backline, puis
  summon Drone dans l'hex vacaté). → **AUCUNE unité ranged backline n'est en sécurité tant que Shadowsun a un
  allié quelque part près d'elle** : prioriser l'élimination de ses alliés ou de Shadowsun AVANT qu'elle se
  repositionne ; le danger-zone overlay est **INUTILE** pour la safety d'un fragile vs elle (le teleport ignore
  la portée affichée). (cf. gameconfig --ability ExemplarOfTheKauyon / --trait Camouflage / DefenderOfTheGreaterGood)
  `▸ Tac: rôle=carry · menace=high (move + Flying + ExemplarOfTheKauyon teleport = reach pleine-planche + Camouflage [ranged hits réduits] + Infiltrate [no overwatch] + Melta Pierce75 ranged carry — supprime tout fragile pas en row 0-1 ; vécu seed 70050 : a tué mon Neurothrope depuis la backline) · counter=garder mes fragiles row 0-1 INTOUCHABLES ; elle n'a PAS de Resilient → un burst focalisé la tue, mais il faut SURVIVRE à son teleport-reach d'abord (tuer ses alliés-ancres ou elle-même tôt) ; le teleport+Flying rend le danger-zone overlay inutile pour la safety d'un fragile [n=1, 70050]`
- **astraDreir « Dreir » (Astra Militarum ; Hero/Resilient/Unstoppable)** — `ToughToKill` (passif) :
  **regen FIXE au DÉBUT de son tour** (`hpToHeal`, **PAS un re-heal full/%**, plafonné à max PV) ; ALSO réduit
  crit chance et crit dmg subis. Sa durabilité = cette regen **+ Resilient** (survit à 1 PV sauf Overkill), PAS
  un top-to-full. `LeadingTheCharge` (actif) : **hard-gated « Dreir n'a PAS bougé »** ce tour — s'il a bougé,
  indispo même si [prêt]/usable s'affiche. Sur fire : gagne Infiltrate, charge (Power, +pierce par allié défait),
  puis summon jusqu'à **4 Death Riders** adjacents qui attaquent immédiatement. → **agir AVANT de le bouger** +
  cible avec hex adjacent libre. (cf. gameconfig --ability LeadingTheCharge / --trait ToughToKill / Resilient)
  `▸ Tac: rôle=engine (summon + sustain) · menace=high (LeadingTheCharge jusqu'à 4 Death Riders gated « n'a pas bougé » + ToughToKill regen/tour + Resilient + −crit) · counter=TAUNT (Taunted_CantUseAbility, cf. H30) pour NIER les summons 2 rounds, puis kill PERMANENT via MULTI-HIT (bat Resilient) ou Overkill ; ⚠ **le zero-out ToughToKill bloque le kill SEULEMENT s'il est le DERNIER hit** (cf. H31/H04) : seed 98000 un multi-hit l'a floored à 1 PUIS le dernier hit = 0 dmg → survécu ; MAIS seed 70008 un multi-hit À GRAND NOMBRE de hits l'a floored à 1, un hit mid-séquence a fait 0 (ToughToKill) ET un hit surplus ultérieur l'a TUÉ depuis 1 PV (WasOverkilled) = full kill → un multi-hit avec surplus >0 past le floor le finit ; sur un multi-hit court, BUDGÉTISER un finisher séparé ; ToughToKill regen un Dreir à 1 PV [n=2, 98000/70008]`
- **necroSpyder « Aleph-Null » (Necron, move3, mêlée Particle)** — **NOYAU de SUSTAIN dur** :
  `ScarabHive` (actif) summon **2 Scarab Swarms** (necroSmnSwarm, Swarm/Flying) à côté de la cible qui
  **attaquent IMMÉDIATEMENT** (Piercing 1ᵉʳ hit). Stack de self-heal/repair : `LivingMetal` (regen %max PV début
  de tour joueur, le rend aussi **Mechanical**), `FabricatorClawArray` (passif : répare un Mechanical adjacent
  après move, sinon fin de tour), `Mechanic` (répare comme action). Mechanical ⇒ ne peut être heal, **seulement
  repair**. ALSO `Explodes` à la mort (Direct à tous les adjacents — peut toucher ses propres Scarabs) et les
  Swarms ont `ReanimationProtocols` (revive sauf **Overkill**). → focus en **Overkill** (nie Reanimation) +
  out-tempo avant que le moteur repair/summon snowballe (out-DPS le stack de heal de front = impraticable).
  (cf. gameconfig --ability ScarabHive / Mechanic / --trait LivingMetal / FabricatorClawArray / Explodes / ReanimationProtocols)
  `▸ Tac: rôle=engine (repair-hub) · menace=CRITICAL **SI ≥1 autre allié Mechanical/LivingMetal sur son équipe**, sinon **LOW** (cœur d'un noyau Mechanical auto-réparant : FabricatorClaw + Mechanic + LivingMetal/NetherRealmCasket alimente toute la grappe blindée — il faut le tuer TÔT) · ⚠ **NUANCE INERTE (vécu seed 70002)** : si Aleph-Null est le SEUL Mechanical du roster adverse, son kit repair/regen est **STRUCTURELLEMENT INERTE** (aucun bénéficiaire = ne peut que se self-regen, jamais amplifier un allié) → demote CRITICAL→LOW, traite-le comme un gros corps soft (recon : compter les autres Mechanical/LivingMetal AVANT de le craindre) · counter=Psychic NoBlocking (Pierce100 + Cannot-be-blocked bypasse TOTALEMENT son armure Mechanical + NetherRealmCasket, vérifié seed 98003) = le bypass le plus fiable ; mais sans repair-target il est si soft qu'un double Flame Brazier le one-shot (vécu seed 70002) ; le finir au RANGED + en **Overkill** (Scarabs ReanimationProtocols + LivingMetal regen) ; `Explodes` à la mort = **Direct aux ADJACENTS SEULEMENT — units 2+ hex épargnées** (friendly-fire ; kill au RANGE pour garder mes fragiles clear) → le tuer DANS son propre cluster pour chunker la grappe gratis (vérifié seeds 98003/98002) ; soft no-Resilient → killable en réaction s'il dive ; ⚠ chaque repair sur un carry DakkaDakka (Snappawrecka) **ajoute des hits** à son attaque → tuer Aleph-Null coupe AUSSI le scaling du carry (seed 98000 : repair-hub backline jamais atteint par mon roster mêlée = a décidé l'attrition) ; ⚠ **NUANCE INERTE re-vérifiée DANS MON roster (seed 70005)** : Aleph-Null seul Mechanical de MON équipe → FabricatorClaw INERTE, seul LivingMetal self-regen actif = corps soft + son `Explodes` est un RISQUE pour MOI (friendly-fired mes TG + Typhus adjacents à sa mort) → ne pas coller mes unités à lui s'il peut mourir [n=5, 98000/98002/98003/70002/70005]`
- **necroDestroyer « Imospekh » (Necron, ranged r2, Overwatch+InescapableDeath)** — tourelle OW à chaîne.
  `MultiThreatEliminator` (actif Ranged, Molecular range 2, Pierce60 = partiellement réduit par l'armure ; les
  hits restants **chaînent vers un ennemi ADJACENT à la cible**, +1 hit par kill, re-cible ; NON réduit par
  Terrifying = melee-only). Caster l'actif = « a attaqué » → PAS en Overwatch ce tour-là. `InescapableDeath`
  (passif) : **+dmg/hit en Overwatch** ET **reste en Overwatch sur un kill déclenché par Overwatch** → chaîne de
  ripostes OW gratuites tant qu'il tue. `LivingMetal` (regen %max début de tour ; Mechanical → repair-only).
  **Pas Resilient** → tuable proprement une fois atteint. **H06 CONFIRMÉ live (n=2, seed 70008)** : la chaîne
  InescapableDeath sur Overwatch a fire — a tué un Death Rider puis est RESTÉ en Overwatch et a continué sur
  l'ennemi suivant en retenant les hits ; chaque kill in-chain ajoute +1 hit (MultiThreatEliminator) AVANT le −1
  InescapableDeath → cascades longues quand ennemis adjacents en range 2. Pierce60 confirmé partiellement réduit
  live (Gauss vs double-armor → JAMAIS un armor-bypass).
  (cf. gameconfig --ability MultiThreatEliminator / --trait InescapableDeath / LivingMetal)
  `▸ Tac: rôle=control/engine-de-réaction · menace=high (OW + InescapableDeath = chaîne OW sur les kills — un seul tour ennemi a rendu beaucoup de dmg + 1 kill seed 70008) · counter=approcher sous Infiltrate (Shadowsun/Dante LightOfSanguinius=no-OW) ; pas Resilient → kill franc une fois en portée ; LivingMetal = repair-only → le tuer vite avant que la regen s'accumule · à MOI = LE garder turret-positionné, screené (BigTarget Gulgortz), et NE PAS attaquer avec quand un dive arrive → la value de réaction (chaîne OW) > un actif (seed 70008 : la chaîne OW + InescapableDeath a porté la récupération de 3v6 à 5v2) ; ⚠ côté ADVERSE : son OW armé en r2 GATE mon avance early → NE PAS entrer en r2 (hold/contourner), puis le tuer franc une fois qu'il avance dans ma portée (no-Resilient → kill propre avant que la chaîne OW snowball ; seed 70053 : tué T4 EN ÉVITANT son r2, comme l'un des 2 summon/OW engines tués le tour décisif) [n=3, 95000/70008/70053]`
- **thousTzaangor « Yazaghor » (Thousand Sons, Flying, Psyker/chaff)** — `WeaverOfFate` (tout tour où **3+
  ennemis** subissent du Psychic → dégât MAX sur toutes ses attaques ce tour — engine de snowball Psychic, cf.
  §2 Ahriman pour le même trait). `SorcerousFacade` : échange sa position avec un Psyker allié (ajoute un bonus
  Psychic). **Bas PV + Flying mais fragile.** (cf. gameconfig --ability SorcerousFacade / --trait WeaverOfFate)
  `▸ Tac: rôle=chaff/engine · menace=med · counter=le tuer TÔT (fragile, no-Resilient) pour couper le snowball WeaverOfFate (max dmg si 3+ cibles Psychic touchées) ; SorcerousFacade = position-swap → ne pas compter sur sa position fixe ; Flying = slippery à pin → le K! quand en portée ; seed 95000 : survécu 3 rounds faute de focus ; seed 70002 : tué T1 (carte « kill early ») ; seed 70009 : K!'d outright par Ragnar WarHowl-buffé → vaut le kill pour nier le moteur Psychic adverse (miroir de mon propre Abraxas/Patermine WeaverOfFate) [n=3, 70002/70009]`
  `▸ Tac (DEMOTE low — WeaverOfFate INERT, seed 70055/70054) : menace=LOW quand l'ENNEMI (son équipe) n'a AUCUN dealer Psychic → WeaverOfFate (3+ ennemis subissent du Psychic → max dmg) ET RealityUnbound (bonus/ennemi marqué Psychic) sont PERMANENTS INERTES faute de source Psychic côté SON équipe → Yazaghor réduit à un fragile Common ranged = simple corps soft, priorité basse. RÈGLE DE RECON (symétrie engine-inerte) : compter les dealers Psychic de SON équipe AVANT de craindre son snowball ; s'il n'y en a aucun → demote. Vécu seed 70055 : WeaverOfFate inert → tué T2 (Archimatos Incursion + Eldryon Executioner). Vécu seed 70054 (n+1) : aucune source Psychic ne touche MES propres units (le trigger compte 3+ de SES ennemis = mes units) → inert, focus-killé T3 avec 3 ranged (clean H03-reciprocal sur son dive isolé). Vécu seed 70058 (n+1) : Yazaghor ENNEMI, aucune source Psychic ne touche mes units → inert, demoté à chaff soft → forward-most diver T2, tué T3 (normale Thaddeus + stun-splash VexillaMagnifica depuis les tuiles courantes, no over-extension) [n=6, 70002/70009/70055/70054/70058]`

- **orksBigMek « Gibbascrapz » (Orks)** — `Mechanic` répare un Mechanical ami comme action (heal = Damage × max weapon hits → quasi-full en UNE action sur son Grot Tank) ⇒ chiper le Tank pendant que Gibbas vit est GÂCHÉ : tuer le repair-engine, pas le sponge. Aura `KustomForceField` (+Armure aux alliés **ADJACENTS** ; tout > base = scaling rareté/star, **PAS** un rework). ⚠️ **aura source-anchored** : tuer Gibbas **strip immédiatement** l'armure de la grappe (cascade `LoseEffect KustomForceField` → leurs hits subis ~doublent) → tuer le Bigmek ouvre une grappe blindée. Summon **Grot Tank** (Vehicle/Mechanical → repairable par Gibbas, BeastSlayer Ragnar +20% mêlée s'applique via Vehicle ; `Ramshackle` −dmg vs faible pierce) qui auto-move+attaque au début de son tour (trait `Summon`). **H10 RÉFUTÉ** : tuer Gibbas NON-adjacent au Tank ne le despawn PAS — la seule mécanique de retrait est `BattleFatigue` (fuir/retiré si un ami **ADJACENT** est défait, +chance si overkillé), adjacency-gated. (cf. gameconfig --trait Mechanic|Summon|BattleFatigue, --effect KustomForceField)
- **custoAtlacoya « Atlacoya » (Custodes, mêlée)** — `TalonsOfTheEmperor` (**Melee range 1, ennemi ADJACENT**) passe en **Direct** (ignore armure/réduction, comme Psychic) si la cible est un **Psyker** OU si Atlacoya est adjacente à un Custodes allié. Snowball : **bonus dmg cumulatif par actif utilisé par un Character allié** ce combat. Passif `DaughterOfTheAbyss` (DEUX volets) : (1) OFFENSIF +dmg aux Psykers ennemis proches ; (2) DÉFENSIF **réduit fortement le Psychic SUBI** → **neutralise quasi-complètement le Psychic ennemi vs Atlacoya** (vérifié : Psychic ennemi rabaissé aux valeurs d'une attaque normale non-Psychic). ⚠ ce n'est PAS une immunité au ranged en général (un ranged NON-Psychic ou un heal-block la touche quand même à distance). Combiné (1)+Direct → Talons sur un Psyker = souvent one-shot d'un caster fragile. `Terrifying`. ⚠ **Talons exige l'adjacence (range 1)** : cast sur cible non-adjacente **rejeté silencieusement** (`mutated=false`, aucune erreur, activation gâchée) → vérifier l'adjacence (glyph/aiMovableTiles) AVANT de caster. Note : `Taunted_CantUseAbility` (Xybia MindControl) coupe AUSSI Talons (cf. §1 MindControl). **Doctrine : engager les casters ennemis avec Atlacoya en priorité, depuis l'adjacence.** (cf. gameconfig --ability TalonsOfTheEmperor, --trait DaughterOfTheAbyss|Terrifying|Parry)
  `▸ Tac: rôle=anvil/carry · menace=med-high (mur anti-Psyker : Terrifying + Parry + DaughterOfTheAbyss −Psychic ; Talons Direct +dmg one-shot un caster fragile ; scale cumulatif/actif allié = snowball si laissée vivante) · counter=si ENNEMI, l'attaquer au RANGED (bypass Terrifying) et en NON-Psychic (DaughterOfTheAbyss annule le Psychic vs elle) ; Parry → ne pas gaspiller un burst multi-hit dessus si autres cibles prioritaires (−1 hit) ; soft sans Resilient → tuable en réaction massée (vécu seed 96000 : tuée par Overwatch + réactions) ; si à MOI, l'engager adjacent à un caster ennemi (Direct anti-Psyker) · ⚠ **à MOI = OUTIL DIRECT-vs-Psyker/armor-bypass à RÉSERVER, NE PAS sur-étendre** : Talons range 1 + un seul move/tour → un move vers une tuile NON-adjacente à un ennemi = STRANDED gâchée (vécu seed 70008 : committée sans vérifier l'adjacence → finie sans cible, focus-killée T1 = perte de mon 2ᵉ bypass-armure → tank ungrindable, loss) → vérifier la légalité du move + l'adjacence AVANT de committer son unique move ; la garder shallow/screenée pour le tank high-armor émergent ; ⚠ **vs un Atlacoya ENNEMI (mirror), mes ranged dealers l'ignorent** : son angle Talons-Direct-vs-Psyker est MOOT si mon roster n'a aucun Psyker → corps soft sans Resilient tué dans le dive (vécu seed 70056) [n=4, 96000/95002/70008/70056]`
  `▸ Tac (n+1 scaling TalonsOfTheEmperor CONFIRMÉ self-play consensus, seed 80000 W) : **le bonus cumulatif/actif allié est MASSIF en fin de bataille** — avec seulement 2 actifs alliés joués avant son tour, Atlacoya a one-shot-finisher un anchor full-HP depuis l'adjacence. DOCTRINE : séquencer les actifs alliés AVANT TalonsOfTheEmperor (chaque actif allié joué avant son tour gonfle son prochain cast). ⚠ cross-validé par les DEUX sides du self-play (A observé son output ; B identifié la menace côté theirs) [self-play consensus, seed 80000] [n=5, 96000/95002/70008/70056/80000-sp]`
  `▸ Tac (RÉVISION MENACE — vs un roster PSYKER-HEAVY, seed 70055) : menace=CRITICAL (pas med-high). DaughterOfTheAbyss réduit le Psychic de mes Psyker-dealers à quasi-rien (plans Psychic vs elle TOUTE la partie, restée near-full) → elle hard-countre le profil de dégâts ENTIER d'un roster Psyker-heavy : Psychic négaté + Terrifying blunte ma mêlée + Parry −1 multi-hit + Talons Direct one-shot un Psyker fragile. Pour un tel roster elle est quasi-IMTUABLE et devient le counter-engine STRUCTUREL de la wincon adverse (endgame injouable, seed 70055 L). COUNTER = la tuer EARLY avec du dégât NON-Psychic NON-Terrifying-réduit (RANGED Blast/Physical d'un non-Psyker) ; NE PAS s'appuyer sur des Psykers pour la casser ; si mon roster est Psyker-heavy sans source non-négatée, FLAGGER la loss STRUCTURELLE au recon (son aura anti-Psychic est LIVE précisément parce que je fielde des Psykers). ⚠ menace contextuelle : la carte KIT liste med-high (générique) ; vs Psyker-heavy c'est CRITICAL — le roster décide [n=1, 70055]`
- **admecMarshall « Tan Gi'da » (AdMech, summon-engine)** — `DoctrinaImperatives` (switch Protector +Armure / Conqueror +dmg vs armure réduite, 1×/tour ; **peut attaquer après le switch**). Passif `ControlEdict` : sous **Protector**, après CHAQUE attaque de Tan Gi'da, summon gratuit d'un **Skitarii Vanguard** dans un hex adjacent libre, **cap 5** ; sous **Conqueror**, les summons Mechanical adjacents co-attaquent sa cible. Summons indépendants/persistants → un roster low-output se fait **out-attritionner**. **Tuer Tan Gi'da ou casser Protector, pas les Vanguards un par un.** Vanguards = Toxic r2 + RadSaturation. (cf. gameconfig --ability DoctrinaImperatives, --trait ControlEdict|Summon)
  `▸ Tac: rôle=engine (summon-engine) · menace=CRITICAL (sous Protector summon 1 Vanguard/attaque, cap 5, persistants + donne +armure aux Mechanical adjacents = blinde la grappe + crit-dmg) · counter=tuer Tan Gi'da OU casser Protector pour stopper le snowball — ne JAMAIS clear les Vanguards un par un (un low-output se fait out-attritionner) ; le +armure se bypasse au **Psychic NoBlocking** (cf. §1) ; ranged r2, à atteindre tôt — s'il reste hors reach il summon le board entier (vécu seed 98003 : jamais atteint, a aidé à tuer mes carries via les Vanguards) [n=1]`
  `▸ Tac (n+1 MINE, seed 70057 W, ControlEdict-Protector confirmé Verif) : Tan Gi'da côté MIEN = SCREEN-engine. Sous Protector, chaque attaque normale summon un Vanguard sur un hex adjacent libre (cap 5) → mes attaques génèrent des corps-écrans qui SOAKENT le focus ranged ennemi (drone + Vanguard ont absorbé ~14k vécu). Usage = attaquer chaque tour sous Protector pour fabriquer un mur de bodies devant mes fragiles ; MAIS ⚠ NE PAS la pousser forward pour chip (vécu : corps avancé chunké = over-extension n+1) : la garder shallow, ses Vanguard font le screen, pas son corps. La branche Conqueror fait plutôt co-attaquer tous les Mechanical Summons adjacents sur sa cible. [n=1, 70057-mine]`
- **admecRuststalker « Exitor-Rho » (AdMech, mêlée, move4)** — `CordClaw` (Melee **Direct Pierce** → ignore armure ; vs Resilient floored à 1, prévoir finisher). Traits `Infiltrate` (ne déclenche PAS l'Overwatch) + `Unstoppable` (ignore les effets de hex qui stoppent). Passif `OptimizedGait` : la clause « se déplace sur l'hex du mort » fire dès qu'un ennemi **ADJACENT** à lui est défait par **N'IMPORTE QUEL ami Mechanical** (pas seulement lui) → un kill d'un allié Mechanical peut le **tirer involontairement en avant** sur l'hex vacant ; surveiller l'exposition. ⚠ **Finisher létal à TOUT HP** : move4 + Infiltrate + Direct armor-ignore lui permettent de traverser le board et de one-shot un fragile même à très bas PV (vérifié seed 97001 : à très bas HP il a traversé pour tuer un fragile). (cf. gameconfig --ability CordClaw, --trait Infiltrate|Unstoppable|OptimizedGait)
  `▸ Tac: rôle=chaff/finisher · menace=HIGH (PAS low/skirmisher — move4+Infiltrate+CordClaw Direct armor-ignore = finisher mobile qui ignore armure ET Overwatch) · counter=LE TUER quand un kill est dispo, ne JAMAIS le laisser à bas-PV « parce qu'il est spent » (à bas HP il a reach-killed un fragile) ; sa mobilité + armor-ignore font d'un Exitor bas-PV un kill garanti sur un fragile au tour suivant ; OptimizedGait peut aussi le tirer en avant via les kills d'alliés Mechanical · ✅ **à MOI = OUTIL ANTI-ARMURE PRÉCIEUX À RÉSERVER/PROTÉGER** : CordClaw Direct Pierce = un de mes seuls bypass d'un tank double-armure → ne PAS le sur-étendre T1 (vécu seed 70008 : Exitor over-étendu T1 → focus-killé → perte de mon SEUL bypass du tank MkXGravis → tank ungrindable, loss) ; le garder SHALLOW/screené pour le tank high-armor émergent ; il one-shot aussi un summon-engine soft = finisher d'engine [n=2, 97001/70008]`
- **admecDestroyer « Sy-gex » (AdMech, move2, Mechanical/Vehicle/HeavyWeapon)** — **Overwatcher RANGED trait-natif** : arme normale multi-hit Physical r3 → s'il n'attaque pas en NORMAL, il s'arme en Overwatch et **tout ennemi qui BOUGE dans son arc r3 (mêlée OU non)** se prend la volée gratis au tour adverse (peut quasi one-shot un entrant AVANT qu'il agisse). `SentinelDirectives` (actif r3, 1 hit + Suppress, interdit si ennemi adjacent) **ne finit PAS son tour et ne DÉSARME PAS l'Overwatch** — seule une **attaque NORMALE** désarme → **fire-then-overwatch double-menace** le même tour. `HeavyGravCannon` (+dmg/+pierce vs Gravis/TerminatorArmour/Mechanical → tape plus fort un terminator). `HeavyWeapon` (+ranged s'il n'a pas bougé). Counter (cf. §1 Overwatch) : ne PAS pather dans l'arc r3, out-range, ou forcer l'OW sur un chaff d'abord ; Vehicle → BeastSlayer applicable. (cf. gameconfig --ability SentinelDirectives, --trait HeavyGravCannon|HeavyWeapon|Overwatch)
  `▸ Tac: rôle=carry/control · menace=high (ranged punch + Overwatch armé r3 + HeavyGravCannon anti-Terminator) · counter=ne JAMAIS pather dans son arc r3 ; le tuer/déplacer ou forcer l'OW sur un chaff avant de bouger une unité de valeur dedans ; ⚠ HeavyGravCannon (+dmg/+pierce vs TerminatorArmour/Mechanical) = menace EXTRÊME pour un terminator allié → tuer Sy-gex TÔT si je joue du Terminator (vécu seed 95001) ; pas Resilient, soft → kill franc une fois en portée ; Mechanical = les dégâts COLLENT (pas de heal-back) → bait son actif avec une adjacency-bait ou le chunk-finir (vécu seed 70004 : tué par la riposte FinalJustice quand il a focus-killé) [n=3]`
  `▸ Tac (n+1 OW-DISARM/RE-ARM cross-observé, seed 80042) : ⚠ NUANCE de timing OW cross-confirmée des DEUX sides — l'Overwatch r3 armé tire UNE volée sur le 1er mover dans l'arc (peut one-shot) puis **DISARME pour le RESTE du tour ennemi** (un 2ᵉ mover passe dans l'ancien arc sans réaction) ; il **RE-ARME au début de SON propre tour** (gate=not-attacked). EXPLOIT à MOI : une fois Sy-gex a fire son OW, l'arc est SAFE jusqu'à son prochain tour → avancer le reste du bulk APRÈS le 1er trigger (sacrifier un corps durable pour spend l'OW, puis closer). EXPLOIT contre lui : un actif Suppress (ex. SuppressiveFire = Pin/Suppress) DÉSARME l'OW pour ce tour sans entrer dans l'arc (seed 80042). ⚠ GAP outillage confirmé : pas d'overlay des arcs OW armé → le danger-zone number ne flag PAS le one-shot OW, à calculer à la main [n=2, 93000/80042]`
- **admecManipulus « Actus » (AdMech, repair-engine, Mechanical)** — `DefendTheDivineWork` (seul actif — PAS une attaque normale, cf. §1) : **répare self + adjacents** ET via `GalvanicField` **chaque unité réparée fait immédiatement une attaque gratuite** = moteur **sustain + action economy**. `DefendTheDivineWork` strip aussi les effets négatifs des réparés (= cleanse, ex. retire Markerlight, cf. §1). Soft (**pas Resilient**) → focalisable sur la tuile d'engagement. ⚠ déni : un heal/repair-block (ex. Mephiston `FuryOfTheAncients`) coupe ses réparations.
  ⚠️ **DEUX vecteurs de réparation S'ADDITIONNENT par cycle de tour** : `DefendTheDivineWork` (self + adjacents) **+** trait **Mechanic** (action de réparation = Damage × hits ; Actus est aussi Mechanical → réparable par d'autres Mechanics). Le heal observé en un tour **dépasse le plafond DefendTheDivineWork seul** → preuve que les deux sources se cumulent. **Conséquence H02 LITTÉRALE pour un repair-engine** : un chip non-létal est **ENTIÈREMENT effacé** au tour suivant → **kill CE tour ou ne pas committer** ; ne PAS sur-étendre un corps pour le chiper. Il kite (move3) en backline après réparation. (cf. gameconfig --ability DefendTheDivineWork, --trait Mechanic, --effect GalvanicField)
  `▸ Tac: rôle=engine · menace=critical (DefendTheDivineWork + Mechanic action additifs = heal au-delà du plafond DTDW ; GalvanicField free-attack par réparé) · counter=kill FIRST (H02) en UN tour, soft & non-Resilient → focus down depuis tuiles SHALLOW (ne JAMAIS sur-étendre un corps pour le chiper : chip effacé + corps stranded = vécu seed 97002) ; OU heal-block FuryOfTheAncients ; soit le kill sécurisé, soit le laisser vivre ; ⚠ **n+1 (vécu seed 70061, CONTRIBUTING ROOT CAUSE)** : après avoir tué le summoner, j'ai seulement CHUNKÉ Actus et HOLD au lieu de sécuriser le kill depuis le shallow → Actus a SURVÉCU jusqu'au timeout round-10 (EnvEndBombardment) = un repair-engine non-fini est un clock qu'on perd ; le « kill ce tour ou ne pas committer » est LITTÉRAL — une fois le summoner mort, Actus DEVAIT devenir le focus #1, pas un chip ; NB DefendTheDivineWork répare ANY adjacent friendly (PAS Mechanical-gated) donc l'engine est LIVE dès qu'Actus a des alliés adjacents, même s'il est le seul Mechanical [n=3, 97002/.../70061]`
- **deathBlightlord « Maladus » (Death Guard, move2 lent, Resilient + TerminatorArmour, ~12k PV)** —
  **anvil d'attrition.** `ContagionsOfNurgle` (aura −armure aux ennemis dedans, **s'étend r1→r3** sur les
  rounds — snowball offensif/défensif). `FlailSwing` (~10k burst mêlée single-turn, overkill sur défaite +
  chaîne Haze). Move2 (lent) → **KITER**. Stack défensif : `Resilient` (1 PV sauf Overkill) +
  `TerminatorArmour` (1ʳᵉ attaque/tour réduite **SAUF Psychic/Direct**) + 12k PV → nécessite un **burst
  2-hit-ou-Overkill** Psychic/Direct, PAS du chip. ⚠️ **Hard-counter d'un roster all-melee SANS
  Psychic/Direct** : chaque tour-d'attaque frais retape la réduction Terminator empilée à l'armure de base
  + aura −armure → mes coups mêlée Pierce-only floorés (= effectivement INKILLABLE). Bypass = Psychic/Direct
  OU Overkill/multi-hit. (cf. gameconfig --ability ContagionsOfNurgle|FlailSwing, --trait Resilient|TerminatorArmour)
  `▸ Tac: rôle=anvil · menace=high (one-shot des fragiles, quasi-inkillable) · counter=KITER (move2) ; bypass Terminator au Psychic/Direct (seuls à ignorer le −75% 1ʳᵉ-hit) ; budgétiser un burst 2-hit/Overkill, jamais du chip ; ⚠ pour un roster all-melee SANS Psychic/Direct = MUR INFRANCHISSABLE → traiter comme une loss structurelle au recon, NE PAS l'engager, gagner sur les softs avant que l'attrition tourne (vécu seed 97002 : mêlée Pierce-only vs lui = nul) [n=1]`
  `▸ Tac (CONFIRM bypass-Psychic = killable + FlailSwing-focus-kill, seed 70059 W) : avec un outil Psychic Pierce100 (Typhus PlagueWind/Archimatos), Maladus est TUABLE proprement — le Psychic bypasse TermArmour à plein (chunk franc), puis floored par un Psychic, puis tué DEPUIS le floor par un extra-hit (multi-hit bat Resilient une fois floored, cf. §1). CONTRASTE avec 97002 (all-melee sans bypass = mur) : un roster AVEC Psychic/Direct le crack. ⚠ FlailSwing ~10k burst CONFIRMÉ focus-killer d'un carry forward → ne JAMAIS présenter un carry adjacent à Maladus ; sa lenteur move2 permet de kiter mais s'il atteint un fragile = ~10k. (cf. gameconfig --ability FlailSwing|PlagueWind) [n=1, 70059]`
- **worldJakhal « Macer » (World Eaters, mêlée, Resilient)** — `JakhalStimms` (cleave Melee Physical sur la
  cible **+ tous les ennemis adjacents À LA FOIS à Macer ET à la cible** = cône d'adjacence-aux-deux,
  gameconfig-confirmé ; coûte un % de la PV COURANTE de Macer ; **NE termine PAS son tour** → enchaîner une
  attaque normale le même tour, ~8400 burst observé). Le **volume multi-hit overcome le Terrifying**
  (réduction-mêlée) d'une cible déjà chunkée → **double-kill une activation** (cleave K! une cible + splash
  chunk un voisin adjacent-aux-deux, puis attaque normale finit le voisin). `Skullsmasher` (+dmg par PV
  manquant + Stun après 1er kill). `Resilient`/`BlessingsOfKhorne`. (cf. gameconfig --ability JakhalStimms|Skullsmasher, --trait Resilient)
  `▸ Tac: rôle=carry · menace=high (burst single-turn ~8400 : JakhalStimms cleave AoE + normale, no-turn-end ; Resilient = last-man) · counter=le focus-reaction (pas Resilient-proof : multi-hit/Overkill) ; ne PAS clusterer mes unités adjacentes-aux-deux d'une cible qu'il vise (cleave les attrape) ; à MOI = double-kill-engine T2 (le multi-hit splash bat le Terrifying d'une cible chunkée — vécu seed 97000) [n=1]`
- **eldarMauganRa « Maugan Ra » (Aeldari, ranged r3, move3, carry fragile ~4248-7029 PV)** — garder
  **STATIONNAIRE** empile 3 bonus gatés « has not moved/attacked » : `HeavyWeapon` (+dmg ranged),
  `InescapableAccuracy` (s'il n'a PAS bougé : ses tirs ranged **ignorent les réductions de hit** →
  **BYPASSENT le Camouflage** de Shadowsun/Deathleaper ; +crit chance/dmg ; **s'applique aux cibles de
  HarvesterOfSouls ET aux tirs Overwatch**), `Overwatch` : riposte tout ennemi entrant en portée — ⚠ **gate
  = NOT-ATTACKED (PAS not-moved)** : Maugan Ra peut **bouger PUIS armer son Overwatch** et **reste ARMÉ
  across turns tant qu'il ne tire pas** (Overwatch_AutoAttack = effet critical persistant) — disarm
  seulement après un tir → l'attaquer depuis hors de son arc évite le trigger [self-play consensus, seed 80020].
  Chaque ennemi entrant en portée déclenche une **riposte SÉPARÉE** → une mêlée/summon qui walk ses unités
  une par une se prend une volée par mover (cascade KILLs). `HarvesterOfSouls` (actif r3) : **vraie AoE
  multi-cibles** — sur la cible + **TOUS les ennemis adjacents à la cible ET en range 3 de Maugan Ra**
  (cleave dévastateur sur une grappe de dive) ; **+1 hit supplémentaire si Maugan Ra n'a PAS bougé**, et
  InescapableAccuracy s'applique aux cibles. **Bouger pour atteindre une cible drop les 3 bonus ET expose la
  carry** → tourelle stationnaire de dissuasion/chip, ne repositionner que sous pression dure. (cf. gameconfig --ability HeavyWeapon|InescapableAccuracy|HarvesterOfSouls, --effect Overwatch_AutoAttack)
  `▸ Tac: rôle=carry · menace=critical SI statique, HIGH si l'IA le fait bouger (tourelle OW statique : HeavyWeapon + InescapableAccuracy bypass-Camouflage + HarvesterOfSouls AoE r3 punit tout mover) · counter=NE PAS walker mes movers UN PAR UN dans sa r3 (chaque entrée = une riposte SÉPARÉE — vécu seed 70006) ; le FORCER à bouger (zoner/menacer en mêlée) pour stripper les 3 bonus statiques ET son Overwatch ET restaurer la protection Camouflage (vécu seed 70006 : IA agressive l'a fait bouger chaque tour → menace DOWN critical→high) ; fragile (~7029, pas Resilient) une fois isolé → fini avec une K! depuis la tuile courante ; approcher seulement sous Infiltrate (no-OW) — ne respecte PAS Camouflage quand statique [n=2, 70006]`
- **eldarRanger « Calandis » (Aeldari, ranged r3, fragile ~7029, pas Resilient)** — `HeavyWeapon` (+dmg
  ranged **s'il n'a PAS bougé**). `FireAndReposition` (attaque + repli ; ⚠ **gate « target in range » →
  rejet mutated=false sans cible valide en portée**, cf. H24 ; **dépense l'Overwatch du tour** → après
  l'avoir usée T1, **plus d'OW T2**). `WireweaveNet` (contre une attaque mêlée NORMALE ; ⚠ **si l'attaquant
  meurt, son attaque mêlée est annulée** → ne PAS poke-mêlée un fragile dessus). `Overwatch` quand
  stationnaire. (cf. gameconfig --ability HeavyWeapon|FireAndReposition|WireweaveNet)
  `▸ Tac: rôle=carry · menace=med (chip ranged + OW + WireweaveNet counter ; HeavyWeapon si immobile) · counter=la tuer au RANGED ou avec un corps EXPENDABLE (WireweaveNet punit le poke mêlée normal + annule l'attaque si l'attaquant meurt) ; la focus TÔT (fragile, pas Resilient = tout K! franc) ; exploiter qu'elle dépense l'OW via FireAndReposition T1 → safe d'approcher T2 ; ⚠ **n+1 (vécu seed 70061)** : un fragile ranged qui dive forward T1 + caste FireAndReposition (OW dépensé) se fait reaction-kill GRATIS T2 (chunk melee + un Overwatch held finit) = easiest kill du match [n=2, …/70061]`
- **genesPatriarch « The Patermine » (Genestealer, Legendary, move4, Infiltrate/Synapse/Terrifying/
  Unstoppable)** — `MightFromBelow` : **Psychic Pierce100 + NoBlocking** (ignore armure/block, brutal vs
  briques armurées), puis summon une Purestrain Genestealer sur **CHAQUE decoy adjacent au Patermine**
  (attaque mêlée immédiate, pas de move ce tour). Decoys via passif `CosmicHorror` (posés quand le Patermine
  LUI-MÊME tue ; +heal si le Patermine marche sur un decoy). Purestrain (genesSmnGenestealer) : move3 mêlée,
  Infiltrate (pas d'Overwatch) + Ambush (1ʳᵉ mort → decoy + resurrect full ; 2ᵉ kill permanent). **Garder les
  carries armurées hors de l'adjacence du Patermine + nier les decoys.** ⚠ **SNOWBALL ENTIÈREMENT
  KILL-GATED** : un kill via MightFromBelow chaîne IMMÉDIATEMENT en un Genestealer sur l'hex du mort
  (kill→CosmicHorror decoy→summon, même tour) → **nier les kills au Patermine = nier les decoys = nier les
  summons**. Le contre est POSITIONNEL (ne présenter AUCUN fragile killable dans son move4 reach), pas
  réactif. ⚠ **Summon DÉCOY-GATED, PAS cast-gated (vérifié seed 70009)** : `Ability_Summon` fire à CHAQUE
  cast de MightFromBelow mais **produit RIEN s'il n'y a aucun decoy adjacent** (sans kill préalable → 0 unité
  spawnée). Le Psychic Pierce100 tape toujours ; seul le summon est gaté sur les decoys (= sur les kills du
  Patermine). (cf. gameconfig --ability MightFromBelow, --trait CosmicHorror|Infiltrate|Ambush)
  `▸ Tac: rôle=carry · menace=critical (snowball self-feeding kill-gated + Psychic Pierce100 ignore armure + move4 reach + Terrifying → bypass = RANGED, ma mêlée fait réduit) · counter=DENY-KILL positionnel (aucun fragile dans son move4 reach = pas de decoy = pas de snowball) ; le tuer au RANGED tôt avant son 1er kill ; une fois qu'il a tué une fois le snowball est live et un set de survivants mêlée ne le rattrape pas [n=1]`
- **genesPrimus « Isaak » (Genestealer, GSC, move3, Ambush+Hero)** — `CultDemagogue` (actif r2) : cible un
  ennemi ≤2 hex, éparpille jusqu'à **8 decoys** ≤2 hex autour, puis summon des **Neophyte Hybrids sur LA
  MOITIÉ** des decoys qui **prennent immédiatement un tour** (Summon auto move+attack) = **board-flip + flanc
  en un tour**. Neophytes ranged r2, chacun `Ambush` (resurrect sur decoy ami). ⚠️ Isaak a AUSSI `Ambush` →
  un seul kill ne le retire pas (resurrect full-HP sur un decoy ami survivant au début de son prochain tour,
  CONDITIONNEL : aucun decoy ami survivant quand son tour commence → reste mort). **Tuer Isaak AVANT le
  cast** (H02 prime sur H03 vs summoner+reviver) ET nier/clear les decoys. (cf. gameconfig --ability CultDemagogue, --trait Ambush)
  `▸ Tac: rôle=engine (board-flip summoner) · menace=CRITICAL (proximate wincon-enabler : 1 cast CultDemagogue au tour ennemi = board-flip massif — Neophyte Hybrids ranged r2 chacun Ambush + decoys prenant un tour IMMÉDIAT ; pas Resilient mais Ambush) · counter=DOIT mourir AVANT sa fenêtre de cast (T2 au plus tard) ; backline + Ambush (exige 2 kills/clear-decoy) → si INATTEIGNABLE T1 sans dealer r3+/deep-strike = reach-fail STRUCTUREL → flagger la loss et jouer un turret défensif plutôt qu'avancer des fragiles dans le reach ; ⚠ ne PAS dépenser mon unique vrai tour sur le LESSER engine (Yarrick) en laissant Isaak libre — tuer l'engine qui ENABLE l'écran, pas le plus facile (vécu seed 70007 ; cf. 91012) ; ⚠ **n+3 vécu** : Isaak backline INATTEIGNABLE à un roster melee/r2 = reach-fail structurel → board flippé avant toute fenêtre de kill = la loss [n=3, 91012/70007/70050 triggered-against-me]`
  `▸ Tac (À MOI — engine bidirectionnel, board-flip FOR me + Ambush self-resurrect, seed 70054 W) : CultDemagogue tout aussi DÉVASTATEUR quand JE le contrôle (cible ≤r2, decoys ≤2 hex, summon Neophyte Hybrids sur la MOITIÉ, TOUS agissent IMMÉDIATEMENT — Summon = auto move+attack ; chacun Ambush ; ranged r2). USAGE : le réserver pour SEIZE l'avantage numérique une fois l'ennemi aminci → vécu seed 70054 : cast tardif a délivré le surnombre qui a fini le combat. ⚠ Isaak `Ambush` (à MOI) : 1ʳᵉ mort → resurrect full-HP sur un decoy ami survivant au DÉBUT de son prochain tour puis agit IMMÉDIATEMENT — CONDITIONNEL au decoy survivant. SOURCE-à-protéger côté moi = Isaak (le board-flip engine) ; un kill sur Isaak n'est que TEMPORAIRE tant qu'un decoy survit [n=1, 70054 chained]`
- **deathTyphus « Typhus » (Death Guard, ~12047 PV, mêlée lent, Resilient + TerminatorArmour)** —
  **anvil d'attrition + AoE Psychic.** Passif **`DestroyerHive`** : au DÉBUT de CHAQUE tour de Typhus,
  inflige du **Direct Damage (Piercing 100, ignore l'armure)** à **UN ennemi adjacent aléatoire** — ⚠ **PAS**
  du friendly-fire ni du self-damage : la cible est un ennemi adjacent de Typhus. **Implication : ne JAMAIS
  laisser une unité fragile (support/glass-cannon) collée à Typhus au début de son tour** (one-shot
  possible). `PlagueWind` (AoE Psychic Pierce100, **NoBlocking**, multi-cible : primary + adjacents).
  `Resilient` (1 PV sauf Overkill) + `TerminatorArmour` (1ʳᵉ attaque/tour réduite SAUF Psychic/Direct) + 12k
  PV = nécessite un **burst multi-hit/multi-source en un tour** (la 2ᵉ attaque distincte bypasse
  TerminatorArmour ; Overkill ou multi-hit bypasse Resilient) — Psychic/Direct passent à plein. **Impossible
  à tuer proprement 1v1** (vécu seed 96000 : tué en réaction par 7 sources distinctes). (cf. gameconfig --ability PlagueWind, --trait DestroyerHive|Resilient|TerminatorArmour)
  `▸ Tac: rôle=anvil · menace=critical (12047 HP + Resilient + TerminatorArmour + DestroyerHive auto-dmg adjacent start-of-turn + PlagueWind r2 Psychic Pierce100 NoBlocking AoE) · counter=multi-source focus en UN tour pour bypasser TerminatorArmour (2ᵉ attaque distincte tape plein) + Overkill/multi-hit pour bypasser Resilient ; Psychic/Direct bypasse TerminatorArmour ; NE PAS laisser une unité fragile adjacente à son démarrage de tour (DestroyerHive one-shot) ; ⚠ il est l'ÉCRAN (anvil) — casser les SOFT engines derrière lui (Isaak/Isabella) plutôt que de chiper Typhus ; ⚠ vécu seed 70050 : PlagueWind a frappé mon cluster + tué un fragile dans le focus [n=2, 96000/70050]`
  `▸ Tac (À MOI — anvil bidirectionnel + outil de bris anti-TermArmour, seed 70059 W) : Typhus est un anvil-baiteur PARFAIT pour MON côté — 12k Resilient/TermArmour ancre un cluster que l'ennemi all-melee est CONTRAINT de diver. Son PlagueWind = LE bris d'un mur d'anvils : Psychic AoE Pierce100 NoBlocking bypasse TOUT TermArmour/Resilient/armure à PLEIN sur chaque cible (vécu : softène 3 anvils en UN cast, malgré TermArmour). DestroyerHive (auto-Direct StartTurn) = chip GRATUIT sur un ennemi adjacent à mon démarrage de tour → positionner Typhus collé à un anvil ennemi en fin de mon tour précédent pour le farmer. USAGE : ancre forward + ouvrir la salve sur un cluster d'anvils groupés avec PlagueWind → softène plusieurs anvils simultanément, enable les multi-kills suivants [n=1, 70059]`

- **deathRotbone « Nauseous Rotbone » (Death Guard, Chaos, mêlée lent, Resilient + Healer)** —
  **engine de sustain/revive.** ⚠ **Quirk Healer vs active** : son trait `Healer` peut soigner
  **N'IMPORTE QUELLE faction alliée** (Xenos/Imperial inclus, PAS restreint Chaos) pour un GROS heal
  (~5000+) — à NE PAS confondre avec son active `RevitalizingMalignancy` qui ne soigne que self+adjacents
  Chaos (0 aux Imperial). Un gros heal sur un allié non-Chaos vient du TRAIT, pas de l'active.
  `TaintedNarthecium` (passif) : revive un Chaos **ADJACENT** défait (gate = mort de Chaos adjacent ; le
  flag « actif » apparaît chaque tour mais ne fire que sur cette condition). (cf. gameconfig --trait Healer,
  --ability RevitalizingMalignancy/TaintedNarthecium/ContagionsOfNurgle)
  `▸ Tac: rôle=engine · menace=critical (Healer = heal toute faction annule chunks/kills + revive Chaos adjacent) · counter=le tuer TÔT et AVANT accumulation de pertes Chaos adjacentes ; Resilient → multi-hit/2ᵉ source/Overkill (vécu seed 98004 : K! TROMPEUR — max-hit < HP → floor, fini multi-hit Chain) ; sa mort empêche le revive de boucler sur un Chaos tanky (vécu seed 96000 : tué T3 multi-source = revive nié) ; ⚠ son **TaintedNarthecium-revive est STRUCTURELLEMENT INERTE** dans un roster où il est le SEUL Chaos (aucun Chaos adjacent à revive) → la menace = le HEAL, PAS le revive ; coupler le kill avec un HEAL-BLOCK (Mephiston FuryOfTheAncients) qui nie heal/revive (vécu seed 98004) [n=2]`
  `▸ Tac (n+1 à MOI = anti-armure + revive-INERTE, seed 70060 W) : ✅ ContagionsOfNurgle −armure aura (s'étend r1→r3) appliquée aux ennemis qui entrent dedans = OUTIL ANTI-ARMURE qui offset PARTIELLEMENT un double-armure ennemi → aide un roster SANS Direct/Psychic/Crit à grind le mur. ⚠ son **heal/revive = STRUCTURELLEMENT INERTE si Nauseous est le SEUL Chaos de MON roster** (heal ne donne RIEN aux Imperial ; revive Chaos-only → aucun Chaos à revive ; heal ne profite qu'aux Xenos alliés) → recon-flagger l'inertie, ne pas compter sur le revive. MÊME classe d'engine-inerte que 98004 mais ici DANS mon propre roster [n=3, 96000/98004/70060]`
- **eldarFarseer « Eldryon » (Aeldari/Xenos, ranged caster, fragile)** — **Doom engine / control.**
  Passif aura `Doom` : gate = **distance EXACTE 2 hexes** (PAS plus près, PAS adjacent, PAS ≤2) → les
  ennemis marqués prennent +Damage des attaques normales des AUTRES alliés, et les alliés Aeldari déalent
  +Damage avec TOUTES leurs attaques vs les marqués. ⚠ **owner = Eldryon, PAS un générique « Farseer »**
  (corrige une mésattribution courante). `Executioner` scale par round → exponentiel R5+. **PAS de
  Resilient/FinalJustice, fragile → glass cannon tuable T1-T2 si focus.** (cf. gameconfig --ability Doom/Executioner)
  `▸ Tac: rôle=engine · menace=critical (Executioner scale Psychic/round → board-wipe exponentiel après R3 ; Doom +dmg aux ennemis à exactement 2 hex) · counter=le tuer dans la FENÊTRE T1-T4 AVANT que l'Executioner monte (fragile, pas Resilient/FJ = priorité ABSOLUE) ; garder mes unités HORS des 2 hex exacts de Doom ; ⚠ peut être ré-healé full par un Healer adverse (Nauseous) → le focus doit l'ACHEVER, pas le chunker (vécu seed 96000 : ré-healé full T2 → tué T3 ; seed 96002 : tué T4 near-miss, 1 tour de plus = scaling létal) ; ⚠ **STRUCTURELLEMENT INATTEIGNABLE derrière un screen all-ranged (turret+drones) pour un roster melee-heavy SANS reach tool** → reach-fail (vécu seed 70052 : l'engage coûtait 3-for-1 par guard, loss structurelle à flagger au recon) [n=3, +70052]`
- **templAncient « Thoread » (Imperium, Black Templars, mêlée, buff-tank + FinalJustice)** —
  `UnbreakableDuty` (actif, range 2) : buff self/friendly-area (−Damage à self + alliés ≤2 hex jusqu'à
  début de leur prochain tour). ⚠ **ne prend PAS de cible ennemie** : viser un ennemi renvoie
  `mutated=false` MAIS le buff allié s'applique quand même → vérifier le type de cible d'un actif défensif
  avant de le caster (vécu seed 96000 : ciblé une ennemie = tour à demi-gâché). Effet conditionnel : si
  **2+ Imperial Characters alliés morts**, Thoread gagne +HP/+Damage jusqu'à fin de bataille et frappe un
  adjacent. Trait `FinalJustice` (cf. §1 — attaque normale à la mort sauf Overkill). (cf. gameconfig --ability UnbreakableDuty, --trait FinalJustice)
  `▸ Tac: rôle=anvil/control · menace=med (buff d'équipe −dmg + scaling conditionnel sur pertes Imperial) · counter=N/A (à MOI) · usage=UnbreakableDuty est self/friendly-area (caster SANS cible ennemie, --to une zone alliée) ; le garder au cœur de la grappe pour l'aura ; FinalJustice = riposte de mort utile en réaction [n=1]`
  `▸ Tac (DEMOTE quand ENNEMI — scaling conditionnel INERT, seed 70054) : ⚠ le scaling de UnbreakableDuty exige « 2+ Imperial Characters alliés MORTS » → STRUCTURELLEMENT INERTE si Thoread est le SEUL Imperial de SON roster (trigger ne peut JAMAIS s'armer). RÈGLE DE RECON (engine/conditionnel-inerte, miroir H02/§6) : COMPTER les bénéficiaires/déclencheurs VALIDES d'un conditionnel AU RECON avant de craindre son scaling ; ici 0 autre Imperial → demote Thoread à un PLAIN killable tank (no-Resilient) + aura −dmg d'équipe + FinalJustice. Vécu seed 70054 : scaling jamais armé → traité en corps killable, chunké en ~2 tours, fini en normale. L'aura −dmg RESTE active (non-conditionnelle) → le tuer coupe AUSSI la réduction d'équipe [n=1, 70054]`
- **eldarAutarch « Aethana » (Aeldari, mêlée, no Resilient)** — passif `PathOfCommand` (aura, range 2) :
  les autres alliés ≤2 hex gagnent +Damage, +Crit, et les alliés Aeldari un +Damage additionnel.
  **Positionnel** : suit Aethana → la bouger hors de portée strip le buff de groupe ; la garder centrale au
  cluster. `Flying` + `TeleportStrike` (deep strike, cf. §1 — **non-ciblable jusqu'à sa 1ʳᵉ action OU fin
  de tour ; landing = action → protection tombe immédiatement**) ; actif mêlée `SwoopingHawk` → auto-finish
  si posée non-adjacente (cf. §1). ⚠ **vécu seed 70051** : l'IA la pose en AVANT (PathOfCommand range-2
  incite à rapprocher de la grappe) → landed FORWARD T1 → dès qu'elle a agi/landed = ciblable et ATTEIGNABLE
  → K! T3. Un deep-striker buff-engine qui sort forward s'auto-expose au focus. (cf. gameconfig --ability PathOfCommand)
  `▸ Tac: rôle=engine (buff-engine) · menace=high (PathOfCommand +dmg/+crit aux alliés ≤2hex = dépompe TOUTE l'équipe ; Flying + TeleportStrike = intouchable jusqu'à sa 1ʳᵉ action) · counter=intouchable en deep-strike, MAIS dès qu'elle land/agit elle est ciblable → si elle sort FORWARD (l'IA le fait pour le buff range-2) elle devient atteignable au tour suivant → K! (no Resilient → tout K! la tue ; vécu seed 70051 : sortie forward T1 → tuée T3) ; la tuer = dépomper l'équipe entière ; si à MOI, la poser ARRIÈRE/flanc, jamais forward si la menace adverse peut la cibler dès T2 [n=1, 70051]`
- **custoVexilusPraetor « Aesoth » (Custodes, mêlée)** — `VexillaMagnifica` (Melee, adjacent, cd2,
  REPEATABLE) : frappe la cible adjacente ET un 2ᵉ ennemi adjacent (Physical), **Stun les DEUX pour 1 ROUND**
  (pas 2 tours), et Aesoth gagne une auto-protection −dmg subi 1 round. Adjacency-gated : il faut 2 ennemis
  adjacents au cast pour les 2 stuns. ⚠ **outil de CONTROL d'abord, PAS un finisher** (vérifié seed 70006) :
  le STUN est garanti mais le dmg est fortement modifié par les buffs/blocks de la cible → ne PAS budgétiser
  VexillaMagnifica comme un K? fiable vs une cible à réduction ; la jouer pour le stun + auto-défense, finir
  avec une autre source. `Resilient`, `BigTarget` (alliés adjacents −1 hit ranged ; non-déplaçable),
  `MartialKatah` (−dmg des attaques NORMALES subies → bypass aux ACTIFS/Direct/Psychic), `StandVigil`
  (buffe les alliés +armure/+dmg). ⚠ **le stun CONVERTIT une unité sur-étendue en kill quasi-garanti** :
  une cible stunnée garde 1 Movement + son attaque normale (cf. §1 Stun — perd QUE ses ACTIVE) mais 1 move
  ≪ ce qu'il faut pour sortir d'une killzone → ne peut quasiment pas retreat → focus-kill (vécu seed 93000 :
  forward stunné → mort sans pouvoir reculer). C'est la pièce qui PUNIT mes erreurs de positionnement.
  ⚠ **côté HARNESS** : une unité À MOI stunnée n'est PAS « complètement bloquée » — ne pas l'`endturn`
  d'office ; elle conserve 1 move + attaque normale (vécu seed 96002 : le `mutated=False` sur mes actions =
  artefact runner, pas la sémantique du Stun ; attaque normale/Overwatch restaient exploitables).
  (cf. gameconfig --ability VexillaMagnifica/StandVigil, --trait BigTarget/MartialKatah)
  `▸ Tac: rôle=control/anvil · menace=high (Resilient + stun-lock qui transforme une sur-extension en kill quasi-garanti ; StandVigil buffe l'équipe +armure/+dmg) · counter=garder mes unités de VALEUR hors de son adjacence (pré-positionnement défensif AVANT qu'Aesoth atteigne ma ligne — vécu seed 96002 : a stunné 2 de mes units = activation perdue, évitable) ; bypass MartialKatah avec actifs/Direct/Psychic ; Resilient → Overkill/2-hit (vécu seed 98004 : Psychic K? l'a laissé à HP résiduel = K? TROMPEUR → Chain l'a fini en overkill) ; exploitable via le splash ARRIÈRE d'un burst double-target (vécu seed 98004) ; le tuer via réactions/Overwatch si je tiens une turret (vécu seed 96002 : tué par cascade Overwatch) ; ⚠ move3 mêlée → atteint ma ligne et melee-kill un fragile sur-étendu (vécu seed 70007 : melee-killé mon fragile forward) → garder les fragiles untouchable, ne pas les avancer dans le reach move3 ; ⚠⚠ **SOFT pour un Psyker/multi-source → le tuer TÔT vaut + que sa barre PV (engine de buff StandVigil)** : casser Aesoth retire StandVigil = DEPUMP l'équipe (durabilité ajoutée à ses alliés disparaît) (vécu seed 70005 : chunké en réactions puis TUÉ par l'EXPLOSION de mon propre Explodes adjacent → StandVigil retiré) ; ⚠ **À MOI = control-tool confirmé n+1** : hit 2 adjacents plein dmg + Stun 1 round les DEUX (bloque leurs ACTIFS, laisse leur normale usable) + auto-protection, REPEATABLE (~cd2) ; le stun-then-finish sur un engine est la séquence (vécu seed 70053 W) [n=6, 96002/98004/70007/70005/70053]`
- **tauAunShi « Aun'Shi » (Tau, buff-engine)** — `SereneUnifier` (range 2) : au début de son tour, buffe
  lui + adjacents + T'au ≤2 hex sur un **cycle de 3 rounds** (R1 SenseOfStone −dmg subi / R2 ZephyrsGrace
  +move / R3 StormOfFire +dmg), puis répète indéfiniment. ⚠ **2 quirks de durée non-déductibles** : le buff
  dure **jusqu'au début du prochain tour du PORTEUR** (donc le −dmg R1 couvre TOUT mon tour intercalé), et
  **les buffs déjà posés persistent 1 round même si Aun'Shi meurt/bouge** (le cycle cesse simplement de
  distribuer de NOUVEAUX buffs ; vécu : morte T2 → pas de Storm R3, mais les units buffées R2 gardent +move
  ce round). (cf. gameconfig --ability SereneUnifier, --effect SenseOfStone/ZephyrsGrace/StormOfFire)
  ⚠ **PHASE DE BUFF = nom de l'effet, PAS le label « tour » affiché (CONFIRMÉ seeds 70050, 80000)** : le
  cycle est tracké par le compteur de ROUND du jeu, jamais par un label UI « tour N » (qui peut rester figé
  sur un placeholder). → **lire le NOM de l'effet dans `decisionView.effects`** (ground truth de la phase),
  jamais le numéro affiché ; le round-state pilote la décision : phase R1 SenseOfStone (−dmg) favorise HOLD
  (laisser l'ennemi venir dans le cushion), PAS avancer dans l'ouvert où 7-10 ennemis focus à travers la réduction.
  ⚠ **RE-CONFIRMÉ self-play seed 80000 (run #4) par les DEUX sides indépendamment** : label UI placeholder figé sur « tour 3 » pendant les vrais tours 3/4/5 alors que l'effet RÉEL cyclait SenseOfStone (R1) → StormOfFire (R3). A et B ont chacun signalé la même friction → **toujours lire `decisionView.effects` (nom d'effet) pour la phase, jamais le compteur de tour affiché.** [self-play consensus, seed 80000, run #4]
  `▸ [self-play consensus, seed 80072]` Cycle RE-CONFIRMÉ n+1 par les DEUX sides (R1 −dmg / R2 +move / R3 +dmg à self+adjacents+T'au ≤2hex) ; le −dmg R1 a halvé l'alpha sur la phase ennemie / blunt le Psychic burst. **Tactique cross-validée** : le PERDANT (A) a correctement TIMED son alpha sur la phase NON-(−dmg) (bonne séquence) — mais MOOT face à un umbrella Apothecary qui a tout heal-off. → la timing-rule (« burster hors-phase −dmg ») reste correcte mais SUBORDONNÉE à « l'umbrella sustain rend tout kill non-permanent » : ne pas burster du tout tant que le reviver n'est pas neutralisé. [self-play consensus, seed 80072]
  `▸ Tac: rôle=buff-engine (cycle R1 −dmg / R2 +move / R3 +dmg sur Aun'Shi+adjacents+T'au ≤2hex) · menace=med (buff-engine fragile, no-Resilient) · counter=tuer Aun'Shi AVANT le round dont le buff me fait le plus mal ; ne pas burst les T'au buffés −dmg (attendre R2/R3 ou taper unbuffé) ; à MOI = jouer la phase via le NOM de l'effet (R1 SenseOfStone = HOLD, pas avance) [n=1, 70050]`
  `▸ Tac (n+1 à MOI, seed 70060 W) : ✅ buff-engine défensif décisif dans un mur de réaction — clusteriser mes T'au (+adjacents) près d'Aun'Shi AVANT le dive ennemi : les phases R1 −dmg ont fait SURVIVRE mon cluster au dive all-melee avec ZÉRO perte hero ; R3 +dmg a boosté mon chip au-dessus de l'estimation à la main (offset le no-bypass). Le buff persiste jusqu'au prochain tour de CHAQUE bénéficiaire même si Aun'Shi bouge/meurt → tenir Aun'Shi central/vivante = aura survie + dmg pour tout le cluster. Composante-clé du « hold-baits-the-dive » [n=2, 70050/70060]`
  `▸ Tac (n+1 engine-kill-first CONFIRMÉ vs Aun'Shi, self-play consensus seed 80000) : tuer Aun'Shi AVANT que R3 StormOfFire puisse re-cycler est le **kill-wincon-first** applicable à son cas exact (cycle observé T4, R1 actif) ; chunk + finish = kill T4 avant la next Storm. ✅ **Cross-validé par les DEUX sides du self-play** (A = kill intentionnel T4 avant R3 ; B = reconnaît l'engine stoppé avant son storm-repeat). gameconfig confirme « After round 3, the cycle begins again ». [self-play consensus, seed 80000]. [n=3, 70050/70060/80000-sp]`
  `▸ Tac (n+1 timing-burst APRÈS le −50% R1 = DÉCISIF côté VAINQUEUR, self-play consensus seed 80000 ts=b7) : la phase R1 SenseOfStone est PUREMENT DÉFENSIVE (−50% dmg SUBI) → un burst dépensé PENDANT cette phase sur une cible buffée est ~halvé (vécu : SeekerMissile ~2793 au lieu de ~5782 sur un Pestillian buffé). ⚠ CÔTÉ OFFENSIF (cross-validé les DEUX sides ce run, A=W) : **timer le focus-kill au tour SUIVANT, une fois le buff expiré** (le −50% dure jusqu'au prochain tour du PORTEUR) ~DOUBLE le dmg landé → A a HOLD une consolidation puis double-killé Tanksmasha+Aun'Shi à plein une fois le −50% tombé. Doctrine : NE PAS burster un cluster en phase SenseOfStone ; attendre 1 tour ou taper une cible HORS de la portée 2-hex du buff. (cf. gameconfig --effect SenseOfStone) [self-play consensus, seed 80000, ts=b7]`

- **ultraEliminatorSgt « Certus » (Ultramarines, sniper, soft NON-Resilient, CamoCloak, Infiltrate)** — quirks non-déductibles : `HeavyWeapon` double l'ability SEULEMENT s'il n'a pas bougé (bouger forfait le bonus, base reste un gros nuke) ; `Infiltrate` = Certus ne déclenche PAS l'Overwatch ennemi ; tir hors range/LoS = no-op silencieux mais action PRÉSERVÉE → repositionner d'abord. (cf. gameconfig --ability MortisRound / --trait Overwatch/Infiltrate/HeavyWeapon)
  `▸ Tac: rôle=carry (artillerie kiting) · menace=med · counter=le tuer au RANGED (Infiltrate = pas catchable par mon OW) ; soft no-Resilient → finisher franc une fois atteignable ; reste backline rows 5-8 comme artillerie → part du focus all-ranged qui out-attritionne un roster melee ; ⚠ INATTEIGNABLE pour un roster melee/r2 sans reach tool = composante d'une loss structurelle de reach à flagger au recon [n=1, 70052]`
  `▸ Tac (À MOI — TURRET Overwatch HELD, CONFIRMÉ live seed 70061) : Overwatch (trait, gate NOT-attacked, cf. §1) fire sur CHAQUE ennemi qui bouge dans sa portée r3 au tour adverse, tant que Certus n'a pas attaqué — **AUCUN cap once-per-turn** : tenir son action offensive arme des reaction-kills illimités. PLAY : la HOLD (ne pas attaquer ce tour) → l'ennemi qui dive séquentiellement se fait reaction-kill 1-par-mover GRATIS (vécu seed 70061 : 3 reaction-kills successifs sur le dive SANS dépenser une action offensive = highest-value engine du match). Analogue Ultramarines du held-OW turret (cf. Azrael/Sy-gex/Re'vas EWO §1) : turret arrière quand l'ennemi DOIT closer, ne pas la pousser pour un finish incertain. [n=1, 70061 chained]`
  `▸ Tac (ENNEMI — FINIR EN MÊLÉE, cross-observé seed 80042) : CamoCloak (réduction hits RANGED) + HeavyWeapon = ranged-mitigation → **la MÊLÉE bypasse les deux** (ni CamoCloak ni HeavyWeapon ne s'appliquent à la mêlée). PLAY confirmé des DEUX sides : finir un Certus survivant en MÊLÉE plutôt qu'au ranged ; pré-positionner le finisher mêlée le tour d'avant pour fermer avant un round-cap. Soft no-Resilient → K! franc une fois adjacent. (Même famille que Snotflogga 3-hits-discrets vs Terrifying/Camouflage §5.) [self-play consensus, seed 80042]`
- **orksRuntherd « Snotflogga » (Orks, summon/lock engine, tank)** — quirks non-déductibles : `GetEmRuntz` summon 1 Grot dans CHAQUE hex adjacent ayant un ennemi adjacent, chaque Grot attaque immédiatement (pas de move) et la cible touchée est **Taunted 1 round** (`Taunted_OnlySpecificTargets`+`BlockMovement`+`CantUseAbility` → la cible ne peut QUE taper le Grot, ni bouger ni user actif/heal/repair) = soft-lock 1 round d'un caster/summoner-clé pour le coût d'un Grot. Passif `SquigHound` : normale **+2 hits Physical single-target (PAS de cleave/spill)** ; après attaque summon 1 Grot adjacent (cap <5) ; Grots amis ignorent BattleFatigue. ⚠️ le « spill sur ennemis adjacents » n'est PAS dans son kit (réfuté — un kill chaîné observé venait d'un Grot summon immédiat, pas du spill). (cf. gameconfig --ability GetEmRuntz / --trait SquigHound)
  `▸ Tac: rôle=anvil/engine (Grot-summoner) · menace=high (énorme HP tank + GetEmRuntz Taunt-lock 1 round + SquigHound feed le snowball) · counter=énorme HP, dur à retirer → kite/ignorer SAUF burst dispo ; la priorité « tuer-les-summoners-d'abord » sur Tan Gi'da/Aleph-Null passe AVANT de chiper cet anvil (vécu seed 98003 : survécu full PV tout le combat) ; ses Grots Taunt + summons feed le board → source secondaire, pas la cible #1 · ✅ **à MOI = engine self-sustaining** : SquigHound farme un Grot (scale rareté cf. H34) à chaque normale qui auto-attaque/chip GRATIS → l'ennemi gaspille des tours à tuer mes Grots remplaçables pendant que mes héros restent sains (vécu seed 98001 W) ; **`BeastSlayer`** (+dmg vs BigTarget/Vehicle) → overkiller IDÉAL d'un BigTarget comme Gulgortz (FinalJustice supprimée seed 98001) ; ✅ **À MOI = melee-finish anti-mitigation confirmé n+1** : les 3 frappes Physical DISCRÈTES (1× base + 2× SquigHound) résolvent indépendamment → CONTOURNENT partiellement Terrifying (réduction mêlée) ET Camouflage (anti-ranged) ET Resilient (multi-hit ≥2) en une activation : a tué un Archimatos full-HP ET chunké Deathleaper past Terrifying ; chaque normale auto-summon un Grot qui auto-chip/reaction-kill → réponse melee-finish à un assassin Terrifying/Camouflage (vécu seed 70053 W) [n=3, 98001/98003/70053] ; ✅ **anti-Resilient confirmé n+1 par DOUBLE-observer** : le multi-hit floor un Resilient anchor à 1 PV puis un hit LATER dans la MÊME activation l'OVERKILLE (WasOverkill=1) → SOLO un Dreir full-HP ET contribue le floor sur Tyrith ; floor-puis-overkill-en-une-activation = LE mécanisme qui bat le clamp Resilient. Démonte un mur de 3 anchors Resilient une-par-tour. [self-play consensus, seed 80020]`
- **orksWarboss « Gulgortz » (Orks, Boss, mêlée + ranged passif, Mechanical, PAS Resilient)** — anvil/carry Ork. Quirks non-déductibles : passif `LightImUp` = après CHAQUE normale, 2ᵉ attaque sur la même cible (3× Projectile ranged) ; si la cible est défaite, hits restants redistribués à un ennemi aléatoire ≤3 hex → sa normale = mêlée + volée ranged enchaînée. `Waaagh` (actif, **gated « n'a PAS bougé »**) = swing de comeback : summon 2 Ork Boyz adjacents + buff d'équipe (Orks amis + units adjacentes : +1 Move, normales mêlée +dmg/+1 hit jusqu'à fin tour) + charge un ennemi EN MOVE RANGE + **tous les Ork Boyz amis prennent un tour immédiatement** (vécu seed 70008 : un cast a flippé 3v6-down en 5v2-up en une activation). ⚠ la charge exige une cible en move range AVEC un hex adjacent libre (contrainte free-adjacent-hex non explicite en i2 ; charge dist2 sans hex libre rejetée). `CrushingStrike` (+dmg mêlée si stationnaire). Trait `FinalJustice` (cf. §1) — ⚠ sa riposte de mort déclenche LightImUp = double volée mêlée+ranged, BIEN plus lourde qu'une normale plate ; un FJ-carrier qui meurt adjacent à un ennemi bas-PV auto-trade un kill (vécu seed 70008 : a tué le Godswyl 458 PV adjacent). `Mechanical` (pas de heal, repair-only). (cf. gameconfig --ability Waaagh / --trait LightImUp/FinalJustice/CrushingStrike/Mechanical)
  `▸ Tac: rôle=anvil/carry · menace=high (FinalJustice + LightImUp = riposte de mort double volée mêlée+ranged ; Waaagh summon 2 Ork Boys) · counter=Mechanical (repair-only) ; pas Resilient → **OVERKILLER** (chunk puis coup létal >2× PV restants, ou Crit) pour nier FinalJustice — sinon sa mort = double volée sur l'adjacent (vécu seed 95001/95002 : tué NON-overkill → FJ tue/chunke l'adjacent) ; ✅ **SUPPRESSION VÉRIFIÉE seed 98001** : tué depuis bas-PV par Snotflogga BeastSlayer (gros hit >2× = overkill) → AUCUNE FJ/LightImUp dans la cascade (i2 « unless Overkilled » confirmé) ; budgétiser dmg >2× PV restants (BeastSlayer vs BigTarget = overkiller idéal) ; ce n'est PAS le wincon (no Ambush/no pump) → le chiper sur plusieurs tours puis l'overkiller, le laisser pour la fin après les engines ; tuer AVANT le Waaagh ou accepter les Boys ; ⚠ **VARIANTE SAFETY si overkill impossible (vécu seed 70009 triggered-against-me)** : tué NON-overkill → FJ a fire MAIS routé sur le seul adjacent = un TANK high-HP (survécu) = riposte absorbée sans perte ; si l'overkill est impossible, finir Gulgortz avec UNIQUEMENT un corps high-HP adjacent (jamais un fragile) [n=4, 70009]`
- **adeptCanoness « Roswitha » (Imperium, Sisters of Battle, ranged/mêlée, anti-Psyker, PAS Resilient)** — quirks non-déductibles : `BrazierOfHolyFire` (Flame range 2 ; **2× hits vs non-Daemon ; vs Daemon : 4× hits + aura +60% dmg à tous les Daemons dans 2 hex ce round et le suivant — Daemons Immune : +20%**. Bonus Daemon STRICTEMENT gaté sur la faction CIBLE : Necrons/Xenos/autres non-Chaos ne reçoivent QUE le chemin 2×). `CondemnorStake` (+dmg massif vs Psykers → **assassin de Psykers dédié**, comme Tjark ; non pertinent face à un roster sans Psyker). `ActOfFaith` (+Crit Chance/Damage à chaque mort/kill d'un Imperial, reset au crit — PAS de bonus de PV). Peut être **ressuscitée par Isabella** (RitesOfRestoration) → la re-tuer est gâché si Isabella vit encore. Vérifié live (seed 70002, à MOI) : Brazier 2× a one-shot un Aleph-Null full-HP (Necron = non-Daemon → chemin 2×, kill propre quand même) ; CondemnorStake a posé un KILL GRATUIT en réaction sur un Ahriman Psyker qui a dive. (cf. gameconfig --ability BrazierOfHolyFire/CondemnorStake / --trait ActOfFaith)
  `▸ Tac: rôle=carry/control · menace=med (seule menace anti-Daemon sérieuse vs roster Chaos/summons ; ActOfFaith stacke le crit par kill/death Imperial) · counter=tuer TÔT (pas Resilient, PV modeste) ; si un reviver vit (Isabella), tuer le reviver d'abord ; ⚠ BrazierOfHolyFire DOUBLE vs Daemons → NE PAS clusterer mes Daemons/summons (PinkHorror/Screamers) adjacents à ses cibles ; CondemnorStake +dmg vs Psykers → ne pas présenter Abraxas/Patriarch adjacent · si à MOI : Brazier = gros nuke single-target (one-shot un non-Daemon haut-PV, 4× +60% vs Daemons — garder au RANGE vs cibles Explodes) ; router sur les Psykers ennemis (assassin de casters dédié) ; soft → finisher trivial une fois chunkée [n=3, 70002]`
  `▸ Tac (CONTRE MA COMPO summon+Psyker — seed 70059 W) : HARD-COUNTER DÉDIÉ de ma compo Chaos summon+Psyker (Brazier aura vs mes Daemons + CondemnorStake vs mes Psykers) → au recon, traiter Roswitha comme menace SPÉCIFIQUE quand JE fielde Daemons+Psykers (miroir de l'aura-anti-X LIVE). Mitigation appliquée : ne pas clusterer mes Daemon-summons sur ses cibles + ne pas présenter mes Psykers adjacents + la tuer TOP-early parmi les softs. Elle tombe vite une fois le dive l'expose [n=1, 70059]`
- **custoKyrus « Tyrith » (Custodes, Resilient, counter)** — quirks non-déductibles : passif `UnwaveringSentinel` = à chaque tour ennemi, après que Tyrith est attaquée par une unité ≤range 2, elle riposte 2× Bolter à l'attaquant (range tombe à 1 si un ennemi lui est adjacent). `Resilient` : coup létal non-Overkill → 1 PV ; un 2ᵉ hit à 1 PV tue (pas de re-trigger) ; one-shot = besoin d'Overkill. **`VigilanceEternal` (actif, cd 2, initial cd 0)** : mêlée mobile, **réutilisable plusieurs fois/combat** et **ne termine PAS son tour**. Cible UNIQUEMENT un ennemi **déjà adjacent** OU ayant un hex libre adjacent dans la move range 2 (gap-close sur cet hex) ; **si aucun hex libre éligible, l'ability ne peut pas s'exécuter** (plans affichent ~0 dmg). NB owner = Tyrith (PAS « Kyrus » ; `--unit Kyrus` = unité inconnue en gameconfig). (cf. gameconfig --ability VigilanceEternal / --trait UnwaveringSentinel/Resilient)
- **custoBladeChampion « Kariyan » (Custodes, anvil anti-normal-attack, Resilient)** — suite défensive, quirks non-déductibles : `MartialKatah` (−dmg de TOUTES les attaques NORMALES subies ; +dmg vs Summons) + `Parry` (−1 hit aux attaques MÊLÉE multi-hit subies, min 1) + `BeastSlayer` (chance occasionnelle de bloquer 100% de l'armure courante — pas fiable) + `Resilient` (achète exactement 1 hit de plus). Net : blunt fortement un focus multi-source d'attaques NORMALES mêlée. ⚠ ses actifs `MartialInspiration` + `LegacyOfCombat` **bypassent SON propre MartialKatah** (actifs ≠ normales) → un porteur de MartialKatah se craque à l'ACTIF, pas à la normale. (cf. gameconfig --trait MartialKatah/Parry/BeastSlayer/Resilient)
- **tauMarksman « Sho'syl » (Tau, ranged, move2, Camouflage+RangedSpecialist)** — quirks non-déductibles : actif `SeekerMissileFrequencyLock` (range 5) marque (Markerlight + lock) ; **au DÉBUT du PROCHAIN tour de Sho'syl, s'il est encore vivant**, la cible prend 1× Heavy Round (capé aux PV cible) — undodgeable, contournable seulement en tuant Sho'syl avant. Normale = passif `MV71SniperDroneSquad` : summon une MV71 Drone qui **attaque avec le Damage stat de Sho'syl** (i2 : « other effects, like buffs, taken from the Drone ») + pose un Markerlight (max 3 drones). Synergie : coupler le Seeker-mark avec un Taunt/BlockMovement pour que la cible ne fuie pas le tir retardé. ⚠ **AUTO-TARGET hérité** (seed 96001) : le missile fire au DÉBUT du tour de Sho'syl, PAS à l'endturn ; un missile hérité d'un runner précédent garde sa cible auto-armée (visait Kharn au lieu de la wincon) → dès le build, **re-cibler/annuler les missiles hérités vers la vraie wincon** avant de jouer. **Caveat outil** : dans `play --spec`, le cast a `mutated=False` (effets purement DIFFÉRÉS) → la garde anti-no-op déclenche TOUR ABANDONNÉ à tort ; **workaround = `act ability` individuel** pour les abilities à effets différés. (cf. gameconfig --ability SeekerMissileFrequencyLock / --trait MV71SniperDroneSquad/Camouflage/RangedSpecialist) (n=1)
  ⚠ **MV71 DRONE = FORCE-MULTIPLIER FOCUS-KILL confirmé (Verif seed 70058)** : le drone summoné frappe au Damage stat de Sho'syl (PAS son profil base) → un drone back-row peut delete un forward sans que Sho'syl bouge (observé : KILL sur ma Jain Zar). Drone HP scale au niveau/rareté du summon. Le drone devient **chair inerte (dmg ~base) dès que Sho'syl meurt** → tuer Sho'syl coupe ET le Seeker ET la menace drone. **Ne PAS avancer une unité dans la reach COMBINÉE de Sho'syl (drone-summon) + un autre dealer back-row** : la reach/dmg du drone n'apparaît PAS dans le danger-zone overlay (summoner blind spot, SKILL §4).
  ⚠ **MV71 DRONE = BURST IMMÉDIAT ON-DEMAND côté MIEN (vécu seed 70057 W, Sho'syl dans MON roster)** : la normale summon un drone qui attaque **immédiatement** (au Damage stat de Sho'syl) DEPUIS la tuile courante/shallow — c'est un **burst-on-demand**, PAS le Seeker différé. Délivre un gros chunk SANS exposer Sho'syl + le drone reste comme **screen** (SaviorProtocols intercept pour les T'au adjacents). Combiné à Tan Gi'da ControlEdict (Vanguard-on-attack) = chaîne de corps-écrans qui soakent le focus ennemi (vécu seed 70057 : drone + Vanguard ont absorbé le focus au lieu de mes héros).
  `▸ Tac (n+1 MINE, seed 70057 W) : Sho'syl côté MIEN = carry burst + screen-generator. La normale (MV71 drone) = chunk IMMÉDIAT depuis tuile shallow + un drone-screen persistant → délivrer du dmg sans avancer Sho'syl ; garder Sho'syl shallow/écrané (c'est l'amplificateur à protéger). [n=1, 70057-mine]`
  `▸ Tac: rôle=engine (summoner/seeker) · menace=CRITICAL (Seeker = kill garanti undodgeable au début de SON prochain tour, fire quelle que soit la position cible — ne se dodge PAS en bougeant, contrairement à HeavyRailRifle ; + MV71 drone qui frappe au Damage stat de Sho'syl = focus-kill d'un forward sans bouger Sho'syl ; + reçoit TwistedScience pump) · counter=DOIT mourir avant que son 1er Seeker résolve — il est la SOURCE du Seeker ET des drones (drones inertes une fois mort) ; kite row 7-9 derrière le mur mêlée = souvent inatteignable pour un roster melee/short-range MAIS devient ATTEIGNABLE si son screen mêlée dive et meurt (vécu seed 70058 : Aesoth K! Sho'syl T4 une fois le screen tombé) ; Camouflage blunt la rétorsion ranged → un kill mêlée/adjacent fonctionne ; NE PAS over-extendre un non-tank dans la reach Sho'syl+drone (drone-reach invisible à l'overlay) [n=2, 97001+70058]`

- **necroOverlord « Anuphet » (Necron, move3, mêlée Energy)** — passif `MartialApotheosis`
  **[AUTO:StartTurn]** : auto-inflige Energy (Pierce) à un ennemi adjacent au hasard, HORS de son
  activation → **finit gratis un survivant à 1 PV** (ex. un Resilient laissé à 1) sans dépenser d'action.
  Garder les unités bas-PV hors de l'adjacence au début de son tour.
  `ResurrectionOrb` (summon SANS dmg) = défaut d'`act` sans --ability → toujours passer --ability
  explicite (cf. §1) ; Warriors invoqués non-commandables au spawn mais menacent via Overwatch (H17).
  **`ResurrectionOrb` = SNOWBALL (i2 vérifié seed 98002)** : summon +1 Necron Warrior **par round écoulé**
  ET **+1 par allié LivingMetal déjà défait** (clause qui RÉCOMPENSE mes kills sur ses Necrons → ne pas
  farmer ses Necrons). Stats imprimées dans le texte = **PRE-scaling** : PV runtime plus haut que l'affiché.
  Necron Warrior invoqué = **move2, ranged r2 Gauss**.
  ⚠ **[indispo] après cast = once-per-turn** (standard active-ability cooldown, vérifié seed 70000).
  **Doctrine : tuer Anuphet TÔT** (soft, no-Resilient → killable en réaction s'il dive) avant que le board
  flood de corps LivingMetal/ReanimationProtocols. (cf. gameconfig --ability ResurrectionOrb --trait MartialApotheosis)
  `▸ Tac: rôle=engine (summoner) · menace=high (ResurrectionOrb = 1 Warrior/round +1/LivingMetal mort + LivingMetal self-regen + MartialApotheosis auto-hit start-of-turn ; source du snowball Necron) · counter=focus-kill TÔT avant que le board se remplisse (soft, no-Resilient → tout K! franc/réaction le tue) ; killable s'il dive, MAIS s'il reste backline (vécu seed 70000 : Anuphet intouchable tout le combat) = SECONDAIRE après les engines AoE/snowball atteignables ; ne PAS out-DPS l'output réparé, briser la SOURCE (lui + Aleph-Null repair) [n=2, 98002/70000]`
- **necroWarden « Makhotep » (Necron, mêlée, Mechanical, anvil/aura)** — `RelentlessMarch` (actif/aura) :
  **aura START-OF-TURN** — **+1 Movement à TOUS les alliés qui DÉMARRENT leur tour adjacents** à
  Makhotep, ET **répare les Mechanical** parmi eux (i2 vérifié seed 95002). Sa valeur réelle = ce **buff de
  mobilité d'équipe + repair-aura** (donne +1 move à Gulgortz/OrkBoyz, répare Mechanical/summons) bien plus
  que ses dégâts directs. `AdaptiveStrategy` (actif, non observé live). `LivingMetal` (regen %max PV début
  de tour → Mechanical, repair-only). **Tuer Makhotep = nier le +1 move + le repair-aura à la grappe
  adjacente.** ⚠ « non-character summons get repaired » et « DangerZone effect » = NON dans i2 (i2 dit
  « Mechanical units » sans distinction character/summon ; DangerZone = effet moteur sans source) → ne pas
  inscrire ces nuances. (cf. gameconfig --ability RelentlessMarch --trait LivingMetal)
  `▸ Tac: rôle=anvil/engine · menace=med (aura +1 move équipe + repair Mechanical au start-of-turn = accélère/sustain la grappe) · counter=le tuer pour stripper le +1 move + le repair-aura aux summons/Mechanical adjacents (Gulgortz/OrkBoyz) ; LivingMetal = repair-only → kill en burst, pas du chip [n=1]`
- **tyranDeathleaper « Deathleaper » (Tyranid, assassin, Camouflage)** — `Camouflage` : attaques RANGED
  contre lui = **−1 hit ; −2 hits si attaquant à >2 hex ; −3 hits en Tall Grass** (plancher ≥1 hit). → un
  finisher ranged multi-hit à distance perd la moitié/plus de ses hits = **peu fiable pour l'achever**. Pour
  fiabiliser : se rapprocher à ≤2 hex (−1 hit seulement), éviter Tall Grass, ou finir en mêlée / via un proc
  AUTO garanti (Seeker StartTurn). Melee-finish > ranged-finish vs Deathleaper hors de portée. Aussi
  `Terrifying` (réduit la mêlée subie, §1) + deep-strike/Infiltrate (pas d'OW) + FeederTendrils (heal à la
  charge) ; fragile, **PAS Resilient**. (cf. gameconfig --trait Camouflage --trait Terrifying --ability FeederTendrils)
  `▸ Tac: rôle=control/assassin · menace=high (deep-strike + Infiltrate + Camouflage + Terrifying + self-heal sur charge) · counter=MELEE-finish (Camouflage rend le ranged peu fiable ; le Terrifying réduit la mêlée MAIS un multi-hit splash l'overcome — vécu seed 97000) ; le tuer le tour où il est exposé (avant FearOfTheUnseen / re-vanish) ; pas Resilient → un K! franc multi-hit suffit ; ⚠ confirmé n+1 que le multi-hit DISCRET d'une normale melee overcome Terrifying ET Camouflage en une activation (near-one-shot) → router un melee multi-hitter dessus le tour où il sort du deep-strike (vécu seed 70053 : émergé T2, tué AVANT FearOfTheUnseen vanish/re-strike) ; ⚠ n+1 RANGED-À-COURTE-PORTÉE (seed 70054) : Camouflage ne retire que −1 hit à ≤2 hex → un focus ranged à ≤2 hex chunke ENCORE gros (overkill T4 sur Deathleaper isolé) → le focus-down du tour où il sort du deep-strike marche AUSSI au ranged si on est collé à ≤2 hex, la mêlée fiabilise le finish [n=3, 97000/70053/70054]`
  `▸ Tac (n+1 backline-reach, seed 70055) : ⚠ deep-strike (sortie NON-adjacente) + Infiltrate + move3 = reach quasi pleine-planche → il atteint la backline « safe » (a tué un fragile que je croyais protégé) ; ne JAMAIS laisser un fragile dans sa zone de reach. Camouflage blunte le ranged ET Terrifying blunte la mêlée → dur à FINIR efficacement → le focus-down d'UN gros source le tour où il est exposé/ciblable ; sinon il survit chunké et contribue au wipe. MELEE-finish préféré (multi-hit discret bat Terrifying, cf. n=2 ci-dessus) [n=3, 97000/70053/70055]`
  `▸ Tac (n+1 focus-kill-on-emerge, seed 70060 W) : confirmé tué LE TOUR où il émerge du deep-strike, AVANT FearOfTheUnseen re-vanish — combo CLOSE-RANGE-ranged + MULTI-HIT-melee : un ranged depuis r3 (Camouflage à ≤2-3 hex ne retire qu'1-2 hits → chunk gros) + un melee multi-hit (hits discrets battent Terrifying) = kill clean. Nauseous (−armure aura) aide aussi. Pas Resilient → un focus coordonné le tour exposé suffit ; ne PAS attendre qu'il re-vanish [n=4, 97000/70053/70055/70060]`
  `▸ Tac (FearOfTheUnseen = engine-killer OFFENSIF quand Deathleaper EST À MOI, [self-play consensus, seed 80003 — team1 W]) : insight non-déductible = `FearOfTheUnseen` **RE-CRÉE un deep-strike-avec-attaque APRÈS que le deep-strike d'ouverture est dépensé** (vanish 1 round → teleport sur N'IMPORTE QUEL hex libre + attaques +3x Direct bonus) → un assassin back-row atteint N'IMPORTE QUELLE backline (engine/caster fragile que rien d'autre ne touche). DOCTRINE : **pré-armer FearOfTheUnseen (cast self, no-move) le tour AVANT** que l'ennemi cluster en portée, puis teleport-K! la SOURCE prioritaire (vécu : K! Archimatos full-HP 8034 ignore armure) le tour de l'over-commit. Le +3x Direct ignore armure/MkXGravis ET le deep-strike d'ouverture est PERDU si on endturn sans l'utiliser → convertir via FearOfTheUnseen, jamais le laisser expirer. ⚠ ADVERSARIAL : le teleport deep + un cleave Jain Zar/Godswyl forward = SUR-EXTENSION qui ne paie QUE si l'alpha est létal EN UN tour ; vs un ennemi qui garde ses engines back (pas d'over-commit), ne PAS deep-commit (carries stranded). Les 2 sides concordent (B a observé `FearOfTheUnseen_TeleportingIn`+`_ExtraDamage` → relocate full-board). (cf. gameconfig --ability FearOfTheUnseen)`
- **bloodSanguinary « Nicodemus » (Blood Angels, healer)** — `BloodChalice` : **SET tous les alliés
  non-Mechanical hex-adjacents à 50% PV** (set absolu, pas heal-to-min) → **FRIENDLY FIRE sur tout allié
  au-dessus de 50%** (vécu : mon Snotflogga chuté de moitié), heal seulement les alliés <50% ; Mechanical
  non affectés. Les mêmes gagnent `BloodChalice_HealOnAttack` (jusqu'au début de leur prochain tour : +pierce
  mêlée + heal sur une attaque mêlée). **Énumérer TOUS les hex-voisins avant de caster.** `SanguinaryPriest`
  (passif observé seed 70051 : regen aux alliés adjacents quand Nicodemus se déplace). **PAS de Resilient,
  PAS de FinalJustice** (seed 70051) → tout K! le tue propre. (cf. gameconfig --ability BloodChalice)
  `▸ Tac: rôle=engine (Healer de sustain) · menace=high (BloodChalice set-50% + HealOnAttack + SanguinaryPriest regen-on-move = sustain l'équipe entière) · counter=le tuer/chunker AVANT qu'il sustain le dive ; no Resilient/no FJ → tout K! le défait propre (vécu seed 70051 : chunké T4 puis fini T5 avant tout cycle de heal significatif) ; se cache souvent en row arrière → le catcher au RANGED ou en réaction quand il dive [n=1, 70051]`
- **eldarJainZar « Jain Zar » (Aeldari, mêlée)** — `SilentDeath` (Melee, Piercing **Pierce80** = contourne
  l'armure) : 3 hits sur la cible primaire **ET jusqu'à 3 ennemis ADJACENTS entre eux** (adjacency-chain AoE
  → 1 cast cleave un cluster). **Arme lancée** : Jain Zar **ne se déplace PAS** (l'arme revient) → cast
  depuis sa position sans s'exposer. Dégâts en hits discrets → **bat Resilient sur CHAQUE cible** (hit 1 →
  1 PV, hits 2-3 tuent, sauf Overkill). Peut **tuer une unité ET chunker une voisine dans le même cast**
  (vérifié seed 70001) → finisher d'engine qui splash GRATIS le carry voisin. Excellent vs clusters armurés.
  ⚠ **once-per-battle observé live (seed 70001 : [indispo] après un usage, jamais rafraîchi)** — NON corroboré
  par gameconfig (aucun champ cooldown/munitions) → cf. H13, le réserver pour un swing décisif, ne pas
  l'alpha-dump. `Infiltrate` (ne déclenche **PAS** l'Overwatch ennemi → flanker la backline gratis) ;
  `TerrorsLament` (aura −dmg / −1 hit mêlée aux ennemis adjacents → blunt aussi les ripostes mêlée et les
  death-ripostes FinalJustice de mes forward units). (cf. gameconfig --ability SilentDeath --trait Infiltrate --trait TerrorsLament)
  `▸ Tac: rôle=carry · menace=high (assassin flanker : SilentDeath spread AoE Pierce80 + Infiltrate no-OW + aura debuff mêlée) · counter=la tuer TÔT au RANGED avant qu'elle atteigne la backline (Infiltrate = mon OW ne la stoppe pas) ; NE PAS stacker mes unités adjacentes (SilentDeath cleave un cluster) ; un burst ranged la défait franc [n=1]`
  `▸ Tac (anti-TerrorsLament — la TUER au RANGED/Psychic, JAMAIS finir en mêlée, [self-play consensus, seed 80003]) : son aura TerrorsLament gute le mêlée adjacent (vérifié live des 2 sides : ripostes mêlée fortement réduites vs Jain Zar) → un gang-mêlée pour la finir se fait blunt et laisse un survivant. Réponse propre = chip + finish au RANGED/Psychic (ignore l'aura, qui ne touche QUE le mêlée adjacent). Corollaire défensif quand JAIN ZAR EST À MOI : back-anchor avec TerrorsLament ne protège que l'ADJACENT (near-worthless vs un core Psyker ranged) → elle doit KILLER des casters, pas anchorer. Vécu seed 80003 (team2 W) : team2 a été FORCÉ de la tuer au Psychic ranged car le mêlée était inefficace.`
- **admecDominus « Vitruvius » (AdMech, ranged)** — `RadBombardment` : AoE en **LIGNE droite** (Toxic
  Pierce70) qui **FRIENDLY-FIRE** (i2 « all units in a straight line », PAS « all enemies » → touche les
  alliés sur la ligne ; vécu : chip sur son propre Patermine). Pose Contamination sur chaque hex de la ligne
  + **Suppressed (Pinned)** sur tous les touchés. Longueur = 2 hexes +1 par round écoulé +1 par heal Mechanic
  ami (CROISSANT). Viser pour ne clipper QUE des ennemis. `Mechanic` (repair-engine). `nrOfHits:1` mais
  **AoE pleine-ligne en UN cast** → CHAQUE unité sur la ligne prend un hit FULL indépendant (vécu seed
  70003 : 2 carrys sur la MÊME ligne en un cast — une grappe mid-board perd plusieurs units d'un coup).
  Croissance rapide → atteint le mid-board T2-T3, surtout avec un Mechanic support. (cf. gameconfig --ability RadBombardment --ability MasterAnnihilator)
  `▸ Tac: rôle=engine · menace=high (dealer ranged r2/line : RadBombardment = ligne AoE Toxic qui GRANDIT +1/round et +1/heal Mechanic + Suppress + friendly-fire ; MasterAnnihilator marque → team +1 hit vs marqué = amplificateur de focus) · counter=soft (pas Resilient) → le FINIR au range (un chip ne suffit PAS : un engine de mark/ligne croissante survit pour fully amplifier) ; le tuer en réaction quand il dive (vécu seed 98004 : a chunké 2 carrys T2 en line ranged puis tué en réaction T2) ; casser le buff-engine effondre l'amplification du focus ranged [n=2]`
  `  ⚠ CONTRADICTION counter (seed 70003) : chippé par le barrage T1 mais PAS fini → il a fire RadBombardment et tué mon carry au tour suivant. Le « focusable/punissable » de 98004 (kill en réaction) NE tient que si on le TUE ; un chip-sans-kill le laisse amplifier = il faut un set-up de FINISH au range, pas un poke.`
  `  ▸ Tac (n+1 RadBombardment = ALPHA multi-cible le plus impactant d'un combat, CONFIRMÉ self-play consensus, seed 80000 (opus run)) : un SEUL cast a chunké QUATRE ennemis groupés en ligne + tué un drone, Contamination + Suppress sur tous (amplifié par MasterAnnihilator +1 hit). Le profil Toxic Pierce70 BYPASSE Terrifying/armure. ⚠ cross-validé les DEUX sides : B (mine) a exécuté l'alpha, A (theirs) a subi le chunk de toute sa ligne clusterée = un BLOB serré est la PIRE forme vs RadBombardment (multi-hit ligne garanti). DOCTRINE défensive : ESPACER les units pour ne donner qu'1-2 cibles par ligne, jamais un blob dans une rangée droite. [self-play consensus, seed 80000 (opus run)]`
  `  ▸ Tac (3ᵉ run seed 80000 = RadBombardment SEUL gagne, sans EnvEndBombardment) : run distinct (team2 W net à T5, PAS un mutual-wipe) — un blob team1 serré rows 0-1 a été chunké/wipe sur la transition de tour T5, state-file loggant RadBombardment + Contamination (+ Foehammer post-kill). ⚠ confirme que RadBombardment+MasterAnnihilator-mark+ContagionsOfNurgle-shred+Foehammer SUFFISENT à gagner par eux-mêmes — pas besoin du round-cap. A (theirs) a correctement attribué la cascade à RadBombardment ; B (mine) l'a mal attribuée à un EnvEndBombardment (absent à round ~5, cf. H57). Le clustered-low-blob reste la PIRE forme vs cet engine, 3ᵉ confirmation. [self-play consensus, seed 80000 (opus + moves fix), 3ᵉ run]`
  `  ▸ Tac (4ᵉ run seed 80000, 2026-06-23 — FRIENDLY-FIRE backline confirmé live) : la ligne tirée depuis row 9 a chipé MA front-line row 0 à longue portée ET friendly-firé SA PROPRE backline ennemie clusterée (3 units dans le MÊME barrage) — A (theirs) a directement observé l'auto-chip d'un backline blob serré. Cross-cohérent avec i2 « all units in a straight line » : un cluster ENNEMI dans une rangée droite s'auto-chip aussi → viser pour clipper que MES ennemis, et un blob ennemi serré est exploitable (le forcer à manger son propre barrage). [self-play consensus, seed 80000, run #4]`
- **darkaCompanion « Sarquael » (Dark Angels, ranged)** — `Supercharge` (Ranged Plasma, range 3, +pierce) :
  hit la cible ET **jusqu'à 2 ennemis dans les hexes DIRECTEMENT DERRIÈRE la cible** → outil de décapitation
  vs formations alignées (summoner/carry avec des unités derrière) ; laisse un debuff +Plasma-pierce sur tous
  les touchés jusqu'à son prochain tour. Passif `GrimRetribution` (overwatch) : chaque tour ennemi, SI aucun
  ennemi adjacent à Sarquael ET il (ou un Dark Angel adjacent) a été attaqué, auto-fire 1× Plasma sur le
  1ᵉʳ attaquant en portée. Lever = le garder hors de l'adjacence mêlée (pas « skip son action »). ⚠ **GATE
  Overwatch = NOT-ATTACKED (Verif-confirmé seed 70060)** : l'Overwatch (trait + GrimRetribution) s'arme
  seulement s'il N'A PAS attaqué ce tour (trait « nor after that ») → laisser Sarquael **unactioned** près du
  cluster = OW armé qui auto-tire un diveur au tour ennemi. ⚠ **id-unité** : le hero « Sarquael » apparaît
  aussi sous l'id `darkaHellblaster` (variante Hellblaster, même kit Supercharge r3 + GrimRetribution).
  (cf. gameconfig --ability Supercharge --ability GrimRetribution)
  `▸ Tac: rôle=turret ranged (à MOI) · valeur=high (Supercharge r3 décapitation + GrimRetribution held-overwatch) · usage à MOI = HOLD Sarquael unactioned près du cluster (OW armé only-if-not-attacked) pour punir le dive ennemi en réaction ; ne JAMAIS le pousser en coin (coin = hors portée OW r3 → NET très inférieur vs tenir près du cluster, vécu seed 70060) ; lead Supercharge (no-move = HeavyWeapon +dmg) sur un engine soft aligné = chunk décisif + debuff Plasma-pierce ; le garder hors adjacence mêlée pour que GrimRetribution fire [n=1, 70060]`
  `▸ Tac (ENNEMI, seed 70057 W, GrimRetribution confirmé Verif) : rôle=control · menace=med (r3 Plasma + Overwatch + GrimRetribution counter + FinalJustice + HeavyWeapon, soft no-Resilient) · counter=BUDGÉTER le contre-coup : si AUCUN ennemi n'est adjacent à Sarquael, toute attaque RANGED sur lui (ou un Dark Angel adjacent) déclenche un Overwatch Plasma counter (observé : un de mes corps a survécu au counter) → soit COLLER un de mes corps adjacent à Sarquael pour suppress GrimRetribution avant de le poke, soit accepter/absorber le counter sur un corps tanky ; le tuer enlève l'Overwatch + la menace ranged. FJ présent → overkill ou route la riposte [n=1, 70057]`

- **blackTerminator « Angrax » (Black Legion)** — (cf. aussi §3bis ci-dessus) overwatch `HatefulAssault` :
  riposte **quand un ennemi adjacent BOUGE HORS** d'un hex adjacent à Angrax (disengagement, PAS l'approche)
  → se désengager de sa mêlée se paie mid-move. (cf. gameconfig --ability HatefulAssault)
- **darkaAsmodai « Asmodai » (Dark Angels, mêlée)** — `ExemplarOfHate` : pose un **mark dmg melee/Overwatch**
  sur n'importe quel ennemi pour ce round + le suivant (2 game-rounds). ⚠ **Le bonus est PAR-HIT** → **multiplicatif
  avec les armes multi-hit** (un burst 4-hit gagne 4× le bonus, vérifié seed 98004 sur Haarken vs Helbrecht marqué) :
  le mark sur une cible que plusieurs alliés vont multi-frapper = amplification massive. Rider « si la cible est **Chaos** »
  (Suppress + une attaque normale gratuite d'un Dark Angel allié) — HYPOTHÈSE (H15) : gaté par la portée d'attaque
  normale du Dark Angel exécutant ; positionner Asmodai adjacent à la cible Chaos avant de caster pour la pleine valeur.
  `FearedInterrogator` : bonus vs cibles Suppressed/Stunned/adjacentes à un Dark Angel. `Terrifying` (réduit la mêlée
  subie → bypass = RANGED, cf. §1). (cf. gameconfig --ability ExemplarOfHate / --trait Terrifying)
  `▸ Tac: rôle=control · menace=med · counter=Terrifying → le tuer/chunker au RANGED (la mêlée est réduite) ; le viser AVANT qu'il mark une pièce-clé (mark melee/OW à toute mêlée/OW alliée 2 rounds) ; reste souvent en retrait jusqu'au mid-game (vécu seed 95000) [n=1]`
- **templSwordBrother « Godswyl » (Black Templars, mêlée)** — `ThunderousAssault` : 1 hit Power (Pierce40), push la
  cible adjacente 1 hex, **Stun 1 round** (PAS 2), puis **GODSWYL lui-même avance sur l'hex vacant** (repositionnement
  forward designé, pas un push d'allié), et les cibles défaites par l'attaque sont **toujours overkillées**.
  `ChampionOfTheFeast` (passif **move-triggered**, PAS un counter-attack) : **après avoir bougé**, 1× Power (Pierce40)
  à un ennemi adjacent **ET réduit son Armour PERMANENT (rest of battle)** ; **s'il ne bouge pas, fire en fin de son tour**.
  Surface dans la cascade comme `Thorns_DefenseReduction`. → un Godswyl qui avance débuffe l'armure d'un adjacent à vie
  (set-up pour la suite, vérifié seed 96001). `RapidAssault` (+move/+dmg) ; `Parry` (−1 hit mêlée subi → préférer UN gros
  hit à un multi-hit contre lui). (cf. gameconfig --ability ThunderousAssault / ChampionOfTheFeast / --trait Parry)
  `▸ Tac: rôle=chaff/striker secondaire · menace=med (PAS la wincon : Common sans valeur d'engine ; danger réel = le burst ThunderousAssault + Stun sur un corps bas-PV) · counter=soft (pas Resilient) = killable franc ; Parry → le frapper en UN gros hit (pas multi-hit) ; le traiter en SECONDAIRE après les engines — NE PAS investir d'output dessus, le laisser DIVER ma ligne tenue et le DELETE en réactions (vécu seed 70001 : a dive ma held-line → mort à un reaction-kill ; son Stun ne neutralise que 1 round, la cible garde 1 move + son attaque normale, cf. §1 Stun ; vécu seed 70008 : chaff confirmé) [n=3, 70001/70008]`
  `▸ Tac (3ᵉ confirmation rôle=chaff, seed 70055) : rôle=chaff/striker CONFIRMÉ n+1 (soft no-Resilient → tué cleanly T3) ; le danger reste UNIQUEMENT le burst ThunderousAssault + Stun 1 round sur un corps bas-PV, Parry → UN gros hit. À traiter en SECONDAIRE (soft autonomous threat à tuer cheaply), PAS la wincon → la CONTRADICTION rôle=carry ci-dessous est RÉSOLUE : 3 matchups (70001/70008/70055) = chaff/striker secondaire [n=4, 70001/70008/70055]`
  `  ⚠ CONTRADICTION rôle RÉSOLUE (3 matchups 70001/70008/70055) : la carte KIT ci-dessus liste rôle=carry (tooltip), mais en jeu Godswyl s'est comporté en CHAFF/striker secondaire à CHAQUE fois (Common, aucune valeur d'engine, dive-puni/tué cleanly). Tag effectif = rôle=chaff/striker ; menace=med (le burst reste réel sur un fragile).`
- **templAggressor « Burchard » (Black Templars, mêlée + ranged, ~12k PV, MkXGravis)** — anvil lourd qui
  **DEVIENT le wincon late** dès qu'on perd l'armor-bypass. **`MkXGravis`** (cf. §1) = double-armure (tout dmg
  entrant repasse l'Armour, **sauf Crit/Direct/Psychic**) → un roster Power/Physical low-pierce est gutté (vécu
  seed 70008 : Gauss Pierce60, Power Pierce40, Physical Pierce1 tous laminés au net). Ranged r2 `FragstormGrenadeLauncher`
  (Blast, leftover-hits → peut finir un voisin) + `Boltstorm`. **move2 (lent) = kitable** — mais il faut quand même un
  bypass-armure (Crit/Direct/Psychic) pour réellement le tuer ; sinon il out-damage 1v1 et overkill un Resilient via
  multi-hits. (cf. gameconfig --trait MkXGravis / --ability FragstormGrenadeLauncher)
  `▸ Tac: rôle=anvil → wincon late ÉMERGENT · menace=critical POUR UN ROSTER SANS Direct/Psychic/Crit (un tank 12k MkXGravis standalone devient INGRINDABLE une fois les screens/engines morts ; ni self-healer ni reach-fail — un mur high-armor que SEUL un bypass-armure tue) · counter=RÉSERVER un burst Direct/Psychic/Crit POUR LUI au recon (même famille que « réserver l'anti-armor burst » 70004/97002) ; un Power/Physical low-pierce ne peut PAS l'out-grind → ne pas planifier de le trade en mêlée, tuer les softs qu'il accompagne et accepter de ne pas le cracker SI le bypass est perdu = FLAGGER la loss ; move2 lent → kitable mais ça ne tue pas ; ⚠ vécu seed 70008 : j'ai perdu mes 2 SEULS bypass (Exitor CordClaw Direct Pierce100 + Atlacoya Direct) en over-extension T1 → Burchard est devenu le wincon imbattable, loss à 1v1 [n=1, 70008]`
  `▸ Tac (n+1 menace CONDITIONNELLE, seed 70060 W) : ⚠ menace=critical SEULEMENT comme DERNIER mur après la guerre des nombres perdue — à 6v1 c'est un GRIND TRIVIAL même sans bypass-armure : vécu seed 70060, mon roster ZÉRO Direct/Psychic/Crit a chunké Burchard puis K! le tour suivant grâce à une −armure aura (Nauseous ContagionsOfNurgle) + un buff dmg (Aun'Shi Storm of Fire) qui ont offset MkXGravis. La clé = GAGNER LA GUERRE DES NOMBRES D'ABORD (ici un mur de réaction Overwatch a tué les 2 carries T2 zéro perte) → affronter Burchard en 6v1 (puits trivial) au lieu d'en dernier mur ingrindable (70008). CONFIRME l'INVERSE de 70008 : un MkXGravis standalone n'est ingrindable QUE quand il est le dernier debout ET la course aux dégâts déjà perdue ; overwhelm via nombres + une −armure aura override le no-bypass [n=2, 70008/70060]`
- **spaceStormcaller « Njal » (Space Wolves, Psyker, ranged r3, move2)** — `TerminatorArmour` (cf. §1 —
  réduit la 1ʳᵉ attaque/tour hors Psychic/Direct ; sur Njal LUI-MÊME → bypass = Psychic/Direct ou 2ᵉ attaque
  distincte ; **ne peut pas être Suppressed**). `Stormcaller` (actif Psychic, **PiercingRatio=100 + trait
  `NoBlocking`** → ignore armure ET block, cf. §1 Psychic-vs-Mechanical) : **AoE = hex de la cible + TOUS
  les hexes adjacents** (Ice-covered) → touche toute la grappe ; **stun les unités FLYING touchées** (vérifié
  seed 70001 : a touché 3 de mes units en ignorant l'armure, menace de stun mon Dante Flying).
  `LordOfTempests` (**snowball : bonus dmg PAR hex d'Ice adjacent** → monte en puissance plus la zone Ice
  s'étend). `Unstoppable`. move2 (lent) mais le reach r3 actif est profond. (cf. gameconfig --ability Stormcaller / --trait TerminatorArmour / NoBlocking)
  `▸ Tac: rôle=engine (Psychic-AoE armor-ignore, la wincon-pair avec un seeker/summoner type Sho'syl) · menace=high (Psychic NoBlocking bypasse l'armure ET TerminatorArmour de mes Terminators ; AoE hex+adjacents → multi-unit cluster threat ; stun mes Flying carries ; LordOfTempests snowball par ice-hex ; ne peut pas être Suppressed) · counter=STUN-le d'abord (Aesoth VexillaMagnifica) pour dénier son AoE un round, PUIS focus-kill ; bypass de SON TerminatorArmour = Psychic/Direct OU focus multi-attaquant en un team-turn (1ʳᵉ attaque réduite, le reste full — vécu seed 70001 : mort T4) OU un attaquant Mechanical HeavyGravCannon (Sy-gex bonus vs TermArmour : 4-hit clean, vécu seed 70058) ; move2 lent → le zoner/out-ranger avec des r3 dealers, devient ATTEIGNABLE une fois son screen mêlée dive/mort (vécu seed 70058 : tué T4) ; NE PAS laisser un carry Flying stationnaire dans sa portée Ice (risque stun) [n=3, 70001+70058]`
  `▸ Tac (n+1 AoE multi-cible CÔTÉ-MIEN, self-play seed 80085 — A possédait Njal, recoupé gameconfig) : Stormcaller = OUTIL D'OUVERTURE DE FOCUS quand l'ennemi est groupé. Vécu seed 80085 (A, about=mine) : UN cast a pré-chunké DEUX cibles à la fois (cible + adjacent) → l'une est devenue un K! garanti et l'autre pré-amorcée pour le mop-up. DOCTRINE : ne pas gâcher Stormcaller sur 1 cible isolée — viser le hex qui maximise les ennemis dans le rayon Ice (cible + adjacents) pour ouvrir un multi-finish ; le multi-hit Psychic ignore l'armure ET bat le floor Resilient. [self-play seed 80085, recoupé gameconfig Stormcaller]`
- **astraBullgryn « Kut » (Astra Militarum, mêlée, anvil/BigTarget)** — `BigTarget` (cf. §1 — alliés
  adjacents −1 hit ranged ; non déplaçable). KIT (observé n=1, NON Verif-confirmé ce wave — à recon
  gameconfig avant de planifier autour) : `FragBomb` multi-hits + splash à TOUS les adjacents à la
  cible ; `AvalancheOfMuscle` +dmg en chargeant ; bruiser lent. (cf. gameconfig --ability FragBomb / AvalancheOfMuscle / --trait BigTarget)
  `▸ Tac: rôle=anvil · menace=med (écran/anvil des dealers, PAS la wincon : son aura BigTarget −1 hit ranged shield leurs dealers de mon ranged ; FragBomb cluster-splash + AvalancheOfMuscle = danger s'il atteint une grappe) · counter=ne PAS investir d'output dessus (puits) ; racer les softs/engines ; éviter de clusterer mes units face à son FragBomb-splash (vécu seed 70003 : barrage-chippé, n'a pas engagé T1) ; ⚠ **PAS de Resilient/FinalJustice → K! propre une fois atteignable** (vécu seed 70009 : Trajann WarHowl-buffé l'a K!'d depuis sa tuile dans le burst ; vécu seed 70008 : chunké par une charge Gulgortz Waaagh puis fini = anvil sans wincon n+1 ; vécu seed 70056 : pur anvil SANS amplificateur → secondaire, tué EN DERNIER une fois isolé par une K! Re'vas, aucun FJ/Resilient = confirme « anvil sans wincon, faible valeur stratégique » n+2 ; son aura BigTarget devient sans objet une fois isolé) [n=4, 70009/70008/70056]`
- **astraDreir « Dreir »** — (déjà décrit ci-dessus, inchangé)
- **genesMagus « Xybia » (Genestealer, Psyker, summon-engine)** — wincon classique : `MindControl`
  (cf. §1 — range 3, Taunt l'allié adjacent au + haut PV + débuff dmg + coupe l'actif de la cible),
  summon de **Neophyte Hybrids**, et trait **`Ambush`** (cf. §1 — 1ʳᵉ mort → decoy + resurrect full ;
  2ᵉ kill PERMANENT). Psychic Pierce100 NoBlocking = ignore armure. **Le 1ᵉʳ kill est TEMP tant qu'un decoy
  survit** → clear les decoys (Steppable, marcher dessus) OU accepter le temp-kill et planifier la 2ᵉ mort.
  Contre-pièces : Atlacoya Talons passe Direct vs Psyker (sauf taunt-lock) ; un heal cleanse ses débuffs
  MindControl ; tout Psychic NoBlocking ignore son armure. (cf. gameconfig --ability MindControl / --trait Ambush)
  `▸ Tac: rôle=engine · menace=critical (summon + MindControl + Ambush-resurrect = wincon) · counter=kill early MAIS 1ᵉʳ kill TEMP (Ambush) sauf decoys clear → 2ᵉ kill PERMANENT (vérifié seed 98001 : Xybia tuée 1× → decoy + revive full T+1 ; 2ᵉ kill = RemoveUnit WasOverkilled, AUCUN decoy/revive — first-defeat-only confirmé) ; un assassin anti-Psyker (Tjark) la K! outright ; ⚠ quand ELLE MindControl une de mes unités, le `Taunted_OnlySpecificTargets` FORCE ma unité à taper LE taunter (Xybia adjacente) → si elle est l'allié-adjacent-au-plus-haut-PV, tuer LE taunter dans cette même action clear les 6 sous-effets instantanément (vécu seed 98001 : MindControl sur Tjark → Tjark forcé sur Xybia → je la tue, Tjark libéré) ; heal cleanse le MindControl [n=2]`
- **tyranParasite « Parasite of Mortrex » (Tyranid, move4 Flier, summon-engine)** — `ItItches` summon des
  **Ripper Swarms** (cf. summons §) + `BarbedOvipositor` (spawn un Ripper quand IL tue une cible non-Mechanical).
  **PAS de resurrect** → le tuer PERMANENT et tôt pour nier le snowball Rippers. ~9k PV, tuable en un tour par
  2-3 sources focalisées (melee/Blast + Psychic). Move4 = très mobile, difficile à kiter. (cf. gameconfig --ability ItItches / BarbedOvipositor)
  `▸ Tac: rôle=engine · menace=high (Ripper snowball, move4 mobile) · counter=kill PERMANENT et tôt (pas de revive) ; focus 2-3 sources en un tour ; surveiller ses Rippers (BattleFatigue à la mort d'un ami adjacent) [n=1]`
- **spaceBlackmane « Ragnar » (Space Wolves, mêlée carry)** — `WarHowl` : self-cast (--target sur Ragnar
  lui-même) qui octroie, **jusqu'à la fin du tour**, à **Ragnar ET tous les Characters alliés SANS normale
  RANGED** (exclut p.ex. Abraxas qui a une normale ranged) : **Unstoppable + +dmg de mêlée + +Crit Chance**
  (i2-vérifié seed 70009 : refresh sur 4 Characters mêlée, PAS sur Abraxas). ⚠ **ne CONSOMME PAS le tour de
  Ragnar** (resté à activer après le cast) ET exige que **Ragnar n'ait PAS bougé** avant de caster → le séquencer
  EN PREMIER, avant le burst (cf. §5bis MIEN-À-ENCHAÎNER). `SagaOfTheWarriorBorn` (+hits à la charge). Attaque normale
  **multi-hit Chain low-pierce** (faible pen armure → armure/Terrifying blunt). Trait **`FinalJustice`** (cf. §1 — riposte
  normale multi-hit à la mort, source-agnostique, sauf Overkill ou aucun adjacent éligible). (cf. gameconfig --ability WarHowl / --trait FinalJustice)
  `▸ Tac: rôle=carry · menace=high (buff d'équipe + charge +hits) / med si on peut LOCK son WarHowl · counter=le tuer AVANT WarHowl ; normale Chain low-pierce = faible pen → armure/Terrifying l'amortit ; ⚠ **un TAUNT lui coupe WarHowl** (vécu seed 70006 : Azkor OverwhelmingWrath Taunt = Taunted_OnlySpecificTargets + BlockMovement + CantUseAbility → Ragnar n'a PAS pu caster WarHowl, movement-locké, forcé de frapper le taunter Terrifying qui a blunté sa mêlée ; cf. H30) ; un STUN (Aesoth VexillaMagnifica) le verrouille aussi (Stunned + MovementOverride + CantUseAbility) = engine-disable total ; pour neutraliser FinalJustice : Overkill OU positionner pour que sa riposte tape un TANK (vécu seed 70006 : FJ absorbée par Aesoth tanky = trivial) OU pas d'adjacent éligible · si à MOI : caster WarHowl EN PREMIER (Ragnar n'a pas bougé, ne finit pas le tour) PUIS le burst mêlée des Characters buffés — le +dmg/hit énorme sur les multi-hit a converti plusieurs plans en K!, 3 kills en UN tour (vécu seed 70009) · ⚠ **vs un Ragnar ENNEMI = la SOURCE-wincon d'un roster all-melee** (WarHowl pump toute la ligne mêlée) → le tuer AVANT son 1er cast gutte toute l'offense ennemie (vécu seed 70056 : Ragnar tué EN RÉACTION dans mon cluster Overwatch/dive-punish AVANT d'avoir jamais casté WarHowl = W ; son FJ low-pen routée sur un tank ou overkill) ; ⚠ **CONFIRM n+1 (seed 70059 W)** : Ragnar = SOURCE-wincon de la ligne all-melee, chunké T2 puis tué T3 via Psychic AoE AVANT tout WarHowl → la ligne n'a JAMAIS été buffée ; ATTEIGNABLE parce que le bulk all-melee+anvil était CONTRAINT de diver (son FJ low-pen négligeable sur mon Typhus) [n=5, 70009/70006/70056/70059]`
  `▸ Tac (n+1 DÉFANG-PAR-LES-BÉNÉFICIAIRES, seed 70057 W) : WarHowl ne pump QUE les melee Characters SANS normale ranged (cf. KIT) → une 2ᵉ voie pour neutraliser l'engine = **tuer ses BÉNÉFICIAIRES avant l'engine lui-même**. Vécu seed 70057 : tué Dante+Helbrecht (les melee Characters bénéficiaires) T3-T4 → au moment où j'ai tué Ragnar T5, WarHowl ne pouvait plus que le SELF-buff = engine défangé même non-pré-empté ; son FJ low-pen a fire (non-overkill) mais trivial sur mon Mataneo armuré Mechanical (confirme la routing-onto-armored §1). DOCTRINE : contre un WarHowl-engine, soit le tuer pre-cast (n=5 ci-dessus), soit vider sa liste de bénéficiaires melee s'ils sont plus atteignables que lui [n=6, +70057]`
  `  ▸ Tac (n+1 FJ ≫ CHUNK D'UN CARRY FULL-HP — self-play consensus, seed 80053 W) : ⚠ la FinalJustice de Ragnar tué NON-overkill peut **quasi-tuer un carry plein-PV en une riposte** — vécu : Ragnar tué par une seule source non-overkill alors qu'un carry full-HP (Mephiston) était dans son arc FJ → la riposte multi-hit (RapidAssault/Saga-buffée) l'a chunké à ~6% PV (puis fini le tour suivant) = perte d'unité ENTIÈREMENT ÉVITABLE. Le « normale low-pen = négligeable » du n=5 vaut **seulement contre un body ARMURÉ** (routing-onto-armored) ; contre un carry NON-armuré/full-HP en pleine portée, l'agrégat des hits ≈ near-kill. DOCTRINE : avant le coup létal sur Ragnar, soit **OVERKILL** (Crit ou dmg > 2× PV restants), soit **dégager mes carries non-armurés de son arc FJ** (router la riposte sur un tank ou tuer hors-portée-de-la-normale). Cross-confirmé self-play : A(theirs) + B(mine, FinalJustice listée sur Ragnar). [self-play consensus, seed 80053]`
- **orksNob « Tanksmasha » (Orks, mêlée carry, ~10k PV, move4, BigTarget, NON-Resilient)** — traits gameconfig
  (Verif seed 70056) : **Hero, GetStuckIn, BeastSlayer (+dmg vs BigTarget/Vehicle), Unstoppable — AUCUN FinalJustice,
  AUCUN Resilient**. Bruiser mobile move4 + charge (Suppress) ; `FragBomb`/Eviscerate multi-hit. **`UnstoppableMomentumReworked`**
  (actif charge, Verif seed 70061) = **DirectDamage Pierce100** (1 hit, **+dmg par hex traversé** ; bonus `SmashaEad` après un
  move 2+ hex). **Pas de death-riposte ni de plancher HP** → meurt proprement à tout coup finisseur une fois chunké.
  (cf. gameconfig --ability UnstoppableMomentumReworked / --trait BeastSlayer)
  `▸ Tac: rôle=carry · menace=high (move4 charge + BigTarget + BeastSlayer = shred mes BigTarget/Vehicle s'il connecte ; over-extend agressivement) · counter=PUNIR le dive (move4 = il dive profond — vécu seed 70056 : dove dans MA moitié T1 → chunké par l'Overwatch Re'vas AVANT mon tour, puis focus-killé depuis mes back tiles, AUCUN forward push nécessaire puisqu'il est venu À MOI) ; ⚠ **PAS de Resilient/FinalJustice → K! propre une fois atteignable**, aucun floor ni riposte à respecter ; BeastSlayer ne compte que vs mes BigTarget (Re'vas) → screener mes BigTarget s'il connecte, mais il n'a jamais connecté ici [n=1, 70056]`
  `▸ Tac (n+1 UnstoppableMomentumReworked multi-target-in-line CONFIRMÉ self-play consensus, seed 80000) : la charge hit TOUS les ennemis sur la LIGNE droite en UN passage — **vécu seed 80000** (B, about=mine) : une seule charge a touché Tigurius ET Exitor-Rho dans la même rangée. gameconfig confirme « Any enemies hit by the charge take 1× Direct Damage ». ⚠ **directionnel** : la ligne choisie au moment du cast décide QUI est hit ; un groupe linéaire adverse = frappe multi-cible gratuite, un groupe en arc = un seul hit. Planifier la direction de la charge pour maximiser le hit-count. ⚠ **tuile d'arrêt = mort** si c'est une EnvEndBombardment active : Tanksmasha s'est arrêté post-charge sur une tuile de bombardement et a été détruit à l'endturn — évaluer la tuile d'arrivée avant de caster. [self-play consensus, seed 80000]. [n=2, 70056/80000-sp]`
  `▸ Tac (NUANCE block BeastSlayer — self-play seed 80000 roundcap + recoupage gameconfig) : ⚠ **le « K! propre / aucun floor » ci-dessus a un caveat probabiliste** — `BeastSlayer` porte une clause de BLOCK (gameconfig : **chance de bloquer 100% de son armure courante** sur un coup entrant). Vécu seed 80000 (A, about=theirs, confidence med) : un burst multi-source K?-labellé a chunké Tanksmasha bas mais **il a SURVÉCU** — le block a absorbé assez pour qu'un K? sous-kill. ⚠ A a mis-labellé ça « BeastSnagga_ExtraBlock » mais gameconfig confirme : orksNob n'a PAS BeastSnagga, c'est la clause block de **BeastSlayer** (cf. hypotheses.md, divergence A/B flaggée). DOCTRINE : un finisher **K?** (pas K!) sur un BeastSlayer-carrier peut whiffer via block → préférer un OVERKILL franc (≥2× la barre, ou 3+ sources discrètes) quand le kill est décisif, ne pas budgétiser un K? near-lethal comme garanti. [self-play seed 80000 roundcap, recoupé gameconfig BeastSlayer]`
  `▸ Tac (À MOI — anti-MkXGravis, CONFIRMÉ Verif seed 70061) : `UnstoppableMomentumReworked` = **Direct Pierce100** → bypasse ENTIÈREMENT la double-armure MkXGravis (Bellator/Inceptors : « incoming damage va à travers l'armure 2× SAUF Crit/Direct », cf. §1) puisque DirectDamage ignore l'armure. ⚠ MAIS le dmg est **distance-dépendant et LOW à courte portée** (+dmg/hex seulement) → de 1 hex avec SmashaEad ≈ **PAS un Bellator-cracker fiable seul** (vécu seed 70061 : insuffisant sur Bellario ; le kill réel = Certus HeavyRound Pierce55 + réactions cluster). USAGE : réserver Tanksmasha pour une CHARGE LONGUE (maximiser les hex traversés = +dmg/hex + SmashaEad) sur la cible MkXGravis, OU le combiner à un finisher ranged (Certus Pierce55 + reactions) — ne jamais compter sur la seule charge courte pour cracker un tank double-armuré. [n=1, 70061 chained]`

- **orksKillaKan « Snappawrecka » (Orks, ranged, carry, BigTarget, NON-Resilient)** — carry ranged **repair-SCALING** :
  `DakkaDakkaDakka` (multi-hit ranged + leftover chaîne vers un ennemi proche) dont le **nombre de hits monte avec
  les repairs reçus** (Snappawrecka est **Mechanical** → repairable par Aleph-Null/Gibbas) → devient PLUS létal à
  mesure qu'on le soigne. `PowerTrip` ignore l'armure. `Explodes` à la mort (cf. §1, friendly-fire). (cf. gameconfig
  --ability DakkaDakkaDakka / --trait PowerTrip / --trait Explodes)
  `▸ Tac: rôle=carry · menace=CRITICAL (repair-hub backline en fait un nuke ranged croissant + armor-ignore + leftover-chain) · counter=NE JAMAIS out-DPS le carry réparé — KILL Snappawrecka OU sa SOURCE de repair (Aleph-Null) early/au range ; soft no-Resilient mais BigTarget ; `Explodes` à la mort → finir au range ; ⚠ une source de repair row 5-7 le rend inatteignable pour un roster mêlée = STRUCTURAL counter à flagger au recon (carry+repair jamais atteints = décide l'attrition) [n=1, 98000]`
- **tauDarkstrider « Darkstrider » (T'au, ranged, control, soft NON-Resilient)** — buff-engine markerlight :
  `StructuralAnalyser` (ses tirs ranged posent un **markerlight** ; les alliés adjacents / T'au à ≤2 hex font du
  bonus ranged vs cible marquée — Darkstrider SE qualifie via la clause T'au-à-≤2-hex). `RangedSpecialist`,
  `SuppressiveFire` (Suppress/Pinned via ranged), `FightingRetreat` (attaque + repli, ne finit PAS le tour),
  `Infiltrate` (ignore l'Overwatch ennemi → s'approche gratis, PAS attrapé par une tourelle OW). (cf. gameconfig
  --ability StructuralAnalyser / --trait SuppressiveFire / --trait Infiltrate)
  `▸ Tac: rôle=control (buff-engine markerlight) · menace=high SI ≥1 autre allié RANGED à feeder, sinon **LOW (engine INERTE)** · counter=le tuer au RANGED (Infiltrate = pas catchable par mon OW) ; ⚠ **DEMOTE high→low quand Darkstrider est le SEUL ranged de SON équipe** (markerlight self-fed sans bénéficiaire = inerte, même famille engine-inerte-sans-bénéficiaire H02/H33 — équipe 4-melee → traité en corps soft, tué dans le dive) ; SECONDAIRE après les vrais carries [n=2, 98000/70056]`
  `▸ Tac (À MOI — CONFIRMÉ live, seed 70054) : `StructuralAnalyser` (passif) = CHAQUE tir ranged pose un **Markerlight** (Effect_Id 188/208) sur la cible ; alliés adjacents + T'au à ≤2 hex font du bonus ranged vs cible marquée (Darkstrider se qualifie via clause T'au-à-≤2-hex). `SuppressiveFire` = chaque tir Suppress AUSSI la cible (Pinned, confirmé live). STACK : RangedSpecialist × markerlight-self × buff d'adjacence → Darkstrider devient mon dealer ranged single-source DOMINANT quand le positionnement est tenu (= mes plus gros hits du combat). USAGE : ORDONNER Darkstrider EN PREMIER dans chaque focus (poser markerlight + Pinned AVANT que les alliés tirent) ; le garder en portée pour empiler ses tirs + le buff d'équipe. ⚠ le delta de bonus spécifique aux ALLIÉS reste non isolé numériquement (cf. H33) mais la mécanique markerlight + Pinned est confirmée live [n=1, 70054 chained] (cf. gameconfig --ability StructuralAnalyser)`
- **thousSorcerer « Thaumachus » (Thousand Sons, Psyker, engine, soft NON-Resilient, Flying)** — ⚠ KIT en partie
  recon-only (cf. H28/H29) : `ArcaneShield` (bouclier à l'allié non-Mechanical le + proche ≤2 hex, **priorité
  Thousand Sons > Chaos > autre allié > self** ; dure 1 round — **persiste possiblement même si Thaumachus meurt**,
  cf. H29 : a absorbé un gros coup après la mort du caster). ⚠ **TRIGGER confirmé live (seed 70053)** : se déclenche
  APRÈS son move, OU à la FIN de son tour s'il N'A PAS bougé → tenir Thaumachus stationnaire repose le bouclier sur le
  même allié chaque tour. `AttemptedPossession` (mind-control une cible ET ses summons → ils attaquent mon camp) ;
  `WeaverOfFate` (max-dmg si 3+ ennemis ont subi du Psychic). Psychic NoBlocking (ignore armure). (cf. gameconfig
  --ability ArcaneShield / --ability AttemptedPossession / --ability WeaverOfFate)
  `▸ [self-play consensus, seed 80097]` **AttemptedPossession LIVE-CONFIRMÉ (upgrade H28 recon-only → vérifié).** A (about=mine) a SUBI live : Thaumachus a HIJACKÉ ses 2 Screamers (summons) sur le tour ennemi → les a **avancés (row 1 → row 6) PUIS forcés à attaquer le camp de A** (le camp d'A = ennemi du point de vue des summons possédés). Confirme les 2 clauses précédemment recon-only : (1) possède la cible ET ses summons ; (2) **les summons possédés bougent AVANT d'attaquer**. DOCTRINE renforcée : **garder mes summons HORS de la portée 2-hex de Thaumachus tant qu'il vit** (sinon mes propres summons forward sont retournés contre moi) → le tuer/disable AVANT de committer des summons près de lui. [self-play consensus, seed 80097] (cf. gameconfig --ability AttemptedPossession)
  `▸ Tac: rôle=engine (psychic/shield + anti-summon + WeaverOfFate-amplifier) · menace=high (ArcaneShield protège leur carry + AttemptedPossession anti-mes-summons + WeaverOfFate MAX-dmg si 3+ cibles Psychic + Psychic armor-ignore) · counter=(1) le DISABLE par CrushingClaws Taunt (Taunted_CantUseAbility) le neutralise TOTALEMENT 1 round = le meilleur disable (cf. H30 : Taunt-locké tout le combat, n'a JAMAIS casté) ; (2) le tuer TÔT avec un ranged no-move K! → retire bouclier + possession + menace psychic ; soft NON-Resilient → killable franc, MAIS ne PAS le focus AVANT Tigurius (block-aura PsychicFortress + AoE re-firante valent plus — split-focus Thaumachus/Tigurius = erreur, FULL-focus Tigurius d'abord) ; ⚠ budgétiser le bouclier posthume sur sa cible avant de committer un coup létal dessus (H29) ; ✅ **À MOI = durabilité gratuite sur le carry** : le garder STATIONNAIRE → ArcaneShield (no-move → end-of-turn trigger) repose le bouclier sur l'allié non-Mechanical le + proche chaque tour (priorité Thousand Sons > Chaos > autre) → glue mon ranged carry à ≤2 hex pour qu'il reste shielded en continu (carry intouchable tout le combat) [n=3, 98000/70000/70053]`
- **ultraInceptorSgt « Bellator » (Ultramarines, Flying, move4, MkXGravis)** — summon-engine : **`DeathFromAbove`**
  invoque **1 Inceptor par ROUND ÉCOULÉ** (round 1 = 1, round 2 = 2, …) — vague CROISSANTE — chacun atterrit
  **adjacent à la cible** et l'attaque **immédiatement** (cf. entrée summon Inceptor §3bis pour les stats). Passif
  **`ShockAssault`** : quand Bellator attaque, tout Inceptor adjacent à LUI ré-attaque. **`MkXGravis`** = double-armure
  SAUF **Crit/Psychic/Direct** (cf. §1) → vulnérable au Direct Pierce100. Flying move4 = mobile. (cf. gameconfig
  --ability DeathFromAbove / --trait ShockAssault / --trait MkXGravis)
  `▸ Tac: rôle=engine (summoner) · menace=high (DeathFromAbove = flood d'Inceptors CROISSANT chaque round move4 + ShockAssault re-attaque ; MkXGravis double-armure le rend dur au chip ranged) · counter=le tuer pour couper le flood (gating caster-mort : killer Bellator STOPPE la vague suivante) ; son MkXGravis se BYPASSE au **Direct/Psychic/Crit** (DoomSiren Direct Pierce100 l'a chunké + 2 Inceptors en un cast) — réserver un Direct/AoE-Direct pour un cluster Bellator+Inceptors ; mobile (Flying move4) donc le catcher quand il close ; ⚠ DeathFromAbove = board-flip CROISSANT que le move-guard 2-ply ne voit pas (cast round 3 → 3 Inceptors move4 landent adjacents à ma backline + attaquent direct) — MAIS rendu ATTEIGNABLE quand l'IA dive forward → le tuer/stun EARLY ; HP plus basse que son rôle ne suggère (meurt vite une fois chunké) ; stun-then-finish via VexillaMagnifica ; ⚠ le crack pratique = **Certus HeavyRound Pierce55 (partiellement à travers la double-armure) + réactions cluster sur le dive**, PAS le Tanksmasha Direct Pierce100 (trop low à courte portée — bypasse MkXGravis mais ne crack pas seul) ; ⚠ « les Inceptors summonés portent MkXGravis » = OBSERVÉ non recoupé (gameconfig liste MkXGravis sur Bellator, PAS sur ultraSmnInceptor — cf. H52) [n=3, 70000/70053/70061]`
- **tyranNeurothrope « Neurothrope » (Tyranids, Psyker, move2, Flying, backline)** — snowball-engine :
  **`Neuroparasite`** escalade en dégât Psychic à chaque hit (cap ~15 niveaux) ; **`SpiritLeech`** self-heal massif
  → **inkillable en late game** une fois empilé (r3 + Flying + heal). `Synapse` (buff les Tyranids autour) +
  **`ShadowInTheWarp`** (réduit MON Psychic). Le Psychic NoBlocking bypasse armure/BigTarget. Vraie wincon late-game
  d'une compo Psychic-cascade (armé par tout ce qui touche 3+ de mes units en Psychic). (cf. gameconfig --ability
  Neuroparasite / --ability SpiritLeech / --trait ShadowInTheWarp)
  `▸ Tac: rôle=engine (snowball Psychic) · menace=CRITICAL (Neuroparasite escalade/hit + SpiritLeech self-heal + r3 Flying = inkillable late ; devient la vraie wincon une fois snowballé) · counter=LE TUER EN PREMIER avant qu'il snowball ; MAIS backline + move2 + Flying + r3 = très dur à atteindre pour un roster melee/r2 → pré-positionner un reach-dealer r3+/deep-strike T1 OU flagger la loss structurelle au recon (resté FULL tout le combat, jamais atteignable = root cause partagée, énième reach-fail, cf. série 19355/96001/97001) ; ShadowInTheWarp réduit MON Psychic = ne pas compter sur un finish Psychic facile [n=2, 19355/70000]`
  `▸ [self-play consensus, seed 80064]` SpiritLeech (Psychic r3, self-heal) CONFIRMÉ n+1 comme engine self-sustaining stacké : même tour, SpiritLeech + un gros Direct allié sur la cible = un de mes carries chuté très bas, et le Neurothrope s'auto-heal vers le full. ⚠ Vulnérabilité confirmée : le Neurothrope **Flying** se fait Stun-lock par Stormcaller Ice-AoE (Njal) → SpiritLeech refusé ce tour-là (B a perdu un tour de leech ainsi). Les 2 sides concordent. Backline (row 5-6) = jamais atteint par le roster melee/r2 adverse cette partie aussi → re-confirme la reach-fail structurelle vs ce backline. [self-play consensus, seed 80064]
  `▸ [self-play consensus, seed 80072]` **Neuroparasite snowball + clear-on-death/heal** CONFIRMÉ n+1 par les DEUX sides : escalade Psychic/niveau (monte sur Psychic-dmg OU Suppress, cap ~15), **clear quand le Neurothrope meurt OU la cible est heal**. A (mine) : SpiritLeech a posé Neuroparasite L2 + Pinned sur une cible, puis le Psychic d'un autre caster sur la MÊME cible a hit plus fort (stacking confirmé) ; B (theirs) : parasite removed on the Neurothrope's death → tuer le Neurothrope stoppe le scaling ET nettoie les parasites existants. ⚠ Ce match : A n'a JAMAIS armé WeaverOfFate (Psychic ne touchait que 1-2 ennemis/tour → caster jamais MAX → le snowball a stalled) → la wincon Psychic-cascade exige de spread 3+ Psychic/tour, sinon le moteur ne démarre pas. [self-play consensus, seed 80072] (cf. gameconfig --ability Neuroparasite)

> Les unités invoquées ont leur propre kit/traits (gameconfig : ids `*Smn*` / `*Npc*`).
> **Les recon dès qu'elles apparaissent** — leurs traits dictent la gestion. Stats
> indicatives (texte de l'ability du parent / gameconfig).

- **genesSmnDecoy « Decoy »** (laissé par `Ambush`) — HP0, traits `Steppable` + `Decoy`
  (cf. §1). → le détruire en **marchant dessus** (`act move --to <son hex>`) coupe la
  résurrection Ambush.
- **tyranNpc4Warrior / Tyranid Warrior** (`AlphaWarrior` de WingedPrime) — ranged ;
  ne bouge pas le tour d'invocation mais attaque + **réagit** (a tué 2 drones en réaction
  sans jouer de tour). (cf. gameconfig --ability AlphaWarrior)
- **tyranSmnHormagaunt** (`SynapticLinchpin`) — spawn adjacent à une cible attaquée par une
  **normale Synapse non-tuante** (Winged Prime ou tout allié Synapse), **attaque immédiatement**
  la cible (max 4 simultanés ; HP scale rank). (cf. gameconfig --ability SynapticLinchpin)
- **astraNpc1Guardsman / Cadian Guardsman** (Yarrick `SendInTheNextWave` / MoW
  `ForwardSpotter`) — ranged ; **attaque immédiatement** à l'invocation.
- **tauSmnDroneShield « Shield Drone »** (Re'vas `EarlyWarningOverride`) — attaque à
  l'invocation ; meat-shield (BigTarget réduit les hits ranged sur Re'vas).
- **genesSmnAberrant « Aberrant Hypermorph »** (Biophagus) — attaque immédiatement.
  `▸ Tac: rôle=chaff · menace=med (juste un summon de Hollan, Resilient/Summon mais SANS snowball) · counter=PAS une priorité sur les hero-engines (Hollan/Xybia/Abraxas) → le tuer quand pratique ; ⚠ HP gonflée bien au-dessus du base par le heal-revive Hollan TwistedScience (recon-on-appearance la PV runtime, jamais le tooltip) ; un BeastSlayer l'a one-shot malgré la PV pumpée [n=1, 98001]`
- **deathPoxwalker** (Corrodius `Poxwalkers`) — spawn dans l'aura Contagion, attaque
  immédiatement ; tuer le summoner coupe le flux. ⚠ **trait `Summon`** (Verif gameconfig/i2
  seed 70056) : i2 = « Moves and attacks automatically at the beginning of its turn » →
  **non-commandable** (absent de « À ACTIVER » ; `act=ability` renvoie `ok=True/mutated=False`) —
  auto-acté par l'engine, l'oracle ne doit PAS queue ses actions (même H41 pattern que tout
  summon Summon-trait : Ork Boys, Death Riders…). Ne pas gaspiller de micro à tenter de le piloter.
- **necroSmnSwarm « Scarab Swarm »** (Aleph-Null `ScarabHive`) — **move4**, Swarm/Flying ;
  spawn 2× à côté de la cible, **attaquent immédiatement** (Piercing 1ᵉʳ hit) ;
  `ReanimationProtocols` (revive sauf **Overkill**). (cf. gameconfig --trait ReanimationProtocols)
- **bloodSmnIntercessor « Jump Pack Intercessor »** (Mataneo `AggressiveOnslaught`, sur charge) —
  Summon/Flying/RapidAssault/RedThirst ; attaque immédiatement ; **quitte le terrain au début de
  chaque tour de Mataneo** (~1 tour).
- **astraSmnDeathRider** (Dreir `LeadingTheCharge`) — move4, FragLance ; jusqu'à 4, adjacents à
  Dreir, attaquent immédiatement.
  `▸ Tac: rôle=chaff · menace=med (soft, non-Resilient) · counter=les AoE/focus down (un AoE-cleave a pris les 3 en UN cast quand ils ont dive clusterisés) ; mieux : NIER le summon en amont (taunt Dreir avant son cast, ou tuer Dreir avant LeadingTheCharge) [n=1, 98000]`
- **admecSmnVanguard / Skitarii Vanguard** (Tan Gi'da `ControlEdict` sous Protector) — Mechanical, **Summon** (auto move+attaque en début de tour), Toxic r2 (Pierce) + mêlée, passif `RadSaturation` (pose Contamination sur son hex) ; cap 5 simultanés. (cf. gameconfig --ability ControlEdict, --trait RadSaturation)
- **astraSmnGuardsman / Cadian Guardsman** (Yarrick `SendInTheNextWave`) — Las r2 ; **Summon** (auto move+attack) + **BattleFatigue** (peut fuir si un ami adjacent meurt, pire si overkill) ; tire immédiatement au cast. NB id `astraSmnGuardsman` (PAS `astraNpc1Guardsman`). (cf. gameconfig --ability SendInTheNextWave, --trait BattleFatigue)
- **genesSmnNeophyte / Neophyte Hybrid** (Isaak `CultDemagogue`) — ranged r2 ; **Summon** + **Ambush** (1ʳᵉ mort → decoy → resurrect full sur decoy ami) ; prend un tour immédiat au spawn. Note quirk : PV live peut dépasser le max gameconfig (scaling émergent niveau × rareté, **pas une contradiction**). (cf. gameconfig --ability CultDemagogue, --trait Ambush)
  `▸ Tac: rôle=chaff (issu du board-flip Isaak) · CHACUN porte Ambush ; 3+ spawnés par CultDemagogue prennent un tour immédiat → out-number + chip-kill une ligne fragile · counter=le VRAI fix = tuer Isaak AVANT le cast (cf. Tac Isaak) ; une fois spawnés, clear les Hybrids ET piétiner les decoys (Steppable) pour nier le resurrect Ambush ; ne pas les chiper un par un pendant que l'engine tourne (board-flip 3v12 possible) [n=1, 70007]`
- **genesSmnGenestealer / Purestrain** (Patermine `MightFromBelow`) — move3 mêlée Bio Pierce ; **Infiltrate** (pas d'Overwatch) + **Ambush** (resurrect full sur decoy ami) + Unstoppable ; attaque immédiate au spawn, pas de move ce tour. (cf. gameconfig --ability MightFromBelow, --trait Ambush)
- **thousSmnBlueHorror / Blue Horror** (Archimatos `Possession`, sur kill RANGED) — ranged r2 Flame+OnFire, move3 ; Summon/WeaverOfFate/Daemon ; `FlamesOfMutation` (met le hex En Feu à la mort SAUF Overkill). Quirk de branche : kill MÊLÉE → Bloodletter à la place (pas Blue Horror). (cf. gameconfig --ability Possession, --trait FlamesOfMutation)
- **thousSmnPinkHorror / Pink Horror** (Abraxas `MasterOfTheTutelaries`) — **Summon** (attaque immédiate au spawn, pas de move ce tour) ; spawné sur un hex libre adjacent à Abraxas. (cf. gameconfig --ability MasterOfTheTutelaries)
  `▸ [self-play consensus, seed 80097]` **passif `Split` = à sa MORT, summon 2 Blue Horrors sur hexes adjacents — SAUF si Overkilled.** Confirmé par les DEUX sides (mine « free replacement bodies » ; theirs « daemon resilience inflating body count »). gameconfig confirme `Split {unitId:thousSmnBlueHorror}` + « Does not apply if Overkilled ». Les Blue Horrors peuvent attaquer immédiatement s'ils spawnent durant le tour du Pink Horror, mais ne bougent pas avant leur tour suivant. → DOCTRINE : un Pink Horror chippé est un PIÈGE de body-count (1 mort = 2 corps de remplacement r2) ; pour le retirer NET, **Overkill** (annule le Split, comme Resilient/FinalJustice). (cf. gameconfig --trait Split) [self-play consensus, seed 80097]
- **thousSmnScreamer / Screamer of Tzeentch** (Abraxas `MasterOfTheTutelaries`, chaîne) — **Summon** (attaque immédiate au spawn, pas de move) ; spawné **1 par dégât Psychic infligé à un ennemi** (jusqu'à fin de tour) sur un hex libre proche d'un ennemi → un AoE/splash Psychic multi-cibles peut en **cascader plusieurs** (1 instance de dégât Psychic = 1 Screamer). (cf. gameconfig --ability MasterOfTheTutelaries)
- **necroNpc1Warrior / Necron Warrior** (Anuphet `ResurrectionOrb`) — Gauss r2 + LivingMetal/ReanimationProtocols ; **scaling sur l'INDEX de round interne, PAS le tour affiché** (1 par round DÉMARRÉ +1 par allié Living Metal défait) ; non-commandable le tour du spawn mais menace via Overwatch (H17). (cf. gameconfig --ability ResurrectionOrb, --trait LivingMetal)
- **tyranNpc2RipperSwarm / Ripper Swarm** (Parasite `ItItches`/`BarbedOvipositor`) — move3, Swarm (5 membres) + **BattleFatigue** (peut fuir si un ami adjacent meurt) ; spawn dans un hex vacant, attaque immédiatement. Quirk : un Ripper « disparu » à la mort du Parasite = **BattleFatigue probable, PAS un despawn-summoner** (aucun lien de mort prouvé). (cf. gameconfig --ability ItItches, --trait BattleFatigue)
- **ultraSmnInceptor / Inceptor** (Bellator `DeathFromAbove`) — **1 par round démarré, plafonné par les hexes ADJACENTS LIBRES** autour de la cible (cluster serré ⇒ 1 seul spawn) ; atterrissent adjacents à la cible, attaquent immédiatement. Passif `ShockAssault` : quand **Bellator** attaque, tout Inceptor adjacent à LUI ré-attaque. (cf. gameconfig --ability DeathFromAbove, --trait ShockAssault)

---

## 3quater. Terrain / effets de tile (confirmés)

> Effets moteur portés par les hexes (gameconfig `aiUtilities.Default.TileEffects` + i2). Résout
> partiellement le TODO « sémantique terrain » du §6.

- **Razor Wire** (moteur : `Thorns_*` / Swamp) — un hex de Razor Wire : (1) une unité qui s'y TIENT subit **+50% Damage** ; (2) une unité non-Flying non-Unstoppable qui ENTRE sur le hex **termine son mouvement** là (besoin d'un tour de plus pour traverser) ; Flying/Unstoppable non affectés. L'IA native pénalise s'y tenir (TileEffect utility négative, même bande que Fire/Ice/SpiderWeb). **Tactique** : attirer un ennemi dessus (+50% dmg subi) ; ne JAMAIS y parquer mes unités au sol. (cf. gameconfig --effect Thorns_DefenseReduction ; i2 Keywords/TileRazorwire)
- **LightCover** (ex. hex DryBush) — accordé en posant le pied sur un hex cover : **réduit les attaques ranged multi-hit subies de 2 hits (min 1)**. Rester sur cover blunt le ranged multi-hit ennemi. (Effet de tile, i2 Keywords/UnitEffect_LightCover ; possible lien avec l'auto-finish H08.)
- **Contamination** (tiles posés par RadBombardment / aura Nurgle) — `Contaminated_Unit` sur les hexes ; les unités dedans subissent Toxic/effets selon la source. Sémantique exacte = TODO §6. (cf. gameconfig --effect Contaminated_Unit)
- **EnvEndBombardment** (effet moteur de round-cap — pas d'ability/trait source ni texte i2) — quand la limite de rounds approche, des effets `EnvEndBombardment_Incoming` tickent en compte-à-rebours, puis un **bombardement AoE board-wide** fire et inflige des dégâts massifs à TOUTES les unités des DEUX équipes. ⚠ **CONFIRMÉ self-play consensus, seed 80000 (opus run)** : nuke terminal qui **wipe l'intégralité du board** (alive_by_team={}, `winner=None`) = **draw / no-winner par sudden-death**. Il **overkill même un Resilient** (final hp=0). Il PUNIT les états d'attrition bas-PV et **annule une position gagnante** non convertie. DOCTRINE (recoupe §3bis Corrodius/Actus H51) : **le round-cap est une HORLOGE DURE** — quand on est ahead-on-quality mais qu'un anvil/engine adverse Resilient traîne, il faut FERMER le combat avant le cap (grind les anvils lents round 5-6, pousser une clôture cohésive) ; ne JAMAIS over-hold ni laisser le board en attrition basse-PV jusqu'au cap. [n=3, 70061/80000-sp(×2)]
  `  ▸ Tac (3ᵉ confirmation self-play seed 80000 — STANDOFF PASSIF MUTUEL) : run distinct où les DEUX oracles ont joué quasi-passif → EnvEndBombardment a fire et wipe les deux blobs = no-winner. ⚠ **les DEUX players ont identifié l'over-passivité comme leur #1 mistake** : « deux turtles face-à-face = round-cap no-winner garanti, l'un DOIT forcer une clôture cohésive ». ⚠ Le bombardement peut tomber PLUS TÔT que « ~round 10 » (cf. H51) : ne pas se reposer sur « j'ai jusqu'au round 10 ». [self-play consensus, seed 80000, run #4]`
  `  ▸ Tac (5ᵉ confirmation self-play seed 80000, run #5 « antipassivity » — QUALITY-AHEAD non converti) : run DISTINCT — A a JOUÉ activement, tué 3 héros ennemis et fini **4v2 EN AVANCE**… et a quand même subi le no-winner board-wide. ⚠ **LEÇON FORTE : être quality-ahead ne SAUVE PAS du cap — un no-winner round-cap est un DOUBLE-LOSS, pas un draw favorable.** Cause proximale de la non-conversion = A a CONSOLIDÉ au tour de conversion (reset actives) — doctrine « kill-or-hold » correcte EN ISOLATION mais l'**horloge OVERRIDE** : avec le cap telegraphé, FERMER un tour plus tôt, accepter un body-trade pour continuer à tuer. ⚠ friction : `EnvEndBombardment_Incoming` n'est PAS surfacé dans decisionView (EFFETS CRITIQUES) → countdown facile à rater. [self-play consensus, seed 80000, run #5]`
  `  ▸ Tac (6ᵉ confirmation self-play seed 80000, run roundcap — PERSPECTIVE NUMÉRIQUE INVERSE) : run DISTINCT — cette fois **team2 (B) était 5v2 DEVANT** et a quand même subi le no-winner board-wide faute de fermer les 2 derniers tanks avant le fire. ⚠ **re-confirme depuis l'autre côté** : que ce soit A 4v2 (#5) ou B 5v2, **l'avance numérique ne convertit PAS toute seule** — le cap est symétrique, il faut être en clôture cohésive par le ~6ᵉ tour. Cause proximale commune = tempo d'ouverture trop prudent (« should have forced contact 1-2 turns earlier »). [self-play consensus, seed 80000, run roundcap]`
  `  ▸ RE DÉFINITIF (ghidra + mesure live standoff passif seed 80000) — RÉSOUT les estimations floues #4/#5 : le cap = la constante **`nrOfRounds`** de la config EnvEndBombardment, **= 8** (lue dans le BC ; nuke = 20% PV max board-wide). 3 abilities Loki : Warning (pose l'effet Incoming), Marker, Damage (le nuke). DSL : Warning fire quand `TotalTurnsFinished == TurnsFromRounds(nrOfRounds)`, Damage à `nrOfRounds + offset`. MESURE 1v1 : `TurnsFromRounds(8)=16` → Incoming arme à TotalTurnsFinished=16 (= **8 tours par camp**) ⇒ **nuke ~2 turns (1 round) après le warning**, soit round ~9-10. ⚠ Les « round ~5-6 » (#4) et « ...=12 » (#5) étaient des **artefacts de compteur** : `GetAmountOfTurnsStartedByCurrentPlayer` (= `view.turn`) N'EST PAS monotone (oscille sur les tours passifs) ; le vrai compteur DSL = `TotalTurnsFinished`. → **le cap réel ≈ round 8 (≈ tes 8 tours/camp), PAS round 5-6**. TOOLING (H58 + horloge) : `rl_duel view` affiche désormais (1) **⏱ HORLOGE round-cap** STATIQUE dès le tour 1 + (2) la ligne **⏱ [ROUND-CAP]** (effet Incoming, RemainingTurns) à ~2 tours de la fin = alarme finale. DOCTRINE figée : sois en CLÔTURE cohésive pour ton **~6ᵉ tour** ; l'avance numérique ne sauve PAS du wipe. [RE ghidra, mesure live seed 80000]`
  `  ▸ Tac (7ᵉ confirmation self-play seed 80003 — POSITION GAGNANTE MAXIMALE non convertie) : cas le plus FORT à ce jour — team1 (A) était **8v2** ET avait tué **les DEUX engines adverses** ; team2 (B) à 2 unités avec ses summon-engines morts. **MALGRÉ une position structurellement gagnante (8v2 + engines ennemis détruits), le no-winner board-wide a fire** (warning armé au tour 11, « dans 2 tours ») → winner=None. ⚠ **DÉMONSTRATION DÉFINITIVE : ni l'avance numérique massive (8v2) NI la destruction des engines adverses ne sauvent du cap** — seule la CLÔTURE (réduire l'ennemi à 0 unité) compte. Cause proximale commune aux 2 sides = **tempo d'ouverture trop prudent** sur le grand gap row-0↔row-9 (« should have engaged harder T3/T5 » ; « it's a RACE »). [self-play consensus, seed 80003]`

---

## 4. Machines of War (MoW)

- **ultraDreadnought / Galatian (Ultramarines)** — `MacroPlasmaIncinerator` = **killzone DIFFÉRÉE, pas un hit immédiat** : pose des effets de tile, frappe à AoE Plasma (Pierce élevé) le **1ᵉʳ ennemi qui TERMINE son move dans la zone** → juger à la cascade, pas au moment du cast. ⚠️ **la danger overlay NE marque PAS cette killzone** : lire l'effet armé `MacroPlasmaIncinerator_AutoAttack` dans decisionView.effects et NE JAMAIS finir un move dedans (vécu : multi-k sur 2 carries). **Visée tactique** : cibler une unité avancée du camp MoW pose la zone DEVANT elle → l'adversaire qui avance pour l'attaquer y termine son move → AoE.
  `DutyEternal` (consomme le MoW) = **summon, 0 dmg offensif** : déploie le Dreadnought comme unité **« Galatian » (ultraSmnDreadnought)** — tank **move0 (tourelle stationnaire)**, BigTarget (non déplaçable) / Overwatch / Vehicle-Mechanical (repair-only, pas de heal). Passif `AncientFury` : les attaques normales splashent (mêlée → adjacents à la cible ET à Galatian ; ranged → adjacents à la cible ET à 2 hex de Galatian). ⚠️ **STRUCTUREL** : move0 → il ne « termine jamais un move » → la killzone MacroPlasma d'un MoW ennemi NE le déclenche JAMAIS, et DutyEternal n'inflige rien → **une MoW seule ne peut PAS endommager un Galatian stationnaire**. Kill-plan = une carry RANGED qui reste HORS de sa portée ; si cette carry meurt, le tank devient injouable pour un reliquat mêlée. (cf. gameconfig --ability MacroPlasmaIncinerator / DutyEternal / AncientFury)
- **blackForgefiend (Chaos)** — artillerie `HadesAutocannons` / `DaemonicOrdnance` **ranged, frappe N'IMPORTE OÙ** (peut tirer depuis off-battlefield = **inciblable**) ; pose Fire sur hex cible + zone. ⚠️ **CRIT RAMP cumulatif** : chaque usage de DaemonicOrdnance donne **+Crit Chance aux DEUX abilities** → burst capable de one-shot une carry (multi-hits crit en un tour). **Cap** : après 3+ crits dans SON tour, plus aucun crit le reste du combat. Le repli ne protège pas (frappe partout) → anticiper le ramp dès les 1ᵉʳˢ usages. (cf. gameconfig --ability DaemonicOrdnance / HadesAutocannons)
- **astraOrdnance « Thaddeus Noble » (Imperial)** — `BasiliskBarrage` (fire SEULEMENT s'il n'a pas bougé) : obus board-wide Blast (Pierce faible, HitsMultipleMembers). ⚠️ **SCATTER** : softener de ZONE, **PAS un sniper** — ne peut PAS fiablement finir une unité précise sur l'hex visé (vécu : visé une cible → cible à 0 dmg, le spread atterrit sur la grappe adjacente/derrière). Chaque **round écoulé** ramène +1 obus vers l'hex cible → plus fiable tard. Touchés gagnent **Suppressed/Pinned** (malus dmg/move, stop Overwatch ; heal/repair retire) — trait `SuppressiveFire` = zone-Suppress automatique sur tout touché.
  **Attaque normale** = Blast **range 3 single-target SANS bouger** = nuke single-target fiable depuis sa tuile (distinct du barrage qui scatter). → barrage pour le spread/déni de zone, attaque normale pour un kill single-target.
  ⚠️ **Move-gate (confirmé live seed 97000)** : sur un tour STATIONNAIRE, barrage+normale = ~one-shot d'une carry ; sur un tour où Thaddeus a BOUGÉ, output ≈ 1/4 (seule la normale single-hit reste) → **le forcer à se repositionner ≈ halve son dmg**. VALEUR RÉELLE = déni de zone + chip incident sur la grappe adjacente, PAS du gros dégât (Pierce faible vs armure). (cf. gameconfig --ability BasiliskBarrage)
  `▸ Tac: rôle=carry · menace=critical vs roster mêlée lent (artillery board-wide ~one-delete/tour, inatteignable derrière un mur) · counter=un dealer ranged/Psychic à soi pour le tuer T1-T2, OU le ZONER/forcer à bouger chaque tour (move-gate : barrage void s'il a bougé → ~1/4 dmg) ; contre un roster pure-mêlée = engine de loss structurelle (wiki §5) — vécu seed 97000 : un anchor a fini par le solo-kill mais trop tard (fragiles déjà delete) [n=1]`
- **tauBroadside « Tson'ji » (Tau)** — `HeavyRailRifle` = **RAILGUN** : cible un ennemi mais **part au DÉBUT du prochain tour du MoW** (Piercing élevé, **bonus vs Vehicles/BigTargets**). ⚠️ **MÉCANIQUE-CLÉ : dégâts réduits par hex que la cible a parcouru à SON dernier tour** (→ min 0) → sur une cible **mobile, le tir est gâché**. **RÈGLE : ne PAS l'armer sans LOCK.** Lock = un taunt/`BlockMovement` (cf. §1) posé le **MÊME tour** par un taunter **déjà adjacent** à la cible (Jaeger `HolyDuel`, Grot de Snotflogga) → cible bouge 0 hex → plein pot. À défaut : garder le tir, ou viser un **ranged déjà à portée de mes unités** (l'IA l'attaque sur place → bouge peu = quasi-lock comportemental, moins fiable). vs MoW : pas de dmg → +1 cd sur l'ability secondaire + le bonus sur la primaire.
  `TwinSmartMissileSystem` (prêt d'emblée) : Blast à **chaque ennemi DÉJÀ Markerlighté** + pose un Markerlight sur la cible → le **1ᵉʳ** tir ne fait **que marquer** (0 dmg si personne n'est encore marqué ; Blast low-pierce ≪ vs armure de toute façon). Vérifié duel seed 33182. (cf. gameconfig --ability HeavyRailRifle / TwinSmartMissileSystem)
- **orksRukkatrukk (Orks)** — `SquigLaunchas` (Ranged, Physical **Pierce1 = FULLY armor-piercing**) : ⚠️ **adjacency-gated** — ne cible un ennemi QUE s'il a **≥1 Ork allié OU ≥2 alliés adjacents** ; summon une Large Squig seulement si **≥2 Orks OU ≥4 alliés adjacents** à la cible (≈ injouable hors roster Ork ; un roster Chaos doit coller 2 unités à la cible pour tirer du tout). ⚠️ output faible vs un **TyrantGuard** N'EST PAS l'armure (Pierce1 = full pierce) mais **GuardianOrganism (−% + cap par hit)** empilé à **BigTarget (−1 hit ranged)** → ~70% de réduction → **pas un finisher vs un tank Guard-protégé**.
  `SquigMine` (trap) : marque tout hex LIBRE (seule contrainte moteur : hex inoccupé ; range gouverne les marques secondaires) — frappe quand un ennemi MARCHE sur un hex marqué. Marquer près des ennemis est tactique, PAS une contrainte moteur (un rejet sur hex libre = contrainte range/valid-tile, pas « doit être enemy-relevant »). (cf. gameconfig --ability SquigLaunchas / SquigMine)

---

## 5. Note de matchup (observé)

Imperium [Trajann/Vexilus/Morvenn/Mephiston/Yarrick + ultraDreadnought] vs Chaos
[Kharn/Corrodius/Abaddon/Macer/Pestillian + blackForgefiend], seed 777, rank 17 :
le côté **Imperium perd structurellement** (4/4 observés). Profil : briques sans heal
soutenu **vs** tanks Resilient / self-heal (Abaddon) / explose + artillerie MoW →
l'**attrition** favorise le Chaos quelle que soit l'exécution. Même la meilleure ligne
Imperium (outils+doctrine corrects : Kharn+Macer+Poxwalker retirés via stun/killzone/actifs)
finit avec Trajann (FinalJustice) puis Morvenn (Pestillian+MoW) qui tombent. → Pour
démontrer « oracle > IA gloutonne », prendre un **matchup équilibré**, pas celui-ci.

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
  **ENGINE (ENNEMI-À-ÉVITER, status=TRIGGERED-AGAINST-ME)** : un summoner back-row peut **focus-delete un de mes forwards sans bouger**
  via sa drone MV71, qui frappe au **Damage stat de Sho'syl, PAS au profil base du drone** (one-shot-class). ⚠ La reach/dmg du
  **drone-summon n'apparaît PAS dans le danger-zone overlay** (summoner blind spot, SKILL §4) → over-extension « invisible ». PLAY
  (à ÉVITER) : NE PAS avancer une unité (surtout un non-tank) dans la reach COMBINÉE summoner-drone (Sho'syl) + autre dealer back-row
  (Njal Psychic AoE) ; n'avancer qu'une durable Resilient (Aesoth) comme écran. SOURCE à couper = tuer Sho'syl → les drones deviennent
  chair inerte (dmg ~base du drone). Vécu seed 70058 : violé à 5v2 (non-décisif) → seule perte. (cf. §3bis Sho'syl MV71 ; gameconfig
  --ability MV71SniperDroneSquad) [n=1, 70058 triggered-against-me]
- `Bellator DeathFromAbove (flood Inceptors croissant) + Archimatos Incursion/Possession (Bloodletter-farm + body-par-kill) + Abaddon FirstAmongTraitors (aura dmg Chaos adjacent)` —
  **ENGINE (ENNEMI-À-ÉVITER, status=chained)** : DOUBLE summon-engine snowball — Bellator flood Inceptors croissants + Archimatos farme
  Bloodletters & spawn un body par kill, AMPLIFIÉ par l'aura adjacente d'Abaddon → board-flip 5v5→8v5 si laissé tourner. SOURCE = tuer
  Archimatos + Bellator EARLY (les deux SOFTS, no-Resilient) ; tuer Archimatos AVEC mon unité (lui = VICTIME) = ZÉRO Possession body
  (cf. §2 Archimatos). PLAY : un roster all-melee + Bellator move4-Flying + Deathleaper deep-strike est CONTRAINT de diver → HOLD cohésif
  T1-T2 pour baiter le dive, puis tuer les DEUX engines dès qu'ATTEIGNABLES sur leur avance. Vécu seed 70053 W : engines tués comme
  victimes/en réaction, source coupée avant compounding ; FirstAmongTraitors quasi-inert une fois Archimatos mort. (cf. §3bis Bellator,
  §2 Archimatos, §2 Abaddon ; gameconfig --ability DeathFromAbove|Incursion|FirstAmongTraitors) [n=1, 70053 chained]
- `Bellator DeathFromAbove (flood Inceptors croissant move4) + Corrodius Poxwalkers/Contagion (Resilient anvil + −armor aura screen) + Actus DefendTheDivineWork/GalvanicField (repair-cluster + free-attack par réparé)` —
  **ENGINE (ENNEMI-À-ÉVITER, status=chained)** : TRIPLE summon/sustain core — Bellator flood (la SOURCE), Corrodius ajoute Poxwalkers
  + aura Contagion −armure (screen lent Resilient), Actus répare le cluster + chaque réparé fait une free-attack → board COMPOUND si
  laissé tourner. SOURCE = tuer Bellator (le flood) + Actus (le repair) EARLY, les DEUX SOFTS no-Resilient ; Corrodius (anvil Resilient
  move2 LENT) = secondaire MAIS doit être COMMENCÉ tôt s'il y a un round cap (cf. §3bis Corrodius/H51). PLAY : Bellator move4-Flying +
  screen lent CONTRAINT de closer → HOLD cohésif + held-Overwatch turret (Certus) baite le dive → tuer les engines à leur sortie.
  ⚠ **VÉCU seed 70061 (status=chained PARTIEL → L timeout)** : Bellator tué T4 (flood stoppé) + Inceptors clearés, MAIS Actus seulement
  CHUNKÉ (jamais fini) + Corrodius jamais engagé → board dominant NON CONVERTI avant le round-cap = mutual-wipe no-winner. LEÇON : casser
  la SOURCE flashy (Bellator) ne suffit PAS — FINIR le repair-engine (Actus) + grind l'anvil (Corrodius) AVANT le cap, sinon les 2 engines
  secondaires survivent au timeout. (cf. §3bis Bellator, §1/§5bis Actus, §2 Corrodius ; gameconfig --ability GalvanicField|Contagion) [n=1, 70061 chained]
- `Ragnar WarHowl (pump +dmg/hit + Unstoppable + +crit) + ligne mêlée Character all-melee (Atlacoya/Tanksmasha/Kut…)` —
  **ENGINE (ENNEMI-À-ÉVITER, status=avoided)** : WarHowl est l'**amplificateur de burst d'un roster pur-mêlée** — un seul cast buffe
  toute la ligne Character mêlée jusqu'à la fin du tour. SOURCE = Ragnar → le tuer (ou le taunt/stun-lock, cf. H30 Azkor OverwhelmingWrath)
  AVANT son 1er cast laisse toute la ligne adverse un-buffée. PLAY : prioriser Ragnar comme la wincon (H02) ; un roster all-melee est
  CONTRAINT de diver → laisser mes réactions/Overwatch le tuer à sa sortie (le burst ne fire jamais). Vécu seed 70056 : Ragnar tué en
  réaction Overwatch AVANT WarHowl = ligne un-buffée = W. ⚠ **CONFIRM n+1 (seed 70059 W)** : Ragnar chunké puis tué T3 par FOCUS Psychic
  actif sur sa sortie AVANT tout cast ; ATTEIGNABLE car le bulk anvil-heavy était CONTRAINT de fermer la distance (sans reaction-engine,
  le bris s'est fait par focus actif au lieu de réactions auto). ⚠ **CONFIRM n+1 + NOUVELLE VOIE (seed 70057 W) — DÉFANG PAR LES
  BÉNÉFICIAIRES** : WarHowl ne pump QUE les melee Characters SANS normale ranged → 2ᵉ voie = tuer ses BÉNÉFICIAIRES (Dante+Helbrecht)
  AVANT l'engine ; au moment de tuer Ragnar, WarHowl ne pouvait plus que self-buff = engine défangé même non-pré-empté. PLAY = soit kill
  pre-cast, soit vider sa liste de bénéficiaires melee s'ils sont plus atteignables que lui. (cf. §3bis Ragnar WarHowl = self-cast, ne
  finit pas le tour ; gameconfig --ability WarHowl|FinalJustice) [n=3, 70056/70059/70057 avoided]
- `Kharn TheBetrayer (kill→auto move+multi-hit/tour + BlessingsOfKhorne) + Tarvakh carry autonome (kill-snowball BlessingsOfKhorne/TrophyTaker)` —
  **ENGINE (ENNEMI-À-ÉVITER, status=avoided)** : DOUBLE carry snowball WorldEaters — Kharn est l'engine-source (1 SEUL kill → TheBetrayer
  s'arme = auto move+Eviscerate au START de chaque tour SANS action + BlessingsOfKhorne cumulatif = carry incontrôlable) amplifié par
  Tarvakh qui snowball INDÉPENDAMMENT par kill (BlessingsOfKhorne, TrophyTaker +dmg vs ≤50% PV). SOURCE à casser = **nier à Kharn (et
  Tarvakh) leur PREMIER kill** ET les tuer sur leur dive AVANT que TheBetrayer s'arme. Les DEUX no-Resilient (Tarvakh NON-pumpé) →
  killables à une réaction massée SI on les atteint. PLAY : roster all-melee CONTRAINT de diver → tenir un mur de réaction (Overwatch-turret
  + held-OW + aura −dmg) qui les tue à leur sortie AVANT tout kill ; ne JAMAIS laisser une de mes unités tomber ≤50% près de Tarvakh
  (TrophyTaker). Vécu seed 70060 W : Kharn + Tarvakh tués TOUS LES DEUX dans mon mur de réaction T2 avec ZÉRO kill scoré → TheBetrayer
  jamais armé. (cf. §2 Kharn TheBetrayer/BlessingsOfKhorne kill-gated + §2 Tarvakh ; gameconfig --ability TheBetrayer|TrophyTaker --trait BlessingsOfKhorne) [n=1, 70060 avoided]
- `Abaddon FirstAmongTraitors (aura dmg aux alliés Chaos adjacents, scale par attaque) + alliés CHAOS sur SON équipe` —
  **ENGINE (ENNEMI-À-ÉVITER, status=avoided) — DEMOTE si le bénéficiaire Chaos manque** : l'aura ne vaut que par le NOMBRE d'alliés Chaos
  adjacents. SOURCE = compter les alliés Chaos au recon : si UN SEUL (ou zéro), l'aura est NEAR-INERTE → demoter Abaddon de wincon à anvil
  Resilient soft, le laisser pour la FIN. PLAY : vécu seed 70059 W — seul allié Chaos = Maladus → aura démotée au recon, Abaddon traité en
  DERNIER (4v1) ; une fois Maladus mort l'aura FULLY inerte → Abaddon overkillé sans urgence. Même classe « engine-inerte-sans-bénéficiaire »
  que le revive Chaos inerte (98004/70060) et l'amplificateur sans cible (Darkstrider markerlight 70056). (cf. §2 Abaddon aura Chaos-gated
  + faction des alliés ; gameconfig --ability FirstAmongTraitors) [n=1, 70059 avoided]
- `overkill raté → FinalJustice` (Helbrecht/Ragnar/Gulgortz/Trajann/Azrael…) — **ENNEMI-À-ÉVITER** :
  si tu ne tues pas en **OVERKILL**, la cible riposte une volée (≈ son attaque normale) → **overkill obligatoire** sur ces porteurs, sinon
  ne pas engager. ⚠ **VARIANTE SAFETY si l'overkill est impossible (vécu seed 70009 triggered-against-me)** : Gulgortz tué NON-overkill →
  FJ + LightImUp ont fire, MAIS routés sur le seul adjacent = un TANK high-HP (Tanksmasha, survécu) = riposte absorbée SANS perte. Si tu ne
  peux pas overkiller un FJ-carrier, finir avec UNIQUEMENT un corps high-HP adjacent (jamais un fragile) ; un chunk de plus pour amener
  <2× PV restants reste préférable (déni FJ complet). ✅ **VOLET POSITIF (vécu seed 70008)** : quand c'est MON FJ-carrier qui meurt adjacent
  à un ennemi bas-PV, le trade joue EN MA FAVEUR — mon Gulgortz tué NON-overkill → FJ a fire une normale et a TUÉ le Godswyl bas-PV adjacent
  = trade 1-pour-1 GRATUIT → positionner un FJ-carrier près d'une cible chunkée avant qu'il meure. ⚠ **CONFIRM n+1 — 3 VOIES VALIDÉES LE
  MÊME MATCH (seed 70057 W, 4 FJ-carriers gérés)** : (a) **Overkill** — Helbrecht overkillé multi-source (`Attack_WasOverkill=1`) → FJ NON
  déclenchée (i2 « unless Overkilled ») ; (b) **kill SANS eligible adjacent** — Dante tué sans cible à portée de sa normale → FJ a fire
  (`IsActingBeforeDeath=0`) mais ZÉRO dmg (no-op) = free-kill path distinct de l'Overkill ; (c) **route faible-pen sur un body armuré** —
  Ragnar tué non-overkill → FJ Chain Pierce20 sur mon Mataneo armuré Mechanical = trivial. DOCTRINE = pour chaque FJ-carrier choisir UNE
  des 3 voies : overkiller (riposte forte type Dante Pierce80/Gulgortz double-volée), tuer hors-portée-de-sa-normale, ou router la riposte
  faible-pen sur un tank/body armuré. (cf. gameconfig --ability FinalJustice) [n≥6, 93000/97002/70009/70008/70057/…]
- `repair Actus → GalvanicField` — **ENNEMI-À-ÉVITER / ENGINE** : chaque repair d'Actus déclenche une **free-attack** de l'unité réparée
  → **tuer Actus** coupe repair + free-attacks (et il re-heal self+adjacents). ⚠ NOTE : DefendTheDivineWork répare ANY allié adjacent (PAS
  Mechanical-gated) → l'engine est LIVE dès qu'Actus a des alliés adjacents, même s'il est le SEUL Mechanical de son équipe (≠ aura
  d'amplification inerte-sans-bénéficiaire). ⚠ **n+1 (vécu seed 70061, status=MISSED → CONTRIBUTING ROOT CAUSE)** : après avoir tué le
  summoner Bellator j'ai seulement CHUNKÉ Actus et HOLD au lieu de le FINIR depuis le shallow → il a survécu jusqu'au round-cap timeout =
  engine intact à la fin. « Kill ce tour ou ne pas committer » est LITTÉRAL pour un repair-engine ; une fois la SOURCE flashy (summoner)
  morte, le repair-engine DEVIENT le focus #1 — ne pas le chiper-et-tenir. (cf. gameconfig --ability GalvanicField|DefendTheDivineWork) [n=3, 97002/…/70061 missed]
- `TwistedScience (Hollan) → pump carry/summon` — **ENNEMI-À-ÉVITER / ENGINE** : tout allié healé par Hollan (autre que lui-même),
  **summons INCLUS**, gagne +maxHP permanent (scale rareté) +dmg si GSC, 1×/unité jusqu'à défaite → transforme un carry/summon en mur
  (vécu : Tarvakh ~30% maxHP en plus seed 97001 ; Xybia + l'Aberrant ressuscité pumpés seed 98001 — **un Hollan qui heal un summon sur
  revive le pompe aussi**). Aucune contrainte d'adjacence sur le PASSIF. → **focaliser le PUMPER (Hollan) pas l'output pumpé** ; le tuer
  TÔT et PERMANENT (avant qu'il soigne quiconque) ; une fois Hollan mort, rien n'est re-pumpé et les corps gonflés meurent normalement
  (vécu seed 98001 W). (cf. gameconfig --ability TwistedScience) [n=2, 97001/98001]
- `Abraxas MasterOfTheTutelaries (Pink Horror + Screamer-cascade-on-Psychic) + chip non-létal / AI ranged focus` —
  **ENNEMI-À-ÉVITER / ENGINE** : un summon-engine Abraxas **chippé non-létalement** (aucun seuil de PV → tout Abraxas survivant cast)
  déclenche MasterOfTheTutelaries → +1 Pink Horror + 1 Screamer par event Psychic-Damage ennemi = **board-flip +N bodies en un tour
  ennemi**, transformant un 5v5 en 3v10 pendant que le cluster ranged focus-kill les fragiles exposés. ⚠ **RÈGLE KILL-OU-HOLD (vécu seed
  70052 triggered-against-me)** : un chip à une seule source qui ne peut pas one-shot la cible est **strictement pire que le hold** — soit
  un **kill GARANTI ce tour** (multi-source depuis tuiles shallow, marge > HP), soit **HOLD total** pour dénier le trigger. JAMAIS un poke
  non-létal sur un summon-engine. ✅ **CONTRE-EXEMPLE POSITIF (vécu seed 70060 W, status=avoided)** : règle kill-not-chip RESPECTÉE → un
  kill GARANTI multi-source en UN tour (min-total vérifié > HP AVANT de committer) a erasé Abraxas AVANT son cast = ZÉRO board-flip, ZÉRO
  summon. Confirme l'INVERSE de 70052 : kill garanti ce tour OU hold total — jamais le poke. (cf. §2 Abraxas, no HP threshold ; gameconfig
  --ability MasterOfTheTutelaries) [n=2, 70052 triggered-against-me / 70060 avoided]
- `Re'vas EarlyWarningOverride (2 Shield Drones + Overwatch armé) + BigTarget screen ranged` — **ENNEMI-À-ÉVITER / ANTI** :
  Re'vas caste EWO T1 → spawne un **écran forward de 2 Shield Drones** (BigTarget −hit ranged, SaviorProtocols) + **arme un Overwatch
  turret** (re-arme sur chaque kill OW) → interdit une approche melee ET **ÉCRANE le soft backline (Eldryon/Abraxas) de mon reach**. PLAY :
  ne JAMAIS pather dans son arc r2 (no OW trigger) ; mais le screen rend les engines back-row inatteignables pour un roster melee → si je
  n'ai pas de reach tool (r3+/deep-strike/flyer) pour contourner le screen, **flagger la loss structurelle de reach au recon** (vécu seed
  70052 : screen tenu, engines softs jamais atteints = composante de la loss). (cf. §3bis Re'vas EWO ; gameconfig --ability EarlyWarningOverride) [n=1, 70052 avoided]
- `buff-engine → ranged dealers` (Calgar `RitesOfBattle` / Trajann `LegendaryCommander` /
  **Helbrecht `CrusadeOfWrath` + Aesoth `StandVigil` + Vitruvius `MasterAnnihilator` = TRIPLE amplificateur empilé**) — **ENNEMI-À-ÉVITER /
  ENGINE** : le(s) buff(s) feed les dealers (team +dmg/+pierce + armure + +1 hit vs marqué → gros focus/tour, kite + focus-kill 1/tour) →
  **tuer les engines de buff** AVANT d'échanger avec les dealers ; casser Helbrecht+Aesoth+Vitruvius effondre l'amplification (vécu seed
  98004 : les 3 cassés T2-T3 en réactions → focus ranged neutralisé). ⚠ **CONFIRM n+1 (seed 70057 W)** : buff-stack mixte Helbrecht
  `CrusadeOfWrath` (melee, live source) + Thaddeus `SpotterReworked` (+dmg ranged aux alliés proches) feeding la ligne de focus → Helbrecht
  (le buff-engine melee) tué T4 par OVERKILL multi-source AVANT d'amplifier une swing mêlée ; Thaddeus tué EN DERNIER (no FJ/no Resilient =
  clean) une fois ses alliés ranged morts → son Spotter n'avait plus personne à feeder = inert. PLAY = casser le buff-engine LIVE en premier
  (Helbrecht, soft, overkill pour nier FJ), garder le buff sans-bénéficiaire (Thaddeus Spotter) pour la fin. (cf. §3bis ; gameconfig
  --ability CrusadeOfWrath|StandVigil|MasterAnnihilator|SpotterReworked) [n≥4, 96002/97000/98004/70057]
- `Vitruvius MasterAnnihilator (mark +1 hit team vs marqué) + RadBombardment (ligne AoE croissante) + team focus` —
  **ENNEMI-À-ÉVITER / ENGINE** : la mark donne à toute la team +1 hit vs la cible marquée (sauf Psychic) ET RadBombardment est une ligne
  AoE Toxic qui GRANDIT +1 hex/round écoulé +1/heal Mechanic (et friendly-fire sa propre ligne) → un dealer ranged-AoE qui atteint le
  mid-board vite ET amplifie le focus de toute l'équipe. ⚠ **RÈGLE FINISH-PAS-CHIP (vécu seed 70003 triggered-against-me)** : Vitruvius
  est SOFT (pas Resilient) mais un CHIP non-létal le laisse fully amplifier — chippé par le barrage T1, il a fire RadBombardment et tué
  mon carry au tour suivant. → contre ce buff/repair-engine, prévoir un FINISH au range (pas un poke) AVANT qu'il close ; le tuer effondre
  la mark + la ligne. (cf. §3bis Vitruvius RadBombardment ligne croissante ; gameconfig --ability MasterAnnihilator|RadBombardment) [n=1, 70003 triggered-against-me]
- `Ambush + decoy ami survivant → resurrect full` (Kelermorph/Judh, Magus, Biophagus…) — **ENNEMI-À-ÉVITER** :
  **1ʳᵉ mort SEULEMENT** → respawn plein PV au début du tour suivant si un decoy ami survit → **clear le decoy** OU forcer une **2ᵉ mort**
  (first-defeat-only, jamais 2×, indépendant de l'overkill). ⚠ NE PAS traiter le 1er kill d'une unité Ambush comme un retrait : budgétiser
  la 2ᵉ mort d'avance. Vécu seed 98001 : Xybia ET Hollan ont eu chacun un revive gratuit (decoys inaccessibles) → gagné quand même via 2ᵉ
  morts, mais clear-decoys aurait économisé 2 tours de cleanup — pré-planifier une unité pour piétiner les decoys (Steppable) quand une
  unité Ambush meurt près de ma ligne. ⚠ **n+1 (vécu seed 70061, triggered-against-me)** : Judh tuée une fois T3 (Certus OW) mais decoys
  survivants → revived FULL le tour suivant ; sur la 2ᵉ tentative j'ai single-sourcé son re-kill et seulement FLOORED (= 50% sur le TOUR
  ENNEMI, scope i2 confirmé) → sa contre + le tour ennemi ont tué mon re-killer. LEÇON re-confirmée : un 1er kill d'unité Ambush n'est PAS
  un retrait — budgétiser la 2ᵉ mort (PERMANENTE) d'avance ; pour une Ambush floored, stacker un 2ᵉ attaquant > HP-floored le MÊME tour, OU
  clear le decoy avant, OU ignorer et presser les engines. (cf. §1 Ambush ; gameconfig --trait Ambush) [n≥4, …/98001/70061]
- `Aleph-Null (necroSpyder repair-hub) + Tan Gi'da (admecMarshall summon-engine) → noyau Mechanical` —
  **ENNEMI-À-ÉVITER / ENGINE** : Aleph-Null répare/regen la grappe Mechanical (FabricatorClawArray + Mechanic + LivingMetal/NetherRealmCasket)
  pendant que Tan Gi'da la blinde (+Protector) et summon des Skitarii Vanguards (cap5) après chaque attaque → noyau **auto-réparant, blindé,
  croissant** qui out-attritionne un roster low-output (snowball ~5 héros → 12 unités en 2 tours, seed 98003). → **tuer les SOURCES** (Tan
  Gi'da + Aleph-Null) TÔT au **Psychic NoBlocking** (bypasse le Protector, cf. §1), ne PAS chiper l'output Vanguard/Snotflogga ; si les
  engines sont structurellement INATTEIGNABLES (row 8-9, reach=zéro), flagger la loss au recon. (cf. gameconfig --ability FabricatorClawArray
  --trait Protector|LivingMetal) [n=1, 98003 missed]
- `summon-engine miroir : Tan Gi'da (ControlEdict) + Yarrick(s) (SendInTheNextWave) + Aleph-Null (ScarabHive)` —
  **ENNEMI-À-ÉVITER / ENGINE** : trois moteurs de summon INDÉPENDANTS (Vanguards 1/attaque cap5 sous Protector + Guardsmen +1/allié-défait
  cap5 — clause snowball qui récompense MES pertes — + Scarabs/use) peuvent flooder 5→12+ unités en 2 tours ; **deux Yarricks DOUBLENT** le
  throughput SendInTheNextWave. Un roster low-output qui ne peut pas burst-down Yarrick avant son actif déclenche le snowball via ses propres
  morts. → couper les sources, ne pas clear le chaff un par un. (cf. gameconfig --ability ControlEdict|SendInTheNextWave|ScarabHive) [n=1, 98003]
- `Anuphet ResurrectionOrb (necroOverlord summoner) + Aleph-Null FabricatorClaw/Mechanic repair (necroSpyder)` —
  **ENNEMI-À-ÉVITER / ENGINE** : noyau Necron sustain-snowball — Anuphet summon un Necron Warrior **chaque round** (+1 par LivingMetal mort,
  clause qui récompense MES kills), Aleph-Null les garde top/réparés (repair + LivingMetal regen) → le board flood de corps tanky réparés
  inout-attritionnables pour un roster non-burst. → **briser la SOURCE** : tuer Aleph-Null (amplificateur de repair) + Anuphet (summoner)
  TÔT plutôt qu'out-DPS l'output réparé. Les DEUX sont SOFTS (no-Resilient) et move-in → killables en réaction s'ils dive (vécu seed 98002 W :
  Aleph-Null tué T2, Anuphet chunké puis fini en réaction → le snowball n'a JAMAIS tourné). (cf. gameconfig --ability ResurrectionOrb|FabricatorClawArray) [n=1, 98002 avoided]
- `Patermine CosmicHorror (kill→decoy) + MightFromBelow (summon sur decoys)` — **ENNEMI-À-ÉVITER / ENGINE** :
  moteur de summon self-feeding ENTIÈREMENT KILL-GATED — chaque kill du Patermine pose un decoy (passif CosmicHorror) puis MightFromBelow
  (Psychic Pierce100 NoBlocking, ignore armure) summon un **Purestrain Genestealer** (Ambush+Infiltrate) sur chaque decoy adjacent → un kill
  via MightFromBelow chaîne IMMÉDIATEMENT en un Genestealer sur l'hex du mort. Gaté UNIQUEMENT sur le Patermine OBTENANT des kills (pas de
  kill = pas de decoy = pas de summon). → **DÉNI POSITIONNEL** : ne présenter AUCUN fragile killable dans son move4 reach (le contre n'est
  PAS réactif). Le Patermine porte Terrifying → bypass = RANGED, le tuer au range AVANT son 1er kill ; une fois qu'il a tué une fois, le
  snowball est live et un set de survivants mêlée ne le rattrape pas. Vécu seed 70003 : a tué Nicodemus T1 → Genestealer summon = snowball
  live → 3v6. (cf. §3bis Patermine ; gameconfig --ability CosmicHorror|MightFromBelow) [n=1, 70003 triggered-against-me]
- `Isaak CultDemagogue (board-flip r2) + Neophyte/Isaak Ambush` — **ENNEMI-À-ÉVITER / ENGINE (board-flip instantané)** :
  UN cast de CultDemagogue au tour ennemi éparpille jusqu'à 8 decoys ≤2 hex de la cible, convertit la MOITIÉ en Neophyte Hybrids (ranged r2,
  CHACUN Ambush) qui prennent un tour IMMÉDIAT + tirent sur ma ligne → board-flip 4v5 → 3v12 en une activation. Les decoys restants
  (Steppable HP0) alimentent aussi DecoysAndMisdirection (resurrect/move-on-decoy +dmg pour les unités GSC). → **tuer Isaak AVANT le cast**
  (T2 au plus tard) ; s'il est INATTEIGNABLE (row-7/9, mon roster move2/r3 + r2 sans reach r3+/deep-strike) = reach-fail STRUCTUREL →
  flagger la loss et jouer un turret défensif (fragiles row 0-1), PAS avancer des fragiles dans le reach Custodes/GSC. ⚠ **status=triggered-against-me**
  (vécu seed 70007 L) : Isaak row-7 jamais menacé (j'ai dépensé mon unique vrai tour sur le LESSER engine Yarrick + heal) → CultDemagogue a
  fire = la loss directe. ⚠ leçon « tuer l'engine qui ENABLE l'écran, pas le plus facile » (cf. 91012). (cf. §3bis Isaak + §1 Ambush ;
  gameconfig --ability CultDemagogue|DecoysAndMisdirection) [n=2, 91012/70007 triggered-against-me]
- `Isaak CultDemagogue (board-flip r2) + Shadowsun (move4 Flying + ExemplarOfTheKauyon teleport) + Typhus anvil EN ÉCRAN` —
  **ENNEMI-À-ÉVITER / ENGINE (board-flip + Flying-teleport-reach derrière un anvil)** : Isaak flippe le board (Neophytes + decoys prenant un
  tour IMMÉDIAT) PENDANT que Shadowsun Flying-teleporte au-delà de TOUT écran (reach pleine-planche, aucun cap de move) pour delete mon outil
  fragile de reach, le tout derrière un anvil Typhus (Resilient+TerminatorArmour) qui écrane les soft engines. → **HOLD les fragiles row 0-1,
  écraner avec des corps de summon UNIQUEMENT, NE JAMAIS avancer un fragile reach-tool** ; forcer l'IA à venir sur un cluster cohésif.
  ⚠ **status=triggered-against-me** (vécu seed 70050 L) : les deux engines étaient INATTEIGNABLES (Isaak/Isabella row 8-9 ; mon Neurothrope
  move2+r3 = reach ~5 depuis row 1, PAS row 9), pourtant j'ai avancé Neurothrope sur un verdict move-guard « propre » → Shadowsun teleport-kill
  + Isaak board-flip + Typhus + Judh en UN tour ennemi → 4v14, sustain-engine intact, AUCUNE reach restante = loss structurelle. ⚠ leçon : vs
  un profil board-flip + Flying-teleport, un verdict move-guard 2-ply « propre » est un faux feu vert (cf. H40) — tenir les fragiles row 0-1
  par DÉFAUT. (cf. §3bis Isaak + Shadowsun ExemplarOfTheKauyon teleport + Typhus anvil ; gameconfig --ability CultDemagogue|ExemplarOfTheKauyon) [n=1, 70050 triggered-against-me]
- `Isabella RitesOfRestoration (revive/heal engine) + Isaak Ambush + Judh Ambush + Neophyte Ambush` —
  **ENNEMI-À-ÉVITER / ENGINE (sustain/revive EMPILÉ sur multi-Ambush)** : un engine de sustain+revive (Isabella, soft no-Resilient/no-FJ →
  tout K! la tue proprement) superposé à PLUSIEURS porteurs d'Ambush (Isaak/Judh + chaque Neophyte) → mes kills sont soit ANNULÉS (revive
  Isabella) soit TEMPORAIRES (decoy Ambush). → **wincon = tuer Isabella tôt ET Isaak avant cast** ; une fois les deux online + le board
  flippé, mes kills sont réversibles et je n'ai plus de reach. ⚠ **status=missed** (vécu seed 70050 L) : jamais atteint la fenêtre —
  Isabella/Isaak row 8-9 inatteignables à mon roster melee/r2 + 1 move2/r3 → flagger la loss au recon quand reach=zéro vers ces engines.
  (cf. §3bis Isabella RitesOfRestoration revive fixe + §1 Ambush first-defeat-only ; gameconfig --ability RitesOfRestoration) [n=1, 70050 missed]
- `Trajann LegendaryCommander (+dmg vs adjacent-à-un-ability-user) + Aesoth StandVigil/VexillaMagnifica stun + Trajann MomentShackle self-heal + DOUBLE summon-engine (Isaak+Yarrick) en ÉCRAN` —
  **ENNEMI-À-ÉVITER / ENGINE (anvil Custodes screené par summons)** : triple-stack Custodes — Trajann amplifie le focus de l'équipe ET se
  heal-to-full REPEATABLE sur cd (mur inkillable, cf. l'entrée Trajann ci-dessous) pendant qu'Aesoth stun (VexillaMagnifica) et buffe
  (StandVigil) → un mur self-sustaining qui out-grind un roster chip une fois les ÉCRANS (Isaak board-flip + Yarrick attrition) construits.
  → NE PAS chiper Trajann (chip annulé) ; casser les ÉCRANS (les summon-engines) en premier — c'est la seule manière de toucher l'anvil.
  ⚠ **status=avoided mais MOOT** (vécu seed 70007 L) : correctement NE PAS chipé Trajann, MAIS échoué à casser l'écran (Isaak engine) →
  l'évitement n'a servi à rien, le board a flippé avant toute fenêtre de kill sur l'anvil. ✅ **CONTRE-EXEMPLE — mur CASSÉ (vécu seed 70005,
  sans summon-engine en écran)** : ce matchup le wall Trajann+StandVigil n'avait PAS de double summon-engine devant lui → la fenêtre était
  atteignable : Aesoth (la SOURCE StandVigil) tué d'abord (par l'Explosion friendly-fire de mon Aleph-Null mourant) = DEPUMP l'équipe, PUIS
  Trajann tué en un tour via la séquence anti-block Typhus Psychic + Ulf GreatFrostAxe (cf. Miennes ci-dessous) pendant MomentShackle en cd.
  LEÇON : casser Aesoth retire StandVigil (depump) ; le wall n'est inkillable que TANT QUE ses écrans (summon-engines) tiennent ET que
  MomentShackle est up — sans écran summon et avec un burst Psychic+actif réservé, il TOMBE. (cf. §3bis Trajann MomentShackle/LegendaryCommander
  + §3bis Aesoth VexillaMagnifica/StandVigil ; gameconfig --ability MomentShackle|LegendaryCommander|StandVigil) [n=2, 70007 avoided / 70005 broken]
- `Tigurius StormOfWrath (Psychic NoBlocking AoE 6-cibles) + WeaverOfFate (Thaumachus/Neurothrope) + Neuroparasite (Neurothrope)` —
  **ENNEMI-À-ÉVITER / ENGINE (cascade Psychic)** : UN cast de Tigurius (Psychic Pierce100 NoBlocking, cible + 5 adjacents = 6 unités) touche
  3+ de mes units → **arme `WeaverOfFate`** (Thaumachus/Neurothrope dealent MAX ce tour) ET escalade **`Neuroparasite`** (+dmg/niveau, cap)
  sur chaque cible touchée → cascade qui snowballe inkillable. Le Psychic NoBlocking ignore TOUTE ma mitigation (armure, BigTarget,
  GuardianOrganism). → **casser la SOURCE** : tuer **Tigurius EN PREMIER** (l'AoE qui touche 3+ ET la block-aura PsychicFortress qui mange
  mes finishers) PUIS **Neurothrope** (le snowball-engine) AVANT qu'ils tournent ; ne PAS clusterer 3+ de mes units exposées à StormOfWrath ;
  mon dmg étant idéalement NON-Psychic ne feed PAS leur WeaverOfFate/Neuroparasite (anti-synergie défensive). ⚠ **status=MISSED** (vécu seed
  70000 L) : j'ai split mon focus Thaumachus/Tigurius au lieu de FULL-focus Tigurius → PsychicFortress a bloqué mes finishers, Tigurius a
  survécu et re-fire → la cascade a tourné ; Neurothrope backline jamais atteint. ⚠⚠ si le roster est melee/r2 sans reach au Neurothrope
  backline (move2/Flying/r3) = HARD-COUNTER structurel, flagger la loss au recon. (cf. §3bis Tigurius StormOfWrath + PsychicFortress block-aura
  + §3bis Neurothrope Neuroparasite ; gameconfig --ability StormOfWrath|Neuroparasite --trait WeaverOfFate) [n=1, 70000 missed]
- `Psyker splash (attaque RANGED normale → +dmg à un ennemi ADJACENT à la cible) → seuil 3+ ennemis-Psychic → WeaverOfFate MAX (Ahriman + Thaumachus)` —
  **ENNEMI-À-ÉVITER / ENGINE (cascade Psychic SANS AoE actif)** : distinct du feed-par-AoE (StormOfWrath ci-dessus). Une **simple attaque
  ranged NORMALE** d'un Psyker (Ahriman/Thaumachus) splash %dmg sur un ennemi adjacent à la cible → contre un cluster ennemi, UNE normale
  touche 2-3 ennemis distincts en Psychic, **arme `WeaverOfFate` sur les DEUX Psykers** (RemainingTurns=1) → ils dealent MAX ce tour →
  **one-shot** (vécu : Jain Zar one-shotée le tour où le splash a touché 2 Guardsmen adjacents → 3 ennemis-Psychic → max). → **NE PAS
  clusterer 3+ de mes units dans la portée Psychic** : garder les unités SPREAD nie le seuil et empêche les jumeaux WeaverOfFate de monter
  à MAX (les deux observateurs concordent : le caster déclenche cheaply via splash, le défenseur dénie via spacing). (cf. gameconfig --trait
  WeaverOfFate « 3+ enemy units have taken Psychic Damage → maximum Damage » + trait Psyker splash ranged normale) [self-play consensus, seed 80003]
  `▸ MIEN-À-EXÉCUTER (côté OFFENSIF — le splash-feed est un ENGINE de victoire, pas qu'un piège défensif, [self-play consensus, seed 80003 — team2 W]) :`
  avec 2-3 Psykers, **spam la normale RANGED** (pas seulement les abilities) pour feed le seuil — vécu seed 80003 : team2 a spammé la normale
  Psyker (ab 69) pour atteindre/maintenir 3+ ennemis-Psychic/tour → `WeaverOfFate` MAX armé → kills garantis (one-shot Jain Zar, focus du
  Deathleaper isolé), **élimination en 4 tours** (clôture AVANT le round-cap). Le Psyker NoBlocking bypasse armure (MkXGravis = ZÉRO
  protection) ET `Terrifying`/Camouflage (réductions MÊLÉE only). ⚠ Garder les casters à **range 2** : une normale adjacente (range 1)
  auto-sélectionne l'arme MÊLÉE faible (Flame), pas le Psychic ranged (gaspille le tour). Coupler avec `Possession`-class (Archimatos) :
  un RANGED-kill spawn un corps gratuit dans le hex de la victime = board-presence pour la race.
- `Njal Stormcaller (Psychic NoBlocking AoE Ice) + mes carries FLYING stationnaires` — **ENNEMI-À-ÉVITER** :
  Stormcaller = Psychic Pierce100 NoBlocking (ignore armure ET TerminatorArmour) AoE sur hex-cible + tous adjacents, **stun les unités
  FLYING touchées** ET +dmg/hex d'Ice adjacent (`LordOfTempests` snowball). → NE PAS laisser un carry Flying (mon Dante) stationnaire dans
  la portée Ice de Njal (risque stun + dmg armor-ignore sur toute la grappe). Couper la source = tuer Njal (move2 lent → kitable/out-rangeable
  par des r3, ou focus multi-attaquant qui bat son TerminatorArmour, cf. §1). (cf. §3bis Njal ; gameconfig --ability Stormcaller --trait LordOfTempests) [n=1, 70001 avoided]
- `Trajann MomentShackle (self-heal REPEATABLE) + Resilient + MartialKatah (−% normales)` —
  **ENNEMI-À-ÉVITER / ENGINE (mur self-healing)** : MomentShackle est un actif STANDARD sur cd (~2 tours), PAS once-per-battle → Trajann se
  heal-to-full tous les ~2 tours pendant que Resilient absorbe tout spike sub-Overkill ET que MartialKatah réduit mes normales ET qu'il
  tape régulièrement. Pour un roster **chip-only** c'est un mur INKILLABLE qui se répare plus vite que mon dmg ET out-damage mon tank → il
  devient la **wincon late de facto** une fois les screens (Angrax/Tigurius) tombés. → fenêtre de kill = un **overkill MULTI-SOURCE en UN
  tour** pendant que MomentShackle est en cd, OU un **Direct/Psychic** qui bypasse son block (DoomSiren Pierce100). ⚠ **RÈGLE
  RECON-RÉSERVE-LE-BURST (vécu seed 70004 triggered-against-me)** : au recon, si l'adverse aligne un Trajann (ou tout anvil Resilient+self-heal)
  et que mon roster est burst-léger, **RÉSERVER mon burst anti-block (Direct/Psychic) POUR LUI** ; le dépenser tôt = chip-only vs l'anvil =
  loss structurelle (j'ai gagné la guerre des engines/dive 4v1 mais DoomSiren déjà spent → jamais pu finir Trajann). Même classe que le
  repair-engine 97002 (« kill CE tour ou ne pas committer ») porté à un Resilient+self-heal. (cf. §3bis Trajann MomentShackle REPEATABLE +
  Resilient + MartialKatah ; gameconfig --ability MomentShackle --trait Resilient|MartialKatah) [n=1, 70004 triggered-against-me]

### Miennes — à ENCHAÎNER (ordre imposé)
- `Ahriman Doombolt (Psychic AoE 3+ cibles) → WeaverOfFate (Ahriman ET Toth) → Toth HellfyreMissileRack (MAX, hit tous les Psychic-marked)` —
  **MIEN-À-ENCHAÎNER (one-turn multi-kill Psychic-burst, ORDRE imposé)** : l'INSIGHT non-déductible = **UN seul `Doombolt`** (3 hits répartis ≤2 hex)
  touche 3+ ennemis distincts en Psychic → dépasse le seuil `WeaverOfFate` qui s'arme sur **CHAQUE Psyker allié le possédant — Ahriman ET Toth, pas
  que le caster** (cascade Effect_Refresh sur les deux). PUIS `HellfyreMissileRack` (Toth, profil HeavyRound, **PAS Psychic**) au MAX frappe la cible
  primaire PLUS **chaque ennemi ayant subi du Psychic CE tour** → un cast = multi-kill (vécu seed 80004 : one-shot 2 Cadian Guardsmen + double-tap
  Forcas en UNE activation). SÉQUENCE imposée : Doombolt D'ABORD (arme Weaver + tag les cibles Psychic) → Hellfyre APRÈS (consomme les tags au MAX).
  ⚠ Hellfyre a un cooldown multi-tour (indispo ~2 tours) → fenêtre unique, ne pas la gâcher sur peu de cibles taggées. ⚠ ne PAS marcher Ahriman dans
  un Overwatch armé pour atteindre la portée Doombolt (vécu : enabler perdu) — armer depuis une tuile hors-arc OW. (cf. gameconfig --ability Doombolt|HellfyreMissileRack --trait WeaverOfFate) [self-play consensus, seed 80004]
- `Volk FrenziedFiring (AoE r3) + grappe ennemie dive (summon-engine adjacent à un anvil/chaff)` — **MIEN-À-ENCHAÎNER
  (cluster-softener 3-target)** : frappe la primaire + TOUS les adjacents à elle, +dmg par hex libre, et les bonus
  FleshmetalGuns frappent CHAQUE ennemi touché. PLAY : quand l'IA dive un soft summon-engine dans une grappe serrée, viser
  l'engine **depuis la tuile courante** (garder HeavyWeapon = +dmg si Volk n'a pas bougé) → l'engine chunké pour le kill,
  les threats adjacents eatent le splash, et le leftover-hit kill le chaff adjacent gratis. Un cast = casse l'engine + chip
  le mur + nie le snowball simultanément. (cf. gameconfig --ability FrenziedFiring) [n=1, 70006 chained]
- `Typhus PlagueWind (3-target Psychic AoE Pierce100 NoBlocking) + grappe ennemie diving into a tight cluster` —
  **MIEN-À-ENCHAÎNER (anti-mur-TermArmour, 3-target full-bypass)** : un cast frappe primaire + adjacent + further-adjacent, chaque
  hit Psychic Pierce100 passe à PLEIN à travers TOUT TerminatorArmour/Resilient/armure (exclusion Psychic par-hit, cf. §1
  TerminatorArmour). PLAY : quand le bulk all-melee ennemi s'est BUNCHÉ en fermant la distance, caster sur la grappe → softène 2-3
  anvils TermArmour simultanément à pleine valeur, enable les multi-kills du tour suivant. OUTIL de bris d'un mur de 2-3 anvils
  TermArmour groupés (là où une mêlée Pierce-only tombe à peu/coup). (cf. gameconfig --ability PlagueWind ; §1 TerminatorArmour)
  [n=1, 70059 chained]
- `Kharn FinalJustice/TheBetrayer death-riposte + Kharn mourant ADJACENT à un anvil chunké` —
  **MIEN-À-ENCHAÎNER (extraction de valeur sur la mort)** : à la mort de Kharn (sauf Overkill), FJ tire une normale → TheBetrayer
  chaîne une 2ᵉ attaque 4× Eviscerate, les deux déchargeant sur l'adjacent. PLAY : si Kharn DOIT mourir au front, l'orienter
  adjacent à un anvil ENNEMI chunké → sa death-riposte extrait un gros burst qui setup un 1-shot du tour suivant. ⚠ C'est le VOLET
  POSITIF d'un over-extension subi (cf. H03) : préférer NE PAS sacrifier Kharn (mon meilleur carry) du tout, mais s'il tombe
  forward, orienter sa mort vers un anvil chunké plutôt que le vide. (cf. gameconfig --ability KillMaimBurn|FinalJustice)
  [n=1, 70059 chained]
- `Certus held-Overwatch turret (r3, gate NOT-attacked) + cluster cohésif Resilient (Nauseous Healer + Gibbas KustomForceField armor-aura) baitant le dive` —
  **MIEN-À-ENCHAÎNER (reaction-engine, demi-réciproque H03)** : un ennemi tout-soft/move-in est CONTRAINT de closer dans le cluster
  Resilient tenu → il dive dans l'arc de Certus held-Overwatch → chaque mover qui entre en portée r3 se prend une riposte SÉPARÉE
  (aucun cap once-per-turn, cf. §3bis Certus + §1 Overwatch). PLAY : HOLD Certus (ne pas attaquer = OW armé) DERRIÈRE le cluster
  armor-buffé → les soft carries qui dive se font reaction-kill GRATIS sans dépenser d'action offensive. Pattern H03-réciproque
  (cf. 96002/98002/70056). ⚠ MAIS le HOLD doit FINIR une fois les engines morts (cf. H51) : over-hold après que le reaction-engine
  ait gagné la guerre des engines → round-cap timeout. (cf. gameconfig --ability Certus-Overwatch ; §1 Overwatch) [n=1, 70061 avoided]
- `Azkor OverwhelmingWrath (Taunt-lock) + AoE retardée + grappe cohésive` — **MIEN-À-ENCHAÎNER (engine-disable + chunk)** :
  OverwhelmingWrath Taunt place sur tous les adjacents Taunted_OnlySpecificTargets + BlockMovement + CantUseAbility
  (cf. H30 = engine-disable) → un carry/buffer ennemi adjacent est forcé de frapper le taunter Azkor (Terrifying blunte
  sa mêlée) ET movement-locké + actifs coupés (no WarHowl-class) ; PUIS l'AoE retardée chunke la cible au tour suivant.
  PLAY : caster quand un carry/buffer mêlée ennemi est adjacent → taunt-lock (disable ses actifs class-WarHowl pour le round)
  + laisser l'AoE retardée le chunker ; le Terrifying rend la mêlée forcée quasi-gratuite. (cf. gameconfig --ability
  OverwhelmingWrath ; H30 Taunt coupe l'actif n=3) [n=1, 70006 chained]
- `Imospekh Overwatch (held, non-attaqué) + InescapableDeath (chain-on-OW-kill)` — **MIEN-À-ENCHAÎNER / ENGINE
  (turret de réaction)** : tenir Imospekh HORS d'attaque arme son Overwatch ; sur un kill déclenché par Overwatch
  il **RESTE en Overwatch** (retenant 1 hit de moins, InescapableDeath) et **chaîne sur l'ennemi suivant** ; chaque
  kill in-chain ajoute +1 hit (MultiThreatEliminator) avant le −1 → un seul tour ENNEMI peut rendre un gros burst multi-OW-hit
  + 1 kill, plus la regen LivingMetal. PLAY : garder Imospekh turret-positionné, screené (BigTarget Gulgortz), et NE PAS
  attaquer avec lui quand un dive arrive → la value de réaction (chaîne OW) > un actif. (cf. gameconfig --ability InescapableDeath ;
  H06 §3bis Imospekh ; MultiThreatEliminator +1-hit/kill) [n=1, 70008 chained]
- `Gulgortz Waaagh (summon 2 Ork Boyz + buff d'équipe + charge) comme swing de comeback` — **MIEN-À-ENCHAÎNER /
  ENGINE (board-swing en une activation)** : un cast (gated « n'a pas bougé ») ajoute 2 corps + buffe les
  Orks/adjacents (+move, normales mêlée +dmg/+1 hit) + charge un ennemi EN MOVE RANGE + tous les Ork Boyz prennent
  un tour. PLAY : caster depuis une position avec une cible de charge VALIDE en move range + des hex adjacents libres
  (la charge sur une cible trop loin / sans hex libre est rejetée mutated=False). Peut flipper un déficit board en un cast.
  (cf. gameconfig --ability Waaagh) [n=1, 70008 chained]
- `Arjac Foehammer (+dmg/Character défait) snowball` — **MIEN-À-ENCHAÎNER (finisher snowball, range 2, Stun)** :
  Foehammer scale **+dmg flat par Character tué dans la bataille** (cumulatif) + Stun jusqu'au prochain tour d'Arjac →
  après plusieurs kills il peut one-shot un tank. ⚠ **CAVEAT (vécu seed 70008 missed)** : il est sur une **LONGUE cooldown de
  bataille** → resté [indispo] tout l'endgame quand j'en avais besoin. PLAY : séquencer les character-kills d'abord pour pomper
  Foehammer, MAIS ne JAMAIS en faire la SEULE réponse à un tank (pas dispo au moment voulu) ; le coupler à un bypass-armure
  persistant. (cf. gameconfig --ability Foehammer) [n=1, 70008 missed]
- `Vitruvius RadBombardment (ligne Toxic AoE) + Arjac Foehammer (nuke Ranged-tagged, même tour)` — **MIEN-À-ENCHAÎNER
  (alpha-swing quand on est en déficit de board)** : le même player-turn, RadBombardment soften plusieurs ennemis groupés (cf. §3bis
  Vitruvius) PUIS Foehammer one-shot un carry full-HP. Foehammer est tagué **Ranged profile=Power** → **BYPASSE Terrifying**
  (réduction MÊLÉE only) et touche un carry Terrifying à plein PV ; le +dmg/Character défait scale le nuke (avec 2 de mes Characters
  morts, K! franc sur un carry full-HP + Stun). ⚠ **cross-validé les DEUX sides** : B (mine) a exécuté l'alpha, A (theirs) a identifié
  Foehammer comme menace high (scaling nuke + stun). PLAY : en déficit numérique, l'attrition lente perd — l'alpha AoE-line +
  finisher Ranged-tagged en un tour est le bon swing. (cf. gameconfig --ability RadBombardment|Foehammer)
  ▸ [self-play consensus, seed 80000 (opus run)]
- `Exitor CordClaw (Direct Pierce100) one-shot Archimatos (le summoner) → aucun Possession body` — **MIEN-À-ENCHAÎNER
  (déni d'engine + déni de body)** : Possession spawn un corps sur CHAQUE kill d'Archimatos (mêlée→Bloodletter,
  ranged→Blue Horror) ; tuer Archimatos avec MON unité (il est la VICTIME, pas le tueur) = **zéro Possession body**
  ET retire le summon-engine. PLAY : focus le summon-engine avec un one-shot armor-ignore AVANT qu'il summon ;
  l'identité du tueur compte pour Possession. (cf. gameconfig --ability CordClaw ; §2 Archimatos Possession = killer-identity)
  [n=1, 70008 chained]
- `Yarrick SendInTheNextWave (Cadian Guardsmen) + zone de contact → corps de réaction/écran jetables` — **MIEN-À-ENCHAÎNER
  (chaff-screen + reaction-bodies)** : chaque cast summon 2 Cadian Guardsmen +1 par allié DÉFAIT (cap 5, tirent
  immédiatement, cf. §3bis Yarrick) → les summoner VERS la zone de contact ajoute des corps de réaction qui screen ET
  punissent les summons-on-appearance adverses ET chip les casters/turrets au range, **sans dépenser les actions de mes
  héros**. PLAY : poser les Guardsmen au contact → ils tuent les summons ennemis qui apparaissent ET chipent les
  casters/turrets en réaction. ⚠ leur compte scale avec MES défaites (un kit qui se renforce à mesure que je perds des corps).
  ⚠ ils consomment leur action au tour IA (réaction) → indisponibles à mon tour immédiatement suivant.
  (cf. gameconfig --ability SendInTheNextWave) [n=1, 70006 chained]
- `WarHowl (Ragnar) → burst mêlée des Characters buffés` — **MIEN-À-ENCHAÎNER (ENABLER de burst)** : poser le
  **buff WarHowl AVANT** la frappe burst (WarHowl en 1er, l'attaque ensuite). WarHowl est un **no-move gate**
  (Ragnar ne doit PAS avoir bougé) qui **ne finit PAS son tour** → buffe Ragnar + tous les Characters mêlée
  alliés SANS normale ranged (exclut Abraxas) avec **Unstoppable + +dmg flat/hit + +Crit** jusqu'à la fin
  du tour. Le +dmg FLAT est énorme sur les normales **multi-hit** (Patermine 5× Psychic, Tanksmasha 3× Eviscerate).
  PLAY : WarHowl EN PREMIER → puis délivrer le burst des Characters buffés le MÊME tour (a converti des plans modestes en
  3 K! en UN tour). (cf. gameconfig --ability WarHowl) [n=2, 97002/70009 chained]
- `Patermine MightFromBelow (5× Psychic Pierce100 NoBlocking) → lead-burst sur la cible la + armurée` —
  **MIEN-À-ENCHAÎNER (anti-armure)** : 5× Psychic Pierce100 NoBlocking → **ignore armure/block** même sur low roll →
  idéal vs les corps mêlée high-armor. PLAY : **mener** le burst sur la cible la plus dure/blindée, puis **finir avec une K!
  d'attaque normale d'une autre unité**. ⚠ la clause de summon (Purestrain) ne chaîne QUE si le Patermine a des decoys adjacents
  (kill-gated CosmicHorror) — sans decoy, l'Ability_Summon fire mais produit RIEN (cf. §3bis Patermine).
  (cf. gameconfig --ability MightFromBelow) [n=1, 70009 chained]
- `Ulf SavageKiller (réaction 5-hit Power) + dive IA (ennemi active-user move adjacent)` — **MIEN-À-ENCHAÎNER /
  ENGINE de réaction** : SavageKiller résout AVANT l'actif de l'ennemi adjacent → pré-empte ET peut tuer le caster
  mid-cast (a killed Tigurius mid-StormOfWrath). PLAY : tenir une **ligne cohésive**, NE PAS sur-étendre, et laisser
  l'IA dive son engine adjacent à Ulf → kill GRATUIT en réaction (réactions T2 ont tué 2 carries à 0 coût). Coupler à
  Isabella RitesOfRestoration pour relancer le moteur si Ulf meurt (cf. entrée ci-dessous). ⚠ re-confirmé n+1 (seed 70005 :
  3 vagues de réactions DestroyerHive+CrushingClaws+SavageKiller ont tué un summon-engine quand il a dive adjacent + chaff
  SANS dépenser d'actions offensives ; même pattern « ligne cohésive → l'IA dive → reaction-kill gratuit » que 70004/70002).
  (cf. gameconfig --ability SavageKiller ; résout-avant-l'actif) [n=2, 70004/70005 chained]
- `Re'vas EarlyWarningOverride (Overwatch armé +2 Shield Drones) + cluster ranged cohésif shallow vs roster ALL-MELEE` —
  **MIEN-À-ENCHAÎNER / ENGINE de réaction** : caster EWO T1 (arme Re'vas en Overwatch + 2 Shield Drones screen) puis **HOLD**
  toute ma ligne ranged en cluster cohésif → un adversaire **100% melee + 1 ranged** est CONTRAINT de diver dans ma killzone →
  l'Overwatch chunke le 1er diveur AVANT mon tour + la masse de réactions (Overwatch + WireweaveNet counter + Corrodius aura)
  fait le killing SANS dépenser mes actions offensives. PLAY : armer l'OW (NE PAS attaquer = garder le gate not-attacked), tenir
  cohésif et shallow, focus-killer le diveur over-étendu depuis mes back tiles — laisser le reste se faire shredder en réaction.
  ⚠ once-per-turn (EWO [indispo] après cast) → planifier UN gros tour d'Overwatch, pas une masse garantie chaque round (cf. §3bis
  Re'vas). Moitié RÉCIPROQUE de H03 ; même classe que `Ulf SavageKiller + dive IA` (le reaction-engine porte le W si la ligne
  reste défensive/cohésive, pattern 96002/98002/70001/70002/70051/70009). ⚠ CONTRE-INDICATION : INERTE vs un cluster ALL-RANGED
  qui ne dive jamais (cf. §Ennemies Re'vas-côté-ennemi 70052 — le hold-baite-le-dive est le contre-profil de l'all-ranged
  focus-fire). (cf. gameconfig --ability EarlyWarningOverride) [n=1, 70056 chained]
- `Re'vas EarlyWarningOverride (Overwatch-turret +re-arm/kill) + Sarquael GrimRetribution (held ranged OW) + Aun'Shi SereneUnifier (−50% dmg aura R1) + cluster cohésif` —
  **MIEN-À-ENCHAÎNER / ENGINE de réaction (mur « hold-baits-the-dive » TRIPLE-stack)** : empiler 2 reaction-engines (Re'vas
  Overwatch-turret qui re-arme à chaque kill + Sarquael GrimRetribution held-overwatch ranged) DERRIÈRE une aura défensive
  (Aun'Shi −50% dmg subi R1) sur un cluster cohésif → un ennemi all-melee est CONTRAINT de diver dedans = plusieurs carries morts
  en réactions sur le tour adverse SANS dépenser mes actions offensives, pendant que l'aura −50% garde ma ligne à ZÉRO perte hero.
  PLAY : armer Re'vas EWO + laisser Sarquael **unactioned** (OW armé only-if-not-attacked) le tour AVANT le contact, tenir le cluster
  groupé, NE PAS pousser les fragiles forward ; clusteriser mes T'au près d'Aun'Shi pour l'aura −50% avant le dive. Closer =
  focus-kill l'engine adverse une fois le board nettoyé par les réactions (a tué les 2 carries+engine-source T2 zéro perte, AVANT
  qu'un Kharn score un kill = TheBetrayer jamais armé). Même classe que `Re'vas EWO + cluster vs ALL-MELEE` ci-dessus mais avec un 2ᵉ
  overwatcher ranged + l'aura −50% qui rend la survie GRATUITE (pattern 96002/98002/70001/70056). ⚠ même CONTRE-INDICATION : INERTE vs
  un cluster ALL-RANGED qui ne dive jamais (cf. §Ennemies Re'vas 70052). (cf. gameconfig --ability EarlyWarningOverride|GrimRetribution|SereneUnifier)
  [n=1, 70060 chained]
- `Sarquael Supercharge (ranged Plasma r3, décapitation : cible + ≤2 hex derrière) + follow-up melee multi-source → one-turn kill d'un engine soft` —
  **MIEN-À-ENCHAÎNER (anti-summon-engine one-turn kill)** : Supercharge front-load un gros chunk sur un engine soft (summon/caster
  no-Resilient), puis 2 normales melee cheap le FINISSENT le même tour → kill GARANTI d'un summon-engine AVANT son cast. ORDRE/RÈGLE :
  lead Supercharge (no-move = HeavyWeapon +dmg) sur l'engine, **vérifier min-total > HP cible AVANT de committer** (kill-not-chip,
  cf. §Ennemies Abraxas — un chip non-létal laisse l'engine caster son board-flip), puis séquencer 2 melee normals pour garantir le
  kill (Abraxas tué en un tour, ZÉRO MasterOfTheTutelaries — pas de Pink Horror/Screamer). Le debuff +Plasma-pierce que Supercharge
  laisse aide aussi le follow-up. (cf. gameconfig --ability Supercharge ; §2 Abraxas MasterOfTheTutelaries no-HP-threshold) [n=1, 70060 chained]
- `Typhus Psychic normal (Pierce100 + NoBlocking) + Ulf GreatFrostAxe (4-hit ACTIF) → kill Trajann (Resilient+MartialKatah+block) en UN tour` —
  **MIEN-À-ENCHAÎNER (anti-anvil self-healing)** : la fenêtre de kill d'un mur Trajann (MomentShackle en cd) existe via une
  séquence à 3 temps : (1) chunker Trajann par RÉACTIONS le tour précédent (DestroyerHive/CrushingClaws) ; (2) **Typhus Psychic
  d'abord** (Pierce100 + NoBlocking → bypass son block ET MartialKatah −20%, qui ne réduit QUE les normales) pour le chunker
  sous le seuil ; (3) **Ulf GreatFrostAxe ENSUITE** (4-hit ACTIF → bypass aussi MartialKatah + bat Resilient floor-then-finish →
  Overkill) le MÊME tour. ORDRE IMPOSÉ : Psychic-bypass-block PUIS actif-multi-hit-finish. EXIGE que MomentShackle soit en cd
  (sinon il heal-to-full et la fenêtre se referme — cf. 70004 burst épuisé, 70007 écran jamais cassé). ⚠ NE PAS chiper (heal+block
  annulent un dmg non-létal). (cf. gameconfig --ability GreatFrostAxe ; §3bis Trajann MartialKatah −20%-normales-only ; §1 Resilient
  × multi-hit) [n=1, 70005 chained]
- `Titus FuelledByFury/FinalJustice + mes finisseurs UNIQUEMENT high-HP adjacents` — **MIEN-À-ENCHAÎNER (anti-revive)** :
  la 1ʳᵉ défaite/tour de Titus bloque l'overkill → FinalJustice fire TOUJOURS, mais son revive ne déclenche QUE si
  la riposte FJ DÉFAIT un ennemi adjacent. PLAY : pré-chunk avec un tank, **finir avec un autre corps high-HP**, et garder
  TOUS mes fragiles (Ulf/Tjark) NON-adjacents → FJ frappe un tank qui survit = pas de kill = pas de revive = mort
  permanente. ⚠ **n+1 APPLIQUÉ avec un STUN-debuff (seed 70058)** : tuer Titus avec une ability qui pose AUSSI un self-debuff sur le
  tank survivant aide la riposte FJ à ne RIEN tuer — Aesoth VexillaMagnifica a K!'d Titus avec SEULEMENT Aesoth adjacent, et le
  **−66% dmg de VexillaMagnifica** a réduit la riposte FJ (le tank a survécu) → no kill → no revive = mort PERMANENTE
  (WasOverkilled=0 vérifié). PLAY : router le coup fatal sur Titus quand SEUL un tank high-HP est adjacent, idéalement via une
  ability qui DEBUFF le tank (absorbe la riposte). (cf. gameconfig --ability FuelledByFury|VexillaMagnifica ; revive-gated-on-FJ-kill)
  [n=2, 70004 avoided + 70058 applied]
- `Isabella RitesOfRestoration + Imperial Character défait (reaction-engine type Ulf)` — **MIEN-À-ENCHAÎNER (recover-engine)** :
  ressuscite 1 Imperial Character défait (+ ≤2 Imperial Summons) dans un hex libre adjacent (ne peut agir ce tour) + self/adjacents
  heal → **récupère un moteur de réaction** (Ulf SavageKiller/FinalJustice). PLAY : caster APRÈS avoir perdu un corps Imperial à un
  trade pour relancer la punition du dive (a ramené Ulf → moteur SavageKiller relancé). ⚠ **[indispo] après 1 usage** (once/long-cd,
  cf. H13) → swing UNIQUE, le réserver pour le corps le plus impactant. (cf. gameconfig --ability RitesOfRestoration) [n=1, 70004 chained]
- `FGL/SuppressiveFire (Burchard) → Pinned → Overwatch turret` — **MIEN-À-ENCHAÎNER** : Pin coupe
  l'Overwatch/déplacement adverse pendant que MA turret Overwatch punit les moves entrants —
  position défensive maintenue = gagne l'attrition par réactions. [n=1, 96002 W]
- `Burchard FragstormGrenadeLauncher (6× Blast, range 2, leftover hits prioritise kills) → kill-chain 2-for-1` —
  **MIEN-À-ENCHAÎNER (kill-chain)** : après avoir tué la cible primaire, les hits Blast RESTANTS s'auto-allouent aux AUTRES
  ennemis dans 2 hex en **priorisant les kills** = finit automatiquement un voisin bas-PV. PLAY : tirer Frag sur une primaire déjà
  chunkée qui jouxte un autre corps faible → un cast = 2 kills (double-kill vécu). ⚠ **PAS once-per-battle** : Frag est un actif Blast
  standard à **cooldown** (revient à [prêt] dans le même combat, contraste avec le set H13 DoomSiren/MurderousSwing no-refresh) →
  ré-utilisable chaque cd. (cf. gameconfig --ability FragstormGrenadeLauncher) [n=1, 70002 chained]
- `Adamatar DoomSiren (3× Direct Pierce100, primaire + 2 adjacents-à-la-cible) + ObsessiveAnnunciation aura (+ranged subi)` —
  **MIEN-À-ENCHAÎNER (chunk-2-corps + setup ranged)** : DoomSiren bypasse l'armure (Pierce100) et splash la cible primaire
  + jusqu'à 2 ennemis adjacents À LA CIBLE → lead DoomSiren sur un **fragile collé à un anvil/cluster** = chunke le fragile
  POUR le kill ET chunke l'anvil voisin GRATIS. PUIS positionner Adamatar **adjacent à un ennemi** pour que son
  aura ObsessiveAnnunciation (+dmg ranged subi) **feed mes kills ranged suivants** (Roswitha/Ahriman). PLAY : DoomSiren
  d'abord (le burst Pierce100), Adamatar reste adjacent pour l'aura, ranged ensuite. ⚠ **CAS MkXGravis (seed 70000)** :
  le Direct Pierce100 **bypasse aussi la double-armure MkXGravis** (qui ne réduit pas les Crit/Psychic/Direct, cf. §1) →
  réserver DoomSiren pour un **cluster d'units armurées MkXGravis/Inceptors**. Chaque OVERKILL ramp les normales d'Adamatar
  (ObsessiveAnnunciation +1 hit perma) → viser des cibles overkillables pour amorcer le snowball. ⚠ **status=MISSED (seed 70004)** :
  le volet ObsessiveAnnunciation+ranged n'a JAMAIS pu chaîner car mon seul ranged (Vindicta) est mort AVANT — leçon = protéger le
  dealer ranged qui doit consommer l'aura AVANT de positionner Adamatar pour le buff. ⚠ **CAS ANTI-BLOCK (seed 70004)** : DoomSiren
  Direct Pierce100 bypasse aussi le **block MomentShackle de Trajann** = le SEUL outil de mon roster qui touchait l'anvil
  self-healing à travers son block → le dépenser tôt (sans cible overkill) = chip-only vs l'anvil = loss structurelle ; RÉSERVER
  DoomSiren pour l'anvil Resilient+self-heal au recon (cf. §3bis Trajann + §5bis Ennemies). (cf. gameconfig --ability DoomSiren ;
  §1 MkXGravis exclut Crit/Psychic/Direct) [n=3, 70002/70000 chained, 70004 missed]
- `Roswitha BrazierOfHolyFire (2× Flame, nuke single-target) + CondemnorStake (+dmg vs Psyker, assassin de casters)` —
  **MIEN-À-ENCHAÎNER (nuke + anti-Psyker)** : Brazier = gros nuke single-target (**one-shot un corps ~9k non-Daemon** ;
  4× hits + aura +60% vs Daemons) → route Brazier sur le plus gros soft-body atteignable. SÉPARÉMENT, CondemnorStake fait de
  Roswitha un **assassin de Psykers dédié** (+dmg/attaque vs Psyker, même famille « bypass-via-anti-tool » que Tjark anti-Psyker
  H11) → router Roswitha sur les Psykers ennemis (free KILL sur un Ahriman ennemi Psyker en réaction). ⚠ garder au RANGE vs cibles
  Explodes. (cf. gameconfig --ability BrazierOfHolyFire|CondemnorStake) [n=1, 70002 chained]
- `kill confirmé (K!) AVANT l'attaque normale` (même unité) — **MIEN-À-ENCHAÎNER (séquençage)** :
  jouer l'**ability/attaque qui CONFIRME le kill en premier**, pas après une normale qui a déjà
  dépensé l'action → 97002 a raté un kill en inversant l'ordre (Azkor). [n=1, 97002]
- `Aethana PathOfCommand (+dmg Aeldari) + Dante LordOfTheHost (+dmg Flying/RapidAssault) + LightOfSanguinius` —
  **MIEN-À-ENCHAÎNER (⚠ conditionnel à la livraison)** : les 2 auras de carry stack quand les deep-strikers
  atterrissent à ≤2 hex l'un de l'autre ET d'une cible → buffe le burst Melta LightOfSanguinius (alpha 1-tour).
  ⚠️ **PIÈGE (seed 98003, status=missed)** : un deep-strike ne peut PAS atterrir adjacent à un ennemi et le
  teleport-move **auto-finit** le deep-striker mêlée non-adjacent (cf. §1 TeleportStrike) → l'alpha est
  **INDÉLIVRABLE** sur un cluster lointain le même tour. **NE PAS dépenser les deep-strikers** quand le cluster
  ennemi est hors charge-range et qu'un atterrissage non-adjacent les strande → les garder **groupés+shallow**
  avec le ranged, alpha SEULEMENT quand tout le roster peut co-fire. (J'ai violé ça = perte des 2 carries T1.)
  (cf. gameconfig --ability PathOfCommand|LordOfTheHost|LightOfSanguinius) [n=1, 98003 missed]
- `Sibyll PsychicMaelstrom (Psychic NoBlocking) → engine Mechanical blindé` — **MIEN-À-ENCHAÎNER / ANTI-armure** :
  réserver le Psychic NoBlocking (le SEUL bypass du stack Mechanical, cf. §1) pour les **engines blindés**
  (Tan Gi'da summon-engine, Aleph-Null repair-hub), JAMAIS le chaff ; pré-positionner la caster T1 pour qu'un
  engine entre en r2+move3 reach T2, plutôt que de strander les carries. (cf. gameconfig --ability PsychicMaelstrom)
  [n=1, 98003 chained]
- `Tjark HuntersBeyondDeath (anti-Psyker) → casters Psyker ennemis (Xybia/Abraxas/Archimatos-class)` —
  **MIEN-À-ENCHAÎNER / ANTI-engine Psyker** : Tjark fait **+dmg PAR HIT vs Psyker** (= assassin de casters)
  ET son aura suppresse les Psykers ennemis dans 2 hex (−dealt, pas d'extra-target sur leur normale ranged). Vs un
  engine-set **Psyker-lourd** (≥2 casters), c'est l'OUTIL DE KILL-ENGINE dédié : router Tjark sur les Psyker-casters
  pour les assassiner, l'aura blunte les survivants (a démantelé un wincon-set Psyker = W). (cf. gameconfig --ability
  HuntersBeyondDeath ; §1 H11 anti-Psyker) [n=1, 98001 chained]
- `Archimatos Possession + finish RANGED (Psychic NoBlocking) → free Blue Horror` —
  **MIEN-À-ENCHAÎNER (body-snowball)** : un kill RANGED (Psychic) d'Archimatos spawn un **Blue Horror gratuit** dans
  l'hex de la victime (un kill MÊLÉE → Bloodletter) ; le Psychic NoBlocking ignore l'armure. PLAY : finir les
  ennemis bas-PV avec le ranged Psychic d'Archimatos plutôt qu'en mêlée → +1 corps gratuit par kill + bypass armure.
  ⚠ killer-identity (cf. §2) : Archimatos doit être le TUEUR (l'acteur), PAS la victime. ⚠ le body spawné scale AU-DESSUS
  du tooltip (HP/Atk runtime > i2 — recon-on-appearance la PV runtime, cf. H43). (cf. gameconfig --ability Possession)
  [n=2, 98001/70054 chained]
- `Snotflogga SquigHound + attaque normale → Grot auto-attaquant gratuit (engine self-sustaining)` —
  **MIEN-À-ENCHAÎNER (board-farm)** : chaque normale de Snotflogga ajoute +2 hits ET auto-summon un Grot (pumpé,
  cf. H34) adjacent à la cible qui **attaque immédiatement** (cap <5 Grots) → body+chip engine qui se
  nourrit seul. PLAY : juste **continuer d'attaquer avec Snotflogga** chaque tour — chaque swing farme un Grot qui
  trade/chip GRATIS ; l'ennemi gaspille des tours entiers à tuer mes Grots remplaçables pendant que mes héros
  restent sains (attrition décisive). (cf. gameconfig --ability SquigHound) [n=1, 98001 chained]
- `Snotflogga normale (SquigHound 3 hits discrets) + GetStuckIn → melee-finish d'un assassin Terrifying/Camouflage (Deathleaper)` —
  **MIEN-À-ENCHAÎNER (anti-mitigation melee-finish)** : les 3 frappes Physical DISCRÈTES d'une normale de Snotflogga résolvent
  INDÉPENDAMMENT → contournent partiellement Terrifying (réduction mêlée) ET Camouflage (anti-ranged) ET Resilient (multi-hit ≥2).
  PLAY : router Snotflogga sur un assassin Terrifying/Camouflage (Deathleaper) le tour où il sort du deep-strike → near-one-shot
  AVANT son vanish/re-strike (FearOfTheUnseen). (cf. gameconfig --ability SquigHound ; §2 Deathleaper Terrifying/Camouflage)
  [n=1, 70053 chained]
- `Aesoth VexillaMagnifica (stun 2 adjacents + −66% self, cd2 repeatable) + follow-up ranged/melee → stun-then-finish d'un engine` —
  **MIEN-À-ENCHAÎNER (control-then-kill)** : VexillaMagnifica frappe 2 ennemis adjacents (CantUseAbility coupe leurs ACTIFS, laisse
  leur normale) + Aesoth −66% dmg subi → l'engine stunné ne peut pas user son actif ce round, et le chunk prépare un kill
  same/next-turn. **REPEATABLE (cd2, PAS once-per-battle).** PLAY : caster quand 2 ennemis (un engine + un body) sont adjacents
  à Aesoth → stun-lock l'engine + chunk, puis finir avec une autre source. ⚠ ne PAS budgétiser le dmg de VexillaMagnifica comme un
  K? fiable (fortement réduit par les buffs/blocks de la cible, cf. §3bis Aesoth) — c'est le STUN qui est l'arme.
  (cf. gameconfig --ability VexillaMagnifica) [n=1, 70053 chained]
- `Thaumachus ArcaneShield (no-move → end-of-turn trigger) → ranged carry le + proche (Shiron) chaque tour` —
  **MIEN-À-ENCHAÎNER / ENGINE (durabilité gratuite sur le carry)** : ArcaneShield repose un bouclier sur l'allié non-Mechanical
  le + proche ≤2 hex APRÈS le move de Thaumachus, OU à la FIN de son tour s'il N'A PAS bougé (priorité Thousand Sons > Chaos > autre >
  self) → tenir Thaumachus stationnaire/finishing glue le bouclier sur mon ranged carry chaque tour. PLAY : garder Thaumachus immobile
  à ≤2 hex de mon carry ranged → bouclier ré-appliqué en continu = carry effectivement intouchable. (cf. gameconfig --ability ArcaneShield)
  [n=1, 70053 chained]
- `chunk + Calandis ranged floor-to-1 + Shiron ranged finish → bat Abaddon Resilient SANS triggerer Drachnyen melee-riposte` —
  **MIEN-À-ENCHAÎNER / ANTI (anti-Resilient-anvil + anti-riposte)** : Resilient floor tout coup létal non-overkill à 1 HP ; un 2ᵉ hit
  DEPUIS 1 HP = kill propre (non-overkill, WasOverkilled=1). En RANGED multi-source on évite Drachnyen (la riposte OFFENSIVE perma-double
  d'Abaddon, qui ne fire que sur SES normales mêlée → ne pas le mêler) → l'anvil tombe sans représailles. PLAY : finir un anvil
  Resilient+Drachnyen-class par chunk → floor-to-1 ranged → finish ranged (jamais en mêlée). (cf. gameconfig --trait Resilient ;
  §3bis Abaddon Drachnyen riposte offensive sur mêlée) [n=1, 70053 chained]
- `BeastSlayer carrier (Snotflogga / Tanksmasha-orksNob) + enemy BigTarget/Vehicle (Gulgortz, Kut…) → anvil-killer dédié` —
  **MIEN-À-ENCHAÎNER** : `BeastSlayer` = +dmg vs BigTarget/Vehicle + block ajouté vs l'armure courante → router le
  porteur BeastSlayer SPÉCIFIQUEMENT sur les anvils BigTarget adverses (il les frappe bien plus fort que mes hitters
  normaux). Sur un FinalJustice-carrier (Gulgortz), pairer avec une **marge d'overkill** (>2× PV restants) pour **supprimer sa
  FinalJustice/LightImUp double-volée**. PLAY : envoyer le BeastSlayer (pas un soft) overkiller Gulgortz — le multiplicateur
  transforme un Gulgortz très bas en overkill clean (→ AUCUNE FJ). ⚠ seed 70009 : Tanksmasha a chunk-kill Gulgortz NON-overkillé
  (FJ a fire mais absorbée par Tanksmasha tank) → la marge d'overkill manquait ; budgétiser un chunk de plus pour le déni FJ complet.
  (cf. gameconfig --trait BeastSlayer ; §1 FinalJustice/Overkill >2×) [n=2, 98001/70009 chained]
- `tuer un Explodes ennemi DANS son propre cluster → AoE friendly-fire gratis` (Aleph-Null/necroSpyder,
  Snappawrecka, Morvenn…) — **MIEN-À-ENCHAÎNER** : Explodes = 25% PV max Direct à TOUS les adjacents, **sans
  filtre ami/ennemi** (cf. §1) → tuer l'unité Explodes pendant qu'elle est entourée de SES alliés chunke la
  grappe gratis (vécu 98003 : Aleph-Null tué → chunke 3 alliés adjacents ; vécu 98002 : Aleph-Null fini au RANGED
  pendant qu'Anuphet + un Necron Warrior étaient adjacents → Explodes les a chunkés GRATIS, accélérant l'effondrement du noyau).
  Silver-lining même sur une ligne perdue ; **finir au RANGE** pour garder MES fragiles hors de l'AoE. [n≥3, 98002/98003 chained]
- `Asmodai ExemplarOfHate (mark +dmg team melee/OW) → Haarken HeraldOfTheApocalypse (burst multi-hit)` —
  **MIEN-À-ENCHAÎNER (ordre imposé)** : le mark +dmg s'applique **par hit** à toute la team → multiplicatif
  avec un burst multi-hit ; **MARK D'ABORD (Asmodai), PUIS le burst Haarken** sur la cible marquée → le
  Herald 4-hit gagne en valeur ET touche 2 cibles (la marquée + l'ennemi derrière, qui prennent +next-attack).
  Aligner une cible adverse avec un ennemi derrière elle maximise le combo. (cf. gameconfig --ability ExemplarOfHate|HeraldOfTheApocalypse)
  [n=1, 98004 chained]
- `Tyrant Guard BigTarget (−1 hit ranged aux adjacents) + GuardianOrganism (−33%/−dmg si TG n'a pas bougé) + fragiles adjacents` —
  **MIEN-À-ENCHAÎNER (écran défensif)** : garder le Tyrant Guard en écran forward (NON-bougé pour armer
  GuardianOrganism) et coller mes fragiles (Abraxas Psyker, Yazaghor) adjacents → le ranged ennemi entrant dans
  la grappe est doublement émoussé (−1 hit + −33% dmg) → les fragiles SURVIVENT dans la danger-zone et restent
  pour réagir. C'est l'écran qui permet à la moitié RÉCIPROQUE de H03 (punir le dive en réactions) de fonctionner :
  ligne tenue = réactions gagnent l'attrition. ⚠ ne PAS faire bouger le TG (perd GuardianOrganism).
  (cf. gameconfig --trait BigTarget|GuardianOrganism) [n=1, 98002 chained]
- `Kharn TheBetrayer (kill earné) → auto move+4× Eviscerate au DÉBUT de chaque tour de Kharn` —
  **MIEN-À-ENCHAÎNER (chip récurrent gratis)** : une fois Kharn amorcé par un kill, il auto-move 2 hexes + frappe
  4× Eviscerate un adjacent au START de chacun de ses tours, **SANS action dépensée** → chip récurrent chaque round.
  ⚠ **NE réagit PAS au tour adverse** (fire à son PROPRE start-of-turn, pas un Overwatch) → ne pas le compter dans le bilan
  de réactions ; ⚠ le chip auto-move garde Kharn ENGAGÉ forward → tension avec « ne pas sur-étendre mon carry » (Kharn
  over-étendu/un-retreatable seed 98002). (cf. gameconfig --ability TheBetrayer) [n=1, 98002 chained]
- `cluster MIEN groupé + soutien mutuel → punir le dive adverse en réactions` — **MIEN-À-ENCHAÎNER /
  réciproque H03** : garder mes unités groupées et en soutien mutuel → quand l'IA s'avance dans la grappe,
  un gros total de réactions (Overwatch/contre) = plusieurs kills SANS dépenser mes actions offensives (vécu
  98004 : 3 kills en réaction T2-T3 ; vécu 70002 : réactions ont tué l'Ahriman ennemi puis fini un Lucien Resilient
  EXACTEMENT en non-overkill = 2 kills décisifs zéro action offensive — un carry BlackRage auto-charge FORCE le dive dans
  la grappe). C'est la moitié RÉCIPROQUE de H03 (bien jouée) qui porte les W ; ⚠ ne PAS la confondre avec la moitié PROPRE
  (ne pas sur-étendre MES carries — violée seed 98004 ET seed 70002 [Abraxas reachable mid-board → focus-killé]). ⚠ **CAS
  STRUCTUREL FORT (seed 70051)** : un adversaire SANS aucun Resilient ET sans carry ranged kiting unreachable **DOIT diver**
  pour porter le combat (100% melee/r2) → un mur Resilient MIEN (Maladus/Dreir/Lucien) absorbe le dive et chaque engine soft
  devient atteignable à sa SORTIE = matchup all-soft+all-melee vs mur Resilient est **structurellement favorable** (l'INVERSE
  exact des séries row-9-inatteignables 96001/97001/70050 — PAS un reach-fail) → hold cohésif T1-T2, l'IA avance tout son cluster
  mid-board, engines softs (Aethana/Sibyll) exposés T3 = H02 portée par H03-réciproque. [n≥4, 93001/98004/70002/70051 chained]
- `Maugan Ra HarvesterOfSouls (AoE r3) → grappe de dive ennemie clusterisée` — **MIEN-À-ENCHAÎNER** :
  HarvesterOfSouls splash la cible + TOUS les ennemis adjacents à elle ET en range 3 de Maugan Ra (vrai multi-cibles,
  cf. §3bis Maugan Ra) → cibler **l'ennemi le plus clusterisé APRÈS qu'ils ont dive in** = un cast cleave plusieurs
  corps (4 cibles en un cast vécu, setup d'un tour de clean-up multi-kill). ⚠ **PIÈGE (tension H03 propre)** : caster depuis
  row 3 expose la carry ranged fragile → privilégier l'angle le plus SHALLOW possible, ou accepter un AoE moins optimal plutôt
  que pousser Maugan Ra dans la kill-zone (la pousser à row 3 chaque tour a contribué à sa mort). (cf. gameconfig --ability HarvesterOfSouls)
  [n=1, 98000 chained]
- `Tyrant Guard CrushingClaws (Taunted_CantUseAbility) → engine ennemi soft (summoner OU Psyker-amplifier)` —
  **MIEN-À-ENCHAÎNER (control / engine-disable)** : caster CrushingClaws sur un engine adverse soft → le combo moteur
  **Taunted_BlockMovement + Taunted_CantUseAbility + Pinned coupe TOTALEMENT ses actifs 1 round** (cf. §1 Taunt) sans
  le tuer (utile vs un engine Resilient/ToughToKill dur à finir, OU pour leader un focus pendant qu'il est inerte).
  Verrouille aussi la cible sur mon anvil (ne peut cibler que TG). DEUX cas vécus : (a) **summoner** Dreir (seed 98000) →
  LeadingTheCharge bloqué = 0 summon de Death Riders ; (b) **Psyker-amplifier** Thaumachus (seed 70000) → AttemptedPossession
  ET ArcaneShield jamais castés de TOUT le combat = engine-disable propre + lead du focus. ⚠ durée 2 rounds observée
  (i2 dit 1) + source Pinned non confirmée → cf. H30. (cf. gameconfig --ability CrushingClaws) [n=2, 98000/70000 chained]
- `Azrael Overwatch HELD armé (LionHelm +dmg) + ligne groupée Terrifying/TerrorsLament + dive mêlée ennemi` —
  **MIEN-À-ENCHAÎNER / engine de réactions (réciproque H03)** : tenir Azrael SANS attaquer ré-arme son Overwatch dans
  le tour adverse (gate=not-attacked, cf. §1) ; le `LionHelm` (range 2) donne **+dmg sur les attaques Overwatch des
  alliés à ≤2 hex** → un dive ennemi dans la grappe se fait reaction-killer en multi-source boosté SANS dépenser mes
  actions offensives, et mes forward bodies Terrifying (Dante) + TerrorsLament (Jain Zar, −dmg/−1 hit mêlée aux adjacents)
  **blunt aussi la mêlée entrante ET les death-ripostes FinalJustice** des ennemis tués en réaction. PLAY : NE PAS pousser
  Azrael forward pour un K? non-garanti — le HOLD armé + grouper des alliés à ≤2 hex = la moitié RÉCIPROQUE de H03 portée
  par le boost (2 kills T3 sur le dive, FJ ripostes absorbées par mes forward Terrifying/TerrorsLament). MÊME mécanisme de W
  que 96002/98002 (turret défensive RANGED = gagne l'attrition). (cf. gameconfig --ability LionHelm ; §1 Overwatch
  gate=not-attacked ; §1 Terrifying/TerrorsLament) [n=1, 70001 chained]
- `Azrael DarkTalonStrike (1× Direct Pierce100 + 6× Bolter LINE) → 2 ennemis ALIGNÉS (deep-strikers)` —
  **MIEN-À-ENCHAÎNER (chunk-2-corps + lock + bypass blindage)** : le Direct Pierce100 sur la cible **bypass armure ET
  TerminatorArmour** (Direct exclu de la réduction, cf. §1) ET la ligne de 6× Bolter touche **TOUS les ennemis en ligne
  droite ininterrompue depuis la cible** → aligner le tir pour que la ligne Bolter passe par un **2ᵉ ennemi clusterisé**
  = chunke deux deep-strikers en un cast + les Suppress (+ Pinned move-1 observé, cf. H38). PLAY : viser de sorte que la ligne
  catche un 2ᵉ ennemi sur le même axe → chunke 2 deep-strikers + les Pin, puis FINIR le chunké avec un ranged normal cheap depuis
  une tuile shallow. ⚠ once-per-battle observé (H38) → réserver pour un swing décisif (deux deep-strikers alignés / un tank
  Psychic/Direct-only type Njal). (cf. gameconfig --ability DarkTalonStrike ; Pinned/once-per-battle = H38) [n=1, 70001 chained]
- `Jain Zar SilentDeath (3 hits primaire + ≤3 adjacents adjacency-chain) → 2 engines ennemis ADJACENTS` —
  **MIEN-À-ENCHAÎNER (engine-finish + chunk-carry GRATIS)** : SilentDeath = arme lancée (caster ne bouge PAS) qui frappe
  la primaire ET jusqu'à 3 ennemis adjacents entre eux, Pierce80 (bat l'armure ET Resilient sur chaque cible via hits
  discrets). PLAY : quand un engine de sustain adverse (leur Nicodemus) jouxte le carry (leur Dante), **finir le LOWER
  avec SilentDeath** → splash GRATIS le carry voisin dans le même cast ; séquencer APRÈS un gros chunk pour garantir le
  kill de l'engine (sustain mort + carry pré-affaibli pour le reaction-kill suivant). ⚠ once-per-battle observé (cf. H13) →
  réserver pour ce double-coup décisif, ne pas l'alpha-dump. (cf. gameconfig --ability SilentDeath) [n=1, 70001 chained]
- `Sy-gex (admecDestroyer) Overwatch HELD armé + ligne groupée` — **MIEN-À-ENCHAÎNER / engine de réactions (réciproque H03)** :
  tenir Sy-gex SANS attaquer en NORMAL ré-arme son Overwatch r3 (gate=not-attacked, cf. §1/§3bis Sy-gex) → tout ennemi qui
  BOUGE dans son arc r3 (mêlée OU non) se prend la volée 4 hits gratis au tour adverse. PLAY : le HOLD armé + grouper la ligne
  = la moitié RÉCIPROQUE de H03 (même mécanisme que la turret Azrael/Burchard). ⚠ **LIMITE (seed 70007 chained)** : un
  SEUL Overwatcher ranged est NÉGLIGEABLE vs un board-flip summon-engine (chunk modeste, mais l'ennemi a flippé le board le tour
  suivant) → l'Overwatch hold ne « gagne l'attrition » que SANS board-flip adverse en jeu (cf. la condition turret 96002 vs 97001).
  ⚠ **CONTRE-EXEMPLE POSITIF n+1 (seed 70058 W)** : le MÊME Sy-gex Overwatch HELD-armé + un screen cohésif (Aesoth
  BigTarget/StandVigil/Resilient) a PORTÉ le W vs un ennemi 3/5 melee/Flying CONTRAINT de diver → l'Overwatch a reaction-KILLED Ulf
  sur le dive (pré-chunké BasiliskBarrage) ET la dive a exposé les 2 engines back-row (Sho'syl/Njal), tués T4 — ici PAS de
  board-flip adverse → le hold-armé a bien gagné l'attrition (pattern 96002/98002/70001/70056/70060). PLAY : feeder Sy-gex
  (HeavyWeapon) avec un buffeur ranged (Thaddeus) amplifie l'output de l'Overwatch. (cf. gameconfig --ability Sy-gex-Overwatch)
  [n=2, 70007 chained + 70058 W]
- `Sy-gex (admecDestroyer) attaque NORMALE 4× Physical r3 (multi-hit) → cible Resilient` — **MIEN-À-ENCHAÎNER
  (anti-Resilient propre)** : l'attaque normale de Sy-gex = 4 HITS → bat fiablement Resilient (le 1er hit floor à 1, chaque hit
  suivant tue puis OVERkille) → l'outil correct pour tuer CLEAN un summon-engine Resilient (a both KILLED ET OVERKILLED Resilient
  Yarrick en un coup, ce qui a AUSSI stripé SummaryExecution de ses Guardsmen). PLAY : router le 4-hit de Sy-gex sur une cible
  Resilient finissable plutôt qu'un single-hit K? trompeur (cf. H04/§1 multi-hit-bat-Resilient) ; ⚠ le HeavyGravCannon
  (+dmg/+pierce) ne s'ajoute QUE vs Mechanical/Terminator Armour/MK X Gravis → inutile vs cibles non-armurées.
  (cf. gameconfig --trait Resilient ; §3bis Sy-gex 4× Physical r3) [n=1, 70007 chained]
- `Sy-gex (admecDestroyer) attaque NORMALE 4× Physical r3 + HeavyGravCannon → cible TerminatorArmour (après STUN)` —
  **MIEN-À-ENCHAÎNER (anti-TerminatorArmour propre)** : `HeavyGravCannon` (+dmg flat + +pierce vs Mechanical/TermArmour/
  MkXGravis, i2 confirmé) fait de Sy-gex (Mechanical attaquant) un **hard-counter de TerminatorArmour** : le multi-hit 4× Physical
  passe la 1ʳᵉ-attaque-réduite (seul le 1er hit blunté, cf. §1 TermArmour) PUIS chaque hit suivant tape full + bonus → tue clean.
  PLAY : (1) STUN d'abord l'engine TermArmour (Aesoth VexillaMagnifica) pour dénier son AoE/actif le round, (2) finir avec le 4-hit
  HeavyGravCannon de Sy-gex (Njal Psychic-AoE engine + TermArmour tué clean après stun). ⚠ le « seul le 1er HIT (pas toute la
  1ʳᵉ attaque-event) est réduit » reste candidate (H48, plausible — le +pierce HeavyGravCannon peut « débloquer » apparemment les
  hits) ; le bonus HeavyGravCannon LUI-MÊME est confirmé i2. (cf. gameconfig --trait HeavyGravCannon ; §1 TermArmour 1ʳᵉ attaque réduite)
  [n=1, 70058 chained]
- `Lucien normale (Loki) + VisionsOfHeresy (2ᵉ attaque GRATUITE r2) → 2 ennemis bas-PV distincts ≤r2` —
  **MIEN-À-ENCHAÎNER (double-finisher)** : la 2ᵉ attaque gratuite de Lucien cible *n'importe quel* ennemi ≤r2 (i2
  « an enemy within range 2 », pas « the same enemy », cf. §3 Lucien) → elle peut frapper une cible DISTINCTE de la
  normale → **une seule activation de Lucien = 2 kills** quand deux ennemis bas-PV sont tous deux à portée r2 l'un de
  l'autre. PLAY : garder Lucien comme finisher double — quand 2 ennemis bas-PV sont à ≤r2, sa normale K! le premier et
  la 2ᵉ attaque K! le second → 2 kills/activation (peut FinishMatch en un cast). (cf. gameconfig --ability VisionsOfHeresy)
  [n=1, 70051 chained]
- `Creed SwornProtector → Kell body-block + SupremeCommander → Guardsmen écran jetable` —
  **MIEN-À-ENCHAÎNER (ressource d'écran, status=na)** : quand Creed a été ciblé, `SwornProtector` spawn Kell
  comme body-block ; `SupremeCommander` peut poser des Guardsmen jetables pour bait/screen. PLAY : noter
  comme ressource de board disponible pour densifier le bait du dive adverse — sortir les summons-screens TÔT (T1)
  contre un adversaire plus dur aurait densifié le bait (Kell a spawn passivement quand Creed a été ciblé, mais
  SupremeCommander jamais cast car le combat s'est résolu vite ; ressource sous-utilisée, na). (cf. gameconfig --ability
  SwornProtector|SupremeCommander) [n=1, 70051 na]
- `Archimatos Incursion (sur un fragile forward) + body-screen → substitut de reaction-engine` — **MIEN-À-ENCHAÎNER
  (board-flip zero-loss / écran-de-réaction)** : Incursion summon des Bloodletters qui **attaquent immédiatement** la
  cible (jusqu'à 6, remplissant les hex adjacents, cf. §2 Archimatos) → les corps créés OCCUPENT les hex, **bloquent
  physiquement les routes d'approche de l'IA et absorbent son focus du tour suivant** → un Incursion sur une cible
  soft/bas-PV devient net-positif MÊME sans kill garanti, et **SUBSTITUE à un reaction-engine manquant** (Overwatch/
  counter absent du roster). PLAY : préférer Incursion à un normal-attack snipe quand la cible a des hex adjacents
  libres ET que la présence-board AI est la contrainte → les summons tradent dans le tour IA pendant que mes héros
  ne meurent pas (NET +2.00, ZÉRO perte, flip à 5v4 full HP vs un normal-snipe = perdre Archimatos 1-pour-1). ⚠ un roster
  summon-only n'a PAS de RIPOSTE (les bodies SCREENENT mais ne contre-attaquent pas) → ne pas confondre « j'ai un écran »
  avec un dive-punish (cf. §7 H03 réciproque-requiert-reaction-engine). (cf. gameconfig --ability Incursion) [n=1, 70055 chained]
- `Parasite BarbedOvipositor (kill non-Mechanical ciblé → Ripper dans l'hex de la victime) + summon-engines comme écran jetable` —
  **MIEN-À-ENCHAÎNER (body-par-kill + screen disposable)** : quand le Parasite tue une cible NON-Mechanical qu'il a
  ciblée (normale OU ability), un **Ripper Swarm spawn dans l'hex de la victime** et peut agir (cf. §2/§3bis Parasite
  BarbedOvipositor — ne fire PAS sur Mechanical) → couplé à mes autres summon-engines (Incursion d'Archimatos, ItItches),
  ces corps jetables laissent l'ennemi all-melee diver dans le chaff au lieu de mes héros. PLAY : mener avec les
  summon-engines pour bâtir un écran ; finir les soft ennemis avec l'écran + 1 héros, garder mes Psykers/fragiles
  derrière (un kill normale du Parasite sur un non-Mechanical a auto-spawné un Ripper = corps d'écran GRATUIT depuis un kill ;
  mes 4 héros sont restés sains). (cf. gameconfig --ability BarbedOvipositor) [n=1, 70055 chained]
- `Darkstrider StructuralAnalyser markerlight (sur tir ranged) + mes alliés ranged (adjacents / T'au ≤2 hex) + SuppressiveFire Pinned` —
  **MIEN-À-ENCHAÎNER (focus-amplifier ranged + control)** : chaque tir ranged de Darkstrider pose un **Markerlight**
  (Effect_Id 188/208, 3 rounds) → les alliés ADJACENTS + T'au à ≤2 hex font **+dmg ranged** vs la cible marquée
  (Darkstrider self-qualifie via la clause T'au-≤2-hex) ET `SuppressiveFire` **Pin** (−1 move, 2 turns) la cible. PLAY :
  ORDONNER Darkstrider EN PREMIER dans chaque focus (poser markerlight + Pinned avant que les alliés tirent) → ses
  propres hits empilés (RangedSpecialist × markerlight-self × buffs) en font mon dealer single-source DOMINANT, et les alliés
  ranged pompent le même focus. ⚠ le delta +dmg ALLIÉ reste non isolé numériquement (cf. H33), mais markerlight + Pinned sont
  CONFIRMÉS live. ⚠ INERTE si Darkstrider est le SEUL ranged de mon équipe (markerlight sans bénéficiaire = self-fed).
  (cf. gameconfig --ability StructuralAnalyser|SuppressiveFire ; --effect Markerlight) [n=1, 70054 chained]
- `Isaak CultDemagogue (board-flip r2) + Neophyte Hybrids (Ambush, tour immédiat) → seize numeric advantage` —
  **MIEN-À-ENCHAÎNER / ENGINE (board-flip instantané EN MA FAVEUR)** : 1 cast cible un ennemi ≤r2, place jusqu'à 8 decoys
  dans 2 hex autour, summon des Neophyte Hybrids sur la MOITIÉ (≤4, ranged r2, CHACUN Ambush) qui agissent
  IMMÉDIATEMENT (Summon auto move+attack). C'est le MÊME engine que le wiki flagge CRITICAL côté ennemi, ici utilisé POUR
  moi = board-flip + flanc en une activation. PLAY : le réserver pour SEIZE l'avantage numérique une fois l'ennemi aminci
  (cast T7 sur un Poxwalker → flip de surnombre qui a fini le combat). Bidirectionnel : dévastateur enemy-owned (à tuer Isaak
  avant cast) ET player-owned (engine décisif une fois l'ennemi thinned). (cf. gameconfig --ability CultDemagogue ; §1 Ambush)
  [n=1, 70054 chained]
- `Isaak Ambush (self-resurrect full-HP sur decoy ami) + mes decoys → récupère un corps focus-killé` —
  **MIEN-À-ENCHAÎNER / ENGINE (recover-engine)** : à sa 1ʳᵉ mort, Isaak laisse un decoy + ressuscite à **PV PLEIN**
  sur un decoy ami survivant AU DÉBUT de son prochain tour, puis agit IMMÉDIATEMENT — CONDITIONNEL : s'il ne reste AUCUN
  decoy ami quand son tour commence, il reste mort. PLAY : un kill sur Isaak n'est que TEMPORAIRE tant qu'un decoy survit
  → ne PAS paniquer si l'IA focus mon Isaak chunké ; ses decoys (semés par HypersensoryAbilities/Ambush/CultDemagogue) le
  ramènent full (focus-killé T5 → resurrected full-HP T6, board-flip CultDemagogue T7 a suivi). (cf. gameconfig --trait Ambush)
  [n=1, 70054 chained]
- `Sho'syl MV71 drone (normale = burst immédiat + drone-screen) + Tan Gi'da ControlEdict (Vanguard-on-attack, Protector) → mur de bodies screen-on-attack` —
  **MIEN-À-ENCHAÎNER / ENGINE (chaîne d'écrans générée par mes attaques, status=chained)** : DEUX engines screen-on-attack qui
  fabriquent des corps à CHAQUE de mes attaques — la normale de Sho'syl summon un MV71 drone (SaviorProtocols 50%
  intercept) qui **attaque IMMÉDIATEMENT** (au Damage stat de Sho'syl) + persiste comme screen ; chaque attaque de
  Tan Gi'da sous Protector summon un Skitarii Vanguard adjacent (cap 5). PLAY : attaquer chaque tour avec Sho'syl +
  Tan Gi'da → mes swings délivrent du dmg ET génèrent des corps-écrans qui SOAKENT le focus ranged ennemi au lieu de mes
  héros/amplificateurs (Vitruvius/Abraxas restent shallow). Idéal vs un ennemi focus-fire : il dépense ses tours à tuer mes
  drones/Vanguard remplaçables (5v0, ~14k de focus absorbé). ⚠ ces bodies SCREENENT mais ne contre-attaquent pas au tour adverse
  (sauf le hit immédiat du drone à la pose) → ne pas les confondre avec un dive-punish reaction-engine (réciproque H03 jouée en
  ACTIVE focus, cf. §7). ⚠ la persistance/bodyguard du drone reste candidate hypotheses.md. (cf. gameconfig --ability ControlEdict)
  [n=1, 70057 chained]

### Anti-synergies
- `Roswitha (Brazier Daemon-gated + CondemnorStake vs Psyker) vs MA compo summon-Daemon + Psyker` —
  **ANTI (triggered-against-me, seed 70059 W, HARD-COUNTER de compo MITIGÉ)** : Roswitha est le counter DÉDIÉ d'un roster
  qui summon des Daemons ET field des Psykers — son Brazier passe de 2× à 4× hits + gagne l'aura +dmg-vs-Daemon sur mes
  summons clusterés, et CondemnorStake en fait un assassin de mes Psykers (cf. gameconfig --ability BrazierOfHolyFire,
  CondemnorStake). RÈGLE DE RECON (miroir de l'aura-anti-X LIVE, cf. Atlacoya ci-dessous) : quand JE fielde Daemons+Psykers,
  une Roswitha adverse est une menace SPÉCIFIQUE à neutraliser tôt. COUNTER : (1) ne PAS clusterer mes Daemon-summons sur ses
  cibles (éviter 4×+aura) ; (2) ne PAS présenter mes Psykers adjacents (éviter CondemnorStake) ; (3) la tuer TOP-early parmi
  les softs — elle est SOFT (no-Resilient). Contrairement à Atlacoya (anti-Psychic STRUCTUREL, quasi-imtuable), Roswitha est
  SOFT → le counter = la tuer tôt avant qu'elle AoE mes summons / assassine un Psyker. [n=1, 70059 avoided]
- `Atlacoya (anti-Psychic flat) + double-Terrifying core (Atlacoya + Deathleaper) vs MON roster Psyker-heavy` —
  **ANTI (triggered-against-me, seed 70055, DAMAGE-TYPE COUNTER STRUCTUREL)** : noyau défensif anti-caster qui NÉGATE
  le profil de dégâts ENTIER d'un roster Psyker-heavy : (1) Atlacoya `DaughterOfTheAbyss` (réduction Psychic flat sur elle,
  cf. gameconfig --ability DaughterOfTheAbyss + §3bis) réduit mes Psyker-dealers à ~1-2 dmg ; (2) le double `Terrifying`
  (Atlacoya + Deathleaper) blunte ma mêlée. Résultat : mes 2 ennemis les moins counterés survivent à tout mon damage et
  grindent mes fragiles → endgame STRUCTURELLEMENT injouable. COUNTER = tuer Atlacoya EARLY avec du dégât NON-Psychic
  NON-Terrifying-réduit (RANGED Blast/Physical d'un non-Psyker) — mais elle est Terrifying+Parry+self-Psychic-reduction =
  quasi-imtuable pour un roster Psyker/melee → le VRAI counter = la SÉLECTION DE ROSTER (non-Psyker-reliant). RÈGLE DE RECON
  (miroir de l'engine-inerte H02/§6) : une aura anti-X (anti-Psychic) est LIVE précisément quand JE fielde la catégorie
  ciblée (Psykers) → flagger « Psyker-heavy vs anti-Psychic Atlacoya + Terrifying core = loss STRUCTURELLE probable » au
  recon, ne PAS s'appuyer sur des Psykers pour la casser. [n=1, 70055 triggered-against-me]
- `FinalJustice-carrier ennemi tué NON-overkill + MA fragile à portée de sa normale` —
  **ANTI (triggered-against-me, seed 70006)** : tuer un FJ-carrier SANS overkill déclenche une free normale qui choisit une
  cible ÉLIGIBLE **dans la portée d'attaque normale du porteur** (PAS une adjacence dure, cf. §1 FinalJustice + gameconfig
  --ability FinalJustice). ⚠ **Le label K! NE warne PAS** : il sommait les hits bruts = exactement les PV restants (aucune
  marge d'overkill détectée). PLAY : AVANT le coup fatal sur un FJ-carrier, garantir **OVERKILL (>2× PV restants)** OU
  **finir au RANGE** (aucune de mes fragiles à portée de sa normale) OU positionner pour que la riposte tape un TANK high-HP
  (cf. variante safety §5bis Ennemies / doctrine-learned §6). C'est la combinaison K!-trompeur (H04) + fragile adjacente à
  un FJ-carrier à sa mort. [n=1, 70006 triggered-against-me]
- `Vindicta FireOfAbsolution (splash Flame aux adjacents-à-la-cible) + MES units adjacentes à la cible` —
  **ANTI (friendly-fire propre, triggered-against-me seed 70000)** : à CHAQUE tir ranged de MA Vindicta, le splash Flame
  touche TOUS les units adjacents à la cible **SANS filtre faction** → friendly-fire mes propres units collées à la cible ;
  multi-hit normale = passif déclenché autant de fois (cf. gameconfig --ability FireOfAbsolution + §2 Vindicta).
  PLAY : **DÉGAGER mes units de l'adjacence-à-la-cible AVANT tout tir de Vindicta** (un kill shallow ou un repositionnement
  d'abord ; cf. doctrine-learned §7). ⚠ NB : côté ENNEMI le même passif punit le cluster ADVERSE (re-confirmé seed 70007 :
  un Vindicta adverse a tué son PROPRE summon + chunké son propre Aesoth → le splash no-filtre joue dans LES DEUX sens),
  mais côté MIEN c'est une anti-synergie à gérer. ⚠ **RE-TRIGGERED-AGAINST-ME (seed 70056)** : ArmoriumCherub + normale avec
  mes units adjacents à la cible → chaque tir splash → grosse perte HP ; même PLAY (dégager avant de tirer).
  [n=3, 70000 triggered-against-me / 70007 enemy-side confirm / 70056 triggered-against-me]
- `Aleph-Null Explodes (% maxHP Direct à TOUS les adjacents) + MES units adjacentes à sa mort` —
  **ANTI (friendly-fire propre, triggered-against-me seed 70005)** : Aleph-Null (mon roster) a `Explodes` → à sa mort,
  Dégât Direct à TOUTES les units adjacentes, **sans filtre allié/ennemi** (cf. §1 + gameconfig --trait Explodes). Vécu seed
  70005 : l'explosion a tué un ennemi adjacent (KILL utile) MAIS aussi chunké mes propres corps adjacents = auto-infligé
  évitable. PLAY : **NE PAS coller mes units à un porteur d'Explodes À MOI** s'il peut mourir (même classe que
  Morvenn/Pestillian Explodes) → pré-positionner pour que son splash de mort touche UNIQUEMENT des ennemis.
  [n=1, 70005 triggered-against-me]
- `Corrodius CursedPlagueBell (aura Contagion) + MON Psyker dealant du Psychic DANS l'aura` —
  **ANTI (self-damage Psyker, triggered-against-me seed 70005)** : tout Psyker DANS l'aura Contagion de Corrodius
  **s'auto-blesse à CHAQUE attaque Psychic** (scale niveau ; cf. gameconfig --ability CursedPlagueBell + §2 Corrodius).
  PLAY : **COMPTER ce self-damage avant de spammer du Psychic dans l'aura d'un Corrodius/Nurgle** — acceptable sur un gros
  corps mais à BUDGÉTISER ; idéalement tuer/sortir de l'aura ou frapper depuis HORS aura. ⚠ tension directe quand le Psychic
  est mon seul bypass-block (chaque cast coûte des PV). [n=1, 70005 triggered-against-me]
- `Mataneo deep-strike/HammerOfWrath finish + cible chunkée lointaine → corps isolé bas-PV` — **ANTI
  (triggered-against-me, seed 98001)** : committer le corps deep-strike pour LANDER un finish le pose **isolé**
  (adjacent aux engines ennemis) à bas PV → focus-killé au tour suivant (même pattern 97002/97000/98000). PLAY :
  **NE PAS** finir une cible chunkée avec un héros exposé qu'on pourrait garder en sécurité — utiliser l'auto-Grot,
  une réaction, ou une unité shallow ; OU laisser la cible à bas PV si elle est inerte sans kill (un carry non-amorcé
  à bas PV ne fait qu'une normale absorbable). C'est la moitié PROPRE de H03 violée sous la forme « deep-finish ».
  [n=1, 98001 triggered-against-me]
- `assassin Khorne planqué` (ex. carry `BloodyFury` Chaos) — **ANTI** : ces carries scalent sur
  les **kills mêlée** (Khorne + re-shield) → **NE PAS** le planquer « pour assassiner », il faut
  qu'il combatte ; le cacher = anti-synergie. [cf. wiki §2]
- `Mephiston FuryOfTheAncients (heal-block 2 rounds) → Healer-engine adverse (Nauseous, Isabella…)` —
  **ANTI (anti-Healer/anti-revive)** : après un MOVE de Mephiston, l'AoE Psychic pose un blocage 2 rounds (la cible ne peut
  être healed/repaired/revived/restore Health, cf. §1 Mephiston + gameconfig --ability FuryOfTheAncients) → **arme dédiée
  pour neutraliser un Healer/reviver adverse**. PLAY : après le move-rider, taper la/les cible(s) que le Healer adverse
  voudrait soigner/revive (surfacé en ⚠ critique dans decisionView) → annule le sustain sur ces unités. Coupler avec un kill
  d'engine. [n=1, 98004 chained]
- `Nauseous Healer + TaintedNarthecium-revive + roster 100% Imperial allies` — **ANTI (revive
  structurellement inerte)** : le revive-engine (revive un Chaos adjacent défait) est **INERTE par la composition même**
  quand le Healer est le SEUL Chaos de l'équipe (alliés tous Imperial → aucun Chaos adjacent à revive) → l'engine ne vaut
  QUE par le trait Healer (heal toute faction), JAMAIS par le revive. PLAY : contre ce roster mixte, le Healer reste à tuer
  (heal-block Mephiston + multi-hit overkill vs son Resilient) mais **le revive ne menace jamais** → recon vérifier la
  faction des alliés du reviver au lieu de craindre le revive. [n=1, 98004 avoided]
- `repair-hub Mechanical (Aleph-Null FabricatorClaw/Mechanic/LivingMetal) + AUCUN autre allié Mechanical` —
  **ANTI (engine repair structurellement inerte)** : le repair-engine ne répare QUE des unités **Mechanical/LivingMetal**
  → si Aleph-Null est le **SEUL** Mechanical de SON équipe, son kit entier (FabricatorClawArray + Mechanic + LivingMetal
  repair) **n'a aucun bénéficiaire** = il ne peut que se self-regen, JAMAIS amplifier un allié → réduit à un gros corps soft
  (no-Resilient). MÊME CLASSE que le revive Chaos inerte (98004) : un engine d'amplification est conditionnel à l'existence
  d'une cible valide sur SON équipe. PLAY : au recon, **compter les autres Mechanical/LivingMetal alliés AVANT de craindre
  le repair-hub** ; s'il n'y en a aucun, demote sa menace (carte wiki CRITICAL → LOW) et traite-le en corps soft normal —
  kill au RANGE (Explodes) ; un 2× Flame Brazier l'one-shot (vécu seed 70002, repair jamais utilisé). [n=1, 70002 avoided]
- `MES seuls outils armor-bypass (Exitor CordClaw Direct Pierce100 + Atlacoya Direct) over-étendus T1 + tank MkXGravis
  ennemi` — **ANTI (missed, seed 70008 = ROOT CAUSE)** : quand l'adverse aligne un tank high-armor MkXGravis (Burchard,
  Calgar…) qui DEVIENDRA le wincon late, mes SEULES réponses sont les outils Direct/Psychic/Crit ; les sur-étendre T1 (= les
  exposer au focus de contact) les fait focus-killer AVANT de pouvoir les réserver → le tank devient INGRINDABLE par mon
  roster Power/Physical résiduel = loss structurelle. PLAY : au recon, **identifier le tank MkXGravis comme wincon late
  émergent ET marquer mes 1-2 outils bypass-armure comme PRÉCIEUX À RÉSERVER/PROTÉGER** → les garder SHALLOW/screenés par
  défaut (jamais le move forward T1), les conserver pour cracker le tank une fois les screens tombés. Même famille que
  « réserver l'anti-armor burst » (70004 self-heal, 97002 repair-engine) mais ici le levier = un TYPE de dégât, pas un
  cooldown. (cf. gameconfig --trait MkXGravis double-armure bypass Crit/Direct/Psychic ; --ability CordClaw,
  DaughterOfTheAbyss.) [n=1, 70008 missed]
- `Mephiston FuryOfTheAncients (heal-block move-rider, 2 rounds) + MA brick ToughToKill/healer-dépendante (Dreir…)` —
  **ANTI (triggered-against-me, seed 70051)** : le heal-block 2 rounds de Mephiston (cf. §1 Mephiston + gameconfig --ability
  FuryOfTheAncients) coupe la regen `ToughToKill` ET tout heal externe → un brick floored par Resilient à bas PV devient
  **NON-récupérable ce round** (Resilient floor 1 mais aucune regen pour remonter) → perdu. ⚠ **repose sur H44 (verdict
  Verif=plausible : ToughToKill comme « heal » bloquable via la clause catch-all « otherwise restore Health »)** — la
  composante heal-block est confirmée, l'interaction ToughToKill-bloquable est plausible. PLAY : un brick
  ToughToKill/healer-dépendant face à un heal-block move-rider perd sa durabilité active → le tenir **HORS de la chaîne
  d'adjacence du Psychic move-rider**, ou accepter qu'il devienne un corps à usage unique ; ordre d'application côté MIEN =
  poser le heal-block AVANT de floorer la cible. [n=1, 70051 triggered-against-me]
- `Tjark HuntersBeyondDeath (aura anti-Psyker) INERTE faute de cible Psyker (côté ennemi OU côté moi)` —
  **ANTI (aura inerte, n=2 : avoided seed 70051 + mienne-inerte seed 70055)** : l'aura anti-Psyker de Tjark (+dmg vs Psyker
  + suppression du multi-hit Psyker, cf. gameconfig --ability HuntersBeyondDeath) est **ENTIÈREMENT INERTE faute de cible
  Psyker** → Tjark réduit à un melee plat Physical Pierce1 (no Resilient). MÊME CLASSE que l'engine repair/revive inerte
  (70002 Aleph-Null / 98004 Nauseous) mais portée aux **AURAS ANTI-X** : une aura d'amplification/suppression ne vaut que
  s'il existe une cible/bénéficiaire valide. DEUX DIRECTIONS confirmées : (a) **Tjark ENNEMI vs MON roster sans Psyker**
  (seed 70051) → demote la carte adverse high→low, traite Tjark en corps soft ; (b) **MON Tjark vs un ENNEMI sans Psyker**
  (seed 70055) → Tjark était dead weight sur l'OFFENSE tout le combat (tous bonus gated-Psyker = zéro contribution), réduit
  à un melee low-pen Terrifying-blunté = un effective unit's worth de output perdu dans un endgame damage-starved. PLAY : au
  recon, **COMPTER les Psykers de l'équipe CIBLE (la sienne pour une aura ennemie, l'adverse pour MON porteur) AVANT de
  valoriser un porteur anti-Psyker** → s'il n'y en a aucun, ne PAS slotter/craindre l'anti-Psyker (carte high→low / corps
  soft killable franc). (cf. §1 H11.) [n=2, 70051 avoided / 70055 mienne-inerte]
- `conditionnel d'engine adverse INERTE faute de déclencheur valide (Thoread UnbreakableDuty / Yazaghor WeaverOfFate)` —
  **ANTI (engine/conditionnel inerte, avoided seed 70054)** : EXTENSION de la règle engine-inerte aux **conditionnels
  SCALANTS et triggers d'AMPLIFICATION** — un buff conditionnel ne vaut QUE si son déclencheur PEUT s'armer dans le matchup.
  DEUX cas confirmés ce match : (a) **Thoread `UnbreakableDuty`** exige « 2+ Imperial Characters alliés MORTS » → INERTE car
  Thoread est le SEUL Imperial de SON roster (le compteur ne peut JAMAIS atteindre 2) → demote à plain killable tank ;
  (b) **Yazaghor `WeaverOfFate`** (scale si 3+ ennemis subissent du Psychic dans le tour) → INERTE car aucune source ne
  dealait du Psychic à ses ennemis (= mes units) → demote à fragile Common. MÊME CLASSE que le revive Chaos inerte (98004),
  le repair-hub sans Mechanical (70002), l'aura anti-X sans cible (70051/70055) : un amplificateur/conditionnel est
  conditionnel à l'existence d'un déclencheur VALIDE. PLAY : au recon, **COMPTER les déclencheurs valides d'un conditionnel
  scalant (allié-mort-de-tel-type, ennemi-subit-tel-dégât, bénéficiaire-de-tel-buff) AVANT de craindre son scaling** ; s'il
  ne peut pas s'armer dans CE matchup → demote la menace (CRITICAL/HIGH → MED/LOW) et traite le porteur en corps killable
  normal. (cf. gameconfig --ability UnbreakableDuty, WeaverOfFate.) [n=1, 70054 avoided]

## 6. TODO (savoir non dérivable encore manquant)
- **Sémantique terrain** (Q2 ouvert oracle-plan) : effet gameplay de Swamp / Water /
  glace / feu / Despoiled Ground (LetTheGalaxyBurn) / Contagion tiles. Non observé.
- Seuil exact d'**Overkill** (ratio dmg/PV) — confirmer la formule.
- Interaction `FuryOfTheAncients` (bloque « restore Health ») × `Drachnyen` (SET HP) :
  bloque-t-il le self-heal d'Abaddon ? Non testé.
