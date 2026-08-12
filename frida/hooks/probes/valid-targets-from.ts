/** `#975-r1` — CAPTEUR : `GetValidTargets` depuis une position ARBITRAIRE.
 *
 *  ⚠ **INERTE tant que le bundle n'est pas rebuilde + reinjecte** (geste orchestrateur). Le
 *  `register` n'arme AUCUN hook : il n'expose qu'un RPC, et ce RPC n'INVOQUE que des QUERIES
 *  (aucune Operation, aucun mutateur ECS).
 *
 *  ## Le trou que ce capteur ferme
 *
 *  Le gate `HasEnemyInRange` de `1087 ExemplarOfTheKauyon` est, LU :
 *
 *      // IdunBattle.AI.Playbook.Loki.ExemplarOfTheKauyonPlaybook$$HasEnemyInRange
 *      UnitPosition..ctor(&pos, <la TUILE VISEE>);
 *      vt = BasePlaybook$$GetEligibleTargetsForNormalAttack(this, caster, pos);
 *      return vt.<Targets>.<Count> > 0;
 *
 *  et `GetEligibleTargetsForNormalAttack` est
 *  `<IBattleQuery slot 0x42 = 66 GetValidTargets>(caster, position, GetNormalAttackType(caster))`.
 *
 *  **Aucun RPC n'expose `GetValidTargets` depuis une position ARBITRAIRE** : `abilityTargets` ne
 *  repond que pour la position COURANTE (`fromHere`) et pour l'UNION sur les tuiles de MOVE
 *  (`targets`), et `castFromTiles` balaie `GetMovableTilesFor`. Or `1087` est un TELEPORT
 *  (`RANGE_WHOLE_BOARD`) dont les destinations sont massivement HORS de l'univers movable. Le port
 *  n'est donc confronte qu'en **borne SUPERIEURE**.
 *
 *  ## Comment on construit une position arbitraire — et pourquoi ainsi
 *
 *  `IdunBattle.Core.UnitPosition` est un `System.ValueType` de **8 octets utiles** (24 boxee moins
 *  le header IL2CPP de 16), c'est-a-dire **UN SEUL POINTEUR** — LU dans `frida/classes.tsv`, et
 *  confirme par `IdunBattle.Core.UnitPosition$$get_MainTile`, dont le corps est
 *  `if (*this != 0 && (*this).Count != 0) return (*this)[0]`. Le champ est donc la LISTE des
 *  tuiles occupees, pas un couple `(q, r)`.
 *
 *  On appelle le ctor NOMME `IdunBattle.Core.UnitPosition$$.ctor(this, tile)`, dont le corps est
 *  `list = new List<Tile>(); if (tile != null) list.Add(tile); *this = list;`. C'est **exactement**
 *  ce que fait `ExemplarOfTheKauyonPlaybook$$HasEnemyInRange`.
 *
 *  ⚠ **On ne MUTE jamais la liste rendue par `EntityExtensions$$GetTiles`.** C'etait la voie
 *  spontanee (elle rend une `List` FRAICHE — `new List<T>(IterateTiles(...))` — donc techniquement
 *  mutable sans risque), mais elle demande d'ecrire un pointeur d'objet dans un tableau manage,
 *  et surtout elle FABRIQUE une structure au lieu d'appeler la fonction que le jeu appelle
 *  lui-meme. Le ctor est la voie nommee ; on la prend.
 *
 *  ## Le CONTROLE, sans lequel la mesure ne vaut rien
 *
 *  `IdunBattle.Core.Services.AttackQuery$$GetValidTargets` (slot 6) porte **TROIS portes qui
 *  rendent un ensemble VIDE sans la moindre erreur** (LU) : `abilityType == 0`, l'ability absente
 *  de l'`ActiveAbilityComponent` du caster (celle-la journalise), et
 *  `AttackQuery$$IsAlreadyUsedThisTurn`. Un `count == 0` peut donc venir d'un COOLDOWN, pas de la
 *  geometrie — et c'est precisement l'erreur qu'un capteur naif ferait commettre.
 *
 *  Le RPC rend donc TOUJOURS, a cote des positions demandees, la mesure depuis la position
 *  COURANTE de l'unite (`control.fromCurrent`), obtenue par le MEME chemin. Elle vaut double :
 *  elle valide la construction de l'`UnitPosition` (elle doit reproduire `abilityTargets.fromHere`)
 *  ET elle separe « rien a portee ici » de « l'ability ne peut pas etre castee du tout ».
 *
 *  ## Discipline
 *
 *  Read-only : `GetValidTargets` est une QUERY (elle alloue du manage, elle ne mute pas l'etat).
 *  Aucun `Interceptor`, aucun heap scan. La liste construite est gcRoot-ee le temps de l'appel —
 *  `GetValidTargets` alloue, donc un GC peut survenir entre deux positions.
 */
import {
    class_get_name, findClassAnywhere, findCtorByParamCount, findMethodByParamClasses,
    findMethodByParamCount, s,
} from "../il2cpp/helpers.js";
import { invokeMethod } from "../il2cpp/invoke.js";
import { gcRoot } from "../il2cpp/gc-root.js";
import { queueOnMainThread } from "../runtime/queue.js";
import { Ctx } from "../controller.js";
import { runnerOff } from "../game/runner.js";
import { getRunner } from "../game/runner-registry.js";
import { state } from "../game/state.js";
import { EntityType, forEachEntity, readBattleStatus } from "../game/match-state.js";
import {
    battleInServicesOff, readTileCoord, servicesOff,
} from "../features/ai-step/internals.js";

/** Resout (runner, state, BattleQuery) — MEME chaine que `abilityTargets`, pas une variante.
 *  Tri-etat : toute impossibilite rend un `error` NOMME, jamais un pointeur nul silencieux. */
function resoudreRunner(runnerId?: number): {
    ok: boolean; error?: string; label?: string;
    runner?: NativePointer; statePtr?: NativePointer; battleQuery?: NativePointer;
} {
    let runner: NativePointer; let label: string;
    if (typeof runnerId === "number") {
        try { runner = getRunner(runnerId).runner; }
        catch (e) { return { ok: false, error: (e as Error).message }; }
        label = "build#" + runnerId;
    } else if (state.liveRunner) {
        runner = state.liveRunner; label = "live";
    } else {
        return { ok: false, error: "no runner — pass runnerId" };
    }
    if (runner.isNull()) return { ok: false, error: label + " runner null" };
    const statePtr = runner.add(runnerOff.state).readPointer();
    if (statePtr.isNull()) return { ok: false, error: "state null" };
    const status = readBattleStatus(statePtr);
    if (status.stage !== 1) {
        return { ok: false, error: "stage " + (status.stageName ?? status.stage)
            + " (need Running)" };
    }
    if (servicesOff < 0 || battleInServicesOff < 0) {
        return { ok: false, error: "services/Battle offsets unresolved" };
    }
    const services = runner.add(servicesOff).readPointer();
    if (services.isNull()) return { ok: false, error: "EntityServices null" };
    const battleQuery = services.add(battleInServicesOff).readPointer();
    if (battleQuery.isNull()) return { ok: false, error: "BattleQuery null (<Battle>)" };
    return { ok: true, label, runner, statePtr, battleQuery };
}

/** `ValidTargets` : l'`OrderedSet` des cibles a `+0x10`, dont le `Count` est a `+0x18` — LU dans
 *  `ExemplarOfTheKauyonPlaybook$$HasEnemyInRange` (`vt.<+0x10>.<+0x18> > 0`). On lit AUSSI les
 *  entityIds, parce qu'un COMPTE seul ne permet pas de savoir QUI le port a manque. */
function readValidTargets(vt: NativePointer): { count: number | null; ids: number[] | null } {
    if (vt.isNull()) return { count: null, ids: null };
    try {
        const set = vt.add(0x10).readPointer();
        if (set.isNull()) return { count: 0, ids: [] };
        const count = set.add(0x18).readS32();
        if (count < 0 || count > 512) return { count: null, ids: null };
        const items = set.add(0x10).readPointer();
        const ids: number[] = [];
        if (!items.isNull()) {
            for (let i = 0; i < count; i++) {
                try {
                    const e = items.add(0x20 + i * Process.pointerSize).readPointer();
                    ids.push(e.isNull() ? -1 : e.add(0x10).readS32());
                } catch { ids.push(-1); }
            }
        }
        return { count, ids };
    } catch { return { count: null, ids: null }; }
}

export function registerValidTargetsFrom(ctx: Ctx): void {
    /** `validTargetsFrom` — `GetValidTargets(unit, UnitPosition(<tuile>), abilityType)` pour un
     *  ensemble de tuiles ARBITRAIRES.
     *
     *  body: { runnerId, unitId, abilityType?, tiles: [{col,row}, ...] }
     *  `abilityType` omis => `UnitExtensions$$GetNormalAttackType(unit)`, exactement ce que fait
     *  `BasePlaybook$$GetEligibleTargetsForNormalAttack`. */
    ctx.rpc.validTargetsFrom = (
        body?: {
            runnerId?: number; unitId?: number; abilityType?: number;
            tiles?: Array<{ col: number; row: number }>;
        },
    ): Promise<unknown> => queueOnMainThread(() => {
        if (typeof body?.unitId !== "number") return { ok: false, error: "need unitId" };
        const tiles = body?.tiles ?? [];
        if (!tiles.length) return { ok: false, error: "need tiles: [{col,row}, ...]" };

        const st = resoudreRunner(body?.runnerId);
        if (!st.ok) return { ok: false, error: st.error };
        const statePtr = st.statePtr!;

        // --- resolution, ENTIEREMENT par nom (aucune RVA)
        const upClass = findClassAnywhere("IdunBattle.Core", "UnitPosition");
        const upCtor = upClass ? findCtorByParamCount(upClass, 1) : null;
        const unitExt = findClassAnywhere("IdunBattle.Entities", "UnitExtensions");
        const getNatMi = unitExt ? findMethodByParamCount(unitExt, "GetNormalAttackType", 1) : null;
        const bqRoot = st.battleQuery!;
        // DEUX overloads 3-param de `GetValidTargets` sur `BattleQuery` : l'un prend une
        // `UnitPosition` (slot 66), l'autre une `Tile` (slot 67, qui construit lui-meme la
        // position). On veut le PREMIER — desambiguise par le TYPE du param[1], jamais par l'arite.
        const gvtMi = bqRoot && !bqRoot.isNull()
            ? findMethodByParamClasses(bqRoot.readPointer(), "GetValidTargets",
                [null, "UnitPosition", null])
            : null;
        const resolution = {
            unitPosition: !!upClass, unitPositionCtor: !!upCtor,
            getNormalAttackType: !!getNatMi,
            getValidTargetsFromPosition: !!gvtMi,
            battleQueryClass: (bqRoot && !bqRoot.isNull())
                ? s(class_get_name(bqRoot.readPointer()) as NativePointer) : null,
        };
        if (!upCtor || !gvtMi) {
            return { ok: false, resolution,
                error: "resolution incomplete — RIEN n'est invoque. Sans le ctor d'`UnitPosition` "
                    + "ou l'overload a POSITION de `GetValidTargets`, la mesure serait celle d'un "
                    + "AUTRE chemin (l'overload a `Tile`), donc une reponse a une autre question." };
        }

        // --- le caster + les entites-tuiles visees
        let unitPtr: NativePointer | null = null;
        const tileByKey = new Map<string, NativePointer>();
        const wanted = new Set(tiles.map((t) => t.col + "," + t.row));
        forEachEntity(statePtr, (e, id, ty) => {
            if (ty === EntityType.Unit || ty === EntityType.Machine) {
                if (id === body.unitId) unitPtr = e;
                return;
            }
            if (ty !== EntityType.Tile) return;
            const c = readTileCoord(e);
            const k = c.col + "," + c.row;
            if (wanted.has(k) && !tileByKey.has(k)) tileByKey.set(k, e);
        });
        if (unitPtr === null) {
            return { ok: false, resolution, error: "unitId " + body.unitId + " introuvable" };
        }

        // --- l'abilityType : fourni, ou celui de l'ATTAQUE NORMALE (comme le playbook natif)
        let abilityType: number | null = null;
        let abilitySource = "body";
        if (typeof body.abilityType === "number") {
            abilityType = body.abilityType | 0;
        } else if (getNatMi) {
            try {
                const r = invokeMethod(getNatMi.info, null, [unitPtr]);
                // `runtime_invoke` BOXE les types valeur -> la valeur est a +0x10.
                abilityType = r.isNull() ? null : r.add(0x10).readS32();
                abilitySource = "GetNormalAttackType";
            } catch { /* */ }
        }
        if (abilityType === null) {
            return { ok: false, resolution,
                error: "abilityType indetermine — `GetValidTargets` rend un ensemble VIDE sur "
                    + "`abilityType == 0`, ce qui se lirait a tort comme « aucune cible »." };
        }

        const abilBuf = Memory.alloc(4);
        abilBuf.writeS32(abilityType);
        const posBuf = Memory.alloc(Process.pointerSize);

        /** Construit `UnitPosition(tile)` puis appelle le slot 66. `tile` nul = position VIDE. */
        const mesure = (tile: NativePointer | null) => {
            posBuf.writePointer(ptr(0));
            try {
                invokeMethod(upCtor.info, posBuf, [tile ?? ptr(0)]);
            } catch (e) { return { error: "ctor UnitPosition: " + (e as Error).message }; }
            const list = posBuf.readPointer();
            if (!list.isNull()) { try { gcRoot.add(list); } catch { /* */ } }
            try {
                const vt = invokeMethod(gvtMi.info, bqRoot, [unitPtr!, posBuf, abilBuf]);
                return readValidTargets(vt);
            } catch (e) {
                return { error: "GetValidTargets: " + (e as Error).message };
            } finally {
                if (!list.isNull()) { try { gcRoot.remove(list); } catch { /* */ } }
            }
        };

        // --- LE CONTROLE : la position COURANTE, par le MEME chemin.
        //     Elle valide la construction de l'`UnitPosition` (elle doit reproduire
        //     `abilityTargets.fromHere`) ET separe « rien a portee ici » de « l'ability ne peut
        //     pas etre castee du tout » (cooldown / ability absente du composant).
        let currentTile: NativePointer | null = null;
        try {
            const c = readTileCoord(unitPtr!);
            const k = c.col + "," + c.row;
            forEachEntity(statePtr, (e, _id, ty) => {
                if (currentTile !== null || ty !== EntityType.Tile) return;
                const tc = readTileCoord(e);
                if (tc.col + "," + tc.row === k) currentTile = e;
            });
        } catch { /* */ }
        const control = {
            tileResolved: currentTile !== null,
            fromCurrent: currentTile !== null ? mesure(currentTile) : null,
            note: "`fromCurrent` doit reproduire `abilityTargets[unitId].abilities[abilityType]"
                + ".fromHere`. S'il rend 0 alors que `fromHere` ne le rend pas, la construction de "
                + "l'`UnitPosition` est en cause et TOUTES les lignes ci-dessous sont a jeter. "
                + "S'il rend 0 partout, c'est le GATE d'ability (cooldown / absente du composant), "
                + "pas la geometrie.",
        };

        const results = tiles.map((t) => {
            const k = t.col + "," + t.row;
            const te = tileByKey.get(k);
            if (!te) {
                return { tile: t, error: "aucune entite-tuile a ce hex (hors plateau ?)" };
            }
            return { tile: t, ...mesure(te) };
        });

        return {
            ok: true, runner: st.label, unitId: body.unitId,
            abilityType, abilitySource, resolution, control, results,
        };
    });
}
