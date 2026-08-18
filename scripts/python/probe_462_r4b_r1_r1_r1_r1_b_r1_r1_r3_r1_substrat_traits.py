"""#462-r4b-r1-r1-r1-r1-b-r1-r1-r3-r1 -- la lecture BRUTE de `ctx.traits` : INVENTAIRE, VENTILATION,
et la LOI qui rend la ventilation derivable.

================================================================================================
CE QUE CE PROBE ETABLIT
================================================================================================
`#462-...-r3` (PR #646) a ferme le defaut sur UN site (`barbed_ovipositor`) : une lecture BRUTE de
`StatsComponent.ctx.traits` rend `set()` sur un CADAVRE, parce que `combatSnapshot.units` ne porte
pas les morts et que `snapshot._load_stats_and_effects` ne pose donc AUCUN `StatsComponent` sur eux.
Le natif, lui, lit `IdunBattle.Entities.Components.BaseUnitComponent$$HasTrait`, que la mort ne
vide pas. Sa fiche annoncait le defaut comme un PATRON, avec un chiffre APPROCHE (54 sites / 29
fichiers) explicitement a re-deriver. C'est ce que fait `--step inventaire`.

`--step ventilation` repond a la question par site : **le sujet peut-il etre une entite chargee
depuis un etat ou elle etait DEJA MORTE ?** La reponse s'appuie sur une LOI, verifiee
executablement par `--step loi` :

  P1. Le capteur `combatSnapshot` n'enumere QUE les entites pour lesquelles la methode native
      `IsAlive` rend vrai (`frida/hooks/features/ai-step/rpc-snapshot.ts`, bloc `allUnits`), et
      `decisionView` publie `alive` en invoquant **LA MEME** methode (`projection.ts`). Donc,
      cote port : `StatsComponent` ABSENT <=> `UnitComponent.alive == False` AU CHARGEMENT.
      (Verifie ici sur `snapshot.load_state`, pas suppose.)

  P2. AUCUNE voie du port ne rend VIVANTE une entite chargee morte. Les deux seules Operations qui
      reposent `alive = True` sont :
        * `IdunBattle.Operations.ReviveUnitOperation$$Execute` (`operations/revive.py`), atteinte
          uniquement par `kill_unit_revive_gate` -- donc sur une mort survenue PENDANT le run ;
        * `IdunBattle.Operations.ResurrectUnitOperation$$Execute` (`operations/resurrect.py`),
          atteinte uniquement par `EnvAmbushResurrectAbility`, dont le selecteur
          `GetUnitsEligibleForResurrect` exige `UnitComponent.turn_defeated` -- un champ
          qu'AUCUN chargement ne seede (seul `AmbushSummonAbility` l'ecrit, a la mort, pendant
          le run).

  => **COROLLAIRE, et c'est LE discriminant de la tranche** : un site dont le sujet est gate
  VIVANT est INERTE, non par prudence mais parce que le seul cadavre du port n'a aucun chemin
  vers la vie. Il ne reste ATTEIGNABLES que les sites dont le sujet peut etre MORT.

================================================================================================
CE QUE LA VENTILATION A TROUVE -- et pourquoi convertir en masse aurait ETE UNE REGRESSION
================================================================================================
Deux sites seulement ont un sujet qui peut etre MORT sans blocage amont ni aval :

  * `runner/operations/triggers/genestealer.py::_valid_dead_decoys`
  * `runner/operations/triggers/dispatch/move_death.py::post_unit_kill_triggers_for_move`

et sur les DEUX, remplacer betement la lecture brute par le foyer AURAIT FAIT DIVERGER LE PORT DU
NATIF. Le decompile de `ADecoysAndMisdirectionAbility$$GetValidDeadDecoys` (relu VERBATIM sur
`rnca9r7q6c`) porte cinq conjoints :

    Filter( AllDeadUnits,
              AreFriends(sel@0x30 owner, sel@0x68 ActiveTarget)
            & HasTrait(sel@0x68 ActiveTarget, 0x41d = 1053 Decoy)
            & IsKilledThisTurn(sel@0x68 ActiveTarget)                        <-- NON PORTE
            & AreEqual(Killer(it), sel@0x40)                       <-- NON PORTE
            & Contains(Tiles(sel@0x40), MainTileOfUnits(it)) )

Le port COLLAPSE `IsKilledThisTurn` et `AreEqual(Killer, ...)` en une CO-LOCALISATION (docstring du
site). Or un cadavre AU CHARGEMENT est exactement une unite qui n'a PAS ete tuee ce tour : la
lecture brute, en rendant `set()`, l'excluait -- par ACCIDENT, mais dans le bon sens. Le foyer, lui,
lui rend son trait `Decoy`/`Steppable` et le ferait passer. Meme forme sur `move_death`.

=> La conversion livree ne se contente donc PAS de changer le substrat : elle SORT l'exclusion de
l'accident en la NOMMANT (`sc is None` = cadavre-au-chargement = collapse d'`IsKilledThisTurn`),
puis lit les traits au foyer. Value-preserving, et le jour ou un `StatsComponent` sera pose sur les
cadavres, l'exclusion ne disparaitra pas en silence.

================================================================================================
USAGE
================================================================================================
    python probe_462_r4b_r1_r1_r1_r1_b_r1_r1_r3_r1_substrat_traits.py --step inventaire
    python probe_462_r4b_r1_r1_r1_r1_b_r1_r1_r3_r1_substrat_traits.py --step ventilation
    python probe_462_r4b_r1_r1_r1_r1_b_r1_r1_r3_r1_substrat_traits.py --step loi
    python probe_462_r4b_r1_r1_r1_r1_b_r1_r1_r3_r1_substrat_traits.py --step contre

Tout est OFFLINE : aucun runner, aucun RPC. ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import ast
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]
ENGINE = PYDIR / "engine"

# Le module d'autorite : sa propre lecture brute EST le foyer, pas une instance du patron.
FOYER = ("entities/traits/unit_trait.py", "entity_trait_names")


# ================================================================================================
# INVENTAIRE -- AST, jamais grep (la prose des docstrings compte des dizaines de faux positifs)
# ================================================================================================
def _dotted(node: ast.AST) -> str:
    parts, cur = [], node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
    elif isinstance(cur, ast.Call):
        parts.append("<call>")
    elif isinstance(cur, ast.Subscript):
        parts.append("<sub>")
    else:
        parts.append("<?>")
    return ".".join(reversed(parts))


def sites(racine: "Path | None" = None) -> list:
    """Toutes les lectures/ecritures de l'attribut `traits`, par AST, sous `engine/`.

    Rend une liste de tuples `(fichier, fonction, expr, role, ligne)` -- `role` = 'R' ou 'W'.
    La CLE de ventilation est `(fichier, fonction, expr, role)` : elle survit a un deplacement
    de lignes, ce qu'un couple `(fichier, ligne)` ne fait pas."""
    base = Path(racine) if racine is not None else ENGINE
    out = []
    for dirpath, _dirs, files in os.walk(base):
        for fn in sorted(files):
            if not fn.endswith(".py"):
                continue
            p = Path(dirpath) / fn
            rel = os.path.relpath(p, base).replace("\\", "/")
            src = p.read_text(encoding="utf-8")
            tree = ast.parse(src)
            owner = {}
            for n in ast.walk(tree):
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    for i in range(n.lineno, (n.end_lineno or n.lineno) + 1):
                        prev = owner.get(i)
                        owner[i] = (n.name, n.lineno) if prev is None or n.lineno > prev[1] else prev
            vus = set()
            for n in ast.walk(tree):
                if isinstance(n, ast.Attribute) and n.attr == "traits":
                    vus.add((n.lineno, _dotted(n), "W" if isinstance(n.ctx, ast.Store) else "R"))
                elif (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                      and n.func.id == "getattr" and len(n.args) >= 2
                      and isinstance(n.args[1], ast.Constant) and n.args[1].value == "traits"):
                    vus.add((n.lineno, "getattr(%s)" % _dotted(n.args[0]), "R"))
            for ln, expr, role in sorted(vus):
                out.append((rel, owner.get(ln, ("<module>", 0))[0], expr, role, ln))
    return out


# ================================================================================================
# VENTILATION -- une ligne PAR CLE, avec son verdict et son MOTIF
# ================================================================================================
# Verdicts :
#   FOYER          le module d'autorite lui-meme
#   WRITE          une ECRITURE (hors patron : c'est le seed, pas une lecture aveugle)
#   HORS-ECS       le `.traits` ne designe pas le `UnitContext` d'une entite ECS
#   ATTEIGNABLE    le sujet peut etre une entite chargee MORTE -- traite par cette tranche
#   INERTE-VIVANT  le sujet est gate VIVANT (loi P1+P2 : un cadavre n'a aucun chemin vers la vie)
#   INERTE-FRAIS   le sujet est une entite creee PENDANT le run (ctx fabrique sur place)
#   INERTE-AMONT   pour un cadavre, un gate ANTERIEUR refuse avant d'atteindre la lecture
#   INERTE-AVAL    la lecture est atteinte pour un cadavre, mais un gate POSTERIEUR refuse quand meme
#   INDECIDABLE    sujet non borne par une enumeration exhaustive des appelants -- NON converti
VENTILATION = {
    # ---- foyer et ecritures -------------------------------------------------------------------
    ("entities/traits/unit_trait.py", "entity_trait_names", "getattr(unit_ctx)", "R"):
        ("FOYER", "le module d'autorite : c'est LUI qui repare le substrat"),
    ("playbook/scene.py", "_seed_measured_traits", "ctx.traits", "W"):
        ("WRITE", "#264 : seed de la MESURE `combatSnapshot.units[].traits`"),
    ("runner/snapshot.py", "_load_unit_traits", "sc.ctx.traits", "W"):
        ("WRITE", "#264 : seed de la MESURE, face runner"),
    # #585 (PR #863, `1106 WarHowl`) -- les DEUX entrees `behaviours/grants.py::execute` (`ctx.traits`
    # W et `getattr(ctx)` R) ont DISPARU de la table : la feuille DSL `AddTrait` n'ecrit plus rien
    # elle-meme, elle DELEGUE a `operations/traits.py::AddTraitOperation.execute` -- le foyer que le
    # natif atteint AUSSI par `<Effect>.ApplyInternal`. Retirer ces entrees N'EST PAS un abandon de
    # verdict : le site a change d'ETAGE (meme forme que les deplacements #498-r3 et #448-...-r2-r2
    # notes plus bas), et les deux entrees ci-dessous portent desormais les memes verdicts.
    #
    # Site NEUF de la meme tranche : les deux Operations `AddTrait` / `RemoveTrait` partagent la cle
    # -- leur methode s'appelle `execute` dans les deux classes, et la cle de ventilation est
    # `(fichier, fonction, expr, role)`.
    ("runner/operations/traits.py", "execute", "ctx.traits", "W"):
        ("WRITE", "`AddTraitOperation$$Execute` / `RemoveTraitOperation$$Execute` : l'ECRITURE de "
                  "la resultante `BaseUnitComponent$$HasTrait` (le port fusionne +0x40/+0x48). "
                  "Elle n'est atteinte que si `_traits_of` a rendu un ctx -- cf. son entree "
                  "ci-dessous"),

    # ---- le `.traits` ne designe pas un ctx d'entite ECS ---------------------------------------
    ("entities/unit_context.py", "trait_objects", "self.traits", "R"):
        ("HORS-ECS", "`self` EST le UnitContext : aucun acces par entite, donc aucun repli"),
    ("entities/abilities/active_ability.py", "get_pierce", "self.caster.traits", "R"):
        ("HORS-ECS", "`self.caster` est un UnitContext deja resolu (et la methode est DEAD CODE "
                     "declare : aucun call-site)"),
    ("entities/effect_targets.py", "_surrounding_enemy_psykers_r2", "world.traits", "R"):
        ("HORS-ECS", "appel de METHODE du pont `world`, pas une lecture de ctx ; les deux "
                     "implementations du pont sont ventilees a leur propre ligne"),
    ("entities/traits/unit_trait.py", "units_without_trait", "getattr(<call>)", "R"):
        ("INERTE-AMONT", "`key` PAR DEFAUT : aucun appelant d'`engine/` n'omet `key`, le lambda "
                         "n'est jamais exerce"),

    # ---- INERTE-AMONT / -AVAL : le sujet peut etre mort, mais un autre gate tranche ------------
    ("runner/operations/triggers/dispatch/core.py", "collect_triggered_abilities", "sc.ctx.traits", "R"):
        ("INERTE-AMONT", "`if sc is None: continue` DEUX lignes plus haut -- un cadavre n'atteint "
                         "jamais la lecture. Le `continue` est un defaut BIEN PLUS large (aucune "
                         "triggered-ability enregistree pour un cadavre) : residu #462-...-r3-r1-r2"),
    ("runner/operations/triggers/genestealer.py", "matches", "getattr(sc.ctx)", "R"):
        ("INERTE-AMONT", "`AmbushSummonAbility` n'est INSCRITE que par `collect_triggered_abilities`, "
                         "qui exige deja un `StatsComponent`"),
    # Site NEUF, arrive avec #585 (PR #863) -- le pendant LECTURE des deux Operations ci-dessus, et
    # l'HERITIER du verdict `INERTE-AMONT` que portait `behaviours/grants.py::execute` (`if ctx is
    # None: continue` juste au-dessus) avant sa delegation.
    ("runner/operations/traits.py", "_traits_of", "getattr(ctx)", "R"):
        ("INERTE-AMONT", "`UnitExtensions$$GetBaseUnitComponent(target)` cote port : la fonction "
                         "sort par `return None, None` des que `sc` (donc `ctx`) est absent, DEUX "
                         "lignes avant la lecture -- un cadavre-au-chargement n'atteint jamais "
                         "`getattr(ctx, 'traits')`. Le natif LEVE sur ce meme cas (composant nul) ; "
                         "le port DEGRADE en no-op, ce qui est du cote PERMISSIF et documente au "
                         "site. Convertir au foyer serait ici une REGRESSION : le foyer rendrait "
                         "le kit gameconfig d'un cadavre, alors que ces deux Operations MUTENT "
                         "l'ensemble -- elles ecriraient sur un substrat fabrique"),
    ("runner/operations/triggers/loki/cosmic_horror.py", "_traits_of", "getattr(sc.ctx)", "R"):
        ("INERTE-AMONT", "3 appels : victime d'un `UnitDefeated` (morte PENDANT le run), ennemi "
                         "vivant, et le crushe d'un `On(PostUnitKill)`. Le motif de ce 3e appel a "
                         "CHANGE en #462-...-c-r3-r1-r4 et s'est RENFORCE : l'event ne sort plus "
                         "d'une re-identification par co-localisation, mais du foyer "
                         "`damage.py::_kill_unit_operation` -- dont les TROIS appelants "
                         "(drain de `pending_deaths`, `_kill_steppable_units` gate `uc.alive`, "
                         "`KillUnitBehaviour` gate `uc.alive`) ne peuvent porter qu'un mort DU RUN"),
    # #1049 -- `CursedOfTheWalkingPoxAbility` : `NOT HasTrait(Target@+0x60, 0x5 = Mechanical)`. Le
    # sujet est la VICTIME d'un `On(0x35 = PostUnitKill)`, donc MORTE -- exactement le 3e appel de
    # `cosmic_horror.py::_traits_of` ci-dessus, et la MEME raison le rend inerte : l'unique emetteur
    # de ce vecteur est le foyer `damage.py::_kill_unit_operation`, dont les TROIS appelants ne
    # peuvent porter qu'un mort DU RUN (qui a donc son `StatsComponent`). Un cadavre-AU-CHARGEMENT
    # n'atteint jamais ce site.
    ("runner/operations/triggers/loki/cursed_of_the_walking_pox.py", "_traits_of",
     "getattr(sc.ctx)", "R"):
        ("INERTE-AMONT", "victime d'un `On(PostUnitKill)` : morte PENDANT le run (meme emetteur, "
                         "memes trois appelants que le 3e appel de `cosmic_horror.py::_traits_of`)"),
    ("runner/operations/triggers/genestealer.py", "_eligible_for_resurrect", "getattr(sc.ctx)", "R"):
        ("INERTE-AVAL", "sujet MORT et lecture ATTEINTE, mais le gate suivant "
                        "(`turn_defeated is None`) refuse tout cadavre-au-chargement : convertir "
                        "ne deplacerait aucun verdict (c'est la P2 de la loi)"),
    ("runner/operations/triggers/genestealer.py", "_hero_key", "getattr(sc.ctx)", "R"):
        ("INERTE-AVAL", "ne trie que `eligible`, deja filtre par `turn_defeated` -- donc des morts "
                        "DU RUN, qui ont leur ctx"),

    # ============================================================================================
    # #547-r11 -- SIX SITES NEUFS, trouves par le cliquet d'exhaustivite. Aucun n'est ATTEIGNABLE.
    #
    # ⚠ LA FICHE `#547-r6` DU BACKLOG EN NOMMAIT TROIS AUTRES (`resurrect.py::tiles_are_occupied`,
    # `traits.py::_traits_of`, `traits.py::execute`) : elle etait PERIMEE -- ces trois-la sont
    # ventiles depuis (les deux `traits.py` ci-dessus), et les six ci-dessous sont arrives entre
    # temps. Diagnostiquer d'apres une fiche plutot que d'apres le rouge courant aurait fait
    # chercher au mauvais endroit.
    # ============================================================================================
    ("entities/effect_targets.py", "_way_of_the_short_blade_marked", "world.traits", "R"):
        ("HORS-ECS", "appel de METHODE du pont `world`, pas une lecture de ctx -- MEME forme exacte "
                     "que `_surrounding_enemy_psykers_r2` et `_synapse_targets` ci-dessus, et les "
                     "deux implementations du pont sont ventilees a leur propre ligne. Le site "
                     "porte au surplus son propre `world.alive(uid)` juste au-dessus, dans la "
                     "boucle `SurroundingFriends`"),
    ("playbook/scene.py", "hunter_of_souls_adjacent_psyker_friends", "getattr(c)", "R"):
        ("INERTE-VIVANT", "balayage de `self.units` avec le gate `if oid == uid or not "
                          "u.get('alive'): continue` AVANT la lecture -- MEME forme exacte que "
                          "`_enmity_adjacent` et `_enemy_psykers_alive` ci-dessus. Face PREDICTION "
                          "de `HunterOfSouls_ExtraDamageEffect$$GetUnits` (#1078-r3), dont "
                          "l'etage `AdjacentFriends(..., 3 = OnlyAliveAndTargetable)` porte deja "
                          "la vivacite cote natif"),
    ("playbook/should_evaluate_target.py", "_traits_ids", "getattr(ctx)", "R"):
        ("INERTE-AMONT", "`BasePlaybook$$ShouldEvaluateTarget` / `UnitExtensions$$"
                         "IsIrrelevantObject`. DEUX gates ANTERIEURS, et le premier suffit : "
                         "`filtrer_cibles` fait `ctx = tab.get(eid)` puis `if ctx is None: "
                         "garde.append(element); continue` -- or `ctx_by_id` vient du `predictor`, "
                         "donc des VIVANTS seuls, et un cadavre-au-chargement n'a de toute facon "
                         "aucun `UnitContext`. Le second est dans la fonction meme (`if ctx is "
                         "None: return None`). La degradation est PERMISSIVE et ECRITE (la cible "
                         "est GARDEE), ce qui est la bonne direction : retirer sur une absence de "
                         "substrat transformerait un trou en restriction"),
    ("runner/operations/damage.py", "_kill_unit_operation", "getattr(_sc_pr.ctx)", "R"):
        ("INERTE-VIVANT", "sujet = `target_id` du `KillUnitOperation` EN COURS -- l'unite qu'on est "
                          "en train de tuer, donc vivante a l'instant du coup (meme argument que "
                          "`components.unit_prevents_overkill`). Le site sert le gate "
                          "`preventRevive = options.<+0x45> ? true : IsSteppable(killed)` du rang "
                          "natif `RecordDeathReason -> Add(0x08) -> Add(0x0d) -> On(1)`. Un "
                          "cadavre-AU-CHARGEMENT n'y entre jamais : les TROIS appelants du foyer "
                          "(drain de `pending_deaths`, `_kill_steppable_units` gate `uc.alive`, "
                          "`KillUnitBehaviour` gate `uc.alive`) ne portent qu'un mort DU RUN -- "
                          "c'est la mesure deja etablie pour `cosmic_horror.py::_traits_of`"),
    ("runner/operations/movement.py", "execute", "getattr(_sc_ms.ctx)", "R"):
        ("INERTE-AMONT", "sujet = `self.unit_id`, le MOVER. `MoveUnitOperation$$Execute` ouvre par "
                         "la garde `_is_allowed_to_move(state, self.unit_id, ...)`, qui porte "
                         "`if uc is not None and not uc.alive: return False` "
                         "(`UnitExtensions$$IsDead`) -- ~286 lignes AVANT cette lecture, qui ne "
                         "sert qu'a decider si le compte de tuiles doit etre calcule "
                         "(`_is_like_flying`). Un cadavre-au-chargement n'atteint jamais le site"),
    ("runner/operations/triggers/loki/final_vengeance.py", "matches", "getattr(<call>)", "R"):
        ("INERTE-AMONT", "sujet = `self.owner_id`, et le gate qui precede est le 2e conjoint de "
                         "`matches` : `mourant = ev.dying_id ?? ev.target_id` puis "
                         "`if mourant is None or int(mourant) != int(self.owner_id): return False` "
                         "(`get_OwnerIsTarget` via `FinalJusticeAbility.Trigger` -- le porteur EST "
                         "le mourant). L'evenement de mort est EMIS par le run "
                         "(`damage.py::_kill_unit_operation`), donc son sujet est toujours un mort "
                         "DU RUN, jamais un cadavre-au-chargement -- qui n'est tue par rien. ⚠ La "
                         "degradation serait PERMISSIVE si le site etait atteint (`sc is None` -> "
                         "`traits = set()` -> le `NOT HasTrait(Owner, 0x3f6 = FinalJustice)` "
                         "passerait), ce qui rend le gate amont load-bearing et non decoratif"),

    # ---- INERTE-FRAIS : entite creee pendant le run --------------------------------------------
    ("runner/operations/spawn.py", "_spawn_config_grot", "ctx.traits", "R"):
        ("INERTE-FRAIS", "`ctx` est construit 3 lignes plus haut par `build_summon_context`"),
    ("runner/operations/spawn.py", "execute", "ctx.traits", "R"):
        ("INERTE-FRAIS", "idem : `build_summon_context` local"),
    # #1049 -- le site d'`execute_self_replica` a DEMENAGE, il n'a pas disparu : son corps
    # par-tuile est devenu le foyer `CopyOwner` partage avec `execute_copy_owner_on_tiles`
    # (`CursedOfTheWalkingPoxAbility`). MEME sujet, MEME raison, une seule entree au lieu de deux.
    ("runner/operations/spawn.py", "_spawn_copy_owner_at_tile", "ctx.traits", "R"):
        ("INERTE-FRAIS", "`ctx` est le clone `_dc_replace(c_ctx, ...)` construit juste au-dessus"),
    ("runner/operations/spawn.py", "execute_pilein_replica", "ctx.traits", "R"):
        ("INERTE-FRAIS", "idem : `build_summon_context` local"),
    ("runner/operations/spawn.py", "trigger_spawned_unit_finish_turn", "getattr(sc.ctx)", "R"):
        ("INERTE-FRAIS", "#291 : le sujet est l'unite qui vient d'APPARAITRE"),

    # ---- INERTE-VIVANT : sujet gate vivant (le gros du gisement) -------------------------------
    ("ai/state_bridge.py", "_move_tiles", "sc.ctx.traits", "R"):
        ("INERTE-VIVANT", "le MOVER"),
    ("ai/state_bridge.py", "_is_machine", "sc.ctx.traits", "R"):
        ("INERTE-VIVANT", "cible `kind == machine` enumeree par le ciblage (une cible morte est "
                          "refusee par `IsInvalidTarget`)"),
    ("playbook/prediction/_shared.py", "_should_apply_ranged_in_melee", "getattr(ctx)", "R"):
        ("INERTE-VIVANT", "l'ATTAQUANT"),
    ("playbook/prediction/_shared.py", "_add_positional_and_defender_mods", "getattr(<call>)", "R"):
        ("INERTE-VIVANT", "l'ATTAQUANT"),
    ("playbook/prediction/_shared.py", "_walk_path_counts_from", "getattr(<call>)", "R"):
        ("INERTE-VIVANT", "occupant BLOQUANT, gate `hp > 0` juste au-dessus"),
    ("playbook/scene.py", "_enemy_psykers_alive", "getattr(c)", "R"):
        ("INERTE-VIVANT", "`Enemies(...)` + `not u.alive -> continue`"),
    # #962 (second lot, apporte par le REBASE) -- site arrive avec #965
    # (`RefusalToBeOutdone`). `_traits_of` sert l'unique `_has_trait`, et ses DEUX call-sites
    # passent `ev.actor_id` : le sujet est le `Caster@+0x48` d'une attaque EN COURS, donc vivant
    # par construction (il vient de frapper). Meme regime que les autres << l'ATTAQUANT >> de
    # cette table.
    ("runner/operations/triggers/loki/refusal_to_be_outdone.py", "_traits_of", "getattr(uc)", "R"):
        ("INERTE-VIVANT", "l'ATTAQUANT (`Caster@+0x48`) d'une attaque en cours -- les deux "
                          "call-sites de `_has_trait` passent `ev.actor_id`"),
    # #962 -- site arrive avec #948 (`EnmityForTheUnworthy`), non ventile. La lecture porte le
    # `NonSteppableOrObjectUnits(..., 3)` des deux compteurs d'adjacence ; son sujet est un
    # ELEMENT de `self.units` que la boucle a deja filtre par `not u.get("alive") -> continue`
    # (scene.py, juste au-dessus de la lecture). Meme regime exact que `_enemy_psykers_alive`.
    ("playbook/scene.py", "_enmity_adjacent", "getattr(c)", "R"):
        ("INERTE-VIVANT", "boucle sur `self.units` avec `not u.alive -> continue` en tete, puis "
                          "`unit_in_adjacent_tiles` -- le cadavre-au-chargement n'atteint jamais "
                          "la lecture"),
    ("playbook/scene.py", "traits", "getattr(c)", "R"):
        ("INERTE-VIVANT", "pont `WorldView.traits` face DECISION ; son unique consommateur "
                          "(`effect_targets`) filtre `world.alive(uid)`"),
    ("runner/components.py", "traits", "getattr(ctx)", "R"):
        ("INERTE-VIVANT", "pont `WorldView.traits` face COMBAT, meme consommateur"),
    ("runner/components.py", "enemy_psykers_alive", "sc.ctx.traits", "R"):
        ("INERTE-VIVANT", "`UnitsWithTrait(Enemies(...))` + gate `alive`"),
    ("runner/components.py", "can_be_overkilled", "getattr(<call>)", "R"):
        ("INERTE-VIVANT", "l'unite qui SUBIT le degat"),
    ("runner/components.py", "contagions_of_nurgle_amount", "getattr(ctx)", "R"):
        ("INERTE-VIVANT", "le dict porte `alive`, et `get_in_range_aura_amount` ecarte "
                          "`not alive or hp <= 0` avant de lire `_traits`"),
    ("runner/damage_model.py", "target_trait_names", "getattr(sc.ctx)", "R"):
        ("INERTE-VIVANT", "foyer local (10 call-sites) : cible ou attaquant d'un degat"),
    ("runner/damage_model.py", "apply_trench_reduction", "getattr(sc.ctx)", "R"):
        ("INERTE-VIVANT", "l'ATTAQUANT"),
    ("runner/operations/additional_hits.py", "collect_additional_hit_groups", "getattr(asc.ctx)", "R"):
        ("INERTE-VIVANT", "l'ATTAQUANT"),
    ("runner/operations/displace.py", "_apply_knockback_to", "getattr(sc.ctx)", "R"):
        ("INERTE-VIVANT", "`IsDisplaceable` : gate `not uc.alive -> return` juste au-dessus"),
    ("runner/operations/displace.py", "_is_empty_or_steppable", "getattr(sc.ctx)", "R"):
        ("INERTE-VIVANT", "occupant issu de `_occupied` (vivants seuls)"),
    # #498-r3 -- l'entree `displace.py::execute` (pull/push/direct) a DISPARU de la table : ces
    # trois `execute()` ne lisent plus `.traits` du tout, ils appellent le foyer
    # `runner/components.py::unit_extensions_is_displaceable`, qui passe par `entity_trait_names`.
    # Meme cause pour `momentum.py::_is_displaceable`. Retirer l'entree N'EST PAS un abandon de
    # verdict : le site a change d'etage, et le foyer n'est pas une lecture brute.
    ("runner/operations/movement.py", "_num_tiles_moved", "getattr(sc0.ctx)", "R"):
        ("INERTE-VIVANT", "le MOVER"),
    # #448-r1-r1-r2-r2 : la lecture « occupant bloquant » qui vivait dans `_num_tiles_moved` a
    # DEMENAGE dans `_blocking_positions`, le foyer que `_num_tiles_moved` et `_calculate_path`
    # partagent desormais. Meme sujet, meme gate, meme verdict -- c'est un changement d'ETAGE, pas
    # un abandon de verdict (meme forme que le deplacement #498-r3 note ci-dessus).
    ("runner/operations/movement.py", "_blocking_positions", "getattr(sc.ctx)", "R"):
        ("INERTE-VIVANT", "occupant bloquant, gate `not uc.alive -> continue`"),
    ("runner/operations/movement.py", "_calculate_path", "getattr(sc.ctx)", "R"):
        ("INERTE-VIVANT", "le MOVER"),
    ("runner/operations/movement.py", "_tiles_are_empty", "getattr(sc.ctx)", "R"):
        ("INERTE-VIVANT", "occupant de la tuile d'ARRIVEE : gate `not uc.alive -> continue` juste "
                          "au-dessus -- un mort ne remplit pas la tuile (`TileContentComponent."
                          "IsFilled` suit le retrait du plateau)"),
    ("runner/operations/movement.py", "_movement_steps", "getattr(sc.ctx)", "R"):
        ("INERTE-VIVANT", "le MOVER"),
    ("runner/operations/movement.py", "_kill_steppable_units", "getattr(sc.ctx)", "R"):
        ("INERTE-VIVANT", "candidat au crush : gate `not uc.alive -> continue` (on ne re-tue pas "
                          "un mort)"),
    # Site NEUF, arrive avec #564 (PR #857, `1039 RitesOfRestoration`). MEME lecture et MEME gate
    # que `_kill_steppable_units` ci-dessus -- le site le dit lui-meme en commentaire.
    ("runner/operations/resurrect.py", "tiles_are_occupied", "getattr(sc.ctx)", "R"):
        ("INERTE-VIVANT", "branche `allowAnyUnit == 0` de `TileExtensions$$IsFreeTile` : occupant "
                          "candidat, gate `uc is None or not uc.alive -> continue` en tete de "
                          "boucle. Un CADAVRE n'occupe rien (`KillUnitOperation` -> "
                          "`RemoveUnitFromTiles` vide le `TileContentComponent`), donc le natif ne "
                          "le voit pas non plus"),
    ("runner/operations/summon_ai.py", "is_automatic", "getattr(sc.ctx)", "R"):
        ("INERTE-VIVANT", "`collect_ai_controlled` evalue `not uc.alive or not is_automatic(...)` "
                          "-- le court-circuit Python garantit un sujet vivant"),
    # #590-r6-r2 : le site a DEMENAGE (`operations/turnflow.py` -> `runner/components.py`) et le
    # mirror est desormais PUBLIC (`unit_extensions_can_move`), pour supprimer l'arete d'import qui
    # imposait un differe a `abilities/loki/attempted_possession.py`. La cle change donc de FICHIER
    # et de NOM ; le classement, lui, tient toujours -- mais sa justification portait deja une
    # premisse fausse AVANT ce deplacement (« son unique appelant est `has_tiles_to_move_to` » :
    # `operations/movement.py::_is_unit_allowed_to_move` et `attempted_possession` l'appellent
    # aussi). Ces deux appelants-la n'ouvrent PAS le gate : le premier lit un `is False` strict et
    # n'agit que sur un refus CERTAIN, le second n'entre en branche mobile que sur un `is True`
    # MESURE -- dans les deux cas un `traits is None` sur un cadavre rendrait la branche PERMISSIVE
    # deja nommee ci-dessous, jamais un refus invente.
    ("runner/components.py", "unit_extensions_can_move", "getattr(sc.ctx)", "R"):
        ("INERTE-VIVANT", "chaine d'appel fermee cote `turnflow` : l'appelant y est "
                          "`has_tiles_to_move_to`, lui-meme appele par `_can_act` et par "
                          "`has_action_available`, tous deux sous "
                          "`VerifyUnitsTurnFinishedOperation.verify_unit_turn_ended`). Le gate "
                          "vivant y est le NATIF lui-meme -- "
                          "`VerifyUnitsTurnFinishedOperation$$VerifyUnitTurnEnded` fait "
                          "`if (TryGetComponent<HealthComponent>(out hp) && hp.IsDead()) return` "
                          "AVANT `HasTilesToMoveTo`, porte en `if uc is not None and not uc.alive: "
                          "return` ; et `$$Execute` n'itere que "
                          "`PlayerComponent$$get_CurrentlyOwnedUnitIds`, dont le `RemoveAll(<defait>)` "
                          "est porte en `if uc is None or not uc.alive: continue`. Le cas `uc is "
                          "None` (seul a franchir le 1er gate) sort du mirror par `return None` "
                          "TROIS lignes avant la lecture. Direction si le gate sautait : `traits is "
                          "None` -> le test `Stationary` ne mord pas -> `return True`, soit la MEME "
                          "sur-estimation permissive que le residu `MovementComponent$$IsAllowedToMove` "
                          "deja nomme dans la docstring du site"),
    ("runner/operations/triggers/base.py", "_unit_trait_names", "sc.ctx.traits", "R"):
        ("INERTE-VIVANT", "foyer local (8 call-sites) : acteur/caster/occupant vivant, ou owner "
                          "d'un `fire_on_death` mort PENDANT le run"),
    ("runner/operations/triggers/genestealer.py", "_valid_decoys", "getattr(sc.ctx)", "R"):
        ("INERTE-VIVANT", "decoys VIVANTS (`not uc.alive -> continue`)"),
    ("runner/operations/triggers/tiles.py", "first_aid_heal", "sc.ctx.traits", "R"):
        ("INERTE-VIVANT", "occupant VIVANT de la tuile FirstAid"),
    ("runner/operations/triggers/tiles.py", "apply_tile_defense_on_move", "sc.ctx.traits", "R"):
        ("INERTE-VIVANT", "le MOVER, et `sc is None -> return` deux lignes plus haut"),
    ("runner/operations/triggers/tiles.py", "light_cover_on_enter", "getattr(sc.ctx)", "R"):
        ("INERTE-VIVANT", "le MOVER, gate `not uc.alive -> return`"),
    ("runner/operations/triggers/loki/arcane_shield.py", "_arcaneshield_candidates", "sc.ctx.traits", "R"):
        ("INERTE-VIVANT", "`OnlyAliveAndTargetable`"),
    ("runner/operations/triggers/loki/contagions_of_nurgle.py", "aura_carriers", "getattr(sc.ctx)", "R"):
        ("INERTE-VIVANT", "gate `not uc.alive -> continue`"),
    ("runner/operations/triggers/loki/control_edict.py", "_adjacent_mechanical_summons",
     "getattr(sc.ctx)", "R"):
        ("INERTE-VIVANT", "gate `sc is None or not uc.alive -> continue`"),
    ("runner/operations/triggers/loki/cursed_plague_bell.py", "matches", "getattr(asc.ctx)", "R"):
        ("INERTE-VIVANT", "l'ACTEUR de l'event"),
    ("runner/operations/triggers/loki/spiritual_leader.py", "_adjacent_decoys", "getattr(sc.ctx)", "R"):
        ("INERTE-VIVANT", "`AdjacentFriends` + gate `not uc.alive -> continue`"),
    ("runner/abilities/loki/facade.py", "get_dynamic_invalid_target_reason", "getattr(sc.ctx)", "R"):
        ("INERTE-VIVANT", "la CIBLE d'un ciblage"),
    ("runner/abilities/loki/swarm.py", "refresh_swarm_hit_reduction", "ctx.traits", "R"):
        ("INERTE-VIVANT", "gate `not uc.alive -> return` puis `ctx is None -> return`"),
    # #508 -- `LeadingTheChargeAbility$$GetSummonTiles` : le sujet est un ennemi ADJACENT a la tuile
    # candidate, et la boucle `UnitsWithoutTrait(0x1b = Steppable)` est GATEE au-dessus.
    ("runner/abilities/loki/leading_the_charge.py", "_has_adjacent_enemies", "getattr(sc.ctx)", "R"):
        ("INERTE-VIVANT", "gate `uc is None or not uc.alive -> continue` en tete de boucle"),
    # #498 -- les deux predicats de `UnstoppableMomentumReworked`. Les verdicts DIFFERENT parce que
    # les gates ne sont pas au meme etage, et c'est exactement ce que cette table sert a dire.
    # (#498-r3 : `_is_displaceable` ne lit plus `.traits` -- il delegue au foyer, cf. la note
    #  posee au bloc `displace.py` ci-dessus. Son gate `alive` est CONSERVE et nomme au site.)
    ("runner/abilities/loki/momentum.py", "_can_move", "getattr(sc.ctx)", "R"):
        ("INERTE-AMONT", "`UnitExtensions$$CanMove` n'a AUCUN gate interne ; son unique appelant "
                         "(`ExecuteBehaviourStep`) pose `if _is_dead(caster): return False` a la "
                         "ligne PRECEDENTE -- le sujet est le CASTER, jamais une entite arbitraire"),
    ("runner/operations/spawn.py", "initialize_deferred_actor_abilities", "getattr(ctx)", "R"):
        ("INERTE-VIVANT", "l'unite qui vient d'agir / d'etre initialisee"),
    ("services/battle_query.py", "select_weapon_pierce", "getattr(ctx)", "R"):
        ("INERTE-VIVANT", "le ctx de l'ATTAQUANT, passe en argument"),
    ("services/movement_query.py", "get_movable_tiles_for", "sc.ctx.traits", "R"):
        ("INERTE-VIVANT", "le MOVER"),
    ("services/movement_query.py", "get_movable_positions_for", "getattr(sc.ctx)", "R"):
        ("INERTE-VIVANT", "le MOVER"),

    # Site NEUF, arrive avec #271-r4 (PR #831) et ventile a la volee par
    # #462-r4b-r1-r1-r1-r1-b-r1-r1-r3-r1-r3 : le cliquet l'a trouve AU REBASE, pas a l'ecriture --
    # c'est la QUATRIEME recidive du gisement, toujours par notre propre cadence de portage.
    ("playbook/non_owner_attack.py", "_has_trait", "c.traits", "R"):
        ("INERTE-VIVANT", "le sujet est `caster` = `UtilityAttackCase+0x10`, l'unite dont l'IA "
                          "evalue l'action : elle est vivante par construction du cas d'utilite. "
                          "S'y ajoute que `Scene.ctx_by_id` vient du `predictor`, donc de "
                          "`combatSnapshot`, donc des VIVANTS seuls -> `c is None` sur un cadavre "
                          "et la fonction rend FAUX, jamais un trait devine"),

    # ---- INDECIDABLE : NON converti, et nomme comme tel ----------------------------------------
    ("runner/components.py", "__init__", "sc.ctx.traits", "R"):
        ("INDECIDABLE", "`UnitEffectStateView` -- substrat des `CreateActiveCondition`. Le seul "
                        "driver enumere (`refresh_stat_modifier_effects`) sort sur `us is None` "
                        "donc n'atteint aucun cadavre, mais les ~15 autres appelants "
                        "d'`active_effects` n'ont PAS ete enumeres. Cle absente = condition de "
                        "TRAIT degradee en VRAI (#208), donc degradation PERMISSIVE"),
    ("playbook/scene.py", "unit_state", "getattr(c)", "R"):
        ("INDECIDABLE", "face DECISION du precedent, meme raison et meme degradation"),

    # ---- 2026-08-14 : QUATRE sites arrives par les tranches de la journee -----------------------
    # Le cliquet a rougi sur `master` APRES coup -- ces sites viennent de #1015-r1 (les deux faces
    # de `CloseCombatWeakness` et d'`InstinctiveBehaviour`) et de #1001. Aucune des PR qui les a
    # crees ne jouait ce fichier : il se declenche sur TOUTE lecture de `traits` sous `engine/`,
    # donc AUCUNE passe derivee du diff ne l'atteint. Ventiles ici, site par site, par leur ROUTE
    # REELLE -- jamais en recopiant le motif d'un frere de meme fichier.
    ("entities/effect_targets.py", "_synapse_targets", "world.traits", "R"):
        ("HORS-ECS", "`tr = world.traits(uid) or ()` -- appel de METHODE du pont `world`, pas une "
                     "lecture de ctx. MEME forme que `_surrounding_enemy_psykers_r2` du meme "
                     "fichier ; les deux implementations du pont sont ventilees a leur propre "
                     "ligne (`scene.py::traits` cote DECISION)"),
    ("playbook/scene.py", "close_combat_weakness_adjacent_enemies", "getattr(c)", "R"):
        ("INERTE-VIVANT", "boucle sur `self.units` gatee par `_adj.unit_matches(self, u)`, dont le "
                          "`selection_type` par defaut est `OnlyAliveAndTargetable` et qui lit "
                          "`alive=bool(u.get('alive'))`. ⚠ La route N'EST PAS celle de son frere "
                          "`_enmity_adjacent`, qui porte un `not u.alive -> continue` LITTERAL en "
                          "tete : ici le gate passe par le mirror de "
                          "`UnitExtensions$$MatchesUnitSelectionType`. Meme verdict, autre chemin"),
    ("runner/operations/triggers/loki/blade_of_the_ancestors.py", "_traits_of", "getattr(sc.ctx)",
     "R"):
        ("INERTE-AMONT", "helper a DEUX appelants, tous deux enumeres. `_friendly_hero` recoit "
                         "`ev.dying_id` (branche 1) puis `ev.actor_id` (branche 2) ; "
                         "`_is_normal_unit` recoit `dying`. Un `dying_id` est mort PENDANT le run "
                         "-- il PORTE son `StatsComponent` (P1 : absent <=> mort AU CHARGEMENT) -- "
                         "et un `actor_id` est l'acteur vivant de l'event. Aucun cadavre-au-"
                         "chargement n'est jamais passe. MEME forme que `cosmic_horror.py::"
                         "_traits_of`, et le repli `[]` sur `sc is None` reste inatteignable"),
    ("runner/snapshot.py", "_load_stats_and_effects", "getattr(sc.ctx)", "R"):
        ("INERTE-VIVANT", "boucle `for eid in state.entities` gatee par `sc is None or uc is None "
                          "or not uc.visual_id -> continue`. Le premier conjoint EST le cadavre-au-"
                          "chargement, par P1 -- il est donc ecarte AVANT la lecture, comme dans "
                          "`control_edict.py::_adjacent_mechanical_summons`. Ce site pose les "
                          "owner-effects de trait (dont `1235 InstinctiveBehaviour_BlockMovement`, "
                          "#1015-r1) : les poser sur un cadavre serait un effet sans porteur"),
}

# Les DEUX sites que la ventilation a rendus ATTEIGNABLES, et que cette tranche a CONVERTIS.
# Ils ne doivent plus figurer a l'inventaire (la lecture brute a disparu) ET doivent porter les
# DEUX marques de la conversion. Le second volet est de la PROVENANCE, par AST : une recopie
# locale strictement equivalente est comportementalement indistinguable, donc AUCUN critere de
# VALEUR ne peut la voir (angle mort mesure en #643 puis en #646).
CONVERTIS = {
    ("runner/operations/triggers/genestealer.py", "_valid_dead_decoys"):
        "`Filter(AllDeadUnits, ...)` : le sujet EST un mort",
}

# Le SECOND site converti par cette tranche -- `move_death.py::post_unit_kill_triggers_for_move` --
# n'existe PLUS depuis #462-r4b-r1-r1-r1-r1-c-r3-r1-r4 : `On(0x35 = PostUnitKill)` est publie par
# `damage.py::_kill_unit_operation`, a son rang natif, donc plus aucune re-identification du crushe
# par co-localisation n'a lieu. La garantie que sa conversion protegeait -- << ne jamais rendre ses
# traits a un cadavre-au-chargement, que le conjoint natif `IsKilledThisTurn` REFUSE >> -- n'est
# pas perdue : elle remonte d'un cran et devient STRUCTURELLE (le gate `uc.alive` de
# `_kill_steppable_units` : un cadavre n'est jamais crushe, donc n'entre jamais dans le foyer).
# Elle reste EXERCEE, sur le chemin reel, par `--step disparu` et par le test homonyme.
DISPARUS = {
    ("runner/operations/triggers/dispatch/move_death.py", "post_unit_kill_triggers_for_move"):
        ("#462-r4b-r1-r1-r1-r1-c-r3-r1-r4", "movement.py", "_kill_steppable_units"),
}

VERDICTS_ATTEIGNABLES = ("ATTEIGNABLE",)


def _cle(s):
    return (s[0], s[1], s[2], s[3])


def _fonction_ast(fichier: str, fonction: str):
    """L'AST de la fonction `fonction` du module `engine/<fichier>` (None si introuvable)."""
    tree = ast.parse((ENGINE / fichier).read_text(encoding="utf-8"))
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == fonction:
            return n
    return None


def etat_conversion() -> list:
    """Pour chaque site CONVERTI : (cle, brut_absent, appelle_foyer, gate_explicite, motif).

    * `brut_absent`    : plus aucune lecture brute de `traits` dans la fonction ;
    * `appelle_foyer`  : la fonction APPELLE `entity_trait_names` (AST, pas grep -- un appel
                         dans un commentaire ne compte pas) ;
    * `gate_explicite` : la fonction LIT `killed_this_turn` -- le substrat NATIF du conjoint
                         `IsKilledThisTurn` (`UnitComponent+0x17a`). Sans ce gate, reparer le
                         substrat de traits ferait entrer dans le selecteur un mort que le natif
                         REFUSE.
                         ⚠ LE CRITERE A CHANGE en #462-r4b-r1-r1-r1-r1-b-r1-r1-r3-r1-r3 : il
                         cherchait un test `sc is None`, qui n'etait qu'un ARTEFACT du port
                         (« pas de `StatsComponent` » ⇒ « pas tue ce tour »). Un artefact ne peut
                         pas garder un conjoint : il tenait par coincidence, et le jour ou un
                         `StatsComponent` sera pose sur les cadavres il tombait en SILENCE. Le
                         critere est desormais le NOM du champ natif."""
    bruts = {}
    for s in sites():
        bruts.setdefault((s[0], s[1]), 0)
        bruts[(s[0], s[1])] += 1
    out = []
    for cle, motif in sorted(CONVERTIS.items()):
        fn = _fonction_ast(*cle)
        appelle = foyer_gate = False
        if fn is not None:
            appelle = any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                          and n.func.id == "entity_trait_names" for n in ast.walk(fn))
            foyer_gate = any(isinstance(n, ast.Attribute) and n.attr == "killed_this_turn"
                             for n in ast.walk(fn))
        out.append((cle, bruts.get(cle, 0) == 0, appelle, foyer_gate, motif))
    return out


def step_inventaire() -> int:
    lst = sites()
    fichiers = sorted({s[0] for s in lst})
    lectures = [s for s in lst if s[3] == "R"]
    ecritures = [s for s in lst if s[3] == "W"]
    foyer = [s for s in lectures if (s[0], s[1]) == FOYER]
    print("INVENTAIRE -- acces a l'attribut `traits` sous `engine/` (AST, jamais grep)")
    print("")
    par_fichier = {}
    for s in lst:
        par_fichier.setdefault(s[0], []).append(s)
    for f in fichiers:
        rows = sorted(par_fichier[f], key=lambda r: r[4])
        print("  %-54s %d" % (f, len(rows)))
        for r in rows:
            print("      %5d  %-1s  %-34s %s" % (r[4], r[3], r[2], r[1]))
    print("")
    print("sites TOTAL           : %d" % len(lst))
    print("  dont ECRITURES      : %d" % len(ecritures))
    print("  dont LECTURES       : %d" % len(lectures))
    print("    dont FOYER        : %d" % len(foyer))
    print("    LECTURES BRUTES   : %d   <-- le gisement du patron"
          % (len(lectures) - len(foyer)))
    print("fichiers              : %d" % len(fichiers))
    print("cles de ventilation   : %d" % len({_cle(s) for s in lst}))
    print("")
    print("Le chiffre annonce par la fiche `-r3` etait APPROCHE (54 sites / 29 fichiers, balayage")
    print("incluant de la prose de docstring). Celui-ci est re-derive : ne pas le recopier non plus,")
    print("le rejouer.")
    return 0


def step_ventilation() -> int:
    lst = sites()
    cles = {}
    for s in lst:
        cles.setdefault(_cle(s), []).append(s)
    manquantes = sorted(k for k in cles if k not in VENTILATION)
    orphelines = sorted(k for k in VENTILATION if k not in cles)
    par_verdict = {}
    for k, occ in cles.items():
        v = VENTILATION.get(k, ("NON-VENTILE", ""))[0]
        par_verdict.setdefault(v, []).append((k, len(occ)))
    print("VENTILATION -- le sujet peut-il etre une entite chargee DEJA MORTE ?")
    print("")
    for v in sorted(par_verdict):
        rows = sorted(par_verdict[v])
        n = sum(c for _k, c in rows)
        print("== %-14s %d site(s) / %d cle(s)" % (v, n, len(rows)))
        if v in VERDICTS_ATTEIGNABLES or v in ("INDECIDABLE", "NON-VENTILE"):
            for k, c in rows:
                print("     %s::%s  (%s) x%d" % (k[0], k[1], k[2], c))
                motif = VENTILATION.get(k, (None, ""))[1]
                if motif:
                    print("        %s" % motif)
    print("")
    rc = 0
    if manquantes:
        rc = 1
        print("ROUGE -- %d site(s) trouve(s) que la table ne ventile PAS :" % len(manquantes))
        for k in manquantes:
            print("     %s::%s  (%s, %s)" % k)
        print("  Un site neuf n'est pas un detail : la ventilation de cette tranche ne dit RIEN de")
        print("  lui. Le ventiler (sujet vivant ou mort ?) fait partie du changement qui l'a cree.")
    if orphelines:
        rc = 1
        print("ROUGE -- %d entree(s) de table sans site correspondant (site deplace ou supprime) :"
              % len(orphelines))
        for k in orphelines:
            print("     %s::%s  (%s, %s)" % k)
    if rc == 0:
        print("table et inventaire COINCIDENT (%d cles)." % len(cles))
    print("")
    print("== CONVERTIS  %d site(s) -- la ventilation les avait rendus ATTEIGNABLES" % len(CONVERTIS))
    for cle, brut_absent, appelle, gate, motif in etat_conversion():
        print("     %s::%s" % cle)
        print("        %s" % motif)
        print("        lecture brute disparue = %s | appelle entity_trait_names = %s | "
              "gate `sc is None` = %s" % (brut_absent, appelle, gate))
        if not (brut_absent and appelle and gate):
            rc = 1
            print("        ROUGE : la conversion est incomplete ou defaite.")
    return rc


# ================================================================================================
# --step loi : les DEUX premisses, verifiees executablement
# ================================================================================================
def _etat_charge():
    """Un `State` produit par le VRAI `snapshot.load_state` : deux unites publiees par
    `decisionView` (l'une vivante, l'autre morte), un `combatSnapshot` qui ne porte QUE la
    vivante -- exactement ce que le capteur produit (`allUnits` filtre par `IsAlive`)."""
    from engine.runner.snapshot import load_state
    decision = {"units": [
        {"id": 1, "visualId": "astraBullgryn", "team": 1, "owner": 3, "alive": True,
         "pos": {"col": 1, "row": 1}, "hp": 100, "hpMax": 100},
        {"id": 2, "visualId": "necroWarden", "team": 2, "owner": 4, "alive": False,
         "pos": {"col": 2, "row": 2}, "hp": 0, "hpMax": 100},
    ]}
    snapshot = {"units": [{"entityId": 1, "entityType": 0, "stats": {}, "unitConfig": None}]}
    return load_state(decision, {}, snapshot)


def step_loi() -> int:
    from engine.runner.components import StatsComponent, UnitComponent
    rc = 0
    print("LOI DE VENTILATION -- les deux premisses, verifiees et non supposees")
    print("")

    # ---- P1 -----------------------------------------------------------------------------------
    print("P1 : `StatsComponent` ABSENT <=> `UnitComponent.alive == False` au chargement")
    st = _etat_charge()
    for uid in (1, 2):
        e = st.get_entity(uid)
        uc = e.get_component(UnitComponent) if e is not None else None
        sc = e.get_component(StatsComponent) if e is not None else None
        print("    eid=%d  alive=%s  StatsComponent=%s"
              % (uid, None if uc is None else uc.alive, sc is not None))
    e1, e2 = st.get_entity(1), st.get_entity(2)
    ok1 = (e1 is not None and e1.get_component(StatsComponent) is not None
           and e2 is not None and e2.get_component(StatsComponent) is None
           and e2.get_component(UnitComponent).alive is False)
    print("    -> %s" % ("VERIFIE" if ok1 else "REFUTE"))
    if not ok1:
        rc = 1
        print("    Si cette premisse tombe, TOUTE la ventilation de cette tranche est a refaire :")
        print("    elle repose sur << ctx absent == cadavre >>.")
    print("")
    print("    Cote CAPTEUR, la meme equivalence se lit dans le hook (citation, pas mesure) :")
    print("      `rpc-snapshot.ts`, bloc `allUnits` : `if (!invokeBool(isAliveMi, [e, statePtr]))")
    print("        return;`  -> combatSnapshot = les seules entites `IsAlive`")
    print("      `projection.ts`                    : `alive: invokeBool(isAliveMi, [e, statePtr])`")
    print("        -> `decisionView.units[].alive` invoque LA MEME methode native")
    print("")

    # ---- P2 -----------------------------------------------------------------------------------
    print("P2 : aucune voie du port ne rend VIVANTE une entite chargee morte")
    from engine.runner.operations.triggers.genestealer import _eligible_for_resurrect
    from engine.runner.components import OwnerComponent, UnitFlagsComponent
    import gameconfig as GC
    from engine.runner.state import State, Entity
    from engine.entities.unit_context import UnitContext

    def _cadavre_ambush(avec_turn_defeated: bool):
        """Un porteur `Ambush` MORT. `avec_turn_defeated` distingue le mort DU RUN (le seul que
        `AmbushSummonAbility` horodate) du cadavre AU CHARGEMENT (jamais horodate)."""
        st2 = State()
        e = Entity(7)
        uc = UnitComponent(visual_id="genesPrimus", alive=False)
        if avec_turn_defeated:
            uc.turn_defeated = 0
        e.add_component(uc)
        e.add_component(OwnerComponent(team=1, player=3))
        e.add_component(UnitFlagsComponent())
        ctx = UnitContext.__new__(UnitContext)
        ctx.visual_id = "genesPrimus"
        ctx.traits = list((GC.unit("genesPrimus") or {}).get("traits") or ())
        ctx.traits_measured = False
        e.add_component(StatsComponent(ctx))
        st2.entities[7] = e
        st2.turn_counts = {3: 1}
        return st2

    du_run = _eligible_for_resurrect(_cadavre_ambush(True), 3)
    au_chargement = _eligible_for_resurrect(_cadavre_ambush(False), 3)
    print("    `_eligible_for_resurrect` sur un porteur Ambush mort :")
    print("        horodate (mort PENDANT le run)     -> %r" % (du_run,))
    print("        NON horodate (cadavre AU CHARGEMENT) -> %r" % (au_chargement,))
    ok2 = bool(du_run) and not au_chargement
    print("    -> %s" % ("VERIFIE" if ok2 else "REFUTE"))
    if not ok2:
        rc = 1
        print("    Une voie de resurrection s'est ouverte : les verdicts INERTE-VIVANT de la table")
        print("    ne tiennent plus, il faut les re-instruire un par un.")
    print("")
    print("    L'autre Operation qui repose `alive = True` est `ReviveUnitOperation$$Execute`,")
    print("    dont l'unique appelant porte est `kill_unit_revive_gate` -- appele par")
    print("    `_fire_death_if_killed`, donc sur une mort SURVENUE PENDANT LE RUN. Un cadavre")
    print("    au chargement ne re-meurt pas : il n'a aucun chemin vers ce gate.")
    return rc


# ================================================================================================
# --step contre : la contre-epreuve DIRIGEE des deux sites ATTEIGNABLES
# ================================================================================================
_ABSENT_CRUSH = object()          # sentinelle : « laisse le defaut derive d'`avec_stats` »


def etat_crush(vis_mort: str, avec_stats: bool, vivant: bool = False,
               tue_ce_tour=_ABSENT_CRUSH, tueur=_ABSENT_CRUSH):
    """Mover (eid 1) et une unite co-localisee (eid 2) de visualId `vis_mort`.

    `avec_stats=False` reproduit le CADAVRE AU CHARGEMENT (absent de `combatSnapshot`) ;
    `True` reproduit le crush SURVENU PENDANT LE RUN (l'entite garde son ctx).

    `vivant=True` monte l'eid 2 VIVANTE : c'est l'ENTREE du crush, pas son resultat -- le regime
    qu'il faut pour exercer `_kill_steppable_units` lui-meme (#462-r4b-r1-r1-r1-r1-c-r3-r1-r4).

    ⚠ LE MORT DU RUN PORTE DESORMAIS LES DEUX CHAMPS QUE LE VRAI CRUSH POSE
    (#462-r4b-r1-r1-r1-r1-b-r1-r1-r3-r1-r3), parce que `_valid_dead_decoys` les LIT :
    `movement.py::_kill_steppable_kill_unit` appelle `_record_death_reason(dead, mover,
    DamageReason.Steppable)` -- d'ou `death_source = (1, 2, None)` -- PUIS
    `damage.py::_kill_unit_operation`, qui pose `killed_this_turn = True`
    (`KillUnitOperation$$Execute+0x828`). Un cadavre-AU-CHARGEMENT n'a ni l'un ni l'autre.
    Les deux surcharges `tue_ce_tour` / `tueur` existent pour ISOLER chaque conjoint : sans elles,
    trois choses changent d'un bras a l'autre et aucun verdict n'est attribuable."""
    import gameconfig as GC
    from engine.runner.state import State, Entity
    from engine.runner.components import (UnitComponent, OwnerComponent, PositionComponent,
                                          HealthComponent, StatsComponent)
    from engine.entities.damage_reason import DamageReason
    from engine.entities.unit_context import UnitContext
    st = State()

    def _add(uid, vis, team, alive, stats):
        e = Entity(uid)
        e.add_component(UnitComponent(visual_id=vis, alive=alive))
        e.add_component(OwnerComponent(team=team, player=team + 2))
        e.add_component(PositionComponent(col=3, row=3))
        e.add_component(HealthComponent(hp=100 if alive else 0, hp_max=100))
        if stats:
            ctx = UnitContext.__new__(UnitContext)
            ctx.visual_id = vis
            ctx.traits = list((GC.unit(vis) or {}).get("traits") or ())
            ctx.traits_measured = False
            e.add_component(StatsComponent(ctx))
        st.entities[uid] = e
        return e

    _add(1, "astraBullgryn", 1, True, True)             # le mover, toujours charge
    mort = _add(2, vis_mort, 1, vivant, avec_stats)     # le co-localise (meme team : G2 friends)
    # Le crush du RUN grave les deux champs ; le cadavre-au-chargement n'en a aucun.
    # `None` (et NON `False`) hors du regime crush : c'est le tri-etat « NON MESURE » -- aucun canal
    # live ne publie `UnitComponent+0x17a`, donc un cadavre-AU-CHARGEMENT ne PEUT pas porter `False`.
    tue = (True if (avec_stats and not vivant) else None) if tue_ce_tour is _ABSENT_CRUSH \
        else tue_ce_tour
    kid = (1 if (avec_stats and not vivant) else None) if tueur is _ABSENT_CRUSH else tueur
    uc = mort.get_component(UnitComponent)
    uc.killed_this_turn = tue
    uc.death_source = None if kid is None else (int(kid), int(DamageReason.Steppable), None)
    return st


def etat_disparus() -> list:
    """Pour chaque site DISPARU : (cle, absent_du_module, porteur_present, porteur_gate).

    * `absent_du_module` : la fonction supprimee n'est PAS revenue (si elle revenait sans que le
      foyer soit revu, le chemin MOVE emettrait `On(0x35)` DEUX fois) ;
    * `porteur_present`  : la fonction qui porte desormais la garantie existe bien ;
    * `porteur_gate`     : elle porte un test sur `uc.alive` -- c'est LUI qui empeche un
      cadavre-au-chargement d'entrer dans le foyer de mort."""
    out = []
    for cle, (_tranche, fich_porteur, fn_porteur) in sorted(DISPARUS.items()):
        absent = _fonction_ast(*cle) is None
        porteur = _fonction_ast(fich_porteur if fich_porteur.startswith("runner/")
                                else "runner/operations/" + fich_porteur, fn_porteur)
        gate = False
        if porteur is not None:
            gate = any(isinstance(n, ast.Attribute) and n.attr == "alive"
                       and isinstance(n.value, ast.Name) and n.value.id == "uc"
                       for n in ast.walk(porteur))
        out.append((cle, absent, porteur is not None, gate))
    return out


def step_contre() -> int:
    from engine.entities.traits.unit_trait import entity_trait_names
    from engine.runner.components import StatsComponent, UnitComponent
    print("CONTRE-EPREUVE DIRIGEE -- pourquoi convertir SEUL les deux sites ATTEIGNABLES aurait")
    print("ete une REGRESSION, et ce que la conversion livree change (ou non).")
    print("")
    for vis in ("genesSmnDecoy",):
        for avec in (True, False):
            st = etat_crush(vis, avec)
            e = st.get_entity(2)
            sc = e.get_component(StatsComponent)
            uc = e.get_component(UnitComponent)
            brut = set(getattr(sc.ctx, "traits", None) or ()) if sc is not None else set()
            foyer = set(entity_trait_names(sc.ctx if sc is not None else None, uc.visual_id))
            regime = "mort PENDANT le run" if avec else "cadavre AU CHARGEMENT"
            print("  %-24s (%s)" % (vis, regime))
            print("      substrat BRUT  = %s" % (sorted(brut),))
            print("      substrat FOYER = %s" % (sorted(foyer),))
            print("      port `killed_this_turn` = %r ; `death_source` = %r"
                  % (uc.killed_this_turn, uc.death_source))
    print("")
    print("Lecture : dans le regime CADAVRE, le foyer rend `Decoy`/`Steppable` la ou le brut rendait")
    print("`[]`. Une conversion NUE aurait donc fait ENTRER dans `GetValidDeadDecoys` un mort que le")
    print("conjoint natif `IsKilledThisTurn` REFUSE -- le port aurait blaste sans kill.")
    print("")
    print("DEPUIS #462-r4b-r1-r1-r1-r1-b-r1-r1-r3-r1-r3, le gate n'est PLUS `sc is None` (un")
    print("artefact du port) : les deux conjoints ont leur substrat NATIF, et ils ne refusent pas")
    print("les memes morts. Les quatre bras ci-dessous le montrent.")
    print("")
    from engine.runner.operations.triggers.genestealer import _valid_dead_decoys
    bras = (
        ("mort du run, crushe PAR le stepper", dict(avec_stats=True), [2]),
        ("cadavre AU CHARGEMENT (rien de mesure)", dict(avec_stats=False), []),
        ("mort du run, mais a REDEMARRE un tour depuis (killed_this_turn=False)",
         dict(avec_stats=True, tue_ce_tour=False), []),
        ("mort du run, tue par une AUTRE unite (Killer != stepper)",
         dict(avec_stats=True, tueur=99), []),
    )
    rc = 0
    for libelle, kw, attendu in bras:
        got = _valid_dead_decoys(etat_crush("genesSmnDecoy", **kw), owner_id=1, stepper_id=1)
        if got != attendu:
            rc = 1
        print("  [%s] %-62s -> %r (attendu %r)"
              % ("OK " if got == attendu else "ROUGE", libelle, got, attendu))
    print("")
    print("Le 4e bras est celui que le COLLAPSE laissait passer : rien ne libere la tuile d'un decoy")
    print("mort, donc un stepper ami qui marche dessus PLUS TARD satisfaisait la co-localisation.")
    return rc


def step_disparu() -> int:
    """Les sites SUPPRIMES : la garantie a-t-elle bien un porteur, et son gate est-il la ?"""
    print("SITES DISPARUS -- ou est passee la garantie qu'ils portaient")
    print("")
    rc = 0
    for cle, absent, porteur, gate in etat_disparus():
        tranche, fich, fn = DISPARUS[cle]
        print("  %s::%s   (%s)" % (cle[0], cle[1], tranche))
        print("      supprime (non revenu)      : %s" % ("OUI" if absent else "NON  <-- ROUGE"))
        print("      porteur %s::%s" % (fich, fn))
        print("        present                  : %s" % ("OUI" if porteur else "NON  <-- ROUGE"))
        print("        porte le gate `uc.alive` : %s" % ("OUI" if gate else "NON  <-- ROUGE"))
        if not (absent and porteur and gate):
            rc = 1
    print("")
    print("Un `NON` sur la 1re ligne = le site est REVENU : le chemin MOVE emettrait")
    print("`On(0x35 = PostUnitKill)` DEUX fois (foyer + re-identification). Un `NON` sur les deux")
    print("autres = la garantie n'a plus de porteur, et un cadavre-au-chargement peut entrer.")
    return rc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", required=True,
                    choices=("inventaire", "ventilation", "loi", "contre", "disparu"))
    a = ap.parse_args()
    return {"inventaire": step_inventaire, "ventilation": step_ventilation,
            "loi": step_loi, "contre": step_contre, "disparu": step_disparu}[a.step]()


if __name__ == "__main__":
    raise SystemExit(main())
