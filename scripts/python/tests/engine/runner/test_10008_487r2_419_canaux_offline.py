"""#10008 -- GARDE des DEUX canaux que la tranche #487-r2 / #419 ajoute au foyer
`frida/hooks/features/ai-step/rpc-snapshot.ts`, et du seul consommateur Python qu'ils appellent.

MEME forme que son voisin `test_999r3r2_545r1_287r5r2_seeds_snapshot_offline.py`, dont il est le
prolongement direct : un champ que le CANAL va publier et que `load_state` laissait tomber.

Les etages qui MORDENT :

  A. SEED de `receiveDamageTypeThisTurn` (`#487-r2`). `ActorStatisticsComponent+0x80` est un
     `Dictionary<DamageProfileType, int>` -- un COMPTE D'INSTANCES PAR PROFIL, jamais une somme de
     degats. Le lecteur porte existe depuis #202 (`UnitsThatTakenDamageThisTurn` = `ContainsKey`)
     et #487-r1 en fait le substrat de la face DECISION de `1088 HellfyreMissileRack`, mais AUCUN
     canal ne le seedait : un etat RECHARGE repartait de `{}`.
     ⚠ Le TRI-ETAT y est plus glissant qu'ailleurs, parce que `{}` (mesure : rien recu ce tour)
     est l'etat MAJORITAIRE. Un `null` de panne rabattu sur `{}` ETEINDRAIT un gate au lieu de
     faire s'abstenir le playbook.

  B. Les DEUX CAPTEURS, lus dans le hook. ⚠ Cet etage garde le CODE, pas le DEPLOIEMENT : les
     deux champs n'arriveront dans un payload qu'apres une FENETRE DE REINJECT, qui appartient a
     l'orchestrateur. Le volet live est `scripts/python/probe_10008_canaux_du_foyer.py`.

  C. NON-REGRESSION DE NOMMAGE, et c'est le cran qui a motive la tranche. Les deux fiches
     nommaient leur champ IL2CPP a cote :
        `receivedDamageThisTurn`  (fiche #487-r2)  vs `ReceiveDamageTypeThisTurn`  (build)
        `Weapons`                 (naturel)        vs `<Weapons>k__BackingField`   (build)
     Un `fieldOffsetOr` sur le nom de la fiche se serait REPLIE EN SILENCE sur le litteral
     decompile : il aurait << marche >> sur ce build par coincidence d'offset, et serait devenu
     faux au premier deplacement de champ, sans que rien ne le dise. Cet etage FIGE les deux noms
     MESURES au RPC `classFields` (session 93, lecture pure).

ASCII only (cp1252).
"""
from __future__ import annotations

#: DECLENCHEUR -- ce qui doit changer pour que ce fichier puisse changer de verdict.
#: `engine/**` parce que l'etage A importe `load_state` ; et les TROIS fichiers de hook que
#: l'etage B/C LISENT, qu'aucun glob Python ne couvre.
DECLENCHEUR = {
    "chemins": (
        "scripts/python/conftest.py", "scripts/python/tests/conftest.py",
        "scripts/python/tests/engine/conftest.py",
        "scripts/python/tests/engine/runner/conftest.py",
        "scripts/python/engine/**/*.py", "scripts/python/*.py",
        "frida/hooks/features/ai-step/rpc-snapshot.ts",
        "frida/hooks/game/receive-damage-types.ts",
        "frida/hooks/game/weapons.ts",
        "data/seed-bc.json",
    ),
    "build": False,
    "toujours": False,
    "raison": "Purement offline : aucun runner, aucun RPC. L'etage A monte un `State` depuis des "
              "payloads SYNTHETIQUES, les etages B et C lisent des fichiers source du depot. "
              "Aucune table de metadonnee du build n'est consultee -> `build: False`.",
}

import os                                                                # noqa: E402
import sys                                                               # noqa: E402
from pathlib import Path                                                 # noqa: E402

import pytest                                                            # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))))

import hexgeo                                                            # noqa: E402
from engine.entities.damage_profile_type import DamageProfileType        # noqa: E402
from engine.entities.pathfinding.board import Board                      # noqa: E402
from engine.runner import snapshot as SNAP                               # noqa: E402
from engine.runner.components import UnitComponent                       # noqa: E402

#: `<racine>/scripts/python/tests/engine/runner/<ce fichier>` -> CINQ remontees.
RACINE = Path(__file__).resolve().parents[5]

COLS, ROWS = 5, 5
VIVANT, PLAYER_MOI = 10, 3


def _tid(col: int, row: int) -> int:
    return col * ROWS + row + 1


def _tiles() -> list:
    out = []
    for col in range(COLS):
        for row in range(ROWS):
            nb = [_tid(c, r) for (c, r) in hexgeo.neighbors(col, row)
                  if 0 <= c < COLS and 0 <= r < ROWS]
            out.append({"id": _tid(col, row), "col": col, "row": row, "elevation": 0,
                        "walkable": True, "isWall": False, "neighbours": nb})
    return out


def _state():
    decision = {"currentPlayer": PLAYER_MOI, "units": [
        {"id": VIVANT, "visualId": "bloodDeathCompany", "alive": True, "team": 1,
         "owner": PLAYER_MOI, "pos": {"col": 0, "row": 2}, "effects": []}]}
    observe = {"units": [{"squadId": VIVANT, "hp": 1000, "hpMax": 1000}]}
    snap = {"statTypes": {}, "units": [
        {"entityId": VIVANT, "entityType": 1, "stats": {}, "unitFlags": []}]}
    return SNAP.load_state(decision, observe, snapshot=snap,
                           board=Board(_tiles(), adjacency="evenq"))


def _actor_stats(champ=...):
    """UNE ligne `actorStats`. `champ=...` laisse la cle ABSENTE -- le TEMOIN exact du bundle
    d'avant cette tranche."""
    ligne = {"entityId": VIVANT}
    if champ is not ...:
        ligne["receiveDamageTypeThisTurn"] = champ
    return {"units": [ligne]}


# =================================================================================================
# ETAGE A -- LE SEED DU DICTIONNAIRE DE PROFILS (#487-r2)
# =================================================================================================

#: Deux profils DISTINCTS et deux comptes DISTINCTS : un seed qui poserait une constante, ou qui
#: confondrait la cle et la valeur, passerait un montage a valeur unique.
PROFIL_A, COMPTE_A = DamageProfileType.Psychic, 2
PROFIL_B, COMPTE_B = DamageProfileType.Bolter, 1


def test_a1_le_dictionnaire_est_seede():
    """`receiveDamageTypeThisTurn.profiles` -> `UnitComponent.received_damage_this_turn`, mirror du
    `Dictionary<DamageProfileType,int>` de `ActorStatisticsComponent@+0x80` qu'ecrit
    `IdunBattle.Entities.Components.ActorStatisticsComponent$$RegisterReceivedDamage`."""
    st = _state()
    SNAP._load_actor_statistics(st, _actor_stats(
        {"profiles": {str(int(PROFIL_A)): COMPTE_A, str(int(PROFIL_B)): COMPTE_B},
         "count": 2, "freeCount": 0, "freeSlotsSkipped": 0}))
    uc = st.get_entity(VIVANT).get_component(UnitComponent)
    assert uc.received_damage_this_turn == {int(PROFIL_A): COMPTE_A, int(PROFIL_B): COMPTE_B}
    assert int(PROFIL_A) != int(PROFIL_B) and COMPTE_A != COMPTE_B, (
        "montage DEGENERE : une confusion cle/valeur ou une constante serait invisible")


def test_a2_les_cles_arrivent_en_CHAINES_et_sont_converties():
    """JSON n'a pas de cle entiere : le canal rend `{"13": 2}`. Le lecteur porte, lui, indexe par
    ENTIER (`ContainsKey(int(profil))`). Sans conversion, `received_damage_this_turn` serait un
    dict a cles STRING et TOUT gate rendrait faux -- degradation silencieuse et totale."""
    st = _state()
    SNAP._load_actor_statistics(st, _actor_stats({"profiles": {"13": 2}}))
    uc = st.get_entity(VIVANT).get_component(UnitComponent)
    assert list(uc.received_damage_this_turn.keys()) == [13]
    assert all(isinstance(k, int) for k in uc.received_damage_this_turn)


def test_a3_un_profil_a_ordinal_NEGATIF_passe():
    """`IdunBattle.Entities.Enum.DamageProfileType.None` vaut **-1**, et les ordinaux ne sont NI
    contigus NI tous positifs (0,1,3,4,...,25 -- `data/symbols/<build>/frida/enums.tsv`). Un seed
    qui filtrerait sur `>= 0` (reflexe naturel, et la garde qui s'applique bien aux VALEURS)
    perdrait cette cle-la."""
    st = _state()
    SNAP._load_actor_statistics(st, _actor_stats({"profiles": {"-1": 1}}))
    uc = st.get_entity(VIVANT).get_component(UnitComponent)
    assert uc.received_damage_this_turn == {int(DamageProfileType.None_): 1}
    assert int(DamageProfileType.None_) == -1, (
        "PREMISSE : si `None` cessait de valoir -1, cet etage garderait autre chose")


@pytest.mark.parametrize("champ", [..., None, {"profiles": None}, {"profiles": "?"}])
def test_a4_non_mesure_ne_pose_rien(champ):
    """TRI-ETAT. Les QUATRE formes de << pas mesure >> -- cle absente (bundle d'avant), champ
    `null`, `profiles: null` (canal refuse), `profiles` non-Mapping -- laissent le dict au `{}` de
    construction, SANS jamais l'ecraser."""
    st = _state()
    uc = st.get_entity(VIVANT).get_component(UnitComponent)
    uc.received_damage_this_turn = {int(PROFIL_A): COMPTE_A}      # ce que la simulation a grave
    SNAP._load_actor_statistics(st, _actor_stats(champ))
    assert uc.received_damage_this_turn == {int(PROFIL_A): COMPTE_A}, (
        "un `null` de PANNE ne doit jamais ECRASER une valeur que le moteur tient deja")


def test_a5_dictionnaire_vide_est_une_MESURE_et_ecrase():
    """`profiles: {}` = MESURE (l'unite n'a rien recu ce tour), l'etat MAJORITAIRE. Il DOIT ecraser
    -- c'est tout l'ecart avec `null`, et le confondre reviendrait a ne jamais pouvoir remettre le
    compteur a zero depuis le canal."""
    st = _state()
    uc = st.get_entity(VIVANT).get_component(UnitComponent)
    uc.received_damage_this_turn = {int(PROFIL_A): COMPTE_A}
    SNAP._load_actor_statistics(st, _actor_stats({"profiles": {}}))
    assert uc.received_damage_this_turn == {}


def test_a6_valeur_negative_ou_illisible_sautee():
    """GARDE `< 0` sur la VALEUR (jamais sur la cle, cf. A3) : c'est un compteur a increments
    `>= 1` (`TryAdd(profil, 1)` sinon `+1`), donc une valeur negative denonce une LECTURE invalide.
    Une cle non convertible est SAUTEE plutot que d'empoisonner un dict indexe par entier."""
    st = _state()
    SNAP._load_actor_statistics(st, _actor_stats(
        {"profiles": {"13": -1, "14": 2, "pas-un-entier": 3}}))
    uc = st.get_entity(VIVANT).get_component(UnitComponent)
    assert uc.received_damage_this_turn == {14: 2}


def test_a4bis_la_voie_DECISION_LIVE_lit_le_MEME_canal_avec_le_MEME_tri_etat():
    """#487-r2 -- L'ETAGE QUE CE FICHIER NE COUVRAIT PAS, et l'oubli etait STRUCTUREL.

    Les tests A1..A7 gardent la voie COMBAT : `actorStats` -> `snapshot._load_actor_statistics` ->
    `UnitComponent.received_damage_this_turn`, que `Scene.from_state` relaie en rejeu OFFLINE. Mais
    la face DECISION **LIVE** ne passe PAS par `load_state` : elle bâtit sa `Scene` par
    `scene.build_predictor` + `Scene.from_predictor_sctx`. MESURE du 2026-08-15
    (`probe_487r2_hellfyre_decision_live.py`) : capteur PARFAIT (`profiles: {"13": 1}` sur les trois
    ennemis armes, `{}` sur le temoin), natif qui propose `1088` avec un bucket `util = 3` -- et
    port a `util = None`, **zero candidat**. Le capteur et le seeder etaient hors de cause : c'est
    la Scene LIVE qui ne consommait pas le champ, alors que `build_predictor` tirait DEJA cet appel
    `actorStats` pour `totalAttacksMade`.

    Le tri-etat est le meme qu'en A4/A5, a un niveau pres, et c'est ce niveau qui est garde ici :
    la table ENTIERE vaut `None` quand AUCUNE ligne ne porte le champ, parce que
    `Scene.received_damage_profiles_by_id` est lui-meme tri-etat. Un `{}` s'y lirait
    << personne n'a pris de degat ce tour >> et ferait REFUSER l'ability (`0 < MIN_UTILITY = 1`) --
    degradation RESTRICTIVE, l'inverse de celle des tables voisines quand elles sont vides."""
    from engine.playbook.scene import _received_damage_profiles_from_actor_stats as lire

    # (1) MESURE : trois lignes, dont une a `profiles` VIDE -- une mesure PLEINE, pas une absence.
    tbl = lire({"units": [
        {"entityId": 81, "receiveDamageTypeThisTurn": {"profiles": {"13": 1}}},
        {"entityId": 87, "receiveDamageTypeThisTurn": {"profiles": {}}},
        {"entityId": 83, "receiveDamageTypeThisTurn": {"profiles": {"13": 1, "14": 2}}}]})
    assert tbl == {81: {13}, 87: set(), 83: {13, 14}}, tbl
    # Les CLES seules comptent : `HasTakenDamageOfDamageProfileThisTurn` est un `ContainsKey`, donc
    # le compte `2` du profil 14 ne doit apparaitre NULLE PART.
    assert all(isinstance(v, set) for v in tbl.values())

    # (2) NON MESURE, aux QUATRE formes de A4 -- la table ENTIERE doit valoir `None`.
    for ligne in ({"entityId": 81},                                    # cle absente (vieux bundle)
                  {"entityId": 81, "receiveDamageTypeThisTurn": None},
                  {"entityId": 81, "receiveDamageTypeThisTurn": {"profiles": None}},
                  {"entityId": 81, "receiveDamageTypeThisTurn": {"profiles": "?"}}):
        assert lire({"units": [ligne]}) is None, ligne
    assert lire(None) is None
    assert lire({}) is None
    assert lire({"units": []}) is None

    # (3) MIXTE : une seule ligne mesuree suffit a rendre une table -- et les NON mesurees en sont
    # ABSENTES (l'accesseur rendra `None` pour elles), jamais inscrites a `set()`.
    mixte = lire({"units": [{"entityId": 81, "receiveDamageTypeThisTurn": {"profiles": {"13": 1}}},
                            {"entityId": 99}]})
    assert mixte == {81: {13}} and 99 not in mixte, mixte


def test_a4ter_la_Scene_LIVE_rend_le_TRI_ETAT_bout_en_bout():
    """Le meme cran, mais au niveau de l'ACCESSEUR que le playbook appelle reellement.

    C'est le SEUL point ou l'on voit que `None` (non mesure) et `False` (mesure negative) ne se
    confondent pas : le playbook s'abstient sur le premier et compte `0` sur le second, et les deux
    produisent le meme << aucun candidat >> -- indistinguables de l'exterieur."""
    from engine.playbook.scene import Scene

    def _scene(tbl):
        """`Scene` MINIMALE -- les 11 champs obligatoires a leur valeur neutre. On ne passe PAS par
        un constructeur de commodite : ce test doit exercer l'accesseur, pas une fabrique."""
        return Scene(ctx_by_id={}, armor_by_id={}, shield_by_id={}, mult_by_id={}, ablvl_by_id={},
                     vis_by_id={}, units=[], hp_by_id={}, pos_by_id={}, team_by_id={},
                     eff_state=None, received_damage_profiles_by_id=tbl)

    mesuree = _scene({81: {13}, 87: set()})
    assert mesuree.has_taken_damage_of_profile_this_turn(81, 13) is True
    assert mesuree.has_taken_damage_of_profile_this_turn(87, 13) is False   # MESURE et negatif
    assert mesuree.has_taken_damage_of_profile_this_turn(99, 13) is None    # unite hors table
    # Table ENTIERE non mesuree -> `None` pour TOUT LE MONDE, y compris une unite connue.
    muette = _scene(None)
    assert muette.has_taken_damage_of_profile_this_turn(81, 13) is None


def test_a4quater_from_predictor_sctx_PROPAGE_le_None_et_ne_le_rabat_PAS_sur_un_dict_vide():
    """LE CRAN QUE LES DEUX PRECEDENTS NE COUVRENT PAS, et il garde la faute la PLUS PROBABLE.

    Dans `from_predictor_sctx`, ce champ est entoure d'une quinzaine de voisins ecrits
    `predictor.get(<nom>) or {}` -- pour eux un dict vide EST la bonne valeur neutre (l'accesseur
    rend alors `None` par ABSENCE DE CLE). Ici c'est l'inverse : le tri-etat est porte par la TABLE
    ENTIERE, donc un `or {}` << uniformisant >> transformerait une non-mesure en AFFIRMATION
    (<< personne n'a pris de degat ce tour >>) et ferait REFUSER `1088` -- degradation RESTRICTIVE,
    silencieuse, et invisible des deux tests ci-dessus qui ne regardent que le helper et
    l'accesseur.

    On lit donc le CODE SOURCE de la fonction : c'est le seul controle qui voie l'ecriture du site
    plutot que son effet dans un montage particulier."""
    import inspect
    from engine.playbook import scene as SC

    src = inspect.getsource(SC.Scene.from_predictor_sctx)
    lignes = [l.strip() for l in src.splitlines()
              if "received_damage_profiles_by_id=" in l]
    assert len(lignes) == 1, (
        "attendu UN seul site d'affectation dans `from_predictor_sctx`, vu %d : %s"
        % (len(lignes), lignes))
    assert "or {}" not in lignes[0] and "or dict()" not in lignes[0], (
        "REGRESSION : le site rabat la non-mesure sur un dict vide -- `%s`. Un `{}` s'y lit "
        "<< personne n'a pris de degat ce tour >>, ce qui fait REFUSER 1088 (utilite 0 < "
        "MIN_UTILITY 1) au lieu de s'abstenir. Cf. #487-r2." % lignes[0])
    # CONTRE-EPREUVE DU CONTROLE LUI-MEME : le motif cherche doit exister chez les VOISINS, sinon
    # l'assertion ci-dessus serait vraie pour une raison sans rapport (ex. `or {}` jamais utilise
    # dans cette fonction).
    assert sum(1 for l in src.splitlines() if "or {}" in l) >= 5, (
        "TEMOIN ABSENT : `from_predictor_sctx` ne porte plus le motif `or {}`, donc le controle "
        "ci-dessus ne discrimine plus rien")


def test_a7_mutant_seed_neutralise_fait_rater_l_etage(monkeypatch):
    """MUTATION ADVERSARIALE = l'arbre d'AVANT : le seed neutralise. Le dict doit rester au `{}` de
    construction meme quand le canal publie deux profils.

    Substitution en FORME B (`SNAP.<nom>`) : `_load_actor_statistics` lit l'attribut de module a
    chaque appel, donc le patch MORD (regle 'HISSER EN FORME B' du CLAUDE.md)."""
    monkeypatch.setattr(SNAP, "_seed_received_damage_types", lambda uc, champ: None)
    st = _state()
    SNAP._load_actor_statistics(st, _actor_stats(
        {"profiles": {str(int(PROFIL_A)): COMPTE_A}}))
    assert st.get_entity(VIVANT).get_component(UnitComponent).received_damage_this_turn == {}


def test_a8_les_sept_compteurs_voisins_restent_seedes():
    """NON-REGRESSION du foyer partage : ajouter un huitieme champ NON scalaire ne doit rien
    changer aux sept compteurs que la meme boucle pose (#340-r1, #509, #926, #545-r1, #287-r5-r2)."""
    st = _state()
    SNAP._load_actor_statistics(st, _actor_stats({"profiles": {"13": 1}})
                                | {"units": [{"entityId": VIVANT,
                                              "receiveDamageTypeThisTurn": {"profiles": {"13": 1}},
                                              "tilesMovedThisTurn": 5, "totalAttacksMade": 11,
                                              "attacksMadeThisTurn": 3,
                                              "attacksReceivedThisTurn": 7}]})
    uc = st.get_entity(VIVANT).get_component(UnitComponent)
    assert (uc.tiles_moved_this_turn, uc.total_attacks_made,
            uc.attacks_made_this_turn, uc.times_attacked_this_turn) == (5, 11, 3, 7)
    assert uc.received_damage_this_turn == {13: 1}


# =================================================================================================
# ETAGE B -- LES DEUX CAPTEURS SONT ECRITS (le DEPLOIEMENT attend une fenetre)
# =================================================================================================

HOOK = RACINE / "frida" / "hooks" / "features" / "ai-step" / "rpc-snapshot.ts"
MOD_RDT = RACINE / "frida" / "hooks" / "game" / "receive-damage-types.ts"
MOD_WPN = RACINE / "frida" / "hooks" / "game" / "weapons.ts"


def _code_seul(src: str) -> str:
    """Le source PRIVE de ses commentaires.

    ⚠ CE DEPOUILLAGE N'EST PAS UNE COMMODITE, c'est ce qui separe une garde de CODE d'une garde de
    PROSE -- et il a ete ajoute parce que les deux etages ci-dessous ont d'abord rougi SUR MES
    PROPRES COMMENTAIRES : `receive-damage-types.ts` EXPLIQUE pourquoi il n'utilise pas
    `fieldOffsetOr`, et `weapons.ts` EXPLIQUE pourquoi il n'invoque rien (le piege #175). Une
    garde par simple `in src` accuse donc exactement les modules qui documentent le mieux ce
    qu'ils s'interdisent -- un cliquet qui punit la documentation se fait retirer. Meme discipline
    que `migrate_va_to_symbol.py`, qui ne reecrit QUE hors des littéraux executables.

    Depouillage volontairement SIMPLE (`/* */` et `//`) : il n'a pas a comprendre TypeScript, il
    a a ne pas voir la prose. Les chaines de caracteres, elles, RESTENT -- un repli ecrit dans une
    chaine reste du code."""
    out, i, n = [], 0, len(src)
    while i < n:
        if src.startswith("/*", i):
            fin = src.find("*/", i + 2)
            i = n if fin < 0 else fin + 2
        elif src.startswith("//", i):
            fin = src.find("\n", i)
            i = n if fin < 0 else fin
        else:
            out.append(src[i])
            i += 1
    return "".join(out)


def test_b1_actorstats_publie_les_profils_recus():
    """#487-r2 : le RPC `actorStats` publie `receiveDamageTypeThisTurn` PAR UNITE, plus le layout
    RESOLU au niveau reponse -- sans ce dernier, un `profiles: null` generalise accuserait la
    bataille au lieu de la resolution."""
    src = HOOK.read_text(encoding="utf-8")
    assert "receiveDamageTypeThisTurn: readReceiveDamageTypes(cp, rdt.channel)" in src
    assert "receiveDamageLayout:" in src
    assert "receiveDamageEnum:" in src


def test_b2_combatsnapshot_publie_les_armes():
    """#419 : le RPC `combatSnapshot` publie `weapons` PAR UNITE, plus le layout resolu."""
    src = HOOK.read_text(encoding="utf-8")
    assert "weapons: readEntityWeapons(e)" in src
    assert "weaponsLayout:" in src
    assert "weaponProfileEnum:" in src


def test_b3_aucune_invocation_native_dans_le_canal_armes():
    """#175 : un SEUL appel natif mal choisi depuis `combatSnapshot` rend toute pose d'effet
    ulterieure sur le runner un no-op SILENCIEUX. Le canal armes est une lecture MEMOIRE PURE, et
    ca doit le rester -- `HasRangedWeapon` se recalcule entierement depuis ce qui est publie."""
    code = _code_seul(MOD_WPN.read_text(encoding="utf-8"))
    assert "invokeMethod" not in code
    assert "invokeBool" not in code
    # CONTRE-EPREUVE D'ANTI-VACUITE : le depouillage ne doit pas avoir tout mange. Sans elle,
    # un `_code_seul` casse rendrait cet etage VERT sur du vide.
    assert "export function readWeapons" in code


# =================================================================================================
# ETAGE C -- LES NOMS MESURES, FIGES (le cran qui a motive la tranche)
# =================================================================================================

def test_c1_le_champ_des_profils_porte_son_nom_MESURE():
    """`ReceiveDamageTypeThisTurn`, et NON `ReceivedDamageThisTurn` que nomme la fiche #487-r2 (ni
    `ResetReceivedDamageThisTurn`, le nom de la METHODE qui le vide). Mesure au RPC `classFields`,
    session 93. Le nom de la fiche ne doit apparaitre dans AUCUNE resolution."""
    src = MOD_RDT.read_text(encoding="utf-8")
    assert 'export const RDT_FIELD = "ReceiveDamageTypeThisTurn";' in src


def test_c2_le_champ_des_armes_porte_ses_CHEVRONS():
    """`<Weapons>k__BackingField` : c'est un backing field d'auto-property, et chercher `Weapons`
    ne resout RIEN. Mesure au RPC `classFields`, session 93."""
    src = MOD_WPN.read_text(encoding="utf-8")
    assert 'export const WEAPONS_FIELD = "<Weapons>k__BackingField";' in src


def test_c3_aucun_repli_litteral_dans_les_deux_resolutions():
    """Les deux canaux resolvent PAR NOM et REFUSENT quand le nom manque -- jamais un
    `fieldOffsetOr(..., 0x80)` qui se replierait en silence sur le litteral decompile. Les offsets
    decompiles n'existent QUE comme temoins de `drift`, et le seul usage autorise du nom de la
    constante est cette comparaison-la."""
    for mod in (MOD_RDT, MOD_WPN):
        code = _code_seul(mod.read_text(encoding="utf-8"))
        assert "resolve" in code, "%s : depouillage casse, l'etage serait VACANT" % mod.name
        assert "fieldOffsetOr" not in code, (
            "%s : `fieldOffsetOr` porte un repli litteral -- c'est exactement ce que la mesure "
            "de nom interdit ici" % mod.name)
        # Les constantes `DECOMPILED_*` n'ont le droit d'apparaitre que dans leur DECLARATION,
        # dans une COMPARAISON de derive (`!==`) ou dans le message de `drift` -- jamais dans un
        # `.add(...)`, qui serait une lecture a l'offset devine.
        for ligne in code.splitlines():
            if "DECOMPILED_" not in ligne:
                continue
            autorise = ("const " in ligne or "!==" in ligne or "drift.push" in ligne
                        or ".toString(16)" in ligne)
            assert autorise, (
                "%s : offset decompile hors declaration/derive -> %s" % (mod.name, ligne.strip()))
            assert ".add(" not in ligne, (
                "%s : LECTURE a un offset decompile -> %s" % (mod.name, ligne.strip()))


def test_c4_le_seuil_melee_est_le_LITTERAL_natif():
    """`IdunShared.Battle.WeaponProfile$$get_IsMelee` = `!Range.HasValue || Range.Value < 2`. Une
    arme de portee **1 est MELEE**, et aucune arme du gameconfig n'a `Range == 1` : une faute de
    seuil serait donc INVISIBLE en live. Le litteral est fige ici et exerce sur memoire simulee par
    `frida/tools/probe-10008-canaux-du-foyer.ts`."""
    src = MOD_WPN.read_text(encoding="utf-8")
    assert "const MELEE_RANGE_MAX_EXCLUSIVE = 2;" in src
    assert "< MELEE_RANGE_MAX_EXCLUSIVE" in src
