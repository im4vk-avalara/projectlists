"""
AIOS Access Manager

Manages access control with privilege groups and user confirmation.

Paper Reference: Section 3.8
Spec Reference: ThreatModel.md, Architecture.md
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
import uuid

logger = logging.getLogger(__name__)


class Permission(str, Enum):
    """Permission types."""
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    DELETE = "delete"
    SHARE = "share"
    ADMIN = "admin"


class PrivilegeLevel(str, Enum):
    """Agent privilege levels."""
    GUEST = "guest"      # Read-only access
    USER = "user"        # Standard access
    PRIVILEGED = "privileged"  # Extended access
    ADMIN = "admin"      # Full access
    SYSTEM = "system"    # Internal system access


@dataclass
class PrivilegeGroup:
    """
    A privilege group defining allowed operations.
    
    Paper Reference: Section 3.8 - privilege groups
    """
    name: str
    level: PrivilegeLevel
    permissions: Set[Permission] = field(default_factory=set)
    allowed_tools: Set[str] = field(default_factory=lambda: {"*"})  # "*" = all
    allowed_agents: Set[str] = field(default_factory=lambda: {"*"})  # Can interact with
    memory_limit_mb: int = 100
    storage_limit_mb: int = 500
    llm_requests_per_minute: int = 60
    
    def has_permission(self, permission: Permission) -> bool:
        """Check if group has permission."""
        if self.level == PrivilegeLevel.ADMIN:
            return True
        return permission in self.permissions
    
    def can_use_tool(self, tool_name: str) -> bool:
        """Check if group can use a tool."""
        if "*" in self.allowed_tools:
            return True
        return tool_name in self.allowed_tools
    
    def can_interact_with(self, agent_id: str) -> bool:
        """Check if can interact with another agent."""
        if "*" in self.allowed_agents:
            return True
        return agent_id in self.allowed_agents
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "level": self.level.value,
            "permissions": [p.value for p in self.permissions],
            "allowed_tools": list(self.allowed_tools),
            "memory_limit_mb": self.memory_limit_mb,
            "storage_limit_mb": self.storage_limit_mb,
        }


@dataclass
class AccessRequest:
    """A pending access request requiring confirmation."""
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str = ""
    resource: str = ""
    permission: Permission = Permission.READ
    description: str = ""
    justification: str = ""
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    status: str = "pending"  # pending, approved, denied, expired
    approved_by: Optional[str] = None
    
    def is_expired(self) -> bool:
        if self.expires_at and time.time() > self.expires_at:
            self.status = "expired"
            return True
        return False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "agent_id": self.agent_id,
            "resource": self.resource,
            "permission": self.permission.value,
            "description": self.description,
            "justification": self.justification,
            "status": self.status,
            "created_at": self.created_at,
        }


@dataclass
class AgentAccess:
    """Access configuration for an agent."""
    agent_id: str
    group: PrivilegeGroup
    custom_permissions: Set[Permission] = field(default_factory=set)
    denied_permissions: Set[Permission] = field(default_factory=set)
    granted_resources: Dict[str, Set[Permission]] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    
    def has_permission(self, permission: Permission) -> bool:
        """Check if agent has permission."""
        if permission in self.denied_permissions:
            return False
        if permission in self.custom_permissions:
            return True
        return self.group.has_permission(permission)
    
    def has_resource_permission(self, resource: str, permission: Permission) -> bool:
        """Check permission for specific resource."""
        if resource in self.granted_resources:
            return permission in self.granted_resources[resource]
        return self.has_permission(permission)


# Confirmation handler type
ConfirmationHandler = Callable[[AccessRequest], asyncio.Future]


class AccessManager:
    """
    Manages access control and user confirmation.
    
    Features:
    - Privilege groups with hierarchical permissions
    - Cross-agent access checks
    - User confirmation for irreversible operations
    - Resource-level permission grants
    
    Paper Reference: Section 3.8
    
    Example:
        access_mgr = AccessManager()
        
        # Check permission
        if await access_mgr.check_permission("agent-1", Permission.WRITE):
            # Allowed
            pass
        
        # Request user confirmation
        approved = await access_mgr.request_confirmation(
            agent_id="agent-1",
            resource="important_file.txt",
            permission=Permission.DELETE,
            description="Delete important file",
        )
    """
    
    # Default privilege groups
    DEFAULT_GROUPS = {
        "guest": PrivilegeGroup(
            name="guest",
            level=PrivilegeLevel.GUEST,
            permissions={Permission.READ},
            memory_limit_mb=50,
            storage_limit_mb=100,
        ),
        "user": PrivilegeGroup(
            name="user",
            level=PrivilegeLevel.USER,
            permissions={Permission.READ, Permission.WRITE, Permission.EXECUTE},
            memory_limit_mb=256,
            storage_limit_mb=1000,
        ),
        "privileged": PrivilegeGroup(
            name="privileged",
            level=PrivilegeLevel.PRIVILEGED,
            permissions={Permission.READ, Permission.WRITE, Permission.EXECUTE, Permission.DELETE, Permission.SHARE},
            memory_limit_mb=512,
            storage_limit_mb=5000,
        ),
        "admin": PrivilegeGroup(
            name="admin",
            level=PrivilegeLevel.ADMIN,
            permissions=set(Permission),
            memory_limit_mb=1024,
            storage_limit_mb=10000,
        ),
    }
    
    def __init__(
        self,
        default_group: str = "user",
        confirmation_timeout: int = 60,
        confirmation_handler: Optional[ConfirmationHandler] = None,
        auto_approve: bool = False,
    ):
        """
        Initialize access manager.
        
        Args:
            default_group: Default privilege group for new agents
            confirmation_timeout: Timeout for confirmation requests
            confirmation_handler: Custom handler for confirmations
            auto_approve: Auto-approve all confirmation requests (for testing)
        """
        self.default_group_name = default_group
        self.confirmation_timeout = confirmation_timeout
        self.confirmation_handler = confirmation_handler
        self.auto_approve = auto_approve
        
        # Groups
        self._groups = dict(self.DEFAULT_GROUPS)
        
        # Agent access configs
        self._agent_access: Dict[str, AgentAccess] = {}
        
        # Pending confirmation requests
        self._pending_requests: Dict[str, AccessRequest] = {}
        self._lock = asyncio.Lock()
        
        # Audit log
        self._audit_log: List[Dict[str, Any]] = []
        
        logger.info(f"Access Manager initialized (default group: {default_group})")
    
    def create_group(
        self,
        name: str,
        level: PrivilegeLevel,
        permissions: Set[Permission],
        **kwargs,
    ) -> PrivilegeGroup:
        """Create a new privilege group."""
        group = PrivilegeGroup(
            name=name,
            level=level,
            permissions=permissions,
            **kwargs,
        )
        self._groups[name] = group
        logger.info(f"Created privilege group: {name}")
        return group
    
    async def register_agent(
        self,
        agent_id: str,
        group_name: Optional[str] = None,
    ) -> AgentAccess:
        """
        Register an agent with access control.
        
        Args:
            agent_id: Agent to register
            group_name: Privilege group (or default)
            
        Returns:
            AgentAccess configuration
        """
        async with self._lock:
            group_name = group_name or self.default_group_name
            group = self._groups.get(group_name)
            
            if not group:
                raise ValueError(f"Unknown privilege group: {group_name}")
            
            access = AgentAccess(agent_id=agent_id, group=group)
            self._agent_access[agent_id] = access
            
            self._log_event("agent_registered", agent_id, group=group_name)
            logger.debug(f"Registered agent '{agent_id}' in group '{group_name}'")
            
            return access
    
    async def get_agent_access(self, agent_id: str) -> AgentAccess:
        """Get or create access config for an agent."""
        if agent_id not in self._agent_access:
            return await self.register_agent(agent_id)
        return self._agent_access[agent_id]
    
    async def check_permission(
        self,
        agent_id: str,
        permission: Permission,
        resource: Optional[str] = None,
    ) -> bool:
        """
        Check if an agent has a permission.
        
        Paper Reference: Section 3.8 - permission checks
        
        Args:
            agent_id: Agent to check
            permission: Permission to check
            resource: Optional specific resource
            
        Returns:
            True if permitted
        """
        access = await self.get_agent_access(agent_id)
        
        if resource:
            result = access.has_resource_permission(resource, permission)
        else:
            result = access.has_permission(permission)
        
        self._log_event(
            "permission_check",
            agent_id,
            permission=permission.value,
            resource=resource,
            result=result,
        )
        
        return result
    
    async def check_cross_agent_access(
        self,
        requesting_agent: str,
        target_agent: str,
        permission: Permission,
    ) -> bool:
        """
        Check if one agent can access another's resources.
        
        Paper Reference: Section 3.8 - cross-agent access checks
        """
        access = await self.get_agent_access(requesting_agent)
        
        # Check if can interact with target
        if not access.group.can_interact_with(target_agent):
            self._log_event(
                "cross_agent_denied",
                requesting_agent,
                target=target_agent,
            )
            return False
        
        # Check permission
        return access.has_permission(permission)
    
    async def check_tool_access(
        self,
        agent_id: str,
        tool_name: str,
    ) -> bool:
        """Check if an agent can use a tool."""
        access = await self.get_agent_access(agent_id)
        return access.group.can_use_tool(tool_name)
    
    async def grant_permission(
        self,
        agent_id: str,
        permission: Permission,
        resource: Optional[str] = None,
    ) -> None:
        """Grant a permission to an agent."""
        async with self._lock:
            access = await self.get_agent_access(agent_id)
            
            if resource:
                if resource not in access.granted_resources:
                    access.granted_resources[resource] = set()
                access.granted_resources[resource].add(permission)
            else:
                access.custom_permissions.add(permission)
            
            self._log_event(
                "permission_granted",
                agent_id,
                permission=permission.value,
                resource=resource,
            )
    
    async def revoke_permission(
        self,
        agent_id: str,
        permission: Permission,
        resource: Optional[str] = None,
    ) -> None:
        """Revoke a permission from an agent."""
        async with self._lock:
            access = await self.get_agent_access(agent_id)
            
            if resource:
                if resource in access.granted_resources:
                    access.granted_resources[resource].discard(permission)
            else:
                access.custom_permissions.discard(permission)
                access.denied_permissions.add(permission)
            
            self._log_event(
                "permission_revoked",
                agent_id,
                permission=permission.value,
                resource=resource,
            )
    
    async def request_confirmation(
        self,
        agent_id: str,
        resource: str,
        permission: Permission,
        description: str,
        justification: str = "",
        timeout: Optional[int] = None,
    ) -> bool:
        """
        Request user confirmation for an operation.
        
        Paper Reference: Section 3.8 - user confirmation for irreversible ops
        
        Args:
            agent_id: Requesting agent
            resource: Resource being accessed
            permission: Permission requested
            description: Human-readable description
            justification: Why access is needed
            timeout: Confirmation timeout
            
        Returns:
            True if approved, False if denied/timeout
        """
        # Auto-approve mode (for testing)
        if self.auto_approve:
            self._log_event(
                "confirmation_auto_approved",
                agent_id,
                resource=resource,
                permission=permission.value,
            )
            return True
        
        # Create request
        request = AccessRequest(
            agent_id=agent_id,
            resource=resource,
            permission=permission,
            description=description,
            justification=justification,
            expires_at=time.time() + (timeout or self.confirmation_timeout),
        )
        
        async with self._lock:
            self._pending_requests[request.request_id] = request
        
        self._log_event(
            "confirmation_requested",
            agent_id,
            request_id=request.request_id,
            resource=resource,
            permission=permission.value,
        )
        
        logger.info(
            f"Confirmation requested: {agent_id} wants {permission.value} on {resource}"
        )
        
        # Use custom handler if provided
        if self.confirmation_handler:
            try:
                future = self.confirmation_handler(request)
                result = await asyncio.wait_for(
                    future,
                    timeout=timeout or self.confirmation_timeout,
                )
                request.status = "approved" if result else "denied"
                return result
            except asyncio.TimeoutError:
                request.status = "expired"
                return False
        
        # Default: wait for manual approval
        try:
            end_time = time.time() + (timeout or self.confirmation_timeout)
            while time.time() < end_time:
                if request.status != "pending":
                    return request.status == "approved"
                await asyncio.sleep(0.1)
            
            request.status = "expired"
            return False
            
        finally:
            async with self._lock:
                self._pending_requests.pop(request.request_id, None)
    
    async def approve_request(
        self,
        request_id: str,
        approved_by: str = "user",
    ) -> bool:
        """Approve a pending confirmation request."""
        async with self._lock:
            request = self._pending_requests.get(request_id)
            if not request or request.is_expired():
                return False
            
            request.status = "approved"
            request.approved_by = approved_by
            
            self._log_event(
                "confirmation_approved",
                request.agent_id,
                request_id=request_id,
                approved_by=approved_by,
            )
            
            return True
    
    async def deny_request(
        self,
        request_id: str,
        denied_by: str = "user",
    ) -> bool:
        """Deny a pending confirmation request."""
        async with self._lock:
            request = self._pending_requests.get(request_id)
            if not request:
                return False
            
            request.status = "denied"
            
            self._log_event(
                "confirmation_denied",
                request.agent_id,
                request_id=request_id,
                denied_by=denied_by,
            )
            
            return True
    
    def get_pending_requests(self) -> List[AccessRequest]:
        """Get all pending confirmation requests."""
        return [
            r for r in self._pending_requests.values()
            if r.status == "pending" and not r.is_expired()
        ]
    
    def _log_event(
        self,
        event_type: str,
        agent_id: str,
        **kwargs,
    ) -> None:
        """Log an access event."""
        event = {
            "timestamp": time.time(),
            "event_type": event_type,
            "agent_id": agent_id,
            **kwargs,
        }
        self._audit_log.append(event)
        
        # Keep limited log
        if len(self._audit_log) > 10000:
            self._audit_log = self._audit_log[-10000:]
    
    def get_audit_log(
        self,
        agent_id: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get audit log entries."""
        entries = self._audit_log
        
        if agent_id:
            entries = [e for e in entries if e["agent_id"] == agent_id]
        if event_type:
            entries = [e for e in entries if e["event_type"] == event_type]
        
        return entries[-limit:]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get access manager statistics."""
        return {
            "registered_agents": len(self._agent_access),
            "privilege_groups": list(self._groups.keys()),
            "pending_requests": len(self.get_pending_requests()),
            "audit_log_size": len(self._audit_log),
        }

