/** Agregateur des RPCs "view" (lecture/probe de runners) — scinde par theme
 *  (module-size >1000 l., 2026-07-11) : board (terrain/pathfinding), snapshot
 *  (stats/config/varTrace, capteur #100), targeting (rank/legalite), decision
 *  (vues decision + applyAction), predict (aiPredict/aiPlaybookPredict #102).
 *  L'API RPC est INCHANGEE (memes noms ctx.rpc.*) ; le point d'entree registerView
 *  est conserve (consomme par ./index.ts). */
import { Ctx } from "../../controller.js";
import { registerViewBoard } from "./rpc-board.js";
import { registerViewSnapshot } from "./rpc-snapshot.js";
import { registerViewTargeting } from "./rpc-targeting.js";
import { registerViewDecision } from "./rpc-decision.js";
import { registerViewPredict } from "./rpc-predict.js";
import { registerViewNcPredict } from "./rpc-nc-predict.js";

export function registerView(ctx: Ctx): void {
    registerViewBoard(ctx);
    registerViewSnapshot(ctx);
    registerViewTargeting(ctx);
    registerViewDecision(ctx);
    registerViewPredict(ctx);
    registerViewNcPredict(ctx);
}
