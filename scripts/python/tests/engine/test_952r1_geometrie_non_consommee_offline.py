"""GARDE #952-r1 (OFFLINE PURE) -- la geometrie de `1190 HuntersBeyondDeath` reste HORS du registre,
et le GATE du malus n'est PAS ce selecteur.

`#952-r1` est **fermé EN REFUS**, et ce fichier est ce qui rend le refus verifiable plutot que
declaratif. Le `CreateTargetSelector` de `HuntersBeyondDeathEffect` est LU et mirrore verbatim dans
la docstring de sa classe :

    UnitsWithTrait( SurroundingEnemies(Owner@+0x30, <+0x50>, range = 2, unique = 1, selType = 3),
                    0x3ea = Psyker, 3 )

Il MATERIALISE `EffectComponent.Targets@+0x48` -- ce que l'UI affiche et ce que lirait
`IdunBattleLogic.Entities.DSLTriggers$$IsEffectTarget`. Mais **aucun lecteur porte d'`IsEffectTarget`
ne le consomme pour 1190**, et ce n'est plus une liste recopiee : `test_toute_entree_du_registre_
a_un_LECTEUR_porte` le DERIVE d'`engine/**` (foyer + relais qui TRANSMETTENT un effect_type), et son
second bras exige que `1190` reste ABSENT de cette derivation. L'inscrire aujourd'hui serait un port
SPECULATIF -- ce que l'en-tete du foyer refuse explicitement.

⚠ LE CONTENU DU REGISTRE NE SE RECOPIE PLUS ICI (#10027). Cette docstring a porte « porte `1026` et
`1191` » ; l'egalite en dur qui la doublait a rougi le jour ou `1500 WayOfTheShortBlade_Additional
AttackMarker` est entre AVEC son lecteur (#1019-r2) -- une entree LEGITIME refusee par un cliquet
qui gardait un inventaire au lieu d'une regle. Le nombre d'entrees se re-derive ; ce qui est garde,
c'est « chacune a un lecteur » et « 1190 n'en est pas ».

⚠ LA CONFUSION CONTRE LAQUELLE CE FICHIER GARDE. Le GATE du malus n'est PAS ce selecteur : il
RE-DERIVE la geometrie (`NOT AmountIsGreater(MinDistance(EffectSource, Caster@+0x48), Direct(2))`)
et porte sur l'**ATTAQUANT** du coup courant, la ou le selecteur vise **les Psykers ennemis**. Deux
sujets differents. Router le gate par `IsEffectTarget` changerait donc de sujet, en silence -- et
c'est exactement ce qu'un lecteur pourrait faire en voyant une geometrie « lue mais pas branchee ».

ASCII only.
"""
from __future__ import annotations

import ast
import importlib
from pathlib import Path

from engine.entities.effect_targets import EFFECT_TARGET_SELECTORS, is_effect_target
from engine.entities.effect_type import EffectType
from engine.entities.effects.loki.hunters_beyond_death import HuntersBeyondDeathEffect

DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/entities/effect_targets.py",
        "scripts/python/engine/entities/effects/loki/hunters_beyond_death.py",
        "scripts/python/engine/entities/effect_type.py",
    ),
    "build": True,          # le gate lit le gameconfig d'`AppData` (la magnitude `dmgReduction`)
    "toujours": False,
    "raison": "Il garde un REFUS : la geometrie de 1190 est lue mais NON consommee, et le gate du "
              "malus porte sur un AUTRE sujet. Inscrire l'une en croyant brancher l'autre ne leve "
              "rien et deplace le malus des attaquants vers les cibles.",
    # REGIME BALAYAGE -- l'etage << chaque entree du registre a un LECTEUR >> DERIVE ses sites de
    # tout `engine/**/*.py` (cf. `test_toute_entree_du_registre_a_un_LECTEUR_porte`). Aucune
    # enumeration ne peut le borner : le lecteur d'une entree FUTURE vit dans un fichier qui
    # n'existe pas encore -- c'est precisement le gisement garde.
    "hors_confrontation":
        "Il BALAIE `scripts/python/engine/**/*.py` pour resoudre, effect_type par effect_type, le "
        "site qui passe cet ordinal a `IsEffectTarget`/`is_effect_target`. Ce dont son VERDICT "
        "depend est nomme dans `chemins` (le registre, l'effet refuse, le mirror d'enum) ; ce "
        "qu'il LIT est le paquet moteur.",
}

HBD = int(EffectType.HuntersBeyondDeath)                              # 0x4a6 = 1190
PSYKER_SUPPRESSION = int(EffectType.HuntersBeyondDeathPsykerSuppression)   # 0x4a7 = 1191
BIG_TARGET_ADJACENT = int(EffectType.BigTarget_AdjacentEffect)        # 0x402 = 1026
#: #1015-r1 -- la TROISIEME geometrie du registre (`SynapseEffect$$CreateTargetSelector`), entree
#: avec son lecteur (le gate `NOT IsEffectTarget(Owner, 0x41c)` de `InstinctiveBehaviour`).
SYNAPSE = int(EffectType.Synapse_Effect)                              # 0x41c = 1052
NIVEAU, MULT = 50, 100


class _MondeVide:
    """Substrat minimal : `is_effect_target` doit sortir AVANT de le toucher (pas d'entree)."""

    def unit_ids(self):
        raise AssertionError("le registre a ete consulte APRES avoir accepte 1190")

    def carries(self, uid, effect_type):
        raise AssertionError("le registre a ete consulte APRES avoir accepte 1190")


def _effet() -> HuntersBeyondDeathEffect:
    return HuntersBeyondDeathEffect(name=EffectType.HuntersBeyondDeath.name, effect_type=HBD,
                                    target=1, active=True,
                                    ability_level=NIVEAU, ability_variables_multiplier=MULT)


def _ctx(att_pos, owner_pos=(0, 0)) -> dict:
    """Le contexte que l'agregateur d'aura defense thread : un Psyker ENNEMI a `att_pos`."""
    return {"owner_team": 1, "owner_pos": owner_pos, "tgt_team": 1,
            "att_team": 2, "att_pos": att_pos, "att_traits": ["Psyker"]}


# ------------------------------------------------------------------ le registre, et son contenu

def test_le_registre_ne_porte_QUE_les_geometries_CONSOMMEES():
    """Cliquet du registre : `1190` n'y est pas, et il n'y entre pas par accident.

    ⚠ CE TEST A CHANGE DE FORME (#10027). Il figeait `set(EFFECT_TARGET_SELECTORS) == {1026, 1191,
    1052}` -- une EGALITE en dur, donc un cliquet qui rougit sur toute entree LEGITIME. C'est
    arrive : `1500 WayOfTheShortBlade_AdditionalAttackMarker` est entre avec #1019-r2 et **son
    lecteur avec lui** (`way_of_the_short_blade.py` : `_is_effect_target(state, ev.actor_id,
    ADDITIONAL_ATTACK_MARKER) is True`, le gate `IsEffectTarget(Caster@<DSLSelectors+0x48>, 0x5dc)`
    de `...Triggered.Loki.WayOfTheShortBlade_AttackAbility$$CreateTrigger`).

    Ce que l'egalite VOULAIT garder tient en deux propositions, et elles sont desormais gardees
    SEPAREMENT, chacune par ce qui la rend vraie :
      * `1190` reste DEHORS -- ici, et c'est le seul invariant qui n'a aucune raison de bouger ;
      * toute entree a un LECTEUR -- `test_toute_entree_du_registre_a_un_LECTEUR_porte`, qui le
        DERIVE du paquet moteur au lieu de recopier une liste. Une entree neuve SANS lecteur
        rougit toujours ; une entree neuve AVEC son lecteur passe, ce qui est la regle voulue
        (« un ajout doit etre conscient -- et s'accompagner de son lecteur »)."""
    assert HBD not in EFFECT_TARGET_SELECTORS, (
        "1190 est ENTRE au registre. Le `CreateTargetSelector` de `HuntersBeyondDeathEffect` "
        "materialise `Targets`, mais AUCUN lecteur porte ne le consomme, et le gate du malus "
        "RE-DERIVE sa geometrie sur un AUTRE sujet (l'attaquant, pas les Psykers ennemis) -- "
        "cf. `test_INSCRIRE_1190_au_registre_ne_change_RIEN_au_gate`.")
    assert HBD != PSYKER_SUPPRESSION and HBD == 1190 and PSYKER_SUPPRESSION == 1191
    # NON-DEGENERESCENCE : les trois entrees d'origine sont TOUJOURS la. Sans ce cran, un registre
    # vide passerait les deux assertions ci-dessus et ce fichier ne garderait plus rien.
    for ordinal, nom in ((BIG_TARGET_ADJACENT, "1026 BigTarget_AdjacentEffect"),
                         (PSYKER_SUPPRESSION, "1191 HuntersBeyondDeathPsykerSuppression"),
                         (SYNAPSE, "1052 Synapse_Effect")):
        assert ordinal in EFFECT_TARGET_SELECTORS, (
            "%s a DISPARU du registre : le foyer ne porte plus la geometrie qu'il gardait" % nom)


# ------------------------------------------------- le cran DERIVE : une entree = un lecteur porte

#: Les noms sous lesquels le foyer unique est APPELE. `IsEffectTarget` est le noeud DSL
#: (`entities/triggers.py`), `is_effect_target` la fonction du foyer -- rejointe aussi bien en
#: import direct (`_is_effect_target(...)`) qu'en methode de scene (`sc.is_effect_target(...)`) ou
#: par `getattr(scene, "is_effect_target", ...)(...)`.
_NOMS_LECTEUR = ("IsEffectTarget", "is_effect_target", "_is_effect_target", "_iet")
#: `engine/entities/effect_targets.py` DEFINIT le foyer et le registre : il ne compte pas comme
#: lecteur (sinon toute entree se prouverait elle-meme, et le cran serait vacant).
_HORS_LECTEURS = ("engine/entities/effect_targets.py",)


def _resout(noeud, mod):
    """L'ordinal designe par un argument d'appel, resolu CONTRE LE MODULE qui l'ecrit.

    Les sites n'ecrivent presque jamais l'ordinal : ils ecrivent `SYNAPSE_EFFECT`,
    `ADDITIONAL_ATTACK_MARKER`, `_OWNER_SUPPRESS`, `int(EffectType.X)`. Resoudre par le module
    IMPORTE est ce qui rend ce balayage DERIVE et non declaratif -- et c'est aussi ce qui le fait
    suivre un renommage de constante sans qu'on y touche."""
    if isinstance(noeud, ast.Constant):
        # `bool` est un `int` en Python : sans ce cran, le `unknown_is_target=True` de
        # `IsEffectTarget(Owner(), SYNAPSE_EFFECT, unknown_is_target=True)` prouverait un lecteur
        # pour « l'effet 1 ». Un drapeau ne designe aucun `EffectType`.
        return int(noeud.value) if type(noeud.value) is int else None
    if isinstance(noeud, ast.Call):                        # `int(...)`
        return _resout(noeud.args[0], mod) if noeud.args else None
    cible = mod
    if isinstance(noeud, ast.Name):
        cible = getattr(mod, noeud.id, None)
    elif isinstance(noeud, ast.Attribute):
        base = _objet(noeud.value, mod)
        cible = getattr(base, noeud.attr, None) if base is not None else None
    else:
        return None
    try:
        return int(cible)
    except (TypeError, ValueError):
        return None


def _objet(noeud, mod):
    if isinstance(noeud, ast.Name):
        return getattr(mod, noeud.id, None)
    if isinstance(noeud, ast.Attribute):
        base = _objet(noeud.value, mod)
        return getattr(base, noeud.attr, None) if base is not None else None
    return None


def _est_appel_de(noeud, noms) -> bool:
    """Les quatre formes sous lesquelles nos sites appellent le foyer ou l'un de ses relais."""
    if not isinstance(noeud, ast.Call):
        return False
    if getattr(noeud.func, "id", None) in noms or getattr(noeud.func, "attr", None) in noms:
        return True
    # `getattr(scene, "is_effect_target", <defaut>)(uid, ET)` -- le nom est une CHAINE.
    return (isinstance(noeud.func, ast.Call)
            and getattr(noeud.func.func, "id", None) == "getattr"
            and any(isinstance(a, ast.Constant) and a.value in noms for a in noeud.func.args))


def _sources():
    """`[(rel, source, arbre)]` pour tout `engine/**/*.py` analysable, hors le foyer lui-meme."""
    racine = Path(__file__).resolve().parents[2] / "engine"
    out = []
    for p in sorted(racine.rglob("*.py")):
        rel = str(p.relative_to(racine.parent)).replace("\\", "/")
        if rel in _HORS_LECTEURS:
            continue
        src = p.read_text(encoding="utf-8", errors="replace")
        try:
            out.append((rel, src, ast.parse(src)))
        except SyntaxError:
            continue
    return out


def _parametres(fn) -> set:
    a = fn.args
    return {p.arg for p in (list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs))}


def _relais(fichiers):
    """Les fonctions qui TRANSMETTENT un effect_type au foyer -- point fixe, parce qu'un site
    n'appelle presque jamais le foyer directement.

    Mesure qui a impose cette passe (#10027) : `1026 BigTarget_AdjacentEffect` etait declare
    ORPHELIN par un balayage qui ne cherchait que `_NOMS_LECTEUR`, alors que son lecteur existe --
    `components.py` : `is_target_of_adjacent_friend_aura(state, uid,
    int(EffectType.BigTarget_AdjacentEffect))`, un WRAPPER qui delegue a `is_effect_target`. Lister
    les wrappers a la main aurait reproduit le vice qu'on repare : ils sont DERIVES.

    ⚠ LE CRITERE EST « TRANSMET », PAS « ATTEINT », et la difference est MESUREE. Un premier point
    fixe sur « la fonction appelle quelque chose qui appelle le foyer » a rendu **361 relais** --
    `execute`, `apply`, `matches`, `generate`, `_score` : la quasi-totalite du moteur. Le cran
    devenait VACANT (tout appel a `execute(x, 7)` prouvait un lecteur pour l'effet 7 -- on voyait
    sortir les ordinaux `0`, `1`, `2`, `5`...). Une fonction n'est un relais que si elle passe
    **l'un de ses PROPRES PARAMETRES** en position effect_type : c'est ce qui distingue un wrapper
    de la geometrie d'un appelant quelconque."""
    noms = set(_NOMS_LECTEUR)
    for _ in range(6):                                     # profondeur constatee : 2 ; marge x3
        neufs = set()
        for _rel, _src, arbre in fichiers:
            for fn in ast.walk(arbre):
                if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if fn.name in noms:
                    continue
                params = _parametres(fn)
                if not params:
                    continue
                for n in ast.walk(fn):
                    if not _est_appel_de(n, noms):
                        continue
                    passes = list(n.args[1:]) + [k.value for k in n.keywords]
                    if any(isinstance(a, ast.Name) and a.id in params for a in passes):
                        neufs.add(fn.name)
                        break
        if not neufs - noms:
            break
        noms |= neufs
    return noms


def _lecteurs_derives():
    """`{effect_type: [<module>:<ligne>]}` -- balaye `engine/**`, resout, et rend AUSSI ses comptes
    de visite : un balayage qui ne visite rien rendrait un dict vide, donc « aucune entree n'a de
    lecteur », donc un rouge qui accuserait le REGISTRE au lieu du BALAYAGE."""
    fichiers = _sources()
    noms = _relais(fichiers)
    par_effet: dict = {}
    visites, avec_appel = 0, 0
    for rel, src, arbre in fichiers:
        if not any(n in src for n in noms):
            continue
        visites += 1
        appels = [n for n in ast.walk(arbre) if _est_appel_de(n, noms)]
        if not appels:
            continue
        nom_mod = "engine." + rel[len("engine/"):-len(".py")].replace("/", ".")
        if nom_mod.endswith(".__init__"):
            nom_mod = nom_mod[:-len(".__init__")]
        try:
            mod = importlib.import_module(nom_mod)
        except Exception:                                  # noqa: BLE001
            # Module non importable seul : il ne prouve rien, et il ne MASQUE rien non plus --
            # l'entree restera orpheline et le test le DIRA.
            continue
        avec_appel += 1
        for n in appels:
            # L'effect_type n'est JAMAIS le 1er argument (le 1er est le SUJET : selecteur, uid,
            # state) : les formes portees le mettent en 2e ou 3e position.
            for a in list(n.args[1:]) + [k.value for k in n.keywords]:
                v = _resout(a, mod)
                if v is not None:
                    par_effet.setdefault(int(v), []).append("%s:%d" % (rel, n.lineno))
    return par_effet, visites, avec_appel


def test_toute_entree_du_registre_a_un_LECTEUR_porte():
    """LE CRAN QUI REMPLACE L'EGALITE EN DUR. Chaque `effect_type` du registre doit etre passe a
    `IsEffectTarget`/`is_effect_target` par un site EXECUTABLE d'`engine/**` -- resolu, pas liste.

    Une geometrie inscrite sans lecteur est un port SPECULATIF : elle materialise `Targets` que
    personne n'interroge. C'est exactement le refus que `1190` incarne, et le cran qui manquait
    pour les autres entrees (seul `1052` avait le sien, en dur)."""
    par_effet, visites, avec_appel = _lecteurs_derives()
    # NON-VIDE DU RECENSEUR, deux etages : des fichiers MENTIONNENT le foyer, et certains
    # l'APPELLENT vraiment. Sans ce cran, un balayage casse rendrait « aucun lecteur » et ferait
    # accuser le registre.
    assert visites >= 5, "le balayage n'a visite que %d fichier(s) mentionnant le foyer" % visites
    assert avec_appel >= 3, (
        "seuls %d fichier(s) portent un APPEL resolu du foyer : le balayage ne reconnait plus les "
        "formes d'appel (`_NOMS_LECTEUR`)" % avec_appel)
    orphelines = sorted(e for e in EFFECT_TARGET_SELECTORS if int(e) not in par_effet)
    assert not orphelines, (
        "geometrie(s) au registre SANS lecteur porte : %s. Une entree materialise `Targets` que "
        "personne n'interroge -- c'est un port SPECULATIF, et c'est le refus meme que 1190 "
        "incarne. Inscrire la geometrie ET son lecteur DANS LE MEME COMMIT, ou ne pas l'inscrire."
        % [(e, EffectType(e).name if e in set(int(x) for x in EffectType) else "?")
           for e in orphelines])
    # LE CRAN N'EST PAS VACANT : `1190`, dont on sait par RE qu'aucun lecteur ne le consomme,
    # DOIT rester absent de la derivation. Sans ce bras, un balayage qui rendrait « tout le monde
    # a un lecteur » passerait pour un garde-fou.
    assert HBD not in par_effet, (
        "1190 a desormais un lecteur (%s) : le REFUS de #952-r1 ne tient plus, et l'inscrire au "
        "registre redevient une question ouverte -- la trancher, ne pas la subir."
        % (par_effet.get(HBD),))


def test_le_cran_de_lecteur_MORD_sur_une_entree_FICTIVE(monkeypatch):
    """CONTRE-EPREUVE du cran ci-dessus. On inscrit une geometrie qu'AUCUN site n'interroge : la
    derivation doit la nommer orpheline. Sans ce bras, un balayage devenu trop large (le premier
    point fixe en rendait **361** relais, donc un lecteur pour presque tout entier ecrit dans le
    moteur) resterait vert en ne prouvant plus rien."""
    fictif = 999999
    monkeypatch.setitem(EFFECT_TARGET_SELECTORS, fictif, lambda world, uid: set())
    par_effet, _v, _a = _lecteurs_derives()
    assert fictif not in par_effet, (
        "la derivation trouve un lecteur pour un effet FICTIF : son critere est trop large, elle "
        "ne garde plus rien (%s)" % (par_effet.get(fictif),))
    orphelines = sorted(e for e in EFFECT_TARGET_SELECTORS if int(e) not in par_effet)
    assert orphelines == [fictif], orphelines


def test_la_geometrie_de_1052_a_bien_un_LECTEUR_porte():
    """Le cran que le test ci-dessus ne porte pas : une entree au registre SANS lecteur serait une
    geometrie morte -- exactement ce que `1190` illustre. On resout le lecteur pour de vrai."""
    from engine.runner.operations.triggers.loki.instinctive_behaviour import (
        SYNAPSE_EFFECT, updated_forced_target)
    assert SYNAPSE_EFFECT == SYNAPSE, "le lecteur ne cite pas le meme effectType"
    arbre = updated_forced_target()
    # L'arbre est un `DSLSelectors$$If(gate, enemies, None())` : le gate DOIT contenir le noeud.
    from engine.entities.triggers import IsEffectTarget

    def _cherche(n, vus=None):
        vus = vus if vus is not None else set()
        if id(n) in vus or n is None:
            return False
        vus.add(id(n))
        if isinstance(n, IsEffectTarget):
            return int(n.effect_type) == SYNAPSE
        for v in vars(n).values() if hasattr(n, "__dict__") else ():
            if _cherche(v, vus):
                return True
        for s in getattr(type(n), "__slots__", ()) or ():
            if _cherche(getattr(n, s, None), vus):
                return True
        return False

    assert _cherche(arbre), (
        "aucun `IsEffectTarget(_, 1052)` dans `updated_forced_target()` -- la geometrie de 1052 "
        "serait au registre SANS lecteur")


def test_une_geometrie_NON_PORTEE_rend_None_jamais_False():
    """La degradation est NOMMEE : `None` = « non porte ». Rendre `False` affirmerait que le refresh
    natif a laisse la liste VIDE -- ce qu'on n'a pas mesure. Le monde n'est meme pas touche."""
    assert is_effect_target(_MondeVide(), 42, HBD) is None


# ------------------------------------------------------- le GATE : un AUTRE sujet, un AUTRE chemin

def test_le_gate_du_malus_MORD_dans_les_deux_sens():
    """CONTROLE DE NON-DEGENERESCENCE, sans lequel l'etage suivant serait vide de sens :
    `NOT AmountIsGreater(MinDistance(src, Caster), Direct(2))` est bien `d <= 2`."""
    eff = _effet()
    assert eff.create_aura_defense_damage_malus_for_ally(_ctx((2, 0))) is not None   # d = 2
    assert eff.create_aura_defense_damage_malus_for_ally(_ctx((3, 0))) is None       # d = 3
    # ... et le TRAIT est un conjoint distinct de la distance.
    sans_psyker = dict(_ctx((2, 0)), att_traits=[])
    assert eff.create_aura_defense_damage_malus_for_ally(sans_psyker) is None


def test_INSCRIRE_1190_au_registre_ne_change_RIEN_au_gate(monkeypatch):
    """LE CRAN QUI COMPTE. Le selecteur materialise `Targets` (les Psykers ENNEMIS) ; le gate
    re-derive `MinDistance` et porte sur l'ATTAQUANT. Les deux ne partagent aucun chemin -- donc
    brancher l'un ne branche pas l'autre, et un lecteur qui croirait << activer >> le malus en
    inscrivant la geometrie n'aurait rien active du tout.

    On INSCRIT reellement 1190 (avec une geometrie qui rendrait TOUT LE MONDE cible) et on verifie
    que les quatre verdicts du gate sont inchanges."""
    monkeypatch.setitem(EFFECT_TARGET_SELECTORS, HBD, lambda world, uid: {1, 2, 3, 42})
    assert HBD in EFFECT_TARGET_SELECTORS                    # la mutation A mordu
    eff = _effet()
    assert eff.create_aura_defense_damage_malus_for_ally(_ctx((2, 0))) is not None
    assert eff.create_aura_defense_damage_malus_for_ally(_ctx((3, 0))) is None
    sans_psyker = dict(_ctx((2, 0)), att_traits=[])
    assert eff.create_aura_defense_damage_malus_for_ally(sans_psyker) is None
    ami = dict(_ctx((2, 0)), att_team=1)                     # `NOT AreFriends(src, Caster)`
    assert eff.create_aura_defense_damage_malus_for_ally(ami) is None
