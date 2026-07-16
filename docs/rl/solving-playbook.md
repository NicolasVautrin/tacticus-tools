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
