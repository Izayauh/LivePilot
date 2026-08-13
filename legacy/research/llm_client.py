"""
LLM Client Abstraction Layer (PATCHED)

Uses google-generativeai (stable) instead of google-genai (alpha).
"""

import os
import asyncio
import json
import hashlib
import requests
import subprocess
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from dotenv import load_dotenv

load_dotenv()

@dataclass
class LLMResponse:
    content: str
    parsed_data: Optional[Dict[str, Any]] = None
    model: str = ""
    tokens_used: int = 0
    success: bool = True
    error: Optional[str] = None

@dataclass 
class ExtractionResult:
    devices: List[Dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    raw_response: str = ""
    source: str = ""
    error: Optional[str] = None

class BaseLLMClient(ABC):
    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: str = None,
        model_id: Optional[str] = None
    ) -> LLMResponse:
        pass
    
    @abstractmethod
    async def extract_structured(
        self,
        content: str,
        schema: Dict = None,
        context: str = "",
        model_id: Optional[str] = None
    ) -> ExtractionResult:
        pass

class GeminiClient(BaseLLMClient):
    """
    Google Gemini client using google-generativeai SDK (Stable).
    """
    
    def __init__(self, api_key: str = None, model_id: str = "gemini-2.0-flash"):
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        self.default_model_id = model_id
        self._model = None
        self._models: Dict[str, Any] = {}
        self._initialized = False
        self._response_cache: Dict[str, LLMResponse] = {}
        
        if not self.api_key:
            print("[GeminiClient] Warning: No API key found. Set GOOGLE_API_KEY env var.")
    
    def _ensure_initialized(self, model_id: Optional[str] = None):
        target_model_id = model_id or self.default_model_id

        if target_model_id in self._models:
            self._model = self._models[target_model_id]
            return self._model

        if not self.api_key:
            return None

        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self._models[target_model_id] = genai.GenerativeModel(target_model_id)
            self._model = self._models[target_model_id]
            self._initialized = True
            return self._model
        except Exception as e:
            print(f"[GeminiClient] Failed to initialize model {target_model_id}: {e}")
            return None

    def _build_cache_key(self, prompt: str, system_prompt: Optional[str], model_id: str) -> str:
        payload = f"{model_id}|{system_prompt or ''}|{prompt}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    async def generate(
        self,
        prompt: str,
        system_prompt: str = None,
        model_id: Optional[str] = None
    ) -> LLMResponse:
        target_model_id = model_id or self.default_model_id
        cache_key = self._build_cache_key(prompt, system_prompt, target_model_id)

        cached = self._response_cache.get(cache_key)
        if cached:
            return cached

        model = self._ensure_initialized(target_model_id)
        if not model:
            return LLMResponse(content="", success=False, error="Gemini client not initialized.")
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"

        max_attempts = max(1, int(os.getenv("RESEARCH_LLM_MAX_RETRIES", "3")))
        base_delay = float(os.getenv("RESEARCH_LLM_RETRY_BASE_DELAY_SEC", "2.0"))

        for attempt in range(1, max_attempts + 1):
            try:
                response = await model.generate_content_async(full_prompt)

                llm_response = LLMResponse(
                    content=response.text,
                    model=target_model_id,
                    success=True
                )

                self._response_cache[cache_key] = llm_response
                return llm_response
            except Exception as e:
                err = str(e)
                is_quota = ("RESOURCE_EXHAUSTED" in err) or ("429" in err)
                if (not is_quota) or (attempt >= max_attempts):
                    return LLMResponse(content="", success=False, error=err)

                wait_s = base_delay * (2 ** (attempt - 1))
                print(f"[GeminiClient] quota/rate limited; retrying in {wait_s:.1f}s (attempt {attempt}/{max_attempts})")
                await asyncio.sleep(wait_s)

        return LLMResponse(content="", success=False, error="LLM generation failed after retries")
    
    async def extract_structured(
        self,
        content: str,
        schema: Dict = None,
        context: str = "",
        model_id: Optional[str] = None
    ) -> ExtractionResult:
        extraction_prompt = self._build_extraction_prompt(content, context)
        response = await self.generate(extraction_prompt, model_id=model_id)
        
        if not response.success:
            return ExtractionResult(error=response.error, raw_response=response.content)
        
        try:
            parsed = self._parse_extraction_response(response.content)
            return ExtractionResult(
                devices=parsed.get("devices", []),
                confidence=parsed.get("confidence", 0.5),
                raw_response=response.content,
                source=context
            )
        except Exception as e:
            return ExtractionResult(error=f"Failed to parse response: {e}", raw_response=response.content)

    def _build_extraction_prompt(self, content: str, context: str = "") -> str:
        system_context = """You are an expert audio engineer assistant. Your task is to extract 
specific audio plugin settings from the provided content (tutorial transcript, article, etc.).

Focus on extracting:
1. Plugin/device names (EQ, Compressor, Reverb, Saturator, Delay, etc.)
2. Specific parameter values with units (threshold: -18dB, attack: 10ms, etc.)
3. The intended purpose of each setting (cut mud, add presence, control dynamics, etc.)

Return your response as valid JSON with this structure:
{
    "devices": [
        {
            "name": "Plugin Name (e.g., EQ Eight, Compressor)",
            "category": "eq|compressor|reverb|delay|saturation|dynamics",
            "purpose": "Brief description of what this device does in the chain",
            "parameters": {
                "parameter_name": {
                    "value": numeric_value,
                    "unit": "dB|Hz|ms|%|ratio",
                    "confidence": 0.0-1.0
                }
            },
            "reasoning": "Why this setting was extracted from the content"
        }
    ],
    "chain_order": ["First device", "Second device", ...],
    "style_description": "Brief description of the overall sound/style",
    "confidence": 0.0-1.0
}"""
        user_prompt = f"""Context: {context if context else "General audio production tutorial"}

Content to analyze:
---
{content[:15000]}  
---

Extract settings. Return ONLY valid JSON."""
        return f"{system_context}\n\n{user_prompt}"

    def _parse_extraction_response(self, response: str) -> Dict[str, Any]:
        response = response.strip()
        if response.startswith("```json"): response = response[7:]
        if response.startswith("```"): response = response[3:]
        if response.endswith("```"): response = response[:-3]
        response = response.strip()
        
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0:
                try: return json.loads(response[start:end])
                except: pass
        return {"devices": [], "confidence": 0.0, "error": "JSON Parse Error"}



_RATE_LIMIT_HINTS = ("rate_limit", "cooldown", "failovererror", "all models failed", "429", "resource_exhausted")

def _looks_like_rate_limit(text: str) -> bool:
    """Return True if *text* contains a rate-limit / cooldown indicator."""
    lower = text.lower()
    return any(h in lower for h in _RATE_LIMIT_HINTS)


class OpenClawRelayClient(BaseLLMClient):
    """Relay client that forwards prompts through local OpenClaw auth session via CLI.

    Includes exponential-backoff retry on rate-limit errors so that transient
    provider cooldowns don't immediately surface as hard failures.
    """

    def __init__(self):
        self.session_id = os.getenv("RESEARCH_OPENCLAW_SESSION_ID", "").strip()
        self.agent_id = os.getenv("RESEARCH_OPENCLAW_AGENT_ID", "main").strip() or "main"
        self.timeout_s = int(os.getenv("RESEARCH_OPENCLAW_TIMEOUT_SEC", "45"))
        self.max_retries = max(1, int(os.getenv("RESEARCH_LLM_MAX_RETRIES", "3")))
        self.base_delay = float(os.getenv("RESEARCH_LLM_RETRY_BASE_DELAY_SEC", "2.0"))
        self._response_cache: Dict[str, LLMResponse] = {}

    def _build_cache_key(self, prompt: str, system_prompt: Optional[str], model_id: str) -> str:
        payload = f"{model_id}|{system_prompt or ''}|{prompt}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    async def _call_once(self, full_prompt: str) -> tuple:
        """Single subprocess call.  Returns (proc | None, error_str)."""
        cmd = ["openclaw", "agent", "--json", "--timeout", str(self.timeout_s),
               "--message", full_prompt]
        if self.session_id:
            cmd.extend(["--session-id", self.session_id])
        else:
            cmd.extend(["--agent", self.agent_id])

        try:
            proc = await asyncio.to_thread(
                subprocess.run, cmd,
                capture_output=True, text=True,
                timeout=self.timeout_s + 10,
            )
            return proc, ""
        except Exception as e:
            return None, str(e)

    async def generate(self, prompt: str, system_prompt: str = None, model_id: Optional[str] = None) -> LLMResponse:
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        target = model_id or "openclaw-relay"
        cache_key = self._build_cache_key(full_prompt, None, target)
        if cache_key in self._response_cache:
            return self._response_cache[cache_key]

        last_error = ""

        for attempt in range(1, self.max_retries + 1):
            proc, exec_err = await self._call_once(full_prompt)

            if exec_err:
                last_error = f"OpenClaw relay execution failed: {exec_err}"
                if _looks_like_rate_limit(exec_err) and attempt < self.max_retries:
                    wait_s = self.base_delay * (2 ** (attempt - 1))
                    print(f"[OpenClawRelay] Rate limit (attempt {attempt}/{self.max_retries}), retrying in {wait_s:.1f}s")
                    await asyncio.sleep(wait_s)
                    continue
                return LLMResponse(content="", success=False, error=last_error)

            if proc.returncode != 0:
                err_text = (proc.stderr or proc.stdout or "").strip()
                last_error = f"OpenClaw relay failed: {err_text[:500]}"
                if _looks_like_rate_limit(err_text) and attempt < self.max_retries:
                    wait_s = self.base_delay * (2 ** (attempt - 1))
                    print(f"[OpenClawRelay] Rate limit (attempt {attempt}/{self.max_retries}), retrying in {wait_s:.1f}s")
                    await asyncio.sleep(wait_s)
                    continue
                return LLMResponse(content="", success=False, error=last_error)

            # --- success path ---
            raw = (proc.stdout or "").strip()
            content = ""
            try:
                data = json.loads(raw)
                content = (
                    data.get("reply")
                    or data.get("message")
                    or data.get("output")
                    or data.get("text")
                    or ""
                )
                if not content and isinstance(data.get("result"), dict):
                    result = data["result"]
                    content = (
                        result.get("reply")
                        or result.get("message")
                        or result.get("output")
                        or result.get("text")
                        or ""
                    )

                    # Current OpenClaw schema: result.payloads[].text
                    if not content and isinstance(result.get("payloads"), list):
                        payload_text = []
                        for payload in result.get("payloads", []):
                            if isinstance(payload, dict):
                                text = payload.get("text")
                                if isinstance(text, str) and text.strip():
                                    payload_text.append(text.strip())
                        if payload_text:
                            content = "\n\n".join(payload_text)
            except Exception:
                content = raw

            if not content:
                return LLMResponse(content="", success=False, error="OpenClaw relay returned empty response")

            resp = LLMResponse(content=content, model=target, success=True)
            self._response_cache[cache_key] = resp
            return resp

        return LLMResponse(content="", success=False, error=last_error or "OpenClaw relay: all retries exhausted")

    async def extract_structured(self, content: str, schema: Dict = None, context: str = "", model_id: Optional[str] = None) -> ExtractionResult:
        prompt = (
            "Extract plugin settings and return strict JSON with keys: devices, chain_order, style_description, confidence.\n"
            f"Context: {context}\n\nContent:\n{content[:15000]}"
        )
        response = await self.generate(prompt, model_id=model_id)
        if not response.success:
            return ExtractionResult(error=response.error, raw_response=response.content)
        try:
            parsed = json.loads(response.content)
        except Exception:
            parsed = {"devices": [], "confidence": 0.0, "error": "JSON Parse Error"}
        return ExtractionResult(
            devices=parsed.get("devices", []),
            confidence=parsed.get("confidence", 0.5),
            raw_response=response.content,
            source=context,
            error=parsed.get("error"),
        )


class OpenAIClient(BaseLLMClient):
    """OpenAI Chat Completions client with async wrapper + retries."""

    def __init__(self, api_key: str = None, model_id: str = "gpt-4o-mini"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.default_model_id = os.getenv("RESEARCH_OPENAI_MODEL", model_id)
        self.base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self._response_cache: Dict[str, LLMResponse] = {}

        if not self.api_key:
            print("[OpenAIClient] Warning: No API key found. Set OPENAI_API_KEY env var.")

    def _build_cache_key(self, prompt: str, system_prompt: Optional[str], model_id: str) -> str:
        payload = f"{model_id}|{system_prompt or ''}|{prompt}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    async def generate(
        self,
        prompt: str,
        system_prompt: str = None,
        model_id: Optional[str] = None
    ) -> LLMResponse:
        target_model_id = model_id or self.default_model_id
        cache_key = self._build_cache_key(prompt, system_prompt, target_model_id)
        cached = self._response_cache.get(cache_key)
        if cached:
            return cached

        if not self.api_key:
            return LLMResponse(content="", success=False, error="OpenAI client not initialized.")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": target_model_id,
            "messages": messages,
            "temperature": 0.2,
        }

        max_attempts = max(1, int(os.getenv("RESEARCH_LLM_MAX_RETRIES", "3")))
        base_delay = float(os.getenv("RESEARCH_LLM_RETRY_BASE_DELAY_SEC", "2.0"))

        for attempt in range(1, max_attempts + 1):
            try:
                def _do_request():
                    return requests.post(
                        f"{self.base_url.rstrip('/')}/chat/completions",
                        headers=headers,
                        json=payload,
                        timeout=60,
                    )

                response = await asyncio.to_thread(_do_request)
                if response.status_code >= 400:
                    err = f"HTTP {response.status_code}: {response.text[:500]}"
                    is_retryable = response.status_code in {429, 500, 502, 503, 504}
                    if (not is_retryable) or (attempt >= max_attempts):
                        return LLMResponse(content="", success=False, error=err)
                    await asyncio.sleep(base_delay * (2 ** (attempt - 1)))
                    continue

                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                llm_response = LLMResponse(content=content or "", model=target_model_id, success=True)
                self._response_cache[cache_key] = llm_response
                return llm_response
            except Exception as e:
                if attempt >= max_attempts:
                    return LLMResponse(content="", success=False, error=str(e))
                await asyncio.sleep(base_delay * (2 ** (attempt - 1)))

        return LLMResponse(content="", success=False, error="OpenAI generation failed after retries")

    async def extract_structured(
        self,
        content: str,
        schema: Dict = None,
        context: str = "",
        model_id: Optional[str] = None
    ) -> ExtractionResult:
        extraction_prompt = self._build_extraction_prompt(content, context)
        response = await self.generate(extraction_prompt, model_id=model_id)
        if not response.success:
            return ExtractionResult(error=response.error, raw_response=response.content)

        parsed = self._parse_extraction_response(response.content)
        return ExtractionResult(
            devices=parsed.get("devices", []),
            confidence=parsed.get("confidence", 0.5),
            raw_response=response.content,
            source=context,
            error=parsed.get("error")
        )

    def _build_extraction_prompt(self, content: str, context: str = "") -> str:
        return (
            "You are an expert audio engineer assistant. Extract specific plugin settings and return JSON only.\n"
            "JSON shape: {\"devices\":[...],\"chain_order\":[],\"style_description\":\"\",\"confidence\":0.0}\n\n"
            f"Context: {context if context else 'General audio production tutorial'}\n\n"
            f"Content to analyze:\n---\n{content[:15000]}\n---\n\nExtract settings. Return ONLY valid JSON."
        )

    def _parse_extraction_response(self, response: str) -> Dict[str, Any]:
        response = (response or "").strip()
        if response.startswith("```json"):
            response = response[7:]
        if response.startswith("```"):
            response = response[3:]
        if response.endswith("```"):
            response = response[:-3]
        response = response.strip()
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(response[start:end])
                except Exception:
                    pass
        return {"devices": [], "confidence": 0.0, "error": "JSON Parse Error"}


class ResearchLLMClient:
    def __init__(self, client: BaseLLMClient = None):
        self.clients: List[BaseLLMClient] = []

        if client is not None:
            self.clients = [client]
        else:
            provider_order = os.getenv("RESEARCH_LLM_PROVIDER_ORDER", "openai,gemini")
            providers = [p.strip().lower() for p in provider_order.split(",") if p.strip()]
            if not providers:
                providers = ["openai", "gemini"]

            for provider in providers:
                if provider == "openclaw":
                    self.clients.append(OpenClawRelayClient())
                elif provider == "openai":
                    oc = OpenAIClient()
                    if oc.api_key:
                        self.clients.append(oc)
                elif provider == "gemini":
                    gc = GeminiClient()
                    if gc.api_key:
                        self.clients.append(gc)

            if not self.clients:
                self.clients = [GeminiClient()]

        self.client = self.clients[0]

    async def _generate_with_fallback(self, prompt: str, system_prompt: str = None, model_id: Optional[str] = None) -> LLMResponse:
        last_error = "No LLM provider configured"
        for c in self.clients:
            resp = await c.generate(prompt, system_prompt=system_prompt, model_id=model_id)
            if resp.success:
                self.client = c
                return resp
            last_error = resp.error or last_error
            print(f"[ResearchLLMClient] Provider failed ({c.__class__.__name__}): {last_error}")
        return LLMResponse(content="", success=False, error=last_error)

    async def extract_vocal_chain_from_transcript(self, transcript: str, artist: str = "", song: str = "", model_id: Optional[str] = None) -> ExtractionResult:
        context = "Vocal chain settings"
        if artist:
            context += f" for {artist}"
        if song:
            context += f" - {song}"

        last_error = "No provider available"
        for c in self.clients:
            result = await c.extract_structured(transcript, context=context, model_id=model_id)
            if not result.error:
                self.client = c
                return result
            last_error = result.error
        return ExtractionResult(error=last_error, raw_response="")

    async def extract_vocal_chain_from_article(self, article: str, source_url: str = "", title: str = "", model_id: Optional[str] = None) -> ExtractionResult:
        last_error = "No provider available"
        for c in self.clients:
            result = await c.extract_structured(article, context=f"Tutorial: {title}", model_id=model_id)
            if not result.error:
                self.client = c
                return result
            last_error = result.error
        return ExtractionResult(error=last_error, raw_response="")

    async def analyze_vocal_intent(self, query: str, model_id: Optional[str] = None) -> Dict[str, Any]:
        prompt = (
            f"Analyze this vocal processing query and extract the intent:\n"
            f"Query: \"{query}\"\n"
            "Return JSON with: { \"artist\": \"...\", \"song\": \"...\", \"style\": \"...\", \"characteristics\": [], \"processing_goals\": [] }"
        )
        response = await self._generate_with_fallback(prompt, model_id=model_id)
        if not response.success:
            return {"error": response.error}

        content = (response.content or "").strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        try:
            res = json.loads(content)
            res["original_query"] = query
            return res
        except Exception:
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    res = json.loads(content[start:end])
                    res["original_query"] = query
                    return res
                except Exception:
                    pass
            return {"query": query}

    async def generate_chain_reasoning(self, devices: List[Dict], intent: Dict, model_id: Optional[str] = None) -> str:
        prompt = f"Explain this chain for {json.dumps(intent)}: {json.dumps(devices)}. Keep it brief (2 sentences)."
        response = await self._generate_with_fallback(prompt, model_id=model_id)
        return response.content if response.success else "Chain extracted."

_research_llm = None
def get_research_llm() -> ResearchLLMClient:
    global _research_llm
    if _research_llm is None: _research_llm = ResearchLLMClient()
    return _research_llm

async def extract_settings_from_text(text: str, context: str = "") -> ExtractionResult:
    """Convenience function for direct extraction"""
    client = get_research_llm()
    return await client.client.extract_structured(text, context=context)
