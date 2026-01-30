"""
JARVIS Task Planner

Autonomous multi-step task planning and execution for complex operations
across multiple clients and devices.
"""

import asyncio
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Callable, Any

from loguru import logger


class TaskStatus(Enum):
    """Status of a task."""
    PENDING = "pending"
    RUNNING = "running"
    WAITING = "waiting"  # Waiting for user confirmation
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepType(Enum):
    """Types of task steps."""
    COMMAND = "command"          # Execute shell command
    APP = "app"                  # Launch/control application
    FILE = "file"                # File operations
    IOT = "iot"                  # IoT device control
    VOICE = "voice"              # TTS output
    WAIT = "wait"                # Wait for time/condition
    CONDITION = "condition"      # Check a condition
    CONFIRM = "confirm"          # Request user confirmation
    PARALLEL = "parallel"        # Execute multiple steps in parallel
    AI = "ai"                    # AI processing/decision


@dataclass
class TaskStep:
    """A single step in a task plan."""
    step_id: str
    step_type: StepType
    description: str
    target_client: Optional[str] = None  # None = server, "all" = broadcast
    parameters: dict = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)  # Step IDs this step depends on
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[dict] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    retry_count: int = 0
    max_retries: int = 1
    timeout_seconds: int = 60
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "step_id": self.step_id,
            "step_type": self.step_type.value,
            "description": self.description,
            "target_client": self.target_client,
            "parameters": self.parameters,
            "depends_on": self.depends_on,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
        }


@dataclass
class TaskPlan:
    """A complete task plan with multiple steps."""
    plan_id: str
    name: str
    description: str
    steps: list[TaskStep] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result_summary: Optional[str] = None
    require_confirmation: bool = False
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "plan_id": self.plan_id,
            "name": self.name,
            "description": self.description,
            "steps": [s.to_dict() for s in self.steps],
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "require_confirmation": self.require_confirmation,
        }
    
    def get_ready_steps(self) -> list[TaskStep]:
        """Get steps that are ready to execute (dependencies met)."""
        completed_ids = {s.step_id for s in self.steps if s.status == TaskStatus.COMPLETED}
        
        ready = []
        for step in self.steps:
            if step.status == TaskStatus.PENDING:
                if all(dep in completed_ids for dep in step.depends_on):
                    ready.append(step)
        
        return ready
    
    def is_complete(self) -> bool:
        """Check if all steps are done."""
        return all(s.status in (TaskStatus.COMPLETED, TaskStatus.CANCELLED) for s in self.steps)
    
    def has_failed(self) -> bool:
        """Check if any step has failed."""
        return any(s.status == TaskStatus.FAILED for s in self.steps)


class TaskPlanner:
    """
    Plans and executes multi-step tasks autonomously.
    
    Features:
    - Breaks complex requests into steps
    - Handles dependencies between steps
    - Executes across multiple clients
    - Handles failures and retries
    - Provides progress updates
    """
    
    # Templates for common multi-step tasks
    TASK_TEMPLATES = {
        "backup_and_sync": {
            "name": "Backup and Sync",
            "steps": [
                {"type": "command", "description": "Create backup archive", "command": "tar -czf backup.tar.gz {path}"},
                {"type": "file", "description": "Transfer backup to server", "operation": "upload"},
            ]
        },
        "deploy_update": {
            "name": "Deploy Update",
            "steps": [
                {"type": "command", "description": "Pull latest changes", "command": "git pull"},
                {"type": "command", "description": "Install dependencies", "command": "pip install -r requirements.txt"},
                {"type": "command", "description": "Restart service", "command": "systemctl restart {service}"},
            ]
        },
        "morning_routine": {
            "name": "Morning Routine",
            "steps": [
                {"type": "iot", "description": "Turn on lights", "device_type": "light", "action": "on"},
                {"type": "voice", "description": "Greet user", "text": "Good morning! Here's your daily briefing."},
                {"type": "command", "description": "Get weather", "command": "curl wttr.in?format=3"},
                {"type": "app", "description": "Open calendar", "app": "gnome-calendar"},
            ]
        },
    }
    
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.plans: dict[str, TaskPlan] = {}
        self.active_plan: Optional[str] = None
        
        # Execution handlers
        self._step_executors: dict[StepType, Callable] = {}
        
        # Event handlers
        self._on_plan_created: list[Callable] = []
        self._on_step_started: list[Callable] = []
        self._on_step_completed: list[Callable] = []
        self._on_plan_completed: list[Callable] = []
        
        self._running = False
        self._lock = asyncio.Lock()
    
    def register_executor(self, step_type: StepType, executor: Callable):
        """Register an executor for a step type."""
        self._step_executors[step_type] = executor
    
    def on_plan_created(self, handler: Callable):
        """Register handler for plan creation."""
        self._on_plan_created.append(handler)
    
    def on_step_completed(self, handler: Callable):
        """Register handler for step completion."""
        self._on_step_completed.append(handler)
    
    def on_plan_completed(self, handler: Callable):
        """Register handler for plan completion."""
        self._on_plan_completed.append(handler)
    
    async def create_plan(
        self,
        user_request: str,
        context: dict = None,
        ai_client = None,
    ) -> TaskPlan:
        """
        Create a task plan from a user request.
        
        Uses AI to break down complex requests into steps.
        """
        plan_id = str(uuid.uuid4())
        
        # Check for template matches
        template = self._match_template(user_request)
        if template:
            plan = self._create_from_template(plan_id, template, user_request)
        else:
            # Use AI to create plan
            plan = await self._ai_create_plan(plan_id, user_request, context, ai_client)
        
        async with self._lock:
            self.plans[plan_id] = plan
        
        # Notify handlers
        for handler in self._on_plan_created:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(plan)
                else:
                    handler(plan)
            except Exception as e:
                logger.error(f"Plan created handler error: {e}")
        
        return plan
    
    def _match_template(self, request: str) -> Optional[dict]:
        """Match request to a template."""
        request_lower = request.lower()
        
        if "backup" in request_lower and ("sync" in request_lower or "transfer" in request_lower):
            return self.TASK_TEMPLATES["backup_and_sync"]
        elif "deploy" in request_lower or "update" in request_lower:
            return self.TASK_TEMPLATES["deploy_update"]
        elif "morning" in request_lower and "routine" in request_lower:
            return self.TASK_TEMPLATES["morning_routine"]
        
        return None
    
    def _create_from_template(self, plan_id: str, template: dict, request: str) -> TaskPlan:
        """Create a plan from a template."""
        steps = []
        
        for i, step_def in enumerate(template["steps"]):
            step = TaskStep(
                step_id=f"{plan_id}-step-{i}",
                step_type=StepType(step_def["type"]),
                description=step_def["description"],
                parameters={k: v for k, v in step_def.items() if k not in ("type", "description")},
            )
            
            # Add dependencies (sequential by default)
            if i > 0:
                step.depends_on.append(f"{plan_id}-step-{i-1}")
            
            steps.append(step)
        
        return TaskPlan(
            plan_id=plan_id,
            name=template["name"],
            description=request,
            steps=steps,
        )
    
    async def _ai_create_plan(
        self,
        plan_id: str,
        request: str,
        context: dict = None,
        ai_client = None,
    ) -> TaskPlan:
        """Use AI to create a task plan."""
        if not ai_client:
            # Create a simple single-step plan
            return TaskPlan(
                plan_id=plan_id,
                name="User Request",
                description=request,
                steps=[
                    TaskStep(
                        step_id=f"{plan_id}-step-0",
                        step_type=StepType.AI,
                        description=request,
                        parameters={"request": request},
                    )
                ],
            )
        
        # AI-powered planning
        prompt = f"""Break down this request into executable steps. 
Return a JSON object with this structure:
{{
    "name": "Brief task name",
    "steps": [
        {{
            "type": "command|app|file|iot|voice|wait|condition",
            "description": "What this step does",
            "target": "client hostname or null for server",
            "parameters": {{...}}
        }}
    ]
}}

Request: {request}

Context: {json.dumps(context or {})}

Available step types:
- command: Shell command execution
- app: Launch application
- file: File operations (read, write, copy, delete)
- iot: IoT device control (device_id, action)
- voice: Speak text
- wait: Wait for seconds or condition
- condition: Check a condition before proceeding

Return ONLY valid JSON, no explanations."""

        try:
            response = await ai_client.complete(prompt)
            
            # Parse response
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                plan_data = json.loads(json_match.group())
                
                steps = []
                for i, step_def in enumerate(plan_data.get("steps", [])):
                    step_type_str = step_def.get("type", "command")
                    try:
                        step_type = StepType(step_type_str)
                    except ValueError:
                        step_type = StepType.COMMAND
                    
                    step = TaskStep(
                        step_id=f"{plan_id}-step-{i}",
                        step_type=step_type,
                        description=step_def.get("description", ""),
                        target_client=step_def.get("target"),
                        parameters=step_def.get("parameters", {}),
                    )
                    
                    # Sequential dependencies by default
                    if i > 0:
                        step.depends_on.append(f"{plan_id}-step-{i-1}")
                    
                    steps.append(step)
                
                return TaskPlan(
                    plan_id=plan_id,
                    name=plan_data.get("name", "AI Generated Task"),
                    description=request,
                    steps=steps,
                )
        
        except Exception as e:
            logger.error(f"AI planning error: {e}")
        
        # Fallback to single step
        return TaskPlan(
            plan_id=plan_id,
            name="User Request",
            description=request,
            steps=[
                TaskStep(
                    step_id=f"{plan_id}-step-0",
                    step_type=StepType.AI,
                    description=request,
                    parameters={"request": request},
                )
            ],
        )
    
    async def execute_plan(
        self,
        plan_id: str,
        parallel: bool = True,
    ) -> bool:
        """
        Execute a task plan.
        
        Args:
            plan_id: ID of the plan to execute
            parallel: Execute independent steps in parallel
        
        Returns:
            True if plan completed successfully
        """
        plan = self.plans.get(plan_id)
        if not plan:
            logger.error(f"Plan not found: {plan_id}")
            return False
        
        if plan.require_confirmation:
            plan.status = TaskStatus.WAITING
            logger.info(f"Plan {plan.name} waiting for confirmation")
            return False
        
        plan.status = TaskStatus.RUNNING
        plan.started_at = datetime.now()
        self.active_plan = plan_id
        
        logger.info(f"Executing plan: {plan.name} ({len(plan.steps)} steps)")
        
        try:
            while not plan.is_complete() and not plan.has_failed():
                ready_steps = plan.get_ready_steps()
                
                if not ready_steps:
                    if not plan.is_complete():
                        logger.warning("No ready steps but plan not complete - possible deadlock")
                        break
                    continue
                
                if parallel:
                    # Execute ready steps in parallel
                    tasks = [self._execute_step(step) for step in ready_steps]
                    await asyncio.gather(*tasks)
                else:
                    # Execute sequentially
                    for step in ready_steps:
                        await self._execute_step(step)
                        if step.status == TaskStatus.FAILED:
                            break
            
            # Determine final status
            if plan.has_failed():
                plan.status = TaskStatus.FAILED
                plan.result_summary = "Plan failed: " + ", ".join(
                    s.error for s in plan.steps if s.status == TaskStatus.FAILED
                )
            else:
                plan.status = TaskStatus.COMPLETED
                plan.result_summary = "All steps completed successfully"
            
            plan.completed_at = datetime.now()
            
            # Notify handlers
            for handler in self._on_plan_completed:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(plan)
                    else:
                        handler(plan)
                except Exception as e:
                    logger.error(f"Plan completed handler error: {e}")
            
            return plan.status == TaskStatus.COMPLETED
            
        except Exception as e:
            logger.exception(f"Plan execution error: {e}")
            plan.status = TaskStatus.FAILED
            plan.result_summary = str(e)
            return False
        finally:
            self.active_plan = None
    
    async def _execute_step(self, step: TaskStep) -> bool:
        """Execute a single step."""
        step.status = TaskStatus.RUNNING
        step.started_at = datetime.now()
        
        logger.debug(f"Executing step: {step.description}")
        
        # Notify handlers
        for handler in self._on_step_started:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(step)
                else:
                    handler(step)
            except Exception as e:
                logger.error(f"Step started handler error: {e}")
        
        try:
            # Get executor for step type
            executor = self._step_executors.get(step.step_type)
            
            if executor:
                result = await asyncio.wait_for(
                    executor(step),
                    timeout=step.timeout_seconds,
                )
            else:
                # Default execution based on type
                result = await self._default_execute(step)
            
            step.result = result
            step.status = TaskStatus.COMPLETED
            step.completed_at = datetime.now()
            
            logger.debug(f"Step completed: {step.description}")
            
        except asyncio.TimeoutError:
            step.status = TaskStatus.FAILED
            step.error = "Step timed out"
            logger.warning(f"Step timed out: {step.description}")
            
        except Exception as e:
            step.status = TaskStatus.FAILED
            step.error = str(e)
            logger.error(f"Step failed: {step.description} - {e}")
            
            # Retry logic
            if step.retry_count < step.max_retries:
                step.retry_count += 1
                step.status = TaskStatus.PENDING
                logger.info(f"Retrying step: {step.description} (attempt {step.retry_count})")
        
        # Notify handlers
        for handler in self._on_step_completed:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(step)
                else:
                    handler(step)
            except Exception as e:
                logger.error(f"Step completed handler error: {e}")
        
        return step.status == TaskStatus.COMPLETED
    
    async def _default_execute(self, step: TaskStep) -> dict:
        """Default step execution."""
        if step.step_type == StepType.WAIT:
            seconds = step.parameters.get("seconds", 1)
            await asyncio.sleep(seconds)
            return {"waited": seconds}
        
        elif step.step_type == StepType.VOICE:
            text = step.parameters.get("text", "")
            logger.info(f"[TTS] {text}")
            return {"spoken": text}
        
        elif step.step_type == StepType.CONDITION:
            # Placeholder - would check actual conditions
            return {"condition": True}
        
        else:
            return {"note": "Step executed with default handler"}
    
    async def cancel_plan(self, plan_id: str) -> bool:
        """Cancel a running plan."""
        plan = self.plans.get(plan_id)
        if not plan:
            return False
        
        plan.status = TaskStatus.CANCELLED
        
        for step in plan.steps:
            if step.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
                step.status = TaskStatus.CANCELLED
        
        logger.info(f"Plan cancelled: {plan.name}")
        return True
    
    def get_plan(self, plan_id: str) -> Optional[TaskPlan]:
        """Get a plan by ID."""
        return self.plans.get(plan_id)
    
    def get_active_plans(self) -> list[TaskPlan]:
        """Get all active (running) plans."""
        return [p for p in self.plans.values() if p.status == TaskStatus.RUNNING]
    
    def get_plan_history(self, limit: int = 10) -> list[TaskPlan]:
        """Get recent completed plans."""
        completed = [p for p in self.plans.values() 
                    if p.status in (TaskStatus.COMPLETED, TaskStatus.FAILED)]
        completed.sort(key=lambda p: p.completed_at or datetime.min, reverse=True)
        return completed[:limit]
