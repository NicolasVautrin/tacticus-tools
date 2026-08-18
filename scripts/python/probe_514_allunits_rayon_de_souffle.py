"""#514 (residu `#508-r1`, volet `AllUnits`) -- le noeud le plus partage du ciblage : RE, rayon
de souffle, et le CLIQUET qui empeche la confusion de revenir.

RE -- DECOMPILE = VERITE (build `rnca9r7q6c`, ghidra-mcp)
--------------------------------------------------------
Le jeu a TROIS primitives d'ensemble d'unites, et leurs corps natifs ne different QUE par un
littéral (une classe de selecteur, puis un slot d'interface, puis un `EntityPool`) :

    IdunBattleLogic.Entities.DSLSelectors$$AllUnits
      -> IdunBattle.Entities.Selectors.AllUnitsSelector$$Select
      -> IBattleQuery slot 136 GetAllUnits
      -> IdunBattle.Core.Services.BattleQuery$$GetAllUnits : state.GetPool(EntityPool.AllUnits = 8)
         AUCUN filtre de vie dans le corps (le seul filtre est le `playerEntityId` nullable, qui
         est `null` a tous les call-sites du DSL).

    <le champ PARTAGE `DSLSelectors+0x20`, pose par DSLSelectors$$InitializeShared>
      -> IdunBattle.Entities.Selectors.AllAliveUnitsSelector$$Select
      -> IBattleQuery slot 137 GetAllAliveUnits
      -> IdunBattle.Core.Services.BattleQuery$$GetAllAliveUnits : state.GetPool(EntityPool.AliveUnits = 0)

    IdunBattleLogic.Entities.DSLSelectors$$AllAliveMachines
      -> IdunBattle.Entities.Selectors.AllAliveMachinesSelector$$Select
      -> IBattleQuery slot 151 GetAllAliveMachines
      -> IdunBattle.Core.Services.BattleQuery$$GetAllAliveMachines : state.GetPool(EntityPool.AliveMachines = 6)

Les trois `BattleQuery$$GetAll*` sont le MEME corps a l'ordinal d'`EntityPool` pres (8 / 0 / 6),
et `IdunBattle.Entities.Enum.EntityPool` est LU dans `data/symbols/<build>/frida/enums.tsv` :
`0=AliveUnits,1=DefeatedUnits,3=PlayingEffects,4=EffectsToSimulate,5=Tiles,6=AliveMachines,
7=MachinePlatforms,8=AllUnits,9=DestroyedMachines`. Le pendant `BattleQuery$$GetAllDeadUnits`
(slot 139) lit le pool `1=DefeatedUnits` PUIS filtre par `IdunBattle.Entities.UnitExtensions$$IsDead`
-- c'est la seule des quatre qui porte un predicat dans son corps.

IDENTITE DU CHAMP `+0x20` -- deux etablissements INDEPENDANTS, aucun n'est un nom lu :
  (a) ELIMINATION structurelle. `DSLSelectors$$InitializeShared` alloue a `+0x20` une classe dont
      le ctor est le corps TRIVIAL a 4 arguments `(this, state, battleQuery, 0)` -- exactement
      celui de `AllUnitsSelector` et d'`AllAliveMachinesSelector`, dont les globales de classe sont
      DIFFERENTES de celle de `+0x20` (une globale de classe n'a qu'UN site d'allocation : verifie
      par `list_xrefs`). Les `AllDead*`/`AllDefeated*` passent, eux, par
      `IdunBattle.Entities.Selectors.AllDefeatedUnitsSelector$$.ctor` (3 arguments, corps distinct).
      Ne reste, dans `frida/classes.tsv`, qu'une seule classe de cette famille sans fabrique :
      `IdunBattle.Entities.Selectors.AllAliveUnitsSelector`.
  (b) MESURE LIVE ANTERIEURE. `IdunBattleLogic.Entities.Abilities.Active.Loki.GetEmRuntzAbility$$GetSpawnTileSelector`
      -- le call-site du fix #202 -- ecrit `Enemies(dsl+0x48 = Caster, dsl+0x20, 3)` et le confront
      live avait etabli que les MORTS en sont EXCLUS alors qu'aucun `Damageable` n'y figure. Le
      filtre de vie est donc DANS `+0x20`.

CE QUE CA CHANGE POUR LE PORT
-----------------------------
Le port n'avait qu'UN noeud, `AllUnits`, qui FILTRE les mortes. Ce n'est pas le mirror de
`DSLSelectors$$AllUnits` -- c'est celui du champ partage `+0x20` = `AllAliveUnits`. Le vrai
`AllUnits` (pool 8, MORTS INCLUS) n'existait PAS cote port : c'est pour ca que #508 a du resoudre
`LeadingTheChargeAbility$$GetExtraPierceRatio` par un helper imperatif LOCAL.

Ce probe MESURE le rayon de souffle des deux cotes et sert de CLIQUET :

  etape 1 (OFFLINE) -- inventaire PORT par AST : tout site EXECUTABLE qui construit `AllUnits(...)`
      ou `AllAliveUnits(...)` sous `scripts/python/**` (l'AST ignore docstrings et commentaires,
      la ou un grep comptait 5x trop).
  etape 2 (OFFLINE) -- WALKER sur les arbres REELLEMENT construits : il visite `__slots__` ET
      `__dict__` (un walker qui ne suivait que `__slots__` rendait « 0 » pour la mauvaise raison),
      puis EVALUE chaque arbre DEUX fois -- avec et sans filtre de vie -- sur un contexte qui
      porte un CADAVRE. Un site dont la sortie ne bouge pas est un site ou la divergence est
      INOBSERVABLE, et c'est un resultat, pas un echec.
  etape 3 (OFFLINE) -- CLIQUET d'attribution : chaque site executable de `AllUnits(` doit etre
      DECLARE dans `SITES_POOL8` avec le symbole natif qui le justifie. Un site non declare
      rougit -- c'est la seule chose qui empeche un futur port d'ecrire `AllUnits()` par habitude
      la ou le natif passe `+0x20`.
  etape 4 (OFFLINE) -- CLIQUET de semantique : `AllUnits` ne filtre PAS, `AllAliveUnits` filtre.

RE-DERIVER LES ENTREES (ne jamais citer ce fichier comme source) :
  * cote NATIF -- `mcp__ghidra__list_xrefs("IdunBattleLogic.Entities.DSLSelectors$$AllUnits")`
    (24 call-sites d'appel + 4 refs de table le 2026-08-07) ; puis decompiler chaque call-site et
    lire QUEL selecteur il passe (`DSLSelectors$$AllUnits(...)` vs `<dsl>+0x20`).
  * cote PORT -- ce probe, etape 1.

Usage :  python scripts/python/probe_514_allunits_rayon_de_souffle.py
"""
from __future__ import annotations

import ast
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

_RACINE = _HERE                      # scripts/python
_PORTEE = ("engine", "tests", ".")   # sous-arbres balayes (`.` = les probes a la racine)


# --------------------------------------------------------------------------------------------- #
# La TABLE D'ATTRIBUTION : pour chaque site executable qui a le droit d'ecrire `AllUnits(`, le
# symbole natif MESURE qui le justifie (le call-site appelle `DSLSelectors$$AllUnits`, pool 8).
# Tout autre site doit ecrire `AllAliveUnits(` (= le champ partage `DSLSelectors+0x20`).
# --------------------------------------------------------------------------------------------- #
SITES_POOL8 = {
    ("engine/runner/abilities/orks.py", "waaagh_attack_tree"):
        "IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetAttackBehaviour",
    ("engine/runner/abilities/loki/leading_the_charge.py", "leading_the_charge_defeated_friends_selector"):
        "IdunBattleLogic.Entities.Abilities.Active.Loki.LeadingTheChargeAbility$$GetExtraPierceRatio",
    # #1002 : la RELIQUE du meme heros (`astraDreir`) construit le MEME filtre pool-8 que son
    # active -- meme predicat `HasBeenDefeated`, donc meme exigence de source MORTS INCLUS.
    ("engine/runner/operations/triggers/loki/sabre_of_sacrifice.py",
     "sabre_of_sacrifice_defeated_friends_selector"):
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki.SabreOfSacrificeAbility$$GetCurrentExtraArmor",
    # #1084 -- les DEUX actives du boss `admecBossBelisarius`. LU sur `t6dpr4k06g` : chacune ecrit
    # un appel EXPLICITE a `IdunBattleLogic.Entities.DSLSelectors$$AllUnits(<dsl>)`, pas le champ
    # partage `<dsl>+0x20`. Ce sont des sources d'un `Friends(Caster, .., 3)` : le pool 8 y fait
    # entrer les cadavres allies, que le `MechanicalUnits`/`EntitiesWithAnyEffect` d'apres ne
    # retire pas.
    ("engine/runner/abilities/admec.py", "solar_atomizer_tree"):
        "IdunBattleLogic.Entities.Abilities.Active.SolarAtomizerAbility$$ExecuteBehaviour",
    ("engine/runner/abilities/admec.py", "invocation_of_machine_vengeance_tree"):
        "IdunBattleLogic.Entities.Abilities.Active.InvocationOfMachineVengeanceAbility$$ExecuteBehaviour",
    # #1083 -- la cascade de tuiles de spawn des power-ups. LU : `AllUnits(pvVar4)` explicite, puis
    # `Enemies(of = Actor@<dsl>+0x40, entities = <ce pool>, selectionType = 3)`. Le site avait DEJA
    # son symbole dans `CALL_SITES_NATIFS_POOL8` sans etre declare ici -- l'ecart exact que
    # l'etape 3 existe pour voir.
    ("engine/runner/operations/triggers/loki/power_up_spawn.py", "spawn_tile_tree"):
        "IdunBattleLogic.Entities.Abilities.Triggered.Loki.APowerup_SpawnAbility$$GetSpawnTile",
    # Le probe et sa GARDE se testent EUX-MEMES sur les deux primitives : ce ne sont pas des
    # mirrors de call-sites natifs, mais les crans qui figent la semantique.
    ("probe_514_allunits_rayon_de_souffle.py", "etape_4"): "<auto-test de l'etape 4>",
    ("tests/engine/runner/test_514_allunits_pool8_offline.py",
     "test_allunits_est_le_pool_8_et_ne_filtre_pas_les_mortes"): "<garde de semantique>",
    ("tests/engine/runner/test_514_allunits_pool8_offline.py",
     "test_les_deux_primitives_divergent_des_qu_il_y_a_UN_cadavre"): "<garde anti-degenere>",
}

#: Call-sites NATIFS de `DSLSelectors$$AllUnits` (pool 8) -- releve `list_xrefs` du 2026-08-07 sur
#: le build `rnca9r7q6c`, **RE-DERIVE le 2026-08-18 sur `t6dpr4k06g` : 24 appels, IDENTIQUES**
#: (28 xrefs dont 4 `DATA`). Sert a l'etape 3 pour dire ce qui reste NON PORTE (donc hors rayon),
#: et depuis #1084 de REFERENTIEL au cran 3b : un symbole d'attribution qui n'est pas ici est soit
#: faux, soit le signe que ce releve est perime.
CALL_SITES_NATIFS_POOL8 = (
    "IdunBattleLogic.Entities.Abilities.Triggered.Loki.ATemptingTrapAbility$$CreateBehaviour",
    "IdunBattleLogic.Entities.Abilities.Active.Loki.ShroudPsalmAbility$$ExecuteBehaviour",
    "IdunBattle.Entities.Effects.Loki.BlessingsOfKhorne_ModifiersEffect$$GetMultiplierBasedOnDefeatedInMelee",
    "IdunBattleLogic.Entities.Abilities.Active.Loki.DevastatingRefrain_AttackAbility$$CreateBehaviour",
    "IdunBattleLogic.Entities.Abilities.Active.Loki.TheQuickeningAbility$$ExecuteBehaviour",
    "IdunBattleLogic.Entities.Abilities.Active.Loki.WaaaghAbility$$GetAttackBehaviour",
    "IdunBattleLogic.Entities.Abilities.Triggered.Loki.EnhancementSummonAbility$$CreateBehaviour",
    "IdunBattleLogic.Entities.Abilities.Triggered.Loki.EnvFactionSummonsAbility$$CreateBehaviour",
    "IdunBattleLogic.Entities.Abilities.Triggered.Loki.FieldsOfFire_AttackedAbility$$GetInstantBehaviour",
    "IdunBattle.Entities.Effects.Loki.BlightedLandEffect$$CreateTargetSelector",
    "IdunBattle.Entities.Effects.Loki.ContemptuousDisregard_DamageReductionEffect$$CreateTargetSelector",
    "IdunBattle.Entities.Effects.Loki.GuardianConstruct_ExtraDamagePctEffect$$CreateTargetSelector",
    "IdunBattle.Entities.Effects.Loki.Test_MachineAdditionModifierForUnitsEffect$$CreateTargetSelector",
    "IdunBattleLogic.Entities.Abilities.Triggered.Loki.HeavyRailRifle_AttackAbility$$CreateBehaviour",
    "IdunBattleLogic.Entities.Abilities.Triggered.Loki.IllusionsOfTzeentchAbility$$CreateBehaviour",
    "IdunBattleLogic.Entities.Abilities.Triggered.Loki.APowerup_SpawnAbility$$GetSpawnTile",
    "IdunBattleLogic.Entities.Abilities.Triggered.Loki.PreCalibratedPurgeSolutionAbility$$CreateBehaviour",
    "IdunBattleLogic.Entities.Abilities.Triggered.Loki.SabreOfSacrificeAbility$$GetCurrentExtraArmor",
    "IdunBattleLogic.Entities.Abilities.Triggered.Loki.SabreOfSacrificeAbility$$GetNumDefeatedFriendlyUnits",
    "IdunBattleLogic.Entities.Abilities.Active.InvocationOfMachineVengeanceAbility$$ExecuteBehaviour",
    "IdunBattleLogic.Entities.Abilities.Active.SolarAtomizerAbility$$ExecuteBehaviour",
    "IdunBattleLogic.Entities.Abilities.Triggered.Loki.WeaverOfFateAbility$$CreateTrigger",
    "IdunBattleLogic.Entities.Abilities.Triggered.Loki.WeaverOfFateAbility$$GetTrigger",
    "IdunBattleLogic.Entities.Abilities.Active.Loki.LeadingTheChargeAbility$$GetExtraPierceRatio",
)


# --------------------------------------------------------------------------------- etape 1 (AST)

def _fichiers_python():
    for sous in _PORTEE:
        base = os.path.join(_RACINE, sous)
        if not os.path.isdir(base):
            continue
        if sous == ".":
            for nom in sorted(os.listdir(base)):
                if nom.endswith(".py"):
                    yield os.path.join(base, nom)
            continue
        for dossier, _sd, fichiers in os.walk(base):
            for nom in sorted(fichiers):
                if nom.endswith(".py"):
                    yield os.path.join(dossier, nom)


def _rel(chemin: str) -> str:
    return os.path.relpath(chemin, _RACINE).replace("\\", "/")


def _porteur(arbre, noeud):
    """Nom de la fonction/classe ENGLOBANTE d'un noeud (le SITE, pas le fichier)."""
    meilleur = None
    for p in ast.walk(arbre):
        if not isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        fin = getattr(p, "end_lineno", None) or p.lineno
        if p.lineno <= noeud.lineno <= fin:
            if meilleur is None or p.lineno > meilleur.lineno:
                meilleur = p
    return meilleur.name if meilleur is not None else "<module>"


#: MEMO DE RESULTAT (#941). Le balayage lit et `ast.parse` tout `_PORTEE`, et `_porteur` refait
#: un `ast.walk` COMPLET par site trouve. Mesure du 2026-08-11 : les DEUX tests du cliquet qui
#: l'appellent coutaient 63,3 s et 59,6 s -- pour le MEME inventaire. Ce qui est retenu est
#: minuscule (deux listes de triplets) ; jamais un AST.
_ETAPE1_CACHE: tuple | None = None


def _balayer_etape_1() -> tuple:
    """LE BALAYAGE. Rend `(trouve, messages_d_echec)` -- separe pour etre SUBSTITUABLE."""
    trouve: dict = {"AllUnits": [], "AllAliveUnits": []}
    echecs: list = []
    for chemin in _fichiers_python():
        try:
            with open(chemin, "r", encoding="utf-8") as fh:
                arbre = ast.parse(fh.read(), filename=chemin)
        except (SyntaxError, UnicodeDecodeError) as exc:
            echecs.append("etape 1 : %s illisible (%s)" % (_rel(chemin), exc))
            continue
        for noeud in ast.walk(arbre):
            if not isinstance(noeud, ast.Call):
                continue
            f = noeud.func
            nom = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else None)
            if nom in trouve:
                trouve[nom].append((_rel(chemin), _porteur(arbre, noeud), noeud.lineno))
    return {k: tuple(v) for k, v in trouve.items()}, tuple(echecs)


def etape_1(fails: list) -> dict:
    """Inventaire AST des sites EXECUTABLES. Rend {nom_noeud: [(fichier, porteur, ligne), ...]}.

    MEMOISE (#941). Le RAPPORT et les echecs sont rejoues a chaque appel : seul le BALAYAGE est
    evite. Le retour est RE-CONSTRUIT (listes neuves) -- un appelant qui le muterait ne peut pas
    changer ce que verra le suivant."""
    global _ETAPE1_CACHE
    print("=== etape 1 -- inventaire PORT (AST : docstrings et commentaires EXCLUS) ===")
    if _ETAPE1_CACHE is None:
        _ETAPE1_CACHE = _balayer_etape_1()
    fige, echecs = _ETAPE1_CACHE
    fails.extend(echecs)
    trouve = {k: list(v) for k, v in fige.items()}
    for nom in ("AllUnits", "AllAliveUnits"):
        print("  %-14s : %d site(s) executable(s)" % (nom, len(trouve[nom])))
        for (fic, port, lig) in trouve[nom]:
            print("      %s:%d  (%s)" % (fic, lig, port))
    return trouve


# ----------------------------------------------------------------------------- etape 2 (WALKER)

#: Constructeurs d'arbre SANS argument obligatoire -- ils couvrent les sites executables et
#: permettent de MESURER le consommateur reel, pas de le supposer.
BUILDERS = (
    ("engine.runner.abilities.orks", "waaagh_buffed_units_selector", ()),
    ("engine.runner.abilities.orks", "waaagh_attack_tree", ()),
    ("engine.runner.abilities.tau", "twin_smart_missile_system_attack_targets", ()),
    ("engine.runner.abilities.thousandsons", "hellfyre_extra_targets_selector", ()),
    ("engine.runner.abilities.admec", "rad_bombardment_affected_tile_amount", ()),
    ("engine.runner.abilities.loki.stormcaller", "stormcaller_tree", ()),
    ("engine.runner.abilities.aeldari", "silent_death_tree", (1,)),
    ("engine.entities.selectors.composites", "get_spawn_tile_selector", ()),
    ("engine.runner.abilities.loki.leading_the_charge",
     "leading_the_charge_defeated_friends_selector", ()),
)


def _marcher(racine, vus=None):
    """Parcours de l'objet-arbre : `__slots__` ET `__dict__`, plus listes/tuples/dicts.

    ⚠ Un walker qui ne suit QUE `__slots__` rend « 0 noeud » sur les classes du port qui n'en
    declarent pas (la majorite des selecteurs) -- un zero pour la mauvaise raison."""
    if vus is None:
        vus = set()
    if id(racine) in vus:
        return
    vus.add(id(racine))
    yield racine
    if isinstance(racine, (str, bytes, int, float, bool)) or racine is None:
        return
    if isinstance(racine, dict):
        for v in list(racine.values()):
            for x in _marcher(v, vus):
                yield x
        return
    if isinstance(racine, (list, tuple, set, frozenset)):
        for v in list(racine):
            for x in _marcher(v, vus):
                yield x
        return
    enfants = []
    for cls in type(racine).__mro__:
        for nom in getattr(cls, "__slots__", ()) or ():
            if hasattr(racine, nom):
                enfants.append(getattr(racine, nom))
    enfants.extend((getattr(racine, "__dict__", None) or {}).values())
    for v in enfants:
        for x in _marcher(v, vus):
            yield x


def _plateau_jouet(cols: int = 8, rows: int = 8):
    """Board PLAT au format `boardGraph` -- sans lui, tout le domaine TUILE degrade en no-op et la
    mesure differentielle rendrait « inobservable » pour la mauvaise raison."""
    import hexgeo
    from engine.entities.pathfinding.board import Board

    def _tid(c, r):
        return c * rows + r + 1

    tuiles = []
    for col in range(cols):
        for row in range(rows):
            nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < cols and 0 <= r < rows]
            tuiles.append({"id": _tid(col, row), "col": col, "row": row, "elevation": 0,
                           "walkable": True, "isWall": False, "neighbours": nb})
    return Board(tuiles, adjacency="evenq")


def _ctx_avec_cadavre():
    """Contexte a CADAVRES. Un montage ou personne n'est mort ne distingue PAS un selecteur qui
    filtre les morts d'un qui ne les filtre pas -- accord en regime DEGENERE."""
    from engine.dsl.base import DslContext
    vivant_ami = {"id": 1, "team": 1, "player": 1, "alive": True, "hp": 100,
                  "pos": {"col": 3, "row": 3}, "visualId": "ami", "_traits": set()}
    mort_ami = {"id": 2, "team": 1, "player": 1, "alive": False, "hp": 0,
                "pos": {"col": 3, "row": 4}, "visualId": "cadavre_ami", "_traits": set()}
    vivant_ennemi = {"id": 3, "team": 2, "player": 2, "alive": True, "hp": 100,
                     "pos": {"col": 4, "row": 3}, "visualId": "ennemi", "_traits": set()}
    mort_ennemi = {"id": 4, "team": 2, "player": 2, "alive": False, "hp": 0,
                   "pos": {"col": 4, "row": 4}, "visualId": "cadavre_ennemi", "_traits": set()}
    unites = [vivant_ami, mort_ami, vivant_ennemi, mort_ennemi]
    return DslContext(units=unites, caster=vivant_ami, target=vivant_ennemi,
                      board=_plateau_jouet(),
                      has_trait=lambda u, t: False, has_unit_flag=lambda u, f: False,
                      faction_of=lambda u: None)


def _ids(sortie):
    if isinstance(sortie, list):
        return [u.get("id") if isinstance(u, dict) else u for u in sortie]
    if isinstance(sortie, dict):
        return [sortie.get("id")]
    return sortie


def _parents(racine) -> dict:
    """{id(enfant): parent} sur le MEME parcours que `_marcher` (`__slots__` ET `__dict__`)."""
    liens: dict = {}
    vus = set()
    pile = [racine]
    while pile:
        n = pile.pop()
        if id(n) in vus:
            continue
        vus.add(id(n))
        enfants = []
        if isinstance(n, dict):
            enfants = list(n.values())
        elif isinstance(n, (list, tuple, set, frozenset)):
            enfants = list(n)
        elif not isinstance(n, (str, bytes, int, float, bool)) and n is not None:
            for cls in type(n).__mro__:
                for nom in getattr(cls, "__slots__", ()) or ():
                    if hasattr(n, nom):
                        enfants.append(getattr(n, nom))
            enfants.extend((getattr(n, "__dict__", None) or {}).values())
        for e in enfants:
            liens.setdefault(id(e), n)
            pile.append(e)
    return liens


def _consommateur_direct(leaf, racine, liens, objets):
    """Le PLUS PROCHE ancetre de type selecteur -- le consommateur IMMEDIAT de la feuille. C'est lui
    qui dit si un cadavre TRAVERSE le noeud, independamment de ce que les etages du dessus filtrent."""
    from engine.dsl.base import TargetsSelector
    cur = liens.get(id(leaf))
    while cur is not None:
        o = objets.get(id(cur), cur)
        if isinstance(o, TargetsSelector):
            return o
        cur = liens.get(id(cur))
    return None


def _filtre_alive(self, ctx):
    """La semantique pool-0 (`GetAllAliveUnits`) -- sert de CONTREFACTUEL sur `AllUnits`."""
    return [u for u in ctx.units if bool(u.get("alive", True)) and (u.get("hp") or 0) > 0]


def _sans_filtre(self, ctx):
    """La semantique pool-8 (`GetAllUnits`) -- sert de CONTREFACTUEL sur `AllAliveUnits`."""
    return list(ctx.units)


def _sortie_sous_patch(selecteur, ctx, classe, remplacant):
    original = classe.select
    try:
        classe.select = remplacant
        return _ids(selecteur.evaluate(ctx))
    except Exception as exc:                                       # noqa: BLE001
        return "<%s>" % type(exc).__name__
    finally:
        classe.select = original


def etape_2(fails: list) -> None:
    """Walker + evaluation DIFFERENTIELLE (avec / sans filtre de vie) sur un plateau a CADAVRES."""
    print("")
    print("=== etape 2 -- WALKER sur les arbres construits + evaluation differentielle ===")
    from engine.entities.selectors import tiles as _tiles
    from engine.dsl.base import TargetsSelector

    noms_cibles = {"AllUnits", "AllAliveUnits"}
    ctx = _ctx_avec_cadavre()

    for (module, fonction, args) in BUILDERS:
        try:
            mod = __import__(module, fromlist=["_"])
            builder = getattr(mod, fonction)
        except (ImportError, AttributeError) as exc:
            fails.append("etape 2 : %s.%s introuvable (%s)" % (module, fonction, exc))
            continue
        try:
            arbre = builder(*args)
        except Exception as exc:                                   # noqa: BLE001 - on MESURE
            fails.append("etape 2 : %s.%s a leve %s: %s" % (module, fonction, type(exc).__name__, exc))
            continue

        feuilles = [n for n in _marcher(arbre) if type(n).__name__ in noms_cibles]
        libelle = "%s.%s" % (module.split(".")[-1], fonction)
        if not feuilles:
            print("  %-52s : aucune feuille d'ensemble" % libelle)
            continue
        compte = {}
        for f in feuilles:
            compte[type(f).__name__] = compte.get(type(f).__name__, 0) + 1
        detail = ", ".join("%s x%d" % (k, v) for k, v in sorted(compte.items()))
        print("  %-52s : %s" % (libelle, detail))

        # SOUS-ARBRES MAXIMAUX de type selecteur qui contiennent une feuille d'ensemble : c'est
        # eux qu'on evalue, pas la racine -- une racine BEHAVIOUR (KillDeadUnits, AddEffect...)
        # n'a pas de sortie comparable, alors que son `units_sel` en a une.
        cands = [n for n in _marcher(arbre)
                 if isinstance(n, TargetsSelector)
                 and any(type(x).__name__ in noms_cibles for x in _marcher(n))]
        maximaux = [s for s in cands
                    if not any(t is not s and any(y is s for y in _marcher(t)) for t in cands)]

        # CONSOMMATEUR IMMEDIAT de chaque feuille : le seul etage dont on puisse dire, sans
        # supposition, si un cadavre le TRAVERSE. Les etages du dessus peuvent le ravaler.
        liens = _parents(arbre)
        objets = {id(n): n for n in _marcher(arbre)}
        directs = []
        for f in feuilles:
            d = _consommateur_direct(f, arbre, liens, objets)
            if d is not None and not any(d is x for x in directs):
                directs.append(d)

        for sel in directs + [m for m in maximaux if not any(m is d for d in directs)]:
            nom_sel = type(sel).__name__
            try:
                courant = _ids(sel.evaluate(ctx))
            except Exception as exc:                               # noqa: BLE001
                print("      %-24s [eval impossible hors state : %s]" % (nom_sel, type(exc).__name__))
                continue
            # CONTREFACTUEL : `AllUnits` FILTRERAIT les mortes -- c'est-a-dire l'etat du port
            # AVANT #514, quand il n'existait qu'un seul noeud. Une sortie qui bouge = le cout
            # MESURE de la confusion sur ce site.
            cf_a = _sortie_sous_patch(sel, ctx, _tiles.AllUnits, _filtre_alive)
            # CONTREFACTUEL SYMETRIQUE : `AllAliveUnits` NE filtrerait PAS (= si on avait
            # « repare » le foyer partage au lieu de le scinder).
            cf_b = _sortie_sous_patch(sel, ctx, _tiles.AllAliveUnits, _sans_filtre)
            print("      %-24s courant=%r | si AllUnits filtrait=%r %s | si AllAliveUnits ne "
                  "filtrait pas=%r %s"
                  % (nom_sel, courant,
                     cf_a, "SENSIBLE" if cf_a != courant else "-",
                     cf_b, "SENSIBLE" if cf_b != courant else "-"))


# ----------------------------------------------------------------------------- etape 3 (CLIQUET)

def etape_3(fails: list, trouve: dict) -> None:
    print("")
    print("=== etape 3 -- CLIQUET d'attribution : tout `AllUnits(` doit citer son natif pool-8 ===")
    print("  call-sites NATIFS pool 8 releves : %d" % len(CALL_SITES_NATIFS_POOL8))
    for (fic, porteur, lig) in trouve["AllUnits"]:
        cle = (fic, porteur)
        symbole = SITES_POOL8.get(cle)
        if symbole is None:
            fails.append(
                "etape 3 : %s:%d (%s) ecrit `AllUnits(` sans declaration. `AllUnits` = "
                "`DSLSelectors$$AllUnits` = pool 8 = MORTS INCLUS. Si le natif de ce site passe le "
                "champ partage `<dsl>+0x20`, ecrire `AllAliveUnits(` ; sinon, declarer le site dans "
                "SITES_POOL8 avec le symbole natif LU au decompile." % (fic, lig, porteur))
            continue
        print("  OK  %s:%d (%s)" % (fic, lig, porteur))
        print("        <- %s" % symbole)
    declares = set(SITES_POOL8)
    vus = {(f, p) for (f, p, _l) in trouve["AllUnits"]}
    for cle in sorted(declares - vus):
        fails.append("etape 3 : SITES_POOL8 declare %s/%s qui n'ecrit plus `AllUnits(` -- "
                     "declaration PERIMEE, la retirer." % cle)
    # CRAN 3b (#1084) -- L'ATTRIBUTION N'EST PAS UNE PROSE LIBRE : le symbole cite doit appartenir
    # au RELEVE des call-sites natifs pool-8. Sans lui, un site pouvait etre declare par un symbole
    # PLAUSIBLE mais qui n'appelle pas `DSLSelectors$$AllUnits` -- et le cliquet redevenait vert
    # sur une justification INVENTEE, ce qui est pire que l'absence de declaration. Les entrees
    # `<...>` sont les auto-tests du cliquet : elles ne mirrorent aucun call-site natif et le
    # DISENT par leur forme, au lieu d'etre exemptees par une liste a part.
    hors_releve = sorted(
        (cle, sym) for cle, sym in SITES_POOL8.items()
        if not (sym.startswith("<") and sym.endswith(">")) and sym not in CALL_SITES_NATIFS_POOL8)
    for cle, sym in hors_releve:
        fails.append(
            "etape 3b : %s/%s est declare par `%s`, qui n'est PAS dans le releve `list_xrefs` de "
            "`IdunBattleLogic.Entities.DSLSelectors$$AllUnits`. Soit le symbole est faux, soit le "
            "releve est perime (le re-derive : `mcp__ghidra__list_xrefs`)." % (cle[0], cle[1], sym))
    if not hors_releve:
        print("  OK  les %d attributions non auto-test citent un call-site du releve natif (%d)"
              % (sum(1 for s in SITES_POOL8.values() if not s.startswith("<")),
                 len(CALL_SITES_NATIFS_POOL8)))


# ----------------------------------------------------------------------------- etape 4 (CLIQUET)

def etape_4(fails: list) -> None:
    print("")
    print("=== etape 4 -- CLIQUET de semantique : pool 8 != pool 0 ===")
    try:
        from engine.entities.selectors.tiles import AllAliveUnits, AllUnits
    except ImportError as exc:
        fails.append("etape 4 : les DEUX primitives doivent exister -- `AllUnits` (pool 8, "
                     "`DSLSelectors$$AllUnits`) et `AllAliveUnits` (pool 0, le champ partage "
                     "`DSLSelectors+0x20`). Import impossible : %s" % exc)
        return

    ctx = _ctx_avec_cadavre()
    tous = _ids(AllUnits().select(ctx))
    vivants = _ids(AllAliveUnits().select(ctx))
    print("  AllUnits()      (EntityPool.AllUnits = 8)    -> %r" % tous)
    print("  AllAliveUnits() (EntityPool.AliveUnits = 0)  -> %r" % vivants)
    if sorted(tous) != [1, 2, 3, 4]:
        fails.append("etape 4 : `AllUnits` doit rendre TOUTES les unites (morts inclus) -- "
                     "`BattleQuery$$GetAllUnits` n'a aucun filtre de vie dans son corps. Rendu %r"
                     % tous)
    if sorted(vivants) != [1, 3]:
        fails.append("etape 4 : `AllAliveUnits` doit rendre les seules VIVANTES (pool 0). "
                     "Rendu %r" % vivants)


# ------------------------------------------------------------------------------------------ main

def main() -> int:
    fails: list = []
    trouve = etape_1(fails)
    etape_2(fails)
    etape_3(fails, trouve)
    etape_4(fails)
    print("")
    if fails:
        print("ECHECS (%d) :" % len(fails))
        for f in fails:
            print("  - %s" % f)
        return 1
    print("OK -- rayon de souffle mesure, attribution declaree, semantique sous cliquet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
