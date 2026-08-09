import json
import time
import urllib.error
import urllib.request


class MiMoError(Exception):
    pass


class StreamStopped(Exception):
    pass


class MiMoClient:
    def __init__(self, api_key, base_url="https://api.xiaomimimo.com/v1",
                 model="mimo-v2.5-pro", temperature=0.7, max_tokens=2048,
                 system_prompt="你是MiMo,小米公司研发的AI智能助手,请根据用户提供的OCR识别文本回答问题。"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.system_prompt = system_prompt

    def stream_chat(self, user_text, stop_event=None):
        url = self.base_url + "/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_text},
            ],
            "temperature": self.temperature,
            "max_completion_tokens": self.max_tokens,
            "stream": True,
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url, data=body, method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + self.api_key,
                "Accept": "text/event-stream",
            },
        )
        try:
            response = urllib.request.urlopen(request, timeout=120)
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")
            raise MiMoError("HTTP {}: {}".format(error.code, detail[:500]))
        except urllib.error.URLError as error:
            raise MiMoError("网络错误: {}".format(error.reason))
        with response:
            if stop_event is not None and stop_event.is_set():
                response.close()
                raise StreamStopped()
            for raw_line in response:
                if stop_event is not None and stop_event.is_set():
                    response.close()
                    raise StreamStopped()
                line = raw_line.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if "error" in chunk:
                    raise MiMoError(str(chunk["error"]))
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                content = delta.get("content")
                if content:
                    yield content

    def test_connection(self):
        url = self.base_url + "/chat/completions"
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": '不要推理，直接返回"1"给我'}],
            "temperature": 0,
            "max_completion_tokens": 500,
            "stream": True,
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url, data=body, method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + self.api_key,
                "Accept": "text/event-stream",
            },
        )
        start = time.monotonic()
        first_token_at = None
        content_parts = []
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                for raw_line in response:
                    line = raw_line.decode("utf-8", "replace").strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data or data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    content = delta.get("content")
                    if content:
                        if first_token_at is None:
                            first_token_at = time.monotonic()
                        content_parts.append(content)
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")
            raise MiMoError("HTTP {}: {}".format(error.code, detail[:300]))
        except urllib.error.URLError as error:
            raise MiMoError("网络错误: {}".format(error.reason))
        if first_token_at is None:
            raise MiMoError("响应为空")
        content = "".join(content_parts)
        return content, first_token_at - start
