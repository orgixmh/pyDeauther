import { parse, type, prompt, input,scroll } from "../../util/io.js";
import { div, clear, typeOut } from "../../util/screens.js";
import pause from "../../util/pause.js";
import alert from "../../util/alert.js";
import { typeSound } from "../../sound/index.js";
import say from "../../util/speak.js";
const controller = new AbortController();
const { signal } = controller;

const sleep = (ms) => new Promise(res => setTimeout(res, ms));
let typer = div();
let stopMain=false;
let booted = false;
export async function boot() {
	clear();
	if ( stopMain ) { return; }
	if (!document.pyConfig.fast_mode) {
		await type(["PRESS ctrl+c to quit app"," "], {
			lineWait: 1,
			finalWait: 1
		});
		await type(["Loading pyDeauther.app.","............................................................"], {
			lineWait: 10,
			finalWait: 1000
		});
		await alert("-- APP LOADED OK! --");
	}
	clear();
	if ( stopMain ) { return; }
	if (!document.pyConfig.fast_mode) {
		await type(["-----------------------------------------------", "|              pyDeauther v0.0.1              |","---------------------------------- ORGix * 2025", " "], {
			lineWait: 50
		});
	}
	if ( stopMain ) { return; }
	
	await mainMenu();
	
}
export async function mainMenu() {
	if ( stopMain ) { return; }
	if (booted) { clear();}
	booted = true;
	await type([" "," *** MAIN MENU ***", " ","  1) ATTACK","  2) WHITELIST", " ", "  Q) QUIT"," "], {
		wait: 15,
		initialWait: 0,
		finalWait: 0,
	});
	if ( stopMain ) { return; }
	await pause();
	await mainMenuSelector();
}

/** mainMenuSelector */
export async function mainMenuSelector() {
	
	if ( stopMain ) { return; }
	let option = await prompt("Please type an option:");
	if ( stopMain ) { return; }
	if (Number(option)>0 && Number(option)<=3 || option == "Q" || option == "q") {
		await pause();
		//say("Loading option "+ option);
		
		
		if (Number(option)==1){
			bridge.send_command(JSON.stringify({ command: "scan", data: "" }));
			clear();
			await alert("-- ENABLING MONITOR MODE ---");
			while(document.modeState && !stopMain){
				await pause(1)
			}
			await alert("-- SCANNING FOR TARGETS ---");
			while(document.scannerState && !stopMain){
				await type(["."], {
					wait: 0,
					initialWait: 0,
					finalWait: 1000,
					useContainer: true
				});
			}
			await pause(1)
			if (document.attackState && !stopMain){
				await alert("-- ATTACKING TARGETS ---");
			}
			while(document.attackState && !stopMain){
				 await sleep(1000);
			}
			
			if (!stopMain) { await sleep(5000);}

		} else 	if (option=="q" || option=="Q"){
				stopMain=true;
				return;
		} else if(option=="2"){
			bridge.send_command(JSON.stringify({ command: "whitelist", data: "" }));
			await alert("-- LOADING WHITELIST.APP ---");
			await sleep(1)
		}

		
		//clear();
		await pause();
		//return mainMenu();
	} else {
		await type([
			"Are you blind mofo? Valid options 1, 2, 3.",
			"Try again!"
		]);

		//clear();
		//await mainMenu();
	}
}

async function deauther() {
	stopMain=false;

	
	const onKeyDown = async event => {
		console.log("Key pressed!")
		if (event.key === 'c' && event.ctrlKey) {
				await type([
					"CTRL+C","EXITING APP"
				]);
				event.preventDefault();
				stopMain=true;
				bridge.send_command(JSON.stringify({ command: "stop_attack", data: "" }));
						
		} 
	};
	window.addEventListener('keydown', onKeyDown, { capture: true, signal });
	while (!stopMain) {
		if (booted){
			await mainMenu();
		}else{
			await boot();	
		}
	}
	
	clear();
		
}

export default deauther;
