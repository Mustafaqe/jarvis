"""
JARVIS Image Analysis

Uses Claude Vision API to analyze images, answer questions about them,
and understand visual content.
"""

import asyncio
import base64
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List
import os

from loguru import logger

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


@dataclass
class AnalysisResult:
    """Result of image analysis."""
    response: str
    prompt: str
    model: str
    tokens_used: int
    success: bool
    error: Optional[str] = None


class ImageAnalyzer:
    """
    Analyze images using Claude Vision API.
    
    Features:
    - Image description
    - Question answering about images
    - Screen content understanding
    - Chart/diagram interpretation
    - Error message reading
    """
    
    def __init__(self, config):
        """
        Initialize image analyzer.
        
        Args:
            config: Configuration object
        """
        self.config = config
        self.provider = config.get("vision.analysis_provider", "anthropic")
        self.model = config.get("ai.llm.model", "claude-3-5-sonnet-20241022")
        
        self._client = None
    
    def _get_client(self):
        """Get or create API client."""
        if self._client is not None:
            return self._client
        
        if self.provider == "anthropic":
            try:
                import anthropic
                api_key = os.getenv("ANTHROPIC_API_KEY")
                if not api_key:
                    raise RuntimeError("ANTHROPIC_API_KEY not set")
                self._client = anthropic.Anthropic(api_key=api_key)
            except ImportError:
                raise RuntimeError("anthropic package not installed")
        else:
            raise RuntimeError(f"Unsupported vision provider: {self.provider}")
        
        return self._client
    
    def _image_to_base64(self, image: "Image.Image", format: str = "PNG") -> str:
        """Convert PIL Image to base64 string."""
        buffer = io.BytesIO()
        image.save(buffer, format=format)
        return base64.standard_b64encode(buffer.getvalue()).decode("utf-8")
    
    def _get_media_type(self, format: str) -> str:
        """Get media type for image format."""
        media_types = {
            "PNG": "image/png",
            "JPEG": "image/jpeg",
            "JPG": "image/jpeg",
            "GIF": "image/gif",
            "WEBP": "image/webp",
        }
        return media_types.get(format.upper(), "image/png")
    
    async def analyze(
        self,
        image: "Image.Image",
        prompt: str,
        context: Optional[str] = None
    ) -> AnalysisResult:
        """
        Analyze image with a custom prompt.
        
        Args:
            image: PIL Image to analyze
            prompt: Question or instruction about the image
            context: Optional context about what the image is
            
        Returns:
            AnalysisResult with response
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._analyze_sync, image, prompt, context
        )
    
    def _analyze_sync(
        self,
        image: "Image.Image",
        prompt: str,
        context: Optional[str] = None
    ) -> AnalysisResult:
        """Synchronous analysis."""
        try:
            client = self._get_client()
            
            # Convert image to base64
            image_data = self._image_to_base64(image)
            
            # Build system prompt
            system_prompt = """You are JARVIS, an AI assistant analyzing visual content.
Provide clear, concise, and helpful analysis of what you see.
If analyzing a screen, focus on the most relevant information.
For error messages, explain what the error means and suggest solutions."""
            
            if context:
                system_prompt += f"\n\nContext: {context}"
            
            # Call Claude Vision
            message = client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": image_data,
                                },
                            },
                            {
                                "type": "text",
                                "text": prompt,
                            }
                        ],
                    }
                ],
            )
            
            response_text = message.content[0].text
            tokens = message.usage.input_tokens + message.usage.output_tokens
            
            return AnalysisResult(
                response=response_text,
                prompt=prompt,
                model=self.model,
                tokens_used=tokens,
                success=True
            )
            
        except Exception as e:
            logger.error(f"Image analysis failed: {e}")
            return AnalysisResult(
                response="",
                prompt=prompt,
                model=self.model,
                tokens_used=0,
                success=False,
                error=str(e)
            )
    
    async def describe(self, image: "Image.Image") -> str:
        """
        Describe what's in the image.
        
        Args:
            image: PIL Image to describe
            
        Returns:
            Description of the image
        """
        result = await self.analyze(
            image,
            "Describe what you see in this image in detail. "
            "Include any text, UI elements, or notable features."
        )
        return result.response if result.success else f"Error: {result.error}"
    
    async def read_screen(self, image: "Image.Image") -> str:
        """
        Read and understand screen content.
        
        Args:
            image: Screenshot to analyze
            
        Returns:
            Summary of screen content
        """
        result = await self.analyze(
            image,
            "This is a screenshot. Please describe:\n"
            "1. What application or window is shown\n"
            "2. The main content visible\n"
            "3. Any important text, messages, or notifications\n"
            "4. Any errors or warnings if visible\n"
            "Be concise but thorough.",
            context="This is a computer screenshot for analysis"
        )
        return result.response if result.success else f"Error: {result.error}"
    
    async def read_error(self, image: "Image.Image") -> str:
        """
        Read and explain error messages from screenshot.
        
        Args:
            image: Screenshot containing error
            
        Returns:
            Explanation of error and possible solutions
        """
        result = await self.analyze(
            image,
            "This screenshot contains an error message or problem. Please:\n"
            "1. Identify and read the error message\n"
            "2. Explain what the error means\n"
            "3. Suggest possible solutions\n"
            "4. Rate the severity (low/medium/high)",
            context="Screenshot of an error message for troubleshooting"
        )
        return result.response if result.success else f"Error: {result.error}"
    
    async def answer_question(self, image: "Image.Image", question: str) -> str:
        """
        Answer a specific question about the image.
        
        Args:
            image: PIL Image
            question: Question to answer
            
        Returns:
            Answer to the question
        """
        result = await self.analyze(image, question)
        return result.response if result.success else f"Error: {result.error}"
    
    async def analyze_chart(self, image: "Image.Image") -> str:
        """
        Analyze a chart or graph.
        
        Args:
            image: Image of chart/graph
            
        Returns:
            Analysis of the chart
        """
        result = await self.analyze(
            image,
            "Analyze this chart or graph:\n"
            "1. What type of chart is this?\n"
            "2. What data does it represent?\n"
            "3. What are the key insights or trends?\n"
            "4. What are the axis labels and values?\n"
            "Provide a clear interpretation of the data.",
            context="Chart or graph for data analysis"
        )
        return result.response if result.success else f"Error: {result.error}"
    
    async def analyze_code(self, image: "Image.Image") -> str:
        """
        Analyze code shown in screenshot.
        
        Args:
            image: Screenshot of code
            
        Returns:
            Analysis of the code
        """
        result = await self.analyze(
            image,
            "Analyze this code screenshot:\n"
            "1. What programming language is this?\n"
            "2. What does this code do?\n"
            "3. Are there any issues or bugs visible?\n"
            "4. Suggest any improvements if applicable.",
            context="Code screenshot for analysis"
        )
        return result.response if result.success else f"Error: {result.error}"
    
    async def find_text(self, image: "Image.Image", target: str) -> str:
        """
        Find specific text in the image.
        
        Args:
            image: Image to search
            target: Text or pattern to find
            
        Returns:
            Location and context of the text if found
        """
        result = await self.analyze(
            image,
            f"Look for the text '{target}' in this image. "
            f"If found, describe where it is located and its context. "
            f"If not found, say so clearly.",
        )
        return result.response if result.success else f"Error: {result.error}"
    
    async def compare_images(
        self,
        image1: "Image.Image",
        image2: "Image.Image"
    ) -> str:
        """
        Compare two images (e.g., before/after).
        
        Note: This requires sending both images and is more expensive.
        Currently sends them side by side.
        
        Args:
            image1: First image
            image2: Second image
            
        Returns:
            Comparison analysis
        """
        # Create side-by-side composite
        if not PIL_AVAILABLE:
            return "Error: PIL not available for image comparison"
        
        # Resize to same height
        h1, h2 = image1.height, image2.height
        max_h = max(h1, h2)
        
        if h1 != max_h:
            ratio = max_h / h1
            image1 = image1.resize((int(image1.width * ratio), max_h))
        if h2 != max_h:
            ratio = max_h / h2
            image2 = image2.resize((int(image2.width * ratio), max_h))
        
        # Create composite
        total_width = image1.width + image2.width + 10
        composite = Image.new("RGB", (total_width, max_h), (255, 255, 255))
        composite.paste(image1, (0, 0))
        composite.paste(image2, (image1.width + 10, 0))
        
        result = await self.analyze(
            composite,
            "This image shows two screenshots side by side. "
            "Compare the left image with the right image. "
            "What are the differences? What changed?",
            context="Side-by-side comparison of two images"
        )
        return result.response if result.success else f"Error: {result.error}"
    
    async def analyze_file(self, path: str | Path) -> AnalysisResult:
        """
        Analyze an image file.
        
        Args:
            path: Path to image file
            
        Returns:
            AnalysisResult
        """
        if not PIL_AVAILABLE:
            return AnalysisResult(
                response="",
                prompt="",
                model=self.model,
                tokens_used=0,
                success=False,
                error="PIL not available"
            )
        
        image = Image.open(path)
        return await self.analyze(image, "Describe this image in detail.")
    
    def shutdown(self) -> None:
        """Cleanup resources."""
        self._client = None
