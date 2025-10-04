import time
import logging
from aiohttp import web
from typing import Dict, Any

logger = logging.getLogger(__name__)


async def time_handler(request):
    """
    Handle time synchronization requests (NTP-style).
    Returns server timestamps for clock synchronization.
    """
    node = request.app.get('node')
    time_sync = getattr(node, 'time_sync', None) if node else None
    
    # Record when we received the request
    server_receive_time = time.time()
    
    # Get synchronized time if available
    if time_sync and hasattr(time_sync, 'get_synchronized_time'):
        synchronized_time = time_sync.get_synchronized_time()
    else:
        synchronized_time = server_receive_time
    
    # Prepare response
    server_send_time = time.time()
    
    response_data = {
        "server_receive_time": server_receive_time,
        "server_send_time": server_send_time,
        "synchronized_time": synchronized_time,
        "local_time": server_send_time,
        "node_id": getattr(node, 'node_id', 'unknown') if node else 'unknown'
    }
    
    # Add synchronization status if available
    if time_sync:
        response_data.update({
            "is_synchronized": time_sync.is_synchronized(),
            "clock_offset": time_sync.clock_offset,
            "sync_accuracy": time_sync.sync_accuracy,
            "last_sync_time": time_sync.last_sync_time
        })
    
    logger.debug(f"Time sync request served: offset={time_sync.clock_offset:.6f}s" 
                if time_sync else "Time sync request served (no sync manager)")
    
    return web.json_response(response_data)


async def clock_status_handler(request):
    """
    Get detailed clock and synchronization status.
    """
    node = request.app.get('node')
    current_time = time.time()
    
    status = {
        "current_time": current_time,
        "node_id": getattr(node, 'node_id', 'unknown') if node else 'unknown',
        "timestamp": current_time
    }
    
    # Add time synchronization status
    time_sync = getattr(node, 'time_sync', None) if node else None
    if time_sync:
        status.update({
            "time_synchronization": time_sync.get_sync_status(),
            "synchronized_time": time_sync.get_synchronized_time()
        })
    else:
        status["time_synchronization"] = {"status": "not_available"}
    
    # Add clock skew analysis
    clock_analyzer = getattr(node, 'clock_analyzer', None) if node else None
    if clock_analyzer:
        status["clock_skew_analysis"] = clock_analyzer.get_skew_statistics()
    else:
        status["clock_skew_analysis"] = {"status": "not_available"}
    
    # Add timestamp correction info
    timestamp_corrector = getattr(node, 'timestamp_corrector', None) if node else None
    if timestamp_corrector:
        status["timestamp_correction"] = timestamp_corrector.get_correction_statistics()
    else:
        status["timestamp_correction"] = {"status": "not_available"}
    
    # Add message ordering buffer status
    message_buffer = getattr(node, 'message_buffer', None) if node else None
    if message_buffer:
        status["message_ordering"] = message_buffer.get_buffer_status()
    else:
        status["message_ordering"] = {"status": "not_available"}
    
    return web.json_response(status)


async def sync_trigger_handler(request):
    """
    Manually trigger time synchronization with peers.
    """
    node = request.app.get('node')
    time_sync = getattr(node, 'time_sync', None) if node else None
    
    if not time_sync:
        return web.json_response(
            {"status": "error", "message": "Time synchronization not available"}, 
            status=503
        )
    
    try:
        # Trigger synchronization with node context for failure detection
        success = await time_sync.synchronize_with_peers(node)
        
        if success:
            return web.json_response({
                "status": "ok",
                "message": "Time synchronization completed",
                "sync_status": time_sync.get_sync_status()
            })
        else:
            return web.json_response({
                "status": "partial",
                "message": "Time synchronization completed with limited success",
                "sync_status": time_sync.get_sync_status()
            }, status=206)
    
    except Exception as e:
        logger.error(f"Manual sync trigger failed: {e}")
        return web.json_response(
            {"status": "error", "message": f"Synchronization failed: {str(e)}"}, 
            status=500
        )


async def timestamp_correct_handler(request):
    """
    Apply timestamp correction to a given timestamp.
    """
    node = request.app.get('node')
    timestamp_corrector = getattr(node, 'timestamp_corrector', None) if node else None
    
    if not timestamp_corrector:
        return web.json_response(
            {"status": "error", "message": "Timestamp correction not available"}, 
            status=503
        )
    
    try:
        payload = await request.json()
        original_timestamp = payload.get('timestamp')
        sender = payload.get('sender')
        
        if original_timestamp is None:
            return web.json_response(
                {"status": "error", "message": "Missing timestamp parameter"}, 
                status=400
            )
        
        # Validate timestamp
        is_valid, reason = timestamp_corrector.validate_timestamp(original_timestamp)
        if not is_valid:
            return web.json_response(
                {"status": "error", "message": f"Invalid timestamp: {reason}"}, 
                status=400
            )
        
        # Apply correction
        corrected_timestamp, correction_info = timestamp_corrector.correct_timestamp(
            original_timestamp, sender
        )
        
        # Estimate accuracy
        accuracy = timestamp_corrector.estimate_accuracy(
            corrected_timestamp, original_timestamp, sender
        )
        
        return web.json_response({
            "status": "ok",
            "original_timestamp": original_timestamp,
            "corrected_timestamp": corrected_timestamp,
            "correction_info": correction_info,
            "estimated_accuracy": accuracy
        })
    
    except Exception as e:
        logger.error(f"Timestamp correction failed: {e}")
        return web.json_response(
            {"status": "error", "message": f"Correction failed: {str(e)}"}, 
            status=500
        )


async def ordering_status_handler(request):
    """
    Get message ordering buffer status and statistics.
    """
    node = request.app.get('node')
    message_buffer = getattr(node, 'message_buffer', None) if node else None
    
    if not message_buffer:
        return web.json_response(
            {"status": "error", "message": "Message ordering not available"}, 
            status=503
        )
    
    try:
        status = message_buffer.get_buffer_status()
        
        # Add deliverable messages count
        deliverable_messages = message_buffer.get_deliverable_messages()
        status["deliverable_messages_count"] = len(deliverable_messages)
        
        # Add sample of deliverable messages (first 5)
        if deliverable_messages:
            status["sample_deliverable_messages"] = [
                {
                    "msg_id": msg.msg_id,
                    "corrected_timestamp": msg.corrected_timestamp,
                    "original_timestamp": msg.original_timestamp,
                    "sender": msg.sender
                }
                for msg in deliverable_messages[:5]
            ]
        
        return web.json_response({
            "status": "ok",
            "ordering_status": status
        })
    
    except Exception as e:
        logger.error(f"Ordering status request failed: {e}")
        return web.json_response(
            {"status": "error", "message": f"Status request failed: {str(e)}"}, 
            status=500
        )


async def force_delivery_handler(request):
    """
    Force delivery of all buffered messages (emergency operation).
    """
    node = request.app.get('node')
    message_buffer = getattr(node, 'message_buffer', None) if node else None
    
    if not message_buffer:
        return web.json_response(
            {"status": "error", "message": "Message ordering not available"}, 
            status=503
        )
    
    try:
        # Force delivery of all messages
        delivered_messages = message_buffer.force_deliver_all()
        
        return web.json_response({
            "status": "ok",
            "message": "All buffered messages forced for delivery",
            "delivered_count": len(delivered_messages),
            "delivered_messages": [
                {
                    "msg_id": msg.msg_id,
                    "corrected_timestamp": msg.corrected_timestamp,
                    "sender": msg.sender,
                    "recipient": msg.recipient
                }
                for msg in delivered_messages
            ]
        })
    
    except Exception as e:
        logger.error(f"Force delivery failed: {e}")
        return web.json_response(
            {"status": "error", "message": f"Force delivery failed: {str(e)}"}, 
            status=500
        )


async def time_stats_handler(request):
    """
    Get comprehensive time-related statistics and metrics.
    """
    node = request.app.get('node')
    current_time = time.time()
    
    stats = {
        "timestamp": current_time,
        "node_id": getattr(node, 'node_id', 'unknown') if node else 'unknown'
    }
    
    # Time synchronization stats
    time_sync = getattr(node, 'time_sync', None) if node else None
    if time_sync:
        sync_status = time_sync.get_sync_status()
        stats["synchronization"] = {
            "is_synchronized": sync_status["synchronized"],
            "success_rate": sync_status["success_rate"],
            "attempts": sync_status["sync_attempts"],
            "successful": sync_status["successful_syncs"],
            "current_offset": sync_status["clock_offset"],
            "accuracy": sync_status["sync_accuracy"],
            "peer_count": len(sync_status.get("peer_offsets", {}))
        }
    
    # Clock skew analysis stats
    clock_analyzer = getattr(node, 'clock_analyzer', None) if node else None
    if clock_analyzer:
        skew_stats = clock_analyzer.get_skew_statistics()
        if "current_skew" in skew_stats:
            stats["clock_skew"] = {
                "current_skew": skew_stats["current_skew"],
                "drift_rate": skew_stats["drift_rate"],
                "measurements": skew_stats["measurements"],
                "std_deviation": skew_stats["std_deviation"],
                "acceptable": skew_stats["acceptable"],
                "recommended_sync_interval": clock_analyzer.recommend_sync_interval()
            }
    
    # Timestamp correction stats
    timestamp_corrector = getattr(node, 'timestamp_corrector', None) if node else None
    if timestamp_corrector:
        correction_stats = timestamp_corrector.get_correction_statistics()
        stats["timestamp_correction"] = {
            "corrections_applied": correction_stats["corrections_applied"],
            "average_magnitude": correction_stats["average_correction_magnitude"],
            "max_magnitude": correction_stats["max_correction_magnitude"],
            "method": correction_stats["current_method"]
        }
    
    # Message ordering stats
    message_buffer = getattr(node, 'message_buffer', None) if node else None
    if message_buffer:
        buffer_stats = message_buffer.get_buffer_status()
        stats["message_ordering"] = {
            "buffer_size": buffer_stats["buffer_size"],
            "utilization": buffer_stats["buffer_utilization"],
            "reordered": buffer_stats["messages_reordered"],
            "delivered": buffer_stats["messages_delivered"],
            "reorder_rate": buffer_stats["reorder_rate"],
            "average_age": buffer_stats["average_message_age"]
        }
    
    return web.json_response({
        "status": "ok",
        "statistics": stats
    })


async def reset_stats_handler(request):
    """
    Reset time-related statistics (for testing/debugging).
    """
    node = request.app.get('node')
    reset_count = 0
    
    # Reset timestamp corrector stats
    timestamp_corrector = getattr(node, 'timestamp_corrector', None) if node else None
    if timestamp_corrector:
        timestamp_corrector.reset_statistics()
        reset_count += 1
    
    # Reset clock analyzer stats
    clock_analyzer = getattr(node, 'clock_analyzer', None) if node else None
    if clock_analyzer:
        clock_analyzer.reset_analysis()
        reset_count += 1
    
    return web.json_response({
        "status": "ok",
        "message": f"Reset {reset_count} statistics modules",
        "timestamp": time.time()
    })