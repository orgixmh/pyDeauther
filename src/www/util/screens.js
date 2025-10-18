import { parse, type, prompt, input } from "./io.js";
import pause from "./pause.js";
import alert from "./alert.js";
import say from "./speak.js";

const USER = "admin";
const PW = "admin";

const fastMode = false;

/** Boot screen */
export async function boot() {
	clear();
	if (!fastMode){
		await type(["Loading pyDeauther.app.","............................................................"," ","APP LOADED OK!"], {
			lineWait: 10,
			finalWait: 100
		});
	}
	
	await mainMenu();
	
}
export async function typeOut(text) {
		await type([text], {
			lineWait: 50
		});
}
export async function mainMenu() {

	clear();
	if (!fastMode){
		await type(["-----------------------------------------------", "|              pyDeauther v0.0.1              |","---------------------------------- ORGix * 2025", " "], {
			lineWait: 50
		});
	}
	

	await type([" "," *** MAIN MENU ***", " ","  1) ATTACK","  2) WHITELIST", "  3) SETTINGS", " "], {
		lineWait: 50,
		finalWait: 1000
	});

	await pause();
	return mainMenuSelector();
}

/** mainMenuSelector */
export async function mainMenuSelector() {
	//clear();
	let option = await prompt("Please type an option:");
	
	if (Number(option)>0 && Number(option)<=3) {
		await pause();
		//say("Loading option "+ option);
		
		
		if (Number(option)==1){
			bridge.send_command(JSON.stringify({ command: "scan", data: "" }));
			await alert("-- STARTING ATTACK ---");
		} else 	if (Number(option)==3){
			bridge.send_command(JSON.stringify({ command: "settings", data: "" }));
			await alert("Loading Settings!");
		}

		
		//clear();
		await pause();
		return mainMenuSelector();
	} else {
		await type([
			"Are you blind mofo? Valid options 1, 2, 3.",
			"Try again!"
		]);
		await pause(1);
		//clear();
		return mainMenu();
	}
}

/** Login screen */
export async function login() {
	clear();
	let user = await prompt("Username:");
	let password = await prompt("Password:", true);

	if (user === USER && password === PW) {
		await pause();
		say("AUTHENTICATION SUCCESSFUL");
		await alert("AUTHENTICATION SUCCESSFUL");
		clear();
		return main();
	} else {
		await type([
			"Incorrect user and/or password.",
			"Please try again"
		]);
		await pause(3);
		clear();
		return login();
	}
}

/** Main input terminal, recursively calls itself */
export async function main() {
	let command = await input();
	try {
		await parse(command);
	} catch (e) {
		if (e.message) await type(e.message);
	}

	main();
}

export function addClasses(el, ...cls) {
	let list = [...cls].filter(Boolean);
	el.classList.add(...list);
}

export function getScreen(...cls) {
	let div = document.createElement("div");
	addClasses(div, "fullscreen", ...cls);
	document.querySelector("#crt").appendChild(div);
	return div;
}

export function toggleFullscreen(isFullscreen) {
	document.body.classList.toggle("fullscreen", isFullscreen);
}

/** Attempts to load template HTML from the given path and includes them in the <head>. */
export async function loadTemplates(path) {
	let txt = await fetch(path).then((res) => res.text());
	let html = new DOMParser().parseFromString(txt, "text/html");
	let templates = html.querySelectorAll("template");

	templates.forEach((template) => {
		document.head.appendChild(template);
	});
}

/** Clones the template and adds it to the container. */
export async function addTemplate(id, container, options = {}) {
	let template = document.querySelector(`template#${id}`);
	if (!template) {
		throw Error("Template not found");
	}
	// Clone is the document fragment of the template
	let clone = document.importNode(template.content, true);

	if (template.dataset.type) {
		await type(clone.textContent, options, container);
	} else {
		container.appendChild(clone);
	}

	// We cannot return clone here
	// https://stackoverflow.com/questions/27945721/how-to-clone-and-modify-from-html5-template-tag
	return container.childNodes;
}

/** Creates a new screen and loads the given template into it. */
export async function showTemplateScreen(id) {
	let screen = getScreen(id);
	await addTemplate(id, screen);
	return screen;
}

/**
 * Creates an element and adds it to the given container (or terminal screen if undefined).
 * @param {String} type The type of element to create.
 * @param {Element} container The container to add the created element to.
 * @param {String} cls The class to apply to the created element.
 * @param {Object} attrs Extra attributes to set on the element.
 */
export function el(
	type,
	container = document.querySelector(".terminal"),
	cls = "",
	attrs
) {
	let el = document.createElement(type);
	addClasses(el, cls);

	container.appendChild(el);

	if (attrs) {
		Object.entries(attrs).forEach(([key, value]) => {
			el.setAttribute(key, value);
		});
	}
	return el;
}

/**
 * Creates a <div> and adds it to the screen.
 * @param {Element} container The container to add the created element to.
 * @param {String} cls The class to apply to the created element.
 */
export function div(...args) {
	return el("div", ...args);
}

export function clear(screen = document.querySelector(".terminal")) {
	screen.innerHTML = "";
}
