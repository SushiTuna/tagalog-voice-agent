from pipecat.frames.frames import TranscriptionFrame, TextFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from bot_config import PRODUCTS


class TranscriptCollector(FrameProcessor):
    """A processor that sits in the pipeline to capture user and assistant utterances."""

    def __init__(self):
        super().__init__()
        self.transcript: list[dict[str, str]] = []
        self.products_discussed: set[str] = set()

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)

        if isinstance(frame, TranscriptionFrame) and direction == FrameDirection.DOWNSTREAM:
            text = frame.text.strip()
            if text:
                self.transcript.append({"role": "user", "text": text})
                self._detect_products(text)

        if isinstance(frame, TextFrame) and direction == FrameDirection.DOWNSTREAM:
            text = frame.text.strip()
            if text and len(text) > 5:
                self.transcript.append({"role": "assistant", "text": text})
                self._detect_products(text)

        await self.push_frame(frame, direction)

    def _detect_products(self, text: str) -> None:
        lower = text.lower()
        for product in PRODUCTS:
            if any(kw in lower for kw in product["keywords"]):
                self.products_discussed.add(product["name"])
