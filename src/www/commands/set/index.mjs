import { parse, type, prompt, input,scroll } from "../../util/io.js";
import { div, clear, typeOut } from "../../util/screens.js";
import pause from "../../util/pause.js";
import alert from "../../util/alert.js";


async function set() {
	if (!document.pyConfig.fast_mode) {
		await type("Executing setting.app...", {
			lineWait: 1,
			finalWait: 1
		});
	}
	bridge.send_command(JSON.stringify({ command: "settings", data: "" }));
	if (!document.pyConfig.fast_mode) {
		await alert("-- APP LOADED OK! --");
	}
	
		
}


export default set;
