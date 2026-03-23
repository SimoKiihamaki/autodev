"""
LLM Response Parser

Handles parsing and validation of LLM API responses.
Provides robust parsing for different response formats and content types.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

from .base_client import ToolUse, LLMResponse
from .exceptions import LLMResponseError, LLMToolUseError

logger = logging.getLogger(__name__)


@dataclass
class ParsedContent:
    """
    Parsed content from LLM response.
    
    Attributes:
        text: Plain text content
        code_blocks: List of extracted code blocks
        tool_calls: List of parsed tool calls
        structured_data: Any structured data found (JSON, etc.)
        thinking: Thinking/reasoning content (if exposed by model)
    """
    text: str = ""
    code_blocks: List[Dict[str, str]] = field(default_factory=list)
    tool_calls: List[ToolUse] = field(default_factory=list)
    structured_data: Optional[Dict[str, Any]] = None
    thinking: Optional[str] = None
    
    def has_code(self) -> bool:
        """Check if content contains code blocks."""
        return len(self.code_blocks) > 0
    
    def has_tool_calls(self) -> bool:
        """Check if content contains tool calls."""
        return len(self.tool_calls) > 0
    
    def get_code(self, language: Optional[str] = None) -> Optional[str]:
        """
        Get code from response.
        
        Args:
            language: Optional language filter
            
        Returns:
            Code string or None
        """
        if not self.code_blocks:
            return None
        
        if language:
            for block in self.code_blocks:
                if block.get('language', '').lower() == language.lower():
                    return block.get('code', '')
            return None
        
        # Return first code block
        return self.code_blocks[0].get('code', '')


class ResponseParser:
    """
    Parser for LLM API responses.
    
    Features:
    - Extract text content from various response formats
    - Parse tool use blocks
    - Extract code blocks from markdown
    - Parse structured JSON data
    - Handle multi-part content
    - Validate response structure
    """
    
    # Regex patterns for content extraction
    CODE_BLOCK_PATTERN = re.compile(
        r'```(\w*)\n(.*?)```',
        re.DOTALL
    )
    
    JSON_PATTERN = re.compile(
        r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}',
        re.DOTALL
    )
    
    THINKING_PATTERN = re.compile(
        r'<thinking>(.*?)</thinking>',
        re.DOTALL | re.IGNORECASE
    )
    
    def parse_anthropic_response(self, response: Any) -> LLMResponse:
        """
        Parse an Anthropic API response.
        
        Args:
            response: Raw Anthropic API response object
            
        Returns:
            LLMResponse with parsed content
            
        Raises:
            LLMResponseError: If response cannot be parsed
        """
        try:
            content_text = ""
            tool_uses = []
            
            # Handle response content blocks
            if hasattr(response, 'content'):
                for block in response.content:
                    parsed = self._parse_content_block(block)
                    if parsed:
                        if isinstance(parsed, str):
                            content_text += parsed
                        elif isinstance(parsed, ToolUse):
                            tool_uses.append(parsed)
            
            # Extract usage information
            usage = self._extract_usage(response)
            
            # Get stop reason
            stop_reason = getattr(response, 'stop_reason', 'end_turn')
            
            # Get model
            model = getattr(response, 'model', '')
            
            return LLMResponse(
                content=content_text.strip(),
                tool_uses=tool_uses,
                stop_reason=stop_reason,
                usage=usage,
                model=model,
            )
            
        except Exception as e:
            raise LLMResponseError(
                f"Failed to parse Anthropic response: {e}",
                response_data=self._safe_serialize(response)
            )
    
    def _parse_content_block(self, block: Any) -> Optional[Union[str, ToolUse]]:
        """
        Parse a single content block.
        
        Args:
            block: Content block from response
            
        Returns:
            Parsed content (string or ToolUse)
        """
        if not hasattr(block, 'type'):
            return str(block) if block else None
        
        block_type = block.type
        
        if block_type == 'text':
            return getattr(block, 'text', '')
        
        elif block_type == 'tool_use':
            tool_id = getattr(block, 'id', '')
            tool_name = getattr(block, 'name', '')
            tool_input = getattr(block, 'input', {})
            
            if not tool_id:
                logger.warning("Tool use block missing ID")
                tool_id = f"tool_{hash(str(tool_input))}"
            
            return ToolUse(
                id=tool_id,
                name=tool_name,
                input=dict(tool_input) if tool_input else {}
            )
        
        elif block_type == 'thinking':
            # Extended thinking content
            return None  # Skip thinking blocks in main content
        
        elif block_type == 'image':
            # Image content - return placeholder
            return "[Image content]"
        
        else:
            logger.debug(f"Unknown content block type: {block_type}")
            return None
    
    def _extract_usage(self, response: Any) -> Dict[str, int]:
        """
        Extract usage information from response.
        
        Args:
            response: API response object
            
        Returns:
            Usage dictionary
        """
        usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }
        
        if hasattr(response, 'usage'):
            usage_obj = response.usage
            usage["input_tokens"] = getattr(usage_obj, 'input_tokens', 0)
            usage["output_tokens"] = getattr(usage_obj, 'output_tokens', 0)
            usage["total_tokens"] = usage["input_tokens"] + usage["output_tokens"]
            
            # Add cache stats if available
            if hasattr(usage_obj, 'cache_read_input_tokens'):
                usage["cache_read_tokens"] = usage_obj.cache_read_input_tokens
            if hasattr(usage_obj, 'cache_creation_input_tokens'):
                usage["cache_creation_tokens"] = usage_obj.cache_creation_input_tokens
        
        return usage
    
    def parse_content(self, text: str) -> ParsedContent:
        """
        Parse text content to extract structured elements.
        
        Args:
            text: Raw text content
            
        Returns:
            ParsedContent with extracted elements
        """
        result = ParsedContent()
        
        # Extract thinking content
        thinking_match = self.THINKING_PATTERN.search(text)
        if thinking_match:
            result.thinking = thinking_match.group(1).strip()
            text = self.THINKING_PATTERN.sub('', text)
        
        # Extract code blocks
        code_matches = self.CODE_BLOCK_PATTERN.findall(text)
        for lang, code in code_matches:
            result.code_blocks.append({
                'language': lang.lower() if lang else 'text',
                'code': code.strip(),
            })
        
        # Try to extract JSON data
        result.structured_data = self._extract_json(text)
        
        # Store cleaned text
        result.text = text.strip()
        
        return result
    
    def _extract_json(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Extract JSON data from text.
        
        Args:
            text: Text potentially containing JSON
            
        Returns:
            Parsed JSON dictionary or None
        """
        # Try to find JSON objects
        matches = self.JSON_PATTERN.findall(text)
        
        for match in matches:
            try:
                data = json.loads(match)
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                continue
        
        # Try parsing the entire text as JSON
        try:
            data = json.loads(text.strip())
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
        
        return None
    
    def extract_tool_result(self, response: LLMResponse) -> Dict[str, Any]:
        """
        Extract tool call results from response.
        
        Args:
            response: LLM response
            
        Returns:
            Dictionary mapping tool IDs to results
        """
        results = {}
        
        for tool_use in response.tool_uses:
            results[tool_use.id] = {
                'name': tool_use.name,
                'input': tool_use.input,
            }
        
        return results
    
    def validate_response(self, response: LLMResponse) -> Tuple[bool, List[str]]:
        """
        Validate an LLM response.
        
        Args:
            response: Response to validate
            
        Returns:
            Tuple of (is_valid, list of issues)
        """
        issues = []
        
        # Check for empty content
        if not response.content and not response.tool_uses:
            issues.append("Response has no content and no tool uses")
        
        # Check for truncated response
        if response.stop_reason == 'max_tokens':
            issues.append("Response was truncated due to max_tokens limit")
        
        # Validate tool uses
        for tool_use in response.tool_uses:
            if not tool_use.id:
                issues.append(f"Tool use '{tool_use.name}' missing ID")
            if not tool_use.name:
                issues.append(f"Tool use {tool_use.id} missing name")
        
        return len(issues) == 0, issues
    
    def _safe_serialize(self, obj: Any) -> Dict[str, Any]:
        """
        Safely serialize an object for error reporting.
        
        Args:
            obj: Object to serialize
            
        Returns:
            Dictionary representation
        """
        try:
            if hasattr(obj, '__dict__'):
                return {
                    k: str(v)[:100]  # Truncate long values
                    for k, v in obj.__dict__.items()
                    if not k.startswith('_')
                }
            return {'type': type(obj).__name__, 'value': str(obj)[:100]}
        except Exception:
            return {'type': type(obj).__name__, 'error': 'serialization failed'}


class StreamingResponseParser:
    """
    Parser for streaming LLM responses.
    
    Handles incremental parsing of streaming content.
    """
    
    def __init__(self):
        self.buffer = ""
        self.tool_uses: List[ToolUse] = []
        self.current_tool: Optional[Dict[str, Any]] = None
        self.current_tool_input = ""
    
    def process_event(self, event: Any) -> Optional[str]:
        """
        Process a streaming event.
        
        Args:
            event: Streaming event from API
            
        Returns:
            Text content to yield (if any)
        """
        if not hasattr(event, 'type'):
            return None
        
        event_type = event.type
        
        if event_type == 'content_block_delta':
            delta = getattr(event, 'delta', {})
            if hasattr(delta, 'text'):
                text = delta.text
                self.buffer += text
                return text
        
        elif event_type == 'content_block_start':
            block = getattr(event, 'content_block', None)
            if block and hasattr(block, 'type'):
                if block.type == 'tool_use':
                    self.current_tool = {
                        'id': getattr(block, 'id', ''),
                        'name': getattr(block, 'name', ''),
                    }
                    self.current_tool_input = ""
        
        elif event_type == 'content_block_stop':
            if self.current_tool:
                # Finalize tool use
                try:
                    input_data = json.loads(self.current_tool_input) if self.current_tool_input else {}
                except json.JSONDecodeError:
                    input_data = {'raw': self.current_tool_input}
                
                self.tool_uses.append(ToolUse(
                    id=self.current_tool.get('id', ''),
                    name=self.current_tool.get('name', ''),
                    input=input_data,
                ))
                self.current_tool = None
                self.current_tool_input = ""
        
        return None
    
    def get_final_response(self, stop_reason: str = 'end_turn', model: str = '') -> LLMResponse:
        """
        Get the final response after streaming completes.
        
        Args:
            stop_reason: Reason for stopping
            model: Model name
            
        Returns:
            Complete LLMResponse
        """
        return LLMResponse(
            content=self.buffer,
            tool_uses=self.tool_uses,
            stop_reason=stop_reason,
            model=model,
        )
    
    def reset(self) -> None:
        """Reset parser state for new stream."""
        self.buffer = ""
        self.tool_uses = []
        self.current_tool = None
        self.current_tool_input = ""


__all__ = [
    "ParsedContent",
    "ResponseParser",
    "StreamingResponseParser",
]
