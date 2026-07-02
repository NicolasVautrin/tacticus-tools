# Validation du moteur Python — méthodologie de référence

> Consolidé le 2026-07-02 depuis CLAUDE.md, les mémoires projet et les design docs
> ([playbook-engine.md](playbook-engine.md), [runner-engine.md](runner-engine.md)).
> C'est LA référence citée par les rôles d'agents (`re-expert`, `validator`).

## 0. Principes transverses (non négociables)

- **L'oracle est toujours le natif qui tourne.** Jamais de fixtures figées, jamais
  de « expected = 4443 » codé en dur : on recalcule l'attendu depuis le live au
  moment du test. Les assertions sont génériques (sur toutes les unités présentes),
  indépendantes du seed ET de la version du jeu.
- **Séparation sémantique/comportement** : le décompilé ghidra = vérité pour la
  SÉMANTIQUE (formules, structures, ordre d'évaluation) ; le live valide le
  COMPORTEMENT (agreement) — il ne sert jamais à découvrir/fitter une formule.
- **Rebuild obligatoire avant chaque run d'agreement** : le harness MUTE les
  runners (`python rl_duel.py build --seed <s>` avant chaque `engine_validate`).
  Un build sans `--keep` NUKE silencieusement les runners frères → un seul acteur
  sur le live pendant une passe de validation.
- **Warmup inconditionnel** après chaque (re)inject, avant tout RPC/probe
  (`warmupGameSingletons({force:true})`, autonome). Aucune exception, même pour
  les probes « self-contained » sur seed BC disque.
- **État dynamique refreshé par step comparé** : boucliers ET armure se lisent dans
  un `combatSnapshot` frais (débuffs type PowerTrip_ReduceArmor) — une capture
  froide au step 0 fausse les prédictions des steps suivants.
- Exécution : `python` (pas `py`), depuis `scripts/python`, stdout ASCII only
  (cp1252). Tests ciblés de la tranche touchée — JAMAIS la suite complète sans
  demande explicite.

## 1. Couche PRÉDICTION / DÉCISION (playbook)

**Objet** : reproduire la décision native — (ability, cible, tuile) — et les
prédictions de dégât/utilité qui la fondent.

**Harness principal : `engine_validate.py`** (agreement décisionnel)
1. Build frais : `python rl_duel.py build --seed <s>` → runnerId.
2. La bataille avance pilotée par l'IA NATIVE, step par step.
3. À chaque step comparé : le moteur calcule SA décision depuis l'état live
   (`decisionView` + `combatSnapshot`) et on la compare à la décision native.
4. Métriques : **ability match** (n/N), **positioning exact** et **≤1hex**.
   Référence courante : seed777, 24 steps.

**Sous-couche numérique : `predict_validate.py`**
- Compare les prédictions elles-mêmes (dmin/dmax par cible, coups, killSure/kill)
  aux `DamagePrediction` natives.
- Ground truth par-coup : traces AllMods (`scorerAllModsTraceDump` et famille
  `scorer*TraceDump`, cf. rpc-api.md) — à utiliser pour trancher un per-hit,
  PAS pour deviner une formule (la formule se lit dans le décompilé).

**Interpréter un miss** (ordre de suspicion validé par l'historique) :
- **TARGET-miss** (même ability, mauvaise cible) → fidélité de la prédiction
  PAR-CIBLE (modifier défenseur, hits conditionnels, AoE set), pas une feuille
  d'utilité manquante.
- **POSITION-miss ~1hex** → scoring de mouvement (MovementSuggestion) ou gate
  positionnel (ex. HeavyWeapon no-move).
- **ABILITY-miss à utilités proches** → tie-break (Bucket = argmax strict,
  premier énuméré ; liste FINAL = [normale, spéciales…]).
- Toujours descendre au probe ciblé (trace par (tuile, cible)) avant de toucher
  au moteur : un miss d'agreement est un symptôme, pas un diagnostic.

## 2. Couche ACTIONS (runner)

**Objet** : mutations d'état exactes — actions → operations → ECS → cascade
(événements, triggers, effets).

**Méthode : replay-diff vs live.** La même action est appliquée côté moteur Python
et côté runner natif, puis on diffe l'état complet (HP, positions, effets, flags)
après chaque apply. Pour le dégât, la validation est **bit-exact** : l'ordre RNG
natif (crit → block → split) est porté, pas approximé.

**Tests live par tranche** : `scripts/python/tests/engine/*_live.py` (non commités,
choix projet) — conftest `live_session`/`rpc`/`live_runner`, init = warmup-si-besoin.
Chaque tranche portée a son/ses tests (move, damage paliers 1..3, crit/block
bit-exact, effets/triggers, ActOfFaith, summons, turn flow, boucliers, Battle
Fatigue, CrushingClaws…). Après une modif : relancer les tests de la tranche + un
test de garde par dépendance partagée impactée, pas plus.

## 3. Scénarios craftés (généralisation — l'étage anti-sur-ajustement)

Un agreement mono-seed ne prouve pas un mécanisme : le projet a tenu des semaines
sur un 20/20 porté par DEUX bugs compensatoires (Harvester pierce-0 + armure
summon manquante). L'étage 3 construit des cas que le fix n'a jamais vus :

- **Choisir les porteurs** avec `unit_map.py` (index requêtable des 669 unités :
  armes/hits/pierce, traits, abilities) — on SÉLECTIONNE l'unité qui exerce le
  mécanisme, on ne seed-hunt pas.
- **Crafter le roster** avec `buildPatchedRunner({aiUnits:["unitId:level",…],
  templateOverrides})` : la condition testée doit être remplie ET stable —
  garder l'unité observée vivante (adversaires faibles/peu nombreux), éliminer le
  bruit (un mécanisme à la fois), garantir une occasion d'agir (cible atteignable).
  Driver les positions si la géométrie compte (une unité qui ne fait que bouger
  survit indéfiniment) — ne jamais « blâmer la géométrie de spawn ».
- **Probes ciblés mécanisme** : comparer la sortie moteur vs native pour CETTE
  config (ex. le set AoE exact d'un cast), pas l'agreement global. Les scripts
  paramétrés (`--seed`, roster, mécanisme) rejoignent l'outillage réutilisable.

## 4. Qui valide quoi (rôles du harness d'agents)

| Rôle | Ce qu'il fait | Ce qu'il ne fait PAS |
|---|---|---|
| `re-expert` | RE + port + **smoke-check** (un seed) pendant l'itération | Prononcer l'acceptance de son propre fix |
| `validator` | 3 étages : conformité statique (VAs↔code), reproduction from scratch, généralisation craftée. **Gate le commit.** | Être l'auteur du fix ; corriger le code jugé |
| orchestrateur | Briefs, lecture critique, arbitrage RE↔validator, commit (sur demande utilisateur) | Valider à la place du validator |

Exclusion mutuelle sur la session Frida pendant toute passe de validation.

## 5. Trous connus (état 2026-07-02)

- **Couverture pilotée par les tranches** : un mécanisme jamais exercé par un
  seed/test peut être silencieusement faux (leçon GetStuckIn : les 6 hits de u90
  manqués faute d'avoir reconné le kit complet). Réflexe : reconner le kit ENTIER
  du porteur (gameconfig + i2), pas seulement les effets capturés.
- **Prédiction non-dégât** (heal/repair/effet — tâche #37) : pas encore de brique
  d'agreement dédiée.
- **Agreement décision historiquement mono-seed (777)** : la généralisation
  multi-seed/multi-roster est institutionnalisée par le validator mais son
  historique est récent.
- **Non modélisé / non mesuré** (documenté dans le code) : HeavyWeapon/
  RangedSpecialist sur les prédictions de SPÉCIALES (régression observée quand
  appliqué naïvement — à trancher par trace AllMods sur un cast spécial d'un
  porteur), cap de dégât du hit bonus MasterAnnihilator, constante +1/event
  d'utilité normale (sans impact argmax connu).
- **Antériorité hexgeo** : toute validation d'adjacence/AoE antérieure au fix de
  parité hexgeo (2026-07-02) est suspecte et à re-dériver au besoin.
