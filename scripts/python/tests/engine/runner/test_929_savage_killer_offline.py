"""#929 -- ce que le LIVE ne peut PAS garder sur `SavageKiller` : les CONSTANTES lues au decompile
et au gameconfig, et le verdict DEAD CODE de `$$CreateValidActiveAbilityTrigger`.

Ce fichier existe parce que la passe live a un MUTANT INERTE, et qu'il est nomme plutot que tu :
muter `DAMAGE_PROFILE` de `Power` en `Physical` NE FAIT PAS ROUGIR `test_929_savage_killer_live.py`.
Cause MESUREE, pas supposee -- deux etages s'additionnent :
  * le montage live passe `--hp-target 999999`, qui met `Armor`/`FixedArmor` a **0**
    (`references/runner.md` Sec.3) : l'etage PERCE-ARMURE du profil n'a alors rien a percer, donc
    `Power` (pierce 40) et `Physical` (pierce 0) rendent le MEME degat sur le caster ;
  * sur le grot de la face A, les deux profils TUENT -> les PV sont clampes a `0` des deux cotes.
Le profil ne peut donc pas etre garde par un delta de PV sur ce montage. Il est garde ICI, contre sa
SOURCE (`AbilityConfiguration.GetDamageProfile()` = `constants.damageProfile` du gameconfig), ce qui
est le cran juste : c'est cette lecture-la que le port doit reproduire.

ASCII only.
"""
from __future__ import annotations

import os
import struct
from pathlib import Path

import pytest

import gameconfig as GC
from engine.entities.active_ability_type import ActiveAbilityType
from engine.entities.damage_profile_type import DamageProfileType
from engine.entities.triggered_ability_type import TriggeredAbilityType
from engine.runner.operations.triggers.loki import savage_killer as SK
from engine.runner.operations.triggers.loki import fuelled_by_fury as FBF

DECLENCHEUR = {
    "chemins": (
        "scripts/python/engine/runner/operations/triggers/loki/savage_killer.py",
        # le foyer PARTAGE dont ce fichier garde le seuil ET le defaut (regression #929)
        "scripts/python/engine/runner/operations/triggers/loki/fuelled_by_fury.py",
        # les trois mirrors d'enum dont il fige les ordinaux et la DISJONCTION des espaces
        "scripts/python/engine/entities/triggered_ability_type.py",
        "scripts/python/engine/entities/active_ability_type.py",
        "scripts/python/engine/entities/damage_profile_type.py",
        # l'enum des evenements, dont il FIGE les quatre abonnements
        "scripts/python/engine/dsl/event_trigger_type.py",
        # les deux lecteurs de gameconfig qu'il confronte au port
        "scripts/python/gameconfig.py", "scripts/python/unit_map.py",
        # ELARGI par #937 : `gameconfig.ability_description` LIT `data/i2_en.json` (entree
        # VERSIONNEE), lecture invisible du graphe d'imports. Rendue visible en gravant
        # l'empreinte #457 de ce fichier, qui a fait rougir `probe_486r15` en DECLARE TROP ETROIT.
        "data/i2_en.json",
    ),
    # Il LIT `GameAssembly.dll` (verdict DEAD CODE aux octets) et le gameconfig d'`AppData`, tous
    # deux HORS de l'arbre : un changement de build peut le faire basculer sans qu'un fichier du
    # depot bouge. Le foyer ajoute `data/symbols/**` de lui-meme.
    "build": True,
    "toujours": False,
    "raison": "Il grave ce que le live ne peut PAS garder : le profil et le nombre de coups lus au "
              "gameconfig (le mutant `Power -> Physical` est INERTE live, armure a 0), la "
              "disjonction des DEUX espaces d'enum du call-site, le seuil de la branche `pre` du "
              "foyer partage, et le verdict DEAD CODE de `$$CreateValidActiveAbilityTrigger` lu "
              "aux octets du binaire.",
}

ROOT = Path(__file__).resolve().parents[4].parent          # racine du depot
IMAGE_BASE = 0x180000000                                   # base de l'image PE de GameAssembly.dll


# ----------------------------------------------------------------------------- les CONSTANTES
def test_le_profil_de_degat_est_celui_du_gameconfig():
    """`AbilityConfiguration.GetDamageProfile()` du `CreateBehaviour` natif lit
    `constants.damageProfile` de l'ability. Le port ne doit pas le DEDUIRE du nom de l'ability ni
    du fait qu'Ulf frappe en Power au normal -- il doit lire CETTE cle."""
    cfg = GC.ability("SavageKiller") or {}
    attendu = ((cfg.get("constants") or {}).get("damageProfile"))
    assert attendu == DamageProfileType.Power.name, (
        f"le gameconfig a change : `SavageKiller.constants.damageProfile` = {attendu!r} "
        "(le port et la RE disent Power) -- re-lire `$$CreateBehaviour` avant de suivre")
    assert SK.DAMAGE_PROFILE == attendu, (
        f"DAMAGE_PROFILE du port = {SK.DAMAGE_PROFILE!r} != gameconfig {attendu!r}")


def test_le_nombre_de_coups_est_la_constante_nrOfHits():
    """`AbilityConfiguration.GetNumberConstant(AbilityConstantType.nrOfHits = 0x2f)` -- le natif
    passe une CONSTANTE `System.Int32` (surcharge `AttackWithAttackDamage` resolue a l'adresse du
    `call`), pas une formule. Le live compte 5 coups ; cette garde dit d'ou vient le 5."""
    cfg = GC.ability("SavageKiller") or {}
    attendu = int(((cfg.get("constants") or {}).get("nrOfHits")))
    assert attendu == 5, f"`SavageKiller.constants.nrOfHits` = {attendu} (la RE et le live disent 5)"


def test_l_attaque_est_melee_par_la_config_pas_par_le_nom():
    """`BaseTriggeredAbility$$GetAttackRangeType` rend `config@+0x20` : `SavageKiller` n'override
    PAS ce slot, donc `is_melee` du port doit venir du gameconfig."""
    cfg = GC.ability("SavageKiller") or {}
    assert cfg.get("attackRangeType") == "Melee", (
        f"`SavageKiller.attackRangeType` = {cfg.get('attackRangeType')!r} -- le port pose "
        "`is_melee=True`, qui ne serait plus fidele")


def test_les_deux_ids_vivent_dans_DEUX_espaces_d_enum_differents():
    """LE PIEGE de cette ability, et il est SILENCIEUX EN ORDINAL.

    `CreateBehaviour` appelle `AbilityOrEffect$$op_Implicit(triggeredAbility: TriggeredAbilityType)`
    avec `this.Id`, tandis que `CreateCharacterActiveAbilityTrigger` appelle
    `$$op_Implicit(activeAbility: **ActiveAbilityType**)` avec l'immediat `0x467`. Les deux
    surcharges ont ete tranchees a l'ADRESSE de la cible d'appel, pas au pseudo-C (qui efface les
    immediats). Ce test grave les deux ordinaux ET le fait qu'ils nomment autre chose dans l'autre
    espace : c'est la seule facon de voir la confusion, puisqu'elle ne leve rien."""
    assert int(TriggeredAbilityType.SavageKiller) == 0x487 == 1159
    assert int(SK.SAVAGE_KILLER) == int(TriggeredAbilityType.SavageKiller)
    assert int(ActiveAbilityType.ArmouredMight_Move) == 0x467 == 1127
    assert SK._ARMOURED_MIGHT_MOVE == int(ActiveAbilityType.ArmouredMight_Move)
    # les MEMES ordinaux dans l'AUTRE espace nomment autre chose -> lire le mauvais enum aurait
    # ecrit un id parfaitement valide et parfaitement faux.
    assert TriggeredAbilityType(1127).name != "ArmouredMight_Move", (
        "TriggeredAbilityType 1127 nomme desormais ArmouredMight_Move : la garde ne discrimine "
        "plus les deux espaces, il faut re-lire la surcharge `op_Implicit` du call-site")
    assert ActiveAbilityType(1159).name != "SavageKiller", (
        "ActiveAbilityType 1159 nomme desormais SavageKiller : meme perte de discrimination")


def test_ArmouredMight_n_a_aucun_porteur_et_c_est_pourquoi_le_terme_est_inerte():
    """Le conjoint `NOT TriggeringAbilityIs(ArmouredMight_Move)` est porte mais INERTE. La raison
    ecrite dans le module est une MESURE, pas une intuition -- elle est re-derivee ici : aucune
    unite du gameconfig n'expose `ArmouredMight` (ni active, ni passive), et `ArmouredMight_Move`
    n'a meme pas d'entree d'ability. Si l'un des deux change, ce test rougit et le residu doit
    etre reouvert (le canal `ev.triggering_effect`, lui, reste non threade sur ce vecteur)."""
    import unit_map
    porteurs = [k["id"] for k in unit_map.all_kits()
                if "ArmouredMight" in (k.get("abilities_all") or [])]
    assert porteurs == [], (
        f"`ArmouredMight` a maintenant des porteurs {porteurs} : le conjoint "
        "`NOT TriggeringAbilityIs(ArmouredMight_Move)` peut devenir observable -> "
        "cabler `ev.triggering_effect` sur le vecteur `On(PreUnitAbility)` avant de continuer")


# ------------------------------------------------------- le foyer PARTAGE (regression #929)
def test_les_quatre_evenements_natifs_sont_abonnes():
    """GARDE STRUCTURELLE : le `CreateTrigger` natif est une union de QUATRE disjonctions
    (`UnitAfterMove`, `UnitDisplaced`, `UnitAdded`, `UnitBecameTargetable`) plus la face B
    `PreUnitAbility` -- soit CINQ evenements, tous abonnes depuis #981.

    ⚠ CE TEST A CHANGE D'ETAT, ET C'EST SON ROLE. Il figeait quatre abonnements et interdisait
    explicitement le cinquieme : `UnitBecameTargetable` etait INATTEIGNABLE faute d'emetteur, donc
    l'abonner aurait materialise un predicat qu'aucun montage ne pouvait exercer (port speculatif).
    Les DEUX conditions qu'il posait sont desormais remplies : le vecteur existe depuis #936
    (`move_death.unit_became_targetable_triggers`, emis par `remove_effect_instance` sous le gate de
    type `UntargetableEffect`), et le predicat `NOT (PreviousTile | TurnStartTile)` est porte
    (`SavageKillerAbility._has_moved`). Residu #929-r1 FERME.

    Il vit ICI et pas dans le fichier `_live.py` parce qu'il est OFFLINE PUR, et qu'un test offline
    heberge dans un `_live.py` est invisible des DEUX gardes du parc
    (`probe_547_ledger_sans_verdict_non_vert.py`)."""
    from engine.dsl.event_trigger_type import EventTriggerType
    abonnes = ({int(SK.SavageKillerAbility.event_id)}
               | {int(e) for e in SK.SavageKillerAbility.event_ids})
    assert abonnes == {int(EventTriggerType.PreUnitAbility),
                       int(EventTriggerType.UnitAfterMove),
                       int(EventTriggerType.UnitDisplaced),
                       int(EventTriggerType.UnitAdded),
                       int(EventTriggerType.UnitBecameTargetable)}, (
        f"abonnements = {sorted(abonnes)} ; le decompile en veut exactement ces cinq")


def test_le_predicat_not_moved_ne_gate_QUE_la_quatrieme_disjonction():
    """`NOT (AmountIsGreaterThanZero(PreviousTile) | AmountIsGreaterThanZero(TurnStartTile))` est un
    conjoint de la SEULE branche `On(0x3b)` au decompile. L'appliquer aux trois autres eteindrait
    `On(UnitAfterMove)` a coup sur (une unite qui vient de bouger a forcement une `PreviousTile`) --
    c'est-a-dire exactement la branche que l'i2 nomme en premier."""
    import inspect
    assert callable(getattr(SK.SavageKillerAbility, "_has_moved", None)), \
        "le predicat `NOT moved` de la 4e disjonction n'est pas porte"
    src = inspect.getsource(SK.SavageKillerAbility.matches)
    assert "_ON_UNIT_BECAME_TARGETABLE" in src and "_has_moved" in src, \
        "`_has_moved` n'est pas branche dans `matches`"
    # le gate est CONDITIONNE a l'event : la garde tombe si quelqu'un le remonte en conjoint commun
    assert src.index("_ON_UNIT_BECAME_TARGETABLE") < src.index("_has_moved"), \
        "`_has_moved` doit etre garde par le test d'evenement, pas applique aux quatre branches"


def test_not_moved_lit_les_DEUX_substrats_natifs():
    """Les deux termes de la disjonction `moved` ont chacun leur mirror, et le port doit lire les
    DEUX : `PreviousTileSelector$$Select` (`PositionComponent+0x88`) et
    `CurrentTurnStartTileSelector$$Select` (`UnitComponent+0x18c`). N'en lire qu'un laisserait
    passer la moitie des summons qui ont bouge."""
    import inspect
    src = inspect.getsource(SK.SavageKillerAbility._has_moved)
    assert "_previous_tiles" in src, "le terme `PreviousTile` n'est pas lu"
    assert "current_turn_start_tile" in src, "le terme `TurnStartTile` n'est pas lu"


def test_le_seuil_pre_et_le_defaut_du_foyer_partage():
    """`IsActiveAbilityCountedAsUsed(isPreAbilityTrigger)` : le decompile ne choisit QUE le seuil
    (`DSLFormulas@+0x18 = Direct(0)` si `true`, `+0x20 = Direct(1)` sinon), jamais la classe du
    comparateur. `SavageKiller` a AJOUTE la branche `true` a un foyer qui n'en portait qu'une ; ce
    test garde que ses DEUX consommateurs historiques (`FuelledByFury_ExtraDamage`,
    `TalonsOfTheEmperor_UsedAbilities`, tous deux `false`) ne changent pas de seuil."""
    assert FBF.COUNTED_AS_USED_THRESHOLD == 1
    assert FBF.COUNTED_AS_USED_THRESHOLD_PRE == 0

    class _S:
        def __init__(self, n):
            self.n = n

        def total_active_ability_used(self, _uid, _ab):
            return self.n

    once = sorted(FBF.ABILITY_COUNTED_ONCE_PER_BATTLE)[0]
    # seuil STRICT : la branche `false` bascule a 2, la branche `true` des 1.
    assert FBF.is_active_ability_counted_as_used(_S(1), 1, once) is True
    assert FBF.is_active_ability_counted_as_used(_S(2), 1, once) is False
    assert FBF.is_active_ability_counted_as_used(_S(1), 1, once,
                                                 is_pre_ability_trigger=True) is False
    assert FBF.is_active_ability_counted_as_used(_S(0), 1, once,
                                                 is_pre_ability_trigger=True) is True


# ------------------------------------------------------------------ le verdict DEAD CODE
def _build_hash() -> str | None:
    """Le build dont on a A LA FOIS la table de symboles VERSIONNEE et la DLL INSTALLEE.

    `data/symbols/` porte plusieurs builds ; prendre le premier par ordre alphabetique rendrait un
    hash PERIME (mesure : `gqfc5mff6c` sort avant `rnca9r7q6c`) et ferait skipper la garde alors
    que le binaire est la. Le discriminant est la CONCORDANCE des deux, exactement la verification
    que le CLAUDE.md exige avant toute analyse offline."""
    d = ROOT / "data" / "symbols"
    local = os.environ.get("LOCALAPPDATA")
    for p in sorted(d.iterdir()) if d.exists() else []:
        if not ((p / "ghidra" / "functions.tsv").exists() and (p / "BUILD").exists()):
            continue
        if (Path(local or "") / "tacticus" / "games" / p.name / "GameAssembly.dll").exists():
            return p.name
    return None


def _va_of(build: str, symbole: str) -> int | None:
    tsv = ROOT / "data" / "symbols" / build / "ghidra" / "functions.tsv"
    for line in tsv.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("#") or "\t" not in line:
            continue
        va, name = line.split("\t", 1)
        if name.strip() == symbole:
            return int(va, 16)
    return None


def _read_at_va(dll: Path, va: int, size: int) -> bytes:
    """Lit `size` octets a la VA `va` en traduisant par les SECTIONS du PE (mini-parseur : e_lfanew,
    NumberOfSections, SizeOfOptionalHeader, puis chaque IMAGE_SECTION_HEADER de 40 octets). La RVA
    est calculee EN CODE (`va - IMAGE_BASE`), jamais a la main."""
    rva = va - IMAGE_BASE
    with dll.open("rb") as f:
        head = f.read(0x400)
        e_lfanew = struct.unpack_from("<I", head, 0x3C)[0]
        nsec = struct.unpack_from("<H", head, e_lfanew + 6)[0]
        opt_size = struct.unpack_from("<H", head, e_lfanew + 20)[0]
        sec_off = e_lfanew + 24 + opt_size
        f.seek(sec_off)
        secs = f.read(40 * nsec)
        for i in range(nsec):
            base = 40 * i
            vsize, vaddr, rawsize, rawptr = struct.unpack_from("<IIII", secs, base + 8)
            if vaddr <= rva < vaddr + max(vsize, rawsize):
                f.seek(rawptr + (rva - vaddr))
                return f.read(size)
    return b""


def _branch_targets(blob: bytes, va: int, opcode: int) -> list[int]:
    """VAs cibles des branchements `rel32` d'un opcode donne -- calcul EN CODE.

    `0xE8` = `call rel32`, `0xE9` = `jmp rel32`. Les DEUX sont necessaires : le troisieme
    appel du `CreateTrigger` natif (`AbilityTrigger$$op_BitwiseOr`) est un **TAIL CALL**, donc un
    `jmp`, et un recensement limite aux `call` en compte 2 la ou le decompile en montre 3 -- ce qui
    ferait passer un seuil << au moins 3 >> pour un layout casse."""
    out = []
    i = 0
    while i + 5 <= len(blob):
        if blob[i] == opcode:
            rel = struct.unpack_from("<i", blob, i + 1)[0]
            out.append(va + i + 5 + rel)
            i += 5
        else:
            i += 1
    return out


def test_create_valid_active_ability_trigger_est_dead_code():
    """VERDICT : `...SavageKillerAbility$$CreateValidActiveAbilityTrigger` n'est appelee NULLE PART.

    Grave AUX OCTETS : `$$CreateTrigger` fait exactement DEUX `call`, vers
    `$$CreateSummonMoveTrigger` et `$$CreateCharacterActiveAbilityTrigger` (plus l'`op_BitwiseOr`),
    et AUCUN vers `$$CreateValidActiveAbilityTrigger`. C'est le cran que `list_xrefs` donne (2 refs,
    toutes DATA, zero `UNCONDITIONAL_CALL`) rejoue sans ghidra -- et il est LOCAL, donc il ne
    depend pas d'un index externe.

    Corollaire deja verifie a la RE et non rejouable ici : `search_symbols_by_name` sur ce nom rend
    UN SEUL symbole dans tout le binaire, donc aucune methode homonyme d'une base ou d'une interface
    ne peut l'atteindre par un slot virtuel.

    SKIP (et un seul, ce fichier a d'autres tests) si le binaire du build attendu n'est pas
    installe : ce n'est pas une entree versionnee."""
    build = _build_hash()
    if build is None:
        pytest.skip("aucune table `data/symbols/<build>/ghidra/functions.tsv`")
    local = os.environ.get("LOCALAPPDATA")
    dll = Path(local or "") / "tacticus" / "games" / build / "GameAssembly.dll"
    if not dll.exists():
        pytest.skip(f"GameAssembly.dll du build {build} non installee ({dll})")
    pref = "IdunBattleLogic.Entities.Abilities.Triggered.Loki.SavageKillerAbility$$"
    va_trigger = _va_of(build, pref + "CreateTrigger")
    va_summon = _va_of(build, pref + "CreateSummonMoveTrigger")
    va_char = _va_of(build, pref + "CreateCharacterActiveAbilityTrigger")
    va_dead = _va_of(build, pref + "CreateValidActiveAbilityTrigger")
    assert None not in (va_trigger, va_summon, va_char, va_dead), (
        "un des quatre symboles a disparu de la table du build -- re-faire la RE avant de "
        f"conclure (trigger={va_trigger} summon={va_summon} char={va_char} dead={va_dead})")
    # `$$CreateTrigger` est court (il tient largement en 0x40 octets, `$$CreateValidActive...` le
    # suit immediatement dans la table) : on lit une fenetre bornee par le symbole SUIVANT.
    # Fenetre bornee par le symbole SUIVANT dans le binaire -- `$$CreateValidActiveAbilityTrigger`
    # suit immediatement `$$CreateTrigger`. La borne est ASSERTEE : si le layout change et que la
    # fenetre devient trop courte, `cibles` serait VIDE et l'assertion « `va_dead` absent »
    # passerait pour une raison VACUE. C'est exactement le faux vert que la contre-epreuve a
    # revele -- on le ferme en assertionnant le NON-VIDE avant de conclure de l'absence.
    fenetre = va_dead - va_trigger
    assert 0x20 <= fenetre <= 0x200, (
        f"fenetre de lecture aberrante ({fenetre:#x}) : `$$CreateValidActiveAbilityTrigger` ne "
        "suit plus `$$CreateTrigger` -- re-deriver les bornes avant de conclure")
    blob = _read_at_va(dll, va_trigger, fenetre)
    assert blob, "lecture PE impossible (traduction RVA -> offset fichier)"
    calls = _branch_targets(blob, va_trigger, 0xE8)
    tails = _branch_targets(blob, va_trigger, 0xE9)
    assert len(calls) == 2, (
        f"`$$CreateTrigger` doit faire EXACTEMENT deux `call` (ses deux helpers ; le troisieme "
        f"appel du decompile, `op_BitwiseOr`, part en TAIL CALL). Lu : {list(map(hex, calls))} -- "
        "une liste trop courte rendrait l'absence de `va_dead` VACUE")
    assert len(tails) == 1, (
        f"tail call `op_BitwiseOr` introuvable : {list(map(hex, tails))}")
    assert va_summon in calls and va_char in calls, (
        f"`$$CreateTrigger` n'appelle plus ses deux helpers vivants : calls={list(map(hex, calls))}")
    assert va_dead not in calls and va_dead not in tails, (
        "`$$CreateValidActiveAbilityTrigger` EST atteinte par `$$CreateTrigger` : le verdict "
        "DEAD CODE du port est FAUX, il faut porter ce conjoint")
