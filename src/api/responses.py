from typing import Any, Dict, Optional, Union
from dataclasses import dataclass
from flask import Response, jsonify, stream_with_context
import json

@dataclass
class APIResponse:
    """Standard API response format"""
    status: bool
    data: Optional[Any] = None
    reason: Optional[str] = None
    http_status: int = 200

def create_stream_response(data: Any) -> Response:
    """
    Create a streaming response for long-running requests
    
    Args:
        data: Data to stream
        
    Returns:
        Response: Flask response object
    """
    def generate() -> str:
        yield json.dumps(data)
    
    response = Response(
        generate(),
        mimetype='application/json'
    )
    response.headers['X-Accel-Buffering'] = 'no'
    response.headers['Cache-Control'] = 'no-cache'
    return response

def json_response(
    response_data: Union[Dict[str, Any], APIResponse],
    status: int = 200
) -> Response:
    """
    Create a JSON response with proper headers
    
    Args:
        response_data: Response data or APIResponse object
        status: HTTP status code
        
    Returns:
        Response: Flask response object
    """
    # Convert APIResponse to dict if needed
    if isinstance(response_data, APIResponse):
        data = {
            "status": response_data.status,
            **({"data": response_data.data} if response_data.data is not None else {}),
            **({"reason": response_data.reason} if response_data.reason is not None else {})
        }
        status = response_data.http_status
    else:
        data = response_data
    
    # Use streaming response for success status
    if status == 200:
        resp = create_stream_response(data)
    else:
        resp = jsonify(data)
    
    resp.status_code = status
    return resp

def error_response(message: str, status: int = 500) -> Response:
    """
    Create an error response
    
    Args:
        message: Error message
        status: HTTP status code
        
    Returns:
        Response: Flask response object
    """
    return json_response(
        APIResponse(
            status=False,
            reason=message,
            http_status=status
        )
    )

def success_response(data: Any = None) -> Response:
    """
    Create a success response
    
    Args:
        data: Response data
        
    Returns:
        Response: Flask response object
    """
    return json_response(
        APIResponse(
            status=True,
            data=data
        )
    ) 