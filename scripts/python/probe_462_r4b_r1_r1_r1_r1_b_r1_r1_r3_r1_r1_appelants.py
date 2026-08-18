"""#462-r4b-r1-r1-r1-r1-b-r1-r1-r3-r1-r1 (+ -r2) -- CE QUE LE PORT SAIT D'UNE UNITE MORTE :
l'ENUMERATION des appelants du substrat `unit_state`, et le REGISTRE des triggered-abilities.

Deux residus, un seul substrat -- << une entite chargee MORTE >> (dite CADAVRE-AU-CHARGEMENT :
presente dans `decisionView.units[]`, `alive == False`, SANS `StatsComponent` parce que
`combatSnapshot` n'enumere que les `IsAlive`).

  * `-r1` : les DEUX sites `INDECIDABLE` de la ventilation `#462-...-r3-r1`
    (`runner/components.py::UnitEffectStateView.__init__` et `playbook/scene.py::Scene.unit_state`)
    lisent `ctx.traits` BRUT. Le seul driver enumere (`refresh_stat_modifier_effects`) sort sur
    `us is None`, mais les AUTRES appelants n'avaient PAS ete enumeres. Ce probe les enumere -- par
    AST, jamais par grep -- et les VENTILE.
  * `-r2` : `triggers/dispatch/core.py::collect_triggered_abilities` fait `if sc is None: continue`,
    donc un cadavre-au-chargement est HORS du registre. La question natif etait ouverte ; elle est
    tranchee ici (`--step registre`).

CE QUE LA MESURE A CHANGE PAR RAPPORT A L'ENONCE DES DEUX RESIDUS :

  1. La degradation permissive a UN SEUL consommateur, et il se MESURE (`--step consommateur`).
     `-r1` dit << cle `traits` absente ⇒ une condition de TRAIT rend VRAI (#208) >>, ce qui est
     exact -- mais une seule `is_active` de tout `engine/` lit cette cle. Un site n'est donc un
     gisement que si son sujet peut etre un cadavre ET que le consommateur aval lit CET effet-la.
  2. La question de `-r2` ne se tranche PAS sur `AbilityAndEffectCache` : elle se tranche un cran
     plus bas, sur `IdunBattle.Operations.EvaluateTriggerOperation$$CanGetAbilityTrigger`
     (`--step registre`).

100 % OFFLINE. ASCII only (cp1252).
"""
from __future__ import annotations

import argparse
import ast
import os
import sys
from pathlib import Path

ICI = Path(__file__).resolve().parent
if str(ICI) not in sys.path:
    sys.path.insert(0, str(ICI))

ENGINE = ICI / "engine"

# #547-r11 : le tri des porteurs `fire_on_death` se fait sur des MEMBRES, plus sur des libelles
# (cf. `EVENTS_DE_SA_PROPRE_MORT`). Import de TETE, forme A assumee : un enum est une feuille, il
# n'ouvre aucun cycle et aucun test ne le substitue.
from engine.dsl.event_trigger_type import EventTriggerType   # noqa: E402


# ================================================================================================
# INVENTAIRE -- AST, jamais grep
# ================================================================================================
def _proprio(tree: ast.AST) -> dict:
    """{ligne: nom de la fonction/classe la PLUS INTERIEURE qui la couvre}."""
    owner: dict = {}
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for i in range(n.lineno, (n.end_lineno or n.lineno) + 1):
                prev = owner.get(i)
                owner[i] = (n.name, n.lineno) if prev is None or n.lineno > prev[1] else prev
    return owner


def _fichiers():
    for dirpath, _d, files in os.walk(ENGINE):
        for fn in sorted(files):
            if fn.endswith(".py"):
                p = Path(dirpath) / fn
                yield os.path.relpath(p, ENGINE).replace("\\", "/"), p


# Les DEUX faces du meme substrat. La cle de ventilation est `(fichier, fonction, methode)` : elle
# survit a un deplacement de lignes, ce qu'un couple `(fichier, ligne)` ne fait pas.
_METHODES = {
    "active_effects": "COMBAT",       # `EffectsState.active_effects(uid, unit_state)`
    "unit_state": "DECISION",         # `Scene.unit_state(uid)` -- le substrat lui-meme
    # #462-...-r1-r1-r1 : le PORTAIL de la face DECISION. `Scene.effects(uid)` appelle
    # `unit_state(uid)` puis `EffectsState.active_effects` -- tout appelant du portail est donc un
    # lecteur du substrat, au meme titre que les appelants directs. Les ventiler EXIGE de les
    # enumerer : la tranche precedente les avait comptes (<< ~30 >>) sans les nommer.
    "effects": "DECISION",
}


def sites() -> list:
    """Tous les appels `<x>.active_effects(...)` et `<x>.unit_state(...)` sous `engine/`.

    Rend `(fichier, fonction, methode, face, ligne, arg0)`. Le foyer `EffectsState.active_effects`
    et `Scene.unit_state` (les DEFINITIONS) sont exclus : ce sont les substrats, pas des appelants.
    """
    out = []
    for rel, p in _fichiers():
        tree = ast.parse(p.read_text(encoding="utf-8"))
        owner = _proprio(tree)
        for n in ast.walk(tree):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)):
                continue
            face = _METHODES.get(n.func.attr)
            if face is None:
                continue
            fn = owner.get(n.lineno, ("<module>", 0))[0]
            if (rel, fn) in (("entities/effects_state.py", "active_effects"),
                             ("playbook/scene.py", "unit_state")):
                continue                              # la DEFINITION, pas un appelant
            arg0 = ast.unparse(n.args[0]) if n.args else "<aucun>"
            out.append((rel, fn, n.func.attr, face, n.lineno, arg0))
    return out


def cle(s) -> tuple:
    return (s[0], s[1], s[2])


# ================================================================================================
# VENTILATION -- un verdict PAR CLE, avec son MOTIF
# ================================================================================================
# Verdicts (memes noms que `probe_462_..._r3_r1_substrat_traits.py`, pour qu'un lecteur qui connait
# l'un lise l'autre) :
#   INERTE-VIVANT  le sujet est un COMBATTANT du coup en cours (attaquant / defenseur / caster /
#                  cible) : il est vivant par construction du vecteur qui appelle
#   INERTE-AMONT   un gate ANTERIEUR (dans la meme fonction) refuse le cadavre avant la lecture
#   INERTE-AVAL    la lecture est atteinte pour un cadavre, mais AUCUN OBSERVABLE n'en depend --
#                  soit le consommateur ne lit aucun effet degrade, soit son verdict est le meme
#                  dans les deux branches, soit LE NATIF SUIT LE MEME CHEMIN (#547-r11 : sur la
#                  face EFFET, `_owner_gate_applies` est FAUX des DEUX cotes)
#   ATTEIGNABLE    le sujet PEUT etre un cadavre-au-chargement, rien dans la fonction ne l'ecarte,
#                  ET LE PORT DIVERGE DU NATIF. ⚠ Ce verdict DECLARE UNE DETTE : le cliquet
#                  `test_aucun_verdict_ATTEIGNABLE_ne_reste_sans_gate` exige alors un gate au
#                  registre `BALAYAGES`. Ne l'ecrire que si la divergence est MESUREE -- un site
#                  que le natif atteint AUSSI est INERTE-AVAL, pas une dette
#   NON-VENTILE    face DECISION -- enumere, pas trie (residu, cf. l'en-tete de `step_ventilation`)
VENTILATION = {
    # ---- face COMBAT : les sujets qui sont des COMBATTANTS ------------------------------------
    ("runner/damage_model.py", "attacker_modifiers", "active_effects"):
        ("INERTE-VIVANT", "`unit_id` = l'ATTAQUANT du coup en cours"),
    ("runner/damage_model.py", "defender_modifiers", "active_effects"):
        ("INERTE-VIVANT", "DEUX appels dans cette fonction, et ils ne sont pas de meme nature : "
                          "le PREMIER porte sur `unit_id` = le DEFENDEUR du coup (vivant par "
                          "construction -- le ciblage natif ne rend pas un mort cible legale) ; le "
                          "SECOND balaie les porteurs d'aura et porte son propre gate `hp <= 0`, "
                          "cf. la note de `_apply_ally_attack_damage_auras`"),
    ("runner/damage_model.py", "apply_trench_reduction", "active_effects"):
        ("INERTE-VIVANT", "`target_id` = la CIBLE du coup"),
    ("runner/damage_model.py", "_has_no_elev", "active_effects"):
        ("INERTE-VIVANT", "appele sur `attacker_id` PUIS `target_id` -- les deux combattants"),
    ("runner/abilities/base.py", "ability_pierce_effect_bonus", "active_effects"):
        ("INERTE-VIVANT", "`caster_id` = le CASTER : un mort ne caste pas"),
    ("runner/operations/repair.py", "_repair_modifier", "active_effects"):
        ("INERTE-VIVANT", "`target_id` d'un REPAIR ; `IdunBattle.Core.Services.AttackQuery$$"
                          "EntityCanBeRepaired` gate la cible en amont du vecteur"),
    ("runner/operations/damage_ops/ability.py", "execute_ability_attack", "active_effects"):
        ("INERTE-VIVANT", "`target_id` de l'attaque d'ability en cours"),
    ("runner/components.py", "unit_prevents_overkill", "active_effects"):
        ("INERTE-VIVANT", "`unit_id` = l'unite dont on decide l'OVERKILL, donc celle qu'on est en "
                          "train de tuer : elle est vivante a l'instant du test"),
    ("runner/operations/triggers/loki/reactivate_overwatch.py", "matches", "active_effects"):
        ("INERTE-AMONT", "`self.owner_id` -- le gate d'owner de `evaluate_trigger_operation` "
                         "(`CanGetAbilityTrigger`, `uc.alive` sauf `fire_on_death`) precede tout "
                         "`matches`, et cette classe ne porte PAS `fire_on_death`"),

    # ---- face COMBAT : les BALAYAGES d'entites -- c'est la que le gisement se joue -------------
    ("runner/damage_model.py", "normal_attack_per_hit_range", "active_effects"):
        ("INERTE-AMONT", "`if sc is None: return None` SIX lignes plus haut -- un "
                         "cadavre-au-chargement n'atteint jamais la lecture"),
    ("runner/damage_model.py", "_apply_ally_attack_damage_auras", "active_effects"):
        ("INERTE-AMONT", "balayage de `state.entities`, gate `hc.hp <= 0 -> continue` juste "
                         "au-dessus. ⚠ Le gate est sur les PV, pas sur `uc.alive` : il tient parce "
                         "que `snapshot._hp_by_id` lit `observe.units[].hp`, qui vaut 0 pour un "
                         "mort. Une capture sans `hp` (cle absente -> `HealthComponent` non pose) "
                         "le rendrait inerte"),
    ("runner/damage_model.py", "build_hits_board", "active_effects"):
        ("INERTE-AMONT", "balayage de `state.entities` sous le gate `#57m` "
                         "(`uid != tgt_id and not _uc.alive -> continue`) : le board natif est une "
                         "OCCUPATION DE TUILE, un mort n'y est plus"),
    ("runner/operations/damage.py", "_crit_carriers", "active_effects"):
        ("INERTE-AMONT", "meme balayage, meme gate `#57m` que `build_hits_board`"),
    ("runner/operations/additional_hits.py", "collect_additional_hit_groups", "active_effects"):
        ("INERTE-AMONT", "balayage de `state.entities`, gate `not uc.alive -> continue`"),
    ("runner/damage_model.py", "defender_fixed_armor", "active_effects"):
        ("ATTEIGNABLE", "LE SEUL des six balayages qui n'avait AUCUN gate de vivacite : ses filtres "
                        "etaient `OwnerComponent`, `PositionComponent` et l'egalite d'equipe. Un "
                        "cadavre-au-chargement de l'equipe du defenseur, s'il a une position, ETAIT "
                        "visite -- et `decisionView.units[]` conserve les morts, donc "
                        "`snapshot._load_stats_and_effects` les seede dans `EffectsState`. "
                        "TRAITE PAR CETTE TRANCHE (gate `uc.alive`, cf. `--step gates`) ; ce que le "
                        "gate ferme et ce qu'il ne ferme PAS : `--step gisement`"),

    # ---- #547-r11 : TROIS APPELANTS NEUFS de la face COMBAT ------------------------------------
    # Le cliquet d'exhaustivite a mordu comme il devait : trois sites `active_effects` sont apparus
    # sans ventilation. Un par un, avec le gate qui tranche.
    ("runner/components.py", "_has_active_movement_blocker", "active_effects"):
        ("INERTE-AVAL", "sujet = `unit_id` de `unit_extensions_can_move` (`UnitExtensions$$CanMove`, "
                        "4e etage = `MovementComponent$$IsAllowedToMove`). ⚠ La lecture EST atteinte "
                        "pour un cadavre-au-chargement : `unit_extensions_can_move` lit "
                        "`sc = get_component(StatsComponent)` mais NE RETOURNE PAS quand `sc is "
                        "None` -- il poursuit avec `traits = None`. Les TROIS appelants la rendent "
                        "neanmoins inerte, et ils ne le font pas de la meme facon : "
                        "(1) `operations/turnflow.py::VerifyUnitsTurnFinishedOperation."
                        "verify_unit_turn_ended` porte `if uc is not None and not uc.alive: return "
                        "{reason: dead}` AVANT `_can_act` -> `has_tiles_to_move_to` (gate AMONT, "
                        "mirror du `TryGetComponent<HealthComponent> && IsDead()` natif) ; "
                        "(2) `operations/movement.py::_is_allowed_to_move` appelle `CanMove` AVANT "
                        "son propre `if uc is not None and not uc.alive: return False` -- la "
                        "lecture est donc bien atteinte, mais le verdict est `False` dans les DEUX "
                        "branches (bloqueur trouve -> `return False` ; aucun bloqueur -> le gate "
                        "`alive` qui suit rend `False`), donc AUCUN observable ne depend du "
                        "resultat : c'est le sens exact d'INERTE-AVAL ; "
                        "(3) `runner/abilities/loki/attempted_possession.py` porte `possessed_id`, "
                        "la CIBLE d'une active -- le ciblage ne rend pas un mort cible legale "
                        "(`IsDeadUnitAndNotAllowedByAbility`, porte par #429-r1)"),
    ("runner/operations/triggers/loki/close_combat_weakness.py", "_owner_active_effect_names",
     "active_effects"):
        ("INERTE-AVAL", "sujet = `self.owner_id` d'un EFFECT-trigger "
                        "(`CloseCombatWeaknessMarkStartedTurnAdjacent`), et RIEN ne l'ecarte : "
                        "`collect_effect_triggers` balaie `state.effects.by_unit` SANS aucun gate "
                        "de vivacite (seul `consumed` exclut, et c'est FIDELE -- le rail natif "
                        "`EvaluateTriggerOperation$$EvaluateEffectTriggerEffectAbilities` ne lit "
                        "jamais `EffectComponent+0x5c`), puis `matches` n'exige que POSITION et "
                        "EQUIPE (`close_combat_weakness_adjacent_enemies_count` : `oc.team is None "
                        "or pc is None -> None`), que le cadavre-au-chargement possede. "
                        "⚠ MAIS CE N'EST PAS UNE DIVERGENCE PORT/NATIF, et c'est la difference avec "
                        "`defender_fixed_armor` : sur la face EFFET `_owner_gate_applies` est FAUX "
                        "-- le natif n'a AUCUN gate d'owner ici, donc lui aussi evalue ce trigger "
                        "pour un cadavre. PORT ET NATIF CONCORDENT : il n'y a pas de dette de "
                        "fidelite a ouvrir, et c'est ce qui interdit d'ecrire ATTEIGNABLE ici (ce "
                        "verdict-la DECLARE une dette, cf. `VERDICTS_A_TRAITER` et son cliquet). "
                        "Le seul ecart residuel est la degradation permissive du substrat "
                        "(`traits` absent -> les conditions de trait sur-evaluent), et sa "
                        "direction est RESTRICTIVE ici : `owner_effect_names` s'elargit, donc "
                        "`NOT HasEffect(Owner, 0x478 SuppressCloseCombatWeakness)` a plus de "
                        "chances de FERMER. L'unique observable serait donc un marqueur `1129` NON "
                        "pose sur un MORT -- or son seul lecteur est la condition de `1130`, le "
                        "malus de degat du porteur, qu'un mort ne subit ni n'inflige. Aucun gate a "
                        "poser : en inventer un DIVERGERAIT du natif"),
    ("services/movement_query.py", "get_range_bonus_for_unit", "active_effects"):
        ("INERTE-VIVANT", "sujet = `unit_id` du seul appelant, `get_movable_tiles_for` "
                          "(`MovementQuery$$GetMovableTilesFor`), dont les quatre call-sites "
                          "portent tous un CASTER ou un MOVER : `runner/abilities/genestealer.py` "
                          "(x3, `caster_id`), `runner/abilities/targeting.py` (l'unite dont on "
                          "planifie le deplacement), `runner/operations/triggers/loki/betrayer.py` "
                          "(`owner_id` du cast), et la voie `engine.ai.state_bridge._move_tiles` "
                          "empruntee par `turnflow.has_tiles_to_move_to`, qui porte deja le gate "
                          "`uc.alive` de `verify_unit_turn_ended` en amont. Un mort ne caste ni ne "
                          "bouge. ⚠ Le PRE-FILTRE de ce foyer ne protege PAS : il teste la "
                          "SURCHARGE de `create_range_bonus_for_movement` sur la liste BRUTE "
                          "`by_unit`, que le cadavre-au-chargement possede -- c'est le sujet, pas "
                          "le pre-filtre, qui rend le site inerte"),

    # ---- face DECISION : le pendant du substrat ------------------------------------------------
    ("playbook/scene.py", "effects", "unit_state"):
        ("INERTE-AVAL", "`Scene.effects(uid)` -- le PORTAIL de la face DECISION. La premisse du "
                        "residu est CONFIRMEE (la `Scene` porte bien des morts : `build_scene_ctx` "
                        "construit `pos_by_id`/`team_by_id`/`hp_by_id` et le `EffectsState` depuis "
                        "TOUT `dv.units`, alors que `ctx_by_id` vient du `predictor`, donc des "
                        "VIVANTS seuls) -- mais le portail ne CHOISIT aucun sujet : il relaie celui "
                        "de son appelant. Les 16 cles d'appelants sont ventilees, 0 ATTEIGNABLE"),
    ("playbook/savior_protocols.py", "_target_has_active_markerlight", "unit_state"):
        ("INERTE-VIVANT", "`target_uid` est un VOISIN du mover, resolu par le selecteur "
                          "`AdjacentFriends` de `SaviorProtocols` -- meme argument `#57m` que "
                          "`build_hits_board` : le board est une occupation de tuile"),
    # Les DEUX fonctions ci-dessus appellent `unit_state` PUIS `active_effects` : elles portent donc
    # une cle par METHODE, et c'est voulu -- ce sont deux lectures distinctes du meme substrat.
    ("playbook/savior_protocols.py", "_target_has_active_markerlight", "active_effects"):
        ("INERTE-VIVANT", "meme sujet que la ligne `unit_state` ci-dessus, meme motif"),
    ("playbook/scene.py", "effects", "active_effects"):
        ("INERTE-AVAL", "le PORTAIL lui-meme. Il ne choisit aucun sujet : il relaie celui de son "
                        "appelant, et les 15 cles d'appelants sont ventilees ci-dessous "
                        "(#462-...-r1-r1-r1). Son verdict est donc l'union des leurs, et elle est "
                        "INERTE : 0 ATTEIGNABLE"),

    # ---- face DECISION : les APPELANTS du portail `Scene.effects` (#462-...-r1-r1-r1) -----------
    # ENUMERES par AST (methode `effects`), pas comptes : la tranche precedente ecrivait
    # << ~30 appelants >> ; il y a **29 appels** pour **15 cles** `(fichier, fonction)`.
    #
    # LA LOI DE VENTILATION EST LA MEME QUE COTE COMBAT, et son resultat est INVERSE : cote COMBAT,
    # un balayage sur six (`defender_fixed_armor`) n'avait AUCUN gate de vivacite ; ici, les
    # QUATRE balayages en portent un. La face DECISION etait deja saine -- ce qui ne se savait pas,
    # puisque personne ne l'avait regardee.
    #
    # ⚠ MEME RESERVE QUE COTE COMBAT : le gate porte sur les PV (`(scene.hp(uid) or 0) > 0`), pas
    # sur `uc.alive`. Il tient parce que `Scene.hp_by_id` lit `dv.units[].hp`, qui vaut 0 pour un
    # mort. Une capture sans `hp` le rendrait inerte.
    ("playbook/prediction/_shared.py", "_apply_ally_attack_dmg_bonus", "effects"):
        ("INERTE-AMONT", "balayage de `scene.pos_by_id`, gate `(scene.hp(uid) or 0) > 0` DANS la "
                         "comprehension. Pendant exact de `damage_model._apply_ally_attack_damage_"
                         "auras`, gate compris"),
    ("playbook/prediction/_shared.py", "_add_positional_and_defender_mods", "effects"):
        ("INERTE-AMONT", "QUATRE appels : trois sur `att_id`/`tgt_id` (les deux combattants), le "
                         "quatrieme est le balayage `_def_carriers` des auras-defense state-wide, "
                         "gate `(scene.hp(uid) or 0) > 0`"),
    ("playbook/prediction/_shared.py", "defender_prediction_block_amount", "effects"):
        ("INERTE-VIVANT", "`tgt_id` = la CIBLE du coup"),
    ("playbook/prediction/normal_attack.py", "_display_attack_base", "effects"):
        ("INERTE-AMONT", "balayage `carriers` de `scene.pos_by_id`, gate "
                         "`(scene.hp(uid) or 0) > 0`"),
    ("playbook/prediction/normal_attack.py", "make_normal_attack_predictions", "effects"):
        ("INERTE-AMONT", "QUATRE appels : `att_id`, `tgt_id` (x2), et le balayage `aura_sources` "
                         "qui itere `_alive_ids` -- le gate est DANS la construction de la liste"),
    ("playbook/prediction/normal_attack.py", "_make_mv71_drone_predictions", "effects"):
        ("INERTE-VIVANT", "`att_id` puis `tgt_id` -- les deux combattants du coup"),
    ("playbook/prediction/normal_attack.py", "get_additional_damage_prediction", "effects"):
        ("INERTE-VIVANT", "`att_id` = l'ATTAQUANT"),
    ("playbook/prediction/normal_attack.py", "get_klaw_attack1_prediction", "effects"):
        ("INERTE-VIVANT", "`att_id` = l'ATTAQUANT"),
    ("playbook/prediction/abilities.py", "generate_multi_hit_attack_prediction", "effects"):
        ("INERTE-VIVANT", "`uid` = l'ATTAQUANT (passe a "
                          "`calculate_attacker_modifiers_for_prediction`)"),
    ("playbook/fury_of_the_ancients.py", "_get_damage_prediction", "effects"):
        ("INERTE-VIVANT", "`uid` = l'ATTAQUANT (meme consommateur)"),
    ("playbook/avalanche_of_muscle.py", "_predict_extra_vs_target", "effects"):
        ("INERTE-VIVANT", "`att_id` = l'ATTAQUANT"),
    ("playbook/heavy_bolt_pistol.py", "_predict_vs_target", "effects"):
        ("INERTE-VIVANT", "`att_id` = l'ATTAQUANT"),
    ("playbook/light_im_up.py", "_predict_extra_vs_target", "effects"):
        ("INERTE-VIVANT", "`att_id` = l'ATTAQUANT"),
    ("playbook/psyker.py", "_predict_amount_vs_target", "effects"):
        ("INERTE-VIVANT", "`att_id` = l'ATTAQUANT"),
    ("playbook/shrapnel.py", "_predict_vs", "effects"):
        ("INERTE-VIVANT", "`att_id` = l'ATTAQUANT"),
    # LE 16e, ET IL EST HORS `playbook/` -- trouve par le CLIQUET D'EXHAUSTIVITE, pas par le
    # recensement : le residu disait << ~30 appelants sous `playbook/` >>, et une enumeration bornee
    # a ce repertoire l'aurait rate. C'est la meme faute que le recenseur de #270-r1 a corrigee :
    # une portee choisie ne peut pas montrer le site qu'elle exclut.
    ("utilities/wireweave_net.py", "target_has_active_wireweave_net", "effects"):
        ("INERTE-VIVANT", "`target_uid` = la CIBLE du mouvement que `WireweaveNet` penalise. "
                          "Mirror de `EntityExtensions.GetOwnedEffects(target, state, 1111)"
                          ".Any(e => e.IsActive)` : le vecteur natif evalue une cible de "
                          "deplacement, vivante par construction"),
    ("playbook/scene.py", "prevents_overkill", "effects"):
        ("INERTE-VIVANT", "`uid` = l'unite dont on decide l'OVERKILL, donc celle qu'on est en "
                          "train de tuer : elle est vivante a l'instant du test. Meme motif que "
                          "`runner/components.py::unit_prevents_overkill` cote COMBAT"),
}

VERDICTS_A_TRAITER = ("ATTEIGNABLE",)


# ================================================================================================
# CONSOMMATEUR -- qui LIT la cle `traits` du `unit_state` ? (le rayon de souffle, mesure)
# ================================================================================================
def consommateurs_cle_traits() -> list:
    """Toute lecture `<x>.get("traits")` sous `engine/entities/effects/` dont le `<x>` est le
    parametre `unit_state` d'une methode `is_active`.

    C'est le RAYON DE SOUFFLE de la degradation permissive : une cle `traits` absente ne peut
    changer un verdict que la ou une `is_active` la lit. Le mesurer evite de traiter les 16 autres
    sites comme s'ils portaient tous le meme risque."""
    out = []
    for rel, p in _fichiers():
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            if not (isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and n.name == "is_active"):
                continue
            noms = {a.arg for a in n.args.args}
            for c in ast.walk(n):
                if (isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
                        and c.func.attr == "get" and len(c.args) >= 1
                        and isinstance(c.args[0], ast.Constant) and c.args[0].value == "traits"):
                    # le receveur remonte-t-il au parametre `unit_state` ?
                    cur = c.func.value
                    while isinstance(cur, (ast.BoolOp, ast.Call)):
                        cur = (cur.values[0] if isinstance(cur, ast.BoolOp) else cur.func)
                    src = ast.unparse(c.func.value)
                    if any(nm in src for nm in noms):
                        out.append((rel, n.name, c.lineno, src))
    return out


# ================================================================================================
# REGISTRE (-r2) -- ce que le natif fait d'un cadavre, et ou la question se tranche
# ================================================================================================
def porteurs_fire_on_death() -> list:
    """Toute classe de `engine/runner/operations/triggers/**` qui pose `fire_on_death = True`,
    avec l'evenement qu'elle ecoute.

    POURQUOI CETTE LISTE EST LE BON RECENSEMENT. Le residu `-r2` demandait si
    `IdunBattleLogic.Core.Services.Caches.AbilityAndEffectCache` retire l'entite a la mort. La
    reponse se lit un cran PLUS BAS, et elle est STRUCTURELLE :
    `IdunBattle.Operations.EvaluateTriggerOperation$$CanGetAbilityTrigger` teste
    `IdunBattle.Entities.UnitExtensions$$IsAlive(owner)` A LA LECTURE, sous une exemption
    `get_AllowForDeadOwner()` (#10015 -- ce n'est PAS un `IsAtomic`) :

        if (!ability.get_AllowForDeadOwner()) { if (IsUnit(owner) && !IsAlive(owner)) return 0; }
        if (IsUnit(owner) && IsTriggersDisabled(owner))                 return 0;

    Si le cache retirait les morts, CE gate et SON exemption seraient tous deux INATTEIGNABLES --
    la branche atomique n'existe QUE pour laisser passer un owner MORT. Le cache CONSERVE donc les
    entites mortes, et c'est `CanGetAbilityTrigger` qui trie.

    ⇒ le `if sc is None: continue` du port et le gate natif rendent le MEME verdict pour toute
    ability NON atomique. Ils ne divergent que sur les ATOMIQUES -- que le port nomme
    `fire_on_death`. D'ou ce recensement : un porteur ne peut diverger que si son EVENEMENT peut
    encore se produire APRES sa propre mort."""
    base = ENGINE / "runner" / "operations" / "triggers"
    out = []
    for p in sorted(base.rglob("*.py")):
        rel = os.path.relpath(p, ENGINE).replace("\\", "/")
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            if not isinstance(n, ast.ClassDef):
                continue
            champs = {}
            for st in n.body:
                if (isinstance(st, ast.Assign) and len(st.targets) == 1
                        and isinstance(st.targets[0], ast.Name)):
                    champs[st.targets[0].id] = ast.unparse(st.value)
            if champs.get("fire_on_death") == "True":
                out.append((rel, n.name, champs.get("event_id"), champs.get("event_ids"),
                            _face_de(rel, n.name), _events_de(rel, n.name)))
    return out


def _events_de(rel: str, nom: str) -> "frozenset | None":
    """Les evenements ECOUTES, en VALEURS -- resolus sur la classe, jamais lus au TEXTE du site.

    ⚠ POURQUOI (#547-r11). Le tri se faisait par SOUS-CHAINE sur l'expression ECRITE
    (`ast.unparse(event_id)`), confrontee a des libelles `"EventTriggerType.UnitDeath"`. Un site qui
    ecrit une CONSTANTE DE MODULE -- `event_id = _ON_UNIT_DEATH`, forme majoritaire -- ne contient
    aucune de ces sous-chaines : `RelicOfLostCadiaSummonUnitAbility` ecoute `UnitDeath(0)`, donc SA
    PROPRE MORT, et sortait pourtant en << NON TRIE >>. Le recenseur ne mesurait pas ce qu'il
    croyait mesurer : il comparait des TEXTES la ou la question porte sur des VALEURS.

    Le probe IMPORTE deja le module pour resoudre la FACE (`_face_de`), donc lire l'attribut ne
    coute rien de plus et supprime toute grammaire. `None` = NON RESOLU (classe absente, attribut
    manquant, valeur non entiere) -- jamais un ensemble VIDE, qui se lirait comme << n'ecoute
    rien >> et ferait taire le cliquet."""
    import importlib
    mod = importlib.import_module("engine." + rel[:-3].replace("/", "."))
    cls = getattr(mod, nom, None)
    if cls is None:
        return None
    brut = []
    un = getattr(cls, "event_id", None)
    if un is not None:
        brut.append(un)
    plusieurs = getattr(cls, "event_ids", None)
    if plusieurs:
        brut.extend(plusieurs)
    if not brut:
        return None
    try:
        return frozenset(int(x) for x in brut)
    except (TypeError, ValueError):
        return None


def _face_de(rel: str, nom: str) -> str:
    """La FACE de la classe -- `EffectTrigger` ou `TriggeredAbility` -- resolue par la vraie MRO.

    ⚠ PAS par le nom de sa base a l'AST : `RitesOfMorkaiReviveTrigger(ReviveEffectTrigger)` derive
    d'`EffectTrigger` par un INTERMEDIAIRE, et un test de nom de base le rendait << NON TRIE >>.
    C'est la meme faute de forme que << l'absence dans une table ne prouve rien >> : un critere
    superficiel rend un faux verdict, pas une mesure. Le probe est offline, l'import ne coute rien."""
    import importlib
    mod = importlib.import_module("engine." + rel[:-3].replace("/", "."))
    cls = getattr(mod, nom, None)
    if cls is None:                                   # classe PRIVEE renommee/absente du module
        return "INCONNUE"
    from engine.runner.operations.triggers.base import EffectTrigger
    return "EFFET" if issubclass(cls, EffectTrigger) else "ABILITY"


# Un porteur `fire_on_death` DIVERGE (port vs natif) sur un cadavre-au-chargement seulement si son
# evenement peut se produire APRES sa mort. Tous ceux dont l'evenement EST leur propre mort sont
# structurellement inertes : l'evenement a deja eu lieu avant la capture, il ne se reproduira pas.
#
# ⚠ EN MEMBRES D'ENUM, PAS EN SOUS-CHAINES (#547-r11). Ces cinq-la etaient des LIBELLES confrontes
# au TEXTE ecrit au site : un `event_id = _ON_UNIT_DEATH` (constante de module) n'en contient aucun,
# donc `RelicOfLostCadiaSummonUnitAbility` -- qui ecoute `UnitDeath(0)`, sa propre mort -- sortait
# << NON TRIE >>. Le membre se compare a la VALEUR resolue par `_events_de`, ce que la doctrine
# << un ENTIER qui DESIGNE quelque chose passe par un ENUM >> demandait deja.
EVENTS_DE_SA_PROPRE_MORT = frozenset(int(x) for x in (
    EventTriggerType.UnitDeath,          # 0
    EventTriggerType.PreUnitDeath,       # 1
    EventTriggerType.PreUnitDeath_2,     # 2
    EventTriggerType.PendingDeathAdded,  # 3
    EventTriggerType.UnitDefeated,       # 54
))


def ecoute_sa_propre_mort(events: "frozenset | None") -> bool:
    """VRAI si TOUS les evenements ecoutes sont des evenements de la mort du porteur.

    `None` (non resolu) -> FAUX : un porteur qu'on n'a pas su lire doit rougir, jamais etre range
    en INERTE par defaut. `all()` et non `any()` : un porteur qui ecoute la mort ET autre chose
    (ex. `event_ids = [UnitDeath, NormalAttack]`) peut encore tirer APRES sa mort par le second
    vecteur -- le classer inerte sur le premier serait exactement le faux negatif qu'on repare."""
    return bool(events) and events.issubset(EVENTS_DE_SA_PROPRE_MORT)

# Les porteurs qui ecoutent AUTRE CHOSE, nommes un par un avec leur consequence mesuree.
REGISTRE_HORS_MORT = {
    "EnvAmbushResurrectAbility":
        ("DIVERGENT-DOUBLE-GATE",
         "`On(TurnStart_Actions = 22)` : l'evenement se reproduit a CHAQUE tour, donc le natif "
         "evalue bien ce trigger pour un cadavre-au-chargement porteur du trait Ambush, la ou le "
         "port ne l'inscrit meme pas. AUCUNE consequence observable, et c'est un DOUBLE gate qui "
         "l'assure : (1) le behaviour est GLOBAL (il enumere TOUS les eligibles), donc toute autre "
         "instance inscrite produit le meme effet ; (2) `_eligible_for_resurrect` exige "
         "`turn_defeated is not None`, que rien ne seede au chargement. Ce qui reste OUVERT est le "
         "cas ou le SEUL porteur Ambush du plateau est un cadavre-au-chargement -- residu "
         "`#462-r4b-r1-r1-r1-r1-b-r1-r1-r3-r1-r2-r1`"),
    # ============================================================================================
    # #547-r11 -- LES CINQ PORTEURS ENTRES AVEC #10015, tous le MEME JOUR que ce cliquet a rougi.
    #
    # C'est le patron annonce, verifie : ce gisement est alimente par NOTRE PROPRE CADENCE. #10015
    # a mecanise l'appariement port <-> natif (9 -> 130 classes confrontees) et pose `fire_on_death`
    # sur cinq classes, chaque valeur LUE dans `metadata/allow_for_dead_owner.tsv` (`b0 01 c3` =
    # `mov al,1 ; ret`). Poser la valeur juste REOUVRE mecaniquement cette table : le port
    # n'inscrit toujours pas un cadavre-au-chargement au registre (`collect_triggered_abilities`,
    # `if sc is None: continue`), alors que le natif l'y garde et le trie a la LECTURE.
    #
    # LE DISCRIMINANT EST LE MEME POUR LES QUATRE PREMIERS, et il est STRUCTUREL : leur `matches`
    # exige que le PORTEUR soit l'ACTEUR (`get_OwnerIsActor` / `get_OwnerIsCaster`). Un
    # cadavre-au-chargement n'agit JAMAIS -- il n'entre pas dans `toActivate`
    # (`VerifyUnitsTurnFinishedOperation.verify_unit_turn_ended` rend `reason: dead` avant tout
    # `_can_act`), et il n'a joue aucun `KillUnitOperation` dans CE run, donc aucune attaque
    # post-mortem `FinalJustice` n'a pu ecrire `AbilityEntities+0x60` pour lui. C'est EXACTEMENT le
    # raisonnement deja ecrit pour `SynapticLinchpinAbility` ci-dessous.
    # ============================================================================================
    "ControlEdictAbility":
        ("SANS CONSEQUENCE -- L'OWNER MORT NE PEUT PAS ETRE L'ACTEUR",
         "`On(NormalAttack = 38)`, evenement qui se reproduit a chaque coup : le natif evalue donc "
         "bien ce trigger pour un cadavre-au-chargement, la ou le port ne l'inscrit meme pas. "
         "AUCUNE consequence -- le corps ENTIER de `matches` est `return ev.actor_id == "
         "self.owner_id` (le mirror de `get_OwnerIsCaster` : Tan est l'attaquant). Un "
         "cadavre-au-chargement ne porte aucune attaque normale, donc le predicat est FAUX pour "
         "lui dans tous les etats atteignables. Le regime divergent est vide."),
    "LightImUpAbility":
        ("SANS CONSEQUENCE -- L'OWNER MORT NE PEUT PAS ETRE L'ACTEUR",
         "`On(NormalAttack = 38, ownerNeedsToBeAlive: 0)`. ⚠ Les DEUX gates sont DISTINCTS et "
         "#10015 les separe : le litteral `ownerNeedsToBeAlive: 0` vit dans le PREDICAT du noeud "
         "DSL `On`, `get_AllowForDeadOwner` vit EN AMONT dans `IdunBattle.Operations."
         "EvaluateTriggerOperation$$CanGetAbilityTrigger` -- le port n'avait que le premier. "
         "Une fois le second pose, le cadavre-au-chargement reste ecarte par le SEUL conjoint du "
         "`CreateTrigger` : `get_OwnerIsActor` = `AreEqual(Owner@0x148, Actor@0x158)`, que "
         "`matches` mirroite par `if self.owner_id != ev.actor_id: return False`. Regime vide."),
    "LordOfTempestsAddIceAbility":
        ("SANS CONSEQUENCE -- L'OWNER MORT NE PEUT PAS ETRE L'ACTEUR",
         "DEUX evenements (`On(NormalAttack = 38)` et `On(Attack = 9)` gate par le kind d'attaque "
         "normale 0x3f5, le smite Psyker), donc le tri par `all()` d'`ecoute_sa_propre_mort` ne "
         "peut pas le ranger inerte sur un seul. Il l'est par le PREMIER conjoint, commun aux deux "
         "branches : `matches` ouvre sur `if ev.actor_id != self.owner_id: return False` "
         "(`get_OwnerIsCaster`). Un cadavre-au-chargement n'attaque pas. Regime vide."),
    "CursedPlagueBellAttackAbility":
        ("SANS CONSEQUENCE -- LA DISJONCTION EXIGE UNE CIBLE, ET UN MORT N'EN EST PAS UNE",
         "`On(Attack = 9)`, et c'est le SEUL des cinq dont le porteur n'a PAS besoin d'etre "
         "l'acteur : le 2e conjoint natif est `OwnerIsTarget | OwnerIsAlive`, donc un porteur MORT "
         "y passe par le membre GAUCHE. Le regime divergent exige donc qu'un cadavre-au-chargement "
         "soit la CIBLE d'une attaque -- et il ne peut pas l'etre : "
         "`IdunBattle.Operations.ActiveAbilityOperation$$IsDeadUnitAndNotAllowedByAbility` est "
         "PORTE (#429-r1) au rang natif, son gate est le virtuel slot 0x11 "
         "`CanContinueOnDeadTarget` dont l'inventaire des overrides est VIDE, et le bit 38 "
         "`AllowDeadTarget` n'a qu'UN porteur dans tout le binaire "
         "(`GreatFrostAxeAbility$$GetTargetingOptionsForContinue`), qui vise une TUILE. S'y "
         "ajoutent deux gates que ce porteur unique ne satisfait pas : "
         "`CurrentAttackDamageProfilesContain(0xd = Psychic)` et `HasTrait(Actor, 0x3ea = Psyker)`. "
         "Ce qui DIVERGE reellement, et c'est le regime que #10015 a ouvert, est le mort DU RUN "
         "(tue par le coup en cours) -- lui a son `StatsComponent`, donc il EST au registre."),
    # ---- LE SEUL DES CINQ DONT LE REGIME DIVERGENT N'EST PAS VIDE -------------------------------
    "LifewardsAbility":
        ("DIVERGENT-REEL -- residu #547-r12",
         "`On(PreDamageTaken = 57)`, et le porteur n'est NI l'acteur NI la cible : le "
         "`CreateTrigger` contraint `AreEqual(Target@<DSLSelectors+0x60>, Parent(Owner@+0x30))`, "
         "c.-a-d. que la victime est CELESTINE et le porteur la GEMINAE. Aucun des deux "
         "discriminants des quatre autres ne s'applique. Et le 2e conjoint est precisement la "
         "disjonction `IsAlive(Owner@+0x30) | HasEffect(Owner@+0x30, 0x4d8 = 1240, onlyActive: 0, "
         "6)` : une Geminae MORTE qui porte encore le marqueur 1240 protege ENCORE Celestine. Ce "
         "regime est ATTEIGNABLE sur un cadavre-au-chargement, et c'est MESURE : "
         "`decisionView.units[]` conserve les morts AVEC leurs effets (cf. `etat_cadavre`), "
         "tandis que `combatSnapshot` ne les enumere pas -- donc l'entite porte 1240 sans porter "
         "de `StatsComponent`, et `collect_triggered_abilities` la saute. Le natif absorbe le "
         "coup, le port le laisse passer : Celestine encaisse des degats que le natif lui epargne. "
         "CE N'EST PAS FERME PAR CETTE TRANCHE (le remede est un cran plus bas -- inscrire au "
         "registre le cadavre-au-chargement pour les seules `fire_on_death`), d'ou un residu "
         "NOMME plutot qu'un verdict d'innocuite."),
    "SynapticLinchpinAbility":
        ("SANS CONSEQUENCE -- L'OWNER MORT NE PEUT PAS ETRE L'ACTEUR",
         "Entre ici avec #937-r1, qui pose `fire_on_death = True` sur la foi d'une valeur LUE : "
         "`SynapticLinchpinAbility$$get_AllowForDeadOwner` (`ITriggeredAbility` slot 8) rend VRAI, "
         "corps `b0 01 c3` PARTAGE avec `FinalJusticeAbility`. L'evenement ecoute est "
         "`On(NormalAttack = 38)`, qui se reproduit a chaque coup : le natif evalue donc bien ce "
         "trigger pour un cadavre-au-chargement, la ou le port ne l'inscrit meme pas. AUCUNE "
         "consequence, et le gate qui l'assure est DANS le trigger natif lui-meme : le disjunct "
         "effectif est `OwnerIsAlive | (OwnerIsActor & TriggeringAbilityIs(FinalJustice))` -- un "
         "porteur MORT n'y passe que s'il est LUI-MEME l'acteur du coup, ce qui exige l'attaque "
         "post-mortem du trait `FinalJustice`. Un cadavre-au-chargement n'agit jamais : il n'a "
         "joue aucun `KillUnitOperation` dans CE run, donc aucune `FinalJusticeAbility` n'a pu "
         "ecrire `AbilityEntities+0x60 = 1024` pour lui. Le regime divergent est vide."),
}


def _est_effect_trigger(face: str) -> bool:
    return face == "EFFET"


# ================================================================================================
# GATES DE VIVACITE -- les SIX balayages d'entites, et la preuve qu'ils portent tous leur gate
# ================================================================================================
# Un balayage de `state.entities` qui appelle `active_effects` sur CHAQUE entite visitee doit
# ecarter les morts : le board natif est une OCCUPATION DE TUILE (`#57m`). Le criteres est LU au
# source (AST) : une lecture de l'attribut `alive`, ou une comparaison sur `hp`.
BALAYAGES = {
    ("runner/damage_model.py", "defender_fixed_armor"):
        "aura FixedArmor de `ProtectorImperative` (gate pose par cette tranche)",
    ("runner/damage_model.py", "_apply_ally_attack_damage_auras"):
        "auras +degat alliees (Conqueror / BeaconOfRage)",
    ("runner/damage_model.py", "defender_modifiers"):
        "porteurs de malus de defense",
    ("runner/damage_model.py", "build_hits_board"):
        "board des COUPS (`#57m`)",
    ("runner/operations/damage.py", "_crit_carriers"):
        "univers des deux canaux CRIT (`#57m`)",
    ("runner/operations/additional_hits.py", "collect_additional_hit_groups"):
        "groupes de coups additionnels",
}


def _fonction_ast(fichier: str, fonction: str):
    tree = ast.parse((ENGINE / fichier).read_text(encoding="utf-8"))
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == fonction:
            return n
    return None


def etat_gates() -> list:
    """Pour chaque balayage : `(cle, lit_alive, compare_hp, motif)`.

    Un balayage passe s'il porte l'UN des deux (les deux formes existent dans l'arbre et sont
    toutes deux fideles : `uc.alive` est le mirror direct, `hp <= 0` la derivation par les PV)."""
    out = []
    for cle_, motif in sorted(BALAYAGES.items()):
        fn = _fonction_ast(*cle_)
        lit_alive = compare_hp = False
        if fn is not None:
            lit_alive = any(isinstance(n, ast.Attribute) and n.attr == "alive"
                            for n in ast.walk(fn))
            compare_hp = any(isinstance(n, ast.Compare)
                             and isinstance(n.left, ast.Attribute) and n.left.attr == "hp"
                             for n in ast.walk(fn))
        out.append((cle_, lit_alive, compare_hp, motif))
    return out


# ================================================================================================
# STEPS
# ================================================================================================
def step_inventaire() -> int:
    lst = sites()
    print("INVENTAIRE -- appelants du substrat `unit_state` sous `engine/` (AST, jamais grep)")
    print("")
    par_face = {}
    for s in lst:
        par_face.setdefault(s[3], []).append(s)
    for face in sorted(par_face):
        rows = sorted(par_face[face], key=lambda r: (r[0], r[4]))
        print("  face %s : %d appel(s)" % (face, len(rows)))
        for r in rows:
            print("      %-52s %5d  %-34s uid=%s" % (r[0], r[4], r[1], r[5]))
        print("")
    print("appels TOTAL : %d  --  cles DISTINCTES : %d" % (len(lst), len({cle(s) for s in lst})))
    return 0


def step_ventilation() -> int:
    lst = sites()
    trouves = {cle(s) for s in lst}
    print("VENTILATION -- le sujet de chaque appelant peut-il etre un CADAVRE-AU-CHARGEMENT ?")
    print("")
    par_verdict = {}
    for c in sorted(trouves):
        v, motif = VENTILATION.get(c, ("NON-VENTILE", "site NEUF : a ventiler"))
        par_verdict.setdefault(v, []).append((c, motif))
    for v in sorted(par_verdict):
        print("  %-14s %d" % (v, len(par_verdict[v])))
        for c, motif in par_verdict[v]:
            print("      %s::%s  (%s)" % (c[0], c[1], c[2]))
            for i in range(0, len(motif), 96):
                print("          %s" % motif[i:i + 96])
        print("")
    manquantes = sorted(trouves - set(VENTILATION))
    orphelines = sorted(set(VENTILATION) - trouves)
    print("cles TOTAL : %d  --  non ventilees : %d  --  orphelines : %d"
          % (len(trouves), len(manquantes), len(orphelines)))
    if manquantes:
        print("  NON VENTILEES : %r" % (manquantes,))
    if orphelines:
        print("  ORPHELINES    : %r" % (orphelines,))
    return 1 if (manquantes or orphelines) else 0


def step_consommateur() -> int:
    cons = consommateurs_cle_traits()
    print("RAYON DE SOUFFLE -- qui LIT la cle `traits` du `unit_state` dans une `is_active` ?")
    print("")
    for rel, fn, ln, src in cons:
        print("  %-52s %5d  %s.get(\"traits\")" % (rel, ln, src))
    print("")
    print("consommateurs : %d" % len(cons))
    print("")
    print("LECTURE. La degradation << cle absente ⇒ condition de TRAIT VRAIE >> ne peut changer un")
    print("verdict QUE la. Un appelant ATTEIGNABLE dont le consommateur aval ne lit pas cet effet-la")
    print("ne porte donc AUCUN ecart par ce canal -- ce qui ne veut pas dire qu'il n'en porte pas")
    print("d'autre (cf. `--step gisement`).")
    return 0 if cons else 1        # un recensement VIDE serait un faux vert : on l'assertionne


def step_gisement() -> int:
    """Ce que le SEUL site ATTEIGNABLE produit -- et pourquoi ce n'est PAS le defaut `traits`."""
    print("LE SEUL SITE ATTEIGNABLE -- `damage_model.py::defender_fixed_armor`")
    print("")
    print("Son balayage retient un porteur d'aura sur trois criteres : `OwnerComponent`,")
    print("`PositionComponent`, meme equipe que le defenseur. AUCUN gate de vivacite, la ou ses")
    print("CINQ freres en portent un (`build_hits_board` et `_crit_carriers` par `#57m`,")
    print("`collect_additional_hit_groups` par `uc.alive`, `_apply_ally_attack_damage_auras` et le")
    print("second appel de `defender_modifiers` par `hp <= 0`).")
    print("")
    print("DEUX ECARTS DISTINCTS s'y superposent, et les confondre ferait corriger le mauvais :")
    print("")
    print("  A. LA CLE `traits` (le defaut nomme par le residu) -- SANS CONSEQUENCE ICI.")
    print("     Le seul consommateur de cette cle est `PinnedEffect.is_active`")
    print("     (`PinnedEffect$$CreateActiveCondition` = `Not(HasTrait(Self, 0x40f =")
    print("     TerminatorArmour))`), un effet de REDUCTION DE DEGAT. `defender_fixed_armor` ne lit")
    print("     que l'aura `FixedArmor` de `ProtectorImperative` : le `Pinned` d'un cadavre y est")
    print("     invisible, actif ou non.")
    print("")
    print("  B. LE GATE DE VIVACITE ABSENT -- c'est LUI, l'ecart, et il est PLUS LARGE.")
    print("     Un cadavre-au-chargement projette son aura `FixedArmor`. Le natif ne le peut pas :")
    print("     `IdunBattle.Operations.KillUnitOperation$$Execute` appelle TROIS fois")
    print("     `RemoveEffects(killed, <step>)`, donc une unite morte EN BATAILLE n'a plus d'effet")
    print("     a projeter -- et c'est aussi pourquoi l'ecart est INERTE EN FAIT aujourd'hui :")
    print("     `decisionView.units[].effects` est VIDE pour un mort, donc `active_effects` rend")
    print("     `[]` et le `if not effs: continue` qui suit l'ecarte. INERTE PAR UNE PROPRIETE DU")
    print("     CAPTEUR, PAS PAR UN GATE DU PORT : rien ne garde cette propriete, et un etat")
    print("     construit hors capture (montage, greffe, seed synthetique) la viole sans erreur.")
    print("")
    print("Le gate `uc.alive` pose par cette tranche ferme B et aligne le site sur ses cinq freres.")
    return 0


def step_registre() -> int:
    lst = porteurs_fire_on_death()
    print("REGISTRE (-r2) -- un cadavre-au-chargement porte-t-il ses triggered-abilities ?")
    print("")
    print("REPONSE NATIVE, et elle ne se lit PAS sur `AbilityAndEffectCache` :")
    for ligne in (porteurs_fire_on_death.__doc__ or "").split("\n")[2:]:
        s = ligne.strip()
        if s:
            print("  %s" % s)
    print("")
    print("PORTEURS `fire_on_death` (= mirror de `get_AllowForDeadOwner`), et leur evenement :")
    print("")
    rc = 0
    for rel, nom, evid, evids, face, evs in lst:
        ev = evid or evids or "<aucun au niveau classe>"
        # L'expression ECRITE reste affichee (elle est lisible), mais le TRI porte sur les VALEURS
        # resolues : les deux sont montrees cote a cote pour que l'ecart saute aux yeux (#547-r11).
        ev = "%s = %s" % (ev, sorted(evs) if evs else "NON RESOLU")
        if _est_effect_trigger(face):
            etat = "INERTE-FACE  (EffectTrigger : `_owner_gate_applies` est FAUX, aucun gate)"
        elif ecoute_sa_propre_mort(evs):
            etat = "INERTE-EVENT (l'evenement EST sa propre mort : deja eu lieu avant la capture)"
        elif nom in REGISTRE_HORS_MORT:
            etat = "%s" % REGISTRE_HORS_MORT[nom][0]
        else:
            etat = "NON TRIE  <-- ROUGE : evenement hors mort, non instruit"
            rc = 1
        print("  %-38s %-52s %s" % (nom, ev, etat))
        print("        %s" % rel)
    print("")
    for nom, (_e, motif) in sorted(REGISTRE_HORS_MORT.items()):
        print("  %s :" % nom)
        for i in range(0, len(motif), 96):
            print("      %s" % motif[i:i + 96])
    print("")
    print("porteurs : %d" % len(lst))
    return rc


def etat_cadavre(traits_mesures: bool):
    """Un cadavre-AU-CHARGEMENT porteur d'un `Pinned`, avec ou sans son substrat de traits.

    `traits_mesures=False` = l'etat REEL produit par `snapshot.load_state` : l'entite vient de
    `decisionView.units[]` (qui conserve les morts AVEC leurs effets) mais `combatSnapshot` ne
    l'enumere pas, donc AUCUN `StatsComponent` -- et `UnitEffectStateView` n'a alors AUCUNE cle
    `traits` a poser. `True` = le contrefactuel : le meme cadavre, ses traits connus."""
    from engine.runner.state import State, Entity
    from engine.runner.components import (UnitComponent, OwnerComponent, PositionComponent,
                                          HealthComponent, StatsComponent)
    from engine.entities.effects_state import EffectsState
    from engine.entities.traits.unit_trait import UnitTrait
    from engine.entities.unit_context import UnitContext
    st = State()
    e = Entity(7)
    e.add_component(UnitComponent(visual_id="ultraTerminator", alive=False))
    e.add_component(OwnerComponent(team=1, player=3))
    e.add_component(PositionComponent(col=4, row=4))
    e.add_component(HealthComponent(hp=0, hp_max=100))
    if traits_mesures:
        from engine.entities.stats import UnitStats
        ctx = UnitContext.__new__(UnitContext)
        ctx.visual_id = "ultraTerminator"
        ctx.traits = [UnitTrait.TerminatorArmour.name]
        ctx.traits_measured = True
        # `UnitEffectStateView.__init__` lit AUSSI `ctx.get_stat(TURNS_STARTED)` -- un ctx
        # `__new__` nu n'a pas de `stats`, et l'oubli se voit en `AttributeError`, pas en verdict.
        ctx.stats = UnitStats()
        e.add_component(StatsComponent(ctx))
    st.entities[7] = e
    st.effects = EffectsState.seed({7: [{"name": "Pinned", "type": None}]}, {}, {}, {})
    return st


def step_contrefactuel() -> int:
    """LA DEGRADATION PERMISSIVE, EXERCEE -- pas seulement affirmee.

    Meme methode que `probe_545_unit_flags_component_vide.py` (meme forme de defaut, un cran
    ailleurs : la, un `UnitFlagsComponent` ABSENT vs VIDE ; ici, une cle `traits` ABSENTE vs
    RENSEIGNEE). On APPELLE le substrat sur les deux etats et on compare la SORTIE."""
    from engine.runner.components import unit_state_for_effects
    print("CONTREFACTUEL -- la cle `traits` absente change-t-elle ce que rend `active_effects` ?")
    print("")
    rc = 1
    sorties = {}
    for mesures in (False, True):
        st = etat_cadavre(mesures)
        us = unit_state_for_effects(st, 7)
        actifs = sorted(getattr(x, "name", None) for x in st.effects.active_effects(7, us))
        portes = sorted(getattr(x, "name", None) for x in st.effects.by_unit.get(7, []))
        sorties[mesures] = actifs
        print("  substrat %-22s cle `traits` %-8s  PORTES %-12s ACTIFS %s"
              % ("MESURE (contrefactuel)" if mesures else "REEL (cadavre charge)",
                 "PRESENTE" if "traits" in us else "ABSENTE", portes, actifs))
    print("")
    if sorties[False] != sorties[True]:
        rc = 0
        print("LES DEUX SORTIES DIFFERENT -- la degradation est REELLE et EXERCEE ici :")
        print("  `PinnedEffect$$CreateActiveCondition` = `Not(HasTrait(Self, 0x40f =")
        print("  TerminatorArmour))`. Sans la cle, `has_trait(None, ...)` est FAUX, donc la")
        print("  condition rend VRAI et l'effet CONTRIBUE (x0.70) sur une unite que le natif")
        print("  immunise. C'est la forme PERMISSIVE : jamais un refus a tort, toujours un")
        print("  effet de trop.")
    else:
        print("SORTIES IDENTIQUES -- ce probe ne discrimine plus rien (regime DEGENERE).")
        print("  Un contrefactuel qui ne separe pas les deux etats est un VERT qui ment : il")
        print("  faut le reparer, pas s'en satisfaire. Verifier que `Pinned` est bien seede et")
        print("  que `TerminatorArmour` est bien le trait lu par la condition.")
    print("")
    print("PORTEE. Ce point de passage est UNIQUE : les 19 appelants enumeres par `--step")
    print("ventilation` consomment TOUS `EffectsState.active_effects`, donc aucun d'eux ne peut")
    print("distinguer les deux etats autrement que par ce que cette mesure montre. C'est ce qui")
    print("rend la ventilation site-par-site suffisante -- elle n'a qu'a repondre << le sujet")
    print("peut-il etre un cadavre ? >>, pas a re-mesurer la degradation.")
    return rc


_STEPS = {"inventaire": step_inventaire, "ventilation": step_ventilation,
          "consommateur": step_consommateur, "gisement": step_gisement,
          "registre": step_registre, "contrefactuel": step_contrefactuel,
          "gates": lambda: step_gates()}


def step_gates() -> int:
    print("GATES DE VIVACITE -- les six balayages d'entites qui appellent `active_effects`")
    print("")
    rc = 0
    for cle_, lit_alive, compare_hp, motif in etat_gates():
        ok = lit_alive or compare_hp
        if not ok:
            rc = 1
        print("  [%s] %-30s %-52s alive=%s hp=%s"
              % ("OK " if ok else "ROUGE", cle_[1], motif, lit_alive, compare_hp))
        print("        %s" % cle_[0])
    print("")
    print("Un balayage SANS gate visite les cadavres-au-chargement (`decisionView.units[]` les")
    print("conserve). `defender_fixed_armor` etait le seul dans ce cas -- il a recu son gate")
    print("`uc.alive` en #462-r4b-r1-r1-r1-r1-b-r1-r1-r3-r1-r1.")
    return rc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--step", choices=sorted(_STEPS), default="ventilation")
    a = ap.parse_args()
    return _STEPS[a.step]()


if __name__ == "__main__":
    raise SystemExit(main())
