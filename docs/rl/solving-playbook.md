# Solving playbook — cas durs (une entree par cas resolu)

Format : **symptome-type -> methode qui l'a craque -> outil/heuristique reutilisable**. Objectif :
que l'orchestrateur resolve SEUL le prochain cas du meme genre. GREP ce fichier AVANT d'attaquer
un cas qui ressemble a une entree existante.

---

## #153 (2026-07-13) — Deux verdicts contradictoires sur une BASE de prediction (flip-flop aura-position)

**Symptome-type** : deux verdicts re-expert "valides" incompatibles sur COMMENT une entree de la
prediction est evaluee (ici : aura d'attaque-stat a la position reelle #67 vs a la tuile candidate
#153) ; historique de flip-flop (#45/#58/#67) ; divergence qui n'apparait que dans une config
particuliere (base haute + cibles blindees) et que chaque camp "explique" par un mecanisme
different (regime blinde per-coup vs position d'aura).

**Methode qui l'a craque** (dans l'ordre, chaque etape a ete decisive) :

1. **Auditer les PREUVES des deux verdicts avant toute nouvelle mesure.**
   - Le test du verdict anterieur (#67, `test_aura_position_live.py`) etait **CIRCULAIRE** : son
     oracle etait `prediction.make_normal_attack_predictions` — **le port lui-meme**. Un test dont
     l'oracle est le code sous test passe QUEL QUE SOIT le comportement natif. Heuristique : pour
     chaque test "live" existant, tracer d'ou viennent les valeurs COMPAREES ; si les deux cotes
     de l'assertion traversent le port, le test ne prouve rien sur le natif.
   - La citation decompile de CHAQUE verdict etait fausse : l'unique `GetStat` de
     `GetAttackHitPrediction @1811af4e0` lit `GetStat(AbilityEntities.Target@+0x10, Health=5,
     Current)` (HP de la CIBLE pour le cap) — ni le "GetStat(Attack) sans position" de #67, ni le
     "GetStat(Attack) du contexte tuile" de #153. Heuristique : **re-deriver soi-meme chaque
     lecture decompile citee** — struct layout via `dump.cs` (`AbilityEntities` TypeDefIndex 11618 :
     +0x10 = Target) + valeur d'enum (`StatType` : 5 = Health, PAS Attack). Une VA citee n'est pas
     une preuve ; l'offset + l'enum le sont.

2. **Construire le cas discriminant qui isole UNE variable, en UNE passe native.**
   - Cle : `decisionView.attackPlans[].evals[].ranked[]` expose deja les predictions natives
     **PER-TUILE-CANDIDATE** (col/row + dmgMin/dmgMax par entree, `maxRank: 99` pour tout avoir).
     => UN SEUL appel `decisionView` donne N mesures ou SEULE la tuile varie : attaquant reel FIXE,
     etat live FIXE, zero risque de mesures correlees entre passes.
   - Verifier l'ETAT au moment de la mesure (pas suppose) : `statModSources` confirme que le
     stat-mod d'aura (+1298, source entite-effet) est bien present sur l'attaquant reel PENDANT la
     passe. Sans ca, "l'aura devrait etre la" reste une hypothese.
   - Comparer chaque ligne native aux DEUX hypotheses offline en ne faisant varier QUE l'entree
     contestee (monkeypatch de `att_pos` dans l'aggregateur d'aura ; tout le reste du pipeline
     identique). Resultat : hypothese A (reelle) 16/29, hypothese B (tuile) **29/29** — les 16
     communs = lignes ou les hypotheses coincident (piege classique du setup non-discriminant :
     si TOUTES les tuiles candidates coincident, on "valide" n'importe quoi).
   - **Chercher la CONVERSE** : le cas le plus probant etait un attaquant SANS le stat-mod a sa
     position reelle (u96 loin du porteur) dont la tuile candidate in-ring GAGNE l'aura
     (base 3011 -> 3909 = +898 RitesOfBattle Basic). Un mecanisme "bake a la position reelle" ne
     peut JAMAIS produire ca. Toujours tester la refutation dans les deux directions
     (perte hors-ring ET gain in-ring).

3. **Lire la fonction DISPLAY native de bout en bout pour le mecanisme** (pas pour "confirmer") :
   la chaine display threade la position candidate comme INPUT explicite —
   `DamagePredictionQuery.GetAllPredictions @181090f50` construit `UnitPosition(tuile de
   selection)` et la passe au service ; `DamagePrediction.PredictNormalAttack @181037cd0` en tire
   `get_MainTile` et la pose comme `CasterTile` dans `AbilityEntities.ctor`. Toute affirmation
   "la position ne sert qu'a la geometrie" etait une deduction jamais lue.

**Outils/heuristiques reutilisables** :
- **Oracle per-tuile gratuit** : `decisionView(maxRank=99, allAbilities=true)` -> `ranked[]` =
  N predictions natives a etat fixe, tuile seule variable. C'est LE harnais discriminant pour
  toute question "cette entree de prediction depend-elle de la tuile candidate ?".
- **Test anti-circularite** : avant de croire un test "live", verifier que son oracle est un RPC
  natif (`decisionView`/`observeBattle`/hook), pas une fonction du port.
- **Verif de citation decompile** : struct offset via dump.cs + enum numerique, systematiquement.
  Les deux verdicts opposes citaient la MEME VA avec deux lectures fausses differentes.
- **Setup discriminant minimal** : les deux hypotheses doivent PREDIRE DIFFEREMMENT sur au moins
  une ligne mesuree (sinon le "PASS" ne tranche rien) — exiger explicitement les deux groupes
  (ici : tuiles in-ring ET out-ring pour le meme attaquant), skip sinon (pattern du nouveau
  `test_aura_position_live.py`).
- **Un fit exact sur un sous-ensemble n'est pas la cause** : #67 collait sur les tuiles in-ring
  (16/29) ; seule la partition complete (29/29 vs 16/29) departage.


---

## #139 (2026-07-16) — Mecanisme transversal invisible du port (ability "does not end turn" : Vindicta, Ragnar, ArmoriumCherub 1014)

**Symptome-type** : une MECANIQUE DE FLUX (pas un scalaire) manque au port — certaines abilities
actives ne consomment pas le tour de l unite alors que le runner offline traite toute action comme
terminale. Aucune divergence chiffree ne la revele (aucun test damage ne casse) : c est un trou
STRUCTUREL du turn-flow, decouvrable seulement en auditant le mecanisme natif de bout en bout.

**Methode qui l a craque** :

1. **Chercher le NOM du concept dans les symboles avant tout decompile large** :
   `search_symbols_by_name("EndTurn")` sort en une passe `ActiveAbilityOperation$$GetSkipEndTurnFlag`
   @180e47120, `AActiveAbility$$SetsEndTurnFlags` @180fb3150 et l override
   `ArcScourgeAbility$$SetsEndTurnFlags` @1811b3d40 — le mecanisme complet etait NOMME. Heuristique :
   les designers nomment les flags d exception (`SkipX`, `SetsXFlags`) ; grep les variantes
   Skip/Sets/Verify/Finish AVANT de fouiller les gros Execute.

2. **Suivre la chaine poseur -> lecteur, pas seulement le poseur** :
   ExecuteInternal @180e44ec0 -> GetSkip*Flag @180e47120/@180e46f60 ->
   AddFlagsAfterAbilityExecution @180e447f0 -> OperationProcessor.FinishUnitTurn @180e081c0 ->
   FinishUnitTurnOperation @180e72140 (UnitFlags 1+3) ; lecteurs : UnitFlagsComponent.TurnEnded
   @180fad510 (= Contains(3)) dans VerifyUnitsTurnFinishedOperation.VerifyUnitTurnEnded @180eded20
   (auto-endturn) et AttackQuery @181054ccc. Sans le cote LECTEUR on ne sait pas ou le port doit
   honorer le flag.

3. **Piege IL2CPP resolu : les overrides constants sont FOLDES (dedup de bodies identiques).**
   Ghidra ne montre que 2 symboles `SetsEndTurnFlags` pour 14 classes overrideuses. Le fold-winner
   `return _dsl.No(+0x118)` @1811b3d40 porte le nom d UNE classe mais 4+ refs vtable ; son sibling
   `return _dsl.False(+0x100)` @1811b3d20 en porte 27. **L inventaire des overrideuses ne peut PAS
   venir de ghidra seul** -> croiser 3 sources : (a) dump Il2CppDumper `symbols.json` (liste
   name-complete des methodes par classe, meme foldees — les RVAs y sont d un autre espace, seuls
   les NOMS/signatures font foi), (b) offsets des champs (`data/symbols.json fields` : DSLFactory
   +0xf8=True/+0x100=False/+0x118=No demasque les constantes retournees), (c) tooltips i2_en.json
   (`grep "not end"`) qui enumerent la famille cote texte AVEC les conditions (FightingRetreat
   conditionnel adjacence). Un body NON foldé restant (= propre symbole ghidra) signale un override
   CONDITIONNEL a decompiler (FightingRetreat @1811de7e0 = Direct(!ennemi adjacent)).

4. **Cas discriminant live a UNE variable via l auto-endturn** : runner 1v1 (`rl_duel build
   --p-units adeptRetributor --a-units necroWarden --board MC1_67`), une seule unite jouable ->
   VerifyUnitsTurnFinished flippe le joueur DES que son unique unite est turn-finished. Mesure :
   cast ArmoriumCherub (1014) -> currentPlayer RESTE 3 et l attaque normale reste jouable (elle a
   ete jouee dans le MEME tour) ; controle : attaque normale (id concret 69) -> flip immediat vers
   4. Deux observations, une variable (l ability castee), zero interpretation.

**Outils/heuristiques reutilisables** :
- **Fold-detector** : refcount/DATA-refs anormalement hauts sur un petit body = fold IL2CPP ; le
  nom du symbole n identifie PAS la classe unique. Inventaire par classe = dump metadata (noms) +
  layout de la factory (constantes) + i2 (semantique), jamais ghidra seul.
- **`SetsEndTurnFlags` retourne un IAbilityTrigger (noeud DSL), PAS un bool** : les overrides
  conditionnels s expriment en arbre evalue avec `AbilityEntities` au moment du cast (aucun
  parametre caster requis a la construction). Chercher le type de retour dans il2cpp_full.json
  avant d interpreter le decompile.
- **Auto-endturn 1v1 = oracle de turn-flow gratuit** : toute question "cette action consomme-t-elle
  le tour ?" se tranche en 2 casts sur un runner mono-unite (flip vs non-flip de currentPlayer).
- **`aiMovableTiles` honore les UnitFlags** (`GetMovableTilesFor(unit, ignoreUnitFlags=false)`) :
  second discriminant dispo sans nouveau hook.
- **Un port de FLUX doit poser les flags pour les abilities NON portees aussi** (le natif les pose
  independamment de la behaviour) -> table d overrides par ability_type dans `abilities/base.py`,
  distincte du registre des behaviours.


---

## #184 (2026-07-16) — Ratio uniforme ~1.49x sur l attaque normale d UNE unite (bloodMephiston) : la factorisation du total etait FAUSSE, la cause etait une aura d equipe ENNEMIE non portee

**Symptome-type** : sur-prediction UNIFORME (meme ratio sur toutes les cibles) de l attaque normale
d UNE seule unite ; le ratio "colle" a une factorisation seduisante (3/2 hits = 1.5 ~ 1.49) qui
oriente tout le monde vers le mauvais etage (selection d arme) ; le fix nait (current-pos) FIXE le
cas mais REGRESSE d autres seeds -> flip-flop. Deux "refutations" successives etaient elles-memes
fausses : la premiere (worldExecutions bit-exact => pas de modifier manquant) testait une unite qui
ne franchissait pas le GATE (profil Power vs aura Psychic-only) ; la seconde (hit-count 3 vs 2)
factorisait un scalaire sous-determine.

**Methode qui l a craque** :

1. **Ne JAMAIS accepter une factorisation d un total unique.** 2016,3024 se decompose en
   2x[806,1210]x1.25 (hits=2) ET en 3x1003x1.25x[0.8,1.2]x0.67 (hits=3, x0.67) — indiscernables
   sur UNE mesure. Discriminant : le champ `appliedHits` du struct natif (aiPredict/`ranked[]`) +
   la RELATION min/max (spread +-20% => max/min = 1.5 STRUCTUREL, pas un indice de hits).

2. **Sweep par tuile AVANT de croire une hypothese positionnelle** : `aiPredict {col,row,fresh:true}`
   sur les 27 tuiles movable en une boucle = carte native complete. Ici : total IDENTIQUE sur ~25
   tuiles (adjacentes ou pas, Delta-elev 0..3) => la cause est position-INDEPENDANTE => exit toutes
   les hypotheses adjacence/elevation/arme d un coup. (Meme harnais que #153 ranked[], en plus dense.)

3. **Chercher le facteur par PAIRE (attaquant, cible), pas par attaquant** :
   `combatSnapshot.normalAttack` (paire vs ALLIE au deploiement) = 3009,4515 SANS le x0.67 ;
   vs les ennemis = x0.67 partout. Un facteur present vs une equipe et absent vs l autre = effet
   d EQUIPE (aura defensive), pas un attribut de l attaquant. La pseudo-refutation "l autre
   attaquant est bit-exact" ne vaut RIEN si son profil de degat ne franchit pas le gate (Power vs
   Psychic) : refuter un modifier exige un temoin qui FRANCHIT toutes les conditions du modifier.

4. **Identifier le porteur via les effets du ROSTER, pas ceux de la cible** : les cibles ne portaient
   RIEN ; `decisionView.effects` du porteur (Atlacoya) listait `DaughterOfTheAbyss_FriendlyDmgReductionPct`
   — nom auto-descriptif. i2 (« Psychic Damage dealt to other friendly units within 2 hexes ... is
   reduced by 33% ») + gameconfig (`dmgReductionPct[L50]=33`) ont scelle magnitude/portee/gate en
   une lecture. x0.67 mesure = 33% EXACT.

5. **Le mecanisme d application etait deja RE'd ailleurs** : la boucle state-wide « TOUS les
   EffectWithTarget actifs x leurs cibles » de `CalculateDefenderModifiersForPrediction @181002c30`
   etait documentee dans case-68. GREP les case-docs pour le COLLECTEUR avant de re-decompiler :
   un malus peut atteindre la cible sans jamais figurer dans SA liste d effets (TargetSelector du
   porteur, ex. SurroundingFriends rayon 2).

**Outils/heuristiques reutilisables** :
- **Anti-sous-determination** : pour tout ratio "rond" (1.5, 0.67, 0.75), enumerer TOUTES les
  factorisations compatibles (hits, pct-mods, base alternative) puis choisir la mesure qui les
  separe (champ appliedHits, sweep par tuile, paire vs allie). Un fit numerique exact sur un cas
  n est pas la cause (deja le piege de #153).
- **`combatSnapshot.normalAttack` = temoin hors-aura gratuit** : la paire vs ALLIE au deploiement
  donne la prediction native SANS les effets d equipe adverse -> isole les modifiers "vs ennemi".
- **Refutation valide = temoin qui franchit le gate** : avant d ecarter "modifier manquant" parce
  qu une autre unite est bit-exacte, verifier profil de degat / trait / equipe / portee du temoin
  contre CHAQUE condition du modifier suspecte.
- **Auras defense-side** : familles `Create*MalusForDefense` + `CreateTargetSelector` projettent
  HORS du porteur ; le port les modelise cote SOURCE (canal `create_aura_defense_damage_malus_for_ally`,
  aggregateur `aura_defense_damage_malus_from_units`, #184) — symetrique de SITW (attaquant) et
  RitesOfBattle (base). Toute divergence "la cible n a aucun effet qui explique X" doit declencher
  le reflexe : scanner les effets des AUTRES unites (les 2 equipes).
- **Latents a ne pas perdre** (documentes case-184, hors perimetre) : `MovementUtil.AreTilesAdjacent
  @18109d740` = voisinage && |Delta-elevation| < 2 (le port n a pas le gate elevation) ; la selection
  d arme native retombe sur MELEE hors portee ranged (FindRangedWeapon null -> FindMeleeWeapon).

## #49x / tache #10 (2026-07-21) — Flip-flop sur le COMPTE d'une utilite NC (Gauntlets 1000) : deux "validations" incompatibles etaient les projections d'UNE regle a DEUX ANCRAGES

**Symptome-type** : une heuristique de compte (utilite playbook, selecteur DSL) validee deux fois
avec deux regles INCOMPATIBLES, chacune reproductible sur SON board/config (ici : "ring-1 seul"
35/35 sur MC1_67 vs "l'arc dist<=2 compte" admis par le natif sur C1_25) ; chaque camp a une
grille de mesures propre qui "prouve" sa regle ; la difference visible entre les configs (board,
elevations) suggere de fausses pistes environnementales (murs, LoS, epsilon).

**Methode qui l'a craque** :

1. **Chercher la variable CACHEE qui differe entre les deux corpus de mesures, pas un mecanisme
   de plus.** Ici : dans TOUTES les mesures "ring-2 mort", la position evaluee etait une tuile
   BALAYEE != la tuile reelle du caster (sweep ncEvaluate) ; dans la mesure "ring-2 vivant", le
   caster etait IMMOBILE (reel == balaye). Des qu'on liste cote a cote les configs avec la colonne
   "reel vs balaye", la reconciliation saute aux yeux : la regle est `util(T) = |ring1(T) UNION
   disque2(TUILE REELLE)|` — chaque camp n'avait vu qu'une degenerescence (disque(reel)=vide ->
   "ring-1 seul" ; reel==T -> "arc(T)"). C'est le pattern #153 (position d'evaluation) applique a
   un SELECTEUR : **quand deux regles rivales collent chacune a son corpus, suspecter que
   l'ANCRAGE (quelle tuile/entite/etat) differe entre les mesures, pas la formule.**
2. **Le decompile revele l'ancrage dans les NOEUDS DSL, pas dans la formule.** La chaine
   `EvaluateNonComparable @18113e5a0` construit le contexte avec `MainTile(position balayee)` ;
   MAIS les deux sous-selecteurs ne consomment PAS le meme noeud racine : `AdjacentTiles(
   CasterTile@+0x168)` (= tuile du CONTEXTE -> suit le sweep) vs `SurroundingEnemies(Caster@
   +0x160)` (= ENTITE -> `GetMainTile(entite)` dans l'etat ECS -> tuile REELLE). **Heuristique
   reutilisable : dans tout arbre DSL evalue en position hypothetique, tracer CHAQUE reference
   au caster jusqu'a son noeud (+0x148 Owner / +0x158 Actor / +0x160 Caster / +0x168 CasterTile /
   +0x170 CasterTiles / +0x178 Target, cf. runner-engine.md:660) : `Caster` et `CasterTile` n'ont
   PAS le meme referentiel pendant un sweep** (`CasterTileSelector.Select @180ee49b0` lit
   ctx.tiles ?? ctx.tile AVANT le fallback entite ; `CasterSelector.Select @180ee47d0` rend
   l'entite). Un selecteur "surrounding/adjacent/nearest" bati sur l'ENTITE est T-independant.
3. **Lire les FLAGS reels du call-site avant de croire un filtre.** La conclusion falsifiee
   ("SurroundingTiles ne rend que des tuiles vides") venait d'une lecture de l'iterateur sans
   ses arguments. Le filtre `IsEmptyOrSteppable` de `TileQuery.<IterateSurroundingTiles>d__6
   @1810ae1b0` est CONDITIONNEL (`dc+0x50`) ; le call-site Gauntlets passe 0 -> OFF. **Remonter
   la chaine ctor -> champs -> MoveNext en suivant les VALEURS (ici SurroundingTiles(...,0,0) ->
   ctor @180ef65c0 -> slot 0x65 args) ; un flag=0 n'est pas un filtre actif.** Piege gshared :
   les offsets de champs different entre le ctor et le MoveNext decompiles (instanciations
   generiques distinctes) — se fier a l'ORDRE des stores, pas aux offsets absolus.
4. **Craft discriminant sur TERRAIN PLAT pour tuer les echappatoires environnementales.** Les
   regles rivales invoquaient l'elevation/LoS ; en placant les crafts sur une zone tout-plat
   (MC1_67 rows 7-8 elev 1), tout blocage "obscured" est impossible PAR CONSTRUCTION -> le
   resultat ne peut trancher que l'ancrage. Ensuite seulement, un craft dedie (crete elev 4)
   valide le predicat obscured isolement (positif craft-O + controle craft-O2).
5. **Valider position-par-position, pas au best.** `ncEvaluate sweep` + comparateur port-vs-natif
   sur CHAQUE position balayee (probe_49x `measure_vs_port`) : un accord "au best" peut masquer
   deux erreurs qui se compensent dans l'argmax ; l'accord par-position sur 17-32 tuiles par
   config est la preuve forte. Et verifier la NON-VACUITE du cote positif (imprimer le set
   non-vide natif : un "PASS tout-vide vs tout-vide" ne prouve rien).

**Outils/heuristiques reutilisables** :
- `probe_49x_realanchor.py` : pattern complet build-roster-custom (`--p-units/--a-units`, 1vN,
  floor controle) + driving multi-tours generique (`drive()` : moves legaux + cycles endturn ;
  `refresh_turn()` : rendre la main au caster AVANT mesure — 3 joueurs, p3=environnement, sinon
  le sweep se reduit a l'origine) + `measure_vs_port()` (accord par-position).
- `bq.surrounding_enemies` / `bq.eligible_targets_count` / `bq.is_target_tile_obscured` :
  primitives mirrorees reutilisables pour les 11 autres abilities a terme `Unobscured`
  (Boltstorm, Doombolt, HeroicFusillade, ... cf. case-49 §3) et tout futur selecteur
  "surrounding" — en se rappelant que l'ancrage (entite vs tuile-contexte) se lit au NOEUD.
- Gate d'eligibilite par-position : `GetEligibleTargetsSelectable(unit, MainTile(T)) @18111ed80`
  vide -> bucket vide MEME si util >= floor ; l'eligibilite dist-1 n'a PAS la porte d'elevation
  du ring-1 utilite (prouve E1-repro (0,2), |Delta-elev|=2 adjacent quand meme eligible).

---

## #39 (2026-07-22) — « Gate per-JOUEUR » de 1180 HeroicFusillade : un A/B 4-experiences reproductible etait un CONFOND avec une variable temporelle (turnsStarted), pas un mecanisme

**Symptome-type** : un verdict comportemental « le natif discrimine par CAMP/joueur » appuye par
plusieurs experiences A/B live reproductibles (swap de camps = flip du comportement), alors que la
lecture decompile ne trouve AUCUNE branche per-player dans la chaine ; le port a fige l'artefact en
gate `team == 1` ; une ability soeur (1191, meme classe de playbook) ne montre PAS l'asymetrie.

**Methode qui l'a craque** :

1. **Lire la chaine ENTIERE avant d'inventer un mecanisme : si tout est player-blind, suspecter
   l'EXPERIENCE, pas le code.** Chaine relue de bout en bout (VAs) : `RunComputerActionsOperation
   @180e93e80` -> `AiControl.GetAi @180ffc270` (PlayerType 0 ET 1 -> MEME instance +0x20 ;
   `AiControl.Init @180ffc460` : 2 paires (AiQuery+DefaultPlayerStrategy+WithSomeRandomness), la
   #2 reservee a PlayerType 4) -> `DefaultPlayerStrategy.<CalculateNextActionForUnit>d__7
   @1810c0c10` (seule reference absolue au camp : un bool `GetCurrentTeamId != 1` passe au LOG
   `AILog.AIActions..ctor` — ecran debug, pas un gate) -> `DefaultAiUnitTactic..ctor @1810eebc0`
   (generateurs ordonnes : dict NC par priorite {1000,100,0,-100,-1000} +0x40, comparables +0x38,
   movement dernier ; premier generateur a action non-nulle GAGNE) ->
   `ActiveAbilityActionGenerator.<GenerateActions>d__7 @18119a3f0` (gates per-ability :
   HasFlag(unit,2=ActiveAbilityUsed), Contains liste, IsAbilityBlocked, get_CanCurrentlyBeUsed
   @180f8fdb0 (+0x28 canStillBeUsed && !+0x35 disabled && cooldown+0x2c && ammo+0x38/+0x40),
   IPlaybook slot4 ShouldEvaluate(unit) / slot5 (unit,positions) / slot6 per-position / slot7
   Evaluate) -> `HeroicFusilladePlaybook.EvaluateNonComparable @181144510` (gates RELATIFS :
   HasTrait(cible,Hero) + IsEnemy(surrounding, CASTER) — symetriques sous swap). ZERO branche
   PlayerType hors Environment. => le « per-joueur » ne POUVAIT pas etre un mecanisme de code.

2. **Chercher la variable CONFONDUE avec le camp dans les experiences.** Lister pour chaque
   experience historique la valeur des variables NON controlees : ici, TOUTES les mesures
   « a-units n'emet pas » etaient au 1er tour de l'unite (walks courts : le camp a-units joue
   2e => son tour 2 est ~2x plus loin en pas), et TOUTES les emissions p-units etaient au tour
   >= 2. Le slot-4 `ShouldEvaluate(unit)` de 1180 (corps folde @18111af90, decouvert en #46
   APRES le verdict case-31) = `GetStat(unit, 0xc=TurnsStarted) > 1` : il predit EXACTEMENT la
   partition observee. **Heuristique : un A/B « camp swap » ne controle PAS le temps — le camp
   determine l'ORDRE de jeu, donc tout gate temporel (turnsStarted, cooldown initial, once-per-N)
   est structurellement correle au camp dans un walk court.**

3. **Croiser avec le contre-exemple de la famille** : 1191 MartialInspiration (meme classe
   NonComparablePlaybook) emet cote team 2 (case-52 #57f) => la famille NC marche pour les
   a-units ; ce qui distingue 1180 n'est pas le camp mais SON slot-4 (1191 n'a pas le gate
   turnsStarted). Un « mecanisme per-X » qui ne s'applique qu'a UN membre d'une famille homogene
   est presque toujours un attribut du membre, pas de X.

4. **Rejouer l'experience historique en MESURANT la variable suspecte** (`probe_39b_tscounter.py` :
   walk natif 909/MC1_67 avec dump `combatSnapshot.stats.turnsStarted` de TOUTES les unites a
   CHAQUE pas). Confirmations : a s10 (verdict historique) ts(Judh)=1 -> bloque ; au tour 2 de
   Judh les autres a-units passent a 2 (le compteur est bien per-player-turn symetrique,
   `StartTurnOperation.Execute @180ea3fb0` ++ `UnitComponent.turnsStarted@+0x58` sur les
   `CurrentlyOwnedUnitIds` du joueur courant) mais ts(Judh) RESTE 1 (effet de bord du 1202
   VigilanceEternal caste SUR lui) -> bloque encore, ce qui explique pourquoi meme un walk long
   sur CE seed n'aurait jamais montre l'emission a-units.

5. **Craft discriminant a UNE variable** (`probe_39c_crafted.py`) : Judh SEUL cote a-units,
   2 necroWarden p-units PILOTES par le probe (tenus adjacents = gate2 garanti, immobiles),
   AUCUNE source d'interference sur le compteur (pas de Kyrus/1202). Resultat : au tour 2
   (ts=2), le natif emet `move+1180->79` DEPUIS LE CAMP A-UNITS => H_perplayer refutee par
   contre-exemple direct. Fix : suppression du gate `_is_player_side` du port (le slot-4
   turnsStarted, deja porte via `_turns_started_gate` + lecture live du compteur par pas,
   suffit) ; agreements re-valides : 909 s10 HIT (69->93), 909 tour-2-Judh ts-colle HIT
   (pas d'overfire), 31337 s6 HIT (1180->79 p-units), crafted HIT (1180->79 a-units).

**Outils/heuristiques reutilisables** :
- **Anti-confond temporel des A/B camp-swap** : avant de conclure « per-joueur », verifier que
  les deux bras de l'A/B sont mesures au MEME numero de tour de l'unite (turnsStarted egal), au
  meme etat de cooldown/ammo, et que le walk est assez long pour voir le 2e tour du camp qui
  joue en second. `combatSnapshot.stats.turnsStarted` par pas = le compteur gratuit.
- **probe_39c pattern « adversaire scripte »** : pour tester une decision du camp AI, piloter le
  camp p-units a la main (moves scriptes + finish, jamais l'IA) pour construire/maintenir la
  precondition geometrique (ici : paire de cibles adjacentes), et laisser le natif decider en
  face. C'est le complement cote a-units du levier « swap --p-units/--a-units ».
- **Un gate slot-4 se mesure au COMPTEUR, pas au calendrier** : l'increment de turnsStarted peut
  etre SAUTE pour une unite (mesure : cible d'un 1202 VigilanceEternal reste a ts=1 pendant son
  2e tour) -> tout port du gate doit lire le compteur LIVE (stat 12) et non « numero de round ».
- **La seule reference absolue au camp dans toute la chaine IA = un flag de log** (`AIActions
  ..ctor(unit, now, teamId != 1)` @1810c0c10, consomme par l'ecran debug AILogScreen) : si un
  futur cas exhibe une vraie asymetrie per-camp cote decision, elle ne peut venir QUE de l'etat
  (compteurs, effets, geometrie), pas du routage IA.


---

## #38b (2026-07-23) — Un gate NC qui « contredit le decompile » + un summon « inerte en runner » : DEUX symptomes, UN artefact d'observation (mauvais visualId de summon)

**Symptome-type** : (a) un gate playbook (ReachedSummonCap/DoctrinaImperatives 1118) emet la ou NOTRE
reconstruction refuse, sur un modele 3-branches pourtant re-confirme au decompile ; deux sous-termes
suspects, dont un herite d'un lot de RE deja refute (slot 0x51 « GetAdjacentUnits », meme lot que le
faux per-player #39). (b) COUPLE : une behaviour (summon ControlEdict) semble ne JAMAIS s'executer en
runner alors qu'elle est validee live ailleurs. Les deux sont en fait le MEME bug de MESURE : le port
ET la sonde comptaient les summons par le mauvais nom -> 0 enfant vu -> cap toujours False (a) ET
« aucun summon » (b).

**Methode qui l'a craque** (dans l'ordre) :

1. **Resoudre les slots d'interface par la VTABLE LIVE, pas par un verdict RE anterieur.** Un
   call-site `FUN_180003bd0(0x51, itfDAT, service, caster)` dispatche le slot 0x51 d'IBattleQuery.
   Le RPC `resolveVtableSlot` (lecture pointeurs de l'Il2CppClass, ZERO invoke) dumpe la vtable de
   `BattleQuery` ; **ancrer sur un slot CONNU** (0xc9 = ReachedSummonCap @181070f60, verifie) donne
   la base d'interface, d'ou tous les autres slots par offset. Verdict : slot 0x51 =
   `GetFreeAdjacentTiles` (1 param), PAS `GetAdjacentUnits` (3 params from/friendsOf/enemiesOf) — la
   signature du call-site (1 argument) suffisait deja a REFUTER l'ancien verdict. Heuristique :
   **le nombre d'arguments du dispatch (`FUN_180003bd0`=1 param apres this, `FUN_18000c1b0`=plusieurs)
   contraint la surcharge ; un slot « tout camp » a 3 params ne peut pas etre un dispatch a 1 arg.**
   Corroborer avec un autre port qui consomme deja le meme slot (`aggressive_onslaught.py` avait
   deja slot 0x51 = free tiles) — deux ports contradictoires du MEME slot dans le code = drapeau rouge.

2. **Desassembler le gate au niveau instruction (capstone) pour figer le CONTROLE DE FLUX**, pas
   se fier au pseudo-C de ghidra. `read_bytes` @VA + capstone : le `jle cb1d` (free-count <= 0 ->
   saute au bloc emit) vs `test al,al; je` (ReachedSummonCap faux -> return) donne les 3 branches
   EXACTES : `count==0 -> ssi Conqueror ; count>0 & free==0 -> emit ; count>0 & free>0 -> ssi cap`.
   Les deux branches d'emission pointent le MEME bloc `GenerateAction(Fix64(100))` -> valider UNE
   branche live valide l'autre par construction.

3. **Oracle natif de gate GRATUIT : `ncEvaluate(unit, ability, sweep=false)`** invoque la leaf
   `Evaluate(unit,pos)` du playbook et rend le bucket (emit + util). C'est la VERITE-TERRAIN du gate,
   step par step, sans hook neuf. Confronter le port `_should_emit` a cette leaf sur CHAQUE step de
   l'unite (14/14) tranche « le port suit-il le gate ? » independamment du downstream (once-per-turn,
   ordre generateurs).

4. **A/B a UNE variable pour la CAUSATION (pas la correlation).** Le gate emettait a count>0 la ou
   nos DEUX modeles (adj-units ET free-tiles) predisaient « cap gate -> pas d'emission ». Plutot que
   re-fitter, construire l'A/B qui isole le cap : MEME tuile, MEME count, free>0 dans les deux bras,
   seul le nombre de summons change (0 -> cap False ; 5+ -> cap True). Resultat : emission flippe avec
   le cap SEUL -> causation prouvee. Bonus : a free=6>0 le bras « 0 summon » n'emet PAS -> refute
   d'un coup le modele « adj==0 -> emit » ET confirme que le mirror free-adj est fidele (le natif voit
   aussi free>0). C'est le pattern #153/#184 (isoler une variable, tester la converse) applique a un
   gate booleen.

5. **Quand « 0 observe » alors que le mecanisme est valide ailleurs : suspecter le NOM, pas le
   mecanisme.** Le summon ControlEdict porte `constants.unitId = admecSmnVanguard` (cle KIT) mais son
   `visualId` LIVE (ce que `observeBattle`/`decisionView` exposent) = `admecNpc1Vanguard`. Compter
   par la cle -> 0 match -> « inerte ». Le comptage par TOUS les visualId (probe) a revele 7 summons
   bien reels. **Le test sibling `test_control_edict_live` documentait deja `SUMMON_VIS` (cle) vs
   `SUMMON_LIVE_VIS` (visualId)** — GREP les tests/docs de la behaviour avant de conclure « ne
   s'execute pas ». Fix principled : resoudre `constants.unitId -> gameconfig.unit(...).visualId`,
   jamais coder le nom en dur.

**Outils/heuristiques reutilisables** :
- **`resolveVtableSlot` + ancre-slot-connu** = LA facon de resoudre un slot d'interface (0x51, etc.)
  contre un verdict RE douteux : lecture pointeurs pure, aucun invoke, aucun reinject. Un slot mal
  attribue par un ancien lot de RE (surtout le lot qui a deja produit un verdict refute) est
  PRIORITAIRE a re-verifier.
- **Signature du dispatch = filtre de surcharge** : `FUN_180003bd0(slot, itf, obj, arg)` = 1 arg
  managed apres this ; toute surcharge candidate a >1 param managed est exclue d'office.
- **`ncEvaluate(sweep=false)` = oracle de gate per-step** ; le confronter au `_should_emit` du port
  sur toutes les decisions de l'unite isole le gate du downstream (once-per-turn, ordre generateurs).
- **A/B « cap » a tuile+count fixes** (`probe_38b_capAB`) : pour tout gate a seuil (cap, cooldown,
  stacks), driver la VARIABLE DE SEUIL seule (ici : faire attaquer l'unite N fois pour accumuler des
  summons) en gelant la geometrie -> causation, pas correlation. Bra « seuil bas » DOIT montrer le
  non-emit (sinon le seuil n'est pas le determinant).
- **`constants.unitId` (cle KIT) != `visualId` (identite LIVE)** : tout comptage/identification d'un
  summon/spawn dans `obs_units`/`decisionView` DOIT passer par `gameconfig.unit(unitId).visualId`.
  Reflexe : si une sonde compte « 0 » d'une entite censee exister, imprimer TOUS les visualId presents
  avant de conclure a l'absence.
- **GetChildrenCount (ParentComponent, append-only, morts inclus) ~ compte `obs_units` du visualId
  du summon SANS filtre isDead** (obs garde les depouilles) : fidele tant qu'aucun summon n'est
  RemoveUnit-ed (retire du board != mort).

---

## #217 (2026-07-23) — Port combat d'une ability AoE + un residu "gate non decode" tranche par replay-diff hydrate

**Symptome-type** : ability active NO-OP silencieuse en combat (absente d'ABILITY_CLASSES) qui
cumule plusieurs sous-systemes (pose d'effets de TUILE + attaque multi-cible + effet gate par trait),
ET un residu documente d'un case anterieur ("struct de flags natif non decode -> gate conservateur
aligne i2") qui devient ACTIF avec le nouveau port : deux lectures du decompile s'opposent (pas de
noeud IsNormalAttack visible dans la formule vs struct +0x14 copiee non decodee).

**Methode qui l'a craque** :

1. **Resoudre l'overload EXACT par xref du call-site, pas par le nom du symbole.** Le decompile de
   l'ExecuteBehaviour affiche `AttackWithAbilityDamage` — il y a 4 overloads homonymes + 4
   `AttackWithAttackDamage`, et le PORT distingue crit/block vs degat-direct sous ces deux noms.
   `list_xrefs` sur chaque overload -> le call-site (18120cdfc) tombe sur @180de9dd0 = LE MEME
   overload que SpiritLeech (deja bit-exact via `execute_ability_attack`) -> pipeline tranche par
   ANCRE (une ability deja validee qui appelle le meme noeud), sans re-RE le behaviour.
   Les overloads minces delegue au core (@180de9e50) : decompiler le CORE pour la classe construite.

2. **Un selecteur natif manquant = nouveau PRIMITIF + nouvelle CAPACITE de contexte, pas un helper
   imperatif.** `UnitsOnTilesWithEffect @180dffc50` n'existait pas cote port ; le mirror = classe
   selecteur (structure du decompile : predicat effectType@+0x20 + FromTrigger) + un champ
   `DslContext.tile_has_effect` wire par `entities_from_state` sur `state.effects` (meme cle tile-id
   que la pose case-35). Pattern reutilisable pour tout predicat d'etat non expose au DslContext :
   capacite nommee + degradation [] documentee si absente.

3. **Trancher un "gate non decode" = replay-diff avec l'effet HYDRATE, en 2 scenarios qui isolent le
   confond d'hydratation.** Piege specifique : `decisionView.effects` est IsActive-filtre -> un effet
   conditionnel INACTIF au capture (ici : LordOfTempests_ExtraDamage sans glace ring-1) n'est PAS
   hydrate offline -> un "match" offline==live peut etre un artefact (les deux sans bonus pour des
   raisons differentes). Discipline : (a) creer la PRE-CONDITION avant le capture (round 1 : attaque
   normale qui pose la glace via le passif deja valide ; round 2 : DRIVE adjacent a la glace ->
   effet actif -> hydrate), (b) IMPRIMER l'etat d'hydratation (`has_lot`, count_pre) pour rendre le
   datapoint interpretable, (c) le verdict = l'ECART CHIFFRE exact (offline-sans-gate - live =
   extraDmg x hexes x hits, au point pres) — pas un booleen. Ici : natif +0 avec effet actif et 3
   hexes glaces -> gate normal-only CONFIRME cote combat, fix = threader `is_normal_attack=False`
   dans le vecteur ability attaquant (symetrique du #112 defenseur).

4. **La zone de diff du replay se compare en DELTAS, pas en absolus** : une tuile deja glacee
   pre-cast ne reapparait pas dans les NOUVELLES poses (gate already-present des deux cotes) ->
   asserter `new_live == new_offline` + `cible in (new | pre)`, jamais `cible in new`.

**Outils/heuristiques reutilisables** :
- **Ancre-par-overload** : avant de RE un noeud d'attaque/degat, xref l'overload du call-site et
  chercher une ability DEJA PORTEE bit-exact sur le meme overload -> le pipeline est herite, pas
  re-derive.
- **Table des selecteurs de contexte DSLFactory** (runner-engine.md : 0x148 Owner, 0x160 Caster,
  0x168 CasterTile, 0x178 Target, 0x190 TargetTiles...) : lire les `*(ctx+0x...)` du decompile
  DIRECTEMENT contre cette table — plus rapide et plus sur que re-deriver chaque slot.
- **Probe replay-diff bit-exact (pattern case-35/probe_217)** = LE discriminant des gates de
  modifiers : meme etat + meme rng -> tout ecart est un modifier manquant/en-trop, et son MONTANT
  identifie l'effet responsable (400 x count x hits ne peut etre que LordOfTempests).
- **Walk de garde qui caste l'ability** (31337 step 11) : `engine_agreement_stages --build --seeds
  31337` valide en une passe le port ET son aval (steps suivants EXACT = pas de divergence d'etat
  compensee).

---

## rngcrit-1202 (2026-07-24) — « Crit-roll fantome » : desync de CONSOMMATION RNG entre attaque normale et attaque d'ability multi-coups a cc=0

**Symptome-type** : deux mesures live « validees » qui se contredisent sur la consommation RNG du
MEME pipeline partage — « cc=0 => 0 tirage crit, 18/18 » (attaque normale) vs « 6 tirages pour
3 coups a cc=0 = 1 crit-roll par coup » (ability #220/#205) ; residu de degat ~1% multi-coups,
coup 1 quasi-exact, coups >=2 desynchronises. Piege classique : attribuer le tirage surnumeraire
a la mecanique la plus connue (le crit) au lieu de le LOCALISER.

**Methode qui l'a craque** :

1. **Decompiler le GATE avant de theoriser l'« eligibilite ».** L'unique chemin crit du per-coup
   partage (`AttackDamageOperation.ExecuteHit @180e5eff0`, slot 0xa) est
   `DamagePrediction.RollCritical @1810387a0` : `cc<1 -> return false SANS tirage`.
   `DamageCalculations.RollCritical @1810057b0` (NextBool brut, sans gate) n'est atteint QUE
   derriere ce gate — deux fonctions homonymes, UNE seule porte le gate : citer la mauvaise VA
   fabrique un faux verdict. A cc=0 il n'existe AUCUN chemin natif qui consomme un tirage crit,
   quel que soit le vecteur. L'« eligibilite crit par ability » se materialise par cc=0, pas par
   un flag qui changerait la consommation.

2. **Enumerer les POINTS DE TIRAGE du per-coup partage et leurs gates** (pas « qui tire », mais
   « qui PEUT tirer et sous quelle condition ») :
   - `HitDamage.GetDamage @181007bf0` sur le struct d'entree — gate `min==max -> 0 tirage` ;
   - crit slot 0xa — gate `cc<1` (+ bypass crit-garanti byte+0x2c/buff slot 4 : crit SANS roll) ;
   - `RandomlyResolveMinMaxDamage @181038600` (slot 8) — **SANS AUCUN gate** (largeur 1 = 1 tirage
     quand meme) ;
   - block/evade dans la sub-op 0x42 (apres le resolve — prouve par #72 valeur-puis-block).
   La difference normal-vs-ability est alors une difference de DONNEES, pas de code : l'attaque
   normale arrive avec un struct DEGENERE (0 tirage GetDamage, le resolve EST la valeur) ; l'ability
   bounds-mode arrive avec [minDmg,maxDmg] (GetDamage = la valeur BRUTE, le resolve degenere est
   GASPILLE). => 1 vs 2 tirages/coup a cc=0, meme code.

3. **Panel de modeles candidats confrontes au MEME etat MT dumpe** (l'arme decisive) : dumper le
   MT pre-cast (`dumpRng`), poser 3-4 modeles de consommation/valeur (port actuel, crit-then-value
   aux impairs, value-then-waste aux pairs...), calculer le per-hit de CHACUN offline depuis des
   clones du MEME etat MT, et comparer au per-hit LIVE extrait des events. Le vrai modele matche
   A L'UNITE tous les seeds ; les faux divergent des le coup 2. Les modeles « crit-roll a cc=0 »
   (valeur aux tirages impairs) sont REFUTES par la donnee, pas par l'argument.
   - Per-hit LIVE robuste = deltas `UnitStats_RemainingHealth` des events step-4 d'`applyAction`
     (JAMAIS le delta HP post-action : une attaque normale FINIT le tour et `LivingMetalRepair`
     resoigne la cible -> delta 0 trompeur).
   - A/B anti-confond : MEME attaquant (custoKyrus : 3-hit normal ET ability 1202 3-hit), MEME
     cible, seule la VOIE change.
   - Piege d'outillage : `--hp-target/--hp-player` ZERONT FixedArmor -> reduce identite -> les
     modeles roll-then-reduce/reduce-then-roll deviennent indistinguables. Discriminer le
     PLACEMENT de la reduction exige une cible a armure reelle SANS override (orksWarboss 2609 ;
     eviter templAncient : machine + pool d'armure = confonds).

4. **Le fix n'est PAS uniforme : la factory DSL native choisit l'OPERATION.** Deux factories
   homonymes cote gameplay, deux operations, deux consommations :
   - `DSLFactory.AttackWithAttackDamage @180de9fb0` (+@180dea180/350/520/6b0) ->
     `AttackDamageBehaviour` -> `AttackDamageOperation.ExecuteHit` -> 2 tirages/coup (cc=0) ;
   - `DSLFactory.AttackWithAbilityDamage @180de9c90/@180de9dd0 -> core @180de9e50` ->
     `AbilityDamageBehaviour` -> `AbilityDamageOperation.ExecuteHits @180e2a860` (GetDamage/coup,
     `CalculateAbilityDamage @18102cb50` = 0 RNG, PAS de resolve) -> 1 tirage/coup.
   **Classifier chaque ability portee par les XREFS de son `ExecuteBehaviour` natif** (une requete
   `list_xrefs` par factory rend la liste complete d'un coup) — JAMAIS au juge ni au nom du
   commentaire de port (PlasmaGrenade etait mal etiquete « AttackWithAttackDamage » alors que ses
   xrefs pointent @180de9c90). Porte par `native_factory="attack"|"ability"` sur la feuille
   Python + `is_attack_damage_op` dans `execute_ability_attack`/`_run_hits`.

5. **Validation adversariale qui a ATTRAPE une regression du fix lui-meme** : apres le fix
   inconditionnel, rejouer le probe multi-hit de L'AUTRE famille (`probe_217_stormcaller`, 3-hit
   AttackWithAbilityDamage) — FAIL post-fix / PASS pre-fix (A/B par `git stash`) => le tirage
   gaspille devait etre conditionnel. Sans ce test croise, le fix aurait ete un sur-ajustement
   inverse. Les carriers 1-hit (SpiritLeech, ThunderousAssault) ne discriminent RIEN en
   consommation : chercher le porteur MULTI-HIT de chaque famille.

**Outils/heuristiques reutilisables** :
- **`probe_rngcrit_1202.py`** : gabarit du panel-de-modeles (dumpRng + clones MT + variantes +
  per-hit events + PORT reel) — adaptable a tout probleme de consommation RNG.
- **Brute-force (lo, W) des bornes live** : avec le MT dumpe, enumerer `g_i = genrand>>1` et
  resoudre `v_i == lo + (g_i mod W)` sur 3 coups -> identifie les bornes du modulo natif SANS
  connaitre le pipeline (confirme lo=2010/W=1005 = bornes reduites du port).
- **Compter les tirages par delta `mti`** (`dumpRng` avant/apres, wrap 624) = le verdict de
  consommation le moins cher ; les VALEURS disent ensuite QUELLE position porte quoi.
- **Un « N/M draws » anormal n'est PAS forcement la mecanique suspectee** : localiser le point de
  tirage par gates (etape 2) avant de nommer le coupable.
- ~~Residu detecte au passage, HORS scope : off-by-one (+1) valeur-dependant sur les DEUX vecteurs
  a armure>0 (rounding pierce/armure, ex. port [918,903,1112] vs live [919,904,1113]) ; et
  `execute_normal_like`/amount-mode + fire-DoT (EnvFireTile) ont une consommation NON mesuree.~~
  **LES TROIS POINTS SONT PERIMES** (re-mesure 2026-07-28, `case-38-offbyone-armor-materialization.md`) :
  - l'off-by-one n'etait PAS un gap de percage -- l'attribution « rounding pierce/armure » de cette
    note visait le MAUVAIS ETAGE. Le defaut float de `StaticBattleRules.Damage$$GetDamageWithPiercing`
    est de signe OPPOSE (`port = natif + 1`) et fermé par #30a. Le vrai etage etait la MATERIALISATION
    finale, `IdunBattle.Core.Services.DamageCalculations$$CalculateBaseDamageWithModifiers` :
    `Fix64.Round(Mul(v, multiplier), AwayFromZero)`, que le port TRONQUAIT. Ferme par #131 (vecteur
    normal) puis par la campagne HeavyGravCannon (vecteur ability bounds-mode). Re-mesure sur le
    montage d'origine : port bit-exact **24/24 coups**, les deux vecteurs, a cc=0 ET cc>=1. PREUVE
    DIRECTE : remis en troncature, le port REPRODUIT le symptome -- `1112` est litteralement une
    cellule tronquee. Garde : `tests/engine/runner/test_offbyone_armor_38_live.py` ;
  - `execute_normal_like` / mode `amount` : consommation MESUREE par R6 (live == arrondi 30/30) ;
  - `EnvFireTile` : traite par #143 (route `AbilityDamageOperation` ; la mention « numeriquement
    equivalent » du backlog y a ete REFUTEE, 100000 vs 25000 mesure).

  Ce que cette note enseigne, du coup, vaut plus que le residu qu'elle signalait : **un residu note
  « au passage » herite de l'attribution de celui qui l'a vu, pas d'une mesure.** Elle a nomme un
  etage plausible (le percage, qu'on venait de regarder) au lieu de l'etage reel, et cette
  attribution a survecu telle quelle jusqu'a ce qu'on la re-mesure.


---

## #45f (2026-07-24) — Ratio constant "explique" par le MAUVAIS mecanisme (x1.5 attribue a crit-on-Ice, c'etait l'elevation)

**Symptome-type** : divergence live/offline en RATIO CONSTANT par coup (ici 1.5000 exact, DidCrit=0),
ATTRIBUEE a un effet plausible narrativement (GFA glace avant de frapper + i2 "The Crit Damage bonus
of the Ice is already applied") alors que la formule decompilee de cet effet CONTREDIT la mesure
(crit-only + proportionnelle a CRIT_DAMAGE=0 -> devrait etre 0). La "contradiction decompile vs live"
n'etait PAS une bizarrerie native a elucider : c'etait le signal que l'ATTRIBUTION etait fausse.

**Methode qui l'a craque** :

1. **Une contradiction formule-vs-mesure se resout en CHERCHANT UN AUTRE COUPABLE, pas en forcant la
   formule.** Le decompile de `IceEffect.CreateEffectDamageBonusForAttack @180f44940` est sans
   ambiguite : trigger `AttackDamageIsCritical & AreEqual(Units(occupants-tuiles-effet), target@0x178)
   & op_LogicalNot(HasTrait(target, 0x19))`, addition `PercentageOf(StatAmount(attacker@0x160,
   10=CRIT_DAMAGE), EffectConfig(5)=25)`. Tous les canaux du EffectBonus sauf ADDITION sont zero.
   Si la mesure dit +50% sur des coups non-crit avec cd=0, ce n'est pas "l'attaque devient critical
   pour l'Ice" (le flag crit REEL per-coup est injecte au ctor AbilityEntities dans ExecuteHit
   @180e5eff0 — verifiable en 5 min de lecture) : c'est un AUTRE etage qui produit le +50%.

2. **Inventorier les multiplicateurs POSITIONNELS avant d'accuser un effet.** Un x1.5 exact sur
   CHAQUE coup, insensible au crit, = un canal percent du builder de mods attaquant. Le builder
   PARTAGE `CalculateAttackerModifiersForPrediction @181000590` inline l'elevation
   (`CalculateElevationBonusModifier @181003ea0` : gate strict `elev(att) > elev(cible)` +
   `!HasEffect(0x423)` DEUX cotes, valeur = config `Damage.ElevationBonus` = 50) + trench. Le
   confond etait PARFAIT : le scenario de test movait l'attaquant sur `ranked[0]` qui PREFERE le
   surplomb -> 1.5x systematique et REPRODUCTIBLE ; et l'attaque normale de CONTROLE du meme caster
   passait par le chemin offline qui applique DEJA l'elevation -> "pas de divergence" -> l'ecart
   semblait specifique a l'ability -> attribution a l'Ice. **Heuristique : un cas de controle qui
   "passe" ne disculpe une variable cachee QUE si les deux vecteurs la traitent PAREIL offline** —
   ici le fork de port (elevation appliquee au vecteur normal, absente du vecteur ability) rendait
   le controle aveugle.

3. **Sonde discriminante = bouger LA variable suspectee, positions FORCEES** (`probe_45f_gfa_elevation`,
   patron reutilisable) : meme build/seed, `applyAction move` place cible et attaquant sur une paire
   de tuiles adjacentes choisie dans `boardGraph` par relation d'elevation (high/flat/low). Resultat
   pre-fix : high = live 1.5000x offline A ROLLS PRNG IDENTIQUES (les 4 valeurs offline de high ==
   celles de flat, meme seed -> la divergence est UN multiplicateur, pas une derive RNG) ; flat/low
   = bit-exact (gate strict `>`). Post-fix : bit-exact partout. **Heuristique : quand le ratio est
   exactement constant ET les rolls identiques, chercher un multiplicateur d'etage, jamais une
   difference de consommation RNG.**

4. **La formule crit-only se valide en FORCANT le regime** (`rl_duel build --crit 100,700`) : chaque
   coup crite -> delta live vs offline-sans-le-terme = +175 = floor(700 x 25/100) CONSTANT (delta
   flat, ratio variable -> canal ADDITION, pas multiplicateur), et bit-exact une fois
   `ice_crit_damage_addition` porte (position pipeline = flat PRE-reduce, meme foyer que le crit
   flat #75/#91). Gate Immune : AUCUN porteur spawnable (pool rank 17) -> validation OFFLINE par
   toggle du trait dans l'etat replay (inject "Immune" -> l'offline perd exactement 175/coup crit
   = le gate est cable dans le pipeline reel) ; la face native du gate reste decompile-only.
   Datapoint "cible non-glacee + crit" = les tests crit existants (test_damage_crit_live, cc=100
   cd=500, aucune glace) : bit-exact SEULEMENT si le terme Ice rend 0 hors tuile glacee.

5. **Asymetrie de FAMILLE mesurable en une paire de sondes** : ATTACK ExecuteHit @180e5eff0 =
   RollCritical (slot-10) + builder mods COMPLET (slot-4, elevation/trench incluses) ; ABILITY
   ExecuteHit @180e29d50 = `AttackHit(..., isCrit=0)` SANS roll + ctx mods attaquant ZEROE (aucun
   builder) -> pas d'elevation, pas de crit, JAMAIS. Mesure : storm_high (Stormcaller surelevee,
   famille ability) = live == offline sans elevation 3/3 ; scrit (--crit 100,700) = live
   crits=[0,0,0]. **Patron : le gate par famille de factory native (`is_attack_damage_op` =
   native_factory != "ability") est la frontiere correcte pour TOUTE feuille positionnelle/crit
   du builder attaquant.**

**Outils/heuristiques reutilisables** :
- **"Ratio exact + rolls identiques" => multiplicateur d'etage manquant** ; croiser avec la liste
  des feuilles du builder @181000590 (elevation, trench, charge, aura, ...) AVANT d'accuser un effet.
- **Verifier qu'un controle est reellement discriminant** : lister ce que chaque vecteur offline
  applique (grep apply_* dans les DEUX chemins) ; un fork de port rend les controles croises muets.
- `probe_45f_gfa_elevation.py` / `probe_45_shared_bonus.py` (commites) = patrons de sonde
  positions-forcees par relation d'elevation, reutilisables pour toute feuille positionnelle.
- Famille effect-damage-bonus (`Effect.CreateEffectDamageBonusForAttack`, collecteur
  `BaseEffect.DamageBonusForAttack @180f0f5e0`) : lire le EffectBonus par CANAL
  (trigger/multiplicator/addition/subtraction/minimum/override) — l'additif ungated
  (AvalancheOfMuscle etc.) et l'addition crit-gated (Ice) coexistent au MEME foyer pipeline ;
  porter le canal + son trigger, jamais un scalaire fitte.


---

## #47 (2026-07-24) — Buffs RANGED du caster absents des attaques d'ABILITY + « crit-rng desync » fantome (MortisRound 3.15x)

**Symptome-type** : une attaque d'ABILITY d'un porteur de buff ranged (trait HeavyWeapon /
RangedSpecialist) sort LIVE a un multiple stable de l'offline (x1.25 / x1.5 / x1.875 selon le cas),
ET un carrier (MortisRound) montre un ratio composite « inexplicable » (~3.15x) attribue par
hypothese a un desync crit-rng per-hit. Deux etages MELANGES dans une seule mesure.

**Methode qui l'a craque** :

1. **Le gate manquant etait un TROU DE THREADING de contexte, pas une formule.** Le natif evalue
   chaque effet contre le MEME contexte d'attaque per-coup (`BaseEffect.DamageBonusForAttack
   @180f0f5e0` recoit l'AbilityEntities : caster/cible/ability declenchante/arme) quel que soit le
   VECTEUR. Le port ne passait ni `is_ranged` ni l'ability declenchante dans
   `execute_ability_attack` -> tout bonus gated `IsRangedAttack` rendait None pour TOUTE attaque
   d'ability. Fix = threader `is_ranged` (derive d'`is_melee` deja present) +
   `trigger_ability_type` (= le param `ability_type` deja route par les leaves) dans
   `attacker_modifiers`, au MEME point et sous le MEME **gate famille** que les feuilles
   positionnelles #45f (famille ATTACK seulement ; ability-family = mods attaquant VIDES).
   **Patron : quand un bonus d'effet manque sur UN vecteur, chercher d'abord quel CHAMP DU
   CONTEXTE natif ce vecteur ne threade pas — la collecte est partagee, seuls les args divergent.**

2. **La clause x2 est un amount CONDITIONNEL au niveau du noeud DSL, hardcode sur UN id.**
   `HeavyWeapon_ExtraDmgEffect.CreateDamageModifier @180f4f030` = `ForPercentIncrease(OwnerIsCaster
   & IsRangedAttack & flags, ConditionalAmount(TriggeringAbilityIs(AbilityOrEffect(0x3ec=1004
   MortisRound)) ? Multiply(base, Direct(2)) : base))`, base = ConfigConst 0xf =
   heavyWeaponExtraDmg=25. 0x3ec est le SEUL id du decompile ET le seul « applies double » de l'i2
   (grep i2_en.json : 1 occurrence) -> le x2 n'est PAS un trait generique, c'est une clause
   per-ability. Vehicule offline : `att_ctx["trigger_ability_type"]` (le contexte positionnel #35
   SERT de struct AbilityEntities du port — y ajouter un champ = mirror, pas un hack).

3. **Demeler un ratio composite = mesurer la CONSOMMATION RNG, pas fitter le ratio.** MortisRound
   live 15256 vs offline 4837 (~3.15x) : `dumpRng` avant/apres le cast -> mti +2 SEULEMENT
   (= tirage valeur + resolve slot-8). AUCUN tirage crit -> l'hypothese « crit-rng desync »
   REFUTEE par comptage, sans debat. Le reste etait : x1.5 (HeavyWeapon double) sur l'attaque
   (4837->7256) + un delta FLAT de 8000 = ceil(80000 x 10%) -> **KNOCKBACK de collision du push
   BLOQUE** (`ApplyKnockbackTo @180e67fc0`, residu slice-21b flagge dans displace.py). La cible
   etait au bord -> push hors-board -> degat de collision agrege dans le MEME hpDelta que
   l'attaque. **Patron : delta = A*ratio + B*flat se separe en bougeant UNE variable qui n'affecte
   que B (ici --hp-target : 80000/50000/30001/8536 -> extra 8000/5000/3001/854 = ceil(max x 10%),
   le point 30001->3001 discrimine le Ceiling Fix64 a l'unite).**

4. **Knockback porte en mirror structurel, constante mesuree FLAGGEE.** Chaine native :
   `Execute @180e685a0` (dest nulle OU IsFilled) -> `ApplyKnockbackTo @180e67fc0` (gate
   IsTargetable) -> (iface DAT_183287ef8, slot 0xf) == `DamagePrediction.GetKnockback @181032760`
   (gates IsDisplaceable + !HasTrait(0x19=25 Immune)) -> `CalculateKnockbackDamage @1810040f0` =
   int(Fix64.Ceiling(maxHealth x cfg@+0x24/100)) via sub-op 0x42 (part bouclier d'abord, 0 rng,
   pas reduit par l'armure — datapoint armure 4461 : kb plein 854). ⚠ la cle BC
   `Damage.KnockbackPercentage`=20 NE matche PAS la valeur effective 10 (4 datapoints) -> champ
   DTO @+0x24 non resolu (dump.cs absent) -> `_KNOCKBACK_PCT=10` HARDCODE-mesure documente.
   Occupant ennemi du pousseur = knockback AUSSI (branche IsEnemy) ; contre-cas anti-sur-
   application : push LIBRE -> zero knockback (mortis-free bit-exact 7256).

5. **Pieges de MESURE live qui fabriquent de faux verdicts** (tous rencontres ici) :
   - cast HORS-TOUR : applyAction repond ok:true mais `mutated:false` -> degats SIMULES puis
     REVERTS dans le meme stream d'events (boucle endturn-jusqu'au-tour-caster obligatoire) ;
   - cible a REGEN (necroWarden LivingMetal) : si l'ability FINIT le tour, le tick de regen tombe
     DANS le stream du cast -> lire `min(serie UnitStats_RemainingHealth)`, pas la derniere ;
   - `observeBattle` est STALE juste apres un applyAction -> le degat live per-coup se lit dans
     les EVENTS (tags UnitStats_RemainingHealth), pas dans observeBattle ni `changes` (absents
     sans push) ;
   - le gate no-move de HeavyWeapon impose un caster JAMAIS deplace -> deplacer la CIBLE pour
     crafter distance/elevation (spawn elev 3 de MC1_67 surplombe des tuiles elev 2 a portee 3).

**Outils/heuristiques reutilisables** :
- `probe_47_ranged_ability_buffs.py` (commite) : patron « caster fixe au spawn + cible deplacee
  par relation d'elevation + assertion hpDelta ET mti » — 5 cas dont 2 regimes discriminants
  (x1.25 plat / x1.875 surplomb depuis la MEME valeur brute 1342) et 1 contre-cas famille
  (SpiritLeech = famille ABILITY -> +33% RangedSpecialist ABSENT live ET offline).
- **mti-delta = arbitre des hypotheses RNG** : compter les tirages live d'un cast (dumpRng x2)
  avant de postuler un roll fantome ; 1 comptage refute/confirme plus vite que tout fit.
- **Ratio compose (x, +flat)** : varier `--hp-target` en 3 points dont un NON-rond (30001) pour
  epingler a la fois la base (maxHealth), le pourcentage ET le mode d'arrondi (Ceiling).

---

## #419-r1-tr14-r5-r2-r1-r2-r1-r1 (2026-08-04) -- Un port DESARME un gate parce qu'une donnee manque, alors que la branche en cause ne LIT PAS cette donnee

**Symptome-type** : natif et port rendent le MEME verdict (refuse/accepte) mais **nomment une regle
differente**. L'accord sur le verdict masque un desaccord sur la CAUSE. En amont, le port porte un
`return None` global (« je ne sais pas decider ») declenche par l'absence d'UNE donnee -- ici
`unit_weapon_range` non observable pour les 81 unites sans arme du gameconfig.

**Ce que ce patron a de traitre** : le `return None` est ecrit comme une degradation PRUDENTE, il est
meme documente comme telle -- alors qu'il est PERMISSIF, donc exactement le trou qu'un entrainement
irait exploiter. Et il ne casse AUCUN test, puisqu'il ne fait que ne rien faire.

**Methode qui l'a craque** :

1. **Enoncer la question binaire AVANT de mesurer** : « la donnee manquante est-elle LUE par la
   branche qu'on desarme ? » -- et dire ce qui ferait conclure l'inverse. Ici : une ecriture du
   drapeau derivee de la valeur, ou une lecture de la valeur dans la branche du drapeau.
2. **Lire les ECRITURES du drapeau dans le producteur, une par une.** `TargetingQuery$$GetRange` :
   `onlyAdjacent` est pose AVANT toute resolution d'arme, puis seulement FORCE a vrai par deux
   conditions qui ne lisent pas la valeur non plus. **Zero dependance** -> le desarmement est faux.
3. **Lire l'ORDRE des tests dans le CONSOMMATEUR.** `GetInvalidTargetReason` teste
   `range._4_1_ OnlyAdjacent` en PREMIER, et `(int)range` n'apparait que dans l'autre branche. Le
   desarmement doit donc descendre A L'ETAGE QUI LIT LA DONNEE, jamais rester en amont.
4. **Ne PAS generaliser aux etages voisins sans les relire** -- c'est le piege symetrique, et il
   etait arme ici : `TargetingQuery$$GetTilesInRange` consomme le MEME retour mais teste
   `(int)range < 0` puis `== 0` AVANT `OnlyAdjacent`. Son `None` sur donnee manquante est donc
   CORRECT, et « corriger par symetrie » l'aurait casse. **Deux consommateurs d'une meme valeur
   peuvent lire ses champs dans un ORDRE different : la question se repose a chaque appelant.**
   Un cran de test interdit desormais l'alignement.
5. **Chiffrer le rayon AVANT/APRES par balayage** (catalogue x jeux d'options), avec trois compteurs
   distincts : gagnes, PERDUS, et **inchanges sur le regime ou la donnee EST observable** (ce
   dernier est le garde-fou anti-debordement -- 58 867 couples ici, 0 bouge).
6. **Separer le MAJORANT du REEL** : le produit cartesien apparie chaque jeu d'options a toute
   unite. Le rayon reel (porteur x SES abilities) valait 57, pas 1 620.

**Le piege du montage, et comment en sortir** : sur le porteur naturel, une AUTRE regle rattrapait
deja le verdict en aval (`TargetMatchesDynamicRule`, bit `0x2` du masque) -- donc le montage evident
ne prouvait que la CAUSE. **GREFFER une variante SANS ce bit** (ici `PoundThemToDust` ->
attaque normale `1126`, masque `0x4000`) transforme la mesure : la baseline y ACCEPTE (`0x0`) ce que
le natif REFUSE. **Heuristique : quand un gate corrige est masque par un gate aval, chercher dans le
registre natif une variante qui n'ARME PAS ce gate aval, et greffer celle-la.**

**Le piege du garde-fou** : le probe de chiffrage raisonnait sur un MODELE du port. Sous mutation
(`return None` remis), il restait VERT -- inventaire deguise en garde. Le cran
`accord_modele_code` APPELLE la vraie fonction sur un `State` synthetique minimal (une unite,
une tuile, un owner) et confronte 4 000+ couples : la contre-epreuve passe alors de 1 rouge a 2.
**Un chiffrage qui ne rappelle pas le code ne garde rien.**

**Outil reutilisable** : `probe_419r1tr14r5r2r1r2r1r1_range_only_adjacent.py` (balayage + accord
modele/code + cran anti-symetrie) et `probe_419r1tr14r5r2r1r2r1r1_only_adjacent_live.py` (deux bras,
dont un GREFFE pour demasquer le gate aval). Baseline exacte a moindre frais : substituer l'attribut
de MODULE (`T.get_range`) par un wrapper qui reproduit l'ancien contrat -- en capturant la vraie
fonction A L'IMPORT, sans quoi le wrapper s'appelle lui-meme.

---

## #437-r1-r1-r3 (2026-08-04) — « la PREDICTION native ignore la face attaquant » : `aiPredict` ne mesurait pas le coup qu'on croyait

Symptome herite, presente comme une divergence de MODELE entre vecteurs : sur les memes entrees
d'etage, le COMBAT rend `(1130, 1695)` et `aiPredict` rend `(904, 1356)` = `Round(P x 0.25)`,
face attaquant `HeavyWeapon_ExtraDmg` totalement absente — attaquant pourtant JAMAIS deplace et
effet PRESENT dans la liste d'effets. **Il n'y avait aucune divergence.**

1. **`aiPredict` n'est l'oracle du coup DEPUIS LA TUILE COURANTE que sous condition, et la
   condition est LISIBLE.** `DamagePredictionQuery$$GetAllPredictions` remplit son dictionnaire en
   DEUX regimes : `GetPredictionForTargetsReachableFromSelectionTile` (cibles valides depuis la
   tuile de selection — prediction A cette tuile, puis les cibles sont RETIREES) et
   `GetPredictionForTargetsUnreachableFromSelectionTile` (les autres — boucle sur le MOVABLE SET,
   prediction a une AUTRE tuile, arbitrage `BetterDamagePrediction`). Le piege est documente dans
   la docstring meme du RPC (`rpc-predict.ts`, piege 3) et il avait ete lu sans etre applique.
   **La garde qui vaut : `abilityTargets(unit, ability).fromHere` contient la cible.** Sans elle,
   une lecture hors portee decrit un coup APRES DEPLACEMENT.
2. **Le lien entre « autre tuile » et « bonus perdu » est UNE seule primitive** :
   `SimulateEffectsOperation$$DoActionInSimulatedTile` appelle le MEME
   `UnitExtensions$$SetMovedFlag` que `MoveUnitOperation$$Execute` des que la position simulee
   differe de la position courante (RE deja au dossier, #266, `prediction_has_moved`). Donc
   `Moved` REEL (l'attaquant a marche) et `Moved` SIMULE (lecture hors portee) ferment le MEME
   gate `!HasFlag(Moved)`. **Deux « pieges de montage » distincts n'en font qu'un** — les chercher
   comme un seul mecanisme evite d'en corriger un et de retomber dans l'autre.
3. **Patron generalisable : quand un canal d'OBSERVATION a un mode DEGRADE silencieux, la garde
   doit porter sur la condition d'entree dans le mode nominal, pas sur un symptome.** Ici la garde
   « `HeavyWeapon_ExtraDmg` est dans les effets » passait dans les DEUX modes degrades. La mesure
   directe (`--attacker-moves` : un pas qui CONSERVE la distance) montre l'effet toujours pose,
   la cible toujours en portee, l'armure toujours armee — et le bonus disparu.
4. **Le discriminant a coute UN run** : balayer la variable suspecte (ici la distance) et lire la
   grandeur A CHAQUE PAS dans le MEME run, plutot que comparer deux runs. `d=5 -> (904, 1356)`,
   `d=3 -> (1130, 1695)`, meme attaquant, meme tuile d'attaquant, meme armure. Un seul parametre
   bouge, donc aucune attribution n'est a debattre.
5. **Retombee inattendue, et c'est la plus utile** : une fois la lecture prise dans le regime
   nominal, `aiPredict` reproduit les TROIS cellules de #437-r1 (`1130/1695`, `1132/1697`,
   `1135/1702`), dont la cellule DISCRIMINANTE 4538. La loi « un `Round` par face » etait etablie
   par INVERSION du PRNG sur le combat ; elle l'est desormais aussi par un canal INDEPENDANT.
   **Reparer un montage rend souvent un second temoin gratuit — le chercher avant de conclure.**

**Outils/heuristiques reutilisables** :
- `probe_437r1r3_prediction_attacker_face.py` (commite) : sweep par distance avec garde
  `fromHere`, contre-epreuve `--attacker-moves` (un pas a distance CONSTANTE isole le gate `Moved`
  de la question de portee), `--shot` (tir reel depuis l'etat mesure + inversion des bornes).
- **Montage overwatch en deux phases** : faire ENTRER le porteur en portee et lui faire ENCAISSER
  le tir (PV eleves), puis ne plus rien bouger et ceder la main jusqu'au RE-ARMEMENT des trois
  conditions. La voie « un spectateur purge le tir d'abord » ne converge pas : le spectateur ne
  peut pas purger tant qu'il est hors de la zone de menace, et le montage cale hors portee.
- **Ne jamais lire une prediction a distance 1** : le natif y prend l'arme de MELEE et tout bonus
  gate `IsRangedAttack` disparait — troisieme voie vers le meme faux negatif.
