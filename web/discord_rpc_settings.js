import { app } from "../../scripts/app.js";

const EXTENSION_NAME = "DiscordRPC.Settings";

// Setting IDs
const SETTINGS = {
    ENABLED: "discord_rpc.enabled",
    SHOW_MODEL: "discord_rpc.show_model_name",
    SHOW_QUEUE: "discord_rpc.show_queue_info",
    SHOW_NODE: "discord_rpc.show_node_name",
    SHOW_STEPS: "discord_rpc.show_step_progress",
    SHOW_TIME: "discord_rpc.show_elapsed_time",
    SHOW_RUN_TIME: "discord_rpc.show_current_run_time",
    CUSTOM_IDLE: "discord_rpc.custom_idle_text",
    PRIVACY_MODE: "discord_rpc.privacy_mode",
    DEBUG_LOGGING: "discord_rpc.debug_logging",
};

// Track current state
let isEnabled = true;
let isGenerating = false;
let topBarButton = null;

/**
 * Discord logo SVG icon (20x20, single color).
 */
function getDiscordIcon(color = "currentColor") {
    return `<svg width="20" height="20" viewBox="0 0 24 24" fill="${color}" xmlns="http://www.w3.org/2000/svg">
        <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028c.462-.63.874-1.295 1.226-1.994a.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.095 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.095 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z"/>
    </svg>`;
}

/**
 * Update the visual state of the top bar button.
 * Three states: disabled (grey), idle (blue), generating (green).
 */
function updateButtonState(button) {
    if (!button) return;
    if (!isEnabled) {
        button.innerHTML = getDiscordIcon("#666666");
        button.style.opacity = "0.5";
        button.style.background = "transparent";
        button.title = "Discord Rich Presence: OFF (click to enable)";
    } else if (isGenerating) {
        button.innerHTML = getDiscordIcon("#FFFFFF");
        button.style.opacity = "1";
        button.style.background = "#57F287";
        button.title = "Discord Rich Presence: Generating...";
    } else {
        button.innerHTML = getDiscordIcon("#FFFFFF");
        button.style.opacity = "1";
        button.style.background = "#5865F2";
        button.title = "Discord Rich Presence: ON (click to disable)";
    }
    button.style.borderRadius = "4px";
}

/**
 * Push a setting change to the Python backend.
 */
async function pushSettingToBackend(key, value) {
    try {
        const keyMap = {
            [SETTINGS.ENABLED]: "enabled",
            [SETTINGS.SHOW_MODEL]: "show_model_name",
            [SETTINGS.SHOW_QUEUE]: "show_queue_info",
            [SETTINGS.SHOW_NODE]: "show_node_name",
            [SETTINGS.SHOW_STEPS]: "show_step_progress",
            [SETTINGS.SHOW_TIME]: "show_elapsed_time",
            [SETTINGS.SHOW_RUN_TIME]: "show_current_run_time",
            [SETTINGS.CUSTOM_IDLE]: "custom_idle_text",
            [SETTINGS.PRIVACY_MODE]: "privacy_mode",
            [SETTINGS.DEBUG_LOGGING]: "debug_logging",
        };
        const backendKey = keyMap[key];
        if (!backendKey) return;

        await fetch("/discord-rpc/config", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ [backendKey]: value }),
        });
    } catch (e) {
        console.warn("[Discord RPC] Failed to push setting to backend:", e);
    }
}

/**
 * Toggle Discord RPC on/off via the top bar button.
 */
async function toggleDiscordRPC() {
    isEnabled = !isEnabled;

    // Update backend
    await pushSettingToBackend(SETTINGS.ENABLED, isEnabled);

    // Update the ComfyUI setting value
    try {
        const settingManager = app?.extensionManager?.setting;
        if (settingManager && typeof settingManager.set === "function") {
            settingManager.set(SETTINGS.ENABLED, isEnabled);
        } else {
            app.ui.settings.setSettingValue(SETTINGS.ENABLED, isEnabled);
        }
    } catch (e) {
        // Fallback if neither API is available
    }

    // Update button visual
    updateButtonState(topBarButton);
}

/**
 * Fetch the current enabled state from the backend on load.
 */
async function fetchInitialState() {
    try {
        const resp = await fetch("/discord-rpc/config");
        if (resp.ok) {
            const config = await resp.json();
            isEnabled = config.enabled !== false;
        }
    } catch (e) {
        // Default to enabled
        isEnabled = true;
    }
}

app.registerExtension({
    name: EXTENSION_NAME,

    actionBarButtons: [
        {
            icon: "pi pi-discord",
            tooltip: "Toggle Discord Rich Presence",
            onClick: toggleDiscordRPC,
        },
    ],

    async setup() {
        // Fetch current state from backend
        await fetchInitialState();

        // Listen to ComfyUI execution events for button color changes
        app.api.addEventListener("execution_start", () => {
            isGenerating = true;
            updateButtonState(topBarButton);
        });
        app.api.addEventListener("executed", () => {
            isGenerating = false;
            updateButtonState(topBarButton);
        });
        app.api.addEventListener("execution_error", () => {
            isGenerating = false;
            updateButtonState(topBarButton);
        });
        app.api.addEventListener("execution_interrupted", () => {
            isGenerating = false;
            updateButtonState(topBarButton);
        });

        // Find and customize our button in the action bar.
        // PrimeVue renders async so we retry until the button appears.
        let retries = 0;
        const findButton = () => {
            const button = document.querySelector(
                'button[aria-label="Toggle Discord Rich Presence"]'
            );
            if (button) {
                topBarButton = button;
                updateButtonState(button);
                button.style.padding = "6px";
                button.style.borderRadius = "4px";
                button.style.border = "1px solid transparent";
                button.style.transition = "all 0.2s ease";
            } else if (retries < 20) {
                retries++;
                setTimeout(findButton, 250);
            }
        };
        requestAnimationFrame(findButton);
    },

    settings: [
        {
            id: SETTINGS.ENABLED,
            name: "Enable Discord Rich Presence",
            type: "boolean",
            defaultValue: true,
            tooltip:
                "Show your ComfyUI activity as Discord Rich Presence status. " +
                "Requires Discord desktop app to be running.",
            category: ["Discord RPC", "General", "Enable"],
            onChange(value) {
                isEnabled = value;
                updateButtonState(topBarButton);
                pushSettingToBackend(SETTINGS.ENABLED, value);
            },
        },
        {
            id: SETTINGS.SHOW_MODEL,
            name: "Show Model Name",
            type: "boolean",
            defaultValue: true,
            tooltip:
                "Display the currently loaded model name in your Discord status.",
            category: ["Discord RPC", "Display", "Model Name"],
            onChange(value) {
                pushSettingToBackend(SETTINGS.SHOW_MODEL, value);
            },
        },
        {
            id: SETTINGS.SHOW_QUEUE,
            name: "Show Queue Info",
            type: "boolean",
            defaultValue: true,
            tooltip:
                "Display the number of items in queue in your Discord status.",
            category: ["Discord RPC", "Display", "Queue Info"],
            onChange(value) {
                pushSettingToBackend(SETTINGS.SHOW_QUEUE, value);
            },
        },
        {
            id: SETTINGS.SHOW_NODE,
            name: "Show Node Name",
            type: "boolean",
            defaultValue: false,
            tooltip:
                "Display the name of the currently processing node " +
                "(e.g. 'KSampler', 'VAEDecode') in your Discord status.",
            category: ["Discord RPC", "Display", "Node Name"],
            onChange(value) {
                pushSettingToBackend(SETTINGS.SHOW_NODE, value);
            },
        },
        {
            id: SETTINGS.SHOW_STEPS,
            name: "Show Step Progress",
            type: "boolean",
            defaultValue: true,
            tooltip:
                "Display step progress (e.g. 'Step 12/20') during generation. " +
                "When disabled, only the progress circle icon is shown.",
            category: ["Discord RPC", "Display", "Step Progress"],
            onChange(value) {
                pushSettingToBackend(SETTINGS.SHOW_STEPS, value);
            },
        },
        {
            id: SETTINGS.SHOW_TIME,
            name: "Show Elapsed Time",
            type: "boolean",
            defaultValue: true,
            tooltip:
                "Display the total session timer in your Discord status. " +
                "When disabled, no timer is shown.",
            category: ["Discord RPC", "Display", "Elapsed Time"],
            onChange(value) {
                pushSettingToBackend(SETTINGS.SHOW_TIME, value);
            },
        },
        {
            id: SETTINGS.SHOW_RUN_TIME,
            name: "Show Current Run Time",
            type: "boolean",
            defaultValue: true,
            tooltip:
                "Display the current generation runtime in the status text. " +
                "The main elapsed timer still shows total session time.",
            category: ["Discord RPC", "Display", "Run Time"],
            onChange(value) {
                pushSettingToBackend(SETTINGS.SHOW_RUN_TIME, value);
            },
        },
        {
            id: SETTINGS.CUSTOM_IDLE,
            name: "Custom Idle Text",
            type: "text",
            defaultValue: "",
            tooltip:
                "Custom text to show instead of 'Idle' when not generating. " +
                "Leave empty for default 'Idle'.",
            category: ["Discord RPC", "Display", "Custom Idle Text"],
            onChange(value) {
                pushSettingToBackend(SETTINGS.CUSTOM_IDLE, value);
            },
        },
        {
            id: SETTINGS.PRIVACY_MODE,
            name: "Privacy Mode",
            type: "boolean",
            defaultValue: false,
            tooltip:
                "Hide the model name from your Discord status. " +
                "Shows 'ComfyUI' instead. Overrides 'Show Model Name'.",
            category: ["Discord RPC", "Privacy", "Privacy Mode"],
            onChange(value) {
                pushSettingToBackend(SETTINGS.PRIVACY_MODE, value);
            },
        },
        {
            id: SETTINGS.DEBUG_LOGGING,
            name: "Debug Logging",
            type: "boolean",
            defaultValue: false,
            tooltip:
                "Log execution events to the console for troubleshooting. " +
                "Enable this when reporting issues on GitHub.",
            category: ["Discord RPC", "Advanced", "Debug Logging"],
            onChange(value) {
                pushSettingToBackend(SETTINGS.DEBUG_LOGGING, value);
            },
        },
    ],
});
