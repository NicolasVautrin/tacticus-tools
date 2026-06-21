# Boucle d'auto-progression — oracle Tacticus

But : **progresser au jeu** en **conservant l'expérience dans des FICHIERS** (jamais le
contexte), via un cycle `explorer → hypothèse → valider → promouvoir`.

## Règle d'or — contexte borné
- Tout le durable = **fichiers** : `journal.md` (épisodique), `hypotheses.md` (provisoire),
  doctrine = `.claude/skills/tacticus-battle/SKILL.md` §6/§7 + `docs/rl/wiki.md`. Le transcript est **jetable**.
- **1 match = 1 sous-agent éphémère** : il lit doctrine + hypothèses, joue 1 match (ses ~N
  round-trips + gros game-states vivent dans SON contexte), écrit l'entrée `journal.md`, et
  ne renvoie qu'un **résumé compact** (issue, tags, deltas H, promotions proposées). Son
  contexte **meurt avec lui**.
- L'**orchestrateur** (/loop) ne voit jamais un game-state brut — juste les résumés. Les
  **métriques** vivent dans ce fichier (§Métriques), relues, pas tenues en contexte.

## Modes de match
- **EXPLORE** (seed aléatoire) → découvrir des failure modes → nouvelles hypothèses.
- **VALIDATE** (rejouer un seed précis) → test **contrôlé** d'une hypothèse : même matchup,
  on ne change QUE le comportement visé → preuve **causale**, ≫ n=1 aléatoire.
  - À vérifier empiriquement : le seed fixe les rosters ; le RNG de combat est-il aussi
    déterministe ? (rejouer mêmes actions → même résultat ?) Si oui = counterfactual parfait.

## Abandon (coût + contexte) — prudence ASYMÉTRIQUE
- **PERDU** : dès que je ne peux plus atteindre/contrer leur win-condition → concède, `L`. (Libéral.)
- **GAGNÉ** : seulement si léthal **certain avant** le leur → `W`. (Conservateur — j'ai sur-estimé
  mes « victoires » 2× ce session ; ne pas fausser le win-rate.)

## Cycle
1. **AVANT** : lire doctrine + `hypotheses.md` ouvertes → fixer **1-2 expériences** du match.
2. **PENDANT** : recon complet (gameconfig→wiki), jouer en appliquant la doctrine, abandon si décidé.
   Outil cheap : `rl_duel.py play --spec '[...]'` = tout le tour + tour IA en 1 appel.
3. **APRÈS (clé)** : revue **auto-ADVERSARIALE** (« suppose la défaite de ma faute → root cause »).
   → écrire l'entrée `journal.md` (tags) → confirmer/réfuter les H ouvertes → ajouter les nouvelles
   → **PROMOUVOIR** en doctrine une H qui passe le **filtre d'inscription** ET (confirmée sur **≥2 parties**
   OU **validée par un seed-replay contrôlé**).

## Filtre d'inscription (anti-overfit — rappel)
**général + vérifié + non-dérivable**. n=1 reste hypothèse. (cf. SKILL §2bis « RÈGLE D'INSCRIPTION »
+ [[feedback_oracle_kb_architecture]])

## Taxonomie des tags (vocabulaire FIXE des failure modes)
`dive-isolé` · `cluster-AoE` · `pas-tué-wincon` · `chaff-focus` · `K!-trompeur` ·
`over-extension` · `sustain-perdu` · `mauvais-recon` · `RNG` · `bon-coup` (succès à renforcer)

## Métriques (à recompter depuis journal.md à chaque revue)

> **RESET 2026-06-21** — l'historique précédent (métriques + INFRA + root-causes par vague) a été
> retiré : il était bâti sur des données **contaminées** par le bug `cmd_play` (l'IA jouait ma team +
> 2ᵉ tour IA gratuit), **corrigé**. Le « over-extension dominant » et l'hypothèse « move-guard aveugle »
> en étaient en grande partie un artefact. À **RECOMPUTER uniquement sur les combats POST-FIX**. Le
> détail brut par combat reste dans `journal.md`.

### Win-rate (recompté depuis journal.md — MAJ après seed 70061, 2026-06-21)
- **Fenêtre POST-FIX (série 70xxx = move-guard per-turn, dataset actif)** : **13 W / 13 L = 26 combats → win-rate 50.0 %**.
  (W : 70014, 70002, 70001, 70009, 70006, 70051, 70056, 70053, 70054, 70060, 70059, 70058, 70057 ; L : 70011, 70012, 70013,
  70003, 70000, 70004, 70007, 70005, 70008, 70050, 70052, 70055, **70061**.)
- **Journal complet (toutes vagues, incl. pré-fix contaminé — pour référence seulement)** : 25 W / 36 L = 61 combats → 41.0 %.

### Fréquence par tag (depuis l'INTÉGRALITÉ de journal.md, 61 entrées de tags — taxonomie canonique)
| tag | n | | tag | n |
|---|---|---|---|---|
| `over-extension` | 54 | | `dive-isolé` | 18 |
| `pas-tué-wincon` | 50 | | `mauvais-recon` | 17 |
| `bon-coup` | 50 | | `K!-trompeur` | 13 |
| `sustain-perdu` | 27 | | `chaff-focus` | 10 |
| `cluster-AoE` | 5 | | `RNG` | 3 |

> **Constat** : `over-extension` reste le tag dominant (52), mais la VAGUE 70xxx montre des **applications
> PROPRES nettes** (96002/98002/70001/70056/70060/70058) où la ligne défensive tenue + un reaction-engine
> portent le W sans slip décisif. ⚠ **seed 70057** = `over-extension` récidive ENCORE dans un W 5v0 (Tan Gi'da,
> un non-tank summon-engine, poussée à (5,3) row 3 à 205 HP pour du chip marginal sur Dante = near-death pour rien) :
> même classe que 70058 (Jain Zar) / 70059 (Kharn) — un non-tank avancé pour du chip/finish que les engines
> screen-on-attack auraient pu délivrer en restant shallow. ⚠ NOUVEAU blind-spot 70057 = le move-guard one-ply
> « safe » à row 2 est devenu NET -4.78/-6.71 quand l'IA a CLOSÉ la distance (delayed-contact, cf. 70003/70007) →
> tenir row 0-1 par défaut quand un gap permet à l'ennemi de sur-committer ; le guard a en revanche SAUVÉ le tour
> décisif (alpha aggressif flaggé OVER-EXTENDED → pull-back a trouvé la ligne Dante-overkill). `bon-coup` (49) ≈
> `pas-tué-wincon` (50) : H02 (kill-wincon-first) est appliqué quand l'engine est ATTEIGNABLE — seed 70057 = W 5v0
> avec wincon-set ENTIER tué dans le bon ordre (engines ATTEIGNABLES car all-melee/deep-strike forcé de closer) ;
> les `pas-tué-wincon` résiduels = surtout les reach-fail row-9 structurels (engine inatteignable), pas une erreur
> de priorité. NOUVELLE DOCTRINE 70057 (au wiki §5bis Ragnar) : un pump-engine (WarHowl) peut être DÉFANGÉ en tuant
> ses BÉNÉFICIAIRES (Dante+Helbrecht) avant l'engine, pas seulement par sa source.
> ⚠ **seed 70061 (L → win-rate POST-FIX retombe à 50.0 %) = NOUVELLE classe de loss « board GAGNÉ NON CONVERTI avant
> le round cap »** : guerre des engines GAGNÉE (Bellator summon-engine + 2 Inceptors + Judh-once tués T3-T4, board dominant
> 4v2-3) MAIS le repair-engine Actus seulement chunké (jamais fini) + l'anvil Resilient Corrodius (12551) jamais engagé →
> le combat a atteint un **hard round cap (~round 10)** où le moteur a déclenché **EnvEndBombardment** (board-wide,
> RemainingTurns=1) = mutual wipe des DEUX équipes → finalStage=Finished mais team gagnante=None (no winner ≠ W). C'est
> distinct des reach-fail (les 2 engines secondaires étaient ATTEIGNABLES, juste pas FINIS) : c'est un échec de CLÔTURE
> (over-hold/chip dans une position gagnée). NOUVELLE MÉCANIQUE candidate **H51 (EnvEndBombardment round-cap mutual-wipe,
> verdict Verif=plausible)** + **H52 (Inceptors summonés MkXGravis ? unconfirmed)**. LEÇON MÉTA : un board gagné avec un
> hard round cap doit être PRESSÉ (push de clôture rounds 6-9), pas tenu ; commencer à grind un anvil Resilient lent dès
> round 5-6 ; budgéter le round clock (candidat tracker `Match_AmountOfTurnsStartedByCurrentPlayer`). NB H05 (floor Judh)
> OBSERVATION contestée RÉSOLUE par Verif : le floor est i2-scopé « tour ennemi seulement » (la note wiki tient), mon
> observation « floor sur tour joueur » était un misread → discarded, H05 reste provisoire non-réfutée.

## Récupération à l'échelle (vector DB — DIFFÉRÉ)
- Journal petit (<~50 parties) → `grep` par tag/unité/seed suffit.
- À l'échelle → **pgvector** (Postgres déjà en place via `rl_ingest_postgres.py`) sur le `summary`
  de chaque entrée → retrouver les K matchs les + similaires (profil de matchup) au lieu de tout
  charger. Entrées `journal.md` conçues dès maintenant pour être embeddables.
