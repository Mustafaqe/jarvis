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


async def run_jarvis(mode: str, config_path: str | None, debug: bool):
    """Main async entry point for JARVIS."""
    # Load configuration
    config = Config(config_path)
    
    if debug:
        config.set("logging.level", "DEBUG")
    
    # Setup logging
    setup_logging(config)
    
    logger.info("=" * 60)
    logger.info("🤖 JARVIS AI Assistant Starting...")
    logger.info("=" * 60)
    
    # Initialize the engine
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
    type=click.Choice(['voice', 'cli', 'web', 'all']),
    default='voice',
    help='Operating mode: voice (default), cli, web, or all'
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
def main(mode: str, config: str | None, debug: bool, version: bool):
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
        asyncio.run(run_jarvis(mode, config, debug))
    except GracefulExit:
        pass


if __name__ == "__main__":
    main()
