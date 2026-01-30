#!/usr/bin/env python3
"""
JARVIS AI Assistant - Main Entry Point

A comprehensive AI-powered assistant for Linux featuring voice interaction,
task automation, system control, and contextual awareness.
"""

import asyncio
import signal
import sys
from pathlib import Path

import click
from loguru import logger

# Add project root to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from jarvis.core.engine import JarvisEngine
from jarvis.core.config import Config
from jarvis.core.logger import setup_logging


class GracefulExit(SystemExit):
    """Custom exception for graceful shutdown."""
    code = 0


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    raise GracefulExit()


async def run_jarvis(mode: str, config_path: str | None, debug: bool, server_host: str = None, server_port: int = 50051):
    """Main async entry point for JARVIS."""
    # Load configuration
    config = Config(config_path)
    
    if debug:
        config.set("logging.level", "DEBUG")
    
    # Override network settings from CLI
    if server_host:
        config.set("network.server_host", server_host)
    if server_port:
        config.set("network.server_port", server_port)
    
    # Setup logging
    setup_logging(config)
    
    logger.info("=" * 60)
    logger.info("🤖 JARVIS AI Assistant Starting...")
    logger.info("=" * 60)
    
    # Handle server/client modes differently
    if mode == "server":
        from jarvis.network.server import JarvisServer
        
        logger.info("Running in SERVER mode")
        server = JarvisServer(config)
        
        try:
            await server.start()
            
            # Also start web dashboard
            from jarvis.interface.web.app import create_app
            from jarvis.core.events import get_event_bus
            import uvicorn
            
            event_bus = get_event_bus()
            app = create_app(config, event_bus, None)
            
            web_config = uvicorn.Config(
                app,
                host=config.get("web.host", "0.0.0.0"),
                port=config.get("web.port", 8000),
                log_level="info" if not debug else "debug",
            )
            web_server = uvicorn.Server(web_config)
            
            await web_server.serve()
            
        except GracefulExit:
            logger.info("Graceful shutdown initiated...")
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received...")
        finally:
            await server.stop()
            logger.info("🛑 JARVIS Server shutdown complete.")
        return
    
    elif mode == "client":
        from jarvis.network.client import JarvisClient, ClientConfig
        import uuid
        
        logger.info(f"Running in CLIENT mode - connecting to {server_host}:{server_port}")
        
        client_config = ClientConfig(
            client_id=config.get("network.client.client_id", str(uuid.uuid4())),
            server_host=server_host or config.get("network.server_host", "localhost"),
            server_port=server_port or config.get("network.server_port", 50051),
            auth_token=config.get("network.auth_token", ""),
            tls_enabled=config.get("network.tls.enabled", False),
            cert_path=config.get("network.tls.cert_path"),
            key_path=config.get("network.tls.key_path"),
            ca_path=config.get("network.tls.ca_path"),
        )
        
        client = JarvisClient(client_config)
        
        try:
            await client.run()
        except GracefulExit:
            logger.info("Graceful shutdown initiated...")
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received...")
        finally:
            await client.disconnect("Shutdown")
            logger.info("🛑 JARVIS Client shutdown complete.")
        return
    
    # Original modes: voice, cli, web, all
    engine = JarvisEngine(config)
    
    try:
        await engine.initialize()
        logger.info(f"Running in {mode.upper()} mode")
        
        if mode == "voice":
            await engine.run_voice_mode()
        elif mode == "cli":
            await engine.run_cli_mode()
        elif mode == "web":
            await engine.run_web_mode()
        elif mode == "all":
            await engine.run_all_modes()
        else:
            logger.error(f"Unknown mode: {mode}")
            sys.exit(1)
            
    except GracefulExit:
        logger.info("Graceful shutdown initiated...")
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received...")
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)
    finally:
        await engine.shutdown()
        logger.info("🛑 JARVIS shutdown complete. Goodbye!")


@click.command()
@click.option(
    '--mode', '-m',
    type=click.Choice(['voice', 'cli', 'web', 'all', 'server', 'client']),
    default='voice',
    help='Operating mode: voice (default), cli, web, all, server, or client'
)
@click.option(
    '--config', '-c',
    type=click.Path(exists=True),
    default=None,
    help='Path to configuration file'
)
@click.option(
    '--debug', '-d',
    is_flag=True,
    default=False,
    help='Enable debug logging'
)
@click.option(
    '--version', '-v',
    is_flag=True,
    default=False,
    help='Show version information'
)
@click.option(
    '--server-host', '-s',
    default=None,
    help='Server hostname/IP for client mode'
)
@click.option(
    '--server-port', '-p',
    type=int,
    default=50051,
    help='Server port (default: 50051)'
)
def main(mode: str, config: str | None, debug: bool, version: bool, server_host: str | None, server_port: int):
    """
    JARVIS - AI-Powered Assistant for Linux
    
    A comprehensive voice-controlled assistant with natural language
    understanding, system control, and automation capabilities.
    """
    if version:
        from jarvis import __version__
        click.echo(f"JARVIS AI Assistant v{__version__}")
        return
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Run the async main loop
    try:
        asyncio.run(run_jarvis(mode, config, debug, server_host, server_port))
    except GracefulExit:
        pass


if __name__ == "__main__":
    main()
