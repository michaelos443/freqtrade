import logging
import time
from typing import Any, Dict

from fastapi import APIRouter, Depends
from fastapi.websockets import WebSocket
from pydantic import ValidationError

from freqtrade.enums import RPCMessageType, RPCRequestType
from freqtrade.exceptions import FreqtradeException
from freqtrade.rpc.api_server.api_auth import validate_ws_token
from freqtrade.rpc.api_server.deps import get_message_stream, get_rpc
from freqtrade.rpc.api_server.ws.channel import WebSocketChannel, create_channel
from freqtrade.rpc.api_server.ws.message_stream import MessageStream
from freqtrade.rpc.api_server.ws_schemas import (
    WSAnalyzedDFMessage,
    WSErrorMessage,
    WSMessageSchema,
    WSRequestSchema,
    WSWhitelistMessage,
)
from freqtrade.rpc.rpc import RPC


logger = logging.getLogger(__name__)

# Private router, protected by API Key authentication
router = APIRouter()

DELAY_THRESHOLD = 60
DEFAULT_CANDLE_LIMIT = 1500



async def channel_reader(channel: WebSocketChannel, rpc: RPC):
    """
    Iterate over the messages from the channel and process the request
    """
    async for message in channel:
        try:
            await _process_consumer_request(message, channel, rpc)
        except FreqtradeException:
            logger.exception(f"Error processing request from {channel}")
            response = WSErrorMessage(data="Error processing request")

            await channel.send(response.dict(exclude_none=True))


async def channel_broadcaster(channel: WebSocketChannel, message_stream: MessageStream):
    """
    Iterate over messages in the message stream and send them
    """
    async for message, ts in message_stream:
        if channel.subscribed_to(message.get("type")):
            # Log a warning if this channel is behind
            # on the message stream by a lot
            now = time.time()
            if (now - ts) > DELAY_THRESHOLD:
                logger.warning(
                    f"Channel {channel} is behind MessageStream by 1 minute,"
                    " this can cause a memory leak if you see this message"
                    " often, consider reducing pair list size or amount of"
                    " consumers."
                )

            asyncio.create_task(channel.send(message, use_timeout=True))


async def _process_consumer_request(
    request: Dict[str, Any],
    channel: WebSocketChannel,
    rpc: RPC
) -> None:
    """
    Validate and handle a request from a WebSocket consumer.

    :param request: The request from the consumer
    :param channel: The WebSocketChannel object for the WebSocket
    :param rpc: The RPC object for the bot
    """
    # Validate the request, makes sure it matches the schema
    try:
        websocket_request = WSRequestSchema.model_validate(request)
    except ValidationError as e:
        logger.error(f"Invalid request from {channel}: {e}")
        return

    type_, data = websocket_request.type, websocket_request.data
    response: Optional[WSMessageSchema] = None

    logger.debug(f"Request of type {type_} from {channel}")

    # If we have a request of type SUBSCRIBE, set the topics in this channel
    if type_ == RPCRequestType.SUBSCRIBE:
        # Early return if no data is passed
        if not data:
            logger.error(
                f"Empty data passed for request of type {type_} from {channel}"
            )
            return

        # If all topics passed are a valid RPCMessageType, set subscriptions on channel
        if all(any(x.value == topic for x in RPCMessageType) for topic in data):
            channel.set_subscriptions(data)
            logger.debug(f"Subscribed to {data} for {channel}")
        else:
            logger.warning(
                f"Invalid topics in SUBSCRIBE request from {channel}: {data}"
            )

        # We don't send a response for subscriptions
        return

    elif type_ == RPCRequestType.WHITELIST:
        # Get whitelist
        whitelist = rpc._ws_request_whitelist()

        # Format response
        response = WSWhitelistMessage(data=whitelist)
        logger.debug(f"Sending whitelist to {channel}")
        await channel.send(response.model_dump(exclude_none=True))

    elif type_ == RPCRequestType.ANALYZED_DF:
        # Limit the amount of candles per dataframe to 'limit' or 1500
        limit = min(
            int(data.get("limit", DEFAULT_CANDLE_LIMIT)), DEFAULT_CANDLE_LIMIT
        ) if data else None
        pair = data.get("pair", None) if data else None
        
        if pair and not isinstance(pair, str):
            logger.error(f"Invalid pair passed for request of type {type_} from {channel}")
            return

        # For every pair in the generator, send a separate message
        for message in rpc._ws_request_analyzed_df(limit, pair):
            # Format response
            response = WSAnalyzedDFMessage(data=message)
            logger.debug(f"Sending analyzed_df to {channel}")
            await channel.send(response.model_dump(exclude_none=True))
        return
    else:
        logger.warning(f"Invalid request type {type_} from {channel}")


@router.websocket("/message/ws")
async def message_endpoint(
    websocket: WebSocket,
    token: str = Depends(validate_ws_token),
    rpc: RPC = Depends(get_rpc),
    message_stream: MessageStream = Depends(get_message_stream),
):
    if token:
        async with create_channel(websocket) as channel:
            await channel.run_channel_tasks(
                channel_reader(channel, rpc), channel_broadcaster(channel, message_stream)
            )
