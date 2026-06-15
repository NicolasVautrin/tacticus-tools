import { Ctx } from "../../controller.js";
import { registerDrive } from "./rpc-drive.js";
import { registerView } from "./rpc-view.js";

export function register(ctx: Ctx): void {
    registerDrive(ctx);
    registerView(ctx);
}
