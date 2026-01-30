"""
JARVIS Web Search Plugin

Provides web search functionality using DuckDuckGo.
"""

import asyncio
from typing import Any

from loguru import logger

from jarvis.plugins.base import Plugin, PluginInfo


class WebSearchPlugin(Plugin):
    """Web search plugin using DuckDuckGo."""
    
    @property
    def info(self) -> PluginInfo:
        return PluginInfo(
            name="Web Search",
            description="Search the web for information",
            version="1.0.0",
            commands=[
                "search for", "google", "look up",
                "search the web", "find online",
            ],
            intents=[
                "search", "google", "look up", "find",
                "what is", "who is", "how to", "when did",
                "where is", "why does", "wiki", "define",
            ],
        )
    
    async def execute(self, command: str, params: dict[str, Any]) -> str:
        """Execute web search."""
        query = self._extract_query(command)
        
        if not query:
            return "What would you like me to search for?"
        
        return await self._search(query)
    
    def _extract_query(self, command: str) -> str:
        """Extract search query from command."""
        command_lower = command.lower()
        
        # Remove common prefixes
        prefixes = [
            "search for", "search the web for", "google",
            "look up", "find online", "search",
            "what is", "what are", "who is", "who are",
            "how to", "how do", "when did", "when does",
            "where is", "where are", "why does", "why do",
            "define", "tell me about", "can you search",
            "please search",
        ]
        
        query = command
        for prefix in prefixes:
            if command_lower.startswith(prefix):
                query = command[len(prefix):].strip()
                break
        
        # Clean up
        query = query.strip('?.,!')
        return query
    
    async def _search(self, query: str) -> str:
        """Perform web search."""
        try:
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None, self._search_sync, query
            )
            return results
        except Exception as e:
            logger.error(f"Search error: {e}")
            return f"Search failed: {e}"
    
    def _search_sync(self, query: str) -> str:
        """Synchronous search using DuckDuckGo."""
        try:
            import httpx
            
            # Use DuckDuckGo instant answer API
            url = "https://api.duckduckgo.com/"
            params = {
                "q": query,
                "format": "json",
                "no_html": "1",
                "skip_disambig": "1",
            }
            
            with httpx.Client(timeout=10) as client:
                response = client.get(url, params=params)
                data = response.json()
            
            # Try to get the abstract/answer
            if data.get("AbstractText"):
                return f"**{data.get('Heading', query)}**\n\n{data['AbstractText']}"
            
            if data.get("Answer"):
                return data["Answer"]
            
            # Try related topics
            if data.get("RelatedTopics"):
                topics = data["RelatedTopics"][:3]
                results = []
                for topic in topics:
                    if isinstance(topic, dict) and topic.get("Text"):
                        results.append(f"• {topic['Text'][:200]}")
                
                if results:
                    return f"Results for '{query}':\n\n" + "\n".join(results)
            
            # Fallback - suggest opening browser
            return f"I couldn't find a quick answer for '{query}'. Would you like me to open a browser search?"
            
        except ImportError:
            return "Web search requires the httpx package. Install with: pip install httpx"
        except Exception as e:
            logger.error(f"DuckDuckGo search error: {e}")
            return f"Search error: {e}"
