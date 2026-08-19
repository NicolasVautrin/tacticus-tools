---
name: tacticus-loop
description: Boucle d'AUTO-PROGRESSION oracle Tacticus. Méta-process qui me fait progresser au jeu en conservant l'expérience dans des FICHIERS (pas le contexte) via le cycle explorer→hypothèse→valider→promouvoir. Orchestre des sous-agents éphémères (1/match, contexte jetable) qui jouent via le skill tacticus-battle, écrivent journal.md, et renvoient un résumé compact. Use when running the autonomous self-improvement loop (NOT for playing a single match — that's tacticus-battle).
user-invocable: true
allowed-tools: Read, Bash, Glob, Grep, Edit, Write, Agent
---

# Tacticus — Boucle d'auto-progression (méta)

Je progresse au jeu **sans faire exploser le contexte** : toute la mémoire vit dans des
fichiers, le transcript est jetable. Ce skill est l'**orchestrateur** ; il **appelle**
`tacticus-battle` (jouer un match) via des sous-agents.

## Fichiers (la mémoire — à NE PAS tenir en contexte, on lit/écrit)
- `docs/rl/journal.md` — épisodique, append-only (1 entrée/match, embeddable).
- `docs/rl/hypotheses.md` — leçons provisoires (tampon avant doctrine).
- `docs/rl/loop.md` — dashboard : métriques + taxonomie des tags + suite benchmark.
- `docs/rl/toolfeedback.md` — backlog outillage (friction/manques signalés ; recurrence).
- **Doctrine** (relue à chaque match par le sous-agent) : `tacticus-battle` §6/§7 + `docs/rl/wiki.md`.

## Règle d'or — contexte borné
**1 match = 1 sous-agent éphémère.** Il lit doctrine+hypothèses, joue 1 match (ses round-trips
+ game-states vivent dans SON contexte), écrit l'entrée `journal.md`, et renvoie SEULEMENT un
résumé compact (issue, tags, deltas H, promotions proposées). Son contexte meurt avec lui.
L'orchestrateur ne voit jamais un game-state brut.

## Runner — SÉQUENTIEL par défaut
1 runner à la fois ; `rl_duel.py dispose` entre les matchs. Tous les RPC passent par une seule
session Frida → 2 runners avancés en concurrence se sérialisent + risque de cross-talk
(singletons partagés). **Expérience à tester avant tout parallélisme** : 2 runners interleavés
gardent-ils un état indépendant ? Si oui → sous-agents parallèles (throughput). Sinon → séquentiel.

## Le tick d'orchestration
1. Lire `loop.md` (métriques) + `hypotheses.md` (H ouvertes) → choisir le **mode** :
   - **EXPLORE** (seed aléatoire) → découvrir des failure modes → nouvelles H.
   - **VALIDATE** (rejouer un seed précis lié à une H) → test contrôlé (même matchup, ne change que
     le comportement visé → preuve causale). Prioriser si une H attend validation.
   - **BENCHMARK** (rejouer un seed de la suite held-out) → mesurer la progression (périodique).
2. **Spawn un sous-agent** (Agent) avec le prompt match (§Prompt sous-agent).
3. Récupérer son résumé compact → mettre à jour `loop.md` (métriques, tags) + statuts d'H +
   **trier le tool-feedback** : une friction `recurrence ≥2` devient une **tâche d'amélioration
   d'outil prioritaire** (corriger l'outil AVANT de continuer à jouer avec un outil cassé).
4. **PROMOUVOIR** en doctrine toute H qui passe le **filtre d'inscription** ET (confirmée sur
   **≥2 parties** OU **validée par un seed-replay contrôlé**). Éditer `tacticus-battle`/`wiki`.
   En mode autonome je promeus moi-même mais je **loggue** chaque promotion dans `loop.md`.
5. Tick suivant (auto-pacé). **Stop** = budget atteint / N matchs / stop utilisateur.

## Abandon (coût + contexte) — ASYMÉTRIQUE
- **PERDU** dès que je ne peux plus atteindre/contrer leur win-condition → concède, `L`. (Libéral.)
- **GAGNÉ** seulement si léthal **certain avant** le leur → `W`. (Conservateur : j'ai sur-estimé
  mes victoires 2× ; ne pas fausser le win-rate.)

## Filtre d'inscription (anti-overfit)
**général + vérifié + non-dérivable**. n=1 reste hypothèse. (cf. tacticus-battle §2bis +
[[feedback_oracle_kb_architecture]].) Rejeter : overfit contextuel, déjà dérivable de gameconfig,
devinette non vérifiée.

## Mesure de progression (cf. loop.md §Métriques)
- **Suite benchmark held-out** (panel de seeds fixes rejoués périodiquement) = la mesure rigoureuse
  (contrôle la chance de matchup). NE JAMAIS entraîner la doctrine sur ces seeds.
- **Fréquence des tags d'échec** (baisse = progrès) ; **counterfactual** sur replay ; round-trips/match.

## Prompt sous-agent (gabarit — un match auto-suffisant)
> « Tu joues 1 match Tacticus en mode <EXPLORE seed aléatoire | VALIDATE seed S | BENCHMARK seed S>.
> 1) Lis la doctrine : skill tacticus-battle §6/§7 + docs/rl/wiki.md, et docs/rl/hypotheses.md
>    (note 1-2 expériences à tester ce match). 2) Vérifie amorce (discoverSources) ; si reinject →
>    autoBootExtraire. 3) Build (rl_duel build --seed … --board <id>, board OBLIGATOIRE) + recon COMPLET (gameconfig de tout le
>    roster, 1 appel ; wiki en complément). 4) Joue en appliquant la doctrine ; **1 appel/round via
>    `rl_duel.py play --spec '[...]'`** ; **abandonne dès que l'issue est décidée** (règle asymétrique).
>    5) Revue AUTO-ADVERSARIALE : "suppose la défaite de ma faute → root cause". 6) **Écris l'entrée
>    journal.md** (format strict, tags de la taxonomie). 7) **Signale toute friction / outil manquant
>    ou améliorable dans `docs/rl/toolfeedback.md`** (statut open, +1 recurrence si déjà listé) — JAMAIS
>    de contournement silencieux. 8) Dispose le runner. **RENVOIE seulement** : issue (W/L/abandon +
>    round), tags, deltas d'hypothèses (confirme/réfute/nouvelle), promotions proposées, **+ tool-feedback
>    (manques/améliorations d'outils rencontrés)**. NE renvoie AUCUN game-state brut. »

## Signaler l'outillage (l'expérience améliore aussi les OUTILS, pas que la doctrine)
Tout sous-agent qui bute sur un outil **manquant** ou **améliorable** (friction, work-around,
étape impossible) DOIT l'**append à `docs/rl/toolfeedback.md`** + le **remonter dans son résumé**.
Canal **symétrique** des hypothèses : `hypotheses → doctrine`, `toolfeedback → outillage`. Une
friction récurrente bloque/coûte chaque match → la corriger compose sur tous les suivants.

## Ne jamais
- Contourner en SILENCE un outil cassé/manquant (→ le signaler dans `toolfeedback.md`).
- Tenir un game-state brut dans le contexte de l'orchestrateur (→ explosion).
- Promouvoir une H n=1 / contextuelle / dérivable (→ doctrine polluée).
- Lancer 2 runners en parallèle avant d'avoir testé l'isolation.
- Entraîner/tuner la doctrine sur les seeds benchmark (held-out).
