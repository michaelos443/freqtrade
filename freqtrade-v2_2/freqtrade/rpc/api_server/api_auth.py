import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from enum import Enum

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, status
from fastapi.security import OAuth2PasswordBearer
from fastapi.security.http import HTTPBasic, HTTPBasicCredentials

from freqtrade.rpc.api_server.api_schemas import AccessAndRefreshToken, AccessToken
from freqtrade.rpc.api_server.deps import get_api_config


logger = logging.getLogger(__name__)

ALGORITHM = "HS256"

router_login = APIRouter()


class TokenType(str, Enum):
    """Enumerator for token types"""
    ACCESS = "access"
    REFRESH = "refresh"


def verify_auth(api_config: dict[str, Any], username: str, password: str):
    """
    Verify the provided username and password against the API configuration.

    Args:
        api_config (dict): The API configuration.
        username (str): The provided username.
        password (str): The provided password.

    Returns:
        bool: True if the provided credentials are valid, False otherwise.
    """
    return secrets.compare_digest(username, api_config.get("username")) and secrets.compare_digest(
        password, api_config.get("password")
    )


httpbasic = HTTPBasic(auto_error=False)
security = HTTPBasic()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)


def get_user_from_token(token, secret_key: str, token_type: str = "access") -> str:  # noqa: S107
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, secret_key, algorithms=[ALGORITHM])
        username: str = payload.get("identity", {}).get("u")
        if username is None:
            raise credentials_exception
        if payload.get("type") != token_type:
            raise credentials_exception

    except jwt.PyJWTError:
        raise credentials_exception
    return username


# This should be reimplemented to better realign with the existing tools provided
# by FastAPI regarding API Tokens
# https://github.com/tiangolo/fastapi/blob/master/fastapi/security/api_key.py
async def validate_ws_token(
    ws: WebSocket,
    ws_token: Optional[str] = Query(default=None, alias="token"),
    api_config: dict[str, Any] = Depends(get_api_config),
):
    secret_ws_token = api_config.get("ws_token")
    secret_jwt_key = api_config.get("jwt_secret_key", "super-secret")

    # Check if ws_token is/in secret_ws_token
    if ws_token and secret_ws_token:
        is_valid_ws_token = False
        if isinstance(secret_ws_token, str):
            is_valid_ws_token = secrets.compare_digest(secret_ws_token, ws_token)
        elif isinstance(secret_ws_token, list):
            is_valid_ws_token = any(
                secrets.compare_digest(potential, ws_token) for potential in secret_ws_token
            ) if secret_ws_token else False

        if is_valid_ws_token:
            return ws_token
        else:
            logger.info("Token is not a valid WS token. Checking if it is a JWT token.")

    # Check if ws_token is a JWT
    try:
        user = get_user_from_token(ws_token, secret_jwt_key)
        return user
    # If the token is a jwt, and it's valid return the user
    except HTTPException:
        pass

    # If it doesn't match, close the websocket connection
    await ws.close(code=status.WS_1008_POLICY_VIOLATION)
    return None


def create_token(data: dict, secret_key: str, token_type: str = "access") -> str:  # noqa: S107
    to_encode = data.copy()
    expire = get_token_expiration(token_type)
    to_encode.update(
        {
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "type": token_type,
        }
    )
    encoded_jwt = jwt.encode(to_encode, secret_key, algorithm=ALGORITHM)
    return encoded_jwt


def get_token_expiration(token_type: TokenType) -> datetime:
    """
    Return the expiration date for the given token type.

    Args:
        token_type (TokenType): The type of token for which to get the expiration date.

    Returns:
        datetime: The expiration date for the given token type.

    Raises:
        ValueError: If the token type is not recognized.
    """
    # Get the current time in UTC
    current_time = datetime.now(timezone.utc)
    # Calculate the expiration date based on the token type
    if token_type == TokenType.ACCESS:
        return current_time + timedelta(minutes=15)
    elif token_type == TokenType.REFRESH:
        return current_time + timedelta(days=30)
    else:
        raise ValueError(f"Invalid token type: {token_type}")


def http_basic_or_jwt_token(
    form_data: HTTPBasicCredentials = Depends(httpbasic),
    token: Optional[str] = Depends(oauth2_scheme),
    api_config: dict[str, Any] = Depends(get_api_config),
):
    """
    Authenticate a user using either HTTP Basic or JWT token.

    Args:
        form_data (HTTPBasicCredentials): The HTTP Basic credentials.
        token (str): The JWT token.
        api_config (dict): The API configuration.

    Returns:
        str: The authenticated user's username.

    Raises:
        HTTPException: If the user is not authenticated.
    """
    if token:
        return get_user_from_token(token, api_config.get("jwt_secret_key", "super-secret"))
    elif form_data and verify_auth(api_config, form_data.username, form_data.password):
        return form_data.username

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized",
    )


@router_login.post("/token/login", response_model=AccessAndRefreshToken)
def token_login(
    form_data: HTTPBasicCredentials = Depends(security), api_config=Depends(get_api_config)
):
    """
    Authenticate a user and generate access and refresh tokens.

    Args:
        form_data (HTTPBasicCredentials): The HTTP Basic credentials.
        api_config (dict): The API configuration.

    Returns:
        Dict[str, str]: The access and refresh tokens.

    Raises:
        HTTPException: If the provided credentials are invalid.
    """
    if verify_auth(api_config, form_data.username, form_data.password):
        # Prepare token data with the user's identity
        token_data = {"identity": {"u": form_data.username}}
        access_token = create_token(
            token_data,
            api_config.get("jwt_secret_key", "super-secret"),
            token_type=TokenType.ACCESS
        )
        refresh_token = create_token(
            token_data,
            api_config.get("jwt_secret_key", "super-secret"),
            token_type=TokenType.REFRESH
        )
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )


@router_login.post("/token/refresh", response_model=AccessToken)
def token_refresh(
        token: str = Depends(oauth2_scheme), api_config=Depends(get_api_config)) -> dict[str, str]:
    """
    Refresh the access token using the provided refresh token.

    Args:
        token (str): The refresh token.
        api_config (dict): The API configuration.

    Returns:
        Dict[str, str]: The new access token.

    Raises:
        HTTPException: If the provided token is not a valid refresh token.
    """
    u = get_user_from_token(token, api_config.get("jwt_secret_key", "super-secret"), "refresh")
    token_data = {"identity": {"u": u}}
    access_token = create_token(
        token_data,
        api_config.get("jwt_secret_key", "super-secret"),
        token_type=TokenType.ACCESS,
    )
    return {"access_token": access_token}
