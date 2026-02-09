# ComfyUI Discord Rich Presence

Show your ComfyUI generation status in Discord. Displays model name, step progress, queue info, and a live progress ring — all configurable from ComfyUI settings.

<!-- screenshots here -->

---

## Features

### 📊 Status Display
| | |
|---|---|
| **Live progress ring** | Animated icon showing generation percentage (0–100%) |
| **Model name** | Currently loaded checkpoint or UNET model |
| **Step counter** | Current step and total, e.g. `Step 12/20` |
| **Node tracking** | Which node is currently executing |
| **Queue info** | Remaining items when queue has multiple prompts |
| **Elapsed timer** | How long you've been generating or idle |

### ⚙️ Customization
| | |
|---|---|
| **Quick toggle** | Enable/disable directly from the toolbar button |
| **Privacy mode** | Hide model name and generation details |
| **Custom idle text** | Set your own status text when not generating |

### 🔧 Under the Hood
| | |
|---|---|
| **Auto-reconnect** | Handles Discord restarts gracefully |
| **Zero nodes** | Pure service extension, nothing added to your workflow |

## Installation

> [!TIP]
> The easiest way to install is through ComfyUI Manager.

### ComfyUI Manager (Recommended)

Search for `Discord Rich Presence` in ComfyUI Manager and install.

### Manual

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/davehornik/ComfyUI-Discord-RPC.git
pip install pypresence
```

> [!IMPORTANT]
> Restart ComfyUI after installation.

## Setup

1. Install the extension and restart ComfyUI
2. Make sure Discord desktop app is running
3. The extension connects automatically — you should see your status in Discord within a few seconds

> [!NOTE]
> Discord mobile and web don't support Rich Presence. The desktop app is required.

## Settings

All settings are accessible in **ComfyUI Settings > Discord Rich Presence**.

| Setting | Default | Description |
|---|---|---|
| Enable Discord RPC | `On` | Master toggle for the extension |
| Show Model Name | `On` | Display checkpoint/UNET name in status |
| Show Queue Info | `On` | Show remaining queue count |
| Show Node Name | `Off` | Show the currently executing node |
| Show Step Progress | `On` | Display step counter (e.g. Step 12/20) |
| Show Elapsed Time | `On` | Show elapsed time timer |
| Custom Idle Text | ` ` | Custom text when idle (default: "Idle") |
| Privacy Mode | `Off` | Hides model name and details |

> [!TIP]
> Enable **Privacy Mode** to hide your model name and workflow details from other Discord users.

## Requirements

- **ComfyUI Desktop** or standalone ComfyUI
- **Discord desktop app** (Rich Presence is not supported on mobile/web)
- **Python package:** `pypresence >= 4.3.0` (installed automatically via ComfyUI Manager)

> [!WARNING]
> If Discord is not running when ComfyUI starts, the extension will retry connecting in the background. No action needed — it will connect automatically once Discord is launched.

## License

MIT
