#!/usr/bin/env python
"""#477-r31 -- le terme `AttractMechanicals` compte-t-il LES DEUX CAMPS, ou seulement les AMIS ?

QUESTION BINAIRE, posee avant la methode : sur une MEME decision, un MEME mover MECHANICAL et des
tuiles candidates de MEME geometrie, le `Tile(7)` NATIF monte-t-il de `+10` UNIQUEMENT sur les
tuiles adjacentes a un Marshal ALLIE (modele AMIS), ou aussi sur celles adjacentes a un Marshal
ENNEMI (modele DEUX CAMPS) ?

CE QUE DIT LE DECOMPILE, relu ligne a ligne sur le build courant --
`IdunBattle.AI.Utilities.AttractMechanicalsUtility.u003CEvaluateMovementInStepsu003Ed__1$$MoveNext` :

    x = Fix64(0);
    if (case.Unit == null)                          yield break;             // AUCUN yield
    if (!UnitExtensions.HasTrait(case.Unit, 5))     yield return x;          // 5 = Mechanical
    units = query.<slot 0x7a = GetAdjacentUnits, arite 4>(case.MovementTile, case.Unit, 0, 0);
    if (Enumerable.Any(units, <>c__DisplayClass1_0.<EvaluateMovementInSteps>b__0))
        x += GetUtilityValue("Marshal_AttractMechanicals");
    yield return x;

et le predicat `IdunBattle.AI.Utilities.AttractMechanicalsUtility.u003Cu003Ec__DisplayClass1_0$$
u003CEvaluateMovementInStepsu003Eb__0` :

    return UnitExtensions.HasActiveAbility(f, 0x45e) && f != case.Unit;

⚠ **LE CAMP EST UN ARGUMENT, PAS UNE PROPRIETE DU SLOT** -- et c'est la faute que ce cas repare.
`data/symbols/<build>/metadata/interface_slots.tsv` nomme le slot `0x7a` `GetAdjacentUnits`
(arite 4), ce dont `case-477r29` §4 avait conclu « donc LES DEUX CAMPS ». Mais la SIGNATURE reelle,
lue dans `frida/methods.tsv` (jamais dans les noms de parametres que ghidra affiche), est
`GetAdjacentUnits(from, friendsOf, enemiesOf, ignoreSteppables)`, et le call-site passe
`friendsOf = case.Unit`, `enemiesOf = null`. Le foyer terminal
`IdunBattle.Core.Services.BattleQuery$$CountOrGetUnitsOnTiles` fait alors :

    if (friendsOf != null && !UnitExtensions.IsFriend(u, friendsOf, ctx))  continue;
    if (enemiesOf != null && !UnitExtensions.IsEnemy(u, enemiesOf, ctx))   continue;

⇒ le nom du slot designe l'ensemble AVANT filtrage. **Cette feuille compte les AMIS**, exactement
comme le `GetAdjacentFriends` (slot `0x83`, arite 2) de `RadSaturationPlaybook` -- lequel n'est
d'ailleurs, une fois deroule, qu'un `GetUnitsOnTiles(..., friendsOf=<entite JOUEUR de unit>,
enemiesOf=null, ...)`. Les deux feuilles interrogent le MEME ensemble ; ce qui les separe :

    | axe          | RadSaturationPlaybook (1202) | AttractMechanicalsUtility          |
    |--------------|------------------------------|------------------------------------|
    | gate         | aucun                        | `HasTrait(case.Unit, Mechanical)`  |
    | self         | INCLUS (aucun `RemoveAll`)   | EXCLU (`f != case.Unit`)           |
    | agregation   | `Count`  -> `+10 x n`        | `Any`    -> `+10` AU PLUS UNE FOIS |
    | cle BC       | `RadSaturation_AdjacentMarshals` | `Marshal_AttractMechanicals`   |

DEUX MONTAGES, parce qu'un seul ne separe pas tout :

  * MONTAGE `camp` -- la geometrie de `probe_477r29` : une CIBLE NEUTRE au centre, un Marshal ALLIE
    et un Marshal ENNEMI a distance 2 d'elle, de part et d'autre, zone STRICTEMENT PLATE. Les deux
    bras vivent dans la MEME decision, sur le MEME sweep : seul le CAMP change.
    ⚠ CE QUI COMMANDE LA GEOMETRIE, CE SONT LES HOOKS : `scorerTileTermTrace` ne voit que le tier
    COMPARABLE (les tuiles d'ATTAQUE). Une disposition ou les deux Marshals encadrent le carrier
    rend un ensemble hooke ENTIEREMENT d'un seul bras -- donc inseparable. C'est la cible neutre au
    centre qui rend l'ensemble ventilable par camp (mesure payee par #477-r29).
  * MONTAGE `agreg` -- DEUX Marshals ALLIES tels qu'une tuile candidate soit adjacente aux DEUX et
    une autre a UN SEUL. Sans lui, `Any` et `Count` rendent la MEME chose et le mutant `COUNT (x n)`
    ne peut pas mordre : le montage `camp` ne separe PAS l'agregation, et le dire est le seul moyen
    de ne pas prendre son silence pour une confirmation.

Les geometries sont CHERCHEES et non devinees (triplet a elevation CONSTANTE tel que les voisines de
la cible se ventilent en groupes MIROIR), et celle de `C4_09` retrouve a l'identique celle de
`probe_477r29`.

LE PORTEUR. Contrairement a `RadSaturation` (dont le seul porteur est un SUMMON), cette feuille ne
se gate sur AUCUNE ability : son gate est un TRAIT. **13 heros du pool sont Mechanical** -- aucune
greffe, aucune injection catalogue. Le carrier retenu (`admecDominus`) est choisi parmi eux pour ses
traits MINIMAUX et parce que son passif n'a PAS de playbook natif (`MasterAnnihilator` : aucun
`*Playbook$$.ctor` dans le binaire), donc aucun terme de tuile concurrent non porte.

⚠ LE CONFOND INVERSE de `probe_477r29` : sur un mover Mechanical qui porterait AUSSI 1202, les DEUX
termes valent 10 et s'ajoutent sur les memes tuiles. L'etape 0 REFUSE donc un carrier porteur de
`TriggeredAbilityType.RadSaturation`.

MESURE, decomposee par etage (hooks EXISTANTS de `scorer-damage-trace`, armes pour UN SEUL
`aiStepDryRun` puis desarmes -- AUCUNE reinjection) :

    X_nat (tuile) = Tile(7) - Elevation - TileEffects
    X_port(tuile) = feuilles du port, MEME retranchement (foyer unique `probe_193c.x_port`)

VERDICT (les deux sont exiges) :
  1. ACCORD    : `X_nat == X_port` sur toutes les tuiles hookees ;
  2. SEPARATION: le mutant qui EST la question du montage doit MORDRE (`DEUX-CAMPS` pour `camp`,
     `COUNT (x n)` pour `agreg`) -- sans quoi le montage est DEGENERE et un vert ne prouve rien.

Usage (ASCII only, depuis scripts/python) :
  python probe_477r31_attract_mechanicals_camp.py --offline-only
  python probe_477r31_attract_mechanicals_camp.py --board MC1_67 --seed 777
  python probe_477r31_attract_mechanicals_camp.py --board MC1_67 --seed 777 --montage agreg
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_pin import BuildPinRefused                              # noqa: E402
from rl_collect_batch import _resolve_session, _rpc                # noqa: E402
from probe_193c_move_playbook_terms import (_r, _by_tile, _one, _port_leaves,   # noqa: E402
                                            _exiger_build_des_rva, x_port,
                                            cause_x_nat_non_mesurable)
from probe_212_spiritual_leader_tile_term import _apply_native_via   # noqa: E402  (`call` injecte)

PYDIR = Path(__file__).resolve().parent
ROOT = PYDIR.parents[1]

#: le carrier : HERO du pool, MECHANICAL (c'est le gate), traits minimaux, passif SANS playbook.
CARRIER = "admecDominus"
MARSHAL_UNIT = "admecMarshall"       # porte l'ACTIVE DoctrinaImperatives (0x45e = 1118)
TARGET_FOE = "necroWarden"           # la CIBLE neutre, sans DoctrinaImperatives
#: UN AMI SANS `DoctrinaImperatives`, place a cote de tuiles candidates SANS Marshal. Il n'est pas
#: decoratif : sans lui, le SEUL ami adjacent a une tuile candidate est le Marshal, si bien que
#: « les amis porteurs du predicat » et « les amis » coincident -- le mutant `SANS-PREDICAT` ne peut
#: alors pas mordre, et un port qui aurait OUBLIE `HasActiveAbility` passerait le test.
NEUTRAL_FRIEND = "orksNob"

#: MONTAGE `camp` -- `board -> (carrier, marshal ALLIE, marshal ENNEMI, cible neutre, ami neutre)`.
#: Geometrie de `probe_477r29` (re-verifiee par le chercheur de ce probe : zone plate, >= 2 tuiles
#: « ALLIE seul », >= 2 « ENNEMI seul », >= 1 temoin parmi les voisines de la cible). `neutral` est
#: CHERCHE en plus : une case adjacente a >= 1 tuile TEMOIN et a AUCUNE tuile de bras.
LAYOUTS_CAMP = {
    "MC1_67": {"carrier": (4, 5), "ally": (2, 7), "foe": (6, 7), "target": (4, 7),
               "neutral": (5, 5)},
    "C4_09":  {"carrier": (4, 2), "ally": (2, 2), "foe": (5, 1), "target": (3, 1),
               "neutral": (1, 0)},
}

#: MONTAGE `agreg` -- `board -> (carrier, marshal ALLIE 1, marshal ALLIE 2, cible neutre)`.
#: CHERCHEE : parmi les voisines de la cible, >= 1 tuile adjacente aux DEUX Marshals (`Count` = 2,
#: `Any` = 1), >= 1 adjacente a UN SEUL, >= 1 temoin, zone a elevation CONSTANTE.
#:   MC1_67 : cible (3,8), Marshals (4,6) et (5,8) -> DEUX=[(4,7)] UN=[(3,7),(4,8)] temoin=[(2,8),(2,7)]
#:   C4_09  : cible (3,1), Marshals (2,2) et (4,2) -> DEUX=[(3,2)] UN=[(4,1),(2,1)] temoin=[(3,0),(4,0),(2,0)]
LAYOUTS_AGREG = {
    "MC1_67": {"carrier": (1, 7), "ally": (4, 6), "ally2": (5, 8), "target": (3, 8)},
    "C4_09":  {"carrier": (5, 0), "ally": (2, 2), "ally2": (4, 2), "target": (3, 1)},
}
MONTAGES = {"camp": LAYOUTS_CAMP, "agreg": LAYOUTS_AGREG}


def _slot_table(build: str) -> dict:
    """`(interface, slot) -> (nom, arite)` depuis l'entree VERSIONNEE `metadata/interface_slots.tsv`."""
    p = ROOT / "data" / "symbols" / build / "metadata" / "interface_slots.tsv"
    out = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        cells = line.split("\t")
        if len(cells) < 4:
            continue
        try:
            out[(cells[0], int(cells[1]))] = (cells[2], int(cells[3]))
        except ValueError:
            continue
    return out


def _signature(build: str, name: str) -> list:
    """Les signatures (`params`) des methodes nommees `name` dans `frida/methods.tsv`.

    C'est LA source du camp : le nom du slot ne dit pas quel argument filtre quoi, les noms de
    parametres affiches par ghidra ne sont pas une mesure, et cette table-la porte le type ET le nom
    des parametres tels que le dump IL2CPP les publie."""
    p = ROOT / "data" / "symbols" / build / "frida" / "methods.tsv"
    out = []
    with p.open(encoding="utf-8") as fh:
        for line in fh:
            cells = line.rstrip("\n").split("\t")
            if len(cells) >= 6 and cells[1] == name:
                out.append(cells[5])
    return out


def _build_hash() -> str:
    import build_pin
    return build_pin.installed_build()


# --------------------------------------------------------------------------------------------
# ETAPE 0 -- offline : le SLOT, la SIGNATURE (le camp), le POIDS, le GATE et la garde de CONFOND
# --------------------------------------------------------------------------------------------
def step0() -> int:
    import io
    import contextlib
    import gameconfig as GC
    from engine import weights as W
    from engine.entities.traits.unit_trait import UnitTrait
    from engine.entities.triggered_ability_type import TriggeredAbilityType
    from engine.utilities.tile import AttractMechanicalsUtility

    print("=== ETAPE 0 (offline) ===")
    rc = 0
    build = _build_hash()
    tbl = _slot_table(build)

    # 1. Le SLOT : nom ET arite. Un nom designe un ENSEMBLE de slots (122..124 ici).
    got = tbl.get(("IBattleQuery", 0x7a))
    ok = got == ("GetAdjacentUnits", 4)
    print("  slot 0x7a -> %-20s arite %s   [%s]"
          % ((got or ("?", "?"))[0], (got or ("?", "?"))[1], "OK" if ok else "ROUGE"))
    rc |= 0 if ok else 1
    # le slot de la feuille VOISINE (`RadSaturationPlaybook`), pour que le contraste soit LU ici.
    gotf = tbl.get(("IBattleQuery", 0x83))
    print("  slot 0x83 -> %-20s arite %s   (feuille voisine RadSaturationPlaybook)"
          % ((gotf or ("?", "?"))[0], (gotf or ("?", "?"))[1]))
    if gotf != ("GetAdjacentFriends", 2):
        rc = 1

    # 2. LA SIGNATURE -- ce qui tranche le CAMP. Le nom `GetAdjacentUnits` ne le dit PAS.
    sigs = set(_signature(build, "IdunBattle.Core.Services.BattleQuery.GetAdjacentUnits"))
    attendus = [s for s in sigs if "friendsOf:" in s and "enemiesOf:" in s]
    print("  signatures GetAdjacentUnits = %d, dont %d portant (friendsOf, enemiesOf) :"
          % (len(sigs), len(attendus)))
    for s in sorted(attendus):
        print("    %s" % s)
    if len(attendus) != len(sigs) or not sigs:
        print("  ROUGE : une surcharge d'arite 4 sans le couple (friendsOf, enemiesOf) -- le "
              "raisonnement 'arg2 = friendsOf' ne tient plus, RELIRE le call-site")
        rc = 1
    print("  => le call-site passe (MovementTile, case.Unit, 0, 0) : friendsOf = case.Unit, "
          "enemiesOf = null -> `CountOrGetUnitsOnTiles` ne garde que les AMIS")

    # 3. POIDS : capture vs gameconfig VIVANT (piege #271).
    bc = json.loads((ROOT / "data" / "seed-bc.json").read_text(encoding="utf-8"))
    cap = (((bc.get("Utilities") or {}).get("Default") or {})
           .get(AttractMechanicalsUtility.WEIGHT_CATEGORY) or {}).get(
               AttractMechanicalsUtility.WEIGHT_KEY)
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        wt = W.load()
    live = wt.sub(AttractMechanicalsUtility.WEIGHT_CATEGORY, AttractMechanicalsUtility.WEIGHT_KEY)
    print("  poids %-28s capture=%s  moteur=%s%s"
          % (AttractMechanicalsUtility.WEIGHT_KEY, cap, live,
             "  [REPLI CAPTURE]" if "repli" in (err.getvalue() or "").lower() else ""))
    if not live:
        print("  ROUGE : poids nul -> le terme serait plat, la mesure ne peut rien contredire")
        rc = 1

    # 4. GATE : le carrier DOIT etre Mechanical (sinon la feuille rend 0 et rien n'est mesure).
    u = GC.unit(CARRIER) or {}
    traits = u.get("traits") or []
    mech = UnitTrait.Mechanical.name in traits
    print("  carrier %-14s traits=%s  Mechanical=%s" % (CARRIER, traits, mech))
    if not mech:
        print("  ROUGE : carrier NON Mechanical -> le gate `HasTrait(case.Unit, 5)` coupe tout")
        rc = 1

    # 5. CONFOND INVERSE de #477-r29 : le carrier ne doit PAS porter RadSaturation, dont le terme
    #    vaut AUSSI 10 et s'ajoute sur LES MEMES tuiles.
    pas = u.get("passiveAbilities") or []
    print("  carrier passifs=%s actifs=%s" % (pas, u.get("activeAbilities") or []))
    if TriggeredAbilityType.RadSaturation.name in pas:
        print("  ROUGE : carrier porteur de RadSaturation -> DEUX termes de +10 sur les memes "
              "tuiles ; X_nat ne trancherait rien")
        rc = 1

    # 6. le porteur du PREDICAT.
    act = (GC.unit(MARSHAL_UNIT) or {}).get("activeAbilities") or []
    print("  %-14s activeAbilities=%s" % (MARSHAL_UNIT, act))
    if "DoctrinaImperatives" not in act:
        print("  ROUGE : le porteur du predicat ne porte pas DoctrinaImperatives")
        rc = 1

    # 7. la CIBLE ne doit pas porter le predicat (elle est ENNEMIE : elle nourrirait le mutant
    #    DEUX-CAMPS sur des tuiles ou l'on ne l'attend pas).
    if "DoctrinaImperatives" in ((GC.unit(TARGET_FOE) or {}).get("activeAbilities") or []):
        print("  ROUGE : la cible neutre %s porte DoctrinaImperatives" % TARGET_FOE)
        rc = 1

    print("  ETAPE 0 : %s" % ("OK" if rc == 0 else "ROUGE"))
    return rc


# --------------------------------------------------------------------------------------------
# MODELES compares -- le port (AMIS) et ses mutants
# --------------------------------------------------------------------------------------------
def _marshals(units, tile, leaf_ctx) -> int:
    """Nombre d'unites de `units` ADJACENTES a `tile` (adjacence NATIVE) portant 0x45e."""
    from engine import battle_query as bq
    from engine.entities.active_ability_type import ActiveAbilityType
    elev = leaf_ctx.get("elev_by_pos")
    neigh = bq.neigh_map(leaf_ctx)
    di = int(ActiveAbilityType.DoctrinaImperatives)
    n = 0
    for u in (units or ()):
        p = u.get("pos")
        if p and bq.is_adjacent(tile, p, elev, neigh) and di in (u.get("active") or ()):
            n += 1
    return n


def _profile(tile, leaf_ctx) -> tuple:
    """`(nAllies, nEnnemis)` de Marshals adjacents a la tuile candidate."""
    return (_marshals(leaf_ctx.get("friend_units"), tile, leaf_ctx),
            _marshals(leaf_ctx.get("enemy_units"), tile, leaf_ctx))


def _self_is_marshal(tile, leaf_ctx) -> int:
    """1 si le MOVER lui-meme (encore sur son origine) est un Marshal adjacent a `tile`.

    Le predicat natif ecrit `f != case.Unit` : ce compte est donc ce que le port doit IGNORER, et
    le mutant `SELF-INCLUS` ci-dessous est ce qui l'assertionne."""
    from engine import battle_query as bq
    from engine.entities.active_ability_type import ActiveAbilityType
    sp = leaf_ctx.get("self_pos")
    if not sp:
        return 0
    if not bq.is_adjacent(tile, tuple(sp), leaf_ctx.get("elev_by_pos"), bq.neigh_map(leaf_ctx)):
        return 0
    return int(int(ActiveAbilityType.DoctrinaImperatives)
               in (leaf_ctx.get("unit_active_abilities") or ()))


def _friends_adjacent(tile, leaf_ctx) -> int:
    """Tous les AMIS adjacents (self exclu, comme le predicat) -- SANS `HasActiveAbility`."""
    from engine import battle_query as bq
    elev, neigh = leaf_ctx.get("elev_by_pos"), bq.neigh_map(leaf_ctx)
    return sum(1 for u in (leaf_ctx.get("friend_units") or ())
               if u.get("pos") and bq.is_adjacent(tile, u["pos"], elev, neigh))


def _models(tile, leaves, leaf_ctx, wt) -> dict:
    """Le terme rendu par CHAQUE modele confronte -- le port, et les mutants de la contre-epreuve.

    Le port est lu dans `leaves` : c'est la feuille evaluee par son VRAI foyer de production
    (`apply_tile_attributes` + `AttractMechanicalsUtility.evaluate`, via `probe_193c._port_leaves`),
    pas une re-implementation. Les mutants sont recalcules ici a partir des memes entrees.
    `a_mordu` se lit ensuite modele par modele, SEPAREMENT du verdict."""
    from engine.utilities.tile import AttractMechanicalsUtility
    from engine.utilities.utility_type import UtilityType
    w = int(wt.sub(AttractMechanicalsUtility.WEIGHT_CATEGORY,
                   AttractMechanicalsUtility.WEIGHT_KEY))
    na, ne = _profile(tile, leaf_ctx)
    slf = _self_is_marshal(tile, leaf_ctx)
    porte = float(leaves.get(int(UtilityType.DoctrinaImperatives_AttractMechanicals), 0.0))
    return {
        "PORT (amis)":      porte,
        "DEUX-CAMPS":       float(w * (1 if (na + ne) else 0)),   # la lecture de case-477r29 §4
        "ENNEMIS":          float(w * (1 if ne else 0)),          # camp inverse
        "SANS-PREDICAT":    float(w * (1 if _friends_adjacent(tile, leaf_ctx) else 0)),
        "COUNT (x n)":      float(w * na),                        # `Count` au lieu d'`Any`
        "SELF-INCLUS":      float(w * (1 if (na + slf) else 0)),  # sans le `f != case.Unit`
        "ABSENT (avant)":   0.0,                                  # le port d'avant cette tranche
    }


# --------------------------------------------------------------------------------------------
# ETAPE 1 -- live
# --------------------------------------------------------------------------------------------
def build_extra(board: str, montage: str) -> list:
    """Les arguments `rl_duel build` du montage -- FOYER UNIQUE, partage avec la garde.

    Refuse un board sans geometrie plutot que de replier sur celle d'un autre : un placement hors
    zone plate reintroduirait l'asymetrie d'elevation que le montage exclut."""
    lay = (MONTAGES.get(montage) or {}).get(board)
    if lay is None:
        raise SystemExit("[477-r31] aucune geometrie %r pour le board %r (connus : %s)."
                         % (montage, board, ", ".join(sorted(MONTAGES.get(montage) or {}))))
    if montage == "camp":
        p_units = "%s,%s,%s" % (CARRIER, MARSHAL_UNIT, NEUTRAL_FRIEND)
        a_units = "%s,%s" % (MARSHAL_UNIT, TARGET_FOE)
        places = [("--place", "%s:%d,%d" % (CARRIER, lay["carrier"][0], lay["carrier"][1])),
                  ("--place", "%s:%d,%d" % (MARSHAL_UNIT, lay["ally"][0], lay["ally"][1])),
                  ("--place", "%s:%d,%d" % (NEUTRAL_FRIEND, lay["neutral"][0], lay["neutral"][1])),
                  ("--a-place", "%s:%d,%d" % (MARSHAL_UNIT, lay["foe"][0], lay["foe"][1])),
                  ("--a-place", "%s:%d,%d" % (TARGET_FOE, lay["target"][0], lay["target"][1]))]
    else:
        # DEUX Marshals ALLIES : `rl_duel` ne sait pas placer deux exemplaires du MEME unitId, donc
        # le second Marshal est un AUTRE porteur de `DoctrinaImperatives`. Il n'y en a qu'un au
        # gameconfig -> on GREFFE l'active sur un second heros du pool (cf. `_seed_bc_montage`).
        p_units = "%s,%s,%s" % (CARRIER, MARSHAL_UNIT, MARSHAL2_UNIT)
        a_units = TARGET_FOE
        places = [("--place", "%s:%d,%d" % (CARRIER, lay["carrier"][0], lay["carrier"][1])),
                  ("--place", "%s:%d,%d" % (MARSHAL_UNIT, lay["ally"][0], lay["ally"][1])),
                  ("--place", "%s:%d,%d" % (MARSHAL2_UNIT, lay["ally2"][0], lay["ally2"][1])),
                  ("--a-place", "%s:%d,%d" % (TARGET_FOE, lay["target"][0], lay["target"][1]))]
    out = ["--seed-bc", "<pose par l'appelant>", "--p-units", p_units, "--a-units", a_units]
    for flag, val in places:
        out += [flag, val]
    return out + ["--hp-player", "100000", "--hp-target", "100000"]


#: MONTAGE `agreg` seulement : un SECOND porteur de `DoctrinaImperatives`. Le gameconfig n'en a
#: qu'un (`admecMarshall`), et `rl_duel` ne place pas deux exemplaires du meme `unitId` -- l'active
#: est donc GREFFEE sur un autre heros du pool. C'est une MESURE et non un contournement : le corps
#: natif ne lit du voisin que `HasActiveAbility(f, 0x45e)`, ni ses stats ni ses traits ni ses armes.
MARSHAL2_UNIT = "admecManipulus"


def _seed_bc_montage(out_path: Path, montage: str) -> Path:
    """Le seed BC du montage.

    ⚠ DEUX ECRITURES, et la premiere a ete PAYEE PAR UNE MESURE ROUGE.

    1. `unequip_relic(admecMarshall)` -- LE CONFOND. `admecMarshall` porte au seed la relique
       `TertiaryAbility = 1457` (`TriggeredAbilityType.KardiocoreGalvanus`), dont le NATIF a une
       face NON-OWNER : `IdunBattle.AI.Playbook.Loki.KardiocoreGalvanusNonOwnerPlaybook.
       u003CCalculateMovementUtilityInStepsu003Ed__2$$MoveNext` rend
       `GetUtilityValue("KardiocoreGalvanus_AdjacentFriendly")` = **20** sur les tuiles adjacentes
       a son porteur, **gate `UnitExtensions.IsMechanical(case.Unit)`**. C'est le MEME gate, le MEME
       camp et LES MEMES TUILES que le terme mesure ici -- inseparables. Premiere mesure
       (`MC1_67`/777) : `X_nat = 30` la ou le port met `10`, sur les 3 tuiles du bras allie.
       Ce n'est pas un bug de cette tranche : `1457` MANQUE au registre
       `engine/playbook/non_owner.NON_OWNER_MOVE_PLAYBOOKS` (12 entrees portees, 25 playbooks
       non-owner dans le binaire). Residu **#477-r33**.
       ⚠ C'est aussi pourquoi `probe_477r29` ne l'avait pas vu : son carrier (`orksNob`) n'est PAS
       Mechanical, donc le gate coupait -- un confond peut dormir sous un montage et se reveiller
       sous le suivant.
    2. `agreg` seulement : `MARSHAL2_UNIT` recoit l'ACTIVE `DoctrinaImperatives` en plus de la
       sienne (greffe ADDITIVE, `replace=False`), faute d'un second porteur au gameconfig."""
    import catalog_inject
    bc = catalog_inject._load_seed(None)
    rep = catalog_inject.unequip_relic(bc, MARSHAL_UNIT)
    print("  relique retiree : %s TertiaryAbility %s -> None%s"
          % (rep["unitId"], rep["tertiaryBefore"], "  [RIEN A FAIRE]" if rep["rien_a_faire"] else ""))
    if rep["rien_a_faire"]:
        print("  ATTENTION : le seed ne porte plus la relique attendue -- le CONFOND a peut-etre "
              "change de forme ; relire `_seed_bc_montage` avant de croire la mesure")
    if montage == "agreg":
        rep = catalog_inject.graft_active_ability(bc, MARSHAL2_UNIT, "DoctrinaImperatives",
                                                  replace=False)
        print("  greffe : %s actifs %s -> %s (config ajoutee: %s)"
              % (rep["unitId"], rep["activeAbilitiesBefore"], rep["activeAbilitiesAfter"],
                 rep["configAdded"]))
        rep2 = catalog_inject.unequip_relic(bc, MARSHAL2_UNIT)
        print("  relique retiree : %s TertiaryAbility %s -> None" % (rep2["unitId"],
                                                                     rep2["tertiaryBefore"]))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(bc), encoding="utf-8")
    return out_path


def _build(seed, board, montage, seed_bc: Path, state: Path):
    extra = build_extra(board, montage)
    extra[1] = str(seed_bc)
    argv = ([sys.executable, "rl_duel.py", "build", "--seed", str(seed), "--board", board,
             "--state-file", str(state)] + extra)
    p = subprocess.run(argv, cwd=str(PYDIR), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if not state.exists():
        print("BUILD KO:\n%s" % ((p.stderr or p.stdout or "")[-2500:]))
        return None
    print((p.stdout or "").strip()[-900:])
    return json.loads(state.read_text())["runnerId"]


def _bras(prof: dict, montage: str, tiles) -> tuple:
    """Les deux groupes de tuiles que le montage doit OBSERVER A EGALITE.

    `camp`  : (Marshal ALLIE seul, Marshal ENNEMI seul) ;
    `agreg` : (DEUX Marshals amis, UN SEUL Marshal ami).
    Un montage dont un bras est vide COTE HOOKS ne separe rien -- c'est la mesure payee par
    #477-r29, ou 6 tuiles hookees etaient toutes du meme bras."""
    if montage == "camp":
        return ([t for t in tiles if prof[t][0] > 0 and prof[t][1] == 0],
                [t for t in tiles if prof[t][1] > 0 and prof[t][0] == 0])
    return ([t for t in tiles if prof[t][0] >= 2], [t for t in tiles if prof[t][0] == 1])


def mesurer(call, rid, montage="camp", max_steps=25, trace=print) -> dict:
    """Marche la trajectoire NATIVE jusqu'au pas ou les DEUX bras sont HOOKES, arme les hooks de
    `scorer-damage-trace` pour UN SEUL `aiStepDryRun`, et rend la mesure.

    `call(method, body, timeout)` est INJECTE : le probe passe son RPC de session, la garde
    (`tests/engine/test_477r31_attract_mechanicals_camp_live.py`) passe la fixture du harnais -- un
    seul montage, deux consommateurs, aucun fork.

    Rend `{"erreur": <str>}` si le regime n'est pas atteint, sinon
    `{"rows": [...], "prof": {...}, "step": n, "uid": n, "bras_a": [...], "bras_b": [...]}`."""
    from engine import weights as W
    from engine.ai import context as _ai_ctx
    from engine.playbook import scene as _scene

    dv0 = call("decisionView", {"runnerId": rid, "maxRank": 1}, 180)
    carrier_id = next((u.get("id") for u in (dv0.get("units") or [])
                       if u.get("visualId") == CARRIER and u.get("ctrl")), None)
    trace("  carrier u%s (%s)" % (carrier_id, CARRIER))
    if carrier_id is None:
        return {"erreur": "carrier %s absent de la bataille" % CARRIER}

    step, seen = 0, 0
    while step < max_steps:
        dry = call("aiStepDryRun", {"runnerId": rid}, 60)
        if not dry.get("ok") or not dry.get("hasNext"):
            return {"erreur": "trajectoire native epuisee au pas %d (%s) apres %d activation(s)"
                              % (step, dry.get("error"), seen)}
        if dry.get("activatedUnitId") != carrier_id:
            _apply_native_via(call, rid, dry)
            step += 1
            continue
        seen += 1
        dv = call("decisionView", {"runnerId": rid, "allAbilities": True, "maxRank": 32}, 180)
        mov = call("aiMovableTiles", {"runnerId": rid}, 90)
        mov_by_unit = {u.get("unitId"): u for u in (mov.get("units") or [])}
        wt = W.load()
        pred = _scene.build_predictor(call, rid)
        ctx = _ai_ctx.build(call, rid, dv, mov_by_unit, carrier_id, wt, pred)
        tiles = list(ctx.action_tiles or [])
        prof = {t: _profile(t, _port_leaves(ctx, t)[1]) for t in tiles}
        ba, bb = _bras(prof, montage, tiles)
        trace("  pas %-3d activation #%d : %d candidates | bras1=%d bras2=%d"
              % (step, seen, len(tiles), len(ba), len(bb)))
        if not (ba and bb):
            _apply_native_via(call, rid, dry)
            step += 1
            continue

        # --- regime realise : on arme les hooks pour UN SEUL dry-run ------------------------
        call("scorerDamageTraceOn", {"runnerId": rid}, 90)
        call("scorerDamageTraceClear", {"runnerId": rid, "stacks": 0}, 60)
        try:
            call("aiStepDryRun", {"runnerId": rid}, 90)
            tterm = call("scorerTileTermTraceDump", {"runnerId": rid, "max": 4000}, 90)
            elev = call("scorerElevTraceDump", {"runnerId": rid, "max": 4000}, 90)
            leaf = call("scorerLeafTraceDump", {"runnerId": rid, "max": 4000}, 90)
        finally:
            call("scorerDamageTraceOff", {"runnerId": rid}, 60)

        tt = _by_tile(tterm.get("entries") or [], "casterCol", "casterRow", "tileTerm")
        el = _by_tile(elev.get("entries") or [], "col", "row", "leaf")
        te = _by_tile([e for e in (leaf.get("entries") or []) if e.get("leaf") == "TileEffects"],
                      "col", "row", "value")
        if not tt:
            return {"erreur": "aucun event tileTerm -- hooks non armes ou aucun tier Comparable"}
        hooked = [t for t in tiles if t in tt]
        ha, hb = _bras(prof, montage, hooked)
        trace("  tuiles HOOKEES=%d | bras1=%d bras2=%d" % (len(hooked), len(ha), len(hb)))
        if not (ha and hb):
            trace("  les hooks n'ont pas couvert les DEUX bras -- on continue la marche")
            _apply_native_via(call, rid, dry)
            step += 1
            continue

        rows = []
        for t in sorted(hooked):
            vt, ve, vf = _one(tt, t), _one(el, t), _one(te, t, 0.0)
            leaves, lc = _port_leaves(ctx, t)
            x = (vt - ve - vf) if None not in (vt, ve, vf) else None
            rows.append({"tile": t, "x_nat": x, "x_port": x_port(leaves),
                         "models": _models(t, leaves, lc, wt),
                         "na": prof[t][0], "ne": prof[t][1],
                         "self": _self_is_marshal(t, lc),
                         "tile7": vt, "elev": ve, "tile_eff": vf,
                         # #477-r31 : la VENTILATION du port par feuille. Sans elle, un desaccord
                         # ne dit que son AMPLITUDE ; avec elle, on lit tout de suite si le port a
                         # mis le terme attendu et si un AUTRE terme manque -- c'est la
                         # decomposition par etage, cote port.
                         "leaves": {k: v for k, v in leaves.items() if abs(v) > 1e-9}})
        # LE CRAN (#10011) : une mesure ou AUCUNE ligne n'a de `x_nat` est un SILENCE, pas une
        # mesure. `divergences` saute les `None`, donc elle rend 0 pour TOUS les modeles et le
        # verdict d'accord passe A VIDE. Mesure du 2026-08-15 : 8 F / 43 P sur ce fichier, tous
        # sur les contre-epreuves, pour une panne de CAPTEUR (adresses epinglees refusees apres
        # le passage du jeu a un nouveau build).
        if not any(r["x_nat"] is not None for r in rows):
            return {"erreur": cause_x_nat_non_mesurable(call, rid, tt, el, te),
                    "rows_muettes": len(rows)}
        return {"rows": rows, "prof": prof, "step": step, "uid": carrier_id,
                "bras_a": ha, "bras_b": hb, "montage": montage,
                "friend_units": list(_port_leaves(ctx, tiles[0])[1].get("friend_units") or ()),
                "enemy_units": list(_port_leaves(ctx, tiles[0])[1].get("enemy_units") or ())}

    return {"erreur": "aucun pas DISCRIMINANT en %d pas (%d activations du carrier)"
                      % (max_steps, seen)}


def divergences(rows) -> dict:
    """`{nom de modele: nombre de tuiles ou X_nat != X_<modele>}` -- la contre-epreuve, chiffree.

    Le modele `PORT (amis)` y figure comme les autres : sa colonne EST le verdict d'accord, et
    `a_mordu` se lit de la meme facon pour tous, SEPAREMENT du verdict."""
    out = {}
    for nom in (rows[0]["models"] if rows else {}):
        n = 0
        for r in rows:
            if r["x_nat"] is None:
                continue
            xm = r["x_port"] - r["models"]["PORT (amis)"] + r["models"][nom]
            if abs(r["x_nat"] - xm) > 1e-6:
                n += 1
        out[nom] = n
    return out


#: le mutant qui EST la question de chaque montage : s'il ne mord pas, le montage est DEGENERE.
MUTANT_SEPARATEUR = {"camp": "DEUX-CAMPS", "agreg": "COUNT (x n)"}


def run(call, rid, montage="camp", max_steps=25) -> int:
    mes = mesurer(call, rid, montage, max_steps)
    if mes.get("erreur"):
        print("  ROUGE : %s" % mes["erreur"])
        return 1
    rows = mes["rows"]
    print("\n  tuile      nA nE self | Tile7nat  Elev  TileEff  X_nat  | X_port  DELTA")
    bad = 0
    for r in rows:
        d = (r["x_nat"] - r["x_port"]) if r["x_nat"] is not None else None
        if d is not None and abs(d) > 1e-6:
            bad += 1
        print("  %-10s %2d %2d %4d | %-9s %-5s %-8s %-6s | %-7.4g %s"
              % (r["tile"], r["na"], r["ne"], r["self"], r["tile7"], r["elev"], r["tile_eff"],
                 r["x_nat"], r["x_port"], ("%.4g" % d) if d is not None else "?"))

    # DECOMPOSITION PAR ETAGE -- on ne rend JAMAIS un desaccord comme un simple scalaire : on
    # imprime la ventilation du port par FEUILLE (nom d'`UtilityType`) sur les tuiles concernees,
    # plus le kit des voisins. C'est ce qui permet de dire QUELLE feuille manque, et non « il
    # manque 20 ».
    if bad:
        from engine.utilities.utility_type import UtilityType
        print("\n  VENTILATION du port sur les tuiles en DESACCORD (feuilles non nulles) :")
        for r in rows:
            d = (r["x_nat"] - r["x_port"]) if r["x_nat"] is not None else None
            if d is None or abs(d) <= 1e-6:
                continue
            noms = []
            for k, v in sorted(r["leaves"].items()):
                try:
                    noms.append("%s=%g" % (UtilityType(k).name, v))
                except ValueError:
                    noms.append("<%d>=%g" % (k, v))
            print("    %-10s manque %+.4g | %s" % (r["tile"], d, ", ".join(noms) or "(aucune)"))
        print("  VOISINS vus par le port (pos / actives / triggered / effets) :")
        for camp, us in (("ami", mes.get("friend_units") or ()),
                         ("ennemi", mes.get("enemy_units") or ())):
            for u in us:
                print("    %-6s %-22s @%-8s act=%s trg=%s eff=%s"
                      % (camp, u.get("vis"), u.get("pos"), list(u.get("active") or ()),
                         list(u.get("triggered") or ()), list(u.get("effects") or ())))

    mordu = divergences(rows)
    print("\n  CONTRE-EPREUVE (X_nat vs X_<modele>, sur les %d tuiles hookees) :" % len(rows))
    for nom, n in mordu.items():
        print("    %-16s divergences = %d / %d   a_mordu=%s"
              % (nom, n, len(rows), "OUI" if n else "NON"))

    rc = 0
    if bad:
        print("\n  ACCORD : ROUGE -- %d tuile(s) en desaccord X_nat vs X_port sur %d"
              % (bad, len(rows)))
        rc = 1
    else:
        print("\n  ACCORD : VERT -- 0 desaccord X_nat vs X_port sur %d tuiles" % len(rows))

    sep = MUTANT_SEPARATEUR[montage]
    if not mordu.get(sep):
        print("  SEPARATION : ROUGE -- le mutant %r rend la MEME chose que le port sur ce "
              "montage : REGIME DEGENERE, rien n'est tranche" % sep)
        rc = 1
    else:
        print("  SEPARATION : VERT -- le mutant %r diverge du natif sur %d tuile(s)"
              % (sep, mordu[sep]))

    # INERTIE PAR ALGEBRE, declaree et assertionnee DANS LES DEUX SENS : le carrier ne porte pas
    # `DoctrinaImperatives`, donc le volet self du predicat (`f != case.Unit`) ne peut pas mordre.
    self_actif = any(r["self"] for r in rows)
    if mordu.get("SELF-INCLUS") or self_actif:
        print("  SELF : le volet self a MORDU (self_marshal=%s) -- l'inertie declaree est FAUSSE"
              % self_actif)
        rc = 1
    else:
        print("  SELF : INERTE PAR ALGEBRE sur ce montage (le carrier ne porte pas 0x45e) -- "
              "le mutant SELF-INCLUS ne peut pas mordre, et c'est ASSERTIONNE")
    # Ce que le montage `camp` ne separe PAS, dit explicitement plutot que tu.
    if montage == "camp" and not mordu.get("COUNT (x n)"):
        print("  NON SEPARE ICI : `Any` vs `Count` -- un seul Marshal ami par tuile sur ce "
              "montage. C'est le montage `agreg` qui le tranche.")
    if montage == "agreg" and not mordu.get("DEUX-CAMPS"):
        print("  NON SEPARE ICI : le CAMP -- aucun Marshal ennemi sur ce montage. "
              "C'est le montage `camp` qui le tranche.")
    print("  VERDICT : %s" % ("ROUGE" if rc else "VERT"))
    return rc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline-only", action="store_true")
    ap.add_argument("--runner", type=int, default=None)
    ap.add_argument("--seed", default="777")
    ap.add_argument("--board", default="MC1_67")
    ap.add_argument("--montage", default="camp", choices=sorted(MONTAGES))
    ap.add_argument("--max-steps", type=int, default=25)
    ap.add_argument("--state-file", default=None)
    a = ap.parse_args()

    rc0 = step0()
    if a.offline_only:
        return rc0
    if rc0:
        print("ETAPE 0 ROUGE -> on n'arme rien (une mesure sur un montage faux ne prouve rien)")
        return rc0
    try:
        _exiger_build_des_rva()
    except BuildPinRefused as exc:
        print(str(exc))
        return 2
    sid = _resolve_session()
    call = (lambda m, b, t=90: _r(sid, m, b, t))
    print("\n=== ETAPE 1 (live) -- montage %s ===" % a.montage)
    if a.runner is not None:
        return run(call, a.runner, a.montage, a.max_steps)
    tag = uuid.uuid4().hex[:8]
    state = Path(a.state_file) if a.state_file else (
        ROOT / "logs" / "runners" / ("probe477r31-%s.json" % tag))
    seed_bc = ROOT / "logs" / "runners" / ("probe477r31-seedbc-%s.json" % tag)
    _seed_bc_montage(seed_bc, a.montage)
    rid = _build(a.seed, a.board, a.montage, seed_bc, state)
    if rid is None:
        return 1
    print("  runner %d seed=%s board=%s montage=%s" % (rid, a.seed, a.board, a.montage))
    try:
        return run(call, rid, a.montage, a.max_steps)
    finally:
        _r(sid, "disposeRunner", {"runnerId": rid}, 30)
        for p in (state, seed_bc):
            try:
                p.unlink()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
