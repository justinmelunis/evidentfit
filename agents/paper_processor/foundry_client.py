"""
GPT-4o-mini client for paper processing using Azure AI Foundry
Compatible interface with MistralClient for easy migration
"""
import os
import json
import logging
import sys
from pathlib import Path
from typing import Optional, Dict, Any

# Dynamic import to handle path resolution at runtime
def _import_foundry_chat():
    """Import foundry_chat with fallback path resolution"""
    try:
        from api.clients.foundry_chat import chat as foundry_chat
        return foundry_chat
    except ImportError:
        # Fallback: add repo root to path
        repo_root = Path(__file__).parent.parent.parent
        api_path = repo_root / "api"
        if api_path.exists():
            sys.path.insert(0, str(api_path))
            try:
                from clients.foundry_chat import chat as foundry_chat
                return foundry_chat
            except ImportError:
                pass
        raise ImportError("Could not import foundry_chat. Ensure api/clients/foundry_chat.py exists")


log = logging.getLogger("paper_processor.foundry_client")


class GPT4oMiniClient:
    """GPT-4o-mini client for paper processing via Azure AI Foundry"""
    
    def __init__(self, model_name: str = "gpt-4o-mini"):
        """
        Initialize GPT-4o-mini client
        
        Args:
            model_name: Model name (defaults to gpt-4o-mini, can be overridden by env)
        """
        self.model_name = os.getenv("FOUNDATION_CHAT_MODEL", model_name)
        log.info(f"Initialized GPT-4o-mini client (model: {self.model_name})")
        
        # Verify configuration
        if not os.getenv("FOUNDATION_ENDPOINT") or not os.getenv("FOUNDATION_KEY"):
            log.warning("Azure AI Foundry not configured. Set FOUNDATION_ENDPOINT and FOUNDATION_KEY")
    
    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        max_new_tokens: int = 800,
        temperature: float = 0.0
    ) -> Optional[Dict[str, Any]]:
        """
        Generate JSON response from prompts
        
        Args:
            system_prompt: System prompt
            user_prompt: User prompt
            max_new_tokens: Maximum tokens (default 800)
            temperature: Sampling temperature (default 0.0 for deterministic)
        
        Returns:
            Parsed JSON dict or None if parsing fails
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        try:
            # Import here to avoid import errors at module load time
            foundry_chat = _import_foundry_chat()
            response_text = foundry_chat(
                messages=messages,
                model=self.model_name,
                max_tokens=max_new_tokens,
                temperature=temperature
            )
            
            # Try to extract JSON from response
            # Sometimes GPT wraps JSON in markdown code blocks
            response_text = response_text.strip()
            
            # Remove markdown code blocks if present
            if response_text.startswith("```"):
                # Find the JSON block
                lines = response_text.split("\n")
                json_lines = []
                in_json = False
                for line in lines:
                    if line.strip().startswith("```"):
                        if not in_json:
                            in_json = True
                            continue
                        else:
                            break
                    if in_json:
                        json_lines.append(line)
                response_text = "\n".join(json_lines)
            elif response_text.startswith("```json"):
                response_text = response_text[7:].strip()
                if response_text.endswith("```"):
                    response_text = response_text[:-3].strip()
            
            # Parse JSON
            try:
                return json.loads(response_text)
            except json.JSONDecodeError:
                # Try to find JSON object in text
                # Look for first { and last }
                start = response_text.find("{")
                end = response_text.rfind("}")
                if start >= 0 and end > start:
                    try:
                        return json.loads(response_text[start:end+1])
                    except json.JSONDecodeError:
                        pass
                
                log.warning(f"Failed to parse JSON from response: {response_text[:200]}...")
                return None
                
        except Exception as e:
            log.error(f"GPT-4o-mini generation failed: {e}")
            return None
    
    def generate(self, prompt: str, max_new_tokens: int = 800, temperature: float = 0.0) -> str:
        """
        Generate text response (for compatibility)
        
        Args:
            prompt: User prompt
            max_new_tokens: Maximum tokens
            temperature: Sampling temperature
        
        Returns:
            Generated text
        """
        messages = [
            {"role": "user", "content": prompt}
        ]
        
        try:
            # Import here to avoid import errors at module load time
            foundry_chat = _import_foundry_chat()
            return foundry_chat(
                messages=messages,
                model=self.model_name,
                max_tokens=max_new_tokens,
                temperature=temperature
            )
        except Exception as e:
            log.error(f"GPT-4o-mini generation failed: {e}")
            return ""

