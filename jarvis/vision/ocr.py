"""
JARVIS OCR Engine

Extracts text from images using Tesseract or EasyOCR.
Supports structured extraction with bounding boxes.
"""

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Tuple
import io

from loguru import logger

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


@dataclass
class TextBlock:
    """A block of extracted text with position information."""
    text: str
    confidence: float
    bbox: Tuple[int, int, int, int]  # (x, y, width, height)
    
    @property
    def x(self) -> int:
        return self.bbox[0]
    
    @property
    def y(self) -> int:
        return self.bbox[1]
    
    @property
    def width(self) -> int:
        return self.bbox[2]
    
    @property
    def height(self) -> int:
        return self.bbox[3]


@dataclass
class OCRResult:
    """Result of OCR extraction."""
    text: str  # Full extracted text
    blocks: List[TextBlock]  # Individual text blocks
    language: str
    engine: str
    
    @property
    def lines(self) -> List[str]:
        """Get text as list of lines."""
        return [line for line in self.text.split("\n") if line.strip()]
    
    @property
    def word_count(self) -> int:
        """Get word count."""
        return len(self.text.split())


class OCREngine:
    """
    OCR engine supporting Tesseract and EasyOCR.
    
    Features:
    - Full text extraction
    - Structured extraction with bounding boxes
    - Multiple language support
    - Confidence scores
    """
    
    def __init__(self, config):
        """
        Initialize OCR engine.
        
        Args:
            config: Configuration object
        """
        self.config = config
        self.engine_type = config.get("vision.ocr_engine", "tesseract")
        self.language = config.get("core.language", "en")[:2]  # Just language code
        
        self._tesseract_available = False
        self._easyocr_available = False
        self._easyocr_reader = None
        
        self._check_availability()
    
    def _check_availability(self) -> None:
        """Check which OCR engines are available."""
        # Check Tesseract
        try:
            import pytesseract
            # Verify tesseract is installed
            pytesseract.get_tesseract_version()
            self._tesseract_available = True
            logger.debug("Tesseract OCR available")
        except Exception as e:
            logger.debug(f"Tesseract not available: {e}")
        
        # Check EasyOCR
        try:
            import easyocr
            self._easyocr_available = True
            logger.debug("EasyOCR available")
        except ImportError:
            logger.debug("EasyOCR not available")
    
    def _get_easyocr_reader(self):
        """Get or create EasyOCR reader (lazy loading)."""
        if self._easyocr_reader is None:
            import easyocr
            # Map language codes
            lang_map = {
                "en": ["en"],
                "es": ["es", "en"],
                "fr": ["fr", "en"],
                "de": ["de", "en"],
                "zh": ["ch_sim", "en"],
                "ja": ["ja", "en"],
                "ko": ["ko", "en"],
                "ar": ["ar", "en"],
            }
            languages = lang_map.get(self.language, ["en"])
            self._easyocr_reader = easyocr.Reader(languages, gpu=False)
        return self._easyocr_reader
    
    def extract_text(self, image: "Image.Image") -> str:
        """
        Extract all text from image.
        
        Args:
            image: PIL Image to extract text from
            
        Returns:
            Extracted text as string
        """
        result = self.extract_structured(image)
        return result.text
    
    async def extract_text_async(self, image: "Image.Image") -> str:
        """Async wrapper for extract_text."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.extract_text, image)
    
    def extract_structured(self, image: "Image.Image") -> OCRResult:
        """
        Extract text with structure and bounding boxes.
        
        Args:
            image: PIL Image to extract text from
            
        Returns:
            OCRResult with text, blocks, and metadata
        """
        if self.engine_type == "tesseract" and self._tesseract_available:
            return self._extract_tesseract(image)
        elif self.engine_type == "easyocr" and self._easyocr_available:
            return self._extract_easyocr(image)
        elif self._tesseract_available:
            return self._extract_tesseract(image)
        elif self._easyocr_available:
            return self._extract_easyocr(image)
        else:
            logger.error("No OCR engine available")
            return OCRResult(
                text="",
                blocks=[],
                language=self.language,
                engine="none"
            )
    
    async def extract_structured_async(self, image: "Image.Image") -> OCRResult:
        """Async wrapper for extract_structured."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.extract_structured, image)
    
    def _extract_tesseract(self, image: "Image.Image") -> OCRResult:
        """Extract text using Tesseract."""
        import pytesseract
        
        try:
            # Get detailed data with bounding boxes
            data = pytesseract.image_to_data(
                image,
                lang=self.language,
                output_type=pytesseract.Output.DICT
            )
            
            blocks = []
            full_text_parts = []
            
            n_boxes = len(data['text'])
            for i in range(n_boxes):
                text = data['text'][i].strip()
                if text:
                    conf = float(data['conf'][i])
                    if conf > 0:  # Skip low-confidence
                        blocks.append(TextBlock(
                            text=text,
                            confidence=conf / 100.0,
                            bbox=(
                                data['left'][i],
                                data['top'][i],
                                data['width'][i],
                                data['height'][i]
                            )
                        ))
                        full_text_parts.append(text)
            
            # Also get plain text for better formatting
            plain_text = pytesseract.image_to_string(image, lang=self.language)
            
            return OCRResult(
                text=plain_text.strip(),
                blocks=blocks,
                language=self.language,
                engine="tesseract"
            )
            
        except Exception as e:
            logger.error(f"Tesseract extraction failed: {e}")
            return OCRResult(
                text="",
                blocks=[],
                language=self.language,
                engine="tesseract"
            )
    
    def _extract_easyocr(self, image: "Image.Image") -> OCRResult:
        """Extract text using EasyOCR."""
        try:
            import numpy as np
            
            reader = self._get_easyocr_reader()
            
            # Convert PIL to numpy
            img_array = np.array(image)
            
            # Run OCR
            results = reader.readtext(img_array)
            
            blocks = []
            full_text_parts = []
            
            for (bbox, text, conf) in results:
                if text.strip():
                    # Convert bbox format
                    x_coords = [p[0] for p in bbox]
                    y_coords = [p[1] for p in bbox]
                    x = int(min(x_coords))
                    y = int(min(y_coords))
                    w = int(max(x_coords) - x)
                    h = int(max(y_coords) - y)
                    
                    blocks.append(TextBlock(
                        text=text,
                        confidence=float(conf),
                        bbox=(x, y, w, h)
                    ))
                    full_text_parts.append(text)
            
            # Reconstruct text with line breaks
            # Sort blocks by y position, then x
            sorted_blocks = sorted(blocks, key=lambda b: (b.y // 20, b.x))
            
            lines = []
            current_line = []
            current_y = -1
            
            for block in sorted_blocks:
                if current_y == -1 or abs(block.y - current_y) < 20:
                    current_line.append(block.text)
                    current_y = block.y
                else:
                    if current_line:
                        lines.append(" ".join(current_line))
                    current_line = [block.text]
                    current_y = block.y
            
            if current_line:
                lines.append(" ".join(current_line))
            
            full_text = "\n".join(lines)
            
            return OCRResult(
                text=full_text,
                blocks=blocks,
                language=self.language,
                engine="easyocr"
            )
            
        except Exception as e:
            logger.error(f"EasyOCR extraction failed: {e}")
            return OCRResult(
                text="",
                blocks=[],
                language=self.language,
                engine="easyocr"
            )
    
    def extract_from_file(self, path: str | Path) -> OCRResult:
        """
        Extract text from an image file.
        
        Args:
            path: Path to image file
            
        Returns:
            OCRResult
        """
        if not PIL_AVAILABLE:
            raise RuntimeError("PIL not available")
        
        image = Image.open(path)
        return self.extract_structured(image)
    
    async def extract_from_file_async(self, path: str | Path) -> OCRResult:
        """Async wrapper for extract_from_file."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.extract_from_file, path)
    
    def extract_from_bytes(self, data: bytes) -> OCRResult:
        """
        Extract text from image bytes.
        
        Args:
            data: Image data as bytes
            
        Returns:
            OCRResult
        """
        if not PIL_AVAILABLE:
            raise RuntimeError("PIL not available")
        
        image = Image.open(io.BytesIO(data))
        return self.extract_structured(image)
    
    async def extract_from_bytes_async(self, data: bytes) -> OCRResult:
        """Async wrapper for extract_from_bytes."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.extract_from_bytes, data)
    
    def shutdown(self) -> None:
        """Cleanup resources."""
        self._easyocr_reader = None
