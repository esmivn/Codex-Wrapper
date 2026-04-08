import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, AsyncIterator, List

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from .codex import CodexError, run_codex, run_codex_last_message
from .config import settings
from .deps import rate_limiter, verify_api_key
from .model_registry import (
    choose_model,
    get_available_models,
    initialize_model_registry,
)
from .security import assert_local_only_or_raise
from .prompt import (
    build_prompt_and_images,
    load_wrapper_system_prompt_parts,
    normalize_responses_input,
)
from .images import save_image_to_temp
from .session_workspace import (
    DEFAULT_USER_ID,
    ensure_session_workspace,
    list_recent_sessions,
    load_session_messages,
    resolve_session_file_path,
    save_session_messages,
)
from .schemas import (
    ChatChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessageResponse,
    ResponsesRequest,
    ResponsesObject,
    ResponsesMessage,
    ResponsesOutputText,
)

app = FastAPI()
STATIC_DIR = Path(__file__).resolve().parent / "static"

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event() -> None:
    await initialize_model_registry()


@app.get("/", include_in_schema=False)
@app.get("/chat", include_in_schema=False)
async def chat_ui() -> FileResponse:
    """Serve the browser chat UI."""
    return FileResponse(STATIC_DIR / "chat.html")


@app.get("/static/{file_path:path}", include_in_schema=False)
async def static_asset(file_path: str) -> FileResponse:
    target = (STATIC_DIR / file_path).resolve()
    try:
        target.relative_to(STATIC_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=404, detail="File not found")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(target)


def _workspace_public_base(request: Request, user_id: str, chat_id: str) -> str:
    return f"{str(request.base_url).rstrip('/')}/workspace/{user_id}/{chat_id}/"


def _build_session_context_prefix(request: Request, user_id: str, chat_id: str, workdir: Path) -> str:
    public_base = _workspace_public_base(request, user_id, chat_id)
    return (
        "Session workspace context:\n"
        f"- user_id: {user_id}\n"
        f"- chat_id: {chat_id}\n"
        f"- current working directory: {workdir}\n"
        f"- files created in this directory are publicly accessible at: {public_base}<relative-path>\n"
        f"- if you create `test.html` in the working directory, share this link: {public_base}test.html\n"
        "- keep generated files inside the current working directory so the user can open them in a browser."
    )


def _normalize_message_payloads(messages: List[Any]) -> List[dict[str, Any]]:
    payloads: List[dict[str, Any]] = []
    for message in messages:
        if hasattr(message, "dict"):
            payloads.append(message.dict())
        else:
            payloads.append(dict(message))
    return payloads


@app.get("/workspace/{user_id}/{chat_id}/{file_path:path}", include_in_schema=False)
async def serve_workspace_file(user_id: str, chat_id: str, file_path: str) -> FileResponse:
    if any(part.startswith(".") for part in Path(file_path).parts):
        raise HTTPException(status_code=404, detail="File not found")
    try:
        target = resolve_session_file_path(user_id=user_id, chat_id=chat_id, relative_path=file_path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(target)


@app.get("/v1/chat/sessions/{chat_id}", dependencies=[Depends(rate_limiter), Depends(verify_api_key)])
async def get_chat_session(chat_id: str):
    try:
        session = ensure_session_workspace(chat_id=chat_id, user_id=DEFAULT_USER_ID)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "user_id": session.user_id,
        "chat_id": session.chat_id,
        "workdir": str(session.session_dir),
        "public_base_url": f"/workspace/{session.user_id}/{session.chat_id}/",
        "messages": load_session_messages(chat_id=session.chat_id, user_id=session.user_id),
    }


@app.get("/v1/chat/sessions", dependencies=[Depends(rate_limiter), Depends(verify_api_key)])
async def list_chat_sessions(limit: int = 10):
    if limit < 1:
        raise HTTPException(status_code=400, detail="limit must be >= 1")
    return {
        "data": list_recent_sessions(user_id=DEFAULT_USER_ID, limit=min(limit, 50))
    }


@app.get("/v1/models", dependencies=[Depends(rate_limiter), Depends(verify_api_key)])
async def list_models():
    """Return available model list."""
    return {"data": [{"id": model} for model in get_available_models(include_reasoning_aliases=True)]}


@app.post("/v1/chat/completions", dependencies=[Depends(rate_limiter), Depends(verify_api_key)])
async def chat_completions(req: ChatCompletionRequest, request: Request):
    try:
        model_name, alias_effort = choose_model(req.model)
    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail={
                "message": str(e),
                "type": "invalid_request_error",
                "code": "model_not_found",
            },
        )

    message_payloads = _normalize_message_payloads(req.messages)
    injected_system_parts = load_wrapper_system_prompt_parts()
    x_overrides = req.x_codex.dict(exclude_none=True) if req.x_codex else {}
    chat_id = x_overrides.pop("chat_id", None)
    user_id = x_overrides.pop("user_id", DEFAULT_USER_ID)
    if alias_effort and "reasoning_effort" not in x_overrides:
        x_overrides["reasoning_effort"] = alias_effort
    overrides = x_overrides or None
    session_dir: Path | None = None
    session_user_id = DEFAULT_USER_ID
    session_chat_id: str | None = None

    if chat_id:
        try:
            session = ensure_session_workspace(chat_id=chat_id, user_id=user_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        session_dir = session.session_dir
        session_user_id = session.user_id
        session_chat_id = session.chat_id
        injected_system_parts.append(
            _build_session_context_prefix(
                request, session.user_id, session.chat_id, session.session_dir
            )
        )

    prompt, image_urls = build_prompt_and_images(
        message_payloads,
        injected_system_parts=injected_system_parts,
    )

    # Safety gate: only allow danger-full-access when explicitly enabled
    if overrides and overrides.get("sandbox") == "danger-full-access":
        if not settings.allow_danger_full_access:
            raise HTTPException(status_code=400, detail="danger-full-access is disabled by server policy")

    # Enforce local-only model provider when enabled
    if settings.local_only:
        try:
            assert_local_only_or_raise()
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    image_paths: List[str] = []
    try:
        for u in image_urls:
            image_paths.append(save_image_to_temp(u, workdir=session_dir))
    except ValueError as e:
        for p in image_paths:
            try:
                os.remove(p)
            except Exception:
                pass
        raise HTTPException(status_code=400, detail=str(e))

    try:
        if req.stream:
            async def event_gen() -> AsyncIterator[bytes]:
                final_text = ""
                async for text in run_codex(prompt, overrides, image_paths, model=model_name, workdir=session_dir):
                    if text:
                        final_text += text
                        chunk = {
                            "choices": [
                                {"delta": {"content": text}, "index": 0, "finish_reason": None}
                            ]
                        }
                        yield f"data: {json.dumps(chunk)}\n\n".encode()
                if session_chat_id:
                    save_session_messages(
                        chat_id=session_chat_id,
                        user_id=session_user_id,
                        messages=[*message_payloads, {"role": "assistant", "content": final_text}],
                    )
                yield b"data: [DONE]\n\n"

            return StreamingResponse(event_gen(), media_type="text/event-stream")
        else:
            final = await run_codex_last_message(prompt, overrides, image_paths, model=model_name, workdir=session_dir)
            if session_chat_id:
                save_session_messages(
                    chat_id=session_chat_id,
                    user_id=session_user_id,
                    messages=[*message_payloads, {"role": "assistant", "content": final}],
                )
            resp = ChatCompletionResponse(
                choices=[ChatChoice(message=ChatMessageResponse(content=final))]
            )
            return resp
    except CodexError as e:
        status = getattr(e, "status_code", None) or 500
        raise HTTPException(
            status_code=status,
            detail={
                "message": str(e),
                "type": "server_error" if status >= 500 else "upstream_error",
                "code": None,
            },
        )
    finally:
        for p in image_paths:
            try:
                os.remove(p)
            except Exception:
                pass


@app.post("/v1/responses", dependencies=[Depends(rate_limiter), Depends(verify_api_key)])
async def responses_endpoint(req: ResponsesRequest):
    try:
        model, alias_effort = choose_model(req.model)
    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail={
                "message": str(e),
                "type": "invalid_request_error",
                "code": "model_not_found",
            },
        )

    # Normalize input → messages
    try:
        messages = normalize_responses_input(req.input)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    overrides = {}
    if alias_effort:
        overrides["reasoning_effort"] = alias_effort
    if req.reasoning and req.reasoning.effort:
        overrides["reasoning_effort"] = req.reasoning.effort

    # Enforce local-only model provider when enabled
    if settings.local_only:
        try:
            assert_local_only_or_raise()
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    prompt, image_urls = build_prompt_and_images(
        messages,
        injected_system_parts=load_wrapper_system_prompt_parts(),
    )

    resp_id = f"resp_{uuid.uuid4().hex}"
    msg_id = f"msg_{uuid.uuid4().hex}"
    created = int(time.time())
    response_model = req.model or model
    codex_overrides = overrides or None

    image_paths: List[str] = []
    try:
        for u in image_urls:
            image_paths.append(save_image_to_temp(u))
    except ValueError as e:
        for p in image_paths:
            try:
                os.remove(p)
            except Exception:
                pass
        raise HTTPException(status_code=400, detail=str(e))

    try:
        if req.stream:
            async def event_gen() -> AsyncIterator[bytes]:
                try:
                    created_evt = {
                        "id": resp_id,
                        "object": "response",
                        "created": created,
                        "model": response_model,
                        "status": "in_progress",
                    }
                    yield f"event: response.created\ndata: {json.dumps(created_evt)}\n\n".encode()

                    buf: list[str] = []
                    async for text in run_codex(prompt, codex_overrides, image_paths, model=model):
                        if text:
                            buf.append(text)
                            delta_evt = {"id": resp_id, "delta": text}
                            yield f"event: response.output_text.delta\ndata: {json.dumps(delta_evt)}\n\n".encode()

                    final_text = "".join(buf)
                    done_evt = {"id": resp_id, "text": final_text}
                    yield f"event: response.output_text.done\ndata: {json.dumps(done_evt)}\n\n".encode()

                    final_obj = ResponsesObject(
                        id=resp_id,
                        created=created,
                        model=response_model,
                        status="completed",
                        output=[
                            ResponsesMessage(
                                id=msg_id,
                                content=[ResponsesOutputText(text=final_text)],
                            )
                        ],
                    ).model_dump()
                    yield f"event: response.completed\ndata: {json.dumps(final_obj)}\n\n".encode()
                except CodexError as e:
                    err_evt = {"id": resp_id, "error": {"message": str(e)}}
                    yield f"event: response.error\ndata: {json.dumps(err_evt)}\n\n".encode()
                finally:
                    yield b"data: [DONE]\n\n"

            headers = {
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            }
            return StreamingResponse(event_gen(), media_type="text/event-stream", headers=headers)
        else:
            final = await run_codex_last_message(prompt, codex_overrides, image_paths, model=model)
            resp = ResponsesObject(
                id=resp_id,
                created=created,
                model=response_model,
                status="completed",
                output=[
                    ResponsesMessage(
                        id=msg_id,
                        content=[ResponsesOutputText(text=final)],
                    )
                ],
            )
            return resp
    except CodexError as e:
        status = getattr(e, "status_code", None) or 500
        raise HTTPException(
            status_code=status,
            detail={
                "message": str(e),
                "type": "server_error" if status >= 500 else "upstream_error",
                "code": None,
            },
        )
    finally:
        for p in image_paths:
            try:
                os.remove(p)
            except Exception:
                pass
