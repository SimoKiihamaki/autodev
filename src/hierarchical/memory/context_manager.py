"""
Context Manager for Hierarchical Agents

Provides intelligent context window management for handling large
codebases and complex tasks within LLM context limits.

This module implements:
- Context window management: Efficient token budget allocation
- File summarization: Compact representation of large files
- Context prioritization: Important code gets more space
- Incremental loading: Load files as needed

Architecture:
    ┌─────────────────────────────────────────────────────────────┐
    │                    Context Manager                          │
    ├─────────────────────────────────────────────────────────────┤
    │  Input Files → Prioritization → Summarization →             │
    │               → Token Budgeting → Context Assembly          │
    │                                                              │
    │  Task Context + Relevant Files + Dependencies → LLM Prompt  │
    └─────────────────────────────────────────────────────────────┘

Usage:
    from hierarchical.memory.context_manager import ContextManager, ContextConfig
    
    config = ContextConfig(max_tokens=8000)
    context = ContextManager(config)
    
    # Add files to context
    context.add_file("src/main.py", priority=Priority.HIGH)
    context.add_file("src/utils.py", priority=Priority.MEDIUM)
    
    # Build context for LLM
    prompt = context.build_context(task_description)
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import logging
import os
import re

logger = logging.getLogger(__name__)


class Priority(Enum):
    """Priority levels for context items."""
    CRITICAL = 1  # Must include, truncate if needed
    HIGH = 2      # Important, include first
    MEDIUM = 3    # Normal priority
    LOW = 4       # Include if space remains
    MINIMAL = 5   # Just references


class ContextType(Enum):
    """Types of context content."""
    TASK = "task"
    FILE = "file"
    SUMMARY = "summary"
    REFERENCE = "reference"
    DEPENDENCY = "dependency"
    ERROR = "error"


@dataclass
class ContextConfig:
    """
    Configuration for Context Manager.
    
    Attributes:
        max_tokens: Maximum tokens in context window
        task_tokens: Tokens reserved for task description
        file_tokens: Default tokens per file
        summary_ratio: Ratio of summary to original size
        include_imports: Include import statements
        include_signatures: Include function/class signatures
        include_docstrings: Include docstrings
        include_comments: Include comments
        max_file_size: Maximum file size to include fully
    """
    max_tokens: int = 8000
    task_tokens: int = 500
    file_tokens: int = 1500
    summary_ratio: float = 0.3
    include_imports: bool = True
    include_signatures: bool = True
    include_docstrings: bool = True
    include_comments: bool = False
    max_file_size: int = 10000  # characters


@dataclass
class FileSummary:
    """
    Summary of a file for context inclusion.
    
    Attributes:
        file_path: Path to the file
        original_size: Original file size in characters
        summary_size: Summary size in characters
        estimated_tokens: Estimated token count
        priority: Context priority
        content: Full or summarized content
        signatures: Function/class signatures
        imports: Import statements
        key_elements: Key code elements identified
        last_modified: File modification time
    """
    file_path: str = ""
    original_size: int = 0
    summary_size: int = 0
    estimated_tokens: int = 0
    priority: Priority = Priority.MEDIUM
    content: str = ""
    signatures: List[str] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    key_elements: List[str] = field(default_factory=list)
    last_modified: Optional[datetime] = None

    @property
    def compression_ratio(self) -> float:
        """Calculate compression ratio."""
        if self.original_size > 0:
            return self.summary_size / self.original_size
        return 1.0


@dataclass
class ContextWindow:
    """
    Represents the assembled context window.
    
    Attributes:
        total_tokens: Total tokens used
        available_tokens: Tokens remaining
        task_context: Task description context
        file_contexts: File context items
        assembled_prompt: Final assembled prompt
        warnings: Warnings about truncation
    """
    total_tokens: int = 0
    available_tokens: int = 0
    task_context: str = ""
    file_contexts: List[Tuple[str, str]] = field(default_factory=list)  # (path, content)
    assembled_prompt: str = ""
    warnings: List[str] = field(default_factory=list)

    @property
    def utilization(self) -> float:
        """Calculate context window utilization."""
        if self.total_tokens > 0:
            return 1.0 - (self.available_tokens / self.total_tokens)
        return 0.0


class ContextManager:
    """
    Intelligent context window manager for hierarchical agents.
    
    This class provides:
    - Token budget management
    - File summarization
    - Context prioritization
    - Incremental context building
    
    Example:
        >>> config = ContextConfig(max_tokens=8000)
        >>> manager = ContextManager(config)
        >>> manager.add_file("main.py", Priority.HIGH)
        >>> prompt = manager.build_context("Fix the bug in user.py")
    """
    
    def __init__(self, config: Optional[ContextConfig] = None):
        """
        Initialize Context Manager.
        
        Args:
            config: Context configuration
        """
        self.config = config or ContextConfig()
        self._files: Dict[str, FileSummary] = {}
        self._task_context: str = ""
        self._additional_context: List[Tuple[ContextType, str, Priority]] = []
        
        logger.info(
            f"ContextManager initialized with {self.config.max_tokens} tokens"
        )

    def set_task_context(self, task_description: str) -> None:
        """
        Set the task description context.
        
        Args:
            task_description: Task description text
        """
        self._task_context = task_description

    def add_file(
        self,
        file_path: str,
        priority: Priority = Priority.MEDIUM,
        content: Optional[str] = None,
    ) -> FileSummary:
        """
        Add a file to the context.
        
        Args:
            file_path: Path to the file
            priority: Context priority
            content: Optional pre-loaded content
            
        Returns:
            FileSummary for the added file
        """
        if content is None:
            content = self._load_file(file_path)
        
        summary = self._create_file_summary(file_path, content, priority)
        self._files[file_path] = summary
        
        logger.debug(f"Added file {file_path} with priority {priority.name}")
        return summary

    def add_context(
        self,
        context_type: ContextType,
        content: str,
        priority: Priority = Priority.MEDIUM,
    ) -> None:
        """
        Add additional context item.
        
        Args:
            context_type: Type of context
            content: Context content
            priority: Context priority
        """
        self._additional_context.append((context_type, content, priority))

    def add_dependency_context(
        self,
        file_path: str,
        related_files: List[str],
    ) -> None:
        """
        Add context about file dependencies.
        
        Args:
            file_path: Main file path
            related_files: List of related/dependency files
        """
        for related in related_files:
            if related not in self._files:
                self.add_file(related, Priority.LOW)

    def build_context(
        self,
        task_description: Optional[str] = None,
    ) -> ContextWindow:
        """
        Build the final context window for LLM.
        
        This method:
        1. Sets task context if provided
        2. Prioritizes all context items
        3. Allocates token budget
        4. Assembles final prompt
        
        Args:
            task_description: Optional task description override
            
        Returns:
            ContextWindow with assembled context
        """
        if task_description:
            self.set_task_context(task_description)
        
        window = ContextWindow(
            total_tokens=self.config.max_tokens,
            available_tokens=self.config.max_tokens,
        )
        
        # Reserve tokens for task
        window.available_tokens -= self.config.task_tokens
        
        # Sort files by priority
        sorted_files = sorted(
            self._files.values(),
            key=lambda f: f.priority.value
        )
        
        # Add files within token budget
        for file_summary in sorted_files:
            if window.available_tokens <= 0:
                window.warnings.append(f"Context full, skipping {file_summary.file_path}")
                break
            
            tokens_needed = file_summary.estimated_tokens
            if tokens_needed <= window.available_tokens:
                window.file_contexts.append(
                    (file_summary.file_path, file_summary.content)
                )
                window.available_tokens -= tokens_needed
            else:
                # Truncate to fit
                truncated = self._truncate_content(
                    file_summary.content,
                    window.available_tokens
                )
                window.file_contexts.append(
                    (file_summary.file_path, truncated)
                )
                window.available_tokens = 0
                window.warnings.append(
                    f"Truncated {file_summary.file_path} to fit context"
                )
        
        # Assemble final prompt
        window.assembled_prompt = self._assemble_prompt(window)
        window.task_context = self._task_context
        
        return window

    def _load_file(self, file_path: str) -> str:
        """Load file content from disk."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logger.error(f"Failed to load file {file_path}: {e}")
            return f"# Error loading file: {e}"

    def _create_file_summary(
        self,
        file_path: str,
        content: str,
        priority: Priority,
    ) -> FileSummary:
        """
        Create a summary of a file for context.
        
        Args:
            file_path: Path to the file
            content: File content
            priority: Context priority
            
        Returns:
            FileSummary object
        """
        original_size = len(content)
        
        # Extract code elements
        imports = self._extract_imports(content)
        signatures = self._extract_signatures(content)
        
        # Decide whether to summarize
        if original_size <= self.config.max_file_size:
            # Include full content
            summary_content = content
            summary_size = original_size
        else:
            # Create summary
            summary_content = self._summarize_file(content, imports, signatures)
            summary_size = len(summary_content)
        
        # Estimate tokens (rough: ~4 chars per token)
        estimated_tokens = summary_size // 4
        
        # Get file modification time
        last_modified = None
        if os.path.exists(file_path):
            mtime = os.path.getmtime(file_path)
            last_modified = datetime.fromtimestamp(mtime)
        
        return FileSummary(
            file_path=file_path,
            original_size=original_size,
            summary_size=summary_size,
            estimated_tokens=estimated_tokens,
            priority=priority,
            content=summary_content,
            signatures=signatures,
            imports=imports,
            key_elements=self._extract_key_elements(content),
            last_modified=last_modified,
        )

    def _extract_imports(self, content: str) -> List[str]:
        """Extract import statements from code."""
        imports = []
        import_pattern = r'^(?:from|import)\s+.+$'
        
        for line in content.split('\n'):
            if re.match(import_pattern, line.strip()):
                imports.append(line.strip())
        
        return imports[:20]  # Limit imports

    def _extract_signatures(self, content: str) -> List[str]:
        """Extract function and class signatures from code."""
        signatures = []
        
        # Python signatures
        patterns = [
            r'^(async\s+)?def\s+\w+\([^)]*\)(\s*->\s*[^:]+)?:',  # Functions
            r'^class\s+\w+.*:',  # Classes
        ]
        
        for line in content.split('\n'):
            stripped = line.strip()
            for pattern in patterns:
                if re.match(pattern, stripped):
                    signatures.append(stripped)
                    break
        
        return signatures[:30]  # Limit signatures

    def _extract_key_elements(self, content: str) -> List[str]:
        """Extract key code elements (function names, class names, etc.)."""
        elements = []
        
        # Extract identifiers that look important
        patterns = [
            r'def\s+(\w+)',  # Function definitions
            r'class\s+(\w+)',  # Class definitions
            r'(\w+)\s*=\s*lambda',  # Lambda assignments
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, content)
            elements.extend(matches)
        
        return list(set(elements))[:20]  # Unique elements, limited

    def _summarize_file(
        self,
        content: str,
        imports: List[str],
        signatures: List[str],
    ) -> str:
        """
        Create a summary of a large file.
        
        Args:
            content: Full file content
            imports: Extracted imports
            signatures: Extracted signatures
            
        Returns:
            Summarized content
        """
        parts = []
        
        # Add imports
        if self.config.include_imports and imports:
            parts.append("# Imports:")
            parts.extend(imports[:10])
            parts.append("")
        
        # Add signatures with docstrings
        if self.config.include_signatures and signatures:
            parts.append("# Signatures:")
            parts.extend(signatures)
            parts.append("")
        
        # Add a snippet of the beginning
        lines = content.split('\n')
        snippet_lines = lines[:50]
        parts.append("# File snippet:")
        parts.extend(snippet_lines)
        
        if len(lines) > 50:
            parts.append(f"\n# ... ({len(lines) - 50} more lines)")
        
        return '\n'.join(parts)

    def _truncate_content(
        self,
        content: str,
        max_tokens: int,
    ) -> str:
        """
        Truncate content to fit within token budget.
        
        Args:
            content: Content to truncate
            max_tokens: Maximum tokens allowed
            
        Returns:
            Truncated content
        """
        max_chars = max_tokens * 4  # Approximate
        
        if len(content) <= max_chars:
            return content
        
        # Truncate with indicator
        return content[:max_chars - 50] + "\n\n# ... [TRUNCATED]"

    def _assemble_prompt(self, window: ContextWindow) -> str:
        """
        Assemble the final prompt from context window.
        
        Args:
            window: Context window with all items
            
        Returns:
            Assembled prompt string
        """
        parts = []
        
        # Task section
        parts.append("## Task")
        parts.append(self._task_context or "No task description provided.")
        parts.append("")
        
        # Files section
        if window.file_contexts:
            parts.append("## Relevant Files")
            for file_path, content in window.file_contexts:
                parts.append(f"### {file_path}")
                parts.append("```")
                parts.append(content)
                parts.append("```")
                parts.append("")
        
        # Warnings
        if window.warnings:
            parts.append("## Context Notes")
            for warning in window.warnings:
                parts.append(f"- {warning}")
            parts.append("")
        
        return '\n'.join(parts)

    def clear(self) -> None:
        """Clear all context."""
        self._files.clear()
        self._task_context = ""
        self._additional_context.clear()
        logger.debug("Context cleared")

    def get_stats(self) -> Dict[str, Any]:
        """
        Get context statistics.
        
        Returns:
            Dictionary of context statistics
        """
        total_original_size = sum(f.original_size for f in self._files.values())
        total_summary_size = sum(f.summary_size for f in self._files.values())
        
        return {
            "files_count": len(self._files),
            "total_original_size": total_original_size,
            "total_summary_size": total_summary_size,
            "compression_ratio": (
                total_summary_size / total_original_size
                if total_original_size > 0 else 1.0
            ),
            "estimated_total_tokens": sum(
                f.estimated_tokens for f in self._files.values()
            ),
            "max_tokens": self.config.max_tokens,
        }
