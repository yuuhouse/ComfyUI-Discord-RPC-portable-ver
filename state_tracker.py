"""State tracking for ComfyUI Discord Rich Presence.

Bridges ComfyUI execution events to the DiscordRPCManager state updates.
Progress is captured via the ``send_sync("progress", ...)`` event that
ComfyUI's ``hijack_progress`` hook emits on every sampler step.  This is
more reliable than monkey-patching ``add_progress_handler`` because
``execution.py`` imports it by name at module load time, making the
module-level patch invisible to the executor.
"""

import logging
import os

logger = logging.getLogger("discord_rpc")

# Node types that load models - maps class_type to input key containing model name
MODEL_NODE_TYPES = {
    "CheckpointLoaderSimple": "ckpt_name",
    "CheckpointLoader": "ckpt_name",
    "UNETLoader": "unet_name",
    "DiffusionModelLoader": "unet_name",
    "DiffusionModelLoaderKJ": "unet_name",
    "CheckpointLoaderKJ": "ckpt_name",
    "unCLIPCheckpointLoader": "ckpt_name",
    "GGUFLoaderKJ": "unet_name",
}


def extract_model_name(prompt):
    """Extract the primary model name from a workflow prompt graph.

    Args:
        prompt: Dict of node_id -> node_data from the queued prompt.

    Returns:
        Model filename without path and extension, or empty string.
    """
    for node_data in prompt.values():
        class_type = node_data.get("class_type", "")
        if class_type in MODEL_NODE_TYPES:
            input_key = MODEL_NODE_TYPES[class_type]
            inputs = node_data.get("inputs", {})
            if input_key in inputs:
                model_path = inputs[input_key]
                if isinstance(model_path, str):
                    return os.path.splitext(os.path.basename(model_path))[0]
    return ""


class StateTracker:
    """Bridges ComfyUI execution events to DiscordRPCManager state updates."""

    def __init__(self, rpc_manager):
        self.rpc = rpc_manager
        self._current_model = ""
        self._node_titles = {}  # node_id -> display_name from prompt graph

    def on_prompt(self, json_data):
        """Called by on_prompt_handler before a prompt is queued.

        Extracts model name and node title map from the workflow.
        Must return json_data unchanged.
        """
        prompt = json_data.get("prompt", {})
        model_name = extract_model_name(prompt)
        if model_name:
            self._current_model = model_name
            self.rpc.update_model_name(model_name)

        # Build node_id -> display title map for "Show Node Name" feature
        self._node_titles = {}
        for node_id, node_data in prompt.items():
            # Use _meta.title if present (user-visible name), else class_type
            meta = node_data.get("_meta", {})
            title = meta.get("title", "") or node_data.get("class_type", "")
            if title:
                self._node_titles[str(node_id)] = title

        # Update queue size
        try:
            from server import PromptServer

            if hasattr(PromptServer, "instance") and PromptServer.instance is not None:
                remaining = PromptServer.instance.prompt_queue.get_tasks_remaining()
                self.rpc.update_queue_size(remaining + 1)
        except Exception:
            pass

        return json_data

    def on_server_event(self, event, data):
        """Called from wrapped send_sync to observe execution lifecycle events.

        Handles:
          - execution_start   → switch to generating state
          - progress          → update step progress (value/max) + current node
          - executing         → track current node; node=None means done
          - execution_error/interrupted → back to idle
          - status            → queue size update
        """
        if event == "execution_start":
            prompt_id = data.get("prompt_id", "")
            self.rpc.set_generating(prompt_id, self._current_model)

        elif event == "progress":
            # Emitted by hijack_progress on every sampler step
            value = data.get("value", 0)
            max_value = data.get("max", 0)
            self.rpc.update_progress(value, max_value)
            # Also update node name from the progress event
            node_id = str(data.get("node", ""))
            if node_id:
                node_name = self._node_titles.get(node_id, "")
                if node_name:
                    self.rpc.update_current_node(node_name)

        elif event == "executing":
            node_id = data.get("node")
            if node_id is None:
                # Execution complete for this prompt
                self.rpc.update_current_node("")
                self._update_queue_remaining()
                self.rpc.set_idle()
            else:
                # A new node started executing - update current node name
                node_name = self._node_titles.get(str(node_id), "")
                if node_name:
                    self.rpc.update_current_node(node_name)

        elif event in ("execution_error", "execution_interrupted"):
            self.rpc.update_current_node("")
            self._update_queue_remaining()
            self.rpc.set_idle()

        elif event == "status":
            status_info = data.get("status", {})
            exec_info = status_info.get("exec_info", {})
            remaining = exec_info.get("queue_remaining", 0)
            self.rpc.update_queue_size(remaining)

    def _update_queue_remaining(self):
        try:
            from server import PromptServer

            if hasattr(PromptServer, "instance") and PromptServer.instance is not None:
                remaining = PromptServer.instance.prompt_queue.get_tasks_remaining()
                self.rpc.update_queue_size(remaining)
        except Exception:
            pass
