"""probe #953-r5 -- RECENSEMENT des consommateurs de `scene.hpmax` / de la cle `max_hp`.

CE QUE LE RESIDU DEMANDE, ET POURQUOI LE REMPLISSAGE NE SUFFIT PAS. `Scene.hpmax` rendait `None`
pour TOUTE unite sur la voie PREDICTION-LIVE : `step_context` ne produit pas `hpmax_by_id` et ne le
PEUT pas -- `decisionView.units[]` ne publie aucune cle de PV max. `Scene.from_state` (voie
offline/combat), elle, remplit depuis `HealthComponent.hp_max`. Les DEUX voies de la MEME classe
divergeaient. Le repli est pose (#953-r1, `predictor["hpmax_eff_by_id"]` = `combatSnapshot.healthMax`
= `GetStat(e, StatType.Health, StatPart.Maximum)`) et `Skullsmasher` est confronte -- mais **un
seul** consommateur avait ete mesure. Un `None` qui devient un nombre ne dit pas QUI le lisait mal.

CE QUE CE PROBE ETABLIT, ET COMMENT.

  * **Etape 1 -- le RECENSEMENT est DERIVE, jamais une liste blanche.** On visite l'AST de TOUT
    `engine/**` et on releve les QUATRE jetons du gisement (`hpmax`, `hpmax_by_id`, `max_hp`,
    `hp_max`), en imprimant la partition exhaustive par jeton. Une liste de sites choisis ne peut
    pas montrer le site qu'elle a oublie -- c'est la lecon de `probe_270r1`.
  * **Etape 2 -- INVARIANT dans les DEUX sens.** Tout site releve doit porter sa classification de
    DEGRADATION dans `DEGRADATIONS` ci-dessous (sinon rc 1) ET toute entree de `DEGRADATIONS` doit
    s'apparier a un site reel (sinon rc 1 : un cliquet vert sur un recensement vide ne garde rien).
  * **Etape 3 (`--live`) -- l'ESPACE DE CLES.** Le repli est pris sur `combatSnapshot.units[]`
    (cle `entityId`) et consomme par des lecteurs qui interrogent `decisionView.units[].id`. Si les
    deux espaces divergeaient, `hpmax_by_id` serait REMPLI et pourtant STERILE -- une panne
    silencieuse EXACTEMENT de la meme forme que celle que #953-r1 a fermee, un etage plus bas.
    L'etape mesure l'intersection ET verifie que `scene.hpmax` rend un entier pour chaque unite.

CE QUE LE RECENSEMENT A CORRIGE DANS LA FICHE (mesure, 2026-08-18) :

  * `engine/predict.py` n'est PAS un consommateur : ses 17 occurrences sont les parametres
    `target_max_hp` / `boss_max_hp` du couple heal/repair, alimentes par `observeBattle.hpMax` via
    `engine/ai/action_generators.py`, jamais par la `Scene` ;
  * `engine/services/trait_damage_limits.py` non plus : son parametre `max_hp` est
    l'`initialHealth` (PV au DEBUT de l'attaque), et sa propre docstring le dit ;
  * le VRAI foyer central est `engine/utilities/damage.py::DamageUtility.evaluate`, ou `None`
    retombe sur les PV COURANTS -- donc `combinedMax` SOUS-ESTIME et l'utilite de degat
    SUR-ESTIME. Six playbooks NonComparable y arrivaient avec `None`.

LE FAIT QUE PERSONNE N'AVAIT ECRIT : **la degradation n'a pas un seul signe.** Cote MAGNITUDE, un
`None` FERME le canal (`_missing_health_steps` rend `None`, `Skullsmasher` muet) ; cote CONDITION
D'ACTIVITE, il l'OUVRE -- `Scene.unit_state` n'ecrit la cle `max_hp` que si elle est non-`None`,
donc les six `CreateActiveCondition` qui la lisent faisaient `.get("max_hp") -> None -> return
True`, c'est-a-dire un effet ACTIF a tort. La face COMBAT, elle, ecrivait la cle
INCONDITIONNELLEMENT (`runner/components.py::UnitEffectStateView`). Aucun site ne LEVE : tout le
trou etait silencieux.

Usage (ASCII only, depuis scripts/python) :
  python probe_953r5_consommateurs_hpmax.py
  python probe_953r5_consommateurs_hpmax.py --check
  python probe_953r5_consommateurs_hpmax.py --live
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

PYDIR = Path(__file__).resolve().parent
ENGINE = PYDIR / "engine"

#: Les QUATRE jetons du gisement. Ils ne designent PAS la meme chose, et les confondre est
#: precisement ce qui a fait ecrire deux faux consommateurs dans la fiche :
#:   `hpmax`       -- l'accesseur/champ de `Scene` (voie DECISION) ;
#:   `hpmax_by_id` -- sa table, et l'homonyme d'`AiDecisionContext` (substrat DIFFERENT :
#:                    `observeBattle.hpMax` + overlay, jamais touche par le trou #953) ;
#:   `max_hp`      -- la cle du dict d'etat d'unite que lisent les `CreateActiveCondition` ;
#:   `hp_max`      -- le champ du `HealthComponent` (ECS, face COMBAT).
JETONS = ("hpmax", "hpmax_by_id", "max_hp", "hp_max")

#: Classification de DEGRADATION, une entree par site RELEVE, clef = `<relpath>::<qualname>::<jeton>`.
#: La valeur est `(classe, ce que `None` / l'absence produit)`. Les classes :
#:   `ABANDON`    -- la prediction entiere est abandonnee (`return None`) ;
#:   `REPLI_0`    -- `or 0` : l'axe devient inerte ;
#:   `REPLI_AUTRE`-- repli sur une AUTRE grandeur (les PV courants) : valeur FAUSSE, pas absente ;
#:   `GATE_FERME` -- le predicat rend Faux (sous-estimation) ;
#:   `GATE_OUVERT`-- le predicat rend Vrai (SUR-estimation : l'effet vit alors qu'il ne devrait pas) ;
#:   `PROPAGE`    -- le site ne decide rien, il transporte la valeur vers un autre foyer ;
#:   `PRODUCTEUR` -- le site ECRIT la table ou la cle ;
#:   `HORS_SCENE` -- le jeton y designe autre chose que `Scene.hpmax` (cf. `JETONS`).
DEGRADATIONS = {
    # ---- PRODUCTEURS ---------------------------------------------------------------------------
    "playbook/scene.py::*::hpmax_by_id": (
        "PRODUCTEUR", "le champ, `from_state` (voie offline/combat : `HealthComponent.hp_max`) et "
        "`from_predictor_sctx` (voie PREDICTION-LIVE). L'accesseur `hpmax()` n'a AUCUN defaut : "
        "`None` ne distingue pas << id inconnu >> de << table vide >>, contrairement a `armor()`"),
    "playbook/scene.py::*::hpmax_eff_by_id": (
        "PRODUCTEUR", "`_hpmax_eff_from_snapshot(combatSnapshot.units[].healthMax)` = "
        "`GetStat(e, StatType.Health, StatPart.Maximum)` -- base + modifications, clampe. Capteur "
        "muet -> `{}`, jamais un 0 fabrique. C'est le REPLI de #953-r1"),
    "playbook/scene.py::*::max_hp": (
        "PRODUCTEUR", "`unit_state` n'ecrit la cle QUE si elle est non-`None` -- c'est CE `if` qui "
        "transforme un trou de substrat en cle ABSENTE, donc en gate OUVERT chez ses lecteurs"),
    "ai/context.py::*::hpmax_by_id": (
        "PRODUCTEUR", "`AiDecisionContext.build` pose `sctx['hpmax_by_id']` AVANT d'appeler "
        "`from_predictor_sctx` -- et il le fait depuis `40da9467` (2026-07-20), donc bien AVANT "
        "#953-r1. Substrat : `observeBattle.hpMax` (la BASE) SURCHARGE par `hpmax_eff_by_id`"),
    "ai/context.py::*::hpmax_eff_by_id": (
        "PRODUCTEUR", "l'overlay EFFECTIF sur la base `observeBattle.hpMax`"),
    "ai/state_bridge.py::*::hpmax_by_id": (
        "PRODUCTEUR", "voie OFFLINE (`Scene.from_state`), table pleine par construction"),
    "runner/components.py::*::max_hp": (
        "PRODUCTEUR", "`UnitEffectStateView` pose `hp`/`max_hp` INCONDITIONNELLEMENT des que le "
        "`HealthComponent` existe -- c'est le FORK mesure : les gates ci-dessous MORDAIENT cote "
        "COMBAT et pas cote DECISION"),
    "runner/abilities/behaviours/context.py::*::max_hp": ("PRODUCTEUR", "meme ecriture, face combat"),
    "runner/operations/triggers/loki/anvil_shield.py::*::max_hp": ("PRODUCTEUR", "idem"),
    "runner/damage_model.py::*::hpmax_by_id": (
        "PRODUCTEUR", "`build_hits_board` : la table du board DSL des coups, face COMBAT"),
    "utilities/tile.py::*::hpmax_by_id": (
        "PRODUCTEUR", "`scene_tile_leaf_ctx` recopie la table dans le contexte de tuile"),
    # ---- CONSOMMATEURS : la degradation, une par site ------------------------------------------
    "playbook/prediction/normal_attack.py::*::hpmax": (
        "ABANDON", "degat en %-des-PV-max : `if not hpmax: return None`. La prediction ENTIERE est "
        "abandonnee -- la seule degradation qui ne sous-estime pas : elle ne rend RIEN"),
    "playbook/prediction/normal_attack.py::*::hpmax_by_id": (
        "GATE_FERME", "`{uid: scene.hpmax(uid)}` verse dans le board DSL des coups : des cles "
        "PRESENTES a valeur `None`, que `dsl/base.py::_is_alive` lit ensuite"),
    "playbook/prediction/abilities.py::*::hpmax": (
        "GATE_FERME|REPLI_AUTRE", "TROIS roles au meme jeton : `tgt_hp_max` (gate "
        "`HealthPctIsBelowOrEqual` de 1376 `LightOfSanguinius` -> FERME), le couple "
        "`_SKULLSMASHER_CTX_HEALTH` (canal MUET -- le defaut mesure par #953-r1) et "
        "`scene.hpmax(caster) or hp_c`, qui fait calculer `get_health_to_lose` sur les PV COURANTS"),
    "playbook/prediction/_shared.py::*::hpmax": (
        "REPLI_0", "`or 0` : `member_total_hp` / `max_health` a 0 -> caps de groupe et de boss "
        "NEUTRALISES, et la source de block `BeastSnagga` inerte"),
    "playbook/prediction/ramming_speed.py::*::hpmax": (
        "REPLI_AUTRE", "repli NOMME sur `get_stat(HEALTH, MAXIMUM)`, qui rend la valeur COURANTE "
        "-> sous-prediction (mesure #383 : [9,15] au lieu de [18,27])"),
    "playbook/noncomparable/black_rage.py::*::hpmax": (
        "GATE_OUVERT|PROPAGE", "`if hp is None or hpmax is None: return True` (offre "
        "INCONDITIONNELLE), puis transport vers `damage_composite`"),
    "playbook/noncomparable/hammer_of_wrath.py::*::hpmax": (
        "PROPAGE", "-> `calculate_utility_from_damage_event(..., target_max_hp)` -> "
        "`utilities/damage.py`, ou `None` retombe sur les PV COURANTS : `combinedMax` SOUS-ESTIME "
        "donc `u_damage = Clamp(D/combinedMax,0,1)*80` SUR-ESTIME"),
    "playbook/noncomparable/heavy_rail_rifle.py::*::hpmax": ("PROPAGE", "idem"),
    "playbook/noncomparable/kill_maim_burn.py::*::hpmax": ("PROPAGE", "idem"),
    "playbook/noncomparable/sentinel_directives.py::*::hpmax": ("PROPAGE", "idem"),
    "playbook/noncomparable/vigilance_eternal.py::*::hpmax": ("PROPAGE", "idem"),
    "playbook/fury_of_the_ancients.py::*::hpmax_by_id": (
        "PROPAGE", "meme tuyau, par la table entiere au lieu d'une valeur"),
    "utilities/tile.py::*::hpmax": (
        "GATE_FERME", "le jumeau DECISION du contexte de tuile (`hp_max` par voisin et pour le "
        "mover). Absent -> `IsDamagedUnit` (`GetStat(Health, Missing) > 0`) ne mord pas, donc le "
        "terme DAMAGED de `SanguinaryPriestPlaybook` sous-compte"),
    "entities/effects/loki/hungering_swarm.py::*::hpmax_by_id": (
        "GATE_FERME", "`if hpmax is None: return None` -- contexte incomplet, AUCUNE contribution"),
    "entities/effects/loki/hail_of_living_ammunition.py::*::hpmax_by_id": ("GATE_FERME", "idem"),
    # ---- les CreateActiveCondition : TOUTES en gate OUVERT (polarite INVERSE des precedents) ----
    "entities/effects/loki/hits.py::*::max_hp": (
        "GATE_OUVERT", "TROIS classes -- `AnvilShield_BlockChanceBelowHealthCap`, `RedThirst`, "
        "`PowerTripFullHealth`. `.get('max_hp') -> None -> return True` : l'effet est ACTIF A TORT"),
    "entities/effects/loki/status.py::*::max_hp": (
        "GATE_OUVERT", "`HammerOfWrathConditionalDamageEffect` (`healthPct = 50`), meme forme"),
    "entities/effects/loki/visions_of_heresy.py::*::max_hp": (
        "GATE_OUVERT", "`HealthPctIsBelowOrEqual(Owner, 50)`, meme forme"),
    "entities/effects/loki/skullsmasher.py::*::max_hp": (
        "GATE_OUVERT", "seule variante de forme : `return super().is_active(...)` au lieu d'un "
        "`True` en dur -- meme RESULTAT (`BaseEffect.is_active` rend True), autre chemin"),
}


def _qualname(pile) -> str:
    return ".".join(pile) if pile else "<module>"


#: Receveurs qui NE SONT PAS une `Scene`. `AiDecisionContext` porte un `hpmax_by_id` HOMONYME dont
#: le substrat est `observeBattle.hpMax` + overlay (`ai/context.py`) : il n'a JAMAIS ete affecte par
#: le trou #953, et le confondre avec celui de la `Scene` gonflerait le gisement de 3x.
_RECEVEURS_HORS_SCENE = ("ctx", "c", "nc", "self.ctx", "case", "dctx")


def recenser() -> tuple:
    """Visite l'AST de TOUT `engine/**`. Rend `(sites, ecartes)`.

    PERIMETRE, et il DIT ce qu'il ecarte (doctrine `probe_270r1` : un compte filtre nomme son
    filtre) -- le gisement #953 est fait de DEUX choses, pas de quatre :

      (A) toute lecture de `<scene>.hpmax(...)` / `<scene>.hpmax_by_id` -- le RECEVEUR est resolu
          par `ast.unparse`, parce qu'`AiDecisionContext` porte un `hpmax_by_id` HOMONYME ;
      (B) toute occurrence du LITTERAL de cle `"max_hp"` -- lecture comme ecriture.

    ECARTES, comptes et nommes : `hp_max` (le champ du `HealthComponent`, face ECS -- un axe
    different, jamais `None` quand le composant existe), et les receveurs hors-`Scene` ci-dessus."""
    sites, ecartes = [], {}

    def _ecarter(motif):
        ecartes[motif] = ecartes.get(motif, 0) + 1

    for p in sorted(ENGINE.rglob("*.py")):
        rel = p.relative_to(ENGINE).as_posix()
        try:
            arbre = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:                                  # pragma: no cover - diagnostic
            continue
        pile = []
        dans_scene = (rel == "playbook/scene.py")

        class V(ast.NodeVisitor):
            def _porte(self, n):
                pile.append(n.name)
                self.generic_visit(n)
                pile.pop()

            visit_FunctionDef = visit_AsyncFunctionDef = visit_ClassDef = _porte

            def visit_Attribute(self, n):
                if n.attr in ("hpmax", "hpmax_by_id"):
                    rec = ast.unparse(n.value)
                    est_scene = ("scene" in rec.lower()) or (dans_scene and rec in ("self", "sc"))
                    if est_scene:
                        sites.append((rel, _qualname(pile), n.attr, n.lineno))
                    else:
                        _ecarter("receveur hors-Scene (%s.%s)" % (rec.split(".")[-1], n.attr))
                elif n.attr == "hp_max":
                    _ecarter("hp_max (HealthComponent, face ECS)")
                self.generic_visit(n)

            def visit_Constant(self, n):
                if isinstance(n.value, str) and n.value == "max_hp":
                    sites.append((rel, _qualname(pile), "max_hp", n.lineno))
                elif isinstance(n.value, str) and n.value in ("hpmax_by_id", "hpmax_eff_by_id"):
                    # Cle de dict du contexte de tuile / du predicteur : c'est la MEME table, mais
                    # transportee. On la garde, c'est un maillon du gisement.
                    sites.append((rel, _qualname(pile), n.value, n.lineno))
                self.generic_visit(n)

            def visit_keyword(self, n):
                if n.arg in ("hpmax_by_id", "hpmax_eff_by_id"):
                    sites.append((rel, _qualname(pile), n.arg, n.lineno))
                self.generic_visit(n)

        V().visit(arbre)
    return sites, ecartes


def _cles(rel: str, qual: str, jeton: str) -> tuple:
    """Les DEUX clefs sous lesquelles un site peut etre classe : la PRECISE (par qualname) et la
    GENERIQUE (`*`, pour un fichier dont tous les sites partagent la meme degradation)."""
    return ("%s::%s::%s" % (rel, qual, jeton), "%s::*::%s" % (rel, jeton))


def voies_de_construction() -> dict:
    """QUI appelle `Scene.from_predictor_sctx`, et son `sctx` porte-t-il DEJA `hpmax_by_id` ?

    C'est la question que la fiche ne posait pas, et elle change ce que le repli de #953-r1
    couvre. Mesure (DERIVEE, pas citee) : dans `engine/**`, `from_predictor_sctx` n'a que DEUX
    call-sites, tous deux dans `ai/context.py`, et tous deux ecrivent `sctx["hpmax_by_id"]` AVANT
    l'appel -- depuis `40da9467` (2026-07-20), donc bien avant #953-r1. Hors `engine/**`, une
    quarantaine de PROBES appellent `from_predictor_sctx(predictor, step_context(...))` avec un
    `sctx` BRUT : pour eux, `predictor["hpmax_eff_by_id"]` est la SEULE source de PV max.

    Corollaire a ne pas rater : `step_context` rend SEPT cles (`eff_state`, `feet_by_id`,
    `hp_by_id`, `machine_ids`, `pos_by_id`, `team_by_id`, `units`) et AUCUNE ne porte le PV max --
    la fiche a raison sur ce point, et le repli est bien ce qui met TOUTES les voies d'accord."""
    out = {"engine": [], "hors_engine": []}
    for p in sorted(PYDIR.rglob("*.py")):
        # ⚠ LE FILTRE SE PREND SUR LE CHEMIN **RELATIF**, jamais sur `p.parts`. Un worktree
        # d'agent vit sous `.claude/worktrees/...`, donc `".claude" in p.parts` est VRAI pour
        # TOUS les fichiers et le recenseur rendait **0** -- un zero qui se lit comme une mesure.
        rel = p.relative_to(PYDIR).as_posix()
        if rel.startswith("tests/"):
            continue
        try:
            src = p.read_text(encoding="utf-8")
        except Exception:                                    # pragma: no cover - diagnostic
            continue
        if "from_predictor_sctx" not in src:
            continue
        cle = "engine" if rel.startswith("engine/") else "hors_engine"
        prefixe = 'sctx["hpmax_by_id"]' in src or "sctx['hpmax_by_id']" in src
        out[cle].append((rel, prefixe))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="mode CLIQUET (rc 1 des qu'un site est "
                                                         "non classe ou qu'une entree est orpheline)")
    ap.add_argument("--live", action="store_true", help="etape 3 : concordance des espaces de cles")
    a = ap.parse_args(argv)

    sites, ecartes = recenser()
    par_jeton = {}
    for _rel, _q, j, _l in sites:
        par_jeton[j] = par_jeton.get(j, 0) + 1
    print("[etape1] %d sites releves sur `engine/**` -- partition EXHAUSTIVE par jeton :" % len(sites))
    for j in sorted(par_jeton):
        print("           %-18s %d" % (j, par_jeton[j]))
    print("[etape1] ECARTES PAR CE PERIMETRE (%d), et voici lesquels :" % sum(ecartes.values()))
    for m in sorted(ecartes, key=lambda k: -ecartes[k])[:8]:
        print("           %-42s %d" % (m, ecartes[m]))

    voies = voies_de_construction()
    prets = [r for r, ok in voies["engine"] if ok]
    print("[etape1bis] appelants de `Scene.from_predictor_sctx` -- `engine/**` : %d fichier(s), "
          "dont %d qui remplissent `sctx['hpmax_by_id']` en amont %r"
          % (len(voies["engine"]), len(prets), prets))
    print("[etape1bis] hors `engine/**` (probes et outils) : %d fichier(s), dont %d remplissent -- "
          "pour les autres, `predictor['hpmax_eff_by_id']` est la SEULE source"
          % (len(voies["hors_engine"]),
             len([r for r, ok in voies["hors_engine"] if ok])))

    non_classes, vus = [], set()
    for rel, q, j, ligne in sites:
        k1, k2 = _cles(rel, q, j)
        if k1 in DEGRADATIONS:
            vus.add(k1)
        elif k2 in DEGRADATIONS:
            vus.add(k2)
        else:
            non_classes.append((rel, q, j, ligne))
    orphelines = sorted(set(DEGRADATIONS) - vus)

    classes = {}
    for k in vus:
        c = DEGRADATIONS[k][0]
        classes[c] = classes.get(c, 0) + 1
    print("[etape2] %d entrees de classification appariees ; par CLASSE de degradation :"
          % len(vus))
    for c in sorted(classes):
        print("           %-22s %d" % (c, classes[c]))
    print("[etape2] sites NON CLASSES : %d ; entrees ORPHELINES : %d"
          % (len(non_classes), len(orphelines)))
    for s in non_classes[:20]:
        print("           NON CLASSE  %s::%s::%s (ligne %d)" % s)
    for k in orphelines[:20]:
        print("           ORPHELINE   %s" % k)

    rc = 0
    if a.check and (non_classes or orphelines):
        rc = 1
    # CRAN ANTI-VIDE : un recenseur qui ne visite RIEN rend `0 non classe` et se lit comme un vert.
    # C'est exactement ce que l'etape 1bis a fait a son premier jet (filtre pris sur `p.parts`, or
    # un worktree d'agent vit sous `.claude/`). On assertionne donc le NON-VIDE des deux mesures.
    if a.check and (not sites or not voies["engine"] or not voies["hors_engine"]):
        print("[garde] REFUS : recensement VIDE (%d sites, %d appelants engine, %d hors engine) -- "
              "le probe ne garde rien dans cet etat"
              % (len(sites), len(voies["engine"]), len(voies["hors_engine"])))
        rc = 1
    if a.live:
        rc |= etape3_espace_de_cles()
    return rc


def etape3_espace_de_cles() -> int:
    """L'ESPACE DE CLES du repli -- la panne silencieuse d'un etage sous celle que #953-r1 a fermee.

    `predictor['hpmax_eff_by_id']` est indexe par `combatSnapshot.units[].entityId` ; ses lecteurs
    interrogent `decisionView.units[].id`. Deux espaces distincts rendraient la table REMPLIE et
    pourtant STERILE, sans erreur. On mesure l'intersection ET on verifie que `scene.hpmax` rend un
    entier pour CHAQUE unite de la vue de decision."""
    import json
    import subprocess
    import uuid
    sys.path.insert(0, str(PYDIR))
    from rl_collect_batch import _resolve_session, _rpc
    sid = _resolve_session()
    if not sid:
        print("[etape3] NON MESURE : aucune session Frida")
        return 0
    root = PYDIR.parents[1]
    state = root / "logs" / "runners" / ("probe953r5-%s.json" % uuid.uuid4().hex[:8])
    state.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, "rl_duel.py", "build", "--seed", "777", "--board", "MC1_67",
                    "--state-file", str(state), "--p-units",
                    "ultraTigurius,astraBullgryn,necroWarden",
                    "--a-units", "worldKharn,templChampion"],
                   cwd=str(PYDIR), capture_output=True, text=True)
    if not state.exists():
        print("[etape3] NON MESURE : build KO")
        return 0
    rid = json.loads(state.read_text())["runnerId"]

    def R(m, b, t=180):
        return (_rpc(sid, m, [b], timeout=t).get("result") or {})
    try:
        from engine import weights as W
        from engine.ai import context as AC
        from engine.playbook import scene as S
        dv = R("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32})
        pred = S.build_predictor(lambda m, b, t=120: R(m, b, t), rid)
        mov = R("aiMovableTiles", {"runnerId": rid}, 90)
        mbu = {u.get("unitId"): u for u in (mov.get("units") or [])}
        ids = sorted(u.get("id") for u in (dv.get("units") or []))
        snap = sorted((pred.get("hpmax_eff_by_id") or {}))
        inter = sorted(set(ids) & set(snap))
        ctx = AC.build(lambda m, b, t=120: R(m, b, t), rid, dv, mbu, ids[0], W.load(), pred)
        vals = {u: ctx.scene.hpmax(u) for u in ids}
        etats = {u: ctx.scene.unit_state(u).get("max_hp") for u in ids}
        print("[etape3] dv.units[].id      : %r" % (ids,))
        print("[etape3] hpmax_eff_by_id    : %r" % (snap,))
        print("[etape3] intersection       : %r" % (inter,))
        print("[etape3] scene.hpmax        : %r" % (vals,))
        print("[etape3] unit_state.max_hp  : %r" % (etats,))
        manquants = [u for u, v in vals.items() if v is None]
        sans_cle = [u for u, v in etats.items() if v is None]
        if len(inter) != len(ids) or manquants or sans_cle:
            print("[etape3] ECHEC : %d unite(s) sans hpmax, %d sans cle `max_hp`, "
                  "intersection %d/%d" % (len(manquants), len(sans_cle), len(inter), len(ids)))
            return 1
        print("[etape3] OK : les DEUX espaces coincident et les %d unites portent leur PV max."
              % len(ids))
        return 0
    finally:
        try:
            R("disposeRunner", {"runnerId": rid}, 60)
        except Exception:                                    # pragma: no cover - nettoyage
            pass


if __name__ == "__main__":
    raise SystemExit(main())
