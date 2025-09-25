import time
import heapq
import asyncio
import logging
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict, deque
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TimedMessage:
    """Message with timing information for ordering"""
    msg_id: str
    sender: str
    recipient: str
    payload: str
    original_timestamp: float  # Original timestamp from sender
    corrected_timestamp: float  # Timestamp after synchronization correction
    receive_timestamp: float   # When we received the message
    sequence_number: Optional[int] = None
    vector_clock: Optional[Dict[str, int]] = None


class MessageOrderingBuffer:
    """
    Buffer for reordering messages that arrive out of sequence due to network delays.
    Uses corrected timestamps and implements various ordering strategies.
    """
    
    def __init__(self, buffer_timeout: float = 5.0, max_buffer_size: int = 1000):
        self.buffer_timeout = buffer_timeout  # Max time to hold messages for reordering
        self.max_buffer_size = max_buffer_size
        
        # Message buffer (min-heap based on corrected timestamp)
        self.message_buffer: List[Tuple[float, TimedMessage]] = []
        
        # Per-sender ordering buffers for maintaining causal ordering
        self.sender_buffers: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        self.sender_sequences: Dict[str, int] = defaultdict(int)
        
        # Vector clocks for tracking causal relationships
        self.vector_clocks: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        
        # Delivered messages tracking (to avoid duplicates)
        self.delivered_messages: Dict[str, float] = {}  # msg_id -> delivery_time
        self.delivered_cleanup_interval = 3600.0  # Clean up after 1 hour
        
        # Statistics
        self.messages_buffered = 0
        self.messages_reordered = 0
        self.messages_delivered = 0
        self.messages_dropped = 0
        
    def add_message(self, message: TimedMessage) -> bool:
        """
        Add a message to the ordering buffer.
        Returns True if message was added, False if it was a duplicate or invalid.
        """
        # Check for duplicates
        if message.msg_id in self.delivered_messages:
            logger.debug(f"Duplicate message ignored: {message.msg_id}")
            return False
        
        # Check buffer size limit
        if len(self.message_buffer) >= self.max_buffer_size:
            logger.warning(f"Message buffer full, dropping oldest messages")
            self._cleanup_old_messages(force=True)
        
        # Add to main buffer with corrected timestamp as priority
        heapq.heappush(self.message_buffer, (message.corrected_timestamp, message))
        self.messages_buffered += 1
        
        # Update vector clock if provided
        if message.vector_clock:
            self._update_vector_clock(message.sender, message.vector_clock)
        
        logger.debug(f"Message buffered: {message.msg_id}, "
                    f"corrected_ts={message.corrected_timestamp:.6f}, "
                    f"buffer_size={len(self.message_buffer)}")
        
        return True
    
    def get_deliverable_messages(self, current_time: Optional[float] = None) -> List[TimedMessage]:
        """
        Get messages that are ready for delivery based on timeout or ordering constraints.
        """
        if current_time is None:
            current_time = time.time()
        
        deliverable = []
        remaining_buffer = []
        
        # Process messages in timestamp order
        while self.message_buffer:
            timestamp, message = heapq.heappop(self.message_buffer)
            
            # Check if message has been buffered long enough
            time_in_buffer = current_time - message.receive_timestamp
            
            if time_in_buffer >= self.buffer_timeout:
                # Timeout reached, deliver regardless of ordering
                deliverable.append(message)
                self.messages_delivered += 1
                self.delivered_messages[message.msg_id] = current_time
                
                if time_in_buffer > self.buffer_timeout * 2:
                    logger.warning(f"Message {message.msg_id} delivered after long delay: "
                                 f"{time_in_buffer:.2f}s")
                
            elif self._can_deliver_now(message, current_time):
                # Message can be delivered based on ordering constraints
                deliverable.append(message)
                self.messages_delivered += 1
                self.delivered_messages[message.msg_id] = current_time
                
            else:
                # Keep in buffer for more reordering
                remaining_buffer.append((timestamp, message))
        
        # Rebuild the heap with remaining messages
        self.message_buffer = remaining_buffer
        heapq.heapify(self.message_buffer)
        
        # Sort deliverable messages by corrected timestamp for final ordering
        deliverable.sort(key=lambda m: m.corrected_timestamp)
        
        # Count reordered messages
        for i, msg in enumerate(deliverable):
            if i > 0 and msg.corrected_timestamp < deliverable[i-1].corrected_timestamp:
                self.messages_reordered += 1
        
        # Cleanup old delivered messages periodically
        self._cleanup_delivered_messages(current_time)
        
        return deliverable
    
    def _can_deliver_now(self, message: TimedMessage, current_time: float) -> bool:
        """
        Determine if a message can be delivered now based on ordering constraints.
        """
        # For now, use simple timestamp-based ordering with a small window
        # More sophisticated causal ordering can be implemented here
        
        # Check if there are any messages with earlier timestamps still expected
        expected_earlier_messages = any(
            ts < message.corrected_timestamp 
            for ts, _ in self.message_buffer
        )
        
        # If no earlier messages expected, or we've waited reasonable time, deliver
        time_in_buffer = current_time - message.receive_timestamp
        return not expected_earlier_messages or time_in_buffer >= self.buffer_timeout * 0.5
    
    def _update_vector_clock(self, sender: str, message_vector_clock: Dict[str, int]):
        """Update vector clocks for causal ordering"""
        for node, clock_value in message_vector_clock.items():
            self.vector_clocks[sender][node] = max(
                self.vector_clocks[sender][node], 
                clock_value
            )
    
    def _cleanup_old_messages(self, force: bool = False):
        """Remove old messages from buffer to prevent memory issues"""
        current_time = time.time()
        cutoff_time = current_time - (self.buffer_timeout * 3)
        
        if force or len(self.message_buffer) > self.max_buffer_size * 0.8:
            # Remove oldest 10% of messages or messages older than cutoff
            to_remove = max(1, len(self.message_buffer) // 10)
            
            # Sort by receive time and remove oldest
            self.message_buffer.sort(key=lambda x: x[1].receive_timestamp)
            
            for _ in range(min(to_remove, len(self.message_buffer))):
                if self.message_buffer:
                    _, old_msg = self.message_buffer.pop(0)
                    self.messages_dropped += 1
                    logger.warning(f"Dropped old message: {old_msg.msg_id}")
            
            # Rebuild heap
            heapq.heapify(self.message_buffer)
    
    def _cleanup_delivered_messages(self, current_time: float):
        """Clean up old delivered message records"""
        cutoff_time = current_time - self.delivered_cleanup_interval
        
        to_remove = [
            msg_id for msg_id, delivery_time in self.delivered_messages.items()
            if delivery_time < cutoff_time
        ]
        
        for msg_id in to_remove:
            del self.delivered_messages[msg_id]
    
    def get_buffer_status(self) -> Dict[str, Any]:
        """Get current buffer status for monitoring"""
        current_time = time.time()
        
        # Calculate average age of buffered messages
        if self.message_buffer:
            ages = [current_time - msg.receive_timestamp for _, msg in self.message_buffer]
            avg_age = sum(ages) / len(ages)
            max_age = max(ages)
        else:
            avg_age = max_age = 0.0
        
        return {
            "buffer_size": len(self.message_buffer),
            "max_buffer_size": self.max_buffer_size,
            "buffer_utilization": len(self.message_buffer) / self.max_buffer_size,
            "average_message_age": avg_age,
            "max_message_age": max_age,
            "messages_buffered": self.messages_buffered,
            "messages_reordered": self.messages_reordered,
            "messages_delivered": self.messages_delivered,
            "messages_dropped": self.messages_dropped,
            "reorder_rate": self.messages_reordered / max(1, self.messages_delivered),
            "delivered_tracking_size": len(self.delivered_messages)
        }
    
    def force_deliver_all(self) -> List[TimedMessage]:
        """Force delivery of all buffered messages (for shutdown)"""
        messages = []
        current_time = time.time()
        
        while self.message_buffer:
            _, message = heapq.heappop(self.message_buffer)
            messages.append(message)
            self.delivered_messages[message.msg_id] = current_time
        
        messages.sort(key=lambda m: m.corrected_timestamp)
        self.messages_delivered += len(messages)
        
        return messages


class CausalOrderingManager:
    """
    Manages causal ordering of messages using vector clocks.
    Ensures that causally related messages are delivered in the correct order.
    """
    
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.vector_clock: Dict[str, int] = defaultdict(int)
        self.pending_messages: Dict[str, List[TimedMessage]] = defaultdict(list)
        
    def increment_clock(self):
        """Increment local clock for outgoing message"""
        self.vector_clock[self.node_id] += 1
    
    def update_clock(self, sender_clock: Dict[str, int]):
        """Update vector clock based on received message"""
        for node, clock_value in sender_clock.items():
            if node != self.node_id:
                self.vector_clock[node] = max(self.vector_clock[node], clock_value)
        
        # Increment local clock
        self.vector_clock[self.node_id] += 1
    
    def can_deliver(self, message: TimedMessage) -> bool:
        """Check if message can be delivered based on causal ordering"""
        if not message.vector_clock:
            return True  # No causal constraints
        
        sender = message.sender
        
        # Check causal ordering constraints
        for node, clock_value in message.vector_clock.items():
            if node == sender:
                # Sender's clock should be exactly one more than our last from sender
                if clock_value != self.vector_clock[sender] + 1:
                    return False
            else:
                # Other nodes' clocks should not be ahead of ours
                if clock_value > self.vector_clock[node]:
                    return False
        
        return True
    
    def add_pending_message(self, message: TimedMessage):
        """Add message to pending queue for causal ordering"""
        self.pending_messages[message.sender].append(message)
    
    def get_deliverable_messages(self) -> List[TimedMessage]:
        """Get messages that can be delivered according to causal ordering"""
        deliverable = []
        
        for sender in list(self.pending_messages.keys()):
            messages = self.pending_messages[sender]
            still_pending = []
            
            for message in messages:
                if self.can_deliver(message):
                    deliverable.append(message)
                    if message.vector_clock:
                        self.update_clock(message.vector_clock)
                else:
                    still_pending.append(message)
            
            if still_pending:
                self.pending_messages[sender] = still_pending
            else:
                del self.pending_messages[sender]
        
        return sorted(deliverable, key=lambda m: m.corrected_timestamp)