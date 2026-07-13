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
