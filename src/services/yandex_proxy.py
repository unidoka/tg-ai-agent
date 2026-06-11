import json
import aiohttp
from aiohttp import web

async def proxy_handler(request):
    """Перехватывает запрос от Aider, сует туда reasoning_effort=none и шлет в Яндекс"""
    target_url = "https://ai.api.cloud.yandex.net/v1/chat/completions"
    
    headers = {k: v for k, v in request.headers.items() if k.lower() not in ['host', 'content-length']}
    body = await request.json()
    
    # Отключаем deep think, который ломает API Яндекса
    body["reasoning_effort"] = "none"
    
    connector = aiohttp.TCPConnector(use_dns_cache=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        try:
            async with session.post(target_url, json=body, headers=headers, timeout=120) as resp:
                res_bytes = await resp.read()
                
                # Защитный пост-фильтр текста от тегов <think>
                try:
                    res_json = json.loads(res_bytes.decode('utf-8'))
                    if "choices" in res_json and len(res_json["choices"]) > 0:
                        content = res_json["choices"][0]["message"].get("content", "")
                        if "</think>" in content:
                            res_json["choices"][0]["message"]["content"] = content.split("</think>")[-1].strip()
                            res_bytes = json.dumps(res_json).encode('utf-8')
                except Exception:
                    pass

                return web.Response(
                    body=res_bytes, 
                    status=resp.status, 
                    headers={k: v for k, v in resp.headers.items() if k.lower() not in ['content-encoding', 'transfer-encoding', 'content-length']}
                )
        except Exception as e:
            return web.Response(text=f"Proxy Error: {str(e)}", status=500)


class YandexApiProxy:
    """Управляющий класс для локального прокси-сервера"""
    def __init__(self, host='127.0.0.1', port=28394):
        self.host = host
        self.port = port
        self.runner = None

    async def start(self):
        app = web.Application()
        app.router.add_post('/chat/completions', proxy_handler)
        app.router.add_post('/v1/chat/completions', proxy_handler)
        
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, self.host, self.port)
        await site.start()
        print(f"🚀 Локальный Yandex-прокси запущен на http://{self.host}:{self.port}")

    async def stop(self):
        if self.runner:
            await self.runner.cleanup()
            print("🛑 Локальный Yandex-прокси остановлен.")