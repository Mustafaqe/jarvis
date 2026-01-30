"""
JARVIS Web Dashboard

FastAPI-based web interface for remote control and monitoring.
"""

from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from loguru import logger
import psutil

from jarvis.core.events import EventBus, EventType


def create_app(config, event_bus: EventBus, engine) -> FastAPI:
    """
    Create the FastAPI application.
    
    Args:
        config: Configuration object
        event_bus: Event bus for communication
        engine: JARVIS engine instance
    
    Returns:
        FastAPI application
    """
    app = FastAPI(
        title="JARVIS Dashboard",
        description="AI-Powered Assistant Web Interface",
        version="1.0.0"
    )
    
    # Store references
    app.state.config = config
    app.state.event_bus = event_bus
    app.state.engine = engine
    
    # WebSocket connections
    active_connections: list[WebSocket] = []
    
    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request):
        """Main dashboard page."""
        html_content = get_dashboard_html()
        return HTMLResponse(content=html_content)
    
    @app.get("/api/status")
    async def get_status():
        """Get system status."""
        cpu = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        return {
            "status": "running",
            "timestamp": datetime.now().isoformat(),
            "system": {
                "cpu_percent": cpu,
                "memory_percent": mem.percent,
                "memory_used_gb": round(mem.used / (1024**3), 1),
                "memory_total_gb": round(mem.total / (1024**3), 1),
                "disk_percent": disk.percent,
                "disk_free_gb": round(disk.free / (1024**3), 1),
            }
        }
    
    @app.post("/api/command")
    async def send_command(request: Request):
        """Send a command to JARVIS."""
        data = await request.json()
        text = data.get("text", "")
        
        if not text:
            return {"error": "No command provided"}
        
        # Emit user input event
        await event_bus.emit(
            EventType.USER_INPUT,
            {"text": text, "source": "web"},
            source="web"
        )
        
        # Process and get response
        if engine._ai_manager:
            response = await engine._ai_manager.process(text)
        else:
            response = engine._fallback_response(text)
        
        return {"response": response}
    
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """WebSocket for real-time updates."""
        await websocket.accept()
        active_connections.append(websocket)
        
        try:
            while True:
                # Receive message from client
                data = await websocket.receive_json()
                
                if data.get("type") == "command":
                    text = data.get("text", "")
                    
                    # Process command
                    if engine._ai_manager:
                        response = await engine._ai_manager.process(text)
                    else:
                        response = engine._fallback_response(text)
                    
                    # Send response
                    await websocket.send_json({
                        "type": "response",
                        "text": response,
                        "timestamp": datetime.now().isoformat()
                    })
                
                elif data.get("type") == "status":
                    # Send system status
                    status = await get_status()
                    await websocket.send_json({
                        "type": "status",
                        **status
                    })
                    
        except WebSocketDisconnect:
            active_connections.remove(websocket)
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            if websocket in active_connections:
                active_connections.remove(websocket)
    
    return app


def get_dashboard_html() -> str:
    """Generate the dashboard HTML."""
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>JARVIS Dashboard</title>
    <style>
        :root {
            --bg-primary: #0a0a0f;
            --bg-secondary: #12121a;
            --bg-tertiary: #1a1a25;
            --accent: #3b82f6;
            --accent-glow: rgba(59, 130, 246, 0.3);
            --text-primary: #f0f0f5;
            --text-secondary: #8888a0;
            --border: #2a2a3a;
            --success: #22c55e;
            --warning: #f59e0b;
            --danger: #ef4444;
        }
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 2rem;
        }
        
        header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 2rem;
            padding-bottom: 1rem;
            border-bottom: 1px solid var(--border);
        }
        
        .logo {
            display: flex;
            align-items: center;
            gap: 1rem;
        }
        
        .logo-icon {
            width: 48px;
            height: 48px;
            background: linear-gradient(135deg, var(--accent), #8b5cf6);
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 24px;
            box-shadow: 0 0 30px var(--accent-glow);
        }
        
        .logo h1 {
            font-size: 1.5rem;
            font-weight: 600;
        }
        
        .status-badge {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.5rem 1rem;
            background: var(--bg-tertiary);
            border-radius: 9999px;
            font-size: 0.875rem;
        }
        
        .status-dot {
            width: 8px;
            height: 8px;
            background: var(--success);
            border-radius: 50%;
            animation: pulse 2s infinite;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        
        .grid {
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 1.5rem;
            margin-bottom: 2rem;
        }
        
        .card {
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 1.5rem;
        }
        
        .card-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 1rem;
        }
        
        .card-title {
            font-size: 0.875rem;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        
        .card-value {
            font-size: 2.5rem;
            font-weight: 700;
        }
        
        .card-value.cpu { color: var(--accent); }
        .card-value.memory { color: #8b5cf6; }
        .card-value.disk { color: #22c55e; }
        
        .progress-bar {
            height: 8px;
            background: var(--bg-tertiary);
            border-radius: 4px;
            overflow: hidden;
            margin-top: 1rem;
        }
        
        .progress-fill {
            height: 100%;
            border-radius: 4px;
            transition: width 0.3s ease;
        }
        
        .progress-fill.cpu { background: var(--accent); }
        .progress-fill.memory { background: #8b5cf6; }
        .progress-fill.disk { background: #22c55e; }
        
        .chat-container {
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 16px;
            overflow: hidden;
        }
        
        .chat-header {
            padding: 1rem 1.5rem;
            border-bottom: 1px solid var(--border);
            font-weight: 600;
        }
        
        .chat-messages {
            height: 400px;
            overflow-y: auto;
            padding: 1.5rem;
        }
        
        .message {
            margin-bottom: 1rem;
            max-width: 80%;
        }
        
        .message.user {
            margin-left: auto;
        }
        
        .message-content {
            padding: 1rem 1.25rem;
            border-radius: 16px;
            line-height: 1.5;
        }
        
        .message.user .message-content {
            background: var(--accent);
            color: white;
            border-bottom-right-radius: 4px;
        }
        
        .message.assistant .message-content {
            background: var(--bg-tertiary);
            border-bottom-left-radius: 4px;
        }
        
        .message-time {
            font-size: 0.75rem;
            color: var(--text-secondary);
            margin-top: 0.25rem;
        }
        
        .chat-input {
            display: flex;
            padding: 1rem 1.5rem;
            border-top: 1px solid var(--border);
            gap: 1rem;
        }
        
        .chat-input input {
            flex: 1;
            padding: 1rem 1.25rem;
            background: var(--bg-tertiary);
            border: 1px solid var(--border);
            border-radius: 12px;
            color: var(--text-primary);
            font-size: 1rem;
            outline: none;
            transition: border-color 0.2s;
        }
        
        .chat-input input:focus {
            border-color: var(--accent);
        }
        
        .chat-input button {
            padding: 1rem 2rem;
            background: var(--accent);
            color: white;
            border: none;
            border-radius: 12px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.1s, box-shadow 0.2s;
        }
        
        .chat-input button:hover {
            transform: translateY(-1px);
            box-shadow: 0 4px 20px var(--accent-glow);
        }
        
        @media (max-width: 768px) {
            .grid {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="logo">
                <div class="logo-icon">🤖</div>
                <h1>JARVIS Dashboard</h1>
            </div>
            <div class="status-badge">
                <span class="status-dot"></span>
                <span>Online</span>
            </div>
        </header>
        
        <div class="grid">
            <div class="card">
                <div class="card-header">
                    <span class="card-title">CPU Usage</span>
                </div>
                <div class="card-value cpu" id="cpu-value">--%</div>
                <div class="progress-bar">
                    <div class="progress-fill cpu" id="cpu-bar" style="width: 0%"></div>
                </div>
            </div>
            
            <div class="card">
                <div class="card-header">
                    <span class="card-title">Memory Usage</span>
                </div>
                <div class="card-value memory" id="mem-value">--%</div>
                <div class="progress-bar">
                    <div class="progress-fill memory" id="mem-bar" style="width: 0%"></div>
                </div>
            </div>
            
            <div class="card">
                <div class="card-header">
                    <span class="card-title">Disk Usage</span>
                </div>
                <div class="card-value disk" id="disk-value">--%</div>
                <div class="progress-bar">
                    <div class="progress-fill disk" id="disk-bar" style="width: 0%"></div>
                </div>
            </div>
        </div>
        
        <div class="chat-container">
            <div class="chat-header">💬 Chat with JARVIS</div>
            <div class="chat-messages" id="chat-messages">
                <div class="message assistant">
                    <div class="message-content">
                        Hello! I'm JARVIS, your AI assistant. How can I help you today?
                    </div>
                    <div class="message-time">Just now</div>
                </div>
            </div>
            <div class="chat-input">
                <input type="text" id="chat-input" placeholder="Type a message..." autocomplete="off">
                <button onclick="sendMessage()">Send</button>
            </div>
        </div>
    </div>
    
    <script>
        const chatMessages = document.getElementById('chat-messages');
        const chatInput = document.getElementById('chat-input');
        
        // Update system stats
        async function updateStats() {
            try {
                const response = await fetch('/api/status');
                const data = await response.json();
                
                document.getElementById('cpu-value').textContent = data.system.cpu_percent + '%';
                document.getElementById('cpu-bar').style.width = data.system.cpu_percent + '%';
                
                document.getElementById('mem-value').textContent = data.system.memory_percent + '%';
                document.getElementById('mem-bar').style.width = data.system.memory_percent + '%';
                
                document.getElementById('disk-value').textContent = data.system.disk_percent + '%';
                document.getElementById('disk-bar').style.width = data.system.disk_percent + '%';
            } catch (e) {
                console.error('Failed to update stats:', e);
            }
        }
        
        // Send message
        async function sendMessage() {
            const text = chatInput.value.trim();
            if (!text) return;
            
            // Add user message
            addMessage(text, 'user');
            chatInput.value = '';
            
            try {
                const response = await fetch('/api/command', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text })
                });
                const data = await response.json();
                
                // Add assistant response
                addMessage(data.response || data.error, 'assistant');
            } catch (e) {
                addMessage('Sorry, there was an error processing your request.', 'assistant');
            }
        }
        
        function addMessage(text, role) {
            const div = document.createElement('div');
            div.className = 'message ' + role;
            div.innerHTML = `
                <div class="message-content">${escapeHtml(text)}</div>
                <div class="message-time">${new Date().toLocaleTimeString()}</div>
            `;
            chatMessages.appendChild(div);
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }
        
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
        
        // Enter to send
        chatInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') sendMessage();
        });
        
        // Initial load and refresh
        updateStats();
        setInterval(updateStats, 5000);
    </script>
</body>
</html>
"""
