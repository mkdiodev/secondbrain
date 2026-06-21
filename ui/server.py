"""Flask web server for the SecondBrain chat UI."""

from __future__ import annotations

import logging
import os

from flask import Flask, jsonify, render_template, request

from .config import UIConfig
from .runtime import ChatRuntime

logger = logging.getLogger("secondbrain.ui")


def create_app() -> tuple[Flask, ChatRuntime]:
    config = UIConfig.from_env()
    runtime = ChatRuntime(config)
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    app.config["SECRET_KEY"] = os.environ.get("SECOND_BRAIN_SECRET_KEY", "dev-secret-key")

    @app.get("/")
    def index() -> str:
        return render_template(
            "index.html",
            title="SecondBrain",
            initial_state=runtime.state(),
        )

    @app.get("/api/state")
    def api_state():
        return jsonify(runtime.state())

    @app.get("/api/history")
    def api_history():
        return jsonify({"history": runtime.history_snapshot()})

    @app.delete("/api/history")
    def api_history_delete():
        runtime.clear_history()
        return jsonify({"status": "cleared"})

    @app.get("/api/memory/search")
    def api_memory_search():
        query = (request.args.get("q") or "").strip()
        if not query:
            return jsonify({"error": "Missing query"}), 400
        limit = int(request.args.get("limit", "5"))
        return jsonify({"results": runtime.search_memory(query, limit=limit)})

    @app.get("/api/dh/config")
    def api_dh_config_get():
        try:
            return jsonify(runtime.workspace.resources.dh_skill.config_payload())
        except Exception as exc:  # pragma: no cover - surfaced in UI
            logger.exception("Drillhole config load failed")
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/dh/config/init")
    def api_dh_config_init():
        try:
            return jsonify(runtime.workspace.resources.dh_skill.config_payload())
        except Exception as exc:  # pragma: no cover - surfaced in UI
            logger.exception("Drillhole config init failed")
            return jsonify({"error": str(exc)}), 400

    @app.put("/api/dh/config")
    def api_dh_config_put():
        payload = request.get_json(silent=True) or {}
        config_payload = payload.get("config")
        if config_payload is None:
            return jsonify({"error": "Missing config"}), 400
        try:
            runtime.workspace.resources.dh_skill.save_config(config_payload)
            return jsonify(runtime.workspace.resources.dh_skill.config_payload())
        except Exception as exc:
            logger.info("Drillhole config save failed: %s", exc)
            return jsonify({"error": str(exc)}), 400

    @app.post("/api/chat")
    def api_chat():
        payload = request.get_json(silent=True) or {}
        message = str(payload.get("message", "")).strip()
        if not message:
            return jsonify({"error": "Empty message"}), 400
        result = runtime.handle_message(message)
        if "error" in result:
            return jsonify(result), 400
        return jsonify(result)

    @app.post("/api/voice/transcribe")
    def api_voice_transcribe():
        audio = request.files.get("audio")
        if audio is None:
            return jsonify({"error": "Missing audio file"}), 400

        language = request.form.get("language") or None
        try:
            from secondbrain.voice import transcribe_audio

            return jsonify(transcribe_audio(audio, language=language))
        except Exception:
            logger.exception("Voice transcription failed")
            return jsonify({"error": "Voice transcription failed"}), 500

    @app.post("/api/workspace")
    def api_workspace():
        payload = request.get_json(silent=True) or {}
        workspace = str(payload.get("workspace", "")).strip()
        if not workspace:
            return jsonify({"error": "Missing workspace"}), 400
        try:
            state = runtime.set_workspace(workspace)
        except Exception as exc:  # pragma: no cover - surfaced in UI
            logger.exception("Workspace switch failed")
            return jsonify({"error": str(exc)}), 400
        return jsonify({"status": "ok", "state": state})

    return app, runtime


def run_server(host: str | None = None, port: int | None = None, debug: bool = False) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    app, runtime = create_app()
    host = host or runtime.config.host
    port = port or runtime.config.port
    logger.info("Starting SecondBrain UI on http://%s:%s", host, port)
    app.run(host=host, port=port, debug=debug, use_reloader=debug)


if __name__ == "__main__":  # pragma: no cover - manual entrypoint
    run_server()
