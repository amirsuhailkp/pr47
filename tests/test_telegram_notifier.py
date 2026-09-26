import pytest

from alerts.telegram.notifier import TelegramNotifier, TelegramSendError


@pytest.mark.asyncio
async def test_send_success():
    async def transport(chat_id, body):
        assert chat_id == "123"
        assert body["text"] == "hello"
        return {"ok": True}

    notifier = TelegramNotifier(bot_token="tok", chat_id="123", transport=transport)
    await notifier.send({"text": "hello"})  # no raise


@pytest.mark.asyncio
async def test_send_missing_text_raises():
    async def transport(chat_id, body):
        return {"ok": True}

    notifier = TelegramNotifier(bot_token="tok", chat_id="123", transport=transport)
    with pytest.raises(TelegramSendError):
        await notifier.send({})


@pytest.mark.asyncio
async def test_send_raises_on_not_ok_response():
    async def transport(chat_id, body):
        return {"ok": False, "description": "chat not found"}

    notifier = TelegramNotifier(bot_token="tok", chat_id="123", transport=transport)
    with pytest.raises(TelegramSendError):
        await notifier.send({"text": "hi"})


@pytest.mark.asyncio
async def test_send_wraps_transport_exception():
    async def transport(chat_id, body):
        raise ConnectionError("network down")

    notifier = TelegramNotifier(bot_token="tok", chat_id="123", transport=transport)
    with pytest.raises(TelegramSendError):
        await notifier.send({"text": "hi"})


@pytest.mark.asyncio
async def test_health_unconfigured_without_token():
    notifier = TelegramNotifier(bot_token="", chat_id="123", transport=lambda *a: None)
    health = await notifier.health()
    assert health["status"] == "UNCONFIGURED"
