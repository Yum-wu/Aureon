"""Conversation manager for tracking multi-turn chat state."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional
import hashlib
import structlog

logger = structlog.get_logger()


@dataclass
class ConversationTurn:
    """Single turn in a conversation."""
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCall:
    """Tool invocation request."""
    tool_name: str
    tool_args: Dict[str, Any]
    call_id: str
    timestamp: datetime


@dataclass
class ToolResult:
    """Tool execution result."""
    call_id: str
    result: Any
    success: bool
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class Conversation:
    """Conversation state container."""
    conversation_id: str
    client_id: str
    turns: List[ConversationTurn] = field(default_factory=list)
    tool_calls: List[ToolCall] = field(default_factory=list)
    tool_results: List[ToolResult] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


class ConversationManager:
    """Manage multi-turn conversations and context.

    Tracks conversation history, manages context windows,
    and orchestrates tool calling.
    """

    def __init__(self, max_turns: int = 20, max_context_tokens: int = 4000):
        """Initialize conversation manager.

        Args:
            max_turns: Maximum number of conversation turns to retain
            max_context_tokens: Maximum token count for context window
        """
        self.conversations: Dict[str, Conversation] = {}
        self.max_turns = max_turns
        self.max_context_tokens = max_context_tokens

    def create_conversation(self, client_id: str) -> str:
        """Create a new conversation.

        Args:
            client_id: Client identifier

        Returns:
            Generated conversation ID
        """
        conversation_id = self._generate_conversation_id(client_id)

        self.conversations[conversation_id] = Conversation(
            conversation_id=conversation_id,
            client_id=client_id,
        )

        logger.info(
            "conversation_created",
            conversation_id=conversation_id,
            client_id=client_id,
        )

        return conversation_id

    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """Get conversation by ID.

        Args:
            conversation_id: Conversation identifier

        Returns:
            Conversation if found, None otherwise
        """
        return self.conversations.get(conversation_id)

    def add_user_turn(
        self,
        conversation_id: str,
        content: str,
        metadata: Dict[str, Any] = None,
    ) -> bool:
        """Add user turn to conversation.

        Args:
            conversation_id: Conversation identifier
            content: User message content
            metadata: Optional metadata for the turn

        Returns:
            True if added successfully, False if conversation not found
        """
        conversation = self.get_conversation(conversation_id)
        if not conversation:
            logger.warning("conversation_not_found", conversation_id=conversation_id)
            return False

        turn = ConversationTurn(
            role="user",
            content=content,
            timestamp=datetime.now(),
            metadata=metadata or {},
        )

        conversation.turns.append(turn)
        conversation.updated_at = datetime.now()
        self._prune_conversation(conversation)

        logger.debug(
            "user_turn_added",
            conversation_id=conversation_id,
            total_turns=len(conversation.turns),
        )

        return True

    def add_assistant_turn(
        self,
        conversation_id: str,
        content: str,
        metadata: Dict[str, Any] = None,
    ) -> bool:
        """Add assistant turn to conversation.

        Args:
            conversation_id: Conversation identifier
            content: Assistant message content
            metadata: Optional metadata for the turn

        Returns:
            True if added successfully, False if conversation not found
        """
        conversation = self.get_conversation(conversation_id)
        if not conversation:
            logger.warning("conversation_not_found", conversation_id=conversation_id)
            return False

        turn = ConversationTurn(
            role="assistant",
            content=content,
            timestamp=datetime.now(),
            metadata=metadata or {},
        )

        conversation.turns.append(turn)
        conversation.updated_at = datetime.now()
        self._prune_conversation(conversation)

        logger.debug(
            "assistant_turn_added",
            conversation_id=conversation_id,
            total_turns=len(conversation.turns),
        )

        return True

    def add_tool_call(
        self,
        conversation_id: str,
        tool_name: str,
        tool_args: Dict[str, Any],
        call_id: str,
    ) -> bool:
        """Add tool call to conversation.

        Args:
            conversation_id: Conversation identifier
            tool_name: Name of the tool being called
            tool_args: Tool arguments
            call_id: Unique identifier for this tool call

        Returns:
            True if added successfully, False if conversation not found
        """
        conversation = self.get_conversation(conversation_id)
        if not conversation:
            logger.warning("conversation_not_found", conversation_id=conversation_id)
            return False

        tool_call = ToolCall(
            tool_name=tool_name,
            tool_args=tool_args,
            call_id=call_id,
            timestamp=datetime.now(),
        )

        conversation.tool_calls.append(tool_call)
        conversation.updated_at = datetime.now()

        logger.debug(
            "tool_call_added",
            conversation_id=conversation_id,
            tool_name=tool_name,
            call_id=call_id,
        )

        return True

    def add_tool_result(
        self,
        conversation_id: str,
        call_id: str,
        result: Any,
        success: bool,
        error: Optional[str] = None,
    ) -> bool:
        """Add tool result to conversation.

        Args:
            conversation_id: Conversation identifier
            call_id: Tool call identifier to match result
            result: Tool execution result
            success: Whether tool execution succeeded
            error: Optional error message if failed

        Returns:
            True if added successfully, False if conversation not found
        """
        conversation = self.get_conversation(conversation_id)
        if not conversation:
            logger.warning("conversation_not_found", conversation_id=conversation_id)
            return False

        tool_result = ToolResult(
            call_id=call_id,
            result=result,
            success=success,
            error=error,
            timestamp=datetime.now(),
        )

        conversation.tool_results.append(tool_result)
        conversation.updated_at = datetime.now()

        logger.debug(
            "tool_result_added",
            conversation_id=conversation_id,
            call_id=call_id,
            success=success,
        )

        return True

    def get_context_messages(
        self,
        conversation_id: str,
        system_prompt: str = None,
    ) -> List[Dict[str, str]]:
        """Get conversation context as message list for LLM.

        Prunes older turns to stay within context window.

        Args:
            conversation_id: Conversation identifier
            system_prompt: Optional system prompt

        Returns:
            List of message dicts (role, content)
        """
        conversation = self.get_conversation(conversation_id)
        if not conversation:
            return []

        messages = []

        # Add system prompt if provided
        if system_prompt:
            messages.append({
                "role": "system",
                "content": system_prompt,
            })

        # Add conversation turns (most recent first, then reverse)
        turns_to_include = conversation.turns[-self.max_turns:]
        for turn in turns_to_include:
            messages.append({
                "role": turn.role,
                "content": turn.content,
            })

        return messages

    def _prune_conversation(self, conversation: Conversation):
        """Prune conversation to stay within limits.

        LRU-style pruning that removes oldest turns when exceeding limits.

        Args:
            conversation: Conversation to prune
        """
        # Prune turns if exceeding max_turns
        if len(conversation.turns) > self.max_turns:
            excess = len(conversation.turns) - self.max_turns
            conversation.turns = conversation.turns[excess:]
            logger.debug(
                "conversation_pruned",
                conversation_id=conversation.conversation_id,
                removed_turns=excess,
            )

        # Prune tool calls and results to match remaining turns
        # Keep only tool calls and results that correspond to remaining turns
        if conversation.tool_calls:
            # Get timestamps from remaining turns
            turn_timestamps = [turn.timestamp for turn in conversation.turns]

            # Filter tool calls to only those within the turn window
            if turn_timestamps:
                earliest_turn = min(turn_timestamps)
                conversation.tool_calls = [
                    tc for tc in conversation.tool_calls
                    if tc.timestamp >= earliest_turn
                ]
                conversation.tool_results = [
                    tr for tr in conversation.tool_results
                    if tr.timestamp >= earliest_turn
                ]

    def _generate_conversation_id(self, client_id: str) -> str:
        """Generate unique conversation ID.

        Args:
            client_id: Client identifier to include in hash

        Returns:
            12-character hexadecimal conversation ID
        """
        timestamp = datetime.now().isoformat()
        hash_input = f"{client_id}:{timestamp}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:12]

    def delete_conversation(self, conversation_id: str) -> bool:
        """Delete conversation.

        Args:
            conversation_id: Conversation identifier

        Returns:
            True if deleted successfully, False if conversation not found
        """
        if conversation_id not in self.conversations:
            logger.warning("conversation_not_found", conversation_id=conversation_id)
            return False

        del self.conversations[conversation_id]
        logger.info("conversation_deleted", conversation_id=conversation_id)
        return True

    def get_conversation_stats(self) -> Dict[str, Any]:
        """Get conversation statistics.

        Returns:
            Dictionary with conversation metrics
        """
        total_conversations = len(self.conversations)
        total_turns = sum(len(conv.turns) for conv in self.conversations.values())
        total_tool_calls = sum(
            len(conv.tool_calls) for conv in self.conversations.values()
        )
        total_tool_results = sum(
            len(conv.tool_results) for conv in self.conversations.values()
        )

        avg_turns_per_conv = (
            round(total_turns / total_conversations, 2)
            if total_conversations > 0
            else 0
        )

        stats = {
            "total_conversations": total_conversations,
            "total_turns": total_turns,
            "total_tool_calls": total_tool_calls,
            "total_tool_results": total_tool_results,
            "avg_turns_per_conversation": avg_turns_per_conv,
            "max_turns_per_conversation": self.max_turns,
            "max_context_tokens": self.max_context_tokens,
        }

        logger.debug("conversation_stats", **stats)
        return stats
