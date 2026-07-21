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
