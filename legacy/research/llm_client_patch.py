class GeminiClient(BaseLLMClient):
    """
    Google Gemini client using google-generativeai SDK (Stable).
    """
    
    def __init__(self, api_key: str = None, model_id: str = "gemini-1.5-flash"):
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        self.model_id = model_id
        self._model = None
        
        if not self.api_key:
            print("[GeminiClient] Warning: No API key found. Set GOOGLE_API_KEY env var.")
    
    def _ensure_initialized(self):
        if not self._model and self.api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                self._model = genai.GenerativeModel(self.model_id)
            except Exception as e:
                print(f"[GeminiClient] Failed to initialize: {e}")
    
    async def generate(self, prompt: str, system_prompt: str = None) -> LLMResponse:
        self._ensure_initialized()
        
        if not self._model:
            return LLMResponse(content="", success=False, error="Gemini client not initialized.")
        
        try:
            full_prompt = prompt
            if system_prompt:
                full_prompt = f"{system_prompt}\n\n{prompt}"
            
            # Use run_in_executor for async wrapper around sync call if needed, 
            # but generate_content_async is available in newer versions.
            response = await self._model.generate_content_async(full_prompt)
            
            return LLMResponse(
                content=response.text,
                model=self.model_id,
                success=True
            )
            
        except Exception as e:
            return LLMResponse(content="", success=False, error=str(e))
