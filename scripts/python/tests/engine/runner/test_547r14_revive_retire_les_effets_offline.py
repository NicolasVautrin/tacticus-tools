"""#547-r14 -- LE REVIVE RETIRE LES EFFETS DU RESSUSCITE, SAUF CEUX A `KeepOnRevive`.

## L'ecart que ce fichier ferme

`IdunBattle.Operations.ReviveUnitOperation$$Execute` appelle le slot 0x5a (`RemoveEffects`)
**INLINE**, entre `IdunBattle.Operations.ReviveUnitOperation$$SetHealth` et l'enregistrement
`HasBeenRevivedByAbility`, avec des options lues aux deux ecritures qui precedent l'appel :

    local_438  = 0                       -> `Nullable<KillUnitStep> step` SANS valeur
    lStack_430 = CONCAT44(_, 1)          -> `options.<+0x08>` = 1   <- LE GATE

`revive.py::ReviveUnitOperation.execute` n'en retirait AUCUN.

## Pourquoi ce n'est PAS le meme fait que #547-r13, et pourquoi les deux doivent coexister

`#547-r13` a etabli que sur le chemin de MORT le gate vaut **0**, donc que `IEffect` slot 2
`get_KeepOnRevive` n'y est **jamais lu** -- et son cliquet garde exactement cela. Ce fichier-ci
garde la face OPPOSEE du meme `if` : le SEUL producteur du binaire qui arme le gate. Les deux
assertions sont contradictoires si on se trompe de chemin, et c'est precisement la confusion qui a
coute `#547-r13` -- d'ou l'etage 2 ci-dessous, qui reprend la face MORT avec la nouvelle API.

## Le point le plus facile a mal lire

Le DEFAUT de `IdunBattle.Entities.Effects.BaseEffect` est **True** (`b0 01 c3`), donc ce retrait
n'est PAS un retrait de masse : la quasi-totalite des effets SURVIT au revive. Il ne mord que sur
les classes qui renversent le getter a `False` -- TROIS dans le binaire, dont DEUX portees
(`PrecisionShot_AimEffect`, `RitesOfMorkaiExtraDamageEffect`). Un test qui se contenterait de
verifier << la liste est vide apres le revive >> serait donc FAUX, pas seulement faible.

Les etages 1 a 4 et 6 ne dependent PAS du jeu installe ; seul le 5 skippe sans le build. Ce fichier
ne peut donc jamais rendre `passed == 0 and skipped > 0` (le regime que #455 fait rougir).

ASCII only (console cp1252).
"""
from __future__ import annotations

import importlib
import pkgutil
import sys
from pathlib import Path

import pytest

PYDIR = Path(__file__).resolve().parents[3]
if str(PYDIR) not in sys.path:
    sys.path.insert(0, str(PYDIR))

from engine.entities.effects.base import BaseEffect                        # noqa: E402
from engine.entities.effects_state import EffectsState                     # noqa: E402
from engine.entities.kill_unit_step import KillUnitStep                    # noqa: E402
import engine.runner.operations.remove_effects as REM                      # noqa: E402
import engine.runner.operations.revive as REV                              # noqa: E402

#: Ce qui doit changer pour que ce FICHIER de test puisse changer de verdict (#486-r15).
DECLENCHEUR = {
    "chemins": (
        # LE SOCLE DE LA DERIVATION (etage 5), qu'aucun import de production n'amene :
        "scripts/python/build_pin.py",
        "scripts/python/il2cpp_metadata.py",
        "scripts/python/probe_175r2_can_be_immune_to.py",
        "scripts/python/probe_547r13_keep_on_revive.py",
        "scripts/python/verdict_cache.py",
        # L'ENTREE VERSIONNEE : elle change au changement de JEU, sans qu'aucun fichier de code ne
        # bouge -- donc AUCUNE cascade d'imports ne la revele.
        "data/symbols/*/metadata/keep_on_revive.tsv",
    ),
    # DERIVE : l'etage 5 lit `data/symbols/**` du build courant.
    "build": True,
    "toujours": False,
    "raison": ("le deriveur du getter et son socle, plus l'entree versionnee -- seule source de "
               "verdict qui bouge sans qu'aucun code ne bouge. Les foyers reellement gardes "
               "(`revive.py`, `remove_effects.py`, `effects/base.py` et les deux mirrors qui "
               "surchargent) sont deja dans la cascade DERIVEE par les imports."),
}

COLS, ROWS, PORTEUR = 5, 5, 20

#: `effect_type` arbitraires, hors de tout domaine porte : ces temoins ne doivent RIEN declencher.
ET_GARDE, ET_FRAGILE, ET_MUET = 4342, 4343, 4344


def _state_reel():
    """Un `State` COMPLET : `remove_effects_operation` ne collecte pas, elle RETIRE (revert des
    modifications, deux events), donc elle a besoin des canaux de `State`."""
    import hexgeo                     # module de `scripts/python`, pas du paquet `engine`
    from engine.entities.pathfinding.board import Board
    from engine.runner.snapshot import load_state
    tiles = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [c * ROWS + r + 1 for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            tiles.append({"id": col * ROWS + row + 1, "col": col, "row": row, "elevation": 0,
                          "walkable": True, "isWall": False, "neighbours": nb})
    decision = {"currentPlayer": 1, "units": [
        {"id": PORTEUR, "visualId": "necroWarden", "alive": True, "team": 2, "owner": 2,
         "pos": {"col": 2, "row": 2}, "effects": []}]}
    observe = {"units": [{"squadId": PORTEUR, "hp": 1000, "hpMax": 1000}]}
    st = load_state(decision, observe, board=Board(tiles, adjacency="evenq"))
    if st.effects is None:
        st.effects = EffectsState()
    return st


def _restants(st) -> list:
    return sorted(int(e.effect_type) for e in st.effects.by_unit.get(PORTEUR, [])
                  if not e.consumed)


def _poser(st, effect_type: int, keep: "bool | None"):
    """Pose un effet temoin. `keep is None` => l'attribut n'est PAS declare sur l'instance (regime
    du `getattr(..., True)` de secours), ce qui est le point de l'etage 3."""
    e = BaseEffect(name="temoin_%d" % effect_type, effect_type=effect_type, target=PORTEUR)
    if keep is not None:
        e.keep_on_revive = keep
    st.effects.add_effect(PORTEUR, e)
    return e


def _mourant(st):
    """Met le porteur dans l'etat ou `ReviveUnitOperation$$Execute` le trouve : PV a 0, non vivant,
    une `ReviveData` en attente sur le `UnitComponent` (posee par `ReviveBehaviour$$Execute`)."""
    from engine.runner.components import HealthComponent, UnitComponent
    e = st.get_entity(PORTEUR)
    e.get_component(HealthComponent).hp = 0
    e.get_component(UnitComponent).alive = False
    REV.post_pending_revive(st, PORTEUR, 600)
    return e


# ------------------------------------------------- etage 1 : LE RETRAIT EXISTE, ET IL DISCRIMINE

def test_le_revive_retire_les_KeepOnRevive_False_et_GARDE_les_True():
    """TEMOIN NON DEGENERE, et c'est ce qui fait la valeur de cet etage : on pose DEUX effets sur le
    ressuscite, l'un `keep_on_revive = True`, l'autre `False`. Le natif garde le premier et retire
    le second.

    Un test qui n'exigerait que << le False part >> passerait aussi sur un port qui retire TOUT ;
    un test qui n'exigerait que << le True reste >> passerait sur le port d'AVANT le correctif, qui
    ne retirait rien. Il faut les deux dans le MEME etat pour que l'assertion discrimine."""
    st = _state_reel()
    garde = _poser(st, ET_GARDE, keep=True)
    fragile = _poser(st, ET_FRAGILE, keep=False)
    _mourant(st)
    assert _restants(st) == sorted([ET_GARDE, ET_FRAGILE])

    out = REV.ReviveUnitOperation.execute(st, PORTEUR)

    assert out is not None and out.get("revived") == PORTEUR, out
    assert _restants(st) == [ET_GARDE], (
        "apres le revive il doit rester EXACTEMENT l'effet a `KeepOnRevive = True` : %s"
        % _restants(st))
    assert not garde.consumed, "l'effet a `KeepOnRevive = True` a ete retire par le revive"
    assert fragile.consumed, "l'effet a `KeepOnRevive = False` a SURVECU au revive"


def test_le_retrait_passe_par_le_FOYER_et_non_par_une_marque():
    """`RemoveEffectsOperation$$Execute` appelle le slot 0x11 (`RemoveEffectOperation$$Execute`)
    pour chaque candidat -- il ne pose pas un drapeau. Le port doit donc passer par
    `remove_effect_instance`, seul endroit qui reverte les modifications et publie
    `On(0x3f)`/`On(0x40)`.

    On SUBSTITUE le foyer sur le MODULE (forme B) et on compte les passages : une implementation
    qui poserait `consumed = True` en direct rendrait les memes `_restants` et serait pourtant
    fausse -- c'est exactement l'ecart que #936-r1 a du corriger ailleurs."""
    st = _state_reel()
    _poser(st, ET_GARDE, keep=True)
    _poser(st, ET_FRAGILE, keep=False)
    _mourant(st)

    vus = []
    vrai = REM.remove_effect_instance

    def espion(state, unit_id, eff):
        vus.append(int(eff.effect_type))
        return vrai(state, unit_id, eff)

    REM.remove_effect_instance = espion
    try:
        REV.ReviveUnitOperation.execute(st, PORTEUR)
    finally:
        REM.remove_effect_instance = vrai
    assert vus == [ET_FRAGILE], (
        "le foyer doit etre appele pour le SEUL candidat retenu : %s" % vus)


# ------------------------------- etage 2 : LE GATE EST CONDITIONNEL (la face MORT, #547-r13)

def test_sur_le_chemin_de_MORT_le_gate_n_est_PAS_arme():
    """`options.<+0x08>` vaut **0** aux quatre producteurs de MORT / DESPAWN : un effet a
    `KeepOnRevive = True` y est retire QUAND MEME.

    C'est la face opposee de l'etage 1, dans le MEME fichier et sur le MEME attribut. Si quelqu'un
    << simplifiait >> en lisant `keep_on_revive` inconditionnellement, l'etage 1 resterait vert et
    celui-ci rougirait -- c'est la seule paire qui attrape cette faute."""
    st = _state_reel()
    garde = _poser(st, ET_GARDE, keep=True)
    fragile = _poser(st, ET_FRAGILE, keep=False)
    retires = REM.remove_effects_operation(st, PORTEUR, step=None)     # gate au DEFAUT = False
    assert sorted(int(x) for x in retires) == sorted([ET_GARDE, ET_FRAGILE]), retires
    assert garde.consumed and fragile.consumed
    assert _restants(st) == []


def test_le_gate_est_le_SEUL_discriminant_entre_les_deux_appels():
    """Meme etat, meme `step`, SEUL `keep_on_revive_gate` change -> le resultat change. C'est la
    contre-epreuve directe du parametre : si le port ignorait l'argument, les deux appels
    rendraient la meme chose."""
    sans = _state_reel()
    _poser(sans, ET_GARDE, keep=True)
    _poser(sans, ET_FRAGILE, keep=False)
    REM.remove_effects_operation(sans, PORTEUR, step=None, keep_on_revive_gate=False)

    avec = _state_reel()
    _poser(avec, ET_GARDE, keep=True)
    _poser(avec, ET_FRAGILE, keep=False)
    REM.remove_effects_operation(avec, PORTEUR, step=None, keep_on_revive_gate=True)

    assert _restants(sans) == [] and _restants(avec) == [ET_GARDE], (
        "le gate ne discrimine pas : sans=%s avec=%s" % (_restants(sans), _restants(avec)))


def test_le_gate_du_step_et_celui_du_revive_sont_INDEPENDANTS():
    """Le natif saute a la SECONDE clause meme quand `options.step` n'a pas de valeur
    (`goto LAB_...` depuis le test de `HasValue`) : les deux gates ne sont pas imbriques.

    On l'exerce avec un `step` RENSEIGNE et le gate arme -- regime qu'aucun producteur du binaire ne
    produit, mais qui isole la structure du `if`."""
    st = _state_reel()
    garde = _poser(st, ET_GARDE, keep=True)
    fragile = _poser(st, ET_FRAGILE, keep=False)
    for e in (garde, fragile):
        e.remove_on_kill_step = KillUnitStep.AfterUnitRemove
    REM.remove_effects_operation(st, PORTEUR, step=int(KillUnitStep.AfterUnitRemove),
                                 keep_on_revive_gate=True)
    assert _restants(st) == [ET_GARDE], _restants(st)


# ---------------------------------------- etage 3 : LE DEFAUT DE SECOURS EST CELUI DU NATIF

def test_un_effet_qui_ne_DECLARE_PAS_l_attribut_SURVIT_au_revive():
    """Meme lecon que #1088 sur `remove_on_kill_step`, transposee : le defaut de secours du
    `getattr` doit etre celui de `IdunBattle.Entities.Effects.BaseEffect`, c'est-a-dire **True**.

    Ecrire `False` la ferait disparaitre au revive tous les effets hydrates par un chemin qui ne
    passe pas par `BaseEffect` -- une regression SILENCIEUSE, du type exact que le port a deja paye
    une fois (`remove_on_kill_step = 0` recopie hors du foyer)."""
    st = _state_reel()

    class _Nu:
        """Stub ETRANGER a la hierarchie : il ne declare NI `keep_on_revive` NI
        `remove_on_kill_step`. C'est le regime des deux `getattr` de secours."""
        def __init__(self):
            self.effect_type, self.consumed, self.name = ET_MUET, False, "nu"

    nu = _Nu()
    assert not hasattr(nu, "keep_on_revive"), "le stub doit rester SANS l'attribut"
    st.effects.by_unit.setdefault(PORTEUR, []).append(nu)
    _poser(st, ET_FRAGILE, keep=False)
    _mourant(st)
    REV.ReviveUnitOperation.execute(st, PORTEUR)
    assert not nu.consumed, (
        "un effet sans l'attribut a ete retire : le defaut de secours n'est pas celui du natif")


def test_le_defaut_de_la_classe_de_base_est_VRAI():
    """`BaseEffect.keep_on_revive` -- la valeur DERIVEE (`b0 01 c3` = `mov al,1 ; ret`).

    Assertion sur la CLASSE et non sur une instance : c'est l'attribut de classe que lisent les
    ~460 classes qui heritent sans surcharger."""
    assert BaseEffect.keep_on_revive is True
    st = _state_reel()
    ordinaire = BaseEffect(name="ordinaire", effect_type=ET_GARDE, target=PORTEUR)
    assert ordinaire.keep_on_revive is True, "l'instance n'herite pas du defaut de classe"
    st.effects.add_effect(PORTEUR, ordinaire)
    _mourant(st)
    REV.ReviveUnitOperation.execute(st, PORTEUR)
    assert _restants(st) == [ET_GARDE], "un effet ORDINAIRE ne survit pas au revive"


# ------------------------------------------------------------- etage 4 : LE RANG NATIF

def test_le_retrait_a_lieu_APRES_les_PV_et_AVANT_le_marquage_VIVANT():
    """RANG, mesure sur l'ETAT et non recopie d'un commentaire.

    Le natif place l'appel entre `IdunBattle.Operations.ReviveUnitOperation$$SetHealth` et la rafale
    `Remove(0xf)`/`Remove(8)`/`Add(0x14)`. Au moment ou les vecteurs `On(0x3f)`/`On(0x40)` partent,
    l'unite a donc deja ses PV mais n'est PAS encore marquee vivante. On observe l'etat DEPUIS le
    foyer substitue -- si l'appel etait deplace en fin de fonction, `alive` serait deja `True` et
    cet etage rougirait."""
    from engine.runner.components import HealthComponent, UnitComponent
    st = _state_reel()
    _poser(st, ET_FRAGILE, keep=False)
    _mourant(st)
    hc = st.get_entity(PORTEUR).get_component(HealthComponent)
    uc = st.get_entity(PORTEUR).get_component(UnitComponent)
    assert int(hc.hp) == 0 and not uc.alive, "montage : le porteur doit partir MORT a 0 PV"

    observe = {}
    vrai = REM.remove_effect_instance

    def espion(state, unit_id, eff):
        observe["hp"] = int(hc.hp)
        observe["alive"] = bool(uc.alive)
        observe["flags"] = set(uc_flags(st))
        return vrai(state, unit_id, eff)

    REM.remove_effect_instance = espion
    try:
        REV.ReviveUnitOperation.execute(st, PORTEUR)
    finally:
        REM.remove_effect_instance = vrai

    assert observe, "le foyer n'a jamais ete appele -- le rang n'a rien mesure"
    assert observe["hp"] == 600, (
        "les PV ne sont pas encore poses au moment du retrait (SetHealth doit PRECEDER) : %s"
        % observe["hp"])
    assert observe["alive"] is False, (
        "l'unite est deja marquee VIVANTE au moment du retrait : l'appel a ete deplace APRES la "
        "rafale de flags, alors que le natif le met AVANT")
    # SECOND SYMPTOME du meme deplacement, sur un canal INDEPENDANT d'`alive` : `Add(0x14 =
    # Revived)` appartient a la rafale qui SUIT le retrait, donc le flag ne doit pas encore etre la.
    # (On vise `Revived` et non `Downed` : ce dernier n'a AUCUN poseur porte -- cf. `revive.py` --
    # donc l'exiger mesurerait le montage, pas le rang.)
    from engine.runner.components import UnitFlagsComponent
    assert int(UnitFlagsComponent.REVIVED) not in observe["flags"], (
        "le flag `Revived` est deja pose au moment du retrait : l'appel a ete deplace APRES la "
        "rafale de flags")
    # ... et il DOIT y etre une fois l'operation finie : sans ce controle positif, l'assertion
    # ci-dessus passerait aussi sur un port qui ne poserait JAMAIS le flag.
    assert int(UnitFlagsComponent.REVIVED) in set(uc_flags(st)), (
        "temoin DEGENERE : le flag `Revived` n'est pas pose non plus a la FIN du revive")


def uc_flags(st) -> list:
    from engine.runner.components import UnitFlagsComponent
    fl = st.get_entity(PORTEUR).get_component(UnitFlagsComponent)
    return [int(f) for f in (fl.flags if fl is not None else [])]


# -------------------------------------------------- etage 5 : LA VALEUR FIGEE (entree versionnee)

def test_le_port_concorde_avec_l_entree_versionnee():
    """Le port dit-il la meme chose que ce qui a ete DERIVE du binaire ?

    Skippe en le disant quand le build n'est pas la -- les autres etages, eux, ont deja tourne."""
    sys.path.insert(0, str(PYDIR))
    import probe_547r13_keep_on_revive as P                                # noqa: E402
    try:
        table = P.lire_tsv()
    except SystemExit as exc:
        pytest.skip("entree versionnee absente pour le build courant : %s" % exc)
    assert table, "l'entree versionnee est VIDE -- un accord sur rien ne prouve rien"
    assert table.get("IdunBattle.Entities.Effects.BaseEffect") is True
    assert BaseEffect.keep_on_revive is table["IdunBattle.Entities.Effects.BaseEffect"]

    from engine.entities.effects.loki.precision_shot import PrecisionShot_AimEffect
    from engine.entities.effects.loki.rites_of_morkai import RitesOfMorkaiExtraDamageEffect
    #: Appariement natif -> mirror, ECRIT A LA MAIN parce qu'il se LIT (meme discipline que #1088).
    #: `Loki.HealingBalmsEffect` n'y est pas : sa valeur est bien `False` au binaire, mais elle n'a
    #: AUCUN mirror sous `engine/entities/effects/` -- ce qui est porte sous ce nom est le TRIGGER
    #: `HealingBalmsDelayedHeal` (`runner/operations/triggers/loki/healing_balms.py`), pas une
    #: classe d'effet, donc rien ne peut porter l'attribut. C'est un NON-COUVERT nomme, pas un oubli.
    apparies = {
        "IdunBattle.Entities.Effects.Loki.PrecisionShot_AimEffect": PrecisionShot_AimEffect,
        "IdunBattle.Entities.Effects.Loki.RitesOfMorkai_ExtraDamageEffect":
            RitesOfMorkaiExtraDamageEffect,
    }
    for natif, cls in apparies.items():
        assert natif in table, (
            "%s ne DECLARE plus le getter dans l'entree versionnee -- le port porte une surcharge "
            "que le binaire n'a plus" % natif)
        assert table[natif] is False, (natif, table[natif])
        assert cls.keep_on_revive is False, (
            "%s : port=%s, binaire=%s" % (natif, cls.keep_on_revive, table[natif]))

    #: La 3e classe native a `False`, SANS mirror : on garde son existence pour qu'un port futur ne
    #: la redecouvre pas, et pour que sa DISPARITION du binaire se voie.
    assert table.get("IdunBattle.Entities.Effects.Loki.HealingBalmsEffect") is False

    faux = sorted(k for k, v in table.items() if v is False)
    assert faux == [
        "IdunBattle.Entities.Effects.Loki.HealingBalmsEffect",
        "IdunBattle.Entities.Effects.Loki.PrecisionShot_AimEffect",
        "IdunBattle.Entities.Effects.Loki.RitesOfMorkai_ExtraDamageEffect",
    ], ("le jeu des classes a `False` a bouge -- toute entrante doit recevoir sa surcharge "
        "portee DANS LE MEME COMMIT : %s" % faux)
    # NON-DEGENERESCENCE : les deux valeurs booleennes doivent etre representees.
    assert set(table.values()) == {True, False}, sorted(set(table.values()))


def test_les_racines_d_INDETERMINATION_sont_inventoriees():
    """Les classes qui DECLARENT le getter sans le rendre CONSTANT (il lit un champ d'instance, ou
    son corps n'est pas trivial). La derivation rend `INDETERMINE` pour elles et pour leur
    descendance -- **jamais un faux `True`**.

    Cet etage FIGE leur inventaire. Il ne pretend PAS que le port est faux pour elles : les `.ctor`
    des classes concernees ont ete LUS un par un au decompile (#547-r14, 30 lectures) et passent
    TOUS `keepOnRevive = 1`, y compris `IdunBattle.Entities.Effects.DynamicStatModifierEffect$$.ctor`
    qui le code EN DUR pour toute sa descendance -- l'heritage du defaut `True` est donc FIDELE. Ce
    qui doit se voir, c'est une racine NOUVELLE : elle sortirait du perimetre de ces lectures et
    devrait etre lue a son tour."""
    # `PYDIR` = `scripts/python` -> `parents[1]` = la racine du depot, qui porte `data/`.
    p = Path(PYDIR).parents[1] / "data" / "symbols"
    tsvs = sorted(p.glob("*/metadata/keep_on_revive.tsv")) if p.is_dir() else []
    if not tsvs:
        pytest.skip("aucune entree versionnee `keep_on_revive.tsv` dans l'arbre")
    sys.path.insert(0, str(PYDIR))
    import build_pin                                                       # noqa: E402
    courant = [t for t in tsvs if t.parent.parent.name == build_pin.current_build()]
    if not courant:
        pytest.skip("pas de `keep_on_revive.tsv` pour le build courant")
    racines = []
    for line in courant[0].read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            continue
        c = line.split("\t")
        if len(c) >= 3 and c[2] == "":
            racines.append(c[0])
    assert sorted(racines) == [
        "IdunBattle.Entities.Effects.AStatModifierEffect",
        "IdunBattle.Entities.Effects.Loki.HuntTheFallen_FallenEffect",
        "IdunBattle.Entities.Effects.Loki.SwarmHitReductionEffect",
        "IdunBattle.Entities.Effects.NoneEffect",
        "IdunBattle.Entities.Effects.TemporaryEffect",
    ], ("les racines d'INDETERMINATION ont bouge -- toute NOUVELLE doit voir son `.ctor` lu au "
        "decompile avant qu'on la laisse heriter du defaut : %s" % sorted(racines))


# ------------------------------------- etage 6 : AUCUNE SURCHARGE PORTEE QUI NE SOIT PAS MESUREE

def test_aucune_classe_portee_ne_surcharge_le_flag_hors_des_DEUX_mesurees():
    """INVARIANT, pas seuil : toute classe d'effet portee qui DECLARE `keep_on_revive` dans son
    propre `__dict__` doit etre l'une des deux dont la valeur `False` est DERIVEE du binaire.

    C'est le cran qui empeche d'inventer une surcharge << par bon sens >>. Le balayage importe tout
    `engine/entities/effects/**` -- pas une liste blanche de modules, qui ne pourrait pas montrer la
    classe qu'elle a oubliee -- et il asserte son propre non-vide."""
    import engine.entities.effects as PKG
    for m in pkgutil.walk_packages(PKG.__path__, PKG.__name__ + "."):
        try:
            importlib.import_module(m.name)
        except Exception:                        # noqa: BLE001 -- un module non importable est
            continue                             # un autre gisement (#485), pas celui-ci
    vues, pile = set(), [BaseEffect]
    while pile:
        c = pile.pop()
        if c in vues:
            continue
        vues.add(c)
        pile.extend(c.__subclasses__())
    assert len(vues) > 50, ("le balayage n'a visite que %d classes -- il ne mesure rien" % len(vues))

    declarantes = sorted(c.__name__ for c in vues
                         if c is not BaseEffect and "keep_on_revive" in c.__dict__)
    assert declarantes == ["PrecisionShot_AimEffect", "RitesOfMorkaiExtraDamageEffect"], (
        "surcharge portee non appariee a une valeur DERIVEE du binaire : %s" % declarantes)

    hors = sorted((c.__name__, repr(c.keep_on_revive)) for c in vues
                  if not isinstance(getattr(c, "keep_on_revive", True), bool))
    assert not hors, ("`keep_on_revive` hors du domaine booleen : %s" % hors)
