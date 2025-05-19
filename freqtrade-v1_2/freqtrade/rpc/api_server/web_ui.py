from pathlib import Path
from typing import Optional

from fastapi import APIRouter
from fastapi.exceptions import HTTPException
from starlette.responses import FileResponse


# Create a router for UI-related endpoints
router_ui = APIRouter()


@router_ui.get("/favicon.ico", include_in_schema=False)
async def favicon() -> FileResponse:
    """
    Serve the favicon.ico file for the UI.

    Returns:
        FileResponse: The favicon.ico file.

    Raises:
        HTTPException: If the favicon.ico file is not found.
    """
    favicon_path = Path(__file__).parent / "ui/favicon.ico"
    if not favicon_path.is_file():
        raise HTTPException(status_code=404, detail="Not Found")
    return FileResponse(str(favicon_path))


@router_ui.get("/fallback_file.html", include_in_schema=False)
async def fallback():
    """
    Serve the fallback_file.html file for the UI.

    Returns:
        FileResponse: The fallback_file.html file.
    """
    fallback_file_path = Path(__file__).parent / "ui/fallback_file.html"
    if not fallback_file_path.is_file():
        raise HTTPException(status_code=404, detail="Not Found")
    return FileResponse(str(fallback_file_path))


@router_ui.get("/ui_version", include_in_schema=False)
async def ui_version():
    from freqtrade.commands.deploy_ui import read_ui_version

    uibase = Path(__file__).parent / "ui/installed/"
    version = read_ui_version(uibase)

    return {
        "version": version if version else "not_installed",
    }


@router_ui.get("/{rest_of_path:path}", include_in_schema=False)
async def index_html(rest_of_path: str):
    """
    Serve static files or fallback to index.html for UI routing.

    Args:
        rest_of_path (str): The path of the requested file.

    Returns:
        FileResponse: The requested file or index.html.

    Raises:
        HTTPException: If the requested file is not found.
    """
    # Block access to API routes or hidden files
    if rest_of_path.startswith("api") or rest_of_path.startswith("."):
        raise HTTPException(status_code=404, detail="Not Found")
    uibase = Path(__file__).parent / "ui/installed/"
    if not uibase.is_dir():
        raise HTTPException(
            status_code=404, detail="UI directory not found"
        )
    filename = uibase / rest_of_path
    # It's security relevant to check "relative_to".
    # Without this, Directory-traversal is possible.
    media_type: str | None = None
    if filename.suffix == ".js":
        # Force text/javascript for .js files - Circumvent faulty system configuration
        media_type = "application/javascript"
    if filename.is_file() and filename.is_relative_to(uibase):
        return FileResponse(str(filename), media_type=media_type)

    index_file = uibase / "index.html"
    if not index_file.is_file():
        return FileResponse(str(uibase.parent / "fallback_file.html"))
    # Fall back to index.html, as indicated by vue router docs
    return FileResponse(str(index_file))
